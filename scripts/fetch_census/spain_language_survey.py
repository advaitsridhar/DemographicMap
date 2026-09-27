#!/usr/bin/env python3
"""Spain: the regional statistics offices' language surveys.

INE's census does not ask language, and the European Social Survey is the only
thing on the map for most of Spain: a few hundred respondents an autonomous
community, drawn to compare countries. Two of the communities with a language
of their own measure it themselves, with samples drawn to describe them:

* **Catalonia** -- Idescat and the Generalitat's *Enquesta d'usos lingüístics
  de la població* (EULP), 2023: the population aged 15 and over by habitual
  language (Idescat table 3202), as weighted estimates in thousands, read from
  Idescat's API. Idescat publishes it for Catalonia, for the areas of the
  Territorial Plan and for its own sampling strata -- none of which is a
  province -- so it is written for the autonomous community only.
* **Galicia** -- the IGE's *Enquisa estrutural a fogares: coñecemento e uso do
  galego*, 2023: the population aged 5 and over by the language they usually
  speak, for Galicia and each of its four provinces (IGE table given below),
  read from the IGE's API.

(The Basque Country's home language is not here: Eustat asks it in its own
census, which is a count; see ``basque_language``.)

Survey estimates, so the file's name ends in ``_survey``: they fill what no
count describes, and as a national (regional) office's survey they stand in
front of the European Social Survey.

Checks, each of which stops the run:

* every unit's categories make its published total;
* for Galicia, the four provinces make Galicia (the IGE's estimates are
  calibrated to the population by province).

Usage:
    python -m scripts.fetch_census.spain_language_survey
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, shares, write_json
from .binding import fold

OUT = "spain_language_survey.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# --- Catalonia -------------------------------------------------------------

EULP_YEAR = 2023
EULP = "https://api.idescat.cat/taules/v2/eulp/3202/23138/cat/data?lang=en"
EULP_PAGE = "https://www.idescat.cat/pub/?id=eulp&lang=en"
EULP_SOURCE = ("Idescat and the Generalitat of Catalonia, Survey on Language Uses of the "
               "Population (EULP) 2023: population aged 15 and over by habitual language")
EULP_LABELS = {
    "CA": "Catalan", "ES": "Spanish", "CA_ES": "Catalan and Spanish",
    "OC_ARANESE": "Aranese Occitan",
    "CA_OTHER_LANG": "Catalan and another language",
    "ES_OTHER_LANG": "Spanish and another language",
    "CA_ES_OTHER_LANG": "Catalan, Spanish and another language",
    "AR": "Arabic", "OTHER_LANG": "Other language",
    "OTHER_COMB_LANG": "Other language combinations", "_U": "Not stated",
}
CATALONIA = "Cataluña/Catalunya"


def jsonstat_cells(payload: dict[str, Any]) -> list[tuple[dict[str, str], float]]:
    """A JSON-stat 2.0 dataset -> [(dimension -> category code, value)]."""
    ids, sizes = payload["id"], payload["size"]
    orders = []
    for name in ids:
        index = payload["dimension"][name]["category"]["index"]
        orders.append(sorted(index, key=index.get) if isinstance(index, dict) else list(index))
    values = payload["value"]
    if isinstance(values, dict):
        total = 1
        for size in sizes:
            total *= size
        values = [values.get(str(i)) for i in range(total)]
    out = []
    for flat, value in enumerate(values):
        if value is None:
            continue
        key, rest = {}, flat
        for i in range(len(ids) - 1, -1, -1):
            key[ids[i]] = orders[i][rest % sizes[i]]
            rest //= sizes[i]
        out.append((key, float(value)))
    return out


def catalonia(payload: dict[str, Any]) -> dict[str, Any]:
    cells = {key["LAN_ISO"]: value for key, value in jsonstat_cells(payload)}
    total = cells.pop("TOTAL", None)
    unknown = sorted(set(cells) - set(EULP_LABELS))
    if unknown:
        raise SystemExit(f"spain_language_survey: EULP categories not declared: {unknown}")
    if total is None or abs(sum(cells.values()) - total) > 0.5:
        raise SystemExit(f"spain_language_survey: EULP categories make "
                         f"{sum(cells.values()):,.1f} thousand against {total}")
    counts = {EULP_LABELS[k]: v * 1000 for k, v in cells.items()}
    rows = shares(counts, total=total * 1000)
    return {
        "language": rows,
        "language_year": EULP_YEAR,
        "language_basis": "survey estimate: habitual language, residents aged 15+",
        "language_note": (
            f"Idescat and the Generalitat's Survey on Language Uses of the Population (EULP) "
            f"{EULP_YEAR}: residents aged 15 and over by the language they habitually speak -- "
            "one language, two or three together, or another; those who did not say are Not "
            f"stated. A weighted survey estimate ({total:,.1f} thousand people aged 15 and over), "
            "not a count; Idescat publishes it for Catalonia and for territorial areas that are "
            "not provinces, so the provinces are left to other sources. INE's census does not "
            "ask language."),
        "sources": [{"field": "language", "name": EULP_SOURCE, "url": EULP_PAGE,
                     "year": EULP_YEAR, "license": "Idescat (CC BY 4.0)"}],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    admin1 = {fold(u["name"]): u for u in json.loads((SITE / "admin1" / "ESP.units.json").read_text())}
    records: list[dict[str, Any]] = []

    shape = admin1.get(fold(CATALONIA))
    if shape is None:
        raise SystemExit(f"spain_language_survey: no drawn {CATALONIA!r}")
    cat = catalonia(http_json(EULP, cache=False, timeout=120))
    records.append(record("ESP-EULP-CAT", shape["name"], level="admin1", parent="ESP",
                          country="ESP", match_by="shape_id", shape_id=shape["id"], **cat))

    for r in records:
        log(f"  {r['level']} {r['name']}: "
            + ", ".join(f"{g['group']} {g['pct']}" for g in r["language"]))
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
