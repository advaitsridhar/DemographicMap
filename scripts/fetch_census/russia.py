#!/usr/bin/env python3
"""The 2020 Russian census, Volume 5: ethnic composition and native language.

Two tables, both published per federal subject, both naming their own universe
in the sheet:

    Tom5_tab1  1. НАЦИОНАЛЬНЫЙ СОСТАВ НАСЕЛЕНИЯ      -> ethnicity
    Tom5_tab6  6. НАСЕЛЕНИЕ ПО РОДНОМУ ЯЗЫКУ         -> language

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
either matches a shape's code or does not, with no fuzzy step in between where
Chechnya can quietly wear Ingushetia's figures. One shape, Sakha, carries no
code in the boundary file and is aliased by name instead.
"""

from __future__ import annotations

import argparse
import io
import re
import time
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, shares, write_json,
)

CAPTURE = "20250105165828"
BASE = (f"https://web.archive.org/web/{CAPTURE}/"
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

# geoBoundaries carries an iso_3166_2 on 82 of Russia's 83 first-order shapes.
# Sakha is the exception, so it is the one subject matched by name.
BY_NAME = {"RU-SA": ("Sakha Republic",)}

# The row whose figure is everyone the question reached. Both tables name it,
# which is why neither needs a denominator inferred.
UNIVERSE = {
    "ethnicity": "Указавшие национальную принадлежность",
    "language": "Указавшие родной язык",
}

TABLE = {"ethnicity": "Tom5_tab1_VPN-2020.xlsx",
         "language": "Tom5_tab6_VPN-2020.xlsx"}

# How far the groups may sit from the universe the sheet publishes. The
# ethnicity table nests -- Авары is followed by Андийцы, Ахвахцы and Дидойцы,
# which are counted inside it -- so a reader that takes every row sums past
# the total. This is the guard that says so rather than publishing it.
TOLERANCE = 0.005


def workbook(filename: str) -> bytes:
    """The file, or a refusal that says what arrived instead.

    The Internet Archive throttles, and it does not do so with a status code:
    it answers 200 with an HTML error page. http_get retries network errors and
    5xx and is right not to touch this one -- from its side the request
    succeeded. So the check belongs here, where something knows the response is
    supposed to be a workbook: a ZIP starts "PK", and 10 kB where 1.6 MB was
    expected is a page saying no.

    Uncached deliberately. http_get caches whatever it received, and a cached
    error page would fail every later run for a reason that had already gone
    away. Two files of about 2.6 MB once per refresh is the cheaper mistake.
    """
    last = b""
    for attempt in range(4):
        blob = http_get(BASE + filename, binary=True, cache=False)
        if blob[:2] == b"PK":
            return blob
        last = blob
        wait = 15 * (attempt + 1)
        log(f"  {filename}: {len(blob):,} bytes beginning {blob[:12]!r}, "
            f"which is not a workbook -- the archive is throttling; "
            f"retrying in {wait}s")
        time.sleep(wait)
    raise SystemExit(
        f"RUS: {filename} came back as {len(last):,} bytes of "
        f"{last[:60]!r} four times over. That is the archive refusing, not "
        f"a file that has moved: the capture is named in this module and can "
        f"be checked by hand.")


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


def label(cell: Any) -> tuple[str, bool]:
    """The group's published name, and whether the sheet indents it.

    Rosstat nests constituent peoples under the group they are counted in, and
    marks them by indenting the label. Returning that fact separately is what
    lets the reader add up the parents alone; the alternative is a hand-written
    list of which peoples are inside which, which would be this code asserting
    an ethnography rather than reading a spreadsheet.
    """
    raw = "" if cell is None else str(cell)
    text = raw.strip()
    # The census writes a group's self-designations in brackets after its
    # name -- "Башкиры (башкирцы, башкорт, мин, ...)". The name is the part
    # before them; the list is a glossary, not part of what to print.
    name = re.split(r"\s*\(", text, 1)[0].strip()
    indented = bool(raw) and raw[0] in " \t " and bool(text)
    return name, indented


def read(blob: bytes, field: str) -> dict[str, dict[str, Any]]:
    """{sheet name: {published, counts}} for every sheet in one table."""
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                  data_only=True)
    wanted = UNIVERSE[field]
    out: dict[str, dict[str, Any]] = {}
    for sheet in book.sheetnames:
        key = sheet.strip()
        if key != COUNTRY_SHEET and key not in SUBJECTS and key not in SKIP:
            log(f"  unknown sheet, not read: {sheet!r}")
            continue
        rows = list(book[sheet].iter_rows(values_only=True))
        published: float | None = None
        counts: dict[str, float] = {}
        nested = 0
        for row in rows:
            if not row:
                continue
            name, indented = label(row[0])
            if not name:
                continue
            if published is None:
                if name.startswith(wanted):
                    published = number(row[1])
                continue
            if name.startswith("в том числе"):
                continue
            value = number(row[1])
            if value is None:
                continue
            # A nested row's count is already inside its parent's.
            if indented:
                nested += 1
                continue
            counts[name] = counts.get(name, 0.0) + value
        out[key] = {"published": published, "counts": counts, "nested": nested}
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
    log(f"  {field}: furthest from its own total is {sheet} at "
        f"{ratio:.4f} of {UNIVERSE[field]!r}"
        + (f", and {tables[sheet]['nested']} nested rows were left to their "
           f"parents" if tables[sheet]["nested"] else ""))
    if off > TOLERANCE:
        raise SystemExit(
            f"RUS {field}: {sheet} sums to {ratio:.4f} of the universe the "
            f"sheet publishes, past the {TOLERANCE:.1%} this reader allows. "
            f"A sheet that does not add up is one this reader has "
            f"misunderstood -- most likely which rows are nested inside "
            f"which.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="russia_subject.json")
    args = ap.parse_args()

    fields: dict[str, dict[str, dict[str, Any]]] = {}
    for field, filename in TABLE.items():
        if fields:
            # Two large files back to back is what tips the archive into
            # throttling, and waiting is cheaper than retrying.
            time.sleep(10)
        blob = workbook(filename)
        log(f"{field}: {filename}, {len(blob):,} bytes")
        fields[field] = read(blob, field)
        check(field, fields[field])

    records = []
    for sheet, code in SUBJECTS.items():
        values: dict[str, Any] = {}
        for field in TABLE:
            got = fields[field].get(sheet)
            if not got or not got["counts"]:
                values[field] = gap(NOT_AVAILABLE)
                continue
            values[field] = shares(
                got["counts"], total=got["published"] or None)
        records.append(record(
            code, sheet, level="admin1", parent="RUS",
            country="RUS", iso_3166_2=code,
            aliases=list(BY_NAME.get(code, ())),
            **values,
            sources=[{"field": field, "name": SOURCE, "url": LANDING,
                      "license": LICENCE, "year": YEAR} for field in TABLE],
        ))

    missing = [s for s in SUBJECTS if s not in fields["ethnicity"]]
    if missing:
        raise SystemExit(
            f"RUS: {len(missing)} configured subjects have no sheet: "
            + ", ".join(missing[:5]))
    path = PROCESSED / args.out
    write_json(path, records)
    log(f"  wrote {path} ({path.stat().st_size // 1024} kB)")
    log(f"  {len(records)} subjects, {len(SKIP)} sheets skipped by name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
