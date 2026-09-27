#!/usr/bin/env python3
"""Saint Lucia: the 2022 census by district, and the 2010 census by settlement.

What this reads, all from the Central Statistics Office (CSO):

* **The 2022 census's REDATAM base** (``PHC2022`` on CELADE's server), by
  district, each person counted with the CSO's weight -- the census's own
  estimate of the undercount, a factor from 1.107 (Anse La Raye) to 1.507
  (Laborie), the weights that give the report's household population of
  171,834: sex (P1_2), five-year age group (P1_3B) and ethnicity (P1_4). The
  base breaks Castries into City, Suburban and Rural; the three are summed.
* **The 2022 Provisional Census Report, Release 2**: Table D.2, religion by
  district, and Table A.9, households, population, men and women by
  settlement ("community"), both weighted as above.
* **The 2010 census's REDATAM base** (``PHC2010C``), cross-tabulated by
  settlement: sex, single year of age, ethnic group and religion. The map's
  547 settlement outlines are the 2010 census's settlements, drawn and named
  as that census named them ("Monkey Town/Ciceron", "Hill 20/Babonneau"), so
  a 2010 row binds to its outline by name within its district -- or, where
  the census files a settlement under the district next door, to the island's
  only outline of that name (``bind_2010``). The base holds
  147,581 people, fewer than the 2010 census's 165,595 in households, so its
  settlement figures are compositions of the people it holds and are never
  written as a population.

What this writes:

* **The ten districts**: 2022 population, sex ratio and median age (within
  the five-year group holding the middle person), ethnicity as the 2022 base
  tabulates it -- African descent/Black, Other, Not reported, nothing finer --
  and religion from Table D.2.
* **The settlements**: median age, ethnic group and religion from the 2010
  base; the 2022 population and sex ratio from Table A.9 where a 2022
  settlement of the same name stands in the same district and its size is
  within DRIFT of the 2010 base's count of the outline (the 2022 list
  renamed, split and joined settlements -- Banannes Bay counts 333 people in
  the 2010 base and 71 in 2022 -- so a name alone is not proof); the 2010
  base's sex ratio otherwise. Every outline with no figure says why.

Neither census asks a language question: the 2022 base's dictionary (DICALL)
and the 2010 base's list no language variable, only difficulty speaking.

Checks, each of which stops the run: the 2022 tables' districts make 171,834
and agree with one another and with Table D.2's district totals; Table D.2's
religions make each district; Table A.9's settlements make their district's
line, and its districts the island's; every crosstab row makes its total.

Usage:
    python -m scripts.fetch_census.lucia_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from .binding import fold
from .cod_ps_age import grouped_median
from .isthmus import crosstabs
from .redatam import Server, median_age, tables

OUT = PROCESSED / "lucia_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
CMDSET = "https://prod.redatam.org/binlca/RpWebStats.exe/CmdSet"
PORTAL = "https://prod.redatam.org/binlca/RpWebEngine.exe/Portal?BASE={base}&lang=eng"
REPORT = ("https://www.stats.gov.lc/wp-content/uploads/2024/08/"
          "StLucia-Provisional-Census-Report2022-Release-2Rev-2.5.pdf")
SOURCE_2022 = ("Central Statistics Office of Saint Lucia, 2022 Population and Housing Census, "
               "REDATAM base PHC2022 (weighted)")
SOURCE_REPORT = ("Central Statistics Office of Saint Lucia, 2022 Population and Housing Census: "
                 "Provisional Census Report, Release 2")
SOURCE_2010 = ("Central Statistics Office of Saint Lucia, 2010 Population and Housing Census, "
               "REDATAM base PHC2010C")
HOUSEHOLD_2022 = 171_834
# What rounding the weighted tables may leave between a sum and its printed
# total, in people. The report's own Table A.9 settlements miss their district
# lines by up to five; a dropped row or a misread column is far more.
SLACK = 6
# How far a 2022 settlement's count may stand from the 2010 base's count of
# the outline of the same name before the name is not taken as proof. The
# base holds 89% of 2010's household population and the island grew 4%, so
# a settlement unchanged in extent sits near 1.2.
DRIFT = 2.0

DISTRICTS = ("Castries", "Anse La Raye", "Canaries", "Soufriere", "Choiseul", "Laborie",
             "Vieux Fort", "Micoud", "Dennery", "Gros Islet")
CASTRIES_PARTS = ("Castries City", "Castries Suburban", "Castries Rural")

ETHNICITY_2022 = {"African Descent/Black": "African descent", "Other": "Other",
                  "Not reported": "Not stated"}
ETHNICITY_2010 = {
    "African Descent/Negor/Black": "African descent", "Indigenous people": "Indigenous",
    "East Indian": "East Indian", "Chinese": "Chinese", "Portuguese": "Portuguese",
    "Syrian/Lebanese": "Syrian/Lebanese", "White/Caucasian": "White", "Mixed": "Mixed",
    "Hispanic": "Hispanic", "other": "Other", "Not Stated": "Not stated",
}
RELIGION_2010 = {
    "Anglican": "Anglican", "Baptist": "Baptist", "Bahai": "Baha'i", "Bretheren": "Brethren",
    "Church of God": "Church of God", "Evangelical": "Evangelical", "Hindu": "Hindu",
    "Jehovah Witnesses": "Jehovah's Witnesses", "Methodist": "Methodist",
    "Moravian": "Moravian", "Muslim": "Muslim", "Pentacostal": "Pentecostal",
    "Presbyterian": "Presbyterian", "Rastafarian": "Rastafarian",
    "Roman Catholic": "Roman Catholic", "Salvation Army": "Salvation Army",
    "Seventh Day Adventist": "Seventh-day Adventist", "Lutheran": "Lutheran",
    "None": "No religion", "Not stated": "Not stated",
}
RELIGION_2022 = {
    "Anglican": "Anglican", "Baptist": "Baptist", "Bahai Faith": "Baha'i",
    "Brethren": "Brethren", "Buddhism": "Buddhist", "Mennonite": "Mennonite",
    "Hindu": "Hindu", "Hinduism": "Hindu", "Jehovah Witnesses": "Jehovah's Witnesses",
    "Methodist": "Methodist", "Mormon": "Mormon", "Islam": "Muslim",
    "Pentecostal": "Pentecostal", "Nazarene": "Church of the Nazarene",
    "Rastafarian": "Rastafarian", "Roman Catholic": "Roman Catholic",
    "Salvation Army": "Salvation Army", "Seventh Day Adventist": "Seventh-day Adventist",
    "Universal Church": "Universal Church",
    "Atheist - Do not believe in God": "Atheist",
    "None - No religion but believe in God": "No religion",
    "Other": "Other religion", "Not reported": "Not stated",
}
LANGUAGE_GAP = ("Saint Lucia's census does not ask a language question: neither the 2022 "
                "base's data dictionary (PHC2022, DICALL) nor the 2010 base's (PHC2010C) holds "
                "a language variable, only difficulty speaking.")

NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+|-)$")
AGE_GROUP = re.compile(r"^(\d+)\s*-\s*(\d+)$")
AGE_OPEN = re.compile(r"^(\d+)\s*\+$")
AGE_YEARS = re.compile(r"^(\d+)\s+years?$")



def present(counts: dict[str, float]) -> list[dict]:
    """Shares of the categories anyone is counted in; a zero is no one, not a group."""
    return shares({k: v for k, v in counts.items() if v})

def figure(token: str) -> int:
    return 0 if token == "-" else int(token.replace(",", ""))


def near(made: float, printed: float, what: str, slack: float = SLACK) -> None:
    """Within the rounding the weights leave, logged; beyond it, the run stops."""
    if abs(made - printed) > slack:
        raise SystemExit(f"lucia_census: {what} make {made:,}, printed {printed:,}")
    if made != printed:
        log(f"  {what} make {made:,}, printed {printed:,}")


# -- the report ---------------------------------------------------------------

def figure_rows(lines: list[str], width: int) -> list[list]:
    """[label, figures] for each line ending in ``width`` figures.

    A line without them continues the label above it (the report wraps a long
    name below its figures: "Atheist - Do not believe in 514 ..." / "God");
    lines before the first figure line are the table's heading.
    """
    out: list[list] = []
    for line in lines:
        tokens = line.split()
        if not tokens or re.fullmatch(r"\d+", line.strip()) or line.startswith("Saint Lucia Pop"):
            continue
        if len(tokens) > width and all(NUMBER.match(t) for t in tokens[-width:]):
            out.append([" ".join(tokens[:-width]), [figure(t) for t in tokens[-width:]]])
        elif out:
            out[-1][0] = f"{out[-1][0]} {line.strip()}"
    return out


def between(pages: list[list[str]], first: str, stop: str) -> list[str]:
    """The lines from the one starting ``first`` to the one starting ``stop``.

    The contents pages list every table with a dotted leader to its page
    number; the table's own title has none.
    """
    lines = [line for page in pages for line in page]
    start = next((i for i, l in enumerate(lines)
                  if l.startswith(first) and not re.search(r"\.{4,}", l)), None)
    if start is None:
        raise SystemExit(f"lucia_census: the report has no {first!r}")
    end = next((i for i, l in enumerate(lines[start + 1:], start + 1) if l.startswith(stop)),
               None)
    if end is None:
        raise SystemExit(f"lucia_census: nothing ends {first!r}")
    return lines[start + 1:end]


def religion_by_district(lines: list[str], island: int = HOUSEHOLD_2022
                         ) -> dict[str, dict[str, int]]:
    """{district: {religion: people}} from Table D.2, after its checks."""
    rows = figure_rows(lines, 11)
    if not rows or rows[0][0] != "Total":
        raise SystemExit(f"lucia_census: Table D.2 opens with {rows[:1]}")
    total = rows[0][1]
    if total[0] != island:
        raise SystemExit(f"lucia_census: Table D.2's total is {total[0]:,}")
    out: dict[str, dict[str, int]] = {d: {} for d in DISTRICTS}
    for label, numbers in rows[1:]:
        if label not in RELIGION_2022:
            raise SystemExit(f"lucia_census: Table D.2 religion {label!r} is not one this reads")
        near(sum(numbers[1:]), numbers[0], f"Table D.2's districts for {label}")
        for district, n in zip(DISTRICTS, numbers[1:]):
            name = RELIGION_2022[label]
            out[district][name] = out[district].get(name, 0) + n
    for j, district in enumerate(DISTRICTS, start=1):
        near(sum(out[district].values()), total[j], f"Table D.2's religions in {district}",
             slack=2 * SLACK)
        out[district]["_total"] = total[j]
    return out


SETTLEMENT_GROUP = re.compile(r"^(Castries (?:City|Suburban|Rural)|(.+) District|Saint Lucia)$")


def settlements_2022(lines: list[str]) -> dict[str, list[dict[str, Any]]]:
    """{district: [{name, households, population, men, women}]} from Table A.9."""
    groups: dict[str, dict[str, Any]] = {}
    current = None
    for label, (households, population, men, women) in figure_rows(lines, 4):
        m = SETTLEMENT_GROUP.match(label)
        if m:
            current = label
            groups[current] = {"total": population, "rows": []}
            continue
        if current is None:
            raise SystemExit(f"lucia_census: Table A.9 row {label!r} before any district")
        groups[current]["rows"].append({"name": label, "households": households,
                                        "population": population, "men": men,
                                        "women": women})
    island = groups.pop("Saint Lucia", None)
    if island is None or island["total"] != HOUSEHOLD_2022 or island["rows"]:
        raise SystemExit("lucia_census: Table A.9 does not open with the island's line")
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group, data in groups.items():
        near(sum(r["population"] for r in data["rows"]), data["total"],
             f"Table A.9's settlements of {group}")
        district = "Castries" if group in CASTRIES_PARTS else SETTLEMENT_GROUP.match(group)[2]
        if district not in DISTRICTS:
            raise SystemExit(f"lucia_census: Table A.9 group {group!r} is no district")
        out[district] += data["rows"]
    near(sum(g["total"] for g in groups.values()), HOUSEHOLD_2022, "Table A.9's districts",
         slack=3)
    return dict(out)


# -- the REDATAM bases --------------------------------------------------------

def district_of(area: str) -> str:
    """The district a 2022 base area belongs to (Castries City -> Castries)."""
    if area in CASTRIES_PARTS:
        return "Castries"
    for district in DISTRICTS:
        if fold(district) == fold(area):
            return district
    raise SystemExit(f"lucia_census: 2022 base area {area!r} is no district")


def by_district(found: list[dict], what: str) -> dict[str, Counter]:
    """{district: Counter(label: weighted people)} from one variable's area tables."""
    out: dict[str, Counter] = defaultdict(Counter)
    for table in found:
        if not table["area"]:
            continue
        rows = Counter()
        for label, n in table["rows"]:
            rows[label] += n
        near(sum(rows.values()), table["total"], f"the 2022 base's {what} in {table['name']}",
             slack=len(rows))
        out[district_of(table["name"])].update(rows)
    if set(out) != set(DISTRICTS):
        raise SystemExit(f"lucia_census: the 2022 base's {what} covers {sorted(out)}")
    return out


def age_groups(counts: Counter) -> list[tuple[int, int | None, float]]:
    groups = []
    for label, n in counts.items():
        m = AGE_GROUP.match(label.strip())
        o = AGE_OPEN.match(label.strip())
        if m:
            groups.append((int(m[1]), int(m[2]), n))
        elif o:
            groups.append((int(o[1]), None, n))
        else:
            raise SystemExit(f"lucia_census: age group {label!r} is not one this reads")
    return sorted(groups, key=lambda g: g[0])


def ages_of(columns: list[str]) -> list[int | None]:
    """The age each "N years" column holds, by its place where its label disagrees.

    The 2010 base labels its value 58 "68 years", so two columns read 68. The
    columns run in value order from 0, one a year, so the n-th is age n; a
    label that says otherwise is logged, and more than two such labels means
    a year is missing and the columns cannot be read by place.
    """
    out: list[int | None] = []
    wrong = []
    for column in columns:
        m = AGE_YEARS.match(column.strip())
        if not m:
            out.append(None)
            continue
        age = sum(1 for a in out if a is not None)
        if int(m[1]) != age:
            wrong.append((age, column))
        out.append(age)
    if len(wrong) > 2:
        raise SystemExit(f"lucia_census: the 2010 base's age columns are not one a year from "
                         f"0: {wrong[:5]}")
    for age, column in wrong:
        log(f"  the 2010 base labels age {age} {column!r}; read by its place")
    return out


def split_settlement(label: str) -> tuple[str, str | None]:
    """("BANANNES BAY", "Castries") from "BANANNES BAY - CASTRIES"; no suffix, no district."""
    if " - " in label:
        name, suffix = label.rsplit(" - ", 1)
        for district in DISTRICTS:
            if fold(district) == fold(suffix):
                return name.strip(), district
    return label.strip(), None


# -- binding -------------------------------------------------------------------

def parts(name: str) -> frozenset[str]:
    return frozenset(fold(p) for p in re.split(r"[/]", name) if fold(p))


# Names that say what kind of place a settlement is, not which one: the 2010
# census's Forest Reserve in Castries is not shown to be the map's in Gros Islet.
GENERIC = {fold(n) for n in ("Forest Reserve", "Village", "Town", "Estate")}


def bind_2010(labels: list[str], shapes: list[dict], district_of_shape: dict[str, str]
              ) -> tuple[dict[str, str], list[str], list[str]]:
    """({2010 label: shape id}, labels left out, labels bound across a district line).

    By name within the district first. A name the district does not draw
    binds to the one outline of that name in the island, if there is exactly
    one and no other label anywhere has the name: the census files Anse Galet
    under Canaries and the map draws it in Anse La Raye, the same place on
    either side of a line the two draw differently. A label without a district
    suffix binds only that way. Two outlines of one name in a district, or two
    labels folding to one name there, are left out.
    """
    by_name: dict[tuple[str | None, str], list[str]] = defaultdict(list)
    anywhere: dict[str, list[str]] = defaultdict(list)
    for shape in shapes:
        district = district_of_shape[shape["parent"]]
        by_name[(district, fold(shape["name"]))].append(shape["id"])
        anywhere[fold(shape["name"])].append(shape["id"])
    keyed: dict[tuple[str | None, str], list[str]] = defaultdict(list)
    named: Counter = Counter()
    for label in labels:
        name, district = split_settlement(label)
        keyed[(district, fold(name))].append(label)
        named[fold(name)] += 1
    bound, left, across = {}, [], []
    for (district, name), same in keyed.items():
        found = by_name.get((district, name), []) if district else []
        if len(same) == 1 and len(found) == 1:
            bound[same[0]] = found[0]
        elif (not found and named[name] == 1 and len(anywhere.get(name, [])) == 1
              and name not in GENERIC):
            bound[same[0]] = anywhere[name][0]
            across.append(same[0])
        else:
            left += same
    taken = Counter(bound.values())
    for label in [l for l, sid in bound.items() if taken[sid] > 1]:
        left.append(label)
        del bound[label]
    return bound, sorted(left), sorted(l for l in across if l in bound)


def bind_2022(rows: dict[str, list[dict]], shapes: list[dict],
              district_of_shape: dict[str, str]) -> dict[str, dict]:
    """{shape id: 2022 row}: the same name, or the same "/"-separated parts, in the district.

    The report adds the district to a name several districts share ("Bella
    Rosa - Castries"); that is taken off. A shape two rows would claim, or a
    row two shapes would, is left out.
    """
    claims: dict[str, list[dict]] = defaultdict(list)
    for district, items in rows.items():
        mine = [s for s in shapes if district_of_shape[s["parent"]] == district]
        for row in items:
            name, _ = split_settlement(row["name"])
            name = re.sub(r"\s+-\s+(?:Castries|Gros-Islet|Vieux-Fort|Soufriere|Choiseul|"
                          r"Laborie|Micoud|Dennery|Canaries|Anse La Raye)$", "", name, flags=re.I)
            exact = [s for s in mine if fold(s["name"]) == fold(name)]
            found = exact or [s for s in mine if parts(s["name"]) == parts(name)]
            if len(found) == 1:
                claims[found[0]["id"]].append(row)
    return {sid: items[0] for sid, items in claims.items() if len(items) == 1}


# -- fetching -------------------------------------------------------------------

def report_pages() -> list[list[str]]:
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(http_get(REPORT, binary=True, cache=False))) as pdf:
        for page in pdf.pages:
            out.append((page.extract_text() or "").splitlines())
    return out


def program(tables_: list[tuple[str, str]]) -> str:
    lines = ["RUNDEF Job", "    SELECTION ALL", ""]
    for i, (kind, what) in enumerate(tables_, 1):
        lines += [f"TABLE T{i}", f"    AS {kind}", f"    OF {what}", ""]
    return "\n".join(lines)


def read_2022() -> dict[str, dict[str, Counter]]:
    server = Server(CMDSET, "PHC2022", lang="eng", who="lucia_census")
    asked = [("sex", "PERSON.P1_2"), ("age", "PERSON.P1_3B"), ("ethnicity", "PERSON.P1_4")]
    text = program([("FREQUENCY", f"{v}\n    AREABREAK DISTRICT\n    WEIGHT PERSON.PERSON_WEIGHT")
                    for _, v in asked])
    pages = server.output(text)
    if len(pages) != len(asked):
        raise SystemExit(f"lucia_census: {len(asked)} tables asked of PHC2022, {len(pages)} came")
    out = {what: by_district(tables(page, "Counts"), what)
           for (what, _), page in zip(asked, pages)}
    for district in DISTRICTS:
        sexes = sum(out["sex"][district].values())
        for what in ("age", "ethnicity"):
            near(sum(out[what][district].values()), sexes,
                 f"the 2022 base's {what} in {district} against its sexes")
    near(sum(sum(c.values()) for c in out["sex"].values()), HOUSEHOLD_2022,
         "the 2022 base's districts")
    return out


def read_2010() -> dict[str, dict[str, dict[str, int]]]:
    """{question: {settlement label: {column: people}}} from the 2010 base's crosstabs."""
    server = Server(CMDSET, "PHC2010C", lang="eng", who="lucia_census")
    asked = [("sex", "PERSON.P36SEX"), ("age", "PERSON.P37AGE"),
             ("ethnicity", "PERSON.P38ETHNIC"), ("religion", "PERSON.P39RELIGIO")]
    pages = server.output(program([("CROSSTABS", f"HHOLD.SETTLEMENT BY {v}")
                                   for _, v in asked]))
    if len(pages) != len(asked):
        raise SystemExit(f"lucia_census: {len(asked)} tables asked of PHC2010C, {len(pages)} came")
    out = {}
    for (what, _), page in zip(asked, pages):
        found = crosstabs(page)
        if len(found) != 1 or not found[0]["cells"]:
            raise SystemExit(f"lucia_census: the 2010 {what} crosstab came back as "
                             f"{len(found)} tables")
        out[what] = found[0]
        log(f"  2010 base, settlement by {what}: {len(found[0]['cells'])} settlements, "
            f"{found[0]['totals']['Total'] if found[0]['totals'] else '?'} people")
    everyone = {label: row["Total"] for label, row in out["sex"]["cells"].items()}
    ages = {label: row["Total"] for label, row in out["age"]["cells"].items()}
    if everyone != ages:
        raise SystemExit("lucia_census: the 2010 sex and age crosstabs count different people")
    for what in ("ethnicity", "religion"):
        for label, row in out[what]["cells"].items():
            if row["Total"] > everyone.get(label, -1):
                raise SystemExit(f"lucia_census: 2010 {what} counts {row['Total']} in {label}, "
                                 f"more than its {everyone.get(label)} people")
    return out


# -- writing ---------------------------------------------------------------------

def composition(row: dict[str, int], labels: dict[str, str], what: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for column, n in row.items():
        if column == "Total":
            continue
        if column not in labels:
            raise SystemExit(f"lucia_census: 2010 {what} {column!r} is not one this reads")
        out[labels[column]] = out.get(labels[column], 0) + n
    return out


def sex_ratio(men: float, women: float, year: int, source: str) -> dict[str, Any]:
    if not women or not men:
        return gap(NOT_AVAILABLE, f"The {year} count here has {men:,.0f} men and "
                                  f"{women:,.0f} women; a ratio of either to none is no "
                                  "figure.")
    return measure(round(1000 * men / women), unit="males_per_1000_females", year=year,
                   source=source)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    pages = report_pages()
    religion = religion_by_district(between(pages, "Table D.2", "Table D.3"))
    settled = settlements_2022(between(pages, "Table A.9", "Table A.10"))
    now = read_2022()
    for district in DISTRICTS:
        near(sum(now["sex"][district].values()), religion[district]["_total"],
             f"the 2022 base's {district} against Table D.2's")
    then = read_2010()

    admin1 = json.loads((SITE / "admin1" / "LCA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "LCA.units.json").read_text())
    district_shape = {}
    for district in DISTRICTS:
        found = [u for u in admin1 if fold(u["name"]) == fold(district)]
        if len(found) != 1:
            raise SystemExit(f"lucia_census: district {district} has {len(found)} polygons")
        district_shape[district] = found[0]
    district_of_shape = {u["id"]: d for d, u in district_shape.items()}

    records = []
    for district in DISTRICTS:
        shape = district_shape[district]
        sexes = now["sex"][district]
        people = sum(sexes.values())
        groups = age_groups(now["age"][district])
        eth = {ETHNICITY_2022.get(k) or _refuse("2022 ethnicity", k): v
               for k, v in now["ethnicity"][district].items()}
        rel = {k: v for k, v in religion[district].items() if k != "_total"}
        records.append(record(
            f"LCA-CSO-{fold(district)}", shape["name"], level="admin1", parent="LCA",
            country="LCA", match_by="shape_id", shape_id=shape["id"],
            population=measure(round(people), year=2022, source=SOURCE_2022),
            population_note=("The 2022 census's household population, each person weighted "
                             "for the CSO's estimated undercount (Table A.3 prints the same)."),
            sex_ratio=sex_ratio(sexes.get("Male", 0), sexes.get("Female", 0), 2022, SOURCE_2022),
            sex_ratio_note="Men per thousand women in the weighted 2022 household population.",
            median_age=measure(grouped_median(groups), unit="years", year=2022,
                               source=SOURCE_2022),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person of the weighted 2022 household population."),
            ethnicity=present(eth), ethnicity_year=2022,
            ethnicity_note=("As the 2022 base tabulates ethnicity: African descent/Black, "
                            "Other and Not reported, nothing finer."),
            religion=present(rel), religion_year=2022,
            religion_note=("Table D.2 of the 2022 report, weighted. \"None - No religion but "
                           "believe in God\" is written as No religion and \"Atheist - Do not "
                           "believe in God\" as Atheist."),
            language=gap(NOT_AVAILABLE, LANGUAGE_GAP),
            sources=[{"field": "population/sex_ratio/median_age/ethnicity",
                      "name": SOURCE_2022, "url": PORTAL.format(base="PHC2022"), "year": 2022},
                     {"field": "religion", "name": f"{SOURCE_REPORT}, Table D.2",
                      "url": REPORT, "year": 2022}]))

    labels = list(then["sex"]["cells"])
    bound, left, across = bind_2010(labels, admin2, district_of_shape)
    log(f"  2010 base: {len(labels)} settlements, {len(bound)} bound to an outline by name, "
        f"{len(across)} of them the island's only outline of that name drawn in another "
        f"district: {across}; {len(left)} left out: {left}")
    columns = list(then["age"]["columns"])
    years = ages_of(columns)
    recent = bind_2022(settled, admin2, district_of_shape)
    records_by_shape: dict[str, dict] = {}
    drifted = []
    for label, sid in bound.items():
        shape = next(s for s in admin2 if s["id"] == sid)
        sex = then["sex"]["cells"][label]
        held = sex["Total"]
        age_row = then["age"]["cells"][label]
        ages = Counter({a: age_row[c] for a, c in zip(years, columns) if a is not None})
        eth = composition(then["ethnicity"]["cells"].get(label, {}), ETHNICITY_2010, "ethnicity")
        rel = composition(then["religion"]["cells"].get(label, {}), RELIGION_2010, "religion")
        fields: dict[str, Any] = {}
        row = recent.get(sid)
        if row and held and not (1 / DRIFT <= row["population"] / held <= DRIFT):
            drifted.append((shape["name"], held, row["population"]))
            row = None
        universe = (f"the {held:,} people the 2010 base holds in the settlement (the base holds "
                    "147,581 of the 2010 census's 165,595 in households)")
        if row:
            fields.update(
                population=measure(row["population"], year=2022, source=SOURCE_REPORT),
                population_note=(f"Table A.9 of the 2022 report, \"{row['name']}\": household "
                                 "population, weighted for the estimated undercount."),
                sex_ratio=sex_ratio(row["men"], row["women"], 2022, SOURCE_REPORT),
                sex_ratio_note=f"Men per thousand women, Table A.9 of the 2022 report.")
        else:
            why = ("its 2022 count stands more than {:g} times from the 2010 base's, so the 2022 "
                   "settlement of that name is not taken to be this outline").format(DRIFT) \
                if sid in recent else "Table A.9 of the 2022 report lists no settlement of this " \
                                      "name in the district"
            fields.update(
                population=gap(NOT_AVAILABLE, f"No population is written: {why}, and the 2010 "
                                              f"base is not the whole 2010 population."),
                sex_ratio=sex_ratio(sex.get("Male", 0), sex.get("Female", 0), 2010, SOURCE_2010),
                sex_ratio_note=f"Men per thousand women among {universe}.")
        records_by_shape[sid] = record(
            f"LCA-CSO-{sid}", shape["name"], level="admin2",
            parent="LCA", parent_name=district_shape[district_of_shape[shape["parent"]]]["name"],
            country="LCA",
            match_by="shape_id", shape_id=sid,
            median_age=measure(median_age(ages), unit="years", year=2010, source=SOURCE_2010),
            median_age_note=f"Interpolated within the single year holding the middle person of "
                            f"{universe}.",
            ethnicity=present(eth), ethnicity_year=2010,
            ethnicity_note=f"Ethnic group, as asked of {universe}.",
            religion=present(rel), religion_year=2010,
            religion_note=f"Religion, as asked of {universe}.",
            language=gap(NOT_AVAILABLE, LANGUAGE_GAP),
            sources=[{"field": "median_age/ethnicity/religion", "name": SOURCE_2010,
                      "url": PORTAL.format(base="PHC2010C"), "year": 2010},
                     {"field": "population/sex_ratio", "name": f"{SOURCE_REPORT}, Table A.9",
                      "url": REPORT, "year": 2022}],
            **fields)
    log(f"  2022 Table A.9: {len(recent)} outlines matched by name, {len(drifted)} of them "
        f"left out as more than {DRIFT:g} times from the 2010 base: {drifted}")
    unbound = [s for s in admin2 if s["id"] not in records_by_shape]
    for shape in unbound:
        why = ("The 2010 census's REDATAM base (PHC2010C) holds no settlement of this name in "
               "the district, or holds it twice, so nothing is bound to this outline.")
        records_by_shape[shape["id"]] = record(
            f"LCA-CSO-{shape['id']}", shape["name"], level="admin2",
            parent="LCA", parent_name=district_shape[district_of_shape[shape["parent"]]]["name"],
            country="LCA",
            match_by="shape_id", shape_id=shape["id"],
            **{f: gap(NOT_AVAILABLE, why) for f in ("population", "median_age", "sex_ratio",
                                                     "religion", "ethnicity")},
            language=gap(NOT_AVAILABLE, LANGUAGE_GAP))
    records += list(records_by_shape.values())
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(DISTRICTS)} districts, "
        f"{len(records_by_shape) - len(unbound)} settlements with figures, "
        f"{len(unbound)} outlines with the reason they have none")
    return 0


def _refuse(what: str, label: str):
    raise SystemExit(f"lucia_census: {what} {label!r} is not one this reads")


if __name__ == "__main__":
    raise SystemExit(main())
