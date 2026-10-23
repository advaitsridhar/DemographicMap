#!/usr/bin/env python3
"""Sierra Leone -- the 2021 Mid-Term Population and Housing Census, on the 2015 census's ground.

Statistics Sierra Leone took a mid-term census in December 2021. Its own site
serves no report a script can reach; citypopulation.de tabulates its counts
for the sixteen districts of 2017 and their chiefdoms, with the 2004 and 2015
censuses beside them on the same 2017 boundaries. The map draws the fourteen
districts and four regions of 2015 (sierra_leone_census), so each 2015
district is put together from the 2017 units that make it:

* ten districts the 2017 changes left whole (Kailahun, Kenema, Kono, Kambia,
  Bo, Bonthe, Moyamba, Pujehun, Western Area Rural and Urban);
* Koinadugu: Koinadugu and Falaba, made out of it in 2017;
* Tonkolili: Tonkolili and Mara chiefdom, which citypopulation.de lists
  under Bombali since 2017;
* Bombali: Bombali less Mara, with the eight chiefdoms of Karene District
  that were Bombali's;
* Port Loko: Port Loko with Karene's other five chiefdoms.

The moves are declared in ``FROM_2017`` and checked, not guessed: the 2015
column of the units each 2015 district is made of must add up to that
district's 2015 census count exactly (sierra_leone_census's figures), and
Karene's chiefdoms split between Bombali and Port Loko in one way only that
does so. A region is its 2015 districts added up.

**What the figures are worth.** The mid-term census's results were disputed
-- its Western Area Urban count, 609,174, is 42% below the 2015 census's
1,055,964 -- and citypopulation.de notes that the reasons for the large
differences between the 2015 and 2021 figures are unclear. So these counts
are not written in front of anything: they are held behind the 2015 census
(build_entities' HELD_ROWS) and offered as newer figures, which the build
shows only where the change from the figure shown is one a population makes,
and otherwise names on the unit as a newer figure not shown. Only the
population is offered; the 2015 census's sex ratios and ages stand.

Usage:
    python -m scripts.fetch_census.sierra_leone_mtphc
"""

from __future__ import annotations

import argparse
import html
import json
import re
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

ADMIN = "https://www.citypopulation.de/en/sierraleone/admin/"
SOURCE = ("Statistics Sierra Leone, 2021 Mid-Term Population and Housing Census, as tabulated "
          "by citypopulation.de")
LICENCE = "citation of citypopulation.de required"
YEAR = 2021
NATIONAL_2021 = 7_548_702
NATIONAL_2015 = 7_092_113
OUT = "sierra_leone_mtphc.json"
CENSUS_2015 = PROCESSED / "sierra_leone_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
STATUSES = ("District", "Chiefdom", "City", "Town", "Ward", "Municipality", "Republic")

# Each 2015 district: the 2017 districts it is made of, and the chiefdoms
# added to it from another 2017 district (+) or taken from it (-).
FROM_2017: dict[str, dict[str, Any]] = {
    "Kailahun": {"districts": ["Kailahun"]},
    "Kenema": {"districts": ["Kenema"]},
    "Kono": {"districts": ["Kono"]},
    "Kambia": {"districts": ["Kambia"]},
    "Bo": {"districts": ["Bo"]},
    "Bonthe": {"districts": ["Bonthe"]},
    "Moyamba": {"districts": ["Moyamba"]},
    "Pujehun": {"districts": ["Pujehun"]},
    "Western Area Rural": {"districts": ["Western Area Rural"]},
    "Western Area Urban": {"districts": ["Western Area Urban"]},
    "Koinadugu": {"districts": ["Koinadugu", "Falaba"]},
    "Tonkolili": {"districts": ["Tonkolili"], "plus": [("Bombali", "Mara")]},
    "Bombali": {"districts": ["Bombali"], "minus": [("Bombali", "Mara")],
                "plus": [("Karene", c) for c in (
                    "Gbanti", "Libeisaygahun/Gbombahun", "Mafonda Makerembay", "Sanda Loko",
                    "Sanda Tendaran", "Sella Limba", "Tambakha Simibungie",
                    "Tambakha Yobangie")]},
    "Port Loko": {"districts": ["Port Loko"],
                  "plus": [("Karene", c) for c in (
                      "Buya", "Dibia", "Romende", "Safroko", "Sanda Magbolontor")]},
}
REGIONS = {"Eastern": ("Kailahun", "Kenema", "Kono"),
           "Northern": ("Bombali", "Kambia", "Koinadugu", "Port Loko", "Tonkolili"),
           "Southern": ("Bo", "Bonthe", "Moyamba", "Pujehun"),
           "Western Area": ("Western Area Rural", "Western Area Urban")}
DISPUTED = ("The mid-term census's results were disputed: it counted 609,174 people in Western "
            "Area Urban, 42% fewer than Statistics Sierra Leone's 2015 census.")


def number(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def table(page: str) -> dict[str, dict[str, Any]]:
    """{2017 district: {"v": (2004, 2015, 2021), "parts": {chiefdom: (...)}}},
    and Sierra Leone under its own name, from the page's rows in order."""
    out: dict[str, dict[str, Any]] = {}
    current = None
    for row in re.findall(r"(?is)<tr\b.*?</tr>", page):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row)]
        if len(cells) < 5 or cells[1] not in STATUSES:
            continue
        name, status = cells[0], cells[1]
        values = tuple(number(c) for c in cells[2:5])
        if status in ("District", "Republic"):
            current = name
            out[name] = {"v": values, "parts": {}}
        elif current is not None:
            out[current]["parts"][name] = values
    return out


def compose(units: dict[str, dict[str, Any]], spec: dict[str, Any], col: int) -> int:
    """A 2015 district's figure in one column (0 2004, 1 2015, 2 2021)."""
    total = 0
    for d in spec["districts"]:
        total += units[d]["v"][col]
    for sign, key in ((1, "plus"), (-1, "minus")):
        for d, chiefdom in spec.get(key, []):
            value = units[d]["parts"].get(chiefdom, (None, None, None))[col]
            if value is None:
                raise SystemExit(f"sierra_leone_mtphc: {d}'s {chiefdom} has no figure in column "
                                 f"{col}")
            total += sign * value
    return total


def check(units: dict[str, dict[str, Any]], counts_2015: dict[str, int]) -> None:
    """Every 2015 district, put together from the 2017 units, makes its 2015
    census count; the districts make the country in 2015 and 2021; and each
    2017 district's chiefdoms make it."""
    country = units.get("Sierra Leone", {}).get("v")
    if not country or country[1] != NATIONAL_2015 or country[2] != NATIONAL_2021:
        raise SystemExit(f"sierra_leone_mtphc: Sierra Leone reads {country}")
    for name, unit in units.items():
        if name == "Sierra Leone":
            continue
        for col in (1, 2):
            made = sum(p[col] or 0 for p in unit["parts"].values())
            if unit["parts"] and made != unit["v"][col]:
                raise SystemExit(f"sierra_leone_mtphc: {name}'s parts make {made:,} in column "
                                 f"{col}, not {unit['v'][col]:,}")
    for col, national in ((1, NATIONAL_2015), (2, NATIONAL_2021)):
        made = sum(compose(units, spec, col) for spec in FROM_2017.values())
        if made != national:
            raise SystemExit(f"sierra_leone_mtphc: the 2015 districts make {made:,} in column "
                             f"{col}, not {national:,}")
    for name, spec in FROM_2017.items():
        got = compose(units, spec, 1)
        if got != counts_2015.get(name):
            raise SystemExit(f"sierra_leone_mtphc: {name} put together from 2017's units counts "
                             f"{got:,} in 2015, not the census's {counts_2015.get(name)}")


def note(name: str, spec: dict[str, Any]) -> str:
    lead = "The 2021 Mid-Term Population and Housing Census's"
    label = name if name.startswith("Western") else f"{name} District"
    if spec.get("plus") or len(spec["districts"]) > 1:
        if name == "Koinadugu":
            how = ("counts for Koinadugu and Falaba districts added together (Falaba was made "
                   "out of Koinadugu in 2017)")
        elif name == "Tonkolili":
            how = ("counts for Tonkolili District and for Mara chiefdom (counted in Bombali "
                   "District since 2017) added together")
        elif name == "Bombali":
            how = ("counts for Bombali District less Mara chiefdom (counted there since 2017) and "
                   "for the eight chiefdoms of Karene District made out of Bombali in 2017, "
                   "added together")
        else:
            how = ("counts for Port Loko District and for the five chiefdoms of Karene District "
                   "made out of Port Loko in 2017 added together")
        return f"{lead} {how}: the district as the 2015 census counted it. {DISPUTED}"
    return f"{lead} count for {label}. {DISPUTED}"


def build(units: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cite = [{"field": "population", "name": SOURCE, "url": ADMIN, "year": YEAR,
             "license": LICENCE}]
    drawn2 = {s["name"]: s for s in admin2}
    drawn1 = {s["name"]: s for s in admin1}
    if sorted(drawn2) != sorted(FROM_2017) or sorted(drawn1) != sorted(REGIONS):
        raise SystemExit(f"sierra_leone_mtphc: drawn {sorted(drawn1)} / {sorted(drawn2)}")
    records = []
    figures = {name: compose(units, spec, 2) for name, spec in FROM_2017.items()}
    for region, districts in REGIONS.items():
        shape = drawn1[region]
        label = "the Western Area" if region == "Western Area" else f"the {region} Region"
        later = (" (the North West Province was made out of the Northern Region in 2017)"
                 if region == "Northern" else "")
        records.append(record(
            f"SLE-MTPHC2021-{shape['id']}", shape["name"], level="admin1", parent="SLE",
            country="SLE", match_by="shape_id", shape_id=shape["id"], sources=cite,
            population=measure(sum(figures[d] for d in districts), year=YEAR, source=SOURCE),
            population_note=(f"The 2021 Mid-Term Population and Housing Census's counts for the "
                             f"districts that made up {label} in 2015 added together{later}. "
                             f"{DISPUTED}")))
    for name, spec in FROM_2017.items():
        shape = drawn2[name]
        records.append(record(
            f"SLE-MTPHC2021-{shape['id']}", shape["name"], level="admin2", parent="SLE",
            country="SLE", match_by="shape_id", shape_id=shape["id"], sources=cite,
            population=measure(figures[name], year=YEAR, source=SOURCE),
            population_note=note(name, spec)))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    ap.parse_args()
    page = http_get(ADMIN, binary=True, cache=False, timeout=120)
    assert isinstance(page, bytes)
    units = table(page.decode("utf-8", "replace"))
    log(f"sierra_leone_mtphc: {len(units)} rows of districts read: "
        + ", ".join(f"{n} {u['v']}" for n, u in units.items()))
    counts_2015 = {r["name"]: r["population"]["value"]
                   for r in json.loads(CENSUS_2015.read_text()) if r["level"] == "admin2"}
    check(units, counts_2015)
    admin1 = json.loads((SITE / "admin1" / "SLE.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SLE.units.json").read_text())
    records = build(units, admin1, admin2)
    for r in records:
        log(f"  {r['level']} {r['name']}: {r['population']['value']:,}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
