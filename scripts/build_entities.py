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
from functools import lru_cache
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
    # After Eurostat, which covers both countries at NUTS 3 with population and
    # nothing else: these are the national registers, and ethnicity is a
    # question Eurostat does not ask.
    "estonia_county.json", "latvia_municipality.json", "finland_region.json",
    "singapore_region.json", "singapore_planning_area.json",
    "srilanka_province.json", "srilanka_district.json",
    "pakistan_district.json",
    "bangladesh_district.json",
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


# Letters NFKD cannot take apart, because they are not an ASCII letter plus a
# mark -- they are their own letter. Stripping combining characters leaves them
# untouched, and the old "keep only a-z0-9" rule then deleted them outright:
# "Ostfold" became "stfold", which is a substring of "vestfoldogtelemark", so
# Norway's Ostfold was joined to Vestfold og Telemark. Folding them is the
# difference between a name and a fragment of one.
FOLD = str.maketrans({
    "ø": "o", "đ": "d", "ð": "d", "ł": "l", "ħ": "h", "ŧ": "t", "ŋ": "n",
    "ı": "i", "ə": "e",
    # Modifier letters standing in for a glottal stop or 'ayn. A source writes
    # "Sanaa" where the boundary file writes "Sanʿaʾ"; they are the same name.
    # ...and the plain apostrophes that stand in for them. Removed rather than
    # left to split a word: "Dar'a" is one name, and splitting it gave "dar"
    # and "a", which lines up with nothing.
    "ʻ": "", "ʼ": "", "ʹ": "", "ʾ": "", "ʿ": "", "ʽ": "",
    "`": "", "´": "", "'": "", "’": "", "ʼ": "",
    "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th",
})


# Words that name a kind of administrative unit rather than a place, dropped
# from both sides of a comparison. English only, deliberately. Adding Latvian's
# "novads" here to reach "Aizkraukles novads" from "Aizkraukle municipality"
# also collapses "Ventspils" and "Ventspils novads" -- a state city and the
# municipality around it, two different places -- onto one key, and one of them
# then wears the other's figures. A local generic word is not a word to strip;
# it is a sign the two sources are speaking different languages, which is what
# the adapter now fixes by asking the office for its own local name.
GENERIC = (r"\b(province|state|region|district|county|prefecture|governorate|"
           r"oblast|department|municipality|city|autonomous|"
           r"territory|of|the|and)\b")


def norm(text: str | None) -> str:
    """A name reduced to what two sources are likely to agree on.

    Alphanumerics of *any* script survive. Restricting the result to a-z0-9
    deleted every letter that is not Latin, so 693 boundary names -- 352
    Russian and 256 Tunisian second-level units among them -- normalised to the
    empty string: unmatchable by name, and all colliding on one key. Cyrillic
    stays Cyrillic here rather than being romanised, because a transliteration
    this code invents is a guess about a name, while the name itself is not.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower()).translate(FOLD)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(GENERIC, " ", text)
    return "".join(c for c in text if c.isalnum())


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
            # Which file a row came from decides whether two rows landing on one
            # shape are a conflict. Across files it is normal -- India's C-01 and
            # C-16 both describe Kargil -- and within one file it means one of
            # them is wrong.
            row["_source"] = filename
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
        if key in {"id", "level", "name", "parent", "parent_name", "parent_aliases",
                   "_source"}:
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

# How much longer a boundary file's last word may be than the source's and still
# be the same word. An inflected or adjectival ending is what this is for --
# "Stockholm" against "Stockholms", "Plzen" against "Plzensky", "Northeast"
# against "Northeastern" -- and three characters covers those without reaching
# a different word: "Tala" against "Talampaya" is five.
INFLECTION_SLACK = 3

# The shortest word a match may rest on when it starts partway through a name.
# "Fes" is three letters and sits at the end of "Oued Fes", a different commune;
# a name has to give more than that before a match starting mid-way is worth
# believing. A match anchored at the first word is stronger evidence, so there
# a short word may still match, but only outright -- which is what carries
# "Lae Atoll" to "Lae" while "San" stays out of "Santa Cruz".
PREFIX_MIN = 4


@lru_cache(maxsize=200_000)
def tokens(text: str | None, joined: bool = False) -> tuple[str, ...]:
    """A name's words, folded the way norm() folds the whole string.

    norm() exists to compare two names as one key; this exists to compare them
    a word at a time, which is the only way to tell a name from a fragment of
    one that happens to straddle two words.
    """
    if not text:
        return ()
    folded = unicodedata.normalize("NFKD", text.lower()).translate(FOLD)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(GENERIC, " ", folded)
    if joined:
        folded = re.sub(r"[-\u2010\u2013]", "", folded)
    out = []
    for word in re.split(r"[^\w]+", folded, flags=re.UNICODE):
        word = "".join(c for c in word if c.isalnum())
        if word:
            out.append(word)
    return tuple(out)


def name_forms(text: str | None) -> tuple[tuple[str, ...], ...]:
    """A name's words, read both ways a hyphen can be read.

    Neither reading is right on its own. Joining fixes CGAZ's "Bio-Bio" against
    a source's "Biobio", and Timor-Leste's "Oe-Cusse" against "Oecusse".
    Splitting fixes an Arabic article the other side leaves off -- "Al-Basrah"
    against "Basra", "An-Najaf" against "Najaf" -- where the article is its own
    word and the match is a run that starts after it. Trying both costs one
    extra comparison in a pass that only runs when the exact one has failed.
    """
    split, join = tokens(text), tokens(text, joined=True)
    return (split,) if split == join else (split, join)


def run_of(short: tuple[str, ...], long: tuple[str, ...], *,
           at_start: bool = False) -> bool:
    """Whether `short` appears in `long` as a run of whole words.

    The last word may run two characters short of its counterpart, which is what
    carries "Stockholm" into "Stockholms lan" -- a source and a boundary file
    disagreeing about an inflected ending, not about which place they mean. Any
    more slack than that and a word matches a different word: "Tala" is a prefix
    of "Talampaya", and Argentina's Talampaya National Park was joined to Tala,
    835 km away. Every earlier word has to match outright, so "anta" cannot
    creep into "santa".
    """
    if not short or len(short) > len(long):
        return False
    starts = [0] if at_start else range(len(long) - len(short) + 1)
    for start in starts:
        window = long[start:start + len(short)]
        tail, target = short[-1], window[-1]
        if not all(a == b for a, b in zip(short[:-1], window[:-1])):
            continue
        if len(tail) < PREFIX_MIN and not (at_start and start == 0):
            continue
        if tail == target:
            return True
        if len(tail) >= PREFIX_MIN and target.startswith(tail) \
                and len(target) - len(tail) <= INFLECTION_SLACK:
            return True
    return False


def related(mine: tuple[tuple[str, ...], ...], theirs: tuple[tuple[str, ...], ...],
            *, at_start: bool = False) -> bool:
    """Whether either name contains the other, under any reading of a hyphen."""
    return any(run_of(a, b, at_start=at_start) or run_of(b, a, at_start=at_start)
               for a in mine for b in theirs)


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
    # Whole words again, anchored at the first one: this is what bridges
    # "Mymensingh Division" to CGAZ's "Mymensingh" and "Alif Alif Atoll" to
    # "Alif Alif". On the squashed string it did what the containment pass did,
    # and read straight across word boundaries -- "Tala" starts
    # "talampayanationalpark", so Argentina's Talampaya National Park was joined
    # to Tala, 835 km away.
    for candidate in [row["name"], *row.get("aliases", [])]:
        mine = name_forms(candidate)
        if not any(mine):
            continue
        hits = [v for k, v in lookup.items()
                if related(mine, name_forms(v["name"]), at_start=True)]
        if len(hits) == 1:
            return hits[0], "prefix"
    # Last pass: unique containment, word by word. This is what bridges a
    # source's long official form to the boundary file's short one -- Wikidata's
    # "Canton of Zurich" to CGAZ's "Zurich", "Stockholms lan" to "Stockholm",
    # "Emirate of Sharjah" to "Sharjah". Exactly one shape may qualify.
    #
    # Word by word, and not by substring, because norm() squashes a name into
    # one run of letters and a substring test then reads straight across the
    # gaps between words. "Anta" is four letters and sits inside "santacruz",
    # so Argentina's Santa Cruz was joined to Anta, 406 km away; Santa Anita
    # went to the same shape, 817 km away. Comparing tokens instead means a
    # match has to start where a word starts.
    for candidate in [row["name"], *row.get("aliases", [])]:
        mine = name_forms(candidate)
        if not any(mine):
            continue
        hits = [v for k, v in lookup.items() if related(mine, name_forms(v["name"]))]
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


def row_point(row: dict[str, Any]) -> list[float] | None:
    """The adapter row's own coordinates, if it published any.

    Wikidata writes them to `coordinates` and uses the same field to carry a gap
    marker when P625 is absent, so the shape of the value is the test.
    """
    for field in ("coordinates", "point"):
        value = row.get(field)
        if isinstance(value, (list, tuple)) and len(value) == 2 \
                and all(isinstance(n, (int, float)) for n in value):
            return [float(value[0]), float(value[1])]
    return None


def within_bbox(point: list[float] | None, bbox: list[float] | None) -> bool:
    """Whether a coordinate falls in a shape's bounding box.

    Deliberately weak as confirmation and strong as refutation: ADM2 geometry is
    dropped after the parent pass (49,349 polygons will not stay in memory), so a
    box is all there is to compare against. A point inside the box is not proof
    it is inside the shape; a point outside the box is proof it is not.
    """
    if not point or not bbox or len(bbox) != 4:
        return False
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


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

    The one case that used to slip through was a row that named a state, resolved
    it, found nothing of that name inside -- and was then handed to the
    country-wide pass anyway, which happily matched a shape in a different state.
    That is the mis-match this function exists to prevent, arrived at by the
    function's own fallback: 443 rows across nine countries, among them Vietnam's
    An Duong (Haiphong, per Wikidata) wearing the figures of An Duong in Hai
    Duong, and Argentina's Apostoles Department (Misiones) wearing Corrientes'.
    A row that contradicts itself is refused when its own published coordinates
    land outside the shape, and kept when they land inside -- which is what
    rescues the city-provinces whose parent is named historically rather than
    currently, Bogota under Cundinamarca and Lima under Lima Department.

    The disagreement on its own is deliberately *not* enough to refuse on, and
    India is the reason. Its district figures are from the 2011 census, so they
    name the states of 2011: Adilabad and Nizamabad say Andhra Pradesh where the
    boundary file says Telangana, Leh and Kargil say Jammu and Kashmir where it
    says Ladakh. Those matches are correct -- the same district, named before the
    state it sits in was split -- and refusing every parent disagreement would
    have deleted 26 of them, along with correct rows in Mexico and the US. The
    census adapters publish no coordinates, so there is no evidence either way,
    and a rule with no evidence behind it should not be deciding.
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
            # The row said which admin-1 it is in and no shape of its name is
            # there, so a country-wide match now would contradict the row's own
            # claim. Whether that contradiction is an error is decided by the
            # row's coordinates and by nothing else -- see the note below on why
            # the disagreement alone is not enough to refuse on.
            unique = {key: entities[0] for key, entities in by_name.items()
                      if len(entities) == 1}
            entity, how = match_name(row, unique)
            point = row_point(row)
            if entity is not None and point:
                if within_bbox(point, entity.get("bbox")):
                    return entity, f"{how}+point"
                return None, "outside_parent"

    unique = {key: entities[0] for key, entities in by_name.items() if len(entities) == 1}
    entity, how = match_name(row, unique)
    if entity is not None:
        return entity, how
    if norm(row.get("name") or "") in by_name:
        return None, "ambiguous"
    return None, "unmatched"


# ---------------------------------------------------------------------------
# Summing a parent from its children
# ---------------------------------------------------------------------------

ROLLUP_FIELDS = ("religion", "language", "ethnicity")

# How far the children's population may sit from the parent's own before the
# sum is refused. Rounding and small-cell suppression move it a little -- New
# Zealand randomly rounds every count to a multiple of three -- and anything
# beyond this is the two figures describing different things.
ROLLUP_TOLERANCE = 0.02

# How much the population gate widens per year between the two figures' dates,
# and the most it will ever widen by. A census and an estimate of the same
# territory taken years apart are the same people counted at different times,
# and the difference between them is growth rather than a fault: Bangladesh's
# divisions carry 2011 figures and its districts the 2022 census, so the
# children exceed their parents by about a tenth. The cap keeps this from ever
# becoming a licence -- Wales' children exceed their parent by 166%, which is
# two different things being counted and stays refused at any drift.
ROLLUP_DRIFT_PER_YEAR = 0.015
ROLLUP_DRIFT_CAP = 0.20


def published(value: Any) -> float | None:
    """A measured number, or None for a gap marker or anything else."""
    if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
        return float(value["value"])
    return None


def vintage(value: Any) -> int | None:
    """The year a measured number is for, when it says."""
    if isinstance(value, dict) and isinstance(value.get("year"), int):
        return value["year"]
    return None


def common_year(children: list[dict[str, Any]]) -> int | None:
    """The year most of the children's populations are for.

    The commonest rather than the newest: one child out of seventeen carrying a
    later date should not decide what the set is. New Zealand's territorial
    authorities are 2023 except for the Chatham Islands, whose figure this
    function's own caller had just rebuilt from its children and stamped 2025 --
    and reading the set as 2025 inverted the direction test and refused the
    whole country.
    """
    years = [y for y in ((vintage(c.get("population")) or None) for c in children)
             if y]
    if not years:
        return None
    counted: dict[int, int] = {}
    for year in years:
        counted[year] = counted.get(year, 0) + 1
    return sorted(counted, key=lambda y: (-counted[y], -y))[0]


def allowance(own_year: int | None, child_year: int | None,
              own: float, total: float) -> float:
    """How far the children may sit from the parent before it is a fault.

    Two figures of the same year should agree to the base tolerance. Two of
    different years should differ, in the direction time moves: children newer
    than their parent should be larger, children older should be smaller. The
    gate widens with the gap between the dates, but only for a difference
    pointing that way -- children *below* an older parent is shrinkage, which
    is what a missing child looks like, and gets no allowance at all.
    """
    if own_year is None or child_year is None or own_year == child_year:
        return ROLLUP_TOLERANCE
    newer = child_year > own_year
    if newer != (total > own):
        return ROLLUP_TOLERANCE
    drift = min(abs(child_year - own_year) * ROLLUP_DRIFT_PER_YEAR,
                ROLLUP_DRIFT_CAP)
    return ROLLUP_TOLERANCE + drift


def implied_total(groups: list[dict[str, Any]]) -> float | None:
    """The denominator a composition's own percentages were taken against.

    Not the unit's population, which is a different number more often than not:
    Mexico publishes indigenous-language shares of the population aged three and
    over, and New Zealand's ethnicity responses outnumber its people because one
    person may give several. Backing the denominator out of the rows keeps
    whatever basis the source used, so a parent summed from its children states
    the same kind of thing its children state.

    Taken from the largest group, whose percentage carries the least rounding
    error: a category at 0.0% would imply any denominator at all.
    """
    best: tuple[float, float] | None = None
    for row in groups:
        pct, count = row.get("pct"), row.get("count")
        if not isinstance(pct, (int, float)) or not isinstance(count, (int, float)):
            continue
        if pct <= 0:
            continue
        if best is None or count > best[0]:
            best = (count, count / (pct / 100.0))
    return best[1] if best else None


def roll_up_field(parent: dict[str, Any], children: list[dict[str, Any]],
                  field: str, *, level: str = "second-level",
                  over_published: bool = False,
                  whole_country: bool = False) -> str | None:
    """Fill a parent's composition by summing a complete set of its children.

    Ladakh is the case this exists for. It became a union territory in 2019, so
    the 2011 census that supplies India's district figures never published a row
    for it -- but it published both of its districts, Leh and Kargil, and their
    counts sum to exactly the population Wikidata gives Ladakh: 274,289. A
    territory whose every constituent part is measured should not read as
    unmeasured.

    Returns a reason string when it refuses, so the build can say what it did
    not do and why. The refusals are the point of the function as much as the
    sums are:

      * Australia's LGAs carry religion but no population, so their populations
        sum to zero. Weighting by nothing would produce a state figure with no
        basis at all -- nine states' worth.
      * Wales' 22 children sum to 3,107,513 against a parent figure of
        1,168,000. Whatever those two numbers are counting, it is not the same
        people, and a sum across that gap would be invented.

    Only a parent with an independently published population can be checked at
    all, so only such a parent is filled. A control that came from the same
    source as the children would prove the arithmetic and nothing else.

    ``whole_country`` is the one thing that replaces that control, and it is a
    stronger one. The population comparison is a proxy for "are these all the
    children"; when *every* shape at this level in the country carries the
    field, the shapes partition the country and the answer is yes by
    construction, for every parent. Bangladesh is the case: 64 of 64 districts
    join, so each of its eight divisions has all of its districts, including
    the two divisions that have no published population of their own to be
    checked against. Pakistan is why it is not assumed -- 114 of its 126
    districts join, so its provinces are genuinely short and stay refused.
    """
    current = parent.get(field)
    if isinstance(current, list) and not over_published:
        return None                                   # already has a real value
    if isinstance(current, dict) and current.get("status") == NOT_COLLECTED:
        return None            # a policy statement, not a gap: leave it standing
    if not children:
        return None

    missing = [c for c in children if not isinstance(c.get(field), list)]
    if missing:
        # Partial coverage is the dangerous case: the sum would look whole and
        # describe only part of the territory.
        return (f"{len(missing)} of {len(children)} children have no {field}"
                if len(missing) < len(children) else None)

    kid_pop = [published(c.get("population")) for c in children]
    if any(v is None for v in kid_pop):
        return f"{field}: {sum(v is None for v in kid_pop)} children have no population"
    total_pop = sum(kid_pop)                                    # type: ignore[arg-type]
    if not total_pop:
        return f"{field}: the children have no population between them"

    disagrees = ""
    own = published(parent.get("population"))
    if own is None:
        if not whole_country:
            return f"{field}: no published population to check the sum against"
    else:
        limit = allowance(vintage(parent.get("population")),
                          common_year(children), own, total_pop)
        if abs(total_pop - own) > limit * own:
            drift = "" if limit == ROLLUP_TOLERANCE else \
                f", outside even the {limit:.0%} allowed for their dates"
            if not whole_country:
                return (f"{field}: children sum to {total_pop:,.0f} against a "
                        f"published {own:,.0f}{drift}")
            # Complete children and a parent figure that disagrees with them
            # means the parent's figure is the doubtful one, not the set: Dhaka
            # division carries a 2011 population of 49,729,000 and lost
            # Mymensingh out of it in 2015, so its 44,215,759 people in 2022 are
            # not a shortfall. The sum is taken and the disagreement is written
            # into the note rather than hidden by it.
            disagrees = (f" The unit's own published population of {own:,.0f} "
                         f"disagrees with that by {100 * (total_pop - own) / own:+.0f}%; "
                         "the sum was taken anyway because every division at "
                         "this level in the country carries these figures, so "
                         "these are certainly all of its children.")

    counts: dict[str, float] = {}
    denominator = 0.0
    for child in children:
        share = implied_total(child[field])
        if share is None:
            return f"{field}: a child publishes shares with no counts"
        denominator += share
        for row in child[field]:
            count = row.get("count")
            if not isinstance(count, (int, float)):
                return f"{field}: a child publishes shares with no counts"
            counts[row.get("group", "")] = counts.get(row.get("group", ""), 0) + count
    if denominator <= 0:
        return f"{field}: the children's percentages imply no denominator"

    parent[field] = [{"group": name,
                      "pct": round(100.0 * total / denominator, 1),
                      "count": int(round(total))}
                     # Name breaks a tie, so two groups of equal size do not
                     # swap places between runs: build.json is a digest of the
                     # written files, and a churning order would invalidate
                     # every reader's cache for no change in the figures.
                     for name, total in sorted(counts.items(),
                                               key=lambda kv: (-kv[1], kv[0]))]
    # Said on the record itself, not only in the source list: a figure nobody
    # published is a different kind of claim from one somebody did, and the
    # panel that shows the bars is where a reader would want to be told.
    many = len(children) != 1
    # A figure that replaced a published one has to say so, and has to say what
    # it replaced. Overwriting the only independent statement about a unit and
    # leaving no trace would turn the control into a casualty of the sum it was
    # there to check.
    displaced = ""
    if isinstance(current, list):
        top = ", ".join(f"{g.get('group')} {g.get('pct')}%" for g in current[:3])
        displaced = (f" Replaces a separately published figure for the unit "
                     f"({top}), which is kept here as the only independent "
                     f"check on this sum.")
    parent[f"{field}_note"] = (
        f"Summed from all {len(children)} {level} division"
        f"{'s' if many else ''};"
        + (" no source publishes this figure for the unit itself."
           if not displaced else "")
        + f" {'Their' if many else 'Its'} population"
        f"{'s total' if many else ' is'} {total_pop:,.0f}"
        # A unit with no published population of its own was filled because
        # every shape at this level in the country carries the field, so the
        # note says that rather than comparing against a figure there isn't.
        + (f" against a published {own:,.0f} for the unit."
           if own is not None else
           ", and no source publishes a population for the unit to check that "
           "against; it was summed because every division at this level in the "
           "country has these figures, so these are all of its children.")
        + disagrees + displaced)
    years = {c.get(f"{field}_year") for c in children} - {None}
    if len(years) == 1:
        parent[f"{field}_year"] = years.pop()

    # A unit whose composition was just summed from a complete set of children
    # should carry their population too, when it has none or an older one.
    # Bangladesh is why: two of its divisions publish no population at all and
    # six publish 2011 figures, so the level above was summing a mixture of
    # vintages -- six 2011 divisions and two 2022 ones -- and comparing that
    # mongrel against a 2025 estimate. The children's own census total is one
    # number of one date, and the figure it replaces goes into a note.
    child_year = common_year(children)
    own_year = vintage(parent.get("population"))
    if child_year and (own is None or own_year is None or own_year < child_year):
        if own is not None:
            parent["population_note"] = (
                f"Summed from all {len(children)} {level} divisions. Replaces "
                f"a separately published {own:,.0f}"
                + (f" for {own_year}" if own_year else "")
                + ", which is kept here as the only independent check on this "
                  "sum.")
        parent["population"] = {"value": int(round(total_pop)),
                                "year": child_year,
                                "source": f"summed from {len(children)} "
                                          f"{level} divisions"}
    # Keyed on name *and* field, not name alone: one census appears in a record
    # several times under different fields, and Ladakh already carried this one
    # as the source of its "became a union territory in 2019" note. Deduplicating
    # by name dropped the entry that says where the religion figures came from,
    # which is the entry a reader would go looking for.
    seen = {(src.get("name"), src.get("field")) for src in parent.get("sources", [])}
    for child in children:
        for src in child.get("sources", []):
            mark = (src.get("name"), src.get("field"))
            if field in (src.get("field") or "") and mark not in seen:
                seen.add(mark)
                parent.setdefault("sources", []).append(dict(src))
    return None


def roll_up_countries(admin0: list[dict[str, Any]],
                      admin1_by_country: dict[str, list[dict[str, Any]]]) -> None:
    """Sum a country from its first-level divisions, where they are all there.

    Unlike the level below, this never fills a gap: every country record
    already carries a Factbook composition, so every sum here *replaces* a
    published figure. That is worth doing only because the two are not equally
    good. The children are usually a national statistical office's own count,
    itemised; the Factbook figure is an older estimate that lumps the tail into
    "other". Leaving them apart makes the map contradict itself between zoom
    levels -- Finland reads 85.9% Finnish nationally and 83.5% when you add up
    the nineteen regions drawn inside it.

    The displaced figure is written into the note rather than dropped, because
    it is the only independent statement about the country and the sum has
    nothing else to be checked against.

    The population gate is the same 2% used below, and at this level it is
    doing something different: the parent's population comes from a current
    estimate and the children's from a census, so it refuses any country whose
    census is more than a couple of years stale -- Mexico by 3.6%, New Zealand
    by 3.2%, Nepal by 6.9%, Australia by 7.5%. Those are vintage gaps rather
    than faults, and widening the bound for them is a separate decision from
    this one; it is left tight here so that nothing is rewritten on a looser
    rule than the one that has been tested.
    """
    filled: list[str] = []
    refused: list[str] = []
    for country in admin0:
        iso3 = (country.get("codes") or {}).get("iso3") or country.get("id", "")[:3]
        children = admin1_by_country.get(iso3, [])
        if not children:
            continue
        for field in ROLLUP_FIELDS:
            before = country.get(field)
            why = roll_up_field(country, children, field,
                                level="first-level", over_published=True)
            if why:
                refused.append(f"{iso3}: {why}")
            elif country.get(field) is not before:
                filled.append(f"{iso3} {field}")
    if filled:
        log(f"  summed {len(filled)} country fields from their first-level "
            f"divisions: " + ", ".join(filled))
    for line in refused:
        log(f"  country not summed -- {line}")


def roll_up_parents(admin1_by_country: dict[str, list[dict[str, Any]]],
                    admin2_by_country: dict[str, list[dict[str, Any]]]) -> None:
    """Fill what can be summed, and say what could not be."""
    filled: list[str] = []
    refused: list[str] = []
    for iso3, parents in sorted(admin1_by_country.items()):
        kids: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            kids[entity.get("parent")].append(entity)
        everywhere = {
            field: bool(admin2_by_country.get(iso3))
            and all(isinstance(e.get(field), list)
                    for e in admin2_by_country[iso3])
            for field in ROLLUP_FIELDS}
        for parent in parents:
            children = kids.get(parent["id"], [])
            for field in ROLLUP_FIELDS:
                before = parent.get(field)
                why = roll_up_field(parent, children, field,
                                    whole_country=everywhere[field])
                if why:
                    refused.append(f"{iso3} {parent['name']}: {why}")
                elif parent.get(field) is not before:
                    filled.append(f"{iso3} {parent['name']} {field}")
    if filled:
        log(f"  summed {len(filled)} admin1 fields from their children: "
            + ", ".join(filled[:8]) + (" ..." if len(filled) > 8 else ""))
    for line in refused:
        log(f"  not summed -- {line}")


EXACT = 3


def evidence(how: str) -> int:
    """How much a match is worth when two rows want the same shape.

    A name that matched outright beats one that matched by a fragment of
    itself, and a match confined to the state the row named beats one that
    searched the whole country. Rotherham's own row says "Rotherham"; Rother's
    says "Rother" and reaches the same shape through the prefix pass, so the
    exact one is the one to keep.
    """
    base = how.split("+")[0]
    if base in ("name", "alias"):
        return EXACT
    return 2 if "+" in how else 1


def resolve_collisions(matched: list[tuple[dict[str, Any], dict[str, Any], str]]
                       ) -> tuple[set[int], list[str]]:
    """Refuse rows of one file that all landed on the same shape.

    Nothing stopped several rows of one adapter from matching one boundary, and
    whichever came last silently overwrote the rest: England's East, Mid, North
    and West Devon all reached a shape called Devon, so Devon wore West Devon's
    figures and the other three vanished. Texas's Jackson County reached a shape
    called Jack. 1,324 rows were being lost this way.

    Where one row's evidence beats every other's the shape is its own and the
    rest are refused -- "Rotherham" over "Rother", "Ostrobothnia" over "Central
    Ostrobothnia". Where nothing separates them, none of them may claim it:
    four Devons and no way to tell which is the shape's is exactly the case for
    a visible gap rather than an invisible guess.

    Rows that all matched *outright* are left alone, because there the rivalry
    is usually a source listing one place twice. Wikidata carries both "Ancasti"
    and "Ancasti Department", and "Department" is a word this code drops, so
    both are the same name reaching the same shape; refusing them would lose
    Ancasti to a duplicate rather than to a mistake. Last one still wins there,
    exactly as before.
    """
    claims: dict[tuple[Any, str], list[int]] = defaultdict(list)
    for i, (row, entity, _) in enumerate(matched):
        claims[(row.get("_source"), entity["id"])].append(i)

    dropped: set[int] = set()
    notes: list[str] = []
    for (_, _eid), idxs in claims.items():
        if len(idxs) < 2:
            continue
        ranked = sorted(idxs, key=lambda i: -evidence(matched[i][2]))
        best, runner = evidence(matched[ranked[0]][2]), evidence(matched[ranked[1]][2])
        if best == EXACT:
            # A name that matched outright owns the shape; anything that got
            # there through a fragment of itself does not. Several outright
            # matches are a duplicated source row, not a rivalry.
            losers = [i for i in idxs if evidence(matched[i][2]) < EXACT]
            kept = matched[ranked[0]][0].get("name")
        else:
            losers = ranked[1:] if best > runner else ranked
            kept = matched[ranked[0]][0].get("name") if best > runner else None
        if not losers:
            continue
        dropped.update(losers)
        shape = matched[idxs[0]][1]["name"]
        names = ", ".join(str(matched[i][0].get("name"))[:24] for i in losers[:4])
        notes.append(f"{shape!r}: refused {names}" +
                     (f" (kept {kept!r})" if kept else " (nothing to separate them)"))
    return dropped, notes


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
                # Collected first, counted once. Several rows of one record can
                # fold into one group -- the US publishes Protestant, Catholic,
                # Orthodox, Latter-day Saints and Jehovah's Witnesses where
                # Australia publishes one "Christianity" -- and counting rows
                # made "units" a row tally wearing the word "areas": the app
                # read Christianity's 450 out to a reader as 450 countries,
                # when only 215 country records carry a religion at all.
                here: set[str] = set()
                for row in value:
                    if not isinstance(row.get("pct"), (int, float)):
                        continue
                    raw = row.get("group", "")
                    name = table.get(canonical_groups.key(raw), raw)
                    labels.setdefault(name, set()).add(raw)
                    here.add(name)
                for name in here:
                    units[name] = units.get(name, 0) + 1
                    countries.setdefault(name, set()).add(code)
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
                 # A residual is an answer's absence, not an answer. The
                 # picker still lists it -- dropping it would hide a fifth of
                 # some populations -- but sorts it last and says so.
                 "residual": canonical_groups.is_residual(name),
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


TRACE: set[str] = set()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", nargs="*", default=["ADM0", "ADM1", "ADM2"])
    # A count says a join went wrong; it never says which row went where, and
    # the difference between 26 matched before a change and 26 after can be a
    # dozen rows swapping places. This prints the verdict on every row of one
    # country, which is what makes a matcher change measurable rather than
    # merely plausible.
    ap.add_argument("--trace", nargs="*", default=[], metavar="ISO3",
                    help="log every adapter row's match for these countries")
    ap.add_argument("--out", type=Path, default=SITE_DATA)
    args = ap.parse_args()
    TRACE.update(iso.upper() for iso in args.trace)

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
        hit = miss = ambiguous = outside = collided = 0
        matched: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        for row in rows:
            # Aliases travel with the key. They were being dropped here, which
            # made every alias an adapter declared for an admin-2 row or its
            # parent dead weight -- the matcher never saw them.
            key = {"name": row.get("name") or "",
                   "aliases": row.get("aliases") or [],
                   "parent_name": row.get("parent_name"),
                   "parent_aliases": row.get("parent_aliases") or [],
                   # The coordinates travel with the key for the same reason the
                   # aliases do: the matcher cannot use what this dict leaves
                   # behind, and dropping them here would silently disable the
                   # one rescue that lets a correct match survive a parent named
                   # historically rather than currently.
                   "point": row_point(row)}
            if row.get("level") == "admin1":
                entity, how = match_name(key, a1)
            else:
                entity, how = match_admin2(key, a2, a1)
            if entity is None:
                miss += 1
                ambiguous += how == "ambiguous"
                outside += how == "outside_parent"
                if iso3 in TRACE:
                    log(f"    trace {iso3} {row.get('name')!r}: {how}")
                continue
            matched.append((row, entity, how))

        # Second pass, because a collision cannot be seen one row at a time.
        dropped, notes = resolve_collisions(matched)
        collided = len(dropped)
        miss += collided
        for i, (row, entity, how) in enumerate(matched):
            if iso3 in TRACE:
                verdict = "beaten to it by another row" if i in dropped else how
                log(f"    trace {iso3} {row.get('name')!r} -> "
                    f"{entity.get('name')!r} ({verdict})")
            if i in dropped:
                continue
            merge_adapter(entity, row)
            entity["match"] = f"adapter:{how}"
            hit += 1
        for note in notes[:4]:
            log(f"    {iso3} {note}")
        if len(notes) > 4:
            log(f"    {iso3} ...and {len(notes) - 4} more shapes with rival rows")
        if rows:
            # Named separately because they mean different things. "Ambiguous"
            # is a row we cannot place; "outside" is a row we could have placed
            # wrongly and refused to -- the count is the mis-match that is no
            # longer happening, and it should not quietly grow.
            why = [f"{ambiguous} ambiguous" if ambiguous else "",
                   f"{outside} outside their stated parent" if outside else "",
                   f"{collided} beaten to their shape by another row" if collided else ""]
            extra = " (" + ", ".join(w for w in why if w) + ")" if any(why) else ""
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

    # -- sum parents from children -------------------------------------------
    # After the policy, so "not collected" still wins: a country that does not
    # ask the question has no children to sum, and must not be given a figure by
    # a later pass that only looks at arithmetic.
    roll_up_parents(admin1_by_country, admin2_by_country)
    # After the level below, so a first-level unit that was itself summed can
    # carry into its country -- and so the country's note counts the divisions
    # as they finally stand rather than as they arrived.
    roll_up_countries(admin0, admin1_by_country)

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
