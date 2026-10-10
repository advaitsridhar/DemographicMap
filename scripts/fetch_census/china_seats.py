#!/usr/bin/env python3
"""Which of today's county-level seats stand in each of China's drawn county polygons.

China's 2,370 second-level polygons are a county division of the mid-1990s
(Tongxian, not Tongzhou District; Panyu as the county-level city it was until
2000), so a county's 2020 figure belongs on a polygon only where the polygon
is still that one county. ``data/processed/code_shapes.json`` says which
polygon a GB/T 2260 code's Wikidata item stands in when the item's name and
the polygon's agree; this says, for every polygon, which current county-level
codes stand in it at all. A polygon holding one seat and bound to that seat's
code by name is the county today; a polygon holding two or more is a city
core or a county a later district was cut from, and one holding none is a
county later merged into a neighbour -- whose own polygon then holds a
county that is bigger than it is drawn.

It needs the CGAZ boundary file the map is built from (data/raw/boundaries,
about 240 MB, not in git and not on the adapter runner), so it is run where
the boundaries are, and its small output is kept in the repository:
``data/raw/wikidata_points/CHN_P442_seats.json``, {shape id: [codes of the seats inside]}.

The seats are Wikidata's current items carrying a six-figure GB/T 2260 code
(data/raw/wikidata_points/CHN_P442.json), less prefecture codes (ending 00)
and the "districts" aggregates (ending 01 and labelled as such). Wikidata
names no figure here; it only says where a code's seat stands.

**Names** (``--names``). A polygon holding one seat is that county only if
its label names it, and code_shapes' test compares the boundary file's
pinyin label with Wikidata's English label, which for a Tibetan, Uyghur or
Mongol county is not pinyin at all ("Gangca County" for 刚察县, drawn
"Gangchaxian") and which no misspelt label meets ("Yitongmazuzizixian" for
伊通满族自治县). This compares the label with the pinyin of the seat's own
Chinese names (``CHN_P442_zh.json``), every reading of a character that has
several (乐亭 is Laoting, not Yueting), the whole name and the name without
its kind and its nationalities, and writes the best agreement (difflib's
ratio, 0 to 1) for every polygon holding one seat:
``data/raw/wikidata_points/CHN_P442_seat_names.json``, {shape id: {code,
label, zh, reading, agreement}}. It needs pypinyin and no boundaries.

Usage:
    python -m scripts.fetch_census.china_seats            # where the boundaries are
    python -m scripts.fetch_census.china_seats --names    # where pypinyin is
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POINTS = ROOT / "data" / "raw" / "wikidata_points" / "CHN_P442.json"
UNITS = ROOT / "site" / "data" / "admin2" / "CHN.units.json"
OUT = ROOT / "data" / "raw" / "wikidata_points" / "CHN_P442_seats.json"
ZH = ROOT / "data" / "raw" / "wikidata_points" / "CHN_P442_zh.json"
NAMES_OUT = ROOT / "data" / "raw" / "wikidata_points" / "CHN_P442_seat_names.json"
CGAZ = "geoBoundariesCGAZ_ADM2.gpkg"


def county_codes(points: list[dict]) -> list[tuple[str, float, float]]:
    """(code, lon, lat) for every current county-level item."""
    out = []
    for p in points:
        code = re.sub(r"\s", "", p.get("code") or "")
        if not re.fullmatch(r"\d{6}", code) or code.endswith("00"):
            continue
        if code[4:] == "01" and re.search(r"(?i)districts\b|市辖区", p.get("label") or ""):
            continue
        out.append((code, float(p["lon"]), float(p["lat"])))
    return out


def boundaries() -> Path:
    for base in (ROOT / "data" / "raw" / "boundaries",
                 ROOT.parent.parent.parent / "data" / "raw" / "boundaries"):
        if (base / CGAZ).exists():
            return base / CGAZ
    raise SystemExit(f"china_seats: {CGAZ} is not here; run this where the boundaries are")


KIND_ZH = re.compile(r"(自治县|自治旗|县|旗|市|区|特区|林区)$")
NATIONS_ZH = re.compile(
    r"((?:满|蒙古|回|藏|彝|苗|土家|侗|瑶|壮|布依|朝鲜|畲|黎|傣|白|哈尼|拉祜|佤|纳西|傈僳|景颇|羌|仡佬|"
    r"土|撒拉|东乡|保安|裕固|锡伯|达斡尔|鄂温克|鄂伦春|仫佬|毛南|水|独龙|怒|普米|阿昌|德昂|布朗|基诺|"
    r"各)族|哈萨克|蒙古|塔吉克|柯尔克孜|维吾尔)+$")
KIND_PINYIN = re.compile(r"(zizhixian|zizixian|zizhiqi|tequ|xian|shi|qu|qi)$")


def readings(text: str, limit: int = 64) -> list[str]:
    """Every pinyin reading of ``text``, toneless, up to ``limit`` of them."""
    import itertools
    from pypinyin import Style, pinyin
    syllables = pinyin(text, style=Style.NORMAL, heteronym=True)
    out = []
    for combo in itertools.product(*[s[:3] for s in syllables]):
        out.append("".join(combo).replace("ü", "v").lower())
        if len(out) >= limit:
            break
    return out


def agreement(zh: str, label: str) -> tuple[float, str]:
    """(best ratio, the reading that made it) of a Chinese name against a
    drawn pinyin label: the whole name, and the name without its kind and its
    nationalities, against the label whole and without its kind."""
    import difflib
    whole = re.sub(r"[^a-z]", "", label.lower())
    stem = whole
    for _ in range(2):
        stem = KIND_PINYIN.sub("", stem)
    bare = KIND_ZH.sub("", zh)
    best, reading = 0.0, ""
    for form in {zh, bare, NATIONS_ZH.sub("", bare) or bare}:
        for r in readings(form):
            for target in (whole, stem):
                ratio = difflib.SequenceMatcher(None, r, target).ratio()
                if ratio > best:
                    best, reading = ratio, r
    return round(best, 3), reading


def names() -> int:
    seats = json.loads(OUT.read_text(encoding="utf-8"))
    zh = json.loads(ZH.read_text(encoding="utf-8"))
    units = {u["id"]: u for u in json.loads(UNITS.read_text(encoding="utf-8"))}
    out: dict[str, dict] = {}
    for shape, codes in sorted(seats.items()):
        if len(codes) != 1:
            continue
        label = units[shape].get("shape_name") or units[shape]["name"]
        best = (0.0, "", "")
        for name in zh.get(codes[0], []):
            ratio, reading = agreement(name, label)
            if ratio > best[0]:
                best = (ratio, reading, name)
        out[shape] = {"code": codes[0], "label": label, "zh": best[2], "reading": best[1],
                      "agreement": best[0]}
    NAMES_OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n",
                         encoding="utf-8")
    high = sum(1 for v in out.values() if v["agreement"] >= 0.9)
    print(f"china_seats: {len(out)} polygons hold one seat; {high} of their labels agree with "
          f"the seat's Chinese name at 0.9 or better -> {NAMES_OUT.relative_to(ROOT)}")
    return 0


def main() -> int:
    import sys
    if "--names" in sys.argv[1:]:
        return names()
    import fiona
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    drawn = {u["id"] for u in json.loads(UNITS.read_text(encoding="utf-8"))}
    ids, geoms = [], []
    with fiona.open(boundaries()) as src:
        for feature in src.filter(bbox=(73, 17, 136, 54)):
            if feature["properties"]["shapeID"] in drawn:
                ids.append(feature["properties"]["shapeID"])
                geoms.append(shape(feature["geometry"]))
    if len(ids) != len(drawn):
        raise SystemExit(f"china_seats: {len(ids)} of the {len(drawn)} drawn polygons found")
    tree = STRtree(geoms)
    seats: dict[str, list[str]] = {sid: [] for sid in ids}
    outside = 0
    for code, lon, lat in county_codes(json.loads(POINTS.read_text(encoding="utf-8"))):
        point = Point(lon, lat)
        hits = [ids[i] for i in tree.query(point) if geoms[i].contains(point)]
        if hits:
            seats[hits[0]].append(code)
        else:
            outside += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({k: sorted(v) for k, v in sorted(seats.items())},
                              ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    counts = [len(v) for v in seats.values()]
    print(f"china_seats: {len(ids)} polygons; {counts.count(1)} hold one seat, "
          f"{sum(1 for c in counts if c > 1)} several, {counts.count(0)} none; "
          f"{outside} seats in no polygon -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
