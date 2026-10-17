#!/usr/bin/env python3
"""Tunisia -- the 2024 census by governorate and delegation: people, ages, sexes.

The Institut National de la Statistique took the Recensement Général de la
Population et de l'Habitat on 6 November 2024 and published, with its first
results in May 2025, a workbook of the whole population by secteur (imada),
sex and five-year age group: every sector with its delegation and governorate,
by code and by name in French and Arabic (sheet ``Population``, one row per
sector, sex and age group). Added up, that is every delegation and every
governorate: the head count, men per 1,000 women, and the median age
interpolated within the five-year group holding the middle person.

**Checks before anything is written.** Every row is one sector, one sex and
one age group, the groups running from 0 without a gap to an open last group;
the sectors make the national count INS announced, 11,972,169; each
delegation sits in one governorate.

**Binding.** The map's first level is the 24 governorates, labelled in French;
its second the 264 delegations of the 2014 census, labelled mostly in Arabic
and a few in French, some with stray direction marks and Persian letters. A
delegation is matched within its governorate on its Arabic or its French name,
both folded (hamza forms, ta marbuta, alef maqsura and Persian letters read as
the Arabic letter, marks and spaces dropped), then on the closest spelling
where each is the other's best. Delegations INS counts that the map does not
draw (``CARVED``: created since 2014 out of one drawn delegation) are added to
the polygon of the delegation they came from, age group by age group, and say
so. Everything left over is logged, both sides.

Usage:
    python -m scripts.fetch_census.tunisia_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

URL = ("https://www.ins.tn/sites/default/files-ftp3/files/2025-05/"
       "Population_Secteur_Age_Sexe_Dynamique.xlsx")
LANDING = ("https://www.ins.tn/enquetes/"
           "recensement-general-de-la-population-et-de-lhabitat-2024")
SOURCE = ("Institut National de la Statistique (INS), Recensement Général de la Population "
          "et de l'Habitat 2024, répartition de la population totale par secteur, âge et sexe")
LICENCE = "INS publication (reuse with attribution)"
YEAR = 2024
NATIONAL = 11_972_169
OUT = "tunisia_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# INS's French governorate name, folded -> the map's label, where folding
# alone does not join them.
GOVERNORATES = {"lekef": "El Kef", "mannouba": "Manouba", "jandouba": "Jendouba",
                "zaghouane": "Zaghouan", "mednine": "Médenine"}
# Delegations INS counts that the map does not draw, created since 2014 out of
# one delegation it does draw: (governorate code, INS delegation code) -> the
# INS delegation code whose polygon holds it. Filled from the run's log.
CARVED: dict[tuple[str, str], str] = {}
# INS's delegation (governorate code, delegation code) -> the map's label,
# where neither name folds to the label and no spelling is close enough.
DELEGATIONS: dict[tuple[str, str], str] = {}
# A pair left over is bound on its closest spelling at this similarity or more.
SPELLING = 0.82
AGE = re.compile(r"^\s*(\d{1,3})\s*-\s*(\d{1,3})\s*$")
OPEN = re.compile(r"^\s*(\d{1,3})\s*(?:\+|ans?\s*et\s*plus|et\s*\+|et\s*plus)\s*$", re.I)
ARABIC = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي",
                        "ی": "ي", "ک": "ك", "ؤ": "و", "ئ": "ي", "ـ": None})


def fold(text: Any) -> str:
    """A name reduced to its letters: accents, marks, direction controls and
    spaces dropped; Arabic hamza forms, ta marbuta, alef maqsura and Persian
    letters read as the plain Arabic letter."""
    raw = unicodedata.normalize("NFKD", str(text or "")).translate(ARABIC)
    out = "".join(c for c in raw.lower()
                  if c.isalnum() and not unicodedata.combining(c)
                  and unicodedata.category(c) != "Cf")
    return re.sub(r"(.)\1+", r"\1", out)


def latin(text: Any) -> str:
    """The French name without 'Délégation de' and its kind words."""
    name = re.sub(r"(?i)^\s*d[ée]l[ée]gation\s+d[e']\s*", "", str(text or ""))
    return fold(name)


def number(cell: Any) -> int:
    if cell is None or cell == "":
        return 0
    if isinstance(cell, (int, float)):
        return int(round(cell))
    text = re.sub(r"[\s  ,]", "", str(cell))
    return int(float(text)) if text else 0


def bounds(label: str) -> tuple[int, int | None]:
    if m := AGE.match(label):
        return int(m.group(1)), int(m.group(2))
    if m := OPEN.match(label):
        return int(m.group(1)), None
    raise SystemExit(f"tunisia_census: an age group reads {label!r}")


def grouped_median(groups: list[tuple[int, int | None, int]]) -> float | None:
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def read(rows: list[list[Any]]) -> dict[str, Any]:
    """{"governorates": {code: unit}, "delegations": {code: unit}, "groups": [...]}."""
    header = [str(c or "").strip() for c in rows[0]]
    at = {h: i for i, h in enumerate(header)}
    need = ("Code_Gouvernorat", "Gouvernorat", "الولاية", "Code_Delegation", "Délégations",
            "المعتمدية", "ID_Sexe", "Tranche d'âge", "Population")
    missing = [n for n in need if n not in at]
    if missing:
        raise SystemExit(f"tunisia_census: the sheet has no {missing}; it has {header}")
    govs: dict[str, dict[str, Any]] = {}
    dels: dict[str, dict[str, Any]] = {}
    labels: set[str] = set()
    total = 0
    for row in rows[1:]:
        cells = list(row) + [None] * len(header)
        gcode = str(cells[at["Code_Gouvernorat"]] or "").strip()
        dcode = str(cells[at["Code_Delegation"]] or "").strip()
        if not gcode or not dcode:
            continue
        sex = str(cells[at["ID_Sexe"]] or "").strip().upper()
        if sex not in ("M", "F"):
            raise SystemExit(f"tunisia_census: a row's sex reads {sex!r}")
        label = str(cells[at["Tranche d'âge"]] or "").strip()
        labels.add(label)
        people = number(cells[at["Population"]])
        total += people
        for table, code, fr, ar in ((govs, gcode, "Gouvernorat", "الولاية"),
                                     (dels, dcode, "Délégations", "المعتمدية")):
            unit = table.setdefault(code, {"code": code, "fr": str(cells[at[fr]] or "").strip(),
                                           "ar": str(cells[at[ar]] or "").strip(),
                                           "gov": gcode, "M": 0, "F": 0,
                                           "ages": defaultdict(int)})
            if table is dels and unit["gov"] != gcode:
                raise SystemExit(f"tunisia_census: delegation {code} sits in governorates "
                                 f"{unit['gov']} and {gcode}")
            unit[sex] += people
            unit["ages"][label] += people
    groups = sorted({bounds(lab) + (lab,) for lab in labels}, key=lambda g: g[0])
    edge = 0
    for low, high, lab in groups:
        if low != edge:
            raise SystemExit(f"tunisia_census: the age groups do not run from 0 without a "
                             f"gap: {[g[2] for g in groups]}")
        edge = high + 1 if high is not None else None
    if groups[-1][1] is not None:
        raise SystemExit("tunisia_census: no open-ended last age group")
    if total != NATIONAL:
        raise SystemExit(f"tunisia_census: the sectors make {total:,}, not INS's {NATIONAL:,}")
    for table in (govs, dels):
        for unit in table.values():
            unit["total"] = unit["M"] + unit["F"]
            unit["groups"] = [(lo, hi, unit["ages"].get(lab, 0)) for lo, hi, lab in groups]
    return {"governorates": govs, "delegations": dels, "groups": groups}


def figures(unit: dict[str, Any]) -> dict[str, Any]:
    return {"median": grouped_median(unit["groups"]),
            "ratio": round(1000 * unit["M"] / unit["F"]) if unit["F"] else None}


def merge(units: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"M": sum(u["M"] for u in units), "F": sum(u["F"] for u in units)}
    out["total"] = out["M"] + out["F"]
    out["groups"] = [(lo, hi, sum(u["groups"][i][2] for u in units))
                     for i, (lo, hi, _) in enumerate(units[0]["groups"])]
    return out


def bind_governorates(govs: dict[str, dict[str, Any]], admin1: list[dict[str, Any]]
                      ) -> dict[str, dict[str, Any]]:
    by_fold = {fold(s["name"]): s for s in admin1}
    bound: dict[str, dict[str, Any]] = {}
    for code, unit in govs.items():
        key = latin(unit["fr"])
        shape = by_fold.get(key) or by_fold.get(fold(GOVERNORATES.get(key, "")))
        if shape is None:
            raise SystemExit(f"tunisia_census: no governorate polygon for {unit['fr']!r}")
        if shape["id"] in {s["id"] for s in bound.values()}:
            raise SystemExit(f"tunisia_census: two governorates on {shape['name']!r}")
        bound[code] = shape
    if len(bound) != len(admin1):
        raise SystemExit(f"tunisia_census: {len(bound)} governorates for {len(admin1)} polygons")
    return bound


def bind_delegations(dels: dict[str, dict[str, Any]], admin2: list[dict[str, Any]],
                     govs: dict[str, dict[str, Any]], report: list[str]
                     ) -> dict[str, list[str]]:
    """Polygon id -> the INS delegation codes it holds."""
    held: dict[str, list[str]] = {}
    carved = {d for (_, d) in CARVED}
    for gcode, gshape in govs.items():
        shapes = [s for s in admin2 if s["parent"] == gshape["id"]]
        mine = {c: u for c, u in dels.items() if u["gov"] == gcode and c not in carved}
        free = {s["id"]: s for s in shapes}
        left: dict[str, dict[str, Any]] = {}
        for code, unit in sorted(mine.items()):
            label = DELEGATIONS.get((gcode, code))
            keys = {fold(label)} if label else {fold(unit["ar"]), latin(unit["fr"])}
            hits = [s for s in free.values() if fold(s["name"]) in keys]
            if len(hits) == 1:
                held[hits[0]["id"]] = [code]
                del free[hits[0]["id"]]
            else:
                left[code] = unit
        # Leftovers on both sides of one governorate: the closest spellings,
        # each the other's best.
        def ratio(unit: dict[str, Any], shape: dict[str, Any]) -> float:
            name = fold(shape["name"])
            return max(SequenceMatcher(None, fold(unit["ar"]), name).ratio(),
                       SequenceMatcher(None, latin(unit["fr"]), name).ratio())
        for code, unit in sorted(left.items()):
            if not free:
                break
            best = max(free.values(), key=lambda s: ratio(unit, s))
            back = max(left.values(), key=lambda u: ratio(u, best))
            if ratio(unit, best) >= SPELLING and back is unit:
                report.append(f"  {gshape['name']}: {unit['fr']} / {unit['ar']} bound to "
                              f"{best['name']!r} by spelling ({ratio(unit, best):.2f})")
                held[best["id"]] = [code]
                del free[best["id"]]
            else:
                report.append(f"  {gshape['name']}: delegation {code} {unit['fr']} / "
                              f"{unit['ar']} ({unit['M'] + unit['F']:,}) has no polygon")
        for shape in free.values():
            report.append(f"  {gshape['name']}: polygon {shape['name']!r} has no delegation")
    for (gcode, code), into in CARVED.items():
        host = next((sid for sid, codes in held.items() if into in codes), None)
        if host is None:
            raise SystemExit(f"tunisia_census: {code} is declared carved from {into}, "
                             "which is bound to no polygon")
        held[host].append(code)
    return held


def build(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    govs = bind_governorates(table["governorates"], admin1)
    records = []
    sources = [{"field": "population/median_age/sex_ratio", "name": SOURCE, "url": LANDING,
                "license": LICENCE, "year": YEAR}]
    for code, shape in sorted(govs.items()):
        unit = table["governorates"][code]
        records.append(unit_record(f"TUN-RGPH2024-{code}", shape, "admin1", unit, sources,
                                   f"the governorate of {unit['fr']}"))
    held = bind_delegations(table["delegations"], admin2, govs, report)
    labels = {s["id"]: s for s in admin2}
    for sid, codes in sorted(held.items()):
        units = [table["delegations"][c] for c in codes]
        unit = units[0] if len(units) == 1 else merge(units)
        what = (f"the delegation of {units[0]['fr']}" if len(units) == 1 else
                f"the delegation of {units[0]['fr']} as drawn in 2014, which the 2024 census "
                f"counts as {', '.join(u['fr'] for u in units[:-1])} and {units[-1]['fr']}")
        records.append(unit_record(f"TUN-RGPH2024-{'-'.join(codes)}", labels[sid], "admin2",
                                   unit, sources, what))
    return records, report


def unit_record(rid: str, shape: dict[str, Any], level: str, unit: dict[str, Any],
                sources: list[dict[str, Any]], what: str) -> dict[str, Any]:
    f = figures(unit)
    return record(
        rid, shape["name"], level=level, parent="TUN", country="TUN",
        match_by="shape_id", shape_id=shape["id"],
        population=measure(unit["total"], year=YEAR, source=SOURCE),
        population_note=(f"The 2024 census count of {what}: {unit['M']:,} men and "
                         f"{unit['F']:,} women."),
        median_age=measure(f["median"], unit="years", year=YEAR, source=SOURCE)
        if f["median"] is not None else None,
        median_age_note=("Interpolated within the five-year age group that holds the middle "
                         "person, from the 2024 census's count of everyone by five-year age "
                         "group."),
        sex_ratio=measure(f["ratio"], unit="males_per_1000_females", year=YEAR, source=SOURCE)
        if f["ratio"] is not None else None,
        sources=sources)


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl                                 # noqa: PLC0415
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    if blob[:2] != b"PK":
        raise SystemExit(f"tunisia_census: {URL} is not a workbook: {blob[:80]!r}")
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    if "Population" not in book.sheetnames:
        raise SystemExit(f"tunisia_census: no sheet 'Population': {book.sheetnames}")
    rows = [list(r) for r in book["Population"].iter_rows(values_only=True)]
    table = read(rows)
    log(f"  {len(table['governorates'])} governorates, {len(table['delegations'])} "
        f"delegations; age groups {[g[2] for g in table['groups']]}")
    for code, unit in sorted(table["delegations"].items()):
        f = figures(unit)
        log(f"  {unit['gov']} {code} {unit['fr']} | {unit['ar']} | {unit['total']:,} | "
            f"median {f['median']} | men/1000 women {f['ratio']}")
    admin1 = json.loads((SITE / "admin1" / "TUN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TUN.units.json").read_text())
    records, report = build(table, admin1, admin2)
    for line in report:
        log(line)
    bound = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} governorates and {bound} of "
        f"{len(admin2)} delegation polygons bound")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
