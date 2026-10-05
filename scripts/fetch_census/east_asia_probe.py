#!/usr/bin/env python3
"""Read-only probes for East Asia's statistical offices.

China, Taiwan, Japan, the two Koreas and Mongolia publish in ways that have to
be looked at before a reader is written: pages in GBK and Big5, CSVs in cp949,
forms whose field names are only in the page's own markup, a register's open
data API keyed by dataset and month, and a PxWeb database. ``east_probe``
(the generic probe) reads workbooks, Wayback listings and JSON; this adds what
it cannot do -- decode a page in the charset it declares, list a form's
fields, POST a form and read the CSV it answers in its own encoding, walk a
PxWeb node, and ask Taiwan's household-register API for a dataset.

Nothing is written and nothing is committed but the log. Every argument is one
whitespace-free token, as the workflow splits its command on whitespace.

Subcommands:

    page URL [--encoding E] [--links REGEX] [--grep REGEX] [--wayback TS|latest]
        A page decoded in the charset it declares (or E): its links whose
        label or address match REGEX, or the text around each REGEX match,
        or the start of its text.
    form URL [--encoding E] [--options N]
        Every form on a page: its action and method, and every input,
        select and textarea in it with its value, and a select's options.
    post URL --field NAME=VALUE ... [--encoding E] [--rows N] [--save PATH]
        POST the fields as a form and describe the answer: a CSV's first
        rows in E, a workbook's sheets, or a page's text.
    pxweb URL [--rows N]
        A PxWeb API node: a folder's entries, or a table's variables with
        their value counts and first values.
    ris DATASET,... --periods PERIOD,... [--rows N]
        Taiwan's household-register open data API
        (www.ris.gov.tw/rs-opendata/api/v1/datastore/DATASET/PERIOD): each
        dataset's answer for each period, its first record's keys and values.
    kosis ORG,TABLE [--encoding ko|en] [--field NAME=VALUE ...] [--grep REGEX]
        KOSIS's table viewer walked with one cookie jar, as a browser walks
        it: statHtml.do, the right-hand frame its script submits, and every
        form or frame that one names; each step's endpoints, forms and status.
    nlsc LEVEL
        Every drawn Taiwanese unit's label point (site/data/LEVEL/TWN.units.json)
        put to the National Land Surveying and Mapping Center's point query
        (api.nlsc.gov.tw/other/TownVillagePointQuery1/LON/LAT), one line each:
        shape id, the point, and the county and township the NLSC places it in.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ._shared import http_get

UA = ("DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
      "python-urllib")
CDX = "https://web.archive.org/cdx/search/cdx"
RIS = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/{dataset}/{period}"


def charset_of(blob: bytes, default: str = "utf-8") -> str:
    head = blob[:4000].decode("ascii", "replace")
    m = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9_-]+)", head, re.I)
    if not m:
        return default
    name = m.group(1).lower()
    return {"gb2312": "gb18030", "gbk": "gb18030", "big5": "big5hkscs",
            "euc-kr": "cp949", "ks_c_5601-1987": "cp949"}.get(name, name)


def decode(blob: bytes, encoding: str | None) -> str:
    enc = encoding or charset_of(blob)
    return blob.decode(enc, "replace").lstrip("﻿")


def latest(url: str) -> str | None:
    query = urllib.parse.urlencode({"url": url, "output": "json", "filter": "statuscode:200",
                                    "fl": "timestamp", "limit": "-1"})
    rows = json.loads(http_get(f"{CDX}?{query}", cache=False, retries=2, timeout=90) or "[]")
    return rows[-1][0] if len(rows) > 1 else None


def fetch(url: str, wayback: str | None = None, aia: bool = False) -> bytes:
    """``aia`` repairs a server that sends its leaf certificate without the
    intermediate (ws.dgbas.gov.tw is one): common.http_get fetches the missing
    link from the certificate's own Authority Information Access extension and
    verifies against it plus the public roots. It never skips the check."""
    if wayback:
        stamp = latest(url) if wayback == "latest" else wayback
        if not stamp:
            raise SystemExit(f"no capture of {url}")
        url = f"https://web.archive.org/web/{stamp}id_/{url}"
        print(f"  via {url}")
    blob = http_get(url, binary=True, cache=False, retries=2, timeout=180, aia=aia)
    assert isinstance(blob, bytes)
    return blob


def plain(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"(?is)<[^>]+>", " ", fragment)).split())


def cmd_page(args: argparse.Namespace) -> None:
    blob = fetch(args.target, args.wayback)
    text = decode(blob, args.encoding)
    print(f"  {len(blob):,} bytes, charset {args.encoding or charset_of(blob)}")
    if args.links:
        match = re.compile(args.links, re.I)
        shown = 0
        for href, label in re.findall(
                r"""(?is)<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", text):
            label = plain(label)
            if not (match.search(href) or match.search(label)):
                continue
            print(f"  link: {label[:100]!r} -> {urllib.parse.urljoin(args.target, href)}")
            shown += 1
            if shown >= args.rows:
                break
        print(f"  ({shown} links shown)")
    if args.grep:
        for m in list(re.finditer(args.grep, text, re.I))[:args.rows]:
            s = max(0, m.start() - args.context)
            print("  ~ " + " ".join(text[s:m.end() + args.context].split()))
    if not args.links and not args.grep:
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        print("  text: " + plain(body)[:args.bytes])


def attrs(tag: str) -> dict[str, str]:
    return {k.lower(): html.unescape(v2 if v2 else v3)
            for k, v2, v3 in re.findall(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""", tag)}


def cmd_form(args: argparse.Namespace) -> None:
    blob = fetch(args.target, args.wayback)
    text = decode(blob, args.encoding)
    forms = list(re.finditer(r"(?is)<form\b([^>]*)>(.*?)</form>", text))
    print(f"  {len(blob):,} bytes, {len(forms)} forms")
    for i, form in enumerate(forms):
        a = attrs(form.group(1))
        print(f"  form {i}: name={a.get('name')!r} id={a.get('id')!r} "
              f"action={a.get('action')!r} method={a.get('method')!r}")
        body = form.group(2)
        for tag in re.finditer(r"(?is)<input\b([^>]*)>", body):
            t = attrs(tag.group(1))
            print(f"    input {t.get('name')!r} type={t.get('type', 'text')!r} "
                  f"value={t.get('value', '')[:60]!r} id={t.get('id')!r}")
        for sel in re.finditer(r"(?is)<select\b([^>]*)>(.*?)</select>", body):
            t = attrs(sel.group(1))
            options = re.findall(r"(?is)<option\b([^>]*)>(.*?)</option>", sel.group(2))
            shown = ", ".join(f"{attrs(o).get('value', '')!r}:{plain(label)[:24]}"
                              for o, label in options[:args.options])
            print(f"    select {t.get('name')!r} id={t.get('id')!r} {len(options)} options: "
                  f"{shown}")
        for area in re.finditer(r"(?is)<textarea\b([^>]*)>", body):
            print(f"    textarea {attrs(area.group(1)).get('name')!r}")


def describe(blob: bytes, args: argparse.Namespace, ctype: str = "") -> None:
    print(f"  {len(blob):,} bytes, type {ctype!r}, begins {blob[:12]!r}")
    if blob[:2] == b"PK" or blob[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):
        from .east_probe import describe_book
        describe_book(blob, "answer", argparse.Namespace(
            grep=args.grep, indent=False, sheets=args.sheets, sheet_match=None,
            start=0, rows=args.rows, cols=args.cols, width=args.width, after=0))
        return
    text = decode(blob, args.encoding)
    if "<html" in text[:600].lower():
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        print("  page: " + plain(body)[:args.bytes])
        return
    if text.lstrip().startswith(("{", "[")):
        print("  json: " + text[:args.bytes])
        return
    rows = list(csv.reader(io.StringIO(text)))
    print(f"  csv: {len(rows)} rows; first row {len(rows[0]) if rows else 0} columns")
    grep = re.compile(args.grep, re.I) if args.grep else None
    shown = 0
    for i, row in enumerate(rows):
        line = " | ".join(c.strip()[:args.width] for c in row[:args.cols])
        if grep and i > 1 and not grep.search(line):
            continue
        print(f"    r{i}: {line}")
        shown += 1
        if shown >= args.rows:
            break


def cmd_get(args: argparse.Namespace) -> None:
    """A file -- workbook, CSV, JSON or page -- described as ``post`` describes
    an answer."""
    describe(fetch(args.target, args.wayback, aia=args.aia), args)


def cmd_post(args: argparse.Namespace) -> None:
    fields = []
    for f in args.field:
        name, _, value = f.partition("=")
        fields.append((name, urllib.parse.unquote_plus(value)))
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(args.target, data=data, method="POST", headers={
        "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        blob = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        disp = resp.headers.get("Content-Disposition", "")
    print(f"  answered {ctype!r} {disp!r}")
    describe(blob, args, ctype)


def cmd_pxweb(args: argparse.Namespace) -> None:
    blob = fetch(args.target)
    data = json.loads(decode(blob, "utf-8"))
    if isinstance(data, list):
        print(f"  folder: {len(data)} entries")
        for row in data[:args.rows]:
            print(f"    {row.get('type')} {row.get('id')!r}: {str(row.get('text'))[:110]}"
                  + (f" (updated {row.get('updated')})" if row.get("updated") else ""))
        return
    print(f"  table: {data.get('title')!r}")
    for var in data.get("variables", []):
        values, texts = var.get("values", []), var.get("valueTexts", [])
        pairs = ", ".join(f"{v}={t[:28]}" for v, t in list(zip(values, texts))[:args.cols])
        print(f"    {var.get('code')!r} ({var.get('text')!r}) {len(values)} values: {pairs}")


def cmd_ris(args: argparse.Namespace) -> None:
    datasets = args.target.split(",")
    periods = (args.periods or "").split(",")
    for dataset in datasets:
        for period in periods:
            url = RIS.format(dataset=dataset, period=period)
            try:
                blob = http_get(url, binary=True, cache=False, retries=1, timeout=90)
            except Exception as exc:  # noqa: BLE001
                print(f"  {dataset}/{period}: failed {exc!r}")
                continue
            assert isinstance(blob, bytes)
            try:
                data = json.loads(blob.decode("utf-8", "replace"))
            except ValueError:
                print(f"  {dataset}/{period}: {len(blob):,} bytes, not JSON: {blob[:80]!r}")
                continue
            records = data.get("responseData") or data.get("result", {}).get("records") or []
            print(f"  {dataset}/{period}: {data.get('responseCode')} "
                  f"{data.get('responseMessage')!r} {len(records)} records "
                  f"(totalPage {data.get('totalPage')}, totalDataSize {data.get('totalDataSize')})")
            for rec in records[:args.rows]:
                print("    " + json.dumps(rec, ensure_ascii=False)[:args.bytes])


KOSIS = "https://kosis.kr/statHtml/"
DO = re.compile(r"[\w/.-]*?\b(\w+\.do)\b")


def form_fields(text: str, name: str) -> dict[str, str]:
    """The hidden inputs of the form called ``name`` (or with that id)."""
    for form in re.finditer(r"(?is)<form\b([^>]*)>(.*?)</form>", text):
        a = attrs(form.group(1))
        if name in (a.get("name"), a.get("id")):
            return {t.get("name"): t.get("value", "")
                    for t in (attrs(i.group(1))
                              for i in re.finditer(r"(?is)<input\b([^>]*)>", form.group(2)))
                    if t.get("name")}
    return {}


def cmd_kosis(args: argparse.Namespace) -> None:
    """KOSIS's table viewer walked the way the browser walks it, with one
    cookie jar: statHtml.do, then the right-hand frame its script submits
    (right_layout.do, from the page's own iframeform plus the fields its
    script sets), then each form or frame that one names. Every step prints
    its status and size, the .do endpoints its markup and script name, its
    forms, and the text around ``--grep``. Nothing is guessed past what the
    previous page names."""
    import http.cookiejar
    org, tbl = args.target.split(",")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    lang = args.encoding or "ko"

    def step(url: str, fields: dict[str, str] | None, referer: str | None) -> str:
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        headers = {"User-Agent": UA}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        try:
            with opener.open(req, timeout=120) as resp:
                blob = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            print(f"  {url}: HTTP {exc.code} {exc.reason}")
            return ""
        except Exception as exc:  # noqa: BLE001
            print(f"  {url}: failed {exc!r}")
            return ""
        text = decode(blob, "utf-8")
        print(f"  {'POST' if data is not None else 'GET'} {url} -> {status}, {len(blob):,} bytes,"
              f" cookies {sorted(c.name for c in jar)}")
        print(f"    endpoints: {sorted(set(DO.findall(text)))[:args.rows]}")
        for form in re.finditer(r"(?is)<form\b([^>]*)>(.*?)</form>", text):
            a = attrs(form.group(1))
            names = [attrs(i.group(1)).get("name")
                     for i in re.finditer(r"(?is)<input\b([^>]*)>", form.group(2))]
            print(f"    form {a.get('name') or a.get('id')!r} action={a.get('action')!r} "
                  f"inputs={[n for n in names if n][:args.cols]}")
        for src in re.findall(r"""(?is)<iframe\b[^>]*src\s*=\s*["']([^"']*)["']""", text):
            print(f"    iframe {src!r}")
        if args.grep:
            for m in list(re.finditer(args.grep, text, re.I))[:args.options]:
                s = max(0, m.start() - args.context)
                print("    ~ " + " ".join(text[s:m.end() + args.context].split()))
        return text

    first_url = f"{KOSIS}statHtml.do?orgId={org}&tblId={tbl}&language={lang}&conn_path=I2"
    first = step(first_url, None, None)
    if not first:
        return
    frame = form_fields(first, "iframeform") or form_fields(first, "ParamInfo")
    frame.update({"orgId": org, "tblId": tbl, "tblSe": "", "tblNm": "", "query": "",
                  "tabYn": "", "language": lang})
    for f in args.field:
        name, _, value = f.partition("=")
        frame[name] = urllib.parse.unquote_plus(value)
    print(f"    right frame fields: {sorted(frame)[:40]}")
    second = step(f"{KOSIS}right_layout.do", frame, first_url)
    if not second:
        return
    # Whatever the right frame submits or frames next, with its own fields.
    for form in re.finditer(r"(?is)<form\b([^>]*)>(.*?)</form>", second):
        a = attrs(form.group(1))
        action = a.get("action") or ""
        if not action or "login" in action.lower() or "oneid" in action.lower():
            continue
        fields = form_fields(second, a.get("name") or a.get("id") or "")
        fields.update({"orgId": org, "tblId": tbl, "language": lang})
        step(urllib.parse.urljoin(f"{KOSIS}right_layout.do", action), fields,
             f"{KOSIS}right_layout.do")
    for src in re.findall(r"""(?is)<iframe\b[^>]*src\s*=\s*["']([^"']+)["']""", second):
        if src.startswith(("javascript", "about")):
            continue
        step(urllib.parse.urljoin(f"{KOSIS}right_layout.do", html.unescape(src)), None,
             f"{KOSIS}right_layout.do")


NLSC = "https://api.nlsc.gov.tw/other/TownVillagePointQuery1/{lon}/{lat}"


def cmd_nlsc(args: argparse.Namespace) -> None:
    import time
    from pathlib import Path
    site = Path(__file__).resolve().parents[2] / "site" / "data" / args.target / "TWN.units.json"
    units = json.loads(site.read_text(encoding="utf-8"))
    print(f"  {len(units)} units in {site.name}")
    for unit in units:
        lon, lat = unit["point"]
        url = NLSC.format(lon=f"{lon:.6f}", lat=f"{lat:.6f}")
        try:
            blob = http_get(url, binary=True, cache=False, retries=2, timeout=60)
            text = plain(decode(blob, "utf-8"))
        except Exception as exc:  # noqa: BLE001
            text = f"failed {exc!r}"
        print(f"  {unit['id']}|{lon:.6f}|{lat:.6f}|{unit['name']}|{text}")
        time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["page", "form", "post", "get", "pxweb", "ris", "nlsc",
                                    "kosis"])
    ap.add_argument("target", nargs="+")
    ap.add_argument("--encoding")
    ap.add_argument("--wayback")
    ap.add_argument("--aia", action="store_true",
                    help="complete a missing intermediate certificate from its AIA extension")
    ap.add_argument("--links")
    ap.add_argument("--grep")
    ap.add_argument("--context", type=int, default=120)
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--cols", type=int, default=14)
    ap.add_argument("--width", type=int, default=24)
    ap.add_argument("--sheets", type=int, default=2)
    ap.add_argument("--bytes", type=int, default=1500)
    ap.add_argument("--options", type=int, default=12)
    ap.add_argument("--field", action="append", default=[])
    ap.add_argument("--periods")
    args = ap.parse_args()
    for target in args.target:
        print(f"== {args.cmd} {target}")
        args.target = target
        try:
            {"page": cmd_page, "form": cmd_form, "post": cmd_post, "get": cmd_get,
             "pxweb": cmd_pxweb,
             "ris": cmd_ris, "nlsc": cmd_nlsc, "kosis": cmd_kosis}[args.cmd](args)
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} {exc.reason}: "
                  + " ".join(exc.read()[:300].decode("utf-8", "replace").split()))
        except SystemExit as exc:
            print(f"  stopped: {exc}")
        except Exception as exc:  # noqa: BLE001 - a probe reports, it does not stop
            print(f"  failed: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
