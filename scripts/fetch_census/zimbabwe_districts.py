#!/usr/bin/env python3
"""Zimbabwe -- the 2022 census's count of every district, and of every province.

ZIMSTAT's "2022 Population and Housing Census: Population Distribution by
District, Ward, Sex and Number of Households" (106 pages) prints the ten
provinces on one page and then, under each province, one page per district,
town council and local board: every ward's men, women, total and households,
and the district's own total line. zimbabwe.py reads the main report's
religion and mother tongue by province; this reads the counts.

Written: population and sex ratio (men per thousand women) for the ten
provinces and for the districts the map draws, from the same census. The
districts say why religion, language and ethnicity are empty -- the census
report publishes religion and mother tongue by province only (Tables 2.14 and
2.17) and ethnicity for the country only (Table 2.15) -- and why there is no
median age: no table of the 2022 census gives ages below the province.

**The units.** The census's 90 units are the map's second level one for one,
under other spellings (``ALIASES``), and the map's Harare Rural is the 91st:
the final tables print Harare Province as Harare Urban District, Chitungwiza
and Epworth, and Harare Urban District's page opens with a Ward 01 of 357,863
people and 92,661 households. That ward is Harare Rural District: ZIMSTAT's
2022 Preliminary Report on Population Figures lists Harare Province as four
districts, Harare Rural among them with one ward of 357,860 people and 92,662
households (page 160), and Harare Urban's wards there begin at Ward 02
(30,229 people, as in the final tables). So Harare Rural is given Ward 01
and Harare Urban the rest of its page (``HARARE_RURAL_WARD``).

**Checks before anything is written.** Every line's men and women make its
total; each district's wards make its total line, in men, women, people and
households; each province's districts make the province's line on the first
page; the provinces make the country's 15,178,957.

Usage:
    python -m scripts.fetch_census.zimbabwe_districts
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .southern_africa_common import fetch, key, sex_ratio, units

URL = ("https://www.zimstat.co.zw/wp-content/uploads//Census/"
       "2022_Population_Distribution_by_District_Ward_SexandHouseholds_23012023.pdf")
REPORT = "https://www.zimstat.co.zw/wp-content/uploads/Census/2022_PHC_Report_27012023_Final.pdf"
SOURCE = ("ZIMSTAT, 2022 Population and Housing Census: Population Distribution by District, "
          "Ward, Sex and Number of Households")
LICENCE = "Official statistics publication of the Zimbabwe National Statistics Agency"
YEAR = 2022
NATIONAL = 15_178_957
OUT = "zimbabwe_districts.json"

NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)"          # "1190" is printed without its comma once
ROW = re.compile(rf"^(?P<label>.*?)\s+(?P<m>{NUM})\s+(?P<f>{NUM})\s+(?P<t>{NUM})\s+(?P<h>{NUM})$")
# The text layer sometimes puts a line's four figures and its label on lines
# of their own ("5,243 6,057 11,300 2,302" and then "Ward 23"): joined again.
FIGURES = re.compile(rf"^{NUM}\s+{NUM}\s+{NUM}\s+{NUM}$")
LABEL = re.compile(r"^(?:Ward \d+|Total)$")


def joined_lines(lines: list[str]) -> list[str]:
    """The page's lines with each split figure line put back on its label."""
    out: list[str] = []
    figures: str | None = None
    label: str | None = None
    for ln in lines:
        if FIGURES.match(ln):
            if label is not None:
                out.append(f"{label} {ln}")
                label = None
            else:
                if figures is not None:
                    out.append(figures)
                figures = ln
        elif LABEL.match(ln):
            if figures is not None:
                out.append(f"{ln} {figures}")
                figures = None
            else:
                label = ln
        else:
            for held in (figures, label):
                if held is not None:
                    out.append(held)
            figures = label = None
            out.append(ln)
    for held in (figures, label):
        if held is not None:
            out.append(held)
    return out
PROVINCES = ("Bulawayo", "Manicaland", "Mashonaland Central", "Mashonaland East",
             "Mashonaland West", "Matabeleland North", "Matabeleland South", "Midlands",
             "Masvingo", "Harare")

# The census's name, reduced (``base``), -> the boundary file's, reduced.
ALIASES = {
    "bulawayourban": "bulawayo",
    "harareurban": "harare",
    "chitungwizaurban": "chitungwiza",
    "muzarabani": "centenarymuzarabani",
    "chinhoyiurban": "chinhoyi",
    "kadoma": "kadomaurban",
    "chirumanzu": "chirumhanzu",
    "gokwetowncentre": "gokwesouthurban",
    "shurugwiurban": "shurugwitown",
}

RELIGION_NOTE = ("ZIMSTAT publishes the 2022 census's religion by province only (2022 "
                 "Population and Housing Census Report, Table 2.14), not by district.")
LANGUAGE_NOTE = ("ZIMSTAT publishes the 2022 census's mother tongue by province only (2022 "
                 "Population and Housing Census Report, Table 2.17), not by district.")
ETHNICITY_NOTE = ("ZIMSTAT publishes the 2022 census's ethnic groups for the country only "
                  "(2022 Population and Housing Census Report, Table 2.15), not by province "
                  "or district.")
AGE_NOTE = ("The 2022 census's published tables give ages for the country and by rural and "
            "urban area, not by district, so no median age from it is shown here.")


def number(text: str) -> int:
    return int(text.replace(",", ""))


def base(name: str) -> str:
    """A unit's name reduced: 'Rural', 'District(s)', 'Town Council' and 'Local
    Board' dropped, 'Urban' kept."""
    text = re.sub(r"(?i)\b(?:rural|districts?|town council|local board)\b", " ", name)
    return key(text)


def census_key(d: dict[str, Any]) -> str:
    """The key a census unit is matched to the map's under."""
    return d.get("key") or ALIASES.get(base(d["name"]), base(d["name"]))


def parse(pages: list[str]) -> dict[str, Any]:
    """{"provinces": {name: row}, "districts": [row]} where a row is
    {"name", "province", "men", "women", "total", "households"}."""
    provinces: dict[str, dict[str, Any]] = {}
    districts: list[dict[str, Any]] = []
    province: str | None = None
    current: dict[str, Any] | None = None
    for text in pages:
        lines = joined_lines([ln.strip() for ln in text.splitlines() if ln.strip()])
        if not lines:
            continue
        if any(ln.startswith("Population Distribution by Province") for ln in lines[:2]):
            for ln in lines:
                hit = ROW.match(ln)
                if hit and hit.group("label") in PROVINCES + ("Total",):
                    provinces[hit.group("label")] = row_of(hit, hit.group("label"), None)
            continue
        title = lines[0]
        if title.endswith(" Province") and title[:-len(" Province")] in PROVINCES:
            province = title[:-len(" Province")]
            current = None
            continue
        if "Population Distribution by Ward" in " ".join(lines[:3]):
            if province is None:
                raise SystemExit(f"zimbabwe_districts: {title!r} comes before any province")
            current = {"name": title, "province": province, "wards": []}
            districts.append(current)
        elif current is None or not any(ln.startswith("Ward ") for ln in lines):
            continue
        for ln in lines:
            hit = ROW.match(ln)
            if not hit:
                # A line with figures that is no ward and no total is shown,
                # so a sum that fails can be traced to the page.
                if re.search(r"\d,\d{3}", ln) or ln.startswith("Ward "):
                    log(f"    {current['name']}: line not read: {ln!r}")
                continue
            label = hit.group("label")
            if label.startswith("Ward "):
                current["wards"].append(row_of(hit, label, province))
            elif label == "Total":
                current.update({k: v for k, v in row_of(hit, current["name"], province).items()
                                if k in ("men", "women", "total", "households")})
            else:
                log(f"    {current['name']}: line not read: {ln!r}")
    check(provinces, districts)
    return {"provinces": provinces, "districts": districts}


def row_of(hit: re.Match, name: str, province: str | None) -> dict[str, Any]:
    men, women, total, households = (number(hit.group(k)) for k in "mfth")
    if men + women != total:
        raise SystemExit(f"zimbabwe_districts: {name}: {men:,} men and {women:,} women do not "
                         f"make {total:,}")
    return {"name": name, "province": province, "men": men, "women": women, "total": total,
            "households": households}


def check(provinces: dict[str, dict[str, Any]], districts: list[dict[str, Any]]) -> None:
    if sorted(provinces) != sorted(PROVINCES + ("Total",)):
        raise SystemExit(f"zimbabwe_districts: the province page gives {sorted(provinces)}")
    if provinces["Total"]["total"] != NATIONAL:
        raise SystemExit(f"zimbabwe_districts: the country is {provinces['Total']['total']:,}, "
                         f"not {NATIONAL:,}")
    for field in ("men", "women", "total", "households"):
        made = sum(provinces[p][field] for p in PROVINCES)
        if made != provinces["Total"][field]:
            raise SystemExit(f"zimbabwe_districts: the provinces make {made:,} {field}")
    for d in districts:
        if "total" not in d or not d["wards"]:
            raise SystemExit(f"zimbabwe_districts: {d['name']} has no total line or no wards")
        for field in ("men", "women", "total", "households"):
            made = sum(w[field] for w in d["wards"])
            if made != d[field]:
                raise SystemExit(f"zimbabwe_districts: {d['name']}'s {len(d['wards'])} wards "
                                 f"make {made:,} {field}, not {d[field]:,}")
    for p in PROVINCES:
        mine = [d for d in districts if d["province"] == p]
        for field in ("men", "women", "total", "households"):
            made = sum(d[field] for d in mine)
            if made != provinces[p][field]:
                raise SystemExit(f"zimbabwe_districts: {p}'s {len(mine)} districts make "
                                 f"{made:,} {field}, not {provinces[p][field]:,}")


def bind(districts: list[dict[str, Any]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """({polygon id: district}, the polygons no district is for): by name
    within the province."""
    province_of = {s["id"]: s["name"] for s in admin1}
    bound: dict[str, dict[str, Any]] = {}
    left: list[dict[str, Any]] = []
    for shape in admin2:
        here = [d for d in districts if d["province"] == province_of.get(shape["parent"])]
        want = key(shape["name"])
        hits = [d for d in here if census_key(d) == want]
        if len(hits) == 1:
            bound[shape["id"]] = hits[0]
        else:
            left.append(shape)
    used = [id(d) for d in bound.values()]
    if len(set(used)) != len(used):
        raise SystemExit("zimbabwe_districts: one district bound to two polygons")
    spare = [d["name"] for d in districts if id(d) not in set(used)]
    if spare:
        raise SystemExit(f"zimbabwe_districts: districts on no polygon: {spare}")
    return bound, left


def fields(row: dict[str, Any], note: str) -> dict[str, Any]:
    return {"population": measure(row["total"], year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": sex_ratio(row["men"], row["women"], year=YEAR, source=SOURCE)}


PRELIMINARY = ("https://zimbabwe.unfpa.org/sites/default/files/pub-pdf/"
               "2022_population_and_housing_census_preliminary_report_on_population_figures.pdf")
SOURCES = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "license": LICENCE,
            "year": YEAR},
           {"field": "religion/language/ethnicity note",
            "name": "ZIMSTAT, 2022 Population and Housing Census Report", "url": REPORT,
            "license": LICENCE, "year": YEAR}]
HARARE_SOURCES = SOURCES + [{
    "field": "population note",
    "name": "ZIMSTAT, 2022 Population and Housing Census Preliminary Report on Population "
            "Figures, p. 160 (Harare Rural District, ward 1)",
    "url": PRELIMINARY, "license": LICENCE, "year": YEAR}]

# Harare Rural District is one ward, which the final tables print as Ward 01
# of Harare Urban District's page; the preliminary report gives it as Harare
# Rural District's ward 1, 357,860 people in 92,662 households.
HARARE_RURAL_WARD = "Ward 01"
HARARE_RURAL_PRELIMINARY = 357_860


def split_harare(districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Harare Urban District's page as two units: Harare Rural District, its
    Ward 01, and Harare Urban District, the rest."""
    out: list[dict[str, Any]] = []
    for d in districts:
        if d["province"] != "Harare" or base(d["name"]) != "harareurban":
            out.append(d)
            continue
        ward = [w for w in d["wards"] if w["name"] == HARARE_RURAL_WARD]
        if len(ward) != 1 or abs(ward[0]["total"] - HARARE_RURAL_PRELIMINARY) > 100:
            raise SystemExit(f"zimbabwe_districts: {d['name']}'s {HARARE_RURAL_WARD} is not "
                             f"the preliminary report's Harare Rural District "
                             f"({HARARE_RURAL_PRELIMINARY:,})")
        rural = {**ward[0], "name": "Harare Rural District", "key": "hararerural",
                 "wards": ward}
        rest = [w for w in d["wards"] if w["name"] != HARARE_RURAL_WARD]
        urban = {"name": d["name"], "province": d["province"], "wards": rest,
                 **{f: d[f] - ward[0][f] for f in ("men", "women", "total", "households")}}
        out.extend([urban, rural])
    return out


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bound, left = bind(split_harare(table["districts"]), admin1, admin2)
    if left:
        raise SystemExit(f"zimbabwe_districts: no census district for "
                         f"{[s['name'] for s in left]}")
    out: list[dict[str, Any]] = []
    gaps = {"religion": gap(NOT_AVAILABLE, RELIGION_NOTE),
            "language": gap(NOT_AVAILABLE, LANGUAGE_NOTE),
            "ethnicity": gap(NOT_AVAILABLE, ETHNICITY_NOTE)}
    for shape in admin2:
        d = bound[shape["id"]]
        note = f"The 2022 census's count for {d['name']}"
        if base(d["name"]) != key(shape["name"]):
            note += f", drawn here as {shape['name']}"
        note += "."
        sources = SOURCES
        if census_key(d) == "harare":
            note = (f"The 2022 census's count for {d['name']}, less its Ward 01: ZIMSTAT's "
                    f"preliminary report lists that ward as Harare Rural District, which is "
                    f"shown on its own polygon.")
            sources = HARARE_SOURCES
        elif census_key(d) == "hararerural":
            note = (f"The 2022 census's count for Harare Rural District, a single ward: "
                    f"ZIMSTAT's final tables print it as Ward 01 of Harare Urban District, "
                    f"and its preliminary report lists it as Harare Rural District "
                    f"({HARARE_RURAL_PRELIMINARY:,} people at that stage).")
            sources = HARARE_SOURCES
        out.append(record(f"ZWE-2022-{key(d['province'])}-{census_key(d)}", shape["name"],
                          level="admin2", parent="ZWE", country="ZWE", match_by="shape_id",
                          shape_id=shape["id"], sources=sources,
                          median_age=gap(NOT_AVAILABLE, AGE_NOTE), **gaps,
                          **fields(d, note)))
    by_name = {key(s["name"]): s for s in admin1}
    for p in PROVINCES:
        shape = by_name.get(key(p))
        if shape is None:
            raise SystemExit(f"zimbabwe_districts: the map draws no province {p!r}")
        out.append(record(f"ZWE-2022-province-{key(p)}", shape["name"], level="admin1",
                          parent="ZWE", country="ZWE", match_by="shape_id",
                          shape_id=shape["id"], sources=SOURCES[:1],
                          **fields(table["provinces"][p],
                                   f"The 2022 census's count for {p} Province.")))
    return out


def pages_of(blob: bytes) -> list[str]:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=("2023", "2024"), expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = parse(pages_of(blob))
    log(f"  {len(table['districts'])} districts in {len(PROVINCES)} provinces, making "
        f"{table['provinces']['Total']['total']:,}")
    records = build(table, units("ZWE", "admin1"), units("ZWE", "admin2"))
    for r in records:
        pop = r["population"].get("value")
        log(f"  {r['level']} {r['name']}: {pop if pop is None else f'{pop:,}'}; "
            f"{r.get('population_note') or r['population'].get('note', '')[:80]}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
