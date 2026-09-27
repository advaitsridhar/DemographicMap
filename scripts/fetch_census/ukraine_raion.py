#!/usr/bin/env python3
"""Ukraine's pre-2020 raions from the 2001 census, and its oblasts' ages from 2017.

**2001 is the last census Ukraine has held.** The 2011 and 2020 rounds were
postponed and then cancelled; every figure here from the census describes 5
December 2001.

The map's second level is the 494 raions of before the 2020 reform, drawn the
way the boundary file draws them: each city of oblast significance -- counted
by the census apart, as a city council (міськрада) -- lies inside one of the
raion polygons, usually the raion it is the seat of and sometimes a
neighbour's. So a polygon's figure is its raion's and the cities' the map
draws inside it, added together, and a raion's figure alone is never put on a
polygon holding a city it does not include.

The figures are the State Statistics Service's 2001 census as the U.S. Census
Bureau tabulated them by rayon and city council (HDX, "Ukraine Subnational
Population and Housing Data Tables"): population by sex and five-year age
group, nationality (Nationality-Language's whole-population block) and native
language. The census database the Service itself published
(database.ukrcensus.gov.ua) answers 404 and the Internet Archive holds only
its dialog pages, not its tables, so this is the reachable form of the
office's own count, in five-year groups -- the median is interpolated within
the group holding the middle person, and says so.

**Binding.** By geometry, checked by name. The Bureau publishes its own
polygons for the areas it tabulated (Ukraine.gdb, same HDX dataset, keyed by
the same GEO_MATCH code as the tables); each area goes to the map polygon
holding the majority of its area, which is what says where a city counted
apart is drawn. Every raion is also matched by name within its oblast -- the
census's adjective ("Bakhchysaraiskyi") against the polygon's town
("Bakhchysarai"), or through the renaming declared below (2016's
decommunisation renamed a raion in most oblasts, and the census predates it)
-- and the run lists every raion where the two disagree. A polygon into which
a quarter or more of an area it is not given reaches is refused with the
reason, as are Sevastopol's polygons: the census counts the city whole. Every
oblast's count must be held by its areas' polygons, or the run stops.

**Oblasts.** Median age and sex ratio from the Bureau's other Age-Sex sheet:
the Service's estimate for 1 January 2017 by oblast, sex and five-year group,
the newest by age the map can read for its oblasts. It covers neither Crimea
nor Sevastopol, whose figures come from 2001.

Usage:
    python -m scripts.fetch_census.ukraine_raion
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, RAW, download, gap, http_get, log, measure,
                      record, shares, write_json)
from . import east_geo, uscb
from .cod_ps_age import grouped_median

SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "ukraine_raion.json"
YEAR = 2001
SOURCE = ("State Statistics Service of Ukraine, All-Ukrainian Population Census "
          "2001, by rayon and city council, as tabulated by the U.S. Census Bureau")
SOURCE_2017 = ("State Statistics Service of Ukraine, population estimate for 1 "
               "January 2017 by oblast, sex and age group, as tabulated by the U.S. "
               "Census Bureau")
LICENCE = "CC BY-IGO, published via HDX"
LAST_CENSUS = (" The 2001 census is the last Ukraine has held: the 2011 and 2020 "
               "rounds were postponed and cancelled.")

# The Bureau's oblast name -> the map's.
OBLAST = {
    "AVTONOMNA RESPUBLIKA KRYM": "Autonomous Republic of Crimea",
    "CHERKAS’KA OBLAST’": "Cherkasy Oblast", "CHERNIHIVS’KA OBLAST’": "Chernihiv Oblast",
    "CHERNIVETS’KA OBLAST’": "Chernivtsi Oblast",
    "DNIPROPETROVS’KA OBLAST’": "Dnipropetrovsk Oblast",
    "DONETS’KA OBLAST’": "Donetsk Oblast",
    "IVANO-FRANKIVS’KA OBLAST’": "Ivano-Frankivsk Oblast",
    "KHARKIVS’KA OBLAST’": "Kharkiv Oblast", "KHERSONS’KA OBLAST’": "Kherson Oblast",
    "KHMEL’NYTS’KA OBLAST’": "Khmelnytskyi Oblast",
    "KIROVOHRADS’KA OBLAST’": "Kirovohrad Oblast", "KYYIVS’KA OBLAST’": "Kyiv Oblast",
    "LUHANS’KA OBLAST’": "Luhansk Oblast", "L’VIVS’KA OBLAST’": "Lviv Oblast",
    "MYKOLAYIVS’KA OBLAST’": "Mykolaiv Oblast", "ODES’KA OBLAST’": "Odessa Oblast",
    "POLTAVS’KA OBLAST’": "Poltava Oblast", "RIVNENS’KA OBLAST’": "Rivne Oblast",
    "SUMS’KA OBLAST’": "Sumy Oblast", "TERNOPIL’S’KA OBLAST’": "Ternopil Oblast",
    "VINNYTS’KA OBLAST’": "Vinnytsia Oblast", "VOLYNS’KA OBLAST’": "Volyn Oblast",
    "ZAKARPATS’KA OBLAST’": "Zakarpattia Oblast",
    "ZAPORIZ’KA OBLAST’": "Zaporizhia Oblast", "ZHYTOMYRS’KA OBLAST’": "Zhytomyr Oblast",
    "MISTO KYYIV": "Kyiv", "MISTO SEVASTOPOL’": "Sevastopol",
}

# Raions renamed since 2001, the census's name -> the polygon's. The 2016
# decommunisation laws renamed most of these (Artemivskyi to Bakhmutskyi,
# Kotovskyi to Podilskyi, Tsiurupynskyi to Oleshkivskyi ...); Volodymyr and
# Zviahel took their names in 2021-2022. Each pair is the raion and its seat's
# new name, which is what the polygon is called.
RENAMED = {
    "ARTEMIVSKYI RAION": "Bakhmut", "KRASNOARMIISKYI RAION": "Pokrovsk",
    "KRASNOLYMANSKYI RAION": "Lyman", "PERSHOTRAVNEVYI RAION": "Manhush",
    "TELMANIVSKYI RAION": "Boikivske", ("Donetsk Oblast", "VOLODARSKYI RAION"): "Nikolske",
    "KRASNODONSKYI RAION": "Sorokyne", "SVERDLOVSKYI RAION": "Dovzhansk",
    "CHERVONOARMIISKYI RAION": "Pulyny", "DZERZHYNSKYI RAION": "Romaniv",
    "NOVOHRAD-VOLYNSKYI RAION": "Zviahel", "VOLODARSKO-VOLYNSKYI RAION": "Khoroshiv",
    "VOLODYMYR-VOLYNSKYI RAION": "Volodymyr", "KIROVOHRADSKYI RAION": "Kropyvnytskyi",
    "ULIANOVSKYI RAION": "Blahovishchenske", "SHCHORSKYI RAION": "Snovsk",
    "DNIPROPETROVSKYI RAION": "Dnipro", "TSIURUPYNSKYI RAION": "Oleshky",
    "ZHOVTNEVYI RAION": "Vitovka", "FRUNZIVSKYI RAION": "Zakharivka",
    "KOMINTERNIVSKYI RAION": "Lyman", "KOTOVSKYI RAION": "Podilsk",
    "KRASNOOKNIANSKYI RAION": "Okny", "KUIBYSHEVSKYI RAION": "Bilmak",
    "SOVIETSKYI RAION": "Sovietsky", "KYIEVO-SVIATOSHYNSKYI RAION": "Kyiv-Sviatoshyn",
    "BILOTSERKIVSKYI RAION": "Bila Tserkva",
}



def base(nso: str) -> str:
    """The Bureau's name without the oblast it adds to tell namesakes apart:
    "VOLODARSKYI RAION (DONETSKA OBLAST)" -> "VOLODARSKYI RAION"."""
    return re.sub(r"\s*\(.*$", "", nso.strip())


def renamed(oblast: str, nso: str) -> str | None:
    return RENAMED.get((oblast, base(nso))) or RENAMED.get(base(nso))


# Polygons the boundary file files under a neighbouring oblast. The raion is
# bound to its polygon wherever the file puts it, and the run says so: the
# polygon is that raion whatever its parent field says.
ELSEWHERE = {
    ("Cherkasy Oblast", "KAMIANSKYI RAION"): ("Kirovohrad Oblast", "Kamianka"),
    ("Kyiv Oblast", "MYRONIVSKYI RAION"): ("Cherkasy Oblast", "Myronivka"),
}

# An area goes to the polygon holding at least this share of its area; below
# CLEAN the run names it; a polygon that PART or more of an area it is not
# given reaches into is refused.
HOLD = 0.5
CLEAN = 0.9
PART = 0.25
UNIT = re.compile(r"^UKR_\d{2}_\d{2}$")


def census_shapes() -> dict[str, Any]:
    """{GEO_MATCH: polygon in longitude and latitude} for the Bureau's
    second-order areas, from the geodatabase it publishes beside the tables."""
    import zipfile

    import fiona
    from fiona.transform import transform_geom
    from shapely.geometry import shape

    resources = uscb.package(uscb.UKRAINE.dataset).get("resources", [])
    found = [r for r in resources if (r.get("name") or "").lower().endswith(".gdb.zip")]
    if not found:
        raise SystemExit("ukraine_raion: the HDX dataset lists no geodatabase: "
                         + ", ".join(str(r.get("name")) for r in resources))
    archive = download(found[0]["url"], RAW / "uscb" / "ukraine.gdb.zip")
    with zipfile.ZipFile(archive) as zf:
        roots = sorted({n.split("/")[0] for n in zf.namelist()
                        if n.split("/")[0].lower().endswith(".gdb")})
    path = f"zip://{archive}!{roots[0]}" if roots else f"zip://{archive}"
    out: dict[str, Any] = {}
    for layer in fiona.listlayers(path):
        with fiona.open(path, layer=layer) as src:
            fields = list(src.schema["properties"])
            first = next(iter(src), None)
            key = next((f for f in fields if first is not None
                        and isinstance(first["properties"].get(f), str)
                        and UNIT.match(first["properties"][f])), None)
            epsg = src.crs.to_epsg() if src.crs else None
            log(f"  {layer}: {len(src)} features, EPSG {epsg}, key {key}; "
                f"fields {fields[:16]}")
            if not key or out:
                continue
            for feature in src:
                code = feature["properties"].get(key)
                if not isinstance(code, str) or not UNIT.match(code):
                    continue
                geometry = feature["geometry"]
                if epsg != 4326:
                    geometry = transform_geom(src.crs, "EPSG:4326", geometry)
                polygon = shape(geometry).buffer(0)
                out[code] = out[code].union(polygon) if code in out else polygon
    if not out:
        raise SystemExit("ukraine_raion: no layer of the geodatabase is keyed by "
                         "second-order GEO_MATCH codes")
    log(f"  the Bureau's polygons: {len(out)} second-order areas")
    return out


def overlay(units: dict[str, Any], polys: dict[str, Any]) -> dict[str, list[tuple[str, float]]]:
    """{area: [(map polygon, share of the area's own area inside it)]}, largest
    share first."""
    from shapely.strtree import STRtree

    ids = list(polys)
    geoms = [polys[i].buffer(0) for i in ids]
    tree = STRtree(geoms)
    out: dict[str, list[tuple[str, float]]] = {}
    for code, unit in units.items():
        area = unit.area
        hits = []
        for j in tree.query(unit):
            inside = geoms[int(j)].intersection(unit).area
            if area and inside / area >= 0.005:
                hits.append((ids[int(j)], inside / area))
        out[code] = sorted(hits, key=lambda h: -h[1])
    return out

GROUP = re.compile(r"^B(\d{2,3})(\d{2,3})$")
OPEN = re.compile(r"^B(\d{2,3})PL$")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\(.*?\)|\(.*$", "", text)
    text = re.sub(r"\b(raion|rayon|district|miskrada|m\.)\b", "", text)
    return re.sub(r"[^a-z]", "", text)


def consonants(text: str) -> str:
    """A name's consonant skeleton: the vowel shifts between a town and its
    raion's adjective (Mezhova, Mezhivskyi; Chutove, Chutivskyi) drop out."""
    text = fold(text)
    for a, b in (("shch", "s"), ("kh", "h"), ("zh", "j"), ("ts", "c"), ("ch", "c"),
                 ("sh", "s"), ("iy", "i"), ("yi", "i")):
        text = text.replace(a, b)
    return re.sub(r"[aeiouy]", "", text)


def raion_stem(nso: str) -> str:
    """The town a raion's adjective is made from, as a consonant skeleton."""
    name = re.sub(r"\s*RAION.*$", "", base(nso))
    name = re.sub(r"(S?KYI|TSKYI|ZKYI|YI)$", "", name)
    return consonants(name)


def number(value: Any) -> float | None:
    return uscb.number(value)


def age_rows(book, sheet: str) -> dict[tuple[str, str], dict[str, Any]]:
    """{(oblast, area): total, men, women, groups, level, nso} from an Age-Sex sheet."""
    rows = uscb.sheet_rows(book, sheet)
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    prefix = "P17_" if any(n.startswith("P17_") for n in names) else ""
    wanted = [prefix + c for c in ("BTOTL", "MTOTL", "FTOTL")] + ["ADM_LEVEL", "NSO_NAME"]
    if missing := [c for c in wanted if c not in at]:
        raise SystemExit(f"ukraine_raion: {sheet} has no {missing}; its columns: "
                         + " ".join(n for n in names if n)[:1500])
    out = {}
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        if level is None:
            continue
        adm1 = str(row[at.get("ADM1_NAME", 0)] or "").strip()
        adm2 = str(row[at["ADM2_NAME"]] or "").strip() if "ADM2_NAME" in at else ""
        groups = []
        for name, i in at.items():
            core = name[len(prefix):] if name.startswith(prefix) else name
            if (m := GROUP.match(core)) and core.startswith("B"):
                groups.append((int(m.group(1)), int(m.group(2)), number(row[i]) or 0.0))
            elif (m := OPEN.match(core)) and core.startswith("B"):
                groups.append((int(m.group(1)), None, number(row[i]) or 0.0))
        total = number(row[at[prefix + "BTOTL"]])
        men = number(row[at[prefix + "MTOTL"]])
        women = number(row[at[prefix + "FTOTL"]])
        unstated = number(row[at[prefix + "B_UNSTATED"]]) if prefix + "B_UNSTATED" in at else 0.0
        out[(adm1, adm2)] = {"level": int(level), "nso": str(row[at["NSO_NAME"]] or "").strip(),
                             "match": str(row[at["GEO_MATCH"]] or "").strip()
                             if "GEO_MATCH" in at else "",
                             "total": total, "men": men, "women": women,
                             "unstated": unstated or 0.0,
                             "groups": sorted(groups, key=lambda g: g[0])}
    return out


def check_row(key, r) -> None:
    if not r["total"]:
        return
    made = sum(n for _, _, n in r["groups"]) + r["unstated"]
    if abs(made - r["total"]) > 0.5 or abs((r["men"] or 0) + (r["women"] or 0) - r["total"]) > 0.5:
        raise SystemExit(f"ukraine_raion: {key}: groups {made:,.0f}, sexes "
                         f"{(r['men'] or 0) + (r['women'] or 0):,.0f}, total {r['total']:,.0f}")


def add(parts: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"total": 0.0, "men": 0.0, "women": 0.0, "unstated": 0.0, "groups": None}
    for p in parts:
        for k in ("total", "men", "women", "unstated"):
            out[k] += p[k] or 0.0
        if out["groups"] is None:
            out["groups"] = [list(g) for g in p["groups"]]
        else:
            for g, h in zip(out["groups"], p["groups"]):
                if (g[0], g[1]) != (h[0], h[1]):
                    raise SystemExit("ukraine_raion: two rows' age groups do not line up")
                g[2] += h[2]
    out["groups"] = [tuple(g) for g in out["groups"] or []]
    return out


def age_fields(r: dict[str, Any], year: int, source: str, note: str) -> dict[str, Any]:
    median = grouped_median(list(r["groups"]))
    return {
        "median_age": measure(median, unit="years", year=year, source=source)
        if median is not None else gap(NOT_AVAILABLE),
        "median_age_note": ("Interpolated within the five-year age group holding the "
                            "middle person" + (f"; the {r['unstated']:,.0f} people whose "
                                               "age was not stated are left out"
                                               if r["unstated"] else "") + "." + note),
        "sex_ratio": measure(round(100 * r["men"] / r["women"], 1),
                             unit="males_per_100_females", year=year, source=source),
        "sex_ratio_note": f"{int(r['men']):,} men and {int(r['women']):,} women." + note,
    }


def bind_raions(raions: list[tuple[tuple[str, str], dict[str, Any]]],
                shapes: dict[str, list[dict[str, Any]]]) -> tuple[dict, list[str]]:
    """{row key: shape} for the raions, by name within the oblast."""
    report = []
    bound: dict[tuple[str, str], dict[str, Any]] = {}
    by_oblast: dict[str, list] = defaultdict(list)
    for key, r in raions:
        by_oblast[OBLAST[key[0]]].append((key, r))
    for oblast, rows in by_oblast.items():
        polys = shapes.get(oblast, [])
        taken: set[str] = set()
        pending = []
        for key, r in rows:
            new_name = renamed(oblast, r["nso"])
            moved = ELSEWHERE.get((oblast, base(r["nso"])))
            if moved:
                target = [s for s in shapes.get(moved[0], []) if s["name"] == moved[1]]
                if len(target) != 1:
                    raise SystemExit(f"ukraine_raion: no single polygon {moved}")
                bound[key] = target[0]
                report.append(f"{oblast}: {r['nso']} is the polygon {moved[1]!r}, which "
                              f"the boundary file files under {moved[0]}")
                continue
            if new_name:
                target = [s for s in polys if s["name"] == new_name]
                if len(target) != 1:
                    raise SystemExit(f"ukraine_raion: {oblast} has {len(target)} polygons "
                                     f"named {new_name!r} for the renamed {r['nso']}")
                bound[key] = target[0]
                taken.add(target[0]["id"])
                continue
            pending.append((key, r))
        free = [s for s in polys if s["id"] not in taken]
        scores = {(i, s["id"]): likeness(r["nso"], s["name"])
                  for i, (key, r) in enumerate(pending) for s in free}
        chosen: dict[int, str] = {}
        used: set[str] = set()
        # Best pair first; a pair is taken only when it beats every rival
        # for either side by the margin, so two raions that look alike to a
        # polygon (Skole and Sokal to "Skolivskyi") refuse rather than guess.
        for (i, sid), score in sorted(scores.items(), key=lambda kv: -kv[1]):
            if i in chosen or sid in used or score < LIKE:
                continue
            rivals = [v for (j, o), v in scores.items()
                      if (j == i and o != sid and o not in used)
                      or (o == sid and j != i and j not in chosen)]
            if score - max(rivals, default=0.0) < LIKE_MARGIN:
                continue
            chosen[i] = sid
            used.add(sid)
        by_id = {s["id"]: s for s in free}
        for i, (key, r) in enumerate(pending):
            if i in chosen:
                bound[key] = by_id[chosen[i]]
                if not skeleton_agrees(r["nso"], by_id[chosen[i]]["name"]):
                    report.append(f"{oblast}: {r['nso']} -> {by_id[chosen[i]]['name']!r} "
                                  f"by likeness {scores[(i, chosen[i])]:.2f}")
                continue
            best = sorted(((v, o) for (j, o), v in scores.items() if j == i), reverse=True)[:2]
            report.append(f"{oblast}: {r['nso']} not bound; nearest "
                          + ", ".join(f"{by_id[o]['name']} {v:.2f}" for v, o in best))
    return bound, report


# How alike a raion's adjective and a polygon's town must be, and by how much
# the pair must beat its nearest rival, for the pair to be bound.
LIKE = 0.75
LIKE_MARGIN = 0.08


def skeleton_agrees(nso: str, polygon: str) -> bool:
    """The consonant skeletons agree, or one runs on from the other by at most
    two letters (Mezhivskyi, Mezhova; Chornobaivskyi, Chornobai)."""
    stem = raion_stem(nso)
    other = consonants(polygon)
    return (other == stem
            or (len(stem) >= 3 and other.startswith(stem) and len(other) - len(stem) <= 2)
            or (len(other) >= 3 and stem.startswith(other) and len(stem) - len(other) <= 2))


def likeness(nso: str, polygon: str) -> float:
    """The closest letter-for-letter likeness of the adjective, cut back to
    each plausible stem, to the polygon's name (Horodyshchenskyi, Horodyshche),
    lifted when the consonant skeletons agree as well."""
    from difflib import SequenceMatcher
    name = fold(re.sub(r"\s*RAION.*$", "", base(nso)))
    target = fold(polygon)
    best = 0.0
    for ending in (r"yi$", r"kyi$", r"skyi$", r"(?:iv|ian|yn|en|n|i)skyi$"):
        cut = re.sub(ending, "", name)
        best = max(best, SequenceMatcher(None, cut, target).ratio()
                   + (0.05 if len(os.path.commonprefix([cut, target])) >= 4 else 0.0))
    return best + (0.10 if skeleton_agrees(nso, polygon) else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    import openpyxl

    url = uscb.workbook_url(uscb.UKRAINE.dataset)
    blob = http_get(url, binary=True, cache_dir=RAW / "uscb")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    ages = age_rows(book, "Age-Sex 2001")
    ages17 = age_rows(book, "Age-Sex 2017")
    # Compositions at the second level, read as the oblast adapter reads them.
    cfg = replace(uscb.UKRAINE, levels={2: "admin2"}, sum_into=None)
    topics = {t.field: t for t in uscb.UKRAINE.topics}
    comps = {field: uscb.read(book, cfg, topic) for field, topic in topics.items()}
    book.close()

    for key, r in ages.items():
        check_row(key, r)
    level2 = {k: r for k, r in ages.items() if r["level"] == 2}
    level1 = {k[0]: r for k, r in ages.items() if r["level"] == 1}
    for oblast, whole in level1.items():
        made = sum(r["total"] for k, r in level2.items() if k[0] == oblast)
        if abs(made - whole["total"]) > 0.5:
            raise SystemExit(f"ukraine_raion: {oblast}'s areas make {made:,.0f}, "
                             f"the oblast {whole['total']:,.0f}")
    log(f"  Age-Sex 2001: {len(level2)} rayons and city councils in {len(level1)} "
        "oblasts; every row's groups and sexes make its total, every oblast's areas "
        "make the oblast")

    admin1 = json.loads((SITE / "admin1" / "UKR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "UKR.units.json").read_text())
    parent_name = {u["id"]: u["name"] for u in admin1}
    shapes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in admin2:
        shapes[parent_name[u["parent"]]].append(u)

    site_ids = {u["id"]: u for u in admin2}
    by_match = {r["match"]: k for k, r in level2.items() if r["match"]}
    if len(by_match) != len(level2):
        raise SystemExit("ukraine_raion: the Age-Sex 2001 sheet's GEO_MATCH codes are "
                         "missing or repeated")

    # Where each area counted lies on the map: the Bureau's own polygons for
    # the areas it tabulated, laid over the map's. This, not a name, is what
    # says which polygon a city counted apart is drawn inside.
    units = census_shapes()
    polys = {sid: geom for sid, (geom, _) in east_geo.polygons("UKR").items()
             if sid in site_ids}
    lies = overlay({m: units[m] for m in by_match if m in units}, polys)

    # The raions by name, as the check on the overlay: the two ways must agree.
    raions = [(k, r) for k, r in level2.items() if "RAION" in r["nso"]
              and k[0] not in ("MISTO KYYIV", "MISTO SEVASTOPOL’")]
    named, report = bind_raions(raions, shapes)
    home: dict[tuple[str, str], str] = {}
    thin: list[str] = []
    disagree: list[str] = []
    undrawn: list[tuple[str, str]] = []
    refused: dict[str, str] = {}
    for match, key in by_match.items():
        nso = level2[key]["nso"]
        if match not in units and key[0] in ("MISTO KYYIV", "MISTO SEVASTOPOL’"):
            # The two cities the map draws apart: Kyiv as one polygon, and
            # Sevastopol, whose polygons are refused below whatever lies where.
            home[key] = shapes[OBLAST[key[0]]][0]["id"]
            report.append(f"{OBLAST[key[0]]}: {nso} has no polygon in the geodatabase; "
                          f"placed in the city's own polygon")
            continue
        if match not in units:
            # No polygon of the Bureau's: a raion can still go by its name; a
            # city council cannot, as nothing then says where it is drawn.
            if key in named:
                home[key] = named[key]["id"]
                report.append(f"{OBLAST[key[0]]}: {nso} has no polygon in the geodatabase; "
                              f"placed by name in {named[key]['name']!r}")
                continue
            raise SystemExit(f"ukraine_raion: {nso} ({match}) has no polygon in the "
                             "geodatabase and no name to place it by")
        hits = lies[match]
        if not hits or hits[0][1] < HOLD:
            # The map does not draw most of this area: counted, and nowhere.
            undrawn.append(key)
            report.append(f"{OBLAST[key[0]]}: {nso} lies in no map polygon by a majority "
                          "of its area: " + ", ".join(f"{site_ids[o]['name']} {s:.0%}"
                                                      for o, s in hits[:3]))
            continue
        sid, share = hits[0]
        home[key] = sid
        if share < CLEAN:
            thin.append(f"{nso} {share:.0%} in {site_ids[sid]['name']}, "
                        + ", ".join(f"{site_ids[o]['name']} {s:.0%}" for o, s in hits[1:3]))
        if share < 1 - PART:
            refused[sid] = (f"Only {share:.0%} of the area the 2001 census counts as "
                            f"{nso.title()} lies in this polygon, so the census's figure "
                            "for it would not describe what the polygon draws.")
        if key in named and named[key]["id"] != sid:
            disagree.append(f"{OBLAST[key[0]]}: {nso} is named for "
                            f"{named[key]['name']!r} and lies in {site_ids[sid]['name']!r}")
    for line in report:
        log("  " + line)
    log(f"  names bind {len(named)} of {len(raions)} raions; the overlay disagrees with "
        f"{len(disagree)} of them")
    for line in disagree:
        log("    " + line)
    if thin:
        log(f"  {len(thin)} areas lie less than {CLEAN:.0%} in their polygon:")
        for line in thin:
            log("    " + line)

    members: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, sid in home.items():
        members[sid].append(key)
        if (parent_name[site_ids[sid]["parent"]] != OBLAST[key[0]]
                and key[0] != "MISTO SEVASTOPOL’"):
            log(f"  {OBLAST[key[0]]}: {level2[key]['nso']} lies in "
                f"{site_ids[sid]['name']!r}, which the map files under "
                f"{parent_name[site_ids[sid]['parent']]}")

    # A polygon is refused when a sizeable part of an area it is not given
    # lies inside it, or when it holds Sevastopol, which the census counts
    # whole and the map cuts in two.
    for match, key in by_match.items():
        if match not in lies:
            continue
        where = (f"counted with {site_ids[home[key]]['name']!r}" if key in home
                 else "drawn in no polygon by a majority of its area")
        for sid, share in lies[match] if key in undrawn else lies[match][1:]:
            if share >= PART and sid not in refused:
                refused[sid] = (f"{share:.0%} of the area the 2001 census counts as "
                                f"{level2[key]['nso'].title()} lies in this polygon, and "
                                f"that area's people are {where}; the census's figures "
                                "cannot be split between the two.")
    seva_why = ("The 2001 census counts Sevastopol whole; the map cuts it into polygons, "
                "and the whole city's figures describe none of them.")
    for key in (k for k in level2 if k[0] == "MISTO SEVASTOPOL’"):
        for sid, share in lies.get(level2[key]["match"], []):
            if share >= 0.01:
                refused[sid] = seva_why
    for shape in shapes["Sevastopol"]:
        refused[shape["id"]] = seva_why
    for sid, why in sorted(refused.items()):
        log(f"  refused {site_ids[sid]['name']} ({parent_name[site_ids[sid]['parent']]}): "
            f"{why}")

    # Every oblast's census count is held by the polygons, refused or not, or
    # named above as drawn nowhere.
    for oblast, whole in level1.items():
        made = sum(level2[k]["total"] for k in list(home) + undrawn if k[0] == oblast)
        if abs(made - whole["total"]) > 0.5:
            raise SystemExit(f"ukraine_raion: {oblast}'s polygons hold {made:,.0f} of "
                             f"its {whole['total']:,.0f}")

    records: list[dict[str, Any]] = []
    raions_only = 0
    for sid, keys in sorted(members.items()):
        if sid in refused:
            continue
        shape = site_ids[sid]
        rows = [level2[k] for k in keys]
        whole = add(rows)
        names = [level2[k]["nso"].title()
                 for k in sorted(keys, key=lambda k: ("RAION" not in level2[k]["nso"], k))]
        if all(k[0] == "MISTO KYYIV" for k in keys):
            note = (f" The city of Kyiv: its {len(keys)} raions of 2001 added together."
                    + LAST_CENSUS)
        else:
            note = (" The polygon is " + " with ".join(names)
                    + (", which the census counts apart and the map draws inside it"
                       if len(names) > 1 else "")
                    + "." + LAST_CENSUS)
        if len(names) == 1:
            raions_only += 1
        values: dict[str, Any] = {
            "population": measure(int(whole["total"]), year=YEAR, source=SOURCE),
            "population_note": "Everyone counted by the 2001 census." + note,
            **age_fields(whole, YEAR, SOURCE, note),
        }
        cites = [{"field": f, "name": SOURCE, "url": uscb.dataset_url(uscb.UKRAINE.dataset),
                  "license": LICENCE, "year": YEAR}
                 for f in ("population", "median_age", "sex_ratio")]
        for field, topic in topics.items():
            counts: Counter = Counter()
            published = 0.0
            missing = []
            for k in keys:
                row = comps[field].get((k[0], k[1]))
                if not row:
                    missing.append(level2[k]["nso"].title())
                    continue
                for label, n in row["counts"].items():
                    counts[uscb.UKRAINE.relabel.get(label, label)] += n
                published += row["published"] or row["summed"]
            if missing:
                values[field] = gap(NOT_AVAILABLE, f"The Bureau's {topic.sheet} sheet has "
                                    f"no figures for {', '.join(missing)}.")
                continue
            values[field] = shares(dict(counts), total=published)
            values[f"{field}_year"] = YEAR
            values[f"{field}_note"] = (topic.note or uscb.UKRAINE.note) + note
            cites.append({"field": field, "name": SOURCE,
                          "url": uscb.dataset_url(uscb.UKRAINE.dataset),
                          "license": LICENCE, "year": YEAR})
        records.append(record(f"UKR-2001-{sid}", shape["name"], level="admin2", parent="UKR",
                              country="UKR", match_by="shape_id", shape_id=sid,
                              sources=cites, **values))
    for sid, why in sorted(refused.items()):
        shape = site_ids[sid]
        refusal = gap(NOT_AVAILABLE, why)
        records.append(record(f"UKR-2001-{sid}", shape["name"], level="admin2",
                              parent="UKR", country="UKR", match_by="shape_id",
                              shape_id=sid, population=refusal, median_age=refusal,
                              sex_ratio=refusal))

    # First level: the 2017 estimate by age where it exists, 2001 otherwise.
    first = {u["name"]: u for u in admin1}
    wrote_2017 = 0
    for bureau, name in OBLAST.items():
        shape = first[name]
        r17 = next((r for (a, _), r in ages17.items() if a == bureau and r["level"] == 1
                    and r["total"]), None)
        if r17:
            check_row(bureau, r17)
            note = " The State Statistics Service's estimate for 1 January 2017."
            values = age_fields(r17, 2017, SOURCE_2017, note)
            cites = [{"field": f, "name": SOURCE_2017,
                      "url": uscb.dataset_url(uscb.UKRAINE.dataset), "license": LICENCE,
                      "year": 2017} for f in ("median_age", "sex_ratio")]
            wrote_2017 += 1
        else:
            r01 = level1[bureau]
            note = (" From the 2001 census: the Service's later estimates by age do not "
                    "cover Crimea or Sevastopol." + LAST_CENSUS)
            values = age_fields(r01, YEAR, SOURCE, note)
            cites = [{"field": f, "name": SOURCE,
                      "url": uscb.dataset_url(uscb.UKRAINE.dataset), "license": LICENCE,
                      "year": YEAR} for f in ("median_age", "sex_ratio")]
        records.append(record(f"UKR-AGE-{shape['id']}", name, level="admin1", parent="UKR",
                              country="UKR", match_by="shape_id", shape_id=shape["id"],
                              sources=cites, **values))
    placed = {r["shape_id"] for r in records if r["level"] == "admin2"}
    left = sorted(u["name"] for u in admin2 if u["id"] not in placed)
    log(f"  {len(members) - len(set(members) & set(refused))} polygons written from "
        f"{len(home)} census areas ({raions_only} a raion alone), {len(refused)} refused, "
        f"{len(undrawn)} areas drawn nowhere; {wrote_2017} oblasts' ages from 2017; "
        f"polygons with no census area: {left}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
