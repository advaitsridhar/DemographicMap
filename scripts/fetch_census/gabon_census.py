#!/usr/bin/env python3
"""Gabon -- the 2013 census's resident population by department and sex.

The Direction Générale de la Statistique published the Recensement Général de
la Population et des Logements de 2013 (RGPL-2013) results as *Résultats
globaux* (October 2015). Its Tableau 6 gives the resident population of every
department by sex, each province's departments followed by the province's own
line; Tableau 5 gives the provinces. The statistics office's own copy
(instatgabon.org) now redirects to its home page, so the copy UNFPA Gabon
publishes is the one read.

A line reads ``Libreville 359 688 344 252 703 940 1er 3724,6`` -- men, women,
total, rank in the province, density -- with spaces for thousands, so the
digits are read as the one split into three figures whose first two make the
third.

**Checks.** Every department's men and women make its total; each province's
departments make the province's own line; the provinces make the national
line (1,811,079).

**Polygons.** The boundary file draws 49 departments against the census's 50:
Owendo, made a department of its own before the census, is drawn inside
Komo-Mondah (its town lies inside that polygon, 1 km from the shore), so that
polygon takes both departments' counts and says so. Four names are spelled
otherwise there (Mulundu as Mouloundou, Haut-Como as Haut-Komo, Douigny as
Douigni, Doutsila as Doutsita).

The report gives ages nationally and by residence only (Tableau 7), so no
department or province has a median age from it.

Usage:
    python -m scripts.fetch_census.gabon_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import bind, fold

URL = "https://gabon.unfpa.org/sites/default/files/pub-pdf/Resultats%20Globaux%20RGPL(1).pdf"
YEAR = 2013
OUT = "gabon_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Direction Générale de la Statistique du Gabon, Résultats globaux du Recensement "
          "Général de la Population et des Logements de 2013 (RGPL-2013), Tableau 6")
LICENCE = "Official statistics publication of the Gabonese Republic, as UNFPA Gabon publishes it"
NATIONAL = 1_811_079

PROVINCES = ("ESTUAIRE", "HAUT-OGOOUE", "MOYEN-OGOOUE", "NGOUNIE", "NYANGA", "OGOOUE-IVINDO",
             "OGOOUE-LOLO", "OGOOUE-MARITIME", "WOLEU-N'TEM")
# The census's department names the boundary file spells otherwise.
ALIASES = {"Mulundu": "Mouloundou", "Haut-Como": "Haut-Komo", "Douigny": "Douigni",
           "Doutsila": "Doutsita"}
# Departments drawn inside another department's polygon: census name -> the one it is in.
DRAWN_INSIDE = {"Owendo": "Komo-Mondah"}
RANK = re.compile(r"^\d+(?:er|ère|ème|e)$")
GROUP = re.compile(r"^\d{1,3}$")

AGE_GAP = ("The 2013 census's published results give ages for the whole country and by urban "
           "or rural residence only, not by province or department.")


def three(groups: list[str]) -> tuple[int, int, int] | None:
    """(men, women, total) from digit groups, the one split whose first two make the third."""
    found = []
    n = len(groups)
    for i in range(1, n - 1):
        for j in range(i + 1, n):
            parts = [groups[:i], groups[i:j], groups[j:]]
            if any(any(len(g) != 3 for g in p[1:]) for p in parts):
                continue
            men, women, total = (int("".join(p)) for p in parts)
            if men + women == total:
                found.append((men, women, total))
    return found[0] if len(found) == 1 else None


def rows(text: str) -> list[tuple[str, tuple[int, int, int], bool]]:
    """(name, figures, is a province line) for Tableau 6's lines, in order."""
    out = []
    lines = text.splitlines()
    for k, line in enumerate(lines):
        tokens = line.split()
        if not tokens:
            continue
        i = 0
        while i < len(tokens) and not GROUP.match(tokens[i]):
            i += 1
        name = " ".join(tokens[:i])
        j = i
        while j < len(tokens) and GROUP.match(tokens[j]):
            j += 1
        if not name or j - i < 3:
            continue
        figures = three(tokens[i:j])
        if figures is None:
            continue
        rest = tokens[j:]
        is_province = name.upper() == name and any(c.isalpha() for c in name)
        if is_province and name.endswith("-") and k + 1 < len(lines):
            name = name + lines[k + 1].strip()            # OGOOUE- / MARITIME
        if not is_province and not (rest and RANK.match(rest[0])):
            continue
        out.append((name, figures, is_province))
    return out


def parse(pages: list[str]) -> dict[str, Any]:
    """{"provinces": {name: (m, w, t)}, "departments": {province: {name: (m, w, t)}}}."""
    text = "\n".join(p for p in pages if "Tableau 6" in p and "département" in p.lower())
    out: dict[str, Any] = {"provinces": {}, "departments": {}, "total": None}
    pending: dict[str, tuple[int, int, int]] = {}
    for name, figures, is_province in rows(text):
        if is_province:
            key = next((p for p in PROVINCES if fold(p) == fold(name)), None)
            if fold(name).startswith("totalgabon") or fold(name) == "gabon":
                out["total"] = figures
                continue
            if key is None:
                continue
            out["provinces"][key] = figures
            out["departments"][key] = pending
            pending = {}
        else:
            pending[name] = figures
    if pending:
        raise SystemExit(f"gabon_census: departments with no province line after them: {pending}")
    return out


def check(table: dict[str, Any]) -> list[str]:
    problems = []
    for province, figures in table["provinces"].items():
        deps = table["departments"].get(province, {})
        made = tuple(sum(d[i] for d in deps.values()) for i in range(3))
        if made != figures:
            problems.append(f"{province}: departments make {made}, its line {figures}")
    total = sum(f[2] for f in table["provinces"].values())
    if total != NATIONAL:
        problems.append(f"provinces make {total:,}, not {NATIONAL:,}")
    if len(table["provinces"]) != len(PROVINCES):
        problems.append(f"{len(table['provinces'])} provinces read")
    return problems


def figures_fields(men: int, women: int, total: int, note: str) -> dict[str, Any]:
    return {"population": measure(total, year=YEAR, source=SOURCE), "population_note": note,
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "sex_ratio_note": "Men per 1,000 women among the residents the 2013 census counted.",
            "median_age": gap(NOT_AVAILABLE, AGE_GAP)}


def build(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    cite = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "year": YEAR,
             "license": LICENCE}]
    parents = {u["id"]: u["name"] for u in admin1}
    first = {fold(u["name"]): u for u in admin1}
    records: list[dict[str, Any]] = []
    for province, figures in table["provinces"].items():
        poly = first.get(fold(province.replace("'", "")))
        if poly is None:
            report.append(f"  province {province}: no polygon")
            continue
        men, women, total = figures
        records.append(record(
            f"GAB-RGPL2013-{poly['id']}", poly["name"], level="admin1", parent="GAB",
            country="GAB", match_by="shape_id", shape_id=poly["id"], sources=cite,
            **figures_fields(men, women, total,
                             f"The resident population of {poly['name']} province at the 2013 "
                             f"census.")))
    departments: dict[str, tuple[str, str]] = {}
    counts: dict[str, tuple[int, int, int]] = {}
    for province, deps in table["departments"].items():
        poly = first.get(fold(province.replace("'", "")))
        for name, figures in deps.items():
            counts[name] = figures
            if name in DRAWN_INSIDE:
                continue
            departments[name] = (ALIASES.get(name, name), poly["name"] if poly else "")
    bound, missing = bind(departments, admin2, parents)
    report += [f"  not bound to a polygon: {m}" for m in missing]
    if missing:
        raise SystemExit("gabon_census: departments with no polygon: " + ", ".join(missing))
    inside: dict[str, list[str]] = {}
    for name, host in DRAWN_INSIDE.items():
        if name in counts:
            inside.setdefault(host, []).append(name)
    shapes = {u["id"]: u for u in admin2}
    for name, sid in sorted(bound.items()):
        shape = shapes[sid]
        parts = [name] + inside.get(name, [])
        men, women, total = (sum(counts[p][i] for p in parts) for i in range(3))
        if len(parts) == 1:
            note = f"The resident population of {name} department at the 2013 census."
        else:
            listed = " and ".join(f"{p} ({counts[p][2]:,})" for p in parts)
            note = (f"The resident population at the 2013 census of {listed} departments, added "
                    f"up: {parts[1]} is drawn here inside {name}.")
        records.append(record(f"GAB-RGPL2013-{sid}", shape["name"], level="admin2", parent="GAB",
                              country="GAB", match_by="shape_id", shape_id=sid, sources=cite,
                              **figures_fields(men, women, total, note)))
        report.append(f"  {shape['name']}: {total:,} ({' + '.join(parts)})")
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import pdfplumber                               # noqa: PLC0415
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    log(f"gabon_census: {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    table = parse(pages)
    problems = check(table)
    for p in problems:
        log(f"  check: {p}")
    if problems:
        raise SystemExit("gabon_census: Tableau 6 does not add up as read")
    admin1 = json.loads((SITE / "admin1" / "GAB.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GAB.units.json").read_text())
    records, report = build(table, admin1, admin2)
    for line in report:
        log(line)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} provinces and "
        f"{sum(r['level'] == 'admin2' for r in records)} department polygons written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
