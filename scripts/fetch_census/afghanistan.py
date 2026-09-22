#!/usr/bin/env python3
"""Ethnic composition of Afghan districts, from each province's own article.

Afghanistan has never completed a population census -- the 1979 count was
abandoned partway, and the census restarted in 2013 excluded ethnicity and
language deliberately -- so there is no official ethnic tabulation of any
kind, and all 398 districts read `not_collected` before this file.

What exists instead is the district development plan. Between roughly 2008
and 2014 the Ministry of Rural Rehabilitation and Development, through its
National Area-Based Development Programme, published a summary for each
district; several state an ethnic breakdown. The English Wikipedia article of
each province transcribes them into its `Administrative divisions` table and
cites the PDFs. That is what this reads.

**It is not a census and the record says so**, in the source name and in the
year. A ministry's planning survey is a weaker thing than a count, and the
right response to that is to label it accurately rather than to refuse it:
the alternative on offer is 398 districts that say nothing at all.

The column is not uniform. Baghlan heads it `Notes`, Badakhshan runs
`Villages` and `Ethnic groups` together into one, and others differ again, so
it is matched by shape rather than by one spelling. Neither is the prose:

    Pashtun 70%, Tajik 20%, Uzbek 10%          <- share after the name
    60% Uzbek, 20% Tajik, 10% Hazara           <- share before it
    51 villages. 100% Tajik.                   <- a village count first
    Majority Turkmen, minority Tajik           <- no shares at all
    Predominantly Pamiris (Ishkashimi), few Tajik

**Only the first three shapes are read.** A row that says "Majority Turkmen"
is refused and stays a gap, because turning *majority* and *minority* into
numbers would be inventing the figures rather than reading them -- and a
district wearing an invented composition is indistinguishable, on the map,
from one wearing a measured one.

Usage:
    python -m scripts.fetch_census.afghanistan --probe
    python -m scripts.fetch_census.afghanistan
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import NOT_AVAILABLE, gap                      # noqa: E402
from probe_wikitable import tables                         # noqa: E402
from ._shared import PROCESSED, log, record, write_json    # noqa: E402
from .europe_wiki import fetch                             # noqa: E402

OUT = "afghanistan_district.json"
LANG = "en"
SOURCE = ("Ministry of Rural Rehabilitation and Development, National "
          "Area-Based Development Programme, district development plans")
LICENCE = "Ministry publication; compilation CC BY-SA 4.0"
# The plans were published across these years and the articles rarely say
# which. The record carries the range rather than a false precision.
YEARS = "2008-2014"

PROVINCES = (
    "Badakhshan", "Badghis", "Baghlan", "Balkh", "Bamyan", "Daikundi",
    "Farah", "Faryab", "Ghazni", "Ghor", "Helmand", "Herat", "Juzjan",
    "Kabul", "Kandahar", "Kapisa", "Khost", "Kunar", "Kunduz", "Laghman",
    "Logar", "Maidan Wardak", "Nangarhar", "Nimruz", "Nuristan", "Paktia",
    "Paktika", "Panjshir", "Parwan", "Samangan", "Sar-e-Pol", "Takhar",
    "Uruzgan", "Zabul",
)

# What the articles call the groups, against this map's names. The spellings
# are the ones the run log reported, not invented ones.
GROUPS = {
    "pashtun": "Pashtun", "pashtuns": "Pashtun", "pashton": "Pashtun",
    "pushtun": "Pashtun", "pathan": "Pashtun",
    "tajik": "Tajik", "tajiks": "Tajik", "tadjik": "Tajik",
    "hazara": "Hazara", "hazaras": "Hazara",
    "uzbek": "Uzbek", "uzbeks": "Uzbek",
    "turkmen": "Turkmen", "turkmens": "Turkmen", "turkman": "Turkmen",
    "aimaq": "Aimaq", "aimaqs": "Aimaq", "aimak": "Aimaq",
    "baloch": "Baloch", "balochs": "Baloch", "baluch": "Baloch",
    "nuristani": "Nuristani", "nuristanis": "Nuristani",
    "pashai": "Pashai", "pashais": "Pashai",
    "pamiri": "Pamiri", "pamiris": "Pamiri",
    "arab": "Arab", "arabs": "Arab",
    "kyrgyz": "Kyrgyz", "qizilbash": "Qizilbash",
    "brahui": "Brahui", "gujjar": "Gujjar", "gurjar": "Gujjar",
    "sadat": "Sayyid", "sayyid": "Sayyid", "sayed": "Sayyid",
    "farsiwan": "Farsiwan", "farsiwans": "Farsiwan",
    "kuchi": "Kuchi", "kochi": "Kuchi",
    "other": "Other", "others": "Other",
}

LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
REF = re.compile(r"<ref[^>]*?(?:/>|>.*?</ref>)", re.S | re.I)
MARKUP = re.compile(r"\{\{[^{}]*\}\}|'''?|<[^>]+>|align=\w+\|?|style=\"[^\"]*\"")
# "Pashtun 70%" and "70% Pashtun" -- both orders appear, often in one article.
AFTER = re.compile(r"([A-Za-z][A-Za-z\- ]{2,24}?)\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%")
BEFORE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?([A-Za-z][A-Za-z\- ]{2,24})")
# A composition may fall short -- the plans list the groups they list -- but
# never overrun: over 100 means a group counted twice and the arithmetic then
# describes nobody.
CEILING = 100.5
FLOOR = 55.0


def clean(cell: str) -> str:
    """A table cell down to the words a reader sees."""
    text = REF.sub(" ", cell)
    text = LINK.sub(lambda m: m.group(2) or m.group(1), text)
    text = MARKUP.sub(" ", text)
    return " ".join(text.split())


def shares(text: str) -> list[dict[str, Any]]:
    """Every "<group> N%" or "N% <group>" pair the cell states.

    Returns [] for a cell that states none, which is the common case and a
    refusal rather than an error: "Majority Turkmen, minority Tajik" is a real
    sentence about a real district and it is not a composition.
    """
    found: dict[str, float] = {}
    for pattern, gi, pi in ((AFTER, 1, 2), (BEFORE, 2, 1)):
        for m in pattern.finditer(text):
            name = GROUPS.get(m.group(gi).strip().lower())
            if not name:
                continue
            pct = float(m.group(pi))
            # The same group twice in one cell is the article contradicting
            # itself; keep the first and let the total test catch the rest.
            found.setdefault(name, pct)
    return [{"group": g, "pct": p} for g, p in found.items()]


def usable(parts: list[dict[str, Any]], where: str) -> bool:
    if not parts:
        return False
    total = sum(p["pct"] for p in parts)
    if total > CEILING:
        log(f"    {where}: refused, shares add to {total:.1f}%")
        return False
    if total < FLOOR:
        log(f"    {where}: refused, shares add to only {total:.1f}%")
        return False
    return True


def notes_column(header: list[str]) -> int | None:
    """Which column carries the ethnic note, by what it is called.

    Baghlan heads it "Notes", Badakhshan runs "Villages" and "Ethnic groups"
    into one cell, and the rest vary; so the name is matched loosely and a
    column that is plainly something else is never chosen.
    """
    for i, cell in enumerate(header):
        name = clean(cell).lower()
        if any(w in name for w in ("ethnic", "note", "demograph", "populationnote")):
            return i
    return None


def name_column(header: list[str]) -> int:
    for i, cell in enumerate(header):
        if "district" in clean(cell).lower():
            return i
    return 0


def province_rows(province: str, *, probing: bool) -> list[dict[str, Any]]:
    title = f"{province} Province"
    # fetch returns (wikitext, resolved title): the article may sit behind a
    # redirect, and the name it resolved to is worth having in the log.
    body, resolved = fetch(title, LANG)
    if resolved != title:
        log(f"  {province}: redirected to {resolved!r}")
    if not body:
        log(f"  {province}: no article")
        return []
    out: list[dict[str, Any]] = []
    for table in tables(body):
        if len(table) < 2:
            continue
        header = table[0]
        col = notes_column(header)
        if col is None:
            continue
        which = name_column(header)
        if probing:
            log(f"  {province}: header {[clean(c) for c in header]}")
        read = refused = 0
        for row in table[1:]:
            if len(row) <= max(col, which):
                continue
            district = clean(row[which])
            note = clean(row[col])
            if not district or not note:
                continue
            parts = shares(note)
            if not usable(parts, f"{province}/{district}"):
                refused += 1
                if probing and note:
                    log(f"      - {district}: {note[:70]}")
                continue
            read += 1
            if probing:
                log(f"      + {district}: "
                    + ", ".join(f"{p['group']} {p['pct']:g}%" for p in parts))
            out.append({"district": district, "ethnicity": parts})
        log(f"  {province}: {read} district(s) with shares, {refused} without")
        break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="print each province's header and every row's verdict, "
                         "and write nothing")
    ap.add_argument("--only", help="comma-separated province names")
    args = ap.parse_args(argv)

    wanted = ([p.strip() for p in args.only.split(",")] if args.only
              else list(PROVINCES))
    records: list[dict[str, Any]] = []
    for province in wanted:
        for row in province_rows(province, probing=args.probe):
            slug = re.sub(r"[^a-z0-9]+", "-", row["district"].lower()).strip("-")
            records.append(record(
                f"AFG-admin2-{slug}", row["district"], level="admin2",
                parent="AFG",
                ethnicity=row["ethnicity"],
                ethnicity_year=YEARS,
                ethnicity_basis="district development plan",
                sources=[{"field": "ethnicity", "name": SOURCE,
                          "licence": LICENCE, "year": YEARS,
                          "url": "https://en.wikipedia.org/wiki/"
                                 "Administrative_divisions_of_Afghanistan"}]))
    log(f"\nAfghanistan: {len(records)} district(s) with an ethnic composition")
    if args.probe:
        log("--probe: nothing written")
        return 0
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
