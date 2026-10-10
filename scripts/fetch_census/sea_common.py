"""Pieces the Southeast Asian age readers share: the drawn units, a median, a ratio.

Every reader in this family turns an office's count of people by age and sex
into the two figures the map shows, binds the office's units to the polygons
the map draws, and checks its sums on the way. What is common to all of them
is here, so that a median is interpolated, and a ratio rounded, one way
everywhere:

* ``drawn(iso3, level)`` -- the map's units under the boundary file's own
  labels (``common.as_drawn``), which is what an office's names are matched
  against; a rebuild renames a polygon after the census row bound to it, and
  matching on that name would move the ground under the matching.
* ``single_median`` -- the median of single years of age, interpolated within
  the year holding the middle person (``redatam.median_age``), the open top
  class given as the last key.
* ``grouped`` -- the same from five-year groups, interpolated within the group
  (``cod_ps_age.grouped_median``), for an office that publishes nothing finer.
* ``ratio`` -- males per 100 females, to one decimal.
* ``age_sex`` -- the record fields for one unit, notes and provenance included.
* ``html_rows`` -- every table of an HTML page as rows of cell texts.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from typing import Any

from ._shared import PROCESSED, measure
from .cod_ps_age import grouped_median
from .redatam import median_age

SITE = PROCESSED.parent.parent / "site" / "data"


def drawn(iso3: str, level: str) -> list[dict[str, Any]]:
    """The map's units at ``level``, each under the boundary file's own label."""
    from common import as_drawn  # noqa: PLC0415 -- scripts/ is on the path via _shared
    return as_drawn(json.loads((SITE / level / f"{iso3}.units.json").read_text()))


def fold(text: Any) -> str:
    """A name reduced to its lower-case letters and digits, without accents."""
    text = unicodedata.normalize("NFKD", str(text or "").lower()).replace("đ", "d")
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def single_median(ages: Counter) -> float | None:
    """The median of a count by single year of age; the open top class last."""
    return median_age(ages)


def grouped(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median of ``(low, high, people)`` groups; None if it falls in the open one."""
    return grouped_median(sorted(groups, key=lambda g: g[0]))


def ratio(men: float, women: float) -> float | None:
    """Males per 100 females, to one decimal."""
    return round(100.0 * men / women, 1) if women else None


def age_sex(*, median: float | None, men: float, women: float, year: int, source: str,
            median_note: str, ratio_note: str, population: int | None = None,
            population_note: str | None = None) -> dict[str, Any]:
    """The record fields for one unit's median age, sex ratio and (optionally) population."""
    out: dict[str, Any] = {}
    if median is not None:
        out["median_age"] = measure(median, unit="years", year=year, source=source)
        out["median_age_note"] = median_note
    if women:
        out["sex_ratio"] = measure(ratio(men, women), unit="males_per_100_females",
                                   year=year, source=source)
        out["sex_ratio_note"] = ratio_note
    if population is not None:
        out["population"] = measure(population, year=year, source=source)
        if population_note:
            out["population_note"] = population_note
    return out


def check_runs(groups: list[tuple[int, int | None, float]], where: str) -> None:
    """Groups that start at 0 and climb without a gap to one open top group."""
    edge = 0
    for i, (low, high, _) in enumerate(sorted(groups, key=lambda g: g[0])):
        if low != edge:
            raise SystemExit(f"{where}: age groups jump to {low} where {edge} was due")
        if high is None:
            if i != len(groups) - 1:
                raise SystemExit(f"{where}: an open age group before the last")
            return
        edge = high + 1
    raise SystemExit(f"{where}: no open top age group")


def polygons(level: str, iso3: str, zoom: int = 7) -> dict[str, Any]:
    """The map's own polygons for one country and level, read from its tiles.

    ``site/tiles/<level>.pmtiles`` is what the map draws, and its features
    carry the boundary file's ``shapeID``, the same id as the units files.
    Reading them is how a reader learns which drawn unit contains another, or
    a place, where the boundary file's own parent is unreliable. Zoom 7 keeps
    every polygon at a resolution of some 600 m, enough to place a district's
    representative point or a town and nothing finer.
    """
    import gzip
    import math

    import mapbox_vector_tile
    from pmtiles.reader import MmapSource, Reader
    from shapely.geometry import shape
    from shapely.ops import unary_union

    units = {u["id"]: u for u in drawn(iso3, level)}
    boxes = [u["bbox"] for u in units.values() if u.get("bbox")]
    west, south = min(b[0] for b in boxes), min(b[1] for b in boxes)
    east, north = max(b[2] for b in boxes), max(b[3] for b in boxes)

    def tile(lon: float, lat: float) -> tuple[int, int]:
        n = 2 ** zoom
        lat = max(min(lat, 85.0), -85.0)
        y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat)))
             / math.pi) / 2 * n
        return int((lon + 180) / 360 * n), int(y)

    def lonlat(px: float, py: float, x: int, y: int, extent: int) -> tuple[float, float]:
        n = 2 ** zoom
        yy = (y + py / extent) / n
        return ((x + px / extent) / n * 360 - 180,
                math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy)))))

    path = SITE.parent / "tiles" / f"{level}.pmtiles"
    parts: dict[str, list[Any]] = {}
    with open(path, "rb") as fh:
        reader = Reader(MmapSource(fh))
        x0, y1 = tile(west, south)
        x1, y0 = tile(east, north)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                data = reader.get(zoom, x, y)
                if not data:
                    continue
                try:
                    data = gzip.decompress(data)
                except OSError:
                    pass
                decoded = mapbox_vector_tile.decode(data, default_options={"y_coord_down": True})
                for layer in decoded.values():
                    extent = layer.get("extent", 4096)
                    for feat in layer["features"]:
                        sid = str(feat["properties"].get("shapeID"))
                        if sid not in units:
                            continue

                        def conv(c: Any) -> Any:
                            if isinstance(c[0], (int, float)):
                                return lonlat(c[0], c[1], x, y, extent)
                            return [conv(v) for v in c]

                        g = feat["geometry"]
                        geom = shape({"type": g["type"], "coordinates": conv(g["coordinates"])})
                        parts.setdefault(sid, []).append(geom.buffer(0))
    return {sid: unary_union(gs) for sid, gs in parts.items()}


def locate(points: dict[Any, tuple[float, float]], level: str, iso3: str,
           zoom: int = 7) -> dict[Any, str | None]:
    """Each (lon, lat) -> the id of the one drawn unit at ``level`` containing it,
    or None where none or several do."""
    from shapely.geometry import Point
    shapes = polygons(level, iso3, zoom)
    out: dict[Any, str | None] = {}
    for key, (lon, lat) in points.items():
        hits = [sid for sid, geom in shapes.items() if geom.contains(Point(lon, lat))]
        out[key] = hits[0] if len(hits) == 1 else None
    return out


AGE_LABEL = re.compile(r"^\s*(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*$")
OPEN_LABEL = re.compile(r"^\s*(\d{1,3})\s*(?:\+|and over|& over|and above|years and over"
                        r"|or more|plus|over)\s*$", re.IGNORECASE)


def band(label: Any) -> tuple[int, int | None] | None:
    """'15-19' -> (15, 19); '85+' / '85 and over' -> (85, None); 'Under 1' -> (0, 0)."""
    text = str(label or "").strip()
    if re.fullmatch(r"(?i)under\s*1|less than 1|<\s*1|0", text):
        return (0, 0)
    if m := AGE_LABEL.match(text):
        return int(m.group(1)), int(m.group(2))
    if m := OPEN_LABEL.match(text):
        return int(m.group(1)), None
    if re.fullmatch(r"\d{1,3}", text):
        return int(text), int(text)
    return None


def html_rows(body: bytes) -> list[list[list[str]]]:
    """Every <table> of a page as rows of cell texts, nested tables kept apart."""
    from html.parser import HTMLParser

    class Rows(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.stack: list[list[list[str]]] = []
            self.done: list[list[list[str]]] = []
            self.cell: list[str] | None = None

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            if tag == "table":
                self.stack.append([])
            elif tag == "tr" and self.stack:
                self.stack[-1].append([])
            elif tag in ("td", "th") and self.stack:
                if not self.stack[-1]:
                    self.stack[-1].append([])
                self.cell = []

        def handle_endtag(self, tag: str) -> None:
            if tag in ("td", "th") and self.cell is not None and self.stack:
                self.stack[-1][-1].append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "table" and self.stack:
                self.done.append(self.stack.pop())

        def handle_data(self, data: str) -> None:
            if self.cell is not None:
                self.cell.append(data)

    for encoding in ("utf-8", "tis-620", "cp874", "latin-1"):
        try:
            text = body.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    parser = Rows()
    parser.feed(text)
    return parser.done
