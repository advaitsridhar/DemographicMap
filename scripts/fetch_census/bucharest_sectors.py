#!/usr/bin/env python3
"""Bucharest's six sectors: median age from the population by legal domicile.

The 2021 census's definitive tables give Bucharest's age structure for the city
as a whole (Tabel 1.03) and its sectors' head count and sexes alone (Tabel
1.22, which romania_census.py reads), so no census median exists for a sector.
The one official age table by sector is the Bucharest regional statistics
office's (DRSMB, part of INS): the population by legal domicile on 1 July 2022
by five-year age group and sex, definitive, for the city and each sector. The
median is interpolated within the five-year group that holds the middle person.

Domicile is not usual residence: it counts everyone whose identity card gives
an address in the sector, including people living elsewhere or abroad, and
Bucharest's domicile total (2.16 million) is well above its census count (1.72
million). So the figure is checked before it is used: the city's median by
domicile must lie within a year of the city's median from the census's own
age groups (Tabel 1.03), or nothing is written. The note says what the figure
counts. Head count and sex ratio stay the census's.

The file is read from the Internet Archive's capture, because
bucuresti.insse.ro does not answer from outside Romania.

Usage:
    python -m scripts.fetch_census.bucharest_sectors
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .balkans_common import check_sum, fold, grouped_median, shapes

OUT = "bucharest_sectors.json"
YEAR = 2022
ORIGINAL = ("https://bucuresti.insse.ro/wp-content/uploads/2024/02/"
            "Populatia-dupa-domiciliu-la-1-iulie-2022-pe-grupe-de-varsta-si-sexe.xlsx")
DOMICILE = "https://web.archive.org/web/20240526051610id_/" + ORIGINAL
CENSUS = ("https://web.archive.org/web/20230601175321id_/https://www.recensamantromania.ro/"
          "wp-content/uploads/2023/05/Tabel-1.03_1.3.1-si-1.03.2.xls")
SOURCE = ("Direcția Regională de Statistică a Municipiului București (INS), population by legal "
          "domicile on 1 July 2022 by age group and sex, definitive data")
CENSUS_SOURCE = ("Institutul Național de Statistică, RPL 2021, definitive results, Tabel 1.03 "
                 "(resident population by age group)")
LICENCE = "Institutul Național de Statistică (reuse with attribution)"
TOLERANCE = 1.0
SECTORS = [f"SECTOR {i}" for i in range(1, 7)]


def band(label: str) -> tuple[float, float | None] | None:
    """'0 - 4 ani' -> (0, 5); '85 ani si peste' -> (85, None); anything else None."""
    text = " ".join(str(label or "").split()).lower()
    m = re.match(r"^(\d+)\s*-\s*(\d+)\s*ani", text)
    if m:
        return float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1)
    m = re.match(r"^(\d+)(ani)?sipeste$", fold(text))       # și, şi or si
    if m:
        return float(m.group(1)), None
    return None


def domicile() -> dict[str, dict[str, Any]]:
    """{'MUNICIPIUL BUCURESTI' or 'SECTOR n': {"groups": Counter, "total"}} (both sexes)."""
    import openpyxl
    blob = http_get(DOMICILE, binary=True, timeout=300)
    rows = [list(r) for r in openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                                    data_only=True).worksheets[0].iter_rows(values_only=True)]
    head = next(i for i, r in enumerate(rows) if any("SECTOR 1" == str(c or "").strip() for c in r))
    # Each place heads three columns: total, men, women.
    cols = {fold(c): j for j, c in enumerate(rows[head]) if c and str(c).strip()}
    places: dict[str, int] = {}
    for name in ["MUNICIPIUL BUCUREȘTI"] + SECTORS:
        j = cols.get(fold(name))
        if j is None:
            raise SystemExit(f"bucharest_sectors: no column for {name} in {rows[head]}")
        places["MUNICIPIUL BUCURESTI" if name.startswith("MUNICIPIUL") else name] = j
    out = {p: {"groups": Counter(), "total": None} for p in places}
    for r in rows[head + 2:]:
        label = str(r[0] or "").strip()
        if label.upper().startswith("TOTAL"):
            for p, j in places.items():
                out[p]["total"] = float(r[j])
            continue
        b = band(label)
        if b is None:
            continue
        for p, j in places.items():
            out[p]["groups"][b] += float(r[j] or 0)
    for p, unit in out.items():
        check_sum(sum(unit["groups"].values()), unit["total"], f"bucharest_sectors: ages of {p}")
    for b in out["MUNICIPIUL BUCURESTI"]["groups"]:
        check_sum(sum(out[s]["groups"][b] for s in SECTORS), out["MUNICIPIUL BUCURESTI"]["groups"][b],
                  f"bucharest_sectors: sectors against the city at {b}")
    return out


def census_city_median() -> float:
    """The city's median from the census's own age groups (Tabel 1.03)."""
    import xlrd
    blob = http_get(CENSUS, binary=True, timeout=300)
    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(1)
    rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
    head = next(i for i, r in enumerate(rows) if any(re.match(r"^\s*0\s*-\s*4", str(c)) for c in r))
    bands = []
    for j, c in enumerate(rows[head]):
        text = " ".join(str(c).split()).lower()
        m = re.match(r"^(\d+)\s*-\s*(\d+)", text)
        top = re.match(r"^(\d+)(ani)?sipeste$", fold(text))   # și, şi or si
        if m:
            bands.append((j, float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1)))
        elif top:
            bands.append((j, float(top.group(1)), None))
    if bands and bands[-1][2] is not None:
        # The open top group's label can run over the header's rows ("85" above
        # "ani si peste"): it is the column after the last closed group.
        j, lo, w = bands[-1]
        bands.append((j + 1, lo + w, None))
    row = next(r for r in rows if fold(r[0]) == "municipiulbucuresti")
    total = float(row[1])
    groups = [(lo, w, float(row[j] or 0)) for j, lo, w in bands]
    check_sum(sum(n for _, _, n in groups), total, "bucharest_sectors: the census city's age groups")
    return grouped_median(groups)


def build() -> list[dict[str, Any]]:
    dom = domicile()
    city_dom = grouped_median([(lo, w, n) for (lo, w), n in dom["MUNICIPIUL BUCURESTI"]["groups"].items()])
    city_census = census_city_median()
    log(f"  Bucharest: median {city_dom} by domicile (1 July 2022), {city_census} from the 2021 "
        f"census's residents")
    if abs(city_dom - city_census) > TOLERANCE:
        raise SystemExit(f"bucharest_sectors: the domicile median {city_dom} is more than "
                         f"{TOLERANCE} year from the census's {city_census}; not a stand-in for it")
    polys = {fold(s["name"]): s for s in shapes("ROU", "admin2") if fold(s["name"]).startswith("sector")}
    records = []
    for sector in SECTORS:
        shape = polys.get(fold(sector))
        if shape is None:
            raise SystemExit(f"bucharest_sectors: no polygon named {sector}")
        unit = dom[sector]
        median = grouped_median([(lo, w, n) for (lo, w), n in unit["groups"].items()])
        note = ("Interpolated within the five-year age group that holds the middle person, from "
                "DRSMB's population by legal domicile on 1 July 2022 by age group (definitive): the "
                "2021 census publishes Bucharest's ages for the city as a whole only. Domicile "
                f"counts everyone registered in the sector, {unit['total']:,.0f} people here, "
                "including those living elsewhere, not the census's usual residents; for the city "
                f"as a whole it gives a median of {city_dom} against the census's {city_census}.")
        records.append(record(
            f"ROU-domicile-2022-{fold(sector)}", shape["name"], level="admin2", parent="ROU",
            country="ROU", match_by="shape_id", shape_id=shape["id"],
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
            median_age_note=note,
            sources=[{"field": "median_age", "name": SOURCE, "url": DOMICILE, "page": ORIGINAL,
                      "year": YEAR, "license": LICENCE},
                     {"field": "median_age", "name": CENSUS_SOURCE, "url": CENSUS, "year": 2021,
                      "license": LICENCE, "note": "the city's median, the check"}]))
        log(f"  {sector}: {unit['total']:,.0f} by domicile, median {median}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("bucharest_sectors: DRSMB's population by domicile, 1 July 2022")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
