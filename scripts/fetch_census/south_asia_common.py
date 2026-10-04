#!/usr/bin/env python3
"""What the South Asia readers share: the drawn units, binding, ages and ratios.

Every reader in this family does the same four things after it has parsed an
office's table, and each of them is the kind of thing that goes wrong quietly
when it is written six times:

* **find the polygon** a row belongs on. The map's units are read from
  ``site/data/<level>/<ISO>.units.json`` under the boundary file's own labels
  (:func:`common.as_drawn`), and a row is bound to a shape id only when exactly
  one unit answers to its name inside the parent it names. Two rows claiming
  one unit, or one row answering to two units, is refused -- a figure on the
  wrong polygon is the one error this project ranks below a gap -- and every
  row and every unit left over is returned so the run can say which.
* **the median age**, from single years where the office publishes them
  (:func:`median_single`, interpolated within the year of the middle person,
  the same rule as ``redatam.median_age``) and from five-year groups only
  where nothing finer is published (:func:`median_grouped`). A median in the
  open top group is refused rather than guessed.
* **the sex ratio**, as males per 100 females to one decimal -- the brief's
  convention and the one Pakistan's, Bangladesh's and Nepal's offices print.
* **the checks** a table supplies about itself: single years adding to the
  printed total, the sexes adding to persons, units adding to their parent.
  A failure is ``raise SystemExit``; nothing here smooths a mismatch.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._shared import log

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site" / "data"


# ---------------------------------------------------------------------------
# The map's units
# ---------------------------------------------------------------------------

def load_units(iso3: str, level: str, site: Path = SITE) -> list[dict[str, Any]]:
    """The units the map draws at one level, under the boundary file's labels.

    Each unit keeps the name the current build gave it as ``site_name`` -- for
    a shape bound by id that is the census row's name, not the boundary
    file's -- because a reader may legitimately match either.
    """
    path = site / level / f"{iso3}.units.json"
    units = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for unit in units:
        drawn = dict(unit)
        drawn["site_name"] = unit.get("name")
        if unit.get("shape_name"):
            drawn["name"] = unit["shape_name"]
        out.append(drawn)
    return out


_SUFFIXES = re.compile(
    r"\b(district|districts|zila|zilla|dzongkhag|gewog|province|division|"
    r"tehsil|taluka|city|town|atoll|thana)\b")


def fold(name: str | None) -> str:
    """A name with case, diacritics, punctuation and generic words removed."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    text = _SUFFIXES.sub(" ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def unit_keys(unit: dict[str, Any]) -> set[str]:
    """Every folded name a unit answers to: its label, its current name, aliases."""
    keys = {fold(unit.get("name")), fold(unit.get("site_name"))}
    for alias in unit.get("aliases") or ():
        keys.add(fold(alias))
    keys.discard("")
    return keys


def bind(rows: dict[str, tuple[str, ...]], units: list[dict[str, Any]],
         *, parent_of: dict[str, str] | None = None,
         parent_units: dict[str, set[str]] | None = None,
         ) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Bind each row to the one unit that answers to one of its names.

    ``rows`` maps a row key to the names it may be found under, the office's
    own first. ``parent_of`` maps a row key to its parent's key, and
    ``parent_units`` maps that parent key to the ids of the units allowed to
    carry the row (the drawn parent's children): a candidate outside them is
    not considered, which is what keeps two districts of one name in two
    provinces apart.

    Returns ``(bound, rows left over, units left over)``. A unit two rows
    answer to is given to neither and both rows are reported -- refusing is
    the only safe answer to a tie, since nothing says which is right.
    """
    candidates: dict[str, list[dict[str, Any]]] = {}
    for key, names in rows.items():
        wanted = {fold(n) for n in names if n}
        wanted.discard("")
        allowed = None
        if parent_of and parent_units is not None:
            allowed = parent_units.get(parent_of.get(key, ""), set())
        hits = [u for u in units
                if unit_keys(u) & wanted and (allowed is None or u["id"] in allowed)]
        # A unit whose own label is the row's first name beats one that only
        # answers through an alias: "Kurram" the shape over a shape whose
        # alias list happens to mention Kurram.
        exact = [u for u in hits if fold(u.get("name")) == fold(names[0])
                 or fold(u.get("site_name")) == fold(names[0])]
        candidates[key] = exact if len(exact) == 1 else hits
    claimed: Counter = Counter(u["id"] for hits in candidates.values()
                               if len(hits) == 1 for u in hits)
    bound: dict[str, dict[str, Any]] = {}
    left: list[str] = []
    for key, hits in candidates.items():
        if len(hits) == 1 and claimed[hits[0]["id"]] == 1:
            bound[key] = hits[0]
        else:
            left.append(key)
    used = {u["id"] for u in bound.values()}
    return bound, left, [u for u in units if u["id"] not in used]


def report_binding(where: str, bound: dict[str, Any], left: list[str],
                   spare: list[dict[str, Any]]) -> None:
    log(f"  {where}: {len(bound)} bound by shape id; {len(left)} row(s) and "
        f"{len(spare)} unit(s) left over")
    if left:
        log("    rows with no single unit: " + ", ".join(sorted(left)))
    if spare:
        log("    units no row reached: "
            + ", ".join(sorted(str(u.get("name")) for u in spare)))


# ---------------------------------------------------------------------------
# Ages and sexes
# ---------------------------------------------------------------------------

def median_single(ages: dict[int, float], *, open_from: int | None = None
                  ) -> float | None:
    """The median of single years of age, interpolated within its year.

    ``open_from`` is the first age of an open top group carried under that
    key ("75 & above" as 75). A median that falls inside it is refused: the
    group's width is unknown, so no year inside it can be named.
    """
    total = sum(n for n in ages.values() if n)
    if total <= 0:
        return None
    half, before = total / 2.0, 0.0
    for age in sorted(ages):
        n = ages[age] or 0
        if before + n >= half and n > 0:
            if open_from is not None and age >= open_from:
                return None
            return round(age + (half - before) / n, 1)
        before += n
    return None


def median_grouped(groups: Iterable[tuple[int, int | None, float]]) -> float | None:
    """The median of ``(low, high, people)`` groups, high None for the open one.

    Linear interpolation within the group that holds the middle person -- the
    standard reading of a grouped distribution, and only ever used where the
    office publishes nothing finer.
    """
    rows = sorted(groups, key=lambda g: g[0])
    total = sum(n for _, _, n in rows)
    if total <= 0:
        return None
    half, before = total / 2.0, 0.0
    for low, high, n in rows:
        if before + n >= half and n > 0:
            if high is None:
                return None
            return round(low + (half - before) / n * (high - low + 1), 1)
        before += n
    return None


def check_contiguous(groups: list[tuple[int, int | None, float]], where: str) -> None:
    """Groups from 0 without a gap, ending in exactly one open group."""
    edge = 0
    for i, (low, high, _n) in enumerate(sorted(groups, key=lambda g: g[0])):
        if low != edge:
            raise SystemExit(f"{where}: the age groups jump from {edge} to {low}")
        if high is None:
            if i != len(groups) - 1:
                raise SystemExit(f"{where}: an open group before the last one")
            return
        edge = high + 1
    raise SystemExit(f"{where}: the age groups have no open top group")


def males_per_100(males: float, females: float) -> float | None:
    if not males or not females:
        return None
    return round(100.0 * males / females, 1)


def agree(label: str, got: float, expected: float, *, tolerance: float = 0) -> None:
    """Two readings of one figure must agree, within ``tolerance`` (absolute)."""
    if abs(got - expected) > tolerance:
        raise SystemExit(f"{label}: {got:,} against {expected:,} "
                         f"({got - expected:+,}); the reading is not the table")


def ages_add_up(label: str, ages: dict[Any, float], total: float,
                *, tolerance: float = 0) -> None:
    agree(f"{label}: the ages", sum(ages.values()), total, tolerance=tolerance)


def merge_counters(parts: Iterable[dict[Any, float]]) -> Counter:
    out: Counter = Counter()
    for part in parts:
        out.update({k: v for k, v in part.items() if v})
    return out
