#!/usr/bin/env python3
"""Guinea-Bissau -- the 2009 census's resident population by region and sector.

The Instituto Nacional de Estatística published the Fourth General Census of
Population and Housing (RGPH 2009) region by region: one PDF for each of the
eight regions and one for the Autonomous Sector of Bissau (SAB), each opening
with Tabela 1, the resident population by sex and by urban or rural residence
for the region, each of its sectors, and every locality. A line reads

    Sector de Catió 26 999 12 903 14 096 52,2     (total, men, women, % women)
    Catió - Urbano  ...                            (the sector's urban part)

The PDFs' text sometimes breaks a number at a thousands space or elsewhere
("665 302 3 63" is 665, 302 and 363); a line is read as the one split of its
digits into a total that is its men and women together, with the women's share
the line prints.

**Checks before anything is written.** A sector's urban and rural lines make
its own line where both are printed; the sectors make their region's line.
A region whose sectors cannot all be read is left out, and says so in the log.

**Binding.** Each sector is bound to its polygon by the polygon's id, declared
below. Three cases are not one sector to one polygon:

* Komo sector was split from Catió around 2007; the boundary file draws the
  two as one polygon, "Setor de Catie", which takes both sectors' counts
  together and says so.
* Cossé sector is drawn as "Setor de Galomaro": Galomaro is its seat, listed
  among its localities.
* Caió sector, with the islands of Jeta and Pecixe, is drawn as two polygons
  -- the mainland with Jeta ("Setor de Caiv") and an island 1 km off it
  ("Setor de Boe") that touches no other sector. The census counts the
  sector whole, so neither polygon gets a figure, and each says why.

Bissau's eight urban sectors are one polygon at both levels: it takes the
SAB's total.

Usage:
    python -m scripts.fetch_census.guinea_bissau_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json

BASE = "https://www.stat-guinebissau.com/Menu_principal/IV_RGPH/rgph1/"
SOURCE = ("Instituto Nacional de Estatística da Guiné-Bissau, IV Recenseamento Geral da "
          "População e Habitação 2009, Tabela 1: resident population by sex and residence, "
          "by region, sector and locality")
LICENCE = "INE Guinea-Bissau publication (reuse with attribution)"
YEAR = 2009
OUT = "guinea_bissau_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# Each region's PDF, the region's polygon, and its sectors (folded) -> polygon ids.
# A polygon listed under more than one sector takes their sum.
REGIONS: dict[str, dict[str, Any]] = {
    "Tombali": {"file": "Regiao_de_Tombali_RGPH_2009.pdf", "polygon": "76643164B14801811690770",
                "sectors": {"catio": "13655514B24413703823033", "komo": "13655514B24413703823033",
                            "bedanda": "13655514B48763126228848",
                            "cacine": "13655514B71925291750028",
                            "quebo": "13655514B12793543239296"}},
    "Quinara": {"file": "Regiao_de%20Quinara_RGPH_2009.pdf", "polygon": "76643164B25325276017448",
                "sectors": {"buba": "13655514B37452641895852", "empada": "13655514B30693048438959",
                            "fulacunda": "13655514B9524670555472",
                            "tite": "13655514B37576476310465"}},
    "Oio": {"file": "Regiao_de_Oio_RGPH_2009.pdf", "polygon": "76643164B92913079273182",
            "sectors": {"bissora": "13655514B57740331915335", "farim": "13655514B57644193184055",
                        "mansaba": "13655514B49812801634354", "mansoa": "13655514B31772276876031",
                        "nhacra": "13655514B47112439721810"}},
    "Biombo": {"file": "Regiao_de_Biombo_RGPH_2009.pdf", "polygon": "76643164B78535055467734",
               "sectors": {"quinhamel": "13655514B66751603958816",
                           "safim": "13655514B65757043009502",
                           "prabis": "13655514B53615250576563"}},
    "Bolama": {"file": "Regiao_de_Bolama_RGPH_2009.pdf", "polygon": "76643164B18917431809987",
               "sectors": {"bolama": "13655514B77006902429960", "bubaque": "13655514B98496568253651",
                           "caravela": "13655514B59106895169358",
                           "uno": "13655514B44985576134462"}},
    "Bafatá": {"file": "Regiao_de_Bafata_RGPH_2009.pdf", "polygon": "76643164B84174472060432",
               "sectors": {"bafata": "13655514B15077734082289",
                           "bambadinca": "13655514B168355566476",
                           "cosse": "13655514B4319146558278",
                           "gamamudo": "13655514B65726406107890",
                           "xitole": "13655514B65471558325414",
                           "contuboel": "13655514B51179315853055"}},
    "Gabú": {"file": "Regiao_de_Gabu_RGPH_2009.pdf", "polygon": "76643164B38080973404583",
             "sectors": {"gabu": "13655514B65296626482863", "boe": "13655514B15408487636665",
                         "pirada": "13655514B16168252486838", "pitche": "13655514B97576906537580",
                         "sonaco": "13655514B47480576799194"}},
    "Cacheu": {"file": "Regiao_de_Cacheu_RGPH_2009.pdf", "polygon": "76643164B20603668674672",
               "sectors": {"bigene": "13655514B76388735674013", "bula": "13655514B11561761851968",
                           "cacheu": "13655514B95678269815128",
                           "canchungo": "13655514B91246233663569",
                           "saodomingos": "13655514B91994517778696", "caio": None}},
    "Bissau": {"file": "SAB_RGPH_2009.pdf", "polygon": "76643164B96925829526723",
               "sectors": {f"sector{i}": "13655514B38974563194217" for i in range(1, 9)}},
}
# Caió sector's two polygons, which get its reason instead of a figure.
CAIO = {"13655514B8216177448850": "the mainland part of Caió sector, with the island of Jeta",
        "13655514B99052541590952": ("an island 1 km off the Caió sector polygon, the only "
                                    "polygon it lies near")}
# What a polygon taking more than one sector says.
POOLED = {"13655514B24413703823033": ("Catió and Komo sectors together: Komo was made from part "
                                      "of Catió around 2007, and the two are drawn as one "
                                      "polygon.")}
SEAT = {"13655514B4319146558278": ("Cossé sector, whose seat is Galomaro.")}

NUMBER = re.compile(r"^\d+$")
RATIO = re.compile(r"^\d{1,3}(?:,\d+)?$")
PART = re.compile(r"^(?P<name>.*?\S)\s*-\s*(?P<kind>Urbano|Rural)$", re.I)
HEAD = re.compile(r"^(?:Sector|Sectoer|Setor)\s+de\s+(?P<name>.+)$", re.I)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text.lower() if "a" <= c <= "z" or c.isdigit())


def split_line(line: str) -> tuple[str, int, int, int] | None:
    """(label, total, men, women) from a table line, or None."""
    tokens = line.split()
    if len(tokens) < 4 or not RATIO.match(tokens[-1]):
        return None
    share = float(tokens[-1].replace(",", "."))
    decimals = len(tokens[-1].split(",")[1]) if "," in tokens[-1] else 0
    tolerance = 0.06 if decimals else 0.6
    numbers: list[str] = []
    i = len(tokens) - 2
    while i >= 0 and NUMBER.match(tokens[i]):
        numbers.insert(0, tokens[i])
        i -= 1
    label = " ".join(tokens[:i + 1])
    digits = "".join(numbers)
    cuts = {sum(len(t) for t in numbers[:k]) for k in range(len(numbers) + 1)}
    found = []
    for a in range(1, len(digits) - 1):
        for b in range(a + 1, len(digits)):
            parts = digits[:a], digits[a:b], digits[b:]
            if any(len(p) > 1 and p[0] == "0" for p in parts):
                continue
            total, men, women = (int(p) for p in parts)
            if men + women != total:
                continue
            if total and abs(100 * women / total - share) > tolerance:
                continue
            if not total and share:
                continue
            found.append(((a in cuts) + (b in cuts), (total, men, women)))
    if not found:
        return None
    best = max(score for score, _ in found)
    picks = {nums for score, nums in found if score == best}
    if len(picks) != 1:
        return None
    total, men, women = picks.pop()
    return label, total, men, women


def parse(lines: list[str], region: str) -> dict[str, Any]:
    """{"region": (total, men, women), "sectors": {key: {...}}} from one PDF's lines."""
    out: dict[str, Any] = {"region": None, "sectors": {}}
    parts: dict[tuple[str, str], tuple[int, int, int]] = {}
    heads: dict[str, tuple[int, int, int]] = {}
    names: dict[str, str] = {}
    for line in lines:
        hit = split_line(line.strip())
        if hit is None:
            continue
        label, *nums = hit
        nums = tuple(nums)
        f = fold(label)
        if f.startswith("regiao") or f == "sab":
            if out["region"] not in (None, nums):
                raise SystemExit(f"guinea_bissau_census: {region}'s line is printed two ways")
            out["region"] = nums
            continue
        part = PART.match(label)
        if part:
            name = part.group("name")
            key = (fold(name), part.group("kind").lower())
            if parts.get(key, nums) != nums:
                raise SystemExit(f"guinea_bissau_census: {label} is printed two ways")
            parts[key] = nums
            names.setdefault(fold(name), name)
            continue
        head = HEAD.match(label)
        if head:
            heads[fold(head.group("name"))] = nums
            names.setdefault(fold(head.group("name")), head.group("name"))
    for key in {k for k, _ in parts} | set(heads):
        pieces = [parts[(key, kind)] for kind in ("urbano", "rural") if (key, kind) in parts]
        summed = tuple(sum(p[i] for p in pieces) for i in range(3)) if pieces else None
        own = heads.get(key)
        if summed and own and summed != own:
            raise SystemExit(f"guinea_bissau_census: {names[key]}'s urban and rural lines make "
                             f"{summed}, its own line {own}")
        out["sectors"][key] = {"name": names[key], "total": (own or summed)[0],
                               "men": (own or summed)[1], "women": (own or summed)[2]}
    return out


def read(blob: bytes, region: str) -> dict[str, Any]:
    import pdfplumber                               # noqa: PLC0415
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            lines += (page.extract_text() or "").splitlines()
    return parse(lines, region)


def check(table: dict[str, Any], region: str, wanted: set[str]) -> str | None:
    """Why a region cannot be written, or None."""
    if table["region"] is None:
        return "no region line"
    missing = wanted - set(table["sectors"])
    if missing:
        return f"sectors not read: {sorted(missing)}; read {sorted(table['sectors'])}"
    made = sum(table["sectors"][k]["total"] for k in wanted)
    if made != table["region"][0]:
        return (f"its sectors {sorted(wanted)} make {made:,}, the region {table['region'][0]:,}; "
                f"read {sorted(table['sectors'])}")
    return None


def fields(total: int, men: int, women: int, note: str) -> dict[str, Any]:
    return {"population": measure(total, year=YEAR, source=SOURCE), "population_note": note,
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "sources": [{"field": "population/sex_ratio", "name": SOURCE,
                         "url": BASE, "license": LICENCE, "year": YEAR}]}


def build(tables: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    first = {u["id"]: u for u in admin1}
    second = {u["id"]: u for u in admin2}
    records: list[dict[str, Any]] = []
    report: list[str] = []
    for region, spec in REGIONS.items():
        table = tables.get(region)
        if table is None:
            report.append(f"{region}: not read")
            continue
        why = check(table, region, set(spec["sectors"]))
        if why:
            report.append(f"{region}: left out -- {why}")
            continue
        poly = first.get(spec["polygon"])
        if poly is None:
            raise SystemExit(f"guinea_bissau_census: no first-level polygon {spec['polygon']}")
        total, men, women = table["region"]
        records.append(record(
            f"GNB-2009-{fold(region)}", poly["name"], level="admin1", parent="GNB", country="GNB",
            match_by="shape_id", shape_id=poly["id"],
            **fields(total, men, women, f"The 2009 census's resident population of {region}"
                     + (" (the Autonomous Sector of Bissau)." if region == "Bissau" else
                        " region."))))
        by_polygon: dict[str, list[str]] = {}
        for key, sid in spec["sectors"].items():
            if sid is not None:
                by_polygon.setdefault(sid, []).append(key)
        for sid, keys in by_polygon.items():
            shape = second.get(sid)
            if shape is None or shape.get("parent") != poly["id"]:
                raise SystemExit(f"guinea_bissau_census: polygon {sid} is not drawn under {region}")
            rows = [table["sectors"][k] for k in keys]
            total = sum(r["total"] for r in rows)
            men = sum(r["men"] for r in rows)
            women = sum(r["women"] for r in rows)
            if region == "Bissau":
                note = ("The 2009 census's resident population of the Autonomous Sector of "
                        "Bissau, its eight urban sectors together.")
            elif sid in POOLED:
                counts = " and ".join(f"{r['name']} {r['total']:,}" for r in rows)
                note = f"The 2009 census's resident population of {POOLED[sid]} ({counts})."
            elif sid in SEAT:
                note = f"The 2009 census's resident population of {SEAT[sid]}"
            else:
                note = f"The 2009 census's resident population of {rows[0]['name']} sector."
            records.append(record(f"GNB-2009-{sid}", shape["name"], level="admin2", parent="GNB",
                                  country="GNB", match_by="shape_id", shape_id=sid,
                                  **fields(total, men, women, note)))
            report.append(f"  {shape['name']}: {total:,} ({', '.join(keys)})")
        if region == "Cacheu":
            caio = table["sectors"]["caio"]
            for sid, what in CAIO.items():
                shape = second.get(sid)
                if shape is None:
                    raise SystemExit(f"guinea_bissau_census: no polygon {sid}")
                text = (f"This polygon is {what}. The 2009 census counts Caió sector whole, "
                        f"islands included ({caio['total']:,} people), and no table counts its "
                        "parts apart, so no figure is shown here.")
                records.append(record(
                    f"GNB-2009-caio-{sid}", shape["name"], level="admin2", parent="GNB",
                    country="GNB", match_by="shape_id", shape_id=sid,
                    population=gap(NOT_AVAILABLE, text), sex_ratio=gap(NOT_AVAILABLE, text),
                    median_age=gap(NOT_AVAILABLE, text)))
            report.append(f"  Caió: {caio['total']:,} on neither of its two polygons")
    made = sum(t["region"][0] for t in tables.values() if t.get("region"))
    report.append(f"regions read make {made:,}")
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    tables: dict[str, dict[str, Any]] = {}
    for region, spec in REGIONS.items():
        url = BASE + spec["file"]
        try:
            blob = http_get(url, binary=True, cache=False, timeout=300)
        except Exception as exc:                     # noqa: BLE001
            log(f"  {region}: {url}: {exc}")
            continue
        if not blob.startswith(b"%PDF"):
            log(f"  {region}: not a PDF: {blob[:60]!r}")
            continue
        tables[region] = read(blob, region)
        t = tables[region]
        log(f"  {region}: region {t['region']}; sectors "
            + ", ".join(f"{s['name']} {s['total']:,}" for s in t["sectors"].values()))
    admin1 = json.loads((SITE / "admin1" / "GNB.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GNB.units.json").read_text())
    records, report = build(tables, admin1, admin2)
    for line in report:
        log("  " + line)
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} regions and "
        f"{sum(1 for r in records if r['level'] == 'admin2')} sector polygons written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
