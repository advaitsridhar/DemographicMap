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
    r"вероисповед|склад|состав|склау|fe[j]?e|besim|gjuh|struktur",
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


# ---------------------------------------------------------------------------
# What a citation is, and what kind of count it describes
# ---------------------------------------------------------------------------

SOURCE_KINDS: tuple[tuple[str, str, str], ...] = (
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
    "census": "A census count.",
    "office": "A statistical-office figure, which may be a census table or an estimate.",
    "registry": "A registry count of who is registered, not a census answer.",
    "ministry": "A ministry figure, not a census answer.",
    "other": "The citation does not say which kind of count this is.",
}
KIND_RANK = {"census": 0, "office": 1, "ministry": 2, "registry": 3, "other": 4}

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


def cite_field(body: str, field: str) -> str:
    m = re.search(r"\|\s*" + re.escape(field) + r"\s*=\s*([^|}]*)", body, re.I)
    return " ".join(m.group(1).split()) if m else ""


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
        years = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", path)]
    if not years:
        # The citation's own date of publication; never its access date,
        # which is when the editor read it.
        dated = " ".join(cite_field(body, f) for f in ("year", "date", "publication-date"))
        years = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", dated)]
    if not years and "=" not in body:
        # A bare external link, "[url The census of 2011, volume 3]", which
        # is how half of these articles cite. It has no fields to read, so
        # the whole of it is the citation and the year in it is the
        # citation's own -- there is no access date in a bare link to
        # mistake it for.
        years = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", body)]
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
    remainder: str | None = None


@dataclass(frozen=True)
class Level:
    """One country at one level: where the articles are and what to read."""

    level: str
    title: str                       # applied to the shape's name
    fields: tuple[Composition, ...]
    lang: str = "en"
    via: str | None = None           # resolve the title above into this edition
    titles: dict[str, str] | None = None     # shape name -> article, where the pattern fails
    absent: dict[str, str] | None = None     # shape name -> why it has no article
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
    for name, body in sections(wikitext):
        if not section.search(name):
            continue
        seen = True
        for table in tables(body):
            if len(table) < 3:
                continue
            first = " ".join(" ".join(row) for row in table[:2])
            if header.search(first):
                return table, body, ""
    if not seen:
        return [], "", f"the article has no section matching {spec.section!r}"
    return [], "", ("the section is there and holds no table whose header this "
                    "reader knows; the article has been reorganised or carries "
                    "a different table")


def read_rows(table: list[list[str]], spec: Composition, decimal: str
              ) -> tuple[dict[str, float], list[str], str]:
    """({label: share}, the labels with no entry in the spec, why not).

    A row is read when its first cell is a label and the row carries at
    least as many numbers as the spec asks for. A row that carries none is
    a header continuation and is skipped in silence; a row whose label the
    spec has no entry for is collected and reported, never guessed at.
    """
    skip = re.compile(spec.skip, re.I)
    out: dict[str, float] = {}
    unknown: list[str] = []
    for row in table:
        if not row:
            continue
        label = cell_text(row[0])
        numbers = [n for n in (number(cell_text(c), decimal) for c in row[1:])
                   if n is not None]
        if not label or not numbers:
            continue
        if skip.search(label):
            continue
        wanted = spec.value if spec.value >= 0 else len(numbers) + spec.value
        if not 0 <= wanted < len(numbers):
            continue
        key = " ".join(label.lower().split())
        mapped = spec.labels.get(key)
        if mapped is None:
            unknown.append(label)
            continue
        out[mapped] = out.get(mapped, 0.0) + numbers[wanted]
    if unknown:
        return {}, unknown, f"labels this reader has no entry for: {unknown}"
    if not out:
        return {}, [], "the table holds no row this reader could read"
    return out, [], ""


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
    "iná": "Other", "ostatné": "Other", "ostatná": "Other",
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
    "slovenes": "Slovene", "czechs": "Czech", "poles": "Polish",
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
        section=r"n[áa]rodnostn[éeé] zlo[žz]enie|n[áa]rodnos",
        header=r"n[áa]rodnos[ťt]",
        value=-1,
        labels=SK_ETHNICITY,
        skip=r"^(spolu|celkom|obyvate)"),
    Composition(
        field="religion",
        section=r"n[áa]bo[žz]ensk[éeé] zlo[žz]enie|vierovyznanie",
        header=r"n[áa]bo[žz]enstvo|vyznanie",
        value=-1,
        labels=SK_RELIGION,
        skip=r"^(spolu|celkom|obyvate)"),
)

SPECS: dict[str, Country] = {
    "SVK": Country(
        iso3="SVK", out="europe_wiki_slovakia.json", decimal=",",
        census="Štatistický úrad SR, Sčítanie obyvateľov, domov a bytov 2011",
        licence="Official statistics; compilation CC BY-SA 4.0",
        levels=(
            Level(level="admin1", lang="sk", title="{name}",
                  titles=SK_REGIONS, fields=SK_FIELDS),
            Level(level="admin2", lang="sk", title="{name} (okres)",
                  official=SK_DISTRICTS, strip="District of ",
                  fields=SK_FIELDS),
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
    for name in names:
        if name in refused:
            continue
        if level.titles and name in level.titles:
            titles[name] = level.titles[name]
        elif level.official:
            continue          # settled below, in one pass over the whole level
        else:
            titles[name] = level.title.format(name=name)
    official = level.official
    article_of: dict[str, str] = {}
    if level.category:
        members = category_members(level.category, level.lang)
        for title in members:
            key = trimmed(title, level.article_trim)
            article_of.setdefault(key, title)
        official = tuple(article_of)
        log(f"    {level.category}: {len(members)} article(s), "
            f"{len(official)} distinct names")
    if official:
        prefix = level.strip or ""
        spellings: dict[str, str] = {}
        for name in names:
            if name in titles or name in refused:
                continue
            key = name[len(prefix):] if name.startswith(prefix) else name
            spellings[trimmed(key, level.shape_trim)] = name
        matched, unmatched = match_spellings(list(spellings), list(official))
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
    if not cites:
        return None, ("the article prints this table and cites nothing for it; "
                      "an uncited figure is not read")
    counts, unknown, why = read_rows(table, spec, country.decimal)
    if why:
        return None, why
    rows, why, remark = shares_of(counts)
    if why:
        return None, why
    described = sorted((describe_citation(c) for c in cites),
                       key=lambda d: KIND_RANK[d[0]])
    kind, year, cited = described[0]
    years = [d[1] for d in described if d[1]]
    year = year or (max(years) if years else None)
    dated = "its citation"
    if year is None:
        header = " ".join(" ".join(row) for row in table[:2])
        printed = [int(y) for y in re.findall(r"\b(19\d\d|20[0-4]\d)\b", header)]
        if not printed:
            return None, ("neither the citation nor the table's own header "
                          "carries a year, so there is no date the figures "
                          "are as of")
        year = max(printed)
        dated = "the table's own header"
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
    if reading["dated"] != "its citation":
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
            fields: dict[str, Any] = {}
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
                    for spec in level.fields:
                        reading, why = read_field(wikitext, spec, country,
                                                  resolved, level.lang)
                        if reading and not fits_population(reading, unit, name, spec):
                            reading, why = None, (
                                "the table in the article counts a population "
                                "this shape does not have, so the article is "
                                "about some other place; it is not read")
                        if reading is None:
                            fields[spec.field] = gap(NOT_AVAILABLE, why)
                            log(f"    {name}: {spec.field}: {why}")
                            continue
                        got = field_fields(reading, spec, country, resolved,
                                           level.lang)
                        sources.append(got.pop(f"{spec.field}_source"))
                        fields.update(got)
                        read[spec.field] += 1
            parent = (country.iso3 if level.level == "admin1"
                      else parents.get(unit.get("parent"), ""))
            records.append(record(
                f"{country.iso3}-{level.level}-{slugify(name)}", name,
                level=level.level,
                parent=country.iso3 if level.level == "admin1"
                else f"{country.iso3}-admin1-{slugify(parent)}" if parent
                else country.iso3,
                parent_name=parent or None, country=country.iso3,
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
    if counted <= 100:                    # percentages, not counts
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
