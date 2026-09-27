#!/usr/bin/env python3
"""Hungary: the 2022 census by járás, Budapest district and county.

KSH publishes the 2022 census (Népszámlálás 2022, reference date 1 October
2022) through its census database, whose front end reads an SDMX-style JSON
API at nepszamlalas2022.ksh.hu/api: ``/api/version``, ``/api/structure/
<dataflow>/<version>`` for the code lists, and ``/api/dataflows/<dataflow>/
<version>/d/<DIM>:<code>+<code>,...`` for the figures, one keyed row per cell.
Two dataflows are read:

* WBS001 -- "Population by sex, age and district": single years of age by
  sex for the 174 járások, Budapest's 23 districts, the 19 counties and
  Budapest;
* WBS003 -- "Population data by settlement", which also answers for the
  districts and counties: religion (one answer a person), ethnicity
  (nemzetiség) and mother tongue.

**Ethnicity and mother tongue take up to two answers each** in the Hungarian
census, and KSH counts every declaration, so the shares are of people naming
that ethnicity or tongue and sum to more than 100; "No answer" is kept as
its own bar. Religion partitions the population: the Catholic total less its
Roman and Greek Catholics is written as "Catholic (unspecified)".

**Places.** geoBoundaries names a district after its seat ("Aszód"), KSH by
the seat's adjective ("Aszódi district"); the two match with the adjective's
-i taken off, and the few irregular ones (Eger/Egri, Szeghalom/Szeghalmi,
Mórahalom/Mórahalmi) and the boundary file's misspelling "Kunszentmártonj"
are declared. Budapest's districts are "District 1" to "District 23" in
KSH's English and "I. kerület" to "XXIII. kerület" on the map. KSH counts
some of Budapest's people in no district ("Budapest data not disaggregated
by district", code 999); they are in Budapest's figure and no district's.

**Districts as drawn in 2013.** The map draws the districts of 2013-2014: in
Fejér a Polgárdi district between Enying and Székesfehérvár, which KSH's 2022
census counts in those two, and elsewhere a few settlements in the district
they have since left. Every settlement's district in KSH's own gazetteer of
1 January 2014 (Helységnévtár, ``hnt_letoltes_2014.xls``) is compared with
the 2022 census's; each district whose settlements changed is summed from
its 2014 settlements, which WBS003 also answers for: population, sex ratio
and the three compositions. A move between counties stops the run. KSH
publishes age by settlement in ten-year groups only, so such a district keeps
the single-year median of its 2022 namesake only where the two differ by no
more than 2% of the people, and says by whom; otherwise the median is a
stated gap.

**First level.** The map files Budapest's districts under Pest, whose
polygon therefore covers Budapest too, so the Pest record is Pest county and
Budapest together, summed from the same counts and saying so. The other
eighteen counties take their compositions; their ages already come from
Eurostat.

Usage:
    python -m scripts.fetch_census.hungary
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, dated, gap, http_get, http_json, log, measure, record,
                      shares, write_json)
from .central_ages import (SEX_RATIO_UNIT, age_sex_fields, check_national_median, check_sum, fold,
                           report_unbound, sex_ratio, units)

API = "https://nepszamlalas2022.ksh.hu/api"
GAZETTEER = "https://www.ksh.hu/docs/helysegnevtar/hnt_letoltes_2014.xls"
GAZETTEER_SOURCE = "KSH, Magyarország helységnévtára, 1 January 2014 (hnt_letoltes_2014.xls)"
PORTAL = "https://nepszamlalas2022.ksh.hu/adatbazis/"
SOURCE = "Hungarian Central Statistical Office (KSH), Census 2022 database ({flow})"
LICENCE = "KSH (free reuse with attribution)"
OUT = PROCESSED / "hungary_census.json"
YEAR = 2022
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV",
         "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII"]
# KSH's adjective -> the boundary file's name, where dropping the -i does not reach it.
IRREGULAR = {"Egri": "Eger", "Szeghalmi": "Szeghalom", "Mórahalmi": "Mórahalom",
             "Kunszentmártoni": "Kunszentmártonj", "Hegyháti": "Hegyhát",
             "Kiskunfélegyházi": "Kiskunfélegyháza", "Nyíregyházi": "Nyíregyháza",
             "Orosházi": "Orosháza"}
# The one district of 2014 that KSH's 2022 count no longer has, and the
# polygon the map draws for it; its settlements are now in Enying (079) and
# Székesfehérvár (085).
GONE_2014 = {"083": ("Polgard", "085")}
# A district rebuilt from its settlements keeps its 2022 namesake's median
# only when the settlements that differ hold at most this share of it.
MEDIAN_TOLERANCE = 0.02
RELIGION = {"RE_RC": "Roman Catholic", "RE_GC": "Greek Catholic", "RE_CA": "Reformed (Calvinist)",
            "RE_LU": "Lutheran", "RE_OC": "Orthodox", "RE_CD": "Other Christian",
            "RE_J": "Judaism", "RE_OCD": "Other religion", "RE_NOT": "No religion",
            "RE_NA": "Not stated"}
PARTITION = ("RE_C", "RE_CA", "RE_LU", "RE_OC", "RE_CD", "RE_J", "RE_OCD", "RE_NOT", "RE_NA")
ETHNICITY = {"EG_HU": "Hungarian", "EG_BU": "Bulgarian", "EG_GI": "Romani", "EG_GR": "Greek",
             "EG_CR": "Croatian", "EG_PO": "Polish", "EG_GE": "German", "EG_AR": "Armenian",
             "EG_RO": "Romanian", "EG_RU": "Rusyn", "EG_SE": "Serbian", "EG_SK": "Slovak",
             "EG_SL": "Slovene", "EG_UK": "Ukrainian", "EG_O": "Other", "EG_NA": "Not stated"}
LANGUAGE = {"MT_HU": "Hungarian", "MT_BU": "Bulgarian", "MT_GIR": "Romani", "MT_GIB": "Boyash",
            "MT_GR": "Greek", "MT_CR": "Croatian", "MT_PO": "Polish", "MT_GE": "German",
            "MT_AR": "Armenian", "MT_RO": "Romanian", "MT_RU": "Rusyn", "MT_SE": "Serbian",
            "MT_SK": "Slovak", "MT_SL": "Slovene", "MT_UK": "Ukrainian", "MT_O": "Other",
            "MT_NA": "Not stated"}
NOTES = {
    "religion": ("Religion, Census 2022 (1 October 2022): one answer per person, voluntary; "
                 "everyone counted, with 'Not stated' for those who did not answer. Catholics "
                 "who named neither the Roman nor the Greek rite are 'Catholic (unspecified)'. "
                 "KSH blanks cells of a few people for confidentiality; they are left out."),
    "ethnicity": ("Ethnicity (nemzetiség), Census 2022: a person could declare up to two and "
                  "every declaration is counted, so each share is the percentage of the "
                  "population naming that ethnicity and the shares sum to more than 100. 'Not "
                  "stated' is those who gave no answer. The thirteen domestic nationalities are "
                  "named; all others are 'Other'."),
    "language": ("Mother tongue, Census 2022: a person could name up to two, and every "
                 "declaration is counted, so the shares sum to more than 100. Romani and Boyash "
                 "(Beás) are counted apart; 'Not stated' is those who gave no answer."),
}


def version() -> str:
    return http_json(f"{API}/version", cache=False)["version"]


def codelists(flow: str, ver: str) -> dict[str, list[dict[str, Any]]]:
    data = http_json(f"{API}/structure/{flow}/{ver}", timeout=300)
    return {cl["id"]: cl.get("codes", []) for cl in data["data"]["codelists"]}


def rows(flow: str, ver: str, selection: str) -> list[dict[str, Any]]:
    return http_json(f"{API}/dataflows/{flow}/{ver}/d/{selection}", timeout=300)


def value(row: dict[str, Any]) -> float:
    v = row.get("OBS_VALUE")
    return float(v) if v not in (None, "") else 0.0


def build() -> list[dict[str, Any]]:
    ver = version()
    log(f"hungary: KSH census 2022 database, version {ver}")
    cl = codelists("WBS001", ver)
    geo = {c["id"]: c for c in cl["CL_TERUL_GEO4"]}
    name_of = {k: (c.get("names") or {}).get("en") or c.get("name") for k, c in geo.items()}
    parent_of = {k: c.get("parent") for k, c in geo.items()}
    ages = cl["CL_KEV_AGE"]
    parents = {c.get("parent") for c in ages}
    single = [c["id"] for c in ages if c["id"] not in parents and c["id"] != "TOTAL"]
    years: dict[str, int] = {}
    for code in single:
        m = re.fullmatch(r"Y(\d+)|Y_LT1|Y_GE(\d+)", code)
        if not m:
            raise SystemExit(f"hungary: an age code this reader does not read: {code}")
        years[code] = 0 if code == "Y_LT1" else int(m.group(1) or m.group(2))
    if sorted(years.values()) != list(range(len(years))):
        raise SystemExit(f"hungary: the single ages run {sorted(years.values())}")
    districts = sorted(k for k in geo if re.fullmatch(r"\d{3}", k) and k != "999")
    counties = sorted(k for k in geo if re.fullmatch(r"HU\d{3}", k))
    wanted = [*districts, "999", *counties, "HU"]
    log(f"  {len(districts)} districts, {len(counties)} counties (Budapest one of them), "
        f"{len(single)} single ages up to {max(years.values())}+")

    # Ages and sexes, a few dozen places a call.
    males: dict[str, Counter] = {}
    females: dict[str, Counter] = {}
    totals: dict[str, float] = {}
    for start in range(0, len(wanted), 30):
        chunk = "+".join(wanted[start:start + 30])
        for row in rows("WBS001", ver, f"TIME_PERIOD:{YEAR},TERUL_GEO4:{chunk},NEME_SEX:M+F,"
                                       f"KEV_AGE:TOTAL+{'+'.join(single)}"):
            place, sex, age = row["TERUL_GEO4"], row["NEME_SEX"], row["KEV_AGE"]
            if age == "TOTAL":
                totals[place] = totals.get(place, 0) + value(row)
                continue
            (males if sex == "M" else females).setdefault(place, Counter())[years[age]] += value(row)
    if "999" not in totals:
        wanted.remove("999")          # no rows: nobody left undistributed by age
    for place in wanted:
        made = sum(males.get(place, Counter()).values()) + sum(females.get(place, Counter()).values())
        if abs(made - totals.get(place, -1)) > 0.5:
            raise SystemExit(f"hungary: {name_of[place]}: ages make {made:,.0f}, the total "
                             f"{totals.get(place)}")
    check_sum((totals[c] for c in counties), totals["HU"], "counties and Budapest against Hungary")
    for county in counties:
        kids = [d for d in districts if parent_of[d] == county]
        if county == "HU110":
            # Budapest's figure holds people KSH could not place in a
            # district (code 999); they are nobody's district.
            rest = totals[county] - sum(totals[d] for d in kids)
            if not 0 <= rest < 0.01 * totals[county] or ("999" in totals and rest != totals["999"]):
                raise SystemExit(f"hungary: Budapest's districts leave {rest:,.0f} unplaced")
            log(f"  Budapest: its 23 districts make {totals[county] - rest:,.0f} of "
                f"{totals[county]:,.0f}; {rest:,.0f} are counted in no district")
            continue
        check_sum((totals[d] for d in kids), totals[county], f"districts against {name_of[county]}")
    both = Counter(males["HU"])
    both.update(females["HU"])
    check_national_median(both, "HU", YEAR + 1)

    # Religion, ethnicity and mother tongue.
    comp: dict[str, dict[str, float]] = {}
    places = [*districts, *counties]
    for start in range(0, len(places), 40):
        chunk = "+".join(places[start:start + 40])
        for row in rows("WBS003", ver, f"TIME_PERIOD:{YEAR},TERUL_GEO5:{chunk},TEL_SZ_ADAT"):
            comp.setdefault(row["TERUL_GEO5"], {})[row["TEL_SZ_ADAT"]] = value(row)
    fields_of: dict[str, dict[str, Any]] = {}
    for place in places:
        c = comp.get(place)
        if not c:
            raise SystemExit(f"hungary: WBS003 has nothing for {name_of[place]}")
        if abs(c["VALLAS_V1"] - totals[place]) > 0.5:
            raise SystemExit(f"hungary: {name_of[place]}: the census population is "
                             f"{c['VALLAS_V1']:,.0f} in WBS003 and {totals[place]:,.0f} in WBS001")
        fields_of[place] = composition(c, name_of[place])

    shapes = units("HUN", "admin2")
    firsts = units("HUN", "admin1")
    source_age = SOURCE.format(flow="WBS001")
    sources = [{"field": "population/median_age/sex_ratio", "name": source_age, "url": PORTAL,
                "license": LICENCE, "year": YEAR},
               {"field": "religion/ethnicity/language", "name": SOURCE.format(flow="WBS003"),
                "url": PORTAL, "license": LICENCE, "year": YEAR}]
    median_note = ("Interpolated within the single year of age that holds the middle person, "
                   "from the 2022 census's count of the {what} by sex and single year of age.")
    records, unbound, used = [], [], set()
    by_key: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_key.setdefault(fold(shape["name"]), []).append(shape)
    rebuilt = drawn_2014(ver, totals, parent_of)
    for code in districts:
        label = name_of[code]
        if parent_of[code] == "HU110":
            number = int(label.split()[-1])
            keys = [fold(f"{ROMAN[number - 1]}. kerület")]
        else:
            adjective = label.replace(" district", "").strip()
            base = IRREGULAR.get(adjective, adjective[:-1] if adjective.endswith("i") else adjective)
            keys = [fold(base), fold(adjective)]
        hits = [s for k in dict.fromkeys(keys) for s in by_key.get(k, []) if s["id"] not in used]
        if len(hits) != 1:
            unbound.append(f"{label} ({code}): {[h['name'] for h in hits]}")
            continue
        shape = hits[0]
        used.add(shape["id"])
        fields = age_sex_fields(males[code], females[code], year=YEAR, source=source_age,
                                total=totals[code], median_note=median_note.format(what="district"),
                                ratio_note="Males per 100 females counted by the 2022 census.")
        if code in rebuilt:
            records.append(drawn_record(code, rebuilt[code], shape, source_age,
                                        county=name_of[parent_of[code]], median=fields))
            continue
        fields.update(fields_of[code])
        records.append(record(
            f"HUN-KSH-{code}", shape["name"], level="admin2", parent=shape["parent"],
            parent_name=name_of[parent_of[code]], country="HUN", codes={"ksh_terul": code},
            aliases=[label], match_by="shape_id", shape_id=shape["id"], sources=sources, **fields))
    for code14, (drawn, _) in GONE_2014.items():
        shape = next(s for s in shapes if s["name"] == drawn)
        used.add(shape["id"])
        records.append(drawn_record(code14, rebuilt[code14], shape, source_age,
                                    county=name_of[parent_of[GONE_2014[code14][1]]], median=None))
    report_unbound("hungary", unbound, [s["name"] for s in shapes if s["id"] not in used])
    if unbound:
        raise SystemExit(f"hungary: {len(unbound)} districts unbound")

    first_by = {fold(u["name"]): u for u in firsts}
    for code in counties:
        if code == "HU110":
            continue
        label = name_of[code].replace(" county", "").strip()
        shape = first_by.get(fold(label))
        if shape is None:
            raise SystemExit(f"hungary: no county polygon for {label}")
        if code == "HU120":
            # The polygon is Pest county and Budapest: sum the two.
            m = Counter(males["HU120"]); m.update(males["HU110"])
            f = Counter(females["HU120"]); f.update(females["HU110"])
            merged = {k: comp["HU120"].get(k, 0) + comp["HU110"].get(k, 0)
                      for k in set(comp["HU120"]) | set(comp["HU110"])}
            fields = age_sex_fields(
                m, f, year=YEAR, source=source_age, total=totals["HU120"] + totals["HU110"],
                median_note=median_note.format(what="county and the capital together"),
                ratio_note="Males per 100 females in Pest county and Budapest together.")
            fields.update(composition(merged, "Pest and Budapest"))
            note = ("The map's Pest polygon holds Budapest as well as Pest county, so these are "
                    "the two summed.")
            for key in ("religion", "ethnicity", "language"):
                fields[f"{key}_note"] = fields[f"{key}_note"] + " " + note
            fields["median_age_note"] += " " + note
            records.append(record(
                f"HUN-KSH-{code}-BP", shape["name"], level="admin1", parent="HUN", country="HUN",
                codes={"ksh_terul": "HU120+HU110"}, match_by="shape_id", shape_id=shape["id"],
                sources=sources, **fields))
            continue
        records.append(record(
            f"HUN-KSH-{code}", shape["name"], level="admin1", parent="HUN", country="HUN",
            codes={"ksh_terul": code}, match_by="shape_id", shape_id=shape["id"],
            sources=sources[1:], **fields_of[code]))
    return records


def gazetteer_2014() -> dict[str, tuple[str, str, str]]:
    """{settlement KSH code: (name, district code, district name)} on 1 January 2014."""
    import xlrd
    book = xlrd.open_workbook(file_contents=http_get(GAZETTEER, binary=True, timeout=300))
    return read_gazetteer([book.sheet_by_index(0).row_values(i)
                           for i in range(book.sheet_by_index(0).nrows)])


def read_gazetteer(table: list[list[Any]]) -> dict[str, tuple[str, str, str]]:
    """The gazetteer's rows: two header rows, then one settlement a row.

    The first header row names a group over its columns ("Helység", "Járás"),
    the second the column inside it ("KSH kódja", "kódja", "neve"). A
    district's code is written with the seat flag after it ("085 0").
    """
    top = [str(c).strip() for c in table[0]]
    sub_ = [str(c).strip() for c in table[1]]
    group, heads = "", []
    for t, b in zip(top, sub_):
        group = t or group
        heads.append((group, b))
    try:
        col_code = heads.index(("Helység", "KSH kódja"))
        col_district = heads.index(("Járás", "kódja"))
        col_district_name = heads.index(("Járás", "neve"))
    except ValueError:
        raise SystemExit(f"hungary: the 2014 gazetteer's header is {heads[:12]}")
    out: dict[str, tuple[str, str, str]] = {}
    for row in table[2:]:
        code = str(row[col_code]).split(".")[0].strip()
        district = str(row[col_district]).strip()[:3]
        if not re.fullmatch(r"\d{4,5}", code) or not re.fullmatch(r"\d{3}", district):
            continue
        out[code.zfill(5)] = (str(row[0]).strip(), district, str(row[col_district_name]).strip())
    log(f"  2014 gazetteer: {len(out):,} settlements in {len({d for _, d, _ in out.values()})} districts")
    return out


def members_2014(old: dict[str, tuple[str, str, str]], now: dict[str, str],
                 county_of: dict[str, str]) -> dict[str, list[str]]:
    """The 2014 districts whose settlements changed, each as its 2014 settlement codes.

    ``old`` is the 2014 gazetteer, ``now`` the 2022 census's settlement ->
    district outside Budapest, ``county_of`` a district's county. A settlement
    moved between counties, or one in a changed district that the gazetteer
    does not have, stops the run: neither can be placed on the drawn map.
    """
    moved = {c: (old[c][1], p) for c, p in now.items() if c in old and old[c][1] != p}
    changed = {d for pair in moved.values() for d in pair}
    unplaced = sorted(c for c, p in now.items() if c not in old and p in changed)
    across = {c: m for c, m in moved.items()
              if county_of.get(m[0], "?") != county_of.get(m[1], "!")}
    log(f"  2022 census: {len(now):,} settlements outside Budapest; {len(moved)} in another district "
        f"than in 2014: {sorted(moved.items())}")
    if across or unplaced:
        raise SystemExit(f"hungary: settlements moved between counties since 2014: {across}; in a "
                         f"changed district but not in the 2014 gazetteer: {unplaced}")
    members: dict[str, list[str]] = {code: [] for code in sorted(changed)}
    for c in sorted(now):
        if c in old and old[c][1] in members:
            members[old[c][1]].append(c)
    empty = [code for code, group in members.items() if not group]
    if empty:
        raise SystemExit(f"hungary: no 2022 settlement of the 2014 districts {empty}")
    return members


def sum_settlements(members: list[str], cells: dict[str, dict[str, float]],
                    names: dict[str, str]) -> dict[str, float]:
    """A district's WBS003 cells, summed over its settlements, each checked."""
    summed: dict[str, float] = {}
    for c in members:
        if c not in cells:
            raise SystemExit(f"hungary: WBS003 has nothing for settlement {names.get(c)} ({c})")
        if abs(cells[c].get("M", 0) + cells[c].get("F", 0) - cells[c]["VALLAS_V1"]) > 0.5:
            raise SystemExit(f"hungary: {names.get(c)}: men and women do not make its "
                             f"{cells[c]['VALLAS_V1']:,.0f} people")
        for k, v in cells[c].items():
            summed[k] = summed.get(k, 0.0) + v
    return summed


def drawn_2014(ver: str, totals: dict[str, float],
               parent_of: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Every 2014 district whose settlements changed, summed from its 2014 settlements."""
    old = gazetteer_2014()
    geo5 = codelists("WBS003", ver)["CL_TERUL_GEO5"]
    parent = {c["id"]: c.get("parent") for c in geo5}
    budapest = {c for c, p in parent.items() if p == "HU110"}
    now = {c: p for c, p in parent.items()
           if re.fullmatch(r"\d{5}", c) and p and re.fullmatch(r"\d{3}", p) and p not in budapest}
    county_of = {d: parent_of.get(d) for d in set(now.values())}
    for gone, (_, heir) in GONE_2014.items():
        county_of[gone] = parent_of.get(heir)
    members = members_2014(old, now, county_of)
    later = {code: sorted(c for c, p in now.items() if p == code) for code in members}
    flat = sorted({c for group in [*members.values(), *later.values()] for c in group})
    cells: dict[str, dict[str, float]] = {}
    blanked: dict[str, int] = {}
    for start in range(0, len(flat), 40):
        chunk = "+".join(flat[start:start + 40])
        for row in rows("WBS003", ver, f"TIME_PERIOD:{YEAR},TERUL_GEO5:{chunk},TEL_SZ_ADAT"):
            place = row["TERUL_GEO5"]
            cells.setdefault(place, {})[row["TEL_SZ_ADAT"]] = value(row)
            if row.get("OBS_VALUE") in (None, ""):
                blanked[place] = blanked.get(place, 0) + 1
    names = {c: old[c][0] if c in old else c for c in flat}
    out: dict[str, dict[str, Any]] = {}
    for code, group in members.items():
        summed = sum_settlements(group, cells, names)
        differ = sorted(set(group) ^ set(later[code]))
        differ_people = sum(cells[c]["VALLAS_V1"] for c in differ)
        out[code] = {"cells": summed, "settlements": sorted(names[c] for c in group),
                     "codes": sorted(group), "blanked": sum(blanked.get(c, 0) for c in group),
                     "name": old[group[0]][2] or code,
                     "differ": [(names[c], cells[c]["VALLAS_V1"], c in group) for c in differ],
                     "share": differ_people / summed["VALLAS_V1"]}
        log(f"  2014 district {code} {out[code]['name']}: {len(group)} settlements, "
            f"{summed['VALLAS_V1']:,.0f} people, {out[code]['blanked']} blanked cells; differs from "
            f"2022 by {differ_people:,.0f} ({100 * out[code]['share']:.1f}%): "
            f"{[n for n, _, _ in out[code]['differ']]}")
    # The rebuilt districts hold the same people as the 2022 districts they came from.
    check_sum((u["cells"]["VALLAS_V1"] for u in out.values()),
              sum(totals[code] for code in members if code in totals),
              "the rebuilt 2014 districts against their 2022 districts")
    return out


def drawn_record(code14: str, unit: dict[str, Any], shape: dict[str, Any], source_age: str,
                 county: str, median: dict[str, Any] | None) -> dict[str, Any]:
    """The record for one district drawn as in 2013-2014, from its settlements' sums.

    ``median`` is the 2022 namesake's age fields, or None where there is none.
    """
    fields = composition(unit["cells"], shape["name"], blanked=unit["blanked"])
    moved = "; ".join(f"{n} ({p:,.0f} people, {'then here' if here else 'now here'})"
                      for n, p, here in unit["differ"])
    why = (f"The map draws the districts of 2013-2014, and this one's settlements have changed "
           f"since ({moved}). Its figures are the 2022 census's counts summed over the "
           f"{len(unit['settlements'])} settlements KSH's gazetteer of 1 January 2014 puts in the "
           f"{unit['name']} district.")
    for key in ("religion", "ethnicity", "language"):
        fields[f"{key}_note"] = fields[f"{key}_note"] + " " + why
    if median is not None and unit["share"] <= MEDIAN_TOLERANCE:
        age = {"median_age": median["median_age"],
               "median_age_note": (median["median_age_note"] + f" It is the 2022 district's, which "
                                   f"differs from the drawn one by {100 * unit['share']:.1f}% of its "
                                   f"people ({moved}); KSH publishes age by settlement in ten-year "
                                   f"groups only.")}
    else:
        age = {"median_age": gap(NOT_AVAILABLE, "Not written: " + why + " KSH publishes age by "
                                 "settlement in ten-year groups only, too coarse for a median.")}
    return record(
        f"HUN-KSH2014-{code14}", shape["name"], level="admin2", parent=shape["parent"],
        parent_name=county, country="HUN",
        codes={"ksh_jaras_2014": code14, "ksh_settlements": ",".join(unit["codes"])},
        aliases=[f"{unit['name']} district (2013)"], match_by="shape_id", shape_id=shape["id"],
        population=measure(int(round(unit["cells"]["VALLAS_V1"])), year=YEAR, source=source_age),
        population_note=why,
        sex_ratio=measure(sex_ratio(unit["cells"]["M"], unit["cells"]["F"]), unit=SEX_RATIO_UNIT,
                          year=YEAR, source=source_age),
        sex_ratio_note="Males per 100 females counted by the 2022 census, same settlements.",
        sources=[{"field": "population/sex_ratio/religion/ethnicity/language",
                  "name": SOURCE.format(flow="WBS003"), "url": PORTAL, "license": LICENCE,
                  "year": YEAR},
                 {"field": "population/sex_ratio/religion/ethnicity/language",
                  "name": GAZETTEER_SOURCE, "url": GAZETTEER, "license": LICENCE, "year": 2014}]
        + ([{"field": "median_age", "name": source_age, "url": PORTAL, "license": LICENCE,
             "year": YEAR}] if "median_age_note" in age else []),
        **age, **fields)


def composition(c: dict[str, float], name: str, blanked: int = 0) -> dict[str, Any]:
    """The three compositions of one unit from its WBS003 cells.

    KSH blanks a cell of a few people for confidentiality; such a cell reads
    as nothing, so a partition may fall a handful short. ``blanked`` is how
    many blanked cells went into a sum of settlements, each allowed its few.
    """
    total = c["VALLAS_V1"]
    partition = sum(c.get(k, 0) for k in PARTITION)
    allowed = max(10, 0.001 * total) + 3 * blanked
    if not 0 <= total - partition <= allowed:
        raise SystemExit(f"hungary: {name}: religion rows make {partition:,.0f} of {total:,.0f}")
    religion = {label: c.get(k, 0) for k, label in RELIGION.items()}
    religion["Catholic (unspecified)"] = c.get("RE_C", 0) - c.get("RE_RC", 0) - c.get("RE_GC", 0)
    if religion["Catholic (unspecified)"] < 0:
        raise SystemExit(f"hungary: {name}: Roman and Greek Catholics exceed all Catholics")
    ethnicity = {label: c.get(k, 0) for k, label in ETHNICITY.items()}
    language = {label: c.get(k, 0) for k, label in LANGUAGE.items()}
    for field, counts, total_key in (("ethnicity", ethnicity, "EG"), ("language", language, "MT")):
        if abs(c.get(total_key, 0) - total) > 0.5:
            raise SystemExit(f"hungary: {name}: {field} is asked of {c.get(total_key):,.0f}, "
                             f"not the population {total:,.0f}")
        if sum(counts.values()) < total - allowed:
            raise SystemExit(f"hungary: {name}: {field} declarations ({sum(counts.values()):,.0f}) "
                             f"are fewer than the people ({total:,.0f})")
    out: dict[str, Any] = {}
    for field, counts in (("religion", religion), ("ethnicity", ethnicity), ("language", language)):
        rows_ = shares({k: v for k, v in counts.items() if v}, total=total)
        out[field] = rows_
        out[f"{field}_year"] = dated(rows_, YEAR)
        out[f"{field}_note"] = NOTES[field]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
