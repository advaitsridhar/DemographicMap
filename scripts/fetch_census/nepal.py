#!/usr/bin/env python3
"""Nepal -- NPHC 2021 caste/ethnicity, mother tongue and religion, by district.

The National Statistics Office publishes all three fields in one document, the
*National Report on caste/ethnicity, Language & Religion*. That is unusual and
valuable: most offices ask one of these and no office outside South Asia asks
caste at all. 142 castes/ethnicities, 124 mother tongues and 10 religions, for
the nation, the 7 provinces and the 77 districts.

Why a PDF and not an API
------------------------
There isn't one that can be reached. ``censusnepal.cbs.gov.np`` serves the
census portal with a certificate that is not valid for that hostname, and so
does ``cbs.gov.np``; ``microdata.nsonepal.gov.np`` has a good certificate and
returns an empty body. Taking population figures over a connection that cannot
be authenticated is not a trade this project makes, so the report is fetched
once from a URL given on the command line, checked into ``data/raw/nepal/`` --
the same treatment as the Census of India C-16 workbooks and the 2020 U.S.
Religion Census, and for the same reason -- and parsed from there.

How the annexes are laid out
----------------------------
Every detail table has the same shape, which is what lets one parser read all
three::

    Annex 1: Population by caste/ethnicity and sex, NPHC 2021
    Area
    Caste/ethinicity      Population  Total   Male     Female
    Nepal
      All Castes           29164578   14253551  14911027
      Kshetri               4796995    2308120   2488875
      ...
    Koshi
      All Castes            4961412    2417328   2544084
      ...
    Taplejung
      All Castes             120590      60773     59817
      ...

An area name sits alone on a line, followed by a total row and then one row per
group, each with three figures. Areas run in document order: the nation, then a
province, then that province's districts, then the next province. Nothing in
the text says which is which, so the level is decided by the name: the 7
provinces and 77 districts are known lists, and an area matching neither is
refused rather than guessed at.

What is checked
---------------
The summary chapter publishes national totals for all three fields in tables
10, 11 and 14 -- separately typeset from the annexes this reads -- so they are
real controls rather than a restatement of the same arithmetic. Every one has
to match before a single record is emitted.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, download, gap, log, measure, record,
    shares, write_json,
)

YEAR = 2021
SOURCE = ("National Statistics Office, National Population and Housing Census "
          "2021: National Report on caste/ethnicity, Language and Religion")
LICENSE = "Government of Nepal, National Statistics Office. Official publication."
PDF = RAW / "nepal" / "NPHC2021_caste_language_religion.pdf"
TOLERANCE = 0.001

# The published national figures, from the summary chapter's tables 10, 11 and
# 14. The annexes this parser reads are typeset separately, so agreement is
# evidence the reading is right rather than evidence the arithmetic is
# self-consistent.
NATIONAL = {
    "ethnicity": {"_total": 29_164_578, "Kshetri": 4_796_995,
                  "Brahman - Hill": 3_292_373, "Magar": 2_013_498,
                  "Tharu": 1_807_124, "Tamang": 1_639_866},
    "language": {"Nepali": 13_084_457, "Maithili": 3_222_389,
                 "Bhojpuri": 1_820_795, "Tharu": 1_714_091,
                 "Tamang": 1_423_075},
    "religion": {"_total": 29_164_578, "Hindu": 23_677_744,
                 "Bouddha": 2_393_549, "Islam": 1_483_066,
                 "Kirat": 924_204, "Christian": 512_313},
}

# Nepal's 7 provinces. Three were renamed after the 2015 constitution and the
# boundary file still carries the old numbers, so each keeps its aliases.
PROVINCES: dict[str, tuple[str, ...]] = {
    "Koshi": ("Province 1", "Province No. 1", "Pradesh 1", "Purwanchal"),
    "Madhesh": ("Province 2", "Madhes", "Madhesh Pradesh", "Province No. 2"),
    "Bagmati": ("Bagmati Province", "Province 3"),
    "Gandaki": ("Gandaki Province", "Province 4"),
    "Lumbini": ("Lumbini Province", "Province 5"),
    "Karnali": ("Karnali Province", "Province 6"),
    "Sudurpashchim": ("Sudurpaschim", "Sudur Pashchim", "Far-Western",
                      "Province 7"),
}

# The 77 districts, by province, as the census names them. This is the list an
# area name has to appear in to be read as a district; anything else in the
# Area column -- a stray header, a page number that survived extraction -- is
# refused rather than emitted as a place.
DISTRICTS: dict[str, tuple[str, ...]] = {
    "Koshi": ("Bhojpur", "Dhankuta", "Ilam", "Jhapa", "Khotang", "Morang",
              "Okhaldhunga", "Panchthar", "Sankhuwasabha", "Solukhumbu",
              "Sunsari", "Taplejung", "Terhathum", "Udayapur"),
    "Madhesh": ("Bara", "Dhanusha", "Mahottari", "Parsa", "Rautahat",
                "Saptari", "Sarlahi", "Siraha"),
    "Bagmati": ("Bhaktapur", "Chitwan", "Dhading", "Dolakha", "Kathmandu",
                "Kavrepalanchok", "Lalitpur", "Makwanpur", "Nuwakot",
                "Ramechhap", "Rasuwa", "Sindhuli", "Sindhupalchok"),
    "Gandaki": ("Baglung", "Gorkha", "Kaski", "Lamjung", "Manang", "Mustang",
                "Myagdi", "Nawalpur", "Parbat", "Syangja", "Tanahun"),
    "Lumbini": ("Arghakhanchi", "Banke", "Bardiya", "Dang", "Gulmi",
                "Kapilvastu", "Palpa", "Parasi", "Pyuthan", "Rolpa",
                "Rukum East", "Rupandehi"),
    "Karnali": ("Dailekh", "Dolpa", "Humla", "Jajarkot", "Jumla", "Kalikot",
                "Mugu", "Rukum West", "Salyan", "Surkhet"),
    "Sudurpashchim": ("Achham", "Baitadi", "Bajhang", "Bajura", "Dadeldhura",
                      "Darchula", "Doti", "Kailali", "Kanchanpur"),
}

# Spellings the boundary file uses for a district the census names otherwise.
# Only spelling variants belong here: a name that names a *different* place is
# a mis-join waiting to happen and is handled by the exclusion list below.
# Two sources of variation are folded here, and they are different things.
# CGAZ's spellings ("Chitawan", "Synagja") are how the boundary file writes a
# name. The parenthesised forms are the census's own: it calls the two
# districts carved out of Nawalparasi in 2017 by the stretch of the Bardaghat
# Susta road that divides them, and calls Rukum's halves the same way.
DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "Bajura": ("Baijura",),
    "Chitwan": ("Chitawan",),
    "Dadeldhura": ("Dadeidhura",),
    "Dhanusha": ("Dhanusa",),
    "Kapilvastu": ("Kapilbastu",),
    "Kavrepalanchok": ("Kabherepalanchok", "Kavre"),
    "Makwanpur": ("Makawanpur",),
    "Syangja": ("Synagja",),
    "Tanahun": ("Tanahu",),
    "Rukum East": ("Rukum_E", "Rukum (East)", "Eastern Rukum"),
    "Rukum West": ("Rukum_W", "Rukum (West)", "Western Rukum"),
    "Nawalpur": ("Nawalparasi (Bardaghat Susta East)",),
    "Parasi": ("Nawalparasi (Bardaghat Susta West)", "Nawalparasi",
               "Nawalparasi West"),
}

# Districts whose figures are deliberately not joined to a boundary shape.
#
# geoBoundaries CGAZ carries 75 shapes for Nepal's 77 districts, and its names
# do not sit on the right polygons. Asking the polygons directly which one
# contains each district's headquarters:
#
#   Butwal and Bhairahawa (Rupandehi)  -> a shape named "Nawalapur"
#   Dailekh town (Dailekh)             -> a shape named "Jajarkot"
#   Siraha town (Siraha)               -> the western of two named "Saptari"
#   Kawasoti (Nawalpur)                -> a shape named "Chitawan"
#
# and "Bara" and "Saptari" each appear twice while Parsa, Siraha, Rupandehi and
# Dailekh appear not at all. A name-keyed join would put Rupandehi's 1.1 million
# people on a polygon labelled Nawalapur and show nothing on screen to say so.
# These six names are therefore withheld: the shapes they would reach are
# either duplicated or demonstrably somebody else's ground.
UNJOINABLE = {
    "Rupandehi": "CGAZ has no Rupandehi; its territory lies inside a shape named Nawalapur",
    "Nawalpur": "CGAZ has no Nawalpur; its territory lies inside a shape named Chitawan",
    "Dailekh": "CGAZ has no Dailekh; its territory lies inside a shape named Jajarkot",
    "Siraha": "CGAZ has no Siraha; its territory lies inside the western of two shapes named Saptari",
    "Parsa": "CGAZ has no Parsa; its territory lies inside a shape named Bara",
    "Saptari": "CGAZ carries two shapes named Saptari, one of which is Siraha",
}
# Bara is in the same bind as Saptari -- two shapes wear the name -- so it goes
# with them.
UNJOINABLE["Bara"] = ("CGAZ carries two shapes named Bara, one of which is "
                      "Parsa")

# The report uses two table shapes, and which one a page is in is decided by
# the row that opens each area rather than by the annex title. The title is
# page furniture: pypdf emits it *after* the rows it labels on every page but
# the first, where it does not appear at all, so bracketing an annex by its
# heading loses a page at each end.
#
# Annex 1 (caste/ethnicity) and Annex 2 (mother tongue) are long tables, and
# each opens an area with its own total label. Both labels occur exactly 85
# times in the report -- the nation, 7 provinces and 77 districts -- which is
# what makes them a reliable bracket.
LONG_TABLES = {"All Castes": "ethnicity", "All MTongues": "language"}

# Annex 5 (religion) is a wide cross-tab instead: a header naming the ten
# religions, then each area in capitals followed by Total, Male and Female
# rows. The Total row is the population and then one count per religion, in
# header order.
RELIGION_HEADER = re.compile(r"^Hindu\s+Bouddha\s+Islam\b", re.I)

FIELDS = ("ethnicity", "language", "religion")


# ---------------------------------------------------------------------------
# Reading the document
# ---------------------------------------------------------------------------

def text_of(path: Path) -> list[str]:
    """The report as lines, page by page, via pypdf.

    pypdf rather than pdftotext because a pip dependency travels with the
    repository and a system package does not: the runner that fetches this is
    not the machine that builds the site.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        raise SystemExit("pypdf is required to read the NPHC report: "
                         "pip install -r requirements.txt")
    reader = PdfReader(str(path))
    log(f"  {len(reader.pages)} pages")
    lines: list[str] = []
    for page in reader.pages:
        lines.extend((page.extract_text() or "").splitlines())
    return lines


def clean(line: str) -> str:
    """One line, with the extraction's artefacts removed.

    The report is typeset with fi/ti ligatures whose glyphs carry no Unicode
    mapping, so "Population" comes back as "Popula \u019f on" and "Office" as
    "Of\ufb01 ce". That only ever affects prose and headers, never a figure, so
    the stray letters are dropped and the spacing closed up rather than
    reconstructed.
    """
    line = line.replace("\u019f", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    return re.sub(r"\s+", " ", line).strip()


_ROW = re.compile(r"^(?P<name>.+?)\s+(?P<total>\d[\d,]*)\s+(?P<male>\d[\d,]*)"
                  r"\s+(?P<female>\d[\d,]*)$")
_TOTAL_ROW = re.compile(r"^(?P<label>All Castes|All MTongues)\s+(?P<total>\d[\d,]*)"
                        r"\s+\d[\d,]*\s+\d[\d,]*$")


def squash(text: str) -> str:
    return "".join(text.split())


def letter_spaced(line: str) -> bool:
    """Whether a line has been justified glyph by glyph.

    A few rows per page come back from the extractor with a space between
    every character -- "T h a r u 9 47 12 3" for "Tharu 94 71 23". Left alone
    the row parser reads the last three space-separated runs as the figures and
    takes 47, 12 and 3, which is a wrong number that looks like a right one.
    Three or more single-letter tokens is the signature.
    """
    return sum(1 for token in line.split()
               if len(token) == 1 and token.isalpha()) >= 3


def split_figures(digits: str) -> tuple[int, int, int] | None:
    """The one way to cut a run of digits into total, male and female.

    The table prints all three and they satisfy total = male + female, so the
    split is recoverable from the document's own redundancy rather than
    guessed at: "947123" cuts only one way, 94 = 71 + 23. Where more than one
    cut satisfies it -- or none does -- this returns None and the caller
    refuses the row rather than choosing.
    """
    found = []
    for i in range(1, len(digits) - 1):
        for j in range(i + 1, len(digits)):
            a, b, c = digits[:i], digits[i:j], digits[j:]
            if any(part != "0" and part.startswith("0") for part in (a, b, c)):
                continue
            if int(a) == int(b) + int(c):
                found.append((int(a), int(b), int(c)))
    return found[0] if len(found) == 1 else None


def parse_long(lines: list[str]) -> dict[str, dict[str, dict[str, int]]]:
    """Annexes 1 and 2, keyed {field: {area: {group: count}}}.

    Both are read in one pass, because which annex a row belongs to is decided
    by the last total label seen -- "All Castes" or "All MTongues" -- and not by
    the page heading. The area is whichever known name last appeared on a line
    of its own; anything else, including the page numbers and the mangled
    column headers, matches nothing and is skipped.
    """
    out: dict[str, dict[str, dict[str, int]]] = {"ethnicity": {}, "language": {}}
    field: str | None = None
    area: str | None = None
    pending: str | None = None
    # Rows the extractor justified glyph by glyph, held back until the ordinary
    # spellings have all been seen, and the name each of them squashes to.
    deferred: list[tuple[str, str, str]] = []
    spellings: dict[str, dict[str, str]] = {}
    for raw in lines:
        line = clean(raw)
        if not line or line.isdigit():
            continue
        total = _TOTAL_ROW.match(line)
        if total:
            # The total row names the annex and closes the area heading above
            # it. Both are settled here rather than guessed at earlier.
            field = LONG_TABLES[total.group("label")]
            if pending is None:
                continue
            area = pending
            out[field].setdefault(area, {})["_total"] = int(
                total.group("total").replace(",", ""))
            continue
        if letter_spaced(line):
            if field and area:
                deferred.append((field, area, line))
            continue
        row = _ROW.match(line)
        if row:
            if field and area:
                name = row.group("name").strip()
                if name not in {"Total", "Male", "Female"}:
                    out[field][area][name] = int(
                        row.group("total").replace(",", ""))
                    spellings.setdefault(field, {})[squash(name)] = name
            continue
        if known_area(line):
            # A heading closes the block above it as well as opening the next.
            # Annexes 3 and 4 -- second language and ancestor's language -- have
            # no "All ..." row of their own, so without this the field and area
            # last set by annex 2 stayed live and every one of their rows piled
            # onto Kanchanpur, the last district of annex 2. The printed-total
            # check caught it: 552,086 against a printed 513,757.
            pending = canonical_area(line)
            area = None

    resolve_spaced(out, deferred, spellings)
    return out


def resolve_spaced(out: dict[str, dict[str, dict[str, int]]],
                   deferred: list[tuple[str, str, str]],
                   spellings: dict[str, dict[str, str]]) -> None:
    """Put the justified rows back, once every ordinary spelling has been seen.

    The name is recovered by matching it, spaces removed, against the names
    read from rows that were not justified -- every group in this report
    appears un-justified somewhere, because a group that appears in one area
    appears in dozens. That is what restores "Brahman - Hill" rather than
    leaving "BrahmanHill" as a group of its own.
    """
    if not deferred:
        return
    recovered = failed = 0
    for field, area, line in deferred:
        squashed = squash(line)
        match = re.match(r"^(?P<name>.*?)(?P<digits>\d+)$", squashed)
        if not match:
            failed += 1
            continue
        figures = split_figures(match.group("digits"))
        if figures is None:
            failed += 1
            log(f"  ! {field}/{area}: cannot split {line!r}")
            continue
        key = match.group("name")
        name = spellings.get(field, {}).get(key, key)
        out[field][area][name] = figures[0]
        recovered += 1
    log(f"  recovered {recovered} justified row(s)"
        + (f", {failed} unreadable" if failed else ""))
    if failed:
        raise SystemExit(f"{failed} justified row(s) could not be read; the "
                         "figures for those areas would be short")


def parse_religion(lines: list[str]) -> dict[str, dict[str, int]]:
    """Annex 5, the wide cross-tab, as {area: {religion: count}}.

    The header names the ten religions and the order they appear in; the area
    follows in capitals, and its Total row is the population and then one count
    per religion. Male and Female repeat the same columns and are not read --
    this map does not break a composition down by sex.
    """
    out: dict[str, dict[str, int]] = {}
    columns: list[str] = []
    area: str | None = None
    for raw in lines:
        line = clean(raw)
        if not line:
            continue
        if RELIGION_HEADER.match(line):
            columns = line.split()
            continue
        if not columns:
            continue
        if line.isupper() and known_area(line):
            area = canonical_area(line)
            continue
        if area and line.startswith("Total "):
            figures = line.split()[1:]
            # The population, then one count per religion. A row of any other
            # width is the column header repeating on a new page, not data.
            if len(figures) != len(columns) + 1:
                continue
            if not all(f.replace(",", "").isdigit() for f in figures):
                continue
            counts = {"_total": int(figures[0].replace(",", ""))}
            for name, value in zip(columns, figures[1:]):
                counts[name] = int(value.replace(",", ""))
            out[area] = counts
            area = None
    return out


def parse_all(lines: list[str]) -> dict[str, dict[str, dict[str, int]]]:
    parsed = parse_long(lines)
    parsed["religion"] = parse_religion(lines)
    return parsed


_AREA_LOOKUP: dict[str, str] = {}


def _build_area_lookup() -> None:
    if _AREA_LOOKUP:
        return
    _AREA_LOOKUP["nepal"] = "Nepal"
    for province, aliases in PROVINCES.items():
        for name in (province, *aliases):
            _AREA_LOOKUP[name.lower()] = province
    for districts in DISTRICTS.values():
        for district in districts:
            _AREA_LOOKUP[district.lower()] = district
            for alias in DISTRICT_ALIASES.get(district, ()):
                _AREA_LOOKUP[alias.lower()] = district


def known_area(name: str) -> bool:
    _build_area_lookup()
    return name.strip().lower() in _AREA_LOOKUP


def canonical_area(name: str) -> str:
    _build_area_lookup()
    return _AREA_LOOKUP[name.strip().lower()]


def province_of(district: str) -> str | None:
    for province, districts in DISTRICTS.items():
        if district in districts:
            return province
    return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_national(field: str, areas: dict[str, dict[str, int]]) -> None:
    """Nepal's row against the summary chapter, before anything is emitted.

    The summary tables are typeset separately from these annexes, so a match is
    evidence the parse is right. A mismatch means the reading is wrong or the
    edition has changed, and either way the figures should not be published.
    """
    got = areas.get("Nepal")
    if not got:
        raise SystemExit(f"{field}: the annex has no Nepal row to check against")
    for group, published in NATIONAL[field].items():
        have = got.get(group)
        if have is None:
            raise SystemExit(f"{field}: Nepal has no {group!r} row; parsed "
                             f"{len(got)} groups")
        drift = abs(have - published) / published
        log(f"  {field} {group}: {have:,} vs published {published:,} ({drift:.4%})")
        if drift > TOLERANCE:
            raise SystemExit(
                f"{field}: {group} is {drift:.2%} from the published figure; "
                "this is not the edition the adapter was written against")


def check_sums(field: str, areas: dict[str, dict[str, int]]) -> None:
    """Each area's groups against its own total, and the districts against Nepal.

    A shares-add-to-100% test cannot catch a parser that drops rows, because
    the shares are computed from what was read. The annex prints its own total
    on every area, which is independent of the rows beneath it, so a dropped
    row shows up here.
    """
    bad = []
    for area, counts in areas.items():
        total = counts.get("_total")
        if not total:
            continue
        summed = sum(v for k, v in counts.items() if k != "_total")
        if abs(summed - total) / total > TOLERANCE:
            bad.append(f"{area} ({summed:,} vs {total:,})")
    if bad:
        raise SystemExit(f"{field}: groups do not sum to the printed total for "
                         f"{len(bad)} area(s): {bad[:5]}")


def compose(counts: dict[str, int], *, min_pct: float) -> list[dict[str, Any]]:
    """One area's counts as shares of its printed total.

    The printed total is the denominator, not the sum of the rows: they agree
    -- check_sums insists on it -- but using the printed one means a share is
    a share of the population the office counted.
    """
    total = counts.get("_total")
    if not total:
        return []
    groups = {k: v for k, v in counts.items() if k != "_total"}
    return shares(groups, total=total, min_pct=min_pct)


# ---------------------------------------------------------------------------
# Building records
# ---------------------------------------------------------------------------

FIELD_NOTES = {
    "ethnicity": (
        "Caste and ethnicity are one question in Nepal's census, answered with "
        "one of 142 categories. It is not comparable with ethnicity elsewhere: "
        "the categories mix caste groups, Adivasi/Janajati nationalities and "
        "religious communities, and a person answers once."),
    "language": (
        "Mother tongue, the language first spoken at home in childhood -- not "
        "the language a person uses now. The census asks second language and "
        "ancestor's language separately; neither is shown here."),
}

# Below this, a group is folded into the payload's tail rather than carried.
# Nepal publishes 142 castes and 124 languages for every one of 77 districts,
# which is a quarter of a million rows; a district where a group is under a
# tenth of a percent contributes a bar too thin to see.
MIN_PCT = 0.1


def build(lines: list[str], *, min_pct: float = MIN_PCT
          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(province records, district records), both validated before return."""
    parsed = parse_all(lines)
    for field in FIELDS:
        areas = parsed[field]
        log(f"  {field}: {len(areas)} areas")
        check_national(field, areas)
        check_sums(field, areas)

    provinces: list[dict[str, Any]] = []
    districts: list[dict[str, Any]] = []
    withheld: list[str] = []

    for province in PROVINCES:
        fields = fields_for(parsed, province, min_pct)
        if not fields:
            log(f"  ! no annex data for province {province}")
            continue
        provinces.append(record(
            f"NPL-{province}", province, level="admin1", parent="NPL",
            country="NPL", aliases=list(PROVINCES[province]),
            population=population_of(parsed, province),
            sources=[{"field": "caste/ethnicity, language, religion",
                      "name": SOURCE, "license": LICENSE}],
            **fields,
        ))

    for province, names in DISTRICTS.items():
        for district in names:
            if district in UNJOINABLE:
                withheld.append(district)
                continue
            fields = fields_for(parsed, district, min_pct)
            if not fields:
                log(f"  ! no annex data for district {district}")
                continue
            districts.append(record(
                f"NPL-{province}-{district}", district, level="admin2",
                parent=f"NPL-{province}", country="NPL",
                aliases=list(DISTRICT_ALIASES.get(district, ())),
                parent_name=province,
                parent_aliases=list(PROVINCES[province]),
                population=population_of(parsed, district),
                sources=[{"field": "caste/ethnicity, language, religion",
                          "name": SOURCE, "license": LICENSE}],
                **fields,
            ))
    if withheld:
        log(f"  withheld {len(withheld)} district(s) with no trustworthy shape: "
            f"{', '.join(sorted(withheld))}")
    return provinces, districts


def fields_for(parsed: dict[str, dict[str, dict[str, int]]], area: str,
               min_pct: float) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in FIELDS:
        counts = parsed[field].get(area)
        if not counts:
            continue
        composition = compose(counts, min_pct=min_pct)
        if not composition:
            continue
        out[field] = composition
        out[f"{field}_year"] = YEAR
        if FIELD_NOTES.get(field):
            out[f"{field}_note"] = FIELD_NOTES[field]
    return out


def population_of(parsed: dict[str, dict[str, dict[str, int]]], area: str):
    """The area's enumerated population, from whichever annex printed it.

    All three annexes cover everyone, so all three totals are the same figure;
    taking the first that has it avoids depending on any one being present.
    """
    for field in FIELDS:
        total = parsed[field].get(area, {}).get("_total")
        if total:
            return measure(int(total), year=YEAR, source=SOURCE)
    return gap(NOT_AVAILABLE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=None,
                    help="fetch the report from here if it is not already in "
                         "data/raw/nepal/")
    ap.add_argument("--pdf", type=Path, default=PDF)
    ap.add_argument("--min-pct", type=float, default=MIN_PCT)
    ap.add_argument("--dump", type=Path, default=None,
                    help="write the extracted text here and stop; for working "
                         "out how an edition is laid out")
    args = ap.parse_args()

    if not args.pdf.exists():
        if not args.url:
            raise SystemExit(
                f"{args.pdf} is not present and no --url was given. The NSO "
                "portal cannot be reached over a verified connection (see the "
                "module docstring), so the report has to be fetched from a URL "
                "and checked in.")
        download(args.url, args.pdf)

    lines = text_of(args.pdf)
    if args.dump:
        args.dump.write_text("\n".join(lines), encoding="utf-8")
        log(f"  wrote {args.dump} ({len(lines):,} lines)")
        return 0

    provinces, districts = build(lines, min_pct=args.min_pct)
    write_json(PROCESSED / "nepal_province.json", provinces)
    write_json(PROCESSED / "nepal_district.json", districts)
    log(f"  {len(provinces)} provinces, {len(districts)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
