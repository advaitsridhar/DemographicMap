"""What the central European age-and-sex readers share.

Austria, Switzerland, Liechtenstein, Poland, Czechia, Slovakia, Hungary,
Slovenia, the Netherlands and Luxembourg each publish their population by age
and sex for the units this map draws, each in its own table. Everything after
the table is the same job and lives here, so that every reader does it the
same way and is checked the same way:

* the median age, interpolated within the single year of age that holds the
  middle person (``redatam.median_age``), or within a five-year group where
  that is all the office publishes, which the note then says;
* the sex ratio, as males per 100 females to one decimal;
* the checks: males and females make the total, units make their parent and
  the country, and the country's median recomputed from the same counts lands
  within 0.3 years of the one Eurostat publishes from the office's figures.
  A miss stops the run; nothing is smoothed.

Binding is by the map's own shape ids (``site/data/<level>/<ISO>.units.json``),
which each reader resolves by name and, where the boundary file's spelling
defeats that, by a declared alias it can be checked against.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from typing import Any, Iterable

from ._shared import log, measure
from .redatam import median_age
from common import ROOT, as_drawn  # noqa: E402  (_shared puts scripts/ on the path)

SITE = ROOT / "site" / "data"
SEX_RATIO_UNIT = "males_per_100_females"
# Eurostat's national median from the office's figures, for the check.
EUROSTAT = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
            "demo_pjanind?format=JSON&lang=EN&indic_de=MEDAGEPOP&geo={geo}")
EUROSTAT_POPULATION = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
                       "demo_pjan?format=JSON&lang=EN&sex=T&age=TOTAL&geo={geo}&time={year}")


def units(iso3: str, level: str) -> list[dict[str, Any]]:
    """The map's units at one level, under the boundary file's own labels."""
    return as_drawn(json.loads((SITE / level / f"{iso3}.units.json").read_text()))


def fold(name: str) -> str:
    """Lower case, no accents, letters and digits only."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    return "".join(c for c in text.lower() if c.isalnum() and not unicodedata.combining(c))


def median_of_groups(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median from (first year, last year or None for open, count) groups.

    Linear within the group that holds the middle person, which is the only
    assumption a five-year table allows. An open top group can hold the median
    only in a population with half its people over 85, which no unit here has;
    it stops the run rather than inventing a width.
    """
    total = sum(n for _, _, n in groups)
    if total <= 0:
        return None
    half, cum = total / 2, 0.0
    for first, last, n in sorted(groups, key=lambda g: g[0]):
        if n > 0 and cum + n >= half:
            if last is None:
                raise SystemExit(f"median falls in the open group {first}+")
            width = last - first + 1
            return round(first + width * (half - cum) / n, 1)
        cum += n
    return None


def sex_ratio(males: float, females: float) -> float | None:
    return round(100.0 * males / females, 1) if females else None


def age_sex_fields(males: Counter, females: Counter, *, year: int, source: str,
                   median_note: str, ratio_note: str | None = None,
                   median: float | None = None, groups: bool = False,
                   total: float | None = None) -> dict[str, Any]:
    """population, median_age and sex_ratio for one unit from its counts.

    ``males``/``females`` are {age: count}; with ``groups`` they are
    {(first, last or None): count} and the median is read from the groups.
    ``median`` is the office's own figure, used as given when it has one for
    exactly this unit. ``total`` is the office's own total, which the sexes
    must make.
    """
    m, f = sum(males.values()), sum(females.values())
    if total is not None and abs(m + f - total) > max(2, 0.0005 * total):
        raise SystemExit(f"males {m:,.0f} + females {f:,.0f} = {m + f:,.0f}, not the "
                         f"published total {total:,.0f}")
    if median is None:
        both = Counter(males)
        both.update(females)
        if groups:
            median = median_of_groups([(a, b, n) for (a, b), n in both.items()])
        else:
            median = median_age(both)
    out: dict[str, Any] = {
        "population": measure(int(round(m + f)), year=year, source=source),
        "median_age": measure(median, unit="years", year=year, source=source),
        "median_age_note": median_note,
        "sex_ratio": measure(sex_ratio(m, f), unit=SEX_RATIO_UNIT, year=year, source=source),
    }
    if ratio_note:
        out["sex_ratio_note"] = ratio_note
    return out


def add(into: dict[Any, Counter], key: Any, counts: Counter) -> None:
    into.setdefault(key, Counter()).update(counts)


def check_sum(parts: Iterable[float], whole: float, what: str, tolerance: float = 0.0) -> None:
    summed = sum(parts)
    if abs(summed - whole) > max(tolerance * whole, 0.5):
        raise SystemExit(f"{what}: the parts sum to {summed:,.0f}, the whole is {whole:,.0f} "
                         f"({summed - whole:+,.0f})")
    log(f"  {what}: parts sum to {summed:,.0f} = {whole:,.0f}")


def eurostat_median(geo: str, year: int) -> float | None:
    """Eurostat's published median age of a country on 1 January ``year``."""
    return _eurostat_value(EUROSTAT.format(geo=geo) + f"&time={year}", f"median for {geo} {year}")


def eurostat_population(geo: str, year: int) -> float | None:
    """Eurostat's published population of a country on 1 January ``year`` (demo_pjan)."""
    return _eurostat_value(EUROSTAT_POPULATION.format(geo=geo, year=year), f"population for {geo} {year}")


def _eurostat_value(url: str, what: str) -> float | None:
    from .eurostat import unpack
    from ._shared import http_json
    try:
        payload = http_json(url, timeout=120)
    except Exception as exc:  # noqa: BLE001 - reported, then the check is skipped by name
        log(f"  Eurostat {what} unavailable ({exc.__class__.__name__})")
        return None
    values = list(unpack(payload).values())
    return values[0] if values else None


def check_national_median(ages: Counter, geo: str, year: int, *, groups: bool = False,
                          tolerance: float = 0.3) -> float | None:
    """The country's median from the same counts, against Eurostat's."""
    mine = (median_of_groups([(a, b, n) for (a, b), n in ages.items()]) if groups
            else median_age(ages))
    theirs = eurostat_median(geo, year)
    if theirs is None:
        # Eurostat has not published this date yet. The year before is the
        # nearest published figure; a population ages by a few tenths of a
        # year in a year, so the check widens by that much and says so.
        earlier = eurostat_median(geo, year - 1)
        if earlier is None:
            log(f"  national median {mine} ({year}); no published figure to check against")
            return mine
        if abs(mine - earlier) > tolerance + 0.4:
            raise SystemExit(f"national median recomputed as {mine} for 1 January {year}; "
                             f"Eurostat's for {year - 1} is {earlier}, too far for a year's ageing")
        log(f"  national median {mine} (1 January {year}) against Eurostat's {earlier} a year "
            f"earlier ({geo}); {year} is not published yet")
        return mine
    if abs(mine - theirs) > tolerance:
        raise SystemExit(f"national median recomputed as {mine}, Eurostat publishes {theirs} "
                         f"for {geo} on 1 January {year}: more than {tolerance} apart")
    log(f"  national median {mine} against Eurostat's {theirs} ({geo}, 1 January {year})")
    return mine


def report_unbound(what: str, office: Iterable[str], shapes: Iterable[str]) -> None:
    office, shapes = sorted(office), sorted(shapes)
    log(f"  {what}: {len(office)} office units unbound"
        + (": " + "; ".join(office) if office else ""))
    log(f"  {what}: {len(shapes)} polygons without an office unit"
        + (": " + "; ".join(shapes) if shapes else ""))
