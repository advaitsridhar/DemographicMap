#!/usr/bin/env python3
"""Nigeria -- local government area headquarters, from English Wikipedia's article on each area.

The 2006 census's priority tables (nigeria_census) name no headquarters, and
Wikidata names a seat (its property P36) for 707 of the 774 local government
areas the map draws. For the other 67 the seat is read from English
Wikipedia's article on the area: the infobox's seat ("seat_type =
Headquarters", "seat = [[Asaba]]"), or a sentence naming it -- "Its
headquarters are in the town of Iragbiji" in the article's opening, "The
capital of the LGA is Gembu", "Otu Jeremi is the headquarters of Ughelli
South LGA", or a town's article that calls the town "the headquarters of the
Idanre Local Government Area". A sentence in the body of the article counts
only where it names the area or its local government; "Its headquarters"
counts only in the opening, where "its" is the area. Each article is found
through the area's own Wikidata item (its English sitelink), or, where the
polygon carries no item, by the title in ``TITLES``; each record cites the
revision read, by its permanent address and year.

A seat is written only where every place the article names it agrees. An
area whose article names none, or two different ones, or that has no
article, gets that reason. Bakassi's polygon is left out: it is the part of
the 2006 area left on the Nigerian side after 2008 (nigeria_census), and an
article's headquarters would be the area's as it was.

The helpers here also serve gambia_capitals and liberia_capitals.

Usage:
    python -m scripts.fetch_census.nigeria_capitals
    python -m scripts.fetch_census.nigeria_capitals --dump NGA GMB LBR   # what each article says
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from datetime import datetime
from typing import Any, Callable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_json, log, record, write_json

WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://{lang}.wikipedia.org/w/api.php"
LICENCE = "CC BY-SA 4.0"
OUT = "nigeria_capitals.json"
SITE = PROCESSED.parent.parent / "site" / "data"
BATCH = 50
VOL4 = "https://datacatalog.ihsn.org/catalog/3340/download/48522"
CENSUS = ("National Population Commission, 2006 Population and Housing Census, Priority "
          "Table Volume IV, Population Distribution by Age and Sex (State and Local "
          "Government Area)")

# Polygons that carry no Wikidata item, or whose item has no English article:
# (state, polygon) -> the English article on the area.
TITLES: dict[tuple[str, str], str] = {
    ("Osun", "Ilesha East"): "Ilesa East",
    ("Abia", "Obi Nwga"): "Obingwa",
    ("Benue", "Oturkpo"): "Otukpo",
}
# Polygons not read: the ground is not the article's area.
NOT_READ = {("Cross River", "Bakassi")}

# Infobox parameters that name a seat, and the labels a seat_type may carry.
SEAT_PARAMS = ("seat", "headquarters", "hq", "capital", "admin_center")
SEAT_LABELS = ("headquarter", "seat", "capital", "admin", "secretariat")

# A place's name: capitalised words, joined by spaces, hyphens or a slash
# ("Oke-Ila Orangun", "Uromi/Uzea", "Unguwa Uku").
PLACE = r"(?P<x>[A-Z][\w'’\-]*(?:[ /\-][A-Z][\w'’\-]*){0,3})"
KEY = r"(?i:headquarters?|secretariat|seat)"
# In the opening, where "its" is the area.
OPENING = (
    re.compile(r"\b(?i:its|the)(?: [\w' ]{0,40}?)? (?i:administrative |local government "
               r"|council )?" + KEY + r"(?: of (?P<of>[^.,;]{0,60}?))? (?i:is|are|was|were|lies"
               r"|lie)(?: (?i:located|situated|sited|based))? (?i:in|at)(?: (?i:the))?"
               r"(?: (?i:ancient |old |historic |state )?(?i:town|city|village|community|suburb"
               r"|locality|area|capital|quarter))?(?: (?i:of))? " + PLACE),
    re.compile(r"\b(?i:with|has|having) (?:(?i:its) )?(?:[\w ]{0,30} )?" + KEY
               + r" (?i:in|at)(?: (?i:the) (?i:town|city) (?i:of))? " + PLACE),
    re.compile(r"\b(?i:headquartered) (?i:in|at) " + PLACE),
    re.compile(r"\b(?i:capital of which is) " + PLACE),
    re.compile(PLACE + r" is the (?i:district )?capital(?=,| and|\.)"),
    # A street address: "Its headquarters are Nnobi Street, Uwani, Enugu".
    re.compile(r"\b(?i:its|the) (?i:headquarters) (?i:is|are) (?:(?i:at|on) )?[A-Z][\w ]*"
               r"(?i:street|road|avenue|close|way)[^.]*?, " + PLACE),
)
# Anywhere in the article, naming the unit.
NAMED = (
    re.compile(r"\b(?i:the )?(?i:capital|seat|headquarters?|administrative seat) of the "
               r"(?P<of>(?i:LGA|local government area|local government|district)) "
               r"(?i:is|are) " + PLACE),
    re.compile(PLACE + r" is (?:also )?the (?i:administrative )?(?i:headquarters|seat) of "
               r"(?:the )?(?P<of>[^.]*?(?i:LGA|local government area|local government|district))"),
)
# The article's own place said to be the seat: "The town is the seat of the
# Kuntaur Local Government Area", "Idanre ... is a historic town ..., and the
# headquarters of the Idanre Local Government Area".
SUBJECT = re.compile(r"\b(?:is|and) (?:also )?the (?i:administrative )?(?i:seat|headquarters) "
                     r"of (?:the )?(?P<of>[^.]*?(?i:local government area|local government|LGA"
                     r"|district))")


def fold(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s or "").lower())


def batches(items: list[str], n: int = BATCH) -> list[list[str]]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def wikidata_items(qids: list[str], sites: tuple[str, ...] = ("enwiki",)) -> dict[str, dict[str, Any]]:
    """{qid: {"sitelinks": {site: title}, "P36": [qid, ...]}} for the items named."""
    out: dict[str, dict[str, Any]] = {}
    for chunk in batches(sorted({q for q in qids if q})):
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
    for chunk in batches(sorted({t for t in titles if t})):
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
                                    "timestamp": rev.get("timestamp"), "text": text or "",
                                    "asked": None}
        for t in chunk:
            final = t
            for _ in range(3):
                final = moved.get(final, final)
            if final in found:
                out[t] = dict(found[final], asked=t, redirected=final != t)
    return out


def search(query: str, lang: str = "en", hits: int = 3) -> list[str]:
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query,
                                "srlimit": hits, "format": "json", "formatversion": "2"})
    data = http_json(f"{WP_API.format(lang=lang)}?{q}", timeout=60)
    return [h["title"] for h in (data.get("query") or {}).get("search") or []]


def permalink(lang: str, title: str, revid: int) -> str:
    return (f"https://{lang}.wikipedia.org/w/index.php?"
            + urllib.parse.urlencode({"title": title.replace(" ", "_"), "oldid": revid}))


def revision_year(timestamp: str | None) -> int | None:
    try:
        return datetime.strptime(str(timestamp)[:10], "%Y-%m-%d").year
    except ValueError:
        return None


def cite(article: dict[str, Any], field: str = "capital", lang: str = "en") -> dict[str, Any]:
    """The revision read, as a source: its title, permanent address and year."""
    edition = {"en": "English", "fr": "French"}[lang]
    return {"field": field, "name": f"{edition} Wikipedia, {article['title']}",
            "url": permalink(lang, article["title"], article["revid"]),
            "year": revision_year(article["timestamp"]), "license": LICENCE}


def infobox(text: str) -> dict[str, str]:
    """The first infobox's parameters, lower-cased, values as written."""
    start = re.search(r"\{\{\s*Infobox", text, re.I)
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
    parts, depth, cur, j = [], 0, [], 0
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


def flat(text: str) -> str:
    """Wikitext as a reader reads it: comments, references, files, tables and
    templates out, links as their words, bold and italics plain."""
    t = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", t, flags=re.S | re.I)
    t = re.sub(r"\[\[(?:File|Image|Fichier|Category|Catégorie):(?:[^\[\]]|\[\[[^\]]*\]\])*\]\]",
               "", t, flags=re.I)
    for _ in range(8):
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\{\|.*?\|\}", "", t, flags=re.S)
    t = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]+)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return t


def parts(text: str) -> tuple[str, str]:
    """(the opening, the rest) of an article, flattened, one line each."""
    body = flat(text)
    m = re.search(r"(?m)^=", body)
    head, rest = (body[:m.start()], body[m.start():]) if m else (body, "")
    rest = re.sub(r"(?m)^=+[^=\n]*=+\s*$", " ", rest)
    return " ".join(head.split()), " ".join(rest.split())


def clean(value: str) -> str:
    """A seat as a reader reads it: markup out, a trailing state or country cut."""
    text = " ".join(flat(value).split()).strip(" ,.;:")
    text = re.sub(r",\s*(?:[A-Z][\w ]* State|Nigeria|The Gambia|Gambia|Liberia)$", "", text)
    text = re.sub(r"\s*\([^)]*\)$", "", text)
    return text.strip(" ,.;:")


def title_base(title: str) -> str:
    """An article's place without its disambiguation: "Dala, Nigeria" -> "Dala"."""
    return re.split(r",| \(", title, maxsplit=1)[0].strip()


def names_unit(of: str, names: list[str]) -> bool:
    """Whether a clause ("the Idanre Local Government Area", "the LGA") is the unit's."""
    f = fold(of)
    return f in ("lga", "localgovernmentarea", "localgovernment", "district", "thelga",
                 "thedistrict") or any(fold(n) and fold(n) in f for n in names)


def seats(text: str, title: str, names: list[str]) -> dict[str, str]:
    """{how: the seat it names} for each way the article names one: "infobox",
    "opening", "named" (a sentence anywhere that names the unit) and "subject"
    (the article's own place said to be the unit's seat)."""
    found: dict[str, str] = {}
    box = infobox(text)
    for key in SEAT_PARAMS:
        if box.get(key) and clean(box[key]):
            label = box.get(f"{key}_type") or (box.get("seat_type") if key == "seat" else "")
            if label and not any(w in label.lower() for w in SEAT_LABELS):
                continue
            found["infobox"] = clean(box[key])
            break
    opening, rest = parts(text)
    for pattern in OPENING:
        m = pattern.search(opening)
        if m and (not m.groupdict().get("of") or names_unit(m.group("of"), names + [title])):
            found["opening"] = clean(m.group("x"))
            break
    for pattern in NAMED:
        for words in (opening, rest):
            m = pattern.search(words)
            if m and names_unit(m.group("of"), names + [title_base(title)]):
                found.setdefault("named", clean(m.group("x")))
    for words in (opening, rest):
        for m in SUBJECT.finditer(words):
            stop = words.rfind(". ", 0, m.start())
            subject = words[0 if stop < 0 else stop + 2:m.start()]
            if re.match(rf"(?:The town|It|{re.escape(title_base(title))})\b", subject) and \
                    names_unit(m.group("of"), names + [title_base(title)]):
                found.setdefault("subject", title_base(title))
    return found


def same_place(a: str, b: str) -> bool:
    return fold(a) == fold(b) or fold(a) in fold(b) or fold(b) in fold(a)


def choose(found: dict[str, str]) -> str | None:
    """The seat where every way the article names one agrees, else None."""
    values = list(found.values())
    if not values or not all(same_place(values[0], v) for v in values[1:]):
        return None
    for how in ("infobox", "opening", "named", "subject"):
        if how in found:
            return found[how]
    return None


def sentences_naming(text: str) -> list[str]:
    """The article's sentences that name a seat word, for the dump."""
    opening, rest = parts(text)
    out = []
    for s in re.split(r"(?<=[.!?])\s+", f"{opening} {rest}"):
        if re.search(r"headquarter|secretariat|\bseat\b|capital|chef-lieu", s, re.I):
            out.append(s[:260])
    return out[:8]


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
                    "level": level,
                    "parent": parents.get(r.get("parent"), r.get("parent")) if level == "admin2"
                    else iso3})
    return out


def read_units(polys: list[dict[str, Any]], titles: dict[tuple[str, str], str]
               ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """({qid: item}, {polygon id: article}) for the polygons given."""
    items = wikidata_items([p["wikidata"] for p in polys])
    want = {}
    for p in polys:
        want[p["id"]] = titles.get((p["parent"], p["name"])) or items.get(
            p["wikidata"] or "", {}).get("sitelinks", {}).get("enwiki")
    got = articles([t for t in want.values() if t])
    return items, {pid: got[t] for pid, t in want.items() if t and t in got}


def bind(iso3: str, polys: list[dict[str, Any]], items: dict[str, dict[str, Any]],
         got: dict[str, dict[str, Any]], why: Callable[[dict[str, Any], dict[str, Any] | None,
                                                         bool], tuple[str, list[dict]]]
         ) -> tuple[list[dict[str, Any]], list[str]]:
    """One record per polygon: its seat, or ``why`` there is none."""
    records, said = [], []
    for p in polys:
        a = got.get(p["id"])
        quiet = not items.get(p["wikidata"] or "", {}).get("P36")
        rid = f"{iso3}-SEAT-{p['id']}"
        where = dict(level=p["level"], parent=iso3, country=iso3, match_by="shape_id",
                     shape_id=p["id"])
        if a is not None:
            found = seats(a["text"], a["title"], [p["name"]])
            seat = choose(found)
            if seat:
                records.append(record(rid, p["name"], capital=seat, sources=[cite(a)], **where))
                said.append(f"{p['parent']} / {p['name']}: {seat} ({found}; {a['title']!r} "
                            f"rev {a['revid']})")
                continue
            if found:
                reason = (f"English Wikipedia's article on {a['title']} names two different "
                          f"seats ({' and '.join(sorted(set(found.values())))}), so neither is "
                          "shown.")
                records.append(record(rid, p["name"], capital=gap(NOT_AVAILABLE, reason),
                                      sources=[cite(a)], **where))
                said.append(f"{p['parent']} / {p['name']}: two seats {found} ({a['title']!r})")
                continue
        reason, sources = why(p, a, quiet)
        records.append(record(rid, p["name"], capital=gap(NOT_AVAILABLE, reason),
                              sources=sources, **where))
        said.append(f"{p['parent']} / {p['name']}: none -- {reason}")
    return records, said


def nigeria_why(p: dict[str, Any], a: dict[str, Any] | None, quiet: bool
                ) -> tuple[str, list[dict[str, Any]]]:
    census = {"field": "capital", "name": CENSUS, "url": VOL4,
              "license": "National Population Commission publication (reuse with attribution)",
              "year": 2006}
    also = ", Wikidata names none," if quiet else ""
    if a is not None:
        return (f"English Wikipedia's article on {a['title']} names no headquarters for the "
                f"local government area{also} and the 2006 census's tables name none.",
                [cite(a), census])
    return (f"English Wikipedia has no article on this local government area{also} and the "
            "2006 census's tables name no headquarters.", [census])


def dump(iso3: str) -> None:
    levels = ("admin1", "admin2") if iso3 == "GMB" else ("admin2",)
    word = {"NGA": "local government area {parent} State Nigeria",
            "GMB": "district {parent} Gambia", "LBR": "district {parent} County Liberia"}[iso3]
    for level in levels:
        polys = unseated(iso3, level)
        items = wikidata_items([p["wikidata"] for p in polys], ("enwiki", "frwiki"))
        en, fr = {}, {}
        for p in polys:
            links = items.get(p["wikidata"] or "", {}).get("sitelinks", {})
            en[p["id"]] = [t for t in [TITLES.get((p["parent"], p["name"])),
                                       links.get("enwiki")] if t]
            fr[p["id"]] = [t for t in [links.get("frwiki")] if t]
            if not en[p["id"]]:
                q = f"{p['name']} " + (word.format(parent=p["parent"]) if level == "admin2"
                                       else "Local Government Area Gambia")
                en[p["id"]] = search(q)
        got_en = articles([t for ts in en.values() for t in ts])
        got_fr = articles([t for ts in fr.values() for t in ts], "fr")
        log(f"=== {iso3} {level}: {len(polys)} polygons without a capital")
        for p in polys:
            log(f"--- {p['parent']} / {p['name']} [{p['wikidata']}] P36="
                f"{items.get(p['wikidata'] or '', {}).get('P36')}")
            for lang, titles, got in (("en", en, got_en), ("fr", fr, got_fr)):
                for title in titles[p["id"]]:
                    a = got.get(title)
                    if not a:
                        log(f"    {lang}: {title!r} -- no article")
                        continue
                    found = seats(a["text"], a["title"], [p["name"]]) if lang == "en" else {}
                    log(f"    {lang}: {a['title']!r} rev {a['revid']} {a['timestamp']}: {found}"
                        f" -> {choose(found)!r}")
                    for s in sentences_naming(a["text"]):
                        log(f"      says: {s}")


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
    polys = [p for p in unseated("NGA") if (p["parent"], p["name"]) not in NOT_READ]
    items, got = read_units(polys, TITLES)
    records, said = bind("NGA", polys, items, got, nigeria_why)
    for line in said:
        log(f"  {line}")
    seated = sum(1 for r in records if isinstance(r["capital"], str))
    log(f"nigeria_capitals: {len(polys)} polygons without a seat on the map; {seated} seats "
        f"written, {len(records) - seated} reasons")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
