"""What the Balkan census readers share: PxWeb queries, ages, names, shapes.

Every reader in this family does the same four things -- asks an office for a
table, turns counts by age and sex into a median and a sex ratio, puts the
office's units on the map's polygons one-to-one, and checks that the parts add
up to the whole -- and each of those is written once, here.

Median age is interpolated within the single year that holds the middle
person (``redatam.median_age``), or, where an office publishes nothing finer,
within the five-year group that holds it (``grouped_median``); the note of
every record says which. Sex ratio is males per 1,000 females, the unit the
map carries everywhere else.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from typing import Any, Iterable

from ._shared import log, measure, read_json
from .pxweb import unstack
from .redatam import median_age

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import USER_AGENT, shard_path  # noqa: E402

__all__ = ["px_meta", "px_table", "median_age", "grouped_median", "sex_ratio",
           "age_fields", "fold", "shapes", "match_names", "unstack", "check_sum"]


# ---------------------------------------------------------------------------
# PxWeb
# ---------------------------------------------------------------------------

def _request(url: str, payload: dict | None = None, timeout: int = 180) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    last: Exception | None = None
    for wait in (3, 10, 30, 60, None):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8-sig", "replace"))
        except urllib.error.HTTPError as exc:
            # 429 is PxWeb's rate limit; anything else in the 400s is a wrong
            # query and asking again will not change it.
            if exc.code != 429 and exc.code < 500:
                body = exc.read()[:300].decode("utf-8", "replace")
                raise SystemExit(f"PxWeb {exc.code} for {url}: {body}")
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        if wait is None:
            break
        log(f"  retry in {wait}s: {url} ({last})")
        time.sleep(wait)
    raise SystemExit(f"PxWeb unreachable: {url} ({last})")


def px_meta(url: str) -> dict[str, dict[str, Any]]:
    """A table's variables by code: {code: {text, values, valueTexts}}."""
    meta = _request(url)
    return {v["code"]: v for v in meta.get("variables", [])}


def px_table(url: str, select: dict[str, list[str] | str]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    """POST a query and return its cells: [({var: (code, label)}, value)].

    ``select`` maps each variable code to a list of value codes, or to "*" for
    all of them. A variable left out is refused rather than let the server
    decide how to collapse it.
    """
    meta = px_meta(url)
    loose = [c for c in meta if c not in select and len(meta[c].get("values", [])) > 1]
    if loose:
        raise SystemExit(f"{url}: variables {loose} left unselected")
    query = []
    for code, values in select.items():
        if code not in meta:
            raise SystemExit(f"{url}: no variable {code!r}; present {sorted(meta)}")
        if values == "*":
            query.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
        else:
            query.append({"code": code, "selection": {"filter": "item", "values": list(values)}})
    payload = _request(url, {"query": query, "response": {"format": "json-stat2"}})
    return unstack(payload)


# ---------------------------------------------------------------------------
# Age and sex
# ---------------------------------------------------------------------------

def grouped_median(groups: Iterable[tuple[float, float | None, float]]) -> float | None:
    """The median age interpolated within the age group that holds it.

    ``groups`` is (lower bound, width, count), in order; the open top group
    has width None and must not hold the median.
    """
    groups = sorted(groups)
    total = sum(n for _, _, n in groups)
    if total <= 0:
        return None
    half, cum = total / 2, 0.0
    for lower, width, n in groups:
        if n > 0 and cum + n >= half:
            if width is None:
                raise SystemExit("the median falls in the open top age group")
            return round(lower + width * (half - cum) / n, 1)
        cum += n
    return None


def sex_ratio(men: float, women: float, *, year: int, source: str) -> dict[str, Any] | None:
    if not women:
        return None
    return measure(round(1000 * men / women), unit="males_per_1000_females",
                   year=year, source=source)


def age_fields(ages: Counter | None, men: float, women: float, *, year: int, source: str,
               note: str, grouped: list[tuple[float, float | None, float]] | None = None
               ) -> dict[str, Any]:
    """median_age, its note, and sex_ratio for one unit."""
    if ages is not None:
        median = median_age(ages)
    else:
        median = grouped_median(grouped or [])
    out: dict[str, Any] = {}
    if median is not None:
        out["median_age"] = measure(median, unit="years", year=year, source=source)
        out["median_age_note"] = note
    ratio = sex_ratio(men, women, year=year, source=source)
    if ratio:
        out["sex_ratio"] = ratio
    return out


# ---------------------------------------------------------------------------
# Names and shapes
# ---------------------------------------------------------------------------

def fold(name: Any) -> str:
    """Lower case, no diacritics, letters and digits only."""
    text = unicodedata.normalize("NFKD", str(name or "").replace("ł", "l").replace("đ", "d")
                                 .replace("Đ", "D").replace("ı", "i"))
    return "".join(c for c in text.lower() if c.isalnum() and not unicodedata.combining(c))


def shapes(iso3: str, level: str) -> list[dict[str, Any]]:
    """The map's polygons for one country and level, as the site draws them."""
    units = read_json(shard_path(level, iso3), [])
    if not units:
        raise SystemExit(f"no {level} shapes for {iso3} at {shard_path(level, iso3)}")
    return units


def match_names(units: dict[str, str], polygons: list[dict[str, Any]], *,
                strip: Iterable[str] = (), aliases: dict[str, str] | None = None,
                who: str) -> tuple[dict[str, str], list[str], list[str]]:
    """{unit code: shape id}, one-to-one, by folded name.

    ``units`` is {code: the office's name}. ``strip`` are words removed from
    both sides before folding ("Municipality", "Općina"); ``aliases`` maps the
    office's name to the boundary file's where they differ by more than
    that. A name two shapes share is bound to neither; every unit and every
    shape left over is returned, so the caller reports both sides.
    """
    aliases = aliases or {}
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in strip) + r")\b", re.I) \
        if strip else None

    def key(name: str) -> str:
        text = pattern.sub(" ", name) if pattern else name
        return fold(text)

    by_key: dict[str, list[str]] = {}
    for poly in polygons:
        by_key.setdefault(key(poly["name"]), []).append(poly["id"])
    bound: dict[str, str] = {}
    used: set[str] = set()
    for code, name in units.items():
        target = key(aliases.get(name, name))
        hits = [sid for sid in by_key.get(target, []) if sid not in used]
        if len(by_key.get(target, [])) == 1 and hits:
            bound[code] = hits[0]
            used.add(hits[0])
    left_units = [f"{units[c]} ({c})" for c in units if c not in bound]
    left_shapes = [p["name"] for p in polygons if p["id"] not in used]
    log(f"  {who}: {len(bound)} bound; units left {len(left_units)}: {left_units[:20]}; "
        f"shapes left {len(left_shapes)}: {left_shapes[:20]}")
    return bound, left_units, left_shapes


def check_sum(parts: float, whole: float, what: str, tolerance: float = 0.0) -> None:
    """Refuse a sum that is not its whole."""
    if abs(parts - whole) > max(tolerance * abs(whole), 0.5):
        raise SystemExit(f"{what}: the parts add to {parts:,.0f} against {whole:,.0f}")
