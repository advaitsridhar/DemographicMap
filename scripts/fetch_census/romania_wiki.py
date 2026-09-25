#!/usr/bin/env python3
"""Romania: ethnicity and religion for every commune, town and city (2021 census).

The 2021 census counted ethnicity and religion for every one of Romania's
3,181 communes and the towns and cities besides, and the National Institute
of Statistics published both tables by UAT ("Populatia rezidenta dupa etnie /
dupa religie ... Judete, Municipii, orase si comune", June 2023). Its hosts
refuse a GitHub runner (see ``romania.py``), and the tables are not in the
Internet Archive as files. Romanian Wikipedia's article on each commune
carries both compositions as pie charts -- "Componenta etnica a comunei X",
"Componenta confesionala a comunei X" -- cited to those two INS tables, with
the unknown share as a slice of its own.

This reads the charts, and only as a transcription of the census:

* a unit is found through its Wikidata item's Romanian article, never by
  searching for a name, so Corcova is Comuna Corcova, Mehedinti;
* a chart is taken as the 2021 count only if its largest share is also
  printed in the article's "Conform recensamantului efectuat in 2021"
  sentence -- an article still charting 2011 is left out;
* shares must sum to within half a point of 100;
* every label is translated to the names the county adapter uses; a label
  with no translation leaves that unit's field out and is logged, so a
  Romanian word never reaches an English chart.

Usage:
    python -m scripts.fetch_census.romania_wiki          # runner
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import NOT_AVAILABLE, PROCESSED, gap, http_json, log, read_json, write_json  # noqa: E402
from fetch_census._shared import record  # noqa: E402
from fetch_census.europe_wiki import plain, template_params  # noqa: E402

YEAR = 2021
SITE = PROCESSED.parent.parent / "site" / "data" / "admin2" / "ROU.json"
WIKIDATA = "https://www.wikidata.org/w/api.php"
ROWIKI = "https://ro.wikipedia.org/w/api.php"
SOURCE = ("Institutul National de Statistica, Recensamantul Populatiei si Locuintelor "
          "2021, populatia rezidenta dupa etnie / dupa religie (UAT), as transcribed "
          "by Romanian Wikipedia")

ETHNICITY = {
    "Români": "Romanians", "Maghiari": "Hungarians", "Romi": "Romani",
    "Ucraineni": "Ukrainians", "Germani": "Germans", "Turci": "Turks",
    "Ruși lipoveni": "Russians", "Ruși": "Russians", "Lipoveni": "Russians",
    "Tătari": "Tatars", "Sârbi": "Serbs", "Slovaci": "Slovaks", "Bulgari": "Bulgarians",
    "Croați": "Croats", "Greci": "Greeks", "Evrei": "Jewish", "Cehi": "Czechs",
    "Polonezi": "Polish", "Italieni": "Italians", "Armeni": "Armenians",
    "Chinezi": "Chinese", "Macedoneni": "Macedonians", "Albanezi": "Albanians",
    "Ceangăi": "Csángós", "Alte etnii": "Other ethnic group", "Altă etnie": "Other ethnic group",
    "Necunoscută": "Not stated", "Necunoscut": "Not stated",
}
RELIGION = {
    "Ortodocși": "Orthodox Christianity", "Romano-catolici": "Roman Catholic",
    "Reformați": "Reformed", "Penticostali": "Pentecostalism",
    "Greco-catolici": "Greek Catholic", "Baptiști": "Baptist",
    "Adventiști de ziua a șaptea": "Seventh-day Adventist", "Adventiști": "Seventh-day Adventist",
    "Musulmani": "Islam", "Unitarieni": "Unitarian", "Martorii lui Iehova": "Jehovah's Witnesses",
    "Creștini după Evanghelie": "Evangelicalism", "Evanghelici": "Evangelicalism",
    "Creștini de rit vechi": "Old Believers", "Evanghelici luterani": "Lutheranism",
    "Luterani": "Lutheranism", "Evanghelici de confesiune augustană": "Lutheranism",
    "Ortodocși sârbi": "Serbian Orthodox", "Mozaici": "Judaism",
    "Armeni apostolici": "Armenian Apostolic", "Alte religii": "Other religion",
    "Altă religie": "Other religion", "Fără religie": "No religion", "Atei": "Atheism",
    "Necunoscută": "Not stated", "Necunoscut": "Not stated",
}
CHARTS = {"ethnicity": (re.compile(r"componen\w+ etnic", re.I), ETHNICITY),
          "religion": (re.compile(r"componen\w+ confesional", re.I), RELIGION)}
CENSUS_SENTENCE = re.compile(r"recensământului efectuat în 2021.{0,1500}", re.S)


def api_get(url: str, params: dict[str, str]) -> dict[str, Any]:
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    for wait in (2, 5, 15, None):
        try:
            return http_json(f"{url}?{q}", timeout=90, cache=False)
        except RuntimeError as exc:
            if wait is None:
                raise
            log(f"  {exc}; waiting {wait}s")
            time.sleep(wait)
    return {}


def titles_for(qids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(qids), 50):
        data = api_get(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                                  "props": "sitelinks", "sitefilter": "rowiki"})
        for qid, entity in (data.get("entities") or {}).items():
            link = ((entity.get("sitelinks") or {}).get("rowiki") or {}).get("title")
            if link:
                out[qid] = link
        time.sleep(0.5)
    return out


def wikitexts(titles: list[str]) -> dict[str, str]:
    """title asked for -> the article's wikitext, following redirects."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        data = api_get(ROWIKI, {"action": "query", "prop": "revisions", "rvprop": "content",
                                "rvslots": "main", "redirects": "1", "titles": "|".join(batch)})
        query = data.get("query") or {}
        moved = {r["from"]: r["to"] for r in query.get("redirects") or []}
        moved.update({n["from"]: n["to"] for n in query.get("normalized") or []})
        text = {p["title"]: ((p.get("revisions") or [{}])[0].get("slots") or {}).get("main", {}).get("content", "")
                for p in query.get("pages") or []}
        for title in batch:
            final = moved.get(moved.get(title, title), moved.get(title, title))
            if text.get(final):
                out[title] = text[final]
        time.sleep(0.5)
    return out


def number(text: str) -> float | None:
    text = plain(text).replace("%", "").strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def chart(wikitext: str, field: str) -> tuple[list[tuple[str, float]], str | None]:
    """(label, share) slices of the one chart of this field, or why not."""
    wanted, _ = CHARTS[field]
    found = []
    for params in template_params(wikitext, "Pie chart"):
        if not wanted.search(plain(params.get("caption", ""))):
            continue
        rows, k = [], 1
        while f"label{k}" in params:
            value = number(params.get(f"value{k}", ""))
            if value is None:
                return [], f"slice {k} has no number"
            rows.append((plain(params[f"label{k}"]).strip(), value))
            k += 1
        found.append(rows)
    if len(found) != 1:
        return [], f"{len(found)} charts"
    return found[0], None


def is_2021(wikitext: str, rows: list[tuple[str, float]]) -> bool:
    top = max(rows, key=lambda r: r[1])[1]
    printed = f"{top:.2f}".replace(".", ",")
    return any(printed in m.group(0) for m in CENSUS_SENTENCE.finditer(wikitext))


def composition(field: str, rows: list[tuple[str, float]], unknown: dict[str, int]
                ) -> list[dict[str, Any]] | None:
    _, names = CHARTS[field]
    shares: dict[str, float] = {}
    for label, value in rows:
        english = names.get(" ".join(label.split()))
        if english is None:
            unknown[f"{field}: {label}"] = unknown.get(f"{field}: {label}", 0) + 1
            return None
        shares[english] = round(shares.get(english, 0.0) + value, 2)
    if abs(sum(shares.values()) - 100) > 0.5:
        return None
    return [{"group": g, "pct": p} for g, p in sorted(shares.items(), key=lambda kv: -kv[1])]


def main() -> int:
    units = [r for r in read_json(SITE, []) if r.get("level") == "admin2" and r.get("wikidata")]
    log(f"{len(units)} Romanian units with a Wikidata item")
    titles = titles_for(sorted({u["wikidata"] for u in units}))
    log(f"{len(titles)} with a Romanian article")
    texts = wikitexts(sorted(set(titles.values())))
    log(f"{len(texts)} articles read")
    records, why, unknown = [], {}, {}
    for unit in units:
        title = titles.get(unit["wikidata"])
        text = texts.get(title or "")
        if not text:
            why["no article"] = why.get("no article", 0) + 1
            continue
        fields: dict[str, Any] = {}
        for field in CHARTS:
            rows, reason = chart(text, field)
            if not rows:
                why[f"{field}: {reason}"] = why.get(f"{field}: {reason}", 0) + 1
                continue
            if not is_2021(text, rows):
                why[f"{field}: not the 2021 count"] = why.get(f"{field}: not the 2021 count", 0) + 1
                continue
            shares = composition(field, rows, unknown)
            if shares:
                fields[field] = shares
                fields[f"{field}_year"] = YEAR
        if not fields:
            continue
        records.append(record(
            f"ROU-WP-{unit['wikidata']}", unit["name"], level="admin2", parent="ROU",
            country="ROU", match_by="shape_id", shape_id=unit["id"],
            wikidata=unit["wikidata"],
            religion=fields.get("religion", gap(NOT_AVAILABLE)),
            religion_year=fields.get("religion_year"),
            ethnicity=fields.get("ethnicity", gap(NOT_AVAILABLE)),
            ethnicity_year=fields.get("ethnicity_year"),
            sources=[{"field": "ethnicity/religion", "name": SOURCE,
                      "url": f"https://ro.wikipedia.org/wiki/{urllib.parse.quote(title)}",
                      "license": "CC BY-SA 4.0 (transcription); INS figures"}],
        ))
    log(f"{len(records)} units with a 2021 composition; left out: {why}")
    if unknown:
        log(f"labels with no translation: {sorted(unknown.items(), key=lambda kv: -kv[1])}")
    write_json(PROCESSED / "romania_uat.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
