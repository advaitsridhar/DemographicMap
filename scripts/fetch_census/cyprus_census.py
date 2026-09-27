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
figures are those of the part the census covered, and say so. The map's
communities in the areas the census did not reach find no CYSTAT row and are
left as they are.

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
           "Kalopanagiotis": "Kalapanagiotis"}
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
                population=gap(NOT_AVAILABLE, WHY_OUTSIDE), median_age=gap(NOT_AVAILABLE, WHY_OUTSIDE),
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
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in admin2:
        dname = district_of.get(s["parent"], "")
        for k in keys(s["name"]):
            by_key[(dname, k)].append(s)
    rev = {v: k for k, v in DISTRICTS.items()}
    bound: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    lost: list[str] = []
    across: list[str] = []
    for code, unit in sorted(comms.items()):
        dname = rev[unit["district"]]
        hit = None
        for k in keys(unit["name"]):
            cands = [s for s in by_key.get((dname, k), []) if s["id"] not in used]
            if len({s["id"] for s in by_key.get((dname, k), [])}) == 1 and cands:
                hit = cands[0]
                break
        if hit is None:
            # The boundary file files a few communities under the district
            # next door (Sia, Ormideia, Xylofagou): a name the whole country
            # has once, on both sides, is the same place.
            for k in keys(unit["name"]):
                cands = {s["id"]: s for (d, kk), ss in by_key.items() if kk == k for s in ss}
                same = [c for c in comms.values() if k in keys(c["name"])]
                if len(cands) == 1 and len(same) == 1 and next(iter(cands)) not in used:
                    hit = next(iter(cands.values()))
                    across.append(f"{unit['name']} ({dname}) on {hit['name']} "
                                  f"({district_of.get(hit['parent'], '?')})")
                    break
        if hit is None:
            lost.append(f"{unit['name']} ({code}, {dname}, {unit['total']:,.0f})")
            continue
        bound[code] = hit
        used.add(hit["id"])
    lost_people = sum(comms[c]["total"] for c in comms if c not in bound)
    log(f"  bound across a district line, by a name unique in the country: {across}")
    log(f"  {len(bound)} of {len(comms)} CYSTAT communities bound; {len(lost)} unbound "
        f"({lost_people:,.0f} people): {lost}")
    spare = [f"{s['name']} ({district_of.get(s['parent'], '?')})" for s in admin2
             if s["id"] not in used and district_of.get(s["parent"]) != OUTSIDE]
    log(f"  {len(spare)} polygons outside Kyrenia with no CYSTAT community: {spare}")
    for code, shape in bound.items():
        unit = comms[code]
        fields = {"population": measure(int(unit["total"]), year=YEAR, source=src["community"])}
        if unit["total"] > 0:
            fields.update(age_fields(None, unit["men"], unit["women"], year=YEAR,
                                     source=src["community"], note=five,
                                     grouped=[(lo, w, n) for (lo, w), n in unit["groups"].items()]))
        records.append(record(
            f"CYP-2021-{code}", shape["name"], level="admin2", parent="CYP", country="CYP",
            match_by="shape_id", shape_id=shape["id"], codes={"cystat": code},
            parent_name=district_of.get(shape["parent"]),
            sources=[cite("community", "population/median_age/sex_ratio")], **fields))
    for s in admin2:
        if district_of.get(s["parent"]) == OUTSIDE:
            records.append(record(
                f"CYP-2021-outside-{s['id']}", s["name"], level="admin2", parent="CYP", country="CYP",
                match_by="shape_id", shape_id=s["id"], parent_name=OUTSIDE,
                population=gap(NOT_AVAILABLE, WHY_OUTSIDE), median_age=gap(NOT_AVAILABLE, WHY_OUTSIDE),
                sex_ratio=gap(NOT_AVAILABLE, WHY_OUTSIDE)))
    return records


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
