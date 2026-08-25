#!/usr/bin/env python3
"""Join boundaries and demographics into the per-entity records the app loads.

Inputs
------
* ``data/raw/boundaries/geoBoundariesCGAZ_ADM{0,1,2}.gpkg``  geometry + shapeIDs
* ``data/processed/admin0.json``                             Factbook country records
* ``data/processed/cities.json``                             Natural Earth largest cities
* ``data/curated/admin1_seed.json``                          hand-checked census rows
* ``data/processed/{us_*,uk_*,canada_*,brazil_*,eurostat_*,australia_*,india_*}.json``
  and ``wikidata_admin{1,2}.json`` -- whichever adapters have been run

Outputs
-------
* ``site/data/admin0.json``           every country, loaded up front (small)
* ``site/data/admin1/{ISO3}.json``    lazy-loaded on country selection
* ``site/data/admin2/{ISO3}.json``    lazy-loaded on admin-1 selection
* ``site/data/search-index.json``     flat id/name/level/parent rows for MiniSearch
* ``site/data/coverage.json``         per-country, per-field availability matrix

The join key is geoBoundaries' ``shapeID``; statistical sources are matched to it
by normalised name within a country, because no agency publishes shapeIDs.  Every
match records *how* it matched so a bad join is auditable rather than invisible.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canonical_groups
from common import (  # noqa: E402
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, ROOT, apply_collection_policy,
    gap, is_gap, log, measure, read_json, repair, write_json,
)

SITE_DATA = ROOT / "site" / "data"
BOUNDARIES = RAW / "boundaries"

# Adapter outputs, in increasing order of authority: later files win.
ADAPTER_FILES = [
    "wikidata_admin1.json", "wikidata_admin2.json",
    "eurostat_nuts2.json", "eurostat_nuts3.json",
    "india_state.json", "india_district.json",
    # After the C-01 files: mother tongue is the one field these add, and a
    # later file never overwrites an earlier real value with a gap marker.
    "india_language_state.json", "india_language_district.json",
    "mexico_state.json", "mexico_municipality.json",
    "nepal_province.json", "nepal_district.json",
    "nz_region.json", "nz_territorial.json",
    "switzerland_canton.json",
    "singapore_region.json", "singapore_planning_area.json",
    "srilanka_province.json", "srilanka_district.json",
    "brazil_state.json", "brazil_municipality.json",
    "canada_province.json", "canada_census_division.json",
    "australia_state.json", "australia_lga.json",
    "uk_lad.json", "us_state.json", "us_county.json",
]

# Where a real adapter exists for a country's subnational demographics. Shown in
# the UI on units that have no values yet, so an empty panel says *which* command
# would fill it rather than just "no data".
ADAPTER_HINTS: dict[str, str] = {
    "USA": "US Census ACS (race, language, age) plus the 2020 U.S. Religion Census: "
           "python -m scripts.fetch_census.us_acs --level county",
    "GBR": "ONS Census 2021 via Nomis (TS021 ethnic group, TS030 religion): "
           "python -m scripts.fetch_census.uk_nomis",
    "CAN": "Statistics Canada 2021 Census Profile (religion, visible minority, language): "
           "python -m scripts.fetch_census.statcan --level census_division",
    "BRA": "IBGE SIDRA 2022 census (population, cor ou raça, religion): "
           "python -m scripts.fetch_census.ibge_sidra --level municipality",
    "AUS": "ABS 2021 Census (religion, ancestry): "
           "python -m scripts.fetch_census.abs --level lga",
    "MEX": "INEGI Censo 2020 ITER (religion, indigenous language, Afro-descendant): "
           "python -m scripts.fetch_census.mexico --level both",
    "NZL": "Stats NZ 2023 Census via Aotearoa Data Explorer (ethnicity, "
           "languages spoken, religious affiliation; needs an API key): "
           "python -m scripts.fetch_census.new_zealand",
    "NPL": "NPHC 2021 report (caste/ethnicity, mother tongue, religion): "
           "python -m scripts.fetch_census.nepal --url <report PDF>",
    "CHE": "FSO structural survey, main languages by canton: "
           "python -m scripts.fetch_census.switzerland",
    "SGP": "SingStat table M810771 (residents by planning region, age, sex): "
           "python -m scripts.fetch_census.singstat",
    "LKA": "Sri Lanka Census 2024 tables A1-A3 (population, ethnicity, religion): "
           "python -m scripts.fetch_census.sri_lanka --level district",
    "IND": "Census of India 2011 tables C-01 (religion) and C-16 (mother tongue): "
           "python -m scripts.fetch_census.india_census --level district && "
           "python -m scripts.fetch_census.india_language --level district",
}
EUROSTAT_HINT = ("Eurostat NUTS population and median age: "
                 "python -m scripts.fetch_census.eurostat --level nuts3")
EUROSTAT_COUNTRIES = {
    "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU",
    "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT",
    "ROU", "SVK", "SVN", "ESP", "SWE", "NOR", "CHE", "ISL", "SRB", "MKD", "TUR",
}
WIKIDATA_HINT = ("Wikidata population, capital and coordinates for every country: "
                 "python scripts/fetch_wikidata.py --level admin2 --countries {iso3}")


def adapter_hint(iso3: str) -> str:
    if iso3 in ADAPTER_HINTS:
        return ADAPTER_HINTS[iso3]
    if iso3 in EUROSTAT_COUNTRIES:
        return EUROSTAT_HINT
    return WIKIDATA_HINT.format(iso3=iso3)


# Fields the coverage matrix reports on.
TRACKED = ("population", "capital", "largest_settlement", "median_age",
           "sex_ratio", "religion", "language", "ethnicity")


def is_disputed(group: str | None) -> bool:
    """geoBoundaries files disputed and special-status areas under numeric groups.

    They appear at all three levels (Abyei is both an ADM0 and an ADM1 shape), so
    the test lives here rather than being repeated per level.
    """
    return bool(group) and group.isdigit()


def norm(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\b(province|state|region|district|county|prefecture|governorate|"
                  r"oblast|department|municipality|city|autonomous|territory|of|the|and)\b",
                  " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


# ---------------------------------------------------------------------------
# Geometry side
# ---------------------------------------------------------------------------

def read_shapes(level: str) -> list[dict[str, Any]]:
    """Feature properties + centroid for one CGAZ level (geometry stays on disk)."""
    import fiona
    from shapely.geometry import shape

    path = BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg"
    if not path.exists():
        # Fatal, not a warning. The boundary files are the only source of
        # shapes, and they are too large to commit, so a checkout that has not
        # run fetch_boundaries.py has none. Carrying on regardless once wrote a
        # 9 kB search index over 218 countries and no divisions, a groups index
        # missing every subnational group, and a coverage matrix that reported
        # nothing below the national level -- all of it committed and deployed,
        # because every per-country shard was left untouched and only the
        # aggregates looked "rebuilt".
        raise SystemExit(
            f"missing {path}\n"
            "The CGAZ boundary files are not in git (they are ~550 MB).\n"
            "Run: python3 scripts/fetch_boundaries.py --cgaz")
    out: list[dict[str, Any]] = []
    with fiona.open(path) as src:
        for feat in src:
            props = dict(feat["properties"])
            geom = shape(feat["geometry"]) if feat["geometry"] else None
            if geom is None or geom.is_empty:
                continue
            point = geom.representative_point()
            bounds = geom.bounds
            out.append({
                "shape_id": props.get("shapeID") or props.get("shapeGroup"),
                "name": repair((props.get("shapeName") or "").strip()),
                "group": props.get("shapeGroup"),
                "point": [round(point.x, 5), round(point.y, 5)],
                "bbox": [round(b, 4) for b in bounds],
                "_geom": geom if level != "ADM2" else None,
                "area": geom.area,
            })
    log(f"  {level}: {len(out)} shapes")
    return out


def link_adm2_parents(adm1: list[dict[str, Any]], adm2: list[dict[str, Any]]) -> None:
    """CGAZ ADM2 carries no parent link, so assign it by point-in-polygon."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adm1:
        by_country[row["group"]].append(row)

    trees: dict[str, tuple[STRtree, list[dict[str, Any]]]] = {}
    for iso3, rows in by_country.items():
        geoms = [r["_geom"] for r in rows if r["_geom"] is not None]
        kept = [r for r in rows if r["_geom"] is not None]
        if geoms:
            trees[iso3] = (STRtree(geoms), kept)

    matched = 0
    for row in adm2:
        entry = trees.get(row["group"])
        row["parent_shape"] = None
        if not entry:
            continue
        tree, rows = entry
        point = Point(row["point"])
        hits = tree.query(point)
        parent = None
        for idx in hits:
            candidate = rows[int(idx)]
            if candidate["_geom"].contains(point):
                parent = candidate
                break
        if parent is None and len(rows) == 1:
            parent = rows[0]
        if parent is None and len(hits):
            parent = rows[int(hits[0])]
        if parent is not None:
            row["parent_shape"] = parent["shape_id"]
            matched += 1
    log(f"  ADM2 -> ADM1 parent assigned for {matched}/{len(adm2)} units")


# ---------------------------------------------------------------------------
# Attribute side
# ---------------------------------------------------------------------------

def load_adapters() -> dict[str, list[dict[str, Any]]]:
    """Every adapter record, bucketed by country, in authority order."""
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for filename in ADAPTER_FILES:
        path = PROCESSED / filename
        rows = read_json(path, None)
        if not rows:
            continue
        log(f"  adapter {filename}: {len(rows)} records")
        for row in rows:
            iso3 = (row.get("country") or (row.get("id") or "")[:3]).upper()
            by_country[iso3].append(row)
    return by_country


def load_curated() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    payload = read_json(ROOT / "data" / "curated" / "admin1_seed.json", {})
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("rows", []):
        rows[row["country"]].append(row)
    return rows, payload.get("_provenance", {})


def apply_curated(entity: dict[str, Any], row: dict[str, Any], prov: dict[str, Any]) -> None:
    source = prov.get("source")
    year = prov.get("year")
    if row.get("population"):
        entity["population"] = measure(row["population"], year=year, source=source)
    if row.get("capital"):
        entity["capital"] = row["capital"]
    if row.get("largest_settlement"):
        entity["largest_settlement"] = row["largest_settlement"]
    if row.get("sex_ratio_f_per_1000_m"):
        entity["sex_ratio"] = measure(row["sex_ratio_f_per_1000_m"],
                                      unit="females_per_1000_males", year=year, source=source)
    for field in ("religion", "ethnicity", "language"):
        if row.get(field):
            entity[field] = row[field]
            if prov.get("note"):
                entity[f"{field}_note"] = prov["note"]
    for field in ("religion", "ethnicity"):
        policy = prov.get(f"{field}_policy")
        if policy and is_gap(entity.get(field)):
            entity[field] = gap(NOT_COLLECTED, policy)
    entity.setdefault("sources", []).append(
        {"field": "curated", "name": source, "year": year,
         "note": prov.get("note"), "license": "See docs/SOURCES.md"})


def merge_adapter(entity: dict[str, Any], row: dict[str, Any]) -> None:
    """Adapter values override seeds; gap markers never overwrite real values."""
    for key, value in row.items():
        if key in {"id", "level", "name", "parent", "parent_name", "parent_aliases"}:
            continue
        if key == "sources":
            entity.setdefault("sources", []).extend(value or [])
            continue
        if is_gap(value) and not is_gap(entity.get(key)):
            continue
        entity[key] = value


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def match_name(row: dict[str, Any], lookup: dict[str, dict[str, Any]]
               ) -> tuple[dict[str, Any] | None, str]:
    """Exact normalised name, then declared aliases, then a *unique* prefix match.

    The prefix pass is what bridges "Tibet" to CGAZ's "Tibet Autonomous Region";
    it refuses to guess when more than one shape would match.
    """
    for candidate in [row["name"], *row.get("aliases", [])]:
        key = norm(candidate)
        if key in lookup:
            return lookup[key], "name" if candidate == row["name"] else "alias"
    for candidate in [row["name"], *row.get("aliases", [])]:
        key = norm(candidate)
        if not key:
            continue
        hits = [v for k, v in lookup.items() if k.startswith(key) or key.startswith(k)]
        if len(hits) == 1:
            return hits[0], "prefix"
    # Last pass: unique substring containment. This is what bridges a source's
    # long official form to the boundary file's short one -- Wikidata's
    # "Canton of Zurich" to CGAZ's "Zurich", "Stockholms lan" to "Stockholm",
    # "Emirate of Sharjah" to "Sharjah". Both strings must be substantial and
    # exactly one shape may qualify, otherwise refuse rather than guess.
    for candidate in [row["name"], *row.get("aliases", [])]:
        key = norm(candidate)
        if len(key) < 4:
            continue
        hits = [v for k, v in lookup.items()
                if len(k) >= 4 and (key in k or k in key)]
        if len(hits) == 1:
            return hits[0], "contains"
    return None, "unmatched"


def scoped_by_parent(by_name: dict[str, list[dict[str, Any]]], parent_id: str
                     ) -> dict[str, dict[str, Any]]:
    """The shapes inside one admin-1, keyed by name, dropping any still ambiguous."""
    out = {}
    for key, entities in by_name.items():
        inside = [e for e in entities if e.get("parent") == parent_id]
        if len(inside) == 1:
            out[key] = inside[0]
    return out


def match_admin2(row: dict[str, Any], by_name: dict[str, list[dict[str, Any]]],
                 admin1: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """Resolve an adapter row to one admin-2 shape, using its state when it has one.

    District names repeat across states. India has a Hamirpur in Himachal Pradesh
    and another in Uttar Pradesh, a Pratapgarh in Rajasthan and another in Uttar
    Pradesh, an Aurangabad in Maharashtra and another in Bihar. A lookup keyed on
    name alone keeps whichever shape it saw last, which makes one district
    unreachable and lets the other quietly wear its twin's figures -- a wrong
    answer that looks exactly like a right one.

    So a row that names its parent state is matched only inside that state. A row
    that does not is matched only against names that are unique country-wide;
    where the name is ambiguous the row is refused, on the same principle the
    prefix and containment passes already follow -- an unmatched row is a visible
    gap, a mis-matched one is invisible.
    """
    parent_name = row.get("parent_name")
    if parent_name:
        # The parent name is matched with aliases too, because boundary files
        # and statistical agencies disagree about renamings: CGAZ still calls
        # Mexico City "Distrito Federal", a name it lost in 2016, so without an
        # alias none of its sixteen alcaldias can be scoped to it and the ones
        # sharing a name with a municipio elsewhere -- Benito Juarez, also in
        # Quintana Roo; Cuauhtemoc, also in Chihuahua and Colima -- are refused
        # as ambiguous.
        parent, _ = match_name({"name": parent_name,
                                "aliases": row.get("parent_aliases") or []}, admin1)
        if parent is not None:
            entity, how = match_name(row, scoped_by_parent(by_name, parent["id"]))
            if entity is not None:
                return entity, f"{how}+state"

    unique = {key: entities[0] for key, entities in by_name.items() if len(entities) == 1}
    entity, how = match_name(row, unique)
    if entity is not None:
        return entity, how
    if norm(row.get("name") or "") in by_name:
        return None, "ambiguous"
    return None, "unmatched"


DISPUTED_NOTE = ("Disputed or special-status territory as delimited by geoBoundaries "
                 "CGAZ, which follows US Department of State definitions. Shown for "
                 "completeness; no sovereignty claim is implied and no demographic "
                 "source is joined to it.")


def mark_disputed_or_hint(entity: dict[str, Any], group: str) -> None:
    """Either flag the unit as disputed, or tell the UI which adapter would fill it.

    A disputed polygon gets no adapter hint: no statistical agency publishes
    demographics for it, so pointing at one would be a false promise.
    """
    if is_disputed(group):
        entity["disputed"] = True
        entity["note"] = DISPUTED_NOTE
    else:
        entity["adapter_hint"] = adapter_hint(group)


def blank(shape: dict[str, Any], level: str, parent: str | None) -> dict[str, Any]:
    return {
        "id": shape["shape_id"],
        "level": level,
        "name": shape["name"] or shape["shape_id"],
        "parent": parent,
        "country": shape["group"],
        "point": shape["point"],
        "bbox": shape["bbox"],
        "capital": gap(NOT_AVAILABLE),
        "largest_settlement": gap(NOT_AVAILABLE),
        "population": gap(NOT_AVAILABLE),
        "median_age": gap(NOT_AVAILABLE),
        "sex_ratio": gap(NOT_AVAILABLE),
        "religion": gap(NOT_AVAILABLE),
        "language": gap(NOT_AVAILABLE),
        "ethnicity": gap(NOT_AVAILABLE),
        "sources": [],
    }


def field_state(value: Any) -> str:
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, dict) and value.get("status"):
        return value["status"]
    if isinstance(value, list) and not value:
        return NOT_AVAILABLE
    return "present"


def group_index(admin0: list[dict[str, Any]],
                admin1: dict[str, list[dict[str, Any]]],
                admin2: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """What can be filtered on worldwide, and what each choice actually covers.

    The app cannot build this from the records it happens to have loaded: at
    world zoom it holds countries only, so a group picker fed from those would
    offer nothing below the national level, and one fed from a single country's
    shard would offer only that country's spellings. The whole point of a global
    filter is to know that "Muslim" and "Islam" are one answer before the map is
    drawn, so the list is assembled here, over every record, once.

    Each entry carries what it is fair to conclude from it: how many units hold
    a figure, which countries those are, the source labels folded into it, and
    any country measuring it a different way -- the US religion figures count
    adherents reported by religious bodies rather than answers people gave, so a
    map of Christianity shades those counties on a basis the others do not share.
    """
    index: dict[str, Any] = {}
    levels = [("admin0", [("", admin0)]),
              ("admin1", sorted(admin1.items())),
              ("admin2", sorted(admin2.items()))]
    for field in ("religion", "language", "ethnicity"):
        units: dict[str, int] = {}
        countries: dict[str, set[str]] = {}
        labels: dict[str, set[str]] = {}
        bases: dict[str, str] = {}
        conflicts: set[str] = set()
        # Counted per level as well as overall. A group reported by 122
        # countries nationally may exist for only two of them at district
        # level, and a map pinned to districts that claims 122 is telling the
        # reader the opposite of what it is showing.
        per_level: dict[str, dict[str, dict[str, Any]]] = {
            name: {} for name, _ in levels}

        for level_name, sources in levels:
          for iso3, rows in sources:
            for record in rows:
                value = record.get(field)
                if not isinstance(value, list):
                    continue
                code = iso3 or record.get("id", "")
                for bad in canonical_groups.check_no_double_counting(value, field):
                    conflicts.add(f"{code}:{bad}")
                basis = record.get(f"{field}_basis")
                if basis:
                    bases[code] = basis
                table = canonical_groups.lookup(field)
                for row in value:
                    if not isinstance(row.get("pct"), (int, float)):
                        continue
                    raw = row.get("group", "")
                    name = table.get(canonical_groups.key(raw), raw)
                    units[name] = units.get(name, 0) + 1
                    countries.setdefault(name, set()).add(code)
                    labels.setdefault(name, set()).add(raw)
                    at = per_level[level_name].setdefault(
                        name, {"units": 0, "countries": set()})
                    at["units"] += 1
                    at["countries"].add(code)

        if conflicts:
            # Rolling children into a parent is only sound while no source
            # publishes both levels at once. If one starts to, the totals would
            # silently double, so the build stops rather than shipping them.
            raise SystemExit(f"{field}: parent and child reported together in "
                             f"{sorted(conflicts)[:5]}")

        index[field] = {
            "groups": [
                {"name": name,
                 "units": units[name],
                 "countries": sorted(c for c in countries[name] if len(c) == 3),
                 "labels": sorted(labels[name]),
                 "canonical": len(labels[name]) > 1 or name in canonical_groups.TABLES[field],
                 "levels": {
                     level_name: {
                         "units": per_level[level_name][name]["units"],
                         "countries": sorted(
                             c for c in per_level[level_name][name]["countries"]
                             if len(c) == 3),
                     }
                     for level_name, _ in levels if name in per_level[level_name]
                 }}
                for name in sorted(units, key=lambda n: (-units[n], n))
            ],
            "bases": bases,
        }
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", nargs="*", default=["ADM0", "ADM1", "ADM2"])
    ap.add_argument("--out", type=Path, default=SITE_DATA)
    args = ap.parse_args()

    log("build_entities: reading boundaries")
    shapes = {level: read_shapes(level) for level in args.levels}
    if "ADM1" in shapes and "ADM2" in shapes:
        link_adm2_parents(shapes["ADM1"], shapes["ADM2"])

    log("build_entities: reading attributes")
    # Several Factbook entities can share one ISO3 (Australia and the Coral Sea
    # Islands are both AUS; France and Clipperton are both FRA). fetch_factbook
    # gives the primary entity the bare code and suffixes the rest, so prefer the
    # record whose id *is* the code -- otherwise a dependency overwrites its
    # parent and the country panel shows the wrong place.
    countries: dict[str, dict[str, Any]] = {}
    for row in read_json(PROCESSED / "admin0.json", []):
        iso3 = (row.get("codes") or {}).get("iso3")
        if not iso3:
            continue
        if row["id"] == iso3 or iso3 not in countries:
            countries[iso3] = row
    cities = read_json(PROCESSED / "cities.json", {"by_country": {}, "by_admin1": {}})
    adapters = load_adapters()
    curated_rows, provenance = load_curated()

    # -- admin 0 -------------------------------------------------------------
    admin0: list[dict[str, Any]] = []
    matched_iso3: set[str] = set()
    for shape in shapes.get("ADM0", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin0", None)
        entity["id"] = iso3
        if is_disputed(iso3):
            # geoBoundaries carries disputed and special-status areas under
            # numeric group codes (Abyei, Aksai Chin, the Senkakus, Gaza, the
            # West Bank). They are real polygons but not countries, so they get
            # their own id space and are labelled rather than silently counted
            # as states.
            # The id stays the raw shapeGroup so it still matches the tile's
            # promoted feature id; the flag is what the UI keys off.
            entity["disputed"] = True
            entity["note"] = DISPUTED_NOTE
            admin0.append(entity)
            continue
        matched_iso3.add(iso3)
        source = countries.get(iso3)
        if source:
            for key, value in source.items():
                if key in {"id", "level", "parent"}:
                    continue
                if key == "sources":
                    entity["sources"].extend(value)
                elif key == "name":
                    entity["name"] = value
                else:
                    entity[key] = value
        else:
            entity["data_status"] = "no Factbook profile matched this ISO3 code"
        city = cities["by_country"].get(iso3)
        if city and is_gap(entity.get("largest_settlement")):
            entity["largest_settlement"] = city["name"]
            entity["largest_settlement_population"] = measure(
                city["population"], source=city["source"])
        admin0.append(entity)

    # Factbook entities with no CGAZ polygon -- dependencies and territories that
    # geoBoundaries folds into their administering state (Hong Kong, Macau,
    # Puerto Rico, Palestine, the Channel Islands...). Keeping them as
    # geometry-less records means they are still searchable and still show their
    # demographics, with the missing outline stated rather than implied.
    for iso3, source in sorted(countries.items()):
        if iso3 in matched_iso3:
            continue
        entity = dict(source)
        entity["id"] = iso3
        entity["level"] = "admin0"
        entity["parent"] = None
        entity["country"] = iso3
        entity["geometry_available"] = False
        entity["point"] = source.get("capital_coordinates")
        entity["bbox"] = None
        entity["note"] = ("geoBoundaries' global composite has no separate outline for "
                          "this entity -- it is drawn as part of the state that "
                          "administers it. The figures below are still its own.")
        entity.setdefault("sources", [])
        admin0.append(entity)

    admin0.sort(key=lambda e: e["name"])

    # -- admin 1 -------------------------------------------------------------
    admin1_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    adm1_index: dict[str, dict[str, str]] = defaultdict(dict)
    for shape in shapes.get("ADM1", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin1", iso3)
        city = cities["by_admin1"].get(f"{iso3}||{norm_city(shape['name'])}")
        if city:
            entity["largest_settlement"] = city["name"]
            entity["largest_settlement_population"] = measure(city["population"], source=city["source"])
        mark_disputed_or_hint(entity, iso3)
        admin1_by_country[iso3].append(entity)
        adm1_index[iso3][norm(shape["name"])] = entity["id"]

    for iso3, rows in curated_rows.items():
        prov = provenance.get(iso3, {})
        lookup = {norm(e["name"]): e for e in admin1_by_country.get(iso3, [])}
        for row in rows:
            entity, how = match_name(row, lookup)
            if entity is None:
                log(f"  curated row unmatched: {iso3} / {row['name']}")
                continue
            apply_curated(entity, row, prov)
            entity["match"] = f"curated:{how}"

    # -- admin 2 -------------------------------------------------------------
    admin2_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in shapes.get("ADM2", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin2", shape.get("parent_shape") or iso3)
        mark_disputed_or_hint(entity, iso3)
        admin2_by_country[iso3].append(entity)

    # -- adapters override both levels --------------------------------------
    for iso3, rows in adapters.items():
        a1 = {norm(e["name"]): e for e in admin1_by_country.get(iso3, [])}
        a2: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            a2[norm(entity["name"])].append(entity)
        hit = miss = ambiguous = 0
        for row in rows:
            # Aliases travel with the key. They were being dropped here, which
            # made every alias an adapter declared for an admin-2 row or its
            # parent dead weight -- the matcher never saw them.
            key = {"name": row.get("name") or "",
                   "aliases": row.get("aliases") or [],
                   "parent_name": row.get("parent_name"),
                   "parent_aliases": row.get("parent_aliases") or []}
            if row.get("level") == "admin1":
                entity, how = match_name(key, a1)
            else:
                entity, how = match_admin2(key, a2, a1)
            if entity is None:
                miss += 1
                ambiguous += how == "ambiguous"
                continue
            merge_adapter(entity, row)
            entity["match"] = f"adapter:{how}"
            hit += 1
        if rows:
            extra = f" ({ambiguous} ambiguous)" if ambiguous else ""
            log(f"  {iso3}: adapter rows matched {hit}, unmatched {miss}{extra}")

    # -- collection policy ---------------------------------------------------
    # Last, so an adapter's real value always wins over the national marker.
    policy_hits: dict[str, int] = defaultdict(int)
    for table in (admin1_by_country, admin2_by_country):
        for iso3, rows in table.items():
            for entity in rows:
                for field in apply_collection_policy(entity, iso3):
                    policy_hits[f"{iso3}/{field}"] += 1
    if policy_hits:
        total = sum(policy_hits.values())
        top = sorted(policy_hits.items(), key=lambda kv: -kv[1])[:8]
        log(f"  collection policy marked {total} subnational fields as not_collected: "
            + ", ".join(f"{k} {v}" for k, v in top))

    # -- write ---------------------------------------------------------------
    out = args.out
    write_json(out / "admin0.json", admin0, compact=True)
    for iso3, rows in sorted(admin1_by_country.items()):
        rows.sort(key=lambda e: e["name"])
        write_json(out / "admin1" / f"{iso3}.json", rows, compact=True)
    for iso3, rows in sorted(admin2_by_country.items()):
        rows.sort(key=lambda e: e["name"])
        write_json(out / "admin2" / f"{iso3}.json", rows, compact=True)

    # Search index, sharded so the first paint does not wait on 49k admin-2 rows:
    # shard 0 (countries + admin-1) loads with the page, shard 2 (admin-2) is
    # fetched in the background and merged when it lands.  Rows are positional
    # arrays -- [id, name, level, country, bbox] -- which is ~40% smaller than
    # the equivalent objects over 52k entities.
    admin1_names = {e["id"]: e["name"]
                    for rows in admin1_by_country.values() for e in rows}

    def row(entity: dict[str, Any], level: int, country: str) -> list[Any]:
        bbox = entity.get("bbox")
        # The parent's name is what separates Harris County, Texas from Harris
        # County, Georgia in the result list.
        parent = admin1_names.get(entity.get("parent") or "") or ""
        return [entity["id"], entity["name"], level, country,
                [round(v, 3) for v in bbox] if bbox else None, parent]

    shard0: list[list[Any]] = [row(e, 0, e["id"]) for e in admin0]
    for iso3, rows in admin1_by_country.items():
        shard0.extend(row(e, 1, iso3) for e in rows)
    shard2: list[list[Any]] = []
    for iso3, rows in admin2_by_country.items():
        shard2.extend(row(e, 2, iso3) for e in rows)

    fields = ["id", "name", "level", "country", "bbox", "parentName"]
    write_json(out / "search-index-0.json", {"fields": fields, "rows": shard0}, compact=True)
    write_json(out / "search-index-2.json", {"fields": fields, "rows": shard2}, compact=True)
    index = shard0 + shard2

    # Coverage matrix: what exists, what is missing, what is never collected.
    coverage: dict[str, Any] = {}
    for entity in admin0:
        if entity.get("disputed"):
            continue
        iso3 = entity["id"]
        entry: dict[str, Any] = {"name": entity["name"], "admin0": {}, "admin1": {}, "admin2": {}}
        for field in TRACKED:
            entry["admin0"][field] = field_state(entity.get(field))
        for level, table in (("admin1", admin1_by_country), ("admin2", admin2_by_country)):
            rows = table.get(iso3, [])
            entry[level]["count"] = len(rows)
            for field in TRACKED:
                states = [field_state(r.get(field)) for r in rows]
                entry[level][field] = {
                    "present": sum(1 for s in states if s == "present"),
                    "not_collected": sum(1 for s in states if s == NOT_COLLECTED),
                    "not_available": sum(1 for s in states if s == NOT_AVAILABLE),
                }
        coverage[iso3] = entry
    write_json(out / "coverage.json", coverage, compact=True)

    write_json(out / "groups.json", group_index(admin0, admin1_by_country,
                                                admin2_by_country), compact=True)

    # A stamp derived from what was actually written, so the app can bust a
    # viewer's cached shards the moment the figures change -- and only then.
    # Content, not a timestamp: an unchanged rebuild must not invalidate
    # everyone's cache, and a changed one must.
    digest = hashlib.sha256()
    for path in sorted(out.rglob("*.json")):
        if path.name != "build.json":
            digest.update(path.read_bytes())
    write_json(out / "build.json", {"version": digest.hexdigest()[:12]}, compact=True)

    log(f"  admin0 {len(admin0)} | admin1 {sum(len(v) for v in admin1_by_country.values())} "
        f"| admin2 {sum(len(v) for v in admin2_by_country.values())} | index {len(index)}")
    return 0


def norm_city(text: str | None) -> str:
    """Match Natural Earth's ADM1NAME spelling, which keeps the generic word."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


if __name__ == "__main__":
    raise SystemExit(main())
