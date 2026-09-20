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

from ._shared import PROCESSED, log, record, write_json

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
# "clearglobal_language_use_SOM_admin1.csv" in the 2025 release and
# "th_lang_admin1_v01.csv" in the older one. The version suffix matters: a
# pattern that required the name to end at "admin1" missed the four older
# files and reported "no first-level file on this dataset", which is a
# different and untrue reason for the same refusal. They have a first-level
# file; it is the wrong shape, and the header test is what should say so.
ADMIN1_FILE = re.compile(r"admin_?1(?!\d).*\.csv$", re.I)
YEAR = re.compile(r"(1[89]\d\d|20\d\d)")


# ---------------------------------------------------------------------------
# What CLEAR Global calls a unit, against what the boundary file calls it
# ---------------------------------------------------------------------------

# CLEAR Global names its first-level units in whatever the source study used,
# and the boundary file names them in English. Where the two disagree the
# build's matcher does not silently fail -- it does something worse. Its
# prefix pass joined "Papua Barat" to the shape called Papua, because "Papua"
# starts "Papua Barat" and no row was named Papua to out-rank it; West Papua's
# composition would have been painted on the province next door while West
# Papua itself stayed empty. "Kepulauan Riau" reached Riau and "Maluku Utara"
# reached Maluku the same way; those two were caught only because a row really
# was named Riau and really was named Maluku, so the collision rule refused
# them both. The one with no rival got through.
#
# Measured against the boundary files in this repository, 96 of 662 rows
# reached no shape at all and three reached the wrong one. So the names are
# declared here rather than guessed there. Each entry is a spelling or a
# translation of the same place -- Indonesian against English, Swahili against
# English, French against English, one transliteration of Arabic against
# another -- and every right-hand side is a name that exists in this repo's
# own admin1 file for that country, which is what makes the table checkable.
#
# What is deliberately NOT here:
#   * Botswana's Gaborone, Francistown, Lobatse, Selibe Phikwe and Jwaneng.
#     They are towns with their own row in CLEAR Global's file and no
#     first-level shape at all in the boundary file. There is nothing to join
#     them to, and inventing one would put a city's languages on a district.
#   * Tanzania's Songwe, split out of Mbeya in 2016, after the boundary file.
#   * Kyrgyzstan's Bishkek (city), for the same reason as Botswana's towns.
#   * Ukraine, Ethiopia, Benin, Mali, Nepal, Namibia, Niger, Sierra Leone and
#     South Africa, whose 24 unmatched rows would gain nothing: each of those
#     countries already carries language from its own census, and this file is
#     first in ADAPTER_FILES precisely so that a census beats it. Aliasing them
#     would add 24 chances to mis-match in exchange for no figure.
# Each of those stays an honest gap, which is the cheaper mistake.
BOUNDARY_ALIASES: dict[str, dict[str, str]] = {
    # Indonesian against English, both directions of the compass word.
    "IDN": {
        "Sumatera Utara": "North Sumatra",
        "Sumatera Barat": "West Sumatra",
        "Sumatera Selatan": "South Sumatra",
        "Kepulauan Bangka Belitung": "Bangka-Belitung Islands",
        "Kepulauan Riau": "Riau Islands",
        "Dki Jakarta": "Jakarta Special Capital Region",
        "Jawa Barat": "West Java",
        "Jawa Tengah": "Central Java",
        "Jawa Timur": "East Java",
        "Daerah Istimewa Yogyakarta": "Special Region of Yogyakarta",
        "Nusa Tenggara Barat": "West Nusa Tenggara",
        "Nusa Tenggara Timur": "East Nusa Tenggara",
        "Kalimantan Barat": "West Kalimantan",
        "Kalimantan Tengah": "Central Kalimantan",
        "Kalimantan Selatan": "South Kalimantan",
        "Kalimantan Timur": "East Kalimantan",
        "Kalimantan Utara": "North Kalimantan",
        "Sulawesi Utara": "North Sulawesi",
        "Sulawesi Tengah": "Central Sulawesi",
        "Sulawesi Selatan": "South Sulawesi",
        "Sulawesi Tenggara": "Southeast Sulawesi",
        "Sulawesi Barat": "West Sulawesi",
        "Maluku Utara": "North Maluku",
        "Papua Barat": "West Papua",
    },
    # Two transliterations of the same Arabic names.
    "IRQ": {
        "Al-Najaf": "An-Najaf",
        "Al-Qadissiya": "Al-Qadisiyah",
        "Kerbala": "Karbala",
        "Ninewa": "Ninawa",
        "Thi Qar": "Dhi Qar",
        "Wassit": "Wasit",
    },
    # English against the French the boundary file keeps, and it keeps it
    # inconsistently: three departments carry "Departement de/du" and three
    # carry the English word "Department" after the French name.
    "HTI": {
        "West": "Departement de l'Ouest",
        "North": "Departement du Nord",
        "South-East": "Departement du Sud-Est",
        "North-East": "Nord-Est Department",
        "North-West": "Nord-Ouest Department",
        "South": "Sud Department",
    },
    "COD": {
        "Bas-Uele": "Lower Uele",
        "Haut-Uele": "Upper Uele",
        "Nord-Kivu": "North Kivu",
        "Sud-Kivu": "South Kivu",
    },
    # "Bantey" is the boundary file's own misspelling of Banteay.
    "KHM": {
        "Banteay Meanchey": "Bantey Meanchey",
        "Ratanak Kiri": "Ratanakiri Province",
        "Tboung Khmum": "Tbong Khmum",
    },
    # The boundary file uses the initials. BARMM is not quite ARMM -- it
    # replaced it in 2019 and took in Cotabato City and 63 barangays of North
    # Cotabato -- but it is the same region in the same place under a new
    # charter, and the alternative is leaving the whole of Muslim Mindanao
    # blank. The difference is one of vintage, which the record already states.
    "PHL": {
        "National Capital Region (NCR)": "NCR",
        "Cordillera Administrative Region (CAR)": "CAR",
        "Bangsamoro Autonomous Region In Muslim Mindanao (BARMM)": "ARMM",
    },
    "SOM": {
        "Hiraan": "Hiiraan",
        "Middle Shabelle": "Middle Shebelle",
        "Lower Shabelle": "Lower Shebelle",
    },
    "KGZ": {"Chui": "Chuy Region"},
    "SLV": {
        "La Paz": "Departamento de La Paz",
        "Santa Ana": "Departamento de Santa Ana",
    },
    "MAR": {
        "Fes-Meknes": "Fez-Meknes",
        "Tanger-Tetouan-Al Hoceima": "Tangier-Tetouan-Al Hoceima",
    },
    # The Gambia names its regions twice over: CLEAR Global uses the region
    # name and the boundary file uses the town each region is administered
    # from. Central River is one region in the boundary file's vintage and two
    # in CLEAR Global's, North and South, so each half is declared against the
    # town that administers it.
    "GMB": {
        "Upper River": "Basse",
        "West Coast": "Brikama",
        "North Bank": "Kerewan",
        "Lower River": "Mansakonko",
        "Central River North": "Kuntaur",
        "Central River South": "Janjanbureh",
    },
    # Swahili against English, for the five Zanzibar and Pemba regions.
    "TZA": {
        "Kaskazini Unguja": "Zanzibar North",
        "Kusini Unguja": "Zanzibar South & Central",
        "Mjini Magharibi": "Zanzibar Urban/West",
        "Kaskazini Pemba": "North Pemba",
        "Kusini Pemba": "South Pemba",
    },
    "MUS": {
        "Plaine Wilhems": "Plaines Wilhems",
        "Rodriguez Island": "Rodrigues",
    },
    "COG": {"Point-Noire": "Pointe-Noire"},
}


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


def compose(rows: list[dict[str, str]]
            ) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """{unit code: {name, shares, total}}, and the units dropped, with reasons.

    The dropped ones come back in two lists, because they are two different
    findings and only one of them is evidence about the file. A unit whose
    shares do not add to one says this table may not be a composition at all,
    and enough of those condemn the country's file. A unit the file declines
    to name -- a DHS extract's "level 1 unknown" -- says only that the study
    could not place some of its respondents, which is normal and is not a
    reason to throw away the regions it did place. Sudan was refused whole on
    that confusion: two named states and one "sudan: level 1 unknown", and
    a third of the rows unnamed read as a third of the rows broken.

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
    unnamed: list[str] = []
    refused: list[str] = []
    for code, unit in units.items():
        name = unit["name"]
        if UNKNOWN_UNIT.search(name) or code.upper().endswith("XXX"):
            unnamed.append(f"{name} ({code}): the file does not say which unit this is")
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
    return kept, refused, unnamed


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

    kept, refused, unnamed = compose(rows)
    for line in unnamed[:4]:
        log(f"    dropped {line}")
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
    aliases = BOUNDARY_ALIASES.get(iso, {})
    for code, unit in sorted(kept.items()):
        records.append(record(
            f"{iso}-CG-{code}", unit["name"], level="admin1", parent=iso,
            country=iso,
            aliases=aliases.get(unit["name"]) and [aliases[unit["name"]]],
            language=unit["shares"],
            language_year=year,
            language_note=note,
            sources=[{"field": "language", "name": source_name,
                      "url": DATASET_PAGE.format(stub=stub),
                      "license": terms}],
        ))
    log(f"    {len(records)} unit(s) written, {len(refused)} not a composition, "
        f"{len(unnamed)} unnamed, year {year}, "
        f"{methodology or 'methodology not stated'}")
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
