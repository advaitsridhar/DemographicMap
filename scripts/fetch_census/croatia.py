#!/usr/bin/env python3
"""Croatia: ethnicity, religion and mother tongue by županija and grad/općina,
from the 2021 census (Popis 2021) final-results workbook.

The Croatian Bureau of Statistics publishes the final results as one workbook
per geography set; the set for towns and municipalities
(``popis_2021-stanovnistvo_po_gradovima_opcinama.xlsx``, 18 MB, 24 sheets)
carries sheet "1." population by ethnicity, "2." by religion and "4." by
mother tongue. The workbook was requested on a runner and those sheets'
headers and first rows read before this was written.

**One layout, three sheets.** Each sheet has a header row that starts with
"Županija" and then, after five name columns, a count column and a percent
column per category. Every header cell is bilingual, Croatian above English
("Hrvati" / "Croats"), so the categories are read from the header rather than
declared here, and a category the bureau adds appears as its own bar rather
than vanishing. Below the header come the country, then each county's own
row (its type columns blank) followed by its towns and municipalities, whose
type ("Grad" or "Općina") and name are separate cells. A dash is a zero.

The categories partition the population, "Other", "Not declared" and
"Unknown" included, and the adapter refuses a row whose counts do not sum to
its total. Ethnicity's tail carries the census's own residual answers
(regional affiliation, a religious affiliation given as an ethnicity) as
their own bars.

**Names.** geoBoundaries names the counties in English ("Zagreb County",
"City of Zagreb", "Bjelovar-Bilogora") and the second level as the bureau
writes it, type first ("Grad Samobor", "Općina Bibinje"), which is what this
adapter composes; the county record carries the Croatian name as an alias and
each unit names its county. The workbook lists the City of Zagreb by its
seventeen city districts rather than as one unit; those are skipped and the
city is written from its own county row, since it is both a county and a
second-level shape. The boundary file has 545 shapes for 556 units and
misspells two ("Opicina Muter-Kornati"); those are declared as aliases, and
the rest of the difference is visible as unmatched rows, not papered over.

Usage:
    python -m scripts.fetch_census.croatia
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, measure, record, shares,
    write_json,
)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402

URL = ("https://podaci.dzs.hr/media/td3jvrbu/"
       "popis_2021-stanovnistvo_po_gradovima_opcinama.xlsx")
PAGE = "https://dzs.gov.hr/vijesti/objavljeni-konacni-rezultati-popisa-2021/1270"
SOURCE = "Croatian Bureau of Statistics (DZS), Census of Population, Households and Dwellings 2021, final results"
LICENCE = "DZS open data (free reuse with attribution)"
YEAR = 2021
SHEETS = {"ethnicity": "1.", "religion": "2.", "language": "4."}
EXPECTED = {"admin1": 21, "admin2": (550, 565)}
UNIT_KINDS = ("Grad", "Općina")

# The bureau's county name (column A of every sheet) -> the boundary file's.
COUNTIES = {
    "Zagrebačka": "Zagreb County",
    "Krapinsko-zagorska": "Krapina-Zagorje",
    "Sisačko-moslavačka": "Sisak-Moslavina",
    "Karlovačka": "Karlovac",
    "Varaždinska": "Varaždin",
    "Koprivničko-križevačka": "Koprivnica-Križevci",
    "Bjelovarsko-bilogorska": "Bjelovar-Bilogora",
    "Primorsko-goranska": "Primorje-Gorski Kotar",
    "Ličko-senjska": "Lika-Senj",
    "Virovitičko-podravska": "Virovitica-Podravina",
    "Požeško-slavonska": "Požega-Slavonia",
    "Brodsko-posavska": "Brod-Posavina",
    "Zadarska": "Zadar County",
    "Osječko-baranjska": "Osijek-Baranja",
    "Šibensko-kninska": "Šibenik-Knin",
    "Vukovarsko-srijemska": "Vukovar-Syrmia",
    "Splitsko-dalmatinska": "Split-Dalmatia",
    "Istarska": "Istria",
    "Dubrovačko-neretvanska": "Dubrovnik-Neretva",
    "Međimurska": "Međimurje",
    "Grad Zagreb": "City of Zagreb",
}
# The boundary file's spellings where they differ from the bureau's: its
# misspellings, its hyphen spacing, and two islands each drawn as one shape
# that is exactly one town (Cres is all of Grad Cres, Lošinj all of Grad
# Mali Lošinj). Istria's bilingual names ("Grad Buje – Buie") are aliased
# generically to their Croatian half.
UNIT_ALIASES = {
    "Općina Murter-Kornati": ["Opicina Muter-Kornati"],
    "Općina Pirovac": ["Opicina Pirovac"],
    "Grad Ivanić-Grad": ["Grad Ivanić Grad"],
    "Općina Budinščina": ["Općina Budinšćina"],
    "Općina Hrašćina": ["Općina Hraščina"],
    "Općina Lobor": ["Grad Lobor"],
    "Općina Zagorska Sela": ["Općina Zagorska sela"],
    "Općina Donji Kukuruzari": ["Općina Donji Kukuzari"],
    "Općina Hrvatska Dubica": ["Općina Hvratska Dubica"],
    "Općina Velika Pisanica": ["Općina Veliki Pisanica"],
    "Općina Malinska-Dubašnica": ["Općina Malinska - Dubašnica"],
    "Općina Okučani": ["Općina Okućani"],
    "Općina Magadenovac": ["Općina Magdenovac"],
    "Općina Kaštelir-Labinci – Castelliere-S. Domenica": ["Općina Kaštelir - Labinci"],
    "Grad Cres": ["Otok Cres"],
    "Grad Mali Lošinj": ["Otok Losinj"],
}


def unit_aliases(shown: str) -> list[str]:
    out = list(UNIT_ALIASES.get(shown, []))
    if " – " in shown:
        out.append(shown.split(" – ")[0].strip())
    return out
# The English half of a header cell, to the bar it is shown as, per field:
# "Jews" is an ethnicity on one sheet and a religion on another. Ethnicity is
# shown in the adjective form the rest of the map uses; anything not listed
# keeps the bureau's English.
LABELS = {
    "ethnicity": {
        "Croats": "Croatian", "Albanians": "Albanian", "Austrians": "Austrian",
        "Bosniacs": "Bosniak", "Bosniaks": "Bosniak", "Bulgarians": "Bulgarian",
        "Montenegrins": "Montenegrin", "Czechs": "Czech", "Hungarians": "Hungarian",
        "Macedonians": "Macedonian", "Germans": "German", "Poles": "Polish", "Roma": "Roma",
        "Romanians": "Romanian", "Russians": "Russian", "Ruthenians": "Rusyn",
        "Slovaks": "Slovak", "Slovenians": "Slovene", "Slovenes": "Slovene",
        "Serbs": "Serbian", "Italians": "Italian", "Turks": "Turkish",
        "Ukrainians": "Ukrainian", "Vlachs": "Vlach", "Jews": "Jewish", "Other": "Other",
        "Regional affiliation": "Regional affiliation",
        "Declared religion": "Religious affiliation given as ethnicity",
        "Not classified": "Not classified", "Not declared": "Not declared",
        "Unknown": "Not stated",
    },
    "religion": {
        "Catholics": "Catholic", "Orthodox": "Orthodox", "Protestants": "Protestant",
        "Other Christians": "Other Christian", "Muslims": "Islam", "Jews": "Judaism",
        "Oriental religions": "Eastern religions", "Eastern religions": "Eastern religions",
        "Other religions, movements and life philosophies": "Other religion",
        "Agnostics and sceptics": "Agnostics and sceptics", "Not religious and atheists": "No religion",
        "Not declared": "Not declared", "Unknown": "Not stated",
    },
    "language": {
        "Other languages": "Other", "Unknown": "Not stated",
    },
}
NOTES = {
    "ethnicity": ("Ethnicity (narodnost), Popis 2021, one answer per person, voluntary. The "
                  "census's residual answers (a regional affiliation, a religious affiliation "
                  "given as an ethnicity, undistributed answers) and the people who did not "
                  "declare or whose answer is unknown are kept as their own bars."),
    "religion": ("Religion (vjera), Popis 2021, one answer per person, voluntary, at the "
                 "categories the bureau publishes; agnostics, the not religious, the "
                 "undeclared and the unknown are kept as their own bars."),
    "language": ("Mother tongue (materinski jezik), Popis 2021, one answer per person, at "
                 "the languages the bureau publishes; Other and Unknown are kept."),
}


def english(cell: Any) -> str:
    """The English half of a bilingual header cell, else the whole cell, less
    a footnote mark ("Other Christians1)")."""
    text = str(cell or "").replace("\r", "").strip()
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    label = parts[-1] if parts else ""
    return re.sub(r"\s*\d\)$", "", label).strip()


def count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "").replace(".", "")
    if text in ("", "-", "–", "z", "…"):
        return 0
    return int(float(text))


def parse_sheet(rows: list[tuple[Any, ...]]) -> tuple[list[str], list[dict[str, Any]]]:
    """(category labels, units) from one sheet's rows.

    A unit is {"county": Croatian county name, "type": "Grad"/"Općina"/None,
    "name": unit name or None for the county's own row, "total": int,
    "counts": {label: int}}. The country row is skipped.
    """
    header_at = None
    for i, row in enumerate(rows):
        if row and str(row[0] or "").strip().startswith("Županija"):
            header_at = i
            break
    if header_at is None:
        raise SystemExit("croatia: no header row starting with 'Županija'")
    header = rows[header_at]
    # Count columns are every column from F whose label is not a percentage;
    # the first of them is the total.
    columns: list[tuple[int, str]] = []
    for j in range(5, len(header)):
        label = english(header[j])
        if not label or label.rstrip().endswith("%"):
            continue
        columns.append((j, label))
    if not columns or columns[0][1].lower() != "total":
        raise SystemExit(f"croatia: expected the first count column to be Total, "
                         f"read {columns[:3]}")
    total_col = columns[0][0]
    labels = [label for _, label in columns[1:]]
    units: list[dict[str, Any]] = []
    for row in rows[header_at + 1:]:
        if not row or row[0] is None:
            continue
        county = str(row[0]).strip()
        if not county or county.startswith("Republika"):
            continue
        if not isinstance(row[total_col], (int, float)) and \
                not str(row[total_col] or "").strip().replace(".", "").isdigit():
            continue                      # a footnote below the table, not a unit
        kind = str(row[1] or "").strip() or None
        name = str(row[4] or "").strip() or None
        if (kind is None) != (name is None):
            raise SystemExit(f"croatia: row {row[:5]} has a type without a name or the reverse")
        counts = {label: count(row[j]) for j, label in columns[1:]}
        units.append({"county": county, "type": kind, "name": name,
                      "total": count(row[total_col]), "counts": counts})
    return labels, units


def sheet_rows(workbook: Any, name: str) -> list[tuple[Any, ...]]:
    if name not in workbook.sheetnames:
        raise SystemExit(f"croatia: no sheet {name!r}; sheets are {workbook.sheetnames}")
    return [tuple(r) for r in workbook[name].iter_rows(values_only=True)]


def bars(field: str, unit: dict[str, Any]) -> Any:
    groups: dict[str, int] = {}
    for label, n in unit["counts"].items():
        shown = LABELS[field].get(label, label)
        groups[shown] = groups.get(shown, 0) + n
    total = unit["total"]
    summed = sum(groups.values())
    if abs(summed - total) > max(0.005 * total, 5):
        raise SystemExit(f"croatia: {unit['county']} / {unit['name']} {field} sums to "
                         f"{summed:,} against the total {total:,}")
    return shares({k: v for k, v in groups.items() if v}, total=total) or gap(NOT_AVAILABLE)


def build() -> list[dict[str, Any]]:
    import openpyxl
    log("croatia: Popis 2021, counties and towns/municipalities")
    blob = http_get(URL, binary=True, timeout=900)
    log(f"  {len(blob):,} bytes")
    workbook = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    parsed = {}
    for field, sheet in SHEETS.items():
        labels, units = parse_sheet(sheet_rows(workbook, sheet))
        log(f"  sheet {sheet} ({field}): {len(labels)} categories: {labels}")
        parsed[field] = units
    keys = [(u["county"], u["type"], u["name"]) for u in parsed["ethnicity"]]
    for field, units in parsed.items():
        theirs = [(u["county"], u["type"], u["name"]) for u in units]
        if theirs != keys:
            raise SystemExit(f"croatia: {field} lists different units from ethnicity "
                             f"({len(theirs)} vs {len(keys)})")
    by_key = {field: {(u["county"], u["type"], u["name"]): u for u in units}
              for field, units in parsed.items()}
    records = []
    skipped: dict[str, int] = {}
    for key in keys:
        county, kind, name = key
        if county not in COUNTIES:
            raise SystemExit(f"croatia: county {county!r} is not in COUNTIES")
        if kind is not None and kind not in UNIT_KINDS:
            # The City of Zagreb is listed by its seventeen city districts,
            # which are neither towns nor municipalities and have no shape;
            # the city itself is written below from its county row.
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        unit = by_key["ethnicity"][key]
        fields: dict[str, Any] = {}
        for field in SHEETS:
            fields[field] = bars(field, by_key[field][key])
            fields[f"{field}_year"] = dated(fields[field], YEAR)
            fields[f"{field}_note"] = NOTES[field]
        county_id = f"HRV-{slugify(county)}"
        shapes = []
        if name is None:
            shapes.append((COUNTIES[county], "admin1", "HRV", None, county_id,
                           [county, f"{county} županija"]))
            if county == "Grad Zagreb":
                # The city is its own county and its own second-level shape.
                shapes.append(("Grad Zagreb", "admin2", county_id, COUNTIES[county],
                               f"{county_id}-grad-zagreb", []))
        else:
            shown = f"{kind} {name}"
            shapes.append((shown, "admin2", county_id, COUNTIES[county],
                           f"{county_id}-{slugify(shown)}", unit_aliases(shown)))
        for shown, level, parent, parent_name, entity_id, aliases in shapes:
            records.append(record(
                entity_id, shown, level=level, parent=parent, parent_name=parent_name,
                country="HRV", aliases=aliases,
                population=measure(unit["total"], year=YEAR, source=SOURCE),
                sources=[{"field": "population/ethnicity/religion/language", "name": SOURCE,
                          "url": PAGE, "license": LICENCE}],
                **fields,
            ))
    for kind, n in skipped.items():
        log(f"  skipped {n} rows of type {kind!r}: not a town or municipality")
    by_level = {"admin1": 0, "admin2": 0}
    for r in records:
        by_level[r["level"]] += 1
    log(f"  {by_level}")
    lo, hi = EXPECTED["admin2"]
    if by_level["admin1"] != EXPECTED["admin1"] or not lo <= by_level["admin2"] <= hi:
        raise SystemExit(f"croatia: expected 21 counties and {lo}-{hi} units, read {by_level}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(PROCESSED / "croatia_county.json", [r for r in records if r["level"] == "admin1"])
    write_json(PROCESSED / "croatia_unit.json", [r for r in records if r["level"] == "admin2"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
