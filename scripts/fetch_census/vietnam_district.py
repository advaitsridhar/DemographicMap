#!/usr/bin/env python3
"""Viet Nam: population and sex ratio by district, median age by province, 2019 census.

The office's Vietnamese results volume -- "Kết quả toàn bộ Tổng điều tra dân số
và nhà ở năm 2019", the 842-page PDF ``vietnam.py`` reads Table 2 from -- has
two more tables this map lacks:

* **Table 1** (pages 9-42): population by urban/rural, sex, province and
  **district** ("huyện/quận/thành phố/thị xã"). Every district row carries
  nine figures -- total, male and female for the whole, the urban and the
  rural population -- read with ``vietnam.figures``, which keeps the one
  split of the digit groups that satisfies the publisher's own arithmetic.
  Each gives a district's **population** and **sex ratio**.
* **Table 5** (pages 239-308): population by five-year age group, sex,
  socio-economic region and province, to an open 85+. Each province's
  **median age** is interpolated within the group holding the middle person;
  the volume publishes single years (Table 4) for the country and its regions
  only, which is what the national check is made against.

**Which polygon a district is.** The boundary file draws 705 districts of a
vintage between 2014 and 2019 (both halves of Từ Liêm, Hà Nội's districts 2
and 9 before Thủ Đức city, Kỳ Sơn and Hoành Bồ before their 2019-2020
mergers), unaccented ("Ba Dinh") and with parents that are not always right
(it files Ba Vì under Phú Thọ). So a census district is bound to a polygon by
its folded name: where that name is the only one of its kind in the census
and on the map, outright; where it is shared (ten polygons are "Chau Thanh"),
to the one polygon of that name whose representative point lies in the
census's province on the map's own admin1 tiles, or failing that whose
boundary-file parent is that province -- and only if exactly one does. A
polygon the census divided after the boundary file was drawn takes the sum of
its parts, declared pair by pair in ``JOINED`` and checked; twelve districts
the boundary file spells its own way or files under a neighbour are declared
in ``PLACED``; the two island districts it does not draw (Cồn Cỏ, Trường Sa)
in ``UNDRAWN``. Anything else left over on either side refuses. Côn Đảo,
which the boundary file draws at both levels, gets its district's figures at
both.

**Checks**, each a refusal: every row's nine figures satisfy the arithmetic
(``vietnam.figures``); every province's districts make the province's own row
for the whole, males and females; the provinces make the national
96,208,984; in Table 5 every unit's groups make its total; and the national
median from the five-year groups is within 0.3 years of the one from Table 4's
single years.

Usage:
    python -m scripts.fetch_census.vietnam_district
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any

from . import vietnam as vn
from ._shared import PROCESSED, RAW, download, log, record, write_json
from .sea_common import age_sex, drawn, grouped, locate, single_median

OUT = "vietnam_district.json"
YEAR = 2019
SOURCE_T1 = ("General Statistics Office of Viet Nam, Kết quả toàn bộ Tổng điều tra dân số và "
             "nhà ở năm 2019 (Completed Results of the 2019 Viet Nam Population and Housing "
             "Census), Table 1: population by urban/rural, sex, province and district, "
             "1 April 2019")
SOURCE_T5 = ("General Statistics Office of Viet Nam, Kết quả toàn bộ Tổng điều tra dân số và "
             "nhà ở năm 2019, Table 5: population by age group, urban/rural, sex, "
             "socio-economic region and province, 1 April 2019")
MEDIAN_TOLERANCE = 0.3
TYPE = re.compile(r"^(?P<vi>Thành phố|Thị xã|Quận|Huyện)\s*-\s*(?P<en>City|Town|Quarter|District)"
                  r"\b\s*(?P<name>.*)$")
LINE = re.compile(r"^\s*(?P<label>\S.*?)\s+(?P<tail>(?:(?:\d{1,3}|-)\s+){8,}(?:\d{1,3}|-))\s*$")
GROUP = re.compile(r"^\s*(?P<lo>\d{1,2})\s*-\s*(?P<hi>\d{1,2})\s+"
                   r"(?P<tail>(?:(?:\d{1,3}|-)\s+){8,}(?:\d{1,3}|-))\s*$")
OPEN = re.compile(r"^\s*(?P<lo>\d{2,3})\s*\+\s+(?P<tail>(?:(?:\d{1,3}|-)\s+){8,}(?:\d{1,3}|-))\s*$")
SINGLE = re.compile(r"^\s*(?P<age>\d{1,2})\s+(?P<tail>(?:(?:\d{1,3}|-)\s+){8,}(?:\d{1,3}|-))\s*$")
# Polygons the census divided after the boundary file was drawn: the
# polygon's (census province, folded name) -> the census districts that make
# it, as (type, name). All five divisions are of 2015, and the boundary file
# draws each district before: Long Mỹ town was cut from Long Mỹ district, Kỳ
# Anh town from Kỳ Anh district, Duyên Hải town from Duyên Hải district, Ia
# H'Drai from Sa Thầy and Phú Riềng from Bù Gia Mập. In each province the map
# draws one polygon fewer than the census counts districts, and the polygons'
# areas on the tiles are the old districts' (Sa Thầy 2,411 km2, the 2,415 of
# Sa Thầy and Ia H'Drai; Bù Gia Mập 1,746, the 1,739 of it and Phú Riềng).
JOINED: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("Hậu Giang", "longmy"): [("District", "Long Mỹ"), ("Town", "Long Mỹ")],
    ("Hà Tĩnh", "kyanh"): [("District", "Kỳ Anh"), ("Town", "Kỳ Anh")],
    ("Trà Vinh", "duyenhai"): [("District", "Duyên Hải"), ("Town", "Duyên Hải")],
    ("Kon Tum", "sathay"): [("District", "Sa Thầy"), ("District", "Ia H' Drai")],
    ("Bình Phước", "bugiamap"): [("District", "Bù Gia Mập"), ("District", "Phú Riềng")],
}
# Census districts their names alone do not find: (province, type, name) ->
# the polygon's name and the province the boundary file files it under;
# exactly one polygon must answer to both. The first three are filed under a
# neighbouring province that has no district of the name -- which is checked
# -- and each lies where its district does: An Lão at 20.80N 106.55E, Hải
# Phòng's; Châu Thành at 9.92N 105.82E, Hậu Giang's (Cần Thơ has had none
# since 2004); Sơn Tây at 14.97N 108.36E, Quảng Ngãi's. The rest are the
# boundary file's spellings: its Phú Quý, unaccented; Tân Thành, the district
# that became Phú Mỹ town in 2018; and type words it keeps in the name.
PLACED: dict[tuple[str, str, str], tuple[str, str]] = {
    ("Hải Phòng", "District", "An Lão"): ("An Lao", "Hải Dương"),
    ("Hậu Giang", "District", "Châu Thành"): ("Chau Thanh", "Cần Thơ"),
    ("Quảng Ngãi", "District", "Sơn Tây"): ("Son Tay", "Kon Tum"),
    ("Bình Thuận", "District", "Phú Quí"): ("Phu Quy", "VNM"),
    ("Bà Rịa–Vũng Tàu", "Town", "Phú Mỹ"): ("Tan Thanh", "Bà Rịa–Vũng Tàu"),
    ("Đắk Lắk", "District", "M'Đrắk"): ("Mdrak District", "Đắk Lắk"),
    ("Tiền Giang", "District", "Cai Lậy"): ("Huyen Cai Lay", "Tiền Giang"),
    ("Tiền Giang", "Town", "Cai Lậy"): ("Thi xa Cai Lay", "Tiền Giang"),
    ("Đồng Tháp", "District", "Cao Lãnh"): ("Huyen Cao Lanh", "Đồng Tháp"),
    ("Đồng Tháp", "City", "Cao Lãnh"): ("Thi xa Cao Lanh", "Đồng Tháp"),
    ("Đồng Tháp", "District", "Hồng Ngự"): ("Huyen Hong Ngu", "Đồng Tháp"),
    ("Đồng Tháp", "Town", "Hồng Ngự"): ("Thi xa Hong Ngu", "Đồng Tháp"),
}
# Census districts no polygon draws: island districts the boundary file
# leaves out. Reported, and written nowhere.
UNDRAWN = {("Quảng Trị", "Cồn Cỏ"), ("Khánh Hòa", "Trường Sa")}
# The polygon drawn at the first level for one census district.
FIRST_LEVEL = {"Côn Đảo": ("Bà Rịa–Vũng Tàu", "Côn Đảo")}


def is_table(page: str, number: int) -> bool:
    head = "\n".join(page.splitlines()[:6])
    return bool(re.search(rf"(?:Table|Biểu)\s*{number}\b", head))


def key(name: str) -> str:
    return vn.fold(name)


def parse_table1(pages: list[str]) -> tuple[list[dict[str, Any]], dict[str, list[int]], list[int]]:
    """Table 1: [{province, type, name, n (nine figures), page}], each province's
    own row, and the country's."""
    rows: list[dict[str, Any]] = []
    provinces: dict[str, list[int]] = {}
    country: list[int] = []
    province = None
    problems: list[str] = []
    for number, page in enumerate(pages, 1):
        if not is_table(page, 1):
            continue
        carried = None
        for line in page.splitlines():
            m = LINE.match(line)
            if not m:
                # A long name breaks after its type: "Thành phố - City" alone on
                # one line, the name and its figures on the next.
                bare = TYPE.match(" ".join(line.split()))
                carried = bare if bare and not bare.group("name") else None
                continue
            label = " ".join(m.group("label").split())
            tokens = m.group("tail").split()
            if carried and not TYPE.match(label):
                label = f"{carried.group('vi')} - {carried.group('en')} {label}"
            carried = None
            if "ENTIRE COUNTRY" in label.upper() or key(label).startswith("toanquoc"):
                country = vn.figures(tokens)
                continue
            t = TYPE.match(label)
            name, kind = (t.group("name").strip(), t.group("en")) if t else (label, None)
            if t and not name:
                # "Quận - Quarter 1": a numbered district, its number heading the
                # tail; the boundary file calls it "Quan 1".
                name, tokens = f"{t.group('vi')} {tokens[0]}", tokens[1:]
            if not t and vn.classify(label)[0] in ("region", "country"):
                continue
            letters = [c for c in name if c.isalpha()]
            if letters and all(c.isupper() for c in letters):
                prov = vn.PROVINCE_KEYS.get(key(vn.UNIT_PREFIX.sub("", name)))
                if prov is None:
                    raise SystemExit(f"vietnam_district: page {number}: {label!r} is not a "
                                     "province this reader knows")
                if prov in provinces:
                    raise SystemExit(f"vietnam_district: {prov} printed twice")
                provinces[prov] = vn.figures(tokens)
                province = prov
                continue
            if province is None or kind is None:
                problems.append(f"page {number}: {label!r}")
                continue
            rows.append({"province": province, "type": kind, "name": name,
                         "n": vn.figures(tokens), "page": number})
    if problems:
        raise SystemExit(f"vietnam_district: {len(problems)} Table 1 rows are neither a "
                         f"province nor a typed district: {problems}")
    return rows, provinces, country


def check_table1(rows, provinces, country) -> None:
    if set(provinces) != set(vn.PROVINCES):
        raise SystemExit(f"vietnam_district: Table 1 provinces missing "
                         f"{sorted(set(vn.PROVINCES) - set(provinces))}")
    for prov, own in provinces.items():
        kids = [r["n"] for r in rows if r["province"] == prov]
        made = [sum(k[i] for k in kids) for i in range(3)]
        if made != own[:3]:
            raise SystemExit(f"vietnam_district: {prov}'s {len(kids)} districts make {made}, "
                             f"against its own {own[:3]}")
    total = sum(p[0] for p in provinces.values())
    if total != vn.NATIONAL_TOTAL or (country and country[0] != total):
        raise SystemExit(f"vietnam_district: the provinces make {total:,}, against "
                         f"{vn.NATIONAL_TOTAL:,}")
    log(f"  Table 1: {len(rows)} districts in {len(provinces)} provinces, each province's "
        f"districts making its own row; the provinces make {total:,}")


def parse_age_tables(pages: list[str]) -> tuple[dict[str, dict[str, Any]], Counter]:
    """Table 5's units with their five-year groups, and Table 4's national single years."""
    units: dict[str, dict[str, Any]] = {}
    current = None
    singles: Counter = Counter()
    single_unit = None
    for number, page in enumerate(pages, 1):
        if is_table(page, 4):
            for line in page.splitlines():
                m = LINE.match(line)
                if m and not SINGLE.match(line) and not OPEN.match(line):
                    label = " ".join(m.group("label").split())
                    kind, _ = vn.classify(label)
                    if kind in ("country", "region", "province"):
                        single_unit = kind
                    elif single_unit == "country" and re.search(r"(?i)under\s*1|dưới\s*1",
                                                                label):
                        singles[0] += vn.figures(m.group("tail").split())[0]
                    continue
                if single_unit != "country":
                    continue
                if s := SINGLE.match(line):
                    singles[int(s.group("age"))] += vn.figures(s.group("tail").split())[0]
                elif o := OPEN.match(line):
                    singles[int(o.group("lo"))] += vn.figures(o.group("tail").split())[0]
            continue
        if not is_table(page, 5):
            continue
        for line in page.splitlines():
            if g := GROUP.match(line):
                if current is None:
                    raise SystemExit(f"vietnam_district: page {number}: an age row before "
                                     "any unit")
                n = vn.figures(g.group("tail").split())
                current["groups"].append((int(g.group("lo")), int(g.group("hi")), n))
                continue
            if o := OPEN.match(line):
                n = vn.figures(o.group("tail").split())
                current["groups"].append((int(o.group("lo")), None, n))
                continue
            m = LINE.match(line)
            if not m:
                continue
            label = " ".join(m.group("label").split())
            kind, name = vn.classify(label)
            words = label.split()
            while kind not in ("province", "region", "country") and len(words) > 1:
                # A wrapped bilingual region name arrives as the last word of its
                # Vietnamese half and the whole English one: "Trung North and
                # South Central Coast". Its English tail is the region.
                words = words[1:]
                kind, name = vn.classify(" ".join(words))
                if kind == "province":
                    kind = "other"        # a tail that names a province is no region
            if kind not in ("province", "region", "country"):
                raise SystemExit(f"vietnam_district: Table 5 page {number}: {label!r} is no "
                                 "unit this reader knows")
            unit_key = name if kind == "province" else f"{kind}:{name}"
            if unit_key in units:
                raise SystemExit(f"vietnam_district: Table 5 prints {label!r} twice")
            current = units[unit_key] = {"kind": kind, "label": label, "groups": [],
                                         "n": vn.figures(m.group("tail").split())}
    for k, u in units.items():
        made = [sum(g[2][i] for g in u["groups"]) for i in range(3)]
        if made != u["n"][:3] or len(u["groups"]) != 18:
            raise SystemExit(f"vietnam_district: Table 5 {k}: {len(u['groups'])} groups make "
                             f"{made}, against {u['n'][:3]}")
    return units, singles


def check_ages(units, singles) -> None:
    provinces = [k for k, u in units.items() if u["kind"] == "province"]
    if set(provinces) != set(vn.PROVINCES):
        raise SystemExit(f"vietnam_district: Table 5 provinces missing "
                         f"{sorted(set(vn.PROVINCES) - set(provinces))}")
    country = [u for u in units.values() if u["kind"] == "country"]
    if len(country) != 1 or sum(singles.values()) != country[0]["n"][0]:
        raise SystemExit(f"vietnam_district: Table 4's single years make "
                         f"{sum(singles.values()):,}, against Table 5's country "
                         f"{country[0]['n'][0] if country else '?'}")
    from_groups = grouped([(lo, hi, n[0]) for lo, hi, n in country[0]["groups"]])
    from_years = single_median(singles)
    if abs(from_groups - from_years) > MEDIAN_TOLERANCE:
        raise SystemExit(f"vietnam_district: the national median is {from_groups} from "
                         f"five-year groups and {from_years} from single years")
    log(f"  Table 5: {len(provinces)} provinces, each one's 18 groups making its total; "
        f"national median {from_groups} from the groups, {from_years} from Table 4's "
        "single years")


def bind(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[str], list[str]]:
    """Polygon id -> the census districts it is; and what was left on each side."""
    name1 = {u["id"]: u["name"] for u in admin1}
    where = locate({u["id"]: tuple(u["point"]) for u in admin2 if u.get("point")},
                   "admin1", "VNM")
    shapes_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in admin2:
        shapes_by_name[key(s["name"])].append(s)
    census_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        census_by_name[key(r["name"])].append(r)
    bound: dict[str, list[dict[str, Any]]] = {}
    used: set[int] = set()
    # Joined polygons first: they are declared.
    for (prov, folded), parts in JOINED.items():
        shapes = [s for s in shapes_by_name.get(folded, [])
                  if name1.get(where.get(s["id"])) == prov or name1.get(s["parent"]) == prov]
        found = [r for r in rows if r["province"] == prov
                 and (r["type"], key(r["name"])) in {(t, key(n)) for t, n in parts}]
        if len(shapes) != 1 or len(found) != len(parts):
            raise SystemExit(f"vietnam_district: the joined polygon {folded} of {prov}: "
                             f"{len(shapes)} polygons, {len(found)} of {len(parts)} districts")
        bound[shapes[0]["id"]] = found
        used.update(id(r) for r in found)
    # Then the declared placements.
    for (prov, kind, name), (polygon, filed) in PLACED.items():
        found = [r for r in rows if r["province"] == prov and r["type"] == kind
                 and key(r["name"]) == key(name)]
        shapes = [s for s in shapes_by_name.get(key(polygon), [])
                  if name1.get(s["parent"], s["parent"]) == filed and s["id"] not in bound]
        if len(found) != 1 or len(shapes) != 1:
            raise SystemExit(f"vietnam_district: {kind} {name} of {prov} -> {polygon!r} filed "
                             f"under {filed}: {len(found)} districts, {len(shapes)} polygons")
        if filed not in (prov, "VNM") and any(r["province"] == filed and key(r["name"])
                                              == key(name) for r in rows):
            raise SystemExit(f"vietnam_district: {filed} has a district {name} of its own; "
                             f"{polygon!r} may be it")
        bound[shapes[0]["id"]] = found
        used.add(id(found[0]))
    taken = set(bound)
    for r in rows:
        if id(r) in used:
            continue
        k = key(r["name"])
        candidates = [s for s in shapes_by_name.get(k, []) if s["id"] not in taken]
        if len(census_by_name[k]) == 1 and len(shapes_by_name.get(k, [])) == 1 and candidates:
            pick = candidates
        else:
            pick = [s for s in candidates if name1.get(where.get(s["id"])) == r["province"]]
            if len(pick) != 1:
                pick = [s for s in candidates if name1.get(s["parent"]) == r["province"]]
            if len(pick) != 1:
                continue
            twins = [x for x in census_by_name[k] if x["province"] == r["province"]
                     and id(x) not in used]
            if len(twins) != 1:
                continue                  # two census districts of one name in one province
        bound[pick[0]["id"]] = [r]
        taken.add(pick[0]["id"])
        used.add(id(r))
    left_census = [f"{r['province']}: {r['type']} {r['name']} ({r['n'][0]:,})"
                   for r in rows if id(r) not in used]
    left_shapes = [f"{s['name']} ({name1.get(s['parent'], s['parent'])}; on the tiles "
                   f"{name1.get(where.get(s['id']), '-')})"
                   for s in admin2 if s["id"] not in bound]
    return bound, left_census, left_shapes


def district_records(bound: dict[str, list[dict[str, Any]]], admin2: list[dict[str, Any]]
                     ) -> list[dict[str, Any]]:
    names = {s["id"]: s["name"] for s in admin2}
    src = [{"field": "population/sex_ratio", "name": SOURCE_T1, "url": vn.MAIN_PDF,
            "year": YEAR, "license": vn.LICENCE}]
    out = []
    for sid, parts in sorted(bound.items(), key=lambda kv: names[kv[0]]):
        total = sum(p["n"][0] for p in parts)
        men = sum(p["n"][1] for p in parts)
        women = sum(p["n"][2] for p in parts)
        label = " and ".join(f"{p['name']} ({p['type'].lower()})" for p in parts)
        whose = (f"the 2019 census's count of {label}, {parts[0]['province']}"
                 + (" -- one polygon, drawn before the census divided it" if len(parts) > 1
                    else ""))
        out.append(record(
            f"VNM-D-{key(parts[0]['province'])}-{key(parts[0]['name'])}", names[sid],
            level="admin2", parent="VNM", country="VNM", match_by="shape_id", shape_id=sid,
            aliases=sorted({p["name"] for p in parts if key(p["name"]) != key(names[sid])}),
            sources=src,
            **age_sex(median=None, men=men, women=women, year=YEAR, source=SOURCE_T1,
                      median_note="", ratio_note=f"Males per 100 females in {whose} "
                                                 "(Table 1).",
                      population=total, population_note=f"The 2019 census: {whose} (Table 1).")))
    return out


def province_records(units: dict[str, dict[str, Any]], admin1: list[dict[str, Any]]
                     ) -> list[dict[str, Any]]:
    by_key = {key(u["name"]): u for u in admin1}
    src = [{"field": "median_age", "name": SOURCE_T5, "url": vn.MAIN_PDF, "year": YEAR,
            "license": vn.LICENCE}]
    out = []
    for prov, u in units.items():
        if u["kind"] != "province":
            continue
        shape = by_key.get(key(prov)) or next((by_key[key(a)] for a in vn.PROVINCES[prov]
                                               if key(a) in by_key), None)
        if shape is None:
            raise SystemExit(f"vietnam_district: no first-level polygon for {prov}")
        median = grouped([(lo, hi, n[0]) for lo, hi, n in u["groups"]])
        if median is None:
            raise SystemExit(f"vietnam_district: {prov}: the middle person is in 85+")
        out.append(record(
            f"VNM-AGE-{key(prov)}", shape["name"], level="admin1", parent="VNM", country="VNM",
            match_by="shape_id", shape_id=shape["id"], sources=src,
            median_age={"value": median, "unit": "years", "year": YEAR, "source": SOURCE_T5},
            median_age_note=("Interpolated within the five-year age group that holds the "
                             "middle person, from the 2019 census's count of the province by "
                             "five-year age group to an open 85+ (Table 5); the volume gives "
                             "single years for the country and its regions only.")))
    return out


def first_level_records(rows: list[dict[str, Any]], admin1: list[dict[str, Any]]
                        ) -> list[dict[str, Any]]:
    out = []
    for polygon, (prov, name) in FIRST_LEVEL.items():
        shape = [u for u in admin1 if key(u["name"]) == key(polygon)]
        found = [r for r in rows if r["province"] == prov and key(r["name"]) == key(name)]
        if len(shape) != 1 or len(found) != 1:
            raise SystemExit(f"vietnam_district: {polygon}: {len(shape)} polygons, "
                             f"{len(found)} districts")
        r = found[0]
        whose = f"the 2019 census's count of {name} district, {prov}"
        out.append(record(
            f"VNM-D1-{key(name)}", shape[0]["name"], level="admin1", parent="VNM",
            country="VNM", match_by="shape_id", shape_id=shape[0]["id"],
            sources=[{"field": "population/sex_ratio", "name": SOURCE_T1, "url": vn.MAIN_PDF,
                      "year": YEAR, "license": vn.LICENCE}],
            **age_sex(median=None, men=r["n"][1], women=r["n"][2], year=YEAR, source=SOURCE_T1,
                      median_note="", ratio_note=f"Males per 100 females in {whose} (Table 1).",
                      population=r["n"][0],
                      population_note=(f"The 2019 census: {whose} (Table 1); the boundary "
                                       "file draws the island district at the first level."))))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log(f"vietnam_district: {SOURCE_T1}")
    pdf = download(vn.MAIN_PDF, RAW / "vietnam" / vn.MAIN_PDF.rsplit("/", 1)[-1])
    pages = vn.page_texts(pdf)
    rows, provinces, country = parse_table1(pages)
    check_table1(rows, provinces, country)
    units, singles = parse_age_tables(pages)
    check_ages(units, singles)
    admin1, admin2 = drawn("VNM", "admin1"), drawn("VNM", "admin2")
    undrawn = {(p, key(n)) for p, n in UNDRAWN}
    drawn_rows = [r for r in rows if (r["province"], key(r["name"])) not in undrawn]
    if len(drawn_rows) != len(rows) - len(UNDRAWN):
        raise SystemExit(f"vietnam_district: the undrawn island districts {sorted(UNDRAWN)} "
                         "are not each one census row")
    bound, left_census, left_shapes = bind(drawn_rows, admin1, admin2)
    log(f"  {len(bound)} of {len(admin2)} polygons bound, {sum(len(v) for v in bound.values())} "
        f"of {len(drawn_rows)} census districts; not drawn: "
        + ", ".join(f"{r['name']} ({r['province']}, {r['n'][0]:,})" for r in rows
                    if (r["province"], key(r["name"])) in undrawn))
    if left_census or left_shapes:
        raise SystemExit(f"vietnam_district: census districts on no polygon ({len(left_census)}): "
                         + "; ".join(left_census) + f"; polygons with no census district "
                         f"({len(left_shapes)}): " + "; ".join(left_shapes))
    records = (district_records(bound, admin2) + province_records(units, admin1)
               + first_level_records(rows, admin1))
    meds = sorted(r["median_age"]["value"] for r in records if r["level"] == "admin1"
                  and "value" in r["median_age"])
    rats = sorted(r["sex_ratio"]["value"] for r in records if r["level"] == "admin2")
    log(f"  provinces' medians {meds[0]}-{meds[-1]}; districts' sex ratios {rats[0]}-{rats[-1]}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
