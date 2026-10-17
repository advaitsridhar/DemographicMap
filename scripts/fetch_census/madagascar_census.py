#!/usr/bin/env python3
"""Madagascar -- the 2018 census (RGPH-3) by district and region.

INSTAT's "Résultats globaux du RGPH-3 de 2018, Tome 2" prints, in its Tableau
8, the resident population of every region and district by sex, with its
demographic weight, sex ratio, share of women and density. A line reads

    Antsirabe I 119 710 126 644 246 354 1,0 94,5 51,4 1854,6

-- men, women and both, each written with spaces between its thousands, then
four figures with decimal commas. The three counts are told apart by the one
split of the digit groups whose men and women make the total (and, were two
to, by the sex ratio printed beside them). Region names are printed rotated,
so the text layer gives them reversed; a region is known instead by its
"Total Région" line and its districts, which must all lie in one first-level
polygon of the map.

Written: the census's count and the sex ratio (men per thousand women) of
every district and region the map draws, and each region's median age.
Antananarivo Renivohitra is one district in the census and six arrondissements
on the map; the arrondissements say so instead of carrying a figure.

**Median ages.** The same volume counts each region's people in the age bands
health programmes use: Tableau 6 those of 15, 18 and 25 and over, Tableau 5
those of 18-24, 19-24 and 20-24, Tableau 4 those of 10-14 and 15-17. Together
they give how many are under 10, 15, 18, 19, 20 and 25, and the median is
interpolated within the band that holds the middle person (Androy's, under 15,
between 10 and 15) -- for the country, between 18 and 19, which INSTAT's own
Tome 1 (Tableau 14) gives as a median of 18. Each table's left page carries the
region names and the first columns, its right page the rest, line for line;
a line's digit groups are read as consecutive (men, women, both) triples, the
one reading in which every triple adds up. Districts get no median: no table
of the volume gives ages below the region.

**Checks before anything is written.** Every line's men and women make its
total; each region's districts make its Total Région line; the regions make
the census's 25,674,196. For the ages, every triple's men and women make its
both-sexes figure, and the 18 and over less the 25 and over is the 18-24 band
of the other table.

Usage:
    python -m scripts.fetch_census.madagascar_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from itertools import combinations
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .southern_africa_common import fetch, key, sex_ratio, units

URL = ("https://www.instat.mg/documents/upload/main/"
       "INSTAT_RGPH3-Definitif-ResultatsGlogaux-Tome2_17-2021.pdf")
SOURCE = ("INSTAT Madagascar, Résultats globaux du RGPH-3 de 2018, Tome 2, Tableau 8 "
          "(population résidente par sexe selon la région et le district)")
LICENCE = "INSTAT Madagascar publication (reuse with attribution)"
YEAR = 2018
NATIONAL = 25_674_196
OUT = "madagascar_census.json"
TITLE = "Tableau 8."
NEXT_TITLE = "Tableau 9."

# The census's district names, reduced -> the map's, reduced.
ALIASES = {"toliarai": "toliaryi", "toliaraii": "toliaryii"}
# The map's region names, reduced -> the census's, reduced (for the notes).
REGION_ALIASES = {"matsiatraambony": "hautematsiatra"}
# The census's one district that the map draws as several polygons.
SPLIT = {"antananarivorenivohitra": re.compile(r"(?i)arrondissement")}
SPLIT_NOTE = ("The 2018 census counts Antananarivo Renivohitra as one district, {total:,} "
              "people ({men:,} men and {women:,} women; INSTAT, RGPH-3 Résultats globaux, "
              "Tome 2, Tableau 8), and publishes no count for its six arrondissements.")

FIGURES = re.compile(r"^(?P<name>.*?)\s*(?P<counts>\d{1,3}(?: \d{3})*(?: \d{1,3}(?: \d{3})*)*)"
                     r"\s+(?P<weight>\d+,\d)\s+(?P<ratio>\d+,\d)\s+(?P<women>\d+,\d)"
                     r"\s+(?P<density>\d+,\d)$")


def splits(counts: str) -> list[tuple[int, int, int]]:
    """Every reading of the digit groups as men, women and total whose men and
    women make the total."""
    tokens = counts.split()

    def number(parts: list[str]) -> int | None:
        if not parts or (len(parts) > 1 and (len(parts[0]) > 3
                                             or any(len(p) != 3 for p in parts[1:]))):
            return None
        return int("".join(parts))

    out = []
    for i, j in combinations(range(1, len(tokens)), 2):
        a, b, c = number(tokens[:i]), number(tokens[i:j]), number(tokens[j:])
        if None not in (a, b, c) and a + b == c:
            out.append((a, b, c))
    return out


def reading(counts: str, ratio: str) -> tuple[int, int, int]:
    options = splits(counts)
    if len(options) > 1:
        printed = float(ratio.replace(",", "."))
        options = [o for o in options if abs(100 * o[0] / o[1] - printed) < 0.06]
    if len(options) != 1:
        raise SystemExit(f"madagascar_census: {counts!r} reads as {options}")
    return options[0]


AGE_SOURCE = ("INSTAT Madagascar, Résultats globaux du RGPH-3 de 2018, Tome 2, Tableaux 4 to 6 "
              "(population of the health programmes' age groups by region)")
AGE_NOTE_DISTRICT = ("INSTAT's RGPH-3 Résultats globaux give ages by region (Tome 2, Tableaux 2 "
                     "to 6), not by district, so no median age is published for this district.")
# Tableau 5's columns (both sexes taken), and Tableau 6's.
T4 = ("10-14", "10-19", "10-24", "15-17", "15-19", "15-24", "15-49")
T5 = ("18-24", "19-24", "20-24", "25-49", "50-59")
T6 = ("15+", "18+", "25+", "49+", "60+")
REGION_NAMES = ("Analamanga", "Vakinankaratra", "Itasy", "Bongolava", "Haute Matsiatra",
                "Amoron'i Mania", "Vatovavy Fitovinany", "Ihorombe", "Atsimo Atsinanana",
                "Atsinanana", "Analanjirofo", "Alaotra Mangoro", "Boeny", "Sofia", "Betsiboka",
                "Melaky", "Atsimo Andrefana", "Androy", "Anosy", "Menabe", "Diana", "Sava")


NAMED_LINE = re.compile(r"^(?P<name>[^\d]+?)\s+(?P<nums>\d{1,3}(?: \d{3})*(?: \d{1,3}(?: \d{3})*)*)$")


def triples(tokens: list[str]) -> list[tuple[int, int, int]]:
    """The digit groups of a line as consecutive (men, women, both) triples:
    the one reading in which every triple adds up."""
    found: list[list[int]] = []

    def walk(i: int, nums: list[int]) -> None:
        if len(found) > 1:
            return
        if i == len(tokens):
            if nums and len(nums) % 3 == 0:
                found.append(list(nums))
            return
        for k in range(1, 5):
            parts = tokens[i:i + k]
            if len(parts) < k or len(parts[0]) > 3 or any(len(t) != 3 for t in parts[1:]):
                break
            n = int("".join(parts))
            if len(nums) % 3 == 2 and nums[-2] + nums[-1] != n:
                continue
            walk(i + k, nums + [n])

    walk(0, [])
    if len(found) != 1:
        raise SystemExit(f"madagascar_census: {' '.join(tokens)!r} reads as "
                         f"{len(found)} sets of triples")
    nums = found[0]
    return [(nums[i], nums[i + 1], nums[i + 2]) for i in range(0, len(nums), 3)]


def two_page_table(left: str, right: str, columns: tuple[str, ...]) -> dict[str, dict[str, int]]:
    """{region name: {column: both sexes}} from a table's left page (names and
    the first columns) and right page (the rest, line for line)."""
    names = ("MADAGASCAR",) + REGION_NAMES
    by_key = {key(n): n for n in names}
    lefts: list[tuple[str, list[str]]] = []
    for raw in left.splitlines():
        hit = NAMED_LINE.match(" ".join(raw.split()))
        if hit and key(hit.group("name")) in by_key:
            lefts.append((by_key[key(hit.group("name"))], hit.group("nums").split()))
    rights = [" ".join(raw.split()).split() for raw in right.splitlines()
              if re.fullmatch(r"\d{1,3}(?: \d{3})*(?: \d{1,3}(?: \d{3})*)+",
                              " ".join(raw.split()))]
    if [n for n, _ in lefts] != list(names) or len(rights) != len(lefts):
        raise SystemExit(f"madagascar_census: {len(lefts)} named lines "
                         f"({[n for n, _ in lefts][:3]}...) and {len(rights)} lines of figures")
    out: dict[str, dict[str, int]] = {}
    for (name, a), b in zip(lefts, rights):
        got = triples(a + b)
        if len(got) != len(columns):
            raise SystemExit(f"madagascar_census: {name}: {len(got)} age groups, not "
                             f"{len(columns)}")
        out[name] = {c: t[2] for c, t in zip(columns, got)}
    return out


def page_after(pages: list[str], title: str) -> tuple[str, str]:
    for i, text in enumerate(pages[:-1]):
        if title in text and "LISTE DES TABLEAUX" not in text and "...." not in text:
            return text, pages[i + 1]
    raise SystemExit(f"madagascar_census: no page titled {title!r}")


def region_ages(pages: list[str]) -> dict[str, dict[str, int]]:
    """{region name: people of 10, 15, 18, 19, 20 and 25 and over}, checked."""
    t4 = two_page_table(*page_after(pages, "Tableau 4."), T4)
    t5 = two_page_table(*page_after(pages, "Tableau 5."), T5)
    t6 = two_page_table(*page_after(pages, "Tableau 6."), T6)
    out: dict[str, dict[str, int]] = {}
    for name in ("MADAGASCAR",) + REGION_NAMES:
        y, a, b = t4[name], t5[name], t6[name]
        if b["18+"] - b["25+"] != a["18-24"] or b["15+"] - b["18+"] != y["15-17"]:
            raise SystemExit(f"madagascar_census: {name}: the bands of Tableaux 4, 5 and 6 "
                             f"disagree ({b}, {a['18-24']:,}, {y['15-17']:,})")
        out[name] = {"10": b["15+"] + y["10-14"], "15": b["15+"], "18": b["18+"],
                     "19": b["25+"] + a["19-24"], "20": b["25+"] + a["20-24"], "25": b["25+"]}
    return out


def median_from(total: int, over: dict[str, int]) -> float:
    """The median age from a total and the people at or over each age."""
    ages = sorted(int(k) for k in over)
    below = {a: total - over[str(a)] for a in ages}
    half = total / 2
    for lo, hi in zip(ages, ages[1:]):
        if below[lo] <= half < below[hi]:
            return round(lo + (hi - lo) * (half - below[lo]) / (below[hi] - below[lo]), 1)
    raise SystemExit(f"madagascar_census: the median of {total:,} lies outside "
                     f"{ages[0]}-{ages[-1]} ({below})")


def rotated(line: str) -> bool:
    """A region name the text layer gives reversed: 'agnamalanA', 'etuaH'."""
    words = [w for w in line.split() if any(c.isalpha() for c in w)]
    return bool(words) and all(w[-1].isupper() and not w[0].isupper() for w in words)


def parse(pages: list[str]) -> dict[str, Any]:
    """{"regions": [{"men", "women", "total", "districts": [...]}], "national": row}."""
    regions: list[dict[str, Any]] = []
    national: dict[str, Any] | None = None
    started = False
    last: dict[str, Any] | None = None
    pending: list[str] = []
    for text in pages:
        if not started:
            if TITLE not in text:
                continue
            started = True
        elif NEXT_TITLE in text:
            break
        for raw in text.splitlines():
            line = " ".join(raw.split())
            hit = FIGURES.match(line)
            if not hit:
                if line and re.search(r"[a-z]", line) and not re.search(
                        r"(?i)(résultats|effectif|région district|homme femme|d[ée]cembre|"
                        r"répartition|rapport de masculinité|source|tableau|graphique)", line):
                    pending.append(line)
                continue
            men, women, total = reading(hit.group("counts"), hit.group("ratio"))
            row = {"men": men, "women": women, "total": total,
                   "ratio": float(hit.group("ratio").replace(",", "."))}
            name = hit.group("name")
            # Lines with no figures finish the name of the district before
            # them, unless they are a rotated region name (each word reversed,
            # its capital last), which is dropped.
            rest = [ln for ln in pending if not rotated(ln)]
            if last is not None and rest:
                last["name"] = " ".join([last["name"]] + rest)
            if "Total Région" in name:
                regions.append({**row, "districts": []})
                last = None
            elif name.strip().upper() == "MADAGASCAR":
                national = row
                last = None
            else:
                if not regions:
                    raise SystemExit(f"madagascar_census: {name!r} comes before any region")
                last = {**row, "name": name.strip()}
                regions[-1]["districts"].append(last)
            pending = []
    check(regions, national)
    return {"regions": regions, "national": national}


def check(regions: list[dict[str, Any]], national: dict[str, Any] | None) -> None:
    if national is None or national["total"] != NATIONAL:
        raise SystemExit(f"madagascar_census: the national line is {national}, not {NATIONAL:,}")
    for field in ("men", "women", "total"):
        made = sum(r[field] for r in regions)
        if made != national[field]:
            raise SystemExit(f"madagascar_census: the regions make {made:,} {field}, "
                             f"not {national[field]:,}")
        for r in regions:
            got = sum(d[field] for d in r["districts"])
            if got != r[field]:
                names = [d["name"] for d in r["districts"]]
                raise SystemExit(f"madagascar_census: the districts {names} make {got:,} "
                                 f"{field}, not their region's {r[field]:,}")
    log(f"  {len(regions)} regions, {sum(len(r['districts']) for r in regions)} districts")


def district_key(name: str) -> str:
    k = key(name)
    return ALIASES.get(k, k)


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {key(s["name"]): s for s in admin2}
    out: list[dict[str, Any]] = []
    sources = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                "license": LICENCE, "year": YEAR}]
    age_sources = sources + [{"field": "median_age", "name": AGE_SOURCE, "url": URL,
                              "license": LICENCE, "year": YEAR}]
    ages = table.get("ages") or {}
    no_age = gap(NOT_AVAILABLE, AGE_NOTE_DISTRICT)
    used: set[str] = set()
    for region in table["regions"]:
        parents = set()
        for d in region["districts"]:
            k = district_key(d["name"])
            if k in SPLIT:
                parts = [s for s in admin2 if SPLIT[k].search(s["name"])]
                if not parts:
                    raise SystemExit(f"madagascar_census: the map draws no part of {d['name']}")
                parents.update(s.get("parent") for s in parts)
                for s in parts:
                    used.add(s["id"])
                    note = SPLIT_NOTE.format(**d)
                    out.append(record(f"MDG-2018-{key(s['name'])}", s["name"], level="admin2",
                                      parent="MDG", country="MDG", match_by="shape_id",
                                      shape_id=s["id"], sources=sources,
                                      population=gap(NOT_AVAILABLE, note),
                                      sex_ratio=gap(NOT_AVAILABLE, note), median_age=no_age))
                continue
            shape = by_key.get(k)
            if shape is None:
                raise SystemExit(f"madagascar_census: no polygon for the district {d['name']!r}")
            used.add(shape["id"])
            parents.add(shape.get("parent"))
            out.append(record(f"MDG-2018-{k}", shape["name"], level="admin2", parent="MDG",
                              country="MDG", match_by="shape_id", shape_id=shape["id"],
                              sources=sources,
                              population=measure(d["total"], year=YEAR, source=SOURCE),
                              population_note=f"The 2018 census's count for the district of "
                                              f"{d['name']}.",
                              sex_ratio=sex_ratio(d["men"], d["women"], year=YEAR,
                                                  source=SOURCE), median_age=no_age))
        if len(parents) != 1:
            raise SystemExit(f"madagascar_census: the districts of one census region lie in "
                             f"{len(parents)} regions of the map: "
                             f"{[d['name'] for d in region['districts']]}")
        parent = next(s for s in admin1 if s["id"] == next(iter(parents)))
        region["shape"] = parent
        census_name = next((n for n in REGION_NAMES if key(n) == REGION_ALIASES.get(
            key(parent["name"]), key(parent["name"]))), None)
        median: dict[str, Any] = {}
        if ages:
            if census_name not in ages:
                raise SystemExit(f"madagascar_census: no age table line for {parent['name']}")
            median = {"median_age": measure(median_from(region["total"], ages[census_name]),
                                            year=YEAR, source=AGE_SOURCE),
                      "median_age_note": (
                          "Interpolated within the age band that holds the middle person, "
                          "from the 2018 census's counts of the people under 10, 15, 18, 19, "
                          "20 and 25 (INSTAT, RGPH-3 Résultats globaux, Tome 2, Tableaux 4 to "
                          "6).")}
        out.append(record(f"MDG-2018-region-{key(parent['name'])}", parent["name"],
                          level="admin1", parent="MDG", country="MDG", match_by="shape_id",
                          shape_id=parent["id"], sources=age_sources if median else sources,
                          **median,
                          population=measure(region["total"], year=YEAR, source=SOURCE),
                          population_note=f"The 2018 census's count for the region of "
                                          f"{parent['name']}.",
                          sex_ratio=sex_ratio(region["men"], region["women"], year=YEAR,
                                              source=SOURCE)))
    missing = [s["name"] for s in admin2 if s["id"] not in used]
    if missing:
        raise SystemExit(f"madagascar_census: polygons with no census district: {missing}")
    if len({r["shape"]["id"] for r in table["regions"]}) != len(admin1):
        raise SystemExit("madagascar_census: the census's regions are not the map's one for one")
    return out


def pages_of(blob: bytes) -> list[str]:
    """The text of the volume's pages 8 to 40, where its age and district
    tables are."""
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages[7:40]]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=("2022", "2024"), expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    pages = pages_of(blob)
    table = parse(pages)
    table["ages"] = region_ages(pages)
    national = median_from(NATIONAL, table["ages"]["MADAGASCAR"])
    log(f"  the country's median age from the bands: {national} (INSTAT, Tome 1: 18)")
    if not 18 <= national < 19:
        raise SystemExit(f"madagascar_census: the country's median comes to {national}, "
                         f"where INSTAT gives 18")
    records = build(table, units("MDG", "admin1"), units("MDG", "admin2"))
    for r in records:
        log(f"  {r['level']} {r['name']}: {r['population'].get('value')}, ratio "
            f"{r['sex_ratio'].get('value')}, median {r['median_age'].get('value')}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
