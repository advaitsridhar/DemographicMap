#!/usr/bin/env python3
"""What Japan's e-Stat catalogue holds for this map, asked rather than assumed.

Japan is declared three times over in ``NOT_COLLECTED_POLICY`` -- religion,
ethnicity and language -- and every one of those declarations rested on reading
the Kokusei Chosa questionnaire. That is a good reason and it is not evidence
about the catalogue: e-Stat is the portal for *every* Japanese government
statistic, not only the census, and a question the census declines can still be
asked by an agency survey. ``docs/SOURCES.md`` said as much and left it open --
"e-Stat itself is open and answers a program". This is the program.

It is read-only. It searches the catalogue for the words a composition would be
titled with, in Japanese first because that is the language the catalogue is
indexed in, and reports for every hit the one thing that decides whether the
map can use it: the geography it is cut by. A table that exists only for Japan
as a whole cannot fill 47 prefectures, and is reported as such rather than
counted as a find.

Three endpoints, all of e-Stat's REST API 3.0:

* ``getStatsList`` -- the catalogue. With ``statsNameList=Y`` it answers with
  the *surveys* that match rather than their tables, which is the only sane
  first pass for a word like 国勢調査 that matches thousands of tables.
* ``getMetaInfo`` -- one table's dimensions: which class objects it is cut by,
  and the codes inside each. This is where "by prefecture" is confirmed or
  denied, and it is also where a category list either partitions a population
  or does not.
* ``getStatsData`` -- the figures, with ``--group`` to sum them by any
  dimension. Summing is the point: the Agency for Cultural Affairs' religion
  tables count adherents as religious bodies report them, and whether that sum
  passes the population is a number, not an opinion.

**The key never appears in this file's output.** It is read from ``ESTAT_API``
in the environment, it is sent as a query parameter because that is the only
place e-Stat reads it, and every line this prints goes through ``scrub()``,
which replaces the key with a placeholder wherever it occurs -- in a URL, in an
echoed request parameter, in an error body. A probe whose whole product is a
log that gets committed cannot rely on remembering not to print it.

Usage:
    python -m scripts.probe_estat                          # the standing sweep
    python -m scripts.probe_estat --search 宗教 --limit 50
    python -m scripts.probe_estat --surveys 民族
    python -m scripts.probe_estat --meta 0003411172
    python -m scripts.probe_estat --data 0003411172 --rows 40 --group area
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import USER_AGENT, log  # noqa: E402

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
KEY_VAR = "ESTAT_API"
TIMEOUT = 120

# The standing sweep. Japanese first: the catalogue is indexed in Japanese and
# an English search returns only the tables that carry an English title, which
# is a small and arbitrary subset. Each term is what a table of the kind this
# map needs would be titled with, not a guess at a table id.
TERMS: tuple[tuple[str, str], ...] = (
    ("宗教", "religion"),
    ("宗教統計調査", "Religious Statistics Survey (Agency for Cultural Affairs)"),
    ("信者", "adherents / believers"),
    ("信徒", "adherents, the other word for it"),
    ("民族", "ethnicity"),
    ("言語", "language"),
    ("母語", "mother tongue"),
    ("日本語", "Japanese language"),
    ("アイヌ", "Ainu"),
    ("国籍", "nationality"),
    ("外国人", "foreign residents"),
    ("在留外国人", "resident foreigners (Immigration Services Agency)"),
)

# Asked in English too, and separately, because a term that matches nothing in
# Japanese and something in English would mean the catalogue carries an English
# index this sweep is missing.
ENGLISH_TERMS = ("religion", "ethnic", "language", "nationality", "foreigner")

# e-Stat's own words for the geography a table is collected at. Anything other
# than the first is a table that could reach below the national line.
COLLECT_AREA = {
    "該当なし": "no area dimension",
    "全国": "Japan as a whole",
    "都道府県": "prefecture",
    "市区町村": "municipality",
}


def app_id() -> str:
    key = (os.environ.get(KEY_VAR) or "").strip()
    if not key:
        raise SystemExit(
            f"probe_estat: {KEY_VAR} is not set. e-Stat's API answers nothing "
            "without an application id; registration is free at "
            "https://www.e-stat.go.jp/api/. The key belongs in a repository "
            "secret and reaches this script through the environment, never on "
            "a command line.")
    return key


def scrub(text: str) -> str:
    """Anything printed, with the key taken out of it."""
    key = (os.environ.get(KEY_VAR) or "").strip()
    return text.replace(key, f"<{KEY_VAR}>") if key else text


def show(text: str) -> None:
    log(scrub(text))


def shown_call(path: str, params: dict[str, Any]) -> str:
    """The request as it is safe to print: everything but the credential."""
    return f"{path}?{urllib.parse.urlencode(params, encoding='utf-8')}"


def call(path: str, params: dict[str, Any], key: str) -> dict[str, Any]:
    """One GET. Returns the parsed body, or a marker describing the failure."""
    query = dict(params)
    query["appId"] = key
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(query, encoding="utf-8")
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:400]
        return {"__error__": scrub(f"HTTP {err.code} {err.reason or ''}: {detail}".strip())}
    except Exception as err:                                  # noqa: BLE001
        return {"__error__": scrub(f"{type(err).__name__}: {err}")}
    try:
        return json.loads(body)
    except ValueError:
        return {"__error__": scrub(
            f"not JSON: {len(body)} bytes; "
            f"{body[:200].decode('utf-8', 'replace')}")}


def text_of(value: Any) -> str:
    """e-Stat writes a labelled code as {'@code': .., '$': ..} and a bare
    string as itself. Both mean the same thing to a reader."""
    if isinstance(value, dict):
        return str(value.get("$", "")).strip()
    return str(value or "").strip()


def code_of(value: Any) -> str:
    return str(value.get("@code", "")).strip() if isinstance(value, dict) else ""


def listed(node: Any) -> list[dict[str, Any]]:
    """A field e-Stat gives as an object when there is one of it and as an
    array when there are several."""
    if node is None:
        return []
    if isinstance(node, dict):
        return [node]
    return [row for row in node if isinstance(row, dict)]


def result_of(payload: dict[str, Any], envelope: str) -> tuple[int, str, dict[str, Any]]:
    """The API's status, its message, and the envelope's body."""
    if "__error__" in payload:
        return -1, str(payload["__error__"]), {}
    inner = payload.get(envelope) or {}
    result = inner.get("RESULT") or {}
    status = int(result.get("STATUS", -1))
    return status, str(result.get("ERROR_MSG", "")), inner


def search(term: str, key: str, *, limit: int, lang: str = "J",
           surveys: bool = False, raw: bool = False,
           extra: dict[str, Any] | None = None) -> None:
    """One catalogue search, printed as tables or as the surveys behind them."""
    params: dict[str, Any] = {"searchWord": term, "limit": limit, "lang": lang}
    if surveys:
        params["statsNameList"] = "Y"
    params.update(extra or {})
    show(f"  {shown_call('getStatsList', params)}")
    payload = call("getStatsList", params, key)
    status, message, inner = result_of(payload, "GET_STATS_LIST")
    if status != 0:
        # 100 is e-Stat's "該当データが0件" -- a real answer, and the one this
        # probe most wants: the word matches nothing in the whole catalogue.
        show(f"    -> status {status}: {message}")
        return
    datalist = inner.get("DATALIST_INF") or {}
    number = datalist.get("NUMBER", 0)
    rows = listed(datalist.get("TABLE_INF")) or listed(datalist.get("LIST_INF"))
    show(f"    -> {number} match(es), {len(rows)} listed")
    if raw and rows:
        # One entry as the API actually shaped it. A reader of this log should
        # not have to trust one_line()'s idea of which fields exist, and a test
        # that pins the reading needs bytes rather than a paraphrase.
        show("    raw[0]: " + json.dumps(rows[0], ensure_ascii=False)[:1500])
    for row in rows:
        show("    " + one_line(row))


def one_line(row: dict[str, Any]) -> str:
    """A catalogue entry as one line: what it is, when, and how far down."""
    ident = str(row.get("@id", "")).strip()
    stat_name = text_of(row.get("STAT_NAME"))
    stat_code = code_of(row.get("STAT_NAME"))
    org = text_of(row.get("GOV_ORG"))
    title = text_of(row.get("TITLE")) or text_of(row.get("STATISTICS_NAME"))
    spec = row.get("STATISTICS_NAME_SPEC") or {}
    if not title and spec:
        title = " / ".join(text_of(v) for v in spec.values() if text_of(v))
    survey = str(row.get("SURVEY_DATE", "")).strip()
    area = str(row.get("COLLECT_AREA", "")).strip()
    area = f"{area} ({COLLECT_AREA[area]})" if area in COLLECT_AREA else area
    total = row.get("OVERALL_TOTAL_NUMBER", "")
    parts = [f"{ident or '-'}", f"[{stat_code or '-'}] {stat_name or '-'}"]
    if org:
        parts.append(org)
    if title:
        parts.append(title[:180])
    if survey:
        parts.append(f"survey {survey}")
    if area:
        parts.append(f"area {area}")
    if total not in ("", None):
        parts.append(f"{total} cells")
    return " | ".join(parts)


def meta(stats_data_id: str, key: str, *, classes: int) -> None:
    """One table's dimensions, which is where 'by prefecture' is settled."""
    params = {"statsDataId": stats_data_id}
    show(f"  {shown_call('getMetaInfo', params)}")
    payload = call("getMetaInfo", params, key)
    status, message, inner = result_of(payload, "GET_META_INFO")
    if status != 0:
        show(f"    -> status {status}: {message}")
        return
    metadata = inner.get("METADATA_INF") or {}
    table = metadata.get("TABLE_INF") or {}
    show(f"    table: {one_line(table)}")
    for key_name in ("TITLE_SPEC", "STATISTICS_NAME_SPEC"):
        spec = table.get(key_name) or {}
        for field, value in spec.items():
            if text_of(value):
                show(f"      {key_name}.{field}: {text_of(value)}")
    for obj in listed((metadata.get("CLASS_INF") or {}).get("CLASS_OBJ")):
        entries = listed(obj.get("CLASS"))
        show(f"    class {obj.get('@id')} = {obj.get('@name')} "
             f"({len(entries)} codes)")
        for entry in entries[:classes]:
            unit = entry.get("@unit")
            level = entry.get("@level")
            extra = " ".join(x for x in (f"level {level}" if level else "",
                                         f"unit {unit}" if unit else "") if x)
            show(f"      {entry.get('@code')}  {entry.get('@name')}"
                 + (f"   ({extra})" if extra else ""))
        if len(entries) > classes:
            show(f"      ... and {len(entries) - classes} more")


def fetch_values(stats_data_id: str, key: str, filters: dict[str, str],
                 *, limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One page of a table's figures, plus the metadata that names the codes."""
    params: dict[str, Any] = {"statsDataId": stats_data_id, "limit": limit,
                              "metaGetFlg": "Y", "cntGetFlg": "N"}
    params.update(filters)
    show(f"  {shown_call('getStatsData', params)}")
    payload = call("getStatsData", params, key)
    status, message, inner = result_of(payload, "GET_STATS_DATA")
    if status != 0:
        show(f"    -> status {status}: {message}")
        return {}, []
    data = inner.get("STATISTICAL_DATA") or {}
    info = data.get("RESULT_INF") or {}
    show(f"    -> {info.get('TOTAL_NUMBER')} values total, "
         f"rows {info.get('FROM_NUMBER')}-{info.get('TO_NUMBER')}")
    return data, listed((data.get("DATA_INF") or {}).get("VALUE"))


def names_from(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    """{class id: {code: name}} for every dimension the response described."""
    out: dict[str, dict[str, str]] = {}
    class_inf = ((data.get("CLASS_INF") or {}).get("CLASS_OBJ"))
    for obj in listed(class_inf):
        out[str(obj.get("@id"))] = {
            str(e.get("@code")): str(e.get("@name"))
            for e in listed(obj.get("CLASS"))
        }
    return out


def show_data(stats_data_id: str, key: str, filters: dict[str, str],
              *, rows: int, group: list[str], limit: int) -> None:
    data, values = fetch_values(stats_data_id, key, filters, limit=limit)
    if not values:
        return
    names = names_from(data)
    for value in values[:rows]:
        labels = []
        for dim, code in sorted(value.items()):
            if not dim.startswith("@") or dim in ("@unit",):
                continue
            name = names.get(dim[1:], {}).get(str(code), "")
            labels.append(f"{dim[1:]}={code}" + (f'"{name}"' if name else ""))
        show(f"      {' '.join(labels)}  = {value.get('$')} "
             f"{value.get('@unit', '')}".rstrip())
    if len(values) > rows:
        show(f"      ... and {len(values) - rows} more values on this page")
    for dim in group:
        totals: dict[str, float] = {}
        for value in values:
            code = str(value.get(f"@{dim}", ""))
            try:
                totals[code] = totals.get(code, 0.0) + float(str(value.get("$")))
            except ValueError:
                continue                      # "-", "***" and the other marks
        show(f"    sum by {dim} ({len(totals)} groups):")
        for code, total in sorted(totals.items(), key=lambda kv: -kv[1])[:60]:
            name = names.get(dim, {}).get(code, "")
            show(f"      {code} {name}: {total:,.0f}")


def sweep(key: str, *, limit: int, only: list[str]) -> None:
    """The standing search, or the subset of it named on the command line.

    A subset because a catalogue search over a common word is slow -- e-Stat
    takes tens of seconds over 言語 or 外国人 -- and a runner has a wall clock.
    Naming terms splits one sweep into several runs without editing the list.
    """
    show("e-Stat catalogue sweep -- surveys carrying each word")
    for term, gloss in TERMS:
        if only and term not in only:
            continue
        show(f"\n== {term}  ({gloss}) -- surveys carrying the word")
        search(term, key, limit=limit, surveys=True)
        time.sleep(0.4)
    for term in ENGLISH_TERMS:
        if only and term not in only:
            continue
        show(f"\n== {term} (lang=E) -- surveys carrying the word")
        search(term, key, limit=limit, lang="E", surveys=True)
        time.sleep(0.4)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", help="one search word, listed as tables")
    ap.add_argument("--surveys", help="one search word, listed as surveys")
    ap.add_argument("--meta", help="statsDataId whose dimensions to print")
    ap.add_argument("--data", help="statsDataId whose figures to print")
    ap.add_argument("--filter", action="append", default=[],
                    help="a getStatsData filter, e.g. cdCat01=001 (repeatable)")
    ap.add_argument("--group", default="",
                    help="comma-separated dimensions to sum the values by")
    ap.add_argument("--rows", type=int, default=30, help="values to print")
    ap.add_argument("--limit", type=int, default=100, help="rows per request")
    ap.add_argument("--lang", default="J", choices=["J", "E"])
    ap.add_argument("--classes", type=int, default=60,
                    help="codes to print per dimension in --meta")
    ap.add_argument("--terms", default="",
                    help="comma-separated subset of the standing sweep to run")
    ap.add_argument("--collect-area", default="",
                    help="e-Stat collectArea filter: 1 national, 2 prefecture, "
                         "3 municipality, 4 other")
    ap.add_argument("--raw", action="store_true",
                    help="also print the first catalogue entry as the API shaped it")
    args = ap.parse_args()

    key = app_id()
    show(f"probe_estat: {KEY_VAR} found, {len(key)} characters")

    extra = {"collectArea": args.collect_area} if args.collect_area else {}
    did_something = False
    if args.search:
        show(f"\n== {args.search} -- tables")
        search(args.search, key, limit=args.limit, lang=args.lang,
               raw=args.raw, extra=extra)
        did_something = True
    if args.surveys:
        show(f"\n== {args.surveys} -- surveys")
        search(args.surveys, key, limit=args.limit, lang=args.lang,
               surveys=True, raw=args.raw, extra=extra)
        did_something = True
    if args.meta:
        show(f"\n== metadata for {args.meta}")
        meta(args.meta, key, classes=args.classes)
        did_something = True
    if args.data:
        show(f"\n== data for {args.data}")
        filters = dict(f.split("=", 1) for f in args.filter if "=" in f)
        group = [g for g in args.group.split(",") if g]
        show_data(args.data, key, filters, rows=args.rows, group=group,
                  limit=args.limit)
        did_something = True
    if not did_something:
        sweep(key, limit=args.limit,
              only=[t for t in args.terms.split(',') if t])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
