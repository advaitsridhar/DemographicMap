#!/usr/bin/env python3
"""Romania: ethnicity and religion by judet, from the census through the Archive.

Romania's 2011 census (RPL 2011) asks ethnicity and religion and publishes both
by county, in Volume 2, *Populatia stabila -- structura etnica si confesionala*.
This adapter reads two of that volume's tables:

* ``vol2_t1.xls``  -- population by ethnicity, county by county, one row per
  census year from 1930 to 2011. Nineteen named peoples, plus "other" and
  "not available".
* ``vol2_t12.xls`` -- population by religion, county by county, split by sex.
  Twenty named confessions, plus "other", "no religion", "atheist" and
  "not available". Only the "Ambele sexe" (both sexes) row is read.

**It is read from the Internet Archive, and that is not a shortcut.** Every
Romanian host this project can name is unreachable from the runner, measured
five ways on two days: ``insse.ro`` over both http and https returns errno 101,
*Network is unreachable* -- a routing failure rather than a slow server or a
block page -- ``statistici.insse.ro`` fails the TLS handshake, and
``recensamantromania.ro`` and ``data.gov.ro`` both time out. HDX carries no
Romanian census dataset. The Archive has the office's own workbooks, byte for
byte, and a capture is fetched raw with the ``id_`` modifier so what arrives is
the stored file and not a rewritten playback page. This is the same trade
already made for Bangladesh's Bureau of Statistics, and for the same reason:
the alternative is not a better source, it is no source.

**Why 2011 and not 2021.** RPL 2021 exists and asks the same two questions, but
its county tables live only behind those unreachable hosts and are not in the
Archive as machine-readable files. 2011 is a real census, it is the most recent
one this project can actually open, and every record says so and carries the
year. A figure eleven years old with its date on it is a different thing from a
guess.

**A count, not a percentage.** Both tables publish people, so the shares here
are computed rather than transcribed, and the count is kept beside each share.
Two of the census's own marks are not numbers and are read as such: ``-`` is a
true zero, and ``*`` is a count the office suppressed for disclosure control --
which is not zero, and is dropped from the composition rather than counted as
one. A suppressed cell is worth at most a handful of people against a county of
hundreds of thousands, so the composition still reaches 100.0.

Usage:
    python -m scripts.fetch_census.romania
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import PROCESSED, http_get, log, slugify, write_json  # noqa: E402
from fetch_census._shared import record, shares  # noqa: E402

YEAR = 2011
SOURCE = ("National Institute of Statistics of Romania, Recensamantul Populatiei "
          "si al Locuintelor 2011, Volume 2: Populatia stabila -- structura "
          "etnica si confesionala")
LICENCE = "Official statistics of Romania"

# The office's own files, at the Archive captures that hold them. The timestamp
# is part of the address: a different capture is a different fetch, and naming
# it is what makes this run repeatable.
BASE = "http://www.recensamantromania.ro/wp-content/uploads/2015/05"
ETHNIC = (f"{BASE}/vol2_t1.xls", "20190404144202")
RELIGION = (f"{BASE}/vol2_t12.xls", "20190404144202")

# Column index -> the canonical name this project already uses. Every one of
# these resolves in group_tree.py; none is invented here.
#
# "Sarbi, Croati, Sloveni" is one column in the source because the older
# rounds counted the three together, and it is published under the name the
# table gives it rather than split by guess -- the tree already carries that
# label for exactly this kind of legacy category.
ETHNIC_COLUMNS: dict[int, str] = {
    3: "Romanians", 4: "Hungarians", 5: "Romani", 6: "Ukrainians",
    7: "Germans", 8: "Turks", 9: "Russians", 10: "Tatars",
    11: "Serbs, Croats and Slovenes", 12: "Slovaks", 13: "Bulgarians",
    14: "Greeks", 15: "Jewish", 16: "Czechs", 17: "Polish", 18: "Armenians",
    19: "Other ethnic group", 20: "Not stated",
}

# Two pairs of columns land on one canonical name and are summed: the census
# counts the Lutherans of the Augsburg Confession apart from the other
# Lutherans, and the two evangelical bodies apart from each other. Neither
# distinction survives into a tree this map draws at four tiers, and adding a
# label for each would put two near-identical slices in every Transylvanian
# panel.
RELIGION_COLUMNS: dict[int, str] = {
    2: "Orthodox Christianity", 3: "Roman Catholic", 4: "Reformed",
    5: "Pentecostalism", 6: "Greek Catholic", 7: "Baptist",
    8: "Seventh-day Adventist", 9: "Islam", 10: "Unitarian",
    11: "Jehovah's Witnesses", 12: "Evangelicalism", 13: "Old Believers",
    14: "Lutheranism", 15: "Serbian Orthodox", 16: "Evangelicalism",
    17: "Lutheranism", 18: "Judaism", 19: "Armenian Apostolic",
    20: "Other religion", 21: "No religion", 22: "Atheism", 23: "Not stated",
}

# The forty-one counties and the capital, as the boundary file spells them
# against the SHOUTED, unaccented spelling the workbook uses.
SHAPE_NAMES: dict[str, str] = {
    "ALBA": "Alba", "ARAD": "Arad", "ARGES": "Argeș", "BACAU": "Bacău",
    "BIHOR": "Bihor", "BISTRITA-NASAUD": "Bistrița-Năsăud", "BOTOSANI": "Botoșani",
    "BRASOV": "Brașov", "BRAILA": "Brăila", "BUZAU": "Buzău",
    "CARAS-SEVERIN": "Caraș-Severin", "CALARASI": "Călărași", "CLUJ": "Cluj",
    "CONSTANTA": "Constanța", "COVASNA": "Covasna", "DAMBOVITA": "Dâmbovița",
    "DOLJ": "Dolj", "GALATI": "Galați", "GIURGIU": "Giurgiu", "GORJ": "Gorj",
    "HARGHITA": "Harghita", "HUNEDOARA": "Hunedoara", "IALOMITA": "Ialomița",
    "IASI": "Iași", "ILFOV": "Ilfov", "MARAMURES": "Maramureș",
    "MEHEDINTI": "Mehedinți", "MURES": "Mureș", "NEAMT": "Neamț", "OLT": "Olt",
    "PRAHOVA": "Prahova", "SATU MARE": "Satu Mare", "SALAJ": "Sălaj",
    "SIBIU": "Sibiu", "SUCEAVA": "Suceava", "TELEORMAN": "Teleorman",
    "TIMIS": "Timiș", "TULCEA": "Tulcea", "VASLUI": "Vaslui", "VALCEA": "Vâlcea",
    "VRANCEA": "Vrancea", "MUNICIPIUL BUCURESTI": "București",
}

# Rows that are not a county: the national total, and the macro-regions and
# development regions the volume also totals over.
NOT_A_COUNTY = {"ROMANIA", "TOTAL"}

# The census hangs a footnote marker off a name where the county's boundary
# moved between rounds, and it does so in one table and not the other: the
# ethnicity table says "ILFOV  4" and "MUNICIPIUL BUCURESTI  4" -- Ilfov was
# carved back out of Bucharest in 1997 -- while the religion table, which
# covers one round only, has no footnote to hang. Both spellings are the same
# county, so the marker comes off before the name is matched. Nothing here is
# a rename: a county whose name genuinely ends in a digit does not exist.
FOOTNOTE_MARKS = "0123456789" + "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
SEX_ROWS = {"AMBELE SEXE", "MASCULIN", "FEMININ"}
BOTH_SEXES = "AMBELE SEXE"
SUPPRESSED = "*"


def fetch(url: str, stamp: str) -> bytes:
    """The office's own workbook, from the Archive, raw.

    ``id_`` is what makes it raw. Without it the Archive returns the playback
    page -- HTML with a toolbar injected -- and xlrd's failure to open that
    would read as "the office publishes a broken file".
    """
    blob = http_get(f"https://web.archive.org/web/{stamp}id_/{url}",
                    binary=True, timeout=180)
    if blob[:15].lstrip().lower().startswith((b"<!doctype", b"<html")):
        raise SystemExit(f"romania: {url} played back as HTML; the id_ modifier "
                         "did not take and nothing has been read")
    log(f"  {url.rsplit('/', 1)[-1]}: {len(blob):,} bytes from the Archive "
        f"capture of {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}")
    return blob


def grid(blob: bytes) -> list[list[str]]:
    import xlrd
    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    return [[str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
            for r in range(sheet.nrows)]


def count(cell: str) -> float | None:
    """A cell as a number, or None where the census printed no number.

    ``-`` is a zero the office states. ``*`` is a count it suppressed, which is
    not a zero and must not become one: None drops the group from that county's
    composition rather than claiming nobody there answered it.
    """
    text = cell.strip()
    if not text or text == SUPPRESSED:
        return None
    if text in ("-", "—", "–"):
        return 0.0
    try:
        return float(text.replace(",", "").replace(" ", ""))
    except ValueError:
        raise SystemExit(f"romania: cannot read {cell!r} as a count")


def clean(label: str) -> str:
    """A row label with its footnote marker and spacing taken off."""
    return " ".join(label.strip().rstrip(FOOTNOTE_MARKS + " ").split()).upper()


def unknown(label: str) -> bool:
    """A row label that looks like a place and is not one this adapter knows.

    The two tables do not spell their counties identically, and a silently
    skipped county is exactly the invisible miss this project cares about:
    the first run read 42 counties of religion and 40 of ethnicity, and said
    nothing about the two until this existed.
    """
    return bool(label) and label not in SHAPE_NAMES and label not in NOT_A_COUNTY \
        and label not in SEX_ROWS and not label[0].isdigit() and label not in ("A", "B")


def read_ethnicity(rows: list[list[str]]) -> dict[str, dict[str, float]]:
    """{county: {group: count}} for the 2011 row of each county."""
    out: dict[str, dict[str, float]] = {}
    strangers: set[str] = set()
    where: str | None = None
    for row in rows:
        label = clean(row[0])
        if label in SHAPE_NAMES:
            where = label
            continue
        if label in NOT_A_COUNTY:
            where = None
            continue
        if unknown(label) and not row[1].strip():
            # A place-looking row with no year beside it is a heading, and a
            # heading this adapter does not recognise is worth printing.
            strangers.add(label)
        # A year row: the county it belongs to is the last one named above it.
        year = row[1].strip()
        if where is None or not year.startswith(str(YEAR)):
            continue
        counts = {}
        for i, group in ETHNIC_COLUMNS.items():
            value = count(row[i]) if i < len(row) else None
            if value is not None:
                counts[group] = counts.get(group, 0.0) + value
        if counts:
            out[where] = counts
        where = None
    if strangers:
        log(f"  ethnicity table: {len(strangers)} unrecognised headings: "
            + ", ".join(sorted(strangers)[:12]))
    return out


def read_religion(rows: list[list[str]]) -> dict[str, dict[str, float]]:
    """{county: {group: count}} from the both-sexes row of each county."""
    out: dict[str, dict[str, float]] = {}
    where: str | None = None
    for row in rows:
        label = clean(row[0])
        if label in SHAPE_NAMES:
            where = label
            continue
        if label in NOT_A_COUNTY:
            where = None
            continue
        if label not in SEX_ROWS:
            continue
        if where is None or label != BOTH_SEXES:
            continue
        counts: dict[str, float] = {}
        for i, group in RELIGION_COLUMNS.items():
            value = count(row[i]) if i < len(row) else None
            if value is not None:
                counts[group] = counts.get(group, 0.0) + value
        if counts:
            out[where] = counts
        where = None
    return out


def note(field: str) -> str:
    return (f"{SOURCE}. Shares computed from the counts the census published, "
            f"which are the {YEAR} round -- the most recent Romanian census "
            f"this project can open. The tables are read from the Internet "
            f"Archive's copy of the office's own workbooks: every Romanian "
            f"host is unreachable from this pipeline, insse.ro answering "
            f"'Network is unreachable' rather than refusing. Counts the census "
            f"suppressed for disclosure control are left out of the "
            f"composition rather than read as zero.")


def build() -> list[dict[str, Any]]:
    ethnic = read_ethnicity(grid(fetch(*ETHNIC)))
    religion = read_religion(grid(fetch(*RELIGION)))
    log(f"  {len(ethnic)} counties with ethnicity, {len(religion)} with religion")

    records: list[dict[str, Any]] = []
    for key, name in sorted(SHAPE_NAMES.items(), key=lambda kv: kv[1]):
        fields: dict[str, Any] = {}
        cite: list[dict[str, Any]] = []
        for field, table in (("ethnicity", ethnic), ("religion", religion)):
            counts = table.get(key)
            if not counts:
                continue
            fields[field] = shares(counts)
            fields[f"{field}_year"] = YEAR
            fields[f"{field}_note"] = note(field)
            cite.append({"field": field, "name": SOURCE,
                         "url": ETHNIC[0] if field == "ethnicity" else RELIGION[0],
                         "license": LICENCE})
        if not fields:
            log(f"  {name}: no row in either table")
            continue
        records.append(record(
            f"ROU-{slugify(name)}", name, level="admin1", parent="ROU",
            country="ROU", sources=cite, **fields))
    return records


def check(records: list[dict[str, Any]]) -> None:
    """Both compositions partition their county, or the run says nothing.

    The census prints people, so each row is checked against its own printed
    total rather than against a percentage that has already been rounded.
    """
    if len(records) != len(SHAPE_NAMES):
        raise SystemExit(f"romania: {len(records)} records for "
                         f"{len(SHAPE_NAMES)} counties")
    for row in records:
        for field in ("ethnicity", "religion"):
            comp = row.get(field)
            if not isinstance(comp, list):
                raise SystemExit(f"romania: {row['name']} has no {field}")
            total = sum(g["pct"] for g in comp)
            if abs(total - 100.0) > 0.6:
                raise SystemExit(f"romania: {row['name']} {field} adds to "
                                 f"{total:.1f}%, which is not a composition")
    biggest = max(records, key=lambda r: max(
        (g["count"] for g in r["ethnicity"] if g["group"] == "Hungarians"), default=0))
    hun = next(g for g in biggest["ethnicity"] if g["group"] == "Hungarians")
    log(f"  most Hungarians: {biggest['name']} at {hun['pct']}% "
        f"({hun['count']:,} people) -- Harghita and Covasna are the two "
        f"counties with a Hungarian majority, so this should be one of them")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log(f"romania: {SOURCE}")
    records = build()
    check(records)
    out = write_json(PROCESSED / "romania_county.json", records)
    log(f"  wrote {out} ({out.stat().st_size // 1024} kB)")
    log(f"  {len(records)} counties with ethnicity and religion, {YEAR} census")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
