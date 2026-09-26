#!/usr/bin/env python3
"""Argentina: the 2022 census by province and department.

Argentina's 24 provinces and 527 departments had a population from Wikidata
and nothing else. INDEC's *Censo Nacional de Población, Hogares y Viviendas
2022, resultados definitivos* are published as workbooks, one per province
and table, each with a sheet for the province and one for every department
(partido in Buenos Aires, comuna in the capital):

- est_c1: everyone counted in 2022, by department, on one sheet;
- est_c4: everyone by sex and single year of age;
- est_c6: INDEC's own median age by department, rounded to a whole year,
  which is only used here to check the median computed from est_c4;
- poblacion_indigena_c1: who recognises themselves as indigenous or as
  descended from an indigenous people, by sex and age;
- poblacion_indigena_c7: whether they speak or understand their people's
  language;
- poblacion_indigena_c9: which people, for the province only;
- poblacion_afrodescendiente_c7: who recognises themselves as
  Afro-descendant or as having Black or African ancestors, by department.

**Median age** is interpolated within the single year of age that holds the
middle person; INDEC's rounded median must agree to within a year.

**Ethnicity** is two questions, asked of everyone in a private dwelling:
indigenous self-recognition, and Afro-descendant. Someone may answer yes to
both and INDEC publishes no cross of the two, so, as for Chile, both are
shown and the remainder is the private-dwelling population less both counts.
The census asks nothing about European or mestizo ancestry. Which people is
published for the province only, so a department's indigenous line is one
line. The share of indigenous people who speak or understand their people's
language is given in the note; it is not a language composition (the
question is asked of nobody else), and language stays the documented gap
the collection policy states.

**Binding.** The boundary file files some departments under the wrong
province -- Entre Ríos's under Buenos Aires, which it draws as one polygon
with them, ten Greater Buenos Aires partidos under the capital, Santiago del
Estero's Rivadavia under Córdoba -- so a department is bound to its polygon
by shape id: by name within its province where that is unique; then by a
name no other unbound polygon or department shares; then, for a name
several share, by the one polygon that lies among its province's other
departments. Anything left is reported and left out, never guessed.

Usage:
    python -m scripts.fetch_census.argentina_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .cod_ps_age import grouped_median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_tls import verified_opener  # noqa: E402

OUT = "argentina_census.json"
YEAR = 2022
HOST = "censo.gob.ar"
UPLOADS = f"https://{HOST}/wp-content/uploads/"
PAGE = f"https://{HOST}/index.php/datos_definitivos_{{page}}/"
SOURCE = "INDEC, Censo Nacional de Población, Hogares y Viviendas 2022, resultados definitivos ({table})"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}
TIMEOUT = 120
SITE = PROCESSED.parent.parent / "site" / "data"

# INDEC's order of the provinces, which numbers its files and sheets; its
# two-digit code; the slug in its file names; its landing page; its name; and
# the boundary file's name for it (None: not drawn at this level). The landing
# pages' names are the portal's own, from its index of provinces.
PROVINCES = [
    (1, "02", "caba", "caba", "Ciudad Autónoma de Buenos Aires", "Ciudad Autónoma de Buenos Aires"),
    (2, "06", "buenosaires", "bsas", "Buenos Aires", "Buenos Aires"),
    (3, "10", "catamarca", "catamarca", "Catamarca", "Catamarca"),
    (4, "22", "chaco", "chaco", "Chaco", "Chaco"),
    (5, "26", "chubut", "chubut", "Chubut", "Chubut"),
    (6, "14", "cordoba", "cordoba", "Córdoba", "Córdoba"),
    (7, "18", "corrientes", "corrientes", "Corrientes", "Corrientes"),
    (8, "30", "entrerios", "entre_rios", "Entre Ríos", None),
    (9, "34", "formosa", "formosa", "Formosa", "Formosa"),
    (10, "38", "jujuy", "jujuy", "Jujuy", "Jujuy"),
    (11, "42", "lapampa", "lapampa", "La Pampa", "La Pampa"),
    (12, "46", "larioja", "larioja", "La Rioja", "La Roja"),
    (13, "50", "mendoza", "mendoza", "Mendoza", "Mendoza"),
    (14, "54", "misiones", "misiones", "Misiones", "Misiones"),
    (15, "58", "neuquen", "neuquen", "Neuquén", "Neuquén"),
    (16, "62", "rionegro", "rionegro", "Río Negro", "Río Negro"),
    (17, "66", "salta", "salta", "Salta", "Salta"),
    (18, "70", "sanjuan", "sanjuan", "San Juan", "San Juan"),
    (19, "74", "sanluis", "sanluis", "San Luis", "San Luis"),
    (20, "78", "santacruz", "santa_cruz", "Santa Cruz", "Santa Cruz"),
    (21, "82", "santafe", "santafe", "Santa Fe", "Santa Fe"),
    (22, "86", "santiago", "santiago_del_estero", "Santiago del Estero", "Santiago del Estero"),
    (23, "94", "tierradelfuego", "tdf",
     "Tierra del Fuego, Antártida e Islas del Atlántico Sur", "Tierra del Fuego"),
    (24, "90", "tucuman", "tucuman", "Tucumán", "Tucumán"),
]
# (topic in the file name, table number): the upload folders to try, in order,
# when a province's landing page does not list the file.
TABLES = {
    ("est", 1): ("2023/11", "2023/12"),
    ("est", 4): ("2023/11", "2023/12"),
    ("est", 6): ("2023/11", "2023/12"),
    ("poblacion_indigena", 1): ("2024/03", "2024/04", "2024/02"),
    ("poblacion_indigena", 7): ("2024/03", "2024/04", "2024/02"),
    ("poblacion_indigena", 9): ("2024/03", "2024/04", "2024/02"),
    ("poblacion_afrodescendiente", 7): ("2024/03", "2024/04", "2024/02"),
}
TABLE_NAMES = {
    ("est", 1): "cuadro 1, total de población por departamento",
    ("est", 4): "cuadro 4, población por sexo y edad",
    ("poblacion_indigena", 1): "población indígena, cuadro 1",
    ("poblacion_indigena", 9): "población indígena, cuadro 9, por pueblo",
    ("poblacion_afrodescendiente", 7): "población afrodescendiente, cuadro 7",
}
# INDEC's names for the peoples -> the map's. Anything not here keeps INDEC's
# spelling; the group tree files it.
PEOPLES = {
    "Qom/Toba": "Qom (Toba)", "Moqoit/Mocoví": "Mocoví", "Chulupí/Nivaclé": "Nivaclé",
    "Wichi": "Wichí", "Sin Información": "Indigenous (people not stated)",
}
INDIGENOUS_DEPT = "Indigenous (people not published)"
AFRO = "Afro-descendant"
REST = "Mestizo or white (neither indigenous nor Afro-descendant)"
# INDEC's spelling -> the boundary file's, where they differ by more than
# accents and punctuation.
ALIASES: dict[str, str] = {}
SINGLE = re.compile(r"^(\d+)$")
OPEN = re.compile(r"^(\d+) y más$")
BAND = re.compile(r"^(\d+)-(\d+)$")
# "Cuadro 4.6.1", and Buenos Aires's "Cuadro4.2.1"; its province sheet is
# "Cuadro4.2.0". A "bis" sheet is a second layout of the same figures.
CUADRO = re.compile(r"^Cuadro\s*(\d+)\.(\d+)(?:\.(\d+))?$")
# A misread sheet or column misses INDEC's median by decades; its own figure
# is a whole year computed its own way, and in a department of a thousand
# people the two can differ by a couple of years. So a unit more than five
# years out stops the run, units more than two out are listed, and how often
# each rounding reproduces INDEC's figure exactly is logged.
MEDIAN_LIMIT = 5.0
MEDIAN_NOTE = 2.0
FIVE_YEAR: dict[str, float | None] = {}


def fold(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", str(name or ""))
    return "".join(c for c in stripped.lower() if c.isalnum() and not unicodedata.combining(c))


def number(value: Any) -> int | None:
    """A count; INDEC's "-" is zero and "///" is not applicable."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).strip()
    if text == "-":
        return 0
    if not text or text.startswith("///"):
        return None
    try:
        return int(round(float(text.replace(" ", ""))))
    except ValueError:
        return None


class Fetcher:
    """censo.gob.ar's files, found from its landing pages or its upload folders."""

    def __init__(self) -> None:
        # The portal omits its intermediate certificate; the opener completes
        # the chain from the leaf's own AIA extension and still verifies it.
        self.opener = verified_opener(HOST)
        self.links: dict[str, list[str]] = {}

    def get(self, url: str, *, quiet: bool = False) -> bytes | None:
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with self.opener.open(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code == 404 or quiet:
                return None
            raise

    def page_links(self, page: str) -> list[str]:
        if page not in self.links:
            body = self.get(PAGE.format(page=page), quiet=True)
            text = body.decode("utf-8", "replace") if body else ""
            self.links[page] = sorted(set(re.findall(r'href="([^"]+\.xlsx)"', text)))
            log(f"  {page}: landing page {'lists ' + str(len(self.links[page])) + ' workbooks' if body else 'not found'}")
        return self.links[page]

    def workbook(self, index: int, slug: str, page: str, topic: str, table: int
                 ) -> tuple[Any, str]:
        import openpyxl
        stem = re.compile(rf"c2022_[a-z]+_{topic}_c{table}_{index}\.xlsx$")
        candidates = [u for u in self.page_links(page) if stem.search(u)]
        candidates += [f"{UPLOADS}{folder}/c2022_{slug}_{topic}_c{table}_{index}.xlsx"
                       for folder in TABLES[(topic, table)]]
        for url in dict.fromkeys(candidates):
            blob = self.get(url)
            if blob and blob[:2] == b"PK":
                return openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                              data_only=True), url
        raise SystemExit(f"argentina_census: no {topic} table {table} for {slug}; tried "
                         + ", ".join(dict.fromkeys(candidates)))


def cuadros(book: Any) -> dict[tuple[int, int | None], list[list[Any]]]:
    """Each "Cuadro t.p[.d]" sheet's rows, keyed (p, d); d is None for the province."""
    out = {}
    for name in book.sheetnames:
        clean = re.sub(r"\s+", " ", name.replace("\xa0", " ")).strip()
        m = CUADRO.match(clean)
        if not m:
            continue
        key = (int(m.group(2)), int(m.group(3)) if m.group(3) and int(m.group(3)) else None)
        if key in out:
            raise SystemExit(f"argentina_census: two sheets for {key} ({name!r})")
        out[key] = [list(r) for r in book[name].iter_rows(values_only=True)]
    return out


def title(rows: list[list[Any]]) -> str:
    for row in rows[:6]:
        text = str(row[0] if row and row[0] is not None else "").strip()
        if text.startswith("Cuadro"):
            return text
    return ""


def label(value: Any) -> str:
    """A cell as a row label; an age stored as 5.0 reads as "5"."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "" if value is None else str(value).strip()


def labelled(rows: list[list[Any]], column: int = 0) -> list[tuple[str, list[int | None]]]:
    """(label, the numbers after it) for each row with a label and numbers.

    Empty cells are skipped: INDEC leaves a blank column between a label and
    its figures in some tables and not in others.
    """
    out = []
    for row in rows:
        if column >= len(row) or not label(row[column]):
            continue
        numbers = [number(c) for c in row[column + 1:] if c not in (None, "")]
        if any(n is not None for n in numbers):
            out.append((label(row[column]), numbers))
    return out


def sheet(sheets: dict[tuple[int, int | None], list[list[Any]]], index: int, what: str
          ) -> list[list[Any]]:
    """The province's own sheet of a workbook."""
    if (index, None) not in sheets:
        raise SystemExit(f"argentina_census: {what}: no province sheet {index} among "
                         f"{sorted(k for k in sheets if k[1] is None)}")
    return sheets[(index, None)]


def total_row(rows: list[list[Any]], what: str) -> list[int | None]:
    for text, numbers in labelled(rows):
        if text == "Total":
            return numbers
    raise SystemExit(f"argentina_census: {what}: no Total row")


def coded(rows: list[list[Any]], repeats: dict[str, list[list[int | None]]] | None = None
          ) -> dict[str, tuple[str, list[int | None]]]:
    """Rows keyed by INDEC code: {code: (name, numbers after the name)}.

    The first row with a code is kept. Buenos Aires's table repeats the
    province's code on its subtotals (the 24 partidos of Greater Buenos Aires,
    the interior); ``repeats`` collects every row's figures by code, so the
    caller can find which of them its departments make.
    """
    out = {}
    for row in rows:
        code = str(row[0] if row and row[0] is not None else "").strip()
        if code.endswith(".0"):
            code = code[:-2]
        if not code.isdigit():
            continue
        name = str(row[1] if len(row) > 1 and row[1] is not None else "").strip()
        # Positions, not a filtered list: a department with no 2010 figure
        # must not shift its 2022 one into the 2010 column.
        key = code.zfill(2) if len(code) <= 2 else code.zfill(5)
        figures = [number(c) for c in row[2:]]
        if repeats is not None:
            repeats.setdefault(key, []).append(figures)
        out.setdefault(key, (name, figures))
    return out


def ages(rows: list[list[Any]], what: str) -> tuple[int, int, float | None]:
    """Women, men and the interpolated median from a sex-by-single-year sheet."""
    header_seen = False
    singles: list[tuple[int, int, int]] = []
    opened: tuple[int, int] | None = None
    bands: list[tuple[int, int, int]] = []
    women = men = None
    for text, numbers in labelled(rows):
        if text == "Total":
            header_seen = True
            total, women, men = numbers[0], numbers[1], numbers[2]
            if women + men != total:
                raise SystemExit(f"argentina_census: {what}: women {women:,} and men {men:,} "
                                 f"make {women + men:,}, not {total:,}")
            continue
        if not header_seen:
            continue
        people = numbers[0]
        if (m := SINGLE.match(text)):
            singles.append((int(m.group(1)), int(m.group(1)), people))
        elif (m := OPEN.match(text)):
            opened = (int(m.group(1)), people)
        elif (m := BAND.match(text)):
            bands.append((int(m.group(1)), int(m.group(2)), people))
    if women is None or opened is None or not singles:
        raise SystemExit(f"argentina_census: {what}: no Total row, single years or open group")
    expected = list(range(0, opened[0]))
    if [a for a, _, _ in singles] != expected:
        raise SystemExit(f"argentina_census: {what}: single years do not run 0-{opened[0] - 1}")
    counted = sum(n for _, _, n in singles) + opened[1]
    if counted != women + men:
        raise SystemExit(f"argentina_census: {what}: ages add up to {counted:,}, "
                         f"not {women + men:,}")
    by_age = {a: n for a, _, n in singles}
    for low, high, people in bands:
        if sum(by_age.get(a, 0) for a in range(low, high + 1)) != people:
            raise SystemExit(f"argentina_census: {what}: ages {low}-{high} do not make their group")
    median = grouped_median([*singles, (opened[0], None, opened[1])])
    FIVE_YEAR[what] = grouped_median([*bands, (opened[0], None, opened[1])])
    return women, men, median


def dept_sheet(sheets: dict[tuple[int, int | None], list[list[Any]]], index: int,
               departments: dict[str, str], what: str) -> dict[str, list[list[Any]]]:
    """Department sheets keyed by INDEC code, each found by the name in its title."""
    out: dict[str, list[list[Any]]] = {}
    for (p, d), rows in sheets.items():
        if p != index or d is None:
            continue
        text = fold(title(rows))
        hits = []
        for code, name in departments.items():
            key = fold(name)
            if any(word + key in text for word in ("departamento", "partido", "comuna")) or (
                    key.startswith("comuna") and key in text):
                hits.append((len(key), code))
        if not hits:
            raise SystemExit(f"argentina_census: {what}: sheet {index}.{d} ({title(rows)!r}) "
                             f"names no department")
        hits.sort(reverse=True)
        if len(hits) > 1 and hits[0][0] == hits[1][0]:
            raise SystemExit(f"argentina_census: {what}: sheet {index}.{d} names two departments")
        code = hits[0][1]
        if code in out:
            raise SystemExit(f"argentina_census: {what}: two sheets for {departments[code]}")
        out[code] = rows
    missing = sorted(set(departments) - set(out))
    if missing:
        raise SystemExit(f"argentina_census: {what}: no sheet for "
                         + ", ".join(departments[c] for c in missing[:8]))
    return out


def bind(departments: dict[str, tuple[str, str]], shapes: list[dict[str, Any]],
         parents: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """INDEC department code -> the map's shape id, by name, then name, then place.

    ``departments`` is {code: (name, province map name or "")}; ``parents``
    the map's admin1 id -> name.
    """
    def key(name: str) -> str:
        return fold(ALIASES.get(name, name))

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in shapes:
        by_key[fold(shape["name"])].append(shape)
    bound: dict[str, str] = {}
    used: set[str] = set()

    def home(province: str) -> tuple[float, float, float, float] | None:
        points = [s["point"] for c, sid in bound.items() for s in shapes
                  if s["id"] == sid and departments[c][1] == province]
        if len(points) < 2:
            return None
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        pad = 0.3
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad

    # 1. By name within the province the boundary file files it under.
    for code, (name, province) in departments.items():
        hits = [s for s in by_key.get(key(name), [])
                if province and parents.get(s["parent"]) == province]
        if len(hits) == 1 and hits[0]["id"] not in used:
            bound[code] = hits[0]["id"]
            used.add(hits[0]["id"])
    progress = True
    while progress:
        progress = False
        pending = [c for c in departments if c not in bound]
        # 2. A name no other unbound polygon or department shares.
        names = defaultdict(list)
        for code in pending:
            names[key(departments[code][0])].append(code)
        for k, codes in names.items():
            free = [s for s in by_key.get(k, []) if s["id"] not in used]
            if len(codes) == 1 and len(free) == 1:
                bound[codes[0]] = free[0]["id"]
                used.add(free[0]["id"])
                progress = True
        # 3. For a shared name, the one free polygon among the province's others.
        for code in [c for c in departments if c not in bound]:
            box = home(departments[code][1] or departments[code][0])
            if box is None:
                continue
            free = [s for s in by_key.get(key(departments[code][0]), [])
                    if s["id"] not in used
                    and box[0] <= s["point"][0] <= box[2] and box[1] <= s["point"][1] <= box[3]]
            if len(free) == 1:
                bound[code] = free[0]["id"]
                used.add(free[0]["id"])
                progress = True
    missing = [f"{departments[c][0]} ({c})" for c in departments if c not in bound]
    return bound, missing


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    admin1 = json.loads((SITE / "admin1" / "ARG.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "ARG.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    admin1_ids = {u["name"]: u["id"] for u in admin1}

    fetcher = Fetcher()
    provinces: dict[str, dict[str, Any]] = {}
    departments: dict[str, dict[str, Any]] = {}
    urls: dict[tuple[str, int], list[str]] = defaultdict(list)
    worst_median = 0.0
    agreement: dict[str, int] = defaultdict(int)
    far: list[str] = []
    for index, pcode, slug, page, name, map_name in PROVINCES:
        what = name
        books = {}
        for (topic, table) in TABLES:
            books[(topic, table)], url = fetcher.workbook(index, slug, page, topic, table)
            urls[(topic, table)].append(url)
        sheets = {k: cuadros(b) for k, b in books.items()}

        # -- the departments and their 2022 populations
        repeats: dict[str, list[list[int | None]]] = {}
        rows = coded(sheet(sheets[("est", 1)], index, f"{what} est_c1"), repeats)
        if pcode not in rows:
            raise SystemExit(f"argentina_census: {what}: est_c1 has no province row {pcode}")
        dept_rows = {c: v for c, v in rows.items() if len(c) == 5 and c.startswith(pcode)}
        population = {c: v[1][1] for c, v in dept_rows.items()}
        province_pop = sum(population.values())
        # One province row, or (Buenos Aires) its Greater Buenos Aires and
        # interior rows, which make the province between them.
        stated = [r[1] for r in repeats[pcode]]
        if province_pop not in stated and province_pop != sum(v or 0 for v in stated):
            raise SystemExit(f"argentina_census: {what}: departments make "
                             f"{province_pop:,}, and the province's rows say {stated}")
        names = {c: v[0] for c, v in dept_rows.items()}

        # -- sex and single years of age
        est4 = sheets[("est", 4)]
        by_dept = dept_sheet(est4, index, names, f"{what} est_c4")
        age_figures = {c: ages(r, f"{what}, {names[c]}") for c, r in by_dept.items()}
        age_province = ages(sheet(est4, index, f"{what} est_c4"), what)
        if sum(a[0] + a[1] for a in age_figures.values()) != age_province[0] + age_province[1]:
            raise SystemExit(f"argentina_census: {what}: departments' ages do not make the province")
        published = {c: v[1][0] for c, v in
                     coded(sheet(sheets[("est", 6)], index, f"{what} est_c6")).items()}
        for code, (_, _, median) in [*age_figures.items(), (pcode, age_province)]:
            if median is None or code not in published or published[code] is None:
                continue
            gap = abs(median - published[code])
            worst_median = max(worst_median, gap)
            five = FIVE_YEAR.get(what if code == pcode else f"{what}, {names[code]}")
            for rule, value in (("single years, rounded", round(median)),
                                ("single years, truncated", int(median)),
                                ("five-year groups, rounded",
                                 round(five) if five is not None else None),
                                ("five-year groups, truncated",
                                 int(five) if five is not None else None)):
                agreement[rule] += value == published[code]
            agreement["units"] += 1
            if gap > MEDIAN_LIMIT:
                raise SystemExit(f"argentina_census: {what} {code}: median {median} against "
                                 f"INDEC's {published[code]}")
            if gap > MEDIAN_NOTE:
                far.append(f"{what} {code} ({names.get(code, what)}, "
                           f"{population.get(code, province_pop):,} people): {median} against "
                           f"{published[code]}")

        # -- indigenous and Afro-descendant self-recognition
        ind1 = sheets[("poblacion_indigena", 1)]
        ind7 = sheets[("poblacion_indigena", 7)]
        indigenous = {c: total_row(r, f"{what} indigenous {names[c]}")[0]
                      for c, r in dept_sheet(ind1, index, names, f"{what} indigena_c1").items()}
        speak = {c: [n for n in total_row(r, f"{what} language {names[c]}") if n is not None]
                 for c, r in dept_sheet(ind7, index, names, f"{what} indigena_c7").items()}
        ind_province = total_row(sheet(ind1, index, f"{what} indigena_c1"),
                                 f"{what} indigenous")[0]
        speak_province = [n for n in total_row(sheet(ind7, index, f"{what} indigena_c7"),
                                               f"{what} language") if n is not None]
        if sum(indigenous.values()) != ind_province:
            raise SystemExit(f"argentina_census: {what}: departments' indigenous people make "
                             f"{sum(indigenous.values()):,}, not {ind_province:,}")
        for code, row in [*speak.items(), (pcode, speak_province)]:
            total, yes, no, unknown = row[:4]
            if yes + no + unknown != total:
                raise SystemExit(f"argentina_census: {what} {code}: language answers "
                                 f"{yes + no + unknown:,} against {total:,}")
            if total != (indigenous.get(code) if code != pcode else ind_province):
                raise SystemExit(f"argentina_census: {what} {code}: tables 1 and 7 disagree "
                                 "on the indigenous population")
        peoples: dict[str, int] = {}
        people_total = None
        for people, numbers in labelled(sheet(sheets[("poblacion_indigena", 9)], index,
                                              f"{what} indigena_c9")):
            if people == "Total":
                people_total = numbers[0]
            elif people_total is not None and numbers and numbers[0] is not None:
                if people.startswith(("Fuente", "Nota")):
                    break
                mapped = PEOPLES.get(people, people)
                peoples[mapped] = peoples.get(mapped, 0) + numbers[0]
        if people_total != ind_province or sum(peoples.values()) != ind_province:
            raise SystemExit(f"argentina_census: {what}: peoples make {sum(peoples.values()):,} "
                             f"of {people_total}, against {ind_province:,}")
        afro_sheet = sheet(sheets[("poblacion_afrodescendiente", 7)], index, f"{what} afro_c7")
        afro_rows = coded(afro_sheet)
        afro_total = total_row(afro_sheet, f"{what} afro")
        if set(names) - set(afro_rows):
            raise SystemExit(f"argentina_census: {what}: afro_c7 lacks "
                             + ", ".join(names[c] for c in set(names) - set(afro_rows)))
        private = {c: afro_rows[c][1][0] for c in names}
        afro = {c: afro_rows[c][1][1] for c in names}
        if sum(private.values()) != afro_total[0] or sum(afro.values()) != afro_total[1]:
            raise SystemExit(f"argentina_census: {what}: departments' Afro-descendants or "
                             "private-dwelling population do not make the province")

        def ethnicity(ind: dict[str, int], afr: int, dwelling: int, spoken: list[int],
                      level: str) -> dict[str, Any]:
            indigenous_total = sum(ind.values())
            rest = dwelling - indigenous_total - afr
            if rest < 0:
                raise SystemExit(f"argentina_census: {what}: indigenous and Afro-descendant "
                                 f"people exceed the private-dwelling population")
            counts = {**ind, AFRO: afr, REST: rest}
            yes = spoken[1]
            said = (f" {100 * yes / indigenous_total:.0f}% of the indigenous population speak or "
                    "understand their people's language." if indigenous_total else "")
            which = ("which people is published for the province only, so the "
                     "department's indigenous population is one line. "
                     if level == "admin2" else "")
            return {
                "ethnicity": shares(counts),
                "ethnicity_year": YEAR,
                "ethnicity_note": (
                    f"Two questions the 2022 census asked the {dwelling:,} people in private "
                    "dwellings: whether a person recognises themselves as indigenous or "
                    "descended from an indigenous people, and whether as Afro-descendant or "
                    "as having Black or African ancestors. Someone may answer yes to both, and "
                    "INDEC publishes no cross of the two, so the remainder is the population "
                    "less both counts; " + which + "the census asks nothing about European or "
                    "mestizo ancestry." + said),
            }

        def fields(level: str, pop: int, women: int, men: int, median: float | None,
                   rounded: int | None, eth: dict[str, Any]) -> dict[str, Any]:
            source = SOURCE.format(table=TABLE_NAMES[("est", 4)])
            out = {
                "population": measure(pop, year=YEAR,
                                      source=SOURCE.format(table=TABLE_NAMES[("est", 1)])),
                "median_age": measure(median, unit="years", year=YEAR, source=source),
                "median_age_note": (
                    "Interpolated within the single year of age that holds the middle person, "
                    "from INDEC's count of everyone by sex and single year of age"
                    + (f"; INDEC's own median, to the whole year, is {rounded}." if rounded
                       is not None else ".")),
                "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                     year=YEAR, source=source),
                **eth,
                "sources": [
                    {"field": "population", "name": SOURCE.format(table=TABLE_NAMES[("est", 1)]),
                     "url": urls[("est", 1)][-1], "year": YEAR},
                    {"field": "median_age/sex_ratio", "name": source,
                     "url": urls[("est", 4)][-1], "year": YEAR},
                    {"field": "ethnicity", "name": SOURCE.format(
                        table=TABLE_NAMES[("poblacion_indigena", 1 if level == "admin2" else 9)]
                        + "; " + TABLE_NAMES[("poblacion_afrodescendiente", 7)]),
                     "url": urls[("poblacion_indigena", 1 if level == "admin2" else 9)][-1],
                     "year": YEAR},
                ],
            }
            return out

        provinces[pcode] = {
            "name": name, "map_name": map_name,
            "fields": fields("admin1", province_pop, age_province[0], age_province[1],
                             age_province[2], published.get(pcode),
                             ethnicity(peoples, afro_total[1], afro_total[0], speak_province,
                                       "admin1")),
        }
        for code in names:
            women, men, median = age_figures[code]
            departments[code] = {
                "name": names[code], "province": name, "map_province": map_name or "",
                "fields": fields("admin2", population[code], women, men, median,
                                 published.get(code),
                                 ethnicity({INDIGENOUS_DEPT: indigenous[code]}, afro[code],
                                           private[code], speak[code], "admin2")),
            }
        log(f"  {name}: {len(names)} departments, {province_pop:,} people, "
            f"{ind_province:,} indigenous, {afro_total[1]:,} Afro-descendant")

    log(f"  medians agree with INDEC's whole-year ones to within {worst_median:.2f} years; "
        f"of {agreement.pop('units')}, reproduced exactly by "
        + ", ".join(f"{rule}: {n}" for rule, n in agreement.items()))
    log(f"  {len(far)} more than {MEDIAN_NOTE:.0f} years from INDEC's: " + "; ".join(far))
    if len(far) > 0.02 * len(departments):
        raise SystemExit("argentina_census: too many medians disagree with INDEC's to be "
                         "rounding")
    national = sum(p["fields"]["population"]["value"] for p in provinces.values())
    log(f"  {len(provinces)} provinces, {len(departments)} departments, {national:,} people")

    bound, missing = bind({c: (d["name"], d["map_province"] or d["province"])
                           for c, d in departments.items()}, admin2, parents)
    log(f"  {len(bound)} departments bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    drawn = {s["id"]: s for s in admin2}
    for code, sid in bound.items():
        was = (drawn[sid].get("population") or {}).get("value")
        now = departments[code]["fields"]["population"]["value"]
        if was and not 0.5 <= now / was <= 2.0:
            log(f"  check: {departments[code]['name']} ({code}) has {now:,} people; the "
                f"polygon {drawn[sid]['name']!r} it is bound to carried {was:,}")
    unbound_shapes = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no department: {unbound_shapes}")

    records = []
    for pcode, p in sorted(provinces.items()):
        extra = ({"match_by": "shape_id", "shape_id": admin1_ids[p["map_name"]]}
                 if p["map_name"] in admin1_ids else {})
        records.append(record(f"ARG-INDEC-{pcode}", p["name"], level="admin1", parent="ARG",
                              country="ARG", codes={"indec": pcode}, **extra, **p["fields"]))
    for code, d in sorted(departments.items()):
        if code not in bound:
            continue
        records.append(record(f"ARG-INDEC-{code}", d["name"], level="admin2", parent="ARG",
                              country="ARG", parent_name=d["province"], codes={"indec": code},
                              match_by="shape_id", shape_id=bound[code], **d["fields"]))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
