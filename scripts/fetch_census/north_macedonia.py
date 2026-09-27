#!/usr/bin/env python3
"""North Macedonia: the 2021 census by municipality and region, from MakStat.

The State Statistical Office publishes the 2021 Census of Population,
Households and Dwellings through its PxWeb database (makstat.stat.gov.mk),
by municipality:

* T1020P21 -- the resident population by single year of age and sex;
* T1008P21 -- by ethnic affiliation; T1012P21 -- by religious affiliation;
  T1015P21 -- by mother tongue (each by sex; the total is read).

Ethnicity, religion and mother tongue were asked of everyone enumerated in
person and answered freely; the census also counts, as its own row in every
one of these tables, "persons for whom data are taken from administrative
sources" -- residents who were not enumerated and whose age and sex come from
registers, with nothing for the three questions. They are kept as their own
bar ("No ... data") rather than spread over the answers.

**Boundary vintage.** The map draws the 84 municipalities of 2004-2013: it has
Kichevo, Drugovo, Oslomej, Vraneshtica and Zajas as five polygons. In 2013 the
four were merged into Kichevo, and the 2021 census tabulates the merged
municipality only. Its settlements, though, are published one by one --
T1502P21 (five-year age groups by sex) and T1503P21 (ethnicity) -- and
settlements nest in the old municipalities. Which old municipality each
settlement belonged to is read from MakStat's own table of the 1948-2002
censuses by settlement, whose 2002 rows name the municipality; the five old
units are then summed from their settlements, and every settlement of the
merged Kichevo must be assigned exactly once and the five must add to it.
Religion and mother tongue are not published by settlement, so those five
polygons carry a stated gap for those two fields: the merged municipality's
figure is never put on its pre-merger parts.

The eight regions are summed from their municipalities (the map's own
nesting), the whole of the merged Kichevo inside Southwest.

Median age is interpolated within the single year of age (municipalities,
regions) or within the five-year group (the five old Kichevo units, whose
settlement table is published in five-year groups); sex ratio is males per
100 females.

Usage:
    python -m scripts.fetch_census.north_macedonia
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .balkans_common import (age_fields, check_sum, fold, grouped_median,
                             match_names, px_meta, px_table, shapes)

OUT = "north_macedonia_census.json"
YEAR = 2021
BASE = "https://makstat.stat.gov.mk/PXWeb/api/v1/en/MakStat/Popisi"
CENSUS = f"{BASE}/Popis2021/NaselenieVkupno"
TABLES = {
    "age": f"{CENSUS}/NaseleniePopis2021/VozrastiPol/T1020P21.px",
    "ethnicity": f"{CENSUS}/NaseleniePopis2021/EtnoKulturniKarakteristiki/T1008P21.px",
    "religion": f"{CENSUS}/NaseleniePopis2021/EtnoKulturniKarakteristiki/T1012P21.px",
    "language": f"{CENSUS}/NaseleniePopis2021/EtnoKulturniKarakteristiki/T1015P21.px",
    "settlement_age": f"{CENSUS}/PodatociNaselenie/T1502P21.px",
    "settlement_ethnicity": f"{CENSUS}/PodatociNaselenie/T1503P21.px",
    "settlements_2002": f"{BASE}/PopisNaNaselenie/PopisiNaseleniMesta/Popis_nm_1948_2002_NasPoEtnPrip_ang.px",
    "municipalities_2002": f"{BASE}/PopisNaNaselenie/PopisOpstini/03Popis_op_02_VkNasPoNacPr_ang.px",
}
PAGE = "https://makstat.stat.gov.mk/PXWeb/pxweb/en/MakStat/MakStat__Popisi__Popis2021/"
SOURCE = ("State Statistical Office of North Macedonia, Census of Population, Households "
          "and Dwellings 2021, MakStat table {table}")
LICENCE = "State Statistical Office of North Macedonia (reuse with attribution)"

# The census's categories, by the code MakStat gives them, to the names the map
# uses. A code not listed stops the run with its label.
LABELS: dict[str, dict[str, str]] = {
    "ethnicity": {
        "Macedonians": "Macedonian", "Albanians": "Albanian", "Turkish": "Turkish",
        "Turks": "Turkish", "Romas": "Roma", "Roma": "Roma", "Vlachs": "Vlach",
        "Serbians": "Serbian", "Serbs": "Serbian", "Bosniaks": "Bosniak",
        "Other": "Other", "Undeclared": "Not declared", "Unknown": "Not stated",
    },
    "religion": {
        "Orthodox": "Orthodox", "Muslims (Islam)": "Islam", "Catholics": "Catholic",
        "Christians": "Christian", "Protestants": "Protestant", "Evangelists": "Evangelical",
        "Evangelists- methodist": "Evangelical Methodist",
        "Evangelists - methodist": "Evangelical Methodist",
        "Buddhists": "Buddhism", "Atheists": "Atheism", "Agnostics": "Agnosticism",
        "Jehovah's Witnesses": "Jehovah's Witnesses", "Adventists": "Seventh-day Adventist",
        "Hindus": "Hinduism", "Jews": "Judaism", "Judaism": "Judaism",
        "Other": "Other religion", "Others": "Other religion", "Undeclared": "Not declared",
        "Not declare": "Not declared", "atheist": "Atheism", "Atheist": "Atheism",
        "Unknown": "Not stated",
    },
    "language": {
        "Macedonian": "Macedonian", "Albanian": "Albanian", "Turkish": "Turkish",
        "Romani": "Romani", "Vlachs": "Aromanian", "Vlach": "Aromanian", "Serbian": "Serbian",
        "Bosniak": "Bosnian", "Bosnian": "Bosnian",
        "Other languages not mentioned": "Other", "Other": "Other",
        "Sign language": "Sign language", "Unknown": "Not stated",
    },
}
ADMIN_SOURCES = "persons for whom data are taken from administrative sources"
NO_DATA = {"ethnicity": "No ethnicity data", "religion": "No religion data",
           "language": "No language data"}
NOTES = {
    "ethnicity": ("Ethnic affiliation, 2021 census, resident population, free declaration. "
                  "'No ethnicity data' is the census's own row for residents not enumerated "
                  "in person, whose age and sex come from administrative registers and who "
                  "answered nothing; 'Not declared' and 'Not stated' are those who declined "
                  "or whose answer is unknown."),
    "religion": ("Religious affiliation, 2021 census, resident population, free declaration. "
                 "'No religion data' is the census's own row for residents not enumerated in "
                 "person (administrative-register records), who answered nothing."),
    "language": ("Mother tongue, 2021 census, resident population. 'No language data' is the "
                 "census's own row for residents not enumerated in person "
                 "(administrative-register records), who answered nothing."),
}

# MakStat writes ц as "c" and the boundary file as "ts"; these are the names
# that differ by more than that.
ALIASES = {
    "Cheshinovo-Obleshevo": "Cheshinovo - Obleshevo",
    "Chucher-Sandevo": "Chucher - Sandevo",
    "Chucher Sandevo": "Chucher - Sandevo",
    "Mavrovo and Rostushe": "Mavrovo and Rostusha",
    "Mavrovo i Rostushe": "Mavrovo and Rostusha",
    "Debrca": "Debartsa",
}
OLD_KICHEVO = ("Kichevo", "Drugovo", "Oslomej", "Vraneshtica", "Zajas")
# The 2021 settlement table's spelling -> the 2002 table's, where the two
# transliterations differ by more than ц: Ehloec (Ехлоец), Karbunica
# (Карбуница) and Rechani - Zajasko (Речани - Зајашко).
SETTLEMENT_ALIASES = {"Ehloec": "Ehlovets", "Karbunica": "Karabunitsa",
                      "Rechani - Zajasko": "Rechani-Zajashko"}


def key(name: str) -> str:
    """A municipality's name folded, with ц written one way."""
    return fold(name).replace("ts", "c")


UNKNOWN: dict[str, set[str]] = defaultdict(set)


def label_of(field: str, label: str) -> str:
    """The map's name for a census category; an unknown one is collected and
    the run refused once the whole table has been read, naming them all."""
    text = " ".join(label.split())
    if text.lower().startswith(ADMIN_SOURCES[:30]):
        return NO_DATA[field]
    if text in LABELS[field]:
        return LABELS[field][text]
    UNKNOWN[field].add(text)
    return text


def refuse_unknown() -> None:
    if any(UNKNOWN.values()):
        raise SystemExit("north_macedonia: categories with no entry in LABELS: "
                         + "; ".join(f"{f}: {sorted(v)}" for f, v in UNKNOWN.items() if v))


def age_of(label: str) -> int | None:
    """A single-year label as an age; the open top class as its lower bound."""
    m = re.match(r"^\s*(\d+)\s*(\+|and over|and more)?\s*$", label)
    return int(m.group(1)) if m else None


def var(meta: dict[str, dict[str, Any]], word: str) -> str:
    """The code of the variable whose English text contains ``word``."""
    hits = [c for c, v in meta.items() if word.lower() in (v.get("text") or "").lower()
            or word.lower() in c.lower()]
    if len(hits) != 1:
        raise SystemExit(f"north_macedonia: no single variable like {word!r}: "
                         f"{[(c, v.get('text')) for c, v in meta.items()]}")
    return hits[0]


def total_code(meta_var: dict[str, Any]) -> str:
    for code, text in zip(meta_var["values"], meta_var["valueTexts"]):
        if "total" in text.lower():
            return code
    raise SystemExit(f"north_macedonia: no total in {meta_var.get('text')}")


def municipal_ages(url: str) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """({code: name}, {code: {"men": Counter, "women": Counter, "total": n}})."""
    meta = px_meta(url)
    muni, age, sex = var(meta, "unicipal"), var(meta, "age"), var(meta, "sex")
    names = dict(zip(meta[muni]["values"], meta[muni]["valueTexts"]))
    sex_codes = dict(zip(meta[sex]["valueTexts"], meta[sex]["values"]))
    cells = px_table(url, {muni: "*", age: "*", sex: "*"})
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"men": Counter(), "women": Counter(),
                                                          "total": 0, "unknown": 0})
    for dims, value in cells:
        code = dims[muni][0]
        age_label = dims[age][1]
        who = dims[sex][1].lower()
        unit = out[code]
        if "total" in age_label.lower():
            if "total" in who:
                unit["total"] = value
            continue
        years = age_of(age_label)
        if "total" in who:
            if years is None:
                unit["unknown"] += value
            continue
        if years is None:
            continue
        (unit["men"] if who.startswith(("male", "men")) else unit["women"])[years] += value
    top = max(age_of(t) or 0 for t in meta[age]["valueTexts"])
    log(f"  {url.rsplit('/', 1)[-1]}: {len(names)} areas, single years to {top} (open top)")
    del sex_codes
    return names, out


def composition(field: str, url: str) -> dict[str, dict[str, float]]:
    """{municipality code: {group: persons}} with the census total under None."""
    meta = px_meta(url)
    muni, sex = var(meta, "unicipal"), var(meta, "sex")
    group = next(c for c in meta if c not in (muni, sex))
    cells = px_table(url, {muni: "*", sex: [total_code(meta[sex])], group: "*"})
    out: dict[str, dict[Any, float]] = defaultdict(dict)
    for dims, value in cells:
        code, label = dims[muni][0], dims[group][1]
        if "total" in label.lower():
            out[code][None] = value
        else:
            name = label_of(field, label)
            out[code][name] = out[code].get(name, 0) + value
    for code, groups in out.items():
        whole = groups.get(None)
        check_sum(sum(v for k, v in groups.items() if k is not None), whole,
                  f"north_macedonia: {field} of area {code}")
    return out


def settlements() -> dict[str, dict[str, Any]]:
    """The merged Kichevo's settlements: {name: {"ages": {(lo, width): {m, f}}, "ethnicity"}}."""
    meta = px_meta(TABLES["settlement_ethnicity"])
    place = var(meta, "settlement")
    group = next(c for c in meta if c != place)
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"ethnicity": {}, "groups": defaultdict(Counter)})
    codes: dict[str, str] = {}
    for dims, value in px_table(TABLES["settlement_ethnicity"], {place: "*", group: "*"}):
        m = re.match(r"^(.*) \((Kichevo)\)$", dims[place][1])
        if not m:
            continue
        codes[dims[place][0]] = m.group(1)
        label = dims[group][1]
        name = None if "total" in label.lower() else label_of("ethnicity", label)
        out[m.group(1)]["ethnicity"][name] = out[m.group(1)]["ethnicity"].get(name, 0) + value
    # The age table is asked for the Kichevo settlements only: every settlement
    # by age and sex is more cells than MakStat serves in one answer (403).
    meta = px_meta(TABLES["settlement_age"])
    place, age, sex = var(meta, "settlement"), var(meta, "age"), var(meta, "sex")
    seen = set()
    for dims, value in px_table(TABLES["settlement_age"], {place: sorted(codes), age: "*", sex: "*"}):
        m = re.match(r"^(.*) \((Kichevo)\)$", dims[place][1])
        if not m or codes.get(dims[place][0]) != m.group(1):
            raise SystemExit(f"north_macedonia: settlement code {dims[place]} differs between "
                             "the age and ethnicity tables")
        seen.add(dims[place][0])
        label, who = dims[age][1], dims[sex][1].lower()
        out[m.group(1)]["groups"][label][who] += value
    if seen != set(codes):
        raise SystemExit(f"north_macedonia: {len(set(codes) - seen)} Kichevo settlements have no ages")
    log(f"  the merged Kichevo: {len(codes)} settlements")
    return out


def old_municipality_of() -> dict[str, str]:
    """{settlement: its 2002 municipality}, for the five of the Kichevo area.

    Read from MakStat's table of the 1948-2002 censuses by settlement, whose
    rows are "Settlement (municipality in the year of the census) year".
    """
    meta = px_meta(TABLES["settlements_2002"])
    place = next(c for c in meta if "settlement" in c.lower())
    group = next(c for c in meta if c != place)
    out: dict[str, str] = {}
    counts: dict[str, float] = defaultdict(float)
    for dims, value in px_table(TABLES["settlements_2002"],
                                {place: "*", group: [meta[group]["values"][0]]}):
        m = re.match(r"^(.*?)\s*(?:\d\))?\s*\(([^()]*)\)\s*2002$", dims[place][1])
        if not m:
            continue
        name, muni = m.group(1).strip(), m.group(2).strip()
        if key(muni) in {key(k) for k in OLD_KICHEVO}:
            muni = next(k for k in OLD_KICHEVO if key(k) == key(muni))
            if name in out and out[name] != muni:
                raise SystemExit(f"north_macedonia: {name} is in both {out[name]} and {muni} in 2002")
            out[name] = muni
            counts[muni] += value
    log(f"  2002 settlements of the Kichevo area: "
        + ", ".join(f"{k} {sum(1 for v in out.values() if v == k)} ({counts[k]:,.0f} people)"
                    for k in OLD_KICHEVO))
    # The settlement table's 2002 people must be the 2002 census's own count of
    # each municipality, or the settlement lists are not those municipalities.
    meta = px_meta(TABLES["municipalities_2002"])
    muni = next(c for c in meta if "unicipal" in (meta[c].get("text") or "") or "unicipal" in c)
    group = next(c for c in meta if c != muni)
    total = [v for v, t in zip(meta[group]["values"], meta[group]["valueTexts"])
             if "total" in t.lower()][:1] or meta[group]["values"][:1]
    for dims, value in px_table(TABLES["municipalities_2002"], {muni: "*", group: total}):
        name = dims[muni][1]
        hit = next((k for k in OLD_KICHEVO if key(k) == key(name)), None)
        if hit:
            # MakStat's two 2002 tables disagree by five people on Oslomej
            # (10,425 by settlement, 10,420 by municipality) and agree exactly
            # on the other four. The settlement lists are what is being tested
            # here, and a misfiled settlement would move people between two of
            # the five -- which would break an exact match somewhere else -- so
            # a difference this small is logged rather than refused.
            check_sum(counts[hit], value, f"north_macedonia: 2002 settlements of {hit}", 0.001)
            log(f"    {hit}: its 2002 settlements add to {counts[hit]:,.0f}, its 2002 count "
                f"is {value:,.0f}")
    return out


def five_year(groups: dict[str, Counter]) -> tuple[list[tuple[float, float | None, float]], float, float]:
    """(grouped ages for both sexes, men, women) from {label: {sex: n}}."""
    rows, men, women = [], None, None
    for label, by_sex in groups.items():
        male = sum(v for k, v in by_sex.items() if k.startswith(("male", "men")))
        female = sum(v for k, v in by_sex.items() if k.startswith(("female", "women")))
        if "total" in label.lower():
            # The sexes are read from the all-ages row, so a person of unknown
            # age still counts towards the ratio.
            men, women = male, female
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", label.strip())
        top = re.match(r"^(\d+)\s*(\+|and over)", label.strip())
        if not (m or top):
            continue
        if m:
            rows.append((float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1),
                         male + female))
        else:
            rows.append((float(top.group(1)), None, male + female))
    if men is None or women is None:
        raise SystemExit("north_macedonia: a settlement age table without its all-ages row")
    return rows, men, women


def build() -> list[dict[str, Any]]:
    names, ages = municipal_ages(TABLES["age"])
    comps = {field: composition(field, TABLES[field]) for field in ("ethnicity", "religion", "language")}
    refuse_unknown()
    national = next(c for c, n in names.items() if "macedonia" in n.lower())
    city = next(c for c, n in names.items() if "city of skopje" in n.lower())
    munis = {c: n for c, n in names.items() if c not in (national, city)}
    log(f"  {len(munis)} municipalities")

    # Every municipality's men and women add to its total, and all of them to
    # the country's.
    for code in names:
        unit = ages[code]
        check_sum(sum(unit["men"].values()) + sum(unit["women"].values()) + unit["unknown"],
                  unit["total"], f"north_macedonia: ages of {names[code]}")
    check_sum(sum(ages[c]["total"] for c in munis), ages[national]["total"],
              "north_macedonia: municipalities against the country")
    for field, table in comps.items():
        check_sum(sum(table[c][None] for c in munis), table[national][None],
                  f"north_macedonia: {field}, municipalities against the country")
        for code in munis:
            check_sum(table[code][None], ages[code]["total"],
                      f"north_macedonia: {field} total of {munis[code]} against its age table")
    whole = Counter()
    for code in munis:
        whole.update(ages[code]["men"])
        whole.update(ages[code]["women"])
    from .redatam import median_age
    log(f"  country: {ages[national]['total']:,.0f} residents, median age "
        f"{median_age(whole)} from single years")

    admin2 = shapes("MKD", "admin2")
    admin1 = shapes("MKD", "admin1")
    region_of = {s["id"]: s["parent"] for s in admin2}
    bound, left_units, left_shapes = match_names(
        {c: ALIASES.get(n, n) for c, n in munis.items()},
        [{**s, "name": s["name"]} for s in admin2],
        who="municipalities")
    # MakStat writes ц as "c"; the boundary file as "ts". Bind the rest on that.
    by_key = defaultdict(list)
    for s in admin2:
        if s["id"] not in bound.values():
            by_key[key(s["name"])].append(s["id"])
    for code in [c for c in munis if c not in bound]:
        hits = by_key.get(key(ALIASES.get(munis[code], munis[code])), [])
        if len(hits) == 1:
            bound[code] = hits[0]
    kichevo = next(c for c, n in munis.items() if key(n) == key("Kichevo"))
    # The merged Kichevo is not a polygon: its name matches the old one's.
    bound.pop(kichevo, None)
    old_shapes = {name: next(s for s in admin2 if key(s["name"]) == key(name)) for name in OLD_KICHEVO}
    left = [munis[c] for c in munis if c not in bound and c != kichevo]
    spare = [s["name"] for s in admin2 if s["id"] not in bound.values()
             and s["id"] not in {x["id"] for x in old_shapes.values()}]
    if left or spare:
        raise SystemExit(f"north_macedonia: unbound municipalities {left}; polygons with none {spare}")
    log(f"  {len(bound)} municipalities bound one-to-one; the merged Kichevo goes to five polygons")

    def comp_fields(code_groups: dict[str, dict[Any, float]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field, groups in code_groups.items():
            counts = {k: v for k, v in groups.items() if k is not None and v}
            out[field] = shares(counts, total=groups[None])
            out[f"{field}_year"] = YEAR
            out[f"{field}_note"] = NOTES[field]
        return out

    def sources(fields: list[str]) -> list[dict[str, Any]]:
        table = {"population": "T1020P21", "median_age/sex_ratio": "T1020P21",
                 "ethnicity": "T1008P21", "religion": "T1012P21", "language": "T1015P21"}
        url = {"population": TABLES["age"], "median_age/sex_ratio": TABLES["age"],
               "ethnicity": TABLES["ethnicity"], "religion": TABLES["religion"],
               "language": TABLES["language"]}
        return [{"field": f, "name": SOURCE.format(table=table[f]), "url": url[f], "page": PAGE,
                 "year": YEAR, "license": LICENCE} for f in fields]

    records: list[dict[str, Any]] = []
    single_note = ("Interpolated within the single year of age that holds the middle person, "
                   "from the census's count of residents by single year of age and sex (T1020P21).")
    regions: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "men": Counter(), "women": Counter(), "total": 0.0,
        "ethnicity": Counter(), "religion": Counter(), "language": Counter()})
    for code, sid in sorted(bound.items(), key=lambda kv: munis[kv[0]]):
        unit = ages[code]
        region = regions[region_of[sid]]
        region["men"].update(unit["men"])
        region["women"].update(unit["women"])
        region["total"] += unit["total"]
        for field in comps:
            region[field].update(comps[field][code])
        records.append(record(
            f"MKD-2021-{code}", munis[code], level="admin2", parent="MKD", country="MKD",
            match_by="shape_id", shape_id=sid,
            population=measure(int(unit["total"]), year=YEAR, source=SOURCE.format(table="T1020P21")),
            **age_fields(unit["men"] + unit["women"], sum(unit["men"].values()),
                         sum(unit["women"].values()), year=YEAR,
                         source=SOURCE.format(table="T1020P21"), note=single_note),
            **comp_fields({f: comps[f][code] for f in comps}),
            sources=sources(["population", "median_age/sex_ratio", "ethnicity", "religion", "language"])))

    # The merged Kichevo: whole into its region, and by settlement onto the five.
    unit = ages[kichevo]
    region = regions[region_of[old_shapes["Kichevo"]["id"]]]
    region["men"].update(unit["men"])
    region["women"].update(unit["women"])
    region["total"] += unit["total"]
    for field in comps:
        region[field].update(comps[field][kichevo])
    places = settlements()
    refuse_unknown()
    home = old_municipality_of()
    # The two tables transliterate a few names differently; they are compared
    # folded, and each 2021 settlement must find exactly one 2002 one.
    by_key: dict[str, list[str]] = defaultdict(list)
    for name in home:
        by_key[key(name)].append(name)
    stray = []
    for name in sorted(places):
        hits = by_key.get(key(SETTLEMENT_ALIASES.get(name, name)), [])
        if len(hits) == 1:
            home.setdefault(name, home[hits[0]])
        else:
            stray.append(name)
    if stray:
        raise SystemExit(f"north_macedonia: Kichevo settlements with no 2002 municipality: {stray}; "
                         f"the 2002 settlements of the five are "
                         + "; ".join(f"{m}: {sorted(n for n, v in home.items() if v == m)}"
                                     for m in OLD_KICHEVO))
    parts: dict[str, dict[str, Any]] = {k: {"groups": defaultdict(Counter), "ethnicity": Counter()}
                                        for k in OLD_KICHEVO}
    for name, place in places.items():
        part = parts[home[name]]
        for label, by_sex in place["groups"].items():
            part["groups"][label].update(by_sex)
        part["ethnicity"].update(place["ethnicity"])
    check_sum(sum(p["ethnicity"][None] for p in parts.values()), comps["ethnicity"][kichevo][None],
              "north_macedonia: the five old municipalities against the merged Kichevo")
    for name in OLD_KICHEVO:
        part, shape = parts[name], old_shapes[name]
        grouped, men, women = five_year(part["groups"])
        whole = part["ethnicity"][None]
        check_sum(men + women, whole, f"north_macedonia: ages of old {name}")
        note = ("Interpolated within the five-year age group that holds the middle person: "
                f"{name} was merged into Kichevo in 2013, the census publishes the merged "
                "municipality by single year, and the old municipality is summed from its "
                "settlements, which are published in five-year groups (T1502P21).")
        eth = {k: v for k, v in part["ethnicity"].items() if k is not None and v}
        stated = gap(NOT_AVAILABLE, (
            f"{name} is drawn as it was before 2013, when it was merged into Kichevo. The 2021 "
            "census publishes this field for the merged municipality only, not by settlement, "
            "so no figure exists for the old municipality and the merged one's is not put on it."))
        records.append(record(
            f"MKD-2021-old-{fold(name)}", shape["name"], level="admin2", parent="MKD",
            country="MKD", match_by="shape_id", shape_id=shape["id"],
            population=measure(int(whole), year=YEAR, source=SOURCE.format(table="T1503P21")),
            population_note=("Summed from the 2021 census's settlements that belonged to "
                             f"{name} in 2002 (MakStat's 1948-2002 settlement table)."),
            **age_fields(None, men, women, year=YEAR, source=SOURCE.format(table="T1502P21"),
                         note=note, grouped=grouped),
            ethnicity=shares(eth, total=whole), ethnicity_year=YEAR,
            ethnicity_note=NOTES["ethnicity"] + (
                f" Summed from the settlements that made up {name} before its 2013 merger "
                "into Kichevo (T1503P21)."),
            religion=stated, language=stated,
            sources=[{"field": "population/ethnicity", "name": SOURCE.format(table="T1503P21"),
                      "url": TABLES["settlement_ethnicity"], "page": PAGE, "year": YEAR,
                      "license": LICENCE},
                     {"field": "median_age/sex_ratio", "name": SOURCE.format(table="T1502P21"),
                      "url": TABLES["settlement_age"], "page": PAGE, "year": YEAR,
                      "license": LICENCE}]))
        log(f"  old {name}: {whole:,.0f} people, median {grouped_median(grouped)}")

    names1 = {s["id"]: s for s in admin1}
    check_sum(sum(r["total"] for r in regions.values()), ages[national]["total"],
              "north_macedonia: regions against the country")
    for rid, region in sorted(regions.items(), key=lambda kv: names1[kv[0]]["name"]):
        shape = names1[rid]
        records.append(record(
            f"MKD-2021-region-{fold(shape['name'])}", shape["name"], level="admin1",
            parent="MKD", country="MKD", match_by="shape_id", shape_id=rid,
            population=measure(int(region["total"]), year=YEAR, source=SOURCE.format(table="T1020P21")),
            **age_fields(region["men"] + region["women"], sum(region["men"].values()),
                         sum(region["women"].values()), year=YEAR,
                         source=SOURCE.format(table="T1020P21"),
                         note=single_note + " Summed over the region's municipalities."),
            **comp_fields({f: dict(region[f]) for f in comps}),
            sources=sources(["population", "median_age/sex_ratio", "ethnicity", "religion", "language"])))
        log(f"  region {shape['name']}: {region['total']:,.0f}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("north_macedonia: MakStat, 2021 census")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
