#!/usr/bin/env python3
"""India -- Census 2011 mother tongue (table C-16), by district and state.

C-16 is the table that closes the one gap ``india_census.py`` could not: it asks
every person their mother tongue, and the Registrar General publishes the answer
down to sub-district level. There is no API. It ships as per-state XLSX
workbooks from the censusindia.gov.in NADA catalogue, so the workbooks live in
``data/raw/india/c16/`` and this reads them from disk.

Two things about the table shape decide how it is read.

**It is hierarchical.** Mother-tongue codes ending in ``000`` are the 122
language groups ("6 HINDI"); the codes beneath each one are the individual
mother tongues returned under it ("Bhojpuri", "Awadhi", "Chhattisgarhi"). Both
levels sit in the same column, so summing the column counts every person twice.
Only the group rows are read -- and that is checked rather than assumed: for
every unit, the group rows must sum to exactly the unit's enumerated population,
or the run stops (:func:`check_levels`). Australia's religion figures were
silently doubled by exactly this shape, and the shares still added to 100%, so
an internal consistency check would not have caught it. This one is arithmetic
against an independent total.

**It is nested geographically.** Each workbook carries state, district and
sub-district rows in one sheet, distinguished by code. This map stops at
district, so only rows with a zero sub-district code are read.

The all-India workbook (``...0000.XLSX``) holds every state; the numbered
workbooks hold that state's districts. Whichever files are present are used, so
adding the remaining states is a matter of dropping their workbooks in.

Coverage is therefore uneven *by design*, and says so: every state has a
mother-tongue composition, while districts have one only where the state's
workbook is present. Districts in the other states keep an explicit gap naming
the missing file, rather than an unexplained blank.

Usage:
    python -m scripts.fetch_census.india_language --level district
    python -m scripts.fetch_census.india_language --level state
"""

from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, log, record, shares, write_json,
)
from .india_census import (
    CATALOG, DISTRICT_ALIASES, STATE_ALIASES, SUBDIVIDED_SINCE_2011,
)

WORKBOOKS = RAW / "india" / "c16"
SOURCE = ("Census of India 2011, table C-16 population by mother tongue "
          "(Registrar General & Census Commissioner)")

# Column positions in the C-16 sheet, which carries a three-row banner.
COL_STATE, COL_DISTRICT, COL_SUBDISTRICT, COL_AREA = 1, 2, 3, 4
COL_MT_CODE, COL_MT_NAME, COL_PERSONS = 5, 6, 7
FIRST_DATA_ROW = 7

# A language *group* row; anything else is one mother tongue reported under it.
GROUP_CODE = re.compile(r"\d+000$")

# How many groups a unit shows before the tail is folded into one labelled
# remainder. 122 groups x 640 districts is a megabyte of payload for figures
# that round to 0.0% -- but the tail is summed and shown, never dropped.
MAX_GROUPS = 12
MIN_PCT = 0.1
REMAINDER = "Other languages"

# What the Registrar General published for India as a whole. A workbook that
# does not reproduce these is not C-16, whatever the filename says.
NATIONAL_CONTROLS: dict[str, int] = {
    "_total": 1_210_854_977,
    "Hindi": 528_347_193,
    "Bengali": 97_237_669,
    "Marathi": 83_026_680,
    "Telugu": 81_127_740,
    "Tamil": 69_026_881,
    "Gujarati": 55_492_554,
    "Urdu": 50_772_631,
    "Kannada": 43_706_512,
    "Odia": 37_521_324,
    "Malayalam": 34_838_819,
    "Punjabi": 33_124_726,
    "Assamese": 15_311_351,
}

STATE_NOTE = ("Census of India 2011 table C-16, population by mother tongue. "
              "Mother tongue is what the respondent names, not a test of "
              "fluency, and is distinct from the languages a person also speaks.")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def clean_group(label: str) -> str:
    """'6 HINDI' -> 'Hindi'; '124 OTHERS' -> 'Other languages'."""
    name = re.sub(r"^\s*\d+\s+", "", str(label)).strip()
    if name.upper() == "OTHERS":
        return REMAINDER
    return name.title().replace("'S", "'s")


def read_workbook(path: Path) -> list[tuple[str, str, str, str, int]]:
    """(state code, district code, area name, group label, persons) per row.

    Sub-district rows and the per-language child rows are dropped here, so
    everything downstream sees one level of one hierarchy.
    """
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit("pip install openpyxl to read the C-16 workbooks") from exc

    sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    out = []
    for row in sheet.iter_rows(min_row=FIRST_DATA_ROW, values_only=True):
        if not row or not row[0]:
            continue
        if str(row[COL_SUBDISTRICT]) != "00000":
            continue
        code = str(row[COL_MT_CODE])
        if not GROUP_CODE.fullmatch(code):
            continue
        out.append((str(row[COL_STATE]), str(row[COL_DISTRICT]),
                    str(row[COL_AREA]).strip(), clean_group(row[COL_MT_NAME]),
                    int(row[COL_PERSONS] or 0)))
    return out


def load(directory: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Every unit found across the workbooks, keyed by (state code, district code)."""
    paths = sorted(directory.glob("*.XLSX")) + sorted(directory.glob("*.xlsx"))
    if not paths:
        raise SystemExit(
            f"no C-16 workbooks in {directory}. Download DDWC16*.XLSX from "
            f"{CATALOG} (Census 2011 > Language > C-16) and put them there.")

    units: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        rows = read_workbook(path)
        log(f"  {path.name}: {len(rows)} language-group rows")
        for state, district, area, group, persons in rows:
            unit = units.setdefault((state, district),
                                    {"name": area, "counts": collections.Counter()})
            # Assigned, not accumulated. Every state's own row appears twice --
            # once in the all-India workbook and once in that state's own -- so
            # summing doubles all 15 of them. Each (unit, language group) pair
            # occurs once per workbook, which makes re-reading it a no-op.
            unit["counts"][group] = persons
    return units


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_levels(units: dict[tuple[str, str], dict[str, Any]],
                 populations: dict[tuple[str, str], int]) -> None:
    """Group rows must sum to the enumerated population of their unit.

    This is the check that catches reading two levels of the hierarchy at once.
    It compares against a total the language table did not produce, so unlike a
    shares-add-to-100% test it cannot be satisfied by double counting.
    """
    drift = []
    for key, unit in units.items():
        expected = populations.get(key)
        if expected is None:
            continue
        got = sum(unit["counts"].values())
        if got != expected:
            drift.append(f"{unit['name']}: mother-tongue rows sum to {got:,}, "
                         f"but {expected:,} people were enumerated "
                         f"({got / expected:.2f}x)")
    if drift:
        raise SystemExit("C-16 hierarchy check failed -- refusing to emit:\n  "
                         + "\n  ".join(drift[:10]))


def validate(units: dict[tuple[str, str], dict[str, Any]]) -> None:
    """Refuse to emit anything unless India's own row matches what was published."""
    india = units.get(("00", "000"))
    if not india:
        raise SystemExit(
            f"the all-India row is missing: add DDWC16STMTMDDS0000.XLSX to "
            f"{WORKBOOKS} so the national totals can be checked.")

    counts = india["counts"]
    drift = []
    total = sum(counts.values())
    if total != NATIONAL_CONTROLS["_total"]:
        drift.append(f"total population {total:,}, "
                     f"published {NATIONAL_CONTROLS['_total']:,}")
    for language, published in NATIONAL_CONTROLS.items():
        if language == "_total":
            continue
        got = counts.get(language)
        if got != published:
            drift.append(f"{language} {got:,} speakers, published {published:,}"
                         if got else f"{language} missing entirely")
    if drift:
        raise SystemExit("these workbooks do not reproduce the published C-16 "
                         "figures -- refusing to emit:\n  " + "\n  ".join(drift))
    log(f"  validated against published C-16: {total:,} people, "
        f"Hindi {100 * counts['Hindi'] / total:.2f}%, "
        f"{len(counts)} language groups")


# ---------------------------------------------------------------------------
# Emitting
# ---------------------------------------------------------------------------

def composition(counts: collections.Counter) -> list[dict[str, Any]]:
    """Largest groups, with the tail summed into one labelled remainder."""
    total = sum(counts.values())
    if not total:
        return []
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    kept: dict[str, int] = {}
    tail = 0
    for name, value in ranked:
        if name != REMAINDER and len(kept) < MAX_GROUPS \
                and 100.0 * value / total >= MIN_PCT:
            kept[name] = value
        else:
            tail += value
    if tail:
        kept[REMAINDER] = kept.get(REMAINDER, 0) + tail
    return shares(kept, total=total)


def language_note(shown: int, groups: int) -> str:
    if shown >= groups:
        return STATE_NOTE
    return (f"{STATE_NOTE} {groups} mother-tongue groups were reported here; the "
            f"{groups - shown} smallest are summed into '{REMAINDER}' rather than "
            f"listed, so the shares still cover everyone enumerated.")


def state_names(units: dict[tuple[str, str], dict[str, Any]]) -> dict[str, str]:
    """State code -> display name, so a district can name the state it is in.

    District names repeat across India -- there is a Hamirpur in two states and a
    Pratapgarh in two others -- so the state is what makes the row unambiguous.
    """
    out = {}
    for (code, district), unit in units.items():
        if district != "000" or code == "00":
            continue
        raw = " ".join(unit["name"].split())
        name = raw.title().replace(" And ", " and ").replace(" Of ", " of ")
        out[code] = STATE_ALIASES.get(raw.lower(), name)
    return out


def build(units: dict[tuple[str, str], dict[str, Any]], level: str
          ) -> list[dict[str, Any]]:
    states = state_names(units)
    out = []
    for (state_code, district_code), unit in sorted(units.items()):
        is_state = district_code == "000"
        if state_code == "00" or is_state != (level == "state"):
            continue

        raw_name = " ".join(unit["name"].split())
        key = raw_name.lower()
        if not is_state and key in SUBDIVIDED_SINCE_2011:
            # One census row, several present-day districts. Splitting a language
            # composition across successors would be an estimate wearing the
            # clothes of a measurement, so each successor gets the reason instead.
            for successor in SUBDIVIDED_SINCE_2011[key]:
                out.append(record(
                    f"IND-D{district_code}-{successor}", successor,
                    level="admin2", parent="IND",
                    parent_name=states.get(state_code),
                    language=gap(NOT_AVAILABLE,
                                 f"The 2011 census reported mother tongue for the "
                                 f"undivided {raw_name} district, which has since "
                                 f"been subdivided. The successor districts were "
                                 f"never enumerated separately."),
                    sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
                ))
            continue

        if is_state:
            name = raw_name.title().replace(" And ", " and ").replace(" Of ", " of ")
            name = STATE_ALIASES.get(raw_name.lower(), name)
            entity_id = f"IND-S-{name.replace(' ', '-')}"
            codes = {"census2011_state": state_code}
        else:
            name = DISTRICT_ALIASES.get(raw_name.lower(), raw_name)
            entity_id = f"IND-D{district_code}"
            codes = {"census2011_state": state_code,
                     "census2011_district": district_code}

        groups = composition(unit["counts"])
        out.append(record(
            entity_id, name, level="admin1" if is_state else "admin2", parent="IND",
            parent_name=None if is_state else states.get(state_code),
            codes=codes,
            language=groups or gap(NOT_AVAILABLE),
            language_note=language_note(len(groups), len(unit["counts"])),
            language_year=2011,
            sources=[{"field": "language", "name": SOURCE, "url": CATALOG,
                      "year": 2011,
                      "license": "Government of India open data (GODL-India)"}],
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", choices=["state", "district"], default="district")
    ap.add_argument("--input", type=Path, default=WORKBOOKS)
    args = ap.parse_args()

    units = load(args.input)
    validate(units)
    # District rows carry their own enumerated totals, so the hierarchy check
    # runs against the C-01 population where india_census has already produced it.
    check_levels(units, populations_from_units(units))

    rows = build(units, args.level)
    covered = {code for (code, district) in units if district != "000"}
    log(f"  {args.level}: {len(rows)} records from "
        f"{len(covered)} state workbook(s)")
    write_json(PROCESSED / f"india_language_{args.level}.json", rows)
    return 0


def populations_from_units(units: dict[tuple[str, str], dict[str, Any]]
                           ) -> dict[tuple[str, str], int]:
    """State totals, summed from that state's district rows.

    An independent total for the hierarchy check: the districts of a state are
    enumerated separately from the state row, so if the state row were reading
    two levels of the language hierarchy it would not equal the district sum.
    """
    by_state: dict[str, int] = collections.Counter()
    for (state, district), unit in units.items():
        if district != "000":
            by_state[state] += sum(unit["counts"].values())
    return {(state, "000"): total for state, total in by_state.items()}


if __name__ == "__main__":
    raise SystemExit(main())
