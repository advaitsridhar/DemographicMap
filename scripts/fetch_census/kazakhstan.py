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
("Атбасарский район" is drawn as "Atbasarskiy"). A unit is placed on the
polygon of its region whose label is its transliteration, or the name
``RENAMED`` gives for a unit the map still knows under an earlier one
(Zelenovskiy is today's Bäiterek District, Tselinniy is Gabit Musrepov
District, and so on) -- each a renaming of the same unit, not a redrawing.

**Units the map does not draw.** The boundary file's second level is about
twenty years old. It draws none of the districts created since (Zhetisay and
Keles out of Maktaaral and Saryagash in 2018, Kegen out of Raiymbek, Kosshy
out of Tselinograd and Sauran out of Turkestan's territory in 2021, the six
of 2022 in Abai and East Kazakhstan, Alatau out of Ili in 2024), and it
leaves most city akimats inside the district around them -- Karaganda,
Temirtau and Saran inside Bukhar-Zhyrau, Oskemen inside Ulan, Oral inside
Bäiterek (Zelenovskiy), and so on. ``INSIDE`` names the drawn polygon each
of these lies in, found by testing the unit's centre or seat against the
drawn polygons, and the polygon carries the sum of every unit inside it, as
a district merged after the census may: the counts are exact, and a
polygon's figure covers the ground it draws. Before this, those polygons
carried their own district's figure alone -- Qostanay without Kostanay
District or Rudny, Bukhar-Zhyrau without Karaganda.

Every unit must land on exactly one polygon of its region, and every polygon
must receive one, or the run stops; ``EMPTY`` lists the one drawn polygon no
unit is: Jambyl Region's second "Zhualy", a small shape north of Taraz,
about 100 km from Zhualy District's own polygon. Records are bound to their
polygon by its id. The three cities of republican significance are one
polygon each where the map draws them (Almaty, Shymkent; Astana has none).

Usage:
    python -m scripts.fetch_census.kazakhstan
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, dated, gap, log, measure, record, shares, write_json,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import canonical_groups  # noqa: E402
from common import as_drawn, read_json, shard_name  # noqa: E402

SITE = PROCESSED.parent.parent / "site" / "data"
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
    "город Тараз": ["Zhamb."],                      # Taraz was Zhambyl, 1993-1997

    "Аксу г.а.": ["Aksuskiy"],
    "Арысь г.а.": ["Arysskiy"],
}

# The same, for names the 2009 and 2021 censuses print differently from the
# 2025 workbook (keyed by ``key``): a district under its name before a
# renaming, and the cities whose workbook entry above says "город".
EARLIER_NAMES: dict[str, list[str]] = {
    "щучинский": ["Shuchinskiy"],          # Shchuchinsk District, renamed Burabay 2009
    "зыряновский": ["Zyryanovsk"],         # renamed Altai District 2019
    "созакский": ["Suzakskiy"],            # the census's spelling of Suzak
    "алматы": ["Almaty (Alma-Ata)"],       # the city of republican significance
    "аягоз": ["Ayagozskiy"],               # 2009: Ayagoz city akimat, the district since
    "джангельдинский": ["Dzhangildinskiy"],  # the 2009 census's spelling
    "имени габита мусрепова": ["Tselinniy"],   # keys are names without 'район'
    "габита мусрепова": ["Tselinniy"],
    "т.рыскулова": ["Lugovskoy"],
}

# Units the boundary file does not draw, by the drawn polygon each lies in
# (keyed by ``key``). Each was placed by testing a point against the drawn
# second-level polygons: a city's centre, a district's seat or, where the
# Bureau's district is new, the seat of the district it was carved from.
INSIDE: dict[str, str] = {
    # Akmola
    "кокшетау": "Zerendinskiy",          # 69.39E 53.28N
    "косшы": "Tselinogradskiy",          # carved from Tselinograd District, 2021; 71.56E 51.03N
    "степногорск": "Akkol`skiy",         # 71.89E 52.35N
    # Almaty Region and Jetisu
    "капшагай": "Iliyskiy",              # 77.07E 43.87N; renamed Konaev in 2022
    "капчагай": "Iliyskiy",              # the 2021 census's spelling
    "қонаев": "Iliyskiy",
    "алатау": "Iliyskiy",                # 2024, built on Zhetygen village of Ili District
    "кегенский": "Raiymbekskiy",         # carved from Raiymbek District, 2018; 79.23E 43.02N
    "текели": "Taldyqorghan",            # 78.82E 44.83N
    "ескельдинский": "Taldyqorghan",     # seat Karabulak 78.49E 44.91N
    # West Kazakhstan
    "уральск": "Zelenovskiy",            # Oral, 51.37E 51.23N
    # Karaganda and Ulytau
    "караганда": "Bukhar-Zhyrauskiy",    # 73.10E 49.80N, and 73.05/49.85, 73.15/49.75
    "сарань": "Bukhar-Zhyrauskiy",       # 72.84E 49.79N
    "темиртау": "Bukhar-Zhyrauskiy",     # 72.96E 50.05N
    "шахтинск": "Abayskiy",              # 72.59E 49.71N
    "балхаш": "Aktogayskiy",             # 74.99E 46.85N
    "приозерск": "Aktogayskiy",          # 73.72E 46.03N
    "жезказган": "Ulytauskiy",           # 67.71E 47.78N
    "сатпаев": "Ulytauskiy",             # 67.53E 47.90N
    "каражал": "Zhanaarkinskiy",         # 70.79E 48.01N
    # Kostanay: the polygon drawn as Qostanay is Kostanay District with the
    # city and Rudny inside it.
    "костанайский": "Qostanay",          # seat Zatobolsk 63.68E 53.19N
    "рудный": "Qostanay",                # 63.12E 52.96N
    "лисаковск": "Taranovskiy",          # 62.49E 52.54N
    # Kyzylorda
    "байконыр": "Karmakchinskiy",        # 63.31E 45.62N
    "байконур": "Karmakchinskiy",
    # Mangystau: Munaily District surrounds Aktau; its villages (Mangystau
    # 51.27E 43.69N, Kyzyltobe 51.20E 43.72N, Baskuduk 51.31E 43.62N) are
    # inside the polygon drawn as Aqtau.
    "жанаозен": "Karakiyanskiy",         # 52.86E 43.34N
    "мунайлинский": "Aqtau",
    # Pavlodar and North Kazakhstan
    "павлодар": "Pavlodarskiy",          # 76.95E 52.29N
    "петропавловск": "Kyzylzharskiy",    # 69.15E 54.87N
    # Turkestan: Sauran, carved in 2021 from Turkestan's own territory,
    # surrounds Turkestan and Kentau.
    "кентау": "Turkestan",               # 68.51E 43.52N
    "сауран": "Turkestan",
    "жетисайский": "Maktaaral`skiy",     # carved from Maktaaral District, 2018; 68.33E 40.77N
    "жетысайский": "Maktaaral`skiy",
    "келесский": "Saryagashskiy",        # carved from Saryagash District, 2018
    # East Kazakhstan and Abai
    "усть-каменогорск": "Ulanskiy",      # Oskemen, 82.61E 49.95N
    # Kurchatov's centre (78.55E 50.76N) falls just inside the drawn Mayskiy
    # polygon of Pavlodar Region, where the second-level outlines overrun
    # the first-level border; inside East Kazakhstan's outline the polygon
    # around it is Beskaragay (78.7E 50.75N, 78.8E 50.6N).
    "курчатов": "Beskaragayskiy",
    "ақсуат": "Tarbagatayskiy",          # carved from Tarbagatay, 2022; Aksuat 82.81E 47.76N
    "жаңасемей": "Semipalatinskiy",      # Semey's rural territory, a district again from 2022
    "мақаншы": "Urdzharskiy",            # carved from Urzhar, 2022; Makanshy 82.00E 46.79N
    "марқакөл": "Kurchumskiy",           # carved from Kurchum, 2022
    "самар": "Kokpektinskiy",            # carved from Kokpekty, 2022; Samarskoye 83.36E 49.03N
    "үлкен нарын": "Katon-Karagayskiy",  # carved from Katon-Karagay, 2022; 84.53E 49.21N
}

# Drawn polygons no unit of the Bureau's is, with the reason.
EMPTY: dict[tuple[str, str], str] = {
    ("Jambyl Region", "Zhualy"): (
        "The boundary file draws a second, small polygon labelled Zhualy north of "
        "Taraz, between Talas, Baizak and Moiynkum districts and about 100 km from "
        "Zhualy District's own polygon (drawn as Zhualynskiy, which carries the "
        "district's figures). No unit the Bureau publishes is this polygon, so "
        "nothing is bound to it."),
}

LOOKALIKE = str.maketrans("AaBCcEeHKMOoPpTXxy", "АаВСсЕеНКМОоРрТХху")
CITY_AKIMAT = re.compile(r"\bг\.\s*а\b\.?", re.IGNORECASE)


def squeeze(text: str) -> str:
    """Lower case, 'ё' as 'е', and no spaces or full stops."""
    return re.sub(r"[\s.]", "", text.lower().replace("ё", "е"))


def key(russian: str) -> str:
    """A unit's name as the lookups know it, across the three sources' spellings.

    'Кокшетау г.а.', 'Кокшетау Г.А.', 'Кокшетау г.а' and 'город Кокшетау' are
    one key; so are 'Район им.Габита Мусрепова' and 'Район Им. Габита
    Мусрепова'. The 2009 volumes set the odd Latin letter in a Cyrillic name
    ('Aршалынский'), which is folded back first.
    """
    return squeeze(bare(CITY_AKIMAT.sub(" ", russian.translate(LOOKALIKE))))


def fold(label: str) -> str:
    """A drawn label for comparison: 'Akkol`skiy' and 'Akkolskiy' alike."""
    return re.sub(r"[`'’ʼ.\s-]", "", label).lower()


def drawn_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The map's Kazakh polygons under the boundary file's own labels."""
    a1 = as_drawn(read_json(SITE / "admin1" / shard_name("KAZ"), []))
    a2 = as_drawn(read_json(SITE / "admin2" / shard_name("KAZ"), []))
    return a1, a2


def names_for(russian: str) -> list[str]:
    """Every drawn label a unit may go by: its transliteration, a renaming, or INSIDE."""
    k = key(russian)
    out = [transliterate(bare(CITY_AKIMAT.sub(" ", russian.translate(LOOKALIKE))))]
    out += [n for full, names in RENAMED.items() if key(full) == k for n in names]
    out += [n for name, names in EARLIER_NAMES.items() if squeeze(name) == k for n in names]
    out += [label for name, label in INSIDE.items() if squeeze(name) == k]
    return out


def place(region: str, units: list[str], a1: list[dict[str, Any]],
          a2: list[dict[str, Any]]) -> dict[str, list[str]]:
    """{drawn polygon id: [units on it]} for one drawn first-level region.

    A unit lands on the polygon one of its names (``names_for``) folds to; it
    must find exactly one, and every polygon of the region must receive at
    least one unit unless ``EMPTY`` says why not. Anything else stops the
    run, listing every unplaced unit at once.
    """
    region_ids = [u["id"] for u in a1 if u["name"] == region]
    if len(region_ids) != 1:
        raise SystemExit(f"kazakhstan: {len(region_ids)} drawn regions named {region!r}")
    polygons = [u for u in a2 if u.get("parent") == region_ids[0]]
    by_fold: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for polygon in polygons:
        by_fold[fold(polygon["name"])].append(polygon)
    out: dict[str, list[str]] = defaultdict(list)
    problems = []
    for unit in units:
        hits = {p["id"]: p for name in names_for(unit) for p in by_fold.get(fold(name), [])}
        if len(hits) != 1:
            problems.append(f"{unit} -> {sorted(p['name'] for p in hits.values()) or 'nothing'}")
            continue
        out[next(iter(hits))].append(unit)
    for polygon in polygons:
        if polygon["id"] not in out and (region, polygon["name"]) not in EMPTY:
            problems.append(f"drawn {polygon['name']} receives no unit")
    if problems:
        raise SystemExit(f"kazakhstan: {region}: " + "; ".join(problems))
    return dict(out)


def namesake(unit: str, label: str) -> bool:
    """Whether the polygon is drawn under this unit's own name (or an earlier one)."""
    k = key(unit)
    own = [transliterate(bare(CITY_AKIMAT.sub(" ", unit.translate(LOOKALIKE))))]
    own += [n for full, names in RENAMED.items() if key(full) == k for n in names]
    own += [n for name, names in EARLIER_NAMES.items() if squeeze(name) == k for n in names]
    return any(fold(n) == fold(label) for n in own)


# Units counted with a polygon that does not hold their point at full
# resolution, and what the reader is told. Measured on the boundary file's
# own geometry (CGAZ ADM1 and ADM2), not on the tiles.
OUTSIDE = {
    "курчатов": (
        "Kurchatov's centre (78.54E 50.75N) lies in the polygon drawn as Mayskiy, a district "
        "of Pavlodar Region, where the boundary file's second-level outlines overrun its "
        "first-level border. The city belongs to East Kazakhstan (to Abai Region since "
        "2022, which the map draws inside it), as the boundary file's first level has it "
        "too, so it is counted here with Beskaragay, the district around it inside East "
        "Kazakhstan's outline."),
}


def polygon_note(label: str, units: list[str]) -> str | None:
    """What a polygon holding several of the Bureau's units carries, said once."""
    if len(units) < 2:
        return None
    first = [u for u in units if namesake(u, label)]
    rest = [u for u in units if u not in first]
    held = first[:1] or rest[:1]
    others = [u for u in units if u not in held]
    outside = [OUTSIDE[key(u)] for u in units if key(u) in OUTSIDE]
    return (f"The polygon drawn as {label} holds {held[0]} and also {', '.join(others)}, "
            f"which the boundary file does not draw apart; it carries their sum."
            + "".join(f" {why}" for why in outside))

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


def build(workbook: Any, a1: list[dict[str, Any]] | None = None,
          a2: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    if a1 is None or a2 is None:
        a1, a2 = drawn_units()
    out: dict[str, list[dict[str, Any]]] = {"admin1": [], "admin2": []}
    units, counts = parse_sheet(list(workbook[COUNTRY_SHEET].iter_rows(values_only=True)))
    log(f"  {COUNTRY_SHEET}: {len(units)} columns, {len(next(iter(counts.values())))} rows")
    if set(units) != set(REGIONS):
        raise SystemExit(f"kazakhstan: the country sheet's columns changed: "
                         f"{sorted(set(units) ^ set(REGIONS))}")
    src = [{"field": "population/ethnicity", "name": SOURCE, "url": PAGE, "license": LICENCE}]
    for shape, groups in merged(counts).items():
        rows = bars(shape, groups)
        out["admin1"].append(record(
            region_id(shape), shape, level="admin1", parent="KAZ", country="KAZ",
            population=measure(groups["Всего"], year=YEAR, source=SOURCE),
            ethnicity=rows, ethnicity_year=dated(rows, YEAR),
            ethnicity_note=f"{SOURCE}. {NOTE}", sources=src,
        ))
    # Every unit of a drawn region, from the sheets of the workbook's columns
    # that make it up; a city of republican significance is one unit.
    by_region: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
    for column, region in REGIONS.items():
        if column in CITY_SHEETS:
            if column in CITY_SHAPES:
                by_region[region][column] = counts[column]
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
            if district in by_region[region]:
                raise SystemExit(f"kazakhstan: {district} twice in {region}")
            by_region[region][district] = dcounts[district]
    out["admin2"] = district_records(by_region, a1, a2, src)
    return out


def summed_counts(parts: list[dict[str, int]]) -> dict[str, int]:
    total: dict[str, int] = {}
    for part in parts:
        for russian, n in part.items():
            total[russian] = total.get(russian, 0) + n
    return total


def district_id(region: str, units: list[str], label: str) -> str:
    """The record id: from the unit whose own name the polygon carries, else the label."""
    own = [u for u in units if namesake(u, label)]
    stem = transliterate(bare(own[0])) if own else label
    return f"{region_id(region)}-{stem.lower().replace(' ', '-')}"


def district_records(by_region: dict[str, dict[str, dict[str, int]]],
                     a1: list[dict[str, Any]], a2: list[dict[str, Any]],
                     src: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One record per drawn polygon, bound by its id, carrying the sum of its units."""
    shapes = {u["id"]: u for u in a2}
    region_of = {u["id"]: u["name"] for u in a1}
    out: list[dict[str, Any]] = []
    for region in sorted(by_region):
        units = by_region[region]
        placed = place(region, list(units), a1, a2)
        for shape_id, names in sorted(placed.items()):
            label = shapes[shape_id]["name"]
            counts = summed_counts([units[n] for n in names])
            rows = bars(label, counts)
            note = polygon_note(label, names)
            out.append(record(
                district_id(region, names, label), label, level="admin2",
                parent=region_id(region), parent_name=region, country="KAZ",
                match_by="shape_id", shape_id=shape_id,
                aliases=sorted({*names, *(transliterate(bare(n)) for n in names)} - {label}),
                population=measure(counts.get("Всего"), year=YEAR, source=SOURCE),
                population_note=note,
                ethnicity=rows, ethnicity_year=dated(rows, YEAR),
                ethnicity_note=f"{SOURCE}. {NOTE}" + (f" {note}" if note else ""),
                sources=src,
            ))
    for (region, label), reason in EMPTY.items():
        if region not in by_region:
            continue
        for shape in a2:
            if shape["name"] == label and region_of.get(shape.get("parent")) == region:
                out.append(record(
                    f"{region_id(region)}-{fold(label)}-unbound", label, level="admin2",
                    parent=region_id(region), parent_name=region, country="KAZ",
                    match_by="shape_id", shape_id=shape["id"],
                    population=gap(NOT_AVAILABLE, reason), ethnicity=gap(NOT_AVAILABLE, reason),
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
