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
    r"autonomous|administrative|capital|metropolitan|"
    r"of|the|and|de|du|des|da|do|del|la|le|les|el|al)\b", re.I)


def fold(text: str | None) -> str:
    """A name reduced to what a boundary file and an encyclopaedia agree on."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower()).translate(FOLD)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = GENERIC.sub(" ", text)
    return "".join(c for c in text if c.isalnum())


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


def contains(qid: str) -> list[str]:
    """What an item says it is divided into: its P150 statements.

    The P131 search alone missed whole countries. Malta files its 68 local
    councils under one of five regions and not under Malta, so a search for
    what sits directly in the country returned 62 items and matched three, all
    three wrong. Reading the division downwards instead of upwards reaches
    them, and reaches a first-level unit whose own article is the only place
    its population is written.
    """
    payload = api(DATA, action="wbgetentities", ids=qid, props="claims")
    item = ((payload or {}).get("entities") or {}).get(qid) or {}
    out = []
    for claim in (item.get("claims") or {}).get("P150", []):
        value = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
        if isinstance(value, dict) and value.get("id"):
            out.append(value["id"])
    return out


def entities(qids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Labels, aliases and the English article title, for a list of items."""
    out: dict[str, dict[str, Any]] = {}
    qids = list(dict.fromkeys(qids))
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        payload = api(DATA, action="wbgetentities", ids="|".join(chunk),
                      props="labels|aliases|sitelinks", languages="en",
                      sitefilter="enwiki")
        for qid, item in (payload.get("entities") or {}).items():
            labels = item.get("labels") or {}
            aliases = item.get("aliases") or {}
            names = [(labels.get("en") or {}).get("value")]
            names += [a.get("value") for a in aliases.get("en") or []]
            title = ((item.get("sitelinks") or {}).get("enwiki") or {}).get("title")
            out[qid] = {"names": [n for n in names if n], "title": title}
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
            preset: dict[str, tuple[str, str, str]] | None = None
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
    taken: set[str] = {qid for qid, _, _ in out.values()}

    def unique(hits: list[str]) -> str | None:
        hits = [q for q in dict.fromkeys(hits) if q not in taken]
        return hits[0] if len(hits) == 1 else None

    def exact(key: str) -> str | None:
        return unique(by_name.get(key, []))

    cutting = truncates(units)

    def prefix(key: str, raw: str) -> str | None:
        if len(key) < PREFIX_MIN:
            return None
        cut = cutting and len(raw.strip()) == TRUNCATED_AT
        return unique([q for form, qids in by_name.items()
                       if form.startswith(key)
                       and (cut or len(form) - len(key) <= PREFIX_TAIL)
                       for q in qids])

    def near(key: str, raw: str) -> str | None:
        if len(key) < NEAR_MIN:
            return None
        return unique([q for form, qids in by_name.items()
                       if len(form) >= NEAR_MIN
                       and SequenceMatcher(None, key, form).ratio() >= NEAR
                       for q in qids])

    for how, find in (("name", lambda key, raw: exact(key)),
                      ("prefix", prefix), ("near", near)):
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


def params(wikitext: str) -> dict[str, str]:
    """The first infobox's parameters, keyed by a normalised name."""
    out: dict[str, str] = {}
    for line in infobox_lines(wikitext):
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


def read(wikitext: str) -> tuple[int | None, int | None, str]:
    """(population, year, remark) from an article's infobox."""
    fields = params(wikitext)
    if not fields:
        return None, None, "no infobox"
    for key in VALUE_KEYS:
        if key not in fields:
            continue
        value, tail = number(fields[key])
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

def units_without_population() -> dict[str, list[dict[str, Any]]]:
    """The first-level shapes whose population is a gap, by country.

    Read from the built site files rather than from the boundary files,
    because what this reader fills is defined by what the last build left
    empty. It can only under-report: a unit that has gained a population
    since is skipped, which is the safe direction.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((SITE / "admin1").glob("*.json")):
        iso3 = path.stem
        rows = read_json(path, [])
        missing = [u for u in rows if isinstance(u, dict)
                   and isinstance(u.get("population"), dict)
                   and "status" in u["population"]]
        if missing:
            out[iso3] = missing
    return out


def country_populations() -> dict[str, float]:
    out: dict[str, float] = {}
    for row in read_json(SITE / "admin0.json", []):
        pop = (row or {}).get("population")
        if isinstance(pop, dict) and isinstance(pop.get("value"), (int, float)):
            out[row["id"]] = float(pop["value"])
    return out


SOURCE = "English Wikipedia, {title} (infobox)"
UNDATED = ("English Wikipedia, {title} (infobox); the article gives no year "
           "for the figure")


def article_for(iso3: str, units: list[dict[str, Any]]
                ) -> dict[str, tuple[str, str, str]]:
    """unit id -> (Wikidata item, English title, how), for as many as can be proved.

    Three sources of candidates, tried in that order because that is the order
    of how much they prove.

    1. The item the build already joined to this shape. 248 of the 610 shapes
       carry one, and nothing this module could work out by name is better
       evidence than a match the map has already made.
    2. What the country says it is divided into (P150), and what those are
       divided into, which is how Malta's 68 local councils are reached: they
       sit under one of five regions and not under Malta, so the search below
       never saw them.
    3. What says it sits directly in the country (P131), which is what a
       first-level unit is and what a town inside one is not.
    """
    qid = country_item(iso3)
    if not qid:
        log(f"{iso3}: no Wikidata item carries this ISO code; skipped")
        return {}

    known = {u["id"]: u["wikidata"] for u in units if u.get("wikidata")}
    divisions = contains(qid)
    pool = entities(set(known.values()) | set(divisions) | set(children(qid)))

    preset: dict[str, tuple[str, str, str]] = {}
    for uid, item in known.items():
        title = (pool.get(item) or {}).get("title")
        if title:
            preset[uid] = (item, title, "wikidata")
    # A shape the build has already joined to an item is that item. Where the
    # item has no English article there is nothing to read, and guessing at a
    # different article by name would be guessing against evidence.
    settled = set(known)

    found = resolve([u for u in units if u["id"] not in settled], pool, preset)
    short = [u for u in units if u["id"] not in found and u["id"] not in settled]
    if short and divisions:
        deeper: set[str] = set()
        for division in divisions[:GRANDCHILDREN]:
            deeper |= set(contains(division))
        deeper -= set(pool)
        if deeper:
            log(f"{iso3}: {len(short)} still unresolved; reading {len(deeper)} "
                f"units one level further down")
            pool.update(entities(deeper))
            # preset carries the first pass forward, so a wider pool can only
            # add a match and never take one away by making it ambiguous.
            found = resolve(short, pool, found)
    return found


def run(iso3: str, units: list[dict[str, Any]], national: float | None,
        *, probe: bool = False) -> list[dict[str, Any]]:
    found = article_for(iso3, units)
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
        text = ((api(WIKI, action="parse", page=title, prop="wikitext",
                     redirects="1") or {}).get("parse") or {})
        wikitext = text.get("wikitext") or ""
        landed = text.get("title") or title
        if not wikitext:
            log(f"  {unit['name']} -> {title}: no wikitext")
            continue
        value, year, remark = read(wikitext)
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
                         "year": year, "remark": remark, "kind": kind(wikitext)})

    rows: list[dict[str, Any]] = []
    division = odd_one_out([r["kind"] for r in read_out])
    for r in read_out:
        unit, landed, value, year = r["unit"], r["title"], r["value"], r["year"]
        # A settlement inside the unit is not the unit -- unless the article is
        # titled the way the map names the place, in which case it is the unit
        # and the article simply calls it a city.
        if (division and r["kind"] in SETTLEMENT
                and fold(unit["name"]) != fold(disambiguated(landed))):
            log(f"  {unit['name']} -> {landed}: reads as a {r['kind']} where "
                f"{iso3}'s units read as a {division}; refused")
            continue
        where = (SOURCE if year else UNDATED).format(title=landed)
        if not year:
            log(f"  {unit['name']} -> {landed}: {value:,}, undated ({r['remark']})")
        rows.append(record(
            f"{iso3}-WP-{slugify(unit['name'])}", unit["name"],
            level="admin1", parent=iso3, country=iso3,
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

    missing = units_without_population()
    nationals = country_populations()
    wanted = [c.upper() for c in args.country] or sorted(missing)
    if args.limit:
        wanted = wanted[:args.limit]

    rows: list[dict[str, Any]] = []
    for iso3 in wanted:
        units = missing.get(iso3)
        if not units:
            log(f"{iso3}: nothing missing a population")
            continue
        try:
            rows.extend(run(iso3, units, nationals.get(iso3), probe=args.probe))
        except Exception as exc:  # one country's outage is not the run's
            log(f"{iso3}: failed -- {exc}")

    if args.probe:
        return
    kept = read_json(PROCESSED / OUT, [])
    if args.country and kept:
        # A per-country run tops up the file rather than replacing it, and
        # replaces every country it was asked for -- including one that read
        # nothing this time, whose old rows must not survive the re-reading
        # that decided against them.
        rows = [r for r in kept if r.get("country") not in set(wanted)] + rows
    write_json(PROCESSED / OUT, sorted(rows, key=lambda r: r["id"]))
    log(f"wrote {len(rows)} records to {OUT}")


if __name__ == "__main__":
    main()
