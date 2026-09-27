#!/usr/bin/env python3
"""Slovenia: population, median age and sex ratio by občina, from SiStat.

The Statistical Office (SURS) publishes the register-based population of
every municipality twice a year on its PxWeb server. Two tables are read, at
the same half-year:

* 05C4003S -- population by municipality and single year of age (0 to 84,
  then 85 and over): the median age;
* 05C4010S -- population, men and women by municipality: the population and
  the sex ratio.

The first carries no sex and the second no age, so each field comes from the
table that has it, and the two totals must agree for every municipality.

**Names.** The boundary file's Slovenian names have lost their carons in a
way that is not a transliteration -- "Ajdovtcina" is Ajdovščina, "Bretice"
Brežice, "Crna na Koroakem" Črna na Koroškem, "Cetale" Žetale -- a č, š or ž
became some other single letter. So a SURS name binds to the polygon whose
name has the same length and the same letters everywhere except where SURS
writes č, š, ž, ć or đ, and the binding must be one to one. Everything left
over on either side is reported.

Ethnicity, religion and mother tongue: the register-based census asks none
of them (NOT_COLLECTED_POLICY for SVN; last asked in 2002).

Usage:
    python -m scripts.fetch_census.slovenia [--half 2026H1]
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .central_ages import age_sex_fields, fold, check_national_median, check_sum, report_unbound, units
from .pxweb import http_json, unstack
from .redatam import median_age

BASE = "https://pxweb.stat.si/SiStatData/api/v1/en/Data/"
AGES = "05C4003S.px"
SEXES = "05C4010S.px"
PORTAL = "https://pxweb.stat.si/SiStatData/pxweb/en/Data/-/05C4003S.px"
SOURCE = "Statistical Office of the Republic of Slovenia (SURS), SiStat 05C4003S and 05C4010S"
LICENCE = "SURS open data (free reuse with attribution)"
OUT = PROCESSED / "slovenia_obcina.json"
SETTLEMENTS = "05C5003S.px"
# A sex ratio outside this band is explained on the record: the settlement
# that carries the excess is named, with its men and women as SiStat counts
# them. Where an institution explains it, it is named here.
USUAL_RATIO = (85.0, 120.0)
INSTITUTIONS = {"Slovenska vas": "the men's prison at Dob (Zavod za prestajanje kazni zapora Dob)"}
# A median this high is explained with the share of the old.
OLD_MEDIAN = 55.0
CARONS = set("čšžćđ")
EXPECTED = 212


def meta(table: str) -> dict[str, dict[str, Any]]:
    return {v["code"]: v for v in http_json(BASE + table)["variables"]}


def code_like(variables: dict[str, dict[str, Any]], word: str) -> str:
    hits = [c for c, v in variables.items() if word.lower() in (v.get("text") or c).lower()]
    if len(hits) != 1:
        raise SystemExit(f"slovenia: no single variable like {word!r}: {list(variables)}")
    return hits[0]


def query(table: str, picks: dict[str, list[str] | None]) -> list[tuple[dict, float]]:
    q = [{"code": code, "selection": ({"filter": "all", "values": ["*"]} if values is None
                                      else {"filter": "item", "values": values})}
         for code, values in picks.items()]
    return unstack(http_json(BASE + table, {"query": q, "response": {"format": "json-stat2"}}))


# SURS abbreviates two municipalities' names where the boundary file does not.
EXPANSIONS = {"Slov. goricah": "Slovenskih goricah"}


def letters(name: str) -> list[tuple[str, bool]]:
    """The name's characters but spaces, each with whether it is a caron letter.

    Punctuation is kept: the boundary file sometimes wrote a hyphen where a
    caron letter was ("Star-e" for Starše), and a hyphen or slash that both
    names have lines up either way.
    """
    out = []
    for ch in name.lower():
        if ch in CARONS:
            out.append(("?", True))
            continue
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c))
        if base and not base.isspace():
            out.append((base, False))
    return out


def spellings(surs: str) -> set[str]:
    out = {surs, surs.split("/")[0].strip()}
    for short, long in EXPANSIONS.items():
        out |= {v.replace(short, long) for v in set(out)}
    return out


def exact(surs: str, drawn: str) -> bool:
    return any(fold(v) == fold(drawn) for v in spellings(surs))


def same_place(surs: str, drawn: str) -> bool:
    """Equal length, equal everywhere SURS does not write a caron letter."""
    for variant in spellings(surs):
        a, b = letters(variant), letters(drawn)
        if len(a) == len(b) and all(wild or x == y[0] for (x, wild), y in zip(a, b)):
            return True
    return False


def cut_at_caron(surs: str, drawn: str) -> bool:
    """The boundary file's name is SURS's cut off where a caron letter was.

    "Ormo" is Ormož and "Velike La" Velike Lašče: the mangling that turned
    carons into other letters elsewhere ended these names at one.
    """
    for variant in spellings(surs):
        a, b = letters(variant), letters(drawn)
        if 0 < len(b) < len(a) and a[len(b)][1] and \
                all(wild or x == y[0] for (x, wild), y in zip(a, b)):
            return True
    return False


def area(shape: dict[str, Any]) -> float:
    x0, y0, x1, y1 = shape["bbox"]
    return (x1 - x0) * (y1 - y0)


def bind(names: dict[str, str]) -> dict[str, dict[str, Any]]:
    """SURS code -> polygon: exact names first, then caron wildcards, then cut names.

    Each pass binds only what is unique among the polygons not yet taken, so
    Trzin binds to "Trzin" before Tržič is looked for and finds "Trsic".
    One boundary name, Maribor, is drawn twice: the municipality and a
    sliver some sixty metres across; the sliver is left unbound.
    """
    shapes = units("SVN", "admin2")
    bound: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for rule in (exact, same_place, cut_at_caron):
        for code, name in sorted(names.items()):
            if code in bound:
                continue
            hits = [s for s in shapes if s["id"] not in used and rule(name, s["name"])]
            if len(hits) > 1:
                biggest = max(hits, key=area)
                if all(area(h) < 0.01 * area(biggest) for h in hits if h is not biggest):
                    log(f"  {name}: {len(hits)} polygons of that name; the others are slivers "
                        f"under 1% of its extent")
                    hits = [biggest]
            if len(hits) == 1:
                bound[code] = hits[0]
                used.add(hits[0]["id"])
    unbound = [f"{names[c]} ({c})" for c in sorted(names) if c not in bound]
    report_unbound("slovenia", unbound, [f"{s['name']} (bbox {s['bbox']})" for s in shapes
                                         if s["id"] not in used])
    return bound


def build(half: str) -> list[dict[str, Any]]:
    log(f"slovenia: SiStat {AGES} and {SEXES}, {half}")
    va, vs = meta(AGES), meta(SEXES)
    muni_a, half_a, age_a = code_like(va, "MUNICIPAL"), code_like(va, "HALF"), code_like(va, "AGE")
    muni_s, half_s, meas_s = code_like(vs, "MUNICIPAL"), code_like(vs, "HALF"), code_like(vs, "MEASURE")
    if half not in va[half_a]["values"] or half not in vs[half_s]["values"]:
        raise SystemExit(f"slovenia: {half} is not in both tables")
    measures = dict(zip(vs[meas_s]["valueTexts"], vs[meas_s]["values"]))
    wanted = {"total": measures["Population - TOTAL"], "men": measures["Population - Men"],
              "women": measures["Population - Women"]}
    sexes: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}
    for key, value in query(SEXES, {muni_s: None, meas_s: list(wanted.values()), half_s: [half]}):
        code, label = key[muni_s]
        names[code] = label
        which = next(k for k, v in wanted.items() if v == key[meas_s][0])
        sexes.setdefault(code, {})[which] = value
    ages: dict[str, Counter] = {}
    age_total: dict[str, float] = {}
    for key, value in query(AGES, {muni_a: None, half_a: [half], age_a: None}):
        code = key[muni_a][0]
        age_code, age_label = key[age_a]
        if "TOTAL" in age_label.upper():
            age_total[code] = value
            continue
        ages.setdefault(code, Counter())[int("".join(c for c in age_label if c.isdigit()))] += value
    municipalities = sorted(c for c in names if c != "0")
    log(f"  {len(municipalities)} municipalities; Slovenia {sexes['0']['total']:,.0f}")
    for code in ["0", *municipalities]:
        s = sexes[code]
        if abs(s["men"] + s["women"] - s["total"]) > 0.5 or abs(age_total[code] - s["total"]) > 0.5:
            raise SystemExit(f"slovenia: {names[code]}: men {s['men']:,.0f} + women "
                             f"{s['women']:,.0f}, total {s['total']:,.0f}, by age {age_total[code]:,.0f}")
        if abs(sum(ages[code].values()) - age_total[code]) > 0.5:
            raise SystemExit(f"slovenia: {names[code]}: the single years do not make the total")
    check_sum((sexes[c]["total"] for c in municipalities), sexes["0"]["total"],
              "municipalities against Slovenia")
    year = int(half[:4])
    # 05C4003S's 2026H1 is the population on 1 January 2026.
    check_national_median(ages["0"], "SI", year if half.endswith("H1") else year + 1)
    bound = bind({c: names[c] for c in municipalities})
    records = []
    for code in municipalities:
        shape = bound.get(code)
        if shape is None:
            continue
        s = sexes[code]
        # No sex in the age table: the ages are both sexes, and the split comes
        # from 05C4010S. age_sex_fields wants the two apart, so the median is
        # computed on the ages and passed in.
        fields = age_sex_fields(
            Counter({0: s["men"]}), Counter({0: s["women"]}), year=year, source=SOURCE,
            total=s["total"], median=median_age(ages[code]),
            median_note=(f"Interpolated within the single year of age that holds the middle "
                         f"person, from SURS's count of the municipality's population by single "
                         f"year of age (0 to 84, then 85 and over), {half} (05C4003S)."),
            ratio_note=f"Males per 100 females in the municipality's population, {half} (05C4010S).")
        label = shape["name"]
        records.append(record(
            f"SVN-{code}", names[code], level="admin2", parent=shape["parent"], country="SVN",
            codes={"surs_obcina": code}, aliases=[label] if label != names[code] else [],
            match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE, "url": PORTAL,
                      "license": LICENCE, "year": year}],
            **fields))
    explain_outliers(records, ages, year)
    if len(records) < EXPECTED:
        log(f"  ! {EXPECTED - len(records)} municipalities left unbound (listed above)")
    return records


def explain_outliers(records: list[dict[str, Any]], ages: dict[str, Counter], year: int) -> None:
    """Say on the record why a sex ratio or a median age stands out."""
    top = max(r["median_age"]["value"] for r in records)
    for r in records:
        code = r["codes"]["surs_obcina"]
        ratio = r["sex_ratio"]["value"]
        if not USUAL_RATIO[0] <= ratio <= USUAL_RATIO[1]:
            r["sex_ratio_note"] += " " + lopsided_settlement(code, r["name"], year)
        median = r["median_age"]["value"]
        if median >= OLD_MEDIAN:
            people = sum(ages[code].values())
            old = sum(n for age, n in ages[code].items() if age >= 65)
            r["median_age_note"] += (f" {100 * old / people:.0f}% of its {people:,.0f} people are 65 or "
                                     f"older" + ("; the highest median of Slovenia's municipalities."
                                                 if median == top else "."))


def lopsided_settlement(code: str, name: str, year: int) -> str:
    """The settlement that carries a municipality's excess of one sex, in SiStat's count."""
    v = meta(SETTLEMENTS)
    place, when, what = code_like(v, "SETTLEMENT"), code_like(v, "YEAR"), code_like(v, "MEASURE")
    sexes: dict[str, str] = {}
    for value, label in zip(v[what]["values"], v[what]["valueTexts"]):
        if re.search(r"(?i)\bwomen\b|\bfemales?\b", label):
            sexes.setdefault("women", value)
        elif re.search(r"(?i)\bmen\b|\bmales?\b", label):
            sexes.setdefault("men", value)
    if set(sexes) != {"men", "women"}:
        raise SystemExit(f"slovenia: {SETTLEMENTS} names no measure for men and women: "
                         f"{v[what]['valueTexts']}")
    wanted = [c for c in v[place]["values"] if len(c) == 6 and c.startswith(code)]
    latest = str(max(int(y) for y in v[when]["values"] if int(y) <= year + 1))
    counts: dict[str, dict[str, float]] = {}
    for key, value in query(SETTLEMENTS, {place: wanted, when: [latest], what: list(sexes.values())}):
        label = key[place][1].split(" ", 1)[-1]
        counts.setdefault(label, {})["men" if key[what][0] == sexes["men"] else "women"] = value
    if not counts:
        raise SystemExit(f"slovenia: {SETTLEMENTS} has no settlements for {name} ({code})")
    worst, c = max(counts.items(), key=lambda kv: abs(kv[1].get("men", 0) - kv[1].get("women", 0)))
    excess = sum(x.get("men", 0) - x.get("women", 0) for x in counts.values())
    log(f"  {name}: {excess:+,.0f} men over women, {c['men'] - c['women']:+,.0f} of them in {worst}")
    where = f", where {INSTITUTIONS[worst]} stands" if worst in INSTITUTIONS else ""
    return (f"The excess is one settlement's: {worst} counts {c['men']:,.0f} men and "
            f"{c['women']:,.0f} women ({SETTLEMENTS}, {latest}){where}, against "
            f"{excess:+,.0f} men over women in the whole municipality.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--half", default="2026H1")
    args = ap.parse_args()
    records = build(args.half)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
