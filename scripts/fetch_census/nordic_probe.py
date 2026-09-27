#!/usr/bin/env python3
"""Read-only probes of the Nordic and Baltic statistical offices' APIs.

The adapters for Sweden, Norway, Denmark, Finland, Iceland, Estonia, Latvia and
Lithuania each lean on a table layout -- which variables a table has, which
codes its geography holds, which years it covers. None of that is guessable
from here, and the sandbox that writes the adapters cannot reach a statistical
host, so this asks the runner and prints only what a decision needs: a table's
variables with their value counts and first and last codes, a folder's
listing, a search's hits, or a small query's first cells.

Each probe is named, and several run in one call:

    python -m scripts.fetch_census.nordic_probe --run swe_tables,nor_07459

Nothing is written; the output is the log.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) python-urllib"
TIMEOUT = 120

SCB = "https://api.scb.se/OV0104/v1/doris/en/ssd"
SSB = "https://data.ssb.no/api/v0/en/table"
STATBANK = "https://api.statbank.dk/v1"
STATFIN = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin"
HAGSTOFA = "https://px.hagstofa.is/pxen/api/v1/en"
STAT_EE = "https://andmed.stat.ee/api/v1/en/stat"
CSB = "https://data.stat.gov.lv/api/v1/en/OSP_PUB"
OSP = "https://osp-rs.stat.gov.lt/rest_xml"


def fetch(url: str, payload: Any = None, accept: str = "application/json") -> bytes:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": UA, "Accept": accept}
    if data is not None:
        headers["Content-Type"] = "application/json"
    delay = 3.0
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue
            body = exc.read()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {exc.code}: {' '.join(body.split())}") from None
    raise RuntimeError("gave up after 429s")


def get_json(url: str, payload: Any = None) -> Any:
    raw = fetch(url, payload).decode("utf-8-sig", "replace")
    return json.loads(raw)


def short(values: list[str], texts: list[str], k: int = 6) -> str:
    pairs = [f"{v}={t}" for v, t in zip(values, texts)]
    if len(pairs) <= 2 * k:
        return "; ".join(pairs)
    return "; ".join(pairs[:k]) + " ... " + "; ".join(pairs[-k:])


def px_meta(url: str, grep: str | None = None, allvals: str | None = None) -> None:
    """A PxWeb table's variables: code, label, count, and first and last values."""
    meta = get_json(url)
    print(f"  title: {meta.get('title')}")
    for var in meta.get("variables", []):
        vals, texts = var.get("values", []), var.get("valueTexts", [])
        flags = "".join(f" [{k}]" for k in ("elimination", "time") if var.get(k))
        print(f"  var {var['code']!r} ({var.get('text')}){flags}: {len(vals)} values")
        print(f"      {short(vals, texts)}")
        lens = Counter(len(v) for v in vals)
        prefixes = Counter(re.match(r"[A-Za-z\-]*", v).group(0) for v in vals)
        if len(vals) > 12:
            print(f"      code lengths {dict(sorted(lens.items()))}; "
                  f"prefixes {dict(prefixes.most_common(8))}")
        if grep:
            hits = [f"{v}={t}" for v, t in zip(vals, texts) if re.search(grep, f"{v} {t}", re.I)]
            if hits:
                print(f"      /{grep}/: {len(hits)} -- " + "; ".join(hits[:40]))
        if allvals and re.fullmatch(allvals, var["code"]):
            print("      ALL: " + "; ".join(f"{v}={t}" for v, t in zip(vals, texts)))


def px_list(url: str, grep: str | None = None) -> None:
    items = get_json(url)
    print(f"  {len(items)} items")
    for item in items:
        line = f"{item.get('id')} [{item.get('type')}] {item.get('text')}"
        if not grep or re.search(grep, line, re.I):
            print(f"    {line}")


def px_search(url: str, limit: int = 40) -> None:
    hits = get_json(url)
    print(f"  {len(hits)} hits")
    for hit in hits[:limit]:
        print(f"    {hit.get('id')} | {hit.get('path')} | {hit.get('title')}")


def px_post(url: str, query: dict[str, Any], limit: int = 30) -> None:
    body = get_json(url, query)
    dims = body.get("dimension", {})
    ids = body.get("id", [])
    print(f"  dims {ids} sizes {body.get('size')}")
    for name in ids:
        cat = dims[name]["category"]
        index = cat["index"]
        order = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
        labels = cat.get("label", {})
        print(f"    {name}: {short(order, [labels.get(c, c) for c in order], 5)}")
    values = body.get("value")
    if isinstance(values, dict):
        values = list(values.values())
    print(f"  {len(values)} values; first {values[:limit]}")
    nums = [v for v in values if isinstance(v, (int, float))]
    print(f"  sum of all {sum(nums):,.0f}")


def statbank_info(table: str, grep: str | None = None) -> None:
    info = get_json(f"{STATBANK}/tableinfo/{table}?lang=en&format=JSON")
    print(f"  {info.get('id')}: {info.get('text')} | unit {info.get('unit')} | "
          f"updated {info.get('updated')}")
    for var in info.get("variables", []):
        vals = var.get("values", [])
        ids, texts = [v["id"] for v in vals], [v["text"] for v in vals]
        print(f"  var {var['id']!r} ({var.get('text')}) elim={var.get('elimination')} "
              f"time={var.get('time')}: {len(vals)} values")
        print(f"      {short(ids, texts)}")
        if grep:
            hits = [f"{i}={t}" for i, t in zip(ids, texts) if re.search(grep, f"{i} {t}", re.I)]
            if hits:
                print(f"      /{grep}/: {len(hits)} -- " + "; ".join(hits[:40]))


def statbank_tables(grep: str) -> None:
    tables = get_json(f"{STATBANK}/tables?lang=en&format=JSON&includeInactive=true")
    print(f"  {len(tables)} tables")
    for t in tables:
        line = f"{t['id']} | {t['text']} | {t.get('firstPeriod')}-{t.get('latestPeriod')} | " \
               f"{','.join(t.get('variables', []))} | active={t.get('active')}"
        if re.search(grep, line, re.I):
            print(f"    {line}")


def sdmx_dataflows(grep: str) -> None:
    raw = fetch(f"{OSP}/dataflow/", accept="application/xml")
    root = ET.fromstring(raw)
    ns_name = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common}Name"
    flows = [el for el in root.iter() if el.tag.endswith("}Dataflow")]
    print(f"  {len(flows)} dataflows")
    shown = 0
    for flow in flows:
        names = {n.get("{http://www.w3.org/XML/1998/namespace}lang"): (n.text or "")
                 for n in flow.findall(ns_name)}
        line = f"{flow.get('id')} | {names.get('en', '')} | {names.get('lt', '')}"
        if re.search(grep, line, re.I):
            print(f"    {line}")
            shown += 1
            if shown > 80:
                print("    ...")
                break


def text(url: str, grep: str | None = None, chars: int = 1500) -> None:
    raw = fetch(url, accept="*/*").decode("utf-8", "replace")
    print(f"  {len(raw):,} characters")
    if grep:
        hits = re.findall(grep, raw, re.I)
        print(f"  /{grep}/: {len(hits)} -- {hits[:40]}")
    else:
        print("  " + " ".join(raw[:chars].split()))


def klass_codes(url: str) -> None:
    body = get_json(url)
    codes = body.get("codes", [])
    print(f"  {len(codes)} codes")
    print("  " + "; ".join(f"{c['code']}={c['name']}" for c in codes))


# ---------------------------------------------------------------------------
# The probes
# ---------------------------------------------------------------------------

PROBES: dict[str, Any] = {
    # Sweden
    "swe_tables": lambda: px_list(f"{SCB}/BE/BE0101/BE0101A"),
    "swe_befolkning": lambda: px_meta(f"{SCB}/BE/BE0101/BE0101A/BefolkningNy"),
    # Norway
    "nor_07459": lambda: px_meta(f"{SSB}/07459", grep=r"^(30|38|54|0710|0301|1804|5001) ",
                                 ),
    "nor_search_church": lambda: px_search(f"{SSB}/?query=church"),
    "nor_search_relig": lambda: px_search(f"{SSB}/?query=religious"),
    "nor_klass_2017": lambda: klass_codes(
        "https://data.ssb.no/api/klass/v1/classifications/131/codesAt.json?date=2017-06-01"),
    # Denmark
    "dnk_folk1a": lambda: statbank_info("FOLK1A"),
    "dnk_km1": lambda: statbank_info("KM1"),
    "dnk_tables": lambda: statbank_tables(r"church|relig|folkekirke|member|language|sprog"),
    # Finland
    "fin_vaerak": lambda: px_list(f"{STATFIN}/vaerak/", grep=r"relig|age|language|area|sub-region"),
    "fin_11re": lambda: px_meta(f"{STATFIN}/vaerak/11re.px", grep=r"^SK"),
    "fin_11rl": lambda: px_meta(f"{STATFIN}/vaerak/11rl.px", grep=r"^SK"),
    "fin_search_relig": lambda: px_search(f"{STATFIN}?query=religious"),
    # Iceland
    "isl_search_muni": lambda: px_search(f"{HAGSTOFA}/Ibuar?query=municipalities"),
    "isl_search_relig": lambda: px_search(f"{HAGSTOFA}/Samfelag?query=religious"),
    "isl_list": lambda: px_list(f"{HAGSTOFA}/Ibuar"),
    # Estonia
    "est_search_div": lambda: px_search(f"{STAT_EE}?query=administrative%20division"),
    "est_search_unit": lambda: px_search(f"{STAT_EE}?query=administrative%20unit"),
    "est_search_rl": lambda: px_search(f"{STAT_EE}?query=ethnic%20nationality"),
    # Latvia
    "lva_search_parish": lambda: px_search(f"{CSB}?query=parish"),
    "lva_search_terr": lambda: px_search(f"{CSB}?query=territorial%20unit"),
    "lva_search_census": lambda: px_search(f"{CSB}?query=ethnicity"),
    # Lithuania
    "ltu_flows": lambda: sdmx_dataflows(
        r"amži|age|tautyb|ethnic|kalb|langu|tikyb|relig|surašym|census"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True,
                    help="comma-separated probe names, or a prefix ending in '*'")
    args = ap.parse_args()
    names: list[str] = []
    for part in args.run.split(","):
        if part.endswith("*"):
            names += [n for n in PROBES if n.startswith(part[:-1])]
        else:
            names.append(part)
    for name in names:
        print(f"== {name}")
        try:
            PROBES[name]()
        except Exception as exc:        # a probe's failure is its answer
            print(f"  FAILED: {exc.__class__.__name__}: {exc}"[:600])
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
