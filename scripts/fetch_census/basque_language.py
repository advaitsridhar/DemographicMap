#!/usr/bin/env python3
"""The Basque Country: language spoken at home, by historical territory, from
Eustat's 2021 Population and Housing Statistics.

Spain's census (INE) does not ask language, and the Basque Country's three
provinces carried no language composition at all -- the European Social
Survey reaches the autonomous community and not its provinces. Eustat, the
Basque statistics office, runs its own census, the *Estadística de Población
y Viviendas*, every five years, and it records for everyone aged 2 and over the
language spoken at home: Basque, Spanish, both, or another. Eustat publishes it
by historical territory -- Araba/Álava, Bizkaia and Gipuzkoa, the three
provinces the map draws -- and for the community (table ``cepv3_lhc04``,
1991-2021), read here from Eustat's PxWeb API for 2021.

A count of the whole population aged 2 and over, not a survey, so the file is
an ordinary one: it replaces the European Social Survey's estimate for the
community.

Labels: Euskera "Basque", Castellano "Spanish", Las dos "Basque and Spanish",
Otra "Other language".

Checks, each of which stops the run:

* every territory's four languages make its published total;
* the three territories make the community, language by language.

Usage:
    python -m scripts.fetch_census.basque_language
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, dated, log, record, shares, write_json
from .binding import fold
from .pxweb import http_json, unstack

OUT = "basque_language.json"
YEAR = 2021
TABLE = "https://www.eustat.eus/bankupx/api/v1/es/DB/PX_010152_cepv3_lhc04.px"
PAGE = "https://www.eustat.eus/bankupx/pxweb/es/DB/-/PX_010152_cepv3_lhc04.px"
SOURCE = ("Eustat, Estadística de Población y Viviendas 2021: population aged 2 and over "
          "by language spoken at home (cepv3_lhc04)")
LICENCE = "Eustat (CC BY 4.0)"
SITE = PROCESSED.parent.parent / "site" / "data"

TERRITORIES = {"01": "Alava", "48": "Bizkaia", "20": "Gipuzkoa"}   # Eustat code -> drawn
COMMUNITY = ("00", "País Vasco/Euskadi")
LANGUAGES = {"20": "Basque", "30": "Spanish", "40": "Basque and Spanish", "50": "Other language"}
TOTAL = "10"

NOTE = ("Eustat's Population and Housing Statistics (the Basque Country's own census), "
        f"{YEAR}: everyone aged 2 and over by the language spoken at home -- Basque, Spanish, "
        "both, or another. A count, not a survey. INE's census of Spain does not ask language.")


def query() -> dict[str, Any]:
    def item(code: str, values: list[str]) -> dict[str, Any]:
        return {"code": code, "selection": {"filter": "item", "values": values}}
    return {"query": [
        item("territorio histórico", [COMMUNITY[0], *TERRITORIES]),
        item("lengua", [TOTAL, *LANGUAGES]),
        item("lugar de nacimiento", ["00"]),
        item("periodo", [str(YEAR)]),
    ], "response": {"format": "json-stat2"}}


def tabulate(cells: list[tuple[dict[str, tuple[str, str]], float]]) -> dict[str, dict[str, float]]:
    """territory code -> {language code: persons}."""
    out: dict[str, dict[str, float]] = {}
    for key, value in cells:
        out.setdefault(key["territorio histórico"][0], {})[key["lengua"][0]] = value
    return out


def check(table: dict[str, dict[str, float]]) -> None:
    for code in [COMMUNITY[0], *TERRITORIES]:
        row = table.get(code)
        if not row or TOTAL not in row:
            raise SystemExit(f"basque_language: no total for territory {code}")
        made = sum(row.get(lang, 0.0) for lang in LANGUAGES)
        if abs(made - row[TOTAL]) > 0.5:
            raise SystemExit(f"basque_language: territory {code}: languages make {made:,.0f} "
                             f"against its total {row[TOTAL]:,.0f}")
    for lang in [TOTAL, *LANGUAGES]:
        made = sum(table[code].get(lang, 0.0) for code in TERRITORIES)
        if abs(made - table[COMMUNITY[0]].get(lang, 0.0)) > 0.5:
            raise SystemExit(f"basque_language: the territories make {made:,.0f} of language "
                             f"{lang}, the community {table[COMMUNITY[0]].get(lang)}")


def fields(row: dict[str, float]) -> dict[str, Any]:
    rows = shares({LANGUAGES[k]: v for k, v in row.items() if k in LANGUAGES}, total=row[TOTAL])
    return {
        "language": rows,
        "language_year": dated(rows, YEAR),
        "language_note": NOTE,
        "sources": [{"field": "language", "name": SOURCE, "url": PAGE, "year": YEAR,
                     "license": LICENCE}],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    table = tabulate(unstack(http_json(TABLE, query())))
    check(table)
    admin1 = {fold(u["name"]): u for u in json.loads((SITE / "admin1" / "ESP.units.json").read_text())}
    admin2 = {fold(u["name"]): u for u in json.loads((SITE / "admin2" / "ESP.units.json").read_text())}
    community = admin1.get(fold(COMMUNITY[1]))
    if community is None:
        raise SystemExit(f"basque_language: no drawn {COMMUNITY[1]!r}")
    records = [record("ESP-EUSTAT-LANG-00", community["name"], level="admin1", parent="ESP",
                      country="ESP", match_by="shape_id", shape_id=community["id"],
                      codes={"eustat": COMMUNITY[0]}, **fields(table[COMMUNITY[0]]))]
    for code, name in TERRITORIES.items():
        shape = admin2.get(fold(name))
        if shape is None or shape.get("parent") != community["id"]:
            raise SystemExit(f"basque_language: {name} is not drawn inside {COMMUNITY[1]}")
        records.append(record(f"ESP-EUSTAT-LANG-{code}", shape["name"], level="admin2",
                              parent="ESP", country="ESP", match_by="shape_id",
                              shape_id=shape["id"], codes={"eustat": code, "ine_province": code},
                              **fields(table[code])))
    for r in records:
        log(f"  {r['name']}: " + ", ".join(f"{g['group']} {g['pct']}" for g in r["language"]))
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
