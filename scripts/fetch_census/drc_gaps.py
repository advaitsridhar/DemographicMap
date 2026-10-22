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
the seat is written for the territory it names, by name and province (the
article's codes are not all OCHA's), Makanza under the article's spelling,
Mankanza. The cities OCHA lists beside the territories (CITIES) are their
own seats, Beni among them although the article names a territory Beni:
OCHA's Beni is the city, and its territory of Beni is the polygon "Oïcha",
whose seat sources place at Beni or at Oïcha, so none is written. A unit
neither listed nor a city gets no seat and is logged.

**2024.** OCHA's humanitarian planning projection for 2024
(drc-hpc-projection-population-2024.xlsx, in cod-ps-cod) gives every health
zone's population with its territory's code; added up by territory, it is a
2024 figure for each of the 164 territories and cities. It is written to
drc_hpc.json, whose rows the build holds behind OCHA's 2020 table
(HELD_ROWS) and shows where the change from 2020 is one a population makes:
the workbook raises each province's 2020 figures by one factor, from 4.8% a
year down (Ituri) to 18% a year up (Kongo-Central).

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

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import bind, fold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

DATASET = "https://data.humdata.org/dataset/d1160fa9-1d58-4f96-9df5-edbff2e80895"
ADM1 = DATASET + "/resource/44bafdcb-e234-4fa2-9d1a-278715384408/download/cod_admpop_adm1_2020.csv"
ADM2 = DATASET + "/resource/bf8edc01-c28a-470d-9720-cb2d9435dfdf/download/cod_admpop_adm2_2020.csv"
HPC = (DATASET + "/resource/9509b41f-efb2-4305-ac43-1e735e3efc60/download/"
       "drc-hpc-projection-population-2024.xlsx")
HPC_YEAR = 2024
HPC_SOURCE = ("OCHA, Common Operational Dataset -- population statistics (cod-ps-cod), "
              "humanitarian planning projection for 2024 by health zone")
HPC_OUT = "drc_hpc.json"
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
# OCHA's names of territories the article spells otherwise (folded).
SEAT_ALIASES = {"makanza": "mankanza"}
# The cities OCHA's table lists beside the territories, each its own seat
# (folded). Beni is the city: OCHA names the territory of Beni after Oïcha.
CITIES = frozenset({"matadi", "boma", "bandundu", "kikwit", "mbandaka", "zongo", "gbadolite",
                    "kisangani", "goma", "butembo", "beni", "bukavu", "kindu", "lubumbashi",
                    "likasi", "mweneditu", "mbujimayi", "kananga"})
# OCHA units that are a territory under another name, and why no seat is written.
NO_SEAT = {
    "oicha": ("This polygon is the territory of Beni, which OCHA's population tables name "
              "Oïcha; published sources place the territory's seat either at Beni, a city "
              "drawn apart as a polygon of its own, or at Oïcha, so no seat is shown."),
}


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
    if not s["f_total"] or not s["f_groups"]:
        return None
    off = max(abs(s["f_total"] - s["f_groups"]), abs(s["m_total"] - s["m_groups"]))
    if off >= 0.005 * (s["f_total"] + s["m_total"]):
        sexes = (f"OCHA's 2020 estimate for {name} splits its people by sex with ratios estimated "
                 f"for the province rather than counted, and its two splits disagree: its totals "
                 f"give {s['f_total']:,} women and {s['m_total']:,} men, its age groups "
                 f"{s['f_groups']:,} women and {s['m_groups']:,} men. No sex ratio is shown.")
    else:
        sexes = (f"OCHA's 2020 estimate for {name} splits its people by sex with a ratio estimated "
                 f"for the province rather than counted, and the DRC has taken no census since "
                 f"1984 that would count it, so no sex ratio is shown.")
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


def seats(wikitext: str) -> dict[tuple[str, str], str]:
    """(territory, province), folded -> seat, from the article's table of territories.

    By name and province, not by the table's codes: some of those are not
    OCHA's (it gives 9102, OCHA's code for Dibaya, to Kamonia).
    """
    out: dict[tuple[str, str], str] = {}
    for table in tables(wikitext):
        if not table:
            continue
        head = [fold(c) for c in table[0]]
        name = next((i for i, c in enumerate(head) if c.startswith("territoire")), None)
        seat = next((i for i, c in enumerate(head) if c.startswith("cheflieu")), None)
        province = next((i for i, c in enumerate(head) if c.startswith("province")), None)
        if name is None or seat is None or province is None:
            continue
        for row in table[1:]:
            if len(row) > max(name, seat, province) and row[name].strip() and row[seat].strip():
                out[(fold(row[name]), fold(row[province]))] = row[seat].strip()
    return out


def build(adm1: list[dict[str, str]], adm2: list[dict[str, str]], seat_of: dict[str, str],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    # OCHA's table is what the reasons rest on; it gives none of these figures.
    cite = [{"field": "median_age note/sex_ratio note", "name": OCHA, "url": OCHA_URL,
             "year": 2020, "license": OCHA_LICENCE}]
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
            report.append(f"  province {name}: no totals by sex; left out")
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
    written = seated = cities = 0
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
        name_key = fold(r["admin2Name_fr"])
        seat = seat_of.get((SEAT_ALIASES.get(name_key, name_key), fold(province)))
        if len(siblings) == 1:
            # The province's one unit is the city that is the province.
            fields["capital"] = shape["name"]
            fields["capital_note"] = (f"{shown} is a city-province, one city, whose seat is the "
                                      f"city itself.")
            cities += 1
        elif name_key in CITIES:
            # One of the cities OCHA lists beside the territories, whose seat is
            # the city itself (the article's territory of Beni is not OCHA's Beni).
            fields["capital"] = shape["name"]
            fields["capital_note"] = (f"{shape['name']} is a city administered apart from the "
                                      f"territories of {shown}; its seat is the city itself.")
            cities += 1
        elif name_key in NO_SEAT:
            fields["capital"] = gap(NOT_AVAILABLE, NO_SEAT[name_key])
            report.append(f"  {shape['name']}: no seat written ({NO_SEAT[name_key][:60]}...)")
        elif seat:
            fields["capital"] = seat
            seated += 1
            sources.append(seat_cite)
        else:
            report.append(f"  {shape['name']} ({province}): neither a listed territory nor a "
                          f"known city; no seat written")
        city = next((c for c, t in CITIES_COUNTED_IN.items() if t == shape["name"]), None)
        if city:
            ocha = next((x for x in adm2 if fold(x["admin2Name_fr"]) == fold(city)), None)
            says = (ocha or {}).get("REMARK", "")
            if not says.endswith(code):
                report.append(f"  {city}: OCHA no longer counts it in {shape['name']} ({says!r})")
            else:
                fields["population_note"] = (
                    f"OCHA's estimate for {shape['name']} territory includes the people of the "
                    f"city of {city}, which is drawn as a polygon of its own and shown there with a "
                    f"figure of its own, so {city}'s people are counted in both.")
                sources = [{**src, "field": f"{src['field']}/population note"}
                           if src["name"] == OCHA else src for src in sources]
        records.append(record(f"COD-GAPS-{sid}", shape["name"], level="admin2", parent="COD",
                              country="COD", match_by="shape_id", shape_id=sid,
                              sources=sources, **fields))
        written += 1
    report.append(f"  {written} territories and cities given reasons"
                  f" ({seated} territories with a seat, {cities} cities)")
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
            match_by="shape_id", shape_id=polys[0]["id"],
            sources=[{**cite[0], "field": "population note/median_age note/sex_ratio note"}],
            population=gap(NOT_AVAILABLE, note), median_age=gap(NOT_AVAILABLE, note),
            sex_ratio=gap(NOT_AVAILABLE, note), **own_seat(town)))
        report.append(f"  town {town}: counted in {counted_in}")
    # The towns another declaration explains: only their seat, which is the town.
    for town in sorted(DECLARED_ELSEWHERE):
        polys = by_name.get(town, [])
        if len(polys) == 1:
            records.append(record(
                f"COD-GAPS-{polys[0]['id']}", town, level="admin2", parent="COD", country="COD",
                match_by="shape_id", shape_id=polys[0]["id"], sources=[], **own_seat(town)))
    # Cities OCHA counts in a territory, which carry a figure of their own from elsewhere.
    for city, territory in CITIES_COUNTED_IN.items():
        polys = by_name.get(city, [])
        ocha = [x for x in adm2 if fold(x["admin2Name_fr"]) == fold(city)]
        says = (ocha[0].get("REMARK") or "").strip() if len(ocha) == 1 else ""
        target = by_code.get(says.rsplit(" ", 1)[-1], {}).get("admin2Name_fr", "")
        if len(polys) != 1 or fold(target) != fold(territory):
            report.append(f"  city {city}: OCHA says {says!r}; left out")
            continue
        why = (f"OCHA's 2020 estimate for the DRC counts the people of the city of {city} within "
               f"{territory} territory, with that territory's estimated ratios, and gives the "
               f"city no ages or sexes of its own, so no median age or sex ratio is shown here.")
        records.append(record(
            f"COD-GAPS-{polys[0]['id']}", city, level="admin2", parent="COD", country="COD",
            match_by="shape_id", shape_id=polys[0]["id"], sources=cite,
            median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
            **own_seat(city, "city")))
        report.append(f"  city {city}: counted in {territory}")
    return records, report


def hpc_sums(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """The 2024 workbook's health zones added up by territory code:
    {code: {"name", "province", "total", "zones"}}."""
    head = [str(c or "").strip() for c in rows[0]]
    code_col = next(i for i, h in enumerate(head) if fold(h).startswith("codeterr"))
    name_col = head.index("Territoire")
    prov_col = head.index("Province")
    pop_col = next(i for i, h in enumerate(head) if fold(h) == f"population{HPC_YEAR}")
    out: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        if len(row) <= pop_col or not row[code_col]:
            continue
        value = row[pop_col]
        if not isinstance(value, (int, float)):
            continue
        entry = out.setdefault(str(row[code_col]).strip(), {
            "name": str(row[name_col] or "").strip(), "province": str(row[prov_col] or "").strip(),
            "total": 0.0, "zones": 0})
        entry["total"] += value
        entry["zones"] += 1
    return out


def total_2020(row: dict[str, str]) -> int:
    """A unit's 2020 estimate: T_TL, or its women and men added up."""
    return num(row, "T_TL") or num(row, "F_TL") + num(row, "M_TL")


# Two units' 2024/2020 ratios this close (relative) are one factor applied to both.
FACTOR_TOLERANCE = 5e-4


def province_factors(pairs: dict[str, list[tuple[int, float]]]) -> dict[str, float]:
    """Province -> the one factor the 2024 table applies to all its units' 2020
    estimates, where every unit of it carries the same one; ``pairs`` gives each
    province's (2020 estimate, 2024 figure) pairs."""
    out: dict[str, float] = {}
    for province, got in pairs.items():
        ratios = sorted(new / old for old, new in got if old > 0)
        if len(ratios) < 2:
            continue
        middle = ratios[len(ratios) // 2]
        if all(abs(r / middle - 1) <= FACTOR_TOLERANCE for r in ratios):
            out[province] = middle
    return out


def hpc_build(sums: dict[str, dict[str, Any]], adm2: list[dict[str, str]],
              admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
              ) -> tuple[list[dict[str, Any]], list[str]]:
    """Each territory's and city's 2024 sum, on the polygon OCHA's 2020 row of the same
    unit reaches; the build holds these behind the 2020 figures (HELD_ROWS).

    The unit is the 2020 row of the workbook's code where that row has the
    workbook's name; otherwise the one 2020 row of the workbook's name in its
    province (the workbook codes Kasongo-Lunda CD3106, the 2020 table CD3107),
    and every such match is logged. Each note says by what factor the workbook
    raises its province's 2020 estimates, where it raises all of them by one."""
    by_key = {fold(u["name"]): u for u in admin1}
    parents = {u["id"]: u["name"] for u in admin1}

    def map_province(name: str) -> dict[str, Any] | None:
        key = fold(name)
        return by_key.get(fold(PROVINCE_AS.get(key, ""))) or by_key.get(key)

    counted = {r["admin2Pcode"]: r for r in adm2 if not (r.get("REMARK") or "").strip()}
    units = {code: (r["admin2Name_fr"], (map_province(r["admin1Name_fr"]) or {}).get("name", ""))
             for code, r in counted.items()}
    bound, _ = bind(units, admin2, parents)
    shapes = {u["id"]: u for u in admin2}
    named: dict[tuple[str, str], list[str]] = defaultdict(list)
    for code, r in counted.items():
        named[(fold(r["admin1Name_fr"]), fold(r["admin2Name_fr"]))].append(code)
    report: list[str] = []
    # 2020 code -> the workbook's codes that are that unit.
    taken: dict[str, list[str]] = defaultdict(list)
    for code, entry in sorted(sums.items()):
        own = counted.get(code)
        if own is not None and fold(own["admin2Name_fr"]) == fold(entry["name"]):
            taken[code].append(code)
            continue
        same = named.get((fold(entry["province"]), fold(entry["name"])), [])
        if len(same) == 1:
            report.append(f"  2024: {code} {entry['name']} ({entry['province']}) is the 2020 "
                          f"table's {same[0]} "
                          f"{counted[same[0]]['admin2Name_fr']}, matched by name in its province"
                          + (f"; the 2020 table's {code} is {own['admin2Name_fr']}" if own else ""))
            taken[same[0]].append(code)
        else:
            report.append(f"  2024: {code} {entry['name']} ({entry['province']}): no 2020 unit "
                          f"of that code and name ({len(same)} of that name in its province)")
    pairs: dict[str, list[tuple[int, float]]] = defaultdict(list)
    chosen: list[tuple[str, str, dict[str, Any]]] = []
    for old, codes in sorted(taken.items()):
        if len(codes) > 1:
            report.append(f"  2024: {', '.join(codes)} are all the 2020 table's {old}; left out")
            continue
        entry = sums[codes[0]]
        pairs[counted[old]["admin1Name_fr"]].append((total_2020(counted[old]), entry["total"]))
        sid = bound.get(old)
        if sid is None:
            report.append(f"  2024: {codes[0]} {entry['name']}: the 2020 unit {old} is on no "
                          f"polygon")
            continue
        chosen.append((old, sid, entry))
    factors = province_factors(pairs)
    for province, factor in sorted(factors.items()):
        report.append(f"  2024: {province}: every unit's 2020 estimate x{factor:.4f}")
    for province in sorted(set(pairs) - set(factors)):
        report.append(f"  2024: {province}: " + ("one unit" if len(pairs[province]) < 2 else
                                                  "its units' 2024/2020 ratios differ"))
    records: list[dict[str, Any]] = []
    for old, sid, entry in chosen:
        name = shapes[sid]["name"]
        if name in TOWNS or name in DECLARED_ELSEWHERE:
            continue
        zones = entry["zones"]
        province = counted[old]["admin1Name_fr"]
        shown = (map_province(province) or {}).get("name") or province
        note = (f"OCHA's projected population of {name} for {HPC_YEAR}, made for humanitarian "
                f"planning: its "
                + (f"{zones} health zones' figures added up." if zones > 1
                   else "health zone's figure."))
        if province in factors:
            note += (f" The projection is OCHA's 2020 estimate for every territory and city of "
                     f"{shown} multiplied by {factors[province]:.2f}.")
        records.append(record(
            f"COD-HPC{HPC_YEAR}-{sid}", name, level="admin2", parent="COD", country="COD",
            match_by="shape_id", shape_id=sid,
            population=measure(round(entry["total"]), year=HPC_YEAR, source=HPC_SOURCE),
            population_note=note,
            sources=[{"field": "population", "name": HPC_SOURCE, "url": OCHA_URL,
                      "year": HPC_YEAR, "license": OCHA_LICENCE},
                     {"field": "population note", "name": OCHA, "url": OCHA_URL, "year": 2020,
                      "license": OCHA_LICENCE}]))
    report.append(f"  2024: {len(records)} territories and cities, "
                  f"{sum(r['population']['value'] for r in records):,} people")
    return records, report


def own_seat(name: str, kind: str = "town") -> dict[str, Any]:
    """A town or city drawn as a polygon of its own is its own seat."""
    return {"capital": name,
            "capital_note": f"This polygon is the {kind} of {name}, whose seat is the {kind} itself."}


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
    import openpyxl                                  # noqa: PLC0415
    blob = http_get(HPC, binary=True, cache=False, timeout=300)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = next(ws for ws in book.worksheets if "health_zone" in ws.title)
    sums = hpc_sums([list(r) for r in sheet.iter_rows(values_only=True)])
    log(f"  {sheet.title}: {sum(e['zones'] for e in sums.values())} health zones in "
        f"{len(sums)} territories and cities, {sum(e['total'] for e in sums.values()):,.0f} people")
    held, lines = hpc_build(sums, adm2, admin1, admin2)
    for line in lines:
        log(line)
    write_json(PROCESSED / HPC_OUT, held)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
