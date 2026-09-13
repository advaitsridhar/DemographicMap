#!/usr/bin/env python3
"""Bhutan -- Population & Housing Census 2017, population by gewog.

**This adapter publishes population and nothing else, and the reason is worth
stating rather than leaving as an empty field.** Bhutan's census does not ask
religion, language or ethnicity. That is not "does not publish": the 2017
national report runs 288 pages over education, fertility, mortality,
disability, labour, migration and housing, and the words religion, ethnic,
Hindu, Buddhist and mother tongue occur on none of them except two pages
describing the census's own publicity -- talk shows held in Dzongkha,
Sharchopkha and Lhotshamkha, and the literacy test card. The 2005 round is the
same. So the three composition fields are declared ``not_collected`` in
``scripts/common.py`` and this file fills the one thing the census does count.

**The one identity-adjacent split the census does publish is citizenship**,
Bhutanese against non-Bhutanese, by dzongkhag and by gewog. It is deliberately
not read here and must not be used as an ethnicity proxy: citizenship is
precisely the contested variable in Bhutan, the 1985 Citizenship Act being how
much of the Lhotshampa population lost its legal standing before leaving.
Table 2.1, which this reads, is the whole resident population "irrespective of
their nationality" -- the report's own words -- which is the figure that
belongs on a map of where people are.

Three things about the documents shape the reader.

**The table shares its page with two columns of narrative.** ``--layout``
extraction interleaves them: "4,183 persons during the intercensal" sits among
the data rows and ends in no numbers, while "Barshong 423 419 842" is a row.
Splitting on whitespace and counting numbers cannot tell those apart reliably.
So the header row -- "Gewog/Town Male Female Total" -- is found first and its
own words fix the table's left edge; everything to the left of that is prose
and is never considered.

**Towns are counted beside gewogs, not inside them.** Tsirang prints two town
rows and twelve gewog rows, and all fourteen add to the printed total: 3,510
urban plus 18,866 rural is 22,376. geoBoundaries draws no town, so the towns
have nowhere to go -- they are declared rather than dropped, and the dzongkhag
above them carries its own printed total, which includes them. The gewog layer
is therefore short of its parent by the urban population, by construction, and
says so.

**The narrative is not always about the dzongkhag whose tables these are.**
Tsirang's page 12 opens "Trashigang Dzongkhag as of the census...", a
copy-paste left in NSB's own text. The tables are Tsirang's. Read the tables,
never the sentences.

Usage:
    python -m scripts.fetch_census.bhutan
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json,
)

YEAR = 2017
SOURCE = ("National Statistics Bureau of Bhutan, Population & Housing Census "
          "of Bhutan 2017, Table 2.1: population distribution by gewog and "
          "town")
LICENCE = "National Statistics Bureau of Bhutan. Official publication."
BASE = "https://nsb.gov.bt/wp-content/uploads/2026/08"

# The twenty dzongkhag reports, by the file name NSB gives each. The index at
# https://www.nsb.gov.bt/phcb links exactly these twenty plus the national
# report; the /publications/ tree does not link them at all, and the URL every
# search engine still cites for the national report (dlm_uploads/2020/07/)
# is a 404. Asked for and answered: all twenty returned 200.
DZONGKHAGS: dict[str, str] = {
    "Bumthang": "PHCB2017_Bumthang.pdf",
    "Chhukha": "PHCB2017_Chhukha.pdf",
    "Dagana": "PHCB2017_Dagana.pdf",
    "Gasa": "PHCB2017_Gasa.pdf",
    "Haa": "PHCB2017_Haa.pdf",
    "Lhuentse": "PHCB2017_Lhuentse.pdf",
    "Monggar": "PHCB2017_Monggar.pdf",
    "Paro": "PHCB2017_Paro.pdf",
    "Pema Gatshel": "PHCB2017_Pema-Gatshel.pdf",
    "Punakha": "PHCB2017_Punakha.pdf",
    "Samdrup Jongkhar": "PHCB2017_Samdrup-Jongkhar.pdf",
    "Samtse": "PHCB2017_Samtse.pdf",
    "Sarpang": "PHCB2017_Sarpang.pdf",
    "Thimphu": "PHCB2017_Thimphu.pdf",
    "Trashi Yangtse": "PHCB2017_Trashi-Yangtse.pdf",
    "Trashigang": "PHCB2017_Trashigang.pdf",
    "Trongsa": "PHCB2017_Trongsa.pdf",
    "Tsirang": "PHCB2017_Tsirang.pdf",
    "Wangdue Phodrang": "PHCB2017_Wangdue-Phodrang.pdf",
    "Zhemgang": "PHCB2017_Zhemgang.pdf",
}

# What geoBoundaries calls each dzongkhag where it differs. "Thimpu" is the
# one that cost something: the dzongkhag carried no population at all because
# of a missing h.
DZONGKHAG_ALIASES: dict[str, tuple[str, ...]] = {
    "Thimphu": ("Thimpu",),
    "Monggar": ("Mongar",),
    "Pema Gatshel": ("Pemagatshel", "Pemagatshel Dzongkhag"),
    "Trashi Yangtse": ("Trashiyangtse", "Tashi Yangtse"),
    "Chhukha": ("Chukha",),
    "Lhuentse": ("Lhuntse",),
}

# The census's own total, from the national report, and the control every
# dzongkhag read here is held to collectively.
NATIONAL = 727_145

HEADER = ("Gewog/Town", "Male", "Female", "Total")
SECTIONS = {"Urban", "Rural"}
NUMBER = re.compile(r"^[\d,]+$")

# A town row ends in the word Town or Thromde. Bhutan's four thromdes --
# Thimphu, Phuentsholing, Gelephu and Samdrup Jongkhar -- are municipalities
# reported beside the gewogs, and geoBoundaries draws neither them nor the
# smaller towns.
TOWN = re.compile(r"\b(Town|Thromde)$")

POPULATION_NOTE = (
    "2017 Population and Housing Census, the whole resident population "
    "'irrespective of their nationality' as the report puts it. Bhutan's "
    "census does not ask religion, language or ethnicity, so those three are "
    "declared rather than left empty.")
GEWOG_NOTE = (
    " This is the gewog's own count. Towns and thromdes are enumerated beside "
    "the gewogs rather than inside them and the boundary file draws none of "
    "them, so a dzongkhag's gewogs come to less than the dzongkhag itself by "
    "its urban population -- 37.8% of Bhutan nationally, and named on the "
    "dzongkhag's record.")


def words_by_row(blob: bytes, tolerance: float = 2.0):
    """Every page as rows of (x0, x1, text), from the words' own boxes.

    The same reading pakistan.py uses, and for a related reason: a page here
    carries two columns of prose beside the table, and only a word's position
    says which it belongs to.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False,
                                       keep_blank_chars=False)
            rows: list[tuple[float, list[tuple[float, float, str]]]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1),
                                                     w["x0"])):
                top = round(word["top"], 1)
                cell = (word["x0"], word["x1"], word["text"])
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append(cell)
                else:
                    rows.append((top, [cell]))
            yield [sorted(cells) for _top, cells in rows]


def table(blob: bytes, dzongkhag: str
          ) -> tuple[dict[str, int], dict[str, int], int]:
    """Table 2.1 for one dzongkhag: its gewogs, its towns, and its total.

    Two things bound the read, and the first attempt had only one of them.

    **The header fixes the table's left edge**, and nothing to the left of it
    is considered. That is the defence against the narrative: prose and data
    share a baseline on these pages, so a rule counting numbers in a line
    would take "4,183 persons during the intercensal" for a row.

    **The table is bounded by its pages**, not only by its printed Total.
    Bounding it by the Total alone let the reader run off the end of Table 2.1
    and through the rest of the document -- Tsirang came back with 885 gewogs
    holding 1.2 million people against a printed 22,376, which the
    reconciliation caught and refused. So collection starts on the page
    carrying the header and stops at the printed Total or at the first page
    that yields no rows, whichever comes first.

    A row is exactly three figures with a name before them. Exactly, not at
    least: a line of prose that happens to carry four numbers is not a row of
    this table, and treating it as one is how the first attempt filled up.
    """
    gewogs: dict[str, int] = {}
    towns: dict[str, int] = {}
    printed = 0
    edge: float | None = None
    reading = False

    for rows in words_by_row(blob):
        if printed:
            break
        found_here = False
        for cells in rows:
            texts = [t for _a, _b, t in cells]
            if edge is None:
                if all(word in texts for word in HEADER):
                    edge = min(x0 for x0, _x1, t in cells if t == HEADER[0])
                    reading = True
                    found_here = True
                continue
            inside = [(x0, x1, t) for x0, x1, t in cells if x0 >= edge - 3.0]
            words = [t for _a, _b, t in inside]
            if not words or (len(words) == 1 and words[0] in SECTIONS):
                continue
            figures = [t for t in words if NUMBER.match(t)]
            if len(figures) != 3 or words[-3:] != figures:
                continue
            name = " ".join(words[:-3]).strip()
            if not name or NUMBER.match(name):
                continue
            try:
                total = int(figures[-1].replace(",", ""))
            except ValueError:
                continue
            found_here = True
            if name == "Total":
                printed = total
                break
            if TOWN.search(name):
                towns[name] = total
            else:
                gewogs[name] = total
        # A page that carried none of this table's rows ends it. Table 2.1
        # runs to one page in the small dzongkhags and two in the large ones,
        # and nothing later in the report is it.
        if reading and not found_here:
            break

    if not gewogs:
        raise SystemExit(f"bhutan: {dzongkhag}: no gewog rows read from "
                         f"Table 2.1")
    if not printed:
        raise SystemExit(
            f"bhutan: {dzongkhag}: Table 2.1 has no printed Total row, which "
            f"is the only thing that says these {len(gewogs)} gewogs are all "
            f"of them")
    counted = sum(gewogs.values()) + sum(towns.values())
    if counted != printed:
        raise SystemExit(
            f"bhutan: {dzongkhag}: {len(gewogs)} gewogs and {len(towns)} "
            f"towns hold {counted:,} against the {printed:,} printed beside "
            f"them -- {printed - counted:+,}. A gewog this reader never "
            f"noticed is a hole, and every other check here passes over it")
    return gewogs, towns, printed


def fetch(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                      "+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/pdf,*/*",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default="",
                    help="one dzongkhag, for working out a layout")
    args = ap.parse_args()

    log("bhutan: National Statistics Bureau, PHCB 2017 Table 2.1")
    records: list[dict[str, Any]] = []
    absent: list[str] = []
    national = 0
    urban_total = 0
    wanted = {k: v for k, v in DZONGKHAGS.items()
              if not args.only or k == args.only}

    for dzongkhag, filename in wanted.items():
        url = f"{BASE}/{filename}"
        try:
            blob = fetch(url)
        except Exception as err:                        # noqa: BLE001
            absent.append(f"{dzongkhag}: {type(err).__name__} {str(err)[:60]}")
            continue
        gewogs, towns, printed = table(blob, dzongkhag)
        national += printed
        urban_total += sum(towns.values())
        log(f"  {dzongkhag}: {len(gewogs)} gewogs, {len(towns)} town(s), "
            f"{printed:,} people")

        cite = [{"field": "population", "name": SOURCE, "url": url,
                 "license": LICENCE}]
        note = POPULATION_NOTE
        if towns:
            note += (" Of these, " + f"{sum(towns.values()):,}"
                     + " are counted in "
                     + ", ".join(sorted(towns))
                     + ", which the boundary file does not draw, so the "
                       "gewogs below come to that much less than this row.")
        records.append(record(
            f"BTN-{dzongkhag.lower().replace(' ', '-')}", dzongkhag,
            level="admin1", parent="BTN", country="BTN",
            aliases=list(DZONGKHAG_ALIASES.get(dzongkhag, ())),
            population=measure(printed, year=YEAR, source=SOURCE),
            population_note=note,
            sources=list(cite)))
        for name, people in sorted(gewogs.items()):
            records.append(record(
                f"BTN-{dzongkhag.lower().replace(' ', '-')}-"
                f"{name.lower().replace(' ', '-')}",
                name, level="admin2", parent="BTN", country="BTN",
                parent_name=dzongkhag,
                parent_aliases=list(DZONGKHAG_ALIASES.get(dzongkhag, ())),
                population=measure(people, year=YEAR, source=SOURCE),
                population_note=POPULATION_NOTE + GEWOG_NOTE,
                sources=list(cite)))

    for line in absent:
        log(f"  NOT READ -- {line}")
    if absent:
        raise SystemExit(
            f"bhutan: {len(absent)} of {len(wanted)} dzongkhag reports were "
            f"not read; refusing to write a partial Bhutan")

    if not args.only and national != NATIONAL:
        raise SystemExit(
            f"bhutan: the twenty dzongkhags hold {national:,} against the "
            f"{NATIONAL:,} the national report prints -- "
            f"{NATIONAL - national:+,}. Each dzongkhag reconciled to its own "
            f"printed total, so this is a whole dzongkhag read twice or not "
            f"at all, which no per-file check can see")
    if not args.only:
        log(f"  the twenty dzongkhags come to {national:,}, the national "
            f"report's own figure")

    out = args.out or PROCESSED / "bhutan_gewog.json"
    write_json(out, records)
    gewogs = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {len(records) - gewogs} dzongkhags and {gewogs} gewogs, "
        f"{urban_total:,} people in towns with no shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
