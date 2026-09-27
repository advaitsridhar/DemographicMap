#!/usr/bin/env python3
"""Lithuania: population, median age and sex ratio for the 60 municipalities and 10 counties.

Statistics Lithuania's Official Statistics Portal answers SDMX 2.1 at
osp-rs.stat.gov.lt. Every observation in its "generic" data message carries
its own key (``dimensionAtObservation="AllDimensions"``), so the reader here
takes each ``Obs`` with its ``ObsKey`` rather than looking for series.

* **S3R167_M3010203** -- resident population at the beginning of the year by
  municipality, sex and five-year age group. The population and the sex ratio
  come from it, and its age groups are checked against its totals.
* **S3R629_M3010217** -- the median age at the beginning of the year, by
  municipality and sex, which the office computes from single years. The
  brief's rule is to take the office's own median where it publishes one for
  exactly the unit, and it does; it publishes it in whole years. The median
  interpolated from the five-year groups is printed beside it as a check.

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
from .cod_ps_age import grouped_median
from .nordic_common import SEX_RATIO_UNIT, bind_rows, check_parts, load_units, request, sex_ratio

OSP = "https://osp-rs.stat.gov.lt/rest_xml"
AGES = "S3R167_M3010203"
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
    log(f"lithuania: {AGES} and {MEDIAN}, beginning of {year}")
    groups: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for key, value in rows:
        if value is None:
            continue
        groups[key["savivaldybesRegdb"]][key["Lytis"]][key["Demogr_amziaus_grM1412"]] = value
    medians = {key["savivaldybesRegdb"]: value for key, value in observations(MEDIAN, year)
               if key["Lytis"] == "0" and value is not None}

    def total(code: str, sex: str) -> float:
        return groups[code][sex].get("g000g999", 0.0)

    for code, by_sex in groups.items():
        if abs(total(code, "1") + total(code, "2") - total(code, "0")) > 0.5:
            raise SystemExit(f"{AGES} {code}: males and females do not make the total")
        for sex, cells in by_sex.items():
            parts = sum(v for g, v in cells.items() if g != "g000g999")
            if abs(parts - cells.get("g000g999", 0)) > 0.5:
                raise SystemExit(f"{AGES} {code} sex {sex}: age groups make {parts:,.0f} of "
                                 f"{cells.get('g000g999', 0):,.0f}")
    counties = sorted(c for c in groups if len(c) == 2 and c.isdigit() and 1 <= int(c) <= 10)
    municipalities = sorted(c for c in groups if len(c) == 2 and c.isdigit() and int(c) > 10)
    check_parts({c: total(c, "0") for c in counties}, total("00", "0"),
                f"{AGES} {year}: counties -> Lithuania", 0)
    check_parts({c: total(c, "0") for c in municipalities}, total("00", "0"),
                f"{AGES} {year}: municipalities -> Lithuania", 0)

    def interpolated(code: str) -> float | None:
        cells = groups[code]["0"]
        bands = []
        for group, n in cells.items():
            if group in ("g000g999", "gxxx"):
                continue
            low = int(group[1:4])
            high = int(group[5:8]) if len(group) > 4 else None
            bands.append((low, high, n))
        return grouped_median(sorted(bands, key=lambda b: b[0]))

    worst = max(abs(medians[c] - (interpolated(c) or 0)) for c in counties + municipalities
                if c in medians)
    log(f"  national median: office {medians.get('00')}, from five-year groups "
        f"{interpolated('00')}; largest difference over all units {worst:.1f} years")

    def fields(code: str) -> dict[str, Any]:
        men, women = total(code, "1"), total(code, "2")
        date = f"1 January {year}"
        out: dict[str, Any] = {
            "population": measure(int(round(total(code, "0"))), year=year,
                                  source=f"{SOURCE}, {AGES}"),
            "population_note": f"Resident population at the beginning of {year}.",
            "sex_ratio": measure(sex_ratio(men, women), unit=SEX_RATIO_UNIT, year=year,
                                 source=f"{SOURCE}, {AGES}"),
            "sex_ratio_note": (f"Males per 100 females among residents on {date} "
                               f"({int(men):,} males, {int(women):,} females)."),
            "sources": [{"field": "population/sex ratio", "name": f"{SOURCE}, {AGES}",
                         "url": PAGE.format(flow=AGES.split("_")[0]), "year": year}],
        }
        if code in medians:
            out["median_age"] = measure(medians[code], unit="years", year=year,
                                        source=f"{SOURCE}, {MEDIAN}")
            out["median_age_note"] = (
                f"The median age at the beginning of {year} as Statistics Lithuania publishes it "
                "for the unit, in whole years.")
            out["sources"].append({"field": "median age", "name": f"{SOURCE}, {MEDIAN}",
                                   "url": PAGE.format(flow=MEDIAN.split("_")[0]), "year": year})
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
