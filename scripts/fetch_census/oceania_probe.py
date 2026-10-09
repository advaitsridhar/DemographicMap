#!/usr/bin/env python3
"""Oceania reconnaissance: what each SDMX service and office serves, before a reader.

Read-only: nothing is written and the output is the log. Each subcommand
answers one question and prints only what decides it.

* ``flows SERVICE [--match RE]`` -- the dataflows of an SDMX service whose id
  or name matches: id, agency, version and English name.
* ``struct SERVICE AGENCY,ID,VERSION [--codes N] [--list CODELIST]`` -- the
  dataflow's dimensions in key order, each with its codelist's size and first
  codes; ``--list`` prints one codelist whole (``--grep`` filters it).
* ``data SERVICE AGENCY,ID,VERSION KEY [--rows N] [--grep RE]`` -- one
  SDMX-CSV query: the row count, each column's distinct values, and the first
  rows (or the rows matching ``--grep``).
* ``get URL [URL...] [--grep RE] [--links RE]`` -- status, type and length of
  each body, then its matching lines or links.

Services: ``pdh`` is the Pacific Community's PDH.Stat, ``abs`` the ABS Data
API, ``nz`` Stats NZ's Aotearoa Data Explorer. The last needs a key, which is
read from the environment (``new_zealand.KEY_VARS``) and sent as a header; it
is never printed, only whether one was found.

Usage:
    python -m scripts.fetch_census.oceania_probe flows pdh
    python -m scripts.fetch_census.oceania_probe struct pdh SPC,DF_POP_PROJ,3.0
    python -m scripts.fetch_census.oceania_probe data pdh SPC,DF_POP_PROJ,3.0 A.FJ..
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict

from ._shared import log

UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"
TIMEOUT = 180

SERVICES = {
    "pdh": "https://stats-sdmx-disseminate.pacificdata.org/rest",
    "abs": "https://data.api.abs.gov.au/rest",
    "nz": "https://api.data.stats.govt.nz/rest",
}
# The catalogue path each service answers: .Stat Suite takes "all/all/latest",
# the ABS lists its own agency.
CATALOGUE = {
    "pdh": "dataflow/all/all/latest",
    "abs": "dataflow/ABS?detail=allstubs",
    "nz": "dataflow/all/all/latest",
}
STRUCTURE_XML = "application/vnd.sdmx.structure+xml;version=2.1"
DATA_CSV = "application/vnd.sdmx.data+csv;version=1.0.0"
NZ_KEY_VARS = ("NZ_STATS_API", "STATS_NZ_API_KEY", "STATSNZ_API_KEY",
               "STATS_NZ_KEY", "STATSNZ_KEY", "NZ_STATS_API_KEY")
NZ_KEY_HEADER = "Ocp-Apim-Subscription-Key"


def headers_for(service: str | None, accept: str | None) -> dict[str, str]:
    out = {"User-Agent": UA, "Accept-Encoding": "identity"}
    if accept:
        out["Accept"] = accept
    if service == "nz":
        for name in NZ_KEY_VARS:
            value = (os.environ.get(name) or "").strip()
            if value:
                out[NZ_KEY_HEADER] = value
                break
    return out


def fetch(url: str, *, service: str | None = None, accept: str | None = None,
          timeout: int = TIMEOUT) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers=headers_for(service, accept))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            body = fh.read()
            # A file stored gzipped (Palau's population XML in the Archive)
            # is read as the file it holds.
            if body[:2] == b"\x1f\x8b":
                import gzip
                try:
                    body = gzip.decompress(body)
                except OSError:
                    pass
            return fh.status, fh.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as err:
        body = err.read()[:1500] if hasattr(err, "read") else b""
        return err.code, (err.headers.get("Content-Type", "") if err.headers else ""), body
    except Exception as exc:  # noqa: BLE001 - a probe reports, never raises
        return -1, type(exc).__name__, str(exc).encode()[:500]


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def english(node: ET.Element, child: str = "Name") -> str:
    names = [n for n in node if local(n.tag) == child]
    for n in names:
        if n.get("{http://www.w3.org/XML/1998/namespace}lang", "en") == "en":
            return " ".join((n.text or "").split())
    return " ".join((names[0].text or "").split()) if names else ""


def cmd_flows(service: str, match: str | None) -> None:
    url = f"{SERVICES[service]}/{CATALOGUE[service]}"
    status, ctype, body = fetch(url, service=service, accept=STRUCTURE_XML)
    log(f"{url}\n  HTTP {status} {ctype} {len(body):,} bytes")
    if status != 200:
        log("  " + body[:600].decode("utf-8", "replace"))
        return
    root = ET.fromstring(body)
    pattern = re.compile(match, re.I) if match else None
    rows = []
    for node in root.iter():
        if local(node.tag) != "Dataflow":
            continue
        fid, agency, version = node.get("id"), node.get("agencyID"), node.get("version")
        name = english(node)
        if pattern and not (pattern.search(fid or "") or pattern.search(name)):
            continue
        rows.append((fid, agency, version, name))
    log(f"  {len(rows)} dataflows" + (f" matching {match!r}" if match else ""))
    for fid, agency, version, name in sorted(rows):
        log(f"  {agency},{fid},{version}  {name[:150]}")


def parse_structure(body: bytes) -> tuple[list[tuple[int, str, str]],
                                         dict[str, "OrderedDict[str, str]"], dict[str, str]]:
    """(dimensions as (position, id, codelist id), codelists, constraint notes)."""
    root = ET.fromstring(body)
    dims: list[tuple[int, str, str]] = []
    lists: dict[str, OrderedDict[str, str]] = {}
    for node in root.iter():
        tag = local(node.tag)
        if tag in ("Dimension", "TimeDimension"):
            ref = ""
            for sub in node.iter():
                if local(sub.tag) == "Enumeration":
                    for r in sub:
                        if local(r.tag) == "Ref":
                            ref = r.get("id", "")
            pos = int(node.get("position") or 0)
            dims.append((pos, node.get("id", ""), ref))
        elif tag == "Codelist":
            codes: OrderedDict[str, str] = OrderedDict()
            for code in node:
                if local(code.tag) == "Code":
                    codes[code.get("id", "")] = english(code)
            lists[node.get("id", "")] = codes
    # Content constraints say which codes actually carry data.
    allowed: dict[str, str] = {}
    for node in root.iter():
        if local(node.tag) != "KeyValue":
            continue
        values = [v.text or "" for v in node if local(v.tag) == "Value"]
        allowed[node.get("id", "")] = f"{len(values)} constrained"
    dims.sort()
    return dims, lists, allowed


def cmd_struct(service: str, flow: str, codes: int, show: str | None,
               grep: str | None) -> None:
    agency, fid, version = flow.split(",")
    url = f"{SERVICES[service]}/dataflow/{agency}/{fid}/{version}?references=all"
    status, ctype, body = fetch(url, service=service, accept=STRUCTURE_XML)
    log(f"{url}\n  HTTP {status} {ctype} {len(body):,} bytes")
    if status != 200:
        log("  " + body[:600].decode("utf-8", "replace"))
        return
    dims, lists, allowed = parse_structure(body)
    pattern = re.compile(grep, re.I) if grep else None
    if show:
        values = lists.get(show)
        if values is None:
            log(f"  no codelist {show!r}; have {sorted(lists)}")
            return
        log(f"  codelist {show}: {len(values)} codes")
        for cid, name in values.items():
            if pattern and not (pattern.search(cid) or pattern.search(name)):
                continue
            log(f"    {cid:>14}  {name[:120]}")
        return
    for pos, did, ref in dims:
        values = lists.get(ref, OrderedDict())
        note = allowed.get(did, "")
        log(f"  [{pos}] {did}  codelist={ref} ({len(values)} codes) {note}")
        for cid, name in list(values.items())[:codes]:
            log(f"        {cid:>14}  {name[:100]}")


def cmd_data(service: str, flow: str, key: str, rows: int, grep: str | None,
             params: str | None, distinct: int) -> None:
    agency, fid, version = flow.split(",")
    url = f"{SERVICES[service]}/data/{agency},{fid},{version}/{key}"
    if params:
        url += "?" + params
    status, ctype, body = fetch(url, service=service, accept=DATA_CSV)
    log(f"{url}\n  HTTP {status} {ctype} {len(body):,} bytes")
    if status != 200:
        log("  " + body[:800].decode("utf-8", "replace"))
        return
    text = body.decode("utf-8-sig", "replace")
    table = list(csv.DictReader(io.StringIO(text)))
    log(f"  {len(table):,} rows; columns {list(table[0]) if table else []}")
    if not table:
        log("  " + text[:500])
        return
    for column in table[0]:
        values: OrderedDict[str, int] = OrderedDict()
        for row in table:
            values[row.get(column) or ""] = values.get(row.get(column) or "", 0) + 1
        sample = ", ".join(list(values)[:distinct])
        log(f"  {column}: {len(values)} distinct: {sample[:600]}")
    pattern = re.compile(grep, re.I) if grep else None
    shown = 0
    for row in table:
        line = " | ".join(f"{v}" for v in row.values())
        if pattern and not pattern.search(line):
            continue
        log("    " + line[:400])
        shown += 1
        if shown >= rows:
            break


def cmd_get(urls: list[str], chars: int, grep: str | None, links: str | None,
            context: int, rows: int) -> None:
    for url in urls:
        status, ctype, body = fetch(url)
        log(f"== {url}\n  HTTP {status} {ctype} {len(body):,} bytes")
        text = body.decode("utf-8", "replace")
        if links:
            pattern = re.compile(links, re.I)
            seen = []
            for href in re.findall(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', text, re.I):
                full = urllib.parse.urljoin(url, href)
                if pattern.search(full) and full not in seen:
                    seen.append(full)
            log(f"  {len(seen)} links matching {links!r}")
            for href in seen[:rows]:
                log("    " + href)
        if grep:
            pattern = re.compile(grep, re.I)
            shown = 0
            for m in pattern.finditer(text):
                a, b = max(0, m.start() - context), min(len(text), m.end() + context)
                log("    ..." + " ".join(text[a:b].split()) + "...")
                shown += 1
                if shown >= rows:
                    break
            log(f"  {shown} matches shown for {grep!r}")
        if not links and not grep:
            log("  " + " ".join(text[:chars].split()))


def cmd_xlsx(url: str, sheets: list[str], first: int, last: int, width: int,
             grep: str | None, cols: int) -> None:
    """Rows ``first``..``last`` of named sheets of a workbook (all sheets if none)."""
    import openpyxl
    status, ctype, body = fetch(url)
    log(f"== {url}\n  HTTP {status} {ctype} {len(body):,} bytes")
    if status != 200:
        return
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    pattern = re.compile(grep, re.I) if grep else None
    for sheet in book.worksheets:
        if sheets and sheet.title not in sheets and sheet.title.replace(" ", "_") not in sheets:
            continue
        log(f"  -- {sheet.title!r}")
        for n, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if n < first:
                continue
            if n > last:
                break
            cells = ["" if c is None else str(c)[:width] for c in row[:cols]]
            while cells and cells[-1] == "":
                cells.pop()
            line = " | ".join(cells)
            if pattern and not pattern.search(line):
                continue
            if line:
                log(f"    {n:>4}: {line}")


def cmd_csv(url: str, columns: list[str], rows: int, grep: str | None) -> None:
    """Chosen columns of a CSV, one row per line (all columns' names first)."""
    import csv
    status, ctype, body = fetch(url)
    log(f"== {url}\n  HTTP {status} {ctype} {len(body):,} bytes")
    if status != 200:
        return
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig", "replace")))
    log("  columns: " + ", ".join(reader.fieldnames or []))
    pattern = re.compile(grep, re.I) if grep else None
    shown = 0
    for row in reader:
        line = " | ".join(str(row.get(c, "")) for c in columns)
        if pattern and not pattern.search(line):
            continue
        log(f"    {line}")
        shown += 1
        if shown >= rows:
            break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("flows")
    f.add_argument("service", choices=sorted(SERVICES))
    f.add_argument("--match")
    s = sub.add_parser("struct")
    s.add_argument("service", choices=sorted(SERVICES))
    s.add_argument("flow")
    s.add_argument("--codes", type=int, default=12)
    s.add_argument("--list")
    s.add_argument("--grep")
    d = sub.add_parser("data")
    d.add_argument("service", choices=sorted(SERVICES))
    d.add_argument("flow")
    d.add_argument("key")
    d.add_argument("--rows", type=int, default=20)
    d.add_argument("--grep")
    d.add_argument("--params")
    d.add_argument("--distinct", type=int, default=15)
    g = sub.add_parser("get")
    g.add_argument("urls", nargs="+")
    g.add_argument("--chars", type=int, default=1500)
    g.add_argument("--grep")
    g.add_argument("--links")
    g.add_argument("--context", type=int, default=120)
    g.add_argument("--rows", type=int, default=60)
    x = sub.add_parser("xlsx")
    x.add_argument("url")
    x.add_argument("--sheet", action="append", default=[],
                   help="a sheet to print (repeatable; write a space as an underscore)")
    x.add_argument("--first", type=int, default=1)
    x.add_argument("--last", type=int, default=60)
    x.add_argument("--width", type=int, default=40)
    x.add_argument("--cols", type=int, default=40)
    x.add_argument("--grep")
    c = sub.add_parser("csv")
    c.add_argument("url")
    c.add_argument("--col", action="append", default=[])
    c.add_argument("--rows", type=int, default=300)
    c.add_argument("--grep")
    args = ap.parse_args()
    if args.cmd == "csv":
        cmd_csv(args.url, args.col, args.rows, args.grep)
        return 0
    if args.cmd == "xlsx":
        cmd_xlsx(args.url, args.sheet, args.first, args.last, args.width, args.grep, args.cols)
        return 0
    if args.cmd == "flows":
        cmd_flows(args.service, args.match)
    elif args.cmd == "struct":
        cmd_struct(args.service, args.flow, args.codes, args.list, args.grep)
    elif args.cmd == "data":
        cmd_data(args.service, args.flow, args.key, args.rows, args.grep,
                 args.params, args.distinct)
    else:
        cmd_get(args.urls, args.chars, args.grep, args.links, args.context, args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
