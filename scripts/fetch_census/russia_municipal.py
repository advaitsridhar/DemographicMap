#!/usr/bin/env python3
"""The 2020 Russian census by municipal district and urban okrug.

Volume 1, table 5 of the census (ЧИСЛЕННОСТЬ НАСЕЛЕНИЯ РОССИИ, ФЕДЕРАЛЬНЫХ
ОКРУГОВ, СУБЪЕКТОВ ... МУНИЦИПАЛЬНЫХ ОБРАЗОВАНИЙ) counts everyone by sex for
every municipal formation as it stood on 1 October 2021: the urban okrugs,
municipal districts and municipal okrugs of each subject, and the settlements
inside them. The first of those tiers is what the map's second level draws,
and this adapter writes each one's count and its men per hundred women.

**What the map draws is not always what the census counted.** The boundary
file's Russian second level is a mix of vintages: Moscow Oblast still has the
districts it abolished in 2015-2019 beside some of the urban okrugs that
replaced them; many oblasts have converted districts into municipal okrugs
since, sometimes merging a district with the town it surrounded. A census
unit is bound to a polygon only when all of these hold:

- the two name the same place: the census's Cyrillic name agrees with the
  polygon's own Cyrillic name, or with the Russian label of the Wikidata item
  the polygon is already linked to, or -- where neither exists -- its
  romanisation agrees with the polygon's romanised name;
- they are the same kind of place: a district (the census's "Xский
  муниципальный район / округ", or an okrug made from one) against a
  "District"/"Rayon"/"район" polygon, a city's urban okrug against a polygon
  named for the city;
- nothing else in the subject claims either of them (one to one);
- an okrug that the census made from a district and its town is not bound
  when the boundary file still draws that town as a polygon of its own: its
  count covers two polygons and belongs to neither.

Wikidata is the name crosswalk here and nothing more: it supplies a Russian
spelling for a polygon the boundary file romanised. No figure comes from it.

Everything not bound is logged, both sides, with the reason.

Usage:
    python -m scripts.fetch_census.russia_municipal --fetch   # runner: workbook + labels
    python -m scripts.fetch_census.russia_municipal           # bind and write
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import PROCESSED, RAW, log, measure, read_json, record, write_json
from . import russia

import fetch_wikidata  # noqa: E402  (scripts/ is on the path via _shared)

TABLE = "Tom1_tab-5_VPN-2020.xlsx"
CAPTURE = "20260901210517"
LANDING = ("https://rosstat.gov.ru/vpn/2020/"
           "Tom1_Chislennost_i_razmeshchenie_naseleniya")
SOURCE = ("Федеральная служба государственной статистики (Rosstat), "
          "Всероссийская перепись населения 2020 года, Том 1, таблица 5: "
          "Численность населения ... муниципальных образований, retrieved via "
          f"the Internet Archive capture of {CAPTURE[:4]}-{CAPTURE[4:6]}-"
          f"{CAPTURE[6:8]}")
YEAR = 2021

SITE = PROCESSED.parent.parent / "site" / "data"
LABELS = RAW / "wikidata_points" / "RUS_admin2_labels.json"
OUT = "russia_municipal.json"


# ---------------------------------------------------------------------------
# The workbook


def units(blob: bytes) -> dict[str, dict[str, Any]]:
    """{subject: {total, men, women, units}} from Volume 1's table 5.

    The sheet says which rows sit inside which only by indent: a subject at
    indent 0 (as are the country and the federal districts), its urban
    okrugs, municipal districts and municipal okrugs at indent 1, their urban
    and rural populations and settlements deeper. A formation's towns are
    kept with it ("г. Старый Оскол"), because whether the boundary file draws
    one of them separately decides whether the formation can be bound at all.
    """
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    sheet = book.worksheets[0]
    out: dict[str, dict[str, Any]] = {}
    block: dict[str, Any] | None = None
    current: dict[str, Any] | None = None
    for row in sheet.iter_rows():
        cell = row[0]
        name = " ".join(str(cell.value or "").split())
        if not name:
            continue
        depth = int(cell.alignment.indent or 0) if cell.alignment else 0
        values = [russia.number(c.value) for c in row[1:4]]
        if depth == 0:
            key = russia.AGE_NAMES.get(russia.dashes(name), russia.dashes(name))
            key = next((s for s in russia.SUBJECTS if russia.dashes(s) == key), key)
            if key in out:
                raise SystemExit(f"russia_municipal: {name!r} opens two blocks")
            block = out[key] = {"total": values[0], "men": values[1],
                                "women": values[2], "units": []}
            current = None
            continue
        if block is None:
            continue
        if depth == 1:
            current = {"name": name, "total": values[0], "men": values[1],
                       "women": values[2], "towns": []}
            block["units"].append(current)
            continue
        if current is not None:
            for town in re.findall(r"\bг\.\s*([^,;()]+)", name):
                current["towns"].append(" ".join(town.split()))
    book.close()
    return out


# ---------------------------------------------------------------------------
# Wikidata as a spelling crosswalk


LABEL_QUERY = """
SELECT ?item ?ru ?en ?oktmo ?gone WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item rdfs:label ?ru . FILTER(LANG(?ru) = "ru") }
  OPTIONAL { ?item rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?item wdt:P764 ?oktmo . }
  OPTIONAL { ?item wdt:P576 ?gone . }
}
"""


def fetch_labels() -> None:
    """The Russian label, OKTMO code and dissolution date of every linked item."""
    shapes = json.loads((SITE / "admin2" / "RUS.units.json").read_text())
    qids = sorted({u["wikidata"] for u in shapes if u.get("wikidata")})
    got: dict[str, dict[str, Any]] = {}
    for i in range(0, len(qids), 300):
        chunk = qids[i:i + 300]
        rows = fetch_wikidata.sparql(
            LABEL_QUERY % " ".join(f"wd:{q}" for q in chunk), cache=False, retries=2)
        for r in rows:
            qid = r["item"]["value"].rsplit("/", 1)[-1]
            entry = got.setdefault(qid, {"ru": None, "en": None, "oktmo": [],
                                         "dissolved": None})
            if r.get("ru"):
                entry["ru"] = r["ru"]["value"]
            if r.get("en"):
                entry["en"] = r["en"]["value"]
            if r.get("oktmo") and r["oktmo"]["value"] not in entry["oktmo"]:
                entry["oktmo"].append(r["oktmo"]["value"])
            if r.get("gone"):
                entry["dissolved"] = r["gone"]["value"][:10]
        log(f"  labels: {len(got)} of {len(qids)} items after {i + len(chunk)}")
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    LABELS.write_text(json.dumps(got, ensure_ascii=False, indent=0, sort_keys=True))
    log(f"  wrote {LABELS} ({len(got)} items)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help="fetch the workbook and the items' Russian labels")
    args = ap.parse_args()
    blob = russia.workbook(TABLE, CAPTURE)
    if args.fetch:
        fetch_labels()
        table = units(blob)
        n = sum(len(v["units"]) for v in table.values())
        log(f"  {TABLE}: {n} first-tier formations in {len(table)} blocks")
        return 0
    raise SystemExit("russia_municipal: binding is not written yet")


if __name__ == "__main__":
    raise SystemExit(main())
