#!/usr/bin/env python3
"""Natural Earth (public domain, CC0) -- code concordance, cities, fallback geometry.

Natural Earth does three jobs in this pipeline that geoBoundaries cannot:

1. **Code concordance.** The Factbook keys everything by two-letter GEC
   (ex-FIPS 10-4) codes; geoBoundaries keys everything by ISO 3166-1 alpha-3.
   ``ne_10m_admin_0_countries`` carries both (``FIPS_10``/``FIPS_10_`` and
   ``ISO_A3``), so it is the join table between them.
2. **Largest settlement.** ``ne_10m_populated_places`` gives a populated-place
   point with ``POP_MAX`` plus its ADM0 and ADM1 names, which yields a real
   largest-city value for countries *and* first-level subdivisions.
3. **Fallback geometry** for admin-0/admin-1 when geoBoundaries is unreachable.

Usage:
    python scripts/fetch_natural_earth.py [--scale 10m] [--geometry]
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PROCESSED, RAW, download, log, write_json  # noqa: E402

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
DEST = RAW / "naturalearth"

# Genuine GEC/name mismatches Natural Earth cannot resolve on its own.
# Keys are the file stems used by the factbook.json mirror (mostly GEC, but the
# mirror has migrated a handful of entities to ISO-style codes).
def norm(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).strip().lower()


def load(name: str) -> dict[str, Any]:
    path = download(f"{BASE}/{name}.geojson", DEST / f"{name}.geojson")
    return json.loads(path.read_text(encoding="utf-8"))


# SOVEREIGNT/SUBUNIT are deliberately excluded: Anguilla's SOVEREIGNT is
# "United Kingdom" and French Southern Territories' is "France", so indexing
# them would let a dependency answer to its parent's name.
NAME_FIELDS = ("NAME_EN", "NAME", "NAME_LONG", "ADMIN", "FORMAL_EN", "BRK_NAME",
               "GEOUNIT", "NAME_SORT")


def build_country_index(countries: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per Natural Earth country carrying every code and name variant.

    Downstream scripts resolve their own keys (Factbook GEC stems, census FIPS,
    Eurostat NUTS-0) against this index rather than against a hand-written map,
    so a new entity only needs a name that Natural Earth already knows.
    """
    rows: list[dict[str, Any]] = []
    for feat in countries["features"]:
        p = feat["properties"]
        iso3 = (p.get("ISO_A3_EH") or p.get("ISO_A3") or p.get("ADM0_A3") or "").strip().upper()
        if not iso3 or iso3 == "-99":
            continue
        iso2 = (p.get("ISO_A2_EH") or p.get("ISO_A2") or "").strip().upper()
        fips = (p.get("FIPS_10") or p.get("FIPS_10_") or "").strip().upper()
        names = []
        for field in NAME_FIELDS:
            value = p.get(field)
            if isinstance(value, str) and value and value != "-99":
                names.append(value)
        lon, lat = p.get("LABEL_X"), p.get("LABEL_Y")
        rows.append({
            "iso3": iso3,
            "type": p.get("TYPE"),
            "sovereign": bool(p.get("ADM0_A3") == iso3 or p.get("TYPE") == "Sovereign country"),
            "iso2": iso2 if iso2 not in {"", "-99"} else None,
            "fips": fips if len(fips) == 2 else None,
            "continent": p.get("CONTINENT"),
            "subregion": p.get("SUBREGION"),
            "names": sorted(set(names)),
            "label_point": [lon, lat] if isinstance(lon, (int, float)) else None,
        })
    rows.sort(key=lambda r: r["iso3"])
    return rows


def build_cities(places: dict[str, Any]) -> dict[str, Any]:
    """Largest populated place per country and per ``ISO3||admin-1 name``."""
    by_country: dict[str, dict[str, Any]] = {}
    by_admin1: dict[str, dict[str, Any]] = {}
    for feat in places["features"]:
        p = feat["properties"]
        iso3 = (p.get("ADM0_A3") or p.get("SOV_A3") or "").upper()
        pop = p.get("POP_MAX") or p.get("POP_MIN") or 0
        name = p.get("NAME_EN") or p.get("NAME") or p.get("NAMEASCII")
        if not iso3 or not name or not pop:
            continue
        lon, lat = feat["geometry"]["coordinates"][:2]
        entry = {"name": name, "population": int(pop),
                 "coordinates": [round(lon, 5), round(lat, 5)],
                 "source": "Natural Earth populated places (CC0)"}
        if pop > by_country.get(iso3, {}).get("population", -1):
            by_country[iso3] = entry
        adm1 = p.get("ADM1NAME")
        if adm1:
            key = f"{iso3}||{norm(adm1)}"
            if pop > by_admin1.get(key, {}).get("population", -1):
                by_admin1[key] = entry
    return {"by_country": by_country, "by_admin1": by_admin1}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scale", default="10m", choices=["10m", "50m", "110m"])
    ap.add_argument("--geometry", action="store_true",
                    help="also download admin-0/1 geometry as a geoBoundaries fallback")
    args = ap.parse_args()

    log("fetch_natural_earth: countries")
    countries = load(f"ne_{args.scale}_admin_0_countries")
    index = build_country_index(countries)
    write_json(RAW / "codes" / "country_index.json", index)

    log("fetch_natural_earth: populated places")
    places = load(f"ne_{args.scale}_populated_places")
    cities = build_cities(places)
    write_json(PROCESSED / "cities.json", cities, compact=True)
    log(f"  {len(index)} countries indexed | {len(cities['by_country'])} with cities "
        f"| {len(cities['by_admin1'])} admin-1 largest cities")

    if args.geometry:
        load(f"ne_{args.scale}_admin_1_states_provinces")
        log("  admin-0/1 fallback geometry cached under data/raw/naturalearth/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
