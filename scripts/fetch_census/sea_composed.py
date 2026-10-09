#!/usr/bin/env python3
"""Religion and ethnicity on the polygons no one census area is: Myanmar's
composed districts, Metro Manila's numbered districts and the Philippine
provinces drawn with a highly urbanized city inside them; and the population
of Myanmar's composed districts and of its states and regions.

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

**Myanmar's population.** The map's district figures are OCHA's COD-PS for
2023 (``cod-ps-mmr-archived``), joined by name, so each composed polygon
showed its namesake's figure alone -- Mindat 72,331 where Mindat and Matupi
together are 239,961. Here the same table's rows are summed onto the polygon
they lie in (``MMR_CODPS_INTO``, the parts ``myanmar_age.COMPOSED`` uses),
every row going to exactly one polygon. The states and regions take the same
table's first-level figures, which their districts add up to, rather than an
encyclopaedia's 2024 figures that fell below the districts drawn inside them
(Kayah 296,903 against Loikaw's 298,758): Mandalay with Nay Pyi Taw, Shan's
and Bago's parts summed.

**The Philippines** -- the 2020 Census of Population and Housing. The
boundary file draws Metro Manila as four numbered districts and the census
counts its seventeen cities and municipality. ``uscb.py`` puts the City of
Manila on the First District and declares the other sixteen shapeless, so the
Second, Third and Fourth districts carry nothing. Here each takes the sum of
the places that make it, as the Philippine Statistics Authority defines the
districts (``NCR_DISTRICTS``). Cotabato City, which the boundary file also
draws on its own, has no row at all -- its people are inside Maguindanao's --
and its record says so (``cotabato_city``). The seventeen highly urbanized
cities outside Metro Manila are drawn inside the provinces around them, and
the census tabulates them apart: ``uscb.py`` put each province's row alone
on its polygon, a quarter of Davao del Sur's people and half of Benguet's.
Here each of those fifteen polygons takes its province with its cities
(``HUC_PROVINCES``), measured against the polygon's own 2020 barangay count.

**Household language** in the Philippines comes from CLEAR Global's
tabulation of the 2010 census (``clear_global.py``), whose second-level rows
the build joins only by a name unique in the country. Four of them miss
polygons the boundary file does draw -- Metro Manila's four districts, which
it labels "NCR, ... District" -- and are bound here by the PSGC code each row
carries (``CLEAR_PHL``). A fifth, Isabela's (a name the City of Isabela also
answers to), is not bound: measured against the province's own 2020 census
ethnicity it is not Isabela's people (``CLEAR_REFUSED``), and the polygon says
so. The City of Isabela and Cotabato City, which the table has no row for,
say so too.

A polygon some of whose parts carry no figures for a question -- the Wa
division's Mongmao, Pangwaun, Narphan and Pangsang carry none for either --
gets a gap naming them, never the sum of the rest.

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
from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, read_json, record, shares,
                      write_json)
from .sea_common import drawn, fold

OUT = "sea_composed.json"
# A whole's total against its parts' sum: the workbooks print whole people,
# so anything past rounding is a different count.
SLACK = 0.5
# The groups of a whole against its parts', all together, as a share of the
# total (see differs()).
GROUP_SLACK = 0.001

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


def has(unit: dict[str, Any], field: str) -> bool:
    f = unit["fields"].get(field)
    return bool(f and f["counts"] and f["published"])


def add(parts: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """Several units' counts and totals for one field, added group by group.

    ``missing`` lists the parts with no figures for the field: where there are
    any, the sum describes only part of the whole and is not published.
    """
    counts: dict[str, float] = defaultdict(float)
    published = 0.0
    missing = []
    for p in parts:
        if not has(p, field):
            missing.append(p)
            continue
        f = p["fields"][field]
        for label, v in f["counts"].items():
            counts[label] += v
        published += f["published"]
    return {"counts": dict(counts), "published": published, "missing": missing}


def unit_name(unit: dict[str, Any]) -> str:
    return (unit["adm3"] or unit["adm2"] or unit["adm1"] or unit["area"]).title()


def differs(whole: dict[str, Any], made: dict[str, Any]) -> list[str]:
    """Where a whole's own row and the sum of its parts disagree, if they do.

    The totals must agree to the person. The groups may disagree by a few
    people in all -- the Philippine region's row prints 19 Buhid Mangyan
    where its seventeen places print 49 -- but not by more than
    ``GROUP_SLACK`` of the total between them: a place missing or counted
    twice moves far more than that. Small disagreements are logged.
    """
    out = []
    total = whole["published"] or 0
    if abs(total - made["published"]) > SLACK:
        out.append(f"total {total:,.0f} against {made['published']:,.0f}")
    small = []
    off = 0.0
    for label in sorted(set(whole["counts"]) | set(made["counts"])):
        a, b = whole["counts"].get(label, 0.0), made["counts"].get(label, 0.0)
        if abs(a - b) > SLACK:
            off += abs(a - b)
            small.append(f"{label} {a:,.0f} against {b:,.0f}")
    if off > max(SLACK, GROUP_SLACK * total):
        out += small
    elif small:
        log(f"    groups a whole and its parts print differently, {off:,.0f} people in all: "
            + "; ".join(small[:6]))
    return out


def check_children(units: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    """Every Myanmar district's and zone's townships make it, group by group.

    Where some of a district's townships carry no figures for a field, the
    district is named and not checked for it: nothing is summed from them.
    """
    kids: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        if u["level"] == 3:
            kids[(fold(u["adm1"]), fold(u["adm2"]))].append(u)
    checked = defaultdict(int)
    for u in units:
        towns = kids.get((fold(u["adm1"]), fold(u["adm2"])))
        if u["level"] != 2 or not towns:
            continue
        for field in fields:
            made = add(towns, field)
            if made["missing"]:
                log(f"    {u['where']}: {len(made['missing'])} of {len(towns)} townships carry "
                    f"no {field} figures ({', '.join(unit_name(t) for t in made['missing'])})")
                continue
            if not has(u, field):
                raise SystemExit(f"sea_composed: {u['where']} carries no {field} figures and "
                                 f"its townships do")
            off = differs(u["fields"][field], made)
            if off:
                raise SystemExit(f"sea_composed: {u['where']}'s townships do not make its "
                                 f"{field}: {'; '.join(off[:6])}")
            checked[field] += 1
    log("  districts and zones whose townships make them: "
        + ", ".join(f"{n} for {f}" for f, n in checked.items()))


def topic_note(country: uscb.Country, topic: uscb.Topic) -> str:
    """The note ``uscb.py`` writes for the same topic: each topic's own, where it has one."""
    return topic.note or country.note


def composition(made: dict[str, Any], relabel: dict[str, str] | None = None
                ) -> list[dict[str, Any]]:
    """The shares of a sum, under the labels ``uscb.py`` publishes: its country's
    ``relabel`` (Myanmar's "Burmese" is the Bamar) applied as it applies it."""
    counts: dict[str, float] = defaultdict(float)
    for label, n in made["counts"].items():
        counts[(relabel or {}).get(label, label)] += n
    return shares(dict(counts), total=made["published"] or sum(counts.values()))


def fields_of(country: uscb.Country, parts: list[dict[str, Any]], said: str
              ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """A record's fields from the sum of its parts, its citations, and the sums.

    A field some part has no figures for is a gap that names those parts.
    """
    out: dict[str, Any] = {}
    cites: list[dict[str, Any]] = []
    sums: dict[str, dict[str, Any]] = {}
    for t in country.topics:
        made = sums[t.field] = add(parts, t.field)
        source = t.source or country.source
        if made["missing"]:
            out[t.field] = gap(NOT_AVAILABLE, (
                f"{source} carries no {t.field} figures for "
                f"{', '.join(unit_name(p) for p in made['missing'])}, which "
                f"{'lies' if len(made['missing']) == 1 else 'lie'} in this polygon, so a sum "
                f"here would describe only part of it."))
            continue
        out[t.field] = composition(made, country.relabel)
        out[f"{t.field}_year"] = t.year or country.year
        out[f"{t.field}_note"] = f"{topic_note(country, t)} {said}"
        cites.append({"field": t.field, "name": source,
                      "url": uscb.dataset_url(country.dataset), "year": t.year or country.year,
                      "license": country.licence})
    return out, cites, sums


def described(sums: dict[str, dict[str, Any]]) -> str:
    return ", ".join(f"{f} " + (f"{s['published']:,.0f}" if not s["missing"] else
                                f"none ({len(s['missing'])} parts without figures)")
                     for f, s in sums.items())


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
    every = [u for cw in walk.values() for u in cw["units"]]
    for field in fields:
        # The Union's row is checked against every unit that carries figures;
        # those that carry none are named, and no sum is taken through them.
        made = add(every, field)
        off = differs(union[0]["fields"][field], made)
        if off:
            raise SystemExit(f"sea_composed: Myanmar's {len(walk)} polygons do not make the "
                             f"Union's {field}: {'; '.join(off[:6])}")
        log(f"  {field}: the {len(walk)} polygons make the Union's {made['published']:,.0f}"
            + (f"; units with no figures: {', '.join(unit_name(u) for u in made['missing'])}"
               if made["missing"] else ""))
    names2 = {s["id"]: s["name"] for s in admin2}
    parent_of = {s["id"]: s["parent"] for s in admin2}
    out = []
    for sid, cw in sorted(walk.items(), key=lambda kv: names2[kv[0]]):
        name = names2[sid]
        if cw["kind"] != "composed" and name not in MMR_BY_ALIAS:
            continue
        said = (f"The boundary file draws one polygon here where the census counted "
                f"{'; '.join(cw['parts'])}, so this is their sum."
                if cw["kind"] == "composed" else
                f"The census calls this district {cw['units'][0]['adm2']!r}.")
        values, cites, sums = fields_of(country, cw["units"], said)
        out.append(record(f"MMR-COMP-{fold(name)}", name, level="admin2", parent="MMR",
                          country="MMR", match_by="shape_id", shape_id=sid,
                          sources=cites, **values))
        log(f"    {name}: {'; '.join(cw['parts'])} -- {described(sums)}")
    states = {fold(u["adm1"]): u for u in units if u["level"] == 1}
    for region in admin1:
        parts = [u for sid, cw in walk.items() if parent_of[sid] == region["id"]
                 for u in cw["units"]]
        if not parts:
            continue
        held = sorted({u["adm1"] for u in parts})
        for f in fields:
            made = add(parts, f)
            if made["missing"]:
                continue
            # The polygon is one census state or region, whose row uscb.py
            # binds to it, or several, whose rows are summed here: either
            # way the polygons inside it must make the row or rows.
            whole = add([states[fold(h)] for h in held], f)
            off = differs(whole, made) if not whole["missing"] else ["no row of its own"]
            if off:
                raise SystemExit(f"sea_composed: {region['name']}'s polygons do not make "
                                 f"{' and '.join(held)}'s {f}: {'; '.join(off[:6])}")
        if len(held) == 1:
            continue
        said = (f"The map draws one polygon here where the census counted "
                f"{' and '.join(h.title() for h in held)}, so this is their sum.")
        values, cites, sums = fields_of(country, parts, said)
        out.append(record(f"MMR-COMP-R-{fold(region['name'])}", region["name"],
                          level="admin1", parent="MMR", country="MMR", match_by="shape_id",
                          shape_id=region["id"], sources=cites, **values))
        log(f"    {region['name']} (first level): {' and '.join(held)} -- {described(sums)}")
    return out


# --------------------------------------------------------------------------
# Myanmar: the population of the composed polygons and of the states
# --------------------------------------------------------------------------

MMR_CODPS = "cod-ps-mmr-archived"
# The rows of OCHA's COD-PS for Myanmar that are not the polygon of their own
# name, and the polygon each lies in: the same parts ``myanmar_age.COMPOSED``
# builds those polygons from, as COD-PS counts them. Matupi and Kawlin are
# districts the boundary file draws inside its Mindat and Katha, and each of
# these self-administered zones lies whole in one polygon (COMPOSED lists every
# one of its townships under it). COD-PS already splits the Wa division as the
# boundary file does, into Hopang and Matman, and counts no Mong Hpayak
# district: its Tachileik row is the polygon of that name.
MMR_CODPS_INTO = {
    "MMR004D004": "Mindat",      # Matupi district
    "MMR005D011": "Katha",       # Kawlin district
    "MMR005S001": "Hkamti",      # Naga Self-Administered Zone
    "MMR014S001": "Taunggyi",    # Danu Self-Administered Zone
    "MMR014S002": "Taunggyi",    # Pa-O Self-Administered Zone
    "MMR015S001": "Kyaukme",     # Pa Laung Self-Administered Zone
    "MMR015S002": "Laukkaing",   # Kokang Self-Administered Zone
}
# A composed polygon's figure against the 2014 census's count of the same
# ground (myanmar_age.json): COD-PS's 2023 country total is 1.12 times the
# census's, and the composed polygons come to 1.05-1.17 times theirs. One
# district's row alone on these polygons came to 0.34-0.97 of the census.
MMR_GROWTH = (0.95, 1.30)
# Rounding: COD-PS prints its figures with decimals, and a first-level row may
# differ from the sum of its districts by half a person for each.
MMR_ROUNDING = 0.5


def codps_units(table: dict[str, Any], level: str) -> dict[str, dict[str, Any]]:
    """A COD-PS table's rows by P-code: the name, the first-level P-code and the total."""
    from . import cod_ps
    from .cod_ps_age import number
    columns = table["columns"]
    name_col = cod_ps.name_column(columns, level)
    total_col = cod_ps.total_column(columns)
    code_col = next((c for c in columns if cod_ps.squash(c) == f"adm{level}pcode"), None)
    parent_col = next((c for c in columns if cod_ps.squash(c) == "adm1pcode"), None)
    if not (name_col and total_col and code_col and parent_col):
        raise SystemExit(f"sea_composed: {table['label']} has no name, total or P-code column "
                         f"for level {level}: {columns[:12]}")
    out: dict[str, dict[str, Any]] = {}
    for row in table["rows"]:
        code = str(row.get(code_col) or "").strip()
        people = number(row.get(total_col))
        if not code or not people or people <= 0:
            raise SystemExit(f"sea_composed: {table['label']}: a row without a P-code or a "
                             f"total: {row.get(name_col)!r}")
        if code in out:
            raise SystemExit(f"sea_composed: {table['label']}: two rows for {code}")
        out[code] = {"code": code, "name": str(row.get(name_col) or "").strip(),
                     "parent": str(row.get(parent_col) or "").strip(), "people": people}
    return out


def codps_part(row: dict[str, Any], polygon: str) -> None:
    """Refuse a row ``MMR_CODPS_INTO`` sends to a polygon COMPOSED does not build from it."""
    spec = myanmar_age.COMPOSED.get(polygon)
    if spec is None:
        raise SystemExit(f"sea_composed: COD-PS's {row['name']} ({row['code']}) is sent to "
                         f"{polygon}, which is one census district")
    zone = myanmar_age.zone_of(row["name"])
    if zone is None:
        if fold(row["name"]) not in {fold(d) for d in spec["districts"]}:
            raise SystemExit(f"sea_composed: COD-PS's {row['name']} ({row['code']}) is not one "
                             f"of {polygon}'s census districts {spec['districts']}")
        return
    if zone not in (spec.get("zones") or {}):
        raise SystemExit(f"sea_composed: COD-PS's {row['name']} ({row['code']}) is not in "
                         f"{polygon}")
    shared = [p for p, other in myanmar_age.COMPOSED.items()
              if p != polygon and zone in (other.get("zones") or {})]
    if shared:
        raise SystemExit(f"sea_composed: the {zone.title()} zone's townships are drawn in "
                         f"{polygon} and {shared}, so its COD-PS row cannot go whole to one")


def part_words(row: dict[str, Any]) -> str:
    name = row["name"]
    words = (f"the {name}" if myanmar_age.zone_of(name) else f"{name} district")
    return f"{words} ({row['people']:,.0f})"


def myanmar_population(rows2: dict[str, dict[str, Any]], rows1: dict[str, dict[str, Any]],
                       admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
                       census: dict[str, float], year: int, cite: dict[str, Any]
                       ) -> dict[str, dict[str, Any]]:
    """Polygon id -> its population fields, for every polygon that is not one COD-PS
    row of its own name -- the composed districts -- and for every state and region.

    Every COD-PS district and zone goes to exactly one polygon, every polygon
    gets one at least, a composed polygon's sum stands within ``MMR_GROWTH`` of
    the 2014 census's count of the same ground, and a state's polygons make the
    COD-PS first-level rows they hold, each of those whole in one polygon.
    """
    source = cite["name"]
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in admin2:
        by_name[fold(s["name"])].append(s)
    names2 = {s["id"]: s["name"] for s in admin2}
    into: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for code, row in sorted(rows2.items()):
        label = MMR_CODPS_INTO.get(code)
        if label is not None:
            codps_part(row, label)
        shapes = by_name.get(fold(label or row["name"]), [])
        if len(shapes) != 1:
            raise SystemExit(f"sea_composed: COD-PS's {row['name']} ({code}) finds "
                             f"{len(shapes)} polygons named {label or row['name']!r}")
        into[shapes[0]["id"]].append(row)
    empty = sorted(s["name"] for s in admin2 if s["id"] not in into)
    if empty:
        raise SystemExit(f"sea_composed: polygons no COD-PS row reaches: {empty}")
    out: dict[str, dict[str, Any]] = {}
    for sid, rows in sorted(into.items(), key=lambda kv: names2[kv[0]]):
        if len(rows) == 1 and fold(rows[0]["name"]) == fold(names2[sid]):
            continue
        people = sum(r["people"] for r in rows)
        then = census.get(sid)
        growth = people / then if then else None
        if growth is None or not MMR_GROWTH[0] <= growth <= MMR_GROWTH[1]:
            raise SystemExit(f"sea_composed: {names2[sid]}'s COD-PS parts make {people:,.0f}, "
                             f"against the 2014 census's {then or 0:,.0f} for the same ground "
                             f"(outside {MMR_GROWTH})")
        parts = sorted(rows, key=lambda r: r["code"])
        if len(parts) == 1:
            note = (f"OCHA's COD-PS for Myanmar (reference year {year}) has no row named "
                    f"{names2[sid]}: the boundary file's {names2[sid]} district is "
                    f"{part_words(parts[0])}, and this is that figure.")
        else:
            note = (f"OCHA's COD-PS for Myanmar (reference year {year}) counts "
                    f"{', '.join(part_words(r) for r in parts[:-1])} and "
                    f"{part_words(parts[-1])} apart, and the boundary file draws them as one "
                    f"polygon: this is their sum.")
        out[sid] = {"level": "admin2", "name": names2[sid],
                    "population": {"value": int(round(people)), "year": year,
                                   "source": source},
                    "population_note": note, "sources": [cite]}
        log(f"    {names2[sid]}: {' + '.join(r['name'] for r in parts)} = {people:,.0f} "
            f"({growth:.2f} times the 2014 census's {then:,.0f})")
    # The states and regions: each polygon holds whole COD-PS first-level units.
    parent_of = {s["id"]: s["parent"] for s in admin2}
    held: dict[str, set[str]] = defaultdict(set)
    for sid, rows in into.items():
        held[parent_of[sid]] |= {r["parent"] for r in rows}
    owner: dict[str, str] = {}
    for aid, codes in held.items():
        for c in codes:
            if c in owner:
                raise SystemExit(f"sea_composed: COD-PS's first-level {c} has districts in two "
                                 f"states or regions of the map")
            owner[c] = aid
    if set(owner) != set(rows1):
        raise SystemExit(f"sea_composed: COD-PS's first-level rows {sorted(rows1)} against "
                         f"those its districts name {sorted(owner)}")
    for c, row in sorted(rows1.items()):
        kids = [r for r in rows2.values() if r["parent"] == c]
        made = sum(r["people"] for r in kids)
        if abs(made - row["people"]) > MMR_ROUNDING * (len(kids) + 1):
            raise SystemExit(f"sea_composed: COD-PS's {row['name']} ({c}) is {row['people']:,.0f} "
                             f"and its districts make {made:,.0f}")
    for region in admin1:
        codes = sorted(held.get(region["id"], ()))
        if not codes:
            continue
        people = sum(rows1[c]["people"] for c in codes)
        drawn_sum = sum(r["people"] for sid, rows in into.items()
                        if parent_of[sid] == region["id"] for r in rows)
        if abs(people - drawn_sum) > MMR_ROUNDING * (len(rows2) + 1):
            raise SystemExit(f"sea_composed: {region['name']}: {people:,.0f} against its "
                             f"districts' {drawn_sum:,.0f}")
        names = [rows1[c]["name"] for c in codes]
        if len(names) == 1:
            note = (f"OCHA's COD-PS for Myanmar (reference year {year}), the same table the "
                    f"districts drawn inside it take their figures from; they add up to it.")
        else:
            note = (f"OCHA's COD-PS for Myanmar (reference year {year}) counts "
                    f"{', '.join(names[:-1])} and {names[-1]} apart, and the map draws them "
                    f"as this one polygon: this is their sum, which the districts drawn "
                    f"inside it add up to.")
        out[region["id"]] = {"level": "admin1", "name": region["name"],
                             "population": {"value": int(round(people)), "year": year,
                                            "source": source},
                             "population_note": note, "sources": [cite]}
        log(f"    {region['name']} (first level): {' + '.join(names)} = {people:,.0f}")
    total = sum(r["people"] for r in rows1.values())
    log(f"  population: {sum(1 for v in out.values() if v['level'] == 'admin2')} composed "
        f"districts and {sum(1 for v in out.values() if v['level'] == 'admin1')} states and "
        f"regions from {len(rows2)} COD-PS districts and zones, {total:,.0f} in all")
    return out


def with_population(records: list[dict[str, Any]], pops: dict[str, dict[str, Any]]
                    ) -> list[dict[str, Any]]:
    """The population fields onto the polygon's record, or a record of their own."""
    out = []
    left = dict(pops)
    for r in records:
        extra = left.pop(r.get("shape_id"), None)
        if extra:
            r = {**r, "population": extra["population"],
                 "population_note": extra["population_note"],
                 "sources": [*r.get("sources", []), *extra["sources"]]}
        out.append(r)
    for sid, extra in sorted(left.items(), key=lambda kv: kv[1]["name"]):
        tag = "R-" if extra["level"] == "admin1" else ""
        out.append(record(f"MMR-POP-{tag}{fold(extra['name'])}", extra["name"],
                          level=extra["level"], parent="MMR", country="MMR",
                          match_by="shape_id", shape_id=sid,
                          **{k: v for k, v in extra.items() if k not in ("name", "level")}))
    return out


def myanmar_codps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], int,
                            dict[str, Any]]:
    """COD-PS's Myanmar districts and zones, its first-level rows, the year and the citation."""
    from . import cod_ps
    from .sea_cod_ps_age import newest_tables
    package = cod_ps.get("package_show", id=MMR_CODPS)
    if not cod_ps.is_usable(package):
        raise SystemExit(f"sea_composed: {MMR_CODPS}: licence {cod_ps.licence(package)}")
    newest = newest_tables(package)
    if "1" not in newest or "2" not in newest or newest["1"][0] != newest["2"][0]:
        raise SystemExit(f"sea_composed: {MMR_CODPS} has no first- and second-level tables "
                         f"of one year: {[(k, v[0], v[1]['label']) for k, v in newest.items()]}")
    year = newest["2"][0]
    log(f"  {MMR_CODPS}: {newest['1'][1]['label']} and {newest['2'][1]['label']} ({year})")
    cite = {"field": "population",
            "name": f"OCHA, Common Operational Dataset -- population statistics ({MMR_CODPS}), "
                    f"reference year {year}",
            "url": cod_ps.DATASET_PAGE.format(stub=MMR_CODPS), "year": year,
            "license": cod_ps.licence(package)}
    return (codps_units(newest["2"][1], "2"), codps_units(newest["1"][1], "1"), year, cite)


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
        made = add(places, field)
        off = (differs(region[0]["fields"][field], made) if not made["missing"] else
               [f"{', '.join(unit_name(p) for p in made['missing'])} without figures"])
        if off:
            raise SystemExit(f"sea_composed: the {NCR}'s places do not make it: "
                             f"{'; '.join(off[:6])}")
    wanted = [NCR_FIRST, *(p for parts in NCR_DISTRICTS.values() for p in parts)]
    if sorted(fold(p) for p in wanted) != sorted(fold(u["area"]) for u in places):
        raise SystemExit(f"sea_composed: the {NCR}'s places are "
                         f"{sorted(u['area'] for u in places)}, against the districts' "
                         f"{sorted(wanted)}")
    log(f"  the {NCR}'s {len(places)} places make its row, and each is in one district")
    by_name = defaultdict(list)
    for s in admin2:
        by_name[fold(s["name"])].append(s)
    out = [*cotabato_city(units, fields, by_name)]
    for district, names in NCR_DISTRICTS.items():
        shapes = by_name.get(fold(district), [])
        if len(shapes) != 1:
            raise SystemExit(f"sea_composed: {len(shapes)} polygons named {district!r}")
        parts = [next(u for u in places if fold(u["area"]) == fold(n)) for n in names]
        listed = ", ".join("Quezon City" if n == "Quezon" else n for n in names)
        said = (f"The boundary file draws Metro Manila as four districts, and this one is "
                f"{listed}, which the census counts apart: this is their sum.")
        values, cites, sums = fields_of(country, parts, said)
        out.append(record(f"PHL-COMP-{fold(district)}", district, level="admin2",
                          parent="PHL", country="PHL", match_by="shape_id",
                          shape_id=shapes[0]["id"], sources=cites, **values))
        log(f"    {district}: {listed} -- {described(sums)}")
    return out


# The highly urbanized cities outside Metro Manila. The census tabulates each
# apart from the province around it, and ``uscb.py`` declares each shapeless,
# but the boundary file draws each inside that province's polygon, and the
# PSA's own barangay table files its barangays under that province, so the
# polygon's population, median age and sex ratio (philippines_age.py) count
# the city's people. Its religion and ethnicity must too: the province's row
# alone is a quarter of Davao del Sur's polygon. The polygon's label ->
# (region, the province's row, the cities' rows and the names a note gives
# them), rows by their names in the US Census Bureau's tables.
HUC_PROVINCES: dict[str, tuple[str, str, tuple[tuple[str, str], ...]]] = {
    "Agusan del Norte": ("Caraga Region", "Agusan Del Norte", (("Butuan", "Butuan"),)),
    "Benguet": ("Cordillera Administrative Region", "Benguet", (("Baguio", "Baguio"),)),
    "Cebu": ("Central Visayas", "Province Of Cebu",
             (("Cebu City", "Cebu City"), ("Lapu-Lapu", "Lapu-Lapu"),
              ("Mandaue", "Mandaue"))),
    "Davao del Sur": ("Davao Region", "Davao Del Sur", (("Davao", "Davao City"),)),
    "Iloilo": ("Western Visayas", "Province Of Iloilo", (("Iloilo City", "Iloilo City"),)),
    "Lanao del Norte": ("Northern Mindanao", "Lanao Del Norte", (("Iligan", "Iligan"),)),
    "Leyte": ("Eastern Visayas", "Leyte", (("Tacloban", "Tacloban"),)),
    "Misamis Oriental": ("Northern Mindanao", "Misamis Oriental",
                         (("Cagayan De Oro", "Cagayan de Oro"),)),
    "Negros Occidental": ("Western Visayas", "Negros Occidental", (("Bacolod", "Bacolod"),)),
    "Palawan": ("Mimaropa", "Palawan", (("Puerto Princesa", "Puerto Princesa"),)),
    "Pampanga": ("Central Luzon", "Pampanga", (("Angeles", "Angeles"),)),
    "Quezon": ("Calabarzon", "Quezon", (("Lucena", "Lucena"),)),
    "South Cotabato": ("Soccsksargen", "South Cotabato",
                       (("General Santos", "General Santos"),)),
    "Zambales": ("Central Luzon", "Zambales", (("Olongapo", "Olongapo"),)),
    "Zamboanga del Sur": ("Zamboanga Peninsula", "Zamboanga Del Sur",
                          (("Zamboanga", "Zamboanga City"),)),
}
# The two provinces ``uscb.py`` also declares shapeless: their polygons are not
# the provinces (philippines_age.EXCLUDE), and they are not cities.
NOT_CITIES = ("Maguindanao", "Province Of Cotabato")
# The census's household population against the barangay count of the same
# polygon (philippines_age.json): the household population leaves out those in
# institutions, and the 69 provinces with no such city come to 0.987-0.999 of
# their polygons' counts. A province's row without its city comes to 0.28-0.87.
HOUSEHOLD_SHARE = (0.985, 1.0)


def huc_provinces(units: list[dict[str, Any]], admin2: list[dict[str, Any]],
                  counted: dict[str, float]) -> list[dict[str, Any]]:
    """Each province polygon holding a highly urbanized city: the province's
    religion and ethnicity with the city's added.

    Refused unless: every city ``uscb.py`` declares shapeless outside Metro
    Manila is added to one polygon; each city's row and its province's are in
    the same region, and every such region's row is the sum of its provinces'
    and cities' rows; and, for both fields, the province with its city makes
    ``HOUSEHOLD_SHARE`` of the polygon's 2020 barangay count while the
    province alone does not -- the measure that puts the city inside it.
    """
    country = uscb.PHILIPPINES
    fields = tuple(t.field for t in country.topics)
    declared = {(fold(r), fold(c)) for r, c in country.no_shape
                if fold(r) != fold(NCR) and c not in NOT_CITIES}
    named = {(fold(r), fold(c)) for r, _, cities in HUC_PROVINCES.values() for c, _ in cities}
    if declared != named:
        raise SystemExit(f"sea_composed: cities declared shapeless and not added to a province: "
                         f"{sorted(declared - named)}; added and not declared: "
                         f"{sorted(named - declared)}")
    rows2: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        if u["level"] == 2:
            rows2[(fold(u["adm1"]), fold(u["area"]))].append(u)
    regions = {fold(u["area"]): u for u in units if u["level"] == 1}
    for region in sorted({r for r, _, _ in HUC_PROVINCES.values()}):
        whole = regions.get(fold(region))
        kids = [u for (r, _), us in rows2.items() if r == fold(region) for u in us]
        for f in fields:
            off = (differs(whole["fields"][f], add(kids, f)) if whole and has(whole, f)
                   else ["no row of its own"])
            if off:
                raise SystemExit(f"sea_composed: {region}'s provinces and cities do not make "
                                 f"its {f}: {'; '.join(off[:6])}")
    by_label = defaultdict(list)
    for s in admin2:
        by_label[s["name"]].append(s)
    out = []
    for label, (region, province, cities) in sorted(HUC_PROVINCES.items()):
        shapes = by_label.get(label, [])
        parts = []
        for name in (province, *(c for c, _ in cities)):
            rows = rows2.get((fold(region), fold(name)), [])
            if len(rows) != 1:
                raise SystemExit(f"sea_composed: {len(rows)} rows for {name} in {region}")
            parts.append(rows[0])
        if len(shapes) != 1:
            raise SystemExit(f"sea_composed: {len(shapes)} polygons labelled {label!r}")
        people = counted.get(shapes[0]["id"])
        if not people:
            raise SystemExit(f"sea_composed: no 2020 barangay count for {label}'s polygon")
        for f in fields:
            alone, made = add(parts[:1], f), add(parts, f)
            if made["missing"]:
                raise SystemExit(f"sea_composed: {label}: a part carries no {f} figures")
            share, before = made["published"] / people, alone["published"] / people
            if not HOUSEHOLD_SHARE[0] <= share <= HOUSEHOLD_SHARE[1] \
                    or HOUSEHOLD_SHARE[0] <= before:
                raise SystemExit(f"sea_composed: {label}: the province alone makes {before:.3f} "
                                 f"of the polygon's 2020 count ({people:,.0f}) for {f}, and "
                                 f"with its cities {share:.3f}, against {HOUSEHOLD_SHARE}")
        shown = [n for _, n in cities]
        listed = shown[0] if len(shown) == 1 else f"{', '.join(shown[:-1])} and {shown[-1]}"
        whose = "the city's" if len(shown) == 1 else "the cities'"
        said = (f"The boundary file draws {listed} inside this province's polygon, and the "
                f"census counts {'it' if len(shown) == 1 else 'them'} apart from the "
                f"province: these are the province's figures and {whose} added together.")
        values, cites, sums = fields_of(country, parts, said)
        out.append(record(f"PHL-COMP-{fold(label)}", label, level="admin2", parent="PHL",
                          country="PHL", match_by="shape_id", shape_id=shapes[0]["id"],
                          sources=cites, **values))
        log(f"    {label}: {province} + {', '.join(c for c, _ in cities)} -- {described(sums)}; "
            f"{sums[fields[0]]['published'] / people:.3f} of the polygon's 2020 count "
            f"({people:,.0f}), the province alone "
            f"{add(parts[:1], fields[0])['published'] / people:.3f}")
    return out


def barangay_counts(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Polygon id -> the 2020 census count philippines_age.json gives it."""
    return {r["shape_id"]: r["population"]["value"] for r in rows
            if r.get("country") == "PHL" and r.get("level") == "admin2" and r.get("shape_id")
            and isinstance(r.get("population"), dict) and r["population"].get("value")}


COTABATO_CITY = "Cotabato City"


def cotabato_city(units: list[dict[str, Any]], fields: tuple[str, ...],
                  by_name: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Cotabato City is drawn on its own and has no row: say why, measured.

    The Bangsamoro region's row is compared with its provinces' rows; where
    they agree, the city's people are inside a province's figures (the PSA's
    barangay table files it under Maguindanao) and cannot be taken out.
    """
    shapes = by_name.get(fold(COTABATO_CITY), [])
    if len(shapes) != 1 or any(fold(COTABATO_CITY) in fold(u["area"]) for u in units):
        return []
    region = [u for u in units if u["level"] == 1 and "muslim" in fold(u["area"])]
    if len(region) != 1:
        raise SystemExit(f"sea_composed: {len(region)} Bangsamoro rows")
    kids = [k for k in units if k["level"] == 2 and fold(k["adm1"]) == fold(region[0]["adm1"])]
    whole = {f: region[0]["fields"][f]["published"] for f in fields}
    made = {f: sum(k["fields"][f]["published"] or 0 for k in kids if f in k["fields"])
            for f in fields}
    names = ", ".join(k["area"].title() for k in kids)
    log(f"  {COTABATO_CITY}: no row; the Bangsamoro region's "
        + "; ".join(f"{f} {whole[f]:,.0f} against its provinces' {made[f]:,.0f}" for f in fields)
        + f" ({names})")
    if any(abs(whole[f] - made[f]) > SLACK for f in fields):
        raise SystemExit(f"sea_composed: the Bangsamoro region's row is not its provinces': "
                         f"{whole} against {made}")
    why = (f"The US Census Bureau's tables of the 2020 census, which carry the Philippines' "
           f"religion and ethnicity on this map, have no row for {COTABATO_CITY}: the "
           f"Bangsamoro region's row is exactly its provinces' ({names}), and the census's "
           f"own barangay table files the city under Maguindanao, so its people are inside "
           f"Maguindanao's figures and cannot be taken out of them.")
    return [record("PHL-COMP-cotabatocity", COTABATO_CITY, level="admin2", parent="PHL",
                   country="PHL", match_by="shape_id", shape_id=shapes[0]["id"],
                   **{f: gap(NOT_AVAILABLE, why) for f in fields})]


# Household language reaches the Philippines' provinces on this map from CLEAR
# Global's tabulation of the 2010 census (clear_global.py), whose second-level
# rows the build joins only by a name unique in the country. Four of its rows
# are polygons the boundary file draws under other labels: Metro Manila's four
# districts, which it calls "NCR, ... District". Each is bound here by the PSGC
# code the table gives as its location code: row id -> (the table's name, the
# polygon's label).
CLEAR_FILE = "clear_global_language.json"
CLEAR_PHL = {
    "PHL-CG-PH13039": ("Metropolitan Manila First District",
                       "NCR, City of Manila, First District"),
    "PHL-CG-PH13074": ("Metropolitan Manila Second District", "NCR, Second District"),
    "PHL-CG-PH13075": ("Metropolitan Manila Third District", "NCR, Third District"),
    "PHL-CG-PH13076": ("Metropolitan Manila Fourth District", "NCR, Fourth District"),
}
# And the two cities the boundary file draws on their own, which the table
# has no row for.
CLEAR_NONE = ("City of Isabela", COTABATO_CITY)
# A row the table has and which is not bound, with what was measured against
# it. Isabela's row (PSGC 02031) is not Isabela's people: set beside the
# province's own 2020 census ethnicity (uscb's philippines_province), it
# gives 13.0% Cebuano where 1.0% of the province is Cebuano or Bisaya, 4.0%
# Hiligaynon where 0.2% is Ilonggo, and 1.2% Cuyonon, 0.6% Palawan and 0.9%
# Romblomanon -- languages of Palawan and Romblon -- where none of their
# peoples is counted, while its Ibanag (7.8%) is half the province's (16.1%).
# Isabela's towns share their names with towns of Palawan (Roxas, Quezon),
# Romblon (San Agustin), Bohol (Alicia, San Isidro) and Iloilo (Cabatuan),
# which is what a tabulation that pooled towns by name would produce.
CLEAR_REFUSED = {
    "Isabela": ("PHL-CG-PH02031", (
        "CLEAR Global's tabulation of the 2010 census has a row for Isabela (PSGC 02031), "
        "and it is not used: beside the province's own 2020 census ethnicity it gives 13.0% "
        "Cebuano where 1.0% of the province is Cebuano or Bisaya, 4.0% Hiligaynon where "
        "0.2% is Ilonggo, and 2.7% in languages of Palawan and Romblon (Cuyonon, Palawan, "
        "Romblomanon) whose peoples the province does not count, while its Ibanag share "
        "(7.8%) is half the census's (16.1%). The row reads as Isabela pooled with "
        "same-named towns elsewhere (Roxas and Quezon in Palawan, San Agustin in Romblon), "
        "not as Isabela's households.")),
}


def clear_language(admin2: list[dict[str, Any]], rows: list[dict[str, Any]]
                   ) -> dict[str, dict[str, Any]]:
    """Polygon id -> its language fields, for the polygons CLEAR's rows miss."""
    by_label = defaultdict(list)
    for s in admin2:
        by_label[s["name"]].append(s)
    table = {r["id"]: r for r in rows if r.get("country") == "PHL" and r["level"] == "admin2"}
    out: dict[str, dict[str, Any]] = {}
    for rid, (name, label) in CLEAR_PHL.items():
        row, shapes = table.get(rid), by_label.get(label, [])
        if row is None or row["name"] != name or len(shapes) != 1 \
                or not isinstance(row.get("language"), list) or not row["language"]:
            raise SystemExit(f"sea_composed: {CLEAR_FILE} has no {rid} named {name!r} with a "
                             f"language, or {len(shapes)} polygons are labelled {label!r}")
        code = rid.rsplit("-", 1)[-1]
        out[shapes[0]["id"]] = {
            "name": label, "language": row["language"],
            "language_year": row.get("language_year"),
            "language_note": (f"{row.get('language_note', '')} The table calls this unit "
                              f"\"{name}\", location code {code}, which is its PSGC code; it is "
                              f"bound to the polygon by that code."),
            "sources": [s for s in row.get("sources") or [] if s.get("field") == "language"]}
        log(f"    {label}: CLEAR Global's {name} ({code}), "
            + ", ".join(f"{g['group']} {g['pct']}" for g in row["language"][:3]))
    for label, (rid, why) in CLEAR_REFUSED.items():
        shapes = by_label.get(label, [])
        if len(shapes) != 1 or rid not in table:
            raise SystemExit(f"sea_composed: {len(shapes)} polygons labelled {label!r}, or "
                             f"{CLEAR_FILE} no longer has {rid}")
        out[shapes[0]["id"]] = {"name": label, "language": gap(NOT_AVAILABLE, why)}
        log(f"    {label}: CLEAR Global's {rid} not used -- " + why[:120] + "...")
    names = {fold(r["name"]) for r in table.values()}
    for label in CLEAR_NONE:
        shapes = by_label.get(label, [])
        if len(shapes) != 1 or fold(label) in names:
            raise SystemExit(f"sea_composed: {len(shapes)} polygons labelled {label!r}, or "
                             f"{CLEAR_FILE} has a row for it after all")
        out[shapes[0]["id"]] = {"name": label, "language": gap(NOT_AVAILABLE, (
            f"CLEAR Global's tabulation of the 2010 census, which carries household language "
            f"for the Philippines' provinces on this map, has no row for {label}, which the "
            f"boundary file draws apart from the province around it."))}
    return out


def with_language(records: list[dict[str, Any]], clear: dict[str, dict[str, Any]]
                  ) -> list[dict[str, Any]]:
    """The language fields onto the polygon's record, or a record of their own."""
    out = []
    left = dict(clear)
    for r in records:
        extra = left.pop(r.get("shape_id"), None)
        if extra:
            r = {**r, **{k: v for k, v in extra.items() if k not in ("name", "sources")},
                 "sources": [*r.get("sources", []), *extra.get("sources", [])]}
        out.append(r)
    for sid, extra in left.items():
        out.append(record(f"PHL-LANG-{fold(extra['name'])}", extra["name"], level="admin2",
                          parent="PHL", country="PHL", match_by="shape_id", shape_id=sid,
                          **{k: v for k, v in extra.items() if k != "name"}))
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
    mmr1, mmr2 = drawn("MMR", "admin1"), drawn("MMR", "admin2")
    records = myanmar(read_units(workbook(uscb.MYANMAR), uscb.MYANMAR.topics), mmr1, mmr2)
    log(f"  Myanmar's population from {MMR_CODPS}, on the polygons that are not one of its "
        f"rows and on the states and regions:")
    census = {r["shape_id"]: r["population"]["value"]
              for r in read_json(PROCESSED / myanmar_age.OUT, [])
              if r.get("level") == "admin2" and isinstance(r.get("population"), dict)}
    rows2, rows1, year, cite = myanmar_codps()
    records = with_population(records, myanmar_population(rows2, rows1, mmr1, mmr2, census,
                                                          year, cite))
    admin2 = drawn("PHL", "admin2")
    units = read_units(workbook(uscb.PHILIPPINES), uscb.PHILIPPINES.topics)
    records += philippines(units, admin2)
    log("  the provinces whose polygons hold a highly urbanized city:")
    counted = barangay_counts(read_json(PROCESSED / "philippines_age.json", []))
    records += huc_provinces(units, admin2, counted)
    log(f"  household language for the polygons {CLEAR_FILE}'s rows miss:")
    records = with_language(records, clear_language(admin2, read_json(PROCESSED / CLEAR_FILE,
                                                                       [])))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
