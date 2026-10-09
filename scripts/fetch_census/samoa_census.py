#!/usr/bin/env python3
"""Samoa, 2021 Census: population, age, sex and religion by Faipule district and political district.

The Samoa Bureau of Statistics publishes the 2021 Census of Population and
Housing as one workbook of 58 tables by place of residence -- region, the 51
electoral constituencies of 2019 and the 339 villages inside them:

* **Table 1**: population by sex and single year of age, to 103, with a "DK"
  column for the age not known;
* **Table 2**: population by sex and religion, 26 denominations.

**The map's units are older.** Its 43 second-level polygons are the 41
Faipule districts the constituencies replaced in 2019 (two of them, Gaga'emauga
I and II, in two pieces: their villages on Savai'i and an exclave each on
Upolu, which the boundary file draws as "(PART)"), and its 11 first-level
polygons the political districts (itumalo) made of them. The 2021 tables are
not printed by either. A district is a set of villages, though, and the 2016
Census printed every village under its district: **2016 Census Brief No. 1,
Table 1** (population by sex and place of residence -- region, district,
village), down to splitting Gaga'emauga I and II between their Upolu and
Savai'i villages. So each 2021 village is put in the district the 2016 census
put it in, and a district's 2021 figures are its villages' added up.

**Matching the villages.** Most 2021 villages carry the 2016 name. Where the
2021 table spells it differently or adds the district to tell two namesakes
apart ("Fusi Safata" for Safata's Fusi), ``RENAMED`` gives the 2016 village,
one by one. A name found in two 2016 districts goes to the district most of
its 2021 constituency's other villages came from. A 2021 village the 2016
census did not have goes the same way, and the log names it. Any village
left over stops the run.

**Political districts** are their Faipule districts added up, by the
composition the 2016 populations on the map already follow (``ITUMALO``).

**Citizenship as ethnicity.** No Samoan census table publishes ethnicity: not
the 2021 workbook's 58 tables or its Fact Sheet, the 2016 census's four Briefs
(population by village; fertility, mortality and migration; education and
work; housing), nor the 2011 census's 93 tables. 2021 and 2011 give
citizenship instead -- 2021's **Table 8a** by village
(born in Samoa or abroad to a citizen parent, naturalised, or not a citizen),
2011's Table 8 by urban and rural residence only. Under the owner's rule for
states that count citizenship rather than ethnicity, the districts carry
2021's count under ``ethnicity_basis: "nationality"``, as two groups:
"Samoan" (every citizen) and "Foreign nationals".

**Not published by place**: language. No census's tables have a language
spoken; their only language items are literacy (the 2021 Fact Sheet's Samoan
and English, the 2016 Brief No. 3's any language, the 2011 tables' Samoan).

**Checks**, each refusing the run: Samoa is 205,557 people (2021) and 195,979
(2016); every row's males and females make its total, its single years of age
make it too, and so do its denominations; a constituency's villages make the
constituency; every 2021 village is placed once; every 2016 district receives
villages, and its 2021 count lies within 40% of its 2016 one -- a wider swing
would mean villages filed in the wrong district; every polygon is bound once.
The country's male and female medians from Table 1's single years must be the
Final Report's (20 and 21, whole years) within ``MEDIAN_SLACK`` and the half
year a whole year stands for. Its median for everyone (22, and the Fact
Sheet's 22.0) lies outside its own sexes', which no set of ages can give, so
the run logs Table 1's 21.4 beside it rather than checking it. Table 8a lists Table 1's villages with Table 1's totals, its four answers are
headed as ``CITIZENSHIP_HEADINGS`` says and make each row's total, each by
sex, and the country's citizens and others are the Fact Sheet's 204,339 and
1,218.

Usage:
    python -m scripts.fetch_census.samoa_census
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, write_json
from .binding import fold
from .oceania_common import (
    bind_level, check, load_units, median_from_single_years, number, population,
    published_median, rows_of,
    sex_ratio, shares_of, summarise, unit_record, workbook,
)

YEAR = 2021
OUT = "samoa_census.json"
OFFICE = "Samoa Bureau of Statistics"
SOURCE = f"{OFFICE}, 2021 Census of Population and Housing, Census Tables"
SOURCE_2016 = f"{OFFICE}, 2016 Census Brief No. 1, Table 1"
URL = "https://www.sbs.gov.ws/wp-content/uploads/2022/12/CensusTablesEXCELFiles.xlsx"
URL_2016 = "https://www.sbs.gov.ws/digi/2-2016%20Census%20Brief%20No.1%20Tables.xlsx"
FACTSHEET_URL = "https://www.sbs.gov.ws/wp-content/uploads/2022/12/Factsheet_Samoa_-PHC2021.pdf"
NATIONAL = 205_557
# Table 8a's four answers after its Total, by the words their headings start with, and
# the Fact Sheet's national counts of citizens and of everyone else (DS.4).
CITIZENSHIP_HEADINGS = ("YES BORN IN SAMOA", "YES BORN ABROAD", "YES SAMOA  CITIZEN BY "
                        "NATURALISATION", "NO NOT A CITIZEN")
CITIZENS_2021, NON_CITIZENS_2021 = 204_339, 1_218
NATIONAL_2016 = 195_979
# The Bureau's medians for Samoa: the 2021 Final Report's key indicators (p. 11),
# in whole years -- everyone 22, males 20, females 21 -- and the Fact Sheet's
# 22.0 (indicator DS.3). A median of everyone lies between its two sexes', so
# the printed 22 is not the same people's as the 20 and 21 beside it; Table 1's
# single years give 21.4, between the two. The run checks the sexes, within
# oceania_common.MEDIAN_SLACK of the whole years printed, and logs the total.
FINAL_REPORT_URL = ("https://sbs.gov.ws/documents/census/2021/"
                    "Census-2021-Final-Report_221122_051222.pdf")
PRINTED_MEDIANS = {"everyone": 22, "males": 20, "females": 21}
FACT_SHEET_MEDIAN = 22.0
REGIONS = ("Apia Urban Area", "North West Upolu", "Rest of Upolu", "Savaii")
UPOLU = {"Apia Urban Area", "North West Upolu", "Rest of Upolu"}

# 2021 village -> the 2016 village it is, where the names differ.
RENAMED = {
    "Vaisigano": "Vaisagano", "Afiuamalu East": "Afiamalu East", "Leififi": "Leifiifi",
    "Tuanimato East": "Tuanaimato East", "Vailoa Faleata": ("Faleata East", "Vailoa"),
    "Leaupuni": "Leaupani", "Safune": "Safune I", "Levi Saleimoa": ("Sagaga La Falefa", "Levi"),
    "Lupuiai": "Lepuiai", "Siufaga Falelatai": ("Falelatai & Samatau", "Siufaga"),
    "Matautu Falelatai": ("Falelatai & Samatau", "Matautu"),
    "Levi Falelatai": ("Falelatai & Samatau", "Levi"),
    "Gagaifolevao": "Gagaifo O Le Vao", "Matautu Lefaga": ("Lefaga & Faleseela", "Matautu"),
    "Nuusuatia": "Niusuatia", "Fusi Safata": ("Safata", "Fusi"),
    "Mulivai Safata": ("Safata", "Mulivai"), "MatautuFalealili": ("Falealili", "Matautu"),
    "Vailoa Aleipata": ("Aleipata Itupa I Luga", "Vailoa"), "Saleaumua": "Saleaaumua",
    "Salimu i Vaa o Fonoti": ("Vaa O Fonoti", "Salimu"), "Saoluafata": "Saolufata",
    "Fusi Anoamaa": ("Anoamaa West", "Fusi"), "Maota Faasaleleaga": ("Faasaleleaga I", "Maota"),
    "Fusi Faasaleleaga": ("Faasaleleaga II", "Fusi"),
    "Siufaga Faasaleleaga": ("Faaleleaga III", "Siufaga"),
    "Salimu Faasaleleaga": ("Faaleleaga III", "Salimu"), "Matavai": "3Matavai",
    "Samata Tai": "Samata I Tai", "Samata Uta": "Samata I Uta",
    "Papa Puleia": ("Palauli Le Falefa", "Papa"), "Vailoa Savaii": ("Palauli East", "Vailoa"),
}
# The 2016 district's name -> the boundary file's, where they differ by more
# than case and punctuation.
DISTRICT_ON_MAP = {"Sagaga La Falefa": "Sagaga le Falefa", "Faaleleaga III": "Faasaleleaga III",
                   "Satupaitea": "Satuipaitea", "Faasaleleaga IV": "Faasalelelaga IV"}
# Gaga'emauga I and II: their villages on Upolu are the "(PART)" polygons.
EXCLAVES = {"Gagaemauga I", "Gagaemauga II"}
# Political district (the boundary file's spelling) -> its Faipule districts.
ITUMALO = {
    "Tuamasaga": ("Vaimauga West", "Vaimauga East", "Faleata East", "Faleata West",
                  "Sagaga La Falefa", "Sagaga Le Usoga", "Safata", "Siumu"),
    "A'ana": ("Aana Alofi I", "Aana Alofi II", "Aana Alofi III", "Falelatai & Samatau",
              "Lefaga & Faleseela"),
    "Aiga-i-le-Tai": ("Aiga I Le Tai",),
    "Atua": ("Anoamaa East", "Anoamaa West", "Falealili", "Lotofaga", "Lepa",
             "Aleipata Itupa I Luga", "Aleipata Itupa I Lalo"),
    "Va'a-o-Fonoti": ("Vaa O Fonoti",),
    "Fa'asaleleaga": ("Faasaleleaga I", "Faasaleleaga II", "Faaleleaga III", "Faasaleleaga IV"),
    "Gaga'emauga": ("Gagaemauga I", "Gagaemauga II", "Gagaemauga III"),
    "Gaga'ifomauga": ("Gagaifomauga I", "Gagaifomauga II", "Gagaifomauga III"),
    "Vaisigano": ("Vaisigano East", "Vaisigano West", "Falealupo", "Alataua West"),
    "Satupa'itea": ("Salega", "Satupaitea"),
    "Palauli": ("Palauli East", "Palauli West", "Palauli Le Falefa"),
}
# Table 2's denominations as the census prints them -> the name written here.
RELIGION_NAMES = {
    "LATTER DAY SAINTS": "Church of Jesus Christ of Latter-day Saints",
    "SEVENTH DAYS ADVENTIST": "Seventh-day Adventist", "JEHOVAHS WITNESS": "Jehovah's Witnesses",
    "ASSEMBLY OF GOD": "Assemblies of God", "BAHAI": "Baha'i", "MUSLIM": "Islam",
    "NO RELIGION": "No religion", "OTHER CHURCHES": "Other churches",
    "ANGLICAN CHURCH": "Anglican", "PABTISM": "Baptist", "POROTESANO": "Porotesano (Protestant)",
    "ASO FITU (SISDAC)": "Aso Fitu (SISDAC)",
}
GROWTH = 0.4


def text(cell: Any) -> str:
    return "" if cell is None else str(cell)


# ---------------------------------------------------------------------------
# Reading the workbooks
# ---------------------------------------------------------------------------

def places(rows: list[list[Any]], name_col: int) -> list[tuple[int, str, list[Any]]]:
    """(depth, name, the row's cells after the name) for every named row.

    Depth is the name's indent in spaces, the tables' own way of nesting a
    village in its district and a district in its region.
    """
    out = []
    for row in rows:
        if len(row) <= name_col:
            continue
        raw = text(row[name_col]).replace("\t", "    ")
        name = " ".join(raw.split())
        if not name:
            continue
        out.append((len(raw) - len(raw.lstrip(" ")), name, list(row[name_col + 1:])))
    return out


def read_2016(rows: list[list[Any]]) -> list[tuple[tuple[str, str], str, float]]:
    """[((region, district), village, people)] from 2016 Brief No. 1, Table 1."""
    region = district = None
    out = []
    districts: dict[tuple[str, str], float] = {}
    total = None
    for depth, name, cells in places(rows, 1):
        people = number(cells[0]) if cells else None
        if people is None:
            continue
        if name == "Samoa":
            total = people
        elif depth == 4:
            check(name in REGIONS, f"samoa_census: 2016 region {name!r}")
            region = name
        elif depth == 8:
            check(region is not None, f"samoa_census: 2016 district {name} before a region")
            district = (region, name)
            districts[district] = people
        elif depth == 12:
            check(district is not None, f"samoa_census: 2016 village {name} before a district")
            out.append((district, name, people))
    check(total == NATIONAL_2016, f"samoa_census: 2016 Table 1 reads Samoa as {total}")
    for key, people in districts.items():
        made = sum(p for d, _, p in out if d == key)
        check(made == people, f"samoa_census: 2016 {key[1]}'s villages make {made:,.0f}, "
                              f"not {people:,.0f}")
    check(len(districts) == 43, f"samoa_census: 2016 Table 1 has {len(districts)} districts")
    return out


def read_2021(rows: list[list[Any]], width: int) -> dict[str, Any]:
    """{"villages": [(constituency, village, cells)], "constituencies": {name: cells}, "total"}.

    ``cells`` are the row's figures after the name, ``width`` of them.
    """
    out: dict[str, Any] = {"villages": [], "constituencies": {}, "total": None}
    constituency = None
    for depth, name, cells in places(rows, 0):
        values = [number(c) for c in cells[:width]]
        if not values or values[0] is None:
            continue
        values = [v or 0.0 for v in values]
        if name == "Samoa":
            out["total"] = values
        elif depth == 4:
            check(name in REGIONS, f"samoa_census: 2021 region {name!r}")
        elif depth == 8:
            constituency = name
            out["constituencies"][name] = values
        elif depth == 12:
            check(constituency is not None, f"samoa_census: 2021 village {name} before any "
                                            "constituency")
            out["villages"].append((constituency, name, values))
    check(out["total"] is not None and out["total"][0] == NATIONAL,
          f"samoa_census: 2021 reads Samoa as {out['total'] and out['total'][0]}")
    for name, values in out["constituencies"].items():
        made = [sum(v[i] for c, _, v in out["villages"] if c == name) for i in range(width)]
        check(made == values, f"samoa_census: 2021 {name}'s villages do not make it")
    return out


def age_columns(header: list[Any]) -> tuple[list[tuple[int, int]], int | None]:
    """[(age, column of its Total)] from Table 1's heading row, and the DK column."""
    ages, unknown = [], None
    for i, cell in enumerate(header):
        label = text(cell).strip().lower()
        found = re.fullmatch(r"age\s*(\d+)", label)
        if found:
            ages.append((int(found.group(1)), i))
        elif label in ("dk", "not stated", "don't know"):
            unknown = i
    check(ages and [a for a, _ in ages] == list(range(len(ages))),
          f"samoa_census: Table 1's ages run {[a for a, _ in ages][:5]}...")
    return ages, unknown


def religion_columns(header: list[Any]) -> list[tuple[str, int]]:
    """[(denomination, column of its Total)] from Table 2's heading row."""
    out = []
    for i, cell in enumerate(header):
        label = " ".join(text(cell).split())
        if label and label.upper() != "TOTAL" and i > 0:
            upper = label.upper()
            name = RELIGION_NAMES.get(upper, label.title().replace(" Of ", " of "))
            if name in [n for n, _ in out]:
                name = f"{name} ({len([n for n, _ in out if n.startswith(name)]) + 1})"
            out.append((name, i))
    return out


def read_citizenship(rows: list[list[Any]]) -> dict[str, Any]:
    """Table 8a by place: [total, born in Samoa, born abroad, naturalised, not a citizen],
    each as both sexes, male, female -- 15 figures after the name.

    The heading row is found by its first cell, and its four answers must start with
    ``CITIZENSHIP_HEADINGS`` in that order; every row's sexes make each answer and the
    four answers make its total; the country's citizens and others are the Fact Sheet's.
    """
    at = next((i for i, row in enumerate(rows)
               if row and text(row[0]).strip().lower() == "place of residence"), None)
    check(at is not None, "samoa_census: Table 8a has no 'Place of residence' heading")
    heading = [" ".join(text(c).split()).upper() for c in rows[at]]
    for k, words in enumerate(CITIZENSHIP_HEADINGS, start=1):
        check(len(heading) > 1 + 3 * k and heading[1 + 3 * k].startswith(" ".join(words.split())),
              f"samoa_census: Table 8a's column {1 + 3 * k} is headed {heading[1 + 3 * k:2 + 3 * k]}"
              f", not {words!r}")
    got = read_2021(rows, 15)
    for _, village, v in got["villages"] + [("", "Samoa", got["total"])]:
        for k in range(5):
            check(v[3 * k] == v[3 * k + 1] + v[3 * k + 2],
                  f"samoa_census: Table 8a's sexes for {village} do not make column {3 * k + 1}")
        check(v[0] == v[3] + v[6] + v[9] + v[12],
              f"samoa_census: Table 8a's answers for {village} make "
              f"{v[3] + v[6] + v[9] + v[12]:,.0f}, not {v[0]:,.0f}")
    national = got["total"]
    check((national[3] + national[6] + national[9], national[12])
          == (CITIZENS_2021, NON_CITIZENS_2021),
          f"samoa_census: Table 8a counts {national[3] + national[6] + national[9]:,.0f} citizens "
          f"and {national[12]:,.0f} others, the Fact Sheet {CITIZENS_2021:,} and "
          f"{NON_CITIZENS_2021:,}")
    return got


# ---------------------------------------------------------------------------
# 2021 villages -> 2016 districts
# ---------------------------------------------------------------------------

def place_villages(old: list[tuple[tuple[str, str], str, float]],
                   new: list[tuple[str, str, Any]]) -> tuple[dict[tuple[str, str], tuple[str, str]],
                                                             list[str]]:
    """{(constituency, village): (region, district)} for every 2021 village.

    Returns the placements and the names of villages placed by their
    constituency because the 2016 census did not list them.
    """
    by_name: dict[str, list[tuple[str, str]]] = {}
    for district, village, _ in old:
        by_name.setdefault(fold(village), []).append(district)

    def named(village: str) -> list[tuple[str, str]]:
        target = RENAMED.get(village, village)
        if isinstance(target, tuple):
            hits = [d for d in by_name.get(fold(target[1]), []) if d[1] == target[0]]
            check(len(hits) >= 1, f"samoa_census: no 2016 {target[1]} in {target[0]}")
            return hits
        return by_name.get(fold(target), [])

    placed: dict[tuple[str, str], tuple[str, str]] = {}
    later = []
    for constituency, village, _ in new:
        hits = named(village)
        if len(set(hits)) == 1:
            placed[(constituency, village)] = hits[0]
        else:
            later.append((constituency, village, hits))
    home: dict[str, Counter] = {}
    for (constituency, _), district in placed.items():
        home.setdefault(constituency, Counter())[district] += 1
    new_villages = []
    for constituency, village, hits in later:
        votes = home.get(constituency, Counter())
        options = [d for d in hits] or list(votes)
        check(options, f"samoa_census: 2021 village {village} ({constituency}) has no 2016 "
                       "district and no neighbour placed")
        ranked = sorted(set(options), key=lambda d: -votes.get(d, 0))
        check(len(ranked) == 1 or votes.get(ranked[0], 0) > votes.get(ranked[1], 0),
              f"samoa_census: 2021 village {village} ({constituency}) could be in "
              f"{[d[1] for d in ranked]}")
        placed[(constituency, village)] = ranked[0]
        if not hits:
            new_villages.append(f"{village} ({constituency}) -> {ranked[0][1]}")
    return placed, new_villages


def districts_of(placed: dict[tuple[str, str], tuple[str, str]], new: list[tuple[str, str, Any]],
                 width: int) -> dict[tuple[str, str], list[float]]:
    out: dict[tuple[str, str], list[float]] = {}
    for constituency, village, values in new:
        key = placed[(constituency, village)]
        row = out.setdefault(key, [0.0] * width)
        for i in range(width):
            row[i] += values[i]
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

CITIZENSHIP_NOTE = (
    "Citizenship, not ethnicity. Samoa's census tables carry no ethnicity: the 2021 workbook's "
    "58 tables and its Fact Sheet, the 2016 census's four Briefs' tables and the 2011 census's "
    "93 tables have none, and 2021 and 2011 give Samoan citizenship instead (2021 Table 8a, by "
    "village; 2011 Table 8, by urban and rural residence only). "
    "Under the owner's rule for states that count citizenship rather than ethnicity, this is "
    "the 2021 count of the people here by citizenship: 'Samoan' is every citizen -- born in "
    "Samoa or abroad to a citizen parent ({born_here:,.0f} and {born_abroad:,.0f} here), or "
    "naturalised ({naturalised:,.0f}) -- and 'Foreign nationals' the {foreign:,.0f} who are "
    "not. A Samoan citizen may be of any ancestry.")
LANGUAGE_GAP = (
    "No language spoken is published: the 2021 workbook's 58 tables have no language table and "
    "its Fact Sheet reports only literacy in Samoan and English (indicators Edn.3 and Edn.4); "
    "the 2016 census's Brief No. 3 tables give literacy in any language (Tables 3-6) and the "
    "2011 census's 93 tables literacy in Samoan (Tables 23-26), both by urban and rural "
    "residence only.")


def citizenship_fields(c: list[float]) -> dict[str, Any]:
    """Table 8a's columns added up: [total, born in Samoa, born abroad, naturalised, not]."""
    return {
        "ethnicity": shares_of({"Samoan": c[1] + c[2] + c[3], "Foreign nationals": c[4]}, c[0]),
        "ethnicity_year": YEAR,
        "ethnicity_basis": "nationality",
        "ethnicity_note": CITIZENSHIP_NOTE.format(born_here=c[1], born_abroad=c[2],
                                                  naturalised=c[3], foreign=c[4]),
    }


def fields_for(totals: list[float], ages: dict[int, float], unknown: float,
               religion: dict[str, float], citizens: list[float]) -> dict[str, Any]:
    median = median_from_single_years(ages)
    unstated = (f" {unknown:,.0f} people whose age was not known are left out of it."
                if unknown else "")
    return {
        **citizenship_fields(citizens),
        "population": population(totals[0], YEAR, f"{SOURCE} (Table 1)"),
        "sex_ratio": measure(sex_ratio(totals[1], totals[2]), unit="males_per_100_females",
                             year=YEAR, source=SOURCE),
        "sex_ratio_note": "Males per 100 females, 2021 Census (Table 1).",
        "median_age": (measure(median, unit="years", year=YEAR, source=SOURCE)
                       if median is not None else None),
        "median_age_note": ("Interpolated within the single year of age that holds the "
                            "middle person, 2021 Census (Table 1)." + unstated),
        "religion": shares_of(religion, totals[0]),
        "religion_year": YEAR,
        "religion_note": "Religion, 2021 Census (Table 2), in the census's own denominations.",
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


SOURCES = [
    {"field": "population/median_age/sex_ratio/religion/ethnicity (citizenship)",
     "name": f"{SOURCE} (Tables 1, 2 and 8a)", "url": URL,
     "year": YEAR, "license": "None stated -- Samoa Bureau of Statistics publication, cited "
                              "as such"},
    {"field": "language (why empty); ethnicity (none published)",
     "name": f"{OFFICE}, 2021 Census Fact Sheet; 2011 Census Excel tables", "url": FACTSHEET_URL,
     "year": YEAR, "license": "None stated -- Samoa Bureau of Statistics publication, cited "
                              "as such"},
    {"field": "the district each village is in", "name": SOURCE_2016, "url": URL_2016,
     "year": 2016, "license": "None stated -- Samoa Bureau of Statistics publication, cited "
                              "as such"},
]


def national_medians(sub_header: list[Any], nation: list[float],
                     ages_at: list[tuple[int, int]]) -> str:
    """Samoa's medians from Table 1's single years, the sexes checked against the Bureau's.

    Each age's Total column is followed by its MALE and FEMALE ones. Returns the
    account for the log.
    """
    sub = [text(c).strip().upper() for c in sub_header]
    check(all(sub[i:i + 3] == ["TOTAL", "MALE", "FEMALE"] for _, i in ages_at),
          "samoa_census: Table 1's ages are not each Total, Male and Female")
    got = {who: median_from_single_years({age: nation[i - 1 + shift] for age, i in ages_at})
           for who, shift in (("everyone", 0), ("males", 1), ("females", 2))}
    checked = [published_median(got[who], PRINTED_MEDIANS[who], f"samoa_census: Samoa's {who}",
                                whole_years=True) for who in ("males", "females")]
    return (f"Samoa's median ages from Table 1's single years: {', '.join(checked)}; everyone "
            f"{got['everyone']}, where the Final Report prints {PRINTED_MEDIANS['everyone']} "
            f"and the Fact Sheet {FACT_SHEET_MEDIAN} -- outside the sexes' "
            f"{PRINTED_MEDIANS['males']} and {PRINTED_MEDIANS['females']}")


def build(book, book_2016, admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    old = read_2016(rows_of(book_2016, "Table 1 Pop by sex_sex"))
    age_rows = rows_of(book, "Table 1")
    religion_rows = rows_of(book, "Table 2")
    ages_at, unknown_at = age_columns(age_rows[1])
    faiths = religion_columns(religion_rows[1])
    age_width = max(i for _, i in ages_at + [(0, unknown_at or 0)]) + 1 - 1
    people = read_2021(age_rows, age_width)
    religion = read_2021(religion_rows, max(i for _, i in faiths))
    check([(c, v) for c, v, _ in people["villages"]] == [(c, v) for c, v, _ in religion["villages"]],
          "samoa_census: Tables 1 and 2 list different villages")
    citizenship = read_citizenship(rows_of(book, "Table 8a"))
    check([(c, v) for c, v, _ in people["villages"]]
          == [(c, v) for c, v, _ in citizenship["villages"]],
          "samoa_census: Tables 1 and 8a list different villages")

    def cell(values: list[float], column: int) -> float:
        return values[column - 1]

    for (constituency, village, a), (_, _, r) in zip(people["villages"], religion["villages"]):
        check(a[0] == a[1] + a[2], f"samoa_census: {village}: males and females do not make "
                                   f"{a[0]:,.0f}")
        years = sum(cell(a, i) for _, i in ages_at) + (cell(a, unknown_at) if unknown_at else 0)
        check(years == a[0], f"samoa_census: {village}'s ages make {years:,.0f}, not {a[0]:,.0f}")
        faith = sum(cell(r, i) for _, i in faiths)
        check(r[0] == a[0] and faith == r[0],
              f"samoa_census: {village}'s denominations make {faith:,.0f}, not {r[0]:,.0f}")
    for (_, village, a), (_, _, c) in zip(people["villages"], citizenship["villages"]):
        check(c[0] == a[0], f"samoa_census: Table 8a counts {c[0]:,.0f} in {village}, Table 1 "
                            f"{a[0]:,.0f}")
    log("  " + national_medians(age_rows[2], people["total"], ages_at))

    placed, new_villages = place_villages(old, people["villages"])
    for line in new_villages:
        log(f"  not in the 2016 list, placed with its constituency's villages: {line}")
    by_age = districts_of(placed, people["villages"], age_width)
    by_faith = districts_of(placed, religion["villages"], max(i for _, i in faiths))
    by_citizenship = districts_of(placed, citizenship["villages"], 15)
    olds = Counter()
    for district, _, count in old:
        olds[district] += count
    check(set(by_age) == set(olds), f"samoa_census: 2016 districts with no 2021 village: "
                                    f"{sorted(set(olds) - set(by_age))}")
    for key, values in by_age.items():
        change = values[0] / olds[key] - 1
        check(abs(change) <= GROWTH, f"samoa_census: {key[1]} ({key[0]}) has {values[0]:,.0f} "
                                     f"in 2021 and {olds[key]:,.0f} in 2016")

    def fields(keys: list[tuple[str, str]]) -> dict[str, Any]:
        a = [sum(by_age[k][i] for k in keys) for i in range(age_width)]
        r = [sum(by_faith[k][i] for k in keys) for i in range(len(by_faith[keys[0]]))]
        c = [sum(by_citizenship[k][i] for k in keys) for i in (0, 3, 6, 9, 12)]
        return fields_for(a[:3], {age: cell(a, i) for age, i in ages_at},
                          cell(a, unknown_at) if unknown_at else 0.0,
                          {name: cell(r, i) for name, i in faiths}, c)

    def polygon_name(key: tuple[str, str]) -> str:
        region, district = key
        name = DISTRICT_ON_MAP.get(district, district)
        return f"{name} (PART)" if district in EXCLAVES and region in UPOLU else name

    parents = {u["id"]: u["name"] for u in admin1}
    itumalo_of = {d: i for i, ds in ITUMALO.items() for d in ds}
    check(set(itumalo_of) == {d for _, d in olds},
          f"samoa_census: districts without a political district: "
          f"{sorted({d for _, d in olds} ^ set(itumalo_of))}")
    district_units = bind_level({f"{r}|{d}": (polygon_name((r, d)), itumalo_of[d])
                                 for r, d in olds}, admin2, parents)
    itumalo_units = bind_level({i: (i, "") for i in ITUMALO}, admin1, {})

    records = []
    for name, unit in itumalo_units.items():
        keys = [k for k in by_age if itumalo_of[k[1]] == name]
        rec_fields = fields(keys)
        rec_fields["population_note"] = (
            "Its Faipule districts' 2021 villages added up: " + ", ".join(
                sorted({k[1] for k in keys})) + ".")
        records.append(unit_record("WSM", name, unit["name"], unit, "admin1", None, SOURCES,
                                   **rec_fields))
    for code, unit in district_units.items():
        region, district = code.split("|")
        rec_fields = fields([(region, district)])
        villages = sorted(v for (c, v), d in placed.items() if d == (region, district))
        rec_fields["population_note"] = (
            f"The 2021 Census counts of the {len(villages)} villages the 2016 Census lists in "
            f"{district}" + (f" on {'Upolu' if region in UPOLU else 'Savaii'}"
                             if district in EXCLAVES else "")
            + ": " + ", ".join(villages) + ".")
        records.append(unit_record("WSM", code, unit["name"], unit, "admin2",
                                   itumalo_of[district], SOURCES, **rec_fields))
    return records


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("samoa_census: 2021 Census Tables 1 and 2, by the 2016 Census's villages")
    records = build(workbook(URL), workbook(URL_2016), load_units("WSM", "admin1"),
                    load_units("WSM", "admin2"))
    log(f"  {len(records)} records: {summarise(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
