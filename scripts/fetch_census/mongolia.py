#!/usr/bin/env python3
"""Mongolia: ethnicity and religion by aimag and soum, from the 2020 census.

The National Statistics Office published, beside the national report, a
results book for each of the 21 aimags and the capital -- "<aimag> аймгийн
хүн ам, орон сууцны 2020 оны улсын тооллогын НЭГДСЭН ДҮН", written by that
aimag's own statistics department. Chapter three of every book is "Улсын
харьяалал, үндэс угсаа, шашин" and carries what this project wants: the
aimag's Mongolian citizens counted by ethnic group, and the religion of the
population aged 15 and over. Some books also print the distribution of each
ethnic group across the aimag's soums, which is the only soum-level figure
the census published on any of the three fields.

**Where the books are.** They were served from ``1212.mn`` by an ASP.NET
handler, ``BookLibraryDownload.ashx?url=<file>&ln=Mn``. That site is gone:
``nso.mn`` and ``www.1212.mn`` now serve one Next.js application, the
handler answers 200 with an empty body over plain HTTP, ``www2.1212.mn``
answers HTTPS with a certificate that expired, and ``opendata.1212.mn`` --
the statistical database's API, which the CRAN package NSO1212 was written
against -- no longer resolves at all. The books are read from the Internet
Archive, the way ``romania.py`` reads the 2011 census: one CDX query lists
every archived capture of every book, and the largest capture of each is
fetched, because the Archive truncated several of them at exactly one
mebibyte and a truncated PDF has no pages at all.

``--fetch`` does that, extracts the pages of each book that mention ethnic
group, religion or the sex ratio, and writes them to
``data/raw/mongolia/<aimag>.txt``; the adapter reads those text files, so a
build without network still runs and what was read is committed beside the
code that read it. Rows are rebuilt from the glyphs' coordinates
(``probe_pdf.laid_out``) because these books set their tables in two
columns and a reader that takes pypdf's string order gets a page of figures
followed by a page of labels.

Usage:
    python -m scripts.fetch_census.mongolia --fetch
    python -m scripts.fetch_census.mongolia
    python -m scripts.fetch_census.mongolia --probe --get https://data.nso.mn/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, RAW, log
from common import http_get  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = "mongolia.json"
YEAR = 2020
RAW_DIR = RAW / "mongolia"
BYTES = 3000
AGENT = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"

CDX = ("http://web.archive.org/cdx/search/cdx?url=1212.mn&matchType=domain"
       "&output=text&limit=6000&fl=timestamp,original,length"
       "&filter=mimetype:application/pdf"
       "&filter=original:.*(XAOCT|url=Khovd[.]pdf|url=Dundgovi[.]pdf|url=Khentii[.]pdf).*")
REPLAY = "https://web.archive.org/web/{timestamp}id_/{original}"

# The 22 first-level units as site/data/admin1/MNG.json names them, and the
# file each aimag's book was served under. Three aimags -- Dundgovi, Khentii
# and Khovd -- published theirs without the XAOCT stem the other nineteen
# share; their plain names are matched on "url=<name>.pdf" so that a
# yearbook called Khovd_2019.pdf is not mistaken for the census book.
BOOKS: dict[str, str] = {
    "Arkhangai": "Arkhangai_XAOCT_Negdsen_dun.pdf",
    "Bayan-Ölgii": "Bayan-Ulgii_XAOCT_Negdsen_Dun.pdf",
    "Bayankhongor": "Bayankhongor_XAOCT_Negdsen_dun.pdf",
    "Bulgan": "Bulgan_XAOCT_Negdsen_dun.pdf",
    "Darkhan-Uul": "Darkhan-Uul_XAOCT_Negdsen%20dun.pdf",
    "Dornod": "Dornod_XAOCT_Negdsen_Dun.pdf",
    "Dornogovi": "Dornogovi_XAOCT_Negdsen_Dun.pdf",
    "Dundgovi": "Dundgovi.pdf",
    "Govi-Altai": "Govi-Altai_XAOCT_Negdsen%20dun.pdf",
    "Govisumber": "Govisumber_XAOCT_Negdsen_dun.pdf",
    "Hovsgel": "Khuvsgul_XAOCT_Negdsen_Dun.pdf",
    "Khentii": "Khentii.pdf",
    "Khovd": "Khovd.pdf",
    "Orkhon": "Orkhon_XAOCT_Negdsen_Dun.pdf",
    "Selenge": "Selenge_XAOCT_Negdsen_dun.pdf",
    "Sükhbaatar": "Sukhbaatar_XAOCT_Negdsen_dun.pdf",
    "Töv": "Tuv_XAOCT_Negdsen%20dun..pdf",
    "Ulaanbaatar": "Ulaanbaatar_XAOCT_Negdsen_dun.pdf",
    "Uvs": "Uvs_XAOCT_Negdsen_Dun.pdf",
    "Zavkhan": "Zavkhan_XAOCT_Negdsen_dun.pdf",
    "Ömnögovi": "Umnugovi_XAOCT_Negdsen_Dun.pdf",
    "Övörkhangai": "Uvurkhangai_XAOCT_Negdsen_dun.pdf",
}

# A page is kept when it names one of these: ethnic group, religion, or the
# sex ratio that heads the soum population tables.
MARKERS = ("угсаа", "шашин", "шашны", "хүйсийн харьцаа", "хүйсийн харьцаагаар")
MAX_PAGES = 70


def slug(name: str) -> str:
    from common import slugify                      # noqa: PLC0415
    return slugify(name)


# ---------------------------------------------------------------------------
# --fetch: the Archive, the books, and the pages worth keeping
# ---------------------------------------------------------------------------

def captures() -> dict[str, tuple[str, str, int]]:
    """{book filename: (timestamp, original url, bytes)} -- the largest
    capture of each book the Archive holds.

    The Archive stored several of these books twice: once whole and once
    truncated at exactly 1,048,576 bytes, a download cut off at one mebibyte.
    A truncated PDF opens as zero pages and reports nothing, so the capture
    to ask for is the biggest one, not the newest.
    """
    text = http_get(CDX, cache=False, retries=3, timeout=120)
    assert isinstance(text, str)
    best: dict[str, tuple[str, str, int]] = {}
    rows = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3 or not parts[2].isdigit():
            continue
        rows += 1
        timestamp, original, size = parts[0], parts[1], int(parts[2])
        for file in BOOKS.values():
            if f"url={file}" not in original:
                continue
            if file not in best or size > best[file][2]:
                best[file] = (timestamp, original, size)
    log(f"  CDX: {rows} archived PDF captures, {len(best)} of the {len(BOOKS)} books")
    return best


def keep_pages(blob: bytes) -> list[int]:
    """The 1-based pages naming ethnic group, religion or the sex ratio."""
    import io                                        # noqa: PLC0415
    from pypdf import PdfReader                      # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    out = []
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").lower()
        if any(marker in text for marker in MARKERS):
            out.append(number)
    return out[:MAX_PAGES]


def laid_out_pages(blob: bytes, numbers: list[int], tolerance: float = 2.0) -> str:
    """Those pages with their rows rebuilt from the glyphs' coordinates."""
    import io                                        # noqa: PLC0415

    import pdfplumber                                # noqa: PLC0415

    out: list[str] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for number in numbers:
            if not 1 <= number <= len(pdf.pages):
                continue
            page = pdf.pages[number - 1]
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            rows: list[tuple[float, list[tuple[float, float, str]]]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(word["top"], 1)
                cell = (word["x0"], word["x1"], word["text"])
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append(cell)
                else:
                    rows.append((top, [cell]))
            out.append(f"=== page {number} ===")
            for _top, cells in rows:
                out.append(" ".join(t for _x0, _x1, t in sorted(cells)))
            page.close()
    return "\n".join(out)


def fetch(only: list[str] | None = None) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    best = captures()
    missing = [n for n, f in BOOKS.items() if f not in best]
    if missing:
        log(f"  ! no archived capture for {missing}")
    for aimag, file in BOOKS.items():
        if only and aimag not in only:
            continue
        if file not in best:
            continue
        timestamp, original, size = best[file]
        url = REPLAY.format(timestamp=timestamp, original=original)
        log(f"  {aimag}: {file} {size:,} bytes, captured {timestamp}")
        try:
            blob = http_get(url, binary=True, cache=False, retries=3, timeout=600,
                            headers={"Accept": "application/pdf,*/*"})
        except Exception as exc:                     # noqa: BLE001
            log(f"    ! unreachable: {type(exc).__name__}: {exc}")
            continue
        assert isinstance(blob, bytes)
        numbers = keep_pages(blob)
        text = laid_out_pages(blob, numbers)
        dest = RAW_DIR / f"{slug(aimag)}.txt"
        header = (f"# {aimag}\n# {url}\n# archived {timestamp}, {size} bytes, "
                  f"pages kept: {numbers}\n")
        dest.write_text(header + text + "\n", encoding="utf-8")
        log(f"    {len(numbers)} pages kept, {len(text):,} chars -> {dest.name}")
    return 0


# ---------------------------------------------------------------------------
# --probe: reconnaissance. Writes nothing.
# ---------------------------------------------------------------------------

def get(url: str, *, limit: int = BYTES, find: str | None = None,
        terms: list[str] | None = None, context: int = 200,
        headers: dict[str, str] | None = None) -> str | None:
    try:
        body = http_get(url, cache=False, retries=1, timeout=60, aia=True, headers=headers)
    except Exception as exc:                # noqa: BLE001 - the probe's product is the reason
        log(f"  {url}\n    unreachable: {type(exc).__name__}: {exc}")
        return None
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    log(f"  {url}\n    {len(text):,} chars")
    if find:
        hits = sorted({m.group(0) for m in re.finditer(find, text)})
        log(f"    {len(hits)} distinct match(es) for {find!r}")
        for hit in hits[:200]:
            log(f"      {hit}")
    elif terms:
        for term in terms:
            seen = 0
            at = text.find(term)
            while at >= 0 and seen < 12:
                lo, hi = max(0, at - context), min(len(text), at + len(term) + context)
                log(f"    [{term} @{at}] ...{text[lo:hi]}...")
                seen += 1
                at = text.find(term, at + 1)
            if not seen:
                log(f"    [{term}] not present")
    else:
        log("    " + text[:limit].replace("\n", "\n    "))
    return text


def post(url: str, payload: dict[str, Any], *, limit: int = BYTES) -> str | None:
    from probe_tls import verified_opener          # noqa: PLC0415
    blob = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=blob, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": AGENT,
    })
    opener = verified_opener(urllib.parse.urlsplit(url).hostname or "")
    try:
        with opener.open(req, timeout=120) as resp:
            text = resp.read().decode("utf-8", "replace")
            log(f"  POST {url} {payload}\n    {resp.status} {len(text):,} chars")
    except Exception as exc:                       # noqa: BLE001
        log(f"  POST {url} {payload}\n    failed: {type(exc).__name__}: {exc}")
        return None
    log("    " + text[:limit].replace("\n", "\n    "))
    return text


def probe(args: argparse.Namespace) -> int:
    for url in args.get or []:
        get(url, limit=args.bytes, find=args.find,
            terms=args.terms.split(",") if args.terms else None,
            context=args.context)
    payload = dict(kv.split("=", 1) for kv in (args.field or []))
    for url in args.post or []:
        post(url, payload, limit=args.bytes)
    return 0


def run() -> int:
    raise SystemExit("mongolia: the reader is not written yet; run with --fetch")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="read the books from the Archive into data/raw/mongolia")
    ap.add_argument("--only", help="comma-separated aimags, for --fetch")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--get", action="append")
    ap.add_argument("--post", action="append")
    ap.add_argument("--field", action="append", help="NAME=VALUE for a POST body")
    ap.add_argument("--find", help="print the distinct matches of this regex instead of the body")
    ap.add_argument("--terms", help="comma-separated words to print the surroundings of")
    ap.add_argument("--context", type=int, default=200)
    ap.add_argument("--bytes", type=int, default=BYTES)
    args = ap.parse_args()
    if args.probe:
        return probe(args)
    if args.fetch:
        return fetch([a.strip() for a in args.only.split(",")] if args.only else None)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
