#!/usr/bin/env python3
"""Three tiers for religion, language and ethnicity, and the rules behind them.

``canonical_groups.py`` says which *labels* mean the same thing. This says how
those names nest, so one set of census rows can answer three questions at three
widths: what is the broadest honest grouping, what family is this, and what did
the source actually write.

    tier 1   the broadest defensible grouping
    tier 2   the family
    tier 3   the group as reported

                 religion            language            ethnicity
    tier 1   Abrahamic religions   Indo-European       African ancestry
    tier 2   Christianity          Germanic            Bantu peoples
    tier 3   Catholicism           English             Zulu

Five rules govern the whole table.

**Roll up, never across.** A group's share is its own rows plus every
descendant's, each counted once. This is only sound while no source publishes a
level beside its own parent; ``check_no_double_counting`` stops the build if one
starts to. A parent's own rows are not a total restated -- a census that offers
"Christian" against "Catholic" means people who named the religion and no
tradition, and the two are disjoint answers to one question.

**A tier is a claim, and tier 1 is the weakest one.** Tier 3 is each country's
own words, which is where cross-border comparison is least safe; tier 1 is
where it is least unsafe. Reading up the tree trades detail for comparability
and the reader should be told that, not just shown it.

**Ethnicity's tier 1 is ancestry, not race.** Race categories are made by
states and no two states make the same ones: US race, Brazilian *cor ou raça*,
UK ethnic group and Chinese *minzu* have different answer sets and different
questions behind them. What they do have in common with an ethnonym is that
both assert something about where a population came from, so ancestry is the
axis that can carry all of them at once -- and it is why Yoruba, "Black or
African American" and Nigerian all land in one colour band on the map.

**A census race category is a sibling of the peoples, never their parent.**
"Black or African American" and Bantu peoples both sit under African ancestry;
neither contains the other. Making Yoruba a child of Black would have the map
assert a mapping no census publishes, and would double-count the moment a
source published both. They are marked so the interface can say which kind of
answer a group is.

**A contested placement gets its own tier-1 node rather than a forced one.**
Jews are an ethnoreligious people counted by European registers; Roma are of
South Asian origin and European residence; neither belongs under one ancestry
without an argument this map has no business making. They stand alone, which
costs one colour and no honesty.

Coverage is measured, not assumed: ``python -m scripts.group_tree --coverage``
prints the share of the shipped map each field's table accounts for.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# Religion: tradition -> religion
# ---------------------------------------------------------------------------
#
# The families below already exist in canonical_groups.RELIGION; this adds the
# tier above them. The groupings are the standard comparative-religion ones and
# each is a real question a reader asks ("where are the Abrahamic religions
# majority"), which is the test a tier-1 node has to pass: if nobody would ever
# select it, it is a filing cabinet and not a category.

RELIGION_TRADITION: dict[str, tuple[str, ...]] = {
    "Abrahamic religions": (
        "Christianity", "Islam", "Judaism", "Baha'i", "Druze", "Samaritan",
        "Rastafarian",
    ),
    "Indian religions": ("Hinduism", "Buddhism", "Sikhism", "Jainism"),
    "East Asian religions": (
        "Taoism", "Confucianism", "Shinto", "Caodaism", "Chondogyo",
        "Cheondoism", "Tenrikyo", "Buddhist or Taoist",
    ),
    "African diaspora religions": ("Spiritism and Afro-Brazilian religions",
                                  # Jamaica's Revival, which its census
                                  # counts apart from the churches.
                                  "Revivalist"),
    "Folk and traditional religions": (
        "Folk and traditional religion", "Māori religions", "Kirat",
        "Prakriti", "Bon", "Modekngei", "Badimo", "Shamanism",
        # Myanmar's nat worship, named the way the census names it.
        "Nat",
        # India's Adivasi religions, from Census 2011 table C-01 Appendix --
        # the break-up of "Other religions and persuasions", which is the only
        # place any census names them. They are here for the same reason
        # Nepal's Kirat, Prakriti and Bon are: they are living traditions with
        # a counted population, and dropping them into "Folk and traditional
        # religion" would erase the one census that counts them. Donyi-Polo is
        # 26% of Arunachal Pradesh, Sanamahi 8% of Manipur, Sarna 13% of
        # Jharkhand. Several are named for the people rather than the faith --
        # "Adi", "Santal", "Munda" -- because that is the answer the census
        # recorded; see canonical_groups for the spellings each folds.
        "Donyi-Polo", "Sarna", "Sari Dharma", "Sanamahi", "Khasi", "Niamtre",
        "Niam Shnong", "Songsarek", "Heraka", "Gondi", "Koyatur",
        "Addi Bassi", "Adi", "Bidin", "Nocte", "Rangfra", "Intaya",
        "Nani Intiya", "Nyarino", "Idu Mishmi", "Hill Miri", "Aka",
        "Santal", "Ho", "Munda", "Oraon", "Bhil", "Baiga", "Korku",
        "Boro", "Karbi",
    ),
    "Other and new religions": (
        "Zoroastrianism", "Yazidi", "Jedi", "Eckankar", "Wicca",
        "Pagan and neo-pagan", "Spiritualism and New Age religions",
        "Eastern religions", "Other religions",
        # India's C-01 Appendix names a religion only where it has a hundred
        # adherents nationally, so every state has a part of the residual that
        # it does not name. india_census.py shows that part rather than
        # normalising it away, and it is not the same thing as the whole
        # "Other religions" bucket -- it is what is left of the bucket once the
        # named religions are out of it.
        "Other religions (not separately named)",
    ),
    "No religion": ("No religion",),
    "Not stated": ("Not stated", "Unaffiliated or not reported",
                   "Scheduled Castes",
                   # Labels that weld a real answer to a non-answer, filed
                   # here beside "Other, none, or not stated": no religion
                   # is named by any of them, and a map that coloured a
                   # country for one would have answered the wrong question.
                   "other or none", "none or refused",
                   "other and unaffiliated", "other or unaffiliated",
                   "agnostics and other", "not applicable", "undeclared",
                   "No Data", "No religion data"),
}

# The Philippines names 82 churches in its 2020 census and Northern Ireland
# names 40. Each is plainly a Christian body and none is reported anywhere
# else, so listing them by hand would be two hundred lines that all say
# "Protestant". These say it once, as a rule about the name: a body whose name
# contains one of these words is that tradition. Only ever applied where no
# exact name matched, and only to the word as it stands -- "Church of Jesus
# Christ of the Latter Day Saints" is matched by "Latter Day" before it can be
# matched by "Church of".
RELIGION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # First, because the rule below reads "Believer" as the name of a church
    # and these are the opposite of one. Czechia, Nicaragua and Venezuela all
    # print a row for someone who believes and belongs to nothing, and it had
    # been counted as Protestant for want of anywhere else to put it. The
    # roots are whole labels and are matched with their case, so "Believers
    # Church" is still a church.
    ("Unaffiliated or not reported",
     ("Believer, church not named", "Believer, no church",
      "believer but not belonging to a church", "believer")),
    ("Latter-day Saints", ("Latter Day", "Latter-day", "Mormon")),
    # Angola's Tocoist church, an African-initiated Christian body that no
    # other tradition here covers.
    ("Christianity", ("Tocoist",)),
    ("Jehovah's Witnesses", ("Jehovah",)),
    ("Orthodoxy", ("Orthodox",)),
    ("Catholicism", ("Catholic", "Oblates")),
    ("Protestantism", (
        "Protestant", "Salvation", "Fellowship", "Believer", "Praise",
        "Outreach", "Faith", "Anabaptist", "Espiritista", "Evangelist",
        "Jesus", "Assemblies", "Assembly", "Word for the World",
        "Things to Come", "Lord of the Nations", "Way of Salvation",
        "Baptist", "Pentecostal", "Evangelical", "Methodist", "Lutheran",
        "Presbyterian", "Anglican", "Episcopal", "Adventist", "Reformed",
        "Brethren", "Iglesia", "Ministries", "Mission", "Church", "Christ",
        "Christian", "Gospel", "Assembly of God", "Assemblies of God",
    )),
    ("Islam", ("Muslim", "Islamic", "Bektashi")),
    ("Folk and traditional religion", ("Tribal", "Traditional", "traditional",
                                       "spirituality", "Animist", "Animist",
                                       "animist", "Indigenous")),
    # A life stance that is the absence of a religion, however the register
    # words it.
    ("No religion", ("Without religion", "without religion", "Humanist",
                     "humanist")),
    ("Pagan and neo-pagan", ("Pagan", "pagan")),
    # Bosnia's registers record a nationality where the form asks for a
    # religion. The adapter says so in the label; what it is not is a
    # religion, which is where "Scheduled Castes" already sits.
    ("Not stated", ("written as religion",)),
    ("Not stated", ("not reported", "not stated", "Not reported",
                    "Not stated", "no answer", "unspecified")),
    ("Other religions", ("spiritual traditions", "Other religion")),
)

# ---------------------------------------------------------------------------
# Language: family -> branch -> language
# ---------------------------------------------------------------------------
#
# Genealogical classification as the standard references give it. The branch
# level exists so that related languages look related on the map without being
# merged: Slavic languages should resemble each other and not Hindi, though
# both are Indo-European.
#
# A band is not a language and is never treated as one. The US ACS publishes
# "German or other West Germanic" and "Russian, Polish, or other Slavic";
# those attach at the branch they name, never to a member of it.

LANGUAGE_BRANCH: dict[str, tuple[str, ...]] = {
    # -- Indo-European
    "Germanic languages": (
        "English", "German", "Dutch", "Afrikaans", "Swedish", "Norwegian",
        "Danish", "Icelandic", "Faroese", "Yiddish", "Frisian",
        "Luxembourgish", "Flemish", "Low German", "Scots", "Swiss German",
        "German or other West Germanic", "Norwegian, Bokmål",
        "Norwegian, Nynorsk", "English only",
    ),
    "Romance languages": (
        "Spanish", "Portuguese", "French", "Italian", "Romanian", "Catalan",
        "Galician", "Romansh", "Moldovan", "Occitan", "Sardinian", "Corsican",
        "Friulian", "Ladin", "Aromanian", "Walloon", "Castilian",
        "Castilian Spanish",
        "French, Haitian, or Cajun", "Spanish or Spanish Creole",
    ),
    "Slavic languages": (
        "Russian", "Ukrainian", "Belarusian", "Polish", "Czech", "Slovak",
        "Bulgarian", "Macedonian", "Serbian", "Croatian", "Bosnian",
        "Montenegrin", "Serbo-Croatian", "Slovenian", "Slovene", "Sorbian",
        "Rusyn", "Kashubian", "Silesian", "Bosnian-Croatian-Serbian",
        "Russian, Polish, or other Slavic",
    ),
    "Indo-Aryan languages": (
        "Hindi", "Urdu", "Bengali", "Panjabi", "Punjabi", "Marathi",
        "Gujarati", "Nepali", "Sindhi", "Odia", "Oriya", "Assamese",
        "Kashmiri", "Maithili", "Bhojpuri", "Sinhala", "Sinhalese",
        "Dhivehi", "Romani", "Konkani", "Dogri", "Awadhi", "Chhattisgarhi",
        "Magahi", "Haryanvi", "Rajasthani", "Bishnupriya", "Sylheti",
        "Tharu", "Bajjika", "Doteli", "Achhami", "Rangpuri",
        "Hindko", "Sareiki", "Saraiki", "Khandeshi", "Bhili/Bhilodi",
        "Bhili", "Kacchi", "Parsi", "Rohingya", "Majhi", "Newari",
    ),
    "Iranian languages": (
        "Persian", "Persian (excluding Dari)", "Dari", "Pashto", "Kurdish",
        "Tajik", "Balochi", "Ossetian", "Talysh", "Luri", "Gilaki",
        "Mazanderani", "Zaza", "Pamiri", "Farsi", "Pushto", "Baluchi",
        "Iranian Persian", "Afghan Persian or Dari", "Afghan Persian",
    ),
    "Baltic languages": ("Lithuanian", "Latvian", "Latgalian"),
    "Celtic languages": (
        "Irish", "Welsh", "Scottish Gaelic", "Breton", "Cornish", "Manx",
        "Gaelic",
    ),
    "Hellenic languages": ("Greek",),
    "Albanian languages": ("Albanian",),
    "Armenian languages": ("Armenian",),
    # -- Afro-Asiatic
    "Semitic languages": (
        "Arabic", "Hebrew", "Amharic", "Tigrinya", "Tigre", "Maltese",
        "Assyrian Neo-Aramaic", "Aramaic", "Syriac", "Harari", "Silt'e",
        "Gurage", "Argobba", "Chaldean Neo-Aramaic", "Coptic", "Assyrian",
        "Sebat Bet Gurage", "Tigrigna", "Tigre",
    ),
    "Berber languages": ("Tamazight", "Kabyle", "Berber", "Tachelhit",
                         "Tarifit", "Tamasheq", "Shilha"),
    "Cushitic languages": (
        "Somali", "Oromo", "Afar", "Sidamo", "Sidama", "Beja", "Saho",
        "Agaw", "Hadiyya", "Kambaata", "Konso", "Gedeo", "Bilen", "Awngi",
        "Agew-Kamyrnya", "Kemant", "Libido", "Alaba-K'abeena", "Burji",
        "Daasanach", "Arbore", "Tsamai", "Baiso", "Dirasha", "Bussa",
    ),
    "Chadic languages": ("Hausa", "Bura", "Marghi", "Kanakuru"),
    "Omotic languages": ("Wolaytta", "Wolayita", "Gamo", "Dawro", "Kafa",
                         "Bench", "Basketo", "Male"),
    # -- Sino-Tibetan
    "Sinitic languages": (
        "Chinese", "Mandarin", "Cantonese", "Hokkien", "Hakka", "Teochew",
        "Min Nan", "Wu", "Fuzhou", "Hainanese", "Foochow",
        "Chinese (incl. Mandarin, Cantonese)",
    ),
    "Tibeto-Burman languages": (
        "Burmese", "Tibetan", "Karen", "Chin", "Kachin", "Rakhine", "Mon",
        "Newar", "Tamang", "Magar", "Gurung", "Limbu", "Rai", "Sherpa",
        "Bodo", "Manipuri", "Meitei", "Garo", "Mizo", "Naga", "Sunwar",
        "Thakali", "Chepang", "Dzongkha", "Lepcha",
    ),
    # -- Niger-Congo
    "Bantu languages": (
        "Swahili", "Shona", "isiZulu", "Zulu", "isiXhosa", "Xhosa",
        "Sesotho", "Sotho", "Setswana", "Tswana", "Sepedi", "Pedi",
        "Xitsonga", "Tsonga", "Tshivenda", "Venda", "siSwati", "Swati",
        "isiNdebele", "Ndebele", "Lingala", "Kikongo", "Kongo", "Tshiluba",
        "Luba", "Kinyarwanda", "Kirundi", "Luganda", "Chichewa", "Nyanja",
        "Bemba", "Umbundu", "Kimbundu", "Kikuyu", "Luhya", "Kamba",
        "Meru", "Gusii", "Makhuwa", "Sena", "Tumbuka", "Lozi", "Tonga",
        "Nyakyusa", "Sukuma", "Chaga", "Haya", "Gogo", "Hehe", "Nyamwezi",
        "Duala", "Ewondo", "Fang", "Bulu", "Kituba", "Mongo", "Lomongo",
        "Ganda", "Gikuyu", "Luba-Kasai", "Mwani", "Rundi (Kirundi)",
        "Kinyarwanda (Rwanda)", "Bobangi", "Babango", "Mpiemo",
    ),
    "Volta-Niger languages": ("Yoruba", "Igbo", "Ewe", "Fon", "Edo", "Idoma",
                              "Igala", "Nupe", "Gun", "Aja"),
    "Kwa languages": ("Akan", "Twi", "Fante", "Ga", "Baoulé", "Anyi",
                      "Guang", "Dangme"),
    "Mande languages": ("Bambara", "Malinke", "Maninka", "Dioula", "Jula",
                        "Soninke", "Mende", "Kpelle", "Susu", "Vai", "Bozo"),
    "Atlantic languages": ("Wolof", "Fula", "Fulfulde", "Pulaar", "Serer",
                           "Diola", "Jola", "Temne", "Balanta", "Manjak"),
    "Gur languages": ("Mooré", "More", "Dagbani", "Dagaare", "Gurma",
                      "Senufo", "Lobiri", "Kabiyé", "Bwamu"),
    "Adamawa-Ubangi languages": ("Sango", "Gbaya", "Banda", "Zande", "Ngbaka",
                                 "Mbum", "Mumuye"),
    # -- other families
    "Turkic languages": (
        "Turkish", "Azerbaijani", "Kazakh", "Uzbek", "Kyrgyz", "Turkmen",
        "Tatar", "Bashkir", "Chuvash", "Uyghur", "Yakut", "Sakha",
        "Karakalpak", "Gagauz", "Crimean Tatar", "Kumyk", "Nogai",
        "Karachay-Balkar", "Balkar", "Karachay", "Tuvan", "Khakas", "Altai",
        "Shor", "Karaim", "Salar", "Dolgan",
    ),
    "Mongolic languages": ("Mongolian", "Buryat", "Kalmyk", "Oirat"),
    "Tungusic languages": ("Evenki", "Evenk", "Even", "Nanai", "Udege",
                           "Oroch", "Ulch", "Uilta", "Orok", "Negidal"),
    # The languages of the Russian far east, which Russia's census names one
    # by one. They are not Altaic and not Siberian-by-courtesy: they are a
    # family of their own, and they hang from the same top grouping as the
    # Tungusic languages because that node is where this map keeps northern
    # Asia rather than because anyone claims the two are related.
    "Chukotko-Kamchatkan languages": ("Chukchi", "Koryak", "Itelmen",
                                      "Alyutor", "Kerek"),
    "Uralic languages": (
        "Finnish", "Estonian", "Hungarian", "Sami", "Karelian", "Veps",
        "Komi", "Komi-Permyak", "Udmurt", "Mari", "Erzya", "Moksha",
        "Mordvin", "Khanty", "Mansi", "Nenets", "Ingrian", "Võro",
    ),
    "Kartvelian languages": ("Georgian", "Mingrelian", "Svan", "Laz"),
    "Northeast Caucasian languages": (
        "Chechen", "Ingush", "Avar", "Dargin", "Lezgin", "Lak", "Tabasaran",
        "Rutul", "Tsakhur", "Agul", "Udi", "Andi",
    ),
    "Northwest Caucasian languages": ("Kabardian", "Adyghe", "Abkhaz",
                                      "Abaza", "Circassian"),
    "Dravidian languages": ("Tamil", "Telugu", "Malayalam", "Kannada",
                            "Tulu", "Gondi", "Kurukh", "Kurukh/Oraon", "Brahui", "Brahvi"),
    "Austroasiatic languages": ("Vietnamese", "Khmer", "Khasi", "Wa",
                                "Khmu", "Katang", "Bru", "Nicobarese"),
    # The Munda branch, which India and Nepal both itemise: Santali alone has
    # more speakers than Estonian, and the censuses list a dozen of its
    # relatives beside it.
    "Munda languages": (
        "Santali", "Mundari", "Ho", "Munda", "Kharia", "Korku", "Savara",
        "Sora", "Bhumij", "Juang", "Koda", "Kora", "Korwa", "Mudiyari",
    ),
    "Tai-Kadai languages": ("Thai", "Lao", "Shan", "Zhuang", "Isan"),
    "Hmong-Mien languages": ("Hmong", "Miao", "Mien", "Yao"),
    "Malayo-Polynesian languages": (
        "Malay", "Indonesian", "Javanese", "Sundanese", "Madurese",
        "Minangkabau", "Buginese", "Balinese", "Acehnese", "Batak",
        "Banjar", "Tagalog", "Tagalog (incl. Filipino)", "Filipino",
        "Cebuano", "Ilocano", "Hiligaynon", "Waray", "Bikol", "Kapampangan",
        "Pangasinan", "Maranao", "Maguindanao", "Tausug", "Chavacano",
        "Malagasy", "Tetum", "Chamorro", "Palauan",
        "Southeast Asian Austronesian languages",
    ),
    "Oceanic languages": (
        "Samoan", "Tongan", "Fijian", "Māori", "Maori", "Hawaiian",
        "Cook Islands Maori", "Niuean", "Tokelauan", "Tuvaluan", "Gilbertese",
        "Marshallese", "Chuukese", "Pohnpeian", "Yapese", "Kosraean",
        "Nauruan", "Rotuman", "Wallisian", "Tahitian", "Rapa Nui",
    ),
    "Papuan languages": ("Tok Pisin languages", "Enga", "Melpa", "Huli",
                         "Dani", "Asmat"),
    "Japonic languages": ("Japanese", "Okinawan"),
    "Koreanic languages": ("Korean",),
    "Indigenous languages of the Americas": (
        "Quechua", "Aymara", "Guarani", "Nahuatl", "Maya", "Yucatec Maya",
        "Zapotec", "Mixtec", "Otomi", "Totonac", "Purepecha", "Tzeltal",
        "Tzotzil", "Mazahua", "Mazatec", "Huastec", "Chol", "Mapudungun",
        "Wayuu", "Miskito", "Garifuna", "Kichwa", "Shuar", "Mam",
        "Kʼicheʼ", "Qʼeqchiʼ", "Shipibo-Konibo", "Shawi", "Ignaciano",
        "Speaks an indigenous language",
    ),
    "Indigenous languages of Australia": (
        "Australian Aboriginal languages", "Arrernte", "Warlpiri",
        "Yolngu Matha", "Pitjantjatjara", "Kriol",
    ),
    "Creole languages": (
        "Creole", "Haitian Creole", "Papiamento", "Tok Pisin", "Bislama",
        "Sranan Tongo", "Cape Verdean Creole", "Mauritian Creole",
        "Seychellois Creole", "Krio", "Patois", "Jamaican Patois",
        "Antillean Creole", "Guianese Creole", "Pidgin", "Nigerian Pidgin",
        "Sango creole",
    ),
    "Sign languages": ("Sign language", "Auslan", "New Zealand Sign Language",
                       "British Sign Language", "American Sign Language"),
    # The click languages of southern Africa. "Khoisan" is not one family --
    # it is three, plus Sandawe and Hadza -- and that is exactly why the
    # languages under it can hang from nothing else: they are not Niger-Congo
    # and they are not Nilo-Saharan, and filing them under either to save a
    # colour would be an assertion no reference makes. This is the same
    # argument the ethnicity tree makes for Khoisan peoples.
    # "San" on its own is deliberately absent: Burkina Faso's census writes
    # it for the San (Samo) language, which is Mande, and one three-letter
    # string cannot be both.
    "Khoisan languages": (
        "Khoisan", "Khoi", "Nama", "Sarwa", "Sandawe", "Damara",
        "Khoi, Nama & San languages", "Nama/Damara",
    ),
    "Language isolates": ("Basque", "Korean isolate", "Ainu", "Burushaski",
                          "Nivkh", "Ket", "Haida", "Ktunaxa", "Kutenai",
                          "Ktunaxa (Kutenai)"),
    # -- Nilo-Saharan, which Ethiopia, South Sudan and Chad all report
    "Nilotic languages": (
        "Nuer", "Dinka", "Shilluk", "Anuak", "Anyiwak", "Luo", "Acholi",
        "Langi", "Alur", "Bari", "Karamojong", "Turkana", "Maasai",
        "Kalenjin", "Nyangatom", "Toposa", "Datooga",
    ),
    "Central Sudanic languages": ("Kresh", "Birri", "Sara", "Sara Proper",
                                  "Ngam (Sara)", "Yulu", "Runga", "Lugbara",
                                  "Ma'di", "Bongo"),
    "Surmic and Koman languages": (
        "Suri", "Suri (Suri)", "Mursi", "Me'en", "Me’en", "Murle", "Bodi",
        "Kwegu", "Kwegu (Kwegoi)", "Komo", "Komo (Sudan)", "Gumuz",
        "Berta", "Kunama", "Nara", "Uduk", "Opuuo",
    ),
    # -- the Indigenous families of Canada, which its census names in full
    "Algonquian languages": (
        "Cree", "Plains Cree", "Woods Cree", "Swampy Cree", "Moose Cree",
        "Nehiyawewin (Plains Cree)", "Nihithawiwin (Woods Cree)",
        "Nehinawewin (Swampy Cree)", "Ililimowin (Moose Cree)",
        "Iyiyiw-Ayimiwin (Northern East Cree)",
        "Inu Ayimun (Southern East Cree)", "Innu (Montagnais)", "Naskapi",
        "Atikamekw", "Ojibway", "Oji-Cree", "Saulteau (Western Ojibway)",
        "Anishinaabemowin (Chippewa)", "Anicinabemowin (Algonquin)",
        "Daawaamwin (Odawa)", "Mi'kmaq", "Wolastoqewi (Malecite)",
        "Ojibwe",
        "Blackfoot", "Michif",
    ),
    "Athabaskan languages": (
        "Dene", "Dakelh (Carrier)", "Tlicho (Dogrib)", "Slavey",
        "Satuotine Yati (North Slavey)", "Deh Gah Ghotie Zhatie (South Slavey)",
        "Gwich'in", "Dane-zaa (Beaver)", "Tsuu T'ina (Sarsi)", "Navajo",
        "Tse'khene (Sekani)", "Tsilhqot'in (Chilcotin)", "Tahltan", "Kaska",
        "Kaska (Nahani)", "Tutchone", "Northern Tutchone", "Southern Tutchone",
        "Wetsuwet'en-Babine", "Han", "Upper Tanana",
    ),
    "Iroquoian languages": ("Mohawk", "Oneida", "Cayuga", "Onondaga",
                            "Seneca", "Tuscarora", "Cherokee"),
    "Salish languages": (
        "Halkomelem", "Squamish", "Lillooet", "Syilx (Okanagan)", "Straits",
        "Secwepemctsin (Shuswap)", "Ntlakapamux (Thompson)", "Comox",
        "Sechelt", "Nuxalk",
    ),
    "Wakashan languages": ("Kwak'wala (Kwakiutl)", "Nuu-chah-nulth (Nootka)",
                           "Haisla", "Heiltsuk", "Oowekyala"),
    "Tsimshianic languages": ("Tsimshian", "Nisga'a", "Gitxsan (Gitksan)",
                              "Gitxsan"),
    "Siouan languages": ("Stoney", "Assiniboine", "Dakota", "Lakota",
                         "Nakota", "Sioux"),
    "Eskimo-Aleut languages": ("Inuktitut", "Inuinnaqtun", "Inuvialuktun",
                               "Inuktut", "Greenlandic", "Kalaallisut",
                               "Aleut", "Yupik"),
    "Tlingit languages": ("Tlingit",),
}

LANGUAGE_FAMILY: dict[str, tuple[str, ...]] = {
    "Indo-European languages": (
        "Germanic languages", "Romance languages", "Slavic languages",
        "Indo-Aryan languages", "Iranian languages", "Baltic languages",
        "Celtic languages", "Hellenic languages", "Albanian languages",
        "Armenian languages",
    ),
    "Afro-Asiatic languages": (
        "Semitic languages", "Berber languages", "Cushitic languages",
        "Chadic languages", "Omotic languages",
    ),
    "Sino-Tibetan languages": ("Sinitic languages", "Tibeto-Burman languages"),
    "Niger-Congo languages": (
        "Bantu languages", "Volta-Niger languages", "Kwa languages",
        "Mande languages", "Atlantic languages", "Gur languages",
        "Adamawa-Ubangi languages",
    ),
    "Austronesian languages": ("Malayo-Polynesian languages",
                               "Oceanic languages"),
    "Turkic languages": ("Turkic languages",),
    "Uralic languages": ("Uralic languages",),
    "Caucasian languages": ("Kartvelian languages",
                            "Northeast Caucasian languages",
                            "Northwest Caucasian languages"),
    "Altaic and Siberian languages": ("Mongolic languages",
                                      "Tungusic languages",
                                      "Chukotko-Kamchatkan languages"),
    "Dravidian languages": ("Dravidian languages",),
    "Austroasiatic languages": ("Austroasiatic languages", "Munda languages"),
    "Khoisan languages": ("Khoisan languages",),
    "Tai-Kadai languages": ("Tai-Kadai languages",),
    "Hmong-Mien languages": ("Hmong-Mien languages",),
    "Japonic languages": ("Japonic languages",),
    "Koreanic languages": ("Koreanic languages",),
    "Papuan languages": ("Papuan languages",),
    "Indigenous languages of the Americas": (
        "Indigenous languages of the Americas", "Algonquian languages",
        "Athabaskan languages", "Iroquoian languages", "Salish languages",
        "Wakashan languages", "Tsimshianic languages", "Siouan languages",
        "Eskimo-Aleut languages", "Tlingit languages"),
    "Nilo-Saharan languages": ("Nilotic languages",
                               "Central Sudanic languages",
                               "Surmic and Koman languages"),
    "Indigenous languages of Australia": (
        "Indigenous languages of Australia",),
    "Creole and contact languages": ("Creole languages",),
    "Sign languages": ("Sign languages",),
    "Language isolates": ("Language isolates",),
    # Where a source publishes a band rather than a language, the band attaches
    # to the family it names and no further: "Other Indo-European" is an
    # Indo-European figure and is not evidence about any member of it.
    "Other and unspecified languages": ("Unclassified language answers",),
}

# Bands and non-answers. A band that names one family joins it; a band that
# spans several, and every form of "not stated", joins the residual family --
# because the alternative is a map that colours a district for a category
# which is the absence of an answer.
LANGUAGE_BANDS: dict[str, tuple[str, ...]] = {
    "Indo-European languages": ("Other Indo-European", "Indo-Aryan",
                                # Afghanistan's third Indo-Iranian branch,
                                # which is neither Iranian nor Indo-Aryan.
                                "Nuristani"),
    "Indo-Aryan languages": ("Bihari languages", "Bihari"),
    "Austroasiatic languages": ("Austro-Asiatic languages, n.i.e",
                                "Austro-Asiatic languages, n.i.e.",
                                "Austro-Asiatic languages", "Munda languages"),
    # Canada's own remainder for the languages it does not itemise. It covers
    # Canadian Indigenous languages and nothing else, so it belongs inside
    # that grouping rather than in the drawer of non-answers.
    "Indigenous languages of the Americas": (
        "Indigenous languages, n.i.e.", "Indigenous languages, n.o.s.",
        "Aboriginal languages, n.o.s.",
    ),
    # Bands a Pacific census writes for the island languages it does not
    # name. Every language they cover is Oceanic.
    "Oceanic languages": ("other Micronesian", "other Pacific Island languages",
                          "other Pacific island languages",
                          "other Pacific Islander", "Austral languages"),
    "Slavic languages": ("Croato-Serbian", "Ruthenian", "Lemko", "Moravian",
                         "Boyko", "Old Church Slavonic", "Slavic",
                         "Goral dialect", "Goral", "Bosniak"),
    "Sign languages": ("Polish Sign Language", "Sign languages",
                       "Russian Sign Language", "Quebec Sign Language",
                       "Peruvian Sign Language", "Deaf, does not speak"),
    "Sinitic languages": ("Sinitic not further defined", "Chinese dialects",
                          "Min Dong", "Yue", "Wu"),
    "Malayo-Polynesian languages": ("Bisaya, n.o.s.", "Kinaray-a",
                                    "Waray-Waray", "Kankanaey",
                                    "Pampangan"),
    "Mande languages": ("Bamanankan", "Wojenaka", "Mossi", "Mòoré"),
    "Creole languages": ("Morisyen", "Jamaican English Creole", "Sango",
                         "Sango Riverain", "Plautdietsch", "Pennsylvania German",
                         "Low Saxon", "Mina"),
    "Unclassified language answers": (
        "Other languages", "Other and unspecified", "Other small languages",
        "Other languages (unspecified)", "Language not stated",
        "Other Asian and Pacific Island",
        # Not "Other and unspecified languages": that is the tier-1 node this
        # band already hangs from, and naming it here too made the two each
        # other's parent. The loop was invisible until the top of the tree
        # started refusing a parent outright.
        "Other language", "Other", "Not stated",
        # Bands that span families rather than naming one. "Other African
        # languages" covers Niger-Congo, Nilo-Saharan and Afro-Asiatic at
        # once, which is no more a family than "African, n.o.s." above it.
        "Other African languages", "other African languages",
        "other Mozambican languages",
        "other European languages", "Other Mali languages",
        "Other non-African language", "Asian languages", "minority languages",
        "only other languages", "indigenous languages",
        # The Factbook's sentence where a census would print a table. It
        # names no language and cannot be read as one, but it led Papua New
        # Guinea's whole entry until it was named here.
        "some 839 living indigenous languages are spoken",
        # Counts of how many languages a person speaks, and the rows a
        # register prints where it has no answer at all.
        "two languages", "two mother tongues", "Two mother tongues",
        "multilingual", "persons 5 or mute", "none", "Unstated",
        "undeclared or unknown", "other or unspecified", "Not applicable",
        # Constructed and classical languages, filed with Esperanto, Latin
        # and Sanskrit above: nobody answers a mother-tongue question with
        # them, and a census that lists them is printing a code list.
        "Ido", "Avestan", "pali", "Pali",
        # Mexico asks whether a person speaks an indigenous language, which is
        # a different question from which language they speak. Neither answer
        # names one, so neither can sit in a family.
        "Does not speak an indigenous language",
        # Canada counts the combinations a household speaks, which name no one
        # language and cannot be filed under any family.
        "English and French", "English and non-official language(s)",
        "French and non-official language(s)",
        "English, French and non-official language(s)",
        "Multiple non-official languages", "None (eg too young to talk)",
        "Not elsewhere included", "African, n.o.s.", "Other local language",
        "Other native language", "Foreign language", "Other Foreign Language",
        "Other Ethiopian Language", "Other Indian languages", "Esperanto",
        "Latin", "Sanskrit", "Other language", "Other languages, n.i.e.",
    ),
}


# ---------------------------------------------------------------------------
# Ethnicity: ancestry -> people family or census category -> group as reported
# ---------------------------------------------------------------------------
#
# Ethnonyms are classified ethnolinguistically, which is the same axis the
# language table uses and the reason the two maps rhyme: a Bantu-speaking
# people and a Bantu language get related colours. Where an ethnonym and a
# language share a name -- which is most of the time -- the two tables agree by
# construction, because both were written from the same classification.

ETHNIC_PEOPLES: dict[str, tuple[str, ...]] = {
    # -- Europe
    "Germanic peoples": (
        "German", "Austrian", "Swiss", "Dutch", "Flemish", "Danish",
        "Swedish", "Norwegian", "Icelandic", "English", "Scottish", "Welsh",
        "British", "Irish", "Luxembourger", "Frisian", "Afrikaner", "Boer",
    ),
    "Romance peoples": (
        "Italian", "French", "Spanish", "Portuguese", "Romanian", "Moldovan",
        "Catalan", "Galician", "Walloon", "Aromanian", "Vlach", "Romansh",
        "Sardinian", "Corsican", "Friulian", "Ladin", "Istro-Romanian",
    ),
    "Slavic peoples": (
        "Russian", "Ukrainian", "Belarusian", "Polish", "Czech", "Slovak",
        "Bulgarian", "Macedonian", "Serbian", "Croatian", "Bosniak",
        "Bosnian", "Montenegrin", "Slovene", "Slovenian", "Silesian",
        "Kashubian", "Rusyn", "Lemko", "Boyko", "Sorbian", "Goral",
        "Yugoslav", "Czechoslovak", "Moravian", "Masurian", "Ruthenian",
        "Pomak",
    ),
    "Baltic peoples": ("Lithuanian", "Latvian", "Latgalian"),
    "Greek and Albanian peoples": ("Greek", "Albanian", "Arvanite"),
    "Finnic and Ugric peoples": (
        "Finnish", "Estonian", "Hungarian", "Sami", "Karelian", "Veps",
        "Ingrian", "Komi", "Komi-Permyak", "Udmurt", "Mari", "Mordvin",
        "Erzya", "Moksha", "Khanty", "Mansi", "Nenets", "Setu",
    ),
    # -- the Middle East and North Africa
    "Arab peoples": (
        "Arab", "Arabs", "Sri Lankan Moor", "Moor", "Syrian", "Egyptian", "Lebanese", "Iraqi",
        "Palestinian", "Jordanian", "Yemeni", "Saudi", "Moroccan",
        "Algerian", "Tunisian", "Libyan", "Sudanese", "Bedouin", "Emirati",
        "Kuwaiti", "Omani", "Qatari", "Bahraini",
    ),
    "Iranian peoples": (
        "Persian", "Kurd", "Kurdish", "Pashtun", "Tajik", "Baloch",
        "Balochi", "Hazara", "Ossetian", "Talysh", "Pamiri", "Lur",
        "Afghan", "Iranian", "Tat", "Aimaq", "Nuristani", "Yazidi",
        "Zaza", "Gilaki", "Mazandarani",
    ),
    "Berber peoples": ("Berber", "Amazigh", "Tamazight", "Tuareg", "Kabyle",
                       "Rif", "Shilha", "Imalawa", "Arab-Amazigh",
                       "Arab-Berber"),
    "Caucasian peoples": (
        "Georgian", "Chechen", "Ingush", "Avar", "Dargin", "Lezgin", "Lak",
        "Tabasaran", "Rutul", "Tsakhur", "Agul", "Udi", "Kabardian",
        "Adyghe", "Abkhaz", "Abaza", "Circassian", "Mingrelian", "Svan",
        "Andi",
    ),
    "Armenian peoples": ("Armenian",),
    "Assyrian and Aramean peoples": ("Assyrian", "Aramean", "Chaldean",
                                     "Syriac"),
    "Turkic peoples": (
        "Turkish", "Turk", "Azerbaijani", "Kazakh", "Uzbek", "Kyrgyz",
        "Turkmen", "Tatar", "Crimean Tatar", "Bashkir", "Chuvash", "Uyghur",
        "Yakut", "Sakha", "Karakalpak", "Gagauz", "Kumyk", "Nogai",
        "Balkar", "Karachay", "Tuvan", "Khakas", "Altai", "Shor", "Karaim",
        "Dolgan", "Nagaybak", "Kumandin", "Meskhetian Turk", "Dungan",
    ),
    # -- Africa
    "Bantu peoples": (
        "Zulu", "Xhosa", "Sotho", "Tswana", "Tsonga", "Venda", "Swazi",
        "Ndebele", "Shona", "Kikuyu", "Luhya", "Kamba", "Kisii", "Meru",
        "Embu", "Taita", "Mijikenda", "Swahili", "Chaga", "Sukuma",
        "Nyamwezi", "Haya", "Makonde", "Hehe", "Gogo", "Bemba", "Tonga",
        "Lozi", "Chewa", "Ngoni", "Lunda", "Luvale", "Tumbuka", "Yao",
        "Makhuwa", "Sena", "Ndau", "Kalanga", "Nambya", "Kongo", "Bakongo",
        "Luba", "Lulua", "Mongo", "Ovimbundu", "Ambundu", "Bakota",
        "Fang", "Bamileke", "Beti", "Duala", "Tikar", "Baganda",
        "Banyankole", "Basoga", "Bakiga", "Banyarwanda", "Hutu", "Tutsi",
        "Twa", "Bubi", "Herero", "Ovambo", "Kavango", "Caprivian",
        "Cuangar", "Ndonga", "Kimbundu", "Umbundu",
    ),
    "West African peoples": (
        "Yoruba", "Igbo", "Hausa", "Fulani", "Peulh", "Fula", "Akan",
        "Ashanti", "Ewe", "Ga", "Dagomba", "Wolof", "Serer", "Diola",
        "Jola", "Bambara", "Malinke", "Soninke", "Dogon", "Mossi", "Bobo",
        "Senufo", "Lobi", "Gurunsi", "Bissa", "Gourmantche", "Mande",
        "Kru", "Temne", "Mende", "Limba", "Kpelle", "Bassa", "Gio",
        "Krahn", "Kanuri", "Tiv", "Ijaw", "Ibibio", "Nupe", "Edo",
        "Susu", "Kissi", "Toma", "Guerze", "Baoule", "Bete", "Dan",
        "Balanta", "Manjak", "Papel", "Bijago", "Sarakole", "Songhai",
        "Tukulor", "Dioula", "Kabye", "Fon", "Adja", "Bariba", "Yom",
        "Betamaribe", "Mandingo", "Vai", "Sherbro", "Kono", "Loko",
    ),
    "Nilotic peoples": (
        "Luo", "Kalenjin", "Maasai", "Turkana", "Samburu", "Dinka", "Nuer",
        "Shilluk", "Acholi", "Langi", "Iteso", "Karamojong", "Lugbara",
        "Alur", "Bari", "Pokot", "Nandi", "Kipsigis",
    ),
    "Horn of Africa peoples": (
        "Somali", "Oromo", "Amhara", "Tigray", "Tigrayan", "Tigrinya",
        "Sidama", "Afar", "Gurage", "Wolayita", "Hadiya", "Kembata",
        "Konso", "Gedeo", "Agew", "Argobba", "Harari", "Saho", "Beja",
        "Kunama", "Nara", "Issa", "Gamo", "Dawro", "Kafa", "Bench",
        "Silte", "Burji", "Mareko", "Alaba", "Shinasha", "Wolaita",
    ),
    "Central African peoples": (
        "Gbaya", "Banda", "Zande", "Ngbaka", "Mbum", "Sara", "Mandjia",
        "Yakoma", "Sango", "Nzakara", "Ngbandi", "Mbaka", "Kaba",
        "Zaghawa", "Massa", "Toupouri", "Moundang", "Baka", "Aka",
        "Mbuti", "Batwa", "Kanembu", "Ouaddai", "Hadjarai", "Tandjile",
    ),
    "Malagasy peoples": ("Malagasy", "Merina", "Betsileo", "Betsimisaraka",
                         "Sakalava", "Tsimihety", "Antaisaka", "Antandroy"),
    "Khoisan peoples": ("Khoisan", "San", "Khoi", "Nama", "Basarwa", "Bushmen",
                        "Kwoi", "Vátua"),
    # -- South, East and Southeast Asia
    "Indo-Aryan peoples": (
        "Bengali", "Punjabi", "Panjabi", "Gujarati", "Marathi", "Sindhi",
        "Nepali", "Sinhalese", "Kashmiri", "Assamese", "Odia", "Bihari",
        "Rajasthani", "Brahman - Hill", "Brahman - Tarai", "Kshetri",
        "Thakuri", "Tharu", "Magar", "Chhetri", "Yadav", "Musalman",
        "Kumal", "Majhi", "Bishwokarma", "Pariyar", "Sanyasi/Dasnami",
        "Gharti/Bhujel", "Mijar", "Sarki", "Damai", "Kami", "Teli",
        "Kurmi", "Dhanuk", "Mallaha", "Chamar", "Dusadh", "Koiri",
    ),
    "Dravidian peoples": ("Tamil", "Telugu", "Malayali", "Kannadiga",
                          "Gond", "Tulu", "Brahui", "Sri Lankan Tamil",
                          "Indian Tamil", "Oraon", "Kudukh", "Kurukh"),
    # The Austroasiatic-speaking peoples of eastern India and the Nepal
    # Tarai. India counts more Santals than Norway has people, and neither
    # Indo-Aryan nor Dravidian is where they belong.
    "Munda peoples": ("Santal", "Santhal", "Santali", "Munda", "Ho",
                      "Kharia", "Korku", "Bhumij", "Sora", "Savara",
                      "Juang", "Mundari"),
    # Basques are neither Romance nor anything else in this band; the
    # language they are named for has no relatives at all.
    "Basque peoples": ("Basque", "Euskaldun"),
    "Himalayan and Tibeto-Burman peoples": (
        "Tamang", "Newar", "Newa: (Newar)", "Gurung", "Rai", "Limbu",
        "Sherpa", "Sunuwar", "Thakali", "Chepang", "Tibetan", "Bhutia",
        "Lepcha", "Bodo", "Naga", "Mizo", "Manipuri", "Garo", "Khasi",
        "Chin", "Kachin", "Karen", "Rakhine", "Mon", "Shan", "Kayah",
        "Burman", "Bamar", "Wa", "Palaung", "Danu", "Kokang", "Lahu",
        "Akha", "Lisu",
    ),
    "Han and Sinitic peoples": ("Chinese", "Han", "Taiwanese", "Hui",
                                "Hakka", "Hokkien", "Teochew", "Cantonese"),
    "Japanese peoples": ("Japanese", "Ainu", "Ryukyuan"),
    "Korean peoples": ("Korean", "South Korean", "North Korean"),
    "Mongolic and Siberian peoples": (
        "Mongolian", "Mongol", "Buryat", "Kalmyk", "Evenk", "Evenki", "Even",
        "Nanai", "Udege", "Chukchi", "Koryak", "Nivkh", "Yupik", "Itelmen",
        "Ulchi", "Oroch", "Ket", "Selkup", "Tofalar", "Eskimo",
    ),
    "Mainland Southeast Asian peoples": (
        "Vietnamese", "Thai", "Lao", "Khmer", "Hmong", "Miao",
        "Muong", "Tay", "Nung", "Cham", "Zhuang", "Isan",
    ),
    "Malay and Indonesian peoples": (
        "Malay", "Indonesian", "Javanese", "Sundanese", "Madurese",
        "Minangkabau", "Buginese", "Balinese", "Acehnese", "Batak",
        "Banjar", "Betawi", "Dayak", "Bumiputera", "Other Bumiputera",
        "Sama", "Bajau", "Badjao", "Iban", "Kadazan", "Melanau", "Murut",
        "Bidayuh", "Orang Asli", "Sangir/Sangil", "Molbog",
    ),
    "Philippine peoples": (
        "Filipino", "Tagalog", "Cebuano", "Ilocano", "Ilonggo", "Bikol/Bicol",
        "Bisaya/Binisaya", "Boholano", "Pangasinan", "Waray", "Kapampangan",
        "Maranao", "Maguindanao", "Tausog/Tausug", "Zamboangeño",
        "Surigaonon", "Karay-a", "Masbateño/Masbatenon", "Capizeño",
        "Romblomanon", "Bantoanon", "Ibanag", "Itawes", "Yogad", "Isinai",
        "Gaddang", "Ivatan", "Ibatan", "Cuyonen/Cuyunon", "Agutaynen",
        "Cagayanen", "Palawani", "Tagbanua", "Yakan",
        "Jama Mapun", "Kolibugan", "Sama/Samal", "Caviteño", "Batangan",
    ),
    "Aboriginal and Torres Strait Islander peoples": (
        "Aboriginal", "Torres Strait Islander",
        "Aboriginal and Torres Strait Islander",
    ),
    # -- the Pacific
    "Polynesian peoples": (
        "Māori", "Maori", "Samoan", "Tongan", "Cook Islands Maori", "Niuean",
        "Tokelauan", "Tuvaluan", "Hawaiian", "Tahitian", "Wallisian",
        "Rotuman", "Pacific Peoples",
    ),
    "Melanesian peoples": ("Fijian", "Ni-Vanuatu", "Papuan", "Solomon Islander",
                           "Kanak", "New Caledonian"),
    "Micronesian peoples": ("Chamorro", "Palauan", "Marshallese", "Chuukese",
                            "Pohnpeian", "Yapese", "Kosraean", "Nauruan",
                            "i-Kiribati", "Gilbertese"),
    # -- the Americas
    "Indigenous peoples of North America": (
        "Navajo", "Cherokee", "Sioux", "Ojibwe", "Cree", "Inuit", "Métis",
        "Apache", "Choctaw", "Chippewa", "Blackfoot", "Iroquois", "Pueblo",
        "First Nations", "Alaska Native", "Aleut",
    ),
    "Indigenous peoples of Mesoamerica and the Caribbean": (
        "Maya", "Nahua", "Zapotec", "Mixtec", "Otomi", "Totonac", "Purepecha",
        "Mazahua", "Mazatec", "Huastec", "Chol", "Tzeltal", "Tzotzil",
        "Garifuna", "Miskito", "Kuna", "Ngäbe", "Taino", "Kalinago",
        "Mam", "Kʼicheʼ", "Qʼeqchiʼ", "Kaqchikel",
    ),
    "Indigenous peoples of South America": (
        "Vedda", "Quechua", "Aymara", "Guarani", "Mapuche", "Wayuu", "Nasa", "Embera",
        "Kichwa", "Shuar", "Aimara", "Ashaninka", "Shipibo", "Awajun",
        "Ticuna", "Yanomami", "Guajiro", "Pemon", "Warao",
    ),
    "Afro-descendant peoples of the Americas": (
        "Raizal", "Palenquero", "Maroon", "Creole",
        "Afro-Colombian", "Quilombola", "Saramaccan", "Ndyuka",
    ),
}

# The census categories. Each is a tier-2 node in its own right, a sibling of
# the people families in the same ancestry -- never a parent of them.
ETHNIC_CENSUS: dict[str, tuple[str, ...]] = {
    "White or European (census category)": (
        "White", "White (non-Hispanic)", "White British", "White Irish",
        "White Other", "White European", "Caucasian", "European",
        "Other White", "Other European", "Branca",
        "White: English, Welsh, Scottish, Northern Irish or British",
        "White: Irish", "White: Other White", "White: Roma",
        "White: Gypsy or Irish Traveller", "White Irish Traveller",
    ),
    "Black or African (census category)": (
        "Black", "Black or African American (non-Hispanic)", "Black African",
        "Black Caribbean", "Black or African American", "African",
        "Afro-descendant", "Black British", "Black or Black Irish", "Preta",
        "Black, Black British, Black Welsh, Caribbean or African: African",
        "Black, Black British, Black Welsh, Caribbean or African: Caribbean",
        "Black, Black British, Black Welsh, Caribbean or African: Other Black",
        "African/Black", "Black/African", "Afro", "Negro",
    ),
    "Asian (census category)": (
        "Asian", "Asian (non-Hispanic)", "Asian or Asian British",
        "Asian or Asian Irish", "South Asian", "Southeast Asian",
        "East Asian", "West Asian", "Other Asian", "Amarela",
        "Indian/Asian", "East Indian", "Asian/Indian",
        "Asian, Asian British or Asian Welsh: Bangladeshi",
        "Asian, Asian British or Asian Welsh: Chinese",
        "Asian, Asian British or Asian Welsh: Indian",
        "Asian, Asian British or Asian Welsh: Other Asian",
        "Asian, Asian British or Asian Welsh: Pakistani",
    ),
    "Indigenous (census category)": (
        "Indigenous", "Indigenous People", "Indigenous Peoples", "Amerindian",
        "American Indian and Alaska Native (non-Hispanic)", "Indígena",
        "Native American", "Indigenous and Alaska native",
        "American Indian and Alaska native", "Native",
    ),
    "Pacific Islander (census category)": (
        "Pacific Islander",
        "Native Hawaiian and Other Pacific Islander (non-Hispanic)",
    ),
    "Mixed or multiple (census category)": (
        "Pardo", "Mestizo", "Coloured", "Mixed", "Mixed or multiple",
        "Two or more races (non-Hispanic)", "Two or more races",
        "mixed", "Mixed race", "Multiracial", "Mulatto",
        "Mixed or Multiple ethnic groups", "Multiple visible minorities",
        "Mixed or Multiple ethnic groups: Other Mixed or Multiple ethnic groups",
        "Mixed or Multiple ethnic groups: White and Asian",
        "Mixed or Multiple ethnic groups: White and Black African",
        "Mixed or Multiple ethnic groups: White and Black Caribbean",
        "Burgher", "Eurasian", "Mulatto", "Zambo", "Castizo",
    ),
    "Hispanic or Latino (census category)": (
        "Hispanic or Latino", "Hispanic or Latino (any race)",
        "Latin American", "Hispanic",
    ),
    "Middle Eastern or North African (census category)": (
        "Middle Eastern or North African", "Other ethnic group: Arab",
        "Middle Eastern/Latin American/African",
    ),
}

# The answers that name a country rather than a people. Where the country has
# one clear ancestry the group is filed under it; the settler nations, whose
# populations are themselves multi-origin and whose "American" or "Australian"
# answer means "nothing further to add", are kept apart and said to be that.
ETHNIC_NATIONALITY: dict[str, tuple[str, ...]] = {
    "Settler-nation identities": (
        "American", "Canadian", "Australian", "New Zealander", "Brazilian",
        "Mexican", "Cuban", "Argentine", "Singaporean", "South African",
    ),
    "Other national identities": (
        "Belgian", "Yugoslavian", "Sri Lankan", "Iranian national",
        "Nigerian", "Kenyan", "Cameroonian", "Malian", "Senegalese",
        "Congolese (Kinshasa)", "Congolese (Brazzaville)", "Chadian",
        "Pakistani", "Indian", "Bangladeshi", "Sri Lankan", "Nepalese",
        "Burmese", "Thai", "Indonesian", "Filipino national",
    ),
}

# Tier 1. Ancestry is the axis that can carry an ethnonym and a census race
# category at once, which is what makes the map cohere: Yoruba, "Black or
# African American" and Nigerian all land in one colour band.
ETHNIC_ANCESTRY: dict[str, tuple[str, ...]] = {
    "African ancestry": (
        "Bantu peoples", "West African peoples", "Nilotic peoples",
        "Horn of Africa peoples", "Central African peoples",
        "Malagasy peoples", "Khoisan peoples",
        "Afro-descendant peoples of the Americas",
        "Black or African (census category)",
    ),
    "European ancestry": (
        "Germanic peoples", "Romance peoples", "Slavic peoples",
        "Baltic peoples", "Greek and Albanian peoples",
        "Finnic and Ugric peoples", "Basque peoples",
        "White or European (census category)",
    ),
    "Middle Eastern and North African ancestry": (
        "Arab peoples", "Iranian peoples", "Berber peoples",
        "Caucasian peoples", "Armenian peoples",
        "Assyrian and Aramean peoples",
        "Middle Eastern or North African (census category)",
    ),
    "Turkic and Central Asian ancestry": ("Turkic peoples",),
    "South Asian ancestry": (
        "Indo-Aryan peoples", "Dravidian peoples",
        "Himalayan and Tibeto-Burman peoples", "Munda peoples",
    ),
    "East and Southeast Asian ancestry": (
        "Han and Sinitic peoples", "Japanese peoples", "Korean peoples",
        "Mongolic and Siberian peoples", "Mainland Southeast Asian peoples",
        "Malay and Indonesian peoples", "Philippine peoples",
        "Asian (census category)",
    ),
    "Indigenous American ancestry": (
        "Indigenous peoples of North America",
        "Indigenous peoples of Mesoamerica and the Caribbean",
        "Indigenous peoples of South America",
        "Indigenous (census category)",
    ),
    "Pacific ancestry": (
        "Polynesian peoples", "Melanesian peoples", "Micronesian peoples",
        "Aboriginal and Torres Strait Islander peoples",
        "Pacific Islander (census category)",
    ),
    "Mixed or multiple ancestry": (
        "Mixed or multiple (census category)",
        "Hispanic or Latino (census category)",
    ),
    "Stated as a nationality": ("Settler-nation identities",
                                "Other national identities"),
    # Two peoples whose placement under any single ancestry would be an
    # argument rather than a fact. They stand alone -- and the communities
    # under each are the ones a register counts separately, which is a
    # division within the people and not a doubt about it.
    "Jewish": ("Mountain Jew", "Mountain Jewish", "Bukharan Jew",
               "Georgian Jew", "Georgian Jewish", "Krymchak",
               "Ashkenazi", "Sephardi"),
    "Romani": ("Central Asian Romani", "Kalderash"),
    # The answers that name no ancestry at all. They are kept, because a bar
    # that quietly drops a fifth of a population is the failure this project
    # cares about most, and they are kept apart, because a map that colours a
    # district for "not stated" has answered the wrong question.
    "Other or not stated ancestry": ("Unclassified ethnicity answers",),
}

ETHNIC_RESIDUALS: tuple[str, ...] = (
    "Other ethnicity", "Ethnicity not stated", "No ethnic group",
    "No ethnicity data", "Other Central Africa",
    "Unknown ethnicity", "Not declared", "Not classified", "No ethnicity",
    "Some other race (non-Hispanic)", "Some other race", "Other",
    "Regional affiliation", "Religious affiliation given as ethnicity",
    "Not elsewhere included", "Ethnicity not reported", "Not stated",
    "Other local ethnicity", "Other non-local ethnicity",
    "Other foreign ethnicity", "Other ethnic group: Any other ethnic group",
    "Visible minority, n.i.e.", "Not a visible minority", "Foreigner",
    "Non-Malaysian citizen", "Other (Malaysian citizen)",
    # Mexico's second question, and its negative answer: "not Afro-descendant"
    # is the absence of one identification rather than the presence of
    # another, and colouring 2,484 municipalities for it would say nothing.
    "Not Afro-descendant",
    "Other Africa", "Other West Africa", "Other Asian", "Other European",
    # The drawer each census keeps for everyone it did not name, in the
    # words it keeps it in.
    "Other ethnic group", "Other ethnicities", "Other tribe",
    "No tribe data", "Other race", "Race not stated", "Other nationalities",
    "ethnic minorities", "other minorities", "other and unspecified",
    "other or unspecified", "undeclared or unknown", "none or unspecified",
    "unspecified smaller ethnic groups", "no ethnic affiliation data available",
    "other Liberian ethnic group", "other Togolese", "and other", "none",
    # A person counted as not being from here, which says nothing about
    # where they are from.
    "Foreign", "foreign", "foreign population", "non-Gambian",
    "foreign/other ethnic group",
    # A religion written into the ethnicity question. The mirror of
    # "Scheduled Castes" in the religion tree: an answer to a different
    # question, kept and kept apart.
    "Orthodox (written as ethnicity)",
    # Cape Verde and Sao Tome ask what a person has been treated differently
    # for. Every answer names a ground -- age, class, religion, where they
    # come from -- and none names an ancestry.
    "Related to age", "Related to class", "Related to gender",
    "Related to regional origin (badio/sampadjudo)",
    "Related to occupation", "Related to race", "Related to religion",
    "Related to political affiliation",
    "Related to a regional origin (Foros, Angulares, Cape Verdeans, Principienses)",
)


# Whole blocks of the tail come from one country's classification and share a
# root word: the Philippines publishes some three hundred groups of which most
# are a named people plus a locality ("Kalinga-Lubuagan", "Manobo-Blit"), and
# Ethiopia prefixes every one of its with "Ethnic group". Listing each by hand
# would be four hundred lines that say the same thing four hundred times, so
# these say it once. A pattern only ever fires where no exact name matched.
ETHNIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Philippine peoples", (
        "Tagabawa", "Dibabawon", "Obu-Manuvu", "Manuvu", "Iwak",
        "Lambanguian", "Kailawan", "Kaylawan", "Mangguangan",
        "Manobo", "Mangyan", "Kalinga", "Tinguian", "Itneg", "Aeta", "Ayta",
        "Agta", "Bukidnon", "Subanen", "Subanon", "Bagobo", "Tagbanua",
        "Dumagat", "Palawan-o", "Kankanaey", "Ifugao", "Ibaloy", "Isneg",
        "Isnag", "Kalanguya", "Balangao", "Bontok", "Tuwali", "Ayangan",
        "Higaonon", "Mandaya", "Mansaka", "Blaan", "T'boli", "Tboli",
        "Teduray", "T'duray", "Talaandig", "Tagakaulo", "Matigsalog",
        "Banwaon", "Umayamnon", "Tigwahanon", "Langilan", "Karulano",
        "Applai", "Chavacano", "Caviteño", "Cotabateño", "Davaweño",
        "Guiangan", "Iranun", "Mamanwa", "Sama", "Badjao", "Yakan",
        "Panay Bukidnon", "Ati", "Ata", "Alta", "Bago", "Baliwon",
        "Diangan", "Eskaya", "Ibukid", "Kagan", "Kalagan", "Kamiguin",
        "Karao", "Kaunana", "Magahats", "Magkunana", "Malaueg", "Parananum",
        "Pan-Ayanon", "Ubo", "Yapayao", "Kabihug", "Manide", "Talaingod",
        "Calinga", "Tingguian", "Bugkalot", "Ilongot", "Egongot",
        "Abelling", "Aberling", "Batak", "Ibatan", "Cuyonen", "Cuyunon",
        "Agutaynen", "Cagayanen", "Romblomanon", "Surigaonon",
    )),
    ("Horn of Africa peoples", ("Ethnic group",)),
    ("Central African peoples", ("Zande", "Yakoma", "Ngbaka", "Gbaya",
                                 "Banda", "Mandjia", "Sara", "Mbum",
                                 "Central Africa")),
    ("Mongolic and Siberian peoples", ("Chuvan", "Kamchadal", "Itelmen",
                                       "Enets", "Yukaghir", "Orok")),
    ("Turkic peoples", ("Tatar", "Kyrgyz", "Kazakh", "Uzbek", "Turkmen")),
    ("Indo-Aryan peoples", ("Brahman", "Chhetri", "Kshetri", "Thakuri",
                            "Dasnami", "Bhujel")),
)

# Groups a pattern would catch and must not. "Ethnic group Other Foreigners"
# and "Ethnic group Sudanese" are Ethiopia's rows for people who are not
# Ethiopian, so they are not Horn of Africa peoples; "Ethnic group From
# different parents" is a mixed answer.
ETHNIC_PATTERN_EXCEPTIONS: dict[str, str] = {
    "Ethnic group Other Foreigners": "Other national identities",
    "Ethnic group Sudanese": "Other national identities",
    "Ethnic group Eritrean": "Other national identities",
    "Ethnic group Kenyan": "Other national identities",
    "Ethnic group Somalian": "Other national identities",
    "Ethnic group Somalie": "Horn of Africa peoples",
    "Ethnic group Other Ethiopian National": "Other national identities",
    "Ethnic group From different parents": "Mixed or multiple (census category)",
}


# ---------------------------------------------------------------------------
# Turning the tables into a tree
# ---------------------------------------------------------------------------

def _invert(table: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """{parent: (children,)} -> {child: parent}, refusing a child twice.

    A name under two parents would make its share depend on which branch the
    reader came down, so it is a mistake to catch here rather than a subtlety
    to resolve at read time.
    """
    out: dict[str, str] = {}
    for parent, kids in table.items():
        for kid in kids:
            if kid == parent:
                continue                      # a family that is its own branch
            if kid in out and out[kid] != parent:
                raise ValueError(
                    f"{kid!r} is under both {out[kid]!r} and {parent!r}")
            out[kid] = parent
    return out


# A name the tables already carry, spelled the way another office spells it.
#
# These are not groupings and they add nothing to the tree: each says that two
# strings are one group, so the right-hand name's placement is the left-hand
# name's placement. They exist because the rules above work on the shape of a
# name -- accents, brackets, slashes, a kind word -- and nothing in the shape
# of "Maure" says it is the French for "Moor", or that Namibia's "Wambo" and
# Angola's "Ovambo" are the same people. Only a reader who knows the two
# literatures can say that, so it is said here, once, by hand.
#
# The test of an entry is that a statistical office would accept it as a
# translation rather than a classification. "Peulh" is French for Fula and
# "Kinh" is what Vietnam calls the Vietnamese; neither decides anything. A
# name whose identity is genuinely contested does not belong here -- it
# belongs in the tree with its own node.
# Names the families above did not carry, with the family each belongs to.
#
# Everything here is a language or a people a source actually reports and the
# tree had no row for -- not a new grouping, just a member of an existing one.
# They are separated from the family tables only so that what was added to
# answer a gap stays legible as such.
LANGUAGE_EXTRA: dict[str, tuple[str, ...]] = {
    "Bantu languages": (
        "Ovambo", "Herero", "Kwangali", "Lozi", "Yeyi", "Mbukushu",
        "Ngombe", "Teke", "Punu", "Kongo", "Luba", "Bemba", "Tonga",
        "Chokwe", "Ngangela", "Kwanyama", "Nyaneka", "Zaramo", "Korekore",
        "Umbundu", "Kimbundu",
        # Southern Africa and the Zambezi, where the language a census names
        # is the people's own name for it.
        "Bisa", "Lala", "Lamba", "Lenje", "Mambwe", "Namwanga", "Nsenga",
        "Kaonde", "Lunda", "Luvale", "Nyanja", "Ila", "Kunda", "Tabwa",
        "Nkoya", "Mbunda", "Senga", "Barwe", "Kalanga", "Nambya",
        "Shangani", "Ndau", "Zezuru", "Manyika", "Nyungwe", "Ronga",
        "Chopi", "Gitonga", "Koti", "Mwani", "Lomwe", "Tswa", "Chuwabo",
        "Chuabo", "Ndonga", "Humbi", "Fiote", "Kavango languages",
        "Zambezi languages", "Subia", "Kgalagadi",
        # Cameroon, the Congo basin and the Central African Republic. The Aka
        # of the Lobaye speak a Bantu language whatever else is said about
        # them, and Kaka and Pomo are its neighbours in the same zone.
        "Aka", "Kaka", "Pomo", "Bomitaba", "Kele", "Tsogho", "Nzebi",
        "Myene", "Duma", "Makaa", "Mbochi", "Sangha", "Eshira", "Bakweri",
        "Bafia", "Bamum", "Batanga", "Yaka",
    ),
    "Mande languages": ("Mandingo", "Dogon",
                        # Mali and Burkina Faso.
                        "Khassonke", "Samogo", "Dafing", "Marka", "Bissa",
                        "Bobo"),
    "Indo-Aryan languages": (
        "Halabi", "Avadhi",
        # Nepal's Indo-Aryan mother tongues. The far-western ones are Nepali
        # as a district speaks it -- Baitadeli is the speech of Baitadi,
        # Bajhangi of Bajhang -- and sit beside Doteli and Achhami, which the
        # table already carries; the Tarai ones are the Maithili and Bhojpuri
        # belt.
        "Baitadeli", "Bajhangi", "Bajureli", "Dailekhi", "Darchuleli",
        "Dadeldhuri", "Jumli", "Angika", "Sadri", "Ranatharu", "Tajpuriya",
        "Rajbanshi", "Rajbansi", "Kumal", "Danuwar", "Darai", "Bote",
        "Sonaha", "Kewarat", "Marwadi", "Marwari",
        # Karnali's Khas, which Jumla and Kalikot report beside Nepali
        # rather than as another word for it.
        "Khash",
        # Pakistan and the Dardic north.
        "Lahnda", "Shina", "Pashai",
    ),
    "Nilo-Saharan languages": ("Songhai", "Zarma", "Kanuri", "Fur", "Gula"),
    "Gur languages": ("Gurma", "Bwamu", "Lobi", "Dagara",
                      "Gurunsi", "Minianka", "Kassena", "Konkomba"),
    # Central African Republic: the Ubangian languages its census lists, which
    # the tree reached only through the "Banda" and "Gbaya" cover terms.
    "Adamawa-Ubangi languages": (
        "Yakoma", "Nzakara", "Gbanziri", "Langbashe", "Sere", "Mandjia",
        "Gbanu", "Bokoto", "Suma", "Kare", "Dakpa", "Langba", "Ndi",
        "Tongo", "Gbaguiri", "Mboundjia", "Issongo", "Bofi", "Gbadok",
        "Ngbandjiri", "Bogongo", "Ali", "Pana", "Kaba", "Yangere",
        "Nbugu", "Binga", "Mbanza", "Banziri",
        # The rest of the same census's Ubangian list.
        "Buraka", "Kpatili", "Kpala", "Kari", "Monzombo", "Mondjombo",
    ),
    # Ethiopia: the Omotic languages of the south-west, which the census
    # writes with the Amharic language suffix -gna as often as not.
    "Omotic languages": (
        "Aari", "Melo", "Chara", "Oyda", "Gofa", "Yemsa", "Dime",
        "Shekkacho", "Dizin", "Sheko", "Koorete", "Nayi", "Bambassi",
        "Zayse-Zergulla", "Kachama-Ganjule", "Boro", "Basketo", "Male",
        "Dawro", "Gamo", "Wolaytta", "Hamer-Banna",
        # Konta, an Ometo variety, and the Karo of the lower Omo, who are
        # South Omotic like the Hamer beside them. Written "Karo
        # (Ethiopia)" in full, because Karo is also a Batak people.
        "Konta", "Karo (Ethiopia)",
    ),
    "Cushitic languages": ("Alaba-K'abeena", "Qebena", "Werji", "Burji",
                           # Timbaaro, counted with Kambaata beside it.
                           "Timbara", "Timbaro"),
    # The Peruvian Amazon, which the census names by the people.
    "Indigenous languages of the Americas": ("Ashaninka", "Awajun",
                                             "Aguaruna"),
    # Russia's federal subjects. The Andic and Tsezic languages of Dagestan,
    # which the Russian census lists one by one beside Avar: every one of
    # them is Nakh-Dagestanian, and several have fewer than a thousand
    # speakers, which is why no general table carries them.
    "Northeast Caucasian languages": (
        "Dagestani", "Tat", "Tsez", "Bezhta", "Hinukh", "Hunzib", "Khwarshi",
        "Akhvakh", "Bagvalal", "Botlikh", "Chamalal", "Godoberi", "Karata",
        "Tindi", "Archi",
    ),
    # Siberia and the Altai, likewise: each of these is a Turkic language
    # that Russia publishes separately from the Altai proper.
    "Turkic languages": ("Teleut", "Kumandin", "Chelkan", "Tubalar",
                         "Chulym", "Soyot", "Tofalar", "Tofa"),
    "Uralic languages": ("Votic", "Nganasan", "Enets", "Selkup",
                         "Livonian"),
    "Sinitic languages": ("Dungan",),
    # North-east India and the Himalaya.
    "Tibeto-Burman languages": (
        "Bhotia", "Adi", "Mishmi", "Thado", "Kinnauri", "Sharchopkha",
        "Nissi", "Dafla", "Nyishi", "Kuki-Chin", "Karenic",
        # Nagaland and Assam, whose census lists each language separately.
        "Angami", "Ao", "Konyak", "Phom", "Sangtam", "Dimasa", "Lotha",
        "Sema", "Rengma", "Chang", "Khiamniungan", "Yimchungre", "Zeliang",
        "Chakru", "Chokri", "Lakher", "Mao", "Kabui", "Wancho", "Tangkhul",
        # The rest of the north-east, as the Indian census spells it.
        "Tripuri", "Rabha", "Kuki", "Halam", "Hmar", "Karbi", "Mikir",
        "Karbi/Mikir", "Paite", "Vaiphei", "Deori", "Koch", "Monpa", "Pawi",
        "Chakhesang", "Liangmei", "Gangte", "Zemi", "Khezha", "Kom",
        "Nocte", "Tangsa", "Zou", "Anal", "Maram", "Maring", "Pochury",
        "Mishing", "Miri", "Lalung", "Lahauli", "Mogh", "Ladakhi", "Balti",
        # Nepal's Kiranti (Rai) languages, which the census lists one by one
        # where a general table writes "Rai": every one of them is a
        # Tibeto-Burman language of the eastern hills.
        "Bantawa", "Chamling", "Thulung", "Kulung", "Sampang", "Wambule",
        "Khaling", "Bahing", "Bayung", "Dumi", "Yakkha", "Nachhiring",
        "Koyee", "Mewahang", "Dungmali", "Athpahariya", "Aathpahariya",
        "Chhintang", "Lungkhim", "Tilung", "Belhare", "Lohorung", "Puma",
        "Jerung", "Jero", "Phangduwali", "Chhiling", "Chhulung", "Yamphu",
        "Yamphe", "Hayu", "Vayu", "Sam", "Dungmali",
        # And its Tibetic and other Tibeto-Burman mother tongues.
        "Ghale", "Thami", "Bhote", "Hyolmo", "Yholmo", "Jirel", "Lhopa",
        "Lhomi", "Manange", "Nar-Phu", "Nubri", "Chum", "Lowa", "Walung",
        "Kagate", "Surel", "Chhantyal", "Chhantel", "Dura", "Raji", "Raute",
        "Meche", "Dhimal", "Byansi", "Baram", "Balkura", "Bhujel",
        "Topkegola", "Mugali", "Karmarong", "Tichhurong",
        "Tichhurong Poike", "Baragunwa",
        "Dolpali", "Dolpo", "Pahari",
    ),
    "Dravidian languages": ("Kui", "Kondh", "Khond", "Malto", "Koya",
                            "Kolami", "Kodagu", "Coorgi", "Konda", "Parji",
                            "Oraon", "Kudukh"),
    # Timor-Leste, whose census names every language of the country. The
    # Austronesian ones and the Papuan ones are a settled split.
    "Malayo-Polynesian languages": (
        "Tetun", "Tetun Prasa", "Tetun Terik", "Baikenu", "Galoli", "Idate",
        "Kemak", "Mambai", "Midiki", "Naueti", "Tokodede", "Waima'a",
        "Philippine languages", "Sasak", "Bantenese",
    ),
    "Papuan languages": ("Bunak", "Fataluku", "Makasai", "Makalero"),
    "Oceanic languages": ("Futunian", "Marquesan", "Paumotu", "Tuamotuan",
                          "Nauruan"),
    "Creole languages": ("Norfolk", "Angolar", "Forro", "Lunguie", "Haitian"),
    # The band the US Virgin Islands writes, filed where the ACS's "Spanish
    # or Spanish Creole" and "French, Haitian, or Cajun" already sit.
    "Romance languages": ("Aragonese", "French or French Creole"),
    "Germanic languages": ("Limburgish",
                           "Limburgish, Limburgan, Limburger"),
    "Iranian languages": ("Ezidian", "Ezdiki"),
    "Semitic languages": ("Hassaniya",),
    "Surmic and Koman languages": ("Majang", "Messengo", "Fadashi"),
    # Two small families with no relative anywhere else in this table.
    # Yukaghir has two members and no accepted wider grouping; Yug is Ket's
    # only relative, and Ket is already here. The node says exactly that --
    # a language this map can place in no family -- and not that either has
    # been shown to be alone in the world.
    "Language isolates": ("Yukaghir", "Yug"),
    "Austroasiatic languages": ("Khmou", "Makong"),
}

ETHNIC_EXTRA: dict[str, tuple[str, ...]] = {
    "West African peoples": (
        "Gurma", "Mandingo", "Songhai", "Themne", "Dogon", "Toucouleur",
        # Ghana, Burkina Faso, Togo and Benin.
        "Gonja", "Frafra", "Dagaaba", "Aja", "Marka", "Senufo", "Kru",
        "Tem", "Kotokoli", "Moba",
        # Liberia and Nigeria.
        "Gola", "Loma", "Grebo", "Idoma", "Bura", "Efik", "Urhobo",
        "Igala", "Tarok",
        # The rest of the Volta basin, where each census writes the group
        # and, as often as not, its neighbours' name for it beside it.
        "Guan", "Kusasi", "Konkomba", "Konkonba", "Wale", "Waala",
        "Akebu", "Akposso", "Ikposso, Akposso", "Akposso/Akebu", "Ife",
        "Ana", "Ana-Ife", "Ouatchi", "Mina", "Gen", "Tchamba", "Anufo",
        "Tchokossi, Anoufom", "Ngangam", "Ngam-Gam", "Nawdem",
        "Nawdem, Losso", "Bassar", "N\u2019Tcha, Bassar", "Lama, Lamba",
        "Lopka", "Yoa", "Otammari", "Otamari", "Dendi",
        "Birifor", "Samo", "Kassena", "Goin", "Bwaba", "Bwa", "Yanan",
        # Mali, Guinea, Senegal, the Gambia and Sierra Leone.
        "Khassonke", "Kakolo", "Somono", "Bozo", "Minianka", "Dafing",
        "Samogo", "Bainouk", "Jahanka", "Yalunka", "Koranko", "Korankoh",
        "Aku", "Koroninka", "Sub-Saharan Mauritanians",
        # Liberia, whose census names sixteen peoples.
        "Mano", "Gbandi", "Belle", "Dei", "Dey", "Sapo", "Krio",
        # Nigeria.
        "Ebira", "Oron", "Bette", "Birom", "Etulo", "Ikwere", "Isoko",
        "Kalabari",
        # Cote d'Ivoire publishes its peoples by language group, and Benin
        # spells Otammari a third way.
        "Gur", "Voltaique", "Lagunaire", "Ottamari", "Akebou",
        # A label that says "and related" covers more than the people it
        # names, so it is listed beside that people and not under it.
        "Dendi and related", "Ottamari and related", "Yoa-Lokpa and related",
        "Koua Lagunaire", "Mina, Guen",
    ),
    "Bantu peoples": (
        "Ovambo", "Ngombe", "Teke", "Punu", "Mokoena", "Herero",
        "Zaramo", "Korekore", "Chokwe", "Ngangela", "Nyaneka",
        # The roots behind the prefixed forms the censuses print. Listed bare
        # so that "Ciyao", "Mmakuwa" and "Yao" are one group, not three.
        "Yao", "Ganda", "Makua", "Bena", "Tswa", "Sambaa", "Fokeng",
        "Kgatla", "Kalanga", "Lete", "Ha", "Nyakyusa", "Luguru", "Fipa",
        "Nyaturu", "Manyika", "Karanga", "Shangaan", "Changana", "Lomwe",
        # Democratic Republic of the Congo.
        "Ntandu", "Yombe", "Yansi", "Songe", "Sengele", "Lega", "Nande",
        "Tetela", "Shi", "Poke", "Budu", "Mbosi", "Kanyok",
        # Gabon and the Republic of the Congo.
        "Mbete", "Nzebi", "Kota", "Kalonji", "Yaka",
        # The Democratic Republic of the Congo's own list of tribes, which
        # runs to a hundred names and is Bantu almost all the way down; the
        # Ubangian and Central Sudanic peoples of its north-east are filed
        # with the Central African peoples instead.
        "Babango", "Baboa", "Boa", "Bakwa Dishi", "Bakwa Mulumba",
        "Bakwanga", "Bangando", "Bangobango", "Bembe", "Boma", "Budza",
        "Bushoong", "Ekonda", "Fuliiru", "Havu", "Hemba", "Hunde",
        "Kaonde", "Kete", "Kundu", "Kusu", "Kutshu", "Kwese", "Lele",
        "Lemfu", "Lengola", "Libinja", "Lokele", "Lombo", "Luntu",
        "Manyanga", "Mbala", "Mbata", "Mboma", "Mbunda", "Mpama", "Kumu",
        "Ndengese", "Ndibu", "Ngengele", "Ngongo", "Ntomba", "Nunu",
        "Nyanga", "Pelende", "Phende", "Pende", "Bira", "Sakata", "Sanga",
        "Songola", "Suku", "Taabwa", "Tabwa", "Vira", "Zela",
        # Zambia, Malawi and Mozambique.
        "Bisa", "Lala", "Lamba", "Lenje", "Mambwe", "Namwanga", "Nsenga",
        "Ila", "Kunda", "Lungu", "Bwile", "Chishinga", "Ngumbo", "Soli",
        "Tokaleya", "Nkoya", "Senga", "Nyanja", "Lambya", "Nkhonde",
        "Mang\u2019anja", "Khokhola", "Ndali", "Chuabo", "Chuwabo",
        "Chope", "Nyungwe", "Ronga", "Tonga", "Bitonga",
        # Tanzania and Uganda write the person, not the people: "Mzigua" is
        # one Zigua, "Musoga" one Soga. These are the roots the class-prefix
        # rule needs to take those apart.
        "Rangi", "Zigua", "Jita", "Kerewe", "Kaguru", "Nyambo", "Pogoro",
        "Shubi", "Ndendeule", "Pemba", "Kinga", "Nyiramba", "Pare",
        "Kurya", "Kuria", "Digo", "Kwere", "Mwera", "Ngindo", "Safwa",
        "Mbugwe", "Nguu", "Ndengereko", "Manyema", "Nyika",
        "Soga", "Kiga", "Nyankole", "Nyarwanda", "Gisu", "Gishu", "Gwere",
        "Nyole", "Nyoro", "Samia", "Konzo", "Khonzo", "Tooro", "Fumbira",
        # Lesotho and Botswana ask for the clan, which is the same root
        # again with Mo- or Le- in front of it.
        "Taung", "Tloung", "Tlokoa", "Tlokwa", "Kholokoe", "Lekholokoe",
        "Khoakhoa", "Lekhoakhoa", "Hlakoana", "Phuthi", "Phuthing",
        "Lephuthing", "Tsoeneng", "Thepu", "Nareng", "Kubung", "Mosiea",
        "Kwena", "Ngwato", "Ngwaketse", "Rolong", "Tswapong", "Kgalagadi",
        "Hurutshe", "Khurutshe", "Yeyi", "Mbukushu", "Birwa", "Mmirwa",
        # Namibia, Angola and Zimbabwe.
        "Subia", "Zezuru", "Kwanyama", "Humbi", "Fiote", "Luvale",
        "Lunda", "Ndau", "Nambya",
        # Cameroon, Gabon and the Republic of the Congo. The Grassfields
        # peoples are Bantoid rather than narrow Bantu, and are filed here
        # for the same reason Bamileke already is.
        "Bafia", "Bafut", "Balikumbat", "Bamoun", "Bamum", "Bangwa",
        "Batanga", "Bayangi", "Bakweri", "Mbo", "Nso", "Njikwa", "Mbam",
        "Mbamois", "Grassfields", "Sawa", "Kako", "Meka", "Makaa",
        "Myene", "Kele", "Tsogho", "Okande", "Shira", "Eshira", "Echira",
        "Duma", "Mbochi", "Sangha", "Nzabi",
        # Equatorial Guinea's coast and Mozambique's.
        "Ndowe", "Bisio", "Ekoti", "Mwani", "Khatla", "Shira-Punu'Vii",
        # Printed beside Chokwe and Lomwe by the censuses that use them,
        # so each is a row of its own and not another spelling.
        "Tshoko", "Lomue",
    ),
    "Mainland Southeast Asian peoples": (
        "Vietnamese",
        # Laos names its peoples by language: Katang and Makong are Katuic,
        # Khmu is Khmuic, Phu Thai and Lue are Tai.
        "Katong", "Katang", "Khmou", "Khmu", "Makong", "Phouthay",
        "Phu Thai", "Lue", "Tai",
    ),
    "Malagasy peoples": ("Sihanaka", "Masikoro", "Antesaka", "Antandroy",
                         # The rest of Madagascar's eighteen.
                         "Antanosy", "Antemoro", "Antembahoaka",
                         "Antakarana", "Antefasy", "Bara", "Mahafaly",
                         "Bezanozano", "Vezo"),
    "Nilotic peoples": ("Teso", "Luo",
                        # Uganda's Nilotic peoples beside its Bantu ones.
                        "Adhola", "Japhadhola", "Kumam", "Sabiny", "Sabini"),
    "Mongolic and Siberian peoples": (
        "Khalkha",
        # Mongolia's own aimags, and the peoples of the Russian far east
        # that the census counts in the hundreds.
        "Bayad", "Buriad", "Dariganga", "Durvud", "Zakhchin",
        "Ulch", "Uilta", "Negidal", "Oroch", "Kerek",
    ),
    "Central African peoples": (
        "Oubanguiens",
        # Chad's census names each group with its neighbours' names beside
        # it; the Sahel and the Chad basin are what this node covers.
        "Baguirmi", "Barma", "Bidiyo", "Bulala", "Dadjo", "Gabri",
        "Gorane", "Tubu", "Zime", "Peve", "Marba", "Musgum", "Mousgoum",
        "Tama", "Maba", "Masalit", "Marba/Lele/Mesme",
        "Mesmedje/Massalat/Kadjakse",
        # Northern Cameroon, whose peoples are Adamawa and Chadic rather
        # than Bantu, and the Ubangian and Central Sudanic peoples of the
        # Congo's north-east.
        "Dii", "Biu-Mandara", "Mayogo", "Mba", "Mbandja", "Mono",
        "Lendu", "Logo", "Mamvu", "Mangbetu",
        # The forest peoples, whom a census names by the cover term.
        "Pygmy", "Autochtones",
    ),
    "Himalayan and Tibeto-Burman peoples": (
        "Ngalop", "Sharchop",
        # Nepal's janajati: the Kiranti (Rai) groups of the eastern hills
        # and the Bhote (Tibetan-descended) groups of the north, which the
        # census lists one by one where a summary writes "Rai" or "Bhote".
        "Bantawa", "Chamling", "Kulung", "Thulung", "Yakkha", "Sampang",
        "Nachhiring", "Khaling", "Bahing", "Mewahang", "Yamphu",
        "Aathpahariya", "Athpahariya", "Loharung", "Lohorung", "Dungmali",
        "Ghale", "Thami", "Bhote", "Dolpo", "Lhopa", "Lhomi", "Jirel",
        "Hyolmo", "Yholmopa", "Walung", "Topkegola", "Karmarong",
        "Mugal", "Mugum", "Surel", "Dura", "Raji", "Raute", "Meche",
        "Dhimal", "Byasi", "Sauka", "Baram", "Baramu",
        "Chhantyal", "Chhantel", "Hayu", "Chumba", "Nubri", "Pahari",
        "Pun",
        # Myanmar's national races, which are Tibeto-Burman unless the
        # census says otherwise.
        "Pa'o", "Intha", "Kayan", "Taungyo", "Kadu", "Kanan",
        # North-east India.
        "Tripuri", "Rabha", "Deori", "Hmar", "Paite", "Vaiphei",
    ),
    "Arab peoples": ("Iraki", "Rashaida", "Sahraoui", "Sahrawi"),
    # Suriname's census names the community by where its ancestors came from.
    "Indo-Aryan peoples": (
        "Hindustani",
        # Nepal's Tarai and hill castes, which speak Maithili, Bhojpuri,
        # Awadhi or Nepali. The census lists them beside Teli, Kurmi and
        # Chamar, which the table already carries, and they are the same
        # kind of answer: a caste of the Indo-Aryan-speaking plains.
        "Sonar", "Hajam", "Thakur", "Hajam/Thakur", "Kalwar", "Baniyan",
        "Gaine", "Kayastha", "Lohar", "Kathabaniyan", "Rajput", "Sundi",
        "Badi", "Haluwai", "Khawas", "Marwadi", "Musahar", "Nuniya",
        "Kewat", "Badhaee", "Badhee", "Baraee", "Dhobi", "Kanu",
        "Rauniyar", "Kumhar", "Bin", "Dom", "Gaderi", "Bhediyar", "Amat",
        "Bantar", "Sardar", "Khatwe", "Dhunia", "Rajbhar", "Bhumihar",
        "Khatik", "Lodh", "Patharkatt", "Kushwadiya", "Sarbaria", "Kori",
        "Dev", "Rajdhob", "Chidimar", "Dhandi", "Dhankar", "Dharikar",
        "Halkhor", "Beldar", "Natuwa", "Kahar", "Tatma", "Tatwa",
        "Kamar", "Kalwar", "Rajbansi", "Rajbanshi", "Tajpuriya", "Gangai",
        "Darai", "Bote", "Kumal", "Danuwar", "Bangali", "Ranatharu",
        "Kewarat", "Chai", "Khulaut",
        # Pakistan's Urdu-speaking migrants from India.
        "Muhajirs", "Muhajir",
    ),
    # Small territories whose census asks for the island, not an ancestry.
    "Other national identities": (
        "Cayman Islander", "Curacaoan", "Falkland Islander", "Gibraltarian",
        "Greenlandic", "Guernsey", "Jersey", "Manx", "Bermudian",
        "Saint Helenian", "Montserratian", "Anguillian", "Aruban",
        "Faroese", "iTaukei", "Liechtensteiner", "Monegasque",
        "St. Helena", "Saint Maarten", "Sint Maarten",
        # Sint Maarten, Guernsey, Saint Helena and the Falklands publish the
        # country a person came from where another census publishes an
        # ancestry. The answer names a state, which is what this node is
        # for, and the bare country name is the whole of the answer.
        "Anguilla", "Aruba", "Curacao", "Dominica", "Dominican Republic",
        "Guyana", "Haiti", "India", "Jamaica", "Netherlands",
        "Saint Kitts and Nevis", "Saint Lucia", "Saint Martin", "Suriname",
        "US", "UK", "UK and Ireland", "Ascension", "South Africa",
        "St. Helenian", "Gulf Co-operative countries",
        "Latvia", "Portugal", "Romania",
        # And the same answer written as an adjective.
        "Andorran", "Chilean", "Colombian", "Dominican", "Honduran",
        "Jamaican", "Kosovan", "Nicaraguan", "Saban", "Surinamese",
        "Venezuelan", "Haitian", "Pitcairn Islander", "Carolinian",
        "Yap outer islanders",
    ),
    # Mauritius counts four "communities" defined by religion and origin
    # together, so two of its four are a faith. Reading "Hindou" as South
    # Asian ancestry would be the likelier guess and still a guess: the
    # census asks about religion there, and the honest answer is to say the
    # category is not an ancestry rather than to pick one for it.
    "Unclassified ethnicity answers": ("Hindou", "Musulman"),
    "Han and Sinitic peoples": ("Hui",),
    # The Austronesian peoples of maritime south-east Asia that Indonesia,
    # Malaysia and Myanmar name beyond the tree's existing list.
    "Malay and Indonesian peoples": ("Banjarese", "Bantenese", "Sasak",
                                     "Moken"),
    "Philippine peoples": ("Tinananen", "Kabayukan"),
    # Poland's ethnographic regions, which its census counts as separate
    # declarations of ethnicity beside Silesian and Kashubian.
    "Slavic peoples": ("Hutsul", "Pomeranian", "Kociewian", "Kurpian",
                       "Podlasian",
                       # Kosovo's Gorani, who speak a South Slavic dialect.
                       "Gorani"),
    # Russia's smallest counted peoples. Each is filed by the language it
    # speaks, which is the axis the rest of this table uses: the Besermyan
    # speak Udmurt, the Hemshin Armenian, the Shapsug Adyghe.
    "Finnic and Ugric peoples": ("Besermyan", "Votic", "Izhorian",
                                 "Nganasan", "Livonian"),
    "Caucasian peoples": ("Shapsug",),
    "Armenian peoples": ("Hemshin",),
    "Turkic peoples": ("Soyot", "Teleut", "Chulym", "Kumandin", "Chelkan",
                       "Tubalar"),
    "Horn of Africa peoples": ("Orma", "Borana", "Bilen", "Tigre"),
    "Dravidian peoples": ("Bharatha",),
    "Polynesian peoples": ("Futunian",),
    "Aboriginal and Torres Strait Islander peoples": ("Australian Aboriginal",),
    "Hispanic or Latino (census category)": ("Latino",),
    "Khoisan peoples": ("Sarwa", "Damara", "Sandawe"),
    "Indigenous peoples of Mesoamerica and the Caribbean": ("Xinca",),
    "Afro-descendant peoples of the Americas": ("Afroecuadorian",
                                                "Afro-Ecuadorian"),
    # Answers that say the person is of more than one ancestry. They are
    # not a refusal to answer and they are not a people, which is what the
    # mixed category is for.
    "Mixed or multiple (census category)": (
        "Black and White", "mixed - other", "two or more ethnicities or races",
        "mixed European and African ancestry", "Mestico", "Baster",
    ),
    "Middle Eastern or North African (census category)": (
        "Arab, Arab Scottish or Arab British",
    ),
    # Scotland writes each of its census categories as the three ways a
    # person might say it. The answer is the category; the "Scottish" and
    # "British" in it say where the person lives, not what they descend
    # from, which is why the compound rule refuses these and the census's
    # own grouping has to be stated.
    "Black or African (census category)": (
        "African-American or African descent",
        "African descent or African-American",
        "African, African Scottish or African British",
        "Black, Black Scottish or Black British",
    ),
    "Asian (census category)": (
        "Bangladeshi, Bangladeshi Scottish or Bangladeshi British",
        "Chinese, Chinese Scottish or Chinese British",
        "Indian, Indian Scottish or Indian British",
        "Pakistani, Pakistani Scottish or Pakistani British",
        "Peoples of India and Pakistan",
    ),
    # Scotland counts Gypsy/Travellers inside its White section, as England
    # and Wales count "White: Gypsy or Irish Traveller", which the table
    # already carries.
    "White or European (census category)": (
        "Gypsy/Traveller",
        # Mauritius's fourth community, and the bands the small European
        # territories write for "somewhere else in Europe", which sit beside
        # "Other European" already in this category.
        "Euro-Mauricien (Blanc)", "other Europe", "other EU", "other Nordic",
        "other Nordic peoples", "other Crown Dependencies",
    ),
    "Pacific Islander (census category)": (
        "Native Hawaiian and other Pacific Islander",
        "Native Hawaiian or other Pacific Islander",
    ),
}


LANGUAGE_VARIANTS: dict[str, str] = {
    # Fula, across a dozen colonial orthographies.
    "Fulah": "Fula", "Fulata": "Fula", "Peulh": "Fula", "Peul": "Fula",
    "Pular": "Fula", "Mbororo": "Fula", "Fulani": "Fula", "Poular": "Fula",
    # Madagascar's census names the highland dialect, not the language.
    "Merina": "Malagasy",
    # Ghana's census names the Akan dialects separately.
    "Asante": "Akan", "Ashanti": "Akan", "Akuapem": "Akan",
    # Southern Africa, where the noun class prefix is part of the name.
    "Oshiwambo": "Ovambo", "Wambo": "Ovambo", "Owambo": "Ovambo",
    "Otjiherero": "Herero", "Rukwangali": "Kwangali",
    "Chewa": "Chichewa",
    # West Africa.
    "Sossou": "Susu", "Soso": "Susu",
    "Mandinka": "Mandingo", "Mandingue": "Mandingo",
    "Songhay": "Songhai", "Djerma": "Songhai",
    "Gourma": "Gurma", "Moore": "Mossi",
    # Central Asia, where Russian sources add -i.
    "Uzbeki": "Uzbek", "Tajiki": "Tajik", "Turkmeni": "Turkmen",
    "Kirghiz": "Kyrgyz", "Kirgiz": "Kyrgyz",
    # The Philippines, whose census writes the pair.
    "Bisaya": "Cebuano", "Binisaya": "Cebuano", "Ilonggo": "Hiligaynon",
    "Bicol": "Bikol", "Ilokano": "Ilocano",
    # Vietnam and China name the majority by its own ethnonym.
    "Kinh": "Vietnamese", "Putonghua": "Mandarin", "Guoyu": "Mandarin",
    # One language, two registers' spellings of it. Russia's neighbours
    # transliterate from Russian, Nepal and India from Devanagari, and the
    # Pacific registers write the island where the reference works write the
    # language.
    "Moldavian": "Moldovan", "Azeri": "Azerbaijani", "Turkmani": "Turkmen",
    "Izhorian": "Ingrian", "Sunuwar": "Sunwar", "Lapcha": "Lepcha",
    "Khiemnungan": "Khiamniungan", "Bishnupuriya": "Bishnupriya",
    "Santhali": "Santali",
    "Nauru": "Nauruan", "Rundi": "Kirundi", "Kiribati": "Gilbertese",
    "Serbo-Croat": "Serbo-Croatian",
    # West Africa, where the dialect a census names is the language the
    # references list.
    "Dyula": "Dioula", "Dagarte": "Dagaare", "Dagomba": "Dagbani",
    "Kokomba": "Konkomba", "Akyem": "Akan", "Boron": "Akan",
    "Gourmantche": "Gurma",
    # Southern Africa and Angola, in Portuguese and in the local spelling.
    "Kwanhama": "Kwanyama", "Nganguela": "Ngangela", "Nhaneca": "Nyaneka",
    "Muhumbi": "Humbi", "Shekgalagadi": "Kgalagadi",
    "Cabo Verdian": "Cape Verdean Creole",
    # The Balkans, where the census names the language after the nation.
    "Vlach": "Aromanian",
    # Ethiopia writes a language as the people's name plus the Amharic
    # suffix -gna ("the X tongue"). Where the root is one the tree already
    # carries, the two spellings are one language; where it is not -- and
    # most of the 2007 census's tail is not -- the name is left alone rather
    # than guessed at from the suffix.
    "Wergigna": "Werji", "Kontigna": "Konta", "Messengogna": "Messengo",
    # Bhutan names Nepali after the south of the country.
    "Lhotshamkha": "Nepali", "Pashaie": "Pashai",
}

ETHNIC_VARIANTS: dict[str, str] = {
    "Maure": "Moor", "Maur": "Moor",
    "Wambo": "Ovambo", "Owambo": "Ovambo", "Oshiwambo": "Ovambo",
    "Mandinka": "Mandingo", "Mandingue": "Mandingo",
    "Sossou": "Susu", "Soso": "Susu",
    "Letebele": "Ndebele", "Matebele": "Ndebele",
    "Zarma": "Songhai", "Songhay": "Songhai", "Djerma": "Songhai",
    "Gourma": "Gurma", "Moore": "Mossi",
    "Kinh": "Vietnamese", "Han Chinese": "Han", "Hui Chinese": "Hui",
    # French and Portuguese spellings of names the tree carries in English.
    "Haoussa": "Hausa", "Peuhl": "Fula", "Gourmatche": "Gurma",
    "Senoufo": "Senufo", "S\u00e9noufo": "Senufo", "Dagari": "Dagaaba",
    "Dagaati": "Dagaaba", "Frafri": "Frafra",
    "Krou": "Kru", "Mjaruo": "Luo", "Ateso": "Teso", "Khalkh": "Khalkha",
    "Makuwa": "Makua", "Mmakuwa": "Makua",
    "Bakwa Kalonji": "Kalonji", "Mb\u00e9d\u00e8": "Mbete", "Muha": "Ha",
    "Lorma": "Loma",
    "Serb": "Serbian", "Black Moors": "Moor", "White Moors": "Moor",
    "Pulaar": "Fula",
    "Croat": "Croatian", "Slovakian": "Slovak",
    # Ukraine's census transliterates every people it counts from Russian,
    # and adds -ian to several the references leave bare.
    "Azeri": "Azerbaijani", "Chuvashian": "Chuvash", "Moldovian": "Moldovan",
    "Mordvinian": "Mordvin", "Gagauzian": "Gagauz", "Abkhazian": "Abkhaz",
    "Ingushetian": "Ingush", "Buriat": "Buryat", "Nenet": "Nenets",
    "Vep": "Veps", "Liv": "Livonian", "Aghul": "Agul", "Abazin": "Abaza",
    "Afghani": "Afghan", "Kazak": "Kazakh",
    # The Congo basin, Uganda and southern Africa, where one people is
    # written a dozen ways across three colonial languages.
    "Kanioka": "Kanyok", "Lugbala": "Lugbara",
    "Mukhonzo": "Konzo", "Mbede": "Mbete", "Mboum": "Mbum",
    "Masa": "Massa", "Tupuri": "Toupouri", "Mundang": "Moundang",
    "Kanouri": "Kanuri", "Tamasheq": "Tamazight", "Pular": "Fula",
    "Peule": "Fula", "Fullah": "Fula",
    "Madingo": "Mandingo", "Mandinga": "Mandingo", "Manjago": "Manjak",
    "Manjaco": "Manjak", "Manjack": "Manjak", "Sereer": "Serer",
    "Kissien": "Kissi", "Serahuleh": "Soninke", "Grusi": "Gurunsi",
    "Gourounsi": "Gurunsi", "Sonrai": "Songhai",
    "Afrikaaner": "Afrikaner", "Masai": "Maasai", "Mosarwa": "Sarwa",
    # Armenia and Vietnam.
    "Yezidi": "Yazidi",
    # Mauritius names its communities in French.
    "Tamoul": "Tamil", "Telegou": "Telugu", "Chinois": "Chinese",
}


def _resolve_variants(field: str, variants: dict[str, str],
                      placed: dict[str, str]) -> dict[str, str]:
    """Give each spelling variant the parent of the name it is a spelling of.

    A variant is a synonym, so it becomes a *sibling* of nothing and a second
    name for one node: it takes the same parent, which is what makes the two
    spellings roll up to one figure. A variant whose target the tree does not
    place is dropped rather than guessed at, and a variant that would shadow a
    name the tree already places is refused outright, because that would mean
    two tables disagree about one string and the quiet winner would depend on
    dictionary order.
    """
    out: dict[str, str] = {}
    for name, target in variants.items():
        if name in placed:
            raise ValueError(
                f"{field}: {name!r} is both placed by the tree "
                f"(under {placed[name]!r}) and listed as a spelling of "
                f"{target!r}; one of the two has to go")
        parent = placed.get(target)
        if parent is not None:
            out[name] = parent
    return out


def parents(field: str) -> dict[str, str]:
    """child -> parent for one field, over the whole tree."""
    if field == "religion":
        return _invert(RELIGION_TRADITION)
    if field == "language":
        out = _invert(LANGUAGE_BRANCH)
        out.update(_invert(LANGUAGE_BANDS))
        out.update(_invert(LANGUAGE_FAMILY))
        out.update(_invert(LANGUAGE_EXTRA))
        out.update(_resolve_variants("language", LANGUAGE_VARIANTS, out))
        return out
    if field == "ethnicity":
        out = {name: "Unclassified ethnicity answers" for name in ETHNIC_RESIDUALS}
        out.update(_invert(ETHNIC_PEOPLES))
        out.update(_invert(ETHNIC_CENSUS))
        out.update(_invert(ETHNIC_NATIONALITY))
        out.update(_invert(ETHNIC_ANCESTRY))
        out.update(_invert(ETHNIC_EXTRA))
        out.update(_resolve_variants("ethnicity", ETHNIC_VARIANTS, out))
        return out
    return {}


def census_categories() -> frozenset[str]:
    """Tier-2 nodes that are a state's category rather than a people."""
    return frozenset(ETHNIC_CENSUS)


# Two ways offices write a name that the table should not have to repeat.
#
# Canada's census does both on the same page: it qualifies a band as "Turkic
# languages, n.i.e." (not included elsewhere) or a rolled-up entry as "Cree,
# n.o.s." (not otherwise specified), and it gives an alternate spelling in
# brackets -- "Punjabi (Panjabi)", "Tlicho (Dogrib)". Neither changes what the
# answer is. Stripping them is a normalisation rather than a guess, which is
# why it runs before the patterns and after the exact names.
_QUALIFIERS = (", n.i.e.", ", n.i.e", ", n.o.s.", ", n.o.s")


# A word that says what kind of thing the entry is, not which one it is.
# Stripping it, or adding it, is the same normalisation read in two
# directions: a source may write "Turkic languages" where the table says
# "Turkic", or "Italic (Romance)" where the table says "Romance languages".
_KINDS = (" languages", " language", " peoples", " people", " speakers",
          " dialects", " dialect")


# Typographic punctuation, as a document sets it, against the plain ASCII a
# table is typed in. Ethiopia's "Alaba-K\u2019abeena" and a table's
# "Alaba-K'abeena" are one language, and nothing but the apostrophe differs.
_PUNCTUATION = {
    "\u2018": "'", "\u2019": "'", "\u02bc": "'", "\u00b4": "'", "`": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2212": "-",
    "\u00a0": " ",
}


def _defold(name: str) -> str:
    """``name`` with its accents and typographic punctuation flattened."""
    plain = "".join(_PUNCTUATION.get(c, c) for c in name)
    return "".join(c for c in unicodedata.normalize("NFD", plain)
                   if unicodedata.category(c) != "Mn")


def normalisations(name: str) -> list[str]:
    """Other forms of ``name`` worth looking up, most faithful first.

    Every form here is the same answer spelled differently, so a match on
    one is a match on the name. Forms that would *change* the answer -- a
    word of the label dropped, two names joined by "and" split apart -- are
    not normalisations and are not produced here; `agreed_parent` handles
    those under a rule that can refuse.
    """
    out = []
    plain = name
    for tail in _QUALIFIERS:
        if plain.endswith(tail):
            plain = plain[: -len(tail)].strip()
            break
    if plain != name:
        out.append(plain)
    # An accented spelling and a bare one are the same name: "Éwé" is "Ewe",
    # "Malinké" is "Malinke", "Guaraní" is "Guarani".
    for form in list(out) + [name]:
        bare = _defold(form)
        if bare != form:
            out.append(bare)
            out.append(bare.replace("'", ""))
    # "Turkic languages" -> "Turkic", so a band reaches the family it names
    # even where the table lists the family under a bare word -- and back the
    # other way, so "Romance" reaches "Romance languages". Case-insensitive,
    # because the Central African Republic's tables write "Banda Languages".
    for form in list(out) + [name]:
        low = form.lower()
        for kind in _KINDS:
            if low.endswith(kind) and len(form) > len(kind) + 1:
                out.append(form[: -len(kind)].strip())
                break
        else:
            out.append(form + " languages")
            out.append(form + " peoples")
    # "Punjabi (Panjabi)" -> "Punjabi", and the bracketed name too: which of
    # the two the table knows varies by entry.
    for form in list(out) + [name]:
        if "(" in form and form.endswith(")"):
            head, _, rest = form.partition("(")
            out.append(head.strip())
            out.append(rest[:-1].strip())
    # "Lushai/Mizo", "Yakthung/Limbu", "Bisaya/Binisaya": a slash between two
    # names of one people is the censuses' own convention for an alternate
    # spelling, unlike "and", which joins two different answers.
    #
    # A semicolon says the same thing and says it by standard: ISO 639 gives
    # every language a reference name and lists its synonyms after one --
    # "Catalan; Valencian", "Avaric; Avar; Avarish", "Faroese; Faeroese" --
    # and a register that types its code list into a census table brings the
    # punctuation with it. Both separators join names of one language; "and"
    # joins two languages and is never split here.
    for form in list(out) + [name]:
        if "/" in form or ";" in form:
            parts = [form] if "/" not in form else form.split("/")
            for part in parts:
                out.extend(bit.strip() for bit in part.split(";"))
    # "Buddhists" is "Buddhist", "Baha'is" is "Baha'i". Only a form the table
    # already knows is ever accepted, so a wrong singular costs nothing.
    for form in list(out) + [name]:
        if form.endswith("s") and len(form) > 3 and not form.endswith("ss"):
            out.append(form[:-1])
    # Once brackets and slashes have opened the name up, offer the kind word
    # again: "Italic (Romance) languages" yields "Romance", and the table
    # spells it "Romance languages".
    for form in list(out):
        low = form.lower()
        if not any(low.endswith(kind) for kind in _KINDS):
            out.append(form + " languages")
            out.append(form + " peoples")
    seen: set[str] = set()
    return [f for f in out if f and f != name and not (f in seen or seen.add(f))]


# Words that say something about the answer without naming one, so they carry
# no placement of their own and must not vote on where a compound belongs.
_EMPTY_WORDS = frozenset({
    "and", "or", "the", "of", "other", "others", "not", "elsewhere",
    "included", "specified", "stated", "reported", "origin", "origins",
    "ancestry", "ancestries", "ethnicity", "ethnic", "group", "groups",
    "only", "mainly", "mainland", "nie", "nos", "some", "all", "any",
    "both", "mixed", "multiple", "another", "unspecified", "descent",
})


def _constituents(name: str) -> list[str]:
    """The parts of ``name`` that could each name a group on their own."""
    words = [w for w in re.split(r"[\s,/()\-]+", name) if w]
    words = [w for w in words
             if len(w) > 2 and w.lower().strip(".") not in _EMPTY_WORDS]
    out = list(words)
    # Pairs too, because "Sri Lankan" and "Black British" are two words that
    # name one thing and would otherwise vote as two.
    out += [f"{a} {b}" for a, b in zip(words, words[1:])]
    return out


_AGREED: dict[str, dict[str, str | None]] = {}


def agreed_parent(field: str, name: str) -> str | None:
    """Where a compound label belongs, when all of its parts agree.

    A label no table spells may still be made of names the tables do spell:
    "Han Chinese" is Han and it is Chinese, and both are Han and Sinitic
    peoples, so the label is too. The rule is that every part that resolves
    must agree, and the label lands at the deepest node they share --
    "Amazigh and Arab" is not Amazigh and is not Arab, but both are Middle
    Eastern and North African ancestry, so that is where it goes.

    The refusal is the point. "European and Mestizo" names two ancestries
    that share nothing, so it is left unplaced and stays visible as a group
    the tree does not cover, which is the honest answer. Reading it as
    either one would put a number under a heading no census wrote.
    """
    cache = _AGREED.setdefault(field, {})
    if name in cache:
        return cache[name]
    cache[name] = None            # guards against recursing through itself
    tops = tier1_names(field)
    trails: list[list[str]] = []
    for part in _constituents(name):
        if part == name:
            continue
        if part not in tops and parent_of(field, part) is None:
            continue
        trail, seen = [], {part}
        at: str | None = part
        while at is not None:
            trail.append(at)
            at = None if at in tops else parent_of(field, at)
            if at in seen:
                break
            if at is not None:
                seen.add(at)
        trails.append(list(reversed(trail)))
    common: list[str] | None = None
    for trail in trails:
        if common is None:
            common = trail
            continue
        stop = 0
        while stop < min(len(common), len(trail)) and common[stop] == trail[stop]:
            stop += 1
        common = common[:stop]
    found = common[-1] if common else None
    cache[name] = None if found == name else found
    return cache[name]


def pattern_parent(field: str, name: str) -> str | None:
    """The family a name falls in by its root word, where no exact name did.

    Only ethnicity uses this, and only for the national blocks documented
    above. It is a rule rather than a guess: every pattern is a people's own
    name, and a match means the label is that people plus a locality.
    """
    if field == "religion":
        for parent, roots in RELIGION_PATTERNS:
            for root in roots:
                if root in name:
                    return parent
        return None
    if field != "ethnicity":
        return None
    if name in ETHNIC_PATTERN_EXCEPTIONS:
        return ETHNIC_PATTERN_EXCEPTIONS[name]
    for parent, roots in ETHNIC_PATTERNS:
        for root in roots:
            if root in name:
                return parent
    return None


def merged_parents(field: str) -> dict[str, str]:
    """The whole tree: the label table's own nesting plus the tiers here.

    canonical_groups owns the bottom of it -- Catholicism under Christianity,
    Sunni under Islam -- because those are facts about the labels themselves.
    This module owns the tiers above. Merged, a name walks from what a census
    wrote all the way to an ancestry or a tradition.
    """
    cached = _MERGED.get(field)
    if cached is not None:
        return cached
    import canonical_groups           # imported here to avoid a cycle: the
    out = dict(canonical_groups.PARENT.get(field, {}))   # label table reads this
    out.update(parents(field))
    _MERGED[field] = out
    return out


# The merged tree and its case-folded twin, built once per field.
#
# Both are caches rather than conveniences. ``parent_of`` runs for every row of
# every one of some fifty thousand records, and rebuilding a two-thousand-entry
# dict inside it was enough to take the build from three minutes to never
# finishing: the first version keyed the folded map on ``id(table)`` and was
# handed a freshly built table each call, so it cached a new copy every time
# and the process was killed before it reached groups.json.
_MERGED: dict[str, dict[str, str]] = {}
_FOLDED: dict[str, dict[str, str]] = {}


def _folded(field: str) -> dict[str, str]:
    """The tree keyed case-insensitively.

    Capitalisation is a house style, not a distinction, and the Factbook's is
    its own: it writes "mixed" where a census writes "Mixed" and "two or more
    races" where the Census Bureau writes "Two or more races". Matching
    literally left Brazil's 45.3% *pardo* -- its largest group -- with no
    ancestry at all.
    """
    cached = _FOLDED.get(field)
    if cached is None:
        cached = {k.lower(): v for k, v in merged_parents(field).items()}
        _FOLDED[field] = cached
    return cached


def parent_of(field: str, name: str, table: dict[str, str] | None = None,
              ) -> str | None:
    """The one step up from ``name``: exact, then folded, then by rule."""
    table = merged_parents(field) if table is None else table
    # A tier-1 node is the top by definition, and saying so here rather than
    # relying on no rule matching is what keeps the tree a tree: the rules
    # below work on the words of a name, and "African ancestry" contains
    # "African", which is a census category *under* it. Answering that would
    # close a loop.
    if name in tier1_names(field):
        return None
    if name in table:
        return table[name]
    folded = _folded(field)
    tops = tier1_names(field)
    # "Romance languages, n.i.e." is the part of Romance that the table did
    # not name separately, so it belongs *under* Romance rather than beside
    # it: read as a sibling, the family it is the remainder of would not
    # count it, and Canada publishes a dozen of these bands. This runs first
    # for the same reason -- the general loop below would match the stripped
    # name and hand back its parent, losing a level.
    for tail in _QUALIFIERS:
        if not name.endswith(tail):
            continue
        base = name[: -len(tail)].strip()
        for form in [base] + normalisations(base):
            if form != name and (form in table or form in tops):
                return form
        break
    for form in [name] + normalisations(name):
        if form in table:
            return table[form]
        if form.lower() in folded:
            return folded[form.lower()]
        if form != name and form in tops:
            return form
    by_root = pattern_parent(field, name)
    if by_root is not None:
        return by_root
    by_class = class_prefix_parent(field, name)
    if by_class is not None:
        return by_class
    # Last: a compound whose parts all point the same way. It runs after the
    # patterns because a pattern is a statement about one people and this is
    # an inference from several, so the narrower rule should win.
    return agreed_parent(field, name)


# The Bantu noun-class prefixes, as censuses across eastern and southern
# Africa attach them to one root.
#
# Tanzania writes the person ("Mzaramo"), Mozambique the language ("Ciyao"),
# Botswana the member of the group ("Mokgatla"), South Africa the language
# with its own prefix ("isiZulu") -- all of them the same root with a class
# marker in front. A table cannot list every prefixed form of every root, and
# stripping the marker is the operation the grammar itself performs.
#
# The rule is deliberately narrow: the stripped root must land in a family
# that uses these prefixes. Without that, "Serb" loses an "Se" and any three
# letters left over could collide with something on the other side of the
# world; with it, a match is only accepted where the convention it assumes
# actually holds.
_CLASS_PREFIXES = (
    "oshi", "otji", "tshi", "ichi", "isi", "chi", "shi", "umu", "aba",
    "ama", "ki", "ci", "xi", "se", "si", "lu", "ru", "bu", "ba", "wa",
    "mo", "mu", "mw", "ma", "m", "u", "a",
)
_PREFIXED_FAMILIES = frozenset({
    "Bantu languages", "Bantu peoples", "Nilotic peoples",
    "Nilotic languages", "Khoisan peoples", "Khoisan languages",
    "Central African peoples",
})


def class_prefix_parent(field: str, name: str) -> str | None:
    """Where a name belongs once its noun-class prefix is taken off."""
    lowered = name.lower()
    for prefix in _CLASS_PREFIXES:
        if not lowered.startswith(prefix):
            continue
        root = name[len(prefix):]
        if len(root) < 3:
            continue
        for form in (root, root.capitalize()):
            parent = parent_of(field, form)
            if parent in _PREFIXED_FAMILIES:
                return parent
    return None


def _reaches_tier1(field: str, name: str, table: dict[str, str],
                   tier1: frozenset[str]) -> bool:
    seen = {name}
    at = name
    while at not in tier1:
        up = parent_of(field, at, table)
        if up is None or up in seen:
            return at in tier1
        seen.add(up)
        at = up
    return True


def tier1_names(field: str) -> frozenset[str]:
    """The nodes that have no parent by design: the map's broadest groupings."""
    if field == "religion":
        return frozenset(RELIGION_TRADITION)
    if field == "language":
        return frozenset(LANGUAGE_FAMILY)
    if field == "ethnicity":
        return frozenset(ETHNIC_ANCESTRY)
    return frozenset()


def _coverage(index: dict[str, Any]) -> int:
    """Print how much of the shipped map each field's tree accounts for."""
    for field in ("religion", "language", "ethnicity"):
        table = merged_parents(field)
        tier1 = tier1_names(field)
        groups = [g for g in index[field]["groups"] if not g["children"]]
        total = sum(g["units"] for g in groups)
        placed = 0
        misses: list[tuple[int, str]] = []
        for group in groups:
            if _reaches_tier1(field, group["name"], table, tier1):
                placed += group["units"]
            else:
                misses.append((group["units"], group["name"]))
        misses.sort(reverse=True)
        print(f"{field}: {placed / total:.1%} of unit-mentions reach a top "
              f"grouping ({len(groups) - len(misses)} of {len(groups)} groups)")
        for units, name in misses[:30]:
            print(f"    {units:>6}  {name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coverage", action="store_true",
                    help="report how much of site/data/groups.json is placed")
    args = ap.parse_args()
    if args.coverage:
        path = Path(__file__).resolve().parent.parent / "site/data/groups.json"
        return _coverage(json.loads(path.read_text()))
    for field in ("religion", "language", "ethnicity"):
        print(f"{field}: {len(parents(field))} names placed in the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------
#
# One band per tier-1 node, and a variation within it per family, so that the
# map reads as regions rather than confetti: every Bantu people is a green, so
# southern Africa looks like one place even where each province reports a
# different people, and a reader can still tell Bantu from Nilotic.
#
# The bands are chosen to stay apart under the three common forms of
# colour-blindness. They are never the only thing carrying identity: every
# unit names its group on hover, the legend names each colour, and the panel
# names it again.
# One base colour per tier-1 node, spread around the wheel so the bands are
# told apart at a glance, and a computed variation per family inside each band.
#
# The bases were hand-picked rather than generated: the ones that colour most
# of the map get the widest separation, and the rare ones take the muted slots,
# so the four or five colours a reader actually has to hold apart are the four
# or five furthest apart. They are drawn from the Okabe-Ito colour-blind-safe
# set where it stretches far enough.
#
# Families are *not* hand-coloured. Each takes its band's hue rotated by its
# position among its siblings, which guarantees no two siblings share a colour
# and spaces them as widely as the band allows. Hand-assigning them produced
# eight greens nobody could separate; a rotation is both wider and stable,
# since the order comes from the table rather than from the data.
TIER_HUE: dict[str, dict[str, str]] = {
    "religion": {
        "Abrahamic religions": "#0072B2",
        "Indian religions": "#E69F00",
        "East Asian religions": "#CC79A7",
        "African diaspora religions": "#8B4A9C",
        "Folk and traditional religions": "#7A5230",
        "Other and new religions": "#00A0B0",
        "No religion": "#7F8C8D",
        "Not stated": "#B0B7BC",
    },
    "language": {
        "Indo-European languages": "#D55E00",
        "Sino-Tibetan languages": "#009E73",
        "Niger-Congo languages": "#4CAF50",
        "Afro-Asiatic languages": "#B8860B",
        "Austronesian languages": "#00A0B0",
        "Turkic languages": "#7B2FBE",
        "Uralic languages": "#0072B2",
        "Dravidian languages": "#C2185B",
        "Austroasiatic languages": "#00897B",
        "Tai-Kadai languages": "#E69F00",
        "Japonic languages": "#CC79A7",
        "Koreanic languages": "#8B4A9C",
        "Indigenous languages of the Americas": "#A0522D",
        "Indigenous languages of Australia": "#8D4E85",
        "Nilo-Saharan languages": "#2E7D32",
        "Khoisan languages": "#6B8E23",
        "Caucasian languages": "#5D3FD3",
        "Altaic and Siberian languages": "#6A5ACD",
        "Hmong-Mien languages": "#D81B60",
        "Papuan languages": "#00695C",
        "Creole and contact languages": "#56B4E9",
        "Sign languages": "#667788",
        "Language isolates": "#8A7A6D",
        "Other and unspecified languages": "#B0B7BC",
    },
    "ethnicity": {
        "African ancestry": "#009E73",
        "European ancestry": "#D55E00",
        "East and Southeast Asian ancestry": "#CC79A7",
        "Mixed or multiple ancestry": "#56B4E9",
        "Indigenous American ancestry": "#E69F00",
        "Pacific ancestry": "#00A0B0",
        "Middle Eastern and North African ancestry": "#B8860B",
        "Romani": "#8B4A9C",
        "Turkic and Central Asian ancestry": "#5D3FD3",
        "South Asian ancestry": "#A0522D",
        "Jewish": "#0072B2",
        "Stated as a nationality": "#667788",
        "Other or not stated ancestry": "#B0B7BC",
    },
}

# Families whose colour is a convention rather than a free choice.
#
# Checked before the rotation below, and the reason it exists: deriving every
# family from its band turned the whole religion map into one blue, because
# Christianity, Islam and Judaism are all Abrahamic. Catholic red, Protestant
# blue, Orthodox purple, Islamic green, Hindu saffron and Buddhist gold are
# what the printed religion atlases use and what a reader arrives expecting,
# and a map that spends that recognition to be internally tidy has made a bad
# trade. Language and ethnicity have no such conventions, so their families
# take the rotation and keep their bands legible instead.
FAMILY_HUE: dict[str, dict[str, str]] = {
    "religion": {
        "Christianity": "#2E5FA3",
        "Catholicism": "#B03A2E",
        "Protestantism": "#2E86C1",
        "Orthodoxy": "#7D3C98",
        "Latter-day Saints": "#5DADE2",
        "Jehovah's Witnesses": "#48C9B0",
        "Islam": "#1E8449",
        "Sunni Islam": "#1E8449",
        "Shia Islam": "#7DCEA0",
        "Ibadi Islam": "#0B5345",
        "Ahmadiyya": "#A9DFBF",
        "Judaism": "#5D6D7E",
        "Hinduism": "#E67E22",
        "Buddhism": "#D4AC0D",
        "Sikhism": "#D35400",
        "Jainism": "#B9770E",
        "Baha'i": "#F5B041",
        "Druze": "#16A085",
        "Zoroastrianism": "#B7950B",
        "Folk and traditional religion": "#7A5230",
        "Māori religions": "#AF7AC5",
        "Spiritism and Afro-Brazilian religions": "#8B4A9C",
        "Shinto": "#E59866",
        "Taoism": "#DC7633",
        "Confucianism": "#CA6F1E",
        "Rastafarian": "#58D68D",
        "No religion": "#7F8C8D",
        "Atheism": "#5D6D7E",
        "Agnosticism": "#AAB7B8",
        "Other religions": "#00A0B0",
        "Not stated": "#B0B7BC",
        "Unaffiliated or not reported": "#95A5A6",
    },
}


# How far a family's hue is turned from its band's, by its position among its
# siblings.
#
# The order goes to the extremes first and then fills in, so a band with three
# families uses the whole span and one with nine still spaces them evenly. The
# span is capped at 30 degrees in each direction for a reason found by trying
# a wider one: at +/-66 a saturated base flew across the wheel -- African
# ancestry's teal-green turned into a deep blue for Malagasy peoples -- and the
# band stopped reading as one region, which is the thing it is for. Within 30
# degrees the families are still plainly different colours and southern Africa
# still looks like southern Africa.
#
# Saturation alternates with the same index, which buys a second axis of
# separation without touching lightness -- lightness belongs to the share.
_ROTATION = (0, 30, -30, 15, -15, 22, -22, 8, -8, 26, -26, 12, -12)
_SATURATION = (1.0, 0.72, 1.0, 0.78, 0.94, 0.68, 1.0, 0.84, 0.9, 0.74, 1.0)


def _hex_to_hls(hex_colour: str) -> tuple[float, float, float]:
    import colorsys
    n = int(hex_colour.lstrip("#"), 16)
    return colorsys.rgb_to_hls(((n >> 16) & 255) / 255,
                               ((n >> 8) & 255) / 255, (n & 255) / 255)


def _hls_to_hex(h: float, l: float, s: float) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)),
                                  max(0.0, min(1.0, s)))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _siblings(field: str, parent: str) -> list[str]:
    """A band's families, in table order, so a colour never moves on a rebuild."""
    table = {"religion": (RELIGION_TRADITION,),
             "language": (LANGUAGE_FAMILY,),
             "ethnicity": (ETHNIC_ANCESTRY,)}.get(field, ())
    for source in table:
        if parent in source:
            return [k for k in source[parent] if k != parent]
    return []


def ancestry(field: str, name: str) -> list[str]:
    """``name`` and every group above it, nearest first, guarded for cycles."""
    trail = [name]
    seen = {name}
    while True:
        up = parent_of(field, trail[-1])
        if up is None or up in seen:
            return trail
        trail.append(up)
        seen.add(up)


def hue(field: str, name: str) -> str | None:
    """The colour ``name`` carries.

    A tier-1 node has its own. A family takes its band's hue turned by its
    position among the band's other families, and lightened a little so the
    band still reads as one region. Anything deeper takes its family's, since
    the map shades it by share rather than by identity.
    """
    fixed = FAMILY_HUE.get(field, {})
    if name in fixed:
        return fixed[name]
    table = TIER_HUE.get(field, {})
    if name in table:
        return table[name]
    trail = ancestry(field, name)
    # A group below a family with a conventional colour takes that colour: a
    # census that names one Catholic order is still drawn Catholic red.
    for step in trail:
        if step in fixed:
            return fixed[step]
    for i, step in enumerate(trail):
        if step not in table:
            continue
        if i == 0:
            return table[step]
        # The family directly under this band is the one whose position sets
        # the turn; a group below it inherits the same colour.
        family = trail[i - 1]
        kin = _siblings(field, step)
        try:
            turn = _ROTATION[kin.index(family) % len(_ROTATION)]
        except ValueError:
            turn = 0
        h, l, sat = _hex_to_hls(table[step])
        index = kin.index(family) if family in kin else 0
        scale = _SATURATION[index % len(_SATURATION)]
        return _hls_to_hex(h + turn / 360.0, min(0.60, l + 0.05), sat * scale)
    return None


def tier(field: str, name: str) -> int:
    """How far down the tree ``name`` sits: 1 for a top grouping."""
    depth = 1
    seen = {name}
    at: str | None = name
    while True:
        up = parent_of(field, at)
        if up is None or up in seen:
            return depth
        depth += 1
        seen.add(up)
        at = up


def at_tier(field: str, name: str, want: int) -> str:
    """``name`` rolled up to tier ``want``, or as far up as it goes."""
    trail = [name]
    seen = {name}
    at: str | None = name
    while True:
        up = parent_of(field, at)
        if up is None or up in seen:
            break
        trail.append(up)
        seen.add(up)
        at = up
    # trail is leaf-first; tier 1 is the last entry.
    index = len(trail) - want
    return trail[max(0, min(index, len(trail) - 1))]
