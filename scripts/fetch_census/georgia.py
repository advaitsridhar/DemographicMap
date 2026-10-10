#!/usr/bin/env python3
"""Georgia from Geostat's own PC-Axis database: the 2014 census and today's count.

Geostat (the National Statistics Office of Georgia) serves its tables through
PX-Web at pc-axis.geostat.ge. This reads:

* **Population, both levels** -- "Population as of 1 January by regions and
  self-governed units" (Demography/Population, table 01), the office's own
  estimate for the latest 1 January. It covers the territory under the
  government's control: Abkhazia and the Tskhinvali region are not in it.
* **Median age and sex ratio, first level** -- the 2014 census's population by
  region, five-year age group and sex (census table 07). Geostat publishes
  single years of age for the country only, so the median is interpolated
  within the five-year group holding the middle person.
* **Sex ratio, second level** -- the 2014 census's population by self-governed
  unit and sex (census table 02).
* **Median age, second level** -- the 2014 census's population by
  self-governed unit and five-year age group, to 85 and over. Geostat's
  PC-Axis database and Main Results stop at three broad groups for a
  municipality; OCHA's Common Operational Dataset for Georgia (cod-ps-geo)
  relays Geostat's own five-year table (geo_admpop_adm2_geostat_2014). Every
  unit's count there must be the census table 02's, unit by unit, or the run
  stops; Tbilisi's ten districts together must give the median its region's
  row gives.
* **Ethnicity, religion and native language, first level** -- the 2014
  census's tables 17, 22 and 20 by region. Geostat's database stops at the
  region for all three.

**Units.** The census and the estimate count the self-governing cities --
Batumi, Kutaisi, Poti and Rustavi, and in 2014 also the seven towns merged back
into their municipalities in 2017 (Ozurgeti, Telavi, Mtskheta, Ambrolauri,
Zugdidi, Akhaltsikhe, Gori) -- apart from the municipality around them. The map
draws a polygon for Tbilisi and none for the other four cities, so each one is
drawn inside some municipality's polygon: the polygon that holds the city's
centre (GeoNames), when no other polygon comes within 1.5 km of that centre.
Otherwise the boundary file's outline cannot say which polygon holds the city,
and every polygon that close is left without a figure, with the reason. A town
merged in 2017 goes with its own municipality: the polygon is the municipality
as it has been since.

Abkhazia and the Tskhinvali region (the map's Java and Akhalgori) were not
enumerated in 2014 and are not in the office's estimate; they are written as
gaps saying so.

Usage:
    python -m scripts.fetch_census.georgia
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.parse
from collections import Counter, defaultdict
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from . import cod_ps, cod_ps_age, east_geo
from .cod_ps_age import grouped_median
from .east_checks import check_median
from .pxweb import TIMEOUT


def http_json(url: str, payload: dict | None = None) -> Any:
    """GET, or POST a PX-Web query; Geostat's answers to a POST open with a BOM."""
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8-sig", "replace"))

SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "georgia.json"
BASE = "https://pc-axis.geostat.ge/PXweb/api/v1/en/Database/"
CENSUS = "Population Census 2014/"
SOCIAL = CENSUS + "Demographic And Social Characteristics/"
GEOGRAPHY = CENSUS + "The Geographical Distribution Of The Population And Internal Migration/"
T_POP = "Demography/Population/01-population-by-self-governed-unit.px"
T_AGE = SOCIAL + "07.px"
T_SEX2 = GEOGRAPHY + "02TOTA~1.PX"
T_COMP = {
    "ethnicity": SOCIAL + "17_Total population by regions and ethnicity.px",
    "religion": SOCIAL + "22_Population by regions and religion.px",
    "language": SOCIAL + "20_Population_by_region,_by_native_languages_and_fluently_speak_Georgian....px",
}
CENSUS_YEAR = 2014
SOURCE = "National Statistics Office of Georgia (Geostat), PC-Axis database: {table}"
LICENCE = "Geostat, open publication"
PAGE = "https://pc-axis.geostat.ge/PXweb/pxweb/en/Database/"

# The census's region -> the map's first-level unit.
REGION = {
    "C. Tbilisi": "Tbilisi", "Autonomous Republic of Adjara": "Adjara",
    "Guria": "Guria", "Imereti": "Imereti", "Kakheti": "Kakheti",
    "Mtskheta-Mtianeti": "Mtskheta-Mtianeti",
    "Racha-Lechkhumi and Kvemo Svaneti": "Racha-Lechkhumi and Kvemo Svaneti",
    "Samegrelo-Zemo Svaneti": "Samegrelo-Zemo Svaneti",
    "Samtskhe-Javakheti": "Samtskhe–Javakheti", "Kvemo Kartli": "Kvemo Kartli",
    "Shida Kartli": "Shida Kartli",
}
# The estimate's region rows -> the census's region names.
ESTIMATE_REGION = {
    "C. Tbilisi Municipality": "C. Tbilisi", "Adjara A.R.": "Autonomous Republic of Adjara",
    "Guria Region": "Guria", "Imereti Region": "Imereti", "Kakheti Region": "Kakheti",
    "Mtskheta-Mtianeti Region": "Mtskheta-Mtianeti",
    "Racha-Lechkhumi and Kvemo Svaneti Region": "Racha-Lechkhumi and Kvemo Svaneti",
    "Samegrelo-Zemo Svaneti Region": "Samegrelo-Zemo Svaneti",
    "Samtskhe-Javakheti Region": "Samtskhe-Javakheti", "Kvemo Kartli Region": "Kvemo Kartli",
    "Shida Kartli Region": "Shida Kartli",
}
# Geostat's spelling of a municipality -> the boundary file's, where they differ.
SPELLING = {"tqibuli": "tkibuli", "dedoplistsqaro": "dedoplistskaro", "sighnagi": "sighnaghi",
            "kvareli": "qvareli", "tetritsqaro": "tetrisqaro", "axaltsikhe": "akhaltsikhe"}
# The four self-governing cities the map draws no polygon for, with their
# approximate centres (GeoNames).
CITIES = {"batumi": "Batumi", "kutaisi": "Kutaisi", "poti": "Poti", "rustavi": "Rustavi"}
CITY_MARGIN_KM = 1.5
UNCOUNTED = {"Abkhazia", "Gagra", "Gali", "Gudauta", "Gulripshi", "Ochamchire", "Sokhumi",
             "Java", "Akhalgori"}
UNCOUNTED_NOTE = ("Not enumerated: the 2014 census and Geostat's population estimates cover "
                  "the territory under the government's control, and this unit lies in "
                  "{what}, occupied since 1992-1993 and 2008.")

LABELS = {
    "ethnicity": {"Georgians": "Georgian", "Azerbaijanians": "Azerbaijani",
                  "Armenians": "Armenian", "Russians": "Russian", "Ossetians": "Ossetian",
                  "Yezidis": "Yazidi", "Ukrainians": "Ukrainian", "Kists": "Kist",
                  "Greeks": "Greek", "Assyrians": "Assyrian", "Other": "Other",
                  "Refusal": "Not declared", "Not stated": "Not stated"},
    "religion": {"Orthodox": "Orthodox", "Muslim": "Muslim",
                 "Armenian apostolic": "Armenian Apostolic", "Catholic": "Catholic",
                 "Jehovah’s Witnesses": "Jehovah's Witnesses", "Yazidis": "Yazidi",
                 "Protestant": "Protestant", "Judaism": "Judaism", "Other": "Other religion",
                 "None": "No religion", "Refusal": "Not stated", "Not stated": "Not stated"},
    "language": {"Georgian": "Georgian", "Abkhazian": "Abkhaz", "Ossetian": "Ossetian",
                 "Azerbaijanian": "Azerbaijani", "Russian": "Russian", "Armenian": "Armenian",
                 "Other": "Other", "Not stated": "Not stated"},
}
NOTES = {
    "ethnicity": ("Ethnicity (ეროვნება) as each person declared it, 2014 census, everyone "
                  "enumerated in the region. 'Not declared' is those who refused to answer, "
                  "'Not stated' those with no answer recorded. Groups Geostat does not name "
                  "are in 'Other'; cells of ten or fewer people are suppressed and counted "
                  "nowhere, which the note on each region states."),
    "religion": ("Religion (აღმსარებლობა), 2014 census, everyone enumerated in the region. "
                 "'Orthodox' is the census's Orthodox Christianity, overwhelmingly the "
                 "Georgian Orthodox Church. The census's refusals and unrecorded answers "
                 "are together in 'Not stated'."),
    "language": ("Native language (მშობლიური ენა), 2014 census, everyone enumerated in the "
                 "region; the languages Geostat names, the rest in 'Other'."),
}
BY_REGION_ONLY = ("Geostat's database publishes the 2014 census's {what} (table {table}) by "
                  "region only, shown one level up; the census's Main Results show it by "
                  "municipality only as charts, and volume I of the 2002 census gives it "
                  "(table {old}) by region too.")
MEDIAN_NOTE = ("From the 2014 census's population by five-year age group and sex, "
               "interpolated within the group holding the middle person: Geostat publishes "
               "single years of age for the country only.")
# OCHA's COD-PS for Georgia: Geostat's 2014 census by self-governed unit and
# five-year age group, which Geostat's own database does not carry.
COD_STUB = "cod-ps-geo"
COD_SOURCE = ("National Statistics Office of Georgia (Geostat), 2014 census, population by "
              "self-governed unit, sex and five-year age group, as OCHA's Common Operational "
              "Dataset for Georgia (cod-ps-geo) relays it")
# The 2014 table's spelling of a unit -> the boundary file's, where they differ.
COD_SPELLING = {"tskaltubo": "tsqaltubo", "tetritskaro": "tetrisqaro"}
MUNICIPAL_MEDIAN_NOTE = (
    "From the 2014 census's population of {parts} by five-year age group (to 85 and over), "
    "interpolated within the group holding the middle person. Geostat's own database and "
    "Main Results give a municipality's ages in three broad groups only; this is Geostat's "
    "five-year table as OCHA's COD-PS for Georgia relays it, whose counts are the census's "
    "own (table 02), unit by unit.")


def fold(text: str) -> str:
    """A self-governed unit's name for matching: 'C. Telavi*' and 'Telavi
    Municipality' both come to 'telavi'."""
    text = re.sub(r"^C\.\s*", "", str(text).strip())
    text = re.sub(r"\*+$", "", text).strip()
    text = re.sub(r"\s+(Municipality|Region|A\.R\.)$", "", text)
    text = re.sub(r"[^a-z]", "", text.lower())
    return SPELLING.get(text, text)


def number(cell: Any) -> float | None:
    if cell is None:
        return None
    text = str(cell).strip().replace(" ", "")
    if text in ("", "..", "...", "-", "…"):
        return None
    return float(text)


def meta(path: str) -> dict[str, dict[str, Any]]:
    got = http_json(BASE + urllib.parse.quote(path))
    return {v["code"]: v for v in got["variables"]}


def query(path: str, picks: dict[str, list[str]]) -> dict[tuple[str, ...], float | None]:
    """{(value text per variable, in the table's order): figure} for a selection
    given as {variable code: [value texts]} (every value when the list is empty)."""
    variables = meta(path)
    order = list(variables)
    body = {"query": [], "response": {"format": "json"}}
    for code, texts in picks.items():
        v = variables[code]
        by_text = dict(zip(v["valueTexts"], v["values"]))
        wanted = [by_text[t] for t in texts] if texts else v["values"]
        if texts and (missing := [t for t in texts if t not in by_text]):
            raise SystemExit(f"georgia: {path} has no {missing} under {code}")
        body["query"].append({"code": code, "selection": {"filter": "item", "values": wanted}})
    got = http_json(BASE + urllib.parse.quote(path), body)
    names = {code: dict(zip(v["values"], v["valueTexts"])) for code, v in variables.items()}
    columns = [c["code"] for c in got["columns"] if c.get("type") != "c"]
    out = {}
    for row in got["data"]:
        key = tuple(names[code][val] for code, val in zip(columns, row["key"]))
        out[key] = number(row["values"][0])
    log(f"  {path.rsplit('/', 1)[-1]}: {len(out)} cells ({', '.join(columns)})")
    return out


def cite(field: str, table: str, year: int) -> dict[str, Any]:
    return {"field": field, "name": SOURCE.format(table=table), "url": PAGE,
            "license": LICENCE, "year": year}


# ---------------------------------------------------------------------------
# Reading


def estimate() -> tuple[int, dict[str, float]]:
    """The latest 1 January estimate: (year, {row label: population})."""
    variables = meta(T_POP)
    geo = next(c for c in variables if c.startswith("region"))
    year = max(variables["year"]["valueTexts"])
    cells = query(T_POP, {geo: [], "year": [year]})
    got = {key[0]: n for key, n in cells.items() if n is not None}
    # The table is in thousands, to one decimal: the country reads about 3,700.
    if not 1_000 < got.get("Georgia", 0) < 10_000:
        raise SystemExit(f"georgia: the country's estimate reads {got.get('Georgia')}, "
                         "not a number of thousands")
    return int(year), {k: round(n * 1000) for k, n in got.items()}


def ages_by_region() -> dict[str, dict[str, Any]]:
    cells = query(T_AGE, {"Age": [], "Regions": [], "Urban/Rural": ["Total"],
                          "Sex": ["Both sexes", "Males", "Females"]})
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"groups": {}, "sex": {}})
    for (age, region, _, sex), n in cells.items():
        if age == "Total":
            out[region]["sex"][sex] = n or 0.0
        elif sex == "Both sexes":
            out[region]["groups"][age] = n or 0.0
    return out


def age_band(label: str) -> tuple[int, int | None]:
    if m := re.match(r"^(\d+)-(\d+)$", label):
        return int(m.group(1)), int(m.group(2))
    if m := re.match(r"^(\d+)\s*(\+|and over)$", label):
        return int(m.group(1)), None
    raise SystemExit(f"georgia: unreadable age group {label!r}")


def age_values(row: dict[str, Any], name: str) -> dict[str, Any]:
    total, men, women = (row["sex"].get(k) for k in ("Both sexes", "Males", "Females"))
    groups = sorted((*age_band(a), n) for a, n in row["groups"].items())
    made = sum(n for *_, n in groups)
    if not total or abs(made - total) > 0.5 or abs((men or 0) + (women or 0) - total) > 0.5:
        raise SystemExit(f"georgia: {name}'s ages make {made:,.0f} and its sexes "
                         f"{(men or 0) + (women or 0):,.0f}, its total {total}")
    table = "2014 census, population by regions, age and sex (table 07)"
    return {
        "median_age": measure(grouped_median(groups), unit="years", year=CENSUS_YEAR,
                              source=SOURCE.format(table=table)),
        "median_age_note": MEDIAN_NOTE,
        "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                             year=CENSUS_YEAR, source=SOURCE.format(table=table)),
        "sex_ratio_note": f"{int(men):,} men and {int(women):,} women enumerated in 2014.",
    }


def region_2014(ages: dict[str, dict[str, Any]], comps: dict[str, dict[str, dict[str, Any]]],
                census: str, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A region's 2014 census figures -- median age, sex and the three
    compositions -- and their citations. Tbilisi's municipality polygon takes
    the same rows as its region's: the two are one city."""
    values: dict[str, Any] = dict(age_values(ages[census], name))
    cites = [cite("median_age", "2014 census, table 07", CENSUS_YEAR),
             cite("sex_ratio", "2014 census, table 07", CENSUS_YEAR)]
    for field in T_COMP:
        row = comps[field][census]
        values[field] = shares(dict(row["counts"]), total=row["total"])
        values[f"{field}_year"] = CENSUS_YEAR
        values[f"{field}_note"] = NOTES[field] + (
            f" {row['hidden']} categories are suppressed in this region "
            f"({row['total'] - sum(row['counts'].values()):,.0f} people)."
            if row["hidden"] else "")
        cites.append(cite(field, f"2014 census, table {T_COMP[field].split('/')[-1][:2]}",
                          CENSUS_YEAR))
    return values, cites


def compositions() -> dict[str, dict[str, dict[str, Any]]]:
    """{field: {census region: {"counts": {label: n}, "total": n, "hidden": k}}}."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for field, path in T_COMP.items():
        variables = meta(path)
        geo = "Regions"
        group = next(c for c in variables if c != geo and c not in ("Urban/Rural",
                     "fluently speak Georgian language"))
        picks = {geo: [], group: []}
        for other in ("Urban/Rural", "fluently speak Georgian language"):
            if other in variables:
                picks[other] = ["Total"]
        cells = query(path, picks)
        gi, ri = list(variables).index(group), list(variables).index(geo)
        by_region: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"counts": Counter(), "total": None, "hidden": 0})
        for key, n in cells.items():
            region, label = key[ri], key[gi].strip()
            if region.startswith("…") or region not in REGION and region != "GEORGIA":
                continue
            row = by_region[region]
            if label == "Total":
                row["total"] = n
                continue
            if label not in LABELS[field]:
                raise SystemExit(f"georgia: {field} has a category {label!r} with no label")
            if n is None:
                row["hidden"] += 1
                continue
            row["counts"][LABELS[field][label]] += n
        for region, row in by_region.items():
            made = sum(row["counts"].values())
            if row["total"] is None or made > row["total"] + 0.5 or \
                    row["total"] - made > 10 * row["hidden"] + 0.5:
                raise SystemExit(f"georgia: {field} in {region}: categories make {made:,.0f} "
                                 f"against {row['total']} with {row['hidden']} suppressed")
        out[field] = dict(by_region)
        log(f"  {field}: {len(by_region)} areas; every region's categories make its total "
            "(less its suppressed cells of ten or fewer)")
    return out


def sexes_2014() -> dict[str, dict[str, float]]:
    """{self-governed unit: {"Males": n, "Females": n, "Both sexes": n}}, 2014."""
    variables = meta(T_SEX2)
    geo = next(c for c in variables if "unit" in c.lower() or "self" in c.lower())
    urban = next((c for c in variables if c.lower().startswith("urban")), None)
    sex = next(c for c in variables if c.lower() == "sex")
    picks = {geo: [], sex: []}
    if urban:
        picks[urban] = [variables[urban]["valueTexts"][0]]
    cells = query(T_SEX2, picks)
    order = list(variables)
    gi, si = order.index(geo), order.index(sex)
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for key, n in cells.items():
        label = {"both sexes": "Both sexes", "total": "Both sexes", "males": "Males",
                 "male": "Males", "females": "Females", "female": "Females"}.get(
                     key[si].strip().lower())
        if label and n is not None:
            out[key[gi].strip()][label] = n
    return dict(out)


def cod_key(name: str) -> str:
    """The 2014 age table's unit for matching: its cities are 'c. Batumi'."""
    key = fold(re.sub(r"(?i)^c\.\s*", "", str(name).strip()))
    return COD_SPELLING.get(key, key)


def municipal_ages() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], str]:
    """The 2014 census's units by five-year age group, as OCHA's COD-PS relays
    Geostat's table: ({folded unit name: [rows]}, the columns, the licence)."""
    package = cod_ps.get("package_show", id=COD_STUB)
    if not cod_ps.is_usable(package):
        raise SystemExit(f"georgia: {COD_STUB}'s licence is {cod_ps.licence(package)}")
    table = next((t for t in cod_ps_age.tables(package)
                  if t["level"] == "2" and t["label"].lower().endswith(".csv")), None)
    if table is None:
        raise SystemExit(f"georgia: {COD_STUB} has no second-level CSV")
    cols = cod_ps_age.age_columns(table["columns"])
    if cols is None or cols["sexes"] != "T":
        raise SystemExit(f"georgia: {table['label']} has no five-year groups for both sexes")
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table["rows"]:
        if not any(str(v if v is not None else "").strip() for v in row.values()):
            continue
        if str(row.get("YEAR") or "").strip() != str(CENSUS_YEAR):
            raise SystemExit(f"georgia: {table['label']} has a row of {row.get('YEAR')!r}")
        out[cod_key(row.get("ADM2_EN") or "")].append(row)
    log(f"  {table['label']}: {sum(len(v) for v in out.values())} units of the 2014 census "
        f"in five-year groups to {cols['opens']['T'][0]} and over")
    return dict(out), cols, cod_ps.licence(package)


def unit_label(row: dict[str, Any]) -> str:
    """'Batumi (city)' for the table's 'c. Batumi', a city."""
    name = re.sub(r"(?i)^c\.\s*", "", str(row.get("ADM2_EN") or "").strip())
    return f"{name} ({str(row.get('ADM2TYPE_EN') or 'unit').strip()})"


def census_ages(rows: list[dict[str, Any]], cols: dict[str, Any],
                name: str) -> tuple[float, float | None]:
    """The count and median of one or more of the 2014 table's units together."""
    groups: dict[tuple[int, int | None], float] = defaultdict(float)
    total = 0.0
    for row in rows:
        got, why = cod_ps_age.unit_figures(row, cols)
        if got is None:
            raise SystemExit(f"georgia: {name}: the 2014 table's {row.get('ADM2_EN')}: {why}")
        total += cod_ps_age.number(row.get(cols["totals"]["T"])) or 0.0
        for band, column in cols["groups"]["T"].items():
            groups[band] += cod_ps_age.number(row.get(column)) or 0.0
        low, column = cols["opens"]["T"]
        groups[(low, None)] += cod_ps_age.number(row.get(column)) or 0.0
    counts = sorted(((lo, hi, n) for (lo, hi), n in groups.items()),
                    key=lambda g: (g[1] is None, g[0]))
    return total, grouped_median(counts)


# ---------------------------------------------------------------------------
# The 2002 census's ethnicity by raion
#
# The only published ethnicity below the region. Volume I of the 2002 census
# results (Tbilisi, 2003), table 22, "permanent population by nationality, by
# region, city and raion", read from the Internet Archive's capture of the
# copy on census.ge. The book is set in the pre-Unicode AcadNusx Georgian font,
# so its text reads as Latin letters ("qarTveli" is ქართველი); the names below
# are written as the text reads. The raions of 2002 are the municipalities of
# 2006 onwards, renamed and not redrawn, which is what the map draws.

CENSUS_2002 = ("https://web.archive.org/web/20190821123826id_/"
               "http://census.ge/files/2002/geo/I%20tomi.pdf")
YEAR_2002 = 2002
GROUPS_2002 = ["Georgian", "Abkhaz", "Ossetian", "Armenian", "Russian", "Azerbaijani",
               "Greek", "Ukrainian", "Kist", "Yazidi"]
# The table's row -> the map's polygon (a municipality), or the city key for a
# city the map draws inside one, or None for a region's own row.
RAION_2002 = {
    "q. baTumi": "batumi", "qedis": "Keda", "qobuleTis": "Kobuleti", "Suaxevis": "Shuakhevi",
    "xelvaCauris": "Khelvachauri", "xulos": "Khulo", "lanCxuTis": "Lanchkhuti",
    "ozurgeTis": "Ozurgeti", "Coxatauris": "Chokhatauri", "q. quTaisi": "kutaisi",
    "tyibulis": "Tkibuli", "wyaltubos": "Tsqaltubo", "WiaTuris": "Chiatura",
    "baRdaTis": "Baghdati", "vanis": "Vani", "zestafonis": "Zestaponi", "Terjolis": "Terjola",
    "samtrediis": "Samtredia", "saCxeris": "Sachkhere", "xaragaulis": "Kharagauli",
    "xonis": "Khoni", "axmetis": "Akhmeta", "gurjaanis": "Gurjaani",
    "dedofliswyaros": "Dedoplis Tskaro", "Telavis": "Telavi", "lagodexis": "Lagodekhi",
    "sagarejos": "Sagarejo", "siRnaRis": "Sighnaghi", "yvarelis": "Qvareli",
    "axalgoris": "Akhalgori", "duSeTis": "Dusheti", "TianeTis": "Tianeti", "mcxeTis": "Mtskheta",
    "yazbegis": "Kazbegi", "ambrolauris": "Ambrolauri", "onis": "Oni", "cageris": "Tsageri",
    "lentexis": "Lentekhi", "zugdidis": "Zugdidi", "abaSis": "Abasha", "martvilis": "Martvili",
    "senakis": "Senaki", "Cxorowyus": "Chkhorotsku", "walenjixis": "Tsalenjikha",
    "xobis": "Khobi", "mestiis": "Mestia", "q. foTi": "poti", "adigenis": "Adigeni",
    "aspinZis": "Aspindza", "axalqalaqis": "Akhalkalaki", "axalcixis": "Akhaltsikhe",
    "borjomis": "Borjomi", "ninowmindis": "Ninotsminda", "q. rusTavi": "rustavi",
    "bolnisis": "Bolnisi", "gardabnis": "Gardabani", "dmanisis": "Dmanisi",
    "marneulis": "Marneuli", "TeTri wyaros": "Tetri Sqaro", "walkis": "Tsalka",
    "goris": "Gori", "kaspis": "Kaspi", "qarelis": "Kareli", "xaSuris": "Khashuri",
    "q. Tbilisis meria": "Tbilisi",
}
REGIONS_2002 = {
    "saqarTvelo - sul": "Georgia", "aWaris ar": "Adjara", "guria": "Guria",
    "imereTi": "Imereti", "kaxeTi": "Kakheti", "mcxeTa-mTianeTi": "Mtskheta-Mtianeti",
    "raWa-leCxumi da qvemo svaneTi": "Racha-Lechkhumi and Kvemo Svaneti",
    "samegrelo-zemo svaneTi": "Samegrelo-Zemo Svaneti", "samcxe-javaxeTi": "Samtskhe-Javakheti",
    "qvemo qarTli": "Kvemo Kartli", "Sida qarTli": "Shida Kartli",
    "afxazeTis ar - (kodoris xeoba)": "Abkhazia (Kodori gorge)",
}
# Each region's rows, in the order the table prints them after the region.
NUMBER = re.compile(r"^(\d+|-)$")
NOTE_2002 = (
    "Nationality (ეროვნება) as each person declared it, from the 2002 census -- the latest "
    "published below the region: Geostat publishes the 2014 census's ethnicity by region "
    "only. Table 22 of volume I of the 2002 results names ten nationalities by raion; "
    "'Other' is the rest of the raion's count. The census covered the territory under the "
    "government's control, so a raion's villages outside it (in Gori, Kareli, Oni and "
    "Akhalgori raions) are not in its count. The raions of 2002 are the municipalities "
    "of 2006 onwards.")


def row_name(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+raioni$", "", text)
    return text


def ethnicity_2002(blob: bytes) -> dict[str, dict[str, Any]]:
    """{table row name: {"total": n, "counts": {label: n}}} from table 22."""
    import sys
    sys.path.insert(0, str(PROCESSED.parent.parent / "scripts"))
    from probe_pdf import PAGE_BREAK, laid_out

    pages = laid_out(blob).split(PAGE_BREAK)
    start = next(i for i, p in enumerate(pages) if "cxrili #22" in p)
    end = next(i for i, p in enumerate(pages) if "cxrili #23" in p)
    lines = [l.strip() for p in pages[start:end + 1] for l in p.split("\n")]
    lines = lines[:next(i for i, l in enumerate(lines) if "cxrili #23" in l)]
    return parse_table22(lines)


def parse_table22(lines: list[str]) -> dict[str, dict[str, Any]]:
    """Table 22's rows, a name split over the lines around its figures joined."""
    known = set(RAION_2002) | set(REGIONS_2002)
    out: dict[str, dict[str, Any]] = {}
    pending = ""
    for i, line in enumerate(lines):
        tokens = line.split()
        numbers = []
        while tokens and NUMBER.match(tokens[-1]):
            numbers.insert(0, tokens.pop())
        if len(numbers) < 11:
            pending = line
            continue
        numbers = numbers[-11:]
        prefix = " ".join(tokens)
        after = lines[i + 1] if i + 1 < len(lines) else ""
        tries = [row_name(prefix), row_name(f"{pending} {prefix}"),
                 row_name(f"{pending} {prefix} {after}"), row_name(f"{prefix} {after}")]
        name = next((t for t in tries if t in known), None)
        if name is None:
            raise SystemExit(f"georgia: table 22 has a row {line!r} (after {pending!r}) "
                             "that names no raion, city or region")
        values = [0.0 if n == "-" else float(n) for n in numbers]
        total, groups = values[0], values[1:]
        if sum(groups) > total:
            raise SystemExit(f"georgia: table 22's {name}: the nationalities make "
                             f"{sum(groups):,.0f}, more than its {total:,.0f}")
        counts = dict(zip(GROUPS_2002, groups))
        counts["Other"] = total - sum(groups)
        out[name] = {"total": total, "counts": counts}
        pending = ""
    if missing := sorted(known - set(out)):
        raise SystemExit(f"georgia: table 22 has no row for {missing}")
    # Every region is its raions and cities, and the regions are the country.
    members: dict[str, list[str]] = defaultdict(list)
    region = None
    for name in out:
        if name in REGIONS_2002:
            region = name
        elif region:
            members[region].append(name)
    for region, names in members.items():
        if region == "saqarTvelo - sul":
            continue
        made = sum(out[n]["total"] for n in names)
        if abs(made - out[region]["total"]) > 0.5:
            raise SystemExit(f"georgia: table 22's {region} is {out[region]['total']:,.0f}, "
                             f"its raions and cities {made:,.0f}")
    # Tbilisi is a region and a city at once, and the table prints it as a city.
    country = (sum(out[r]["total"] for r in REGIONS_2002 if r != "saqarTvelo - sul")
               + out["q. Tbilisis meria"]["total"])
    if abs(country - out["saqarTvelo - sul"]["total"]) > 0.5:
        raise SystemExit(f"georgia: table 22's regions make {country:,.0f}, the country "
                         f"{out['saqarTvelo - sul']['total']:,.0f}")
    log(f"  2002 census table 22: {len(out) - len(REGIONS_2002)} raions and cities; every "
        f"region is its rows and the regions make the country's "
        f"{out['saqarTvelo - sul']['total']:,.0f}")
    return out


# ---------------------------------------------------------------------------
# Placing the cities the map draws inside a municipality


def km(a: Any, b: Any) -> float:
    """Degrees of distance to kilometres at Georgia's latitude."""
    return a.distance(b) * 111.32 * math.cos(math.radians(42.0))


def displacing(why: dict[str, Any], year: int) -> dict[str, Any]:
    """A stated gap that an encyclopaedia's figure of before ``year + 1`` gives way to.

    A gap never displaces a figure by itself, so these reasons stood beside
    the figures they explain away: Wikidata's 2024 figure for Tsqaltubo, the
    municipality without Kutaisi, on a polygon that may hold the city; and
    Wikidata's "2,008" for Abkhazia, dated 1996. Geostat's statement is as of
    its estimate's year, so anything older yields, and an undated figure too.
    """
    return {**why, "displaces_before": year + 1, "displaces_undated": True}


def city_homes(polys: dict[str, Any], site: dict[str, dict[str, Any]]) -> tuple[dict, dict]:
    """({city key: polygon id}, {polygon id: reason it is refused})."""
    from shapely.geometry import Point

    places = {east_geo.fold(p["name"]): p for p in east_geo.places("GEO")}
    homes, refused = {}, {}
    for key, name in CITIES.items():
        p = places.get(key)
        if not p:
            raise SystemExit(f"georgia: GeoNames has no {name}")
        point = Point(p["lon"], p["lat"])
        near = sorted((km(geom, point), sid) for sid, (geom, _) in polys.items())
        inside = [sid for d, sid in near if d == 0.0]
        close = [sid for d, sid in near if d <= CITY_MARGIN_KM]
        if len(inside) == 1 and close == inside:
            homes[key] = inside[0]
            log(f"  {name}'s centre lies in {site[inside[0]]['name']!r}; the nearest other "
                f"polygon is {near[1][0]:.1f} km away")
            continue
        names = ", ".join(f"{site[s]['name']} ({d:.1f} km)" for d, s in near[:3])
        log(f"  {name}: not placed; polygons near its centre: {names}")
        for sid in close:
            refused[sid] = (f"The city of {name}, counted apart from every municipality, "
                            "has no polygon of its own on this map, and its centre lies "
                            f"within {CITY_MARGIN_KM} km of more than one: " + names
                            + ". The outline cannot say which polygon holds the city, so "
                            "no figure is written here.")
    return homes, refused


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()

    admin1 = json.loads((SITE / "admin1" / "GEO.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GEO.units.json").read_text())
    first = {u["name"]: u for u in admin1}
    parent = {u["id"]: u["name"] for u in admin1}
    site = {u["id"]: u for u in admin2}
    if missing := [m for m in REGION.values() if m not in first]:
        raise SystemExit(f"georgia: the map has no first-level unit {missing}")

    year, pop = estimate()
    comps = compositions()
    ages = ages_by_region()
    sex2 = sexes_2014()

    # The country's median from the same five-year groups the regions' come
    # from (its own row, or the regions together), against Eurostat's for the
    # census's own year, computed from Geostat's single years. Measured: 37.7
    # here against 37.5 for 1 January 2014; Eurostat's 1 January 2015 (37.4)
    # is on the base the census itself reset.
    whole = ages.get("Georgia") or ages.get("GEORGIA")
    if whole is not None:
        country_groups = sorted((*age_band(a), n) for a, n in whole["groups"].items())
    else:
        summed: dict[str, float] = defaultdict(float)
        for census in REGION:
            for a, n in ages[census]["groups"].items():
                summed[a] += n
        country_groups = sorted((*age_band(a), n) for a, n in summed.items())
    check_median("GE", CENSUS_YEAR, grouped_median(country_groups),
                 "georgia: the country's 2014 census ages")

    # The estimate: regions and their units add up, and the regions make the country.
    country = pop.get("Georgia")
    regions = {ESTIMATE_REGION[k]: v for k, v in pop.items() if k in ESTIMATE_REGION}
    if set(regions) != set(REGION):
        raise SystemExit(f"georgia: the estimate's regions are {sorted(regions)}")
    if abs(sum(regions.values()) - country) > 50 * len(regions):  # rounded to 100 each
        raise SystemExit(f"georgia: the regions make {sum(regions.values()):,.0f}, the "
                         f"country {country:,.0f}")
    log(f"  estimate for 1 January {year}: {len(regions)} regions make the country's "
        f"{country:,.0f}")

    def census_2014(census: str, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return region_2014(ages, comps, census, name)

    records: list[dict[str, Any]] = []
    for census, name in REGION.items():
        u = first[name]
        values: dict[str, Any] = {
            "population": measure(int(regions[census]), year=year,
                                  source=SOURCE.format(table="population as of 1 January "
                                                       "by regions and self-governed units")),
            "population_note": (f"Geostat's estimate for 1 January {year}, published in thousands to one decimal"
                                 + (", for the part of the region under the government's "
                                    "control" if name in ("Shida Kartli", "Mtskheta-Mtianeti")
                                    else "") + "."),
        }
        cites = [cite("population", "population as of 1 January by regions and self-governed "
                      "units", year)]
        more, more_cites = census_2014(census, name)
        values.update(more)
        cites += more_cites
        records.append(record(f"GEO-GEOSTAT-{u['id']}", name, level="admin1", parent="GEO",
                              country="GEO", match_by="shape_id", shape_id=u["id"],
                              sources=cites, **values))
    for name in ("Abkhazia",):
        u = first[name]
        why = displacing(gap(NOT_AVAILABLE, UNCOUNTED_NOTE.format(what="Abkhazia")), year)
        records.append(record(f"GEO-GEOSTAT-{u['id']}", name, level="admin1", parent="GEO",
                              country="GEO", match_by="shape_id", shape_id=u["id"],
                              population=why, median_age=why, sex_ratio=why, religion=why,
                              language=why, ethnicity=why))
    # The country's own 2014 rows, for a curated country record: the build
    # will not sum Georgia's regions into the country, whose count (the
    # Factbook's, with Abkhazia and South Ossetia) is not theirs.
    for field in T_COMP:
        row = comps[field]["GEORGIA"]
        log("  country " + json.dumps({
            "field": field, "total": row["total"], "hidden": row["hidden"],
            "groups": shares(dict(row["counts"]), total=row["total"])}, ensure_ascii=False))

    # Second level: municipalities by name within the map's region, the cities
    # by where their centre lies.
    polys = {sid: g for sid, g in east_geo.polygons("GEO").items() if sid in site}
    homes, refused = city_homes(polys, site)
    by_name: dict[str, str] = {}
    for u in admin2:
        k = fold(u["name"])
        if k in by_name:
            raise SystemExit(f"georgia: two polygons fold to {k!r}")
        by_name[k] = u["id"]
    units: dict[str, list[str]] = defaultdict(list)     # polygon -> estimate rows
    for label in pop:
        if label == "C. Tbilisi Municipality":
            units[by_name["tbilisi"]].append(label)     # a region and a unit at once
            continue
        if label in ESTIMATE_REGION or label == "Georgia" or label.startswith(("-", "*")):
            continue
        k = fold(label)
        if k in CITIES:
            if k in homes:
                units[homes[k]].append(label)
            continue
        if k in by_name:
            units[by_name[k]].append(label)
        elif label not in ("Abkhazia A.R.", "Ajara Municipality") and not label.endswith("**"):
            log(f"  estimate row {label!r} has no polygon")
    census_units: dict[str, list[str]] = defaultdict(list)
    regions_2014 = set(REGION) | {"Georgia", "GEORGIA"}
    for label in sex2:
        k = fold(label)
        if label in regions_2014 and k != "tbilisi":
            continue
        if k in CITIES:
            if k in homes:
                census_units[homes[k]].append(label)
            continue
        if k in by_name and label not in census_units[by_name[k]]:
            census_units[by_name[k]].append(label)
        elif k not in by_name and label not in regions_2014:
            log(f"  2014 unit {label!r} has no polygon")

    # The same units' five-year age groups (OCHA's relay of Geostat's table),
    # placed as table 02's rows are; Tbilisi's districts go to the city.
    cod_rows, cod_cols, cod_licence = municipal_ages()
    cod_units: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tbilisi_rows: list[dict[str, Any]] = []
    for k, rows in cod_rows.items():
        if all(fold(r.get("ADM1_EN") or "").endswith("tbilisi") for r in rows) and k != "tbilisi":
            tbilisi_rows += rows
        elif k in CITIES:
            if k in homes:
                cod_units[homes[k]] += rows
        elif k in by_name:
            cod_units[by_name[k]] += rows
        else:
            log(f"  the 2014 age table's {[r.get('ADM2_EN') for r in rows]} has no polygon")
    # Tbilisi's districts together are the city, whose median the census's
    # region table (07) gives: the two tables must agree.
    city_total, city_median = census_ages(tbilisi_rows, cod_cols, "Tbilisi")
    region_groups = sorted((*age_band(a), n) for a, n in ages["C. Tbilisi"]["groups"].items())
    region_median = grouped_median(region_groups)
    if city_median != region_median or abs(city_total - sum(n for *_, n in region_groups)) > 0.5:
        raise SystemExit(f"georgia: Tbilisi's {len(tbilisi_rows)} districts in the 2014 age "
                         f"table make {city_total:,.0f} and a median of {city_median}; the "
                         f"census's region table {sum(n for *_, n in region_groups):,.0f} and "
                         f"{region_median}")
    log(f"  Tbilisi's {len(tbilisi_rows)} districts in the 2014 age table make the city's "
        f"{city_total:,.0f} and its median of {city_median}, as table 07 does")
    cod_written = 0

    # The 2002 census's ethnicity, by the raion each polygon is and the city
    # drawn inside it.
    eth02 = ethnicity_2002(http_get(CENSUS_2002, binary=True, timeout=600))
    by_map_name = {u["name"]: u["id"] for u in admin2}
    rows_2002: dict[str, list[str]] = defaultdict(list)
    for row, target in RAION_2002.items():
        if target in CITIES:
            if target in homes:
                rows_2002[homes[target]].append(row)
            continue
        if target not in by_map_name:
            raise SystemExit(f"georgia: 2002's {row} goes to {target!r}, which the map lacks")
        rows_2002[by_map_name[target]].append(row)

    def ethnicity_2002_values(sid: str) -> dict[str, Any]:
        rows = rows_2002.get(sid)
        if not rows:
            return {}
        counts: Counter = Counter()
        total = 0.0
        for r in rows:
            counts.update(eth02[r]["counts"])
            total += eth02[r]["total"]
        city = [r for r in rows if r.startswith("q. ")]
        return {"ethnicity": shares(dict(counts), total=total),
                "ethnicity_year": YEAR_2002,
                "ethnicity_note": NOTE_2002 + (
                    f" The city of {city[0][3:].replace('T', 't').title()}, counted apart, is "
                    "added: the map draws it inside this polygon." if city and
                    not city[0].startswith("q. Tbilisis") else "")
                + (" Akhalgori raion was enumerated in 2002, when it was under the "
                   "government's control, all but two of its village councils; it has not "
                   "been since 2008." if rows == ["axalgoris"] else ""),
                "_cite": cite("ethnicity", "2002 census, volume I, table 22 (census.ge, "
                              "via the Internet Archive)", YEAR_2002)}

    left = []
    for u in admin2:
        sid, name = u["id"], u["name"]
        where = parent[u["parent"]]
        if name in UNCOUNTED:
            why = gap(NOT_AVAILABLE, UNCOUNTED_NOTE.format(
                what="Abkhazia" if where == "Abkhazia" else "the Tskhinvali region"))
            # Abkhazia's encyclopaedia figures are the de facto authorities' or
            # a year read as a count (Wikidata's "2,008" for 1996), and give
            # way. Akhalgori's is the 2002 census's, Georgia's own, taken when
            # the raion was under the government's control -- the census whose
            # ethnicity is shown here -- and stands.
            if where == "Abkhazia":
                why = displacing(why, year)
            extra = ethnicity_2002_values(sid)
            cites = [extra.pop("_cite")] if extra else []
            records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                                  country="GEO", match_by="shape_id", shape_id=sid,
                                  population=why, median_age=why, sex_ratio=why,
                                  religion=why, language=why,
                                  **({"ethnicity": why} | extra), sources=cites))
            continue
        if sid in refused:
            why = displacing(gap(NOT_AVAILABLE, refused[sid]), year)
            records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                                  country="GEO", match_by="shape_id", shape_id=sid,
                                  population=why, sex_ratio=why, median_age=why,
                                  ethnicity=why, religion=why, language=why))
            continue
        if sid == by_name["tbilisi"]:
            # Tbilisi is a region and a municipality at once, one polygon at
            # each level: the 2014 census's region rows describe it, and are
            # newer than the 2002 raion table's.
            rows = units.get(sid) or []
            values = {"population": measure(int(sum(pop[r] for r in rows)), year=year,
                                            source=SOURCE.format(
                                                table="population as of 1 January by regions "
                                                      "and self-governed units")),
                      "population_note": (f"Geostat's estimate for 1 January {year}, "
                                          "published in thousands to one decimal.")}
            more, cites = census_2014("C. Tbilisi", name)
            values.update(more)
            cites.insert(0, cite("population", "population as of 1 January by regions and "
                                 "self-governed units", year))
            records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                                  country="GEO", match_by="shape_id", shape_id=sid,
                                  sources=cites, **values))
            continue
        rows = units.get(sid)
        if not rows:
            left.append(name)
            continue
        values: dict[str, Any] = {}
        cites = []
        parts = " and ".join(rows)
        values["population"] = measure(int(sum(pop[r] for r in rows)), year=year,
                                       source=SOURCE.format(table="population as of 1 "
                                                            "January by regions and "
                                                            "self-governed units"))
        values["population_note"] = (f"Geostat's estimate for 1 January {year}, published in thousands to one decimal: {parts}"
                                     + (", the city counted apart and drawn inside this "
                                        "polygon" if len(rows) > 1 else "") + ".")
        cites.append(cite("population", "population as of 1 January by regions and "
                          "self-governed units", year))
        crows = census_units.get(sid, [])
        men = sum(sex2[r].get("Males", 0) for r in crows)
        women = sum(sex2[r].get("Females", 0) for r in crows)
        if crows and women:
            values["sex_ratio"] = measure(round(100 * men / women, 1),
                                          unit="males_per_100_females", year=CENSUS_YEAR,
                                          source=SOURCE.format(table="2014 census, population "
                                                               "by self-governed units and "
                                                               "sex (table 02)"))
            values["sex_ratio_note"] = (f"{int(men):,} men and {int(women):,} women "
                                        "enumerated in 2014 in " + " and ".join(crows) + ".")
            cites.append(cite("sex_ratio", "2014 census, table 02", CENSUS_YEAR))
        arows = cod_units.get(sid, [])
        if arows:
            counted, median = census_ages(arows, cod_cols, name)
            enumerated = sum(sex2[r].get("Both sexes", 0) for r in crows)
            if abs(counted - enumerated) > 0.5:
                raise SystemExit(f"georgia: {name}: the 2014 age table's "
                                 f"{[r.get('ADM2_EN') for r in arows]} make {counted:,.0f}, "
                                 f"the census's table 02 ({crows}) {enumerated:,.0f}")
            what = " and ".join(unit_label(r) for r in arows)
            values["median_age"] = measure(median, unit="years", year=CENSUS_YEAR,
                                           source=COD_SOURCE)
            values["median_age_note"] = MUNICIPAL_MEDIAN_NOTE.format(parts=what) + (
                " The city counted apart is drawn inside this polygon." if len(arows) > 1
                else "")
            cites.append({"field": "median_age", "name": COD_SOURCE,
                          "url": cod_ps.DATASET_PAGE.format(stub=COD_STUB),
                          "license": cod_licence, "year": CENSUS_YEAR})
            cod_written += 1
        else:
            values["median_age"] = gap(NOT_AVAILABLE, (
                "Geostat publishes no age by municipality beyond the 2014 census's three "
                "broad groups (0-14, 15-64, 65 and over, in its Main Results), and OCHA's "
                "relay of its five-year table has no row for this unit."))
        for field, table in (("religion", "22"), ("language", "20")):
            values[field] = gap(NOT_AVAILABLE, BY_REGION_ONLY.format(
                what={"religion": "religion", "language": "native language"}[field],
                table=table, old={"religion": "29", "language": "23"}[field]))
        extra = ethnicity_2002_values(sid)
        if extra:
            cites.append(extra.pop("_cite"))
            values.update(extra)
        records.append(record(f"GEO-GEOSTAT-{sid}", name, level="admin2", parent="GEO",
                              country="GEO", match_by="shape_id", shape_id=sid,
                              sources=cites, **values))
    if left:
        log(f"  polygons with no estimate row: {left}")
    log(f"  second level: {cod_written} polygons with a median from the 2014 age table, "
        "each one's count the census's own")
    # Every estimate row is somewhere: on a polygon, on a refused polygon's
    # city, or in the occupied territories.
    placed = {r for rows in units.values() for r in rows}
    stray = [l for l in pop if l not in placed and l not in ESTIMATE_REGION
             and l != "Georgia" and fold(l) not in CITIES and pop[l]]
    log(f"  second level: {sum(1 for r in records if r['level'] == 'admin2' and isinstance(r.get('population'), dict) and 'value' in r['population'])} "
        f"polygons with a count; rows on no polygon: {stray}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
