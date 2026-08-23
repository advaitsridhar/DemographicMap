#!/usr/bin/env python3
"""Sri Lanka -- Census of Population and Housing 2024, by district and province.

The Department of Census and Statistics publishes the district tables as small
trilingual workbooks rather than through an API, so they live in
``data/raw/srilanka/`` and are read from disk:

* ``A1`` population by sex and age
* ``A2`` population by ethnicity
* ``A3`` population by religion

Three things about these sheets shape how they are read.

**Every label is trilingual.** A district cell reads
``"නුවරඑළිය நுவெரலியா Nuwara Eliya"`` -- Sinhala, Tamil and English run
together in one string. The English is the only ASCII in it, which makes
extracting it a filter rather than a guess.

**Each district occupies two rows**: counts, then the census's own published
percentages. Only the counts are used, but the percentages are not ignored --
:func:`check_published_shares` recomputes every share from the counts and
requires it to agree with what the Department printed beside it. That is a check
the source hands you for free, and it is independent of any total this adapter
computes, so it catches a column read one place to the left in a way that
summing to 100% never would.

**Provinces are not in these tables.** The nine provinces are summed from their
districts, which is arithmetic on official counts rather than estimation, and
the sums are required to reproduce the national totals exactly.

Sri Lanka does not ask mother tongue, so ``language`` is marked *not collected*
rather than merely missing. What the census asks instead is literacy: the
ability to speak, read and write Sinhala, Tamil and English, for people aged 10
and over, explicitly not accounting for any other language. Those are
overlapping proficiencies rather than shares of a population, so they are not a
composition, and they are not a substitute for one. Nor is language inferred
from ethnicity here -- most Sri Lankan Moors speak Tamil, which would put a
tenth of the country in the wrong column.

Usage:
    python -m scripts.fetch_census.sri_lanka --level district
    python -m scripts.fetch_census.sri_lanka --level province
"""

from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, log, measure, record, shares, write_json,
)

WORKBOOKS = RAW / "srilanka"
SOURCE = ("Census of Population and Housing 2024, Department of Census and "
          "Statistics, Sri Lanka")
CATALOG = "https://www.statistics.gov.lk/"

# Column positions, which the three-row trilingual banner makes worth naming.
A1_TOTAL, A1_MALE, A1_FEMALE = 3, 4, 5
FIRST_CATEGORY = 2          # A2 and A3: category counts start here
A2_TOTAL = A3_TOTAL = 1

# The Department's labels, tidied for display. Its own spelling of "Sinhalees"
# and "Sri lanka Tamil" is kept faithful in meaning but not in typo.
ETHNIC_LABELS = {
    "Sinhalees": "Sinhalese",
    "Sri lanka Tamil": "Sri Lankan Tamil",
    "Indian Tamil  Malaiyaga Thamilar": "Indian Tamil",
    "Sri Lanka Moor Muslim": "Sri Lankan Moor",
    "Sri Lanka Chetty": "Sri Lankan Chetty",
    "Veddhas": "Vedda",
}

# The nine provinces, and the districts the Department reports under each.
PROVINCES = {
    "Western": ["Colombo", "Gampaha", "Kalutara"],
    "Central": ["Kandy", "Matale", "Nuwara Eliya"],
    "Southern": ["Galle", "Matara", "Hambantota"],
    "Northern": ["Jaffna", "Kilinochchi", "Mannar", "Vavuniya", "Mullaitivu"],
    "Eastern": ["Batticaloa", "Ampara", "Trincomalee"],
    "North Western": ["Kurunegala", "Puttalam"],
    "North Central": ["Anuradhapura", "Polonnaruwa"],
    "Uva": ["Badulla", "Moneragala"],
    "Sabaragamuwa": ["Ratnapura", "Kegalle"],
}

# The boundary files spell one district differently from the census.
DISTRICT_ALIASES = {"Moneragala": "Monaragala"}

# The national row of these same workbooks, pinned so a different file cannot be
# swapped in unnoticed. This is a regression guard, not independent validation:
# unlike the India controls, which are figures the Registrar General published
# separately, these were read out of the file they check. The independent test
# here is check_published_shares, which plays the counts off against percentages
# the Department computed itself.
NATIONAL_CONTROLS: dict[str, int] = {
    "_total": 21_781_800,
    "Buddhist": 15_199_093,
    "Hindu": 2_734_839,
    "Islam": 2_337_379,
    "Roman Catholic": 1_224_348,
    "Other Christian": 282_185,
    "Sinhalese": 16_144_037,
    "Sri Lankan Tamil": 2_681_627,
    "Indian Tamil": 600_360,
    "Sri Lankan Moor": 2_283_246,
}

SHARE_TOLERANCE = 0.1       # percentage points, against the printed figures


def english(value: Any) -> str:
    """The English half of a trilingual cell -- the only ASCII in it."""
    text = "".join(ch for ch in str(value or "") if ord(ch) < 128)
    return re.sub(r"\s+", " ", text).replace("/", " ").strip()


def read_sheet(path: Path, tag: str) -> tuple[list[str], dict[str, list[Any]],
                                              dict[str, list[Any]]]:
    """(category labels, counts by district, published percentages by district)."""
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit("pip install openpyxl to read the Sri Lanka workbooks") from exc

    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True)[tag]
                .iter_rows(values_only=True))

    labels: list[str] = []
    for row in rows[:8]:
        found = [english(c) for c in row[FIRST_CATEGORY:] if c]
        if len(found) > len(labels):
            labels = found

    counts: dict[str, list[Any]] = {}
    percents: dict[str, list[Any]] = {}
    pending: str | None = None
    for row in rows:
        name = english(row[0])
        if name and name not in ("District",) and not name.startswith(tag):
            counts[name] = list(row)
            pending = name
        elif pending and isinstance(row[A2_TOTAL], (int, float)):
            # The unlabelled row under a district is its percentage row.
            percents[pending] = list(row)
            pending = None
    return labels, counts, percents


def category_counts(row: list[Any], labels: list[str],
                    rename: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for offset, label in enumerate(labels):
        value = row[FIRST_CATEGORY + offset] if FIRST_CATEGORY + offset < len(row) else None
        if not isinstance(value, (int, float)) or not label:
            continue
        out[rename.get(label, label)] = float(value)
    return out


def check_published_shares(name: str, counts: dict[str, float], total: float,
                           printed: list[Any], labels: list[str],
                           rename: dict[str, str]) -> list[str]:
    """Recomputed shares must match the percentages printed beside them.

    The Department prints its own percentage row under every district. Checking
    against it tests the column alignment itself: a row read one cell to the left
    still sums to 100%, but stops agreeing with what was published.
    """
    drift = []
    for offset, label in enumerate(labels):
        cell = printed[FIRST_CATEGORY + offset] if FIRST_CATEGORY + offset < len(printed) else None
        if not isinstance(cell, (int, float)) or not label:
            continue
        got = 100.0 * counts.get(rename.get(label, label), 0.0) / total if total else 0.0
        if abs(got - float(cell)) > SHARE_TOLERANCE:
            drift.append(f"{name} / {label}: computed {got:.1f}%, published {cell}%")
    return drift


def load() -> dict[str, Any]:
    a1_labels, a1, _ = read_sheet(WORKBOOKS / "A1.xlsx", "A1")
    a2_labels, a2, a2_pct = read_sheet(WORKBOOKS / "A2.xlsx", "A2")
    a3_labels, a3, a3_pct = read_sheet(WORKBOOKS / "A3.xlsx", "A3")

    districts = [n for n in a1 if n != "Sri Lanka"]
    log(f"  read {len(districts)} districts from A1/A2/A3")

    drift: list[str] = []
    units: dict[str, dict[str, Any]] = {}
    for name in a1:
        total = a1[name][A1_TOTAL]
        if not isinstance(total, (int, float)):
            continue
        ethnicity = category_counts(a2.get(name, []), a2_labels, ETHNIC_LABELS)
        religion = category_counts(a3.get(name, []), a3_labels, {})
        if name in a2_pct:
            drift += check_published_shares(name, ethnicity, total, a2_pct[name],
                                            a2_labels, ETHNIC_LABELS)
        if name in a3_pct:
            drift += check_published_shares(name, religion, total, a3_pct[name],
                                            a3_labels, {})
        units[name] = {
            "population": int(total),
            "male": a1[name][A1_MALE], "female": a1[name][A1_FEMALE],
            "ethnicity": ethnicity, "religion": religion,
        }

    if drift:
        raise SystemExit("computed shares disagree with the published percentages "
                         "-- refusing to emit:\n  " + "\n  ".join(drift[:12]))
    log(f"  every share agrees with the Department's own printed percentages "
        f"(within {SHARE_TOLERANCE}pp)")
    return units


def validate(units: dict[str, Any]) -> None:
    country = units.get("Sri Lanka")
    if not country:
        raise SystemExit("the Sri Lanka total row is missing from A1")

    merged = {**country["religion"], **country["ethnicity"]}
    drift = []
    if country["population"] != NATIONAL_CONTROLS["_total"]:
        drift.append(f"total {country['population']:,}, "
                     f"published {NATIONAL_CONTROLS['_total']:,}")
    for label, published in NATIONAL_CONTROLS.items():
        if label == "_total":
            continue
        got = merged.get(label)
        if got is None:
            drift.append(f"{label} missing entirely")
        elif int(got) != published:
            drift.append(f"{label} {int(got):,}, published {published:,}")
    if drift:
        raise SystemExit("these workbooks do not match the pinned 2024 national "
                         "row -- refusing to emit:\n  " + "\n  ".join(drift))

    summed = sum(v["population"] for k, v in units.items() if k != "Sri Lanka")
    if summed != NATIONAL_CONTROLS["_total"]:
        raise SystemExit(f"districts sum to {summed:,}, national row says "
                         f"{NATIONAL_CONTROLS['_total']:,}")
    log(f"  national row matches the pinned 2024 figures: "
        f"{country['population']:,} people, Buddhist "
        f"{100 * merged['Buddhist'] / country['population']:.1f}%, "
        f"Sinhalese {100 * merged['Sinhalese'] / country['population']:.1f}%")


def build_record(name: str, unit: dict[str, Any], *, level: str,
                 entity_id: str, codes: dict[str, Any]) -> dict[str, Any]:
    population = unit["population"]
    male, female = unit["male"], unit["female"]
    ratio = round(1000.0 * female / male) if male else None
    return record(
        entity_id, name, level=level, parent="LKA", codes=codes,
        population=measure(population, year=2024, source=SOURCE),
        sex_ratio=(measure(ratio, unit="females_per_1000_males", year=2024,
                           source=SOURCE) if ratio else gap(NOT_AVAILABLE)),
        religion=shares(unit["religion"], total=population) or gap(NOT_AVAILABLE),
        religion_note="Census of Population and Housing 2024, table A3.",
        religion_year=2024,
        ethnicity=shares(unit["ethnicity"], total=population) or gap(NOT_AVAILABLE),
        ethnicity_note=(
            "Census 2024 table A2. Sri Lanka's ethnic classification distinguishes "
            "Sri Lankan Tamils from Indian Tamils (Malaiyaga Thamilar), whose "
            "ancestors were brought to the plantations under British rule, and "
            "counts Moors as an ethnic group rather than a religious one."),
        ethnicity_year=2024,
        language=gap(NOT_COLLECTED,
                     "Sri Lanka's census does not ask mother tongue. It asks "
                     "literacy -- the ability to speak, read and write Sinhala, "
                     "Tamil and English, for people aged 10 and over -- and the "
                     "2024 report states it did not account for proficiency in any "
                     "other language. Those are overlapping proficiencies, not "
                     "shares of a population, so they do not form a composition. "
                     "Nor is language inferred from ethnicity here: most Sri Lankan "
                     "Moors speak Tamil, which would put a tenth of the country in "
                     "the wrong column."),
        sources=[{"field": "population/religion/ethnicity", "name": SOURCE,
                  "url": CATALOG, "year": 2024}],
    )


def districts(units: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for name, unit in units.items():
        if name == "Sri Lanka":
            continue
        shape = DISTRICT_ALIASES.get(name, name)
        out.append(build_record(f"{shape} District", unit, level="admin2",
                                entity_id=f"LKA-D-{shape.replace(' ', '-')}",
                                codes={"census2024_district": name}))
    return out


def provinces(units: dict[str, Any]) -> list[dict[str, Any]]:
    """Province totals summed from their districts.

    Plain arithmetic on official counts: the nine sums reproduce the national
    population exactly, which is asserted rather than assumed.
    """
    out = []
    covered = 0
    for province, members in PROVINCES.items():
        missing = [d for d in members if d not in units]
        if missing:
            raise SystemExit(f"{province}: districts absent from the workbooks: {missing}")
        agg = {"population": 0, "male": 0, "female": 0,
               "ethnicity": collections.Counter(), "religion": collections.Counter()}
        for member in members:
            unit = units[member]
            agg["population"] += unit["population"]
            agg["male"] += unit["male"] or 0
            agg["female"] += unit["female"] or 0
            agg["ethnicity"].update(unit["ethnicity"])
            agg["religion"].update(unit["religion"])
        covered += agg["population"]
        out.append(build_record(f"{province} Province", agg, level="admin1",
                                entity_id=f"LKA-P-{province.replace(' ', '-')}",
                                codes={"province": province}))
    if covered != NATIONAL_CONTROLS["_total"]:
        raise SystemExit(f"provinces sum to {covered:,}, national total is "
                         f"{NATIONAL_CONTROLS['_total']:,}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", choices=["district", "province"], default="district")
    args = ap.parse_args()

    units = load()
    validate(units)
    rows = districts(units) if args.level == "district" else provinces(units)
    log(f"  {args.level}: {len(rows)} records")
    write_json(PROCESSED / f"srilanka_{args.level}.json", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
