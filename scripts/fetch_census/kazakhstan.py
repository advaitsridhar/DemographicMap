#!/usr/bin/env python3
"""Kazakhstan: ethnicity by region and district, from the Bureau's start-of-2025 tables.

The Bureau of National Statistics publishes "Population by ethnic groups of
the Republic of Kazakhstan" every March (series 18, Demographic statistics):
one workbook with the country by region on one sheet and, on a sheet per
region, that region by district and city akimat, 73 ethnic rows each. Its
site is an application that offers no file link a reader can follow, so the
workbook is committed under ``data/raw/kazakhstan/`` and read from disk, as
India's and Sri Lanka's are. The copy here is the 27 March 2025 edition,
population at 1 January 2025.

**What it is and is not.** These are the Bureau's register-based population
figures carried forward from the 2021 census, not a census count; the record
says so in its year and note. They are the only ethnicity by district the
Bureau publishes at all, and the only ethnicity by region a reader can reach.

**Regions: 20 in the workbook, 16 on the map.** The boundary file draws the
2017 layout. Since then Shymkent left South Kazakhstan (2018) and Abai,
Jetisu and Ulytau were carved out of East Kazakhstan, Almaty Region and
Karaganda (2022), each a clean partition of the old region. The workbook
gives counts, so the four pairs are summed into the shapes they came from,
which is exact, and every group's total is checked against the workbook's
own "Всего" row before and after.

**Districts.** The district sheets name their units in Russian; the boundary
file carries a Latin transliteration of the same adjectival names
("Атбасарский район" is drawn as "Atbasarskiy"). Each district record keeps
the Bureau's Cyrillic name and carries a transliteration as an alias, which
matches most of them by name within their region. The boundary file is older
than several renamings, so ``RENAMED`` declares those the map knows under
their previous name (Zelenovskiy is today's Bäiterek District, Tselinniy is
Gabit Musrepov District, and so on) -- each a renaming of the same unit, not a
redrawing. Districts the file draws under a name this adapter cannot settle
stay as visible gaps. Districts inside the three cities of republican
significance are not emitted: the map draws each city as one shape, and that
shape gets the city's total.

Usage:
    python -m scripts.fetch_census.kazakhstan
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, log, measure, record, shares, write_json,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import canonical_groups  # noqa: E402

WORKBOOK = RAW / "kazakhstan" / "ethnic-groups-2025.xlsx"
OUT = {"admin1": "kazakhstan_oblast.json", "admin2": "kazakhstan_district.json"}
YEAR = 2025
SOURCE = ("Bureau of National Statistics of Kazakhstan, 'Population by ethnic groups of "
          "the Republic of Kazakhstan at the start of 2025' (series 18, Demographic "
          "statistics, published 27 March 2025)")
PAGE = "https://stat.gov.kz/ru/industries/social-statistics/stat-demography/"
LICENCE = "Official statistics of the Bureau of National Statistics; free to use with attribution"
NOTE = ("Register-based population at 1 January 2025, carried forward from the 2021 "
        "census; not a census count. Read from the Bureau's workbook.")
EXPECTED = {"admin1": 16}
COUNTRY_SHEET = "РКобл"

# Workbook column (2022 layout) -> boundary shape (2017 layout). Four shapes
# are the sum of two columns: the region a new one was carved out of, plus it.
REGIONS: dict[str, str] = {
    "Абай": "East Kazakhstan Region",
    "Восточно-Казахстанская": "East Kazakhstan Region",
    "Акмолинская": "Akmola Region",
    "Актюбинская": "Aktobe Region",
    "Алматинская": "Almaty Region",
    "Жетісу": "Almaty Region",
    "Атырауская": "Atyrau Region",
    "Западно-Казахстанская": "West Kazakhstan Region",
    "Жамбылская": "Jambyl Region",
    "Карагандинская": "Karaganda Region",
    "Ұлытау": "Karaganda Region",
    "Костанайская": "Kostanay Region",
    "Кызылординская": "Kyzylorda Region",
    "Мангистауская": "Mangystau Region",
    "Павлодарская": "Pavlodar Region",
    "Северо-Казахстанская": "North Kazakhstan Region",
    "Туркестанская": "South Kazakhstan Region",
    "г.Шымкент": "South Kazakhstan Region",
    "г.Астана": "Astana",
    "г.Алматы": "Almaty",
}
# Cities of republican significance: the map draws Almaty and Shymkent as
# one second-level shape each (Astana has none), so their region-level total
# is also published as that shape, under the boundary file's name.
CITY_SHAPES = {"г.Алматы": ("Almaty (Alma-Ata)", "Almaty"),
               "г.Шымкент": ("Shymkent", "South Kazakhstan Region")}
CITY_SHEETS = {"г.Астана", "г.Алматы", "г.Шымкент"}

# The boundary file's spelling where a straight transliteration does not
# reach it: the file's typos, its BGN-style "Dzh"/"q" spellings, and the
# districts it still draws under a name since replaced (same unit, renamed).
RENAMED: dict[str, list[str]] = {
    "Астраханский район": ["Astrakhansiy"],
    "Ерейментауский район": ["Ereymengauskiy"],
    "Федоровский район": ["Fyodorovskiy"],
    "Жангалинский район": ["Dzhangalinskiy"],
    "Жанибекский район": ["Dzhanybekskiy"],
    "Жангельдинский район": ["Dzhangildinskiy"],
    "Кармакшинский район": ["Karmakchinskiy"],
    "Чиилийский район": ["Shieliyskiy"],
    "Щербактинский район": ["Sherbaktinskiy"],
    "Тайыншинский район": ["Taiynshinskiy"],
    "Тюлькубасский район": ["Tyulkubaskiy"],
    "Шардаринский район": ["Chardarinskiy"],
    "Мангистауский район": ["Manghystauskiy"],
    "Райымбекский район": ["Raiymbekskiy"],
    "Район Байдибека": ["Baydibekskiy"],
    "Жуалынский район": ["Zhualy"],
    "Актау г.а.": ["Aqtau"],
    "город Актобе": ["Aqtobe"],
    "город Костанай": ["Qostanay"],
    "Кызылорда г.а.": ["Qyzylorda"],
    "Талдыкорган г.а.": ["Taldyqorghan"],
    "Риддер г.а.": ["Leninogorsk"],                 # Leninogorsk, renamed Ridder 2002
    "район Алтай": ["Zyryanovsk"],                  # Zyryanovsk District, renamed 2019
    "Бурабайский район": ["Shuchinskiy"],           # Shchuchinsk District, renamed 2009
    "район Биржан сал": ["Enbekshilderskiy"],       # Enbekshilder District, renamed 2018
    "Район Турара Рыскулова": ["Lugovskoy"],        # Lugovoy District, renamed 2003
    "Аккайынский район": ["Sovetskiy"],             # Sovetsky District, renamed 1997
    "Район Магжана Жумабаева": ["Bulaevskiy"],      # Bulaevo District, renamed 2000
    "Район Им.Габита Мусрепова": ["Tselinniy"],     # Tselinny District, renamed 2000
    "район Бәйтерек": ["Zelenovskiy"],              # Zelenov District, renamed 2019
    "Бокейординский район": ["Urdinskiy"],          # Urda District, renamed 1990s
    "район Беимбета Майлина": ["Taranovskiy"],      # Taranovsky District, renamed 2018
    "район Тереңкөл": ["Kachirskiy"],               # Kachiry District, renamed 2018
    "район Аққулы": ["Lebyazhinskiy"],              # Lebyazhye District, renamed 2018
    "Сырдарьинский район": ["Terenozekskiy"],       # its seat Terenozek names the shape
    # City akimats the file draws under the district or city name they
    # replaced: Semipalatinsk became Semey in 2007; Aksu's and Arys's rural
    # districts were folded into their city akimats.
    "Семей г.а.": ["Semipalatinskiy"],
    "Аксу г.а.": ["Aksuskiy"],
    "Арысь г.а.": ["Arysskiy"],
}

# Beyond the Rosstat table: the Bureau's spellings and its residual rows.
LABELS = {
    "Кыргызы": "Kyrgyz", "Латышы": "Latvian", "Саха(Якуты)": "Yakut",
    "Татары крымские": "Crimean Tatar", "Народы Индии и Пакистана": "Peoples of India and Pakistan",
    "Англичане": "English", "Белуджи": "Baloch", "Евреи грузинские": "Georgian Jewish",
    "Талышы": "Talysh",
    "Не указавшие": "Not stated", "Другие национальности": "Other",
}

CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i",
}
GENERIC = re.compile(r"(г\.а\.|Г\.А\.|город|\bг\.|район|Район)")


def transliterate(text: str) -> str:
    out = []
    for ch in text:
        t = CYRILLIC.get(ch.lower())
        out.append(ch if t is None else (t.capitalize() if ch.isupper() else t))
    return "".join(out)


def bare(district: str) -> str:
    """'Аккольский район' -> 'Аккольский'; 'Кокшетау г.а.' -> 'Кокшетау'."""
    return " ".join(GENERIC.sub(" ", district).split())


def label(russian: str) -> str:
    shown = LABELS.get(russian) or canonical_groups.RUSSIAN_ETHNICITY.get(russian)
    if not shown:
        raise SystemExit(f"kazakhstan: no English label for {russian!r}; add it to LABELS")
    return shown


def count(cell: Any) -> int | None:
    if cell is None or cell in ("-", "х", "x", "...", "…"):
        return None if cell in ("х", "x", "...", "…") else 0
    if isinstance(cell, (int, float)):
        return int(cell)
    return int(str(cell).replace(" ", "").replace(",", "") or 0)


def parse_sheet(rows: list[tuple[Any, ...]]) -> tuple[list[str], dict[str, dict[str, int]]]:
    """(unit names in column order, {unit: {russian label: count}}) from one sheet.

    The header row is the one whose third cell is "Этносы"; the unit names
    are on it from the fifth column, or on the next row when the sheet puts
    "В том числе" there (the country sheet does). A cell of "х" (confidential)
    or "..." is left out of the unit's counts.
    """
    rows = [tuple(r) for r in rows]
    for i, row in enumerate(rows):
        if len(row) > 2 and str(row[2] or "").strip() == "Этносы":
            names_row = rows[i + 1] if str(row[4] or "").strip().startswith("В том числе") else row
            first = i + 2 if names_row is not row else i + 1
            break
    else:
        raise SystemExit("kazakhstan: no header row with 'Этносы'; the workbook changed shape")
    # "г. Астана" on one sheet and "г.Астана" on another are one city.
    units = [re.sub(r"^г\.\s+", "г.", " ".join(str(c).split()))
             for c in names_row[4:] if c is not None and str(c).strip()]
    counts: dict[str, dict[str, int]] = {u: {} for u in units}
    for row in rows[first:]:
        if len(row) < 4 or row[2] is None:
            continue
        russian = str(row[2]).strip()
        for j, unit in enumerate(units):
            n = count(row[4 + j]) if 4 + j < len(row) else 0
            if n is not None:
                counts[unit][russian] = n
    return units, counts


def bars(name: str, counts: dict[str, int]) -> Any:
    total = counts.get("Всего")
    if not total:
        return gap(NOT_AVAILABLE)
    groups: dict[str, int] = {}
    for russian, n in counts.items():
        if russian == "Всего" or not n:
            continue
        shown = label(russian)
        groups[shown] = groups.get(shown, 0) + n
    summed = sum(groups.values())
    if abs(summed - total) > max(0.005 * total, 5):
        raise SystemExit(f"kazakhstan: {name} sums to {summed:,} against the total {total:,}")
    return shares(groups, total=total)


def merged(counts: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """The workbook's 20 columns summed into the 16 shapes."""
    out: dict[str, dict[str, int]] = {}
    for column, shape in REGIONS.items():
        if column not in counts:
            raise SystemExit(f"kazakhstan: column {column!r} is missing from the country sheet")
        target = out.setdefault(shape, {})
        for russian, n in counts[column].items():
            target[russian] = target.get(russian, 0) + n
    return out


def region_id(shape: str) -> str:
    from common import slugify
    return f"KAZ-{slugify(shape)}"


def build(workbook: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"admin1": [], "admin2": []}
    units, counts = parse_sheet(list(workbook[COUNTRY_SHEET].iter_rows(values_only=True)))
    log(f"  {COUNTRY_SHEET}: {len(units)} columns, {len(next(iter(counts.values())))} rows")
    if set(units) != set(REGIONS):
        raise SystemExit(f"kazakhstan: the country sheet's columns changed: "
                         f"{sorted(set(units) ^ set(REGIONS))}")
    src = [{"field": "population/ethnicity", "name": SOURCE, "url": PAGE, "license": LICENCE}]
    for shape, groups in merged(counts).items():
        out["admin1"].append(record(
            region_id(shape), shape, level="admin1", parent="KAZ", country="KAZ",
            population=measure(groups["Всего"], year=YEAR, source=SOURCE),
            ethnicity=bars(shape, groups), ethnicity_note=f"{SOURCE}. {NOTE}", sources=src,
        ))
    for column, (shape, region) in CITY_SHAPES.items():
        out["admin2"].append(record(
            f"{region_id(region)}-{column.lstrip('г.').lower()}", shape, level="admin2",
            parent=region_id(region), parent_name=region, country="KAZ",
            population=measure(counts[column]["Всего"], year=YEAR, source=SOURCE),
            ethnicity=bars(shape, counts[column]), ethnicity_note=f"{SOURCE}. {NOTE}",
            sources=src,
        ))
    for column, region in REGIONS.items():
        if column in CITY_SHEETS:
            continue
        sheet = column.replace("г.", "").strip()
        if sheet not in workbook.sheetnames:
            raise SystemExit(f"kazakhstan: no sheet {sheet!r}; sheets are {workbook.sheetnames}")
        districts, dcounts = parse_sheet(list(workbook[sheet].iter_rows(values_only=True)))
        summed = sum(dcounts[d].get("Всего", 0) for d in districts)
        if summed != counts[column]["Всего"]:
            raise SystemExit(f"kazakhstan: {sheet}'s districts sum to {summed:,} against the "
                             f"region's {counts[column]['Всего']:,}")
        for district in districts:
            aliases = [transliterate(bare(district))] + RENAMED.get(district, [])
            out["admin2"].append(record(
                f"{region_id(region)}-{transliterate(bare(district)).lower().replace(' ', '-')}",
                district, level="admin2", parent=region_id(region), parent_name=region,
                country="KAZ", aliases=aliases,
                population=measure(dcounts[district].get("Всего"), year=YEAR, source=SOURCE),
                ethnicity=bars(district, dcounts[district]),
                ethnicity_note=f"{SOURCE}. {NOTE}", sources=src,
            ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    import openpyxl
    log(f"kazakhstan: {WORKBOOK}")
    workbook = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    out = build(workbook)
    for level, records in out.items():
        log(f"  {level}: {len(records)} records")
        if level in EXPECTED and len(records) != EXPECTED[level]:
            raise SystemExit(f"kazakhstan: expected {EXPECTED[level]} {level} records, "
                             f"built {len(records)}")
        write_json(PROCESSED / OUT[level], records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
