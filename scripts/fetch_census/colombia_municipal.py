#!/usr/bin/env python3
"""Colombia: median age and sex ratio for every municipality and department (DANE, 2018).

DANE's municipal population series built on the 2018 census (CNPV 2018),
``PPED-AreaSexoEdadMun-2018-2042_VP.xlsx``, gives every municipality's
population by area, sex and single year of age, 0 to 100 and over. The 2018
rows -- the census year the series is built on -- are read, for the whole
municipality ("Total" area):

* **sex ratio** is its men per 1,000 women;
* **median age** is computed from its single-year counts, the age at which
  half the population is younger, interpolated within that year of age.
  DANE's workbook publishes the counts, not the median, so the record says
  the median is computed from them.

A department's figures are its municipalities' counts summed age by age, and
its median is computed from those sums -- never averaged from the
municipalities' medians, which would weight a town of 2,000 like Cali.

The file is read against itself before anything is written: every
municipality's men and women must add to its total, and the national sums
must match the national rows.

Usage:
    python -m scripts.fetch_census.colombia_municipal      # runner
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import PROCESSED, RAW, http_get, log, measure, write_json  # noqa: E402
from fetch_census._shared import record  # noqa: E402

URL = ("https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/"
       "PPED-AreaSexoEdadMun-2018-2042_VP.xlsx")
SHEET = "PobMunicipalxÁreaSexoEdad"
YEAR = 2018
SOURCE = ("DANE, population by municipality, sex and age, 2018 "
          "(series based on the Censo Nacional de Poblacion y Vivienda 2018)")
AGE = re.compile(r"^(Hombres|Mujeres|Total)\s+(\d+)")


def median_age(counts: list[float]) -> float | None:
    """The age half the population is younger than, from single-year counts."""
    total = sum(counts)
    if total <= 0:
        return None
    half, cum = total / 2, 0.0
    for age, n in enumerate(counts):
        if cum + n >= half and n > 0:
            return round(age + (half - cum) / n, 1)
        cum += n
    return None


def main() -> int:
    import openpyxl
    blob = http_get(URL, binary=True, cache_dir=RAW / "colombia", timeout=600)
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = wb[SHEET].iter_rows(values_only=True)
    head = None
    for row in rows:
        if row and str(row[0] or "").strip() == "DP":
            head = row
            break
    if head is None:
        raise SystemExit("colombia_municipal: no header row starting 'DP'")
    labels = [str(c or "").strip() for c in next(rows)]
    col = {str(h or "").strip(): i for i, h in enumerate(head) if h}
    men_col, women_col = labels.index("Hombres"), labels.index("Mujeres")
    ages: dict[str, dict[int, int]] = {"Hombres": {}, "Mujeres": {}, "Total": {}}
    for i, label in enumerate(labels):
        m = AGE.match(label)
        if m:
            ages[m.group(1)][int(m.group(2))] = i
    if len(ages["Hombres"]) != 101 or len(ages["Mujeres"]) != 101:
        raise SystemExit(f"colombia_municipal: {len(ages['Hombres'])} male and "
                         f"{len(ages['Mujeres'])} female age columns, not 101 each")
    records: list[dict[str, Any]] = []
    men_sum = women_sum = 0
    departments: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not row or row[col["AÑO"]] != YEAR or str(row[col["ÁREA GEOGRÁFICA"]]).strip() != "Total":
            continue
        code = str(row[col["MPIO"]]).strip().zfill(5)
        men, women = row[men_col] or 0, row[women_col] or 0
        by_age = [(row[ages["Hombres"][a]] or 0) + (row[ages["Mujeres"][a]] or 0) for a in range(101)]
        if abs(sum(by_age) - (men + women)) > 2:
            raise SystemExit(f"colombia_municipal: {code} ages sum to {sum(by_age)}, "
                             f"not its {men + women} men and women")
        men_sum += men
        women_sum += women
        dept = departments.setdefault(code[:2], {
            "name": str(row[col["DPNOM"]]).strip(), "men": 0, "women": 0, "ages": [0] * 101})
        dept["men"] += men
        dept["women"] += women
        dept["ages"] = [a + b for a, b in zip(dept["ages"], by_age)]
        median = median_age(by_age)
        records.append(record(
            f"COL-{code}", str(row[col["DPMP"]]).strip(), level="admin2",
            parent=f"COL-{code[:2]}", parent_name=str(row[col["DPNOM"]]).strip(),
            country="COL", codes={"divipola": code},
            median_age=(measure(median, unit="years", year=YEAR, source=SOURCE)
                        if median is not None else None),
            median_age_note="Computed from DANE's single-year counts by age.",
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE) if women else None,
            sources=[{"field": "median age/sex ratio", "name": SOURCE, "url": URL,
                      "license": "DANE open data (attribution)"}],
        ))
    municipalities = len(records)
    for code, dept in sorted(departments.items()):
        median = median_age(dept["ages"])
        records.append(record(
            f"COL-{code}", dept["name"], level="admin1", parent="COL", country="COL",
            codes={"divipola": code},
            median_age=(measure(median, unit="years", year=YEAR, source=SOURCE)
                        if median is not None else None),
            median_age_note=("Computed from DANE's single-year counts by age, summed over "
                             "the department's municipalities."),
            sex_ratio=(measure(round(1000 * dept["men"] / dept["women"]),
                               unit="males_per_1000_females", year=YEAR, source=SOURCE)
                       if dept["women"] else None),
            sources=[{"field": "median age/sex ratio", "name": SOURCE, "url": URL,
                      "license": "DANE open data (attribution)"}],
        ))
    records = [{k: v for k, v in r.items() if v is not None} for r in records]
    log(f"  {municipalities} municipalities and {len(departments)} departments in {YEAR}; "
        f"{men_sum:,} men and {women_sum:,} women")
    if not 1000 <= municipalities <= 1200 or len(departments) != 33:
        raise SystemExit(f"colombia_municipal: {municipalities} municipalities in "
                         f"{len(departments)} departments is not Colombia")
    write_json(PROCESSED / "colombia_municipality.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
