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
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_json, log, measure,
    record, write_json,
)

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
COLLECTS_BOTH = {"RO", "BG", "SK", "IE", "HU", "HR", "SI", "LT", "LV", "EE", "CZ", "MK", "RS", "ME", "AL"}


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="nuts2", choices=["nuts2", "nuts3"])
    ap.add_argument("--year", default=None, help="reference year; default is the latest available")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

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
        if len(geo) != want_len:
            continue
        if geo not in latest or year > latest[geo][0]:
            latest[geo] = (year, value)

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

    src = "Eurostat (demo_r_pjangrp3 / demo_r_pjanind3)"
    records: list[dict[str, Any]] = []
    for geo, (year, value) in sorted(latest.items()):
        country = geo[:2]
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
            parent=country,
            codes={"nuts": geo, "nuts_level": want_len - 2},
            population=measure(int(value), year=int(year[:4]), source=src),
            median_age=(measure(med[1], unit="years", year=int(med[0][:4]), source=src)
                        if med else gap(NOT_AVAILABLE)),
            religion=field("religion"),
            ethnicity=field("ethnicity"),
            sources=[{"field": "population/median age", "name": "Eurostat",
                      "url": API.format(dataset="demo_r_pjangrp3"),
                      "license": "Eurostat re-use policy (attribution)"}],
        ))
    write_json(args.out or PROCESSED / f"eurostat_{args.level}.json", records)
    log(f"  {len(records)} {args.level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
