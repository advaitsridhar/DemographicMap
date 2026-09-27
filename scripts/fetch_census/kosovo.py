#!/usr/bin/env python3
"""Kosovo: the 2024 census by municipality and district, from ASKdata.

The Kosovo Agency of Statistics (ASK) publishes the 2024 Population and
Housing Census through its PxWeb database (askdata.rks-gov.net), by
municipality, under "Census population / Demographic characteristics":

* census2024_00 -- population by single year of age and sex;
* tab04census  -- population by five-year age group and sex, *with
  estimation*: ASK's figure where the enumeration fell short;
* census2024_05 -- ethnicity; census2024_63 -- the same *with estimation*;
* census2024_10 -- religion; census2024_22 -- mother tongue.

**The north.** In four municipalities -- North Mitrovica, Leposaviq, Zubin
Potok and Zveçan -- most residents were not enumerated, and ASK publishes an
estimate beside the count. Wherever a municipality's enumerated population
falls short of ASK's estimated one, this reads the estimated tables: the head
count, the age and sex (in five-year groups, the finest ASK publishes with the
estimate), and ethnicity; religion and mother tongue exist only for the
enumerated residents there, and a composition of a minority of a
municipality's people is not the municipality's, so those two fields carry a
stated gap instead. Elsewhere the single-year table is read.

The seven districts the map draws are summed from their municipalities.

Usage:
    python -m scripts.fetch_census.kosovo
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .balkans_common import age_fields, check_sum, fold, grouped_median, px_meta, px_table, shapes
from .redatam import median_age

OUT = "kosovo_census.json"
YEAR = 2024
BASE = "https://askdata.rks-gov.net/api/v1/en/ASKdata/Census%20population/1_Demographic_Characteristics"
TABLES = {
    "age": f"{BASE}/census2024_00.px",
    "age_est": f"{BASE}/tab04census.px",
    "ethnicity": f"{BASE}/census2024_05.px",
    "ethnicity_est": f"{BASE}/census2024_63.px",
    "religion": f"{BASE}/census2024_10.px",
    "language": f"{BASE}/census2024_22.px",
}
PAGE = "https://askdata.rks-gov.net/pxweb/en/ASKdata/ASKdata__Census%20population__1_Demographic_Characteristics/"
SOURCE = "Kosovo Agency of Statistics, Population and Housing Census 2024, ASKdata table {table}"
LICENCE = "Kosovo Agency of Statistics (reuse with attribution)"

LABELS = {
    "ethnicity": {"albanian": "Albanian", "serb": "Serbian", "bosniak": "Bosniak",
                  "turk": "Turkish", "romani": "Roma", "roma": "Roma", "ashkali": "Ashkali",
                  "egyptian": "Balkan Egyptian", "gorani": "Gorani", "others": "Other",
                  "other": "Other", "prefers not to answer": "Not declared",
                  "not available": "Not stated"},
    "religion": {"islam": "Islam", "orthodox": "Orthodox", "catholic": "Catholic",
                 "others": "Other religion", "other": "Other religion",
                 "no religious affiliation": "No religion",
                 "prefers not to answer": "Not declared", "not available": "Not stated"},
    "language": {"albanian": "Albanian", "serb": "Serbian", "serbian": "Serbian",
                 "bosnian": "Bosnian", "turkish": "Turkish", "romani": "Romani",
                 "other (specify)": "Other", "other": "Other", "not available": "Not stated",
                 "prefers not to answer": "Not declared"},
}
NOTES = {
    "ethnicity": ("Ethnic affiliation, 2024 census, resident population, free declaration; "
                  "those who preferred not to answer are their own bar. Egyptian is the "
                  "census's Balkan Egyptian community."),
    "religion": ("Religion, 2024 census, resident population, free declaration; no religious "
                 "affiliation and preferring not to answer are their own bars."),
    "language": "Mother tongue, 2024 census, resident population.",
}
# ASK's municipality names, in Albanian and in their definite forms, to the
# boundary file's.
ALIASES = {
    "gjakove": "Gjakova", "gllogoc": "Drenas", "gllogovc": "Drenas", "kline": "Klina",
    "kamenice": "Kamenica", "mitrovice": "Mitrovica", "peje": "Peja", "podujeve": "Podujeva",
    "prishtine": "Pristina", "suhareke": "Suhareka", "malisheve": "Malisheva",
    "mamushe": "Mamusha", "haniielezit": "Han i Elezit", "hanitelezit": "Han i Elezit",
    "gracanice": "Gracanica", "mitroviceveriut": "North Mitrovica",
    "mitroviceeveriut": "North Mitrovica", "novoberde": "Novobërdë", "skenderaj": "Skenderaj",
    "shtime": "Shtime", "shterpce": "Shtërpcë", "fushekosove": "Fushë Kosovë",
    "mitrovicaveriore": "North Mitrovica", "zveqan": "Zveçan", "leposaviq": "Leposaviq", "zubinpotok": "Zubin Potok",
}
COVERAGE = 0.995


def key(name: str) -> str:
    return fold(re.sub(r"^Municipality of\s+", "", name))


def var(meta: dict[str, dict[str, Any]], *words: str) -> str:
    hits = [c for c, v in meta.items()
            if any(w in (v.get("text") or "").lower() or w in c.lower() for w in words)]
    if len(hits) != 1:
        raise SystemExit(f"kosovo: no single variable like {words}: "
                         f"{[(c, v.get('text')) for c, v in meta.items()]}")
    return hits[0]


def value_code(meta_var: dict[str, Any], want: str) -> str:
    for code, text in zip(meta_var["values"], meta_var["valueTexts"]):
        if text.strip().lower() == want.lower():
            return code
    raise SystemExit(f"kosovo: no value {want!r} in {meta_var.get('text')}: {meta_var['valueTexts']}")


def muni_var(meta: dict[str, dict[str, Any]]) -> str:
    """The variable listing KOSOVA and the municipalities (ASK names it oddly)."""
    hits = [c for c, v in meta.items() if any(t.strip().upper() == "KOSOVA" for t in v["valueTexts"])
            or any(key(t) == "decan" for t in v["valueTexts"])]
    if len(hits) != 1:
        raise SystemExit(f"kosovo: no single municipality variable in {list(meta)}")
    return hits[0]


_SHAPE_KEYS: dict[str, str] = {}


def canon(label: str) -> str:
    """One name for a municipality whichever table spells it: the boundary
    file's, where it can be found. ASK's tables disagree with each other
    ("Gllogoc" and "Gllogovc", "Novobërdë" and "Novobërda"), so each table's
    rows are keyed by this before any two are compared."""
    label = label.strip()
    if label.upper() == "KOSOVA":
        return "KOSOVA"
    if not _SHAPE_KEYS:
        _SHAPE_KEYS.update({key(s["name"]): re.sub(r"^Municipality of\s+", "", s["name"])
                            for s in shapes("XKX", "admin2")})
    base = key(ALIASES.get(fold(label), label))
    for form in (base, base[:-1] + "a" if base.endswith("e") else base,
                 base[:-1] + "e" if base.endswith("a") else base, base + "a", base.rstrip("ae")):
        if form in _SHAPE_KEYS:
            return _SHAPE_KEYS[form]
    return label


def year_pick(meta: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    out = {}
    for c, v in meta.items():
        if any(t.strip() == str(YEAR) for t in v["valueTexts"]) and len(v["values"]) <= 3:
            out[c] = [value_code(v, str(YEAR))]
    return out


def ages(url: str, grouped: bool) -> dict[str, dict[str, Any]]:
    """{municipality label: {"men", "women", "total", "ages" or "groups"}}."""
    meta = px_meta(url)
    muni = muni_var(meta)
    sex = var(meta, "gjinia", "sex")
    rest = [c for c in meta if c not in (muni, sex) and c not in year_pick(meta)]
    if len(rest) != 1:
        raise SystemExit(f"kosovo: {url}: cannot tell the age variable among {rest}")
    age = rest[0]
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "men": 0.0, "women": 0.0, "total": 0.0, "ages": Counter(), "groups": Counter(),
        "by_sex": Counter(), "rows": Counter()})
    for dims, value in px_table(url, {muni: "*", sex: "*", age: "*", **year_pick(meta)}):
        place, who, label = canon(dims[muni][1]), dims[sex][1].lower(), dims[age][1].strip()
        unit = out[place]
        if label.lower() == "total":
            unit["rows"][who] = value
            continue
        if who != "total":
            unit["by_sex"][who] += value
            continue
        if grouped:
            m = re.match(r"^(\d+)\s*-\s*(\d+)$", label)
            top = re.match(r"^(\d+)\s*(\+|and over|e me shume)", label, re.I)
            if m:
                unit["groups"][(float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1))] += value
            elif top:
                unit["groups"][(float(top.group(1)), None)] += value
            else:
                raise SystemExit(f"kosovo: age group {label!r}")
        else:
            m = re.match(r"^(\d+)\s*(\+)?$", label)
            if not m:
                raise SystemExit(f"kosovo: single age {label!r}")
            unit["ages"][int(m.group(1))] += value
    # The all-ages row where the table prints one, the ages summed where not;
    # the two must agree where both exist.
    for place, unit in out.items():
        summed = sum(unit["groups"].values()) if grouped else sum(unit["ages"].values())
        unit["total"] = unit["rows"].get("total", summed)
        unit["men"] = unit["rows"].get("male", unit["by_sex"]["male"])
        unit["women"] = unit["rows"].get("female", unit["by_sex"]["female"])
        check_sum(summed, unit["total"], f"kosovo: ages of {place} in {url.rsplit('/', 1)[-1]}")
        check_sum(unit["men"] + unit["women"], unit["total"], f"kosovo: sexes of {place}")
    return out


def composition(field: str, url: str) -> dict[str, dict[Any, float]]:
    meta = px_meta(url)
    muni = muni_var(meta)
    sex = var(meta, "gjinia", "sex")
    years = year_pick(meta)
    group = next(c for c in meta if c not in (muni, sex) and c not in years)
    total_sex = value_code(meta[sex], "Total")
    out: dict[str, dict[Any, float]] = defaultdict(dict)
    for dims, value in px_table(url, {muni: "*", sex: [total_sex], group: "*", **years}):
        place, label = canon(dims[muni][1]), dims[group][1].strip()
        if label.lower() == "total":
            out[place][None] = value
            continue
        name = LABELS[field].get(label.lower())
        if name is None:
            raise SystemExit(f"kosovo: {field} category {label!r} has no entry in LABELS")
        out[place][name] = out[place].get(name, 0) + value
    for place, groups in out.items():
        check_sum(sum(v for k, v in groups.items() if k is not None), groups[None],
                  f"kosovo: {field} of {place}")
    return out


def build() -> list[dict[str, Any]]:
    single = ages(TABLES["age"], grouped=False)
    estimated = ages(TABLES["age_est"], grouped=True)
    comps = {f: composition(f, TABLES[f]) for f in ("ethnicity", "religion", "language")}
    eth_est = composition("ethnicity", TABLES["ethnicity_est"])
    country = next(p for p in single if p.upper() == "KOSOVA")
    places = [p for p in single if p != country]
    for p in places:
        for name, table in (("estimated ages", estimated), ("ethnicity", comps["ethnicity"]),
                            ("religion", comps["religion"]), ("language", comps["language"]),
                            ("estimated ethnicity", eth_est)):
            if p not in table:
                raise SystemExit(f"kosovo: {p} is in the single-year table and not in the "
                                 f"{name} table, which lists {sorted(table)}")
    check_sum(sum(single[p]["total"] for p in places), single[country]["total"],
              "kosovo: municipalities against Kosovo (enumerated)")
    est_country = next(p for p in estimated if p.upper() == "KOSOVA")
    check_sum(sum(estimated[p]["total"] for p in places), estimated[est_country]["total"],
              "kosovo: municipalities against Kosovo (with estimation)")
    log(f"  Kosovo: {single[country]['total']:,.0f} enumerated, "
        f"{estimated[est_country]['total']:,.0f} with ASK's estimate; national median "
        f"{median_age(single[country]['ages'])} from single years")

    admin2 = shapes("XKX", "admin2")
    admin1 = {s["id"]: s for s in shapes("XKX", "admin1")}
    by_key = {key(s["name"]): s for s in admin2}
    bound: dict[str, dict[str, Any]] = {}
    lost = []
    for p in places:
        target = ALIASES.get(fold(p), p)
        shape = by_key.get(key(target))
        if shape is None:
            lost.append(p)
            continue
        if shape["id"] in {s["id"] for s in bound.values()}:
            raise SystemExit(f"kosovo: two municipalities on {shape['name']}")
        bound[p] = shape
    spare = [s["name"] for s in admin2 if s["id"] not in {b["id"] for b in bound.values()}]
    if lost or spare:
        raise SystemExit(f"kosovo: ASK's municipalities with no polygon {lost}; "
                         f"polygons with no municipality: {spare}")
    log(f"  {len(bound)} municipalities bound one-to-one")

    src = {k: SOURCE.format(table=v.rsplit("/", 1)[-1].replace(".px", "")) for k, v in TABLES.items()}
    records = []
    districts: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "men": 0.0, "women": 0.0, "total": 0.0, "groups": Counter(), "ethnicity": Counter(),
        "religion": Counter(), "language": Counter(), "short": []})
    for p in places:
        shape = bound[p]
        count, est = single[p], estimated[p]
        coverage = count["total"] / est["total"] if est["total"] else 1.0
        full = coverage >= COVERAGE
        fields: dict[str, Any] = {}
        cite: list[dict[str, Any]] = []
        if full:
            fields["population"] = measure(int(count["total"]), year=YEAR, source=src["age"])
            fields.update(age_fields(count["ages"], count["men"], count["women"], year=YEAR,
                                     source=src["age"], note=(
                                         "Interpolated within the single year of age that holds "
                                         "the middle person, from the census's count by single "
                                         "year of age and sex (census2024_00).")))
            cite.append({"field": "population/median_age/sex_ratio", "name": src["age"],
                         "url": TABLES["age"], "page": PAGE, "year": YEAR, "license": LICENCE})
            eth = comps["ethnicity"][p]
            eth_src = "ethnicity"
        else:
            fields["population"] = measure(int(est["total"]), year=YEAR, source=src["age_est"])
            fields["population_note"] = (
                f"ASK's figure with its estimate: the census enumerated {count['total']:,.0f} "
                f"of the {est['total']:,.0f} residents it puts here ({100 * coverage:.0f}%).")
            fields.update(age_fields(None, est["men"], est["women"], year=YEAR,
                                     source=src["age_est"], grouped=[(lo, w, n) for (lo, w), n in est["groups"].items()],
                                     note=("Interpolated within the five-year age group that "
                                           "holds the middle person, from ASK's population by age "
                                           "group and sex with its estimate for residents not "
                                           "enumerated (tab04census); the single-year table "
                                           "counts the enumerated only.")))
            cite.append({"field": "population/median_age/sex_ratio", "name": src["age_est"],
                         "url": TABLES["age_est"], "page": PAGE, "year": YEAR, "license": LICENCE})
            eth = eth_est[p]
            eth_src = "ethnicity_est"
        whole = eth[None]
        check_sum(whole, fields["population"]["value"], f"kosovo: ethnicity total of {p}", 0.001)
        fields["ethnicity"] = shares({k: v for k, v in eth.items() if k is not None and v}, total=whole)
        fields["ethnicity_year"] = YEAR
        fields["ethnicity_note"] = NOTES["ethnicity"] + ("" if full else (
            " Includes ASK's estimate for the residents the census did not enumerate "
            "(census2024_63)."))
        cite.append({"field": "ethnicity", "name": src[eth_src], "url": TABLES[eth_src],
                     "page": PAGE, "year": YEAR, "license": LICENCE})
        for field in ("religion", "language"):
            groups = comps[field][p]
            if full:
                fields[field] = shares({k: v for k, v in groups.items() if k is not None and v},
                                       total=groups[None])
                fields[f"{field}_year"] = YEAR
                fields[f"{field}_note"] = NOTES[field]
                cite.append({"field": field, "name": src[field], "url": TABLES[field],
                             "page": PAGE, "year": YEAR, "license": LICENCE})
            else:
                fields[field] = gap(NOT_AVAILABLE, (
                    f"The 2024 census enumerated {count['total']:,.0f} of the {est['total']:,.0f} "
                    f"residents ASK estimates for {p} ({100 * coverage:.0f}%), and publishes "
                    f"{'religion' if field == 'religion' else 'mother tongue'} for the enumerated "
                    "only. Those answers describe the people who took part, not the "
                    "municipality, so they are not shown as its composition."))
        records.append(record(f"XKX-2024-{fold(p)}", shape["name"], level="admin2", parent="XKX",
                              country="XKX", match_by="shape_id", shape_id=shape["id"],
                              sources=cite, **fields))
        d = districts[shape["parent"]]
        d["total"] += est["total"]
        d["men"] += est["men"]
        d["women"] += est["women"]
        d["groups"].update(est["groups"])
        d["ethnicity"].update(eth)
        d["religion"].update(comps["religion"][p])
        d["language"].update(comps["language"][p])
        if not full:
            d["short"].append(p)
        log(f"  {p}: {count['total']:,.0f} enumerated / {est['total']:,.0f} estimated"
            + ("" if full else " -- read with ASK's estimate"))
    for did, d in sorted(districts.items(), key=lambda kv: admin1[kv[0]]["name"]):
        shape = admin1[did]
        grouped = [(lo, w, n) for (lo, w), n in d["groups"].items()]
        more: dict[str, Any] = {}
        for field in ("religion", "language"):
            if d["short"]:
                more[field] = gap(NOT_AVAILABLE, (
                    f"The 2024 census publishes this field for enumerated residents only, and "
                    f"in {', '.join(d['short'])} it enumerated too few of them for the "
                    "answers to describe the district."))
                continue
            more[field] = shares({k: v for k, v in d[field].items() if k is not None and v},
                                 total=d[field][None])
            more[f"{field}_year"] = YEAR
            more[f"{field}_note"] = NOTES[field] + " Summed over the district's municipalities."
            more.setdefault("_cite", []).append(
                {"field": field, "name": src[field], "url": TABLES[field], "page": PAGE,
                 "year": YEAR, "license": LICENCE})
        extra_cite = more.pop("_cite", [])
        records.append(record(
            f"XKX-2024-district-{fold(shape['name'])}", shape["name"], level="admin1",
            parent="XKX", country="XKX", match_by="shape_id", shape_id=did,
            population=measure(int(d["total"]), year=YEAR, source=src["age_est"]),
            **age_fields(None, d["men"], d["women"], year=YEAR, source=src["age_est"],
                         grouped=grouped, note=(
                             "Interpolated within the five-year age group that holds the middle "
                             "person, summed over the district's municipalities from ASK's "
                             "population by age group and sex with its estimate (tab04census).")),
            ethnicity=shares({k: v for k, v in d["ethnicity"].items() if k is not None and v},
                             total=d["ethnicity"][None]),
            ethnicity_year=YEAR,
            ethnicity_note=NOTES["ethnicity"] + " Summed over the district's municipalities, "
            "with ASK's estimate for residents not enumerated in the north (census2024_63).",
            sources=[{"field": "population/median_age/sex_ratio", "name": src["age_est"],
                      "url": TABLES["age_est"], "page": PAGE, "year": YEAR, "license": LICENCE},
                     {"field": "ethnicity", "name": src["ethnicity_est"],
                      "url": TABLES["ethnicity_est"], "page": PAGE, "year": YEAR,
                      "license": LICENCE}] + extra_cite,
            **more))
        log(f"  district {shape['name']}: {d['total']:,.0f}, median {grouped_median(grouped)}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("kosovo: ASKdata, 2024 census")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
