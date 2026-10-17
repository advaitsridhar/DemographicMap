"""Helpers shared by the Southern Africa and Indian Ocean census readers.

Each reader in this region does the same few things: fetches a statistics
office's file, from the office or from the Internet Archive's copy of it where
the office refuses the runner; reduces names to a key that survives the
offices' spellings; takes a median age from grouped counts; and writes a sex
ratio as men per thousand women. They live here so that every reader does
them the same way.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from ._shared import PROCESSED, http_get, log, measure

SITE = PROCESSED.parent.parent / "site" / "data"
ARCHIVE = "https://web.archive.org/web/{stamp}id_/{url}"


def fetch(url: str, *, archive: Iterable[str] = (), office: bool = True,
          timeout: int = 300, expect: bytes | tuple[bytes, ...] | None = None) -> tuple[bytes, str]:
    """(body, the address it came from): the office's own copy first (unless
    ``office`` is False, for a host known to refuse the runner), then the
    Internet Archive's raw (``id_``) copy at each timestamp of ``archive`` in
    turn. ``expect`` is the start a good body must have (``%PDF``, ``PK``), so
    an error page served with a 200 is not taken for the file."""
    tries: list[str] = [url] if office else []
    tries += [ARCHIVE.format(stamp=s, url=url) for s in archive]
    last: Exception | None = None
    for target in tries:
        try:
            body = http_get(target, binary=True, cache=False, timeout=timeout, retries=2)
        except Exception as exc:                    # noqa: BLE001 -- the next route
            log(f"    {target}: {type(exc).__name__}: {str(exc)[:160]}")
            last = exc
            continue
        assert isinstance(body, bytes)
        if expect and not body.startswith(expect):
            log(f"    {target}: not the file ({body[:60]!r})")
            last = ValueError(f"{target} is not the file")
            continue
        return body, target
    raise SystemExit(f"could not fetch {url}: {last}")


def key(name: Any) -> str:
    """A name reduced to its letters and digits, accents and case dropped."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def grouped_median(groups: Iterable[tuple[float, float | None, float]]) -> float | None:
    """The median age interpolated within the age group that holds it.

    ``groups`` is (lower bound, width in years, people); the open top group
    has width None and may not hold the median. None if nobody is counted.
    """
    rows = sorted(groups, key=lambda g: g[0])
    total = sum(n for _, _, n in rows)
    if total <= 0:
        return None
    half, before = total / 2, 0.0
    for lower, width, n in rows:
        if n > 0 and before + n >= half:
            if width is None:
                raise SystemExit("the median falls in the open top age group")
            return round(lower + width * (half - before) / n, 1)
        before += n
    return None


def sex_ratio(men: float, women: float, *, year: int, source: str) -> dict[str, Any] | None:
    """Men per thousand women, whole."""
    if not men or not women:
        return None
    return measure(round(1000 * men / women), unit="males_per_1000_females",
                   year=year, source=source)


def units(iso3: str, level: str) -> list[dict[str, Any]]:
    """The polygons the map draws for a country at a level, under the boundary
    file's own labels where the build has renamed one."""
    path = SITE / level / f"{iso3}.units.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [{**u, "name": u["shape_name"]} if u.get("shape_name") else u for u in rows]


def joined(names: list[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
