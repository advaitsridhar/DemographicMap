#!/usr/bin/env python3
"""CLEAR Global's language-use files: the main household language, by region.

CLEAR Global (formerly Translators without Borders) publishes one HDX dataset
per country under the organization ``clear``, named ``<country>-languages``,
with a CSV per administrative level. The August 2025 release rewrote them into
one long-format table:

    location_code, location_name, location_level, language_code,
    language_name, language_rank, proportion_value, reliability_score,
    dataset_name, url, source, datetime_published, date_creation,
    representivity_rating

One row is one language in one unit, and ``proportion_value`` is that
language's share of the unit's population -- the catalogue's own words are
"the main language spoken in the household by proportion of the population".
That is a composition, and it is what this map wants: a first-level unit's
languages, adding to one.

**It is not CLEAR Global's own survey.** Each file names the study it was
tabulated from, in ``dataset_name`` and ``source``, and they are of three very
different kinds: a census microdata extract from IPUMS International (Iraq's
is the 1997 census), a DHS or MICS round, or a humanitarian needs assessment.
The catalogue's ``methodology`` says which, and for a survey
``methodology_other`` grades it -- "Representative survey at 95% confidence
level and a 10% margin of error, or better" against
"Non-representative/indicative survey". Every record written here carries the
study's name, its date, that grading and the licence, because a 1997 census
extract and an indicative 2016 assessment cannot be read as the same kind of
claim and the file must not present them as one.

**The older files are a different dataset and are not read.** Six of the 55
(Cameroon, Colombia, Ecuador, India, Nicaragua, Venezuela) were last updated
between 2020 and 2022 and are licensed "Creative Commons, Attribution,
Non-commercial, Share-alike" with ``isopen: false``; Thailand's and the
duplicate ``drc-languages`` are of the same vintage under CC BY-SA. All eight
are in the pre-2025 wide format, whose columns are independent indicators
rather than parts of a whole -- Bangkok reads Thai 0.997 and Other 0.036,
which is 103.3% of a city, and docs/SOURCES.md has had that measurement since
Thailand was looked at. This reader recognises a file by its **header**, not
by its name or its date: a file without the long-format columns is skipped
and its header is printed, so the exclusion stays a measurement. That the
six non-commercial datasets are exactly the ones the header test rejects is
a fact about this publisher's history and not an assumption: the licence of
every dataset is read from the catalogue on each run and logged.

**What is refused, and why.** A composition that is the same everywhere is
not a measurement of anywhere:

* a unit whose languages do not add to 1 (within 0.02) is dropped and named
  in the log, and a country where more than a fifth of units fail that is
  refused whole;
* a country whose units all carry the *identical* composition is refused --
  Haiti's ten regions each read Haitian 1.0 and nothing else, which asserts
  that French is spoken in none of them and tells a reader nothing about any
  region. That is the same fault as a constant entered once and copied down;
* a unit whose name says it is unknown -- DHS files carry rows like
  "west: level 2 unknown" -- is dropped, since there is no shape it could be
  matched to and a fuzzy match to a real region would be worse than a gap.

**Level.** Admin 1 only. The files carry admin2 rows too, and this map would
take them, but the table has no parent column: the only route to a district's
region is the P-code prefix, and that is a guess. Somalia's SO2301 does sit
under SO23 and Iraq's IQG15Q05 under IQG15, but Kyrgyzstan's admin1 codes are
zero-padded to thirteen characters (KG06000000000) and its districts are not
(KG06246000000), so no one prefix rule holds across the publisher. A
mis-parented district is an invisible error and a missing one is a visible
gap, so the districts are left for a pass that can establish the parent
rather than infer it.

Usage:
    python -m scripts.fetch_census.clear_global            # write the file
    python -m scripts.fetch_census.clear_global --probe SOM,IRQ
    python -m scripts.fetch_census.clear_global --org
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, write_json

API = "https://data.humdata.org/api/3/action"
ORG = "clear"
OUT = "clear_global_language.json"
TIMEOUT = 120
PUBLISHER = "CLEAR Global (formerly Translators without Borders)"
DATASET_PAGE = "https://data.humdata.org/dataset/{stub}"
HEADERS = {"Accept": "application/json",
           "User-Agent": "DemographicMap/1.0 "
                         "(+https://github.com/advaitsridhar/DemographicMap)"}

# The long-format columns of the 2025 release. A file that does not carry all
# of them is a different dataset and is not read; see the module docstring.
REQUIRED = ("location_code", "location_name", "location_level",
            "language_name", "proportion_value")

# How far a unit's languages may be from adding to one before the unit is
# dropped. These are tabulated shares and they land within a rounding error
# of 1; 0.02 is loose enough for that and far too tight for the wide-format
# files, whose columns are independent indicators and reach 1.21.
TOLERANCE = 0.02
# And how many of a country's units may fail that before the country is not
# worth writing at all.
MAX_FAILED = 0.20
MIN_UNITS = 2
# A share this small rounds to 0.0% and would print as a group nobody speaks.
MIN_PCT = 0.05

UNKNOWN_UNIT = re.compile(r"\bunknown\b|\blevel \d+ unknown\b", re.I)
ADMIN1_FILE = re.compile(r"admin_?1\D*\.csv$", re.I)
YEAR = re.compile(r"(1[89]\d\d|20\d\d)")


def get(path: str, **params: object) -> Any:
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as handle:
        return json.load(handle)["result"]


def fetch(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as handle:
        return handle.read().decode("utf-8-sig", "replace")


def catalogue() -> list[dict[str, Any]]:
    """Every dataset the publisher has, asked for by organization name."""
    found = get("package_search", fq=f"organization:{ORG}", rows=300)
    return found.get("results", []) or []


def licence(package: dict[str, Any]) -> str:
    """The licence as the catalogue states it, verbatim, for the record.

    Not a tidied summary. The owner's decision of 20 September 2026 was that a
    restrictive HDX licence is not a reason to stop, on condition that what
    was taken and under what terms sits on the face of the data; a string this
    project composed itself would not be that.
    """
    parts = [f"{package.get('license_title') or package.get('license_id') or '?'}"]
    other = (package.get("license_other") or "").strip().replace("\n", " ")
    if other:
        parts.append(other)
    parts.append(f"license_id={package.get('license_id')!r}, "
                 f"isopen={package.get('isopen')}")
    return " -- ".join(parts)


def iso3(package: dict[str, Any]) -> str:
    for group in package.get("groups", ()) or ():
        name = str(group.get("name", ""))
        if len(name) == 3 and name.isalpha():
            return name.upper()
    return ""


def reference_year(package: dict[str, Any], rows: list[dict[str, str]]) -> int | None:
    """The year the figures describe, from the catalogue and the file both.

    ``dataset_date`` is a Solr range -- "[1997-12-31T00:00:00 TO
    1997-12-31T23:59:59]" -- and every row carries ``datetime_published`` in
    American order, "12-31-1997". They should agree; where they do not, the
    catalogue's is taken and the disagreement is logged, because a year that
    is wrong by twenty years is the difference between a census and a
    guess.
    """
    catalogue_year = None
    match = YEAR.search(str(package.get("dataset_date") or ""))
    if match:
        catalogue_year = int(match.group(1))
    file_years = set()
    for row in rows:
        found = YEAR.search(str(row.get("datetime_published") or ""))
        if found:
            file_years.add(int(found.group(1)))
    if catalogue_year and file_years and file_years != {catalogue_year}:
        log(f"      the catalogue says {catalogue_year} and the file says "
            f"{sorted(file_years)}; taking the catalogue's")
    return catalogue_year or (min(file_years) if file_years else None)


def admin1_resource(package: dict[str, Any]) -> dict[str, Any] | None:
    """The first-level file, found by name rather than by uuid.

    HDX rotates resource uuids, so a hardcoded one is a fetch that works until
    the publisher next republishes. png.py asks by name for the same reason.
    """
    for resource in package.get("resources", []) or ():
        if ADMIN1_FILE.search(str(resource.get("name", ""))):
            return resource
    return None


def read_csv(body: str) -> tuple[list[dict[str, str]], list[str]]:
    reader = csv.DictReader(io.StringIO(body))
    return list(reader), list(reader.fieldnames or [])


def compose(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """{unit code: {name, shares, total}}, and the units refused, with reasons.

    ``total`` is kept as the file gave it, before rounding, because it is the
    evidence for whether this is a composition at all.
    """
    units: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("location_level", "")).strip() not in ("1", "admin1"):
            continue
        code = (row.get("location_code") or "").strip()
        name = (row.get("location_name") or "").strip()
        language = (row.get("language_name") or "").strip()
        if not code or not name or not language:
            continue
        try:
            value = float(row.get("proportion_value") or "")
        except ValueError:
            continue
        unit = units.setdefault(code, {"name": name, "counts": {}})
        # A language listed twice in one unit is added up rather than
        # overwritten: dropping one of them would quietly shrink the unit.
        unit["counts"][language] = unit["counts"].get(language, 0.0) + value

    kept: dict[str, dict[str, Any]] = {}
    refused: list[str] = []
    for code, unit in units.items():
        name = unit["name"]
        if UNKNOWN_UNIT.search(name) or code.upper().endswith("XXX"):
            refused.append(f"{name} ({code}): the file does not say which unit this is")
            continue
        total = sum(unit["counts"].values())
        if abs(total - 1.0) > TOLERANCE:
            refused.append(f"{name} ({code}): its languages add to {total:.3f}, "
                           f"not to 1")
            continue
        shares = [{"group": language, "pct": round(100.0 * value, 1)}
                  for language, value in unit["counts"].items()
                  if 100.0 * value >= MIN_PCT]
        shares.sort(key=lambda r: (-r["pct"], r["group"]))
        if not shares:
            refused.append(f"{name} ({code}): no language reaches 0.05%")
            continue
        kept[code] = {"name": name, "shares": shares, "total": total}
    return kept, refused


def signature(unit: dict[str, Any]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((r["group"], r["pct"]) for r in unit["shares"]))


def country_records(package: dict[str, Any]) -> list[dict[str, Any]]:
    """One country's first-level records, or none with the reason logged."""
    iso = iso3(package)
    stub = str(package.get("name", ""))
    log(f"  {stub} ({iso or '?'}): {package.get('title')}")
    log(f"    licence: {licence(package)}")
    if not iso:
        log("    refused: the catalogue gives no ISO3 for this dataset")
        return []
    resource = admin1_resource(package)
    if resource is None:
        log("    refused: no first-level file on this dataset")
        return []
    try:
        body = fetch(str(resource.get("url")))
    except Exception as err:                       # noqa: BLE001 -- reported
        log(f"    refused: {resource.get('name')}: {type(err).__name__}: {err}")
        return []
    rows, columns = read_csv(body)
    missing = [c for c in REQUIRED if c not in columns]
    if missing:
        log(f"    refused: {resource.get('name')} is not the long format; "
            f"it has no {', '.join(missing)}")
        log(f"      its columns are: {', '.join(columns)}")
        return []

    kept, refused = compose(rows)
    for line in refused[:8]:
        log(f"    dropped {line}")
    if len(refused) > 8:
        log(f"    ... and {len(refused) - 8} more dropped")
    total_units = len(kept) + len(refused)
    if not kept or len(kept) < MIN_UNITS:
        log(f"    refused: {len(kept)} usable unit(s) of {total_units}")
        return []
    if total_units and len(refused) / total_units > MAX_FAILED:
        log(f"    refused: {len(refused)} of {total_units} units are not a "
            f"composition; this file is not read as one")
        return []
    if len({signature(unit) for unit in kept.values()}) == 1:
        one = next(iter(kept.values()))["shares"]
        shown = ", ".join("{} {}%".format(r["group"], r["pct"]) for r in one[:3])
        log(f"    refused: all {len(kept)} units carry the identical "
            f"composition ({shown}); that is a national figure repeated, "
            f"not a measurement by unit")
        return []

    year = reference_year(package, rows)
    study = sorted({(r.get("dataset_name") or "").strip() for r in rows} - {""})
    origin = sorted({(r.get("source") or "").strip() for r in rows} - {""})
    grading = sorted({(r.get("representivity_rating") or "").strip()
                      for r in rows} - {""})
    methodology = str(package.get("methodology") or "").strip()
    method_note = str(package.get("methodology_other") or "").strip()
    terms = licence(package)
    source_name = (f"{PUBLISHER}, {package.get('title')} "
                   f"({resource.get('name')})")
    note = (
        f"The main language spoken in the household, as a share of the "
        f"population. Tabulated by {PUBLISHER} from "
        f"{'; '.join(study) or 'a study the file does not name'}"
        f"{' (' + '; '.join(origin) + ')' if origin else ''}"
        f"{f', {year}' if year else ''}. "
        f"Methodology as the publisher states it: {methodology or 'not stated'}"
        f"{'; ' + method_note if method_note else ''}"
        f"{'; representivity ' + ', '.join(grading) if grading else ''}. "
        f"Licence: {terms}.")

    records = []
    for code, unit in sorted(kept.items()):
        records.append(record(
            f"{iso}-CG-{code}", unit["name"], level="admin1", parent=iso,
            country=iso,
            language=unit["shares"],
            language_year=year,
            language_note=note,
            religion=gap(NOT_AVAILABLE,
                         "CLEAR Global's language files do not carry religion."),
            ethnicity=gap(NOT_AVAILABLE,
                          "CLEAR Global's language files do not carry ethnicity."),
            sources=[{"field": "language", "name": source_name,
                      "url": DATASET_PAGE.format(stub=stub),
                      "license": terms}],
        ))
    log(f"    {len(records)} unit(s) written, {len(refused)} dropped, "
        f"year {year}, {methodology or 'methodology not stated'}")
    return records


def probe(isos: list[str]) -> None:
    """What one country's files contain, described and not written."""
    wanted = {i.upper() for i in isos}
    for package in catalogue():
        if iso3(package) not in wanted:
            continue
        log(f"\n=== {iso3(package)}  {package.get('name')} ===")
        log(f"  licence: {licence(package)}")
        log(f"  methodology: {package.get('methodology')!r} "
            f"{(package.get('methodology_other') or '')!r}")
        log(f"  reference period: {package.get('dataset_date')!r}")
        for resource in package.get("resources", []) or ():
            name = str(resource.get("name", ""))
            if not name.lower().endswith(".csv"):
                continue
            log(f"  --- {name}")
            try:
                rows, columns = read_csv(fetch(str(resource.get("url"))))
            except Exception as err:               # noqa: BLE001 -- reported
                log(f"      {type(err).__name__}: {err}")
                continue
            log(f"      {len(rows)} row(s); columns: {', '.join(columns)}")
            for row in rows[:4]:
                log("      | " + " | ".join(f"{k}={v}"[:40] for k, v in row.items()))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default="",
                    help="comma-separated ISO3s whose files to describe, "
                         "writing nothing")
    ap.add_argument("--org", action="store_true",
                    help="list the publisher's datasets and their licences")
    ap.add_argument("--only", default="",
                    help="comma-separated ISO3s to write, rather than all")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.probe:
        probe([x for x in args.probe.split(",") if x])
        return 0
    packages = catalogue()
    if args.org:
        for package in sorted(packages, key=lambda p: str(p.get("name"))):
            log(f"{package.get('name'):48} {iso3(package) or '?':4} "
                f"{licence(package)}")
        return 0

    only = {x.upper() for x in args.only.split(",") if x}
    log(f"clear_global: {len(packages)} dataset(s) from {PUBLISHER} on HDX")
    records: list[dict[str, Any]] = []
    written: list[str] = []
    for package in sorted(packages, key=lambda p: str(p.get("name"))):
        if only and iso3(package) not in only:
            continue
        got = country_records(package)
        if got:
            written.append(f"{iso3(package)}:{len(got)}")
        records += got
    if not records:
        raise SystemExit("clear_global: nothing usable was read; writing nothing")
    log(f"  {len(records)} first-level units in {len(written)} countries: "
        f"{', '.join(written)}")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
