#!/usr/bin/env python3
"""DRC -- why its provinces and territories show no median age or sex ratio, and its towns no figures.

The Democratic Republic of the Congo has taken no census since 1984. The
population the map shows for its provinces and territories is OCHA's 2020
estimate (cod-ps-cod), built from the health zones' figures by the DRC
Information Management Working Group. OCHA's own caveat: "All age and sex
disaggregations are based on estimated ratios at the administrative level 1
(province level)". This reads OCHA's two tables (provinces and territories)
and states, on each record, what is true of them:

* **Provinces**: ages come in four broad groups only (0-4, 5-19, 20-64, 65
  and over), from ratios estimated for the province, which cannot place a
  median; and the table's two splits by sex disagree -- its total columns and
  its age groups give the province different numbers of women and men -- so no
  sex ratio is shown either. Each province's own numbers are quoted.
* **Territories and cities**: each has its province's age structure and
  proportion of men applied to its total (checked here: the shares agree to
  the fourth decimal across every territory of a province), so they describe
  the province, not the territory.
* **Towns drawn apart**: OCHA's table gives fifteen towns no figure of their
  own ("Population is reflected in" a territory's code). Each town's record
  says which territory counts its people. Measured on the polygons (CGAZ,
  October 2026): Aba (68.7 km2) lies inside Faradje, Ariwara (3.7) and
  Ingbokolo (13.0) inside Aru, Baraka (1.5) inside Fizi, Bena-Dibele (21.4)
  and Tshumbe (12.2) inside Kole, Dibaya-Lubwe (6.4) and Mangai (10.3) inside
  Idiofa, Isiro (54.8) inside Rungu, Kamituga (7.8) inside Mwenga, Mongwalu
  (5.1) inside Djugu; Bangu (67.9) on the edge of Songololo and
  Mbanza-Ngungu, Inkisi (44.4) of Madimba and Mbanza-Ngungu, Kalima (158.1)
  of Kailo and Pangi, Namoya (6.8) of Kabambare and Shabunda.
* **Cities with a figure of their own**: Bunia, Kolwezi and Tshikapa carry
  encyclopaedia figures on their polygons while OCHA counts their people in
  Irumu, Mutshatsha and Kamonia; those territories' records say so.

Every statement is checked against the tables as read; a premise no longer
true leaves its record out and says so in the log.

**Capitals.** French Wikipedia's *Territoire (république démocratique du
Congo)* lists each territory with its OCHA code and its seat (*chef-lieu*);
the seat is written for the territory it names.

Usage:
    python -m scripts.fetch_census.drc_gaps [--run LABEL]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, write_json
from .binding import bind, fold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

DATASET = "https://data.humdata.org/dataset/d1160fa9-1d58-4f96-9df5-edbff2e80895"
ADM1 = DATASET + "/resource/44bafdcb-e234-4fa2-9d1a-278715384408/download/cod_admpop_adm1_2020.csv"
ADM2 = DATASET + "/resource/bf8edc01-c28a-470d-9720-cb2d9435dfdf/download/cod_admpop_adm2_2020.csv"
OUT = "drc_gaps.json"
SITE = PROCESSED.parent.parent / "site" / "data"
OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-cod), reference year 2020"
OCHA_URL = "https://data.humdata.org/dataset/cod-ps-cod"
OCHA_LICENCE = "Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO)"
WIKI_TITLE = "Territoire (république démocratique du Congo)"
WIKI_URL = "https://fr.wikipedia.org/wiki/Territoire_(r%C3%A9publique_d%C3%A9mocratique_du_Congo)"

GROUPS = ("00_04", "05_19", "adulte", "agee")
# OCHA's province names -> the map's, where they differ by more than accents.
PROVINCE_AS = {"basuele": "Lower Uele", "hautuele": "Upper Uele", "kasaicentral": "Central Kasai",
               "nordkivu": "North Kivu", "sudkivu": "South Kivu"}
# Town polygons OCHA gives no figure of their own: polygon -> the territories it touches
# (one: drawn inside it; two: on their edge), as measured.
TOWNS: dict[str, tuple[str, ...]] = {
    "Aba": ("Faradje",), "Ariwara": ("Aru",), "Bangu": ("Songololo", "Mbanza-Ngungu"),
    "Baraka": ("Fizi",), "Bena-Dibele": ("Kole",), "Dibaya-Lubwe": ("Idiofa",),
    "Ingbokolo": ("Aru",), "Inkisi": ("Madimba", "Mbanza-Ngungu"), "Isiro": ("Rungu",),
    "Kalima": ("Kailo", "Pangi"), "Kamituga": ("Mwenga",), "Mangai": ("Idiofa",),
    "Mongwalu": ("Djugu",), "Namoya": ("Kabambare", "Shabunda"), "Tshumbe": ("Kole",),
}
# Cities whose polygon carries a figure of its own while OCHA counts them in a territory.
CITIES_COUNTED_IN = {"Bunia": "Irumu", "Kolwezi": "Mutshatsha", "Tshikapa": "Kamonia"}
# Towns another declaration already explains (stated_gaps): left to it.
DECLARED_ELSEWHERE = frozenset({"Tshimbulu", "Lukalaba", "Dingila", "Kasaji", "Kaoze",
                                "Yangambi", "Nioki"})
COPY_TOLERANCE = 1e-3


def rows_of(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def num(row: dict[str, str], key: str) -> int:
    value = (row.get(key) or "").strip()
    return int(float(value)) if value and value != "<Null>" else 0


def sums(row: dict[str, str]) -> dict[str, int]:
    f = sum(num(row, f"F_{g}") for g in GROUPS)
    m = sum(num(row, f"M_{g}") for g in GROUPS)
    return {"f_groups": f, "m_groups": m, "f_total": num(row, "F_TL"), "m_total": num(row, "M_TL")}


def shares(row: dict[str, str]) -> tuple[float, ...] | None:
    """A unit's age-and-sex proportions: each group's share of the total, and men's share."""
    t = [num(row, f"T_{g}") for g in GROUPS]
    total = sum(t)
    f, m = num(row, "F_TL"), num(row, "M_TL")
    if total <= 0 or f + m <= 0:
        return None
    return tuple(x / total for x in t) + (m / (f + m),)


def copied(rows: list[dict[str, str]]) -> bool:
    """Whether every unit of a province has the same proportions (the province's applied)."""
    found = [s for s in (shares(r) for r in rows) if s]
    return len(found) >= 2 and all(
        max(abs(a - b) for a, b in zip(s, found[0])) <= COPY_TOLERANCE for s in found)


def province_fields(name: str, row: dict[str, str]) -> dict[str, Any] | None:
    s = sums(row)
    ages = ("The DRC has taken no census since 1984. OCHA's 2020 estimate for "
            f"{name} gives its people's ages in four broad groups only (under 5, 5 to 19, 20 "
            "to 64, and 65 and over), split from ratios estimated for the province rather than "
            "counted, which cannot place a median age.")
    off = max(abs(s["f_total"] - s["f_groups"]), abs(s["m_total"] - s["m_groups"]))
    if not s["f_total"] or off < 0.005 * (s["f_total"] + s["m_total"]):
        return None
    sexes = (f"OCHA's 2020 estimate for {name} splits its people by sex with ratios estimated "
             f"for the province rather than counted, and its two splits disagree: its totals "
             f"give {s['f_total']:,} women and {s['m_total']:,} men, its age groups "
             f"{s['f_groups']:,} women and {s['m_groups']:,} men. No sex ratio is shown.")
    return {"median_age": gap(NOT_AVAILABLE, ages), "sex_ratio": gap(NOT_AVAILABLE, sexes)}


def territory_fields(province: str) -> dict[str, Any]:
    ages = (f"OCHA's 2020 estimate gives every territory and city of {province} the same age "
            f"structure, {province}'s estimated ratios applied to each one's total, in four broad "
            "groups (under 5, 5 to 19, 20 to 64, and 65 and over). They describe the province, "
            "not this unit, and the DRC has taken no census since 1984, so no median age is "
            "shown.")
    sexes = (f"OCHA's 2020 estimate gives every territory and city of {province} the same "
             f"proportion of men, {province}'s estimated ratio applied to each one's total, so it "
             "describes the province, not this unit, and no sex ratio is shown.")
    return {"median_age": gap(NOT_AVAILABLE, ages), "sex_ratio": gap(NOT_AVAILABLE, sexes)}


def town_note(town: str, touching: tuple[str, ...], counted_in: str) -> str:
    where = (f"drawn inside {touching[0]} territory" if len(touching) == 1
             else f"drawn on the edge of {touching[0]} and {touching[1]} territories")
    return (f"This polygon is the town of {town}, {where}. OCHA's 2020 population estimate for "
            f"the DRC counts its people within {counted_in} territory's figure, shown on that "
            f"territory's polygon, and gives the town no figure of its own, so no population, "
            f"median age or sex ratio is shown here.")


def seats(wikitext: str) -> dict[str, str]:
    """OCHA code -> seat, from the article's table of territories."""
    out: dict[str, str] = {}
    for table in tables(wikitext):
        if not table:
            continue
        head = [fold(c) for c in table[0]]
        code = next((i for i, c in enumerate(head) if c == "pcode"), None)
        seat = next((i for i, c in enumerate(head) if c.startswith("cheflieu")), None)
        if code is None or seat is None:
            continue
        for row in table[1:]:
            if len(row) > max(code, seat) and row[code].strip() and row[seat].strip():
                out[f"CD{row[code].strip()}"] = row[seat].strip()
    return out


def build(adm1: list[dict[str, str]], adm2: list[dict[str, str]], seat_of: dict[str, str],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    cite = [{"field": "median_age/sex_ratio", "name": OCHA, "url": OCHA_URL, "year": 2020,
             "license": OCHA_LICENCE}]
    by_key = {fold(u["name"]): u for u in admin1}
    parents = {u["id"]: u["name"] for u in admin1}

    def map_province(name: str) -> dict[str, Any] | None:
        key = fold(name)
        return by_key.get(fold(PROVINCE_AS.get(key, ""))) or by_key.get(key)

    # Provinces.
    for row in adm1:
        name = row.get("admin1Name_fr", "")
        poly = map_province(name)
        if poly is None:
            report.append(f"  province {name}: no polygon")
            continue
        fields = province_fields(poly["name"], row)
        if fields is None:
            report.append(f"  province {name}: its two sex splits agree; left out")
            continue
        records.append(record(f"COD-GAPS-{poly['id']}", poly["name"], level="admin1",
                              parent="COD", country="COD", match_by="shape_id",
                              shape_id=poly["id"], sources=cite, **fields))
    # Territories and cities, by province.
    by_code = {r["admin2Pcode"]: r for r in adm2}
    counted = [r for r in adm2 if not (r.get("REMARK") or "").strip()]
    in_province: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in counted:
        in_province[r["admin1Pcode"]].append(r)
    units: dict[str, tuple[str, str]] = {}
    for r in adm2:
        poly = map_province(r["admin1Name_fr"])
        units[r["admin2Pcode"]] = (r["admin2Name_fr"], poly["name"] if poly else "")
    bound, missing = bind(units, admin2, parents)
    report += [f"  OCHA unit with no polygon: {m}" for m in missing]
    shapes = {u["id"]: u for u in admin2}
    seat_cite = {"field": "capital", "name": f"French Wikipedia, {WIKI_TITLE}", "url": WIKI_URL,
                 "license": "CC BY-SA 4.0"}
    written = 0
    for code, sid in sorted(bound.items()):
        r = by_code[code]
        shape = shapes[sid]
        if shape["name"] in TOWNS or shape["name"] in DECLARED_ELSEWHERE:
            continue
        if (r.get("REMARK") or "").strip():
            continue
        province = r["admin1Name_fr"]
        shown = (map_province(province) or {}).get("name", province)
        siblings = in_province[r["admin1Pcode"]]
        if len(siblings) == 1:
            # The province's one unit (Kinshasa): its figures are the province's.
            only = province_fields(shown, r)
            if only is None:
                report.append(f"  {province}: its one unit's sex splits agree; no reason written")
                continue
            fields: dict[str, Any] = only
        elif not copied(siblings):
            report.append(f"  {province}: its units' proportions differ; no reason written")
            continue
        else:
            fields = territory_fields(shown)
        sources = list(cite)
        if code in seat_of:
            fields["capital"] = seat_of[code]
            sources.append(seat_cite)
        city = next((c for c, t in CITIES_COUNTED_IN.items() if t == shape["name"]), None)
        if city:
            ocha = next((x for x in adm2 if fold(x["admin2Name_fr"]) == fold(city)), None)
            says = (ocha or {}).get("REMARK", "")
            if not says.endswith(code):
                report.append(f"  {city}: OCHA no longer counts it in {shape['name']} ({says!r})")
            else:
                fields["population_note"] = (
                    f"OCHA's 2020 estimate for {shape['name']} territory includes the people of the "
                    f"city of {city}, which is drawn as a polygon of its own and shown there with a "
                    f"figure of its own, so {city}'s people are counted in both.")
        records.append(record(f"COD-GAPS-{sid}", shape["name"], level="admin2", parent="COD",
                              country="COD", match_by="shape_id", shape_id=sid,
                              sources=sources, **fields))
        written += 1
    report.append(f"  {written} territories and cities given reasons"
                  f" ({sum(1 for c in bound if c in seat_of)} with a seat)")
    # Towns.
    by_name = defaultdict(list)
    for u in admin2:
        by_name[u["name"]].append(u)
    for town, touching in TOWNS.items():
        polys = by_name.get(town, [])
        ocha = [x for x in adm2 if fold(x["admin2Name_fr"]) == fold(town)]
        if len(polys) != 1 or len(ocha) != 1:
            report.append(f"  town {town}: {len(polys)} polygons, {len(ocha)} OCHA rows; left out")
            continue
        says = (ocha[0].get("REMARK") or "").strip()
        target = says.rsplit(" ", 1)[-1] if says.startswith("Population is reflected in") else ""
        counted_in = by_code.get(target, {}).get("admin2Name_fr")
        if not counted_in or fold(counted_in) not in {fold(t) for t in touching}:
            report.append(f"  town {town}: OCHA says {says!r}; left out")
            continue
        note = town_note(town, touching, counted_in)
        records.append(record(
            f"COD-GAPS-{polys[0]['id']}", town, level="admin2", parent="COD", country="COD",
            match_by="shape_id", shape_id=polys[0]["id"], sources=cite,
            population=gap(NOT_AVAILABLE, note), median_age=gap(NOT_AVAILABLE, note),
            sex_ratio=gap(NOT_AVAILABLE, note)))
        report.append(f"  town {town}: counted in {counted_in}")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    from .europe_wiki import fetch as wiki_fetch     # noqa: PLC0415
    adm1 = rows_of(http_get(ADM1, binary=True, cache=False, timeout=180).decode("utf-8"))
    adm2 = rows_of(http_get(ADM2, binary=True, cache=False, timeout=180).decode("utf-8"))
    log(f"drc_gaps: OCHA's tables: {len(adm1)} provinces, {len(adm2)} territories, cities and towns")
    for key in [f"{s}_{g}" for g in GROUPS for s in "FMT"] + ["F_TL", "M_TL"]:
        if key not in (adm1[0] if adm1 else {}):
            raise SystemExit(f"drc_gaps: OCHA's province table has no column {key}; "
                             f"the reasons describe a table that has changed")
    wikitext, landed = wiki_fetch(WIKI_TITLE, "fr")
    seat_of = seats(wikitext)
    log(f"  {landed}: {len(seat_of)} territories with a seat")
    admin1 = json.loads((SITE / "admin1" / "COD.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "COD.units.json").read_text())
    records, report = build(adm1, adm2, seat_of, admin1, admin2)
    for line in report:
        log(line)
    write_json(PROCESSED / OUT, records)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} provinces and "
        f"{sum(r['level'] == 'admin2' for r in records)} second-level polygons written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
