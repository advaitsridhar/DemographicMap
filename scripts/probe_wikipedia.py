#!/usr/bin/env python3
"""Ask Wikipedia about every subdivision on this map, and report what it has.

The owner's instruction was to check every single first- and second-level unit
against Wikipedia -- not a sample, and not only the ones whose country already
has a reader. This does that, and writes nothing but a report: it is the
measurement that decides which countries are worth a bespoke reader and which
genuinely have nothing to read.

It is one sweep rather than a per-country agent because the fetching is bulk
work. The MediaWiki API takes fifty titles per request and Wikidata fifty
entities, so 52,573 units cost about 2,100 requests rather than 52,573. What
is *not* bulk work is writing a reader once this has run: every country names
its demographic section differently, in its own language, and puts the figures
in a table or an infobox or neither. That is the part a reader has to be
written for, country by country, and this report says which countries have
anything there to write one against.

The chain, per unit:

    Wikidata QID  ->  sitelinks  ->  the article's title in each edition
                  ->  wikitext   ->  does it carry a demographic section,
                                     an infobox parameter, or nothing?

Two editions are asked for each unit: the country's own principal language,
because that is where a national statistical table is usually transcribed --
the Dutch provinces' religion is in nl.wikipedia's infobox and nowhere in the
English article -- and English, because it is the fallback that exists for
almost everything.

Usage:
    python -m scripts.probe_wikipedia                      # every country
    python -m scripts.probe_wikipedia --countries NLD,BEL
    python -m scripts.probe_wikipedia --level admin1
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED, log, read_json, write_json   # noqa: E402

REPORT = PROCESSED / "wikipedia_probe.json"
WD_API = "https://www.wikidata.org/w/api.php"
BATCH = 50
PAUSE = 0.2
HEADERS = {"User-Agent": "DemographicMap/1.0 "
                         "(+https://github.com/advaitsridhar/DemographicMap)"}

# A heading or an infobox parameter that would carry one of the three fields,
# in the languages these articles are written in. Deliberately wide: this is a
# probe, and a false positive costs a line in a report while a false negative
# costs a country. The words come from the readers already written for
# Indonesia, Slovakia, Bulgaria, Serbia, North Macedonia, Moldova and the
# Netherlands, plus the obvious cognates.
WANTED = re.compile(
    r"religi|godsdienst|gezindte|vierovyznan|n[áa]bo[žz]en|религи|вероизповед|"
    r"agama|kepercayaan|religion|confession|culto|credo|"
    r"langue|lengua|idioma|l[íi]ngua|sprache|taal|jazyk|мова|език|язык|"
    r"bahasa|language|mother tongue|native language|"
    # "ethni" not "ethnic": French writes "Composition ethnique", which the
    # narrower form missed -- and that is every francophone country at once.
    r"ethni|etni|n[áa]rodnost|националн|етничк|suku|volksgroep|"
    r"nationalit|ancestry|race",
    re.I)
# A heading is only interesting if something tabular or list-shaped follows.
TABLE = re.compile(r"^\s*\{\|", re.M)
SECTION = re.compile(r"^==+\s*([^=\n]+?)\s*=+\s*$", re.M)
INFOBOX_PARAM = re.compile(r"^\s*\|\s*([^=|{}\n]{2,40}?)\s*=([^\n]*)$", re.M)

# A composition states shares. Requiring one is what separates the Dutch
# provinces' "religie = 68,4% geen gezindte<br/>18,7% Protestants" from
# Bhutan's "WWW-SPRACHE = de", which is the language of the town's *website*
# and was counted as a language composition 170 times by the first sweep.
SHARE = re.compile(r"\d[\d.,]*\s*%|%\s*\d")


def get(api: str, **params: object) -> dict[str, Any]:
    params = {**params, "format": "json", "formatversion": "2"}
    url = f"{api}?{urllib.parse.urlencode(params)}"
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=HEADERS), timeout=90) as fh:
                return json.load(fh)
        except Exception:                            # noqa: BLE001 -- retried
            if attempt == 3:
                raise
            time.sleep(4 * attempt)
    return {}


def sitelinks(qids: list[str]) -> dict[str, dict[str, str]]:
    """{qid: {wiki: title}} for a batch of entities."""
    out: dict[str, dict[str, str]] = {}
    data = get(WD_API, action="wbgetentities", ids="|".join(qids),
               props="sitelinks")
    for qid, entity in (data.get("entities") or {}).items():
        out[qid] = {k: v.get("title", "")
                    for k, v in (entity.get("sitelinks") or {}).items()
                    if k.endswith("wiki")}
    return out


def wikitexts(lang: str, titles: list[str]) -> dict[str, str]:
    """{title: wikitext} for a batch from one edition."""
    data = get(f"https://{lang}.wikipedia.org/w/api.php", action="query",
               prop="revisions", rvprop="content", rvslots="main",
               titles="|".join(titles), redirects="1")
    out: dict[str, str] = {}
    query = data.get("query") or {}
    renamed = {r["to"]: r["from"] for r in (query.get("redirects") or [])}
    for page in query.get("pages") or []:
        title = page.get("title") or ""
        revs = page.get("revisions") or []
        if not revs:
            continue
        body = ((revs[0].get("slots") or {}).get("main") or {}).get("content")
        if body:
            out[renamed.get(title, title)] = body
    return out


# How much a reader could get out of each verdict, worst to best. It lives
# beside verdict() because it must list every kind verdict() can return: the
# re-probe of 22 September died on KeyError('section+figures') after 16,353
# units had been resolved, because the two were edited apart. A test walks
# verdict()'s own branches against this.
RANK = ("nothing", "section only", "infobox", "section+infobox",
        "section+figures", "section+figures+infobox",
        "section+table", "section+table+infobox")


def verdict(wikitext: str) -> tuple[str, list[str]]:
    """What this article carries, and the headings or parameters that say so.

    A heading and an infobox parameter are reported together rather than one
    shadowing the other, and the Netherlands is why. Its province articles
    have a "Religie" heading with prose under it and the actual figures in the
    infobox; a probe that stopped at the heading would have called that
    "section only" and the country would have read as having nothing to write
    a reader against -- which is precisely the mistake the Europe reader made,
    and why twelve Dutch provinces sat empty.
    """
    # Every heading with its real position, so a section can be bounded by the
    # next one. The first version searched 4,000 characters from
    # ``wikitext.find(heading)`` -- which finds the first occurrence of the
    # *string* "Ethnicity" anywhere, a link or the lead included, not the
    # heading -- and then read straight across into whatever table came next.
    # Every one of Hungary's 126 districts was reported as carrying a table
    # that way; their Ethnicity and Religion sections are prose, and the table
    # the probe found was a population time series in another section.
    marks = [(m.start(), m.end(), m.group(1)) for m in SECTION.finditer(wikitext)]
    hits, tabled, figured = [], [], []
    for i, (_start, end, heading) in enumerate(marks):
        if not WANTED.search(heading):
            continue
        hits.append(heading)
        body = wikitext[end:marks[i + 1][0] if i + 1 < len(marks) else len(wikitext)]
        if TABLE.search(body):
            tabled.append(heading)
        elif SHARE.search(body):
            figured.append(heading)

    # An infobox parameter counts only when its value states shares. The name
    # alone is not evidence: "WWW-SPRACHE" is a website's language.
    params = [name for name, value in INFOBOX_PARAM.findall(wikitext)
              if WANTED.search(name) and SHARE.search(value)]

    if tabled:
        kind = "section+table+infobox" if params else "section+table"
    elif figured:
        kind = "section+figures+infobox" if params else "section+figures"
    elif params:
        kind = "section+infobox" if hits else "infobox"
    elif hits:
        kind = "section only"
    else:
        kind = "nothing"
    return kind, (tabled or figured or hits) + params


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--countries", default="")
    ap.add_argument("--level", default="both",
                    choices=["admin1", "admin2", "both"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--show", type=int, default=0, metavar="N",
                    help="print the matched section's own text for the first "
                         "N readable units and write nothing; the verdict has "
                         "been wrong twice and this is how it gets checked")
    args = ap.parse_args()

    units: list[dict[str, Any]] = []
    for level in (["admin1", "admin2"] if args.level == "both" else [args.level]):
        units += [u for u in read_json(PROCESSED / f"wikidata_{level}.json", [])
                  if u.get("wikidata")]
    only = {c.upper() for c in args.countries.split(",") if c}
    if only:
        units = [u for u in units if (u.get("country") or "") in only]
    log(f"probe_wikipedia: {len(units)} units with a Wikidata id")

    # Sitelinks first, in batches of fifty.
    links: dict[str, dict[str, str]] = {}
    for i in range(0, len(units), BATCH):
        chunk = [u["wikidata"] for u in units[i:i + BATCH]]
        try:
            links.update(sitelinks(chunk))
        except Exception as err:                     # noqa: BLE001 -- reported
            log(f"  sitelinks {i}: {type(err).__name__}: {err}")
        time.sleep(PAUSE)
        if i and i % (BATCH * 40) == 0:
            log(f"  {i} of {len(units)} units resolved")

    # Then the wikitext, grouped by edition so a batch is one request.
    by_wiki: dict[str, list[tuple[str, dict[str, Any]]]] = collections.defaultdict(list)
    no_article: list[dict[str, Any]] = []
    for unit in units:
        found = links.get(unit["wikidata"]) or {}
        if not found:
            no_article.append(unit)
            continue
        # The country's own edition if the unit has one there, else English,
        # else whatever edition exists -- an article in one language is worth
        # probing even when it is in none of the obvious ones.
        # "enwiki" was appended unconditionally and then indexed, which
        # raised KeyError on the first unit whose only article is in another
        # language -- 2,000 units into the first real run. English is a
        # preference, not a guarantee: a Nepali district or an Iranian county
        # may be written up only in its own edition.
        wiki = next((w for w in found if w != "enwiki"), None)
        for choice in [w for w in (wiki, "enwiki") if w and w in found]:
            by_wiki[choice].append((found[choice], unit))

    results: dict[str, dict[str, Any]] = {}
    shown = [0]
    for wiki, entries in sorted(by_wiki.items(), key=lambda kv: -len(kv[1])):
        lang = wiki[:-4]
        for i in range(0, len(entries), BATCH):
            chunk = entries[i:i + BATCH]
            try:
                bodies = wikitexts(lang, [t for t, _ in chunk])
            except Exception as err:                 # noqa: BLE001 -- reported
                log(f"  [{lang}] batch {i}: {type(err).__name__}: {err}")
                continue
            for title, unit in chunk:
                body = bodies.get(title)
                if not body:
                    continue
                kind, words = verdict(body)
                if args.show and kind != "nothing" and shown[0] < args.show:
                    shown[0] += 1
                    log(f"\n--- {unit.get('country')} {unit.get('level')} "
                        f"{title} [{lang}] {kind} {words}")
                    for m in SECTION.finditer(body):
                        if not WANTED.search(m.group(1)):
                            continue
                        rest = body[m.end():]
                        nxt = SECTION.search(rest)
                        text = rest[:nxt.start()] if nxt else rest
                        text = " ".join(text.split())[:700]
                        log(f"  [{m.group(1)}] {text}")
                key = unit["id"]
                best = results.get(key)
                if best is None or RANK.index(kind) > RANK.index(best["kind"]):
                    results[key] = {"country": unit.get("country"),
                                    "level": unit.get("level"),
                                    "name": unit.get("name"),
                                    "wiki": lang, "title": title,
                                    "kind": kind, "words": words[:6]}
            time.sleep(PAUSE)
        log(f"  [{lang}] {len(entries)} article(s) probed")

    # The report: per country, how many of its units carry what.
    per_country: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for row in results.values():
        per_country[row["country"]][f"{row['level']}:{row['kind']}"] += 1
    for unit in no_article:
        per_country[unit.get("country")][f"{unit.get('level')}:no article"] += 1

    # A run updates the countries it answered for and leaves the rest alone.
    #
    # 52,573 units over two editions is about 2,100 requests, which does not
    # fit in one 45-minute job, so this will be run in batches -- and a
    # wholesale write would mean each batch discarding the one before it.
    # fetch_wikidata learned the same lesson the expensive way.
    #
    # The unit of replacement is the country, and the test is whether this run
    # produced anything for it at all: a country that was asked about and
    # whose every request failed has no entry here, so its earlier rows stand
    # rather than being silently deleted by a network failure. Only a country
    # this run actually has something to say about is overwritten.
    if args.show:
        log("\n--show: nothing written")
        return 0
    out = Path(args.out) if args.out else REPORT
    previous = read_json(out, {}) or {}
    answered = set(per_country)
    kept = [row for row in previous.get("units", [])
            if row.get("country") not in answered]
    merged_per: dict[str, dict[str, int]] = {
        iso: counts for iso, counts in (previous.get("per_country") or {}).items()
        if iso not in answered}
    merged_per.update({k: dict(v) for k, v in per_country.items()})

    log("")
    log("%-5s %s" % ("iso", "units by what their article carries"))
    for iso in sorted(per_country):
        counts = per_country[iso]
        line = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        log(f"  {iso:4} {line}")
    total = collections.Counter()
    for counts in merged_per.values():
        total.update(counts)
    log("")
    log(f"this run: {len(answered)} countries, {len(results)} units")
    log(f"world so far ({len(merged_per)} countries): "
        + ", ".join(f"{k} {v}" for k, v in sorted(total.items())))
    write_json(out, {"per_country": merged_per, "units": kept + list(results.values())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
