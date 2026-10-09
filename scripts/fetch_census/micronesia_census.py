#!/usr/bin/env python3
"""Federated States of Micronesia: the 2023 and 2010 censuses by state and municipality.

The FSM Statistics Division publishes each census as workbooks on
``stats.gov.fm``:

* **2023 Population and Housing Census, National Basic Tables.** Table B1 is
  age and sex by state, with each state's median age; Table B6 religion by
  state. Its six population tables carry no ethnicity and no language.
* **2023 state basic tables** for Yap, Pohnpei and Kosrae: Table B1 by
  municipality, and for Yap and Pohnpei Table B6 (religion). The office's
  Chuuk page offers no 2023 tables, only the 2010 tabulation.
* **2010 Census, National Basic Tables.** Table B08 (ethnicity) and the
  language mainly spoken at home (Table B10A, persons aged three and over) by
  state.
* **2010 state basic tabulations**, by municipality: Table B01 (age and sex,
  with the median) for every state; ethnicity (B08), religion (B09) and
  language (B10A) for Yap and Pohnpei; religion (Table 22) and language
  (Table 26A) for Kosrae, which has no ethnicity table; nothing but B01 and
  housing for Chuuk.

**What each unit takes.** A state takes its 2023 people, median age, sex
ratio and religion, and its 2010 ethnicity and language. A Yap or Pohnpei
municipality takes the same; a Kosrae municipality its 2023 people, age and
sex and its 2010 religion and language; a Chuuk municipality its 2010 people,
median age and sex ratio, which is everything published for it. Every figure
is the office's own: the medians are the tables' "Median" rows.

**Suppression.** The 2023 tables print ``*`` for a count small enough to
identify someone. A unit's religion shares are of its whole population, so
the suppressed cells are left out rather than guessed and the shares add up to
less than 100; the note says how much.

**What the map draws.** The four states; and 31 of the census's 75
municipalities: ten of Yap's 20, ten of Chuuk's 40, seven of Pohnpei's 11 and
Kosrae's four. The census spells one of them Piherarh, the boundary file
Piherech: the islet of Namonuito Atoll the other spellings call Pisaras.

**Checks**, each refusing the run: the municipalities listed here are all in
every table and add up to their state (within the few people the 2023
tables' own rows disagree by), so none goes unread; the states add up to the
country; every
unit's men and women add up to its total; a published median lies within two
years of the one its five-year groups give; ethnicity's single groups and its
mixed answers add up to the unit's people, and religion's and language's
categories to their tables' totals.

Usage:
    python -m scripts.fetch_census.micronesia_census
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, write_json
from .binding import fold
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, number, population, sex_ratio,
    shares_of, summarise, unit_record, workbook,
)

OUT = "micronesia_census.json"
OFFICE = "FSM Statistics Division, Federated States of Micronesia"
LICENCE = "None stated -- FSM Statistics Division publication, cited as such"
SITE = "https://stats.gov.fm/download/"
NATIONAL_2023 = (SITE + "18/population-statistics/2210/"
                 "fsm-basic-tables-2023-population-housing-census.xlsx")
STATE_2023 = {
    "Yap": SITE + "56/yap/2212/yap-basic-tables-2023-population-housing-census.xlsx",
    "Pohnpei": SITE + "54/pohnpei/2216/pni-basic-tables-2023-population-housing-census.xlsx",
    "Kosrae": SITE + "55/kosrae/2217/ksa-basic-tables-2023-population-housing-census.xlsx",
}
NATIONAL_2010 = (SITE + "18/population-statistics/600/"
                 "fsm-basic-tables-2010-population-housing-census.xlsx")
STATE_2010 = {
    "Pohnpei": SITE + "64/states/596/"
               "pohnpei-basic-tabulation-2010-census-of-population-and-housing.xlsx",
    "Kosrae": SITE + "64/states/597/"
              "kosrae-basic-tabulation-2010-census-of-population-and-housing.xlsx",
    "Yap": SITE + "64/states/598/yap-basic-tabulation-2010-census-of-population-and-housing.xlsx",
    "Chuuk": SITE + "64/states/599/"
             "chuuk-basic-tabulation-2010-census-of-population-and-housing.xlsx",
}
# The 2010 workbooks as the office's former site served them, in the Internet
# Archive, for when stats.gov.fm will not answer: the same publication.
_OLD = "https://www.fsmstatistics.fm/wp-content/uploads/2019/02/"
_WAYBACK = "http://web.archive.org/web/{}id_/" + _OLD + "{}"
ARCHIVED = {
    NATIONAL_2010: _WAYBACK.format(20201115081345, "2010-Basic-Tables.xlsx"),
    STATE_2010["Yap"]: _WAYBACK.format(20201115023645, "PopHseY_details.xlsx"),
    STATE_2010["Chuuk"]: _WAYBACK.format(20201115023726, "PopHseC_details.xlsx"),
    STATE_2010["Pohnpei"]: _WAYBACK.format(20201115023902, "PopHseP_details.xlsx"),
    STATE_2010["Kosrae"]: _WAYBACK.format(20201115023929, "PopHseK_details.xlsx"),
}
T2023 = f"{OFFICE}, 2023 FSM Population and Housing Census"
T2010 = f"{OFFICE}, 2010 FSM Census of Population and Housing"

STATES = ("Yap", "Chuuk", "Pohnpei", "Kosrae")
FSM_2023 = 75_817
FSM_2010 = 102_843
# Every municipality each state's tables carry, as they spell it. The tables
# also print their regions' subtotals (Yap Proper, Chuuk Lagoon, Faichuk,
# the Mortlocks and so on), which are read past.
MUNICIPALITIES = {
    "Yap": ("Rumung", "Maap", "Gagil", "Tomil", "Fanif", "Weloy", "Dalipebinaw", "Rull",
            "Kanifay", "Gilman", "Ulithi", "Fais", "Ngulu", "Woleai", "Eauripik", "Ifalik",
            "Faraulep", "Elato", "Lamotrek", "Satawal"),
    "Chuuk": ("Weno", "Piis-Penau", "Fono", "Tonoas", "Fefen", "Siis", "Uman", "Parem", "Eot",
              "Udot", "Romanum", "Fanapanges", "Wonei", "Paata", "Tol", "Polle", "Nema", "Losap",
              "Piis-Emwar", "Namoluk", "Ettal", "Lekinioch", "Oneop", "Satowan", "Kuttu", "Moch",
              "Ta", "Houk", "Polowat", "Pollap", "Tamatam", "Makur", "Onoun", "Onou", "Unanu",
              "Piherarh", "Nomwin", "Fananu", "Ruo", "Murillo"),
    "Pohnpei": ("Madolenihmw", "U", "Nett", "Sokehs", "Kitti", "Kolonia", "Mwoakilloa",
                "Pingelap", "Sapwuahfik", "Nukuoro", "Kapingamarangi"),
    "Kosrae": ("Lelu", "Malem", "Utwe", "Tafunsak"),
}
# The census's spelling -> the boundary file's.
ALIASES = {"Piherarh": "Piherech"}
# The 2023 tables' rows disagree by a person or two (Sokehs's and Pingelap's
# totals are one more than their men and women): no more than this is let by.
SLACK = 3

ETHNIC = {
    "yapese": "Yapese", "ulithian": "Ulithian", "woleaian": "Woleaian",
    "satawalese": "Satawalese", "chuukese": "Chuukese", "mortlockese": "Mortlockese",
    "pohnpeian": "Pohnpeian", "sapwuahfikese": "Sapwuahfikese",
    "pingelapese": "Pingelapese", "mwoakilese": "Mwoakilese", "nukuoroan": "Nukuoroan",
    "kapingamarangian": "Kapingamarangian", "kosraean": "Kosraean", "palauan": "Palauan",
    "marshallese": "Marshallese", "otherpacificislander": "Other Pacific Islander",
    "usamerican": "U.S. American", "australiannewzealander": "Australian / New Zealander",
    "othercaucasianwhite": "Other Caucasian / White", "filipino": "Filipino",
    "chinesetaiwanese": "Chinese / Taiwanese", "japanese": "Japanese",
    "otherasian": "Other Asian", "other": "Other ethnicity", "othersingle": "Other ethnicity",
}
MIXED_MAIN = {"yapese": "Yapese and another ethnicity",
              "chuukese": "Chuukese and another ethnicity",
              "pohnpeian": "Pohnpeian and another ethnicity",
              "kosraean": "Kosraean and another ethnicity",
              "other": "Other mixed ethnicity"}
MIXED_LOCAL = {"yapese": "Two or more Yap State ethnicities",
               "chuukese": "Two or more Chuuk State ethnicities",
               "pohnpeian": "Two or more Pohnpei State ethnicities"}
RELIGION_2010 = {
    "romancatholic": "Roman Catholic", "congregationprotestant": "Congregational / Protestant",
    "mormon": "Church of Jesus Christ of Latter-day Saints", "baptist": "Baptist",
    "sevendayadventistsda": "Seventh-day Adventist", "assemblyofgod": "Assembly of God",
    "apostolic": "Apostolic", "pentecostal": "Pentecostal",
    "jehovahwitnesses": "Jehovah's Witnesses", "otherreligions": "Other religion",
    "noreligion": "No religion", "refused": "Not stated",
}
RELIGION_2023 = {
    "romancatholic": "Roman Catholic", "congregationprotestant": "Congregational / Protestant",
    "assemblyofgod": "Assembly of God", "pentecostal": "Pentecostal", "apostolic": "Apostolic",
    "baptist": "Baptist", "sda": "Seventh-day Adventist",
    "mormon": "Church of Jesus Christ of Latter-day Saints",
    "jehovahswitness": "Jehovah's Witnesses", "otherreligion": "Other religion",
    "noreligionrefused": "No religion/Refused",
}
LANGUAGE = {
    "english": "English", "yapese": "Yapese",
    "yapeseouterislandlanguages": "Yap Outer Island languages", "chuukese": "Chuukese",
    "pohnpeian": "Pohnpeian", "sapwuahfikese": "Sapwuahfikese", "pingelapese": "Pingelapese",
    "mwoakilese": "Mwoakilese", "nukuoroankapingamarangian": "Nukuoro and Kapingamarangi",
    "kosraean": "Kosraean", "otherpacificislandlanguages": "Other Pacific Island languages",
    "filipino": "Filipino", "chinesetaiwanese": "Chinese", "japanese": "Japanese",
    "otherlanguages": "Other languages",
}


# -- reading ---------------------------------------------------------------

def value(cell: Any) -> float | None:
    """A count, or None for a blank, a dash or a suppressed ``*``."""
    return number(cell)


def flat_rows(rows: list[list[Any]], units: tuple[str, ...]) -> list[tuple[int, str, dict]]:
    """Every labelled row as (row number, label, {unit: value}).

    A row naming two or more of ``units`` is a header and sets which column
    holds which unit until the next header; the label is the row's first
    cell. A workbook that sets its municipalities in two blocks side by side
    (Yap's and Chuuk's) repeats the label in each block, so the first cell
    labels both. Columns the header does not name -- "Total", a region's
    subtotal -- are read past; a municipality missing from the list would be
    too, which is why every state's listed municipalities must add up to the
    state (``add_up``).
    """
    known = {fold(u): u for u in units}
    out: list[tuple[int, str, dict]] = []
    columns: dict[int, str] = {}
    for n, row in enumerate(rows, start=1):
        cells = list(row)
        heads = {i: known[fold(c)] for i, c in enumerate(cells)
                 if isinstance(c, str) and fold(c) in known}
        if len(heads) >= 2:
            columns = heads
            continue
        label = cells[0] if cells else None
        if not isinstance(label, str) or not label.strip() or not columns:
            continue
        out.append((n, label.strip(), {u: value(cells[i]) if i < len(cells) else None
                                       for i, u in columns.items()}))
    return out


def ranges(rows: list[list[Any]], title: str) -> list[tuple[int, int]]:
    """(first, last) row numbers of every table whose title matches ``title``."""
    starts = [n for n, row in enumerate(rows, start=1)
              if row and isinstance(row[0], str) and re.match(title, row[0].strip())]
    out = []
    for start in starts:
        end = next((n for n in range(start + 1, len(rows) + 1)
                    if rows[n - 1] and isinstance(rows[n - 1][0], str)
                    and rows[n - 1][0].strip().startswith("Table ")), len(rows) + 1)
        out.append((start, end - 1))
    check(bool(out), f"micronesia_census: no table titled {title!r}")
    return out


AGE = (re.compile(r"less than (\d+)"), re.compile(r"(\d+)\s*(?:to|-|–)\s*(\d+)"),
       re.compile(r"(\d+)\s*\+"))


def age_group(label: str) -> tuple[int, int | None] | None:
    text = label.lower()
    if m := AGE[0].search(text):
        return 0, int(m.group(1)) - 1
    if m := AGE[1].search(text):
        return int(m.group(1)), int(m.group(2))
    if m := AGE[2].search(text):
        return int(m.group(1)), None
    return None


def age_sex(rows: list[list[Any]], units: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """{unit: total, male, female, median, groups} from Table B1/B01.

    2023 sets its sexes off by "BOTH GENDER" / "MALE" / "FEMALE" rows, each
    followed by a "Total" row; 2010 prints the men's and women's totals on
    their "Male" and "Female" rows. The median row is "Median" or "Median age".
    """
    flat = flat_rows(rows, units)
    out: dict[str, dict[str, Any]] = {}
    for first, last in ranges(rows, r"Table B0?1\."):
        sex = "both"
        # Chuuk's 2010 table adds a "75+" row under each median, the sum of
        # the three groups above it: groups are read only before the median.
        closed = False
        for n, label, values in flat:
            if not first <= n <= last:
                continue
            key = fold(label)
            if key in ("bothgender", "bothsexes", "bothgenders"):
                sex = "both"
                continue
            if key in ("male", "males", "female", "females"):
                sex = "male" if key.startswith("male") else "female"
                if any(v is not None for v in values.values()):
                    for unit, v in values.items():
                        out.setdefault(unit, {}).setdefault(sex, v)
                continue
            if key == "total":
                for unit, v in values.items():
                    out.setdefault(unit, {}).setdefault(sex if sex != "both" else "total", v)
            elif key.startswith("median"):
                for unit, v in values.items():
                    out.setdefault(unit, {}).setdefault(f"median_{sex}", v)
                closed = closed or sex == "both"
            elif sex == "both" and not closed and (group := age_group(label)):
                for unit, v in values.items():
                    out.setdefault(unit, {}).setdefault("groups", []).append(
                        (group[0], group[1], v))
    return out


def religion_2023(rows: list[list[Any]], units: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """{unit: {"total", "counts" (None where suppressed)}} from Table B6, both sexes."""
    flat = flat_rows(rows, units)
    out: dict[str, dict[str, Any]] = {}
    for first, last in ranges(rows, r"Table B6\."):
        sex = "both"
        for n, label, values in flat:
            if not first <= n <= last:
                continue
            key = fold(label)
            if key in ("male", "female"):
                sex = key
            if sex != "both":
                continue
            if key == "total":
                for unit, v in values.items():
                    out.setdefault(unit, {"counts": {}})["total"] = v
            elif key in RELIGION_2023:
                for unit, v in values.items():
                    out.setdefault(unit, {"counts": {}})["counts"][RELIGION_2023[key]] = v
            elif any(v is not None for v in values.values()):
                raise SystemExit(f"micronesia_census: Table B6 row {n} is {label!r}")
    for unit, got in out.items():
        lacking = set(RELIGION_2023.values()) - set(got["counts"])
        check(not lacking, f"micronesia_census: Table B6 lacks {lacking} for {unit}")
    return out


def section(flat: list[tuple[int, str, dict]], start: str, labels: dict[str, str],
            what: str) -> dict[str, dict[str, Any]]:
    """{unit: {"total", "counts"}}: the row whose label begins ``start`` gives
    the totals (or, if it has none, the next row does) and the rows after it
    that ``labels`` knows the categories, up to the first it does not."""
    at = next((i for i, (_, label, _) in enumerate(flat) if fold(label).startswith(start)), None)
    check(at is not None, f"micronesia_census: no {what} rows")
    totals = flat[at][2]
    i = at + 1
    if all(v is None for v in totals.values()):
        totals = flat[i][2]
        i += 1
    out = {u: {"total": t, "counts": {}} for u, t in totals.items()}
    while i < len(flat) and fold(flat[i][1]) in labels:
        for unit, v in flat[i][2].items():
            label = labels[fold(flat[i][1])]
            out[unit]["counts"][label] = out[unit]["counts"].get(label, 0) + (v or 0)
        i += 1
    for unit, got in out.items():
        check(len(got["counts"]) >= 5, f"micronesia_census: {what} for {unit} has "
                                       f"{len(got['counts'])} categories")
        check(got["total"] is not None and sum(got["counts"].values()) == got["total"],
              f"micronesia_census: {unit}'s {what} adds up to {sum(got['counts'].values())}, "
              f"not {got['total']}")
    return out


def ethnicity_2010(rows: list[list[Any]], units: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """{unit: {group: count}} from Table B08: single groups and mixed answers.

    The single groups are the table's leaves: under "Caucasian / White" and
    "Asian" it is their indented parts that are read. A mixed answer is
    counted once, under the main ethnicity it was given with ("Yapese as main
    ethnicity and") or as two of one state's peoples ("Multiple Yapese
    localities"); the rows beneath each, which split it by the other group,
    are read past. The subtotal rows are worded differently from workbook to
    workbook and are not used: the check is against the unit's people.
    """
    flat = flat_rows(rows, units)
    (first, last), *_ = ranges(rows, r"Table B08\.")
    out: dict[str, dict[str, float]] = {u: {} for u in units}
    mixed = False
    for n, label, values in flat:
        if not first <= n <= last:
            continue
        key = fold(label)
        if key.startswith("multipleethnic"):
            mixed = True
            continue
        group = None
        if not mixed and key in ETHNIC:
            group = ETHNIC[key]
        elif mixed and (m := re.match(r"(\w+) as main ethnic", label.strip(), re.I)):
            group = MIXED_MAIN.get(m.group(1).lower())
            check(group is not None, f"micronesia_census: B08 row {n} {label!r}")
        elif mixed and (m := re.match(r"multiple (\w+) local", label.strip(), re.I)):
            group = MIXED_LOCAL.get(m.group(1).lower())
            check(group is not None, f"micronesia_census: B08 row {n} {label!r}")
        if group is None:
            continue
        for unit, v in values.items():
            out[unit][group] = out[unit].get(group, 0) + (v or 0)
    return out


# -- building ----------------------------------------------------------------

def check_age(unit: str, got: dict[str, Any], year: int) -> None:
    total, male, female = got.get("total"), got.get("male"), got.get("female")
    check(total is not None and total > 0, f"micronesia_census: {unit} has no {year} total")
    if male is not None and female is not None:
        check(abs(male + female - total) <= 2,
              f"micronesia_census: {unit}'s {year} men and women make {male + female}, not {total}")
    median = got.get("median_both")
    check(median is not None and 10 <= median <= 60,
          f"micronesia_census: {unit}'s {year} median is {median}")
    groups = [(lo, hi, n) for lo, hi, n in got.get("groups", []) if n is not None]
    if len(groups) == len(got.get("groups", [])) and groups:
        check(abs(sum(n for _, _, n in groups) - total) <= 2,
              f"micronesia_census: {unit}'s {year} age groups add up to "
              f"{sum(n for _, _, n in groups)}, not {total}")
        computed = median_from_groups(sorted(groups, key=lambda g: g[0]))
        check(computed is not None and abs(computed - median) <= 2.0,
              f"micronesia_census: {unit}'s {year} median is printed {median}, its five-year "
              f"groups give {computed}")


def add_up(state: str, got: dict[str, dict[str, Any]], expected: float, year: int) -> None:
    names = set(MUNICIPALITIES[state])
    check(names <= set(got),
          f"micronesia_census: the {year} {state} tables lack {sorted(names - set(got))}")
    total = sum(got[m]["total"] for m in names)
    check(abs(total - expected) <= SLACK,
          f"micronesia_census: {state}'s {year} municipalities add up to {total:,}, not "
          f"{expected:,}")
    if total != expected:
        log(f"  {state} {year}: municipalities add up to {total:,}, the state's row "
            f"{expected:,}")


def religion_note(year: int, total: float, counts: dict[str, float | None],
                  where: str) -> tuple[list[dict[str, Any]], str]:
    shown = {k: v for k, v in counts.items() if v}
    hidden = [k for k, v in counts.items() if v is None]
    held = total - sum(shown.values())
    check(held >= -SLACK, f"micronesia_census: {where}'s religion exceeds its people by {-held}")
    if not hidden:
        check(abs(held) <= SLACK, f"micronesia_census: {where}'s religion misses {held}")
    note = (f"Religion, {year} census (Table B6), as shares of all {int(total):,} people "
            f"counted here.")
    if hidden and held > 0:
        note += (f" The office suppresses small counts (printed *): {', '.join(hidden)}; the "
                 f"{int(held):,} people in those cells ({100 * held / total:.1f}%) are left out, "
                 f"so the shares shown add up to less than 100.")
    return shares_of(shown, total), note


def composition_2010(counts: dict[str, float], total: float, field: str) -> list[dict[str, Any]]:
    check(abs(sum(counts.values()) - total) <= 0.5,
          f"micronesia_census: {field} adds up to {sum(counts.values())}, not {total}")
    return shares_of(counts, total)


ETHNIC_NOTE = ("Ethnicity, 2010 census (Table B08): each person's single ethnic group, or, for "
               "the {mixed:,} people who gave more than one, the main one they named with "
               "another (\"Pohnpeian and another ethnicity\") or two of one state's peoples "
               "(\"Two or more Pohnpei State ethnicities\"). The 2023 census's published tables "
               "carry no ethnicity; 2010 is the latest count of it.")
LANGUAGE_NOTE = ("Language mainly spoken at home, persons aged three and over, 2010 census "
                 "(Table B10A): {total:,} people here. The 2023 census's published tables carry "
                 "no language; 2010 is the latest count of it.")
RELIGION_2010_NOTE = ("Religion, 2010 census (Table {table}), as shares of all {total:,} people "
                      "here; 'Not stated' is the census's 'Refused'. The 2023 census publishes no "
                      "religion by {where} municipality.")


def fields_state(state: str, n23: dict, r23: dict, eth: dict, lang: dict,
                 people10: dict) -> dict[str, Any]:
    got = n23[state]
    religion, religion_note_text = religion_note(2023, got["total"], r23[state]["counts"], state)
    mixed = sum(v for k, v in eth[state].items() if k in MIXED_MAIN.values()
                or k in MIXED_LOCAL.values())
    return {
        "population": population(got["total"], 2023, f"{T2023}, National Basic Tables (Table B1)"),
        "median_age": measure(got["median_both"], unit="years", year=2023,
                              source=f"{T2023}, National Basic Tables (Table B1)"),
        "median_age_note": "Median age at the 2023 census, as Table B1 prints it.",
        "sex_ratio": measure(sex_ratio(got["male"], got["female"]), unit="males_per_100_females",
                             year=2023, source=f"{T2023}, National Basic Tables (Table B1)"),
        "sex_ratio_note": (f"Males per 100 females, 2023 census (Table B1): {int(got['male']):,} "
                           f"men, {int(got['female']):,} women."),
        "religion": religion, "religion_year": 2023, "religion_note": religion_note_text,
        "ethnicity": composition_2010(eth[state], people10[state], f"{state}'s ethnicity"),
        "ethnicity_year": 2010,
        "ethnicity_note": ETHNIC_NOTE.format(mixed=int(mixed)),
        "language": shares_of(lang[state]["counts"], lang[state]["total"]),
        "language_year": 2010,
        "language_note": LANGUAGE_NOTE.format(total=int(lang[state]["total"])),
    }


def fields_municipality(state: str, name: str, ages: dict, year: int, source: str,
                        religion: dict | None, ethnicity: dict | None,
                        language: dict | None, people10: float | None) -> dict[str, Any]:
    got = ages[name]
    table = "B1" if year == 2023 else "B01"
    fields: dict[str, Any] = {
        "population": population(got["total"], year, f"{source} (Table {table})"),
        "median_age": measure(got["median_both"], unit="years", year=year,
                              source=f"{source} (Table {table})"),
        "median_age_note": f"Median age at the {year} census, as the state's Table {table} "
                           f"prints it.",
    }
    if got.get("male") is not None and got.get("female") is not None:
        fields["sex_ratio"] = measure(sex_ratio(got["male"], got["female"]),
                                      unit="males_per_100_females", year=year,
                                      source=f"{source} (Table {table})")
        fields["sex_ratio_note"] = (f"Males per 100 females, {year} census: "
                                    f"{int(got['male']):,} men, {int(got['female']):,} women.")
    if religion is not None:
        fields.update(religion)
    if ethnicity is not None:
        mixed = sum(v for k, v in ethnicity.items() if k in MIXED_MAIN.values()
                    or k in MIXED_LOCAL.values())
        fields["ethnicity"] = composition_2010(ethnicity, people10, f"{name}'s ethnicity")
        fields["ethnicity_year"] = 2010
        fields["ethnicity_note"] = ETHNIC_NOTE.format(mixed=int(mixed))
    if language is not None:
        fields["language"] = shares_of(language["counts"], language["total"])
        fields["language_year"] = 2010
        fields["language_note"] = LANGUAGE_NOTE.format(total=int(language["total"]))
    return fields


CHUUK_GAP = ("The 2010 census's Chuuk State tabulation publishes age and sex (Table B01) and "
             "housing by municipality and nothing else; the 2023 census has published no Chuuk "
             "State tables (the office's Chuuk page offers only the 2010 tabulation), and its "
             "national tables stop at the state. Chuuk's {what} is counted by state only.")
KOSRAE_ETHNIC_GAP = ("The 2010 census's Kosrae State tabulation has no ethnicity table by "
                     "municipality (its tables go from citizenship to marital status and "
                     "religion), and the 2023 census's published tables carry no ethnicity. "
                     "Kosrae's ethnicity is counted by state only (2010 national Table B08).")


def read_workbook(url: str):
    try:
        return workbook(url)
    except SystemExit as err:
        if url not in ARCHIVED:
            raise
        log(f"  {url}: {err}; reading the Internet Archive's copy")
        return workbook(ARCHIVED[url])


def sheet_rows(book) -> list[list[Any]]:
    """The rows of the workbook's sheet that holds its population tables.

    A contents sheet lists Table B1's title too, so of the sheets that name
    it the longest is the one with the tables.
    """
    found = []
    for sheet in book.worksheets:
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        if any(r and isinstance(r[0], str) and re.match(r"Table B0?1\.", r[0].strip())
               for r in rows):
            found.append(rows)
    check(bool(found), "micronesia_census: no sheet holds Table B1")
    return max(found, key=len)


def municipal_rows(admin2: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """{state-municipality: (census name, state)} for the municipalities the map draws.

    The rest of the census's 75 have no polygon; ``bind_level`` then refuses
    the run if any drawn polygon is left without its municipality.
    """
    drawn = {fold(u["name"]) for u in admin2}
    return {f"{state}-{name}": (name, state) for state in STATES
            for name in MUNICIPALITIES[state] if fold(ALIASES.get(name, name)) in drawn}


def build(n23: dict, r23: dict, eth10: dict, lang10: dict, people10: dict,
          municipal: dict[str, dict[str, Any]], admin1: list[dict], admin2: list[dict]
          ) -> list[dict[str, Any]]:
    records = []
    sources_state = [
        {"field": "population/median_age/sex_ratio/religion", "name": f"{T2023}, National Basic "
         "Tables (Tables B1, B6)", "url": NATIONAL_2023, "year": 2023, "license": LICENCE},
        {"field": "ethnicity/language", "name": f"{T2010}, National Basic Tables (Tables B08, "
         "B10A)", "url": NATIONAL_2010, "year": 2010, "license": LICENCE},
    ]
    bound = bind_level({s: (s, "") for s in STATES}, admin1, {})
    for state, unit in bound.items():
        records.append(unit_record("FSM", state, unit["name"], unit, "admin1", None,
                                   sources_state,
                                   **fields_state(state, n23, r23, eth10, lang10, people10)))
    parents = {u["id"]: u["name"] for u in admin1}
    placed = bind_level(municipal_rows(admin2), admin2, parents, ALIASES)
    for key, unit in placed.items():
        state, name = key.split("-", 1)
        m = municipal[state]
        records.append(unit_record("FSM", key, unit["name"], unit, "admin2", state, m["sources"],
                                   **m["fields"][name]))
    return records


def municipal_fields(state: str, n23: dict, books23: dict, books10: dict
                     ) -> dict[str, Any]:
    """Every drawn-or-not municipality's fields, and the state's sources."""
    names = MUNICIPALITIES[state]
    ages10 = age_sex(books10[state], names)
    add_up(state, ages10, {"Yap": 11_377, "Chuuk": 48_654, "Pohnpei": 36_196,
                           "Kosrae": 6_616}[state], 2010)
    people10 = {n: ages10[n]["total"] for n in names}
    out: dict[str, Any] = {"fields": {}, "sources": []}
    flat10 = flat_rows(books10[state], names)
    if state == "Chuuk":
        for name in names:
            check_age(name, ages10[name], 2010)
            fields = fields_municipality(state, name, ages10, 2010, f"{T2010}, Chuuk State "
                                         "basic tabulation", None, None, None, None)
            for field in ("religion", "language", "ethnicity"):
                fields[field] = gap(NOT_AVAILABLE, CHUUK_GAP.format(what=field))
            out["fields"][name] = fields
        out["sources"] = [{"field": "population/median_age/sex_ratio",
                           "name": f"{T2010}, Chuuk State basic tabulation (Table B01)",
                           "url": STATE_2010[state], "year": 2010, "license": LICENCE}]
        return out
    ages23 = age_sex(books23[state], names)
    add_up(state, ages23, n23[state]["total"], 2023)
    language = section(flat10, "languagemainlyspoken", LANGUAGE, f"{state} 2010 language")
    if state in ("Yap", "Pohnpei"):
        relig23 = religion_2023(books23[state], names)
        ethnic = ethnicity_2010(books10[state], names)
        relig10 = None
    else:
        relig23 = None
        ethnic = None
        relig10 = section(flat10, "religion", RELIGION_2010, f"{state} 2010 religion")
    for name in names:
        check_age(name, ages23[name], 2023)
        religion: dict[str, Any] = {}
        if relig23 is not None:
            shares, note = religion_note(2023, ages23[name]["total"], relig23[name]["counts"], name)
            check(relig23[name]["total"] is None
                  or abs(relig23[name]["total"] - ages23[name]["total"]) <= SLACK,
                  f"micronesia_census: {name}'s Table B6 counts {relig23[name]['total']}, "
                  f"Table B1 {ages23[name]['total']}")
            religion = {"religion": shares, "religion_year": 2023, "religion_note": note}
        else:
            got = relig10[name]
            check(got["total"] == people10[name],
                  f"micronesia_census: {name}'s 2010 religion counts {got['total']}, "
                  f"Table B01 {people10[name]}")
            religion = {"religion": composition_2010(got["counts"], got["total"],
                                                     f"{name}'s religion"),
                        "religion_year": 2010,
                        "religion_note": RELIGION_2010_NOTE.format(
                            table="22", total=int(got["total"]), where="Kosrae")}
        fields = fields_municipality(state, name, ages23, 2023, f"{T2023}, {state} State basic "
                                     "tables", religion, ethnic[name] if ethnic else None,
                                     language[name], people10[name])
        if ethnic is None:
            fields["ethnicity"] = gap(NOT_AVAILABLE, KOSRAE_ETHNIC_GAP)
        out["fields"][name] = fields
    out["sources"] = [
        {"field": "population/median_age/sex_ratio" + ("/religion" if relig23 else ""),
         "name": f"{T2023}, {state} State basic tables (Table B1" + (", B6)" if relig23 else ")"),
         "url": STATE_2023[state], "year": 2023, "license": LICENCE},
        {"field": "language" + ("/ethnicity" if ethnic else "/religion"),
         "name": f"{T2010}, {state} State basic tabulation", "url": STATE_2010[state],
         "year": 2010, "license": LICENCE},
    ]
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("micronesia_census: 2023 and 2010 census workbooks")
    national23 = sheet_rows(read_workbook(NATIONAL_2023))
    n23 = age_sex(national23, STATES)
    check(abs(sum(n23[s]["total"] for s in STATES) - FSM_2023) <= SLACK,
          "micronesia_census: the 2023 states do not add up to the country")
    for state in STATES:
        check_age(state, n23[state], 2023)
    r23 = religion_2023(national23, STATES)
    national10 = sheet_rows(read_workbook(NATIONAL_2010))
    people10 = {s: v["total"] for s, v in age_sex(national10, STATES).items()}
    check(sum(people10[s] for s in STATES) == FSM_2010,
          "micronesia_census: the 2010 states do not add up to the country")
    eth10 = ethnicity_2010(national10, STATES)
    lang10 = section(flat_rows(national10, STATES), "languagemainlyspoken", LANGUAGE,
                     "2010 language by state")
    books23 = {s: sheet_rows(read_workbook(u)) for s, u in STATE_2023.items()}
    books10 = {s: sheet_rows(read_workbook(u)) for s, u in STATE_2010.items()}
    municipal = {s: municipal_fields(s, n23, books23, books10) for s in STATES}
    records = build(n23, r23, eth10, lang10, people10, municipal,
                    load_units("FSM", "admin1"), load_units("FSM", "admin2"))
    log("  " + summarise(records))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
