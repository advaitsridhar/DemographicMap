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

from ._shared import NOT_AVAILABLE, PROCESSED, dated, gap, http_json, log, record, shares, write_json
from .central_ages import age_sex_fields, check_national_median, check_sum, fold, report_unbound, units

API = "https://nepszamlalas2022.ksh.hu/api"
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
# The map draws one district KSH's 2022 count does not have: "Polgard" (Wikidata
# Q15275788, its population dated 2012), a district of the 2013 division
# whose settlements KSH now counts in the Enying and Szekesfehervar districts,
# the two polygons beside it. So neither of those districts' figures fits its
# drawn polygon, and none fits Polgard's; the three are written as gaps.
REDRAWN = {"Enyingi": "Enying", "Székesfehérvári": "Székesfehérvár"}
OLD_DISTRICT = "Polgard"
GAP_FIELDS = ("median_age", "sex_ratio", "religion", "ethnicity", "language")
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
    check_national_median(both, "HU", YEAR + 1, tolerance=0.5)

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
    redrawn_note = ("Not written: the map draws Fejér's districts as they were in 2013, with a "
                    "Polgárd district between Enying and Székesfehérvár; KSH's 2022 census counts "
                    "that district's settlements in its Enying and Székesfehérvár districts, so no "
                    "published figure covers exactly this polygon.")
    for code in districts:
        label = name_of[code]
        if label.replace(" district", "").strip() in REDRAWN:
            shape = next(s for s in shapes
                         if s["name"] == REDRAWN[label.replace(" district", "").strip()])
            used.add(shape["id"])
            records.append(record(
                f"HUN-KSH-{code}", shape["name"], level="admin2", parent=shape["parent"],
                country="HUN", codes={"ksh_terul": code}, match_by="shape_id", shape_id=shape["id"],
                **{f: gap(NOT_AVAILABLE, redrawn_note) for f in GAP_FIELDS}))
            continue
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
        fields.update(fields_of[code])
        records.append(record(
            f"HUN-KSH-{code}", shape["name"], level="admin2", parent=shape["parent"],
            parent_name=name_of[parent_of[code]], country="HUN", codes={"ksh_terul": code},
            aliases=[label], match_by="shape_id", shape_id=shape["id"], sources=sources, **fields))
    old = next(s for s in shapes if s["name"] == OLD_DISTRICT)
    used.add(old["id"])
    records.append(record(
        "HUN-2013-Polgard", old["name"], level="admin2", parent=old["parent"], country="HUN",
        match_by="shape_id", shape_id=old["id"],
        **{f: gap(NOT_AVAILABLE, redrawn_note) for f in GAP_FIELDS}))
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


def composition(c: dict[str, float], name: str) -> dict[str, Any]:
    total = c["VALLAS_V1"]
    partition = sum(c.get(k, 0) for k in PARTITION)
    # KSH blanks a cell of a few people for confidentiality; such a cell reads
    # as nothing here, so a partition may fall a handful short and no more.
    if not 0 <= total - partition <= max(10, 0.001 * total):
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
        if sum(counts.values()) < total - max(10, 0.001 * total):
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
