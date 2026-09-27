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
import unicodedata
from collections import Counter
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .central_ages import age_sex_fields, check_national_median, check_sum, report_unbound, units
from .pxweb import http_json, unstack
from .redatam import median_age

BASE = "https://pxweb.stat.si/SiStatData/api/v1/en/Data/"
AGES = "05C4003S.px"
SEXES = "05C4010S.px"
PORTAL = "https://pxweb.stat.si/SiStatData/pxweb/en/Data/-/05C4003S.px"
SOURCE = "Statistical Office of the Republic of Slovenia (SURS), SiStat 05C4003S and 05C4010S"
LICENCE = "SURS open data (free reuse with attribution)"
OUT = PROCESSED / "slovenia_obcina.json"
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


def letters(name: str) -> list[tuple[str, bool]]:
    """The name's letters, each with whether it is a caron letter SURS writes."""
    out = []
    for ch in name.lower():
        if ch in CARONS:
            out.append(("?", True))
            continue
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c))
        if base.isalnum():
            out.append((base, False))
    return out


def same_place(surs: str, drawn: str) -> bool:
    for variant in {surs, surs.split("/")[0]}:
        a, b = letters(variant), letters(drawn)
        if len(a) == len(b) and all(wild or x == y[0] for (x, wild), y in zip(a, b)):
            return True
    return False


def bind(names: dict[str, str]) -> dict[str, dict[str, Any]]:
    shapes = units("SVN", "admin2")
    bound, unbound, used = {}, [], set()
    for code, name in sorted(names.items()):
        hits = [s for s in shapes if same_place(name, s["name"])]
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{name} ({code}): {[h['name'] for h in hits]}")
            continue
        bound[code] = hits[0]
        used.add(hits[0]["id"])
    report_unbound("slovenia", unbound, [s["name"] for s in shapes if s["id"] not in used])
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
    if len(records) < EXPECTED:
        log(f"  ! {EXPECTED - len(records)} municipalities left unbound (listed above)")
    return records


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
