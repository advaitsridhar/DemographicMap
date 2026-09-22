#!/usr/bin/env python3
"""Europe: religion, language and ethnicity from each unit's own Wikipedia
article, at first and second level.

This is the Indonesian method (``indonesia.py``) turned on Europe, by the
owner's decision of 20 September 2026: read what a place's article publishes
about who lives there, take it only where the article cites something and the
citation can be dated, and leave a stated reason where it cannot.

Europe differs from Indonesia in three ways this module has to handle rather
than paper over:

* **A different edition per country.** The Romanian article of a commune
  carries its 2021 census ethnicity and religion tables; the English one
  carries a sentence. The spec names the edition, and the source line names
  it too, because which edition a figure was read from is part of where it
  came from.
* **A different template per country.** There is no European infobox. Some
  countries put the composition in a table under a "Demographics" heading,
  some in the infobox, and most nowhere at all.
* **A list is not a composition.** Many articles name the languages spoken in
  a place without a share for any of them. That is a list, and this module
  never turns one into a composition.

Usage:
    python -m scripts.fetch_census.europe_wiki --probe ro:Adamclisi,_Constanța
    python -m scripts.fetch_census.europe_wiki --country BGR
    python -m scripts.fetch_census.europe_wiki
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_json, log,
                      read_json, record, write_json)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402
from probe_wikitable import infobox_lines, tables  # noqa: E402

PAUSE = 0.3
BACKOFF = (60, 120, 240)


def api(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def fetch(title: str, lang: str) -> tuple[str, str]:
    """The article's wikitext and the title it resolved to."""
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    time.sleep(PAUSE)
    for wait in (*BACKOFF, None):
        try:
            data = http_json(f"{api(lang)}?{q}", timeout=90)
            break
        except RuntimeError as exc:
            if wait is None:
                raise
            log(f"  [{lang}] {title!r}: {exc}; waiting {wait}s")
            time.sleep(wait)
    parsed = data.get("parse") or {}
    text = parsed.get("wikitext") or ""
    if not text:
        log(f"  [{lang}] {title!r}: nothing ({(data.get('error') or {}).get('code')})")
    return text, parsed.get("title") or title


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

PROBE_LOG = PROCESSED / "europe_wiki_probe.log"
_probe_lines: list[str] = []


def say(line: str) -> None:
    """Print, and keep it for the probe's own log file.

    The runner tees every run into data/processed/last-run.log and commits
    it, so two adapters dispatched minutes apart overwrite each other's
    answer -- the first Europe probe's log was gone by the time it was read,
    replaced by an unrelated catalogue listing. A probe's whole product is
    what it printed, so it also writes a file of its own that nothing else
    touches.
    """
    log(line)
    _probe_lines.append(line)


COMPOSITION = re.compile(
    r"etni|na[tţț]ional|nacional|национал|етни|этни|религ|confes|конфес|рели|"
    r"veroispoved|vallás|nemzetiség|národnost|náboženstv|jezik|język|"
    r"limba|език|мова|language|religio|ethnic|nationalit|faith|мов|"
    r"anyanyelv|kalba|valoda|keel|usk|rahvus|tautyb|tautīb|"
    r"demogra|населен|становништв|composition|населення|popula|"
    r"вероисповед|вероизповед|изповед|роден\s+език|склад|состав|fe[j]?e|besim|gjuh|struktur",
    re.I)

HEADING = re.compile(r"^\s*(=+)\s*(.+?)\s*\1\s*$", re.M)
REF = re.compile(r"<ref\b([^>/]*)(?:/>|>(.*?)</ref>)", re.S | re.I)


def sections(wikitext: str) -> list[tuple[str, str]]:
    """(heading, body) for every section, with the lead under ""."""
    out: list[tuple[str, str]] = []
    last, name = 0, ""
    for m in HEADING.finditer(wikitext):
        out.append((name, wikitext[last:m.start()]))
        name, last = m.group(2), m.end()
    out.append((name, wikitext[last:]))
    return out


def probe(spec: str, rows: int, width: int) -> None:
    """Print one article's infobox parameters and its composition sections.

    A European unit's article almost never names the field in the table's
    own header -- Bulgaria's ethnic table starts "Численост | Дял (в %)" and
    says what it counts in the heading above it -- so the tables are printed
    under the section they sit in, and a section is shown when either its
    heading or its first rows name one of the three fields.

    ``spec`` is "lang:Title"; a title carries underscores rather than spaces,
    because the runner hands this command to xargs and xargs splits on
    whitespace.
    """
    lang, _, title = spec.partition(":")
    wikitext, resolved = fetch(title.replace("_", " "), lang)
    say(f"\n===== [{lang}] {resolved!r}, {len(wikitext):,} bytes")
    if not wikitext:
        return
    say("  -- infobox --")
    for entry in infobox_lines(wikitext):
        head, _, rest = entry.partition("=")
        key = head.strip(" |")
        value = " ".join(rest.split())
        if COMPOSITION.search(key) or COMPOSITION.search(value[:60]):
            say(f"    * {key} = {value[:4 * width]}")
        else:
            say(f"      {key} = {value[:width]}")
    say("  -- sections --")
    for name, body in sections(wikitext):
        found = tables(body)
        flat = " ".join(" ".join(r) for t in found for r in t[:3])
        interesting = COMPOSITION.search(name) or COMPOSITION.search(flat[:400])
        if not found:
            say(f"    [{name}] no table")
            continue
        if not interesting:
            say(f"    [{name}] {len(found)} table(s), not a composition: {flat[:70]}")
            continue
        say(f"    [{name}] {len(found)} table(s)")
        for m in REF.finditer(body):
            attrs, cite = m.group(1), m.group(2)
            say(f"      ref{attrs.strip() and ' ' + attrs.strip() or ''}: "
                f"{' '.join((cite or '').split())[:3 * width]}")
        for i, table in enumerate(found, 1):
            say(f"      table {i}: {len(table)} rows")
            for row in table[:rows]:
                say("        " + " | ".join(c[:width] for c in row))
            if len(table) > rows:
                say(f"        ... {len(table) - rows} more rows")


# ---------------------------------------------------------------------------
# From the shape's name to the article
# ---------------------------------------------------------------------------

def langlinks(titles: list[str], src: str, dest: str) -> dict[str, str]:
    """{title asked for: the title of the same article in ``dest``}.

    The shapes this map draws carry English names and several of these
    countries keep their composition only in their own edition, so the join
    between the two is an interlanguage link and not a transliteration
    invented here. A name that transliterates two ways -- and Bulgarian,
    Serbian and Macedonian all have several romanisations in use -- would
    otherwise be a guess, and a guess that lands on the wrong article is the
    mis-match this project treats as worse than a gap.

    Fifty titles a request, which is the API's limit for a non-bot client.
    A title the edition does not have simply has no entry, and the caller
    says so on the record.
    """
    out: dict[str, str] = {}
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        q = urllib.parse.urlencode({
            "action": "query", "prop": "langlinks", "lllang": dest,
            "lllimit": "500", "titles": "|".join(batch), "redirects": "1",
            "format": "json", "formatversion": "2"})
        time.sleep(PAUSE)
        data = http_json(f"{api(src)}?{q}", timeout=90)
        query = data.get("query") or {}
        # The API answers about the title it ended at, so the two hops it
        # may have taken -- case and underscore normalisation, then a
        # redirect -- are followed back to the title that was asked for.
        back: dict[str, str] = {}
        for hop in ("normalized", "redirects"):
            for step in query.get(hop) or []:
                back[step["to"]] = back.get(step["from"], step["from"])
        for page in query.get("pages") or []:
            links = page.get("langlinks") or []
            if not links:
                continue
            asked = back.get(page["title"], page["title"])
            out[asked] = links[0]["title"]
    return out


def category_members(category: str, lang: str) -> list[str]:
    """The article titles in one category, in the order the API gives them.

    This is how a country's own list of unit names is obtained without
    typing a hundred and forty-five of them into this file and without
    inventing a transliteration: the boundary file spells a Serbian
    municipality "Cacak City" and Serbia spells it "Cacak" with three
    diacritics, and match_spellings joins the two without guessing at
    either.
    """
    out: list[str] = []
    cont: dict[str, str] = {}
    while True:
        q = urllib.parse.urlencode({
            "action": "query", "list": "categorymembers",
            "cmtitle": category, "cmlimit": "500", "cmnamespace": "0",
            "format": "json", "formatversion": "2", **cont})
        time.sleep(PAUSE)
        data = http_json(f"{api(lang)}?{q}", timeout=90)
        out.extend(m["title"] for m in
                   (data.get("query") or {}).get("categorymembers") or [])
        cont = data.get("continue") or {}
        if not cont:
            return out


LINK_TARGET = re.compile(r"\[\[([^\]|#<>\[]+?)(?:\|[^\]]*)?\]\]")
NOT_AN_ARTICLE = re.compile(r"^(file|image|category|template|help|wikipedia|"
                            r"wikt|s|commons|:)\s*:", re.I)


def link_targets(title: str, lang: str) -> list[str]:
    """The articles one article links to, in order, without repeats.

    Serbia has no category listing its municipalities -- the one that looks
    like it holds them holds a single article, its own list -- so the list
    is that article, and what it links to at each row is the municipality's
    own page. Read from the wikitext rather than from the rendered table,
    because a table cell prints a link's display text and throws the title
    away, and the title is the whole point.
    """
    wikitext, _ = fetch(title, lang)
    out: list[str] = []
    seen: set[str] = set()
    for m in LINK_TARGET.finditer(wikitext):
        target = " ".join(m.group(1).split())
        if not target or NOT_AN_ARTICLE.match(target) or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


# The Serbian, Croatian and Montenegrin alphabets romanise with diacritics
# and one digraph, and a boundary file that has romanised them further
# writes "Cacak" for Cacak and "Arandjelovac" for Arandelovac -- the second
# a letter longer than the name it came from, which is why the positional
# matcher above cannot be used here. Folding both sides to plain letters is
# exact instead of positional, and it is a transliteration nobody has to
# invent: it is the one the boundary file already used.
DIGRAPHS = {"đ": "dj", "Đ": "dj", "ð": "dj", "ø": "o", "ł": "l", "ß": "ss",
            "æ": "ae", "œ": "oe", "þ": "th"}
# North Macedonia's boundary file goes further than dropping the diacritics:
# it spells the Cyrillic out in English digraphs, so Bogdanci is
# "Bogdantsi", Aracinovo is "Arachinovo" and Cesinovo-Oblesevo is
# "Cheshinovo - Obleshevo". Collapsing each digraph to the one letter it
# stands for makes the two spellings the same string, and it collapses the
# same way on both sides, so nothing is decided by which side a name came
# from. Two official names that met in the middle would be an ambiguity and
# are refused rather than guessed at.
COLLAPSE = (("shch", "s"), ("sh", "s"), ("ch", "c"), ("zh", "z"),
            ("ts", "c"), ("kj", "k"), ("gj", "g"), ("dj", "d"))


def folded(name: str) -> str:
    """A name reduced to the letters a romanisation of it keeps."""
    text = "".join(DIGRAPHS.get(c, c) for c in name)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^0-9a-z]", "", text.casefold())
    for digraph, letter in COLLAPSE:
        text = text.replace(digraph, letter)
    return text


def match_folded(spellings: list[str], official: list[str]
                 ) -> tuple[dict[str, str], dict[str, str]]:
    """({spelling: official name}, {spelling: why it matched nothing}), by
    folding both sides to plain letters and requiring them to be equal."""
    index: dict[str, list[str]] = {}
    for name in official:
        index.setdefault(folded(name), []).append(name)
    matched: dict[str, str] = {}
    refused: dict[str, str] = {}
    for spelling in spellings:
        fits = index.get(folded(spelling), [])
        if len(fits) == 1:
            matched[spelling] = fits[0]
        elif fits:
            refused[spelling] = (
                f"{spelling!r} romanises the same way as {len(fits)} of the "
                f"country's own names ({', '.join(fits)}); it is not matched "
                f"to any of them")
        else:
            refused[spelling] = (
                f"{spelling!r} is none of the names on the country's own list "
                f"of units; there is no article to read for it")
    return matched, refused


# ---------------------------------------------------------------------------
# What a citation is, and what kind of count it describes
# ---------------------------------------------------------------------------

SOURCE_KINDS: tuple[tuple[str, str, str], ...] = (
    # First, and before "census", because these pages carry census figures
    # and say so in their titles: pop-stat.mashke.org is one person's
    # compilation of Eastern European census results, not an office, and a
    # record that called it a census would be claiming a provenance it does
    # not have.
    ("compilation", r"pop-stat\.mashke\.org|citypopulation\.de|"
                    r"population statistics of eastern europe",
     "a third-party compilation of census figures"),
    ("census", r"census|\bpopis\b|\bперепис|преброяван|recens[aă]m|s[čc][ií]tan|"
               r"n[ée]psz[áa]ml[áa]l|gjenerale e popullsis|surveys of population|"
               r"popullsis[ëe] dhe|\bпопис\b|censusresults",
     "a population census"),
    ("office", r"nsi\.bg|stat\.gov|statistics|statisti[ck]|statistika|statisztik|"
               r"insse|instat|statistik|osp\.stat|\bstat\.",
     "a national statistical office"),
    ("registry", r"registr|регистр|register|\bmatri[ck]",
     "a population register"),
    ("ministry", r"minist|министер|ministerstv",
     "a government ministry"),
)
EXPLAINED = dict((k, e) for k, _, e in SOURCE_KINDS)
EXPLAINED["other"] = "a source this reader cannot classify"
CAVEAT = {
    "compilation": "A census figure as a third-party compilation republishes "
                   "it, not read from the office that took the census.",
    "census": "A census count.",
    "office": "A statistical-office figure, which may be a census table or an estimate.",
    "registry": "A registry count of who is registered, not a census answer.",
    "ministry": "A ministry figure, not a census answer.",
    "other": "The citation does not say which kind of count this is.",
}
KIND_RANK = {"census": 0, "office": 1, "ministry": 2, "registry": 3,
             "compilation": 4, "other": 5}

REF_FULL = re.compile(r"<ref\b([^>/]*)(?:/>|>(.*?)</ref>)", re.S | re.I)
REF_NAME = re.compile(r"""name\s*=\s*["']?([^"'/>]+?)["']?\s*$""", re.I)


def ref_name(attrs: str) -> str | None:
    m = REF_NAME.search(attrs.strip())
    return m.group(1).strip().lower() if m else None


def ref_definitions(wikitext: str) -> dict[str, str]:
    """Every named reference's body, wherever on the page it is defined."""
    out: dict[str, str] = {}
    for m in REF_FULL.finditer(wikitext):
        body, name = m.group(2), ref_name(m.group(1))
        if body and name:
            out.setdefault(name, body)
    return out


def citations(fragment: str, definitions: dict[str, str]) -> list[str]:
    """The bodies of the references inside one fragment of an article.

    A reference used by a name the page never defines is a citation to
    nothing -- it has no year and no table behind it, whatever the name
    suggests -- so it is resolved through the page's definitions or dropped.
    """
    out: list[str] = []
    for m in REF_FULL.finditer(fragment):
        body, name = m.group(2), ref_name(m.group(1))
        if not body and name:
            body = definitions.get(name, "")
        if body:
            out.append(body)
    return out


# A citation template's parameter names are in the language of the edition
# it sits in: bg.wikipedia's {{Цитат уеб}} takes заглавие and уеб_адрес.
# Reading only the English names left every Bulgarian citation looking like
# a bare body with no title and no URL, which is also what its source line
# on the record would have said.
FIELD_NAMES = {
    "title": ("title", "trans-title", "заглавие", "наслов", "názov", "titlu",
              "cím", "naslov"),
    "url": ("url", "уеб_адрес", "адрес", "адреса"),
    "date": ("year", "date", "publication-date", "година", "дата", "rok"),
}


def cite_field(body: str, field: str) -> str:
    for name in FIELD_NAMES.get(field, (field,)):
        m = re.search(r"\|\s*" + re.escape(name) + r"\s*=\s*([^|}]*)", body, re.I)
        if m and m.group(1).strip():
            return " ".join(m.group(1).split())
    return ""


def describe_citation(body: str) -> tuple[str, int | None, str]:
    """(kind, year, what the citation says it is) for one reference body."""
    title = cite_field(body, "title") or cite_field(body, "trans-title")
    url = cite_field(body, "url")
    haystack = f"{title} {url} {body[:300]}".lower()
    kind = "other"
    for name, pattern, _ in SOURCE_KINDS:
        if re.search(pattern, haystack):
            kind = name
            break
    years = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", title)]
    if not years:
        path = re.sub(r"web\.archive\.org/web/\d+/", "", url)
        # A URL glues the year to a word -- popis2022.stat.gov.rs,
        # census2011.statistics.sk, publikacije.stat.gov.rs/G2023/ -- so a
        # word boundary finds none of them, and every Serbian district was
        # refused for want of a date that was in its citation all along.
        # What must not happen is reading four digits out of the middle of
        # an identifier, so the year may touch letters and not digits:
        # "G20234001.pdf" yields nothing, "G2023" yields 2023.
        years = [int(y) for y in
                 re.findall(r"(?<!\d)(19\d\d|20[0-4]\d)(?!\d)", path)]
    if not years:
        # The citation's own date of publication; never its access date,
        # which is when the editor read it.
        dated = cite_field(body, "date")
        years = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", dated)]
    if not years:
        # A citation template in the local language: the Bulgarian articles
        # use {{Цитат уеб}}, whose parameters are заглавие and уеб_адрес, so
        # the fields read above are all empty and a well-dated citation
        # looks undated -- every one of Bulgaria's 28 mother-tongue tables
        # was refused for it. What is scanned instead is the whole citation
        # with the editor's own dates taken out of it, which is the one
        # thing in there that is not the figure's date.
        stripped = re.sub(r"\|\s*[^|=}]*(access|archive|достъп|посетен|"
                          r"abruf|consult)[^|=}]*=[^|}]*", " ", body, flags=re.I)
        years = [int(y) for y in
                 re.findall(r"(?<!\d)(19\d\d|20[0-4]\d)(?!\d)", stripped)]
    if not years and "=" not in body:
        # A bare external link, "[url The census of 2011, volume 3]", which
        # is how half of these articles cite. It has no fields to read, so
        # the whole of it is the citation and the year in it is the
        # citation's own -- there is no access date in a bare link to
        # mistake it for.
        years = [int(y) for y in
                 re.findall(r"(?<!\d)(19\d\d|20[0-4]\d)(?!\d)", body)]
    return kind, (max(years) if years else None), title or url or " ".join(body.split())[:80]


# ---------------------------------------------------------------------------
# Reading one composition out of one article
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Composition:
    """How one field's composition is written in one country's articles.

    ``section`` and ``header`` are both required and both are checks: the
    heading says what the table counts (a European article almost never
    repeats it in the header) and the header says the columns are still in
    the order this reader was written against. An article that has been
    reorganised fails the header and is refused, rather than read wrong.

    ``value`` is which of a row's numbers is the share, counted from the
    first number after the label, so -1 is the last. It is never guessed:
    Albania's table prints 2011, 2023 and the difference between them side
    by side, and the last number in the row is the change since 2011.
    """

    field: str
    section: str
    header: str
    value: int
    labels: dict[str, str]
    skip: str = r"^$"
    # Whether the section must hold exactly one table this reader
    # recognises. Bulgaria's municipalities print their ethnic composition
    # once per census under one heading, with nothing in the header to say
    # which is which, so reading "the first one" would date half of them
    # wrong. Where this is set, a second recognised table refuses the unit.
    unique: bool = False
    # How many figures a row of this table carries. A table that prints two
    # censuses side by side has four -- count, share, count, share -- and a
    # row that carries fewer is a row about only one of them, where "the
    # last number" is a share of the wrong year. Where this is set, such a
    # row is dropped rather than read from the wrong column, and the note
    # says how many were dropped.
    width: int | None = None
    # Whether ``value`` counts the row's columns rather than its figures.
    #
    # The two are the same until a cell is empty, and Moldova's tables are
    # full of empty cells. Taraclia's religion table prints 2004, 2014 and
    # 2024 side by side and writes "-" where a faith had nobody: its
    # Lutheran row is "- | - | 44 | 0.13 | - | -", whose last *figure* is
    # 0.13 and whose last *column* is empty. Counting figures publishes
    # 2014's Lutherans as 2024's; counting columns reads nothing there,
    # which is what the table says. It also keeps the rows the width check
    # would have thrown away whole -- the same table's Jehovah's Witnesses
    # have no 2004 figure and a perfectly good 2024 one.
    #
    # Opt-in, because it is only safe where a row's cells line up with the
    # header's, and a table that merges two cells into one (Chisinau's
    # ethnic table does, where a people has no count for 1989) is only
    # aligned at the end -- which is the column these specs read.
    columns: bool = False


@dataclass(frozen=True)
class Level:
    """One country at one level: where the articles are and what to read."""

    level: str
    title: str                       # applied to the shape's name
    fields: tuple[Composition, ...]
    lang: str = "en"
    via: str | None = None           # resolve the title above into this edition
    titles: dict[str, str] | None = None     # shape name -> article, where the pattern fails
    # shape name -> why nothing is read for it. Either there is no article,
    # or there is one and what it publishes is not this country's census:
    # Bender's composition is Transnistria's own count of a city Moldova did
    # not count, and reading it would put another authority's figures out
    # under the National Bureau's name.
    absent: dict[str, str] | None = None
    # Where the boundary file's spelling cannot be used as written: the
    # country's own list of unit names, and the prefix the file puts in
    # front of each ("District of "). match_spellings joins the two.
    official: tuple[str, ...] | None = None
    strip: str = ""
    # Where the country's own list of unit names is a Wikipedia category
    # rather than a list typed into this file. The two sides are compared on
    # a key -- the shape's name without the word the boundary file appends,
    # the article's title without the disambiguator Wikipedia appends -- and
    # the article kept is the one the category named.
    category: str | None = None
    category_lang: str = ""
    # ...or an article whose links are that list, where no category holds it.
    links: str | None = None
    # How a boundary file's spelling is joined to the country's own name:
    # "positional" for a file that has lost its letters outside ASCII,
    # "folded" for one that has romanised them.
    match: str = "positional"
    shape_trim: str = ""
    article_trim: str = ""


@dataclass(frozen=True)
class Country:
    iso3: str
    out: str
    decimal: str                     # "." or "," -- which mark a number's fraction uses
    census: str                      # what the articles are transcribing
    licence: str
    levels: tuple[Level, ...]
    # A field this country's articles were searched for and do not carry in
    # a form that can be read. It goes on every record as a gap with the
    # reason, because a measured negative is a result: it says which kind of
    # empty this is, and stops the next reader repeating the search.
    declared: dict[str, str] | None = None
    # Where the article cites its census once, in the infobox, and does not
    # repeat the reference on the table.
    #
    # Moldova is why. Its district articles all transcribe the same 2024
    # census into the same two-column table, and three of thirty-two happen
    # to carry the reference on the table itself; the rest cite it from
    # `population_footnotes` and nowhere else. Read strictly, that left
    # twenty-nine districts empty over where an editor put a <ref>, not over
    # anything about the figures.
    #
    # It stays opt-in and it stays narrow: the value is a pattern the
    # infobox's citation must match, so a district cannot borrow a citation
    # about something else, and the note on every record says the citation
    # came from the infobox rather than from the table. A reader of the panel
    # can see exactly what was leaned on.
    infobox_citation: str | None = None


# The share of a composition that may be missing before the rest is carried
# as a remainder row, and the bounds outside which the reading is refused
# rather than remarked on. Both are Indonesia's, and for the same reasons.
TOLERANCE = 0.6
BOUNDS = (90.0, 103.0)
REMAINDER = "Other or not stated"


def number(cell: str, decimal: str) -> float | None:
    """A cell's number, or None.

    Which mark separates a fraction is a fact about the country and not
    about the cell: "77,956" is seventy-eight thousand on the English
    Wikipedia and seventy-eight on the Slovak one. Guessing it per cell
    would read Slovakia's "91,41" as ninety-one thousand and Serbia's
    "112.084" as a hundred and twelve, so the mark is declared per country
    and everything else that separates digits is a thousands separator.
    """
    text = re.sub(r"[\s ]", "", cell.strip()).strip("%").strip()
    text = re.sub(r"^[+±]", "", text)
    if decimal == ",":
        text = text.replace(".", "").replace(" ", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    return float(text) if re.fullmatch(r"-?\d+(?:\.\d+)?", text) else None


def cell_text(cell: str) -> str:
    """A cell's label, its table markup and footnote marks gone."""
    text = re.sub(r"^[^|]*\|(?!\|)", "", cell.strip()) if "|" in cell else cell
    text = re.sub(r"\[\d+\]|\*+$", "", text)
    return " ".join(text.split()).strip(" .:;")


def find_table(wikitext: str, spec: Composition) -> tuple[list[list[str]], str, str]:
    """(the table's rows, the section's wikitext, why not).

    The section is returned with it because that is where the citation
    lives: a table's own markup rarely carries the reference, and the
    sentence above it nearly always does.
    """
    section = re.compile(spec.section, re.I)
    header = re.compile(spec.header, re.I)
    seen = False
    tabled = False
    found: list[tuple[list[list[str]], str]] = []
    for name, body in sections(wikitext):
        if not section.search(name):
            continue
        seen = True
        for table in tables(body):
            tabled = tabled or len(table) >= 3
            if len(table) < 3:
                continue
            first = " ".join(" ".join(row) for row in table[:2])
            if header.search(first):
                found.append((table, body))
    if found and spec.unique and len(found) > 1:
        return [], "", (f"the article prints {len(found)} tables of this kind "
                        f"under one heading, with nothing in their headers to "
                        f"say which census each is; none is read")
    if found:
        return found[0][0], found[0][1], ""
    if not seen:
        return [], "", f"the article has no section matching {spec.section!r}"
    if not tabled:
        # Worth separating from the refusal below, because they are
        # different facts about the article and a reader of the map should
        # not have to guess which happened. Montenegro's municipality
        # articles have a Demographics heading with prose under it and the
        # only table on the page is the council's party seats.
        return [], "", ("the article has a section where a composition would "
                        "go and prints no table in it at all; this unit's "
                        "article publishes no composition")
    return [], "", ("the section is there and holds a table whose header this "
                    "reader does not know; the article has been reorganised "
                    "or carries a different table")


PIXELS = re.compile(r"^\d+\s*px$", re.I)


SOFT_BREAK = re.compile(r"-\s+")


def label_for(label: str, labels: dict[str, str]) -> tuple[str | None, str]:
    """(the map's name for this row, the key it was found under).

    A row's first cell often carries a flag before the label -- a {{flag}}
    template or a [[File:...|22px]] link -- and what that resolves to in
    wikitext is either the country's name or the image's size. Kosice
    Region's table reads "Slovensko slovenska" and "22px romska" for rows
    that are "slovenska" and "romska". So a size token is dropped outright,
    and leading words are dropped one at a time only while what remains is
    a label this reader already knows: an unknown label stays unknown and
    is reported rather than whittled into a guess.
    """
    # A cell that breaks a long word over two lines leaves the hyphen
    # behind: Bulgaria's "Не се само- определят" is one word, hyphenated by
    # the table's width and by nothing else.
    label = SOFT_BREAK.sub("", " ".join(label.lower().split()))
    words = [w for w in label.split(" ") if not PIXELS.match(w)]
    whole = " ".join(words)
    if whole in labels:
        return labels[whole], whole
    # A spanning cell leaks the group it spans into the first row under it,
    # so Blagoevgrad's Russians arrive as "Drugi Rusnatsi" -- the outer label
    # "other" and the inner one "Russians" in one cell, with one pair of
    # figures between them that belongs to whichever of the two the table
    # meant. The outer one is the residual, which is the reading that cannot
    # overstate a people, so it is preferred where the first word is itself
    # a label.
    if words and words[0] in labels:
        return labels[words[0]], words[0]
    for start in range(1, len(words)):
        key = " ".join(words[start:])
        if key in labels:
            return labels[key], key
    return None, whole


def read_rows(table: list[list[str]], spec: Composition, decimal: str
              ) -> tuple[dict[str, float], list[str], str]:
    """({label: share}, what to say about the rows not read, why not).

    A row is read when its first cell is a label and the row carries at
    least as many numbers as the spec asks for. A row that carries none is
    a header continuation and is skipped in silence; a row whose label the
    spec has no entry for is collected and reported, never guessed at.

    The middle value is the labels themselves where a label was unknown --
    which is what the refusal prints -- and otherwise the sentences the
    record must carry about rows this reader passed over.
    """
    skip = re.compile(spec.skip, re.I)
    out: dict[str, float] = {}
    unknown: list[str] = []
    short = 0
    blank = 0
    for row in table:
        if not row:
            continue
        label = cell_text(row[0])
        cells = [number(cell_text(c), decimal) for c in row[1:]]
        numbers = [n for n in cells if n is not None]
        if not label or not numbers:
            continue
        if skip.search(label):
            continue
        if spec.width is not None and len(numbers) != spec.width:
            short += 1
            continue
        found = cells if spec.columns else numbers
        wanted = spec.value if spec.value >= 0 else len(found) + spec.value
        if not 0 <= wanted < len(found):
            continue
        if found[wanted] is None:
            # Only where the columns are being counted: the row is about
            # this table's subject and has nothing in the column read.
            blank += 1
            continue
        mapped, key = label_for(label, spec.labels)
        if mapped is None:
            unknown.append(label)
            continue
        out[mapped] = out.get(mapped, 0.0) + found[wanted]
    if unknown:
        return {}, unknown, f"labels this reader has no entry for: {unknown}"
    if not out and blank:
        # Briceni's religion table is this: a 2014 column of counts with the
        # share column beside it left empty in every row. Worth telling apart
        # from the refusal below, because the article does publish a table
        # and it is the column that is missing.
        return {}, [], (f"the table's rows are there and the column this "
                        f"reader takes the share from is empty in all "
                        f"{blank} of them")
    if not out:
        return {}, [], "the table holds no row this reader could read"
    said: list[str] = []
    if short:
        said.append(f"{short} row(s) of the table carry figures for only one "
                    f"of the censuses it prints and are not read; what they "
                    f"hold is inside the remainder.")
    if blank:
        said.append(f"{blank} row(s) of the table print nothing in the column "
                    f"read -- the table has no figure there -- and are not "
                    f"read.")
    return out, said, ""


def shares_of(counts: dict[str, float]) -> tuple[list[dict[str, Any]], str, str]:
    """(rows, why not, a remark where the shares needed a decision)."""
    total = sum(counts.values())
    if not BOUNDS[0] <= total <= BOUNDS[1]:
        return [], f"the shares add to {total:.2f}, which is not a composition", ""
    remark = ""
    if total < 100.0 - TOLERANCE:
        counts = dict(counts)
        counts[REMAINDER] = round(100.0 - total, 2)
        remark = (f"The table's groups add to {total:.1f}%; the rest is carried "
                  f"as a remainder.")
    elif total > 100.0 + TOLERANCE:
        remark = (f"As printed the shares add to {total:.1f}%, and are carried "
                  f"as printed.")
    rows = [{"group": g, "pct": round(p, 2)} for g, p in counts.items()]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows, "", remark


# ---------------------------------------------------------------------------
# A boundary file's spelling, against the country's own
# ---------------------------------------------------------------------------

# The boundary file's admin2 layer for Slovakia has lost every letter outside
# ASCII: "District of Banskk vtiavnica" is Banská Štiavnica, "Bonovce nad
# Bebra*" is Banovce nad Bebravou. The substitutions are not a codepage --
# the same letter comes back as different characters in different names, "a"
# with an acute as "s" in Banska Bystrica and as "k" in Banska Stiavnica --
# so nothing can be decoded. What survives intact is every letter that was
# ASCII to begin with, and their positions.
#
# So a name matches a district when every ASCII letter of the district's own
# spelling is the same letter in the same place, a letter the district
# spells outside ASCII may be anything, and a "*" (which the file uses where
# it ran out of room) ends the comparison. A shorter name is allowed to be a
# truncation of a longer one, which is what "Liptovsk" and "Rimavsk" are.
#
# Two passes, because a truncation can be ambiguous: "Gala" is Sala with two
# letters replaced and is also the first four letters of Galanta. Full-length
# matches are made first and take their districts out of the running, so the
# shape that really is Galanta claims it and "Gala" is left with one
# candidate. A name still matching two districts is refused and named in the
# log: an unmatched shape is a visible gap and a mis-matched one is not.
STAR = "*"
HYPHEN = re.compile(r"\s*-\s*")


def spaced(name: str) -> str:
    """The name with the spaces around a hyphen settled.

    The comparison below is positional, so one space either side of the
    hyphen moves every letter after it. The boundary file writes "Kovice -
    okolie" and Slovakia writes "Kosice-okolie", which is the same district
    and the same letters.
    """
    return HYPHEN.sub("-", name)


def could_be(spelling: str, official: str) -> bool:
    """Whether a boundary file's ``spelling`` can be this ``official`` name."""
    spelling, official = spaced(spelling), spaced(official)
    if len(spelling) > len(official):
        return False
    for i, (got, want) in enumerate(zip(spelling, official)):
        if got == STAR:
            return True
        if want.isascii():
            if got.casefold() != want.casefold():
                return False
        elif got.isascii() and got.isalpha() or got == " ":
            continue          # a letter outside ASCII, replaced by some letter
        elif got != want:
            return False
    return True


def match_spellings(spellings: list[str], official: list[str]
                    ) -> tuple[dict[str, str], dict[str, str]]:
    """({boundary spelling: official name}, {spelling: why it matched nothing}).

    Exact and full-length matches first, then truncations against what is
    left; a spelling that still fits two names is refused rather than guessed.
    """
    matched: dict[str, str] = {}
    refused: dict[str, str] = {}
    left = list(official)
    for exact in (True, False):
        for spelling in spellings:
            if spelling in matched or spelling in refused:
                continue
            fits = [name for name in left
                    if could_be(spelling, name)
                    and (not exact or len(spaced(spelling)) == len(spaced(name)))]
            if len(fits) == 1:
                matched[spelling] = fits[0]
                left.remove(fits[0])
            elif fits and not exact:
                refused[spelling] = (
                    f"the boundary file spells this unit {spelling!r}, which "
                    f"fits {len(fits)} of the country's own names "
                    f"({', '.join(fits)}); it is not matched to any of them")
    for spelling in spellings:
        if spelling not in matched and spelling not in refused:
            refused[spelling] = (
                f"the boundary file spells this unit {spelling!r}, which is "
                f"none of the country's own unit names; there is no article "
                f"to read for it")
    return matched, refused


# ---------------------------------------------------------------------------
# The labels, per edition
# ---------------------------------------------------------------------------

# Slovak. The census's own categories, from the tables census2011.statistics.sk
# publishes and the sk.wikipedia articles transcribe. A bucket naming two
# peoples at once is one bucket and not two rows: the 2011 tables give some
# districts "rusinska a ukrajinska" together, and splitting that would be
# inventing the split.
SK_ETHNICITY = {
    "slovenská": "Slovak", "maďarská": "Hungarian", "rómska": "Romani",
    "rusínska": "Rusyn", "ukrajinská": "Ukrainian",
    "rusínska a ukrajinská": "Rusyn and Ukrainian",
    "česká": "Czech", "moravská": "Moravian", "sliezska": "Silesian",
    "česká a moravská": "Czech and Moravian",
    "česká, moravská a sliezska": "Czech, Moravian and Silesian",
    "nemecká": "German", "poľská": "Polish", "ruská": "Russian",
    "bulharská": "Bulgarian", "židovská": "Jewish", "chorvátska": "Croatian",
    "srbská": "Serbian", "rumunská": "Romanian", "rakúska": "Austrian",
    "albánska": "Albanian", "grécka": "Greek", "talianska": "Italian",
    "anglická": "English", "iránska": "Iranian", "írska": "Irish",
    "vietnamská": "Vietnamese", "čínska": "Chinese", "turecká": "Turkish",
    "francúzska": "French", "kanadská": "Canadian", "kórejská": "Korean",
    "americká": "American", "holandská": "Dutch", "španielska": "Spanish",
    "slovinská": "Slovene", "slezská": "Silesian", "slezania": "Silesian",
    "iná": "Other", "ostatné": "Other", "ostatná": "Other",
    "ostatná, nezistená": "Other or not stated",
    "iná a neuvedená": "Other or not stated",
    "iná, nezistená": "Other or not stated",
    "neuvedená": "Not stated", "nezistená národnosť": "Not stated",
    "nezistená": "Not stated", "nezistené": "Not stated",
    "iná a nezistená": "Other or not stated",
}
SK_RELIGION = {
    "rímskokatolícka cirkev": "Roman Catholic", "rímskokatolícke": "Roman Catholic",
    "gréckokatolícka cirkev": "Greek Catholic", "gréckokatolícke": "Greek Catholic",
    "pravoslávna cirkev": "Orthodox", "pravoslávne": "Orthodox",
    "evanjelická cirkev augsburského vyznania": "Lutheran",
    "evanjelické augsburského vyznania": "Lutheran",
    "reformovaná kresťanská cirkev": "Reformed", "reformované kresťanské": "Reformed",
    "evanjelická cirkev metodistická": "Methodist",
    "apoštolská cirkev": "Other Christian", "cirkev bratská": "Other Christian",
    "kresťanské zbory": "Other Christian",
    "cirkev adventistov siedmeho dňa": "Other Christian",
    "bratská jednota baptistov": "Other Christian",
    "cirkev československá husitská": "Other Christian",
    "starokatolícka cirkev": "Other Christian",
    "náboženská spoločnosť jehovovi svedkovia": "Jehovah's Witnesses",
    "ústredný zväz židovských náboženských obcí": "Judaism",
    "židovské": "Judaism",
    "kresťanské spoločenstvá": "Other Christian",
    "novoapoštolská cirkev": "Other Christian",
    "bahájske spoločenstvo": "Other religion",
    "cirkev ježiša krista svätých neskorších dní": "Latter-day Saints",
    "iné": "Other religion", "ostatné": "Other religion",
    "bez vyznania": "No religion", "bez vyznania a nezistené": "No religion or not stated",
    "nezistené": "Not stated", "nezistená": "Not stated",
}
# What the English Wikipedia's Balkan tables call the peoples in them.
BALKAN_ETHNICITY = {
    "serbs": "Serbian", "hungarians": "Hungarian", "roma": "Romani",
    "romani": "Romani", "romas": "Romani", "croats": "Croatian",
    "slovaks": "Slovak", "montenegrins": "Montenegrin", "yugoslavs": "Yugoslav",
    "albanians": "Albanian", "bosniaks": "Bosniak", "bosniacs": "Bosniak",
    "macedonians": "Macedonian", "vlachs": "Vlach", "aromanians": "Aromanian",
    "turks": "Turkish", "bulgarians": "Bulgarian", "romanians": "Romanian",
    "rusyns": "Rusyn", "ruthenians": "Rusyn", "bunjevci": "Bunjevac",
    "gorani": "Gorani", "ashkali": "Ashkali", "egyptians": "Balkan Egyptian",
    "balkan egyptians": "Balkan Egyptian", "ethnic muslims": "Muslim (ethnic)",
    "muslims": "Muslim (ethnic)", "muslims by nationality": "Muslim (ethnic)",
    "germans": "German", "russians": "Russian", "ukrainians": "Ukrainian",
    "slovenes": "Slovene", "slovenians": "Slovene", "czechs": "Czech",
    "poles": "Polish", "slovenians (people)": "Slovene",
    "romanians": "Romanian", "vlasi": "Vlach", "bunjevac": "Bunjevac",
    "šokci": "Šokci", "sokci": "Šokci", "goranci": "Gorani",
    "yugoslav": "Yugoslav", "bosnians": "Bosnian", "serb": "Serbian",
    "greeks": "Greek", "jews": "Jewish", "italians": "Italian",
    "torbesh": "Torbesh", "serbians": "Serbian", "gagauz": "Gagauz",
    "moldovans": "Moldovan", "moldovans *": "Moldovan",
    "romanians *": "Romanian", "gagauzians": "Gagauz", "belarusians": "Belarusian",
    "armenians": "Armenian", "others": "Other", "other": "Other",
    "other ethnicities": "Other", "others/undeclared/unknown": "Not declared or unknown",
    "other / undeclared / unknown": "Not declared or unknown",
    "undeclared/unknown": "Not declared or unknown",
    "undeclared": "Not declared", "unknown": "Not stated",
    "not declared": "Not declared", "no answer": "Not stated",
    "regional affiliation": "Regional affiliation",
    "persons for whom data are taken from administrative sources":
        "Taken from administrative records",
}
# A row that is a sum of the rows around it, or the table's own total.
TOTALS = r"^(total|totals|ukupno|укупно|spolu|обшто|общо|sum|population)\b"


# ---------------------------------------------------------------------------
# The countries
# ---------------------------------------------------------------------------

# The 79 districts and 8 regions, spelled as Slovakia spells them. The
# boundary file's own spellings are matched to these by match_spellings.
SK_DISTRICTS = (
    "Banská Bystrica", "Banská Štiavnica", "Bardejov", "Bánovce nad Bebravou",
    "Bratislava I", "Bratislava II", "Bratislava III", "Bratislava IV",
    "Bratislava V", "Brezno", "Bytča", "Detva", "Dolný Kubín",
    "Dunajská Streda", "Galanta", "Gelnica", "Hlohovec", "Humenné", "Ilava",
    "Kežmarok", "Komárno", "Košice I", "Košice II", "Košice III", "Košice IV",
    "Košice-okolie", "Krupina", "Kysucké Nové Mesto", "Levice", "Levoča",
    "Liptovský Mikuláš", "Lučenec", "Malacky", "Martin", "Medzilaborce",
    "Michalovce", "Myjava", "Námestovo", "Nitra", "Nové Mesto nad Váhom",
    "Nové Zámky", "Partizánske", "Pezinok", "Piešťany", "Poltár", "Poprad",
    "Považská Bystrica", "Prešov", "Prievidza", "Púchov", "Revúca",
    "Rimavská Sobota", "Rožňava", "Ružomberok", "Sabinov", "Senec", "Senica",
    "Skalica", "Snina", "Sobrance", "Spišská Nová Ves", "Stará Ľubovňa",
    "Stropkov", "Svidník", "Topoľčany", "Trebišov", "Trenčín", "Trnava",
    "Turčianske Teplice", "Tvrdošín", "Veľký Krtíš", "Vranov nad Topľou",
    "Zlaté Moravce", "Zvolen", "Žarnovica", "Žiar nad Hronom", "Žilina",
    "Čadca", "Šaľa",
)
SK_REGIONS = {
    "Region of Banská Bystrica": "Banskobystrický kraj",
    "Region of Bratislava": "Bratislavský kraj",
    "Region of Košice": "Košický kraj",
    "Region of Nitra": "Nitriansky kraj",
    "Region of Prešov": "Prešovský kraj",
    "Region of Trenčín": "Trenčiansky kraj",
    "Region of Trnava": "Trnavský kraj",
    "Region of Žilina": "Žilinský kraj",
}

SK_FIELDS = (
    Composition(
        field="ethnicity",
        section=r"n[áa]rodnos|obyvate[ľl]|demograf|zlo[žz]enie|[šs]trukt[úu]ra",
        header=r"n[áa]rodnos[ťt]",
        value=-1,
        labels=SK_ETHNICITY,
        skip=r"^(spolu|celkom|obyvate)"),
    Composition(
        field="religion",
        section=r"n[áa]bo[žz]en|vierovyznanie|obyvate[ľl]|demograf|zlo[žz]enie|[šs]trukt[úu]ra",
        header=r"n[áa]bo[žz]enstvo|vyznanie",
        value=-1,
        labels=SK_RELIGION,
        skip=r"^(spolu|celkom|obyvate)"),
)

BALKAN_RELIGION = {
    "eastern orthodox": "Orthodox", "orthodox": "Orthodox",
    "orthodox christians": "Orthodox", "orthodox christianity": "Orthodox",
    "roman catholic": "Catholic", "catholics": "Catholic", "catholic": "Catholic",
    "protestants": "Protestant", "protestant": "Protestant",
    "islam": "Islam", "muslims": "Islam", "muslim": "Islam",
    "other christian": "Other Christian",
    "other christian religions": "Other Christian",
    "judaism": "Judaism", "jews": "Judaism",
    "atheist": "Atheism", "atheists": "Atheism",
    "agnostic": "Agnosticism", "agnostics": "Agnosticism",
    "other": "Other religion", "others": "Other religion",
    "undeclared": "Not declared", "not declared": "Not declared",
    "unknown": "Not stated", "no answer": "Not stated",
    "adherents of other religions": "Other religion",
    "believers who do not belong to any religion": "Other religion",
    "no religion": "No religion", "not religious": "No religion",
}

MK_ETHNICITY = Composition(
    field="ethnicity",
    section=r"^demograph|^population|ethnic|^census",
    # " | 2002 | 2021 | | Number | % | Number | % " -- the two censuses the
    # article prints side by side, which is what makes the width check below
    # the thing that keeps a row of one census out of the other's column.
    header=r"number\s*\|?\s*%",
    value=-1,
    width=4,
    labels=BALKAN_ETHNICITY,
    skip=TOTALS)

# Moldova's own words, on top of the Balkan tables above. They are kept
# here rather than added to the shared ones because a label added to read
# Taraclia would otherwise change what is read in Serbia and North
# Macedonia, in tables nobody has looked at while writing this.
MD_ETHNICITY_LABELS = {
    **BALKAN_ETHNICITY,
    # Gagauzia's table's word for the Roma, and the 2024 census's.
    "gypsies": "Romani",
}
MD_RELIGION_LABELS = {
    **BALKAN_RELIGION,
    "eastern orthodoxy": "Orthodox",
    # The dash marks a child of the row above it -- see MD_SUBTOTALS.
    "– orthodox christians": "Orthodox",
    "– old believers": "Old Believer",
    "– other christians": "Other Christian",
    "other christians": "Other Christian",
    "baptist": "Baptist", "– baptists": "Baptist",
    "evangelical": "Evangelical", "– evangelic christian": "Evangelical",
    "pentecostal": "Pentecostal", "– penticostal": "Pentecostal",
    "– seventh-day adventist": "Seventh-day Adventist",
    "– lutheran": "Lutheran",
    "– presbyterian": "Presbyterian",
    "– roman catholic": "Roman Catholic",
    "jehovah's witnesses": "Jehovah's Witnesses",
    "other religions": "Other religion",
    # Basarabeasca's table, which names the same faiths in the plural and
    # puts "Christians" over them with no dash to mark the children.
    "orthodox christians": "Orthodox", "baptists": "Baptist",
    "adventists": "Adventist", "pentecostals": "Pentecostal",
    "evangelicals": "Evangelical", "old believers": "Old Believer",
    "catholics": "Catholic",
    # Beside atheists and agnostics in the same table, so it is a fourth
    # answer and not the category the three of them sit in. Mapped onto "No
    # religion" it made Basarabeasca report a parent and its children at once,
    # which the build refuses and is right to.
    "irreligious": "Irreligious",
    # The census's own category, beside atheists and agnostics in the same
    # table, so it is not either of them and is not folded into either.
    "free thinkers": "Freethinker",
    # One bar for two answers, because the census printed one number for
    # them. Chisinau's table has a separate "No religion" row beside this.
    "agnostic / atheist": "Agnostic or atheist",
    # Gagauzia's, and the same reasoning: both halves are irreligion.
    "atheism and irreligion": "No religion",
}
MD_LANGUAGE_LABELS = {
    "romanian": "Romanian", "moldovan": "Moldovan", "russian": "Russian",
    "gagauz": "Gagauz", "bulgarian": "Bulgarian", "ukrainian": "Ukrainian",
    # Gagauzia's table names the two together and gives them one figure;
    # Chisinau's keeps them apart. A bucket naming two languages at once is
    # one bucket and not two rows, and splitting it would invent the split.
    "moldovan (romanian)": "Moldovan (Romanian)",
    "other languages": "Other", "others": "Other", "other": "Other",
}

# A row that is the sum of the rows under it.
#
# Moldova's religion tables print the parent above its parts. Chisinau's
# has "Christianity (total)" at 94.45% standing over Baptist, Evangelical,
# Catholic, Pentecostal and the rest; Gagauzia's and Taraclia's have
# "Christians" over "– Orthodox Christians" and "– Other Christians", the
# dash marking the child. Reading both counts those people twice and hands
# the map a composition adding to nearly two hundred -- which shares_of
# would refuse, so the whole unit would be lost over it.
#
# Skipping a parent whose children are missing is the safe direction of the
# same mistake: what is left adds to five per cent and is refused, which is
# a gap and not a wrong figure.
MD_SUBTOTALS = r"|\(total\)|^christians$|^christianity$"

# The table's own header, which is a row like any other to a reader that has
# only the wikitext. Most of Europe's headers are skipped without being
# named -- they carry no figure, so there is nothing to read out of them --
# but Moldova's carry the census years, "Ethnicity | 2004 | 2014 | 2024",
# and a row with a label and figures in it is exactly what this reader
# stops at. Naming them is what keeps the header out of the composition.
MD_HEADER_ROWS = r"|^ethnic(ity|s|\s+group)|^religio|^(first\s+)?language"

MD_ETHNICITY = Composition(
    field="ethnicity",
    section=r"ethnic|^demograph|^population",
    # "Ethnic group" in a district's two-column table and in Chisinau's six
    # censuses side by side; "Ethnicity" in Taraclia's three.
    header=r"ethnic(ity|\s+group)",
    value=-1,
    labels=MD_ETHNICITY_LABELS,
    skip=TOTALS + MD_HEADER_ROWS)
MD_RELIGION = Composition(
    field="religion",
    section=r"religio",
    header=r"religio",
    value=-1,
    # Counting columns and not figures: Taraclia prints three censuses side
    # by side and writes "-" where a faith had nobody in one of them.
    columns=True,
    labels=MD_RELIGION_LABELS,
    skip=TOTALS + MD_SUBTOTALS + MD_HEADER_ROWS)
# Two shapes of the same question, one per article that asks it. Chisinau's
# table is first language by census since 1989; Gagauzia's is mother tongue
# beside the language spoken at home, which is why its column is named and
# not counted from the end -- the last column of that table is a different
# question.
MD_LANGUAGE_FIRST = Composition(
    field="language",
    section=r"language|mother tongue",
    header=r"first language",
    value=-1,
    labels=MD_LANGUAGE_LABELS,
    skip=TOTALS + MD_HEADER_ROWS)
MD_LANGUAGE_MOTHER = Composition(
    field="language",
    section=r"language|mother tongue",
    header=r"mother tongue",
    value=1,
    width=4,
    labels=MD_LANGUAGE_LABELS,
    skip=TOTALS + MD_HEADER_ROWS)
MD_FIELDS = (MD_ETHNICITY, MD_RELIGION, MD_LANGUAGE_FIRST, MD_LANGUAGE_MOTHER)

# The units of Moldova that are not districts, and so are in no category of
# them: the capital, the second city and the autonomous unit. Naming the
# article each one keeps its composition in is all it takes to reach them,
# because a name given here is used before the country's own list of unit
# names is consulted at all.
MD_TITLES = {"Chisinau": "Chișinău", "Balti": "Bălți", "Gagauzia": "Gagauzia"}

# The two this reader will not read, and why.
#
# Both are administered by Transnistria, which the 2024 Moldovan census did
# not count: the National Bureau's tables stop at the Dniester. What their
# articles publish instead is Transnistria's own counting, and this reader
# would print it under the line "Biroul Naţional de Statistică,
# Recensământul Populaţiei şi al Locuinţelor" -- a provenance it does not
# have. That is the mis-statement this project treats as worse than a gap,
# so they are gaps, and these are the reasons.
MD_ABSENT = {
    "Transnistria": (
        "Transnistria is not under the Moldovan government's control and the "
        "2024 Moldovan census did not count it. Its article publishes no "
        "composition table for the territory: what it has is an infobox "
        "listing 29.1% Russians, 28.6% Moldovans/Romanians and 22.9% "
        "Ukrainians from the census the Transnistrian authorities took in "
        "2015, and a column of 2004 prose, district by district, inside its "
        "table of administrative divisions. Neither is a figure of the "
        "census this reader names as its source, and the 2015 one counts "
        "Bender too, which this map draws as a unit of its own. They are "
        "left unread rather than published as Moldovan census results."),
    "Bender": (
        "Bender is administered by Transnistria and the 2024 Moldovan census "
        "did not count it. The only composition its article prints is the "
        "2004 census the Transnistrian authorities took, cited to a "
        "third-party compilation of Eastern European census results, and its "
        "rows give ranges rather than counts where the compiler could not "
        "tell -- \"0-5\", \"61-66\" -- inside column markup this reader "
        "cannot line up with the header. It is not a figure of the census "
        "this reader names as its source, and it is not read."),
}

# The two municipalities the category files under their formal titles.
ME_TITLES = {"Cetinje Municipality": "Old Royal Capital Cetinje",
             "Podgorica Municipality": "Podgorica Capital City"}

ME_FIELDS = (
    Composition(field="ethnicity", section=r"ethnic|^demograph|^population",
                header=r"ethnic(ity|\s+group|\s+composition)|nationality",
                value=-1, labels=BALKAN_ETHNICITY, skip=TOTALS),
    Composition(field="religion", section=r"religio|^demograph|^population",
                header=r"religio|denomination|faith|confession",
                value=-1, labels=BALKAN_RELIGION, skip=TOTALS),
)

# Bulgarian. The National Statistical Institute's own categories, as the
# Bulgarian Wikipedia article of a province or a municipality transcribes
# them. "Neotgovorili" and "Nepokazano" are the census's two ways of writing
# the people who did not answer, and both are kept as their own bar.
BG_ETHNICITY = {
    "българи": "Bulgarian", "турци": "Turkish", "цигани": "Romani",
    "роми": "Romani", "руснаци": "Russian", "арменци": "Armenian",
    "власи": "Vlach", "македонци": "Macedonian", "гърци": "Greek",
    "украинци": "Ukrainian", "евреи": "Jewish", "румънци": "Romanian",
    "каракачани": "Karakachan", "татари": "Tatar", "сърби": "Serbian",
    "албанци": "Albanian", "германци": "German", "поляци": "Polish",
    "други": "Other", "друг": "Other", "друга": "Other",
    "не се самоопределят": "Not declared",
    "не се самоопределили": "Not declared",
    "неотговорили": "Not stated", "не отговорили": "Not stated",
    "непоказано": "Not stated", "не показано": "Not stated",
}
BG_LANGUAGE = {
    "български": "Bulgarian", "турски": "Turkish", "цигански": "Romani",
    "ромски": "Romani", "руски": "Russian", "арменски": "Armenian",
    "гръцки": "Greek", "румънски": "Romanian", "украински": "Ukrainian",
    "татарски": "Tatar", "други": "Other", "друг": "Other",
    "не се самоопределят": "Not declared",
    "неотговорили": "Not stated", "не отговорили": "Not stated",
    "непоказано": "Not stated",
}
BG_RELIGION = {
    "православие": "Orthodox", "православни": "Orthodox",
    "източноправославно": "Orthodox",
    "католицизъм": "Catholic", "католици": "Catholic",
    "протестантство": "Protestant", "протестанти": "Protestant",
    "ислям": "Islam", "мюсюлмани": "Islam",
    "ислям сунитски": "Sunni Islam", "ислям шиитски": "Shia Islam",
    "юдаизъм": "Judaism", "армено-григорианско": "Other Christian",
    "друго": "Other religion", "други": "Other religion",
    "нямат": "No religion", "нямам": "No religion", "без религия": "No religion",
    "не се самоопределят": "Not declared",
    "неотговорили": "Not stated", "не отговорили": "Not stated",
    "непоказано": "Not stated",
}
BG_PROVINCE = (
    Composition(field="language", section=r"^езици|роден език",
                header=r"роден език", value=-1, width=2,
                labels=BG_LANGUAGE, skip=TOTALS),
    Composition(field="religion", section=r"вероизповед|религи",
                header=r"численост.*дял", value=-1, width=4,
                labels=BG_RELIGION, skip=TOTALS),
    Composition(field="ethnicity", section=r"етнически|етнос",
                header=r"численост.*дял", value=-1, width=4,
                labels=BG_ETHNICITY, skip=TOTALS),
)
# No width here, unlike the provinces: a municipality's table is two
# columns wide where it prints one census and four where it prints two, and
# the last figure in a row is the newest share either way. What keeps a
# 2001 table from being read as 2011 is not the width but ``unique`` -- a
# section holding more than one of these refuses the unit.
BG_MUNICIPALITY = (
    Composition(field="religion", section=r"вероизповед|религи",
                header=r"численост.*дял", value=-1, unique=True,
                labels=BG_RELIGION, skip=TOTALS),
    Composition(field="ethnicity", section=r"етнически|етнос",
                header=r"численост.*дял", value=-1, unique=True,
                labels=BG_ETHNICITY, skip=TOTALS),
)

RS_ETHNICITY = Composition(
    field="ethnicity",
    section=r"ethnic|^demograph|^population",
    header=r"ethnic(ity|\s+group)",
    value=-1,
    labels=BALKAN_ETHNICITY,
    skip=TOTALS)

SPECS: dict[str, Country] = {
    "SVK": Country(
        iso3="SVK", out="europe_wiki_slovakia.json", decimal=",",
        census="Štatistický úrad SR, Sčítanie obyvateľov, domov a bytov 2011",
        licence="Official statistics; compilation CC BY-SA 4.0",
        declared={"language": (
            "Slovakia's census asks mother tongue, and the Slovak Wikipedia "
            "article of a region or a district carries the census's "
            "nationality table and its religion table and not its "
            "mother-tongue table. There is nothing here to read for this "
            "field; the figures exist at the Statistical Office.")},
        levels=(
            Level(level="admin1", lang="sk", title="{name}",
                  titles=SK_REGIONS, fields=SK_FIELDS),
            Level(level="admin2", lang="sk", title="{name} (okres)",
                  official=SK_DISTRICTS, strip="District of ",
                  fields=SK_FIELDS),
        )),
    # North Macedonia: the 2021 census, which the English article of each
    # municipality prints beside the 2002 one in a four-column table. The
    # regions are not here -- they have no such table -- and say so.
    "MKD": Country(
        iso3="MKD", out="europe_wiki_north_macedonia.json", decimal=".",
        census="State Statistical Office of North Macedonia, Census of "
               "Population, Households and Dwellings",
        licence="Official statistics; compilation CC BY-SA 4.0",
        declared={
            "language": (
                "The one table a North Macedonian municipality's article "
                "carries as a matter of course is the census's ethnicity. A "
                "few also print mother tongue and religion, under headings "
                "that differ from article to article and sometimes twice "
                "over for two boundary eras, and this reader does not "
                "attempt them."),
            "religion": (
                "The one table a North Macedonian municipality's article "
                "carries as a matter of course is the census's ethnicity. A "
                "few also print religion, under headings that differ from "
                "article to article, and this reader does not attempt them."),
        },
        levels=(
            Level(level="admin2", lang="en",
                  title="{name} Municipality", match="folded",
                  category="Category:Municipalities of North Macedonia",
                  article_trim=r"\s+Municipality(,.*)?$",
                  # The boundary file draws the pre-2013 layout. Four of
                  # these were merged into Kicevo in 2013 and one is a
                  # translation rather than a transliteration ("and" for
                  # "i"), so none of the five is in the present category,
                  # and each still has an article of its own.
                  titles={
                      "Drugovo": "Drugovo Municipality",
                      "Oslomej": "Oslomej Municipality",
                      "Vraneshtitsa": "Vraneštica Municipality",
                      "Zajas": "Zajas Municipality",
                      "Mavrovo and Rostusha": "Mavrovo i Rostuše Municipality",
                  },
                  fields=(MK_ETHNICITY,)),
        )),
    # Moldova: the districts, whose English articles carry an ethnic table of
    # percentages and cite the census the infobox is dated by, plus the five
    # units that are not districts and so are in no category of them.
    # Chisinau, Balti and Gagauzia are named to their articles and read like
    # any other unit -- which gets the capital's 720,128 people all three
    # fields and Gagauzia all three, and measures Balti's article as
    # publishing no composition at all. Bender and Transnistria are refused,
    # in writing, for the reason under MD_ABSENT.
    #
    # Four districts -- Edinet, Falesti, Glodeni and Riscani -- have a
    # Demographics heading in English with no table under it, and that is
    # what their records say. The Romanian edition does carry an ethnic
    # table for each of them, and it was read and not taken: those tables
    # are the 2004 census, twenty years older than the 2024 figures every
    # other Moldovan unit here carries, three of the four cite nothing at
    # all (so they would be published undated, beside neighbours dated
    # 2024), and Riscani's has two rows merged into one cell -- "Moldoveni
    # Romani 1 | 50.391 777 | 72,55% 1,12%" -- which is two peoples sharing
    # a label and would be refused anyway. Reaching them would also need a
    # per-unit edition, which this reader does not have. Measured and left.
    "MDA": Country(
        iso3="MDA", out="europe_wiki_moldova.json", decimal=".",
        census="Biroul Naţional de Statistică, Recensământul Populaţiei şi al "
               "Locuinţelor",
        licence="Official statistics; compilation CC BY-SA 4.0",
        # Three of the thirty-two districts carry the census reference on the
        # ethnic table; the rest cite it once, from population_footnotes, and
        # transcribe the same 2024 release into the same two-column table.
        # The pattern is the National Bureau's own results page, so a district
        # can only borrow a citation that is to the census itself.
        infobox_citation=r"statistica\.gov\.md|Recens[aă]m[aâ]ntul|"
                         r"National Bureau of Statistics",
        # No declared gap for religion or language any more. It used to say
        # that a Moldovan article carries neither, and that is a statement
        # about districts which stopped being true of the country the moment
        # the capital, Gagauzia and Taraclia were reached: all three publish
        # a religion table, and two of them publish languages. Each unit now
        # says for itself which kind of empty it is -- no such heading, a
        # heading with no table under it, a table whose column is blank --
        # because that is what was measured for it.
        levels=(
            Level(level="admin1", lang="en", title="{name} District",
                  category="Category:Districts of Moldova", match="folded",
                  article_trim=r"\s+District$",
                  titles=MD_TITLES, absent=MD_ABSENT,
                  fields=MD_FIELDS),
            Level(level="admin2", lang="en", title="{name} District",
                  category="Category:Districts of Moldova", match="folded",
                  article_trim=r"\s+District$",
                  titles=MD_TITLES, absent=MD_ABSENT,
                  fields=MD_FIELDS),
        )),
    # Serbia: ethnicity, which is what the English article of a district and
    # of a municipality carries and the only one of the three it does. The
    # Serbian edition adds religion at the district level, in a table whose
    # cells hold a count and a share inside one pair of brackets; that is a
    # second reader and it is not written yet, so religion is a stated gap.
    #
    # No category lists Serbia's units -- the one that looks like it holds
    # them holds its own list article and nothing else -- so the candidates
    # are what that list article links to, and the join is by folding both
    # sides to plain letters: the boundary file writes "Arandjelovac" where
    # Serbia writes "Arandelovac", a letter shorter, so a positional match
    # would fail on exactly the names a romanisation changes the length of.
    "SRB": Country(
        iso3="SRB", out="europe_wiki_serbia.json", decimal=".",
        census="Републички завод за статистику, Попис становништва, "
               "домаћинстава и станова (Statistical Office of the Republic of "
               "Serbia, Census of Population, Households and Dwellings)",
        licence="Official statistics; compilation CC BY-SA 4.0",
        declared={
            "religion": (
                "The English article of a Serbian district or municipality "
                "carries an ethnic table and no religion table. The Serbian "
                "edition's district articles do carry one, in a table whose "
                "cells hold a count and a share inside one pair of brackets "
                "-- '112.084 (89,67%)' -- which this reader does not read."),
            "language": (
                "No Serbian unit article measured carries a mother-tongue "
                "composition, in either edition, though the census asks the "
                "question and publishes it by municipality."),
        },
        levels=(
            Level(level="admin1", lang="en", title="{name}", match="folded",
                  links="Administrative districts of Serbia",
                  # The list article names the City of Belgrade, which the
                  # boundary file draws as a district, by its own article;
                  # and Srem District, which the file calls by the region's
                  # English name, Syrmia.
                  titles={"Belgrade": "Belgrade",
                          "Syrmia District": "Srem District"},
                  fields=(RS_ETHNICITY,)),
            Level(level="admin2", lang="en", title="{name}", match="folded",
                  links="Municipalities and cities of Serbia",
                  shape_trim=r"\s+(Municipality|Municipal\*|City)$",
                  article_trim=r",\s*Serbia$",
                  titles={"Petrovac-na-Mlavi Municipality": "Petrovac na Mlavi",
                          "Raska Municipality": "Raška"},
                  fields=(RS_ETHNICITY,)),
        )),
    # Bulgaria: the composition is in the Bulgarian edition and not in the
    # English one, whose province articles carry a 2001 religion table and
    # nothing else. The article is reached by its interlanguage link from
    # the English title rather than by a transliteration invented here.
    #
    # Mother tongue is a province-level table and it is the 2001 census:
    # the Bulgarian articles have not been brought forward to 2011 for that
    # field, and a 2001 figure said to be 2001 is a figure, while one said
    # to be 2011 would be a mistake.
    "BGR": Country(
        iso3="BGR", out="europe_wiki_bulgaria.json", decimal=".",
        census="Национален статистически институт, Преброяване на населението "
               "(National Statistical Institute of Bulgaria, Census of "
               "Population and Housing)",
        licence="Official statistics; compilation CC BY-SA 4.0",
        levels=(
            Level(level="admin1", lang="bg", via="en", match="folded",
                  title="{name} Province",
                  category="Category:Provinces of Bulgaria",
                  article_trim=r"\s+Province$",
                  fields=BG_PROVINCE),
            Level(level="admin2", lang="bg", via="en",
                  title="{name} Municipality", fields=BG_MUNICIPALITY),
        )),
    # Montenegro: the 23 municipalities the boundary file draws, at both
    # levels because it draws them at both.
    "MNE": Country(
        iso3="MNE", out="europe_wiki_montenegro.json", decimal=".",
        census="Monstat, Popis stanovništva, domaćinstava i stanova",
        licence="Official statistics; compilation CC BY-SA 4.0",
        declared={"language": (
            "A Montenegrin municipality's article carries ethnicity and "
            "religion and no mother-tongue table, though the census asks "
            "the question and publishes it.")},
        levels=(
            Level(level="admin1", lang="en", title="{name}", match="folded",
                  category="Category:Municipalities of Montenegro",
                  article_trim=r"\s+Municipality$",
                  shape_trim=r"\s+Municipality$",
                  titles=ME_TITLES, fields=ME_FIELDS),
            Level(level="admin2", lang="en", title="{name}", match="folded",
                  category="Category:Municipalities of Montenegro",
                  article_trim=r"\s+Municipality$",
                  shape_trim=r"\s+Municipality$",
                  titles=ME_TITLES, fields=ME_FIELDS),
        )),
}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

SITE = Path(__file__).resolve().parent.parent.parent / "site" / "data"
# How far a table's own head count may be from the population this map
# already carries for the shape and still be the same place. A census table
# and a Eurostat estimate are years apart, so the band is wide; what it is
# there to catch is an article about the town rather than about the district
# around it, which is off by a factor and not by a fifth.
POPULATION_BAND = (0.55, 1.8)


def shapes(iso3: str, level: str) -> list[dict[str, Any]]:
    return read_json(SITE / level / f"{iso3}.json", []) or []


def trimmed(name: str, pattern: str) -> str:
    """The comparison key: the name with the word that is not part of it gone.

    The boundary file writes "Ada Municipality" and "Cacak City"; the English
    Wikipedia writes "Ada, Serbia" and "Cacak" with its diacritics. Neither
    side's extra word is part of the place's name, and the letters that are
    have to line up for the positional match below to mean anything.
    """
    return re.sub(pattern, "", name).strip(" ,-") if pattern else name


def article_titles(country: Country, level: Level, names: list[str]
                   ) -> tuple[dict[str, str], dict[str, str]]:
    """({shape name: article title}, {shape name: why it has none}).

    Three ways a title is arrived at, in order: the level's own table of
    exceptions, the boundary file's spelling matched against the country's
    own list of unit names, and the level's pattern applied to the name as
    the file spells it.
    """
    titles: dict[str, str] = {}
    refused: dict[str, str] = dict(level.absent or {})
    # Whether this level has a list of the country's own unit names to join
    # against. Where it has, the pattern below is not used at all: it was
    # used for every unit at first, which quietly made the list dead code
    # and sent the reader to "Bogdantsi Municipality", the boundary file's
    # transliteration, while the article is "Bogdanci Municipality" and the
    # category had said so.
    listed = bool(level.official or level.category or level.links)
    for name in names:
        if name in refused:
            continue
        if level.titles and name in level.titles:
            titles[name] = level.titles[name]
        elif not listed:
            titles[name] = level.title.format(name=name)
    official = level.official
    article_of: dict[str, str] = {}
    if level.category or level.links:
        where = level.category_lang or level.via or level.lang
        members = (category_members(level.category, where) if level.category
                   else link_targets(level.links, where))
        for title in members:
            key = trimmed(title, level.article_trim)
            article_of.setdefault(key, title)
        official = tuple(article_of)
        log(f"    {level.category or level.links}: {len(members)} article(s), "
            f"{len(official)} distinct names")
    if listed and official:
        prefix = level.strip or ""
        spellings: dict[str, str] = {}
        for name in names:
            if name in titles or name in refused:
                continue
            key = name[len(prefix):] if name.startswith(prefix) else name
            spellings[trimmed(key, level.shape_trim)] = name
        join = match_folded if level.match == "folded" else match_spellings
        matched, unmatched = join(list(spellings), list(official))
        for spelling, name in matched.items():
            titles[spellings[spelling]] = (
                article_of[name] if article_of else level.title.format(name=name))
        for spelling, why in unmatched.items():
            refused[spellings[spelling]] = why
    if level.via:
        found = langlinks(sorted(set(titles.values())), level.via, level.lang)
        for name, title in list(titles.items()):
            if title in found:
                titles[name] = found[title]
            else:
                del titles[name]
                refused[name] = (
                    f"the English Wikipedia article {title!r} has no "
                    f"{level.lang}.wikipedia counterpart, and the composition "
                    f"is published only in that edition")
    return titles, refused


def field_source(country: Country, spec: Composition, kind: str, year: int,
                 title: str, lang: str) -> dict[str, str]:
    return {"field": spec.field,
            "name": f"{country.census} ({year}), as the {lang}.wikipedia "
                    f"article '{title}' transcribes it",
            "url": f"https://{lang}.wikipedia.org/wiki/"
                   + urllib.parse.quote(title.replace(" ", "_")),
            "license": country.licence}


def read_field(wikitext: str, spec: Composition, country: Country, title: str,
               lang: str) -> tuple[dict[str, Any] | None, str]:
    """(what was read, why it was not).

    The rules are Indonesia's, kept whole because they are the reason the
    figures can be trusted: a figure with no citation is not read, and a
    figure whose citation cannot be dated is not read. Europe adds one thing
    Indonesia did not need. A census table transcribed into an article
    usually prints the census year in its own header -- "pocet (2011)",
    "2002 | 2021" -- while the reference beside it is a bare link to the
    office's results site with no year anywhere in it. That header year is
    not the editor's access date and not a guess: it is printed with the
    figures, by the same hand. So the citation is still required absolutely,
    and where it carries no year the table's own header may supply one. The
    note says which of the two dated the figure.
    """
    table, body, why = find_table(wikitext, spec)
    if why:
        return None, why
    definitions = ref_definitions(wikitext)
    cites = citations(body, definitions)
    borrowed = False
    if not cites and country.infobox_citation:
        cites = [c for line in infobox_lines(wikitext)
                 for c in citations(line, definitions)
                 if re.search(country.infobox_citation, c, re.I)]
        borrowed = bool(cites)
    # An uncited table is read, and the article is named as the source.
    #
    # The owner's decision of 22 September 2026, and it overrides the rule
    # inherited from the Indonesian reader. That rule refused a table the
    # article cited nothing for, and on Wikipedia that is a fact about
    # editing habits rather than about evidence: Moldova's districts all
    # transcribe the same 2024 census into the same table and three of
    # thirty-two happen to repeat the <ref> on it, so twenty-nine districts
    # went empty over where an editor put a footnote.
    #
    # Nothing is invented by reading them. The figures still have to survive
    # every other test -- the labels must all be known, and the shares must
    # add to about a hundred -- and the record says plainly that the article
    # is what it rests on, so a reader of the panel can weigh it.
    uncited = not cites
    # Which mark separates a fraction is a fact about the country, except
    # where it is not: Bulgaria's provinces write "89.72" and its
    # municipalities write "64,81", in the same edition and under the same
    # heading. So the declared mark is tried first and the other one after
    # it, and the arbiter is the same check that would otherwise refuse the
    # table -- only a reading whose shares add to about a hundred is
    # accepted, and reading "64,81" as six thousand adds to ten thousand.
    other = "," if country.decimal == "." else "."
    counts: dict[str, float] = {}
    for mark in (country.decimal, other):
        counts, dropped, why = read_rows(table, spec, mark)
        if why:
            if mark == other or "no entry for" in why:
                return None, why
            continue
        rows, bad, remark = shares_of(counts)
        if not bad:
            break
        if mark == other:
            return None, bad
    else:
        return None, bad
    if mark != country.decimal:
        remark = (f"The table writes a fraction with \"{mark}\" where this "
                  f"country's articles usually write \".\"; read as shares, "
                  f"they add to a hundred. " + remark).strip()
    if dropped:
        remark = (" ".join(dropped) + " " + remark).strip()
    if borrowed:
        remark = ("The table itself carries no reference; the citation is the "
                  "one the article's infobox gives for the same census. "
                  + remark).strip()
    if uncited:
        remark = ("The article cites nothing for this table, so the article "
                  "itself is the source on the record. " + remark).strip()
        kind, year, cited = "other", None, (
            f"https://{lang}.wikipedia.org/wiki/"
            + urllib.parse.quote(title.replace(" ", "_")))
    else:
        described = sorted((describe_citation(c) for c in cites),
                           key=lambda d: KIND_RANK[d[0]])
        kind, year, cited = described[0]
        years = [d[1] for d in described if d[1]]
        year = year or (max(years) if years else None)
    dated = "its citation"
    # The year the column read is printed under, where the table prints one.
    # This is not a fallback for an undated citation but the better answer
    # where both exist: Blagoevgrad's ethnic table prints 2001 and 2011 side
    # by side and cites the 2001 release first, so the 2011 column -- which
    # is the one read -- was being stamped 2001. A figure dated by the
    # wrong census is worse than no figure.
    header = " ".join(" ".join(row) for row in table[:2])
    printed = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", header)]
    if printed and spec.value == -1:
        if year and max(printed) != year:
            remark = (f"The citation is for {year}; the column read is the one "
                      f"the table's own header labels {max(printed)}, and that "
                      f"is the year on this record. " + remark).strip()
        year = max(printed)
        dated = "the table's own header"
    if year is None:
        # An undated figure is read and said to be undated.
        #
        # The owner's decision of 22 September 2026, and the same one that
        # dropped the citation gate above. Refusing here threw away a whole
        # composition to avoid printing one unknown field, which is a worse
        # trade than it looks: a district with no ethnic table at all and a
        # district whose table is undated came out identical on the map.
        remark = ("Neither the citation nor the table's own header carries a "
                  "year, so the date these figures are as of is unknown. "
                  + remark).strip()
        dated = "nothing on the page"
    return {"rows": rows, "year": year, "kind": kind, "cited": cited,
            "remark": remark, "dated": dated, "counts": counts}, ""


def field_fields(reading: dict[str, Any], spec: Composition, country: Country,
                 title: str, lang: str) -> dict[str, Any]:
    sentences = [
        f"Population by {FIELD_WORD[spec.field]} for {reading['year']} from "
        f"{EXPLAINED[reading['kind']]}, as the {lang}.wikipedia article "
        f"'{title}' transcribes and cites it.",
        CAVEAT[reading["kind"]],
    ]
    if reading["dated"] != "its citation" and "The citation is for" not in reading["remark"]:
        # Only where the citation really is undated. Where it carries a year
        # and the table's header carries another, the remark below already
        # says both and which one the record holds, and this sentence said
        # the opposite of it.
        sentences.append("The citation carries no year; the figures are dated "
                         "by the year printed in the table's own header.")
    if reading["remark"]:
        sentences.append(reading["remark"])
    return {
        spec.field: reading["rows"],
        f"{spec.field}_year": reading["year"],
        f"{spec.field}_note": " ".join(sentences),
        f"{spec.field}_source": field_source(country, spec, reading["kind"],
                                             reading["year"], title, lang),
    }


FIELD_WORD = {"religion": "religion", "language": "mother tongue",
              "ethnicity": "ethnicity"}


def run(country: Country) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    parents = {s["id"]: s["name"] for s in shapes(country.iso3, "admin1")}
    for level in country.levels:
        units = shapes(country.iso3, level.level)
        titles, refused = article_titles(country, level, [u["name"] for u in units])
        log(f"  {country.iso3} {level.level}: {len(units)} shapes, "
            f"{len(titles)} with an article, {len(refused)} without")
        for why in sorted(set(refused.values())):
            log(f"    no article: {why}")
        read = {spec.field: 0 for spec in level.fields}
        for unit in units:
            name = unit["name"]
            fields: dict[str, Any] = {k: gap(NOT_AVAILABLE, why)
                                      for k, why in (country.declared or {}).items()}
            sources: list[dict[str, str]] = []
            title = titles.get(name)
            if title is None:
                for spec in level.fields:
                    fields[spec.field] = gap(NOT_AVAILABLE, refused[name])
            else:
                wikitext, resolved = fetch(title, level.lang)
                if not wikitext:
                    for spec in level.fields:
                        fields[spec.field] = gap(
                            NOT_AVAILABLE,
                            f"the {level.lang}.wikipedia article {title!r}, "
                            f"which is where this country publishes its "
                            f"compositions, does not exist")
                else:
                    # Two specs for one field are two shapes the same table
                    # takes, not two readings of it. A country whose units
                    # are not all the same kind of unit needs this: Moldova
                    # publishes its capital's mother tongues under "First
                    # language", with a column per census since 1989, and
                    # Gagauzia's under "Mother tongue", beside a second pair
                    # of columns for the language spoken at home. Neither
                    # spec can read the other's table and both must be
                    # tried, so the first that reads wins and the rest are
                    # not attempted. What a field that reads nothing says is
                    # the first spec's refusal, because the first spec is the
                    # shape the country's articles usually take.
                    taken: set[str] = set()
                    failed: set[str] = set()
                    for spec in level.fields:
                        if spec.field in taken:
                            continue
                        reading, why = read_field(wikitext, spec, country,
                                                  resolved, level.lang)
                        if reading and not fits_population(reading, unit, name, spec):
                            reading, why = None, (
                                "the table in the article counts a population "
                                "this shape does not have, so the article is "
                                "about some other place; it is not read")
                        if reading is None:
                            if spec.field not in failed:
                                failed.add(spec.field)
                                fields[spec.field] = gap(NOT_AVAILABLE, why)
                                log(f"    {name}: {spec.field}: {why}")
                            continue
                        got = field_fields(reading, spec, country, resolved,
                                           level.lang)
                        sources.append(got.pop(f"{spec.field}_source"))
                        fields.update(got)
                        taken.add(spec.field)
                        read[spec.field] += 1
            parent = (country.iso3 if level.level == "admin1"
                      else parents.get(unit.get("parent"), ""))
            records.append(record(
                f"{country.iso3}-{level.level}-{slugify(name)}", name,
                level=level.level,
                parent=country.iso3 if level.level == "admin1"
                else f"{country.iso3}-admin1-{slugify(parent)}" if parent
                else country.iso3,
                parent_name=parent if level.level == "admin2" else None,
                country=country.iso3,
                sources=sources, **fields))
        for field, n in read.items():
            log(f"  {country.iso3} {level.level}: {field}: {n} of {len(units)}")
    return records


def fits_population(reading: dict[str, Any], unit: dict[str, Any], name: str,
                    spec: Composition) -> bool:
    """Whether the table counts the people who live in this shape.

    The guard exists because of how these articles are titled. The English
    Wikipedia gives a Serbian municipality the name of the town at its
    centre, and the town has an article of its own under names that differ
    by a comma; a reader that followed the wrong one would publish the
    town's composition on the municipality's shape, which is a mis-match and
    invisible. A table of percentages has nothing to check, so this passes
    it; a table of counts is weighed against the population this map already
    carries for the shape.
    """
    counted = sum(v for v in reading["counts"].values())
    if counted <= BOUNDS[1]:
        # Percentages, which have nothing to weigh.
        #
        # The bound is the same one that decides whether a set of figures is
        # a composition at all, and it has to be: shares_of has already run
        # by the time this is asked, so anything still here added to between
        # 90 and 103 and is a set of shares by that decision. A fixed 101
        # said otherwise about Briceni, whose ethnic table adds to 101.31 as
        # printed -- nine percentages, weighed against a district of 46,894
        # people and refused for being 0.2% of it. No unit at either level
        # of this map has a hundred and three inhabitants, so nothing that
        # really is a count can slip through here.
        return True
    population = (unit.get("population") or {})
    total = population.get("value") if isinstance(population, dict) else None
    if not total:
        return True
    ratio = counted / total
    if POPULATION_BAND[0] <= ratio <= POPULATION_BAND[1]:
        return True
    log(f"    {name}: the {spec.field} table counts {counted:,.0f} against a "
        f"population of {total:,} ({100 * ratio:.0f}%)")
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", nargs="+", metavar="LANG:TITLE",
                    help="print one or more articles' infobox, references and tables")
    ap.add_argument("--category", nargs="+", metavar="LANG:CATEGORY",
                    help="print the article titles in a category")
    ap.add_argument("--country", nargs="+", metavar="ISO3",
                    help="the countries to read; the default is every spec")
    ap.add_argument("--rows", type=int, default=25)
    ap.add_argument("--width", type=int, default=40)
    args = ap.parse_args(argv)
    if args.probe:
        for spec in args.probe:
            probe(spec, args.rows, args.width)
        PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)
        PROBE_LOG.write_text("\n".join(_probe_lines) + "\n", encoding="utf-8")
        log(f"\nwrote {PROBE_LOG}")
        return 0
    if args.category:
        for spec in args.category:
            lang, _, name = spec.partition(":")
            found = category_members(name.replace("_", " "), lang)
            say(f"\n===== [{lang}] {name}: {len(found)} article(s)")
            for title in found:
                say(f"    {title}")
        PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)
        PROBE_LOG.write_text("\n".join(_probe_lines) + "\n", encoding="utf-8")
        return 0
    wanted = [c.upper() for c in (args.country or SPECS)]
    unknown = [c for c in wanted if c not in SPECS]
    if unknown:
        raise SystemExit(f"europe_wiki: no spec for {unknown}")
    by_file: dict[str, list[dict[str, Any]]] = {}
    for iso3 in wanted:
        country = SPECS[iso3]
        log(f"{iso3}:")
        by_file.setdefault(country.out, []).extend(run(country))
    for filename, records in by_file.items():
        write_json(PROCESSED / filename, records)
        log(f"wrote {PROCESSED / filename} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
