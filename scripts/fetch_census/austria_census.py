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

**Vintage.** The sheets are served under today's municipality codes --
Schwechat is there as 30740, its code since Wien-Umgebung was dissolved in
2017, and the Styrian municipalities under the codes of the districts merged
in 2012 and 2013. A municipality formed by a merger since 2001 has a sheet
that says it has no data and lists the municipalities it was made of; their
own sheets are read and summed in its place. A code opens with its
district's three digits, so each of today's 94 districts is the sum of its
municipalities, and Vienna's 23 Gemeindebezirke are the one district the map
draws. The municipalities come from the same register the age reader
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
GENERAL = "https://www.statistik.at/blickgem/blick1/g{code}.pdf"
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
                 "sheets of the district's municipalities of today (one merged since 2001 as the "
                 "sheets of the municipalities it was made of). Austria's census has been "
                 "register-based since 2011 and has not asked religion since 2001."),
    "language": ("Umgangssprache (the language of everyday use), Volkszählung 2001 (15 May 2001): "
                 "the whole resident population, one answer per person as published; Statistik "
                 "Austria names nine languages at municipal level and puts the rest together with "
                 "those not stated. Summed from the census sheets of the district's municipalities of "
                 "today (one merged since 2001 as the sheets of the municipalities it was made of). "
                 "Not asked since 2001: the census has been register-based since 2011."),
}


def municipalities(year: int) -> list[str]:
    """Today's municipality codes (Vienna as its 23 Gemeindebezirke)."""
    blob = http_get(DATA.format(year=year, part="_C-GRGEMAKT-0"), binary=True)
    rows = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")), delimiter=";")
    listed = {row["code"].split("-")[-1]: row["name"] for row in rows}
    codes = sorted(c for c in listed if re.fullmatch(r"\d{5}", c))
    # Vienna is listed as its 23 Gemeindebezirke (90101 ... 92301); a code for
    # the city as a whole beside them would count it twice.
    whole = [c for c in codes if c.startswith("900")]
    if whole and any(c.startswith("9") and not c.startswith("900") for c in codes):
        log(f"  Vienna as a whole, left out beside its districts: {[(c, listed[c]) for c in whole]}")
        codes = [c for c in codes if c not in whole]
    others = {c: n for c, n in listed.items() if c not in codes and c not in whole}
    if others:
        # The list carries a code for the unclassifiable beside the
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
        # A municipality merged after the 2001 sheets were last regenerated has
        # none; its general sheet (blick1) still lists what it was made of.
        general = http_get(GENERAL.format(code=code), binary=True, timeout=120)
        if not general.startswith(b"%PDF"):
            return {"code": code, "missing": True}
        page = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(general)).pages)
        merged = listed_parts(page)
        if not merged or code in merged:
            return {"code": code, "error": f"austria_census: {code}: no 2001 sheet, and its general "
                    f"sheet lists no merger", "excerpt": " | ".join(page.split("\n"))[:600]}
        parts = [sheet(old) for old in merged]
        bad = [p for p in parts if p.get("error") or p.get("missing")]
        if bad:
            return {"code": code, "error": f"austria_census: {code}: merged from {merged}, and "
                    f"{[p['code'] for p in bad]} could not be read",
                    "excerpt": " | ".join(page.split("\n"))[:600]}
        return {"code": code, "merged": merged, "parts": parts}
    page = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(blob)).pages)
    merged = merged_from(code, page)
    if merged:
        # A municipality formed by a merger since 2001 has no sheet of its own;
        # it lists the municipalities it was made of, whose 2001 sheets are the
        # figures for its ground.
        parts = [sheet(old) for old in merged]
        bad = [p for p in parts if p.get("error") or p.get("missing")]
        if bad:
            return {"code": code, "error": f"austria_census: {code}: merged from {merged}, and "
                    f"{[p['code'] for p in bad]} could not be read",
                    "excerpt": " | ".join(page.split("\n"))[:600]}
        return {"code": code, "merged": merged, "parts": parts}
    try:
        return read_sheet(code, page)
    except SystemExit as exc:
        return {"code": code, "error": str(exc), "excerpt": " | ".join(page.split("\n"))[:900]}


def listed_parts(page: str) -> list[str]:
    """The codes listed one per line after "Zusammenlegung der Gemeinden", up to the first other line."""
    if "Zusammenlegung der Gemeinden" not in page:
        return []
    out: list[str] = []
    for line in page.split("Zusammenlegung der Gemeinden", 1)[1].split("\n")[1:]:
        m = re.match(r"\s*(\d{5})\s", line)
        if m:
            out.append(m.group(1))
        elif line.strip() and out:
            break
    return out


def merged_from(code: str, page: str) -> list[str]:
    """The municipalities a merged one was made of, as its sheet lists them; [] if none."""
    if "Zusammenlegung der Gemeinden" not in page or "keine Daten" not in page:
        return []
    block = page.split("Zusammenlegung der Gemeinden", 1)[1].split("Für die Gemeinde", 1)[0]
    # One line per old municipality: "62203 Bad Waltersdorf", or, where only
    # part of it came, "62227 Limbach bei Neudau (KG Oberlimbach 64131)" --
    # the second number is a cadastral community's, not a municipality's.
    olds = re.findall(r"(?:^|\n)\s*(\d{5})\s", block)
    if not olds or code in olds:
        raise SystemExit(f"austria_census: {code}: a merger listed without its parts: {block[:200]!r}")
    return olds


def read_sheet(code: str, page: str) -> dict[str, Any]:
    head = re.search(r"\((\d{5})\)", page)
    # Vienna's Gemeindebezirke have sheets headed "Wien" and no code.
    vienna = code.startswith("9") and not head and page.lstrip().startswith("Wien")
    if not vienna and (not head or head.group(1) != code):
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
    name = re.search(r"Gemeinde:\s*(.+?)\s*\(\d{5}\)", page)
    return {"code": code, "total": people, "religion": religion, "language": language,
            "name": name.group(1) if name else ("Wien" if vienna else "")}


def leaves(s: dict[str, Any]) -> list[dict[str, Any]]:
    """A sheet's 2001 municipalities: itself, or its parts, and theirs where a part merged again."""
    if not s.get("merged"):
        return [s]
    return [leaf for part in s["parts"] for leaf in leaves(part)]


def adopt_orphans(sheets: list[dict[str, Any]], missing: list[str], codes: list[str],
                  workers: int) -> list[dict[str, Any]]:
    """Give a municipality with no sheet at all the 2001 sheets nobody else claims.

    Fürstenfeld (62280), merged in 2015, has no 2001 sheet and no general
    sheet listing its parts. Its parts still have sheets under the codes
    their district gave them before the merger, and no other municipality of
    today lists them. So, district by district, the codes of the district's
    number range that are neither a municipality of today nor a listed part
    are read; where exactly one municipality of the district lacks a sheet,
    they are its parts. The national count checks the result: a part
    counted twice or missed would miss 8,032,926.
    """
    claimed = set(codes) | {p["code"] for s in sheets if s.get("merged") for p in s["parts"]} \
        | {leaf["code"] for s in sheets for leaf in leaves(s)}
    by_district: dict[str, list[str]] = {}
    for code in missing:
        by_district.setdefault(code[:3], []).append(code)
    adopted: dict[str, dict[str, Any]] = {}
    for district, lacking in sorted(by_district.items()):
        if len(lacking) != 1:
            raise SystemExit(f"austria_census: no 2001 sheet for {lacking} in district {district}")
        candidates = [f"{district}{i:02d}" for i in range(1, 100) if f"{district}{i:02d}" not in claimed]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            found = [s for s in pool.map(sheet, candidates)
                     if not s.get("missing") and not s.get("error") and not s.get("merged")]
        if not found:
            raise SystemExit(f"austria_census: {lacking[0]} has no 2001 sheet and district "
                             f"{district} has no unclaimed one")
        log(f"  {lacking[0]}: no 2001 sheet; district {district}'s unclaimed sheets "
            f"{[(f['code'], f['name']) for f in found]} are its parts")
        adopted[lacking[0]] = {"code": lacking[0], "merged": [f["code"] for f in found],
                               "parts": found}
    return [adopted.get(s["code"], s) for s in sheets]


def build(year: int, workers: int) -> list[dict[str, Any]]:
    log(f"austria_census: Volkszählung 2001 sheets (vz7) for the municipalities of {year}")
    codes = municipalities(year)
    log(f"  {len(codes)} municipalities")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        sheets = list(pool.map(sheet, codes))
    failed = [s for s in sheets if s.get("error")]
    for s in failed[:10]:
        log(f"  ! {s['error']}\n      {s['excerpt']}")
    if failed:
        raise SystemExit(f"austria_census: {len(failed)} sheets could not be read: "
                         f"{[s['code'] for s in failed][:60]}")
    missing = [s["code"] for s in sheets if s.get("missing")]
    if missing:
        sheets = adopt_orphans(sheets, missing, codes, workers)
    # Each 2001 municipality is counted once, in the district of the
    # municipality of today it went to. One that was split between two of
    # today's (Limbach bei Neudau, by cadastral community) is listed by both;
    # it is counted once, and only if both are in the same district.
    def district(code: str) -> str:
        return VIENNA if code.startswith("9") else code[:3]

    counted: dict[str, tuple[str, dict[str, Any]]] = {}
    split: dict[str, set[str]] = {}
    for s in sheets:
        for part in leaves(s):
            split.setdefault(part["code"], set()).add(district(s["code"]))
            counted.setdefault(part["code"], (district(s["code"]), part))
    torn = {c: d for c, d in split.items() if len(d) > 1}
    if torn:
        raise SystemExit(f"austria_census: 2001 municipalities split across today's districts: {torn}")
    merged = [s for s in sheets if s.get("merged")]
    listings: dict[str, int] = {}
    for s in merged:
        for leaf in {leaf["code"] for leaf in leaves(s)}:
            listings[leaf] = listings.get(leaf, 0) + 1
    shared = sorted(c for c, n in listings.items() if n > 1)
    log(f"  {len(merged)} municipalities formed by mergers since 2001, read as the sheets of "
        f"their parts; {len(counted)} municipalities of 2001 in all; listed by two of today's "
        f"(split by cadastral community, counted once): {shared}")
    check_sum((p["total"] for _, p in counted.values()), NATIONAL_2001,
              "municipalities of 2001 against Austria")

    sums: dict[str, dict[str, Any]] = {}
    for key, part in counted.values():
        into = sums.setdefault(key, {"total": 0.0, "religion": {}, "language": {}})
        into["total"] += part["total"]
        for field in ("religion", "language"):
            for k, v in part[field].items():
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
