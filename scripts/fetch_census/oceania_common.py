"""What the Oceania census readers share: the map's units, binding, medians, records.

Each Pacific statistics office publishes its census as a handful of workbooks
or a report, by island, district or province. The readers built on these
helpers bind those units to the map's polygons by name within the parent the
boundary file gives them (``binding.bind``), write each record against the
polygon it was bound to (``match_by="shape_id"``), and stop rather than guess
when a unit or a polygon is left over.
"""

from __future__ import annotations

import io
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ._shared import NOT_COLLECTED, gap, http_get, log, measure, record
from .binding import bind, fold
from .cod_ps_age import grouped_median
from .redatam import median_age as single_year_median

SITE = Path(__file__).resolve().parents[2] / "site" / "data"


def load_units(iso3: str, level: str) -> list[dict[str, Any]]:
    """The map's units at one level, under the boundary file's own labels."""
    from common import as_drawn
    path = SITE / level / f"{iso3}.units.json"
    return as_drawn(json.loads(path.read_text())) if path.exists() else []


def workbook(url: str, attempts: int = 4):
    """A workbook fetched and opened for reading.

    An xlsx is a zip archive. Tonga's file server once answered 200 with a
    12 kB body that was not one, and the same URL gave the 218 kB workbook
    the next time, so a body that is not a zip is fetched again (uncached)
    after a pause, and the run stops only if it never comes.
    """
    import openpyxl
    for attempt in range(1, attempts + 1):
        blob = http_get(url, binary=True, timeout=300, cache=False)
        assert isinstance(blob, bytes)
        log(f"  {url}: {len(blob):,} bytes")
        if blob[:2] == b"PK":
            return openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        head = " ".join(blob[:160].decode("utf-8", "replace").split())
        log(f"    not a workbook (attempt {attempt} of {attempts}): {head!r}")
        if attempt < attempts:
            time.sleep(20 * attempt)
    raise SystemExit(f"{url}: no workbook after {attempts} attempts")


def rows_of(book, sheet: str) -> list[list[Any]]:
    """A sheet's rows as lists, trailing empty cells kept."""
    return [list(r) for r in book[sheet].iter_rows(values_only=True)]


def number(cell: Any) -> float | None:
    """A cell as a number: commas and spaces dropped, a dash or a blank is None."""
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).strip().replace(",", "").replace(" ", "")
    if text in ("", "-", "–", "—", ".."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def sex_ratio(male: float, female: float) -> float:
    return round(100.0 * male / female, 1)


def median_from_single_years(ages: dict[int, float]) -> float | None:
    """The median of a single-year distribution whose last key is the open top."""
    return single_year_median(Counter({age: n for age, n in ages.items() if n}))


def median_from_groups(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median of (low, high, people) groups, the last open-ended (high None)."""
    return grouped_median(groups)


def check(condition: bool, message: str) -> None:
    """A failed check stops the run: a mismatch is never smoothed over."""
    if not condition:
        raise SystemExit(message)


FIGURE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*(?:\.\d+)?|-)$")


def transcription(text: str, columns: tuple[str, ...], what: str,
                  adds_up: bool = True) -> dict[str, dict[str, float]]:
    """{line label: {column: figure}} from a table transcribed as "label | figures".

    For a table an office prints only as a picture, read off the rendered
    page: "-" is none, every line must have one figure per column, and with
    ``adds_up`` each line's figures after the first must make the first.
    """
    rows: dict[str, dict[str, float]] = {}
    for line in text.strip().splitlines():
        label, _, figures = (part.strip() for part in line.partition("|"))
        cells = figures.split()
        check(len(cells) == len(columns) and all(FIGURE.match(c) for c in cells),
              f"{what}: {label!r} has {len(cells)} figures for {len(columns)} columns")
        check(label not in rows, f"{what}: two lines {label!r}")
        row = dict(zip(columns, (0.0 if c == "-" else float(c.replace(",", "")) for c in cells)))
        if adds_up:
            parts = sum(list(row.values())[1:])
            check(abs(parts - row[columns[0]]) < 0.5,
                  f"{what}: {label!r} adds up to {parts:,.0f}, not {row[columns[0]]:,.0f}")
        rows[label] = row
    return rows


def close(a: float, b: float, slack: float = 0.0) -> bool:
    return abs(a - b) <= slack


def bind_level(rows: dict[str, tuple[str, str]], units: list[dict[str, Any]],
               parents: dict[str, str], aliases: dict[str, str] | None = None,
               ) -> dict[str, dict[str, Any]]:
    """{row key: unit}, every unit and every row bound exactly once.

    ``rows`` is {key: (name, the parent's name as the map spells it)};
    ``parents`` the map's admin1 id -> name. A row or a polygon left over
    stops the run, naming both sides.
    """
    bound, missing = bind(rows, units, parents, aliases or {})
    by_id = {u["id"]: u for u in units}
    left = [u["name"] for u in units if u["id"] not in set(bound.values())]
    if missing or left:
        raise SystemExit(f"binding left rows {missing} and polygons {left} unbound")
    return {key: by_id[sid] for key, sid in bound.items()}


def unit_record(iso3: str, key: str, name: str, unit: dict[str, Any], level: str,
                parent_name: str | None, sources: list[dict[str, Any]],
                **fields: Any) -> dict[str, Any]:
    """A record bound to the polygon it describes, by shape id."""
    return record(f"{iso3}-CENSUS-{fold(key)}", name, level=level, parent=iso3, country=iso3,
                  parent_name=parent_name, match_by="shape_id", shape_id=unit["id"],
                  sources=sources, **{k: v for k, v in fields.items() if v is not None})


def shares_of(counts: dict[str, float], total: float) -> list[dict[str, Any]]:
    """Each group's share of ``total``, largest first; zero groups dropped."""
    rows = [{"group": k, "pct": round(100.0 * v / total, 1), "count": int(round(v))}
            for k, v in counts.items() if v and v > 0]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows


def not_collected(note: str) -> dict[str, Any]:
    return gap(NOT_COLLECTED, note)


def population(value: float, year: int, source: str) -> dict[str, Any]:
    return measure(int(round(value)), year=year, source=source)


def summarise(records: Iterable[dict[str, Any]]) -> str:
    counts: Counter = Counter()
    for rec in records:
        for field in ("population", "median_age", "sex_ratio", "religion", "language",
                      "ethnicity"):
            value = rec.get(field)
            if isinstance(value, list) or (isinstance(value, dict) and "value" in value):
                counts[(rec["level"], field)] += 1
    return ", ".join(f"{lvl} {f} {n}" for (lvl, f), n in sorted(counts.items()))
