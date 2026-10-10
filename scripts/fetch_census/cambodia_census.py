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
OCHA's 2018 administrative boundaries; the census counts 202, Phnom Penh's
khans and several provinces having been divided since. So the census is
bound one level down, commune by commune: each 2019 commune is the 2018
commune with its own code *and* its own name, or failing that the one commune
of its name in its province (2018 gazetteer, OCHA's ``cod-ps-khm`` tabular
data, CC BY-IGO); a commune neither finds, in a district every other commune
of which stayed whole, goes with its district. A code alone is never trusted:
the census numbers Tboung Khmum's districts and communes afresh (its 2501 is
Krong Suong, the gazetteer's KH2501 Dambae; its 250201 Anhchaeum, the
gazetteer's KH250201 Chhuk), so a code whose name differs is someone else's.
Each 2018 district then takes the sum of the 2019 communes that were in it,
so a polygon drawn before a division takes the parts it was divided into.

A census district that the 2018 gazetteer also has -- the same name in the
same province, ``Krong``/``Khan``/``Srok`` aside and a romanisation apart
(``homes``) -- must have every one of its communes in that 2018 district, or
the run refuses; and a polygon that takes one such district whole must come
back to that district's own row exactly. A commune that cannot be placed
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
DISTRICT_AGE_GAP = BELOW_PROVINCE.format(
    what="ages by province only in three broad groups (Table PT 02: 0-14, 15-59, 60 and "
         "over), single years only for the whole country (priority table A1)")
DISTRICT_RELIGION_GAP = BELOW_PROVINCE.format(what="religion by province and above "
                                                   "(Table 2.5.1)")
DISTRICT_LANGUAGE_GAP = BELOW_PROVINCE.format(what="mother tongue for the country only "
                                                   "(Table 2.7.1)")
# Districts the census counts that were cut from a single 2018 district:
# Phnom Penh's Khan Boeng Keng Kang, made in 2019 of four sangkats of Khan
# Chamkar Mon, whose other sangkats the census still counts under Chamkar Mon.
DIVIDED_FROM = {1213: "KH1201"}
# Communes the census counts in a district the 2018 gazetteer also has, but
# which the gazetteer has in another district: census commune -> the 2018
# district whose polygon holds it. None is known; a commune that needs one
# refuses the run until it is declared here with its evidence.
TRANSFERRED: dict[int, str] = {}
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
# Where a province's district tables are not used, an encyclopaedia's figure
# for one of its districts dated before this year is not shown either (the
# build's ``displaces_before``): it is the same undercount. Wikidata's 2019
# figures for Preah Sihanouk's four districts -- 73,036, 105,053, 25,791 and
# 15,985 -- are exactly the regular-household counts of Tables P-01 to P-25,
# 219,865 together, 70.9% of the province's 310,072 in Table 2.1.1. A figure
# from a later year is not this census's and is left to stand.
DISPLACES_BEFORE = YEAR + 1


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


# A census district and a 2018 district are one district when their names,
# the words Krong, Khan and Srok aside, are this alike and no other 2018
# district of the province comes within MARGIN of the best: measured on the
# 202 census districts, the furthest true pair is Phnom Penh's "Ruessei Kaev"
# and "Russey Keo" (0.70) and the closest false best Kambol's "Chamkar Mon"
# (0.50), and the runner-up is never within 0.2 of a true pair.
SAME_DISTRICT = 0.7
MARGIN = 0.1
DISTRICT_WORD = re.compile(r"(?i)^(?:krong|khan|srok)\s+")


def district_key(name: Any) -> str:
    return fold(DISTRICT_WORD.sub("", str(name or "").strip()))


def homes(annex: dict[int, dict[str, Any]], adm2: dict[str, str]) -> dict[int, str]:
    """Census district -> the 2018 district (pcode) that is the same district by
    name, for every census district the 2018 gazetteer also has. Codes play no
    part: the census renumbered Tboung Khmum's."""
    from difflib import SequenceMatcher
    out: dict[int, str] = {}
    for p, prov in annex.items():
        pool = {pc: district_key(n) for pc, n in adm2.items() if pc[2:4] == f"{p:02d}"}
        taken: dict[str, int] = {}
        for d, dist in sorted(prov["districts"].items()):
            if d in DIVIDED_FROM:
                continue
            key = district_key(dist["name"])
            scored = sorted(((SequenceMatcher(None, key, k).ratio(), pc) for pc, k in pool.items()),
                            reverse=True)
            if not scored or scored[0][0] < SAME_DISTRICT or (
                    len(scored) > 1 and scored[1][0] > scored[0][0] - MARGIN):
                continue
            pcode = scored[0][1]
            if pcode in taken:
                raise SystemExit(f"cambodia_census: census districts {taken[pcode]} and {d} "
                                 f"both read as the 2018 {adm2[pcode]} ({pcode})")
            taken[pcode] = d
            out[d] = pcode
    return out


def crosswalk(annex: dict[int, dict[str, Any]], adm3: list[dict[str, Any]],
              adm2: dict[str, str]) -> tuple[dict[str, list[tuple[int, int, dict[str, Any]]]],
                                             list[str], set[str]]:
    """2018 district pcode -> [(2019 district, 2019 commune, its row)]; the communes
    that could not be placed; and the 2018 districts those make incomplete.

    ``adm2`` is the gazetteer's 2018 districts, pcode -> name.

    A census district the gazetteer also has (``homes``) is looked for in that
    2018 district first: each of its communes is one of that district's by
    name, by a code the district holds, or by a close spelling; failing all
    three, a commune found by its exact name in another district of the
    province was moved there and must be declared (``TRANSFERRED``), and one
    found nowhere is new since 2018 (a commune divided, as Phnom Penh's
    Stueng Mean Chey into three) and goes with its district. A census district
    the gazetteer does not have is found commune by commune in the province:
    by a code whose name agrees, by its exact name, or by a close spelling in
    a 2018 district its other communes went to or it was cut from."""
    from difflib import SequenceMatcher
    home = homes(annex, adm2)
    by_code = {str(r["ADM3_PCODE"]).strip(): r for r in adm3}
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_district: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in adm3:
        by_name[(str(r["ADM2_PCODE"])[:4], fold(r["ADM3_EN"]))].append(r)
        by_district[str(r["ADM2_PCODE"]).strip()].append(r)

    def closest(name: str, rows: list[dict[str, Any]]) -> tuple[float, dict[str, Any]] | None:
        scored = sorted(((SequenceMatcher(None, fold(name), fold(r["ADM3_EN"])).ratio(), r)
                         for r in rows), key=lambda x: -x[0])
        if scored and scored[0][0] >= 0.8 and (
                len(scored) == 1 or scored[1][0] <= scored[0][0] - 0.1):
            return scored[0]
        return None

    placed: dict[str, list[tuple[int, int, dict[str, Any]]]] = defaultdict(list)
    waiting: list[tuple[int, int, dict[str, Any]]] = []
    moved: list[str] = []
    new: list[str] = []
    for p, prov in annex.items():
        for d, dist in prov["districts"].items():
            h = home.get(d)
            for c, com in dist["communes"].items():
                code_hit = by_code.get(f"KH{c:06d}")
                named = by_name.get((f"KH{p:02d}", fold(com["name"])), [])
                if h:
                    own = by_district[h]
                    if (any(fold(r["ADM3_EN"]) == fold(com["name"]) for r in own)
                            or (code_hit is not None
                                and str(code_hit["ADM2_PCODE"]).strip() == h)):
                        placed[h].append((d, c, com))
                        continue
                    near = closest(com["name"], own)
                    if near:
                        log(f"  commune {c} {com['name']} read as the 2018 {near[1]['ADM3_EN']} "
                            f"({near[1]['ADM3_PCODE']}, {near[0]:.2f})")
                        placed[h].append((d, c, com))
                        continue
                    if c in TRANSFERRED:
                        log(f"  commune {c} {com['name']} counted in {TRANSFERRED[c]}, the 2018 "
                            "district it was moved from")
                        placed[TRANSFERRED[c]].append((d, c, com))
                        continue
                    if named:
                        moved.append(f"{c} {com['name']} of {d} {dist['name']} (2018 {h}) is "
                                     "named only in " + ", ".join(
                                         f"{r['ADM2_PCODE']} ({r['ADM3_PCODE']})" for r in named))
                        continue
                    new.append(f"{c} {com['name']}")
                    placed[h].append((d, c, com))
                    continue
                hit = (code_hit if code_hit is not None
                       and fold(code_hit["ADM3_EN"]) == fold(com["name"]) else None)
                if hit is None:
                    hit = named[0] if len(named) == 1 else None
                if hit is None:
                    waiting.append((d, c, com))
                    continue
                placed[str(hit["ADM2_PCODE"]).strip()].append((d, c, com))
    if moved:
        raise SystemExit("cambodia_census: communes of a district both lists have, named only "
                         "in another district (a transfer, to be declared in TRANSFERRED, or a "
                         "misreading): " + "; ".join(moved))
    if new:
        log(f"  communes with no 2018 counterpart, counted with their own district ({len(new)}): "
            + ", ".join(new))
    # A commune of a district the gazetteer does not have, which neither its
    # code nor its name finds, is placed in turn: by a close spelling of a
    # 2018 commune of its province in a 2018 district its district's other
    # communes went to (or the one its district was cut from); else with
    # them, where they all went to one 2018 district.
    left: list[str] = []
    broken: set[str] = set()
    for d, c, com in waiting:
        others = {pc for pc, items in placed.items() for (dd, _, _) in items if dd == d}
        target = DIVIDED_FROM.get(d)
        allowed = others | ({target} if target else set())
        near = closest(com["name"], [r for r in adm3
                                     if str(r["ADM2_PCODE"])[:4] == f"KH{d // 100:02d}"])
        if near and str(near[1]["ADM2_PCODE"]).strip() in allowed:
            log(f"  commune {c} {com['name']} read as the 2018 {near[1]['ADM3_EN']} "
                f"({near[1]['ADM3_PCODE']}, {near[0]:.2f})")
            placed[str(near[1]["ADM2_PCODE"]).strip()].append((d, c, com))
            continue
        if len(allowed) == 1:
            placed[next(iter(allowed))].append((d, c, com))
            continue
        left.append(f"{c} {com['name']} (district {d}; nearest "
                    + (f"{near[1]['ADM3_EN']} {near[1]['ADM3_PCODE']}" if near else "-") + ")")
        broken |= allowed
    strays = [f"{c} {com['name']} of {d} (2018 {home[d]}) in {pc}"
              for pc, items in placed.items() for d, c, com in items
              if d in home and pc != home[d] and TRANSFERRED.get(c) != pc]
    if strays:
        raise SystemExit("cambodia_census: communes away from their own district: "
                         + "; ".join(sorted(strays)))
    log(f"  census districts that are 2018 districts by name: {len(home)}, each whole in it"
        + "".join(f"; {d} {annex[d // 100]['districts'][d]['name']} is {pc}"
                  for d, pc in sorted(home.items()) if int(pc[2:]) != d))
    return placed, left, broken


def district_records(annex, placed, broken, adm2_rows,
                     low: dict[int, float] | None = None) -> list[dict[str, Any]]:
    districts = {d: dist for prov in annex.values() for d, dist in prov["districts"].items()}
    home = homes(annex, {str(r["ADM2_PCODE"]).strip(): str(r["ADM2_EN"]) for r in adm2_rows})
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
                population=dict(gap(NOT_AVAILABLE, note), displaces_before=DISPLACES_BEFORE),
                sex_ratio=gap(NOT_AVAILABLE, note),
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
        if parts == whole and len(parts) == 1 and home.get(parts[0]) == pcode:
            if (t, m, f) != districts[parts[0]]["n"][1:]:
                raise SystemExit(f"cambodia_census: {pcode} adds to {t:,}, not its own row "
                                 f"{districts[parts[0]]['n'][1]:,}")
            label = f"{districts[parts[0]]['name']} district"
        else:
            named = [f"{districts[d]['name']} ({len([1 for dd, _, _ in items if dd == d])} "
                     f"of {len(districts[d]['communes'])} communes)" for d in parts]
            label = ("the 2019 communes of "
                     + (named[0] if len(named) == 1
                        else ", ".join(named[:-1]) + " and " + named[-1])
                     + ", which lie in the district as it was drawn in 2018")
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
                      # Not "The 2019 census: the 2019 census's count of ...",
                      # which said the census twice.
                      population_note=(f"{whose[0].upper()}{whose[1:]}: people in normal "
                                       f"or regular households ({HOUSEHOLD_NOTE})."))))
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
                      population_note=(f"{whose[0].upper()}{whose[1:]}, migrants working "
                                       "abroad left out (Table 2.1.1)."))))
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
    adm2 = {str(r["ADM2_PCODE"]).strip(): str(r["ADM2_EN"]) for r in gaz["ADM2"]}
    placed, left, broken = crosswalk(annex, gaz["ADM3"], adm2)
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
