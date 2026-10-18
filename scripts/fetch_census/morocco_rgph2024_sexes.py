#!/usr/bin/env python3
"""Morocco -- men per 1,000 women at the 2024 census, by region and province.

The Haut-Commissariat au Plan publishes the results of the Recensement Général
de la Population et de l'Habitat of September 2024 on a public dashboard
(``resultats2024.rgphapps.ma``). Its saved chart "DEMOGRAPHIE: Population
Municipale" (``CHART``) answers with the municipal population of the Kingdom,
every region, province and prefecture, and the communes, by sex and by urban
and rural parts. Read here: the whole municipal population's men and women of
every region and province, and so men per 1,000 women.

The municipal population leaves out the people counted apart -- in barracks,
boarding schools, prisons and the like -- whom the legal population includes;
the sexes are published for it alone.

**Binding** is the legal-population reader's (``morocco_rgph2024``): HCP's
workbook of the legal population is read again for its regions and provinces
with their codes, bound to the polygons as that reader binds them (the
polygons the Western Sahara line cuts take no figure, and say why there), and
each bound unit takes the dashboard's row of its name -- the same office's
names, reduced the same way.

**Checks before anything is written.** The chart's rows must hold the Kingdom
and every region and province of the workbook, men and women each; every
region's provinces must make its men and its women; the regions must make the
Kingdom's.

Usage:
    python -m scripts.fetch_census.morocco_rgph2024_sexes
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from . import morocco_rgph2024 as legal
from ._shared import PROCESSED, http_get, log, measure, record, write_json

CHART = "https://resultats2024.rgphapps.ma/api/v1/chart/807/data/?format=json"
LANDING = "https://resultats2024.rgphapps.ma/"
SOURCE = ("Haut-Commissariat au Plan (HCP), Recensement Général de la Population et de "
          "l'Habitat 2024, population municipale par sexe des régions, provinces et préfectures "
          "(plateforme des résultats du RGPH 2024)")
LICENCE = legal.LICENCE
YEAR = 2024
OUT = "morocco_rgph2024_sexes.json"
KINGDOM = legal.key("Royaume du Maroc")
SEXES = {"Masculin": "men", "Féminin": "women"}


def read_chart(body: dict[str, Any]) -> dict[str, Any]:
    """{"kingdom": {...}, "regions": {key: {...}}, "provinces": {(region key,
    key): {...}}} of the whole municipal population's men and women."""
    results = body.get("result") or []
    if len(results) != 1:
        raise SystemExit(f"morocco_rgph2024_sexes: the chart answers {len(results)} results")
    data = results[0].get("data") or []
    value = next((c for c in results[0].get("colnames", []) if "valeur" in c.lower()), None)
    if value is None:
        raise SystemExit(f"morocco_rgph2024_sexes: no value column in {results[0].get('colnames')}")
    out: dict[str, Any] = {"kingdom": {}, "regions": defaultdict(dict),
                           "provinces": defaultdict(dict)}
    for row in data:
        if row.get("Milieu") != "Ensemble" or row.get("Sexe") not in SEXES:
            continue
        if row.get(value) is None:
            continue
        parts = [p.strip() for p in str(row.get("Zone") or "").split("->")]
        sex, n = SEXES[row["Sexe"]], int(round(float(row[value])))
        if len(parts) == 1 and legal.key(parts[0]) == KINGDOM:
            out["kingdom"][sex] = n
        elif len(parts) == 1:
            out["regions"][legal.key(parts[0])][sex] = n
            out["regions"][legal.key(parts[0])]["name"] = parts[0]
        elif len(parts) == 2:
            out["provinces"][(legal.key(parts[0]), legal.key(parts[1]))][sex] = n
            out["provinces"][(legal.key(parts[0]), legal.key(parts[1]))]["name"] = parts[1]
    return out


def check(chart: dict[str, Any], table: dict[str, Any]) -> None:
    """The chart answers its 10,000 largest rows, so a unit too small for that
    is missing: Aousserd's men, south of the Western Sahara line, are. The
    regions the line cuts are written nowhere and are not checked below
    their own row; everything else must be whole."""
    across = {legal.key(r["name"]) for c, r in table["regions"].items()
              if c in legal.CLAIM_LINE_REGIONS}
    for sex in SEXES.values():
        if sex not in chart["kingdom"]:
            raise SystemExit(f"morocco_rgph2024_sexes: no {sex} for the Kingdom")
    for rkey, region in chart["regions"].items():
        if rkey in across:
            continue
        for sex in SEXES.values():
            made = sum(p.get(sex, 0) for (r, _), p in chart["provinces"].items() if r == rkey)
            if sex not in region or made != region[sex]:
                raise SystemExit(f"morocco_rgph2024_sexes: {region.get('name')}'s provinces make "
                                 f"{made:,} {sex}, the region {region.get(sex)}")
    for sex in SEXES.values():
        made = sum(r[sex] for r in chart["regions"].values())
        if made != chart["kingdom"][sex]:
            raise SystemExit(f"morocco_rgph2024_sexes: the regions make {made:,} {sex}, the "
                             f"Kingdom {chart['kingdom'][sex]:,}")
    names = {legal.key(r["name"]) for r in table["regions"].values()}
    missing = names - set(chart["regions"])
    if missing:
        raise SystemExit(f"morocco_rgph2024_sexes: regions not in the chart: {sorted(missing)}")
    provinces = {legal.key(p["name"]) for c, p in table["provinces"].items()
                 if c // 1000 not in legal.CLAIM_LINE_REGIONS}
    have = {k for _, k in chart["provinces"]}
    if provinces - have:
        raise SystemExit(f"morocco_rgph2024_sexes: provinces not in the chart: "
                         f"{sorted(provinces - have)}")


def build(chart: dict[str, Any], table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    bound, report = legal.build(table, admin1, admin2)
    by_province = {k: v for (_, k), v in chart["provinces"].items()}
    out = []
    for rec in bound:
        code = int((rec.get("codes") or {}).get("hcp") or 0)
        if not code or "value" not in (rec.get("population") or {}):
            continue                                # across the line: said there
        row = table["regions"].get(code) if rec["level"] == "admin1" else \
            table["provinces"].get(code)
        if row is None:
            continue
        found = (chart["regions"] if rec["level"] == "admin1" else by_province).get(
            legal.key(row["name"]))
        if not found or not found.get("women"):
            report.append(f"{row['name']}: no sexes in the chart")
            continue
        men, women = found["men"], found["women"]
        out.append(record(
            f"MAR-RGPH2024-SEX-{code}", rec["name"], level=rec["level"], parent="MAR",
            country="MAR", match_by="shape_id", shape_id=rec["shape_id"],
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            sex_ratio_note=(f"Men per 1,000 women in the municipal population of "
                            f"{row['name']} at the 2024 census: {men:,} men and {women:,} "
                            "women. The municipal population leaves out the people counted "
                            "apart, in barracks, boarding schools, prisons and the like."),
            codes={"hcp": str(code)},
            sources=[{"field": "sex_ratio", "name": SOURCE, "url": LANDING,
                      "license": LICENCE, "year": YEAR}]))
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    blob = http_get(legal.URL, binary=True, cache=False, timeout=120)
    if blob[:2] != b"PK":
        raise SystemExit(f"morocco_rgph2024_sexes: {legal.URL} is not a workbook")
    table = legal.read(blob)
    chart = read_chart(json.loads(http_get(CHART, cache=False, timeout=180)))
    log(f"  chart: the Kingdom {chart['kingdom']}, {len(chart['regions'])} regions, "
        f"{len(chart['provinces'])} provinces")
    check(chart, table)
    admin1 = json.loads((legal.SITE / "admin1" / "MAR.units.json").read_text())
    admin2 = json.loads((legal.SITE / "admin2" / "MAR.units.json").read_text())
    records, report = build(chart, table, admin1, admin2)
    for line in report:
        log("  " + line)
    for r in records:
        log(f"  {r['level']} {r['name'][:40]:40} {r['sex_ratio']['value']}")
    log(f"  {sum(r['level'] == 'admin1' for r in records)} regions and "
        f"{sum(r['level'] == 'admin2' for r in records)} provinces written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
