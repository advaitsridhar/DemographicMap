#!/usr/bin/env python3
"""Kyrgyzstan: the 2022 census by region, district and city.

Book III of the 2022 Population and Housing Census, *Regions of the Kyrgyz
Republic*, is one PDF for each of the seven regions and for each of the two
cities of republican rank, Bishkek and Osh (National Statistical Committee,
2023). Four of its tables are read from every book:

* the permanent population by sex and single year of age (the region or city
  as a whole: 2.7, "по полу и возрасту");
* the permanent population by sex and age group, territory by territory (2.8,
  "по полу, возрастным группам и территории"; 2.7 in Bishkek's book): every
  district and city of the region;
* 3.2, the most numerous ethnic groups by territory, with men and women;
* 3.4, the ethnic groups by native language.

Tables are told apart by their titles and "Продолжение табл." lines, not by
their numbers, which differ from book to book. Every figure is read from the
PDF's text and must make itself whole: both sexes = men + women in every row,
a territory's groups make its total, the districts and cities make their
region, and the age tables agree with table 3.2 on every territory's men and
women.

**Binding.** The boundary file draws 41 districts. It does not draw the
cities of regional rank, nor Bishkek or Osh: each is placed on the drawn
district that holds it (``PLACE``), measured against the drawn outlines, and
a polygon holding several units carries their sum and says so. Its first
level draws seven regions, Bishkek inside Chuy and Osh inside Osh Region;
and it draws Toguz-Toro district -- Jalal-Abad Region's in the census --
inside Naryn Region (92% of its polygon). A first-level polygon therefore
carries the units its own districts hold, which for Chuy, Osh, Naryn and
Jalal-Abad is not the census region's figure, and its note says so.

**Fields.**
* population and sex ratio: table 3.2's men and women;
* median age: interpolated within the five-year group holding the middle
  person (0-4, 5-9, 10-14, 15, 16-19, 20-24 ... 85-89, 90-99, 100+), for a
  district; for a region whose polygon is the census region (or a region and
  the city inside it), within the single year holding it, from table 2.7;
* ethnicity: table 3.2's groups, the rest as published under "other";
* language: table 3.4. For each group it lists, the number who named their
  own group's language, Kyrgyz, Russian (and Uzbek where the book prints a
  column for it), or another language; its first row gives every column's
  total over the whole population. A group's own language is its language
  (Uzbek for Uzbeks, Dungan for Dungans); the people of the groups the table
  does not list who named their own language are counted as other languages.

Religion was not asked by the 2022 census.

Usage:
    python -m scripts.fetch_census.kyrgyzstan_census
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from .cod_ps_age import grouped_median
from .kazakhstan_census import readings
from .redatam import median_age

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import as_drawn, read_json, shard_name  # noqa: E402

ISO3 = "KGZ"
YEAR = 2022
OUT = "kyrgyzstan_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
ARCHIVE = "https://www.stat.gov.kg/media/publicationarchive/"
PAGE = "https://www.stat.gov.kg/ru/publications/"
LICENCE = ("Official statistics of the National Statistical Committee of the Kyrgyz Republic; "
           "free to use with attribution")
SOURCE = ("National Statistical Committee of the Kyrgyz Republic, 2022 Population and Housing "
          "Census, Book III: Regions of the Kyrgyz Republic ({book}), 2023")

# The nine books: the drawn first-level region each belongs to, the census
# region's own row, and the file.
BOOKS = {
    "Chuy": ("Chuy Region", "чуйская область", "390cc065-9ead-4ac7-9f6f-2ddfa38a8cbe"),
    "Bishkek": ("Chuy Region", "г.бишкек", "2a645aed-5154-4518-b114-dc97239a3a83"),
    "Osh": ("Osh Region", "ошская область", "f76c9a54-0edf-4cfd-91df-8d01379a128b"),
    "Osh city": ("Osh Region", "г.ош", "6d075a2f-51ec-4cec-bf59-455c631ce39b"),
    "Batken": ("Batken Region", "баткенская область", "dfe4b339-3f9c-4bb7-887e-96e55e15dde0"),
    "Jalal-Abad": ("Jalal-Abad Region", "жалал-абадская область",
                   "ad52f290-cb14-4ff1-9179-d0ad0f38b09d"),
    "Issyk-Kul": ("Issyk-Kul Region", "иссык-кульская область",
                  "8b892242-eaa9-446d-94b2-7ba7aadcb340"),
    "Naryn": ("Naryn Region", "нарынская область", "e790d125-ecd1-471e-b31b-0eb9dc7c4894"),
    "Talas": ("Talas Region", "таласская область", "d79c0e75-073d-4a50-92fe-3c735b1a2dfc"),
}

BOOK_TITLE = {"Chuy": "Chuy Region", "Bishkek": "the city of Bishkek", "Osh": "Osh Region",
              "Osh city": "the city of Osh", "Batken": "Batken Region",
              "Jalal-Abad": "Jalal-Abad Region", "Issyk-Kul": "Issyk-Kul Region",
              "Naryn": "Naryn Region", "Talas": "Talas Region"}


def unit_title(unit: str) -> str:
    """'тогуз-тороуский район' -> 'Toguz-Toro (тогуз-тороуский район)'."""
    return f"{PLACE[unit]} ({unit})"


# Each district and city (``key`` of its name) -> the drawn district polygon
# holding it. The cities are not drawn; their points, tested against the
# drawn outlines, fall inside the district named. Kyzyl-Kiya's point lies in
# the strip where the boundary file's Batken and Osh outlines overlap; the
# first level puts it in Batken Region, whose district there is Kadamjay.
PLACE = {
    # Chuy Region, with Bishkek
    "г.токмок": "City of Tomok", "аламудунский район": "Alamudun",
    "жайылский район": "Jayyl", "кеминский район": "Kemin", "московский район": "Moskva",
    "панфиловский район": "Panfilov", "сокулукский район": "Sokuluk",
    "чуйский район": "Chuy", "ысык-атинский район": "Ysyk-Ata",
    "г.бишкек": "Alamudun",                       # 74.59E 42.87N, inside Alamudun
    # Osh Region, with Osh
    "алайский район": "Alay", "араванский район": "Aravan",
    "кара-кулжинский район": "Kara-Kulja", "кара-сууский район": "Kara-Suu",
    "ноокатский район": "Nookat", "узгенский район": "Uzgen",
    "чон-алайский район": "Chong-Alay",
    "г.ош": "Kara-Suu",                           # 72.80E 40.53N, inside Kara-Suu
    # Batken Region
    "г.баткен": "Batken", "г.кызыл-кия": "Kadamjay", "г.сулюкта": "Leilek",
    "баткенский район": "Batken", "кадамжайский район": "Kadamjay",
    "лейлекский район": "Leilek",
    # Jalal-Abad Region (Toguz-Toro drawn in Naryn Region)
    "г.жалал-абад": "Suzak", "г.кара-куль": "Toktogul", "г.майлуу-суу": "Nooken",
    "г.таш-кумыр": "Aksy", "аксыйский район": "Aksy", "ала-букинский район": "Ala-Buka",
    "базар-коргонский район": "Bazar-Korgon", "ноокенский район": "Nooken",
    "сузакский район": "Suzak", "тогуз-тороуский район": "Toguz-Toro",
    "токтогульский район": "Toktogul", "чаткальский район": "Chatkal",
    # Issyk-Kul Region
    "г.каракол": "Ak-Suu", "г.балыкчы": "Issyk Kul", "ак-суйский район": "Ak-Suu",
    "джети-огузский район": "Jeti-Oguz", "жети-огузский район": "Jeti-Oguz",
    "иссык-кульский район": "Issyk Kul", "ысык-кульский район": "Issyk Kul",
    "тонский район": "Tong", "тюпский район": "Tup",
    # Naryn Region
    "г.нарын": "Naryn", "ак-талинский район": "Ak-Talaa", "ат-башинский район": "At-Bashy",
    "жумгальский район": "Jumgal", "кочкорский район": "Kochkor",
    "нарынский район": "Naryn",
    # Talas Region
    "г.талас": "Talas", "бакай-атинский район": "Bakay-Ata",
    "кара-бууринский район": "Kara-Buura", "манасский район": "Manas",
    "таласский район": "Talas",
}

# Table 3.2's and 3.4's ethnic groups -> the label used on the map.
ETHNIC = {
    "кыргызы": "Kyrgyz", "узбеки": "Uzbek", "русские": "Russian", "дунгане": "Dungan",
    "уйгуры": "Uyghur", "таджики": "Tajik", "турки": "Turkish", "казахи": "Kazakh",
    "татары": "Tatar", "украинцы": "Ukrainian", "корейцы": "Korean", "корейлер": "Korean",
    "азербайджанцы": "Azerbaijani", "курды": "Kurdish", "немцы": "German",
    "чеченцы": "Chechen", "лезгины": "Lezgin", "даргинцы": "Dargin",
    "карачаевцы": "Karachay", "балкарцы": "Balkar", "туркмены": "Turkmen",
    "китайцы": "Chinese", "белорусы": "Belarusian", "армяне": "Armenian",
    "аварцы": "Avar", "кумыки": "Kumyk", "агулы": "Agul", "калмыки": "Kalmyk",
    "башкиры": "Bashkir", "чуваши": "Chuvash", "молдаване": "Moldovan",
    "ингуши": "Ingush", "осетины": "Ossetian", "грузины": "Georgian",
    "цыгане": "Romani", "евреи": "Jewish", "поляки": "Polish", "мордва": "Mordvin",
    "литовцы": "Lithuanian", "латыши": "Latvian", "эстонцы": "Estonian",
    "греки": "Greek", "кабардинцы": "Kabardian", "ногайцы": "Nogai", "лакцы": "Lak",
    "табасараны": "Tabasaran", "афганцы": "Afghan", "персы": "Persian",
    "арабы": "Arab", "каракалпаки": "Karakalpak", "монголы": "Mongol",
    "болгары": "Bulgarian", "гагаузы": "Gagauz", "удмурты": "Udmurt", "марийцы": "Mari",
    "мордва": "Mordvin", "абхазы": "Abkhaz", "черкесы": "Circassian", "якуты": "Yakut",
    "буряты": "Buryat", "японцы": "Japanese", "вьетнамцы": "Vietnamese",
    "ассирийцы": "Assyrian", "румыны": "Romanian", "венгры": "Hungarian",
    "чехи": "Czech", "финны": "Finnish", "американцы": "American",
    "народы индии и пакистана": "People of India and Pakistan",
    "пакистанцы и индийцы": "People of India and Pakistan",
    "пакистанцы и индусы": "People of India and Pakistan",
    "другие": "Other", "другие этнические группы": "Other",
    "другие национальности": "Other",
}
# A group's own language; None where the group has no single language.
OWN_LANGUAGE = {
    "Kyrgyz": "Kyrgyz", "Uzbek": "Uzbek", "Russian": "Russian", "Dungan": "Dungan",
    "Uyghur": "Uyghur", "Tajik": "Tajik", "Turkish": "Turkish", "Kazakh": "Kazakh",
    "Tatar": "Tatar", "Ukrainian": "Ukrainian", "Korean": "Korean",
    "Azerbaijani": "Azerbaijani", "Kurdish": "Kurdish", "German": "German",
    "Chechen": "Chechen", "Lezgin": "Lezgin", "Dargin": "Dargin",
    "Karachay": "Karachay-Balkar", "Balkar": "Karachay-Balkar", "Turkmen": "Turkmen",
    "Chinese": "Chinese", "Belarusian": "Belarusian", "Armenian": "Armenian",
    "Avar": "Avar", "Kumyk": "Kumyk", "Agul": "Agul", "Kalmyk": "Kalmyk",
    "Bashkir": "Bashkir", "Chuvash": "Chuvash", "Moldovan": "Romanian",
    "Ingush": "Ingush", "Ossetian": "Ossetian", "Georgian": "Georgian",
    "Romani": "Romani", "Polish": "Polish", "Lithuanian": "Lithuanian",
    "Latvian": "Latvian", "Estonian": "Estonian", "Greek": "Greek",
    "Kabardian": "Kabardian", "Nogai": "Nogai", "Lak": "Lak", "Tabasaran": "Tabasaran",
    "Persian": "Persian", "Arab": "Arabic", "Karakalpak": "Karakalpak",
    "Bulgarian": "Bulgarian", "Gagauz": "Gagauz", "Udmurt": "Udmurt", "Mari": "Mari",
    "Abkhaz": "Abkhaz", "Circassian": "Circassian", "Yakut": "Yakut", "Buryat": "Buryat",
    "Japanese": "Japanese", "Vietnamese": "Vietnamese", "Assyrian": "Assyrian",
    "Romanian": "Romanian", "Hungarian": "Hungarian", "Czech": "Czech",
    "Finnish": "Finnish", "American": None,
    "Mordvin": None, "Afghan": None, "Mongol": None, "Jewish": None,
    "People of India and Pakistan": None, "Other": None,
}
# Table 3.4's language columns, as its heading names them.
COLUMNS = {"кыргызский": "Kyrgyz", "русский": "Russian", "узбекский": "Uzbek",
           "таджикский": "Tajik", "казахский": "Kazakh", "дунганский": "Dungan",
           "другие": None}
OTHER_LANGUAGES = "Other languages"

GROUPS = [(0, 4), (5, 9), (10, 14), (15, 15), (16, 19), (20, 24), (25, 29), (30, 34),
          (35, 39), (40, 44), (45, 49), (50, 54), (55, 59), (60, 64), (65, 69), (70, 74),
          (75, 79), (80, 84), (85, 89), (90, 99), (100, None)]
GROUP_LABELS = ["0-4", "5-9", "10-14", "15", "16-19", "20-24", "25-29", "30-34", "35-39",
                "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79",
                "80-84", "85-89", "90-99", "100 лет и старше"]
RELIGION_GAP = gap(NOT_AVAILABLE, (
    "The 2022 census publishes no religion table: Book III's nine regional books cover "
    "numbers and placement, sex and age, ethnic group and language, education, marital "
    "status and fertility (each book's contents, www.stat.gov.kg/media/publicationarchive/), "
    "and none counts religion for any region, district or city."))

PCT = re.compile(r"^(?:\d+(?:[,.]\d+)?|[-–−])$")
DASHES = ("-", "–", "−")


# --------------------------------------------------------------------------
# Reading figures.

def key(name: str) -> str:
    """'г. Токмок' -> 'г.токмок'; '  Аламудунский  район' -> 'аламудунский район'."""
    low = " ".join(name.lower().replace("ё", "е").split())
    return re.sub(r"^г\.?\s*", "г.", low) if re.match(r"^г[.\s]", low) else low


def figures(tokens: list[str], n: int, ok: Callable[[list[int]], bool],
            triples: bool = False) -> list[list[int]]:
    """Every way of reading ``n`` figures from ``tokens`` that ``ok`` accepts.

    Thousands are set apart by spaces ('1 056 758'); a dash is nothing. With
    ``triples``, the figures come as (both sexes, men, women) and a reading
    is dropped as soon as a triple does not add up.
    """
    found: list[list[int]] = []
    tokens = [("-" if t in DASHES else t) for t in tokens]

    def walk(i: int, acc: list[int]) -> None:
        if triples and acc and len(acc) % 3 == 0 and acc[-3] != acc[-2] + acc[-1]:
            return
        if len(acc) == n:
            if i == len(tokens) and ok(acc):
                found.append(acc)
            return
        if i >= len(tokens):
            return
        for value, j in readings(tokens, i):
            walk(j, acc + [value or 0])

    walk(0, [])
    return found


def sexes(tokens: list[str], where: str, strict: bool = True) -> tuple[int, int, int]:
    """Both sexes, men and women from a row's figures, the one reading that adds up.

    Not ``strict``: a row whose men and women miss its total by a misprint is
    still read when its figures can be read only one way, and the misprint is
    logged; only the total is then used, and it is checked against the rows
    it belongs with.
    """
    found = figures(tokens, 3, lambda v: v[0] == v[1] + v[2])
    if not found and not strict:
        found = figures(tokens, 3, lambda v: True)
        if len(found) == 1:
            log(f"  {where}: men and women {found[0][1]:,} + {found[0][2]:,} do not make "
                f"{found[0][0]:,} as printed")
    if len(found) != 1:
        raise SystemExit(f"kyrgyzstan_census: {where}: {len(found)} readings of "
                         f"{' '.join(tokens)!r} as both sexes, men and women")
    return tuple(found[0])  # type: ignore[return-value]


def split_label(line: str) -> tuple[str, list[str]]:
    """('кыргызы', ['785', '211', ...]) -- the words before the first figure."""
    tokens = line.split()
    for i, token in enumerate(tokens):
        if token[0].isdigit() or token in DASHES:
            return " ".join(tokens[:i]), tokens[i:]
    return " ".join(tokens), []


def is_territory(line: str) -> bool:
    low = key(line)
    return (low in PLACE or low.endswith(" район") or low.endswith(" область")
            or low in {b[1] for b in BOOKS.values()}) and not re.search(r"\d", low)


def urban_or_rural(label: str) -> str | None:
    low = label.lower().replace("c", "с")       # a Latin c in "cельское"
    if low.startswith("городское"):
        return "urban"
    if low.startswith("сельское"):
        return "rural"
    return None


# --------------------------------------------------------------------------
# Which pages hold which table.

TITLES = {
    "years": r"по\s+полу\s+и\s+возрасту",
    "groups": r"по\s+полу,?\s+(?:и\s+)?возрастным\s+группам",
    "ethnic": r"наиболее\s+многочисленн\w*\s+этническ",
    "language": r"по\s+родному\s+языку|по\s+владению\s+родным\s+языком",
}
NUMBERED = re.compile(r"(\d)\.(\d+)\.?\s+(?:Численность|Распределение)\s+([^.]{0,200})")
CONTINUED = re.compile(r"Продолжение\s+табл\.?\s*(\d)\.(\d+)\b", re.I)


def signature(text: str) -> str | None:
    """A page's table told by its own column headings, where they say it."""
    if "язык своей" in text and "кыргызский" in text:
        return "language"
    if "Численность лиц" in text and "в процентах" in text:
        return "ethnic"
    return None


def page_kinds(pages: list[str]) -> list[str | None]:
    """The table each page belongs to: 'years', 'groups', 'ethnic', 'language' or None.

    A page whose column headings say which table it is (3.2, 3.4) is that
    table; otherwise its "Продолжение табл. N" line or its title decides,
    once N is known from a title or from a page whose headings say it.
    """
    number_kind: dict[str, str] = {}
    flat = [" ".join(p.split()) for p in pages]
    for text in flat:
        if "СОДЕРЖАНИЕ" in text:
            continue
        for m in NUMBERED.finditer(text):
            title = m.group(3)
            if re.search(r"этническ\w*\s+групп\s+по\s+возрастн|образован|брак", title):
                continue
            for kind, pattern in TITLES.items():
                if re.search(pattern, title):
                    number_kind.setdefault(f"{m.group(1)}.{m.group(2)}", kind)
        own = signature(text)
        for a, b in CONTINUED.findall(text):
            if own:
                number_kind.setdefault(f"{a}.{b}", own)
    kinds: list[str | None] = []
    for text in flat:
        if "СОДЕРЖАНИЕ" in text:
            kinds.append(None)
            continue
        own = signature(text)
        if own:
            kinds.append(own)
            continue
        found = {number_kind[f"{a}.{b}"] for a, b in CONTINUED.findall(text)
                 if f"{a}.{b}" in number_kind}
        if not found:
            found = {number_kind[f"{m.group(1)}.{m.group(2)}"] for m in NUMBERED.finditer(text)
                     if f"{m.group(1)}.{m.group(2)}" in number_kind}
        kinds.append(found.pop() if len(found) == 1 else None)
    return kinds


def numeric(tokens: list[str]) -> bool:
    return bool(tokens) and all(re.fullmatch(r"\d+|\d+,\d+|[-–−]", t) for t in tokens)


# --------------------------------------------------------------------------
# The tables.

def parse_groups(text: str, where: str) -> dict[str, dict[str, Any]]:
    """{territory: {'total': (b, m, w), 'groups': [(b, m, w), ...]}} from the age-group table.

    A territory's block starts with its name, then "Все население" with its
    figures -- or a dash, when the territory is all urban or all rural and the
    next row carries them. Urban and rural blocks that follow are skipped.
    """
    out: dict[str, dict[str, Any]] = {}
    pending: str | None = None
    block: dict[str, Any] | None = None
    waiting = False                       # "Все население -": the next row is the whole

    def start(tokens: list[str]) -> dict[str, Any]:
        if block is not None:
            raise SystemExit(f"kyrgyzstan_census: {where} {block['name']}: age block ends "
                             f"after {block['labels'][-1:]}")
        while tokens and tokens[0] in DASHES:    # "Все население - 316 745 ..."
            tokens = tokens[1:]
        return {"name": pending, "total": sexes(tokens[:-2], f"{where} {pending}"),
                "groups": [], "labels": []}

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        label, tokens = split_label(line)
        low = label.lower()
        if not has_figures(tokens) and is_territory(label or line):
            pending, waiting = key(label or line), False
            continue
        if low.startswith("все население"):
            if pending is None:
                continue
            if not [t for t in tokens if t not in DASHES]:
                waiting = True
                continue
            block = start(tokens)
            pending, waiting = None, False
            continue
        if urban_or_rural(label) and numeric(tokens):
            if waiting and pending:
                block = start(tokens)
                pending, waiting = None, False
            continue
        if block is None:
            continue
        # An age row's label is its first token ("0-4", "15"), or "100 лет и старше".
        if re.match(r"^100 лет и старше", line):
            name, rest = "100 лет и старше", line.split()[4:]
        elif not label and tokens:
            name, rest = tokens[0], tokens[1:]
        else:
            continue
        if name not in GROUP_LABELS or not numeric(rest):
            continue
        if name in block["labels"]:
            raise SystemExit(f"kyrgyzstan_census: {where} {block['name']}: {name} twice")
        block["labels"].append(name)
        block["groups"].append(sexes(rest[:-2], f"{where} {block['name']} {name}"))
        if name == GROUP_LABELS[-1]:
            finish_groups(block, out, where)
            block = None
    if block is not None:
        raise SystemExit(f"kyrgyzstan_census: {where} {block['name']}: the age table ends "
                         f"inside its block")
    return out


def finish_groups(block: dict[str, Any], out: dict[str, dict[str, Any]], where: str) -> None:
    if block["labels"] != GROUP_LABELS:
        raise SystemExit(f"kyrgyzstan_census: {where} {block['name']}: age groups "
                         f"{block['labels']}")
    made = tuple(sum(g[i] for g in block["groups"]) for i in range(3))
    if made != block["total"]:
        raise SystemExit(f"kyrgyzstan_census: {where} {block['name']}: age groups make "
                         f"{made} against {block['total']}")
    old = out.get(block["name"])
    if old and (old["total"], old["groups"]) != (block["total"], block["groups"]):
        raise SystemExit(f"kyrgyzstan_census: {where} {block['name']}: two different "
                         f"age blocks")
    out[block["name"]] = {"total": block["total"], "groups": block["groups"]}


def parse_years(text: str, where: str) -> dict[str, Any] | None:
    """The 2022 single years (both sexes, men, women) from table 2.7, or None.

    Rows carry twelve figures: 2009's whole population, then 2022's whole,
    urban and rural, each as both sexes, men and women.
    """
    ages: dict[int, tuple[int, int, int]] = {}
    total = None

    def read(tokens: list[str], what: str) -> tuple[int, int, int]:
        def ok(v: list[int]) -> bool:
            return v[3:6] == [a + b for a, b in zip(v[6:9], v[9:12])]
        found = figures(tokens, 12, ok, triples=True)
        if len(found) != 1:
            raise SystemExit(f"kyrgyzstan_census: {where} {what}: {len(found)} readings of "
                             f"{' '.join(tokens)!r}")
        return tuple(found[0][3:6])  # type: ignore[return-value]

    for raw in text.splitlines():
        line = " ".join(raw.split())
        label, tokens = split_label(line)
        if label.lower().startswith("все население") and numeric(tokens) and total is None:
            total = read(tokens, "all ages")
            continue
        if total is None or not tokens:
            continue
        lower = line.lower()
        if re.match(r"^до 1 год", lower):
            age, rest = 0, line.split()[3:]
        elif re.match(r"^100 лет и старше", lower):
            age, rest = 100, line.split()[4:]
        elif not label and tokens[0].isdigit() and int(tokens[0]) < 100:
            age, rest = int(tokens[0]), tokens[1:]
        else:
            continue
        if len(rest) < 12 or not numeric(rest) or age in ages:
            continue
        ages[age] = read(rest, f"age {age}")
    if total is None or not ages:
        return None
    if sorted(ages) != list(range(101)):
        raise SystemExit(f"kyrgyzstan_census: {where}: single years "
                         f"{sorted(set(range(101)) - set(ages))[:10]} missing")
    made = tuple(sum(v[i] for v in ages.values()) for i in range(3))
    if made != total:
        raise SystemExit(f"kyrgyzstan_census: {where}: single years make {made} "
                         f"against {total}")
    return {"total": total, "both": Counter({a: v[0] for a, v in ages.items()})}


def has_figures(tokens: list[str]) -> bool:
    return numeric(tokens) and any(t[0].isdigit() for t in tokens)


def ethnic_group(label: str, before: str, where: str, strict: bool = True) -> str:
    """The map's label for a table's ethnic group, joining a name wrapped over two lines.

    Not ``strict`` (table 3.4, where a group only needs its own language): a
    group not known here keeps its printed name, and its own language is
    counted as other languages.
    """
    for name in (label, f"{before} {label}"):
        group = ETHNIC.get(" ".join(name.lower().split()))
        if group:
            return group
    if not strict:
        log(f"  {where}: table 3.4's {label!r} is not a known group; its own language is "
            f"counted as other languages")
        return f"({label})"
    raise SystemExit(f"kyrgyzstan_census: {where}: ethnic group {label!r} is not known "
                     f"(line above: {before!r})")


def parse_ethnic(text: str, where: str) -> dict[str, dict[str, Any]]:
    """{territory: {'total': (b, m, w), 'groups': {label: count}}} from table 3.2.

    A territory's name, then its "Все население" row (both sexes, men, women,
    100), then one row per group with its share; the urban and rural blocks a
    region or city also prints are skipped.
    """
    out: dict[str, dict[str, Any]] = {}
    pending: str | None = None
    block: dict[str, Any] | None = None
    before = ""
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        label, tokens = split_label(line)
        figured = has_figures(tokens)
        if is_territory(label or line):
            pending, block = key(label or line), None
            if figured:                             # the name and its figures on one line
                label = "все население"
        if not figured:
            before = label or line
            continue
        low = label.lower()
        if low.startswith("все население"):
            if pending is None:
                block = None
                continue
            block = {"total": sexes(tokens[:-1], f"{where} {pending}"), "groups": Counter()}
            if pending in out:
                raise SystemExit(f"kyrgyzstan_census: {where}: {pending} twice in table 3.2")
            out[pending] = block
            pending = None
            continue
        if urban_or_rural(label):
            block = None
            continue
        if block is None or not label:
            continue
        group = ethnic_group(label, before, where)
        block["groups"][group] += sexes(tokens[:-1], f"{where} {label}", strict=False)[0]
    for name, block in out.items():
        made, total = sum(block["groups"].values()), block["total"][0]
        if made != total:
            # A group row the table leaves out (Osh Region's Nookat prints no row
            # for its 134 Russians, whom table 3.4 lists) is still among the
            # people: a shortfall of under 1% is counted as other groups.
            if made > total or total - made > 0.01 * total:
                raise SystemExit(f"kyrgyzstan_census: {where} {name}: groups make "
                                 f"{made:,} of {total:,}")
            log(f"  {where} {name}: the printed groups make {made:,} of {total:,}; the "
                f"{total - made:,} left are counted as other")
            block["groups"]["Other"] += total - made
            block["unprinted"] = total - made
    return out


def language_columns(text: str) -> list[str | None]:
    """Table 3.4's columns after the total: own language, then as the heading names them."""
    for raw in text.splitlines():
        low = raw.lower()
        if "кыргызский" in low and "другие" in low:
            words = re.findall(r"[а-я]+", low)
            cols = [COLUMNS[w] for w in words if w in COLUMNS]
            return ["own", *cols]
    raise SystemExit("kyrgyzstan_census: table 3.4 has no heading naming its languages")


def parse_language(text: str, where: str,
                   ethnic: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{territory: {'total': [...], 'groups': {label: [...]}, 'columns': [...]}}.

    Each row is the total, then one figure per column, and must add up; a
    total that table 3.2 also gives must be the same.
    """
    columns = language_columns(text)
    n = len(columns) + 1
    out: dict[str, dict[str, Any]] = {}
    pending: str | None = None
    block: dict[str, Any] | None = None
    current = ""
    before = ""

    def read(tokens: list[str], what: str, total: int | None) -> list[int]:
        """The one reading that adds up -- and that has table 3.2's total, where it has one."""
        found = figures(tokens, n, lambda v: v[0] == sum(v[1:]))
        if total is not None and len(found) > 1:
            found = [v for v in found if v[0] == total] or found
        if len(found) != 1:
            raise SystemExit(f"kyrgyzstan_census: {where} {what}: {len(found)} readings of "
                             f"{' '.join(tokens)!r} in table 3.4")
        if total is not None and found[0][0] != total:
            log(f"  {where} {what}: table 3.4 has {found[0][0]:,}, table 3.2 {total:,}")
        return found[0]

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        label, tokens = split_label(line)
        figured = has_figures(tokens)
        if is_territory(label or line):
            pending, block = key(label or line), None
            if not figured:
                continue
            label = "все население"                 # the name and its figures on one line
        if not figured:
            before = label or line
            continue
        if label.lower().startswith("все население"):
            if pending is None:
                block = None
                continue
            known = ethnic.get(pending, {}).get("total", (None,))[0]
            block = {"total": read(tokens, pending, known), "groups": {},
                     "columns": columns}
            if known is not None and block["total"][0] != known:
                raise SystemExit(f"kyrgyzstan_census: {where} {pending}: table 3.4 counts "
                                 f"{block['total'][0]:,}, table 3.2 {known:,}")
            out[pending] = block
            current, pending = pending, None
            continue
        if urban_or_rural(label):
            block = None
            continue
        if block is None or not label:
            continue
        group = ethnic_group(label, before, where, strict=False)
        if group in block["groups"]:
            raise SystemExit(f"kyrgyzstan_census: {where} {current}: {label!r} twice in "
                             f"table 3.4")
        known = None if group == "Other" else ethnic.get(current, {}).get(
            "groups", {}).get(group)
        block["groups"][group] = read(tokens, f"{current} {label}", known)
    return out


def languages(block: dict[str, Any]) -> Counter:
    """A territory's native languages from its table 3.4 rows (see the module notes)."""
    columns = block["columns"]
    total = block["total"]
    out: Counter = Counter()
    own_listed = 0
    for group, row in block["groups"].items():
        own = row[1]
        own_listed += own
        out[OWN_LANGUAGE.get(group) or OTHER_LANGUAGES] += own
    for i, column in enumerate(columns[1:], start=2):
        out[column or OTHER_LANGUAGES] += total[i]
    out[OTHER_LANGUAGES] += total[1] - own_listed
    if out[OTHER_LANGUAGES] < 0 or sum(out.values()) != total[0]:
        raise SystemExit(f"kyrgyzstan_census: native languages make {sum(out.values()):,} "
                         f"of {total[0]:,}")
    return +out


# --------------------------------------------------------------------------
# A book.

def pdf_pages(blob: bytes) -> list[str]:
    import logging

    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages]


def read_book(name: str, pages: list[str]) -> dict[str, Any]:
    """The four tables of one book, checked against each other and the region's row."""
    kinds = page_kinds(pages)
    text = {kind: "\n".join(p for p, k in zip(pages, kinds) if k == kind)
            for kind in TITLES}
    for kind, body in text.items():
        if not body and kind != "years":
            raise SystemExit(f"kyrgyzstan_census: {name}: no {kind} table found")
    _, region, _ = BOOKS[name]
    ethnic = parse_ethnic(text["ethnic"], name)
    groups = parse_groups(text["groups"], name)
    language = parse_language(text["language"], name, ethnic)
    years = parse_years(text["years"], name)
    units = [t for t in ethnic if t in PLACE]
    if region not in ethnic:
        raise SystemExit(f"kyrgyzstan_census: {name}: table 3.2 has no row {region!r}; "
                         f"it has {sorted(ethnic)}")
    # The units make the region (a city book's only unit is the city).
    if region not in PLACE:
        made = tuple(sum(ethnic[t]["total"][i] for t in units) for i in range(3))
        if made != ethnic[region]["total"]:
            raise SystemExit(f"kyrgyzstan_census: {name}: units {units} make {made} "
                             f"against {ethnic[region]['total']}; unplaced: "
                             f"{sorted(set(ethnic) - set(units) - {region})}")
    for unit in units + [region]:
        if unit not in groups:
            raise SystemExit(f"kyrgyzstan_census: {name}: no age block for {unit}")
        if groups[unit]["total"] != ethnic[unit]["total"]:
            raise SystemExit(f"kyrgyzstan_census: {name} {unit}: the age table has "
                             f"{groups[unit]['total']}, table 3.2 {ethnic[unit]['total']}")
        if unit not in language:
            raise SystemExit(f"kyrgyzstan_census: {name}: no table 3.4 block for {unit}")
    if years and years["total"] != ethnic[region]["total"]:
        raise SystemExit(f"kyrgyzstan_census: {name}: single years make {years['total']}, "
                         f"table 3.2 {ethnic[region]['total']}")
    return {"region": region, "units": units, "ethnic": ethnic, "groups": groups,
            "language": language, "years": years}


# --------------------------------------------------------------------------
# Records.

def drawn_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (as_drawn(read_json(SITE / "admin1" / shard_name(ISO3), [])),
            as_drawn(read_json(SITE / "admin2" / shard_name(ISO3), [])))


def pooled(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Several units' figures added together."""
    total = tuple(sum(p["total"][i] for p in parts) for i in range(3))
    groups = [tuple(sum(p["groups"][g][i] for p in parts) for i in range(3))
              for g in range(len(GROUPS))]
    ethnic: Counter = Counter()
    language: Counter = Counter()
    for p in parts:
        ethnic.update(p["ethnic"])
        language.update(p["languages"])
    return {"total": total, "groups": groups, "ethnic": ethnic, "languages": language}


def fields(unit: dict[str, Any], years: Counter | None, note: str | None,
           books: list[str]) -> dict[str, Any]:
    both, men, women = unit["total"]
    source = SOURCE.format(book=", ".join(books))
    extra = f" {note}" if note else ""
    if years is not None:
        median = median_age(years)
        how = ("Median of the census's single years of age (table 2.7), interpolated within "
               "the year holding the middle person.")
    else:
        median = grouped_median([(lo, hi, g[0]) for (lo, hi), g in zip(GROUPS, unit["groups"])])
        how = ("Median interpolated within the age group holding the middle person, from "
               "the census's five-year groups by territory (0-4 ... 85-89, then 15 and 16-19 "
               "apart, 90-99 and 100+); single years are published for regions only.")
    if sum(unit["ethnic"].values()) != both or sum(unit["languages"].values()) != both:
        raise SystemExit(f"kyrgyzstan_census: compositions do not make {both:,}")
    return {
        "population": measure(both, year=YEAR, source=source),
        "population_note": note,
        "sex_ratio": measure(round(100 * men / women, 1), year=YEAR, source=source,
                             unit="males_per_100_females"),
        "sex_ratio_note": ("Men per 100 women, from table 3.2's men and women." + extra),
        "median_age": measure(median, year=YEAR, source=source),
        "median_age_note": how + extra,
        "ethnicity": shares(dict(unit["ethnic"])),
        "ethnicity_year": YEAR,
        "ethnicity_note": ("Ethnic group (национальность) as each person declared it, table "
                           "3.2; the groups too small to be printed for a territory are its "
                           "'other'." + extra),
        "language": shares(dict(unit["languages"])),
        "language_year": YEAR,
        "language_note": (
            "Native language (родной язык), table 3.4. The table gives, for each group it "
            "lists, the number who named their own group's language, Kyrgyz, Russian (and "
            "Uzbek where printed) or another; a group's own language is counted as that "
            "group's language, and the own language of groups the table does not list as "
            "other languages." + extra),
        "religion": RELIGION_GAP,
        "sources": [{"field": "population/sex_ratio/median_age/ethnicity/language",
                     "name": source, "url": PAGE, "license": LICENCE}],
    }


def build(books: dict[str, dict[str, Any]], a1: list[dict[str, Any]],
          a2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shape_of = {u["name"]: u for u in a2}
    region_name = {u["id"]: u["name"] for u in a1}
    if len(shape_of) != len(a2):
        raise SystemExit("kyrgyzstan_census: the boundary file uses a district name twice")
    units: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for book_name, book in books.items():
        for unit in book["units"]:
            label = PLACE[unit]
            if label not in shape_of:
                raise SystemExit(f"kyrgyzstan_census: {unit} -> {label!r}, which is not drawn")
            units[shape_of[label]["id"]].append((book_name, unit, {
                "total": book["ethnic"][unit]["total"],
                "groups": book["groups"][unit]["groups"],
                "ethnic": book["ethnic"][unit]["groups"],
                "languages": languages(book["language"][unit])}))
    missing = [u["name"] for u in a2 if u["id"] not in units]
    if missing:
        raise SystemExit(f"kyrgyzstan_census: drawn districts with no unit: {missing}")
    out: list[dict[str, Any]] = []
    by_region: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for shape in a2:
        parts = units[shape["id"]]
        by_region[shape["parent"]].extend(parts)
        names = [p[1] for p in parts]
        note = (f"The polygon drawn as {shape['name']} holds {', '.join(names)}, which the "
                f"boundary file does not draw apart; it carries their sum."
                if len(parts) > 1 else None)
        out.append(record(
            f"KGZ-CENSUS-{shape['id']}", shape["name"], level="admin2",
            parent=f"KGZ-CENSUS-{shape['parent']}", parent_name=region_name[shape["parent"]],
            country=ISO3, match_by="shape_id", shape_id=shape["id"], aliases=names,
            **fields(pooled([p[2] for p in parts]), None, note,
                     sorted({p[0] for p in parts}))))
    for region in a1:
        parts = by_region.get(region["id"], [])
        if not parts:
            raise SystemExit(f"kyrgyzstan_census: {region['name']} holds no unit")
        book_names = sorted({p[0] for p in parts})
        whole_books = [b for b in book_names
                       if set(books[b]["units"]) == {p[1] for p in parts if p[0] == b}]
        years = None
        if whole_books == book_names and all(books[b]["years"] for b in book_names):
            years = sum((books[b]["years"]["both"] for b in book_names), Counter())
        unit = pooled([p[2] for p in parts])
        note = None
        if len(book_names) > 1 or whole_books != book_names:
            holds = []
            for b in book_names:
                here = [p[1] for p in parts if p[0] == b]
                gone = [u for u in books[b]["units"] if u not in here]
                if not gone:
                    holds.append(BOOK_TITLE[b])
                elif BOOKS[b][0] == region["name"]:
                    holds.append(f"{BOOK_TITLE[b]} except {', '.join(map(unit_title, gone))}, "
                                 f"which the boundary file draws in another region")
                else:
                    holds.append(f"{', '.join(map(unit_title, here))} of {BOOK_TITLE[b]}")
            note = (f"The polygon drawn as {region['name']} holds {'; and '.join(holds)}. "
                    f"It carries the sum of what it holds, which is not the census region's "
                    f"own figure.")
        if years is not None and sum(years.values()) != unit["total"][0]:
            raise SystemExit(f"kyrgyzstan_census: {region['name']}: single years make "
                             f"{sum(years.values()):,} of {unit['total'][0]:,}")
        out.append(record(
            f"KGZ-CENSUS-{region['id']}", region["name"], level="admin1", parent=ISO3,
            country=ISO3, match_by="shape_id", shape_id=region["id"],
            **fields(unit, years, note, book_names)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--books", default="", help="comma-separated book names (default: all)")
    args = ap.parse_args()
    names = [b for b in args.books.split(",") if b] or list(BOOKS)
    books: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for name in names:
        url = ARCHIVE + BOOKS[name][2] + ".pdf"
        log(f"kyrgyzstan_census: {name}: {url}")
        try:
            pages = pdf_pages(http_get(url, binary=True, timeout=300))  # type: ignore[arg-type]
            books[name] = read_book(name, pages)
        except SystemExit as stop:
            problems.append(str(stop))
            log(f"  {stop}")
            continue
        book = books[name]
        log(f"  {len(book['units'])} units: {', '.join(book['units'])}; single years "
            f"{'read' if book['years'] else 'not found'}")
    if problems:
        raise SystemExit("kyrgyzstan_census: " + " | ".join(problems))
    a1, a2 = drawn_units()
    out = build(books, a1, a2)
    for r in out:
        log(f"    {r['level']} {r['name']}: {r['population']['value']:,}, median "
            f"{r['median_age']['value']}, ratio {r['sex_ratio']['value']}, "
            f"{r['ethnicity'][0]['group']} {r['ethnicity'][0]['pct']}%, "
            f"{r['language'][0]['group']} {r['language'][0]['pct']}%")
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
