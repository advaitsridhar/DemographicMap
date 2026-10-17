#!/usr/bin/env python3
"""Libya -- the 2006 census by shabiyah: head count, median age and sex ratio.

The Bureau of Statistics and Census counted Libya on 15 April 2006 and
published, in the census's Table (10), the total resident population --
Libyans and non-Libyans -- by mahallah, five-year age group and sex. The US
Census Bureau's subnational tables for HDX carry that table whole, summed to
the 100 baladiyat and the 22 shabiyat of the time, with the census's own codes
(``libya-subnational-boundaries-and-tabular-data``, sheet ``Age-Sex``). No
later count exists: the 2012 figures beside it in the same workbook are the
Bureau's National Population Survey, a sample, and the population figures
since are estimates.

**What is written**, for every shabiyah, at both levels of the map (which
draws the 22 shabiyat twice, with the same outlines and the same ids): the
2006 count, the median age interpolated within the five-year group holding
the middle person, and men per 1,000 women.

**The labels.** Seventeen of the boundary file's 22 labels are the shabiyat's
own names. Five are the names of districts of the 2001 division, put on the
polygons of the 2007 shabiyat that took them in: the polygon labelled Al
Qubbah holds Derna, labelled Ajdabiya holds Ajdabiya and the oases of Jalu,
Awjila and Marada (Al Wahat), Ghadamis holds Nalut and Ghadames (Nalut),
Mizdah holds Gharyan, Yafran and Mizda (Al Jabal al Gharbi), and Tajura' wa
an Nawahi al Arba holds Tripoli. Each is bound by its shape id to the
shabiyah it draws (``SHAPES``) and carries that shabiyah's name.

**Checks before anything is written.** Every row's age groups and its men and
women make its total; the 22 shabiyat make the national row, 5,657,692; each
shabiyah's mahallat make it; every shabiyah is bound to exactly one polygon
and every polygon to one shabiyah.

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
from ._shared import PROCESSED, http_get, log, measure, record, write_json

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
# file's shape id. Established by the polygons' extent: each holds its
# shabiyah's seat and towns (see the module docstring).
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
# The five polygons whose label is a district of the 2001 division: the name
# of the 2007 shabiyah each draws, and what that shabiyah holds, for the note.
# Every other polygon keeps the boundary file's label, which is its
# shabiyah's own name in another spelling.
RELABELLED: dict[str, tuple[str, str]] = {
    "darnah": ("Darnah", "Derna and Al Qubbah"),
    "alwahat": ("Al Wahat", "Ajdabiya and the oases of Jalu, Awjila and Marada"),
    "tarabulus": ("Tripoli", "Tripoli with Tajura and its outskirts"),
    "aljabalalgharbi": ("Al Jabal al Gharbi", "Gharyan, Yafran and Mizda"),
    "nalut": ("Nalut", "Nalut and Ghadames"),
}
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
    """The national row, the shabiyat and their mahallat from the Age-Sex sheet."""
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
        below = table["below"].get(key)
        if below and sum(below) != unit["total"]:
            raise SystemExit(f"libya_census: {unit['name']}'s mahallat make {sum(below):,}, "
                             f"not {unit['total']:,}")


def build(table: dict[str, Any], drawn: dict[str, list[dict[str, Any]]]
          ) -> list[dict[str, Any]]:
    """One record per shabiyah and level, bound by shape id."""
    for level, shapes in drawn.items():
        ids = {s["id"] for s in shapes}
        wanted = set(SHAPES.values())
        if ids != wanted:
            raise SystemExit(f"libya_census: the map's {level} polygons are not the 22 "
                             f"bound here: {sorted(ids ^ wanted)}")
    labels = {s["id"]: s["name"] for shapes in drawn.values() for s in shapes}
    records = []
    for key, unit in sorted(table["shabiyat"].items()):
        sid = SHAPES[key]
        median = grouped_median(unit["groups"])
        ratio = round(1000 * unit["men"] / unit["women"])
        name, held = RELABELLED.get(key, (labels[sid], ""))
        where = (f" {labels[sid]}, a name this area is also given, was a district of the "
                 f"2001 division; the area shown is the shabiyah of {name} as drawn in 2007, "
                 f"which holds {held}." if held else "")
        pop_note = (f"The 2006 census count of {name}, Libyans and non-Libyans resident on "
                    f"15 April 2006: {unit['men']:,} men and {unit['women']:,} women.{where}")
        for level in drawn:
            records.append(record(
                f"LBY-2006-{key}-{level}", name, level=level, parent="LBY", country="LBY",
                match_by="shape_id", shape_id=sid,
                population=measure(unit["total"], year=YEAR, source=SOURCE),
                population_note=pop_note,
                median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
                median_age_note=("Interpolated within the five-year age group that holds the "
                                 "middle person, from the 2006 census's count of everyone "
                                 "resident by five-year age group."),
                sex_ratio=measure(ratio, unit="males_per_1000_females", year=YEAR,
                                  source=SOURCE),
                sex_ratio_note=(f"Men per 1,000 women among everyone the 2006 census counted "
                                f"as resident, Libyans and non-Libyans: {unit['men']:,} men "
                                f"and {unit['women']:,} women."),
                codes={"uscb": unit["name"]},
                sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE,
                          "url": uscb.dataset_url(DATASET), "year": YEAR,
                          "license": LICENCE}]))
    return records


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl                                 # noqa: PLC0415
    url = uscb.workbook_url(DATASET)
    blob = http_get(url, binary=True, cache=False, timeout=180)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Metadata") for c in r if c)
    if str(YEAR) not in meta:
        raise SystemExit("libya_census: the workbook's metadata never names 2006")
    # What the Population sheet's 2020 figure is, from the workbook's own
    # dictionary, so the log says why it is or is not used.
    for row in uscb.sheet_rows(book, "Data Dictionary"):
        cells = [str(c).strip() for c in row if c is not None]
        if cells and any("2020" in c for c in cells):
            log("  dictionary: " + " | ".join(c[:300] for c in cells))
    table = read(uscb.sheet_rows(book, "Age-Sex"))
    for key, unit in sorted(table["shabiyat"].items()):
        log(f"  {unit['name']:24} {unit['total']:>10,}  median {grouped_median(unit['groups'])}"
            f"  men/1000 women {round(1000 * unit['men'] / unit['women'])}")
        # Its baladiyat, so the ground each shabiyah counts can be compared
        # with the polygon it is bound to.
        log("      " + "; ".join(f"{b['name']} {b['total']:,}"
                                 for b in table["baladiyat"] if fold(b["shabiyah"]) == key))
    drawn = {level: json.loads((SITE / level / "LBY.units.json").read_text())
             for level in ("admin1", "admin2")}
    records = build(table, drawn)
    log(f"  {len(table['shabiyat'])} shabiyat making {table['national']['total']:,}; "
        f"{len(records)} records")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
