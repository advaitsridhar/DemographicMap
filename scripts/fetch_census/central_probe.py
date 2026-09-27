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


def che3() -> None:
    """Which 2025 communes straddle a 2009 district, and the BFS tables on religion."""
    lines = fetch("https://www.agvchapp.bfs.admin.ch/api/communes/correspondances?"
                  "startPeriod=01-01-2009&endPeriod=01-01-2025&includeUnmodified=true")[2]
    rows = list(csv_rows(text(lines)))
    spans: dict[str, set[str]] = {}
    for r in rows:
        spans.setdefault(f"{r['TerminalCode']} {r['TerminalName']}", set()).add(r["InitialParentName"])
    log(f"   {len(rows)} correspondences, {len(spans)} terminal communes")
    for commune, parents in sorted(spans.items()):
        if len(parents) > 1:
            log(f"   ! {commune}: {sorted(parents)}")
    import time
    status, _, body = fetch("https://www.pxweb.bfs.admin.ch/api/v1/de/")
    dbs = [row.get("dbid") for row in json.loads(text(body))]
    log(f"   titles of {len(dbs)} BFS tables matching religion or language:")
    for dbid in dbs:
        if not dbid or not dbid.startswith("px-x-01"):
            continue
        status, _, body = fetch(f"https://www.pxweb.bfs.admin.ch/api/v1/de/{dbid}/{dbid}.px", timeout=30)
        try:
            title = json.loads(text(body)).get("title", "")
        except Exception:  # noqa: BLE001
            title = f"HTTP {status}"
        if re.search(r"(?i)relig|konfess|sprach", title):
            log(f"   - {dbid}: {title[:220]}")
        time.sleep(0.2)


def csv_rows(page: str, delimiter: str = ","):
    import csv
    import io
    return csv.DictReader(io.StringIO(page), delimiter=delimiter)


def lie3() -> None:
    base = "https://etab.llv.li/PXWeb/api/v1/de/eTab/"

    def walk(path: str, depth: int) -> None:
        status, _, body = fetch(base + urllib.parse.quote(path))
        try:
            rows = json.loads(text(body))
        except Exception:  # noqa: BLE001
            log(f"   {path}: HTTP {status} {text(body)[:120]}")
            return
        for row in rows:
            rid = row.get("id")
            log(f"   {'  ' * depth}{row.get('type')} {path}{rid} | {row.get('text')}"[:220])
            if row.get("type") == "l" and depth < 3:
                walk(f"{path}{rid}/", depth + 1)
    walk("Bevölkerung/", 0)


def pol3() -> None:
    base = "https://bdl.stat.gov.pl/api/v1"
    for url in (f"{base}/variables?subject-id=P3814&format=json&page-size=100&lang=pl",
                f"{base}/subjects?parent-id=G7&format=json&page-size=100&lang=pl"):
        page = show(url)
        try:
            for row in json.loads(page).get("results", []):
                log(f"   - {row.get('id')} {row.get('name') or ''} {row.get('n1') or ''} | "
                    f"{row.get('n2') or ''} | {row.get('n3') or ''} lvls {row.get('levels')} "
                    f"years {str(row.get('years'))[-40:]}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}")


def svk3() -> None:
    status, _, body = fetch("https://data.statistics.sk/api/v2/collection?lang=en")
    items = jpath(json.loads(text(body)), "link.item") or []
    for item in items:
        label = item.get("label", "")
        if re.search(r"(?i)2021|census|sodb|nationalit|religio|tongue|language", label):
            log(f"   - {item.get('href')} | {label[:160]}")
    show("https://data.statistics.sk/api/v2/dataset/om7005rr/SK0101/2024/IN010088/SPOLU?lang=en&type=json",
         raw=700)
    show("https://statdata.statistics.sk/public/ui/dc/domov/data-view", r"https?://[^\"' ]+", limit=20)


def hun3() -> None:
    import openpyxl
    import io as _io
    for code in ("1.1.2", "1.1.6", "1.1.7"):
        url = f"https://nepszamlalas2022.ksh.hu/en/results/final-data/tables/nsz2022-{code}-eng.xlsx"
        status, _, body = fetch(url)
        log(f"\n## {url}: HTTP {status}, {len(body):,} bytes")
        if status != 200:
            continue
        book = openpyxl.load_workbook(_io.BytesIO(body), read_only=True, data_only=True)
        for sheet in book.worksheets[:6]:
            rows = list(sheet.iter_rows(values_only=True, max_row=14))
            log(f"   sheet {sheet.title!r}: {sheet.max_row} rows x {sheet.max_column} cols")
            for row in rows:
                cells = [str(c)[:28] for c in row[:14] if c is not None]
                if cells:
                    log("     " + " | ".join(cells))


def svn3() -> None:
    status, _, body = fetch("https://pxweb.stat.si/SiStatData/api/v1/en/Data/")
    rows = json.loads(text(body))
    for row in rows:
        title = row.get("text", "")
        if re.search(r"(?i)municipal", title) and re.search(r"(?i)\bage\b|census|ethnic|religio|tongue",
                                                              title):
            log(f"   - {row.get('id')} {title[:200]}")


def nld3() -> None:
    for url in ("https://www.cbs.nl/", "https://archive.org/wayback/available?url=opendata.cbs.nl/ODataApi/odata/03759ned",
                "https://service.pdok.nl/cbs/wijkenbuurten/2022/wfs/v1_0?request=GetCapabilities&service=WFS"):
        show(url, raw=400)


def lux3() -> None:
    base = "https://lustat.statec.lu/rest/data"
    for flow in ("LU1,DF_X021,1.1/all?startPeriod=2015&endPeriod=2017",
                 "LU1,DSD_CENSUS_GROUP1_3@DF_B1607,1.0/all"):
        lines = head_lines(f"{base}/{flow}", 3)
        log(f"   ({len(lines)} lines)")
        # which municipalities and periods, briefly
        head = lines[0].split(",") if lines else []
        log(f"   columns: {head}")
    show("https://statistiques.public.lu/fr.html", r"href=\"[^\"]*(?:recens|rp20|langu)[^\"]*\"", limit=30)


def cze3() -> None:
    query = """PREFIX dct: <http://purl.org/dc/terms/>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
SELECT ?d ?title ?url WHERE {
  ?d a dcat:Dataset ; dct:title ?title ; dcat:distribution ?dist .
  ?dist dcat:downloadURL ?url .
  FILTER(CONTAINS(LCASE(STR(?title)), "věk"))
  FILTER(CONTAINS(STR(?url), "csu.gov.cz") || CONTAINS(STR(?url), "czso.cz"))
} LIMIT 60"""
    url = "https://data.gov.cz/sparql?query=" + urllib.parse.quote(query)
    page = show(url, headers={"Accept": "application/sparql-results+json"})
    try:
        for b in json.loads(page)["results"]["bindings"]:
            log(f"   - {b['title']['value'][:110]} | {b['url']['value']}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}: {page[:300]}")


def aut3() -> None:
    page = text(fetch("https://data.statistik.gv.at/web/catalog.jsp")[2])
    ids = sorted(set(re.findall(r"dataset=(OGD_[^\"&'<> ]+)", page)))
    log(f"   {len(ids)} OGD datasets")
    for i in ids:
        if re.search(r"(?i)vz|volksz|relig|sprach|2001|census|reg", i):
            log(f"   - {i}")


def deu3() -> None:
    base = "https://www-genesis.destatis.de/genesisWS/rest/2020"
    for term in ("Sprache", "gesprochene Sprache"):
        body = urllib.parse.urlencode({"term": term, "category": "tables", "pagelength": "50",
                                       "language": "de"}).encode()
        status, _, reply = fetch(f"{base}/find/find", data=body,
                                 headers={"username": "GAST", "password": "GAST",
                                          "Content-Type": "application/x-www-form-urlencoded"})
        log(f"\n## GENESIS find {term!r}: HTTP {status}, {len(reply):,} bytes")
        try:
            data = json.loads(text(reply))
            log(f"   status: {data.get('Status')}")
            for row in (data.get("Tables") or [])[:50]:
                log(f"   - {row.get('Code')} | {row.get('Content')[:160]} | {row.get('Time')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {text(reply)[:300]}")


def cze4() -> None:
    lines = head_lines("https://data.csu.gov.cz/opendata/sady/OBY02BHVD/distribuce/csv", 4)
    if lines:
        rows = list(csv_rows("\n".join(lines)))
        kinds = Counter_(r.get("uzemi_cis") or r.get("UZEMI_CIS") or "?" for r in rows)
        years = Counter_(r.get("casref_do") or r.get("rok") or "?" for r in rows)
        log(f"   territory kinds {dict(kinds)}; periods {dict(list(years.items())[-6:])}")
        log(f"   columns {list(rows[0].keys()) if rows else []}")


def Counter_(items):  # noqa: N802 - a local alias keeps the import where it is used
    from collections import Counter
    return Counter(items)


def pol4() -> None:
    base = "https://bdl.stat.gov.pl/api/v1"
    show(f"{base}/data/by-variable/746289?format=json&unit-level=5&page-size=2&lang=pl", raw=700)
    show(f"{base}/data/by-variable/746289?format=json&unit-level=0&lang=pl", raw=500)
    for subject in ("P1336", "P2137"):
        page = show(f"{base}/variables?subject-id={subject}&format=json&page-size=12&lang=pl")
        try:
            for row in json.loads(page).get("results", []):
                log(f"   - {row.get('id')} {row.get('n1')} | {row.get('n2')} | {row.get('n3')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}")


def svk4() -> None:
    show("https://data.statistics.sk/api/v2/dataset/om7009rr/SK0101/2024/IN010053/1/all?lang=en&type=json",
         raw=600)
    page = show("https://data.statistics.sk/api/v2/dataset/om7005rr/all/2024/IN010088/SPOLU?lang=en&type=json")
    try:
        data = json.loads(page)
        log(f"   ids {data.get('id')} sizes {data.get('size')} values {str(data.get('value'))[:300]}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}")
    show("https://www.scitanie.sk/", r"href=\"[^\"]+\"", limit=80)


def hun4() -> None:
    show("https://nepszamlalas2022.ksh.hu/", r"href=\"[^\"]*(?:tabl|xlsx|terulet|kiadvany|adatbazis)[^\"]*\"",
         limit=60)
    show("https://nepszamlalas2022.ksh.hu/eredmenyek/vegleges-adatok/tablak/",
         r"href=\"[^\"]+\.xlsx\"", limit=80)
    show("https://nepszamlalas2022.ksh.hu/adatbazis/", raw=1500)


def nld4() -> None:
    for prefix in ("opendata.cbs.nl/ODataFeed/odata/03759ned", "opendata.cbs.nl/ODataApi/odata/03759ned",
                   "opendata.cbs.nl/CsvDownload/csv/03759ned", "opendata.cbs.nl/ODataApi/OData/03759ned"):
        head_lines(f"http://web.archive.org/cdx/search/cdx?url={prefix}*&limit=25&fl=timestamp,original,length",
                   25)


def lux4() -> None:
    csv_accept = {"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}
    for flow in ("LU1,DF_X021,1.1/all?startPeriod=2017&endPeriod=2017",
                 "LU1,DSD_CENSUS_GROUP1_3@DF_B1607,1.0/all"):
        status, _, body = fetch(f"https://lustat.statec.lu/rest/data/{flow}", headers=csv_accept)
        lines = text(body).splitlines()
        log(f"\n## {flow}: HTTP {status}, {len(lines)} lines")
        for line in lines[:4]:
            log("   | " + line[:300])
        if len(lines) > 1:
            rows = list(csv_rows("\n".join(lines)))
            for col in rows[0]:
                vals = Counter_(r[col] for r in rows)
                if len(vals) < 400:
                    log(f"   {col}: {len(vals)} values, e.g. {list(vals)[:12]}")
                else:
                    log(f"   {col}: {len(vals)} values")
    show("https://statistiques.public.lu/fr/publications/recensement.html", r"href=\"[^\"]+\"[^>]*>[^<]{4,}<",
         limit=80)


def aut4() -> None:
    for i in (1, 2, 3, 4):
        stem = f"https://data.statistik.gv.at/data/OGD_f0743_VZ_HIS_GEM_{i}"
        head_lines(stem + "_HEADER.csv", 12)
    show("https://data.statistik.gv.at/web/meta.jsp?dataset=OGD_f0743_VZ_HIS_GEM_1",
         r"OGD_[A-Za-z0-9_\-]+\.csv|<title>[^<]*|Religion[^<]{0,80}|Umgangssprache[^<]{0,80}")


def deu4() -> None:
    base = "https://genesis.destatis.de/genesisWS/rest/2020"
    for term in ("Sprache", "Religion"):
        body = urllib.parse.urlencode({"term": term, "category": "tables", "pagelength": "60",
                                       "language": "de"}).encode()
        status, _, reply = fetch(f"{base}/find/find", data=body,
                                 headers={"username": "GAST", "password": "GAST",
                                          "Content-Type": "application/x-www-form-urlencoded"})
        log(f"\n## GENESIS find {term!r}: HTTP {status}, {len(reply):,} bytes")
        try:
            data = json.loads(text(reply))
            log(f"   status: {data.get('Status')}")
            for row in (data.get("Tables") or [])[:60]:
                log(f"   - {row.get('Code')} | {row.get('Content')[:170]} | {row.get('Time')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {text(reply)[:300]}")


def che4() -> None:
    import time
    status, _, body = fetch("https://www.pxweb.bfs.admin.ch/api/v1/de/")
    dbs = [row.get("dbid") for row in json.loads(text(body))]
    for dbid in dbs:
        if not dbid or not re.match(r"px-x-010[2-6]", dbid):
            continue
        status, _, body = fetch(f"https://www.pxweb.bfs.admin.ch/api/v1/de/{dbid}/{dbid}.px", timeout=30)
        try:
            title = json.loads(text(body)).get("title", "")
        except Exception:  # noqa: BLE001
            title = f"HTTP {status} {text(body)[:60]}"
        log(f"   - {dbid}: {title[:230]}")
        time.sleep(0.15)
    show("https://www.bfs.admin.ch/bfs/de/home/statistiken/bevoelkerung/sprachen-religionen/religionen.html",
         r"href=\"[^\"]*asset[^\"]*\"[^>]*>[^<]*<|href=\"[^\"]*dam-api[^\"]*\"", limit=40)


def cze5() -> None:
    lines = head_lines("https://csu.gov.cz/docs/107508/bc8f2d41-4d3a-a8f4-02fa-800d9cd27266/"
                       "130181-24data2023.csv", 4)
    rows = list(csv_rows("\n".join(lines)))
    if rows:
        for col in rows[0]:
            vals = Counter_(r[col] for r in rows)
            log(f"   {col}: {len(vals)} values, e.g. {list(vals)[:8]}")
    query = """PREFIX dct: <http://purl.org/dc/terms/>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
SELECT ?title ?url WHERE {
  ?d a dcat:Dataset ; dct:title ?title ; dcat:distribution ?dist .
  ?dist dcat:downloadURL ?url .
  FILTER(CONTAINS(STR(?url), "130181") || CONTAINS(LCASE(STR(?title)), "jednotek věku"))
} LIMIT 80"""
    page = show("https://data.gov.cz/sparql?query=" + urllib.parse.quote(query),
                headers={"Accept": "application/sparql-results+json"})
    try:
        for b in json.loads(page)["results"]["bindings"]:
            log(f"   - {b['title']['value'][:110]} | {b['url']['value']}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}")


def hun5() -> None:
    show("https://nepszamlalas2022.ksh.hu/eredmenyek/statikus-tablak", r"href=\"[^\"]+\"[^>]*>[^<]{3,}<",
         limit=120)
    show("https://nepszamlalas2022.ksh.hu/adatbazis/app.js?v1", r"(?:https?:)?//[^\"' ]+|/api/[^\"' ]+|\.php[^\"' ]*",
         limit=40)


def che5() -> None:
    for table in ("px-x-0103030000_211", "px-x-0103030000_220", "px-x-0103030000_223"):
        pxweb_meta(f"https://www.pxweb.bfs.admin.ch/api/v1/de/{table}/{table}.px")
    head_lines("https://www.agvchapp.bfs.admin.ch/api/communes/correspondances?"
               "startPeriod=01-01-2009&endPeriod=01-01-2011", 1)


def svk5() -> None:
    show("https://www.scitanie.sk/obyvatelia/rozsirene-vysledky", r"href=\"[^\"]+\"[^>]*>[^<]{3,}<", limit=80)
    show("https://www.scitanie.sk/obyvatelia/zakladne-vysledky/pocet-obyvatelov/SR/SK0/SR",
         r"href=\"[^\"]*(?:zakladne-vysledky|xlsx|csv|stiahn)[^\"]*\"", limit=60)


def nld5() -> None:
    show("https://service.pdok.nl/cbs/wijkenbuurten/2022/wfs/v1_0?request=DescribeFeatureType&service=WFS"
         "&version=2.0.0&typeNames=wijkenbuurten:gemeenten", r"name=\"[a-z_0-9]+\"", limit=120)
    show("https://www.cbs.nl/nl-nl/zoeken?q=religie%20provincie", r"href=\"[^\"]*(?:relig|kerk)[^\"]*\"",
         limit=30)


def lux5() -> None:
    show("https://statistiques.public.lu/fr/publications/recensement/diversite-linguistique.html",
         r"href=\"[^\"]+\.(?:xlsx?|csv|pdf)\"|href=\"[^\"]*lustat[^\"]*\"", limit=40)
    status, _, body = fetch("https://lustat.statec.lu/rest/dataflow/all/all/latest?detail=allstubs",
                            headers={"Accept": "application/vnd.sdmx.structure+json;version=1.0"})
    flows = jpath(json.loads(text(body)), "data.dataflows") or []
    for flow in flows:
        name = flow.get("name") or ""
        if re.search(r"(?i)2011|census|recens|RP20|langu|main language|religi", name) and \
                not re.search(r"(?i)working status|occupation|economic|education", name):
            log(f"   - {flow.get('id')}({flow.get('version')}) {name[:150]}")


def hun6() -> None:
    page = text(fetch("https://nepszamlalas2022.ksh.hu/adatbazis/app.js?v1")[2])
    for pattern in (r"fetch\([^)]{0,120}\)", r"[\"'`][^\"'`]{0,60}(?:api|\.json|data/)[^\"'`]{0,80}[\"'`]"):
        hits = sorted(set(re.findall(pattern, page)))
        log(f"   {len(hits)} matches of {pattern!r}")
        for hit in hits[:40]:
            log("   - " + hit[:200])
    show("https://map.ksh.hu/nepszamlalas/", r"src=\"[^\"]+\"|href=\"[^\"]+\"", limit=30)


def nld6() -> None:
    show("https://www.cbs.nl/nl-nl/maatwerk/2026/11/religie-naar-regio-2021-2025",
         r"href=\"[^\"]+\.(?:xlsx|csv|zip|ods)\"|<title>[^<]*|<p>[^<]{20,400}</p>", limit=20)
    show("https://www.cbs.nl/nl-nl/zoeken?q=leeftijd%20gemeente%20geslacht%20maatwerk",
         r"href=\"[^\"]*(?:maatwerk|cijfers/detail)[^\"]*\"", limit=30)


def svk6() -> None:
    page = show("https://gis.scitanie.sk/portal/sharing/rest/search?q=n%C3%A1rodnos%C5%A5&f=json&num=40")
    try:
        for row in json.loads(page).get("results", []):
            log(f"   - {row.get('type')} | {row.get('title')} | {row.get('url')}")
    except Exception as exc:  # noqa: BLE001
        log(f"   {exc}")
    for q in ("okres", "vierovyznanie", "jazyk"):
        page = text(fetch(f"https://gis.scitanie.sk/portal/sharing/rest/search?q={q}&f=json&num=40")[2])
        try:
            for row in json.loads(page).get("results", []):
                log(f"   [{q}] {row.get('type')} | {row.get('title')} | {row.get('url')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}")
    show("https://www.scitanie.sk/mapa-stranok", r"href=\"[^\"]*obyvatelia/zakladne-vysledky[^\"]*\"", limit=60)


def lie7() -> None:
    url = ("https://etab.llv.li/PXWeb/api/v1/de/eTab/" +
           urllib.parse.quote("Bevölkerung/Bevölkerungsstand/Stichtag 31 Dezember/211.004.px"))
    meta = json.loads(text(fetch(url)[2]))
    for v in meta["variables"]:
        log(f"   {v['code']!r}: {list(zip(v['values'], v['valueTexts']))[:16]}")
    query = {"query": [
        {"code": "Jahr", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Altersjahr", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Geschlecht", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Heimat", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Wohnort", "selection": {"filter": "item",
                                          "values": [str(i) for i in range(14)]}}],
        "response": {"format": "json-stat2"}}
    for fmt in ("json-stat2", "json-stat", "csv"):
        query["response"]["format"] = fmt
        status, _, body = fetch(url, data=json.dumps(query).encode(),
                                headers={"Content-Type": "application/json"})
        log(f"\n## POST {fmt}: HTTP {status}, {len(body):,} bytes")
        log("   " + text(body)[:1500].replace("\n", "\n   "))


def xlsx_dump(url: str, rows: int = 12, sheets: int = 8, cols: int = 14) -> None:
    import io as _io
    import openpyxl
    status, _, body = fetch(url)
    log(f"\n## {url}: HTTP {status}, {len(body):,} bytes")
    if status != 200:
        return
    book = openpyxl.load_workbook(_io.BytesIO(body), read_only=True, data_only=True)
    log(f"   sheets: {book.sheetnames}")
    for sheet in book.worksheets[:sheets]:
        log(f"   sheet {sheet.title!r}: {sheet.max_row} rows x {sheet.max_column} cols")
        for row in sheet.iter_rows(values_only=True, max_row=rows):
            cells = [str(c)[:30] for c in row[:cols] if c is not None]
            if cells:
                log("     " + " | ".join(cells))


def hun7() -> None:
    page = text(fetch("https://nepszamlalas2022.ksh.hu/adatbazis/app.js?v1")[2])
    for pattern in (r"\bal\s*=\s*[^,;]{0,100}", r"apiBaseUrl\s*[:=]\s*[^,;]{0,100}", r"new ol\([^)]{0,100}\)",
                    r"https://[a-z0-9.\-]*ksh\.hu[^\"'` ]*"):
        hits = sorted(set(re.findall(pattern, page)))
        log(f"   {pattern!r}: {hits[:12]}")
    for url in ("https://nepszamlalas2022.ksh.hu/adatbazis/api/version",
                "https://nepszamlalas2022.ksh.hu/api/version",
                "https://nepszamlalas2022.ksh.hu/adatbazis/api/index/hu/0"):
        show(url, raw=600)


def svk7() -> None:
    for q in ("obyv_", "Hosted narodnost", "okres narod", "materinsk", "nabozen"):
        page = text(fetch("https://gis.scitanie.sk/portal/sharing/rest/search?q="
                          + urllib.parse.quote(q) + "&f=json&num=100")[2])
        try:
            rows = json.loads(page).get("results", [])
            log(f"   [{q}] {len(rows)} results")
            for row in rows:
                if row.get("url") and "server/rest" in (row.get("url") or ""):
                    log(f"   - {row.get('type')} | {row.get('title')} | {row.get('url')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {page[:200]}")
    show("https://gis.scitanie.sk/server/rest/services/Hosted?f=json", raw=3000)


def nld7() -> None:
    xlsx_dump("https://www.cbs.nl/-/media/_excel/2026/11/religie_2025_tabellen.xlsx", rows=16)


def hun8() -> None:
    base = "https://nepszamlalas2022.ksh.hu/api"
    for path in ("index/hu/V67", "index/en/V67", "index/hu", "dataflows", "structure"):
        show(f"{base}/{path}", raw=1500)


def svk8() -> None:
    base = "https://gis.scitanie.sk/server/rest/services/Hosted/"
    for service in ("obyv_ekchar_nar_dlnar", "obyv_ekchar_nar_matjaz", "obyv_ekchar_nabo_vekskup",
                    "obyv_ekchar_matjaz_vekskup", "obyv_demo_vek_zloz"):
        page = text(fetch(base + service + "/FeatureServer/layers?f=json")[2])
        try:
            layers = json.loads(page).get("layers", [])
        except Exception as exc:  # noqa: BLE001
            log(f"   {service}: {exc}: {page[:200]}")
            continue
        log(f"\n## {service}: {len(layers)} layers")
        for layer in layers:
            fields = [f["name"] for f in layer.get("fields", [])]
            log(f"   layer {layer.get('id')} {layer.get('name')!r}: {len(fields)} fields: "
                f"{fields[:60]}")


def nld8() -> None:
    import io as _io
    import openpyxl
    body = fetch("https://www.cbs.nl/-/media/_excel/2026/11/religie_2025_tabellen.xlsx")[2]
    book = openpyxl.load_workbook(_io.BytesIO(body), read_only=True, data_only=True)
    for name, cols in (("Tabel 2", 28), ("Toelichting", 3), ("Tabel 1", 6)):
        log(f"\n## sheet {name}")
        for row in book[name].iter_rows(values_only=True):
            cells = [str(c)[:60] for c in row[:cols] if c is not None]
            if cells:
                log("   " + " | ".join(cells))


def hun9() -> None:
    page = text(fetch("https://nepszamlalas2022.ksh.hu/adatbazis/app.js?v1")[2])
    for word in ("/api/index/", "/api/structure/", "/api/dataflows/"):
        for m in list(re.finditer(re.escape(word), page))[:2]:
            log(f"   ...{page[max(0, m.start() - 700):m.start() + 300]}...".replace("\n", " "))


def svk9() -> None:
    base = "https://gis.scitanie.sk/server/rest/services/Hosted/"
    for service, layer in (("obyv_ekchar_nabo_vekskup", 5), ("obyv_ekchar_matjaz_vekskup", 5),
                           ("obyv_ekchar_nar_vekskup", None), ("obyv_ekchar_nar_dlnar", 2)):
        if layer is None:
            page = text(fetch(base + service + "/FeatureServer/layers?f=json")[2])
            try:
                for lay in json.loads(page).get("layers", []):
                    log(f"   {service} layer {lay['id']} {lay['name']!r}: "
                        f"{[(f['name'], f.get('alias')) for f in lay.get('fields', [])][:40]}")
            except Exception as exc:  # noqa: BLE001
                log(f"   {exc}")
            continue
        page = text(fetch(f"{base}{service}/FeatureServer/{layer}?f=json")[2])
        try:
            info = json.loads(page)
            log(f"\n## {service}/{layer} {info.get('name')!r}")
            log(f"   fields: {[(f['name'], f.get('alias')) for f in info.get('fields', [])]}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {page[:200]}")
        q = (f"{base}{service}/FeatureServer/{layer}/query?where=1%3D1&outFields=*&returnGeometry=false"
             f"&resultRecordCount=4&f=json")
        page = text(fetch(q)[2])
        try:
            for feat in json.loads(page).get("features", []):
                log(f"   row: {json.dumps(feat.get('attributes'), ensure_ascii=False)[:700]}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {page[:200]}")
        count = text(fetch(f"{base}{service}/FeatureServer/{layer}/query?where=1%3D1&returnCountOnly=true&f=json")[2])
        log(f"   count: {count[:100]}")


def hun10() -> None:
    base = "https://nepszamlalas2022.ksh.hu/api"
    version = json.loads(text(fetch(f"{base}/version")[2]))["version"]
    for lang in ("en", "hu"):
        page = text(fetch(f"{base}/index/{version}/{lang}")[2])
        try:
            data = json.loads(page)
        except Exception as exc:  # noqa: BLE001
            log(f"   {lang}: {exc}: {page[:300]}")
            continue
        flows = data.get("dataflows", [])
        log(f"\n## index {version}/{lang}: keys {list(data)[:10]}, {len(flows)} dataflows")
        for flow in flows:
            label = json.dumps(flow, ensure_ascii=False)
            if re.search(r"(?i)district|járás|religi|vallás|nation|nemzetis|tongue|anyanyelv|age|kor\b|sex|nem\b",
                         label):
                log(f"   - {label[:400]}")
        if flows:
            log(f"   first: {json.dumps(flows[0], ensure_ascii=False)[:600]}")


def hun11() -> None:
    base = "https://nepszamlalas2022.ksh.hu/api"
    version = json.loads(text(fetch(f"{base}/version")[2]))["version"]
    index = json.loads(text(fetch(f"{base}/index/{version}/en")[2]))
    for flow in index["dataflows"]:
        if flow["id"] in ("WBS001", "WBS003", "WBS008", "WBS009", "WBS010"):
            log(f"   {flow['id']}: {json.dumps(flow['dimensions'], ensure_ascii=False)[:1500]}")
    dims = index.get("dimensions")
    log(f"   dimensions entry: {json.dumps(dims, ensure_ascii=False)[:1500]}")
    for flow in ("WBS001", "WBS003"):
        page = text(fetch(f"{base}/structure/{flow}/{version}")[2])
        log(f"\n## structure {flow}: {len(page):,} chars: {page[:1500]}")
        try:
            data = json.loads(page)
            cls = jpath(data, "data.codelists") or []
            for cl in cls:
                codes = cl.get("codes", [])
                log(f"   codelist {cl.get('id')}: {len(codes)} codes, e.g. "
                    f"{[(c.get('id'), jpath(c, 'names.en') or c.get('name')) for c in codes[:8]]}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}")
    for path in (f"dataflows/WBS001/{version}", f"dataflows/WBS001/{version}/d/CL_TIME_PERIOD,CL_TERUL_GEO4,CL_NEME_SEX,CL_KEV_AGE",
                 f"dataflows/WBS001/latest"):
        show(f"{base}/{path}", raw=800)


def hun12() -> None:
    base = "https://nepszamlalas2022.ksh.hu/api"
    version = json.loads(text(fetch(f"{base}/version")[2]))["version"]
    page = text(fetch("https://nepszamlalas2022.ksh.hu/adatbazis/app.js?v1")[2])
    for m in list(re.finditer(r"OBS_VALUE", page))[:3]:
        log(f"   ...{page[max(0, m.start() - 600):m.start() + 400]}...".replace("\n", " "))
    for flow in ("WBS001", "WBS003"):
        data = json.loads(text(fetch(f"{base}/structure/{flow}/{version}")[2]))
        dsds = jpath(data, "data.dataStructures") or []
        for dsd in dsds:
            dims = jpath(dsd, "dataStructureComponents.dimensionList.dimensions") or []
            log(f"   {flow} dimensions: {[(d.get('id'), jpath(d, 'localRepresentation.enumeration')) for d in dims]}")
        for cl in jpath(data, "data.codelists") or []:
            codes = cl.get("codes", [])
            if cl["id"] in ("CL_TERUL_GEO4", "CL_TERUL_GEO5"):
                named = [(c["id"], jpath(c, "names.en") or c.get("name"), c.get("parent")) for c in codes]
                log(f"   {cl['id']}: {len(codes)}; first 30: {named[:30]}")
                log(f"   {cl['id']}: codes by length: {Counter_(len(c['id']) for c in codes)}")
                log(f"   {cl['id']}: sample 5-char: {[n for n in named if len(n[0]) == 5][:10]}")
                log(f"   {cl['id']}: sample 3-char: {[n for n in named if len(n[0]) == 3][:40]}")
            if cl["id"] in ("CL_TEL_SZ_ADAT", "CL_KEV_AGE"):
                log(f"   {cl['id']}: {[(c['id'], jpath(c, 'names.en') or c.get('name'), c.get('parent')) for c in codes]}"[:6000])
    tries = [f"dataflows/WBS001/{version}/d/TIME_PERIOD:2022,TERUL_GEO4:HU110,NEME_SEX:M,KEV_AGE",
             f"dataflows/WBS001/{version}/d/TIME_PERIOD:2022,TERUL_GEO4:HU110,NEME_SEX:M+F,KEV_AGE:TOTAL+Y1+Y2",
             f"dataflows/WBS001/{version}/d/TERUL_GEO4:HU110"]
    for path in tries:
        show(f"{base}/{path}", raw=900)


def deu5() -> None:
    base = "https://genesis.destatis.de/genesisWS/rest/2020"
    for term in ("vorwiegend gesprochene Sprache", "Haushaltssprache", "Einwanderungsgeschichte",
                 "Migrationshintergrund"):
        body = urllib.parse.urlencode({"term": term, "category": "tables", "pagelength": "40",
                                       "language": "de"}).encode()
        status, _, reply = fetch(f"{base}/find/find", data=body,
                                 headers={"username": "GAST", "password": "GAST",
                                          "Content-Type": "application/x-www-form-urlencoded"})
        try:
            data = json.loads(text(reply))
            log(f"\n## GENESIS {term!r}: {len(data.get('Tables') or [])} tables")
            for row in (data.get("Tables") or [])[:40]:
                log(f"   - {row.get('Code')} | {' '.join(row.get('Content', '').split())[:170]}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {text(reply)[:200]}")
    show("https://www.destatis.de/SiteGlobals/Forms/Suche/Expertensuche_Formular.html?"
         "templateQueryString=vorwiegend+gesprochene+Sprache", r"href=\"[^\"]+\"[^>]*>[^<]{10,}<", limit=40)


def hun13() -> None:
    base = "https://nepszamlalas2022.ksh.hu/api"
    version = json.loads(text(fetch(f"{base}/version")[2]))["version"]
    data = json.loads(text(fetch(f"{base}/structure/WBS003/{version}")[2]))
    for cl in jpath(data, "data.codelists") or []:
        if cl["id"] == "CL_TEL_SZ_ADAT":
            codes = [(c["id"], jpath(c, "names.en"), c.get("parent")) for c in cl["codes"]]
            log(f"   CL_TEL_SZ_ADAT from 60: {codes[60:]}")
    for path in (f"dataflows/WBS003/{version}/d/TIME_PERIOD:2022,TERUL_GEO5:122,TEL_SZ_ADAT",
                 f"dataflows/WBS003/{version}/d/TIME_PERIOD:2022,TERUL_GEO5:HU120,TEL_SZ_ADAT",
                 f"dataflows/WBS001/{version}/d/TIME_PERIOD:2022,TERUL_GEO4:122,NEME_SEX:M,KEV_AGE"):
        page = text(fetch(f"{base}/{path}")[2])
        try:
            rows = json.loads(page)
            log(f"\n## {path}: {len(rows)} rows")
            for r in rows[:200]:
                key = r.get("TEL_SZ_ADAT") or r.get("KEV_AGE")
                log(f"   {key}={r.get('OBS_VALUE')}")
        except Exception as exc:  # noqa: BLE001
            log(f"   {exc}: {page[:300]}")


def deu6() -> None:
    """The Zensus 2022 database's answers to a few forms of the same request.

    The account reaches this probe through the environment and goes only into
    request headers; nothing here prints it.
    """
    import os
    auth = {"username": os.environ.get("ZENSUS_USER", ""), "password": os.environ.get("ZENSUS_PASSWORD", "")}
    base = "https://ergebnisse.zensus2022.de/api/rest/2020"
    for path in ("helloworld/logincheck", "catalogue/tables?selection=1000A-1018&language=de"):
        status, _, body = fetch(f"{base}/{path}", data=b"", headers={**auth, "Content-Type":
                                                                     "application/x-www-form-urlencoded"})
        log(f"\n## {path}: HTTP {status}: {text(body)[:400]}")
    variants = {
        "as written": {"name": "1000A-1018", "area": "all", "format": "ffcsv", "compress": "false",
                       "language": "de", "regionalvariable": "GEORB1", "regionalschluessel": ""},
        "no key": {"name": "1000A-1018", "area": "all", "format": "ffcsv", "compress": "false",
                   "language": "de", "regionalvariable": "GEORB1"},
        "Land cut": {"name": "1000A-1018", "area": "all", "format": "ffcsv", "compress": "false",
                     "language": "de", "regionalvariable": "GEOBL1"},
        "default": {"name": "1000A-1018", "area": "all", "format": "ffcsv", "compress": "false",
                    "language": "de"},
        "Kreise": {"name": "1000A-1018", "area": "all", "format": "ffcsv", "compress": "false",
                   "language": "de", "regionalvariable": "GEOLK4"},
    }
    for label, params in variants.items():
        status, head, body = fetch(f"{base}/data/tablefile", data=urllib.parse.urlencode(params).encode(),
                                   headers={**auth, "Content-Type": "application/x-www-form-urlencoded"})
        kind = head.get("Content-Type") or head.get("content-type")
        log(f"\n## tablefile {label}: HTTP {status}, {len(body):,} bytes, {kind}")
        if not body.startswith(b"PK"):
            log("   " + text(body)[:300].replace("\n", " "))


def che7() -> None:
    for url in ("https://www.bfs.admin.ch/bfs/de/home/statistiken/bevoelkerung/sprachen-religionen/religionen.html",
                "https://www.bfs.admin.ch/bfs/de/home/statistiken/bevoelkerung/sprachen-religionen/sprachen.html",
                "https://www.bfs.admin.ch/bfs/de/home/statistiken/bevoelkerung/sprachen-religionen.assetdetail.html"):
        show(url, r"assetdetail\.\d+\.html|dam-api[^\"' ]+|href=\"[^\"]*(?:xlsx|je-d-01\.08)[^\"]*\"", limit=40)


def nld9() -> None:
    url = ("https://service.pdok.nl/cbs/wijkenbuurten/2022/wfs/v1_0?request=GetFeature&service=WFS&version=2.0.0"
           "&typeNames=wijkenbuurten:gemeenten&propertyName=gemeentecode,gemeentenaam,water,mannen,vrouwen,jaar"
           "&outputFormat=application/json&count=5")
    show(url, raw=1500)
    for year in (2022, 2023):
        show(f"https://service.pdok.nl/cbs/wijkenbuurten/{year}/wfs/v1_0?request=GetFeature&service=WFS"
             f"&version=2.0.0&typeNames=wijkenbuurten:gemeenten&resultType=hits", raw=400)
    show("https://www.cbs.nl/nl-nl/maatwerk/2023/14/kerncijfers-wijken-en-buurten-2022",
         r"href=\"[^\"]+\.(?:xlsx|zip|csv)\"", limit=10)


CHE_RELIGION_ASSETS = (36343816, 36429858, 35627011, 35607916, 35607913, 35607915, 35607929,
                       35627019, 35607932, 36429856, 36429857)
CHE_LANGUAGE_ASSETS = (36434442, 36434449, 36630112, 36063525, 36434435, 36063516, 36063463,
                       36063461)


def che8() -> None:
    """What each BFS asset on the religion and language pages is, and the xlsx ones' heads."""
    for asset in CHE_RELIGION_ASSETS + CHE_LANGUAGE_ASSETS:
        status, head, body = fetch(f"https://dam-api.bfs.admin.ch/hub/api/dam/assets/{asset}")
        page = text(body)
        titles = re.findall(r'"(?:title|name|filename|fileName|mimeType|language)"\s*:\s*"([^"]{1,160})"',
                            page)
        log(f"\n# asset {asset}: meta HTTP {status}: {' | '.join(dict.fromkeys(titles))[:600]}")
        if status != 200:
            log("   " + page[:300].replace("\n", " "))
        status, head, body = fetch(f"https://dam-api.bfs.admin.ch/hub/api/dam/assets/{asset}/master")
        kind = head.get("Content-Type") or head.get("content-type") or head.get("error", "")
        disp = head.get("Content-Disposition") or head.get("content-disposition") or ""
        log(f"   master HTTP {status}, {len(body):,} bytes, {kind}, {disp[:120]}")
        if status == 200 and body[:2] == b"PK":
            import io as _io
            import openpyxl
            try:
                book = openpyxl.load_workbook(_io.BytesIO(body), read_only=True, data_only=True)
            except Exception as exc:  # noqa: BLE001
                log(f"   not a workbook: {exc}")
                continue
            log(f"   sheets: {book.sheetnames[:12]}")
            for sheet in book.worksheets[:2]:
                log(f"   sheet {sheet.title!r}")
                for row in sheet.iter_rows(values_only=True, max_row=16):
                    cells = [str(c)[:28] for c in row[:12] if c is not None]
                    if cells:
                        log("     " + " | ".join(cells))


def svn4() -> None:
    """Census 2002 by municipality: religion, mother tongue and ethnic affiliation."""
    show("https://www.stat.si/popis2002/si/", r"href=\"[^\"]+\"[^>]*>[^<]{3,80}<", limit=60)
    show("https://www.stat.si/popis2002/si/rezultati/rezultati_red.asp", r"href=\"[^\"]+\"[^>]*>[^<]{3,80}<",
         limit=80)
    for q in ("ter=OBC&st=7", "ter=OBC&st=8", "ter=OBC&st=9"):
        show(f"https://www.stat.si/popis2002/si/rezultati/rezultati_red.asp?{q}", raw=1200)


def aut5() -> None:
    """Census 2001 religion and Umgangssprache by Bezirk; the 2021 religion survey."""
    show("https://www.statistik.at/statistiken/bevoelkerung-und-soziales/bevoelkerung/"
         "bevoelkerungsstand/bevoelkerung-nach-religion",
         r"href=\"[^\"]+\.(?:xlsx?|ods|csv|pdf)\"|href=\"[^\"]*(?:religion|Religion)[^\"]*\"", limit=40)
    show("https://www.statistik.at/statistiken/bevoelkerung-und-soziales/bevoelkerung/"
         "bevoelkerungsstand/bevoelkerung-nach-sprache",
         r"href=\"[^\"]+\.(?:xlsx?|ods|csv|pdf)\"|href=\"[^\"]*(?:sprach|Sprach)[^\"]*\"", limit=40)
    for url in ("https://www.statistik.at/blickgem/vz1/g10101.pdf",
                "https://www.statistik.at/blickgem/G0101/g10101.pdf",
                "https://www.statistik.at/fileadmin/pages/405/VZ2001_Hauptergebnisse_I_Oesterreich.pdf"):
        status, head, body = fetch(url)
        log(f"\n## {url}: HTTP {status}, {len(body):,} bytes, "
            f"{head.get('Content-Type') or head.get('content-type') or head.get('error', '')}")


PROBES: dict[str, Callable[[], None]] = {
    "che8": che8, "svn4": svn4, "aut5": aut5,
    "che7": che7, "nld9": nld9,
    "deu6": deu6,
    "hun13": hun13,
    "deu5": deu5,
    "hun12": hun12,
    "hun11": hun11,
    "hun10": hun10,
    "hun9": hun9, "svk9": svk9,
    "hun8": hun8, "svk8": svk8, "nld8": nld8,
    "hun7": hun7, "svk7": svk7, "nld7": nld7,
    "lie7": lie7,
    "hun6": hun6, "nld6": nld6, "svk6": svk6,
    "cze5": cze5, "hun5": hun5, "che5": che5, "svk5": svk5, "nld5": nld5, "lux5": lux5,
    "cze4": cze4, "pol4": pol4, "svk4": svk4, "hun4": hun4, "nld4": nld4, "lux4": lux4,
    "aut4": aut4, "deu4": deu4, "che4": che4,
    "che3": che3, "lie3": lie3, "pol3": pol3, "svk3": svk3, "hun3": hun3, "svn3": svn3,
    "nld3": nld3, "lux3": lux3, "cze3": cze3, "aut3": aut3, "deu3": deu3,
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
