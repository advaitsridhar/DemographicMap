#!/usr/bin/env python3
"""West Africa and the Sahel -- second-level units' seats, from OCHA's boundary sets.

OCHA's Common Operational Datasets of administrative boundaries (COD-AB, HDX)
carry, beside the polygons, a layer of the units' capitals: one point per
department, prefecture, sector, moughataa, commune or cercle, named for its
seat, as the countries' mapping and statistics offices gave it to OCHA. Where
the map's own unit has no capital at all, this names it from that layer.

**Binding.** By the unit's name against the layer's unit name (each country's
spellings in ALIASES), not by the map's polygons, which the runner does not
have. Where a unit has several points under its name (Senegal's and Togo's
layers mix a few arrondissements' seats in with the departments'), the one
named for the unit is taken when there is exactly one, and none otherwise;
Niger's layer gives the communes' seats, and only a department whose seat
point bears the department's name is taken. Every point was placed on the
map's polygons beforehand (2026-10-17): EXCLUDED lists the units whose point
falls in another polygon or whose name is not the seat's, and they are left as
they are.

**First-level units.** Where a layer also has a point for each region (one
with no second-level name: Burkina Faso's), a first-level unit with no capital
takes its region's seat when the layer's region is made of exactly the
second-level units the map draws inside the unit -- the same ground, whatever
it is called now (Burkina Faso's layer names the regions of 2025, of which
Kadiogo and Djôrô are the old Centre and Sud-Ouest renamed).

Only units whose capital is empty on the map are written: a capital another
source names is not replaced. Where the layer spells the seat as a variant of
the unit's own name (Benin's "Kopargo" for Copargo), the unit's spelling is
kept.

Usage:
    python -m scripts.fetch_census.sahel_capitals
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import unicodedata
import zipfile
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json

API = "https://data.humdata.org/api/3/action/package_show?id="
SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "sahel_capitals.json"

COUNTRIES = {
    "SEN": ("cod-ab-sen", "Senegal"), "NER": ("cod-ab-ner", "Niger"),
    "TGO": ("cod-ab-tgo", "Togo"), "BEN": ("cod-ab-ben", "Benin"),
    "GNB": ("cod-ab-gnb", "Guinea-Bissau"), "CPV": ("cod-ab-cpv", "Cabo Verde"),
    "BFA": ("cod-ab-bfa", "Burkina Faso"), "MLI": ("cod-ab-mli", "Mali"),
    "MRT": ("cod-ab-mrt", "Mauritania"),
}
# The map's unit (folded) -> the layer's unit name (folded), per country.
ALIASES = {
    "SEN": {"medinayoroufoula": "medinayorofoulah", "tivaoune": "tivaouane"},
    "TGO": {"tandjouare": "tandjoare", "lomecommune": "lomecommune"},
    "MLI": {"tombouctou": "timbuktu"},
    "MRT": {"basseknou": "bassikounou", "boutilimitt": "boutilimit", "chinguitti": "chinguity",
            "eayouneelatrous": "aioun", "elmejrya": "moudjeria", "koubenni": "kobeni",
            "magtalahjar": "maghtalahjar", "moughataadenneama": "nema",
            "selibabi": "selibaby", "tijigja": "tidjikja", "timbedgha": "timbedra"},
    "GNB": {"catie": "catio", "quinh": "quinhamel", "gabv": "gabu", "caiv": "caio",
            "canghungo": "canchungo", "madinadobo": "boe", "galomaro": "galomarocosse",
            "gamamundo": "gamamudoganadu", "stodomingos": "saodomingos",
            "cacheu": "cacheucalequisse", "bissauautonomoussector": "sectorautonomodebissau"},
}
# Units whose point was checked and is not their seat as the map draws them.
EXCLUDED = {
    ("MRT", "akjoujt"): "the point lies 3.4 km outside, in the polygon drawn as Benichab",
    ("MRT", "fderick"): "the layer names Zouérat, the wilaya's capital, for F'Dérik",
    ("BEN", "adjarra"): "the point lies 2.2 km outside, in the polygon drawn as Avrankou",
    ("BEN", "akpomisserete"): "the layer's name, Agpro, is not the commune's seat's",
    ("NER", "tahoua"): "the point is the city of Tahoua, drawn as a polygon of its own",
    ("TGO", "kozah"): "the layer has two points, Kara and Kozah, and the seat is Kara",
    ("TGO", "basmono"): "the layer names Athiémé, a town in Benin across the Mono",
    ("GNB", "boe"): "the polygon drawn as Boé lies in Cacheu, far from the sector of Boé",
    ("SEN", "thies"): "the layer's point is Thiès Ouest, one of the city's communes",
    ("BEN", "aguegues"): "the layer's Aguégué-Houédomè could not be confirmed as the seat",
    ("BEN", "semekpodji"): "the layer's Sèmè could not be confirmed as the seat",
    ("CPV", "nossasenhoradaajuda"): ("the layer names Porto dos Mosteiros, a village beside "
                                     "the municipality's seat"),
}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def filled(value: Any) -> bool:
    return value not in (None, "", "<Null>")


def unit_key(iso3: str, name: str) -> str:
    key = fold(name)
    if iso3 == "GNB" and key.startswith("setorde"):
        key = key[len("setorde"):]
    return ALIASES.get(iso3, {}).get(key, key)


def layer(iso3: str) -> tuple[list[dict[str, Any]], str]:
    """The capitals layer's points, and the dataset's page."""
    dataset, _ = COUNTRIES[iso3]
    package = json.loads(http_get(API + dataset, cache=False, timeout=120))["result"]
    urls = [r["url"] for r in package.get("resources") or []
            if str(r.get("url", "")).endswith("admin_boundaries.geojson.zip")]
    if not urls:
        raise SystemExit(f"sahel_capitals: {dataset} has no GeoJSON boundary set")
    blob = http_get(urls[0], binary=True, cache=False, timeout=300)
    points = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for name in zf.namelist():
            if name.endswith("admincapitals.geojson"):
                for f in json.loads(zf.read(name)).get("features") or []:
                    geom = f.get("geometry") or {}
                    if geom.get("type") == "Point":
                        points.append({**(f.get("properties") or {}),
                                       "_xy": geom["coordinates"][:2]})
    log(f"  {iso3}: {len(points)} capital points in {dataset}")
    return points, f"https://data.humdata.org/dataset/{dataset}"


def seats(iso3: str, points: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """{the layer's unit (folded): [its seat points]} for second-level units."""
    out: dict[str, list[dict[str, Any]]] = {}
    for p in points:
        unit = p.get("adm2_name")
        if not filled(unit):
            continue
        name = str(p.get("name_1") or p.get("name") or "").strip()
        if iso3 == "BFA" and filled(p.get("adm3_name")):
            continue                      # a commune's seat
        if iso3 == "NER" and fold(name) != fold(unit):
            continue                      # a commune's seat
        out.setdefault(fold(unit), []).append({**p, "_name": name})
    return out


def choose(key: str, found: list[dict[str, Any]], parent: str, shared: bool = False
           ) -> str | None:
    """The seat: the one name the unit's points give, after keeping those of the
    unit's own region where the name is shared, and the one named for the unit
    where several remain. A name the map gives to several units (Cabo Verde's
    parishes) is taken only from a point of the unit's own region."""
    names = sorted({p["_name"] for p in found})
    if (len(names) > 1 or shared) and parent:
        within = sorted({p["_name"] for p in found if fold(p.get("adm1_name")) == fold(parent)})
        if within or shared:
            names = within
    if len(names) > 1:
        own = [n for n in names if fold(n) == key]
        names = own if len(own) == 1 else []
    return names[0] if len(names) == 1 else None


def is_silent(value: Any) -> bool:
    return isinstance(value, dict) and "status" in value and not (value.get("note") or "").strip()


def build(iso3: str, points: list[dict[str, Any]], page: str, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    _, country = COUNTRIES[iso3]
    parents = {u["id"]: u["name"] for u in admin1}
    by_unit = seats(iso3, points)
    source = {"field": "capital",
              "name": f"OCHA, {country} - Subnational Administrative Boundaries (COD-AB), "
                      "administrative capitals", "url": page, "license": "CC BY-IGO"}
    records, report = [], []
    keys = [unit_key(iso3, u["name"]) for u in admin2]
    for u in admin2:
        if not is_silent(u.get("capital")):
            continue
        key = unit_key(iso3, u["name"])
        shared = keys.count(key) > 1
        if (iso3, key) in EXCLUDED:
            report.append(f"{u['name']}: left out, {EXCLUDED[(iso3, key)]}")
            continue
        found = by_unit.get(key, [])
        seat = choose(key, found, parents.get(u.get("parent"), ""), shared)
        if seat is None:
            report.append(f"{u['name']}: {'no point' if not found else 'points ' + str(sorted({p['_name'] for p in found}))}")
            continue
        xy = next(p["_xy"] for p in found if p["_name"] == seat)
        if difflib.SequenceMatcher(None, fold(seat), fold(u["name"])).ratio() >= 0.7:
            seat = u["name"]               # the seat bears the unit's name
        log(f"    {iso3} {u['name']} [{u['id']}]: {seat} ({xy[0]:.5f}, {xy[1]:.5f})")
        records.append(record(f"{iso3}-CODAB-seat-{fold(u['name'])}-{u['id'][-6:]}", u["name"],
                              level="admin2", parent=iso3, country=iso3, match_by="shape_id",
                              shape_id=u["id"], capital=seat, sources=[source]))
    return records, report


def regions(iso3: str, points: list[dict[str, Any]], page: str, admin1: list[dict[str, Any]],
            admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """First-level units' seats, where the layer has a point for a region (no
    second-level name) and that region is made of exactly the second-level
    units the map draws inside the unit: the same ground, whatever its name
    (Burkina Faso's layer names the regions of 2025, two of which are old
    regions renamed)."""
    _, country = COUNTRIES[iso3]
    source = {"field": "capital",
              "name": f"OCHA, {country} - Subnational Administrative Boundaries (COD-AB), "
                      "administrative capitals", "url": page, "license": "CC BY-IGO"}
    seat_of: dict[str, set[str]] = {}
    made_of: dict[str, set[str]] = {}
    for p in points:
        region = p.get("adm1_name")
        if not filled(region):
            continue
        if filled(p.get("adm2_name")):
            made_of.setdefault(fold(region), set()).add(unit_key(iso3, p["adm2_name"]))
        elif not filled(p.get("adm3_name")):
            seat_of.setdefault(fold(region), set()).add(
                str(p.get("name_1") or p.get("name") or "").strip())
    records, report = [], []
    for u in admin1:
        if not is_silent(u.get("capital")):
            continue
        children = {unit_key(iso3, c["name"]) for c in admin2 if c.get("parent") == u["id"]}
        same = [r for r, kids in made_of.items() if children and kids == children]
        seats_ = sorted(seat_of.get(same[0], set())) if len(same) == 1 else []
        if len(seats_) != 1 or not seats_[0]:
            report.append(f"{u['name']} (first level): "
                          + ("no region of the layer is made of its units" if len(same) != 1
                             else f"the region's points name {seats_}"))
            continue
        log(f"    {iso3} {u['name']} [{u['id']}] (first level, the layer's {same[0]}): "
            f"{seats_[0]}")
        records.append(record(f"{iso3}-CODAB-seat1-{fold(u['name'])}-{u['id'][-6:]}", u["name"],
                              level="admin1", parent=iso3, country=iso3, match_by="shape_id",
                              shape_id=u["id"], capital=seats_[0], sources=[source]))
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    records: list[dict[str, Any]] = []
    for iso3 in COUNTRIES:
        admin1 = json.loads((SITE / "admin1" / f"{iso3}.units.json").read_text())
        admin2 = json.loads((SITE / "admin2" / f"{iso3}.units.json").read_text())
        points, page = layer(iso3)
        mine, report = build(iso3, points, page, admin1, admin2)
        silent = sum(1 for u in admin2 if is_silent(u.get("capital")))
        log(f"  {iso3}: {len(mine)} of {silent} empty capitals named")
        first, more = regions(iso3, points, page, admin1, admin2)
        silent1 = sum(1 for u in admin1 if is_silent(u.get("capital")))
        log(f"  {iso3}: {len(first)} of {silent1} empty first-level capitals named")
        for line in report + more:
            log(f"    not named: {line}")
        records += mine + first
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
