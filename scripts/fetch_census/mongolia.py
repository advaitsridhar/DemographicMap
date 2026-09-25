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
coordinates, and each word is written with the span it occupies the way
``probe_pdf --boxes`` prints it: these books set their tables in two columns,
so a reader that takes pypdf's string order gets a page of figures followed
by a page of labels, and they write a thousands separator as a space, so
only the gaps say whether "46 192 37 611" is two numbers or four.

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
from common import shard_name  # noqa: E402

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
       # Khentii bare, because that aimag's 2020 book is not under the XAOCT
       # stem and the Archive holds it, if at all, under a numbered name.
       "|Khentii"
       "|url=Census2020_Main_report_Eng[.]pdf).*")
REPLAY = "https://web.archive.org/web/{timestamp}id_/{original}"

# The 22 first-level units as site/data/admin1/MNG.units.json names them, the
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
    # Khentii's 2020 book is not in the Archive: Khentii.pdf is that aimag's
    # 2010 one and 18._Khentii.pdf, the only other candidate, names neither
    # ethnic group nor religion on any of its pages.
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
IRRELIGIOUS = {"шүтдэггүй", "шүтлэггүй", "шашингүй", "шашингүйчүүд",
               "шашиншүтдэггүй", "шашиншүтлэггүй", "ямарнэгэншашиншүтдэггүй"}
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
# Two groups the English report spells differently from the way this file
# carries them; every other column name is identical.
REPORT_NAMES = {"Kazak": "Kazakh", "Hoshuud": "Khoshuud"}

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


def fetch(only: list[str] | None = None, force: bool = False) -> int:
    """Read what is wanted into data/raw/mongolia.

    ``--only`` takes the names below, comma-separated and without spaces --
    the workflow that runs this hands its input to xargs, so an argument with
    a space in it arrives as two. Twenty-two books of twenty megabytes do not
    always finish inside one runner's timeout, which is what ``--only`` is
    for.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    found = captures()
    wanted: list[tuple[str, Path, tuple[str, ...], tuple[str, ...]]] = [
        ("report", RAW_DIR / REPORT_FILE, (REPORT_EN,), REPORT_MARKERS),
    ]
    wanted += [(name, RAW_DIR / f"{raw_name(name)}.txt", files, MARKERS)
               for name, (_en, files) in AIMAGS.items()]
    wrote = 0
    for name, dest, files, markers in wanted:
        if only and name not in only:
            continue
        if dest.exists() and dest.stat().st_size > 2000 and not force:
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


def plain(line: str) -> str:
    """The row as words, without the boxes --fetch wrote beside them."""
    return " ".join(t for t, _a, _b in tokens_of(line))


def value_of(token: str) -> float | None:
    return None if token in {"-", "--"} else float(token.rstrip("%").replace(",", "."))


def figures(run: list[tuple[str, float, float]],
            width: int | None) -> list[float | None] | None:
    """A run of numeric words read as numbers.

    These books write a thousands separator as a space, so "46 192 37 611" is
    two numbers or four and nothing in the text says which. The gaps do: the
    space inside a number is a couple of points wide and the gap between two
    columns is ten or more. Two words are joined only when both are plain
    digits and the second is exactly three of them -- that is what a thousands
    group looks like -- and only when the gap between them is on the near side
    of the widest jump in this row's gaps, which is where the two kinds of gap
    separate. A row of percentages has no joinable pair at all and is left
    alone.

    The run can also be longer than the table is wide, because these pages set
    two tables side by side and one line of glyphs is a row of each. The
    leading ``width`` numbers are this table's row; what follows belongs to
    the table on the right and is left to the line's other run.
    """
    if width is None or len(run) <= (width or 0):
        return [value_of(t) for t, _a, _b in run]
    if any(a < 0 for _t, a, _b in run):
        return None
    gaps = [run[i + 1][1] - run[i][2] for i in range(len(run) - 1)]
    joinable = [i for i, (text, _a, _b) in enumerate(run[:-1])
                if text.isdigit() and run[i + 1][0].isdigit()
                and len(run[i + 1][0]) == 3]
    threshold = -1.0
    if joinable:
        ordered = sorted(gaps)
        jumps = [(ordered[i + 1] / max(ordered[i], 0.5), ordered[i])
                 for i in range(len(ordered) - 1)]
        threshold = max(jumps)[1] if jumps else ordered[-1]
        # ...and never wider than a space. These books are set at eight to
        # eleven points, where a space is two or three points wide and the gap
        # between two columns is ten or more; without the cap, a row that needs
        # one join gets it at its narrowest column boundary, which is how
        # Khovd's "14 2 969" became "14 2969".
        threshold = min(threshold, 6.0)
    groups: list[list[str]] = []
    for i, (text, _a, _b) in enumerate(run):
        if groups and i - 1 in joinable and gaps[i - 1] <= threshold:
            groups[-1].append(text)
        else:
            groups.append([text])
    if len(groups) < width:
        return None
    return [value_of("".join(g)) for g in groups[:width]]


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
    # The table prints Ulaanbaatar twice: once among the aimags and again at
    # the foot, where the four regions are listed and the capital is its own
    # region. The second is the same row, so each block takes each unit once.
    done: set[tuple[str, int]] = set()
    seen = 0
    wanted: tuple[str, ...] | None = None
    for index, line in enumerate(lines):
        heading = plain(line)
        if TRANSPOSE.search(heading):
            wanted = None
            continue
        if MAIN_TABLE.search(heading):
            seen += 1
            wanted = BLOCKS[seen - 1] if seen <= len(BLOCKS) else None
            if wanted and seen <= 2:
                check_block_header(lines, index, wanted)
            continue
        if wanted is None:
            continue
        for label, values in rows_in(line):
            name = BY_ENGLISH.get(label.strip())
            if name is None or (name, seen) in done:
                continue
            done.add((name, seen))
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
        hit = [REPORT_NAMES.get(t, t) for t, _a, _b in tokens_of(line)
               if REPORT_NAMES.get(t, t) in wanted]
        if len(hit) == len(wanted):
            if hit == list(wanted):
                return
            raise SystemExit(f"mongolia: Appendix Table 3.6 heads its columns {hit} "
                             f"where this reader expects {list(wanted)}")
    raise SystemExit(f"mongolia: no header line at {plain(lines[index])!r} names the "
                     f"columns {list(wanted)}")


def check_report(shares: dict[str, dict[str, float]]) -> None:
    missing = sorted(set(AIMAGS) - set(shares))
    if missing:
        raise SystemExit(f"mongolia: Appendix Table 3.6 gives no row for {missing}")
    worst = ("", 100.0)
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
    log(f"  Appendix Table 3.6: {len(shares)} aimags over 26 ethnic groups, each "
        f"adding to 100 (furthest {worst[0]} at {worst[1]:.2f})")


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
    fallback: tuple[float, float] | None = None
    for line in lines:
        for label, values in rows_in(line):
            # Three figures or six: the table prints a total and the two sexes
            # for 2020, and often for 2010 beside it. The narrative says the
            # same numbers in a sentence -- "46.6 хувь нь шашингүйчүүд, 53.4
            # хувь нь шашинтан" -- and a sentence yields one figure, so a row
            # of one is prose and not the table.
            if len(values) not in (3, 6):
                continue
            key, value = group_key(label), year_value(values)
            if value is None:
                continue
            if key in IRRELIGIOUS:
                irreligious = value
                # The two lines are one question with two answers, so either
                # gives the other. Selenge's book prints only "Шүтдэг" under a
                # heading this reader does not recognise as its opposite.
                pair = (100.0 - value, value)
            elif key in RELIGIOUS:
                religious = value
                pair = (value, 100.0 - value)
            else:
                continue
            if (religious is not None and irreligious is not None
                    and abs(religious + irreligious - 100.0) <= 1.0):
                return religious, irreligious
            fallback = fallback or pair
    return fallback


def pick_kinds(lines: list[str]) -> dict[str, float] | None:
    """The breakdown of the religious population, however the book lays it out:
    the religions down the rows, or across the columns with a total beneath.

    A row is kept by its label, and the same label reappears: "Бусад" heads a
    residual in the ethnicity table, in the education table and in this one.
    So each religion's latest reading replaces the one before it and the set
    is tested after every row -- the first set of three or more that adds to
    100 and names Buddhism or Islam is the table, and every book's religion
    table is the one that satisfies that.
    """
    rows: dict[str, float] = {}
    for line in lines:
        for label, values in rows_in(line):
            group = RELIGION.get(group_key(label))
            if not group or len(values) not in (1, 2, 3, 6):
                continue
            value = year_value(values)
            # A dash is nil, not a missing figure: several aimags have no
            # Muslims at all and the table says so with a dash.
            value = 0.0 if value is None and len(values) >= 6 else value
            if value is None or not 0.0 <= value <= 100.0:
                continue
            rows[group] = value
            if (len(rows) >= 3 and abs(sum(rows.values()) - 100.0) <= 1.5
                    and ("Buddhism" in rows or "Islam" in rows)):
                return dict(rows)
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


TITLE = re.compile(r"(?i)хүснэгт|зураг|\b(19|20)\d\d\b")


def header_columns(page: list[str], i: int) -> tuple[list[str], bool] | None:
    """The columns a soum table really has, read from where its words sit.

    Several books set a column's heading over three baselines and in
    fragments: Sukhbaatar prints "Дарь-" and "Уриан-" on the line above the
    others and "ганга" and "хай" on the line below, so the line that looks
    like the header names six groups where the table has eight columns, and a
    reader that trusts it hands every group the column to its left. Here the
    words of the lines around the header are gathered, grouped by the space
    they occupy across the page, and each group's fragments joined in reading
    order: that recovers "Дарьганга" and "Урианхай" and, in Khuvsgul, the
    "Хөвсгөл аймгийн харьяат-Бүгд" whose four lines head the total column.
    """
    window: list[tuple[int, str, float, float]] = []
    for offset in range(-4, 5):
        number = i + offset
        if not 0 <= number < len(page):
            continue
        words = [(t, x0, x1) for t, x0, x1 in tokens_of(page[number]) if x0 >= 0]
        if not words or len(words) > 16:
            continue
        if sum(1 for t, _a, _b in words if NUMBER.match(t)) >= 2:
            if offset > 0:
                break
            continue
        if any(TITLE.search(t) for t, _a, _b in words):
            continue
        window += [(number, t, x0, x1) for t, x0, x1 in words]
    if not window:
        return None
    clusters: list[dict[str, Any]] = []
    for number, text, x0, x1 in sorted(window, key=lambda w: (w[2], w[0])):
        if clusters and x0 <= clusters[-1]["x1"] + 2.0:
            clusters[-1]["x1"] = max(clusters[-1]["x1"], x1)
            clusters[-1]["parts"].append((number, x0, text))
        else:
            clusters.append({"x0": x0, "x1": x1, "parts": [(number, x0, text)]})
    groups: list[str] = []
    has_total = False
    for index, cluster in enumerate(clusters):
        text = "".join(t for _n, _x, t in sorted(cluster["parts"]))
        key = group_key(text.replace("-", ""))
        if key in ETHNIC:
            groups.append(ETHNIC[key])
        elif key in TOTALS or key.endswith(("бүгд", "дүн")):
            if groups:
                return None
            has_total = True
        elif key in HEAD_WORDS or (index == 0 and not groups):
            continue
        else:
            return None
    if len(groups) < 3 or len(groups) != len(set(groups)):
        return None
    return groups, has_total


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


def block_rows(lines: list[str], width: int, soums: dict[str, str],
               refused: set[str] | None = None
               ) -> tuple[dict[str, list[float | None]], list[float | None] | None]:
    """The rows under one header: {label: figures}, and the unit's own line.

    A row is kept only when its name folds to a soum of this aimag. These
    pages set two tables side by side, so one line of glyphs is a row of each,
    and without that test the education table's rows -- whose labels are ethnic
    groups -- land in the soum table and its columns stop adding up. Names that
    are neither a soum nor the aimag's own line go into ``refused``, which the
    caller logs.
    """
    rows: dict[str, list[float | None]] = {}
    total: list[float | None] | None = None
    misses = 0
    hanging: tuple[str, list[float | None]] | None = None
    for line in lines:
        hits = [r for r in rows_in(line, width) if len(r[1]) == width]
        if not hits:
            # A soum whose name is too long for its column is set over two
            # lines -- "Чандмань-" and then "Өндөр" underneath -- and that
            # second line is the end of the name above it, not a row.
            tail = plain(line).strip()
            if (hanging and tail and " " not in tail
                    and not any(ch.isdigit() for ch in tail)
                    and soum_key(hanging[0] + tail) in soums):
                rows.setdefault(hanging[0] + tail, hanging[1])
                hanging = None
                continue
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
            if soum_key(label) not in soums:
                if label.endswith("-"):
                    hanging = (label, values)
                elif refused is not None and group_key(label) not in ETHNIC:
                    refused.add(label)
                continue
            rows.setdefault(label, values)
    return rows, total


def classify(block: dict[str, list[float | None]], total: list[float | None] | None,
             has_total: bool) -> str | None:
    """"row shares" | "counts" | "column shares", or None when no arithmetic fits.

    Each shape is told by its own arithmetic and nothing else, so a table read
    wrongly is refused rather than written:

    * **row shares** -- every soum's own line opens with 100.0 and its groups
      add to about that (about, because the book prints the rest of the groups
      in a continued block);
    * **column shares** -- the aimag's line is 100.0 in every column, because
      each column is one group's distribution over the soums, and the soums add
      to 100 down each column;
    * **counts** -- every figure is a whole number and the soums add to the
      aimag's own line in every column.
    """
    values = [[v or 0.0 for v in row] for row in block.values()]
    if not values or len({len(row) for row in values}) != 1:
        return None
    width = len(values[0])
    columns = [sum(row[i] for row in values) for i in range(width)]
    if (has_total and all(abs(row[0] - 100.0) < 0.05 for row in values)
            and all(50.0 <= sum(row[1:]) <= 100.8 for row in values)):
        # A leading column of exactly 100.0 on every soum's line, and nothing
        # after it adding to more: each line is that soum's own distribution.
        # It can add to less than 100 because the book carries the rest of the
        # groups in a continued block, which is merged in afterwards -- Tes in
        # Zavkhan is 97.5 here and the other 2.5 is three columns away.
        return "row shares"
    if total and len(total) == width:
        printed = [t or 0.0 for t in total]
        if (all(abs(t - 100.0) < 0.05 for t in printed)
                and not all(abs(row[0] - 100.0) < 0.05 for row in values)
                and all(abs(c - 100.0) <= 3.0 for c in columns if c)):
            return "column shares"
        integral = all(float(v).is_integer() for row in values for v in row)
        if integral and all(abs(c - t) <= max(3.0, 0.02 * t)
                            for c, t in zip(columns, printed)):
            return "counts"
    integral = all(float(v).is_integer() for row in values for v in row)
    if integral and has_total and all(
            row[0] + 2.0 >= sum(row[1:]) for row in values):
        return "counts"
    if not has_total and all(abs(sum(row) - 100.0) <= 2.0 for row in values):
        return "row shares"
    return None


class Soums:
    """What one aimag's book says about its soums, and what checks it."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, float]] = {}
        self.shape = ""
        self.aimag: dict[str, float] = {}
        self.weight: dict[str, float] = {}

    def add(self, block: dict[str, list[float | None]], groups: list[str],
            total: list[float | None] | None, total_column: bool,
            continued: bool = False) -> None:
        for label, values in block.items():
            figures = values[1:] if total_column else values
            into = self.rows.setdefault(label, {})
            for group, value in zip(groups, figures):
                if value:
                    into[group] = into.get(group, 0.0) + value
            if total_column and self.shape == "column shares":
                self.weight.setdefault(label, values[0] or 0.0)
        # The aimag's own line is kept only from a block whose arithmetic was
        # checked. A continued block is taken on its labels, and one of
        # Selenge's carries a stray 81,443 where its total should be.
        if total and not continued:
            figures = total[1:] if total_column else total
            for group, value in zip(groups, figures):
                if value is not None:
                    self.aimag.setdefault(group, value)


def read_soums(book: list[list[str]], soums: dict[str, str], refused: set[str],
               report: dict[str, float]) -> Soums | None:
    """What an aimag's book prints for its soums, block by block.

    A block is a header line naming three or more ethnic groups followed by
    rows of a label and exactly as many figures. Blocks of the same shape are
    merged, because most books print the table in two or three column blocks
    under a "continued" heading.
    """
    out = Soums()
    for page in book:
        for i, line in enumerate(page):
            head = header_groups(line)
            if not head:
                continue
            groups, has_total = header_columns(page, i) or head
            read = best_block(page[i + 1:], groups, has_total, soums, refused,
                              out.rows, tokens_of(line))
            if not read:
                continue
            block, kind, total_column, total = read
            if kind == CONTINUED:
                # A block carrying the same soums as the one before it and a
                # different set of groups is the rest of the same table, which
                # most books print under "Хүснэгт 3.6-ын үргэлжлэл". Its own
                # columns add to nothing in particular -- they are the groups
                # nobody in the aimag much belongs to -- so it is taken on the
                # strength of its labels rather than its arithmetic, and only
                # where it is not the transpose (see best_block).
                if not out.rows or out.shape not in ("row shares", "counts"):
                    continue
                if not plausible(block, groups, total_column, out, report):
                    continue
            elif out.shape and kind != out.shape:
                continue
            else:
                out.shape = kind
            out.add(block, groups, total, total_column, kind == CONTINUED)
    return out if out.rows else None


def plausible(block: dict[str, list[float | None]], groups: list[str],
              total_column: bool, out: Soums, report: dict[str, float]) -> bool:
    """Whether a continued block's columns can be the groups its header names.

    The continued blocks carry the groups nobody in the aimag much belongs to,
    so their own arithmetic says nothing; but each column still has to be the
    size the national report says that group is. One of Selenge's is not: its
    columns would make the Khoshuud, of whom the report finds none in Selenge,
    several hundred people.
    """
    scale = sum(v for v in out.aimag.values() if v > 0) or 100.0
    for column, group in enumerate(groups):
        offset = column + (1 if total_column else 0)
        total = sum((row[offset] or 0.0) for row in block.values())
        if out.shape == "counts":
            mine = 100.0 * total / scale
        else:
            mine = total / max(len(block), 1)
        if abs(mine - report.get(group, 0.0)) > max(0.5, 0.2 * report.get(group, 0.0)):
            return False
    return True


def check_soums(name: str, table: Soums, report: dict[str, float]) -> str | None:
    """Why this aimag's soum table cannot be trusted, or None.

    Two books head a column with a name that is split over three baselines --
    Sukhbaatar sets "Дарь-" above "ганга" -- and the reader then has one name
    fewer than the table has columns and would hand each group the column to
    its left. That is the mis-match this project refuses rather than writes, so
    every table is checked against Appendix Table 3.6 of the national report,
    which was read from a different document:

    * where the book prints the aimag's own line, that line is the aimag's
      composition and must be the one the report gives;
    * where it prints each group's distribution over the soums, the soum's
      share of the aimag can be worked out from it and must be the share the
      book's own first column prints.
    """
    # For a table of counts the soums themselves add to the aimag, so the check
    # is on the sum; for one of shares the aimag's own printed line is it.
    mine_raw: dict[str, float] = dict(table.aimag)
    if table.shape == "counts":
        mine_raw = {}
        for values in table.rows.values():
            for group, value in values.items():
                mine_raw[group] = mine_raw.get(group, 0.0) + value
    if table.shape == "row shares" and not mine_raw:
        # A book that prints no line of its own for the aimag: the soums'
        # unweighted mean is a coarser thing than the aimag's composition, so
        # it is compared loosely, and it still catches a table read one column
        # out of step.
        for values in table.rows.values():
            for group, value in values.items():
                mine_raw[group] = mine_raw.get(group, 0.0) + value
        total = sum(v for v in mine_raw.values() if v > 0)
        against = sum(report.get(g, 0.0) for g in mine_raw)
        if total <= 0 or against <= 0:
            return "nothing in the soum table could be read against the report"
        for group, value in mine_raw.items():
            mine = 100.0 * value / total
            theirs = 100.0 * report.get(group, 0.0) / against
            if abs(mine - theirs) > 15.0:
                return (f"the soums average {mine:.1f}% {group} where the national "
                        f"report's Appendix Table 3.6 puts the aimag at {theirs:.1f}%")
        return None
    if table.shape in ("row shares", "counts"):
        # Both sides are read over the groups this table names, because a book
        # that prints its table in two blocks names only some of them in each.
        total = sum(v for v in mine_raw.values() if v > 0)
        against = sum(report.get(g, 0.0) for g in mine_raw)
        if total <= 0 or against <= 0:
            return "nothing in the soum table could be read against the report"
        for group, value in mine_raw.items():
            mine = 100.0 * value / total
            theirs = 100.0 * report.get(group, 0.0) / against
            # A fifth of the group, or half a point, whichever is the larger:
            # a table read a column out of step gives a group that is not in
            # the aimag at all a real share, and gives a group that is one of
            # a few hundred people.
            if abs(mine - theirs) > max(0.5, 0.2 * theirs):
                return (f"the soum table puts {group} at {mine:.1f}% of the aimag "
                        f"where the national report's Appendix Table 3.6 has "
                        f"{theirs:.1f}%")
    if table.shape == "column shares":
        if not table.weight:
            return "the soum table prints no column of each soum's own share"
        for label, printed in table.weight.items():
            derived = sum(v * report.get(g, 0.0) for g, v in table.rows[label].items())
            if abs(derived / 100.0 - printed) > 1.2:
                return (f"weighting {label}'s column by the report's shares gives "
                        f"{derived / 100.0:.1f}% of the aimag where the book's own "
                        f"first column prints {printed:.1f}%")
    return None


def first_column(lines: list[str]) -> float | None:
    """Where the first figure of this block's rows begins."""
    for line in lines[:12]:
        for text, x0, _x1 in tokens_of(line):
            if NUMBER.match(text) and x0 >= 0:
                return x0
        if any(NUMBER.match(t) for t, _a, _b in tokens_of(line)):
            return None
    return None


def best_block(lines: list[str], groups: list[str], has_total: bool,
               soums: dict[str, str], refused: set[str],
               seen: dict[str, dict[str, float]] | None = None,
               header: list[tuple[str, float, float]] | None = None
               ) -> tuple[dict[str, list[float | None]], str, bool,
                          list[float | None] | None] | None:
    """The rows under a header, read as wide as the figures say they are.

    Several books print the total column's heading over three baselines --
    "Хөвсгөл", "аймгийн", "харьяат-", "Бүгд" around the line that names the
    groups -- so the header alone does not say whether there is a total column
    in front of the groups. Both widths are read and the one whose arithmetic
    works is kept; where both work, the one that reads more soums.
    """
    options = [(len(groups) + 1, True)] if has_total else [
        (len(groups) + 1, True), (len(groups), False)]
    if not has_total and header is not None:
        # Whether a column of the unit's own total stands in front of the
        # groups is a question about where the figures sit, and the glyphs
        # answer it: if a row's first figure begins to the left of the first
        # group's heading, there is a column there that the heading does not
        # name. Guessing instead cost Dornod its second block, where both
        # widths read fourteen rows and the wrong one silently shifted the
        # Barga and Uzemchin columns by one.
        leading = first_column(lines)
        first_group = min((x0 for t, x0, _x1 in header if group_key(t) in ETHNIC),
                          default=None)
        if leading is not None and first_group is not None:
            options = [(len(groups) + 1, True)] if leading + 8.0 < first_group else [
                (len(groups), False)]
    best: tuple[dict[str, list[float | None]], str, bool,
                list[float | None] | None] | None = None
    for width, total_column in options:
        block, total = block_rows(lines, width, soums, refused)
        if len(block) < 2:
            continue
        kind = classify(block, total, total_column)
        if not kind and seen and not total_column:
            overlap = len(set(block) & set(seen)) / len(block)
            printed = [t or 0.0 for t in (total or [])]
            transpose = bool(printed) and all(abs(t - 100.0) < 0.05 for t in printed)
            if overlap >= 0.7 and not transpose:
                kind = CONTINUED
        if kind and (best is None or len(block) > len(best[0])):
            best = (block, kind, total_column, total)
    return best


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

def shapes() -> dict[str, dict[str, str]]:
    """{aimag: {folded soum name: the boundary file's spelling}}."""
    from common import read_json                     # noqa: PLC0415
    site = Path(__file__).resolve().parent.parent.parent / "site" / "data"
    first = read_json(site / "admin1" / shard_name("MNG"), []) or []
    second = read_json(site / "admin2" / shard_name("MNG"), []) or []
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
CONTINUED = "continued"


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
NO_SOUM_TABLE_GAP = (
    "The 2020 census published ethnic group for this aimag; this aimag's own results "
    "book, which is where the census published anything by soum, prints no table of "
    "ethnic group by soum that could be read.")


def build(report: dict[str, dict[str, float]],
          religion: dict[str, dict[str, float]],
          soums: dict[str, Soums],
          gaps: dict[str, str], soum_gaps: dict[str, str],
          geometry: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    from common import slugify                       # noqa: PLC0415
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
        kind = table.shape if table else ""
        weights = report.get(aimag, {}) if kind == "column shares" else None
        written: set[str] = set()
        for label, values in sorted(table.rows.items() if table else []):
            name = geometry.get(aimag, {}).get(soum_key(label))
            if not name:
                unmatched.append(f"{aimag} / {label}")
                continue
            if name in written:
                unmatched.append(f"{aimag} / {label} (a second row for {name})")
                continue
            written.add(name)
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
        # ...and a record for every soum the boundary file draws that no row
        # reached, saying which of the four things went wrong. A gap that
        # names what was asked of which source is the point of this project;
        # a soum left out of the file entirely would say nothing at all.
        for folded, name in sorted(geometry.get(aimag, {}).items(), key=lambda kv: kv[1]):
            if name in written:
                continue
            why = soum_gaps.get(aimag) or (
                f"This aimag's 2020 census results book prints ethnic group by soum "
                f"and no line of that table is for {name}."
                if table else NO_SOUM_TABLE_GAP)
            out.append(record(
                f"{aid}-{slugify(name)}", name, level="admin2", parent=aid,
                parent_name=aimag, country="MNG",
                ethnicity=gap(NOT_AVAILABLE, why),
                religion=gap(NOT_AVAILABLE, SOUM_RELIGION_GAP)))
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

    geometry = shapes()
    religion: dict[str, dict[str, float]] = {}
    soums: dict[str, Soums] = {}
    gaps: dict[str, str] = {}
    refused: dict[str, set[str]] = {}
    soum_gaps: dict[str, str] = {}
    for aimag in AIMAGS:
        path = RAW_DIR / f"{raw_name(aimag)}.txt"
        if not path.exists():
            gaps[aimag] = NO_BOOK_GAP
            soum_gaps[aimag] = NO_BOOK_GAP
            log(f"    {aimag:14} no book read")
            continue
        book = pages(path.read_text(encoding="utf-8"))
        faith = read_religion(book)
        if faith:
            religion[aimag] = faith
        refused[aimag] = set()
        table = read_soums(book, geometry.get(aimag, {}), refused[aimag],
                           report.get(aimag, {}))
        wrong = check_soums(aimag, table, report.get(aimag, {})) if table else None
        if table and not wrong:
            soums[aimag] = table
        elif wrong:
            log(f"    {aimag:14} soum table refused: {wrong}")
            soum_gaps[aimag] = (
                "This aimag's 2020 census results book prints a table of ethnic group "
                f"by soum, and it was refused rather than written because {wrong}. "
                "A composition read one column out of step is worse than none.")
            table = None
        top = ", ".join(f"{g} {v:.1f}" for g, v in sorted(
            religion.get(aimag, {}).items(), key=lambda kv: -kv[1])[:3]) \
            or "religion not read"
        log(f"    {aimag:14} {top:48} soums "
            f"{len(table.rows) if table else 0:>3} "
            f"({table.shape if table else 'no table found'})")
    for aimag, names in sorted(refused.items()):
        if names and aimag in soums:
            log(f"    {aimag}: {len(names)} row label(s) in the soum table match no "
                f"shape of this aimag and are left unwritten: {sorted(names)[:8]}")
    check_national(religion)
    records = build(report, religion, soums, gaps, soum_gaps, geometry)
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
    ap.add_argument("--only", help="comma-separated aimags (or 'report'), for --fetch")
    ap.add_argument("--force", action="store_true",
                    help="with --fetch, read again what is already on disk")
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
        return fetch([a.strip() for a in args.only.split(",")] if args.only else None,
                     force=args.force)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
