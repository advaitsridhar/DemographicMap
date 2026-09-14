#!/usr/bin/env python3
"""Is there a Bangladeshi mother-tongue table below the division?

The census 2022 adapter publishes mother tongue for the eight divisions and a
stated gap for all sixty-four zilas, on the strength of one reading: the
Socio-Economic and Demographic Survey 2023 prints Table 3.6 by division only.
That is a claim about one publication, and "no district language figure exists"
is a claim about several. This asks the others.

Four questions, one download each, nothing written and nothing committed:

* the census's own admin-2 workbook -- every sheet name, not just the three
  the adapter reads, because a language sheet the adapter never asked for
  would not have announced itself;
* the census's *National Report (Volume I)* -- the whole 520 pages searched for
  mother tongue, language, bilingual and the named minority tongues, and its
  list of tables printed, because a district language table would be in it;
* what the Bureau's own publication pages link to -- the Zila Reports, the
  Community Series and anything else, so a route nobody has opened is at least
  named;
* whichever further PDFs are given on the command line.

Read-only, and the output is the log.

Usage:
    python -m scripts.probe_bangladesh_language
    python -m scripts.probe_bangladesh_language --pdf https://example.org/zila.pdf
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import http_get, log  # noqa: E402

WORKBOOK = ("https://data.humdata.org/dataset/"
            "a6fedebe-72fe-4fc2-8657-1580acfa32c6/resource/"
            "72eaaa6c-6a30-4efd-bad9-02133b316ea8/download/"
            "bangladesh_bbs_population-and-housing-census-dataset_2022_admin-02.xlsx")

REPORT = ("https://objectstorage.ap-dcc-gazipur-1.oraclecloud15.com/n/axvjbnqprylg/"
          "b/V2Ministry/o/office-bbs/2024/12/9ce5bd160bb14a1ab1eabe886adddb9a.pdf")

# The Bureau's own pages. Reachable only with the intermediate certificate the
# server omits supplied from the leaf's AIA extension -- full verification,
# see scripts/probe_tls.py.
PAGES = [
    "https://bbs.gov.bd/site/page/47856ad0-7e1c-4aab-bd78-892733bc06eb/"
    "Population-and-Housing-Census",
    "https://bbs.gov.bd/site/page/b588b454-0f88-4679-bf20-90e06dc1d10b/"
    "Census",
]

# What a mother-tongue table would have to say somewhere on its face, and the
# tongues a real breakdown would name. "Others" against "Bangla" is what the
# survey already publishes; a named second language is what would make a
# composition.
TERMS = ["mother tongue", "mother-tongue", "language", "languages", "bilingual",
         "spoken", "speak", "dialect", "linguistic"]
TONGUES = ["Chakma", "Marma", "Santal", "Saontal", "Garo", "Tripura", "Mro",
           "Rakhain", "Manipuri", "Urdu", "Bishnupriya", "Tanchangya",
           "Tonchonga", "Khasi", "Hajong", "Munda", "Oraon", "Rohingya",
           "Bawm", "Khumi", "Chak", "Pankho", "Lushai", "Koch", "Dalu",
           "Rajbanshi", "Sylheti", "Chittagonian", "Arabic", "English"]


def workbook_sheets(url: str) -> None:
    """Every sheet of the admin-2 workbook, named, with its header row.

    The adapter opens three sheets by name. A sheet it does not ask for is a
    sheet it cannot report missing, so the question "is there a language sheet"
    is answered by listing all of them rather than by looking one up.
    """
    import openpyxl

    log(f"\n=== workbook: {url.rsplit('/', 1)[-1]} ===")
    blob = http_get(url, binary=True, timeout=180, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                      "+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/vnd.openxmlformats-officedocument."
                  "spreadsheetml.sheet,*/*"})
    log(f"  {len(blob):,} bytes")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    try:
        log(f"  {len(book.sheetnames)} sheets:")
        for i, name in enumerate(book.sheetnames, 1):
            sheet = book[name]
            header: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                header = ["" if c is None else str(c).strip() for c in row]
                break
            mark = " <-- LANGUAGE?" if any(
                term in name.lower() or any(term in h.lower() for h in header)
                for term in ("tongue", "language", "bangla", "speak",
                             "lingu", "dialect")) else ""
            log(f"   {i:3d}. {name!r} "
                f"({sheet.max_row}x{sheet.max_column}){mark}")
            log(f"        header: {', '.join(h for h in header if h)[:400]}")
    finally:
        book.close()


# The 2011 series lives on the Bureau's legacy host, 203.112.218.65:8008,
# which answers slowly enough that the default patience -- four tries of five
# minutes -- can hold a runner for twenty minutes on one unreachable file.
# A probe that never returns teaches nothing, so its patience is bounded and
# settable: a slow host and an absent one are different findings, and the log
# has to be able to say which.
PDF_TIMEOUT = 120
PDF_RETRIES = 2


def pdf_text(url: str, timeout: int = PDF_TIMEOUT,
             retries: int = PDF_RETRIES) -> list[str]:
    import pypdf

    blob = http_get(url, binary=True, timeout=timeout, retries=retries)
    log(f"  {len(blob):,} bytes")
    reader = pypdf.PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


def search_pdf(url: str, label: str, timeout: int = PDF_TIMEOUT,
               retries: int = PDF_RETRIES) -> None:
    """A whole PDF searched for language, and its table headings listed.

    Two different questions, and both have to be asked. A term search says
    whether the word appears; the list of table headings says at what
    geography the report tabulates anything at all -- which is the question
    that actually decides whether a district figure can exist.
    """
    log(f"\n=== {label} ===")
    log(f"  {url}")
    try:
        pages = pdf_text(url, timeout=timeout, retries=retries)
    except Exception as exc:                                   # noqa: BLE001
        log(f"  UNREADABLE: {type(exc).__name__}: {exc}")
        return
    log(f"  {len(pages)} pages")
    whole = "\n".join(pages).lower()

    for term in TERMS:
        hits = [i + 1 for i, page in enumerate(pages) if term in page.lower()]
        log(f"  {term!r}: {len(hits)} page(s)"
            + (f" -> {hits[:30]}" if hits else ""))
    named = {t: whole.count(t.lower()) for t in TONGUES}
    log("  named tongues: "
        + (", ".join(f"{k} x{v}" for k, v in named.items() if v) or "none"))

    # Every line that looks like a table heading, and what geography it names.
    # "Table P29 ... by Category, Sex and Division" is the shape that decides
    # this: a heading ending in District is a district table.
    headings = re.findall(r"(?im)^\s*(table\s+[A-Za-z]?[\d.]+\s*[:.\-]?\s.{0,140})$",
                          "\n".join(pages))
    seen: dict[str, int] = {}
    for heading in headings:
        key = " ".join(heading.split())
        seen[key] = seen.get(key, 0) + 1
    log(f"  {len(seen)} distinct table headings")
    for word in ("District", "Zila", "Upazila", "Division", "Union"):
        count = sum(1 for k in seen if word.lower() in k.lower())
        log(f"    headings naming {word}: {count}")
    interesting = [k for k in seen
                   if any(t in k.lower() for t in
                          ("tongue", "language", "lingu", "bangla"))]
    log(f"  table headings naming a language: {interesting or 'none'}")

    # The pages themselves, for whatever matched, so a heading found here can
    # be read rather than merely counted.
    for i, page in enumerate(pages, 1):
        low = page.lower()
        if "mother tongue" in low or "mother-tongue" in low:
            body = "\n".join(line.rstrip() for line in page.splitlines()
                             if line.strip())
            log(f"\n  --- page {i} (mother tongue) " + "-" * 40)
            log(body[:1800])


def links(url: str) -> None:
    """What a Bureau publication page actually offers."""
    log(f"\n=== page: {url} ===")
    try:
        body = http_get(url, aia=True, timeout=90)
    except Exception as exc:                                   # noqa: BLE001
        log(f"  UNREACHABLE: {type(exc).__name__}: {exc}")
        return
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    log(f"  {len(body):,} characters")
    found = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body,
                       re.I | re.S)
    rows = []
    for href, text in found:
        text = " ".join(re.sub(r"<[^>]+>", " ", text).split())
        rows.append((urllib.parse.urljoin(url, href), text))
    log(f"  {len(rows)} links")
    for href, text in rows:
        blob = f"{href} {text}".lower()
        if any(word in blob for word in
               ("zila", "district", "community", "union", "report", ".pdf",
                "census", "tongue", "language", "series")):
            log(f"    {text[:90]!r}\n        {href}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", action="append", default=[],
                    help="a further PDF to search; repeatable")
    ap.add_argument("--skip-workbook", action="store_true")
    ap.add_argument("--skip-report", action="store_true")
    ap.add_argument("--skip-pages", action="store_true")
    ap.add_argument("--pdf-timeout", type=int, default=PDF_TIMEOUT)
    ap.add_argument("--pdf-retries", type=int, default=PDF_RETRIES)
    args = ap.parse_args()

    if not args.skip_workbook:
        try:
            workbook_sheets(WORKBOOK)
        except Exception as exc:                               # noqa: BLE001
            log(f"  workbook unreadable: {type(exc).__name__}: {exc}")
    if not args.skip_report:
        search_pdf(REPORT, "Census 2022 National Report (Volume I)")
    if not args.skip_pages:
        for page in PAGES:
            links(page)
    for extra in args.pdf:
        search_pdf(extra, f"extra: {extra.rsplit('/', 1)[-1]}",
                   timeout=args.pdf_timeout, retries=args.pdf_retries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
