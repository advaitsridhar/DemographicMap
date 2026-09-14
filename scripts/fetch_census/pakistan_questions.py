#!/usr/bin/env python3
"""What Pakistan's census asks, read off the Bureau's own files.

Pakistan's 133 provincial and district records carry an empty ethnicity field.
An empty field on the map reads as "nobody has run this fetch yet", and before
it can be given a reason the reason has to be *measured*: is ethnicity a
question the census asks and the Bureau does not publish by district
(``not_available``), or a question the form has never put at all
(``not_collected``)? Those are opposite claims about the state, and only the
questionnaire and the published table series can tell them apart.

This probe is how that was settled. It is read-only -- it writes no records --
and its product is the log:

* **The table series.** ``table_N_kp_districts.pdf`` for N = 1..30, each
  fetched and its printed title read. That is the Bureau's whole published
  district-level series for the 2023 round, named by the office rather than
  guessed at, and what is in it is what the census publishes by district.

* **The questionnaire.** The Bureau's site runs on WordPress, whose REST API
  lists every file the office has uploaded. Asking it for "questionnaire",
  "form" and "census" enumerates the forms instead of guessing filenames --
  the mistake that cost Islamabad two census rounds behind
  ``table_9_islamabad_districts.pdf``.

* **The words.** Every PDF that answers is swept for ethnic, ethnicity, caste,
  tribe, biradari, qaum, race, nationality, mother tongue and religion, and
  the count of pages carrying each is printed. A form that asks religion and
  mother tongue and never once writes "ethnic" is the evidence the declaration
  rests on.

Usage:
    python -m scripts.fetch_census.pakistan_questions
    python -m scripts.fetch_census.pakistan_questions --tables 1-30
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ._shared import log

BASE = "https://www.pbs.gov.pk/wp-content/uploads/census_tables/tables"
SITE = "https://www.pbs.gov.pk"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                  "+https://github.com/advaitsridhar/DemographicMap)",
    "Accept": "*/*",
}

# What the form would have to carry for ethnicity to be a question Pakistan
# asks. "Qaum" and "biradari" are in the list because they are the words the
# thing actually goes by in Pakistan -- an English-language sweep for "ethnic"
# alone would miss a Urdu-language form entirely.
TERMS = ("ethnic", "ethnicity", "caste", "scheduled caste", "tribe", "tribal",
         "biradari", "qaum", "race", "racial", "nationality", "citizenship",
         "mother tongue", "language", "religion", "sect")


def get(url: str, timeout: int = 90) -> tuple[int, bytes, str]:
    """``(status, body, content-type)``, with a 404 reported rather than raised.

    A URL that 404s and a table that was never published are the same
    observation until something separates them, so the status is a finding and
    not an error: every candidate is asked and every answer is printed.
    """
    req = urllib.request.Request(url, headers=dict(HEADERS))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as err:
        return err.code, b"", err.headers.get("Content-Type", "") if err.headers else ""
    except Exception as err:                      # noqa: BLE001
        log(f"    {type(err).__name__}: {err}")
        return 0, b"", ""


def pages(blob: bytes) -> list[str]:
    """A PDF's pages as text, or an empty list if it will not open."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(blob)) as pdf:
            return [(page.extract_text() or "") for page in pdf.pages]
    except Exception as err:                      # noqa: BLE001
        log(f"    could not read as PDF: {type(err).__name__}: {err}")
        return []


def sweep(name: str, texts: list[str]) -> None:
    """How many of a document's pages carry each term, printed one per line."""
    if not texts:
        return
    lowered = [t.lower() for t in texts]
    log(f"    {name}: {len(texts)} pages")
    for term in TERMS:
        hits = [i + 1 for i, t in enumerate(lowered) if term in t]
        if hits:
            shown = ", ".join(str(h) for h in hits[:12])
            more = f" (+{len(hits) - 12} more)" if len(hits) > 12 else ""
            log(f"      {term:<16} {len(hits):>4} pages: {shown}{more}")
        else:
            log(f"      {term:<16}    0 pages")


def title_of(texts: list[str]) -> str:
    """The printed table heading, which is the office's own name for it."""
    for text in texts[:2]:
        for line in text.splitlines():
            line = " ".join(line.split())
            if re.match(r"TABLE\s*\d+", line, re.I):
                return line[:160]
    return "(no TABLE heading on the first two pages)"


def table_series(spec: str) -> None:
    """Every district-level table the Bureau publishes, by its printed title.

    Khyber Pakhtunkhwa's files are the ones read, because the four provinces
    are filed under one scheme and KP's are the smallest of them. What the
    series contains is a fact about the census's publication, not about KP.
    """
    first, _, last = spec.partition("-")
    numbers = range(int(first), int(last or first) + 1)
    log("table series -- table_N_kp_districts.pdf")
    for n in numbers:
        url = f"{BASE}/table_{n}_kp_districts.pdf"
        status, blob, ctype = get(url)
        if status != 200 or not blob:
            log(f"  {n:>3}  {status}  {url}")
            continue
        texts = pages(blob)
        log(f"  {n:>3}  200  {len(blob):>9,} bytes  {title_of(texts)}")


def wp(path: str, **params: Any) -> Any:
    """One WordPress REST call, or None.

    The Bureau's index page for the census tables answers 404, so there is no
    catalogue to read links off. The REST API is the catalogue the site keeps
    for itself: it lists the uploads by name, which is the difference between
    enumerating the office's forms and guessing at their filenames.
    """
    url = f"{SITE}/wp-json/wp/v2/{path}?" + urllib.parse.urlencode(params)
    status, blob, _ctype = get(url, timeout=60)
    log(f"  {status}  {url}")
    if status != 200 or not blob:
        return None
    try:
        return json.loads(blob)
    except ValueError:
        log("    not JSON")
        return None


def catalogue(terms: tuple[str, ...] = ()) -> list[str]:
    """PDF links the office's own upload index names, searched by word.

    ``terms`` overrides the questionnaire hunt, so the same catalogue can be
    asked a different question without a second probe: the point of going
    through the upload index rather than guessing filenames holds whatever is
    being looked for.
    """
    found: dict[str, str] = {}
    log("WordPress upload catalogue")
    for term in terms or ("questionnaire", "form", "census 2023", "census",
                          "training", "manual", "instruction"):
        items = wp("media", search=term, per_page=50, _fields="source_url,title")
        if not isinstance(items, list):
            continue
        for item in items:
            src = (item or {}).get("source_url") or ""
            title = ((item or {}).get("title") or {}).get("rendered") or ""
            if src and src.lower().endswith(".pdf"):
                found.setdefault(src, title)
    for term in terms or ("questionnaire", "census questionnaire"):
        items = wp("search", search=term, per_page=30)
        if isinstance(items, list):
            for item in items:
                log(f"    page: {(item or {}).get('title')!r} "
                    f"{(item or {}).get('url')}")
    for src, title in sorted(found.items()):
        log(f"    {src}   [{title}]")
    return sorted(found)


# Filenames worth asking for outright, because a catalogue that answers 404 or
# returns nothing is itself only one observation. Every one of these is printed
# with the status it answered, so an absent form and an unasked one are never
# the same line in this log.
CANDIDATES = (
    f"{SITE}/sites/default/files/population/2023/questionnaire.pdf",
    f"{SITE}/sites/default/files/population/2023/census_questionnaire.pdf",
    f"{SITE}/wp-content/uploads/2023/questionnaire.pdf",
    f"{SITE}/sites/default/files/population/2017/questionnaire.pdf",
    f"{SITE}/sites/default/files/population_census/census_2017_questionnaire.pdf",
    f"{SITE}/sites/default/files/PAKISTAN%20TEHSIL%20WISE%20FOR%20WEB%20CENSUS_2017.pdf",
    f"{SITE}/sites/default/files/population/2023/national_report.pdf",
    f"{SITE}/wp-content/uploads/census_tables/national/table_11_pakistan.pdf",
)


def spans(spec: str) -> list[int]:
    """"14-16,21,163-166" as a list of page numbers, one-based."""
    out: list[int] = []
    for piece in spec.split(","):
        piece = piece.strip()
        if not piece:
            continue
        first, _, last = piece.partition("-")
        out.extend(range(int(first), int(last or first) + 1))
    return out


def show(url: str, spec: str) -> None:
    """Print named pages of a PDF in full.

    A term sweep says which page carries a word and nothing about what the
    sentence around it claims -- and the difference decides this whole
    question. The National Census Report has "ethnicity" on one page of 234,
    and whether that page is a table of Pakistan's ethnic groups or a glossary
    entry explaining that the census records nationality instead is not
    something a hit count can tell you.

    It also guards the opposite error. Three of the Bureau's enumeration forms
    answered zero for every term in this list, religion and mother tongue
    included, which are certainly on the census form -- they are scans with no
    text layer, and reading that as "the form does not ask" would be the worst
    mistake available here.
    """
    status, blob, _ctype = get(url)
    if status != 200 or blob[:4] != b"%PDF":
        log(f"  {status}  not a PDF  {url}")
        return
    texts = pages(blob)
    log(f"  {url}  ({len(texts)} pages)")
    for number in spans(spec):
        if not 1 <= number <= len(texts):
            log(f"    page {number}: out of range")
            continue
        log(f"    ---- page {number} " + "-" * 50)
        for line in (texts[number - 1] or "(no text layer)").splitlines():
            log(f"    | {line}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables", default="1-30",
                    help="range of table numbers to ask the office for")
    ap.add_argument("--url", action="append", default=[],
                    help="a PDF to fetch and sweep for the terms, on its own: "
                         "given at least once, the table series and the "
                         "catalogue are not asked for again")
    ap.add_argument("--text", action="append", default=[],
                    help="URL#pages, e.g. '...report.pdf#163-166': print "
                         "those pages in full instead of counting words")
    ap.add_argument("--catalogue", action="append", default=[],
                    help="ask the office's upload index for these words and "
                         "print what it names, instead of the table series")
    args = ap.parse_args()

    log("pakistan_questions: what the 2023 census form asks, measured")
    if args.text:
        # Reading named pages is its own run: the table series above costs
        # half an hour of the runner's time and answers a question already
        # answered.
        for spec in args.text:
            url, _, want = spec.partition("#")
            show(url, want or "1")
        return 0
    if args.catalogue:
        # The catalogue on its own. Asking the office what it has published
        # about a place is a different question from what its form asks, and
        # it should not cost the half-hour the table series takes.
        catalogue(tuple(args.catalogue))
        return 0
    if args.url:
        # Same reason: a named document to sweep is a follow-up question, and
        # re-enumerating 26 table PDFs to ask it costs half an hour and
        # answers nothing new.
        log("term sweep")
        for url in args.url:
            status, blob, _ctype = get(url)
            if status != 200 or blob[:4] != b"%PDF":
                log(f"  {status}  not a PDF  {url}")
                continue
            log(f"  {url}")
            sweep(url.rsplit("/", 1)[-1], pages(blob))
        return 0
    table_series(args.tables)

    urls = list(catalogue())
    log("named candidates")
    for url in CANDIDATES:
        status, blob, ctype = get(url)
        log(f"  {status}  {len(blob):>9,} bytes  {ctype:<24} {url}")
        if status == 200 and blob[:4] == b"%PDF":
            urls.append(url)
    urls += list(args.url)

    log("term sweep")
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        status, blob, _ctype = get(url)
        if status != 200 or blob[:4] != b"%PDF":
            log(f"  {status}  not a PDF  {url}")
            continue
        log(f"  {url}")
        sweep(url.rsplit("/", 1)[-1], pages(blob))
    return 0


if __name__ == "__main__":
    sys.exit(main())
