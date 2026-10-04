#!/usr/bin/env python3
"""Myanmar: median age and sex ratio by district and state/region, 2014 census.

The 2014 Myanmar Population and Housing Census counted everyone by sex and
five-year age group, and the US Census Bureau's subnational tables for Burma
(HDX, CC BY; ``uscb.py`` reads the religion sheet of the same workbook) carry
that count -- sheet ``Age-Sex``, columns ``B0004`` ... ``B75PL`` for both
sexes and ``MTOTL`` / ``FTOTL`` -- for every state and region, district,
self-administered zone and township, citing the census's own "Population by
Sex and Age Groups". Nothing finer than five-year groups is published below
the Union, so the median is interpolated within the group holding the middle
person, and the note says so.

**What the map draws is not quite what the census counted.** The census has
74 districts and, beside them, the six self-administered zones and divisions
-- Naga, Danu, Pa-O, Pa Laung, Kokang and Wa -- whose townships belong to no
district. The boundary file draws 74 districts and no zone: the Kokang zone is
its Laukkaing district, the Wa division is its Hopang and Matman districts,
and the townships of the Naga, Danu, Pa-O and Pa Laung zones lie inside its
Hkamti, Taunggyi and Kyaukme districts. A district's census figures would be
the wrong thing to put on those six polygons, so each of them is built from
the census's own townships instead -- the district's townships plus the zone's
that the polygon takes in -- and the note lists them. Every other drawn
district is the census district of that name, matched by name (and by the
romanisations ``ALIASES`` declares, pair by pair). Nay Pyi Taw has no shape of
its own: its two districts are drawn under Mandalay, and are matched there.

**States and regions** are the sum of the districts the map draws inside each
polygon (so Mandalay takes in Nay Pyi Taw), which is what the polygon holds.

**Checks**, each a refusal: every row's age groups and its sexes make its
total; every district's townships make the district; every township and every
district is used exactly once across the 74 polygons; the 74 polygons make
the census's national 50,279,900; and the Union's median recomputed from the
same five-year groups is within 0.3 years of the census's 27.1 (Union report,
the median from single years).

Usage:
    python -m scripts.fetch_census.myanmar_age
    python -m scripts.fetch_census.myanmar_age --list     # the census's units, for the crosswalk
"""

from __future__ import annotations

import argparse
import io
from collections import defaultdict
from typing import Any

from . import uscb
from ._shared import PROCESSED, http_get, log, record, write_json
from .sea_common import age_sex, drawn, fold, grouped
from .uscb_age_sex import groups_of, number

OUT = "myanmar_age.json"
YEAR = 2014
DATASET = "burma-subnational-boundaries-and-tabular-data"
SOURCE = ("Department of Population, 2014 Myanmar Population and Housing Census, population "
          "by sex and five-year age group, as the U.S. Census Bureau tabulates it for HDX")
LICENCE = "CC BY, published via HDX"
NATIONAL = 50_279_900
NATIONAL_MEDIAN = 27.1
MEDIAN_TOLERANCE = 0.3

# The boundary file's district -> the census's, where the romanisations
# differ (uscb.MYANMAR declares the same pairs for the religion sheet).
ALIASES = {
    "Bawlake": "BAWLAKHE", "Hakha": "HAKA", "Kawthoung": "KAWTHAUNG",
    "Kyaukpyu": "KYAUNKPYU", "Langkho": "LANGHKO", "Loilen": "LOILEM",
    "Mrauk-U": "MYAUK U", "Hpapun": "PHARPON", "Thayarwady": "THARRAWADDY",
    "Yinmarbin": "YINMARPIN", "Puta-O": "PUTAO", "Det Khi Na": "DEKKHINA",
    "Oke Ta Ra": "OTTARA",
}
# The six polygons built from townships: the drawn district -> (census
# district or zone, township) pairs. A district named here contributes all
# of its own townships; a zone, only the townships listed.
COMPOSED: dict[str, dict[str, Any]] = {
    "Hkamti": {"districts": ["HKAMTI"], "zone": "NAGA", "townships": ["LAHE", "LESHI", "NANYUN"]},
    "Taunggyi": {"districts": ["TAUNGGYI"], "zone": None,
                 "townships": ["PINDAYA", "YWANGAN", "HOPONG", "HSIHSENG", "PINLAUNG"]},
    "Kyaukme": {"districts": ["KYAUKME"], "zone": "PA LAUNG", "townships": ["NAMHSAN", "MANTON"]},
    "Laukkaing": {"districts": [], "zone": "KOKANG", "townships": ["LAUKKAING", "KONKYAN"]},
    "Hopang": {"districts": [], "zone": "WA", "townships": ["HOPANG", "MONGMAO", "PANWAING"]},
    "Matman": {"districts": [], "zone": "WA", "townships": ["MATMAN", "NAMPHAN", "PANGSANG"]},
}


def read_rows() -> tuple[list[dict[str, Any]], dict[str, int]]:
    import openpyxl
    url = uscb.workbook_url(DATASET)
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Metadata") for c in r if c)
    if str(YEAR) not in meta:
        raise SystemExit(f"myanmar_age: the workbook's metadata never names {YEAR}")
    rows = uscb.sheet_rows(book, "Age-Sex")
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    out = []
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        if level is None:
            continue
        unit = {"level": level,
                "adm1": str(row[at["ADM1_NAME"]] or "").strip(),
                "adm2": str(row[at["ADM2_NAME"]] or "").strip() if level >= 2 else "",
                "adm3": str(row[at["ADM3_NAME"]] or "").strip() if level >= 3 else "",
                "nso": str(row[at["NSO_NAME"]] or "").strip(),
                "total": number(row[at["BTOTL"]]), "men": number(row[at["MTOTL"]]),
                "women": number(row[at["FTOTL"]]), "groups": groups_of(row, at)}
        where = " / ".join(x for x in (unit["adm1"], unit["adm2"], unit["adm3"]) if x)
        if not unit["total"] or unit["men"] is None or unit["women"] is None:
            raise SystemExit(f"myanmar_age: {where}: no total, male or female count")
        made = sum(n for _, _, n in unit["groups"])
        if made != unit["total"] or unit["men"] + unit["women"] != unit["total"]:
            raise SystemExit(f"myanmar_age: {where}: groups make {made:,}, sexes "
                             f"{unit['men'] + unit['women']:,}, against {unit['total']:,}")
        unit["where"] = where
        out.append(unit)
    return out, at


def zone_of(name: str) -> str | None:
    """'NAGA SAZ' / 'WA SAD' / 'Kokang Self-Administered Zone' -> 'NAGA' / 'WA' / 'KOKANG'."""
    up = " ".join(name.upper().replace("-", " ").split())
    for z in ("NAGA", "DANU", "PA O", "PA LAUNG", "KOKANG", "WA"):
        if up.startswith(z + " ") and any(k in up for k in ("SAZ", "SAD", "SELF")):
            return z.replace("PA O", "PA-O")
    return None


def add(units: list[dict[str, Any]]) -> dict[str, Any]:
    """Several census units added together, age group by age group."""
    bands = [(a, b) for a, b, _ in units[0]["groups"]]
    for u in units[1:]:
        if [(a, b) for a, b, _ in u["groups"]] != bands:
            raise SystemExit(f"myanmar_age: {u['where']} has other age groups")
    return {"groups": [(a, b, sum(u["groups"][i][2] for u in units))
                       for i, (a, b) in enumerate(bands)],
            "men": sum(u["men"] for u in units), "women": sum(u["women"] for u in units),
            "total": sum(u["total"] for u in units)}


def check_townships(rows: list[dict[str, Any]]) -> None:
    """Every district's (and zone's) townships make the district."""
    towns = defaultdict(int)
    for r in rows:
        if r["level"] == 3:
            towns[(fold(r["adm1"]), fold(r["adm2"]))] += r["total"]
    for r in rows:
        if r["level"] == 2:
            made = towns.get((fold(r["adm1"]), fold(r["adm2"])))
            if made != r["total"]:
                raise SystemExit(f"myanmar_age: {r['where']}: townships make {made}, "
                                 f"against {r['total']:,}")
    log(f"  every district's and zone's townships make it")


def compose(rows: list[dict[str, Any]], admin2: list[dict[str, Any]]
            ) -> dict[str, dict[str, Any]]:
    """Each drawn district -> its census figures and the parts they came from."""
    districts = [r for r in rows if r["level"] == 2]
    towns = [r for r in rows if r["level"] == 3]
    by_district = defaultdict(list)
    for d in districts:
        by_district[fold(d["adm2"])].append(d)
    used_districts: set[int] = set()
    used_towns: set[int] = set()
    out: dict[str, dict[str, Any]] = {}
    for shape in admin2:
        name = shape["name"]
        if name in COMPOSED:
            spec = COMPOSED[name]
            parts = []
            for dn in spec["districts"]:
                hits = [t for t in towns if fold(t["adm2"]) == fold(dn)]
                if not hits:
                    raise SystemExit(f"myanmar_age: no townships under district {dn}")
                parts.extend(hits)
            for tn in spec["townships"]:
                hits = [t for t in towns if fold(t["adm3"]) == fold(tn)
                        and zone_of(t["adm2"]) is not None
                        and (spec["zone"] is None or zone_of(t["adm2"]) == spec["zone"])]
                if len(hits) != 1:
                    raise SystemExit(f"myanmar_age: {len(hits)} zone townships named {tn} "
                                     f"for {name}")
                parts.extend(hits)
            for p in parts:
                if id(p) in used_towns:
                    raise SystemExit(f"myanmar_age: township {p['where']} used twice")
                used_towns.add(id(p))
            out[shape["id"]] = {**add(parts), "parts": [p["adm3"].title() for p in parts],
                                "kind": "townships"}
            continue
        key = fold(ALIASES.get(name, name))
        hits = by_district.get(key, [])
        if len(hits) != 1:
            raise SystemExit(f"myanmar_age: {len(hits)} census districts for the polygon "
                             f"{name!r} (looked for {ALIASES.get(name, name)!r}); census "
                             f"districts: {sorted({d['adm2'] for d in districts})}")
        d = hits[0]
        if id(d) in used_districts:
            raise SystemExit(f"myanmar_age: census district {d['where']} bound twice")
        used_districts.add(id(d))
        for t in towns:
            if fold(t["adm2"]) == key:
                used_towns.add(id(t))
        out[shape["id"]] = {**add([d]), "parts": [d["adm2"].title()], "kind": "district"}
    left_towns = [t["where"] for t in towns if id(t) not in used_towns]
    if left_towns:
        raise SystemExit(f"myanmar_age: townships on no polygon: {left_towns}")
    total = sum(v["total"] for v in out.values())
    if total != NATIONAL:
        raise SystemExit(f"myanmar_age: the {len(out)} polygons make {total:,}, against the "
                         f"census's {NATIONAL:,}")
    log(f"  {len(out)} polygons: {sum(1 for v in out.values() if v['kind'] == 'district')} "
        f"census districts and {sum(1 for v in out.values() if v['kind'] == 'townships')} "
        f"built from townships; every township used once; they make {total:,}")
    return out


def check_national(rows: list[dict[str, Any]]) -> None:
    union = [r for r in rows if r["level"] == 0]
    if len(union) != 1 or union[0]["total"] != NATIONAL:
        raise SystemExit(f"myanmar_age: the Union row is not the census's {NATIONAL:,}")
    median = grouped(union[0]["groups"])
    if median is None or abs(median - NATIONAL_MEDIAN) > MEDIAN_TOLERANCE:
        raise SystemExit(f"myanmar_age: the Union's median from five-year groups is {median}, "
                         f"against the census's {NATIONAL_MEDIAN}")
    log(f"  Union median from five-year groups {median}, the census's {NATIONAL_MEDIAN}")


def fields(fig: dict[str, Any], whose: str) -> dict[str, Any]:
    median = grouped(fig["groups"])
    if median is None:
        raise SystemExit(f"myanmar_age: {whose}: the middle person is in the open 75+ group")
    return age_sex(median=median, men=fig["men"], women=fig["women"], year=YEAR, source=SOURCE,
                   median_note=(f"Interpolated within the five-year age group that holds the "
                                f"middle person, from the 2014 census's count of {whose} by "
                                f"sex and five-year age group (to an open 75+); the census "
                                f"publishes nothing finer below the Union."),
                   ratio_note=f"Males per 100 females in the 2014 census's count of {whose}.")


def build(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    figs = compose(rows, admin2)
    src = [{"field": "median_age/sex_ratio", "name": SOURCE, "url": uscb.dataset_url(DATASET),
            "year": YEAR, "license": LICENCE}]
    out = []
    for shape in admin2:
        f = figs[shape["id"]]
        whose = (f"the census district of {f['parts'][0]}" if f["kind"] == "district" else
                 f"the townships the boundary file draws in this district "
                 f"({', '.join(f['parts'])})")
        out.append(record(f"MMR-CEN2014-{fold(shape['name'])}", shape["name"], level="admin2",
                          parent="MMR", country="MMR", match_by="shape_id",
                          shape_id=shape["id"], sources=src, **fields(f, whose)))
    for region in admin1:
        kids = [s for s in admin2 if s["parent"] == region["id"]]
        if not kids:
            continue
        f = add([{**figs[s["id"]], "where": s["name"]} for s in kids])
        names = ", ".join(sorted(s["name"] for s in kids))
        out.append(record(f"MMR-CEN2014-R-{fold(region['name'])}", region["name"],
                          level="admin1", parent="MMR", country="MMR", match_by="shape_id",
                          shape_id=region["id"], sources=src,
                          **fields(f, f"the {len(kids)} districts the map draws in this "
                                      f"state or region ({names})")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the census's units and stop")
    args = ap.parse_args()
    log(f"myanmar_age: {SOURCE}")
    rows, _ = read_rows()
    if args.list:
        for r in rows:
            if r["level"] in (1, 2, 3):
                log(f"  L{r['level']} {r['adm1']:18} | {r['adm2']:28} | {r['adm3']:22} | "
                    f"{r['nso'][:40]:40} | {r['total']:>10,}")
        return 0
    check_national(rows)
    check_townships(rows)
    records = build(rows, drawn("MMR", "admin1"), drawn("MMR", "admin2"))
    for level in ("admin1", "admin2"):
        rs = [r for r in records if r["level"] == level]
        meds = sorted(r["median_age"]["value"] for r in rs)
        rats = sorted(r["sex_ratio"]["value"] for r in rs)
        log(f"  {level}: {len(rs)} units; median {meds[0]}-{meds[-1]}; "
            f"sex ratio {rats[0]}-{rats[-1]}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
