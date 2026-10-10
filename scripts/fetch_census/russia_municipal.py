#!/usr/bin/env python3
"""The 2020 Russian census by municipal district and urban okrug.

Volume 1, table 5 of the census (ЧИСЛЕННОСТЬ НАСЕЛЕНИЯ РОССИИ, ФЕДЕРАЛЬНЫХ
ОКРУГОВ, СУБЪЕКТОВ ... МУНИЦИПАЛЬНЫХ ОБРАЗОВАНИЙ) counts everyone by sex for
every municipal formation as it stood on 1 October 2021: the urban okrugs,
municipal districts and municipal okrugs of each subject, and the settlements
inside them. The first of those tiers is what the map's second level draws,
and this adapter writes each one's count and its men per hundred women.

**What the map draws is not always what the census counted.** The boundary
file's Russian second level is a mix of vintages: Moscow Oblast still has the
districts it abolished in 2015-2019 beside some of the urban okrugs that
replaced them; many oblasts have converted districts into municipal okrugs
since, sometimes merging a district with the town it surrounded. A census
unit is bound to a polygon only when all of these hold:

- the two name the same place: the census's Cyrillic name agrees with the
  polygon's own Cyrillic name, or with the Russian label of the Wikidata item
  the polygon is already linked to, or -- where neither exists -- its
  romanisation agrees with the polygon's romanised name;
- they are the same kind of place: a district (the census's "Xский
  муниципальный район / округ", or an okrug made from one) against a
  "District"/"Rayon"/"район" polygon, a city's urban okrug against a polygon
  named for the city;
- nothing else in the subject claims either of them (one to one);
- an okrug that the census made from a district and its town is not bound
  when the boundary file still draws that town as a polygon of its own: its
  count covers two polygons and belongs to neither;
- a settlement the census counts in one unit and the boundary file draws in
  another unit's polygon (Kharp, joined to Labytnangi in 2021; the villages
  Chechnya moved between districts) is carried to the polygon that draws it,
  from its own row of the table, where that row is the whole change -- and
  where it is not, neither polygon is bound (DRAWN_ELSEWHERE). Every
  settlement GeoNames places well outside its unit's polygon is logged.

Wikidata is the name crosswalk here and nothing more: it supplies a Russian
spelling for a polygon the boundary file romanised. No figure comes from it.

Everything not bound is logged, both sides, with the reason.

Usage:
    python -m scripts.fetch_census.russia_municipal --fetch   # runner: workbook + labels
    python -m scripts.fetch_census.russia_municipal           # bind and write
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, RAW, gap, log, measure, record, write_json
from . import east_geo, russia

import fetch_wikidata  # noqa: E402  (scripts/ is on the path via _shared)

TABLE = "Tom1_tab-5_VPN-2020.xlsx"
CAPTURE = "20260901210517"
LANDING = ("https://rosstat.gov.ru/vpn/2020/"
           "Tom1_Chislennost_i_razmeshchenie_naseleniya")
SOURCE = ("Федеральная служба государственной статистики (Rosstat), "
          "Всероссийская перепись населения 2020 года, Том 1, таблица 5: "
          "Численность населения ... муниципальных образований, retrieved via "
          f"the Internet Archive capture of {CAPTURE[:4]}-{CAPTURE[4:6]}-"
          f"{CAPTURE[6:8]}")
YEAR = 2021

SITE = PROCESSED.parent.parent / "site" / "data"
LABELS = RAW / "wikidata_points" / "RUS_admin2_labels.json"
OUT = "russia_municipal.json"

# What this file does not write, and why, on every polygon it reaches: without
# a note the Wikidata sweep's placeholder ("nothing has been fetched") stands,
# which is not a reason. Religion is left to the country's collection policy.
#
# Measured: Rosstat's federal volume 2 (tables 2 and 5) and volume 5 (tables
# 1, 3, 4, 6 and 23), read through the Internet Archive, are all by subject.
_UNREACHED = (
    " Rosstat's federal volumes publish it by subject only (shown one level up); "
    "below that the regional offices publish it, on hosts whose Russian Trusted "
    "Root CA certificate the runner does not trust, and the Internet Archive holds "
    "about 12 of their 85 sites.")
UNREAD = {
    "median_age": gap(NOT_AVAILABLE, "The 2020 census's age by municipal unit is not "
                      "read here." + _UNREACHED),
    "ethnicity": gap(NOT_AVAILABLE, "The 2020 census's nationality by municipal unit "
                     "is not read here." + _UNREACHED),
    "language": gap(NOT_AVAILABLE, "The 2020 census's native language by municipal "
                    "unit is not read here." + _UNREACHED),
}


# ---------------------------------------------------------------------------
# The workbook


# Blocks read and not bound: the federal cities are not divided on this map
# (Moscow's one child polygon is a mis-parented Moscow Oblast district), and
# Crimea and Sevastopol are drawn inside Ukraine.
NOT_DRAWN = {"г. Москва - городское население", "г. Санкт-Петербург - городское население",
             "Республика Крым", "г. Севастополь"}

# Table 5 spells North Ossetia with a bare hyphen.
BLOCK_NAMES = {"Республика Северная Осетия-Алания": "РСО-Алания"}

TOWN = re.compile(r"\bг\.\s*([^,;()\-]+(?:-[^,;()\s]+)*)")

# A settlement row, as the table names it: "г. Валуйки", "пгт Уразово",
# "село Головчино", "Городское население - г. Алексеевка".
SETTLEMENT = re.compile(
    r"(?:^|-\s)(г\.|город|пгт|рп|рабочий поселок|поселок городского типа|"
    r"село|с\.|поселок|посёлок|п\.|станица|ст-ца|аул|деревня|д\.|хутор|х\.)\s+"
    r"([А-ЯЁ][^,;()]*?)\s*$")


def settlements(label: str, people: float | None, men: float | None = None,
                women: float | None = None) -> list[list[Any]]:
    """[[kind, name, people, men, women]] for a row that names a settlement."""
    found = SETTLEMENT.search(label)
    if not found or not people:
        return []
    kind = found.group(1)
    kind = "г." if kind in {"г.", "город"} else kind
    return [[kind, " ".join(found.group(2).split()), people, men, women]]


def subject_key(name: str) -> str:
    key = russia.dashes(name)
    key = BLOCK_NAMES.get(key, russia.AGE_NAMES.get(key, key))
    return next((s for s in russia.SUBJECTS if russia.dashes(s) == key), key)


def units(blob: bytes) -> dict[str, dict[str, Any]]:
    """{subject: {total, men, women, units}} from Volume 1's table 5.

    The sheet says which rows sit inside which only by indent: a subject at
    indent 0 (as are the country and the federal districts), its urban
    okrugs, municipal districts and municipal okrugs at indent 1, their urban
    and rural populations and settlements deeper. Arkhangelsk and Tyumen
    oblasts are the exception: their autonomous okrugs and the oblast without
    them sit at indent 1 as subjects of their own, and their formations one
    level further in.

    A formation keeps its towns ("г. Старый Оскол") and whether it has a
    rural population, because both decide whether the boundary file's polygon
    can be the same place.
    """
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    sheet = book.worksheets[0]
    out: dict[str, dict[str, Any]] = {}
    block: dict[str, Any] | None = None
    current: dict[str, Any] | None = None
    tier = 1
    combined = False
    sub_open: dict[str, Any] | None = None
    for row in sheet.iter_rows():
        cell = row[0]
        name = " ".join(str(cell.value or "").split())
        if not name:
            continue
        depth = int(cell.alignment.indent or 0) if cell.alignment else 0
        values = [russia.number(c.value) for c in row[1:4]]
        opens = depth == 0 or (depth == 1 and combined
                               and subject_key(name) in russia.SUBJECTS)
        if opens:
            key = subject_key(name)
            if key in out:
                raise SystemExit(f"russia_municipal: {name!r} opens two blocks")
            if depth == 0:
                combined = key in russia.SKIP and key not in NOT_DRAWN
            block = out[key] = {"total": values[0], "men": values[1],
                                "women": values[2], "units": []}
            tier = depth + 1
            current = None
            continue
        if block is None:
            continue
        if depth == tier:
            own = re.split(r"\s+-\s+(?=(?:городское|сельское) население)", name, 1)
            current = {"name": own[0].strip(), "label": name, "total": values[0],
                       "men": values[1], "women": values[2], "towns": [],
                       "urban_only": "- городское население" in name,
                       "rural_only": "- сельское население" in name,
                       "rural": 0.0}
            block["units"].append(current)
            current["towns"] += [" ".join(t.split()) for t in TOWN.findall(name)]
            current["places"] = settlements(name, *values)
            current["parts"] = []
            sub_open = None
            continue
        if current is not None and depth > tier:
            if name.startswith("Сельское население") and values[0]:
                current["rural"] += values[0]
            current["towns"] += [" ".join(t.split()) for t in TOWN.findall(name)]
            current["places"] += settlements(name, *values)
            # The formation's own urban and rural rows, one level in, and the
            # settlements an unnamed urban row is made of, one level further:
            # what a formation that spans a town's polygon and a district's
            # can be split by (split_okrug).
            if depth == tier + 1:
                opened = None
                if re.match(r"(Городское|Сельское) население", name):
                    opened = {"urban": name.startswith("Городское"), "label": name,
                              "total": values[0], "men": values[1], "women": values[2],
                              "places": settlements(name, *values), "sub": []}
                    current["parts"].append(opened)
                # Rows one level further belong to this row only while no
                # other row of its level has come between.
                sub_open = opened if opened and opened["urban"] and not opened["places"] \
                    else None
            elif depth == tier + 2 and sub_open is not None:
                sub_open["sub"] += settlements(name, *values)
    book.close()
    return out


# ---------------------------------------------------------------------------
# Wikidata as a spelling crosswalk


LABEL_QUERY = """
SELECT ?item ?ru ?en ?oktmo ?gone WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item rdfs:label ?ru . FILTER(LANG(?ru) = "ru") }
  OPTIONAL { ?item rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?item wdt:P764 ?oktmo . }
  OPTIONAL { ?item wdt:P576 ?gone . }
}
"""


def fetch_labels() -> None:
    """The Russian label, OKTMO code and dissolution date of every linked item."""
    shapes = json.loads((SITE / "admin2" / "RUS.units.json").read_text())
    qids = sorted({u["wikidata"] for u in shapes if u.get("wikidata")})
    got: dict[str, dict[str, Any]] = {}
    for i in range(0, len(qids), 300):
        chunk = qids[i:i + 300]
        rows = fetch_wikidata.sparql(
            LABEL_QUERY % " ".join(f"wd:{q}" for q in chunk), cache=False, retries=2)
        for r in rows:
            qid = r["item"]["value"].rsplit("/", 1)[-1]
            entry = got.setdefault(qid, {"ru": None, "en": None, "oktmo": [],
                                         "dissolved": None})
            if r.get("ru"):
                entry["ru"] = r["ru"]["value"]
            if r.get("en"):
                entry["en"] = r["en"]["value"]
            if r.get("oktmo") and r["oktmo"]["value"] not in entry["oktmo"]:
                entry["oktmo"].append(r["oktmo"]["value"])
            if r.get("gone"):
                entry["dissolved"] = r["gone"]["value"][:10]
        log(f"  labels: {len(got)} of {len(qids)} items after {i + len(chunk)}")
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    LABELS.write_text(json.dumps(got, ensure_ascii=False, indent=0, sort_keys=True))
    log(f"  wrote {LABELS} ({len(got)} items)")


# ---------------------------------------------------------------------------
# Names


# What a Russian name says about kind rather than place. Removed from both the
# census's names and the polygons' Russian spellings before they are compared.
RU_KIND = re.compile(
    r"\b(?:городской округ|муниципальный район|муниципальный округ|"
    r"муниципальное образование|муниципальные образования|районное муниципальное "
    r"образование|городское муниципальное образование|сельское поселение|"
    r"городское поселение|город-герой|город-курорт|город|г\.|пгт|рабочий поселок|"
    r"поселок|посёлок|село|зато|район|улус|кожуун|аймак|округ|городского округа|"
    r"национальный|немецкий национальный|с подведомственной территорией|"
    r"и района|города|областного значения)\b", re.I)

# The same for the romanised names of the boundary file.
LATIN_KIND = re.compile(
    r"\b(?:urban okrug|municipal okrug|municipal district|district|rayon|raion|"
    r"rajon|okrug|city|gorodskoy|ulus|kozhuun|oblast|krai|republic|of|the|urban|"
    r"municipality|municipal|formation|region|resort town|national)\b", re.I)

CYRILLIC = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l",
                     "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh",
                     "shch", "", "y", "", "e", "yu", "ya"]))


def ru_core(name: str) -> str:
    """A Russian name's place words, lower case, ё as е, quotes and brackets gone."""
    text = name.lower().replace("ё", "е")
    text = re.sub(r"\([^)]*\)", " ", text)        # "(долгано-эвенкийский)"
    text = re.sub(r"[\"«»“”]", " ", text)
    text = re.sub(r"\s+-\s+", " ", text)
    text = RU_KIND.sub(" ", text)
    # Marёvsky "... Новгородской области": the subject's name in the unit's.
    text = re.sub(r"\b\w+(?:ской|ского) (?:области|края|республики)\b", " ", text)
    return " ".join(text.split())


def ru_stem(core: str) -> str:
    """A core with its adjectival ending folded, so -ский/-ской/-ское agree."""
    words = []
    for word in core.split():
        # The adjective keeps a mark: "Алейский" (the district) and
        # "Алейск" (its town) are different places, often both in the table.
        word = re.sub(r"(ц|с)(кий|кой|кое|кая|кие)$", r"\1к~", word)
        word = re.sub(r"(ный|ной|ное|ная|ные)$", "н~", word)
        word = re.sub(r"(ий|ый|ой|ое|ая)$", "~", word)
        words.append(word)
    return "".join(words).replace("-", "")


def translit(text: str) -> str:
    return "".join(CYRILLIC.get(ch, ch) for ch in text.lower())


def latin_stem(text: str) -> str:
    """A romanised name folded far enough that BGN, ISO and German spellings meet.

    geoBoundaries romanises unevenly -- "Abansky Rayon", "Nizhnedevitsky
    District", "Rajon Nischnekamsk" -- so the comparison is on a skeleton:
    digraphs to one letter, y/i/j as one, the adjectival ending folded.
    """
    import unicodedata
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r",.*$", "", text)             # "Voskhod, Moscow Oblast"
    text = LATIN_KIND.sub(" ", text)
    text = re.sub(r"[^a-z~ ]", "", text)
    words = []
    for word in text.split():
        # The adjective first, while its ending is still as written.
        word = re.sub(r"(skiy|skii|skij|sky|ski|skoy|skoye|skoe|skaya|skaja)$", "sk~", word)
        word = re.sub(r"(nyy|nyi|niy|ny|noy|noye|noe|naya)$", "n~", word)
        for a, b in (("shch", "s"), ("sch", "s"), ("tsch", "c"), ("kh", "h"), ("zh", "j"),
                     ("ts", "c"), ("tz", "c"), ("ch", "c"), ("sh", "s"), ("w", "v")):
            word = word.replace(a, b)
        word = re.sub(r"[yji]+", "i", word)
        word = re.sub(r"(ie|ye|je)", "e", word)
        word = re.sub(r"(iu|yu|ju)", "u", word)
        word = re.sub(r"(ia|ya|ja)", "a", word)
        word = re.sub(r"(.)\1", r"\1", word)
        word = word.replace("'", "")
        words.append(word)
    return "".join(words)


def census_stems(unit: dict[str, Any]) -> tuple[set[str], set[str], str]:
    """(Russian stems, Latin skeletons, kind) for one census formation.

    Kind is "city" when the formation is a town and its okrug with at most a
    tenth of its people rural, "district" otherwise. A town-like formation
    named by adjective ("Кемеровский городской округ") also answers to its
    town ("Кемерово"), which is what a polygon for the city is called.
    """
    name = unit["name"]
    # 'Муниципальный район "Город Киров и Кировский район"': the district
    # that includes its town is known by the district's name.
    name = re.sub(r"(?i)\bгород\s+\S+\s+и\s+", "", name)
    core = ru_core(name)
    total = unit["total"] or 0
    rural = unit["rural"] or (total if unit.get("rural_only") else 0)
    city = unit.get("urban_only") or (total and rural / total <= 0.10)
    stems = {ru_stem(core)} if core else set()
    if city and unit["towns"]:
        # The town's own name, instead of the okrug's adjective: the district
        # around a town often carries the same adjective ("Кемеровский
        # муниципальный округ") and would claim the polygon too.
        stems = {ru_stem(ru_core(unit["towns"][0]))}
    stems.discard("")
    return stems, {latin_stem(translit(s)) for s in stems}, "city" if city else "district"


def shape_stems(shape: dict[str, Any], label: dict[str, Any] | None
                ) -> tuple[set[str], set[str]]:
    """(Russian stems, Latin skeletons) for one polygon: its own name, and the
    Russian label of the item it is linked to."""
    name = shape["name"]
    ru: set[str] = set()
    latin: set[str] = set()
    if re.search(r"[А-Яа-яЁё]", name):
        ru.add(own_russian(name))
    else:
        latin.add(latin_stem(name))
    if label and label.get("ru") and label_agrees(name, label["ru"]):
        ru.add(ru_stem(ru_core(label["ru"])))
    ru.discard("")
    latin.discard("")
    return ru, latin | {latin_stem(translit(s)) for s in ru}


def own_russian(name: str) -> str:
    """The stem of a polygon's own Cyrillic name, allowing for a cut-off one.

    The boundary file's name field stops at 26 characters, so "Арамильский
    городской окру" and "городской округ Верхний Та" are all there is. A
    cut-off kind word is dropped, and a name cut inside the place's own words
    is marked with "*" to be compared as the start of a name.
    """
    if len(name) < TRUNCATED:
        return ru_stem(ru_core(name))
    words = name.split()
    while words and any(k.startswith(words[-1].lower()) for k in KIND_WORDS):
        words = words[:-1]
    core = ru_core(" ".join(words))
    if not core:
        return ""
    whole = re.search(r"(ский|ской|ское|цкий|цкой|ный|ной)$", core)
    return ru_stem(core) + ("" if whole else "*")


def label_agrees(name: str, russian: str) -> bool:
    """Is the linked item's Russian label a spelling of the polygon's own name?

    The link was made by an earlier name sweep and is sometimes to the wrong
    item: the polygon "Volgodonsk" is linked to Volgodonskoy District, and
    "Shumerlinsky District" to the town of Shumerlya. A label that does not
    agree with the name it stands beside is not used -- and neither is the
    population that came with it.
    """
    theirs = ru_stem(ru_core(russian))
    if re.search(r"[А-Яа-яЁё]", name):
        own = own_russian(name)
        if own.endswith("*"):
            return bool(own[:-1]) and theirs.startswith(own[:-1])
        return own == theirs
    own = latin_stem(name)
    theirs = latin_stem(translit(theirs))
    # A town's name and its district's adjective are close in letters and
    # far apart in place: "Volgodonsk" is not "Волгодонской район".
    return own.endswith("~") == theirs.endswith("~") and similar(own, theirs) >= 0.75


def shape_kind(name: str) -> str | None:
    """"district", "city" or None, from the kind words a polygon's name carries."""
    low = name.lower()
    if re.search(r"(district|rayon|raion|rajon|ulus|район|улус|кожуун|municipal region|"
                 r"municipal distri| region$)", low):
        return "district"
    if re.search(r"(городской округ|urban okrug|urban district|city|зато|closed admin)", low):
        return "city"
    return "city" if not re.search(r"(okrug|округ)", low) else None


TRUNCATED = 25
KIND_WORDS = ("городской", "округ", "муниципальный", "муниципальное", "район",
              "образование", "городское", "поселение")


def similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def skeleton(latin: str) -> str:
    """A romanised skeleton's consonants. The vowel that comes and goes between
    a town and its district's adjective drops out: Kolomna and Kolomensky are
    both "klmn"."""
    return re.sub(r"[aeiouy~]", "", latin)


def adjective_of(town: str, district: str) -> bool:
    """Is a district's adjective (a Latin skeleton ending "sk~") made from the
    town's name (a Latin skeleton)?

    Kolomna and Kolomensky, Serpukhov and Serpukhovsky, Pereslavl-Zalessky and
    Pereslavsky. The first six letters decided this before, and "kolomn"
    against "kolome" let the Kolomna okrug of 2017 -- the city, its district
    and, from 2020, Ozyory -- onto the city's polygon.
    """
    if not district.endswith("sk~"):
        return False
    adj = skeleton(district[:-3])
    own = skeleton(town.replace("~", ""))
    if min(len(adj), len(own)) < 4:
        return False
    return adj == own or own.startswith(adj) or adj.startswith(own)


def names_town(shape: dict[str, Any], town: str) -> bool:
    """Is this polygon named for the town (a census row's "г. X")?"""
    ru = ru_stem(ru_core(town))
    if len(ru) < 3:
        return False
    lat = latin_stem(translit(ru))
    s_ru, s_lat = shape["stems"]
    if ru in s_ru or lat in s_lat:
        return True
    return any(s.endswith("*") and len(s) >= 6 and ru.startswith(s[:-1]) for s in s_ru)


def town_drawn_apart(units: list[dict[str, Any]], free: list[dict[str, Any]]
                     ) -> tuple[str, dict[str, Any]] | None:
    """(town, polygon) when a formation's count takes in a town the map draws
    as a polygon of its own that no formation is bound to.

    Such a formation covers two polygons and so belongs to neither, however
    small the town's share: the Odintsovo okrug of 2019 holds Zvenigorod
    (7.6% of it), which the map draws apart, and the Kolomna okrug holds
    Ozyory (11%). A district-kind polygon is never taken for a town.
    """
    for cu in units:
        for town in cu["towns"]:
            for sh in free:
                if shape_kind(sh["name"]) != "district" and names_town(sh, town):
                    return town, sh
    return None


# How close two romanised skeletons must be when no Russian spelling settles
# a polygon, and by how much the best must beat the second best.
FUZZY = 0.86
MARGIN = 0.06


# Polygons named in a language no romanisation of the census's Russian can
# reach, each declared with what it means. None has a town of 3,000 people for
# the towns pass to place it by, or it would not need declaring.
DECLARED = {
    # "German National District" is the English of Немецкий национальный
    # район, the Altai Krai district with its seat at Galbshtadt.
    "Немецкий Национальный муниципальный район": "German National District",
    # Upper Ket: the district on the upper Ket river, Верхнекетский.
    "Верхнекетский муниципальный район": "Upper Ket region",
    # Äänisenranta, "Onega shore" in Finnish, is Karelia's Prionezhsky
    # (Прионежский, "by the Onega") district.
    "Прионежский муниципальный район": "Äänisenranta District",
    # Koskenala, "below the rapids", is the Finnish of Подпорожье; the
    # district is Podporozhsky.
    "Подпорожский муниципальный район": "Koskenala District",
    # Zalari is the seat of Заларинский district.
    "Заларинский муниципальный район": "Zalari municipal region",
    # The census names the municipality in the genitive.
    "Муниципальное образование Мамско-Чуйского района": "Мамско-Чуйский район",
    # Olenyok ulus, the Evenk national district of Sakha.
    "Оленекский эвенкийский национальный муниципальный район": "Olenyoksky Ulus",
    # The Lotoshino urban okrug of 2017 is the Lotoshinsky District renamed,
    # with the same bounds; its seat Lotoshino is a work settlement with no
    # polygon of its own. The okrug is named for the settlement and the
    # polygon for the district's adjective, which no spelling rule joins.
    # The census's 22,217 against the polygon's 21,850 (2025) agrees.
    "Городской округ Лотошино": "Lotoshinsky District",
}


# Settlements the 2020 census files under one unit that the boundary file
# draws inside another unit's polygon, because the outlines are older than
# the change. Found by putting every settlement the table names (all towns,
# and every village of 3,000 or more) at its GeoNames point and keeping those
# that land in a polygon other than their unit's -- a scan run over all 2,311
# formations, whose other hits were each read and are same-named villages or
# simplified borders (logged by the run as "placed elsewhere"). Each entry:
# (subject, settlement as the table spells it) -> (the polygon that draws it,
# what is done, the evidence).
#
# "move": the census counts the settlement on its own row with its sex, so the
# polygon that draws it gets its people and the unit it was joined to loses
# them: the office's own counts, re-assembled for the outlines the map draws.
# "refuse": the change cannot be undone from the census's rows -- other
# villages moved with it that the table does not name, or that GeoNames cannot
# place -- so neither polygon gets a figure.
#
# Each value is (the polygon, the action, the settlement's English name, a
# clause about it: for a move one that follows "it", for a refusal one that
# follows the name).
DRAWN_ELSEWHERE: dict[tuple[str, str], tuple[str, str, str, str]] = {
    # Kharp was the urban settlement (городское поселение) of Kharp in
    # Priuralsky District until 23 April 2021, when it was joined to the
    # Labytnangi urban okrug (Wikidata P131 history of Q1067697). The census
    # of 1 October 2021 counts the okrug as Labytnangi (25,501) and Kharp
    # (5,031) and nothing else; the boundary file still draws Kharp inside
    # Priuralsky District, 13 km from the Labytnangi polygon (GeoNames
    # 66.80 N, 65.81 E).
    ("ЯНАО", "Харп"): (
        "Priuralsky Rayon", "move", "Kharp",
        "was part of Priuralsky District until 23 April 2021, when it was joined to the "
        "Labytnangi urban okrug, and the boundary file still draws it inside Priuralsky "
        "District"),
    # Chechnya's districts were redrawn after the boundary file's outlines
    # were made. The census of 2021 files Starye Atagi under Urus-Martanovsky
    # District, Kulary under Achkhoy-Martanovsky District and Chechen-Aul
    # (with Berdykel) under the city of Argun; all three of the first lie
    # inside the map's Groznensky District (GeoNames: 43.12 N 45.74 E, 43.24 N
    # 45.50 E, 43.20 N 45.79 E), the district Wikidata still files Starye
    # Atagi under until its 2009 municipal reform. Bamut, which the census
    # counts in the new Sernovodsky District, lies inside the map's
    # Achkhoy-Martanovsky District. Berdykel (8,346) cannot be placed by
    # GeoNames, and the table names no village under 3,000 that may have
    # moved with these, so the drawn districts cannot be re-assembled.
    ("Чеченская Республика", "Старые-Атаги"): (
        "Groznensky District", "refuse", "Starye Atagi",
        "which the census counts in Urus-Martanovsky District, lies inside the map's "
        "Groznensky District"),
    ("Чеченская Республика", "Кулары"): (
        "Groznensky District", "refuse", "Kulary",
        "which the census counts in Achkhoy-Martanovsky District, lies inside the map's "
        "Groznensky District"),
    ("Чеченская Республика", "Чечен-Аул"): (
        "Groznensky District", "refuse", "Chechen-Aul",
        "which the census counts in the city of Argun with Berdykel (8,346 people, "
        "whom GeoNames cannot place), lies inside the map's Groznensky District"),
    ("Чеченская Республика", "Бамут"): (
        "Achkhoy-Martanovsky District", "refuse", "Bamut",
        "which the census counts in the new Sernovodsky District, lies inside the map's "
        "Achkhoy-Martanovsky District"),
}


def drawn_elsewhere(subject: str, cunits: list[dict[str, Any]],
                    shapes: list[dict[str, Any]], members: dict[str, list[int]]
                    ) -> tuple[dict[str, list[tuple]], dict[str, list[tuple]],
                               dict[str, list[str]], list[str]]:
    """Apply DRAWN_ELSEWHERE to one subject's bindings.

    Returns (moved out, moved in, refused, log): per polygon, the settlements
    it loses and gains as (name, people, men, women, other unit, why), the
    polygons refused with the sentences that say why, and the run's lines.
    A declared settlement the table or the polygons no longer hold stops the
    run: a stale declaration is a mistake, not a gap.
    """
    out: dict[str, list[tuple]] = defaultdict(list)
    into: dict[str, list[tuple]] = defaultdict(list)
    refused: dict[str, list[str]] = defaultdict(list)
    report: list[str] = []
    by_name = {sh["name"]: sh["id"] for sh in shapes}
    for (subj, place), (polygon, action, english, clause) in DRAWN_ELSEWHERE.items():
        if subj != subject:
            continue
        rows = [(j, p) for j, cu in enumerate(cunits) for p in cu.get("places", [])
                if p[1] == place]
        if len(rows) != 1 or polygon not in by_name:
            raise SystemExit(f"russia_municipal: {subject}: {place!r} is in {len(rows)} "
                             f"formations, and {polygon!r} is "
                             f"{'' if polygon in by_name else 'not '}drawn")
        j, (_, name, people, men, women) = rows[0]
        home = next((sid for sid, js in members.items() if j in js), None)
        there = by_name[polygon]
        unit = cunits[j]["name"]
        if action == "move" and home and there in members and home != there:
            out[home].append((name, people, men, women, polygon,
                              f" {english} ({people:,.0f} people) is not in this figure, "
                              f"though the census counts it in this unit: it {clause}, "
                              f"so its own row in the census's table is counted there."))
            into[there].append((name, people, men, women, unit,
                                f" With {english} ({people:,.0f} people), from its own row "
                                f"in the census's table: it {clause}."))
            report.append(f"{subject}: {name} ({people:,.0f}) moved from {unit!r} to "
                          f"{polygon!r}: it {clause}")
            continue
        sentence = f"{english} ({people:,.0f} people), {clause}"
        for sid in (home, there):
            if sid:
                refused[sid].append(sentence)
        report.append(f"{subject}: {name} ({people:,.0f}) is counted in {unit!r} and drawn "
                      f"in {polygon!r}; neither polygon is bound")
    return out, into, refused, report


def candidates(cunit: dict[str, Any], shape: dict[str, Any],
               label: dict[str, Any] | None) -> tuple[str, float] | None:
    """How a census formation and a polygon agree, if they do: the basis and a score."""
    if DECLARED.get(cunit["name"]) == shape["name"]:
        return ("declared", 1.0)
    c_ru, c_lat, _ = cunit["stems"]
    s_ru, s_lat = shape["stems"]
    if c_ru & s_ru:
        return ("russian", 1.0)
    cut = {s[:-1] for s in s_ru if s.endswith("*") and len(s) >= 5}
    if any(c.startswith(p) for c in c_ru for p in cut):
        return ("russian, cut short", 0.98)
    if c_lat & s_lat:
        return ("romanised", 0.99)
    best = max((similar(a, b) for a in c_lat for b in s_lat), default=0.0)
    if best >= FUZZY:
        return ("near", best)
    return None


def bind_subject(cunits: list[dict[str, Any]], shapes: list[dict[str, Any]],
                 labels: dict[str, dict[str, Any]]) -> tuple[dict[int, str], list[str]]:
    """{census index: shape id} for one subject, and what was refused and why.

    One to one, best first: a pairing is taken only when it is the best for
    both sides and clears the next-best by MARGIN (exact agreements always do).
    """
    notes: list[str] = []
    scored: dict[tuple[int, str], tuple[str, float]] = {}
    for i, cu in enumerate(cunits):
        for sh in shapes:
            got = candidates(cu, sh, labels.get(sh.get("wikidata") or ""))
            if got:
                # Kind breaks a tie and nothing more: Kemerovo's town and the
                # district around it share an adjective, and one polygon is
                # called a district and the other is not.
                kind = shape_kind(sh["name"])
                nudge = 0.0 if kind is None else (KIND if kind == cu["stems"][2] else -KIND)
                scored[(i, sh["id"])] = (got[0], got[1] + nudge)
    bound: dict[int, str] = {}
    taken: set[str] = set()
    for (i, sid), (basis, score) in sorted(scored.items(), key=lambda kv: -kv[1][1]):
        if i in bound or sid in taken:
            continue
        rivals_c = [s for (j, other), (_, s) in scored.items()
                    if j == i and other != sid and other not in taken]
        rivals_s = [s for (j, other), (_, s) in scored.items()
                    if other == sid and j != i and j not in bound]
        second = max(rivals_c + rivals_s, default=0.0)
        if score < 1.0 - KIND and score - second < MARGIN:
            notes.append(f"{cunits[i]['name']!r}: {basis} {score:.2f} with "
                         f"{sid} too close to a rival at {second:.2f}")
            continue
        if score - second < 1.5 * KIND:
            notes.append(f"{cunits[i]['name']!r}: agrees as well with more than one "
                         f"polygon, or its polygon with more than one formation")
            continue
        bound[i] = sid
        taken.add(sid)
    return bound, notes


KIND = 0.01


# ---------------------------------------------------------------------------
# Where a formation's towns are


def gazetteer(shapes_geo: dict[str, Any], parent_of: dict[str, str]
              ) -> dict[tuple[str, str], list[tuple[str, int, float, float]]]:
    """{(admin1 shape, romanised skeleton): [(polygon, population, lon, lat)]} for
    GeoNames' places.

    Each place is put in the map's polygons once, and filed under the
    first-level unit its polygon belongs to, so a town is only ever looked for
    in its own subject.
    """
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    ids = list(shapes_geo)
    tree = STRtree([shapes_geo[i][0] for i in ids])
    out: dict[tuple[str, str], list[tuple[str, int, float, float]]] = defaultdict(list)
    for place in east_geo.places("RUS"):
        point = Point(place["lon"], place["lat"])
        hits = [ids[k] for k in tree.query(point, predicate="within")]
        # A polygon the release has and the map does not draw (the release
        # files Crimea under Russia; the map, under Ukraine) places nothing.
        if len(hits) != 1 or hits[0] not in parent_of:
            continue
        sid = hits[0]
        out[(parent_of[sid], latin_stem(place["name"]))].append(
            (sid, place["population"], place["lon"], place["lat"]))
    return out


# A settlement GeoNames puts this far outside its unit's polygon, with a
# population that agrees with the census's to within a factor of two, is
# logged for review; nearer than this is a simplified border.
OUTSIDE_KM = 2.0


def placed_elsewhere(subject: str, subject_shape: str, cunits: list[dict[str, Any]],
                     members: dict[str, list[int]],
                     index: dict[tuple[str, str], list[tuple[str, int, float, float]]],
                     shapes_geo: dict[str, Any], name_of: dict[str, str]) -> list[str]:
    """The run's review list: settlements of a bound unit that GeoNames places
    well inside another polygon. Each is either declared in DRAWN_ELSEWHERE or
    has been read and found to be a same-named village or a simplified
    border; the list is printed so a new one is seen, not acted on blindly."""
    import math
    from shapely.geometry import Point

    lines = []
    for sid, js in members.items():
        own_poly = shapes_geo[sid][0]
        for j in js:
            own = cunits[j]["stems"][0]
            for kind, name, people, *_ in cunits[j].get("places", []):
                hits = index.get((subject_shape, latin_stem(translit(ru_core_place(name)))), [])
                if len(hits) != 1 or hits[0][0] == sid or ru_stem(ru_core(name)) in own:
                    continue
                other, population, lon, lat = hits[0]
                if not population or not 0.5 <= people / population <= 2.0:
                    continue
                km = own_poly.distance(Point(lon, lat)) * 111.32 * math.cos(math.radians(lat))
                if km < OUTSIDE_KM:
                    continue
                state = ("declared" if (subject, name) in DRAWN_ELSEWHERE
                         else "read: a namesake or a simplified border")
                lines.append(f"{subject}: placed elsewhere -- {kind} {name} ({people:,.0f}) "
                             f"of {cunits[j]['name']!r} is {km:.1f} km outside "
                             f"{name_of.get(sid, sid)!r}, in {name_of.get(other, other)!r} "
                             f"({state})")
    return lines


def locate(unit: dict[str, Any], subject_shape: str,
           index: dict[tuple[str, str], list[tuple[str, int]]]
           ) -> list[tuple[str, float, str]]:
    """[(polygon, people, settlement)] for the formation's settlements that GeoNames places.

    A settlement is placed only when exactly one GeoNames place of its
    subject carries its romanised name; the villages sharing a name with a
    dozen others are left out rather than guessed.
    """
    got = []
    for kind, name, people, *_ in unit.get("places", []):
        hits = index.get((subject_shape, latin_stem(translit(ru_core_place(name)))), [])
        if len(hits) == 1:
            got.append((hits[0][0], people, name, kind))
    return got


def by_polygon(located: list[tuple[str, float, str, str]]) -> Counter:
    got: Counter = Counter()
    for sid, people, _, _ in located:
        got[sid] += people
    return got


def ru_core_place(name: str) -> str:
    return " ".join(name.lower().replace("ё", "е").split())


# A bound formation whose towns put more than this share of its people in
# another polygon is taken to span two polygons, and is not bound.
AWAY = 0.20
# A formation not bound by name is placed by its towns only when this share of
# the people GeoNames can place lies in one polygon.
PLACED = 0.90
# The map's figure for a polygon, where it has one from an encyclopaedia, and
# the census's may differ by years of change; a census count more than this
# many times the polygon's is a merged okrug laid on one of the polygons it
# was merged from, and is not bound. Only that side is tested: a census count
# far *below* the polygon's figure has, in every case read, been the linked
# item's population for a larger or later unit (Rzhevsky District's item is
# the 2022 okrug with the town in it), not a sign that the census unit is
# the wrong one.
RATIO = 2.5
# ...except where the formation's own towns, placed inside the polygon, make
# the difference: an encyclopaedia's figure for "Gaysky District" is the
# district of before 2015 without the town of Gay, which was an urban okrug of
# its own, and the boundary file draws no polygon for Gay -- its point lies in
# the district's. The okrug of today is then exactly the polygon, and it is
# bound when the polygon is a district's and the rest of its count, less the
# towns inside, is within these bounds of the figure the polygon carries. Only
# a district's: a city's polygon with its own town inside is the Kolomna case
# (Losino-Petrovsky's okrug of 2019 took in Monino and the villages around it,
# and the city's polygon carries the city okrug of before).
REST = (0.7, 1.3)


# Settlement kinds that are urban without being towns: an okrug's urban row
# may hold these beside its town, and they go with the district around it.
URBAN_TYPE = {"пгт", "рп", "рабочий поселок", "поселок городского типа"}


def split_okrug(cu: dict[str, Any], town_sid: str, rest_sid: str,
                placed: list[tuple[str, float, str, str]], name_of: dict[str, str],
                kind_of: dict[str, str | None],
                figure_of: dict[str, float | None] | None = None
                ) -> tuple[dict[str, Any], dict[str, Any]] | str:
    """The town's row and the rest of an okrug, as two units, or why not.

    An okrug made of a town and the district around it, which the map still
    draws as two polygons, is counted by the census as one unit -- and, one
    row in, as its urban population and its rural population, each with its
    sex. Where the urban population is the town alone (or the town and
    urban-type settlements, пгт, which lie in the district), the town's row
    is the town polygon's own count and the okrug less the town is the
    district polygon's. Taken only when all of these hold:

    - the okrug's urban and rural rows are one each and make its total, and
      its urban row is exactly one town (г.) and any number of пгт;
    - GeoNames puts the town inside the town's polygon, and none of the
      okrug's other settlements there;
    - the town's polygon is not a district's, and the other polygon is one;
    - where either polygon carries a figure from another source, its part is
      within REST of it (Serpukhov's rest, 47,237, is 1.33 times the 35,551
      Serpukhovsky District carries, and is refused).

    Returns the two units, or a sentence saying which condition failed.
    """
    parts = cu.get("parts") or []
    urban = [p for p in parts if p["urban"]]
    rural = [p for p in parts if not p["urban"]]
    if len(urban) != 1 or len(rural) > 1:
        return "its urban and rural rows are not one of each"
    up = urban[0]
    rp = rural[0] if rural else {"total": 0.0, "men": 0.0, "women": 0.0}
    for key in ("total", "men", "women"):
        if abs((up[key] or 0) + (rp[key] or 0) - (cu[key] or 0)) > 0.5:
            return f"its urban and rural rows do not make its {key}"
    rows = up["places"] or up["sub"]
    towns = [p for p in rows if p[0] == "г."]
    if len(towns) != 1 or any(p[0] not in URBAN_TYPE for p in rows if p[0] != "г."):
        return "its urban population is not one town and urban-type settlements"
    if abs(sum(p[2] for p in rows) - (up["total"] or 0)) > 0.5:
        return "its urban row's settlements do not make it"
    _, town, people, men, women = towns[0]
    if men is None or women is None or abs(men + women - people) > 0.5:
        return f"the row for {town} does not give its sex"
    if kind_of.get(town_sid) == "district" or kind_of.get(rest_sid) != "district":
        return "the polygons are not a town's and a district's"
    where = [s for s, _, name, _ in placed if name == town]
    if where != [town_sid]:
        return (f"GeoNames does not put {town} inside {name_of.get(town_sid, town_sid)!r}")
    inside = [name for s, _, name, _ in placed if s == town_sid and name != town]
    if inside:
        return (f"{', '.join(inside)}, also of the okrug, lie inside "
                f"{name_of.get(town_sid, town_sid)!r}")
    rest = {k: (cu[k] or 0) - v for k, v in (("total", people), ("men", men),
                                             ("women", women))}
    if min(rest.values()) <= 0:
        return "nothing is left of the okrug outside the town"
    for sid, part in ((town_sid, people), (rest_sid, rest["total"])):
        held = (figure_of or {}).get(sid)
        if held and not REST[0] <= part / held <= REST[1]:
            return (f"its part for {name_of.get(sid, sid)!r}, {part:,.0f}, is "
                    f"{part / held:.2f} times the {held:,.0f} that polygon carries")
    others = [p for p in rows if p[0] != "г."]
    outside = f"its rural population ({rp['total'] or 0:,.0f})"
    if others:
        outside += " and the urban-type settlement" + ("s" if len(others) > 1 else "") \
            + " of " + ", ".join(f"{p[1]} ({p[2]:,.0f})" for p in others)
    town_unit = {
        "name": f"г. {town}", "total": people, "men": men, "women": women,
        "towns": [town], "places": [], "parts": [], "rural": 0.0,
        "stems": cu["stems"], "split_of": cu["name"],
        "own_note": (
            f"Everyone the 2020 census counted (reference date 1 October 2021) in the "
            f"town of {town}, from the town's own row of the census's table. The census "
            f"counts the town within {cu['name']} ({cu['total']:,.0f} people), whose "
            f"other {rest['total']:,.0f} people live outside the town and are shown on "
            f"{name_of.get(rest_sid, rest_sid)}, which the map draws beside it.")}
    rest_unit = {
        "name": f"{cu['name']} less г. {town}", "total": rest["total"],
        "men": rest["men"], "women": rest["women"], "towns": [], "places": [],
        "parts": [], "rural": rp["total"] or 0.0, "stems": cu["stems"],
        "split_of": cu["name"],
        "own_note": (
            f"Everyone the 2020 census counted (reference date 1 October 2021) in "
            f"{cu['name']} outside the town of {town}: {outside}, from the okrug's own "
            f"rows of the census's table. The town ({people:,.0f} people), which the "
            f"census counts in the same okrug, is shown on "
            f"{name_of.get(town_sid, town_sid)}, which the map draws as a polygon of "
            "its own.")}
    return town_unit, rest_unit


def carried(shape: dict[str, Any], labels: dict[str, dict[str, Any]],
            linked: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """The figure a polygon carries from another source, or {}.

    The map's figure is this file's own once a build has run: the comparison
    is then with the figure the linked item carries, which the census's
    replaced, so a second run decides as the first did. A population that
    came with a link to the wrong item says nothing about this polygon.
    """
    pop = shape.get("population") or {}
    if pop.get("source") == SOURCE:
        pop = (linked or {}).get(shape.get("wikidata") or "") or {}
    label = labels.get(shape.get("wikidata") or "")
    if label and label.get("ru") and not label_agrees(shape["name"], label["ru"]):
        pop = {}
    return pop


def spanning_reason(unit: str, total: float, polygons: list[str], here: str,
                    held: dict[str, float]) -> str:
    """Why a polygon gets no figure when its okrug spans several of them.

    Said from the polygon's own side: the others are named, never itself.
    """
    others = ["this one"] + [p for p in polygons if p != here]
    towns = "".join(f" {'This one' if p == here else p} holds {held[p]:,.0f} of its "
                    "people in its towns." for p in polygons if held.get(p))
    return (f"The 2020 census counts {unit} ({total:,.0f} people) as one unit, and the "
            f"map draws it as more than one polygon: {', '.join(others[:-1])} and "
            f"{others[-1]}.{towns} Its count belongs to no one polygon, so none is "
            "written.")


def bind_all(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
             admin2: list[dict[str, Any]], labels: dict[str, dict[str, Any]],
             shapes_geo: dict[str, Any], linked: dict[str, dict[str, Any]] | None = None
             ) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, str]]:
    """{polygon id: {subject, members}} for all of Russia, the log of what was
    not bound, and {polygon id: why it has no census figure} for the rest."""
    subject_of_code = {c: s for s, c in russia.SUBJECTS.items()}
    parent_of = {u["id"]: u["parent"] for u in admin2}
    index = gazetteer(shapes_geo, parent_of)
    groups: dict[str, dict[str, Any]] = {}
    report: list[str] = []
    why: dict[str, str] = {}
    for first in admin1:
        subject = subject_of_code.get(first.get("iso_3166_2") or "")
        shapes = [dict(u) for u in admin2 if u["parent"] == first["id"]]
        if not shapes:
            continue
        block = table.get(subject or "")
        if not block or not block["units"]:
            report.append(f"{first['name']}: {len(shapes)} polygons, and no census "
                          f"formations for {subject!r}")
            for sh in shapes:
                why.setdefault(sh["id"], (
                    f"The boundary file files this polygon under {first['name']}, which "
                    "the 2020 census's municipal table counts whole, with no municipal "
                    "units below it; a unit of the same name elsewhere is not this "
                    "polygon's to take, so no census figure is written."))
            continue
        for sh in shapes:
            sh["stems"] = shape_stems(sh, labels.get(sh.get("wikidata") or ""))
        cunits = [dict(c) for c in block["units"]]
        for cu in cunits:
            cu["stems"] = census_stems(cu)
        bound, notes = bind_subject(cunits, shapes, labels)
        report += [f"{subject}: {n}" for n in notes]
        placed_at = {i: locate(cu, first["id"], index) for i, cu in enumerate(cunits)}
        located = {i: by_polygon(p) for i, p in placed_at.items()}
        name_of = {sh["id"]: sh["name"] for sh in shapes}

        # A formation named for one polygon whose towns lie in another. The
        # town a formation is named for is not counted against it: a small
        # city's polygon, simplified, can leave its own GeoNames point just
        # outside, and the name has already said where it is. A formation
        # found to span polygons is then not placed anywhere by its towns
        # either: its count belongs to two polygons and so to neither.
        spanning: set[int] = set()
        kind_of = {sh["id"]: shape_kind(sh["name"]) for sh in shapes}
        figure_of = {sh["id"]: carried(sh, labels, linked).get("value") for sh in shapes}
        # Okrugs split into the town's row and the rest (split_okrug):
        # (formation, town polygon, district polygon, the two units, the
        # reason written if the split cannot be kept).
        splits: list[tuple[int, str, str, dict[str, Any], dict[str, Any],
                           dict[str, str]]] = []
        for i, sid in list(bound.items()):
            total = cunits[i]["total"] or 0
            own = cunits[i]["stems"][0]
            away: Counter = Counter()
            for s, n, town, kind in placed_at[i]:
                # Towns only: a village by a boundary lands on either side of
                # a simplified line, and an okrug joined to a town always
                # has the town to show for it.
                if s != sid and kind == "г." and ru_stem(ru_core(town)) not in own:
                    away[s] += n
            if total and sum(away.values()) > AWAY * total:
                where = ", ".join(f"{name_of.get(s, s)} ({n:,.0f})" for s, n in away.items())
                report.append(f"{subject}: {cunits[i]['name']!r} agrees by name with "
                              f"{name_of[sid]!r} but {sum(away.values()):,.0f} of its "
                              f"{total:,.0f} people live in towns the map draws in "
                              f"{where}; it spans polygons and is not bound")
                polygons = [name_of[s] for s in [sid, *away]]
                held = {name_of[s]: n for s, n in away.items()}
                reasons = {s: spanning_reason(cunits[i]["name"], total, polygons,
                                              name_of[s], held) for s in [sid, *away]}
                del bound[i]
                spanning.add(i)
                split = (split_okrug(cunits[i], next(iter(away)), sid, placed_at[i],
                                     name_of, kind_of, figure_of) if len(away) == 1
                         else "its towns lie in more than one other polygon")
                if isinstance(split, tuple):
                    splits.append((i, next(iter(away)), sid, *split, reasons))
                    continue
                report.append(f"{subject}: {cunits[i]['name']!r} is not split: {split}")
                for s, reason in reasons.items():
                    why.setdefault(s, reason)
        # The other way round: an okrug made from a town and the district
        # around it, bound to the town's polygon while the boundary file still
        # draws the district beside it (Pereslavl-Zalessky and Pereslavsky
        # District; Manturovo and Manturovsky District; Kolomna and Kolomensky
        # District). The district's polygon is left with no formation of its
        # own and an adjective made from the okrug's town.
        taken = set(bound.values())
        lonely = [sh for sh in shapes if sh["id"] not in taken
                  and shape_kind(sh["name"]) == "district"]
        for i, sid in list(bound.items()):
            cu = cunits[i]
            if cu["stems"][2] != "district" or not cu["towns"]:
                continue
            town = latin_stem(translit(ru_stem(ru_core(cu["towns"][0])))).replace("~", "")
            if len(town) < 4:
                continue
            for sh in lonely:
                if any(s.endswith("~") and ((len(town) >= 6 and s[:6] == town[:6])
                                            or adjective_of(town, s))
                       for s in sh["stems"][1]):
                    report.append(f"{subject}: {cu['name']!r} agrees by name with "
                                  f"{name_of[sid]!r}, but it has a rural population "
                                  f"({cu['rural']:,.0f}) and the map still draws "
                                  f"{sh['name']!r} beside it: the okrug joined the "
                                  f"two, and is not bound")
                    reason = (f"The 2020 census counts {cu['name']} ({cu['total']:,.0f} "
                              f"people) as one okrug: the town and the district around "
                              f"it, which the map still draws apart as "
                              f"{name_of[sid]!r} and {sh['name']!r}. Its count belongs "
                              "to neither polygon, so none is written.")
                    reasons = {sid: reason, sh["id"]: reason}
                    # And the polygons its other towns lie in (Ozyory's).
                    for s, _, other, kind in placed_at[i]:
                        if kind == "г." and s not in (sid, sh["id"]):
                            reasons.setdefault(s, reason[:-len("so none is written.")]
                                               + f"and it takes in {other}, which lies "
                                               "in this polygon; so none is written.")
                    del bound[i]
                    spanning.add(i)
                    split = split_okrug(cu, sid, sh["id"], placed_at[i], name_of,
                                        kind_of, figure_of)
                    if isinstance(split, tuple) and len(reasons) == 2:
                        splits.append((i, sid, sh["id"], *split, reasons))
                        break
                    report.append(f"{subject}: {cu['name']!r} is not split: "
                                  + (split if isinstance(split, str)
                                     else "its towns lie in a third polygon"))
                    for s, why_not in reasons.items():
                        why.setdefault(s, why_not)
                    break
        members: dict[str, list[int]] = {sid: [i] for i, sid in bound.items()}
        how: dict[str, str] = {sid: "name" for sid in members}

        # Formations not bound by name, put where their towns are.
        pending: dict[str, list[int]] = defaultdict(list)
        for j, cu in enumerate(cunits):
            if j in bound or j in spanning or not located[j]:
                continue
            best, people = located[j].most_common(1)[0]
            if people < PLACED * sum(located[j].values()):
                report.append(f"{subject}: {cu['name']!r} is not bound; its towns lie in "
                              + ", ".join(name_of.get(s, s) for s in located[j]))
                for s in located[j]:
                    why.setdefault(s, (
                        f"The 2020 census counts {cu['name']} ({cu['total']:,.0f} people) "
                        "as one unit, and its settlements lie in more than one of the "
                        "map's polygons: " + ", ".join(name_of.get(t, t) for t in located[j])
                        + ". Its count belongs to no one polygon, so none is written."))
                continue
            kind = cu["stems"][2]
            if best in members:
                if kind == "city":
                    members[best].append(j)
                    how[best] = "name, with a town the map draws inside it"
                else:
                    report.append(f"{subject}: {cu['name']!r} lies in "
                                  f"{name_of[best]!r}, already bound by name to "
                                  f"{cunits[members[best][0]]['name']!r}; not bound")
            else:
                pending[best].append(j)
        for sid, js in pending.items():
            districts = [j for j in js if cunits[j]["stems"][2] == "district"]
            cities = [j for j in js if cunits[j]["stems"][2] == "city"]
            if len(districts) == 1 or (not districts and len(cities) == 1):
                members[sid] = districts + cities
                how[sid] = "towns"
            else:
                report.append(f"{subject}: {name_of[sid]!r} holds the towns of "
                              + ", ".join(repr(cunits[j]["name"]) for j in js)
                              + "; which of them it is cannot be told, so none is bound")
                why.setdefault(sid, (
                    "The polygon holds the towns of more than one of the 2020 census's "
                    "units (" + ", ".join(cunits[j]["name"] for j in js) + "), and "
                    "which of them it draws cannot be told, so no figure is written."))

        # The split okrugs, where nothing else has claimed either polygon:
        # the town's row on the town's polygon, the rest on the district's.
        for i, town_sid, rest_sid, town_unit, rest_unit, reasons in splits:
            if town_sid in members or rest_sid in members or town_sid in pending \
                    or rest_sid in pending:
                report.append(f"{subject}: {cunits[i]['name']!r} is not split: another "
                              "formation lies in one of its polygons")
                for s, reason in reasons.items():
                    why.setdefault(s, reason)
                continue
            for sid, unit in ((town_sid, town_unit), (rest_sid, rest_unit)):
                j = len(cunits)
                cunits.append(unit)
                placed_at[j], located[j] = [], Counter()
                members[sid] = [j]
                how[sid] = "split okrug"
            report.append(f"{subject}: {cunits[i]['name']!r} ({cunits[i]['total']:,.0f}) "
                          f"split: the town's row {town_unit['total']:,.0f} to "
                          f"{name_of[town_sid]!r}, the rest {rest_unit['total']:,.0f} to "
                          f"{name_of[rest_sid]!r}")

        # A polygon's current figure, where it has one, and the census's
        # cannot be worlds apart -- unless the formation's own towns, placed
        # inside the polygon, are the difference.
        extra: dict[str, str] = {}
        for sid, js in list(members.items()):
            shape = next(sh for sh in shapes if sh["id"] == sid)
            total = sum(cunits[j]["total"] or 0 for j in js)
            pop = carried(shape, labels, linked)
            ratio = total / pop["value"] if pop.get("value") else None
            if ratio is not None and ratio > RATIO:
                inside = [(town, n) for j in js for s, n, town, kind in placed_at[j]
                          if s == sid and kind == "г."]
                rest = total - sum(n for _, n in inside)
                if (inside and shape_kind(shape["name"]) == "district"
                        and REST[0] <= rest / pop["value"] <= REST[1]):
                    towns = ", ".join(f"{t} ({n:,.0f})" for t, n in inside)
                    report.append(f"{subject}: {name_of[sid]!r} gets {total:,.0f}, "
                                  f"{ratio:.2f} times the {pop['value']:,} it carries; "
                                  f"the towns {towns} lie inside it and the rest, "
                                  f"{rest:,.0f}, is its figure's size: bound")
                    extra[sid] = (" The boundary file draws no polygon of its own for "
                                  + ", ".join(t for t, _ in inside) + ", which lies inside "
                                  "this one, so the census's unit is the polygon with "
                                  "the town in it.")
                else:
                    report.append(f"{subject}: {name_of[sid]!r} would get {total:,.0f} from "
                                  + " + ".join(repr(cunits[j]['name']) for j in js)
                                  + f", {ratio:.2f} times the {pop['value']:,} it carries "
                                  f"({pop.get('source')}); not the same place, not bound")
                    why.setdefault(sid, (
                        "The 2020 census's nearest unit, " + " and ".join(
                            cunits[j]["name"] for j in js) + f", counts {total:,.0f} "
                        f"people, {ratio:.1f} times the figure this polygon carries; "
                        "they are not the same place, so no census figure is written."))
                    del members[sid]
                    continue

        # A formation whose count takes in a town the map draws as a polygon
        # of its own that no formation holds, whatever the town's share:
        # the town's polygon by its name, or by where the town's point lies.
        # The Odintsovo okrug of 2019 took in Zvenigorod (7.6% of it) and the
        # Kolomna okrug Ozyory (11%); Berezniki's took in Usolye with the
        # Usolsky District of before 2018. Each would wear the other polygon's
        # people.
        for sid, js in sorted(members.items()):
            free = [sh for sh in shapes if sh["id"] not in members and sh["id"] != sid]
            found = town_drawn_apart([cunits[j] for j in js], free)
            drawn = "which the map draws apart as"
            if not found:
                free_ids = {sh["id"] for sh in free}
                spot = next(((town, s) for j in js for s, n, town, kind in placed_at[j]
                             if kind == "г." and s in free_ids), None)
                if spot:
                    found = (spot[0], next(sh for sh in free if sh["id"] == spot[1]))
                    drawn = "which lies in the map's polygon"
            if not found:
                continue
            town, other = found
            names = " + ".join(repr(cunits[j]["name"]) for j in js)
            report.append(f"{subject}: {names} counts the town of {town}, {drawn} "
                          f"{other['name']!r}, which no formation holds; "
                          f"{name_of[sid]!r} is not bound")
            reason = (f"The 2020 census's {' and '.join(cunits[j]['name'] for j in js)} "
                      f"takes in the town of {town}, {drawn} {other['name']!r}: its "
                      "count covers more than one polygon, so none is written.")
            why.setdefault(sid, reason)
            why.setdefault(other["id"], reason)
            del members[sid]

        # Settlements the census counts in one unit and the map draws in
        # another's polygon: moved where the census's rows allow it, the
        # polygons refused where they do not.
        report += placed_elsewhere(subject, first["id"], cunits, members, index,
                                   shapes_geo, name_of)
        moved_out, moved_in, wrong, lines = drawn_elsewhere(subject, cunits, shapes,
                                                            members)
        report += lines
        for sid, sentences in wrong.items():
            if sid in members:
                del members[sid]
            why[sid] = ("The 2020 census's unit and this polygon are not the same "
                        "ground: " + "; ".join(sentences) + ". The census's figure for "
                        "the unit would describe a different area, and the change "
                        "cannot be undone from its rows, so none is written.")

        for sid, js in members.items():
            shape = next(sh for sh in shapes if sh["id"] == sid)
            groups[sid] = {"subject": subject, "shape": shape["name"], "how": how[sid],
                           "members": [cunits[j] for j in js], "extra": extra.get(sid, ""),
                           "moved_out": moved_out.get(sid, []),
                           "moved_in": moved_in.get(sid, [])}
        split_up = {cunits[j].get("split_of") for js in members.values() for j in js}
        left = [cu["name"] for j, cu in enumerate(cunits)
                if not any(j in js for js in members.values())
                and cu["name"] not in split_up]
        empty = [sh for sh in shapes if sh["id"] not in members]
        for sh in empty:
            why.setdefault(sh["id"], (
                "No unit of the 2020 census's municipal table is this polygon and "
                "nothing else. The boundary file draws an older division here; the "
                f"census's units left over in {subject} are "
                + (", ".join(left) if left else "none") + "."))
        if left or empty:
            report.append(f"{subject}: formations left {left}; polygons left "
                          f"{[sh['name'] for sh in empty]}")
    return groups, report, why


def linked_populations() -> dict[str, dict[str, Any]]:
    """{Wikidata item: its population} for Russia's second level, as the
    Wikidata sweep wrote it: what a polygon carried before this file's figure
    replaced it."""
    path = PROCESSED / "wikidata_admin2.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text())
    rows = rows.get("records", rows) if isinstance(rows, dict) else rows
    return {r["id"].split("-WD-", 1)[1]: r["population"] for r in rows
            if r.get("country") == "RUS" and "-WD-" in r.get("id", "")
            and isinstance(r.get("population"), dict) and r["population"].get("value")}


def figures(group: dict[str, Any]) -> tuple[float, float, float]:
    """(people, men, women) on one polygon: its units, less the settlements the
    map draws elsewhere, plus those it draws here from another unit."""
    total = sum(u["total"] for u in group["members"])
    men = sum(u["men"] for u in group["members"])
    women = sum(u["women"] for u in group["members"])
    for sign, moved in ((-1, group.get("moved_out", [])), (1, group.get("moved_in", []))):
        for _, people, m, w, *_ in moved:
            if m is None or w is None or abs(m + w - people) > 0.5:
                raise SystemExit(f"russia_municipal: a moved settlement's men and women "
                                 f"do not make its {people:,.0f}")
            total, men, women = total + sign * people, men + sign * m, women + sign * w
    if total <= 0 or men <= 0 or women <= 0:
        raise SystemExit(f"russia_municipal: {group['shape']} is left with {total:,.0f}")
    return total, men, women


def moved_note(group: dict[str, Any]) -> str:
    """What the note says about settlements moved to or from this polygon: the
    count is the unit's less what the map draws elsewhere, or with what the
    map draws here, each from its own row of the census's table."""
    return "".join(why for *_, why in group.get("moved_out", []) + group.get("moved_in", []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help="fetch the workbook and the items' Russian labels")
    args = ap.parse_args()
    blob = russia.workbook(TABLE, CAPTURE)
    if args.fetch:
        fetch_labels()
        table = units(blob)
        n = sum(len(v["units"]) for v in table.values())
        log(f"  {TABLE}: {n} first-tier formations in {len(table)} blocks")
        return 0
    table = units(blob)
    for name, block in table.items():
        made = sum(u["total"] or 0 for u in block["units"])
        if block["units"] and abs(made - (block["total"] or 0)) > 0.5:
            raise SystemExit(f"russia_municipal: {name}'s formations make {made:,.0f}, "
                             f"the subject {block['total']:,.0f}")
        for u in block["units"]:
            if (u["men"] or 0) + (u["women"] or 0) != u["total"]:
                raise SystemExit(f"russia_municipal: {name}, {u['name']}: men and "
                                 f"women do not make its {u['total']:,.0f}")
    log(f"  {TABLE}: every subject's formations make its total, and every "
        "formation's men and women make its own")
    admin1 = json.loads((SITE / "admin1" / "RUS.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "RUS.units.json").read_text())
    labels = json.loads(LABELS.read_text())
    groups, report, why = bind_all(table, admin1, admin2, labels,
                                   east_geo.polygons("RUS"), linked_populations())
    for line in report:
        log("  " + line)
    records = []
    how_many: Counter = Counter()
    for sid, g in sorted(groups.items()):
        members = g["members"]
        total, men, women = figures(g)
        names = [u["name"] for u in members]
        how_many[g["how"]] += 1
        if len(members) == 1 and members[0].get("own_note"):
            note = members[0]["own_note"]
        else:
            note = ("Everyone the 2020 census counted (reference date 1 October 2021) in "
                    + names[0])
            if len(names) > 1:
                note += (" and in " + ", ".join(names[1:]) + ", which the census counts "
                         "apart and the map draws inside this polygon")
            note += "."
        note += g.get("extra", "") + moved_note(g)
        records.append(record(
            f"RUS-VPN2020-{sid}", g["shape"], level="admin2", parent="RUS",
            country="RUS", match_by="shape_id", shape_id=sid,
            population=measure(int(total), year=YEAR, source=SOURCE),
            population_note=note,
            sex_ratio=measure(round(100 * men / women, 1), unit="males_per_100_females",
                              year=YEAR, source=SOURCE),
            sex_ratio_note=f"{int(men):,} men and {int(women):,} women; {note}",
            sources=[{"field": "population/sex_ratio", "name": SOURCE, "url": LANDING,
                      "license": russia.LICENCE, "year": YEAR}],
            **UNREAD,
        ))
    # The polygons no census unit is, each with the reason, so the map says
    # why rather than showing nothing (a gap never displaces a figure).
    site = {u["id"]: u for u in admin2}
    for sid, reason in sorted(why.items()):
        if sid in groups or sid not in site:
            continue
        refusal = gap(NOT_AVAILABLE, reason)
        records.append(record(
            f"RUS-VPN2020-{sid}", site[sid]["name"], level="admin2", parent="RUS",
            country="RUS", match_by="shape_id", shape_id=sid,
            population=refusal, sex_ratio=refusal, **UNREAD))
    # A settlement moved between polygons leaves one and joins another: what
    # the polygons are written with must be what their units count.
    written = sum(figures(g)[0] for g in groups.values())
    held = sum(u["total"] for g in groups.values() for u in g["members"])
    if abs(written - held) > 0.5:
        raise SystemExit(f"russia_municipal: the polygons are written with {written:,.0f} "
                         f"people and their units count {held:,.0f}")
    formations = sum(len(b["units"]) for k, b in table.items() if k not in NOT_DRAWN)
    # A split okrug's two parts are one formation.
    placed = sum(1 for g in groups.values() for u in g["members"] if not u.get("split_of"))
    placed += len({(g["subject"], u["split_of"]) for g in groups.values()
                   for u in g["members"] if u.get("split_of")})
    bound_n = len(groups)
    log(f"  {bound_n} of {len(admin2)} polygons bound ({dict(how_many)}), holding "
        f"{placed} of {formations} formations; {len(records) - bound_n} polygons "
        "written as gaps with the reason")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
