"""The first-level unit the next build files each second-level polygon under.

A reader that says where the map files a district -- "the boundary file draws
it inside Tashkent Region, and its people are in the city's figure" -- reads
the map's parents from site/data, which is the last build's. But the build
does not take every parent from the geometry: ``build_entities.DECLARED_PARENTS``
files some polygons under the unit their census counts them in, whatever
first-level polygon holds most of them, and ``UNPARENTED`` and ``NOT_NESTED``
leave some with no first-level parent at all. A sentence written from the last
build's parents is false as soon as a declaration is added, until the reader
runs again after a rebuild -- and then it is false the other way.

So such a reader applies the declarations itself: ``as_filed`` gives the drawn
second-level units with the parent the next build will give them, from the
same table the build reads. The declarations are imported, not copied, so the
two cannot drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_entities  # noqa: E402


def as_filed(iso3: str, admin1: list[dict[str, Any]],
             admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``admin2`` (copies), each with the ``parent`` the build will file it under.

    ``admin1`` is the drawn first-level units under the boundary file's labels
    (``common.as_drawn``), which is how DECLARED_PARENTS names them. A
    declaration naming a label the country does not draw exactly once stops
    the run, as it stops the build. A polygon of a country whose second level
    is not nested, or one declared to have no first-level parent, is filed
    under the country.
    """
    by_label: dict[str, list[dict[str, Any]]] = {}
    for unit in admin1:
        by_label.setdefault(unit["name"], []).append(unit)
    out = []
    for unit in admin2:
        shape_id = unit.get("id") or ""
        wanted = build_entities.DECLARED_PARENTS.get(shape_id)
        if iso3 in build_entities.NOT_NESTED or shape_id in build_entities.UNPARENTED:
            unit = {**unit, "parent": iso3}
        elif wanted and wanted[0] == iso3:
            found = by_label.get(wanted[1], [])
            if len(found) != 1:
                raise SystemExit(f"declared_parents: {iso3} draws {len(found)} first-level "
                                 f"units labelled {wanted[1]!r}, where "
                                 f"{unit.get('name')!r} is declared under it")
            unit = {**unit, "parent": found[0]["id"]}
        out.append(unit)
    return out
