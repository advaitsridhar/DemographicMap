#!/usr/bin/env python3
"""Switzerland: population, median age and sex ratio for the districts the map draws.

**What the map draws.** geoBoundaries' Swiss second level is the district
map of about 2009, not today's: Bern's 26 Amtsbezirke (replaced by ten
Verwaltungskreise in 2010), Thurgau's eight districts (five since 2011),
Lucerne's five Ämter (Wahlkreise since 2013), Graubünden's eleven Bezirke
(Regionen since 2016), Neuchâtel's six districts (abolished 2018), and
Schaffhausen's six Bezirke, beside Vaud's post-2008 districts. The Federal
Statistical Office's own register of communes and districts through time
(the "Historisiertes Gemeindeverzeichnis", served by the AGVCH API) lists
exactly that division on 1 January 2009, so 2009 is the vintage every
polygon is read against.

**Where the figures come from.** BFS table px-x-0102010000_101 gives the
permanent resident population on 31 December by commune, sex and single
year of age (0 to 99, then 100 and over), in today's communes. The AGVCH
correspondence table says, for every commune of 2009, which commune of today
it became. A 2009 district is then the sum of today's communes whose every
2009 predecessor lay inside it.

**Where that is impossible, nothing is written.** Seventeen of today's
communes were merged across a 2009 district line -- Neuchâtel (2021) out of
three districts, Bellinzona (2017) out of two, Lyss with Busswil, Chur with
Haldenstein, Murten with Clavaleyres across a cantonal border -- and BFS
publishes no split of them. A district one of them straddles cannot be
summed without putting part of a merged commune's people on the wrong
polygon, so those districts are left out and named in the log, and the
map's other districts are filled.

**Special polygons.** Basel-Stadt is drawn as its three communes, which are
read as communes. Appenzell Ausserrhoden is drawn whole although BFS's 2009
register still divides it into three districts; the three are summed.
Valais's Raron district is drawn as its two historic halves, Östlich and
Westlich Raron, which are made of the communes declared below and checked
to be all of it. The second polygon labelled Schaffhausen is the district's
exclave south of the Rhine, Buchberg and Rüdlingen, and is read as those
two communes. "Bodensee" is Thurgau's part of Lake Constance, where nobody
lives.

Usage:
    python -m scripts.fetch_census.switzerland_ages [--year 2025]
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import time
from collections import Counter
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, write_json
from .central_ages import age_sex_fields, check_national_median, check_sum, fold, units
from .pxweb import http_json, unstack

TABLE = "https://www.pxweb.bfs.admin.ch/api/v1/de/px-x-0102010000_101/px-x-0102010000_101.px"
AGVCH = "https://www.agvchapp.bfs.admin.ch/api/communes/"
VINTAGE = "01-01-2009"
PORTAL = "https://www.pxweb.bfs.admin.ch/pxweb/de/px-x-0102010000_101/"
SOURCE = ("Federal Statistical Office (BFS/OFS), STATPOP, px-x-0102010000_101, and the "
          "historicised register of communes (AGVCH)")
LICENCE = "BFS open data (free reuse with attribution)"
OUT = PROCESSED / "switzerland_bezirk.json"

# The two halves of the Raron district as drawn, by their 2009 communes.
RARON = {
    "Raron": {"Betten", "Bister", "Bitsch", "Filet", "Grengiols", "Martisberg", "Mörel",
              "Mörel-Filet", "Riederalp"},
    "West Raron": {"Ausserberg", "Blatten", "Bürchen", "Eischoll", "Ferden", "Hohtenn",
                   "Kippel", "Niedergesteln", "Raron", "Steg", "Steg-Hohtenn", "Unterbäch",
                   "Wiler (Lötschen)"},
}
SCHAFFHAUSEN_EXCLAVE = {"Buchberg", "Rüdlingen"}
BASEL_STADT = {"Basel", "Bettingen", "Riehen"}
WATER = {"Bodensee"}
LAKE = re.compile(r"(?i)\b(?:see|lac|lago|lai|lej)\b|bodensee|thunersee|brienzersee|zürichsee")
# Map spellings that no prefix rule reaches.
ALIASES = {"Jura-Nord vaudois": "Jura-North Vaudois",
           "Riviera-Pays-d'Enhaut": "Pays-d'Enhaut"}
PREFIXES = ("Amtsbezirk ", "Bezirk ", "Amt ", "Wahlkreis ", "Kanton ", "Canton de ",
            "Distretto di ", "District de la ", "District de l'", "District du ", "District des ",
            "District de ", "District d'")
ARTICLE = {"District de la ": "La ", "District du ": "Le ", "District des ": "Les "}


def agvch(query: str) -> list[dict[str, str]]:
    text = http_get(AGVCH + query, timeout=300)
    if not text.startswith(("HistoricalCode", "InitialHistoricalCode")):
        raise SystemExit(f"switzerland_ages: AGVCH answered something else for {query}: {text[:120]!r}")
    return list(csv.DictReader(io.StringIO(text)))


def variants(name: str) -> set[str]:
    out = set()
    for part in (p.strip() for p in name.split("/")):
        part = re.sub(r"\s*\([^)]*\)", "", part).strip()
        for prefix in PREFIXES:
            if part.startswith(prefix):
                rest = part[len(prefix):]
                out |= {rest, ARTICLE.get(prefix, "") + rest}
                break
        else:
            out.add(part)
    out |= {ALIASES[v] for v in out if v in ALIASES}
    out |= {v.replace("St. ", "Sankt ") for v in out}
    return {fold(v) for v in out}


def read_population(year: int, communes: list[str], batch: int) -> dict[str, dict[str, Any]]:
    """Commune code -> {"m": Counter, "f": Counter, "total"} for the year."""
    meta = {v["code"]: v for v in http_json(TABLE)["variables"]}
    code = {k: next(c for c in meta if c.startswith(k)) for k in
            ("Jahr", "Kanton", "Bevölkerungstyp", "Staatsangehörigkeit", "Geschlecht", "Alter")}
    if str(year) not in meta[code["Jahr"]]["values"]:
        raise SystemExit(f"switzerland_ages: the table has no {year}")
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(communes), batch):
        chunk = communes[start:start + batch]
        query = [
            {"code": code["Jahr"], "selection": {"filter": "item", "values": [str(year)]}},
            {"code": code["Kanton"], "selection": {"filter": "item", "values": chunk}},
            {"code": code["Bevölkerungstyp"], "selection": {"filter": "item", "values": ["1"]}},
            {"code": code["Staatsangehörigkeit"], "selection": {"filter": "item", "values": ["-99999"]}},
            {"code": code["Geschlecht"], "selection": {"filter": "item", "values": ["-99999", "1", "2"]}},
            {"code": code["Alter"], "selection": {"filter": "item",
                                                  "values": meta[code["Alter"]]["values"]}},
        ]
        payload = http_json(TABLE, {"query": query, "response": {"format": "json-stat2"}})
        for key, value in unstack(payload):
            commune = key[code["Kanton"]][0]
            sex, age = key[code["Geschlecht"]][0], key[code["Alter"]][0]
            unit = out.setdefault(commune, {"m": Counter(), "f": Counter(), "total": None})
            if age == "-99999":
                if sex == "-99999":
                    unit["total"] = value
                continue
            if sex == "1":
                unit["m"][int(age)] += value
            elif sex == "2":
                unit["f"][int(age)] += value
        time.sleep(0.5)
    return out, meta, code


def build(year: int, batch: int) -> list[dict[str, Any]]:
    log(f"switzerland_ages: BFS px-x-0102010000_101, 31 December {year}, "
        f"read against the districts of {VINTAGE}")
    snapshot = agvch(f"snapshot?date={VINTAGE}")
    cantons = {r["HistoricalCode"]: r for r in snapshot if r["Level"] == "1"}
    districts = {r["HistoricalCode"]: r for r in snapshot if r["Level"] == "2"}
    old_communes = {r["BfsCode"]: r for r in snapshot if r["Level"] == "3"}
    meta = {v["code"]: v for v in http_json(TABLE)["variables"]}
    place_code = next(c for c in meta if c.startswith("Kanton"))
    px_communes = [v for v in meta[place_code]["values"] if re.fullmatch(r"\d{4}", v)]
    # Which structure the table's communes are in: the end date whose
    # correspondence lands on exactly the table's communes.
    lakes: set[str] = set()
    for end in (f"01-01-{year + 1}", f"31-12-{year}", f"01-01-{year}"):
        rows = agvch(f"correspondances?startPeriod={VINTAGE}&endPeriod={end}&includeUnmodified=true")
        names_t = {str(int(r["TerminalCode"])).zfill(4): r["TerminalName"] for r in rows}
        only_px = set(px_communes) - set(names_t)
        only_register = set(names_t) - set(px_communes)
        # The register lists the cantons' lake areas as communes; nobody lives
        # there and the population table leaves them out.
        if not only_px and all(LAKE.search(names_t[c]) for c in only_register):
            lakes = only_register
            log(f"  the table's {len(px_communes)} communes are the register's of {end}"
                + (f" (less its lake areas: {sorted(names_t[c] for c in lakes)})" if lakes else ""))
            break
        log(f"  {end}: {len(only_px)} of the table's communes not in the register, "
            f"{len(only_register)} the other way")
    else:
        raise SystemExit("switzerland_ages: no register date matches the table's communes")
    initial_of: dict[str, set[str]] = {}          # today's commune -> its 2009 communes
    for r in rows:
        initial_of.setdefault(str(int(r["TerminalCode"])).zfill(4), set()).add(r["InitialCode"])
    if set().union(*initial_of.values()) != set(old_communes):
        missing = set(old_communes) - set().union(*initial_of.values())
        raise SystemExit(f"switzerland_ages: 2009 communes with no successor: {sorted(missing)[:10]}")

    data, meta, code = read_population(year, px_communes, batch)
    for commune, unit in data.items():
        made = sum(unit["m"].values()) + sum(unit["f"].values())
        if abs(made - unit["total"]) > 0.5:
            raise SystemExit(f"switzerland_ages: commune {commune}: men and women by age make "
                             f"{made:,.0f}, the total is {unit['total']:,.0f}")
    national_query = [
        {"code": code["Jahr"], "selection": {"filter": "item", "values": [str(year)]}},
        {"code": code["Kanton"], "selection": {"filter": "item", "values": ["8100"]}},
        {"code": code["Bevölkerungstyp"], "selection": {"filter": "item", "values": ["1"]}},
        {"code": code["Staatsangehörigkeit"], "selection": {"filter": "item", "values": ["-99999"]}},
        {"code": code["Geschlecht"], "selection": {"filter": "item", "values": ["-99999"]}},
        {"code": code["Alter"], "selection": {"filter": "item", "values": ["-99999"]}},
    ]
    national = next(v for _, v in unstack(http_json(TABLE, {"query": national_query,
                                                             "response": {"format": "json-stat2"}})))
    check_sum((u["total"] for u in data.values()), national, "communes against Switzerland")
    ages = Counter()
    for u in data.values():
        ages.update(u["m"])
        ages.update(u["f"])
    check_national_median(ages, "CH", year + 1)

    # The units to fill: a name, its canton, and its 2009 communes.
    targets: list[tuple[str, str, set[str]]] = []
    for hist, d in districts.items():
        canton = cantons[d["Parent"]]
        members = {c for c, r in old_communes.items() if r["Parent"] == hist}
        if canton["ShortName"] in ("BS", "AR") or d["Name"] == "Bezirk Raron":
            continue
        if d["Name"] == "Bezirk Schaffhausen":
            exclave = {c for c in members if old_communes[c]["Name"] in SCHAFFHAUSEN_EXCLAVE}
            if len(exclave) != len(SCHAFFHAUSEN_EXCLAVE):
                raise SystemExit("switzerland_ages: Buchberg and Rüdlingen are not both in "
                                 "the 2009 district of Schaffhausen")
            targets.append(("Schaffhausen (exclave)", canton["Name"], exclave))
            members -= exclave
        targets.append((d["Name"], canton["Name"], members))
    bs = [c for c, r in old_communes.items()
          if cantons[districts[r["Parent"]]["Parent"]]["ShortName"] == "BS"]
    if {old_communes[c]["Name"] for c in bs} != BASEL_STADT:
        raise SystemExit(f"switzerland_ages: Basel-Stadt's 2009 communes are "
                         f"{sorted(old_communes[c]['Name'] for c in bs)}")
    for c in bs:
        targets.append((old_communes[c]["Name"], "Basel-Stadt", {c}))
    ar = [h for h, d in districts.items() if cantons[d["Parent"]]["ShortName"] == "AR"]
    targets.append(("Appenzell Ausserrhoden", "Appenzell Ausserrhoden",
                    {c for c, r in old_communes.items() if r["Parent"] in ar}))
    raron = next(h for h, d in districts.items() if d["Name"] == "Bezirk Raron")
    raron_members = {c for c, r in old_communes.items() if r["Parent"] == raron}
    halves = {half: {c for c in raron_members if old_communes[c]["Name"] in names_}
              for half, names_ in RARON.items()}
    if set().union(*halves.values()) != raron_members or halves["Raron"] & halves["West Raron"]:
        raise SystemExit("switzerland_ages: the declared halves of Raron are not its communes: "
                         + str(sorted(old_communes[c]["Name"] for c in raron_members)))
    for half, members in halves.items():
        targets.append((half, "Valais / Wallis", members))

    shapes = units("CHE", "admin2")
    canton_of = {u["id"]: u["name"] for u in units("CHE", "admin1")}
    exclave_shape = min((s for s in shapes if s["name"] == "Schaffhausen"),
                        key=lambda s: (s["bbox"][2] - s["bbox"][0]) * (s["bbox"][3] - s["bbox"][1]))
    source = SOURCE
    records, used, skipped, unbound = [], set(), [], []
    for name, canton_name, members in sorted(targets):
        if name == "Schaffhausen (exclave)":
            hits = [exclave_shape]
        else:
            keys = variants(name)
            hits = [s for s in shapes if fold(s["name"]) in keys and s["id"] != exclave_shape["id"]
                    and any(fold(p) == fold(canton_of.get(s["parent"], ""))
                            for p in canton_name.split("/"))]
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{name} ({canton_name}): {[h['name'] for h in hits]}")
            continue
        shape = hits[0]
        used.add(shape["id"])
        todays = sorted(t for t, ini in initial_of.items() if ini & members)
        straddling = [t for t in todays if not initial_of[t] <= members]
        if straddling:
            names_ = [next(r["TerminalName"] for r in rows if str(int(r["TerminalCode"])).zfill(4) == t)
                      for t in straddling]
            skipped.append(f"{name}: {', '.join(names_)}")
            note = (f"Not written: the map draws this district as it was in 2009, and "
                    f"{', '.join(names_)} -- today's commune(s) -- merged 2009 communes from inside "
                    f"and outside it. BFS publishes today's communes only, so no official figure "
                    f"covers exactly this polygon.")
            records.append(record(
                f"CHE-2009-{fold(name)}", shape["name"], level="admin2", parent=shape["parent"],
                country="CHE", match_by="shape_id", shape_id=shape["id"],
                median_age=gap(NOT_AVAILABLE, note), sex_ratio=gap(NOT_AVAILABLE, note)))
            continue
        m, f, total = Counter(), Counter(), 0.0
        for t in todays:
            if t in lakes:
                continue
            m.update(data[t]["m"])
            f.update(data[t]["f"])
            total += data[t]["total"]
        fields = age_sex_fields(
            m, f, year=year, source=source, total=total,
            median_note=(f"Interpolated within the single year of age that holds the middle "
                         f"person, from BFS's count of the permanent resident population on 31 "
                         f"December {year} by single year of age, summed over the {len(todays)} "
                         f"communes of today that lie wholly within this unit as it was drawn "
                         f"in 2009."),
            ratio_note=(f"Males per 100 females in the permanent resident population on 31 "
                        f"December {year}, same communes."))
        records.append(record(
            f"CHE-2009-{fold(name)}", shape["name"], level="admin2", parent=shape["parent"],
            country="CHE", codes={"bfs_2009": name, "bfs_communes_today": ",".join(todays)},
            match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population/median_age/sex_ratio", "name": source, "url": PORTAL,
                      "license": LICENCE, "year": year}],
            **fields))
    left = sorted(s["name"] for s in shapes if s["id"] not in used)
    log(f"  {len(records) - len(skipped)} units written; {len(skipped)} left out because a "
        f"commune of today straddles them:")
    for line in skipped:
        log(f"    - {line}")
    log(f"  units unbound: {unbound}")
    log(f"  polygons with no unit: {left}")
    if unbound or set(left) - WATER:
        raise SystemExit("switzerland_ages: units and polygons do not pair up one to one")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--batch", type=int, default=60)
    args = ap.parse_args()
    records = build(args.year, args.batch)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
