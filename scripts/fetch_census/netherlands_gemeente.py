#!/usr/bin/env python3
"""The Netherlands: population, sex ratio, median age and migration background by gemeente.

CBS's "Kerncijfers wijken en buurten 2022" (KWB 2022) counts the registered
population (BRP) of every gemeente, wijk and buurt on 1 January 2022, with
men and women. CBS publishes it as a workbook on download.cbs.nl, which reset
every connection from the fetch runner, and as the attributes of its own
wijk- en buurtkaart 2022, which PDOK serves as a WFS: the same figures, read
here from the WFS. Its gemeenten are those of 1 January 2022: 345.

**Vintage.** The map draws 344 gemeenten: the 2022 division after Weesp
joined Amsterdam on 24 March 2022, and before Brielle, Hellevoetsluis and
Westvoorne became Voorne aan Zee in 2023. So Amsterdam's polygon is given
Amsterdam and Weesp summed, which is what it holds, and every other gemeente
is its own polygon. Every figure here is of 1 January 2022 for that reason:
it is the date the drawn division is the office's own.

**Median age.** From StatLine table 03759ned (population on 1 January by sex,
single year of age and region), read through CBS's OData service, which
refused the fetch runner in September 2026 and answers it now. The median is
interpolated within the single year that holds the middle person; each
gemeente's men and women by age must make the same population the key figures
give, and the country's median, recomputed, must land within 0.3 years of
Eurostat's.

**Migration background as ethnicity.** No Dutch register records ethnicity;
what CBS counts is migration background (migratieachtergrond): a person's own
country of birth, or, for those born in the Netherlands, the mother's -- the
father's where the mother was born in the Netherlands too. By the owner's
decision of 19 September 2026 it is carried on the ethnicity field under
``ethnicity_basis: "migration background (CBS)"``, from StatLine 84910NED
(population on 1 January 2010-2022 by migration background, generation, age
and region): "Dutch" is CBS's Nederlandse achtergrond (both parents born in
the Netherlands), the largest origins are named, the former Netherlands
Antilles and Aruba as the one group CBS reports them as, and every other
background is "Other migration background". CBS replaced this
classification with "herkomst" from 2022, and 1 January 2022 is its last
date -- the date of the drawn division. The gemeenten and the twelve
provinces are written.

Usage:
    python -m scripts.fetch_census.netherlands_gemeente
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from collections import Counter
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_json, log, measure, record, write_json
from .central_ages import (SEX_RATIO_UNIT, age_sex_fields, check_national_median, check_sum, fold,
                           report_unbound, sex_ratio, units)
from .central_nationality import DECISION, composition

WFS = ("https://service.pdok.nl/cbs/wijkenbuurten/2022/wfs/v1_0?request=GetFeature&service=WFS"
       "&version=2.0.0&typeNames=wijkenbuurten:gemeenten&outputFormat=application/json&count=2000"
       "&propertyName=gemeentecode,gemeentenaam,water,mannen,vrouwen,jaar")
PAGE = "https://www.cbs.nl/nl-nl/maatwerk/2023/14/kerncijfers-wijken-en-buurten-2022"
SOURCE = ("CBS, Kerncijfers wijken en buurten 2022 (population register, 1 January 2022), "
          "via the wijk- en buurtkaart 2022 on PDOK")
LICENCE = "CC BY 4.0 (CBS)"
OUT = PROCESSED / "netherlands_gemeente.json"
YEAR = 2022
NATIONAL = 17_590_672             # CBS, population of the Netherlands on 1 January 2022
EXPECTED = 345
MERGED_INTO = {"Weesp": "Amsterdam"}          # 24 March 2022, before the map's division
# CBS's spelling -> the boundary file's, where folding does not reach it.
MAP_NAMES = {"Hengelo": "Hengelo (O)", "Bergen (L.)": "Bergen (L)", "Bergen (NH.)": "Bergen (NH)"}

# --- StatLine through CBS's OData service ----------------------------------
ODATA = "https://opendata.cbs.nl/ODataApi/odata/{table}/{path}"
STATLINE = "https://opendata.cbs.nl/statline/#/CBS/nl/dataset/{table}/table"
AGE_TABLE = "03759ned"
ORIGIN_TABLE = "84910NED"
PERIOD = f"{YEAR}JJ00"
AGE_SOURCE = ("CBS StatLine 03759ned, Bevolking op 1 januari en gemiddeld; geslacht, leeftijd en "
              "regio (1 January 2022)")
ORIGIN_SOURCE = ("CBS StatLine 84910NED, Bevolking; migratieachtergrond, generatie, leeftijd, regio, "
                 "1 januari (1 January 2022)")
# Regions a request asks for at once: CBS answers at most 10,000 cells a call,
# and a region has three sexes by some 107 ages, or 61 backgrounds.
CHUNK = 40
AGE_CHUNK = 20
# A background is named when its people are at least this share of the country.
NAMED_SHARE = 0.003
# How far StatLine's counts of a gemeente may sit from the key figures' before
# they are not the same register on the same day.
AGREE = 0.0005
DUTCH = "Dutch"
OTHER_BACKGROUND = "Other migration background"
CARIBBEAN = "Dutch Caribbean"
# CBS's background titles -> the map's labels. The former Netherlands
# Antilles and Aruba are read as the one group CBS reports them as, whose
# parts (Aruba, Curacao, the Antilles before 2010) are then not named again.
BACKGROUND: dict[str, str] = {
    "Nederlandse achtergrond": DUTCH, "Turkije": "Turkish", "Marokko": "Moroccan",
    "Suriname": "Surinamese", "Indonesië": "Indonesian", "Duitsland": "German",
    "Polen": "Polish", "België": "Belgian", "Syrië": "Syrian", "Verenigd Koninkrijk": "British",
    "China": "Chinese", "India": "Indian", "Irak": "Iraqi", "Iran": "Iranian",
    "Afghanistan": "Afghan", "Somalië": "Somali", "Eritrea": "Eritrean",
    "Kaapverdië": "Cape Verdean", "Ghana": "Ghanaian", "Egypte": "Egyptian",
    "Ethiopië": "Ethiopian", "Zuid-Afrika": "South African", "Brazilië": "Brazilian",
    "Colombia": "Colombian", "Verenigde Staten van Amerika": "American", "Filippijnen": "Filipino",
    "Pakistan": "Pakistani", "Thailand": "Thai", "Vietnam": "Vietnamese",
    "Bosnië-Herzegovina": "Bosnian and Herzegovinian", "Bulgarije": "Bulgarian",
    "Frankrijk": "French", "Griekenland": "Greek", "Hongarije": "Hungarian", "Italië": "Italian",
    "Oekraïne": "Ukrainian", "Portugal": "Portuguese", "Roemenië": "Romanian", "Rusland": "Russian",
    "Spanje": "Spanish", "(voormalige) Nederlandse Antillen, Aruba": CARIBBEAN,
}
CARIBBEAN_PARTS = ("Aruba", "Curaçao", "Nederlandse Antillen (oud)")


def features(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{gemeente code: {name, total, men, women}} from the WFS's GeoJSON.

    The layer also holds "Buitenland" (GM0998), a placeholder for residents
    abroad with -99999999 in every count, and may split a gemeente into its
    land and water parts; a gemeente met twice must carry the same counts.
    """
    out: dict[str, dict[str, Any]] = {}
    for feat in payload.get("features", []):
        props = feat.get("properties") or {}
        code = str(props.get("gemeentecode") or "").strip()
        men, women = props.get("mannen"), props.get("vrouwen")
        if not code.startswith("GM") or men is None or women is None or men < 0 or women < 0:
            continue
        entry = {"name": str(props.get("gemeentenaam")).strip(), "men": float(men),
                 "women": float(women), "total": float(men) + float(women)}
        if code in out and (out[code]["men"], out[code]["women"]) != (entry["men"], entry["women"]):
            raise SystemExit(f"netherlands_gemeente: {code} appears twice with different counts")
        out[code] = entry
    return out


def read() -> tuple[dict[str, dict[str, Any]], float | None]:
    """{gemeente code: {name, total, men, women}}; the WFS has no national row."""
    payload = http_json(WFS, timeout=300)
    water = {}
    for feat in payload.get("features", []):
        key = (feat.get("properties") or {}).get("water")
        water[key] = water.get(key, 0) + 1
    log(f"  WFS: {len(payload.get('features', []))} features; water flags {water}")
    return features(payload), None


# ---------------------------------------------------------------------------
# StatLine
# ---------------------------------------------------------------------------

def odata(table: str, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Every row of one OData resource, following CBS's next links."""
    query = urllib.parse.urlencode({**(params or {}), "$format": "json"},
                                   quote_via=urllib.parse.quote, safe="$,'()")
    url = ODATA.format(table=table, path=path) + "?" + query
    rows: list[dict[str, Any]] = []
    while url:
        payload = http_json(url, timeout=300)
        rows += payload.get("value", [])
        url = payload.get("odata.nextLink")
    return rows


def topic(table: str) -> str:
    """The table's one population measure: the first Topic of its DataProperties."""
    topics = [p["Key"] for p in odata(table, "DataProperties") if p.get("Type") == "Topic"]
    if not topics:
        raise SystemExit(f"netherlands_gemeente: {table} lists no measure")
    return topics[0]


def total_key(rows: list[dict[str, Any]], what: str) -> str:
    """The key of a dimension's total, the one whose title opens with "Totaal"."""
    hits = [r["Key"].strip() for r in rows if str(r.get("Title", "")).startswith("Totaal")]
    if len(hits) != 1:
        raise SystemExit(f"netherlands_gemeente: {len(hits)} totals for {what}: {hits}")
    return hits[0]


def single_ages(rows: list[dict[str, Any]]) -> dict[str, int]:
    """{age key: the year it stands for} -- "0 jaar" ... and the open top class
    ("N jaar of ouder") only where it continues the single years. The table's
    other groups ("0 tot 20 jaar", "65 jaar of ouder") are subtotals."""
    singles, tops = {}, {}
    for r in rows:
        title = str(r.get("Title", "")).strip()
        m = re.fullmatch(r"(\d+) jaar", title)
        if m:
            singles[r["Key"].strip()] = int(m.group(1))
            continue
        m = re.fullmatch(r"(\d+) jaar of ouder", title)
        if m:
            tops[r["Key"].strip()] = int(m.group(1))
    if not singles:
        raise SystemExit("netherlands_gemeente: no single years of age in 03759ned")
    last = max(singles.values())
    top = [k for k, v in tops.items() if v == last + 1]
    if sorted(singles.values()) != list(range(last + 1)) or len(top) != 1:
        raise SystemExit(f"netherlands_gemeente: single ages 0..{last} with open tops {tops}")
    singles[top[0]] = last + 1
    return singles


def regions_filter(codes: list[str]) -> str:
    """CBS pads its region keys to six characters ("NL01  ", "PV20  "), and an
    OData filter matches the key exactly."""
    return "(" + " or ".join(f"RegioS eq '{c.ljust(6)}'" for c in codes) + ")"


def read_ages(codes: list[str], period: str = PERIOD) -> dict[str, dict[str, Any]]:
    """{region code: {"m": Counter, "f": Counter, "total": all ages, both sexes}} on the
    1 January ``period`` stands for, in the gemeenten of that date."""
    measure_key = topic(AGE_TABLE)
    sexes = odata(AGE_TABLE, "Geslacht")
    sex_total = total_key(sexes, "Geslacht")
    men = next(r["Key"].strip() for r in sexes if r["Title"].strip() == "Mannen")
    women = next(r["Key"].strip() for r in sexes if r["Title"].strip() == "Vrouwen")
    ages_rows = odata(AGE_TABLE, "Leeftijd")
    age_total = total_key(ages_rows, "Leeftijd")
    ages = single_ages(ages_rows)
    marital = total_key(odata(AGE_TABLE, "BurgerlijkeStaat"), "BurgerlijkeStaat")
    asked = "(" + " or ".join(f"Leeftijd eq '{k}'" for k in [age_total, *ages]) + ")"
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(codes), AGE_CHUNK):
        chunk = codes[start:start + AGE_CHUNK]
        flt = (f"Perioden eq '{period}' and BurgerlijkeStaat eq '{marital}' and {asked} and "
               f"{regions_filter(chunk)}")
        for row in odata(AGE_TABLE, "TypedDataSet",
                         {"$filter": flt, "$select": f"Geslacht,Leeftijd,RegioS,{measure_key}"}):
            region, sex, age = row["RegioS"].strip(), row["Geslacht"].strip(), row["Leeftijd"].strip()
            value = row.get(measure_key)
            if value is None:
                continue
            unit = out.setdefault(region, {"m": Counter(), "f": Counter(), "total": None})
            if sex == sex_total and age == age_total:
                unit["total"] = float(value)
            elif age in ages and sex == men:
                unit["m"][ages[age]] += float(value)
            elif age in ages and sex == women:
                unit["f"][ages[age]] += float(value)
    for region, unit in out.items():
        made = sum(unit["m"].values()) + sum(unit["f"].values())
        if unit["total"] is None or abs(made - unit["total"]) > 0.5:
            raise SystemExit(f"netherlands_gemeente: {region}: men and women by age make "
                             f"{made:,.0f}, the total is {unit['total']}")
    return out


def read_origins(codes: list[str]) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """({region code: {background key: people}}, {background key: CBS's title}) for every
    sex, age and generation together."""
    measure_key = topic(ORIGIN_TABLE)
    sex = total_key(odata(ORIGIN_TABLE, "Geslacht"), "Geslacht")
    age = total_key(odata(ORIGIN_TABLE, "Leeftijd"), "Leeftijd")
    generation = total_key(odata(ORIGIN_TABLE, "Generatie"), "Generatie")
    titles = {r["Key"].strip(): str(r["Title"]).strip()
              for r in odata(ORIGIN_TABLE, "Migratieachtergrond")}
    out: dict[str, dict[str, float]] = {}
    for start in range(0, len(codes), CHUNK):
        chunk = codes[start:start + CHUNK]
        flt = (f"Perioden eq '{PERIOD}' and Geslacht eq '{sex}' and Leeftijd eq '{age}' and "
               f"Generatie eq '{generation}' and {regions_filter(chunk)}")
        for row in odata(ORIGIN_TABLE, "TypedDataSet",
                         {"$filter": flt, "$select": f"Migratieachtergrond,RegioS,{measure_key}"}):
            value = row.get(measure_key)
            if value is None:
                continue
            out.setdefault(row["RegioS"].strip(), {})[row["Migratieachtergrond"].strip()] = float(value)
    return out, titles


def background_parts(titles: dict[str, str]) -> dict[str, str]:
    """The keys of the categories the composition is built from, by role:
    "total", "dutch", "migrant" (everyone with a migration background) and
    the country-level categories CBS lists, by title."""
    by_title = {t: k for k, t in titles.items()}
    need = {"total": "Totaal", "dutch": "Nederlandse achtergrond", "migrant": "Met migratieachtergrond",
            "western": "Westerse migratieachtergrond", "nonwestern": "Niet-westerse migratieachtergrond"}
    missing = [t for t in need.values() if t not in by_title]
    if missing:
        raise SystemExit(f"netherlands_gemeente: 84910NED has no {missing}")
    return {role: by_title[t] for role, t in need.items()}


def origin_composition(counts: dict[str, float], titles: dict[str, str], names: list[str],
                       where: str) -> list[dict[str, Any]]:
    """Dutch, the named backgrounds and the rest, of the region's total.

    CBS's own identities are checked first: Dutch and migration background
    make the total, and western and non-western make the migration
    background.
    """
    part = background_parts(titles)
    total, dutch, migrant = (counts.get(part[k], 0.0) for k in ("total", "dutch", "migrant"))
    if abs(dutch + migrant - total) > 0.5:
        raise SystemExit(f"netherlands_gemeente: {where}: Dutch {dutch:,.0f} and migration "
                         f"background {migrant:,.0f} do not make the total {total:,.0f}")
    if abs(counts.get(part["western"], 0) + counts.get(part["nonwestern"], 0) - migrant) > 0.5:
        raise SystemExit(f"netherlands_gemeente: {where}: western and non-western do not make "
                         f"the migration background")
    key_of = {titles[k]: k for k in counts if k in titles}
    parts = {"dutch": dutch}
    labels = {"dutch": DUTCH}
    for title in names:
        parts[title] = counts.get(key_of.get(title, ""), 0.0)
        labels[title] = BACKGROUND[title]
    parts["rest"] = migrant - sum(v for k, v in parts.items() if k != "dutch")
    labels["rest"] = OTHER_BACKGROUND
    if parts["rest"] < -0.5:
        raise SystemExit(f"netherlands_gemeente: {where}: the named backgrounds make more than "
                         f"the migration background")
    return composition(parts, total, list(parts), labels, residual=OTHER_BACKGROUND, where=where)


def named_backgrounds(national: dict[str, float], titles: dict[str, str]) -> list[str]:
    """The countries named on the map: CBS's country categories (and the
    Antilles and Aruba as one) with at least NAMED_SHARE of the country, by
    title. Aggregates of former states other than the Antilles are not
    named; their listed successors may be."""
    part = background_parts(titles)
    total = national[part["total"]]
    out, unlabelled = [], []
    for key, title in titles.items():
        if key in part.values() or key not in national:
            continue
        if title in CARIBBEAN_PARTS or title.startswith(("(voormalig", "Europa", "Europese Unie",
                                                         "GIPS", "Midden- en Oost")):
            if title != "(voormalige) Nederlandse Antillen, Aruba":
                continue
        if title in ("Afrika", "Amerika", "Azië", "Oceanië") or title.endswith("(oud)"):
            continue
        if national[key] / total >= NAMED_SHARE:
            if title not in BACKGROUND:
                unlabelled.append(f"{title} ({national[key]:,.0f})")
            else:
                out.append(title)
    if unlabelled:
        raise SystemExit(f"netherlands_gemeente: backgrounds above the naming threshold with "
                         f"no label: {unlabelled}")
    return sorted(out, key=lambda t: -national[{v: k for k, v in titles.items()}[t]])


ORIGIN_NOTE = (
    "Population by migration background on 1 January 2022 (CBS StatLine 84910NED, from the "
    "population register): MIGRATION BACKGROUND, not ethnicity, which no Dutch register "
    "records. CBS's definition until 2022: a person's own country of birth, or for someone born "
    "in the Netherlands the mother's, or the father's where the mother was born in the "
    "Netherlands too; 'Dutch' is CBS's Nederlandse achtergrond, both parents born in the "
    "Netherlands, whatever the person's nationality. 'Dutch Caribbean' is the former "
    "Netherlands Antilles and Aruba as CBS reports them; backgrounds below "
    f"{NAMED_SHARE:.1%} of the country are '{OTHER_BACKGROUND}'. CBS replaced the classification "
    "with 'herkomst' from 2022, and 1 January 2022 is also the date of the division the map "
    f"draws. Written by the map owner's decision of {DECISION}.")


def build() -> list[dict[str, Any]]:
    log("netherlands_gemeente: CBS Kerncijfers wijken en buurten 2022, 03759ned and 84910NED, "
        "by gemeente")
    gemeenten, national = read()
    log(f"  {len(gemeenten)} gemeenten; Nederland {national or 0:,.0f}")
    if len(gemeenten) != EXPECTED:
        raise SystemExit(f"netherlands_gemeente: {len(gemeenten)} gemeenten, not {EXPECTED}")
    missing = [g["name"] for g in gemeenten.values() if None in (g["total"], g["men"], g["women"])]
    if missing:
        raise SystemExit(f"netherlands_gemeente: no count for {missing}")
    check_sum((g["total"] for g in gemeenten.values()), NATIONAL, "gemeenten against the Netherlands")
    if national is not None:
        check_sum([national], NATIONAL, "the workbook's own national row")
    worst = max(abs(g["men"] + g["women"] - g["total"]) for g in gemeenten.values())
    log(f"  men + women against the total: largest difference {worst:,.0f}")
    if worst > 0:
        raise SystemExit("netherlands_gemeente: men and women do not make a gemeente's total")

    # Single years of age by sex, the same register on the same day.
    codes = sorted(gemeenten)
    ages = read_ages(codes + ["NL01"])
    worst = (0.0, "")
    for code, g in gemeenten.items():
        unit = ages.get(code)
        if unit is None:
            raise SystemExit(f"netherlands_gemeente: 03759ned has no {g['name']} ({code})")
        for got, want, who in ((sum(unit["m"].values()), g["men"], "men"),
                               (sum(unit["f"].values()), g["women"], "women")):
            # The key figures and StatLine are the same register on the same
            # day, published a year apart; a handful of later corrections
            # separates them, never more than AGREE of a gemeente.
            if abs(got - want) > max(10.0, AGREE * want):
                raise SystemExit(f"netherlands_gemeente: {g['name']}: 03759ned counts {got:,.0f} "
                                 f"{who}, the key figures {want:,.0f}")
            if abs(got - want) / max(want, 1) > worst[0]:
                worst = (abs(got - want) / max(want, 1), f"{g['name']} {who} {got:,.0f} / {want:,.0f}")
    log(f"  03759ned against the key figures, men and women: largest difference {worst[0]:.4%} "
        f"({worst[1]})")
    both = Counter(ages["NL01"]["m"])
    both.update(ages["NL01"]["f"])
    check_sum([ages["NL01"]["total"]], NATIONAL, "03759ned's national row", tolerance=AGREE)
    check_national_median(both, "NL", YEAR)

    # Migration background, gemeenten, provinces and the country.
    provinces = [u for u in units("NLD", "admin1")]
    origins, titles = read_origins(codes + [f"PV{n}" for n in range(20, 32)] + ["NL01"])
    part = background_parts(titles)
    for code, g in gemeenten.items():
        got = origins.get(code, {}).get(part["total"])
        if got is None or abs(got - g["total"]) > max(10.0, AGREE * g["total"]):
            raise SystemExit(f"netherlands_gemeente: {g['name']}: 84910NED counts {got}, the key "
                             f"figures {g['total']:,.0f}")
    names = named_backgrounds(origins["NL01"], titles)
    log(f"  named backgrounds: {', '.join(BACKGROUND[t] for t in names)}")
    check_sum((origins[f"PV{n}"][part["total"]] for n in range(20, 32)), NATIONAL,
              "provinces against the Netherlands, 84910NED", tolerance=AGREE)

    by_name = {g["name"]: code for code, g in gemeenten.items()}
    for part_name, whole in MERGED_INTO.items():
        into, other = by_name[whole], by_name[part_name]
        g = gemeenten[into]
        for key in ("total", "men", "women"):
            g[key] += gemeenten[other][key]
        g["merged"] = part_name
        ages[into]["m"].update(ages[other]["m"])
        ages[into]["f"].update(ages[other]["f"])
        ages[into]["total"] += ages[other]["total"]
        for key, value in origins[other].items():
            origins[into][key] = origins[into].get(key, 0.0) + value
        log(f"  {whole}: {part_name} added, {g['total']:,.0f}")

    shapes = units("NLD", "admin2")
    by_key: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_key.setdefault(fold(shape["name"]), []).append(shape)
    records, unbound, used = [], [], set()
    for code, g in sorted(gemeenten.items()):
        if g["name"] in MERGED_INTO:
            continue
        drawn = MAP_NAMES.get(g["name"], g["name"])
        hits = [s for s in by_key.get(fold(drawn), []) if s["id"] not in used]
        if len(hits) != 1:
            unbound.append(f"{g['name']} ({code})")
            continue
        shape = hits[0]
        used.add(shape["id"])
        merged = g.get("merged")
        what = f"{g['name']} and {merged}, which joined it on 24 March 2022," if merged else g["name"]
        age_fields = age_sex_fields(
            ages[code]["m"], ages[code]["f"], year=YEAR, source=AGE_SOURCE, total=g["total"],
            median_note=(f"Interpolated within the single year of age that holds the middle person, "
                         f"from CBS's count of the registered population of {what} on 1 January "
                         f"2022 by sex and single year of age (StatLine 03759ned)."))
        records.append(record(
            f"NLD-KWB2022-{code}", g["name"], level="admin2", parent=shape["parent"], country="NLD",
            codes={"cbs_gemeente": code}, aliases=[shape["name"]] if shape["name"] != g["name"] else [],
            match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population/sex_ratio", "name": SOURCE, "url": PAGE,
                      "license": LICENCE, "year": YEAR},
                     {"field": "median_age", "name": AGE_SOURCE,
                      "url": STATLINE.format(table=AGE_TABLE), "license": LICENCE, "year": YEAR},
                     {"field": "ethnicity", "name": ORIGIN_SOURCE,
                      "url": STATLINE.format(table=ORIGIN_TABLE), "license": LICENCE, "year": YEAR}],
            population=measure(int(g["total"]), year=YEAR, source=SOURCE),
            sex_ratio=measure(sex_ratio(g["men"], g["women"]), unit=SEX_RATIO_UNIT, year=YEAR,
                              source=SOURCE),
            sex_ratio_note=(f"Males per 100 females registered in {what} on 1 January 2022 "
                            f"(CBS key figures by gemeente)."),
            median_age=age_fields["median_age"], median_age_note=age_fields["median_age_note"],
            ethnicity=origin_composition(origins[code], titles, names, g["name"]),
            ethnicity_year=YEAR, ethnicity_basis="migration background (CBS)",
            ethnicity_note=ORIGIN_NOTE + (f" {what.replace(',', '')} summed." if merged else "")))
    left = [s["name"] for s in shapes if s["id"] not in used]
    report_unbound("netherlands_gemeente", unbound, left)
    if unbound or left:
        raise SystemExit(f"netherlands_gemeente: {len(unbound)} gemeenten and {len(left)} polygons "
                         f"unpaired")

    # The twelve provinces, by name.
    region_titles = {r["Key"].strip(): str(r["Title"]).strip()
                     for r in odata(ORIGIN_TABLE, "RegioS", {"$filter": "startswith(Key,'PV')"})}
    by_province = {fold(u["name"]): u for u in provinces}
    for n in range(20, 32):
        code = f"PV{n}"
        name = re.sub(r"\s*\(PV\)\s*$", "", region_titles.get(code, ""))
        shape = by_province.get(fold(name))
        if shape is None:
            raise SystemExit(f"netherlands_gemeente: no province polygon for {code} {name!r}")
        records.append(record(
            f"NLD-PV-{code}", shape["name"], level="admin1", parent="NLD", country="NLD",
            codes={"cbs_provincie": code}, match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "ethnicity", "name": ORIGIN_SOURCE,
                      "url": STATLINE.format(table=ORIGIN_TABLE), "license": LICENCE, "year": YEAR}],
            ethnicity=origin_composition(origins[code], titles, names, name),
            ethnicity_year=YEAR, ethnicity_basis="migration background (CBS)",
            ethnicity_note=ORIGIN_NOTE))
    return records


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
