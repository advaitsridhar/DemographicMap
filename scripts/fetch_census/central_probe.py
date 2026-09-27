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


def head_lines(url: str, n: int = 6, *, grep: str | None = None, limit: int = 40) -> list[str]:
    status, head, body = fetch(url)
    page = text(body)
    lines = page.splitlines()
    log(f"\n## {url}\n   HTTP {status}, {len(body):,} bytes, {len(lines):,} lines, "
        f"{head.get('Content-Type') or head.get('error', '')}")
    for line in lines[:n]:
        log("   | " + line[:240])
    if grep:
        hits = [line for line in lines if re.search(grep, line)]
        log(f"   {len(hits)} lines match {grep!r}")
        for line in hits[:limit]:
            log("   > " + line[:240])
    return lines


def aut2() -> None:
    stem = "https://data.statistik.gv.at/data/OGD_bevstandjbab2002_BevStand_2026"
    head_lines(stem + "_HEADER.csv", 12)
    head_lines(stem + ".csv", 5)
    head_lines(stem + "_C-GRGEMAKT-0.csv", 4, grep=r"GRGEMAKT-9|GRGEMAKT-10[12]", limit=8)
    head_lines(stem + "_C-GALTEJ112-0.csv", 3, grep=r"GALTEJ112-1(0\d|1\d)\b", limit=20)
    head_lines(stem + "_C-C11-0.csv", 4)
    head_lines("https://www.statistik.at/verzeichnis/reglisten/polbezirke.csv", 8)


def che2() -> None:
    lines = head_lines("https://www.agvchapp.bfs.admin.ch/api/communes/snapshot?date=01-01-2009", 1)
    rows = [line.split(",") for line in lines[1:]]
    cantons = {r[0]: r[7] for r in rows if len(r) > 7 and r[4] == "1"}
    districts = [r for r in rows if len(r) > 7 and r[4] == "2"]
    log(f"   2009: {len(cantons)} cantons, {len(districts)} districts, "
        f"{sum(1 for r in rows if len(r) > 7 and r[4] == '3')} communes")
    for r in districts:
        log(f"   D {cantons.get(r[5], r[5])} {r[1]} {r[6]}")
    for q in ("snapshot?date=01-01-2025", "correspondances?startPeriod=01-01-2009&endPeriod=01-01-2025",
              "correspondances?startPeriod=01-01-2009&endPeriod=01-01-2025&includeUnmodified=true",
              "levels?date=01-01-2025"):
        head_lines("https://www.agvchapp.bfs.admin.ch/api/communes/" + q, 4)
    pxweb_meta("https://www.pxweb.bfs.admin.ch/api/v1/de/px-x-0104010000_101/px-x-0104010000_101.px")
    status, _, body = fetch("https://www.pxweb.bfs.admin.ch/api/v1/de/")
    try:
        rows = json.loads(text(body))
        for row in rows:
            label = f"{row.get('dbid') or row.get('id')} {row.get('text')}"
            if re.search(r"(?i)relig|konfess|sprach", label):
                log("   - " + label[:200])
        log(f"   sample root rows: {rows[:3]}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}")


def lie2() -> None:
    for url in ("https://etab.llv.li/PXWeb/api/v1/de/", "https://etab.llv.li/api/v1/de/",
                "https://etab.llv.li/PXWeb/api/v1/de/eTab/"):
        pxweb_meta(url)
    show("https://www.statistikportal.li/de/themen/bevoelkerung/bevoelkerungsstand",
         r"href=\"[^\"]+\.(?:xlsx?|csv|pdf)\"|href=\"[^\"]*etab[^\"]*\"", limit=40)
    show("https://www.statistikportal.li/de/erhebungen-register/volkszaehlung",
         r"href=\"[^\"]+\.(?:xlsx?|csv|pdf)\"|href=\"[^\"]*etab[^\"]*\"", limit=40)


def pol2() -> None:
    base = "https://bdl.stat.gov.pl/api/v1"
    show(f"{base}/subjects/P4280?format=json&lang=pl", raw=1200)
    for q in ("roczniki", "mediana", "struktura ludno", "ludność według"):
        page = show(f"{base}/subjects/search?name={urllib.parse.quote(q)}&format=json&page-size=50&lang=pl")
        try:
            for row in json.loads(page).get("results", [])[:30]:
                log(f"   - {row.get('id')} lvls {row.get('levels')} vars {row.get('hasVariables')} "
                    f"{row.get('name')} | parent {row.get('parentId')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}")
    show(f"{base}/data/by-variable/1650633?format=json&unit-level=5&page-size=3&lang=pl", raw=900)


def cze2() -> None:
    show("https://csu.gov.cz/otevrena_data", r"href=\"[^\"]+\"[^>]*>[^<]*(?:[Vv]ěk|[Oo]byvatel)[^<]*<",
         limit=40)
    show("https://csu.gov.cz/otevrena_data", r"href=\"[^\"]*(?:produkty|katalog|sady)[^\"]*\"", limit=30)


def svk2() -> None:
    for dim in ("om7009rr_vuc", "om7009rr_obd", "om7009rr_ukaz", "om7009rr_poh", "om7009rr_vek",
                "om7005rr_ukaz"):
        cube = dim.split("_")[0]
        page = show(f"https://data.statistics.sk/api/v2/dimension/{cube}/{dim}?lang=en")
        try:
            data = json.loads(page)
            cat = jpath(data, f"dimension.{dim}.category") or jpath(data, "category") or {}
            labels = cat.get("label", {})
            keys = list(labels)
            log(f"   {len(keys)} values: " + "; ".join(f"{k}={labels[k]}" for k in keys[:12])
                + (f" ... {keys[-1]}={labels[keys[-1]]}" if len(keys) > 12 else ""))
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {page[:300]}")
    show("https://www.scitanie.sk/", r"href=\"[^\"]*(?:otvoren|open|data|csv|xlsx)[^\"]*\"", limit=40)


def hun2() -> None:
    show("https://nepszamlalas2022.ksh.hu/en/results/tables", r"href=\"[^\"]+\"[^>]*>[^<]{3,}<", limit=80)
    show("https://www.ksh.hu/stadat?lang=en&theme=nep", r"<a [^>]*href=\"[^\"]+\"[^>]*>[^<]{3,}</a>", limit=80)


def svn2() -> None:
    for path in ("", "Data/", "Data/05C4010S.px", "Data/05C4004S.px", "Data/05C5002S.px",
                 "Data/05C2002S.px"):
        pxweb_meta(f"https://pxweb.stat.si/SiStatData/api/v1/en/{path}")


def nld2() -> None:
    for url in ("https://datasets.cbs.nl/odata/v1/CBS/03759ned",
                "https://odata4.cbs.nl/CBS/03759ned",
                "https://opendata.cbs.nl/ODataApi/odata/03759ned",
                "http://opendata.cbs.nl/ODataApi/odata/03759ned"):
        show(url, raw=500)


def lux2() -> None:
    base = "https://lustat.statec.lu/rest"
    for flow in ("DF_B1607", "DF_X021", "DF_B1102"):
        show(f"{base}/dataflow/LU1/{flow}/latest?references=all&detail=referencepartial",
             r"<(?:str|structure):Name[^>]*xml:lang=\"en\"[^>]*>[^<]+|id=\"[A-Z_0-9]+\"", limit=40,
             headers={"Accept": "application/vnd.sdmx.structure+xml;version=2.1"})
    show(f"{base}/data/LU1,DF_B1607,1.0/all?startPeriod=2021&dimensionAtObservation=AllDimensions",
         raw=1500, headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"})
    show("https://statistiques.public.lu/fr/recensement.html", r"href=\"[^\"]*(?:langu|xls|recensement)[^\"]*\"",
         limit=40)


PROBES: dict[str, Callable[[], None]] = {
    "aut": aut, "che": che, "lie": lie, "pol": pol, "cze": cze, "svk": svk,
    "hun": hun, "svn": svn, "nld": nld, "lux": lux,
    "aut2": aut2, "che2": che2, "lie2": lie2, "pol2": pol2, "cze2": cze2, "svk2": svk2,
    "hun2": hun2, "svn2": svn2, "nld2": nld2, "lux2": lux2,
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
