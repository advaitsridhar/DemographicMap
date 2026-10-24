#!/usr/bin/env python3
"""Thailand: religion, nationality and language by province, from the 2010 census's provincial reports.

The 2000 census is read for all of Thailand (``thailand``, ``thailand_nationality``)
and has no row for **Bueng Kan**, which was made from eight districts of Nong
Khai in March 2011. The 2010 Population and Housing Census was taken in
September 2010, and the National Statistical Office published a report for
each of the 77 provinces it had by then, Bueng Kan among them
(``popcensus.nso.go.th/report/<Province>_T.pdf``). That host no longer
resolves, and the Office's others refuse this project (docs/SOURCES.md,
*Thailand: a language table that cannot be a composition*); the Internet
Archive kept 75 of the reports, and ``CAPTURES`` names each file and the
capture read. Lampang's and Suphan Buri's were not captured, and those two keep
2000.

**Religion and nationality.** Each report's section 1.5, "Religion and
nationality", prints a table of the province's people by religion and by
nationality, in percent, for the province and for its municipal and
non-municipal areas; the province's own column, the first, is read. Its rows
are the faiths and the nationalities the province has: Buddhist, Muslim,
Christian and others; Thai and the few nationalities the province counts most
of (Lao along the Mekong, Burmese and Cambodian on the borders, Malaysian in
the far south, Chinese, Japanese and British where they live), and others. A
row printed "a" (under 0.1%) or 0.0 is left out. The table is found by its
100.0 rows, not by its number, and read as the text layer lays it out: a
nationality block continued on the next page (Nong Khai's), figures that fall
to the line under their label (Yala's, Saraburi's), a footnote mark after a
label (Ratchaburi's), a figure split at its point (Phuket's "3. 6"), a
misprinted later column (Krabi's "614"), Thai marks drawn from a font's
private-use glyphs. Bangkok's nationality block is the one whose text comes
apart; ``FROM_PAGE`` holds its rows as the page prints them. A footnote under
the table that leaves out people whose answer was not known (Phuket's,
Ratchaburi's) is said in the note.

**Every block is checked against the report's own key indicators**, the page
near the front that prints "Thai citizenship (%)" and "Buddhism (%)" for 1990,
2000 and 2010. A block stands when its Thai (or Buddhist) row is the
indicators' 2010 figure, or one in the last digit from it, and its rows can
add to 100 once rounding is allowed for (``adds_up``: each printed figure
within 0.05, each "a" under 0.1); otherwise the indicators stand in its place
-- the Thai share and everyone else, as the 2000 reading does, and Buddhism
with the other faiths they print -- and the note says why. Where the two part
by more than a digit the table's Thai share is the higher every time (Mae Hong
Son's prints 94.1% and its indicators 90.0%); why is not printed. Two tables'
footnotes say they leave out people whose nationality was not known, which
would raise the Thai share, but those two print their indicators' figure
exactly. A block printed word for word in two reports is held to the exact
figure in both.

**Language** is table 6 of each report's statistical annex, its people by the
languages they usually speak at home: only Thai, Thai and another language, or
another language only, as counts that add up to the province, shown as shares
in the words of the country's figure (the Factbook's line for the same census).
Thai there takes in its regional varieties: Isan-speaking Bueng Kan counts
361,914 of its 362,754 people as speaking only Thai.

**Bueng Kan and Nong Khai.** Nong Khai's report counts the province as it
was at the census, all seventeen districts: its district tables list Bueng
Kan (78,423 people), Seka (74,616), So Phisai (62,328) and the five others that
became Bueng Kan in March 2011. Bueng Kan's report counts those eight districts
alone, 362,754 people. So Bueng Kan's figure is its own, and Nong Khai's is
shown on Nong Khai as drawn now, as its 2000 figure is, with a note that it
covers both (the build's ``ROW_COVERS_SHAPES`` keeps a row on its own shape).

Usage:
    python -m scripts.fetch_census.thailand_2010
    python -m scripts.fetch_census.thailand_2010 --probe          # print, write nothing
    python -m scripts.fetch_census.thailand_2010 --only "Bueng Kan"   # print, write nothing
"""

from __future__ import annotations

import argparse
import io
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .sea_common import drawn, fold

OUT = "thailand_2010.json"
YEAR = 2010
LICENCE = "Open Government Data of Thailand (NSO publication)"
REPORTS = "http://popcensus.nso.go.th/report/"
SOURCE = ("National Statistical Office, 2010 Population and Housing Census, {province} "
          "report: section 1.5, people by religion and nationality (percent)")
INDICATORS = ("National Statistical Office, 2010 Population and Housing Census, {province} "
              "report: key indicators, 2010")
LANGUAGE_SOURCE = ("National Statistical Office, 2010 Population and Housing Census, {province} "
                   "report: table 6, population by usual languages spoken at home")
# Seconds between two reports fetched from the Archive, which asks to be read
# gently; a report already in the cache costs nothing and waits for nothing.
PAUSE = 3.0
# The pages searched for the table and the indicators; both sit in the first
# thirty of a report of two hundred, and reading the rest costs minutes each.
PAGES = 60

# Province, as the boundary file names it less "Province" -> (report, capture).
CAPTURES: dict[str, tuple[str, str]] = {
    "Amnat Charoen": ("AmnatCharoen_T.pdf", "20160303183316"),
    "Ang Thong": ("AngThong_T.pdf", "20160303174311"),
    "Bangkok": ("Bangkok_T.pdf", "20160303213735"),
    "Bueng Kan": ("BuengKan_T.pdf", "20160304023534"),
    "Buri Ram": ("BuriRam_T.pdf", "20160304023555"),
    "Chachoengsao": ("Chachoengsao_T.pdf", "20160303170110"),
    "Chai Nat": ("ChaiNat_T.pdf", "20160303171649"),
    "Chaiyaphum": ("Chaiyaphum_T.pdf", "20160303210740"),
    "Chanthaburi": ("Chanthaburi_T.pdf", "20160414135618"),
    "Chiang Mai": ("ChiangMai_T.pdf", "20160303193158"),
    "Chiang Rai": ("ChiangRai_T.pdf", "20160415115826"),
    "Chon Buri": ("ChonBuri_T.pdf", "20160303222803"),
    "Chumphon": ("Chumphon_T.pdf", "20160303181955"),
    "Kalasin": ("Kalasin_T.pdf", "20160415120008"),
    "Kamphaeng Phet": ("KamphaengPhet_T.pdf", "20160303174244"),
    "Kanchanaburi": ("Kanchanaburi_T.pdf", "20160303174322"),
    "Khon Kaen": ("KhonKaen_T.pdf", "20160303195950"),
    "Krabi": ("Krabi_T.pdf", "20160303180748"),
    "Lamphun": ("Lamphun_T.pdf", "20160303211634"),
    "Loei": ("Loei_T.pdf", "20160303211822"),
    "Lopburi": ("LopBuri_T.pdf", "20160303170314"),
    "Mae Hong Son": ("MaeHongSon_T.pdf", "20160303200858"),
    "Maha Sarakham": ("MahaSarakham_T.pdf", "20160303193417"),
    "Mukdahan": ("Mukdahan_T.pdf", "20160303174302"),
    "Nakhon Nayok": ("NakhonNayok_T.pdf", "20160303191538"),
    "Nakhon Pathom": ("NakhonPathom_T.pdf", "20160415070607"),
    "Nakhon Phanom": ("NakhonPhanom_T.pdf", "20160303180617"),
    "Nakhon Ratchasima": ("NakhonRatchasima_T.pdf", "20160303193338"),
    "Nakhon Sawan": ("NakhonSawan_T.pdf", "20160303195111"),
    "Nakhon Si Thammarat": ("NakhonSiThammarat_T.pdf", "20160415064644"),
    "Nan": ("Nan_T.pdf", "20160303184452"),
    "Narathiwat": ("Narathiwat_T.pdf", "20160303221229"),
    "Nong Bua Lam Phu": ("NongBuaLamPhu_T.pdf", "20160304191439"),
    "Nong Khai": ("NongKhai_T.pdf", "20160303180930"),
    "Nonthaburi": ("Nonthaburi_T.pdf", "20160415065002"),
    "Pathum Thani": ("PathumThani_T.pdf", "20160304190447"),
    "Pattani": ("Pattani_T.pdf", "20160415071025"),
    "Phangnga": ("Phangnga_T.pdf", "20160303204915"),
    "Phatthalung": ("Phatthalung_T.pdf", "20160414124504"),
    "Phayao": ("Phayao_T.pdf", "20160303185250"),
    "Phetchabun": ("Phetchabun_T.pdf", "20160414134225"),
    "Phetchaburi": ("Phetchaburi_T.pdf", "20160303211411"),
    "Phichit": ("Phichit_T.pdf", "20160303171959"),
    "Phitsanulok": ("Phitsanulok_T.pdf", "20160303182704"),
    "Phra Nakhon Si Ayutthaya": ("Ayutthaya_T.pdf", "20160303165808"),
    "Phrae": ("Phrae_T.pdf", "20160303210845"),
    "Phuket": ("Phuket_T.pdf", "20160303190029"),
    "Prachin Buri": ("PrachinBuri_T.pdf", "20160303174413"),
    "Prachuap Khiri Khan": ("Phachuap_T.pdf", "20160303171211"),
    "Ranong": ("Ranong_T.pdf", "20150514081846"),
    "Ratchaburi": ("Ratchaburi_T.pdf", "20160304023635"),
    "Rayong": ("Rayong_T.pdf", "20160304023654"),
    "Roi Et": ("RoiEt_T.pdf", "20160415064341"),
    "Sa Kaeo": ("SaKaeo_T.pdf", "20160303215742"),
    "Sakon Nakhon": ("SakonNakhon_T.pdf", "20160304192229"),
    "Samut Prakan": ("SamutPrakan_T.pdf", "20160414131740"),
    "Samut Sakhon": ("SamutSakhon_T.pdf", "20160303220634"),
    "Samut Songkhram": ("SamutSongkhram_T.pdf", "20160303181232"),
    "Saraburi": ("Saraburi_T.pdf", "20160415070957"),
    "Satun": ("Satun_T.pdf", "20160304192756"),
    "Si Sa Ket": ("SiSaKet_T.pdf", "20160303182914"),
    "Sing Buri": ("SingBuri_T.pdf", "20160304023757"),
    "Songkhla": ("Songkhla_T.pdf", "20160304023900"),
    "Sukhothai": ("Sukhothai_T.pdf", "20160414135717"),
    "Surat Thani": ("SuratThani_T.pdf", "20150925065914"),
    "Surin": ("Surin_T.pdf", "20160303193242"),
    "Tak": ("Tak_T.pdf", "20160303193433"),
    "Trang": ("Trang_T.pdf", "20160303212107"),
    "Trat": ("Trat_T.pdf", "20160303182403"),
    "Ubon Ratchathani": ("Ubonatchathani_T.pdf", "20160303203058"),
    "Udon Thani": ("UdonThani_T.pdf", "20160303181252"),
    "Uthai Thani": ("UthaiThani_T.pdf", "20160303200042"),
    "Uttaradit": ("Uttaradit_T.pdf", "20160304023920"),
    "Yala": ("Yala_T.pdf", "20160303194707"),
    "Yasothon": ("Yasothon_T.pdf", "20160303204205"),
}

# The table's rows, in the words the map uses. A row the table prints and
# these do not name stops the run: a new label is read, not guessed at.
RELIGIONS = {"พุทธ": "Buddhism", "อิสลาม": "Islam", "คริสต์": "Christianity",
             "ฮินดู": "Hinduism", "ซิกข์": "Sikhism", "ขงจื้อ": "Confucianism",
             "ไม่มีศาสนา": "No religion", "อื่นๆ": "Other religions",
             # Bangkok's report spells the Sikhs' faith so.
             "ซิกซ์": "Sikhism"}
NATIONALITIES = {"ไทย": "Thai", "ลาว": "Lao", "พม่า": "Burmese", "กัมพูชา": "Cambodian",
                 "จีน": "Chinese", "เวียดนาม": "Vietnamese", "อินเดีย": "Indian",
                 "มาเลเซีย": "Malaysian", "ญี่ปุ่น": "Japanese", "เกาหลี": "Korean",
                 "ฟิลิปปินส์": "Filipino", "สหราชอาณาจักร": "British", "อังกฤษ": "British",
                 "เยอรมนี": "German", "เยอรมัน": "German", "สหรัฐอเมริกา": "American",
                 "อเมริกัน": "American", "อื่นๆ": "Other nationalities",
                 # Phayao's text layer drops the tone mark of ญี่ปุ่น.
                 "ญี่ปุน": "Japanese"}
LABELS = set(RELIGIONS) | set(NATIONALITIES)
RESIDUAL_FAITH = "Other or not stated"
RESIDUAL_NATIONALITY = "Foreign, stateless or unknown"
# Table 6's first three rows, the people who usually speak only Thai at home,
# Thai and another language, or another language only, in the words of the
# country's figure, which is the Factbook's line for the same census.
LANGUAGES = {"ภาษาไทยภาษาเดียว": "Thai only", "ภาษาไทยและภาษาอื่น": "Thai and other languages",
             "ภาษาอื่นอย่างเดียว": "only other languages"}
COUNT_ROW = re.compile(r"^\s*(\D+?)\s+([\d,]+|-)(?=\s|$)")
# How far from table 6's first row its "everyone" row is looked for: a text
# layer can put the table's heading and total after its rows (Nakhon Phanom's).
NEAR = 15

VALUE = r"(?:a|-|\d+\.\d)"
# A column after the first, as printed: only the first is read, and a later one
# can be misprinted -- Krabi's table prints 614 for its non-municipal Buddhists.
COLUMN = r"[-a\d.,]+"
# A footnote mark after a label: Ratchaburi's "อื่นๆ 1/".
MARK = r"(?:\s*\d/)?"
HEAD = re.compile(rf"^\s*(ศาสนา|สัญชาติ)\S*{MARK}\s+100\.0(?:\s+100\.0){{0,2}}\s*$")
ROW = re.compile(rf"^\s*(\D+?){MARK}\s+({VALUE})(?:\s+{COLUMN}){{0,2}}\s*$")
# The figures of a row whose label the text layer left on the line above, with
# or without a blank line between: Yala's ไทย and พม่า, Saraburi's พม่า.
FIGURES = re.compile(rf"^\s*{VALUE}(?:\s+{COLUMN}){{0,2}}\s*$")
# The table's footnotes -- "a less than 0.1", "a very few, under 0.1", "1/
# excluding unknown" -- and a "note:" line, which would otherwise read as rows.
FOOTNOTE = re.compile(r"^\s*a\s|^\s*\d/|น้อยกว่า|หมายเหตุ|ไม่ถึงร้อยละ|น้อยมาก")
# What a text layer holds that is not what is printed. Thai marks some reports'
# fonts draw from the Private Use Area -- the Windows Thai shaping glyphs, U+F700
# to U+F71A -- are the letters they stand for: "คริสต" is คริสต์ and
# "พมา" is พม่า. Zero-width marks and the soft hyphen are nothing, and the
# no-break space is a space.
TEXT = str.maketrans({0xF700: "ฐ", 0xF701: "ิ", 0xF702: "ี", 0xF703: "ึ", 0xF704: "ื",
                      0xF705: "่", 0xF706: "้", 0xF707: "๊", 0xF708: "๋", 0xF709: "์",
                      0xF70A: "่", 0xF70B: "้", 0xF70C: "๊", 0xF70D: "๋", 0xF70E: "์",
                      0xF70F: "ญ", 0xF710: "ั", 0xF711: "ํ", 0xF712: "็", 0xF713: "่",
                      0xF714: "้", 0xF715: "๊", 0xF716: "๋", 0xF717: "์", 0xF718: "ุ",
                      0xF719: "ู", 0xF71A: "ฺ",
                      0x200B: None, 0x200C: None, 0x200D: None, 0xFEFF: None,
                      0x00AD: None, 0x00A0: " "})
# How far a block's Thai or Buddhist row may sit from the key indicators'
# figure: one in the last printed digit, which two roundings of one count can
# differ by. A block printed word for word in two reports is held to the exact
# figure in both.
SLACK = 0.1
# The key indicators' 2010 figure is the last number before the English label;
# Bangkok's report says "Thai nationalities" and "Buddhists", Krabi's "Buddihism".
THAI = re.compile(r"(\d+\.\d)\s+Thai (?:citizenship|nationality|nationalities)\s*\(%\)")
FAITH = re.compile(r"(\d+\.\d)\s+(Budd\w*|Muslims?|Islam\w*|Christian\w*)\s*\(%\)")
# Pages read past the one where the table and the key indicators were first
# both seen, so that a block continued on the next page is read: Nong Khai's
# nationality rows are on the page after its religion rows.
MORE = 2
# How far into a report its statistical annex is searched for table 6, which
# sits some fifty to seventy pages in.
ANNEX_PAGES = 140

# Rows read from the printed page where its text layer comes apart. Bangkok's
# nationality block, on page 35 of its report, extracts as scattered fragments
# of words; these are its rows as the page prints them, and page 62 prints the
# same figures in English (Thai 91.4, Burmese 2.6, Cambodian 0.9, Chinese 0.9,
# Japanese 0.8, Laotian 0.6, Others 2.8).
FROM_PAGE: dict[str, dict[str, list[tuple[str, list[str]]]]] = {
    "Bangkok": {"nationality": [("ไทย", ["91.4"]), ("พม่า", ["2.6"]), ("กัมพูชา", ["0.9"]),
                                ("จีน", ["0.9"]), ("ญี่ปุ่น", ["0.8"]), ("ลาว", ["0.6"]),
                                ("อื่นๆ", ["2.8"])]},
}

# A table's note, and the sentence on its remainder, said where the remainder is shown.
NOTE_RELIGION = (
    "The 2010 Population and Housing Census, the province's report: the province's people "
    "by religion, in percent, as section 1.5 prints them.{remainder} A faith the table "
    "prints as under 0.1% is left out.")
NOTE_NATIONALITY = (
    "Nationality, not ethnicity: Thailand's census does not ask ethnicity, and this is the "
    "2010 census's count of the province's people by nationality, in percent, as section 1.5 "
    "of the province's report prints it. 'Thai' names no one people: the Isan, Malay, Khmer, "
    "Kuy, hill peoples and Chinese who hold Thai nationality are all in it.{remainder} A "
    "nationality the table prints as under 0.1% is left out.")
REMAINDER = {"religion": ("Other religions", " 'Other religions' is the table's own "
                          "remainder, every faith it does not name."),
             "nationality": ("Other nationalities", " 'Other nationalities' is the table's "
                             "own remainder, every nationality it does not name.")}
NOTE_FROM_INDICATORS = (
    "The 2010 Population and Housing Census, the province's report: the province's people "
    "by {what}, in percent, as its key indicators print them. The report's section 1.5 "
    "table cannot be used -- {why} -- so the key indicators' figures are shown.")
WHY_ROW = "it prints {row} {table}% where the key indicators print {printed}%"
WHY_MISSING = "it has no {row} row"
WHY_SUM = "its rows add to {total:.1f}%, further from 100 than rounding allows"
WHY_COPY = ("its rows are {other}'s, word for word, and print {row} {table}% where the key "
            "indicators print {printed}%")
WHY_NONE = "its rows cannot be read in the archived copy of the report"
NOTE_INDICATOR_FAITHS = (
    " They name only the faiths shown; '{residual}' is what those leave of 100%.")
NOTE_INDICATOR_NATIONALITY = (
    " They print the share of Thai nationality and the share of people not of Thai "
    "nationality, shown here as '{residual}'.")
# A footnote under the table that says it leaves out the people whose answer was
# not known: Phuket's marks the whole table, Ratchaburi's its nationality rows.
NOTE_UNKNOWN = {"religion": " The table leaves out people whose answer was not known, as its "
                            "footnote says.",
                "nationality": " The table leaves out people whose nationality was not known, "
                               "as its footnote says."}
NOTE_LANGUAGE = (
    "The 2010 Population and Housing Census, the province's report, table 6: the province's "
    "people by the languages they usually speak at home, as shares of the table's counts. "
    "Thai there takes in its regional varieties -- Isan-speaking Bueng Kan counts 99.8% of "
    "its people as speaking only Thai -- and the table lists the other languages spoken, "
    "Malay (Yawi), Khmer, Karen, Hmong, Mon, Lao, Chinese and Burmese among them, by who "
    "speaks them. A share under 0.05% is left out.")
NOTE_SPLIT = {
    "Bueng Kan": (" Bueng Kan was made from eight districts of Nong Khai in March 2011, six "
                  "months after the census was taken; the Office published those districts' "
                  "count as Bueng Kan's own report."),
    "Nong Khai": (" The report counts Nong Khai as it was at the census, with the eight "
                  "districts that became Bueng Kan province in March 2011; Bueng Kan's own "
                  "report counts those eight districts alone."),
}
# Each composition's check: the row compared, and how a note names it.
KEYS = {"religion": ("Buddhism", "Buddhism"), "nationality": ("Thai", "Thai nationality")}

Block = list[tuple[str, list[str]]]


@dataclass
class Reading:
    """One report's religion and nationality, and what was checked."""
    province: str
    religion: list[dict[str, Any]] = field(default_factory=list)
    nationality: list[dict[str, Any]] = field(default_factory=list)
    religion_from: str = "table"
    nationality_from: str = "table"
    religion_note: str = ""
    nationality_note: str = ""
    language: list[dict[str, Any]] = field(default_factory=list)
    language_note: str = ""
    problems: list[str] = field(default_factory=list)
    # Every block found, and the block each composition stands on.
    found: dict[str, list[Block]] = field(default_factory=dict)
    raw: dict[str, Block] = field(default_factory=dict)


def clean(line: str) -> str:
    """A line as printed (``TEXT``), with a figure the text layer split at its
    point -- Phuket's "3. 6" -- made whole."""
    return re.sub(r"(?<=\d)\. (?=\d)", ".", line.translate(TEXT))


def report_text(body: bytes) -> tuple[list[str], list[str]]:
    """A report's text layer, line by line, twice: its front, to ``MORE`` pages
    past the one where section 1.5's table and the key indicators were first
    both seen (``PAGES`` at most), and all that was read, which goes on into the
    statistical annex as far as its table 6."""
    from pypdf import PdfReader                      # noqa: PLC0415 -- optional
    reader = PdfReader(io.BytesIO(body))
    lines: list[str] = []
    cut = seen = None
    for number, page in enumerate(reader.pages[:ANNEX_PAGES]):
        lines.extend(clean(line) for line in (page.extract_text() or "").splitlines())
        if cut is None:
            if seen is None and all(blocks(lines).values()) and THAI.search("\n".join(lines)):
                seen = number
            if (seen is not None and number >= seen + MORE) or number + 1 >= PAGES:
                cut = len(lines)
        if cut is not None and languages(lines) is not None:
            break
    return lines[:cut], lines


def label(text: str) -> str:
    """A row's label without the spaces a text layer scatters through Thai."""
    return re.sub(r"\s+", "", text)


def blocks(lines: list[str], notes: list[str] | None = None) -> dict[str, list[Block]]:
    """Every religion block and every nationality block of section 1.5's table,
    in the order printed. A block is a 100.0 row and the rows under it, to a
    footnote, the next block or the first line that is not a row. ``notes``,
    given, gathers the footnotes that end a block."""
    found: dict[str, list[Block]] = {"religion": [], "nationality": []}
    rows: Block | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if head := HEAD.match(line):
            rows = []
            found["religion" if head.group(1) == "ศาสนา" else "nationality"].append(rows)
            continue
        if rows is None or not line.strip():
            continue
        if FOOTNOTE.search(line):
            if notes is not None:
                notes.append(line.strip())
            rows = None
            continue
        row = ROW.match(line)
        if row is None and label(line) in LABELS:
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and FIGURES.match(lines[j]):
                line, i = f"{line.strip()} {lines[j].strip()}", j + 1
                row = ROW.match(line)
        if row is None:
            rows = None
            continue
        rows.append((label(row.group(1)), line[row.start(2):].split()))
    return {what: [b for b in found[what] if b] for what in found}


def faith(word: str) -> str:
    """A key indicator's faith in the map's words."""
    if word.startswith("Budd"):
        return "Buddhism"
    return "Islam" if word.startswith(("Musl", "Islam")) else "Christianity"


def indicators(lines: list[str]) -> dict[str, Any]:
    """The key indicators' 2010 figures: the last number before each English label."""
    text = "\n".join(lines)
    out: dict[str, Any] = {"faiths": {}}
    if m := THAI.search(text):
        out["thai"] = m.group(1)
    for value, word in FAITH.findall(text):
        out["faiths"].setdefault(faith(word), value)
    return out


def shares(block: Block, names: dict[str, str], problems: list[str],
           what: str) -> list[dict[str, Any]]:
    """The first column of a block's rows, in the map's words; a row printed "a",
    "-" or 0.0 left out."""
    out: list[dict[str, Any]] = []
    for text, values in block:
        group = names.get(text)
        if group is None:
            problems.append(f"{what} row {text!r} is not in the table of labels")
            continue
        if any(r["group"] == group for r in out):
            problems.append(f"{what}: two rows are {group}")
            continue
        if values[0] in ("a", "-") or float(values[0]) == 0.0:
            continue
        out.append({"group": group, "pct": float(values[0])})
    return out


def first(rows: list[dict[str, Any]], group: str) -> str | None:
    pct = next((r["pct"] for r in rows if r["group"] == group), None)
    return None if pct is None else f"{pct:.1f}"


def frozen(block: Block) -> tuple:
    return tuple((text, tuple(values)) for text, values in block)


def adds_up(block: Block) -> tuple[bool, float]:
    """Whether a block's first column can be 100 once rounding is allowed for --
    each printed figure within 0.05 of its share, each "a" under 0.1 -- and the
    printed figures' sum."""
    printed = [float(values[0]) for _, values in block if values[0] not in ("a", "-")]
    small = sum(values[0] == "a" for _, values in block)
    total = round(sum(printed), 1)
    give = 0.05 * len(printed) + 1e-9
    return total - give <= 100.0 <= total + give + 0.1 * small, total


def counted(line: str) -> tuple[str, int] | None:
    """A count row's label and first figure ("-" is none)."""
    if (m := COUNT_ROW.match(line)) is None:
        return None
    return label(m.group(1)), 0 if m.group(2) == "-" else int(m.group(2).replace(",", ""))


def languages(lines: list[str]) -> dict[str, int | None] | None:
    """Table 6's first column: the people who usually speak only Thai at home,
    Thai and another language, or another language only, and as "total" the
    table's "everyone" row nearest them (None when none is near). Found by its
    rows, which no other table has, not by its heading; None until all three
    have been read."""
    for i, line in enumerate(lines):
        row = counted(line)
        if row is None or LANGUAGES.get(row[0]) != "Thai only":
            continue
        out: dict[str, int | None] = {"Thai only": row[1]}
        for other in lines[i + 1:i + 6]:
            if (row := counted(other)) is not None and row[0] in LANGUAGES:
                out.setdefault(LANGUAGES[row[0]], row[1])
        if len(out) < len(LANGUAGES):
            continue
        near = [(abs(j - i), row[1]) for j in range(max(0, i - NEAR), i + NEAR)
                if j < len(lines) and (row := counted(lines[j])) and row[0] == "ยอดรวม"]
        out["total"] = min(near)[1] if near else None
        return out
    return None


def language_shares(counts: dict[str, int | None], problems: list[str]
                    ) -> list[dict[str, Any]]:
    """Table 6's three rows as shares of the people they count, which must be
    its "everyone" row where one is near them."""
    parts = sum(counts[group] or 0 for group in LANGUAGES.values())
    total = counts.get("total") or parts
    if total <= 0 or abs(parts - total) > max(2, total // 1000):
        problems.append(f"language: table 6's rows add to {parts:,} of {total:,}")
        return []
    shares = [(group, round(100.0 * counts[group] / total, 1)) for group in LANGUAGES.values()]
    return [{"group": group, "pct": pct} for group, pct in shares if pct > 0]


def read(province: str, lines: list[str],
         copies: dict[str, tuple[str, tuple]] | None = None,
         annex: list[str] | None = None) -> Reading:
    """A report's religion and nationality, each from the block of section 1.5's
    table its key indicators bear out, or else from the indicators.

    A block stands when its Buddhist (or Thai) row is the indicators' 2010 figure,
    or within ``SLACK`` of it, and its rows add to 100 as far as rounding allows
    (``adds_up``): an exact block before a near one, an earlier before a later.
    ``copies`` names, for a composition, the province whose block is word for
    word one of this report's, and that block: it stands only on the exact
    figure. Language is table 6 of ``annex``, the report's text as far as its
    statistical annex (``lines`` when not given)."""
    copies = copies or {}
    reading = Reading(province)
    notes: list[str] = []
    found = blocks(lines, notes)
    for what, rows in FROM_PAGE.get(province, {}).items():
        if not found[what]:
            found[what] = [rows]
    reading.found = found
    key = indicators(lines)
    for what, names in (("religion", RELIGIONS), ("nationality", NATIONALITIES)):
        group, row = KEYS[what]
        printed = key["faiths"].get("Buddhism") if what == "religion" else key.get("thai")
        best: tuple[float, list[dict[str, Any]], Block] | None = None
        why = ""
        for block in found[what]:
            problems: list[str] = []
            rows = shares(block, names, problems, what)
            reading.problems.extend(p for p in problems if p not in reading.problems)
            if problems:
                continue
            table = first(rows, group)
            whole, total = adds_up(block)
            copy = copies.get(what)
            copied_here = copy is not None and copy[1] == frozen(block)
            limit = 0.0 if copied_here else SLACK
            if printed is None:
                off = 0.0
            elif table is None:
                off = math.inf
            else:
                off = round(abs(float(table) - float(printed)), 1)
            if off <= limit and whole:
                if best is None or off < best[0]:
                    best = (off, rows, block)
                continue
            if why:
                continue
            if copied_here and off <= SLACK:
                why = WHY_COPY.format(other=copy[0], row=row, table=table, printed=printed)
            elif off > limit:
                why = (WHY_MISSING.format(row=row) if table is None else
                       WHY_ROW.format(row=row, table=table, printed=printed))
            else:
                why = WHY_SUM.format(total=total)
        if best is not None:
            if printed is None:
                reading.problems.append(f"{what}: no key indicator to check the table by")
            setattr(reading, what, best[1])
            reading.raw[what] = best[2]
            setattr(reading, f"{what}_note", table_note(what, best[1]) + unknown_note(what, notes))
        elif printed is not None:
            setattr(reading, f"{what}_from", "indicators")
            setattr(reading, what, from_indicators(what, key))
            setattr(reading, f"{what}_note", indicator_note(what, why or WHY_NONE))
        else:
            reading.problems.append(f"{what}: neither a table that adds up nor key indicators")

    counts = languages(lines if annex is None else annex)
    if counts is None:
        reading.problems.append("language: no table 6 with its three rows")
    else:
        reading.language = language_shares(counts, reading.problems)
        reading.language_note = NOTE_LANGUAGE if reading.language else ""

    for what in ("religion", "nationality", "language"):
        rows = getattr(reading, what)
        total = sum(r["pct"] for r in rows)
        if rows and not 99.5 <= total <= 100.5:
            reading.problems.append(f"{what} adds to {total:.1f}")
        if rows:
            setattr(reading, f"{what}_note",
                    getattr(reading, f"{what}_note") + NOTE_SPLIT.get(province, ""))
    return reading


def unknown_note(what: str, notes: list[str]) -> str:
    """The sentence for a footnote under the table that leaves out the unknown:
    one about nationality speaks to the nationality rows alone."""
    for note in notes:
        if re.search(r"ไม่รวม.*ไม่ทราบ", note) and (what == "nationality"
                                                   or "สัญชาติ" not in note):
            return NOTE_UNKNOWN[what]
    return ""


def table_note(what: str, rows: list[dict[str, Any]]) -> str:
    group, sentence = REMAINDER[what]
    note = NOTE_RELIGION if what == "religion" else NOTE_NATIONALITY
    return note.format(remainder=sentence if any(r["group"] == group for r in rows) else "")


def from_indicators(what: str, key: dict[str, Any]) -> list[dict[str, Any]]:
    """The key indicators' figures as a composition, with what they leave of 100."""
    if what == "religion":
        rows = [{"group": g, "pct": float(v)} for g, v in key["faiths"].items()]
        residual = RESIDUAL_FAITH
    else:
        rows = [{"group": "Thai", "pct": float(key["thai"])}]
        residual = RESIDUAL_NATIONALITY
    left = round(100.0 - sum(r["pct"] for r in rows), 1)
    if left > 0:
        rows.append({"group": residual, "pct": left})
    return rows


def indicator_note(what: str, why: str) -> str:
    if what == "religion":
        return (NOTE_FROM_INDICATORS.format(what="religion", why=why)
                + NOTE_INDICATOR_FAITHS.format(residual=RESIDUAL_FAITH))
    return ("Nationality, not ethnicity: Thailand's census does not ask ethnicity. "
            + NOTE_FROM_INDICATORS.format(what="nationality", why=why)
            + NOTE_INDICATOR_NATIONALITY.format(residual=RESIDUAL_NATIONALITY))


def copied(readings: list[Reading]) -> list[tuple[str, str, str]]:
    """(province, composition, other province) for every block a reading stands
    on that is, every column alike, the block another province's stands on;
    each of the two is named."""
    seen: dict[tuple, str] = {}
    out = []
    for r in readings:
        for what, block in r.raw.items():
            other = seen.setdefault((what, frozen(block)), r.province)
            if other != r.province:
                out += [(r.province, what, other), (other, what, r.province)]
    return out


def build(readings: list[Reading], admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {fold(r.province): r for r in readings}
    out = []
    for shape in admin1:
        reading = by_name.get(fold(shape["name"].removesuffix(" Province")))
        if reading is None:
            continue
        file, capture = CAPTURES[reading.province]
        url = f"http://web.archive.org/web/{capture}/{REPORTS}{file}"
        sources, fields = [], {}
        for what, rows, note, frm in (("religion", reading.religion, reading.religion_note,
                                       reading.religion_from),
                                      ("ethnicity", reading.nationality,
                                       reading.nationality_note, reading.nationality_from),
                                      ("language", reading.language, reading.language_note,
                                       "annex")):
            if not rows:
                continue
            fields[what] = rows
            fields[f"{what}_year"] = YEAR
            fields[f"{what}_note"] = note
            name = {"table": SOURCE, "indicators": INDICATORS,
                    "annex": LANGUAGE_SOURCE}[frm].format(province=reading.province)
            sources.append({"field": what, "name": name, "url": url, "year": YEAR,
                            "license": LICENCE})
        if "ethnicity" in fields:
            fields["ethnicity_basis"] = "nationality"
        out.append(record(f"THA-CEN2010-{fold(reading.province)}", shape["name"],
                          level="admin1", parent="THA", country="THA", match_by="shape_id",
                          shape_id=shape["id"], sources=sources, **fields))
    drawn_names = {fold(s["name"].removesuffix(" Province")) for s in admin1}
    missing = sorted(r.province for r in readings if fold(r.province) not in drawn_names)
    if missing:
        raise SystemExit(f"thailand_2010: no polygon for {missing}")
    return out


def fetch(province: str) -> bytes:
    file, capture = CAPTURES[province]
    return http_get(f"http://web.archive.org/web/{capture}id_/{REPORTS}{file}",
                    binary=True, timeout=300)


def settle(texts: dict[str, Any]) -> tuple[dict[str, Reading], list[str]]:
    """Every report read; then read again, for a block it stands on that another
    report's reading stands on too, word for word, with that block held to the
    exact figure. With a line for each such block. A report's text is its lines,
    or (front, annex) as ``report_text`` gives them."""
    texts = {p: t if isinstance(t, tuple) else (t, t) for p, t in texts.items()}
    readings = {province: read(province, front, annex=annex)
                for province, (front, annex) in texts.items()}
    held: dict[str, dict[str, tuple[str, tuple]]] = {}
    for province, what, other in copied(list(readings.values())):
        held.setdefault(province, {})[what] = (other, frozen(readings[province].raw[what]))
    lines = []
    for province, copies in sorted(held.items()):
        front, annex = texts[province]
        readings[province] = read(province, front, copies, annex)
        for what, (other, block) in sorted(copies.items()):
            raw = readings[province].raw.get(what)
            stood = raw is not None and frozen(raw) == block
            lines.append(f"the {what} block of {province}'s report is {other}'s, word for "
                         "word; held to the exact figure, it "
                         + ("stands" if stood else "gives way to the key indicators"))
    return readings, lines


def show(reading: Reading, probe: bool) -> None:
    log(f"  {reading.province}: religion ({reading.religion_from}) "
        + ", ".join(f"{r['group']} {r['pct']}" for r in reading.religion)
        + f"; nationality ({reading.nationality_from}) "
        + ", ".join(f"{r['group']} {r['pct']}" for r in reading.nationality)
        + "; language " + ", ".join(f"{r['group']} {r['pct']}" for r in reading.language))
    for problem in reading.problems:
        log(f"    PROBLEM {problem}")
    if probe:
        for what, found in reading.found.items():
            for block in found:
                mark = "*" if reading.raw.get(what) is block else " "
                log(f"   {mark}{what}: " + "; ".join(f"{t} {' '.join(v)}" for t, v in block))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="print every report's blocks and indicators; write nothing")
    ap.add_argument("--only", action="append", default=[],
                    help="a province, repeatable; prints its reading and writes nothing")
    args = ap.parse_args()

    provinces = args.only or sorted(CAPTURES)
    unknown = [p for p in provinces if p not in CAPTURES]
    if unknown:
        raise SystemExit(f"thailand_2010: no report for {unknown}")
    log(f"thailand_2010: {len(provinces)} provincial reports of the 2010 census")
    texts: dict[str, tuple[list[str], list[str]]] = {}
    for province in provinces:
        started = time.monotonic()
        texts[province] = report_text(fetch(province))
        took = time.monotonic() - started
        log(f"  {province}: {len(texts[province][0])} lines, {len(texts[province][1])} "
            f"with the annex, in {took:.0f} s")
        if took > 1.0:
            time.sleep(PAUSE)                        # a fetch, not the cache
    readings, held = settle(texts)
    for province in provinces:
        show(readings[province], args.probe)
    for line in held:
        log(f"  copied: {line}")
    if args.probe:
        return 0
    if args.only:
        # The file is every report's; some of them written alone would empty the rest.
        log(f"  --only: {OUT} is not written")
        return 0
    problems = [f"{r.province}: {p}" for r in readings.values() for p in r.problems]
    if problems:
        raise SystemExit("thailand_2010: " + "; ".join(problems))
    records = build(list(readings.values()), drawn("THA", "admin1"))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records "
        f"({sum(r.religion_from == 'indicators' for r in readings.values())} religion and "
        f"{sum(r.nationality_from == 'indicators' for r in readings.values())} nationality "
        "from the key indicators)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
