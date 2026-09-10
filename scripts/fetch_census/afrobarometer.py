#!/usr/bin/env python3
"""Afrobarometer Round 9: religion and ethnicity by region, for 39 countries.

This is the first source on this map that is a **survey rather than a count**,
and everything below follows from that. 53,444 people were interviewed across
39 African countries; the questions are Q95 "What is your religion, if any?"
and Q84a "What is your ethnic community, cultural group or tribe?", and every
respondent carries the region they were interviewed in. That is exactly the
shape this map wants, for 36 countries that have nothing at all.

What it is not is a census. Afrobarometer is designed to be representative
**nationally**; a region is a sampling stratum, not an estimation domain. The
median region here holds 72 respondents and the thinnest holds 8, so a share
drawn from one carries an interval far wider than any census figure on this
map. Three rules keep that from being published as though it were precision:

* **Regions under MIN_SAMPLE respondents are dropped**, not estimated. 25 is
  the Demographic and Health Surveys' own threshold, and using the field's
  convention rather than inventing one keeps this comparable to how the source
  material is normally read. It leaves 442 of 519 regions.
* **A region between 25 and 49 is marked low precision** so the map can say so.
  DHS prints those in parentheses for the same reason.
* **"Not asked in the country" is honoured as a refusal to answer, not a zero.**
  Mauritania was never asked about religion, and Sudan, Tunisia and the
  Seychelles were never asked about ethnicity. Building a composition for them
  out of the remaining codes would invent a figure where a question does not
  exist, so those become ``not_collected`` -- the same status the EU countries
  that decline to ask about ethnicity already carry here.

Placed **first** in ADAPTER_FILES, which is the lowest authority: Ethiopia,
Mali and South Africa already have census figures and those must win. Because
merge_adapter works field by field, this still fills a field the census left
empty without touching one it filled.

The published file is a 24 MB workbook of 400-odd columns. Only five are read,
so what is committed is an extract of those five -- reproducible from the
release with ``--extract`` -- rather than the whole thing.

Usage:
    python -m scripts.fetch_census.afrobarometer
    python -m scripts.fetch_census.afrobarometer --extract R9.Merge_39ctry.xlsx
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from typing import Any

from ._shared import (NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, log,
                      record, shares, write_json)

HERE = RAW / "afrobarometer"
EXTRACT = HERE / "r9_extract.csv.gz"
LABELS = HERE / "r9_labels.json"
OUT = "afrobarometer_region.json"

# Column positions in the published merge file, confirmed against the codebook.
COLUMNS = {"country": 1, "region": 9, "ethnicity": 297, "religion": 340, "weight": 396}

# DHS suppresses a cell below 25 unweighted cases and parenthesises 25-49.
MIN_SAMPLE = 25
LOW_PRECISION = 50

# Codes that are not an answer. 9994 is its own case and handled separately:
# the others are one person declining, 9994 is the country never being asked.
NOT_ANSWERED = {"-1", "9998", "9999"}
NOT_ASKED = "9994"
# A respondent who claims no ethnic group, which is an answer and not a gap.
NATIONAL_ONLY = "9990"

# Afrobarometer's country code -> ISO3. Written out rather than matched on
# name: "Congo- Brazzaville" (the codebook's own spacing) is COG, the Republic
# of the Congo, and a name match that reached for COD instead would put one
# country's figures on the other's shapes without anything looking wrong.
ISO3 = {
    "2": "AGO", "3": "BEN", "4": "BWA", "5": "BFA", "6": "CPV", "7": "CMR",
    "8": "COG", "9": "CIV", "10": "SWZ", "11": "ETH", "12": "GAB", "13": "GMB",
    "14": "GHA", "15": "GIN", "16": "KEN", "17": "LSO", "18": "LBR", "19": "MDG",
    "20": "MWI", "21": "MLI", "22": "MRT", "23": "MUS", "24": "MAR", "25": "MOZ",
    "26": "NAM", "27": "NER", "28": "NGA", "29": "STP", "30": "SEN", "31": "SYC",
    "32": "SLE", "33": "ZAF", "34": "SDN", "35": "TZA", "36": "TGO", "37": "TUN",
    "38": "UGA", "39": "ZMB", "40": "ZWE",
}

SOURCE = "Afrobarometer Round 9 (2021-2023)"
UNIVERSE = ("Afrobarometer Round 9, a nationally representative sample of "
            "citizens of voting age. Regional shares are survey estimates, not "
            "census counts: they carry sampling error, and regions with fewer "
            "than 25 respondents are omitted rather than estimated.")


def load_labels() -> dict[str, dict[str, str]]:
    return json.loads(LABELS.read_text(encoding="utf-8"))


def code(value: Any) -> str | None:
    """Codes arrive as floats from the workbook; compare them as integers."""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return None


# The codebook's "X only" means the respondent said X and named no sub-group,
# which reads as an odd label on a map. The plain name is what they said.
UNSPECIFIED = {"Christian only": "Christian", "Muslim only": "Muslim",
               "Sunni only": "Sunni"}


def clean(label: str) -> str:
    """Drop the codebook's parenthetical gloss, keeping the group's name."""
    name = re.sub(r"\s*\((?:e\.g\.|i\.e\.|Do not).*$", "", label).strip().rstrip(",")
    return UNSPECIFIED.get(name, name)


def extract(path: str) -> int:
    """Re-derive the committed extract from the published workbook."""
    import openpyxl                                  # noqa: PLC0415 -- optional

    log(f"afrobarometer: reading {path}")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book[book.sheetnames[0]]
    HERE.mkdir(parents=True, exist_ok=True)
    rows = 0
    with gzip.open(EXTRACT, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(COLUMNS))
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row is None or len(row) <= COLUMNS["weight"]:
                continue
            if row[COLUMNS["country"]] is None:
                continue
            writer.writerow([row[i] for i in COLUMNS.values()])
            rows += 1
    book.close()
    log(f"  wrote {EXTRACT} ({rows} rows)")
    return rows


def tabulate() -> tuple[dict[tuple[str, str], dict[str, dict[str, float]]],
                        dict[tuple[str, str], int], set[tuple[str, str]]]:
    """Weighted counts per country/region/field, plus the unweighted n."""
    tally: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    sample: dict[tuple[str, str], int] = {}
    never_asked: set[tuple[str, str]] = set()
    asked: set[tuple[str, str]] = set()
    with gzip.open(EXTRACT, "rt", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            country, region = code(row["country"]), code(row["region"])
            if not country or not region:
                continue
            try:
                weight = float(row["weight"])
            except (TypeError, ValueError):
                weight = 1.0
            key = (country, region)
            sample[key] = sample.get(key, 0) + 1
            cell = tally.setdefault(key, {"religion": {}, "ethnicity": {}})
            for field, column in (("religion", "religion"), ("ethnicity", "ethnicity")):
                value = code(row[column])
                if value == NOT_ASKED:
                    never_asked.add((country, field))
                    continue
                asked.add((country, field))
                if value is None or value in NOT_ANSWERED:
                    continue
                cell[field][value] = cell[field].get(value, 0.0) + weight
    # A country counts as never asked only if no respondent in it was asked.
    return tally, sample, {pair for pair in never_asked if pair not in asked}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", metavar="XLSX",
                    help="re-derive the committed extract from the published workbook")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.extract:
        extract(args.extract)
        return 0

    labels = load_labels()
    tally, sample, never_asked = tabulate()
    log(f"afrobarometer: {len(sample)} country/region cells, "
        f"{sum(sample.values())} interviews")
    for country, field in sorted(never_asked):
        log(f"  {labels['COUNTRY'].get(country, country)}: {field} not asked")

    records: list[dict[str, Any]] = []
    dropped = low = 0
    for (country, region), cell in sorted(tally.items()):
        n = sample[(country, region)]
        name = labels["REGION"].get(region)
        if not name:
            continue
        if n < MIN_SAMPLE:
            dropped += 1
            continue
        fields: dict[str, Any] = {}
        for field, table in (("religion", labels["Q95"]), ("ethnicity", labels["Q84A"])):
            if (country, field) in never_asked:
                fields[field] = gap(NOT_COLLECTED)
                fields[f"{field}_note"] = (
                    f"Afrobarometer did not ask about {field} in this country.")
                continue
            counts = {clean(table.get(c, c)) if c != NATIONAL_ONLY
                      else "No ethnic group": v
                      for c, v in cell[field].items()}
            rows = shares(counts)
            fields[field] = rows or gap(NOT_AVAILABLE)
            if rows:
                note = f"{UNIVERSE} This region: {n} respondents."
                if n < LOW_PRECISION:
                    note += (" Fewer than 50 respondents, so this share is"
                             " imprecise and should be read as indicative.")
                fields[f"{field}_note"] = note
        if n < LOW_PRECISION:
            low += 1
        iso = ISO3.get(country)
        if not iso:
            raise SystemExit(f"afrobarometer: no ISO3 for country code {country}")
        records.append(record(
            f"{iso}-AB9-{region}", name, level="admin1", parent=iso,
            country=iso,
            **fields,
            sources=[{"field": "religion/ethnicity", "name": SOURCE,
                      "url": "https://www.afrobarometer.org/data/",
                      "license": "Afrobarometer data use policy"}],
        ))
    log(f"  {len(records)} regions kept, {dropped} dropped under {MIN_SAMPLE} "
        f"respondents, {low} marked low precision")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
