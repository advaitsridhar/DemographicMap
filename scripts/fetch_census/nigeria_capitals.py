#!/usr/bin/env python3
"""Nigeria -- local government area headquarters, from English Wikipedia's article on each area.

The 2006 census's priority tables (nigeria_census) name no headquarters, and
Wikidata names a seat (its property P36) for 707 of the 774 local government
areas the map draws. For the other 67 the seat is read from English
Wikipedia's article on the area: the infobox's seat ("seat_type =
Headquarters", "seat = [[Iragbiji]]") or the lead's sentence naming it ("Its
headquarters are in the town of Iragbiji"). Each article is found through the
area's own Wikidata item (its English sitelink), or, for the six polygons
that carry no item, by the title given in ``TITLES``; each record cites the
revision read, by its permanent address and year.

A seat is written only where the article names one and, where the infobox
and the lead both name one, they agree. An area whose article names none, or
two that disagree, gets the reason, citing the article. Bakassi's polygon is
left out: it is the part of the 2006 area left on the Nigerian side after
2008 (nigeria_census), and its article's headquarters are the area's as it
was.

The helpers here (``wikidata_items``, ``articles``, ``seats``) also serve
gambia_capitals and liberia_capitals.

Usage:
    python -m scripts.fetch_census.nigeria_capitals
    python -m scripts.fetch_census.nigeria_capitals --dump NGA GMB LBR   # print what each article says
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_json, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import plain  # noqa: E402

WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://{lang}.wikipedia.org/w/api.php"
LICENCE = "CC BY-SA 4.0"
OUT = "nigeria_capitals.json"
SITE = PROCESSED.parent.parent / "site" / "data"
BATCH = 50

# Polygons that carry no Wikidata item: the English article on the area.
TITLES = {
    ("Osun", "Ilesha East"): "Ilesa East",
    ("Kaduna", "Zaria"): "Zaria (Local Government Area)",
    ("Abia", "Obi Nwga"): "Obi Ngwa",
    ("Benue", "Oturkpo"): "Otukpo",
    ("Abuja Federal Capital Territory", "Municipal Area Council"): "Abuja Municipal Area Council",
}
# Titles tried for the dump only, where a polygon has no item: The Gambia's
# two local government areas the map shows no seat for.
DUMP_TITLES = {
    ("GMB", "Kuntaur"): ("Kuntaur Local Government Area", "Kuntaur", "Kuntaur Administrative Area"),
    ("GMB", "Kanifing"): ("Kanifing Municipal Council", "Kanifing", "Kanifing Municipality"),
}
# Polygons not read: the ground is not the article's area.
NOT_READ = {("Cross River", "Bakassi")}

# Infobox parameters that name a seat, and the labels a seat_type may carry.
SEAT_PARAMS = ("seat", "headquarters", "hq", "capital", "admin_center", "chef-lieu",
               "chef_lieu", "chef-lieu de district")
SEAT_LABELS = ("headquarter", "seat", "capital", "admin", "secretariat", "chef-lieu")
# A seat named in a sentence: "Its headquarters are in the town of Iragbiji",
# "with its headquarters at Gwammaja", "The headquarters of the LGA is in X".
PLACE = r"(?P<x>\[\[[^\]]+\]\]|[A-Z][\w'’\-]*(?:[ \-][A-Z][\w'’\-]*){0,3})"
SENTENCES = (
    re.compile(r"\b(?:[Ii]ts|[Tt]he(?: [\w ]{0,40}?)?)(?: administrative)? "
               r"(?:headquarters?|seat|secretariat)(?: of [\w .'’\-]{0,60}?)? "
               r"(?:is|are|was|were|lies|lie)(?: located| situated| sited| based)? "
               r"(?:in|at)(?: the)?(?: (?:ancient |old |historic )?(?:town|city|village|community))?"
               r"(?: of)? " + PLACE),
    re.compile(r"\b(?:with|has) (?:its )?(?:administrative )?headquarters? (?:in|at)"
               r"(?: the (?:town|city) of)? " + PLACE),
    re.compile(r"\bheadquartered (?:in|at)(?: the (?:town|city) of)? " + PLACE),
    re.compile(r"\bchef-lieu (?:est|:) " + PLACE),
)
# A place said to be the seat: "Kuntaur is the seat of the Kuntaur Local
# Government Area".
IS_SEAT = re.compile(PLACE + r" (?:is|was) the (?:administrative )?(?:seat|headquarters?|capital)"
                     r" of (?:the )?(?P<of>[^.]{0,80})")


def batches(items: list[str], n: int = BATCH) -> list[list[str]]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def wikidata_items(qids: list[str], sites: tuple[str, ...] = ("enwiki",)) -> dict[str, dict[str, Any]]:
    """{qid: {"sitelinks": {site: title}, "P36": [qid, ...]}} for the items named."""
    out: dict[str, dict[str, Any]] = {}
    for chunk in batches(sorted(set(q for q in qids if q))):
        q = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(chunk),
                                    "props": "sitelinks|claims", "sitefilter": "|".join(sites),
                                    "format": "json"})
        data = http_json(f"{WD_API}?{q}", timeout=120)
        for qid, ent in (data.get("entities") or {}).items():
            claims = ent.get("claims") or {}
            seats = [c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                     for c in claims.get("P36", [])]
            out[qid] = {"sitelinks": {s: v.get("title") for s, v in
                                      (ent.get("sitelinks") or {}).items()},
                        "P36": [s for s in seats if s]}
    return out


def articles(titles: list[str], lang: str = "en") -> dict[str, dict[str, Any]]:
    """{title asked for: {"title", "revid", "timestamp", "text"}}, redirects followed."""
    out: dict[str, dict[str, Any]] = {}
    for chunk in batches(sorted(set(t for t in titles if t))):
        q = urllib.parse.urlencode({"action": "query", "prop": "revisions",
                                    "rvprop": "ids|timestamp|content", "rvslots": "main",
                                    "titles": "|".join(chunk), "redirects": "1",
                                    "format": "json", "formatversion": "2"})
        data = http_json(f"{WP_API.format(lang=lang)}?{q}", timeout=120).get("query") or {}
        moved: dict[str, str] = {}
        for kind in ("normalized", "redirects"):
            for m in data.get(kind) or []:
                moved[m["from"]] = m["to"]
        found = {}
        for page in data.get("pages") or []:
            revs = page.get("revisions") or []
            if page.get("missing") or not revs:
                continue
            rev = revs[0]
            text = (rev.get("slots") or {}).get("main", {}).get("content") or rev.get("content")
            found[page["title"]] = {"title": page["title"], "revid": rev.get("revid"),
                                    "timestamp": rev.get("timestamp"), "text": text or ""}
        for t in chunk:
            final = t
            for _ in range(3):
                final = moved.get(final, final)
            if final in found:
                out[t] = found[final]
    return out


def permalink(lang: str, title: str, revid: int) -> str:
    return (f"https://{lang}.wikipedia.org/w/index.php?"
            + urllib.parse.urlencode({"title": title.replace(" ", "_"), "oldid": revid}))


def revision_year(timestamp: str | None) -> int | None:
    try:
        return datetime.strptime(str(timestamp)[:10], "%Y-%m-%d").year
    except ValueError:
        return None


def infobox(text: str) -> dict[str, str]:
    """The first infobox's parameters, lower-cased, values as written."""
    start = re.search(r"\{\{\s*(?:Infobox|Info/|Infobox settlement)", text, re.I)
    if not start:
        return {}
    depth, i, body = 0, start.start(), None
    while i < len(text) - 1:
        two = text[i:i + 2]
        if two == "{{":
            depth += 1
            i += 2
            continue
        if two == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                body = text[start.start() + 2:i - 2]
                break
            continue
        i += 1
    if body is None:
        return {}
    parts, depth, cur = [], 0, []
    j = 0
    while j < len(body):
        two = body[j:j + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            j += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            j += 2
            continue
        if body[j] == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
            j += 1
            continue
        cur.append(body[j])
        j += 1
    parts.append("".join(cur))
    out = {}
    for part in parts[1:]:
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip().lower()] = v.strip()
    return out


def clean(value: str) -> str:
    """A seat as a reader reads it: markup out, a trailing state or country cut."""
    text = re.sub(r"<!--.*?-->", "", value or "", flags=re.S)
    text = plain(text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:")
    text = re.sub(r",\s*(?:[A-Z][\w ]* State|Nigeria|The Gambia|Gambia|Liberia)$", "", text)
    return text.strip(" ,.;:")


def lead(text: str) -> str:
    """The article's text before its first section heading, infobox and references out."""
    body = re.split(r"^==", text, maxsplit=1, flags=re.M)[0]
    body = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", body, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    # Templates out, innermost first (the infobox among them).
    for _ in range(6):
        body = re.sub(r"\{\{[^{}]*\}\}", "", body)
    return " ".join(body.split())


def seats(text: str) -> dict[str, str]:
    """{"infobox": seat, "lead": seat} for each place that names one."""
    found: dict[str, str] = {}
    box = infobox(text)
    for key in SEAT_PARAMS:
        if box.get(key) and clean(box[key]):
            label = box.get(f"{key}_type") or box.get("seat_type") or ""
            if key == "seat" and label and not any(w in label.lower() for w in SEAT_LABELS):
                continue
            found["infobox"] = clean(box[key])
            break
    words = lead(text)
    for pattern in SENTENCES:
        m = pattern.search(words)
        if m:
            found["lead"] = clean(m.group("x"))
            break
    else:
        m = IS_SEAT.search(words)
        if m:
            found["is_seat"] = f"{clean(m.group('x'))} (of {clean(m.group('of'))})"
    return found


def sentences_naming(text: str, words: tuple[str, ...] = ("headquarter", "seat", "capital",
                                                           "chef-lieu", "secretariat")) -> list[str]:
    """The lead's sentences that name any of the words, for the dump."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", lead(text)):
        if any(w in s.lower() for w in words):
            out.append(s[:240])
    return out


def same_place(a: str, b: str) -> bool:
    fold = lambda s: re.sub(r"[^a-z]", "", s.lower())  # noqa: E731
    return fold(a) == fold(b) or fold(a) in fold(b) or fold(b) in fold(a)


def unseated(iso3: str, level: str = "admin2") -> list[dict[str, Any]]:
    """The polygons of a country and level that show no capital on the map."""
    parents = {r["id"]: r["name"] for r in json.loads((SITE / "admin1" / f"{iso3}.units.json")
                                                       .read_text())}
    rows = json.loads((SITE / level / f"{iso3}.units.json").read_text())
    out = []
    for r in rows:
        if isinstance(r.get("capital"), str) and r["capital"].strip():
            continue
        out.append({"id": r["id"], "name": r["name"], "wikidata": r.get("wikidata"),
                    "parent": parents.get(r.get("parent"), r.get("parent")) if level == "admin2"
                    else iso3})
    return out


def dump(iso3: str) -> None:
    levels = ("admin1", "admin2") if iso3 == "GMB" else ("admin2",)
    for level in levels:
        polys = unseated(iso3, level)
        items = wikidata_items([p["wikidata"] for p in polys], ("enwiki", "frwiki"))
        titles: dict[str, list[str]] = {"en": [], "fr": []}
        for p in polys:
            links = items.get(p["wikidata"] or "", {}).get("sitelinks", {})
            named = TITLES.get((p["parent"], p["name"])) or DUMP_TITLES.get((iso3, p["name"]))
            p["en"] = ([named] if isinstance(named, str) else list(named or [])) or \
                [links.get("enwiki")]
            p["fr"] = [links.get("frwiki")]
            titles["en"].extend(t for t in p["en"] if t)
            titles["fr"].extend(t for t in p["fr"] if t)
        got = {lang: articles(t, lang) for lang, t in titles.items()}
        log(f"=== {iso3} {level}: {len(polys)} polygons without a capital")
        for p in polys:
            log(f"--- {p['parent']} / {p['name']} [{p['wikidata']}] P36="
                f"{items.get(p['wikidata'] or '', {}).get('P36')}")
            for lang in ("en", "fr"):
                for title in p[lang]:
                    a = got[lang].get(title or "")
                    if not a:
                        log(f"    {lang}: {title!r} -- no article")
                        continue
                    log(f"    {lang}: {a['title']!r} rev {a['revid']} {a['timestamp']}: "
                        f"{seats(a['text'])}")
                    box = infobox(a["text"])
                    for k in ("settlement_type", "seat_type", "seat", "headquarters", "capital",
                              "chef-lieu"):
                        if box.get(k):
                            log(f"      infobox {k} = {box[k][:120]!r}")
                    for s in sentences_naming(a["text"]):
                        log(f"      lead: {s}")


def bind(polys: list[dict[str, Any]], items: dict[str, dict[str, Any]],
         got: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """One record per polygon read: its seat, or why there is none."""
    records, said = [], []
    for p in polys:
        if (p["parent"], p["name"]) in NOT_READ:
            continue
        title = TITLES.get((p["parent"], p["name"])) or items.get(
            p["wikidata"] or "", {}).get("sitelinks", {}).get("enwiki")
        a = got.get(title or "")
        if a is None:
            said.append(f"{p['parent']}/{p['name']}: no English article ({title!r})")
            continue
        cite = [{"field": "capital", "name": f"English Wikipedia, {a['title']}",
                 "url": permalink("en", a["title"], a["revid"]),
                 "year": revision_year(a["timestamp"]), "license": LICENCE}]
        found = {k: v for k, v in seats(a["text"]).items() if k in ("infobox", "lead")}
        values = list(found.values())
        if values and all(same_place(values[0], v) for v in values[1:]):
            seat = found.get("infobox") or found["lead"]
            records.append(record(
                f"NGA-SEAT-{p['id']}", p["name"], level="admin2", parent="NGA", country="NGA",
                match_by="shape_id", shape_id=p["id"], capital=seat, sources=cite))
            said.append(f"{p['parent']}/{p['name']}: {seat} ({', '.join(found)}; {a['title']} "
                        f"rev {a['revid']})")
            continue
        if values:
            why = (f"English Wikipedia's article on {a['title']} names two different "
                   f"headquarters ({found['infobox']} in its infobox, {found['lead']} in its "
                   "text), so neither is shown.")
        else:
            why = (f"English Wikipedia's article on {a['title']} names no headquarters, and "
                   "the 2006 census's tables name none.")
        records.append(record(
            f"NGA-SEAT-{p['id']}", p["name"], level="admin2", parent="NGA", country="NGA",
            match_by="shape_id", shape_id=p["id"], capital=gap(NOT_AVAILABLE, why),
            sources=cite))
        said.append(f"{p['parent']}/{p['name']}: none -- {why}")
    return records, said


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", nargs="*", metavar="ISO3",
                    help="print what each article says for these countries, and stop")
    args = ap.parse_args()
    if args.dump is not None:
        for iso3 in args.dump or ["NGA"]:
            dump(iso3.upper())
        return 0
    polys = unseated("NGA")
    items = wikidata_items([p["wikidata"] for p in polys])
    titles = [TITLES.get((p["parent"], p["name"])) or items.get(p["wikidata"] or "", {})
              .get("sitelinks", {}).get("enwiki") for p in polys]
    got = articles([t for t in titles if t])
    records, said = bind(polys, items, got)
    for line in said:
        log(f"  {line}")
    seated = sum(1 for r in records if isinstance(r["capital"], str))
    log(f"nigeria_capitals: {len(polys)} polygons without a seat on the map; {seated} seats "
        f"written, {len(records) - seated} reasons")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
