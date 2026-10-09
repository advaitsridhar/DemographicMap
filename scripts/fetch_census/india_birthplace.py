#!/usr/bin/env python3
"""India -- Census 2011 table D-01, place of birth: country of birth on the ethnicity field.

India's census does not ask ethnicity. It does count, for every person, where
they were born. Table D-01, *Population classified by place of birth and
sex*, is published as one workbook per state on the censusindia.gov.in NADA
catalogue (studies PC11_D01-00 to PC11_D01-35, numbered 10671 to 10706): for
India, every state and every one of the 640 districts of 2011, the people
born in India and the people born outside it -- by continent, by the 34
countries the table names and the rest of each continent as "Elsewhere" --
and those whose birthplace could not be classified. On 19 September 2026 the
map's owner decided that the ethnicity field may carry a count of
nationality, citizenship or country of birth as a real composition, under an
``ethnicity_basis`` that says which (``nordic_origin.py`` writes Sweden's
register that way). This module is that decision for India, basis "country
of birth".

**Labels.** Everyone born in India is "Indian". A country of birth is named,
by its people's adjective, where at least ``NAMED_FLOOR`` people across India
were born in it -- Bangladesh (2,747,062), Pakistan (918,982), Nepal
(810,158), Sri Lanka (198,193) and Myanmar (59,282); every other country,
named by the table or not, is "Other", and the table's "Unclassifiable" is
"Not stated". A label names the country a person was born in, under its
present name, and nothing more: not a citizenship and not an ethnic group,
which every note says.

**Checks**, each of which stops the run: on every row, males and females
make persons; in every unit, born in India, born outside it and
unclassifiable make the total, the state of enumeration and the other states
make born in India, the place of enumeration, the rest of the district and
the other districts make the state of enumeration, the states named make the
other states, the five continents make born outside India, and each
continent its countries and its "Elsewhere"; every state's districts make
the state's own row, label by label; the states make the all-India row,
which must print 1,210,854,977 people; there are 640 districts; and a
district bound to a shape must carry, on that shape, the 2011 count
``india_census.py`` put there from table C-01 -- two tables typeset apart,
so a code bound to the wrong polygon shows up as two populations.

**Which shapes.** As ``india_ages.py``, for the same reasons: a district
unchanged since 2011 takes its own row, bound by its census code. The shapes
that kept a district's name after a newer district was cut out of them, the
districts created since and the successors of the three divided whole have no
row of their own, and say so. The shapes that kept a name are given the
undivided district's row in a second file, ``india_birthplace_successors.json``,
with india_census's sentence saying how much of the ground they keep -- the
convention India's religion and language follow on the same shapes; which
file the map reads is one line in the build. The new districts get nothing in
either: a predecessor's shares would be an estimate, and India's ethnicity is
a declared field on which ``check_no_estimate_on_policy_field`` refuses one.

States: the state's own row, except Telangana and the residual Andhra
Pradesh, Ladakh and the rest of Jammu and Kashmir, each summed from its 2011
districts, and Dadra and Nagar Haveli and Daman and Diu, summed from the two
territories' rows.

Usage:
    python -m scripts.fetch_census.india_birthplace
"""

from __future__ import annotations

import argparse
import collections
import io
import re
from typing import Any, Iterable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, shares, write_json
from .india_ages import census_population, code, number, state_name_2011
from .india_census import (
    BOUNDARY_ARTEFACTS, CREATED_AFTER_2011, NATIONAL_CONTROLS, NEW_DISTRICT_ALIASES,
    SPLIT_STATES, STATE_IN_2011, SUBDIVIDED_SINCE_2011, lost_territory,
    lost_territory_reason, subdivided_reason,
)
from .south_asia_common import fold, load_units

YEAR = 2011
NADA = "https://censusindia.gov.in/nada/index.php/catalog"
SOURCE = ("Census of India 2011, table D-01: population classified by place of "
          "birth and sex (Registrar General & Census Commissioner)")
LICENCE = "Government of India open data (GODL-India)"
# The catalogue's studies PC11_D01-00 (India) to PC11_D01-35; each study's one
# file is linked from its related-materials page, which is read, not guessed.
STUDIES = range(10671, 10707)
INDIA_STUDY = 10671
BASIS = "country of birth"
DECISION = "19 September 2026"
INDIA_POPULATION = NATIONAL_CONTROLS["population"][0]
DISTRICTS_2011 = NATIONAL_CONTROLS["districts"][0]

HOME = "Indian"
OTHER = "Other"
UNKNOWN = "Not stated"
# A country of birth is named where at least this many people across India
# were born in it: the five neighbours above, and none of the 29 others the
# table names (the United Arab Emirates are next, at 24,634).
NAMED_FLOOR = 50_000
# The table's spelling of a country -> its people's adjective. A country over
# the floor that is missing here stops the run rather than vanish into "Other".
ADJECTIVES = {
    "Bangladesh": "Bangladeshi", "Pakistan": "Pakistani", "Nepal": "Nepalese",
    "Sri Lanka": "Sri Lankan", "Mayanmar": "Burmese", "Myanmar": "Burmese",
}

# The table's own rows, as it words them (folded), and what each is.
ROWS = {
    "total population": "total",
    "born within india": "india",
    "within the state of enumeration": "within",
    "born in the place of enumeration": "place",
    "born elsewhere in the district of enumeration": "district",
    "born in other districts of the state": "districts",
    "states in india beyond the state of enumeration": "states",
    "born outside india": "outside",
    "unclassifiable": "unclassifiable",
}

Triple = tuple[int, int, int]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_rows(rows: Iterable[list[Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """{(state code, district code): unit} from one D-01 sheet's rows.

    Every unit is a run of rows -- "Total Population", then the birthplaces --
    under one area; the codes are the census's own, zero-padded, "000" for
    the state's own row and "00" for India. Only the total columns (persons,
    males, females) are read; the rural and urban ones beside them are not
    needed.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        row = list(row) + [None] * (8 - len(row))
        state, district = code(row[1], 2), code(row[2], 3)
        if state is None or district is None:
            continue
        area, place = str(row[3] or "").strip(), " ".join(str(row[4] or "").split())
        persons, males, females = number(row[5]), number(row[6]), number(row[7])
        if persons is None or males is None or females is None:
            raise SystemExit(f"india_birthplace: {area}: the row {place!r} has no figures")
        unit = out.setdefault((state, district), {"state": state, "district": district,
                                                  "name": area, "rows": []})
        unit["rows"].append((place, persons, males, females))
    return out


def read_workbook(blob: bytes) -> dict[tuple[str, str], dict[str, Any]]:
    if blob[:2] == b"PK":
        import openpyxl                             # noqa: PLC0415
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        return read_rows(book.worksheets[0].iter_rows(values_only=True))
    import xlrd                                     # noqa: PLC0415
    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    return read_rows(sheet.row_values(i) for i in range(sheet.nrows))


def add(*triples: Triple) -> Triple:
    return (sum(t[0] for t in triples), sum(t[1] for t in triples),
            sum(t[2] for t in triples))


def interpret(unit: dict[str, Any]) -> dict[str, Any]:
    """One unit's birthplaces, every sum the table implies checked.

    Persons only are kept: {"total", "india", "outside", "unclassifiable",
    "elsewhere" (the continents' unnamed rest), "countries" (by the table's
    name)}.
    """
    where = f"india_birthplace: {unit['name']}"
    figures: dict[str, Triple] = {}
    named_states: list[Triple] = []
    continents: list[dict[str, Any]] = []
    section = None
    for place, persons, males, females in unit["rows"]:
        if males + females != persons:
            raise SystemExit(f"{where}: {place}: {males:,} males and {females:,} females "
                             f"make {males + females:,}, not {persons:,}")
        key = place.lower()
        triple = (persons, males, females)
        kind = ROWS.get(key)
        if kind is not None:
            if kind in figures:
                raise SystemExit(f"{where} prints {place!r} twice")
            figures[kind] = triple
            section = kind
        elif key.startswith("countries in "):
            continents.append({"name": place, "total": triple, "countries": {},
                               "elsewhere": None})
            section = "continent"
        elif section == "states":
            named_states.append(triple)
        elif section == "continent" and key == "elsewhere":
            if continents[-1]["elsewhere"] is not None:
                raise SystemExit(f"{where}: {continents[-1]['name']} has two 'Elsewhere' rows")
            continents[-1]["elsewhere"] = triple
        elif section == "continent":
            if place in continents[-1]["countries"]:
                raise SystemExit(f"{where} prints {place!r} twice")
            continents[-1]["countries"][place] = triple
        else:
            raise SystemExit(f"{where}: a row the table does not have: {place!r}")
    missing = sorted(set(ROWS.values()) - set(figures))
    if missing:
        raise SystemExit(f"{where} has no row for {missing}")

    def agree(what: str, got: Triple, want: Triple) -> None:
        if got != want:
            raise SystemExit(f"{where}: {what} make {got}, not {want}")

    agree("born in India, born outside and unclassifiable",
          add(figures["india"], figures["outside"], figures["unclassifiable"]),
          figures["total"])
    agree("the state of enumeration and the other states",
          add(figures["within"], figures["states"]), figures["india"])
    agree("the place, the rest of the district and the other districts",
          add(figures["place"], figures["district"], figures["districts"]),
          figures["within"])
    agree("the states named", add(*named_states), figures["states"])
    agree("the continents", add(*(c["total"] for c in continents)), figures["outside"])
    countries: collections.Counter[str] = collections.Counter()
    elsewhere = 0
    for continent in continents:
        if continent["elsewhere"] is None:
            raise SystemExit(f"{where}: {continent['name']} has no 'Elsewhere' row")
        agree(f"{continent['name']}'s countries and the rest",
              add(*continent["countries"].values(), continent["elsewhere"]),
              continent["total"])
        for name, triple in continent["countries"].items():
            countries[name] += triple[0]
        elsewhere += continent["elsewhere"][0]
    return {"name": unit["name"], "state": unit["state"], "district": unit["district"],
            "total": figures["total"][0], "india": figures["india"][0],
            "outside": figures["outside"][0],
            "unclassifiable": figures["unclassifiable"][0],
            "elsewhere": elsewhere, "countries": countries}


def combine(parts: list[dict[str, Any]], name: str) -> dict[str, Any]:
    countries: collections.Counter[str] = collections.Counter()
    for part in parts:
        countries.update(part["countries"])
    return {"name": name, "state": None, "district": None,
            "total": sum(p["total"] for p in parts),
            "india": sum(p["india"] for p in parts),
            "outside": sum(p["outside"] for p in parts),
            "unclassifiable": sum(p["unclassifiable"] for p in parts),
            "elsewhere": sum(p["elsewhere"] for p in parts), "countries": countries}


def same(where: str, got: dict[str, Any], want: dict[str, Any]) -> None:
    """Two readings of one area agree, label by label."""
    for key in ("total", "india", "outside", "unclassifiable", "elsewhere"):
        if got[key] != want[key]:
            raise SystemExit(f"india_birthplace: {where}: {key} {got[key]:,} against "
                             f"{want[key]:,}")
    for country in set(got["countries"]) | set(want["countries"]):
        if got["countries"][country] != want["countries"][country]:
            raise SystemExit(f"india_birthplace: {where}: born in {country} "
                             f"{got['countries'][country]:,} against "
                             f"{want['countries'][country]:,}")


def check_all(units: dict[tuple[str, str], dict[str, Any]], india: dict[str, Any]) -> None:
    if india["total"] != INDIA_POPULATION:
        raise SystemExit(f"india_birthplace: the all-India row prints {india['total']:,}, "
                         f"not {INDIA_POPULATION:,}")
    states = {s: u for (s, d), u in units.items() if d == "000"}
    districts = {k: u for k, u in units.items() if k[1] != "000"}
    if len(districts) != DISTRICTS_2011:
        raise SystemExit(f"india_birthplace: {len(districts)} districts in the workbooks, "
                         f"not {DISTRICTS_2011}")
    for state, row in states.items():
        inside = [u for (s, d), u in districts.items() if s == state]
        same(f"state {state} ({row['name']}) against its districts",
             combine(inside, row["name"]), row)
    same("the states against India", combine(list(states.values()), "India"), india)
    log(f"  {len(states)} states and {len(districts)} districts reconcile, label by "
        f"label, to India's {india['total']:,}")


# ---------------------------------------------------------------------------
# Labels and fields
# ---------------------------------------------------------------------------

def named_countries(india: dict[str, Any]) -> dict[str, str]:
    """The table's name -> the label, for every country over the floor."""
    out = {}
    for country, people in sorted(india["countries"].items()):
        if people < NAMED_FLOOR:
            continue
        label = ADJECTIVES.get(country)
        if label is None:
            raise SystemExit(f"india_birthplace: {people:,} people across India were "
                             f"born in {country!r}, which has no label here")
        out[country] = label
    return out


def composition(unit: dict[str, Any], named: dict[str, str]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter(
        {HOME: unit["india"], UNKNOWN: unit["unclassifiable"], OTHER: unit["elsewhere"]})
    for country, people in unit["countries"].items():
        counts[named.get(country, OTHER)] += people
    if sum(counts.values()) != unit["total"]:
        raise SystemExit(f"india_birthplace: {unit['name']}: the labels make "
                         f"{sum(counts.values()):,} of {unit['total']:,}")
    return {label: n for label, n in counts.items() if n}


def ethnicity_fields(unit: dict[str, Any], named: dict[str, str], url: str,
                     extra: str = "") -> dict[str, Any]:
    counts = composition(unit, named)
    note = (f"Census of India 2011, table D-01: the {unit['total']:,} people counted "
            f"here by where they were born -- {unit['india']:,} in India, "
            f"{unit['outside']:,} outside it and {unit['unclassifiable']:,} whose "
            f"birthplace could not be classified. India's census does not ask "
            f"ethnicity. Each label names a country of birth under its present name, "
            f"not a citizenship or an ethnic group; 'Other' is every country fewer "
            f"than {NAMED_FLOOR:,} people across India were born in. Written by the "
            f"map owner's decision of {DECISION}.{extra}")
    return {"ethnicity": shares(counts, total=unit["total"]), "ethnicity_year": YEAR,
            "ethnicity_basis": BASIS, "ethnicity_note": note,
            "sources": [{"field": "ethnicity", "name": SOURCE, "url": url,
                         "year": YEAR, "license": LICENCE}]}


def listed(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]


def lost_reason(name: str, share: int, gone: tuple[tuple[str, int], ...]) -> str:
    """Why a shape that kept a district's name carries no count of birthplaces."""
    names = [child for child, _ in gone]
    when = " and ".join(str(y) for y in sorted({year for _, year in gone}))
    return (f"Census of India 2011 table D-01 counts place of birth for districts as "
            f"they stood in 2011, and its {name} row is the undivided district, before "
            f"{listed(names)} ({when}) {'were' if len(names) > 1 else 'was'} carved out "
            f"of it. The shape drawn here keeps about {share}% of that ground. No count "
            f"exists for the district as drawn, and the undivided district's is not "
            f"shown on part of its ground.")


def created_reason(name: str, year: int, predecessors: tuple[str, ...]) -> str:
    return (f"{name} did not exist at the 2011 census: it was created in {year}, out "
            f"of {listed(list(predecessors))}. Census of India 2011 table D-01 counts "
            f"place of birth for the 640 districts of 2011 and this is not one of them, "
            f"and India's next census has not been held, so no count exists for this "
            f"district.")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def study_file(study: int) -> str:
    """The one download link on a study's related-materials page."""
    page = http_get(f"{NADA}/{study}/related-materials", cache=False, aia=True)
    links = sorted(set(re.findall(rf"{re.escape(NADA)}/{study}/download/\d+", page)))
    if len(links) != 1:
        raise SystemExit(f"india_birthplace: study {study} links {len(links)} files: {links}")
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
        read = {key: interpret(unit) for key, unit in read_workbook(blob).items()}
        states = {s for s, d in read if d == "000" and s != "00"}
        log(f"  study {study}: {len(read)} units, state(s) {sorted(states)}, "
            f"{len(blob):,} bytes")
        if study == INDIA_STUDY:
            # The all-India workbook repeats every state's own row as well:
            # India's row is taken from it, the states from their own files.
            india = read.get(("00", "000"))
            continue
        for key, unit in read.items():
            if key in units:
                raise SystemExit(f"india_birthplace: {unit['name']} is in two workbooks")
            units[key] = unit
        for state in states:
            urls[state] = url
    if india is None:
        raise SystemExit("india_birthplace: the all-India workbook has no India row")
    return units, urls, india


# ---------------------------------------------------------------------------
# Binding and records
# ---------------------------------------------------------------------------

def district_name(unit: dict[str, Any]) -> str:
    name = re.sub(r"^District\s*-\s*", "", unit["name"]).strip()
    return re.sub(r"\s*\(\d+\)\s*$", "", name)


def records(units: dict[tuple[str, str], dict[str, Any]], urls: dict[str, str],
            named: dict[str, str], shapes1: list[dict[str, Any]] | None = None,
            shapes2: list[dict[str, Any]] | None = None
            ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    shapes1 = load_units("IND", "admin1") if shapes1 is None else shapes1
    shapes2 = load_units("IND", "admin2") if shapes2 is None else shapes2
    state_of_shape = {u["id"]: u for u in shapes1}
    by_code = {}
    for shape in shapes2:
        district = (shape.get("codes") or {}).get("census2011_district")
        if district:
            by_code[district.zfill(3)] = shape
    lost_keys = {(fold(s), fold(d)): v for (s, d), v in lost_territory().items()}
    main: list[dict[str, Any]] = []
    successors: list[dict[str, Any]] = []
    tally: collections.Counter[str] = collections.Counter()

    for (state, district), unit in sorted(units.items()):
        if district == "000":
            continue
        name = district_name(unit)
        shape = by_code.get(district)
        if shape is None:
            tally["2011 district with no shape (divided since)"] += 1
            continue
        counted = census_population(shape)
        if counted is not None and counted != unit["total"]:
            raise SystemExit(
                f"india_birthplace: {name} (code {district}) has {unit['total']:,} people "
                f"in D-01 and its shape carries {counted:,} from C-01; the code is bound "
                f"to the wrong polygon")
        state_shape = state_of_shape.get(shape.get("parent"))
        state_key = state_name_2011(state_shape["name"]) if state_shape else ""
        names = {fold(name), fold(shape.get("name")), fold(shape.get("site_name")),
                 *(fold(a) for a in shape.get("aliases") or ())}
        hit = next((lost_keys[(state_key, n)] for n in names
                    if (state_key, n) in lost_keys), None)
        label = shape.get("site_name") or name
        key = f"IND-BIRTH-{state}-{district}"
        if hit is None:
            main.append(record(key, label, level="admin2", parent="IND", country="IND",
                               match_by="shape_id", shape_id=shape["id"],
                               **ethnicity_fields(unit, named, urls[state])))
            tally["district, unchanged since 2011"] += 1
            continue
        share, gone = hit
        main.append(record(key, label, level="admin2", parent="IND", country="IND",
                           match_by="shape_id", shape_id=shape["id"],
                           ethnicity=gap(NOT_AVAILABLE, lost_reason(name, share, gone)),
                           sources=[{"field": "ethnicity", "name": SOURCE,
                                     "url": urls[state], "year": YEAR,
                                     "license": LICENCE}]))
        successors.append(record(
            key, label, level="admin2", parent="IND", country="IND",
            match_by="shape_id", shape_id=shape["id"],
            **ethnicity_fields(unit, named, urls[state],
                               " " + lost_territory_reason(name, share, gone))))
        tally["shape that kept a name after a split"] += 1

    # The shapes with no 2011 code, each with its reason.
    created = {}
    for state, entries in CREATED_AFTER_2011.items():
        for name, year, predecessors in entries:
            for key in {fold(name), fold(NEW_DISTRICT_ALIASES.get(name, ""))} - {""}:
                created[(fold(state), key)] = (name, year, predecessors)
    divided = {fold(successor): undivided
               for undivided, names in SUBDIVIDED_SINCE_2011.items()
               for successor in names}
    for shape in shapes2:
        if (shape.get("codes") or {}).get("census2011_district"):
            continue
        state_now = fold(state_of_shape.get(shape.get("parent"), {}).get("name"))
        names = {fold(shape.get("name")), fold(shape.get("site_name")),
                 *(fold(a) for a in shape.get("aliases") or ())} - {""}
        label = shape.get("site_name") or shape["name"]
        entry = next((created[(state_now, n)] for n in names
                      if (state_now, n) in created), None)
        undivided = next((divided[n] for n in names if n in divided), None)
        artefact = next((BOUNDARY_ARTEFACTS[k][1] for k in BOUNDARY_ARTEFACTS
                         if fold(k) in names), None)
        if entry is not None:
            reason, kind = created_reason(*entry), "district created since 2011"
        elif undivided is not None:
            reason = subdivided_reason(undivided.title())
            kind = "successor of a district divided whole"
        elif artefact is not None:
            reason, kind = artefact, "boundary artefact"
        else:
            raise SystemExit(f"india_birthplace: {label} has no 2011 code and is in no "
                             "table of districts created or divided since")
        main.append(record(f"IND-BIRTH-{fold(label)}-{shape['id'][-6:]}", label,
                           level="admin2", parent="IND", country="IND",
                           match_by="shape_id", shape_id=shape["id"],
                           ethnicity=gap(NOT_AVAILABLE, reason)))
        tally[kind] += 1

    # States, as drawn.
    by_state_code = {s: u for (s, d), u in units.items() if d == "000"}
    for shape in shapes1:
        folded = fold(shape.get("site_name") or shape["name"])
        state_code = (shape.get("codes") or {}).get("census2011_state")
        extra = ""
        if folded in (fold("Telangana"), fold("Andhra Pradesh")):
            split, new = SPLIT_STATES["Telangana"], folded == fold("Telangana")
            extra = (" Summed from the ten 2011 districts that became the state in "
                     "2014. The seven Khammam mandals moved to Andhra Pradesh that "
                     "year for the Polavaram project are inside them -- 190,304 "
                     "people, 0.5% of this total -- and D-01 publishes nothing below "
                     "the district to take them out." if new else
                     " Summed from the thirteen 2011 districts left to the state when "
                     "Telangana was formed in 2014; the seven Khammam mandals it "
                     "gained that year (190,304 people) are outside them, and D-01 "
                     "publishes nothing below the district to add them in.")
        elif folded in (fold("Ladakh"), fold("Jammu and Kashmir")):
            split, new = SPLIT_STATES["Ladakh"], folded == fold("Ladakh")
            extra = (" Summed from Leh (Ladakh) and Kargil, the 2011 districts that "
                     "became the union territory in 2019." if new else
                     " Summed from the 2011 districts that remained in Jammu and "
                     "Kashmir when Ladakh was separated in 2019.")
        else:
            split, new = None, False
        if split is not None:
            inside = [u for (s, d), u in units.items() if s == split.state_code
                      and d != "000" and (int(d) in split.codes) == new]
            whole = combine(inside, shape["name"])
            expect = split.population if new else split.residual
            if whole["total"] != expect:
                raise SystemExit(f"india_birthplace: {shape['name']} sums to "
                                 f"{whole['total']:,} from its 2011 districts, not {expect:,}")
            url = urls[split.state_code]
        elif state_code == "26":
            whole = combine([by_state_code["25"], by_state_code["26"]], shape["name"])
            extra = (" Summed from the two union territories the census counted, "
                     "Dadra and Nagar Haveli and Daman and Diu, merged in 2020.")
            url = urls["26"]
        elif state_code in by_state_code:
            whole, url = by_state_code[state_code], urls[state_code]
        else:
            raise SystemExit(f"india_birthplace: no D-01 row for {shape['name']} "
                             f"(code {state_code})")
        counted = census_population(shape)
        merged_part = state_code == "26" and counted in (
            by_state_code["25"]["total"], by_state_code["26"]["total"])
        if counted is not None and counted != whole["total"] and not merged_part:
            raise SystemExit(f"india_birthplace: {shape['name']} has {whole['total']:,} in "
                             f"D-01 and {counted:,} on its shape")
        main.append(record(
            f"IND-BIRTH-STATE-{fold(shape['name'])}", shape.get("site_name") or shape["name"],
            level="admin1", parent="IND", country="IND", match_by="shape_id",
            shape_id=shape["id"], **ethnicity_fields(whole, named, url, extra)))
        tally["state"] += 1
    return main, successors, dict(tally)


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("india_birthplace: Census of India 2011, table D-01")
    units, urls, india = fetch_all()
    check_all(units, india)
    named = named_countries(india)
    shown = [f"{label} ({india['countries'][country]:,})" for country, label in named.items()]
    log(f"  named: {', '.join(shown)}")
    main_records, successor_records, tally = records(units, urls, named)
    for kind, n in sorted(tally.items()):
        log(f"  {n:4d} {kind}")
    write_json(PROCESSED / "india_birthplace.json", main_records)
    write_json(PROCESSED / "india_birthplace_successors.json", successor_records)
    log(f"  {len(main_records)} records in india_birthplace.json, "
        f"{len(successor_records)} in india_birthplace_successors.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
