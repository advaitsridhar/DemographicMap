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
import sys
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
    "African diaspora religions": ("Spiritism and Afro-Brazilian religions",),
    "Folk and traditional religions": (
        "Folk and traditional religion", "Māori religions", "Kirat",
        "Prakriti", "Bon", "Modekngei", "Badimo", "Shamanism",
    ),
    "Other and new religions": (
        "Zoroastrianism", "Yazidi", "Jedi", "Eckankar", "Wicca",
        "Pagan and neo-pagan", "Spiritualism and New Age religions",
        "Eastern religions", "Other religions",
    ),
    "No religion": ("No religion",),
    "Not stated": ("Not stated", "Unaffiliated or not reported",
                   "Scheduled Castes"),
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
    ("Latter-day Saints", ("Latter Day", "Latter-day", "Mormon")),
    ("Jehovah's Witnesses", ("Jehovah",)),
    ("Orthodoxy", ("Orthodox",)),
    ("Catholicism", ("Catholic",)),
    ("Protestantism", (
        "Protestant", "Salvation", "Fellowship", "Believer", "Praise",
        "Outreach", "Faith", "Anabaptist", "Espiritista", "Evangelist",
        "Things to Come", "Lord of the Nations", "Way of Salvation",
        "Baptist", "Pentecostal", "Evangelical", "Methodist", "Lutheran",
        "Presbyterian", "Anglican", "Episcopal", "Adventist", "Reformed",
        "Brethren", "Iglesia", "Ministries", "Mission", "Church", "Christ",
        "Christian", "Gospel", "Assembly of God", "Assemblies of God",
    )),
    ("Islam", ("Muslim", "Islamic")),
    ("Folk and traditional religion", ("Tribal", "Traditional", "spirituality",
                                       "Animist", "Indigenous")),
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
    "Tungusic languages": ("Evenki", "Evenk", "Even", "Nanai", "Udege"),
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
    "Austroasiatic languages": ("Vietnamese", "Khmer", "Santali", "Mundari",
                                "Ho", "Khasi", "Wa"),
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
                                      "Tungusic languages"),
    "Dravidian languages": ("Dravidian languages",),
    "Austroasiatic languages": ("Austroasiatic languages",),
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
    "Indo-European languages": ("Other Indo-European", "Indo-Aryan"),
    "Slavic languages": ("Croato-Serbian", "Ruthenian", "Lemko", "Moravian",
                         "Boyko", "Old Church Slavonic", "Slavic"),
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
        "Other Asian and Pacific Island", "Other and unspecified languages",
        "Other language", "Other", "Not stated",
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
                          "Indian Tamil"),
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
        "Finnic and Ugric peoples",
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
        "Himalayan and Tibeto-Burman peoples",
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
    # argument rather than a fact. They stand alone.
    "Jewish": (),
    "Romani": (),
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


def parents(field: str) -> dict[str, str]:
    """child -> parent for one field, over the whole tree."""
    if field == "religion":
        return _invert(RELIGION_TRADITION)
    if field == "language":
        out = _invert(LANGUAGE_BRANCH)
        out.update(_invert(LANGUAGE_BANDS))
        out.update(_invert(LANGUAGE_FAMILY))
        return out
    if field == "ethnicity":
        out = {name: "Unclassified ethnicity answers" for name in ETHNIC_RESIDUALS}
        out.update(_invert(ETHNIC_PEOPLES))
        out.update(_invert(ETHNIC_CENSUS))
        out.update(_invert(ETHNIC_NATIONALITY))
        out.update(_invert(ETHNIC_ANCESTRY))
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


def normalisations(name: str) -> list[str]:
    """Other forms of ``name`` worth looking up, most faithful first."""
    out = []
    plain = name
    for tail in _QUALIFIERS:
        if plain.endswith(tail):
            plain = plain[: -len(tail)].strip()
            break
    if plain != name:
        out.append(plain)
    # "Turkic languages" -> "Turkic", so a band reaches the family it names
    # even where the table lists the family under a bare word.
    for form in list(out) + [name]:
        if form.endswith(" languages"):
            out.append(form[: -len(" languages")])
    # "Punjabi (Panjabi)" -> "Punjabi", and the bracketed name too: which of
    # the two the table knows varies by entry.
    for form in list(out) + [name]:
        if "(" in form and form.endswith(")"):
            head, _, rest = form.partition("(")
            out.append(head.strip())
            out.append(rest[:-1].strip())
    seen: set[str] = set()
    return [f for f in out if f and f != name and not (f in seen or seen.add(f))]


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
    if name in table:
        return table[name]
    folded = _folded(field)
    tops = tier1_names(field)
    for form in [name] + normalisations(name):
        if form in table:
            return table[form]
        if form.lower() in folded:
            return folded[form.lower()]
        if form != name and form in tops:
            return form
    return pattern_parent(field, name)


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
