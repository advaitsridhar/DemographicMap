#!/usr/bin/env python3
"""Religion by Dutch province, from each province's own infobox.

All twelve Dutch provinces carry a religion split, and none of it was on this
map: religion read `not_available` on all twelve and on all 344 municipalities,
with the note saying only that Eurostat carries no composition. Language and
ethnicity are a different matter and stay as they are -- NOT_COLLECTED_POLICY
says the Netherlands does not collect them.

It is in the **infobox**, not in a section with a table, which is why the
Europe reader never found it: that one looks for a heading and a table under
it, and `[Religie]` on these articles is a heading with prose. The parameter
looks like this, on nl:Groningen (provincie):

    | religie = 68,4% geen [[Religie|gezindte]]<br />18,7% [[Protestantisme|
      Protestants]]<br> 6,7% overige [[Religie|gezindte]]<br> 4,9% [[Rooms-
      Katholieke Kerk|Rooms-katholiek]] <br />1,3% [[Moslim]]
    | religiejaar = 2015<ref name="religieus">[... CBS, 22 december 2016]</ref>

So: shares separated by `<br>` in any of its spellings, a comma for the
decimal point, and the label inside a wiki link that has to be unwrapped to
its display text. The citation sits on `religiejaar`, not on `religie`, and
the year sits in front of it.

**The years are not uniform and each record carries its own.** Ten provinces
cite CBS's 2015 figures, published December 2016; Noord-Brabant and Limburg
cite a 2023 release, and Drenthe a 2025 one, which also uses a different
vocabulary ("Niet godsdienstig" where the older ones write "geen gezindte").
A reader comparing Drenthe with Groningen is comparing ten years apart, and
the panel has to be able to say so.

Two titles are not what they look like: nl:Zeeland is a disambiguation page
and nl:Limburg (Nederland) a redirect, so the provinces are at
"Zeeland (provincie)" and "Limburg (Nederlandse provincie)". Probing for them
by the obvious name returned a 1,545-byte stub and a 343-byte one, which is
what a redirect looks like from here.

Usage:
    python -m scripts.fetch_census.netherlands
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import NOT_AVAILABLE, gap                      # noqa: E402
from ._shared import PROCESSED, log, record, write_json    # noqa: E402
from .indonesia import (citations, fetch, infobox_param,   # noqa: E402
                        ref_definitions)

OUT = "netherlands_province.json"
LANG = "nl"
LICENCE = "Official statistics (CBS); compilation CC BY-SA 4.0"

# The twelve, as nl.wikipedia titles them against the boundary file's names.
PROVINCES = {
    "Groningen (provincie)": "Groningen",
    "Friesland": "Fryslân",
    "Drenthe": "Drenthe",
    "Overijssel": "Overijssel",
    "Flevoland": "Flevoland",
    "Gelderland": "Gelderland",
    "Utrecht (provincie)": "Utrecht",
    "Noord-Holland": "Noord-Holland",
    "Zuid-Holland": "Zuid-Holland",
    "Zeeland (provincie)": "Zeeland",
    "Noord-Brabant": "Noord-Brabant",
    "Limburg (Nederlandse provincie)": "Limburg",
}

# What the infobox writes, against what this map calls it. Two vocabularies:
# the 2015 release says "geen gezindte" (no denomination) and the 2025 one
# "Niet godsdienstig" (not religious). They are the same answer to the same
# question and both are the survey's own words for it.
LABELS = {
    "geen gezindte": "No religion",
    "geen godsdienstige gezindte": "No religion",
    "niet godsdienstig": "No religion",
    "protestants": "Protestant",
    "protestant": "Protestant",
    "rooms-katholiek": "Roman Catholic",
    "rooms-katholieken": "Roman Catholic",
    "katholiek": "Roman Catholic",
    "moslim": "Muslim",
    "moslims": "Muslim",
    "islam": "Muslim",
    "overige gezindte": "Other religion",
    "overige gezindten": "Other religion",
    "overig": "Other religion",
    "overige": "Other religion",
    "andere gezindte": "Other religion",
    "hindoe": "Hindu",
    "boeddhist": "Buddhist",
    "joods": "Judaism",
}

BREAK = re.compile(r"<\s*br\s*/?\s*>", re.I)
# "68,4% geen [[Religie|gezindte]]" -- the comma is the decimal point.
SHARE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*%\s*(.+?)\s*$", re.S)
LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
YEAR = re.compile(r"(\d{4})")
# Shares may add to less than 100 -- Limburg's four add to 95.4 -- because the
# infobox lists the groups it lists. They may not add to more: that would mean
# a group counted twice, and the arithmetic would be describing nobody.
TOLERANCE = 1.0
FLOOR = 80.0


def unwrap(text: str) -> str:
    """A wiki link down to what a reader sees."""
    return LINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)


def clean(label: str) -> str:
    text = unwrap(label)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[''\"]+", "", text)
    return " ".join(text.split()).strip(" .,;:")


def shares(value: str) -> tuple[list[dict[str, Any]], str]:
    """The infobox's shares, or the reason they are not read."""
    rows: list[dict[str, Any]] = []
    unknown: list[str] = []
    for part in BREAK.split(value):
        part = part.strip()
        if not part:
            continue
        found = SHARE.match(part)
        if not found:
            return [], f"{clean(part)[:40]!r} is not a share"
        pct = float(found.group(1).replace(",", "."))
        label = clean(found.group(2))
        canonical = LABELS.get(label.lower())
        if canonical is None:
            unknown.append(label)
            continue
        rows.append({"group": canonical, "pct": round(pct, 1)})
    if unknown:
        return [], f"labels this reader has no entry for: {unknown}"
    if len(rows) < 2:
        return [], "fewer than two groups"
    total = sum(r["pct"] for r in rows)
    if total > 100.0 + TOLERANCE:
        return [], f"the shares add to {total:.1f}, which is more than a whole"
    if total < FLOOR:
        return [], f"the shares add to {total:.1f}, too little to be a picture"
    # Same group twice -- "overige gezindte" beside "overig" -- is added up
    # rather than overwritten, which would quietly shrink the province.
    merged: dict[str, float] = {}
    for row in rows:
        merged[row["group"]] = merged.get(row["group"], 0.0) + row["pct"]
    out = [{"group": g, "pct": round(p, 1)} for g, p in merged.items()]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out, ""


def province_record(title: str, name: str) -> dict[str, Any] | None:
    wikitext, url = fetch(title, LANG)
    if not wikitext:
        log(f"  {name}: the article could not be read")
        return None
    if len(wikitext) < 3000:
        # nl:Zeeland is a disambiguation page and nl:Limburg (Nederland) a
        # redirect; both came back as a stub rather than as an error.
        log(f"  {name}: '{title}' is {len(wikitext)} bytes, which is a "
            f"redirect or a disambiguation page rather than the province")
        return None
    value = infobox_param(wikitext, "religie")
    if not value:
        log(f"  {name}: the infobox has no 'religie' parameter")
        return None
    dated = infobox_param(wikitext, "religiejaar") or ""
    found = YEAR.search(dated)
    if not found:
        log(f"  {name}: 'religiejaar' states no year; not read")
        return None
    year = int(found.group(1))
    cites = citations(dated, ref_definitions(wikitext)) \
        + citations(value, ref_definitions(wikitext))
    if not cites:
        log(f"  {name}: the figures carry no citation; not read")
        return None
    rows, why = shares(value)
    if why:
        log(f"  {name}: {why}")
        return None
    total = sum(r["pct"] for r in rows)
    short = (f" The infobox lists the groups it lists and they add to "
             f"{total:.1f}%, so this describes that share of the province "
             f"and not the whole of it." if total < 100.0 - TOLERANCE else "")
    return record(
        f"NLD-{name.lower().replace(' ', '-')}", name,
        level="admin1", parent="NLD", country="NLD",
        religion=rows,
        religion_year=year,
        religion_note=(
            f"Religion in {name} for {year}, as the nl.wikipedia article "
            f"'{title}' transcribes it from Statistics Netherlands (CBS). "
            f"The figure is in the article's infobox rather than in a table. "
            f"Cited to: {cites[0][:200]}.{short} The twelve provinces do not "
            f"share a year -- most cite CBS's 2015 release, Noord-Brabant and "
            f"Limburg a 2023 one and Drenthe a 2025 one -- so each province "
            f"carries its own."),
        language=gap(NOT_AVAILABLE),
        ethnicity=gap(NOT_AVAILABLE),
        sources=[{"field": "religion",
                  "name": f"Statistics Netherlands (CBS), religion by "
                          f"province ({year}), as the nl.wikipedia article "
                          f"'{title}' transcribes it",
                  "url": url, "year": year, "license": LICENCE}])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    log(f"netherlands: {len(PROVINCES)} provinces from nl.wikipedia")
    out = []
    for title, name in PROVINCES.items():
        got = province_record(title, name)
        if got:
            top = got["religion"][0]
            log(f"  {name}: {len(got['religion'])} groups, "
                f"{top['group']} {top['pct']}%, {got['religion_year']}")
            out.append(got)
    if not out:
        raise SystemExit("netherlands: nothing was read; writing nothing")
    log(f"  {len(out)} of {len(PROVINCES)} provinces written")
    write_json(args.out or PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
