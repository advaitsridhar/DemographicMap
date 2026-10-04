#!/usr/bin/env python3
"""Catalonia: religion and first language by province from the CEO's political barometer.

The Centre d'Estudis d'Opinió (CEO), the Generalitat de Catalunya's survey
office, interviews 2,000 people face to face three times a year for its
Baròmetre d'Opinió Política (BOP), and publishes the anonymised microdata of
every wave as open data: one accumulated file per series, linked from the
Generalitat's open-data portal (Dades Obertes Catalunya, dataset gp4k-sxxn),
downloadable with no account and no form. Every respondent carries the
province they live in, which nothing else on the map gives below the
comunidad for either field: Spain's census asks neither religion nor language,
the CIS publishes Catalonia's 2024 pre-electoral survey by province no longer,
and Idescat's language survey (EULP) is published for Catalonia and for areas
that are not provinces.

**What is read.** The three most recent waves of the face-to-face series,
pooled (at the time of writing BOP 62-64, June 2025 to June 2026, 6,000
interviews), and two questions:

* ``RELIGIO`` "Amb independència que sigui practicant o no, quina és la seva
  religió?" -- whatever their practice, what is their religion: Catholicism,
  Evangelical or Protestant Christianity, Islam, Jehovah's Witnesses,
  Buddhism, Orthodox Christianity, Judaism, none (agnosticism), none
  (atheism), other; don't know and no answer are Not stated.
* ``LLENGUA_PRIMERA_1_3`` "Quina llengua va parlar primer vostè, a casa, quan
  era petit?" -- the language first spoken at home as a child: Catalan,
  Spanish, or another answer, which ``LLENGUA_PRIMERA_ALTRES`` details as
  Catalan and Spanish equally, Aranese, Arabic, Romanian, or other languages
  or combinations. The habitual-language question (``LLENGUA_HABITUAL``) has
  not been asked since 2022 and is not read.

Religion is written for the four provinces and for Catalonia as a whole; first
language for the provinces only, because Catalonia's language is Idescat's
EULP (2023, habitual language, a dedicated language survey with a larger
sample), which this file does not write over.

**What the religion question counts.** It asks which religion people have,
whatever their practice, so nominal Catholics answer Catholicism. That puts
Catholics first in Catalonia (53% in waves 62-64, against 38% for atheism and
agnosticism together), where the European Social Survey -- which first asks
whether one belongs to any religion at all -- puts no religion first (54%
against 39% Roman Catholic, rounds 7-11, 2014-2024, residents aged 15 and
over). The CIS's own question lands where this one does: its 2021 survey of
Catalonia (study 3306, 4,106 respondents) found Catholics 52% and its three
irreligious answers 43%, and Catholics within 1 to 3 points of this file's
figures in each province. So Catalonia's comunidad is written here as well,
in front of the ESS as the build ranks a national office's survey: it agrees
with its own provinces at the zoom below and with the comunidades the CIS
fills. Every religion note says what the question counts.

**Weights and sample.** The CEO's weight (``PONDERA``) is applied; it is 1 for
every respondent of these waves, the sample being drawn in proportion to the
population by province, and the note says so when that holds. A province
needs 100 respondents (100-299 is marked low precision).

**Microdata.** The file is read where it is downloaded, on the runner, into a
temporary file; only each province's tally of the two questions is written.

Checks, each of which stops the run:

* the open-data listing still describes the series' universe as Spanish
  citizens aged 18 and over resident in Catalonia, and every respondent read
  says they are a Spanish citizen;
* every code read has the label it is translated from (a recoded question
  stops the run rather than being mislabelled), and no respondent of the
  pooled waves skipped either question;
* the provinces are Barcelona, Girona, Lleida and Tarragona by their INE
  codes, they make the pool, and each composition makes its province's
  respondents;
* every province binds by its INE code to exactly one drawn polygon labelled
  with its name, inside the polygon labelled Catalonia (``spain_cis.bind``).

Usage:
    python -m scripts.fetch_census.catalonia_ceo
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .binding import fold
from .spain_cis import bind, load_units

OUT = "catalonia_ceo_survey.json"
LISTING = "https://analisi.transparenciacatalunya.cat/resource/gp4k-sxxn.json"
DATASET = ("https://analisi.transparenciacatalunya.cat/Sector-P-blic/"
           "Microdades-acumulades-de-les-enquestes-del-Centre-/gp4k-sxxn")
SERIES = "BOP_presencial"
WAVES = 3
MIN_N = 100
LOW_PRECISION = 300
LICENCE = "Dades Obertes Catalunya open-data licence (attribution: Centre d'Estudis d'Opinió)"
CATALONIA = "09"

COLUMNS = ["PONDERA", "BOP_NUM", "ANY", "MES", "PROVINCIA", "CIUTADANIA", "RELIGIO",
           "LLENGUA_PRIMERA_1_3", "LLENGUA_PRIMERA_ALTRES"]

PROVINCES = {8: "08", 17: "17", 25: "25", 43: "43"}
CITIZENS = {1, 2}          # Spanish citizen; Spanish citizen and another

# Code -> (the start of the CEO's label, folded; the map's label).
RELIGION = {
    1: ("catolicisme", "Catholic"),
    2: ("cristianismeevangelic", "Evangelical or Protestant"),
    3: ("islam", "Islam"),
    4: ("testimonis", "Jehovah's Witnesses"),
    5: ("budisme", "Buddhism"),
    6: ("cristianismeortodox", "Orthodox"),
    7: ("judaisme", "Judaism"),
    8: ("capagnosticisme", "Agnostic"),
    9: ("capateisme", "Atheist"),
    80: ("altres", "Other religions"),
    98: ("nohosap", "Not stated"),
    99: ("nocontesta", "Not stated"),
}
FIRST = {
    1: ("catala", "Catalan"),
    2: ("castella", "Spanish"),
    80: ("altresopcions", None),           # detailed by LLENGUA_PRIMERA_ALTRES
    98: ("nohosap", "Not stated"),
    99: ("nocontesta", "Not stated"),
}
OTHER_FIRST = {
    1: ("catalaicastellaperigual", "Catalan and Spanish"),
    2: ("aranes", "Aranese Occitan"),
    3: ("arab", "Arabic"),
    4: ("romanes", "Romanian"),
    80: ("altresllenguesocombinacions", "Other languages or combinations"),
}
RELIGION_QUESTION = ("\"Amb independència que sigui practicant o no, quina és la seva religió?\" "
                     "(whatever your practice, what is your religion?)")
FIRST_QUESTION = ("\"Quina llengua va parlar primer vostè, a casa, quan era petit?\" (which "
                  "language did you first speak at home as a child?), with \"another answer\" "
                  "detailed by the follow-up question")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def check_labels(labels: dict[Any, str], codes: dict[int, tuple[str, Any]], variable: str) -> None:
    """Every code read must carry the label it is translated from."""
    for code, (start, _) in codes.items():
        got = next((v for k, v in labels.items() if int(float(k)) == code), None)
        if got is None or not fold(got).startswith(start):
            raise SystemExit(f"catalonia_ceo: {variable} {code} is labelled {got!r}, "
                             f"expected one beginning {start!r}")


def series(listing: list[dict[str, Any]]) -> dict[str, Any]:
    """The face-to-face BOP series in the open-data listing: its file and universe."""
    row = next((r for r in listing if r.get("codi_serie") == SERIES), None)
    if row is None:
        raise SystemExit(f"catalonia_ceo: the listing has no series {SERIES}")
    universe = row.get("univers") or ""
    if "ciutadaniaespanyola" not in fold(universe) or "18" not in universe:
        raise SystemExit(f"catalonia_ceo: the series' universe is now {universe!r}")
    url = ((row.get("microdades_1") or {}).get("url") or "")
    if not url.endswith(".sav"):
        raise SystemExit(f"catalonia_ceo: the series' SPSS file is now {url!r}")
    return {"url": url, "universe": universe, "title": row.get("titol_serie", "")}


def code_of(value: Any, allowed: Any) -> int | None:
    """A cell as one of the allowed codes, or None: missing, fractional or unknown."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or not number.is_integer() or int(number) not in allowed:
        return None
    return int(number)


def tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pooled rows -> each province's weighted tally of the two questions.

    ``rows`` are dicts of the COLUMNS, as numbers (NaN where missing).
    """
    waves = sorted({int(r["BOP_NUM"]) for r in rows})
    out: dict[str, Any] = {"waves": waves, "provinces": {}, "uniform": True}
    religion: dict[int, Counter] = defaultdict(Counter)
    first: dict[int, Counter] = defaultdict(Counter)
    n: Counter = Counter()
    mass: Counter = Counter()
    for r in rows:
        prov = code_of(r["PROVINCIA"], PROVINCES)
        if prov is None:
            raise SystemExit(f"catalonia_ceo: a respondent's province is {r['PROVINCIA']!r}")
        if code_of(r["CIUTADANIA"], CITIZENS) is None:
            raise SystemExit(f"catalonia_ceo: a respondent in wave {r['BOP_NUM']} is not a "
                             f"Spanish citizen ({r['CIUTADANIA']!r}); the universe has changed")
        weight = float(r["PONDERA"])
        if weight != 1.0:
            out["uniform"] = False
        rel = code_of(r["RELIGIO"], RELIGION)
        if rel is None:
            raise SystemExit(f"catalonia_ceo: RELIGIO {r['RELIGIO']!r} in wave {r['BOP_NUM']}")
        religion[prov][RELIGION[rel][1]] += weight
        lang = code_of(r["LLENGUA_PRIMERA_1_3"], FIRST)
        if lang is None:
            raise SystemExit(f"catalonia_ceo: LLENGUA_PRIMERA_1_3 "
                             f"{r['LLENGUA_PRIMERA_1_3']!r} in wave {r['BOP_NUM']}")
        label = FIRST[lang][1]
        if label is None:
            other = code_of(r["LLENGUA_PRIMERA_ALTRES"], OTHER_FIRST)
            if other is None:
                raise SystemExit(f"catalonia_ceo: LLENGUA_PRIMERA_ALTRES "
                                 f"{r['LLENGUA_PRIMERA_ALTRES']!r} for \"another answer\" in "
                                 f"wave {r['BOP_NUM']}")
            label = OTHER_FIRST[other][1]
        first[prov][label] += weight
        n[prov] += 1
        mass[prov] += weight
    if sum(n.values()) != len(rows) or set(n) != set(PROVINCES):
        raise SystemExit(f"catalonia_ceo: the provinces hold {dict(n)} of {len(rows):,} "
                         f"respondents")
    for prov, code in PROVINCES.items():
        for name, counts in (("religion", religion[prov]), ("first language", first[prov])):
            if abs(sum(counts.values()) - mass[prov]) > 1e-6:
                raise SystemExit(f"catalonia_ceo: province {code}'s {name} makes "
                                 f"{sum(counts.values()):,.2f}, its respondents {mass[prov]:,.2f}")
        out["provinces"][code] = {"n": n[prov], "religion": dict(religion[prov]),
                                  "language": dict(first[prov])}
    whole: Counter = Counter()
    for prov in PROVINCES:
        whole.update(religion[prov])
    out["catalonia"] = {"n": len(rows), "religion": dict(whole)}
    return out


def rows_of(counts: dict[str, float]) -> list[dict[str, Any]]:
    total = sum(counts.values())
    rows = [{"group": label, "pct": round(100.0 * value / total, 1)}
            for label, value in counts.items() if value > 0]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows


def describe(waves: list[int], dates: dict[int, tuple[int, int]]) -> str:
    """BOP 62 (June 2025), 63 (October 2025) and 64 (June 2026)."""
    parts = [f"{w} ({MONTHS[dates[w][1] - 1]} {dates[w][0]})" for w in waves]
    return "BOP " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0])


# What the religion question counts, beside the survey the map shows where
# this file does not reach: the European Social Survey first asks whether one
# belongs to a religion at all, and in Catalonia that is the difference between
# Catholics leading and no religion leading. The CIS's own question, which asks
# what one is "en materia religiosa", lands where this one does.
WORDING = ("The question asks which religion people have, practising or not, so it counts "
           "nominal Catholics as Catholics, as the CIS's question does; surveys that first ask "
           "whether one belongs to any religion at all, such as the European Social Survey, find "
           "fewer Catholics and more people with none.")
CENSUS = {
    "religion": ("No Spanish census since the Constitution of 1978, which provides that no one "
                 "may be obliged to declare their religion (art. 16.2), has asked it."),
    "language": ("Spain's census does not ask anyone's first or usual language: its 2021 round "
                 "was drawn from registers, and its 2011 and earlier rounds asked people in "
                 "Catalonia only how well they knew Catalan. Idescat's language survey (EULP) is "
                 "not published by province."),
}


def note(field: str, n: int, where: str, waves: str, uniform: bool) -> str:
    precision = " Low precision: under 300 respondents." if n < LOW_PRECISION else ""
    weighting = ("unweighted: the CEO's weight (PONDERA) is 1 for every respondent of these "
                 "waves, the sample being drawn in proportion to the population by province"
                 if uniform else "weighted by the CEO's coefficients (PONDERA)")
    if field == "religion":
        what = (f"{RELIGION_QUESTION} -- Catholicism, Evangelical or Protestant Christianity, "
                "Islam, Jehovah's Witnesses, Buddhism, Orthodox Christianity, Judaism, none "
                "(agnosticism), none (atheism) or another; don't know and no answer are Not "
                "stated.")
        wording = f" {WORDING}"
    else:
        what = (f"{FIRST_QUESTION}: Catalan, Spanish, both equally, Aranese, Arabic, Romanian, "
                "or other languages or combinations; don't know and no answer are Not stated.")
        wording = ""
    return (f"Centre d'Estudis d'Opinió (Generalitat de Catalunya), Baròmetre d'Opinió Política, "
            f"face-to-face waves {waves}, pooled: {what} A survey estimate, not a count: {n:,} "
            f"respondents in {where} ({weighting}).{precision} Universe: Spanish citizens aged "
            f"18 and over resident in Catalonia, so foreign residents, among whom Muslims and "
            f"Orthodox Christians are many, are not in it.{wording} Read from the CEO's "
            f"anonymised microdata on the Generalitat's open-data portal. {CENSUS[field]}")


def build(got: dict[str, Any], dates: dict[int, tuple[int, int]],
          provinces: dict[str, dict[str, Any]], comunidades: dict[str, dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    waves = describe(got["waves"], dates)
    year = max(dates[w][0] for w in got["waves"])
    basis = {"religion": "survey estimate: self-identification, Spanish citizens aged 18+",
             "language": "survey estimate: first language spoken at home as a child, Spanish "
                         "citizens aged 18+"}
    source = {"name": f"Centre d'Estudis d'Opinió, Baròmetre d'Opinió Política, {waves} "
                      f"(anonymised microdata, Dades Obertes Catalunya)",
              "url": DATASET, "year": year, "license": LICENCE}
    catalonia = comunidades[CATALONIA]
    records: list[dict[str, Any]] = []
    skipped: list[str] = []
    for code, prov in sorted(got["provinces"].items()):
        shape = provinces[code]
        if shape["parent"] != catalonia["id"]:
            raise SystemExit(f"catalonia_ceo: {shape['name']} is not drawn inside Catalonia")
        if prov["n"] < MIN_N:
            skipped.append(f"{shape['name']}: {prov['n']} respondents")
            continue
        where = f"the province of {shape['name']}"
        fields: dict[str, Any] = {"sources": []}
        for field in ("religion", "language"):
            fields[field] = rows_of(prov[field])
            fields[f"{field}_year"] = year
            fields[f"{field}_basis"] = basis[field]
            fields[f"{field}_note"] = note(field, prov["n"], where, waves, got["uniform"])
            fields["sources"].append(dict(source, field=field))
        records.append(record(
            f"ESP-CEO-{code}", shape["name"], level="admin2", parent="ESP", country="ESP",
            match_by="shape_id", shape_id=shape["id"],
            codes={"ine_province": code, "ceo_n": prov["n"]}, **fields))
    whole = got["catalonia"]
    records.append(record(
        "ESP-CEO-CA09", catalonia["name"], level="admin1", parent="ESP", country="ESP",
        match_by="shape_id", shape_id=catalonia["id"],
        codes={"ine_ccaa": CATALONIA, "ceo_n": whole["n"]},
        religion=rows_of(whole["religion"]), religion_year=year,
        religion_basis=basis["religion"],
        religion_note=note("religion", whole["n"], "Catalonia", waves, got["uniform"]),
        sources=[dict(source, field="religion")]))
    return records, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    admin1, admin2 = load_units()
    provinces, comunidades = bind(admin1, admin2)
    listing = http_get(LISTING, cache=False, timeout=120)
    assert isinstance(listing, str)
    found = series(json.loads(listing))
    log(f"  {found['title']}: {found['url']}")
    raw = http_get(found["url"], binary=True, cache=False, timeout=900)
    assert isinstance(raw, bytes)
    log(f"  {len(raw):,} bytes")

    import pyreadstat                                  # noqa: PLC0415 -- the runner has it
    with tempfile.NamedTemporaryFile(suffix=".sav") as handle:
        handle.write(raw)
        handle.flush()
        frame, meta = pyreadstat.read_sav(handle.name, usecols=COLUMNS)
    del raw
    labels = meta.variable_value_labels
    check_labels(labels.get("RELIGIO", {}), RELIGION, "RELIGIO")
    check_labels(labels.get("LLENGUA_PRIMERA_1_3", {}), FIRST, "LLENGUA_PRIMERA_1_3")
    check_labels(labels.get("LLENGUA_PRIMERA_ALTRES", {}), OTHER_FIRST, "LLENGUA_PRIMERA_ALTRES")
    names = {int(float(k)): v for k, v in labels.get("PROVINCIA", {}).items()}
    for value, code in PROVINCES.items():
        if fold(names.get(value, "")) != fold(provinces[code]["name"]):
            raise SystemExit(f"catalonia_ceo: PROVINCIA {value} is {names.get(value)!r}, the "
                             f"map's province {code} {provinces[code]['name']!r}")

    waves = sorted({int(w) for w in frame["BOP_NUM"].dropna()})[-WAVES:]
    pool = frame[frame["BOP_NUM"].isin(waves)]
    rows = pool.to_dict("records")
    dates = {}
    for wave in waves:
        part = pool[pool["BOP_NUM"] == wave]
        dates[wave] = (int(part["ANY"].mode().iat[0]), int(part["MES"].mode().iat[0]))
        log(f"  wave {wave}: {len(part):,} respondents, {dates[wave][1]}/{dates[wave][0]}")
    got = tally(rows)
    del frame, pool, rows
    records, skipped = build(got, dates, provinces, comunidades)
    for r in records:
        log(f"  {r['level']} {r['name']} (n={r['codes']['ceo_n']:,}): religion "
            + ", ".join(f"{g['group']} {g['pct']}" for g in r["religion"]))
        if isinstance(r.get("language"), list):
            log("      first language " + ", ".join(f"{g['group']} {g['pct']}"
                                                   for g in r["language"]))
    for line in skipped:
        log(f"  left out: {line}")
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
