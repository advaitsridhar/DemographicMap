#!/usr/bin/env python3
"""Brazil -- IBGE SIDRA API (states and municipalities), 2022 Census.

SIDRA URLs read as a path of selectors::

    /values/t/{table}/n{level}/all/v/{variable}/p/{period}/c{class}/all

with ``n3`` = state (UF) and ``n6`` = municipality.  Tables used:

* **9514** resident population by sex and age (2022 Census)
* **9605** population by colour or race (cor ou raça)
* **10086** population by religion (2022 Census, released June 2025)

Brazil's *cor ou raça* is self-declared skin colour, not ethnicity: the
categories (branca, preta, parda, amarela, indígena) do not map onto US race or
UK ethnic group, and the app labels the field accordingly.

Usage:
    python -m scripts.fetch_census.ibge_sidra --level municipality
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_json, log, measure, record, shares, write_json,
)

# After ._shared, which is what puts scripts/ on the path.
import canonical_groups  # noqa: E402

SIDRA = "https://apisidra.ibge.gov.br/values"
LOCALITIES = "https://servicodados.ibge.gov.br/api/v1/localidades/{kind}"
LEVELS = {"state": ("n3", "estados", "admin1"), "municipality": ("n6", "municipios", "admin2")}

TABLES = {
    "population": {"table": "9514", "variable": "93", "classification": None, "period": "2022"},
    "colour_race": {"table": "9605", "variable": "93", "classification": "86", "period": "2022"},
}
# The 2022-census religion table's variable id was guessed and 400ed on the
# first live run, so try the plausible spellings in order and keep the first
# that answers; a wrong guess now fails fast instead of retrying for 30s.
RELIGION_VARIANTS = [
    {"table": "10086", "variable": "93", "classification": "133", "period": "2022"},
    {"table": "10086", "variable": "1000093", "classification": "133", "period": "2022"},
    {"table": "10086", "variable": "allxp", "classification": "133", "period": "2022"},
]


def sidra(table: dict[str, Any], level_code: str) -> list[dict[str, str]]:
    url = (f"{SIDRA}/t/{table['table']}/{level_code}/all"
           f"/v/{table['variable']}/p/{table['period']}")
    if table["classification"]:
        url += f"/c{table['classification']}/all"
    rows = http_json(url, timeout=300)
    # SIDRA returns the column dictionary as row 0.
    return rows[1:] if len(rows) > 1 else []


def collect(rows: list[dict[str, str]], code_key: str, label_key: str | None) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row.get(code_key)
        raw = row.get("V")
        if not code or raw in (None, "", "-", "..", "...", "X"):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        label = row.get(label_key, "Total") if label_key else "Total"
        if label.lower().startswith("total"):
            out.setdefault(code, {})["__total__"] = value
        else:
            out.setdefault(code, {})[label] = value
    return out


def englished(field: str, counts: dict[str, float]) -> dict[str, float]:
    """SIDRA's labels, in the language the rest of the map is in.

    Brazil's 25 states read "Católica Apostólica Romana 56.7%" and "Parda"
    while its own country record, which comes from the Factbook, said Roman
    Catholic and mixed. The canonical tables had folded the Portuguese to the
    right groups for as long as Brazil has been here -- but those tables reach
    the group picker, and the name a bar carries comes from the record. Same
    half-fix as Russia's, found the same way.

    An unknown label stops the run rather than reaching the map in Portuguese.
    IBGE adding a category is a thing to look at, not to pass through.
    """
    out: dict[str, float] = {}
    for label, value in counts.items():
        name = canonical_groups.translate("IBGE", field, label)
        if name is None:
            raise SystemExit(
                f"{field}: no English name for {label!r}. IBGE publishes a "
                f"category this build has never seen; add it to "
                f"canonical_groups.BRAZIL_{field.upper()} rather than letting "
                f"one Portuguese label through a translated chart.")
        out[name] = out.get(name, 0.0) + value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="municipality", choices=list(LEVELS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    level_code, locality_kind, level = LEVELS[args.level]
    log(f"ibge_sidra: {args.level} ({level_code})")

    places = {str(p["id"]): p for p in http_json(LOCALITIES.format(kind=locality_kind), timeout=180)}

    pop = collect(sidra(TABLES["population"], level_code), "D1C", None)
    race = collect(sidra(TABLES["colour_race"], level_code), "D1C", "D4N")
    religion: dict[str, dict[str, float]] = {}
    for variant in RELIGION_VARIANTS:
        try:
            religion = collect(sidra(variant, level_code), "D1C", "D4N")
            if religion:
                log(f"  religion: table {variant['table']} v/{variant['variable']} answered")
                break
        except Exception as exc:
            log(f"  religion variant v/{variant['variable']} failed ({exc})")
    if not religion:
        log("  religion unavailable from every variant; marking not_available")

    src = "IBGE, Censo Demográfico 2022 (SIDRA)"
    records: list[dict[str, Any]] = []
    for code, place in places.items():
        name = place.get("nome")
        parent = "BRA"
        if args.level == "municipality":
            uf = (place.get("microrregiao") or {}).get("mesorregiao", {}).get("UF", {})
            parent = f"BRA-{uf.get('id')}" if uf.get("id") else "BRA"
        total = pop.get(code, {}).get("__total__")
        rvals = englished("ethnicity", {k: v for k, v in race.get(code, {}).items()
                                        if k != "__total__"})
        gvals = englished("religion", {k: v for k, v in religion.get(code, {}).items()
                                       if k != "__total__"})
        records.append(record(
            f"BRA-{code}", name, level=level, parent=parent,
            codes={"ibge": code},
            population=measure(int(total), year=2022, source=src) if total else gap(NOT_AVAILABLE),
            ethnicity=shares(rvals) or gap(NOT_AVAILABLE),
            ethnicity_note=("IBGE 'cor ou raça' is self-declared skin colour (branca, preta, "
                            "parda, amarela, indígena) and is not equivalent to ethnicity "
                            "classifications used elsewhere in this dataset. The labels are "
                            "shown in English; 'Pardo' keeps Brazil's own term rather than "
                            "becoming 'Mixed', which is a different question asked elsewhere."),
            religion=shares(gvals) or gap(NOT_AVAILABLE, "IBGE 2022 religion table not returned for this locality."),
            sources=[{"field": "population/colour-race/religion", "name": src,
                      "url": f"{SIDRA}/t/{TABLES['colour_race']['table']}",
                      "license": "IBGE open data"}],
        ))
    write_json(args.out or PROCESSED / f"brazil_{args.level}.json", records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
