#!/usr/bin/env python3
"""Afrobarometer Round 8: the language people speak at home, by region.

Round 9 is already on this map, for religion and ethnicity. It does not ask
about language. Round 8 does -- Q2, "Language spoken in home", coded to 458
named languages -- and language is the field Africa is emptiest of on this
map: of the twenty countries Round 8 covers that the map draws a first level
for, seventeen carry no language composition at all, and the three that do
(Mali, South Africa, Zimbabwe) have it from a census. So this module exists
for one field.

**The sampling rules are Round 9's, imported rather than restated**, because
two readings of the same survey programme must not drift apart:
``MIN_SAMPLE`` 25, ``LOW_PRECISION`` 50. A region under 25 respondents is
dropped rather than estimated, and one between 25 and 49 says on its own
record that it is imprecise. Both are the Demographic and Health Surveys'
conventions, used here so that reading this survey looks like how the field
normally reads one.

**What it is not is a census.** Afrobarometer is designed to be representative
nationally; a region is a sampling stratum, not an estimation domain. 48,084
people were interviewed across 34 countries and 457 regions, the median region
holding 72 of them. Registered first in ``ADAPTER_FILES``, the lowest
authority, so any census wins the field.

**The country label table names 37 countries and the round surveyed 34.**
Algeria, Madagascar and São Tomé and Príncipe carry a code and no
respondents -- the merge file's labels span the programme, not this round --
so they produce no records at all rather than empty ones. The guard below
still stands for a country that *is* surveyed and records no language;
nothing currently trips it.

**"Other" is carried, not dropped.** Code 9995 is a language the questionnaire
did not enumerate, which is an answer; excluding it would inflate every named
language in the region. It is published as ``Other language``. Refusals, don't
knows and missing values are excluded from the denominator, which is the usual
treatment and the one Round 9 already uses.

**The extract stores labels, not codes.** Round 9's does the opposite, because
its source is a workbook of numeric codes with a separate codebook; this one is
read from the SPSS release, which carries most of its value labels inside the
file, so resolving them at extract time removes a class of code-to-label
drift. Most, not all: the release's REGION table holds 427 of the 454 labels
the codebook lists, and the 27 it omits include every one of Tanzania's 31
regions, which read as "740.0" until the codebook fills them. The released
file is 52 MB of 425 columns and is not committed; what is committed is the
six columns this reads and the codebook's region list, re-derivable with
``--extract``.

Usage:
    python -m scripts.fetch_census.afrobarometer_r8
    python -m scripts.fetch_census.afrobarometer_r8 --extract <release>.sav
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, RAW, gap, log, record, shares,
                      write_json)
from .afrobarometer import LOW_PRECISION, MIN_SAMPLE

HERE = RAW / "afrobarometer"
EXTRACT = HERE / "r8_extract.csv.gz"
# The release's own REGION value-label table is short: it holds 427 of the 454
# the codebook lists, and Tanzania's 31 regions -- codes 740 to 770 -- are
# among the missing, so reading the file alone leaves a twenty-nine-region
# country labelled "740.0". The codebook (R8_Merge-Codebook, 28 May 2024) is
# the authority, and its list is transcribed here and used to fill whatever
# the file does not carry. The file still wins where both have a label.
REGION_CODEBOOK = HERE / "r8_region_codebook.json"
OUT = "afrobarometer_r8_language.json"

# The columns of the SPSS release this reads, and the name each is written
# under. Religion and ethnicity are extracted although nothing here publishes
# them: Round 9 covers both and is newer, but the release is not committed and
# re-extracting means having the 52 MB file again, so the two fields that might
# later rescue a region Round 9 had too few respondents for are taken now.
COLUMNS = {"country": "COUNTRY", "region": "REGION", "language": "Q2",
           "religion": "Q98A", "ethnicity": "Q81", "weight": "withinwt_ea"}

# What the questionnaire calls a non-answer. "Other" is deliberately absent:
# it is an answer, and appears below under its own label.
NOT_ANSWERED = {"Missing", "Refused", "Don't know", "Don’t know"}
OTHER = "Other"
OTHER_LABEL = "Other language"

# Afrobarometer's country name -> ISO3, written out rather than matched, for
# the reason Round 9's map gives: a name match is how one country's figures
# land on another's shapes with nothing looking wrong.
ISO3 = {
    "Algeria": "DZA", "Angola": "AGO", "Benin": "BEN", "Botswana": "BWA",
    "Burkina Faso": "BFA", "Cabo Verde": "CPV", "Cameroon": "CMR",
    "Côte d'Ivoire": "CIV", "Eswatini": "SWZ", "Ethiopia": "ETH",
    "Gabon": "GAB", "Gambia": "GMB", "Ghana": "GHA", "Guinea": "GIN",
    "Kenya": "KEN", "Lesotho": "LSO", "Liberia": "LBR", "Madagascar": "MDG",
    "Malawi": "MWI", "Mali": "MLI", "Mauritius": "MUS", "Morocco": "MAR",
    "Mozambique": "MOZ", "Namibia": "NAM", "Niger": "NER", "Nigeria": "NGA",
    "São Tomé and Príncipe": "STP", "Senegal": "SEN", "Sierra Leone": "SLE",
    "South Africa": "ZAF", "Sudan": "SDN", "Tanzania": "TZA", "Togo": "TGO",
    "Tunisia": "TUN", "Uganda": "UGA", "Zambia": "ZMB", "Zimbabwe": "ZWE",
}

# ---------------------------------------------------------------------------
# Where a survey stratum sits on the map
# ---------------------------------------------------------------------------

# Afrobarometer's region name -> the name the boundary file draws. Three
# different things live here and the distinction is the point:
#
#   * a spelling: "Huila" for Huíla, "Koulikoro" for the file's Koulikouro,
#     "Souther Nations..." for SNNPR (the release's own typo), the French
#     names of Cameroon's English-named regions. One stratum, one shape.
#   * a stratum *finer* than the map, which is summed into the shape that
#     contains it: Kweneng East and Kweneng West into Kweneng, Mfoundi
#     (Yaoundé) into Centre, Songwe -- carved out of Mbeya in 2016, after
#     these shapes were drawn -- back into Mbeya. Several strata mapping to
#     one shape are added together, weighted, which is arithmetic and not an
#     assumption.
#   * a stratum the map has merged: Niger's file draws "Tahoua/Agadez" and
#     "Zinder/Diffa" as single shapes, so all four strata land on two.
#
# What is *not* here is the opposite case -- a stratum coarser than the map --
# which is declared in COARSER below and published for no shape at all,
# because splitting it would mean assuming the composition is uniform inside
# it, and this map does not do that quietly.
REGIONS: dict[tuple[str, str], str] = {
    # Angola, Benin, Guinea, Mali, Mauritius, Morocco: spelling and accents.
    ("AGO", "Huila"): "Huíla", ("AGO", "Malange"): "Malanje",
    ("AGO", "Uige"): "Uíge",
    ("BEN", "ATACORA"): "Atakora", ("BEN", "COUFFO"): "Kouffo",
    ("GIN", "BOKÉ"): "Boke", ("GIN", "LABÉ"): "Labe",
    ("GIN", "N'ZÉRÉKORÉ"): "Nzerekore",
    ("MLI", "Koulikoro"): "Koulikouro", ("MLI", "Ségou"): "Segou",
    ("MUS", "Plaine Wilhems"): "Plaines Wilhems",
    ("MUS", "Riviere du Rempart"): "Rivière du Rempart",
    ("MAR", "BENI MELLAL-KHENIFRA"): "Béni Mellal-Khénifra",
    ("MAR", "DERAA-TAFILALT"): "Drâa-Tafilalet",
    ("MAR", "FES-MEKNES"): "Fez-Meknes",
    ("MAR", "RABAT-SALE-KENITRA"): "Rabat-Salé-Kenitra",
    ("MAR", "TANGIER-TETOUAN-HOCEIMA"): "Tangier-Tetouan-Al Hoceima",
    # Ethiopia: two spellings and one typo in the release.
    ("ETH", "Dire Dawa City Adminnistration"): "Dire Dawa",
    ("ETH", "Harari"): "Hareri",
    ("ETH", "Souther Nations, Nationalities & Peoples (SNNP)"): "SNNPR",
    # Liberia: the file's counties carry the "Grand" the survey drops.
    ("LBR", "Bassa"): "Grand Bassa", ("LBR", "Cape Mount"): "Grand Cape Mount",
    # Malawi and Sierra Leone: the same three regions, named shorter.
    ("MWI", "Center"): "Central Region", ("MWI", "North"): "Northern Region",
    ("MWI", "South"): "Southern Region",
    ("SLE", "WESTERN"): "Western Area",
    # Cameroon: the survey names the regions in French, the file in English.
    ("CMR", "Est"): "East", ("CMR", "Nord"): "North",
    ("CMR", "Extreme- Nord"): "Far North", ("CMR", "Nord Ouest"): "North-West",
    ("CMR", "Ouest"): "West", ("CMR", "Sud"): "South",
    ("CMR", "Sud Ouest"): "South-West",
    # ...and surveys its two big cities apart from the regions holding them.
    ("CMR", "Mfoundi"): "Centre", ("CMR", "Wouri"): "Littoral",
    # Namibia: Kavango was split in two in 2013 and Caprivi renamed Zambezi,
    # both after the file's shapes were drawn.
    ("NAM", "Kavango East"): "Kavango", ("NAM", "Kavango West"): "Kavango",
    ("NAM", "Zambezi"): "Caprivi",
    # Niger: the file draws two pairs as one shape each, and misspells Dosso.
    ("NER", "AGADEZ"): "Tahoua/Agadez", ("NER", "TAHOUA"): "Tahoua/Agadez",
    ("NER", "ZINDER"): "Zinder/Diffa", ("NER", "DIFFA"): "Zinder/Diffa",
    ("NER", "DOSSO"): "Dossa",
    # Togo: Lomé is surveyed apart from the Maritime region around it.
    ("TGO", "LOME"): "Maritime Region",
    # Tanzania: Zanzibar under its Swahili names, and Songwe, carved out of
    # Mbeya in 2016, back into it.
    ("TZA", "Mjini Magharibi"): "Zanzibar Urban/West",
    ("TZA", "Unguja Kaskazini"): "Zanzibar North",
    ("TZA", "Unguja Kusini"): "Zanzibar South & Central",
    ("TZA", "Pemba Kaskazini"): "North Pemba",
    ("TZA", "Pemba Kusini"): "South Pemba",
    ("TZA", "Songwe"): "Mbeya",
    # Botswana: sixteen survey districts over ten shapes. The five "Central"
    # sub-districts and the two mining townships inside them are Central; the
    # cities are the district that surrounds them.
    ("BWA", "Central Bobonong"): "Central District",
    ("BWA", "Central Boteti"): "Central District",
    ("BWA", "Central Mahalapye"): "Central District",
    ("BWA", "Central Serowe/Palapye"): "Central District",
    ("BWA", "Central Tutume"): "Central District",
    ("BWA", "Selibe Phikwe"): "Central District",
    ("BWA", "Sowa"): "Central District",
    ("BWA", "Francistown"): "North-East District",
    ("BWA", "North East"): "North-East District",
    ("BWA", "Gaborone"): "South-East District",
    ("BWA", "Lobatse"): "South-East District",
    ("BWA", "South East"): "South-East District",
    ("BWA", "Barolong"): "Southern District",
    ("BWA", "Ngwaketse"): "Southern District",
    ("BWA", "Ngwaketse West"): "Southern District",
    ("BWA", "Jwaneng"): "Southern District",
    ("BWA", "Kweneng East"): "Kweneng District",
    ("BWA", "Kweneng West"): "Kweneng District",
    ("BWA", "Ngamiland East"): "North-West District",
    ("BWA", "Ngamiland West"): "North-West District",
    ("BWA", "Kgalagadi North"): "Kgalagadi District",
    ("BWA", "Kgalagadi South"): "Kgalagadi District",
    ("BWA", "Chobe"): "Chobe District", ("BWA", "Ghanzi"): "Ghanzi District",
    ("BWA", "Kgatleng"): "Kgatleng District",
    # Uganda: eleven sub-regions over the file's four regions.
    ("UGA", "Acholi"): "Northern Region", ("UGA", "Lango"): "Northern Region",
    ("UGA", "Karamoja"): "Northern Region",
    ("UGA", "West Nile"): "Northern Region",
    ("UGA", "Ankole"): "Western Region", ("UGA", "Kigezi"): "Western Region",
    ("UGA", "Tooro"): "Western Region", ("UGA", "Bunyoro"): "Western Region",
    ("UGA", "Buganda"): "Central Region", ("UGA", "Busoga"): "Eastern Region",
    # Côte d'Ivoire: the survey uses the 31-region layout, the file the 14
    # districts those regions make up.
    ("CIV", "Agneby-Tiassa"): "Lagunes", ("CIV", "Gbeke"): "Valle Du Bandama",
    ("CIV", "Gontougo"): "Zanzan", ("CIV", "Guemon"): "Montagnes",
    ("CIV", "Tonkpi"): "Montagnes", ("CIV", "Gôh"): "Goh-Djiboua",
    ("CIV", "Haut-Sassandra"): "Sassandra-Marahoue",
    ("CIV", "Marahoue"): "Sassandra-Marahoue",
    ("CIV", "Nawa"): "Bas-Sassandra", ("CIV", "Poro"): "Savanes",
}

# Countries whose survey stratum is *coarser* than the shapes the map draws.
# Cabo Verde is surveyed in five strata over 22 municipalities, Sudan in six
# macro-regions over 19 states, Tunisia in seven over 24 governorates. A
# composition for "North West" is a fact about a seventh of Tunisia and not
# about Jendouba, Béja, El Kef or Siliana, and spreading it over the four
# would state something nobody measured. Nothing is written for them, and the
# run says so rather than leaving the reader to notice.
COARSER = {"CPV": (5, 22), "SDN": (6, 19), "TUN": (7, 24)}

SOURCE = "Afrobarometer Round 8 (2019-2021)"
URL = "https://www.afrobarometer.org/data/"
LICENCE = "Afrobarometer data use policy"
UNIVERSE = (
    "Language spoken in home, from Afrobarometer Round 8 (2019-2021), a "
    "nationally representative sample of citizens of voting age. This is a "
    "survey estimate and not a census count: it carries sampling error, and "
    "regions with fewer than 25 respondents are omitted rather than estimated.")
NO_LANGUAGE = (
    "Afrobarometer Round 8 records no language for any respondent in this "
    "country, so no composition is built from the round. That is a limit of "
    "this release, not a statement that the question is never asked.")


def extract(path: str) -> int:
    """Re-derive the committed extract from the SPSS release."""
    import pyreadstat                                # noqa: PLC0415 -- optional

    log(f"afrobarometer_r8: reading {path}")
    frame, meta = pyreadstat.read_sav(path, usecols=list(COLUMNS.values()))
    labels = {column: dict(meta.variable_value_labels.get(column, {}))
              for column in COLUMNS.values()}
    region = COLUMNS["region"]
    book = json.loads(REGION_CODEBOOK.read_text(encoding="utf-8"))
    filled = 0
    for key, name in book.items():
        if float(key) not in labels[region]:
            labels[region][float(key)] = name
            filled += 1
    log(f"  REGION: {len(labels[region]) - filled} labels in the release, "
        f"{filled} filled from the codebook")

    def label(column: str, value: Any) -> str:
        if value != value or value is None:          # NaN
            return ""
        table = labels[column]
        return str(table.get(value, value)).strip()

    HERE.mkdir(parents=True, exist_ok=True)
    rows = 0
    with gzip.open(EXTRACT, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(COLUMNS))
        for values in zip(*(frame[c] for c in COLUMNS.values())):
            out = [label(c, v) if c != COLUMNS["weight"] else v
                   for c, v in zip(COLUMNS.values(), values)]
            if not out[0] or not out[1]:             # no country or no region
                continue
            writer.writerow(out)
            rows += 1
    log(f"  wrote {EXTRACT} ({rows:,} rows)")
    return rows


def tabulate() -> tuple[dict[tuple[str, str], dict[str, float]],
                        dict[tuple[str, str], int], set[str]]:
    """Weighted language counts per country/region, the unweighted n, and the
    countries the round records no language for at all."""
    tally: dict[tuple[str, str], dict[str, float]] = {}
    sample: dict[tuple[str, str], int] = {}
    answered: set[str] = set()
    seen: set[str] = set()
    with gzip.open(EXTRACT, "rt", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            country, region = row["country"], row["region"]
            seen.add(country)
            key = (country, region)
            sample[key] = sample.get(key, 0) + 1
            try:
                weight = float(row["weight"])
            except (TypeError, ValueError):
                weight = 1.0
            name = row["language"]
            if not name or name in NOT_ANSWERED:
                continue
            answered.add(country)
            name = OTHER_LABEL if name == OTHER else name
            cell = tally.setdefault(key, {})
            cell[name] = cell.get(name, 0.0) + weight
    return tally, sample, seen - answered


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", metavar="SAV",
                    help="re-derive the committed extract from the SPSS release")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.extract:
        extract(args.extract)
        return 0

    tally, sample, silent = tabulate()
    log(f"afrobarometer_r8: {len(sample)} country/region cells, "
        f"{sum(sample.values()):,} interviews")
    for country in sorted(silent):
        log(f"  {country}: the round records no language")

    # Strata that land on one shape are added together before anything is
    # published: Kweneng East and Kweneng West are one shape's worth of
    # people, and emitting them as two records would put the second on top of
    # the first. The sample sizes add too, which is what the 25-respondent
    # floor should be applied to -- a shape covered by two strata of 20 was
    # interviewed 40 times.
    merged: dict[tuple[str, str], dict[str, float]] = {}
    merged_n: dict[tuple[str, str], int] = {}
    strata: dict[tuple[str, str], list[str]] = {}
    skipped_coarse: dict[str, int] = {}
    for (country, region), counts in sorted(tally.items()):
        iso = ISO3.get(country)
        if not iso:
            raise SystemExit(f"afrobarometer_r8: no ISO3 for {country!r}")
        if iso in COARSER:
            skipped_coarse[iso] = skipped_coarse.get(iso, 0) + 1
            continue
        shape = REGIONS.get((iso, region), region)
        key = (iso, shape)
        cell = merged.setdefault(key, {})
        for group, weight in counts.items():
            cell[group] = cell.get(group, 0.0) + weight
        merged_n[key] = merged_n.get(key, 0) + sample[(country, region)]
        strata.setdefault(key, []).append(region)

    records: list[dict[str, Any]] = []
    dropped = low = 0
    for (iso, shape), counts in sorted(merged.items()):
        n = merged_n[(iso, shape)]
        if n < MIN_SAMPLE:
            dropped += 1
            continue
        region = shape
        rows = shares(counts)
        if not rows:
            continue
        note = f"{UNIVERSE} This region: {n} respondents."
        parts = strata[(iso, shape)]
        if parts != [shape]:
            note += (f" The survey stratifies this shape as "
                     f"{', '.join(sorted(parts))}, summed here.")
        if n < LOW_PRECISION:
            low += 1
            note += (" Fewer than 50 respondents, so this share is imprecise "
                     "and should be read as indicative.")
        records.append(record(
            f"{iso}-AB8-{region}", region, level="admin1", parent=iso,
            country=iso, language=rows, language_year=2020,
            language_note=note,
            sources=[{"field": "language", "name": SOURCE, "url": URL,
                      "year": 2020, "license": LICENCE}]))
    # A country the round records nothing for still gets a stated reason, on
    # every region it interviewed in: a gap that says why is the point.
    for (country, region), n in sorted(sample.items()):
        if country not in silent or n < MIN_SAMPLE:
            continue
        iso = ISO3.get(country)
        if not iso:
            raise SystemExit(f"afrobarometer_r8: no ISO3 for {country!r}")
        shape = REGIONS.get((iso, region), region)
        records.append(record(
            f"{iso}-AB8-{shape}", shape, level="admin1", parent=iso,
            country=iso, language=gap(NOT_AVAILABLE, NO_LANGUAGE),
            sources=[{"field": "language", "name": SOURCE, "url": URL,
                      "year": 2020, "license": LICENCE}]))
    kept = sum(1 for r in records if isinstance(r.get("language"), list))
    log(f"  {kept} shapes carry a language composition, {dropped} dropped "
        f"under {MIN_SAMPLE} respondents, {low} marked low precision")
    for iso, n in sorted(skipped_coarse.items()):
        strat, shapes_drawn = COARSER[iso]
        log(f"  {iso}: {n} strata not written -- the survey stratifies the "
            f"country in {strat} where the map draws {shapes_drawn}")
    write_json(args.out or PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
