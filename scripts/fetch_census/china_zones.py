#!/usr/bin/env python3
"""Where China's development zones stand: their townships, placed among the drawn county polygons.

A provincial census yearbook counts a development zone, a new area or a
management district (开发区, 新区, 管理区; codes ending 71 to 80) apart from the
counties and districts whose ground it holds, so a county row beside one may
be short of the ground its polygon draws. ``china_county_census`` refuses a
county only where such a unit stands on its polygon, and this finds where each
one stands: its townships (乡级单位) as the National Bureau of Statistics'
statistical division codes list them (统计用区划代码), and each township's own
point -- Wikidata's coordinates for the item carrying its code, or failing
that its name in the same prefecture (``data/raw/wikidata_points/CHN_P442.json``).
Wikidata names no figure here; it only says where a township's seat stands.

**The listing.** The Bureau no longer serves any edition of the codes (its
pages answer 404) and the Internet Archive kept only a handful of the zones'
pages, so the listing is read from the open transcription of the codes that
modood/Administrative-divisions-of-China keeps on GitHub, at the commit that
carries the 2020 edition -- the division of 30 June 2020, four months before
the census -- and checked, zone by zone, against every page of the Bureau's
own that the Archive holds for that edition (``CHECKS``): a page that differs
from the transcription stops the run. Wikidata's items carrying a zone's code
are added to its townships, so a township a zone held under an older edition
is placed too; a zone only ever gains refusals by it.

Two steps, because the first needs the network and the second the boundary
file (``data/raw/boundaries``, not in git and not on the runner):

    python -m scripts.fetch_census.china_zones --fetch 22,32,63,15,37   # runner
        -> data/processed/china_zone_townships.json
    python -m scripts.fetch_census.china_zones --place                  # boundaries
        -> data/raw/wikidata_points/CHN_zone_ground.json: each zone township's
           point, the polygon it stands in and the polygons within NEAR of it
        -> data/raw/wikidata_points/CHN_township_ground.json: the same for every
           township of every county-level unit of those provinces, which
           ``china_county_census`` holds a county's polygon to: its own townships
           in it, and no other unit's township inside it

A township no point can be found for is written without one, and the reader
treats its zone, and so its prefecture, as one it cannot place.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, RAW, http_get, log

LISTING = PROCESSED / "china_zone_townships.json"
GROUND = RAW / "wikidata_points" / "CHN_zone_ground.json"
TOWNS = RAW / "wikidata_points" / "CHN_township_ground.json"
POINTS = RAW / "wikidata_points" / "CHN_P442.json"
UNITS = Path(__file__).resolve().parents[2] / "site" / "data" / "admin2" / "CHN.units.json"
CDX = "https://web.archive.org/cdx/search/cdx"
REPLAY = "https://web.archive.org/web/{stamp}id_/{url}"
PAUSE = 4                     # seconds between two requests to the Internet Archive
MIRROR = ("https://raw.githubusercontent.com/modood/Administrative-divisions-of-China/"
          "{ref}/dist/{name}")
# The commit "数据更新（截止时间：2020-06-30，发布时间：2020-11-06）": the Bureau's
# 2020 edition, the division of 30 June 2020, published 6 November 2020.
MIRROR_REF = "78b6f36127ff8dc8e6ca3d82e43ab10619b553d2"
EDITION = "2020"
TRANSCRIPTION = ("the National Bureau of Statistics' statistical division codes, {edition} "
                 "edition, as transcribed by modood/Administrative-divisions-of-China")
# The Bureau's own pages for a zone that the Internet Archive kept: (edition,
# address). Each one of the edition read is compared with the transcription.
CHECKS = (
    ("2020", "http://www.stats.gov.cn/tjsj/tjbz/tjyqhdmhcxhfdm/2020/32/05/320571.html"),
    ("2021", "http://www.stats.gov.cn/tjsj/tjbz/tjyqhdmhcxhfdm/2021/22/08/220871.html"),
    ("2023", "https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/32/07/320771.html"),
    ("2023", "https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/15/25/152571.html"),
    ("2023", "https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/37/07/370772.html"),
    ("2023", "https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/37/10/371071.html"),
    ("2023", "https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/37/17/371771.html"),
    ("2023", "https://www.stats.gov.cn/sj/tjbz/tjyqhdmhcxhfdm/2023/37/17/371772.html"),
)
# A township's point is held to touch every polygon within this distance of
# it (degrees; about 3 km): the boundary file's lines are generalised, and a
# township is ground around its seat, not the seat alone.
NEAR = 0.03


def is_zone(code: str) -> bool:
    """A county-level code the Bureau gives a development zone or another
    special unit: its fifth and sixth figures 71 to 80."""
    return len(code) >= 6 and code[4:6].isdigit() and 71 <= int(code[4:6]) <= 80


# ---------------------------------------------------------------------------
# Reading the listing
# ---------------------------------------------------------------------------

def rows_of(page: str, kind: str) -> list[tuple[str, str, str | None]]:
    """(twelve-figure code, name, link) for every ``<tr class="KINDtr">`` row
    of one of the Bureau's listing pages: countytr on a prefecture's, towntr
    on a county's. A unit with nothing below it carries no link."""
    out = []
    for row in re.findall(rf"""(?is)<tr[^>]*class\s*=\s*["']?{kind}tr["']?[^>]*>(.*?)</tr>""",
                          page):
        cells = re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)
        if len(cells) < 2:
            continue
        text = [" ".join(html.unescape(re.sub(r"(?s)<[^>]+>", " ", c)).split()) for c in cells]
        link = re.search(r"""(?i)href\s*=\s*["']([^"']+)["']""", row)
        code, name = text[0].replace(" ", ""), text[-1].replace(" ", "")
        if re.fullmatch(r"\d{12}", code):
            out.append((code, name, link.group(1) if link else None))
    return out


def decode(blob: bytes) -> str:
    head = blob[:3000].decode("ascii", "replace")
    m = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9_-]+)", head, re.I)
    charset = (m.group(1).lower() if m else "utf-8")
    charset = {"gb2312": "gb18030", "gbk": "gb18030"}.get(charset, charset)
    return blob.decode(charset, "replace")


def capture(url: str) -> str:
    """The Internet Archive's newest capture of one of the Bureau's pages."""
    query = urllib.parse.urlencode({"url": url, "output": "json", "filter": "statuscode:200",
                                    "fl": "timestamp", "limit": "-1"})
    rows = json.loads(http_get(f"{CDX}?{query}", cache=False, retries=4, timeout=90) or "[]")
    if len(rows) <= 1:
        raise LookupError(f"no capture of {url}")
    time.sleep(PAUSE)
    blob = http_get(REPLAY.format(stamp=rows[-1][0], url=url), binary=True, cache=True,
                    retries=4, timeout=90)
    assert isinstance(blob, bytes)
    return decode(blob)


def transcription(name: str) -> list[dict[str, str]]:
    blob = http_get(MIRROR.format(ref=MIRROR_REF, name=name), binary=True, cache=True,
                    retries=4, timeout=120)
    assert isinstance(blob, bytes)
    return list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))


def zones_of(areas: list[dict[str, str]], streets: list[dict[str, str]],
             provinces: list[str]) -> dict[str, dict[str, Any]]:
    """{zone code: {name, prefecture, townships: [[nine-figure code, name]]}}
    for every county-level unit coded 71 to 80 in the provinces asked for."""
    out: dict[str, dict[str, Any]] = {}
    for row in areas:
        code = row["code"]
        if code[:2] in provinces and is_zone(code):
            out[code] = {"name": row["name"], "prefecture": f"{code[:4]}00", "townships": []}
    for row in streets:
        if row["areaCode"] in out:
            out[row["areaCode"]]["townships"].append([row["code"], row["name"]])
    return out


def units_of(areas: list[dict[str, str]], streets: list[dict[str, str]],
             provinces: list[str]) -> dict[str, dict[str, Any]]:
    """{county-level code: {name, prefecture, townships: [[nine-figure code,
    name]]}} for every county-level unit of the provinces asked for, zones and
    districts included: what ``china_county_census`` holds each county's
    polygon to (its own townships inside it, nobody else's)."""
    out: dict[str, dict[str, Any]] = {}
    for row in areas:
        code = row["code"]
        if code[:2] in provinces:
            out[code] = {"name": row["name"], "prefecture": f"{code[:4]}00", "townships": []}
    for row in streets:
        if row["areaCode"] in out:
            out[row["areaCode"]]["townships"].append([row["code"], row["name"]])
    return out


def check(zones: dict[str, dict[str, Any]], pages: dict[str, str]) -> list[str]:
    """Each kept page of the Bureau's against the transcription's zone of the
    same code: the same townships under the same codes and names, or a
    refusal. {address: page}."""
    said = []
    for url, page in pages.items():
        code = re.search(r"(\d{6})\.html$", url).group(1)
        theirs = sorted((c[:9], n) for c, n, _ in rows_of(page, "town"))
        ours = sorted((c, n) for c, n in zones.get(code, {}).get("townships", []))
        if theirs != ours:
            raise SystemExit(f"china_zones: the Bureau's page for {code} ({url}) lists {theirs} "
                             f"and the transcription {ours}")
        said.append(f"{code}: {len(theirs)} townships, the same in both")
    return said


def fetch(provinces: list[str]) -> int:
    areas, streets = transcription("areas.csv"), transcription("streets.csv")
    zones = zones_of(areas, streets, provinces)
    pages: dict[str, str] = {}
    for edition, url in CHECKS:
        if edition != EDITION:
            continue
        try:
            pages[url] = capture(url)
        except Exception as exc:  # noqa: BLE001 - logged; a page not read checks nothing
            log(f"  {url} not read: {type(exc).__name__}: {str(exc)[:120]}")
    checked = check(zones, pages)
    for line in checked:
        log(f"  checked against the Bureau's own page: {line}")
    for code, zone in sorted(zones.items()):
        log(f"  {code} {zone['name']}: {len(zone['townships'])} townships")
    units = units_of(areas, streets, provinces)
    listing = {"source": TRANSCRIPTION.format(edition=EDITION),
               "url": MIRROR.format(ref=MIRROR_REF, name="streets.csv"),
               "edition": EDITION, "checked": checked, "zones": zones, "units": units}
    LISTING.write_text(json.dumps(listing, ensure_ascii=False, separators=(",", ":"),
                                  sort_keys=True) + "\n", encoding="utf-8")
    log(f"china_zones: {len(zones)} zones and {len(units)} county-level units "
        f"({sum(len(u['townships']) for u in units.values())} townships) in "
        f"{','.join(provinces)} -> {LISTING.name}")
    return 0


# ---------------------------------------------------------------------------
# Placing the townships
# ---------------------------------------------------------------------------

SUFFIX_ZH = re.compile(r"(街道办事处|街道|民族乡|镇|乡|苏木|办事处|管委会|管理区|农场|林场|区)$")
SUFFIX_EN = re.compile(r"(?i)\b(subdistrict|sub-district|town|township|ethnic township|"
                       r"sumu|area|farm|street|office)\b")


def bare_label(label: str) -> str:
    return re.sub(r"[^a-z]", "", SUFFIX_EN.sub("", label or "").lower())


def pinyins(name: str) -> set[str]:
    from .china_seats import readings
    return {r.replace("v", "u") for r in readings(SUFFIX_ZH.sub("", name) or name)}


# A zone's township named with the zone in front of it ("芦台开发区海北镇",
# "察北管理区黄山管理处"): the township's own name is what follows.
ZONE_PREFIX = re.compile(r"^.+?(开发区|管理区|新区)(?=.{2,}$)")
KIND_EN = {"街道": "subdistrict", "镇": "town", "乡": "township"}


def point_for(code: str, name: str, by_code: dict[str, dict[str, Any]],
              by_prefecture: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, str]:
    """(the Wikidata item standing for the township, how it was found): the
    item carrying the township's own code whose label reads as its name, or
    failing that the one item in the prefecture whose label does -- of the
    same kind (街道 a subdistrict, 镇 a town, 乡 a township) where two do."""
    own = ZONE_PREFIX.sub("", name)
    names = pinyins(name) | pinyins(own)
    item = by_code.get(code[:9]) or by_code.get(code)
    if item and bare_label(item.get("label", "")) in names:
        return item, "its code"
    hits = [p for p in by_prefecture.get(code[:4], []) if bare_label(p.get("label", "")) in names]
    if len(hits) > 1:
        kind = next((en for zh, en in KIND_EN.items() if own.endswith(zh)), None)
        same = [p for p in hits if kind and re.search(rf"(?i)\b{kind}\b", p.get("label", ""))]
        hits = same if len(same) == 1 else hits
    if len(hits) == 1:
        return hits[0], f"its name, in the prefecture (as {hits[0]['code']})"
    if item and not hits:
        # The code's item is labelled other than in pinyin (a Q-number, or
        # an English name): its code alone says it is this township.
        return item, "its code (the item's label is not its name in pinyin)"
    return None, ("no item carries its code or its name" if not hits else
                  f"{len(hits)} items in the prefecture carry its name")


def place() -> int:
    import fiona
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    from .china_seats import boundaries
    listing = json.loads(LISTING.read_text(encoding="utf-8"))
    points = json.loads(POINTS.read_text(encoding="utf-8"))
    by_code: dict[str, dict[str, Any]] = {}
    by_prefecture: dict[str, list[dict[str, Any]]] = {}
    for p in points:
        code = re.sub(r"\s", "", p.get("code") or "")
        if len(code) in (9, 12) and p.get("lon") is not None:
            p = {**p, "code": code}
            by_code.setdefault(code, p)
            by_prefecture.setdefault(code[:4], []).append(p)
    drawn = {u["id"] for u in json.loads(UNITS.read_text(encoding="utf-8"))}
    ids, geoms = [], []
    with fiona.open(boundaries()) as src:
        for feature in src.filter(bbox=(73, 17, 136, 54)):
            if feature["properties"]["shapeID"] in drawn:
                ids.append(feature["properties"]["shapeID"])
                geoms.append(shape(feature["geometry"]))
    tree = STRtree(geoms)

    def located(item: dict[str, Any]) -> dict[str, Any]:
        pt = Point(float(item["lon"]), float(item["lat"]))
        return {"qid": item.get("qid"), "lon": item["lon"], "lat": item["lat"],
                "shape": next((ids[i] for i in tree.query(pt) if geoms[i].contains(pt)), None),
                "near": sorted(ids[i] for i in tree.query(pt.buffer(NEAR))
                               if geoms[i].distance(pt) <= NEAR)}

    ground: dict[str, Any] = {}
    placed = unplaced = extra = 0
    for zcode, zone in sorted(listing["zones"].items()):
        out = {"name": zone["name"], "listing": listing["source"], "townships": []}
        seen = set()
        for code, name in zone["townships"]:
            item, how = point_for(code, name, by_code, by_prefecture)
            entry: dict[str, Any] = {"code": code, "name": name, "how": how}
            if item:
                entry.update(located(item))
                seen.add(item.get("qid"))
                placed += 1
            else:
                unplaced += 1
            out["townships"].append(entry)
        # Wikidata's items carrying the zone's code that the listing does not
        # name: townships the zone held under another edition.
        for code, item in sorted(by_code.items()):
            if code.startswith(zcode) and item.get("qid") not in seen:
                out["townships"].append({"code": code, "name": item.get("label"),
                                         "how": "a Wikidata item carrying the zone's code",
                                         **located(item)})
                extra += 1
        ground[zcode] = out
    GROUND.write_text(json.dumps(ground, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")
    log(f"china_zones: {len(ground)} zones; {placed} listed townships placed, {unplaced} not; "
        f"{extra} more from Wikidata's items -> {GROUND}")
    # Every county-level unit's townships, compactly: [code, name, the polygon
    # its point stands in, the polygons within NEAR of it] or [code, name] for
    # one with no point.
    towns: dict[str, list[list[Any]]] = {}
    placed = unplaced = 0
    for ucode, unit in sorted((listing.get("units") or {}).items()):
        rows = []
        for code, name in unit["townships"]:
            item, _ = point_for(code, name, by_code, by_prefecture)
            if item:
                spot = located(item)
                rows.append([code, name, spot["shape"], spot["near"]])
                placed += 1
            else:
                rows.append([code, name])
                unplaced += 1
        towns[ucode] = rows
    TOWNS.write_text(json.dumps(towns, ensure_ascii=False, separators=(",", ":"),
                                sort_keys=True) + "\n", encoding="utf-8")
    log(f"china_zones: {len(towns)} county-level units; {placed} townships placed, {unplaced} "
        f"not -> {TOWNS}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", help="province codes (22,32): read the listing on the runner")
    ap.add_argument("--place", action="store_true",
                    help="place the listed zones' townships, where the boundaries are")
    args = ap.parse_args()
    if args.fetch:
        return fetch(args.fetch.split(","))
    if args.place:
        return place()
    ap.error("--fetch CODES or --place")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
