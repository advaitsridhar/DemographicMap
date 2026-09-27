#!/usr/bin/env python3
"""Serbia: the 2022 census by municipality and district, from RZS's open data.

The Statistical Office of the Republic of Serbia (RZS) publishes the 2022
Census of Population, Households and Dwellings in its dissemination database
(data.stat.gov.rs), and every dataset of it as a JSON file on its open-data
service (opendata.stat.gov.rs), for the country, the regions, the 25 areas
(oblasti -- the map's districts and Belgrade) and every municipality, city and
city municipality:

* 3104020201IND01 -- population by five-year age group and sex;
* 3104020101IND01 -- national affiliation (nacionalna pripadnost) by sex;
* 3104020301IND01 -- religion (veroispovest) by sex;
* 3104020302IND01 -- mother tongue (maternji jezik) by sex.

Single years of age are published by region only (3104021001IND01), so a
municipality's median age is interpolated within the five-year group that
holds the middle person, and the note says so. The districts keep Eurostat's
newer figures for age and head count; they take their compositions from here.

The map draws the five cities that are divided into city municipalities --
Niš, Novi Sad, Požarevac, Užice and Vranje -- whole, and RZS publishes each of
them whole too ("Grad Niš"); Belgrade is drawn as one unit and is the
Belgrade area. Kosovo is not in the census and not in this country's units.

Checks: every composition's categories add to its total, the Christian
subtotal to its denominations, the age groups and the sexes to the total, the
four tables agree on each unit's head count, and the bound units add to the
national count.

Usage:
    python -m scripts.fetch_census.serbia_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .balkans_common import age_fields, check_sum, fold, grouped_median, shapes

OUT = "serbia_census.json"
YEAR = 2022
API = "https://opendata.stat.gov.rs/data/WcfJsonRestService.Service1.svc/dataset/{id}/2/json"
PAGE = "https://data.stat.gov.rs/Home/Result/{sub}?languageCode=sr-Latn"
DATASETS = {
    "age": "3104020201IND01",
    "ethnicity": "3104020101IND01",
    "religion": "3104020301IND01",
    "language": "3104020302IND01",
}
TITLES = {
    "age": "population by age and sex",
    "ethnicity": "population by national affiliation and sex",
    "religion": "population by religion",
    "language": "population by mother tongue",
}
SOURCE = ("Statistical Office of the Republic of Serbia (RZS), 2022 Census of Population, "
          "Households and Dwellings, {title} (dataset {id})")
LICENCE = "Statistical Office of the Republic of Serbia, open data (reuse with attribution)"
NATIONAL = 6_647_003
COUNTRY = "REPUBLIKA SRBIJA"
# The keys every RZS record carries beside its own category.
FRAME = {"nTer", "nTipNaselja", "nPol", "nJedinicaMere", "nIzvorI", "nStatusPodatka",
         "nStarGrupa"}
# The map's first-level units -> RZS's areas (oblasti).
AREAS = {
    "Belgrade": "Beogradska oblast", "Bor District": "Borska oblast",
    "Branicevo District": "Braničevska oblast", "Central Banat District": "Srednjobanatska oblast",
    "Jablanica District": "Jablanička oblast", "Kolubara District": "Kolubarska oblast",
    "Macva District": "Mačvanska oblast", "Moravica District": "Moravička oblast",
    "Nisava District": "Nišavska oblast", "North Backa District": "Severnobačka oblast",
    "North Banat District": "Severnobanatska oblast", "Pcinja District": "Pčinjska oblast",
    "Pirot District": "Pirotska oblast", "Podunavlje District": "Podunavska oblast",
    "Pomoravlje District": "Pomoravska oblast", "Rasina District": "Rasinska oblast",
    "Raska District": "Raška oblast", "South Backa District": "Južnobačka oblast",
    "South Banat District": "Južnobanatska oblast", "Sumadija District": "Šumadijska oblast",
    "Syrmia District": "Sremska oblast", "Toplica District": "Toplička oblast",
    "West Backa District": "Zapadnobačka oblast", "Zajecar District": "Zaječarska oblast",
    "Zlatibor District": "Zlatiborska oblast",
}
# The map's second-level names that are not RZS's with the suffix dropped.
ALIASES = {"Belgrade": "Beogradska oblast"}

LABELS: dict[str, dict[str, str]] = {
    "ethnicity": {
        "srbi": "Serbian", "albanci": "Albanian", "bosnjaci": "Bosniak", "bugari": "Bulgarian",
        "bunjevci": "Bunjevac", "vlasi": "Vlach", "goranci": "Gorani", "jugosloveni": "Yugoslav",
        "madari": "Hungarian", "makedonci": "Macedonian", "muslimani": "Muslim (ethnic)",
        "nemci": "German", "romi": "Roma", "rumuni": "Romanian", "rusi": "Russian",
        "rusini": "Rusyn", "slovaci": "Slovak", "slovenci": "Slovene", "ukrajinci": "Ukrainian",
        "hrvati": "Croatian", "crnogorci": "Montenegrin", "ostali": "Other",
        "nisuseizjasnili": "Not declared", "nepoznato": "Not stated",
    },
    "religion": {
        "pravoslavna": "Orthodox", "katolicka": "Catholic", "protestantska": "Protestant",
        "ostalehriscanske": "Other Christian", "islamska": "Islam", "judeisticka": "Judaism",
        "istocnjackeveroispovesti": "Eastern religions", "ostaleveroispovesti": "Other religion",
        "agnostici": "Agnosticism", "nisuverniciateisti": "Atheism",
        "nisuseizjasnili": "Not declared", "nepoznato": "Not stated",
    },
    "language": {
        "srpski": "Serbian", "albanski": "Albanian", "bosanski": "Bosnian",
        "bugarski": "Bulgarian", "bunjevacki": "Bunjevac", "vlaski": "Vlach",
        "madarski": "Hungarian", "makedonski": "Macedonian", "nemacki": "German",
        "romski": "Romani", "rumunski": "Romanian", "ruminski": "Romanian", "ruski": "Russian",
        "rusinski": "Rusyn", "slovacki": "Slovak", "slovenacki": "Slovene",
        "ukrajinski": "Ukrainian", "hrvatski": "Croatian", "crnogorski": "Montenegrin",
        "ostalijezici": "Other", "nijeseizjasnio": "Not declared",
        "nisuseizjasnili": "Not declared", "nepoznato": "Not stated",
    },
}
# "Svega hrišćanska": the census's subtotal of the four Christian rows.
CHRISTIAN_SUBTOTAL = "svegahriscansk"  # RZS ends it with a Cyrillic a
CHRISTIAN = ("Orthodox", "Catholic", "Protestant", "Other Christian")
NOTES = {
    "ethnicity": ("National affiliation (nacionalna pripadnost), 2022 census, resident "
                  "population, free and optional declaration. Those who declared a regional "
                  "affiliation, those who did not declare and those whose answer is unknown are "
                  "their own bars; 'Muslim (ethnic)' is the census's Muslimani, a nationality, "
                  "and 'Vlach' its Vlasi."),
    "religion": ("Religion (veroispovest), 2022 census, resident population, free and optional "
                 "declaration, at the denominations RZS publishes; agnostics, atheists, the "
                 "undeclared and the unknown are their own bars. The census's subtotal of "
                 "Christians is not shown beside the four denominations it adds up."),
    "language": ("Mother tongue (maternji jezik), 2022 census, resident population; those who "
                 "did not declare and those whose answer is unknown are their own bars."),
}


def label_of(field: str, name: str) -> str | None:
    """The bar a category is shown as; None for a total or a subtotal."""
    f = fold(name)
    if f == "ukupno" or f.startswith(CHRISTIAN_SUBTOTAL):
        return None
    if field == "ethnicity" and f.startswith("izjasniliseusmisluregionalne"):
        return "Regional affiliation"
    return LABELS[field].get(f, "")


def key(name: str) -> str:
    """A territory's name folded; RZS's đ and the map's dj are one letter."""
    text = re.sub(r"\s+(Municipality|Municipal\*?|City)$", "", name.strip())
    return fold(text).replace("dj", "d")


def load(dataset: str) -> list[dict[str, Any]]:
    blob = http_get(API.format(id=dataset), binary=True, timeout=600)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    member = next(n for n in zf.namelist() if n.lower().endswith(".json"))
    rows = json.loads(zf.read(member).decode("utf-8-sig"))
    log(f"  {dataset}: {len(blob):,} bytes zipped, {len(rows):,} records")
    return [r for r in rows if str(r.get("god")) == str(YEAR)
            and r.get("nTipNaselja", "Ukupno").strip() == "Ukupno"]


def category_key(rows: list[dict[str, Any]], dataset: str) -> str:
    keys = {k for r in rows[:50] for k in r if k.startswith("n") and k not in FRAME}
    if len(keys) != 1:
        raise SystemExit(f"serbia_census: {dataset}: cannot tell the category among {sorted(keys)}")
    return keys.pop()


def value(r: dict[str, Any]) -> float:
    v = r.get("vrednost")
    return float(v) if v not in (None, "") else 0.0


def compositions(field: str) -> dict[str, dict[str | None, float]]:
    """{territory: {label: people, None: total}} for both sexes together."""
    dataset = DATASETS[field]
    rows = [r for r in load(dataset) if str(r.get("nPol", "")).strip() == "Ukupno"]
    cat = category_key(rows, dataset)
    out: dict[str, dict[str | None, float]] = defaultdict(lambda: defaultdict(float))
    subtotal: dict[str, float] = defaultdict(float)
    unknown: set[str] = set()
    for r in rows:
        place, name = r["nTer"].strip(), str(r[cat]).strip()
        label = label_of(field, name)
        if label == "":
            unknown.add(name)
            continue
        if label is None:
            if fold(name).startswith(CHRISTIAN_SUBTOTAL):
                subtotal[place] += value(r)
            else:
                out[place][None] += value(r)
            continue
        out[place][label] += value(r)
    if unknown:
        raise SystemExit(f"serbia_census: {field} categories with no entry in LABELS: {sorted(unknown)}")
    for place, groups in out.items():
        check_sum(sum(v for k, v in groups.items() if k is not None), groups[None],
                  f"serbia_census: {field} of {place}")
        if field == "religion":
            check_sum(sum(groups.get(k, 0.0) for k in CHRISTIAN), subtotal[place],
                      f"serbia_census: Christians of {place}")
    log(f"  {field}: {len(out)} territories, {cat}")
    return out


def ages() -> dict[str, dict[str, Any]]:
    """{territory: {"groups": [(lower, width, n)], "men", "women", "total"}}."""
    rows = load(DATASETS["age"])
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "groups": Counter(), "by_sex": Counter(), "totals": Counter()})
    for r in rows:
        place, band, sex = r["nTer"].strip(), str(r["nStarGrupa"]).strip(), str(r["nPol"]).strip()
        unit = out[place]
        if band == "Ukupno":
            unit["totals"][sex] += value(r)
            continue
        m = re.match(r"^(\d+)\s*[–-]\s*(\d+)$", band)
        top = re.match(r"^(\d+)\s*(\+|i više)", band)
        if m:
            span = (float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1))
        elif top:
            span = (float(top.group(1)), None)
        elif re.search(r"\(\d+\+\)", band):
            continue           # "Punoletni (18+)": adults, beside the groups
        else:
            raise SystemExit(f"serbia_census: age group {band!r}")
        if sex == "Ukupno":
            unit["groups"][span] += value(r)
        else:
            unit["by_sex"][(sex, span)] += value(r)
    final: dict[str, dict[str, Any]] = {}
    for place, unit in out.items():
        total, men, women = (unit["totals"][s] for s in ("Ukupno", "Muško", "Žensko"))
        check_sum(sum(unit["groups"].values()), total, f"serbia_census: age groups of {place}")
        check_sum(men + women, total, f"serbia_census: sexes of {place}")
        final[place] = {"groups": [(lo, w, n) for (lo, w), n in sorted(unit["groups"].items(),
                                                                      key=lambda kv: kv[0][0])],
                        "men": men, "women": women, "total": total}
    log(f"  age: {len(final)} territories")
    return final


def cite(field: str) -> dict[str, Any]:
    dataset = DATASETS[field]
    return {"field": field if field != "age" else "population/median_age/sex_ratio",
            "name": SOURCE.format(title=TITLES[field], id=dataset), "url": API.format(id=dataset),
            "page": PAGE.format(sub=dataset[:10]), "year": YEAR, "license": LICENCE}


def comp_fields(comps: dict[str, dict[str, dict[str | None, float]]], place: str,
                total: float, extra: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in ("ethnicity", "religion", "language"):
        groups = comps[field][place]
        check_sum(groups[None], total, f"serbia_census: {field} total of {place} against its head count")
        out[field] = shares({k: v for k, v in groups.items() if k is not None and v}, total=groups[None])
        out[f"{field}_year"] = YEAR
        out[f"{field}_note"] = NOTES[field] + extra
    return out


def build() -> list[dict[str, Any]]:
    age = ages()
    comps = {f: compositions(f) for f in ("ethnicity", "religion", "language")}
    for field, table in comps.items():
        check_sum(table[COUNTRY][None], NATIONAL, f"serbia_census: {field}, the country")
    check_sum(age[COUNTRY]["total"], NATIONAL, "serbia_census: age, the country")
    by_key: dict[str, list[str]] = defaultdict(list)
    for place in age:
        by_key[key(place)].append(place)

    records = []
    # Second level: municipalities and cities, the five divided cities whole.
    admin1 = {s["id"]: s for s in shapes("SRB", "admin1")}
    admin2 = shapes("SRB", "admin2")
    bound: dict[str, str] = {}
    lost = []
    for shape in admin2:
        name = ALIASES.get(shape["name"], shape["name"])
        k = key(name)
        tries = (["grad" + k, k] if shape["name"].endswith(" City") else [k])
        hit = next((by_key[t] for t in tries if len(by_key.get(t, [])) == 1), None)
        if hit is None:
            lost.append(shape["name"])
            continue
        bound[shape["id"]] = hit[0]
    places = list(bound.values())
    if len(set(places)) != len(places):
        raise SystemExit(f"serbia_census: a territory on two polygons: "
                         f"{[p for p, n in Counter(places).items() if n > 1]}")
    if lost:
        raise SystemExit(f"serbia_census: polygons with no RZS territory: {lost}")
    check_sum(sum(age[p]["total"] for p in places), NATIONAL,
              "serbia_census: the bound municipalities against the country")
    log(f"  {len(bound)} second-level polygons bound one-to-one; they add to the country")
    by_area: dict[str, float] = defaultdict(float)
    note = ("Interpolated within the five-year age group that holds the middle person, from "
            "the census's population by age group and sex (3104020201IND01): RZS publishes "
            "single years of age by region only.")
    for shape in admin2:
        place = bound[shape["id"]]
        unit = age[place]
        by_area[shape["parent"]] += unit["total"]
        fields: dict[str, Any] = {"population": measure(int(unit["total"]), year=YEAR,
                                                        source=cite("age")["name"])}
        fields.update(age_fields(None, unit["men"], unit["women"], year=YEAR,
                                 source=cite("age")["name"], note=note, grouped=unit["groups"]))
        fields.update(comp_fields(comps, place, unit["total"]))
        records.append(record(
            f"SRB-2022-{fold(place)}", shape["name"], level="admin2", parent="SRB", country="SRB",
            parent_name=admin1[shape["parent"]]["name"], match_by="shape_id", shape_id=shape["id"],
            codes={"rzs": place},
            sources=[cite("age")] + [cite(f) for f in ("ethnicity", "religion", "language")],
            **fields))
    # First level: the districts and Belgrade, compositions only.
    for sid, shape in admin1.items():
        area = AREAS.get(shape["name"])
        if area is None or area not in age:
            raise SystemExit(f"serbia_census: no RZS area for the district {shape['name']!r}")
        total = age[area]["total"]
        if abs(by_area[sid] - total) > 0.5:
            log(f"  !! {shape['name']}: the map's municipalities in it add to {by_area[sid]:,.0f}, "
                f"RZS's {area} counts {total:,.0f}")
        records.append(record(
            f"SRB-2022-area-{fold(area)}", shape["name"], level="admin1", parent="SRB",
            country="SRB", match_by="shape_id", shape_id=sid, codes={"rzs": area},
            sources=[cite(f) for f in ("ethnicity", "religion", "language")],
            **comp_fields(comps, area, total)))
        log(f"  {shape['name']} ({area}): {total:,.0f}, municipalities "
            f"{by_area[sid]:,.0f}, median {grouped_median(age[area]['groups'])}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("serbia_census: RZS open data, 2022 census")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
