#!/usr/bin/env python3
"""Georgia from Geostat's own PC-Axis database: the 2014 census and today's count.

Geostat (the National Statistics Office of Georgia) serves its tables through
PX-Web at pc-axis.geostat.ge. This reads:

* **Population, both levels** -- "Population as of 1 January by regions and
  self-governed units" (Demography/Population, table 01), the office's own
  estimate for the latest 1 January. It covers the territory under the
  government's control: Abkhazia and the Tskhinvali region are not in it.
* **Median age and sex ratio, first level** -- the 2014 census's population by
  region, five-year age group and sex (census table 07). Geostat publishes
  single years of age for the country only, so the median is interpolated
  within the five-year group holding the middle person.
* **Sex ratio, second level** -- the 2014 census's population by self-governed
  unit and sex (census table 02). The census publishes no age by municipality
  beyond three broad groups, so the second level has no median.
* **Ethnicity, religion and native language, first level** -- the 2014
  census's tables 17, 22 and 20 by region. Geostat's database stops at the
  region for all three.

**Units.** The census and the estimate count the self-governing cities --
Batumi, Kutaisi, Poti and Rustavi, and in 2014 also the seven towns merged back
into their municipalities in 2017 (Ozurgeti, Telavi, Mtskheta, Ambrolauri,
Zugdidi, Akhaltsikhe, Gori) -- apart from the municipality around them. The map
draws a polygon for Tbilisi and none for the other four cities, so each one is
drawn inside some municipality's polygon: the polygon that holds the city's
centre (GeoNames), when no other polygon comes within 1.5 km of that centre.
Otherwise the boundary file's outline cannot say which polygon holds the city,
and every polygon that close is left without a figure, with the reason. A town
merged in 2017 goes with its own municipality: the polygon is the municipality
as it has been since.

Abkhazia and the Tskhinvali region (the map's Java and Akhalgori) were not
enumerated in 2014 and are not in the office's estimate; they are written as
gaps saying so.

Usage:
    python -m scripts.fetch_census.georgia
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.parse
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from . import east_geo
from .cod_ps_age import grouped_median
from .pxweb import TIMEOUT


def http_json(url: str, payload: dict | None = None) -> Any:
    """GET, or POST a PX-Web query; Geostat's answers to a POST open with a BOM."""
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8-sig", "replace"))

SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "georgia.json"
BASE = "https://pc-axis.geostat.ge/PXweb/api/v1/en/Database/"
CENSUS = "Population Census 2014/"
SOCIAL = CENSUS + "Demographic And Social Characteristics/"
GEOGRAPHY = CENSUS + "The Geographical Distribution Of The Population And Internal Migration/"
T_POP = "Demography/Population/01-population-by-self-governed-unit.px"
T_AGE = SOCIAL + "07.px"
T_SEX2 = GEOGRAPHY + "02TOTA~1.PX"
T_COMP = {
    "ethnicity": SOCIAL + "17_Total population by regions and ethnicity.px",
    "religion": SOCIAL + "22_Population by regions and religion.px",
    "language": SOCIAL + "20_Population_by_region,_by_native_languages_and_fluently_speak_Georgian....px",
}
CENSUS_YEAR = 2014
SOURCE = "National Statistics Office of Georgia (Geostat), PC-Axis database: {table}"
LICENCE = "Geostat, open publication"
PAGE = "https://pc-axis.geostat.ge/PXweb/pxweb/en/Database/"

# The census's region -> the map's first-level unit.
REGION = {
    "C. Tbilisi": "Tbilisi", "Autonomous Republic of Adjara": "Adjara",
    "Guria": "Guria", "Imereti": "Imereti", "Kakheti": "Kakheti",
    "Mtskheta-Mtianeti": "Mtskheta-Mtianeti",
    "Racha-Lechkhumi and Kvemo Svaneti": "Racha-Lechkhumi and Kvemo Svaneti",
    "Samegrelo-Zemo Svaneti": "Samegrelo-Zemo Svaneti",
    "Samtskhe-Javakheti": "Samtskhe–Javakheti", "Kvemo Kartli": "Kvemo Kartli",
    "Shida Kartli": "Shida Kartli",
}
# The estimate's region rows -> the census's region names.
ESTIMATE_REGION = {
    "C. Tbilisi Municipality": "C. Tbilisi", "Adjara A.R.": "Autonomous Republic of Adjara",
    "Guria Region": "Guria", "Imereti Region": "Imereti", "Kakheti Region": "Kakheti",
    "Mtskheta-Mtianeti Region": "Mtskheta-Mtianeti",
    "Racha-Lechkhumi and Kvemo Svaneti Region": "Racha-Lechkhumi and Kvemo Svaneti",
    "Samegrelo-Zemo Svaneti Region": "Samegrelo-Zemo Svaneti",
    "Samtskhe-Javakheti Region": "Samtskhe-Javakheti", "Kvemo Kartli Region": "Kvemo Kartli",
    "Shida Kartli Region": "Shida Kartli",
}
# Geostat's spelling of a municipality -> the boundary file's, where they differ.
SPELLING = {"tqibuli": "tkibuli", "dedoplistsqaro": "dedoplistskaro", "sighnagi": "sighnaghi",
            "kvareli": "qvareli", "tetritsqaro": "tetrisqaro"}
# The four self-governing cities the map draws no polygon for, with their
# approximate centres (GeoNames).
CITIES = {"batumi": "Batumi", "kutaisi": "Kutaisi", "poti": "Poti", "rustavi": "Rustavi"}
CITY_MARGIN_KM = 1.5
UNCOUNTED = {"Abkhazia", "Gagra", "Gali", "Gudauta", "Gulripshi", "Ochamchire", "Sokhumi",
             "Java", "Akhalgori"}
UNCOUNTED_NOTE = ("Not enumerated: the 2014 census and Geostat's population estimates cover "
                  "the territory under the government's control, and this unit lies in "
                  "{what}, occupied since 1992-1993 and 2008.")

LABELS = {
    "ethnicity": {"Georgians": "Georgian", "Azerbaijanians": "Azerbaijani",
                  "Armenians": "Armenian", "Russians": "Russian", "Ossetians": "Ossetian",
                  "Yezidis": "Yazidi", "Ukrainians": "Ukrainian", "Kists": "Kist",
                  "Greeks": "Greek", "Assyrians": "Assyrian", "Other": "Other",
                  "Refusal": "Not declared", "Not stated": "Not stated"},
    "religion": {"Orthodox": "Orthodox", "Muslim": "Muslim",
                 "Armenian apostolic": "Armenian Apostolic", "Catholic": "Catholic",
                 "Jehovah’s Witnesses": "Jehovah's Witnesses", "Yazidis": "Yazidi",
                 "Protestant": "Protestant", "Judaism": "Judaism", "Other": "Other religion",
                 "None": "No religion", "Refusal": "Not stated", "Not stated": "Not stated"},
    "language": {"Georgian": "Georgian", "Abkhazian": "Abkhaz", "Ossetian": "Ossetian",
                 "Azerbaijanian": "Azerbaijani", "Russian": "Russian", "Armenian": "Armenian",
                 "Other": "Other", "Not stated": "Not stated"},
}
NOTES = {
    "ethnicity": ("Ethnicity (ეროვნება) as each person declared it, 2014 census, everyone "
                  "enumerated in the region. 'Not declared' is those who refused to answer, "
                  "'Not stated' those with no answer recorded. Groups Geostat does not name "
                  "are in 'Other'; cells of ten or fewer people are suppressed and counted "
                  "nowhere, which the note on each region states."),
    "religion": ("Religion (აღმსარებლობა), 2014 census, everyone enumerated in the region. "
                 "'Orthodox' is the census's Orthodox Christianity, overwhelmingly the "
                 "Georgian Orthodox Church. The census's refusals and unrecorded answers "
                 "are together in 'Not stated'."),
    "language": ("Native language (მშობლიური ენა), 2014 census, everyone enumerated in the "
                 "region; the languages Geostat names, the rest in 'Other'."),
}
MEDIAN_NOTE = ("From the 2014 census's population by five-year age group and sex, "
               "interpolated within the group holding the middle person: Geostat publishes "
               "single years of age for the country only.")


def fold(text: str) -> str:
    """A self-governed unit's name for matching: 'C. Telavi*' and 'Telavi
    Municipality' both come to 'telavi'."""
    text = re.sub(r"^C\.\s*", "", str(text).strip())
    text = re.sub(r"\*+$", "", text).strip()
    text = re.sub(r"\s+(Municipality|Region|A\.R\.)$", "", text)
    text = re.sub(r"[^a-z]", "", text.lower())
    return SPELLING.get(text, text)


def number(cell: Any) -> float | None:
    if cell is None:
        return None
    text = str(cell).strip().replace(" ", "")
    if text in ("", "..", "...", "-", "…"):
        return None
    return float(text)


def meta(path: str) -> dict[str, dict[str, Any]]:
    got = http_json(BASE + urllib.parse.quote(path))
    return {v["code"]: v for v in got["variables"]}


def query(path: str, picks: dict[str, list[str]]) -> dict[tuple[str, ...], float | None]:
    """{(value text per variable, in the table's order): figure} for a selection
    given as {variable code: [value texts]} (every value when the list is empty)."""
    variables = meta(path)
    order = list(variables)
    body = {"query": [], "response": {"format": "json"}}
    for code, texts in picks.items():
        v = variables[code]
        by_text = dict(zip(v["valueTexts"], v["values"]))
        wanted = [by_text[t] for t in texts] if texts else v["values"]
        if texts and (missing := [t for t in texts if t not in by_text]):
            raise SystemExit(f"georgia: {path} has no {missing} under {code}")
        body["query"].append({"code": code, "selection": {"filter": "item", "values": wanted}})
    got = http_json(BASE + urllib.parse.quote(path), body)
    names = {code: dict(zip(v["values"], v["valueTexts"])) for code, v in variables.items()}
    columns = [c["code"] for c in got["columns"] if c.get("type") != "c"]
    out = {}
    for row in got["data"]:
        key = tuple(names[code][val] for code, val in zip(columns, row["key"]))
        out[key] = number(row["values"][0])
    log(f"  {path.rsplit('/', 1)[-1]}: {len(out)} cells ({', '.join(columns)})")
    return out


def cite(field: str, table: str, year: int) -> dict[str, Any]:
    return {"field": field, "name": SOURCE.format(table=table), "url": PAGE,
            "license": LICENCE, "year": year}


# ---------------------------------------------------------------------------
# Reading


def estimate() -> tuple[int, dict[str, float]]:
    """The latest 1 January estimate: (year, {row label: population})."""
    variables = meta(T_POP)
    geo = next(c for c in variables if c.startswith("region"))
    year = max(variables["year"]["valueTexts"])
    cells = query(T_POP, {geo: [], "year": [year]})
    return int(year), {key[0]: n for key, n in cells.items() if n is not None}


def ages_by_region() -> dict[str, dict[str, Any]]:
    cells = query(T_AGE, {"Age": [], "Regions": [], "Urban/Rural": ["Total"],
                          "Sex": ["Both sexes", "Males", "Females"]})
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"groups": {}, "sex": {}})
    for (age, region, _, sex), n in cells.items():
        if age == "Total":
            out[region]["sex"][sex] = n or 0.0
        elif sex == "Both sexes":
            out[region]["groups"][age] = n or 0.0
    return out


def age_band(label: str) -> tuple[int, int | None]:
    if m := re.match(r"^(\d+)-(\d+)$", label):
        return int(m.group(1)), int(m.group(2))
    if m := re.match(r"^(\d+)\s*(\+|and over)$", label):
        return int(m.group(1)), None
    raise SystemExit(f"georgia: unreadable age group {label!r}")


def age_values(row: dict[str, Any], name: str) -> dict[str, Any]:
    total, men, women = (row["sex"].get(k) for k in ("Both sexes", "Males", "Females"))
    groups = sorted((*age_band(a), n) for a, n in row["groups"].items())
    made = sum(n for *_, n in groups)
    if not total or abs(made - total) > 0.5 or abs((men or 0) + (women or 0) - total) > 0.5:
        raise SystemExit(f"georgia: {name}'s ages make {made:,.0f} and its sexes "
                         f"{(men or 0) + (women or 0):,.0f}, its total {total}")
    table = "2014 census, population by regions, age and sex (table 07)"
    return {
        "median_age": measure(grouped_median(groups), unit="years", year=CENSUS_YEAR,
                              source=SOURCE.format(table=table)),
        "median_age_note": MEDIAN_NOTE,
        "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                             year=CENSUS_YEAR, source=SOURCE.format(table=table)),
        "sex_ratio_note": f"{int(men):,} men and {int(women):,} women enumerated in 2014.",
    }


def compositions() -> dict[str, dict[str, dict[str, Any]]]:
    """{field: {census region: {"counts": {label: n}, "total": n, "hidden": k}}}."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for field, path in T_COMP.items():
        variables = meta(path)
        geo = "Regions"
        group = next(c for c in variables if c != geo and c not in ("Urban/Rural",
                     "fluently speak Georgian language"))
        picks = {geo: [], group: []}
        for other in ("Urban/Rural", "fluently speak Georgian language"):
            if other in variables:
                picks[other] = ["Total"]
        cells = query(path, picks)
        gi, ri = list(variables).index(group), list(variables).index(geo)
        by_region: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"counts": Counter(), "total": None, "hidden": 0})
        for key, n in cells.items():
            region, label = key[ri], key[gi].strip()
            if region.startswith("…") or region not in REGION and region != "GEORGIA":
                continue
            row = by_region[region]
            if label == "Total":
                row["total"] = n
                continue
            if label not in LABELS[field]:
                raise SystemExit(f"georgia: {field} has a category {label!r} with no label")
            if n is None:
                row["hidden"] += 1
                continue
            row["counts"][LABELS[field][label]] += n
        for region, row in by_region.items():
            made = sum(row["counts"].values())
            if row["total"] is None or made > row["total"] + 0.5 or \
                    row["total"] - made > 10 * row["hidden"] + 0.5:
                raise SystemExit(f"georgia: {field} in {region}: categories make {made:,.0f} "
                                 f"against {row['total']} with {row['hidden']} suppressed")
        out[field] = dict(by_region)
        log(f"  {field}: {len(by_region)} areas; every region's categories make its total "
            "(less its suppressed cells of ten or fewer)")
    return out


def sexes_2014() -> dict[str, dict[str, float]]:
    """{self-governed unit: {"Males": n, "Females": n, "Both sexes": n}}, 2014."""
    variables = meta(T_SEX2)
    geo = next(c for c in variables if "unit" in c.lower() or "self" in c.lower())
    urban = next((c for c in variables if c.lower().startswith("urban")), None)
    sex = next(c for c in variables if c.lower() == "sex")
    picks = {geo: [], sex: []}
    if urban:
        picks[urban] = [variables[urban]["valueTexts"][0]]
    cells = query(T_SEX2, picks)
    order = list(variables)
    gi, si = order.index(geo), order.index(sex)
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for key, n in cells.items():
        label = {"both sexes": "Both sexes", "total": "Both sexes", "males": "Males",
                 "male": "Males", "females": "Females", "female": "Females"}.get(
                     key[si].strip().lower())
        if label and n is not None:
            out[key[gi].strip()][label] = n
    return dict(out)


# ---------------------------------------------------------------------------
# Placing the cities the map draws inside a municipality


def km(a: Any, b: Any) -> float:
    """Degrees of distance to kilometres at Georgia's latitude."""
    return a.distance(b) * 111.32 * math.cos(math.radians(42.0))


def city_homes(polys: dict[str, Any], site: dict[str, dict[str, Any]]) -> tuple[dict, dict]:
    """({city key: polygon id}, {polygon id: reason it is refused})."""
    from shapely.geometry import Point

    places = {east_geo.fold(p["name"]): p for p in east_geo.places("GEO")}
    homes, refused = {}, {}
    for key, name in CITIES.items():
        p = places.get(key)
        if not p:
            raise SystemExit(f"georgia: GeoNames has no {name}")
        point = Point(p["lon"], p["lat"])
        near = sorted((km(geom, point), sid) for sid, (geom, _) in polys.items())
        inside = [sid for d, sid in near if d == 0.0]
        close = [sid for d, sid in near if d <= CITY_MARGIN_KM]
        if len(inside) == 1 and close == inside:
            homes[key] = inside[0]
            log(f"  {name}'s centre lies in {site[inside[0]]['name']!r}; the nearest other "
                f"polygon is {near[1][0]:.1f} km away")
            continue
        names = ", ".join(f"{site[s]['name']} ({d:.1f} km)" for d, s in near[:3])
        log(f"  {name}: not placed; polygons near its centre: {names}")
        for sid in close:
            refused[sid] = (f"The city of {name}, counted apart from every municipality, "
                            "has no polygon of its own on this map, and its centre lies "
                            f"within {CITY_MARGIN_KM} km of more than one: " + names
                            + ". The outline cannot say which polygon holds the city, so "
                            "no figure is written here.")
    return homes, refused


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()

    admin1 = json.loads((SITE / "admin1" / "GEO.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GEO.units.json").read_text())
    first = {u["name"]: u for u in admin1}
    parent = {u["id"]: u["name"] for u in admin1}
    site = {u["id"]: u for u in admin2}
    if missing := [m for m in REGION.values() if m not in first]:
        raise SystemExit(f"georgia: the map has no first-level unit {missing}")

    year, pop = estimate()
    comps = compositions()
    ages = ages_by_region()
    sex2 = sexes_2014()

    # The estimate: regions and their units add up, and the regions make the country.
    country = pop.get("Georgia")
    regions = {ESTIMATE_REGION[k]: v for k, v in pop.items() if k in ESTIMATE_REGION}
    if set(regions) != set(REGION):
        raise SystemExit(f"georgia: the estimate's regions are {sorted(regions)}")
    if abs(sum(regions.values()) - country) > 0.5:
        raise SystemExit(f"georgia: the regions make {sum(regions.values()):,.0f}, the "
                         f"country {country:,.0f}")
    log(f"  estimate for 1 January {year}: {len(regions)} regions make the country's "
        f"{country:,.0f}")

    records: list[dict[str, Any]] = []
    for census, name in REGION.items():
        u = first[name]
        values: dict[str, Any] = {
            "population": measure(int(regions[census]), year=year,
                                  source=SOURCE.format(table="population as of 1 January "
                                                       "by regions and self-governed units")),
            "population_note": (f"Geostat's estimate for 1 January {year}"
                                 + (", for the part of the region under the government's "
                                    "control" if name in ("Shida Kartli", "Mtskheta-Mtianeti")
                                    else "") + "."),
            **age_values(ages[census], name),
        }
        cites = [cite("population", "population as of 1 January by regions and self-governed "
                      "units", year),
                 cite("median_age", "2014 census, table 07", CENSUS_YEAR),
                 cite("sex_ratio", "2014 census, table 07", CENSUS_YEAR)]
        for field in T_COMP:
            row = comps[field][census]
            values[field] = shares(dict(row["counts"]), total=row["total"])
            values[f"{field}_year"] = CENSUS_YEAR
            values[f"{field}_note"] = NOTES[field] + (
                f" {row['hidden']} categories are suppressed in this region "
                f"({row['total'] - sum(row['counts'].values()):,.0f} people)."
                if row["hidden"] else "")
            cites.append(cite(field, f"2014 census, table {T_COMP[field].split('/')[-1][:2]}",
                              CENSUS_YEAR))
        records.append(record(f"GEO-GEOSTAT-{u['id']}", name, level="admin1", parent="GEO",
                              country="GEO", match_by="shape_id", shape_id=u["id"],
                              sources=cites, **values))
    for name in ("Abkhazia",):
        u = first[name]
        why = gap(NOT_AVAILABLE, UNCOUNTED_NOTE.format(what="Abkhazia"))
        records.append(record(f"GEO-GEOSTAT-{u['id']}", name, level="admin1", parent="GEO",
                              country="GEO", match_by="shape_id", shape_id=u["id"],
                              median_age=why, sex_ratio=why, religion=why, language=why,
                              ethnicity=why))

    # Second level: municipalities by name within the map's region, the cities
    # by where their centre lies.
    polys = {sid: g for sid, g in east_geo.polygons("GEO").items() if sid in site}
    homes, refused = city_homes(polys, site)
    by_name: dict[str, str] = {}
    for u in admin2:
        k = fold(u["name"])
        if k in by_name:
            raise SystemExit(f"georgia: two polygons fold to {k!r}")
        by_name[k] = u["id"]
    units: dict[str, list[str]] = defaultdict(list)     # polygon -> estimate rows
    for label in pop:
        if label in ESTIMATE_REGION or label == "Georgia" or label.startswith(("-", "*")):
            continue
        k = fold(label)
        if k in CITIES:
            if k in homes:
                units[homes[k]].append(label)
            continue
        if k in by_name:
            units[by_name[k]].append(label)
        elif label not in ("Abkhazia A.R.", "Ajara Municipality") and not label.endswith("**"):
            log(f"  estimate row {label!r} has no polygon")
    census_units: dict[str, list[str]] = defaultdict(list)
    regions_2014 = set(REGION) | {"Georgia", "GEORGIA"}
    for label in sex2:
        k = fold(label)
        if label in regions_2014 and k != "tbilisi":
            continue
        if k in CITIES:
            if k in homes:
                census_units[homes[k]].append(label)
            continue
        if k in by_name and label not in census_units[by_name[k]]:
            census_units[by_name[k]].append(label)
    # Tbilisi is a region and a self-governed unit at once: counted once.
    for sid, labels in census_units.items():
        totals = [sex2[l].get("Both sexes") for l in labels]
        if len(labels) > 1 and len(set(totals)) < len(totals):
            census_units[sid] = [labels[0]]
    left = []
    for u in admin2:
        sid, name = u["id"], u["name"]
        where = parent[u["parent"]]
        if name in UNCOUNTED:
            why = gap(NOT_AVAILABLE, UNCOUNTED_NOTE.format(
                what="Abkhazia" if where == "Abkhazia" else "the Tskhinvali region"))
            records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                                  country="GEO", match_by="shape_id", shape_id=sid,
                                  population=why, median_age=why, sex_ratio=why,
                                  religion=why, language=why, ethnicity=why))
            continue
        if sid in refused:
            why = gap(NOT_AVAILABLE, refused[sid])
            records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                                  country="GEO", match_by="shape_id", shape_id=sid,
                                  population=why, sex_ratio=why))
            continue
        rows = units.get(sid)
        if not rows:
            left.append(name)
            continue
        values: dict[str, Any] = {}
        cites = []
        parts = " and ".join(rows)
        values["population"] = measure(int(sum(pop[r] for r in rows)), year=year,
                                       source=SOURCE.format(table="population as of 1 "
                                                            "January by regions and "
                                                            "self-governed units"))
        values["population_note"] = (f"Geostat's estimate for 1 January {year}: {parts}"
                                     + (", the city counted apart and drawn inside this "
                                        "polygon" if len(rows) > 1 else "") + ".")
        cites.append(cite("population", "population as of 1 January by regions and "
                          "self-governed units", year))
        crows = census_units.get(sid, [])
        men = sum(sex2[r].get("Males", 0) for r in crows)
        women = sum(sex2[r].get("Females", 0) for r in crows)
        if crows and women:
            values["sex_ratio"] = measure(round(100 * men / women, 1),
                                          unit="males_per_100_females", year=CENSUS_YEAR,
                                          source=SOURCE.format(table="2014 census, population "
                                                               "by self-governed units and "
                                                               "sex (table 02)"))
            values["sex_ratio_note"] = (f"{int(men):,} men and {int(women):,} women "
                                        "enumerated in 2014 in " + " and ".join(crows) + ".")
            cites.append(cite("sex_ratio", "2014 census, table 02", CENSUS_YEAR))
        values["median_age"] = gap(NOT_AVAILABLE, (
            "Geostat publishes no age by municipality beyond the 2014 census's three broad "
            "groups (0-14, 15-64, 65 and over, in its Main Results), from which no median "
            "can be read; its single years of age and five-year groups stop at the region."))
        records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                              country="GEO", match_by="shape_id", shape_id=sid,
                              sources=cites, **values))
    if left:
        log(f"  polygons with no estimate row: {left}")
    # Every estimate row is somewhere: on a polygon, on a refused polygon's
    # city, or in the occupied territories.
    placed = {r for rows in units.values() for r in rows}
    stray = [l for l in pop if l not in placed and l not in ESTIMATE_REGION
             and l != "Georgia" and fold(l) not in CITIES and pop[l]]
    log(f"  second level: {sum(1 for r in records if r['level'] == 'admin2' and isinstance(r.get('population'), dict) and 'value' in r['population'])} "
        f"polygons with a count; rows on no polygon: {stray}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
