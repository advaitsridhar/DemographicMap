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
districts the province, for households, males and females (where a district
row and its communes disagree -- Kampong Cham's Chamkar Leu prints 5,160 in
all four columns, Kandal's Kandal Stueng another district's 332,843 -- the
province's own total decides: the communes' sum stands only if with it the
districts make the province, and is logged; a district code printed under
the wrong province, Srei Santhor's "211", is read from its communes'
codes); in Table 2.1.1 every
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
from ._shared import NOT_AVAILABLE, PROCESSED, RAW, download, gap, log, record, write_json
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
BELOW_PROVINCE = ("The 2019 census's final report tabulates each district by population and "
                  "sex only (Tables P-01 to P-25), and {what}. Its 25 provincial reports, "
                  "which tabulate below the province, set their text in a form that does not "
                  "extract: Kep's 143 pages yield none of the words District, Religion or "
                  "Mother.")
DISTRICT_AGE_GAP = BELOW_PROVINCE.format(what="ages by province and above")
DISTRICT_RELIGION_GAP = BELOW_PROVINCE.format(what="religion by province and above "
                                                   "(Table 2.5.1)")
DISTRICT_LANGUAGE_GAP = BELOW_PROVINCE.format(what="mother tongue for the country only "
                                                   "(Table 2.7.1)")
# Districts the census counts that were cut from a single 2018 district:
# Phnom Penh's Khan Boeng Keng Kang, made in 2019 of four sangkats of Khan
# Chamkar Mon, whose other sangkats the census still counts under Chamkar Mon.
DIVIDED_FROM = {1213: "KH1201"}
# Below this share of a province's people in regular households, its district
# tables would understate its districts by the rest, and are not used.
HOUSEHOLD_FLOOR = 0.95
LOW_HOUSEHOLDS = ("The 2019 census's district tables count only the people of normal or regular "
                  "households, and in {province} {share:.0%} of the people the census counted "
                  "lived outside them -- in work camps, institutions, on boats or in transit "
                  "(Table 2.1.1 against Tables P-01 to P-25) -- so a district's figure from "
                  "those tables would understate it by as much, and is not written.")
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
                # The figures on a later line, the name's last word before
                # them or with them: "70206 Sdach Kong Khang" / "Cheung" /
                # "1,375 5,228 ...".
                if (re.fullmatch(r"[A-Za-z'][A-Za-z' .-]{0,30}", line) and len(line.split()) <= 3
                        and line.split()[0] not in ("Total", "Toatl", "Urban", "Rural", "Based",
                                                    "Table", "Household", "Ratio")):
                    carried = f"{carried} {line}"
                    continue
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


def check_annex(provinces: dict[int, dict[str, Any]],
                table: dict[int, tuple[int, int, int]] | None = None) -> None:
    if sorted(provinces) != list(range(1, 26)):
        raise SystemExit(f"cambodia_census: the annex names provinces {sorted(provinces)}")
    for p, prov in provinces.items():
        if prov["n"] is None or not prov["districts"]:
            raise SystemExit(f"cambodia_census: province {p:02d} has no total or no districts")
        disputed: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {}
        for d, dist in prov["districts"].items():
            for unit in dist["communes"].values():
                _, t, m, f = unit["n"]
                if m + f != t:
                    raise SystemExit(f"cambodia_census: {unit['name']}: {m:,} males and {f:,} "
                                     f"females against {t:,}")
            if not dist["communes"]:
                raise SystemExit(f"cambodia_census: district {d} {dist['name']} has no commune")
            made = tuple(sum(c["n"][i] for c in dist["communes"].values()) for i in range(4))
            if made != dist["n"]:
                disputed[d] = (dist["n"], made)
        # A district row its communes do not make is a misprint of one or the
        # other -- Kampong Cham's Chamkar Leu prints 5,160 in all four
        # columns, Kandal Stueng another district's 332,843 -- and the
        # province's own total decides between them: the communes' sum stands
        # if, with it, the districts make the province, and anything else
        # refuses.
        for d, (row, made) in disputed.items():
            prov["districts"][d]["n"] = made
        made = tuple(sum(x["n"][i] for x in prov["districts"].values()) for i in range(4))
        if disputed and made == prov["n"]:
            for d, (row, sums) in disputed.items():
                log(f"  district {d} {prov['districts'][d]['name']}: its row {row} is not its "
                    f"communes' sum {sums}; the communes' sum makes the province's total, and "
                    "stands")
        elif disputed:
            raise SystemExit("cambodia_census: " + "; ".join(
                f"district {d} {prov['districts'][d]['name']}: its "
                f"{len(prov['districts'][d]['communes'])} communes make {sums}, against "
                f"{row}; rows not read: "
                f"{[x for x in prov.get('unread', []) if x.startswith(str(d))]}"
                for d, (row, sums) in disputed.items()))
        if made != prov["n"]:
            # Prey Veng's total row prints 1,049,361 people where its
            # districts -- each its own communes' sum -- make 1,056,866, with
            # the households agreeing to the one. Where the households agree
            # and the districts' people fit inside the province's whole
            # population (Table 2.1.1), the total row is the misprint.
            whole = (table or {}).get(p, (0, 0, 0))[2]
            if made[0] == prov["n"][0] and whole and made[1] <= whole:
                log(f"  province {p:02d} {prov['name']}: its total row {prov['n']} is not its "
                    f"districts' sum {made}; the households agree and the districts' people "
                    f"fit in its {whole:,} (Table 2.1.1), so the districts stand")
                prov["n"] = made
            else:
                raise SystemExit(f"cambodia_census: province {p:02d}: its districts make "
                                 f"{made}, against {prov['n']}")
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
            # The two tables romanise a few names differently ("Tbong" and
            # "Tboung"); one close match among the 25, and only one, is the
            # province. Regions and the urban/rural rows match none.
            import difflib
            close = difflib.get_close_matches(fold(m.group("name")), list(codes), n=2,
                                              cutoff=0.8)
            if len(close) != 1 or codes[close[0]] in out:
                continue
            code = codes[close[0]]
            log(f"  Table 2.1.1 {m.group('name')!r} read as province {code:02d} "
                f"({annex[code]['name']})")
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
    # A commune neither its code nor its name finds is placed, in turn: by a
    # close spelling of a 2018 commune of its province, if that commune lies
    # in a 2018 district its own district's other communes went to (or the
    # one its district was cut from); else with its district, where every
    # other commune of that district stayed in one 2018 district.
    from difflib import SequenceMatcher
    left: list[str] = []
    broken: set[str] = set()
    for d, c, com in waiting:
        home = f"KH{d:04d}"
        others = {pc for pc, items in placed.items() for (dd, _, _) in items if dd == d}
        target = DIVIDED_FROM.get(d) or (home if home in adm2_codes else None)
        allowed = others | ({target} if target else set())
        scored = sorted(((SequenceMatcher(None, fold(com["name"]), fold(r["ADM3_EN"])).ratio(), r)
                         for r in adm3 if str(r["ADM2_PCODE"])[:4] == f"KH{d // 100:02d}"),
                        key=lambda x: -x[0])
        if (scored and scored[0][0] >= 0.8
                and (len(scored) == 1 or scored[1][0] <= scored[0][0] - 0.1)
                and str(scored[0][1]["ADM2_PCODE"]).strip() in allowed):
            best = scored[0][1]
            log(f"  commune {c} {com['name']} read as the 2018 {best['ADM3_EN']} "
                f"({best['ADM3_PCODE']}, {scored[0][0]:.2f})")
            placed[str(best["ADM2_PCODE"]).strip()].append((d, c, com))
            continue
        if target and others <= {target}:
            placed[target].append((d, c, com))
            continue
        near = ", ".join(f"{r['ADM3_EN']} {r['ADM3_PCODE']} {s:.2f}" for s, r in scored[:2])
        left.append(f"{c} {com['name']} (district {d}; nearest {near})")
        broken |= others | ({target} if target else set())
    return placed, left, broken


def district_records(annex, placed, broken, adm2_rows,
                     low: dict[int, float] | None = None) -> list[dict[str, Any]]:
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
    skipped = []
    for i, unit in sorted(bound.items(), key=lambda kv: kv[1]["name"]):
        pcode = str(rows[i]["ADM2_PCODE"]).strip()
        items = placed[pcode]
        province = int(pcode[2:4])
        if low and province in low:
            note = LOW_HOUSEHOLDS.format(province=annex[province]["name"],
                                         share=1 - low[province])
            skipped.append(unit["name"])
            out.append(record(
                f"KHM-D-{pcode}", unit["name"], level="admin2", parent="KHM", country="KHM",
                match_by="shape_id", shape_id=unit["id"], codes={"pcode": pcode},
                population=gap(NOT_AVAILABLE, note), sex_ratio=gap(NOT_AVAILABLE, note),
                median_age=gap(NOT_AVAILABLE, DISTRICT_AGE_GAP),
                religion=gap(NOT_AVAILABLE, DISTRICT_RELIGION_GAP),
                language=gap(NOT_AVAILABLE, DISTRICT_LANGUAGE_GAP)))
            continue
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
            median_age=gap(NOT_AVAILABLE, DISTRICT_AGE_GAP),
            religion=gap(NOT_AVAILABLE, DISTRICT_RELIGION_GAP),
            language=gap(NOT_AVAILABLE, DISTRICT_LANGUAGE_GAP),
            **age_sex(median=None, men=m, women=f, year=YEAR, source=SOURCE_DISTRICT,
                      median_note="", ratio_note=f"Males per 100 females in {whose} (Tables "
                                                 "P-01 to P-25).",
                      population=t,
                      population_note=(f"The 2019 census: {whose}, people in normal or "
                                       f"regular households ({HOUSEHOLD_NOTE})."))))
    log(f"  {len(out)} district polygons written, {len(skipped)} of them with stated gaps "
        f"({', '.join(skipped)}); drawn before a division and summed from their communes "
        f"({len(changed)}): {'; '.join(changed)}")
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


def explain(annex: dict[int, dict[str, Any]], gaz: dict[str, list[dict[str, Any]]]) -> None:
    """Print, province by province, each census district beside the 2018 district
    of the same code, and for a province where any of them differ by name, every
    commune on both sides. Nothing is written."""
    adm2 = {str(r["ADM2_PCODE"]).strip(): str(r["ADM2_EN"]) for r in gaz["ADM2"]}
    for p, prov in sorted(annex.items()):
        odd = [d for d, dist in prov["districts"].items()
               if fold(adm2.get(f"KH{d:04d}", "")) != fold(dist["name"])]
        if not odd:
            continue
        log(f"  province {p:02d} {prov['name']}: census districts "
            + "; ".join(f"{d} {dist['name']} ({len(dist['communes'])})"
                        + ("" if d not in odd else f" [2018 KH{d:04d}: "
                           f"{adm2.get(f'KH{d:04d}', '-')}]")
                        for d, dist in sorted(prov["districts"].items())))
        log("    2018 districts: " + "; ".join(f"{k} {v}" for k, v in sorted(adm2.items())
                                                 if k[2:4] == f"{p:02d}"))
        if len(odd) < 2 and p != 25:
            continue
        for d, dist in sorted(prov["districts"].items()):
            log(f"    census {d} {dist['name']}: " + ", ".join(
                f"{c} {com['name']}" for c, com in sorted(dist["communes"].items())))
        for code in sorted(k for k in adm2 if k[2:4] == f"{p:02d}"):
            log(f"    2018 {code} {adm2[code]}: " + ", ".join(
                f"{r['ADM3_PCODE']} {r['ADM3_EN']}" for r in gaz["ADM3"]
                if str(r["ADM2_PCODE"]).strip() == code))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--explain", action="store_true",
                    help="print the census's districts beside the 2018 gazetteer's where "
                         "their codes name different districts; write nothing")
    args = ap.parse_args()
    from pypdf import PdfReader
    log(f"cambodia_census: {SOURCE_DISTRICT}")
    pdf = download(FINAL_PDF, RAW / "cambodia" / FINAL_PDF.rsplit("/", 1)[-1])
    pages = [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    log(f"  {len(pages)} pages")
    annex = parse_annex(pages)
    table = parse_provinces(pages, annex)
    check_annex(annex, table)
    if args.explain:
        explain(annex, gazetteer())
        return 0
    low: dict[int, float] = {}
    for p, prov in annex.items():
        if prov["n"][1] > table[p][2]:
            raise SystemExit(f"cambodia_census: province {p:02d}'s regular households hold "
                             f"{prov['n'][1]:,}, more than its {table[p][2]:,}")
        share = prov["n"][1] / table[p][2]
        if share < HOUSEHOLD_FLOOR:
            low[p] = share
    log("  regular households' share of each province's people: lowest "
        + ", ".join(f"{annex[p]['name']} {prov['n'][1] / table[p][2]:.1%}"
                    for p, prov in sorted(annex.items(),
                                          key=lambda kv: kv[1]["n"][1] / table[kv[0]][2])[:5])
        + f"; provinces below {HOUSEHOLD_FLOOR:.0%}, whose district tables are not used: "
        + (", ".join(f"{annex[p]['name']} ({s:.1%})" for p, s in sorted(low.items())) or "none"))
    gaz = gazetteer()
    adm2_codes = {str(r["ADM2_PCODE"]).strip() for r in gaz["ADM2"]}
    placed, left, broken = crosswalk(annex, gaz["ADM3"], adm2_codes)
    log(f"  communes placed in 2018 districts: {sum(len(v) for v in placed.values())}; not "
        f"placed ({len(left)}): {'; '.join(left[:60])}; 2018 districts left incomplete "
        f"({len(broken)}): {', '.join(sorted(broken))}")
    records = district_records(annex, placed, broken, gaz["ADM2"], low) + province_records(
        table, gaz["ADM1"])
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
