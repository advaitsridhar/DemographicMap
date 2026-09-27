#!/usr/bin/env python3
"""Read-only probes for the central European census readers.

Germany, Austria, Switzerland, Liechtenstein, Poland, Czechia, Slovakia,
Hungary, Slovenia, the Netherlands and Luxembourg each publish population by
age and sex, and several of them census compositions, through their own
portals. Which table, which layout and which geography is not guessable, so
each named probe below asks one office what it serves and prints only what is
needed to write a reader against it: a table's variables, a catalogue's
matching entries, a file's first lines. Nothing is written; the output is the
log.

Usage:
    python -m scripts.fetch_census.central_probe aut che pol
    python -m scripts.fetch_census.central_probe get URL [REGEX]
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from ._shared import log
from common import USER_AGENT  # noqa: E402  (_shared puts scripts/ on the path)

TIMEOUT = 90


def fetch(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None,
          timeout: int = TIMEOUT) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as err:
        body = err.read() or b""
        try:
            if err.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
        except OSError:
            pass
        return err.code, dict(err.headers or {}), body
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not stop
        return -1, {"error": f"{exc.__class__.__name__}: {exc}"}, b""


def text(body: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", "replace")


def show(url: str, find: str | None = None, *, limit: int = 40, raw: int = 0,
         headers: dict[str, str] | None = None, data: bytes | None = None) -> str:
    status, head, body = fetch(url, headers=headers, data=data)
    kind = head.get("Content-Type") or head.get("content-type") or head.get("error", "")
    log(f"\n## {url}\n   HTTP {status}, {len(body):,} bytes, {kind}")
    page = text(body)
    if find:
        seen: list[str] = []
        for m in re.finditer(find, page):
            hit = m.group(0)
            if hit not in seen:
                seen.append(hit)
        log(f"   {len(seen)} distinct matches of {find!r}")
        for hit in seen[:limit]:
            log("   - " + " ".join(hit.split())[:300])
    if raw:
        log("   " + page[:raw].replace("\n", "\n   "))
    return page


def pxweb_meta(url: str, values: int = 8) -> dict[str, Any] | None:
    status, _, body = fetch(url)
    log(f"\n## PxWeb {url}\n   HTTP {status}, {len(body):,} bytes")
    if status != 200:
        log("   " + text(body)[:300])
        return None
    try:
        meta = json.loads(text(body))
    except json.JSONDecodeError:
        log("   not JSON: " + text(body)[:300])
        return None
    if isinstance(meta, list):
        for row in meta[:values * 10]:
            log(f"   - {row.get('id')} [{row.get('type')}] {row.get('text')}")
        return None
    log(f"   title: {meta.get('title')}")
    for var in meta.get("variables", []):
        vals, texts = var.get("values", []), var.get("valueTexts", [])
        sample = ", ".join(f"{v}={t}" for v, t in list(zip(vals, texts))[:values])
        log(f"   {var.get('code')} ({var.get('text')}): {len(vals)} values; {sample}"
            + (f" ... last {vals[-1]}={texts[-1]}" if len(vals) > values else ""))
    return meta


def jpath(obj: Any, keys: str) -> Any:
    for key in keys.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and key.isdigit():
            obj = obj[int(key)] if int(key) < len(obj) else None
        else:
            return None
    return obj


# ---------------------------------------------------------------------------
# One probe per office
# ---------------------------------------------------------------------------

def aut() -> None:
    for year in (2026, 2025, 2024):
        show(f"https://data.statistik.gv.at/web/meta.jsp?dataset=OGD_bevstandjbab2002_BevStand_{year}",
             r"OGD_[A-Za-z0-9_\-]+\.csv|<title>[^<]*")
    show("https://data.statistik.gv.at/web/catalog.jsp", r"dataset=OGD_bev[^\"&'<> ]+", limit=60)


def che() -> None:
    pxweb_meta("https://www.pxweb.bfs.admin.ch/api/v1/de/px-x-0102010000_101/px-x-0102010000_101.px")
    status, _, body = fetch("https://www.pxweb.bfs.admin.ch/api/v1/de/")
    log(f"\n## BFS PxWeb root: HTTP {status}, {len(body):,} bytes")
    try:
        rows = json.loads(text(body))
        log(f"   {len(rows)} databases")
        for row in rows:
            label = f"{row.get('dbid') or row.get('id')} {row.get('text')}"
            if re.search(r"Religion|Konfession|Sprache|Hauptsprache", label):
                log("   - " + label[:200])
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}: {text(body)[:200]}")
    page = show("https://www.agvchapp.bfs.admin.ch/api/communes/snapshot?date=01-01-2009", raw=600)
    lines = page.splitlines()
    log(f"   {len(lines)} lines")


def lie() -> None:
    show("https://www.statistikportal.li/de", r"href=\"[^\"]*(?:bev|volks|etab|Bev|Volks)[^\"]*\"", limit=60)
    show("https://etab.llv.li/", r"href=\"[^\"]+\"|<title>[^<]*", limit=40)


def pol() -> None:
    for query in ("mediana", "wiek"):
        page = show(f"https://bdl.stat.gov.pl/api/v1/variables/search?name={query}&format=json"
                    f"&page-size=100&lang=pl")
        try:
            data = json.loads(page)
            log(f"   totalRecords {data.get('totalRecords')}")
            for row in data.get("results", [])[:100]:
                log(f"   - {row.get('id')} subj {row.get('subjectId')} lvl {row.get('level')} "
                    f"years {row.get('years', [])[-2:] if row.get('years') else ''} | "
                    f"{row.get('n1')} | {row.get('n2')} | {row.get('n3')} | {row.get('n4')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}")


def cze() -> None:
    show("https://csu.gov.cz/otevrena-data", r"href=\"[^\"]*(?:produkty|opendata|otevren)[^\"]*\"", limit=80)
    show("https://data.csu.gov.cz/", r"href=\"[^\"]+\"|<title>[^<]*", limit=30)


def svk() -> None:
    status, _, body = fetch("https://data.statistics.sk/api/v2/collection?lang=en")
    log(f"\n## DATAcube collection: HTTP {status}, {len(body):,} bytes")
    try:
        coll = json.loads(text(body))
        items = jpath(coll, "link.item") or []
        log(f"   {len(items)} datasets")
        for item in items:
            label = item.get("label", "")
            if re.search(r"(?i)age|nationalit|religio|mother tongue|census", label) and \
                    re.search(r"(?i)district|okres|municip", label):
                log(f"   - {item.get('href')} | {label[:160]}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}: {text(body)[:300]}")


def hun() -> None:
    show("https://www.ksh.hu/stadat?lang=en&theme=nep", r"href=\"[^\"]*stadat_files[^\"]*\"[^<]*<", limit=80)
    show("https://nepszamlalas2022.ksh.hu/en/", r"href=\"[^\"]+\"", limit=60)


def svn() -> None:
    pxweb_meta("https://pxweb.stat.si/SiStatData/api/v1/en/Data/05C4002S.px")
    status, _, body = fetch("https://pxweb.stat.si/SiStatData/api/v1/en/Data?query=municipalities&filter=*")
    log(f"\n## SiStat search: HTTP {status}, {len(body):,} bytes")
    try:
        for row in json.loads(text(body))[:80]:
            log(f"   - {row.get('id')} {row.get('title') or row.get('text')}"[:200])
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}: {text(body)[:300]}")


def nld() -> None:
    page = show("https://opendata.cbs.nl/ODataApi/odata/03759ned/DataProperties?$format=json")
    try:
        for row in json.loads(page).get("value", []):
            log(f"   - {row.get('Key')} [{row.get('Type')}] {row.get('Title')}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}")
    flt = urllib.parse.quote("substringof('ezindte',Title) or substringof('eligi',Title)")
    page = show(f"https://opendata.cbs.nl/ODataCatalog/Tables?$format=json&$filter={flt}")
    try:
        for row in json.loads(page).get("value", []):
            log(f"   - {row.get('Identifier')} | {row.get('Title')} | {row.get('Period')} | "
                f"{row.get('Frequency')}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}")


def lux() -> None:
    status, _, body = fetch("https://lustat.statec.lu/rest/dataflow/all/all/latest?detail=allstubs",
                            headers={"Accept": "application/vnd.sdmx.structure+json;version=1.0"})
    log(f"\n## LUSTAT dataflows: HTTP {status}, {len(body):,} bytes")
    page = text(body)
    try:
        flows = jpath(json.loads(page), "data.dataflows") or []
        log(f"   {len(flows)} dataflows")
        for flow in flows:
            name = flow.get("name") or jpath(flow, "names.en") or ""
            if re.search(r"(?i)commun|munic|langu|âge|age\b|age group", name):
                log(f"   - {flow.get('agencyID')}:{flow.get('id')}({flow.get('version')}) {name[:150]}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}: {page[:300]}")


PROBES: dict[str, Callable[[], None]] = {
    "aut": aut, "che": che, "lie": lie, "pol": pol, "cze": cze, "svk": svk,
    "hun": hun, "svn": svn, "nld": nld, "lux": lux,
}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    if argv[0] == "get":
        show(argv[1], argv[2] if len(argv) > 2 else None, raw=0 if len(argv) > 2 else 1500)
        return 0
    if argv[0] == "px":
        for url in argv[1:]:
            pxweb_meta(url)
        return 0
    for name in argv:
        log(f"\n=== {name}")
        try:
            PROBES[name]()
        except Exception as exc:  # noqa: BLE001
            log(f"   probe {name} failed: {exc.__class__.__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
