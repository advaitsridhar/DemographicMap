#!/usr/bin/env python3
"""India -- Census 2011 table C-13, single year age returns: the median age.

Every Indian unit on the map had a 2011 population, a sex ratio and three
compositions and no median age. The Registrar General publishes table C-13,
*Single year age returns by residence and sex*, as one workbook per state on
the censusindia.gov.in NADA catalogue (studies PC11_C13-00 to PC11_C13-35):
every state and every one of the 640 districts, ages 0 to 99 one by one,
"100+" and "Age not stated", persons, males and females, total, rural and
urban. That is the age structure of every person the census counted, and the
median is read from it the standard way -- interpolated within the single year
that holds the middle person, with "100+" the open top group and the people of
unstated age left out of it and counted in the note.

**What is checked, before anything is written:**

* in every unit the single years, 100+ and the unstated add up to the "All
  ages" row, for persons, males and females;
* every state's districts add up to the state's own row, and the states to
  the all-India workbook, which must print 1,210,854,977;
* every district bound to a shape carries, on that shape, the 2011 count
  ``india_census.py`` put there from table C-01 -- the two tables were
  typeset apart, so a code bound to the wrong polygon shows up as two
  different populations, and the binding is refused;
* the split states are their districts: present-day Telangana's ten 2011
  districts must sum to the 35,193,978 and the residual Andhra Pradesh to
  the 49,386,799 ``india_census.SPLIT_STATES`` holds, and Ladakh's two and the
  rest of Jammu and Kashmir likewise.

**Which shapes, and the rule the files are split on.** The census counted 640
districts and the map draws 735. A district that has not changed since 2011
carries its own row's median, bound by its census code (the build put the
code on the shape). Two kinds of shape are not that district:

* the 75 shapes that kept a district's name after a newer district was cut
  out of them (``india_census.LOST_TERRITORY_SINCE_2011``) -- the 2011 row is
  the undivided district's;
* the 91 districts created since 2011 and the six successors of the three
  districts the census counted whole and that have since been divided
  (``CREATED_AFTER_2011``, ``SUBDIVIDED_SINCE_2011``) -- no row exists for
  them at all.

The brief for this round says a district split after the census must not get
its parent's figure, so the main file, ``india_age.json``, carries neither and
gives every one of them its reason. The owner's earlier decision for India --
the parent's figures on the shape that kept the name, with a sentence saying
so, and the predecessor's shares on the new districts as a stated estimate --
is what ``india_census.py`` does with every other field. So the same medians,
the undivided district's on the shapes that kept the name and the
predecessors' summed ages on the new ones, are written apart, to
``india_age_successors.json``, with the sentences india_census uses: which of
the two conventions the map follows for this field is one line in the build.

States: the state's own row, except where the state is not the 2011 state --
Telangana and the residual Andhra Pradesh, Ladakh and the rest of Jammu and
Kashmir, each summed from its 2011 districts; and Dadra and Nagar Haveli and
Daman and Diu, merged in 2020, summed from the two territories' workbooks.

Usage:
    python -m scripts.fetch_census.india_ages
"""

from __future__ import annotations

import argparse
import collections
import re
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .india_census import (
    BOUNDARY_ARTEFACTS, CREATED_AFTER_2011, DISTRICT_ALIASES, NATIONAL_CONTROLS,
    NEW_DISTRICT_ALIASES, SPLIT_STATES, STATE_IN_2011, SUBDIVIDED_SINCE_2011,
    created_reason, inherited_note, lost_territory, lost_territory_reason,
    subdivided_inherited_note, subdivided_reason,
)
from .south_asia_common import agree, fold, load_units, median_single

YEAR = 2011
NADA = "https://censusindia.gov.in/nada/index.php/catalog"
SOURCE = ("Census of India 2011, table C-13: single year age returns by "
          "residence and sex (Registrar General & Census Commissioner)")
LICENCE = "Government of India open data (GODL-India)"
# The catalogue's studies, PC11_C13-00 (India) to PC11_C13-35, are numbered
# 1436 to 1471 in the order the run found them; each study's one file is
# linked from its related-materials page, which is read rather than guessed.
STUDIES = range(1436, 1472)
INDIA_STUDY = 1436
OPEN_FROM = 100

# The census's population for the whole country, which the all-India workbook
# must print and the states must add up to.
INDIA_POPULATION = NATIONAL_CONTROLS["population"][0]
DISTRICTS_2011 = NATIONAL_CONTROLS["districts"][0]


class Unit(dict):
    """One area of C-13: its codes, its name and its ages by sex."""


def read_workbook(blob: bytes) -> dict[tuple[str, str], dict[str, Any]]:
    """{(state code, district code): unit} for one C-13 workbook.

    Every unit is a run of rows -- "All ages", 0 to 99, "100+", "Age not
    stated" -- under one area; the codes are the census's own, zero-padded,
    with "000" for the state's own row.
    """
    import xlrd                                     # noqa: PLC0415
    book = xlrd.open_workbook(file_contents=blob)
    sheet = book.sheet_by_index(0)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for i in range(sheet.nrows):
        row = sheet.row_values(i)
        if len(row) < 8:
            continue
        state, district = code(row[1], 2), code(row[2], 3)
        if state is None or district is None:
            continue
        area, age = str(row[3]).strip(), row[4]
        persons, males, females = (number(row[5]), number(row[6]), number(row[7]))
        if persons is None or males is None or females is None:
            continue
        unit = out.setdefault((state, district), Unit(
            state=state, district=district, name=area, total=None,
            ages={"T": collections.Counter(), "M": collections.Counter(),
                  "F": collections.Counter()},
            unstated=(0, 0, 0)))
        label = str(age).strip().lower()
        if label in ("all ages", "all age"):
            unit["total"] = (persons, males, females)
        elif label.startswith("age not stated"):
            unit["unstated"] = (persons, males, females)
        else:
            years = single(age)
            if years is None:
                raise SystemExit(f"india_ages: {area}: an age row reads {age!r}")
            for sex, n in zip("TMF", (persons, males, females)):
                if years in unit["ages"][sex]:
                    raise SystemExit(f"india_ages: {area} prints age {years} twice")
                unit["ages"][sex][years] = n
    return out


def code(value: Any, width: int) -> str | None:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(width) if text.isdigit() else None


def number(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).replace(",", "").strip()
    return int(text) if text.isdigit() else None


def single(age: Any) -> int | None:
    """0..99 from a cell, and OPEN_FROM for "100+"."""
    if isinstance(age, (int, float)):
        return int(age)
    text = str(age).strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"100\s*\+", text):
        return OPEN_FROM
    return None


def check_unit(unit: dict[str, Any]) -> None:
    where = f"india_ages: {unit['name']}"
    if unit["total"] is None:
        raise SystemExit(f"{where} has no 'All ages' row")
    if set(unit["ages"]["T"]) != set(range(0, OPEN_FROM + 1)):
        missing = sorted(set(range(0, OPEN_FROM + 1)) - set(unit["ages"]["T"]))
        raise SystemExit(f"{where} is missing ages {missing[:10]}")
    for i, sex in enumerate("TMF"):
        agree(f"{where} {sex}: single years with the unstated",
              sum(unit["ages"][sex].values()) + unit["unstated"][i], unit["total"][i])
    agree(f"{where}: males and females", unit["total"][1] + unit["total"][2],
          unit["total"][0])


def combine(units: list[dict[str, Any]], name: str) -> dict[str, Any]:
    out = Unit(state=None, district=None, name=name,
               total=tuple(sum(u["total"][i] for u in units) for i in range(3)),
               ages={sex: collections.Counter() for sex in "TMF"},
               unstated=tuple(sum(u["unstated"][i] for u in units) for i in range(3)))
    for unit in units:
        for sex in "TMF":
            out["ages"][sex].update(unit["ages"][sex])
    return out


def lost_age_reason(name: str, share: int,
                    gone: tuple[tuple[str, int], ...]) -> str:
    """Why a shape that kept a district's name carries no median age."""
    names = [child for child, _ in gone]
    listed = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else names[0]
    years = sorted({year for _, year in gone})
    when = " and ".join(str(y) for y in years)
    return (f"Census of India 2011 table C-13 publishes single years of age for "
            f"districts as they stood in 2011, and its {name} row is the "
            f"undivided district, before {listed} ({when}) "
            f"{'were' if len(names) > 1 else 'was'} carved out of it. The shape "
            f"drawn here keeps about {share}% of that ground. No age has been "
            f"counted for the district as drawn, and the undivided district's "
            f"median is not shown on part of its ground.")


def median_of(unit: dict[str, Any]) -> float | None:
    return median_single(dict(unit["ages"]["T"]), open_from=OPEN_FROM)


def age_fields(unit: dict[str, Any], url: str, extra: str = "") -> dict[str, Any]:
    median = median_of(unit)
    if median is None:
        raise SystemExit(f"india_ages: {unit['name']}: no median below 100")
    unstated = unit["unstated"][0]
    return {
        "median_age": measure(median, unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            f"Census of India 2011 table C-13: the median of the single years of "
            f"age of the {unit['total'][0] - unstated:,} people whose age was "
            f"returned, interpolated within the year that holds the middle "
            f"person (100 and over is the open top group)."
            + (f" The {unstated:,} people whose age was not stated are left "
               f"out of it." if unstated else "") + extra),
        "sources": [{"field": "median_age", "name": SOURCE, "url": url,
                     "year": YEAR, "license": LICENCE}],
    }


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def study_file(study: int) -> str:
    """The one download link on a study's related-materials page."""
    page = http_get(f"{NADA}/{study}/related-materials", cache=False, aia=True)
    links = sorted(set(re.findall(rf"{re.escape(NADA)}/{study}/download/\d+", page)))
    if len(links) != 1:
        raise SystemExit(f"india_ages: study {study} links {len(links)} files: {links}")
    return links[0]


def fetch_all() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, str],
                         dict[str, Any]]:
    """Every state's units, the URL each state came from, and India's row."""
    units: dict[tuple[str, str], dict[str, Any]] = {}
    urls: dict[str, str] = {}
    india: dict[str, Any] | None = None
    for study in STUDIES:
        url = study_file(study)
        blob = http_get(url, cache=False, aia=True, binary=True)
        read = read_workbook(blob)
        states = {s for s, d in read if d == "000"}
        log(f"  study {study}: {len(read)} units, state(s) {sorted(states)}, "
            f"{len(blob):,} bytes")
        if study == INDIA_STUDY:
            india = read.get(("00", "000"))
            continue
        for key, unit in read.items():
            if key in units:
                raise SystemExit(f"india_ages: {unit['name']} is in two workbooks")
            units[key] = unit
        for state in states:
            urls[state] = url
    if india is None:
        raise SystemExit("india_ages: the all-India workbook has no India row")
    return units, urls, india


# ---------------------------------------------------------------------------
# Checks across units
# ---------------------------------------------------------------------------

def check_all(units: dict[tuple[str, str], dict[str, Any]], india: dict[str, Any]) -> None:
    for unit in units.values():
        check_unit(unit)
    check_unit(india)
    agree("india_ages: the all-India row", india["total"][0], INDIA_POPULATION)
    states = {s: u for (s, d), u in units.items() if d == "000"}
    districts = {k: u for k, u in units.items() if k[1] != "000"}
    agree("india_ages: districts in the workbooks", len(districts), DISTRICTS_2011)
    for state, row in states.items():
        inside = [u for (s, d), u in districts.items() if s == state]
        for i in range(3):
            agree(f"india_ages: state {state} ({row['name']}) against its districts",
                  sum(u["total"][i] for u in inside), row["total"][i])
    for i in range(3):
        agree("india_ages: the states against India",
              sum(u["total"][i] for u in states.values()), india["total"][i])
    log(f"  {len(states)} states and {len(districts)} districts reconcile, to "
        f"India's {india['total'][0]:,}")


# ---------------------------------------------------------------------------
# Binding and records
# ---------------------------------------------------------------------------

def census_population(unit: dict[str, Any]) -> int | None:
    pop = unit.get("population")
    if isinstance(pop, dict) and pop.get("year") == YEAR and "Census of India" in str(
            pop.get("source")):
        return int(pop["value"])
    return None


def state_name_2011(name: str) -> str:
    folded = fold(name)
    for present, then in STATE_IN_2011.items():
        if fold(present) == folded:
            return fold(then)
    return folded


def build() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    units, urls, india = fetch_all()
    check_all(units, india)
    return records(units, urls, india)


def records(units: dict[tuple[str, str], dict[str, Any]], urls: dict[str, str],
            india: dict[str, Any] | None = None
            ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    shapes1 = load_units("IND", "admin1")
    shapes2 = load_units("IND", "admin2")
    state_of_shape = {u["id"]: u for u in shapes1}
    by_code = {}
    for shape in shapes2:
        district = (shape.get("codes") or {}).get("census2011_district")
        if district:
            by_code[district.zfill(3)] = shape
    lost = lost_territory()
    lost_keys = {(fold(s), fold(d)): v for (s, d), v in lost.items()}
    main: list[dict[str, Any]] = []
    successors: list[dict[str, Any]] = []
    tally = collections.Counter()

    # Districts that are their 2011 selves, and the shapes that kept a name.
    rows_by_name: dict[tuple[str, str], dict[str, Any]] = {}
    for (state, district), unit in sorted(units.items()):
        if district == "000":
            continue
        name = re.sub(r"^District\s*-\s*", "", unit["name"]).strip()
        name = re.sub(r"\s*\(\d+\)\s*$", "", name)
        unit["district_name"] = name
        shape = by_code.get(district)
        state_shape = state_of_shape.get(shape.get("parent")) if shape else None
        state_key = state_name_2011(state_shape["name"]) if state_shape else ""
        names = {fold(name), *(fold(a) for a in (shape or {}).get("aliases") or ()),
                 fold((shape or {}).get("name")), fold((shape or {}).get("site_name"))}
        # And the census's spellings of the boundary file's names, which is
        # how india_census keys its tables ("Mahbubnagar" for "Mahabubnagar").
        names |= {fold(k) for k, v in DISTRICT_ALIASES.items() if fold(v) in names}
        rows_by_name[(state, fold(name))] = unit
        if shape is None:
            tally["2011 district with no shape (subdivided since)"] += 1
            continue
        counted = census_population(shape)
        if counted is not None and counted != unit["total"][0]:
            raise SystemExit(
                f"india_ages: {name} (code {district}) has {unit['total'][0]:,} "
                f"people in C-13 and its shape carries {counted:,} from C-01; the "
                "code is bound to the wrong polygon")
        hit = next((lost_keys[(state_key, n)] for n in names
                    if (state_key, n) in lost_keys), None)
        url = urls[state]
        if hit is None:
            main.append(record(
                f"IND-AGE-{state}-{district}", shape.get("site_name") or name,
                level="admin2", parent="IND", country="IND",
                match_by="shape_id", shape_id=shape["id"],
                **age_fields(unit, url)))
            tally["district, unchanged since 2011"] += 1
        else:
            share, gone = hit
            note = " " + lost_territory_reason(name, share, gone)
            successors.append(record(
                f"IND-AGE-LOST-{state}-{district}", shape.get("site_name") or name,
                level="admin2", parent="IND", country="IND",
                match_by="shape_id", shape_id=shape["id"],
                **age_fields(unit, url, note)))
            main.append(record(
                f"IND-AGE-{state}-{district}", shape.get("site_name") or name,
                level="admin2", parent="IND", country="IND",
                match_by="shape_id", shape_id=shape["id"],
                median_age={"status": "not_available",
                            "note": lost_age_reason(name, share, gone)},
                sources=[{"field": "median_age", "name": SOURCE, "url": url,
                          "year": YEAR, "license": LICENCE}]))
            tally["shape that kept a name after a split"] += 1

    # The shapes with no 2011 code: districts created since, the successors of
    # the three districts divided whole, and the one boundary artefact. Each is
    # found by its own name (or the alias india_census declares for it) inside
    # its present-day state, and gets its reason; the successors file gets the
    # predecessors' ages summed, single year by single year.
    def predecessor(state_now: str, state_then: str, name: str) -> dict[str, Any] | None:
        # The census's spelling, and the boundary file's where india_census
        # declares the two differ ("Mahbubnagar" is drawn "Mahabubnagar").
        spellings = {fold(name), fold(DISTRICT_ALIASES.get(name.casefold(), ""))} - {""}
        for shape in shapes2:
            code_ = (shape.get("codes") or {}).get("census2011_district")
            if not code_ or fold(state_of_shape.get(shape.get("parent"), {}).get(
                    "name")) not in (state_now, state_then):
                continue
            if spellings & {fold(shape.get("name")), fold(shape.get("site_name")),
                            *(fold(a) for a in shape.get("aliases") or ())}:
                for (s, d), unit in units.items():
                    if d == code_.zfill(3):
                        return unit
        then_code = next((s for (s, d), u in units.items()
                          if d == "000" and state_then in fold(u["name"])), None)
        return next((u for (s, n), u in rows_by_name.items()
                     if s == then_code and n in spellings), None)

    created = {}
    for state, entries in CREATED_AFTER_2011.items():
        for name, year, predecessors in entries:
            keys = {fold(name), fold(NEW_DISTRICT_ALIASES.get(name, ""))} - {""}
            for key in keys:
                created[(fold(state), key)] = (state, name, year, predecessors)
    divided = {fold(successor): undivided
               for undivided, names in SUBDIVIDED_SINCE_2011.items()
               for successor in names}
    for shape in shapes2:
        if (shape.get("codes") or {}).get("census2011_district"):
            continue
        state_now = fold(state_of_shape.get(shape.get("parent"), {}).get("name"))
        names = {fold(shape.get("name")), fold(shape.get("site_name")),
                 *(fold(a) for a in shape.get("aliases") or ())} - {""}
        entry = next((created[(state_now, n)] for n in names
                      if (state_now, n) in created), None)
        label = shape.get("site_name") or shape["name"]
        if entry is not None:
            state, name, year, predecessors = entry
            state_then = fold(STATE_IN_2011.get(state, state))
            main.append(record(
                f"IND-AGE-NEW-{fold(state)}-{fold(name)}", label, level="admin2",
                parent="IND", country="IND", match_by="shape_id", shape_id=shape["id"],
                median_age={"status": "not_available",
                            "note": created_reason(name, year, predecessors)}))
            tally["district created since 2011"] += 1
            parts = [predecessor(state_now, state_then, p) for p in predecessors]
            if all(parts):
                whole = combine(parts, name)
                successors.append(record(
                    f"IND-AGE-NEW-{fold(state)}-{fold(name)}", label, level="admin2",
                    parent="IND", country="IND", match_by="shape_id", shape_id=shape["id"],
                    **age_fields(whole, urls[parts[0]["state"]], " " + inherited_note(
                        name, year, predecessors))))
            else:
                log(f"  ! {name}: a predecessor of {predecessors} has no C-13 row")
            continue
        undivided = next((divided[n] for n in names if n in divided), None)
        if undivided is not None:
            main.append(record(
                f"IND-AGE-SUB-{fold(label)}", label, level="admin2", parent="IND",
                country="IND", match_by="shape_id", shape_id=shape["id"],
                median_age={"status": "not_available",
                            "note": subdivided_reason(undivided.title())}))
            tally["successor of a district divided whole"] += 1
            whole_unit = next((u for (s, n), u in rows_by_name.items()
                               if n == fold(undivided)), None)
            if whole_unit is not None:
                successors.append(record(
                    f"IND-AGE-SUB-{fold(label)}", label, level="admin2", parent="IND",
                    country="IND", match_by="shape_id", shape_id=shape["id"],
                    **age_fields(whole_unit, urls[whole_unit["state"]], " "
                                 + subdivided_inherited_note(undivided.title(), label))))
            else:
                log(f"  ! {undivided}: no C-13 row for the undivided district")
            continue
        artefact = next((BOUNDARY_ARTEFACTS[k] for k in BOUNDARY_ARTEFACTS
                         if fold(k) in names), None)
        if artefact is not None:
            main.append(record(
                f"IND-AGE-ARTEFACT-{fold(label)}", label, level="admin2", parent="IND",
                country="IND", match_by="shape_id", shape_id=shape["id"],
                median_age={"status": "not_available", "note": artefact[1]}))
            tally["boundary artefact"] += 1
            continue
        raise SystemExit(f"india_ages: {label} has no 2011 code and is in no table "
                         "of districts created or divided since; it cannot be placed")

    # States, as drawn.
    by_state_code = {s: u for (s, d), u in units.items() if d == "000"}
    for shape in shapes1:
        folded = fold(shape.get("site_name") or shape["name"])
        state_code = (shape.get("codes") or {}).get("census2011_state")
        extra = ""
        if folded in (fold("Telangana"), fold("Andhra Pradesh")):
            split = SPLIT_STATES["Telangana"]
            inside = [u for (s, d), u in units.items() if s == split.state_code
                      and d != "000" and (int(d) in split.codes) == (folded == fold("Telangana"))]
            whole = combine(inside, shape["name"])
            expect = split.population if folded == fold("Telangana") else split.residual
            agree(f"india_ages: {shape['name']} summed from its 2011 districts",
                  whole["total"][0], expect)
            extra = (" Summed from the ten 2011 districts that became the state "
                     "in 2014. The seven Khammam mandals moved to Andhra Pradesh "
                     "that year for the Polavaram project are inside them -- "
                     "190,304 people, 0.5% of this total -- and C-13 publishes "
                     "nothing below the district to take them out."
                     if folded == fold("Telangana") else
                     " Summed from the thirteen 2011 districts left to the state "
                     "when Telangana was formed in 2014; the seven Khammam "
                     "mandals it gained that year (190,304 people) are outside "
                     "them, and C-13 publishes nothing below the district to add "
                     "them in.")
            url = urls[split.state_code]
        elif folded in (fold("Ladakh"), fold("Jammu and Kashmir")):
            split = SPLIT_STATES["Ladakh"]
            inside = [u for (s, d), u in units.items() if s == split.state_code
                      and d != "000" and (int(d) in split.codes) == (folded == fold("Ladakh"))]
            whole = combine(inside, shape["name"])
            expect = split.population if folded == fold("Ladakh") else split.residual
            agree(f"india_ages: {shape['name']} summed from its 2011 districts",
                  whole["total"][0], expect)
            extra = (" Summed from Leh (Ladakh) and Kargil, the 2011 districts that "
                     "became the union territory in 2019." if folded == fold("Ladakh")
                     else " Summed from the 2011 districts that remained in Jammu "
                     "and Kashmir when Ladakh was separated in 2019.")
            url = urls[split.state_code]
        elif state_code == "26":
            whole = combine([by_state_code["25"], by_state_code["26"]], shape["name"])
            extra = (" Summed from the two union territories the census counted, "
                     "Dadra and Nagar Haveli and Daman and Diu, merged in 2020.")
            url = urls["26"]
        elif state_code in by_state_code:
            whole = by_state_code[state_code]
            url = urls[state_code]
        else:
            log(f"  ! no C-13 row for {shape['name']} (code {state_code})")
            continue
        counted = census_population(shape)
        merged_part = state_code == "26" and counted in (
            by_state_code["25"]["total"][0], by_state_code["26"]["total"][0])
        if merged_part:
            # The shape carries one territory's count until india_census's
            # state run, which now sums the two, is built; the C-13 sum is
            # checked against both territories' own rows above.
            log(f"  {shape['name']}: the shape carries {counted:,}, one of the two "
                f"territories; C-13 sums both to {whole['total'][0]:,}")
        elif counted is not None and counted != whole["total"][0]:
            raise SystemExit(f"india_ages: {shape['name']} has {whole['total'][0]:,} in "
                             f"C-13 and {counted:,} on its shape")
        main.append(record(
            f"IND-AGE-STATE-{fold(shape['name'])}", shape.get("site_name") or shape["name"],
            level="admin1", parent="IND", country="IND",
            match_by="shape_id", shape_id=shape["id"], **age_fields(whole, url, extra)))
        tally["state"] += 1
    if india is not None:
        log(f"  India's own median, from the all-India workbook: {median_of(india)}")
    return main, successors, dict(tally)


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("india_ages: Census of India 2011, table C-13")
    main_records, successor_records, tally = build()
    for kind, n in sorted(tally.items()):
        log(f"  {n:4d} {kind}")
    write_json(PROCESSED / "india_age.json", main_records)
    write_json(PROCESSED / "india_age_successors.json", successor_records)
    log(f"  {len(main_records)} records in india_age.json, "
        f"{len(successor_records)} in india_age_successors.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
