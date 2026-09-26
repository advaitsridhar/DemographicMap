#!/usr/bin/env python3
"""Ecuador's provinces and cantons: median age and sex ratio, 2022 census.

The same INEC workbook ecuador_census.py reads for the count
("01_2022_CPV_Estructura_poblacional.xlsx", from the Internet Archive's
capture, since INEC's host refuses an automated reader) has, in sheet 2.1,
everyone by sex and five-year age group for every province, canton and
parish. A province's rows name "Total <province>" as their canton; a canton's
name "Total <canton>" as their parish.

- **sex ratio**: men per 1,000 women, from the unit's own total row;
- **median age**: interpolated within the five-year group holding the middle
  person, the open-ended "85 o más" never holding it.

Every unit's age groups must add up to its total row, men and women
separately, and every province's cantons must add up to the province, before
anything is written. Units are named as ecuador_census.py names them, so the
two files reach the same shapes.

INEC's "2022_CPV_Autoidentificacion_Cultura" workbook (an .xls, whatever its
name says, read from the Archive's January 2025 capture) gives two more:

- **ethnicity**, sheet 1.1: how everyone identifies "according to their
  culture and customs" -- indigenous, Afro-Ecuadorian, Black, mulatto,
  montubio, mestizo, white, other;
- **language**, sheet 5.1: which languages everyone aged 1 or over speaks,
  as combinations. Anyone who speaks an indigenous language, alone or with
  another, is counted under indigenous languages, as Mexico's are; anyone
  else who speaks Spanish, under Spanish.

The same checks: every unit's categories make its total, and every
province's cantons make the province.

Usage:
    python -m scripts.fetch_census.ecuador_profile
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .cod_ps_age import grouped_median
from .ecuador_census import CAPTURE, ORIGINAL, YEAR, fetch_blob, fold
from common import slugify  # noqa: E402

OUT = PROCESSED / "ecuador_profile.json"
SHEET = "2.1"
SOURCE = ("INEC, Censo de Población y Vivienda 2022, Estructura poblacional, tabla 2.1 "
          "(población por sexo al nacer y grupos de edad)")
CULTURE = ("https://www.censoecuador.gob.ec/wp-content/uploads/2024/02/"
           "2022_CPV_Autoidentificacion_Cultura.xlsx")
CULTURE_CAPTURE = f"https://web.archive.org/web/20250114111544id_/{CULTURE}"
CULTURE_SOURCE = ("INEC, Censo de Población y Vivienda 2022, Autoidentificación y cultura, "
                  "tabla {table}")
# Header starts, as INEC prints them, and the map's label for each.
ETHNIC = (("Indigena", "Indigenous"), ("Indígena", "Indigenous"),
          ("Afroecuatoriano", "Afro-Ecuadorian"), ("Negra", "Black"), ("Mulata", "Mulatto"),
          ("Montubia", "Montubio"), ("Mestiza", "Mestizo"), ("Blanca", "White"),
          ("Otro", "Other"))
LANGUAGE = (("Solo idioma o lengua ind", "Indigenous languages"),
            ("Idioma o lengua ind", "Indigenous languages"),
            ("Solo castellano", "Spanish"), ("Castellano o español", "Spanish"),
            ("Solo idioma extranjero", "Foreign languages"),
            ("Idioma extranjero", "Foreign languages"),
            ("Solo lengua de señas", "Ecuadorian Sign Language"),
            ("Tres o más", "Three or more languages"), ("No habla", "Does not speak"))
BAND = re.compile(r"^De (\d+)-(\d+)$")
OPEN = re.compile(r"^(\d+) o más$")


def rows_of(blob: bytes) -> list[list[str]]:
    import io

    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return [["" if c is None else str(c).strip() for c in row]
            for row in book[SHEET].iter_rows(values_only=True)]


def units(rows: list[list[str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(province, canton or "") -> total row and age groups, by sex.

    Parishes are read past: the map draws cantons.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if len(row) < 8 or not row[7].replace(".", "").isdigit():
            continue
        province, canton, parish, label = row[1], row[2], row[3], row[4]
        if fold(province) == "total nacional":
            continue
        if fold(canton) == fold(f"Total {province}"):
            key = (province, "")
        elif fold(parish) == fold(f"Total {canton}"):
            key = (province, canton)
        else:
            continue
        unit = out.setdefault(key, {"total": None, "groups": []})
        men, women = int(float(row[6])), int(float(row[7]))
        if label.startswith("Total"):
            unit["total"] = (men, women)
        elif m := BAND.match(label):
            unit["groups"].append((int(m.group(1)), int(m.group(2)), men, women))
        elif m := OPEN.match(label):
            unit["groups"].append((int(m.group(1)), None, men, women))
        else:
            raise SystemExit(f"ecuador_profile: unread age group {label!r}")
    return out


def label_for(header: str, rules: tuple[tuple[str, str], ...]) -> str | None:
    for start, label in rules:
        if fold(header).startswith(fold(start)):
            return label
    return None


def composition_table(grid: list[list[str]], rules: tuple[tuple[str, str], ...],
                      what: str) -> dict[tuple[str, str], dict[str, Any]]:
    """(province, canton or "") -> total and counts under the map's labels.

    The category row is the one below "Número total de personas"; every one
    of its headers must be read, or the table is refused rather than a
    category silently dropped.
    """
    head = next(i for i, row in enumerate(grid)
                if any(fold(c).startswith("numero total") for c in row))
    total_col = next(j for j, c in enumerate(grid[head]) if fold(c).startswith("numero total"))
    columns = {}
    for j, header in enumerate(grid[head + 1]):
        if j <= total_col or not header.strip():
            continue
        label = label_for(header, rules)
        if label is None:
            raise SystemExit(f"ecuador_profile: {what}: unread category {header!r}")
        columns[j] = label
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in grid[head + 2:]:
        if len(row) <= total_col or not row[total_col].replace(".", "").isdigit():
            continue
        province, canton, area = row[1], row[2], row[3]
        if fold(province) == "total nacional":
            continue
        if fold(area) not in ("total", fold(f"Total {canton}"), fold(f"Total {province}")):
            continue
        key = (province, "") if fold(canton) == fold(f"Total {province}") else (province, canton)
        counts: dict[str, int] = defaultdict(int)
        for j, label in columns.items():
            counts[label] += int(float(row[j] or 0))
        total = int(float(row[total_col]))
        if sum(counts.values()) != total:
            raise SystemExit(f"ecuador_profile: {what}: {province} / {canton or '-'}: "
                             f"categories {sum(counts.values()):,} against {total:,}")
        out[key] = {"total": total, "counts": dict(counts)}
    provinces = {p for p, c in out if not c}
    for province in sorted(provinces):
        cantons = {c: v for (p, c), v in out.items() if p == province and c}
        for label in sorted(out[(province, "")]["counts"]):
            if sum(v["counts"].get(label, 0) for v in cantons.values()) != \
                    out[(province, "")]["counts"][label]:
                raise SystemExit(
                    f"ecuador_profile: {what}: {province}'s cantons do not make its {label}: "
                    f"{sum(v['counts'].get(label, 0) for v in cantons.values()):,} against "
                    f"{out[(province, '')]['counts'][label]:,}; totals "
                    f"{sum(v['total'] for v in cantons.values()):,} against "
                    f"{out[(province, '')]['total']:,}; cantons read: "
                    + ", ".join(f"{c} {v['total']:,}" for c, v in sorted(cantons.items())))
    log(f"  {what}: {len(provinces)} provinces and {len(out) - len(provinces)} cantons; "
        "every one's categories make its total, and every province's cantons make it")
    return out


def xls_grid(blob: bytes, sheet: str) -> list[list[str]]:
    """A sheet as text cells, whichever format the bytes turn out to be."""
    def text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()
    if blob[:2] == b"PK":
        import io

        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)[sheet]
        return [[text(v) for v in row] for row in ws.iter_rows(values_only=True)]
    import xlrd
    ws = xlrd.open_workbook(file_contents=blob).sheet_by_name(sheet)
    return [[text(ws.cell_value(r, c)) for c in range(ws.ncols)] for r in range(ws.nrows)]


def figures(unit: dict[str, Any], where: str) -> tuple[float, int]:
    if unit["total"] is None:
        raise SystemExit(f"ecuador_profile: {where} has no total row")
    men, women = unit["total"]
    groups = sorted(unit["groups"], key=lambda g: g[0])
    edge = 0
    for low, high, *_ in groups:
        if low != edge:
            raise SystemExit(f"ecuador_profile: {where}: ages jump from {edge} to {low}")
        edge = (high or 0) + 1
    if groups[-1][1] is not None:
        raise SystemExit(f"ecuador_profile: {where}: no open-ended last group")
    if (sum(g[2] for g in groups), sum(g[3] for g in groups)) != (men, women):
        raise SystemExit(f"ecuador_profile: {where}: age groups do not add up to the total")
    median = grouped_median([(low, high, m + w) for low, high, m, w in groups])
    if median is None:
        raise SystemExit(f"ecuador_profile: {where}: median in the open-ended group")
    return median, round(1000 * men / women)


def build(rows: list[list[str]], ethnicity: dict | None = None,
          language: dict | None = None) -> list[dict[str, Any]]:
    found = units(rows)
    ethnicity, language = ethnicity or {}, language or {}

    def extra(province: str, canton: str) -> dict[str, Any]:
        """The unit's compositions, found by folded name."""
        out: dict[str, Any] = {}
        for field, table, sheet, note in (
                ("ethnicity", ethnicity, "1.1",
                 "How each of the {total:,} people counted identifies, \"according to their "
                 "culture and customs\", as the 2022 census asked it."),
                ("language", language, "5.1",
                 "The languages each of the {total:,} people aged 1 or over speaks. Anyone "
                 "who speaks an indigenous language, alone or with Spanish or another, is "
                 "counted under indigenous languages; anyone else who speaks Spanish, under "
                 "Spanish.")):
            unit = next((v for (p, c), v in table.items()
                         if fold(p) == fold(province) and fold(c) == fold(canton)), None)
            if unit is None:
                continue
            out[field] = shares(unit["counts"])
            out[f"{field}_year"] = YEAR
            out[f"{field}_note"] = note.format(total=unit["total"])
            out.setdefault("sources", []).append(
                {"field": field, "name": CULTURE_SOURCE.format(table=sheet), "url": CULTURE,
                 "archived": CULTURE_CAPTURE})
        return out
    provinces = {p for p, c in found if not c}
    cantons: dict[str, list[str]] = defaultdict(list)
    for province, canton in found:
        if canton:
            cantons[province].append(canton)
    for province in provinces:
        total = found[(province, "")]["total"]
        summed = tuple(map(sum, zip(*(found[(province, c)]["total"] for c in cantons[province]))))
        if summed != total:
            raise SystemExit(f"ecuador_profile: {province}'s cantons make {summed}, not {total}")
    log(f"  {len(provinces)} provinces and {sum(map(len, cantons.values()))} cantons; "
        "every one's age groups make its total, and every province's cantons make it")
    cite = [{"field": "median_age/sex_ratio", "name": SOURCE, "url": ORIGINAL,
             "archived": CAPTURE}]
    note = ("Interpolated within the five-year age group that holds the middle person, from "
            "INEC's count of everyone by sex and age.")
    out = []
    for province in sorted(provinces):
        name = province.title() if province.isupper() else province
        median, ratio = figures(found[(province, "")], province)
        out.append(record(
            f"ECU-CEN-{slugify(name)}-AGE", name, level="admin1", parent="ECU", country="ECU",
            median_age={"value": median, "unit": "years", "year": YEAR, "source": SOURCE},
            median_age_note=note,
            sex_ratio={"value": ratio, "unit": "males_per_1000_females", "year": YEAR,
                       "source": SOURCE},
            **with_sources(cite, extra(province, ""))))
        for canton in sorted(cantons[province]):
            label = canton.title() if canton.isupper() else canton
            median, ratio = figures(found[(province, canton)], f"{province} / {canton}")
            out.append(record(
                f"ECU-CEN-{slugify(name)}-{slugify(label)}-AGE", label, level="admin2",
                parent="ECU", country="ECU", parent_name=name, aliases=[f"Cantón {label}"],
                median_age={"value": median, "unit": "years", "year": YEAR, "source": SOURCE},
                median_age_note=note,
                sex_ratio={"value": ratio, "unit": "males_per_1000_females", "year": YEAR,
                           "source": SOURCE},
                **with_sources(cite, extra(province, canton))))
    return out


def with_sources(cite: list[dict[str, Any]], fields: dict[str, Any]) -> dict[str, Any]:
    return {**fields, "sources": cite + fields.get("sources", [])}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    blob = fetch_blob(CAPTURE)
    log(f"  {CAPTURE}: {len(blob):,} bytes")
    culture = fetch_blob(CULTURE_CAPTURE)
    # The Archive serves this capture gzipped, as it was stored.
    if culture[:2] == b"\x1f\x8b":
        import gzip
        culture = gzip.decompress(culture)
    log(f"  {CULTURE_CAPTURE}: {len(culture):,} bytes")
    ethnicity = composition_table(xls_grid(culture, "1.1"), ETHNIC, "ethnicity (1.1)")
    language = composition_table(xls_grid(culture, "5.1"), LANGUAGE, "language (5.1)")
    write_json(OUT, build(rows_of(blob), ethnicity, language))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
