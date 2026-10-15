#!/usr/bin/env python3
"""Ghana -- the 2021 Population and Housing Census, by district and region.

The Ghana Statistical Service publishes the census's tables in its StatsBank,
a PxWeb service. One table counts the population by district, region, type of
locality, single year of age, sex and education; two more count it by
religious affiliation and by major ethnic group, over the same areas. Each is
asked for the cells this map shows -- every area by sex, every area by single
year of age, every area by religion, every area by ethnic group -- with every
other variable held at its total.

Written for each district the map draws and for its 16 regions: population and
sex ratio (males per 100 females) from the counts by sex, the median age from
the counts by single year of age, and religion and ethnicity as shares of
their own counts. The census's "Christian" is a subtotal of four groups
(Protestant, Catholic, Pentecostal/Charismatic, Other Christian), which are
shown instead of it. Fewer people are counted by ethnic group than live in
most districts, so the ethnic shares are of the people counted by ethnic
group, and each unit's note gives both numbers.

**The districts.** The census counts 261 districts; the boundary file draws
260, drawn before Guan district was made in 2019 out of the Santrokofi,
Akpafu, Likpe and Lolobi area of Hohoe Municipal and put in Oti Region. Hohoe
Municipal's polygon still holds that area -- Likpe-Mate, Bala and Lolobi
Kumasi lie inside it, and inside Volta Region's polygon -- so it gets Hohoe's
and Guan's counts added together (``POOLS``) and says so. A region's polygon
gets the census's own row for the region when the districts drawn in it are
exactly the region's districts, which is every region but two; Volta's and
Oti's polygons get the sum of the districts drawn in them, Guan counted with
Volta, and say so. The sub-metropolitan areas some metropolitan districts are
also counted by (STMA-Takoradi and the like) are not drawn, and are only
checked against their district.

Names are matched within each region on a reduction that drops "Municipal",
"Metropolitan", "Area", "District" and anything in brackets; ``ALIASES``
holds the spellings that differ otherwise (Akwapim and Akwapem, Bosomtwi and
Bosomtwe, the census's "Cape Cape Metropolitan Area").

**Checks before anything is written.** For every area: men and women make the
total, and the single years of age make it too; the religions make their
total, which is the population, and the four Christian groups make
"Christian"; the ethnic groups make their total, which is no more than the
population. Each region's districts make the region, the regions make Ghana,
and Ghana is 30,832,019. Every polygon is bound to one census district (Hohoe
to two), and every census district to one polygon.

Usage:
    python -m scripts.fetch_census.ghana_census
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from collections import Counter
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .pxweb import http_json, unstack
from .redatam import median_age

BASE = "https://statsbank.statsghana.gov.gh/api/v1/en/PHC%202021%20StatsBank/Population/"
TABLES = {"population": BASE + "population_table.px", "religion": BASE + "religion_table.px",
          "ethnicity": BASE + "ethnic_table.px"}
TITLES = {
    "population": "Population by District, Region, Type of Locality, Single Age, Sex, and Education",
    "religion": ("Population by Religious Affiliation, District, Region, Type of Locality, Age, "
                 "Sex, and Education"),
    "ethnicity": ("Population by Major Ethnic Group, District, Region, Type of Locality, Age, Sex, "
                  "and Education"),
}
SOURCE = "Ghana Statistical Service, 2021 Population and Housing Census, StatsBank: {title}"
LICENCE = "Ghana Statistical Service (reuse with attribution)"
YEAR = 2021
NATIONAL = 30_832_019
OUT = "ghana_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
CHUNK = 40                           # areas per single-age query

REGIONS = ("Western", "Central", "Greater Accra", "Volta", "Eastern", "Ashanti", "Western North",
           "Ahafo", "Bono", "Bono East", "Oti", "Northern", "Savannah", "North East", "Upper East",
           "Upper West")
# The boundary file's reduced name -> the census's, within the same region.
ALIASES = {
    "adansiakrofuom": "akrofuom", "adenta": "adentan", "agotimeziope": "agortimeziope",
    "akwapemnorth": "akwapimnorth", "akwapemsouth": "akwapimsouth", "akyemmansa": "akyemansa",
    "aseneakrosomanso": "asenemansoakroso", "bolgaeast": "bolgatangaeast",
    "bosomtwe": "bosomtwi", "capecoast": "capecape", "denkyembour": "denkyembuor",
    "dormaa": "dormaacentral", "kasenanankanaeast": "kasenanankana",
    "lowermanya": "lowermanyakrobo", "mfantseman": "mfantsiman", "okaikweinorth": "okaikoinorth",
    "sagnerigu": "sagnarigu", "sekyereaframplainsnorth": "sekyereaframplains",
    "twifoattimorkwa": "twifoatimorkwa", "twifohemanglowerdenkyira": "twifohemanlowerdenkyira",
    "uppermanya": "uppermanyakrobo",
}
# (region, census district) drawn inside another district's polygon -> that
# district: Guan, made in 2019 from Hohoe Municipal's SALL area.
POOLS = {("Oti", "guan"): ("Volta", "hohoe")}
SALL = ("Guan district was made in 2019 out of the Santrokofi, Akpafu, Likpe and Lolobi area of "
        "Hohoe Municipal and put in Oti Region; the boundary file still draws that area inside "
        "Hohoe Municipal, in Volta Region.")
POOL_WHY = {("Volta", "hohoe"): SALL + " So the two districts' counts are shown here together."}
# The census's religion rows -> the bars shown; "Christian" is their subtotal.
RELIGION = {
    "Protestant (Anglican, Lutheran, Presbyterian, Methodist, etc.)": "Protestant",
    "Catholic": "Catholic", "Pentecostal/Charismatic": "Pentecostal/Charismatic",
    "Other Christian": "Other Christian", "Islam": "Islam", "Traditionalist": "Traditionalist",
    "No Religion": "No religion", "Other Religion": "Other religion",
}
CHRISTIAN = ("Protestant", "Catholic", "Pentecostal/Charismatic", "Other Christian")
ETHNICITY = {"Akan": "Akan", "Ga-Dangme": "Ga-Dangme", "Ewe": "Ewe", "Guan": "Guan",
             "Gurma": "Gurma", "Mole-Dagbani": "Mole-Dagbani", "Grusi": "Grusi", "Mande": "Mande",
             "Others": "Other"}
SUBMETRO = re.compile(r"^[A-Z]{2,5}-")
DROP = re.compile(r"\b(?:municipal|metropolitan|metropolis|area|district|assembly)\b")


def key(name: str) -> str:
    """A name reduced to its letters, without the kind of assembly or brackets."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = DROP.sub(" ", s)
    return "".join(c for c in s if "a" <= c <= "z")


def clean(text: str) -> str:
    return " ".join(str(text).replace("/ ", "/").split())


def ask(url: str, payload: dict | None = None) -> Any:
    """GET (metadata) or POST (a query), asked again after a pause if it fails."""
    for wait in (5, 20, 60, None):
        try:
            return http_json(url, payload)
        except Exception as exc:                    # noqa: BLE001 -- network, 5xx, rate limit
            if wait is None:
                raise
            log(f"    {url}: {exc.__class__.__name__} ({exc}); again in {wait} s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def variable(meta: dict[str, Any], code: str) -> dict[str, str]:
    """{value text: value code} of one variable of a table."""
    for var in meta.get("variables", []):
        if var.get("code") == code:
            return {clean(t): v for v, t in zip(var["values"], var["valueTexts"])}
    raise SystemExit(f"ghana_census: no variable {code!r}: "
                     f"{[v.get('code') for v in meta.get('variables', [])]}")


def pick(values: dict[str, str], text: str, what: str) -> str:
    if text not in values:
        raise SystemExit(f"ghana_census: {what} has no value {text!r}: {list(values)[:30]}")
    return values[text]


def areas(texts: list[str]) -> list[dict[str, Any]]:
    """The Geographic_Area values in order, each with its kind, its region
    and, for a sub-metropolitan area, the district it is part of."""
    out: list[dict[str, Any]] = []
    region = district = None
    for text in texts:
        if text == "Ghana":
            out.append({"name": text, "kind": "country"})
        elif text in REGIONS:
            region = text
            out.append({"name": text, "kind": "region"})
        elif region is None:
            raise SystemExit(f"ghana_census: {text!r} comes before any region")
        elif SUBMETRO.match(text):
            if district is None:
                raise SystemExit(f"ghana_census: {text!r} follows no district")
            out.append({"name": text, "kind": "submetro", "region": region, "district": district})
        else:
            district = text
            out.append({"name": text, "kind": "district", "region": region, "key": key(text)})
    return out


def query(url: str, pins: dict[str, list[str]]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    payload = {"query": [{"code": code, "selection": {"filter": "item", "values": values}}
                         for code, values in pins.items()],
               "response": {"format": "json-stat2"}}
    return unstack(ask(url, payload))


def by_area(cells: list[tuple[dict[str, tuple[str, str]], float]], var: str
            ) -> dict[str, dict[str, float]]:
    """{area text: {value text of var: count}}."""
    out: dict[str, dict[str, float]] = {}
    for dims, value in cells:
        area = clean(dims["Geographic_Area"][1])
        out.setdefault(area, {})[clean(dims[var][1])] = value
    return out


def read() -> dict[str, Any]:
    """Every area's counts by sex, single year of age, religion and ethnic group."""
    meta = {name: ask(url) for name, url in TABLES.items()}
    texts = list(variable(meta["population"], "Geographic_Area"))
    table = {"areas": areas(texts)}
    codes = variable(meta["population"], "Geographic_Area")
    ages = variable(meta["population"], "Age")
    singles = [t for t in ages if re.fullmatch(r"\d+\+?", t)]
    sexes = variable(meta["population"], "Sex")
    base = {"Locality": [pick(variable(meta["population"], "Locality"), "All Locality Types",
                              "Locality")],
            "Education": [pick(variable(meta["population"], "Education"), "Total", "Education")]}
    everyone = [codes[t] for t in texts]
    cells = query(TABLES["population"], {
        "Geographic_Area": everyone, "Sex": [sexes[s] for s in ("Both sexes", "Male", "Female")],
        "Age": [pick(ages, "All ages", "Age")], **base})
    table["sex"] = by_area(cells, "Sex")
    table["age"] = {}
    for i in range(0, len(everyone), CHUNK):
        cells = query(TABLES["population"], {
            "Geographic_Area": everyone[i:i + CHUNK], "Sex": [pick(sexes, "Both sexes", "Sex")],
            "Age": [ages[t] for t in singles], **base})
        table["age"].update(by_area(cells, "Age"))
        time.sleep(1)
    for name, var in (("religion", "Religious_Affiliation"), ("ethnicity", "Ethnicity")):
        m = meta[name]
        groups = variable(m, var)
        where = variable(m, "Geographic_Area")
        cells = query(TABLES[name], {
            "Geographic_Area": [pick(where, t, f"the {name} table's areas") for t in texts],
            var: list(groups.values()),
            "Sex": [pick(variable(m, "Sex"), "Both sexes", "Sex")],
            "Age": [pick(variable(m, "Age"), "All ages", "Age")],
            "Locality": [pick(variable(m, "Locality"), "All Locality Types", "Locality")],
            "Education": [pick(variable(m, "Education"), "Total", "Education")]})
        table[name] = by_area(cells, var)
    return table


def counts(table: dict[str, Any], area: str) -> dict[str, Any]:
    """One area's counts: total, men, women, single ages, religion, ethnicity."""
    sex = table["sex"].get(area)
    if not sex:
        raise SystemExit(f"ghana_census: no counts by sex for {area!r}")
    ages = Counter()
    for label, n in table["age"].get(area, {}).items():
        ages[int(label.rstrip("+"))] += n
    religion = {RELIGION[k]: v for k, v in table["religion"].get(area, {}).items() if k in RELIGION}
    ethnicity = {ETHNICITY[k]: v for k, v in table["ethnicity"].get(area, {}).items()
                 if k in ETHNICITY}
    return {"total": sex.get("Both sexes"), "men": sex.get("Male"), "women": sex.get("Female"),
            "ages": ages, "religion": religion,
            "religion_total": table["religion"].get(area, {}).get("Total"),
            "christian": table["religion"].get(area, {}).get("Christian"),
            "ethnicity": ethnicity,
            "ethnicity_total": table["ethnicity"].get(area, {}).get("Total")}


def check_area(area: str, c: dict[str, Any]) -> None:
    def same(a: float | None, b: float | None, what: str) -> None:
        if a is None or b is None or round(a) != round(b):
            raise SystemExit(f"ghana_census: {area}: {what}: {a} against {b}")
    same(c["men"] + c["women"], c["total"], "men and women against the total")
    same(sum(c["ages"].values()), c["total"], "the single years of age against the total")
    same(sum(c["religion"].values()), c["religion_total"], "the religions against their total")
    same(c["religion_total"], c["total"], "the religion table's total against the population")
    same(sum(c["religion"][k] for k in CHRISTIAN), c["christian"],
         "the four Christian groups against Christian")
    same(sum(c["ethnicity"].values()), c["ethnicity_total"], "the ethnic groups against their total")
    if c["ethnicity_total"] > c["total"]:
        raise SystemExit(f"ghana_census: {area}: more people counted by ethnic group "
                         f"({c['ethnicity_total']:,.0f}) than live there ({c['total']:,.0f})")


def add(parts: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"total": 0.0, "men": 0.0, "women": 0.0, "ages": Counter(),
                           "religion": Counter(), "ethnicity": Counter(), "religion_total": 0.0,
                           "christian": 0.0, "ethnicity_total": 0.0}
    for c in parts:
        for k in ("total", "men", "women", "religion_total", "christian", "ethnicity_total"):
            out[k] += c[k]
        out["ages"].update(c["ages"])
        out["religion"].update(c["religion"])
        out["ethnicity"].update(c["ethnicity"])
    out["religion"], out["ethnicity"] = dict(out["religion"]), dict(out["ethnicity"])
    return out


def check(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every area's counts, checked; {area: counts}."""
    got: dict[str, dict[str, Any]] = {}
    for a in table["areas"]:
        got[a["name"]] = counts(table, a["name"])
        check_area(a["name"], got[a["name"]])
    if round(got["Ghana"]["total"]) != NATIONAL:
        raise SystemExit(f"ghana_census: Ghana is {got['Ghana']['total']:,.0f}, not {NATIONAL:,}")
    regions = [a["name"] for a in table["areas"] if a["kind"] == "region"]
    if sorted(regions) != sorted(REGIONS):
        raise SystemExit(f"ghana_census: the regions are {regions}")
    for k in ("total", "men", "women"):
        if round(sum(got[r][k] for r in regions)) != round(got["Ghana"][k]):
            raise SystemExit(f"ghana_census: the regions do not make Ghana's {k}")
        for r in regions:
            made = sum(got[a["name"]][k] for a in table["areas"]
                       if a["kind"] == "district" and a["region"] == r)
            if round(made) != round(got[r][k]):
                raise SystemExit(f"ghana_census: {r}'s districts make {made:,.0f} {k}, "
                                 f"not {got[r][k]:,.0f}")
    metros: dict[str, float] = {}
    for a in table["areas"]:
        if a["kind"] == "submetro":
            metros[a["district"]] = metros.get(a["district"], 0.0) + got[a["name"]]["total"]
    for district, made in metros.items():
        say = "make" if round(made) == round(got[district]["total"]) else "do NOT make"
        log(f"  {district}'s sub-metropolitan areas {say} it: {made:,.0f} against "
            f"{got[district]['total']:,.0f}")
    return got


def bind(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
         ) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    """({district polygon id: [(region, census district name), ...]},
    {region polygon id: region name})."""
    region_of = {}
    for shape in admin1:
        name = re.sub(r"\s+Region$", "", shape["name"])
        if name not in REGIONS:
            raise SystemExit(f"ghana_census: region polygon {shape['name']!r} is no census region")
        region_of[shape["id"]] = name
    if sorted(region_of.values()) != sorted(REGIONS):
        raise SystemExit(f"ghana_census: region polygons {sorted(region_of.values())}")
    census: dict[tuple[str, str], str] = {}
    for a in table["areas"]:
        if a["kind"] == "district":
            if (a["region"], a["key"]) in census:
                raise SystemExit(f"ghana_census: two districts of {a['region']} read {a['key']!r}")
            census[(a["region"], a["key"])] = a["name"]
    bound: dict[str, list[tuple[str, str]]] = {}
    used: set[tuple[str, str]] = set()
    left = []
    for shape in admin2:
        region = region_of.get(shape["parent"])
        k = key(shape["name"])
        k = ALIASES.get(k, k)
        if (region, k) not in census or (region, k) in used:
            left.append(f"{shape['name']!r} ({region}, {k})")
            continue
        used.add((region, k))
        bound[shape["id"]] = [(region, census[(region, k)])]
    if left:
        raise SystemExit(f"ghana_census: polygons with no census district: {left}")
    for (region, k), (to_region, to_key) in POOLS.items():
        target = next((sid for sid, parts in bound.items()
                       if parts[0] == (to_region, census.get((to_region, to_key)))), None)
        if (region, k) not in census or target is None:
            raise SystemExit(f"ghana_census: cannot pool {region} {k} into {to_region} {to_key}")
        bound[target].append((region, census[(region, k)]))
        used.add((region, k))
    unused = sorted(f"{r}: {n}" for (r, k), n in census.items() if (r, k) not in used)
    if unused:
        raise SystemExit(f"ghana_census: census districts on no polygon: {unused}")
    return bound, region_of


def joined(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def fields(c: dict[str, Any], note: str) -> dict[str, Any]:
    src = {k: SOURCE.format(title=t) for k, t in TITLES.items()}
    median = median_age(c["ages"])
    ethnic_note = (f"Major ethnic group as the 2021 census counts it. These shares are of the "
                   f"{c['ethnicity_total']:,.0f} people the census counts by ethnic group here, "
                   f"of {c['total']:,.0f} residents.")
    return {
        "population": measure(round(c["total"]), year=YEAR, source=src["population"]),
        "population_note": note,
        "sex_ratio": measure(round(100 * c["men"] / c["women"], 1), unit="males_per_100_females",
                             year=YEAR, source=src["population"]),
        "median_age": measure(median, unit="years", year=YEAR, source=src["population"]),
        "religion": shares(c["religion"], total=c["religion_total"]),
        "religion_year": YEAR,
        "religion_note": ("Religious affiliation as the 2021 census counts it, of every resident. "
                          "The census's 'Christian' is shown as its four groups: Protestant, "
                          "Catholic, Pentecostal/Charismatic and Other Christian."),
        "ethnicity": shares(c["ethnicity"], total=c["ethnicity_total"]),
        "ethnicity_year": YEAR,
        "ethnicity_note": ethnic_note,
        "sources": [{"field": f, "name": src[t], "url": TABLES[t], "license": LICENCE,
                     "year": YEAR}
                    for f, t in (("population/sex_ratio/median_age", "population"),
                                 ("religion", "religion"), ("ethnicity", "ethnicity"))],
    }


def build(table: dict[str, Any], got: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bound, region_of = bind(table, admin1, admin2)
    records: list[dict[str, Any]] = []
    drawn: dict[str, list[tuple[str, str]]] = {}
    drawn_in: dict[str, str] = {}
    for shape in admin2:
        parts = bound[shape["id"]]
        drawn.setdefault(shape["parent"], []).extend(parts)
        for _, n in parts[1:]:
            drawn_in[n] = f"{shape['name']}, in {region_of[shape['parent']]} Region"
        c = add([got[name] for _, name in parts])
        if len(parts) == 1:
            name = parts[0][1]
            note = f"The 2021 census's count for {name}."
        else:
            why = POOL_WHY[(parts[0][0], key(parts[0][1]))]
            note = (f"{why} The 2021 census counts "
                    + joined([f"{n} {got[n]['total']:,.0f}" for _, n in parts]) + ".")
        records.append(record(
            f"GHA-2021-{key(parts[0][0])}-{key(parts[0][1])}", shape["name"], level="admin2",
            parent="GHA", country="GHA", match_by="shape_id", shape_id=shape["id"],
            **fields(c, note)))
    for shape in admin1:
        region = region_of[shape["id"]]
        here = drawn.get(shape["id"], [])
        own = sorted(a["name"] for a in table["areas"]
                     if a["kind"] == "district" and a["region"] == region)
        if sorted(n for _, n in here) == own:
            c = got[region]
            note = f"The 2021 census's count for {region} Region."
        else:
            c = add([got[n] for _, n in here])
            extra = sorted(n for r, n in here if r != region)
            missing = sorted(set(own) - {n for _, n in here})
            if missing:
                what = f"{region} Region's districts other than {joined(missing)}"
            else:
                what = f"{region} Region's {len(own)} districts"
            if extra:
                where = sorted({r for r, n in here if r != region})
                what += f" and {joined(extra)}, which the census counts in {joined(where)} Region"
            note = (f"The 2021 census's counts for {what}, added up. The census counts {region} "
                    f"Region at {got[region]['total']:,.0f}. {SALL}")
            report = [n for n in missing if n not in drawn_in]
            if report:
                raise SystemExit(f"ghana_census: {region}'s districts {report} are drawn nowhere")
        records.append(record(
            f"GHA-2021-region-{key(region)}", shape["name"], level="admin1", parent="GHA",
            country="GHA", match_by="shape_id", shape_id=shape["id"], **fields(c, note)))
    return records


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    table = read()
    got = check(table)
    kinds = Counter(a["kind"] for a in table["areas"])
    log(f"  {kinds['region']} regions, {kinds['district']} districts and {kinds['submetro']} "
        f"sub-metropolitan areas, making {got['Ghana']['total']:,.0f}")
    admin1 = json.loads((SITE / "admin1" / "GHA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GHA.units.json").read_text())
    records = build(table, got, admin1, admin2)
    for r in records:
        if r["name"] in ("Sagnerigu", "Kpandai", "Kumbungu", "Hohoe Municipal", "Volta Region",
                         "Oti Region", "Northern Region"):
            log(f"  {r['name']}: {r['population']['value']:,} people, {r['sex_ratio']['value']} "
                f"men per 100 women, median {r['median_age']['value']}; {r['population_note']}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin2')} of {len(admin2)} districts and "
        f"{sum(1 for r in records if r['level'] == 'admin1')} of {len(admin1)} regions written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
