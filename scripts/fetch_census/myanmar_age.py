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
district. The boundary file draws 74 districts too, but older ones: Mindat
before Matupi district was cut from it, Katha before Kawlin, Tachileik before
Mong Hpayak, and no zone at all -- the Kokang zone is its Laukkaing district,
the Wa division its Hopang and Matman districts, and the townships of the
Naga, Danu, Pa-O and Pa Laung zones lie inside its Hkamti, Taunggyi and
Kyaukme districts. Those nine polygons are each built from the census's own
units -- whole districts, and a zone's townships -- placed by their seats in
the map's own polygons (``COMPOSED``), and the note lists what each holds.
Every other drawn district is the census district of that name, matched by
name (and by the spellings ``ALIASES`` declares, pair by pair). Nay Pyi Taw
has no shape of its own: its two districts are drawn under Mandalay.

**Population** is written with the ages: the drawn districts' figures on the
map are COD-PS projections for 2023 of the census's own districts, which for
the nine polygons above are not the area drawn.

**States and regions** are the sum of the districts the map draws inside each
polygon (so Mandalay takes in Nay Pyi Taw), which is what the polygon holds.

**Checks**, each a refusal: every row's age groups and its sexes make its
total; every district's and zone's townships make it; every census district
and zone township is used exactly once across the 74 polygons; the polygons
make the census's national 50,279,900; and the Union's median recomputed from
the same five-year groups is within 0.3 years of the census's 27.1.

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

# The boundary file's district -> the census's, where the names differ by
# more than case, accents and spacing (uscb.MYANMAR declares the same
# romanisation pairs for the religion sheet).
ALIASES = {
    "Bawlake": "BAWLAKHE", "Hakha": "HAKA", "Kawthoung": "KAWTHAUNG",
    "Kyaukpyu": "KYAUNKPYU", "Langkho": "LANGHKO", "Loilen": "LOILEM",
    "Mrauk-U": "MYAUK U", "Hpapun": "PHARPON", "Thayarwady": "THARRAWADDY",
    "Yinmarbin": "YINMARPIN", "Maubin": "MA-UBIN", "Muse": "MU SE",
    "Monghsat": "MONG HSAT", "Kale": "KALE DISTRICT", "Tamu": "TAMU DISTRICT",
    "Gangaw": "GANGAW DISTRICT", "Lashio": "LASHIO DISTRICT",
    "Yangon (North)": "YANGON NORTH DISTRICT", "Yangon (East)": "YANGON EAST DISTRICT",
    "Yangon (South)": "YANGON SOUTH DISTRICT", "Yangon (West)": "YANGON",
}
# The polygons that are not one census district. The boundary file is older
# than the 2014 census's districts: it draws Mindat before Matupi district
# was cut from it, Katha before Kawlin, Tachileik before Mong Hpayak, and no
# self-administered zone at all -- the Naga zone's townships lie in its
# Hkamti, the Danu and Pa-O zones' in its Taunggyi, the Pa Laung zone's in
# its Kyaukme, the Kokang zone is its Laukkaing and the Wa division its
# Hopang and Matman. Each township's seat was placed in the map's own
# polygons (site/tiles/admin2.pmtiles, zoom 8), and the Wa division's six
# townships split three and three, north and south, as the two polygons do
# (Hopang 22.70-23.49 N, Matman 21.48-22.89 N). A drawn district here takes
# whole census districts, and the listed townships of a zone.
COMPOSED: dict[str, dict[str, Any]] = {
    "Mindat": {"districts": ["MINDAT", "MATUPI"]},
    "Katha": {"districts": ["KATHA", "KAWLIN"]},
    "Tachileik": {"districts": ["TACHILEIK", "MONG HPAYAK"]},
    "Hkamti": {"districts": ["HKAMTI"], "zones": {"NAGA": ["LAY SHI", "LAHE", "NANYUN"]}},
    "Taunggyi": {"districts": ["TAUNGGYI"],
                 "zones": {"DANU": ["PINDAYA", "YWANGAN"],
                           "PAO": ["HOPONG", "HSIHSENG", "PINLAUNG"]}},
    "Kyaukme": {"districts": ["KYAUKME"], "zones": {"PALAUNG": ["NAMHSAN", "MANTON"]}},
    "Laukkaing": {"districts": [], "zones": {"KOKANG": ["LAUKINE", "KONKYAN"]}},
    "Hopang": {"districts": [], "zones": {"WA": ["HOPAN", "MONGMAO", "PANGWAUN"]}},
    "Matman": {"districts": [], "zones": {"WA": ["MAKMAN", "NARPHAN", "PANGSANG"]}},
}
ZONES = ("NAGA", "DANU", "PAO", "PALAUNG", "KOKANG", "WA")


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
    """'NAGA SELF-ADMINISTERED ZONE' -> 'NAGA', 'WA SELF-ADMINISTERED DIVISION' -> 'WA'."""
    key = fold(name)
    if "selfadministered" not in key:
        return None
    hits = [z for z in ZONES if key.startswith(fold(z) + "selfadministered")]
    return hits[0] if len(hits) == 1 else None


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
    """Each drawn district -> its census figures and the parts they came from.

    Every census district and every township of a zone must be used exactly
    once across the polygons, and the polygons must make the Union.
    """
    districts = [r for r in rows if r["level"] == 2 and zone_of(r["adm2"]) is None]
    zone_towns = [r for r in rows if r["level"] == 3 and zone_of(r["adm2"]) is not None]
    used: dict[int, str] = {}

    def take(unit: dict[str, Any], polygon: str) -> dict[str, Any]:
        if id(unit) in used:
            raise SystemExit(f"myanmar_age: {unit['where']} is in both {used[id(unit)]!r} "
                             f"and {polygon!r}")
        used[id(unit)] = polygon
        return unit

    def district(name: str, polygon: str) -> dict[str, Any]:
        hits = [d for d in districts if fold(d["adm2"]) == fold(name)]
        if len(hits) != 1:
            raise SystemExit(f"myanmar_age: {len(hits)} census districts named {name!r} for "
                             f"the polygon {polygon!r}; census districts: "
                             f"{sorted(d['adm2'] for d in districts)}")
        return take(hits[0], polygon)

    out: dict[str, dict[str, Any]] = {}
    for shape in admin2:
        name = shape["name"]
        spec = COMPOSED.get(name)
        if spec is None:
            d = district(ALIASES.get(name, name), name)
            out[shape["id"]] = {**add([d]), "parts": [d["adm2"].title()], "kind": "district"}
            continue
        parts = [district(dn, name) for dn in spec["districts"]]
        labels = [f"{p['adm2'].title()} district" for p in parts]
        for zone, townships in (spec.get("zones") or {}).items():
            for tn in townships:
                hits = [t for t in zone_towns if zone_of(t["adm2"]) == zone
                        and fold(t["adm3"]) == fold(tn)]
                if len(hits) != 1:
                    raise SystemExit(f"myanmar_age: {len(hits)} townships named {tn} in the "
                                     f"{zone} zone, for the polygon {name!r}")
                parts.append(take(hits[0], name))
            labels.append(f"{', '.join(t.title() for t in townships)} of the "
                          f"{zone.title() if zone != 'PAO' else 'Pa-O'} "
                          f"self-administered {'division' if zone == 'WA' else 'zone'}")
        out[shape["id"]] = {**add(parts), "parts": labels, "kind": "composed"}
    left = [u["where"] for u in districts + zone_towns if id(u) not in used]
    if left:
        raise SystemExit(f"myanmar_age: census units on no polygon: {left}")
    total = sum(v["total"] for v in out.values())
    if total != NATIONAL:
        raise SystemExit(f"myanmar_age: the {len(out)} polygons make {total:,}, against the "
                         f"census's {NATIONAL:,}")
    log(f"  {len(out)} polygons: {sum(1 for v in out.values() if v['kind'] == 'district')} "
        f"census districts and {sum(1 for v in out.values() if v['kind'] == 'composed')} "
        f"composed; every census district and zone township used once; they make {total:,}")
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


def fields(fig: dict[str, Any], whose: str, population: bool) -> dict[str, Any]:
    median = grouped(fig["groups"])
    if median is None:
        raise SystemExit(f"myanmar_age: {whose}: the middle person is in the open 75+ group")
    return age_sex(median=median, men=fig["men"], women=fig["women"], year=YEAR, source=SOURCE,
                   median_note=(f"Interpolated within the five-year age group that holds the "
                                f"middle person, from the 2014 census's count of {whose} by "
                                f"sex and five-year age group (to an open 75+); the census "
                                f"publishes nothing finer below the Union."),
                   ratio_note=f"Males per 100 females in the 2014 census's count of {whose}.",
                   population=fig["total"] if population else None,
                   population_note=(f"The 2014 census's count of {whose}."
                                    if population else None))


def build(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    figs = compose(rows, admin2)
    src = [{"field": "median_age/sex_ratio", "name": SOURCE, "url": uscb.dataset_url(DATASET),
            "year": YEAR, "license": LICENCE}]
    out = []
    for shape in admin2:
        f = figs[shape["id"]]
        whose = (f"the census district of {f['parts'][0]}" if f["kind"] == "district" else
                 f"everyone in what the boundary file draws as this district, which the "
                 f"2014 census counted as {'; '.join(f['parts'])}")
        out.append(record(f"MMR-CEN2014-{fold(shape['name'])}", shape["name"], level="admin2",
                          parent="MMR", country="MMR", match_by="shape_id",
                          shape_id=shape["id"],
                          sources=[{**src[0], "field": "population/median_age/sex_ratio"}],
                          **fields(f, whose, population=True)))
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
                                      f"state or region ({names})", population=False)))
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
