#!/usr/bin/env python3
"""Mauritius -- the 2022 Housing and Population Census by district and island.

Statistics Mauritius publishes the census's demographic tables as one workbook
(Volume II: Demographic and Fertility Characteristics). Three of its sheets
are read here, each by country, district (and island), and municipal ward or
village council area:

    D2  resident population by age group and sex
    D6  resident population by religious group
    D9  resident population by language usually spoken at home

Written: for the nine districts of the Island of Mauritius and for Rodrigues
-- each drawn by the map once at either level -- the census's count, the sex ratio (men per thousand women), the median age
(interpolated within the age group that holds the middle person), religion and
home language as counts. The five Hindu groups the census lists (Hindu & Other
Hindu, Tamil, Telugu, Marathi and Vedic) are written as one Hindu group, and
the note says so. Agaléga and St. Brandon have no line in these tables (the
Republic's residents in them are the two main islands'), and say so.

**The units.** Each table's blocks are found by their label: a district's
("PORT LOUIS DISTRICT ...") or an island's ("... RODRIGUES"); the first block
of each is the whole unit, before its urban and rural parts or its wards.

**Checks before anything is written.** A block's men and women make its
total and its age groups make it too; its religions and its languages make the
same total; the districts and islands make the Republic's 1,233,097.

Usage:
    python -m scripts.fetch_census.mauritius_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .southern_africa_common import fetch, grouped_median, key, sex_ratio, units

URL = ("https://statsmauritius.govmu.org/Documents/Census_and_Surveys/Census2022/"
       "HPC_TR_Vol2_Demography_Yr22.xlsx")
SOURCE = ("Statistics Mauritius, 2022 Housing and Population Census, Volume II: Demographic and "
          "Fertility Characteristics")
LICENCE = "Statistics Mauritius publication (reuse with attribution)"
YEAR = 2022
NATIONAL = 1_233_097
OUT = "mauritius_census.json"
# The map's units (reduced name) -> how each table labels them, reduced.
UNITS = {"portlouis": ("portlouis",), "pamplemousses": ("pamplemousses",),
         "rivieredurempart": ("rivieredurempart", "rdurempart"), "flacq": ("flacq",),
         "grandport": ("grandport",), "savanne": ("savanne",),
         "plaineswilhems": ("plaineswilhems",), "moka": ("moka",),
         "blackriver": ("blackriver",), "rodrigues": ("rodrigues",)}
# The outer islands, which the volume's tables do not give: the Republic's
# resident population in them is the Island of Mauritius' and Rodrigues'.
OUTER = {"agalega": "Agaléga", "stbrandon": "St. Brandon"}
OUTER_NOTE = ("Statistics Mauritius' 2022 census tables of age, sex, religion and language give "
              "the Island of Mauritius, by district, and Rodrigues; the Republic's 1,233,097 "
              "residents in them are those two islands' alone, and {name} has no line.")

RELIGION = (("buddhist", "Buddhist"), ("assembl", "Assembly of God"),
            ("churchofengland", "Church of England/ Protestant"),
            ("romancatholic", "Roman Catholic"), ("otherchristian", "Other Christian"),
            ("seventh", "Seventh Day Adventist"), ("jehovah", "Jehovah's Witnesses"),
            ("marathi", "Hindu"), ("tamil", "Hindu"), ("telugu", "Hindu"), ("vedic", "Hindu"),
            ("hindu", "Hindu"), ("islam", "Islam"), ("ahmadi", "Islam"),
            ("norelig", "No religion"), ("notstated", None), ("other", "Other religion"))
LANGUAGE = {"creole": "Mauritian Creole", "bhojpuri": "Bhojpuri", "french": "French",
            "english": "English", "hindi": "Hindi", "bangla": "Bengali",
            "chineselanguages": "Chinese languages", "marathi": "Marathi", "tamil": "Tamil",
            "telugu": "Telugu", "urdu": "Urdu", "othernotstated": "Other languages or not stated"}

ETHNICITY_NOTE = ("Mauritius has not asked residents' ethnic group in its census since 1972 "
                  "(the 2022 census records religion, language usually spoken at home and "
                  "language of forefathers), so there is no census figure for it.")
AGE = re.compile(r"^(?:<\s*(?P<lt>\d+)|(?P<lo>\d+)\s*-\s*(?P<hi>\d+)|(?P<top>\d+)\s*\+)$")


def cell(v: Any) -> Any:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return " ".join(v.split())
    return v


def sheets(blob: bytes) -> dict[str, list[list[Any]]]:
    import openpyxl                                 # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return {ws.title.strip(): [[cell(v) for v in r] for r in ws.iter_rows(values_only=True)]
            for ws in wb.worksheets if ws.title.strip() in ("D2", "D6", "D9")}


def unit_of(label: str) -> str | None:
    """The map unit a block's label is the whole of, or None."""
    k = key(label)
    if "ward" in k or "vca" in k or "village" in k:
        return None
    for unit, wants in UNITS.items():
        if any(w in k for w in wants) and ("district" in k or unit == "rodrigues"):
            return unit
    return None


def heads(rows: list[list[Any]]) -> list[str]:
    """Each column's head: the lowest text above the first figure (a head
    spanning several columns, such as "Religious group", sits above them)."""
    out: dict[int, list[str]] = {}
    for row in rows[:8]:
        if any(isinstance(v, int) for v in row[1:]):
            break
        for i, v in enumerate(row):
            if i and isinstance(v, str) and v:
                out.setdefault(i, []).append(v)
    width = max(len(r) for r in rows[:8])
    return [(out.get(i) or [""])[-1] for i in range(width)]


def read_d2(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    head = heads(rows)
    cols = {}
    for i, h in enumerate(head):
        hit = AGE.match(h.strip())
        if hit:
            if hit.group("lt"):
                cols[i] = (0, int(hit.group("lt")))
            elif hit.group("top"):
                cols[i] = (int(hit.group("top")), None)
            else:
                cols[i] = (int(hit.group("lo")), int(hit.group("hi")) - int(hit.group("lo")) + 1)
    total_col = next(i for i, h in enumerate(head) if key(h) == "allages")
    out: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for row in rows:
        label = row[0] if row and isinstance(row[0], str) else ""
        if label and not any(isinstance(v, int) for v in row[1:]):
            unit = unit_of(label)
            current = unit if unit and unit not in out else None
            if current:
                out[current] = {"label": label}
            continue
        if current and label in ("Both sexes", "Male", "Female"):
            out[current][label] = row
    for unit, b in out.items():
        both, men, women = b.get("Both sexes"), b.get("Male"), b.get("Female")
        if not (both and men and women) or men[total_col] + women[total_col] != both[total_col]:
            raise SystemExit(f"mauritius_census: D2 {b['label']}: men and women do not make "
                             f"its total")
        ages = [(lo, w, both[i]) for i, (lo, w) in sorted(cols.items())]
        if sum(n for _, _, n in ages) != both[total_col]:
            raise SystemExit(f"mauritius_census: D2 {b['label']}: its age groups do not make "
                             f"{both[total_col]:,}")
        b.update(total=both[total_col], men=men[total_col], women=women[total_col], ages=ages)
    return out


def read_composition(rows: list[list[Any]], what: str, mapper) -> dict[str, dict[str, Any]]:
    head = heads(rows)
    total_col = next(i for i, h in enumerate(head) if key(h).startswith("total"))
    groups = {i: mapper(h) for i, h in enumerate(head) if i > total_col and h}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        label = row[0] if row and isinstance(row[0], str) else ""
        unit = unit_of(label) if label else None
        if not unit or unit in out or not isinstance(row[total_col], int):
            continue
        counts: dict[str, int] = {}
        unstated = 0
        for i, g in groups.items():
            v = row[i] if i < len(row) and isinstance(row[i], int) else 0
            if g is None:
                unstated += v
            else:
                counts[g] = counts.get(g, 0) + v
        if sum(counts.values()) + unstated != row[total_col]:
            raise SystemExit(f"mauritius_census: {what} {label}: the groups make "
                             f"{sum(counts.values()) + unstated:,}, not {row[total_col]:,} "
                             f"(heads {head})")
        out[unit] = {"label": label, "total": row[total_col], "unstated": unstated,
                     "counts": counts}
    return out


def religion_of(head: str) -> str | None | bool:
    k = key(head)
    for part, name in RELIGION:
        if part in k:
            return name
    return f"{head}".strip()


def language_of(head: str) -> str:
    k = key(re.sub(r"\s+\d+$", "", head))
    return LANGUAGE.get(k, re.sub(r"\s+\d+$", "", head).strip())


def build(tables: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ages, rel, lang = tables["D2"], tables["D6"], tables["D9"]
    missing = [u for u in UNITS if u not in ages or u not in rel or u not in lang]
    if missing:
        raise SystemExit(f"mauritius_census: no block for {missing}")
    made = sum(ages[u]["total"] for u in UNITS)
    if made != NATIONAL:
        raise SystemExit(f"mauritius_census: the districts and islands make {made:,}")
    sources = [{"field": "population/sex_ratio/median_age",
                "name": f"{SOURCE}, Table D2", "url": URL, "license": LICENCE, "year": YEAR},
               {"field": "religion", "name": f"{SOURCE}, Table D6", "url": URL,
                "license": LICENCE, "year": YEAR},
               {"field": "language", "name": f"{SOURCE}, Table D9", "url": URL,
                "license": LICENCE, "year": YEAR}]
    out = []
    for level, shapes in (("admin1", admin1), ("admin2", admin2)):
        for shape in shapes:
            u = key(shape["name"])
            if u in OUTER:
                note = OUTER_NOTE.format(name=OUTER[u])
                out.append(record(
                    f"MUS-2022-{level}-{u}", shape["name"], level=level, parent="MUS",
                    country="MUS", match_by="shape_id", shape_id=shape["id"],
                    sources=sources[:1],
                    median_age=gap(NOT_AVAILABLE, note), sex_ratio=gap(NOT_AVAILABLE, note),
                    religion=gap(NOT_AVAILABLE, note), language=gap(NOT_AVAILABLE, note),
                    ethnicity=gap(NOT_AVAILABLE, ETHNICITY_NOTE)))
                continue
            if u not in UNITS:
                raise SystemExit(f"mauritius_census: no census unit for {shape['name']!r}")
            a, r, g = ages[u], rel[u], lang[u]
            if not (a["total"] == r["total"] == g["total"]):
                raise SystemExit(f"mauritius_census: {shape['name']}'s tables count "
                                 f"{a['total']}, {r['total']} and {g['total']}")
            stated = r["total"] - r["unstated"]
            out.append(record(
                f"MUS-2022-{level}-{u}", shape["name"], level=level, parent="MUS",
                country="MUS", match_by="shape_id", shape_id=shape["id"], sources=sources,
                population=measure(a["total"], year=YEAR, source=f"{SOURCE}, Table D2"),
                population_note=f"The 2022 census's resident population of {shape['name']}.",
                sex_ratio=sex_ratio(a["men"], a["women"], year=YEAR,
                                    source=f"{SOURCE}, Table D2"),
                median_age=measure(grouped_median(a["ages"]), year=YEAR,
                                   source=f"{SOURCE}, Table D2"),
                median_age_note=("Interpolated within the age group that holds the middle "
                                 "person, from the 2022 census's counts by age group "
                                 "(Table D2)."),
                religion=shares({k: v for k, v in r["counts"].items() if v}, total=stated),
                religion_year=YEAR,
                religion_note=(f"Religious group of the {stated:,} residents who stated one, of "
                               f"{r['total']:,} (Table D6). The census's five Hindu groups -- "
                               f"Hindu & Other Hindu, Tamil, Telugu, Marathi and Vedic -- are "
                               f"one Hindu group here."),
                language=shares({k: v for k, v in g["counts"].items() if v},
                                total=g["total"]),
                language_year=YEAR, language_basis="language usually spoken at home",
                language_note=("Language usually spoken at home, as the 2022 census records it "
                               "for every resident (Table D9)."),
                ethnicity=gap(NOT_AVAILABLE, ETHNICITY_NOTE)))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=("2024", "2025"), expect=b"PK")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    raw = sheets(blob)
    tables = {"D2": read_d2(raw["D2"]),
              "D6": read_composition(raw["D6"], "D6", religion_of),
              "D9": read_composition(raw["D9"], "D9", language_of)}
    for name, t in tables.items():
        log(f"  {name}: {[(u, b['label']) for u, b in t.items()]}")
    records = build(tables, units("MUS", "admin1"), units("MUS", "admin2"))
    for r in records:
        if r["level"] == "admin1":
            log(f"  {r['name']}: {r['population']['value']:,}, ratio {r['sex_ratio']['value']}, "
                f"median {r['median_age']['value']}, {r['religion'][:2]}, {r['language'][:1]}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
