#!/usr/bin/env python3
"""Indonesia: median age and sex ratio from two provinces' civil registries.

BPS answers this project's reader 403 on every host it owns, its key-only
API has no key here, and Dukcapil's national dashboards time out
(docs/SOURCES.md, "Indonesia: what BPS's refusal left reachable"), so no
census or projection table by age reaches any Indonesian polygon. Two
provinces publish their civil register's age structure on their own CKAN
portals, in the layout of Dukcapil's consolidated data (``STRUKTUR UMUR``):
one row for the province and one per kabupaten and kota, each with its
Kemendagri code, and men (``L``/``LK``), women (``P``/``PR``) and both
(``JML``) in five-year groups from 00-04 to an open >75:

* **West Sumatra** -- *Buku Data Kependudukan Semester II Tahun 2023*, table
  STRUKTUR UMUR, by the province's Dinas Kependudukan dan Pencatatan Sipil,
  on ``data.sumbarprov.go.id``: the province and its 19.
* **Bengkulu** -- *Jumlah Penduduk Provinsi Bengkulu Berdasarkan Kelompok
  Usia Semester I Tahun 2026*, on ``data.bengkuluprov.go.id``: the province
  and its 10.

These are registered residents (the civil register at the end of the
semester), not a census count; every record says so. The median is
interpolated within the five-year group holding the middle person; the sex
ratio is men per 100 women. No population is written: the map's head counts
for these units come from elsewhere and are not displaced by a register's.

**Binding.** A kabupaten or kota binds to the drawn polygon of its name
inside its province's polygon (``fold`` equality, the register's
``SAWAHLUNTO`` and the boundary file's ``Sawah Lunto`` alike); its code
must sit under the province's. Every row binds one polygon and every
polygon of the province binds one row, except the shapes that are not
regencies (``NOT_REGENCIES``: the boundary file's lake shapes).

**Checks**, each a refusal: in every row and group men and women make both;
the groups run from 0 without a gap to the open top; the kabupaten and kota
make the province's row in every group and sex.

Usage:
    python -m scripts.fetch_census.indonesia_registry_age
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any, NamedTuple

from ._shared import PROCESSED, http_get, log, record, write_json
from .sea_common import age_sex, check_runs, drawn, fold, grouped

OUT = "indonesia_registry_age.json"
LICENCE = "Open government data of the province, published on its Satu Data portal"
HEADER = re.compile(r"^\s*(?P<band>>?\s*\d{1,2}(?:\s*-\s*\d{1,2})?)\s*\(\s*(?P<sex>LK|L|PR|P|JML|JM)"
                    r"\w*\s*\)?\s*$", re.IGNORECASE)
SEX = {"l": "M", "lk": "M", "p": "F", "pr": "F", "jml": "T", "jm": "T"}
# Drawn second-level shapes that are water, not regencies.
NOT_REGENCIES = frozenset({"danau"})


class Source(NamedTuple):
    key: str
    province: str          # the map's first-level name
    code: str              # the Kemendagri province code
    url: str
    page: str
    year: int
    period: str
    title: str


SOURCES = (
    Source("sumbar", "West Sumatra", "13",
           "https://data.sumbarprov.go.id/dataset/76470dbf-cddc-46bd-90f1-966f5a428aa1"
           "/resource/e73c6550-30a1-45e3-abf3-0fcc7c285289/download/struktur-umur.xlsx",
           "https://data.sumbarprov.go.id/dataset/"
           "buku-data-kependudukan-semester-ii-tahun-2023-prov-sumatera-barat",
           2023, "the end of the second half of 2023",
           "Dinas Kependudukan dan Pencatatan Sipil Provinsi Sumatera Barat, Buku Data "
           "Kependudukan Semester II Tahun 2023, tabel Struktur Umur"),
    Source("bengkulu", "Bengkulu", "17",
           "https://data.bengkuluprov.go.id/dataset/90762429-4dea-4c0d-9edf-7e51256ddfdd"
           "/resource/09b5f2b5-c81a-41b4-951f-9756399ef8e3/download/"
           "struktur-umur-semester-i-2026.xlsx",
           "https://data.bengkuluprov.go.id/dataset/"
           "jumlah-penduduk-provinsi-bengkulu-berdasarkan-kelompok-usia-semester-i-tahun-2026",
           2026, "the end of the first half of 2026",
           "Pemerintah Provinsi Bengkulu, Jumlah Penduduk Provinsi Bengkulu Berdasarkan "
           "Kelompok Usia Semester I Tahun 2026 (the civil register's age structure)"),
)


def code_of(cell: Any) -> str:
    """A Kemendagri code as printed: 13, 13.01 -- and 13.1, a float for 13.10."""
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return str(int(cell)) if float(cell).is_integer() else f"{float(cell):.2f}"
    return str(cell or "").strip()


def band_of(label: str) -> tuple[int, int | None]:
    text = label.replace(" ", "")
    if text.startswith(">"):
        return int(text[1:]), None
    low, _, high = text.partition("-")
    return int(low), int(high)


def read(grid: list[list[Any]], where: str) -> list[dict[str, Any]]:
    """Each row: its code, name and {band: {M, F, T}}, checked."""
    head = next((i for i, row in enumerate(grid)
                 if [str(c or "").strip().upper() for c in row[:2]] == ["NO", "WILAYAH"]), None)
    if head is None:
        raise SystemExit(f"indonesia_registry_age: {where}: no NO / WILAYAH header row")
    names = [str(c or "").strip() for c in grid[head]]
    code_col = next((i for i, n in enumerate(names) if n.upper() == "KODE"), None)
    cols: dict[tuple[int, int | None], dict[str, int]] = {}
    for i, name in enumerate(names):
        if m := HEADER.match(name):
            cols.setdefault(band_of(m.group("band")), {})[SEX[m.group("sex").lower()]] = i
    if code_col is None or not cols or any(set(v) != {"M", "F", "T"} for v in cols.values()):
        raise SystemExit(f"indonesia_registry_age: {where}: a header it cannot read: {names}")
    check_runs([(lo, hi, 0) for lo, hi in cols], where)
    rows = []
    for row in grid[head + 1:]:
        code = code_of(row[code_col] if code_col < len(row) else None)
        if not code:
            continue
        name = str(row[1] or "").strip()
        groups = {}
        for b, at in cols.items():
            m, f, t = (row[at[s]] if at[s] < len(row) else None for s in "MFT")
            if any(not isinstance(v, (int, float)) for v in (m, f, t)):
                raise SystemExit(f"indonesia_registry_age: {where}: {name} {b}: blank cells")
            if m + f != t:
                raise SystemExit(f"indonesia_registry_age: {where}: {name} {b}: {m:,} men and "
                                 f"{f:,} women make {m + f:,}, against {t:,}")
            groups[b] = {"M": m, "F": f, "T": t}
        rows.append({"code": code, "name": name, "groups": groups})
    return rows


def check_province(rows: list[dict[str, Any]], source: Source) -> tuple[dict[str, Any],
                                                                         list[dict[str, Any]]]:
    """The province's row, and its kabupaten and kota, which must make it."""
    top = [r for r in rows if r["code"] == source.code]
    kids = [r for r in rows if r["code"].startswith(source.code + ".")]
    other = [r["code"] for r in rows if r not in top and r not in kids]
    if len(top) != 1 or not kids or other:
        raise SystemExit(f"indonesia_registry_age: {source.key}: {len(top)} province rows, "
                         f"{len(kids)} under it, other codes {other}")
    for b, sexes in top[0]["groups"].items():
        for s, v in sexes.items():
            made = sum(k["groups"][b][s] for k in kids)
            if made != v:
                raise SystemExit(f"indonesia_registry_age: {source.key}: the kabupaten and kota "
                                 f"make {made:,} in {b} {s}, against the province's {v:,}")
    total = sum(g["T"] for g in top[0]["groups"].values())
    log(f"  {source.key}: {len(kids)} kabupaten and kota make the province's {total:,} in "
        f"every group and sex")
    return top[0], kids


def bind(kids: list[dict[str, Any]], region: dict[str, Any], admin2: list[dict[str, Any]],
         source: Source) -> dict[str, dict[str, Any]]:
    """Polygon id -> its row, one to one inside the province's polygon."""
    shapes = [s for s in admin2 if s["parent"] == region["id"]
              and fold(s["name"]) not in NOT_REGENCIES]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for s in shapes:
        by_name.setdefault(fold(s["name"]), []).append(s)
    out: dict[str, dict[str, Any]] = {}
    for row in kids:
        hits = by_name.get(fold(row["name"]), [])
        if len(hits) != 1 or hits[0]["id"] in out:
            raise SystemExit(f"indonesia_registry_age: {source.key}: {row['name']} "
                             f"({row['code']}) names {len(hits)} polygons of "
                             f"{sorted(s['name'] for s in shapes)}")
        out[hits[0]["id"]] = row
    left = sorted(s["name"] for s in shapes if s["id"] not in out)
    if left:
        raise SystemExit(f"indonesia_registry_age: {source.key}: polygons with no row: {left}")
    return out


def fields(row: dict[str, Any], source: Source, whose: str) -> dict[str, Any]:
    groups = [(lo, hi, g["T"]) for (lo, hi), g in row["groups"].items()]
    men = sum(g["M"] for g in row["groups"].values())
    women = sum(g["F"] for g in row["groups"].values())
    said = (f"from the civil register's count of {whose} by five-year age group and sex at "
            f"{source.period}: residents on the register, not a census")
    median = grouped(groups)
    if median is None or not women:
        raise SystemExit(f"indonesia_registry_age: {whose}: no median below the open group, "
                         f"or no women")
    return age_sex(median=median, men=men, women=women, year=source.year,
                   source=source.title,
                   median_note=(f"Interpolated within the five-year age group that holds the "
                                f"middle person, {said}."),
                   ratio_note=f"Males per 100 females {said}.")


def build(source: Source, grid: list[list[Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = read(grid, source.key)
    top, kids = check_province(rows, source)
    regions = [u for u in admin1 if u["name"] == source.province]
    if len(regions) != 1:
        raise SystemExit(f"indonesia_registry_age: {len(regions)} polygons named "
                         f"{source.province!r}")
    cite = [{"field": "median_age/sex_ratio", "name": source.title, "url": source.page,
             "year": source.year, "license": LICENCE}]
    out = [record(f"IDN-REG-{source.key}", source.province, level="admin1", parent="IDN",
                  country="IDN", match_by="shape_id", shape_id=regions[0]["id"],
                  sources=cite, **fields(top, source, f"the province ({top['name'].title()})"))]
    names = {s["id"]: s["name"] for s in admin2}
    for sid, row in sorted(bind(kids, regions[0], admin2, source).items(),
                           key=lambda kv: names[kv[0]]):
        out.append(record(f"IDN-REG-{source.key}-{row['code']}", names[sid], level="admin2",
                          parent="IDN", country="IDN", match_by="shape_id", shape_id=sid,
                          sources=cite,
                          **fields(row, source, f"{row['name'].title()} ({row['code']})")))
    meds = sorted(r["median_age"]["value"] for r in out)
    log(f"  {source.key}: {len(out)} records; median {meds[0]}-{meds[-1]}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl
    log("indonesia_registry_age: two provinces' civil-register age structure")
    admin1, admin2 = drawn("IDN", "admin1"), drawn("IDN", "admin2")
    records: list[dict[str, Any]] = []
    for source in SOURCES:
        book = openpyxl.load_workbook(io.BytesIO(http_get(source.url, binary=True, cache=False)),
                                      read_only=True, data_only=True)
        grid = [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]
        book.close()
        records += build(source, grid, admin1, admin2)
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
