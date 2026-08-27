#!/usr/bin/env python3
"""PxWeb -- one adapter for the many statistical offices that run it.

Most of Europe's national statistical offices publish through PxWeb, and they
all speak the same two-call protocol: GET a table path for its metadata, POST a
query back to the same path for the figures. That makes a new office a few
lines of configuration rather than a new scraper, which is the same bargain the
Eurostat adapter makes and the reason this exists rather than eight files.

What it is *for* is the fields Eurostat does not carry. The Census Hub serves
population, age and sex for every member state on one reference date, but not
ethnicity, religion or language -- those are asked only by the states that ask
them, and published only through their own offices. Central and Eastern Europe
is where that matters: those censuses ask ethnicity and religion together, and
almost nothing else in this dataset does.

Two properties of PxWeb decide the shape of the code below.

A table's variables are named by the office, in its own language and its own
words, so the geography dimension is "Maakond" in Estonia and "region" in
Norway. Rather than hardcode those, each table's config names the variables it
needs and the adapter verifies they exist before asking for anything -- a query
against a variable that is not there returns an error page, not a smaller
answer.

And the query is a POST whose selection must be spelled out. Asking for
everything is what times out or gets refused; asking for one year, every region
and every category of one classification is what works.

Usage:
    python -m scripts.fetch_census.pxweb --country EST
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
)

TIMEOUT = 90


class Table:
    """One PxWeb table, and which of its variables mean what.

    ``geo`` and ``group`` are variable *codes* as the office publishes them.
    ``keep`` pins any remaining variable to a single value -- a year, a sex, a
    citizenship -- because a dimension left unpinned multiplies the response and
    usually means summing across something that should not be summed.
    """

    def __init__(self, path: str, field: str, geo: str, group: str,
                 keep: dict[str, str] | None = None, year: int | None = None,
                 note: str = "", drop: tuple[str, ...] = (),
                 geo_len: int | None = None, geo_stem: int | None = None,
                 geo_prefix: str | None = None, national: str | None = None):
        self.path = path
        self.field = field
        self.geo = geo
        self.group = group
        self.keep = keep or {}
        self.year = year
        self.note = note
        self.drop = drop
        # Length of a geography code at the level being asked for. A PxWeb
        # geography variable holds several levels at once, and the office
        # encodes depth in the code: Latvia's country is "LV", its statistical
        # regions "LV00A", its municipalities "LV0001000".
        self.geo_len = geo_len
        # ...and length alone is not always enough. Latvia's towns are the
        # same width as the municipalities that contain them and differ only in
        # the tail: Jekabpils municipality is "LV0031000" and the town of
        # Jekabpils inside it is "LV0031010". geo_stem is how many leading
        # characters name the family a code belongs to -- six, here -- so that
        # a town can be recognised by the municipality standing beside it
        # rather than by a rule about tails. See drop_nested().
        self.geo_stem = geo_stem
        # Some offices say the level in the code rather than in its width.
        # Finland's regions are "MK01".."MK21" and the aggregates beside them
        # are "SSS" whole country, "MA1" mainland and "MA2" Aland; a length
        # rule would separate them here by luck, because every MK code happens
        # to be one character longer, and would stop being true the day an
        # aggregate got a fourth character. "MK" is the office's own word for
        # the level.
        self.geo_prefix = geo_prefix
        # The geography code that means the whole country. Not guessable from
        # the label: Estonia calls that row "Whole country" and Latvia calls it
        # "Latvia", so looking for the word "total" found Estonia's and missed
        # Latvia's -- in the one table the check was written for.
        self.national = national


# Filled in from what scripts/probe_pxweb.py actually found. An office is only
# listed here once its tables have been seen to exist, be public, and break
# down by a geography the boundary files can join.
#
# Ten instances were walked. Lithuania, Slovakia, Croatia and Serbia answered
# 404 or something that was not JSON at the base URLs tried. North Macedonia's
# tree returned only broadcast-language tables at the depth walked. Slovenia has
# ethnicity by all 193 municipalities but only from the 1991 census, against
# boundaries that have been redrawn twice since, so it is left out rather than
# joined across thirty-five years of redistricting.
#
# The Nordic offices were written off in that pass and should not have been.
# The line said they "ask citizenship, which is a different question", and of
# Finland that it "rate-limits metadata requests and asks language rather than
# ethnicity". Both halves are wrong. Ethnicity is not the only field here --
# language is one of the four, and Finland records mother tongue in the
# population register for every resident, which is a count rather than a
# sample. And the rate-limiting was a fact about the probe's pacing, not about
# the data: StatFin answers 429 under a brisk walk, the probe read that as an
# unreachable node, and an empty result became a conclusion about the country.
# Re-walked with backoff, that instance returns 44 candidate tables.
#
# What is left is the two Baltic offices, and they are the point: neither
# country has had any ethnicity figure in this dataset, and both publish one
# annually at a level the boundary files carry.
INSTANCES: dict[str, dict[str, Any]] = {
    "EST": {
        "name": "Statistics Estonia",
        "base": "https://andmed.stat.ee/api/v1/en/stat",
        # The boundary file names Estonia's counties in Estonian ("Harju
        # maakond"), so the join needs the Estonian labels; the English ones
        # ("Harju county") stay as aliases.
        "local": "et",
        "source": "Statistics Estonia, table RV0222U",
        "url": "https://andmed.stat.ee/en/stat/rahvastik__rahvastikunaitajad-ja"
               "-koosseis__rahvaarv-ja-rahvastiku-koosseis/RV0222U",
        "licence": "CC BY 4.0",
        "level": "admin1",
        "file": "estonia_county",
        "tables": [Table(
            path="rahvastik/rahvastikunaitajad-ja-koosseis/"
                 "rahvaarv-ja-rahvastiku-koosseis/RV0222U.PX",
            field="ethnicity", geo="Maakond", group="Rahvus",
            # Sex must be pinned or males and females are added to a total that
            # already contains both. Year likewise: this is a register count on
            # 1 January, not a census, and every year is in the same table.
            keep={"Aasta": "2026", "Sugu": "1"}, year=2026,
            # "00" is the whole country and "unk" is a county nobody recorded;
            # "784" Tallinn and "793" Tartu city sit *inside* Harju and Tartu
            # counties, so counting them beside their parents would double
            # those two counties' people.
            drop=("unk", "784", "793"), national="00",
            note="Ethnic nationality as recorded in the population register on "
                 "1 January 2026, not a census answer. Estonia asks it of "
                 "residents rather than inferring it from citizenship."),
        ],
    },
    "FIN": {
        "name": "Statistics Finland",
        "base": "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin",
        "source": "Statistics Finland, table 11rl",
        "url": "https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/"
               "statfin_vaerak_pxt_11rl.px",
        "licence": "CC BY 4.0",
        "level": "admin1",
        "file": "finland_region",
        # Finland's regions are named inconsistently in the boundary file --
        # "Central Finland" and "Lapland" in English beside "Kainuu" and
        # "Keski-Pohjanmaa" in Finnish -- so neither language reaches all 19 on
        # its own. Taking the Finnish labels as the name and keeping the
        # English as an alias gives the matcher both forms to try.
        "local": "fi",
        # geoBoundaries names six of Finland's regions with older English
        # exonyms that neither the Finnish label nor Statistics Finland's own
        # English one reaches. These are declared equivalences rather than
        # anything a matcher could infer: "Varsinais-Suomi" and "Finland
        # Proper" share no word, and "North Ostrobothnia" is close enough to
        # bare "Ostrobothnia" -- a different region -- that the loose pass
        # reached it and was stopped only by the rule that settles two rows
        # landing on one shape. A wrong join that a tiebreak happens to catch
        # is still a wrong join waiting for the tiebreak to be absent.
        "aliases": {
            "MK02": ("Finland Proper",),        # Varsinais-Suomi
            "MK05": ("Tavastia Proper",),       # Kanta-Häme
            "MK10": ("Southern Savonia",),      # Etelä-Savo
            "MK11": ("Northern Savonia",),      # Pohjois-Savo
            "MK17": ("Northern Ostrobothnia",), # Pohjois-Pohjanmaa
            "MK21": ("Åland Islands",),         # Ahvenanmaa
        },
        "tables": [Table(
            path="vaerak/11rl.px",
            field="language", geo="alue_23_20260101", group="kieli_15_20180102",
            # Age and sex must be pinned to their totals or every person is
            # counted once per band. contentscode has one value and is pinned
            # for the same reason the others are: nothing may be summed over.
            keep={"ikaryhma_10_20180101": "SSS", "sukupuoli_9_20180101": "SSS",
                  "timeperiod_y": "2025", "contentscode": "vaerak-vaesto"},
            year=2025,
            # "MK" is maakunta. The same variable also carries "SSS" the whole
            # country, "MA1" mainland Finland and "MA2" Aland -- and MA2 is
            # MK21 under another name, so counting both would add Aland twice.
            geo_prefix="MK", national="SSS",
            # The language list is two levels deep and the parents are not
            # marked the way Estonia's are. "01 NATIONAL LANGUAGES, TOTAL"
            # holds Finnish, Swedish and Sami; "02 FOREIGN LANGUAGES, TOTAL"
            # holds the other 163. Keeping either beside its children counts
            # most of the country twice, and neither label is a word is_total()
            # knows.
            drop=("01", "02"),
            note="Mother tongue as recorded in the population register on 31 "
                 "December 2025. Finland registers one language per resident, "
                 "so these are shares of everyone rather than of the people "
                 "who answered a question."),
        ],
    },
    "LVA": {
        "name": "Statistics Latvia",
        "base": "https://data.stat.gov.lv/api/v1/en/OSP_PUB",
        # Likewise Latvian: CGAZ carries "Aizkraukles novads", not "Aizkraukle
        # municipality", and "Ventspils" beside "Ventspils novads".
        "local": "lv",
        "source": "Central Statistical Bureau of Latvia, table IRE031",
        "url": "https://data.stat.gov.lv/pxweb/en/OSP_PUB/START__POP__IR__IRE/IRE031",
        "licence": "CC BY 4.0",
        "level": "admin1",
        "file": "latvia_municipality",
        "tables": [Table(
            path="POP/IR/IRE/IRE031",
            field="ethnicity", geo="AREA", group="ETHNICITY",
            # IRE031 is the count and IRE0311 the same figures as percentages;
            # taking both would read every number twice.
            keep={"ContentsCode": "IRE031", "TIME": "2026"}, year=2026,
            # Nine characters is the municipality and state-city level. The
            # same variable also carries the country and two vintages of the
            # statistical regions, defined before and after 1 January 2024,
            # which overlap each other.
            geo_len=9, geo_stem=6, national="LV",
            note="Ethnicity as recorded in the population register at the "
                 "beginning of 2026. 'Other ethnicities' also holds people who "
                 "selected none and people who did not indicate one, so it is "
                 "not a count of anyone in particular."),
        ],
    },
}


def http_json(url: str, payload: dict | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def variables(base: str, table: Table) -> dict[str, dict[str, Any]]:
    """The table's variables by code, so a query can be checked before it is sent."""
    meta = http_json(f"{base}/{table.path}")
    return {v["code"]: v for v in meta.get("variables", [])}


def in_language(base: str, lang: str) -> str:
    """The same PxWeb base URL, served in another language.

    Every instance seen puts the language in the path -- ".../api/v1/en/stat",
    ".../api/v1/en/OSP_PUB" -- and serves the identical table tree under each
    one. Same codes, same figures, different labels.
    """
    return re.sub(r"/v(\d+)/en/", rf"/v\1/{lang}/", base, count=1)


def local_names(base: str, table: Table, lang: str) -> dict[str, str]:
    """{geography code: the office's own name for it}, or {} if unavailable.

    The boundary files carry local-language names -- "Harju maakond",
    "Aizkraukles novads" -- and the English labels a PxWeb instance serves by
    default do not reach them. "Aizkraukle municipality" against "Aizkraukles
    novads" is two disagreements at once: a translated generic word and a
    genitive ending, and no rule about English suffixes bridges either.

    Rather than invent the morphology, ask the office. It publishes the same
    table under a language path, so the local name is a fetch and not a guess.
    A failure here is not fatal: the English name still matches whatever it
    matched before.
    """
    try:
        meta = variables(in_language(base, lang), table)
    except Exception as exc:                # network, 404, or a renamed tree
        log(f"    no {lang} labels ({exc.__class__.__name__}); "
            f"joining on the English ones")
        return {}
    var = meta.get(table.geo)
    if not var:
        return {}
    return dict(zip(var.get("values", []), var.get("valueTexts", [])))


def build_query(table: Table, meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Every region, every category, one value for everything else."""
    missing = [code for code in (table.geo, table.group) if code not in meta]
    if missing:
        raise SystemExit(
            f"{table.path}: no variable {missing} — the office renamed or "
            f"withdrew it. Present: {sorted(meta)}")

    query = []
    for code in (table.geo, table.group):
        query.append({"code": code,
                      "selection": {"filter": "all", "values": ["*"]}})
    for code, value in table.keep.items():
        if code not in meta:
            raise SystemExit(f"{table.path}: cannot pin absent variable {code!r}")
        query.append({"code": code,
                      "selection": {"filter": "item", "values": [value]}})
    # Anything still unpinned would multiply the table and force a sum across a
    # dimension nobody chose. Refuse rather than guess which way to collapse it.
    loose = [c for c in meta
             if c not in {table.geo, table.group} | set(table.keep)
             and len(meta[c].get("values", [])) > 1]
    if loose:
        raise SystemExit(
            f"{table.path}: {loose} left unpinned; each would be summed over. "
            "Add them to keep= with the value the figures should be read at.")
    return {"query": query, "response": {"format": "json-stat2"}}


# ---------------------------------------------------------------------------
# Reading a table back
# ---------------------------------------------------------------------------

# A value whose label starts with this is a sub-category of the one above it.
# Statistics Estonia writes "Other ethnic nationalities" and then "..Ukrainians",
# "..Belorussians" beneath it; keeping both counts those people twice, which is
# the same trap the ABS classification sets with its "... Total" rows.
CHILD_MARKER = ".."

# The label a PxWeb table gives the row that is everyone. It is the denominator
# rather than a category, and it is also the only population figure these tables
# carry, so it is taken out of the shares and kept as the unit's population.
TOTAL_LABELS = ("total", "whole country", "all")


def unstack(payload: dict[str, Any]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    """json-stat2 -> one entry per cell, each carrying its dimensions' codes and labels.

    The values arrive as a single flat array in row-major order over the
    dimensions named in ``id``, so the position in that array *is* the
    combination of categories -- there is no other record of which cell is
    which.
    """
    ids: list[str] = payload["id"]
    sizes: list[int] = payload["size"]
    dims = payload["dimension"]

    order: list[list[str]] = []
    labels: list[dict[str, str]] = []
    for name in ids:
        category = dims[name]["category"]
        index = category["index"]
        # PxWeb sends the index either as code -> position or as a bare list.
        order.append(sorted(index, key=index.get) if isinstance(index, dict)
                     else list(index))
        labels.append(category.get("label") or {})

    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    values = payload["value"]
    if isinstance(values, dict):        # sparse form: position -> value
        values = [values.get(str(i)) for i in range(strides[0] * sizes[0])]

    out = []
    for flat, value in enumerate(values):
        if value is None:
            continue
        key = {}
        for i, name in enumerate(ids):
            code = order[i][(flat // strides[i]) % sizes[i]]
            key[name] = (code, labels[i].get(code, code))
        out.append((key, float(value)))
    return out


# An office that redraws a unit distinguishes the vintages in the label rather
# than only in the code: Latvia writes "Madona municipality (from 01.07.2025.)"
# for the municipality that absorbed Varaklani. That parenthetical is metadata
# about the row, not part of the place's name, and carrying it into the record
# means the join looks for a shape called "Madona municipality (from
# 01.07.2025.)" and finds nothing.
#
# What marks it is the date, not the word in front of it. Matching on "from"
# and "until" worked on the English labels and missed the Latvian ones, where
# the same qualifier reads "(no 01.07.2025.)" -- and the local labels are the
# ones the join now runs on. A parenthesis with no date in it is part of a
# name and stays.
VINTAGE = re.compile(
    r"\s*\([^()]{0,20}?\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\.?\s*\)\s*$")


def place_name(label: str, code: str = "") -> str:
    """The place's name, with the office's bookkeeping taken off.

    Statistics Finland repeats the code inside the label -- "MK13 Central
    Finland", "MK19 Lapland" -- which is how a table reads to someone browsing
    it and is not how any boundary file names a place. Only the row's own code
    is stripped, so a name that merely starts with letters and digits keeps
    them.
    """
    if code and label.startswith(f"{code} "):
        label = label[len(code) + 1:]
    return VINTAGE.sub("", label).strip()


def is_total(label: str) -> bool:
    return label.strip().lower() in TOTAL_LABELS


def wanted_area(code: str, label: str, table: Table) -> bool:
    """Whether a geography value is one of the units being asked for.

    A PxWeb geography variable usually holds several levels at once, and often
    two vintages of one level: Latvia's lists the country, five statistical
    regions as defined before 2024, five as defined after, and then the
    municipalities. Summing or joining across that would double-count half the
    country, so the level is pinned by code length -- the office's own encoding
    of depth -- and everything else is refused.
    """
    if code in table.drop or is_total(label) or label.startswith(CHILD_MARKER):
        return False
    if table.geo_prefix is not None and not code.startswith(table.geo_prefix):
        return False
    return table.geo_len is None or len(code) == table.geo_len


def reject_reason(code: str, label: str, table: Table) -> str:
    if code == table.national:
        return "the country itself"
    if code in table.drop:
        return "named in drop="
    if is_total(label):
        return "a total, not a unit"
    if label.startswith(CHILD_MARKER):
        return f"labelled {CHILD_MARKER!r}, so inside another unit"
    if table.geo_prefix is not None and not code.startswith(table.geo_prefix):
        return f"code does not start {table.geo_prefix!r}"
    return f"code is not {table.geo_len} characters"


def drop_nested(codes: list[str], table: Table) -> dict[str, str]:
    """Which of these codes sit inside another one that is also present.

    Latvia numbers a municipality "LV0031000" and the town inside it
    "LV0031010" -- same width, same first six characters, and the parent's tail
    sorts first. Refusing every code that does not end "000" reads that
    correctly for the towns and then throws away Madona, which after the July
    2025 merge with Varaklani is "LV0038001" and is nobody's child.

    So the tail is not judged on its own. Codes are grouped by their stem and a
    group of one is kept whatever its tail; only where two codes share a stem
    does the earlier tail win, and the other is reported as contained. That
    asks the office's own numbering which units overlap instead of guessing a
    convention, and it cannot silently drop a unit that stands alone.
    """
    if table.geo_stem is None:
        return {}
    family: dict[str, list[str]] = {}
    for code in codes:
        family.setdefault(code[:table.geo_stem], []).append(code)
    nested = {}
    for stem, members in family.items():
        if len(members) < 2:
            continue
        parent = min(members)
        for code in members:
            if code != parent:
                nested[code] = parent
    return nested


def fetch(base: str, table: Table) -> tuple[dict[str, dict[str, Any]], float | None]:
    """One table -> {area code: {"name", "counts", "total"}}, and the country total.

    The country row is dropped from the units and kept as the control. It is
    the office's own statement of how many people the table describes, and the
    units have to add up to it.
    """
    meta = variables(base, table)
    payload = http_json(f"{base}/{table.path}", build_query(table, meta))
    areas: dict[str, dict[str, Any]] = {}
    national: float | None = None
    # Which geography values were left out, and on which rule. A level pinned
    # by the shape of a code is a guess about an office's numbering, and a
    # silent one takes a real unit out with the duplicates: Latvia's first run
    # dropped three towns that sit inside their municipalities and one
    # municipality that does not.
    refused: dict[str, list[str]] = {}
    for key, value in unstack(payload):
        area_code, area_label = key[table.geo]
        group_code, group_label = key[table.group]
        if area_code == table.national and is_total(group_label):
            national = value
        if not wanted_area(area_code, area_label, table):
            refused.setdefault(reject_reason(area_code, area_label, table),
                               []).append(f"{area_code} {area_label}")
            continue
        entry = areas.setdefault(area_code, {"name": area_label, "counts": {},
                                             "total": None})
        if is_total(group_label):
            entry["total"] = value
        elif group_label.startswith(CHILD_MARKER):
            continue                    # counted already inside its parent
        elif group_code not in table.drop:
            entry["counts"][group_label] = entry["counts"].get(group_label, 0.0) + value
    # Containment can only be seen once every code is in hand: a town looks
    # exactly like a municipality until the municipality turns up beside it.
    for code, parent in drop_nested(list(areas), table).items():
        inside = areas.pop(code)
        refused.setdefault(f"inside {areas[parent]['name']}", []).append(
            f"{code} {inside['name']}")
    for reason, names in sorted(refused.items()):
        unique = sorted(set(names))
        log(f"    left out ({reason}): {len(unique)} — " + ", ".join(unique[:6])
            + (" ..." if len(unique) > 6 else ""))
    return areas, national


def check(iso3: str, table: Table, areas: dict[str, dict[str, Any]],
          national: float | None = None) -> None:
    """Every unit's categories must add up to the total the table itself gives.

    This is the one control a single table can offer, and it is worth having:
    it is exactly what catches a level of the classification being kept twice
    or dropped once, which is the way these joins go wrong silently.
    """
    bad = []
    for code, entry in areas.items():
        total, counted = entry["total"], sum(entry["counts"].values())
        if not total:
            continue
        if abs(counted - total) > max(0.005 * total, 5):
            bad.append(f"{entry['name']} ({code}): categories {counted:,.0f} "
                       f"against a published {total:,.0f}")
    if bad:
        raise SystemExit(f"{iso3} {table.path}: the categories do not partition the "
                         f"population in {len(bad)} units — " + "; ".join(bad[:3]))
    log(f"    {len(areas)} units, categories sum to the published total in each")

    # ...and the units have to add up to the country, which is the check that
    # catches a unit counted inside another one. Every Latvian municipality's
    # own categories added up perfectly while three towns were being counted
    # twice, once on their own and once inside the municipality holding them:
    # 45 units summing to 1,911,026 against a country of 1,845,096.
    if national is None:
        log("    (no country row in this table: the units cannot be checked "
            "against a whole)")
        return
    summed = sum(e["total"] for e in areas.values() if e["total"])
    if abs(summed - national) > max(0.005 * national, 50):
        raise SystemExit(
            f"{iso3} {table.path}: {len(areas)} units sum to {summed:,.0f} against "
            f"a published national {national:,.0f}, a difference of "
            f"{summed - national:+,.0f}. One of them is inside another, or one "
            f"is missing.")
    log(f"    ...and to {summed:,.0f} against a published national {national:,.0f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    iso3 = args.country.strip().upper()
    spec = INSTANCES.get(iso3)
    if not spec:
        raise SystemExit(f"no PxWeb instance configured for {iso3}. "
                         f"Configured: {sorted(INSTANCES)}")

    log(f"pxweb: {spec['name']} ({iso3})")
    merged: dict[str, dict[str, Any]] = {}
    for table in spec["tables"]:
        log(f"  {table.path}")
        areas, national = fetch(spec["base"], table)
        check(iso3, table, areas, national)
        local = local_names(spec["base"], table, spec["local"]) if spec.get("local") else {}
        for code, entry in areas.items():
            # The local name leads because it is what the boundary file
            # carries; the English one follows as an alias so a search for
            # "Aizkraukle municipality" still finds the place.
            slot = merged.setdefault(code, {
                "name": local.get(code) or entry["name"],
                "aliases": [entry["name"]] if local.get(code) else [],
                "fields": {}, "population": None, "notes": {}})
            slot["population"] = slot["population"] or entry["total"]
            slot["fields"][table.field] = shares(entry["counts"], total=entry["total"])
            slot["notes"][table.field] = table.note
            slot["year"] = table.year

    source = {"field": "/".join(sorted({t.field for t in spec["tables"]})),
              "name": spec["source"], "url": spec["url"],
              "license": spec["licence"]}
    records = []
    for code, slot in sorted(merged.items()):
        fields: dict[str, Any] = {}
        for field, rows in slot["fields"].items():
            fields[field] = rows or gap(NOT_AVAILABLE)
            if slot["notes"].get(field):
                fields[f"{field}_note"] = slot["notes"][field]
            fields[f"{field}_year"] = slot.get("year")
        records.append(record(
            f"{iso3}-{code}", place_name(slot["name"], code),
            level=spec["level"], parent=iso3, codes={"pxweb": code},
            aliases=sorted(({place_name(a, code) for a in slot["aliases"]}
                            | set(spec.get("aliases", {}).get(code, ())))
                           - {place_name(slot["name"], code)}) or None,
            population=(measure(int(round(slot["population"])), year=slot.get("year"),
                                source=spec["source"])
                        if slot["population"] else gap(NOT_AVAILABLE)),
            sources=[source], **fields))

    out = args.out or PROCESSED / f"{spec['file']}.json"
    write_json(out, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
