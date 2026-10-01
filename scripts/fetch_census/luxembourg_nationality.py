#!/usr/bin/env python3
"""Luxembourg: nationality as ethnicity, by commune and canton, from the 2021 census.

Luxembourg's census asks citizenship, not ethnicity. By the owner's decision
of 19 September 2026 that count is carried on the ethnicity field under
``ethnicity_basis: "nationality"`` (see ``central_nationality``).

**What is read.** STATEC's 2021 census (8 November 2021) on LUSTAT,
DSD_CENSUS_GROUP7_10@DF_B1625, "Population by canton and municipality,
citizenship and sex": Luxembourgers, citizens of the other EU-27 countries,
citizens of non-EU countries, the stateless and those whose citizenship was
not stated, for the 102 communes of 2021 and the 12 cantons. It is the only
citizenship table STATEC publishes by commune for that census, and it groups
the foreign citizenships as the EU's statistics do; no finer one exists by
commune.

**The six drawn parts** of the three communes merged in 2018 (Habscht,
Helperknapp, Rosport-Mompach), which the 2021 census counts merged, take the
2011 census's population of usual residence by commune and nationality (1
February 2011, STATEC on data.public.lu), the last count of each, grouped the
same way: the 25 EU-27 countries the 2011 table names; the United Kingdom,
then a member, and the rest of the world as non-EU, as EU-27 counts it today.
The 2011 table names no Croatians -- Croatia joined in 2013 -- and counts
them among the other European countries, so they are non-EU here.

Usage:
    python -m scripts.fetch_census.luxembourg_nationality
"""

from __future__ import annotations

import argparse
import csv
import io
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .central_ages import check_sum, fold, units
from .central_nationality import STATELESS, UNKNOWN, composition, note
from .luxembourg import (LICENCE, LUXDATA, MAP_NAMES, MERGED_SINCE_MAP, OLD_NAMES, PORTAL, book_rows,
                         num, text_of)

DATA = ("https://lustat.statec.lu/rest/data/LU1,DSD_CENSUS_GROUP7_10@DF_B1625,1.0/all"
        "?dimensionAtObservation=AllDimensions")
SOURCE = "STATEC, Recensement de la population 2021, LUSTAT DF_B1625 (citizenship by commune)"
RP2011 = (LUXDATA + "population-de-residence-habituelle-par-commune-et-nationalite-au-1er-fevrier-"
          "2011/20160711-131429/Population_par_commune_et_nationalite_au_1er_fevrier_2011.xlsx")
RP2011_SOURCE = ("STATEC, Recensement de la population 2011 (1 February 2011), population of usual "
                 "residence by commune and nationality")
OUT = PROCESSED / "luxembourg_nationality.json"
YEAR = 2021
LABELS = {"NAT": "Luxembourger", "EU_FOR": "Other EU nationals", "NEU": "Non-EU nationals",
          "STLS": STATELESS, "UNK": UNKNOWN}
# The 2011 table's columns, grouped as DF_B1625 groups citizenship.
EU27_2011 = ("Belgique", "Bulgarie", "République tchèque", "Danemark", "Allemagne", "Estonie",
             "Irlande", "Grèce", "Espagne", "France", "Italie", "Chypre", "Lettonie", "Lituanie",
             "Hongrie", "Malte", "Pays-Bas", "Autriche", "Pologne", "Portugal", "Roumanie",
             "Slovénie", "Slovaquie", "Finlande", "Suède")
NON_EU_2011 = ("Royaume-Uni", "Autre pays européen", "Pays en Afrique",
               "Pays des Caraïbes, d’Amérique du sud ou centrale", "Pays d’Amérique du nord",
               "Pays d’Asie", "Pays d’Océanie")


def read() -> tuple[dict[str, str], dict[str, dict[str, float]]]:
    """GEO labels and {geo: {citizenship code: people}}, both sexes."""
    blob = http_get(DATA, headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0;labels=both"},
                    timeout=300)
    rows = list(csv.DictReader(io.StringIO(blob)))
    if not rows:
        raise SystemExit("luxembourg_nationality: DF_B1625 came back empty")
    col = {k.split(":")[0]: k for k in rows[0]}
    labels: dict[str, str] = {}
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        geo, _, label = row[col["GEO"]].partition(": ")
        labels[geo] = label.strip() or geo
        if row[col["SEX"]].split(":")[0] != "_T":
            continue
        citizen = row[col["CITIZEN"]].split(":")[0]
        out.setdefault(geo, {})[citizen] = float(row[col["OBS_VALUE"]] or 0)
    return labels, out


def partition(counts: dict[str, float], where: str) -> dict[str, float]:
    """Luxembourgers, other EU, non-EU, stateless and not stated, which must make
    the total, with EU and non-EU making the foreigners."""
    parts = {k: counts.get(k, 0.0) for k in LABELS}
    total = counts.get("_T")
    if total is None:
        raise SystemExit(f"luxembourg_nationality: {where} has no total")
    if abs(sum(parts.values()) - total) > 0.5:
        raise SystemExit(f"luxembourg_nationality: {where}: {parts} make {sum(parts.values()):,.0f}, "
                         f"the total is {total:,.0f}")
    if "FOR" in counts and abs(parts["EU_FOR"] + parts["NEU"] - counts["FOR"]) > 0.5:
        raise SystemExit(f"luxembourg_nationality: {where}: EU and non-EU foreigners make "
                         f"{parts['EU_FOR'] + parts['NEU']:,.0f}, the foreigners {counts['FOR']:,.0f}")
    return parts


def read_2011(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """{commune: {NAT, EU_FOR, NEU, STLS, UNK, _T}} from the 2011 table."""
    head = next(i for i, r in enumerate(rows) if "Belgique" in [text_of(c) for c in r])
    names = [text_of(c).replace("'", "’") for c in rows[head]]
    known = {"Luxembourg", "Apatrides", "Non indiqué", "Total", *EU27_2011, *NON_EU_2011}
    unknown = [n for n in names if n and n not in known]
    if unknown:
        raise SystemExit(f"luxembourg_nationality: 2011 columns this reader does not group: {unknown}")
    out: dict[str, dict[str, float]] = {}
    for r in rows[head + 1:]:
        if not r or not text_of(r[0]) or num(r[names.index("Total")]) is None:
            continue
        cell = {n: num(r[j]) or 0.0 for j, n in enumerate(names) if n}
        unit = {"NAT": cell["Luxembourg"], "EU_FOR": sum(cell.get(n, 0) for n in EU27_2011),
                "NEU": sum(cell.get(n, 0) for n in NON_EU_2011), "STLS": cell["Apatrides"],
                "UNK": cell["Non indiqué"], "_T": cell["Total"]}
        if abs(sum(v for k, v in unit.items() if k != "_T") - unit["_T"]) > 0.5:
            raise SystemExit(f"luxembourg_nationality: 2011 {text_of(r[0])}: the nationalities do "
                             f"not make the total")
        out[text_of(r[0])] = unit
    return out


NOTE = note("Population by citizenship", "8 November 2021",
            "the 2021 census's count of each resident's citizenship (STATEC, LUSTAT DF_B1625), "
            "which STATEC publishes by commune only in groups: Luxembourgers, citizens of the "
            "other EU-27 countries, of non-EU countries, the stateless and the not stated",
            extra="A Luxembourger with another citizenship too is counted as a Luxembourger.")


def build() -> list[dict[str, Any]]:
    log("luxembourg_nationality: RP 2021 by commune and citizenship (LUSTAT DF_B1625)")
    labels, table = read()
    national = partition(table["_T"], "Luxembourg") if "_T" in table else None
    cantons = sorted(g for g in table if g != "_T" and labels.get(g, "").startswith("Canton "))
    communes = sorted(g for g in table if g != "_T" and g not in cantons)
    log(f"  {len(communes)} communes, {len(cantons)} cantons")
    if len(communes) != 102 or len(cantons) != 12 or national is None:
        raise SystemExit(f"luxembourg_nationality: expected 102 communes, 12 cantons and the country")
    parts = {g: partition(table[g], labels[g]) for g in [*communes, *cantons]}
    check_sum((sum(parts[g].values()) for g in communes), sum(national.values()),
              "communes against Luxembourg")
    check_sum((sum(parts[g].values()) for g in cantons), sum(national.values()),
              "cantons against Luxembourg")

    def fields(unit: dict[str, float], where: str, text: str) -> dict[str, Any]:
        return {"ethnicity": composition(unit, sum(unit.values()), list(LABELS), LABELS, where=where),
                "ethnicity_year": YEAR, "ethnicity_basis": "nationality", "ethnicity_note": text}

    sources = [{"field": "ethnicity", "name": SOURCE, "url": PORTAL, "license": LICENCE, "year": YEAR}]
    records: list[dict[str, Any]] = []
    for level, geos in (("admin2", communes), ("admin1", cantons)):
        shapes = units("LUX", level)
        by_key: dict[str, list[dict[str, Any]]] = {}
        for shape in shapes:
            by_key.setdefault(fold(shape["name"]), []).append(shape)
        unbound, used = [], set()
        for geo in geos:
            name = labels[geo].replace(" - ", "-")
            if name in MERGED_SINCE_MAP:
                continue
            drawn = MAP_NAMES.get(name, name)
            keys = [fold(drawn)] if level == "admin2" else [fold("Canton " + drawn.replace("Canton ", "")),
                                                              fold(drawn)]
            hits = next((by_key[k] for k in keys if by_key.get(k)), [])
            if len(hits) != 1 or hits[0]["id"] in used:
                unbound.append(f"{name} ({geo})")
                continue
            used.add(hits[0]["id"])
            records.append(record(
                f"LUX-RP2021-{geo}-nat", hits[0]["name"], level=level,
                parent="LUX" if level == "admin1" else hits[0]["parent"], country="LUX",
                codes={"statec_geo": geo}, match_by="shape_id", shape_id=hits[0]["id"],
                sources=sources, **fields(parts[geo], name, NOTE)))
        left = [s for s in shapes if s["id"] not in used]
        expected = {n for ps in MERGED_SINCE_MAP.values() for n in ps} if level == "admin2" else set()
        if unbound or {s["name"] for s in left} != expected:
            raise SystemExit(f"luxembourg_nationality: {level} does not pair up: {unbound} / "
                             f"{[s['name'] for s in left]}")
        if level == "admin2":
            old = read_2011(book_rows(RP2011))
            total_2011 = old.pop("Total", None)
            if total_2011 is None:
                raise SystemExit("luxembourg_nationality: the 2011 table has no total row")
            check_sum((u["_T"] for u in old.values()), total_2011["_T"],
                      "2011 communes against Luxembourg")
            for shape in left:
                merged = next(m for m, ps in MERGED_SINCE_MAP.items() if shape["name"] in ps)
                name = OLD_NAMES.get(shape["name"], shape["name"])
                if name not in old:
                    raise SystemExit(f"luxembourg_nationality: the 2011 table has no {name}")
                unit = {k: v for k, v in old[name].items() if k != "_T"}
                text = note("Population of usual residence by nationality", "1 February 2011",
                            "the 2011 census's count by commune and nationality, grouped as the "
                            "2021 census groups it: Luxembourgers, the other EU-27 countries, the "
                            "rest (the United Kingdom included, and Croatia, which the 2011 table "
                            "does not name), the stateless and the not stated",
                            extra=(f"{shape['name']} merged into {merged} in 2018 and the 2021 "
                                   f"census counts {merged} as one commune; the map draws the "
                                   f"communes of 2015-2017, so this polygon takes the last count "
                                   f"of the commune itself."))
                records.append(record(
                    f"LUX-RP2011-{fold(shape['name'])}-nat", shape["name"], level="admin2",
                    parent=shape["parent"], country="LUX", codes={"statec_name": name},
                    match_by="shape_id", shape_id=shape["id"],
                    sources=[{"field": "ethnicity", "name": RP2011_SOURCE, "url": RP2011,
                              "license": LICENCE, "year": 2011}],
                    **{**fields(unit, name, text), "ethnicity_year": 2011}))
                log(f"  {shape['name']}: 2011 census, {old[name]['_T']:,.0f} people")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
