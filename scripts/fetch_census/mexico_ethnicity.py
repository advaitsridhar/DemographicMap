#!/usr/bin/env python3
"""Mexico: indigenous and Afro-Mexican self-identification by municipio (2020 census).

The basic questionnaire, which ITER and ``mexico.py`` carry, asks everyone one
ethnic question -- whether they consider themselves Afro-Mexican, Black or
Afro-descendant -- and whether they speak an indigenous language. Whether a
person considers themselves indigenous ("De acuerdo con su cultura, ¿se
considera indígena?") is asked only in the extended questionnaire, a sample
of about four million homes drawn so that every municipio has an estimate.
Language is no stand-in for it: 7.4 million people aged 3 or over speak an
indigenous language, and 23.2 million consider themselves indigenous.

The two identifications overlap. On the Costa Chica many people answer yes to
both, so the two shares INEGI publishes cannot be stacked into one bar that
sums to 100. The cross of the two answers exists only in the sample's
microdata, which INEGI publishes openly with the expansion factor (FACTOR)
its own tables are weighted by. This reads each state's file, weights every
person aged 3 or over by it, and splits them five ways: indigenous only,
indigenous and Afro-Mexican, Afro-Mexican only, neither, and not stated.
Only those sums are written; the microdata stays where it was read.

Nothing is written unless every figure reproduces INEGI's own tables:

* every municipio's and every state's population aged 3 or over, and its
  shares who do, do not and did not say they consider themselves indigenous,
  equal INEGI's published estimates (``cpv2020_a_<state>_05_etnicidad.xlsx``,
  sheet 02) to within 0.01 of a point. "No" is code 3; which codes INEGI
  counts as "yes", and whether people of unstated age are in the base, is read
  off that match rather than assumed, and every reading that reproduces all 32
  states must agree on the codes people actually gave. Whatever is neither yes
  nor no is not stated;
* the Afro-Mexican question's "yes", over all ages, gives a national estimate
  within 5% of the full count's 2,576,213 (ITER's POB_AFRO), which the sample
  is an estimate of; of the readings that do, the nearest is taken.

Records carry the ids, names and parents of ``mexico.py``'s, so they join the
same polygons.

Usage:
    python -m scripts.fetch_census.mexico_ethnicity        # runner
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter, defaultdict
from itertools import product
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, read_json, record, shares, write_json
from .mexico import LICENSE, NATIONAL, STATE_ALIASES
from .mexico_age import STATES, number

YEAR = 2020
BASE = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/"
MICRODATA = BASE + "microdatos/Censo2020_CA_{abbr}_csv.zip"
TABLE = BASE + "tabulados/ampliado/cpv2020_a_{abbr}_05_etnicidad.xlsx"
SOURCE = ("INEGI, Censo de Población y Vivienda 2020, cuestionario ampliado "
          "(muestra censal, microdatos ponderados con el factor de expansión)")
TABLE_SOURCE = ("INEGI, Censo de Población y Vivienda 2020, tabulados del cuestionario "
                "ampliado (Etnicidad 02: autoadscripción indígena por municipio)")
SHEET = "02"
CODED = re.compile(r"^(\d{2,3})\s+(.+)$")
COLUMNS = ("ENT", "MUN", "FACTOR", "EDAD", "PERTE_INDIGENA", "AFRODES")
UNSTATED_AGE = "999"
TOLERANCE = 0.01                    # percentage points
# The sample is weighted to the census's population by age and sex, not by
# identity, and it puts Afro-Mexicans at 2,482,098 against the full count's
# 2,576,213 -- 3.7% fewer (September 2026). The check is for a misread answer
# code, which would miss by orders of magnitude, not by that.
AFRO_TOLERANCE = 0.05               # of the full count

# The questionnaire's answers are yes, yes in part, no and does not know, and
# the file adds a code for no answer at all. Which of them INEGI's published
# "se considera indígena" counts is taken from the match with its table, over
# these readings, not from a reading of the codebook. A reading is
# (indigenous yes, Afro-Mexican yes, whether unstated ages are in the base).
NO = "3"
YES = (frozenset({"1"}), frozenset({"1", "2"}))
AGE_BASE = (False, True)

LABELS = {
    "indigenous": "Indigenous (self-identified)",
    "both": "Indigenous and Afro-Mexican",
    "afro": "Afro-Mexican or Afro-descendant",
    "neither": "Mestizo or white (neither indigenous nor Afro-Mexican)",
    "unstated": "Not stated",
}
NOTE = (
    "Everyone aged 3 or over, by two questions of the 2020 census's extended "
    "questionnaire: whether they consider themselves indigenous, by their "
    "culture, and whether they consider themselves Afro-Mexican, Black or "
    "Afro-descendant. A person may say yes to both, and those who did are "
    "shown on their own rather than counted twice. No question asks about "
    "mestizo or white ancestry; that share is everyone who said no to both. "
    "Estimated by INEGI's expansion factors from a sample of about four "
    "million homes, so the Afro-Mexican share differs slightly from the full "
    "count's. Identifying as indigenous is much wider than speaking an "
    "indigenous language, which the language figure shows.")


def fetch(template: str, abbrs: tuple[str, ...]) -> tuple[str, bytes]:
    for abbr in abbrs:
        url = template.format(abbr=abbr)
        try:
            blob = http_get(url, binary=True, cache=False, timeout=600)
        except (RuntimeError, OSError) as exc:
            log(f"  {url}: {exc}")
            continue
        # INEGI answers a wrong path with HTTP 200 and an HTML page.
        if blob.startswith(b"PK"):
            return url, blob
    raise LookupError(abbrs)


def tally(code: str, url: str, blob: bytes) -> dict[str, Counter]:
    """Each municipio's weighted people, by (age class, indigenous, Afro) answer."""
    out: dict[str, Counter] = defaultdict(Counter)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        member = next((n for n in zf.namelist() if n.lower().startswith("personas")), None)
        if member is None:
            raise SystemExit(f"mexico_ethnicity: {url} holds no person file: {zf.namelist()}")
        with zf.open(member) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="latin-1", newline=""))
            header = [h.strip() for h in next(reader)]
            missing = [c for c in COLUMNS if c not in header]
            if missing:
                raise SystemExit(f"mexico_ethnicity: {url} {member} lacks {missing}")
            ent, mun, factor, age, indig, afro = (header.index(c) for c in COLUMNS)
            for row in reader:
                if row[ent] != code:
                    raise SystemExit(f"mexico_ethnicity: {url} has a person in state "
                                     f"{row[ent]!r}, not {code}")
                years = row[age].strip()
                band = ("unstated" if years == UNSTATED_AGE or not years.isdigit()
                        else "3+" if int(years) >= 3 else "0-2")
                out[row[mun]][(band, row[indig].strip(), row[afro].strip())] += int(row[factor])
    return out


def published(code: str, url: str, blob: bytes) -> dict[str, dict[str, Any]]:
    """INEGI's own estimates from sheet 02, by municipio code and 'Total'."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    out: dict[str, dict[str, Any]] = {}
    for row in wb[SHEET].iter_rows(values_only=True):
        if not row or len(row) < 8 or not row[0]:
            continue
        ent = CODED.match(str(row[0]).strip())
        if not ent or str(row[2] or "").strip() != "Total":
            continue
        if ent.group(1) != code:
            raise SystemExit(f"mexico_ethnicity: {url} has a row for state {row[0]!r}, not {code}")
        unit = str(row[1] or "").strip()
        mun = CODED.match(unit)
        if unit != "Total" and not mun:
            raise SystemExit(f"mexico_ethnicity: {url}: unreadable municipio cell {unit!r}")
        key = "Total" if unit == "Total" else mun.group(1).zfill(3)
        entry = out.setdefault(key, {"name": ent.group(2).strip() if unit == "Total"
                                     else mun.group(2).strip()})
        estimator = str(row[3] or "").strip()
        if estimator == "Valor":
            entry.update(base=number(row[4]), yes=number(row[5]), no=number(row[6]),
                         unstated=number(row[7]))
        elif estimator.startswith("Coeficiente"):
            entry["cv"] = number(row[5])
    if "Total" not in out or len(out) < 2:
        raise SystemExit(f"mexico_ethnicity: {url}: {len(out)} rows with a Total estimate")
    return out


def indigenous_shares(counts: Counter, reading: tuple) -> tuple[float, float, float, float]:
    """(base, % yes, % no, % not stated) of the indigenous question under a reading."""
    yes, _, with_unstated_age = reading
    bands = {"3+", "unstated"} if with_unstated_age else {"3+"}
    base = y = n = 0
    for (band, indig, _), people in counts.items():
        if band not in bands:
            continue
        base += people
        y += people if indig in yes else 0
        n += people if indig == NO else 0
    if not base:
        return 0, 0.0, 0.0, 0.0
    return base, 100 * y / base, 100 * n / base, 100 * (base - y - n) / base


def agrees(counts: Counter, table: dict[str, Any], reading: tuple) -> bool:
    base, y, n, u = indigenous_shares(counts, reading)
    return (table.get("base") is not None and abs(base - table["base"]) < 0.5
            and all(abs(ours - (theirs or 0)) <= TOLERANCE
                    for ours, theirs in ((y, table.get("yes")), (n, table.get("no")),
                                         (u, table.get("unstated")))))


def composition(counts: Counter, reading: tuple) -> tuple[float, dict[str, float]]:
    """The five-way split of everyone in the base."""
    indig_yes, afro_yes, with_unstated_age = reading
    bands = {"3+", "unstated"} if with_unstated_age else {"3+"}
    split: Counter = Counter()
    for (band, indig, afro), people in counts.items():
        if band not in bands:
            continue
        if indig in indig_yes and afro in afro_yes:
            split["both"] += people
        elif indig in indig_yes:
            split["indigenous"] += people
        elif afro in afro_yes:
            split["afro"] += people
        elif indig == NO and afro == NO:
            split["neither"] += people
        else:
            split["unstated"] += people
    return sum(split.values()), {LABELS[k]: v for k, v in split.items() if v}


def note_for(table: dict[str, Any]) -> str:
    cv = table.get("cv")
    if cv is None:
        return NOTE
    return (NOTE + f" INEGI's coefficient of variation for the indigenous share "
            f"here is {cv:.1f}%.")


def main() -> int:
    states: dict[str, dict[str, Any]] = {}
    missing = []
    for code, abbrs in STATES.items():
        try:
            data_url, data = fetch(MICRODATA, abbrs)
            table_url, table = fetch(TABLE, abbrs)
        except LookupError:
            missing.append(f"{code} {abbrs}")
            continue
        counts = tally(code, data_url, data)
        del data
        states[code] = {"counts": counts, "table": published(code, table_url, table),
                        "urls": (data_url, table_url)}
        log(f"  {code}: {len(counts)} municipios in the sample, "
            f"{sum(sum(c.values()) for c in counts.values()):,} people weighted")
    if missing:
        raise SystemExit(f"mexico_ethnicity: no microdata or table for {', '.join(missing)}")

    # The one reading of the codes under which the sample reproduces every
    # published estimate, municipio by municipio and state by state.
    readings = [(yes, frozenset(), age) for yes, age in product(YES, AGE_BASE)]
    fits = set(readings)
    answers: dict[str, Counter] = {"indigenous": Counter(), "Afro-Mexican": Counter(),
                                   "age": Counter()}
    for code, state in states.items():
        table, counts = state["table"], state["counts"]
        if set(table) - {"Total"} != set(counts):
            raise SystemExit(f"mexico_ethnicity: state {code}: the table has "
                             f"{len(set(table) - {'Total'})} municipios, the sample "
                             f"{len(counts)}; differing: "
                             f"{sorted((set(table) - {'Total'}) ^ set(counts))[:10]}")
        whole = sum(counts.values(), Counter())
        for (band, indig, afro), people in whole.items():
            answers["indigenous"][indig] += people if band != "0-2" else 0
            answers["Afro-Mexican"][afro] += people
            answers["age"][band] += people
        here = {r for r in readings
                if agrees(whole, table["Total"], r)
                and all(agrees(counts[m], table[m], r) for m in counts)}
        if not here:
            first = next(iter(counts))
            codes = Counter()
            for (band, indig, afro), people in whole.items():
                codes[("indig", indig)] += people
                codes[("afro", afro)] += people
                codes[("age", band)] += people
            raise SystemExit(
                f"mexico_ethnicity: no reading of the codes reproduces state {code}'s "
                f"table. Codes: {dict(codes)}. Table total {table['Total']}, "
                f"municipio {first} {table[first]}; sample under each reading: "
                f"{[(r, indigenous_shares(counts[first], r)) for r in readings]}")
        fits &= here
    for question, seen in answers.items():
        log(f"  {question} answers, weighted: " + ", ".join(
            f"{k or 'blank'} {v:,}" for k, v in sorted(seen.items())))
    # Readings that differ only in codes nobody gave are one reading.
    given = {k for k, v in answers["indigenous"].items() if v}
    effective = {(frozenset(yes & given), age) for yes, _, age in fits}
    if len(effective) != 1:
        raise SystemExit(f"mexico_ethnicity: {len(effective)} different readings reproduce "
                         f"every table: {effective}")
    indig_yes, with_unstated_age = effective.pop()

    # The Afro-Mexican "yes", over all ages, against the full count the
    # sample estimates.
    counted = NATIONAL["POB_AFRO"]
    afro_given = answers["Afro-Mexican"]
    estimates = {frozenset(y & set(afro_given)): sum(afro_given[c] for c in y) for y in YES}
    close = {y: e for y, e in estimates.items() if abs(e - counted) <= AFRO_TOLERANCE * counted}
    if not close:
        raise SystemExit(f"mexico_ethnicity: no reading of the Afro-Mexican answers comes within "
                         f"{AFRO_TOLERANCE:.0%} of the full count's {counted:,}: "
                         f"{ {tuple(sorted(y)): e for y, e in estimates.items()} }")
    afro_yes = min(close, key=lambda y: abs(close[y] - counted))
    reading = (indig_yes, afro_yes, with_unstated_age)
    log(f"  reading: indigenous yes={sorted(indig_yes)}, Afro-Mexican yes={sorted(afro_yes)} "
        f"(sample {close[afro_yes]:,}, full count {counted:,}), no={NO}, unstated age "
        f"{'in' if with_unstated_age else 'out of'} the base")

    iter_states = {r["id"]: r for r in read_json(PROCESSED / "mexico_state.json", [])}
    iter_municipios = {r["id"]: r for r in read_json(PROCESSED / "mexico_municipality.json", [])}
    records: list[dict[str, Any]] = []
    national: Counter = Counter()
    for code, state in states.items():
        data_url, table_url = state["urls"]
        cite = [{"field": "ethnicity", "name": SOURCE, "url": data_url, "license": LICENSE},
                {"field": "ethnicity", "name": TABLE_SOURCE, "url": table_url,
                 "license": LICENSE}]
        whole = sum(state["counts"].values(), Counter())
        base, split = composition(whole, reading)
        national.update(split)
        known = iter_states.get(f"MEX-{code}000") or {}
        records.append(record(
            f"MEX-{code}000", known.get("name") or state["table"]["Total"]["name"],
            level="admin1", parent="MEX", country="MEX", codes={"inegi": f"{code}000"},
            ethnicity=shares(split, total=base), ethnicity_year=YEAR,
            ethnicity_note=note_for(state["table"]["Total"]), sources=cite))
        for mun, counts in sorted(state["counts"].items()):
            base, split = composition(counts, reading)
            known = iter_municipios.get(f"MEX-{code}{mun}") or {}
            records.append(record(
                f"MEX-{code}{mun}", known.get("name") or state["table"][mun]["name"],
                level="admin2", parent=f"MEX-{code}", country="MEX",
                parent_name=known.get("parent_name") or state["table"]["Total"]["name"],
                parent_aliases=STATE_ALIASES.get(state["table"]["Total"]["name"]),
                codes={"inegi": f"{code}{mun}"},
                ethnicity=shares(split, total=base), ethnicity_year=YEAR,
                ethnicity_note=note_for(state["table"][mun]), sources=cite))
    # A municipio ITER counts and the sample does not reach says so.
    sampled = {r["id"] for r in records}
    for mid, m in iter_municipios.items():
        if mid not in sampled:
            records.append(record(
                mid, m["name"], level="admin2", parent=m["parent"], country="MEX",
                parent_name=m.get("parent_name"), parent_aliases=m.get("parent_aliases"),
                codes=m.get("codes"),
                ethnicity=gap(NOT_AVAILABLE, "INEGI's extended-questionnaire sample "
                              "publishes no estimate for this municipio.")))
    total = sum(national.values())
    log(f"  national, aged 3+: " + ", ".join(
        f"{k} {100 * v / total:.1f}%" for k, v in national.most_common()))
    log(f"  {sum(1 for r in records if r['level'] == 'admin2')} municipios "
        f"({len(iter_municipios) - len(sampled & set(iter_municipios))} of ITER's without "
        f"an estimate), {sum(1 for r in records if r['level'] == 'admin1')} states")
    write_json(PROCESSED / "mexico_ethnicity.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
