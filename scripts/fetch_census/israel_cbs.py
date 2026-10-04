#!/usr/bin/env python3
"""Israel's districts and sub-districts: population by population group, CBS.

The Central Bureau of Statistics' *Statistical Abstract of Israel 2024*
(No. 75), Table 2.17 -- "Localities and population, by population group,
district, sub-district and natural region" -- gives every district and
sub-district's population on 31 December 2023, in thousands to one decimal,
as Jews and others, Arabs, and foreigners (people in Israel who are not
Israeli citizens or permanent residents). The workbook is
``st02_17.xlsx`` of the abstract's population chapter.

**What is written** on each unit the map draws as the CBS counts it: the
population, and its people by population group on the ethnicity field
(``ethnicity_basis`` "population group", the CBS's own classification).

**Where the map and the CBS draw different ground** (the Asia brief's rule:
bind only to the polygon the source counts):

* *Golan.* The CBS's Northern District includes the Golan sub-district; the
  map draws the Golan Heights inside Syria's Quneitra governorate and only a
  sliver under Israel's "Golan". So the Golan sub-district's figure is
  bound nowhere, and the Northern District is written as the sum of its
  four other sub-districts (Zefat, Kinneret, Yizre'el, Akko), which the
  drawn district is.
* *Jerusalem.* The CBS's Jerusalem District -- a single sub-district, which
  the table divides only into the Judean Mountains and Judean Foothills
  natural regions -- counts all of Jerusalem's municipal area, East
  Jerusalem included, which the map draws within the West Bank. Its figure
  is not the drawn polygon's, and the CBS publishes none for the district
  without East Jerusalem, so the district and the drawn "Jerusalem"
  sub-district both say so.

**Checks** (any failure stops the run): each row's groups make its total
(to the table's rounding, 0.1 thousand per term); the sub-districts make
their district. What the six districts leave of the country's total row --
the Israelis of the Judea and Samaria Area -- is logged.

Usage:
    python -m scripts.fetch_census.israel_cbs
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import check, units, workbook

ISO3 = "ISR"
OUT = "israel_cbs.json"
URL = "https://www.cbs.gov.il/he/publications/doclib/2024/2.shnatonpopulation/st02_17.xlsx"
YEAR = 2023
SOURCE = ("Central Bureau of Statistics (Israel), Statistical Abstract of Israel 2024 "
          "(No. 75), Table 2.17: population by population group, district and "
          "sub-district, 31 December 2023")
LICENCE = "Central Bureau of Statistics (Israel), published statistical abstract"
# Table rounding: each figure is in thousands to one decimal.
ROUND = 0.1
DISTRICTS = {
    "JERUSALEM DISTRICT": "Jerusalem District",
    "NORTHERN DISTRICT": "Northern District",
    "HAIFA DISTRICT": "Haifa",
    "CENTRAL DISTRICT": "Central District",
    "TEL AVIV DISTRICT": "Tel Aviv",
    "SOUTHERN DISTRICT": "Southern District",
}
# The CBS's sub-district -> the boundary file's label.
SUBDISTRICTS = {
    "Zefat": "Zefat", "Kinneret": "Kinneret", "Yizre'el": "Yizre'el", "Akko": "Akko",
    "Golan": "Golan", "Haifa": "Haifa", "Hadera": "Hadera", "Sharon": "HaSharon",
    "Petah Tiqwa": "Petah Tiqwa", "Ramla": "Ramla", "Rehovot": "Rehovot",
    "Tel Aviv": "Tel Aviv", "Ashqelon": "Ashqelon", "Be'er Sheva": "Be'er Sheva",
}
# The Jerusalem District is one sub-district, which the boundary file draws
# as "Jerusalem"; the table lists only its natural regions beneath it.
JERUSALEM_LABEL = "Jerusalem"
GOLAN_WHY = ("The CBS counts the Golan Heights as the Golan sub-district of the Northern "
             "District; the map draws the Golan Heights within Syria's Quneitra "
             "governorate, and this shape is a sliver of it, so no CBS figure is this "
             "shape's.")
JERUSALEM_WHY = ("The CBS's Jerusalem figures count all of Jerusalem's municipal area, East "
                 "Jerusalem included, which the map draws within the West Bank; the CBS "
                 "publishes no figure for the part of the district this shape is.")
GROUPS = ("Foreign nationals", "Arabs", "Jews and others")


def figure(cell: Any) -> float | None:
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return float(cell)
    text = str(cell or "").strip()
    return 0.0 if text in ("-", "0") else None


def name_of(label: str) -> tuple[str, str | None]:
    """('district', KEY) or ('subdistrict', name) or ('', None)."""
    text = re.sub(r"\(\d+\)", "", label).strip()
    if text.upper() == text and text.upper() in DISTRICTS:
        return "district", text.upper()
    m = re.match(r"^(.*?)\s*S\.D\.?$", text)
    if m:
        return "subdistrict", m.group(1).strip()
    if text.upper().startswith("TOTAL POPULATION"):
        return "total", "TOTAL"
    return "", None


def read(sheets: dict[str, list[list[Any]]]) -> dict[tuple[str, str], dict[str, float]]:
    """(kind, name) -> {group: people, total}, from every sheet of Table 2.17."""
    out: dict[tuple[str, str], dict[str, float]] = {}
    district = None
    for rows in sheets.values():
        for row in rows:
            if not row or not isinstance(row[0], str):
                continue
            kind, name = name_of(row[0])
            if not kind:
                continue
            cells = [figure(c) for c in row[1:6]]
            if any(c is None for c in cells):
                continue
            foreign, arabs, jews, israelis, total = cells
            where = f"{kind} {name}"
            check(abs(arabs + jews - israelis) <= 2 * ROUND + 1e-9,
                  f"israel_cbs: {where}: Arabs and Jews-and-others do not make the Israelis")
            check(abs(israelis + foreign - total) <= 2 * ROUND + 1e-9,
                  f"israel_cbs: {where}: Israelis and foreigners do not make the total")
            if kind == "district":
                district = name
            entry = {"Foreign nationals": foreign * 1000, "Arabs": arabs * 1000,
                     "Jews and others": jews * 1000, "total": total * 1000,
                     "district": district if kind == "subdistrict" else name}
            check((kind, name) not in out, f"israel_cbs: {where} twice")
            out[(kind, name)] = entry
    return out


def build(table: dict[tuple[str, str], dict[str, float]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], parents: dict[str, str]) -> list[dict[str, Any]]:
    districts = {n: v for (k, n), v in table.items() if k == "district"}
    subs = {n: v for (k, n), v in table.items() if k == "subdistrict"}
    # The Tel Aviv District is a single sub-district, which the table may list
    # only as the district.
    if "Tel Aviv" not in subs and "TEL AVIV DISTRICT" in districts:
        subs["Tel Aviv"] = dict(districts["TEL AVIV DISTRICT"], district="TEL AVIV DISTRICT")
    check(set(DISTRICTS) <= set(districts), f"israel_cbs: districts {sorted(districts)}")
    check(set(SUBDISTRICTS) <= set(subs), f"israel_cbs: sub-districts {sorted(subs)}")
    for d in DISTRICTS:
        kids = [v for v in subs.values() if v["district"] == d]
        if kids:
            made = sum(v["total"] for v in kids)
            check(abs(made - districts[d]["total"]) <= 1000 * ROUND * (len(kids) + 1),
                  f"israel_cbs: {d}'s sub-districts make {made:,.0f}, not "
                  f"{districts[d]['total']:,.0f}")
    total = table.get(("total", "TOTAL"))
    check(total is not None, "israel_cbs: no total row")
    made = sum(districts[d]["total"] for d in DISTRICTS)
    log(f"  districts make {made:,.0f}; the country {total['total']:,.0f}; "
        f"outside the six districts {total['total'] - made:,.0f}")
    source = [{"field": "population/ethnicity", "name": SOURCE, "url": URL, "year": YEAR,
               "license": LICENCE}]

    def fields(v: dict[str, float], what: str) -> dict[str, Any]:
        population = measure(round(v["total"]), year=YEAR, source=SOURCE)
        population["note"] = (f"The CBS's estimate for 31 December 2023 for {what}, published "
                              f"in thousands to one decimal (the nearest hundred people).")
        return {
            "population": population,
            "ethnicity": shares({g: v[g] for g in GROUPS if v[g]}, total=v["total"]),
            "ethnicity_year": YEAR, "ethnicity_basis": "population group",
            "ethnicity_note": (
                "The CBS's population groups: Jews and others (others being non-Arab "
                "Christians, members of other religions and people the population "
                "register classifies by no religion), Arabs, and foreigners -- residents "
                "who are neither citizens nor permanent residents. Published in thousands "
                "to one decimal."),
            "sources": source,
        }

    out: list[dict[str, Any]] = []
    drawn1 = {u["name"]: u for u in admin1}
    for key_, label in DISTRICTS.items():
        unit = drawn1.get(label)
        check(unit is not None, f"israel_cbs: {label} is not drawn")
        if key_ == "JERUSALEM DISTRICT":
            out.append(record(f"ISR-CBS-{label}", label, level="admin1", parent=ISO3,
                              country=ISO3, match_by="shape_id", shape_id=unit["id"],
                              population=gap(NOT_AVAILABLE, JERUSALEM_WHY),
                              ethnicity=gap(NOT_AVAILABLE, JERUSALEM_WHY)))
            continue
        if key_ == "NORTHERN DISTRICT":
            kids = [n for n in ("Zefat", "Kinneret", "Yizre'el", "Akko")]
            v = {g: sum(subs[n][g] for n in kids) for g in GROUPS + ("total",)}
            golan = subs["Golan"]["total"]
            check(abs(v["total"] + golan - districts[key_]["total"]) <= 1000 * ROUND * 6,
                  "israel_cbs: the Northern District is not its sub-districts")
            rec = record(f"ISR-CBS-{label}", label, level="admin1", parent=ISO3, country=ISO3,
                         match_by="shape_id", shape_id=unit["id"],
                         **fields(v, "the Zefat, Kinneret, Yizre'el and Akko sub-districts"))
            rec["population"]["note"] += (
                f" The sum of the district's sub-districts other than the Golan "
                f"({golan:,.0f} people), which the map draws in Syria's Quneitra governorate.")
            out.append(rec)
            continue
        out.append(record(f"ISR-CBS-{label}", label, level="admin1", parent=ISO3,
                          country=ISO3, match_by="shape_id", shape_id=unit["id"],
                          **fields(districts[key_], f"the {key_.title()}")))
    by_label: dict[str, list[dict[str, Any]]] = {}
    for unit in admin2:
        by_label.setdefault(unit["name"], []).append(unit)
    for name, label in list(SUBDISTRICTS.items()) + [(None, JERUSALEM_LABEL)]:
        found = by_label.get(label, [])
        check(len(found) == 1, f"israel_cbs: {len(found)} drawn units labelled {label!r}")
        unit = found[0]
        why = GOLAN_WHY if name == "Golan" else JERUSALEM_WHY if name is None else None
        if why:
            out.append(record(f"ISR-CBS-{label}", label, level="admin2", parent=ISO3,
                              country=ISO3, parent_name=parents.get(unit["parent"]),
                              match_by="shape_id", shape_id=unit["id"],
                              population=gap(NOT_AVAILABLE, why),
                              ethnicity=gap(NOT_AVAILABLE, why)))
            continue
        out.append(record(f"ISR-CBS-{label}", label, level="admin2", parent=ISO3, country=ISO3,
                          parent_name=parents.get(unit["parent"]), match_by="shape_id",
                          shape_id=unit["id"], aliases=[f"{name} sub-district"],
                          **fields(subs[name], f"the {name} sub-district")))
    left = sorted(set(by_label) - set(SUBDISTRICTS.values()) - {JERUSALEM_LABEL})
    check(not left, f"israel_cbs: drawn sub-districts with no CBS row: {left}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    table = read(workbook(URL))
    admin1, admin2 = units(ISO3, "admin1"), units(ISO3, "admin2")
    rows = build(table, admin1, admin2, {u["id"]: u["name"] for u in admin1})
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
