#!/usr/bin/env python3
"""First-level units: the population its own Wikipedia article prints, where
nothing else on this map has one.

610 of the map's 3,224 first-level shapes carry no population at all -- every
Maltese locality, every Jamaican parish, every Zambian province, every Saudi
region. The owner's objection of 22 September 2026 was that the figures are
plainly there on Wikipedia, and measuring the five worst countries showed he
was right: each of those articles carries ``population_total`` and
``population_as_of`` in its infobox. The reason they were empty is that
admin-1 population has only ever been fetched from Wikidata's P1082, and a
unit with no P1082 statement -- or with no Wikidata item the admin-1 sweep's
class filter recognised -- came out blank. No reader had ever opened the
article.

This does that, and only that: one scalar field, for a unit that has none.

Three things it will not do.

*An article it cannot prove is the right one is not read.* Names on the map
are the boundary file's, which abbreviates ("Anse Etoil"), drops accents
("Valle Du Bandama") and respells ("Hayel Region"), so a title guessed from
one is a guess. Every candidate is resolved to a Wikidata item first and kept
only if that item is located *directly in the country* (P131), which is what
a first-level unit is and what a town inside one is not. An unmatched unit is
a visible gap; a unit joined to the wrong article is an invisible wrong
number, which is worse.

*A figure it cannot parse is not guessed at.* A value must read as a whole
number, grouped with commas or spaces or not at all. A range, a decimal, an
approximation or a template this module does not know is refused and printed,
so the next run can be told about it rather than publishing a number nobody
wrote.

*An undated figure is published undated.* By the owner's decision of 22
September 2026, a figure on Wikipedia is read whether or not the page dates
it; where the infobox gives no year, the source line says so in words rather
than the record carrying a year nobody stated.

It sits directly below the Wikidata sweep in ADAPTER_FILES, which means every
census file in this project overwrites it. It is the floor, not the ceiling.

Usage:
    python -m scripts.fetch_census.wiki_population --probe ZMB
    python -m scripts.fetch_census.wiki_population --country MLT
    python -m scripts.fetch_census.wiki_population
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path
from difflib import SequenceMatcher
from typing import Any, Iterable

from ._shared import PROCESSED, http_json, log, measure, read_json, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402
from probe_wikitable import infobox_lines  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
SITE = ROOT / "site" / "data"
OUT = "wiki_population_admin1.json"

WIKI = "https://en.wikipedia.org/w/api.php"
DATA = "https://www.wikidata.org/w/api.php"
PAUSE = 0.25
BACKOFF = (30, 60, 120)
LICENCE = "CC BY-SA 4.0"

# How many items to ask Wikidata for in one wbgetentities call (its own limit
# for an anonymous client) and how deep to page the child search. Malta puts
# every locality, parish church and street directly in the country, so the
# candidate list is long where the unit list is longest.
BATCH = 50
PAGES = 90
PER_PAGE = 500

# How far a name may be from the one Wikidata carries and still be taken
# for the same place: long enough that the overlap is not a coincidence,
# close enough that the difference is a spelling.
PREFIX_MIN = 6
# A name that only gains an ending -- North Macedonia's "East" against
# "Eastern Statistical Region" -- may be shorter, because an ending of at
# most three letters is the whole of what it is allowed to gain.
ENDING_MIN = 4
NEAR_MIN = 8
NEAR = 0.92
# The width the boundary file cuts a name to. Seychelles' 24 districts are all
# exactly ten characters -- "Anse Etoil", "Mont Buxto", "Baie Saint" -- and a
# name that long is the only one this module will follow a prefix of freely.
# Below it a prefix may only make up an ending, three characters at most,
# because a prefix that adds a whole word is a different place: the first run
# of this reader matched Jamaica's Clarendon parish to Clarendon Park, a town
# inside it, and Malta's Valletta to the Valletta-Mdina railway.
TRUNCATED_AT = 10
PREFIX_TAIL = 3
# How many names of exactly that length it takes before the length is the
# boundary file's doing rather than a coincidence.
TRUNCATED_SIGN = 3

# The most items to consider for one country. Malta files every locality,
# parish church and street directly under the country, and a candidate
# list longer than this is not going to be made safer by being longer.
CEILING = 4000

# How many of a country's own divisions to open in turn when its first
# level is not what sits directly under it. Five for Malta, thirteen for
# Saudi Arabia; a country with more than this has not needed it.
GRANDCHILDREN = 60

# How many hits of the country-restricted search to consider for one name.
SEARCH_HITS = 15

# How much larger than its shape's bounding box a place's stated area may
# be before it cannot be that shape. Ten times, because Wikidata's areas are
# not always right: Malta's Mgarr is about 16 km^2 and Wikidata says 161,
# which a margin of one and a half refused. What this exists to catch is a
# region offered for its capital, and that is a hundred times or more --
# Minsk Region against the city's box is 157.
AREA_SLACK = 10.0
# How far outside its shape's box, in degrees, a place's own coordinates
# must lie before they prove it is somewhere else -- at least this, and at
# least the size of the box itself.
POINT_SLACK = 1.5

# Above this share of the national total, a country's first level is
# reported as possibly counting someone twice.
OVERCOUNT = 1.05

# The share of its shape's bounding box a place reached only through a
# redirect must fill. A shape seldom fills its whole box, so this is low;
# a town offered for the region around it fills a fraction of a percent.
MIN_FILL = 0.05


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def api(endpoint: str, **params: Any) -> Any:
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    time.sleep(PAUSE)
    for wait in (*BACKOFF, None):
        try:
            return http_json(url, timeout=90)
        except RuntimeError as exc:
            if wait is None:
                raise
            log(f"  {exc}; waiting {wait}s")
            time.sleep(wait)
    return {}


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

FOLD = str.maketrans({
    "ø": "o", "đ": "d", "ð": "d", "ł": "l", "ħ": "h", "ŧ": "t", "ŋ": "n",
    "ı": "i", "ə": "e", "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th",
    "ʻ": "", "ʼ": "", "ʹ": "", "ʾ": "", "ʿ": "", "ʽ": "",
    "`": "", "´": "", "'": "", "’": "",
})

# The words that say what kind of unit a place is rather than which place it
# is. Dropped from both sides of a comparison, in the four languages whose
# forms actually appear in these 610 names: "Artibonite Department" and
# "Departement de l'Artibonite" are the same unit, and so are "Hayel Region"
# and "Ha'il Province".
GENERIC = re.compile(
    r"\b(province|provincia|state|region|regiao|regi[oó]n|district|districto|"
    r"county|prefecture|governorate|oblast|department|departement|departamento|"
    r"municipality|municipio|parish|paroisse|atoll|island|islands|"
    r"autonomous|administrative|capital|metropolitan|city|"
    # The same words in the languages Europe's first level is written in on
    # this map. Belgium's shapes are "Vlaams Gewest" and "Wallonne Gewest",
    # Portugal's are its distritos, Italy's regione, Latvia's novads and its
    # state cities' valstspilseta, Lithuania's apskritis; the decentralised
    # administrations Greece's shapes are drawn from carry both words in
    # English.
    r"gewest|distrito|regione|provincie|apskritis|novads|valstspilseta|"
    r"pilseta|statistical|decentralized|decentralised|administration|"
    r"of|the|and|de|du|des|da|do|del|la|le|les|el|al)\b", re.I)


def plain(text: str | None) -> str:
    """A name lowercased and stripped of accents, and nothing else."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower()).translate(FOLD)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def fold(text: str | None) -> str:
    """A name reduced to what a boundary file and an encyclopaedia agree on.

    Where dropping the generic words leaves nothing, the name *is* its generic
    words, and it is kept whole: Iceland's "Capital Region" folded to the
    empty string and was never compared with anything.
    """
    bare = plain(text)
    if not bare:
        return ""
    stripped = "".join(c for c in GENERIC.sub(" ", bare) if c.isalnum())
    return stripped or "".join(c for c in bare if c.isalnum())


def same_place_name(a: str, b: str) -> bool:
    """Whether two names are one name, allowing an ending of a few letters.

    Latvia's boundary file writes its state cities in the genitive --
    "Rezeknes" for Rezekne -- and the settlement guard refused the city's own
    article for its own shape on that one letter.
    """
    x, y = fold(a), fold(b)
    if x == y:
        return True
    short, long_ = sorted((x, y), key=len)
    return len(short) >= ENDING_MIN and long_.startswith(short) \
        and len(long_) - len(short) <= PREFIX_TAIL


DIRECTIONS = frozenset({
    "north", "south", "east", "west", "northern", "southern", "eastern",
    "western", "northeast", "northwest", "southeast", "southwest",
    "northeastern", "northwestern", "southeastern", "southwestern",
    "nord", "sud", "est", "ouest", "ovest", "norte", "sur", "este", "oeste"})


def a_part_of(name: str, title: str) -> bool:
    """Whether the article is this unit's name with a compass point added.

    Oman's boundary file draws its regions as they were before 2011, when
    Al Batinah and Ash Sharqiyah were each split into a North and a South
    governorate. Resolved against the country's current divisions, "Al
    Batinah" reached Al Batinah South Governorate and read 465,550 people for
    a shape that holds both halves -- the region's own article, which the
    previous run had found, gives 772,590. "X South" is a part of X.

    Only exactly that. Eritrea's "Debub" is Tigrinya for "south" and its
    article is "Southern region"; once the compass point is taken away, what
    is left is not "Debub", so it is not a part of it.
    """
    words = plain(disambiguated(title or "")).split()
    if not DIRECTIONS.intersection(words):
        return False
    rest = fold(" ".join(w for w in words if w not in DIRECTIONS))
    return bool(rest) and rest == fold(name)


def says_its_kind(name: str) -> bool:
    """Whether a name carries a word for what kind of unit it is."""
    return fold(name) != "".join(c for c in plain(name) if c.isalnum())


def disambiguated(title: str) -> str:
    """A title with its ", Country" or " (department)" tail removed.

    Wikipedia disambiguates where two places share a name; the tail is the
    encyclopaedia's bookkeeping and not part of what the place is called, so
    it is dropped before the name is compared.
    """
    title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
    return title.split(",")[0].strip()


# ---------------------------------------------------------------------------
# Resolving a unit to an article
# ---------------------------------------------------------------------------

def country_item(iso3: str) -> str | None:
    """The Wikidata item whose ISO 3166-1 alpha-3 code is this one."""
    hits = ((api(DATA, action="query", list="search",
                 srsearch=f"haswbstatement:P298={iso3}", srlimit=5,
                 srnamespace=0) or {}).get("query") or {}).get("search") or []
    for hit in hits:
        if re.fullmatch(r"Q\d+", hit.get("title") or ""):
            return hit["title"]
    return None


def children(country_qid: str) -> list[str]:
    """Every Wikidata item whose P131 is the country itself.

    A first-level unit is by definition located in its country and in nothing
    between, so this is the set a first-level unit must be drawn from. It also
    contains streets and churches in the small countries, which is harmless:
    a name has to match for an item to be used at all.

    Paged by the API's own ``continue`` and not by counting what came back.
    An anonymous client is clamped to 50 results a call however many it asks
    for, so a run that stopped when a page came back short of what it
    requested would have stopped after the very first one.
    """
    out: list[str] = []
    params: dict[str, Any] = {}
    for _ in range(PAGES):
        payload = api(DATA, action="query", list="search",
                      srsearch=f"haswbstatement:P131={country_qid}",
                      srlimit=PER_PAGE, srnamespace=0, **params) or {}
        batch = ((payload.get("query") or {}).get("search")) or []
        out.extend(hit["title"] for hit in batch
                   if re.fullmatch(r"Q\d+", hit.get("title") or ""))
        cont = payload.get("continue") or {}
        if "sroffset" not in cont or not batch or len(out) >= CEILING:
            break
        params = {"sroffset": cont["sroffset"], "continue": cont.get("continue", "-||")}
    return out


def claims_of(qid: str) -> dict[str, list[dict[str, Any]]]:
    payload = api(DATA, action="wbgetentities", ids=qid, props="claims")
    item = ((payload or {}).get("entities") or {}).get(qid) or {}
    return item.get("claims") or {}


def statements(claims: dict[str, list[dict[str, Any]]], prop: str) -> list[str]:
    out = []
    for claim in claims.get(prop, []):
        value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        if isinstance(value, dict) and value.get("id"):
            out.append(value["id"])
        elif isinstance(value, str):
            out.append(value)
    return out


# Always asked for, whatever the country says it speaks: English because the
# article is English, "mul" because Wikidata now keeps a name that is the same
# in every language there once rather than per language, and the languages
# the boundary files most often write a European or African name in. The
# first run asked for English alone, and every one of Belgium's, France's,
# Italy's and Portugal's gaps was a unit whose name on the map is not English.
LANGUAGES = ("en", "mul", "fr", "de", "es", "it", "pt", "nl", "ru")


def languages(claims: dict[str, list[dict[str, Any]]]) -> list[str]:
    """The Wikimedia codes of the country's official languages (P37 -> P424)."""
    codes: list[str] = []
    for lang in statements(claims, "P37")[:6]:
        codes += statements(claims_of(lang), "P424")
    return list(dict.fromkeys([*LANGUAGES, *codes]))


def contains(qid: str) -> list[str]:
    """What an item says it is divided into: its P150 statements.

    The P131 search alone missed whole countries. Malta files its 68 local
    councils under one of five regions and not under Malta, so a search for
    what sits directly in the country returned 62 items and matched three, all
    three wrong. Reading the division downwards instead of upwards reaches
    them, and reaches a first-level unit whose own article is the only place
    its population is written.
    """
    return statements(claims_of(qid), "P150")


def entities(qids: Iterable[str], langs: Iterable[str] = ("en", "mul")
             ) -> dict[str, dict[str, Any]]:
    """Labels and aliases in these languages, and the English article title."""
    out: dict[str, dict[str, Any]] = {}
    qids = list(dict.fromkeys(qids))
    langs = list(dict.fromkeys(langs))
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        payload = api(DATA, action="wbgetentities", ids="|".join(chunk),
                      props="labels|aliases|sitelinks", languages="|".join(langs),
                      sitefilter="enwiki")
        for qid, item in (payload.get("entities") or {}).items():
            labels = item.get("labels") or {}
            aliases = item.get("aliases") or {}
            names = [(labels.get(lang) or {}).get("value") for lang in langs]
            for lang in langs:
                names += [a.get("value") for a in aliases.get(lang) or []]
            title = ((item.get("sitelinks") or {}).get("enwiki") or {}).get("title")
            out[qid] = {"names": list(dict.fromkeys(n for n in names if n)),
                        "title": title}
    return out


def truncates(units: list[dict[str, Any]]) -> bool:
    """Whether this country's names come out of the boundary file cut short.

    Measured rather than assumed. All 24 of Seychelles' districts are exactly
    ten characters long -- "Anse Etoil", "Mont Buxto", "Baie Saint" -- which
    no real list of names does by accident. Jamaica has two of fourteen at
    that length and is not cut, which matters: with the free prefix granted to
    every long name, "Saint Thomas" reached Saint Thomas in the Vale, a
    different parish.
    """
    return sum(1 for u in units
               if len((u.get("name") or "").strip()) == TRUNCATED_AT) >= TRUNCATED_SIGN


def resolve(units: list[dict[str, Any]], pool: dict[str, dict[str, Any]],
            preset: dict[str, tuple[str, str, str]] | None = None,
            exclude: Iterable[str] = (),
            cutting: bool | None = None
            ) -> dict[str, tuple[str, str, str]]:
    """unit id -> (Wikidata item, English title, how it was matched).

    Three passes, each refusing wherever more than one item would answer and
    never handing one item to two units.

    The prefix pass is what reaches Seychelles, whose boundary file truncates
    a name to ten characters: "Anse Etoil" is the start of "Anse Etoile" and
    of nothing else in the country. The near pass is what reaches a name the
    boundary file respelled -- "Valle Du Bandama" against Wikidata's "Vallee
    du Bandama" -- and it is deliberately the narrowest of the three: both
    names long, one country, one candidate, and close enough that the
    difference is a spelling rather than a different place. Every match above
    the exact one is printed, because a match this module guessed is a match
    somebody should be able to check.

    ``exclude`` is the items the build has already joined to the country's
    *other* shapes. Belarus draws Minsk the region and Minsk the city as two
    shapes, and once the generic words are gone both are "minsk"; the region
    is already the region's, so the city is the only one left for the city.

    Where two items still fold to one name, the one whose own name is written
    exactly as the map writes it wins -- but only where the map's name says
    what kind of unit it is. Lithuania's "Alytus County" folds to "alytus"
    with the town and the district municipality, and only the county is called
    "Alytus County": the word "County" is the evidence. Bulgaria's map calls
    Sofia Province plain "Sofia", and the one item spelled exactly "Sofia" is
    the capital, so a bare name settles nothing and the tie is refused. The
    test suite caught this tiebreak choosing the city before it ever ran.
    """
    by_name: dict[str, list[str]] = {}
    for qid, item in pool.items():
        if not item["title"]:
            continue
        forms = {fold(n) for n in item["names"]}
        forms.add(fold(disambiguated(item["title"])))
        forms.add(fold(item["title"]))
        for form in forms:
            if form:
                by_name.setdefault(form, []).append(qid)

    out: dict[str, tuple[str, str, str]] = dict(preset or {})
    taken: set[str] = {qid for qid, _, _ in out.values()} | set(exclude)

    def written(qid: str) -> set[str]:
        item = pool[qid]
        return {plain(n) for n in item["names"]} | {
            plain(disambiguated(item["title"]))}

    def unique(hits: list[str], raw: str) -> str | None:
        hits = [q for q in dict.fromkeys(hits)
                if q not in taken and not a_part_of(raw, pool[q]["title"])]
        if len(hits) == 1:
            return hits[0]
        if not says_its_kind(raw):
            return None
        spelled = [q for q in hits if plain(raw) in written(q)]
        return spelled[0] if len(spelled) == 1 else None

    def exact(key: str, raw: str) -> str | None:
        return unique(by_name.get(key, []), raw)

    if cutting is None:
        cutting = truncates(units)

    def prefix(key: str, raw: str) -> str | None:
        cut = cutting and len(raw.strip()) == TRUNCATED_AT
        if len(key) < (PREFIX_MIN if cut else ENDING_MIN):
            return None
        return unique([q for form, qids in by_name.items()
                       if form.startswith(key)
                       and (cut or len(form) - len(key) <= PREFIX_TAIL)
                       for q in qids], raw)

    def near(key: str, raw: str) -> str | None:
        if len(key) < NEAR_MIN:
            return None
        return unique([q for form, qids in by_name.items()
                       if len(form) >= NEAR_MIN
                       and SequenceMatcher(None, key, form).ratio() >= NEAR
                       for q in qids], raw)

    for how, find in (("name", exact), ("prefix", prefix), ("near", near)):
        for unit in units:
            if unit["id"] in out:
                continue
            key = fold(unit["name"])
            if not key:
                continue
            qid = find(key, unit["name"])
            if qid:
                taken.add(qid)
                out[unit["id"]] = (qid, pool[qid]["title"], how)
    return out


# ---------------------------------------------------------------------------
# Reading the infobox
# ---------------------------------------------------------------------------

COMMENT = re.compile(r"<!--.*?-->", re.S)
REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
# Templates that wrap a number without changing it. Anything else in a value
# is a construction this module has not been taught to read, and a value that
# needs one is refused rather than guessed at.
PASSTHROUGH = re.compile(r"\{\{\s*(?:formatnum:\s*|nowrap\s*\||nobold\s*\||"
                         r"small\s*\||val\s*\||increase\s*\||decrease\s*\||"
                         r"as of\s*\|)([^{}|]*?)(?:\|[^{}]*)?\}\}", re.I)

# Templates that add a note about the article rather than anything about the
# place: Eritrea's five regions all print their census figure with a
# {{citation needed}} hung off the end, and all five were refused as "not a
# whole number" for it. Removed, not expanded -- what they say is about the
# sourcing, and the sourcing is not the figure.
MAINTENANCE = re.compile(
    r"\{\{\s*(?:citation needed|cn|fact|clarify|clarification needed|when|"
    r"update|update after|dubious|disputed|better source needed|"
    r"verify source|unreliable source\?|page needed|specify|"
    r"according to whom|by whom|vague|original research\?|"
    r"efn|refn|sfn|nb|note|"
    # The arrows. {{increase}} beside a figure says which way it moved since
    # the last one, which is about the series and not about the figure;
    # Cambodia writes all three of its provinces that way.
    r"increase|decrease|steady|nochange|no change|gain|loss|growth|positive "
    r"decrease|negative increase)\b[^{}]*\}\}", re.I)

# A parameter that ran on into the next one. Maldives' Shaviyani Atoll writes
# "12,091 noofislands=51" on one line, and a population never contains an "=".
RAN_ON = re.compile(r"\s+[A-Za-z_][\w\s-]*=.*$")

NUMBER = re.compile(r"^\d{1,3}(?:[,    ]\d{3})+$|^\d+$")
YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
DATED_KEY = re.compile(r"^(?:pop|population)_?(?:census_?)?((?:19|20)\d\d)(?:_?census)?$")

# In the order a figure should be preferred. A census beats an estimate, and a
# total beats either, because a total is what the article settled on.
VALUE_KEYS = ("population_total", "population_census", "population_estimate",
              "population", "pop", "population_as_of_total")
YEAR_KEYS = {
    "population_total": ("population_as_of", "population_total_year",
                         "census_year", "population_date", "pop_year"),
    "population_census": ("population_census_year", "census_year",
                          "population_as_of", "population_date"),
    "population_estimate": ("population_estimate_year", "population_as_of",
                            "population_date", "pop_year"),
    "population": ("population_as_of", "census_year", "population_date",
                   "pop_year", "population_year"),
    "pop": ("pop_year", "population_as_of", "census_year"),
}


def clean(value: str) -> str:
    value = COMMENT.sub("", value)
    value = REF.sub("", value)
    value = MAINTENANCE.sub("", value)
    for _ in range(3):
        value = PASSTHROUGH.sub(lambda m: m.group(1), value)
    value = LINK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(1), value)
    value = TAG.sub(" ", value).replace("'''", "").replace("''", "")
    return " ".join(value.split()).strip()


def unclosed(value: str) -> str:
    """The value without the braces that end the infobox rather than it.

    ``infobox_lines`` hands the *last* parameter of a template the ``}}`` that
    closed the template, so an article whose population is the final line came
    back as "12998 }}" and was refused as not a number. Stripped only while
    the value has more closing braces than opening ones, so a figure written
    ``{{formatnum:1898133}}`` keeps its own.
    """
    while value.count("}}") > value.count("{{") and value.rstrip().endswith("}}"):
        value = value.rstrip()[:-2]
    return value


INFOBOX = re.compile(r"\{\{\s*infobox", re.I)


def params(wikitext: str) -> dict[str, str]:
    """Every infobox's parameters, keyed by a normalised name, first one first.

    Not only the first. An article can open with a box about something the
    place is -- a World Heritage Site, a protected area -- and carry the
    population in the settlement box beneath it; Mount Athos came back as
    having no population parameter that way. The first box to state a
    parameter still wins, so a second box never overrides the place's own.
    """
    out: dict[str, str] = {}
    lines: list[str] = []
    for m in INFOBOX.finditer(wikitext):
        lines += infobox_lines(wikitext[m.start():])
    if not lines:
        lines = infobox_lines(wikitext)
    for line in lines:
        line = line.lstrip().lstrip("|")
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = " ".join(key.split()).lower().replace(" ", "_")
        if key and key not in out:
            out[key] = unclosed(value)
    return out


def number(text: str) -> tuple[int | None, str]:
    """The whole number a value states, or why it states none."""
    body = RAN_ON.sub("", clean(text))
    if not body:
        return None, "empty"
    # "12,998 (2024)" -- the figure, with the year the article put beside it.
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", body)
    tail = ""
    if m:
        body, tail = m.group(1).strip(), m.group(2)
    if not NUMBER.match(body):
        return None, f"not a whole number: {body[:60]!r}"
    digits = re.sub(r"[^\d]", "", body)
    if not digits:
        return None, f"no digits: {body[:60]!r}"
    value = int(digits)
    if value <= 0:
        return None, "zero"
    return value, tail


def year_of(text: str) -> tuple[int | None, str]:
    """The single year a value names, or why it names none."""
    found = sorted({int(y) for y in YEAR.findall(clean(text))})
    if not found:
        return None, "no year in the value"
    if len(found) > 1:
        return None, f"several years in one value: {found}"
    return found[0], ""


# An infobox that prints Wikidata's figure rather than writing one down.
# France's regions ({{France metadata Wikidata|population_total}}), Latvia's
# municipalities ({{wikidata|property|...|P1082}}) and the Philippines' ({{PH
# wikidata|population_total}}) all do it, so the page shows a number and its
# wikitext holds none.
PULLS_FROM_WIKIDATA = re.compile(r"\{\{[^{}]*wikidata", re.I)
FROM_WIKIDATA = "the infobox displays Wikidata's figure"


def read(wikitext: str) -> tuple[int | None, int | None, str]:
    """(population, year, remark) from an article's infobox.

    A remark of FROM_WIKIDATA means the infobox shows Wikidata's own P1082,
    which the caller reads from the item the article belongs to.
    """
    fields = params(wikitext)
    if not fields:
        return None, None, "no infobox"
    for key in VALUE_KEYS:
        if key not in fields:
            continue
        value, tail = number(fields[key])
        if value is None and PULLS_FROM_WIKIDATA.search(fields[key]):
            return None, None, FROM_WIKIDATA
        if value is None:
            return None, None, f"{key}: {tail}"
        year, why = None, ""
        for yk in YEAR_KEYS.get(key, ("population_as_of",)):
            if yk in fields:
                year, why = year_of(fields[yk])
                if year:
                    break
        if year is None and tail:
            year, why = year_of(tail)
        if year is None and not why:
            why = "the infobox names no year for the figure"
        return value, year, why if year is None else ""
    # Templates that put the year in the parameter's name. Infobox Russian
    # federal subject writes "pop_2021census = 995,686", which is how the
    # Sakha Republic's article came back as having no population at all. The
    # newest census that carries a figure is read, dated by its own key.
    dated = sorted(((int(m.group(1)), key) for key in fields
                    for m in [DATED_KEY.match(key)] if m), reverse=True)
    last = ""
    for year, key in dated:
        value, why = number(fields[key])
        if value is not None:
            return value, year, ""
        last = f"{key}: {why}"
    if last:
        return None, None, last
    return None, None, "no population parameter in the infobox"


# The last word of what an article says it is. "[[Districts of Libya|District]]"
# is a district; "City" is a city. Infobox settlement's own parameter, so it is
# the article speaking about itself rather than this module inferring.
SETTLEMENT = frozenset({"city", "town", "village", "hamlet", "suburb", "locality",
                        "neighbourhood", "neighborhood", "settlement", "commune"})


def kind(wikitext: str) -> str:
    """What the article's infobox says the place is, in one word."""
    words = clean((params(wikitext) or {}).get("settlement_type", "")).lower().split()
    return words[-1].strip(" ()") if words else ""


def odd_one_out(kinds: list[str]) -> str | None:
    """The kind of division this country's units are, where they agree on one.

    Libya's 22 districts read 11 "District" and one "City": the city of Zawiya,
    whose article this module had resolved for Az Zawiyah district, and whose
    200,000 people are not the district's. A unit reading as a settlement in a
    country whose units read as divisions is the shape of that mistake, and
    this is what names the majority it stands against.
    """
    counted = [k for k in kinds if k]
    if not counted:
        return None
    best = max(set(counted), key=counted.count)
    if best in SETTLEMENT or counted.count(best) * 2 < len(kinds):
        return None
    return best


# ---------------------------------------------------------------------------
# What the map is missing
# ---------------------------------------------------------------------------

def country_shapes() -> dict[str, list[dict[str, Any]]]:
    """Every first-level shape the last build wrote, by country."""
    out: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((SITE / "admin1").glob("*.json")):
        rows = [u for u in read_json(path, []) if isinstance(u, dict)]
        if rows:
            out[path.stem] = rows
    return out


def ours(value: Any) -> bool:
    """Whether a population on the map was written by this reader."""
    return isinstance(value, dict) and \
        str(value.get("source") or "").startswith("English Wikipedia,")


def to_read(shapes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The shapes this reader answers for: every empty one, and every one it filled.

    Its own earlier answers are read again on every run rather than trusted,
    for two reasons. A run for a country replaces that country's rows in the
    output, and the first version of this reader chose the units to re-read
    from what the last build left empty -- which, once a build had joined its
    figures in, was only the units it had failed on. Re-running Malta after
    that build would have written five rows and deleted the 63 it had read
    before. And a guard added since an earlier run should apply to what that
    run wrote, not only to what comes after it.

    A population some other source wrote is never in this list, so no census
    figure is ever in reach of this reader.
    """
    return [u for u in shapes
            if (isinstance(u.get("population"), dict) and "status" in u["population"])
            or ours(u.get("population"))]


def countries() -> dict[str, dict[str, Any]]:
    """Each country's own record: its English name and its population."""
    out: dict[str, dict[str, Any]] = {}
    for row in read_json(SITE / "admin0.json", []):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pop = row.get("population")
        out[row["id"]] = {
            "name": row.get("name") or "",
            "population": float(pop["value"]) if isinstance(pop, dict)
            and isinstance(pop.get("value"), (int, float)) else None}
    return out


SOURCE = "English Wikipedia, {title} (infobox)"
UNDATED = ("English Wikipedia, {title} (infobox); the article gives no year "
           "for the figure")


def search(name: str, country_qid: str, langs: list[str]) -> dict[str, dict[str, Any]]:
    """Items in the country whose names read like this one, by full-text search.

    The last resort before a title is guessed, and still an index lookup
    rather than a guess: Wikidata's own search, over every label and alias in
    every language, restricted to items whose country (P17) is this one. It is
    what reaches a unit the country does not list among its divisions and the
    P131 search cut off before it got to -- Italy files more than four
    thousand things directly under Italy, and its five macro-regions were not
    among the first four thousand.
    """
    words = " ".join("".join(c if c.isalnum() else " " for c in name).split())
    if not words:
        return {}
    qids: list[str] = []
    # Statistical regions first. Italy's first level on this map is its five
    # NUTS-1 macro-regions, and a plain search for "Centro" or "Sud" among
    # everything in Italy is fifteen neighbourhoods deep before it reaches
    # one; among items carrying a NUTS code (P605) it is the first hit.
    for extra in (" haswbstatement:P605", ""):
        hits = ((api(DATA, action="query", list="search",
                     srsearch=f"{words} haswbstatement:P17={country_qid}{extra}",
                     srlimit=SEARCH_HITS, srnamespace=0) or {}).get("query") or {}
                ).get("search") or []
        qids += [h["title"] for h in hits if re.fullmatch(r"Q\d+", h.get("title") or "")]
    qids = list(dict.fromkeys(qids))
    return entities(qids, langs) if qids else {}


def claim_values(qid: str, prop: str) -> list[dict[str, Any]]:
    """One property's statements on one item, without the rest of the item.

    wbgetclaims rather than wbgetentities: a region's full claims run to
    hundreds of kilobytes and all this needs is one property of it.
    """
    payload = api(DATA, action="wbgetclaims", entity=qid, property=prop) or {}
    return (payload.get("claims") or {}).get(prop) or []


def wikidata_population(qid: str) -> tuple[int | None, int | None]:
    """The figure Wikidata's P1082 gives, and the year its P585 dates it to.

    The preferred statement if there is one, else the most recent normal one
    -- which is what an infobox reading "best" from Wikidata prints.
    """
    best: tuple[int, int, int] | None = None
    for claim in claim_values(qid, "P1082"):
        rank = {"preferred": 2, "normal": 1}.get(claim.get("rank"), 0)
        if not rank:
            continue
        value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        try:
            amount = int(float(str(value.get("amount", "")).lstrip("+")))
        except ValueError:
            continue
        year = 0
        for q in (claim.get("qualifiers") or {}).get("P585", []):
            time = ((q.get("datavalue") or {}).get("value") or {}).get("time", "")
            if len(time) >= 5 and time[1:5].isdigit():
                year = max(year, int(time[1:5]))
        key = (rank, year, amount)
        if amount > 0 and (best is None or key > best):
            best = key
    if best is None:
        return None, None
    return best[2], best[1] or None


# Square kilometres per unit, for the units Wikidata states areas in.
AREA_UNITS = {"Q712226": 1.0, "Q35852": 0.01, "Q232291": 2.589988,
              "Q25343": 1e-6, "Q81292": 4046.8564224e-6}


def refuted(qid: str, bbox: list[float] | None) -> str:
    """Why this item cannot be the shape, or "" if nothing says it cannot.

    Refutation only, never confirmation: a point inside a bounding box does
    not prove a place is the shape, and a place smaller than the box proves
    nothing either. What they can prove is the negative. A place whose stated
    area is larger than the box could not fit inside it -- Minsk Region,
    39,900 km^2, offered for a shape whose box is 253 km^2 -- and a place
    whose own coordinates lie far from the box is somewhere else: Argentina's
    "La Roja" (La Rioja, misspelt) reached Rojas Partido in Buenos Aires
    province, 4.6 degrees east of the province's box.

    "Far" is generous, because coordinates are not always where the place is.
    With a margin of a tenth of a degree the first run of this check refused
    Harbour Island, whose polygon in the boundary file sits 11 km from the
    island, and San Andres, whose Wikidata point is out at sea a degree north
    of the islands. Both figures were right. Minsk never needed the margin to
    be tight: its area alone refutes it.
    """
    if not bbox or len(bbox) != 4:
        return ""
    w, s_, e, n = bbox
    pad_x = pad_y = max(POINT_SLACK, e - w, n - s_)
    points = []
    for claim in claim_values(qid, "P625"):
        v = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if isinstance(v.get("latitude"), (int, float)) and isinstance(v.get("longitude"), (int, float)):
            points.append((v["longitude"], v["latitude"]))
    if points and not any(w - pad_x <= x <= e + pad_x and s_ - pad_y <= y <= n + pad_y
                          for x, y in points):
        x, y = points[0]
        return f"its coordinates ({y:.2f}, {x:.2f}) lie outside the shape"
    box, km2 = box_km2(bbox), area_km2(qid)
    if box and km2 is not None and km2 > box * AREA_SLACK + 50:
        return f"its area, {km2:,.0f} km^2, cannot fit in the shape's {box:,.0f} km^2 box"
    return ""


def area_km2(qid: str) -> float | None:
    """The item's stated area in square kilometres, if it states one."""
    for claim in claim_values(qid, "P2046"):
        v = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        unit = str(v.get("unit", "")).rsplit("/", 1)[-1]
        try:
            return float(str(v.get("amount", "")).lstrip("+")) * AREA_UNITS[unit]
        except (KeyError, ValueError):
            continue
    return None


def box_km2(bbox: list[float] | None) -> float | None:
    if not bbox or len(bbox) != 4:
        return None
    w, s_, e, n = bbox
    return abs(n - s_) * 111.32 * abs(e - w) * 111.32 * math.cos(math.radians((n + s_) / 2))


def too_small(qid: str, bbox: list[float] | None) -> str:
    """Why a place reached only through a redirect is too small to be the shape.

    The redirect stage takes the article Wikipedia sends a bare name to, and a
    region named after its capital sends the name to the capital. Every
    earlier stage had refused these as ties -- Morogoro Region, Morogoro the
    city and Morogoro District all fold to one name -- and the redirect then
    walked past the refusal to the town: 471,409 people for a region of three
    million, and the same for Brikama, Basse and Ajdabiya. A place offered
    that way must state an area, and fill a reasonable share of the shape's
    box, before it is read. Malta's localities and Latvia's state cities,
    which are towns and are the shapes, do.
    """
    box = box_km2(bbox)
    if not box:
        return ""
    area = area_km2(qid)
    if area is None:
        return "reached only by a redirect, and Wikidata states no area to size it by"
    if area < box * MIN_FILL:
        return (f"reached only by a redirect, and its {area:,.0f} km^2 is "
                f"{area / box:.1%} of the shape's {box:,.0f} km^2 box")
    return ""


def in_country(qid: str, country_qid: str) -> bool:
    claims = claims_of(qid)
    return country_qid in statements(claims, "P17") or \
        country_qid in statements(claims, "P131")


def by_title(unit: dict[str, Any], country: str, country_qid: str,
             taken: set[str]) -> tuple[str, str] | None:
    """The article Wikipedia itself sends this name to, if it is in the country.

    Burkina Faso renamed its thirteen regions in 2025, and the boundary file
    still carries the old names. Wikidata moved its labels with the rename and
    kept some of the old ones as aliases, which reached six of the thirteen;
    the other seven old names survive only as Wikipedia redirects --
    "Boucle du Mouhoun Region" is a redirect to Bankui Region. Following a
    redirect is following the encyclopaedia's own statement that the two are
    one place, so it is taken, but only after the page it lands on is proved
    to be an item located in this country, not a disambiguation page, and not
    an item another shape already holds.
    """
    name = unit["name"].strip()
    titles = [f"{name} Region ({country})", f"{name} Region, {country}",
              f"{name} ({country})", f"{name}, {country}",
              f"{name} Region", name]
    titles = list(dict.fromkeys(titles))
    q = (api(WIKI, action="query", prop="pageprops",
             ppprop="wikibase_item|disambiguation", titles="|".join(titles),
             redirects="1") or {}).get("query") or {}
    normal = {n["from"]: n["to"] for n in q.get("normalized") or []}
    moved = {r["from"]: r["to"] for r in q.get("redirects") or []}
    pages = {pg.get("title"): pg for pg in q.get("pages") or []}
    for title in titles:
        landed = moved.get(normal.get(title, title), normal.get(title, title))
        page = pages.get(landed) or {}
        props = page.get("pageprops") or {}
        if page.get("missing") or "disambiguation" in props:
            continue
        item = props.get("wikibase_item")
        if not item or item in taken or item == country_qid:
            continue
        if in_country(item, country_qid):
            return item, landed
    return None


# Articles named by declaration, for first-level units whose names on the map
# no index can connect to their article. Italy's first level on this map is
# its five NUTS-1 macro-regions, written as Eurostat writes them; Wikidata
# keeps "Nord-Est" as an alias of Northeast Italy and nothing of the kind for
# the other four, and its search offers neighbourhoods called Centro and
# islands called Isole instead. Greece's are its decentralised
# administrations, in a Greek-English hybrid the boundary file invented.
#
# A declaration names an article and proves nothing: the page must still
# exist and not be a disambiguation page, its item must still be located in
# the country and held by no other shape, its coordinates and area must not
# refute it, and its infobox must still be read. It only replaces the search.
TITLES: dict[tuple[str, str], str] = {
    ("ITA", "Centro"): "Central Italy",
    ("ITA", "Isole"): "Insular Italy",
    ("ITA", "Nord-Ovest"): "Northwest Italy",
    # Not ("ITA", "Sud"): "Southern Italy". It was declared, and it is the
    # Mezzogiorno *with* Sicily and Sardinia -- 19.7 million against the
    # NUTS-1 region's 13.4 -- so Italy's five summed to 65.3 million against
    # 58.9, over by exactly Insular Italy. No English article is the mainland
    # south alone, and a sum that counts the islands twice is the wrong
    # number this project ranks below a gap.
    ("GRC", "Egean"): "Decentralized Administration of the Aegean",
    ("GRC", "Peloponisos-W. Greece & Ionian"):
        "Decentralized Administration of Peloponnese, Western Greece and the Ionian",
}


def declared(iso3: str, unit: dict[str, Any], country_qid: str,
             taken: set[str]) -> tuple[str, str] | None:
    """The declared article for this unit, if TITLES names one and it holds."""
    title = TITLES.get((iso3, unit["name"]))
    if not title:
        return None
    q = (api(WIKI, action="query", prop="pageprops",
             ppprop="wikibase_item|disambiguation", titles=title,
             redirects="1") or {}).get("query") or {}
    for page in q.get("pages") or []:
        props = page.get("pageprops") or {}
        item = props.get("wikibase_item")
        if page.get("missing") or "disambiguation" in props or not item:
            log(f"  {unit['name']}: the declared article {title!r} is not an article")
            return None
        if item in taken or item == country_qid or not in_country(item, country_qid):
            log(f"  {unit['name']}: the declared article {title!r} is {item}, "
                f"which is another shape's or not in the country")
            return None
        return item, page.get("title") or title
    return None


def article_for(iso3: str, units: list[dict[str, Any]],
                shapes: list[dict[str, Any]] | None = None,
                country: str = "") -> dict[str, tuple[str, str, str]]:
    """unit id -> (Wikidata item, English title, how), for as many as can be proved.

    Candidates are drawn in stages, narrowest first, and each stage is handed
    what the ones before it settled, so a wider pool can add a match and never
    take one away by making it ambiguous.

    0. The item the build already joined to this shape. Nothing this module
       could work out by name is better evidence than a match the map has
       already made.
    1. What the country says it is divided into (P150). Bulgaria's 28
       provinces are there and Sofia the city is not, which is what separates
       Sofia Province from the capital on the only name the map gives it.
    2. What says it sits directly in the country (P131), which is what a
       first-level unit is and what a town inside one is not.
    3. What the country's divisions are divided into, which is how Malta's 68
       local councils are reached under its five regions.
    4. Wikidata's full-text search, restricted to the country.
    5. The article Wikipedia's own redirects send the name to.
    """
    shapes = shapes or units
    qid = country_item(iso3)
    if not qid:
        log(f"{iso3}: no Wikidata item carries this ISO code; skipped")
        return {}
    claims = claims_of(qid)
    divisions = statements(claims, "P150")
    langs = languages(claims)

    mine = {u["id"] for u in units}
    known = {u["id"]: u["wikidata"] for u in units if u.get("wikidata")}
    others = {u["wikidata"] for u in shapes
              if u.get("wikidata") and u["id"] not in mine}
    # The country itself is never a unit of itself -- unless it has only the
    # one shape, as the Vatican does.
    if len(shapes) > 1:
        others.add(qid)

    pool = entities(set(known.values()) | set(divisions), langs)
    found: dict[str, tuple[str, str, str]] = {}
    for uid, item in known.items():
        title = (pool.get(item) or {}).get("title")
        if title:
            found[uid] = (item, title, "wikidata")
    # A shape the build has already joined to an item is that item. Where the
    # item has no English article there is nothing to read, and guessing at a
    # different article by name would be guessing against evidence.
    settled = set(known)
    # Measured on every shape the country has, so a late stage with two
    # names left does not forget that Seychelles cuts all of them.
    cut = truncates(shapes)

    def short() -> list[dict[str, Any]]:
        return [u for u in units if u["id"] not in found and u["id"] not in settled]

    def widen(label: str, qids: Iterable[str]) -> None:
        nonlocal found
        fresh = set(qids) - set(pool)
        if fresh and short():
            pool.update(entities(fresh, langs))
        before = len(found)
        found = resolve(short(), pool, found, others, cut)
        if len(found) > before:
            log(f"{iso3}: {label} resolved {len(found) - before} more")

    for unit in short():
        taken = {item for item, _, _ in found.values()} | others
        hit = declared(iso3, unit, qid, taken)
        if hit:
            found[unit["id"]] = (hit[0], hit[1], "declaration")
    widen("the country's own divisions", ())
    if short():
        widen("what sits directly in the country", children(qid))
    if short() and divisions:
        deeper: set[str] = set()
        for division in divisions[:GRANDCHILDREN]:
            deeper |= set(contains(division))
        widen("one level further down", deeper)
    for unit in short():
        hits = search(unit["name"], qid, langs)
        if not hits:
            continue
        pool.update(hits)
        before = len(found)
        found = resolve([unit], hits, found, others, cut)
        if len(found) > before:
            log(f"  {unit['name']}: found by searching the country")
        else:
            # What the search did offer, so the next run can be taught the
            # name rather than the gap being re-diagnosed from nothing.
            offered = [f"{q} {(v['names'] or ['?'])[0]!r}" for q, v in list(hits.items())[:5]]
            log(f"  {unit['name']}: searching the country offered {', '.join(offered)}")
    if country:
        for unit in short():
            taken = {item for item, _, _ in found.values()} | others
            hit = by_title(unit, country, qid, taken)
            if hit:
                found[unit["id"]] = (hit[0], hit[1], "redirect")
    return found


def overcount(iso3: str, shapes: list[dict[str, Any]], read_out: list[dict[str, Any]],
              national: float | None) -> float | None:
    """The country's first level, summed with what this run read, over its total.

    Printed and never acted on, because it cannot say which figure is wrong
    and a sum over a whole country is not a clean test: vintages differ, and
    Kuwait's governorates add to 110% of an older national figure with no
    unit mis-read. What it is for is the case no single unit can show. Italy's
    five macro-regions each read correctly on their own and summed to 111%,
    because one article's "Southern Italy" included the islands another
    article had already counted.
    """
    if not national:
        return None
    mine = {r["unit"]["id"]: r["value"] for r in read_out}
    total = 0.0
    for shape in shapes:
        if shape["id"] in mine:
            total += mine[shape["id"]]
            continue
        pop = shape.get("population")
        if isinstance(pop, dict) and isinstance(pop.get("value"), (int, float)) \
                and not ours(pop):
            total += pop["value"]
    share = total / national
    if share > OVERCOUNT:
        log(f"  {iso3}: its first level now sums to {total:,.0f}, "
            f"{share:.0%} of the country's {national:,.0f} -- check for a unit "
            f"counted twice")
    return share


def run(iso3: str, units: list[dict[str, Any]], national: float | None,
        *, probe: bool = False, shapes: list[dict[str, Any]] | None = None,
        country: str = "") -> list[dict[str, Any]]:
    found = article_for(iso3, units, shapes, country)
    log(f"{iso3}: {len(units)} units without a population, {len(found)} resolved")
    read_out: list[dict[str, Any]] = []
    for unit in units:
        hit = found.get(unit["id"])
        if not hit:
            why = ("its Wikidata item has no English article"
                   if unit.get("wikidata") else "no article resolved")
            log(f"  {unit['name']}: {why}")
            continue
        item, title, how = hit
        if probe or how != "wikidata":
            log(f"  {unit['name']} -> {title} ({item}, matched by {how})")
        if probe:
            continue
        why = refuted(item, unit.get("bbox"))
        if not why and how == "redirect":
            why = too_small(item, unit.get("bbox"))
        if why:
            log(f"  {unit['name']} -> {title} ({item}): {why}; refused")
            continue
        text = ((api(WIKI, action="parse", page=title, prop="wikitext",
                     redirects="1") or {}).get("parse") or {})
        wikitext = text.get("wikitext") or ""
        landed = text.get("title") or title
        if not wikitext:
            log(f"  {unit['name']} -> {title}: no wikitext")
            continue
        value, year, remark = read(wikitext)
        pulled = remark == FROM_WIKIDATA
        if pulled:
            # What the reader of the page sees is Wikidata's figure, so that
            # is what is read -- from the item this article belongs to, and
            # with the year Wikidata dates it to.
            value, year = wikidata_population(item)
            remark = "" if year else "Wikidata dates the figure to no year"
            if value is None:
                log(f"  {unit['name']} -> {landed}: its infobox displays "
                    f"Wikidata's figure and {item} has no P1082")
                continue
        if value is None:
            log(f"  {unit['name']} -> {landed}: {remark}")
            continue
        if national and value > national * 1.02:
            # A unit cannot hold more people than its country. Where it reads
            # that way the article is not the unit's -- the commonest way for
            # a resolution to go wrong is to land on the country itself.
            log(f"  {unit['name']} -> {landed}: {value:,} exceeds the country's "
                f"own {national:,.0f}; refused")
            continue
        read_out.append({"unit": unit, "title": landed, "value": value,
                         "year": year, "remark": remark, "kind": kind(wikitext),
                         "item": item if pulled else None})

    rows: list[dict[str, Any]] = []
    overcount(iso3, shapes or units, read_out, national)
    division = odd_one_out([r["kind"] for r in read_out])
    for r in read_out:
        unit, landed, value, year = r["unit"], r["title"], r["value"], r["year"]
        # A settlement inside the unit is not the unit -- unless the article is
        # titled the way the map names the place, in which case it is the unit
        # and the article simply calls it a city.
        if (division and r["kind"] in SETTLEMENT
                and not same_place_name(unit["name"], disambiguated(landed))):
            log(f"  {unit['name']} -> {landed}: reads as a {r['kind']} where "
                f"{iso3}'s units read as a {division}; refused")
            continue
        where = (SOURCE if year else UNDATED).format(title=landed)
        if r["item"]:
            where = where.replace("(infobox)", f"(infobox, which displays "
                                               f"Wikidata {r['item']}'s P1082)")
        if not year:
            log(f"  {unit['name']} -> {landed}: {value:,}, undated ({r['remark']})")
        rows.append(record(
            f"{iso3}-WP-{slugify(unit['name'])}", unit["name"],
            level="admin1", parent=iso3, country=iso3,
            # Bound to the polygon this reader started from, so the build
            # never has to find it again by name. This reader knows exactly
            # which shape it read for; a name-keyed join could only lose that.
            shape_id=unit["id"], match_by="shape_id",
            population=measure(value, unit="people", year=year, source=where),
            sources=[{"field": "population", "name": "Wikipedia",
                      "url": "https://en.wikipedia.org/wiki/"
                             + urllib.parse.quote(landed.replace(" ", "_")),
                      "year": year, "license": LICENCE}]))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", action="append", default=[],
                    help="ISO3; repeatable. Default: every country with a gap.")
    ap.add_argument("--probe", action="store_true",
                    help="Print what each unit resolves to and read nothing.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Stop after this many countries.")
    args = ap.parse_args()

    shapes = country_shapes()
    nations = countries()
    wanted = [c.upper() for c in args.country] or \
        sorted(c for c, rows in shapes.items() if to_read(rows))
    if args.limit:
        wanted = wanted[:args.limit]

    rows: list[dict[str, Any]] = []
    failed: set[str] = set()
    for iso3 in wanted:
        units = to_read(shapes.get(iso3, []))
        if not units:
            log(f"{iso3}: nothing this reader answers for")
            continue
        nation = nations.get(iso3) or {}
        try:
            rows.extend(run(iso3, units, nation.get("population"), probe=args.probe,
                            shapes=shapes[iso3], country=nation.get("name", "")))
        except Exception as exc:  # one country's outage is not the run's
            log(f"{iso3}: failed -- {exc}")
            failed.add(iso3)

    if args.probe:
        return
    kept = read_json(PROCESSED / OUT, [])
    if kept:
        # A run replaces every country it read -- including one that read
        # nothing this time, whose old rows must not survive the re-reading
        # that decided against them -- and keeps every other country's rows.
        # A country whose run failed keeps what it had: an outage is not a
        # finding that the figures are gone.
        replaced = set(wanted) - failed
        rows = [r for r in kept if r.get("country") not in replaced] + rows
    write_json(PROCESSED / OUT, sorted(rows, key=lambda r: r["id"]))
    log(f"wrote {len(rows)} records to {OUT}")


if __name__ == "__main__":
    main()
