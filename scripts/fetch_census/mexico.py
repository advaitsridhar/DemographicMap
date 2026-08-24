#!/usr/bin/env python3
"""Mexico -- INEGI Censo de Población y Vivienda 2020, by municipio.

The ITER release ("Principales resultados por localidad") is one CSV covering
every locality, municipio, state and the nation, and it carries three of the
things this map wants: religion, whether a person speaks an indigenous
language, and Afro-descendant self-identification. All of it comes from the
*cuestionario básico*, asked of everyone, so these are counts rather than
sample estimates -- which is why Mexico can be shown at municipio level at all.

That makes it the largest single addition available to this project: some 2,470
municipios, more subnational units carrying religion than everything on the map
outside the United States and India.

Three things about the file decide how it is read.

**The columns are named by the office and documented beside the data.** The
archive ships its own dictionary, so rather than hardcode ``PCATOLICA`` and
guess at the rest, the religion columns are found by reading the descriptions.
A guessed column name that INEGI renamed between rounds would fail as a missing
key at build time; derived names fail as a loud mismatch here instead.

**One file holds four levels of geography.** The nation is ENTIDAD 00, a state
is MUN 000, a municipio is LOC 0000, and everything else is an individual
locality -- 190,000 of them. Reading without filtering sums the country several
times over.

**Two of the three fields are yes/no, not compositions.** The census records
*whether* someone speaks an indigenous language here, not which one; the
language itself lives in other tables. So the shares are two-category and the
note says so, because "Mexico: indigenous language 6.1%" beside India's mother
tongues would otherwise read as the same kind of measurement.

Usage:
    python -m scripts.fetch_census.mexico --level municipality
"""

from __future__ import annotations

import argparse
import csv
import io
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, http_get, log, measure, record, shares,
    write_json,
)

SOURCE = "INEGI, Censo de Población y Vivienda 2020 (ITER)"
YEAR = 2020
URL = ("https://www.inegi.org.mx/contenidos/programas/ccpv/2020/"
       "datosabiertos/iter/iter_00_cpv2020_csv.zip")

# INEGI publishes under its own free-use terms: reuse and redistribution are
# permitted with attribution to the source.
LICENSE = ("Términos de Libre Uso de la Información del INEGI "
           "(attribution required)")

# Published national figures, from INEGI's own 2020 results. The file must
# reproduce them or it is not the file this adapter was written against.
NATIONAL = {
    "POBTOT": 126_014_024,
    "P3YM_HLI": 7_364_645,
    "POB_AFRO": 2_576_213,
}
TOLERANCE = 0.0001

# The dictionary describes every column; these are the phrases that identify
# the ones worth mapping. Matching on the description rather than the column
# name means a renamed column is found, and a column whose meaning changed is
# not silently kept.
RELIGION_HINTS = (
    ("Catholic", "religión católica"),
    ("Protestant and evangelical", "protestante"),
    ("Other religions", "otras religiones"),
    ("No religion", "sin religión"),
)


def load(url: str = URL) -> zipfile.ZipFile:
    blob = http_get(url, binary=True, cache_dir=RAW / "mexico")
    if not blob.startswith(b"PK"):
        # INEGI answers a wrong path with HTTP 200 and an HTML page, so a
        # successful request proves nothing about what came back.
        raise SystemExit(f"{url} did not return a zip: {blob[:120]!r}")
    return zipfile.ZipFile(io.BytesIO(blob))


def member(archive: zipfile.ZipFile, part: str) -> str:
    names = [n for n in archive.namelist()
             if part in n.lower() and n.lower().endswith(".csv")]
    if not names:
        raise SystemExit(f"no {part!r} CSV in the archive: {archive.namelist()}")
    return max(names, key=lambda n: archive.getinfo(n).file_size)


def decode(raw: bytes) -> str:
    """UTF-8 if it is UTF-8, latin-1 if it is not.

    The archive mixes both, and guessing wrong is not a crash: latin-1 accepts
    every byte, so a UTF-8 file read as latin-1 turns "religión" into
    "religiÃ³n" and every description match silently fails. Trying UTF-8 first
    and falling back only on a real decode error gets each member right.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_csv(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as fh:
        text = io.StringIO(decode(fh.read()), newline="")
    for row in csv.DictReader(text):
        yield {(k or "").lstrip("﻿"): v for k, v in row.items()}


def plain(text: str) -> str:
    """Lower case with the accents removed.

    Matching a description against "religión católica" should not depend on
    which encoding the member happened to be written in, nor on whether INEGI
    accented a word this round. Comparing without accents removes the question.
    """
    stripped = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower()


def religion_columns(archive: zipfile.ZipFile) -> dict[str, str]:
    """Map a display name to the column INEGI uses for it, from the dictionary.

    The dictionary is a flat CSV whose rows carry a description and a column
    name among their fields, so the column is taken as the short upper-case
    token on the row whose description names the group.
    """
    rows = list(read_csv(archive, member(archive, "diccionario")))
    found: dict[str, str] = {}
    for label, phrase in RELIGION_HINTS:
        for row in rows:
            values = [str(v or "") for v in row.values()]
            blob = plain(" ".join(values))
            if plain(phrase) not in blob:
                continue
            codes = [v.strip() for v in values
                     if v.strip().isupper() and 3 <= len(v.strip()) <= 16
                     and " " not in v.strip()]
            if codes:
                found[label] = codes[0]
                break
    missing = [label for label, _ in RELIGION_HINTS if label not in found]
    if missing:
        # Say what the dictionary actually looks like. "Not found" on its own
        # sends the next person guessing at encodings and column names, which
        # is how two runs were already spent; the rows are right here.
        sample = [" | ".join(str(v) for v in row.values())[:130] for row in rows[:4]]
        religious = [" | ".join(str(v) for v in row.values())[:130] for row in rows
                     if "relig" in plain(" ".join(str(v) for v in row.values()))][:6]
        raise SystemExit(
            f"religion columns not found for {missing}.\n"
            f"  dictionary rows: {len(rows)}\n"
            f"  fields: {list(rows[0]) if rows else 'none'}\n"
            f"  first rows:\n    " + "\n    ".join(sample) +
            f"\n  rows mentioning religion ({len(religious)}):\n    " +
            "\n    ".join(religious))
    log(f"  religion columns: {found}")
    return found


def number(value: Any) -> float | None:
    """A count, or None where INEGI withheld or suppressed it.

    The file uses '*' for values suppressed to protect confidentiality and 'N/D'
    for not determined. Reading either as zero would turn a withheld figure into
    a claim that nobody there is anything.
    """
    text = str(value or "").strip()
    if not text or text in {"*", "N/D", "N/A", "-"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def level_of(row: dict[str, str]) -> str:
    """Which of the four geographies a row is.

    ENTIDAD 00 is the country, MUN 000 a state, LOC 0000 a municipio, and
    anything else one of the 190,000 individual localities. Summing the file
    without this counts Mexico four times.
    """
    if (row.get("ENTIDAD") or "").strip() == "00":
        return "nation"
    if (row.get("MUN") or "").strip() == "000":
        return "state"
    if (row.get("LOC") or "").strip() == "0000":
        return "municipality"
    return "locality"


def check_national(row: dict[str, str]) -> None:
    """The nation row must reproduce INEGI's published figures.

    These are numbers the file did not produce -- they come from the results
    INEGI announced -- so unlike a shares-add-up test this cannot be satisfied
    by a mis-parse that happens to be internally consistent.
    """
    for column, published in NATIONAL.items():
        got = number(row.get(column))
        if got is None:
            raise SystemExit(f"national row has no {column}")
        drift = abs(got - published) / published
        log(f"  {column}: {got:,.0f} vs published {published:,} ({drift:.4%})")
        if drift > TOLERANCE:
            raise SystemExit(
                f"{column} is {drift:.2%} from the published figure; this is "
                "not the release the adapter was written against")


def compose(row: dict[str, str], religion: dict[str, str]) -> dict[str, Any]:
    """The three fields, as compositions, from one area's row."""
    total = number(row.get("POBTOT"))
    out: dict[str, Any] = {}

    counts = {label: number(row.get(column)) for label, column in religion.items()}
    counts = {k: v for k, v in counts.items() if v is not None}
    # INEGI's four religion groups are asked of everyone, so what they leave
    # over is people who did not state one -- named rather than dropped, so the
    # bar reaches 100% without implying the remainder is irreligious.
    if counts and total:
        stated = sum(counts.values())
        if total - stated > 0:
            counts["Not stated"] = total - stated
        out["religion"] = shares(counts, total=total)
        out["religion_year"] = YEAR

    speakers = number(row.get("P3YM_HLI"))
    base = number(row.get("P_3YMAS")) or total
    if speakers is not None and base:
        out["language"] = shares(
            {"Speaks an indigenous language": speakers,
             "Does not speak an indigenous language": max(base - speakers, 0.0)},
            total=base)
        out["language_year"] = YEAR
        out["language_note"] = (
            "The census records whether a person aged 3 or over speaks an "
            "indigenous language, not which one, so this is a yes/no split "
            "rather than a composition of languages. Which language is asked, "
            "and published in other INEGI tables, but not in this one.")

    afro = number(row.get("POB_AFRO"))
    if afro is not None and total:
        out["ethnicity"] = shares(
            {"Afro-Mexican or Afro-descendant": afro,
             "Not Afro-descendant": max(total - afro, 0.0)},
            total=total)
        out["ethnicity_year"] = YEAR
        out["ethnicity_note"] = (
            "Self-identification as Afro-Mexican or Afro-descendant, asked of "
            "everyone in the 2020 census. It is a single yes/no question, not a "
            "classification of the whole population, so the complement means "
            "'did not identify as Afro-descendant' and not membership of any "
            "other group. Not comparable with other countries' ethnicity "
            "categories.")
    return out


def build(level: str) -> list[dict[str, Any]]:
    archive = load()
    religion = religion_columns(archive)
    data = member(archive, "conjunto_de_datos")
    log(f"  reading {data}")

    out: list[dict[str, Any]] = []
    seen = {"nation": 0, "state": 0, "municipality": 0, "locality": 0}
    for row in read_csv(archive, data):
        kind = level_of(row)
        seen[kind] += 1
        if kind == "nation":
            check_national(row)
            continue
        if kind != level:
            continue

        state = (row.get("NOM_ENT") or "").strip()
        name = (row.get("NOM_MUN") or "").strip() if level == "municipality" else state
        code = f'{(row.get("ENTIDAD") or "").strip()}{(row.get("MUN") or "").strip()}'
        total = number(row.get("POBTOT"))
        fields = compose(row, religion)

        out.append(record(
            f"MEX-{code}",
            name,
            level="admin2" if level == "municipality" else "admin1",
            parent=f'MEX-{(row.get("ENTIDAD") or "").strip()}' if level == "municipality" else "MEX",
            country="MEX",
            # Municipio names repeat across states -- there is a Hidalgo in
            # several -- so the state travels with the row for the matcher.
            parent_name=state if level == "municipality" else None,
            codes={"inegi": code},
            population=(measure(int(total), year=YEAR, source=SOURCE)
                        if total else gap(NOT_AVAILABLE)),
            sources=[{"field": "religion/language/ethnicity", "name": SOURCE,
                      "url": URL, "license": LICENSE}],
            **fields,
        ))
    log(f"  rows by level: {seen}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="municipality",
                    choices=["state", "municipality"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    records = build(args.level)
    name = "mexico_state.json" if args.level == "state" else "mexico_municipality.json"
    write_json(args.out or (PROCESSED / name), records)
    log(f"  {len(records)} {args.level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
