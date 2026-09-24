#!/usr/bin/env python3
"""OCHA's Common Operational Dataset -- Population Statistics, by district.

30,170 of this map's 49,349 second-level shapes have no published population,
and that is what stops a parent's composition from being subtracted down to
its one unread district: a share cannot be turned into a count without a
weight. Bolivia has a population for 9 of 9 departments and 0 of 110
provinces, Iraq 12 of 18 governorates and 0 of 101 districts.

Wikidata was the only global attempt and its ceiling is low: of 18,656 admin2
items it carries P1082 for 6,441, and about 4,900 of those reach a shape.

COD-PS is the other candidate. OCHA publishes one dataset per country, agreed
with the national statistical office, giving population by P-code at every
level the country has. It is the reference population table for humanitarian
work, which is both why it is good (an office's own figures, a stated
reference year) and why it must be read carefully (some of it is projected
forward from an old census, and the licences are not uniform -- cod-ps-idn is
"humanitarian use only" and not an open licence at all).

This runs as a probe first, deliberately. Nothing is written until the log has
said, per country, what the licence is, what the resources are called and
which administrative levels they carry. That is the lesson of cod-ps-idn: the
family name does not tell you the licence, and a dataset that looks like the
others can be the one that may not be used.

Usage:
    python -m scripts.fetch_census.cod_ps --probe        # measure, write nothing
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from typing import Any

from ._shared import PROCESSED, log, record, write_json

API = "https://data.humdata.org/api/3/action"
TIMEOUT = 120
OUT = "cod_ps_admin2.json"
DATASET_PAGE = "https://data.humdata.org/dataset/{stub}"
HEADERS = {"Accept": "application/json",
           "User-Agent": "DemographicMap/1.0 "
                         "(+https://github.com/advaitsridhar/DemographicMap)"}


def get(path: str, **params: object) -> Any:
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(
            urllib.request.Request(url, headers=HEADERS), timeout=TIMEOUT) as fh:
        return json.load(fh)["result"]


def catalogue() -> list[dict[str, Any]]:
    """Every cod-ps dataset, paged. CKAN caps rows per request."""
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        page = get("package_search", q="name:cod-ps-*", rows=100, start=start)
        got = page.get("results") or []
        out.extend(got)
        start += len(got)
        if not got or start >= int(page.get("count") or 0):
            break
    return out


def licence(package: dict[str, Any]) -> str:
    """The licence as the catalogue states it, never as the family implies."""
    title = str(package.get("license_title") or "").strip()
    other = str(package.get("license_other") or "").strip()
    return (f"{title or 'unstated'} -- license_id={package.get('license_id')!r}, "
            f"isopen={package.get('isopen')}"
            + (f", license_other={other!r}" if other else ""))


# The two licences this map may read a COD-PS under. CC BY-IGO is the common
# one and is an attribution licence; png.py has read cod-ps-png under it since
# before this file existed. Everything else is refused by name rather than by
# flag: "humanitarian use only" (cod-ps-idn and four others), "Restricted for
# use only in HRP and Humanitarian Operations", and the two that state no
# licence at all.
USABLE = ("cc-by-igo", "cc-by")


def is_usable(package: dict[str, Any]) -> bool:
    return str(package.get("license_id") or "") in USABLE


def iso3(package: dict[str, Any]) -> str:
    for group in package.get("groups") or ():
        code = str(group.get("name") or "").upper()
        if len(code) == 3:
            return code
    name = str(package.get("name") or "")
    tail = name.rsplit("-", 1)[-1].upper()
    return tail if len(tail) == 3 else ""


def probe() -> None:
    packages = catalogue()
    log(f"cod_ps: {len(packages)} cod-ps dataset(s) on HDX")
    usable_count = 0
    for package in sorted(packages, key=lambda p: str(p.get("name"))):
        terms = licence(package)
        if is_usable(package):
            usable_count += 1
        log(f"  {str(package.get('name')):22} {iso3(package) or '?':4} {terms}")
        for resource in package.get("resources") or ():
            log(f"      {str(resource.get('name'))[:78]:80} "
                f"{str(resource.get('format'))}")
    # NOT CKAN's isopen flag, which is what the first version of this printed
    # and it was misleading: 132 of these are CC BY-IGO, which HDX marks
    # isopen=False only because CKAN's registry does not list it. CC BY-IGO is
    # an attribution licence and this map already reads cod-ps-png under it
    # (scripts/fetch_census/png.py). What is genuinely unusable is the handful
    # that say so in words -- "humanitarian use only", "Restricted for use only
    # in HRP and Humanitarian Operations" -- and the ones with no licence at
    # all. So the count is by what the licence says, not by the flag.
    log(f"  usable (CC BY or CC BY-IGO): {usable_count} of {len(packages)}")


# The columns, as the eight countries probed on 21 September 2026 write them.
# The name column carries the language rather than a fixed suffix -- Iran and
# Turkey write ADM2_EN, Romania ADM2_RO -- so it is matched by shape and the
# English one is preferred where a file has both.
# The column names, as the 148 datasets actually write them. There is no one
# schema: the first version of this matched ^ADM2_[A-Z]{2}$ and refused
# fifteen files whose only fault was spelling. What is out there --
#
#   ADM2_EN      ADM2_RO      ADM2_NAME    ADM2_NAME_SI
#   admin2Name_en   admin2Name_fr   admin2Name_ru
#   Adm2_name    adm2_Name    district_name
#
# -- so the column is recognised by its shape after the punctuation and case
# are taken out, and the preference order is English, then an unqualified
# name, then whatever language is left. A file that offers ADM2_NAME beside
# ADM2_NAME_SI and ADM2_NAME_TA is Sri Lanka's, and the unqualified one is the
# English it already is.
LEVEL_WORD = re.compile(r"^(?:adm|admin)(?P<level>[123])")
# Never a name: a code, a classification, or one of the alternates a file
# carries beside the name it actually uses.
NOT_A_NAME = ("pcode", "code", "type", "refname", "altname")
# The total. T_TL is the COD-PS standard and a handful write it out instead.
TOTAL_COLUMNS = ("ttl", "populationtotal", "totalpopulation", "total")
# The reference year is a column in the newer files and only in the resource
# name in the older ones ("irn_admpop_adm2_2016_v2.csv"). A population with no
# year is not written: the point of this file is to weigh a composition, and a
# weight of unknown vintage against a composition of known vintage is how a
# residual comes out wrong while looking right.
YEAR_IN_NAME = re.compile(r"_(\d{4})(?:_|\.)")


def squash(column: str) -> str:
    return "".join(c for c in column.lower() if c.isalnum())


def name_column(columns: list[str], level: str) -> str | None:
    """The column naming the units at ``level``, or None.

    Ranked rather than taken first, because several files carry more than one
    name column and picking the wrong one puts a Tamil transliteration where
    the boundary file has English.
    """
    def rank(column: str) -> tuple[int, int]:
        flat = squash(column)
        if flat.endswith("en"):
            return (0, len(flat))
        if flat.endswith("name"):
            return (1, len(flat))
        return (2, len(flat))


    found = []
    for column in columns:
        flat = squash(column.strip())
        match = LEVEL_WORD.match(flat)
        if not match or match.group("level") != level:
            continue
        rest = flat[match.end():]
        # Either it says "name" (ADM2_NAME, admin2Name_en) or it is the bare
        # language the older files use (ADM2_EN, ADM2_RO).
        if not (rest.startswith("name") or (len(rest) == 2 and rest.isalpha())):
            continue
        if any(b in rest for b in NOT_A_NAME):
            continue
        found.append(column.strip())
    # Somalia writes "district_name" and "province_name" with no adm prefix.
    if not found:
        word = "district" if level == "2" else "province"
        found = [c.strip() for c in columns if squash(c) == f"{word}name"]
    return min(found, key=rank) if found else None


def total_column(columns: list[str]) -> str | None:
    for column in columns:
        if squash(column) in TOTAL_COLUMNS:
            return column.strip()
    return None


def reference_year(columns: list[str], rows: list[dict[str, str]],
                   resource_name: str) -> int | None:
    if "year" in columns:
        years = {str(r.get("year") or "").strip() for r in rows}
        years = {y for y in years if y.isdigit()}
        if len(years) == 1:
            return int(years.pop())
    found = YEAR_IN_NAME.search(resource_name)
    return int(found.group(1)) if found else None


# A district table, by the file's own name: "adm2", or "admpop2" as Cameroon's
# is called ("CMR_admpop2_2025.csv"), which the first version of this missed.
ADM2_NAME = re.compile(r"adm(?:pop)?_?2(?!\d)")


def adm2_resource(package: dict[str, Any]) -> dict[str, Any] | None:
    """The district table: a CSV where there is one, else the workbook.

    Sixty-odd datasets publish their districts only inside the workbook
    beside the national and first-level CSVs -- Kenya's, Zambia's, Iraq's,
    Jamaica's -- so a reader of CSVs alone found nothing there.
    """
    resources = list(package.get("resources") or ())
    for resource in resources:
        name = str(resource.get("name") or "").lower()
        if ADM2_NAME.search(name) and name.endswith(".csv"):
            return resource
    books = workbooks(package)
    return books[0] if books else None


def workbooks(package: dict[str, Any]) -> list[dict[str, Any]]:
    """The population workbooks, newest-named first; never a gazetteer.

    Most of them turned out to hold only national and first-level sheets --
    Bolivia's, Cuba's, Iraq's, Jamaica's, Vietnam's -- so each is asked in
    turn, and Chad's district sheet is in its 2021 workbook, not its 2023 one.
    """
    books = [r for r in package.get("resources") or ()
             if str(r.get("name") or "").lower().endswith((".xlsx", ".xlsm"))
             and not re.search(r"gazetteer|admgz|boundar|admin_?boundaries",
                               str(r.get("name") or "").lower())]
    return sorted(books, key=lambda r: [-int(y) for y in re.findall(
        r"(\d{4})", str(r.get("name") or ""))] or [0])


def workbook_rows(body: bytes) -> tuple[list[str], list[dict[str, str]], str]:
    """The district sheet of a COD-PS workbook, as a CSV reader would give it.

    The sheet is found by its name ("..._adm2" or "admpop2"), and nothing else
    is guessed: a workbook with no such sheet is refused by the caller.
    """
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    for sheet in book.worksheets:
        title = sheet.title.lower().replace(" ", "")
        # "adm2" or "admpop2" in the name, or Uzbekistan's bare "L2"; and a
        # total among its columns, since Zambia's workbook has a boundary
        # sheet called AB-ADM2 that carries names and no population.
        if not (ADM2_NAME.search(title) or title == "l2"):
            continue
        rows = sheet.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows, [])]
        if total_column([h for h in header if h]) is None:
            continue
        out = []
        for row in rows:
            if not any(v not in (None, "") for v in row):
                continue
            out.append({h: ("" if v is None else str(v)) for h, v in zip(header, row) if h})
        return [h for h in header if h], out, sheet.title
    return [], [], ""


# Where this map's own shapes are, so a file can be asked which level it is
# actually describing rather than believed.
SITE = PROCESSED.parent.parent / "site" / "data"


def fold(name: str) -> str:
    """Enough of a name to compare two spellings of it."""
    stripped = unicodedata.normalize("NFKD", name)
    letters = "".join(c for c in stripped if not unicodedata.combining(c))
    return "".join(c for c in letters.lower() if c.isalnum())


# Words that say what kind of unit a name is, in the boundary file's way of
# writing it or the table's: "District of Bardejov" against "Bardejov",
# "Provincia de Antofagasta" against "Antofagasta", "Acoyapa (Municipio)".
# Used only to decide which of this map's levels a table describes -- the
# join itself is the build's, with its own rules -- so a looser comparison
# here moves no figure onto any shape.
KIND_WORDS = re.compile(
    r"\((?:[^)]*)\)|\b(?:district|province|provincia|departamento|department|"
    r"municipality|municipio|municipalite|arrondissement|commune|county|rayon|"
    r"raion|region|of|de|del|la|le)\b")


def level_key(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name.lower())
    letters = "".join(c for c in stripped if not unicodedata.combining(c))
    return fold(KIND_WORDS.sub(" ", letters))


def shape_names(code: str, level: str) -> set[str]:
    path = SITE / level / f"{code}.json"
    try:
        return {level_key(s["name"]) for s in json.loads(path.read_text())}
    except (OSError, ValueError, KeyError):
        return set()


def which_level(code: str, names: list[str]) -> tuple[str | None, str]:
    """Which of this map's levels the file's rows are naming, by measurement.

    "adm2" is the file's word, not this map's, and the two do not always mean
    the same divisions. Romania's cod-ps adm2 table has 42 rows -- its judete,
    which are this map's *first* level -- against 3,235 communes at the second.
    Written as districts those 42 would mostly find no shape, which is a
    visible gap and survivable; but Romanian communes are frequently named
    after the county town, so some would find the wrong shape and wear a
    county's population. That is the invisible error this project exists to
    avoid, so the level is established rather than assumed.

    The test is the file's own names against this map's: whichever level they
    match more is the level they describe. A file matching neither is refused,
    because then there is nothing to say where its rows belong.
    """
    want = {level_key(n) for n in names if n}
    want.discard("")
    if not want:
        return None, "no row carries a name"
    scores = {level: len(want & shape_names(code, level))
              for level in ("admin1", "admin2")}
    best = max(scores, key=lambda k: scores[k])
    other = "admin1" if best == "admin2" else "admin2"
    # A tie says nothing about which level it is, and a handful of names says
    # too little: Kyrgyzstan's table lost all but four rows to repeated codes,
    # two of which matched each level, and was written as four first-level
    # units carrying 329,300 people between them.
    if scores[best] == scores[other] \
            or scores[best] < min(MIN_LEVEL_NAMES, len(want)):
        return None, (f"its names match {scores['admin2']} of this map's "
                      f"districts and {scores['admin1']} of its first-level "
                      f"units, out of {len(want)}; too few of either to say "
                      f"which level this file describes")
    if scores[best] < MIN_LEVEL_MATCH * len(want):
        return None, (f"its names match {scores['admin2']} of this map's "
                      f"districts and {scores['admin1']} of its first-level "
                      f"units, out of {len(want)}; too few of either to say "
                      f"which level this file describes")
    return best, (f"{scores[best]} of {len(want)} names match this map's "
                  f"{best} (against {scores[other]} at {other})")


# How much of a file must land on a level before this reader believes it is
# that level. Not a majority: boundary files and COD-PS disagree about
# spellings often enough that a real match sits well below 100%.
MIN_LEVEL_MATCH = 0.40
# And never on fewer names than this (or than the table has), however well
# they match.
MIN_LEVEL_NAMES = 5


def adm3_resource(package: dict[str, Any]) -> dict[str, Any] | None:
    for resource in package.get("resources") or ():
        name = str(resource.get("name") or "").lower()
        if re.search(r"adm(?:pop)?_?3(?!\d)", name) and name.endswith(".csv"):
            return resource
    return None


def dataset_year(package: dict[str, Any]) -> int | None:
    """The one year HDX's own reference period for the dataset names, if one.

    CKAN writes it as "[2018-01-01T00:00:00 TO 2018-12-31T23:59:59]". A span
    of more than one year says nothing about which year a row describes, so
    only a single year is taken.
    """
    years = set(re.findall(r"(\d{4})-\d{2}-\d{2}", str(package.get("dataset_date") or "")))
    return int(years.pop()) if len(years) == 1 else None


def read_table(resource: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], str] | None:
    """A table's columns, rows and the name its year may be read from."""
    try:
        with urllib.request.urlopen(urllib.request.Request(
                str(resource.get("url")), headers=HEADERS), timeout=TIMEOUT) as fh:
            raw_body = fh.read()
    except Exception as err:                         # noqa: BLE001 -- reported
        log(f"    refused: {resource.get('name')}: {type(err).__name__}: {err}")
        return None
    resource_name = str(resource.get("name") or "")
    if resource_name.lower().endswith(".csv"):
        reader = csv.DictReader(io.StringIO(raw_body.decode("utf-8-sig", "replace")))
        return ([c.strip() for c in (reader.fieldnames or [])], list(reader),
                resource_name)
    try:
        columns, rows, sheet = workbook_rows(raw_body)
    except Exception as err:                         # noqa: BLE001 -- reported
        log(f"    refused: {resource_name}: unreadable workbook: "
            f"{type(err).__name__}: {err}")
        return None
    if not rows:
        log(f"    refused: {resource_name} has no district sheet")
        return None
    log(f"    read sheet {sheet!r} of {resource_name}")
    # The year may be in the sheet's name rather than the file's.
    return columns, rows, f"{resource_name} {sheet}_"


def read_units(package: dict[str, Any], resource: dict[str, Any],
               cod_level: str) -> tuple[dict[str, dict[str, Any]], int] | None:
    """The table's units at ``cod_level`` and its reference year, or None."""
    table = read_table(resource)
    if table is None:
        return None
    columns, rows, resource_name = table
    unit = name_column(columns, cod_level)
    parent = name_column(columns, "1")
    total = total_column(columns)
    if not unit or not total:
        log(f"    refused: no level-{cod_level} name column or no total; "
            f"its columns are: {', '.join(columns[:12])}")
        return None
    year = reference_year(columns, rows, resource_name)
    if year is None:
        year = dataset_year(package)
        if year is None:
            log("    refused: the file states no reference year, in a column or "
                "its own name, and HDX's reference period for it is not one year")
            return None
        log(f"    reference year {year} from HDX's reference period for the "
            f"dataset, the file stating none")

    # One row per district, and a district that appears twice is refused
    # rather than summed or overwritten. Turkey's file carries a "type"
    # column, so a second row for one P-code would be a different universe
    # (residents against some other count) and adding them would invent a
    # population nobody published.
    pcodes = (f"adm{cod_level}pcode", f"admin{cod_level}pcode", "districtcode")
    seen: dict[str, dict[str, Any]] = {}
    clashed: set[str] = set()
    unnamed = bad = 0
    for row in rows:
        name = (row.get(unit) or "").strip()
        code2 = next((str(row[c]).strip() for c in row
                      if squash(c) in pcodes and row.get(c)), name).strip()
        raw = (row.get(total) or "").strip().replace(",", "")
        if not name or not code2:
            unnamed += 1
            continue
        try:
            people = int(float(raw))
        except ValueError:
            bad += 1
            continue
        if people <= 0:
            bad += 1
            continue
        if code2 in seen:
            if seen[code2]["people"] != people:
                clashed.add(code2)
            continue
        seen[code2] = {"name": name, "people": people,
                       "parent": (row.get(parent) or "").strip() if parent else ""}
    for code2 in clashed:
        seen.pop(code2, None)
    if clashed:
        log(f"    {len(clashed)} unit(s) appear twice with different "
            f"totals and are refused")
    if unnamed or bad:
        log(f"    {unnamed} row(s) unnamed, {bad} with no usable total")
    if not seen:
        log("    refused: no unit survived")
        return None
    return seen, year


# Countries whose district table shares names with the map's second level
# without sharing its units. Kenya's COD-PS districts are its sub-counties and
# the map's are its constituencies: in most counties the two coincide, and in
# some they do not -- Laikipia's three constituencies took sub-county figures
# summing to 52% of the county, Wajir's 72%, Kwale's 77%. Nothing in a single
# row says which kind it is, so a county's rows are kept only where they
# partition it: every one of its shapes takes exactly one row, and the rows
# add up to the county's own total in the same dataset's first-level table.
PARTITION_CHECK = {"KEN"}
PARTITION_TOLERANCE = 0.02


def first_level_totals(package: dict[str, Any]) -> dict[str, int]:
    """The dataset's own first-level totals, by name key."""
    for resource in package.get("resources") or ():
        name = str(resource.get("name") or "").lower()
        if re.search(r"adm(?:pop)?_?1(?!\d)", name) and name.endswith(".csv"):
            table = read_table(resource)
            if table is None:
                return {}
            columns, rows, _ = table
            unit, total = name_column(columns, "1"), total_column(columns)
            if not unit or not total:
                return {}
            out: dict[str, int] = {}
            for row in rows:
                try:
                    out[level_key(row.get(unit) or "")] = int(float(
                        (row.get(total) or "").replace(",", "")))
                except ValueError:
                    continue
            return out
    return {}


def partitioned(code: str, rows: list[dict[str, Any]],
                totals: dict[str, int]) -> list[dict[str, Any]]:
    """Only the rows of first-level units they are shown to partition."""
    try:
        shapes = json.loads((SITE / "admin2" / f"{code}.json").read_text())
        parents = {s["id"]: s["name"] for s in
                   json.loads((SITE / "admin1" / f"{code}.json").read_text())}
    except (OSError, ValueError):
        return []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(level_key(row["name"]), []).append(row)
    under: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        under.setdefault(shape.get("parent"), []).append(shape)
    kept: list[dict[str, Any]] = []
    passed = failed = 0
    for parent, members in under.items():
        taken = [by_key.get(level_key(m["name"]), []) for m in members]
        county = totals.get(level_key(parents.get(parent, "")))
        if county and all(len(t) == 1 for t in taken):
            people = sum(t[0]["population"]["value"] for t in taken)
            if abs(people - county) <= PARTITION_TOLERANCE * county:
                kept.extend(t[0] for t in taken)
                passed += 1
                continue
        failed += 1
    log(f"    partition check: {passed} first-level unit(s) whose rows add up "
        f"to its own total, kept; {failed} left out")
    return kept


def country_records(package: dict[str, Any]) -> list[dict[str, Any]]:
    """One country's district populations, or none with the reason logged.

    The district table first. Where its units are not this map's -- El
    Salvador's second level became 44 municipalities in 2024, and its 262 old
    ones, the map's, are the table one level down -- the next table is asked
    the same question.
    """
    code = iso3(package)
    stub = str(package.get("name") or "")
    terms = licence(package)
    log(f"  {stub} ({code or '?'})")
    log(f"    licence: {terms}")
    if not code:
        log("    refused: the catalogue gives no ISO3")
        return []
    if not is_usable(package):
        log("    refused: this licence is not one this map may read")
        return []
    first = adm2_resource(package)
    candidates = [(first, "2")] + [(book, "2") for book in workbooks(package)
                                   if book is not first] + [(adm3_resource(package), "3")]
    if candidates[0][0] is None and candidates[1][0] is None:
        log("    refused: no adm2 CSV or workbook on this dataset")
        return []
    for resource, cod_level in candidates:
        if resource is None:
            continue
        got = read_units(package, resource, cod_level)
        if got is None:
            continue
        seen, year = got
        level, why = which_level(code, [u["name"] for u in seen.values()])
        if level is None:
            log(f"    refused {resource.get('name')}: {why}")
            continue
        log(f"    level: {why} ({resource.get('name')})")
        source = {"field": "population",
                  "name": f"OCHA, Common Operational Dataset -- population "
                          f"statistics ({stub}), reference year {year}",
                  "url": DATASET_PAGE.format(stub=stub),
                  "year": year,
                  "license": terms}
        out = []
        for code2, unit_row in sorted(seen.items()):
            out.append(record(
                f"{code}-CODPS-{code2}", unit_row["name"], level=level,
                parent=code, country=code,
                # The parent hint is only meaningful for a district: at the
                # first level the parent is the country and naming a region
                # there would send the matcher looking for a shape above it.
                parent_name=(unit_row["parent"] or None) if level == "admin2" else None,
                population={"value": unit_row["people"], "year": year,
                            "source": source["name"]},
                sources=[source]))
        if code in PARTITION_CHECK and level == "admin2":
            out = partitioned(code, out, first_level_totals(package))
        log(f"    {len(out)} {level} unit(s), reference year {year}, "
            f"{sum(r['population']['value'] for r in out):,} people")
        return out
    return []


def headers(isos: list[str]) -> None:
    """The first two lines of each country's adm2 table, and nothing else.

    A reader cannot be written against a guessed column name, and COD-PS has
    been through more than one schema. This prints what is actually there.
    """
    wanted = {c.upper() for c in isos}
    for package in sorted(catalogue(), key=lambda p: str(p.get("name"))):
        code = iso3(package)
        if wanted and code not in wanted:
            continue
        if not is_usable(package):
            log(f"  {code}: refused, {licence(package)}")
            continue
        for resource in package.get("resources") or ():
            name = str(resource.get("name") or "")
            if name.lower().endswith((".xlsx", ".xlsm")) and "boundaries" not in name.lower():
                # Every sheet's name and first two rows: which one holds the
                # districts, and under what columns, is read and not guessed.
                log(f"  {code} {name}")
                try:
                    import openpyxl
                    with urllib.request.urlopen(urllib.request.Request(
                            str(resource.get("url")), headers=HEADERS),
                            timeout=TIMEOUT) as fh:
                        book = openpyxl.load_workbook(io.BytesIO(fh.read()),
                                                      read_only=True, data_only=True)
                    for ws in book.worksheets:
                        rows = ws.iter_rows(values_only=True, max_row=2)
                        log(f"      sheet {ws.title!r}")
                        for row in rows:
                            log("        " + " | ".join(
                                "" if v is None else str(v) for v in row)[:300])
                except Exception as err:             # noqa: BLE001 -- reported
                    log(f"      unreadable: {type(err).__name__}: {err}")
                continue
            if "adm2" not in name.lower() or not name.lower().endswith(".csv"):
                continue
            log(f"  {code} {name}")
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        str(resource.get("url")), headers=HEADERS),
                        timeout=TIMEOUT) as fh:
                    body = fh.read(4000).decode("utf-8-sig", "replace")
            except Exception as err:                 # noqa: BLE001 -- reported
                log(f"      unreadable: {type(err).__name__}: {err}")
                continue
            for line in body.splitlines()[:2]:
                log(f"      {line[:400]}")
            break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="describe every dataset and write nothing")
    ap.add_argument("--only", default="",
                    help="comma-separated ISO3s to write, rather than all")
    ap.add_argument("--out", default=None)
    ap.add_argument("--headers", default="",
                    help="comma-separated ISO3s whose adm2 table to describe")
    args = ap.parse_args()
    if args.headers:
        headers([x for x in args.headers.split(",") if x])
        return 0
    if args.probe:
        probe()
        return 0
    only = {x.upper() for x in args.only.split(",") if x}
    packages = catalogue()
    log(f"cod_ps: {len(packages)} cod-ps dataset(s) on HDX")
    records_out: list[dict[str, Any]] = []
    written: list[str] = []
    for package in sorted(packages, key=lambda p: str(p.get("name"))):
        if only and iso3(package) not in only:
            continue
        got = country_records(package)
        if got:
            written.append(f"{iso3(package)}:{len(got)}")
        records_out += got
    if not records_out:
        raise SystemExit("cod_ps: nothing usable was read; writing nothing")
    log(f"  {len(records_out)} districts in {len(written)} countries: "
        f"{', '.join(written)}")
    write_json(args.out or PROCESSED / OUT, records_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
