#!/usr/bin/env python3
"""Morocco -- men per 1,000 women and mother tongue at the 2024 census, by region
and province.

The Haut-Commissariat au Plan publishes the results of the Recensement Général
de la Population et de l'Habitat of September 2024 on a public dashboard
(``resultats2024.rgphapps.ma``), whose tables answer the dashboard's own data
service (``API``) for anyone. Two are read here, for the Kingdom, every region
and province and the communes named in ``morocco_rgph2024.ACROSS_COMMUNES``:

* the municipal population by sex (``DATASET_SEXES``, the indicator
  "Population municipale"), and so men per 1,000 women;
* the shares of the population whose mother tongue is Arabic and Amazigh
  (``DATASET_TONGUES``).

Both are asked of the data service by zone, not read off the dashboard's saved
charts: those answer only their 10,000 largest rows, which leave out every
small commune and, for the mother tongues, every region and province.

The municipal population leaves out the people counted apart -- in barracks,
boarding schools, prisons and the like -- whom the legal population includes;
the sexes are published for it alone.

**Binding** is the legal-population reader's (``morocco_rgph2024``): HCP's
workbook of the legal population is read again for its regions and provinces
with their codes, bound to the polygons as that reader binds them (the
polygons the Western Sahara line cuts take no figure, and say why there), and
each bound unit takes the data service's rows of its name -- the same
office's names, reduced the same way. A commune of a province bound here that
lies across the Western Sahara line (Assa-Zag's Al Mahbass) is taken out of
its province and region: its men and women, and its speakers of each tongue.

**Checks before anything is written.** The Kingdom and every region and
province of the workbook must be answered, men and women each; every region's
provinces must make its men and its women; the regions must make the
Kingdom's; the two shares of a unit must not pass 100%.

Usage:
    python -m scripts.fetch_census.morocco_rgph2024_sexes
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any

from . import morocco_rgph2024 as legal
from ._shared import PROCESSED, http_get, log, measure, record, write_json
from common import USER_AGENT  # noqa: E402  (on the path through _shared)

API = "https://resultats2024.rgphapps.ma/api/v1/chart/data"
LANDING = "https://resultats2024.rgphapps.ma/"
# The dashboard's tables: its indicators by zone, area and sex (lot1_rgph), and
# its shares of the population by mother tongue (TAB_VF_LANGUES_MATERNELLES).
DATASET_SEXES = 84
DATASET_TONGUES = 109
POPULATION = "Population municipale"
TONGUES = {"Part de la population dont la langue maternelle est l'arabe (%)": "Arabic",
           "Part de la population dont la langue maternelle est l'amazigh (%)": "Amazigh"}
SOURCE = ("Haut-Commissariat au Plan (HCP), Recensement Général de la Population et de "
          "l'Habitat 2024, population municipale par sexe des régions, provinces et préfectures "
          "(plateforme des résultats du RGPH 2024)")
SOURCE_TONGUE = ("Haut-Commissariat au Plan (HCP), Recensement Général de la Population et de "
                 "l'Habitat 2024, langue maternelle de la population des régions, provinces et "
                 "préfectures (plateforme des résultats du RGPH 2024)")
LICENCE = legal.LICENCE
YEAR = 2024
OUT = "morocco_rgph2024_sexes.json"
KINGDOM = legal.key("Royaume du Maroc")
SEXES = {"Masculin": "men", "Féminin": "women"}
LIMIT = 50_000


def post(dataset: int, columns: list[str], filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The data service's rows of one table, grouped by ``columns`` and summed;
    a refusal, an error or a full page stops the run."""
    body = {"datasource": {"id": dataset, "type": "table"}, "force": False,
            "queries": [{"columns": columns,
                         "metrics": [{"expressionType": "SQL", "label": "v",
                                      "sqlExpression": 'SUM("Value(valeur indicateur)")'}],
                         "filters": filters, "row_limit": LIMIT}],
            "result_format": "json", "result_type": "full"}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json",
        "Accept": "application/json"})
    payload: dict[str, Any] = {}
    for wait in (5, 20, 60, None):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"morocco_rgph2024_sexes: the data service answers {exc.code}: "
                             f"{exc.read()[:300]!r}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if wait is None:
                raise SystemExit(f"morocco_rgph2024_sexes: {API} unreachable: {exc}")
            log(f"  retrying after {exc} in {wait}s")
            time.sleep(wait)
    results = payload.get("result") or []
    if len(results) != 1 or results[0].get("error"):
        raise SystemExit(f"morocco_rgph2024_sexes: the data service answers "
                         f"{json.dumps(payload)[:400]}")
    rows = results[0].get("data") or []
    if len(rows) >= LIMIT:
        raise SystemExit(f"morocco_rgph2024_sexes: {len(rows)} rows, a full page")
    return rows


def zone(row: dict[str, Any]) -> tuple[str, ...]:
    """(region,), (region, province) or (region, province, commune), as keys;
    the Kingdom is (KINGDOM,)."""
    names = [row.get("libelle_fr"), row.get("libelle_prov"), row.get("libelle_commune")]
    return tuple(legal.key(n) for n in names if n)


def read_sexes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """{"kingdom": {...}, "regions": {key: {...}}, "provinces": {(region key, key):
    {...}}, "communes": {(region, province, commune): {...}}} of the whole
    municipal population's men and women."""
    out: dict[str, Any] = {"kingdom": {}, "regions": defaultdict(dict),
                           "provinces": defaultdict(dict), "communes": defaultdict(dict)}
    for row in rows:
        if row.get("Sexe") not in SEXES or row.get("v") is None:
            continue
        where, sex, n = zone(row), SEXES[row["Sexe"]], int(round(float(row["v"])))
        if where == (KINGDOM,):
            out["kingdom"][sex] = n
            continue
        table = {1: "regions", 2: "provinces", 3: "communes"}[len(where)]
        key = where[0] if len(where) == 1 else where
        out[table][key][sex] = n
        out[table][key]["name"] = [v for v in (row.get("libelle_fr"), row.get("libelle_prov"),
                                                row.get("libelle_commune")) if v][-1]
        out[table][key]["zone"] = where
    return out


def read_tongues(rows: list[dict[str, Any]]) -> dict[tuple[str, ...], dict[str, float]]:
    """Zone -> {"Arabic": share, "Amazigh": share} of the whole population."""
    out: dict[tuple[str, ...], dict[str, float]] = defaultdict(dict)
    for row in rows:
        group = TONGUES.get(row.get("Titre de l'indicateur"))
        if group is None or row.get("v") is None:
            continue
        out[zone(row)][group] = float(row["v"])
    for where, got in out.items():
        if sum(got.values()) > 100.2:
            raise SystemExit(f"morocco_rgph2024_sexes: {where}'s mother tongues make "
                             f"{sum(got.values())}%")
    return out


def check(chart: dict[str, Any], table: dict[str, Any]) -> None:
    """Every region's provinces make its men and women, the regions the
    Kingdom's, and every unit of HCP's workbook is answered."""
    for sex in SEXES.values():
        if sex not in chart["kingdom"]:
            raise SystemExit(f"morocco_rgph2024_sexes: no {sex} for the Kingdom")
    for rkey, region in chart["regions"].items():
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
        raise SystemExit(f"morocco_rgph2024_sexes: regions not answered: {sorted(missing)}")
    provinces = {legal.key(p["name"]) for p in table["provinces"].values()}
    have = {k for _, k in chart["provinces"]}
    if provinces - have:
        raise SystemExit(f"morocco_rgph2024_sexes: provinces not answered: "
                         f"{sorted(provinces - have)}")


def across(chart: dict[str, Any], province: str) -> list[dict[str, Any]]:
    """The communes of a province that lie across the Western Sahara line, with
    their men and women; each must be answered, once."""
    out = []
    names = [n for p, ns in legal.ACROSS_COMMUNES.items() if legal.key(p) == legal.key(province)
             for n in ns]
    for name in names:
        hits = [c for (r, p, k), c in chart["communes"].items()
                if p == legal.key(province) and name in k]
        if len(hits) != 1 or not all(s in hits[0] for s in SEXES.values()):
            raise SystemExit(f"morocco_rgph2024_sexes: {province}'s commune {name!r} is "
                             f"answered {len(hits)} times: {hits}")
        out.append(hits[0])
    return out


def tongue_shares(shares: dict[str, float], people: int, less: list[tuple[dict[str, float], int]]
                  ) -> dict[str, float]:
    """A unit's shares without the communes in ``less`` ((shares, people) each),
    weighted by the municipal population."""
    if not less:
        return shares
    left = people - sum(n for _, n in less)
    return {g: round((s * people - sum(cs.get(g, 0) * n for cs, n in less)) / left, 1)
            for g, s in shares.items()}


def build(chart: dict[str, Any], table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], tongues: dict[tuple[str, ...], dict[str, float]] | None
          = None) -> tuple[list[dict[str, Any]], list[str]]:
    bound, report = legal.build(table, admin1, admin2)
    by_province = {k: (r, v) for (r, k), v in chart["provinces"].items()}
    tongues = tongues or {}
    out = []
    for rec in bound:
        code = int((rec.get("codes") or {}).get("hcp") or 0)
        if not code or "value" not in (rec.get("population") or {}):
            continue                                # across the line: said there
        row = table["regions"].get(code) if rec["level"] == "admin1" else \
            table["provinces"].get(code)
        if row is None:
            continue
        if rec["level"] == "admin1":
            found, where = chart["regions"].get(legal.key(row["name"])), (legal.key(row["name"]),)
            provinces = [p["name"] for c, p in table["provinces"].items() if c // 1000 == code]
        else:
            region, found = by_province.get(legal.key(row["name"]), (None, None))
            where, provinces = (region, legal.key(row["name"])), [row["name"]]
        if not found or not found.get("women"):
            report.append(f"{row['name']}: no sexes answered")
            continue
        less = [(p, c) for p in provinces for c in across(chart, p)]
        men = found["men"] - sum(c["men"] for _, c in less)
        women = found["women"] - sum(c["women"] for _, c in less)
        without = ""
        if less:
            without = (" without " + " and ".join(
                f"the commune of {c['name']} ({c['men'] + c['women']:,} people"
                + (f", in {p} province" if rec["level"] == "admin1" else "") + ")"
                for p, c in less) + ", which lies south of the Western Sahara line")
        fields: dict[str, Any] = {
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "sex_ratio_note": (f"Men per 1,000 women in the municipal population of "
                               f"{row['name']} at the 2024 census{without}: {men:,} men and "
                               f"{women:,} women. The municipal population leaves out the "
                               "people counted apart, in barracks, boarding schools, prisons "
                               "and the like."),
            "sources": [{"field": "sex_ratio", "name": SOURCE, "url": LANDING,
                         "license": LICENCE, "year": YEAR}]}
        shares = tongues.get(where)
        if shares:
            minus = []
            for _, c in less:
                cs = tongues.get(c["zone"])
                if cs is None:
                    raise SystemExit(f"morocco_rgph2024_sexes: no mother tongues for "
                                     f"{c['name']}")
                minus.append((cs, c["men"] + c["women"]))
            got = tongue_shares(shares, found["men"] + found["women"], minus)
            fields["language"] = [{"group": g, "pct": v} for g, v in
                                  sorted(got.items(), key=lambda kv: (-kv[1], kv[0]))]
            fields["language_basis"] = "mother tongue"
            fields["language_year"] = YEAR
            fields["language_note"] = (
                f"Mother tongue at the 2024 census: the shares of the population of "
                f"{row['name']}{without} whose mother tongue is Arabic and Amazigh (Tachelhit, "
                "Tamazight or Tarifit). The two need not make 100%: the rest have another "
                "mother tongue.")
            fields["sources"].append({"field": "language", "name": SOURCE_TONGUE,
                                      "url": LANDING, "license": LICENCE, "year": YEAR})
        out.append(record(
            f"MAR-RGPH2024-SEX-{code}", rec["name"], level=rec["level"], parent="MAR",
            country="MAR", match_by="shape_id", shape_id=rec["shape_id"],
            codes={"hcp": str(code)}, **fields))
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
    communes = sorted({n for names in legal.ACROSS_COMMUNES.values() for n in names})
    above = [{"col": "Milieu", "op": "==", "val": "Ensemble"},
             {"col": "libelle_commune", "op": "IS NULL"}]
    rows = post(DATASET_SEXES, ["libelle_fr", "libelle_prov", "Sexe"],
                above + [{"col": "Key(Nom indicateur)", "op": "==", "val": POPULATION}])
    commune_rows = post(DATASET_SEXES, ["libelle_fr", "libelle_prov", "libelle_commune", "Sexe"],
                        [{"col": "Milieu", "op": "==", "val": "Ensemble"},
                         {"col": "Key(Nom indicateur)", "op": "==", "val": POPULATION},
                         {"col": "libelle_commune", "op": "IS NOT NULL"}])
    commune_rows = [r for r in commune_rows
                    if any(n in legal.key(r.get("libelle_commune")) for n in communes)]
    chart = read_sexes(rows + commune_rows)
    for key, c in chart["communes"].items():
        log(f"  commune across the line: {key} {c}")
    log(f"  the Kingdom {chart['kingdom']}, {len(chart['regions'])} regions, "
        f"{len(chart['provinces'])} provinces, {len(chart['communes'])} communes")
    check(chart, table)
    tongue_rows = post(DATASET_TONGUES, ["libelle_fr", "libelle_prov", "libelle_commune",
                                         "Titre de l'indicateur"],
                       [{"col": "Milieu", "op": "==", "val": "Ensemble"},
                        {"col": "Sexe", "op": "==", "val": "Ensemble"}])
    tongue_rows = [r for r in tongue_rows if not r.get("libelle_commune")
                   or any(n in legal.key(r.get("libelle_commune")) for n in communes)]
    tongues = read_tongues(tongue_rows)
    log(f"  mother tongues for {len(tongues)} zones; the Kingdom {tongues.get((KINGDOM,))}")
    admin1 = json.loads((legal.SITE / "admin1" / "MAR.units.json").read_text())
    admin2 = json.loads((legal.SITE / "admin2" / "MAR.units.json").read_text())
    records, report = build(chart, table, admin1, admin2, tongues)
    for line in report:
        log("  " + line)
    for r in records:
        log(f"  {r['level']} {r['name'][:40]:40} {r['sex_ratio']['value']} "
            f"{[(g['group'], g['pct']) for g in r.get('language') or []]}")
    log(f"  {sum(r['level'] == 'admin1' for r in records)} regions and "
        f"{sum(r['level'] == 'admin2' for r in records)} provinces written; "
        f"{sum(bool(r.get('language')) for r in records)} with mother tongues")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
