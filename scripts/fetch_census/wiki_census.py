#!/usr/bin/env python3
"""Census tables that reach this project only as a Wikipedia transcription.

Some statistical offices publish a census table by region and then keep it
where no automated reader can go -- behind a firewall that answers 418, in a
JavaScript shell, or on a host this project has not been able to open. When a
Wikipedia article transcribes that table and cites the census, the table can
still be read, through the MediaWiki API, and the record can name the census
as its source with the article as the copy it was read from. Thailand's
provincial religion was the first of these (``thailand.py``, its own file
because its table has a citation per row); this module holds the rest, one
spec per country, so a new one is a dozen lines and not a new adapter.

What a spec says, and what the reader checks:

* the article and which of its tables, found by its first header cells so a
  reordered article refuses rather than reading the wrong table;
* which columns are the shares (percentages as printed), which is the name,
  and how many header rows to skip;
* the year and the census the article transcribes, and the shapes' names
  where they differ from the article's.

A row's shares must add to within half a percent of 100; when they fall short
of it by more than rounding, the rest is published as one "Other or not
stated" group, and a row past 100.5% refuses the run. A printed 0.0 is kept:
it means "below 0.05%", which is a measurement.

**Kazakhstan.** "Religion in Kazakhstan" transcribes the 2021 National
Population Census, religious affiliation by region, with a count and a percent
per faith; the percents are read (one count in the article is mistyped, and the
percent beside it is not). The table lists sixteen regions and omits Shymkent,
a city of republican significance since 2018; the boundary file draws the
2017 layout, in which Shymkent is still inside South Kazakhstan Region, so the
article's "Turkistan Region" (which excludes Shymkent) is not matched to that
shape and South Kazakhstan stays a visible gap. The other fifteen regions and
cities match by name.

**Cambodia.** "Religion in Cambodia" transcribes the 2008 and 2019 General
Population Censuses, religion by province; the 2019 columns are read. Four
provinces are spelled differently by the boundary file (Bantey Meanchey,
Kratie, Takeo, Tbong Khmum) and are declared as aliases.

Usage:
    python -m scripts.fetch_census.wiki_census --country KAZ
    python -m scripts.fetch_census.wiki_census            # every spec
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
REMAINDER = "Other or not stated"

SPECS: dict[str, dict[str, Any]] = {
    "KAZ": {
        "title": "Religion in Kazakhstan",
        "field": "religion",
        "year": 2021,
        "level": "admin1",
        "first_header": ["Region", "Islam", "Christianity"],
        "header_rows": 2,                       # the second row is "# | % | # | % ..."
        "columns": {"Islam": 2, "Christianity": 4, "Other religions": 6,
                    "No religion": 8, "Not stated": 10},
        "skip": {"Total"},
        "aliases": {},
        "unmatched_by_design": {"Turkistan Region"},
        "expected": 16,
        "source": "Bureau of National Statistics of Kazakhstan, 2021 National Population "
                  "Census, religious affiliation by region",
        "licence": "Official statistics; compilation CC BY-SA 4.0",
        "note": "Shares as the census published them, read from the Wikipedia article "
                "'Religion in Kazakhstan', which transcribes the 2021 census table by "
                "region. 'Not stated' is the census's undeclared.",
        "out": "kazakhstan_region.json",
    },
    "KHM": {
        "title": "Religion in Cambodia",
        "field": "religion",
        "year": 2019,
        "level": "admin1",
        "first_header": ["Province", "Buddhism", "Islam"],
        "header_rows": 2,                       # the second row is "2008 | 2019 | ..."
        "columns": {"Buddhism": 2, "Islam": 4, "Christianity": 6, "Other religions": 8},
        "skip": {"Total"},
        "aliases": {"Banteay Meanchey": ["Bantey Meanchey"], "Kratié": ["Kratie"],
                    "Takéo": ["Takeo"], "Tboung Khmum": ["Tbong Khmum"],
                    "Ratanakiri": ["Ratanakiri Province"]},
        "unmatched_by_design": set(),
        "expected": 25,
        "source": "National Institute of Statistics of Cambodia, General Population "
                  "Census of Cambodia 2019, religion by province",
        "licence": "Official statistics; compilation CC BY-SA 4.0",
        "note": "Shares as the census published them, read from the Wikipedia article "
                "'Religion in Cambodia', which transcribes the 2008 and 2019 census "
                "tables by province; the 2019 columns are read.",
        "out": "cambodia_province.json",
    },
}


def percent(cell: str) -> float | None:
    text = cell.replace("%", "").replace(",", "").strip()
    if text.upper() in ("", "N/A", "NA", "-", "—", "–"):
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise SystemExit(f"wiki_census: cannot read {cell!r} as a percentage")
    return float(text)


def find_table(found: list[list[list[str]]], first_header: list[str]) -> list[list[str]]:
    for t in found:
        if t and [c.strip() for c in t[0][:len(first_header)]] == first_header:
            return t
    raise SystemExit(f"wiki_census: no table starts with {first_header}; the article changed")


def bars(spec: dict[str, Any], row: list[str]) -> list[dict[str, Any]]:
    shares: dict[str, float] = {}
    for label, i in spec["columns"].items():
        pct = percent(row[i]) if i < len(row) else None
        if pct is not None:
            shares[label] = pct
    if not shares:
        return []
    summed = sum(shares.values())
    if summed > 100.5 or summed < 90:
        raise SystemExit(f"wiki_census: {row[0]!r} adds to {summed:.2f}%; wrong columns")
    rest = round(100.0 - summed, 2)
    if rest >= 0.15:
        shares[REMAINDER] = rest
    out = [{"group": g, "pct": round(p, 2)} for g, p in shares.items()]
    out.sort(key=lambda r: r["pct"], reverse=True)
    return out


def build(iso3: str, spec: dict[str, Any], wikitext: str) -> list[dict[str, Any]]:
    table = find_table(tables(wikitext), spec["first_header"])
    records: list[dict[str, Any]] = []
    for row in table[spec["header_rows"]:]:
        name = row[0].strip()
        if not name or name in spec["skip"]:
            continue
        shares = bars(spec, row)
        if not shares:
            log(f"  {name}: no shares in the row")
            continue
        field = spec["field"]
        records.append(record(
            f"{iso3}-{slug(name)}", name, level=spec["level"], parent=iso3, country=iso3,
            aliases=spec["aliases"].get(name, []),
            sources=[{"field": field, "name": spec["source"],
                      "url": f"https://en.wikipedia.org/wiki/{spec['title'].replace(' ', '_')}",
                      "license": spec["licence"]}],
            # ``shares`` is non-empty by the check above, so the year always
            # has a figure to describe.
            **{field: shares, f"{field}_year": spec["year"],
               f"{field}_note": f"{spec['source']}. {spec['note']}"},
        ))
    return records


def slug(text: str) -> str:
    from common import slugify
    return slugify(text)


def fetch(title: str) -> str:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    parsed = http_json(f"{API}?{q}", timeout=90).get("parse") or {}
    text = parsed.get("wikitext") or ""
    log(f"  {title!r}: {len(text):,} bytes of wikitext")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default=None, help="one ISO3 from SPECS; default all")
    args = ap.parse_args()
    for iso3, spec in SPECS.items():
        if args.country and iso3 != args.country:
            continue
        log(f"wiki_census {iso3}: {spec['source']}")
        records = build(iso3, spec, fetch(spec["title"]))
        log(f"  {len(records)} {spec['level']} records"
            + (f"; not matched by design: {sorted(spec['unmatched_by_design'])}"
               if spec["unmatched_by_design"] else ""))
        if len(records) != spec["expected"]:
            raise SystemExit(f"wiki_census {iso3}: expected {spec['expected']} rows, "
                             f"read {len(records)}")
        write_json(PROCESSED / spec["out"], records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
