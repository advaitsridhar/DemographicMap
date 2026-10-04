#!/usr/bin/env python3
"""Finland: membership of a religious community, from the population register, for the units the map draws.

**The source.** Finland's population register records every resident's
religious community, and Statistics Finland publishes it in three parts by
municipality, sub-region and region among its key figures on the population
(StatFin 11ra, 1990-2025): the share belonging to the Evangelical Lutheran
Church, the share belonging to other religious groups, and the share with no
religious affiliation, each to one decimal, beside the population of 31
December. It is a count of everyone -- registered membership, not belief --
and the same register's national count by community (StatFin 11rx, which has
no area) is its control. The FIN religion policy says Statistics Finland
publishes religion for the whole country only; 11ra is the table that shows
otherwise.

**The units.** The map draws Finland's seventy sub-regions as they were in
2020 (finland.py binds them), and nineteen regions that are 2020's too --
Kuhmoinen in Central Finland, Joroinen and Heinävesi in Southern Savonia,
Isokyrö in Ostrobothnia, all moved on 1 January 2021 -- but for two
municipalities: Iitti is drawn in Päijät-Häme, where it moved in 2021, and
Vaala in Kainuu, which it left in 2016 (DRAWN_REGION says how that was
measured). 11ra lays every year out in the division of 1 January 2026. Today's
municipalities are placed in the drawn units by their codes (Honkajoki and
Pertunmaa, merged since 2020, lay in the same units as the municipalities they
joined); then

* a unit whose code is today's and whose people are exactly 11ra's for that
  code is the same territory, and takes 11ra's own shares for it;
* any other is summed from its municipalities, each one's shares weighed by its
  population. The counts are the shares times the population, so a summed share
  is good to 0.05 points.

Every unit also carries its population on the same day, by the same rule:
11ra's own count where today's unit of its code is the same territory, else
the sum of its municipalities -- the count for the territory the map draws,
which no figure for today's units gives. Where the map shows a figure for
today's unit of the same code on a different territory (nine regions, the
Lahti sub-region), or finland.py's 2020 count, this corrects it.

**Labels.** 11ra gives three groups below the country, and the units keep
exactly those three: "Evangelical Lutheran Church of Finland"; "Member of
another religious community" (the Orthodox Church, the Catholic Church, the
free churches, the registered Islamic communities and every other community
the register knows -- 11rx has them apart for the whole country only); and
"Not a member of any religious community", the register's own words for what
Statistics Finland calls no religious affiliation, filed with no religion.
Each note says it is membership, not belief: a believer outside every
registered community is in the third group.

**The country.** 11rx's count by community is read in full, its two levels
checked against each other and the whole, and printed as the country's
itemised figure (NATIONAL_GROUPS) for data/curated/admin0_detail.json, which
the build applies after summing the regions: the regions' three groups would
fold the Orthodox churches, Catholics and Muslims into one "other" for the
country, where the register itself names them. The run says whether the
curated row agrees with the register.

**Checks.** Every area's three shares make 100 to within their rounding; the
municipalities make the country's population exactly; 11rx's national count of
Lutherans, of the unaffiliated and of everyone else agrees with 11ra's national
shares to within their rounding, and its communities make its whole on both of
its levels; every unit taken from 11ra's own row agrees with the sum of its
municipalities to 0.1 points; every 2020 sub-region lies in one 2020 region;
every drawn polygon is bound one to one.

Usage:
    python -m scripts.fetch_census.finland_religion
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from typing import Any, Callable

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .nordic_common import bind_rows, load_units, request_json, unplaced
from .pxweb import unstack

TABLE = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/vaerak/11ra.px"
PAGE = ("https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/"
        "statfin_vaerak_pxt_11ra.px")
NATIONAL = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/vaerak/11rx.px"
SOURCE = "Statistics Finland, table 11ra (key figures on population)"
OUT = PROCESSED / "finland_religion.json"

POPULATION = "vaerak-vaesto"
LUTHERAN = "Evangelical Lutheran Church of Finland"
OTHER = "Member of another religious community"
NONE = "Not a member of any religious community"
SHARES = {"vaesto_usk_evlut_p": LUTHERAN, "vaesto_usk_muu_p": OTHER,
          "vaesto_usk_ei_p": NONE}
CONTENTS = [POPULATION, *SHARES]
# 11rx's codes for the whole country, everyone ("SSS"), the Lutheran church
# ("F09") and those in no religious community ("H00"); the rest are the
# other communities.
NATIONAL_ALL, NATIONAL_LUTHERAN, NATIONAL_NONE = "SSS", "F09", "H00"
# 11rx's two levels (uskontokunta_10_20190101): eight groups that make the
# whole, two of which -- Christianity (F00) and the other religious groups
# (G00) -- are made of the communities listed under them.
NATIONAL_TOP = ("A00", "B00", "C00", "D00", "E00", "F00", "G00", "H00")
NATIONAL_PARTS = {
    "F00": ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F10", "F11"),
    "G00": ("G01", "G02", "G03", "G04", "G05", "G06"),
}
# The country's figure, itemised from 11rx: each label and the 11rx codes it
# joins, every community of the lower level in exactly one. The labels are the
# office's own where the group tree places them; "Other Christian" joins the
# smaller Christian bodies 11rx names (Adventism, the Anglican churches,
# Baptism, the Lutheran free congregations, Methodism, the free churches and
# other Christian), and "Other religions" the rest of the other religious
# groups (the Bahá'í, the Christian Community, the Liberal Catholic Church and
# others) with the indigenous religions and neo-paganism.
NATIONAL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (LUTHERAN, ("F09",)),
    (NONE, ("H00",)),
    ("Orthodox churches", ("F08",)),
    ("Islam", ("D00",)),
    ("Other Christian", ("F01", "F02", "F03", "F04", "F07", "F10", "F11")),
    ("Roman Catholic Church", ("F06",)),
    ("Jehovah's Witnesses", ("G02",)),
    ("Pentecostalism", ("F05",)),
    ("Church of Jesus Christ of Latter-day Saints", ("G03",)),
    ("Buddhism", ("B00",)),
    ("Hinduism", ("C00",)),
    ("Judaism", ("E00",)),
    ("Other religions", ("A00", "G01", "G04", "G05", "G06")),
)
NATIONAL_PAGE = ("https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/"
                 "statfin_vaerak_pxt_11rx.px")
CURATED = PROCESSED.parent / "curated" / "admin0_detail.json"
BASIS = "registered membership"
# Three shares, each rounded to one decimal, make 100 to within 0.15.
ROUNDING = 0.15
# A sum of municipal shares against the office's own share for the same
# territory: each is good to 0.05.
AGREEMENT = 0.1 + 1e-9
PAUSE = 1.5                     # StatFin answers 429 to a brisker pace
# Municipalities of the map's year (2020) gone by 11ra's division, and the one
# each joined, whose figure now holds its people in every year. Each pair lay
# in the same 2020 sub-region and region, which place() checks.
#   Honkajoki (099) joined Kankaanpää (214) on 1 January 2021.
#   Pertunmaa (588) joined Mäntyharju (507) by 2026: 11ra's 2024 figure for
#   Mäntyharju, in today's division, is 7,057 -- 11rf's 5,532 for Mäntyharju
#   and 1,525 for Pertunmaa in 2024's own (church_probe round c8).
MERGED_SINCE = {"099": "214", "588": "507"}
# The map's regions are not quite 2020's. Rebuilt from the site's tiles, every
# drawn sub-region lies (98% or more of it) inside one drawn region but two:
# 19.0% of the Kouvola sub-region is inside the drawn Päijät-Häme, which is
# Iitti's share of it -- Iitti moved there from Kymenlaakso in 2021 -- and
# 15.3% of Oulunkaari is inside the drawn Kainuu, Vaala's share -- Vaala left
# Kainuu for Northern Ostrobothnia in 2016. So the regions are summed from the
# 2020 key with those two municipalities in the regions the map draws them in:
# {code: (its name, the drawn region's maakunta code)}.
DRAWN_REGION = {"142": ("Iitti", "07"), "785": ("Vaala", "18")}

Rows = dict[str, dict[str, float]]


def division_year(variable: str) -> int:
    """11ra's area variable is named for its division: alue_23_20260101 -> 2026."""
    found = re.search(r"_(\d{4})0101$", variable)
    if not found:
        raise SystemExit(f"11ra: cannot tell the division of the area variable {variable!r}")
    return int(found.group(1))


def read_rows(body: dict[str, Any], area: str) -> Rows:
    """json-stat2 -> {area code: {content code: value}}."""
    rows: Rows = defaultdict(dict)
    for key, value in unstack(body):
        rows[key[area][0]][key["contentscode"][0]] = value
    return dict(rows)


def check_rows(rows: Rows) -> float:
    """Every area answers all four contents, has people, and its three shares
    make 100 to within their rounding; returns the worst difference."""
    worst = 0.0
    for code, row in rows.items():
        missing = [c for c in CONTENTS if row.get(c) is None]
        if missing:
            raise SystemExit(f"11ra {code}: no value for {missing}")
        if row[POPULATION] <= 0:
            raise SystemExit(f"11ra {code}: a population of {row[POPULATION]}")
        off = abs(sum(row[c] for c in SHARES) - 100)
        if off > ROUNDING + 1e-9:
            raise SystemExit(f"11ra {code}: the three shares make {100 + off:.1f}")
        worst = max(worst, off)
    return worst


def counts_of(row: dict[str, float]) -> dict[str, float]:
    """One area's people in each group: its shares of its population."""
    return {label: row[POPULATION] * row[code] / 100.0 for code, label in SHARES.items()}


def check_national(rows: Rows, national: dict[str, float]) -> dict[str, float]:
    """11ra's national shares against 11rx's count by community, everyone.

    The populations must be the same number, and each share 11rx implies must
    round to 11ra's within its rounding. Returns 11rx's three counts."""
    whole = rows.get("SSS")
    if whole is None:
        raise SystemExit("11ra: no row for the whole country")
    everyone = national.get(NATIONAL_ALL)
    if everyone is None or abs(everyone - whole[POPULATION]) > 0.5:
        raise SystemExit(f"11rx counts {everyone} people, 11ra {whole[POPULATION]:,.0f}")
    lutheran, none = national.get(NATIONAL_LUTHERAN), national.get(NATIONAL_NONE)
    if lutheran is None or none is None:
        raise SystemExit("11rx: no count of the Lutheran church or of the unaffiliated")
    counted = {LUTHERAN: lutheran, OTHER: everyone - lutheran - none, NONE: none}
    for code, label in SHARES.items():
        share = 100.0 * counted[label] / everyone
        if abs(share - whole[code]) > 0.05 + 1e-9:
            raise SystemExit(f"11rx gives {label} {share:.2f}% of the country, 11ra "
                             f"{whole[code]}%")
    return counted


def national_groups(national: dict[str, float]) -> list[dict[str, Any]]:
    """11rx's count by community -> the country's itemised figure, as
    NATIONAL_GROUPS joins it.

    The eight groups of the upper level must make everyone, and Christianity
    and the other religious groups their communities, to the person; every
    community of the lower level must be in exactly one label, and 11rx must
    have no code the reader does not know. Anything else stops the run."""
    leaves = [c for c in NATIONAL_TOP if c not in NATIONAL_PARTS] + [
        c for parts in NATIONAL_PARTS.values() for c in parts]
    known = {NATIONAL_ALL, *NATIONAL_TOP, *leaves}
    strange = sorted(set(national) - known)
    missing = sorted(known - set(national))
    if strange or missing:
        raise SystemExit(f"11rx: communities the reader does not know {strange}; "
                         f"communities it lacks {missing}")
    for whole, parts in ((NATIONAL_ALL, NATIONAL_TOP), *NATIONAL_PARTS.items()):
        made = sum(national[c] for c in parts)
        if abs(made - national[whole]) > 0.5:
            raise SystemExit(f"11rx: {whole} is {national[whole]:,.0f}, its parts make "
                             f"{made:,.0f}")
    used = [c for _, codes in NATIONAL_GROUPS for c in codes]
    if sorted(used) != sorted(leaves):
        raise SystemExit(f"NATIONAL_GROUPS: joins {sorted(used)}, 11rx's communities are "
                         f"{sorted(leaves)}")
    counts = {label: sum(national[c] for c in codes) for label, codes in NATIONAL_GROUPS}
    return shares(counts, total=national[NATIONAL_ALL])


def curated_agreement(groups: list[dict[str, Any]], year: int) -> str:
    """Whether data/curated/admin0_detail.json's Finnish religion row is this
    figure: said, never stopped on, since the curated file is the build's."""
    try:
        rows = json.loads(CURATED.read_text(encoding="utf-8")).get("rows", [])
    except (OSError, ValueError) as exc:
        return f"the curated file cannot be read ({exc})"
    row = next((r for r in rows if r.get("country") == "FIN"
                and r.get("field") == "religion"), None)
    if row is None:
        return "the curated file has no row for Finland's religion yet"
    theirs = {g.get("group"): g.get("count") for g in row.get("groups") or []}
    ours = {g["group"]: g["count"] for g in groups}
    if theirs == ours and row.get("year") == year:
        return f"the curated row agrees with the register's {year} count"
    return (f"the curated row ({row.get('year')}) differs from the register's {year} count: "
            + "; ".join(f"{k} {theirs.get(k)} against {ours.get(k)}"
                        for k in sorted(set(theirs) | set(ours), key=str)
                        if theirs.get(k) != ours.get(k)))


def curated_row(groups: list[dict[str, Any]], year: int, people: float) -> dict[str, Any]:
    """The country's row for data/curated/admin0_detail.json, which the build
    applies after summing the regions, from 11rx's itemised count."""
    return {
        "country": "FIN", "field": "religion", "year": year, "basis": BASIS,
        "groups": groups,
        "source": f"Statistics Finland, table 11rx (population by religious community, age "
                  f"and sex), 31 December {year}",
        "url": NATIONAL_PAGE, "license": "CC BY 4.0 (Statistics Finland)",
        "note": (f"Membership of a religious community as Finland's population register "
                 f"records it for every resident on 31 December {year}: {people:,.0f} people "
                 "(Statistics Finland, table 11rx). A count of registered membership, not of "
                 "belief. 'Not a member of any religious community' is everyone in no "
                 "registered community, which Statistics Finland calls no religious "
                 "affiliation; it also holds people of faith who belong to none. 'Other "
                 "Christian' joins the smaller Christian bodies the table names (Adventists, "
                 "the Anglican churches, Baptists, the Lutheran free congregations, "
                 "Methodists, the free churches and other Christians); 'Other religions' the "
                 "Bahá'í, the Christian Community, the Liberal Catholic Church, the indigenous "
                 "religions and neo-paganism and the rest of the other religious groups. "
                 "Statistics Finland counts the communities apart for the whole country only: "
                 "the regions and sub-regions carry the same register's three groups (the "
                 "Lutheran church, every other community together, and none) for the same "
                 "day, so this figure is the itemised whole of theirs."),
    }


def place(current: list[str], key: dict[str, str], merged: dict[str, str],
          what: str) -> dict[str, str]:
    """Today's municipality codes -> the units of the key's year, by code.

    A code the key does not know stops the run. So does a municipality of the
    key's year that is gone today, unless ``merged`` names the one it joined
    and that one lies in the same unit -- then its people are in its
    successor's figure, which is counted in the right unit already."""
    unknown = sorted(c for c in current if c not in key)
    if unknown:
        raise SystemExit(f"{what}: today's municipalities {unknown} are not in the key")
    for code in sorted(set(key) - set(current)):
        into = merged.get(code)
        if into is None or key.get(into) != key[code]:
            raise SystemExit(f"{what}: municipality {code} of the key's year is gone today and "
                             "is not known to have joined one in the same unit")
    return {c: key[c] for c in current}


def sum_units(rows: Rows, placed: dict[str, str]
              ) -> tuple[dict[str, float], dict[str, dict[str, float]], dict[str, int]]:
    """The people, the people in each group and the number of municipalities
    of each unit, summed from the municipalities ``placed`` in it."""
    people: dict[str, float] = defaultdict(float)
    groups: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    parts: dict[str, int] = defaultdict(int)
    for muni, unit in placed.items():
        row = rows[f"KU{muni}"]
        people[unit] += row[POPULATION]
        for label, n in counts_of(row).items():
            groups[unit][label] += n
        parts[unit] += 1
    return dict(people), {u: dict(g) for u, g in groups.items()}, dict(parts)


def own_row(rows: Rows, prefix: str, unit: str, people: float) -> dict[str, float] | None:
    """11ra's own row for a unit of the map's year, when it is the same
    territory today: the same code, and exactly the same people."""
    row = rows.get(f"{prefix}{unit}")
    if row is not None and abs(row[POPULATION] - people) <= 0.5:
        return row
    return None


def check_agreement(row: dict[str, float], groups: dict[str, float], people: float,
                    what: str) -> float:
    """The office's shares for a unit against the sum of its municipalities'."""
    worst = 0.0
    for code, label in SHARES.items():
        off = abs(100.0 * groups[label] / people - row[code])
        if off > AGREEMENT:
            raise SystemExit(f"{what}: its municipalities make {label} "
                             f"{100.0 * groups[label] / people:.2f}%, 11ra's own figure is "
                             f"{row[code]}%")
        worst = max(worst, off)
    return worst


def composition(rows: Rows, prefix: str, unit: str, people: float,
                groups: dict[str, float], parts: int, year: int, drawn: str,
                kind: str) -> tuple[dict[str, Any], bool]:
    """A unit's religion fields, and whether they are 11ra's own figure.
    ``drawn`` says which division the map draws ("the sub-regions of 2020")."""
    row = own_row(rows, prefix, unit, people)
    if row is not None:
        counts = counts_of(row)
        how = (f"Statistics Finland's own figure for the {kind}, which today holds the same "
               f"municipalities as in {drawn}.")
    else:
        counts = groups
        how = (f"Summed from its {parts} municipalities in {drawn}, each one's shares weighed "
               f"by its population; Statistics Finland's own {kind} figures are for today's "
               f"{kind}s, which differ.")
    total = sum(counts.values())
    shown = {label: 100.0 * n / people for label, n in counts.items()}
    note = (f"Membership of a religious community as Finland's population register records "
            f"it for every resident on 31 December {year} (Statistics Finland, key figures on "
            f"population, table 11ra): {LUTHERAN} {shown[LUTHERAN]:.1f}%, other religious "
            f"communities {shown[OTHER]:.1f}%, none {shown[NONE]:.1f}% of {people:,.0f} "
            "people. A count of registered membership, not of belief. Below the country, "
            "Statistics Finland publishes these three groups only, and they are shown as "
            "published: 'Member of another religious community' joins the Orthodox Church of "
            "Finland, the Catholic Church, the free churches, the registered Islamic "
            "communities and every other community the register knows, which it counts apart "
            "for the whole country only (table 11rx). 'Not a member of any religious "
            "community' is the register's row for everyone in no registered community, which "
            "Statistics Finland calls no religious affiliation; being membership, it also "
            "holds people of faith who belong to no registered community. " + how)
    fields = {"religion": shares(counts, total=people), "religion_year": year,
              "religion_basis": BASIS, "religion_note": note}
    if abs(total - people) > ROUNDING / 100.0 * people + 1:
        raise SystemExit(f"{kind} {unit}: its groups make {total:,.0f} of {people:,.0f}")
    return fields, row is not None


def key_pairs(urls: list[str]) -> dict[str, str]:
    """A correspondence table's maps list -> {source code: target code}.

    Since early October 2026 the classification service answers HTTP 500 to a
    maps request with any of its content, meta or language parameters -- the
    route finland.py and nordic_origin read -- and answers the bare request
    with the list of its maps' own addresses, each ending in the two codes it
    joins: ``.../kunta_1_20200101%23seutukunta_1_20200101/maps/305/178`` is
    Kuusamo in Koillismaa. A source in two targets stops the run."""
    out: dict[str, str] = {}
    for url in urls:
        found = re.search(r"/maps/([^/?#]+)/([^/?#]+)$", str(url))
        if not found:
            raise SystemExit(f"classification: a map address without two codes: {url!r}")
        source, target = found.groups()
        if out.get(source, target) != target:
            raise SystemExit(f"classification: {source} maps to {out[source]} and {target}")
        out[source] = target
    return out


def item_names(items: list[dict[str, Any]]) -> dict[str, str]:
    """A classification's items -> {code: name}."""
    return {item["code"]: (item.get("classificationItemNames") or [{}])[0].get("name", "")
            for item in items}


CLASS_API = "https://data.stat.fi/api/classifications/v2"


def load_keys(year: int) -> tuple[dict[str, str], dict[str, str], dict[str, str],
                                  dict[str, str], dict[str, str], dict[str, str]]:
    """The map's year's keys: {municipality: sub-region}, {sub-region: name},
    {drawn name: sub-region}, {municipality: region}, {region: name},
    {municipality: name}.

    Every municipality of the year must be in both keys, every sub-region and
    region named, and the sub-regions must be the seventy finland.py binds."""
    from . import finland as fi

    def maps(target: str) -> dict[str, str]:
        return key_pairs(request_json(
            f"{CLASS_API}/correspondenceTables/kunta_1_{year}0101%23{target}_1_{year}0101/maps",
            pause=PAUSE))

    def names(classification: str) -> dict[str, str]:
        return item_names(request_json(
            f"{CLASS_API}/classifications/{classification}_1_{year}0101/classificationItems"
            "?content=data&meta=max&lang=fi", pause=PAUSE))

    munis = names("kunta")
    sk_of, sk_names = maps("seutukunta"), names("seutukunta")
    mk_of, mk_names = maps("maakunta"), names("maakunta")
    for what, key, named in (("sub-region", sk_of, sk_names), ("region", mk_of, mk_names)):
        if set(key) != set(munis):
            raise SystemExit(f"classification {year}: the {what} key has "
                             f"{sorted(set(munis) ^ set(key))[:10]} unlike the municipalities")
        unnamed = sorted(set(key.values()) - set(named))
        if unnamed:
            raise SystemExit(f"classification {year}: {what}s with no name {unnamed}")
    sk_names = {c: n for c, n in sk_names.items() if c in set(sk_of.values())}
    mk_names = {c: n for c, n in mk_names.items() if c in set(mk_of.values())}
    found, missing = fi.match(sk_names)
    if missing or len(sk_names) != len(fi.DRAWN):
        raise SystemExit(f"classification {year}: {len(sk_names)} sub-regions; the drawn names "
                         f"it lacks: {missing}")
    log(f"  the {year} keys: {len(munis)} municipalities in {len(sk_names)} sub-regions and "
        f"{len(mk_names)} regions")
    return sk_of, sk_names, found, mk_of, mk_names, munis


def drawn_regions(mk_of: dict[str, str], munis: dict[str, str]) -> dict[str, str]:
    """The 2020 key's municipality -> region, with DRAWN_REGION's municipalities
    in the regions the map draws them in. Each must be the municipality named,
    and lie in another region in the key, or the run stops."""
    out = dict(mk_of)
    for code, (name, region) in DRAWN_REGION.items():
        if munis.get(code) != name or mk_of.get(code) in (None, region):
            raise SystemExit(f"finland: municipality {code} is {munis.get(code)!r} in region "
                             f"{mk_of.get(code)}, not {name} outside region {region}")
        out[code] = region
    return out


def finland(keys: Callable[[int], tuple] = load_keys, key_year: int = 2020
            ) -> list[dict[str, Any]]:
    from . import finland as fi
    from .nordic_origin import FIN_REGIONS
    meta = {v["code"]: v for v in request_json(TABLE, pause=PAUSE)["variables"]}
    area = next(c for c in meta if c.startswith("alue"))
    missing = [c for c in CONTENTS if c not in meta["contentscode"]["values"]]
    if missing:
        raise SystemExit(f"11ra: no contents {missing}")
    division = division_year(area)
    # The newest year, or the one before if the newest has its population and
    # not yet its religious communities (an incomplete year stops the run).
    for year in sorted(meta["timeperiod_y"]["values"])[-1:-3:-1]:
        rows = read_rows(request_json(TABLE, {"query": [
            {"code": area, "selection": {"filter": "all", "values": ["*"]}},
            {"code": "contentscode", "selection": {"filter": "item", "values": CONTENTS}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": [year]}},
        ], "response": {"format": "json-stat2"}}, pause=PAUSE), area)
        if any(rows.get("SSS", {}).get(c) is not None for c in SHARES):
            break
        log(f"  11ra {year}: no religious community yet; the year before")
    worst = check_rows(rows)
    kinds = defaultdict(int)
    for code in rows:
        kinds[re.match(r"[A-Z]*", code).group(0)] += 1
    log(f"  11ra {year} in the division of {division}: {dict(kinds)}; every area's three "
        f"shares make 100 to within {worst:.2f}")
    nmeta = {v["code"]: v for v in request_json(NATIONAL, pause=PAUSE)["variables"]}
    community = next(c for c in nmeta if c.startswith("uskonto"))
    national = {key[community][0]: value for key, value in unstack(request_json(NATIONAL, {
        "query": [
            {"code": community, "selection": {"filter": "all", "values": ["*"]}},
            {"code": "sukupuoli_9_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "ikaryhma_10_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": [year]}},
        ], "response": {"format": "json-stat2"}}, pause=PAUSE))}
    counted = check_national(rows, national)
    log("  11rx agrees: " + "; ".join(f"{k} {v:,.0f}" for k, v in counted.items()))
    detail = curated_row(national_groups(national), int(year), national[NATIONAL_ALL])
    log(f"  11rx's {len(national) - 1} communities make its whole on both levels; the "
        "country's figure for data/curated/admin0_detail.json -- "
        f"{curated_agreement(detail['groups'], int(year))}:")
    log("  " + json.dumps(detail, ensure_ascii=False))

    sk_of, sk_names, found, mk_of, mk_names, munis = keys(key_year)
    for sk in set(sk_of.values()):
        homes = {mk_of.get(k) for k, s in sk_of.items() if s == sk}
        if len(homes) != 1 or None in homes:
            raise SystemExit(f"finland: sub-region {sk_names[sk]} lies in regions {homes}")
    mk_drawn = drawn_regions(mk_of, munis)
    current = sorted(c[2:] for c in rows if c.startswith("KU"))
    place_sk = place(current, sk_of, MERGED_SINCE, f"11ra -> {key_year} sub-regions")
    place_mk = place(current, mk_drawn, MERGED_SINCE, "11ra -> the drawn regions")
    people_sk, groups_sk, parts_sk = sum_units(rows, place_sk)
    people_mk, groups_mk, parts_mk = sum_units(rows, place_mk)
    whole = rows["SSS"][POPULATION]
    for what, people in (("sub-regions", people_sk), ("regions", people_mk)):
        if abs(sum(people.values()) - whole) > 0.5:
            raise SystemExit(f"11ra: the {what} make {sum(people.values()):,.0f} of "
                             f"{whole:,.0f}")
    log(f"  {len(current)} municipalities make the country's {whole:,.0f} in "
        f"{len(people_sk)} sub-regions and {len(people_mk)} regions of {key_year}")
    agreement = 0.0
    for prefix, people, groups in (("SK", people_sk, groups_sk), ("MK", people_mk, groups_mk)):
        for unit, n in people.items():
            row = own_row(rows, prefix, unit, n)
            if row is not None:
                agreement = max(agreement, check_agreement(row, groups[unit], n,
                                                           f"{prefix}{unit}"))
    log(f"  units unchanged since {key_year}: their municipalities' sums agree with 11ra's own "
        f"figures to within {agreement:.2f} points")

    shapes_rows = {found[d]: (d, "") for d in fi.DRAWN}
    bound, missing_rows, left, _pieces = bind_rows("FIN", "admin2", shapes_rows)
    if missing_rows or left:
        raise SystemExit(f"finland: sub-regions unbound {missing_rows}; polygons unbound "
                         f"{[s['name'] for s in left]}")
    admin1 = {u["name"]: u for u in load_units("FIN", "admin1")}
    if set(FIN_REGIONS) != set(mk_names) or set(FIN_REGIONS.values()) != set(admin1):
        raise SystemExit(f"finland: regions {sorted(mk_names)} against the drawn "
                         f"{sorted(admin1)}")
    source = {"field": "religion", "name": SOURCE, "url": PAGE, "year": int(year)}
    records: list[dict[str, Any]] = []
    own = {"admin2": 0, "admin1": 0}

    sk_drawn = f"the sub-regions of {key_year}, which the map draws"
    mk_drawn_text = (f"the regions of {key_year} as the map draws them -- with Iitti in "
                     "Päijät-Häme, as since 2021, and Vaala in Kainuu, as before 2016")

    def population(prefix: str, unit: str, people: float, kind: str,
                   drawn: str) -> dict[str, Any]:
        """The unit's people on the same day as its religion: 11ra's own count
        where today's unit of its code is the same territory, else the sum of
        its municipalities -- the count for the territory the map draws, which
        no figure for today's units gives."""
        row = rows.get(f"{prefix}{unit}")
        if row is not None and abs(row[POPULATION] - people) <= 0.5:
            how = (f"Statistics Finland's own count for the {kind} (table 11ra), which today "
                   f"holds the same municipalities as in {drawn}.")
        else:
            how = (f"Summed from today's municipalities in {drawn} (Statistics Finland, table "
                   "11ra). " + (f"Today's {kind} of the same code is another territory, so its "
                                "own figure is not this unit's." if row is not None else
                                f"Statistics Finland has no {kind} of this code today."))
        return {"population": measure(int(round(people)), year=int(year), source=SOURCE),
                "population_note": f"Registered residents on 31 December {year}. " + how}

    for sk, (drawn, _) in sorted(shapes_rows.items()):
        fields, is_own = composition(rows, "SK", sk, people_sk[sk], groups_sk[sk],
                                     parts_sk[sk], int(year), sk_drawn, "sub-region")
        own["admin2"] += is_own
        extra = population("SK", sk, people_sk[sk], "sub-region", sk_drawn)
        records.append(record(
            f"FIN-REL-SK{key_year}-{sk}", drawn, level="admin2", parent="FIN", country="FIN",
            codes={"seutukunta": sk, "vintage": key_year}, match_by="shape_id",
            shape_id=bound[sk], **fields, **extra,
            sources=[dict(source, field="religion" + ("/population" if extra else ""))]))
    for mk in sorted(FIN_REGIONS):
        fields, is_own = composition(rows, "MK", mk, people_mk[mk], groups_mk[mk],
                                     parts_mk[mk], int(year), mk_drawn_text, "region")
        own["admin1"] += is_own
        extra = population("MK", mk, people_mk[mk], "region", mk_drawn_text)
        records.append(record(
            f"FIN-REL-MK{key_year}-{mk}", FIN_REGIONS[mk], level="admin1", parent="FIN",
            country="FIN", codes={"maakunta": mk, "vintage": key_year}, match_by="shape_id",
            shape_id=admin1[FIN_REGIONS[mk]]["id"], **fields, **extra,
            sources=[dict(source, field="religion" + ("/population" if extra else ""))]))
    summed = sorted(r["name"] for r in records if "Summed" in r["religion_note"])
    log(f"  {own['admin2']} of {len(shapes_rows)} sub-regions and {own['admin1']} of "
        f"{len(FIN_REGIONS)} regions take 11ra's own figure; summed from their municipalities, "
        f"religion and population alike ({len(summed)}): {summed}")
    # The drawn sub-regions under another drawn region than their maakunta's:
    # said, not stopped on -- the regions are summed from municipalities.
    shape_parent = {s["id"]: s["parent"] for s in load_units("FIN", "admin2")}
    elsewhere = sorted(f"{sk_names[sk]} under {admin1[FIN_REGIONS[mk_of[k]]]['name']}"
                       for k, sk in sk_of.items() if sk in bound
                       and shape_parent[bound[sk]] != admin1[FIN_REGIONS[mk_of[k]]]["id"])
    if elsewhere:
        log(f"  drawn sub-regions filed under another region than their {key_year} maakunta: "
            f"{sorted(set(elsewhere))}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("finland_religion: Statistics Finland 11ra by the units of the map's year")
    records = finland()
    labels = {g["group"] for r in records for g in r.get("religion") or []
              if isinstance(r.get("religion"), list)}
    log(f"  {len(records)} records; religion labels the group tree cannot place: "
        f"{unplaced('religion', labels) or 'none'}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
