#!/usr/bin/env python3
"""Germany -- Zensus 2022 religion and nationality by Land and Regierungsbezirk.

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

**Nationality as ethnicity.** Germany's census asks no ethnicity question; it
counts citizenship. By the owner's decision of 19 September 2026 that count
is carried on the ethnicity field under ``ethnicity_basis: "nationality"``
(see ``central_nationality``), from table 1000A-1021, the 41 nationalities
most frequent in Germany, read at the same cuts as religion. A person who
holds German citizenship is counted German whatever else they hold.

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
from .central_nationality import GERMAN, composition, label_for, named

BASE = "https://ergebnisse.zensus2022.de/api/rest/2020"
TABLE = "1000A-1018"
TIMEOUT = 300
# The two tables read, by what they give: religion (RELZG2) and the 41
# nationalities most frequent in Germany (STALD4), both of the census day.
TABLES: dict[str, str] = {"religion": "1000A-1018", "nationality": "1000A-1021"}
LICENCE = "Destatis, Datenlizenz Deutschland Namensnennung 2.0"
# A nationality is named when its people are at least this share of Germany's.
NAMED_SHARE = 0.002

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
# Nine Laender have no Regierungsbezirke at all, so GEORB1 has no row for them
# -- and geoBoundaries draws each as a single ADM2 shape carrying the Land's own
# name. The shape is the Land, so the Land's figures are that shape's figures,
# and leaving them blank would mark as unmeasured nine places that were measured
# exactly once at exactly this extent.
#
# Declared rather than derived, because the rule "a Land with no GEORB1 row"
# catches ten and the tenth must not be filled. Rhineland-Palatinate abolished
# its Regierungsbezirke in 2000; geoBoundaries still draws Koblenz, Trier and
# Rheinhessen-Pfalz, so its one Land figure would have to be split three ways
# and cannot be. It stays a visible gap, which is the honest answer.
WHOLE_LAND_REGIONS: dict[str, str] = {
    "01": "Schleswig-Holstein",
    "02": "Hamburg",
    "04": "Bremen",
    "10": "Saarland",
    "11": "Berlin",
    "12": "Brandenburg",
    "13": "Mecklenburg-Vorpommern",
    "15": "Sachsen-Anhalt",
    "16": "Thüringen",
}

# Rhineland-Palatinate abolished its Regierungsbezirke in 2000, but NUTS 2
# still divides it into the three statistical regions geoBoundaries draws,
# and every Kreis's key still carries the old Bezirk in its third digit: 071xx
# are Koblenz's, 072xx Trier's, 073xx Rheinhessen-Pfalz's (Kreis codes 07111
# Koblenz city through 07340 Suedwestpfalz). So the three are sums of the
# Kreis cut of the same table (GEOLK4), and the sum of the three must be the
# Land's own figure from the Land cut.
RLP_REGIONS: dict[str, str] = {"071": "Koblenz", "072": "Trier", "073": "Rheinhessen-Pfalz"}

LEVELS: dict[str, tuple[str, str, str, int]] = {
    "land": ("GEOBL1", "admin1", "germany_land.json", 16),
    "regierungsbezirk": ("GEORB1", "admin2", "germany_regierungsbezirk.json", 38),
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

NATIONALITY_SOURCE = ("Statistisches Bundesamt, Zensus 2022, Tabelle 1000A-1021 "
                      "(Personen: Staatsangehörigkeit (Häufigste Länder))")
NATIONALITY_URL = ("https://ergebnisse.zensus2022.de/datenbank/online/statistic/1000A/table/"
                   "1000A-1021")
NATIONALITY_NOTE = (
    "Population by citizenship (Staatsangehörigkeit) on 15 May 2022, Zensus 2022 (table "
    "1000A-1021, the 41 nationalities most frequent in Germany): NATIONALITY, not ethnicity, "
    "which Germany's census does not ask. A person holding German citizenship is counted as "
    "German whatever other citizenship they also hold, naturalised citizens and ethnic German "
    f"resettlers included; nationalities below {NAMED_SHARE:.1%} of Germany's population, those "
    "the table does not list, the stateless and those whose citizenship is unclear are 'Other "
    "nationalities'. Zensus 2022 protects its cells with the cell key method, which can move a "
    "count by a few people.")


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


def parse(text: str, region_code: str = "GEOBL1", table: str = "religion"
          ) -> dict[str, dict[str, Any]]:
    """Area code -> {name, counts by group, total}.

    ffcsv is one row per cell: the variables spelled out with their codes and
    labels, then the value and its unit. Every figure appears twice, once as a
    percentage and once as a count, and only the counts are read -- a share
    reconstructed from a rounded percentage is out by thousands of people and
    carries no sign that it was never counted.

    For religion a group is RELIGION's English name for the RELZG2 code, and
    an unknown code stops the run. For nationality it is the country as the
    table names it ("Türkei"); the labels are applied later, by
    ``central_nationality``, which refuses a large one it has no label for.
    """
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    if not rows:
        raise SystemExit("germany: the table came back with no rows")

    areas: dict[str, dict[str, Any]] = {}
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
        entry = areas.setdefault(code, {"name": name, "counts": {}, "total": None})
        if not group_code:                # "Insgesamt", the row's own total
            entry["total"] = count
            continue
        if table == "religion":
            group = RELIGION.get(group_code)
            if group is None:
                unknown.add(f"{group_code} ({row.get('2_variable_attribute_label')})")
                continue
        else:
            group = (row.get("2_variable_attribute_label") or "").strip()
        entry["counts"][group] = entry["counts"].get(group, 0) + count

    if unknown:
        raise SystemExit(
            "germany: RELZG2 categories this build has never seen: "
            + ", ".join(sorted(unknown))
            + ". Add them to RELIGION rather than letting a category fall out "
              "of a composition that is supposed to sum to the population.")
    return areas


def fetch(name: str, auth: dict[str, str], region: str) -> str:
    try:
        return tablefile(name, auth, region)
    except urllib.error.HTTPError as err:
        body = (err.read() or b"")[:600].decode("utf-8", "replace")
        raise SystemExit(
            f"germany: {name} cut by {region} answered HTTP {err.code} {err.reason} ({body!r}). "
            f"A 401 here means the account was not accepted -- this API reads the "
            f"credential from the request headers and ignores it as a query "
            f"parameter, so a working account presented the wrong way looks "
            f"exactly like a rejected one.") from err


def gather(table: str, auth: dict[str, str], level: str) -> dict[str, dict[str, Any]]:
    """One table's areas at one level of the map, checked.

    The Laender are GEOBL1's sixteen rows. The second level is GEORB1's
    Regierungsbezirke and statistische Regionen, the nine Laender that are one
    region each (WHOLE_LAND_REGIONS) from GEOBL1, and Rhineland-Palatinate's
    three regions summed from GEOLK4's Kreise, which must make the Land.
    """
    name = TABLES[table]
    region_code, _, _, expected = LEVELS[level]
    log(f"germany: Zensus 2022 table {name} ({table}), cut by {region_code} ({level})")
    areas = parse(fetch(name, auth, region_code), region_code, table)
    log(f"  {len(areas)} areas in the {region_code} cut")

    if level == "regierungsbezirk":
        # The nine Laender that are one region. Their figures come from the
        # Land cut of the same table, because GEORB1 simply has no row for a
        # Land that never divided.
        whole = parse(fetch(name, auth, "GEOBL1"), "GEOBL1", table)
        added = 0
        for code, land in WHOLE_LAND_REGIONS.items():
            entry = whole.get(code)
            if entry is None:
                raise SystemExit(
                    f"germany: {land} ({code}) is declared a whole-Land region "
                    f"and the Land cut has no row for it. One of the two lists "
                    f"has moved and guessing which would fill a shape with the "
                    f"wrong Land's figures.")
            if entry["name"] != land:
                raise SystemExit(
                    f"germany: Land {code} is declared as {land!r} and the "
                    f"table calls it {entry['name']!r}.")
            if code in areas:
                raise SystemExit(
                    f"germany: {land} is declared a whole-Land region and "
                    f"GEORB1 now has its own row for it. The declaration is "
                    f"stale and would double-count.")
            areas[code] = entry
            added += 1
        log(f"  + {added} Laender that are a single region")
        kreise = parse(fetch(name, auth, "GEOLK4"), "GEOLK4", table)
        rlp = {code: e for code, e in kreise.items() if code.startswith("07") and len(code) >= 5}
        if {code[:3] for code in rlp} != set(RLP_REGIONS):
            raise SystemExit(f"germany: Rhineland-Palatinate's Kreise open with "
                             f"{sorted({code[:3] for code in rlp})}, not {sorted(RLP_REGIONS)}")
        for prefix, region in RLP_REGIONS.items():
            members = [e for code, e in rlp.items() if code.startswith(prefix)]
            counts: dict[str, int] = {}
            for e in members:
                for group, n in e["counts"].items():
                    counts[group] = counts.get(group, 0) + n
            if any(e["total"] is None for e in members):
                raise SystemExit(f"germany: a Kreis of {region} has no total")
            areas[prefix] = {"name": region, "counts": counts,
                             "total": sum(e["total"] for e in members)}
            log(f"  + {region}: {len(members)} Kreise, {areas[prefix]['total']:,}")
        summed = sum(areas[p]["total"] for p in RLP_REGIONS)
        land = whole["07"]["total"]
        if summed != land:
            raise SystemExit(f"germany: the three regions of Rhineland-Palatinate make "
                             f"{summed:,}, the Land cut says {land:,}")
    if expected and len(areas) != expected:
        raise SystemExit(
            f"germany: expected {expected} areas from {region_code} and the "
            f"table held {len(areas)}. That is a different geography from the "
            f"one this adapter was written against, and the join should not be "
            f"given it unchecked.")
    if not areas:
        raise SystemExit(f"germany: {region_code} returned no areas at all")
    return areas


def religion_fields(entry: dict[str, Any]) -> dict[str, Any]:
    counts, total = entry["counts"], entry["total"]
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
    return {"religion": shares(counts, total=total) or gap(NOT_AVAILABLE),
            "religion_note": NOTE, "religion_year": CENSUS_YEAR}


def nationality_fields(areas: dict[str, dict[str, Any]], national: dict[str, Any]
                       ) -> dict[str, dict[str, Any]]:
    """{area code: the ethnicity fields} from 1000A-1021, every area named alike.

    The table lists the 41 nationalities most frequent in Germany; those at
    NAMED_SHARE of the country or more are named everywhere and the rest of
    each area's people -- the other listed nationalities, those the table does
    not list, the stateless and those whose citizenship is unclear -- are
    "Other nationalities". The cell key method with which Zensus 2022 protects
    its cells can move a count by a few people, so a composition is checked
    against its area's total rather than its cells against each other.
    """
    total = national["total"]
    labels: dict[str, str | None] = {c: label_for(c, GERMAN) for c in national["counts"]}
    names = named(national["counts"], total, labels, share=NAMED_SHARE, always=["Deutschland"])
    log(f"  named: {', '.join(str(labels[n]) for n in names)}")
    out: dict[str, dict[str, Any]] = {}
    for code, entry in areas.items():
        if entry["total"] is None:
            raise SystemExit(f"germany: {entry['name']} has no total in {TABLES['nationality']}")
        counts = dict(entry["counts"])
        listed = sum(counts.values())
        if listed > entry["total"] + max(16, 0.001 * entry["total"]):
            raise SystemExit(f"germany: {entry['name']}: the listed nationalities make "
                             f"{listed:,}, more than the total {entry['total']:,}")
        # The people of nationalities the table does not list, so that the
        # categories make the total.
        counts["__unlisted__"] = max(entry["total"] - listed, 0)
        out[code] = {
            "ethnicity": composition(counts, entry["total"], names,
                                     {**labels, "__unlisted__": None},
                                     where=f"germany: {entry['name']}"),
            "ethnicity_year": CENSUS_YEAR, "ethnicity_basis": "nationality",
            "ethnicity_note": NATIONALITY_NOTE,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="land", choices=list(LEVELS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    _, level, filename, _ = LEVELS[args.level]
    auth = credentials()
    religion = gather("religion", auth, args.level)
    citizens = gather("nationality", auth, args.level)
    if set(religion) != set(citizens):
        raise SystemExit(f"germany: the religion and nationality tables cover different areas: "
                         f"{sorted(set(religion) ^ set(citizens))}")
    for code in religion:
        a, b = religion[code]["total"], citizens[code]["total"]
        if a is not None and b is not None and a != b:
            raise SystemExit(f"germany: {religion[code]['name']}: the two tables count "
                             f"{a:,} and {b:,} people")
    national = parse(fetch(TABLES["nationality"], auth, "GEOBL1"), "GEODL1", "nationality")
    if len(national) != 1:
        raise SystemExit(f"germany: {len(national)} national rows in the nationality table")
    ethnicity = nationality_fields(citizens, next(iter(national.values())))

    records = []
    for code, entry in sorted(religion.items()):
        total = entry["total"]
        # A Regierungsbezirk's key opens with its Land's: 059 is Arnsberg in
        # 05, Nordrhein-Westfalen. So the parent is read off the code rather
        # than looked up, and the sixteen Laender parent Germany itself.
        parent = "DEU" if level == "admin1" else f"DEU-{code[:2]}"
        if level == "admin2" and code in RLP_REGIONS:
            entity_id = f"DEU-{code}-SR"
        else:
            # A whole-Land region's key is its Land's, so its record id would
            # collide with the Land's own. The suffix keeps them apart; the
            # ags code stays the real one.
            entity_id = (f"DEU-{code}-RB"
                         if level == "admin2" and code in WHOLE_LAND_REGIONS
                         else f"DEU-{code}")
        records.append(record(
            entity_id, entry["name"], level=level, parent=parent,
            codes={"ags": code},
            population=(measure(int(total), year=CENSUS_YEAR, source=SOURCE)
                        if total else gap(NOT_AVAILABLE)),
            **religion_fields(entry),
            **ethnicity[code],
            sources=[{"field": "religion/population", "name": SOURCE,
                      "url": URL, "license": LICENCE},
                     {"field": "ethnicity", "name": NATIONALITY_SOURCE,
                      "url": NATIONALITY_URL, "license": LICENCE}],
        ))

    out = args.out or PROCESSED / filename
    write_json(out, records)
    log(f"  wrote {out}")
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
