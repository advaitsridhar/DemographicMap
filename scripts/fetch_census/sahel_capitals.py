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
kept -- but never a label that carries its class word (Guinea-Bissau's "Setor
de Bambadinca"): there the point's own name stands. Seats the name rules miss
but a checked point gives are listed in SEAT_POINTS (Niger's departments the
layer names otherwise, its cities drawn as units of their own, Kozah's seat
Kara, Guinea-Bissau's sector of Boé drawn under the label Madina do Boé). A
unit the layer gives no seat says so: how many of the units drawn here it
gives one, and what it has for this one (a point filed under another unit, a
point whose name is not the unit's, a polygon that is not the unit its label
names); Niger's departments are told what the layer, which gives the
communes' seats, gives for the commune of the department's name. The source
carries the dataset's year as HDX records it.

Usage:
    python -m scripts.fetch_census.sahel_capitals
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import re
import unicodedata
import zipfile
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, write_json

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
            "canghungo": "canchungo", "galomaro": "galomarocosse",
            "gamamundo": "gamamudoganadu", "stodomingos": "saodomingos",
            "cacheu": "cacheucalequisse", "bissauautonomoussector": "sectorautonomodebissau"},
    # The layer names the provinces of 2025: Oubritenga and Sanmatenga renamed.
    "BFA": {"oubritenga": "bassitenga", "sanmatenga": "sandbondtenga"},
    # The layer names Belbédji department Tarka (no point there bears either name).
    "NER": {"belbedji": "tarka"},
}
# Units whose point was checked and is not their seat as the map draws them,
# with what the visitor is told instead (after "OCHA's administrative
# boundaries for <country>, which give the seats of n of the N units drawn
# here, ..."): what the layer's point is.
EXCLUDED = {
    ("MRT", "fderick"): ("the layer names Zouérat, the wilaya's capital, for F'Dérik",
                         "name Zouérat, the capital of the wilaya, for it"),
    ("BEN", "akpomisserete"): ("the layer's name, Agpro, is not the commune's",
                               "give for this one a point named Agpro, not the commune's name"),
    ("TGO", "basmono"): ("the layer names Athiémé, a town in Benin across the Mono",
                         "name Athiémé, a town in Benin across the Mono, for it"),
    ("BEN", "aguegues"): ("the layer's name, Aguégué-Houédomè, is not the commune's",
                          "give for this one a point named Aguégué-Houédomè, not the "
                          "commune's name"),
    ("BEN", "semekpodji"): ("the layer's name, Sèmè, is not the commune's",
                            "give for this one a point named Sèmè, not the commune's name"),
    ("CPV", "nossasenhoradaajuda"): ("the layer names Porto dos Mosteiros, a village beside "
                                     "the municipality's seat",
                                     "name Porto dos Mosteiros for it, a village beside the "
                                     "municipality's seat"),
}
# Polygons that are not the unit their label names, with what the visitor is
# told. The polygon Guinea-Bissau's boundaries label Boé lies 1 km off the Caió
# sector polygon, in Cacheu (its centroid 16.08 W, 11.83 N); the sector of Boé
# is the Gabú polygon they label Madina do Boé, which holds the layer's point
# for Boé (14.217 W, 11.75 N, the town of Boé, once Madina do Boé) and takes it
# through SEAT_POINTS.
NOT_THE_UNIT = {
    ("GNB", "boe"): ("This polygon, labelled Boé, is an island 1 km off the Caió sector "
                     "polygon in the Cacheu region, not the sector of Boé, which lies in the "
                     "Gabú region; that sector's seat is shown on the polygon of Madina do "
                     "Boé."),
}
# Seats the layer files under another unit, each point placed on the map's
# polygons beforehand, with what the visitor is told (after the same opening as
# EXCLUDED's): Benin's So-Ava point is filed under Abomey-Calavi and lies in
# the polygon drawn as Abomey-Calavi (2.400 E, 6.500 N).
FILED_ELSEWHERE = {
    ("BEN", "soava"): ("file their one point named So-Ava under Abomey-Calavi, and it lies "
                       "inside the outline drawn here for Abomey-Calavi, not this commune's"),
}
# Units whose names the boundary file writes with their class word, and often
# cut or garbled (Guinea-Bissau's "Setor de Caiv" for Caió, "Setor de Gabv"
# for Gabú): the class word is not part of the unit's key, and no seat is ever
# written in the unit's spelling there -- the point's own name stands.
CLASS_WORDS = {"GNB": "setorde"}
# Seats the name rules miss, each point checked on the map's polygons
# (2026-10-17): the map's unit -> (the layer's unit, the point's name, both
# folded, and the seat as written, or None for the unit's own spelling).
# Niger's layer names several departments otherwise (Konni for
# Birni-N'Konni, Doutchi, Tagazar for Balléyara, Matameye for Kantché, whose
# seat is Matamèye) and spells some seats otherwise (Ayarou, Tillabery);
# Boboye's seat is Birni N'Gaouré; the cities of Maradi, Zinder and Tahoua
# are drawn as units of their own, each holding its own point. Kozah's seat
# is Kara (the layer has a point for each); Thiès's is the city, whose commune
# Thiès Ouest holds the layer's point; Malem Hodar's is spelt Maleme Hoddar.
# (Akjoujt's and Adjarra's points lie 3.4 and 2.2 km outside the polygons
# drawn under their names, in their neighbours, but are the towns the units
# are named for, and Tahoua's department has its seat in the city drawn
# beside it: the name rules take those.)
SEAT_POINTS = {
    ("NER", "ayerou"): ("ayerou", "ayarou", None),
    ("NER", "balleyara"): ("tagazar", "balleyara", None),
    ("NER", "bankilare"): ("bankillare", "bankilare", None),
    ("NER", "birninkonni"): ("konni", "birninkonni", None),
    ("NER", "boboye"): ("boboye", "birningaoure", None),
    ("NER", "dioundiou"): ("dioudiou", "dioundiou", None),
    ("NER", "dogondoutchi"): ("doutchi", "dogondoutchi", None),
    ("NER", "guidanroumdji"): ("guidanroumji", "guidanroumdji", None),
    ("NER", "kantche"): ("matameye", "matamaye", "Matamèye"),
    ("NER", "tesker"): ("tasker", "tesker", None),
    ("NER", "tillaberi"): ("tillaberi", "tillabery", None),
    ("NER", "maradi"): ("madarounfa", "maradi", None),
    ("NER", "zinder"): ("mirriah", "zinder", None),
    ("NER", "tahouaville"): ("tahoua", "tahoua", "Tahoua"),
    ("TGO", "kozah"): ("kozah", "kara", None),
    ("SEN", "thies"): ("thies", "thiesouest", "Thiès"),
    ("SEN", "malemhodar"): ("malemhodar", "malemehoddar", None),
    # Guinea-Bissau's sector of Boé, drawn in Gabú under the label "Madina do
    # Boé": the layer's point for Boé lies inside it (NOT_THE_UNIT).
    ("GNB", "madinadobo"): ("boe", "boe", None),
}
# What the second-level units are called, for the reason given where no seat is.
UNIT_WORDS = {"SEN": ("department", "departments"), "NER": ("department", "departments"),
              "TGO": ("prefecture", "prefectures"), "BEN": ("commune", "communes"),
              "GNB": ("sector", "sectors"), "CPV": ("parish", "parishes"),
              "BFA": ("province", "provinces"), "MLI": ("cercle", "cercles"),
              "MRT": ("moughataa", "moughataas")}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def filled(value: Any) -> bool:
    return value not in (None, "", "<Null>")


def base_key(iso3: str, name: str) -> str:
    """The unit's folded name without its class word (CLASS_WORDS)."""
    key = fold(name)
    word = CLASS_WORDS.get(iso3)
    if word and key.startswith(word):
        key = key[len(word):]
    return key


def unit_key(iso3: str, name: str) -> str:
    key = base_key(iso3, name)
    return ALIASES.get(iso3, {}).get(key, key)


def as_written(iso3: str, seat: str, u: dict[str, Any]) -> str:
    """The seat as written: the unit's own spelling where the layer spells the
    seat as a variant of the unit's name (Benin's "Kopargo" for Copargo), but
    never where the unit's name carries its class word (CLASS_WORDS): "Setor de
    Bambadinca" is no town's name, and the sector's seat is the layer's
    Bambadinca."""
    if iso3 in CLASS_WORDS:
        return seat
    if difflib.SequenceMatcher(None, fold(seat), fold(u["name"])).ratio() >= 0.7:
        return u["name"]
    return seat


def dataset_year(package: dict[str, Any]) -> int | None:
    """The year of the dataset's reference date, as HDX records it."""
    for key in ("dataset_date", "last_modified", "metadata_modified"):
        m = re.search(r"(19|20)\d{2}", str(package.get(key) or ""))
        if m:
            return int(m.group(0))
    return None


def source_of(country: str, page: str, year: int | None) -> dict[str, Any]:
    named = f"COD-AB, {year}" if year else "COD-AB"
    return {"field": "capital",
            "name": f"OCHA, {country} - Subnational Administrative Boundaries ({named}), "
                    "administrative capitals",
            "url": page, "license": "CC BY-IGO", **({"year": year} if year else {})}


def layer(iso3: str) -> tuple[list[dict[str, Any]], str, int | None]:
    """The capitals layer's points, the dataset's page and its year."""
    dataset, _ = COUNTRIES[iso3]
    package = json.loads(http_get(API + dataset, cache=False, timeout=120))["result"]
    year = dataset_year(package)
    log(f"  {iso3}: {dataset} dated {package.get('dataset_date')!r} -> {year}")
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
    return points, f"https://data.humdata.org/dataset/{dataset}", year


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


def point_name(p: dict[str, Any]) -> str:
    return str(p.get("name_1") or p.get("name") or "").strip()


def seat_of(iso3: str, u: dict[str, Any], points: list[dict[str, Any]],
            by_unit: dict[str, list[dict[str, Any]]], parent: str, shared: bool
            ) -> tuple[str | None, Any, str]:
    """(seat, its point, why not): the unit's seat by the layer, or None and
    the reason in the log's words."""
    key = unit_key(iso3, u["name"])
    pick = SEAT_POINTS.get((iso3, key))
    if pick:
        unit, wanted, written = pick
        hits = [p for p in points
                if fold(p.get("adm2_name")) == unit and fold(point_name(p)) == wanted]
        if len({point_name(p) for p in hits}) != 1:
            return None, None, f"the checked point {wanted!r} of {unit!r} is not in the layer"
        seat = written or as_written(iso3, point_name(hits[0]), u)
        return seat, hits[0]["_xy"], ""
    if (iso3, key) in NOT_THE_UNIT:
        return None, None, "left out, the polygon is not the unit its label names"
    if (iso3, key) in EXCLUDED:
        return None, None, f"left out, {EXCLUDED[(iso3, key)][0]}"
    found = by_unit.get(key, [])
    seat = choose(key, found, parent, shared)
    if seat is None:
        return None, None, ("no point" if not found
                            else "points " + str(sorted({p["_name"] for p in found})))
    xy = next(p["_xy"] for p in found if p["_name"] == seat)
    return as_written(iso3, seat, u), xy, ""


def no_seat(iso3: str, u: dict[str, Any], points: list[dict[str, Any]], given: int,
            drawn: int) -> str | None:
    """What the visitor is told where the layer gives this unit no seat: how
    many of the units drawn here it gives one, and what it has for this one.
    Niger's layer gives the communes' seats, so a department is told what it
    gives for the commune of its name."""
    _, country = COUNTRIES[iso3]
    word, words = UNIT_WORDS[iso3]
    key = unit_key(iso3, u["name"])
    if (iso3, key) in NOT_THE_UNIT:
        return NOT_THE_UNIT[(iso3, key)]
    if iso3 == "NER":
        head = (f"OCHA's administrative boundaries for {country} give the seats of the "
                "communes, not of the departments")
        own = [p for p in points if fold(p.get("adm2_name")) == key
               and fold(p.get("adm3_name")) == key and point_name(p)]
        if own:
            commune, named = str(own[0]["adm3_name"]).strip(), point_name(own[0])
            return head + (f", and the one they give for the commune of {commune} is named "
                           f"{named}, not {commune}.")
        return head + ", and they list no commune of this department's name."
    head = (f"OCHA's administrative boundaries for {country}, which give the seats of "
            f"{given:,} of the {drawn:,} {words} drawn here, ")
    if (iso3, key) in EXCLUDED:
        told = EXCLUDED[(iso3, key)][1]
        return head + told + "." if told else None
    if (iso3, key) in FILED_ELSEWHERE:
        return head + FILED_ELSEWHERE[(iso3, key)] + "."
    return head + f"give none for this {word}."


def build(iso3: str, points: list[dict[str, Any]], page: str, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], year: int | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    _, country = COUNTRIES[iso3]
    parents = {u["id"]: u["name"] for u in admin1}
    by_unit = seats(iso3, points)
    source = source_of(country, page, year)
    records, report = [], []
    keys = [unit_key(iso3, u["name"]) for u in admin2]
    found = [(u, *seat_of(iso3, u, points, by_unit, parents.get(u.get("parent"), ""),
                          keys.count(unit_key(iso3, u["name"])) > 1)) for u in admin2]
    given = sum(1 for _, seat, _, _ in found if seat)
    for u, seat, xy, why in found:
        if not is_silent(u.get("capital")):
            continue
        rid = f"{iso3}-CODAB-seat-{fold(u['name'])}-{u['id'][-6:]}"
        if seat is None:
            report.append(f"{u['name']}: {why}")
            note = no_seat(iso3, u, points, given, len(admin2))
            if note:
                # The layer is the source the note quotes, not of a figure shown.
                records.append(record(rid, u["name"], level="admin2", parent=iso3, country=iso3,
                                      match_by="shape_id", shape_id=u["id"],
                                      capital=gap(NOT_AVAILABLE, note),
                                      sources=[{**source, "field": "capital note"}]))
            continue
        log(f"    {iso3} {u['name']} [{u['id']}]: {seat} ({xy[0]:.5f}, {xy[1]:.5f})")
        records.append(record(rid, u["name"], level="admin2", parent=iso3, country=iso3,
                              match_by="shape_id", shape_id=u["id"], capital=seat,
                              sources=[source]))
    return records, report


def regions(iso3: str, points: list[dict[str, Any]], page: str, admin1: list[dict[str, Any]],
            admin2: list[dict[str, Any]], year: int | None = None
            ) -> tuple[list[dict[str, Any]], list[str]]:
    """First-level units' seats, where the layer has a point for a region (no
    second-level name) and that region is made of exactly the second-level
    units the map draws inside the unit: the same ground, whatever its name
    (Burkina Faso's layer names the regions of 2025, two of which are old
    regions renamed)."""
    _, country = COUNTRIES[iso3]
    source = source_of(country, page, year)
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
        points, page, year = layer(iso3)
        mine, report = build(iso3, points, page, admin1, admin2, year)
        silent = sum(1 for u in admin2 if is_silent(u.get("capital")))
        named = sum(1 for r in mine if isinstance(r.get("capital"), str))
        log(f"  {iso3}: {named} of {silent} empty capitals named, "
            f"{len(mine) - named} say why none is")
        first, more = regions(iso3, points, page, admin1, admin2, year)
        silent1 = sum(1 for u in admin1 if is_silent(u.get("capital")))
        log(f"  {iso3}: {len(first)} of {silent1} empty first-level capitals named")
        for line in report + more:
            log(f"    not named: {line}")
        records += mine + first
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
