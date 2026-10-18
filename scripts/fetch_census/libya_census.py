#!/usr/bin/env python3
"""Libya -- the 2006 census: head count, median age and sex ratio for the areas drawn.

The Bureau of Statistics and Census counted Libya on 15 April 2006 and
published, in the census's Table (10), the total resident population --
Libyans and non-Libyans -- by mahallah, five-year age group and sex. The US
Census Bureau's subnational tables for HDX carry that table whole, summed to
the 100 baladiyat and the 22 shabiyat of the time, with the census's own codes
(``libya-subnational-boundaries-and-tabular-data``, sheet ``Age-Sex``). No
later count exists: the 2012 figures beside it in the same workbook are the
Bureau's National Population Survey, a sample, and the population figures
since are estimates.

**The areas drawn are not quite the census's shabiyat.** The map draws 22
areas, twice (both levels, the same outlines and ids), and five carry the
names of districts of the 2001 division (Ajdabiya, Al Qubbah, Ghadamis,
Mizdah, Tajura' wa an Nawahi al Arba) where the census's shabiyat are Al
Wahat, Darnah, Nalut, Al Jabal al Gharbi and Tripoli. Placing each baladiyah's
seat (GeoNames) in the outlines shows where the two differ: the outline
labelled Al Marj holds Al Abyar and Tocra, which the census counts with
Benghazi; Al Jabal al Akhdar holds Al Abraq (the census's Darnah); Al Marqab
holds Zliten (the census's Misrata); Az Zawiyah holds Janzur, Al Mayah, Az
Zahra and As Sawani (the census's Al Jafarah); and the outline labelled
Tajura' wa an Nawahi al Arba holds Garabulli and Qasr Khiyar (the census's Al
Marqab) and Qasr bin Ghashir (Al Jafarah) besides Tripoli.

**What is written.** Every area is the sum of the census's baladiyat whose
seats lie in it, age group by age group (``MOVED`` declares the baladiyat
that lie outside their census shabiyah), so its count, its median age --
interpolated within the five-year group holding the middle person -- and its
men per 1,000 women are the census's own for that ground. Two areas are left
without figures and say why (``UNSURE``): the outline labelled Tajura' wa an
Nawahi al Arba and Al Jifarah, between which three baladiyat of the census's
Al Jafarah (Sidi as Sayih, Suq al Khamis, As Sabiah) cannot be placed.

**Checks before anything is written.** Every row's age groups and its men and
women make its total; the 22 shabiyat make the national row, 5,657,692; each
shabiyah's baladiyat and its mahallat make it; every baladiyah lands on one
area; every drawn area is bound to one record.

Usage:
    python -m scripts.fetch_census.libya_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
from typing import Any

from . import uscb
from ._shared import PROCESSED, NOT_AVAILABLE, gap, http_get, log, measure, record, write_json

DATASET = "libya-subnational-boundaries-and-tabular-data"
YEAR = 2006
NATIONAL = 5_657_692
OUT = "libya_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Bureau of Statistics and Census Libya, General Population Census 2006, Table (10): "
          "total resident population (Libyans and non-Libyans) by mahallah, age group and sex, "
          "as the US Census Bureau tabulates it for HDX")
LICENCE = "Creative Commons Attribution International (CC BY), published via HDX"

# The census's shabiyah (folded, as the Bureau spells it) -> the boundary
# file's shape id of the area that holds its seat.
SHAPES: dict[str, str] = {
    "albutnan": "10800210B28216506156245",
    "darnah": "10800210B44488917334986",             # labelled Al Qubbah
    "aljabalalakhdar": "10800210B23470577588067",
    "almarj": "10800210B54463644997685",
    "banghazi": "10800210B74925506200485",
    "alwahat": "10800210B39782956615971",            # labelled Ajdabiya
    "alkufrah": "10800210B89898169718474",
    "surt": "10800210B41812565387288",
    "misratah": "10800210B58781405840719",
    "almarqab": "10800210B66581866957995",
    "tarabulus": "10800210B53685260454781",          # labelled Tajura' wa an Nawahi al Arba
    "aljafarah": "10800210B86029592505559",
    "azzawiyah": "10800210B15874653580067",
    "annuqatalkhams": "10800210B63841479422356",
    "aljabalalgharbi": "10800210B39461050964926",    # labelled Mizdah
    "nalut": "10800210B65194490964920",              # labelled Ghadamis
    "aljufrah": "10800210B94224648391824",
    "wadiashshati": "10800210B20515568933500",
    "sabha": "10800210B80153830865201",
    "wadialhayat": "10800210B2800497533490",
    "ghat": "10800210B26344076542723",
    "murzuq": "10800210B53073192190863",
}
# The five areas whose label is a district of the 2001 division: the name of
# the census's shabiyah each draws, and what that shabiyah holds, for the
# note. Every other area keeps its label, its shabiyah's name in another
# spelling.
RELABELLED: dict[str, tuple[str, str]] = {
    "darnah": ("Darnah", "Derna and Al Qubbah"),
    "alwahat": ("Al Wahat", "Ajdabiya and the oases of Jalu, Awjila and Marada"),
    "tarabulus": ("Tripoli", "Tripoli with Tajura and its outskirts"),
    "aljabalalgharbi": ("Al Jabal al Gharbi", "Gharyan, Yafran and Mizda"),
    "nalut": ("Nalut", "Nalut and Ghadames"),
}
# Baladiyat whose seat lies in an area other than their census shabiyah's,
# by GeoNames' point for the seat: (shabiyah, baladiyah), folded -> the
# shabiyah key of the area that holds it.
MOVED: dict[tuple[str, str], str] = {
    ("banghazi", "alibyar"): "almarj",            # Al Abyar, 32.19N 20.60E
    ("banghazi", "tukrah"): "almarj",             # Tocra, 32.53N 20.58E
    ("darnah", "alabraq"): "aljabalalakhdar",     # Al Abraq
    ("misratah", "zlitan"): "almarqab",           # Zliten, 32.47N 14.57E
    ("almarqab", "alqarabulli"): "tarabulus",     # Garabulli, 32.75N 13.71E
    ("almarqab", "qasralkhayar"): "tarabulus",    # Qasr Khiyar, 32.70N 13.85E
    ("aljafarah", "qasrbinghashir"): "tarabulus",
    ("aljafarah", "janzur"): "azzawiyah",         # Janzur, 32.82N 13.01E
    ("aljafarah", "almayah"): "azzawiyah",
    ("aljafarah", "azzahra"): "azzawiyah",
    ("aljafarah", "sawanibinadam"): "azzawiyah",  # As Sawani, 32.72N 13.07E
}
# Areas left without figures, and why: three of the census's Al Jafarah
# baladiyat could lie in either.
# An encyclopaedia's figure older than this year, or undated, gives way to an
# UNSURE area's reason: none of them is for the ground drawn.
DISPLACES_BEFORE = 2026
UNSURE: dict[str, str] = {
    key: ("The 2006 census counts this area's people in baladiyat of which three -- Sidi as "
          "Sayih, Suq al Khamis and As Sabiah, about 66,000 people -- lie on or near the line "
          "between the areas shown as Al Jifarah and as Tripoli, which do not follow the "
          "census's shabiyat; no count for this area as shown can be made from them, so none "
          "is shown.")
    for key in ("tarabulus", "aljafarah")}
GROUP = re.compile(r"^([BMF])(\d{2})(\d{2})$")
OPEN = re.compile(r"^([BMF])(\d{2})PL$")


def fold(text: Any) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalpha())


def number(value: Any) -> int | None:
    got = uscb.number(value)
    return None if got is None else int(round(got))


def grouped_median(groups: list[tuple[int, int | None, int]]) -> float | None:
    """The median of (low, high, people) groups; None if it falls in the open one."""
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def columns(names: list[str]) -> dict[str, list[tuple[int, int | None, int]]]:
    """Per sex letter, (low, high, column index) for each age group, youngest first."""
    out: dict[str, list[tuple[int, int | None, int]]] = {"B": [], "M": [], "F": []}
    for i, name in enumerate(names):
        if m := GROUP.match(name):
            out[m.group(1)].append((int(m.group(2)), int(m.group(3)), i))
        elif m := OPEN.match(name):
            out[m.group(1)].append((int(m.group(2)), None, i))
    for sex, groups in out.items():
        groups.sort(key=lambda g: g[0])
        edge = 0
        for low, high, _ in groups:
            if low != edge:
                raise SystemExit(f"libya_census: the {sex} age groups do not run from 0 "
                                 f"without a gap: {groups}")
            edge = (high + 1) if high is not None else None
        if not groups or groups[-1][1] is not None:
            raise SystemExit(f"libya_census: no open-ended last {sex} age group")
    return out


def read(rows: list[list[Any]]) -> dict[str, Any]:
    """The national row, the shabiyat, their baladiyat and their mahallat."""
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    groups = columns(names)
    out: dict[str, Any] = {"national": None, "shabiyat": {}, "below": {}, "baladiyat": []}
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        if level is None:
            continue
        name = str(row[at["AREA_NAME"]] or "").strip()
        total = number(row[at["BTOTL"]])
        men, women = number(row[at["MTOTL"]]), number(row[at["FTOTL"]])
        if total is None or men is None or women is None:
            raise SystemExit(f"libya_census: {name}: no total, male or female count")
        ages = [(lo, hi, number(row[i]) or 0) for lo, hi, i in groups["B"]]
        for sex, made in (("B", sum(n for _, _, n in ages)), ("sexes", men + women),
                          ("M", sum(number(row[i]) or 0 for _, _, i in groups["M"])),
                          ("F", sum(number(row[i]) or 0 for _, _, i in groups["F"]))):
            want = {"M": men, "F": women}.get(sex, total)
            if made != want:
                raise SystemExit(f"libya_census: {name}: the {sex} figures make {made:,}, "
                                 f"not {want:,}")
        unit = {"name": name, "total": total, "men": men, "women": women, "groups": ages,
                "shabiyah": str(row[at["ADM1_NAME"]] or "").strip()}
        if level == 0:
            out["national"] = unit
        elif level == 1:
            if fold(name) in out["shabiyat"]:
                raise SystemExit(f"libya_census: shabiyah {name} printed twice")
            out["shabiyat"][fold(name)] = unit
        elif level == 2:
            out["baladiyat"].append(unit)
        elif level == 3:
            out["below"].setdefault(fold(unit["shabiyah"]), []).append(total)
    check(out)
    return out


def check(table: dict[str, Any]) -> None:
    national = table["national"]
    if national is None or national["total"] != NATIONAL:
        raise SystemExit(f"libya_census: the national row reads "
                         f"{national and national['total']}, not {NATIONAL:,}")
    made = sum(u["total"] for u in table["shabiyat"].values())
    if made != NATIONAL:
        raise SystemExit(f"libya_census: the shabiyat make {made:,}, not {NATIONAL:,}")
    if set(table["shabiyat"]) != set(SHAPES):
        raise SystemExit("libya_census: the shabiyat are not the 22 bound here: "
                         f"{sorted(set(table['shabiyat']) ^ set(SHAPES))}")
    for key, unit in table["shabiyat"].items():
        for what, parts in (("mahallat", table["below"].get(key)),
                            ("baladiyat", [b["total"] for b in table["baladiyat"]
                                           if fold(b["shabiyah"]) == key])):
            if parts and sum(parts) != unit["total"]:
                raise SystemExit(f"libya_census: {unit['name']}'s {what} make "
                                 f"{sum(parts):,}, not {unit['total']:,}")


def compose(table: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Area (its shabiyah key) -> the census's baladiyat whose seats lie in it."""
    areas: dict[str, list[dict[str, Any]]] = {key: [] for key in SHAPES}
    used: set[tuple[str, str]] = set()
    for unit in table["baladiyat"]:
        home = fold(unit["shabiyah"])
        key = (home, fold(unit["name"]))
        if key in MOVED:
            used.add(key)
        areas[MOVED.get(key, home)].append(unit)
    stale = sorted(set(MOVED) - used)
    if stale:
        raise SystemExit(f"libya_census: MOVED names baladiyat the census does not: {stale}")
    if sum(b["total"] for parts in areas.values() for b in parts) != NATIONAL:
        raise SystemExit("libya_census: the areas do not make the national total")
    return areas


def merged(parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {"total": sum(p["total"] for p in parts), "men": sum(p["men"] for p in parts),
            "women": sum(p["women"] for p in parts),
            "groups": [(lo, hi, sum(p["groups"][i][2] for p in parts))
                       for i, (lo, hi, _) in enumerate(parts[0]["groups"])]}


def display(name: str) -> str:
    return " ".join(w.capitalize() if w.isupper() else w for w in str(name).split())


def build(table: dict[str, Any], drawn: dict[str, list[dict[str, Any]]]
          ) -> list[dict[str, Any]]:
    """One record per area and level, bound by shape id."""
    for level, shapes in drawn.items():
        ids = {s["id"] for s in shapes}
        wanted = set(SHAPES.values())
        if ids != wanted:
            raise SystemExit(f"libya_census: the map's {level} polygons are not the 22 "
                             f"bound here: {sorted(ids ^ wanted)}")
    labels = {s["id"]: s["name"] for shapes in drawn.values() for s in shapes}
    areas = compose(table)
    records = []
    for key in sorted(SHAPES):
        sid = SHAPES[key]
        census = table["shabiyat"][key]
        name, held = RELABELLED.get(key, (labels[sid], ""))
        where = (f" {labels[sid]}, a name this area is also given, was a district of the "
                 f"2001 division; the area shown is the shabiyah of {name} as drawn in 2007, "
                 f"which holds {held}." if held else "")
        if key in UNSURE:
            fields = {f: gap(NOT_AVAILABLE, UNSURE[key] + where)
                      for f in ("population", "median_age", "sex_ratio")}
            # The encyclopaedia's figures on these two outlines are for other
            # ground (Jafara's 2020 548,855 counts Janzur and the baladiyat
            # around it, which lie in Az Zawiyah's outline; the undated 267,031
            # is the 2001 district of Tajura' alone): the reason displaces them.
            fields["population"]["displaces_before"] = DISPLACES_BEFORE
            fields["population"]["displaces_undated"] = True
        else:
            parts = areas[key]
            unit = merged(parts)
            gained = [p for p in parts if fold(p["shabiyah"]) != key]
            lost = [b for b in table["baladiyat"] if fold(b["shabiyah"]) == key
                    and all(b is not p for p in parts)]
            if gained or lost:
                diff = []
                if gained:
                    diff.append("with " + ", ".join(
                        f"{display(p['name'])} ({p['total']:,}), which the census counts with "
                        f"{display(table['shabiyat'][fold(p['shabiyah'])]['name'])}"
                        for p in gained))
                if lost:
                    diff.append("without " + ", ".join(
                        f"{display(b['name'])} ({b['total']:,})" for b in lost)
                        + ", which lie outside it")
                what = (f"the census's shabiyah of {display(census['name'])} "
                        f"({census['total']:,}) " + " and ".join(diff) +
                        "; added up from the census's baladiyat whose seats lie in the area "
                        "shown")
            else:
                what = f"the shabiyah of {name}"
            median = grouped_median(unit["groups"])
            fields = {
                "population": measure(unit["total"], year=YEAR, source=SOURCE),
                "population_note": (f"The 2006 census count of {what}, Libyans and "
                                    f"non-Libyans resident on 15 April 2006: {unit['men']:,} "
                                    f"men and {unit['women']:,} women.{where}"),
                "median_age": measure(median, unit="years", year=YEAR, source=SOURCE),
                "median_age_note": ("Interpolated within the five-year age group that holds "
                                    "the middle person, from the 2006 census's count of "
                                    "everyone resident by five-year age group."),
                "sex_ratio": measure(round(1000 * unit["men"] / unit["women"]),
                                     unit="males_per_1000_females", year=YEAR, source=SOURCE),
                "sex_ratio_note": (f"Men per 1,000 women among everyone the 2006 census "
                                   f"counted as resident here, Libyans and non-Libyans: "
                                   f"{unit['men']:,} men and {unit['women']:,} women."),
                "sources": [{"field": "population/median_age/sex_ratio", "name": SOURCE,
                             "url": uscb.dataset_url(DATASET), "year": YEAR,
                             "license": LICENCE}]}
        for level in drawn:
            # The outline's own label is this area's other name: another
            # source's row on the outline by that label is the same place.
            aliases = [labels[sid]] if labels[sid] != name else None
            records.append(record(f"LBY-2006-{key}-{level}", name, level=level, parent="LBY",
                                  country="LBY", match_by="shape_id", shape_id=sid,
                                  aliases=aliases, codes={"uscb": census["name"]}, **fields))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    import openpyxl                                 # noqa: PLC0415
    url = uscb.workbook_url(DATASET)
    blob = http_get(url, binary=True, cache=False, timeout=180)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Metadata") for c in r if c)
    if str(YEAR) not in meta:
        raise SystemExit("libya_census: the workbook's metadata never names 2006")
    table = read(uscb.sheet_rows(book, "Age-Sex"))
    areas = compose(table)
    for key, parts in sorted(areas.items()):
        unit = merged(parts)
        log(f"  {key:18} {unit['total']:>10,}  median {grouped_median(unit['groups'])}  "
            f"men/1000 women {round(1000 * unit['men'] / unit['women'])}"
            + ("  (left without figures)" if key in UNSURE else "") + "  <- "
            + "; ".join(f"{p['name']} {p['total']:,}" for p in parts))
    drawn = {level: json.loads((SITE / level / "LBY.units.json").read_text())
             for level in ("admin1", "admin2")}
    records = build(table, drawn)
    log(f"  {len(table['shabiyat'])} shabiyat making {table['national']['total']:,}; "
        f"{len(records)} records")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
