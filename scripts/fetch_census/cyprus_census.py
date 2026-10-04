#!/usr/bin/env python3
"""Cyprus: the 2021 census by district and community, from CYSTAT's database.

The Statistical Service of Cyprus (CYSTAT) publishes the Census of Population
and Housing 2021 (reference day 1 October 2021) in its PxWeb database
(cystatdb.cystat.gov.cy):

* 1891129E -- population by district, sex and single year of age (to 80+);
* 1891108E -- population by district, municipality/community, sex and
  five-year age group (to 80+);
* 1891616E -- population by language, sex and district.

So the districts take head count, median age (from single years), sex ratio
and language; the municipalities and communities take head count, sex ratio
and a median interpolated within the five-year group that holds the middle
person, which is the finest CYSTAT publishes for them.

**Where the census was taken.** The Republic's censuses since 1974 cover the
areas under the effective control of its Government. Kyrenia district lies
wholly outside them, so it and its communities have no figure here, and say
why. Nicosia and Famagusta districts lie partly outside them: the district
figures are those of the part the census covered, and say so. Every polygon
with no CYSTAT community says why, and its population marker carries
``displaces_before`` (1974), so that where the build honours it Wikidata's
1973 counts for the communities outside the census stop standing in for a
figure.

**Binding.** A community goes on the polygon of its name in its district, or
across a district line where the name is unique in the country (Ormideia and
Xylofagou, Larnaca communities the boundary file files under Famagusta); the
records and the district rows say where the map's districts and CYSTAT's
part. Where the file draws a name twice, the community is pinned to the
polygon holding its village (``PINNED``); the polygon labelled Sia holds Sia
and Kornos and carries both (``SUMMED``); Pano and Kato Koutrafas, whose
labels the file swaps, are left off (``SWAPPED``). Each was measured against
GeoNames' and Wikidata's points for the villages. A community of fewer than
50 residents has no median or sex ratio shown.

**What is not here.** CYSTAT publishes the 2021 census's religion and
ethnic/religious group for the whole country only -- by citizenship group
(1891632E, 1891642E) and country of birth (1891635E) -- and nothing of either
by district; the 2011 census's tables in the same database (1862010E-1862030E)
carry neither. The districts' religion and ethnicity are therefore stated
gaps, not readings.

Usage:
    python -m scripts.fetch_census.cyprus_census
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .balkans_common import age_fields, check_sum, fold, px_meta, px_table, shapes
from .redatam import median_age

OUT = "cyprus_census.json"
YEAR = 2021
# cystatdb23px answers a GET itself and moves a POST (301) to cystatdb, and
# urllib follows a moved POST as a GET -- which returns the table's metadata
# instead of its data. So the tables are asked for at cystatdb directly.
BASE = ("https://cystatdb.cystat.gov.cy/api/v1/en/8.CYSTAT-DB/Population/"
        "Census%20of%20Population%20and%20Housing%202021/Population/")
TABLES = {
    "single": BASE + "Population%20-%20Place%20of%20Residence/1891129E.px",
    "community": BASE + "Population%20-%20Place%20of%20Residence/1891108E.px",
    "language": BASE + "Population%20-%20Language%2C%20Religion%2C%20Ethnic%20Religious%20Group/1891616E.px",
}
TITLES = {
    "single": "population enumerated by district, sex and single year of age (1891129E)",
    "community": ("population enumerated by district, municipality/community, sex and age "
                  "(1891108E)"),
    "language": "population enumerated by language, sex and district (1891616E)",
}
PAGE = "https://cystatdb23px.cystat.gov.cy/pxweb/en/8.CYSTAT-DB/"
SOURCE = "Statistical Service of Cyprus (CYSTAT), Census of Population and Housing 2021, {title}"
LICENCE = "Statistical Service of Cyprus (reuse with attribution)"
# The map's districts -> CYSTAT's (folded; the tables spell Lefkosia three ways).
DISTRICTS = {"Nicosia": "lefkosia", "Famagusta": "ammochostos", "Larnaca": "larnaka",
             "Limassol": "lemesos", "Paphos": "pafos"}
PARTLY = {"Nicosia", "Famagusta"}
OUTSIDE = "Kyrenia"
LANGUAGES = {
    "greek": "Greek", "english": "English", "russian": "Russian", "arabic": "Arabic",
    "romanian": "Romanian", "bulgarian": "Bulgarian", "filipino": "Filipino",
    "ukranian": "Ukrainian", "ukrainian": "Ukrainian", "georgian": "Georgian",
    "nepalese": "Nepali", "french": "French", "vietnamese": "Vietnamese", "german": "German",
    "chinese": "Chinese", "polish": "Polish", "turkish": "Turkish", "persian": "Persian",
    "armenian": "Armenian", "hebrew": "Hebrew", "italian": "Italian", "latvian": "Latvian",
    "slovakian": "Slovak", "moldovian": "Moldovan", "bengali": "Bengali", "spanish": "Spanish",
    "swedish": "Swedish", "hungarian": "Hungarian", "urdu": "Urdu", "dutch": "Dutch",
    # Rows that name a country rather than a language: shown within Other.
    "indian": "Other", "srilankan": "Other", "yugoslavian": "Other",
    "otherlanguages": "Other", "notstated": "Not stated",
}
# CYSTAT's spelling -> the boundary file's, where they differ by more than
# the district suffix or a parenthesis; each checked against the polygon's
# district.
ALIASES = {"Agios Georgios Kafkallou": "Agios Georgios Kafkaliou",
           "Agios Theodoros Tillirias": "Agios Theodoros Tillrias",
           "Agioi Vavatsinias": "Agloi Vavatsinias",
           "Agia Marina Kelokedaron": "Ayia Marina Kelokedharon",
           "Chlorakas": "Chloraka", "Pafos": "Paphos",
           "Livadia Lefkosias": "Livadia Lefosias", "Moutoullas": "Moutoulias",
           "Kalopanagiotis": "Kalapanagiotis", "Tremithousa": "Trimithousa"}
# Communities CYSTAT counts as one that the boundary file draws as the parts
# they were formed from. The figure goes on the first part's polygon only
# once the parts are drawn as one (make_redrawn merges them under its id),
# never on a part while the others are still drawn beside it.
MERGED = {"Dromolaxia - Meneou": ("Dromolaxia", "Meneou")}
# Communities whose name the boundary file draws twice, bound to the polygon
# that holds the village (GeoNames' and Wikidata's points agree). The other
# "Katydata" holds Agios Georgios (Lefkas); the other "Trimithousa" is the
# Trimithousa of the Chrysochou area (Wikidata Q7842235), a village apart from
# CYSTAT's Tremithousa near Paphos (Q7838121).
PINNED = {"Katydata": "46923920B11980221307495", "Tremithousa": "46923920B17841566161623"}
OTHER_OF_NAME = {
    "46923920B20193016295799": (
        "One of two polygons the boundary file labels Katydata. CYSTAT's Katydata (1416) is on the "
        "other, which holds the village; this one holds Agios Georgios (Lefkas), by GeoNames, a "
        "community CYSTAT's 2021 census does not list."),
    "46923920B86597490798508": (
        "The Trimithousa of the Chrysochou area (Wikidata Q7842235), a village apart from CYSTAT's "
        "Tremithousa near Paphos (6023), which is on the other polygon of the name. CYSTAT's 2021 "
        "census lists no community of this one's."),
}
# A polygon that is two communities: (its label, its map district) -> the
# CYSTAT communities summed onto it. "Sia" (47.7 km2, filed under Larnaca)
# holds the villages of both Sia (Nicosia district) and Kornos (Larnaca), by
# GeoNames' and Wikidata's points, and the map draws no Kornos.
SUMMED = {("Sia", "Larnaca"): ("Sia", "Kornos")}
# Two neighbours whose labels the boundary file swaps: GeoNames and Wikidata
# both put each village 0.6-1 km inside the other's polygon. Neither figure is
# put on either.
SWAPPED = ("Pano Koutrafas", "Kato Koutrafas")
# Communities the map does not draw, inside the polygon of the one named:
# GeoNames' Anthoupoli (Archangelos-Anthoupoli) lies in Lakatameia's, its
# Troodos in Pano Platres's.
HOLDS = {"Lakatameia": "Synoikismos Anthoupolis", "Pano Platres": "Troodos"}
# Communities CYSTAT lists with no residents because the part of them under
# the Government's control is empty, while the village itself lies beyond it
# and is counted by the census taken in the north in 2011 (cyprus_north_census,
# which writes its figure once this file leaves a gap there). Their 0 is not
# the village's population, so the polygon gets a statement instead: by code,
# the village's name in that census.
COUNTED_IN_THE_NORTH = {"1110": "Akıncılar", "1350": "Yukarı Bostancı"}
# Below this many residents a community's median age and sex ratio are not
# shown: 19 people with 18 men read as a ratio of 1,800.
MIN_RESIDENTS = 50
# The year before which an encyclopaedia's head count for a polygon this file
# says the census does not reach is displaced by the statement (the build's
# ``displaces_before``): the Republic's last census of the whole island was
# 1973's.
DISPLACES_BEFORE = 1974
SUFFIXES = ("lefkosias", "lemesou", "larnakas", "pafou", "ammochostou", "keryneias", "municipality")
WHY_OUTSIDE = ("Kyrenia district has been outside the effective control of the Government of the "
               "Republic of Cyprus since 1974. The Republic's censuses since then, the 2021 census "
               "included, were taken only in the areas under its control, so none counts it.")
WHY_RELIGION = ("CYSTAT publishes the 2021 census's religion for the whole country only, by "
                "citizenship group (1891632E) and country of birth (1891635E); its database has no "
                "table of religion by district, and the 2011 census's tables there carry none.")
WHY_ETHNICITY = ("CYSTAT publishes the 2021 census's ethnic/religious group for the whole country "
                 "only, by citizenship group (1891642E); its database has no table of it by "
                 "district, and the 2011 census's tables there carry none.")
WHY_COMMUNITY = ("CYSTAT publishes the 2021 census's language by district only, and its religion "
                 "and ethnic/religious group for the whole country only (1891616E, 1891632E, "
                 "1891642E); no table of any of the three is published by municipality or "
                 "community.")
PART_NOTE = ("Counts the part of the district under the effective control of the Government of "
             "the Republic of Cyprus, where the 2021 census was taken; it was not taken in the rest.")


def var(meta: dict[str, dict[str, Any]], word: str) -> str:
    hits = [c for c in meta if word in c.upper()]
    if len(hits) != 1:
        raise SystemExit(f"cyprus_census: no single variable like {word!r} in {list(meta)}")
    return hits[0]


def total_code(meta_var: dict[str, Any]) -> str:
    hits = [c for c, t in zip(meta_var["values"], meta_var["valueTexts"]) if t.strip().lower() == "total"]
    if len(hits) != 1:
        raise SystemExit(f"cyprus_census: no single Total in {meta_var['valueTexts'][:10]}")
    return hits[0]


def district_key(text: str) -> str:
    """'LEFKOSIA DISTRICT', 'Lekfosia', 'Lefkosia' -> 'lefkosia'."""
    f = fold(re.sub(r"\s+DISTRICT$", "", text.strip(), flags=re.I))
    return {"lekfosia": "lefkosia"}.get(f, f)


def keys(name: str) -> list[str]:
    """The folded forms a community's name may take, most exact first."""
    out = []
    name = ALIASES.get(name, name)
    bare = re.sub(r"\s*\([^)]*\)", "", name).strip()     # "Voroklini (Oroklini)"
    forms = [name, bare] + [p for p in re.split(r"\s+or\s+", bare) if p != bare]
    for part in forms:
        f = fold(part)
        out.append(f)
        bare = f
        for s in SUFFIXES:
            if bare.endswith(s) and len(bare) > len(s):
                bare = bare[:-len(s)]
        out.append(bare)
    return list(dict.fromkeys(out))


def sex_of(label: str) -> str:
    t = label.strip().lower()
    return {"total": "total", "males": "men", "females": "women"}[t]


def single_years() -> dict[str, dict[str, Any]]:
    """{district key or 'total': {"ages": Counter, "men", "women", "total"}}."""
    meta = px_meta(TABLES["single"])
    dist, sex, age = var(meta, "DISTRICT"), var(meta, "SEX"), var(meta, "AGE")
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"ages": Counter(), "men": 0.0,
                                                          "women": 0.0, "total": 0.0})
    for dims, value in px_table(TABLES["single"], {dist: "*", sex: "*", age: "*"}):
        place = district_key(dims[dist][1])
        who, label = sex_of(dims[sex][1]), dims[age][1].strip()
        unit = out[place]
        if label.lower() == "total":
            unit[who] = value
            continue
        if who != "total":
            continue
        m = re.match(r"^(\d+)\s*\+?$", label)
        if not m:
            raise SystemExit(f"cyprus_census: single age {label!r}")
        unit["ages"][int(m.group(1))] += value
    for place, unit in out.items():
        check_sum(sum(unit["ages"].values()), unit["total"], f"cyprus_census: ages of {place}")
        check_sum(unit["men"] + unit["women"], unit["total"], f"cyprus_census: sexes of {place}")
    return out


def communities() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """({code: unit}, {district key: unit}) from 1891108E; each unit carries its
    name, district, five-year groups, men, women and total."""
    meta = px_meta(TABLES["community"])
    place_var, sex, age = var(meta, "MUNICIPALITY"), var(meta, "SEX"), var(meta, "AGE")
    names = dict(zip(meta[place_var]["values"], meta[place_var]["valueTexts"]))
    units: dict[str, dict[str, Any]] = defaultdict(lambda: {"groups": Counter(), "men": 0.0,
                                                            "women": 0.0, "total": 0.0})
    for dims, value in px_table(TABLES["community"], {place_var: "*", sex: "*", age: "*"}):
        code, who, label = dims[place_var][0], sex_of(dims[sex][1]), dims[age][1].strip()
        unit = units[code]
        if label.lower() == "total":
            unit[who] = value
            continue
        if who != "total":
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", label)
        top = re.match(r"^(\d+)\s*\+$", label)
        if m:
            unit["groups"][(float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1))] += value
        elif top:
            unit["groups"][(float(top.group(1)), None)] += value
        else:
            raise SystemExit(f"cyprus_census: age group {label!r}")
    districts: dict[str, dict[str, Any]] = {}
    by_district_code: dict[str, str] = {}
    for code, text in names.items():
        if text.strip().upper().endswith("DISTRICT"):
            by_district_code[code] = district_key(text)
    comms: dict[str, dict[str, Any]] = {}
    for code, unit in units.items():
        check_sum(sum(unit["groups"].values()), unit["total"], f"cyprus_census: ages of {names[code]}")
        check_sum(unit["men"] + unit["women"], unit["total"], f"cyprus_census: sexes of {names[code]}")
        unit["name"] = names[code].strip()
        if code in by_district_code:
            districts[by_district_code[code]] = unit
        elif code.upper() == "TOTAL":
            districts["total"] = unit
        else:
            # A community's code opens with its district's.
            dcode = next((d for d in by_district_code if code.startswith(d) and len(code) == 4), None)
            if dcode is None:
                raise SystemExit(f"cyprus_census: no district for {code} {names[code]}")
            unit["district"] = by_district_code[dcode]
            comms[code] = unit
    for d, whole in districts.items():
        if d == "total":
            continue
        check_sum(sum(u["total"] for u in comms.values() if u["district"] == d), whole["total"],
                  f"cyprus_census: communities of {d}")
    check_sum(sum(w["total"] for d, w in districts.items() if d != "total"),
              districts["total"]["total"], "cyprus_census: districts against the country")
    return comms, districts


def languages() -> dict[str, dict[str | None, float]]:
    meta = px_meta(TABLES["language"])
    dist, sex, lang = var(meta, "DISTRICT"), var(meta, "SEX"), var(meta, "LANGUAGE")
    out: dict[str, dict[str | None, float]] = defaultdict(lambda: defaultdict(float))
    unknown = set()
    for dims, value in px_table(TABLES["language"], {dist: "*", sex: [total_code(meta[sex])],
                                                     lang: "*"}):
        place, label = district_key(dims[dist][1]), dims[lang][1].strip()
        if label.lower() == "total":
            out[place][None] += value
            continue
        name = LANGUAGES.get(fold(label))
        if name is None:
            unknown.add(label)
            continue
        out[place][name] += value
    if unknown:
        raise SystemExit(f"cyprus_census: languages with no label: {sorted(unknown)}")
    for place, groups in out.items():
        check_sum(sum(v for k, v in groups.items() if k is not None), groups[None],
                  f"cyprus_census: languages of {place}")
    return out


NATIONAL_TABLES = {
    "religion": BASE + "Population%20-%20Language%2C%20Religion%2C%20Ethnic%20Religious%20Group/1891632E.px",
    "ethnicity": BASE + "Population%20-%20Language%2C%20Religion%2C%20Ethnic%20Religious%20Group/1891642E.px",
}


def national() -> None:
    """The country's religion and ethnic/religious group, which CYSTAT
    publishes for the whole country only: printed for a curated country row,
    not written to any unit."""
    import json
    for field, url in NATIONAL_TABLES.items():
        meta = px_meta(url)
        sex, cit = var(meta, "SEX"), var(meta, "CITIZENSHIP")
        group = next(c for c in meta if c not in (sex, cit))
        counts: dict[str, float] = {}
        whole = 0.0
        for dims, value in px_table(url, {sex: [total_code(meta[sex])], cit: [total_code(meta[cit])],
                                          group: "*"}):
            label = re.sub(r"\s*\(\d+\)\s*$", "", dims[group][1].strip())
            if label.lower() == "total":
                whole = value
            else:
                counts[label] = counts.get(label, 0.0) + value
        check_sum(sum(counts.values()), whole, f"cyprus_census: national {field}")
        log(f"  CURATED {field} {int(whole)} " + json.dumps(
            shares({k: v for k, v in counts.items() if v}, total=whole), ensure_ascii=False))


def cite(table: str, field: str) -> dict[str, Any]:
    return {"field": field, "name": SOURCE.format(title=TITLES[table]), "url": TABLES[table],
            "page": PAGE, "year": YEAR, "license": LICENCE}


def build() -> list[dict[str, Any]]:
    single = single_years()
    comms, districts = communities()
    langs = languages()
    country = districts["total"]["total"]
    check_sum(single["total"]["total"], country, "cyprus_census: the two age tables, the country")
    log(f"  Cyprus (areas under Government control): {country:,.0f} residents, median "
        f"{median_age(single['total']['ages'])} from single years; {len(comms)} municipalities "
        "and communities")

    admin1 = {s["name"]: s for s in shapes("CYP", "admin1")}
    admin2 = shapes("CYP", "admin2")
    records = []
    src = {k: SOURCE.format(title=v) for k, v in TITLES.items()}
    one = ("Interpolated within the single year of age that holds the middle person, from the "
           "census's population by single year of age and sex (1891129E).")
    five = ("Interpolated within the five-year age group that holds the middle person, from the "
            "census's population by community, sex and age group (1891108E): CYSTAT publishes "
            "nothing finer by community.")
    lang_note = ("Language, 2021 census, resident population, one language per person as "
                 "CYSTAT's table 1891616E counts it. The table's rows 'Indian', 'Sri Lankan' and "
                 "'Yugoslavian', which name a country rather than a language, are shown within "
                 "Other; 'Not stated' is its own bar.")
    for name, shape in admin1.items():
        if name == OUTSIDE:
            records.append(record(
                f"CYP-2021-{fold(name)}", name, level="admin1", parent="CYP", country="CYP",
                match_by="shape_id", shape_id=shape["id"],
                population=dict(gap(NOT_AVAILABLE, WHY_OUTSIDE), displaces_before=DISPLACES_BEFORE),
                median_age=gap(NOT_AVAILABLE, WHY_OUTSIDE),
                sex_ratio=gap(NOT_AVAILABLE, WHY_OUTSIDE), religion=gap(NOT_AVAILABLE, WHY_OUTSIDE),
                language=gap(NOT_AVAILABLE, WHY_OUTSIDE), ethnicity=gap(NOT_AVAILABLE, WHY_OUTSIDE)))
            continue
        d = DISTRICTS.get(name)
        if d is None or d not in single or d not in districts or d not in langs:
            raise SystemExit(f"cyprus_census: no CYSTAT district for {name!r}")
        unit = single[d]
        check_sum(unit["total"], districts[d]["total"], f"cyprus_census: the two age tables, {name}")
        check_sum(langs[d][None], unit["total"], f"cyprus_census: the language table, {name}")
        fields: dict[str, Any] = {"population": measure(int(unit["total"]), year=YEAR, source=src["single"])}
        if name in PARTLY:
            fields["population_note"] = PART_NOTE
        fields.update(age_fields(unit["ages"], unit["men"], unit["women"], year=YEAR,
                                 source=src["single"], note=one + (" " + PART_NOTE if name in PARTLY else "")))
        fields["language"] = shares({k: v for k, v in langs[d].items() if k is not None and v},
                                    total=langs[d][None])
        fields["language_year"] = YEAR
        fields["language_note"] = lang_note + (" " + PART_NOTE if name in PARTLY else "")
        fields["religion"] = gap(NOT_AVAILABLE, WHY_RELIGION)
        fields["ethnicity"] = gap(NOT_AVAILABLE, WHY_ETHNICITY)
        records.append(record(
            f"CYP-2021-{fold(name)}", name, level="admin1", parent="CYP", country="CYP",
            match_by="shape_id", shape_id=shape["id"], codes={"cystat": d},
            sources=[cite("single", "population/median_age/sex_ratio"), cite("language", "language")],
            **fields))
        log(f"  {name}: {unit['total']:,.0f}, median {fields['median_age']['value']}, "
            f"{fields['sex_ratio']['value']} men per 100 women")

    # Second level: bind each CYSTAT community to the map's polygon of that
    # name within the same district, one-to-one.
    district_of = {s["id"]: s["name"] for s in admin1.values()}
    by_id = {s["id"]: s for s in admin2}
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in admin2:
        dname = district_of.get(s["parent"], "")
        for k in keys(s["name"]):
            by_key[(dname, k)].append(s)
    rev = {v: k for k, v in DISTRICTS.items()}
    bound: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    lost: list[str] = []
    across: list[tuple[str, str, str]] = []           # (community code, its district, the map's)
    why_not: dict[str, str] = {}                      # polygon id -> why it has no community
    drawn = {fold(s["name"]) for s in admin2}
    name_code = {unit["name"]: code for code, unit in comms.items()}
    summed_codes = {name_code[n]: label for label, names in SUMMED.items() for n in names
                    if n in name_code}
    for label, names in SUMMED.items():
        if any(n not in name_code for n in names):
            raise SystemExit(f"cyprus_census: SUMMED names {names}, not all in CYSTAT's table")
    for code, unit in sorted(comms.items()):
        dname = rev[unit["district"]]
        if code in summed_codes:
            continue                                  # summed onto one polygon below
        if unit["name"] in SWAPPED:
            lost.append(f"{unit['name']} ({code}, {dname}, {unit['total']:,.0f}): its polygon's label "
                        "is swapped with its neighbour's")
            continue
        hit = None
        if unit["name"] in PINNED:
            hit = by_id.get(PINNED[unit["name"]])
            if hit is None or not set(keys(hit["name"])) & set(keys(unit["name"])):
                raise SystemExit(f"cyprus_census: PINNED sends {unit['name']} to "
                                 f"{PINNED[unit['name']]}, which is {hit and hit['name']!r}")
            bound[code] = hit
            used.add(hit["id"])
            continue
        parts = MERGED.get(unit["name"])
        if parts:
            if any(fold(p) in drawn for p in parts[1:]):
                lost.append(f"{unit['name']} ({code}, {dname}, {unit['total']:,.0f}): drawn as "
                            f"its parts {list(parts)}, which make_redrawn is to merge")
                for s in admin2:
                    if fold(s["name"]) in {fold(p) for p in parts}:
                        why_not[s["id"]] = (
                            f"CYSTAT's 2021 census counts {unit['name']} ({code}) as one community of "
                            f"{unit['total']:,.0f} residents, which the boundary file draws as "
                            f"{' and '.join(parts)}; its figures go on them once they are drawn as one.")
                continue
            unit = dict(unit, name=parts[0])
        for k in keys(unit["name"]):
            cands = [s for s in by_key.get((dname, k), []) if s["id"] not in used]
            if len({s["id"] for s in by_key.get((dname, k), [])}) == 1 and cands:
                hit = cands[0]
                break
        if hit is None:
            # The boundary file files a few communities under the district
            # next door (Ormideia, Xylofagou): a name the whole country has
            # once, on both sides, is the same place.
            for k in keys(unit["name"]):
                cands = {s["id"]: s for (d, kk), ss in by_key.items() if kk == k for s in ss}
                same = [c for c in comms.values() if k in keys(c["name"])]
                if len(cands) == 1 and len(same) == 1 and next(iter(cands)) not in used:
                    hit = next(iter(cands.values()))
                    break
        if hit is None:
            lost.append(f"{unit['name']} ({code}, {dname}, {unit['total']:,.0f})")
            continue
        bound[code] = hit
        used.add(hit["id"])
    # Polygons that are two communities: the sum of both.
    pooled: dict[str, dict[str, Any]] = {}
    for (label, dname), names in SUMMED.items():
        hits = [s for s in admin2 if s["name"] == label and district_of.get(s["parent"]) == dname]
        if len(hits) != 1 or hits[0]["id"] in used:
            raise SystemExit(f"cyprus_census: no single free polygon {label!r} in {dname}")
        codes = [name_code[n] for n in names]
        unit = {"name": " and ".join(names), "district": None, "groups": Counter(), "men": 0.0,
                "women": 0.0, "total": 0.0, "codes": codes}
        for c in codes:
            unit["groups"].update(comms[c]["groups"])
            for k in ("men", "women", "total"):
                unit[k] += comms[c][k]
        key = "+".join(codes)
        pooled[key] = unit
        bound[key] = hits[0]
        used.add(hits[0]["id"])
    for code, shape in bound.items():
        for c in pooled[code]["codes"] if code in pooled else [code]:
            theirs, drawn_in = rev[comms[c]["district"]], district_of.get(shape["parent"], "?")
            if theirs != drawn_in:
                across.append((c, theirs, drawn_in))
    lost_people = sum(comms[c]["total"] for c in comms
                      if c not in bound and not any(c in u["codes"] for u in pooled.values()))
    log(f"  drawn across a district line: {[(comms[c]['name'], t, m) for c, t, m in across]}")
    log(f"  {len(comms) - len(lost)} of {len(comms)} CYSTAT communities bound "
        f"({len(pooled)} polygon(s) carrying two); {len(lost)} unbound ({lost_people:,.0f} people): {lost}")

    # The districts say which communities the map draws across their lines:
    # CYSTAT's district figure is its own district's, and the polygon is not.
    for rec in records:
        if rec["level"] != "admin1" or rec["name"] == OUTSIDE:
            continue
        name = rec["name"]
        out_of = [c for c, t, m in across if t == name]
        into = [c for c, t, m in across if m == name]
        if not (out_of or into):
            continue
        words = []
        if out_of:
            words.append(f"includes {listing(comms, out_of)}, which the boundary file draws in "
                         f"{' and '.join(sorted({m for c, t, m in across if t == name}))}")
        if into:
            words.append(f"leaves out {listing(comms, into)}, which CYSTAT counts in "
                         f"{' and '.join(sorted({t for c, t, m in across if m == name}))} and the "
                         "boundary file draws inside this district")
        rec["population_note"] = " ".join(filter(None, [
            rec.get("population_note"),
            f"CYSTAT's figure for {name} district " + "; and it ".join(words) + "."]))

    # The villages the map does not draw, inside the polygon of another.
    inside_note: dict[str, str] = {}
    for host, guest in HOLDS.items():
        code = name_code.get(guest)
        if code and code not in bound:
            inside_note[host] = (f"The polygon also holds {guest} ({comms[code]['total']:,.0f} residents), "
                                 "which CYSTAT counts as a community of its own and the map does not "
                                 "draw; its people are not in this figure.")
    for code, shape in bound.items():
        unit = pooled.get(code) or comms[code]
        if code in COUNTED_IN_THE_NORTH and not unit["total"]:
            why = (f"CYSTAT's 2021 census lists {unit['name']} ({code}) with no residents: the part "
                   "of the community under the effective control of the Government of the Republic "
                   f"of Cyprus is empty, and the village ({COUNTED_IN_THE_NORTH[code]}) lies outside "
                   "it, where the Republic's censuses since 1974 have not been taken.")
            records.append(record(
                f"CYP-2021-{code}", shape["name"], level="admin2", parent="CYP", country="CYP",
                match_by="shape_id", shape_id=shape["id"], codes={"cystat": code},
                parent_name=district_of.get(shape["parent"]),
                population=dict(gap(NOT_AVAILABLE, why), displaces_before=DISPLACES_BEFORE),
                median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
                religion=gap(NOT_AVAILABLE, WHY_COMMUNITY), language=gap(NOT_AVAILABLE, WHY_COMMUNITY),
                ethnicity=gap(NOT_AVAILABLE, WHY_COMMUNITY)))
            continue
        fields = {"population": measure(int(unit["total"]), year=YEAR, source=src["community"])}
        notes = []
        if code in pooled:
            parts = [comms[c] for c in unit["codes"]]
            notes.append(
                f"The boundary file draws {' and '.join(p['name'] for p in parts)} as one polygon, "
                f"labelled {shape['name']!r}: it holds both villages, by GeoNames' and Wikidata's points, "
                f"and no polygon is drawn for {parts[-1]['name']}. It carries their sum ("
                + ", ".join(f"{p['name']} {p['total']:,.0f}, {rev[p['district']]} district" for p in parts)
                + ").")
        for c, theirs, drawn_in in across:
            if c == code or (code in pooled and c in unit["codes"]):
                notes.append(f"CYSTAT counts {comms[c]['name']} in {theirs} district; the boundary file "
                             f"draws it in {drawn_in}.")
        if shape["name"] in inside_note:
            notes.append(inside_note[shape["name"]])
        if notes:
            fields["population_note"] = " ".join(notes)
        grouped = [(lo, w, n) for (lo, w), n in unit["groups"].items()]
        old = sum(n for lo, w, n in grouped if w is None)
        if 0 < unit["total"] < MIN_RESIDENTS:
            few = gap(NOT_AVAILABLE, (
                f"The 2021 census counts {count_of(unit['total'], 'resident')} here ({count_of(unit['men'], 'man', 'men')} "
                f"and {count_of(unit['women'], 'woman', 'women')}); below {MIN_RESIDENTS} residents a median "
                "age and a ratio of men to women describe a handful of people, and are not shown."))
            fields.update(median_age=few, sex_ratio=few)
        elif unit["total"] > 0 and old >= unit["total"] / 2:
            # Half its people or more are in the open top group (80 and over):
            # the median is somewhere above 80 and cannot be placed.
            fields.update(age_fields(None, unit["men"], unit["women"], year=YEAR,
                                     source=src["community"], note=five, grouped=[]))
            fields["median_age"] = gap(NOT_AVAILABLE, (
                f"{old:,.0f} of the community's {unit['total']:,.0f} residents are 80 or over, "
                "the census table's open top age group, so the median lies somewhere above 80 "
                "and cannot be interpolated."))
            fields.pop("median_age_note", None)
        elif unit["total"] > 0:
            fields.update(age_fields(None, unit["men"], unit["women"], year=YEAR,
                                     source=src["community"], note=five, grouped=grouped))
        else:
            empty = gap(NOT_AVAILABLE, "The 2021 census counts no residents in this community, "
                                       "so it has no median age or sex ratio.")
            fields.update(median_age=empty, sex_ratio=empty)
        if unit["total"] >= MIN_RESIDENTS and not unit["women"]:
            fields["sex_ratio"] = gap(NOT_AVAILABLE, (
                f"The 2021 census counts {count_of(unit['men'], 'man', 'men')} and no women in this "
                "community, so a ratio of men to women is not defined."))
        elif unit["total"] >= MIN_RESIDENTS and isinstance(fields.get("sex_ratio"), dict) \
                and fields["sex_ratio"].get("value") is not None \
                and not 70 <= fields["sex_ratio"]["value"] <= 140:
            fields["sex_ratio_note"] = (
                f"As the census counts it: {count_of(unit['men'], 'man', 'men')} and "
                f"{count_of(unit['women'], 'woman', 'women')}.")
        records.append(record(
            f"CYP-2021-{code}", shape["name"], level="admin2", parent="CYP", country="CYP",
            match_by="shape_id", shape_id=shape["id"],
            codes={"cystat": code if code not in pooled else unit["codes"]},
            parent_name=district_of.get(shape["parent"]),
            religion=gap(NOT_AVAILABLE, WHY_COMMUNITY), language=gap(NOT_AVAILABLE, WHY_COMMUNITY),
            ethnicity=gap(NOT_AVAILABLE, WHY_COMMUNITY),
            sources=[cite("community", "population/median_age/sex_ratio")], **fields))

    # Every other polygon says why it has no figure. Its population marker
    # displaces an encyclopaedia's figure from before 1974 (Wikidata's 1973
    # counts for the communities the Republic's censuses have not reached
    # since), where the build honours ``displaces_before``.
    swapped_ids = {s["id"] for s in admin2 if s["name"] in SWAPPED}
    for sid in swapped_ids:
        why_not[sid] = (
            "The boundary file's labels for Pano and Kato Koutrafas are swapped: GeoNames and Wikidata "
            "both put the village of Pano Koutrafas inside the polygon labelled Kato Koutrafas and "
            "Kato Koutrafas inside the one labelled Pano Koutrafas. CYSTAT counts "
            + " and ".join(f"{comms[name_code[n]]['name']} {comms[name_code[n]]['total']:,.0f}"
                           for n in SWAPPED if n in name_code)
            + " residents; neither figure is put on a polygon that may be the other village.")
    for s in admin2:
        dname = district_of.get(s["parent"], "")
        if s["id"] in used:
            continue
        if dname == OUTSIDE:
            why = WHY_OUTSIDE
        elif s["id"] in why_not:
            why = why_not[s["id"]]
        elif s["id"] in OTHER_OF_NAME:
            why = OTHER_OF_NAME[s["id"]]
        else:
            why = (f"CYSTAT's 2021 census (table 1891108E) lists no municipality or community of this "
                   f"name in {dname} district. The Republic's censuses since 1974 have been taken only "
                   "in the areas under the effective control of its Government, and name each "
                   "community they count; this is not one of them.")
        pop = dict(gap(NOT_AVAILABLE, why), displaces_before=DISPLACES_BEFORE)
        records.append(record(
            f"CYP-2021-{'outside' if dname == OUTSIDE else 'none'}-{s['id']}", s["name"], level="admin2",
            parent="CYP", country="CYP", match_by="shape_id", shape_id=s["id"], parent_name=dname,
            population=pop, median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
            religion=gap(NOT_AVAILABLE, why), language=gap(NOT_AVAILABLE, why),
            ethnicity=gap(NOT_AVAILABLE, why)))
    log(f"  {sum(1 for s in admin2 if s['id'] not in used and district_of.get(s['parent']) != OUTSIDE)} "
        "polygons outside Kyrenia with no community say why")
    return records


def count_of(n: float, one: str, many: str | None = None) -> str:
    """'1 man', '2 men', '0 women'."""
    return f"{n:,.0f} {one if round(n) == 1 else (many or one + 's')}"


def listing(comms: dict[str, dict[str, Any]], codes: list[str]) -> str:
    people = sum(comms[c]["total"] for c in codes)
    names = [comms[c]["name"] for c in codes]
    return (" and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)
            + f" ({people:,.0f} people)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("cyprus_census: CYSTAT, Census of Population and Housing 2021")
    records = build()
    national()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
