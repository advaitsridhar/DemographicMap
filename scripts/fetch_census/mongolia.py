#!/usr/bin/env python3
"""Mongolia: ethnicity and religion by aimag and soum, from the 2020 census.

Mongolia's 2020 Population and Housing Census asked ethnic group (*үндэс
угсаа*, 33 groups where 2010 had 29) of every Mongolian citizen, and asked
religion -- "Та шашин шүтдэг үү, шүтдэг бол ямар шашин шүтдэг вэ?" -- of a
ten per cent sample of the population aged 15 and over. It did not ask
language, which ``NOT_COLLECTED_POLICY`` declares.

Two publications are read, both from the National Statistics Office:

* the **English national report**, whose Appendix Table 3.6 is the
  percentage distribution of each aimag's population by ethnicity -- the one
  table that gives an ethnic composition for all 22 first-level units at
  once, in the office's own English spellings;
* the **22 aimag results books**, "<aimag> аймгийн хүн ам, орон сууцны 2020
  оны улсын тооллогын НЭГДСЭН ДҮН", each written by that aimag's own
  statistics department. Chapter three of every one carries the religion of
  the population aged 15 and over, and most of them also print a table of
  ethnic group by **soum**, which is the only figure the census published
  below the aimag on any of the three fields.

**Where they are.** They were served from ``1212.mn`` by an ASP.NET handler,
``BookLibraryDownload.ashx?url=<file>&ln=Mn``. That site is gone: ``nso.mn``
and ``www.1212.mn`` now serve one Next.js application, the handler answers
200 with an empty body over plain HTTP, ``www2.1212.mn`` answers HTTPS with
a certificate that expired, ``web.nso.mn`` refuses the connection, and
``opendata.1212.mn`` -- the statistical database's API, which the CRAN
package NSO1212 is written against -- no longer resolves at all. They are
read from the Internet Archive, the way ``romania.py`` reads Romania's 2011
census: one CDX query lists every archived capture of every book, and the
largest capture of each is fetched, because the Archive truncated several of
them at exactly one mebibyte and a truncated PDF has no pages at all.

``--fetch`` does that, extracts the pages naming ethnic group, religion or
the sex ratio, and writes them to ``data/raw/mongolia/``; the adapter reads
those text files, so a build without network still runs and what was read is
committed beside the code that read it. Rows are rebuilt from the glyphs'
coordinates (as ``probe_pdf --layout`` does) because these books set their
tables in two columns and a reader that takes pypdf's string order gets a
page of figures followed by a page of labels.

**The soum tables come in three shapes**, because 22 statistics departments
wrote 22 books. Some print each soum's own composition in percentages, some
print counts, and some print the *distribution of each ethnic group across
the soums* -- a table whose columns add to 100 rather than its rows. The
third is still a composition once it is weighted by the aimag's own group
shares, and the reader says which shape it found and checks all three: rows
to 100, counts to their own total, columns to 100. An aimag whose book
prints no such table gets no soum rows and the log says so.

**Joining a soum to a shape.** The boundary file romanises Mongolian in a
scheme of its own -- "Adaacag", "Aldarxaan", "Altanco'gc", and "Herlen" in
one aimag against "Xerlen" in another -- so names are compared on a folded
key that both sides reduce to: apostrophes, hyphens and spaces dropped, kh
and h read as x, ts and ch as c, sh as s, and y as i. Doubled vowels are
kept, because Цагааннуур and Цагаан-Уур are two soums of Khuvsgul that
collapsing them would make one. Three soums are called Altai, but each is
in a different aimag and
every match is made inside one aimag, so none of them is ambiguous. A soum
whose folded name matches no shape in its aimag is logged and left
unwritten.

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

from ._shared import NOT_AVAILABLE, PROCESSED, RAW, gap, log, record, write_json
from common import http_get  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = "mongolia.json"
YEAR = 2020
RAW_DIR = RAW / "mongolia"
BYTES = 3000
AGENT = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"

NSO = "National Statistics Office of Mongolia"
CENSUS = f"2020 Population and Housing Census of Mongolia, {NSO}"
REPORT_SOURCE = (f"{CENSUS}, National Report (English edition), Appendix Table 3.6: "
                 "percentage distribution of population by ethnicity, and aimags and "
                 "the capital, 2020")
BOOK_SOURCE = (f"{CENSUS}, the aimag's own results book "
               "(“Хүн ам, орон сууцны 2020 оны улсын тооллогын нэгдсэн дүн”), "
               "chapter three")
LICENCE = f"Official statistics of the {NSO}, cited as published"
ARCHIVE = "https://web.archive.org/web/*/1212.mn/BookLibraryDownload.ashx*"

CDX = ("http://web.archive.org/cdx/search/cdx?url=1212.mn&matchType=domain"
       "&output=text&limit=8000&fl=timestamp,original,length"
       "&filter=mimetype:application/pdf"
       "&filter=original:.*(XAOCT|url=Khovd[.]pdf|url=dundgovi[.]pdf|url=Dundgovi[.]pdf"
       "|url=Khentii[.]pdf|url=18[._]+Khentii[.]pdf"
       "|url=Census2020_Main_report_Eng[.]pdf).*")
REPLAY = "https://web.archive.org/web/{timestamp}id_/{original}"

# The 22 first-level units as site/data/admin1/MNG.json names them, the
# office's own English spelling in the national report, and the file or files
# that aimag's book was served under. Nineteen share the XAOCT stem; Dundgovi,
# Khentii and Khovd published theirs under a plain name, matched on
# "url=<name>.pdf" so that a yearbook called Khovd_2019.pdf is not mistaken
# for the census book. Where several names are given they are tried in turn:
# Khentii.pdf turns out to be that aimag's *2010* book, typeset in a legacy
# Mongolian codepage that extracts as Latin-1 mojibake, and it is rejected by
# the test below that a book must name 2020.
AIMAGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Arkhangai": ("Arkhangai", ("Arkhangai_XAOCT_Negdsen_dun.pdf",)),
    "Bayan-Ölgii": ("Bayan-Ulgii", ("Bayan-Ulgii_XAOCT_Negdsen_Dun.pdf",)),
    "Bayankhongor": ("Bayankhongor", ("Bayankhongor_XAOCT_Negdsen_dun.pdf",)),
    "Bulgan": ("Bulgan", ("Bulgan_XAOCT_Negdsen_dun.pdf",)),
    "Darkhan-Uul": ("Darkhan-Uul", ("Darkhan-Uul_XAOCT_Negdsen%20dun.pdf",)),
    "Dornod": ("Dornod", ("Dornod_XAOCT_Negdsen_Dun.pdf",)),
    "Dornogovi": ("Dornogovi", ("Dornogovi_XAOCT_Negdsen_Dun.pdf",)),
    "Dundgovi": ("Dundgovi", ("dundgovi.pdf", "Dundgovi.pdf")),
    "Govi-Altai": ("Govi-Altai", ("Govi-Altai_XAOCT_Negdsen%20dun.pdf",)),
    "Govisumber": ("Govisumber", ("Govisumber_XAOCT_Negdsen_dun.pdf",)),
    "Hovsgel": ("Khuvsgul", ("Khuvsgul_XAOCT_Negdsen_Dun.pdf",)),
    "Khentii": ("Khentii", ("18._Khentii.pdf", "Khentii.pdf")),
    "Khovd": ("Khovd", ("Khovd.pdf",)),
    "Orkhon": ("Orkhon", ("Orkhon_XAOCT_Negdsen_Dun.pdf",)),
    "Selenge": ("Selenge", ("Selenge_XAOCT_Negdsen_dun.pdf",)),
    "Sükhbaatar": ("Sukhbaatar", ("Sukhbaatar_XAOCT_Negdsen_dun.pdf",)),
    "Töv": ("Tuv", ("Tuv_XAOCT_Negdsen%20dun..pdf",)),
    "Ulaanbaatar": ("Ulaanbaatar", ("Ulaanbaatar_XAOCT_Negdsen_dun.pdf",)),
    "Uvs": ("Uvs", ("Uvs_XAOCT_Negdsen_Dun.pdf",)),
    "Zavkhan": ("Zavkhan", ("Zavkhan_XAOCT_Negdsen_dun.pdf",)),
    "Ömnögovi": ("Umnugovi", ("Umnugovi_XAOCT_Negdsen_Dun.pdf",)),
    "Övörkhangai": ("Uvurkhangai", ("Uvurkhangai_XAOCT_Negdsen_dun.pdf",)),
}
BY_ENGLISH = {english: name for name, (english, _files) in AIMAGS.items()}

# A page of an aimag book is kept when it names one of these: ethnic group,
# religion, or the sex ratio that heads the soum population tables.
MARKERS = ("угсаа", "шашин", "шашны", "хүйсийн харьцаа", "хүйсийн харьцаагаар")
MAX_PAGES = 70
# A book that never says this is not the 2020 census's book.
STAMP = "2020"

# The English national report, for Appendix Table 3.6.
REPORT_EN = "Census2020_Main_report_Eng.pdf"
REPORT_MARKERS = ("by ethnicity, and aimags", "continued table 3.6")
REPORT_FILE = "national-report-en.txt"

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

# The 2020 list of ethnic groups, Mongolian to the office's own English. The
# books spell several of them more than one way and a label is folded before
# it is looked up, so "Казах"/"Казак" and "Дарьганга"/"Дариганга" are one key.
ETHNIC: dict[str, str] = {
    "халх": "Khalkh", "казах": "Kazakh", "казак": "Kazakh",
    "дөрвөд": "Durvud", "буриад": "Buriad", "баяд": "Bayad",
    "дарьганга": "Dariganga", "дариганга": "Dariganga",
    "урианхай": "Uriankhai", "захчин": "Zakhchin", "дархад": "Darkhad",
    "торгууд": "Torguud", "өөлд": "Uuld", "өөлөд": "Uuld",
    "хотон": "Khoton", "мянгад": "Myangad", "барга": "Barga",
    "үзэмчин": "Uzemchin", "харчин": "Kharchin",
    "хотгойд": "Khotgoid", "хотогойд": "Khotgoid",
    "элжгэн": "Eljigen", "элжигэн": "Eljigen",
    "сартуул": "Sartuul", "тува": "Tuva", "тувва": "Tuva",
    "цаатан": "Tsaatan (Dukha)", "цаатандуха": "Tsaatan (Dukha)",
    "хамниган": "Khamnigan", "узбек": "Uzbek (Chantuu)",
    "узбекчантуу": "Uzbek (Chantuu)", "чантуу": "Uzbek (Chantuu)",
    "хошууд": "Khoshuud", "хошуд": "Khoshuud", "цахар": "Tsakhar",
    "хорчин": "Khorchin", "халимаг": "Khalimag", "сөнөд": "Sonod",
    "түмэд": "Tumed", "балба": "Balba", "уйгар": "Uyghur",
    "бусад": "Other ethnic groups",
    "бусадүндэстэн": "Other ethnic groups",
    "бусадугсаатан": "Other ethnic groups",
    "бусадүндэстэнугсаатан": "Other ethnic groups",
    "бусадүндэсугсаатан": "Other ethnic groups",
    "бусадгадаадүндэсугсаатан": "Other nationals (Mongolian citizens)",
    "бусадгадаадмонголынхарьяат": "Other nationals (Mongolian citizens)",
    "монголынхарьяат": "Other nationals (Mongolian citizens)",
}
# The aimag total column of a soum table, under any of its headings.
TOTALS = {"бүгд", "дүн", "нийт", "монголулсынхарьяатбүгд", "монголулсынхарьяат",
          "сумдүгд", "бүгддүн", "монголулсын"}
# Row labels that are not a soum.
NOT_A_SOUM = {"бүгд", "дүн", "нийт", "аймгийндүн", "аймагдүн", "хот", "хөдөө",
              "улсындүн", "дүнгээр", "нийтдүн", "бүсээр", "нийслэл", "аймаг",
              "сум", "сумбүс", "бүс"}
# Header words that are neither a group nor a total.
HEAD_WORDS = {"сум", "сумын", "сумд", "сумдаар", "сумууд", "сумыннэр", "сумнэр",
              "дүүрэг", "нэр", "бүс", "cум", "c", "аймаг", "сумбүс", "хороо"}

# The religions the census counts, and the two answers to the question before
# them. "Бусад" here is other *religions*, a residual inside the religious
# population and not a welded "other or none": the census asks whether a person
# follows a religion at all first, so no religion is its own published answer.
RELIGION: dict[str, str] = {
    "будда": "Buddhism", "буддын": "Buddhism", "буддашашин": "Buddhism",
    "буддашашинтан": "Buddhism", "буддизм": "Buddhism", "буддашашны": "Buddhism",
    "ислам": "Islam", "исламшашин": "Islam", "лалын": "Islam",
    "лалыншашин": "Islam", "исламшашны": "Islam",
    "христ": "Christianity", "христийн": "Christianity",
    "христосын": "Christianity", "христшашин": "Christianity",
    "бөө": "Shamanism", "бөөгийн": "Shamanism", "бөөшашин": "Shamanism",
    "бөөгийншашин": "Shamanism", "шаман": "Shamanism",
    "бусад": "Other religions", "бусадшашин": "Other religions",
}
NO_RELIGION = "No religion"
IRRELIGIOUS = {"шүтдэггүй", "шашингүй", "шашингүйчүүд", "шашиншүтдэггүй",
               "ямарнэгэншашиншүтдэггүй"}
RELIGIOUS = {"шүтдэг", "шашинтан", "шашиншүтдэг", "шашинтай"}

# The three blocks Appendix Table 3.6 is printed in, in the order of their
# columns. Blocks one and two carry a clean header line and the reader checks
# it; the third's header is broken across three baselines -- "Tsaatan",
# "Uzbek" and "groups /" sit above "Eljigen Sartuul Tuva Khamnigan Khoshuud
# Other" -- so the order here is the left-to-right reading of those two lines
# together, and the checks below are what test it: with this order every
# aimag's 26 shares add to 100.
BLOCKS: tuple[tuple[str, ...], ...] = (
    ("Khalkh", "Kazakh", "Durvud", "Buriad", "Bayad", "Dariganga",
     "Uriankhai", "Zakhchin"),
    ("Darkhad", "Torguud", "Uuld", "Khoton", "Myangad", "Barga",
     "Uzemchin", "Kharchin", "Khotgoid"),
    ("Eljigen", "Tsaatan (Dukha)", "Sartuul", "Tuva", "Uzbek (Chantuu)",
     "Khamnigan", "Khoshuud", "Other ethnic groups",
     "Other nationals (Mongolian citizens)"),
)
# The report's own national figures, for the checks. Table 3.2 for ethnicity;
# Tables 3.9 and 3.10 for religion, where 59.4% of the population aged 15 and
# over follow a religion and 87.1% of those are Buddhist.
NATIONAL_ETHNICITY = {"Khalkh": 83.8, "Kazakh": 3.8, "Durvud": 2.6,
                      "Bayad": 2.0, "Buriad": 1.4}
NATIONAL_RELIGIOUS = 59.4
NATIONAL_RELIGION = {"Buddhism": 87.1, "Islam": 5.4, "Shamanism": 4.2,
                     "Christianity": 2.2, "Other religions": 1.1}

# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "ie", "ё": "io",
    "ж": "j", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "ө": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ү": "u", "ф": "f", "х": "x", "ц": "c", "ч": "c", "ш": "s",
    "щ": "s", "ъ": "", "ы": "i", "ь": "i", "э": "e", "ю": "iu", "я": "ia",
}


def fold(text: str) -> str:
    """A name reduced to what two romanisations of it agree on.

    The boundary file's scheme and the books' Cyrillic disagree about
    apostrophes (Өндөр is "O'ndor" but Бор-Өндөр is "Bor-Ondor"), about x
    against h (Хэрлэн is "Herlen" in Dornod and "Xerlen" in Khentii), about c
    against ts (Цагаан is "Cagaan" but Сайнцагаан is "Saintsagaan") and about
    hyphen against space ("Xalx gol", "Zamyn U'ud"). Reducing both sides to
    one alphabet settles all four. Doubled letters are *not* collapsed:
    Khuvsgul has both Цагааннуур and Цагаан-Уур, and collapsing would make
    them one name and the join a guess.
    """
    out = []
    for char in text.lower().strip():
        if char in CYRILLIC:
            out.append(CYRILLIC[char])
        elif char.isalnum():
            out.append(char)
    latin = "".join(out)
    for old, new in (("kh", "x"), ("ts", "c"), ("ch", "c"), ("sh", "s"),
                     ("h", "x"), ("y", "i"), ("q", "k"), ("w", "v")):
        latin = latin.replace(old, new)
    return latin


SOUM_WORDS = re.compile(r"(?:^|\s)(сум|сумын|сумд|дүүрэг|дүүргийн|тосгон|баг|"
                        r"хороо)(?=\s|$)", re.IGNORECASE)


def soum_key(label: str) -> str:
    return fold(SOUM_WORDS.sub(" ", label))


def group_key(label: str) -> str:
    return re.sub(r"[^а-яөүёa-z]", "", label.lower())


# ---------------------------------------------------------------------------
# --fetch: the Archive, the books, and the pages worth keeping
# ---------------------------------------------------------------------------

def raw_name(aimag: str) -> str:
    """The raw file's name: the Archive's own stem for that aimag's book,
    lower-cased. Deliberately not a slug of the Mongolian name -- the boundary
    file spells four aimags with ö and ü, and a raw file called
    ``bayan-ölgii.txt`` is a name not every checkout can hold."""
    stem = AIMAGS[aimag][1][0].split("_XAOCT")[0]
    return re.sub(r"^\d+[._]+", "", stem).removesuffix(".pdf").lower()


def captures() -> dict[str, list[tuple[str, str, int]]]:
    """{filename: [(timestamp, original url, bytes), ...]}, largest first.

    The Archive stored several of these books twice: once whole and once
    truncated at exactly 1,048,576 bytes, a download cut off at one mebibyte.
    A truncated PDF opens as zero pages and reports nothing, so the capture to
    ask for is the biggest one, not the newest -- and when the biggest is
    itself half-written, or the Archive answers 503 for it, the next one down
    is tried rather than the book being given up on.
    """
    text = http_get(CDX, cache=False, retries=3, timeout=120)
    assert isinstance(text, str)
    wanted = {REPORT_EN, *[f for _en, files in AIMAGS.values() for f in files]}
    found: dict[str, list[tuple[str, str, int]]] = {}
    rows = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3 or not parts[2].isdigit():
            continue
        rows += 1
        timestamp, original, size = parts[0], parts[1], int(parts[2])
        for file in wanted:
            if f"url={file}" in original:
                found.setdefault(file, []).append((timestamp, original, size))
    for rowset in found.values():
        rowset.sort(key=lambda r: -r[2])
    log(f"  CDX: {rows} archived PDF captures, {len(found)} of the "
        f"{len(wanted)} files wanted")
    return found


def keep_pages(blob: bytes, markers: tuple[str, ...]) -> tuple[list[int], bool]:
    """The 1-based pages naming one of the markers, and whether the document
    names 2020 anywhere."""
    import io                                        # noqa: PLC0415
    from pypdf import PdfReader                      # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    out, stamped = [], False
    for number, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").lower()
        stamped = stamped or STAMP in text
        if any(marker in text for marker in markers):
            out.append(number)
    return out[:MAX_PAGES], stamped


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
            for _top, cells_ in rows:
                # Each word carries where it sits, because "46 192 37 611" is
                # two numbers or four and only the gaps say which: these books
                # write a thousands separator as a space, and the space inside
                # a number is a couple of points where the gap between two
                # columns is ten. probe_pdf --boxes prints the same thing for
                # the same reason.
                out.append(" ".join(f"{t}[{x0:.0f}-{x1:.0f}]"
                                    for x0, x1, t in sorted(cells_)))
            page.close()
    return "\n".join(out)


def fetch(only: list[str] | None = None) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    found = captures()
    wanted: list[tuple[str, Path, tuple[str, ...], tuple[str, ...]]] = [
        ("National report (English)", RAW_DIR / REPORT_FILE, (REPORT_EN,),
         REPORT_MARKERS),
    ]
    wanted += [(name, RAW_DIR / f"{raw_name(name)}.txt", files, MARKERS)
               for name, (_en, files) in AIMAGS.items()]
    wrote = 0
    for name, dest, files, markers in wanted:
        if only and name not in only:
            continue
        if dest.exists() and dest.stat().st_size > 2000 and not only:
            log(f"  {name}: {dest.name} already read")
            wrote += 1
            continue
        if read_one(name, dest, files, markers, found):
            wrote += 1
    log(f"  {wrote} of {len(wanted)} files in {RAW_DIR}")
    return 0


def read_one(name: str, dest: Path, files: tuple[str, ...],
             markers: tuple[str, ...],
             found: dict[str, list[tuple[str, str, int]]]) -> bool:
    for file in files:
        for timestamp, original, size in found.get(file, [])[:6]:
            url = REPLAY.format(timestamp=timestamp, original=original)
            log(f"  {name}: {file} {size:,} bytes, captured {timestamp}")
            try:
                blob = http_get(url, binary=True, cache=False, retries=4, timeout=900,
                                headers={"Accept": "application/pdf,*/*"})
                assert isinstance(blob, bytes)
                numbers, stamped = keep_pages(blob, markers)
                if not numbers:
                    log("    ! no page of this capture names what is wanted")
                    continue
                if not stamped:
                    log("    ! this capture never names 2020; not the 2020 census")
                    continue
                text = laid_out_pages(blob, numbers)
            except Exception as exc:                 # noqa: BLE001
                log(f"    ! {type(exc).__name__}: {exc}")
                continue
            header = (f"# {name}\n# {url}\n# archived {timestamp}, {size} bytes, "
                      f"pages kept: {numbers}\n")
            dest.write_text(header + text + "\n", encoding="utf-8")
            log(f"    {len(numbers)} pages kept, {len(text):,} chars -> {dest.name}")
            return True
    log(f"  ! {name}: no capture of {list(files)} could be read")
    return False


# ---------------------------------------------------------------------------
# Reading a row out of the laid-out text
# ---------------------------------------------------------------------------

BOXED = re.compile(r"^(?P<text>.*)\[(?P<x0>-?\d+)-(?P<x1>-?\d+)\]$")
NUMBER = re.compile(r"^-{1,2}$|^\d+(?:[.,]\d+)?%?$")


def tokens_of(line: str) -> list[tuple[str, float, float]]:
    """(text, left, right) for every word of a row as --fetch wrote it."""
    out: list[tuple[str, float, float]] = []
    for word in line.split():
        match = BOXED.match(word)
        if match and match.group("text"):
            out.append((match.group("text"), float(match.group("x0")),
                        float(match.group("x1"))))
        else:
            out.append((word, -1.0, -1.0))
    return out


def figures(run: list[tuple[str, float, float]],
            width: int | None) -> list[float | None] | None:
    """A run of numeric words read as numbers.

    These books write a thousands separator as a space, so "46 192 37 611" is
    two numbers or four and nothing in the text says which. The gaps do: the
    space inside a number is a couple of points wide and the gap between two
    columns is ten or more. When the caller knows how many columns the table
    has, the widest ``width - 1`` gaps are taken as the column boundaries and
    everything else is joined -- and the row is refused unless that split is
    clean, the narrowest boundary gap strictly wider than the widest gap
    inside a number. Without a width, every word is its own number, which is
    right for a table of percentages and is all the callers that pass none
    ever read.
    """
    if width is None or len(run) <= width:
        return [None if t in {"-", "--"} else float(t.rstrip("%").replace(",", "."))
                for t, _a, _b in run]
    if any(a < 0 for _t, a, _b in run) or any(
            "." in t or "," in t or t in {"-", "--"} for t, _a, _b in run):
        return None
    gaps = sorted(((run[i + 1][1] - run[i][2], i) for i in range(len(run) - 1)),
                  reverse=True)
    boundaries = gaps[:width - 1]
    if len(boundaries) < width - 1 or (len(gaps) > width - 1
                                       and boundaries[-1][0] <= gaps[width - 1][0]):
        return None
    cut = {i for _gap, i in boundaries}
    values: list[float | None] = []
    digits = ""
    for i, (text, _a, _b) in enumerate(run):
        digits += text
        if i in cut or i == len(run) - 1:
            values.append(float(digits))
            digits = ""
    return values if len(values) == width else None


def rows_in(line: str, width: int | None = None
            ) -> list[tuple[str, list[float | None]]]:
    """Every (label, figures) pair on one row of the page.

    A row of these books is often two rows: the pages set their tables in two
    columns, so "Тариат 5.2 5.3 0.2 1.8 1.1 2.6 Өөлд 100.0 8.4 2.0 1.1 19.2"
    is one line of one table beside one line of another. Each run of numeric
    words is returned with the words immediately before it, and the caller
    keeps the runs of the width it is looking for.
    """
    out: list[tuple[str, list[float | None]]] = []
    words = tokens_of(line)
    i = 0
    while i < len(words):
        if NUMBER.match(words[i][0]):
            i += 1
            continue
        start = i
        while i < len(words) and not NUMBER.match(words[i][0]):
            i += 1
        label = " ".join(t for t, _a, _b in words[start:i]).strip(" .:*")
        run_start = i
        while i < len(words) and NUMBER.match(words[i][0]):
            i += 1
        if not label or i == run_start:
            continue
        values = figures(words[run_start:i], width)
        if values:
            out.append((label, values))
    return out


def one_row(line: str) -> tuple[str, list[float | None]] | None:
    rows = rows_in(line)
    return rows[0] if rows else None


def pages(text: str) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.startswith("=== page "):
            out.append([])
        elif not line.startswith("#"):
            out[-1].append(line)
    return [p for p in out if p]


# ---------------------------------------------------------------------------
# Appendix Table 3.6 of the English national report
# ---------------------------------------------------------------------------

MAIN_TABLE = re.compile(r"(?i)(?:tables?|continued\s+table)\s+3\.6\b(?!\.?\s*a\b)")
TRANSPOSE = re.compile(r"(?i)(?:tables?|continued\s+table)\s+3\.6\.?\s*a\b")


def read_report(text: str) -> dict[str, dict[str, float]]:
    """{aimag: {group: percent of the aimag's Mongolian citizens}}."""
    lines = text.splitlines()
    shares: dict[str, dict[str, float]] = {}
    seen = 0
    wanted: tuple[str, ...] | None = None
    for index, line in enumerate(lines):
        if TRANSPOSE.search(line):
            wanted = None
            continue
        if MAIN_TABLE.search(line):
            seen += 1
            wanted = BLOCKS[seen - 1] if seen <= len(BLOCKS) else None
            if wanted and seen <= 2:
                check_block_header(lines, index, wanted)
            continue
        if wanted is None:
            continue
        for label, values in rows_in(line):
            name = BY_ENGLISH.get(label.strip())
            if name is None:
                continue
            # Block one prints a leading "Mongolian citizens-Total" of 100.0.
            if len(values) == len(wanted) + 1 and values[0] == 100.0:
                values = values[1:]
            if len(values) != len(wanted):
                raise SystemExit(
                    f"mongolia: Appendix Table 3.6 block {seen} gives {label!r} "
                    f"{len(values)} figures against {len(wanted)} columns: {line!r}")
            into = shares.setdefault(name, {})
            for group, value in zip(wanted, values):
                if value:
                    into[group] = into.get(group, 0.0) + value
    if seen < len(BLOCKS):
        raise SystemExit(f"mongolia: only {seen} block(s) of Appendix Table 3.6 were "
                         "found in the national report")
    return shares


def check_block_header(lines: list[str], index: int, wanted: tuple[str, ...]) -> None:
    """The names printed over a block's columns must be the names read into it."""
    for line in lines[index:index + 8]:
        hit = [t for t, _a, _b in tokens_of(line) if t in wanted]
        if len(hit) == len(wanted):
            if hit == list(wanted):
                return
            raise SystemExit(f"mongolia: Appendix Table 3.6 heads its columns {hit} "
                             f"where this reader expects {list(wanted)}")
    raise SystemExit(f"mongolia: no header line at {lines[index]!r} names the columns "
                     f"{list(wanted)}")


def check_report(shares: dict[str, dict[str, float]]) -> None:
    missing = sorted(set(AIMAGS) - set(shares))
    if missing:
        raise SystemExit(f"mongolia: Appendix Table 3.6 gives no row for {missing}")
    worst = ("", 0.0)
    for name, groups in sorted(shares.items()):
        total = sum(groups.values())
        if abs(total - 100.0) > abs(worst[1] - 100.0):
            worst = (name, total)
        if abs(total - 100.0) > 1.0:
            raise SystemExit(f"mongolia: {name}'s 26 ethnic shares add to {total:.1f}, "
                             "not 100")
    for group, national in NATIONAL_ETHNICITY.items():
        largest = max(groups.get(group, 0.0) for groups in shares.values())
        if largest < national:
            raise SystemExit(f"mongolia: no aimag reaches the national {group} share "
                             f"of {national}% (largest {largest}%)")
    log(f"  Appendix Table 3.6: 22 aimags over 26 ethnic groups, each adding to 100 "
        f"(furthest {worst[0]} at {worst[1]:.1f})")


# ---------------------------------------------------------------------------
# An aimag's book: religion, and ethnic group by soum
# ---------------------------------------------------------------------------

def year_value(values: list[float | None]) -> float | None:
    """The 2020 total of a row printed for 2010 and 2020, each with a total and
    the two sexes; a book that prints 2020 alone gives three figures or one."""
    if len(values) >= 6:
        return values[3]
    if len(values) in (1, 2, 3):
        return values[0]
    return None


def read_religion(book: list[list[str]]) -> dict[str, float] | None:
    """{group: percent of the population aged 15 and over}.

    Two tables make one composition: the share who follow a religion at all,
    and the breakdown of those who do.
    """
    lines = [line for page in book for line in page]
    status = pick_status(lines)
    kinds = pick_kinds(lines)
    if not status or not kinds:
        return None
    religious, irreligious = status
    out = {NO_RELIGION: irreligious}
    for group, share in kinds.items():
        out[group] = religious * share / 100.0
    return out


def pick_status(lines: list[str]) -> tuple[float, float] | None:
    religious = irreligious = None
    for line in lines:
        for label, values in rows_in(line):
            key, value = group_key(label), year_value(values)
            if value is None:
                continue
            if key in IRRELIGIOUS and irreligious is None:
                irreligious = value
            elif key in RELIGIOUS and religious is None:
                religious = value
        if religious is not None and irreligious is not None:
            break
    if religious is None or irreligious is None:
        return None
    if abs(religious + irreligious - 100.0) > 1.0:
        return None
    return religious, irreligious


def pick_kinds(lines: list[str]) -> dict[str, float] | None:
    """The breakdown of the religious population, however the book lays it out:
    the religions down the rows, or across the columns with a total beneath."""
    rows: dict[str, float] = {}
    for line in lines:
        for label, values in rows_in(line):
            group, value = RELIGION.get(group_key(label)), year_value(values)
            if group and value is not None and group not in rows:
                rows[group] = value
    if len(rows) >= 3 and abs(sum(rows.values()) - 100.0) <= 1.5:
        return rows
    return pick_kinds_across(lines)


def pick_kinds_across(lines: list[str]) -> dict[str, float] | None:
    for i, line in enumerate(lines):
        header = [RELIGION[group_key(t)] for t, _a, _b in tokens_of(line)
                  if group_key(t) in RELIGION]
        if len(header) < 3 or len(header) != len(set(header)):
            continue
        totals: list[list[float | None]] = []
        for follow in lines[i + 1:i + 40]:
            for label, values in rows_in(follow):
                if group_key(label) in {"бүгд", "дүн", "нийт"} and len(values) in (
                        len(header), len(header) + 1):
                    totals.append(values[-len(header):])
        for values in reversed(totals):
            numbers = [v or 0.0 for v in values]
            if abs(sum(numbers) - 100.0) <= 1.5:
                return dict(zip(header, numbers))
    return None


def header_groups(line: str) -> tuple[list[str], bool] | None:
    """The ethnic groups a soum table heads its columns with, and whether it
    opens with the unit's own total."""
    tokens = [t for t, _a, _b in tokens_of(line) if t]
    if not tokens or any(re.search(r"\d", t) for t in tokens):
        return None
    groups: list[str] = []
    has_total = False
    for token in tokens:
        key = group_key(token)
        if key in ETHNIC:
            groups.append(ETHNIC[key])
        elif key in TOTALS and not groups:
            has_total = True
        elif key in HEAD_WORDS:
            continue
        else:
            return None
    if len(groups) < 3 or len(groups) != len(set(groups)):
        return None
    return groups, has_total


def block_rows(lines: list[str], width: int) -> tuple[dict[str, list[float | None]],
                                                      list[float | None] | None]:
    rows: dict[str, list[float | None]] = {}
    total: list[float | None] | None = None
    misses = 0
    for line in lines:
        hits = [r for r in rows_in(line, width) if len(r[1]) == width]
        if not hits:
            misses += 1
            if misses > 10 and rows:
                break
            continue
        misses = 0
        for label, values in hits:
            if group_key(label) in NOT_A_SOUM:
                if total is None:
                    total = values
                continue
            if len(label) > 34 or any(ch.isdigit() for ch in label):
                continue
            rows.setdefault(label, values)
    return rows, total


def classify(block: dict[str, list[float | None]], total: list[float | None] | None,
             has_total: bool) -> str | None:
    """"row shares" | "counts" | "column shares", or None when no arithmetic fits."""
    values = [[v or 0.0 for v in row] for row in block.values()]
    if not values:
        return None
    rest = [row[1:] if has_total else row for row in values]
    if has_total:
        if all(abs(row[0] - 100.0) < 0.05 for row in values) and all(
                abs(sum(r) - 100.0) <= 2.0 for r in rest):
            return "row shares"
        if (total and all(abs((t or 0.0) - 100.0) < 0.05 for t in total)
                and all(abs(row[0] - 100.0) > 0.05 for row in values)):
            columns = [sum(row[i] for row in values) for i in range(len(values[0]))]
            if all(abs(c - 100.0) <= 3.0 for c in columns if c):
                return "column shares"
    integral = all(float(v).is_integer() for row in values for v in row)
    if integral and has_total and all(
            abs(row[0] - sum(row[1:])) <= max(2.0, 0.02 * row[0])
            for row in values if row[0]):
        return "counts"
    if not has_total:
        if all(abs(sum(r) - 100.0) <= 2.0 for r in rest):
            return "row shares"
        if integral:
            return "counts"
    return None


def read_soums(book: list[list[str]]) -> tuple[dict[str, dict[str, float]], str] | None:
    """{soum label: {group: value}} and the shape the table came in.

    A block is a header line naming three or more ethnic groups followed by
    rows of a label and exactly as many figures. Blocks of the same shape are
    merged, because most books print the table in two or three column blocks
    under a "continued" heading.
    """
    merged: dict[str, dict[str, float]] = {}
    shape = ""
    for page in book:
        for i, line in enumerate(page):
            head = header_groups(line)
            if not head:
                continue
            groups, has_total = head
            block, total = block_rows(page[i + 1:], len(groups) + (1 if has_total else 0))
            if len(block) < 2:
                continue
            kind = classify(block, total, has_total)
            if not kind or (shape and kind != shape):
                continue
            shape = kind
            for label, values in block.items():
                figures = values[1:] if has_total else values
                into = merged.setdefault(label, {})
                for group, value in zip(groups, figures):
                    if value:
                        into[group] = into.get(group, 0.0) + value
    return (merged, shape) if merged else None


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def shapes() -> dict[str, dict[str, str]]:
    """{aimag: {folded soum name: the boundary file's spelling}}."""
    from common import read_json                     # noqa: PLC0415
    site = Path(__file__).resolve().parent.parent.parent / "site" / "data"
    first = read_json(site / "admin1" / "MNG.json", []) or []
    second = read_json(site / "admin2" / "MNG.json", []) or []
    by_id = {row["id"]: row["name"] for row in first}
    out: dict[str, dict[str, str]] = {name: {} for name in by_id.values()}
    clashes: list[str] = []
    for row in second:
        aimag = by_id.get(row["parent"])
        if aimag is None:
            continue
        folded = soum_key(row["name"])
        if folded in out[aimag]:
            clashes.append(f"{aimag} / {row['name']} and {out[aimag][folded]}")
            continue
        out[aimag][folded] = row["name"]
    if clashes:
        log(f"  ! two shapes fold to one key and neither can be matched: {clashes}")
    return out


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

MIN_SHARE = 0.05
RESIDUAL = "Other ethnic groups"


def composition(values: dict[str, float], residual: str = RESIDUAL
                ) -> list[dict[str, Any]]:
    total = sum(v for v in values.values() if v > 0)
    if total <= 0:
        return []
    keep: dict[str, float] = {}
    for group, value in values.items():
        if value <= 0:
            continue
        share = 100.0 * value / total
        target = residual if share < MIN_SHARE else group
        keep[target] = keep.get(target, 0.0) + share
    rows = sorted(keep.items(), key=lambda kv: (-kv[1], kv[0]))
    shares = whole_hundred([v for _g, v in rows])
    return [{"group": g, "pct": p} for (g, _v), p in zip(rows, shares) if p > 0]


def whole_hundred(values: list[float]) -> list[float]:
    """Shares re-rounded to one decimal by largest remainder, so they add to
    exactly 100.0."""
    scaled = [v * 10 for v in values]
    floors = [int(s) for s in scaled]
    short = round(1000 - sum(floors))
    order = sorted(range(len(scaled)), key=lambda i: scaled[i] - floors[i], reverse=True)
    for i in order[:short]:
        floors[i] += 1
    return [f / 10 for f in floors]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

ETHNICITY_NOTE_AIMAG = (
    "Shares of the aimag's Mongolian citizens by ethnic group as the 2020 census "
    "published them, read from Appendix Table 3.6 of the National Statistics Office's "
    "English national report. The base is citizens, so the foreign nationals the "
    "census counted separately are outside it, and a group under 0.05% of the aimag "
    "is inside “Other ethnic groups”.")
RELIGION_NOTE = (
    "Shares of the population aged 15 and over, read from chapter three of this "
    "aimag's own 2020 census results book: the published share who follow a religion, "
    "split by the published breakdown of those who do. The census asked religion of a "
    "ten per cent sample of that age group, so these are sample estimates, and "
    "“No religion” is an answer people gave rather than a residual.")
SOUM_NOTES = {
    "row shares": (
        "Shares of the soum's Mongolian citizens by ethnic group as the 2020 census "
        "published them, from the table of ethnic group by soum in this aimag's own "
        "census results book."),
    "counts": (
        "Shares of the soum's Mongolian citizens by ethnic group, from the counts the "
        "2020 census published for this soum in the table of ethnic group by soum in "
        "this aimag's own census results book."),
    "column shares": (
        "Shares of the soum's Mongolian citizens by ethnic group in 2020, worked out "
        "from two tables of this aimag's own census results book: the published share "
        "of each ethnic group that lives in this soum, weighted by that group's share "
        "of the aimag. The book prints the soum breakdown down the column rather than "
        "across the row, so this composition is derived and not transcribed."),
}
SOUM_RELIGION_GAP = (
    "The 2020 census asked religion of a ten per cent sample of the population aged 15 "
    "and over and published the answer for the aimag; this aimag's results book prints "
    "no religion table by soum.")
NO_BOOK_GAP = (
    "The 2020 census published religion for this aimag in the aimag's own results "
    "book. No capture of that book could be read from the Internet Archive, and "
    "1212.mn, which served it, no longer answers.")
NO_TABLE_GAP = (
    "This aimag's 2020 census results book was read, and no table of religious "
    "adherence in it could be resolved into a composition.")


def build(report: dict[str, dict[str, float]],
          religion: dict[str, dict[str, float]],
          soums: dict[str, tuple[dict[str, dict[str, float]], str]],
          gaps: dict[str, str]) -> list[dict[str, Any]]:
    from common import slugify                       # noqa: PLC0415
    geometry = shapes()
    out: list[dict[str, Any]] = []
    unmatched: list[str] = []
    placed = 0
    for aimag in AIMAGS:
        aid = f"MNG-{slugify(aimag)}"
        ethnicity = composition(report.get(aimag, {}))
        faith = religion.get(aimag)
        fields: dict[str, Any] = {
            "country": "MNG",
            "ethnicity": ethnicity or None,
            "ethnicity_year": YEAR if ethnicity else None,
            "ethnicity_note": ETHNICITY_NOTE_AIMAG if ethnicity else None,
            "sources": [{"field": "ethnicity", "name": REPORT_SOURCE,
                         "url": ARCHIVE, "license": LICENCE}],
        }
        if faith:
            fields["religion"] = composition(faith, "Other religions")
            fields["religion_year"] = YEAR
            fields["religion_note"] = RELIGION_NOTE
            fields["sources"].append({"field": "religion", "name": BOOK_SOURCE,
                                      "url": ARCHIVE, "license": LICENCE})
        else:
            fields["religion"] = gap(NOT_AVAILABLE, gaps.get(aimag, NO_TABLE_GAP))
        out.append(record(aid, aimag, level="admin1", parent="MNG", **fields))

        table = soums.get(aimag)
        if not table:
            continue
        rows_by_soum, kind = table
        weights = report.get(aimag, {}) if kind == "column shares" else None
        for label, values in sorted(rows_by_soum.items()):
            name = geometry.get(aimag, {}).get(soum_key(label))
            if not name:
                unmatched.append(f"{aimag} / {label}")
                continue
            if weights is not None:
                values = {g: v * weights.get(g, 0.0) for g, v in values.items()}
            rows = composition(values)
            if not rows:
                continue
            placed += 1
            out.append(record(
                f"{aid}-{slugify(name)}", name, level="admin2", parent=aid,
                parent_name=aimag, country="MNG",
                ethnicity=rows, ethnicity_year=YEAR, ethnicity_note=SOUM_NOTES[kind],
                religion=gap(NOT_AVAILABLE, SOUM_RELIGION_GAP),
                sources=[{"field": "ethnicity", "name": BOOK_SOURCE,
                          "url": ARCHIVE, "license": LICENCE}]))
    if unmatched:
        log(f"  {len(unmatched)} soum row(s) matched no shape in their aimag and are "
            "left unwritten:")
        for line in unmatched:
            log(f"    {line}")
    log(f"  {placed} soums written of the {sum(len(v) for v in geometry.values())} "
        "the boundary file draws")
    return out


def check_national(religion: dict[str, dict[str, float]]) -> None:
    """What the aimags say against what the report says for the country.

    The aimags cannot be added without their populations, which these tables do
    not carry, so the check is the one the figures can bear: Bayan-Ölgii must be
    the Muslim aimag and no other may come near it, and the aimags' Buddhist
    share must bracket the national one.
    """
    if not religion:
        raise SystemExit("mongolia: no aimag's religion could be read")
    muslim = sorted(((v.get("Islam", 0.0), k) for k, v in religion.items()),
                    reverse=True)
    national = NATIONAL_RELIGIOUS * NATIONAL_RELIGION["Buddhism"] / 100.0
    buddhist = sorted(v.get("Buddhism", 0.0) for v in religion.values())
    log(f"  religion read for {len(religion)} of {len(AIMAGS)} aimags; most Muslim "
        f"{muslim[0][1]} {muslim[0][0]:.1f}%, next {muslim[1][1]} {muslim[1][0]:.1f}%; "
        f"Buddhist share runs {buddhist[0]:.1f}% to {buddhist[-1]:.1f}% around the "
        f"national {national:.1f}%")
    if muslim[0][1] != "Bayan-Ölgii":
        raise SystemExit(f"mongolia: the most Muslim aimag reads as {muslim[0][1]}, "
                         "not Bayan-Ölgii; the join or the reading is wrong")
    if not buddhist[0] < national < buddhist[-1]:
        raise SystemExit(f"mongolia: the aimags' Buddhist share runs {buddhist[0]:.1f} "
                         f"to {buddhist[-1]:.1f} and does not bracket the national "
                         f"{national:.1f}")


def run() -> int:
    log(f"mongolia: {CENSUS}")
    report_path = RAW_DIR / REPORT_FILE
    if not report_path.exists():
        raise SystemExit(f"mongolia: {report_path} is missing; run --fetch where "
                         "there is network")
    report = read_report(report_path.read_text(encoding="utf-8"))
    check_report(report)

    religion: dict[str, dict[str, float]] = {}
    soums: dict[str, tuple[dict[str, dict[str, float]], str]] = {}
    gaps: dict[str, str] = {}
    for aimag in AIMAGS:
        path = RAW_DIR / f"{raw_name(aimag)}.txt"
        if not path.exists():
            gaps[aimag] = NO_BOOK_GAP
            log(f"    {aimag:14} no book read")
            continue
        book = pages(path.read_text(encoding="utf-8"))
        faith = read_religion(book)
        if faith:
            religion[aimag] = faith
        table = read_soums(book)
        if table:
            soums[aimag] = table
        top = ", ".join(f"{g} {v:.1f}" for g, v in sorted(
            religion.get(aimag, {}).items(), key=lambda kv: -kv[1])[:3]) \
            or "religion not read"
        log(f"    {aimag:14} {top:48} soums "
            f"{len(table[0]) if table else 0:>3} "
            f"({table[1] if table else 'no table found'})")
    check_national(religion)
    records = build(report, religion, soums, gaps)
    write_json(PROCESSED / OUT, records)
    first = sum(1 for r in records if r["level"] == "admin1")
    log(f"  wrote {first} aimags and {len(records) - first} soums to {OUT}")
    return 0


# ---------------------------------------------------------------------------
# --probe: reconnaissance. Writes nothing.
# ---------------------------------------------------------------------------

def get(url: str, *, limit: int = BYTES, find: str | None = None,
        terms: list[str] | None = None, context: int = 200,
        headers: dict[str, str] | None = None) -> str | None:
    try:
        body = http_get(url, cache=False, retries=1, timeout=60, aia=True,
                        headers=headers)
    except Exception as exc:            # noqa: BLE001 - the probe's product is the reason
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
    from probe_tls import verified_opener            # noqa: PLC0415
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
    except Exception as exc:                         # noqa: BLE001
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="read the books from the Archive into data/raw/mongolia")
    ap.add_argument("--only", help="comma-separated aimags, for --fetch")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--get", action="append")
    ap.add_argument("--post", action="append")
    ap.add_argument("--field", action="append", help="NAME=VALUE for a POST body")
    ap.add_argument("--find",
                    help="print the distinct matches of this regex, not the body")
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
