#!/usr/bin/env python3
"""Burkina Faso: religion by region, 5e RGPH 2019.

INSD's *Volume des tableaux statistiques* of the fifth census prints
Tableau I.22, the resident population of each of the thirteen regions by
religion in percent, with the region's population in the last column. The
shares are applied to that population to give counts, and the thirteen
populations must sum to the printed national figure. The census publishes
the principal language spoken by milieu only, not by region, and no
ethnicity, so those fields are untouched. The thirteen regions carried
Afrobarometer survey shares for religion; the census replaces them.

Usage:
    python -m scripts.fetch_census.burkina
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_text  # noqa: E402

OUT = "burkina_region.json"
YEAR = 2019
URL = ("https://www.insd.bf/sites/default/files/2024-06/"
       "Volume%20des%20tableaux%20statistiques_%205e%20RGPH.pdf")
SOURCE = ("INSD, Cinquième Recensement Général de la Population et de l'Habitation (RGPH 2019), "
          "Volume des tableaux statistiques, Tableau I.22")
LICENCE = "Official statistics publication of the Institut National de la Statistique et de la Démographie"

REGIONS = ["Boucle du Mouhoun", "Cascades", "Centre", "Centre-Est", "Centre-Nord", "Centre-Ouest",
           "Centre-Sud", "Est", "Hauts-Bassins", "Nord", "Plateau Central", "Sahel", "Sud-Ouest"]
RELIGIONS = ["Animist", "Islam", "Catholic", "Protestant", "Other religion", "No religion"]
NOTE = ("Tableau I.22: religion of the resident population in the six classes the census "
        "prints (Animiste, Musulman, Catholique, Protestant, Autre, Sans religion), shares "
        "to one decimal applied to the region's printed population.")
ROW = re.compile(r"^(" + "|".join(re.escape(r) for r in sorted(REGIONS + ["Burkina Faso"], key=len,
                                                              reverse=True))
                 + r")\s+((?:\d+(?:,\d+)?\s+){6})((?:\d{1,3}\s*)+)$")


def read(text: str) -> dict[str, tuple[int, dict[str, float]]]:
    """{region: (population, {religion: percent})} from Tableau I.22."""
    for page in text.split(PAGE_BREAK):
        if "Tableau I.22" not in page:
            continue
        if not re.search(r"Région\s+Animiste\s+Musulman\s+Catholique\s+Protestant\s+Autre\s+"
                         r"Sans religion\s+Ensemble", page):
            continue
        out: dict[str, tuple[int, dict[str, float]]] = {}
        for line in page.splitlines():
            m = ROW.match(line.strip())
            if not m:
                continue
            pcts = [float(t.replace(",", ".")) for t in m.group(2).split()]
            pop = int(m.group(3).replace(" ", ""))
            if abs(sum(pcts) - 100) > 0.35:
                raise SystemExit(f"burkina: {m.group(1)} shares sum to {sum(pcts):.1f}")
            out[m.group(1)] = (pop, dict(zip(RELIGIONS, pcts)))
        missing = sorted(set(REGIONS + ["Burkina Faso"]) - set(out))
        if missing:
            raise SystemExit(f"burkina: Tableau I.22 lacks rows for {missing}")
        national = out.pop("Burkina Faso")
        total = sum(p for p, _ in out.values())
        if total != national[0]:
            raise SystemExit(f"burkina: regions sum to {total:,} against a printed {national[0]:,}")
        for label, printed in national[1].items():
            rebuilt = sum(p * v[label] for p, v in out.values()) / total
            if abs(rebuilt - printed) > 0.15:
                raise SystemExit(f"burkina: {label} rebuilt from the regions is {rebuilt:.2f} "
                                 f"against a printed {printed}")
        return out
    raise SystemExit("burkina: no page carries Tableau I.22 with its column heads")


def build(text: str) -> list[dict[str, Any]]:
    table = read(text)
    src = [{"field": "religion", "name": SOURCE, "url": URL, "license": LICENCE}]
    from common import slugify
    records = []
    for region in REGIONS:
        pop, pcts = table[region]
        counts = {k: v * pop / 100 for k, v in pcts.items() if v}
        records.append(record(
            f"BFA-{slugify(region)}", region, level="admin1", parent="BFA", country="BFA",
            sources=src, religion=shares(counts, total=pop), religion_year=YEAR,
            religion_note=f"{SOURCE}. {NOTE}"))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=None, help="a saved probe_pdf dump instead of the PDF")
    args = ap.parse_args()
    log(f"burkina: {SOURCE}")
    text = Path(args.text).read_text(encoding="utf-8") if args.text else fetch_text(URL)
    records = build(text)
    log(f"  {len(records)} regions")
    if len(records) != 13:
        raise SystemExit(f"burkina: expected 13 regions, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
