"""Pieces the Southeast Asian age readers share: the drawn units, a median, a ratio.

Every reader in this family turns an office's count of people by age and sex
into the two figures the map shows, binds the office's units to the polygons
the map draws, and checks its sums on the way. What is common to all of them
is here, so that a median is interpolated, and a ratio rounded, one way
everywhere:

* ``drawn(iso3, level)`` -- the map's units under the boundary file's own
  labels (``common.as_drawn``), which is what an office's names are matched
  against; a rebuild renames a polygon after the census row bound to it, and
  matching on that name would move the ground under the matching.
* ``single_median`` -- the median of single years of age, interpolated within
  the year holding the middle person (``redatam.median_age``), the open top
  class given as the last key.
* ``grouped`` -- the same from five-year groups, interpolated within the group
  (``cod_ps_age.grouped_median``), for an office that publishes nothing finer.
* ``ratio`` -- males per 100 females, to one decimal.
* ``age_sex`` -- the record fields for one unit, notes and provenance included.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from typing import Any

from ._shared import PROCESSED, measure
from .cod_ps_age import grouped_median
from .redatam import median_age

SITE = PROCESSED.parent.parent / "site" / "data"


def drawn(iso3: str, level: str) -> list[dict[str, Any]]:
    """The map's units at ``level``, each under the boundary file's own label."""
    from common import as_drawn  # noqa: PLC0415 -- scripts/ is on the path via _shared
    return as_drawn(json.loads((SITE / level / f"{iso3}.units.json").read_text()))


def fold(text: Any) -> str:
    """A name reduced to its lower-case letters and digits, without accents."""
    text = unicodedata.normalize("NFKD", str(text or "").lower()).replace("đ", "d")
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def single_median(ages: Counter) -> float | None:
    """The median of a count by single year of age; the open top class last."""
    return median_age(ages)


def grouped(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median of ``(low, high, people)`` groups; None if it falls in the open one."""
    return grouped_median(sorted(groups, key=lambda g: g[0]))


def ratio(men: float, women: float) -> float | None:
    """Males per 100 females, to one decimal."""
    return round(100.0 * men / women, 1) if women else None


def age_sex(*, median: float | None, men: float, women: float, year: int, source: str,
            median_note: str, ratio_note: str, population: int | None = None,
            population_note: str | None = None) -> dict[str, Any]:
    """The record fields for one unit's median age, sex ratio and (optionally) population."""
    out: dict[str, Any] = {}
    if median is not None:
        out["median_age"] = measure(median, unit="years", year=year, source=source)
        out["median_age_note"] = median_note
    if women:
        out["sex_ratio"] = measure(ratio(men, women), unit="males_per_100_females",
                                   year=year, source=source)
        out["sex_ratio_note"] = ratio_note
    if population is not None:
        out["population"] = measure(population, year=year, source=source)
        if population_note:
            out["population_note"] = population_note
    return out


def check_runs(groups: list[tuple[int, int | None, float]], where: str) -> None:
    """Groups that start at 0 and climb without a gap to one open top group."""
    edge = 0
    for i, (low, high, _) in enumerate(sorted(groups, key=lambda g: g[0])):
        if low != edge:
            raise SystemExit(f"{where}: age groups jump to {low} where {edge} was due")
        if high is None:
            if i != len(groups) - 1:
                raise SystemExit(f"{where}: an open age group before the last")
            return
        edge = high + 1
    raise SystemExit(f"{where}: no open top age group")


AGE_LABEL = re.compile(r"^\s*(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*$")
OPEN_LABEL = re.compile(r"^\s*(\d{1,3})\s*(?:\+|and over|& over|and above|years and over"
                        r"|or more|plus|over)\s*$", re.IGNORECASE)


def band(label: Any) -> tuple[int, int | None] | None:
    """'15-19' -> (15, 19); '85+' / '85 and over' -> (85, None); 'Under 1' -> (0, 0)."""
    text = str(label or "").strip()
    if re.fullmatch(r"(?i)under\s*1|less than 1|<\s*1|0", text):
        return (0, 0)
    if m := AGE_LABEL.match(text):
        return int(m.group(1)), int(m.group(2))
    if m := OPEN_LABEL.match(text):
        return int(m.group(1)), None
    if re.fullmatch(r"\d{1,3}", text):
        return int(text), int(text)
    return None
