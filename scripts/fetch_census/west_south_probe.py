#!/usr/bin/env python3
"""Read-only probes for the west and south of Europe (PRT, ESP, ITA, MLT, GBR,
IRL and the microstates): what each office's API or site actually serves,
before an adapter relies on it.

Nothing is written. The output is the log, and it is kept short on purpose:
the lines needed to decide, never the whole page.

Subcommands:

* ``url URL... [--grep a,b] [--chars N]`` -- status, type and size of each URL,
  then the lines of its text (tags stripped) that carry a term, or its first
  characters.
* ``links URL... [--grep a,b]`` -- the links on a page whose address or text
  carries a term.
* ``json URL [--path a.0.b] [--depth N]`` -- the shape of a JSON answer.
* ``ine-pt CODE|FROM-TO...`` -- INE Portugal indicator metadata (title,
  dimensions, last period) for each code or range of codes.
* ``ine-es [--ops a,b] [--tables a,b]`` -- INE Spain's operations whose name
  carries a term, and their tables whose name carries another.
* ``nomis [--search a,b] [--dataset NM_x_1]`` -- Nomis datasets whose name
  carries a term, or one dataset's dimensions and codes.

Usage:
    python -m scripts.fetch_census.west_south_probe url https://example.org --grep census
"""

from __future__ import annotations

import argparse
import html
import json
import re
from typing import Any

from ._shared import http_get, http_json, log


def fetch(url: str, *, binary: bool = False, timeout: int = 120) -> bytes | str:
    return http_get(url, cache=False, retries=2, timeout=timeout, binary=binary)


def text_of(body: str) -> list[str]:
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|td|th)>", "\n", body)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return [re.sub(r"\s+", " ", line).strip() for line in body.splitlines()
            if line.strip()]


def terms(value: str) -> list[str]:
    return [t.strip().lower() for t in (value or "").split(",") if t.strip()]


def cmd_url(args: argparse.Namespace) -> int:
    needles = terms(args.grep)
    for url in args.url:
        log(f"== {url}")
        try:
            raw = fetch(url, binary=True, timeout=args.timeout)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {type(err).__name__}: {str(err)[:300]}")
            continue
        assert isinstance(raw, bytes)
        log(f"  {len(raw):,} bytes; starts {raw[:8]!r}")
        if raw[:4] == b"%PDF" or raw[:2] == b"PK":
            log("  binary (PDF or zip); use probe_pdf / probe_xlsx")
            continue
        body = raw.decode(args.charset or "utf-8", errors="replace")
        lines = (text_of(body) if "<" in body[:2000] and not args.raw
                 else body.splitlines())
        if needles:
            hits = [i for i, line in enumerate(lines)
                    if any(n in line.lower() for n in needles)]
            log(f"  {len(lines)} lines, {len(hits)} with {needles}")
            shown = 0
            for i in hits:
                log(f"  {i:>5}: {lines[i][:args.width]}")
                shown += 1
                if shown >= args.limit:
                    break
        else:
            log("  " + "\n  ".join(line[:args.width] for line in lines)[:args.chars])
    return 0


def cmd_links(args: argparse.Namespace) -> int:
    needles = terms(args.grep)
    for url in args.url:
        log(f"== {url}")
        try:
            body = fetch(url, timeout=args.timeout)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {type(err).__name__}: {str(err)[:300]}")
            continue
        assert isinstance(body, str)
        found = re.findall(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body)
        shown = 0
        for href, label in found:
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()
            if needles and not any(n in (href + " " + label).lower() for n in needles):
                continue
            log(f"  {label[:90]:<90} {href[:200]}")
            shown += 1
            if shown >= args.limit:
                break
        log(f"  {shown} of {len(found)} links shown")
    return 0


def shape(value: Any, depth: int, indent: str = "  ") -> None:
    if isinstance(value, dict):
        log(f"{indent}{{{len(value)} keys}}")
        if depth <= 0:
            log(f"{indent}  keys: {list(value)[:30]}")
            return
        for key in list(value)[:40]:
            item = value[key]
            if isinstance(item, (dict, list)):
                log(f"{indent}{key}:")
                shape(item, depth - 1, indent + "  ")
            else:
                log(f"{indent}{key}: {str(item)[:160]!r}")
    elif isinstance(value, list):
        log(f"{indent}[{len(value)} items]")
        if value and depth > 0:
            shape(value[0], depth - 1, indent + "  ")
            if len(value) > 1:
                log(f"{indent}  last: {json.dumps(value[-1], ensure_ascii=False)[:200]}")
    else:
        log(f"{indent}{str(value)[:200]!r}")


def cmd_json(args: argparse.Namespace) -> int:
    for url in args.url:
        log(f"== {url}")
        try:
            payload = http_json(url, cache=False, retries=2, timeout=args.timeout)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {type(err).__name__}: {str(err)[:300]}")
            continue
        for part in [p for p in (args.path or "").split(".") if p]:
            payload = payload[int(part)] if isinstance(payload, list) else payload[part]
        if args.pluck and isinstance(payload, list):
            keys = [k for k in args.pluck.split(",") if k]
            for item in payload[:args.limit]:
                if isinstance(item, dict):
                    log("  " + " | ".join(str(item.get(k))[:120] for k in keys))
            log(f"  {len(payload)} items")
            continue
        shape(payload, args.depth)
    return 0


# ---------------------------------------------------------------------------
# INE Portugal
# ---------------------------------------------------------------------------

INE_PT_META = "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp?varcd={code}&lang=PT"


def ine_pt_codes(specs: list[str]) -> list[str]:
    codes: list[str] = []
    for spec in specs:
        if "-" in spec:
            lo, hi = spec.split("-")
            codes.extend(f"{n:07d}" for n in range(int(lo), int(hi) + 1))
        else:
            codes.append(spec.zfill(7))
    return codes


def cmd_ine_pt(args: argparse.Namespace) -> int:
    needles = terms(args.grep)
    for code in ine_pt_codes(args.codes):
        try:
            payload = http_json(INE_PT_META.format(code=code), cache=False, retries=1,
                                timeout=60)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {code}: {type(err).__name__}: {str(err)[:120]}")
            continue
        entry = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(entry, dict) or not entry.get("IndicadorNome"):
            if args.verbose:
                log(f"  {code}: {str(payload)[:160]}")
            continue
        name = entry.get("IndicadorNome", "")
        if needles and not any(n in name.lower() for n in needles):
            continue
        last = entry.get("UltimoPref") or entry.get("DataUltimoAtualizacao") or ""
        log(f"  {code}: {name[:230]} | last {last} | {entry.get('Periodic', '')}")
        if args.dims:
            dims = entry.get("Dimensoes") or {}
            for dim in (dims.get("Descricao_Dim") or [])[:8]:
                log(f"      dim {dim.get('dim_num')}: {dim.get('abrv')}")
            # Categoria_Dim is a list of one-key dicts, "Dim_Num2_1111601":
            # [{...}], one per category; grouped by the dimension they are of.
            grouped: dict[str, list[dict[str, Any]]] = {}
            for dim in dims.get("Categoria_Dim") or []:
                for key, cats in dim.items():
                    cats = cats if isinstance(cats, list) else [cats]
                    grouped.setdefault("_".join(key.split("_")[:2]), []).extend(cats)
            for key, cats in grouped.items():
                sample = ", ".join(f"{c.get('cat_id')}={c.get('categ_dsg')}"
                                   for c in cats[:args.dims])
                log(f"      {key} ({len(cats)}): {sample[:400]}")
    return 0


# ---------------------------------------------------------------------------
# INE Spain
# ---------------------------------------------------------------------------

INE_ES = "https://servicios.ine.es/wstempus/js/ES"


def cmd_ine_es(args: argparse.Namespace) -> int:
    ops = http_json(f"{INE_ES}/OPERACIONES_DISPONIBLES", cache=False, timeout=120)
    wanted = terms(args.ops)
    chosen = [o for o in ops if any(w in (o.get("Nombre") or "").lower() for w in wanted)]
    for op in chosen:
        log(f"== op {op.get('Id')} {op.get('Cod_IOE')} {op.get('Codigo')}: {op.get('Nombre')}")
        try:
            tables = http_json(f"{INE_ES}/TABLAS_OPERACION/{op['Id']}", cache=False,
                               timeout=120)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {type(err).__name__}: {str(err)[:200]}")
            continue
        want_t = terms(args.tables)
        for table in tables:
            name = table.get("Nombre") or ""
            if want_t and not all(w in name.lower() for w in want_t):
                continue
            log(f"  table {table.get('Id')}: {name[:200]} | {table.get('Anyo_Periodo_ini')}"
                f"-{table.get('Ultima_Modificacion')}")
    return 0


# ---------------------------------------------------------------------------
# Nomis
# ---------------------------------------------------------------------------

NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"


def cmd_nomis(args: argparse.Namespace) -> int:
    for needle in terms(args.search):
        url = f"{NOMIS}/def.sdmx.json?search=*{needle.replace(' ', '*')}*"
        try:
            payload = http_json(url, cache=False, timeout=180)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {needle}: {type(err).__name__}: {str(err)[:200]}")
            continue
        families = (payload.get("structure", {}).get("keyfamilies") or {}).get("keyfamily") or []
        log(f"== search {needle!r}: {len(families)} datasets")
        for fam in families[:args.limit]:
            name = fam.get("name", {})
            name = name.get("value") if isinstance(name, dict) else str(name)
            log(f"  {fam.get('id'):<12} {str(name)[:150]}")
    for dataset in args.dataset or []:
        try:
            payload = http_json(f"{NOMIS}/{dataset}/def.sdmx.json", cache=False, timeout=180)
            fam = payload["structure"]["keyfamilies"]["keyfamily"][0]
            log(f"== {dataset}: {fam.get('name', {}).get('value')}")
            for dim in fam["components"]["dimension"]:
                log(f"  dimension {dim.get('conceptref')} ({dim.get('codelist')})")
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  {dataset}: {type(err).__name__}: {str(err)[:200]}")
        for dim in [d.strip() for d in args.codes.split(",") if d.strip()]:
            try:
                payload = http_json(f"{NOMIS}/{dataset}/{dim}.def.sdmx.json", cache=False,
                                    timeout=180)
                lists = payload["structure"]["codelists"]["codelist"]
                for codelist in lists:
                    codes = codelist.get("code", [])
                    log(f"  {dim}: {len(codes)} codes")
                    for code in codes[:args.limit]:
                        desc = (code.get("description") or {}).get("value", "")
                        log(f"    {code.get('value')}: {desc[:120]}")
            except Exception as err:                # noqa: BLE001 -- reported
                log(f"  {dataset}/{dim}: {type(err).__name__}: {str(err)[:200]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("url")
    p.add_argument("url", nargs="+")
    p.add_argument("--grep", default="")
    p.add_argument("--chars", type=int, default=1500)
    p.add_argument("--width", type=int, default=220)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--charset", default=None)
    p.add_argument("--raw", action="store_true", help="keep the markup")
    p.set_defaults(run=cmd_url)

    p = sub.add_parser("links")
    p.add_argument("url", nargs="+")
    p.add_argument("--grep", default="")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--timeout", type=int, default=90)
    p.set_defaults(run=cmd_links)

    p = sub.add_parser("json")
    p.add_argument("url", nargs="+")
    p.add_argument("--path", default="")
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--pluck", default="", help="fields to print for each item of a list")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(run=cmd_json)

    p = sub.add_parser("ine-pt")
    p.add_argument("codes", nargs="+")
    p.add_argument("--grep", default="")
    p.add_argument("--dims", type=int, default=0)
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(run=cmd_ine_pt)

    p = sub.add_parser("ine-es")
    p.add_argument("--ops", default="continua,padr")
    p.add_argument("--tables", default="")
    p.set_defaults(run=cmd_ine_es)

    p = sub.add_parser("nomis")
    p.add_argument("--search", default="")
    p.add_argument("--dataset", action="append")
    p.add_argument("--codes", default="geography")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(run=cmd_nomis)

    args = ap.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
