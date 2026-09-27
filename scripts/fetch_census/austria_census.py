#!/usr/bin/env python3
"""Austria: religion and Umgangssprache by politischer Bezirk, from the 2001 census.

Austria's census has been register-based since 2011 and no register holds
religion or language; the Volkszählung of 15 May 2001 was the last to ask
both, of everyone. Statistik Austria still serves its results municipality by
municipality in "Ein Blick auf die Gemeinde": sheet ``vz7`` of each
municipality (``https://www.statistik.at/blickgem/vz7/g<code>.pdf``) gives the
resident population by religion (römisch-katholisch, evangelisch, orthodox,
islamisch, israelitisch, sonstiges, ohne Bekenntnis, unbekannt) and by
Umgangssprache, the language of everyday use (Deutsch, Burgenland-Kroatisch,
Slowenisch, Tschechisch, Ungarisch, Serbisch, Kroatisch, Bosnisch, Türkisch,
Sonstige und unbekannt).

**Vintage.** The sheets are served under today's municipality codes, with the
2001 count laid over today's boundaries -- Schwechat is there as 30740, its
code since Wien-Umgebung was dissolved in 2017, and the Styrian municipalities
under the codes of the districts merged in 2012 and 2013. A code opens with
its district's three digits, so each of today's 94 districts is the sum of its
municipalities' sheets, and Vienna's 23 Gemeindebezirke are the one district
the map draws. The municipalities come from the same register the age reader
uses (OGD_bevstandjbab2002_BevStand_<year>, C-GRGEMAKT-0).

**Checks.** Each sheet names the municipality it was asked for; its religion
rows and its language rows each make its resident population; and the
municipalities make the 2001 census's national count, 8,032,926.

Usage:
    python -m scripts.fetch_census.austria_census [--year 2026] [--workers 6]
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ._shared import PROCESSED, dated, http_get, log, record, shares, write_json
from .austria import DATA, LAENDER, REGISTER_ALIASES, VIENNA, districts
from .central_ages import check_sum, fold, report_unbound, units

SHEET = "https://www.statistik.at/blickgem/vz7/g{code}.pdf"
PORTAL = "https://www.statistik.at/blickgem/"
SOURCE = ("Statistik Austria, Volkszählung 2001 (15 May 2001), Ein Blick auf die Gemeinde: "
          "Wohnbevölkerung nach Religion und Umgangssprache")
LICENCE = "Statistik Austria (free reuse with attribution)"
OUT = PROCESSED / "austria_census.json"
YEAR = 2001
NATIONAL_2001 = 8_032_926       # Volkszählung 2001, resident population (statistical result)
EXPECTED = 94

NUMBER = r"\s+(\d{1,3}(?:\.\d{3})*)\s+\d{1,3},\d"
RELIGION = {
    "römisch-katholisch": "Roman Catholic", "evangelisch": "Protestant",
    "orthodox": "Orthodox", "islamisch": "Islam", "israelitisch": "Judaism",
    "sonstiges": "Other religion", "ohne Bekenntnis": "No religion", "unbekannt": "Not stated",
}
LANGUAGE = {
    "Deutsch": "German", "Burgenland-Kroatisch": "Burgenland Croatian", "Slowenisch": "Slovene",
    "Tschechisch": "Czech", "Ungarisch": "Hungarian", "Serbisch": "Serbian",
    "Kroatisch": "Croatian", "Bosnisch": "Bosnian", "Türkisch": "Turkish",
    "Sonstige und unbekannt": "Other or unknown language",
}
# A label must not be read inside a longer one: "Kroatisch" inside
# "Burgenland-Kroatisch", "unbekannt" inside "Sonstige und unbekannt".
GUARD = {"Kroatisch": r"(?<![-\w])", "unbekannt": r"(?<!und )(?<!\w)"}
NOTES = {
    "religion": ("Religious denomination, Volkszählung 2001 (15 May 2001): the whole resident "
                 "population, one answer; 'Protestant' is the Evangelical churches of the Augsburg "
                 "and Helvetic confessions; 'Not stated' is 'unbekannt'. Summed from the census "
                 "sheets of the district's municipalities, which Statistik Austria lays over "
                 "today's boundaries. Austria's census has been register-based since 2011 and has "
                 "not asked religion since 2001."),
    "language": ("Umgangssprache (the language of everyday use), Volkszählung 2001 (15 May 2001): "
                 "the whole resident population, one answer per person as published; Statistik "
                 "Austria names nine languages at municipal level and puts the rest together with "
                 "those not stated. Summed from the census sheets of the district's municipalities, "
                 "laid over today's boundaries. Not asked since 2001: the census has been "
                 "register-based since 2011."),
}


def municipalities(year: int) -> list[str]:
    """Today's municipality codes (Vienna as its 23 Gemeindebezirke)."""
    blob = http_get(DATA.format(year=year, part="_C-GRGEMAKT-0"), binary=True)
    rows = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")), delimiter=";")
    listed = {row["code"].split("-")[-1]: row["name"] for row in rows}
    codes = sorted(c for c in listed if re.fullmatch(r"\d{5}", c))
    others = {c: n for c, n in listed.items() if c not in codes}
    if others:
        # The list carries a code for the country as a whole beside the
        # municipalities; nothing else is expected.
        log(f"  not municipalities, left out: {others}")
        if len(others) > 1:
            raise SystemExit(f"austria_census: unexpected non-municipal codes {others}")
    return codes


def find(page: str, labels: dict[str, str], code: str, what: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for german, english in labels.items():
        hits = re.findall(GUARD.get(german, r"(?<!\w)") + re.escape(german) + NUMBER, page)
        values = {int(h.replace(".", "")) for h in hits}
        if len(values) > 1:
            raise SystemExit(f"austria_census: {code}: {german!r} read as {sorted(values)}")
        out[english] = float(values.pop()) if values else 0.0
    return out


def sheet(code: str) -> dict[str, Any]:
    """One municipality's 2001 population, religion and Umgangssprache."""
    from pypdf import PdfReader
    blob = http_get(SHEET.format(code=code), binary=True, timeout=120)
    if not blob.startswith(b"%PDF"):
        return {"code": code, "missing": True}
    page = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(blob)).pages)
    head = re.search(r"\((\d{5})\)", page)
    if not head or head.group(1) != code:
        raise SystemExit(f"austria_census: the sheet asked for {code} is headed "
                         f"{head.group(1) if head else None}")
    total = re.search(r"Wohnbevölkerung\s+(\d{1,3}(?:\.\d{3})*)\s+100,0", page)
    if not total:
        raise SystemExit(f"austria_census: {code}: no resident population on the sheet")
    people = float(total.group(1).replace(".", ""))
    religion = find(page, RELIGION, code, "religion")
    language = find(page, LANGUAGE, code, "language")
    for field, counts in (("religion", religion), ("language", language)):
        if abs(sum(counts.values()) - people) > 0.5:
            raise SystemExit(f"austria_census: {code}: {field} rows make {sum(counts.values()):,.0f}, "
                             f"the sheet's population is {people:,.0f}: {counts}")
    return {"code": code, "total": people, "religion": religion, "language": language}


def build(year: int, workers: int) -> list[dict[str, Any]]:
    log(f"austria_census: Volkszählung 2001 sheets (vz7) for the municipalities of {year}")
    codes = municipalities(year)
    log(f"  {len(codes)} municipalities")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        sheets = list(pool.map(sheet, codes))
    missing = [s["code"] for s in sheets if s.get("missing")]
    if missing:
        raise SystemExit(f"austria_census: no 2001 sheet for {len(missing)} municipalities: "
                         f"{missing[:40]}")
    check_sum((s["total"] for s in sheets), NATIONAL_2001, "municipalities against Austria (2001)")

    sums: dict[str, dict[str, Any]] = {}
    for s in sheets:
        key = VIENNA if s["code"].startswith("9") else s["code"][:3]
        into = sums.setdefault(key, {"total": 0.0, "religion": {}, "language": {}})
        into["total"] += s["total"]
        for field in ("religion", "language"):
            for k, v in s[field].items():
                into[field][k] = into[field].get(k, 0.0) + v
    log(f"  {len(sums)} districts")

    names = districts()
    shapes = units("AUT", "admin2")
    parents = {u["id"]: u["name"] for u in units("AUT", "admin1")}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_name.setdefault(fold(shape["name"]), []).append(shape)
    source = [{"field": "religion/language", "name": SOURCE, "url": PORTAL, "license": LICENCE,
               "year": YEAR}]
    records, unbound, used = [], [], set()
    for key in sorted(sums):
        name = VIENNA if key == VIENNA else REGISTER_ALIASES.get(key, names.get(key))
        if name is None:
            raise SystemExit(f"austria_census: district {key} is not in today's register")
        land = LAENDER["9" if key == VIENNA else key[0]]
        hits = [h for h in by_name.get(fold(name), []) if parents.get(h["parent"]) == land] \
            or by_name.get(fold(name), [])
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{name} ({key})")
            continue
        shape = hits[0]
        used.add(shape["id"])
        c = sums[key]
        fields: dict[str, Any] = {}
        for field in ("religion", "language"):
            rows = shares({k: v for k, v in c[field].items() if v}, total=c["total"])
            fields[field] = rows
            fields[f"{field}_year"] = dated(rows, YEAR)
            fields[f"{field}_note"] = NOTES[field] + (
                " Vienna's 23 Gemeindebezirke are summed as the one district the map draws."
                if key == VIENNA else "")
        records.append(record(
            f"AUT-VZ2001-{'900' if key == VIENNA else key}", shape["name"], level="admin2",
            parent=shape["parent"], parent_name=land, country="AUT",
            codes={"statistik_austria_pol_bezirk": "900" if key == VIENNA else key},
            match_by="shape_id", shape_id=shape["id"], sources=source, **fields))
    report_unbound("austria_census", unbound, [s["name"] for s in shapes if s["id"] not in used])
    if unbound or len(records) != EXPECTED:
        raise SystemExit(f"austria_census: {len(records)} districts bound, {EXPECTED} expected")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    records = build(args.year, args.workers)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
