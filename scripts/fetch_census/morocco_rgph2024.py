#!/usr/bin/env python3
"""Morocco -- the 2024 census's legal population, by region and by province.

The Haut-Commissariat au Plan publishes the legal population of the Kingdom
from the Recensement Général de la Population et de l'Habitat of September
2024 as a workbook: every region, province and prefecture, then every cercle
and commune, each row with its Moroccans, its foreign residents, its total and
its households, and HCP's geographic code (the region's one or two digits, the
province's three more). The urban and rural halves printed with each block are
not read.

**Checks before anything is written.** Every row's Moroccans and foreigners
make its total; every region's provinces make the region; the regions make
the national total HCP announced, 36,828,330.

**Binding.** The map's first level is the twelve regions; its second level the
provinces and prefectures, under a mix of French, English and Arabic labels
("Province d'Errachidia إقليم الرشيدية", "Agadir Ida-Outanane Prefecture",
"Prefecture of Casablanca"). A label is reduced to its Latin name without the
kind of unit, and matched within its region, one to one; ALIASES holds the
spellings no reduction joins. Everything left over is logged, both sides.

**The Western Sahara line.** The boundary file draws Western Sahara apart, as
disputed ground; the map's Laâyoune-Sakia El Hamra region is only the strip
north of 27°40'N, and three of its polygons are pieces of provinces whose
people live almost all across that line: a 2,016 km2 strip of Es-Semara and a
0.7 km2 sliver labelled Oued Ed-Dahab (Dakhla's province). HCP counts each
province whole, so no figure of its is written on those pieces, and the
region's own polygon gets none either: each says why, and the figure an
encyclopaedia put there (the whole region's, or Dakhla's) gives way. The
third, Tarfaya Province, is most of its province, but HCP counts it with its
communes south of the line (Daoura), so it too says why instead of showing
the province's count; the province's communes must make that count, and the
commune named must be among them. Dakhla-Oued Ed-Dahab, the twelfth region,
is not drawn under Morocco at all. One more commune lies across the line in a
province drawn otherwise whole: Al Mahbass, which HCP counts in Assa-Zag
(``ACROSS_COMMUNES``); Assa-Zag's and Guelmim-Oued Noun's counts are written
without it, and their notes name it.

**Nationality.** Every region and province bound carries its Moroccans and its
foreign residents as its ethnicity, on the basis of nationality.

Usage:
    python -m scripts.fetch_census.morocco_rgph2024
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)

URL = "https://www.hcp.ma/file/242341/"
LANDING = ("https://www.hcp.ma/Population-legale-du-Royaume-du-Maroc-repartie-par-regions-"
           "provinces-et-prefectures-et-communes-selon-les-resultats-du_a3974.html")
SOURCE = ("Haut-Commissariat au Plan (HCP), Recensement Général de la Population et de "
          "l'Habitat 2024, population légale des régions, provinces, préfectures et communes")
LICENCE = "HCP open data (reuse with attribution)"
YEAR = 2024
NATIONAL = 36_828_330
OUT = "morocco_rgph2024.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The regions whose drawn polygons stop at the Western Sahara line, by HCP code.
CLAIM_LINE_REGIONS = {11: "Laâyoune-Sakia El Hamra", 12: "Dakhla-Oued Ed-Dahab"}
# Polygons of those regions that are pieces of a province counted across the
# line, by the boundary file's label: the province HCP counts, and the measured
# piece. Each is written as a stated gap that gives way to nothing and displaces
# an encyclopaedia's figure for the whole province.
ACROSS_THE_LINE = {
    "Province d'Es-Semara إقليم السمارة": (
        "Es-Semara", "the 2,016 km2 part of Es-Semara province north of the Western "
                     "Sahara line"),
    "Oued Ed-Dahab Province": (
        "Oued Ed-Dahab", "a sliver of 0.7 km2 at the Western Sahara line, labelled for "
                         "Oued Ed-Dahab province"),
}
# A polygon that is most of its province, the rest across the line: the
# boundary file draws Tarfaya Province north of 27°40'N only (its polygon
# stops at 27.667°N), and HCP counts the province with its communes south of
# the line -- Daoura, which GeoNames places at 27.46°N, inside the disputed
# polygon and outside this one. Written as a stated gap like the pieces, the
# commune named with its own count: label -> (the province HCP counts, the
# part drawn, the communes across the line as HCP names them, folded).
PART_ACROSS = {
    "Tarfaya Province": ("Tarfaya", "the part of Tarfaya province north of the Western "
                                    "Sahara line", ("daoura",)),
}
# Communes across the line in provinces drawn whole otherwise, outside the two
# regions the line cuts: HCP's province name -> its communes there, folded. HCP
# counts Al Mahbass in Assa-Zag province (Guelmim-Oued Noun); Mahbès, at about
# 27.42°N 9.03°W, lies south of 27°40'N, in the polygon drawn for Western Sahara
# at both levels, and the polygon drawn for Assa-Zag stops at 27.667°N (Assa and
# Zag inside it). The province's and the region's counts are written without
# the commune, which their notes name.
ACROSS_COMMUNES = {"Assa-Zag": ("almahbass",)}
# Spellings no reduction joins: the boundary file's reduced label -> HCP's.
ALIASES = {
    "tangierassilah": "tangerassilah",
    "tangiertetouanalhoceima": "tangertetouanalhoceima",
    "fezmeknes": "fesmeknes",
    "rhamna": "rehamna",
    "mohammedia": "mohammadia",
    "fquihbensaleh": "fquihbensalah",
    "elkelaatessraghna": "elkelaasraghna",
}
# A label left over after that is paired with a province of its own region only
# when each is the other's closest spelling, at this similarity or more.
SPELLING = 0.8
# The fields a stated reason across the line is written on.
FIELDS = ("population", "median_age", "sex_ratio", "religion", "language", "ethnicity")
KIND_WORDS = re.compile(
    r"(?i)\b(?:province|prefecture|préfecture|region|région|of|de|du|des|d|l|la|le|les|"
    r"arrondissements)\b")


def latin(name: str) -> str:
    """The label's Latin part, folded: no accents, no Arabic or Tifinagh, no kind words."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if ("a" <= c.lower() <= "z") or c in " -'" else " " for c in text)
    text = text.replace("'", " ")
    text = KIND_WORDS.sub(" ", text)
    return "".join(c for c in text.lower() if c.isalpha())


def number(cell: Any) -> int | None:
    if isinstance(cell, bool) or cell is None:
        return None
    if isinstance(cell, (int, float)):
        return int(cell)
    text = re.sub(r"[\s  ]", "", str(cell))
    return int(text) if text.isdigit() else None


def read(blob: bytes) -> dict[str, Any]:
    """{"national": total, "regions": {code: row}, "provinces": {code: row}} from
    the sheet's rows for the whole population.

    The sheet prints the same units several times over: the regions, then their
    urban and rural halves, then the regions with their provinces (and those
    halves), then everything down to the communes. Rows for an urban or rural
    half are skipped; a unit printed twice must read the same both times."""
    import openpyxl                                 # noqa: PLC0415
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = list(book.worksheets[0].iter_rows(values_only=True))
    out: dict[str, Any] = {"national": None, "regions": {}, "provinces": {}, "communes": {},
                           "all_communes": {}}
    for row in rows:
        cells = list(row) + [None] * 7
        name = str(cells[0] or "").strip()
        if not name or "(milieu " in name:
            continue
        moroccans, foreigners, total = number(cells[1]), number(cells[2]), number(cells[3])
        if total is None or moroccans is None or foreigners is None:
            continue
        if moroccans + foreigners != total:
            raise SystemExit(f"morocco_rgph2024: {name}: {moroccans:,} Moroccans and "
                             f"{foreigners:,} foreigners do not make its {total:,}")
        code = number(cells[6])
        entry = {"name": name, "total": total, "moroccans": moroccans,
                 "foreigners": foreigners, "households": number(cells[4]), "code": code}
        if name.startswith("Ensemble du territoire national"):
            if out["national"] not in (None, total):
                raise SystemExit("morocco_rgph2024: the national row is printed with two totals")
            out["national"] = total
            continue
        if code is None or code < 1:
            continue
        # Regions have one or two digits; provinces and prefectures the region's
        # code and three more; cercles two more and communes four more. The
        # communes of the regions the Western Sahara line cuts are kept, and
        # every commune apart (``ACROSS_COMMUNES`` looks there).
        table = ("regions" if code < 100 else "provinces" if code < 100_000 else None)
        if table is None:
            if code < 10_000_000:
                continue
            out["all_communes"][code] = entry
            if code // 10_000 // 1000 not in CLAIM_LINE_REGIONS:
                continue
            table = "communes"
        seen = out[table].get(code)
        if seen is not None and (seen["total"], seen["name"]) != (total, name):
            raise SystemExit(f"morocco_rgph2024: code {code} is printed as {seen['name']} "
                             f"({seen['total']:,}) and as {name} ({total:,})")
        out[table][code] = entry
    if out["national"] != NATIONAL:
        raise SystemExit(f"morocco_rgph2024: the national row reads {out['national']}, not "
                         f"HCP's {NATIONAL:,}")
    if sum(r["total"] for r in out["regions"].values()) != NATIONAL:
        raise SystemExit("morocco_rgph2024: the regions do not make the national total")
    for code, region in out["regions"].items():
        made = sum(p["total"] for c, p in out["provinces"].items() if c // 1000 == code)
        if made != region["total"]:
            raise SystemExit(f"morocco_rgph2024: {region['name']}'s provinces make {made:,}, "
                             f"the region {region['total']:,}")
    return out


def key(name: str) -> str:
    k = latin(name)
    return ALIASES.get(k, k)


def fields(row: dict[str, Any], what: str, less: list[dict[str, Any]] = ()) -> dict[str, Any]:
    """The legal population and nationality of a region or province, without
    the communes in ``less`` (across the Western Sahara line), which its notes
    name."""
    total = row["total"] - sum(c["total"] for c in less)
    moroccans = row["moroccans"] - sum(c["moroccans"] for c in less)
    foreigners = row["foreigners"] - sum(c["foreigners"] for c in less)
    without = ""
    if less:
        without = (" without " + " and ".join(
            f"the commune of {display_commune(c['name'])} ({c['total']:,} people)"
            for c in less) + ", which lies south of the Western Sahara line")
    note = (f"The legal population of {what}{without} in the 2024 census (RGPH, September "
            f"2024): {moroccans:,} Moroccans and {foreigners:,} foreign residents.")
    return {"population": measure(total, year=YEAR, source=SOURCE),
            "population_note": note,
            # Nationality, which the census counts, on the ethnicity field.
            "ethnicity": shares({"Moroccan": moroccans, "Foreign nationals": foreigners}),
            "ethnicity_basis": "nationality",
            "ethnicity_year": YEAR,
            "ethnicity_note": (f"Nationality, from the legal population of {what}{without} in "
                               f"the 2024 census: {moroccans:,} Moroccans and {foreigners:,} "
                               "foreign residents."),
            "codes": {"hcp": str(row["code"])},
            "sources": [{"field": "population/ethnicity", "name": SOURCE, "url": LANDING,
                         "license": LICENCE, "year": YEAR}]}


def across_communes(table: dict[str, Any], province_code: int) -> list[dict[str, Any]]:
    """The communes of a province that ``ACROSS_COMMUNES`` names, each found once
    among the province's communes, whose counts must make the province's."""
    row = table["provinces"][province_code]
    names = [n for p, ns in ACROSS_COMMUNES.items() if key(p) == key(row["name"]) for n in ns]
    if not names:
        return []
    communes = [c for k, c in table.get("all_communes", table["communes"]).items()
                if k // 10_000 == province_code]
    if sum(c["total"] for c in communes) != row["total"]:
        raise SystemExit(f"morocco_rgph2024: {row['name']}'s {len(communes)} communes make "
                         f"{sum(c['total'] for c in communes):,}, not its {row['total']:,}")
    out = []
    for name in names:
        found = [c for c in communes if name in latin(c["name"])]
        if len(found) != 1:
            raise SystemExit(f"morocco_rgph2024: {row['name']} has {len(found)} communes named "
                             f"{name!r}: {[c['name'] for c in communes]}")
        out.append(found[0])
    return out


def stated(text: str) -> dict[str, Any]:
    """The same stated reason on every field, displacing an encyclopaedia's figure."""
    out = {}
    for field in FIELDS:
        why = gap(NOT_AVAILABLE, text)
        why["displaces_before"] = YEAR + 1
        out[field] = why
    return out


def part_across(table: dict[str, Any], label: str) -> str:
    """The stated reason for a polygon PART_ACROSS declares: its province's
    count, and the communes of it across the line with theirs. The province's
    communes must make its count, and each declared commune must be one of
    them, or the run stops."""
    province, part, across = PART_ACROSS[label]
    hits = [(c, p) for c, p in table["provinces"].items() if key(p["name"]) == key(province)]
    if len(hits) != 1:
        raise SystemExit(f"morocco_rgph2024: {label}: {len(hits)} HCP provinces named {province}")
    code, row = hits[0]
    communes = [c for k, c in table["communes"].items() if k // 10_000 == code]
    made = sum(c["total"] for c in communes)
    if made != row["total"]:
        raise SystemExit(f"morocco_rgph2024: {province} province's {len(communes)} communes make "
                         f"{made:,}, not its {row['total']:,}")
    named = []
    for name in across:
        found = [c for c in communes if name in latin(c["name"])]
        if len(found) != 1:
            raise SystemExit(f"morocco_rgph2024: {province} province has {len(found)} communes "
                             f"named {name!r}: {[c['name'] for c in communes]}")
        named.append(f"{display_commune(found[0]['name'])} ({found[0]['total']:,} people)")
    which = ("the commune of " + named[0] if len(named) == 1 else
             "the communes of " + ", ".join(named[:-1]) + " and " + named[-1])
    return (f"This polygon is {part}. The 2024 census counts {province} province whole "
            f"({row['total']:,} people), {which} south of that line among them, and no figure "
            "for the part north of it alone has been read, so none is shown here.")


def display_commune(name: str) -> str:
    """'Commune de Daoura' -> 'Daoura'; "Commune d'El Hagounia" -> 'El Hagounia'."""
    return re.sub(r"(?i)^commune\s+(?:de\s+|d['’]\s*)?", "", str(name).strip())


def pair_by_spelling(shapes: list[dict[str, Any]],
                     provinces: dict[str, tuple[int, dict[str, Any]]]
                     ) -> list[tuple[dict[str, Any], int]]:
    """Leftover labels and leftover provinces of one region, paired only where
    each is the other's closest spelling and close enough."""
    from difflib import SequenceMatcher             # noqa: PLC0415

    def ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()
    pairs = []
    for shape in shapes:
        k = key(shape["name"])
        best = max(provinces, key=lambda p: ratio(k, p), default=None)
        if best is None or ratio(k, best) < SPELLING:
            continue
        back = max(shapes, key=lambda s: ratio(key(s["name"]), best))
        if back is shape:
            pairs.append((shape, provinces[best][0]))
    return pairs


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    report: list[str] = []
    regions = {key(r["name"]): (code, r) for code, r in table["regions"].items()}
    region_of_shape: dict[str, int] = {}
    for shape in admin1:
        hit = regions.get(key(shape["name"]))
        if hit is None:
            report.append(f"region polygon {shape['name']!r}: no HCP region")
            continue
        code, row = hit
        region_of_shape[shape["id"]] = code
        if code in CLAIM_LINE_REGIONS:
            why = stated(
                f"This polygon is only the part of the {CLAIM_LINE_REGIONS[code]} region "
                "north of the Western Sahara line; the region's people live almost all "
                "across it. The 2024 census counts the region whole "
                f"({row['total']:,}), and no source counts this part apart, so no "
                "figure is shown here.")
            # The region's own count goes with the reason and is never shown:
            # the build weighs by it how much of Morocco the region is when it
            # sums the country from its regions (covered_share), and takes it
            # off before writing, as it does a count NOT_THIS_GROUND refuses.
            why["population"]["refused_value"] = row["total"]
            records.append(record(
                f"MAR-RGPH2024-{code}", shape["name"], level="admin1", parent="MAR",
                country="MAR", match_by="shape_id", shape_id=shape["id"], **why))
            report.append(f"region {shape['name']!r}: across the line, written as a gap")
            continue
        less = [c for p in sorted(table["provinces"]) if p // 1000 == code
                for c in across_communes(table, p)]
        records.append(record(f"MAR-RGPH2024-{code}", shape["name"], level="admin1",
                              parent="MAR", country="MAR", match_by="shape_id",
                              shape_id=shape["id"], **fields(row, row["name"], less)))
    every = {key(p["name"]): p for p in table["provinces"].values()}
    used: set[int] = set()
    by_region: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for shape in admin2:
        by_region[region_of_shape.get(shape["parent"], -1)].append(shape)
    for region, shapes in sorted(by_region.items()):
        provinces = {key(p["name"]): (c, p) for c, p in table["provinces"].items()
                     if c // 1000 == region}
        left: list[dict[str, Any]] = []
        for shape in shapes:
            if shape["name"] in ACROSS_THE_LINE:
                province, piece = ACROSS_THE_LINE[shape["name"]]
                row = every.get(key(province))
                counted = f" ({row['total']:,} people)" if row else ""
                records.append(record(
                    f"MAR-RGPH2024-piece-{shape['id']}", shape["name"], level="admin2",
                    parent="MAR", country="MAR", match_by="shape_id", shape_id=shape["id"],
                    **stated(f"This polygon is {piece}. The 2024 census counts {province} "
                             f"province whole{counted}, almost all of it across that line, "
                             "and no source counts this piece apart, so no figure is shown "
                             "here.")))
                report.append(f"{shape['name']!r}: a piece across the line, written as a gap")
                continue
            if shape["name"] in PART_ACROSS:
                records.append(record(
                    f"MAR-RGPH2024-part-{shape['id']}", shape["name"], level="admin2",
                    parent="MAR", country="MAR", match_by="shape_id", shape_id=shape["id"],
                    **stated(part_across(table, shape["name"]))))
                report.append(f"{shape['name']!r}: part of a province across the line, written "
                              "as a gap")
                continue
            if region in CLAIM_LINE_REGIONS or region == -1:
                report.append(f"{shape['name']!r}: in a region the line cuts; not bound")
                continue
            hit = provinces.get(key(shape["name"]))
            if hit is None or hit[0] in used:
                left.append(shape)
                continue
            code, row = hit
            used.add(code)
            records.append(record(f"MAR-RGPH2024-{code}", shape["name"], level="admin2",
                                  parent="MAR", country="MAR", match_by="shape_id",
                                  shape_id=shape["id"],
                                  **fields(row, row["name"], across_communes(table, code))))
        spare = {k: v for k, v in provinces.items() if v[0] not in used}
        paired = pair_by_spelling(left, spare)
        for shape, code in paired:
            row = table["provinces"][code]
            used.add(code)
            report.append(f"{shape['name']!r} bound to {row['name']!r} by spelling")
            records.append(record(f"MAR-RGPH2024-{code}", shape["name"], level="admin2",
                                  parent="MAR", country="MAR", match_by="shape_id",
                                  shape_id=shape["id"],
                                  **fields(row, row["name"], across_communes(table, code))))
        for shape in left:
            if all(shape is not s for s, _ in paired):
                report.append(f"{shape['name']!r} ({key(shape['name'])}): no HCP province "
                              "of that name in its region")
    left = [p["name"] for c, p in table["provinces"].items()
            if c not in used and c // 1000 not in CLAIM_LINE_REGIONS]
    report.append(f"HCP provinces not drawn: {left}")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    blob = http_get(URL, binary=True, cache=False, timeout=120)
    if blob[:2] != b"PK":
        raise SystemExit(f"morocco_rgph2024: {URL} is not a workbook: {blob[:80]!r}")
    # Which bytes were read, for anyone checking the rows against the file.
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = read(blob)
    log(f"  {len(table['regions'])} regions and {len(table['provinces'])} provinces and "
        f"prefectures, making {table['national']:,}")
    admin1 = json.loads((SITE / "admin1" / "MAR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "MAR.units.json").read_text())
    records, report = build(table, admin1, admin2)
    for line in report:
        log("  " + line)
    for code in (1405, 2411, 4501, 8201):
        row = table["provinces"].get(code)
        if row:
            log(f"  {row['name']}: {row['total']:,}")
    for code, row in sorted(table["provinces"].items()):
        for c in across_communes(table, code):
            log(f"  {row['name']}: {c['name']} {c['total']:,} ({c['code']}), across the line, "
                f"taken out of {row['name']} ({row['total']:,})")
    for label, (province, _, _) in PART_ACROSS.items():
        for code, row in table["provinces"].items():
            if key(row["name"]) == key(province):
                for c in sorted(table["communes"].values(), key=lambda c: c["code"]):
                    if c["code"] // 10_000 == code:
                        log(f"  {row['name']}: {c['name']} {c['total']:,} ({c['code']})")
    bound = [r for r in records if r["level"] == "admin2" and "value" in r["population"]]
    log(f"  {sum(1 for r in records if r['level'] == 'admin1' and 'value' in r['population'])} "
        f"regions and {len(bound)} of {len(admin2)} provinces bound")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
