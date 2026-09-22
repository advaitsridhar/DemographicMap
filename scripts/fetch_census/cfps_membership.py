#!/usr/bin/env python3
"""China: membership of a religious organisation, by province, from CFPS.

A different question from the one cfps_microdata.py reads, and a different
field, because conflating them would be the error this file exists to avoid.

CFPS asked adults what religion they belonged to in 2012 and what they
believed in in 2016, and those two waves are what `religion` is built from.
It stopped asking after that. 2014 and 2018 ask instead which deities a
person believes in -- Buddha, Immortal, Allah, Catholic God, Jesus Christ,
Ancestor, Ghost, Feng shui -- which is multi-select and non-exclusive, so it
cannot make a composition: one person answers yes to three of them, the
shares do not sum to a hundred, and "no religion" is not derivable. 2020 and
2022 drop even that.

What all of 2018, 2020 and 2022 do carry is `qn4004`, "Are you a member of
religious group", asked yes or no alongside membership of the Communist
Party, the Youth League and the trade union. That is a rate, not a
composition, so it is written as one: a scalar share with its year, its
weighted base and its sample size, on its own field.

**It is not religiosity and the field name must not suggest it is.** China's
religious life is overwhelmingly unaffiliated with any organisation; the
2016 affiliation question put Shanghai's "no religion" at 86.7% while this
question puts organisational membership across five provinces between 2 and
4%. They measure different things and the map shows them as different things.

**Five provinces, for the reason cfps_microdata.py gives at length.** CFPS
drew Shanghai, Liaoning, Henan, Gansu and Guangdong as self-representative
subsamples; the other twenty come from a pooled frame that represents the
pool and not its members, and the survey's own report says province-level
inference is supported for the five alone. More waves do not change that --
it is the sampling design, not the sample size.

The microdata never enters the repository. This reads the public release a
registered user obtains from ISSS, under `--root`, and writes only the
province aggregates. CFPS's data-use terms additionally require that any
analysis below the provincial level be done in ISSS's enclave, so this never
touches a variable finer than the province code.

Usage:
    python -m scripts.fetch_census.cfps_membership --root /path/to/waves
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import NOT_AVAILABLE, gap                      # noqa: E402
from ._shared import PROCESSED, log, record, write_json    # noqa: E402
from .cfps_microdata import (PROVINCES, SELF_REPRESENTATIVE,  # noqa: E402
                             read_wave, wave_file)

OUT = "cfps_membership_province.json"
FIELD = "religious_membership"
LICENCE = "Aggregates of CFPS microdata; compilation CC BY-SA 4.0"

# Newest first: the newest wave a province appears in is the one written.
#
# The stems carry the "e" ISSS puts on its English releases (ecfps2022person).
# The Kaggle re-upload cfps_microdata.py targets drops it, so both spellings
# are tried -- the wave and questionnaire are the same file either way, and a
# reader that only knew one would silently find nothing and report zero
# provinces, which is what it did the first time this was run.
WAVES: list[tuple[int, str, str, str, str]] = [
    (2022, "ecfps2022person_202410", "provcd22", "qn4004", "rswt_natcs22n"),
    (2020, "ecfps2020person_202306", "provcd20", "qn4004", "rswt_natcs20n"),
    (2018, "ecfps2018person_202012", "provcd18", "qn4004", "rswt_natcs18n"),
]


def find_wave(root: Path, stem: str) -> Path | None:
    """The wave file under either the English or the Kaggle spelling."""
    for candidate in (stem, stem[1:] if stem.startswith("e") else "e" + stem):
        found = wave_file(root, candidate)
        if found is not None:
            return found
    return None

# CFPS codes a refusal or a don't-know negative. They are not "no": counting
# them as one would report a lower membership rate than the survey found.
YES, NO = 1, 0
# A share from a handful of respondents is not a share. Shanghai's 2022 cell
# is 25 yes of 847, which is thin and publishable with its size stated; a
# province with a tenth of that is not.
MIN_SAMPLE = 300


def rate(rows: list[tuple[int, int, float | None]], code: int
         ) -> tuple[float, float, int] | None:
    """(weighted %, weighted base, sample size) for one province."""
    here = [(a, w) for p, a, w in rows
            if p == code and a in (YES, NO) and w is not None]
    if len(here) < MIN_SAMPLE:
        return None
    base = sum(w for _a, w in here)
    if base <= 0:
        return None
    yes = sum(w for a, w in here if a == YES)
    return 100.0 * yes / base, base, len(here)


def build(root: Path) -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for year, stem, prov, ans, weight in WAVES:
        if find_wave(root, stem) is None:
            log(f"  {year}: {stem}.dta not found, skipped")
            continue
        rows = read_wave(find_wave(root, stem).parent,
                         find_wave(root, stem).stem, prov, ans, weight)
        took = 0
        for code in sorted(SELF_REPRESENTATIVE):
            if code in seen:
                continue
            got = rate(rows, code)
            if got is None:
                log(f"    {PROVINCES[code]}: too few answers in {year}")
                continue
            share, base, n = got
            seen.add(code)
            took += 1
            name = PROVINCES[code]
            out.append(record(
                f"CHN-admin1-{code}", name, level="admin1", parent="CHN",
                **{FIELD: {"value": round(share, 1), "unit": "%", "year": year,
                           "source": f"China Family Panel Studies {year}"},
                   f"{FIELD}_note":
                       f"Share of adults answering yes to \"are you a member "
                       f"of religious group\" (qn4004), weighted by the wave's "
                       f"cross-sectional individual weight. {n:,} respondents "
                       f"answered in {name}. This is membership of an "
                       f"organisation and not religious belief: CFPS's 2016 "
                       f"affiliation question is a different question and is "
                       f"the source of this province's religion composition.",
                   "sources": [{"field": FIELD,
                                "name": f"China Family Panel Studies {year}, "
                                        f"qn4004, by province, weighted",
                                "licence": LICENCE, "year": year,
                                "url": "https://www.isss.pku.edu.cn/cfps/"}]}))
        log(f"  {year}: {took} province(s)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True,
                    help="directory holding the public-release wave files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = build(args.root)
    log(f"\nCFPS membership: {len(rows)} province(s) of "
        f"{len(SELF_REPRESENTATIVE)} self-representative")
    for r in rows:
        log(f"  {r['name']:<24}{r[FIELD]['value']:>5}%  ({r[FIELD]['year']})")
    if args.dry_run:
        log("--dry-run: nothing written")
        return 0
    write_json(PROCESSED / OUT, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
