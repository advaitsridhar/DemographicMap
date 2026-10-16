#!/usr/bin/env python3
"""Abkhazia: its de facto authorities' count for 1 January 2026 and their 2011 census.

Georgia's 2014 census and Geostat's estimates cover the territory under the
government's control (georgia), so the only counts of Abkhazia are those of
its de facto authorities, whose independence Georgia and most states do not
recognise: the census of February 2011, and the estimate of the population
present (наличное население) that their statistics committee makes for the
start of each year from it -- the census count with each year's births and
arrivals added and deaths and departures taken away. The State Committee of
the Republic of Abkhazia on Statistics (Государственный комитет Республики
Абхазия по статистике, cgsra.org) prints both in its yearbook, «Абхазский
статистический ежегодник – 2025» (Sukhum, 2026), a PDF. This reads:

* table 1.11 -- the population on 1 January 2026 by district and sex, for the
  population and the sex ratio; its total must be table 1.1's for 2026, and
  every row's men and women must make it;
* table 1.2 -- the 2011 census's population by five-year age group, to 70 and
  over, for the median age, interpolated within the group holding the middle
  person; the groups must make the census's total;
* table 1.12 -- the 2011 census's nationality by district, for ethnicity. Its
  column headings are printed sideways and come out of the PDF as letters, so
  the columns are told apart by their totals, which must be table 1.7's 2011
  count of each district, and every row's districts must make its total.

Two more are read only to check what they are, because the yearbook also
prints ages and nationality for 1 January 2026, which would otherwise be the
newer figures. They are not newer counts: table 1.6 prints the 2011 census's
share of every age group, to the decimal, against the 2026 total, and table
1.16 keeps each district's 2011 share of every nationality to within a fifth
of a percentage point. The run stops if either stops being so: a table that
has become a new count should then be read instead.

**Binding.** The first-level polygon is all of Abkhazia, and takes the
republic's rows. Its six second-level polygons are drawn as Georgia's
municipalities, while the authorities count by districts redrawn since the
war, and only two of the six are one of their districts: every settlement
that Wikidata places in the Gagra and Gudauta districts lies inside the
polygon of that name, but for one village on the line itself (Amzhikukhua,
10 m from it by GeoNames' point). The other four are written as gaps that say
why (``REFUSED``):

* Sokhumi and Gulripshi -- the authorities count the city of Sukhum apart
  from both districts, and the line drawn between the two polygons runs
  through the east of the city: Abkhazian State University lies 1.7 km inside
  Gulripshi's polygon, and several of Gulripsh district's villages lie in
  Ochamchire's.
* Ochamchire and Gali -- the districts as drawn before 1995, when the
  authorities formed Tkvarcheli district from parts of both and counted
  others of Gal's villages in Ochamchira district; Gal's villages along the
  Enguri (Otobaia, 2 km in) lie in the polygon drawn as Zugdidi.

The yearbook publishes no religion and no language, and ages for the
republic only; those fields are gaps that say so.

Usage:
    python -m scripts.fetch_census.abkhazia_census
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .east_asia_common import drawn, grouped_median, sex_ratio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, laid_out  # noqa: E402

OUT = "abkhazia_census.json"
URL = "https://cgsra.org/media/files/25.pdf"
YEAR = 2026               # the estimate's 1 January
CENSUS = 2011
SOURCE = ("State Committee of the Republic of Abkhazia on Statistics (the statistics office of "
          "Abkhazia's de facto authorities), «Абхазский статистический ежегодник – 2025» "
          "(Abkhaz statistical yearbook 2025, 2026), table {table}")
LICENCE = "Published by the State Committee of the Republic of Abkhazia on Statistics; terms of reuse not stated"

WHOLE = "Все население"
# The districts as the tables name them, in the order the 2011 nationality
# table's columns follow (told apart by their totals all the same).
DISTRICTS = {
    "г. Сухум": "the city of Sukhum",
    "Гагрский район": "Gagra district",
    "Гудаутский район": "Gudauta district",
    "Сухумский район": "Sukhum district",
    "Гулрыпшский район": "Gulripsh district",
    "Очамчырский район": "Ochamchira district",
    "Ткуарчалский район": "Tkvarcheli district",
    "Галский район": "Gal district",
}
# Nationality rows, with the spaces the PDF puts inside some labels taken out.
NATIONALITY = {
    "Абхазы": "Abkhaz", "Русские": "Russian", "Армяне": "Armenian", "Грузины": "Georgian",
    "Украинцы": "Ukrainian", "Белорусы": "Belarusian", "Греки": "Greek",
    "Мегрелы": "Mingrelian", "Мингрелы": "Mingrelian", "Осетины": "Ossetian",
    "Татары": "Tatar", "Турки": "Turkish", "Цыгане": "Romani", "Эстонцы": "Estonian",
    "Другиенациональности": "Other",
}
# The most a district's share of a nationality on 1 January 2026 (table 1.16)
# moves from its 2011 share (1.12), in percentage points: 0.17 in this
# edition, Gudauta's Armenians.
SHARES_KEPT = 0.2
TITLES = {
    "1.1": r"1\.\s?1 Численность наличного населения",
    "1.2": r"1\.\s?2 Распределение наличного населения по возрастным группам",
    "1.6": r"1\.\s?6 Распределение наличного населения по возрастным группам",
    "1.7": r"1\.\s?7 Численность наличного населения по административно-",
    "1.11": r"1\.\s?11 Численность наличного населения по административно-",
    "1.12": r"1\.\s?12 Национальный состав наличного населения",
    "1.16": r"1\.\s?16 Национальный состав наличного населения",
}
# What the lines under each title must say, so that a later edition's tables
# are not read as this one's.
DATED = {"1.2": "Переписи населения 2011 года", "1.6": "1 января 2026 года",
         "1.7": "Переписи населения 2011 года", "1.11": "1 января 2026 года",
         "1.12": "Переписи населения 2011 года", "1.16": "1 января 2026 года"}
NEXT_TITLE = re.compile(r"^1\.\s?\d{1,2}\s+\S")

# The two polygons that are one district each: the map's label -> the row.
BOUND = {"Gagra": "Гагрский район", "Gudauta": "Гудаутский район"}

NOT_GEORGIAS = ("Georgia's own 2014 census and Geostat's estimates do not cover Abkhazia, and the "
                "authorities that count it are recognised by few states.")
ESTIMATE = ("their census of February 2011, carried forward with each year's births and arrivals "
            "added and deaths and departures taken away (their statistics committee's yearbook, "
            "table 1.11)")
NO_RELIGION = ("Not published: the de facto authorities' statistics committee gives no religion "
               "from their 2011 census, and Georgia's 2014 census did not count Abkhazia.")
NO_LANGUAGE = ("Not published: the de facto authorities' statistics committee gives nationality "
               "from their 2011 census but no language, and Georgia's 2014 census did not count "
               "Abkhazia.")
NO_DISTRICT_AGES = ("Not published by district: the de facto authorities' statistics committee "
                    "gives ages from their 2011 census for Abkhazia as a whole only.")
PARTS = ("Not written: the outline drawn here holds parts of several of the districts the de "
         "facto authorities count by, and none of them whole.")
SOUTH_EAST = ("The de facto authorities redrew the districts here after the war: in 1995 they "
              "formed Tkvarcheli district from parts of the Ochamchira and Gal districts, and "
              "they count more of Gal's former villages in Ochamchira district. The outlines "
              "drawn as Ochamchire and Gali are the districts as they were before, so neither "
              "holds a district the authorities count: ")


def south_east(people: dict[str, int]) -> str:
    """The figures the two south-eastern notes end on."""
    parts = [people["Очамчырский район"], people["Ткуарчалский район"], people["Галский район"]]
    return (f" Ochamchira, Tkvarcheli and Gal districts together had {sum(parts):,} people on "
            f"1 January {YEAR} ({parts[0]:,}, {parts[1]:,} and {parts[2]:,}); no figure is "
            "written for either outline.")


# The four polygons left without a figure: the map's label -> the population
# note, from the 2026 counts by district.
REFUSED: dict[str, Callable[[dict[str, int]], str]] = {
    "Sokhumi": lambda p: (
        f"The de facto authorities count the city of Sukhum ({p['г. Сухум']:,} people on "
        f"1 January {YEAR}) apart from the Sukhum district around it "
        f"({p['Сухумский район']:,}). This outline holds most of both, but the line drawn "
        "between it and Gulripshi runs through the east of the city, whose university lies "
        "in the outline drawn as Gulripshi: neither figure, nor their sum, is this "
        "outline's, so none is written here."),
    "Gulripshi": lambda p: (
        f"The de facto authorities' Gulripsh district had {p['Гулрыпшский район']:,} people "
        f"on 1 January {YEAR}. This outline holds most of it, but also the east of the city "
        "of Sukhum, which they count apart (the line drawn with Sokhumi runs through the "
        "city), while several of the district's villages lie in the outline drawn as "
        "Ochamchire: the district's figure is not this outline's, so none is written here."),
    "Ochamchire": lambda p: SOUTH_EAST + (
        "the town of Tkvarcheli lies in this one and many of its district's villages in "
        "Gali's, and several villages of Gulripsh district lie in this one too.") + south_east(p),
    "Gali": lambda p: SOUTH_EAST + (
        "villages of the Ochamchira and Tkvarcheli districts lie in this one, and Gal's "
        "villages along the Enguri, such as Otobaia, lie outside it, in the outline drawn as "
        "Zugdidi.") + south_east(p),
}


# ---------------------------------------------------------------------------
# Reading the yearbook's tables
# ---------------------------------------------------------------------------

def readings(tokens: list[str], k: int) -> list[list[int]]:
    """Every way to read ``tokens`` as ``k`` numbers printed with a space
    between thousands: a head of one to three digits and then groups of
    exactly three, or a number printed whole ("244236"); a dash is nothing."""
    if k == 0:
        return [] if tokens else [[]]
    if not tokens:
        return []
    head = tokens[0]
    if head in ("-", "–"):
        return [[0] + rest for rest in readings(tokens[1:], k - 1)]
    if not head.isdigit():
        return []
    if len(head) > 3:
        return [[int(head)] + rest for rest in readings(tokens[1:], k - 1)]
    out = []
    n = 1
    while True:
        value = int("".join(tokens[:n]))
        out += [[value] + rest for rest in readings(tokens[n:], k - 1)]
        if n < len(tokens) and len(tokens[n]) == 3 and tokens[n].isdigit():
            n += 1
        else:
            return out


def numbers(text: str, k: int, adds_up: Callable[[list[int]], bool], what: str) -> list[int]:
    """The one reading of ``text`` as ``k`` numbers for which ``adds_up`` holds."""
    found = [r for r in readings(text.split(), k) if adds_up(r)]
    if len(found) != 1:
        raise SystemExit(f"abkhazia_census: {what}: {text!r} reads as {len(found)} sets of "
                         f"{k} numbers that add up, not one")
    return found[0]


def table(text: str, key: str) -> list[str]:
    """The lines of table ``key``: from its title (the last time the title is
    printed, the contents page coming first) to the next table's."""
    lines = text.split("\n")
    title = re.compile("^" + TITLES[key])
    starts = [i for i, line in enumerate(lines) if title.match(line.strip())]
    if not starts:
        raise SystemExit(f"abkhazia_census: no table {key} in the yearbook")
    start = starts[-1]
    body: list[str] = []
    for line in lines[start + 1:]:
        if NEXT_TITLE.match(line.strip()):
            break
        body.append(line.strip())
    if key in DATED and not any(DATED[key] in line for line in [lines[start], *body[:3]]):
        raise SystemExit(f"abkhazia_census: table {key} is not dated {DATED[key]!r}")
    return body


ROW = re.compile(r"^(?P<label>.*?[^\d\s–-])\s+(?P<figures>[\d\s–-]+)$")


def labelled(lines: list[str]) -> list[tuple[str, str]]:
    """(label, figures) for each line that is a label followed by figures."""
    out = []
    for line in lines:
        m = ROW.match(line)
        if m:
            out.append((m.group("label").strip(), m.group("figures").strip()))
    return out


def year_total(lines: list[str], year: int) -> int:
    """Table 1.1's population for the start of ``year``."""
    for line in lines:
        tokens = line.split()
        if tokens and tokens[0] == str(year):
            cut = next(i for i, t in enumerate(tokens[1:]) if "," in t)
            return numbers(" ".join(tokens[1:cut + 1]), 3, lambda r: r[0] == r[1] + r[2],
                           f"table 1.1, {year}")[0]
    raise SystemExit(f"abkhazia_census: table 1.1 has no row for {year}")


def by_district(lines: list[str], key: str) -> dict[str, tuple[int, int, int]]:
    """{the republic and each district: (both sexes, men, women)}, from 1.7 or
    1.11. The republic is the first "Все население" row; the city and town rows
    inside a district are skipped."""
    out: dict[str, tuple[int, int, int]] = {}
    for label, figures in labelled(lines):
        if label == WHOLE and WHOLE not in out or label in DISTRICTS:
            if label in out:
                raise SystemExit(f"abkhazia_census: table {key} has two rows for {label!r}")
            both, men, women = numbers(figures, 3, lambda r: r[0] == r[1] + r[2],
                                       f"table {key}, {label}")
            out[label] = (both, men, women)
    missing = [d for d in (WHOLE, *DISTRICTS) if d not in out]
    if missing:
        raise SystemExit(f"abkhazia_census: table {key} has no row for {missing}")
    if sum(out[d][0] for d in DISTRICTS) != out[WHOLE][0]:
        raise SystemExit(f"abkhazia_census: table {key}'s districts make "
                         f"{sum(out[d][0] for d in DISTRICTS):,}, not {out[WHOLE][0]:,}")
    return out


def by_nationality(lines: list[str], key: str, totals: dict[str, int]
                   ) -> dict[str, dict[str, int]]:
    """{the republic and each district: {nationality: people}} from 1.12 or
    1.16, its columns told apart by ``totals`` (the same date's count of each
    district, from 1.7 or 1.11)."""
    rows: dict[str, list[int]] = {}
    for label, figures in labelled(lines):
        name = label.replace(" ", "")
        if name == WHOLE.replace(" ", ""):
            name = WHOLE
        elif name not in NATIONALITY:
            continue
        if name in rows:
            raise SystemExit(f"abkhazia_census: table {key} has two rows for {label!r}")
        rows[name] = numbers(figures, 1 + len(DISTRICTS), lambda r: r[0] == sum(r[1:]),
                             f"table {key}, {label}")
    if WHOLE not in rows:
        raise SystemExit(f"abkhazia_census: table {key} has no row for {WHOLE!r}")
    column: dict[str, int] = {}
    for district, total in totals.items():
        where = [j for j, v in enumerate(rows[WHOLE][1:], 1) if v == total]
        if len(where) != 1:
            raise SystemExit(f"abkhazia_census: table {key}: {total:,} ({district}) is in "
                             f"{len(where)} columns, not one")
        column[district] = where[0]
    groups = [g for g in rows if g != WHOLE]
    out: dict[str, dict[str, int]] = {}
    for unit, j in [(WHOLE, 0), *column.items()]:
        counts: dict[str, int] = {}
        for g in groups:
            counts[NATIONALITY[g]] = counts.get(NATIONALITY[g], 0) + rows[g][j]
        if sum(counts.values()) != rows[WHOLE][j]:
            raise SystemExit(f"abkhazia_census: table {key}, {unit}: the nationalities make "
                             f"{sum(counts.values()):,}, not {rows[WHOLE][j]:,}")
        out[unit] = counts
    return out


AGE = re.compile(r"^(?:(?P<lo>\d+)\s*[–-]\s*(?P<hi>\d+)|(?P<top>\d+) лет и старше)\s+(?P<rest>.+)$")


def by_age(lines: list[str], key: str) -> dict[int, tuple[int, str]]:
    """{the age group's lower bound: (people, the share printed beside them)}
    from 1.2 or 1.6; the open top group is 70 and over."""
    out: dict[int, tuple[int, str]] = {}
    for line in lines:
        m = AGE.match(line)
        if not m:
            continue
        tokens = m.group("rest").split()
        cut = next((i for i, t in enumerate(tokens) if "," in t), None)
        if not cut:
            raise SystemExit(f"abkhazia_census: table {key}: no share in {line!r}")
        people = readings(tokens[:cut], 1)
        if len(people) != 1:
            raise SystemExit(f"abkhazia_census: table {key}: {line!r} is not one count")
        lower = int(m.group("lo") or m.group("top"))
        if m.group("lo") and int(m.group("hi")) != lower + 4:
            raise SystemExit(f"abkhazia_census: table {key}: {line!r} is not a five-year group")
        out[lower] = (people[0][0], tokens[cut])
    if sorted(out) != list(range(0, 75, 5)):
        raise SystemExit(f"abkhazia_census: table {key} has the age groups {sorted(out)}")
    return out


# ---------------------------------------------------------------------------
# Checks and records
# ---------------------------------------------------------------------------

def read(text: str) -> dict[str, Any]:
    """Every figure the records use, checked against the yearbook's other tables."""
    t11 = by_district(table(text, "1.11"), "1.11")
    t7 = by_district(table(text, "1.7"), "1.7")
    whole = year_total(table(text, "1.1"), YEAR)
    if whole != t11[WHOLE][0]:
        raise SystemExit(f"abkhazia_census: table 1.11 makes {t11[WHOLE][0]:,} people and "
                         f"table 1.1 {whole:,} for {YEAR}")
    nat = by_nationality(table(text, "1.12"), "1.12", {d: t7[d][0] for d in DISTRICTS})
    if sum(nat[WHOLE].values()) != t7[WHOLE][0]:
        raise SystemExit("abkhazia_census: the 2011 nationality table does not make table "
                         "1.7's census count")
    later = by_nationality(table(text, "1.16"), "1.16", {d: t11[d][0] for d in DISTRICTS})
    for district in DISTRICTS:
        then, now = nat[district], later[district]
        for group in sorted(set(then) | set(now)):
            moved = abs(100 * then.get(group, 0) / sum(then.values())
                        - 100 * now.get(group, 0) / sum(now.values()))
            if moved > SHARES_KEPT:
                raise SystemExit(
                    f"abkhazia_census: table 1.16 moves {DISTRICTS[district]}'s {group} share "
                    f"{moved:.2f} points from 2011's: it is no longer the census's shares carried "
                    "forward, and should be read as a newer count")
    ages = by_age(table(text, "1.2"), "1.2")
    if sum(n for n, _ in ages.values()) != t7[WHOLE][0]:
        raise SystemExit(f"abkhazia_census: the 2011 age groups make "
                         f"{sum(n for n, _ in ages.values()):,}, not {t7[WHOLE][0]:,}")
    for lower, (_, share) in by_age(table(text, "1.6"), "1.6").items():
        if share != ages[lower][1]:
            raise SystemExit(f"abkhazia_census: table 1.6 prints {share} for the group from "
                             f"{lower}, and 2011's census {ages[lower][1]}: it is no longer "
                             "the census's shares, and should be read")
    median = grouped_median([(lower, None if lower == 70 else 5, n)
                             for lower, (n, _) in ages.items()])
    return {"people": t11, "nationality": nat, "median": median}


def cite(table_no: str, field: str) -> dict[str, str]:
    return {"field": field, "name": SOURCE.format(table=table_no), "url": URL, "license": LICENCE}


def counted(unit: str, figures: dict[str, Any], *, whole: bool) -> dict[str, Any]:
    """The fields of a polygon that is the republic or one of its districts."""
    both, men, women = figures["people"][unit]
    if whole:
        population_note = (f"The de facto authorities' estimate of the people present on 1 "
                           f"January {YEAR}: {ESTIMATE}. {NOT_GEORGIAS}")
    else:
        population_note = (f"The de facto authorities' estimate of the people present in "
                           f"{DISTRICTS[unit]} on 1 January {YEAR}: {ESTIMATE}. {NOT_GEORGIAS}")
    fields: dict[str, Any] = {
        "population": measure(both, year=YEAR, source=SOURCE.format(table="1.11")),
        "population_note": population_note,
        "sex_ratio": sex_ratio(men, women, year=YEAR, source=SOURCE.format(table="1.11")),
        "ethnicity": shares({g: n for g, n in figures["nationality"][unit].items() if n}),
        "ethnicity_year": CENSUS,
        "ethnicity_note": (
            "Nationality as the de facto authorities' census of February 2011 counted it "
            "(their statistics committee's yearbook, table 1.12), Georgians and Mingrelians "
            "apart as the census lists them. Their tables for later years, to 1 January 2026, keep each district's "
            "2011 shares to within a fifth of a percentage point, so they are not a newer count."),
        "religion": gap(NOT_AVAILABLE, NO_RELIGION),
        "language": gap(NOT_AVAILABLE, NO_LANGUAGE),
    }
    cites = [cite("1.11", "population/sex_ratio"), cite("1.12", "ethnicity")]
    if whole:
        fields["median_age"] = measure(figures["median"], unit="years", year=CENSUS,
                                       source=SOURCE.format(table="1.2"))
        fields["median_age_note"] = (
            "Interpolated within the five-year age group holding the middle person, from the "
            "de facto authorities' census of February 2011 (their statistics committee's "
            "yearbook, table 1.2). Their age tables for later years print the 2011 census's shares against each year's "
            "total, so they carry nothing newer.")
        cites.insert(1, cite("1.2", "median_age"))
    else:
        fields["median_age"] = gap(NOT_AVAILABLE, NO_DISTRICT_AGES)
    fields["sources"] = cites
    return fields


def refused(people: dict[str, int], name: str) -> dict[str, Any]:
    """The fields of a polygon that is no district: gaps that say why, and that no
    figure fits it, its own or one derived from its neighbours' (``not_this_ground``)."""
    return {"population": dict(gap(NOT_AVAILABLE, REFUSED[name](people)), not_this_ground=True),
            "sex_ratio": dict(gap(NOT_AVAILABLE, PARTS), not_this_ground=True),
            "ethnicity": dict(gap(NOT_AVAILABLE, PARTS), not_this_ground=True),
            "median_age": gap(NOT_AVAILABLE, NO_DISTRICT_AGES),
            "religion": gap(NOT_AVAILABLE, NO_RELIGION),
            "language": gap(NOT_AVAILABLE, NO_LANGUAGE)}


def records(figures: dict[str, Any], admin1: list[dict[str, Any]],
            admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The republic's record, the two districts', and the four gaps."""
    abkhazia = [u for u in admin1 if u["name"] == "Abkhazia"]
    if len(abkhazia) != 1:
        raise SystemExit(f"abkhazia_census: the map draws {len(abkhazia)} first-level "
                         "units named Abkhazia")
    whole = abkhazia[0]
    inside = {u["name"]: u for u in admin2 if u.get("parent") == whole["id"]}
    if set(inside) != set(BOUND) | set(REFUSED):
        raise SystemExit(f"abkhazia_census: the map draws {sorted(inside)} inside Abkhazia, "
                         f"not {sorted(set(BOUND) | set(REFUSED))}")
    people = {unit: both for unit, (both, _, _) in figures["people"].items()}
    out = [record(f"GEO-ABK-{whole['id']}", whole["name"], level="admin1", parent="GEO",
                  country="GEO", match_by="shape_id", shape_id=whole["id"],
                  **counted(WHOLE, figures, whole=True))]
    for name, unit in sorted(BOUND.items()):
        sid = inside[name]["id"]
        out.append(record(f"GEO-ABK-{sid}", name, level="admin2", parent="GEO",
                          country="GEO", match_by="shape_id", shape_id=sid,
                          **counted(unit, figures, whole=False)))
    for name in sorted(REFUSED):
        sid = inside[name]["id"]
        out.append(record(f"GEO-ABK-{sid}", name, level="admin2", parent="GEO",
                          country="GEO", match_by="shape_id", shape_id=sid,
                          **refused(people, name)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log(f"abkhazia_census: {URL}")
    blob = http_get(URL, binary=True, timeout=300)
    assert isinstance(blob, bytes)
    text = laid_out(blob).replace(PAGE_BREAK, "\n")
    figures = read(text)
    for unit, (both, men, women) in figures["people"].items():
        log(f"  1 January {YEAR}: {DISTRICTS.get(unit, 'Abkhazia')}: {both:,} "
            f"({men:,} men, {women:,} women)")
    log(f"  2011 census: median age {figures['median']}; nationality of "
        f"{sum(figures['nationality'][WHOLE].values()):,} people")
    rows = records(figures, drawn("GEO", "admin1"), drawn("GEO", "admin2"))
    write_json(PROCESSED / OUT, rows)
    log(f"wrote {len(rows)} records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
