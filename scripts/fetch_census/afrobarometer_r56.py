#!/usr/bin/env python3
"""Afrobarometer Rounds 5 and 6: Burundi and Egypt, the two countries Round 9 misses.

Round 9 surveys 39 countries and is the source for all three fields on every
one of them. Three African countries appear in the earlier merged rounds and
not in Round 9 -- Algeria, Burundi and Egypt -- and this module exists for
them. It publishes two.

The question is not "which round is newest" but "which is the newest round
that *asks*". Afrobarometer writes a real code, "Not asked in country", when
a question was dropped from a national questionnaire, and reading that as a
missing answer rather than a missing question would build a composition out
of whatever remained. Counting substantive answers per country, field and
round across Rounds 5 to 9 turns up exactly two places anywhere in the series
where the newest round covering a country is silent on a field an older one
asked:

    Burundi   ethnicity   Round 6 does not ask; Round 5 does (1,129 answers)
    Egypt     religion    Round 6 does not ask; Round 5 does (1,190 answers)

So the rounds are mixed *per field*, and ``choose()`` below re-derives that
from the extract on every run rather than trusting the table above. Each
field carries its own year, read from the round's own interview dates:

    Burundi religion, language   Round 6, 29 Sep - 10 Oct 2014      2014
    Burundi ethnicity            Round 5, 28 Nov - 10 Dec 2012      2012
    Egypt religion               Round 5, 8 - 19 Mar 2013           2013

**Egypt gets no language and no ethnicity.** Ethnicity is never asked there.
Language is asked, and is refused anyway: both rounds code every one of 2,388
Egyptian respondents to a single value -- "Arabic" in Round 5, "Egyptian
Arabic" in Round 6 -- and a variable with one value is a constant the field
team entered, not a composition anyone measured. Publishing it would paint
Egypt uniformly Arabic-speaking on a survey's authority and hide Nubian,
Beja, Siwi and Domari behind it. Burundi's language question is not the same
case and is published: its respondents could and did name a second language,
and 8 of 1,200 said Swahili rather than Kirundi.

**Algeria is refused outright**, and the reason is worth stating because the
first look suggested otherwise. Round 6 stratifies Algeria in 8 multi-wilaya
regions ("North Middle Region") where the map draws 48 wilayas, so it is
plainly coarser than the shapes. Round 5 *does* name wilayas -- 36 of them --
which looks usable until the allocation is read: Oran, 1.6 million people,
holds 10 interviews and Tamanghasset, 200,000, holds 128. Where the answer
can be checked against something known, it fails. Tizi Ouzou is the heart of
Kabylie and Tamazight is the language of the overwhelming majority there;
Round 5 interviewed 10 people in it and recorded no Amazigh speaker at all,
and neighbouring Bejaia, equally Kabyle, comes out 15% Amazigh on 39
interviews -- enough to clear the 25-respondent floor and be published. That
is not an imprecise figure, it is a wrong one, and a wrong figure on a shape
is worse than an empty shape: the empty one says it is empty.

Rumonge is Burundi's eighteenth province and has no stratum in either round,
because it did not exist: it was split from Bururi and Bujumbura Rural on 26
March 2015, after both fieldworks. It is written out with that as its reason
rather than left to the generic one.

Registered **first** in ADAPTER_FILES with the other two survey files, which
is the lowest authority. Nothing else on this map writes to Burundi or Egypt
today, so nothing is at stake in the order; it is there because a survey
ranks below a count whatever else happens to be present.

The releases are 50 MB of microdata and are not committed. What is committed
is the seven columns this reads, for the three countries above only --
reproducible with ``--extract``.

Usage:
    python -m scripts.fetch_census.afrobarometer_r56
    python -m scripts.fetch_census.afrobarometer_r56 --extract R5.sav R6.sav
"""

from __future__ import annotations

import argparse
import csv
import gzip
from typing import Any

from ._shared import (NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, log,
                      record, shares, write_json)
from .afrobarometer import LOW_PRECISION, MIN_SAMPLE, clean

HERE = RAW / "afrobarometer"
EXTRACT = HERE / "r56_extract.csv.gz"
OUT = "afrobarometer_r56.json"

# The two releases' variable names. Round 5 asks ethnicity as Q84 and Round 6
# as Q87; both call religion Q98a and language Q2, and both carry one
# within-country weight rather than Round 8's and 9's household/EA pair.
ROUNDS: dict[str, dict[str, str]] = {
    "R5": {"country": "COUNTRY", "region": "REGION", "language": "Q2",
           "ethnicity": "Q84", "religion": "Q98A", "weight": "withinwt",
           "date": "DATEINTR"},
    "R6": {"country": "COUNTRY", "region": "REGION", "language": "Q2",
           "ethnicity": "Q87", "religion": "Q98A", "weight": "withinwt",
           "date": "DATEINTR"},
}
FIELDS = ("religion", "ethnicity", "language")
# Newest first, which is the order choose() walks.
NEWEST_FIRST = ("R6", "R5")

# Only these three are extracted: every other country in the two rounds is in
# Round 9, which is newer and is already read.
COUNTRIES = {"Burundi": "BDI", "Egypt": "EGY", "Algeria": "DZA"}
REFUSED = {"DZA"}

# Not an answer, in every spelling the two releases use. "Not asked in
# country" is deliberately here *and* counted separately: as a share it is
# not an answer, but a country where every respondent carries it is a country
# that was never asked, which is a different statement and gets a different
# status.
NOT_ANSWERED = {"missing", "refused", "don't know", "don’t know", "",
                "nan", "no further reply"}
NOT_ASKED = ("not asked in country", "not asked in this country")
# A respondent who names no ethnic group, which is an answer and not a gap.
# Matched on its opening words because the two releases punctuate the rest
# differently -- Round 5 writes 'or "doesn\'t think of self in those terms"'
# and Round 6 writes "or 'doesnt think of self in those terms'" -- and an
# exact match would quietly stop recognising one of them.
NATIONAL_ONLY = "national identity only"
NATIONAL_ONLY_LABEL = "No ethnic group"
OTHER = {"others": "Other", "other": "Other"}

# Survey stratum -> the name the map draws. Burundi's two Bujumburas are the
# trap: the round's "Bujumbura" is the rural province and its "Bujumbura
# Marie" -- the release's own misspelling of Mairie -- is the city. Matching
# either on the bare name would land the capital's figures on the countryside.
REGIONS: dict[tuple[str, str], str] = {
    ("BDI", "Bujumbura"): "Bujumbura Rural",
    ("BDI", "Bujumbura Marie"): "Bujumbura Mairie",
    ("BDI", "Cankuza"): "Cankuzo",
    ("BDI", "Karusi"): "Karuzi",
    ("BDI", "Ruyiga"): "Ruyigi",
    # Egypt's governorates, in the map's spelling. Two of the map's names are
    # misspelled -- "Luxor Governate", "Minya Governate" -- and are matched as
    # they are drawn rather than as they should be; correcting a shape's name
    # is a different job from reading a survey.
    ("EGY", "Alexandria"): "Alexandria Governorate",
    ("EGY", "Al-Sharqia"): "Al Sharqia Governorate",
    ("EGY", "Asyut"): "Asyut Governorate",
    ("EGY", "Assyout"): "Asyut Governorate",
    ("EGY", "Aswan"): "Aswan Governorate",
    ("EGY", "Beheira"): "Beheira Governorate",
    ("EGY", "Beni Suef"): "Beni Suef Governorate",
    ("EGY", "Beni Souif"): "Beni Suef Governorate",
    ("EGY", "Cairo"): "Cairo Governorate",
    ("EGY", "Charqia"): "Al Sharqia Governorate",
    ("EGY", "Dakahlia"): "Dakahlia Governorate",
    ("EGY", "Damietta"): "Damietta Governorate",
    ("EGY", "El Feyoum"): "Faiyum Governorate",
    ("EGY", "El Menya"): "Minya Governate",
    ("EGY", "Faiyum"): "Faiyum Governorate",
    ("EGY", "Gharbia"): "Gharbiyya Governorate",
    ("EGY", "Giza"): "Giza Governorate",
    ("EGY", "Ismailia"): "Ismailia Governorate",
    ("EGY", "Kafr el-Sheikh"): "Kafr el-Sheikh Governorate",
    ("EGY", "Luxor"): "Luxor Governate",
    ("EGY", "Matrouh"): "Matrouh Governorate",
    ("EGY", "Minya"): "Minya Governate",
    ("EGY", "Monufia"): "Monufia Governorate",
    ("EGY", "Port Said"): "Port Said Governorate",
    ("EGY", "Qalyubia"): "Qalyubia Governorate",
    ("EGY", "Qena"): "Qena Governorate",
    # "Al Bahr al Ahmar" is the Red Sea governorate under its Arabic name, and
    # Round 5 uses both codes for it. They are one shape and are summed.
    ("EGY", "Al Bahr al Ahmar"): "Red Sea Governorate",
    ("EGY", "Red Sea"): "Red Sea Governorate",
    ("EGY", "Sohag"): "Sohag Governorate",
    ("EGY", "Souhag"): "Sohag Governorate",
    ("EGY", "Suez"): "Suez Governorate",
}

# A shape no round has a stratum for, and why. Left out, it would fall to the
# build's generic "nothing was read for this unit", which would be true and
# would not be the reason.
UNSAMPLED = {
    ("BDI", "Rumonge"): (
        "Rumonge did not exist when either round was in the field: it was "
        "split from Bururi and Bujumbura Rural on 26 March 2015, and "
        "Afrobarometer interviewed in Burundi in November 2012 and October "
        "2014. Neither round has a stratum for it, and dividing its parents' "
        "shares between them would be a guess about which side of a new "
        "border each respondent lived on."),
}

SOURCES = {"R5": ("Afrobarometer Round 5 (2011-2013)", "AB5"),
           "R6": ("Afrobarometer Round 6 (2014-2015)", "AB6")}
URL = "https://www.afrobarometer.org/data/"
LICENCE = "Afrobarometer data use policy"
UNIVERSE = ("Afrobarometer {round}, a nationally representative sample of "
            "citizens of voting age. Regional shares are survey estimates and "
            "not census counts: they carry sampling error, and regions with "
            "fewer than 25 respondents are omitted rather than estimated.")
NEVER_ASKED = ("Afrobarometer did not ask about {field} in this country in "
               "either round that surveyed it.")
ONE_VALUE = (
    "Afrobarometer asked about language here but coded every one of its "
    "{n:,} Egyptian respondents, across both rounds, to a single value. A "
    "variable with one value is a constant the field team entered rather "
    "than a composition anyone measured, so none is built from it.")


def extract(paths: dict[str, str]) -> int:
    """Re-derive the committed extract from the two SPSS releases."""
    import pyreadstat                                # noqa: PLC0415 -- optional

    HERE.mkdir(parents=True, exist_ok=True)
    columns = ["round", "country", "region", "religion", "ethnicity",
               "language", "weight", "year"]
    rows = 0
    with gzip.open(EXTRACT, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for rnd in NEWEST_FIRST:
            path = paths[rnd]
            names = ROUNDS[rnd]
            log(f"afrobarometer_r56: reading {rnd} from {path}")
            frame, meta = pyreadstat.read_sav(path, usecols=list(names.values()))
            labels = {c: dict(meta.variable_value_labels.get(c, {}))
                      for c in names.values()}

            def label(column: str, value: Any) -> str:
                if value is None or value != value:            # NaN
                    return ""
                return str(labels[column].get(value, value)).strip()

            kept = 0
            for values in zip(*(frame[c] for c in names.values())):
                cell = dict(zip(names, values))
                country = label(names["country"], cell["country"])
                if country not in COUNTRIES:
                    continue
                region = label(names["region"], cell["region"])
                if not region:
                    continue
                date = cell["date"]
                writer.writerow([
                    rnd, country, region,
                    label(names["religion"], cell["religion"]),
                    label(names["ethnicity"], cell["ethnicity"]),
                    label(names["language"], cell["language"]),
                    cell["weight"],
                    getattr(date, "year", ""),
                ])
                kept += 1
            log(f"  {kept:,} rows for {', '.join(sorted(COUNTRIES))}")
            rows += kept
    log(f"  wrote {EXTRACT} ({rows:,} rows)")
    return rows


def read() -> list[dict[str, str]]:
    with gzip.open(EXTRACT, "rt", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def answer(value: str) -> str | None:
    """The group a respondent named, or None if they named none."""
    low = value.strip().lower()
    if low in NOT_ANSWERED or low.startswith(NOT_ASKED):
        return None
    if low.startswith(NATIONAL_ONLY):
        return NATIONAL_ONLY_LABEL
    return clean(OTHER.get(low, value.strip()))


def choose(rows: list[dict[str, str]]) -> dict[tuple[str, str], str | None]:
    """The newest round that asks each country's field, measured not assumed.

    A field with one distinct answer across a whole country is not a
    measurement -- see Egypt's language in the docstring -- so two distinct
    answers is the floor for counting a round as having asked.
    """
    seen: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        for field in FIELDS:
            name = answer(row[field])
            if name:
                seen.setdefault((row["country"], field, row["round"]),
                                set()).add(name)
    out: dict[tuple[str, str], str | None] = {}
    for country in COUNTRIES:
        for field in FIELDS:
            out[(country, field)] = next(
                (r for r in NEWEST_FIRST
                 if len(seen.get((country, field, r), ())) > 1), None)
    return out


def year_of(rows: list[dict[str, str]], country: str, rnd: str) -> int | None:
    years = {int(r["year"]) for r in rows
             if r["country"] == country and r["round"] == rnd and r["year"]}
    return years.pop() if len(years) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract", nargs=2, metavar=("R5_SAV", "R6_SAV"),
                    help="re-derive the committed extract from the releases")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.extract:
        extract(dict(zip(("R5", "R6"), args.extract)))
        return 0

    rows = read()
    picked = choose(rows)
    for (country, field), rnd in sorted(picked.items()):
        log(f"afrobarometer_r56: {country} {field}: "
            f"{SOURCES[rnd][0] if rnd else 'no round asks it'}")

    # Weighted counts per shape, per field, from whichever round was picked
    # for that country and field. Strata landing on one shape are summed, and
    # so are their sample sizes: a shape covered by two strata of 20 was
    # interviewed 40 times.
    tally: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    sample: dict[tuple[str, str], dict[str, int]] = {}
    # Which strata a round drew inside a shape, kept *per round*: the two
    # rounds spell several of them differently -- Ruyiga for Ruyigi, Souhag
    # for Sohag -- and pooling the spellings would make the note claim a
    # summing that never happened. Only the Red Sea case is a real sum, and
    # it is a real sum within one round.
    strata: dict[tuple[str, str, str], set[str]] = {}
    refused_strata: dict[str, set[str]] = {}
    for row in rows:
        iso = COUNTRIES[row["country"]]
        if iso in REFUSED:
            refused_strata.setdefault(iso, set()).add(row["region"])
            continue
        shape = REGIONS.get((iso, row["region"]), row["region"])
        key = (iso, shape)
        strata.setdefault((iso, shape, row["round"]), set()).add(row["region"])
        try:
            weight = float(row["weight"])
        except (TypeError, ValueError):
            weight = 1.0
        for field in FIELDS:
            if picked[(row["country"], field)] != row["round"]:
                continue
            sample.setdefault(key, {})
            sample[key][field] = sample[key].get(field, 0) + 1
            name = answer(row[field])
            if not name:
                continue
            cell = tally.setdefault(key, {}).setdefault(field, {})
            cell[name] = cell.get(name, 0.0) + weight

    records: list[dict[str, Any]] = []
    kept = {field: 0 for field in FIELDS}
    dropped = low = 0
    for (iso, shape) in sorted(sample):
        country = next(c for c, i in COUNTRIES.items() if i == iso)
        fields: dict[str, Any] = {}
        sources: list[dict[str, Any]] = []
        thin = False
        for field in FIELDS:
            rnd = picked[(country, field)]
            if rnd is None:
                note = (ONE_VALUE.format(n=sum(
                    1 for r in rows if r["country"] == country
                    and answer(r[field]))) if field == "language"
                    else NEVER_ASKED.format(field=field))
                fields[field] = gap(NOT_COLLECTED, note)
                continue
            n = sample[(iso, shape)].get(field, 0)
            if n < MIN_SAMPLE:
                dropped += 1
                continue                    # no row at all beats a thin one
            rows_out = shares(tally.get((iso, shape), {}).get(field, {}))
            if not rows_out:
                continue
            name, tag = SOURCES[rnd]
            note = UNIVERSE.format(round=name.split("Afrobarometer ")[1].split(" (")[0])
            note += f" This region: {n} respondents."
            parts = strata[(iso, shape, rnd)]
            # One stratum under another name is a spelling, and saying it was
            # "summed" would describe an arithmetic that did not happen. Two
            # strata on one shape really are added, and that is worth saying.
            if len(parts) > 1:
                note += (f" The survey draws this shape as "
                         f"{', '.join(sorted(parts))}, summed here.")
            elif parts != {shape}:
                note += f" The survey names this stratum {next(iter(parts))}."
            if n < LOW_PRECISION:
                thin = True
                note += (" Fewer than 50 respondents, so this share is "
                         "imprecise and should be read as indicative.")
            year = year_of(rows, country, rnd)
            fields[field] = rows_out
            fields[f"{field}_note"] = note
            if year:
                fields[f"{field}_year"] = year
            sources.append({"field": field, "name": name, "url": URL,
                            "year": year, "license": LICENCE})
            kept[field] += 1
        low += thin
        if not sources:
            continue
        tag = SOURCES[picked[(country, "religion")] or "R6"][1]
        records.append(record(f"{iso}-{tag}-{shape}", shape, level="admin1",
                              parent=iso, country=iso, **fields,
                              sources=sources))

    for (iso, shape), why in sorted(UNSAMPLED.items()):
        records.append(record(
            f"{iso}-AB-{shape}", shape, level="admin1", parent=iso,
            country=iso,
            **{f: gap(NOT_AVAILABLE, why) for f in FIELDS},
            sources=[{"field": "/".join(FIELDS), "name": SOURCES["R6"][0],
                      "url": URL, "license": LICENCE}]))

    for iso, names in sorted(refused_strata.items()):
        log(f"  {iso}: {len(names)} strata not written -- see the module "
            f"docstring for why this country's sample is not read by shape")
    log(f"  {len(records)} records: "
        + ", ".join(f"{n} {f}" for f, n in kept.items())
        + f"; {dropped} field-cells dropped under {MIN_SAMPLE} respondents, "
          f"{low} shapes marked low precision")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
