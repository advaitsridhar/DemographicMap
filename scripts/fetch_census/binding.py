"""Binding a statistics office's units to the map's polygons by shape id.

A boundary file's parent for a polygon is not always the office's: Argentina's
files Entre Ríos's departments under Buenos Aires, Panama's has a Ngäbe-Buglé
district under Veraguas. Name matching within a parent loses those, and name
matching across the country gives a namesake. ``bind`` does neither: it binds
by name within the parent where that is unique, then by a name no other
unbound polygon or unit shares, then, for a name several share, by the one
polygon lying among the parent's other units. Whatever is left is reported
and left out.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any


def fold(name: str) -> str:
    # Argentina's "1° de Mayo" is "1º de Mayo" in another of INDEC's tables: a
    # degree sign in one, an ordinal indicator (which NFKD reads as "o") in the
    # other.
    text = re.sub(r"[º°ª]", "", str(name or ""))
    stripped = unicodedata.normalize("NFKD", text)
    return "".join(c for c in stripped.lower() if c.isalnum() and not unicodedata.combining(c))


def bind(departments: dict[str, tuple[str, str]], shapes: list[dict[str, Any]],
         parents: dict[str, str], aliases: dict[str, str] | None = None
         ) -> tuple[dict[str, str], list[str]]:
    """Unit code -> the map's shape id, by name, then name, then place.

    ``departments`` is {code: (name, parent's map name or its own name)};
    ``parents`` the map's admin1 id -> name; ``aliases`` the office's
    spelling -> the boundary file's, where they differ by more than accents.
    """
    aliases = aliases or {}

    def key(name: str) -> str:
        return fold(aliases.get(name, name))

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in shapes:
        by_key[fold(shape["name"])].append(shape)
    bound: dict[str, str] = {}
    used: set[str] = set()

    def home(province: str) -> tuple[float, float, float, float] | None:
        points = [s["point"] for c, sid in bound.items() for s in shapes
                  if s["id"] == sid and departments[c][1] == province]
        if len(points) < 2:
            return None
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        pad = 0.3
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad

    # 1. By name within the province the boundary file files it under.
    for code, (name, province) in departments.items():
        hits = [s for s in by_key.get(key(name), [])
                if province and parents.get(s["parent"]) == province]
        if len(hits) == 1 and hits[0]["id"] not in used:
            bound[code] = hits[0]["id"]
            used.add(hits[0]["id"])
    progress = True
    while progress:
        progress = False
        pending = [c for c in departments if c not in bound]
        # 2. A name no other unbound polygon or department shares.
        names = defaultdict(list)
        for code in pending:
            names[key(departments[code][0])].append(code)
        for k, codes in names.items():
            free = [s for s in by_key.get(k, []) if s["id"] not in used]
            if len(codes) == 1 and len(free) == 1:
                bound[codes[0]] = free[0]["id"]
                used.add(free[0]["id"])
                progress = True
        # 3. For a shared name, the one free polygon among the province's others.
        for code in [c for c in departments if c not in bound]:
            box = home(departments[code][1] or departments[code][0])
            if box is None:
                continue
            free = [s for s in by_key.get(key(departments[code][0]), [])
                    if s["id"] not in used
                    and box[0] <= s["point"][0] <= box[2] and box[1] <= s["point"][1] <= box[3]]
            if len(free) == 1:
                bound[code] = free[0]["id"]
                used.add(free[0]["id"])
                progress = True
    missing = [f"{departments[c][0]} ({c})" for c in departments if c not in bound]
    return bound, missing
