#!/usr/bin/env python3
"""Cambodia: population and sex ratio by district and province, 2019 census.

The National Institute of Statistics' final report on the 2019 General
Population Census --

    https://nis.gov.kh/wp-content/uploads/2025/09/Final-General-Population-Census-2019-English.pdf

-- carries two tables this map lacks:

* **Table 2.1.1** (report page 15): the total population by province and
  sex, every resident of the province counted, migrants working abroad left
  out. Each province's **sex ratio** (and its population) comes from here.
* **Tables P-01 to P-25** (report pages 146-208), one per province: for the
  province, each district (srok, khan, krong) and each commune (khum,
  sangkat), the number of households and the population by sex, "based on
  normal or regular households". Each district's **population** and **sex
  ratio** come from here. The regular-household population leaves out the
  1.6% of the country counted in institutions, homeless, on boats or in
  transit -- which the census counts only by province -- and every record
  says so.

**Which polygon a district is.** The boundary file draws the 197 districts of
OCHA's 2018 administrative boundaries; the census counts 204, Phnom Penh's
khans and several provinces having been divided since. So the census is
bound one level down, commune by commune: each 2019 commune is the 2018
commune with its own code and name, or failing that the one commune of its
name in its province (2018 gazetteer, OCHA's ``cod-ps-khm`` tabular data,
CC BY-IGO); a commune neither finds, in a district every other commune of
which stayed whole, goes with its district. Each 2018 district then takes
the sum of the 2019 communes that were in it, so a polygon drawn before a
division takes the parts it was divided into. A district the census left
whole must come back to its own row exactly; a commune that cannot be placed
leaves its polygon out, logged.

**Checks**, each a refusal: in every commune row males and females make the
total; every district's communes make the district, and every province's
districts the province, for households, males and females (a district row
that contradicts itself -- Kampong Cham's Chamkar Leu prints 5,160 in all four
columns -- is read as its communes' sum, logged, and the province's total
then checks it; a district code printed under the wrong province, Srei
Santhor's "211", is read from its communes' codes); in Table 2.1.1 every
province's sexes make its total and the 25 provinces make the census's
15,552,211.

Usage:
    python -m scripts.fetch_census.cambodia_census
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from . import cod_ps
from ._shared import PROCESSED, RAW, download, log, record, write_json
from .sea_cod_ps_age import bind_rows, spelled
from .sea_common import age_sex, fold

OUT = "cambodia_census.json"
YEAR = 2019
FINAL_PDF = ("https://nis.gov.kh/wp-content/uploads/2025/09/"
             "Final-General-Population-Census-2019-English.pdf")
CODAB_DATASET = "cod-ps-khm"
CODAB_RESOURCE = "KHM_AdminBoundaries_TabularData.xlsx"
NATIONAL = 15_552_211
SOURCE_PROVINCE = ("National Institute of Statistics, General Population Census of the Kingdom "
                   "of Cambodia 2019, final results, Table 2.1.1: total population by province "
                   "and sex")
SOURCE_DISTRICT = ("National Institute of Statistics, General Population Census of the Kingdom "
                   "of Cambodia 2019, final results, Tables P-01 to P-25: population in normal "
                   "or regular households by province, district and commune, and sex")
LICENCE = "Official statistics of the National Institute of Statistics, Ministry of Planning"
NUM = r"(-|\d{1,3}(?:,\d{3})*|\d+)"
ROW = re.compile(rf"^(?P<code>\d{{3,6}})\s+(?P<name>.*?\S)\s+{NUM}\s+{NUM}\s+{NUM}\s+{NUM}"
                 r"\s+(?:-|[\d.]+)\s+(?:-|[\d.]+)\s*$")
# Kampong Cham's table spells its total row "Toatl".
TOTAL = re.compile(rf"^(?:Total|Toatl)\s+{NUM}\s+{NUM}\s+{NUM}\s+{NUM}\s+(?:-|[\d.]+)\s+"
                   r"(?:-|[\d.]+)\s*$")
HEADER = re.compile(r"^(?P<code>\d{2})\s+(?P<name>[A-Z][A-Za-z' .-]+?)\s*$")
PROVINCE_ROW = re.compile(rf"^(?P<name>[A-Z][A-Za-z' .-]+?)\s+{NUM}\s+{NUM}\s+{NUM}\s*$")
HOUSEHOLD_NOTE = ("the census's district tables count the population of normal or regular "
                  "households, leaving out the 1.6% of the country in institutions, homeless, on "
                  "boats or in transit, which it counts by province only")


def number(text: str) -> int:
    return 0 if text == "-" else int(text.replace(",", ""))


def parse_annex(pages: list[str]) -> dict[int, dict[str, Any]]:
    """Tables P-01..P-25: {province: {name, n, districts: {code: {name, n, communes}}}},
    each n being (households, total, male, female)."""
    provinces: dict[int, dict[str, Any]] = {}
    current = None
    province = 0
    pending = None              # a district row whose printed code is not its province's
    carried = ""                # a row's code and name, its figures on the next line
    for page in pages:
        if not re.search(r"Table\s*P-\d{2}", page):
            continue
        for raw in page.splitlines():
            line = " ".join(raw.split())
            if carried:
                # The figures on the next line, and perhaps the name's last
                # word with them: "70206 Sdach Kong Khang" / "Cheung 1,375 ...".
                tail = re.fullmatch(rf"(?P<rest>[A-Za-z'.() -]*?)\s*(?:{NUM}\s+){{4}}"
                                    r"(?:-|[\d.]+)\s+(?:-|[\d.]+)", line)
                if tail and tail.group("rest").strip() not in ("Total", "Toatl", "Urban",
                                                               "Rural"):
                    line = f"{carried} {line}"
                elif current is not None:
                    current.setdefault("unread", []).append(carried)
                carried = ""
            if re.fullmatch(r"\d{3,6}\s+[^\d]+", line):
                carried = line
                continue
            if h := HEADER.match(line):
                if pending:
                    raise SystemExit(f"cambodia_census: the district row {pending['line']!r} "
                                     "is followed by no commune of its province")
                province = int(h.group("code"))
                current = provinces.setdefault(province, {"name": h.group("name"), "n": None,
                                                          "districts": {}})
                continue
            if current is None:
                continue
            if t := TOTAL.match(line):
                if current["n"] is None:
                    current["n"] = tuple(number(x) for x in t.groups())
                continue
            m = ROW.match(line)
            if not m:
                if re.match(r"^\d{3,6}\s", line):
                    current.setdefault("unread", []).append(line)
                continue
            code = int(m.group("code"))
            n = tuple(number(x) for x in m.groups()[2:6])
            if len(m.group("code")) <= 4:
                if pending:
                    raise SystemExit(f"cambodia_census: the district row {pending['line']!r} "
                                     "is followed by no commune of its province")
                if code // 100 == province:
                    current["districts"][code] = {"name": m.group("name"), "n": n,
                                                  "communes": {}}
                else:
                    # A misprinted district code -- Kampong Cham's Srei Santhor
                    # is printed "211" -- is read from its communes' codes.
                    pending = {"name": m.group("name"), "n": n, "line": line}
                continue
            district = code // 100
            if code // 10000 != province:
                raise SystemExit(f"cambodia_census: row {line!r} belongs to no district of "
                                 f"province {province:02d}")
            if pending and district not in current["districts"]:
                log(f"  the district row {pending['line']!r} is read as district {district}, "
                    f"its communes' code")
                current["districts"][district] = {"name": pending["name"], "n": pending["n"],
                                                  "communes": {}}
                pending = None
            if district not in current["districts"]:
                raise SystemExit(f"cambodia_census: row {line!r} belongs to no district of "
                                 f"province {province:02d}")
            current["districts"][district]["communes"][code] = {"name": m.group("name"),
                                                                "n": n}
    if pending:
        raise SystemExit(f"cambodia_census: the district row {pending['line']!r} is followed "
                         "by no commune of its province")
    return provinces


def check_annex(provinces: dict[int, dict[str, Any]]) -> None:
    if sorted(provinces) != list(range(1, 26)):
        raise SystemExit(f"cambodia_census: the annex names provinces {sorted(provinces)}")
    for p, prov in provinces.items():
        if prov["n"] is None or not prov["districts"]:
            raise SystemExit(f"cambodia_census: province {p:02d} has no total or no districts")
        for d, dist in prov["districts"].items():
            for unit in dist["communes"].values():
                _, t, m, f = unit["n"]
                if m + f != t:
                    raise SystemExit(f"cambodia_census: {unit['name']}: {m:,} males and {f:,} "
                                     f"females against {t:,}")
            made = tuple(sum(c["n"][i] for c in dist["communes"].values()) for i in range(4))
            _, t, m, f = dist["n"]
            if m + f != t and dist["communes"]:
                # A district row at odds with itself -- Kampong Cham's Chamkar
                # Leu prints 5,160 in all four columns -- is replaced by its
                # communes' sum; the province's own total checks the result.
                log(f"  district {d} {dist['name']}: its row {dist['n']} contradicts itself; "
                    f"read as its communes' sum {made}")
                dist["n"] = made
            if not dist["communes"] or made != dist["n"]:
                unread = [x for x in prov.get("unread", []) if x.startswith(str(d))]
                raise SystemExit(f"cambodia_census: district {d} {dist['name']}: its "
                                 f"{len(dist['communes'])} communes make {made}, against "
                                 f"{dist['n']}; its communes read: "
                                 f"{sorted(dist['communes'])}; rows not read: {unread}")
        made = tuple(sum(x["n"][i] for x in prov["districts"].values()) for i in range(4))
        if made != prov["n"]:
            raise SystemExit(f"cambodia_census: province {p:02d}: its districts make {made}, "
                             f"against {prov['n']}")
    districts = sum(len(v["districts"]) for v in provinces.values())
    communes = sum(len(d["communes"]) for v in provinces.values()
                   for d in v["districts"].values())
    people = sum(v["n"][1] for v in provinces.values())
    log(f"  Tables P-01..P-25: {districts} districts and {communes} communes in 25 provinces, "
        f"each district's communes and each province's districts making its row; "
        f"{people:,} people in regular households")


def parse_provinces(pages: list[str], annex: dict[int, dict[str, Any]]
                    ) -> dict[int, tuple[int, int, int]]:
    """Table 2.1.1: province -> (male, female, total), named as the annex names them."""
    page = next((p for p in pages if re.search(r"Table\s*2\.1\.1", p)), None)
    if page is None:
        raise SystemExit("cambodia_census: no Table 2.1.1")
    codes = {fold(v["name"]): p for p, v in annex.items()}
    out: dict[int, tuple[int, int, int]] = {}
    for raw in page.splitlines():
        m = PROVINCE_ROW.match(" ".join(raw.split()))
        if not m:
            continue
        code = codes.get(fold(m.group("name")))
        if code is None:
            continue                               # a region, or the urban/rural rows
        male, female, total = (number(x) for x in m.groups()[1:])
        if male + female != total:
            raise SystemExit(f"cambodia_census: Table 2.1.1 {m.group('name')}: sexes make "
                             f"{male + female:,}, against {total:,}")
        out[code] = (male, female, total)
    if sorted(out) != list(range(1, 26)) or sum(v[2] for v in out.values()) != NATIONAL:
        raise SystemExit(f"cambodia_census: Table 2.1.1 gives {len(out)} provinces making "
                         f"{sum(v[2] for v in out.values()):,}, not 25 making {NATIONAL:,}")
    log(f"  Table 2.1.1: 25 provinces making {NATIONAL:,}")
    return out


def gazetteer() -> dict[str, list[dict[str, Any]]]:
    """OCHA's 2018 tabular boundaries for Cambodia: ADM1, ADM2, ADM3 rows."""
    import openpyxl
    package = cod_ps.get("package_show", id=CODAB_DATASET)
    resource = next((r for r in package.get("resources") or ()
                     if str(r.get("name") or "") == CODAB_RESOURCE), None)
    if resource is None:
        raise SystemExit(f"cambodia_census: {CODAB_DATASET} has no {CODAB_RESOURCE}")
    path = download(str(resource["url"]), RAW / "cambodia" / CODAB_RESOURCE)
    book = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
    out: dict[str, list[dict[str, Any]]] = {}
    for sheet in book.worksheets:
        if sheet.title.upper() not in ("ADM1", "ADM2", "ADM3"):
            continue
        rows = sheet.iter_rows(values_only=True)
        head = [str(c or "").strip() for c in next(rows)]
        out[sheet.title.upper()] = [dict(zip(head, r)) for r in rows if any(r)]
    log(f"  2018 gazetteer: {', '.join(f'{k} {len(v)}' for k, v in sorted(out.items()))}")
    return out


def crosswalk(annex: dict[int, dict[str, Any]], adm3: list[dict[str, Any]],
              adm2_codes: set[str]) -> tuple[dict[str, list[tuple[int, int, dict[str, Any]]]],
                                             list[str], set[str]]:
    """2018 district pcode -> [(2019 district, 2019 commune, its row)]; the communes
    that could not be placed; and the 2018 districts those make incomplete."""
    by_code = {str(r["ADM3_PCODE"]).strip(): r for r in adm3}
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in adm3:
        by_name[(str(r["ADM2_PCODE"])[:4], fold(r["ADM3_EN"]))].append(r)
    placed: dict[str, list[tuple[int, int, dict[str, Any]]]] = defaultdict(list)
    waiting: list[tuple[int, int, dict[str, Any]]] = []
    for p, prov in annex.items():
        for d, dist in prov["districts"].items():
            for c, com in dist["communes"].items():
                pcode = f"KH{c:06d}"
                hit = by_code.get(pcode)
                if hit is not None and fold(hit["ADM3_EN"]) != fold(com["name"]) \
                        and str(hit["ADM2_PCODE"]) != f"KH{d:04d}":
                    hit = None                     # the code was reused elsewhere
                if hit is None:
                    named = by_name.get((f"KH{p:02d}", fold(com["name"])), [])
                    hit = named[0] if len(named) == 1 else None
                if hit is None:
                    waiting.append((d, c, com))
                    continue
                placed[str(hit["ADM2_PCODE"]).strip()].append((d, c, com))
    # A commune neither its code nor its name finds goes with its district,
    # where every other commune of that district stayed in it.
    left: list[str] = []
    broken: set[str] = set()
    for d, c, com in waiting:
        home = f"KH{d:04d}"
        others = {pc for pc, items in placed.items() for (dd, _, _) in items if dd == d}
        if home in adm2_codes and others <= {home}:
            placed[home].append((d, c, com))
            continue
        left.append(f"{c} {com['name']} (district {d})")
        broken |= others | ({home} if home in adm2_codes else set())
    return placed, left, broken


def district_records(annex, placed, broken, adm2_rows) -> list[dict[str, Any]]:
    districts = {d: dist for prov in annex.values() for d, dist in prov["districts"].items()}
    rows = [r for r in adm2_rows if str(r["ADM2_PCODE"]).strip() in placed
            and str(r["ADM2_PCODE"]).strip() not in broken]
    bound, left, unbound = bind_rows("KHM", "admin2", rows, "ADM2_EN", "ADM1_EN")
    log(f"  2018 districts on no polygon ({len(left)}): {'; '.join(left)}; polygons with no "
        f"district ({len(unbound)}): {', '.join(unbound)}")
    src = [{"field": "population/sex_ratio", "name": SOURCE_DISTRICT, "url": FINAL_PDF,
            "year": YEAR, "license": LICENCE}]
    out = []
    changed = []
    for i, unit in sorted(bound.items(), key=lambda kv: kv[1]["name"]):
        pcode = str(rows[i]["ADM2_PCODE"]).strip()
        items = placed[pcode]
        t = sum(com["n"][1] for _, _, com in items)
        m = sum(com["n"][2] for _, _, com in items)
        f = sum(com["n"][3] for _, _, com in items)
        parts = sorted({d for d, _, _ in items})
        whole = [d for d in parts
                 if {c for dd, c, _ in items if dd == d} == set(districts[d]["communes"])]
        if parts == [int(pcode[2:])] and whole == parts:
            if (t, m, f) != districts[parts[0]]["n"][1:]:
                raise SystemExit(f"cambodia_census: {pcode} adds to {t:,}, not its own row "
                                 f"{districts[parts[0]]['n'][1]:,}")
            label = f"{districts[parts[0]]['name']} district"
        else:
            label = ("the 2019 communes of " + ", ".join(
                f"{districts[d]['name']} ({len([1 for dd, _, _ in items if dd == d])} of "
                f"{len(districts[d]['communes'])} communes)" for d in parts)
                + " -- the polygon is the district as drawn in 2018")
            changed.append(f"{unit['name']} <- {', '.join(districts[d]['name'] for d in parts)}")
        whose = f"the 2019 census's count of {label}"
        out.append(record(
            f"KHM-D-{pcode}", unit["name"], level="admin2", parent="KHM", country="KHM",
            match_by="shape_id", shape_id=unit["id"], codes={"pcode": pcode}, sources=src,
            **age_sex(median=None, men=m, women=f, year=YEAR, source=SOURCE_DISTRICT,
                      median_note="", ratio_note=f"Males per 100 females in {whose} (Tables "
                                                 "P-01 to P-25).",
                      population=t,
                      population_note=(f"The 2019 census: {whose}, people in normal or "
                                       f"regular households ({HOUSEHOLD_NOTE})."))))
    log(f"  {len(out)} district polygons written; drawn before a division and summed from "
        f"their communes ({len(changed)}): {'; '.join(changed)}")
    return out


def province_records(table: dict[int, tuple[int, int, int]], adm1_rows) -> list[dict[str, Any]]:
    rows = [r for r in adm1_rows if int(str(r["ADM1_PCODE"]).strip()[2:]) in table]
    bound, left, unbound = bind_rows("KHM", "admin1", rows, "ADM1_EN", None)
    if left or unbound:
        raise SystemExit(f"cambodia_census: provinces on no polygon {left}, polygons with no "
                         f"province {unbound}")
    src = [{"field": "population/sex_ratio", "name": SOURCE_PROVINCE, "url": FINAL_PDF,
            "year": YEAR, "license": LICENCE}]
    out = []
    for i, unit in sorted(bound.items(), key=lambda kv: kv[1]["name"]):
        code = int(str(rows[i]["ADM1_PCODE"]).strip()[2:])
        male, female, total = table[code]
        whose = "the 2019 census's count of the province's whole population"
        out.append(record(
            f"KHM-P-{code:02d}", unit["name"], level="admin1", parent="KHM", country="KHM",
            match_by="shape_id", shape_id=unit["id"], sources=src,
            **age_sex(median=None, men=male, women=female, year=YEAR, source=SOURCE_PROVINCE,
                      median_note="", ratio_note=f"Males per 100 females in {whose} "
                                                 "(Table 2.1.1).",
                      population=total,
                      population_note=(f"The 2019 census: {whose}, migrants working abroad "
                                       "left out (Table 2.1.1)."))))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    from pypdf import PdfReader
    log(f"cambodia_census: {SOURCE_DISTRICT}")
    pdf = download(FINAL_PDF, RAW / "cambodia" / FINAL_PDF.rsplit("/", 1)[-1])
    pages = [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    log(f"  {len(pages)} pages")
    annex = parse_annex(pages)
    check_annex(annex)
    table = parse_provinces(pages, annex)
    for p, prov in annex.items():
        if not 0.9 * table[p][2] <= prov["n"][1] <= table[p][2]:
            raise SystemExit(f"cambodia_census: province {p:02d}'s regular households hold "
                             f"{prov['n'][1]:,} of its {table[p][2]:,}")
    gaz = gazetteer()
    adm2_codes = {str(r["ADM2_PCODE"]).strip() for r in gaz["ADM2"]}
    placed, left, broken = crosswalk(annex, gaz["ADM3"], adm2_codes)
    log(f"  communes placed in 2018 districts: {sum(len(v) for v in placed.values())}; not "
        f"placed ({len(left)}): {'; '.join(left[:60])}; 2018 districts left incomplete "
        f"({len(broken)}): {', '.join(sorted(broken))}")
    records = district_records(annex, placed, broken, gaz["ADM2"]) + province_records(
        table, gaz["ADM1"])
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
