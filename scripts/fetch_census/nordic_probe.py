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
            if shown > 400:
                print("    ...")
                break


def sdmx_series(flow: str, query: str = "", limit: int = 6) -> None:
    """An OSP dataflow's series: how many, their dimensions, and a few keys."""
    raw = fetch(f"{OSP}/data/{flow}{query}", accept="application/xml")
    root = ET.fromstring(raw)
    series = [el for el in root.iter() if el.tag.endswith("Series")]
    print(f"  {len(raw):,} bytes, {len(series)} series")
    if series and not any(kv.tag.endswith("}Value") for kv in series[0].iter()):
        # Structure-specific form: the key is the Series element's attributes
        # and each Obs carries TIME_PERIOD and OBS_VALUE.
        dims2: dict[str, Counter] = {}
        for s in series:
            for k, v in s.attrib.items():
                dims2.setdefault(k, Counter())[v] += 1
        for name, values in dims2.items():
            vals = list(values)
            print(f"    dim {name}: {len(vals)} values: {vals[:15]}{' ...' if len(vals) > 15 else ''}")
        for s in series[:limit]:
            obs = [(o.get("TIME_PERIOD"), o.get("OBS_VALUE")) for o in s if o.tag.endswith("Obs")]
            print(f"    {dict(s.attrib)} -> {obs[-3:]}")
        return
    if not series:
        print("  " + " ".join(raw[:1500].decode("utf-8", "replace").split()))
    dims: dict[str, Counter] = {}
    for s in series:
        for kv in s.iter():
            if kv.tag.endswith("}Value") and kv.get("id"):
                dims.setdefault(kv.get("id"), Counter())[kv.get("value")] += 1
    for name, values in dims.items():
        vals = list(values)
        print(f"    dim {name}: {len(vals)} values: {vals[:12]}{' ...' if len(vals) > 12 else ''}")
    for s in series[:limit]:
        key = {kv.get("id"): kv.get("value") for kv in s.iter()
               if kv.tag.endswith("}Value") and kv.get("id")}
        obs = []
        for o in s.iter():
            if o.tag.endswith("}Obs"):
                d = o.find(".//{*}ObsDimension")
                v = o.find(".//{*}ObsValue")
                obs.append((d.get("value") if d is not None else None,
                            v.get("value") if v is not None else None))
        print(f"    {key} -> {obs[-3:]}")


def fin_class(year: str) -> None:
    """Statistics Finland's municipality -> sub-region key for one year: the sub-regions."""
    url = (f"https://data.stat.fi/api/classifications/v2/correspondenceTables/"
           f"kunta_1_{year}0101%23seutukunta_1_{year}0101/maps?content=data&meta=max&lang=fi")
    body = get_json(url)
    print(f"  {len(body)} maps; first: {json.dumps(body[0], ensure_ascii=False)[:1500]}")
    targets = Counter(m.get("targetLocalId") for m in body)
    print(f"  {len(targets)} sub-regions")


def isl(fn, *a, **k):
    time.sleep(6)
    return fn(*a, **k)


def sdmx_obs(flow: str, query: str = "", limit: int = 8) -> None:
    """An OSP flow in the all-dimensions form: each Obs carries its own key."""
    raw = fetch(f"{OSP}/data/{flow}{query}", accept="application/xml")
    root = ET.fromstring(raw)
    obs = [el for el in root.iter() if el.tag.endswith("}Obs")]
    print(f"  {len(raw):,} bytes, {len(obs)} observations")
    dims: dict[str, Counter] = {}
    rows = []
    for o in obs:
        key = {}
        value = None
        for el in o.iter():
            if el.tag.endswith("}Value") and el.get("id"):
                key[el.get("id")] = el.get("value")
            if el.tag.endswith("}ObsValue"):
                value = el.get("value")
        for k, v in key.items():
            dims.setdefault(k, Counter())[v] += 1
        rows.append((key, value))
    for name, values in dims.items():
        vals = list(values)
        print(f"    dim {name}: {len(vals)} values: {vals[:40]}{' ...' if len(vals) > 40 else ''}")
    for key, value in rows[:limit]:
        print(f"    {key} = {value}")


def links(url: str, grep: str, limit: int = 80) -> None:
    raw = fetch(url, accept="text/html,*/*").decode("utf-8", "replace")
    hrefs = re.findall(r"""href=["']([^"'#]+)["'][^>]*>([^<]{0,120})""", raw, re.I)
    print(f"  {len(raw):,} characters, {len(hrefs)} links")
    shown = 0
    for href, label in hrefs:
        line = f"{' '.join(label.split())} -> {urllib.parse.urljoin(url, href)}"
        if re.search(grep, line, re.I):
            print(f"    {line}")
            shown += 1
            if shown >= limit:
                break


def sdmx_codes(path: str, grep: str | None = None, limit: int = 120) -> None:
    """The codelists an OSP structure refers to: id and names of each code."""
    raw = fetch(f"{OSP}/{path}", accept="application/xml")
    root = ET.fromstring(raw)
    lists = [el for el in root.iter() if el.tag.endswith("}Codelist")]
    print(f"  {len(raw):,} bytes, {len(lists)} codelists")
    for cl in lists:
        codes = [el for el in cl if el.tag.endswith("}Code")]
        print(f"    codelist {cl.get('id')}: {len(codes)} codes")
        shown = 0
        for code in codes:
            names = {n.get("{http://www.w3.org/XML/1998/namespace}lang"): n.text
                     for n in code if n.tag.endswith("}Name")}
            line = f"{code.get('id')} = {names.get('en')} | {names.get('lt')}"
            if not grep or re.search(grep, line, re.I):
                print(f"      {line}")
                shown += 1
                if shown >= limit:
                    break


def cdx(query: str, limit: int = 60) -> None:
    """What the Wayback Machine holds under a URL prefix."""
    url = ("https://web.archive.org/cdx/search/cdx?" + query
           + f"&output=json&limit={limit}&collapse=urlkey")
    rows = get_json(url)
    print(f"  {max(len(rows) - 1, 0)} captures")
    for row in rows[1:]:
        print(f"    {row[1]} {row[2]} {row[3] if len(row) > 3 else ''} {row[4] if len(row) > 4 else ''}")


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
    # Round 8
    "r8_ltu_cdx_9601028": lambda: cdx("url=osp.stat.gov.lt/documents/10180/9601028/*", limit=200),
    "r8_ltu_cdx_10367417": lambda: cdx("url=osp.stat.gov.lt/documents/10180/10367417/*", limit=200),
    "r8_ltu_cdx_10439642": lambda: cdx("url=osp.stat.gov.lt/documents/10180/10439642/*", limit=200),
    "r8_ltu_cdx_savivald": lambda: cdx("url=osp.stat.gov.lt/documents/10180/*&filter=original:.*(?:savivald|kalb|tikyb|Tikyb|Kalb).*", limit=200),
    "r8_lva_taut": lambda: px_list("https://data.stat.gov.lv/api/v1/en/OSP_OD/tautassk/taut"),
    "r8_lva_demogr": lambda: px_list("https://data.stat.gov.lv/api/v1/en/OSP_OD/tautassk/demogr"),
    # Round 7
    "r7_ltu_cl1": lambda: sdmx_codes("codelist/LSD/savivaldybesRegdb/latest", limit=90),
    "r7_ltu_cl2": lambda: sdmx_codes("datastructure/LSD/M3010203/latest?references=children", limit=90),
    "r7_ltu_cl3": lambda: text(f"{OSP}/dataflow/LSD/S3R167_M3010203/latest?references=all", chars=1800),
    "r7_ltu_cdx": lambda: cdx("url=osp.stat.gov.lt/documents/10180/*&filter=original:.*(?:surasym|tautyb).*"),
    "r7_isl_trufelog": lambda: isl(px_list, f"{HAGSTOFA}/Samfelag/menning/5_trufelog/trufelog"),
    "r7_lva_tsk": lambda: px_list("https://data.stat.gov.lv/api/v1/en/OSP_OD/tautassk"),
    "r7_lva_tsk2021": lambda: px_search("https://data.stat.gov.lv/api/v1/en/OSP_OD?query=2021"),
    "r7_lva_ird081_units": lambda: px_meta(f"{CSB}/POP/IR/IRD/IRD081", grep=r"^LV00\d{5}"),
    "r7_est_rv0241_star": lambda: px_meta(
        f"{STAT_EE}/Lepetatud_tabelid/Rahvastik.Arhiiv/"
        "Rahvastikun%C3%A4itajad%20ja%20koosseis.%20Arhiiv/RV0241.PX", grep=r"\*|COUNTY"),
    "r7_est_rl0429_units": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel-ja-keelteoskus-murded/RL0429.PX", grep=r"OTH|COUNTY"),
    "r7_est_rl0433_units": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel-ja-keelteoskus-murded/RL0433.PX", allvals="Elukoht"),
    "r7_est_rl21434": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel/RL21434.px", grep=r"COUNTY|county|maakond"),
    "r7_est_rl21452": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "usk/RL21452.px", grep=r"COUNTY|county|maakond"),
    "r7_est_rv0222u": lambda: px_meta(
        f"{STAT_EE}/rahvastik/rahvastikunaitajad-ja-koosseis/rahvaarv-ja-rahvastiku-koosseis/RV0222U.PX"),
    # Round 6
    "r6_ltu_codes": lambda: sdmx_codes("dataflow/LSD/S3R167_M3010203/latest?references=all",
                                       grep=r"savivald|apskr|^\d\d |LT0|^00 "),
    "r6_ltu_629more": lambda: sdmx_obs("S3R629_M3010217", "?startPeriod=2025&endPeriod=2026", limit=20),
    "r6_ltu_cdx1": lambda: cdx("url=osp.stat.gov.lt/documents/10180/*&filter=original:.*(?:surasym|tautyb|Surasym).*"),
    "r6_ltu_cdx2": lambda: cdx("url=osp.stat.gov.lt/gyventoju-ir-bustu-surasymai*"),
    "r6_ltu_datagov": lambda: text("https://data.gov.lt/datasets?q=sura%C5%A1ymas",
                                   grep=r"[^\"<>]{0,80}ura[sš]ym[^\"<>]{0,80}"),
    "r6_ltu_getdata": lambda: text("https://get.data.gov.lt/datasets/gov/lsd/:ns", chars=2000),
    "r6_fin_avain": lambda: px_list("https://pxdata.stat.fi/PxWeb/api/v1/en/Kuntien_avainluvut"),
    "r6_fin_avain_q": lambda: px_search("https://pxdata.stat.fi/PxWeb/api/v1/en/Kuntien_avainluvut?query=church"),
    "r6_isl_trufelog": lambda: isl(px_list, f"{HAGSTOFA}/Samfelag/menning/5_trufelog"),
    "r6_est_usk2021": lambda: px_list(
        f"{STAT_EE}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/usk"),
    "r6_lva_od": lambda: px_list("https://data.stat.gov.lv/api/v1/en/OSP_OD"),
    "r6_lva_od_q": lambda: px_search("https://data.stat.gov.lv/api/v1/en/OSP_OD?query=language"),
    # Round 5
    "r5_ltu_203": lambda: sdmx_obs("S3R167_M3010203", "?startPeriod=2026&endPeriod=2026"),
    "r5_ltu_629": lambda: sdmx_obs("S3R629_M3010217", "?startPeriod=2026&endPeriod=2026"),
    "r5_ltu_216": lambda: sdmx_obs("S3R167_M3010216", "?startPeriod=2026&endPeriod=2026", limit=3),
    "r5_ltu_page1": lambda: links("https://osp.stat.gov.lt/gyventoju-ir-bustu-surasymai1",
                                  r"surasym|2021|xls|csv|duomen"),
    "r5_ltu_page2": lambda: links("https://osp.stat.gov.lt/2021-gyventoju-ir-bustu-surasymo-rezultatai",
                                  r"tautyb|kalb|tikyb|xls|csv|duomen"),
    "r5_ltu_datagov": lambda: text("https://data.gov.lt/datasets?q=surašymas", grep=r"[^\"<>]{0,80}surašym[^\"<>]{0,80}"),
    "r5_lva_dbs": lambda: px_list("https://data.stat.gov.lv/api/v1/en"),
    "r5_lva_ird081": lambda: px_meta(f"{CSB}/POP/IR/IRD/IRD081", allvals="AREA"),
    "r5_fin_evang": lambda: px_search(f"{STATFIN}?query=Evangelical"),
    "r5_fin_dbs": lambda: px_list("https://pxdata.stat.fi/PxWeb/api/v1/en"),
    "r5_fin_11ra_sk": lambda: px_meta(f"{STATFIN}/vaerak/11ra.px", grep=r"^SK"),
    "r5_isl_09000": lambda: isl(px_meta, f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/x_eldraefni/MAN09000.px",
                               allvals=".*"),
    "r5_isl_menning": lambda: isl(px_list, f"{HAGSTOFA}/Samfelag/menning"),
    "r5_isl_02005": lambda: isl(px_meta, f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/sveitarfelog/MAN02005.px"),
    "r5_est_rel2021": lambda: px_list(
        f"{STAT_EE}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad"),
    "r5_est_2021lang": lambda: px_list(
        f"{STAT_EE}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/rahvus-emakeel"),
    # Round 4
    "r4_ltu_210": lambda: sdmx_series("S3R167_M3010210", "?startPeriod=2026&endPeriod=2026"),
    "r4_ltu_203": lambda: sdmx_series("S3R167_M3010203", "?startPeriod=2026&endPeriod=2026", limit=3),
    "r4_ltu_629": lambda: sdmx_series("S3R629_M3010217", "?startPeriod=2026&endPeriod=2026", limit=3),
    "r4_ltu_216": lambda: sdmx_series("S3R167_M3010216", "?startPeriod=2026&endPeriod=2026", limit=3),
    "r4_ltu_215": lambda: sdmx_series("S3R167_M3010215_1", "?startPeriod=2021&endPeriod=2026", limit=3),
    "r4_ltu_162": lambda: sdmx_series("S3R162_M3010215_2", "?startPeriod=2021&endPeriod=2026", limit=3),
    "r4_ltu_flows": lambda: sdmx_dataflows(r"gyventojų ir būstų|population and housing|surašymas|census"),
    "r4_lva_ird041": lambda: px_meta(f"{CSB}/POP/IR/IRD/IRD041"),
    "r4_lva_ird031": lambda: px_meta(f"{CSB}/POP/IR/IRD/IRD031"),
    "r4_lva_home": lambda: px_search(f"{CSB}?query=home"),
    "r4_lva_root": lambda: px_list(f"{CSB}"),
    "r4_lva_pop": lambda: px_list(f"{CSB}/POP"),
    "r4_fin_11ra": lambda: px_meta(f"{STATFIN}/vaerak/11ra.px"),
    "r4_fin_passiivi": lambda: px_search(
        "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin_Passiivi?query=religious%20community"),
    "r4_isl_old": lambda: isl(px_list, f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/x_eldraefni"),
    "r4_isl_yfirlit": lambda: isl(px_list, f"{HAGSTOFA}/Ibuar/mannfjoldi/1_yfirlit"),
    "r4_isl_bak": lambda: isl(px_list, f"{HAGSTOFA}/Ibuar/mannfjoldi/3_bakgrunnur"),
    "r4_isl_root": lambda: isl(px_list, f"{HAGSTOFA}"),
    "r4_isl_samfelag": lambda: isl(px_list, f"{HAGSTOFA}/Samfelag"),
    "r4_est_rl0429": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel-ja-keelteoskus-murded/RL0429.PX", allvals="Elukoht"),
    "r4_est_rl0433": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel-ja-keelteoskus-murded/RL0433.PX"),
    "r4_est_rl0452": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "usk/RL0452.PX"),
    "r4_est_rl21429": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel/RL21429.px"),
    "r4_est_rv0241_all": lambda: px_meta(
        f"{STAT_EE}/Lepetatud_tabelid/Rahvastik.Arhiiv/"
        "Rahvastikun%C3%A4itajad%20ja%20koosseis.%20Arhiiv/RV0241.PX", grep=r"\*"),
    # Round 3
    "r3_swe_ages": lambda: px_meta(f"{SCB}/BE/BE0101/BE0101A/BefolkningCKM", allvals="Alder"),
    "r3_nor_12026": lambda: px_post(f"{SSB}/12026", {"query": [
        {"code": "KOKkommuneregion0000", "selection": {"filter": "item", "values": ["0710", "0301", "0101", "0706"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [
            "KOSmedlemmerdnk0000", "KOSmedltroslivs0000", "KOSpersoneralle0000"]}},
        {"code": "Tid", "selection": {"filter": "item", "values": ["2016", "2017", "2018"]}}],
        "response": {"format": "json-stat2"}}),
    "r3_nor_eka": lambda: px_meta(f"{SSB}/12026", grep=r"^EKA|^EAK"),
    "r3_fin_class2020": lambda: fin_class("2020"),
    "r3_fin_class2014": lambda: fin_class("2014"),
    "r3_fin_passiivi": lambda: px_search(
        "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin_Passiivi?query=religious"),
    "r3_isl_folder": lambda: isl(px_list, f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/sveitarfelog"),
    "r3_isl_2byggdir": lambda: isl(px_list, f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir"),
    "r3_isl_mann": lambda: isl(px_list, f"{HAGSTOFA}/Ibuar/mannfjoldi"),
    "r3_isl_02001": lambda: isl(px_meta, f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/sveitarfelog/MAN02001.px",
                               allvals="Sveitarf.*"),
    "r3_isl_relig": lambda: isl(px_search, f"{HAGSTOFA}/Ibuar?query=religious%20organizations"),
    "r3_est_ethfolder": lambda: px_list(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel-ja-keelteoskus-murded"),
    "r3_est_usk": lambda: px_list(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/usk"),
    "r3_est_rv0241": lambda: px_meta(
        f"{STAT_EE}/Lepetatud_tabelid/Rahvastik.Arhiiv/"
        "Rahvastikun%C3%A4itajad%20ja%20koosseis.%20Arhiiv/RV0241.PX", allvals="Haldus.*|Elukoht.*|.*[Uu]nit.*"),
    "r3_est_rv0222": lambda: px_meta(
        f"{STAT_EE}/Lepetatud_tabelid/Rahvastik.Arhiiv/"
        "Rahvastikun%C3%A4itajad%20ja%20koosseis.%20Arhiiv/RV0222.PX"),
    "r3_lva_ird": lambda: px_list(f"{CSB}/POP/IR/IRD"),
    "r3_lva_lang": lambda: px_search(f"{CSB}?query=language"),
    "r3_lva_census": lambda: px_search(f"{CSB}?query=census%202021"),
    "r3_ltu_flows": lambda: sdmx_dataflows(
        r"tautyb|gimtoji|native language|religi|tikyb|mother tongue|ethnicity|surašymo"),
    "r3_ltu_s3r167_203": lambda: sdmx_series("S3R167_M3010203", "?startPeriod=2026&endPeriod=2026"),
    "r3_ltu_s3r629": lambda: sdmx_series("S3R629_M3010217", "?startPeriod=2026&endPeriod=2026"),
    "r3_ltu_s3r0155": lambda: sdmx_series("S3R0155_M3010203_1", "?startPeriod=2026&endPeriod=2026"),
    "r3_ltu_s3r167_216": lambda: sdmx_series("S3R167_M3010216", "?startPeriod=2026&endPeriod=2026"),
    "r3_ltu_s3r167_210": lambda: sdmx_series("S3R167_M3010210", "?startPeriod=2026&endPeriod=2026"),
    # Round 2
    "r2_swe_ckm": lambda: px_meta(f"{SCB}/BE/BE0101/BE0101A/BefolkningCKM"),
    "r2_nor_kostra": lambda: px_list(f"{SSB}/kf/kf04/kirke_kostra/SBMENU12107"),
    "r2_nor_kostra2": lambda: px_list(f"{SSB}/kf/kf04/kirke_kostra/SBMENU6460"),
    "r2_nor_trosamf": lambda: px_list(f"{SSB}/kf/kf04/trosamf"),
    "r2_nor_12026": lambda: px_meta(f"{SSB}/12026", grep=r"^(0710|1804|0301|K-0301) "),
    "r2_nor_06326": lambda: px_meta(f"{SSB}/06326"),
    "r2_nor_08531": lambda: px_meta(f"{SSB}/08531"),
    "r2_nor_search_members": lambda: px_search(f"{SSB}/?query=members%20church%20municipality"),
    "r2_dnk_km6": lambda: statbank_info("KM6"),
    "r2_fin_11rf": lambda: px_meta(f"{STATFIN}/vaerak/11rf.px", grep=r"^SK"),
    "r2_fin_11rx": lambda: px_meta(f"{STATFIN}/vaerak/11rx.px"),
    "r2_fin_11rm": lambda: px_meta(f"{STATFIN}/vaerak/11rm.px", grep=r"^SK"),
    "r2_fin_class": lambda: text(
        "https://data.stat.fi/api/classifications/v2/correspondenceTables/"
        "kunta_1_20250101%23seutukunta_1_20250101/maps?content=data&meta=max&lang=fi",
        chars=800),
    "r2_isl_muni": lambda: px_list(f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/sveitarfelog"),
    "r2_isl_mann": lambda: px_list(f"{HAGSTOFA}/Ibuar/mannfjoldi"),
    "r2_isl_relig": lambda: px_search(f"{HAGSTOFA}/Ibuar?query=religious"),
    "r2_isl_02001": lambda: px_meta(f"{HAGSTOFA}/Ibuar/mannfjoldi/2_byggdir/sveitarfelog/MAN02001.px"),
    "r2_est_archive": lambda: px_list(
        f"{STAT_EE}/Lepetatud_tabelid/Rahvastik.Arhiiv/"
        "Rahvastikun%C3%A4itajad%20ja%20koosseis.%20Arhiiv"),
    "r2_est_rel2011": lambda: px_list(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad"),
    "r2_est_rl0428": lambda: px_meta(
        f"{STAT_EE}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad/"
        "rahvus-emakeel-ja-keelteoskus-murded/RL0428.PX"),
    "r2_est_search_age": lambda: px_search(f"{STAT_EE}?query=sex%20age%20administrative"),
    "r2_lva_ird081": lambda: px_meta(f"{CSB}/POP/IR/IRD/IRD081", grep=r"pag|Ain"),
    "r2_lva_rig010": lambda: px_meta(f"{CSB}/POP/IR/IRD/RIG010", grep=r"Ainaž"),
    "r2_lva_rig040": lambda: px_meta(f"{CSB}/POP/IR/IRE/RIG040", grep=r"Ainaž"),
    "r2_lva_search_age": lambda: px_search(f"{CSB}?query=single%20year"),
    "r2_ltu_flows": lambda: sdmx_dataflows(r"^S3R\d+_M301|surašym|census|Gyventojų surašymo"),
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
