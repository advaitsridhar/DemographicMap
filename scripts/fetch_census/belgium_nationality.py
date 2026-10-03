#!/usr/bin/env python3
"""Belgium: nationality as ethnicity, by region and province, from the 2021 census.

Belgium's census asks no ethnicity question; its register-based census of 1
January 2021 counts citizenship. By the owner's decision of 19 September
2026 that count is carried on the ethnicity field under ``ethnicity_basis:
"nationality"`` (see ``central_nationality``).

**What is read.** Statbel's own pages sit behind a challenge page that asks a
browser to prove it is human, which this project does not get around. The
same census counts are Statbel's transmission to Eurostat's 2021 Census Hub,
dataset ``cens_21ctz_r3``: the population by country of citizenship (every
country, the stateless and the unknown) by NUTS region. The map's second
level is Belgium's eleven provinces, which are NUTS 2 (Brussels-Capital among
them), and its first is the three regions, NUTS 1, so each polygon is read at
its own code: nothing is summed and nothing split.

**Checks.** Every region's countries, stateless and unknown make its total;
the provinces make their regions and the regions the country; the citizenship
categories with at least ``NAMED_SHARE`` of Belgium's people are named and the
rest of each unit is "Other nationalities".

Usage:
    python -m scripts.fetch_census.belgium_nationality
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from typing import Any

from ._shared import PROCESSED, http_json, log, record, write_json
from .central_ages import check_sum, fold, units
from .central_nationality import ISO2, composition, named, note
from .eurostat import unpack

DATASET = "cens_21ctz_r3"
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/" + DATASET
PAGE = "https://ec.europa.eu/eurostat/databrowser/view/" + DATASET + "/default/table"
SOURCE = ("Statbel, Census 2021 (1 January 2021), population by country of citizenship, as "
          "transmitted to Eurostat's 2021 Census Hub (cens_21ctz_r3)")
LICENCE = "Eurostat (free reuse with attribution)"
OUT = PROCESSED / "belgium_nationality.json"
YEAR = 2021
NAMED_SHARE = 0.004
# NUTS code -> the map's name for it, at the level the map draws it.
REGIONS = {"BE1": "Brussels Hoofdstedelijk", "BE2": "Vlaams Gewest", "BE3": "Wallonne Gewest"}
PROVINCES = {"BE10": "Brussels", "BE21": "Antwerpen", "BE22": "Limburg",
             "BE23": "Oost-Vlaanderen", "BE24": "Vlaams-Brabant", "BE25": "West-Vlaanderen",
             "BE31": "Waals-Brabant", "BE32": "Henegouwen", "BE33": "Luik",
             "BE34": "Luxemburg", "BE35": "Namen"}


def leaf(code: str) -> bool:
    """A citizenship category that partitions the population: a country (the
    Belgians, "NAT" in the Census Hub, are read as "BE"), a continent's
    remainder ("AFR_OTH"), the stateless or the unknown. The groups (FOR,
    EU_FOR, NEU, AFR, ...) and the total are sums of these."""
    return bool(re.fullmatch(r"[A-Z]{2}", code)) or code.endswith("_OTH") or code in ("STLS", "UNK")


def read() -> dict[str, dict[str, float]]:
    """{NUTS code: {citizenship code: people}} for Belgium and its regions and provinces."""
    geos = ["BE", *REGIONS, *PROVINCES]
    params = [("format", "JSON"), ("lang", "EN"), ("sex", "T"), ("age", "TOTAL")] + [("geo", g) for g in geos]
    payload = http_json(API + "?" + urllib.parse.urlencode(params), timeout=300)
    dims = payload["id"]
    log(f"  {DATASET}: dimensions {dims}, sizes {payload['size']}")
    fixed = {d: payload["dimension"][d]["category"]["index"] for d in dims}
    # Every dimension but citizenship and geography must be down to its total.
    for d in dims:
        if d in ("citizen", "geo", "time", "freq"):
            continue
        cats = list(fixed[d])
        if cats not in (["T"], ["TOTAL"], ["NR"], ["PER"]):
            raise SystemExit(f"belgium_nationality: dimension {d} has {cats[:6]}; asked for totals")
    i_geo, i_cit = dims.index("geo"), dims.index("citizen")
    out: dict[str, dict[str, float]] = {}
    for key, value in unpack(payload).items():
        out.setdefault(key[i_geo], {})[key[i_cit]] = value
    # The Census Hub counts the reporting country's own citizens as "NAT",
    # not under its country code.
    for geo, counts in out.items():
        if "NAT" in counts:
            if counts.get("BE"):
                raise SystemExit(f"belgium_nationality: {geo} counts Belgians both as NAT and BE")
            counts["BE"] = counts.pop("NAT")
    return out


def check(table: dict[str, dict[str, float]]) -> None:
    for geo, counts in table.items():
        total = counts.get("TOTAL")
        leaves = sum(v for c, v in counts.items() if leaf(c))
        if total is None or abs(leaves - total) > max(2, 0.0005 * total):
            raise SystemExit(f"belgium_nationality: {geo}: the citizenship categories make "
                             f"{leaves:,.0f}, the total is {total}")
    check_sum((table[g]["TOTAL"] for g in REGIONS), table["BE"]["TOTAL"], "regions against Belgium")
    for region in REGIONS:
        check_sum((table[p]["TOTAL"] for p in PROVINCES if p.startswith(region)),
                  table[region]["TOTAL"], f"provinces against {region}")


def build() -> list[dict[str, Any]]:
    log(f"belgium_nationality: Eurostat {DATASET}, Belgium, 1 January {YEAR}")
    table = read()
    missing = [g for g in ("BE", *REGIONS, *PROVINCES) if g not in table]
    if missing:
        raise SystemExit(f"belgium_nationality: {DATASET} has no rows for {missing}")
    check(table)
    national = {c: v for c, v in table["BE"].items() if leaf(c)}
    total = table["BE"]["TOTAL"]
    labels = {c: ISO2.get(c) for c in national}
    names = named(national, total, labels, share=NAMED_SHARE, always=["BE"])
    log(f"  named: {', '.join(str(labels[n]) for n in names)}")
    text = note("Population by country of citizenship", "1 January 2021",
                "the register-based census's count of each resident's citizenship (Statbel, "
                "Census 2021, through Eurostat's Census Hub)",
                extra="Belgians with a second citizenship are counted as Belgian.")
    sources = [{"field": "ethnicity", "name": SOURCE, "url": PAGE, "license": LICENCE,
                "year": YEAR}]
    records = []
    for level, codes in (("admin1", REGIONS), ("admin2", PROVINCES)):
        shapes = units("BEL", level)
        for code, name in codes.items():
            hits = [s for s in shapes if fold(s["name"]) == fold(name)]
            if len(hits) != 1:
                raise SystemExit(f"belgium_nationality: {name!r} meets {[h['name'] for h in hits]}")
            counts = {c: v for c, v in table[code].items() if leaf(c)}
            records.append(record(
                f"BEL-NUTS-{code}-nat", hits[0]["name"], level=level,
                parent="BEL" if level == "admin1" else hits[0]["parent"], country="BEL",
                codes={"nuts": code}, match_by="shape_id", shape_id=hits[0]["id"],
                sources=sources,
                ethnicity=composition(counts, table[code]["TOTAL"], names, labels, where=name),
                ethnicity_year=YEAR, ethnicity_basis="nationality", ethnicity_note=text))
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
