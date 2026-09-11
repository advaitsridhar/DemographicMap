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
adding a state is a matter of dropping its workbook in.

**All 35 are now present**, so every district the 2011 census enumerated has a
mother-tongue composition: 643 records covering all 640 districts, three of
which have since been subdivided and emit their successors as gaps instead.
The shapes without a composition are the ones the census never enumerated at
all -- districts created after 2011 -- and those are ``india_census.py``'s
``CREATED_AFTER_2011`` rather than a missing file here.

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
    CATALOG, DISTRICT_ALIASES, SPLIT_STATES, STATE_ALIASES, SUBDIVIDED_SINCE_2011,
    lost_territory, lost_territory_reason, split_note, subdivided_reason,
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
REMAINDER = "Other small languages"

# The census has a residual group of its own (code 124), and it is not the same
# thing as the tail this adapter folds. In Zunheboto it is 95.6% of the district
# -- the Sumi spoken there is reported under it rather than under group 107 --
# and the Registrar General publishes no breakdown beneath it at district level.
# Labelling that "other small languages" would describe a long tail of minor
# tongues, which is the opposite of what it is, so the two are kept apart.
CENSUS_RESIDUAL = "Other languages (unspecified)"

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
    """'6 HINDI' -> 'Hindi'; '124 OTHERS' -> the census's own residual label."""
    name = re.sub(r"^\s*\d+\s+", "", str(label)).strip()
    if name.upper() == "OTHERS":
        return CENSUS_RESIDUAL
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
        # The census residual ranks like any other group: it is a category the
        # Registrar General published, not something this adapter invented.
        if len(kept) < MAX_GROUPS and 100.0 * value / total >= MIN_PCT:
            kept[name] = value
        else:
            tail += value
    if tail:
        kept[REMAINDER] = tail
    return shares(kept, total=total)


def language_note(rows: list[dict[str, Any]], groups: int) -> str:
    note = STATE_NOTE
    shown = len([r for r in rows if r["group"] != REMAINDER])
    if shown < groups:
        note += (f" {groups} mother-tongue groups were reported here; the "
                 f"{groups - shown} smallest are summed into '{REMAINDER}' rather "
                 f"than listed, so the shares still cover everyone enumerated.")
    residual = next((r for r in rows if r["group"] == CENSUS_RESIDUAL), None)
    if residual:
        note += (f" '{CENSUS_RESIDUAL}' ({residual['pct']}%) is the census's own "
                 f"catch-all group, not a tail summed here: the Registrar General "
                 f"published no breakdown beneath it at this level.")
    return note


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


def split_state_rows(units: dict[tuple[str, str], dict[str, Any]],
                     states: dict[str, str]) -> list[dict[str, Any]]:
    """Mother tongue for the states the census never named, and their remainders.

    The same arithmetic ``india_census.split_states`` does for religion, on the
    other table, and the two are worth keeping apart rather than sharing code:
    C-16 and C-01 are different publications with different district columns,
    and a split that is right in one and wrong in the other is the failure
    neither file can see by itself. What ties them together is that both must
    reproduce the same population -- ``SPLIT_STATES`` carries it, and a
    workbook that disagrees stops the run here exactly as the extract does
    there.
    """
    out: list[dict[str, Any]] = []
    problems: list[str] = []
    for new_state, split in SPLIT_STATES.items():
        parent_unit = units.get((split.state_code, "000"))
        if parent_unit is None:
            continue                       # that state's workbook is not present
        members = collections.Counter()
        for code in split.codes:
            unit = units.get((split.state_code, f"{code:03d}"))
            if unit is None:
                problems.append(f"{new_state}: no C-16 row for district "
                                f"{code:03d} of {split.parent}")
                continue
            members.update(unit["counts"])
        residual = collections.Counter(parent_unit["counts"])
        residual.subtract(members)
        total = sum(members.values())
        if total != split.population:
            problems.append(f"{new_state}: its C-16 district rows sum to "
                            f"{total:,} against a published {split.population:,}")
        if sum(residual.values()) != split.residual:
            problems.append(
                f"{split.parent}: what is left after {new_state} sums to "
                f"{sum(residual.values()):,} against a published {split.residual:,}")
        if any(v < 0 for v in residual.values()):
            problems.append(f"{split.parent}: taking {new_state} out leaves a "
                            f"negative count for a language, so the district "
                            f"rows do not sit inside the state row")
        kept = sum(1 for (code, district) in units
                   if code == split.state_code and district != "000") \
            - len(split.codes)
        for name, counts, residual_ in ((new_state, members, False),
                                        (split.parent, +residual, True)):
            groups = composition(counts)
            out.append(record(
                f"IND-S-{name.replace(' ', '-')}", name, level="admin1",
                parent="IND", codes={"census2011_state": split.state_code},
                language=groups or gap(NOT_AVAILABLE),
                language_note=(
                    language_note(groups, len(counts))
                    + " " + split_note(new_state, split, residual=residual_,
                                       total=sum(counts.values()),
                                       undivided=sum(parent_unit["counts"].values()),
                                       kept=kept)),
                language_year=2011,
                sources=[{"field": "language", "name": SOURCE, "url": CATALOG,
                          "year": 2011,
                          "license": "Government of India open data (GODL-India)"}],
            ))
    if problems:
        raise SystemExit(
            "india_language: the state splits do not reproduce the census's "
            "own figures, so nothing is being emitted:\n  - "
            + "\n  - ".join(problems))
    return out


def build(units: dict[tuple[str, str], dict[str, Any]], level: str
          ) -> list[dict[str, Any]]:
    states = state_names(units)
    shrunken = lost_territory()
    out = []
    if level == "state":
        out.extend(split_state_rows(units, states))
    for (state_code, district_code), unit in sorted(units.items()):
        is_state = district_code == "000"
        if state_code == "00" or is_state != (level == "state"):
            continue

        raw_name = " ".join(unit["name"].split())
        key = raw_name.lower()
        state_2011 = (states.get(state_code) or "").casefold()
        shrink = shrunken.get((state_2011, key)) if not is_state else None
        if shrink:
            # The shape still carries this district's name and no longer
            # carries its territory. india_census.py emits the same id with
            # the same reason; both files have to, because whichever runs last
            # decides what the record says and a gap that has lost its reason
            # is indistinguishable from one nobody thought about.
            share, successors = shrink
            reason = lost_territory_reason(DISTRICT_ALIASES.get(key, raw_name),
                                           share, successors)
            out.append(record(
                f"IND-D{district_code}", DISTRICT_ALIASES.get(key, raw_name),
                level="admin2", parent="IND", parent_name=states.get(state_code),
                codes={"census2011_state": state_code,
                       "census2011_district": district_code},
                population=gap(NOT_AVAILABLE, reason),
                religion=gap(NOT_AVAILABLE, reason),
                language=gap(NOT_AVAILABLE, reason),
                # Sex ratio too, though this file never fills it. A bare gap
                # here would land on india_census's explained one when the two
                # records merge -- gap does not overwrite a value, but it does
                # overwrite another gap, and the later file wins.
                sex_ratio=gap(NOT_AVAILABLE, reason),
                sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
            ))
            continue
        if not is_state and key in SUBDIVIDED_SINCE_2011:
            # One census row, several present-day districts. Splitting a language
            # composition across successors would be an estimate wearing the
            # clothes of a measurement, so each successor gets the reason instead.
            #
            # Religion and population carry the same reason rather than the
            # bare gap `record` would default them to. This file and
            # india_census.py both emit a record for these successors under the
            # same id, and merging lets a gap overwrite a gap: a default
            # `not_available` with no note landing on top of india_census's
            # explained one is how East Jaintia Hills came to show an
            # unexplained blank for religion beside a fully explained blank for
            # language.
            reason = subdivided_reason(raw_name)
            for successor in SUBDIVIDED_SINCE_2011[key]:
                out.append(record(
                    f"IND-D{district_code}-{successor}", successor,
                    level="admin2", parent="IND",
                    parent_name=states.get(state_code),
                    population=gap(NOT_AVAILABLE, reason),
                    religion=gap(NOT_AVAILABLE, reason),
                    language=gap(NOT_AVAILABLE, reason),
                    sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
                ))
            continue

        if is_state:
            if state_code in {s.state_code for s in SPLIT_STATES.values()}:
                # Emitted above, as the two states its districts now make up.
                # Left here as well it would write a second record under the
                # residual state's id, carrying the undivided state's languages.
                continue
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
            language_note=language_note(groups, len(unit["counts"])),
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
