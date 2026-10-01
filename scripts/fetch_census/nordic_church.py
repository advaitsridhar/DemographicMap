#!/usr/bin/env python3
"""Religion from the national churches' own membership counts: Sweden's kommuner, Finland's sub-regions.

Neither country's statistics office publishes religion below the country.
Sweden's census is compiled from registers and the state has kept no record
of religion since the Church of Sweden separated from it in 2000; Finland's
population register does record every resident's religious community, but
Statistics Finland publishes it for the whole country only (table 11rx). What
each majority church does publish is its own membership by municipality, and
the gap round's brief allows exactly that "where the statistics office
publishes none": the church's members against everyone else, with the
official population as the denominator, a count of membership and not of
belief, said so in every note.

* **Sweden** -- the Church of Sweden's "Medlemmar i Svenska kyrkan i
  förhållande till folkmängd den 31.12.2021 per församling, kommun och län
  samt riket" (its statistics folder, ``NyckeltalLKF(1).pdf``), the latest
  edition by kommun. Both columns read here -- the population and the
  Church's members -- are Statistics Sweden's, produced for the Church (the
  table's own first page says so). The 290 kommuner have not changed since
  2003; they are bound by SCB's codes, as ``sweden.py`` binds them. The län
  are not written: the European Social Survey already gives each a fuller
  composition, which a two-row count would displace.
* **Finland** -- the Evangelical Lutheran Church's membership on 31 December
  2020 by economic unit (``Jäsenmäärä2020.xlsx`` on kirkontilastot.fi: every
  parish union and independent parish), the last year it published as a
  file; later years are on Tableau only. A unit is a municipality's parishes
  or a few neighbouring municipalities', so each is placed in the 2020
  sub-region its municipalities lie in -- the map's own -- and set against
  Statistics Finland's population of the same day (11rf). A unit whose
  municipalities lie in two sub-regions (Sund-Vårdö on Åland) is left out
  with those municipalities' people, and the note says so; a parish with no
  territory (the German congregation) is left out of every sub-region.

Labels: "Church of Sweden" and "Not a member of the national church" for
Sweden, as Denmark's register reads; "Evangelical Lutheran Church of Finland"
and "Not a member of the Evangelical Lutheran Church of Finland" for Finland,
where the Orthodox Church is a national church too.

Checks: every row is read with its own percentage (Sweden) or the file's own
total (Finland); the kommuner make their län and the Church's population of
each kommun sits within a few per cent of SCB's own; every drawn unit is bound
one to one; a sub-region's members never exceed its people.

Usage:
    python -m scripts.fetch_census.nordic_church --country SWE
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import bind_rows, request, request_json, unplaced
from .pxweb import unstack

BASIS = "registered membership"

# ---------------------------------------------------------------------------
# Sweden
# ---------------------------------------------------------------------------

SVK_URLS = (
    "https://www.svenskakyrkan.se/filer/1374643/NyckeltalLKF(1).pdf",
    "https://web.archive.org/web/20220401215825id_/https://www.svenskakyrkan.se/filer/1374643/"
    "NyckeltalLKF(1).pdf",
)
SVK_PAGE = "https://www.svenskakyrkan.se/statistik"
SVK_YEAR = 2021
SVK_TITLE = "Medlemmar i Svenska kyrkan i förhållande till folkmängd den 31.12.2021"
SWEDEN_CHURCH = "Church of Sweden"
SWEDEN_OUTSIDE = "Not a member of the national church"
# Each row prints two shares after its counts: the residents who are members
# of the Church, in whatever parish ("Folkbokförda medlemmar inom
# församlingen i % av folkmängden"), and the members of its own parishes
# against its population ("Medlemmar i församlingen i % av folkmängden") --
# the second is the counts' own ratio, rounded. They differ only where a
# parish without territory counts members who live elsewhere (Karlskrona's
# admiralty parish: 66.0% against 66.1%). The split of the counts must match
# the second to rounding, or the first within PCT_SLACK when only it is printed.
RATIO_SLACK = 0.06
PCT_SLACK = 0.6
ROW = re.compile(r"^(?P<name>.+?) (?P<kind>kommun|län)(?: \(\d+\))? (?P<rest>\d.*)$")
UNPLACED = "På kommunen skrivna "


def numbers(groups: list[str]) -> int | None:
    """Digit groups printed with a space for the thousands -> the number, or
    None if they cannot be one ("027" opening a number, a short inner group)."""
    if not groups or any(not g.isdigit() for g in groups):
        return None
    if len(groups[0]) > 3 or (len(groups) > 1 and groups[0].startswith("0")):
        return None
    if any(len(g) != 3 for g in groups[1:]):
        return None
    return int("".join(groups))


def percent(token: str) -> float | None:
    found = re.fullmatch(r"(\d+),(\d)%", token)
    return float(f"{found.group(1)}.{found.group(2)}") if found else None


def population_and_members(rest: str) -> tuple[int, int, float]:
    """The first two numbers of a row, told apart by the shares printed after
    them, and the first share: the residents who are members, in whatever parish.

    The table prints thousands with a space, so "556 399 71,8%" could be one
    number or two; it is the split whose members-over-population matches the
    printed ratio, members never more than the population. Anything but one
    such split stops the run. A leading code in brackets is passed over."""
    tokens = re.sub(r"^\(\d+\)\s+", "", rest).split()
    groups = []
    for token in tokens:
        if not re.fullmatch(r"\d{1,3}", token):
            break
        groups.append(token)
    shares_ = [percent(t) for t in tokens[len(groups):len(groups) + 2]]
    if not shares_ or shares_[0] is None:
        raise SystemExit(f"svenska kyrkan: no share after the counts in {rest[:80]!r}")
    residents = shares_[0]
    ratio, slack = ((shares_[1], RATIO_SLACK) if len(shares_) > 1 and shares_[1] is not None
                    else (residents, PCT_SLACK))
    fits = []
    for i in range(1, len(groups)):
        pop, members = numbers(groups[:i]), numbers(groups[i:])
        if pop and members is not None and members <= pop \
                and abs(100 * members / pop - ratio) <= slack:
            fits.append((pop, members))
    if len(fits) != 1:
        raise SystemExit(f"svenska kyrkan: {len(fits)} readings of {rest[:80]!r}: {fits}")
    return fits[0][0], fits[0][1], residents


Row = tuple[int, int, float]


def svk_rows(lines: list[str]) -> tuple[dict[str, Row], dict[str, Row], Row | None]:
    """{kommun: (population, members, residents' share)}, {län: ...} and the
    row of people registered in a kommun without a property ("På kommunen
    skrivna"), which the table prints once, for the whole country."""
    kommuner: dict[str, Row] = {}
    lan: dict[str, Row] = {}
    unplaced_row = None
    for line in lines:
        line = " ".join(line.split())
        if line.startswith(UNPLACED):
            if unplaced_row is not None:
                raise SystemExit("svenska kyrkan: two rows of people without a property")
            unplaced_row = population_and_members(line[len(UNPLACED):])
            continue
        found = ROW.match(line)
        if not found or "församling" in found.group("name"):
            continue
        target = kommuner if found.group("kind") == "kommun" else lan
        name = found.group("name")
        if name in target:
            raise SystemExit(f"svenska kyrkan: {name} {found.group('kind')} twice")
        target[name] = population_and_members(found.group("rest"))
    return kommuner, lan, unplaced_row


def match_names(printed: list[str], scb: dict[str, str]) -> dict[str, str]:
    """The table's genitive names ("Karlshamns", "Faluns", "Borås") -> SCB's
    codes: the name as printed, else without its genitive s. One to one, or
    the run stops."""
    by_name = {fold(n): c for c, n in scb.items()}
    out, missing = {}, []
    for name in printed:
        code = by_name.get(fold(name))
        if code is None and name.endswith("s"):
            code = by_name.get(fold(name[:-1]))
        if code is None:
            missing.append(name)
        else:
            out[name] = code
    twice = sorted({c for c in out.values() if list(out.values()).count(c) > 1})
    if missing or twice:
        raise SystemExit(f"svenska kyrkan: no SCB code for {missing}; codes twice {twice}")
    return out


def sweden() -> list[dict[str, Any]]:
    import pdfplumber
    from .sweden import BASE, bind_kommuner
    raw, used = None, None
    for url in SVK_URLS:
        try:
            raw = request(url, accept="application/pdf,*/*", attempts=3)
        except (SystemExit, Exception) as exc:
            log(f"  {url}: {str(exc)[:120]}")
            continue
        if raw.startswith(b"%PDF"):
            used = url
            break
    if not used:
        raise SystemExit("svenska kyrkan: no copy of the table answered")
    with pdfplumber.open(io.BytesIO(raw)) as doc:
        lines = [line for page in doc.pages for line in (page.extract_text() or "").splitlines()]
    if not any(SVK_TITLE in " ".join(line.split()) for line in lines[:5]):
        raise SystemExit(f"svenska kyrkan: {used} is not the 2021 table: {lines[:2]}")
    kommuner, lan, nowhere = svk_rows(lines)
    log(f"  {used}: {len(lines):,} lines, {len(kommuner)} kommuner, {len(lan)} län, "
        f"registered without a property: {nowhere}")
    meta = {v["code"]: v for v in request_json(BASE.format(lang="sv", table="BefolkningNy"))
            ["variables"]}
    sv = dict(zip(meta["Region"]["values"], meta["Region"]["valueTexts"]))
    scb_kommuner = {c: n for c, n in sv.items() if len(c) == 4}
    code_of = match_names(list(kommuner), scb_kommuner)
    if len(code_of) != len(scb_kommuner):
        raise SystemExit(f"svenska kyrkan: {len(code_of)} kommuner of SCB's {len(scb_kommuner)}")
    # The kommuner must make their län, and the län with the people registered
    # without a property the whole of Sweden.
    lan_code = {name: next((c for c, n in sv.items() if len(c) == 2 and
                            fold(n.removesuffix(" län").rstrip("s")) ==
                            fold(name.rstrip("s"))), None) for name in lan}
    if None in lan_code.values() or len(set(lan_code.values())) != 21:
        raise SystemExit(f"svenska kyrkan: län not matched: {lan_code}")
    for name, code in lan_code.items():
        parts = [kommuner[k] for k, c in code_of.items() if c[:2] == code]
        for i, what in ((0, "population"), (1, "members")):
            if sum(p[i] for p in parts) != lan[name][i]:
                raise SystemExit(f"svenska kyrkan: {name}'s kommuner make "
                                 f"{sum(p[i] for p in parts):,} {what} of {lan[name][i]:,}")
    # SCB's own count of the same day: the table's kommun populations leave
    # out only the people SCB cannot place on a property.
    scb = scb_population()
    worst = max((abs(scb[c] - kommuner[k][0]) / scb[c], k) for k, c in code_of.items())
    log(f"  the table's kommun populations against SCB's of the same day: worst "
        f"{100 * worst[0]:.2f}% ({worst[1]})")
    if worst[0] > 0.03:
        raise SystemExit(f"svenska kyrkan: {worst[1]} is {100 * worst[0]:.1f}% off SCB's count")
    total = sum(row[0] for row in lan.values()) + (nowhere[0] if nowhere else 0)
    if abs(total - scb["00"]) > 0.0005 * scb["00"]:
        raise SystemExit(f"svenska kyrkan: the län and the unplaced make {total:,} against "
                         f"SCB's {scb['00']:,.0f}")
    log(f"  län and the people without a property make {total:,} against SCB's {scb['00']:,.0f}")
    bound = bind_kommuner(sv, sorted(scb_kommuner))
    records = []
    for name, code in sorted(code_of.items(), key=lambda kv: kv[1]):
        pop, members, residents = kommuner[name]
        elsewhere = (f" Of the kommun's residents, {residents:.1f}% are members, in whatever "
                     "parish; the count above is of the members of its own parishes, wherever "
                     "they live -- the two differ where a parish without territory (Karlskrona's "
                     "admiralty parish) has members in more than one kommun."
                     if abs(residents - 100 * members / pop) >= 0.15 else "")
        records.append(record(
            f"SWE-SVK-{code}", sv[code], level="admin2", parent="SWE", country="SWE",
            parent_name=sv[code[:2]], codes={"scb": code}, match_by="shape_id",
            shape_id=bound[code],
            religion=shares({SWEDEN_CHURCH: members, SWEDEN_OUTSIDE: pop - members}, total=pop),
            religion_year=SVK_YEAR, religion_basis=BASIS,
            religion_note=(
                f"Members of the Church of Sweden on 31 December {SVK_YEAR} against the kommun's "
                f"population the same day, {members:,} of {pop:,}, both counted by Statistics "
                "Sweden for the Church (Svenska kyrkan, 'Medlemmar i Svenska kyrkan i förhållande "
                f"till folkmängd den 31.12.{SVK_YEAR} per församling, kommun och län samt "
                "riket'): the Church's registered membership, not belief. Everyone else -- "
                "members of other faiths and of none alike -- is one group: no Swedish register "
                "records religion, and the Church's is the only membership count published by "
                "kommun. The population leaves out the few people registered in the kommun "
                "without a property, whom SCB cannot place in a parish." + elsewhere),
            sources=[{"field": "religion", "name": "Church of Sweden (Svenska kyrkan), "
                      f"members against population 31 December {SVK_YEAR}, counted by SCB",
                      "url": used, "year": SVK_YEAR}]))
    return records


def scb_population() -> dict[str, float]:
    """SCB's register population on 31 December of SVK_YEAR, by region."""
    from .sweden import BASE
    url = BASE.format(lang="en", table="BefolkningNy")
    meta = {v["code"]: v for v in request_json(url)["variables"]}
    content = next(c for c in meta["ContentsCode"]["values"])
    body = request_json(url, {"query": [
        {"code": "Region", "selection": {"filter": "item", "values": meta["Region"]["values"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [content]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [str(SVK_YEAR)]}},
    ], "response": {"format": "json-stat2"}})
    out: dict[str, float] = defaultdict(float)
    for key, value in unstack(body):
        out[key["Region"][0]] += value
    return dict(out)


# ---------------------------------------------------------------------------
# Finland
# ---------------------------------------------------------------------------

EVL_URLS = (
    "https://www.kirkontilastot.fi/tiedostot/J%C3%A4senm%C3%A4%C3%A4r%C3%A42020.xlsx",
    "https://web.archive.org/web/20220705145540id_/https://www.kirkontilastot.fi/tiedostot/"
    "J%C3%A4senm%C3%A4%C3%A4r%C3%A42020.xlsx",
)
EVL_PAGE = "https://www.kirkontilastot.fi/"
EVL_YEAR = 2020
EVL_SHEET = "TalousyksikötEkonomiskaenheter"
FINLAND_CHURCH = "Evangelical Lutheran Church of Finland"
FINLAND_OUTSIDE = "Not a member of the Evangelical Lutheran Church of Finland"
POP_TABLE = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/vaerak/11rf.px"
POP_PAGE = ("https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/"
            "statfin_vaerak_pxt_11rf.px")
NAMES_KEY = ("https://data.stat.fi/api/classifications/v2/correspondenceTables/"
             "kunta_1_{y}0101%23seutukunta_1_{y}0101/maps?content=data&meta=max&lang={lang}")

# Economic units whose name is not a municipality's, or is a parish union's
# genitive: the municipalities their parishes cover. A unit spanning several
# municipalities need only be placed in the sub-region they share, and the
# run checks that they share one.
UNITS: dict[str, tuple[str, ...]] = {
    "Espoon ev.lut.srky-Esbo ev.luth.ksamf": ("Espoo",),
    "Hangö ksamf-Hangon srky": ("Hanko",),
    "Helsingin srky-Helsingfors ksamf": ("Helsinki",),
    "Hämeenlinnan srky": ("Hämeenlinna",),
    "Joensuun ev.lut.srky": ("Joensuu",),
    "Kauniaisten srky-Grankulla ksamf": ("Kauniainen",),
    "Kirkkonummen srky-Kyrkslätts ksamf": ("Kirkkonummi",),
    "Kokkolan srky-Karleby ksamf": ("Kokkola",),
    "Korsholms ksamf-Mustasaaren srky": ("Mustasaari",),
    "Kotka-Kymi": ("Kotka",),                 # Kymi joined Kotka in 1977
    "Kouvolan srky": ("Kouvola",),
    "Kristinestads ksamf-Kristiinankaupungin srky": ("Kristiinankaupunki",),
    "Kuopion ev.lut.srky": ("Kuopio",),
    "Lahden srky": ("Lahti",),
    "Lappeenrannan srky": ("Lappeenranta",),
    "Lapuan Tuomiokirkko": ("Lapua",),
    "Loviisanseudun srky-Lovisanejdens ksamf": ("Loviisa", "Lapinjärvi"),
    "Malax ksamf-Maalahden srky": ("Maalahti",),
    "Mikkelin Tuomiokirkko": ("Mikkeli",),
    "Naantalin srky": ("Naantali",),
    "Oulun ev.lut.srky": ("Oulu",),
    "Pargas ksamf-Paraisten srky": ("Parainen",),
    "Pedersörenejdens ksamf-Pietarsaarenseudun srky": ("Pietarsaari", "Pedersören kunta"),
    "Pohjois-Lapin srky": ("Inari", "Utsjoki"),
    "Porin ev.lut.srky": ("Pori",),
    "Porvoon srky-Borgå ksamf": ("Porvoo",),
    "Raseborgs ksamf-Raaseporin srky": ("Raasepori",),
    "Sipoon srky-Sibbo ksamf": ("Sipoo",),
    "Siuntion srky-Sjundeå ksamf": ("Siuntio",),
    "Säkylä-Köyliö": ("Säkylä",),             # Köyliö joined Säkylä in 2016
    "Sääksmäki": ("Valkeakoski",),
    "Tampereen ev.lut.srky-Tammerfors ev.luth.ksamf": ("Tampere",),
    "Turun ja Kaarinan srky-Åbo och St.Karins ksamf": ("Turku", "Kaarina"),
    "Vaasan srky-Vasa ksamf": ("Vaasa",),
    "Vantaan srky-Vanda ksamf": ("Vantaa",),
    "Ylä-Savon srky": ("Iisalmi", "Lapinlahti", "Sonkajärvi", "Pielavesi"),
    # Parishes formed across municipalities, each within one sub-region:
    # Jämijärvi and Pomarkku (Martinkoski), Tervo and Vesanto (Niinivesi),
    # Lemi, Savitaipale and Taipalsaari (Taipale), Hartola, Sysmä and
    # Padasjoki (Tainionvirta), and Föglö, Kökar and Sottunga.
    "Martinkoski": ("Jämijärvi", "Pomarkku"),
    "Niinivesi": ("Tervo", "Vesanto"),
    "Taipale": ("Lemi", "Savitaipale", "Taipalsaari"),
    "Tainionvirta": ("Hartola", "Sysmä", "Padasjoki"),
    "Ålands södra skärgård": ("Föglö", "Kökar", "Sottunga"),
}
# Parishes with no territory of their own, whose members live anywhere: the
# German congregation, and one this reader cannot place in one sub-region.
NO_TERRITORY = {"Tyska": "the German congregation (Deutsche Gemeinde), which has no territory",
                "Olaus Petri": "Olaus Petri församling, which this reader cannot place in one "
                               "sub-region"}


def evl_units(rows: list[tuple]) -> tuple[dict[str, int], int]:
    """The economic units sheet -> {unit: members} and the sheet's own total."""
    units: dict[str, int] = {}
    total = None
    for row in rows:
        cells = [c for c in row]
        if not cells or not isinstance(cells[0], str):
            continue
        name = " ".join(cells[0].split())
        value = next((c for c in reversed(cells) if isinstance(c, (int, float))), None)
        if value is None:
            continue
        if name.lower().startswith("talousyksiköt yhteensä"):
            total = int(value)
        elif not name.lower().startswith(("talousyksikkö", "seurakunta")):
            if name in units:
                raise SystemExit(f"jäsenmäärä: {name} twice")
            units[name] = int(value)
    if total is None:
        raise SystemExit("jäsenmäärä: no total row")
    if sum(units.values()) != total:
        raise SystemExit(f"jäsenmäärä: the units make {sum(units.values()):,} of {total:,}")
    return units, total


def unit_municipalities(unit: str, by_name: dict[str, str]) -> tuple[str, ...]:
    """An economic unit's municipality codes: from UNITS, else its own name, or
    each part of a name joined by a hyphen ("Brändö-Kumlinge", "Ingå-Inkoo")."""
    if unit in UNITS:
        missing = [n for n in UNITS[unit] if fold(n) not in by_name]
        if missing:
            raise SystemExit(f"jäsenmäärä: {unit}: no municipality called {missing}")
        return tuple(sorted({by_name[fold(n)] for n in UNITS[unit]}))
    if fold(unit) in by_name:
        return (by_name[fold(unit)],)
    parts = {by_name[fold(p)] for p in re.split(r"\s*-\s*", unit) if fold(p) in by_name}
    return tuple(sorted(parts))


def finland() -> list[dict[str, Any]]:
    import openpyxl
    from . import finland as fi
    from .nordic_origin import drawn_subregion_key
    raw, used = None, None
    for url in EVL_URLS:
        try:
            raw = request(url, accept="*/*", attempts=3)
        except (SystemExit, Exception) as exc:
            log(f"  {url}: {str(exc)[:120]}")
            continue
        if raw.startswith(b"PK"):
            used = url
            break
    if not used:
        raise SystemExit("jäsenmäärä: no copy of the workbook answered")
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = book[EVL_SHEET]
    rows = list(sheet.iter_rows(values_only=True))
    if f"31.12.{EVL_YEAR}" not in str(rows[0][0]):
        raise SystemExit(f"jäsenmäärä: the sheet is not for 31.12.{EVL_YEAR}: {rows[0][0]!r}")
    units, total = evl_units(rows)
    key_year, sk_of, sk_names, found = drawn_subregion_key()
    names: dict[str, str] = {}
    for lang in ("fi", "sv"):
        for entry in request_json(NAMES_KEY.format(y=key_year, lang=lang), pause=fi.PAUSE):
            code, name = fi.item(entry, "source")
            names[fold(name)] = code
            # "Pedersören kunta - Pedersöre", "Maarianhamina - Mariehamn"
            for part in re.split(r"\s+-\s+", name):
                names.setdefault(fold(part), code)
    placed: dict[str, int] = defaultdict(int)
    left_out: dict[str, int] = {}
    spanning: dict[str, tuple[str, ...]] = {}
    covered: set[str] = set()
    for unit, members in units.items():
        if unit in NO_TERRITORY:
            left_out[unit] = members
            continue
        munis = unit_municipalities(unit, names)
        if not munis:
            raise SystemExit(f"jäsenmäärä: no municipality for the unit {unit!r}")
        homes = {sk_of[m] for m in munis}
        covered |= set(munis)
        if len(homes) > 1:
            spanning[unit] = munis
            left_out[unit] = members
            continue
        placed[homes.pop()] += members
    log(f"  {used}: {len(units)} units, {total:,} members; left out of every sub-region: "
        f"{left_out}; municipalities named by no unit (in a union's parishes): "
        f"{sorted(set(sk_of) - covered)}")
    # The population of the same day, in the same year's municipalities.
    meta = {v["code"]: v for v in request_json(POP_TABLE, pause=fi.PAUSE)["variables"]}
    area = next(c for c in meta if c.startswith("kunta"))
    codes = [f"KU{k}" for k in sorted(sk_of)]
    people: dict[str, float] = {}
    for chunk in (codes[i:i + 150] for i in range(0, len(codes), 150)):
        for key, value in unstack(request_json(POP_TABLE, {"query": [
            {"code": area, "selection": {"filter": "item", "values": chunk}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": [str(EVL_YEAR)]}},
            {"code": "sukupuoli_9_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "ikaryhma_10_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "contentscode", "selection": {"filter": "item", "values": ["vaerak-vaesto"]}},
        ], "response": {"format": "json-stat2"}}, pause=fi.PAUSE)):
            people[key[area][0][2:]] = value
    missing = [c for c in sk_of if not people.get(c)]
    if missing:
        raise SystemExit(f"11rf {EVL_YEAR}: no population for the key's municipalities {missing}")
    excluded = {m for munis in spanning.values() for m in munis}
    pop: dict[str, float] = defaultdict(float)
    for code, sk in sk_of.items():
        if code not in excluded:
            pop[sk] += people[code]
    for sk in set(sk_of.values()):
        share = placed.get(sk, 0) / pop[sk] if pop[sk] else 0
        if not 0.4 <= share <= 0.97:
            raise SystemExit(f"jäsenmäärä: {sk_names[sk]}: {placed.get(sk, 0):,} members of "
                             f"{pop[sk]:,.0f} people ({100 * share:.1f}%)")
    shapes_rows = {found[d]: (d, "") for d in fi.DRAWN}
    bound, missing_rows, left, _p = bind_rows("FIN", "admin2", shapes_rows)
    if missing_rows or left:
        raise SystemExit(f"finland: sub-regions unbound {missing_rows}")
    away = "; ".join(f"{u} ({left_out[u]:,} members): {why}" for u, why in NO_TERRITORY.items()
                     if u in left_out)
    records = []
    for sk, (drawn, _) in sorted(shapes_rows.items()):
        members, total_people = placed.get(sk, 0), pop[sk]
        cut = sorted(f"{unit} ({', '.join(m for m in munis)})" for unit, munis in spanning.items()
                     if any(sk_of[m] == sk for m in munis))
        records.append(record(
            f"FIN-EVL-SK{key_year}-{sk}", drawn, level="admin2", parent="FIN", country="FIN",
            codes={"seutukunta": sk, "vintage": key_year}, match_by="shape_id",
            shape_id=bound[sk],
            religion=shares({FINLAND_CHURCH: members, FINLAND_OUTSIDE: total_people - members},
                            total=total_people),
            religion_year=EVL_YEAR, religion_basis=BASIS,
            religion_note=(
                f"Members of the Evangelical Lutheran Church of Finland on 31 December {EVL_YEAR} "
                f"by the church's own count ('Talousyksiköiden jäsenmäärä 31.12.{EVL_YEAR}', "
                "its membership by parish union and independent parish), summed into the "
                f"sub-region of {key_year} and set against Statistics Finland's population of "
                f"the same day (table 11rf): {members:,} of {total_people:,.0f}. The church's "
                "registered membership, not belief. Everyone else -- members of the Orthodox "
                "Church of Finland, of other communities and of none -- is one group: the "
                "population register records every resident's religious community, but "
                "Statistics Finland publishes it for the whole country only (table 11rx)."
                + (f" Left out with their people: {'; '.join(cut)}, a parish whose "
                   "municipalities lie in two sub-regions, so its members cannot be placed in "
                   "either." if cut else "")
                + (f" Counted in no sub-region: {away}." if away else "")),
            sources=[{"field": "religion", "name": "Evangelical Lutheran Church of Finland, "
                      f"membership by economic unit 31 December {EVL_YEAR} (kirkontilastot.fi)",
                      "url": used, "year": EVL_YEAR},
                     {"field": "religion", "name": "Statistics Finland, table 11rf",
                      "url": POP_PAGE, "year": EVL_YEAR}]))
    return records


READERS = {"SWE": (sweden, "sweden_church.json"), "FIN": (finland, "finland_church.json")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True, choices=sorted(READERS))
    args = ap.parse_args()
    reader, out = READERS[args.country]
    log(f"nordic_church: {args.country}")
    records = reader()
    labels = {g["group"] for r in records for g in r.get("religion") or []
              if isinstance(r.get("religion"), list)}
    log(f"  {len(records)} records; religion labels the group tree cannot place: "
        f"{unplaced('religion', labels) or 'none'}")
    write_json(PROCESSED / out, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
