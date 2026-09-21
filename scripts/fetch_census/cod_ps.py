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
LEVEL_WORD = re.compile(r"^(?:adm|admin)(?P<level>[12])")
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


def adm2_resource(package: dict[str, Any]) -> dict[str, Any] | None:
    for resource in package.get("resources") or ():
        name = str(resource.get("name") or "").lower()
        if "adm2" in name and name.endswith(".csv"):
            return resource
    return None


# Where this map's own shapes are, so a file can be asked which level it is
# actually describing rather than believed.
SITE = PROCESSED.parent.parent / "site" / "data"


def fold(name: str) -> str:
    """Enough of a name to compare two spellings of it."""
    stripped = unicodedata.normalize("NFKD", name)
    letters = "".join(c for c in stripped if not unicodedata.combining(c))
    return "".join(c for c in letters.lower() if c.isalnum())


def shape_names(code: str, level: str) -> set[str]:
    path = SITE / level / f"{code}.json"
    try:
        return {fold(s["name"]) for s in json.loads(path.read_text())}
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
    want = {fold(n) for n in names if n}
    if not want:
        return None, "no row carries a name"
    scores = {level: len(want & shape_names(code, level))
              for level in ("admin1", "admin2")}
    best = max(scores, key=lambda k: scores[k])
    other = "admin1" if best == "admin2" else "admin2"
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


def country_records(package: dict[str, Any]) -> list[dict[str, Any]]:
    """One country's district populations, or none with the reason logged."""
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
    resource = adm2_resource(package)
    if resource is None:
        log("    refused: no adm2 CSV on this dataset")
        return []
    try:
        with urllib.request.urlopen(urllib.request.Request(
                str(resource.get("url")), headers=HEADERS), timeout=TIMEOUT) as fh:
            body = fh.read().decode("utf-8-sig", "replace")
    except Exception as err:                         # noqa: BLE001 -- reported
        log(f"    refused: {resource.get('name')}: {type(err).__name__}: {err}")
        return []
    reader = csv.DictReader(io.StringIO(body))
    rows = list(reader)
    columns = [c.strip() for c in (reader.fieldnames or [])]
    unit = name_column(columns, "2")
    parent = name_column(columns, "1")
    total = total_column(columns)
    if not unit or not total:
        log(f"    refused: no second-level name column or no total; "
            f"its columns are: {', '.join(columns[:12])}")
        return []
    year = reference_year(columns, rows, str(resource.get("name") or ""))
    if year is None:
        log("    refused: the file states no reference year, in a column or "
            "its own name")
        return []

    # One row per district, and a district that appears twice is refused
    # rather than summed or overwritten. Turkey's file carries a "type"
    # column, so a second row for one P-code would be a different universe
    # (residents against some other count) and adding them would invent a
    # population nobody published.
    seen: dict[str, dict[str, Any]] = {}
    clashed: set[str] = set()
    unnamed = bad = 0
    for row in rows:
        name = (row.get(unit) or "").strip()
        code2 = next((str(row[c]).strip() for c in row
                      if squash(c) in ("adm2pcode", "admin2pcode", "districtcode")
                      and row.get(c)), name).strip()
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
        log(f"    {len(clashed)} district(s) appear twice with different "
            f"totals and are refused")
    if unnamed or bad:
        log(f"    {unnamed} row(s) unnamed, {bad} with no usable total")
    if not seen:
        log("    refused: no district survived")
        return []

    level, why = which_level(code, [u["name"] for u in seen.values()])
    if level is None:
        log(f"    refused: {why}")
        return []
    log(f"    level: {why}")

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
            # The parent hint is only meaningful for a district: at the first
            # level the parent is the country and naming a region there would
            # send the matcher looking for a shape above the one it wants.
            parent_name=(unit_row["parent"] or None) if level == "admin2" else None,
            population={"value": unit_row["people"], "year": year,
                        "source": source["name"]},
            sources=[source]))
    log(f"    {len(out)} {level} unit(s), reference year {year}, "
        f"{sum(r['population']['value'] for r in out):,} people")
    return out


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
