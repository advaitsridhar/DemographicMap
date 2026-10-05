#!/usr/bin/env python3
"""Religion and ethnicity on the polygons no one census area is: Myanmar's
composed districts and Metro Manila's numbered districts.

Both countries' compositions reach this map through the US Census Bureau's
subnational tables (``uscb.py``), which give each census area to the polygon
of its own name. That is right wherever the boundary file draws the census's
areas, and this file mends the two places where it does not. It reads the
same workbooks with ``uscb.py``'s own functions, so every group label is the
one that reader publishes and the group tree already files.

**Myanmar** -- religion from the 2014 census; ethnicity from the Department of
Population's 2018 Township Profiles (reference date 1 April 2017), the
census's own ethnicity tables never having been released. Both are on the
workbook's "Ethnicity" sheet, under the prefixes ``RLG_`` and ``ETH_``. The
boundary file's 74 districts are older than the census's (``myanmar_age.py``
measured them): nine polygons are each the sum of census districts and
self-administered-zone townships (``myanmar_age.COMPOSED``), and "Yangon
(West)" is the census district the workbook calls "YANGON". By name alone,
``uscb.py`` gives six of the nine the figures of the one census district
inside them that shares the name -- Hkamti without the Naga zone, Taunggyi
without the Danu and Pa-O zones, Kyaukme without the Pa Laung zone, Mindat
without Matupi, Katha without Kawlin, Tachileik without Mong Hpayak -- and
leaves Laukkaing, Hopang, Matman and Yangon (West) empty. Here all ten take
the sum of their parts, the same parts their ages are built from
(``myanmar_age.crosswalk``). At the first level the map's Mandalay polygon
also holds Nay Pyi Taw's districts, so it takes the two regions summed.

**The Philippines** -- the 2020 Census of Population and Housing. The
boundary file draws Metro Manila as four numbered districts and the census
counts its seventeen cities and municipality. ``uscb.py`` puts the City of
Manila on the First District and declares the other sixteen shapeless, so the
Second, Third and Fourth districts carry nothing. Here each takes the sum of
the places that make it, as the Philippine Statistics Authority defines the
districts (``NCR_DISTRICTS``).

**Checks**, each a refusal: in Myanmar every district's and zone's townships
make it, group by group, for both questions; every census district and zone
township is on exactly one polygon; the polygons make the Union's row; and a
state or region the map draws whole is the sum of the polygons inside it. In
the Philippines the region's seventeen places make its row, group by group,
and every one of them is the First District's or one of the three summed
here, exactly once.

Usage:
    python -m scripts.fetch_census.sea_composed
"""

from __future__ import annotations

import argparse
import io
from collections import defaultdict
from typing import Any

from . import myanmar_age, uscb
from ._shared import PROCESSED, http_get, log, record, shares, write_json
from .sea_common import drawn, fold

OUT = "sea_composed.json"
# A group's count in a whole against its parts' sum: the workbooks print
# whole people, so anything past rounding is a different count.
SLACK = 0.5

# Polygons the census's districts reach only by a name ``uscb.py`` does not
# know: the census calls West Yangon district "YANGON" (myanmar_age.ALIASES),
# and the site's Yangon (West) carries no religion or ethnicity.
MMR_BY_ALIAS = frozenset({"Yangon (West)"})

NCR = "National Capital Region"
# The Philippine Statistics Authority's four districts of the National
# Capital Region, by the names the US Census Bureau's tables give its places
# (Quezon City is "Quezon" there).
NCR_DISTRICTS = {
    "NCR, Second District": ("Mandaluyong", "Marikina", "Pasig", "Quezon", "San Juan"),
    "NCR, Third District": ("Caloocan", "Malabon", "Navotas", "Valenzuela"),
    "NCR, Fourth District": ("Las Piñas", "Makati", "Muntinlupa", "Parañaque", "Pasay",
                             "Pateros", "Taguig"),
}
# Bound to "NCR, City of Manila, First District" by uscb.py already.
NCR_FIRST = "Manila"


def labels(names: list[str], aliases: list[str], topic: uscb.Topic
           ) -> tuple[dict[int, str], int | None]:
    """A topic's group columns and their labels, and its total, as uscb.read() takes them."""
    if topic.denominator:
        if topic.denominator not in names:
            raise SystemExit(f"sea_composed: no column {topic.denominator!r} in {topic.sheet}")
        total = names.index(topic.denominator)
    else:
        total = uscb.denominator(names, aliases, topic.prefix)
    found = uscb.groups(names, aliases, total, uscb.sexed(names, topic.prefix), topic.prefix)
    if topic.label_prefix:
        found = {i: (label[len(topic.label_prefix):].strip()
                     if label.startswith(topic.label_prefix) else label)
                 for i, label in found.items()}
    if not found or total is None:
        raise SystemExit(f"sea_composed: {topic.sheet} [{topic.prefix}] has "
                         f"{len(found)} group columns and "
                         f"{'a' if total is not None else 'no'} total")
    return found, total


def read_units(sheets: dict[str, list[list[Any]]], topics: tuple[uscb.Topic, ...]
               ) -> list[dict[str, Any]]:
    """Every row of the topics' sheets: its geography, and per field its counts and total.

    Rows of two sheets are the same unit where their geography columns agree.
    """
    units: dict[tuple[Any, ...], dict[str, Any]] = {}
    for topic in topics:
        rows = sheets[topic.sheet]
        names, aliases = uscb.columns(rows)
        found, total = labels(names, aliases, topic)
        at = {n: i for i, n in enumerate(names) if n}
        if "ADM_LEVEL" not in at or "AREA_NAME" not in at:
            raise SystemExit(f"sea_composed: {topic.sheet} is not a geography sheet")
        for row in rows[2:]:
            level = uscb.number(row[at["ADM_LEVEL"]])
            if level is None:
                continue
            level = int(level)

            def cell(col: str, deep: int) -> str:
                return str(row[at[col]] or "").strip() if col in at and level >= deep else ""
            geo = (level, cell("ADM1_NAME", 1), cell("ADM2_NAME", 2), cell("ADM3_NAME", 3),
                   cell("AREA_NAME", 0))
            unit = units.setdefault(geo, {
                "level": level, "adm1": geo[1], "adm2": geo[2], "adm3": geo[3],
                "area": geo[4], "where": " / ".join(x for x in geo[1:4] if x) or geo[4],
                "fields": {}})
            if topic.field in unit["fields"]:
                raise SystemExit(f"sea_composed: two {topic.sheet} rows for {unit['where']}")
            unit["fields"][topic.field] = {
                "counts": {label: v for i, label in found.items()
                           if (v := uscb.number(row[i])) is not None and v > 0},
                "published": uscb.number(row[total])}
    return list(units.values())


def add(parts: list[dict[str, Any]], field: str, where: str) -> dict[str, Any]:
    """Several units' counts and totals for one field, added group by group."""
    counts: dict[str, float] = defaultdict(float)
    published = 0.0
    for p in parts:
        f = p["fields"].get(field)
        if not f or not f["counts"] or not f["published"]:
            raise SystemExit(f"sea_composed: {where}: {p['where']} has no {field} figures, "
                             f"so the sum would be part of the polygon")
        for label, v in f["counts"].items():
            counts[label] += v
        published += f["published"]
    return {"counts": dict(counts), "published": published}


def differs(whole: dict[str, Any], made: dict[str, Any]) -> list[str]:
    """Where a whole's own row and the sum of its parts disagree."""
    out = []
    if abs((whole["published"] or 0) - made["published"]) > SLACK:
        out.append(f"total {whole['published']:,.0f} against {made['published']:,.0f}")
    for label in sorted(set(whole["counts"]) | set(made["counts"])):
        a, b = whole["counts"].get(label, 0.0), made["counts"].get(label, 0.0)
        if abs(a - b) > SLACK:
            out.append(f"{label} {a:,.0f} against {b:,.0f}")
    return out


def check_children(units: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    """Every Myanmar district's and zone's townships make it, group by group."""
    kids: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        if u["level"] == 3:
            kids[(fold(u["adm1"]), fold(u["adm2"]))].append(u)
    checked = 0
    for u in units:
        if u["level"] != 2 or not kids.get((fold(u["adm1"]), fold(u["adm2"]))):
            continue
        for field in fields:
            if field not in u["fields"]:
                continue
            made = add(kids[(fold(u["adm1"]), fold(u["adm2"]))], field, u["where"])
            off = differs(u["fields"][field], made)
            if off:
                raise SystemExit(f"sea_composed: {u['where']}'s townships do not make its "
                                 f"{field}: {'; '.join(off[:6])}")
        checked += 1
    log(f"  every one of {checked} districts' and zones' townships make it, for "
        f"{' and '.join(fields)}")


# uscb.py's Philippine note is about religion and it writes it on both fields;
# the ethnicity question gets its own here.
NOTES = {("PHL", "ethnicity"): ("2020 Census of Population and Housing, the census's question "
                                "on each person's ethnicity, as published.")}


def topic_note(country: uscb.Country, topic: uscb.Topic) -> str:
    return NOTES.get((country.iso3, topic.field)) or topic.note or country.note


def composition(made: dict[str, Any]) -> list[dict[str, Any]]:
    return shares(made["counts"], total=made["published"] or sum(made["counts"].values()))


def cites(country: uscb.Country) -> list[dict[str, Any]]:
    return [{"field": t.field, "name": t.source or country.source,
             "url": uscb.dataset_url(country.dataset), "year": t.year or country.year,
             "license": country.licence} for t in country.topics]


def fields_of(country: uscb.Country, figs: dict[str, dict[str, Any]], said: str
              ) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for t in country.topics:
        out[t.field] = composition(figs[t.field])
        out[f"{t.field}_year"] = t.year or country.year
        out[f"{t.field}_note"] = f"{topic_note(country, t)} {said}"
    return out


# --------------------------------------------------------------------------
# Myanmar
# --------------------------------------------------------------------------

def myanmar(units: list[dict[str, Any]], admin1: list[dict[str, Any]],
            admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    country = uscb.MYANMAR
    fields = tuple(t.field for t in country.topics)
    check_children(units, fields)
    walk = myanmar_age.crosswalk([u for u in units if u["level"] in (2, 3)], admin2)
    union = [u for u in units if u["level"] == 0]
    if len(union) != 1:
        raise SystemExit(f"sea_composed: {len(union)} Union rows in Myanmar's sheet")
    for field in fields:
        made = add([u for cw in walk.values() for u in cw["units"]], field, "the Union")
        off = differs(union[0]["fields"][field], made)
        if off:
            raise SystemExit(f"sea_composed: Myanmar's {len(walk)} polygons do not make the "
                             f"Union's {field}: {'; '.join(off[:6])}")
        log(f"  {field}: the {len(walk)} polygons make the Union's {made['published']:,.0f}")
    names2 = {s["id"]: s["name"] for s in admin2}
    out = []
    for sid, cw in sorted(walk.items(), key=lambda kv: names2[kv[0]]):
        name = names2[sid]
        if cw["kind"] != "composed" and name not in MMR_BY_ALIAS:
            continue
        figs = {f: add(cw["units"], f, name) for f in fields}
        said = (f"The boundary file draws one polygon here where the census counted "
                f"{'; '.join(cw['parts'])}, so this is their sum."
                if cw["kind"] == "composed" else
                f"The census calls this district {cw['units'][0]['adm2']!r}.")
        out.append(record(f"MMR-COMP-{fold(name)}", name, level="admin2", parent="MMR",
                          country="MMR", match_by="shape_id", shape_id=sid,
                          sources=cites(country), **fields_of(country, figs, said)))
        log(f"    {name}: {'; '.join(cw['parts'])} -- "
            + ", ".join(f"{f} {figs[f]['published']:,.0f}" for f in fields))
    states = {fold(u["adm1"]): u for u in units if u["level"] == 1}
    for region in admin1:
        kids = [cw for sid, cw in walk.items()
                if next(s for s in admin2 if s["id"] == sid)["parent"] == region["id"]]
        if not kids:
            continue
        parts = [u for cw in kids for u in cw["units"]]
        held = sorted({u["adm1"] for u in parts})
        figs = {f: add(parts, f, region["name"]) for f in fields}
        if len(held) == 1:
            # The polygon is one census state or region: the sum of its
            # polygons must be that row, which is what uscb.py binds to it.
            for f in fields:
                off = differs(states[fold(held[0])]["fields"][f], figs[f])
                if off:
                    raise SystemExit(f"sea_composed: {region['name']}'s polygons do not make "
                                     f"{held[0]}'s {f}: {'; '.join(off[:6])}")
            continue
        for f in fields:
            whole = add([states[fold(h)] for h in held], f, region["name"])
            off = differs(whole, figs[f])
            if off:
                raise SystemExit(f"sea_composed: {region['name']}'s polygons do not make "
                                 f"{' and '.join(held)}'s {f}: {'; '.join(off[:6])}")
        said = (f"The map draws one polygon here where the census counted "
                f"{' and '.join(h.title() for h in held)}, so this is their sum.")
        out.append(record(f"MMR-COMP-R-{fold(region['name'])}", region["name"],
                          level="admin1", parent="MMR", country="MMR", match_by="shape_id",
                          shape_id=region["id"], sources=cites(country),
                          **fields_of(country, figs, said)))
        log(f"    {region['name']} (first level): {' and '.join(held)}")
    return out


# --------------------------------------------------------------------------
# The Philippines
# --------------------------------------------------------------------------

def philippines(units: list[dict[str, Any]], admin2: list[dict[str, Any]]
                ) -> list[dict[str, Any]]:
    country = uscb.PHILIPPINES
    fields = tuple(t.field for t in country.topics)
    region = [u for u in units if u["level"] == 1 and fold(u["area"]) == fold(NCR)]
    places = [u for u in units if u["level"] == 2 and fold(u["adm1"]) == fold(NCR)]
    if len(region) != 1:
        raise SystemExit(f"sea_composed: {len(region)} rows for the {NCR}")
    for field in fields:
        off = differs(region[0]["fields"][field], add(places, field, NCR))
        if off:
            raise SystemExit(f"sea_composed: the {NCR}'s places do not make it: "
                             f"{'; '.join(off[:6])}")
    wanted = [NCR_FIRST, *(p for parts in NCR_DISTRICTS.values() for p in parts)]
    if sorted(fold(p) for p in wanted) != sorted(fold(u["area"]) for u in places):
        raise SystemExit(f"sea_composed: the {NCR}'s places are "
                         f"{sorted(u['area'] for u in places)}, against the districts' "
                         f"{sorted(wanted)}")
    log(f"  the {NCR}'s {len(places)} places make its row, and each is in one district")
    # Cotabato City has a polygon and no figures; say what the tables hold
    # around it, for the record of why.
    for u in units:
        if u["level"] == 1 and "muslim" in fold(u["area"]):
            kids = [k for k in units if k["level"] == 2 and fold(k["adm1"]) == fold(u["adm1"])]
            for field in fields:
                made = sum(k["fields"][field]["published"] or 0 for k in kids
                           if field in k["fields"])
                log(f"  {u['area']} {field}: {u['fields'][field]['published']:,.0f} against "
                    f"its places' {made:,.0f} ({', '.join(k['area'] for k in kids)})")
    by_name = defaultdict(list)
    for s in admin2:
        by_name[fold(s["name"])].append(s)
    out = []
    for district, names in NCR_DISTRICTS.items():
        shapes = by_name.get(fold(district), [])
        if len(shapes) != 1:
            raise SystemExit(f"sea_composed: {len(shapes)} polygons named {district!r}")
        parts = [next(u for u in places if fold(u["area"]) == fold(n)) for n in names]
        figs = {f: add(parts, f, district) for f in fields}
        listed = ", ".join("Quezon City" if n == "Quezon" else n for n in names)
        said = (f"The boundary file draws Metro Manila as four districts, and this one is "
                f"{listed}, which the census counts apart: this is their sum.")
        out.append(record(f"PHL-COMP-{fold(district)}", district, level="admin2",
                          parent="PHL", country="PHL", match_by="shape_id",
                          shape_id=shapes[0]["id"], sources=cites(country),
                          **fields_of(country, figs, said)))
        log(f"    {district}: {listed} -- "
            + ", ".join(f"{f} {figs[f]['published']:,.0f}" for f in fields))
    return out


def workbook(country: uscb.Country) -> dict[str, list[list[Any]]]:
    import openpyxl
    url = uscb.workbook_url(country.dataset)
    log(f"  {country.name}: {url}")
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    sheets = {t.sheet: uscb.sheet_rows(book, t.sheet) for t in country.topics}
    book.close()
    return sheets


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("sea_composed: religion and ethnicity on the polygons no one census area is")
    records = myanmar(read_units(workbook(uscb.MYANMAR), uscb.MYANMAR.topics),
                      drawn("MMR", "admin1"), drawn("MMR", "admin2"))
    records += philippines(read_units(workbook(uscb.PHILIPPINES), uscb.PHILIPPINES.topics),
                           drawn("PHL", "admin2"))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
