#!/usr/bin/env python3
"""Ecuador's provinces and cantons: median age and sex ratio, 2022 census.

The same INEC workbook ecuador_census.py reads for the count
("01_2022_CPV_Estructura_poblacional.xlsx", from the Internet Archive's
capture, since INEC's host refuses an automated reader) has, in sheet 2.1,
everyone by sex and five-year age group for every province, canton and
parish. A province's rows name "Total <province>" as their canton; a canton's
name "Total <canton>" as their parish.

- **sex ratio**: men per 1,000 women, from the unit's own total row;
- **median age**: interpolated within the five-year group holding the middle
  person, the open-ended "85 o más" never holding it.

Every unit's age groups must add up to its total row, men and women
separately, and every province's cantons must add up to the province, before
anything is written. Units are named as ecuador_census.py names them, so the
two files reach the same shapes.

Usage:
    python -m scripts.fetch_census.ecuador_profile
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .cod_ps_age import grouped_median
from .ecuador_census import CAPTURE, ORIGINAL, YEAR, fetch_blob, fold
from common import slugify  # noqa: E402

OUT = PROCESSED / "ecuador_profile.json"
SHEET = "2.1"
SOURCE = ("INEC, Censo de Población y Vivienda 2022, Estructura poblacional, tabla 2.1 "
          "(población por sexo al nacer y grupos de edad)")
BAND = re.compile(r"^De (\d+)-(\d+)$")
OPEN = re.compile(r"^(\d+) o más$")


def rows_of(blob: bytes) -> list[list[str]]:
    import io

    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return [["" if c is None else str(c).strip() for c in row]
            for row in book[SHEET].iter_rows(values_only=True)]


def units(rows: list[list[str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(province, canton or "") -> total row and age groups, by sex.

    Parishes are read past: the map draws cantons.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if len(row) < 8 or not row[7].replace(".", "").isdigit():
            continue
        province, canton, parish, label = row[1], row[2], row[3], row[4]
        if fold(province) == "total nacional":
            continue
        if fold(canton) == fold(f"Total {province}"):
            key = (province, "")
        elif fold(parish) == fold(f"Total {canton}"):
            key = (province, canton)
        else:
            continue
        unit = out.setdefault(key, {"total": None, "groups": []})
        men, women = int(float(row[6])), int(float(row[7]))
        if label.startswith("Total"):
            unit["total"] = (men, women)
        elif m := BAND.match(label):
            unit["groups"].append((int(m.group(1)), int(m.group(2)), men, women))
        elif m := OPEN.match(label):
            unit["groups"].append((int(m.group(1)), None, men, women))
        else:
            raise SystemExit(f"ecuador_profile: unread age group {label!r}")
    return out


def figures(unit: dict[str, Any], where: str) -> tuple[float, int]:
    if unit["total"] is None:
        raise SystemExit(f"ecuador_profile: {where} has no total row")
    men, women = unit["total"]
    groups = sorted(unit["groups"], key=lambda g: g[0])
    edge = 0
    for low, high, *_ in groups:
        if low != edge:
            raise SystemExit(f"ecuador_profile: {where}: ages jump from {edge} to {low}")
        edge = (high or 0) + 1
    if groups[-1][1] is not None:
        raise SystemExit(f"ecuador_profile: {where}: no open-ended last group")
    if (sum(g[2] for g in groups), sum(g[3] for g in groups)) != (men, women):
        raise SystemExit(f"ecuador_profile: {where}: age groups do not add up to the total")
    median = grouped_median([(low, high, m + w) for low, high, m, w in groups])
    if median is None:
        raise SystemExit(f"ecuador_profile: {where}: median in the open-ended group")
    return median, round(1000 * men / women)


def build(rows: list[list[str]]) -> list[dict[str, Any]]:
    found = units(rows)
    provinces = {p for p, c in found if not c}
    cantons: dict[str, list[str]] = defaultdict(list)
    for province, canton in found:
        if canton:
            cantons[province].append(canton)
    for province in provinces:
        total = found[(province, "")]["total"]
        summed = tuple(map(sum, zip(*(found[(province, c)]["total"] for c in cantons[province]))))
        if summed != total:
            raise SystemExit(f"ecuador_profile: {province}'s cantons make {summed}, not {total}")
    log(f"  {len(provinces)} provinces and {sum(map(len, cantons.values()))} cantons; "
        "every one's age groups make its total, and every province's cantons make it")
    cite = [{"field": "median_age/sex_ratio", "name": SOURCE, "url": ORIGINAL,
             "archived": CAPTURE}]
    note = ("Interpolated within the five-year age group that holds the middle person, from "
            "INEC's count of everyone by sex and age.")
    out = []
    for province in sorted(provinces):
        name = province.title() if province.isupper() else province
        median, ratio = figures(found[(province, "")], province)
        out.append(record(
            f"ECU-CEN-{slugify(name)}-AGE", name, level="admin1", parent="ECU", country="ECU",
            median_age={"value": median, "unit": "years", "year": YEAR, "source": SOURCE},
            median_age_note=note,
            sex_ratio={"value": ratio, "unit": "males_per_1000_females", "year": YEAR,
                       "source": SOURCE},
            sources=cite))
        for canton in sorted(cantons[province]):
            label = canton.title() if canton.isupper() else canton
            median, ratio = figures(found[(province, canton)], f"{province} / {canton}")
            out.append(record(
                f"ECU-CEN-{slugify(name)}-{slugify(label)}-AGE", label, level="admin2",
                parent="ECU", country="ECU", parent_name=name, aliases=[f"Cantón {label}"],
                median_age={"value": median, "unit": "years", "year": YEAR, "source": SOURCE},
                median_age_note=note,
                sex_ratio={"value": ratio, "unit": "males_per_1000_females", "year": YEAR,
                           "source": SOURCE},
                sources=cite))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    blob = fetch_blob(CAPTURE)
    log(f"  {CAPTURE}: {len(blob):,} bytes")
    write_json(OUT, build(rows_of(blob)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
