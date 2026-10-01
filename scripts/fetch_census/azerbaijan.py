#!/usr/bin/env python3
"""Azerbaijan's rayons and cities from the State Statistical Committee's own tables.

Azstat publishes the permanent population at the start of each year by
economic region and administrative-territorial unit, by sex and five-year age
group (table 1.23, ``001_23.xls``: one sheet each for everyone, men and women,
1 January 2020 to the latest year). That is population, men per hundred women
and a median age for every rayon and city of republican subordination, the
median interpolated within the five-year group holding the middle person --
Azstat publishes single years of age for the country and not for its rayons.

**Units the map draws and the table does not.** Four cities -- Lankaran,
Shaki, Yevlakh and Shusha -- are drawn as polygons of their own beside the
rayon around each; Azstat's table counts each city inside its rayon. Their
figure covers two polygons and is written on neither. Table 1.19 gives each
city's population alone, in thousands to one decimal, and that is written on
the city's polygon, with the rayon's remainder on the rayon's -- except
Lankaran's, which the map draws as two polygons (the rayon and its exclave
on the coast north of the city), neither of which is the rayon.

**The rayons that were outside the government's control until 2020-2023**
(Agdam, Fuzuli and Tartar in part; Kalbajar, Lachin, Qubadli, Zangilan,
Jabrayil, Khojaly, Khojavend, Shusha, Aghdara and the city of Khankendi
whole) are written with a note saying what their figure is. The 2019 census
did not enumerate that territory (Azstat's table 1.17: "excluding the
population in the territories under occupation at the time of the census"),
and Azstat's annual estimates attribute to these units the population
registered to them, which is not a count of residents on the ground.

**First level.** Nakhchivan's figures are its economic region's row. The rest
of the country, "Contiguous Azerbaijan" on the map, is the country's row less
Nakhchivan's, age group by age group.

Usage:
    python -m scripts.fetch_census.azerbaijan
"""

from __future__ import annotations

import argparse
import io
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .cod_ps_age import grouped_median
from .east_checks import check_median

SITE = PROCESSED.parent.parent / "site" / "data"
BASE = "https://www.stat.gov.az/source/demoqraphy/az/"
AGES = BASE + "001_23.xls"
CITIES = BASE + "001_19.xls"
PAGE = "https://www.stat.gov.az/source/demoqraphy/"
SOURCE = ("State Statistical Committee of the Republic of Azerbaijan, permanent "
          "population by economic regions and administrative-territorial units, "
          "sex and age groups (table 1.23)")
CITY_SOURCE = ("State Statistical Committee of the Republic of Azerbaijan, "
               "permanent population by economic regions, administrative-"
               "territorial units, cities and settlements (table 1.19)")
LICENCE = "Azstat, open publication"
OUT = "azerbaijan_rayon.json"

# Azstat's name -> the map's polygon. Written out: 75 rows and 79 polygons,
# every pair checkable by eye, and a romanisation rule would be this code
# guessing at a name. The four cities inside rayons, and Lankaran's two
# polygons, are handled below them.
POLYGON = {
    "Bakı şəhəri": "Baku City", "Naxçıvan şəhəri": "Nakhchivan City",
    "Babək rayonu": "Babek District", "Culfa rayonu": "Julfa District",
    "Kəngərli rayonu": "Kangarli District", "Ordubad rayonu": "Ordubad District",
    "Sədərək rayonu": "Sadarak District", "Şahbuz rayonu": "Shahbuz District",
    "Şərur rayonu": "Sharur District", "Sumqayıt şəhəri": "Sumqayit City",
    "Abşeron rayonu": "Absheron District", "Xızı rayonu": "Khizi District",
    "Ağsu rayonu": "Agsu District", "İsmayıllı rayonu": "Ismailli District",
    "Qobustan rayonu": "Gobustan District", "Şamaxı rayonu": "Shamakhi District",
    "Gəncə şəhəri": "Ganja City", "Naftalan şəhəri": "Naftalan City",
    "Daşkəsən rayonu": "Dashkasan District", "Goranboy rayonu": "Goranboy District",
    "Göygöl rayonu": "Goygol District", "Samux rayonu": "Samukh District",
    "Xankəndi şəhəri": "Khankendi City", "Ağcabədi rayonu": "Aghjabadi District",
    "Ağdam rayonu": "Agdam District", "Bərdə rayonu": "Barda District",
    "Füzuli rayonu": "Fuzuli District", "Xocalı rayonu": "Khojaly District",
    "Xocavənd rayonu": "Khojavend District", "Tərtər rayonu": "Tartar District",
    "Ağstafa rayonu": "Agstafa District", "Gədəbəy rayonu": "Gadabay District",
    "Qazax rayonu": "Qazakh District", "Şəmkir rayonu": "Shamkir District",
    "Tovuz rayonu": "Tovuz District", "Xaçmaz rayonu": "Khachmaz District",
    "Quba rayonu": "Quba District", "Qusar rayonu": "Qusar District",
    "Siyəzən rayonu": "Siazan District", "Şabran rayonu": "Shabran District",
    "Astara rayonu": "Astara District", "Cəlilabad rayonu": "Jalilabad District",
    "Lerik rayonu": "Lerik District", "Masallı rayonu": "Masally District",
    "Yardımlı rayonu": "Yardymli District", "Mingəçevir şəhəri": "Mingachevir City",
    "Ağdaş rayonu": "Agdash District", "Göyçay rayonu": "Goychay District",
    "Kürdəmir rayonu": "Kurdamir District", "Ucar rayonu": "Ujar District",
    "Zərdab rayonu": "Zardab District", "Beyləqan rayonu": "Beylagan District",
    "İmişli rayonu": "Imishli District", "Saatlı rayonu": "Saatly District",
    "Sabirabad rayonu": "Sabirabad District", "Balakən rayonu": "Balakan District",
    "Qax rayonu": "Qakh District", "Qəbələ rayonu": "Qabala District",
    "Oğuz rayonu": "Oghuz District", "Zaqatala rayonu": "Zaqatala District",
    "Cəbrayıl rayonu": "Jabrayil District", "Kəlbəcər rayonu": "Kalbajar District",
    "Qubadlı rayonu": "Qubadli District", "Laçın rayonu": "Lachin District",
    "Zəngilan rayonu": "Zangilan District", "Şirvan şəhəri": "Shirvan City",
    "Biləsuvar rayonu": "Bilasuvar District", "Hacıqabul rayonu": "Hajigabul District",
    "Neftçala rayonu": "Neftchala District", "Salyan rayonu": "Salyan District",
}

# Rayons whose figure takes in a city the map draws apart: rayon -> (the
# city's name in table 1.19, its polygon, the rayon's polygon or None when
# the map draws the rayon as more than one polygon).
SPLIT = {
    "Lənkəran rayonu": ("Lənkəran şəhəri", "Lankaran City", None),
    "Şəki rayonu": ("Şəki şəhəri", "Shaki City", "Shaki District"),
    "Yevlax rayonu": ("Yevlax şəhəri", "Yevlakh City", "Yevlakh District"),
    "Şuşa rayonu": ("Şuşa şəhəri", "Shusha City", "Shusha District"),
}

# Rows with no polygon of their own on this map.
NO_POLYGON = {
    "Ağdərə rayonu": ("Aghdara rayon, re-formed in Azstat's classification; the "
                      "map draws no polygon for it"),
}

# Units outside the government's control between the early 1990s and 2020-2023,
# whole or in part (the Qarabağ and Şərqi Zəngəzur economic regions, less
# Ağcabədi and Bərdə, which never were).
CONTESTED = {
    "Xankəndi şəhəri", "Ağdam rayonu", "Ağdərə rayonu", "Füzuli rayonu",
    "Xocalı rayonu", "Xocavənd rayonu", "Şuşa rayonu", "Tərtər rayonu",
    "Cəbrayıl rayonu", "Kəlbəcər rayonu", "Qubadlı rayonu", "Laçın rayonu",
    "Zəngilan rayonu",
}
CONTESTED_NOTE = (
    " The unit was wholly or partly outside the government's control from the "
    "early 1990s until 2020-2023, and the 2019 census did not enumerate that "
    "territory (Azstat, table 1.17: 'excluding the population in the "
    "territories under occupation at the time of the census'). The figure is "
    "Azstat's estimate for the start of the year, which the table does not say "
    "how it makes; with no census behind it, it should not be read as a count of "
    "the people living there (Khankendi's has moved only from 4,295 to 4,387 "
    "since 2020).")

# What this file does not write, and why, on every unit it writes: Azstat's
# yearbook gives the 2019 census's nationality (table 1.5) and native
# language (table 1.6) for the country alone.
UNREAD = {
    "ethnicity": gap(NOT_AVAILABLE, (
        "Azstat publishes the 2019 census's nationality for the country only (table "
        "1.5 of 'The population of Azerbaijan'); no table gives it by rayon, city or "
        "for Nakhchivan.")),
    "language": gap(NOT_AVAILABLE, (
        "Azstat publishes the 2019 census's native language for the country only "
        "(table 1.6 of 'The population of Azerbaijan'); no table gives it by rayon, "
        "city or for Nakhchivan.")),
    "religion": gap(NOT_AVAILABLE, (
        "Azstat's population tables, the 2019 census's among them, give no religion "
        "by rayon, city or for Nakhchivan.")),
}

# Rows far from the figures the map carried before, with what was measured
# (table 1.23's every sheet, 2020-2026, and table 1.19): Azstat's own series
# is steady, and the earlier figures describe something else.
CHECKED = {
    "Abşeron rayonu": (" The rayon takes in the city of Xırdalan (196,200 at the start "
                       "of 2026, table 1.19); Azstat's figure for it has run from "
                       "428,498 (2020) to 435,187 (2026), about twice the 210,000 "
                       "some older compilations give."),
    "Sədərək rayonu": (" Azstat's figure for the rayon has run from 22,569 (2020) to "
                       "23,365 (2026)."),
}

COUNTRY = "Azərbaycan Respublikası"
NAKHCHIVAN = "Naxçıvan iqtisadi rayonu"
GROUP = re.compile(r"^(\d+)\s*-\s*(\d+)$")
OPEN = re.compile(r"^(\d+)\s*\+$")


def clean(name: Any) -> str:
    text = " ".join(str(name or "").split())
    return re.sub(r"\s*-\s*cəmi$|\s*-\s*c ə m i$", "", text).strip()


def number(cell: Any) -> float | None:
    if cell in (None, "", "-", "…", "..."):
        return None
    try:
        return float(str(cell).replace(",", "."))
    except ValueError:
        return None


def sheet_rows(book, title: str) -> list[list[Any]]:
    sheet = book.sheet_by_name(title)
    return [sheet.row_values(i) for i in range(sheet.nrows)]


def age_table(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{unit: {total, groups}} from one sheet of table 1.23."""
    header = None
    for i, row in enumerate(rows[:15]):
        cells = [str(c).strip() for c in row]
        if "0-4" in cells:
            header = i
            break
    if header is None:
        raise SystemExit("azerbaijan: no age-group header in table 1.23")
    bands: list[tuple[int, int, int | None]] = []
    for j, cell in enumerate(rows[header]):
        text = str(cell).strip()
        if m := GROUP.match(text):
            bands.append((j, int(m.group(1)), int(m.group(2))))
        elif m := OPEN.match(text):
            bands.append((j, int(m.group(1)), None))
    if not bands or bands[0][1] != 0 or bands[-1][2] is not None:
        raise SystemExit(f"azerbaijan: table 1.23's groups run {bands[:2]}...{bands[-1:]}")
    out: dict[str, dict[str, Any]] = {}
    for row in rows[header + 1:]:
        name = clean(row[1] if len(row) > 1 else "")
        total = number(row[2]) if len(row) > 2 else None
        if not name or total is None:
            continue
        name = COUNTRY if name.startswith(COUNTRY) else name
        groups = [(low, high, number(row[j]) or 0.0) for j, low, high in bands]
        out[name] = {"total": total, "groups": groups}
    return out


def latest_year(book) -> int:
    years = [int(m.group(1)) for n in book.sheet_names()
             if (m := re.match(r"01\.01\.(\d{4}) il \(bütün", n))]
    if not years:
        raise SystemExit("azerbaijan: table 1.23 has no 'bütün əhali' sheet")
    return max(years)


def read_ages(blob: bytes) -> tuple[int, dict[str, dict[str, Any]]]:
    """(year, {unit: total, men, women, groups}) for the latest year, every sum checked."""
    import xlrd
    book = xlrd.open_workbook(file_contents=blob)
    year = latest_year(book)
    sheets = {kind: age_table(sheet_rows(book, f"01.01.{year} il ({kind})"))
              for kind in ("bütün əhali", "kişilər", "qadınlar")}
    everyone, men, women = sheets["bütün əhali"], sheets["kişilər"], sheets["qadınlar"]
    out: dict[str, dict[str, Any]] = {}
    for name, got in everyone.items():
        if name not in men or name not in women:
            raise SystemExit(f"azerbaijan: {name} is in the everyone sheet and not both sexes'")
        made = sum(n for _, _, n in got["groups"])
        m, w = men[name]["total"], women[name]["total"]
        if abs(made - got["total"]) > 0.5 or abs(m + w - got["total"]) > 0.5:
            raise SystemExit(f"azerbaijan {year}: {name}: the groups make {made:,.0f} and "
                             f"the sexes {m + w:,.0f}, against {got['total']:,.0f}")
        out[name] = {"total": got["total"], "men": m, "women": w, "groups": got["groups"]}
    return year, out


def read_cities(blob: bytes) -> dict[str, dict[str, float]]:
    """{city: {total, men, women}} in persons, from table 1.19's thousands."""
    import xlrd
    book = xlrd.open_workbook(file_contents=blob)
    rows = sheet_rows(book, book.sheet_names()[0])
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        name = clean(row[1] if len(row) > 1 else "")
        if name in {c for c, _, _ in SPLIT.values()} and name not in out:
            total, men, women = (number(row[k]) for k in (2, 3, 4))
            if total is None or men is None or women is None:
                raise SystemExit(f"azerbaijan: table 1.19 gives no figures for {name}")
            out[name] = {"total": round(total * 1000), "men": men * 1000,
                         "women": women * 1000}
    missing = {c for c, _, _ in SPLIT.values()} - set(out)
    if missing:
        raise SystemExit(f"azerbaijan: table 1.19 has no row for {sorted(missing)}")
    return out


def fields(unit: dict[str, Any], year: int, note: str = "") -> dict[str, Any]:
    median = grouped_median([(lo, hi, n) for lo, hi, n in unit["groups"]])
    men, women = unit["men"], unit["women"]
    return {
        "population": measure(int(round(unit["total"])), year=year, source=SOURCE),
        "population_note": f"Permanent population at the start of {year}." + note,
        "median_age": measure(median, unit="years", year=year, source=SOURCE)
        if median is not None else None,
        "median_age_note": ("Interpolated within the five-year age group holding the "
                            "middle person; Azstat publishes five-year groups for "
                            "rayons, and single years only for the country." + note),
        "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                             year=year, source=SOURCE),
        "sex_ratio_note": f"{int(men):,} men and {int(women):,} women." + note,
        "sources": [{"field": f, "name": SOURCE, "url": PAGE, "license": LICENCE,
                     "year": year} for f in ("population", "median_age", "sex_ratio")],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    year, table = read_ages(http_get(AGES, binary=True, cache=False))
    cities = read_cities(http_get(CITIES, binary=True, cache=False))
    log(f"  table 1.23 for 1 January {year}: {len(table)} rows, every row's groups and "
        "sexes making its total")

    admin1 = json.loads((SITE / "admin1" / "AZE.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "AZE.units.json").read_text())
    by_name: dict[str, list[dict[str, Any]]] = {}
    for u in admin2:
        by_name.setdefault(u["name"], []).append(u)

    # The units the country's row is made of, which must add up to it.
    rows = set(POLYGON) | set(SPLIT) | set(NO_POLYGON)
    missing = rows - set(table)
    if missing:
        raise SystemExit(f"azerbaijan: table 1.23 has no row for {sorted(missing)}")
    made = sum(table[r]["total"] for r in rows)
    if abs(made - table[COUNTRY]["total"]) > 0.5:
        raise SystemExit(f"azerbaijan: the {len(rows)} units make {made:,.0f}, the "
                         f"country {table[COUNTRY]['total']:,.0f}")
    log(f"  the {len(rows)} rayons and cities make the country's "
        f"{table[COUNTRY]['total']:,.0f}")
    # The country's median from the same five-year groups the rayons' come
    # from, against Eurostat's (from Azstat's single years).
    check_median("AZ", year, grouped_median(sorted(table[COUNTRY]["groups"])),
                 "azerbaijan: the country (table 1.23)")

    records: list[dict[str, Any]] = []

    def polygon(name: str) -> dict[str, Any]:
        found = by_name.get(name, [])
        if len(found) != 1:
            raise SystemExit(f"azerbaijan: the map has {len(found)} polygons named {name!r}")
        return found[0]

    for row, shape_name in POLYGON.items():
        shape = polygon(shape_name)
        note = (CONTESTED_NOTE if row in CONTESTED else "") + CHECKED.get(row, "")
        records.append(record(f"AZE-AZSTAT-{shape['id']}", row, level="admin2",
                              parent="AZE", country="AZE", match_by="shape_id",
                              shape_id=shape["id"], **fields(table[row], year, note)))
    for row, (city, city_shape, rayon_shape) in SPLIT.items():
        rayon, town = table[row], cities[city]
        note = CONTESTED_NOTE if row in CONTESTED else ""
        gap_note = (f"Azstat publishes age groups and sexes for {row} whole, which "
                    f"takes in the city of {city.split()[0]}; the map draws the city and "
                    "the rest of the rayon as separate polygons, and the whole's figures "
                    "describe neither.")
        why = gap(NOT_AVAILABLE, gap_note)
        shape = polygon(city_shape)
        records.append(record(
            f"AZE-AZSTAT-{shape['id']}", city, level="admin2", parent="AZE",
            country="AZE", match_by="shape_id", shape_id=shape["id"],
            population=measure(town["total"], year=year, source=CITY_SOURCE),
            population_note=(f"The city's permanent population at the start of {year}, "
                             "published in thousands to one decimal." + note),
            median_age=why, sex_ratio=why,
            sources=[{"field": "population", "name": CITY_SOURCE, "url": PAGE,
                      "license": LICENCE, "year": year}]))
        if rayon_shape is None:
            parts = by_name.get("Lankaran District", [])
            log(f"  {row}: the map draws the rayon as {len(parts)} polygons; its "
                "remainder is written on neither")
            split = gap(NOT_AVAILABLE, (
                f"Azstat counts {row} with the city of Lankaran in it "
                f"({int(rayon['total']):,} at the start of {year}); the map draws the city "
                f"apart and the rest of the rayon as {len(parts)} polygons, and no "
                "published figure describes one of them."))
            for part in parts:
                records.append(record(
                    f"AZE-AZSTAT-{part['id']}", row, level="admin2", parent="AZE",
                    country="AZE", match_by="shape_id", shape_id=part["id"],
                    population=split, median_age=split, sex_ratio=split))
            continue
        shape = polygon(rayon_shape)
        rest = int(round(rayon["total"] - town["total"]))
        records.append(record(
            f"AZE-AZSTAT-{shape['id']}", row, level="admin2", parent="AZE",
            country="AZE", match_by="shape_id", shape_id=shape["id"],
            population=measure(rest, year=year, source=CITY_SOURCE),
            population_note=(f"The rayon's permanent population at the start of {year} "
                             f"({int(rayon['total']):,}, table 1.23) less the city of "
                             f"{city.split()[0]}'s ({town['total']:,}, table 1.19, in "
                             "thousands to one decimal)." + note),
            median_age=why, sex_ratio=why,
            sources=[{"field": "population", "name": CITY_SOURCE, "url": PAGE,
                      "license": LICENCE, "year": year},
                     {"field": "population", "name": SOURCE, "url": PAGE,
                      "license": LICENCE, "year": year}]))
    for row, why in NO_POLYGON.items():
        log(f"  {row} ({table[row]['total']:,.0f}): {why}")

    # First level.
    nakh = table[NAKHCHIVAN]
    country = table[COUNTRY]
    rest = {"total": country["total"] - nakh["total"],
            "men": country["men"] - nakh["men"], "women": country["women"] - nakh["women"],
            "groups": [(lo, hi, a - b) for (lo, hi, a), (_, _, b)
                       in zip(country["groups"], nakh["groups"])]}
    first = {u["name"]: u for u in admin1}
    for name, unit, note in (
            ("Nakhchivan Autonomous Republic", nakh, ""),
            ("Contiguous Azerbaijan", rest,
             " The country's figures less Nakhchivan's, age group by age group.")):
        shape = first[name]
        records.append(record(f"AZE-AZSTAT-{shape['id']}", name, level="admin1",
                              parent="AZE", country="AZE", match_by="shape_id",
                              shape_id=shape["id"], **fields(unit, year, note)))
    nakh_rows = ["Naxçıvan şəhəri", "Babək rayonu", "Culfa rayonu", "Kəngərli rayonu",
                 "Ordubad rayonu", "Sədərək rayonu", "Şahbuz rayonu", "Şərur rayonu"]
    if abs(sum(table[r]["total"] for r in nakh_rows) - nakh["total"]) > 0.5:
        raise SystemExit("azerbaijan: Nakhchivan's units do not make its total")
    for r in records:
        for field, why in UNREAD.items():
            if isinstance(r.get(field), dict) and not r[field].get("note"):
                r[field] = why
    bound = {r["shape_id"] for r in records if r["level"] == "admin2"}
    left = sorted(u["name"] for u in admin2 if u["id"] not in bound)
    log(f"  {len(bound)} of {len(admin2)} polygons written; left: {left}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
