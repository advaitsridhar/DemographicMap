#!/usr/bin/env python3
"""Cuba: ONEI's population by municipio at the end of 2024, and the 2012 census's skin colour.

Cuba's 16 provinces and 168 municipios had no median age, sex ratio or
composition, and 60 municipios no population. ONEI's own site answers this
map's reader with an expired certificate (and, for the Wayback Machine's
crawler, now and then a 403), so both publications are read from the
Internet Archive's captures of ONEI's own files, byte for byte (``id_``).

* **Population, sex ratio and median age** -- *Estudios y Datos sobre la
  Población Cubana 2024* (ONEI, Centro de Estudios de Población y Desarrollo,
  May 2025): Table 1, the population of every province and municipio by sex
  and zone at 31 December 2024, and Table 5, every municipio by sex and
  five-year age group. The count is ONEI's "población efectiva", the
  resident population it has published since the 2024 yearbook (those who
  spent 180 of the last 365 days in the country), carried forward from the
  2012 census by the vital and migration registers. Median age is
  interpolated within the five-year group holding the middle person; a
  province's age groups are the sum of its municipios'.
* **Ethnicity** -- the 2012 Population and Housing Census (Censo de Población
  y Viviendas 2012), as ONEI's *El color de la piel según el Censo de
  Población y Viviendas de 2012* tabulates it in its statistical annex, Table
  1: everyone by skin colour -- white, black, mulatto or mestizo -- for every
  province and municipio. The only census of this century to ask it, and
  the only composition Cuba's census publishes: it asks neither religion nor
  language (NOT_COLLECTED_POLICY).

Every row is checked before anything is written: each row's sexes and zones
make its total (Table 1, Table 5), its colours make its total and its printed
shares (the 2012 table), each municipio's age groups make the men and women
Table 1 gives it, each province's municipios make the province and the
provinces make Cuba -- in both years. A number printed with spaces between
its thousands is read back only where one reading satisfies those sums; two
readings, or none, stop the run.

Usage:
    python -m scripts.fetch_census.cuba_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections.abc import Callable
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .binding import bind, fold
from .cod_ps_age import grouped_median

OUT = "cuba_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
WAYBACK = "http://web.archive.org/web/{stamp}id_/{url}"

ESTUDIOS = ("https://www.onei.gob.cu/sites/default/files/publicaciones/2025-05/"
            "estudios-y-datos-2024_0.pdf")
ESTUDIOS_STAMP = "20260624193511"
ESTUDIOS_YEAR = 2024
ESTUDIOS_SOURCE = ("ONEI, Estudios y Datos sobre la Población Cubana 2024 (May 2025), Tables 1 "
                   "and 5: population by province, municipio, sex and age at 31 December 2024")
NATIONAL_2024 = 9_748_007

COLOUR = ("http://www.one.cu/publicaciones/cepde/cpv2012/elcolordelapielcenso2012/"
          "0011%20ANEXO%20TABLAS%20ESTAD%C3%8DSTICAS.pdf")
COLOUR_STAMP = "2016"
COLOUR_YEAR = 2012
COLOUR_SOURCE = ("ONEI, El color de la piel según el Censo de Población y Viviendas de 2012, "
                 "statistical annex, Table 1: population by skin colour, province and municipio")
NATIONAL_2012 = 11_167_325

TABLE_1 = "1 . Población de Cuba por provincias y municipios, según sexo y zona"
TABLE_5 = "5 . Población de Cuba por municipios (incluye total provincial) y grupos de edades"
COLOUR_TABLE = "1. Población por color de la piel, según provincias y municipios"
COLOURS = ("White", "Black", "Mulatto or Mestizo")

# ONEI's province names -> the boundary file's.
PROVINCES = {"La Habana": "Havana", "Isla de Juventud": "Isle of Youth",
             "Isla de la Juventud": "Isle of Youth"}
# ONEI's municipio names -> the boundary file's, where they differ by more
# than accents and case. The special municipality of the Isle of Youth is
# its province's one unit.
# Table 1 of 2024 writes two municipios as neither Table 5 nor the boundary
# file does: "1ro de Enero" and "Antillas".
MUNICIPIOS = {"Carlos Manuel de Céspedes": "Céspedes", "Habana Vieja": "La Habana Vieja",
              "La Habana del Este": "Habana del Este", "Lajas": "Santa Isabel de las Lajas",
              "Isla de la Juventud": "Isle of Youth", "1ro de Enero": "Primero de Enero",
              "Antillas": "Antilla"}
AGE = re.compile(r"^(\d{1,2})-(\d{1,2})$")
OPEN = re.compile(r"^(\d{1,2})y\+?$")
NUMERIC = re.compile(r"^(?:\d+|-)$")
LETTER = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]")


def capitals(label: str) -> bool:
    """A label printed in capitals: a province, or in Table 5 a municipio's heading."""
    return bool(LETTER.search(label)) and label.upper() == label


def title_case(name: str) -> str:
    """A province printed in capitals, in the case ONEI prints its municipios."""
    small = {"de", "del", "la", "las", "los", "y"}
    words = name.lower().split()
    return " ".join(w if i and w in small else w[:1].upper() + w[1:] for i, w in enumerate(words))


def split_row(line: str) -> tuple[str, list[str]]:
    """A table row's label and its trailing number tokens (digit groups or '-')."""
    tokens = line.split()
    i = len(tokens)
    while i > 0 and NUMERIC.match(tokens[i - 1]):
        i -= 1
    return " ".join(tokens[:i]), tokens[i:]


# How far a printed row may miss its own sums: ONEI's tables are published
# with an occasional one-person disagreement between a total and its parts
# (Rodas in 2024: 9 285 urban men and 9 641 urban women printed against an
# urban total of 18 925, and so 14 518 men and 14 196 women against 28 713).
# One person out of place shows in two of a row's sums, so a row may miss
# them by two in all; it is logged, and anything more stops the run.
SLACK = 2
DISCREPANCIES: list[str] = []


def regroup(tokens: list[str], n: int, error: Callable[[list[int]], int],
            where: str) -> list[int]:
    """The one way of reading ``tokens`` as ``n`` numbers that meets the row's sums.

    ONEI prints thousands with a space ("1 317"), and sometimes not at all
    ("4516"), so a row of digit groups can be read several ways. A number is
    a group of any length, or one of up to three digits followed by groups of
    exactly three; "-" is zero. Every reading is tried; ``error`` says by how
    many people it misses the row's own sums. The reading that misses by
    least must be the only one to, and must miss by no more than ``SLACK``.
    """
    found: dict[tuple[int, ...], int] = {}

    def walk(i: int, acc: list[int]) -> None:
        if len(acc) == n:
            if i == len(tokens):
                found[tuple(acc)] = error(acc)
            return
        if i >= len(tokens) or len(tokens) - i < n - len(acc):
            return
        head = tokens[i]
        if head == "-":
            walk(i + 1, acc + [0])
            return
        value, j = int(head), i + 1
        walk(j, acc + [value])
        if len(head) > 3:
            return
        while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
            value = value * 1000 + int(tokens[j])
            j += 1
            walk(j, acc + [value])

    walk(0, [])
    best = min(found.values(), default=None)
    winners = [v for v, e in found.items() if e == best]
    if best is None or best > SLACK or len(winners) != 1:
        raise SystemExit(f"cuba_census: {where}: {len(winners)} readings of "
                         f"{' '.join(tokens)!r} come within {best} of its sums; exactly one "
                         f"must, within {SLACK}")
    if best:
        DISCREPANCIES.append(f"{where} (by {best})")
    return list(winners[0])


def zones_error(v: list[int]) -> int:
    """How far total, men, women; urban total, men, women; rural total, men, women miss their sums."""
    t, h, m, ut, uh, um, rt, rh, rm = v
    return (abs(t - h - m) + abs(ut - uh - um) + abs(rt - rh - rm) + abs(t - ut - rt)
            + abs(h - uh - rh) + abs(m - um - rm))


def colours_error(v: list[int]) -> int:
    return abs(v[0] - v[1] - v[2] - v[3])


def pdf_pages(url: str, stamp: str) -> list[str]:
    """The text of every page of a captured PDF."""
    from pypdf import PdfReader
    blob = http_get(WAYBACK.format(stamp=stamp, url=url), binary=True, cache=False)
    reader = PdfReader(io.BytesIO(blob))
    texts = [page.extract_text() or "" for page in reader.pages]
    log(f"  {url.rsplit('/', 1)[-1]}: {len(texts)} pages")
    return texts


def carrying(texts: list[str], marker: str) -> list[str]:
    """The pages whose text carries a table's title."""
    return [t for t in texts if marker in re.sub(r"\s+", " ", t)]


def check_sums(municipios: dict[str, dict[str, list[int]]], provinces: dict[str, list[int]],
               national: list[int] | None, total: int, what: str) -> None:
    if national is None or national[0] != total:
        raise SystemExit(f"cuba_census: {what}: the national row is {national}, not {total:,}")
    for province, values in provinces.items():
        made = [sum(col) for col in zip(*municipios[province].values())]
        if made != values:
            raise SystemExit(f"cuba_census: {what}: {province}'s municipios make {made}, the "
                             f"province {values}")
    made = [sum(col) for col in zip(*provinces.values())]
    count = sum(len(m) for m in municipios.values())
    if made != national or len(provinces) != 16 or count != 168:
        raise SystemExit(f"cuba_census: {what}: {len(provinces)} provinces and {count} "
                         f"municipios make {made}; ONEI published 16, 168 and {national}")


def by_province(texts: list[str], n: int, check: Callable[[list[int]], int],
                trailing_shares: int = 0
                ) -> tuple[dict[str, dict[str, list[int]]], dict[str, list[int]], list[int] | None,
                           list[tuple[str, list[int], list[float]]]]:
    """Rows of a province-and-municipio table: a province in capitals, its municipios after it.

    Returns {province: {municipio: values}}, {province: values}, the national
    row, and every row with the shares printed after its counts.
    """
    municipios: dict[str, dict[str, list[int]]] = {}
    provinces: dict[str, list[int]] = {}
    national: list[int] | None = None
    current = None
    rows = []
    for text in texts:
        for line in text.splitlines():
            words = line.split()
            printed: list[float] = []
            while trailing_shares and words and re.fullmatch(r"\d{1,3},\d", words[-1]):
                printed.insert(0, float(words.pop().replace(",", ".")))
            if len(printed) != trailing_shares:
                continue
            label, tokens = split_row(" ".join(words))
            if not label or len(tokens) < n or not LETTER.search(label):
                continue
            values = regroup(tokens, n, check, label)
            rows.append((label, values, printed))
            if label == "CUBA":
                national = values
            elif capitals(label):
                current = title_case(label)
                provinces[current] = values
                municipios.setdefault(current, {})
            elif current is None:
                raise SystemExit(f"cuba_census: municipio {label!r} before any province")
            else:
                municipios[current][label] = values
    # The Isle of Youth is a special municipality directly under the state:
    # the 2012 tables print it as a province with no municipio beneath it,
    # the 2024 ones as a province and its one municipio. Either way it is
    # one unit at both levels.
    for province, values in provinces.items():
        if not municipios[province]:
            municipios[province] = {province: values}
    return municipios, provinces, national, rows


def population_table(texts: list[str]) -> tuple[dict[str, dict[str, list[int]]], dict[str, list[int]]]:
    """Table 1 of 2024, checked: every row's zones, the provinces and Cuba."""
    municipios, provinces, national, _ = by_province(texts, 9, zones_error)
    check_sums(municipios, provinces, national, NATIONAL_2024, "2024")
    log(f"  Table 1: 16 provinces and 168 municipios making ONEI's {NATIONAL_2024:,}; every "
        "row's sexes and zones make its total")
    return municipios, provinces


def age_label(label: str) -> tuple[int, int | None] | None:
    if m := AGE.match(label):
        return int(m.group(1)), int(m.group(2))
    if m := OPEN.match(label.replace(" ", "")):
        return int(m.group(1)), None
    return None


def age_table(texts: list[str], municipios: dict[str, dict[str, list[int]]]
              ) -> dict[tuple[str, str], list[tuple[int, int | None, int, int]]]:
    """Table 5: (province, municipio) -> [(low, high, men, women)], checked against Table 1.

    A municipio's block opens with its name in capitals on a line of its
    own, then its "Total" row and eighteen age groups. A province's total
    row (capitals, with figures) says which province the blocks that follow
    belong to, so the two San Luis are told apart.
    """
    names = {fold(PROVINCES.get(p, p)): p for p in municipios}
    own = {p: {**{fold(m): m for m in ms}, **{fold(MUNICIPIOS.get(m, m)): m for m in ms}}
           for p, ms in municipios.items()}
    out: dict[tuple[str, str], list[tuple[int, int | None, int, int]]] = {}
    totals: dict[tuple[str, str], list[int]] = {}
    province: str | None = None
    municipio: tuple[str, str] | None = None
    for text in texts:
        for line in text.splitlines():
            label, tokens = split_row(line)
            if not label:
                continue
            key = fold(label)
            if not tokens and capitals(label) and province and key in own[province]:
                municipio = (province, own[province][key])
                if municipio in out:
                    raise SystemExit(f"cuba_census: Table 5 prints {municipio[1]} twice")
                out[municipio] = []
                continue
            if len(tokens) < 9:
                continue
            if capitals(label) and label != "CUBA":
                named = fold(PROVINCES.get(title_case(label), title_case(label)))
                if named not in names:
                    raise SystemExit(f"cuba_census: Table 5 names a province Table 1 does not: "
                                     f"{label!r}")
                province, municipio = names[named], None
                continue
            if municipio is None or label == "CUBA":
                continue
            values = regroup(tokens, 9, zones_error, f"{municipio[1]}, {label}")
            if label == "Total":
                totals[municipio] = values
                continue
            band = age_label(label)
            if band is None:
                raise SystemExit(f"cuba_census: {municipio[1]}: an age group this file does not "
                                 f"read: {label!r}")
            out[municipio].append((band[0], band[1], values[1], values[2]))
    expected = {(p, m) for p, ms in municipios.items() for m in ms}
    if set(out) != expected:
        raise SystemExit(f"cuba_census: Table 5 lacks {sorted(expected - set(out))} and has "
                         f"{sorted(set(out) - expected)} that Table 1 does not")
    for unit, groups in out.items():
        lows = [g[0] for g in groups]
        if lows != list(range(0, 90, 5)) or groups[-1][1] is not None:
            raise SystemExit(f"cuba_census: {unit[1]}'s age groups start at {lows}")
        men, women = sum(g[2] for g in groups), sum(g[3] for g in groups)
        table_1 = municipios[unit[0]][unit[1]]
        if (men, women) != (table_1[1], table_1[2]) or totals.get(unit, [None])[0] != table_1[0]:
            raise SystemExit(f"cuba_census: {unit[1]}'s age groups make {men:,} men and "
                             f"{women:,} women; Table 1 has {table_1[1]:,} and {table_1[2]:,}")
    log("  Table 5: all 168 municipios, every one's eighteen age groups making Table 1's men "
        "and women")
    return out


def colour_table(texts: list[str]) -> tuple[dict[str, dict[str, list[int]]], dict[str, list[int]]]:
    """The 2012 table: {province: {municipio: [total, white, black, mulatto]}}, and the provinces."""
    municipios, provinces, national, rows = by_province(texts, 4, colours_error, trailing_shares=4)
    for label, values, printed in rows:
        for count, share in zip(values, printed):
            if values[0] and abs(100 * count / values[0] - share) > 0.051:
                raise SystemExit(f"cuba_census: 2012: {label}: {count:,} of {values[0]:,} is not "
                                 f"the {share}% printed beside it")
    check_sums(municipios, provinces, national, NATIONAL_2012, "2012")
    log(f"  2012 colour table: 16 provinces and 168 municipios making {NATIONAL_2012:,}; every "
        "row's colours make its total and its printed shares")
    return municipios, provinces


def figures(values: list[int], groups: list[tuple[int, int | None, int]]) -> dict[str, Any]:
    """A unit's population, median age and sex ratio from its Table 1 row and age groups."""
    total, men, women = values[:3]
    return {
        "population": measure(total, unit="people", year=ESTUDIOS_YEAR,
                              source=ESTUDIOS_SOURCE),
        "median_age": measure(grouped_median(groups), unit="years", year=ESTUDIOS_YEAR,
                              source=ESTUDIOS_SOURCE),
        "median_age_note": (
            "Interpolated within the five-year age group that holds the middle person, from "
            "ONEI's count of the population by five-year age group at 31 December 2024."),
        "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                             year=ESTUDIOS_YEAR, source=ESTUDIOS_SOURCE),
    }


def colour_fields(values: list[int]) -> dict[str, Any]:
    total, *counts = values
    return {
        "ethnicity": shares(dict(zip(COLOURS, counts))),
        "ethnicity_year": COLOUR_YEAR,
        "ethnicity_note": (
            "Skin colour (color de la piel) as the 2012 Population and Housing Census recorded "
            f"it for everyone counted -- {total:,} people here -- in its three categories: "
            "white (blanca), black (negra), and mulatto or mestizo (mulata o mestiza). Cuba's "
            "census asks no other identity question."),
    }


def sources() -> list[dict[str, Any]]:
    return [{"field": "population/median age/sex ratio", "name": ESTUDIOS_SOURCE,
             "url": WAYBACK.format(stamp=ESTUDIOS_STAMP, url=ESTUDIOS), "year": ESTUDIOS_YEAR},
            {"field": "ethnicity", "name": COLOUR_SOURCE,
             "url": WAYBACK.format(stamp=COLOUR_STAMP, url=COLOUR), "year": COLOUR_YEAR}]


def province_groups(ages: dict[tuple[str, str], list[tuple[int, int | None, int, int]]],
                    province: str) -> list[tuple[int, int | None, int]]:
    """A province's age groups: the sum of its municipios'."""
    groups: dict[tuple[int, int | None], int] = {}
    for (p, _), bands in ages.items():
        if p == province:
            for low, high, men, women in bands:
                groups[(low, high)] = groups.get((low, high), 0) + men + women
    return [(low, high, n) for (low, high), n in sorted(groups.items(), key=lambda g: g[0][0])]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    texts = pdf_pages(ESTUDIOS, ESTUDIOS_STAMP)
    municipios, provinces = population_table(carrying(texts, TABLE_1))
    ages = age_table(carrying(texts, TABLE_5), municipios)
    colour_m, colour_p = colour_table(carrying(pdf_pages(COLOUR, COLOUR_STAMP), COLOUR_TABLE))
    log(f"  {len(DISCREPANCIES)} printed rows miss their own sums by a person, as published: "
        + "; ".join(DISCREPANCIES))

    admin1 = json.loads((SITE / "admin1" / "CUB.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CUB.units.json").read_text())
    first = {fold(u["name"]): u for u in admin1}

    def map_province(name: str) -> str:
        return fold(PROVINCES.get(name, name))

    def shape_of(province: str) -> dict[str, Any]:
        shape = first.get(map_province(province))
        if shape is None:
            raise SystemExit(f"cuba_census: province {province!r} has no polygon")
        return shape

    colour_by_province = {map_province(p): v for p, v in colour_p.items()}
    colour_by_unit = {(map_province(p), fold(MUNICIPIOS.get(m, m))): v
                      for p, ms in colour_m.items() for m, v in ms.items()}
    missing_2012 = sorted({map_province(p) for p in provinces} - set(colour_by_province))
    missing_2012 += sorted(f"{m} ({p})" for p, ms in municipios.items() for m in ms
                           if (map_province(p), fold(MUNICIPIOS.get(m, m))) not in colour_by_unit)
    if missing_2012:
        raise SystemExit(f"cuba_census: units of 2024 with no 2012 row: {missing_2012}")

    records = []
    for province, values in provinces.items():
        shape = shape_of(province)
        records.append(record(
            f"CUB-ONEI-{fold(province)}", shape["name"], level="admin1", parent="CUB",
            country="CUB", match_by="shape_id", shape_id=shape["id"],
            aliases=[province] if province != shape["name"] else [],
            **figures(values, province_groups(ages, province)),
            **colour_fields(colour_by_province[map_province(province)]), sources=sources()))

    parents = {u["id"]: u["name"] for u in admin1}
    units = {f"{fold(p)}-{fold(m)}": (m, shape_of(p)["name"])
             for p, ms in municipios.items() for m in ms}
    bound, missing = bind(units, admin2, parents, MUNICIPIOS)
    log(f"  {len(bound)} municipios bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    labels = {s["id"]: s["name"] for s in admin2}
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no municipio: {unbound}")
    for province, ms in municipios.items():
        for name, values in ms.items():
            code = f"{fold(province)}-{fold(name)}"
            sid = bound.get(code)
            if sid is None:
                continue
            groups = [(lo, hi, men + women) for lo, hi, men, women in ages[(province, name)]]
            records.append(record(
                f"CUB-ONEI-{code}", labels[sid], level="admin2", parent="CUB", country="CUB",
                parent_name=shape_of(province)["name"], match_by="shape_id", shape_id=sid,
                aliases=[name] if name != labels[sid] else [],
                **figures(values, groups),
                **colour_fields(colour_by_unit[(map_province(province),
                                                fold(MUNICIPIOS.get(name, name)))]),
                sources=sources()))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
