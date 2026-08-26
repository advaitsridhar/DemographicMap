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
    "Christianity": (
        "Christian", "Christianity", "Christians", "Chretien", "Chrétien",
        # Denominations and traditions. No source publishes both a Christian
        # total and its denominations -- the guard below enforces that -- so
        # these roll up rather than double.
        "Catholic", "Roman Catholic", "Catholicism", "Catholics",
        "Católica Apostólica Romana", "Catholique", "Catolica",
        "Protestant", "Protestants", "Protestante", "Evangélicas",
        "Protestant and evangelical", "other Protestant",
        "Evangelical", "Evangelical Christian", "Evangelical Lutheran",
        "Evangelical, Born Again and Fundamentalist", "Evangelical/Protestant",
        "Orthodox", "Orthodox Christian", "Eastern Orthodox",
        "Eastern Orthodox Christian", "Greek Orthodox", "Russian Orthodox",
        "Serbian Orthodox", "Romanian Orthodox", "Ethiopian Orthodox",
        "Armenian Orthodox", "Coptic Orthodox", "Syrian Orthodox",
        "Anglican", "Church of England", "Episcopal",
        "Baptist", "Methodist", "Presbyterian",
        "Presbyterian, Congregational and Reformed", "Reformed",
        "Lutheran", "Pentecostal", "Adventist", "Seventh Day Adventist",
        "Seventh-day Adventist", "Congregational", "Moravian", "Mennonite",
        "New Apostolic", "Apostolic", "Kimbanguist", "Quaker",
        # Two bodies most offices count as Christian and a few list apart.
        # They are folded here because the alternative -- a "Jehovah's Witness"
        # group reaching 27 countries and a "Christianity" group that omits
        # them -- describes the same people twice under different headings.
        "Jehovah's Witness", "Jehovah's Witnesses", "Jehovah Witness",
        "Latter-day Saints", "Church of Jesus Christ",
        "Church of Jesus Christ of Latter-day Saints", "Mormon",
        "Other Christian", "Other Christians", "other Christians",
        "Other Christian religions", "Christian nfd", "Christian, unspecified",
        # National and regional churches, each named only by its own country's
        # entry. Folding them is what lets a map of Christianity include
        # Iceland, Norway, Armenia and Kiribati at all -- unfolded, each is a
        # one-country group and the country reads as having no Christians.
        "Church of Norway", "Church of Sweden", "Church of Iceland",
        "Evangelical Lutheran Church of Iceland",
        "Independent Congregation of Reykjavik",
        "Independent Congregation of Hafnarfjordur",
        "Evangelical Church of the Augsburg Confession",
        "Armenian Apostolic", "Armenian Apostolic Christian",
        "Christian Orthodox", "Old Believer", "Greek Catholic",
        "Calvinist", "Reformed Christian", "Protestant Reformed",
        "Evangelical Reformist", "Protestant Evangelical",
        "Evangelical and Pentecostal", "Evangelical or Protestant",
        "Evangelical/Protestant", "Protestant/Anglican",
        "Assembly of God", "Salvation Army", "Salutiste",
        "Iglesia ni Cristo", "Kiribati Protestant Church",
        "Kiribati Uniting Church", "Congregational Christian Church",
        "Ekalesia Niue", "Church of Jesus Christ in Madagascar/Malagasy",
        "Awakening Churches/Christian Revival", "Apostolic Sect",
        "Universal Kingdom of God", "Worship Centre",
        "Jehovah's Witness and Church of Jesus Christ", "Latter Day Saints",
    ),
    "Islam": (
        "Islam", "Muslim", "Muslims", "Musalman", "Musulman", "Islamic",
        "Sunni", "Sunni Muslim", "Shia", "Shia Muslim", "Shi'a",
        "Ahmadiyya", "Ibadhi",
    ),
    "Hinduism": ("Hindu", "Hinduism", "Hindus"),
    "Buddhism": ("Buddhist", "Buddhism", "Bouddha", "Buddhists"),
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
        "Shaman", "shamanist", "Badimo", "Modekngei", "Mana",
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
        "Sin religión", "irreligion", "secular",
        # Answers that all mean "not religious". A person filtering for "No
        # religion" and missing the twelve countries whose Factbook entry says
        # "atheist" is being shown a false map, and each of these is an
        # unambiguous statement about the respondent -- unlike the mixed
        # buckets listed under "Not stated" and the ones excluded entirely.
        "atheist", "Atheist", "atheism", "agnostic", "Agnostic",
        "agnostic/atheist", "unaffiliated", "Unaffiliated",
        "non-believers", "non-believer", "non-believer/agnostic",
        "no religious affiliation", "not religious",
        "agnostic or atheist", "none/atheist", "nonbeliever/agnostic",
        "atheist or agnostic",
    ),
    "Not stated": (
        "Not stated", "Not answered", "Religious affiliation not stated",
        "Sem declaração", "Não sabe", "unspecified", "no response",
        "no answer", "unknown", "refused to answer", "not reported",
        "Object to answering", "Not elsewhere included", "declined to answer",
        "don't know/no answer", "don't know/refused", "do not know",
    ),
    "Other religions": (
        "Other", "Other religion", "Other religions", "Other Religions",
        "Outras religiosidades", "other religions", "Otras religiones",
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
    "Romanian": ("Romanian", "Moldovan", "Moldovian"),
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
    # Mexico writes its census category two ways in the same release.
    "Afro-descendant": (
        "Afro-descendant", "African descent", "Afro-Mexican or Afro-descendant",
        "Afrodescendiente", "of African descent",
    ),
    # Residuals, for the same reason as the language ones: "other" reaches 142
    # countries and tops the picker while meaning nothing in particular.
    "Other ethnicity": ("other", "other ethnicity", "others",
                        "Other Ethnicity", "Other"),
    "Ethnicity not stated": ("unspecified", "not stated", "no response",
                             "not reported", "unknown"),
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

# Groups that are the absence of an answer rather than an answer: a residual
# "other", or a non-response. They are real and must be shown -- a bar that
# quietly drops 20% of a population is the failure this project cares about
# most -- but nobody browses the world looking for them, so the picker sorts
# them last and says what they are.
RESIDUAL: frozenset[str] = frozenset({
    "Other religions", "Not stated", "Unaffiliated or not reported",
    "Other languages", "Language not stated",
    "Other ethnicity", "Ethnicity not stated",
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
    return [c for c, labels in seen.items()
            if len(set(labels)) > 1 and key(c) in labels]
