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
    python -m scripts.fetch_census.mexico --level both
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


def read_rows(archive: zipfile.ZipFile, name: str) -> list[list[str]]:
    """Every cell of a member, as rows, with no assumption about a header.

    The dictionary does not begin with its header -- DictReader made a single
    field named "" out of a blank first line and every row came back empty.
    Nothing here needs the header anyway: the columns are found by scanning
    cells for a description, so reading rows plainly removes the assumption
    rather than correcting it. The delimiter is sniffed because INEGI is not
    consistent about it between members.
    """
    with archive.open(name) as fh:
        text = decode(fh.read())
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text, newline=""), dialect))


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
    rows = read_rows(archive, member(archive, "diccionario"))
    found: dict[str, str] = {}
    for label, phrase in RELIGION_HINTS:
        for row in rows:
            cells = [str(c or "") for c in row]
            if plain(phrase) not in plain(" ".join(cells)):
                continue
            # The column name is the short upper-case token on the row; the
            # rest of it is prose and a value range.
            codes = [c.strip() for c in cells
                     if c.strip().isupper() and 3 <= len(c.strip()) <= 16
                     and " " not in c.strip()]
            if codes:
                found[label] = codes[0]
                break
    missing = [label for label, _ in RELIGION_HINTS if label not in found]
    if missing:
        # Say what the dictionary actually looks like. "Not found" on its own
        # sends the next person guessing at encodings and column names, which
        # is how two runs were already spent; the rows are right here.
        sample = [" | ".join(row)[:130] for row in rows[:4]]
        religious = [" | ".join(row)[:130] for row in rows
                     if "relig" in plain(" ".join(row))][:6]
        raise SystemExit(
            f"religion columns not found for {missing}.\n"
            f"  dictionary rows: {len(rows)}\n"
            f"  widest row: {max((len(r) for r in rows), default=0)} cells\n"
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
    entidad = (row.get("ENTIDAD") or "").strip()
    mun = (row.get("MUN") or "").strip()
    loc = (row.get("LOC") or "").strip()
    # All three codes have to be zero for the nation, not just the first.
    # Entity 00 also carries national sub-totals, and treating every one of
    # them as "the nation" ran the published-figure check against a row holding
    # 250,354 people -- which is how this was found.
    if entidad == "00":
        return "nation" if mun == "000" and loc == "0000" else "national subtotal"
    if mun == "000":
        return "state" if loc == "0000" else "state subtotal"
    if loc == "0000":
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


# CGAZ carries the pre-2016 name for Mexico City. INEGI uses the current one,
# so the boundary file and the census disagree about the parent of sixteen
# alcaldias; the alias is how the matcher is told they are the same place.
STATE_ALIASES = {"Ciudad de México": ["Distrito Federal", "Mexico City"]}


def build(levels: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Records for the requested levels, from one pass over the 190 MB file.

    Both levels are read together because the archive is downloaded, unzipped
    and scanned once either way; asking for states and municipios separately
    costs two full passes to answer from the same rows.
    """
    archive = load()
    religion = religion_columns(archive)
    data = member(archive, "conjunto_de_datos")
    log(f"  reading {data}")

    out: dict[str, list[dict[str, Any]]] = {level: [] for level in levels}
    seen: dict[str, int] = {}
    checked = False
    for row in read_csv(archive, data):
        kind = level_of(row)
        seen[kind] = seen.get(kind, 0) + 1
        if kind == "nation":
            if not checked:
                check_national(row)
                checked = True
            continue
        if kind not in out:
            continue

        municipal = kind == "municipality"
        state = (row.get("NOM_ENT") or "").strip()
        name = (row.get("NOM_MUN") or "").strip() if municipal else state
        code = f'{(row.get("ENTIDAD") or "").strip()}{(row.get("MUN") or "").strip()}'
        total = number(row.get("POBTOT"))
        fields = compose(row, religion)

        out[kind].append(record(
            f"MEX-{code}",
            name,
            level="admin2" if municipal else "admin1",
            parent=f'MEX-{(row.get("ENTIDAD") or "").strip()}' if municipal else "MEX",
            country="MEX",
            # Municipio names repeat across states -- there is a Hidalgo in
            # several -- so the state travels with the row for the matcher.
            aliases=None if municipal else STATE_ALIASES.get(state),
            parent_name=state if municipal else None,
            parent_aliases=STATE_ALIASES.get(state) if municipal else None,
            codes={"inegi": code},
            population=(measure(int(total), year=YEAR, source=SOURCE)
                        if total else gap(NOT_AVAILABLE)),
            sources=[{"field": "religion/language/ethnicity", "name": SOURCE,
                      "url": URL, "license": LICENSE}],
            **fields,
        ))
    if not checked:
        raise SystemExit("no national row (ENTIDAD 00, MUN 000, LOC 0000) to "
                         "check the published figures against")
    log(f"  rows by level: {seen}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="both",
                    choices=["state", "municipality", "both"])
    ap.add_argument("--out", type=Path, default=None,
                    help="write to this path instead of data/processed "
                         "(one level only)")
    args = ap.parse_args()

    levels = ["state", "municipality"] if args.level == "both" else [args.level]
    if args.out and len(levels) > 1:
        raise SystemExit("--out writes one file; pick a single --level")

    built = build(set(levels))
    for level in levels:
        name = ("mexico_state.json" if level == "state"
                else "mexico_municipality.json")
        write_json(args.out or (PROCESSED / name), built[level])
        log(f"  {len(built[level])} {level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
