#!/usr/bin/env python3
"""European Union -- Eurostat JSON-stat API at NUTS-2 / NUTS-3.

Datasets:

* ``demo_r_pjangrp3``  population on 1 January by age group, sex and NUTS-2
* ``demo_r_d3dens``    population density by NUTS-3
* ``demo_r_pjanind3``  median age and dependency ratios by NUTS-3

Eurostat covers population, age and sex everywhere it reaches, but **not**
ethnicity or religion: those are national census questions and only some member
states ask them.  Romania, Bulgaria, Slovakia and Ireland collect both; France
collects neither (barred by law); Germany collects religion via church-tax
registration but not ethnicity; Spain records co-official language by
autonomous community only.  ``COLLECTION_POLICY`` below is what the app renders
as "not collected" rather than "missing".

Usage:
    python -m scripts.fetch_census.eurostat --level nuts2
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, http_json, log, measure,
    read_json, record, write_json,
)

# Eurostat's own two-letter codes, two of which are not ISO 3166-1 alpha-2.
EUROSTAT_ALPHA2 = {"EL": "GRC", "UK": "GBR"}


def alpha2_to_iso3() -> dict[str, str]:
    """alpha-2 -> alpha-3 from the Natural Earth country index, or the site's own.

    The index lives under data/raw, which is not in git, so on an Actions
    runner it is absent and only the two codes above resolved: a NUTS-3 run
    there skipped every region of every country but Greece and the UK. The
    built site carries each country's ISO2 in its codes, so that is read too.
    """
    out = dict(EUROSTAT_ALPHA2)
    for row in read_json(RAW / "codes" / "country_index.json", []):
        if row.get("iso2"):
            out.setdefault(row["iso2"], row["iso3"])
    site = PROCESSED.parent.parent / "site" / "data" / "admin0.json"
    for row in read_json(site, []) or []:
        codes = row.get("codes") or {}
        if codes.get("iso2") and codes.get("iso3"):
            out.setdefault(codes["iso2"], codes["iso3"])
    return out

API = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
       "{dataset}?format=JSON&lang=EN")

COLLECTION_POLICY: dict[str, dict[str, str]] = {
    "FR": {"ethnicity": "France does not collect ethnicity or religion in its census (statistiques ethniques are barred by law).",
           "religion": "France does not collect religion in its census."},
    "DE": {"ethnicity": "Germany's census records citizenship and migration background, not ethnicity."},
    "ES": {"ethnicity": "Spain's census records nationality and birthplace, not ethnicity.",
           "religion": "Spain's census does not ask religion."},
    "IT": {"ethnicity": "Italy's census records citizenship, not ethnicity."},
    "NL": {"ethnicity": "The Netherlands records migration background, not ethnicity."},
    "SE": {"ethnicity": "Sweden records country of birth and citizenship, not ethnicity."},
    "BE": {"ethnicity": "Belgium does not collect ethnicity; language community is administrative."},
    "DK": {"ethnicity": "Denmark records ancestry and citizenship, not ethnicity."},
    "FI": {"ethnicity": "Finland records native language and citizenship, not ethnicity."},
    "AT": {"ethnicity": "Austria records citizenship and country of birth, not ethnicity."},
    "PL": {"religion": "Poland's 2021 census asked religion on a voluntary basis; sub-national release is limited."},
}
# Eurostat's own region boundaries (GISCO), which place a region on the map by
# its outline where its name and the map's differ -- "Bratislavsky kraj" and
# "Region of Bratislava" -- see scripts/nuts_crosswalk.py.
GISCO = ("https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
         "NUTS_RG_10M_2024_4326_LEVL_{level}.geojson")
GEOMETRY = RAW / "eurostat"
CROSSWALK = PROCESSED / "nuts_crosswalk.json"

COLLECTS_BOTH = {"RO", "BG", "SK", "IE", "HU", "HR", "SI", "LT", "LV", "EE", "CZ", "MK", "RS", "ME", "AL"}


def fetch_geometry() -> None:
    """GISCO's NUTS-2 and NUTS-3 outlines, into data/raw/eurostat (runner)."""
    from ._shared import http_get
    GEOMETRY.mkdir(parents=True, exist_ok=True)
    for level in (2, 3):
        url = GISCO.format(level=level)
        text = http_get(url, cache=False, timeout=600)
        dest = GEOMETRY / url.rsplit("/", 1)[1]
        dest.write_text(text if isinstance(text, str) else text.decode("utf-8"), encoding="utf-8")
        log(f"  {dest.name}: {dest.stat().st_size // 1024} kB")


def bind_by_outline(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into those the outline crosswalk places, and the rest.

    A placed record is bound to its polygon by id, at the level the crosswalk
    found it on; the build then gives it the polygon's own label. A region
    whose polygon is already spoken for by a finer region of the same outline
    (Istanbul is TR10 and TR100) is dropped rather than bound twice, and so is
    one whose outline shows it is a unit and more (Eurostat's Pest is the
    map's Pest without Budapest) -- by name it would land anyway.
    """
    crosswalk = read_json(CROSSWALK, {}) or {}
    # Where GISCO draws a country, its outline is the test: a region that is
    # not one of the map's units by outline is not one by name either. The
    # UK left NUTS 2024, so its regions still go by name.
    outlined = {nuts_id[:2] for nuts_id in crosswalk}
    placed, rest = [], []
    dropped = 0
    for rec in records:
        entry = crosswalk.get(rec["codes"]["nuts"])
        if not entry:
            if rec["codes"]["nuts"][:2] in outlined:
                dropped += 1
            else:
                rest.append(rec)
        elif entry.get("superseded_by") or entry.get("refused"):
            continue
        else:
            rec["level"] = entry["level"]
            rec["match_by"] = "shape_id"
            rec["shape_id"] = entry["shape_id"]
            placed.append(rec)
    if crosswalk:
        log(f"  {len(placed)} regions placed by outline; {dropped} are no one unit by "
            f"outline; {len(rest)} left to their names")
    return placed, rest


def jsonstat(dataset: str, **filters: str) -> dict[str, Any]:
    url = API.format(dataset=dataset)
    for key, val in filters.items():
        url += f"&{key}={val}"
    return http_json(url, timeout=300)


def unpack(payload: dict[str, Any]) -> dict[tuple[str, ...], float]:
    """JSON-stat 2.0 -> {(dim values...): value}, honouring the sparse index."""
    dims = payload["id"]
    sizes = payload["size"]
    categories = [list(payload["dimension"][d]["category"]["index"]) for d in dims]
    values = payload["value"]
    items = values.items() if isinstance(values, dict) else enumerate(values)
    out: dict[tuple[str, ...], float] = {}
    for flat, value in items:
        if value is None:
            continue
        idx = int(flat)
        keys = []
        for size, cats in zip(reversed(sizes), reversed(categories)):
            keys.append(cats[idx % size])
            idx //= size
        out[tuple(reversed(keys))] = float(value)
    return out


def whole_country(geo: str) -> bool:
    """A NUTS code that is its whole country: LU00, LU000, MT00 and the like.

    Eurostat gives a country too small to divide one region at each level,
    coded with zeros. It is not a division of the country, so it has no unit
    on this map; written as one, it went looking for a namesake and Canton
    Luxembourg took all 681,973 of the Grand Duchy's people.
    """
    return len(geo) > 2 and set(geo[2:]) == {"0"}


def by_level(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """NUTS-3 rows at whichever of the map's levels each country's names are.

    NUTS-3 is France's departements and Spain's provinces, which are this
    map's districts; it is also Sweden's counties, Romania's judete and
    Turkey's provinces, which are its first level. So each country's names are
    measured against both of the map's levels, as the COD-PS reader does, and
    each row is written at the level its country's names match. Written as
    districts, a county would look for a district of its name, and Stockholms
    lan could land on Stockholm municipality with the whole county's people;
    left out, as it was, Turkey's 81 provinces had no figure of their own and
    the NUTS-2 regions of two to six provinces stood in for them.
    """
    from .cod_ps import which_level
    by_country: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_country.setdefault(rec["country"], []).append(rec)
    kept: list[dict[str, Any]] = []
    for iso3, rows in sorted(by_country.items()):
        level, why = which_level(iso3, [r["name"] for r in rows])
        if level is None:
            log(f"  {iso3}: {len(rows)} NUTS-3 regions left out -- {why}")
            continue
        for row in rows:
            row["level"] = level
        kept.extend(rows)
        log(f"  {iso3}: {len(rows)} NUTS-3 regions kept at {level} -- {why}")
    return kept


# A region's name split into the units it may be made of: at commas and
# ampersands first, then at "and", then at both -- "Kensington and Chelsea &
# Hammersmith and Fulham" is two boroughs only when split at the ampersand.
SPLITS = (r",\s*|\s*&\s*", r",\s*|\s+and\s+", r",\s*|\s*&\s*|\s+and\s+",
          r"\s+and\s+")


def joined_units(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Leave out a NUTS region that is one of the map's units and more.

    Eurostat's UK regions are often two or three council areas at once --
    "Aberdeen City and Aberdeenshire", "Perth & Kinross and Stirling" -- and
    such a name reaches the first council it starts with. Written there,
    Aberdeen City carried 495,365 people, its own and Aberdeenshire's, and
    Perth and Kinross took Stirling's. A region whose whole name is a drawn
    unit is that unit ("Dumfries & Galloway", "Brighton and Hove"); one that
    only contains a drawn unit's name is that unit and more, and describes
    none of them. The same holds a level up: Turkey's NUTS-2 region TRC2 is
    "Sanliurfa, Diyarbakir", and read as the province it starts with it gave
    Sanliurfa 4,071,429 people and the pair's median age.
    """
    from .cod_ps import level_key, shape_names
    kept: list[dict[str, Any]] = []
    names_by_level: dict[tuple[str, str], set[str]] = {}

    def unit(names: set[str], text: str) -> bool:
        text = re.sub(r"\s*&\s*", " and ", text.strip())
        text = re.sub(r",\s*(City|County) of$", "", text)
        return bool(text) and level_key(text) in names

    for rec in records:
        key = (rec["country"], rec["level"])
        if key not in names_by_level:
            names_by_level[key] = shape_names(*key)
        names = names_by_level[key]
        label = re.sub(r"\s*\(NUTS \d{4}\)\s*$", "", rec["name"]).replace("\xa0", " ")
        if unit(names, label):
            kept.append(rec)
            continue
        inside = sorted({p.strip() for pat in SPLITS for p in re.split(pat, label)
                         if p.strip() and p.strip() != label and unit(names, p)})
        if inside:
            log(f"  {rec['country']}: {rec['name']} left out -- it holds "
                f"{', '.join(inside)} and more")
            continue
        kept.append(rec)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="nuts2", choices=["nuts2", "nuts3"])
    ap.add_argument("--year", default=None, help="reference year; default is the latest available")
    ap.add_argument("--out", default=None)
    ap.add_argument("--fetch-geometry", action="store_true",
                    help="download GISCO's NUTS outlines for scripts/nuts_crosswalk.py and stop")
    args = ap.parse_args()
    if args.fetch_geometry:
        fetch_geometry()
        return 0

    log(f"eurostat: demo_r_pjangrp3 ({args.level})")
    pop_payload = jsonstat("demo_r_pjangrp3", sex="T", age="TOTAL", unit="NR")
    pop = unpack(pop_payload)
    dims = pop_payload["id"]
    geo_pos, time_pos = dims.index("geo"), dims.index("time")
    labels = pop_payload["dimension"]["geo"]["category"]["label"]

    want_len = 4 if args.level == "nuts2" else 5
    latest: dict[str, tuple[str, float]] = {}
    for key, value in pop.items():
        geo, year = key[geo_pos], key[time_pos]
        if len(geo) != want_len or whole_country(geo):
            continue
        if geo not in latest or year > latest[geo][0]:
            latest[geo] = (year, value)

    src = "Eurostat (demo_r_pjangrp3 / demo_r_pjanind3)"
    by_sex: dict[str, dict[str, tuple[str, float]]] = {}
    for sex in ("M", "F"):
        try:
            payload = jsonstat("demo_r_pjangrp3", sex=sex, age="TOTAL", unit="NR")
        except Exception as exc:
            log(f"  population by sex unavailable ({exc})")
            by_sex = {}
            break
        s_dims = payload["id"]
        s_geo, s_time = s_dims.index("geo"), s_dims.index("time")
        for key, value in unpack(payload).items():
            geo, year = key[s_geo], key[s_time]
            held = by_sex.setdefault(sex, {})
            if geo not in held or year > held[geo][0]:
                held[geo] = (year, value)

    def sex_ratio(geo: str) -> Any:
        m, f = by_sex.get("M", {}).get(geo), by_sex.get("F", {}).get(geo)
        if not m or not f or m[0] != f[0] or not f[1]:
            return gap(NOT_AVAILABLE)
        return measure(round(1000 * m[1] / f[1]), unit="males_per_1000_females",
                       year=int(m[0][:4]), source=src)

    try:
        med_payload = jsonstat("demo_r_pjanind3", indic_de="MEDAGEPOP")
        med_raw = unpack(med_payload)
        m_dims = med_payload["id"]
        m_geo, m_time = m_dims.index("geo"), m_dims.index("time")
        median: dict[str, tuple[str, float]] = {}
        for key, value in med_raw.items():
            geo, year = key[m_geo], key[m_time]
            if geo not in median or year > median[geo][0]:
                median[geo] = (year, value)
    except Exception as exc:
        log(f"  median age unavailable ({exc})")
        median = {}

    iso3_of = alpha2_to_iso3()
    records: list[dict[str, Any]] = []
    for geo, (year, value) in sorted(latest.items()):
        country = geo[:2]
        # Without a resolvable ISO3 the join would bucket the record under a
        # junk country and silently match nothing -- the first live run put all
        # 352 rows under "EU-" exactly this way.
        iso3 = iso3_of.get(country)
        if not iso3:
            log(f"  {geo}: no ISO3 for Eurostat country code {country!r}; skipped")
            continue
        policy = COLLECTION_POLICY.get(country, {})
        med = median.get(geo)

        def field(name: str) -> Any:
            if name in policy:
                return gap(NOT_COLLECTED, policy[name])
            if country in COLLECTS_BOTH:
                return gap(NOT_AVAILABLE,
                           f"{country} collects {name} in its national census; "
                           "Eurostat does not redistribute it sub-nationally -- "
                           "fetch from the national statistical office.")
            return gap(NOT_AVAILABLE)

        records.append(record(
            f"EU-{geo}", labels.get(geo, geo),
            level="admin1" if args.level == "nuts2" else "admin2",
            parent=iso3,
            country=iso3,
            codes={"nuts": geo, "nuts_level": want_len - 2},
            population=measure(int(value), year=int(year[:4]), source=src),
            median_age=(measure(med[1], unit="years", year=int(med[0][:4]), source=src)
                        if med else gap(NOT_AVAILABLE)),
            sex_ratio=sex_ratio(geo),
            religion=field("religion"),
            ethnicity=field("ethnicity"),
            sources=[{"field": "population/median age/sex ratio", "name": "Eurostat",
                      "url": API.format(dataset="demo_r_pjangrp3"),
                      "license": "Eurostat re-use policy (attribution)"}],
        ))
    placed, records = bind_by_outline(records)
    if args.level == "nuts3":
        records = by_level(records)
    records = placed + joined_units(records)
    write_json(args.out or PROCESSED / f"eurostat_{args.level}.json", records)
    log(f"  {len(records)} {args.level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
