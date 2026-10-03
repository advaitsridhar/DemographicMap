#!/usr/bin/env python3
"""The 2020 Russian census by federal subject: Volumes 5 and 2.

Two tables of Volume 5, both published per federal subject, both naming their
own universe in the sheet:

    Tom5_tab1  1. НАЦИОНАЛЬНЫЙ СОСТАВ НАСЕЛЕНИЯ      -> ethnicity
    Tom5_tab6  6. НАСЕЛЕНИЕ ПО РОДНОМУ ЯЗЫКУ         -> language

and one of Volume 2:

    Tom2_tab2  2. НАСЕЛЕНИЕ ПО ВОЗРАСТНЫМ ГРУППАМ И ПОЛУ
               -> population, median age, sex ratio

Volume 2's table prints each subject's everyone-counted total by sex, the
five-year groups it is made of, and Rosstat's own "Медианный возраст". The
median is Rosstat's, not one interpolated here: the office computed it from
single years, which is finer than the groups the table prints. The groups are
still read, and must add up to the total, and the median interpolated from
them must land within a year of Rosstat's -- the check that the row read is
the subject's and not its town or country population.

Not table 5. It is called ВЛАДЕНИЕ ЯЗЫКАМИ -- *proficiency*, which languages a
person knows -- and a person may know several, so its columns are independent
indicators rather than parts of one whole. Published as a composition it would
read past 100%, which is what Thailand's language file was refused for. The
native-language table is the one that partitions a population, and table 6 is
it.

**Fetched from the Internet Archive, and the citation says so.** rosstat.gov.ru
serves a valid certificate signed by the Russian Trusted Sub CA, an authority
operated by the Ministry of Digital Development that no ordinary trust store
carries -- Russian government sites moved to it after 2022. The site is not
refusing this client and this project will not disable verification to reach
it, so the files come from a public archive of the same URLs. That makes the
capture date part of the provenance: the map cites Rosstat's publication as
retrieved by the Internet Archive on the date below, not as fetched from
Rosstat today.

**Matched on ISO 3166-2, not on names.** The sheets are Cyrillic and the
boundary file is English, and norm() deliberately does not transliterate --
inventing a romanisation here would be this code guessing at a name rather
than reading one. Every subject therefore carries its ISO 3166-2 code, which
either names exactly one of the map's shapes (the codes Wikidata gives them) or
stops the run, with no fuzzy step in between where Chechnya can quietly wear
Ingushetia's figures. The row is bound to that shape by id, under the shape's
own name, with the sheet's name as an alias.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import time
from collections import Counter
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, http_get, log, measure, record,
    shares, write_json,
)

# After ._shared, which is what puts scripts/ on the path.
import canonical_groups  # noqa: E402

# Where the two workbooks live once fetched. They are checked in, which is
# this project's existing answer for a source with no reliably fetchable URL --
# Nepal's report, Sri Lanka's tables and India's C-16 workbooks are all read
# from here. Russia qualifies twice over: its own host serves a certificate no
# ordinary trust store carries, and the archive standing in for it throttles
# hard enough to answer with an HTML page. A quarterly refresh should not
# depend on an archive being in a good mood, and 2.6 MB is a small price for
# a build that does the same thing every time.
STORE = RAW / "russia"
SITE = PROCESSED.parent.parent / "site" / "data"

CAPTURE = "20250105165828"
# The "id_" suffix is the Wayback Machine's raw-content form, and it is not
# optional here. Without it the archive answers a request for a .xlsx with its
# playback wrapper -- 10 kB of "<!DOCTYPE html><title>Wayback Machine</title>"
# -- which is a valid page and a useless workbook. That was read here as rate
# limiting and written up as such four times before anyone looked at the body.
# It was never rate limiting. id_ returns 1.5 MB beginning "PK", first ask.
BASE = (f"https://web.archive.org/web/{CAPTURE}id_/"
        "https://rosstat.gov.ru/storage/mediabank/")
LANDING = ("https://rosstat.gov.ru/vpn/2020/"
           "Tom5_Nacionalnyj_sostav_i_vladenie_yazykami")

YEAR = 2021
SOURCE = ("Федеральная служба государственной статистики (Rosstat), "
          "Всероссийская перепись населения 2020 года, Том 5: Национальный "
          "состав и владение языками, retrieved via the Internet Archive "
          f"capture of {CAPTURE[:4]}-{CAPTURE[4:6]}-{CAPTURE[6:8]}")
LICENCE = "Rosstat open data"

# The sheet that names the whole country. Read as the control every other
# adapter here keeps, and never emitted: it is not a shape on this map.
COUNTRY_SHEET = "Российская Федерация"

# Sheets that exist and are deliberately not read, each for its own reason.
# Two are the *combined* forms of a subject the boundary file draws split, so
# reading them alongside their parts would count about four million people
# twice; two are territory this map already draws from Ukraine's own census.
SKIP = {
    "Архангельская область":
        "the form including Nenets AO, which is drawn separately",
    "Тюменская область":
        "the form including Khanty-Mansi and Yamalo-Nenets, drawn separately",
    "Республика Крым":
        "claimed by this file and by Ukraine's 2001 census, which this map "
        "already publishes on the same shapes",
    "г. Севастополь":
        "as Crimea, and geoBoundaries draws neither inside Russia",
}

# Sheet name -> ISO 3166-2. Written out rather than derived: a rule mapping
# Cyrillic to these codes would be a transliteration with extra steps, and
# every entry here is checkable against one published standard.
SUBJECTS = {
    "Белгородская область": "RU-BEL",
    "Брянская область": "RU-BRY",
    "Владимирская область": "RU-VLA",
    "Воронежская область": "RU-VOR",
    "Ивановская область": "RU-IVA",
    "Калужская область": "RU-KLU",
    "Костромская область": "RU-KOS",
    "Курская область": "RU-KRS",
    "Липецкая область": "RU-LIP",
    "Московская область": "RU-MOS",
    "Орловская область": "RU-ORL",
    "Рязанская область": "RU-RYA",
    "Смоленская область": "RU-SMO",
    "Тамбовская область": "RU-TAM",
    "Тверская область": "RU-TVE",
    "Тульская область": "RU-TUL",
    "Ярославская область": "RU-YAR",
    "г. Москва": "RU-MOW",
    "Республика Карелия": "RU-KR",
    "Республика Коми": "RU-KO",
    "Архангельская область без АО": "RU-ARK",
    "Ненецкий автономный округ": "RU-NEN",
    "Вологодская область": "RU-VLG",
    "Калининградская область": "RU-KGD",
    "Ленинградская область": "RU-LEN",
    "Мурманская область": "RU-MUR",
    "Новгородская область": "RU-NGR",
    "Псковская область": "RU-PSK",
    "г. Санкт-Петербург": "RU-SPE",
    "Республика Адыгея": "RU-AD",
    "Республика Калмыкия": "RU-KL",
    "Краснодарский край": "RU-KDA",
    "Астраханская область": "RU-AST",
    "Волгоградская область": "RU-VGG",
    "Ростовская область": "RU-ROS",
    "Республика Дагестан": "RU-DA",
    "Республика Ингушетия": "RU-IN",
    "Кабардино-Балкарская Республика": "RU-KB",
    "Карачаево-Черкесская Республика": "RU-KC",
    "РСО-Алания": "RU-SE",
    "Чеченская Республика": "RU-CE",
    "Ставропольский край": "RU-STA",
    "Республика Башкортостан": "RU-BA",
    "Республика Марий Эл": "RU-ME",
    "Республика Мордовия": "RU-MO",
    "Республика Татарстан": "RU-TA",
    "Удмуртская Республика": "RU-UD",
    "Чувашская Республика": "RU-CU",
    "Пермский край": "RU-PER",
    "Кировская область": "RU-KIR",
    "Нижегородская область": "RU-NIZ",
    "Оренбургская область": "RU-ORE",
    "Пензенская область": "RU-PNZ",
    "Самарская область": "RU-SAM",
    "Саратовская область": "RU-SAR",
    "Ульяновская область": "RU-ULY",
    "Курганская область": "RU-KGN",
    "Свердловская область": "RU-SVE",
    "Тюменская область без АО": "RU-TYU",
    "ХМАО": "RU-KHM",
    "ЯНАО": "RU-YAN",
    "Челябинская область": "RU-CHE",
    "Республика Алтай": "RU-AL",
    "Республика Тыва": "RU-TY",
    "Республика Хакасия": "RU-KK",
    "Алтайский край": "RU-ALT",
    "Красноярский край": "RU-KYA",
    "Иркутская область": "RU-IRK",
    "Кемеровская область - Кузбасс": "RU-KEM",
    "Новосибирская область": "RU-NVS",
    "Омская область": "RU-OMS",
    "Томская область": "RU-TOM",
    "Республика Бурятия": "RU-BU",
    "Республика Саха (Якутия)": "RU-SA",
    "Забайкальский край": "RU-ZAB",
    "Камчатский край": "RU-KAM",
    "Приморский край": "RU-PRI",
    "Хабаровский край": "RU-KHA",
    "Амурская область": "RU-AMU",
    "Магаданская область": "RU-MAG",
    "Сахалинская область": "RU-SAK",
    "Еврейская автономная область": "RU-YEV",
    "Чукотский автономный округ": "RU-CHU",
}

# The two tables do not spell every subject the same way. Table 1 writes ХМАО
# and ЯНАО; table 6 writes them out in full. Read under their own names those
# two sheets are simply unknown, and the two regions lose their language field
# without anything failing -- which is how this was nearly shipped.
ALSO_KNOWN_AS = {
    "Ханты-Мансийский АО - Югра": "ХМАО",
    "Ямало-Ненецкий АО": "ЯНАО",
}

# The map's first-order shapes are geoBoundaries, which publishes no ISO 3166-2
# column at all -- shapeName, shapeID, shapeGroup, shapeType and nothing else.
# The codes are joined on from Wikidata, which carries one for all 83 of the
# subjects configured here.
#
# All 83, which is a correction. This was written believing Wikidata had a code
# for 82 of them and that Sakha was the exception needing a name, and the
# belief was never measured; counting the codes in the adapter's own output
# gives 83, Sakha's RU-SA among them. The alias is kept anyway, as the one
# spelled-out fallback if that row ever loses its code, but it is a spare
# rather than the load-bearing part it was described as.
BY_NAME = {"RU-SA": ("Sakha Republic",)}

# The row whose figure is everyone the question reached. Both tables name it,
# which is why neither needs a denominator inferred.
UNIVERSE = {
    "ethnicity": "Указавшие национальную принадлежность",
    "language": "Указавшие родной язык",
}

TABLE = {"ethnicity": "Tom5_tab1_VPN-2020.xlsx",
         "language": "Tom5_tab6_VPN-2020.xlsx"}

# The row both tables print, outside their universe, for everyone whose form
# carries no answer ("Лица, в переписных листах которых национальная
# принадлежность не указана"; "... родной язык не указан").
UNSTATED = "Лица, в переписных листах которых"

# What each composition is a share of, and what it leaves out. The universe
# is only those who answered: 130,587,364 of the 147,182,123 counted stated a
# nationality, so about 16.6 million are outside every share, and saying so is
# the difference between "Russians are 80.9%" and "80.9% of those who
# answered".
NOTE = {
    "ethnicity": ("Nationality (национальная принадлежность) as each person stated "
                  "it in the 2020 census (reference date 1 October 2021). The shares "
                  "are of the {published:,} people in the subject who stated one; "
                  "{left:,} of the {total:,} counted ({pct:.1f}%) have no answer on "
                  "their census form and are left out. "
                  "Peoples Rosstat "
                  "lists inside another (Andi within Avars, Kryashens within Tatars) "
                  "are counted with it. Shares are rounded to 0.1, so the smallest "
                  "groups show as 0.0."),
    "language": ("Native language (родной язык) as each person stated it in the 2020 "
                 "census (reference date 1 October 2021). The shares are of the "
                 "{published:,} people in the subject who stated one; {left:,} of the "
                 "{total:,} counted ({pct:.1f}%) have no answer on their census form and "
                 "are left out. Shares are rounded to 0.1, so the "
                 "smallest languages show as 0.0."),
}

# Volume 2, table 2, from its own capture: the archive holds each file at the
# moments it was crawled, and this one was taken in October 2022.
AGE_TABLE = "Tom2_tab2_VPN-2020.xlsx"
AGE_CAPTURE = "20221003180330"
AGE_LANDING = ("https://rosstat.gov.ru/vpn/2020/"
               "Tom2_Vozrastno_polovoj_sostav_i_sostoyanie_v_brake")
AGE_SOURCE = ("Федеральная служба государственной статистики (Rosstat), "
              "Всероссийская перепись населения 2020 года, Том 2, таблица 2: "
              "Население по возрастным группам и полу, retrieved via the "
              f"Internet Archive capture of {AGE_CAPTURE[:4]}-"
              f"{AGE_CAPTURE[4:6]}-{AGE_CAPTURE[6:8]}")

# Volume 2 spells six subjects differently from Volume 5's sheet names, with
# en dashes where Volume 5 has hyphens and whole words where it abbreviates.
# Mapped onto the names SUBJECTS already keys, so one subject is one key.
AGE_NAMES = {
    "Архангельская область без автономного округа": "Архангельская область без АО",
    "Республика Северная Осетия - Алания": "РСО-Алания",
    "Ханты-Мансийский автономный округ - Югра": "ХМАО",
    "Ямало-Ненецкий автономный округ": "ЯНАО",
    "Тюменская область без автономных округов": "Тюменская область без АО",
}

# The blocks of Volume 2's table that are not subjects: the country, read as
# the control, and the eight federal districts, which are sums of subjects.
FEDERAL_DISTRICT = re.compile(r"федеральный округ$")

# The census's own count of everyone, the control every subject's total adds
# up to (with Crimea and Sevastopol, which this map does not draw here).
COUNTRY_TOTAL = 147_182_123

# How far Rosstat's median may sit from the one interpolated out of the
# five-year groups it prints. Interpolating within a five-year group assumes
# the people in it are spread evenly, which a single-year computation does
# not, so the two differ by a few tenths; a whole year apart means the row
# read is not the one the median belongs to.
MEDIAN_SLACK = 1.0

# How far the groups may sit from the universe the sheet publishes. The
# ethnicity table nests -- Авары is followed by Андийцы, Ахвахцы and Дидойцы,
# which are counted inside it -- so a reader that takes every row sums past
# the total. This is the guard that says so rather than publishing it.
TOLERANCE = 0.005


def workbook(filename: str, capture: str = CAPTURE) -> bytes:
    """The file, or a refusal that says what arrived instead.

    The check earns its place even now that BASE asks for raw content: the
    archive answers 200 either way, and an HTML page where a workbook was
    expected is a successful request for the wrong thing. http_get cannot see
    that -- from its side nothing failed -- so it belongs here, where something
    knows what was asked for. A ZIP starts "PK".

    What this guard could not do was explain itself. It refused four runs
    saying the archive was throttling, which was a guess made from a byte count
    and never checked against the body. The body said "Wayback Machine". The
    lesson kept here is that a guard which names the wrong cause is still
    better than none -- it stopped the bad file -- but that reading the
    evidence would have cost one probe instead of four runs.

    Uncached deliberately. http_get caches whatever it received, and a cached
    error page would fail every later run for a reason that had already gone
    away. Two files of about 2.6 MB once per refresh is the cheaper mistake.

    retries=1, arrived at by overshooting in both directions. http_get
    defaults to four, and four of those inside four of these multiply rather
    than add: a throttled fetch went twenty slow requests deep and ran
    seventeen minutes before it was killed. Zero then swung too far the other
    way, because a timeout is exactly the transient this layer should ride out
    and it aborted on the first one. One retry inside, four outside, and the
    outer loop owns the policy because it is the layer that can tell an error
    page from a dropped connection.
    """
    kept = STORE / filename
    if kept.exists():
        blob = kept.read_bytes()
        if blob[:2] == b"PK":
            log(f"  {filename}: {len(blob):,} bytes from {kept.parent}")
            return blob
        log(f"  {filename}: the checked-in copy is not a workbook; refetching")

    last = b""
    base = BASE.replace(CAPTURE, capture)
    for attempt in range(4):
        blob = http_get(base + filename, binary=True, cache=False,
                        retries=1, timeout=90)
        if blob[:2] == b"PK":
            STORE.mkdir(parents=True, exist_ok=True)
            kept.write_bytes(blob)
            log(f"  {filename}: {len(blob):,} bytes, kept at {kept}")
            return blob
        last = blob
        wait = 15 * (attempt + 1)
        log(f"  {filename}: {len(blob):,} bytes beginning {blob[:12]!r}, "
            f"which is not a workbook; retrying in {wait}s")
        time.sleep(wait)
    raise SystemExit(
        f"RUS: {filename} came back as {len(last):,} bytes of {last[:60]!r} "
        f"four times over, and no copy is checked in at {kept}. Read those "
        f"bytes before concluding anything about why: the last time this "
        f"fired they were the archive's playback wrapper, and the URL wanted "
        f"the id_ suffix rather than the four rounds of backoff it got.")


def number(cell: Any) -> float | None:
    """A count, or None. Rosstat writes an em dash where a group is absent."""
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).strip().replace(" ", "").replace(" ", "")
    if not text or text in {"-", "–", "—", "..."}:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def label(cell: Any) -> str:
    """The group's published name.

    The census writes a group's self-designations in brackets after its name --
    "Башкиры (башкирцы, башкорт, мин, ...)". The name is the part before them;
    the list is a glossary, not part of what to print.
    """
    text = ("" if cell is None else str(cell)).strip()
    return re.split(r"\s*\(", text, 1)[0].strip()


def indent(cell: Any) -> int:
    """How far the sheet indents this label."""
    alignment = getattr(cell, "alignment", None)
    return int((alignment.indent or 0) if alignment else 0)


def parents(rows: list[tuple[str, float, int]]) -> list[tuple[str, float]]:
    """The groups that are not counted inside another group.

    Rosstat lists constituent peoples inside the group they belong to --
    Аварцы then Андийцы, Ахвахцы, Дидойцы; Татары then Кряшены -- and adding
    those to their parent counts the same people twice.

    Which rows are which is in the indent, and it took three tries to read it.
    Leading whitespace was wrong: it missed every real sub-group and fired on
    Русские in Воронежская область, dropping the largest group in a region of
    2.2 million. "Indented at all" was wrong the other way: Rosstat indents the
    whole list one level under "в том числе:", so in Чукотский автономный округ
    that read 94 of 95 rows as nested and kept 446 people out of 47,044.

    The level that means "a group" is therefore the commonest one, not zero and
    not the smallest -- a sheet has one row per ethnicity and only a handful of
    sub-groups, so the mode is the top of the list by construction.

    Rows at exactly that level, and no others. Deeper is inside something.
    Shallower is not a member of the list at all, and the row that proves it is
    "Лица, в переписных листах которых национальная принадлежность не указана"
    -- the people who stated nothing. Counting them took ХМАО to 135% of its
    own total, because the universe this reconciles against is Указавшие
    национальную принадлежность, those who *did* state. A residual outside the
    denominator cannot be one of its parts.
    """
    if not rows:
        return []
    depths = Counter(depth for _name, _value, depth in rows)
    top = depths.most_common(1)[0][0]
    return [(name, value) for name, value, depth in rows if depth == top]


def layout(sheet: Any, wanted: str) -> tuple[int, int] | None:
    """Which column holds the label and which the count, for this sheet.

    Not columns 0 and 1. Two sheets of the 88 -- Ингушетия and Красноярский
    край -- were saved with the pivot table's member keys still in the first
    column:

        [P16_Nationality].[Hierarchy].[Code02].&[3] | Аварцы | 63

    Reading position 0 there takes the key as the label and the label as the
    count, so the universe row is never recognised, no groups are collected,
    and the subject comes out empty. Empty is the dangerous outcome: it reads
    on the map as a census that did not ask, and it is the reader that did not
    look.

    So the columns are found rather than assumed, by locating the row that
    names the universe and taking the first numeric column to its right.
    """
    for row in sheet.iter_rows(max_row=40):
        for i, cell in enumerate(row):
            if label(cell.value).startswith(wanted):
                for j in range(i + 1, len(row)):
                    if number(row[j].value) is not None:
                        return i, j
    return None


def read(blob: bytes, field: str) -> dict[str, dict[str, Any]]:
    """{sheet name: {published, counts}} for every sheet in one table."""
    import openpyxl

    # Not read_only: the indent that says which rows are nested is a style,
    # and a read-only workbook does not carry styles. Two files of a few
    # megabytes are worth the memory to read them correctly.
    book = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    wanted = UNIVERSE[field]
    out: dict[str, dict[str, Any]] = {}
    for sheet in book.sheetnames:
        key = ALSO_KNOWN_AS.get(sheet.strip(), sheet.strip())
        if key != COUNTRY_SHEET and key not in SUBJECTS and key not in SKIP:
            log(f"  unknown sheet, not read: {sheet!r}")
            continue
        where = layout(book[sheet], wanted)
        if where is None:
            raise SystemExit(
                f"RUS {field}: {sheet} has no row naming {wanted!r}. Every "
                f"other sheet in this file does, so this is a layout this "
                f"reader has not seen rather than a question the region was "
                f"not asked.")
        at_name, at_value = where
        published: float | None = None
        unstated: float | None = None
        seen: list[tuple[str, float, int]] = []
        for row in book[sheet].iter_rows():
            if len(row) <= at_value:
                continue
            name = label(row[at_name].value)
            if not name:
                continue
            if published is None:
                if name.startswith(wanted):
                    published = number(row[at_value].value)
                continue
            if name.startswith("в том числе"):
                continue
            value = number(row[at_value].value)
            if value is None:
                continue
            # The people who gave no answer, outside the universe: kept for
            # the note, which says how many the shares leave out.
            if name.startswith(UNSTATED):
                unstated = (unstated or 0.0) + value
            seen.append((name, value, indent(row[at_name])))
        counts: dict[str, float] = {}
        for name, value in parents(seen):
            counts[name] = counts.get(name, 0.0) + value
        out[key] = {"published": published, "counts": counts, "unstated": unstated,
                    "nested": len(seen) - len(parents(seen))}
    book.close()
    return out


def check(field: str, tables: dict[str, dict[str, Any]]) -> None:
    """Refuse a table this reader has misunderstood, and say which way."""
    worst = None
    for sheet, got in tables.items():
        published, counts = got["published"], got["counts"]
        if not published or not counts:
            continue
        ratio = sum(counts.values()) / published
        if worst is None or abs(ratio - 1) > abs(worst[1] - 1):
            worst = (sheet, ratio)
    if worst is None:
        raise SystemExit(f"RUS {field}: no sheet published a universe")
    sheet, ratio = worst
    off = abs(ratio - 1)
    got = tables[sheet]
    # The largest groups, because the first time this fired the whole story was
    # that Русские was missing from them and the ratio alone did not say so. A
    # sum that is wrong is usually wrong about something nameable.
    top = ", ".join(f"{name} {value:,.0f}" for name, value
                    in sorted(got["counts"].items(), key=lambda kv: -kv[1])[:3])
    log(f"  {field}: furthest from its own total is {sheet} at "
        f"{ratio:.4f} of {UNIVERSE[field]!r} ({got['published']:,.0f}); "
        f"largest {top}; {got['nested']} nested rows left to their parents")
    if off > TOLERANCE:
        raise SystemExit(
            f"RUS {field}: {sheet} sums to {ratio:.4f} of the "
            f"{got['published']:,.0f} the sheet publishes, past the "
            f"{TOLERANCE:.1%} this reader allows. Its largest groups came out "
            f"as {top} -- check whether one that belongs there is missing "
            f"before assuming the nesting is wrong, because that is what it "
            f"was last time.")


GROUP = re.compile(r"^(\d+)\s*[–—-]\s*(\d+)$")
OPEN_GROUP = re.compile(r"^(\d+)\s+и\s+более$")


def dashes(text: str) -> str:
    """One spelling of a name: en and em dashes as hyphens, spaces single."""
    return " ".join(re.sub(r"\s*[–—]\s*", " - ", text).split())


def ages(blob: bytes) -> dict[str, dict[str, Any]]:
    """{subject: total, men, women, groups, median} from Volume 2's table 2.

    Each block opens with the subject's name on a row of its own, then
    "Городское и сельское население" -- everyone -- with the groups under it,
    then the same again for the urban and the rural population. Only the
    first, everyone, is read; a subject's block ends at the next name.
    """
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = book.worksheets[0]
    out: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    reading = False
    for row in sheet.iter_rows(values_only=True):
        name = dashes(str(row[0] or "").strip())
        values = [number(c) for c in row[1:4]]
        if not name:
            continue
        if all(v is None for v in values) and (
                name == COUNTRY_SHEET or FEDERAL_DISTRICT.search(name)
                or AGE_NAMES.get(name, name) in SUBJECTS or name in SKIP
                or AGE_NAMES.get(name, name) in {dashes(s) for s in SUBJECTS}):
            key = AGE_NAMES.get(name, name)
            key = next((s for s in SUBJECTS if dashes(s) == key), key)
            if key in out:
                raise SystemExit(f"RUS ages: {name!r} opens two blocks")
            current = out[key] = {"groups": [], "total": None, "men": None,
                                  "women": None, "median": None}
            reading = False
            continue
        if current is None:
            continue
        # A block opens with everyone. The three cities of federal
        # significance have no rural population and open with "Городское
        # население" instead, which for them is everyone; the country and its
        # subjects adding up is what says it was read as such.
        if (name in {"Городское и сельское население", "Городское население"}
                and current["total"] is None):
            current["total"], current["men"], current["women"] = values
            reading = True
            continue
        if name in {"Городское население", "Сельское население"}:
            reading = False
            continue
        if not reading:
            continue
        closed, open_ = GROUP.match(name), OPEN_GROUP.match(name)
        if closed:
            current["groups"].append((int(closed.group(1)), int(closed.group(2)),
                                      values[0] or 0.0))
        elif open_:
            current["groups"].append((int(open_.group(1)), None, values[0] or 0.0))
        elif name == "Медианный возраст":
            current["median"] = values[0]
            reading = False
    book.close()
    return out


def grouped(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median interpolated within its five-year group; the check on Rosstat's."""
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0.0
    for low, high, people in sorted(groups, key=lambda g: g[0]):
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def check_ages(table: dict[str, dict[str, Any]]) -> None:
    """Every subject's groups make its total, its sexes too, and the country adds up."""
    missing = [s for s in SUBJECTS if s not in table]
    if missing:
        raise SystemExit(f"RUS ages: {len(missing)} configured subjects have no block "
                         f"in {AGE_TABLE}: {', '.join(missing[:6])}")
    worst = (None, 0.0)
    for name, got in table.items():
        total, men, women, median = (got["total"], got["men"], got["women"],
                                     got["median"])
        if not total or men is None or women is None or median is None:
            raise SystemExit(f"RUS ages: {name}: no total, sexes or median read")
        made = sum(n for _, _, n in got["groups"])
        if abs(made - total) > 0.5 or abs(men + women - total) > 0.5:
            raise SystemExit(
                f"RUS ages: {name}: the groups make {made:,.0f} and the sexes "
                f"{men + women:,.0f}, against a total of {total:,.0f}")
        mine = grouped(got["groups"])
        off = abs((mine or 0) - median)
        if mine is None or off > MEDIAN_SLACK:
            raise SystemExit(
                f"RUS ages: {name}: Rosstat's median is {median} and the groups "
                f"give {mine}; a year apart means this is not the row it goes with")
        if off > worst[1]:
            worst = (name, off)
    country = table[COUNTRY_SHEET]["total"]
    if country != COUNTRY_TOTAL:
        raise SystemExit(f"RUS ages: the country's block reads {country:,.0f}, not "
                         f"the census's {COUNTRY_TOTAL:,}")
    # The subjects the census counts, once each: the configured 83, which hold
    # Arkhangelsk and Tyumen without their okrugs, and Crimea and Sevastopol.
    summed = sum(table[s]["total"] for s in SUBJECTS) + sum(
        table[s]["total"] for s in ("Республика Крым", "г. Севастополь"))
    if summed != country:
        raise SystemExit(f"RUS ages: the subjects make {summed:,.0f}, the country "
                         f"{country:,.0f}")
    log(f"  ages: {len(SUBJECTS)} subjects' groups and sexes make their totals, the "
        f"subjects make the country's {country:,.0f}; Rosstat's median and the "
        f"grouped one are furthest apart in {worst[0]}, by {worst[1]:.1f} years")


def age_fields(got: dict[str, Any]) -> dict[str, Any]:
    """The three figures one subject carries from Volume 2."""
    men, women = got["men"], got["women"]
    return {
        "population": measure(int(got["total"]), year=YEAR, source=AGE_SOURCE),
        "population_note": ("Everyone the 2020 census counted in the subject "
                            "(reference date 1 October 2021)."),
        "median_age": measure(got["median"], unit="years", year=YEAR,
                              source=AGE_SOURCE),
        "median_age_note": ("Rosstat's own median age for the subject, as "
                            "Volume 2 publishes it (\"Медианный возраст\"), "
                            "everyone counted by the 2020 census."),
        "sex_ratio": measure(round(100 * men / women, 1),
                             unit="males_per_100_females", year=YEAR,
                             source=AGE_SOURCE),
        "sex_ratio_note": (f"{int(men):,} men and {int(women):,} women counted "
                           "by the 2020 census."),
    }


def englished(field: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rosstat's group names, in the language the rest of the map is in.

    Every other adapter here emits English already -- Ukraine's oblasts
    publish "Romanian", not "румунська" -- and Russia was the exception, so
    83 subjects read "Русские 90.2%" and the world filter offered "Русские"
    as a different answer from the "Russian" it already had from Estonia,
    Latvia and Lithuania. The same people, counted by four censuses, split
    across two alphabets.

    Translating a group is not the romanisation this adapter refuses. That
    refusal is about matching a *shape*: an invented English spelling of a
    place name attaches real figures to the wrong region and nothing on the
    map shows it, which is why subjects are matched on their ISO code. A group
    name is the label a bar carries, and these are declared one at a time in
    canonical_groups rather than transliterated by rule.

    An unknown label stops the run. It would otherwise reach the map in
    Cyrillic, and one untranslated row among translated ones reads as a
    different kind of thing rather than as the gap in a table that it is.
    """
    out = []
    for row in rows:
        name = canonical_groups.translate_russian(field, row["group"])
        if name is None:
            raise SystemExit(
                f"{field}: no English name for {row['group']!r}. Rosstat "
                f"publishes a group this build has never seen; add it to "
                f"canonical_groups.RUSSIAN_{field.upper()} rather than "
                f"letting one Cyrillic label through a translated chart.")
        out.append({**row, "group": name})
    return out


def universe_note(field: str, got: dict[str, Any], total: float) -> str:
    """What a subject's composition is a share of, and how many it leaves out.

    The people with no answer are the subject's count less those who stated
    one; where the sheet prints its own row for them, the two must agree, or
    the count and the universe are not the same people.
    """
    published = got["published"] or sum(got["counts"].values())
    left = total - published
    if left < 0:
        raise SystemExit(f"RUS {field}: {published:,.0f} stated an answer, more than "
                         f"the {total:,.0f} counted")
    if got.get("unstated") is not None and abs(got["unstated"] - left) > 0.5:
        raise SystemExit(f"RUS {field}: the sheet's row of people with no answer holds "
                         f"{got['unstated']:,.0f}, the count less those who answered "
                         f"{left:,.0f}")
    return NOTE[field].format(published=int(published), left=int(left), total=int(total),
                              pct=100 * left / total)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="russia_subject.json")
    args = ap.parse_args()

    fields: dict[str, dict[str, dict[str, Any]]] = {}
    for field, filename in TABLE.items():
        if fields:
            # A courtesy pause between two multi-megabyte requests to a free
            # public archive. Not a workaround for anything: the wrapper this
            # once seemed to be evidence of was a URL mistake, not a limit.
            time.sleep(5)
        blob = workbook(filename)
        log(f"{field}: {filename}, {len(blob):,} bytes")
        fields[field] = read(blob, field)
        check(field, fields[field])

    time.sleep(5)
    blob = workbook(AGE_TABLE, AGE_CAPTURE)
    log(f"ages: {AGE_TABLE}, {len(blob):,} bytes")
    table = ages(blob)
    check_ages(table)

    # The shape each code names, looked up here rather than left to the
    # build's code pass. That pass refuses a row answering a question the
    # shape has already been answered on, which is right for two sources
    # matched two ways -- but Wikidata's fill-only population is on every
    # shape before the code pass runs, so once this file carried the census
    # count the pass refused 82 of the 83 rows whole, ethnicity and language
    # with them. A row bound to its shape is merged like any other, and the
    # census count replaces the encyclopaedia's, which is the order the build
    # keeps everywhere else.
    units = json.loads((SITE / "admin1" / "RUS.units.json").read_text())
    by_code: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        if isinstance(unit.get("iso_3166_2"), str):
            by_code.setdefault(unit["iso_3166_2"], []).append(unit)
    unbound = {code: len(by_code.get(code, [])) for code in SUBJECTS.values()
               if len(by_code.get(code, [])) != 1}
    if unbound:
        raise SystemExit(f"RUS: these codes name no shape or several: {unbound}")

    records = []
    for sheet, code in SUBJECTS.items():
        unit = by_code[code][0]
        values: dict[str, Any] = {}
        for field in TABLE:
            got = fields[field].get(sheet)
            if not got or not got["counts"]:
                values[field] = gap(NOT_AVAILABLE)
                continue
            values[field] = englished(
                field, shares(got["counts"], total=got["published"] or None))
            values[f"{field}_year"] = YEAR
            values[f"{field}_note"] = universe_note(field, got, table[sheet]["total"])
        records.append(record(
            code, unit["name"], level="admin1", parent="RUS",
            country="RUS", iso_3166_2=code,
            # These sheets are Cyrillic and the shapes English, so the name
            # pass cannot settle them: the row is bound to the shape its code
            # names, and keeps the sheet's own name as an alias.
            match_by="shape_id", shape_id=unit["id"],
            aliases=[sheet, *BY_NAME.get(code, ())],
            **values,
            **age_fields(table[sheet]),
            sources=[{"field": field, "name": SOURCE, "url": LANDING,
                      "license": LICENCE, "year": YEAR} for field in TABLE]
            + [{"field": field, "name": AGE_SOURCE, "url": AGE_LANDING,
                "license": LICENCE, "year": YEAR}
               for field in ("population", "median_age", "sex_ratio")],
        ))

    # Every table, not just the first. Checking one of them let ХМАО and ЯНАО
    # through with ethnicity and no language, because table 6 spells their
    # names out where table 1 abbreviates: a subject present in one file and
    # absent from another is exactly the gap that looks like a country simply
    # not answering that question.
    for field in TABLE:
        # Present *and* read. A sheet that exists and yields nothing is the
        # same gap as a sheet that is absent, and it looks identical on the
        # map to a census that did not ask -- which is how Ингушетия and
        # Красноярский край nearly shipped empty.
        missing = [s for s in SUBJECTS
                   if not (fields[field].get(s) or {}).get("counts")]
        if missing:
            raise SystemExit(
                f"RUS {field}: {len(missing)} of {len(SUBJECTS)} configured "
                f"subjects came out empty from {TABLE[field]}: "
                + ", ".join(missing[:6])
                + ". A subject this file does not carry is a gap for that "
                  "field alone, which reads on the map as a question the "
                  "region was not asked.")
    path = PROCESSED / args.out
    write_json(path, records)
    log(f"  wrote {path} ({path.stat().st_size // 1024} kB)")
    log(f"  {len(records)} subjects, {len(SKIP)} sheets skipped by name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
