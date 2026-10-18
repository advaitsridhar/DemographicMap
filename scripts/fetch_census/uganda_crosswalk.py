#!/usr/bin/env python3
"""Write ``uganda_counties.py``: which 2024 census units make each Ugandan county polygon.

The map draws Uganda's counties as they stood around 2002; the 2024 census
counts some 310 counties, cities and municipalities, many cut from the older
counties since, and below them some 2,200 sub-counties. This measures which of
them make each drawn polygon, from points sampled evenly over each unit's
outline, and writes the result as a module the adapter imports (the runner has
no boundary files, so this runs where they are).

**County level.** Each 2024 county, city division or municipality (the census
dashboard's outlines, ``uganda_county_points.json``) is placed in the polygon
holding at least three quarters of its points on land. A polygon is written as
the sum of the units placed in it (PLACED) only where it is shown to be their
ground:

* no unit placed elsewhere, or in no polygon, has a quarter or more of its
  points inside it;
* no such unit has one point in twenty or more inside it farther than 2 km
  from its line; and
* none of its own units has one point in twenty or more outside it farther
  than 2 km from its line.

Points within 2 km of a line are where two drawings of the same line disagree,
the boundary file's and the Bureau's: Koboko's, a district whose lines have not
moved since 2002, run up to 3 km apart, and the 16% of Kira Municipality's
points inside the Kampala polygon all lie within 1.6 km of its line. Beyond
2 km, a neighbour's ground is inside the polygon, or the polygon's ground in a
neighbour. Two polygons are set by hand: Kampala's is the city's five
divisions, the same ground as Kampala District of 2002, whose boundary has not
moved (the Bureau draws Rubaga division twice, its main outline with a third
of its points outside the boundary file's Kampala, all within 1.8 km of the
line, and a small piece wholly inside), and Buvuma's is the island district,
whose outline the Bureau draws over the lake.

**Sub-county level.** A polygon refused at county level is settled from the
2024 sub-counties (the sub-county profile tables, ``uganda_subcounties.json``)
where every unit crossing it can be split: each of the unit's 2024
sub-counties matched by name, within its district, to one of OCHA's sub-county
outlines of 2020 (``uganda_subcounty_points.json``) that lies in one polygon by
the same tests. SETTLED gives such a polygon's whole units and the sub-counties
of the crossing ones that lie in it. STRADDLING names, for every other polygon,
the 2024 units that cross its line (those with a tenth or more of their points
inside it, or one in twenty farther in than 2 km, and its own units with one
in twenty farther out).

Usage:
    python -m scripts.fetch_census.uganda_crosswalk > scripts/fetch_census/uganda_counties.py
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED = ROOT / "data" / "processed"
BOUNDARIES = ROOT / "data" / "raw" / "boundaries" / "geoBoundariesCGAZ_ADM2.gpkg"
PLACE = 0.75
INTRUDE = 0.25
DEEP = 0.05
DEPTH_KM = 2.0
# A unit with this share of its points inside a polygon is named as crossing it.
NAMED = 0.10
KM_PER_DEGREE = 111.0
# Polygons set by hand: Kampala (the city's five divisions) and Buvuma (the
# island district, whose outline the Bureau draws over the lake).
FORCED = {"47994165B16286500452212": ["1021", "1022", "1023", "1024", "1025"],
          "47994165B9859706646942": ["1201"]}


def refusals(stats: dict[str, dict[str, float]], members: set[str]) -> list[tuple[str, str]]:
    """Why a polygon is not its members' ground, from each unit's
    {"share": share of its points inside, "deep_in": share inside farther than
    DEPTH_KM from the line, "deep_out": share outside farther than DEPTH_KM}:
    [(unit, "in" | "out")], empty when it is."""
    out = []
    for code, s in sorted(stats.items()):
        if code in members:
            if s.get("deep_out", 0) >= DEEP:
                out.append((code, "out"))
        elif s.get("share", 0) >= INTRUDE or s.get("deep_in", 0) >= DEEP:
            out.append((code, "in"))
    return out


def crossing(stats: dict[str, dict[str, float]], members: set[str]) -> list[str]:
    """The units named as crossing a refused polygon's line."""
    return sorted(code for code, s in stats.items()
                  if (code not in members and (s.get("share", 0) >= NAMED
                                               or s.get("deep_in", 0) >= DEEP))
                  or (code in members and s.get("deep_out", 0) >= DEEP))


def fold(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\btown council\b", "tc", text)
    text = re.sub(r"\b(division|sub[- ]?county|ward)\b", "", text)
    return re.sub(r"[^a-z]", "", text)


def district_key(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower().replace(" city", ""))


class Map:
    """The boundary file's Ugandan polygons, and where points fall in them."""

    def __init__(self) -> None:
        import fiona                                # noqa: PLC0415
        from shapely.geometry import shape          # noqa: PLC0415
        from shapely.strtree import STRtree         # noqa: PLC0415
        self.shapes: dict[str, Any] = {}
        with fiona.open(BOUNDARIES) as src:
            for f in src:
                if f["properties"].get("shapeGroup") == "UGA":
                    self.shapes[f["properties"]["shapeID"]] = shape(f["geometry"])
        self.ids = list(self.shapes)
        self.tree = STRtree([self.shapes[i] for i in self.ids])
        self.lines = {i: g.boundary for i, g in self.shapes.items()}

    def locate(self, points: list[list[float]]) -> list[tuple[Any, str]]:
        """[(point, polygon)] for the points on land."""
        from shapely.geometry import Point          # noqa: PLC0415
        out = []
        for x, y in points:
            p = Point(x, y)
            for idx in self.tree.query(p):
                if self.shapes[self.ids[idx]].contains(p):
                    out.append((p, self.ids[idx]))
                    break
        return out

    def stats(self, located: list[tuple[Any, str]], sid: str) -> dict[str, float]:
        n = len(located)
        if not n:
            return {}
        line = self.lines[sid]
        inside = [p for p, s in located if s == sid]
        outside = [p for p, s in located if s != sid]
        return {"share": len(inside) / n,
                "deep_in": sum(1 for p in inside
                               if line.distance(p) * KM_PER_DEGREE > DEPTH_KM) / n,
                "deep_out": sum(1 for p in outside
                                if line.distance(p) * KM_PER_DEGREE > DEPTH_KM) / n}


def home_of(located: list[tuple[Any, str]]) -> str | None:
    counts: dict[str, int] = defaultdict(int)
    for _, sid in located:
        counts[sid] += 1
    if not counts:
        return None
    best = max(counts, key=counts.get)
    return best if counts[best] >= PLACE * len(located) else None


def judge(geo: Map, located: dict[str, list[tuple[Any, str]]], sid: str,
          members: set[str]) -> tuple[list[tuple[str, str]], dict[str, dict[str, float]]]:
    """The refusals for polygon ``sid`` with ``members``, and the units' stats."""
    stats = {}
    for code, loc in located.items():
        if code in members or any(s == sid for _, s in loc):
            stats[code] = geo.stats(loc, sid)
    return refusals(stats, members), stats


def build() -> dict[str, Any]:
    geo = Map()
    units = json.loads((PROCESSED / "uganda_county_points.json").read_text())
    names: dict[str, str] = {}
    pooled: dict[str, list[list[float]]] = defaultdict(list)
    for u in units:
        # A unit drawn twice (Rubaga division) is one unit.
        pooled[u["code"]].extend(u["points"])
        names[u["code"]] = u["name"]
    meta = {u["code"]: u for u in units}
    located = {code: geo.locate(points) for code, points in pooled.items()}
    homes = {code: home_of(loc) for code, loc in located.items()}
    placed: dict[str, set[str]] = defaultdict(set)
    for code, sid in homes.items():
        if sid:
            placed[sid].add(code)
    accepted: dict[str, list[str]] = {}
    refused: dict[str, tuple[list[tuple[str, str]], dict[str, dict[str, float]]]] = {}
    for sid in geo.ids:
        if sid in FORCED:
            accepted[sid] = FORCED[sid]
            continue
        why, stats = judge(geo, located, sid, placed.get(sid, set()))
        if placed.get(sid) and not why:
            accepted[sid] = sorted(placed[sid])
        else:
            refused[sid] = (why, stats)
    # Sub-county level, for the refused polygons.
    table = json.loads((PROCESSED / "uganda_subcounties.json").read_text())
    outlines = json.loads((PROCESSED / "uganda_subcounty_points.json").read_text())
    by_name: dict[tuple[str, str], list[str]] = defaultdict(list)
    out_loc: dict[str, list[tuple[Any, str]]] = {}
    for o in outlines:
        pr = o["props"]
        by_name[(district_key(pr["adm2_name"]), fold(pr["adm4_name"]))].append(pr["adm4_pcode"])
        out_loc[pr["adm4_pcode"]] = geo.locate(o["points"])
    out_home = {c: home_of(loc) for c, loc in out_loc.items()}
    counties = {}
    for code, u in meta.items():
        hits = [r for r in table if r["level"] == "county" and r["name"] == u["name"]
                and r["total"] == u["total"]]
        if len(hits) == 1:
            counties[code] = hits[0]
    settled: dict[str, dict[str, Any]] = {}
    straddling: dict[str, list[str]] = {}
    for sid, (why, stats) in refused.items():
        members = placed.get(sid, set())
        split = sorted({code for code, _ in why})
        whole = sorted(c for c in members if c not in split)
        parts: list[list[str]] = []
        ok = bool(split)
        for code in split:
            county = counties.get(code)
            if county is None:
                ok = False
                break
            kids = [r for r in table if r["level"] == "subcounty"
                    and r["county"] == county["name"] and r["district"] == county["district"]]
            for kid in kids:
                hit = by_name.get((district_key(kid["district"]), fold(kid["name"])), [])
                home = out_home.get(hit[0]) if len(hit) == 1 else None
                if home is None or refusals({"x": geo.stats(out_loc[hit[0]], home)}, {"x"}):
                    ok = False
                    break
                if home == sid:
                    parts.append([kid["district"], kid["county"], kid["name"]])
            if not ok:
                break
        if ok and (whole or parts):
            settled[sid] = {"counties": whole, "subcounties": parts}
        else:
            straddling[sid] = sorted({names[c] for c in crossing(stats, members)})
    return {"placed": accepted, "settled": settled, "straddling": straddling, "names": names}


def block(items: list[str], indent: str) -> list[str]:
    lines, out = [], indent
    for c in items:
        piece = json.dumps(c, ensure_ascii=False) + ", "
        if len(out) + len(piece) > 99:
            lines.append(out.rstrip())
            out = indent
        out += piece
    lines.append(out.rstrip().rstrip(","))
    return lines


def render(result: dict[str, Any], labels: dict[str, str]) -> str:
    doc = ("Which of the 2024 census's counties, cities and municipalities, or sub-counties, make "
           "each of the map's Ugandan counties (generated by uganda_crosswalk, do not edit by "
           "hand; the rules are in its docstring). PLACED gives the polygons that are whole "
           "2024 counties; SETTLED those that are whole counties and sub-counties, the "
           "sub-counties by district, county and name as the 2024 sub-county profile tables "
           "give them; STRADDLING names, for every other polygon, the 2024 units that cross "
           "its line. Kampala and Buvuma are set by hand.")
    out = ['"""' + textwrap.fill(doc, 79, break_long_words=False) + '\n"""', "", "PLACED = {"]
    names = result["names"]
    for sid in sorted(result["placed"], key=lambda s: labels.get(s, s)):
        codes = result["placed"][sid]
        note = "  (set by hand)" if sid in FORCED else ""
        out.append(f"    # {labels.get(sid, '?')}: "
                   + ", ".join(" ".join(names.get(c, c).split()) for c in codes) + note)
        out.append(f'    "{sid}": [')
        out += block(codes, "        ")
        out.append("    ],")
    out.append("}")
    out.append("SETTLED = {")
    for sid in sorted(result["settled"], key=lambda s: labels.get(s, s)):
        entry = result["settled"][sid]
        out.append(f"    # {labels.get(sid, '?')}")
        out.append(f'    "{sid}": {{')
        out.append('        "counties": [')
        out += block(entry["counties"], "            ")
        out.append("        ],")
        out.append('        "subcounties": [')
        for part in entry["subcounties"]:
            out.append("            " + json.dumps(part, ensure_ascii=False) + ",")
        out.append("        ],")
        out.append("    },")
    out.append("}")
    out.append("STRADDLING = {")
    for sid in sorted(result["straddling"], key=lambda s: labels.get(s, s)):
        out.append(f"    # {labels.get(sid, '?')}")
        out.append(f'    "{sid}": [')
        out += block(result["straddling"][sid], "        ")
        out.append("    ],")
    out.append("}")
    return "\n".join(out) + "\n"


def main() -> int:
    result = build()
    labels = {r["id"]: r["name"].strip() for r in
              json.loads((ROOT / "site" / "data" / "admin2" / "UGA.units.json").read_text())}
    sys.stdout.write(render(result, labels))
    print(f"{len(result['placed'])} placed, {len(result['settled'])} settled at sub-county "
          f"level, {len(result['straddling'])} straddling", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
