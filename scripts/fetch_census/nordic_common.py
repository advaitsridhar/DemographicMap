"""What the Nordic and Baltic adapters share: the map's units, binding, age and sex.

Eight countries, five kinds of API, one job each: read the office's population
by single year of age and sex for the units the map draws, and bind each row to
exactly one polygon. The binding is where these go wrong silently, so it is
done once, here, with the same rules for all eight:

* a drawn polygon is bound by the office's name for it, folded (case,
  diacritics, punctuation) after the office's and the boundary file's generic
  words are taken off -- "kommune", "vald", "novads", "seutukunta";
* within the boundary file's parent where the office's grouping gives one, and
  by a name no other unit shares otherwise (``binding.bind``);
* one row to one polygon, and every row and polygon left over is reported.

A kommune drawn as several polygons -- Frogn's exclave in the Oslofjord,
Malvik's two islets -- is a special case of the last rule: the pieces carry the
same name and the same parent, so no name can choose between them. The largest
takes the unit's figures and the small ones are reported as pieces rather than
given a copy, because a copy would count the same people twice in anything
summed from the polygons.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

import time
import urllib.error
import urllib.request

from ._shared import PROCESSED, log, measure
from .binding import bind, fold
from .redatam import median_age

SITE = PROCESSED.parent.parent / "site" / "data"
USER_AGENT = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) python-urllib"


def request(url: str, payload: Any = None, *, accept: str = "application/json",
            timeout: int = 180, pause: float = 0.0) -> bytes:
    """GET, or POST ``payload`` as JSON; backs off on 429 and 5xx, fails fast on 4xx.

    Hagstofa and StatFin both answer 429 to a brisk pace, and a throttled
    request is not an answer about the data, so it is waited out rather than
    reported.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if data is not None:
        headers["Content-Type"] = "application/json"
    delay = 5.0
    for attempt in range(6):
        if pause:
            time.sleep(pause)
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 5:
                log(f"    HTTP {exc.code}; waiting {delay:.0f}s :: {url}")
                time.sleep(delay)
                delay *= 2
                continue
            body = exc.read()[:400].decode("utf-8", "replace")
            raise SystemExit(f"HTTP {exc.code} from {url}: {' '.join(body.split())}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt < 5:
                log(f"    {exc.__class__.__name__}; waiting {delay:.0f}s :: {url}")
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise SystemExit(f"gave up on {url}")


def request_json(url: str, payload: Any = None, **kwargs: Any) -> Any:
    return json.loads(request(url, payload, **kwargs).decode("utf-8-sig", "replace"))


def unplaced(field: str, labels: Iterable[str]) -> list[str]:
    """The labels the group tree cannot carry up to one of its top groupings."""
    import group_tree                       # scripts/ is on the path via _shared
    tops = group_tree.tier1_names(field)
    return sorted({label for label in labels
                   if group_tree.ancestry(field, label)[-1] not in tops})

# The brief's convention for this round: males per hundred females, to one
# decimal. Most of the map's older figures are per thousand; the unit travels
# with every value, so a reader is never left guessing which.
SEX_RATIO_UNIT = "males_per_100_females"


def sex_ratio(males: float, females: float) -> float | None:
    return round(100.0 * males / females, 1) if females else None


def load_units(iso3: str, level: str) -> list[dict[str, Any]]:
    return json.loads((SITE / level / f"{iso3}.units.json").read_text())


def parent_names(iso3: str) -> dict[str, str]:
    """The map's admin1 shape id -> its name."""
    return {u["id"]: u["name"] for u in load_units(iso3, "admin1")}


def _area(box: list[float] | None) -> float:
    if not box:
        return 0.0
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def split_pieces(shapes: list[dict[str, Any]], key=lambda s: s["name"],
                 ratio: float = 0.05) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Shapes, less the small pieces of a unit drawn as several polygons.

    Two polygons with one name under one parent are one unit when all but one
    are small beside the largest; each small one is set aside as a piece. Two
    of comparable size are left in, because that is two places with one name
    -- Nes in Akershus and Nes in Buskerud -- and binding must tell them apart.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for shape in shapes:
        groups[(fold(key(shape)), shape.get("parent") or "")].append(shape)
    kept, pieces = [], []
    for members in groups.values():
        if len(members) == 1:
            kept += members
            continue
        members = sorted(members, key=lambda s: -_area(s.get("bbox")))
        big = _area(members[0].get("bbox"))
        small = [s for s in members[1:] if _area(s.get("bbox")) < ratio * big]
        kept += [s for s in members if s not in small]
        pieces += small
    return kept, pieces


def bind_rows(iso3: str, level: str, rows: dict[str, tuple[str, str]],
              *, shape_name=lambda s: s["name"], aliases: dict[str, str] | None = None,
              shapes: list[dict[str, Any]] | None = None, pieces_ratio: float = 0.05,
              ) -> tuple[dict[str, str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Office rows -> the map's shape ids, one to one.

    ``rows`` is {code: (the office's name, a group name)}. The group is the
    boundary file's parent name when the office's grouping is the map's, and
    otherwise any label shared by the unit's neighbours (a former county):
    ``bind`` then uses it only to place a name several units share, by the
    box its already-bound neighbours make. ``shape_name`` gives the name a
    polygon is matched by (the boundary file's label with its suffixes off).

    Returns the binding, the rows left unbound, the polygons left unbound and
    the pieces set aside.
    """
    shapes = shapes if shapes is not None else load_units(iso3, level)
    kept, pieces = split_pieces(shapes, key=shape_name, ratio=pieces_ratio)
    parents = parent_names(iso3) if level == "admin2" else {}
    view = [{**s, "name": shape_name(s)} for s in kept]
    bound, missing = bind(rows, view, parents, aliases)
    # bind() never binds one polygon twice; say so rather than trust it.
    twice = [sid for sid, n in Counter(bound.values()).items() if n > 1]
    if twice:
        raise SystemExit(f"{iso3} {level}: polygons bound twice: {twice}")
    used = set(bound.values())
    left = [s for s in kept if s["id"] not in used]
    log(f"  {iso3} {level}: {len(bound)} of {len(rows)} office units bound to "
        f"{len(shapes)} polygons ({len(pieces)} set aside as pieces)")
    if missing:
        log(f"    office units with no polygon ({len(missing)}): " + "; ".join(missing))
    if left:
        log(f"    polygons with no office unit ({len(left)}): "
            + "; ".join(f"{s['name']} [{s['id']}]" for s in left))
    if pieces:
        log(f"    pieces left unbound ({len(pieces)}): "
            + "; ".join(f"{s['name']} [{s['id']}]" for s in pieces))
    return bound, missing, left, pieces


def strip_words(name: str, words: Iterable[str]) -> str:
    """``name`` without any of the generic ``words`` standing alone in it."""
    out = str(name)
    for word in words:
        out = re.sub(rf"(?i)(^|\s){re.escape(word)}(?=\s|$)", " ", out)
    return " ".join(out.split())


class AgeSex:
    """One unit's people by single year of age and sex."""

    def __init__(self) -> None:
        self.males: Counter = Counter()
        self.females: Counter = Counter()

    def add(self, age: int, sex: str, n: float) -> None:
        (self.males if sex == "m" else self.females)[age] += n

    def __iadd__(self, other: "AgeSex") -> "AgeSex":
        self.males.update(other.males)
        self.females.update(other.females)
        return self

    @property
    def men(self) -> float:
        return sum(self.males.values())

    @property
    def women(self) -> float:
        return sum(self.females.values())

    @property
    def total(self) -> float:
        return self.men + self.women

    def median(self) -> float | None:
        return median_age(self.males + self.females)

    def fields(self, *, year: int, source: str, url: str, date: str,
               population: bool = True, extra_note: str = "") -> dict[str, Any]:
        """population, median age and sex ratio, each with its note and source."""
        out: dict[str, Any] = {
            "median_age": measure(self.median(), unit="years", year=year, source=source),
            "median_age_note": (
                f"Interpolated within the single year of age that holds the middle person, "
                f"from {source}'s count of residents by single year of age on {date}; "
                f"the office tabulates the ages, not this median.{extra_note}"),
            "sex_ratio": measure(sex_ratio(self.men, self.women), unit=SEX_RATIO_UNIT,
                                 year=year, source=source),
            "sex_ratio_note": (f"Males per 100 females among residents on {date} "
                               f"({int(self.men):,} males, {int(self.women):,} females)."),
        }
        fields = ["median age", "sex ratio"]
        if population:
            out["population"] = measure(int(round(self.total)), year=year, source=source)
            out["population_note"] = f"Registered residents on {date}.{extra_note}"
            fields.insert(0, "population")
        out["sources"] = [{"field": "/".join(fields), "name": source, "url": url,
                           "year": year}]
        return out


def fold_small(counts: dict[str, float], total: float, other: str, floor: float = 0.0005,
               keep: Iterable[str] = ()) -> tuple[dict[str, float], int, float]:
    """Counts with the zero rows dropped and every group under ``floor`` of the
    total (0.05%, which rounds to 0.0%) counted in ``other``; returns the new
    counts, how many groups were folded and how many people they hold.

    A list of 160 languages each rounded to 0.0% sums to 99.3%, and a row that
    reads 0 says nothing a reader can use.
    """
    keep = set(keep) | {other}
    out: dict[str, float] = {}
    folded, people = 0, 0.0
    for label, n in counts.items():
        if not n or n <= 0:
            continue
        if label not in keep and total and n / total < floor:
            folded += 1
            people += n
            continue
        out[label] = out.get(label, 0.0) + n
    if people:
        out[other] = out.get(other, 0.0) + people
    return out, folded, people


EUROSTAT_MEDIAN = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
                   "demo_pjanind?format=JSON&lang=EN&geo={geo}&indic_de=MEDAGEPOP"
                   "&sinceTimePeriod={since}")
# The brief's bound on a national median recomputed from the single years
# against a published one.
MEDIAN_TOLERANCE = 0.3


def published_median(geo: str, year: int) -> tuple[float | None, str]:
    """Eurostat's median age for a country on 1 January ``year`` (demo_pjanind).

    Eurostat computes it from the national office's own count by single year
    of age, which is the table read here, so the two should agree to within
    the interpolation; none of the five Nordic offices publishes a national
    median of its own in the tables these adapters read. Returns the value, or
    None and why not.
    """
    try:
        body = request_json(EUROSTAT_MEDIAN.format(geo=geo, since=year - 2), timeout=60)
    except (SystemExit, Exception) as exc:              # a cross-check, not a source
        return None, f"Eurostat unreachable ({str(exc)[:120]})"
    index = body.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
    values = body.get("value", {})
    if str(year) not in index or str(index[str(year)]) not in values:
        return None, f"Eurostat has no median for {geo} on 1 January {year} yet " \
                     f"(latest: {max(index, default='none')})"
    return float(values[str(index[str(year)])]), "Eurostat demo_pjanind"


def check_national_median(geo: str, year: int, ours: float | None, what: str) -> None:
    """Stop if the recomputed national median is more than 0.3 years off Eurostat's.

    Where Eurostat has not yet published that 1 January, the year before is
    the nearest figure; a population ages by a few tenths of a year in a year,
    so the bound widens by 0.4 and the log says so.
    """
    if ours is None:
        log(f"  {what}: no national median to check")
        return
    theirs, why = published_median(geo, year)
    bound, when = MEDIAN_TOLERANCE, year
    if theirs is None:
        theirs, why2 = published_median(geo, year - 1)
        if theirs is None:
            log(f"  {what}: national median {ours}; nothing published to check it against "
                f"-- {why}; {why2}")
            return
        bound, when = MEDIAN_TOLERANCE + 0.4, year - 1
    log(f"  {what}: national median {ours} against Eurostat's {theirs} for 1 January {when} "
        f"({ours - theirs:+.2f} years, bound {bound})")
    if abs(ours - theirs) > bound:
        raise SystemExit(f"{what}: the national median recomputed from the single years, "
                         f"{ours}, is {ours - theirs:+.2f} years off Eurostat's {theirs} for "
                         f"1 January {when}")


def check_parts(parts: dict[str, float], whole: float, what: str,
                tolerance: float = 0.0005, slack: float = 2) -> None:
    """The parts must make the whole, within rounding; otherwise stop."""
    summed = sum(parts.values())
    if abs(summed - whole) > max(slack, tolerance * whole):
        raise SystemExit(f"{what}: {len(parts)} parts sum to {summed:,.0f} against a "
                         f"published {whole:,.0f} ({summed - whole:+,.0f})")
    log(f"    {what}: {len(parts)} parts sum to {summed:,.0f} against {whole:,.0f}")
