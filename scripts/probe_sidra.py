#!/usr/bin/env python3
"""Ask SIDRA what a table is before reading numbers out of it.

Brazil's 27 states carried a religion composition that summed to a quarter of
each state's population, and it was read as a quirk of a sample table. It was
not. Table 10086, which the adapter had been calling "population by religion",
is a fertility table: its one variable is "women aged 12 and over who have had
live births", cross-tabulated by religion. Every figure on the map for Brazil's
religion was the religion of mothers. The table's id was guessed, the guess
answered numbers, and numbers that answer look like the right ones.

So this asks the catalogue. IBGE's aggregates API lists every table with its
name, and for any table its variables, classifications and the geographic
levels it is published at -- the three facts that decide whether a table can
be the source of a field at all. Read-only; the output is the log.

Usage:
    python -m scripts.probe_sidra --match religi
    python -m scripts.probe_sidra --table 10203
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
AGENT = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"


def get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def describe(table: str) -> None:
    meta = get(f"{BASE}/{table}/metadados")
    print(f"\n== table {meta.get('id')}: {meta.get('nome')}")
    print(f"   survey: {(meta.get('pesquisa') or '')}  |  subject: {(meta.get('assunto') or '')}")
    print(f"   periods: {meta.get('periodicidade')}")
    levels = meta.get("nivelTerritorial") or {}
    for kind, codes in levels.items():
        print(f"   levels[{kind}]: {codes}")
    print("   variables:")
    for v in meta.get("variaveis") or []:
        print(f"     v/{v.get('id'):<8} {v.get('nome')}  [{v.get('unidade')}]")
    print("   classifications:")
    for c in meta.get("classificacoes") or []:
        cats = c.get("categorias") or []
        names = [k.get("nome") for k in cats[:8]]
        print(f"     c{c.get('id')} {c.get('nome')} -- {len(cats)} categories: {names}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--match", default=None, help="substring of the table name (case-insensitive)")
    ap.add_argument("--survey", default="CD", help="pesquisa code; CD = Censo Demográfico")
    ap.add_argument("--table", action="append", default=[], help="describe this table id")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    for table in args.table:
        describe(table)

    if args.match:
        q = urllib.parse.urlencode({"pesquisa": args.survey})
        catalogue = get(f"{BASE}?{q}")
        needle = args.match.lower()
        hits = []
        for survey in catalogue:
            for agg in survey.get("agregados") or []:
                if needle in (agg.get("nome") or "").lower():
                    hits.append((survey.get("nome"), agg.get("id"), agg.get("nome")))
        print(f"\n== {len(hits)} tables in survey {args.survey!r} whose name contains {args.match!r}")
        for survey, tid, name in hits[:args.limit]:
            print(f"  {tid:<7} {name[:140]}")
        # Describe the first few, so the variables and levels are on the record.
        for _, tid, _ in hits[:6]:
            try:
                describe(str(tid))
            except Exception as err:                        # noqa: BLE001 -- reported
                print(f"   ({tid}: {type(err).__name__}: {err})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
