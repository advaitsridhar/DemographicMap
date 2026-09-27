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
  count covers two polygons and belongs to neither.

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

from ._shared import PROCESSED, RAW, log, measure, record, write_json
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


def settlements(label: str, people: float | None) -> list[list[Any]]:
    """[[kind, name, people]] for a row that names a settlement."""
    found = SETTLEMENT.search(label)
    if not found or not people:
        return []
    kind = found.group(1)
    kind = "г." if kind in {"г.", "город"} else kind
    return [[kind, " ".join(found.group(2).split()), people]]


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
            current["places"] = settlements(name, values[0])
            continue
        if current is not None and depth > tier:
            if name.startswith("Сельское население") and values[0]:
                current["rural"] += values[0]
            current["towns"] += [" ".join(t.split()) for t in TOWN.findall(name)]
            current["places"] += settlements(name, values[0])
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
}


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
              ) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """{(admin1 shape, romanised skeleton): [(polygon, population)]} for GeoNames' places.

    Each place is put in the map's polygons once, and filed under the
    first-level unit its polygon belongs to, so a town is only ever looked for
    in its own subject.
    """
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    ids = list(shapes_geo)
    tree = STRtree([shapes_geo[i][0] for i in ids])
    out: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for place in east_geo.places("RUS"):
        point = Point(place["lon"], place["lat"])
        hits = [ids[k] for k in tree.query(point, predicate="within")]
        # A polygon the release has and the map does not draw (the release
        # files Crimea under Russia; the map, under Ukraine) places nothing.
        if len(hits) != 1 or hits[0] not in parent_of:
            continue
        sid = hits[0]
        out[(parent_of[sid], latin_stem(place["name"]))].append((sid, place["population"]))
    return out


def locate(unit: dict[str, Any], subject_shape: str,
           index: dict[tuple[str, str], list[tuple[str, int]]]
           ) -> list[tuple[str, float, str]]:
    """[(polygon, people, settlement)] for the formation's settlements that GeoNames places.

    A settlement is placed only when exactly one GeoNames place of its
    subject carries its romanised name; the villages sharing a name with a
    dozen others are left out rather than guessed.
    """
    got = []
    for kind, name, people in unit.get("places", []):
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


def bind_all(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
             admin2: list[dict[str, Any]], labels: dict[str, dict[str, Any]],
             shapes_geo: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """{polygon id: {subject, members}} for all of Russia, and the log of what was not bound."""
    subject_of_code = {c: s for s, c in russia.SUBJECTS.items()}
    parent_of = {u["id"]: u["parent"] for u in admin2}
    index = gazetteer(shapes_geo, parent_of)
    groups: dict[str, dict[str, Any]] = {}
    report: list[str] = []
    for first in admin1:
        subject = subject_of_code.get(first.get("iso_3166_2") or "")
        shapes = [dict(u) for u in admin2 if u["parent"] == first["id"]]
        if not shapes:
            continue
        block = table.get(subject or "")
        if not block or not block["units"]:
            report.append(f"{first['name']}: {len(shapes)} polygons, and no census "
                          f"formations for {subject!r}")
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
                del bound[i]
                spanning.add(i)
        # The other way round: an okrug made from a town and the district
        # around it, bound to the town's polygon while the boundary file still
        # draws the district beside it (Pereslavl-Zalessky and Pereslavsky
        # District; Manturovo and Manturovsky District). The district's
        # polygon is left with no formation of its own and an adjective made
        # from the okrug's town.
        taken = set(bound.values())
        lonely = [sh for sh in shapes if sh["id"] not in taken
                  and shape_kind(sh["name"]) == "district"]
        for i, sid in list(bound.items()):
            cu = cunits[i]
            if cu["stems"][2] != "district" or not cu["towns"]:
                continue
            town = latin_stem(translit(ru_stem(ru_core(cu["towns"][0])))).replace("~", "")
            if len(town) < 6:
                continue
            for sh in lonely:
                if any(s.endswith("~") and s[:6] == town[:6] for s in sh["stems"][1]):
                    report.append(f"{subject}: {cu['name']!r} agrees by name with "
                                  f"{name_of[sid]!r}, but it has a rural population "
                                  f"({cu['rural']:,.0f}) and the map still draws "
                                  f"{sh['name']!r} beside it: the okrug joined the "
                                  f"two, and is not bound")
                    del bound[i]
                    spanning.add(i)
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

        # The last test: a polygon's current figure, where it has one, and the
        # census's cannot be worlds apart.
        for sid, js in list(members.items()):
            shape = next(sh for sh in shapes if sh["id"] == sid)
            total = sum(cunits[j]["total"] or 0 for j in js)
            pop = shape.get("population") or {}
            label = labels.get(shape.get("wikidata") or "")
            # A population that came with a link to the wrong item says
            # nothing about this polygon.
            if label and label.get("ru") and not label_agrees(shape["name"], label["ru"]):
                pop = {}
            ratio = total / pop["value"] if pop.get("value") else None
            if ratio is not None and ratio > RATIO:
                report.append(f"{subject}: {name_of[sid]!r} would get {total:,.0f} from "
                              + " + ".join(repr(cunits[j]['name']) for j in js)
                              + f", {ratio:.2f} times the {pop['value']:,} it carries "
                              f"({pop.get('source')}); not the same place, not bound")
                del members[sid]
                continue
            groups[sid] = {"subject": subject, "shape": shape["name"], "how": how[sid],
                           "members": [cunits[j] for j in js]}
        left = [cu["name"] for j, cu in enumerate(cunits)
                if not any(j in js for js in members.values())]
        empty = [sh["name"] for sh in shapes if sh["id"] not in members]
        if left or empty:
            report.append(f"{subject}: formations left {left}; polygons left {empty}")
    return groups, report


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
    groups, report = bind_all(table, admin1, admin2, labels, east_geo.polygons("RUS"))
    for line in report:
        log("  " + line)
    records = []
    how_many: Counter = Counter()
    for sid, g in sorted(groups.items()):
        members = g["members"]
        total = sum(u["total"] for u in members)
        men = sum(u["men"] for u in members)
        women = sum(u["women"] for u in members)
        names = [u["name"] for u in members]
        how_many[g["how"]] += 1
        note = ("Everyone the 2020 census counted (reference date 1 October 2021) in "
                + names[0])
        if len(names) > 1:
            note += (" and in " + ", ".join(names[1:]) + ", which the census counts "
                     "apart and the map draws inside this polygon")
        note += "."
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
        ))
    formations = sum(len(b["units"]) for k, b in table.items() if k not in NOT_DRAWN)
    placed = sum(len(g["members"]) for g in groups.values())
    log(f"  {len(records)} of {len(admin2)} polygons bound ({dict(how_many)}), holding "
        f"{placed} of {formations} formations")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
