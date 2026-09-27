#!/usr/bin/env python3
"""Lithuania: population, median age and sex ratio for the 60 municipalities and 10 counties.

Statistics Lithuania's Official Statistics Portal answers SDMX 2.1 at
osp-rs.stat.gov.lt. Every observation in its "generic" data message carries
its own key (``dimensionAtObservation="AllDimensions"``), so the reader here
takes each ``Obs`` with its ``ObsKey`` rather than looking for series.

* **S3R167_M3010202** -- resident population at the beginning of the year by
  municipality, sex and single year of age (0-84, 85 and over, and a few of
  unknown age). The median age and the sex ratio come from it.
* **S3R167_M3010203** -- the same people by five-year group, which gives the
  population and checks the single years, sex by sex.
* **S3R629_M3010217** -- the median age the office publishes for each unit,
  in completed years (44 for the country at the beginning of 2026, where
  Eurostat's convention gives 44.6). The map gives medians to a tenth of a year,
  interpolated within the year that holds the middle person, and so does this
  adapter, from the office's own single years; the run checks that every
  interpolated median falls in the office's completed year.

The codes are those of ``savivaldybesRegdb`` (00 the country, 01-10 the
counties, the rest the municipalities), and the code list gives each a
Lithuanian and an English name. The boundary file names municipalities in
both languages -- "Akmenės rajono savivaldybė" beside "Alytus District
Municipality" -- so both are offered to the binder, with the office's
abbreviations ("r. sav.", "d. mun.") written out.

The 2021 census's ethnicity, native language and religion are published on
osp.stat.gov.lt, whose pages answer a scripted request with a Cloudflare
challenge (HTTP 403); see the report for what was tried.

Usage:
    python -m scripts.fetch_census.lithuania
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json
from .binding import fold
from .nordic_common import (SEX_RATIO_UNIT, AgeSex, bind_rows, check_parts, load_units,
                            request, sex_ratio)

OSP = "https://osp-rs.stat.gov.lt/rest_xml"
AGES = "S3R167_M3010203"
SINGLE = "S3R167_M3010202"
MEDIAN = "S3R629_M3010217"
SOURCE = "Statistics Lithuania"
PAGE = "https://osp.stat.gov.lt/statistiniu-rodikliu-analize?indicator={flow}"
OUT = PROCESSED / "lithuania_municipality.json"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def observations(flow: str, year: int) -> list[tuple[dict[str, str], float | None]]:
    raw = request(f"{OSP}/data/{flow}?startPeriod={year}&endPeriod={year}",
                  accept="application/xml")
    root = ET.fromstring(raw)
    out = []
    for obs in root.iter():
        if not obs.tag.endswith("}Obs"):
            continue
        key, value = {}, None
        for el in obs.iter():
            if el.tag.endswith("}Value") and el.get("id"):
                key[el.get("id")] = el.get("value")
            elif el.tag.endswith("}ObsValue"):
                text = el.get("value")
                value = None if text in (None, "", "NaN") else float(text)
        out.append((key, value))
    if not out:
        raise SystemExit(f"{flow} {year}: no observations -- "
                         + " ".join(raw[:400].decode("utf-8", "replace").split()))
    return out


def code_names(flow: str) -> dict[str, dict[str, str]]:
    """{code: {"lt": name, "en": name}} for the municipality code list."""
    raw = request(f"{OSP}/datastructure/LSD/{flow.split('_', 1)[1]}/latest?references=children",
                  accept="application/xml")
    root = ET.fromstring(raw)
    for codelist in root.iter():
        if codelist.tag.endswith("}Codelist") and codelist.get("id") == "savivaldybesRegdb":
            return {code.get("id"): {n.get(XML_LANG): n.text or "" for n in code
                                     if n.tag.endswith("}Name")}
                    for code in codelist if code.tag.endswith("}Code")}
    raise SystemExit(f"{flow}: no savivaldybesRegdb code list in its structure")


def expand_lt(name: str) -> str:
    return (name.replace(" r. sav.", " rajono savivaldybė")
                .replace(" m. sav.", " miesto savivaldybė")
                .replace(" sav.", " savivaldybė"))


def expand_en(name: str) -> str:
    return (name.replace(" d. mun.", " District Municipality")
                .replace(" c. mun.", " City Municipality")
                .replace(" t. mun.", " City Municipality")
                .replace(" mun.", " Municipality"))


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    names = code_names(AGES)
    year = None
    for candidate in range(2027, 2019, -1):
        try:
            rows = observations(AGES, candidate)
        except SystemExit:
            continue
        year = candidate
        break
    if year is None:
        raise SystemExit(f"{AGES}: no year from 2020 on")
    log(f"lithuania: {AGES}, {SINGLE} and {MEDIAN}, beginning of {year}")
    people: dict[str, AgeSex] = defaultdict(AgeSex)
    totals: dict[tuple[str, str], float] = {}
    unknown: dict[str, float] = defaultdict(float)
    age_var = "Demogr_amziusM1411"
    for key, value in observations(SINGLE, year):
        if value is None:
            continue
        code, sex, age = key["savivaldybesRegdb"], key["Lytis"], key[age_var]
        if age == "g000g999":
            totals[(code, sex)] = value
        elif sex == "0":
            continue
        elif age == "gxxx":
            unknown[code] += value
        else:
            people[code].add(85 if age == "g085" else int(age), "m" if sex == "1" else "f", value)
    # The five-year table is the check on the single years: the same people,
    # tabulated a second time.
    grouped: dict[tuple[str, str], float] = {}
    for key, value in rows:
        if value is not None and key["Demogr_amziaus_grM1412"] == "g000g999":
            grouped[(key["savivaldybesRegdb"], key["Lytis"])] = value
    for code, got in people.items():
        whole = totals.get((code, "0"), grouped.get((code, "0"), -1))
        if abs(got.total + unknown[code] - whole) > 0.5:
            raise SystemExit(f"{SINGLE} {code}: single years make {got.total:,.0f} "
                             f"(+{unknown[code]:,.0f} of unknown age) against {whole:,.0f}")
        if abs(whole - grouped.get((code, "0"), whole)) > 0.5:
            raise SystemExit(f"{code}: {SINGLE} counts {whole:,.0f}, {AGES} "
                             f"{grouped.get((code, '0')):,.0f}")
        for sex, count in (("1", got.men), ("2", got.women)):
            if (code, sex) in grouped and abs(count - grouped[(code, sex)]) > unknown[code] + 0.5:
                raise SystemExit(f"{code} sex {sex}: single years make {count:,.0f} against "
                                 f"{grouped[(code, sex)]:,.0f}")
    medians = {key["savivaldybesRegdb"]: value for key, value in observations(MEDIAN, year)
               if key["Lytis"] == "0" and value is not None}

    def total(code: str) -> float:
        return grouped.get((code, "0"), people[code].total + unknown[code])

    counties = sorted(c for c in people if len(c) == 2 and c.isdigit() and 1 <= int(c) <= 10)
    municipalities = sorted(c for c in people if len(c) == 2 and c.isdigit() and int(c) > 10)
    check_parts({c: total(c) for c in counties}, total("00"),
                f"{AGES} {year}: counties -> Lithuania", 0)
    check_parts({c: total(c) for c in municipalities}, total("00"),
                f"{AGES} {year}: municipalities -> Lithuania", 0)
    # Statistics Lithuania publishes the median in completed years; the one
    # interpolated here from the same single years should fall in that year.
    off = [f"{c} {medians[c]:.0f} vs {people[c].median()}" for c in counties + municipalities
           + ["00"] if c in medians and int(people[c].median() or 0) != int(medians[c])]
    log(f"  national median {people['00'].median()} (the office: {medians.get('00')} in "
        f"completed years); units whose interpolated median is not in the office's year: "
        f"{off or 'none'}")

    def fields(code: str) -> dict[str, Any]:
        ages = people[code]
        date = f"1 January {year}"
        out: dict[str, Any] = {
            "population": measure(int(round(total(code))), year=year,
                                  source=f"{SOURCE}, {AGES}"),
            "population_note": f"Resident population at the beginning of {year}.",
            "median_age": measure(ages.median(), unit="years", year=year,
                                  source=f"{SOURCE}, {SINGLE}"),
            "median_age_note": (
                "Interpolated within the single year of age that holds the middle person, from "
                f"Statistics Lithuania's residents by single year of age on {date}. The office "
                f"publishes the median in completed years ({MEDIAN}: "
                f"{medians[code]:.0f} here); this is the same median to a tenth of a year, as "
                "the rest of the map gives it." if code in medians else
                "Interpolated within the single year of age that holds the middle person."),
            "sex_ratio": measure(sex_ratio(ages.men, ages.women), unit=SEX_RATIO_UNIT, year=year,
                                 source=f"{SOURCE}, {SINGLE}"),
            "sex_ratio_note": (f"Males per 100 females among residents on {date} "
                               f"({int(ages.men):,} males, {int(ages.women):,} females)."),
            "sources": [{"field": "population/median age/sex ratio",
                         "name": f"{SOURCE}, {SINGLE}",
                         "url": PAGE.format(flow=SINGLE.split("_")[0]), "year": year}],
        }
        return out

    rows_ = {c: (expand_lt(names[c]["lt"]), "") for c in municipalities}
    aliases = {expand_lt(names[c]["lt"]): expand_en(names[c]["en"]) for c in municipalities}
    bound, _m, _l, _p = bind_rows("LTU", "admin2", rows_, aliases=aliases)
    labels = {s["id"]: s["name"] for s in load_units("LTU", "admin2")}
    records = []
    for code in municipalities:
        sid = bound.get(code)
        if sid is None:
            continue
        name = rows_[code][0]
        records.append(record(
            f"LTU-OSP-{code}", name, level="admin2", parent="LTU", country="LTU",
            codes={"osp": code}, match_by="shape_id", shape_id=sid,
            aliases=sorted({labels[sid], expand_en(names[code]["en"])} - {name}), **fields(code)))
    admin1 = {fold(u["name"].replace(" County", "")): u for u in load_units("LTU", "admin1")}
    for code in counties:
        english = names[code]["en"].replace(" county", "")
        shape = admin1.get(fold(english))
        if shape is None:
            raise SystemExit(f"lithuania: county {names[code]} has no polygon")
        records.append(record(
            f"LTU-OSP-{code}", shape["name"], level="admin1", parent="LTU", country="LTU",
            codes={"osp": code}, match_by="shape_id", shape_id=shape["id"],
            aliases=[names[code]["lt"], names[code]["en"]], **fields(code)))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
