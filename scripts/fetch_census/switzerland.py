#!/usr/bin/env python3
"""Switzerland -- main languages by canton, from the FSO structural survey.

The Federal Statistical Office publishes main languages by canton as a
spreadsheet rather than through an API, so it lives in
``data/raw/switzerland/`` and is read from disk.

Two properties of this table decide what the records are allowed to claim.

**A person may name up to three main languages**, so the columns sum to about
119% of the population nationally and the shares are of *responses*, not of
people. That is the same shape as Australian ancestry, and it is stated on every
record rather than left for a reader to notice that the bars overflow.

**It is a survey, not a census.** Every figure ships with a confidence interval,
some of them enormous -- Uri's French estimate carries +/-57%. Estimates whose
interval exceeds :data:`MAX_INTERVAL` are dropped rather than shown, because a
share of 0.9% that could be anywhere between 0.4% and 1.4% is not a fact about
Uri, and 'X' marks cells the FSO suppressed outright for disclosure control.

So the records go to ``switzerland_language_survey.json`` with a
``language_basis`` that begins "survey estimate", which the build ranks
behind any count, and each note gives the sample the FSO drew in the canton
that year (from its stratification table, as ``switzerland_religion`` reads
it). The survey's weighted total is the population in private households,
not the canton's population, so no population is written.

Usage:
    python -m scripts.fetch_census.switzerland
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, log, record, shares, write_json,
)
from .central_ages import fold
from .switzerland_religion import sample_drawn

WORKBOOK = RAW / "switzerland" / "languages_canton_se2024.xlsx"
SHEET = "Canton"
SOURCE = "Office fédéral de la statistique (OFS), relevé structurel 2024"
PORTAL = "https://www.bfs.admin.ch/"
YEAR = 2024
OUT = PROCESSED / "switzerland_language_survey.json"
BASIS = ("survey estimate: structural survey 2024, permanent resident population in private "
         "households, up to three main languages a person")

# Column index -> display label. Each is followed by its confidence interval.
LANGUAGES = {5: "German", 7: "French", 9: "Italian", 11: "Romansh",
             13: "English", 15: "Other languages"}
TOTAL_COLUMN = 3
# Cantons are named in column 2; the sheet's own national row puts "Total" in
# column 1 and leaves column 2 empty. Reading only column 2 drops that row, and
# the reconciliation below then compares the canton sum against itself.
NAME_COLUMN = 2
LABEL_COLUMN = 1
FIRST_DATA_ROW = 5          # the sheet's own Total row, then the 26 cantons

# Beyond this half-width, in percent of the estimate, the figure says more about
# the sample than about the canton.
MAX_INTERVAL = 25.0

# The workbook writes cantons bilingually; the boundary files pick one name.
CANTON_ALIASES = {
    "Bern / Berne": "Bern",
    "Fribourg / Freiburg": "Fribourg",
    "Graubünden / Grigioni / Grischun": "Graubünden",
    "Valais / Wallis": "Valais",
}

NOTE = (
    "FSO structural survey 2024: main languages, of which a person may name up "
    "to three. The shares are therefore of responses rather than of people and "
    "sum to more than 100% -- nationally about 119%. It is a sample survey, so "
    "every figure is an estimate; those whose confidence interval exceeded "
    f"±{MAX_INTERVAL:.0f}% of the estimate have been dropped rather than shown. "
    "The census has not asked every resident since 2000.")


def clean(name: Any) -> str:
    text = " ".join(str(name or "").replace("/", " / ").split())
    return CANTON_ALIASES.get(text, text)


def number(value: Any) -> float | None:
    """A weighted estimate, or None where the FSO withheld or omitted it.

    'X' marks a cell suppressed for disclosure control -- fewer than five
    observations behind it -- and is emphatically not zero.
    """
    if isinstance(value, (int, float)):
        return float(value)
    return None


def read(path: Path) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit("pip install openpyxl to read the FSO workbook") from exc
    if not path.exists():
        raise SystemExit(f"missing workbook: {path}")

    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True)[SHEET]
                .iter_rows(values_only=True))
    out = []
    for row in rows[FIRST_DATA_ROW:]:
        name = clean(row[NAME_COLUMN]) or clean(row[LABEL_COLUMN])
        total = number(row[TOTAL_COLUMN])
        if not name or not total:
            continue
        counts, dropped = {}, []
        for index, label in LANGUAGES.items():
            value = number(row[index])
            interval = number(row[index + 1])
            if value is None:
                dropped.append(f"{label} (suppressed)")
                continue
            if interval is not None and interval > MAX_INTERVAL:
                dropped.append(f"{label} (±{interval:.0f}%)")
                continue
            counts[label] = value
        out.append({"name": name, "total": total, "counts": counts,
                    "dropped": dropped})
    return out


def check(cantons: list[dict[str, Any]], national: dict[str, Any]) -> None:
    """The cantons must reproduce the sheet's own national row."""
    if not national["counts"]:
        # Checked first: an empty national row means the language columns were
        # not found at all, and reporting that as a canton-count mismatch would
        # send the next reader looking in the wrong place.
        raise SystemExit("the national row carries no language columns")
    summed = sum(c["total"] for c in cantons)
    expected = national["total"]
    if abs(summed - expected) > 1:
        raise SystemExit(f"cantons sum to {summed:,.0f}, the sheet's national row "
                         f"says {expected:,.0f}")
    if len(cantons) != 26:
        raise SystemExit(f"expected 26 cantons, read {len(cantons)}")
    overflow = 100.0 * sum(national["counts"].values()) / expected
    log(f"  26 cantons summing to {summed:,.0f}, matching the national row; "
        f"languages total {overflow:.1f}% of it (multiple answers allowed)")


def build(cantons: list[dict[str, Any]], drawn: dict[str, float]) -> list[dict[str, Any]]:
    """One record a canton; ``drawn`` is the sample the FSO drew there, by canton name."""
    by_fold = {fold(k): v for k, v in drawn.items()}
    out = []
    for canton in cantons:
        n = by_fold.get(fold(canton["name"]))
        if n is None:
            raise SystemExit(f"no sample size for {canton['name']}")
        if n < 100:
            raise SystemExit(f"{canton['name']}: only {n:,.0f} people drawn")
        note = NOTE + (f" Sample: the FSO drew about {n:,.0f} people aged 15 and over in the "
                       f"canton in {YEAR} (its population considered times its sampling rate, "
                       f"from the FSO's stratification table cc-t-40-se_strata-{YEAR})"
                       + ("; low precision." if n < 300 else "."))
        if canton["dropped"]:
            note += (" Not shown for this canton: "
                     + ", ".join(canton["dropped"]) + ".")
        out.append(record(
            f"CHE-{canton['name'].replace(' ', '-')}", canton["name"],
            level="admin1", parent="CHE", codes={"canton": canton["name"]},
            language=shares(canton["counts"], total=canton["total"]) or gap(NOT_AVAILABLE),
            language_note=note,
            language_year=YEAR,
            language_basis=BASIS,
            sources=[{"field": "language", "name": SOURCE, "url": PORTAL,
                      "year": YEAR,
                      "note": "Permanent resident population in private "
                              "households; diplomats and people in collective "
                              "households are excluded."}],
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=WORKBOOK)
    args = ap.parse_args()

    rows = read(args.input)
    national = next((r for r in rows if r["name"] == "Total"), None)
    if national is None:
        raise SystemExit("the sheet's national Total row is missing; without it "
                         "the canton sum has nothing independent to check against")
    cantons = [r for r in rows if r is not national]
    check(cantons, national)
    out = build(cantons, sample_drawn([YEAR]))
    log(f"  {len(out)} cantons with main-language shares")
    write_json(OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
