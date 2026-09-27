#!/usr/bin/env python3
"""Liechtenstein: its eleven Gemeinden, from the Amt für Statistik's eTab.

The office publishes its tables on a PxWeb server (etab.llv.li, API v1), and
three of them are read:

* 211.004 -- the permanent population on 31 December by single year of age
  (0 to 105), sex, citizenship and Gemeinde, from the population register:
  the population, median age and sex ratio;
* 213.001d -- the permanent population by religion and Gemeinde, from the
  Volkszählung 2020 (reference day 31 December 2020);
* 213.011d -- the permanent population by main language (Hauptsprache) and
  Gemeinde, from the same census.

Both census questions take one answer a person, so the categories partition
the population, which is checked for every Gemeinde. The religion list is two
levels deep in one place -- "Evangelisch (reformiert, protestantisch)" beside
the three churches it is made of -- and the parent is dropped once it has been
seen to equal its children, so nobody is counted twice.

**One polygon, two levels.** The boundary file draws each Gemeinde both as a
first-level and as a second-level unit under the same shape id, so every
figure is written twice, once for each level, bound by shape id.

Ethnicity is not asked: the census records citizenship (Staatsbürgerschaft),
which is a different question and is not used as a proxy.

Usage:
    python -m scripts.fetch_census.liechtenstein
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from ._shared import PROCESSED, dated, log, measure, record, shares, write_json
from .central_ages import age_sex_fields, check_sum, fold, units
from .pxweb import unstack
from common import USER_AGENT  # noqa: E402

BASE = "https://etab.llv.li/PXWeb/api/v1/de/eTab/"
TABLES = {
    "age": "Bevölkerung/Bevölkerungsstand/Stichtag 31 Dezember/211.004.px",
    "religion": "Bevölkerung/Bevölkerungsstruktur/213.001d.px",
    "language": "Bevölkerung/Bevölkerungsstruktur/213.011d.px",
}
PORTAL = "https://www.statistikportal.li/de/anwendungen-datenbanken/etab"
SOURCE_AGE = "Amt für Statistik Liechtenstein, eTab 211.004 (Bevölkerungsstatistik, {year})"
SOURCE_CENSUS = "Amt für Statistik Liechtenstein, Volkszählung 2020, eTab {table}"
LICENCE = "Amt für Statistik Liechtenstein (free reuse with attribution)"
OUT = PROCESSED / "liechtenstein_gemeinde.json"
CENSUS_YEAR = 2020
GEMEINDEN = ("Vaduz", "Triesen", "Balzers", "Triesenberg", "Schaan", "Planken", "Eschen",
             "Mauren", "Gamprin", "Ruggell", "Schellenberg")

# 211.004 counts people by locality (Wohnort), not by Gemeinde: three of the
# eleven Gemeinden are two localities each in it. Nendeln is a village of
# Eschen, Schaanwald of Mauren, and "Gamprin-Bendern" is the Gemeinde of
# Gamprin under the names of its two villages.
LOCALITY = {"Nendeln": "Eschen", "Schaanwald": "Mauren", "Gamprin-Bendern": "Gamprin"}

RELIGION = {
    "Römisch-katholisch": "Roman Catholic",
    # The answer "Protestant" with no church named, a row of its own in 2020.
    "Evangelisch (reformiert, protestantisch)": "Protestant",
    "Evangelisch-reformiert": "Reformed",
    "Evangelisch-lutherisch": "Lutheran",
    "Andere protestantische Kirchen": "Other Protestant",
    "Christlich-orthodox": "Orthodox",
    "Andere christliche Kirchen": "Other Christian",
    "Islamisch": "Islam",
    "Islam": "Islam",
    "Islamische Gemeinschaften": "Islam",
    "Andere Religionen": "Other religion",
    "Andere Religionsgemeinschaften": "Other religion",
    "Jüdisch": "Judaism",
    "Keine Religionszugehörigkeit": "No religion",
    "Ohne Religionszugehörigkeit": "No religion",
    "Keine Religion": "No religion",
    "Konfessionslos": "No religion",
    "Ohne Angabe": "Not stated",
}
# The parent row in the religion table, dropped once it equals its children.
RELIGION_PARENT = "Evangelisch (reformiert, protestantisch)"
RELIGION_CHILDREN = ("Evangelisch-reformiert", "Evangelisch-lutherisch",
                     "Andere protestantische Kirchen")

LANGUAGE = {
    "Deutsch": "German", "Französisch": "French", "Italienisch": "Italian",
    "Rätoromanisch": "Romansh", "Englisch": "English", "Niederländisch": "Dutch",
    "Spanisch": "Spanish", "Portugiesisch": "Portuguese", "Türkisch": "Turkish",
    "Albanisch": "Albanian", "Serbisch": "Serbian", "Kroatisch": "Croatian",
    "Bosnisch": "Bosnian", "Serbokroatisch": "Serbo-Croatian",
    "Serbisch, Kroatisch, Bosnisch": "Serbo-Croatian",
    "Serbisch/Kroatisch/Bosnisch/Montenegrinisch": "Serbo-Croatian",
    "Ungarisch": "Hungarian", "Tschechisch": "Czech", "Slowakisch": "Slovak",
    "Polnisch": "Polish", "Russisch": "Russian", "Ukrainisch": "Ukrainian",
    "Slowenisch": "Slovene", "Rumänisch": "Romanian", "Griechisch": "Greek",
    "Mazedonisch": "Macedonian", "Bulgarisch": "Bulgarian", "Arabisch": "Arabic",
    "Tamilisch": "Tamil", "Chinesisch": "Chinese", "Thailändisch": "Thai",
    "Tagalog": "Filipino", "Vietnamesisch": "Vietnamese", "Japanisch": "Japanese",
    "Kurdisch": "Kurdish", "Persisch": "Persian", "Schwedisch": "Swedish",
    "Norwegisch": "Norwegian", "Dänisch": "Danish", "Finnisch": "Finnish",
    "Lettisch": "Latvian", "Litauisch": "Lithuanian", "Estnisch": "Estonian",
    "Hindi": "Hindi", "Tibetisch": "Tibetan", "Somalisch": "Somali",
    "Tigrinya": "Tigrinya", "Eritreisch": "Tigrinya",
    "Übrige Sprachen": "Other language", "Andere Sprachen": "Other language",
    "Übrige europäische Sprachen": "Other European languages",
    "Übrige westeuropäische Sprachen": "Other language",
    "Übrige osteuropäische Sprachen": "Other language",
    "Übrige slawische Sprachen": "Other Slavic languages",
    "Übrige asiatische Sprachen": "Other language",
    "Übrige afrikanische Sprachen": "Other language",
    "Ohne Angabe": "Not stated",
}


def table_url(key: str) -> str:
    return BASE + urllib.parse.quote(TABLES[key])


def post(key: str, query: list[dict[str, Any]]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    url = table_url(key)
    body = json.dumps({"query": query, "response": {"format": "json-stat"}}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8-sig"))
    if "dataset" in payload:              # json-stat 1, where a server ignores the ask
        payload = payload["dataset"]
        payload = {"id": payload["dimension"]["id"], "size": payload["dimension"]["size"],
                   "dimension": payload["dimension"], "value": payload["value"]}
    asked = {q["code"]: len(q["selection"]["values"]) for q in query}
    log(f"  {TABLES[key].rsplit('/', 1)[-1]}: asked {asked}, answered {payload.get('size')}, {len(payload['value'])} values of type {type(payload['value']).__name__}")
    return unstack(payload)


def meta(key: str) -> dict[str, dict[str, str]]:
    """{variable code: {value text: value code}}."""
    req = urllib.request.Request(table_url(key), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8-sig"))
    return {v["code"]: dict(zip(v["valueTexts"], v["values"])) for v in data["variables"]}


def pick(variables: dict[str, dict[str, str]], word: str) -> str:
    hits = [code for code in variables if word.lower() == code.lower()] or \
        [code for code in variables if word.lower() in code.lower()]
    if len(hits) != 1:
        raise SystemExit(f"liechtenstein: no single variable named like {word!r}: {sorted(variables)}")
    return hits[0]


def gemeinde_name(label: str) -> str:
    """A place label without the indentation marks or code a table may put on it."""
    text = label.strip().lstrip(".-> ").strip()
    for name in (*GEMEINDEN, "Liechtenstein"):
        if text == name or text.endswith(" " + name) or text.startswith(name + " "):
            return name
    return text


def total_code(values: dict[str, str]) -> str:
    hits = [code for text, code in values.items() if "Total" in text or text == "Liechtenstein"]
    if len(hits) != 1:
        raise SystemExit(f"liechtenstein: no single total among {list(values)[:6]}")
    return hits[0]


def ages(year: int) -> tuple[dict[str, Counter], dict[str, Counter]]:
    var = meta("age")
    jahr, alter, sex, heimat, ort = (pick(var, w) for w in
                                     ("Jahr", "Altersjahr", "Geschlecht", "Heimat", "Wohnort"))
    if str(year) not in var[jahr]:
        raise SystemExit(f"liechtenstein: 211.004 has no {year}; it has {list(var[jahr])[:4]}")
    query = [
        {"code": jahr, "selection": {"filter": "item", "values": [var[jahr][str(year)]]}},
        {"code": alter, "selection": {"filter": "item", "values": list(var[alter].values())}},
        {"code": sex, "selection": {"filter": "item", "values": list(var[sex].values())}},
        {"code": heimat, "selection": {"filter": "item", "values": [total_code(var[heimat])]}},
        {"code": ort, "selection": {"filter": "item", "values": list(var[ort].values())}},
    ]
    males: dict[str, Counter] = {}
    females: dict[str, Counter] = {}
    totals: dict[str, float] = {}
    rows = post("age", query)
    seen = sorted({k[ort][1] for k, _ in rows})
    log(f"  211.004: {len(rows):,} cells; places {seen}")
    for key, value in rows:
        place = LOCALITY.get(key[ort][1].strip(), gemeinde_name(key[ort][1]))
        age_text = key[alter][1].strip()
        sex_text = key[sex][1].strip()
        if "Total" in age_text:
            if "Total" in sex_text:
                totals[place] = totals.get(place, 0) + value
            continue
        years = int("".join(ch for ch in age_text if ch.isdigit()))
        if sex_text == "Männer":
            males.setdefault(place, Counter())[years] += value
        elif sex_text == "Frauen":
            females.setdefault(place, Counter())[years] += value
    return males, females, totals


def census(key: str, labels: dict[str, str]) -> dict[str, dict[str, float]]:
    var = meta(key)
    stichtag = pick(var, "Stichtag")
    group = pick(var, "Religion" if key == "religion" else "Hauptsprache")
    sex = pick(var, "Geschlecht")
    place = pick(var, "Gemeinde")
    query = [
        {"code": stichtag, "selection": {"filter": "item", "values": [var[stichtag]["31.12.2020"]]}},
        {"code": group, "selection": {"filter": "item", "values": list(var[group].values())}},
        {"code": sex, "selection": {"filter": "item", "values": [total_code(var[sex])]}},
        {"code": place, "selection": {"filter": "item", "values": list(var[place].values())}},
    ]
    others = [c for c in var if c not in {stichtag, group, sex, place}]
    for code in others:                    # Heimat: both citizenships together
        query.append({"code": code, "selection": {"filter": "item",
                                                  "values": [total_code(var[code])]}})
    raw: dict[str, dict[str, float]] = {}
    for k, value in post(key, query):
        raw.setdefault(gemeinde_name(k[place][1]), {})[k[group][1].strip()] = value
    out: dict[str, dict[str, float]] = {}
    unknown = set()
    for gemeinde, rows in raw.items():
        total = next(v for label, v in rows.items() if "Total" in label)
        parts = {label: v for label, v in rows.items() if "Total" not in label}
        if key == "religion" and RELIGION_PARENT in parts:
            # Either a subtotal of the three Protestant rows after it, or the
            # answer "Protestant" given without a church. The sums say which:
            # the rows partition the Gemeinde one way or the other.
            summed = sum(parts.values())
            if abs(summed - parts[RELIGION_PARENT] - total) <= 0.5:
                del parts[RELIGION_PARENT]
            elif abs(summed - total) > 0.5:
                raise SystemExit(f"liechtenstein: {gemeinde}: religion rows make {summed:,.0f} "
                                 f"with {RELIGION_PARENT!r} and {summed - parts[RELIGION_PARENT]:,.0f} "
                                 f"without it; the total is {total:,.0f}")
        counts: dict[str, float] = {}
        for label, v in parts.items():
            english = labels.get(label)
            if english is None:
                unknown.add(label)
                continue
            counts[english] = counts.get(english, 0) + v
        if abs(sum(parts.values()) - total) > 0.5:
            raise SystemExit(f"liechtenstein: {gemeinde} {key}: categories sum to "
                             f"{sum(parts.values()):,.0f}, the total is {total:,.0f}")
        counts["_total"] = total
        out[gemeinde] = counts
    if unknown:
        raise SystemExit(f"liechtenstein: {key} labels with no English name here: {sorted(unknown)}")
    return out


def build(year: int) -> list[dict[str, Any]]:
    log(f"liechtenstein: eTab 211.004 ({year}), 213.001d and 213.011d (Volkszählung 2020)")
    males, females, totals = ages(year)
    missing = [g for g in (*GEMEINDEN, "Liechtenstein") if g not in totals]
    if missing:
        raise SystemExit(f"liechtenstein: 211.004 has no rows for {missing}; it has {sorted(totals)}")
    national = totals["Liechtenstein"]
    check_sum((totals[g] for g in GEMEINDEN), national, "Gemeinden against Liechtenstein")
    religion = census("religion", RELIGION)
    language = census("language", LANGUAGE)
    check_sum((religion[g]["_total"] for g in GEMEINDEN), religion["Liechtenstein"]["_total"],
              "Gemeinden against Liechtenstein, census 2020")
    source_age = SOURCE_AGE.format(year=year)
    shapes = {fold(u["name"]): u for u in units("LIE", "admin2")}
    firsts = {fold(u["name"]): u for u in units("LIE", "admin1")}
    records = []
    for gemeinde in GEMEINDEN:
        fields = age_sex_fields(
            males[gemeinde], females[gemeinde], year=year, source=source_age,
            total=totals[gemeinde],
            median_note=(f"Interpolated within the single year of age that holds the middle "
                         f"person, from the Amt für Statistik's count of the Gemeinde's permanent "
                         f"population on 31 December {year} by single year of age (eTab 211.004)."),
            ratio_note=f"Males per 100 females in the permanent population on 31 December {year}.")
        rel = {k: v for k, v in religion[gemeinde].items() if k != "_total"}
        lang = {k: v for k, v in language[gemeinde].items() if k != "_total"}
        fields.update({
            "religion": shares(rel, total=religion[gemeinde]["_total"]),
            "religion_year": dated(shares(rel), CENSUS_YEAR),
            "religion_note": (
                "Religious affiliation, Volkszählung 2020 (31 December 2020): one answer per "
                "person, the whole permanent population; 'Not stated' is kept as its own bar."),
            "language": shares(lang, total=language[gemeinde]["_total"]),
            "language_year": dated(shares(lang), CENSUS_YEAR),
            "language_note": (
                "Main language (Hauptsprache) -- the language a person thinks in and knows best "
                "-- Volkszählung 2020: one answer per person, the whole permanent population."),
        })
        sources = [
            {"field": "population/median_age/sex_ratio", "name": source_age, "url": PORTAL,
             "license": LICENCE, "year": year},
            {"field": "religion", "name": SOURCE_CENSUS.format(table="213.001d"), "url": PORTAL,
             "license": LICENCE, "year": CENSUS_YEAR},
            {"field": "language", "name": SOURCE_CENSUS.format(table="213.011d"), "url": PORTAL,
             "license": LICENCE, "year": CENSUS_YEAR},
        ]
        for level, table in (("admin1", firsts), ("admin2", shapes)):
            shape = table.get(fold(gemeinde))
            if shape is None:
                raise SystemExit(f"liechtenstein: no {level} polygon named {gemeinde}")
            records.append(record(
                f"LIE-{fold(gemeinde)}-{level}", gemeinde, level=level,
                parent="LIE" if level == "admin1" else shape["parent"], country="LIE",
                match_by="shape_id", shape_id=shape["id"], sources=sources, **fields))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()
    records = build(args.year)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
