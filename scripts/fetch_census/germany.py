#!/usr/bin/env python3
"""Germany -- Zensus 2022 religion by Land, from the results database.

Germany was the largest European country with nothing below the national line:
sixteen Laender, eleven carrying a population figure and none a composition.
``scripts/probe_genesis.py`` established why nobody had filled it, and the
answer was not that the data is missing. Four things had to be settled first,
and each is recorded here because each was nearly mistaken for an absence:

* The database speaks POST and answers 405 to a GET.
* It reads the credential from **request headers**. As query parameters, as
  HTTP Basic and as a bearer token it ignores them and keeps answering as the
  anonymous user GAST, which is indistinguishable from a rejected account until
  ``helloworld/logincheck`` is asked who it thinks it is talking to.
* ``data/tablefile`` returns a **ZIP** holding one CSV whatever
  ``compress=false`` says, and that CSV is UTF-8 with a byte-order mark.
* Of the four tables titled *Personen: Religion*, only **1000A-1018** is cut by
  a civil geography. The others are cut by 19 Landeskirchen, 27 Bistuemer and
  299 Bundestagswahlkreise -- two church administrations and an electoral map,
  none of them anything a boundary file draws. Guessing would have been wrong
  three times in four.

**What the three categories are, and are not.** RELZG2 offers Roman Catholic
Church, Protestant Church, and "Sonstige, keine, ohne Angabe". These are
memberships of a *public-law corporation* -- the church-tax register -- and not
answers to a question about belief. Germany's Muslims, Jews, Orthodox
Christians and free-church Protestants are inside the third category together
with the irreligious and the non-responding, because their communities are
mostly not corporations under public law. That category runs from 44% in
Baden-Wuerttemberg to 83% in Mecklenburg-Vorpommern, so it is the largest bar
in every Land and it is the least informative one. The record says so in
``religion_note`` rather than letting three bars imply the question had three
answers.

The finer classification exists -- RELZG1, seven categories, table 2000X-1022
-- and is published for Germany as a whole and no further. Germany publishes
something coarser about its Laender than about itself.

Usage:
    python -m scripts.fetch_census.germany --level land
    python -m scripts.fetch_census.germany --level regierungsbezirk
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
)

BASE = "https://ergebnisse.zensus2022.de/api/rest/2020"
TABLE = "1000A-1018"
TIMEOUT = 120

# One table, four geographies. 1000A-1018 is published cut by Bundeslaender, by
# 36 Regierungsbezirke, by 400 Landkreise and by 10,787 Gemeinden, and asking
# for it without naming one returns whichever it calls its default -- which is
# how it was read four times as a sixteen-row table while the finer cuts sat
# behind the same code, never absent and never asked for.
#
# geoBoundaries draws Germany at ADM2 as 38 Regierungsbezirke and statistische
# Regionen -- Arnsberg, Detmold, Duesseldorf, Koeln and Muenster for NRW,
# Oberbayern through Schwaben for Bavaria, and the smaller Laender standing as
# one unit each. So GEORB1 is the cut this map can use and GEOLK4 is not: 400
# Kreise would join nothing at all while looking like four hundred rows of
# progress.
LEVELS: dict[str, tuple[str, str, str, int]] = {
    "land": ("GEOBL1", "admin1", "germany_land.json", 16),
    "regierungsbezirk": ("GEORB1", "admin2", "germany_regierungsbezirk.json", 0),
}

# The census date the table itself carries, not the year the file was made.
CENSUS_YEAR = 2022

SOURCE = ("Statistisches Bundesamt, Zensus 2022, Tabelle 1000A-1018 "
          "(Personen: Religion, Bundeslaender)")
URL = "https://ergebnisse.zensus2022.de/datenbank/online/statistic/1000A/table/1000A-1018"

# The published German labels, and the English this map shows. Kept as a
# declaration rather than a guess: an unknown label stops the run, the way
# Russia's and Brazil's do, because a category silently dropped is a share that
# no longer sums to the population.
RELIGION: dict[str, str] = {
    "REL-RK-OR": "Roman Catholic",
    "REL-EV-OR": "Protestant",
    "REL-SONST-X": "Other, none, or not stated",
}

NOTE = (
    "Zensus 2022 records membership of a religious body incorporated under "
    "public law -- the church-tax register -- not religious belief. Only the "
    "Roman Catholic and Protestant churches are counted separately; Muslims, "
    "Jews, Orthodox Christians and free-church Protestants fall inside "
    "'Other, none, or not stated' along with people of no religion and those "
    "who did not answer, because their communities are mostly not public-law "
    "corporations. Germany publishes a seven-category classification for the "
    "country as a whole but not by Land."
)


def credentials() -> dict[str, str]:
    """The account, as headers, which is the only place this API reads it.

    Measured rather than assumed -- see the module docstring. Missing
    credentials are a refusal here and not a fallback to anonymous: GAST can
    search the catalogue and read nothing, so an anonymous run would fetch a
    401 and have to be told apart from a table that had gone away.
    """
    user = os.environ.get("ZENSUS_USER", "").strip()
    password = os.environ.get("ZENSUS_PASSWORD", "").strip()
    if not (user and password):
        raise SystemExit(
            "germany: ZENSUS_USER and ZENSUS_PASSWORD are needed. The Zensus "
            "2022 database lets an anonymous user search its catalogue and "
            "read nothing -- every data endpoint answers 401 -- so without an "
            "account there is nothing to fetch. Registration is free at "
            "https://ergebnisse.zensus2022.de; the credentials belong in "
            "repository secrets and reach this script through the environment.")
    return {"username": user, "password": password}


def tablefile(name: str, auth: dict[str, str], region: str = "") -> str:
    """The table as CSV text, out of the ZIP the API answers with."""
    params = {
        "name": name, "area": "all", "format": "ffcsv",
        "compress": "false", "language": "de",
    }
    if region:
        # regionalvariable is what asks for a geography other than the default.
        params["regionalvariable"] = region
        params["regionalschluessel"] = ""
    body = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(
        f"{BASE}/data/tablefile", data=body,
        headers={"Accept": "*/*",
                 "Content-Type": "application/x-www-form-urlencoded",
                 **auth},
        method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = response.read()
    if payload.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if not names:
                raise SystemExit(f"germany: {name} came back as an empty archive")
            payload = archive.read(names[0])
    # utf-8-sig: the byte-order mark would otherwise ride along on the first
    # column name and no header lookup would match it.
    return payload.decode("utf-8-sig", "replace")


# GEORB1 is "Regierungsbezirke/Statistische Regionen", and the slash is doing
# real work: the thirty-six areas are of three kinds and each kind is labelled
# with its own prefix. North Rhine-Westphalia, Bavaria, Baden-Wuerttemberg and
# Hesse still have Regierungsbezirke ("Reg.-Bez. Arnsberg"); Saxony renamed
# theirs Direktionsbezirke; Lower Saxony abolished theirs in 2004 and reports
# statistische Regionen in their place. The boundary file carries the bare
# name in all three cases.
#
# Stripped in the reader rather than declared in MISSPELLED: these are prefixes
# a source puts on every row of a geography, not names anybody got wrong.
_REGION_PREFIXES = ("Reg.-Bez. ", "Direktionsbezirk ", "Statistische Region ")


def shape_name(label: str) -> str:
    """The label as the boundary file spells it."""
    for prefix in _REGION_PREFIXES:
        if label.startswith(prefix):
            return label[len(prefix):].strip()
    return label


def parse(text: str, region_code: str = "GEOBL1") -> dict[str, dict[str, Any]]:
    """Land -> {name, counts by English group, total}.

    ffcsv is one row per cell: the variables spelled out with their codes and
    labels, then the value and its unit. Every figure appears twice, once as a
    percentage and once as a count, and only the counts are read -- a share
    reconstructed from a rounded percentage is out by thousands of people and
    carries no sign that it was never counted.
    """
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    if not rows:
        raise SystemExit("germany: the table came back with no rows")

    laender: dict[str, dict[str, Any]] = {}
    unknown: set[str] = set()
    for row in rows:
        if row.get("1_variable_code") != region_code:
            continue
        if (row.get("value_unit") or "").strip() != "Anzahl":
            continue                      # the percentage twin of this cell
        code = (row.get("1_variable_attribute_code") or "").strip()
        name = shape_name((row.get("1_variable_attribute_label") or "").strip())
        group_code = (row.get("2_variable_attribute_code") or "").strip()
        raw = (row.get("value") or "").strip()
        if not (code and name and raw):
            continue
        try:
            count = int(raw)
        except ValueError:
            continue                      # a suppressed or dashed cell
        entry = laender.setdefault(code, {"name": name, "counts": {},
                                          "total": None})
        if not group_code:                # "Insgesamt", the row's own total
            entry["total"] = count
            continue
        group = RELIGION.get(group_code)
        if group is None:
            unknown.add(f"{group_code} ({row.get('2_variable_attribute_label')})")
            continue
        entry["counts"][group] = entry["counts"].get(group, 0) + count

    if unknown:
        raise SystemExit(
            "germany: RELZG2 categories this build has never seen: "
            + ", ".join(sorted(unknown))
            + ". Add them to RELIGION rather than letting a category fall out "
              "of a composition that is supposed to sum to the population.")
    return laender


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="land", choices=list(LEVELS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    region_code, level, filename, expected = LEVELS[args.level]
    log(f"germany: Zensus 2022 table {TABLE}, cut by {region_code} ({args.level})")
    auth = credentials()
    try:
        text = tablefile(TABLE, auth, region_code)
    except urllib.error.HTTPError as err:
        raise SystemExit(
            f"germany: {TABLE} answered HTTP {err.code} {err.reason}. A 401 "
            f"here means the account was not accepted -- this API reads the "
            f"credential from the request headers and ignores it as a query "
            f"parameter, so a working account presented the wrong way looks "
            f"exactly like a rejected one.") from err

    areas = parse(text, region_code)
    log(f"  {len(areas)} areas in the {region_code} cut")
    if expected and len(areas) != expected:
        raise SystemExit(
            f"germany: expected {expected} areas from {region_code} and the "
            f"table held {len(areas)}. That is a different geography from the "
            f"one this adapter was written against, and the join should not be "
            f"given it unchecked.")
    if not areas:
        raise SystemExit(f"germany: {region_code} returned no areas at all")

    records = []
    for code, entry in sorted(areas.items()):
        counts = entry["counts"]
        total = entry["total"]
        if total and counts:
            summed = sum(counts.values())
            # The three categories are exhaustive by construction, so a gap
            # between them and the published total means a category was missed
            # -- exactly what shares() would silently paper over by using its
            # own sum as the denominator.
            if abs(summed - total) > max(16, total * 0.001):
                raise SystemExit(
                    f"germany: {entry['name']} sums to {summed:,} against a "
                    f"published total of {total:,}. The categories are meant "
                    f"to be exhaustive; a difference this size means one was "
                    f"dropped.")
        # A Regierungsbezirk's key opens with its Land's: 059 is Arnsberg in
        # 05, Nordrhein-Westfalen. So the parent is read off the code rather
        # than looked up, and the sixteen Laender parent Germany itself.
        parent = "DEU" if level == "admin1" else f"DEU-{code[:2]}"
        records.append(record(
            f"DEU-{code}", entry["name"], level=level, parent=parent,
            codes={"ags": code},
            population=(measure(int(total), year=CENSUS_YEAR, source=SOURCE)
                        if total else gap(NOT_AVAILABLE)),
            religion=shares(counts, total=total) or gap(NOT_AVAILABLE),
            religion_note=NOTE,
            religion_year=CENSUS_YEAR,
            sources=[{"field": "religion/population", "name": SOURCE,
                      "url": URL, "license": "Destatis, Datenlizenz Deutschland Namensnennung 2.0"}],
        ))

    out = args.out or PROCESSED / filename
    write_json(out, records)
    log(f"  wrote {out}")
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
