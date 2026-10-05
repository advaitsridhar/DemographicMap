#!/usr/bin/env python3
"""Kazakhstan: median age and sex ratio by region and district, 2021 census.

The 2021 National Population Census is the only source of single-year ages
below the region. The Bureau of National Statistics published its tables of
ethnic group, locality and age as one workbook on 28 November 2025:

* sheet 1.1 -- every region by single year of age (0 to 99, then 100+), sex
  and urban/rural;
* sheet 3.1 -- every locality by single year of age, both sexes, keyed by
  its KATO code: level 1 is the region, level 2 the district or city akimat.

Sex below the region is in the census's first results volume, *Population of
the Republic of Kazakhstan* (2023), table 2.2: men and women for every city
and district, 2009 and 2021. The volume is a PDF; each row's figures are
read from its text and must make themselves whole -- total = men + women and
the printed men per 1,000 women, for both censuses -- or the row is not
read. Every district of sheet 3.1 must then find exactly one row of table 2.2
in its region with its own 2021 total.

**Binding.** The census's districts and city akimats are placed on the drawn
polygons with the same rule as the Bureau's 2025 ethnicity workbook
(``kazakhstan.place``): by name, by a renaming the map still shows, or --
for the many units the twenty-year-old boundary file does not draw -- on the
drawn polygon that holds them (``kazakhstan.INSIDE``). A polygon holding
several units takes the median of their pooled single years and the ratio of
their summed men and women, which is exact. The 2021 layout has 17 regions:
Shymkent is pooled with Turkestan Region into the drawn South Kazakhstan.

**Checks.** Each locality's single years make its total; a region's
districts make the region; the regions make the country (19,186,015); sheet
1.1's regions agree with sheet 3.1's, and its men and women make both sexes;
table 2.2's region rows carry sheet 3.1's region totals.

Usage:
    python -m scripts.fetch_census.kazakhstan_census
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from . import kazakhstan as kz
from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .redatam import median_age

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ISO3 = "KAZ"
YEAR = 2021
OUT = "kazakhstan_census.json"
NATIONAL = 19_186_015
WORKBOOK_URL = (
    "https://stat.gov.kz/upload/medialibrary/93d/msehzbw870uc729ejpv5eynfszawxgep/"
    "%D0%A7%D0%B8%D1%81%D0%BB%D0%B5%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D1%8C%20%D0%BD%D0%B0"
    "%D1%81%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%A0%D0%B5%D1%81%D0%BF%D1%83%D0%B1"
    "%D0%BB%D0%B8%D0%BA%D0%B8%20%D0%9A%D0%B0%D0%B7%D0%B0%D1%85%D1%81%D1%82%D0%B0%D0%BD"
    "%20%D0%BF%D0%BE%20%D1%8D%D1%82%D0%BD%D0%BE%D1%81%D0%B0%D0%BC,%20%D0%BD%D0%B0%D1%81"
    "%D0%B5%D0%BB%D0%B5%D0%BD%D0%BD%D1%8B%D0%BC%20%D0%BF%D1%83%D0%BD%D0%BA%D1%82%D0%B0"
    "%D0%BC%20%D0%B8%20%D0%BF%D0%BE%20%D0%B2%D0%BE%D0%B7%D1%80%D0%B0%D1%81%D1%82%D0%B0"
    "%D0%BC%20(1).xlsx")
VOLUME_URL = ("https://stat.gov.kz/upload/medialibrary/75f/z2gxd3z3s8gsf7em4x4q5ahd87mgoc5m/"
              "%D0%9D%D0%B0%D1%81%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5%201%20%D1%82%D0%BE%D0%BC.pdf")
PAGE = "https://stat.gov.kz/ru/national/2021/"
WORKBOOK_SOURCE = ("Bureau of National Statistics of Kazakhstan, 2021 National Population "
                   "Census: population by ethnic group, locality and age (workbook of "
                   "28 November 2025), sheets 1.1 and 3.1")
VOLUME_SOURCE = ("Bureau of National Statistics of Kazakhstan, 2021 National Population "
                 "Census: Population of the Republic of Kazakhstan, volume 1 (2023), table 2.2")
LICENCE = "Official statistics of the Bureau of National Statistics; free to use with attribution"

# KATO's first two digits -> the drawn first-level region.
KATO_REGION = {
    "11": "Akmola Region", "15": "Aktobe Region", "19": "Almaty Region",
    "23": "Atyrau Region", "27": "West Kazakhstan Region", "31": "Jambyl Region",
    "35": "Karaganda Region", "39": "Kostanay Region", "43": "Kyzylorda Region",
    "47": "Mangystau Region", "55": "Pavlodar Region", "59": "North Kazakhstan Region",
    "61": "South Kazakhstan Region", "63": "East Kazakhstan Region",
    "71": "Astana", "75": "Almaty", "79": "South Kazakhstan Region",
}
# Cities of republican significance: one unit each, under the name the
# placement knows them by. Astana's polygon has no second level.
CITY_UNITS = {"75": "г.Алматы", "79": "г.Шымкент"}
# Sheet 1.1's region headings -> KATO prefix.
SHEET_REGIONS = {
    "акмолинская": "11", "актюбинская": "15", "алматинская": "19", "атырауская": "23",
    "западно-казахстанская": "27", "жамбылская": "31", "карагандинская": "35",
    "костанайская": "39", "кызылординская": "43", "мангистауская": "47",
    "мангыстауская": "47",
    "павлодарская": "55", "северо-казахстанская": "59", "туркестанская": "61",
    "восточно-казахстанская": "63", "нур-султан": "71", "астана": "71", "алматы": "75",
    "шымкент": "79",
}
MEDIAN_NOTE = ("Median of the 2021 census's single years of age (0 to 99 and 100 and "
               "over), interpolated within the year holding the middle person.")
RATIO_NOTE = "Men per 100 women, from the census's counts of men and women."


# --------------------------------------------------------------------------
# The workbook.

def age_of(label: Any) -> int | None:
    """0..99 from a single-year heading, 100 from '100+' or '100 и старше'."""
    text = str(label if label is not None else "").strip()
    if re.fullmatch(r"\d+(\.0)?", text):
        return int(float(text))
    m = re.fullmatch(r"(\d+)\s*(\+|и\s*старше|и\s*более)", text)
    return int(m.group(1)) if m else None


def number(cell: Any) -> int:
    if cell is None or str(cell).strip() in ("", "-", "–"):
        return 0
    if isinstance(cell, (int, float)):
        return int(cell)
    return int(str(cell).replace(" ", "").replace("\xa0", ""))


def region_prefix(heading: str) -> str:
    name = re.sub(r"(^г\.\s*|\s*область$)", "", " ".join(str(heading).split()), flags=re.I)
    prefix = SHEET_REGIONS.get(name.lower())
    if not prefix:
        raise SystemExit(f"kazakhstan_census: sheet 1.1 region {heading!r} is not known")
    return prefix


def parse_regions(rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Counter]]:
    """{KATO prefix: {'both'|'men'|'women': Counter(age -> n)}} from sheet 1.1."""
    head = next((i for i, r in enumerate(rows) if r and str(r[0] or "").strip() == "Регионы"),
                None)
    if head is None:
        raise SystemExit("kazakhstan_census: sheet 1.1 has no 'Регионы' row")
    regions, kinds, sexes = rows[head], rows[head + 1], rows[head + 2]
    columns: dict[int, tuple[str, str]] = {}
    region = kind = None
    for j in range(1, len(regions)):
        region = regions[j] if regions[j] not in (None, "") else region
        kind = kinds[j] if j < len(kinds) and kinds[j] not in (None, "") else kind
        sex = str(sexes[j] or "").strip() if j < len(sexes) else ""
        if region is None or str(kind).strip() != "Всего":
            continue
        which = {"Всего": "both", "Мужчины": "men", "Женщины": "women"}.get(sex)
        if which and str(region).strip() != "Республика Казахстан":
            columns[j] = (region_prefix(str(region)), which)
    out: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    totals: dict[tuple[str, str], int] = {}
    for row in rows[head + 3:]:
        if not row or row[0] is None:
            continue
        first = str(row[0]).strip()
        if first.startswith("Возраст"):
            totals = {columns[j]: number(row[j]) for j in columns}
            continue
        age = age_of(first)
        if age is None:
            if out:
                break
            continue
        for j, (prefix, which) in columns.items():
            out[prefix][which][age] += number(row[j]) if j < len(row) else 0
    if len({p for p, _ in columns.values()}) != 17:
        raise SystemExit(f"kazakhstan_census: sheet 1.1 has {len(out)} regions, not 17")
    for prefix, sexes_ in out.items():
        both, men, women = (sum(sexes_[w].values()) for w in ("both", "men", "women"))
        if men + women != both or (totals and totals.get((prefix, "both")) != both):
            raise SystemExit(f"kazakhstan_census: sheet 1.1 region {prefix}: men {men:,} + "
                             f"women {women:,} against {both:,} (total row "
                             f"{totals.get((prefix, 'both'))})")
        for age in sexes_["both"]:
            if sexes_["men"][age] + sexes_["women"][age] != sexes_["both"][age]:
                raise SystemExit(f"kazakhstan_census: sheet 1.1 region {prefix}, age {age}: "
                                 f"men and women do not make both sexes")
    return {p: dict(v) for p, v in out.items()}


def parse_localities(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Levels 0-2 of sheet 3.1: [{level, kato, name, total, ages}] in order."""
    head = next((i for i, r in enumerate(rows) if r and str(r[0] or "").strip() == "Уровень"),
                None)
    if head is None:
        raise SystemExit("kazakhstan_census: sheet 3.1 has no 'Уровень' row")
    header = rows[head]
    ages = {j: age_of(header[j]) for j in range(4, len(header))}
    unknown = [header[j] for j, a in ages.items() if a is None and header[j] not in (None, "")]
    if unknown:
        raise SystemExit(f"kazakhstan_census: sheet 3.1 age headings {unknown[:5]}")
    out = []
    for row in rows[head + 1:]:
        if not row or row[0] is None or not re.fullmatch(r"\d+", str(row[0]).strip()):
            continue
        level = int(row[0])
        if level > 2:
            continue
        counts = Counter({ages[j]: number(row[j]) for j in ages
                          if ages[j] is not None and j < len(row)})
        total = number(row[3])
        if sum(counts.values()) != total:
            raise SystemExit(f"kazakhstan_census: {row[2]}: single years make "
                             f"{sum(counts.values()):,} against {total:,}")
        out.append({"level": level, "kato": str(row[1]).strip().zfill(9),
                    "name": " ".join(str(row[2]).split()), "total": total, "ages": counts})
    return out


def regions_of(localities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{KATO prefix: {'total', 'ages', 'units': [level-2 rows]}} with every sum checked."""
    national = [u for u in localities if u["level"] == 0]
    out: dict[str, dict[str, Any]] = {}
    for unit in localities:
        prefix = unit["kato"][:2]
        if unit["level"] == 1:
            out[prefix] = {"name": unit["name"], "total": unit["total"], "ages": unit["ages"],
                           "units": []}
        elif unit["level"] == 2:
            if prefix not in out:
                raise SystemExit(f"kazakhstan_census: {unit['name']} before its region")
            out[prefix]["units"].append(unit)
    if set(out) != set(KATO_REGION):
        raise SystemExit(f"kazakhstan_census: regions {sorted(set(out) ^ set(KATO_REGION))}")
    for prefix, region in out.items():
        summed = sum(u["total"] for u in region["units"])
        if summed != region["total"]:
            raise SystemExit(f"kazakhstan_census: {region['name']}'s districts make "
                             f"{summed:,} against {region['total']:,}")
    country = sum(r["total"] for r in out.values())
    if country != NATIONAL or (national and national[0]["total"] != NATIONAL):
        raise SystemExit(f"kazakhstan_census: the regions make {country:,}, not {NATIONAL:,}")
    return out


# --------------------------------------------------------------------------
# Table 2.2 of the first volume.

def readings(tokens: list[str], start: int) -> Iterable[tuple[int | None, int]]:
    """(value, next token) for each way a figure can begin at tokens[start].

    Thousands are set apart by spaces, so '187 897' is one figure and '1 012'
    may be one too; a token of four digits or more stands alone.
    """
    token = tokens[start]
    if token in ("-", "–"):
        yield None, start + 1
        return
    if not token.isdigit() or (len(token) > 1 and token[0] == "0"):
        return
    yield int(token), start + 1
    if len(token) <= 3:
        value, j = int(token), start + 1
        while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
            value, j = value * 1000 + int(tokens[j]), j + 1
            yield value, j


def whole(total: int | None, men: int | None, women: int | None, ratio: int | None) -> bool:
    """A census's four figures agree: men and women make the total, and the ratio."""
    if None in (total, men, women, ratio):
        return total is None or None in (men, women) or men + women == total
    if men + women != total or not women:
        return False
    return abs(ratio - 1000 * men / women) <= 1


def split_row(text: str) -> list[int | None] | None:
    """The eight figures of a table 2.2 row, if exactly one reading makes them whole."""
    tokens = text.split()
    found: list[list[int | None]] = []

    def walk(i: int, acc: list[int | None]) -> None:
        if len(acc) == 4 and not whole(*acc):
            return
        if len(acc) == 8:
            if i == len(tokens) and whole(*acc[4:]):
                found.append(list(acc))
            return
        if i >= len(tokens):
            return
        for value, j in readings(tokens, i):
            walk(j, acc + [value])

    walk(0, [])
    return found[0] if len(found) == 1 else None


ROW = re.compile(r"^\s*(?P<label>[^\d]*?)\s*(?P<figures>[\d][\d\s\-–]*)$")


def table_rows(text: str) -> list[tuple[str, list[int | None]]]:
    """(label, figures) for every line of table 2.2's whole-population part."""
    # The contents page names the table first; the table's own heading is
    # the last mention.
    start = text.rfind("2.2 Population by city and district")
    if start < 0:
        raise SystemExit("kazakhstan_census: table 2.2 not found in the volume")
    body = text[start:]
    end = body.find("Urban population")
    if end < 0:
        raise SystemExit("kazakhstan_census: table 2.2's whole-population part has no end")
    out = []
    for line in body[:end].splitlines():
        m = ROW.match(line)
        if not m:
            continue
        figures = split_row(m.group("figures"))
        if figures is not None:
            out.append((" ".join(m.group("label").split()), figures))
    return out


def volume_text(blob: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def sexes_by_unit(rows: list[tuple[str, list[int | None]]],
                  regions: dict[str, dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """{KATO code: (men, women)} for every level-2 unit, matched by its 2021 total.

    Table 2.2 lists a region's row and then its cities and districts in the
    KATO order, with a city's own districts indented beneath it. A unit takes
    the row of its region's block whose 2021 total is its own; each row is
    taken once, and a unit with no such row stops the run.
    """
    starts = {r["total"]: prefix for prefix, r in regions.items()}
    blocks: dict[str, list[tuple[str, list[int | None]]]] = defaultdict(list)
    current = None
    for label, figures in rows:
        total = figures[4]
        if total in starts and ("region" in label.lower() or "city" in label.lower()):
            current = starts[total]
            continue
        if current:
            blocks[current].append((label, figures))
    out: dict[str, tuple[int, int]] = {}
    missing = []
    for prefix, region in regions.items():
        if prefix in CITY_UNITS or prefix == "71":
            continue
        pool = list(blocks.get(prefix, []))
        for unit in region["units"]:
            hit = next((i for i, (_, f) in enumerate(pool) if f[4] == unit["total"]), None)
            if hit is None:
                missing.append(f"{unit['name']} ({unit['total']:,})")
                continue
            _, figures = pool.pop(hit)
            out[unit["kato"]] = (figures[5], figures[6])
    if missing:
        raise SystemExit(f"kazakhstan_census: table 2.2 has no row for {missing}")
    return out


# --------------------------------------------------------------------------
# Records.

def ratio(men: int, women: int) -> float:
    return round(100 * men / women, 1)


def fields(ages: Counter, men: int, women: int, note: str | None) -> dict[str, Any]:
    extra = f" {note}" if note else ""
    return {
        "median_age": measure(median_age(ages), year=YEAR, source=WORKBOOK_SOURCE),
        "median_age_note": MEDIAN_NOTE + extra,
        "sex_ratio": measure(ratio(men, women), year=YEAR, source=VOLUME_SOURCE,
                             unit="males_per_100_females"),
        "sex_ratio_note": RATIO_NOTE + extra,
    }


def build(regions: dict[str, dict[str, Any]], sexes: dict[str, dict[str, Counter]],
          by_unit: dict[str, tuple[int, int]], a1: list[dict[str, Any]],
          a2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    src = [{"field": "median_age", "name": WORKBOOK_SOURCE, "url": PAGE, "license": LICENCE},
           {"field": "sex_ratio", "name": VOLUME_SOURCE, "url": PAGE, "license": LICENCE}]
    region_ids = {u["name"]: u["id"] for u in a1}
    shapes = {u["id"]: u for u in a2}
    out: list[dict[str, Any]] = []
    # First level: sheet 1.1's regions, pooled where the map draws one shape.
    pooled: dict[str, list[str]] = defaultdict(list)
    for prefix in sorted(KATO_REGION):
        pooled[KATO_REGION[prefix]].append(prefix)
    for name, prefixes in sorted(pooled.items()):
        if name not in region_ids:
            raise SystemExit(f"kazakhstan_census: no drawn region {name!r}")
        ages = sum((sexes[p]["both"] for p in prefixes), Counter())
        men = sum(sum(sexes[p]["men"].values()) for p in prefixes)
        women = sum(sum(sexes[p]["women"].values()) for p in prefixes)
        if sum(ages.values()) != sum(regions[p]["total"] for p in prefixes):
            raise SystemExit(f"kazakhstan_census: {name}: sheet 1.1 and sheet 3.1 disagree")
        note = (f"Turkestan Region and the city of Shymkent, a region of its own since "
                f"2018, together." if len(prefixes) > 1 else None)
        out.append(record(
            f"KAZ-CENSUS-{'-'.join(prefixes)}", name, level="admin1", parent=ISO3,
            country=ISO3, match_by="shape_id", shape_id=region_ids[name],
            sources=src, **fields(ages, men, women, note)))
    # Second level: the units of each drawn region, placed on its polygons.
    units_by_region: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for prefix, region in regions.items():
        name = KATO_REGION[prefix]
        if prefix == "71":
            continue
        if prefix in CITY_UNITS:
            men = sum(sexes[prefix]["men"].values())
            women = sum(sexes[prefix]["women"].values())
            units_by_region[name][CITY_UNITS[prefix]] = {
                "ages": region["ages"], "men": men, "women": women}
            continue
        for unit in region["units"]:
            men, women = by_unit[unit["kato"]]
            if men + women != unit["total"]:
                raise SystemExit(f"kazakhstan_census: {unit['name']}: men and women "
                                 f"make {men + women:,} against {unit['total']:,}")
            if unit["name"] in units_by_region[name]:
                raise SystemExit(f"kazakhstan_census: {unit['name']} twice in {name}")
            units_by_region[name][unit["name"]] = {"ages": unit["ages"], "men": men,
                                                   "women": women}
    region_of = {u["id"]: u["name"] for u in a1}
    for name in sorted(units_by_region):
        units = units_by_region[name]
        for shape_id, names in sorted(kz.place(name, list(units), a1, a2).items()):
            label = shapes[shape_id]["name"]
            ages = sum((units[n]["ages"] for n in names), Counter())
            men = sum(units[n]["men"] for n in names)
            women = sum(units[n]["women"] for n in names)
            out.append(record(
                f"KAZ-CENSUS-{shape_id}", label, level="admin2",
                parent=kz.region_id(name), parent_name=name, country=ISO3,
                match_by="shape_id", shape_id=shape_id, aliases=sorted(set(names) - {label}),
                sources=src, **fields(ages, men, women, kz.polygon_note(label, names))))
        for (region, label), reason in kz.EMPTY.items():
            if region != name:
                continue
            for shape in a2:
                if shape["name"] == label and region_of.get(shape.get("parent")) == region:
                    out.append(record(
                        f"KAZ-CENSUS-{shape['id']}", label, level="admin2",
                        parent=kz.region_id(region), parent_name=region, country=ISO3,
                        match_by="shape_id", shape_id=shape["id"],
                        median_age=gap(NOT_AVAILABLE, reason),
                        sex_ratio=gap(NOT_AVAILABLE, reason)))
    return out


def workbook_rows(blob: bytes) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    for sheet in ("1.1", "3.1"):
        if sheet not in book.sheetnames:
            raise SystemExit(f"kazakhstan_census: no sheet {sheet}; sheets {book.sheetnames}")
    return (list(book["1.1"].iter_rows(values_only=True)),
            list(book["3.1"].iter_rows(values_only=True)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("kazakhstan_census: 2021 census ages (workbook) and sexes (volume 1, table 2.2)")
    blob = http_get(WORKBOOK_URL, binary=True, timeout=300)
    assert isinstance(blob, bytes)
    sheet11, sheet31 = workbook_rows(blob)
    sexes = parse_regions(sheet11)
    regions = regions_of(parse_localities(sheet31))
    for prefix, region in regions.items():
        both = sum(sexes[prefix]["both"].values())
        if both != region["total"]:
            raise SystemExit(f"kazakhstan_census: {region['name']}: sheet 1.1 has {both:,}, "
                             f"sheet 3.1 {region['total']:,}")
    volume = http_get(VOLUME_URL, binary=True, timeout=300)
    assert isinstance(volume, bytes)
    rows = table_rows(volume_text(volume))
    log(f"  table 2.2: {len(rows)} rows read whole")
    by_unit = sexes_by_unit(rows, regions)
    a1, a2 = kz.drawn_units()
    out = build(regions, sexes, by_unit, a1, a2)
    for level in ("admin1", "admin2"):
        mine = [r for r in out if r["level"] == level]
        log(f"  {level}: {len(mine)} records")
    for r in out:
        med, sr = r["median_age"], r["sex_ratio"]
        if "value" in med:
            log(f"    {r['level']} {r['name']}: median {med['value']}, ratio {sr['value']}")
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
