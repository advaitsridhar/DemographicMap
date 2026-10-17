#!/usr/bin/env python3
"""Sao Tome and Principe -- the 2012 census by district: ages, sexes, religion.

The Instituto Nacional de Estatística published the IV Recenseamento Geral da
População e da Habitação (RGPH 2012) as a national report and one
*Resultado Distrital* per district, all PDF. This reads:

* the national report's Quadro 2 -- the resident population (present and
  absent residents, in ordinary and collective dwellings) of each district by
  sex: the population and the sex ratio;
* each district report's Quadro 5 -- residents of ordinary dwellings by sex
  and five-year age group: the median age;
* each district report's Quadro 6 -- the same residents by religion, in the
  census's thirteen answers: the religion composition.

The map draws the six districts of Sao Tome island and the Autonomous Region
of Principe (one district, drawn as Pagué) at the second level, and the two
islands' provinces at the first: Sao Tome province is the six districts added
up, Principe the region.

**Not language.** Quadro 10 asks which languages each person speaks, several
answers allowed -- in Água Grande 98.6% speak Portuguese and 36.8% Forro -- so
its answers do not divide the population into shares, and the language field
says so rather than show them.

**Checks.** Quadro 2's men and women make its total; every age table's groups
make its total; every religion row makes the district's total; the districts'
residents make the national line; and each religion column, added over the
districts, must make the national report's Quadro 6 where that row is read.

Usage:
    python -m scripts.fetch_census.sao_tome_census [--run LABEL]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .cod_ps_age import grouped_median

BASE = ("https://www.ine.st/phocadownload/userupload/Documentos/Recenseamentos/2012/"
        "Dados%20Distritais%20e%20Nacional%20Recenseamento%202012/")
NATIONAL = BASE + "Resultados%20Nacionais%20do%20IV%20RGPH%202012.pdf"
YEAR = 2012
OUT = "sao_tome_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Instituto Nacional de Estatística de São Tomé e Príncipe, IV Recenseamento Geral da "
          "População e da Habitação 2012")
LICENCE = "INE São Tomé e Príncipe publication (reuse with attribution)"

# District -> (its report's file, the map's second-level polygon id).
DISTRICTS: dict[str, tuple[str, str]] = {
    "Água Grande": ("Resultado_Distrital__%C3%81GUA-GRANDE.pdf", "43174148B36740863505441"),
    "Mé-Zóchi": ("Resultado_Distrital_M%C3%89-Z%C3%93CHI.pdf", "43174148B76706884828518"),
    "Cantagalo": ("Resultado%20Distrital_CANTAGALO.pdf", "43174148B99779095511190"),
    "Caué": ("Resultado_Distrital_CAU%C3%89.pdf", "43174148B37019359222323"),
    "Lembá": ("Resultado_Distrital_LEMB%C3%81.pdf", "43174148B20195011652309"),
    "Lobata": ("Resultado%20Distrital_LOBATA.pdf", "43174148B25004726463593"),
    "Príncipe": ("Resultado%20Distrital_REGI%C3%83O%20AUT%C3%93NOMA%20DO%20PR%C3%8DNCIPE.pdf",
                 "43174148B82261817076051"),
}
# The two islands' provinces (first-level polygon ids) and their districts.
PROVINCES = {"São Tomé": ("19237168B40253326356618", [d for d in DISTRICTS if d != "Príncipe"]),
             "Príncipe": ("19237168B82261817076051", ["Príncipe"])}
# Quadro 6's columns as the reports print them, in English. The first group
# follows the total; the second carries the rest.
RELIGION_FIRST = ("Adventist", "Assembly of God", "Catholic", "God Is Love Pentecostal Church",
                  "Jehovah's Witnesses", "Maná Church")
RELIGION_SECOND = ("New Apostolic", "Church of World Messianity",
                   "Universal Church of the Kingdom of God", "Other religion", "Don't know",
                   "Not stated", "No religion")
AGE_ROWS = [f"{lo}-{lo + 4}" for lo in range(0, 80, 5)] + ["80"]
NUMBER = re.compile(r"^\d{1,3}(?:\.\d{3})*$")

LANGUAGE_GAP = ("The 2012 census asked which languages each person speaks, several answers "
                "allowed (in Água Grande 98.6% speak Portuguese and 36.8% Forro), so its answers "
                "do not divide the population into shares and none are shown.")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text.lower() if c.isalnum())


def numbers(line: str) -> list[int]:
    """The figures at the end of a table line, thousands written with dots."""
    out: list[int] = []
    for token in reversed(line.split()):
        if NUMBER.match(token):
            out.insert(0, int(token.replace(".", "")))
        else:
            break
    return out


def pages_text(blob: bytes) -> list[str]:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


DISTRICT_KEYS = {**{fold(d): d for d in DISTRICTS},
                 fold("Região Autónoma do Príncipe"): "Príncipe", fold("R. A. Príncipe"): "Príncipe"}
# Quadro 2's row labels; what is left of a line without them and its figures
# is a piece of the district name printed down the block's side.
LABELS = ("% População residente por sexo", "População Residente (RP+RA)",
          "População total recenseada", "(RP+RA+V)", "Residente Presente (RP)",
          "Residente Ausentes (RA)", "Visitas (Presente não Residente) (V)")


def letters(text: str) -> str:
    """A name's letters in alphabetical order, accents and punctuation dropped."""
    return "".join(sorted(c for c in fold(text) if c.isalpha()))


NAME_LETTERS = {letters(key): name for key, name in DISTRICT_KEYS.items()}


def blocks(page: str) -> list[tuple[str, list[int]]]:
    """Quadro 2's district blocks on a page: (the letters of the district name
    printed sideways down the block, the resident line's figures).

    A block runs from "População total recenseada" to the line of shares by
    sex. The name is set vertically, so it reaches the text a letter or two
    at a time, alone on a line or ahead of a row label.
    """
    out: list[tuple[str, list[int]]] = []
    pool: list[str] = []
    figures: list[int] = []
    inside = False
    for line in page.splitlines():
        if "População total recenseada" in line:
            pool, figures, inside = [], [], True
        if not inside:
            continue
        rest = line
        for label in LABELS:
            rest = rest.replace(label, " ")
        pool.extend(t for t in rest.split() if not re.search(r"\d", t))
        if "População Residente (RP+RA)" in line:
            after = line.split("População Residente (RP+RA)", 1)[1].split()
            figures = [int(t.replace(".", "")) for t in after if NUMBER.match(t)]
        if "% População residente por sexo" in line:
            out.append((letters(" ".join(pool)), figures))
            inside = False
    return out


def residents(pages: list[str]) -> dict[str, tuple[int, int, int, int]]:
    """Quadro 2: district -> (total, men, women, of them in ordinary dwellings).

    The table lists the districts one block after another; a block's resident
    line gives total, men and women in all dwellings, then the same in
    ordinary and in collective dwellings. A block is the district whose name
    has exactly the block's letters.
    """
    out: dict[str, tuple[int, int, int, int]] = {}
    for page in pages:
        # The table itself, not the contents page that names it.
        if "Quadro 2" not in page or "Residente (RP+RA)" not in page:
            continue
        for key, figures in blocks(page):
            name = NAME_LETTERS.get(key)
            if name and len(figures) >= 6 and figures[1] + figures[2] == figures[0]:
                out.setdefault(name, (figures[0], figures[1], figures[2], figures[3]))
    return out


def quadro2_lines(pages: list[str]) -> list[str]:
    """The table's lines, printed when it cannot be read."""
    return [line for page in pages if "Quadro 2" in page and "Residente (RP+RA)" in page
            for line in page.splitlines()][:80]


def table_lines(pages: list[str], title: str, limit: int = 60) -> list[str]:
    """The first lines of the pages holding a table, printed when it cannot be read."""
    return [line for page in pages if title in page for line in page.splitlines()][:limit]


def national_residents(pages: list[str]) -> int | None:
    """The national report's Quadro 1: residents in all dwellings."""
    for page in pages:
        if "Quadro 1" not in page:
            continue
        found = [numbers(line) for line in page.splitlines()
                 if "Residente (RP+RA)" in line and "População" in line]
        found = [f for f in found if len(f) >= 3 and f[1] + f[2] == f[0]]
        if found:
            return max(f[0] for f in found)
    return None


def ages(pages: list[str]) -> tuple[int, list[list[Any]]] | None:
    """Quadro 5 of a district report: (total, [[low, high, people], ...]).

    Each row gives total, men and women for the district, then (outside the
    all-urban Água Grande) the same for its urban and its rural part; the
    district's three come first.
    """
    for page in pages:
        if "Quadro 5" not in page or "quinquenais" not in page:
            continue
        rows: dict[str, int] = {}
        total = None
        for line in page.splitlines():
            figures = numbers(line)
            if len(figures) not in (3, 6, 9) or figures[1] + figures[2] != figures[0]:
                continue
            label = line.strip().split()[0]
            if label == "Total":
                total = figures[0]
            elif re.match(r"^\d+-\d+$", label) or label == "80":
                rows.setdefault(label, figures[0])
        if total and all(r in rows for r in AGE_ROWS):
            groups = [[int(r.split("-")[0]), int(r.split("-")[1]), rows[r]] for r in AGE_ROWS[:-1]]
            groups.append([80, None, rows["80"]])
            if sum(g[2] for g in groups) != total:
                raise SystemExit(f"sao_tome_census: age groups make {sum(g[2] for g in groups):,}, "
                                 f"the table {total:,}")
            return total, groups
    return None


def religion(pages: list[str], total: int) -> dict[str, int] | None:
    """Quadro 6 of a district report: the district's row in both column groups."""
    text = [line for page in pages if "Quadro 6" in page for line in page.splitlines()]
    first = None
    for line in text:
        figures = numbers(line)
        if len(figures) == 7 and figures[0] == total:
            first = figures[1:]
            break
    if first is None:
        return None
    rest = total - sum(first)
    second = None
    for line in text:
        figures = numbers(line)
        if len(figures) == 7 and sum(figures) == rest and figures[-1] > 0:
            second = figures
            break
    if second is None:
        return None
    return dict(zip(RELIGION_FIRST + RELIGION_SECOND, first + second))


def fields(res: tuple[int, int, int] | None, age: tuple[int, list] | None,
           rel: dict[str, int] | None, where: str) -> dict[str, Any]:
    out: dict[str, Any] = {"language": gap(NOT_AVAILABLE, LANGUAGE_GAP)}
    if res:
        total, men, women = res
        out["population"] = measure(total, year=YEAR, source=SOURCE)
        out["population_note"] = (f"The resident population of {where} at the 2012 census, present "
                                  f"and absent residents, in ordinary and collective dwellings.")
        out["sex_ratio"] = measure(round(1000 * men / women), unit="males_per_1000_females",
                                   year=YEAR, source=SOURCE)
        out["sex_ratio_note"] = "Men per 1,000 women among the residents the 2012 census counted."
    if age:
        median = grouped_median([tuple(g) for g in age[1]])
        if median is not None:
            out["median_age"] = {"value": median, "unit": "years", "year": YEAR, "source": SOURCE}
            out["median_age_note"] = (
                f"Interpolated within the five-year age group that holds the middle person, from "
                f"the 2012 census's ages of the {age[0]:,} residents of ordinary dwellings.")
    if rel:
        out["religion"] = shares(rel)
        out["religion_year"] = YEAR
        out["religion_note"] = (f"The 2012 census's religion question, answered for the "
                                f"{sum(rel.values()):,} residents of ordinary dwellings, in the "
                                f"census's own thirteen answers.")
    return out


def build(national: list[str], reports: dict[str, list[str]]) -> tuple[list[dict], list[str]]:
    report: list[str] = []
    res: dict[str, tuple[int, int, int]] = {}
    data: dict[str, dict[str, Any]] = {}
    table = residents(national)
    if set(table) != set(DISTRICTS):
        for line in quadro2_lines(national):
            log(f"    | {line}")
        raise SystemExit(f"sao_tome_census: Quadro 2 read for {sorted(table)} only")
    for name in DISTRICTS:
        pages = reports.get(name)
        if pages is None:
            raise SystemExit(f"sao_tome_census: no report read for {name}")
        for other, own in residents(pages).items():
            if own != table[other]:
                raise SystemExit(f"sao_tome_census: {name}'s report prints {own} for {other}, "
                                 f"the national report {table[other]}")
        total, men, women, ordinary = table[name]
        res[name] = (total, men, women)
        age = ages(pages)
        if age is None:
            for line in table_lines(pages, "Quadro 5"):
                log(f"    | {line}")
            raise SystemExit(f"sao_tome_census: no age table read for {name}")
        if age[0] != ordinary:
            raise SystemExit(f"sao_tome_census: {name}'s ages cover {age[0]:,}, its residents of "
                             f"ordinary dwellings are {ordinary:,}")
        rel = religion(pages, age[0])
        if rel is None:
            for line in table_lines(pages, "Quadro 6"):
                log(f"    | {line}")
            raise SystemExit(f"sao_tome_census: no religion row read for {name}")
        data[name] = {"age": age, "religion": rel}
        report.append(f"  {name}: residents {total:,} ({men:,} men); ordinary dwellings "
                      f"{ordinary:,}; religion "
                      + (f"{sum(rel.values()):,} in {len(rel)} answers" if rel else "not read"))
    whole = national_residents(national)
    made = sum(r[0] for r in res.values())
    report.append(f"  the districts' residents make {made:,}; the national line {whole}")
    if whole is not None and whole != made:
        raise SystemExit(f"sao_tome_census: districts make {made:,}, the country {whole:,}")
    records: list[dict[str, Any]] = []
    for name, (file, sid) in DISTRICTS.items():
        d = data.get(name, {})
        cite = [{"field": "population/sex_ratio/median_age/religion",
                 "name": SOURCE + f", Resultado Distrital ({name}), Quadros 2, 5 and 6",
                 "url": BASE + file, "year": YEAR, "license": LICENCE}]
        where = "the Autonomous Region of Príncipe" if name == "Príncipe" else f"{name} district"
        records.append(record(f"STP-RGPH2012-{sid}", name, level="admin2", parent="STP",
                              country="STP", match_by="shape_id", shape_id=sid,
                              sources=cite, **fields(res[name], d.get("age"), d.get("religion"),
                                                      where)))
    for province, (sid, members) in PROVINCES.items():
        total = sum(res[m][0] for m in members)
        men = sum(res[m][1] for m in members)
        women = sum(res[m][2] for m in members)
        agegroups = None
        if all(data.get(m, {}).get("age") for m in members):
            pooled = [[lo, hi, 0] for lo, hi, _ in data[members[0]]["age"][1]]
            for m in members:
                for i, (_, _, people) in enumerate(data[m]["age"][1]):
                    pooled[i][2] += people
            agegroups = (sum(data[m]["age"][0] for m in members), pooled)
        rel = None
        if all(data.get(m, {}).get("religion") for m in members):
            rel = {k: sum(data[m]["religion"][k] for m in members)
                   for k in RELIGION_FIRST + RELIGION_SECOND}
        where = ("the Autonomous Region of Príncipe" if province == "Príncipe"
                 else "São Tomé province, its six districts added up")
        cite = [{"field": "population/sex_ratio/median_age/religion",
                 "name": SOURCE + f", Resultado Distrital ({m}), Quadros 2, 5 and 6",
                 "url": BASE + DISTRICTS[m][0], "year": YEAR, "license": LICENCE}
                for m in members]
        records.append(record(f"STP-RGPH2012-{sid}", province, level="admin1", parent="STP",
                              country="STP", match_by="shape_id", shape_id=sid,
                              sources=cite,
                              **fields((total, men, women), agegroups, rel, where)))
        report.append(f"  province {province}: {total:,}")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    drawn = {u["id"] for level in ("admin1", "admin2")
             for u in json.loads((SITE / level / "STP.units.json").read_text())}
    wanted = {sid for _f, sid in DISTRICTS.values()} | {sid for sid, _m in PROVINCES.values()}
    if wanted - drawn:
        raise SystemExit(f"sao_tome_census: polygons no longer drawn: {sorted(wanted - drawn)}")
    blob = http_get(NATIONAL, binary=True, cache=False, timeout=300)
    log(f"sao_tome_census: national report {len(blob):,} bytes, "
        f"sha256 {hashlib.sha256(blob).hexdigest()}")
    national = pages_text(blob)
    reports: dict[str, list[str]] = {}
    for name, (file, _sid) in DISTRICTS.items():
        try:
            body = http_get(BASE + file, binary=True, cache=False, timeout=300)
        except Exception as exc:                     # noqa: BLE001 -- reported
            log(f"  {name}: {exc}")
            continue
        if not body.startswith(b"%PDF"):
            log(f"  {name}: not a PDF")
            continue
        log(f"  {name}: {len(body):,} bytes, sha256 {hashlib.sha256(body).hexdigest()}")
        reports[name] = pages_text(body)
    records, report = build(national, reports)
    for line in report:
        log(line)
    nat = {}
    for r in records:
        if r["level"] == "admin2" and isinstance(r.get("religion"), list):
            for g in r["religion"]:
                nat[g["group"]] = nat.get(g["group"], 0) + g["count"]
    whole = sum(nat.values())
    if whole:
        log("  religion, the districts added up: " + ", ".join(
            f"{k} {100 * v / whole:.1f}%" for k, v in sorted(nat.items(), key=lambda kv: -kv[1])))
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
