#!/usr/bin/env python3
"""Kuwait's governorates and areas in the 2021 register-based census.

The Central Statistical Bureau's first register-based census (التعداد
التسجيلي لدولة الكويت 2021, with the Public Authority for Civil Information)
publishes its tables on census.csb.gov.kw, each exportable as a workbook
(``CensusData?st_id=N&handler=ExportExcel``). Four are read:

* Table 1 (st_id 4): every governorate's people by nationality (Kuwaiti,
  non-Kuwaiti) and sex;
* Table 2 (st_id 5): every governorate's people by five-year age group and sex;
* Table 6 (st_id 26): every governorate's people by nationality group (Gulf,
  Arab, Asian, African, European, North American, South American,
  Australian) and sex;
* Table 52 (st_id 72): the people habitually resident in each of the 157
  areas (مناطق), by nationality and sex, under their Arabic and English names.

**What is written.** For each governorate: population, males per hundred
females, median age, and people by nationality on the ethnicity field --
Kuwaitis (Table 1), the other Gulf states' citizens (Table 6's Gulf group
less the Kuwaitis), and the rest by Table 6's groups ("Australian", a
continent's group beside the others, is written "Oceanian nationalities").
For each drawn area that is the ground of one or more census areas:
population, males per hundred females, and Kuwaiti against non-Kuwaiti
nationals. Every other drawn area says why it has none.

**Which area is which governorate's** is measured, not assumed: Table 52
lists the areas governorate by governorate, and the running sum of its rows
must close on each governorate's Table 1 total in turn, or the run stops.

**Binding an area is measured on the ground.** The boundary file's area
polygons are not the census's areas: drawn "Yarmouk" holds a quarter of
Al-Yarmouk, drawn "Rawda" holds Al-Rawda and most of Al-Adailiya, drawn
"Messila" holds Al-Masayel and blocks of Sabah Al-Salem. So a name is no
evidence. OpenStreetMap carries most census areas' outlines under their
Arabic names (``boundary=administrative``, ``admin_level=6``, mapped from the
Public Authority for Civil Information's areas). Each run reads them through
the Overpass API, finds each of Table 52's areas by its Arabic name, and
measures the share of its ground (on drawn land) inside each drawn polygon;
``--osm`` stops there and writes the measurement to
``data/raw/kuwait/osm_areas.json`` (not committed), which a later run on the
same machine reuses. A governorate's desert (بر محافظة ...) is outlined as
the drawn governorate less every outlined area.

A drawn polygon then carries the census areas whose ground lies at least
``HOME`` inside it, summed, and only when the other census areas inside it
would hold no more than ``STRAY`` of their people. An outlined area counts
at its own average density over its ground there; an area OpenStreetMap only
marks with a point (or, failing that, a declared GeoNames point,
``GEONAMES``) counts whole in the polygon holding the point; an area with
neither outline nor point counts whole in every polygon of its governorate,
since it could be in any. Every polygon refused, every census area with no
home, and every area OpenStreetMap does not outline is logged with its
numbers.

**Small counts.** A sex ratio is not written for fewer than ``MIN_SEX`` men or
women, nor a nationality split for fewer than ``MIN_PEOPLE`` people: the
census's three people of Failaka Island are a count, not a share. An area
with more than three men per woman says the ratio is the census's count,
with the country's non-Kuwaitis' own.

**Checks** (any failure stops the run): every table's rows add up (men and
women to the total, Kuwaitis and others to everyone); the governorates make
the census's total; age groups and nationality groups make each
governorate; the areas close on the governorates; each census area is
bound at most once.

Usage:
    python -m scripts.fetch_census.kuwait_census --osm   # measure areas' ground only
    python -m scripts.fetch_census.kuwait_census
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import check, median_age, sex_ratio, units, workbook

ISO3 = "KWT"
OUT = "kuwait_census.json"
OSM_FILE = PROCESSED.parent / "raw" / "kuwait" / "osm_areas.json"
YEAR = 2021
EXPORT = "https://census.csb.gov.kw/CensusData?st_id={}&handler=ExportExcel"
TABLES = {"nationality": 4, "ages": 5, "groups": 26, "areas": 72}
PAGE = "https://census.csb.gov.kw/CensusData_EN?id=1"
SOURCE = ("Central Statistical Bureau (Kuwait), Register-based Census 2021, Table {}")
LICENCE = "Central Statistical Bureau of Kuwait, published census tables"
OSM_SOURCE = ("OpenStreetMap contributors (ODbL), the areas' outlines "
              "(boundary=administrative, admin_level=6) read through the Overpass API")
# The census's total, the first figure on census.csb.gov.kw: 4,385,717.
NATIONAL = 4_385_717
# A polygon no census area can be bound to says why, and the statement
# displaces an encyclopaedia's population for it dated before this year (the
# build's ``displaces_before``), undated ones included (``displaces_undated``):
# the polygon is not the census's area at any date. Wikidata's 393,432 (2014)
# stood on the polygon labelled Jahra, which holds 38% of the census's
# Al-Jahra area's ground and no census area mostly.
DISPLACES_BEFORE = 2026
# Table 1's governorates, in the order the area table lists them, and the
# boundary file's labels for them.
GOVERNORATES = {
    "The Capital": "Al Asimah",
    "Hawalli": "Hawalli",
    "Al-Ahmadi": "Ahmadi",
    "Al-Jahra": "Jahra",
    "Al-Farwaniya": "Farwaniya",
    "Mubarak Al-Kabeer": "Mubarak Al-Kabeer",
}
# Table 6's nationality groups, as the map writes them. "Australian" stands
# beside the continents' groups, so it is the continent's nationals.
GROUPS = {
    "Gulf": None,             # split into Kuwaitis and other GCC citizens
    "Arabic": "Other Arab nationalities",
    "Asian": "Asian nationalities",
    "African": "African nationalities",
    "European": "European nationalities",
    "North America": "North American nationalities",
    "South America": "South American nationalities",
    "Australian": "Oceanian nationalities",
}
SEXES = ("Male", "Female", "Total")

# A census area is a drawn polygon's when at least this share of its ground
# (on drawn land) lies inside it ...
HOME = 0.80
# ... and a polygon carries its census areas only when the other areas' ground
# inside it would hold, at each area's own average density, at most this share
# of their people. The share northern Cyprus's quarters are held to.
STRAY = 0.10
# Below these a ratio or a share says nothing about a place.
MIN_SEX = 50
MIN_PEOPLE = 100
# More men per woman than this is explained in the note.
SKEWED = 3
# What the census does not publish, read off its list of 118 tables
# (CensusData_EN?id=1, probe 3fc32eb) and Table 53 itself (probe d6e67dd): no
# table by religion or language, and ages by governorate (Tables 2-4) or for
# the whole country (Table 53) only.
TABLE_LIST = ("none of the 118 tables the census publishes on census.csb.gov.kw "
              "(CensusData_EN?id=1)")
RELIGION_WHY = (f"Kuwait's 2021 register-based census publishes no religion table: {TABLE_LIST} "
                "is by religion.")
LANGUAGE_WHY = (f"Kuwait's 2021 register-based census publishes no language table: "
                f"{TABLE_LIST} is by language.")
AREA_AGE_WHY = ("The 2021 census counts each area's residents by nationality and sex only "
                "(Table 52); its age tables are by governorate (Tables 2-4) or for the whole "
                "country (Table 53), so no area's median age is published.")

# OpenStreetMap's areas, read in four boxes (south, west, north, east) so a
# busy server answers each.
OVERPASS = "https://overpass-api.de/api/interpreter"
BOXES = ("28.5,46.5,28.95,48.6", "28.95,46.5,29.5,47.85", "28.95,47.85,29.5,48.6",
         "29.5,46.5,30.15,48.6")
PLACE_KINDS = ("suburb", "quarter", "city", "town", "village", "locality", "island",
               "neighbourhood")
# Table 52's Arabic names that OpenStreetMap writes otherwise: the census's
# name -> OSM's names, whose outlines together are the census area. Each is
# the same place under a spelling or a fuller name (الصليبيخات / الصليبخات,
# "Doha residential" / الدوحة, "Fahad Al-Ahmad Al-Jaber" / فهد الأحمد), or
# the census's one area that OSM maps in parts (the three Shuwaikh
# industrial blocks).
OSM_NAMES = {
    "الشويخ الصناعية": ["الشويخ الصناعية 1", "الشويخ الصناعية 2", "الشويخ الصناعية 3"],
    "الصليبيخات": ["الصليبخات"],
    "الدوحة السكنية": ["الدوحة"],
    "شمال غرب الصليبيخات": ["شمال غرب الصليبخات"],
    "مدينة جابر الأحمد": ["جابر الأحمد"],
    "منطقة وزارات": ["منطقة الوزارات"],
    "فهد الأحمد الجابر": ["فهد الأحمد"],
    "علي صباح السالم": ["ام الهيمان-علي صباح السالم"],
    "عبدالله المبارك": ["عبدالله المبارك الصباح"],
    "غرب عبدالله المبارك": ["غرب عبدالله المبارك الصباح"],
    "غرب أبو فطيرة": ["غرب أبو فطيرة الحرفية"],
    "المطار": ["المطار الدولي"],
    "الجهراء الصناعية الحرفية 1": ["الجهراء الصناعية الحرفية"],
    "الشعيبة الصناعية غ": ["الشعيبه الصناعيه الغربيه"],
    "ميناء عبدالله صناعية": ["ميناء عبدالله"],
    "الصليبية السكنية": ["الصليبية الشعبية"],
    # Sabah Al-Ahmad City's five census areas are one outline in OSM: each
    # takes the city's ground, so all five are homed (or not) together.
    "صباح الأحمد 1": ["صباح الأحمد"], "صباح الأحمد 2": ["صباح الأحمد"],
    "صباح الأحمد 3": ["صباح الأحمد"], "صباح الأحمد 4": ["صباح الأحمد"],
    "صباح الأحمد 5": ["صباح الأحمد"],
    "صباح الأحمد البحرية": ["مدينة صباح الأحمد البحرية"],
    "الجواخير الجنوبية": ["الجنوبية الجواخير"],
    "الزور": ["الزور وصولة"],
    # OSM has no outline of Ahmadi City, only the city's point, named الأحمدي.
    "مدينة الأحمدي": ["الأحمدي"],
}
# A governorate's desert: the census's name begins so.
DESERT = "بر محافظة"
# Census areas OpenStreetMap neither outlines nor marks, placed instead by
# GeoNames points (runner probe 95a9b67): its area features (ADM2), which
# follow the Public Authority for Civil Information's areas, and the village
# the Khairan chalets stand by. Each point counts its area whole in the
# polygon holding it, as an OSM point does; Al-Misila has two, and counts in
# both polygons. GeoNames has one area for Ardiya's storage and
# government-use zones, which the census counts apart, so both take it.
ARDIYA = ("geonames:12216345 Al Aridiyah Takhzin wa Isti'malat al Hukumiyah", 29.27910,
          47.91486)
GEONAMES = {
    "المسيلة": [("geonames:12216417 Al Masilah (area)", 29.23720, 48.08749),
                ("geonames:387962 Al Masilah (locality)", 29.26194, 48.07972)],
    "العارضية مخازن": [ARDIYA],
    "العارضية استعمال الحكومة": [ARDIYA],
    "شاليهات الخيران": [("geonames:285790 Al Khiran (village)", 28.66300, 48.37900)],
}


def numbers(row: list[Any]) -> list[float]:
    return [float(c) for c in row if isinstance(c, (int, float)) and not isinstance(c, bool)]


ARABIC = re.compile(r"[؀-ۿ]")


def english(row: list[Any]) -> list[str]:
    """A row's English labels: text cells with no Arabic letter, spaces made plain."""
    out = []
    for c in row:
        if not isinstance(c, str):
            continue
        text = " ".join(c.replace("\xa0", " ").split())
        if text and not ARABIC.search(text) and re.search(r"[A-Za-z0-9>]", text):
            out.append(text)
    return out


def arabic(row: list[Any]) -> str:
    """A row's first Arabic label, spaces made plain."""
    return next((" ".join(c.replace("\xa0", " ").split()) for c in row
                 if isinstance(c, str) and ARABIC.search(c)), "")


def fold_ar(text: str) -> str:
    """An Arabic name reduced to what spellings agree on: no vowel marks or
    tatweel, one alef, ta marbuta as ha, alef maqsura as ya, no spaces."""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[ً-ْـ]", "", text)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"),
                 ("ؤ", "و"), ("ئ", "ي")):
        text = text.replace(a, b)
    return re.sub(r"[^ء-ي0-9]", "", text)


def governorate_of(label: str) -> str | None:
    text = re.sub(r"\s*Governorate\s*$", "", label.strip(), flags=re.I)
    return text if text in GOVERNORATES else None


def table1(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Governorate -> Kuwaiti/other/all by sex, from Table 1."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        words, figures = english(row), numbers(row)
        if len(figures) != 9 or not words:
            continue
        gov = governorate_of(words[-1])
        name = gov or words[-1]
        km, kf, kt, nm, nf, nt, tm, tf, tt = figures
        for a, b, c, what in ((km, kf, kt, "Kuwaitis"), (nm, nf, nt, "others"),
                              (tm, tf, tt, "everyone")):
            check(a + b == c, f"kuwait_census: Table 1 {name} {what}: {a:,.0f} + {b:,.0f} "
                              f"!= {c:,.0f}")
        check(kt + nt == tt, f"kuwait_census: Table 1 {name}: nationalities do not make {tt:,.0f}")
        out[name] = {"kuwaiti": kt, "other": nt, "men": tm, "women": tf, "total": tt}
    check(set(GOVERNORATES) <= set(out), f"kuwait_census: Table 1 rows {sorted(out)}")
    made = sum(out[g]["total"] for g in GOVERNORATES) + out.get("Not Stated", {}).get("total", 0)
    check(out.get("Total", {}).get("total") == NATIONAL == made,
          f"kuwait_census: Table 1 makes {made:,.0f}, its total row "
          f"{out.get('Total', {}).get('total')}, the census {NATIONAL:,}")
    return out


AGE = re.compile(r"^(\d+)\s*-\s*(\d+)$|^>\s*(\d+)$")


def table2(rows: list[list[Any]]) -> dict[str, list[tuple[int, int | None, float]]]:
    """Governorate -> both sexes' five-year groups, from Table 2."""
    groups: dict[str, list[tuple[int, int | None, float]]] = {g: [] for g in GOVERNORATES}
    current = None
    for row in rows:
        words, figures = english(row), numbers(row)
        if len(figures) != 8:
            continue
        for w in words:
            m = AGE.match(w)
            if m:
                current = ((int(m.group(1)), int(m.group(2))) if m.group(1)
                           else (int(m.group(3)) + 1, None))
            elif w == "Total" and words.index(w) > 0:
                current = None
        if "Total" not in words[:1] or current is None:
            continue
        for gov, people in zip(GOVERNORATES, figures[:6]):
            groups[gov].append((current[0], current[1], people))
    for gov, got in groups.items():
        got.sort(key=lambda g: g[0])
        edge = 0
        for low, high, _n in got:
            check(low == edge, f"kuwait_census: Table 2 {gov}: age groups break at {edge}")
            edge = high + 1 if high is not None else -1
        check(got and got[-1][1] is None, f"kuwait_census: Table 2 {gov}: no open group")
    return groups


def table6(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Governorate -> nationality group -> people (both sexes), from Table 6."""
    out: dict[str, dict[str, float]] = {}
    current = None
    for row in rows:
        words, figures = english(row), numbers(row)
        # A block's first row carries its sex and its place ("Male", "Not
        # Stated"); the place holds until the next block's first row.
        if len(words) >= 2 and words[0] in SEXES:
            current = governorate_of(words[1])
        if len(figures) != len(GROUPS) + 1 or words[:1] != ["Total"] or current is None:
            continue
        check(sum(figures[:-1]) == figures[-1],
              f"kuwait_census: Table 6 {current}: groups do not make {figures[-1]:,.0f}")
        out[current] = dict(zip(GROUPS, figures[:-1])) | {"total": figures[-1]}
    check(set(GOVERNORATES) <= set(out), f"kuwait_census: Table 6 governorates {sorted(out)}")
    return out


def table52(rows: list[list[Any]], govs: dict[str, dict[str, float]] | None = None
            ) -> dict[str, dict[str, Any]]:
    """Area -> its people by nationality and sex, its Arabic name and its governorate.

    The governorate is found by the running sum: the rows close on each
    governorate's Table 1 total in Table 1's order, or the run stops. Without
    ``govs`` (the ``--osm`` mode, which needs only the names) it is not found.
    """
    areas: list[tuple[str, str, list[float]]] = []
    for row in rows:
        words, figures = english(row), numbers(row)
        if len(figures) != 9 or not words:
            continue
        name = words[-1]
        km, kf, kt, nm, nf, nt, tm, tf, tt = figures
        check(km + kf == kt and nm + nf == nt and tm + tf == tt and kt + nt == tt,
              f"kuwait_census: Table 52 {name}: its cells do not add up")
        areas.append((name, arabic(row), figures))
    out: dict[str, dict[str, Any]] = {}
    order = list(GOVERNORATES)
    gov_i, run = 0, 0.0
    for name, ar, f in areas:
        if name in ("NOT STATED", "TOTAL"):
            continue
        check(name not in out, f"kuwait_census: Table 52 lists {name} twice")
        entry = {"ar": ar, "kuwaiti": f[2], "other": f[5], "men": f[6], "women": f[7],
                 "total": f[8], "other_men": f[3], "other_women": f[4]}
        out[name] = entry
        if govs is None:
            continue
        check(gov_i < len(order), f"kuwait_census: Table 52 runs past the governorates at {name}")
        gov = order[gov_i]
        entry["governorate"] = gov
        run += f[8]
        if run == govs[gov]["total"]:
            gov_i, run = gov_i + 1, 0.0
        check(run < govs[gov]["total"], f"kuwait_census: Table 52's areas overrun {gov}")
    if govs is not None:
        check(gov_i == len(order), f"kuwait_census: Table 52's areas close on {gov_i} "
                                   f"governorates")
    return out


# --- where each census area is: OpenStreetMap's outlines on the drawn polygons ---

def overpass(box: str) -> list[dict[str, Any]]:
    """The named areas (administrative level 6, or places drawn as areas) and
    the named place points in a box."""
    within = f"({box})"
    kinds = "|".join(PLACE_KINDS)
    query = ("[out:json][timeout:240];("
             f'relation["boundary"="administrative"]["admin_level"="6"]["name"]{within};'
             f'way["boundary"="administrative"]["admin_level"="6"]["name"]{within};'
             f'relation["place"~"^({kinds})$"]["name"]{within};'
             f'way["place"~"^({kinds})$"]["name"]{within};'
             f'node["place"~"^({kinds})$"]["name"]{within};'
             ");out geom;")
    req = urllib.request.Request(
        OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/"
                               "DemographicMap) python-urllib"})
    # A busy public server answers 429 or 504 now and then; it is asked again
    # after a pause, and a fifth refusal stops the run.
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=400) as fh:
                return json.loads(fh.read()).get("elements") or []
        except urllib.error.HTTPError as err:
            if err.code not in (429, 502, 503, 504) or attempt == 4:
                raise
            log(f"    Overpass {box}: {err.code}, asking again in {60 * (attempt + 1)} s")
            time.sleep(60 * (attempt + 1))
    return []


def osm_index(elements: list[dict[str, Any]]) -> dict[str, list[tuple[str, Any]]]:
    """Folded Arabic name -> [(OSM id, outline)], areas only, administrative first."""
    from .west_asia_probe import osm_shape
    out: dict[str, list[tuple[str, Any, int]]] = defaultdict(list)
    for el in elements:
        if el.get("type") == "node":
            continue
        tags = el.get("tags") or {}
        geom = osm_shape(el)
        if geom is None or geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        rank = 0 if tags.get("boundary") == "administrative" else 1
        for name in {tags.get("name:ar", ""), tags.get("name", "")}:
            if name and ARABIC.search(name):
                out[fold_ar(name)].append((f"{el['type'][0]}{el['id']}", geom, rank))
    # One outline per name: the administrative area where there is one.
    return {k: [(i, g) for i, g, r in sorted(v, key=lambda t: t[2])
                if r == min(t[2] for t in v)] for k, v in out.items()}


def osm_points(elements: list[dict[str, Any]]) -> dict[str, list[tuple[str, float, float]]]:
    """Folded Arabic name -> [(OSM id, lon, lat)] of the named place points."""
    out: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for el in elements:
        if el.get("type") != "node" or "lat" not in el:
            continue
        tags = el.get("tags") or {}
        for name in {tags.get("name:ar", ""), tags.get("name", "")}:
            if name and ARABIC.search(name):
                out[fold_ar(name)].append((f"n{el['id']}", el["lon"], el["lat"]))
    return dict(out)


def lookup(index: dict[str, list[Any]], name: str) -> list[Any]:
    """An index's entries for a name, or for the name without its article."""
    return index.get(fold_ar(name)) or index.get(fold_ar(re.sub(r"^ال", "", name))) or []


def outlines(areas: dict[str, dict[str, Any]], index: dict[str, list[tuple[str, Any]]]
             ) -> dict[str, tuple[list[str], Any]]:
    """Census area -> (OSM ids, its outline), for the areas OSM outlines under
    their name (or every name ``OSM_NAMES`` gives them)."""
    from shapely.ops import unary_union
    out: dict[str, tuple[list[str], Any]] = {}
    for name, a in areas.items():
        found: list[tuple[str, Any]] = []
        for want in OSM_NAMES.get(a["ar"], [a["ar"]]):
            hits = lookup(index, want)
            if not hits:
                found = []
                break
            # Every outline of the name: OSM maps some areas in two pieces.
            found += hits
        if found:
            out[name] = ([i for i, _g in found], unary_union([g for _i, g in found]))
    return out


def spread(outline: Any, drawn: dict[str, Any], land: Any) -> dict[str, float]:
    """The share of an outline's drawn-land ground inside each drawn polygon."""
    on_land = outline.intersection(land).area
    shares: dict[str, float] = {}
    if on_land <= 0:
        return shares
    for sid, poly in drawn.items():
        if poly.intersects(outline):
            s = poly.intersection(outline).area / on_land
            if s >= 0.005:
                shares[sid] = round(s, 4)
    return shares


def holder(lon: float, lat: float, drawn: dict[str, Any]) -> str | None:
    """The one drawn polygon holding a point, or None."""
    from shapely.geometry import Point
    hits = [sid for sid, poly in drawn.items() if poly.contains(Point(lon, lat))]
    return hits[0] if len(hits) == 1 else None


def ground(areas: dict[str, dict[str, Any]], elements: list[dict[str, Any]],
           drawn2: dict[str, Any], labels2: dict[str, str], drawn1: dict[str, Any],
           labels1: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Each census area placed on the drawn polygons: the share of its ground
    in each (second level, and first level for the governorates' notes), or,
    where OSM has no outline of it, the polygons holding its OSM points.

    ``areas`` must carry each area's governorate: a desert's outline is the
    drawn governorate less every outlined area.
    """
    from shapely.ops import unary_union
    index = osm_index(elements)
    points = osm_points(elements)
    found = outlines(areas, index)
    covered = unary_union([g for _ids, g in found.values()]) if found else None
    gov_shape = {labels1[sid]: g for sid, g in drawn1.items()}
    for name, a in areas.items():
        if name in found or not a["ar"].startswith(DESERT):
            continue
        shape = gov_shape.get(GOVERNORATES.get(a.get("governorate", ""), ""))
        if shape is not None:
            found[name] = ([], shape.difference(covered) if covered is not None else shape)
    land2 = unary_union(list(drawn2.values()))
    land1 = unary_union(list(drawn1.values()))
    out: dict[str, dict[str, Any]] = {}
    for name, a in areas.items():
        entry: dict[str, Any] = {"ar": a["ar"], "osm": [], "shares": {}, "admin1": {}}
        if name in found:
            ids, outline = found[name]
            on_land = outline.intersection(land2).area
            shares = spread(outline, drawn2, land2)
            entry.update(
                osm=ids, desert=not ids, shares=shares, admin1=spread(outline, drawn1, land1),
                km2=round(outline.area * 111.32 ** 2 * 0.8723, 3),
                on_drawn_land=round(on_land / outline.area, 4) if outline.area else 0,
                drawn={labels2[s]: v for s, v in sorted(shares.items(), key=lambda kv: -kv[1])})
        else:
            spots = [p for want in OSM_NAMES.get(a["ar"], [a["ar"]]) for p in lookup(points, want)]
            if not spots:
                spots = [(pid, lon, lat) for pid, lat, lon in GEONAMES.get(a["ar"], [])]
            entry["points"] = {pid: holder(lon, lat, drawn2) for pid, lon, lat in spots}
        out[name] = entry
    return out


def measure_ground(areas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Every census area placed on the drawn polygons, from OSM read now."""
    from .sea_common import polygons
    elements: list[dict[str, Any]] = []
    for box in BOXES:
        got = overpass(box)
        log(f"  Overpass {box}: {len(got)} named areas and points")
        elements += got
    admin2, admin1 = units(ISO3, "admin2"), units(ISO3, "admin1")
    labels2 = {u["id"]: u["name"] for u in admin2}
    labels1 = {u["id"]: u["name"] for u in admin1}
    drawn2 = {sid: g for sid, g in polygons("admin2", ISO3, 8).items() if sid in labels2}
    drawn1 = {sid: g for sid, g in polygons("admin1", ISO3, 7).items() if sid in labels1}
    placed = ground(areas, elements, drawn2, labels2, drawn1, labels1)
    outlined = [n for n, p in placed.items() if p["osm"]]
    deserts = [n for n, p in placed.items() if p.get("desert")]
    pointed = {n: p["points"] for n, p in placed.items() if p.get("points")}
    lost = sorted(set(placed) - set(outlined) - set(deserts) - set(pointed))
    log(f"  census areas placed by their OSM outline: {len(outlined)} of {len(placed)}; "
        f"governorate deserts outlined as the rest of the drawn governorate: {deserts}")
    log("  placed by points only (OSM's, or GeoNames' where OSM has none): " + "; ".join(
        f"{n} ({areas[n]['ar']}, {areas[n]['total']:,.0f}) in "
        + ", ".join(f"{labels2.get(s, 'no drawn polygon') if s else 'no drawn polygon'} "
                    f"({pid})" for pid, s in pts.items())
        for n, pts in sorted(pointed.items())))
    log(f"  neither outlined nor pointed: {len(lost)}: " + "; ".join(
        f"{n} ({areas[n]['ar']}, {areas[n]['total']:,.0f})" for n in lost))
    return {"source": OSM_SOURCE, "read": date.today().isoformat(), "home": HOME,
            "areas": placed}


# --- binding ------------------------------------------------------------------

def others_inside(sid: str, names: list[str], areas: dict[str, dict[str, Any]],
                  shares: dict[str, dict[str, float]], spots: dict[str, set[str]],
                  anywhere: dict[str, set[str]],
                  gazetteer: dict[str, str] | None = None) -> list[tuple[float, str, str]]:
    """The people of other census areas a drawn polygon may hold, largest
    first: (people, area, how they are counted). ``gazetteer`` names the
    source of each placed-by-point area's point (OpenStreetMap by default)."""
    out = []
    for m, s in shares.items():
        if m not in names and s.get(sid, 0) > 0:
            out.append((areas[m]["total"] * s[sid], m, f"{s[sid]:.0%} of its ground"))
    for m, where in spots.items():
        if m not in names and sid in where:
            source = (gazetteer or {}).get(m, "OpenStreetMap")
            out.append((areas[m]["total"], m, f"whole: {source} places it here by a point, "
                                              f"and OpenStreetMap does not outline it"))
    for m, where in anywhere.items():
        if m not in names and sid in where:
            out.append((areas[m]["total"], m, "whole: OpenStreetMap neither outlines nor "
                                              "marks it, so it may be in any polygon of its "
                                              "governorate"))
    return sorted(out, reverse=True)


def bind(areas: dict[str, dict[str, Any]], placed: dict[str, dict[str, Any]],
         admin2: list[dict[str, Any]], parents: dict[str, str]
         ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Drawn polygon id -> the census areas it carries; and every other drawn
    polygon id -> why it carries none.

    A census area's home is the polygon holding at least ``HOME`` of its
    ground; a polygon carries its homed areas only when the other areas it
    may hold (``others_inside``) come to at most ``STRAY`` of their people.
    """
    known = {n: p for n, p in placed.items() if n in areas}
    missing = sorted(set(areas) - set(known))
    check(not missing, f"kuwait_census: the measurement has no entry for {missing}; "
                       f"re-run --osm")
    shares = {n: p["shares"] for n, p in known.items() if p.get("shares")}
    labels = {u["id"]: u["name"] for u in admin2}
    # Areas with no outline: where their points lie, or else anywhere in the
    # drawn governorate the census counts them in.
    spots = {n: {s for s in (p.get("points") or {}).values() if s}
             for n, p in known.items()
             if not p.get("shares") and not p.get("osm") and not p.get("desert")}
    by_gov: dict[str, set[str]] = defaultdict(set)
    for unit in admin2:
        by_gov[parents.get(unit["parent"], "")].add(unit["id"])
    anywhere = {n: by_gov[GOVERNORATES[areas[n]["governorate"]]]
                for n, where in spots.items() if not where}
    spots = {n: where for n, where in spots.items() if where}
    gazetteer = {n: "GeoNames" for n in spots
                 if all(p.startswith("geonames:") for p in known[n].get("points") or {})}
    homes: dict[str, list[str]] = defaultdict(list)
    for name, s in shares.items():
        sid, best = max(s.items(), key=lambda kv: kv[1])
        if best >= HOME:
            homes[sid].append(name)
    bound: dict[str, dict[str, Any]] = {}
    why: dict[str, str] = {}
    for unit in admin2:
        sid = unit["id"]
        names = sorted(homes.get(sid, []))
        inside = others_inside(sid, names, areas, shares, spots, anywhere, gazetteer)
        stray = sum(n for n, _m, _how in inside)
        if names:
            own = sum(areas[n]["total"] for n in names)
            if own > 0 and stray <= STRAY * own:
                bound[sid] = {"names": names, "stray": stray, "own": own,
                              "shares": {n: shares[n][sid] for n in names},
                              "deserts": [n for n in names if known[n].get("desert")]}
                continue
            why[sid] = (
                f"The census areas whose ground lies mostly inside this polygon -- "
                + ", ".join(f"{n.title()} ({areas[n]['total']:,.0f} people, "
                            f"{shares[n][sid]:.0%} of its ground)" for n in names)
                + f" -- are not all it may hold: other census areas inside it would add some "
                  f"{stray:,.0f} people ({stray / own:.1%} of these, more than the "
                  f"{STRAY:.0%} a binding allows), chiefly "
                + "; ".join(f"{m.title()} {n:,.0f} ({how})" for n, m, how in inside[:3])
                + ". The boundary file's line here is not the census's, so no count is this "
                  "polygon's.") if own > 0 else "The census counts no one here."
            continue
        if inside:
            why[sid] = ("No census area's ground lies mostly inside this polygon. It may hold "
                        + "; ".join(f"{m.title()} ({how})" for _n, m, how in inside[:4])
                        + " -- measured on OpenStreetMap's outlines and points of the census's "
                          "areas -- so no count is this polygon's.")
        else:
            why[sid] = ("No census area OpenStreetMap outlines or marks lies inside this "
                        "polygon, so no count is known to be this polygon's.")
    for sid, b in bound.items():
        log(f"    {labels[sid]:32} {b['own']:>9,.0f} <- " + ", ".join(
            f"{n} {b['shares'][n]:.0%}" for n in b["names"]) + f" (stray {b['stray']:,.0f})")
    for sid, text in why.items():
        if text.startswith("The census areas whose ground"):
            log(f"    refused {labels[sid]}: {text}")
    homeless = sorted(n for n, s in shares.items() if max(s.values()) < HOME)
    log(f"  drawn areas carrying census areas: {len(bound)} of {len(admin2)}")
    log(f"  census areas with no home: {len(homeless)}: " + "; ".join(
        f"{n} ({labels.get(max(shares[n], key=shares[n].get), '?')} "
        f"{max(shares[n].values()):.0%})" for n in homeless))
    log("  census areas placed by points only: " + "; ".join(
        f"{n} ({areas[n]['total']:,.0f}, {gazetteer.get(n, 'OpenStreetMap')}) in "
        f"{', '.join(labels[s] for s in sorted(w))}" for n, w in sorted(spots.items())))
    log("  census areas with neither outline nor point: " + "; ".join(
        f"{n} ({areas[n]['total']:,.0f}, {areas[n]['governorate']})"
        for n in sorted(anywhere)))
    return bound, why


def area_fields(names: list[str], areas: dict[str, dict[str, Any]],
                b: dict[str, Any], non_kuwaiti_men: float,
                non_kuwaiti_women: float) -> dict[str, Any]:
    """Population, sex ratio and nationality for the census areas a polygon carries."""
    total = sum(areas[n]["total"] for n in names)
    men = sum(areas[n]["men"] for n in names)
    women = sum(areas[n]["women"] for n in names)
    kuwaiti = sum(areas[n]["kuwaiti"] for n in names)
    other = sum(areas[n]["other"] for n in names)
    other_men = sum(areas[n]["other_men"] for n in names)
    which = (names[0].title() if len(names) == 1 else
             ", ".join(n.title() for n in names[:-1]) + " and " + names[-1].title())
    several = len(names) > 1
    ground_note = ((" The census areas' ground (OpenStreetMap's outlines" if several else
                    " The census area's ground (OpenStreetMap's outline")
                   + ("; for a governorate's desert, the drawn governorate less every outlined "
                      "area" if b.get("deserts") else "")
                   + ") lies " + ", ".join(f"{b['shares'][n]:.0%}" for n in names)
                   + " inside this polygon" + (", in that order" if several else "")
                   + (f"; other census areas inside it would add some {b['stray']:,.0f} "
                      f"people, at their own areas' average density"
                      if b["stray"] >= 1 else "") + ".")
    both = people(men, women)
    population = measure(total, year=YEAR, source=SOURCE.format(52))
    population["note"] = (f"The 2021 register-based census's habitual residents of {which}: "
                          f"{both}."
                          + (" The sum of the census's areas whose ground this polygon is."
                             if several else "") + ground_note)
    fields: dict[str, Any] = {"population": population}
    if men < MIN_SEX or women < MIN_SEX or total < MIN_PEOPLE:
        fields["sex_ratio"] = gap(NOT_AVAILABLE, (
            f"The census counts {both} here; with fewer than {MIN_SEX} of either, or "
            f"{MIN_PEOPLE} people in all, a ratio says nothing about the place."))
    else:
        fields["sex_ratio"] = sex_ratio(men, women, year=YEAR, source=SOURCE.format(52))
        note = f"Males per 100 females in the 2021 census: {both}."
        if men > SKEWED * women:
            note += (f" A ratio this high is the census's count, not an error: {other_men:,.0f} "
                     f"of the men here are non-Kuwaiti, and Kuwait's non-Kuwaiti residents "
                     f"are {non_kuwaiti_men:,.0f} men and {non_kuwaiti_women:,.0f} women "
                     f"(Table 52's total).")
        fields["sex_ratio_note"] = note
    if total < MIN_PEOPLE:
        fields["ethnicity"] = gap(NOT_AVAILABLE, (
            f"The census counts {total:,.0f} people here ({kuwaiti:,.0f} Kuwaiti); with fewer "
            f"than {MIN_PEOPLE}, a share says nothing about the place."))
    else:
        fields.update(
            ethnicity=nationality_shares(kuwaiti, other, total), ethnicity_year=YEAR,
            ethnicity_basis="nationality",
            ethnicity_note=("Nationality, not ethnicity: Kuwaiti citizens and everyone else, "
                            "as Table 52 counts them. The census counts citizenship and no "
                            "ethnic group, so citizenship is shown here in place of "
                            "ethnicity."))
    return fields


def people(men: float, women: float) -> str:
    """'1 man and 2 women', '7,539 men and 42 women'."""
    return (f"{men:,.0f} {'man' if men == 1 else 'men'} and "
            f"{women:,.0f} {'woman' if women == 1 else 'women'}")


def osm_url(osm_id: str) -> str:
    """'r18005317' -> its page on openstreetmap.org."""
    kind = {"r": "relation", "w": "way", "n": "node"}.get(osm_id[:1])
    return f"https://www.openstreetmap.org/{kind}/{osm_id[1:]}" if kind else \
        "https://www.openstreetmap.org/"


def nationality_shares(kuwaiti: float, other: float, total: float) -> list[dict[str, Any]]:
    """Kuwaitis and everyone else; a group nobody in the area holds is left out."""
    counts = {"Kuwaiti": kuwaiti, "Foreign nationals": other}
    return shares({k: v for k, v in counts.items() if v}, total=total)


def crossing_notes(areas: dict[str, dict[str, Any]], placed: dict[str, dict[str, Any]],
                   admin1: list[dict[str, Any]]) -> dict[str, str]:
    """Drawn governorate label -> a note naming the census areas of another
    governorate whose ground lies mostly inside it."""
    labels = {u["id"]: u["name"] for u in admin1}
    out: dict[str, list[str]] = defaultdict(list)
    for name, p in placed.items():
        s = p.get("admin1") or {}
        if name not in areas or not s:
            continue
        sid, best = max(s.items(), key=lambda kv: kv[1])
        drawn_gov = labels.get(sid)
        census_gov = GOVERNORATES[areas[name]["governorate"]]
        if best >= HOME and drawn_gov and drawn_gov != census_gov:
            out[drawn_gov].append(f"{name.title()} ({areas[name]['total']:,.0f} people), which "
                                  f"the census counts in {census_gov}")
    return {g: " The polygon also holds the ground of " + "; ".join(v) + "." for g, v in
            out.items()}


def build(t1: list[list[Any]], t2: list[list[Any]], t6: list[list[Any]], t52: list[list[Any]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          parents: dict[str, str], placed: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    govs = table1(t1)
    ages = table2(t2)
    groups = table6(t6)
    areas = table52(t52, govs)
    out: list[dict[str, Any]] = []
    drawn1 = {u["name"]: u for u in admin1}
    crossing = crossing_notes(areas, placed, admin1)
    for gov, label in GOVERNORATES.items():
        check(label in drawn1, f"kuwait_census: {label} is not drawn")
        g = govs[gov]
        aged = sum(n for _a, _b, n in ages[gov])
        check(aged == g["total"], f"kuwait_census: {gov}'s age groups make {aged:,.0f}, "
                                  f"not {g['total']:,.0f}")
        grp = groups[gov]
        check(grp["total"] == g["total"], f"kuwait_census: Table 6 {gov} makes "
                                          f"{grp['total']:,.0f}, not {g['total']:,.0f}")
        check(grp["Gulf"] >= g["kuwaiti"], f"kuwait_census: {gov}: fewer Gulf citizens than "
                                           f"Kuwaitis")
        counts = {"Kuwaiti": g["kuwaiti"], "GCC nationals": grp["Gulf"] - g["kuwaiti"]}
        counts.update({lab: grp[k] for k, lab in GROUPS.items() if lab})
        population = measure(g["total"], year=YEAR, source=SOURCE.format(1))
        population["note"] = (f"The 2021 register-based census: {g['men']:,.0f} men and "
                              f"{g['women']:,.0f} women." + crossing.get(label, ""))
        out.append(record(
            f"KWT-CEN2021-{label}", label, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=drawn1[label]["id"],
            aliases=[f"{gov} Governorate"],
            population=population,
            sex_ratio=sex_ratio(g["men"], g["women"], year=YEAR, source=SOURCE.format(1)),
            sex_ratio_note=f"Males per 100 females in the 2021 census: {g['men']:,.0f} men and "
                           f"{g['women']:,.0f} women.",
            median_age=median_age(ages[gov], year=YEAR, source=SOURCE.format(2)),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person, from the 2021 census's count of the governorate by "
                             "five-year age group (Table 2)."),
            ethnicity=shares({k: v for k, v in counts.items() if v}, total=g["total"]),
            ethnicity_year=YEAR, ethnicity_basis="nationality",
            ethnicity_note=(
                "Nationality, not ethnicity: the census counts citizenship and no ethnic "
                "group, so citizenship is shown here in place of ethnicity. "
                "Kuwaitis are Table 1's; GCC nationals are Table 6's Gulf group less the "
                "Kuwaitis; the rest are Table 6's groups of other countries' citizens, its "
                "'Australian' group (the continent's, beside the others) written as "
                "'Oceanian nationalities'."),
            religion=gap(NOT_AVAILABLE, RELIGION_WHY),
            language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
            sources=[{"field": "population/sex_ratio/median_age/ethnicity",
                      "name": SOURCE.format("1, 2 and 6"), "url": PAGE, "year": YEAR,
                      "license": LICENCE}]))
    # Areas.
    bound, why = bind(areas, placed, admin2, parents)
    other_men = sum(a["other_men"] for a in areas.values())
    other_women = sum(a["other_women"] for a in areas.values())
    used: set[str] = set()
    for unit in admin2:
        sid = unit["id"]
        drawn_gov = parents.get(unit["parent"])
        if sid not in bound:
            out.append(record(
                f"KWT-CEN2021-{unit['name']}-{sid[-6:]}", unit["name"], level="admin2",
                parent=ISO3, country=ISO3, parent_name=drawn_gov, match_by="shape_id",
                shape_id=sid,
                median_age=gap(NOT_AVAILABLE, AREA_AGE_WHY),
                religion=gap(NOT_AVAILABLE, RELIGION_WHY),
                language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
                population=dict(gap(NOT_AVAILABLE, why[sid]),
                                displaces_before=DISPLACES_BEFORE, displaces_undated=True),
                **{f: gap(NOT_AVAILABLE, why[sid]) for f in ("sex_ratio", "ethnicity")}))
            continue
        b = bound[sid]
        for n in b["names"]:
            check(n not in used, f"kuwait_census: {n} bound twice")
            used.add(n)
        rec = record(
            f"KWT-CEN2021-{unit['name']}-{sid[-6:]}", unit["name"], level="admin2",
            parent=ISO3, country=ISO3, parent_name=drawn_gov, match_by="shape_id",
            shape_id=sid, aliases=[n.title() for n in b["names"]],
            median_age=gap(NOT_AVAILABLE, AREA_AGE_WHY),
            religion=gap(NOT_AVAILABLE, RELIGION_WHY),
            language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
            **area_fields(b["names"], areas, b, other_men, other_women),
            sources=[{"field": "population/sex_ratio/ethnicity", "name": SOURCE.format(52),
                      "url": PAGE, "year": YEAR, "license": LICENCE},
                     {"field": "placement", "name": OSM_SOURCE,
                      "url": osm_url((placed[b["names"][0]].get("osm") or [""])[0]),
                      "license": "ODbL"}])
        crossed = sorted({GOVERNORATES[areas[n]["governorate"]] for n in b["names"]}
                         - {drawn_gov})
        if crossed:
            rec["population"]["note"] += (" The census counts it in " + " and ".join(crossed)
                                          + ".")
        out.append(rec)
    log(f"  census areas bound: {len(used)} of {len(areas)} "
        f"({sum(areas[n]['total'] for n in used):,.0f} of "
        f"{sum(a['total'] for a in areas.values()):,.0f} people)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--osm", action="store_true",
                    help="measure each census area's ground on the drawn polygons")
    args = ap.parse_args()
    sheets = {k: next(iter(workbook(EXPORT.format(v)).values())) for k, v in TABLES.items()}
    if args.osm or not OSM_FILE.exists():
        measured = measure_ground(table52(sheets["areas"], table1(sheets["nationality"])))
        OSM_FILE.parent.mkdir(parents=True, exist_ok=True)
        OSM_FILE.write_text(json.dumps(measured, ensure_ascii=False, indent=1, sort_keys=True)
                            + "\n", encoding="utf-8")
        log(f"  wrote {OSM_FILE.relative_to(PROCESSED.parent.parent)}")
        if args.osm:
            return 0
    else:
        log(f"  areas' ground as measured on {json.loads(OSM_FILE.read_text())['read']} "
            f"({OSM_FILE.name})")
    placed = json.loads(OSM_FILE.read_text(encoding="utf-8"))["areas"]
    admin1, admin2 = units(ISO3, "admin1"), units(ISO3, "admin2")
    parents = {u["id"]: u["name"] for u in admin1}
    rows = build(sheets["nationality"], sheets["ages"], sheets["groups"], sheets["areas"],
                 admin1, admin2, parents, placed)
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
