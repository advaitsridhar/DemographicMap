"""Uzbekistan's regions and districts: population, median age and sex ratio from SIAT.

The agency's open-data portal (siat.stat.uz) publishes indicator 2.01.02.0001,
the permanent population at the start of each year from 2010, for every
region, city and district, keyed by SOATO code, under CC BY 4.0. OCHA's
population table for Uzbekistan names the districts and carries no figure,
and Wikidata has none for most of them, so 163 of the map's 198 were blank.

**Names.** The agency writes "Balykchi district" and "Jalаquduk district" (with
a Cyrillic а); the boundary file writes "Balikchi" and "Djalalkuduk". Each unit
is matched to a shape inside its own region on a key that folds the
romanisations together (kh/x/h, dzh/dj/j, q/k, doubled letters, vowels), and
only where exactly one shape answers; a handful the key cannot reach --
renamings, mostly -- are declared.

**Units the boundary file does not draw.** Uzbekistan has made new districts
and cities since the boundary file was drawn, and the ground of each is still
inside an older shape: Kukdala was carved out of Chirakchi in 2023, so the
agency's 2026 figure for Chirakchi is short by Kukdala's 200,000 people. The
agency's own series says where each came from -- the year a unit first
appears, the unit it came out of loses about that many people -- and that is
read rather than assumed:

  * one district lost at least 60% of the new unit's first figure and no
    other lost 5%: the old shape is the two together, and says so;
  * several did: none of them is the shape the boundary file draws, and each
    is left a gap that says why;
  * a unit in the series from its start and not drawn (Shirin, a city of
    regional rank) is placed by declaration, measured against the shapes.

**Median age and sex ratio.** The same portal publishes the permanent
population by sex in fourteen age groups (indicators 2.01.02.0022 to 0049:
0-2, 3-5, 6-7, 8-15, 16-17, 18-19, five-year groups to 39, ten-year groups to
59, 60-64 and 65 and over) for every region and district, in persons. The
groups are the agency's own -- school and working-age bands, not five-year
ones -- and nothing finer is published below the country, so the median is
interpolated within the group that holds the middle person (always one of
the five-year groups between 20 and 39 here) and the note says so. The sex
ratio is men per hundred women from the same counts. A unit the boundary file
draws as two of the agency's units takes the two added together, group by
group, exactly as its population does; a unit left blank for its population
is left blank for these too. Checks: each unit's groups must add up to its
population in indicator 2.01.02.0001 (published in thousands, so within a
rounding allowance), every district's counts to its region's, and the regions'
to the country's.

Usage:
    python -m scripts.fetch_census.uzbekistan_siat --dump   # save the JSON
    python -m scripts.fetch_census.uzbekistan_siat
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, read_json, record, write_json
from .cod_ps_age import grouped_median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import NOT_AVAILABLE, as_drawn, gap, measure, slugify  # noqa: E402,F401
from common import shard_name  # noqa: E402

INDICATOR = 246
CODE = "2.01.02.0001"
POINTER = f"https://api.siat.stat.uz/sdmx/{INDICATOR}/table/download/?download_format=json"
PAGE = f"https://siat.stat.uz/data/{INDICATOR}/?lang=en"
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "uzbekistan" / f"siat_{INDICATOR}.json"
SITE = ROOT / "site" / "data"
OUT = PROCESSED / "uzbekistan_siat.json"
LICENCE = "CC BY 4.0"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
           "Accept": "application/json"}
TIMEOUT = 120
# The portal answers 429 to a reader that asks for twenty-eight tables in a
# row; it is asked again after a pause, the pause doubling each time.
PAUSE = 2.0
RETRIES = 6

# Permanent population by sex and age group, in persons: (first age, last
# age or None for the open group, the women's indicator, the men's). The
# codes run 2.01.02.0022-0035 for women and 0036-0049 for men, in this order.
AGE_GROUPS: tuple[tuple[int, int | None, int, int], ...] = (
    (0, 2, 3132, 3146), (3, 5, 3133, 3147), (6, 7, 3134, 3148), (8, 15, 3135, 3149),
    (16, 17, 3136, 3150), (18, 19, 3137, 3151), (20, 24, 3138, 3152),
    (25, 29, 3139, 3153), (30, 34, 3140, 3154), (35, 39, 3141, 3155),
    (40, 49, 3142, 3156), (50, 59, 3143, 3157), (60, 64, 3144, 3158),
    (65, None, 3145, 3159),
)
AGE_PAGE = "https://siat.stat.uz/data/{indicator}/?lang=en"
# The population table is published in thousands to one decimal: a unit's
# age groups may differ from it by the rounding of that figure and no more.
ROUNDING = 60

# The agency's region names to the map's first level.
REGION = {
    "Andijan region": "Andijan Region", "Bukhara region": "Bukhara Region",
    "Fergana region": "Fergana Region", "Jizzakh region": "Jizzakh Region",
    "Namangan region": "Namangan Region", "Navoi region": "Navoiy Region",
    "Kashkadarya region": "Qashqadaryo Region",
    "Republic of Karakalpakstan": "Republic of Karakalpakstan",
    "Samarkand region": "Samarqand Region", "Syrdarya region": "Sirdaryo Region",
    "Surkhandarya region": "Surxondaryo Region", "Tashkent city": "Tashkent",
    "Tashkent region": "Tashkent Region", "Khorezm region": "Xorazm Region",
}
# The boundary file puts three of Tashkent city's districts in Tashkent
# Region; a city district is looked for there as well.
ALSO_IN = {"Tashkent": ("Tashkent Region",)}
# Where the folded key cannot reach: Bo'z district was renamed Bo'ston, and
# the boundary file spells four others its own way.
DECLARED = {
    "Bustan district": "Boz", "Jalаquduk district": "Djalalkuduk",
    "Qorovulbozor district": "Karaulbazar", "Jizzakh city": "Dzhizak city",
    "Piskent district": "Pskent", "Gurlan district": "Gurlen",
}
# Units in the series from its start that the boundary file does not draw,
# with the shapes whose ground may hold them. Shirin's coordinates (40.227 N,
# 69.134 E) fall inside the shape called Bekabad and 0.01 degrees from Khavas,
# on the border of two regions: which holds it cannot be told.
UNDRAWN = {"Shirin city": ("Khavas", "Bekabad")}
# How much of a new unit's first figure one district must have lost to be
# its only source, and how much any other may have lost for that to hold.
SOLE_SOURCE = 0.6
ALSO_SOURCE = 0.05

HOMOGLYPHS = str.maketrans("аеорсухкмтвАЕОРСУХКМТВ", "aeopcyxkmtbAEOPCYXKMTB")
FOLDS = (("dzh", "j"), ("dj", "j"), ("zh", "j"), ("kh", "h"), ("x", "h"), ("q", "k"),
         ("sh", "s"), ("ch", "c"), ("yo", "o"), ("yu", "u"), ("ya", "a"), ("y", "i"),
         ("w", "v"))


def key(name: str) -> str:
    """A name with its romanisation folded away, for matching inside one region."""
    text = unicodedata.normalize("NFKD", name.translate(HOMOGLYPHS))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\b(district|city|region|tumani|shahri|shahar)\b|city$", " ", text)
    text = re.sub(r"[‘’'`ʻʼ]", "", text)
    for a, b in FOLDS:
        text = text.replace(a, b)
    text = re.sub(r"[^a-z]", "", text)
    text = re.sub(r"(.)\1+", r"\1", text)
    return text.translate(str.maketrans("oue", "aai"))


def is_city(unit: dict[str, Any]) -> bool:
    return bool(re.search(r"city$|\bcity\b", unit["Klassifikator_en"].lower())
                or re.search(r"\bshahri?\b|\bshahar\b", unit["Klassifikator"]))


def get(url: str) -> bytes:
    import time
    import urllib.error
    pause = PAUSE
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                        timeout=TIMEOUT) as fh:
                return fh.read()
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == RETRIES - 1:
                raise
            log(f"    429 from the portal; asking again in {pause:.0f} s")
            time.sleep(pause)
            pause *= 2
    raise SystemExit(f"uzbekistan_siat: {url} kept answering 429")


def download(indicator: int = INDICATOR) -> bytes:
    """The data file an indicator's download link points to."""
    pointer_url = f"https://api.siat.stat.uz/sdmx/{indicator}/table/download/?download_format=json"
    pointer = json.loads(get(pointer_url))
    url = pointer.get("file") or pointer.get("file_2")
    log(f"  {pointer_url} -> {url} ({pointer.get('size')}, updated {pointer.get('updated_at')})")
    return get(url)


def age_tables() -> dict[int, list[dict[str, Any]]]:
    """The twenty-eight age-by-sex tables, by indicator id, read with pauses."""
    import time
    out: dict[int, list[dict[str, Any]]] = {}
    for _, _, women, men in AGE_GROUPS:
        for indicator in (women, men):
            out[indicator] = json.loads(download(indicator))[0]["data"]
            time.sleep(PAUSE)
    return out


def age_profiles(tables: dict[int, list[dict[str, Any]]]
                 ) -> tuple[str, dict[str, dict[str, list[tuple[int, int | None, float]]]]]:
    """(year, {SOATO code: {"men": groups, "women": groups}}) for the newest
    year every table carries; a unit missing from any table is left out."""
    common = None
    for rows in tables.values():
        span = set(years(rows))
        common = span if common is None else common & span
    if not common:
        raise SystemExit("uzbekistan_siat: the age tables share no year")
    year = max(common)
    out: dict[str, dict[str, list[tuple[int, int | None, float]]]] = {}
    codes = set.intersection(*({r["Code"] for r in rows} for rows in tables.values()))
    by_code = {ident: {r["Code"]: r for r in rows} for ident, rows in tables.items()}
    for code in codes:
        sexes: dict[str, list[tuple[int, int | None, float]]] = {"men": [], "women": []}
        for low, high, women, men in AGE_GROUPS:
            for sex, ident in (("women", women), ("men", men)):
                value = by_code[ident][code].get(year)
                if value is None:
                    break
                sexes[sex].append((low, high, float(value)))
        if all(len(groups) == len(AGE_GROUPS) for groups in sexes.values()):
            out[code] = sexes
    return year, out


def summed(profiles: list[dict[str, list[tuple[int, int | None, float]]]]
           ) -> dict[str, list[tuple[int, int | None, float]]]:
    """Several units' age groups added together, group by group."""
    out: dict[str, list[tuple[int, int | None, float]]] = {}
    for sex in ("men", "women"):
        groups = [list(g) for g in profiles[0][sex]]
        for other in profiles[1:]:
            for i, (_, _, n) in enumerate(other[sex]):
                groups[i][2] += n
        out[sex] = [tuple(g) for g in groups]  # type: ignore[misc]
    return out


def age_fields(profile: dict[str, list[tuple[int, int | None, float]]], year: str,
               population: float | None, label: str) -> dict[str, Any]:
    """Median age and sex ratio for one unit, checked against its population."""
    men = sum(n for _, _, n in profile["men"])
    women = sum(n for _, _, n in profile["women"])
    if not men or not women:
        raise SystemExit(f"uzbekistan_siat: {label} has no men or no women in {year}")
    if population is not None and abs(men + women - population) > max(ROUNDING, 0.003 * population):
        raise SystemExit(f"uzbekistan_siat: {label}'s age groups add up to {men + women:,.0f} "
                         f"against its population of {population:,.0f} in {year}")
    groups = [(lo, hi, m + w) for (lo, hi, m), (_, _, w) in zip(profile["men"], profile["women"])]
    median = grouped_median(groups)
    if median is None:
        raise SystemExit(f"uzbekistan_siat: {label}'s middle person is in the open age group")
    source = (f"Statistics Agency of Uzbekistan, SIAT indicators 2.01.02.0022-0049, "
              f"permanent population by sex and age group on 1 January {year}")
    band = next(f"{lo}-{hi}" for lo, hi, _ in groups
                if hi is not None and lo <= median < hi + 1)
    return {
        "median_age": measure(median, unit="years", year=int(year), source=source),
        "median_age_note": (
            f"Interpolated within the agency's {band} age group, which holds the middle "
            f"person, from the permanent population in fourteen age groups (0-2, 3-5, 6-7, "
            f"8-15, 16-17, 18-19, 20-24 ... 35-39, 40-49, 50-59, 60-64, 65+), the finest "
            f"the agency publishes below the country. {men + women:,.0f} people."),
        "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                             year=int(year), source=source),
        "sex_ratio_note": f"{men:,.0f} men and {women:,.0f} women, permanent population.",
        "_age_source": source,
    }


def years(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(k for k in rows[0] if re.fullmatch(r"\d{4}", k))


def first_year(unit: dict[str, Any], span: list[str]) -> str | None:
    return next((y for y in span if unit.get(y)), None)


def shapes() -> dict[str, list[dict[str, Any]]]:
    """The map's second-level shapes in Uzbekistan, by the name of their region."""
    # The boundary file's own labels (common.as_drawn): a polygon this reader
    # binds by id is renamed by the build after the row bound to it, and the
    # next run must still find it under the label it was matched on.
    parents = {e["id"]: e["name"]
               for e in as_drawn(read_json(SITE / "admin1" / shard_name("UZB"), []))}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in as_drawn(read_json(SITE / "admin2" / shard_name("UZB"), [])):
        out[parents.get(entity.get("parent"), "")].append(entity)
    return out


def region_shapes() -> dict[str, str]:
    """The map's first-level shape ids in Uzbekistan, by their drawn label."""
    return {e["name"]: e["id"]
            for e in as_drawn(read_json(SITE / "admin1" / shard_name("UZB"), []))}


def match(unit: dict[str, Any], region: str,
          by_region: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The shapes a unit could be, in its region (and where else it may be filed)."""
    pool = [e for r in (region, *ALSO_IN.get(region, ())) for e in by_region.get(r, [])]
    declared = DECLARED.get(unit["Klassifikator_en"])
    if declared:
        return [e for e in pool if e["name"] == declared]
    city = is_city(unit)
    names = {key(unit["Klassifikator_en"]), key(unit["Klassifikator"])}
    return [e for e in pool
            if key(e["name"]) in names and ("city" in e["name"].lower()) == city]


def sources_of(new: dict[str, Any], siblings: list[dict[str, Any]],
               span: list[str]) -> list[tuple[dict[str, Any], float]]:
    """The units a new one was carved from: what each lost the year it appeared."""
    year = first_year(new, span)
    before = span[span.index(year) - 1]
    out = []
    for other in siblings:
        if other is new or not other.get(before) or not other.get(year):
            continue
        lost = other[before] - other[year]
        if lost > ALSO_SOURCE * new[year]:
            out.append((other, lost))
    return out


def build(data: list[dict[str, Any]], by_region: dict[str, list[dict[str, Any]]],
          ages: tuple[str, dict[str, Any]] | None = None,
          region_ids: dict[str, str] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    """Records for the regions and the districts the map draws.

    ``ages`` is ``age_profiles``' answer, (year, {code: groups by sex}); with
    it, every record whose units all carry groups gets a median age and a sex
    ratio. ``region_ids`` binds the regions to their shapes by id.
    """
    span = years(data)
    latest = span[-1]
    region_of = {u["Code"]: u["Klassifikator_en"] for u in data if len(u["Code"]) == 4}
    units = [u for u in data if len(u["Code"]) > 4 and u.get(latest)]
    source = (f"Statistics Agency of Uzbekistan, SIAT indicator {CODE}, permanent "
              f"population on 1 January {latest}")
    cite = [{"field": "population", "name": source, "url": PAGE, "license": LICENCE}]
    notes: list[str] = []

    # Every unit to the shape it is, where exactly one answers.
    placed: dict[str, dict[str, Any]] = {}
    claims: dict[str, list[str]] = defaultdict(list)
    for unit in units:
        region = REGION[region_of[unit["Code"][:4]]]
        found = match(unit, region, by_region)
        if len(found) == 1:
            placed[unit["Code"]] = found[0]
            claims[found[0]["id"]].append(unit["Code"])
        unit["_region"] = region
    for shape_id, codes in claims.items():
        if len(codes) > 1:
            notes.append(f"{shape_id}: claimed by {codes}; none kept")
            for code in codes:
                placed.pop(code, None)

    # What the boundary file does not draw, and whose ground it is on.
    extra: dict[str, list[dict[str, Any]]] = defaultdict(list)   # shape id -> units
    refused: dict[str, str] = {}                                  # shape id -> why
    shape_of = {u["Code"]: s for u in units if (s := placed.get(u["Code"]))}
    for unit in units:
        if unit["Code"] in placed:
            continue
        name = unit["Klassifikator_en"]
        people = f"{unit[latest] * 1000:,.0f}"
        if name in UNDRAWN:
            for target in UNDRAWN[name]:
                for shape in (s for s in shape_of.values() if s["name"] == target):
                    refused[shape["id"]] = (
                        f"{name} ({people} people), which the agency counts on its own "
                        f"and the boundary file does not draw, lies on the border of "
                        f"{' and '.join(UNDRAWN[name])}; which of them holds its ground "
                        f"cannot be told, so neither takes the agency's figure.")
            continue
        year = first_year(unit, span)
        if year == span[0]:
            notes.append(f"{name}: not drawn and in the series from its start; "
                         f"no shape takes it")
            continue
        siblings = [u for u in units if u["Code"][:4] == unit["Code"][:4]]
        found = sources_of(unit, siblings, span)
        drawn = [(u, lost) for u, lost in found if u["Code"] in placed]
        if (len(found) == 1 and drawn
                and found[0][1] >= SOLE_SOURCE * unit[year]):
            extra[placed[drawn[0][0]["Code"]]["id"]].append(unit)
            notes.append(f"{name}: carved from {drawn[0][0]['Klassifikator_en']} in {year}")
            continue
        for source_unit, _ in drawn:
            refused[placed[source_unit["Code"]]["id"]] = (
                f"Part of this district became {name} in {year}, which the boundary "
                f"file does not draw, together with part of "
                + ", ".join(u["Klassifikator_en"] for u, _ in found
                            if u is not source_unit)
                + "; how much came from each is not published, so the agency's "
                  "figure is left out.")
        notes.append(f"{name}: carved from {[u['Klassifikator_en'] for u, _ in found]} "
                     f"in {year}; those shapes left blank")

    age_year, profiles = ages if ages else ("", {})

    def with_ages(fields: dict[str, Any], parts: list[dict[str, Any]], label: str,
                  population: float | None) -> dict[str, Any]:
        """The unit's median age and sex ratio, where every part has its groups."""
        found = [profiles.get(p["Code"]) for p in parts]
        if not profiles or any(f is None for f in found):
            return fields
        extra_fields = age_fields(summed(found), age_year, population, label)
        age_source = extra_fields.pop("_age_source")
        if len(parts) > 1:
            extra_fields["median_age_note"] += (
                " The boundary file draws this district before "
                + " and ".join(p["Klassifikator_en"] for p in parts[1:])
                + " was carved out of it, so its groups are added in.")
        fields.update(extra_fields)
        fields["sources"] = [*fields.get("sources", []),
                             {"field": "median_age/sex_ratio", "name": age_source,
                              "url": AGE_PAGE.format(indicator=AGE_GROUPS[0][2]),
                              "license": LICENCE}]
        return fields

    region_ids = region_ids or {}
    rows: list[dict[str, Any]] = []
    for code, region in region_of.items():
        if region not in REGION:
            continue
        unit = next(u for u in data if u["Code"] == code)
        fields = with_ages({"sources": list(cite)}, [unit], region,
                           round(unit[latest] * 1000) if age_year == latest else None)
        shape_id = region_ids.get(REGION[region])
        rows.append(record(f"UZB-SIAT-{code}", REGION[region], level="admin1",
                           parent="UZB", country="UZB",
                           aliases=[region, unit["Klassifikator"]],
                           match_by="shape_id" if shape_id else None, shape_id=shape_id,
                           population=measure(round(unit[latest] * 1000), year=int(latest),
                                              source=source),
                           **fields))
    parents = {e["id"]: r for r, es in by_region.items() for e in es}
    for unit in units:
        shape = placed.get(unit["Code"])
        if shape is None:
            continue
        parts = [unit, *extra.get(shape["id"], [])]
        why = refused.get(shape["id"])
        if why:
            population = gap(NOT_AVAILABLE, why)
            fields: dict[str, Any] = {"sources": [], "median_age": gap(NOT_AVAILABLE, why),
                                      "sex_ratio": gap(NOT_AVAILABLE, why)}
        else:
            value = round(sum(p[latest] for p in parts) * 1000)
            population = measure(value, year=int(latest), source=source)
            if len(parts) > 1:
                population["note"] = (
                    f"The boundary file draws this district as it was before "
                    + " and ".join(f"{p['Klassifikator_en']} ({p[latest] * 1000:,.0f})"
                                   for p in parts[1:])
                    + " was carved out of it; the figure is the two together, from "
                      "the same table and year.")
            fields = with_ages({"sources": list(cite)}, parts, shape["name"],
                               value if age_year == latest else None)
        rows.append(record(f"UZB-SIAT-{unit['Code']}", shape["name"], level="admin2",
                           parent="UZB", country="UZB", parent_name=parents[shape["id"]],
                           aliases=[unit["Klassifikator_en"], unit["Klassifikator"]],
                           match_by="shape_id", shape_id=shape["id"],
                           population=population, **fields))
    if profiles:
        check_sums(rows, region_of, data, profiles, age_year)
    return rows, notes


def check_sums(rows: list[dict[str, Any]], region_of: dict[str, str],
               data: list[dict[str, Any]], profiles: dict[str, Any], year: str) -> None:
    """Every region's districts add up to it, and the regions to the country."""
    def people(code: str) -> float:
        p = profiles[code]
        return sum(n for sex in ("men", "women") for _, _, n in p[sex])

    country = next((c for c, name in region_of.items() if name not in REGION), None)
    regions = [c for c, name in region_of.items() if name in REGION]
    for code in regions:
        if code not in profiles:
            continue
        inside = [u["Code"] for u in data if len(u["Code"]) > 4 and u["Code"][:4] == code
                  and u["Code"] in profiles]
        total = sum(people(c) for c in inside)
        if inside and abs(total - people(code)) > max(ROUNDING, 0.002 * people(code)):
            raise SystemExit(f"uzbekistan_siat: {region_of[code]}'s districts' age groups add "
                             f"up to {total:,.0f} against the region's {people(code):,.0f} "
                             f"in {year}")
    if country and country in profiles:
        total = sum(people(c) for c in regions if c in profiles)
        if abs(total - people(country)) > max(ROUNDING, 0.001 * people(country)):
            raise SystemExit(f"uzbekistan_siat: the regions' age groups add up to {total:,.0f} "
                             f"against the country's {people(country):,.0f} in {year}")
    log(f"  age groups checked: districts against regions, regions against the country "
        f"({year})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true", help="save the agency's JSON and stop")
    ap.add_argument("--offline", action="store_true", help="read the saved JSON")
    ap.add_argument("--no-ages", action="store_true",
                    help="population only: do not read the age-by-sex tables")
    args = ap.parse_args()
    blob = DUMP.read_bytes() if args.offline else download()
    if args.dump:
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        DUMP.write_bytes(blob)
        log(f"  wrote {DUMP.relative_to(ROOT)}")
        return 0
    data = json.loads(blob)[0]["data"]
    ages = None
    if not (args.offline or args.no_ages):
        year, profiles = age_profiles(age_tables())
        log(f"  age groups by sex for {len(profiles)} units, 1 January {year}")
        if year != years(data)[-1]:
            log(f"  note: the age tables' newest year is {year}, the population "
                f"table's {years(data)[-1]}; units are checked against neither")
        ages = (year, profiles)
    rows, notes = build(data, shapes(), ages=ages, region_ids=region_shapes())
    for line in notes:
        log(f"  {line}")
    districts = [r for r in rows if r["level"] == "admin2"]
    filled = sum(1 for r in districts if "value" in r["population"])
    aged = sum(1 for r in rows if "value" in (r.get("median_age") or {}))
    log(f"  {len(rows) - len(districts)} regions, {len(districts)} districts "
        f"({filled} with a figure, {len(districts) - filled} left blank with the reason); "
        f"{aged} with a median age and sex ratio")
    for r in rows:
        if "value" in (r.get("median_age") or {}):
            log(f"    {r['level']} {r['name']}: median {r['median_age']['value']}, "
                f"ratio {r['sex_ratio']['value']}")
    write_json(OUT, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
