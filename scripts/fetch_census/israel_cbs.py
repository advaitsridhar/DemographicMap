#!/usr/bin/env python3
"""Israel's districts and sub-districts: population by population group, CBS.

The Central Bureau of Statistics' *Statistical Abstract of Israel 2024*
(No. 75), Table 2.17 -- "Localities and population, by population group,
district, sub-district and natural region" -- gives every district and
sub-district's population on 31 December 2023, in thousands to one decimal,
as Jews and others, Arabs, and foreigners (people in Israel who are not
Israeli citizens or permanent residents). The workbook is
``st02_17.xlsx`` of the abstract's population chapter.

**What is written** on each unit the map draws as the CBS counts it: the
population, and its people by population group on the ethnicity field
(``ethnicity_basis`` "population group", the CBS's own classification).
Two more tables of the same chapter add, for Israelis (citizens and
permanent residents, not foreigners):

* Table 2.19 (``st02_19x.xlsx``, average 2023): the median age, as the CBS
  computes it, and men and women, for every district and sub-district;
* Table 2.15 (``st02_15x.xlsx``, 31 December 2023): people by the religion
  the population register records, for each district. Sub-districts are
  not written (the table lists their smaller religions only where they are
  large), except Tel Aviv's, which is the district.

**Population groups.** Table 2.17 prints the Israelis in two groups, "Jews
and others" and "Arabs". Filed as one bar, "Jews and others" would colour
the map Jewish for its others too -- the non-Arab Christians, members of
other religions and people the register classifies by no religion, 7
points of the Haifa District. Table 2.15 lists every district's and
sub-district's Jews on the same date, and the CBS's population group "Jews"
is the register's religion "Jews", so the bar is written as two: the Jews
(labelled "Jewish", as the map's country row has them), and the rest of
the group as "Others (not Jews or Arabs)". The CBS's "Arabs" are Muslims,
Arab Christians and the Druze together, as the note says.

**Language** is in no table of the abstract by district or sub-district,
and UNdata holds no census language table for Israel, so every unit says
so.

**Where the map and the CBS draw different ground** (the Asia brief's rule:
bind only to the polygon the source counts):

* *Golan.* The CBS's Northern District includes the Golan sub-district; the
  map draws the Golan Heights inside Syria's Quneitra governorate and only a
  sliver under Israel's "Golan". So the Golan sub-district's figure is
  bound nowhere, and the Northern District is written as the sum of its
  four other sub-districts (Zefat, Kinneret, Yizre'el, Akko), which the
  drawn district is; its median age is interpolated within those four
  sub-districts' summed age groups, and its religion is left unwritten
  (the table does not give the Golan's smaller religions apart).
* *Jerusalem.* The CBS's Jerusalem District -- a single sub-district, which
  the table divides only into the Judean Mountains and Judean Foothills
  natural regions -- counts all of Jerusalem's municipal area, East
  Jerusalem included, which the map draws within the West Bank (measured on
  the map's tiles: the Old City, Sheikh Jarrah, Silwan, Beit Hanina,
  Shuafat, Ramot, Pisgat Ze'ev, Neve Ya'akov, Gilo and Har Homa fall in the
  West Bank's polygon; Rehavia, Katamon, Talpiot, Kiryat HaYovel, Mount
  Scopus, Mevaseret Zion, Abu Ghosh and Beit Shemesh in this one). Its
  figure is not the drawn polygon's, and the abstract gives none for the
  district without East Jerusalem, so the district and the drawn
  "Jerusalem" sub-district both say so. The statement displaces an
  encyclopaedia's population for either shape dated before
  ``DISPLACES_BEFORE`` (the build's ``displaces_before``): Wikidata's are
  the whole district's (1,034,200, 2014) and the whole city's (1,050,151,
  2024), both counting East Jerusalem as the CBS does.

**Checks** (any failure stops the run): each row's groups make its total
(to the table's rounding, 0.1 thousand per term); the sub-districts make
their district; each age row's groups make its total and its women are
fewer than everyone; a district's listed religions do not exceed its
total and leave at most 1,500 people unnamed. What the six districts leave
of the country's total row -- the Israelis of the Judea and Samaria Area --
is logged.

Usage:
    python -m scripts.fetch_census.israel_cbs
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import check, median_age, units, workbook

ISO3 = "ISR"
OUT = "israel_cbs.json"
URL = "https://www.cbs.gov.il/he/publications/doclib/2024/2.shnatonpopulation/st02_17.xlsx"
YEAR = 2023
SOURCE = ("Central Bureau of Statistics (Israel), Statistical Abstract of Israel 2024 "
          "(No. 75), Table 2.17: population by population group, district and "
          "sub-district, 31 December 2023")
LICENCE = "Central Bureau of Statistics (Israel), published statistical abstract"
# Table rounding: each figure is in thousands to one decimal.
ROUND = 0.1
DISTRICTS = {
    "JERUSALEM DISTRICT": "Jerusalem District",
    "NORTHERN DISTRICT": "Northern District",
    "HAIFA DISTRICT": "Haifa",
    "CENTRAL DISTRICT": "Central District",
    "TEL AVIV DISTRICT": "Tel Aviv",
    "SOUTHERN DISTRICT": "Southern District",
}
# The CBS's sub-district -> the boundary file's label.
SUBDISTRICTS = {
    "Zefat": "Zefat", "Kinneret": "Kinneret", "Yizre'el": "Yizre'el", "Akko": "Akko",
    "Golan": "Golan", "Haifa": "Haifa", "Hadera": "Hadera", "Sharon": "HaSharon",
    "Petah Tiqwa": "Petah Tiqwa", "Ramla": "Ramla", "Rehovot": "Rehovot",
    "Tel Aviv": "Tel Aviv", "Ashqelon": "Ashqelon", "Be'er Sheva": "Be'er Sheva",
}
# The Jerusalem District is one sub-district, which the boundary file draws
# as "Jerusalem"; the table lists only its natural regions beneath it.
JERUSALEM_LABEL = "Jerusalem"
GOLAN_WHY = ("The CBS counts the Golan Heights as the Golan sub-district of the Northern "
             "District; the map draws the Golan Heights within Syria's Quneitra "
             "governorate, and this shape is a sliver of it, so no CBS figure is this "
             "shape's.")
JERUSALEM_WHY = ("The CBS's Jerusalem figures count all of Jerusalem's municipal area, East "
                 "Jerusalem included, which the map draws within the West Bank; the CBS "
                 "publishes no figure for the part of the district this shape is. "
                 "Encyclopaedia figures for the district or the city of Jerusalem count East "
                 "Jerusalem too, and are not shown here.")
# The statement displaces an encyclopaedia's population for the Jerusalem
# shapes dated before this year (the build's ``displaces_before``): checked in
# 2026 against the CBS's abstracts, which count East Jerusalem in every
# Jerusalem figure they print. A figure dated 2026 or later is newer than the
# check and stands until the reader is looked at again.
DISPLACES_BEFORE = 2026
GROUPS = ("Foreign nationals", "Arabs", "Jews and others")
# Table 2.17's "Jews and others", written as Table 2.15's Jews and the rest.
# "Jewish" is the label the map's country row (and the group tree's node)
# gives the same people.
JEWS = "Jewish"
OTHERS = "Others (not Jews or Arabs)"
LANGUAGE_WHY = (
    "No CBS table of language by district or sub-district could be found: the Statistical "
    "Abstract of Israel 2024's population chapter tabulates population group, religion, age "
    "and sex; UNdata's census tables reported to the UN Statistics Division hold no language "
    "table for Israel; and the CBS's census and social-survey pages could not be read on 9 "
    "October 2026 (their content is drawn by script, and the Internet Archive's index of the "
    "2008 census site did not answer).")
# Table 2.19: Israelis by age and sex (average 2023), with the CBS's median.
URL_AGES = "https://www.cbs.gov.il/he/publications/doclib/2024/2.shnatonpopulation/st02_19x.xlsx"
SOURCE_AGES = ("Central Bureau of Statistics (Israel), Statistical Abstract of Israel 2024 "
               "(No. 75), Table 2.19: Israelis by age and sex, district and sub-district, "
               "average 2023")
# The table's age columns, oldest first, as printed.
AGE_COLUMNS = [(75, None), (65, 74), (55, 64), (45, 54), (35, 44), (30, 34), (25, 29),
               (20, 24), (15, 19), (5, 14), (0, 4)]
# Table 2.15: Israelis by religion, district and sub-district, 31 December 2023.
URL_RELIGION = ("https://www.cbs.gov.il/he/publications/doclib/2024/2.shnatonpopulation/"
                "st02_15x.xlsx")
SOURCE_RELIGION = ("Central Bureau of Statistics (Israel), Statistical Abstract of Israel 2024 "
                   "(No. 75), Table 2.15: Israelis by district, sub-district and religion, "
                   "31 December 2023")
# The table's religion sections, as the map writes them.
RELIGIONS = {"JEWS": "Judaism", "MOSLEMS": "Muslims", "CHRISTIANS": "Christianity",
             "DRUZE": "Druze", "NOT CLASSIFIED": "Not classified by religion"}
# The column of the 31 December 2023 count, in thousands.
RELIGION_COLUMN = 9
# A district's religions the table does not list (Druze outside the Northern
# and Haifa districts) may leave at most this many thousand unnamed.
UNLISTED = 1.5
HEBREW_DISTRICTS = {
    "\u05de\u05d7\u05d5\u05d6 \u05d9\u05e8\u05d5\u05e9\u05dc\u05d9\u05dd": "JERUSALEM DISTRICT",
    "\u05de\u05d7\u05d5\u05d6 \u05d4\u05e6\u05e4\u05d5\u05df": "NORTHERN DISTRICT",
    "\u05de\u05d7\u05d5\u05d6 \u05d7\u05d9\u05e4\u05d4": "HAIFA DISTRICT",
    "\u05de\u05d7\u05d5\u05d6 \u05d4\u05de\u05e8\u05db\u05d6": "CENTRAL DISTRICT",
    "\u05de\u05d7\u05d5\u05d6 \u05ea\u05dc \u05d0\u05d1\u05d9\u05d1": "TEL AVIV DISTRICT",
    "\u05de\u05d7\u05d5\u05d6 \u05d4\u05d3\u05e8\u05d5\u05dd": "SOUTHERN DISTRICT",
}
HEBREW = re.compile(r"[\u0590-\u05FF]")
# "Thereof:" in Hebrew, which opens a row the English column leaves blank.
THEREOF_HE = "\u05de\u05d6\u05d4:"
SUB_RELIGION_WHY = (
    "The CBS publishes religion by sub-district only in part: Table 2.15 of the "
    "Statistical Abstract of Israel 2024 lists every sub-district's Jews, but its "
    "Muslims, Christians, Druze and people of no classified religion only for the "
    "sub-districts where each is numerous, so no full religious breakdown of the "
    "{name} sub-district is published.")


def figure(cell: Any) -> float | None:
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return float(cell)
    text = str(cell or "").strip()
    return 0.0 if text in ("-", "0") else None


def name_of(label: str) -> tuple[str, str | None]:
    """('district', KEY) or ('subdistrict', name) or ('', None)."""
    text = re.sub(r"\(\d+\)", "", label).strip()
    if text.upper() in DISTRICTS:
        return "district", text.upper()
    m = re.match(r"^(.*?)\s*S\.D\.?$", text)
    if m:
        return "subdistrict", m.group(1).strip()
    if text.upper().startswith("TOTAL POPULATION"):
        return "total", "TOTAL"
    return "", None


def read(sheets: dict[str, list[list[Any]]]) -> dict[tuple[str, str], dict[str, float]]:
    """(kind, name) -> {group: people, total}, from every sheet of Table 2.17."""
    out: dict[tuple[str, str], dict[str, float]] = {}
    district = None
    for rows in sheets.values():
        for row in rows:
            if not row or not isinstance(row[0], str):
                continue
            kind, name = name_of(row[0])
            if not kind:
                continue
            cells = [figure(c) for c in row[1:6]]
            if any(c is None for c in cells):
                continue
            foreign, arabs, jews, israelis, total = cells
            where = f"{kind} {name}"
            check(abs(arabs + jews - israelis) <= 2 * ROUND + 1e-9,
                  f"israel_cbs: {where}: Arabs and Jews-and-others do not make the Israelis")
            check(abs(israelis + foreign - total) <= 2 * ROUND + 1e-9,
                  f"israel_cbs: {where}: Israelis and foreigners do not make the total")
            if kind == "district":
                district = name
            entry = {"Foreign nationals": foreign * 1000, "Arabs": arabs * 1000,
                     "Jews and others": jews * 1000, "total": total * 1000,
                     "district": district if kind == "subdistrict" else name}
            check((kind, name) not in out, f"israel_cbs: {where} twice")
            out[(kind, name)] = entry
    return out


def read_ages(sheets: dict[str, list[list[Any]]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(kind, name) -> everyone's median and age groups, everyone, females (Table 2.19).

    The first sheet's first section is the whole population: each row carries
    the females (median, eleven age groups, total) and then everyone (the
    same thirteen columns). The section ends at the next section's heading.
    """
    rows = next(iter(sheets.values()))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    started = False
    for row in rows:
        label = row[0] if row else None
        if started and not label and any(isinstance(c, str) and c.strip() for c in row[1:3]):
            break
        if not isinstance(label, str):
            continue
        kind, name = name_of(label)
        if not kind or len(row) < 27:
            continue
        cells = [figure(c) for c in row[1:27]]
        if any(c is None for c in cells):
            continue
        started = True
        females, everyone = cells[:13], cells[13:]
        groups = sorted((lo, hi, n * 1000) for (lo, hi), n in zip(AGE_COLUMNS, everyone[1:12]))
        made = sum(n for _a, _b, n in groups) / 1000
        check(abs(made - everyone[12]) <= ROUND * 6 + 1e-9,
              f"israel_cbs: Table 2.19 {kind} {name}: age groups make {made:,.1f}, not "
              f"{everyone[12]:,.1f}")
        check(0 < females[12] < everyone[12], f"israel_cbs: Table 2.19 {kind} {name}: "
                                              f"females {females[12]} of {everyone[12]}")
        out[(kind, name)] = {"median": everyone[0], "groups": groups,
                             "total": everyone[12] * 1000, "females": females[12] * 1000}
    check(bool(out), "israel_cbs: Table 2.19 read no rows")
    return out


def religion_rows(sheets: dict[str, list[list[Any]]]):
    """(section, row, thousands) for every figure row of Table 2.15.

    Sections follow their headings (TOTAL POPULATION, JEWS, MOSLEMS, ...); the
    section is "total" or a key of ``RELIGIONS``.
    """
    section = None
    for rows in sheets.values():
        for row in rows:
            if not row:
                continue
            head = str(row[1]).strip().upper() if len(row) > 1 and isinstance(row[1], str) \
                else ""
            if not (isinstance(row[0], str) and row[0].strip()) and head and not any(
                    figure(c) is not None for c in row[2:RELIGION_COLUMN + 1]):
                if head.startswith("TOTAL POPULATION"):
                    section = "total"
                else:
                    section = next((k for k in RELIGIONS if head.startswith(k)), section)
                continue
            if section is None or len(row) <= RELIGION_COLUMN:
                continue
            value = figure(row[RELIGION_COLUMN])
            if value is not None:
                yield section, row, value


def read_religion(sheets: dict[str, list[list[Any]]]) -> dict[str, dict[str, float]]:
    """District -> people by religion and in all, 31 December 2023 (Table 2.15).

    A row is a district by its English label, or -- where the English is left
    blank under a "Thereof" -- by its Hebrew one; sub-district rows are not
    read, because the table lists the smaller religions only where they are
    large.
    """
    out: dict[str, dict[str, float]] = {}
    for section, row, value in religion_rows(sheets):
        english = re.sub(r"^\s*Thereof:\s*", "", str(row[0] or ""), flags=re.I)
        kind, name = name_of(english) if english.strip() else ("", None)
        if kind != "district":
            hebrew = next((str(c).strip() for c in reversed(row)
                           if isinstance(c, str) and HEBREW.search(c)), "")
            hebrew = hebrew.replace(THEREOF_HE, "").strip()
            name = HEBREW_DISTRICTS.get(hebrew)
            if name is None:
                continue
        key_ = "total" if section == "total" else RELIGIONS[section]
        entry = out.setdefault(name, {})
        check(key_ not in entry, f"israel_cbs: Table 2.15 {name} {key_} twice")
        entry[key_] = value * 1000
    check(set(DISTRICTS) <= set(out), f"israel_cbs: Table 2.15 districts {sorted(out)}")
    return out


def read_jews(sheets: dict[str, list[list[Any]]]) -> dict[tuple[str, str], float]:
    """(kind, name) -> Jews on 31 December 2023, for every district and sub-district.

    Table 2.15 lists the Jews of every district and of every sub-district
    under its English label (the smaller religions it lists only where they
    are numerous, so this is the one section read below the district).
    """
    out: dict[tuple[str, str], float] = {}
    for section, row, value in religion_rows(sheets):
        if section != "JEWS" or "thereof" in str(row[0] or "").lower():
            continue
        kind, name = name_of(str(row[0] or ""))
        if kind not in ("district", "subdistrict"):
            continue
        check((kind, name) not in out, f"israel_cbs: Table 2.15 Jews of {name} twice")
        out[(kind, name)] = value * 1000
    return out


def age_fields(a: dict[str, Any], what: str, *, ours: bool = False) -> dict[str, Any]:
    """Median age and males per 100 females from Table 2.19's row(s)."""
    men = a["total"] - a["females"]
    if ours:
        median = median_age(a["groups"], year=YEAR, source=SOURCE_AGES)
        how = ("interpolated within the table's age groups (0-4, 5-14, 15-19 and so on to "
               "75+) summed over " + what + ", since the CBS's own median is for a "
               "different ground")
    else:
        median = measure(a["median"], unit="years", year=YEAR, source=SOURCE_AGES)
        how = "the CBS's own median for " + what
    return {
        "median_age": median,
        "median_age_note": (f"Median age of Israelis (citizens and permanent residents, not "
                            f"foreigners), average 2023: {how}."),
        "sex_ratio": measure(round(100 * men / a["females"], 1), unit="males_per_100_females",
                             year=YEAR, source=SOURCE_AGES),
        "sex_ratio_note": (f"Males per 100 females among Israelis, average 2023: "
                           f"{men:,.0f} men and {a['females']:,.0f} women in {what}, the "
                           f"men being the table's total less its females, in thousands to "
                           f"one decimal."),
    }


def religion_fields(r: dict[str, float], what: str) -> dict[str, Any]:
    counts = {lab: r[lab] for lab in RELIGIONS.values() if r.get(lab)}
    listed = sum(counts.values())
    check(listed <= r["total"] + 1000 * ROUND * 5,
          f"israel_cbs: {what}: religions make {listed:,.0f}, more than {r['total']:,.0f}")
    check(r["total"] - listed <= 1000 * UNLISTED,
          f"israel_cbs: {what}: {r['total'] - listed:,.0f} people of no listed religion")
    rest = r["total"] - listed
    return {
        "religion": shares(counts, total=r["total"]),
        "religion_year": YEAR,
        "religion_basis": "religion as recorded in the population register",
        "religion_note": (
            f"Israelis (citizens and permanent residents, not foreigners) by the religion "
            f"the population register records, 31 December 2023, in thousands to one "
            f"decimal. 'Not classified by religion' is the register's own category, mostly "
            f"immigrants under the Law of Return who are not Jewish."
            + (f" The table lists the Druze only in the Northern and Haifa districts; the "
               f"remaining {rest:,.0f} people of {what} are of no religion it lists here."
               if rest >= 50 else "")),
    }


def population_groups(v: dict[str, float], jews: float | None, what: str
                      ) -> tuple[dict[str, float], str]:
    """The unit's people by population group, and the note that says what they are.

    With Table 2.15's Jews for the unit, "Jews and others" is written as the
    Jews and the rest of the group; the rest may fall below nothing only by
    the two tables' rounding, 0.1 thousand, or the run stops.
    """
    tail = (" Arabs are the CBS's group of Muslims, Arab Christians and the Druze. "
            "Foreign nationals are residents who are neither citizens nor permanent "
            "residents. Published in thousands to one decimal.")
    if jews is None:
        counts = {g: v[g] for g in GROUPS if v[g]}
        return counts, ("The CBS's population groups: Jews and others (others being non-Arab "
                        "Christians, members of other religions and people the population "
                        "register classifies by no religion), Arabs, and foreign nationals."
                        + tail)
    rest = v["Jews and others"] - jews
    check(rest >= -1000 * 2 * ROUND, f"israel_cbs: {what}: Table 2.15 counts {jews:,.0f} Jews, "
                                     f"more than Table 2.17's {v['Jews and others']:,.0f} "
                                     f"Jews and others")
    counts = {"Foreign nationals": v["Foreign nationals"], "Arabs": v["Arabs"], JEWS: jews,
              OTHERS: max(rest, 0.0)}
    return ({k: n for k, n in counts.items() if n},
            "The CBS's population groups on 31 December 2023. Table 2.17 prints the Jews "
            "with the others as one group; the Jews are Table 2.15's count of the same "
            "date (the CBS's group 'Jews' is the register's religion), and 'Others (not Jews "
            "or Arabs)' is the rest of that group: non-Arab Christians, members of other "
            "religions and people the population register classifies by no religion, "
            f"{max(rest, 0.0):,.0f} people here." + tail)


def build(table: dict[tuple[str, str], dict[str, float]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], parents: dict[str, str],
          ages: dict[tuple[str, str], dict[str, Any]] | None = None,
          religion: dict[str, dict[str, float]] | None = None,
          jews: dict[tuple[str, str], float] | None = None) -> list[dict[str, Any]]:
    ages = ages or {}
    religion = religion or {}
    jews = dict(jews or {})
    if jews and ("subdistrict", "Tel Aviv") not in jews \
            and ("district", "TEL AVIV DISTRICT") in jews:
        jews[("subdistrict", "Tel Aviv")] = jews[("district", "TEL AVIV DISTRICT")]
    if ("subdistrict", "Tel Aviv") not in ages and ("district", "TEL AVIV DISTRICT") in ages:
        ages[("subdistrict", "Tel Aviv")] = ages[("district", "TEL AVIV DISTRICT")]
    districts = {n: v for (k, n), v in table.items() if k == "district"}
    subs = {n: v for (k, n), v in table.items() if k == "subdistrict"}
    # The Tel Aviv District is a single sub-district, which the table may list
    # only as the district.
    if "Tel Aviv" not in subs and "TEL AVIV DISTRICT" in districts:
        subs["Tel Aviv"] = dict(districts["TEL AVIV DISTRICT"], district="TEL AVIV DISTRICT")
    check(set(DISTRICTS) <= set(districts), f"israel_cbs: districts {sorted(districts)}")
    check(set(SUBDISTRICTS) <= set(subs), f"israel_cbs: sub-districts {sorted(subs)}")
    for d in DISTRICTS:
        kids = [v for v in subs.values() if v["district"] == d]
        if kids:
            made = sum(v["total"] for v in kids)
            check(abs(made - districts[d]["total"]) <= 1000 * ROUND * (len(kids) + 1),
                  f"israel_cbs: {d}'s sub-districts make {made:,.0f}, not "
                  f"{districts[d]['total']:,.0f}")
    total = table.get(("total", "TOTAL"))
    check(total is not None, "israel_cbs: no total row")
    made = sum(districts[d]["total"] for d in DISTRICTS)
    log(f"  districts make {made:,.0f}; the country {total['total']:,.0f}; "
        f"outside the six districts {total['total'] - made:,.0f}")
    source = [{"field": "population/ethnicity", "name": SOURCE, "url": URL, "year": YEAR,
               "license": LICENCE}]
    age_source = {"field": "median_age/sex_ratio", "name": SOURCE_AGES, "url": URL_AGES,
                  "year": YEAR, "license": LICENCE}
    religion_source = {"field": "religion", "name": SOURCE_RELIGION, "url": URL_RELIGION,
                       "year": YEAR, "license": LICENCE}

    def more(rec: dict[str, Any], age: dict[str, Any] | None, rel: dict[str, Any] | None
             ) -> dict[str, Any]:
        if age:
            rec.update(age)
            rec["sources"] = rec["sources"] + [age_source]
        if rel:
            rec.update(rel)
            rec["sources"] = rec["sources"] + [religion_source]
        return rec

    def gaps(why: str, *, displace: bool = False) -> dict[str, Any]:
        out = {f: gap(NOT_AVAILABLE, why)
               for f in ("population", "ethnicity", "median_age", "sex_ratio", "religion")}
        if displace:
            out["population"] = dict(out["population"], displaces_before=DISPLACES_BEFORE)
        out["language"] = gap(NOT_AVAILABLE, LANGUAGE_WHY)
        return out

    def jews_of(keys: list[tuple[str, str]]) -> float | None:
        """The units' Jews summed, or None where Table 2.15 was not read."""
        if not jews:
            return None
        missing = [k for k in keys if k not in jews]
        check(not missing, f"israel_cbs: Table 2.15 has no Jews for {missing}")
        return sum(jews[k] for k in keys)

    def fields(v: dict[str, float], what: str, keys: list[tuple[str, str]]) -> dict[str, Any]:
        population = measure(round(v["total"]), year=YEAR, source=SOURCE)
        population["note"] = (f"The CBS's estimate for 31 December 2023 for {what}, published "
                              f"in thousands to one decimal (the nearest hundred people).")
        counts, note = population_groups(v, jews_of(keys), what)
        return {
            "population": population,
            "ethnicity": shares(counts, total=v["total"]),
            "ethnicity_year": YEAR, "ethnicity_basis": "population group",
            "ethnicity_note": note,
            "language": gap(NOT_AVAILABLE, LANGUAGE_WHY),
            "sources": source + ([{"field": "ethnicity", "name": SOURCE_RELIGION,
                                   "url": URL_RELIGION, "year": YEAR, "license": LICENCE}]
                                 if jews else []),
        }

    out: list[dict[str, Any]] = []
    drawn1 = {u["name"]: u for u in admin1}
    for key_, label in DISTRICTS.items():
        unit = drawn1.get(label)
        check(unit is not None, f"israel_cbs: {label} is not drawn")
        if key_ == "JERUSALEM DISTRICT":
            out.append(record(f"ISR-CBS-{label}", label, level="admin1", parent=ISO3,
                              country=ISO3, match_by="shape_id", shape_id=unit["id"],
                              **gaps(JERUSALEM_WHY, displace=True)))
            continue
        if key_ == "NORTHERN DISTRICT":
            kids = [n for n in ("Zefat", "Kinneret", "Yizre'el", "Akko")]
            v = {g: sum(subs[n][g] for n in kids) for g in GROUPS + ("total",)}
            golan = subs["Golan"]["total"]
            check(abs(v["total"] + golan - districts[key_]["total"]) <= 1000 * ROUND * 6,
                  "israel_cbs: the Northern District is not its sub-districts")
            rec = record(f"ISR-CBS-{label}", label, level="admin1", parent=ISO3, country=ISO3,
                         match_by="shape_id", shape_id=unit["id"],
                         **fields(v, "the Zefat, Kinneret, Yizre'el and Akko sub-districts",
                                  [("subdistrict", n) for n in kids]))
            rec["population"]["note"] += (
                f" The sum of the district's sub-districts other than the Golan "
                f"({golan:,.0f} people), which the map draws in Syria's Quneitra governorate.")
            parts = [ages.get(("subdistrict", n)) for n in kids]
            age = None
            if all(parts):
                summed = {"groups": [(lo, hi, sum(p["groups"][i][2] for p in parts))
                                     for i, (lo, hi, _n) in enumerate(parts[0]["groups"])],
                          "total": sum(p["total"] for p in parts),
                          "females": sum(p["females"] for p in parts), "median": None}
                age = age_fields(summed, "the Zefat, Kinneret, Yizre'el and Akko "
                                         "sub-districts", ours=True)
            # The district's religion counts the Golan, whose smaller religions
            # the table does not give apart, so none is written here.
            rec["religion"] = gap(NOT_AVAILABLE, (
                "The CBS publishes the Northern District's religions with the Golan "
                "sub-district in them, and does not list the Golan's Christians and "
                "unclassified apart, so the religion of the district as the map draws it "
                "(without the Golan) is not published."))
            out.append(more(rec, age, None))
            continue
        rec = record(f"ISR-CBS-{label}", label, level="admin1", parent=ISO3,
                     country=ISO3, match_by="shape_id", shape_id=unit["id"],
                     **fields(districts[key_], f"the {key_.title()}", [("district", key_)]))
        age = ages.get(("district", key_))
        rel = religion.get(key_)
        out.append(more(rec, age_fields(age, f"the {key_.title()}") if age else None,
                        religion_fields(rel, f"the {key_.title()}") if rel else None))
    by_label: dict[str, list[dict[str, Any]]] = {}
    for unit in admin2:
        by_label.setdefault(unit["name"], []).append(unit)
    for name, label in list(SUBDISTRICTS.items()) + [(None, JERUSALEM_LABEL)]:
        found = by_label.get(label, [])
        check(len(found) == 1, f"israel_cbs: {len(found)} drawn units labelled {label!r}")
        unit = found[0]
        why = GOLAN_WHY if name == "Golan" else JERUSALEM_WHY if name is None else None
        if why:
            out.append(record(f"ISR-CBS-{label}", label, level="admin2", parent=ISO3,
                              country=ISO3, parent_name=parents.get(unit["parent"]),
                              match_by="shape_id", shape_id=unit["id"],
                              **gaps(why, displace=name is None)))
            continue
        rec = record(f"ISR-CBS-{label}", label, level="admin2", parent=ISO3, country=ISO3,
                     parent_name=parents.get(unit["parent"]), match_by="shape_id",
                     shape_id=unit["id"], aliases=[f"{name} sub-district"],
                     **fields(subs[name], f"the {name} sub-district", [("subdistrict", name)]))
        age = ages.get(("subdistrict", name))
        # Tel Aviv's one sub-district is the district, whose religions the
        # table gives in full; no other sub-district's are.
        rel = religion.get("TEL AVIV DISTRICT") if name == "Tel Aviv" else None
        if rel is None and religion:
            rec["religion"] = gap(NOT_AVAILABLE, SUB_RELIGION_WHY.format(name=name))
        out.append(more(rec, age_fields(age, f"the {name} sub-district") if age else None,
                        religion_fields(rel, "the Tel Aviv sub-district") if rel else None))
    left = sorted(set(by_label) - set(SUBDISTRICTS.values()) - {JERUSALEM_LABEL})
    check(not left, f"israel_cbs: drawn sub-districts with no CBS row: {left}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    table = read(workbook(URL))
    ages = read_ages(workbook(URL_AGES))
    religion_sheets = workbook(URL_RELIGION)
    religion = read_religion(religion_sheets)
    jews = read_jews(religion_sheets)
    check(bool(jews), "israel_cbs: Table 2.15 gave no Jews by district")
    log(f"  Table 2.15: Jews of {sum(1 for k, _n in jews if k == 'district')} districts and "
        f"{sum(1 for k, _n in jews if k == 'subdistrict')} sub-districts")
    admin1, admin2 = units(ISO3, "admin1"), units(ISO3, "admin2")
    rows = build(table, admin1, admin2, {u["id"]: u["name"] for u in admin1}, ages, religion,
                 jews)
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
