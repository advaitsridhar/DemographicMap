#!/usr/bin/env python3
"""Slovakia: nationality, mother tongue and religion by kraj and okres, from SODB 2021.

The Statistical Office publishes the 2021 census (Sčítanie obyvateľov, domov
a bytov 2021) on its own ArcGIS server, gis.scitanie.sk, as hosted feature
services -- the layers behind the census's map portal. Three are read, each
with one layer per kraj and one per okres that carries the question's answers
as columns (``cv_1``, ``cv_2``, ...; the column's alias is the answer's
Slovak name) beside the unit's population (``spolu``):

* ``obyv_ekchar_nar_vekskup``, layer AR4315 -- nationality (národnosť);
* ``obyv_ekchar_matjaz_vekskup``, layer AR4316 -- mother tongue;
* ``obyv_ekchar_nabo_vekskup``, layer AR4318 -- religion (náboženské vyznanie).

Each question takes one answer a person (the census also asked an optional
second nationality, which is not added here), and the office lists the
largest answers by name and the rest, including those who gave none, as
"ostatné". So each unit's columns partition its population, which is checked
for every kraj and okres, and "ostatné" is shown as "Other or not stated"
because that is what it holds.

These replace the Slovak Wikipedia transcriptions of the 2011 census
(``europe_wiki_slovakia.json``) wherever both exist, and the three questions
are filled everywhere, mother tongue for the first time.

The okresy are bound to the map's polygons by the declared names in
``slovakia.MAP_NAMES``, the kraje by their NUTS 3 codes.

Usage:
    python -m scripts.fetch_census.slovakia_census
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import PROCESSED, http_json, log, record, shares, write_json
from .central_ages import check_sum, fold, units
from .slovakia import REGIONS, bind_districts, district_name

BASE = "https://gis.scitanie.sk/server/rest/services/Hosted/"
PORTAL = "https://www.scitanie.sk/obyvatelia/rozsirene-vysledky"
SOURCE = "Statistical Office of the Slovak Republic, Census 2021 (SODB 2021), gis.scitanie.sk"
LICENCE = "Statistical Office of the SR open data (free reuse with attribution)"
OUT = PROCESSED / "slovakia_census.json"
YEAR = 2021
NATIONAL = 5_449_270              # SODB 2021, the whole population on 1 January 2021
SERVICES = {
    "ethnicity": ("obyv_ekchar_nar_vekskup", {"admin1": 3, "admin2": 5}),
    "language": ("obyv_ekchar_matjaz_vekskup", {"admin1": 3, "admin2": 5}),
    "religion": ("obyv_ekchar_nabo_vekskup", {"admin1": 3, "admin2": 5}),
}
OTHER = "Other or not stated"
LABELS = {
    "ethnicity": {
        "slovenská": "Slovak", "maďarská": "Hungarian", "rómska": "Romani", "rusínska": "Rusyn",
        "česká": "Czech", "ukrajinská": "Ukrainian", "nemecká": "German", "moravská": "Moravian",
        "poľská": "Polish", "ruská": "Russian", "bulharská": "Bulgarian", "chorvátska": "Croatian",
        "srbská": "Serbian", "židovská": "Jewish", "ostatné": OTHER,
    },
    "language": {
        "slovenský": "Slovak", "maďarský": "Hungarian", "rómsky": "Romani", "rusínsky": "Rusyn",
        "český": "Czech", "ukrajinský": "Ukrainian", "nemecký": "German", "poľský": "Polish",
        "ruský": "Russian", "anglický": "English", "chorvátsky": "Croatian", "srbský": "Serbian",
        "bulharský": "Bulgarian", "ostatné": OTHER,
    },
    # Religion aliases are long church names; the start of each is enough.
    "religion": {
        "bez náboženského vyznania": "No religion",
        "rímskokatolícka cirkev": "Roman Catholic",
        "evanjelická cirkev augsburského vyznania": "Lutheran",
        "gréckokatolícka cirkev": "Greek Catholic",
        "reformovaná kresťanská cirkev": "Reformed",
        "pravoslávna cirkev": "Orthodox",
        "kresťanské zbory": "Other Christian",
        "náboženská spoločnosť jehovovi svedkovia": "Jehovah's Witnesses",
        "svedkovia jehovovi": "Jehovah's Witnesses",
        "evanjelická cirkev metodistická": "Other Christian",
        "apoštolská cirkev": "Other Christian",
        "bratská jednota baptistov": "Other Christian",
        "cirkev bratská": "Other Christian",
        "cirkev adventistov siedmeho dňa": "Seventh-day Adventist",
        "cirkev ježiša krista svätých neskorších dní": "Latter-day Saints",
        "novoapoštolská cirkev": "Other Christian",
        "starokatolícka cirkev": "Old Catholic",
        "ústredný zväz židovských náboženských obcí": "Judaism",
        "islam": "Islam", "budhizmus": "Buddhism",
        "ostatné": OTHER,
    },
}
NOTES = {
    "ethnicity": ("Nationality (národnosť), SODB 2021: one answer per person, the whole "
                  "population on 1 January 2021. The optional second nationality is not added. "
                  "The office names the largest nationalities; the rest, and those who stated "
                  "none, are 'Other or not stated'."),
    "language": ("Mother tongue, SODB 2021: one answer per person, the whole population. The "
                 "office names the largest languages; the rest, and those who stated none, are "
                 "'Other or not stated'."),
    "religion": ("Religious affiliation, SODB 2021: one answer per person, the whole "
                 "population. The office names the largest churches; the rest, and those who "
                 "stated none, are 'Other or not stated'."),
}


def english(field: str, alias: str) -> str | None:
    alias = alias.strip().lower()
    for start, label in LABELS[field].items():
        if alias.startswith(start):
            return label
    return None


def layer(field: str, level: str) -> dict[str, dict[str, Any]]:
    """{unit code: {"name", "total", "counts": {label: n}}} for one question at one level."""
    service, layers = SERVICES[field]
    url = f"{BASE}{service}/FeatureServer/{layers[level]}"
    info = http_json(f"{url}?f=json", timeout=120)
    columns: dict[str, str] = {}
    unknown = []
    for f in info.get("fields", []):
        name, alias = f["name"], f.get("alias") or ""
        if name.startswith("cv_") and not name.endswith("p"):
            label = english(field, alias)
            if label is None:
                unknown.append(f"{name}={alias}")
            else:
                columns[name] = label
    if unknown:
        raise SystemExit(f"slovakia_census: {service}/{layers[level]}: answers with no English "
                         f"name here: {unknown}")
    rows = http_json(f"{url}/query?where=1%3D1&outFields=*&returnGeometry=false&f=json",
                     timeout=120).get("features", [])
    out = {}
    for feature in rows:
        a = feature["attributes"]
        counts: dict[str, float] = {}
        for column, label in columns.items():
            counts[label] = counts.get(label, 0) + (a.get(column) or 0)
        total = a["spolu"]
        if abs(sum(counts.values()) - total) > 0.5:
            raise SystemExit(f"slovakia_census: {field} {a.get('nazov')}: the answers make "
                             f"{sum(counts.values()):,.0f}, the population is {total:,.0f}")
        out[a["uzemie"]] = {"name": a.get("nazov") or a["uzemie"], "total": total, "counts": counts}
    log(f"  {field} {level}: {len(out)} units, {len(columns)} answers named")
    return out


def build() -> list[dict[str, Any]]:
    log("slovakia_census: SODB 2021 feature services on gis.scitanie.sk")
    tables = {(field, level): layer(field, level) for field in SERVICES
              for level in ("admin1", "admin2")}
    for field in SERVICES:
        kraje, okresy = tables[(field, "admin1")], tables[(field, "admin2")]
        check_sum((u["total"] for u in kraje.values()), NATIONAL, f"{field}: kraje against Slovakia")
        for code, kraj in kraje.items():
            check_sum((u["total"] for c, u in okresy.items() if c.startswith(code)),
                      kraj["total"], f"{field}: okresy against {kraj['name']}")
    okresy = tables[("religion", "admin2")]
    bound = bind_districts({c: district_name(u["name"]) for c, u in okresy.items()})
    firsts = {fold(u["name"]): u for u in units("SVK", "admin1")}
    records = []
    sources = [{"field": "ethnicity/language/religion", "name": SOURCE, "url": PORTAL,
                "license": LICENCE, "year": YEAR}]
    for level in ("admin1", "admin2"):
        for code in sorted(tables[("religion", level)]):
            fields: dict[str, Any] = {}
            for field in SERVICES:
                unit = tables[(field, level)].get(code)
                if unit is None:
                    raise SystemExit(f"slovakia_census: {code} is missing from the {field} layer")
                fields[field] = shares({k: v for k, v in unit["counts"].items() if v},
                                       total=unit["total"])
                fields[f"{field}_year"] = YEAR
                fields[f"{field}_note"] = NOTES[field]
            name = tables[("religion", level)][code]["name"]
            if level == "admin1":
                shape = firsts.get(fold(REGIONS.get(code, "")))
                if shape is None:
                    raise SystemExit(f"slovakia_census: kraj {code} {name} has no polygon")
                parent = "SVK"
            else:
                shape = bound[code]
                parent = shape["parent"]
            records.append(record(
                f"SVK-SODB-{code}", name if level == "admin2" else shape["name"], level=level,
                parent=parent, country="SVK", codes={"nuts": code},
                aliases=[shape["name"]] if shape["name"] != name else [],
                match_by="shape_id", shape_id=shape["id"], sources=sources, **fields))
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
