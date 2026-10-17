#!/usr/bin/env python3
"""Côte d'Ivoire -- the 2021 census (RGPH 2021) by region, from ANStat's regional pages.

The national statistics agency (ANStat, formerly INS) published the 2021
census's results for each of the 31 regions and the two autonomous districts
on its census site, rp2021.anstat.ci: a page per region with its seat ("Sa
capitale est Bouaké"), its departments' seats, and a synoptic table of the
region against the country -- everyone by sex in 2021 (and 1998), the mean age,
the population in broad age groups -- and a paragraph giving the share of
Ivorians among its residents. The site refuses an automated client; the
Internet Archive's captures of January 2026 are read instead.

Written for each region and autonomous district: population and sex ratio
(2021), its seat where the map names none, and the Ivorian and non-Ivorian
shares of its people on the ethnicity field under its basis (nationality: the
census's question is nationality, and the page gives only those two shares).
The median age says why there is none: the table gives the mean age and broad
groups only. Each of the 14 districts takes its regions added together; the map
draws the two autonomous districts at both levels.

**Checks before anything is written.** Each table's men and women make its
total, for 2021 and for 1998; the national column is the census's 29,389,150;
the regions make the country within the table's rounding; every region and
district on the map is found once.

Usage:
    python -m scripts.fetch_census.cote_divoire_census
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json

SITE_URL = "https://rp2021.anstat.ci/"
ARCHIVE = "https://web.archive.org/web/2026/" + SITE_URL
SOURCE = ("Agence Nationale de la Statistique (ANStat) de Côte d'Ivoire, Recensement Général de "
          "la Population et de l'Habitat (RGPH) 2021, regional monograph page, Tableau "
          "synoptique de la région")
LICENCE = "ANStat publication (reuse with attribution)"
YEAR = 2021
NATIONAL = (15_344_990, 14_044_160, 29_389_150)
OUT = "cote_divoire_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The census site's page for each region, and the map's name for it (folded).
PAGES = {
    "district-autonome-abidjan-mono": "districtautonomedabidjan",
    "district-autonome-yamoussoukro-mono": "districtautonomedeyamoussoukro",
    "mono-region-gbokle": "gbokle", "mono-region-nawa": "nawa",
    "mono-region-de-san-pedro": "sanpedro", "region-indenie-djuablin-mono": "indeniedjuablin",
    "region-sud-comoe-mono": "sudcomoe", "region-folon-mono": "folon",
    "region-kabadougou-mono": "kabadougou", "region-goh-mono": "goh",
    "region-loh-djiboua-mono": "lohdjiboua", "region-belier-mono": "belier",
    "region-iffou-mono": "iffou", "region-moronou-mono": "moronou", "region-nzi-mono": "nzi",
    "region-agneby-tiassa-mono": "agnebytiassa", "region-grands-ponts-mono": "grandsponts",
    "region-la-me-mono": "me", "region-cavally-mono": "cavally", "region-guemon-mono": "guemon",
    "region-tonkpi-mono": "tonkpi", "region-haut-sassandra-mono": "hautsassandra",
    "region-marahoue-mono": "marahoue", "region-bagoue-mono": "bagoue",
    "region-poro-mono": "poro", "region-tchologo-mono": "tchologo",
    "region-gbeke-mono": "gbeke", "region-hambol-mono": "hambol",
    "region-bafing-mono": "bafing", "region-bere-mono": "bere",
    "region-du-worodougou-mono": "worodougou", "region-bounkani-mono": "bounkani",
    "region-gontougo-mono": "gontougo",
}
NO_MEDIAN = ("The 2021 census's synoptic table for the {unit} gives the mean age ({mean} "
             "years) and the population in broad age groups (under 15, 15 to 64, 65 and over), "
             "from which no median age can be taken.")


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def strip(page: str) -> str:
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()


def readings(tokens: list[str], start: int) -> list[tuple[int, int]]:
    """(value, end) for each way a number can be read from tokens[start:]."""
    if start >= len(tokens) or not tokens[start].isdigit():
        return []
    first = tokens[start]
    if len(first) > 3:
        return [(int(first), start + 1)]
    out, j = [(int(first), start + 1)], start + 1
    while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
        j += 1
        out.append((int("".join(tokens[start:j])), j))
    return out


def row_numbers(text: str, label: str, national: int) -> list[list[int | None]]:
    """The candidate (region 2021, region 1998) readings of a synoptic row, after
    the country's own figure; 1998 is None where the table gives '-'."""
    m = re.search(rf"{label}\s+((?:[\d-]+\s+){{1,12}})", text + " ")
    if not m:
        raise SystemExit(f"cote_divoire_census: no row {label!r}")
    tokens = m.group(1).split()
    starts = [end for value, end in readings(tokens, 0) if value == national]
    if not starts:
        raise SystemExit(f"cote_divoire_census: {label!r} does not open with {national:,}")
    out = []
    for value, end in readings(tokens, starts[0]):
        rest = tokens[end:]
        if rest and rest[0] == "-":
            out.append([value, None])
        for old, old_end in readings(tokens, end):
            out.append([value, old])
    return out


def synoptic(text: str) -> dict[str, Any]:
    """The region's 2021 (and 1998) men, women and total, and its mean age."""
    total = row_numbers(text, "Population totale", NATIONAL[2])
    men = row_numbers(text, "Population masculine", NATIONAL[0])
    women = row_numbers(text, "Population f[ée]minine", NATIONAL[1])
    # A region has well over 50,000 people; a reading of "1 352 900" as 1,352
    # (and the rest as 1998's) is the digits split in the wrong place.
    for t in (t for t in total if t[0] >= 50_000):
        for m in men:
            for w in women:
                if abs(m[0] + w[0] - t[0]) > 1:
                    continue
                if None not in (t[1], m[1], w[1]) and abs(m[1] + w[1] - t[1]) > 1:
                    continue
                mean = re.search(r"Age moyen de la population\s+([\d,]+)\s+([\d,]+)", text)
                return {"men": m[0], "women": w[0], "total": t[0],
                        "mean": mean.group(2).replace(",", ".") if mean else None}
    raise SystemExit("cote_divoire_census: the synoptic table's sexes do not make its total")


def page_facts(text: str) -> dict[str, Any]:
    facts = synoptic(text)
    seat = re.search(r"Sa capitale est ([^.]+?)\s*\.", text)
    facts["seat"] = seat.group(1).strip() if seat else None
    nat = re.search(r"compos[ée]e\s+(?:de|à)\s*([\d,]+)\s*%\s*d.Ivoiriens\s+et\s+([\d,]+)\s*%", text)
    facts["ivorian"] = (float(nat.group(1).replace(",", ".")), float(nat.group(2).replace(",", ".")))\
        if nat else None
    return facts


def nationality(shares: tuple[float, float], unit: str) -> dict[str, Any]:
    ivorian, other = shares
    return {"ethnicity": [{"group": "Ivorian", "pct": ivorian},
                          {"group": "Non-Ivorian", "pct": other}],
            "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
            "ethnicity_note": ("Nationality, not ethnicity: the 2021 census's shares of "
                               f"Ivorians and of other nationals among the {unit}'s residents, "
                               "as ANStat's regional page gives them; it gives no breakdown "
                               "by ethnic group or by country.")}


def build(facts: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    report: list[str] = []
    by_key = {PAGES[slug]: f for slug, f in facts.items()}
    src = {"name": SOURCE, "url": SITE_URL, "license": LICENCE, "year": YEAR}
    parents: dict[str, list[dict[str, Any]]] = {}
    for shape in admin2:
        f = by_key.get(fold(shape["name"]))
        if f is None:
            report.append(f"region polygon {shape['name']!r}: no page")
            continue
        parents.setdefault(shape["parent"], []).append(f)
        unit = "region" if not shape["name"].startswith("District") else "district"
        fields: dict[str, Any] = {
            "population": measure(f["total"], year=YEAR, source=SOURCE),
            "sex_ratio": measure(round(1000 * f["men"] / f["women"]),
                                 unit="males_per_1000_females", year=YEAR, source=SOURCE),
            "median_age": gap(NOT_AVAILABLE, NO_MEDIAN.format(unit=unit, mean=f["mean"] or "?"))
            if f["mean"] else gap(NOT_AVAILABLE),
        }
        cited = ["population", "sex_ratio"]
        if f["seat"]:
            fields["capital"] = f["seat"]
            cited.append("capital")
        if f["ivorian"]:
            fields.update(nationality(f["ivorian"], unit))
            cited.append("ethnicity")
        records.append(record(f"CIV-RGPH2021-{fold(shape['name'])}", shape["name"],
                              level="admin2", parent="CIV", country="CIV", match_by="shape_id",
                              shape_id=shape["id"],
                              sources=[{**src, "field": "/".join(cited)}], **fields))
    for shape in admin1:
        parts = parents.get(shape["id"], [])
        if not parts:
            report.append(f"district polygon {shape['name']!r}: no regions")
            continue
        men, women, total = (sum(p[k] for p in parts) for k in ("men", "women", "total"))
        fields = {
            "population": measure(total, year=YEAR, source=SOURCE),
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "median_age": gap(NOT_AVAILABLE, (
                "The 2021 census's synoptic tables give each region's mean age and broad age "
                "groups only, from which no median age can be taken.")),
        }
        if len(parts) > 1:
            fields["population_note"] = ("The 2021 census's counts of the district's "
                                         f"{len(parts)} regions, added.")
        elif parts[0]["seat"]:
            fields["capital"] = parts[0]["seat"]
        records.append(record(f"CIV-RGPH2021-district-{fold(shape['name'])}", shape["name"],
                              level="admin1", parent="CIV", country="CIV", match_by="shape_id",
                              shape_id=shape["id"],
                              sources=[{**src, "field": "population/sex_ratio"}], **fields))
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    facts = {}
    for slug in PAGES:
        body = http_get(ARCHIVE + slug + "/", cache=False, timeout=120)
        text = strip(body if isinstance(body, str) else body.decode("utf-8", "replace"))
        f = page_facts(text)
        log(f"  {slug}: {f['total']:,} ({f['men']:,} men), seat {f['seat']}, mean age "
            f"{f['mean']}, Ivorians {f['ivorian']}")
        facts[slug] = f
    made = sum(f["total"] for f in facts.values())
    if abs(made - NATIONAL[2]) > 50:
        raise SystemExit(f"cote_divoire_census: the regions make {made:,}, not {NATIONAL[2]:,}")
    log(f"  the regions make {made:,} against the country's {NATIONAL[2]:,}")
    admin1 = json.loads((SITE / "admin1" / "CIV.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CIV.units.json").read_text())
    records, report = build(facts, admin1, admin2)
    for line in report:
        log("  " + line)
    if report:
        raise SystemExit("cote_divoire_census: units left unplaced (above)")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
