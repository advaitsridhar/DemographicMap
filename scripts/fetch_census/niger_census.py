#!/usr/bin/env python3
"""Niger -- the 2012 census (RGPH 2012): sex by department, age and religion by region.

INS Niger's report *Etat et structure de la population du Niger en 2012*
(RGPH 2012, November 2015) prints:

* Tableau 6 -- the resident population of every region and department by sex
  (63 departments and the four cities with a department's standing: Maradi,
  Tahoua, Zinder and Niamey);
* Tableaux A2 to A4 -- each region's population by sex and five-year age group;
* Tableau A 11 -- each region's population by religion, in counts;
* Tableau 11 -- each region's median age, in whole years.

**What this writes.** The sex ratio of every department and region, a census's
figure in front of OCHA's 2024 projection; the median age and the religion of
every first-level polygon. No population: OCHA's 2024 projections are newer
figures for the same departments, and the regions are their sums.

**Two polygons are two regions.** The boundary file draws Tahoua with Agadez
and Zinder with Diffa as single first-level polygons. Each takes its two
regions' counts added: men and women, every five-year age group, every
religion. Its median age is the median of the added age groups, interpolated
within the group holding the middle person, and so is every other polygon's;
each is checked against the report's whole-year median for its regions.

**Checks before anything is written.** Every department's men and women make
its total; the departments make their region and the regions make the
country's 17,138,707; every region's age groups make its population, for men,
women and both; every region's religions make its population; each median
derived from the age groups is within a year of the report's own.

Usage:
    python -m scripts.fetch_census.niger_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .cod_ps_age import grouped_median

URL = "https://www.stat-niger.org/wp-content/uploads/2020/05/ETAT_STRUCTURE_POPULATION.pdf"
SOURCE = ("Institut National de la Statistique (INS) du Niger, Quatrième Recensement Général de "
          "la Population et de l'Habitat (RGPH 2012), Etat et structure de la population du Niger "
          "en 2012 (2015)")
LICENCE = "INS Niger publication (reuse with attribution)"
YEAR = 2012
NATIONAL = (8_518_818, 8_619_889, 17_138_707)
OUT = "niger_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

REGIONS = ["AGADEZ", "DIFFA", "DOSSO", "MARADI", "TAHOUA", "TILLABERI", "ZINDER", "NIAMEY"]
# The boundary file's first-level polygons, folded -> the census regions in them.
POLYGONS = {"dossa": ["DOSSO"], "dosso": ["DOSSO"], "maradi": ["MARADI"], "niamey": ["NIAMEY"],
            "tahouaagadez": ["TAHOUA", "AGADEZ"], "tillaberi": ["TILLABERI"],
            "zinderdiffa": ["ZINDER", "DIFFA"]}
# The census's department names the boundary file writes otherwise.
DEPARTMENTS = {"tibiridoutchi": "tibiri", "villedemaradi": "maradi", "villedetahoua": "tahouaville",
               "villedezinder": "zinder", "villedeniamey": "niamey"}
RELIGIONS = ["No religion", "Islam", "Christianity", "Animist", "Other religion", "Not stated"]
SHOWN = {"AGADEZ": "Agadez", "DIFFA": "Diffa", "DOSSO": "Dosso", "MARADI": "Maradi",
         "TAHOUA": "Tahoua", "TILLABERI": "Tillabéri", "ZINDER": "Zinder", "NIAMEY": "Niamey"}
AGE_ROW = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*ans\s+(.*)$")
OPEN_ROW = re.compile(r"^\s*85\s*(?:ans\s+et\s+plus|&\s*\+)\s+(.*)$")
TOTAL_ROW = re.compile(r"^\s*Total\s+(.*)$")


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def grouped(chunk: list[str]) -> bool:
    return (bool(chunk) and all(t.isdigit() for t in chunk) and 1 <= len(chunk[0]) <= 3
            and all(len(t) == 3 for t in chunk[1:]))


def triples(tokens: list[str], k: int) -> list[tuple[int, int, int]]:
    """The one way the tokens read as ``k`` (men, women, total) triples, each
    number printed with thousands spaces and each triple adding up."""
    found: list[list[int]] = []

    def walk(i: int, acc: list[int]) -> None:
        if len(found) > 1:
            return
        if len(acc) == 3 * k:
            if i == len(tokens):
                found.append(acc)
            return
        for j in range(i + 1, min(len(tokens), i + 4) + 1):
            chunk = tokens[i:j]
            if not grouped(chunk):
                continue
            nxt = acc + [int("".join(chunk))]
            if len(nxt) % 3 == 0 and nxt[-3] + nxt[-2] != nxt[-1]:
                continue
            walk(j, nxt)

    walk(0, [])
    if len(found) != 1:
        raise SystemExit(f"niger_census: {' '.join(tokens)!r} reads {len(found)} ways as "
                         f"{k} triples")
    acc = found[0]
    return [(acc[i], acc[i + 1], acc[i + 2]) for i in range(0, 3 * k, 3)]


def parse_departments(text: str) -> dict[str, Any]:
    """Tableau 6: {"regions": {region: (m, w, t)}, "departments": {(region, name): (m, w, t)}}."""
    regions: dict[str, tuple[int, int, int]] = {}
    departments: dict[tuple[str, str], tuple[int, int, int]] = {}
    region = None
    seen = False
    # Tableau 6 runs over four pages and repeats its column heads on each;
    # only the first carries the title.
    for page in text.split("\f"):
        if "% Population du pays" not in page or "% Population de la région" not in page:
            continue
        seen = True
        for line in page.splitlines():
            m = re.match(r"^\s*([A-Z][A-Z'’ ()\-]+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.*)$", line)
            if not m:
                continue
            name = " ".join(m.group(1).split())
            men, women, total = int(m.group(2)), int(m.group(3)), int(m.group(4))
            if men + women != total:
                raise SystemExit(f"niger_census: {name}: {men:,} + {women:,} is not {total:,}")
            if name in REGIONS and not m.group(5).strip().endswith("%") \
                    and not name.startswith("VILLE"):
                region = name
                regions[name] = (men, women, total)
            elif region is not None:
                departments[(region, name)] = (men, women, total)
    if not seen:
        raise SystemExit("niger_census: no page carries Tableau 6")
    return {"regions": regions, "departments": departments}


def parse_ages(layout: str) -> dict[str, list[tuple[int, int | None, tuple[int, int, int]]]]:
    """Tableaux A2-A4, laid out: {region: [(low, high, (m, w, t)), ...]} and the
    region's printed totals under "Total"."""
    out: dict[str, list[tuple[int, int | None, tuple[int, int, int]]]] = {}
    for page in layout.split("\f"):
        head = re.search(r"Tableau A[234]\s*:.*?régions?\s+(?:d[’'e]\s*|de\s+)(.+)", page)
        if not head:
            continue
        names = [fold(n) for n in re.split(r",|\bet\b", head.group(1).replace(".", ""))
                 if fold(n)]
        order = []
        for n in names:
            hit = [r for r in REGIONS if fold(r) == n or (n == "tillabery" and r == "TILLABERI")]
            if not hit:
                raise SystemExit(f"niger_census: {head.group(0)!r} names an unknown region {n!r}")
            order.append(hit[0])
        for line in page.splitlines():
            m = AGE_ROW.match(line) or OPEN_ROW.match(line) or TOTAL_ROW.match(line)
            if not m:
                continue
            if m.re is AGE_ROW:
                low, high, rest = int(m.group(1)), int(m.group(2)), m.group(3)
            elif m.re is OPEN_ROW:
                low, high, rest = 85, None, m.group(1)
            else:
                low, high, rest = -1, None, m.group(1)
            for region, figures in zip(order, triples(rest.split(), len(order))):
                out.setdefault(region, []).append((low, high, figures))
    return out


def parse_religion(text: str) -> dict[str, dict[str, int]]:
    """Tableau A 11: {region: {religion: people}}, its total checked."""
    out: dict[str, dict[str, int]] = {}
    for page in text.split("\f"):
        if "Tableau A 11" not in page and "TABLEAU A 11" not in page and "Tableau A11" not in page:
            continue
        for line in page.splitlines():
            m = re.match(r"^\s*([A-Z]+)\s+((?:\d+\s+){6}\d+)\s*$", line)
            if not m or m.group(1) not in REGIONS:
                continue
            values = [int(v) for v in m.group(2).split()]
            if sum(values[:6]) != values[6]:
                raise SystemExit(f"niger_census: {m.group(1)}'s religions make {sum(values[:6]):,}, "
                                 f"not {values[6]:,}")
            out[m.group(1)] = dict(zip(RELIGIONS, values[:6]))
    return out


def parse_published_medians(text: str) -> dict[str, int]:
    """Tableau 11: {region: median age, both sexes, whole years}."""
    out: dict[str, int] = {}
    for page in text.split("\f"):
        if "Tableau 11" not in page:
            continue
        body = page.split("Tableau 11", 1)[1]
        for line in body.splitlines():
            m = re.match(r"^\s*([A-Z]+)\s+((?:\d+\s+){5}\d+)\s*$", line)
            if m and m.group(1) in REGIONS:
                out.setdefault(m.group(1), int(m.group(2).split()[5]))
    return out


def check(table: dict[str, Any], ages: dict[str, Any], religion: dict[str, Any]) -> None:
    if set(table["regions"]) != set(REGIONS):
        raise SystemExit(f"niger_census: Tableau 6 lacks {sorted(set(REGIONS) - set(table['regions']))}")
    made = tuple(sum(v[i] for v in table["regions"].values()) for i in range(3))
    if made != NATIONAL:
        raise SystemExit(f"niger_census: the regions make {made}, not {NATIONAL}")
    for region in REGIONS:
        rows = [v for (r, _), v in table["departments"].items() if r == region]
        made = tuple(sum(v[i] for v in rows) for i in range(3))
        if made != table["regions"][region]:
            raise SystemExit(f"niger_census: {region}'s {len(rows)} departments make {made}")
        groups = [g for g in ages.get(region, []) if g[0] >= 0]
        printed = [g for g in ages.get(region, []) if g[0] < 0]
        if len(groups) != 18 or len(printed) != 1:
            raise SystemExit(f"niger_census: {region} has {len(groups)} age groups")
        made = tuple(sum(g[2][i] for g in groups) for i in range(3))
        if made != printed[0][2] or made != table["regions"][region]:
            raise SystemExit(f"niger_census: {region}'s age groups make {made}, not "
                             f"{table['regions'][region]}")
        if sum(religion[region].values()) != table["regions"][region][2]:
            raise SystemExit(f"niger_census: {region}'s religions do not make its population")


def median_of(regions: list[str], ages: dict[str, Any]) -> float | None:
    groups: dict[tuple[int, int | None], int] = {}
    for region in regions:
        for low, high, figures in ages[region]:
            if low >= 0:
                groups[(low, high)] = groups.get((low, high), 0) + figures[2]
    return grouped_median([(low, high, n) for (low, high), n in sorted(groups.items())])


def build(text: str, layout: str, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    table = parse_departments(text)
    ages = parse_ages(layout)
    religion = parse_religion(text)
    check(table, ages, religion)
    published = parse_published_medians(text)
    for region in REGIONS:
        derived = median_of([region], ages)
        if region in published and (derived is None or abs(derived - published[region]) > 1.0):
            raise SystemExit(f"niger_census: {region}'s median from its age groups is {derived}, "
                             f"the report's {published[region]}")
    src = {"name": SOURCE, "url": URL, "license": LICENCE, "year": YEAR}
    records: list[dict[str, Any]] = []
    report: list[str] = []
    regions_of: dict[str, list[str]] = {}
    for shape in admin1:
        regions = POLYGONS.get(fold(shape["name"]))
        if not regions:
            report.append(f"region polygon {shape['name']!r}: no census region")
            continue
        regions_of[shape["id"]] = regions
        men = sum(table["regions"][r][0] for r in regions)
        women = sum(table["regions"][r][1] for r in regions)
        counts: dict[str, int] = {}
        for r in regions:
            for k, v in religion[r].items():
                counts[k] = counts.get(k, 0) + v
        shown = " and ".join(SHOWN[r] for r in regions)
        both = len(regions) > 1
        median = median_of(regions, ages)
        reported = ", ".join(f"{SHOWN[r]} {published[r]}" for r in regions if r in published)
        median_note = (
            ("The regions of " + shown + " together, as the polygon draws them: the median of "
             "their populations added five-year group by five-year group (Tableaux A2 to A4)"
             if both else "The median of the region's five-year age groups (Tableaux A2 to A4)")
            + ", interpolated within the group holding the middle person; the report gives "
            + reported + " in whole years.")
        records.append(record(
            f"NER-RGPH2012-{fold(shape['name'])}", shape["name"], level="admin1", parent="NER",
            country="NER", match_by="shape_id", shape_id=shape["id"],
            sources=[{**src, "field": "sex_ratio/median_age/religion"}],
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE + ", Tableau 6"),
            sex_ratio_note=(f"The regions of {shown} added together." if both else None),
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
            median_age_note=median_note,
            religion=shares(counts, total=sum(counts.values())), religion_year=YEAR,
            religion_note=("Religion of the resident population as the 2012 census tabulates it "
                           "by region (Tableau A 11), those who gave none counted as not stated"
                           + (f"; the regions of {shown} added together." if both else "."))))
    by_name: dict[tuple[str, str], tuple[str, tuple[int, int, int]]] = {}
    for (region, name), figures in table["departments"].items():
        key = DEPARTMENTS.get(fold(name), fold(name))
        by_name[(region, key)] = (name, figures)
    used: set[tuple[str, str]] = set()
    for shape in admin2:
        regions = regions_of.get(shape.get("parent"), [])
        key = fold(shape["name"])
        hits = [(r, key) for r in regions if (r, key) in by_name]
        if len(hits) != 1 or hits[0] in used:
            report.append(f"department polygon {shape['name']!r}: not bound ({hits})")
            continue
        used.add(hits[0])
        name, (men, women, total) = by_name[hits[0]]
        records.append(record(
            f"NER-RGPH2012-{hits[0][0].lower()}-{key}", shape["name"], level="admin2",
            parent="NER", country="NER", match_by="shape_id", shape_id=shape["id"],
            sources=[{**src, "field": "sex_ratio"}],
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE + ", Tableau 6"),
            sex_ratio_note=(f"The 2012 census counted {men:,} men and {women:,} women in "
                            + (f"the city of {shape['name'].replace(' Ville', '')}."
                               if name.startswith("VILLE DE") else
                               f"the department of {shape['name']}."))))
    left = sorted(f"{r}/{n}" for (r, n) in by_name if (r, n) not in used)
    if left:
        report.append(f"departments not bound: {left}")
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"niger_census: {URL} is not a PDF: {blob[:60]!r}")
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    from pypdf import PdfReader                          # noqa: PLC0415
    import pdfplumber                                    # noqa: PLC0415
    text = "\f".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages)
    layout_pages = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            plain = page.extract_text() or ""
            if re.search(r"Tableau A[234]\s*:", plain):
                layout_pages.append(page.extract_text(layout=True) or "")
    layout = "\f".join(layout_pages)
    admin1 = json.loads((SITE / "admin1" / "NER.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "NER.units.json").read_text())
    records, report = build(text, layout, admin1, admin2)
    for line in report:
        log("  " + line)
    for r in records:
        if r["level"] == "admin1":
            log(f"  {r['name']}: {r['sex_ratio']['value']} men per 1,000 women, median "
                f"{r['median_age']['value']}, {r['religion'][0]['group']} "
                f"{r['religion'][0]['pct']}%")
    n1 = sum(1 for r in records if r["level"] == "admin1")
    n2 = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {n1} first-level polygons and {n2} departments bound")
    if n1 != len(admin1) or n2 != len(admin2) or report:
        raise SystemExit("niger_census: not every polygon was bound")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
