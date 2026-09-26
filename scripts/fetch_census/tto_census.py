#!/usr/bin/env python3
"""Trinidad and Tobago: the 2011 census by municipality, from the CSO's Demographic Report.

The Central Statistical Office's *2011 Population and Housing Census
Demographic Report* prints, for the fourteen municipalities of Trinidad and
for Tobago:

* Table 1b, the de jure population, and its non-institutional part;
* Table 1.6, the median age;
* Table 2a, the population by five-year age group, for both sexes, men and women;
* Table 7, the non-institutional population by ethnic group;
* Table 8, the non-institutional population by religion.

The CSO's own host refuses this project's runner (HTTP 403 on every page), so
the report is read from the Internet Archive's capture of the CSO's file,
byte for byte (the ``id_`` form of the capture).

The map draws thirteen of the municipalities and Tobago, and no Borough of
Arima: measured on the map's own outlines, every part of Arima lies inside
the polygon named Tunapuna-Piarco. So that polygon carries the two added
together -- their people, their ethnic groups and religions, their age groups
-- and its median age is interpolated from the summed age groups rather than
taken from Table 1.6, which gives each only separately. Every note says so.

Checks, each of which stops the run: every municipality's ethnic groups and
religions make its non-institutional population in Table 1b; the
municipalities make Trinidad and, with Tobago, the country's 1,328,019 (de
jure) and 1,322,546 (non-institutional); each unit's age groups make its
population and its men and women make it too. The median interpolated from
Table 2a is compared with Table 1.6's for every municipality, and a
difference of more than a year stops the run, because that would mean the age
groups were misread.

Usage:
    python -m scripts.fetch_census.tto_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = PROCESSED / "tto_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2011
ORIGINAL = "https://cso.gov.tt/wp-content/uploads/2020/01/2011-Demographic-Report.pdf"
CAPTURE = "20200512061508"
URL = f"https://web.archive.org/web/{CAPTURE}id_/{ORIGINAL}"
SOURCE = ("Central Statistical Office of Trinidad and Tobago, 2011 Population and Housing "
          "Census Demographic Report (read from the Internet Archive's capture of the CSO's file)")
DE_JURE = 1_328_019
NON_INSTITUTIONAL = 1_322_546

# The report's units, as its tables print them (fold() ignores spacing and slashes).
MUNICIPALITIES = (
    "City of Port of Spain", "City of San Fernando", "Borough of Arima", "Borough of Chaguanas",
    "Borough of Point Fortin", "Couva/ Tabaquite/ Talparo", "Diego Martin",
    "Mayaro/ Rio Claro", "Penal/ Debe", "Princes Town", "San Juan / Laventille",
    "Sangre Grande", "Siparia", "Tunapuna/ Piarco")
TOBAGO_PARISHES = ("St.Andrew", "St.David", "St.George", "St.John", "St.Mary", "St.Patrick",
                   "St.Paul")
TOTALS = ("TRINIDAD AND TOBAGO", "TRINIDAD", "TOBAGO")
UNITS = MUNICIPALITIES + TOTALS + TOBAGO_PARISHES
# The map's polygons, and the report's units each holds.
POLYGONS = {
    "Port of Spain": ("City of Port of Spain",), "San Fernando": ("City of San Fernando",),
    "Chaguanas": ("Borough of Chaguanas",), "Point Fortin": ("Borough of Point Fortin",),
    "Couva-Tabaquite-Talparo": ("Couva/ Tabaquite/ Talparo",),
    "Diego Martin": ("Diego Martin",), "Rio Claro-Mayaro": ("Mayaro/ Rio Claro",),
    "Penal-Debe": ("Penal/ Debe",), "Princes Town": ("Princes Town",),
    "San Juan-Laventille": ("San Juan / Laventille",), "Sangre Grande": ("Sangre Grande",),
    "Siparia": ("Siparia",), "Tobago": ("TOBAGO",),
    "Tunapuna-Piarco": ("Tunapuna/ Piarco", "Borough of Arima"),
}
ETHNICITY = {
    "African": "African", "Caucasian": "White", "Chinese": "Chinese",
    "East Indian": "East Indian", "Indigenous": "Indigenous",
    "Mixed - African/ East Indian": "Mixed (African and East Indian)",
    "Mixed - Other": "Mixed (other)", "Portuguese": "Portuguese",
    "Syrian/ Lebanese": "Syrian/Lebanese", "Other ethnic group": "Other",
    "Not stated": "Not stated",
}
RELIGION = {
    "Anglican": "Anglican", "Baptist-Spiritual Shouter": "Spiritual Baptist",
    "Baptist-Other": "Baptist", "Hinduism": "Hindu", "Islam": "Muslim",
    "Jehovah's Witness": "Jehovah's Witnesses", "Methodist": "Methodist",
    "Moravian": "Moravian", "Orisha": "Orisha",
    "Pentecostal/ Evangelical/ Full Gospel": "Pentecostal/Evangelical/Full Gospel",
    "Presbyterian/ Congregational": "Presbyterian/Congregational",
    "Rastafarian": "Rastafarian", "Roman Catholic": "Roman Catholic",
    "Seventh Day Adventist": "Seventh-day Adventist", "Other": "Other religion",
    "None": "No religion", "Not Stated": "Not stated",
}
# How far the CSO's own printed sums may miss, in people. Table 2a's age groups
# for the whole country make 1,328,017 against its printed 1,328,019; a
# misread column is thousands.
SLACK = 5
NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+|-)$")
FOOTER = re.compile(r"POPULATION AND HOUSING CENSUS|DEMOGRAPHIC REPORT")
INDEX = re.compile(r"^\(\d+\)")


def key(name: str) -> str:
    return fold(str(name).replace("’", "'"))


def value(token: str) -> int:
    return 0 if token == "-" else int(token.replace(",", ""))


def split(line: str) -> tuple[str, list[int]]:
    """A line's words and its figures: "City of 48,838 3,123" -> ("City of", [48838, 3123]).

    The figures are the longest unbroken run of numeric tokens, because a dash
    is both a zero ("- 1 1 3") and part of a label ("Mixed - Other").
    """
    tokens = line.split()
    best, start = (0, 0), None
    for i, token in enumerate(tokens + [""]):
        if NUMBER.match(token):
            start = i if start is None else start
        elif start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    numbers = [value(t) for t in tokens[best[0]:best[1]]]
    words = tokens[:best[0]] + tokens[best[1]:]
    return " ".join(words), numbers


def rows(lines: list[str], known: set[str]) -> list[tuple[str, list[int]]]:
    """(label, figures) for every figure line of a table page, its label reassembled.

    A label the page wraps is put back together: the words of lines without
    figures before a figure line, the figure line's own, and -- if that is
    still not a name in ``known`` -- the word lines after it, one at a time,
    until it is. A label that never becomes a known name stops the run.
    """
    body, started = [], False
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if INDEX.match(text):
            started = True
            continue
        if FOOTER.search(text):
            break
        if started:
            body.append(split(text))
    out, pending, i = [], [], 0
    while i < len(body):
        words, numbers = body[i]
        i += 1
        if not numbers:
            pending.append(words)
            continue
        label = " ".join(p for p in pending + [words] if p)
        pending = []
        while key(label) not in known and i < len(body) and not body[i][1]:
            label = f"{label} {body[i][0]}".strip()
            i += 1
        if key(label) not in known:
            raise SystemExit(f"tto_census: row label {label!r} is not one this reads")
        out.append((label, numbers))
    return out


def page_lines(text: str) -> list[str]:
    """A page's lines, with the doubled text layer some pages carry taken out."""
    out = []
    for line in text.splitlines():
        if not out or line != out[-1]:
            out.append(line)
    return out


def section(lines: list[str]) -> tuple[str, bool]:
    """("BOTH SEXES" | "MALE" | "FEMALE", whether this is the page with All Ages)."""
    head = [ln.strip().upper() for ln in lines[:12]]
    sex = next((h for h in head if h in ("BOTH SEXES", "MALE", "FEMALE")), "")
    return sex, any(re.match(r"^ALL(\s|$)", h) for h in head)


def blocks(table: list[tuple[str, list[int]]], units: set[str],
           labels: dict[str, str]) -> dict[str, dict[str, int]]:
    """{unit key: {category: all-ages count, "_total": n}} from a unit/category table."""
    out: dict[str, dict[str, int]] = {}
    current = None
    for label, numbers in table:
        k = key(label)
        if k in units:
            current = k
            out[current] = {"_total": numbers[0]}
        elif current is not None:
            name = next(v for c, v in labels.items() if key(c) == k)
            out[current][name] = out[current].get(name, 0) + numbers[0]
    return out


def ages(left: list[tuple[str, list[int]]], right: list[tuple[str, list[int]]]
         ) -> dict[str, dict[str, Any]]:
    """{unit key: {"total", "groups", "unstated"}} from Table 2a's two pages for one sex."""
    lows = [0, 5, 10, 15, 20, 25, 30, 35]
    out = {}
    for label, numbers in left:
        if len(numbers) != 9:
            raise SystemExit(f"tto_census: Table 2a's {label} has {len(numbers)} figures, not 9")
        out[key(label)] = {"total": numbers[0],
                           "groups": [(lo, lo + 4, n) for lo, n in zip(lows, numbers[1:])]}
    for label, numbers in right:
        if len(numbers) != 10:
            raise SystemExit(f"tto_census: Table 2a's {label} has {len(numbers)} figures, not 10")
        unit = out[key(label)]
        unit["groups"] += [(lo, lo + 4, n) for lo, n in zip(range(40, 80, 5), numbers[:8])]
        unit["groups"].append((80, None, numbers[8]))
        unit["unstated"] = numbers[9]
        made = sum(g[2] for g in unit["groups"]) + unit["unstated"]
        if abs(made - unit["total"]) > SLACK:
            raise SystemExit(f"tto_census: {label}'s age groups make {made:,} of "
                             f"{unit['total']:,}")
        if made != unit["total"]:
            log(f"  Table 2a: {label}'s age groups make {made:,} of {unit['total']:,}")
    return out


MEDIAN = re.compile(r"^(.*?)\s+2011\s+(\d+\.\d)\s")


def medians(lines: list[str]) -> dict[str, float]:
    """{unit key: median age in 2011} from Table 1.6."""
    out = {}
    for line in lines:
        m = MEDIAN.match(line.strip())
        if m:
            out[key(m.group(1))] = float(m.group(2))
    return out


def check_parts(table: dict[str, Any], what: str, total_of) -> None:
    """The municipalities make Trinidad, and Trinidad and Tobago the country."""
    trinidad = sum(total_of(table[key(m)]) for m in MUNICIPALITIES)
    if trinidad != total_of(table[key("TRINIDAD")]):
        raise SystemExit(f"tto_census: the municipalities' {what} make {trinidad:,}, Trinidad's "
                         f"is {total_of(table[key('TRINIDAD')]):,}")
    both = total_of(table[key("TRINIDAD")]) + total_of(table[key("TOBAGO")])
    if both != total_of(table[key("TRINIDAD AND TOBAGO")]):
        raise SystemExit(f"tto_census: Trinidad and Tobago's {what} do not add up")


def read(pages: list[list[str]]) -> dict[str, Any]:
    """Everything this writes, from the report's pages as lines (1-based page list)."""
    units = {key(u) for u in UNITS}
    ethnic_known = units | {key(c) for c in ETHNICITY}
    religion_known = units | {key(c) for c in RELIGION}
    population: dict[str, tuple[int, int]] = {}
    median_published: dict[str, float] = {}
    age_pages: dict[str, dict[str, list]] = {}
    ethnic_rows: list[tuple[str, list[int]]] = []
    religion_rows: list[tuple[str, list[int]]] = []
    for lines in pages:
        head = " ".join(lines[:6]).upper()
        if re.search(r"\bTABLE 1B\b", head):
            for label, numbers in rows(lines, units):
                population[key(label)] = (numbers[0], numbers[1])
        elif re.search(r"\bTABLE 1\.6\b", head):
            median_published.update(medians(lines))
        elif re.search(r"\bTABLE 2A\b", head):
            sex, left = section(lines)
            age_pages.setdefault(sex, {})["left" if left else "right"] = rows(lines, units)
        elif re.search(r"\bTABLE [78]\b", head):
            # A municipality's block can run over onto the next page, so the
            # pages' rows are gathered first and read as one table.
            sex, left = section(lines)
            if sex != "BOTH SEXES" or not left:
                continue
            if re.search(r"\bTABLE 7\b", head):
                ethnic_rows += rows(lines, ethnic_known)
            else:
                religion_rows += rows(lines, religion_known)
    ethnicity = blocks(ethnic_rows, units, ETHNICITY)
    religion = blocks(religion_rows, units, RELIGION)
    both = ages(age_pages["BOTH SEXES"]["left"], age_pages["BOTH SEXES"]["right"])
    men = {key(l): n[0] for l, n in age_pages["MALE"]["left"]}
    women = {key(l): n[0] for l, n in age_pages["FEMALE"]["left"]}
    for k, unit in both.items():
        if men[k] + women[k] != unit["total"]:
            raise SystemExit(f"tto_census: {k}'s men and women do not make {unit['total']:,}")
    if population[key("TRINIDAD AND TOBAGO")] != (DE_JURE, NON_INSTITUTIONAL):
        raise SystemExit(f"tto_census: Table 1b's country row is "
                         f"{population[key('TRINIDAD AND TOBAGO')]}")
    check_parts(population, "populations", lambda p: p[0])
    check_parts(population, "non-institutional populations", lambda p: p[1])
    check_parts(both, "age tables", lambda u: u["total"])
    for what, table in (("ethnic groups", ethnicity), ("religions", religion)):
        for k, counts in table.items():
            made = sum(v for c, v in counts.items() if c != "_total")
            if made != counts["_total"] or counts["_total"] != population[k][1]:
                raise SystemExit(f"tto_census: {k}'s {what} make {made:,}; its total is "
                                 f"{counts['_total']:,} and Table 1b's non-institutional "
                                 f"{population[k][1]:,}")
        check_parts(table, what, lambda c: c["_total"])
    for m in MUNICIPALITIES + ("TOBAGO",):
        k = key(m)
        computed = grouped_median(sorted(both[k]["groups"], key=lambda g: g[0]))
        if abs(computed - median_published[k]) > 1.0:
            raise SystemExit(f"tto_census: {m}'s median from Table 2a is {computed}, Table "
                             f"1.6 prints {median_published[k]}")
    return {"population": population, "median": median_published, "ages": both, "men": men,
            "women": women, "ethnicity": ethnicity, "religion": religion}


def pdf_pages(blob: bytes) -> list[list[str]]:
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            try:
                page = page.dedupe_chars()
            except AttributeError:
                pass
            out.append(page_lines(page.extract_text() or ""))
    return out


def combine(parts: list[dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in parts:
        for c, v in part.items():
            if c != "_total":
                out[c] = out.get(c, 0) + v
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    data = read(pdf_pages(http_get(URL, binary=True, cache=False)))
    log(f"  {len(MUNICIPALITIES)} municipalities and Tobago making {DE_JURE:,} (de jure) and "
        f"{NON_INSTITUTIONAL:,} (non-institutional); ethnic groups, religions, ages and sexes "
        "each make every unit")
    admin1 = json.loads((SITE / "admin1" / "TTO.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    if len(shapes) != len(POLYGONS):
        raise SystemExit(f"tto_census: the map draws {len(shapes)} units, not {len(POLYGONS)}")
    records = []
    for ours, theirs in POLYGONS.items():
        shape = shapes.get(fold(ours))
        if shape is None:
            raise SystemExit(f"tto_census: no polygon named {ours!r}")
        ks = [key(t) for t in theirs]
        joined = len(ks) > 1
        what = " and ".join(theirs)
        pop = sum(data["population"][k][0] for k in ks)
        groups: dict[tuple[int, int | None], int] = {}
        for k in ks:
            for lo, hi, n in data["ages"][k]["groups"]:
                groups[(lo, hi)] = groups.get((lo, hi), 0) + n
        median = (grouped_median([(lo, hi, n) for (lo, hi), n in sorted(groups.items(),
                                                                         key=lambda g: g[0][0])])
                  if joined else data["median"][ks[0]])
        men = sum(data["men"][k] for k in ks)
        women = sum(data["women"][k] for k in ks)
        joint = (f" The map draws no Borough of Arima: its ground lies inside this polygon, "
                 f"so the figure is {what}'s together." if joined else "")
        records.append(record(
            f"TTO-CSO-{fold(ours)}", shape["name"], level="admin1", parent="TTO", country="TTO",
            match_by="shape_id", shape_id=shape["id"],
            aliases=[t for t in theirs if t != shape["name"]],
            population=measure(pop, year=YEAR, source=SOURCE),
            population_note=(f"The 2011 census's de jure population (Table 1b).{joint}"),
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
            median_age_note=(("Interpolated within the five-year age group holding the middle "
                              "person, from Table 2a's age groups added together (people of "
                              "unstated age left out)." if joined else
                              "Table 1.6's median age for the municipality.") + joint),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            sex_ratio_note=f"Men per thousand women in Table 2a's population.{joint}",
            ethnicity=shares(combine([data["ethnicity"][k] for k in ks])), ethnicity_year=YEAR,
            ethnicity_note=("Ethnic group, as asked of the non-institutional population "
                            f"(Table 7); \"Not stated\" is the census's own line.{joint}"),
            religion=shares(combine([data["religion"][k] for k in ks])), religion_year=YEAR,
            religion_note=("Religion, as asked of the non-institutional population (Table 8), "
                           "in the census's own denominations; \"Baptist-Spiritual Shouter\" is "
                           f"written as Spiritual Baptist.{joint}"),
            sources=[{"field": "population/median_age/sex_ratio/ethnicity/religion",
                      "name": SOURCE, "url": ORIGINAL, "archived": URL, "year": YEAR}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
