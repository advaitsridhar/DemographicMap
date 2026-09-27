#!/usr/bin/env python3
"""Austria: religion by Bundesland in 2021, Statistik Austria's survey estimate.

The register-based census has carried no religion since 2011. For 2021
Statistik Austria measured religious affiliation in a sample survey and
published the result extrapolated to each Land's whole population, in
thousands to one decimal ("Bevölkerung 2021 nach ausgewählter Religions-
zugehörigkeit und Bundesland", ``neu__Religion_2021_Bundesland.ods`` on its
page "Religionsbekenntnis"). The groups are Christianity -- with the Roman
Catholic, the Evangelical (A.B. and H.B.) and the Orthodox churches named
inside it -- Islam, other religions, and no religion; they make the Land's
population.

These are survey estimates and say so in ``religion_basis``; the output is a
``*_survey.json`` file, which the build uses only where no count exists and
ranks above the cross-national European Social Survey.

Usage:
    python -m scripts.fetch_census.austria_religion
"""

from __future__ import annotations

import argparse
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from ._shared import PROCESSED, dated, http_get, log, record, shares, write_json
from .central_ages import check_sum, fold, units

DATA = "https://www.statistik.at/fileadmin/pages/439/neu__Religion_2021_Bundesland.ods"
PORTAL = ("https://www.statistik.at/statistiken/bevoelkerung-und-soziales/bevoelkerung/"
          "weiterfuehrende-bevoelkerungsstatistiken/religionsbekenntnis")
SOURCE = ("Statistik Austria, Bevölkerung 2021 nach ausgewählter Religionszugehörigkeit und "
          "Bundesland (survey estimate)")
LICENCE = "CC BY 4.0 (Statistik Austria)"
OUT = PROCESSED / "austria_religion_survey.json"
YEAR = 2021
LAENDER = ("Burgenland", "Kärnten", "Niederösterreich", "Oberösterreich", "Salzburg",
           "Steiermark", "Tirol", "Vorarlberg", "Wien")
# Row labels by how they begin; the sheet's own run past the column width.
ROWS = {"Gesamtbevölkerung": "total", "Christentum": "christian",
        "Römisch-katholisch": "Roman Catholic", "Evangelisch": "Protestant",
        "Orthodox": "Orthodox", "Islam": "Islam", "Andere Religion": "Other religion",
        "Keine": "No religion", "Keiner": "No religion"}
NS = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
      "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
NOTE = ("Statistik Austria's estimate of religious affiliation in 2021 from its sample survey, "
        "extrapolated to the Land's whole population and published in thousands to one decimal. "
        "'Other Christian' is the Christians outside the three churches the table names (Roman "
        "Catholic, Evangelical A.B. and H.B., Orthodox); 'Protestant' is the Evangelical church. "
        "A survey estimate: the register-based census has carried no religion since 2011, and "
        "the last census to ask was 2001.")


def rows_of(blob: bytes) -> list[list[str]]:
    """The first sheet's rows as text, repeated cells expanded."""
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(blob)).read("content.xml"))
    sheet = next(root.iter(f"{{{NS['table']}}}table"))
    out = []
    for row in sheet.iter(f"{{{NS['table']}}}table-row"):
        cells: list[str] = []
        for cell in row.iter(f"{{{NS['table']}}}table-cell"):
            words = " ".join("".join(p.itertext()) for p in cell.iter(f"{{{NS['text']}}}p"))
            repeat = int(cell.get(f"{{{NS['table']}}}number-columns-repeated", "1"))
            cells += [words.strip()] * min(repeat, 50)
        out.append(cells)
    return out


def thousands(text: str) -> float:
    return float(text.replace(" ", "").replace(" ", "").replace(",", ".")) * 1000


def read() -> dict[str, dict[str, float]]:
    """{Land: {row: people}} from the sheet's block in thousands."""
    rows = rows_of(http_get(DATA, binary=True, timeout=120))
    head_at = next(i for i, r in enumerate(rows) if r and r[0].startswith("Religion"))
    header = [re.sub(r"[-\s]", "", c) for c in rows[head_at]]
    columns = {}
    for land in ("Österreich", *LAENDER):
        hits = [j for j, c in enumerate(header) if c == re.sub(r"[-\s]", "", land)]
        if len(hits) != 1:
            raise SystemExit(f"austria_religion: no single column for {land}: {rows[head_at]}")
        columns[land] = hits[0]
    out: dict[str, dict[str, float]] = {land: {} for land in columns}
    for r in rows[head_at + 1:]:
        if any("Prozent" in c for c in r):
            break                       # the absolute block ends where the shares begin
        if not r or not r[0]:
            continue
        key = next((v for k, v in ROWS.items() if r[0].startswith(k)), None)
        if key is None:
            if re.search(r"\d", "".join(r[1:])):
                raise SystemExit(f"austria_religion: a row this reader does not know: {r[:3]}")
            continue
        if key in out["Österreich"]:
            raise SystemExit(f"austria_religion: {r[0]!r} met twice before the shares")
        for land, j in columns.items():
            out[land][key] = thousands(r[j])
    return out


def build() -> list[dict[str, Any]]:
    log("austria_religion: Statistik Austria, religion 2021 by Bundesland (survey estimate)")
    table = read()
    named = ("Roman Catholic", "Protestant", "Orthodox")
    for land, v in table.items():
        parts = v["christian"] + v["Islam"] + v["Other religion"] + v["No religion"]
        # published in thousands to one decimal: each figure is within 50 people
        if abs(parts - v["total"]) > 250:
            raise SystemExit(f"austria_religion: {land}: groups make {parts:,.0f} of {v['total']:,.0f}")
        v["Other Christian"] = v["christian"] - sum(v[k] for k in named)
        if v["Other Christian"] < -150:
            raise SystemExit(f"austria_religion: {land}: the named churches exceed Christianity")
    check_sum((table[land]["total"] for land in LAENDER), table["Österreich"]["total"],
              "Laender against Austria", tolerance=0.0005)
    shapes = {fold(u["name"]): u for u in units("AUT", "admin1")}
    records = []
    for land in LAENDER:
        shape = shapes.get(fold(land))
        if shape is None:
            raise SystemExit(f"austria_religion: no polygon for {land}")
        v = table[land]
        counts = {k: max(v[k], 0.0) for k in (*named, "Other Christian", "Islam",
                                              "Other religion", "No religion")}
        rows = shares(counts, total=v["total"])
        log(f"  {land}: {v['total']:,.0f}; " + ", ".join(f"{r['group']} {r['pct']}" for r in rows))
        records.append(record(
            f"AUT-REL2021-{fold(land)}", shape["name"], level="admin1", parent="AUT",
            country="AUT", match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "religion", "name": SOURCE, "url": PORTAL, "license": LICENCE,
                      "year": YEAR}],
            religion=rows, religion_year=dated(rows, YEAR),
            religion_basis="survey estimate: sample survey extrapolated to the whole population",
            religion_note=NOTE))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
