#!/usr/bin/env python3
"""United States -- Census Bureau ACS 5-year API (states and counties).

Race/ethnicity comes from **B03002** (Hispanic or Latino origin by race), not
B02001, because only B03002 makes the Hispanic-origin question orthogonal to
race the way the published "White, non-Hispanic" figures do.  Language uses
**C16001** (the collapsed version of B16001, which is far smaller over 3,143
counties).  Median age and sex ratio come from the **DP05** profile.

Religion is *not* in the census: the US census has been barred from asking a
mandatory religion question since 1976 (13 U.S.C. 221(c)).  The county-level
substitute is the 2020 U.S. Religion Census (ASARB, distributed by ARDA), which
counts *adherents reported by 372 religious bodies* -- 161,224,088 people, about
48.6% of the 2020 population -- and is therefore not comparable with the
self-identification percentages used everywhere else in this dataset.

The 372 individual bodies it reports are collapsed into traditions -- Catholic,
Protestant, Orthodox Christian, Latter-day Saints, Judaism, Islam, Buddhism,
Hinduism and so on -- because a denominational breakdown is neither mappable nor
comparable with the broad census categories used elsewhere here.  Output is
always labelled ``religion_basis: adherents`` and carries the publisher's
suggested citation.

An API key is optional below 500 calls/day; set ``CENSUS_API_KEY`` to lift that.

Usage:
    python -m scripts.fetch_census.us_acs --level county --year 2022
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, dated, gap, http_get, http_json,
    log, measure, record, shares, write_json,
)

BASE = "https://api.census.gov/data/{year}/acs/acs5"
# DP* variables are served by the data-profile endpoint, not the detailed
# tables -- asking acs/acs5 for DP05_0018E gets a plain-text error, not JSON.
BASE_PROFILE = "https://api.census.gov/data/{year}/acs/acs5/profile"

# B03002 lines that partition the population exactly once.
RACE_LINES = {
    "B03002_003E": "White (non-Hispanic)",
    "B03002_004E": "Black or African American (non-Hispanic)",
    "B03002_005E": "American Indian and Alaska Native (non-Hispanic)",
    "B03002_006E": "Asian (non-Hispanic)",
    "B03002_007E": "Native Hawaiian and Other Pacific Islander (non-Hispanic)",
    "B03002_008E": "Some other race (non-Hispanic)",
    "B03002_009E": "Two or more races (non-Hispanic)",
    "B03002_012E": "Hispanic or Latino (any race)",
}
RACE_TOTAL = "B03002_001E"

# The name C16001 gives the column that is not any of the twelve it names, and
# the name kept for what is left of it after RESIDUAL_DETAIL below is read.
RESIDUAL = "Other and unspecified"

LANGUAGE_LINES = {
    "C16001_002E": "English only",
    "C16001_003E": "Spanish",
    "C16001_006E": "French, Haitian, or Cajun",
    "C16001_009E": "German or other West Germanic",
    "C16001_012E": "Russian, Polish, or other Slavic",
    "C16001_015E": "Other Indo-European",
    "C16001_018E": "Korean",
    "C16001_021E": "Chinese (incl. Mandarin, Cantonese)",
    "C16001_024E": "Vietnamese",
    "C16001_027E": "Tagalog (incl. Filipino)",
    "C16001_030E": "Other Asian and Pacific Island",
    "C16001_033E": "Arabic",
    "C16001_036E": RESIDUAL,
}
LANGUAGE_TOTAL = "C16001_001E"

# C16001's residual, and the seven lines of B16001 that make it up.
#
# C16001 is the *collapsed* language table: 13 categories, one of which is a
# word meaning "none of the twelve above". B16001 is the same survey's detailed
# table -- 42 languages, published for every county in the 5-year estimates --
# and the census itself says which of its lines roll into which of C16001's.
# Seven roll into this one, and nothing else does, so substituting them for it
# is reading the census's own break-up of its own residual rather than
# estimating anything.
#
# It is not a small thing outside the cities. In the Bethel Census Area of
# Alaska the residual was 56.6% of everyone over five -- the largest single
# figure on the shape was a word for "not asked about" -- and what it holds is
# Central Alaskan Yup'ik, which B16001 counts under "Other Native languages of
# North America".
#
# The labels are the table's own, minus a trailing " languages" where it has
# one, which is the shortening the C16001 labels above already use ("Other
# Asian and Pacific Island" is C16001's "Other Asian and Pacific Island
# languages"). B16001_126's label is left as C16001's "Other and unspecified"
# rather than becoming "Other and unspecified languages", because that exact
# string is a tier-1 node of the group tree and a group of the same name would
# be its own parent.
RESIDUAL_LINE = "C16001_036E"
RESIDUAL_DETAIL = {
    "B16001_108E": "Hebrew",
    "B16001_111E": "Amharic, Somali, or other Afro-Asiatic",
    "B16001_114E": "Yoruba, Twi, Igbo, or other languages of Western Africa",
    "B16001_117E": "Swahili or other languages of Central, Eastern, and "
                   "Southern Africa",
    "B16001_120E": "Navajo",
    "B16001_123E": "Other Native languages of North America",
    "B16001_126E": RESIDUAL,
}

PROFILE_LINES = {"DP05_0018E": "median_age", "DP05_0004E": "sex_ratio_m_per_100f"}


def query(year: int, get: list[str], geo: str, key: str | None,
          base: str = BASE) -> list[dict[str, str]]:
    params = [f"get=NAME,{','.join(get)}", f"for={geo}"]
    if key:
        params.append(f"key={key}")
    url = f"{base.format(year=year)}?" + "&".join(params)
    text = http_get(url, timeout=180)
    assert isinstance(text, str)
    # The Census API used to allow 500 anonymous calls a day; it now returns a
    # "Missing Key" HTML page with HTTP 200 when no key is sent. Turn that into
    # an instruction instead of a JSON traceback.
    if "Missing Key" in text[:400]:
        raise SystemExit(
            "us_acs: api.census.gov now requires an API key for every request. "
            "Request a free key at https://api.census.gov/data/key_signup.html "
            "and set it as the CENSUS_API_KEY environment variable (in CI: a "
            "repository secret of the same name).")
    import json as _json
    rows = _json.loads(text.lstrip("\ufeff"))
    header, *body = rows
    return [dict(zip(header, row)) for row in body]


def as_float(value: str | None) -> float | None:
    """ACS uses negative sentinels (-666666666) for suppressed cells."""
    if value in (None, "", "null"):
        return None
    try:
        num = float(value)
    except ValueError:
        return None
    return None if num <= -666666 else num


def geoid(row: dict[str, str], level: str) -> str:
    return row["state"] + (row.get("county", "") if level == "county" else "")


# B16001 answers for states and for nothing smaller. Asked for every county
# in the 2022 5-year file it returns a row per county with null in all seven
# columns -- not an error, not a zero: no figure. So a county's own residual is
# divided nowhere, and the twelve named categories plus one word are the
# finest the ACS publishes at this level.
#
# The state's division is not carried down onto its counties either, which is
# what India's district detail does for its districts. The reason is that here
# the assumption fails in exactly the places the question is asked. A state's
# residual mixes the languages of its reservations with those of its cities:
# South Dakota's is 58% Native languages and 36% Amharic, Somali and Swahili,
# the second of those being Sioux Falls. Scaled onto Todd County -- the Rosebud
# Reservation, and 21.8% residual -- it would put several hundred East African
# speakers there. That is a mis-matched row, and a mis-matched row is worse
# than an undivided one.
#
# What is left is to say what the column holds. Below RESIDUAL_LOUD it is a
# rounding line nobody asks about; above it, it is often the largest figure on
# the shape.
RESIDUAL_LOUD = 5.0

COUNTY_RESIDUAL_NOTE = (
    " This column is large here and the ACS does not divide it: its detailed "
    "language table, B16001, is published for states and larger and answers "
    "null for every county. The state's own division of the same column is not "
    "scaled onto counties either, because a state's residual mixes the "
    "languages of its reservations with those of its cities -- South Dakota's "
    "is 58% Native languages beside 36% Amharic, Somali and Swahili, and "
    "carrying that to the Rosebud Reservation would invent East African "
    "speakers there.")

# What the column holds, in the counties where it is over a tenth of everybody
# and the answer is not in doubt: every one of them is a reservation or an
# Alaska Native region, and every other language of any size in the United
# States has a column of its own above. The languages are named from the
# communities the county covers; the census names none of them.
#
# Keyed by GEOID and checked against the name the API returns for it, because
# a FIPS code typed from memory onto the wrong county is a mis-match nobody
# would see -- it would read as an ordinary sentence about an ordinary place.
RESIDUAL_COUNTIES: dict[str, tuple[str, str]] = {
    "02050": ("Bethel Census Area, Alaska", "Central Alaskan Yup'ik"),
    "02158": ("Kusilvak Census Area, Alaska", "Central Alaskan Yup'ik"),
    "02070": ("Dillingham Census Area, Alaska", "Central Alaskan Yup'ik"),
    "02164": ("Lake and Peninsula Borough, Alaska",
              "Central Alaskan Yup'ik and Alutiiq"),
    "02180": ("Nome Census Area, Alaska",
              "Inupiaq, Central Alaskan Yup'ik, and the St. Lawrence Island "
              "Yupik of Gambell and Savoonga"),
    "02185": ("North Slope Borough, Alaska", "Inupiaq"),
    "02188": ("Northwest Arctic Borough, Alaska", "Inupiaq"),
    "04001": ("Apache County, Arizona",
              "Navajo, with Western Apache in the south of the county"),
    "04005": ("Coconino County, Arizona", "Navajo and Hopi"),
    "04017": ("Navajo County, Arizona", "Navajo and Hopi"),
    "35006": ("Cibola County, New Mexico",
              "Navajo, and the Western Keres of Acoma and Laguna"),
    "35031": ("McKinley County, New Mexico", "Navajo and Zuni"),
    "35045": ("San Juan County, New Mexico", "Navajo"),
    "35053": ("Socorro County, New Mexico",
              "Navajo, of the Alamo Navajo Reservation"),
    "49037": ("San Juan County, Utah", "Navajo"),
    "30003": ("Big Horn County, Montana", "Crow and Northern Cheyenne"),
    "46007": ("Bennett County, South Dakota", "Lakota"),
    "46031": ("Corson County, South Dakota", "Lakota"),
    "46041": ("Dewey County, South Dakota", "Lakota"),
    "46095": ("Mellette County, South Dakota", "Lakota"),
    "46102": ("Oglala Lakota County, South Dakota", "Lakota"),
    "46121": ("Todd County, South Dakota", "Lakota"),
    "46137": ("Ziebach County, South Dakota", "Lakota"),
}

LANGUAGE_NOTE = ("Language spoken at home, population 5 years and over "
                 "(ACS table C16001).")
STATE_DETAIL_NOTE = (
    " C16001's own 'Other and unspecified' column is replaced here by the "
    "seven lines of the detailed table B16001 that make it up -- Hebrew, the "
    "Afro-Asiatic, West African and Central/Eastern/Southern African "
    "groupings, Navajo, other Native languages of North America, and what is "
    "still unspecified after those. Both tables are the same survey's, and "
    "the parts are checked against the column they replace before either is "
    "used.")


def residual_note(gid: str, name: str, rows: list[dict[str, Any]]) -> str:
    """One county's language note: the general one, and what its Other holds.

    Silent on a county whose residual is small -- most of them -- because a
    paragraph about a 0.3% column on three thousand records is noise, not
    provenance.
    """
    share = next((row["pct"] for row in rows if row["group"] == RESIDUAL), 0.0)
    if share < RESIDUAL_LOUD:
        return LANGUAGE_NOTE
    note = LANGUAGE_NOTE + COUNTY_RESIDUAL_NOTE
    named = RESIDUAL_COUNTIES.get(gid)
    if named is None:
        return note
    expected, languages = named
    if name != expected:
        raise SystemExit(
            f"us_acs: GEOID {gid} is {name!r} in this year's ACS and this "
            f"file has it as {expected!r}. The sentence naming what its "
            f"'{RESIDUAL}' column holds would go on the wrong county, which "
            f"is not visible from the outside. Nothing is being emitted.")
    return note + (
        f" What it holds here is, in the main, {languages} -- named from the "
        f"community this county covers and not by the census, which pools it "
        f"with everything else it did not ask about.")


def with_detail(counts: dict[str, float], detail: dict[str, float] | None,
                name: str, raw: dict[str, str] | None = None) -> dict[str, float]:
    """C16001's twelve named categories, with its residual replaced by B16001's
    seven.

    The invariant is checked rather than trusted, the way India's C-01 Appendix
    substitution checks its own: the parts must come to the whole they replace,
    to the person. C16001 is a collapsed view of B16001 and the two are
    produced from one set of estimates, so they agree exactly or one of these
    line numbers is not the line this file thinks it is -- and a line number
    that has quietly moved would otherwise land as a plausible wrong figure on
    three thousand counties.

    A geography B16001 does not answer for at all stops the run for the same
    reason. Every county has this table in the 5-year estimates; a missing row
    means the request or the year is wrong, not that the county has no
    languages.
    """
    if detail is None:
        raise SystemExit(
            f"us_acs: {name} has a C16001 row and no B16001 row. Every "
            f"geography in the 5-year estimates has both; a missing one means "
            f"the request or the year is wrong. Nothing is being emitted.")
    bucket = counts.get(RESIDUAL, 0.0)
    named = sum(detail.values())
    if named != bucket:
        raise SystemExit(
            f"us_acs: {name}: B16001's seven lines inside C16001's "
            f"'{RESIDUAL}' come to {named:,.0f} against the {bucket:,.0f} "
            f"C16001 prints for the column itself. They are the same survey's "
            f"figures for the same people, so they agree or a line number "
            f"here is wrong, or this table is not published at this level. "
            f"What the API returned for it: "
            f"{ {k: v for k, v in (raw or {}).items() if k in RESIDUAL_DETAIL} }. "
            f"Nothing is being emitted.")
    out = {label: value for label, value in counts.items() if label != RESIDUAL}
    out.update({label: value for label, value in detail.items() if value})
    return out


def fetch(level: str, year: int, key: str | None) -> list[dict[str, Any]]:
    geo = "county:*" if level == "county" else "state:*"
    src = f"U.S. Census Bureau, ACS {year} 5-year estimates"

    race = query(year, [RACE_TOTAL, *RACE_LINES], geo, key)
    lang = {geoid(r, level): r for r in query(year, [LANGUAGE_TOTAL, *LANGUAGE_LINES], geo, key)}
    # A second request rather than one: C16001 and B16001 are different tables
    # and the API takes one table's variables at a time well and both at once
    # badly. The join is on the geoid, which both return. Counties are not
    # asked at all -- see RESIDUAL_COUNTIES above for what B16001 answers for
    # a county, which is nothing.
    fine = ({geoid(r, level): r for r in query(year, list(RESIDUAL_DETAIL), geo, key)}
            if level == "state" else {})
    prof = {geoid(r, level): r
            for r in query(year, list(PROFILE_LINES), geo, key, base=BASE_PROFILE)}

    out: list[dict[str, Any]] = []
    for row in race:
        gid = geoid(row, level)
        total = as_float(row.get(RACE_TOTAL))
        counts = {label: as_float(row.get(code)) for code, label in RACE_LINES.items()}
        counts = {k: v for k, v in counts.items() if v is not None}

        lrow = lang.get(gid, {})
        lcounts = {label: as_float(lrow.get(code)) for code, label in LANGUAGE_LINES.items()}
        lcounts = {k: v for k, v in lcounts.items() if v}

        prow = prof.get(gid, {})
        median = as_float(prow.get("DP05_0018E"))
        ratio = as_float(prow.get("DP05_0004E"))

        # ACS names a county "Autauga County, Alabama". The state half is what
        # separates the thirty-one counties called Washington from each other, so
        # it is passed through for matching rather than thrown away.
        name = row["NAME"]
        state_name = name.split(",")[-1].strip() if level == "county" and "," in name else None

        # A suppressed detail cell reads as zero here on purpose: it then fails
        # the sum against C16001's own column and with_detail says which
        # geography, rather than being quietly dropped out of a total.
        drow = fine.get(gid)
        dcounts = (None if drow is None else
                   {label: (as_float(drow.get(code)) or 0.0)
                    for code, label in RESIDUAL_DETAIL.items()})

        race_rows = shares(counts, total=total)
        divided = (with_detail(lcounts, dcounts, name, drow)
                   if lrow and level == "state" else lcounts)
        lang_rows = shares(divided, total=as_float(lrow.get(LANGUAGE_TOTAL)))
        out.append(record(
            f"USA-{gid}",
            name,
            level="admin1" if level == "state" else "admin2",
            parent="USA" if level == "state" else f"USA-{row['state']}",
            parent_name=state_name,
            codes={"geoid": gid, "fips_state": row["state"],
                   "fips_county": row.get("county")},
            population=measure(int(total), year=year, source=src) if total else gap(NOT_AVAILABLE),
            median_age=measure(median, unit="years", year=year, source=src) if median else gap(NOT_AVAILABLE),
            sex_ratio=(measure(round(ratio * 10), unit="males_per_1000_females",
                               year=year, source=src) if ratio else gap(NOT_AVAILABLE)),
            ethnicity=race_rows or gap(NOT_AVAILABLE),
            ethnicity_year=dated(race_rows, year),
            ethnicity_note=("US Census race and Hispanic-origin categories (ACS table B03002). "
                            "Not comparable with other countries' ethnicity classifications."),
            language=lang_rows or gap(NOT_AVAILABLE),
            language_year=dated(lang_rows, year),
            language_note=(LANGUAGE_NOTE + STATE_DETAIL_NOTE if level == "state"
                           else residual_note(gid, name, lang_rows)),
            religion=gap(NOT_COLLECTED, CENSUS_BARRED + " Any figures shown come "
                         "instead from the 2020 U.S. Religion Census (ASARB), which "
                         "counts adherents reported by religious bodies rather than "
                         "asking people."),
            sources=[{"field": "ethnicity/language/population", "name": src,
                      "url": BASE.format(year=year), "license": "Public domain (U.S. Government work)"}],
        ))
    return out


# The citation the publisher asks for, verbatim, recorded on every record the
# study touches. Note the year: the workbook's own Copyright sheet says 2022,
# the suggested citation on usreligioncensus.org says 2023. The publisher's
# wording is what goes on the record.
# Checked in under data/raw/us/: there is no API for this study, and the US
# census is barred from asking the question, so without the workbook the build
# cannot re-derive religion for a single county.
RELIGION_YEAR = 2020            # the year the study counted, not the year it was published
RELIGION_FILE = RAW / "us" / "2020_USRC_Group_Detail.xlsx"

RELIGION_CITATION = (
    "Clifford Grammich, Erica Dollhopf, Mary Gautier, Richard Houseal, "
    "Dale E. Jones, Alexei Krindatch, Richie Stanley, and Scott Thumma. 2023. "
    "2020 U.S. Religion Census: Religious Congregations & Membership Study. "
    "Association of Statisticians of American Religious Bodies."
)

# Every sheet in the workbook carries a row holding the whole country, and each
# one hides it differently: the county sheet keys it FIPS = "Total", the state
# sheet StateCode = "Totals", the nation sheet Group Code = "Totals". None of
# them names a group. Summing a column without excluding it doubles the United
# States exactly -- 322,019,032 adherents against a true 161,009,516, 97% of the
# population religiously adherent.
#
# Nothing internal to the table catches that. Every county's own shares stay
# correct and still reproduce the percentages the file prints beside them,
# exactly as they did for the ABS "Christianity Total" rows and the India C-16
# group codes. It is visible only against a total the detail rows did not
# produce, which is why these rows are read and used as the control rather than
# skipped and forgotten. The singular/plural difference is the whole reason this
# is a set: an exact match on "total" silently misses the state sheet.
NATIONAL_BLOCK = {"total", "totals"}

LEVELS = {
    "county": {"sheet": "2020 Group by County", "key": ("fips",), "width": 5,
               "share": ("adherents as % of total population",)},
    "state": {"sheet": "2020 Group by State", "key": ("statecode",), "width": 2,
              "share": ("adherents as % of population",)},
}

# The study reports 372 individual religious bodies, which is far too fine to
# put on a map and not comparable with the broad census categories every other
# country here uses. They are collapsed into traditions.
#
# The mapping is by exact name and only for what is *not* Protestant; anything
# unlisted falls through to Protestant, and the adapter prints the largest
# groups it defaulted so that a body added in a later release is visible rather
# than silently absorbed. Matching on keywords instead would be wrong in both
# directions: the Orthodox Presbyterian Church and the Orthodox Mennonite Church
# are Protestant, and the Polish National Catholic Church is not Roman Catholic.
DEFAULT_TRADITION = "Protestant"
TRADITIONS: dict[str, str] = {
    "Catholic Church": "Catholic",
    "Church of Jesus Christ of Latter-day Saints": "Latter-day Saints",
    "Community of Christ": "Latter-day Saints",
    "Jehovah's Witnesses": "Jehovah's Witnesses",
    "Muslim Estimate": "Islam",
    # Judaism is reported by movement; the map shows the religion.
    "Orthodox Judaism": "Judaism",
    "Reform Judaism": "Judaism",
    "Conservative Judaism": "Judaism",
    "Reconstructionist Judaism": "Judaism",
    "Independent Judaism": "Judaism",
    "Chabad Judaism": "Judaism",
    "Hindu Temples": "Hinduism",
    "Hindu Yoga and Meditation": "Hinduism",
    "Vedanta Society": "Hinduism",
    "Mahayana Buddhist": "Buddhism",
    "Theravada Buddhist": "Buddhism",
    "Vajarayana Buddhist": "Buddhism",
    # Eastern and Oriental Orthodox, by jurisdiction.
    "Greek Orthodox Archdiocese of America": "Orthodox Christian",
    "Coptic Orthodox Church": "Orthodox Christian",
    "Ethiopian Orthodox": "Orthodox Christian",
    "Eritrean Orthodox": "Orthodox Christian",
    "Orthodox Church in America": "Orthodox Christian",
    "Antiochian Orthodox Christian Archdiocese of North America, The": "Orthodox Christian",
    "Serbian Orthodox Church in North America": "Orthodox Christian",
    "Armenian Church of North America (Catholicosate of Etchmiadzin)": "Orthodox Christian",
    "Armenian Apostolic Church of America (Catholicosate of Cilicia)": "Orthodox Christian",
    "Russian Orthodox Church Outside of Russia": "Orthodox Christian",
    "Patriarchal Parishes of the Russian Orthodox Church in the USA": "Orthodox Christian",
    "Malankara Orthodox Syrian Church": "Orthodox Christian",
    "Malankara Archdiocese of the Syrian Orthodox Church in North America": "Orthodox Christian",
    "Syriac Orthodox Church of Antioch": "Orthodox Christian",
    "Macedonian Orthodox Church: American Diocese": "Orthodox Christian",
    "Ukrainian Orthodox Church of the USA": "Orthodox Christian",
    "Romanian Orthodox Archdiocese in Americas": "Orthodox Christian",
    "American Carpatho-Russian Orthodox Diocese": "Orthodox Christian",
    "Bulgarian Eastern Orthodox Diocese of the USA, Canada and Australia": "Orthodox Christian",
    "Albanian Orthodox Diocese of America": "Orthodox Christian",
    "Georgian Orthodox Parishes in the United States": "Orthodox Christian",
    "Belarusan Autocephalous Orthodox Church": "Orthodox Christian",
    "Church of the Genuine Orthodox Christians": "Orthodox Christian",
    "Holy Orthodox Church in North America": "Orthodox Christian",
    "Syro-Russian Orthodox Catholic Church": "Orthodox Christian",
    # Old Catholic and independent Catholic bodies, in communion with none of
    # the above and not counted as Roman Catholic.
    "Polish National Catholic Church": "Other Christian",
    "North American Old Roman Catholic Church": "Other Christian",
    "Orthodox Old Roman Catholic Communion": "Other Christian",
    "Ecumenical Catholic Communion": "Other Christian",
    "Ecumenical Catholic Church": "Other Christian",
    "United Catholic Church": "Other Christian",
    "Liberal Catholic Church": "Other Christian",
    "Catholic Apostolic Church in North America": "Other Christian",
    "Swedenborgian Church": "Other Christian",
    "Union of Messianic Jewish Congregations": "Other Christian",
    "Association of Messianic Congregations": "Other Christian",
    # Reported as congregations with no adherent estimate, so these contribute
    # nothing to any share; they are listed so the classification is complete
    # and so they land correctly if a later release does estimate them.
    "Baha'i Faith USA": "Other religions",
    "American Sikh Council": "Other religions",
    "Jain": "Other religions",
    "Zoroastrian": "Other religions",
    "Shinto": "Other religions",
    "Tao": "Other religions",
    "Unitarian Universalist Association of Congregations": "Other religions",
    "National Spiritualist Association of Churches": "Other religions",
}


# The reason the United States has no government religion figure at any level of
# geography, stated once. It prefixes every gap this adapter emits, because it
# is the fact that makes the rest of the sentence necessary.
CENSUS_BARRED = ("The U.S. census may not ask a mandatory religion question "
                 "(13 U.S.C. 221(c)), so no government figures exist at any "
                 "level.")

# Why a US area can have no figure even with the workbook in hand. Naming the
# reason is the whole point: "no data" and "the study does not cover this place"
# and "nobody reported a congregation here" are three different facts, and only
# the last is about the place itself.
UNMATCHED_REASONS = {
    "72": "The 2020 study covers the 50 states and the District of Columbia. "
          "Puerto Rico is outside its frame, so no municipio has an adherent "
          "count from it either.",
    "09": "Connecticut replaced its eight counties with nine planning regions in "
          "2022. The 2020 study reports the old counties, so its figures cannot "
          "be placed on this geography without inventing a way to split them.",
}
# The share of an area the study accounts for is not a constant to be scaled
# away: it runs from 27.3% in New Hampshire to 76.2% in Utah. Rescaling each
# area's shares to sum to 100% would make those two look equally religious,
# which deletes the most informative signal in the data and asserts that nobody
# in the United States is unaffiliated.
#
# So the shortfall is named instead. It is genuinely two things at once -- people
# who belong to nothing, and members of bodies that did not report -- and the
# study cannot separate them, so the label does not pretend to.
REMAINDER = "Unaffiliated or not reported"

UNMATCHED_DEFAULT = (
    "No religious body reporting to the 2020 study had a congregation here. That "
    "is an absence of reported adherents, not a count of zero believers.")


def read_group_detail(path: Path, level: str) -> tuple[dict[str, dict[str, float]],
                                                       dict[str, float], float]:
    """Adherents by area and religious body, area populations, and the control.

    Handles the ASARB workbook directly (.xlsx) and a CSV export of one of its
    sheets. Returns per-area counts keyed by the body's own name, the 2020
    population the file itself implies for each area, and the national total
    carried by the whole-country row.
    """
    spec = LEVELS[level]
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = book[spec["sheet"]] if spec["sheet"] in book.sheetnames else book.worksheets[0]
        rows = sheet.iter_rows(values_only=True)
        header = [str(c or "") for c in next(rows)]
        records: Any = (dict(zip(header, r)) for r in rows)
    else:
        import csv
        with path.open(newline="", encoding="utf-8-sig") as handle:
            records = list(csv.DictReader(handle))

    def field(row: dict, *names: str) -> Any:
        for name in names:
            for key in row:
                if key and key.strip().lower() == name:
                    return row[key]
        return None

    areas: dict[str, dict[str, float]] = {}
    populations: dict[str, float] = {}
    national = 0.0
    for row in records:
        code = str(field(row, *spec["key"]) or "").strip()
        if not code:
            continue
        try:
            adherents = float(field(row, "adherents", "adherent"))
        except (TypeError, ValueError):
            continue          # blank means not reported, which is not zero

        # Before anything else: the whole-country row names no group, so a
        # reader that requires one skips it silently and loses the only figure
        # the detail rows can be checked against.
        if code.lower() in NATIONAL_BLOCK:
            national += adherents
            continue

        group = str(field(row, "group name", "grpname") or "").strip()
        if not group:
            continue
        code = code.zfill(spec["width"])
        areas.setdefault(code, {})[group] = adherents
        # The file prints each count as a share of its area's population, so the
        # denominator it used can be recovered rather than assumed. Taking it
        # from the file keeps the shares equal to the published ones; the ACS
        # population on the record is a different year and would not.
        try:
            share = float(field(row, *spec["share"]))
        except (TypeError, ValueError):
            share = 0.0
        if share > 0 and adherents > 0:
            implied = adherents / share
            known = populations.setdefault(code, implied)
            # Every row of an area must imply the same denominator. If the file
            # ever computed its percentages against something that varies by
            # row, taking the population from the first row would leave every
            # other share on that area wrong by a factor nothing would show.
            if abs(implied - known) > max(1.0, known * 1e-6):
                raise SystemExit(
                    f"{level} {code}: rows imply different populations "
                    f"({known:,.0f} and {implied:,.0f}); the share column is not "
                    "on a single denominator and cannot be inverted")
    return areas, populations, national


def check_national(areas: dict[str, dict[str, float]], national: float, level: str) -> None:
    """The areas must add up to the whole-country row, or the read is wrong.

    This is the check that catches reading that row as an area. It compares
    against a figure the detail rows did not produce, so unlike a
    shares-add-to-100% test it cannot be satisfied by double counting.
    """
    if not national:
        raise SystemExit(
            f"no whole-country row (key in {sorted(NATIONAL_BLOCK)}) in the {level} "
            "sheet. Either the layout changed or it was filtered out -- without it "
            "the detail rows have nothing independent to reconcile against, and a "
            "doubled country reads as a valid table.")
    total = sum(sum(g.values()) for g in areas.values())
    drift = abs(total - national) / national
    print(f"  {level}: {total:,.0f} vs whole-country row {national:,.0f} "
          f"({drift:.4%} apart, {len(areas)} areas)")
    if drift > 0.005:
        raise SystemExit(f"{level} adherents are {drift:.2%} from the whole-country row")


def to_traditions(groups: dict[str, float]) -> dict[str, float]:
    """Collapse individual religious bodies into the traditions the map shows."""
    out: dict[str, float] = {}
    for name, adherents in groups.items():
        tradition = TRADITIONS.get(name, DEFAULT_TRADITION)
        out[tradition] = out.get(tradition, 0.0) + adherents
    return out


def report_defaults(areas: dict[str, dict[str, float]]) -> None:
    """Name the largest bodies that fell through to Protestant.

    Everything unlisted defaults, so a body added by a later release -- or a
    renamed one -- would be absorbed without complaint. Printing the top of that
    list on every run is what makes the classification auditable.
    """
    totals: dict[str, float] = {}
    for groups in areas.values():
        for name, adherents in groups.items():
            if name not in TRADITIONS:
                totals[name] = totals.get(name, 0.0) + adherents
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print(f"  {len(totals)} bodies defaulted to {DEFAULT_TRADITION}; largest: "
          + ", ".join(f"{n} {v:,.0f}" for n, v in top))


def attach_religion(records: list[dict[str, Any]], path: Path, level: str) -> None:
    """Merge a 2020 U.S. Religion Census extract (ASARB, ARDA dataset RCMSCY20).

    Opt-in: the study is copyright ASARB and the map carries it by the
    publisher's suggested citation, which is recorded on every record it
    touches.
    """
    areas, populations, national = read_group_detail(path, level)
    check_national(areas, national, level)
    report_defaults(areas)

    matched = 0
    for rec in records:
        gid = rec.get("codes", {}).get("geoid", "")
        groups = areas.get(gid)
        pop = populations.get(gid)
        if not groups or not pop:
            rec["religion"] = gap(NOT_COLLECTED, CENSUS_BARRED + " " +
                                  UNMATCHED_REASONS.get(gid[:2], UNMATCHED_DEFAULT))
            # The stamp goes with the value it described. These records are
            # written here and never carry one, so this only ever states the
            # rule -- but an area the study does not reach must not keep a date
            # from an area it does.
            rec.pop("religion_year", None)
            continue
        matched += 1
        counts = to_traditions(groups)
        # Not in 30 counties, where reporting bodies claim more adherents than
        # the county has residents -- rural congregations drawing members from
        # outside it. King County, Texas reports 452%. A "remainder" there would
        # be negative, which is not a group of people.
        remainder = pop - sum(counts.values())
        if remainder > 0:
            counts[REMAINDER] = remainder
        rec["religion"] = shares(counts, total=pop)
        rec["religion_year"] = RELIGION_YEAR
        rec["religion_basis"] = "adherents"
        rec["religion_note"] = (
            "2020 U.S. Religion Census (ASARB): adherents reported by 372 religious "
            "bodies, grouped into traditions and expressed as a share of the 2020 "
            "census population. These are counts of people reported by religious "
            "bodies, not answers people gave about themselves. The study accounted "
            "for about 48.6% of the population nationally, and between 27% and 76% "
            "depending on the state; the rest is shown as one category because it "
            "mixes people who belong to nothing with members of bodies that did not "
            "report, and the study cannot tell them apart. Not comparable with the "
            "census religion figures used for other countries.")
        rec["sources"].append({"field": "religion", "name": RELIGION_CITATION,
                               "url": "https://www.usreligioncensus.org/",
                               "license": "Copyright ASARB; used with the "
                                          "publisher's suggested citation"})
    print(f"  religion attached to {matched} of {len(records)} records")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="county", choices=["state", "county"])
    ap.add_argument("--year", type=int, default=2022)
    ap.add_argument("--religion-file", type=Path, default=RELIGION_FILE,
                    help="2020 U.S. Religion Census workbook or sheet export "
                         "(ASARB / ARDA RCMSCY20); read at the chosen --level")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    key = os.environ.get("CENSUS_API_KEY")
    log(f"us_acs: ACS {args.year} 5-year, level={args.level}"
        + ("" if key else " (no CENSUS_API_KEY set; the API now rejects keyless requests)"))
    records = fetch(args.level, args.year, key)
    if args.religion_file and args.religion_file.exists():
        attach_religion(records, args.religion_file, args.level)
    else:
        # Not an error: without the workbook the records keep their
        # not_collected marker, which is the truthful state of a US religion
        # figure. Saying so beats a silent skip.
        print(f"  no religion workbook at {args.religion_file}; "
              "religion stays not_collected")
    out = args.out or PROCESSED / f"us_{args.level}.json"
    write_json(out, records)
    log(f"  {len(records)} {args.level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
