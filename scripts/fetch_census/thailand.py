#!/usr/bin/env python3
"""Thailand: religion by province, from the 2000 census final reports.

Thailand's 77 provinces carried no religion at all. The National Statistical
Office refuses automated readers on every host this project has tried, so
its own tables cannot be read; but the 2000 Population and Housing Census
published a final report per province (``web.nso.go.th/pop2000/finalrep/``),
and a Wikipedia article -- "Nationality, religion, and language data for the
provinces of Thailand" -- transcribes the Buddhist, Muslim and Christian
shares from all 76 of them into one sortable table, each row citing the
report it was read from. That table is what this reads, through the
MediaWiki API, and the record's source is the NSO report the row cites, not
the article.

**What is and is not taken.** The table has eleven columns: Thai nationals
1970 and 2000, Buddhist / Muslim / Christian for 1990 and 2000, and a free-text
"linguistic minorities" cell for each of the two years. Religion 2000 is read
as printed; 1990 is older and is not. Nationality is citizenship, not
ethnicity, so it is left alone. The language cells list some minorities
("Malay (66.1%), Chinese (3.0%)") and are silent about the rest, which is not
a partition of anyone, so they stay unread -- the province keeps the gap
reason it already carries for that field.

**Arithmetic.** The three shares rarely reach 100; the rest is the census's
"other" and "unknown", which the article does not carry, so it is published
as one remainder group, "Other or not stated", when it is at least 0.05%. An
``N/A`` means the report gave nothing for that faith (below 0.1% or not
published) and the group is simply absent. A province whose three shares add
to more than 100.5% refuses the run: that would mean the columns were read in
the wrong order.

**Bueng Kan** was carved out of Nong Khai in 2011, so the 2000 census has no
row for it and it stays empty; Nong Khai's figure is Nong Khai's alone and is
not stretched over both.

**Names.** The article spells four provinces as one word or with different
spacing from the boundary file (Buriram / Buri Ram, Chonburi / Chon Buri,
Samutprakan / Samut Prakan, Sisaket / Si Sa Ket); those are declared as
aliases. Kalasin is drawn without the word "Province", so every record carries
its bare name as an alias too.

Usage:
    python -m scripts.fetch_census.thailand
    python -m scripts.fetch_census.thailand --wikitext saved.txt   # offline
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_json, log, record, write_json

OUT = "thailand_province.json"
YEAR = 2000
PAGE = "Nationality, religion, and language data for the provinces of Thailand"
API = ("https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json"
       "&formatversion=2&redirects=1&page=" + PAGE.replace(" ", "_"))
SOURCE = "NSO, 2000 Population and Housing Census, provincial final reports"
COMPILED_BY = f"compiled in the Wikipedia article '{PAGE}' (CC BY-SA 4.0)"
LICENCE = "Open Government Data of Thailand (NSO publication); compilation CC BY-SA 4.0"
EXPECTED = 76                                     # 77 provinces less Bueng Kan

# The header this was written against, in order. A different order refuses.
HEADER = ["province name", "Thai nationals in 1970", "Thai nationals in 2000",
          "Buddhist in 1990", "Buddhist in 2000", "Muslim in 1990", "Muslim in 2000",
          "Christian in 1990", "Christian in 2000",
          "Linguistic minorities in 1990", "Linguistic minorities in 2000"]
COLUMNS = {"Buddhism": 4, "Islam": 6, "Christianity": 8}
REMAINDER = "Other or not stated"

# Article spelling -> the boundary file's.
ALIASES = {
    "Buriram": ["Buri Ram Province", "Buri Ram"],
    "Chonburi": ["Chon Buri Province", "Chon Buri"],
    "Samutprakan": ["Samut Prakan Province", "Samut Prakan"],
    "Sisaket": ["Si Sa Ket Province", "Si Sa Ket"],
}

LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
CITED = re.compile(r"url=\s*(https?://web\.nso\.go\.th/\S+?)\s*[|}]")


def plain(cell: str) -> str:
    """A header or value cell without its links, refs and markup."""
    cell = REF.sub("", cell)
    cell = LINK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(1), cell)
    cell = cell.replace("'''", "").replace("''", "").replace("%", "")
    return " ".join(cell.split())


def percent(cell: str) -> float | None:
    """'99.8%' -> 99.8; '99.5' (the % forgotten) -> 99.5; 'N/A' -> None."""
    text = plain(cell)
    if text.upper() in ("N/A", "NA", "", "-"):
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        raise SystemExit(f"thailand: cannot read {cell!r} as a percentage")
    return float(text)


def table(wikitext: str) -> list[list[str]]:
    """The one sortable table's rows, cells still in wikitext."""
    start = wikitext.find('{| class="wikitable sortable"')
    if start < 0:
        raise SystemExit("thailand: the article no longer carries a sortable table")
    end = wikitext.find("\n|}", start)
    rows: list[list[str]] = []
    for chunk in wikitext[start:end].split("\n|-"):
        lines = [ln for ln in chunk.strip().split("\n") if ln.startswith(("!", "|"))]
        if not lines:
            continue
        line = lines[-1]                            # the row's one content line
        if line.startswith("|+"):
            continue                                # the caption
        # A header row may separate its cells with "!!" or, as this one
        # does, with "||"; a data row only ever uses "||".
        cells = re.split(r"!!|\|\|", line[1:]) if line.startswith("!") else line[1:].split("||")
        rows.append([c.strip() for c in cells])
    return rows


def province(cell: str) -> tuple[str, str | None]:
    """The first cell -> (name as the boundary file spells it, the NSO report cited)."""
    m = LINK.search(cell)
    if not m:
        raise SystemExit(f"thailand: no province link in {cell!r}")
    target = re.sub(r"\s+province$", "", m.group(1), flags=re.I).strip()
    cited = CITED.search(cell)
    return target, cited.group(1) if cited else None


def build(wikitext: str) -> list[dict[str, Any]]:
    rows = table(wikitext)
    header = [plain(c) for c in rows[0]]
    if header != HEADER:
        raise SystemExit(f"thailand: the table's columns changed: {header}")

    records: list[dict[str, Any]] = []
    for cells in rows[1:]:
        if len(cells) != len(HEADER):
            raise SystemExit(f"thailand: row has {len(cells)} cells: {cells[0][:60]!r}")
        bare, report = province(cells[0])
        shares = {faith: percent(cells[i]) for faith, i in COLUMNS.items()}
        known = {faith: pct for faith, pct in shares.items() if pct is not None}
        if not known:
            log(f"  {bare}: no 2000 religion in the table")
            continue
        summed = sum(known.values())
        if summed > 100.5:
            raise SystemExit(f"thailand: {bare} adds to {summed:.1f}%; wrong columns")
        rest = round(100.0 - summed, 1)
        if rest >= 0.05:
            known[REMAINDER] = rest
        bars = sorted(({"group": g, "pct": p} for g, p in known.items()),
                      key=lambda r: r["pct"], reverse=True)

        name = bare if bare == "Bangkok" else f"{bare} Province"
        aliases = ALIASES.get(bare, [])
        if bare != "Bangkok" and bare not in aliases:
            aliases = aliases + [bare]
        source = {"field": "religion", "name": SOURCE, "url": report or API,
                  "license": LICENCE}
        records.append(record(
            f"THA-{bare.replace(' ', '_')}", name,
            level="admin1", parent="THA", country="THA", aliases=aliases,
            religion=bars,
            religion_note=(f"{SOURCE}, {COMPILED_BY}. Shares as printed in the "
                           f"provincial report; '{REMAINDER}' is what the three named "
                           f"faiths leave of 100%. A faith the report did not give "
                           f"is absent, not zero."),
            sources=[source],
        ))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--wikitext", default=None,
                    help="read a saved copy of the article's wikitext instead of the API")
    args = ap.parse_args()

    log(f"thailand: religion by province, {SOURCE}")
    if args.wikitext:
        wikitext = Path(args.wikitext).read_text(encoding="utf-8")
    else:
        parsed = http_json(API, timeout=90).get("parse") or {}
        wikitext = parsed.get("wikitext") or ""
        log(f"  {PAGE!r}: {len(wikitext):,} bytes of wikitext")
    records = build(wikitext)
    log(f"  {len(records)} provinces with a 2000 religion")
    if len(records) != EXPECTED:
        raise SystemExit(f"thailand: expected {EXPECTED} provinces, read {len(records)}")
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
