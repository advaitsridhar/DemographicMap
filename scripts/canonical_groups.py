#!/usr/bin/env python3
"""Cross-country names for the same religion, language or ethnic group.

A global filter is only possible if "Muslim" and "Islam" are known to be the
same answer. They are not the same *string*: across nine countries the religion
field alone carries 39 distinct labels for perhaps a dozen religions, because
each statistical office writes its own. Filtering on raw labels would show a
world map of Islam that silently omits every country whose census says
"Muslim" -- 865 units in one spelling, 737 in the other.

So this is the one table that says which labels name the same thing. It is
consumed by build_entities.py to emit site/data/groups.json, which the frontend
reads; there is deliberately no second copy of it in JavaScript.

Three rules govern what may be merged.

**Only merge what is genuinely the same question.** A rolled-up group must mean
the same thing in each country, not merely sound similar.

**Roll up, never across.** Where a country reports finer categories than the
canonical group -- the US reports Protestant, Catholic, Orthodox, Latter-day
Saints and Jehovah's Witnesses where Australia reports "Christianity" -- the
children sum to the parent. A source is never asked to supply both levels, so
summing cannot double count; the guard in ``canonicalise`` enforces that.

**Never merge an ambiguity into a certainty.** The US "Unaffiliated or not
reported" is deliberately absent from ``No religion`` below. It mixes people
who belong to nothing with members of bodies that did not report, and folding
it in would turn "we cannot tell" into a count of the non-religious.
"""

from __future__ import annotations

from typing import Any, Iterable

# canonical name -> the source labels that mean it
RELIGION: dict[str, tuple[str, ...]] = {
    # --- Christianity and its traditions -----------------------------------
    #
    # The tradition names below are groups in their own right, each a child of
    # Christianity in PARENT. That is what lets a reader ask for Catholicism
    # across 119 countries, or for Christianity whole and have every
    # denomination counted into it. Before the split they were all folded into
    # "Christianity" on sight, so the map could answer the second question and
    # not the first, and 6,144 records saying "Roman Catholic" were invisible
    # to the filter.
    #
    # Rolling up stays sound because no source publishes a tradition beside
    # the Christian total it belongs to; the guard in canonicalise enforces it.
    "Christianity": (
        # Only the labels that name no tradition. A census that offers
        # "Christian" against "Catholic" means people who said just
        # "Christian", and that answer belongs at the family level rather than
        # inside one of its children.
        "Christian", "Christianity", "Christians", "Chretien", "Chrétien",
        "Christian (unspecified)", "Christian nfd", "Christian, unspecified",
        "Other Christian", "Other Christians", "other Christians",
        "Other Christian religions", "Other Christian denominations",
        # Afrobarometer's label for a respondent who named no denomination.
        "Christian only",
        # A person of both traditions, and a church that belongs to neither:
        # both are Christian answers that no child can hold.
        "Protestant (Mixed)", "Mixed Catholic / Protestant",
        "Non-denominational Christian", "Christian Fellowship Church",
        "Independent", "African Independent Church",
    ),
    "Catholicism": (
        "Catholic", "Roman Catholic", "Catholicism", "Catholics",
        "Católica Apostólica Romana", "Catholique", "Catolica",
        "Catholic (unspecified)", "Greek Catholic",
        # The Philippines counts the Charismatic renewal separately and says
        # so in the column head; both are Catholics.
        "Roman Catholic, excluding Catholic Charismatics",
        "Catholic Charismatic", "Roman Catholic Charismatic",
    ),
    "Protestantism": (
        "Protestant", "Protestants", "Protestante", "Evangélicas",
        "Protestant and evangelical", "other Protestant",
        "Protestant (unspecified)",
        "Evangelical", "Evangelical Christian", "Evangelical Lutheran",
        "Evangelical, Born Again and Fundamentalist", "Evangelical/Protestant",
        "Evangelical Reformist", "Protestant Evangelical",
        "Evangelical and Pentecostal", "Evangelical or Protestant",
        "Protestant/Anglican",
        "Anglican", "Church of England", "Episcopal",
        "Baptist", "Methodist", "Presbyterian",
        "Presbyterian, Congregational and Reformed", "Reformed",
        "Lutheran", "Pentecostal", "Adventist", "Seventh Day Adventist",
        "Seventh-day Adventist", "Congregational", "Moravian", "Morovian",
        "Mennonite", "New Apostolic", "Apostolic", "Kimbanguist",
        "Quaker", "Quaker/Friends", "Friends",
        "Calvinist", "Reformed Christian", "Protestant Reformed",
        "Assembly of God", "Salvation Army", "Salutiste",
        "Dutch Reformed", "Church of Christ", "Brethren",
        # Czechia's churches, and its census write-ins that name a tradition
        # but no church.
        "Evangelical Church of Czech Brethren", "Czechoslovak Hussite",
        # National and regional churches, each named only by its own country's
        # entry. Folding them is what lets a map of Protestantism include
        # Iceland, Norway and Kiribati at all -- unfolded, each is a
        # one-country group and the country reads as having no Protestants.
        "Church of Norway", "Church of Sweden", "Church of Iceland",
        "Church of Scotland",
        "Evangelical Lutheran Church of Iceland",
        "Independent Congregation of Reykjavik",
        "Independent Congregation of Hafnarfjordur",
        "Evangelical Church of the Augsburg Confession",
        "Kiribati Protestant Church", "Kiribati Uniting Church",
        "Congregational Christian Church", "Ekalesia Niue",
        "Church of Jesus Christ in Madagascar/Malagasy Lutheran Church/Anglican Church",
        "Awakening Churches/Christian Revival", "Apostolic Sect",
        "Universal Kingdom of God", "Worship Centre",
        "United Church", "United Church of Zambia or UCZ",
        "United Church of Zambia", "New Apostolic Church",
        "Christian mission in many lands (CMML)",
        # Afrobarometer churches large enough in one country to have earned
        # their own code. The Zionist Christian Church is South Africa's
        # largest single denomination and Fifohazana is a Malagasy revival
        # movement inside the Protestant churches; Eglise du Christianisme
        # Céleste is the Celestial Church of Christ, in Benin and Nigeria.
        "Zionist Christian Church", "Eglise Du Christianisme Céleste",
        "Celestial Church of Christ", "Fifohazana",
        # NISRA's MS-B20, which names every denomination Northern Ireland
        # counted at a thousand people or more.
        "Presbyterian Church in Ireland", "Church of Ireland",
        "Methodist Church in Ireland", "Independent Methodist",
        "Free Presbyterian", "Reformed Presbyterian",
        "Non-Subscribing Presbyterian", "Congregational Church",
        # KNBS's 2019 categories: Kenya's two largest Christian groupings
        # after Protestant and Catholic.
        "Evangelical Churches", "African Instituted Churches",
        # The Philippines' two largest non-Catholic churches. Both are
        # restorationist rather than Reformation Protestant, and both are
        # counted here for the same reason the national churches above are:
        # alone, each is a one-country group.
        "Iglesia ni Cristo", "Aglipay",
        "United Church of Christ in the Philippines",
    ),
    "Orthodoxy": (
        "Orthodox", "Orthodox Christian", "Eastern Orthodox",
        "Eastern Orthodox Christian", "Christian Orthodox", "Orthodox Church",
        "Greek Orthodox", "Russian Orthodox", "Serbian Orthodox",
        "Romanian Orthodox", "Romanian Orthodox Church", "Ethiopian Orthodox",
        "Old Believer",
        # Oriental Orthodox: in communion with each other rather than with
        # Constantinople, and counted as Orthodox by every office that names
        # them.
        "Armenian Orthodox", "Armenian Apostolic",
        "Armenian Apostolic Christian", "Coptic Orthodox", "Coptic",
        "Syrian Orthodox",
    ),
    # Two bodies most offices count as Christian and a few list apart. They
    # are children of Christianity rather than folded into it: each is large
    # enough to ask about on its own -- 2,425 and 2,114 records -- and a
    # reader who wants the Christian total still gets them.
    "Jehovah's Witnesses": (
        "Jehovah's Witness", "Jehovah's Witnesses", "Jehovah Witness",
        "Jehovah’s Witness", "Jehovah's Witnesses and Bible Students",
        "Jehovah's Witness and Church of Jesus Christ",
    ),
    "Latter-day Saints": (
        "Latter-day Saints", "Latter Day Saints", "Church of Jesus Christ",
        "Church of Jesus Christ of Latter-day Saints", "Mormon",
        "Church of Jesus Christ of Latter Day Saints (Mormons)",
    ),
    # --- Islam and its branches --------------------------------------------
    "Islam": (
        "Islam", "Muslim", "Muslims", "Musalman", "Musulman", "Islamic",
        # Afrobarometer's label for a respondent who named no branch, which is
        # the plainest Muslim answer there is.
        "Muslim only",
    ),
    "Sunni Islam": (
        "Sunni", "Sunni Muslim", "Sunni only",
        # The Sufi orders. Afrobarometer offers a Senegalese respondent the
        # brotherhood rather than the faith and most take it, so a filter for
        # Islam that omits them shows the country as barely Muslim.
        "Mouridiya Brotherhood", "Mouride", "Tijaniya Brotherhood", "Tijani",
        "Qadiriya", "Qadiriya Brotherhood", "Ançardine",
    ),
    "Shia Islam": (
        "Shia", "Shia Muslim", "Shi'a", "Ismaeli", "Ismaili",
    ),
    "Ibadi Islam": ("Ibadhi", "Ibadi"),
    # Pakistan counts Ahmadis separately and by law does not count them as
    # Muslim; most of the world's offices do. The group is kept under Islam
    # and named, which is the only arrangement that neither erases the
    # community nor overwrites the census that separated it.
    "Ahmadiyya": ("Ahmadiyya", "Ahmadi", "Ahmadis", "Qadiani"),
    # --- everything else ----------------------------------------------------
    "Hinduism": ("Hindu", "Hinduism", "Hindus"),
    "Buddhism": ("Buddhist", "Buddhism", "Bouddha", "Buddhists",
                 # The Factbook's word for the Vajrayana of Bhutan,
                 # Mongolia and Kalmykia. Left alone it led three
                 # countries under its own name on a map whose
                 # Buddhist colour they should have carried.
                 "Lamaistic Buddhist", "Lamaistic", "Lamaism"),
    "Judaism": ("Jewish", "Judaism", "Jew", "Jews"),
    "Sikhism": ("Sikh", "Sikhism", "Sikha", "Sikhs"),
    "Jainism": ("Jain", "Jainism", "Jains"),
    "Taoism": ("Taoist", "Taoism", "Dao", "Daoism"),
    "Confucianism": ("Confucian", "Confucianism"),
    "Shinto": ("Shinto", "Shintoism"),
    "Zoroastrianism": ("Zoroastrian", "Zoroastrianism", "Parsi", "Parsee"),
    "Baha'i": ("Baha'i", "Bahai", "Bahá'í", "Baha'i Faith"),
    "Druze": ("Druze", "Druse"),
    "Rastafarian": ("Rastafarian", "Rastafari", "Rasta"),
    "Spiritism and Afro-Brazilian religions": (
        "Espírita", "Umbanda e Candomblé", "Spiritist", "Spiritism",
        "Candomble", "Umbanda", "African American/umbanda", "Vodoun", "Voodoo",
        "Umbanda and Candomblé", "Vodou", "Winti", "Spirtism", "Saio/Zione",
    ),
    # The world's traditional and ethnic religions, which offices name a dozen
    # ways and rarely break down further. Kept apart from Taoism, which is a
    # named tradition rather than a residual for "the local religion".
    "Folk and traditional religion": (
        "folk religion", "folk religions", "Folk religion",
        "traditional", "Traditional", "traditionalist", "Traditionalist",
        "traditional religion", "traditional beliefs", "indigenous beliefs",
        "animist", "Animist", "Animiste", "animism", "Animism",
        "ethnic religionist", "African traditionalist",
        "traditional African religion", "customary beliefs", "folk",
        # Census 2022 heads the column "Traditional African" and calls it
        # "Traditional African religion" in the prose on the same page. The
        # Factbook string is the tail of "ancestral, tribal, animist, or other
        # traditional African religions", which its parser leaves cut in half.
        "Traditional African", "Traditional African religion",
        "or other traditional African religions",
        "Shaman", "shamanist", "Badimo", "Modekngei", "Mana",
        "Traditional/Ethnic religion", "Traditional/ethnic religion",
        # Brazil's 2022 column for the religions of its indigenous peoples.
        "Indigenous traditions",
    ),
    # Maori churches. Stats NZ classifies these apart from Christian and this
    # follows it: Ratana and Ringatu are Christian in origin but are counted,
    # and understood, as Maori religions.
    "Māori religions": (
        "Ratana", "Ringatū", "Ringatu",
        "Other Māori religions, beliefs and philosophies",
    ),
    "No religion": (
        "No religion", "No religion / secular", "Sem religião", "none",
        "None", "Secular Other Spiritual and No Religious Affiliation",
        "Sin religión", "irreligion", "secular", "Non-religious",
        "No religion and secular perspectives",
        # Answers that all mean "not religious". A person filtering for "No
        # religion" and missing the twelve countries whose Factbook entry says
        # "atheist" is being shown a false map, and each of these is an
        # unambiguous statement about the respondent -- unlike the mixed
        # buckets listed under "Not stated" and the ones excluded entirely.
        "unaffiliated", "Unaffiliated",
        "non-believers", "non-believer", "no religious affiliation",
        "not religious",
        # Labels that weld the two positions below into one figure. They
        # cannot be split, so they stay at the level that contains both.
        "agnostic/atheist", "agnostic or atheist", "none/atheist",
        "nonbeliever/agnostic", "atheist or agnostic", "non-believer/agnostic",
    ),
    # Two positions several censuses count separately and side by side, and
    # which are therefore groups of their own rather than spellings of the one
    # above. Croatia is the case: its 2021 census prints "Atheists and
    # non-believers" beside "Agnostics and sceptics", two disjoint answers that
    # sum into the non-religious rather than restating it. As children they
    # sum; folded together they tripped the guard that stops a group being
    # counted twice, which was the guard being right.
    "Atheism": ("atheist", "Atheist", "atheism", "Atheists",
                "Atheists and non-believers"),
    "Agnosticism": ("agnostic", "Agnostic", "agnosticism", "Agnostics",
                    "Agnostics and sceptics"),
    "Not stated": (
        "Not stated", "Not answered", "Religious affiliation not stated",
        "Sem declaração", "Não sabe", "unspecified", "no response",
        "no answer", "unknown", "refused to answer", "not reported",
        "Object to answering", "Not elsewhere included", "declined to answer",
        "don't know/no answer", "don't know/refused", "do not know",
        "Religion not stated", "Don't know", "Does not know", "Not declared",
    ),
    "Other religions": (
        "Other", "Other religion", "Other religions", "Other Religions",
        "Outras religiosidades", "other religions", "Otras religiones",
        "Other religious affiliations",
    ),
}

# What is deliberately NOT merged, and why. Each of these looks foldable and
# is not, so the reasoning lives beside the table rather than in a commit
# message nobody will find.
#
# "Unaffiliated or not reported" (US Religion Census) stays out of "No
#     religion". It mixes people who belong to nothing with members of bodies
#     that did not report, and folding it in would turn "we cannot tell" into
#     a count of the non-religious. The bare "unaffiliated" of the Factbook is
#     folded, because there it is an answer rather than a residual.
#
# "none or unspecified", "other or none", "other/not stated",
#     "other and unspecified" stay out of everything. Each welds a real answer
#     to a non-answer, and there is no honest place to put the result.
#
# "Kirat", "Prakriti", "Bon" (Nepal) keep their own names. They are living
#     traditions with 924,204, 102,048 and 67,223 adherents respectively, and
#     dropping them into "Folk and traditional religion" would erase the only
#     census that counts them.
#
# "Jedi" (New Zealand) is left alone. It is a real recorded answer and folding
#     it into "Other religions" would hide something the census chose to show.

# A language name is usually already standard, and two countries that both
# say "Russian" already group together, because an unmapped label keys on
# itself. So this table is not a list of languages -- it is a list of the
# places where one language has two names.
#
# It stays small for a second reason. The US ACS reports bands ("German or
# other West Germanic", "Chinese (incl. Mandarin, Cantonese)") where India
# reports individual mother tongues, and a band is not a language; folding a
# band into one of its members would attribute every speaker to it.
LANGUAGE: dict[str, tuple[str, ...]] = {
    # The two Chinese languages most censuses count, each under several names.
    # "Chinese" unqualified is left alone: it is a band covering both.
    "Mandarin": ("Mandarin", "Northern Chinese", "Putonghua", "Guoyu",
                 "Mandarin Chinese"),
    "Cantonese": ("Cantonese", "Yue", "Yue Chinese"),
    # Nepal's census writes the language of the Newar people as
    # "Nepalbhasha(Newari)"; it is the same language Wikidata and the Factbook
    # call Newari.
    "Newari": ("Newari", "Nepalbhasha(Newari)", "Nepalbhasha (Newari)"),
    # te reo Maori. Stats NZ writes it "Māori" in both the language and the
    # ethnicity classification; they are different questions, and only the
    # language one is folded here.
    "Māori": ("Māori", "Maori", "te reo Māori", "te reo"),
    "Tagalog": ("Tagalog", "Filipino", "Pilipino"),
    "Panjabi": ("Panjabi", "Punjabi"),
    "Persian": ("Persian", "Farsi", "Persian (Farsi)"),
    "Dhivehi": ("Dhivehi", "Divehi", "Maldivian"),
    "Sinhala": ("Sinhala", "Sinhalese"),
    "Burmese": ("Burmese", "Myanmar"),
    "Khmer": ("Khmer", "Cambodian"),
    "Malay": ("Malay", "Bahasa Malaysia", "Bahasa Melayu"),
    "Indonesian": ("Indonesian", "Bahasa Indonesia"),
    "Dutch": ("Dutch", "Netherlandic", "Flemish"),
    "Greek": ("Greek", "Hellenic"),
    # "Moldovan" and "Moldovian" were folded in here and are not any more.
    # No source in this dataset has ever emitted either as a *language* label
    # -- checked across every built file, zero occurrences -- so the fold was
    # doing nothing, and it stopped being harmless the moment Rosstat arrived:
    # its table lists Молдавский and Румынский as separate rows of the same
    # subject in 80 of 83, and folding one into the other would have summed
    # two categories the census chose to keep apart, invisibly, in 80 places.
    # Same evidence, same answer as the Central African Republic's Fulah,
    # Fulata and Peulh. The ethnicity table never folded Moldovan and still
    # does not: there it is a nationality Moldova and Ukraine both report.
    "Romanian": ("Romanian",),
    "Norwegian": ("Norwegian", "Bokmål", "Nynorsk"),
    "Romani": ("Romani", "Romany", "Roma"),
    "New Zealand Sign Language": ("New Zealand Sign Language", "NZSL"),
    # Named individually so their own spellings unify; all of these appear in
    # more than one source under more than one form.
    "Tamil": ("Tamil",),
    "Hindi": ("Hindi",),
    "Bengali": ("Bengali", "Bangla"),
    "German": ("German", "Deutsch"),
    "French": ("French", "Français"),
    "Italian": ("Italian",),
    "Romansh": ("Romansh", "Rhaeto-Romance", "Romansch"),
    "English": ("English",),
    "Nepali": ("Nepali", "Nepalese"),
    "Samoan": ("Samoan",),
    "Tongan": ("Tongan",),
    "Spanish": ("Spanish", "Castilian", "Español"),
    "Portuguese": ("Portuguese", "Português"),
    "Afrikaans": ("Afrikaans",),
    "Maithili": ("Maithili",),
    "Bhojpuri": ("Bhojpuri",),
    "Arabic": ("Arabic",),
    "Russian": ("Russian",),
    "Urdu": ("Urdu",),
    "Vietnamese": ("Vietnamese",),
    "Turkish": ("Turkish",),
    "Swahili": ("Swahili", "Kiswahili"),
    # South Africa's official languages, each under the three forms this
    # dataset meets: the census's own spelling, the Factbook's "X or Y"
    # compound, and the bare English name other sources use.
    #
    # Two bare names are deliberately left out. "Ndebele" is Northern Ndebele
    # in Zimbabwe and Southern Ndebele in South Africa, which are different
    # languages; "Sotho" is Sesotho in Lesotho and, loosely, Sepedi in the
    # north. Folding either would merge two languages under one name. The
    # Factbook's compounds are safe because they only ever appear in the South
    # African entry.
    "isiZulu": ("isiZulu", "Zulu", "isiZulu or Zulu"),
    "isiXhosa": ("isiXhosa", "Xhosa", "isiXhosa or Xhosa"),
    "isiNdebele": ("isiNdebele", "isiNdebele or Ndebele", "Southern Ndebele"),
    "Sepedi": ("Sepedi", "Pedi", "Sepedi or Pedi", "Northern Sotho",
               "Sesotho sa Leboa"),
    "Sesotho": ("Sesotho", "Sesotho or Sotho", "Southern Sotho"),
    "Setswana": ("Setswana", "Tswana", "Setswana or Tswana"),
    "siSwati": ("siSwati", "Swati", "siSwati or Swati", "Swazi"),
    "Tshivenda": ("Tshivenda", "Venda", "Tshivenda or Venda"),
    "Xitsonga": ("Xitsonga", "Tsonga", "Xitsonga or Tsonga"),
    "South African Sign Language": ("South African Sign Language", "SASL"),
    # Mali's languages, which arrived under two spellings each because the
    # country is described by two sources at once: the Factbook at the national
    # level and the 2009 census, via the US Census Bureau, at the regional one.
    # Unmapped, every one of them keyed on itself, so the world filter offered
    # "Tamasheq" over nine Malian regions beside "Tamacheq" over Mali entire,
    # as though they were different languages spoken by different people. They
    # are the same census.
    #
    # Two of these keep the weld their source made. "Maraka/Soninke" and
    # "Sonrhai/Djerma" each name two peoples the Malian census counts together,
    # and the canonical form is the source's own spelling rather than a tidier
    # invented one -- folding them into a bare "Soninke" or "Songhai" would
    # merge a pair with one of its members the moment another country reports
    # that member alone.
    "Fula": ("Fula", "Fula/fulfulbe", "Peuhl/Foulfoulbe/Fulani",
             "Fula, Fulah, Pulaar, Pular"),
    "Maraka/Soninke": ("Maraka/Soninke",),
    "Sonrhai/Djerma": ("Sonrhai/Djerma", "Sonrai/djerma"),
    "Tamasheq": ("Tamasheq", "Tamacheq"),
    "Senufo": ("Senufo", "Senoufo"),
    # Deliberately NOT folded into "Fula": the Central African Republic's "Fulah",
# "Fulata" and "Peulh". The first and third are names for the Fula language and
# would look obviously foldable, but CAR's census lists all three as separate
# rows *of the same prefecture* -- Bamingui-Bangoran has Fulah 11.4%, Fulata
# 0.0% and Peulh 0.0% -- so its classification distinguishes them, and folding
# would sum categories the source chose to keep apart. Mali's forms are safe
# because no Malian record carries two of them at once.
#
# Residuals. Named so they stop appearing as the largest "language" in the
    # picker -- "other" reaches 92 countries and is not something anyone means
    # to filter for.
    "Other languages": ("other", "other languages", "others",
                        "other language", "Other"),
    "Language not stated": ("unspecified", "not stated", "no response",
                            "not reported", "unknown"),
}

# Ethnicity is the field where merging goes wrong most easily, because the
# categories are made by states rather than found in the world. Brazil's
# "parda", the UK's "Mixed", and the US "Two or more races" are three
# different questions with three different answer sets, and a person counted
# in one would not necessarily be counted in the others.
#
# So this table holds only two kinds of entry: the same name spelled
# differently, and the same *people* named differently by sources describing
# the same population. Everything else keeps the name its census used, which
# still groups correctly across countries -- an unmapped label keys on itself,
# so the "White" of 27 countries is already one filter.
ETHNICITY: dict[str, tuple[str, ...]] = {
    # Spelling and diacritics of one people.
    "Māori": ("Māori", "Maori"),
    "Romani": ("Romani", "Romany", "Roma", "Rroma", "Gypsy"),
    # Singular and plural, and the noun beside the adjective. The Baltic
    # population registers write "Russians" and "Poles" where every other
    # source in this dataset writes "Russian" and "Polish", and unmapped they
    # became a second entry for the same people: "Russians" in two countries
    # beside "Russian" in twelve, neither of which is the filter anyone wants.
    # This is the first kind of entry the table admits -- one name spelled two
    # ways -- and not a merge of two states' categories.
    "Russian": ("Russian", "Russians"),
    "Latvian": ("Latvian", "Latvians"),
    "Estonian": ("Estonian", "Estonians"),
    "Lithuanian": ("Lithuanian", "Lithuanians"),
    "Ukrainian": ("Ukrainian", "Ukrainians"),
    "Belarusian": ("Belarusian", "Belarusians"),
    "Polish": ("Polish", "Poles"),
    "Jewish": ("Jewish", "Jews"),
    # One South African category spelled two ways: the census writes
    # "Coloured" and the Factbook "Colored". This is a spelling, not a merge
    # of two states' categories -- both describe the same census answer in the
    # same country.
    "Coloured": ("Coloured", "Colored"),
    # Mexico writes its census category two ways in the same release.
    "Afro-descendant": (
        "Afro-descendant", "African descent", "Afro-Mexican or Afro-descendant",
        "Afrodescendiente", "of African descent",
    ),
    # Residuals, for the same reason as the language ones: "other" reaches 142
    # countries and tops the picker while meaning nothing in particular.
    "Other ethnicity": ("other", "other ethnicity", "others",
                        "Other Ethnicity", "Other",
                        "Other ethnic nationalities",
                        # Latvia's residual is both at once and says so: it
                        # holds people who selected no ethnicity and people
                        # who did not indicate one, beside people who gave an
                        # ethnicity outside the nine named. It cannot be split,
                        # so it goes with "other" and the record's note says
                        # what is inside it.
                        "Other ethnicities, including not selected and not "
                        "indicated ethnicity"),
    "Ethnicity not stated": ("unspecified", "not stated", "no response",
                             "not reported", "unknown",
                             "Ethnic nationality unknown"),
}

# What is deliberately NOT merged here, and why:
#
# "White" / "European" / "Caucasian" are three states' categories, not three
#     words for one. New Zealand's "European" includes people the US census
#     would not call White, and vice versa. They stay apart.
#
# "Black" / "African" / "Afro-descendant" likewise. "African" in a European
#     census usually means place of origin; "Black" in the US and UK is a
#     self-identified race category; only the Latin American
#     afrodescendiente/African-descent pair is close enough to fold.
#
# "Mestizo" / "Mixed" / "Two or more races" / "parda" are four constructions
#     of mixedness with four different rules, and merging them would invent a
#     worldwide category no census asked about.
#
# "Indian" / "East Indian" / "Asian Indian" are not folded either: in the
#     Caribbean "East Indian" is a descent category, in Singapore "Indian" is
#     one of four official races, and in the US "Asian Indian" is a census
#     race. Related, but counted on different bases.

# ---------------------------------------------------------------------------
# The 2020 Russian census names its groups in Russian
#
# Rosstat publishes 147 nationalities and 176 native languages, and every one
# arrived as Cyrillic. On the map that made 83 federal subjects read
# "Русские 90.2%", and in the world filter it made "Русские" a different
# answer from the "Russian" already there from Estonia, Latvia and Lithuania --
# the same people, counted by four censuses, split across two alphabets.
#
# So these are translations, and it is worth being exact about why that is
# allowed here when a romanisation was refused for the *shapes*. Guessing an
# English spelling of a place name to match a boundary is dangerous because a
# wrong guess attaches real figures to the wrong region and nothing shows it.
# A group label is not a key into anything: it is the name a bar carries, and
# these are declared one by one in a table rather than transliterated by rule.
#
# The one thing a wrong entry here *can* do is merge two groups, because
# canonicalise() sums rows that reach the same name. That is what the tests
# check: every label the adapter emits appears exactly once below, and no two
# labels in one record resolve to the same name.
#
# Ordered by the number of people each covers nationally, largest first.

RUSSIAN_ETHNICITY: dict[str, str] = {
    "Русские":                                               "Russian",
    "Татары":                                                "Tatar",
    "Чеченцы":                                               "Chechen",
    "Башкиры":                                               "Bashkir",
    "Указавшие другие ответы о национальной принадлежности": "Other ethnicity",
    "Чуваши":                                                "Chuvash",
    "Аварцы":                                                "Avar",
    "Армяне":                                                "Armenian",
    "Украинцы":                                              "Ukrainian",
    "Даргинцы":                                              "Dargin",
    "Казахи":                                                "Kazakh",
    "Кумыки":                                                "Kumyk",
    "Нет национальной принадлежности":                       "No ethnicity",
    "Кабардинцы":                                            "Kabardian",
    "Ингуши":                                                "Ingush",
    "Лезгины":                                               "Lezgin",
    "Осетины":                                               "Ossetian",
    "Мордва":                                                "Mordvin",
    "Якуты":                                                 "Yakut",
    "Азербайджанцы":                                         "Azerbaijani",
    "Буряты":                                                "Buryat",
    "Марийцы":                                               "Mari",
    "Удмурты":                                               "Udmurt",
    "Таджики":                                               "Tajik",
    "Узбеки":                                                "Uzbek",
    "Тувинцы":                                               "Tuvan",
    "Карачаевцы":                                            "Karachay",
    "Белорусы":                                              "Belarusian",
    "Немцы":                                                 "German",
    "Калмыки":                                               "Kalmyk",
    "Лакцы":                                                 "Lak",
    "Цыгане":                                                "Romani",
    "Табасараны":                                            "Tabasaran",
    "Коми":                                                  "Komi",
    "Киргизы":                                               "Kyrgyz",
    "Балкарцы":                                              "Balkar",
    "Турки":                                                 "Turkish",
    "Черкесы":                                               "Circassian",
    "Грузины":                                               "Georgian",
    "Адыгейцы":                                              "Adyghe",
    "Ногайцы":                                               "Nogai",
    "Корейцы":                                               "Korean",
    "Евреи":                                                 "Jewish",
    "Алтайцы":                                               "Altai",
    "Молдаване":                                             "Moldovan",
    "Хакасы":                                                "Khakas",
    "Коми-пермяки":                                          "Komi-Permyak",
    "Греки":                                                 "Greek",
    "Ненцы":                                                 "Nenets",
    "Абазины":                                               "Abaza",
    "Туркмены":                                              "Turkmen",
    "Эвенки":                                                "Evenk",
    "Агулы":                                                 "Agul",
    "Рутульцы":                                              "Rutul",
    "Карелы":                                                "Karelian",
    "Ханты":                                                 "Khanty",
    "Езиды":                                                 "Yazidi",
    "Курды":                                                 "Kurd",
    "Поляки":                                                "Polish",
    "Эвены":                                                 "Even",
    "Китайцы":                                               "Chinese",
    "Чукчи":                                                 "Chukchi",
    "Арабы":                                                 "Arab",
    "Литовцы":                                               "Lithuanian",
    "Цахуры":                                                "Tsakhur",
    "Манси":                                                 "Mansi",
    "Нанайцы":                                               "Nanai",
    "Болгары":                                               "Bulgarian",
    "Шорцы":                                                 "Shor",
    "Гагаузы":                                               "Gagauz",
    "Латыши":                                                "Latvian",
    "Долганы":                                               "Dolgan",
    "Абхазы":                                                "Abkhaz",
    "Вьетнамцы":                                             "Vietnamese",
    "Финны":                                                 "Finnish",
    "Эстонцы":                                               "Estonian",
    "Индийцы":                                               "Indian",
    "Коряки":                                                "Koryak",
    "Нагайбаки":                                             "Nagaybak",
    "Вепсы":                                                 "Veps",
    "Ассирийцы":                                             "Assyrian",
    "Сойоты":                                                "Soyot",
    "Турки-месхетинцы":                                      "Meskhetian Turk",
    "Крымские татары":                                       "Crimean Tatar",
    "Нивхи":                                                 "Nivkh",
    "Талыши":                                                "Talysh",
    "Афганцы":                                               "Afghan",
    "Селькупы":                                              "Selkup",
    "Дунгане":                                               "Dungan",
    "Ительмены":                                             "Itelmen",
    "Удины":                                                 "Udi",
    "Ульчи":                                                 "Ulch",
    "Кумандинцы":                                            "Kumandin",
    "Персы":                                                 "Persian",
    "Телеуты":                                               "Teleut",
    "Уйгуры":                                                "Uyghur",
    "Сербы":                                                 "Serbian",
    "Хемшилы":                                               "Hemshin",
    "Бесермяне":                                             "Besermyan",
    "Шапсуги":                                               "Shapsug",
    "Юкагиры":                                               "Yukaghir",
    "Румыны":                                                "Romanian",
    "Эскимосы":                                              "Yupik",
    "Камчадалы":                                             "Kamchadal",
    "Саамы":                                                 "Sami",
    "Французы":                                              "French",
    "Венгры":                                                "Hungarian",
    "Итальянцы":                                             "Italian",
    "Удэгейцы":                                              "Udege",
    "Монголы":                                               "Mongol",
    "Испанцы":                                               "Spanish",
    "Британцы":                                              "British",
    "Американцы":                                            "American",
    "Кеты":                                                  "Ket",
    "Чехи":                                                  "Czech",
    "Чуванцы":                                               "Chuvan",
    "Каракалпаки":                                           "Karakalpak",
    "Тофалары":                                              "Tofalar",
    "Кубинцы":                                               "Cuban",
    "Нганасаны":                                             "Nganasan",
    "Японцы":                                                "Japanese",
    "Таты":                                                  "Tat",
    "Русины":                                                "Rusyn",
    "Орочи":                                                 "Oroch",
    "Негидальцы":                                            "Negidal",
    "Памирцы":                                               "Pamiri",
    "Пакистанцы":                                            "Pakistani",
    "Алеуты":                                                "Aleut",
    "Чулымцы":                                               "Chulym",
    "Уйльта":                                                "Uilta",
    "Горские евреи":                                         "Mountain Jew",
    "Тазы":                                                  "Taz",
    "Ижорцы":                                                "Izhorian",
    "Энцы":                                                  "Enets",
    "Караимы":                                               "Karaim",
    "Словаки":                                               "Slovak",
    "Хорваты":                                               "Croatian",
    "Македонцы":                                             "Macedonian",
    "Словенцы":                                              "Slovene",
    "Водь":                                                  "Votic",
    "Боснийцы":                                              "Bosnian",
    "Черногорцы":                                            "Montenegrin",
    "Крымчаки":                                              "Krymchak",
    "Кереки":                                                "Kerek",
    "Среднеазиатские евреи":                                 "Bukharan Jew",
    "Грузинские евреи":                                      "Georgian Jew",
    "Цыгане среднеазиатские":                                "Central Asian Romani",
}

RUSSIAN_LANGUAGE: dict[str, str] = {
    "Русский":                      "Russian",
    "Татарский":                    "Tatar",
    "Чеченский":                    "Chechen",
    "Башкирский":                   "Bashkir",
    "Аварский":                     "Avar",
    "Чувашский":                    "Chuvash",
    "Армянский":                    "Armenian",
    "Кабардино-черкесский":         "Kabardian",
    "Даргинский":                   "Dargin",
    "Кумыкский":                    "Kumyk",
    "Ингушский":                    "Ingush",
    "Якутский":                     "Yakut",
    "Осетинский":                   "Ossetian",
    "Лезгинский":                   "Lezgin",
    "Казахский":                    "Kazakh",
    "Бурятский":                    "Buryat",
    "Азербайджанский":              "Azerbaijani",
    "Карачаево-балкарский":         "Karachay-Balkar",
    "Марийский":                    "Mari",
    "Таджикский":                   "Tajik",
    "Тувинский":                    "Tuvan",
    "Мордовский":                   "Mordvin",
    "Удмуртский":                   "Udmurt",
    "Узбекский":                    "Uzbek",
    "Украинский":                   "Ukrainian",
    "Калмыцкий":                    "Kalmyk",
    "Лакский":                      "Lak",
    "Табасаранский":                "Tabasaran",
    "Цыганский":                    "Romani",
    "Киргизский":                   "Kyrgyz",
    "Турецкий":                     "Turkish",
    "Адыгейский":                   "Adyghe",
    "Ногайский":                    "Nogai",
    "Коми":                         "Komi",
    "Грузинский":                   "Georgian",
    "Алтайский":                    "Altai",
    "Хакасский":                    "Khakas",
    "Эрзя-мордовский":              "Erzya",
    "Молдавский":                   "Moldovan",
    "Белорусский":                  "Belarusian",
    "Курдский":                     "Kurdish",
    "Коми-пермяцкий":               "Komi-Permyak",
    "Абазинский":                   "Abaza",
    "Ненецкий":                     "Nenets",
    "Туркменский":                  "Turkmen",
    "Дагестанский":                 "Dagestani",
    "Указавшие другие ответы":      "Other languages",
    "Агульский":                    "Agul",
    "Рутульский":                   "Rutul",
    "Немецкий":                     "German",
    "Мокша-мордовский":             "Moksha",
    "Андийский":                    "Andi",
    "Горномарийский":               "Hill Mari",
    "Цезский":                      "Tsez",
    "Китайский":                    "Chinese",
    "Корейский":                    "Korean",
    "Арабский":                     "Arabic",
    "Греческий":                    "Greek",
    "Хантыйский":                   "Khanty",
    "Цахурский":                    "Tsakhur",
    "Каратинский":                  "Karata",
    "Карельский":                   "Karelian",
    "Эвенкийский":                  "Evenki",
    "Чукотский":                    "Chukchi",
    "Бежтинский":                   "Bezhta",
    "Английский":                   "English",
    "Ахвахский":                    "Akhvakh",
    "Вьетнамский":                  "Vietnamese",
    "Эвенский":                     "Even",
    "Адыгский":                     "Circassian",
    "Нанайский":                    "Nanai",
    "Шорский":                      "Shor",
    "Абхазский":                    "Abkhaz",
    "Долганский":                   "Dolgan",
    "Хинди":                        "Hindi",
    "Чамалинский":                  "Chamalal",
    "Ботлихский":                   "Botlikh",
    "Литовский":                    "Lithuanian",
    "Гагаузский":                   "Gagauz",
    "Тиндальский":                  "Tindi",
    "Корякский":                    "Koryak",
    "Румынский":                    "Romanian",
    "Болгарский":                   "Bulgarian",
    "Иврит":                        "Hebrew",
    "Еврейский":                    "Jewish (unspecified)",
    "Французский":                  "French",
    "Гунзибский":                   "Hunzib",
    "Персидский":                   "Persian",
    "Хваршинский":                  "Khwarshi",
    "Латышский":                    "Latvian",
    "Польский":                     "Polish",
    "Годоберинский":                "Godoberi",
    "Испанский":                    "Spanish",
    "Эстонский":                    "Estonian",
    "Дунганский":                   "Dungan",
    "Талышский":                    "Talysh",
    "Ассирийский":                  "Assyrian",
    "Багвалинский":                 "Bagvalal",
    "Мансийский":                   "Mansi",
    "Пушту":                        "Pashto",
    "Крымскотатарский":             "Crimean Tatar",
    "Сербскохорватский":            "Serbo-Croatian",
    "Удинский":                     "Udi",
    "Арчинский":                    "Archi",
    "Селькупский":                  "Selkup",
    "Телеутский":                   "Teleut",
    "Русский жестовый язык глухих": "Russian Sign Language",
    "Нивхский":                     "Nivkh",
    "Вепсский":                     "Veps",
    "Итальянский":                  "Italian",
    "Финский":                      "Finnish",
    "Монгольский":                  "Mongolian",
    "Тюркский":                     "Turkic",
    "Тубаларский":                  "Tubalar",
    "Ульчский":                     "Ulch",
    "Русинский":                    "Rusyn",
    "Эскимосский":                  "Yupik",
    "Ительменский":                 "Itelmen",
    "Португальский":                "Portuguese",
    "Венгерский":                   "Hungarian",
    "Уйгурский":                    "Uyghur",
    "Татский":                      "Tat",
    "Удэгейский":                   "Udege",
    "Кумандинский":                 "Kumandin",
    "Челканский":                   "Chelkan",
    "Гинухский":                    "Hinukh",
    "Идиш":                         "Yiddish",
    "Японский":                     "Japanese",
    "Юкагирский":                   "Yukaghir",
    "Нганасанский":                 "Nganasan",
    "Каракалпакский":               "Karakalpak",
    "Чешский":                      "Czech",
    "Дари":                         "Dari",
    "Саамский":                     "Sami",
    "Словенский":                   "Slovene",
    "Мегрельский":                  "Mingrelian",
    "Бенгали":                      "Bengali",
    "Суахили":                      "Swahili",
    "Лугово-восточный марийский":   "Meadow Mari",
    "Алюторский":                   "Alyutor",
    "Ногайско-карагашский":         "Nogai-Karagash",
    "Булгарский":                   "Bulgar",
    "Тайский":                      "Thai",
    "Тамильский":                   "Tamil",
    "Кетский":                      "Ket",
    "Урду":                         "Urdu",
    "Латинский":                    "Latin",
    "Албанский":                    "Albanian",
    "Амхарский":                    "Amharic",
    "Алеутский":                    "Aleut",
    "Македонский":                  "Macedonian",
    "Орочский":                     "Oroch",
    "Уйльта":                       "Uilta",
    "Словацкий":                    "Slovak",
    "Шведский":                     "Swedish",
    "Нидерландский":                "Dutch",
    "Индонезийский":                "Indonesian",
    "Ижорский":                     "Izhorian",
    "Старославянский":              "Old Church Slavonic",
    "Энецкий":                      "Enets",
    "Тофаларский":                  "Tofalar",
    "Датский":                      "Danish",
    "Норвежский":                   "Norwegian",
    "Чулымско-тюркский":            "Chulym",
    "Малайский":                    "Malay",
    "Тибетский":                    "Tibetan",
    "Негидальский":                 "Negidal",
    "Ирландский":                   "Irish",
    "Водский":                      "Votic",
    "Юртовско-татарский":           "Yurt Tatar",
    "Бирманский":                   "Burmese",
    "Исландский":                   "Icelandic",
    "Караимский":                   "Karaim",
    "Керекский":                    "Kerek",
    "Югский":                       "Yug",
    "Юитский":                      "Siberian Yupik",
}

# ---------------------------------------------------------------------------
# Sources that publish their groups in their own language
#
# Brazil's 2022 census, read from IBGE's SIDRA API. The religion labels already
# reached the right canonical groups through the tables above -- "Católica
# Apostólica Romana" has folded into Christianity for as long as Brazil has
# been on this map -- and the states still read "Católica Apostólica Romana
# 56.7%", because those tables reach the *index* and not the record. Same
# half-fix as Russia's, found the same way.
#
# Two of the five colour-or-race categories are deliberately not translated
# into a category some other country also has.
#
# "Parda" becomes Pardo and stays Brazil's own. The table above says why in the
# case it was written for: Brazil's parda, the UK's Mixed and the US "two or
# more races" are three different questions with three different answer sets,
# and a person counted in one would not necessarily be counted in the others.
# Translating it to "Mixed" would merge 92 million people into a category the
# census did not ask about.
#
# "Amarela" becomes Asian, which is the opposite call and needs its own reason:
# Brazil's own country record, from the Factbook, already calls these people
# Asian. Leaving the states as "Amarela" keeps a country apart from its own
# states, which is the split this whole exercise exists to close.
BRAZIL_ETHNICITY: dict[str, str] = {
    "Branca":   "White",
    "Parda":    "Pardo",
    "Preta":    "Black",
    "Amarela":  "Asian",
    "Indígena": "Indigenous",
}

BRAZIL_RELIGION: dict[str, str] = {
    "Católica Apostólica Romana": "Roman Catholic",
    "Evangélicas":                "Evangelical",
    "Espírita":                   "Spiritism",
    "Umbanda e Candomblé":        "Umbanda and Candomblé",
    "Tradições indígenas":        "Indigenous traditions",
    "Outras religiosidades":      "Other religions",
    "Sem religião":               "No religion",
    "Sem declaração":             "Not stated",
    "Não sabe":                   "Does not know",
}

# Keyed by the body that publishes the labels, because the tables are facts
# about a source rather than about a language: a second Portuguese-speaking
# census would have its own categories and its own translations of them.
TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "Rosstat": {"ethnicity": RUSSIAN_ETHNICITY, "language": RUSSIAN_LANGUAGE},
    "IBGE": {"ethnicity": BRAZIL_ETHNICITY, "religion": BRAZIL_RELIGION},
}

# Kept for the Russian adapter and its tests, which name it directly.
RUSSIAN = TRANSLATIONS["Rosstat"]


def translate(source: str, field: str, label: str) -> str | None:
    """The English name for one group of one source, or None if it has none.

    Applied by the adapter rather than folded into the tables above, because
    the tables only reach the group *index* -- the name a bar carries on the
    map comes from the record itself. Folding left the picker saying "Russian"
    while Tatarstan still read "Русские 40.3%", which is half a fix.

    None is a refusal, not a fallback. A label with no entry here would
    otherwise reach the map in its own language, and one untranslated row in a
    chart of translated ones reads as a different kind of thing rather than as
    the gap in this table that it is.
    """
    return TRANSLATIONS.get(source, {}).get(field, {}).get(" ".join(label.split()))


def translate_russian(field: str, label: str) -> str | None:
    """Rosstat's, by the name the Russian adapter and its tests already use."""
    return translate("Rosstat", field, label)


# ---------------------------------------------------------------------------
# The hierarchy
# ---------------------------------------------------------------------------
#
# Canonical names above say which labels mean the same thing. This says which
# of those names sit inside which, and it is what lets one map answer two
# questions: "where are Catholics" and "where are Christians", off the same
# rows, without a source ever being asked for both.
#
# Three properties are load-bearing.
#
# **A child's share is part of its parent's.** Selecting a parent sums every
# descendant's rows, so Christianity over Poland counts a "Roman Catholic"
# row that never says the word Christian. This is only sound because no
# source publishes a level beside its own parent; ``check_no_double_counting``
# stops the build if one starts to.
#
# **A family is a defensible cross-border statement, a leaf often is not.**
# Two countries that both report Catholics are reporting the same thing. Two
# that both report "White" are not, quite -- so the ethnicity tree puts the
# census race-like categories in a family of their own, apart from the named
# peoples, rather than pretending one rolls into the other.
#
# **An unmapped name is a top-level group.** Nothing is lost by being absent
# from this table; it just has no parent to be counted into.

# child canonical name -> parent canonical name, per field.
PARENT: dict[str, dict[str, str]] = {
    "religion": {
        "Catholicism": "Christianity",
        "Protestantism": "Christianity",
        "Orthodoxy": "Christianity",
        "Jehovah's Witnesses": "Christianity",
        "Latter-day Saints": "Christianity",
        "Sunni Islam": "Islam",
        "Shia Islam": "Islam",
        "Ibadi Islam": "Islam",
        "Ahmadiyya": "Islam",
        "Atheism": "No religion",
        "Agnosticism": "No religion",
    },
    # Genealogical classification, as the standard references give it. A
    # family is one hue on the map and closely related languages are shades of
    # it, which is why the branch level exists between the two: Slavic
    # languages should look like each other and not like Hindi, though both
    # are Indo-European.
    # Language and ethnicity nest in ``group_tree``, which holds the wider
    # tables and the tiers above them. Religion's nesting stays here because
    # it is a fact about the labels: a census that writes "Roman Catholic" has
    # named a tradition of Christianity, the same kind of statement as saying
    # "Muslim" and "Islam" are one word for one answer.
}


HUE: dict[str, dict[str, str]] = {
    "religion": {
        "Christianity": "#3b6fd4",
        "Catholicism": "#c0392b",
        "Protestantism": "#3b6fd4",
        "Orthodoxy": "#7d3c98",
        "Latter-day Saints": "#5dade2",
        "Jehovah's Witnesses": "#2e86c1",
        "Islam": "#1e8449",
        "Sunni Islam": "#1e8449",
        "Shia Islam": "#52be80",
        "Ahmadiyya": "#82e0aa",
        "Ibadi Islam": "#0e6251",
        "Hinduism": "#e67e22",
        "Buddhism": "#d4ac0d",
        "Judaism": "#5d6d7e",
        "Sikhism": "#d35400",
        "Jainism": "#b9770e",
        "Folk and traditional religion": "#8d6e63",
        "Spiritism and Afro-Brazilian religions": "#a569bd",
        "Māori religions": "#af7ac5",
        "Shinto": "#e59866",
        "Taoism": "#dc7633",
        "Confucianism": "#ca6f1e",
        "Zoroastrianism": "#b7950b",
        "Baha'i": "#f5b041",
        "Druze": "#48c9b0",
        "Rastafarian": "#58d68d",
        "No religion": "#95a5a6",
        "Atheism": "#7f8c8d",
        "Agnosticism": "#aab7b8",
        "Other religions": "#c39bd3",
        "Not stated": "#bdc3c7",
        "Unaffiliated or not reported": "#aeb6bf",
    },
}


def parent_of(field: str, name: str) -> str | None:
    """The group ``name`` rolls up into, or None when it is top level.

    PARENT above is the nesting that is a fact about the labels themselves --
    Catholicism inside Christianity, Sunni inside Islam. The tiers above that
    (Abrahamic religions, Indo-European languages, African ancestry) live in
    ``group_tree``, which also knows how to read a band or a qualified
    spelling. Imported here rather than at module scope because group_tree
    reads this module's tables; neither import runs at the other's import
    time, so there is no cycle.
    """
    import group_tree
    return group_tree.parent_of(field, name)


def ancestry(field: str, name: str) -> list[str]:
    """``name`` and every group above it, nearest first.

    Guarded against a cycle rather than trusting the table: a typo that made
    two groups each other's parent would otherwise hang the build.
    """
    trail = [name]
    seen = {name}
    while True:
        up = parent_of(field, trail[-1])
        if up is None or up in seen:
            return trail
        trail.append(up)
        seen.add(up)


def family(field: str, name: str) -> str:
    """The top of ``name``'s tree: its hue on the most-populous-group map."""
    return ancestry(field, name)[-1]


def children(field: str) -> dict[str, list[str]]:
    """parent -> its direct children, for one field, over the whole tree."""
    import group_tree
    out: dict[str, list[str]] = {}
    merged = dict(PARENT.get(field, {}))
    merged.update(group_tree.parents(field))
    for child, up in merged.items():
        out.setdefault(up, []).append(child)
    for kids in out.values():
        kids.sort()
    return out


def roll_up(counts: dict[str, float], field: str,
            ) -> dict[str, float]:
    """Add every group's share into each of its ancestors.

    The result holds both levels: ``{"Catholicism": 30, "Christianity": 30}``
    from one Catholic row, so a caller can read either without summing twice.
    A parent's own rows are already in it -- a source that says "Christian"
    beside "Catholic" means people who named the religion and no tradition,
    and the two are disjoint answers to one question.

    Measured before it was relied on: of 1,824 shipped records that carry a
    family label beside one of its traditions, none is a total row restated.
    Afrobarometer is the pattern -- a respondent who answered "Christian only"
    is counted once, under Christianity, and never again under a denomination
    they did not name.
    """
    out: dict[str, float] = {}
    for name, value in counts.items():
        for step in ancestry(field, name):
            out[step] = out.get(step, 0.0) + value
    return out


def share_of(counts: dict[str, float], field: str, group: str) -> float:
    """One group's share, its descendants included."""
    return roll_up(counts, field).get(group, 0.0)


def hue(field: str, name: str) -> str | None:
    """The group's own colour, or the nearest one above it in the tree."""
    import group_tree
    return group_tree.hue(field, name)


# Groups that are the absence of an answer rather than an answer: a residual
# "other", or a non-response. They are real and must be shown -- a bar that
# quietly drops 20% of a population is the failure this project cares about
# most -- but nobody browses the world looking for them, so the picker sorts
# them last and says what they are.
RESIDUAL: frozenset[str] = frozenset({
    "Other religions", "Not stated", "Unaffiliated or not reported",
    "Other languages", "Language not stated",
    "Other ethnicity", "Ethnicity not stated",
    # Labels that weld a real answer to a non-answer. They are deliberately
    # merged into nothing -- there is no honest place to put "other or none"
    # -- and they are just as deliberately marked here, because a map that
    # colours a country for its largest group must not answer "which religion
    # is largest" with a bucket that is partly the absence of an answer.
    "other or none", "Other, none, or not stated", "none or unspecified",
    "none/unspecified", "none or refused", "other/none/unspecified",
    "other or not stated", "none or not stated", "Other and unspecified",
    "Other or unspecified", "other/not stated", "Other/not stated",
    "No ethnic group", "Unknown ethnicity", "Not declared",
    "Some other race (non-Hispanic)", "Other and unspecified languages",
    # A marker the source prints where it has nothing to report. It is not a
    # group at all, and until it was named here it read as one: grey on the
    # map, indistinguishable from a country the map has no data for, but
    # counted in the composition and able to lead a unit.
    "No Data", "No religion data", "not applicable", "undeclared",
    "Not applicable", "Undeclared", "other or unaffiliated",
    "other and unaffiliated", "agnostics and other", "other",
    "Other tribe", "Other groups", "other minorities", "ethnic minorities",
    "Related to regional origin (badio/sampadjudo)",
    "Indigenous languages, n.o.s.", "Indigenous languages, n.i.e.",
    "indigenous languages", "other languages/dialects",
    "other traditional religions", "other Mozambican languages",
})


def is_residual(name: str) -> bool:
    return name in RESIDUAL


TABLES: dict[str, dict[str, tuple[str, ...]]] = {
    "religion": RELIGION,
    "language": LANGUAGE,
    "ethnicity": ETHNICITY,
}


def key(label: str) -> str:
    """The form labels are compared in: case and surrounding space ignored.

    Capitalisation is a house style, not a distinction. The Factbook writes
    "no religion" and a census writes "No religion"; matching them literally
    left the world filter offering both, one reaching ten countries at the
    national level and the other six countries' provinces, as though they were
    different answers to the question.
    """
    return " ".join(label.split()).lower()


def lookup(field: str) -> dict[str, str]:
    """Source label -> canonical name, for one field."""
    out: dict[str, str] = {}
    for canonical, labels in TABLES.get(field, {}).items():
        for label in labels:
            out[key(label)] = canonical
    return out


def canonicalise(rows: Iterable[dict[str, Any]], field: str) -> dict[str, float]:
    """Sum one record's composition into canonical groups.

    Labels with no canonical name keep their own, so nothing is dropped: an
    unmapped group stays filterable under exactly the name its census used.
    """
    table = lookup(field)
    out: dict[str, float] = {}
    for row in rows or ():
        pct = row.get("pct")
        if not isinstance(pct, (int, float)):
            continue
        label = row.get("group", "")
        name = table.get(key(label), label)
        out[name] = out.get(name, 0.0) + pct
    return out


def check_no_double_counting(rows: Iterable[dict[str, Any]], field: str,
                             ) -> list[str]:
    """Names in one record that would be summed with their own parent.

    Rolling children into a parent is only safe while no source reports both
    levels at once. If one ever does -- an "ABS Christianity Total" row beside
    its denominations -- this returns the offending labels rather than letting
    the total quietly double.
    """
    table = lookup(field)
    seen: dict[str, list[str]] = {}
    for row in rows or ():
        if not isinstance(row.get("pct"), (int, float)):
            continue
        label = key(row.get("group", ""))
        canonical = table.get(label, label)
        seen.setdefault(canonical, []).append(label)
    # A canonical group reached by its own name AND by a *different* label that
    # rolls into it means the source published the parent and the child side by
    # side. The same label twice is a different thing -- the Factbook lists
    # Bissa twice for Burkina Faso -- and summing those is right, not a fault.
    #
    # What this cannot see is a parent published under some other label: a
    # plain "Christian" row above Anglican, Baptist and the rest. Names cannot
    # settle that, because the same word is usually a residual instead -- the
    # Factbook gives Sint Maarten "Christian" 4.1% beside Protestant 41.9%,
    # meaning people who said only "Christian", which should be summed.
    #
    # Detecting it by arithmetic was tried and rejected. A parent equals the
    # sum of its children, so "largest is within 1% of the rest combined"
    # finds the ABS "Christianity Total" shape exactly -- and also fires on 22
    # of the ~49,000 shipped records, every one a coincidence of the form
    # "the biggest group happens to equal the others added up" (Bay County,
    # Florida: Catholic 19.9 against Protestant 18.9 + Latter-day Saints 0.5 +
    # Jehovah's Witnesses 0.4). At that false-positive rate the warning costs
    # more attention than the gap it covers, so the gap is documented instead.
    # Compared in key() form on both sides: the labels have been folded, and
    # the canonical name is a display string, so "Christianity" has to be
    # folded too or a parent beside its child stops being reported.
    #
    # A residual is never a parent, so a residual reached twice is never this
    # fault. Northern Ireland is the case: NISRA writes "Other Religions" where
    # the ONS writes "Other religion", both mean everything the question did
    # not name, and the United Kingdom's rolled-up record carries one row from
    # each office. Adding two catch-alls together is right -- there is no third
    # figure they are both part of -- but "Other Religions" lowercases to the
    # canonical name exactly, so without this the build stopped on it.
    return [c for c, labels in seen.items()
            if len(set(labels)) > 1 and key(c) in labels and not is_residual(c)]
