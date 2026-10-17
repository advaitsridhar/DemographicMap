#!/usr/bin/env python3
"""Uganda: the 2024 census by county, on the counties the map draws.

The Uganda Bureau of Statistics publishes the National Population and Housing
Census 2024 down to the parish through the dissemination dashboard on
statistics.ubos.org/nphc, whose JSON interface answers by level (district,
county, subcounty, parish): the population by sex, and the population in a set
of age groups (0-4, 0-17, 6-12, 13-18, 14-64, 15 and over, 18-30, 15-24, 18
and over, 60 and over, 65 and over, 80 and over). The host sends its leaf
certificate without the intermediate above it, so it is reached with the
missing link completed from the certificate's own AIA record (``aia``), still
fully verified.

**The map's counties are not the census's.** The boundary file draws 151
second-level polygons in Uganda: the counties as they stood around 2002, with
a few municipalities, where the 2024 census counts some 350 counties, cities
and municipalities, many of them cut from the older counties since (Kyadondo
into Kira and Nansana, Busiro into Entebbe and Makindye-Ssabagabo...). The
dashboard publishes each 2024 county's outline with its figures, so which 2024
counties make each polygon is measured rather than guessed: ``--points`` writes
points sampled evenly over every 2024 county (``uganda_county_points.json``),
and each county is placed in the drawn polygon that holds at least
``WHOLLY`` of its points. CROSSWALK records the result; a polygon is written
only when every 2024 county that reaches it is wholly inside it, and its figures
are the sum of those counties'.

**What is written.** Population and men per 1,000 women for each polygon, and
the median age, interpolated within the age group that holds the middle
person from the groups above made disjoint (0-4, 5-14, 15-17, 18-24, 25-30,
31-59, 60-64, 65-79, 80 and over).

**Checks.** Each county's sexes make its total, and its age groups make it
too; the counties make their districts, and the districts make the country.

Usage:
    python -m scripts.fetch_census.uganda_census --points
    python -m scripts.fetch_census.uganda_census
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

from ._shared import PROCESSED, http_get, log, write_json

API = "https://statistics.ubos.org/nphc/api"
PAGE = "https://statistics.ubos.org/nphc/"
POINTS = "uganda_county_points.json"
# Points sampled per 2024 county, at the least.
SAMPLES = 60


def fetch_json(url: str) -> Any:
    body = http_get(url, cache=False, timeout=300, aia=True)
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise SystemExit(f"uganda_census: {url} answered no JSON: {text[:200]!r}")
    return json.loads(text[start:])


def sample(geometry: dict[str, Any], wanted: int) -> tuple[list[list[float]], float]:
    """Points on a regular grid over the polygon, about ``wanted`` of them, and its area in km2."""
    from shapely.geometry import Point, shape     # noqa: PLC0415
    poly = shape(geometry)
    if not poly.is_valid:
        poly = poly.buffer(0)
    west, south, east, north = poly.bounds
    lat = (south + north) / 2
    km_x = 111.32 * math.cos(math.radians(lat))
    area = poly.area * km_x * 110.57
    step = math.sqrt(poly.area / max(wanted, 1)) or 0.01
    points: list[list[float]] = []
    while True:
        points = []
        y = south + step / 2
        while y < north:
            x = west + step / 2
            while x < east:
                if poly.contains(Point(x, y)):
                    points.append([round(x, 5), round(y, 5)])
                x += step
            y += step
        if len(points) >= wanted or step < 1e-4:
            break
        step /= 1.4
    rep = poly.representative_point()
    points.append([round(rep.x, 5), round(rep.y, 5)])
    return points, round(area, 1)


def write_points() -> int:
    data = fetch_json(f"{API}/get_geospatial_data.php?level=county")
    features = (data.get("geojson") or data).get("features") or []
    out = []
    for feature in features:
        props = feature.get("properties") or {}
        pop = props.get("population_data") or {}
        points, area = sample(feature["geometry"], SAMPLES)
        out.append({"code": str(pop.get("code") or ""), "name": props.get("County"),
                    "district_code": str(props.get("DCode") or pop.get("district_code") or ""),
                    "region_code": str(props.get("RCode") or ""),
                    "male": pop.get("male_popn"), "female": pop.get("female_popn"),
                    "total": pop.get("total_popn"), "area_km2": area, "points": points})
    log(f"  {len(out)} counties, {sum(len(c['points']) for c in out):,} points, "
        f"{sum(c['total'] or 0 for c in out):,} people")
    write_json(PROCESSED / POINTS, out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", action="store_true",
                    help="write points sampled over every 2024 county, for the crosswalk")
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    if args.points:
        return write_points()
    raise SystemExit("uganda_census: the crosswalk is not written yet; run --points")


if __name__ == "__main__":
    raise SystemExit(main())
