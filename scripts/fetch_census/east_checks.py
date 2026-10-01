#!/usr/bin/env python3
"""Cross-checks shared by the eastern census adapters.

One for now: a country's median age, recomputed from the same five-year
groups the adapter interpolates its units' medians from, against Eurostat's
(``demo_pjanind``, MEDAGEPOP), which Eurostat computes from the national
office's single years. The brief bounds the two at 0.3 years; the bound
measures the interpolation and the reading together, so a misread column or
a shifted age group -- the faults that move a median by years -- stops the
run, and the width of a five-year group does not.

Eurostat's figure is looked up through ``nordic_common.published_median``.
"""

from __future__ import annotations

from ._shared import log
from .nordic_common import MEDIAN_TOLERANCE, published_median

# A population ages by a few tenths of a year in a year: against the year
# before, the bound widens by this much, as the Nordic adapters' check does.
YEAR_APART = 0.4


def check_median(geo: str, year: int, ours: float | None, what: str,
                 basis: str = "five-year groups") -> str:
    """Stop if ``ours`` is further from Eurostat's median than the bound.

    Against Eurostat's figure for ``year``, or failing that the year before
    with the bound widened; with neither, the run says so and goes on.
    Returns the line logged, so a caller can put it in a note.
    """
    if ours is None:
        line = f"{what}: no national median to check"
        log("  " + line)
        return line
    theirs, why = published_median(geo, year)
    bound, when = MEDIAN_TOLERANCE, year
    if theirs is None:
        theirs, why_before = published_median(geo, year - 1)
        if theirs is None:
            line = (f"{what}: national median {ours} from {basis}; Eurostat publishes "
                    f"none to check it against ({why}; {why_before})")
            log("  " + line)
            return line
        bound, when = MEDIAN_TOLERANCE + YEAR_APART, year - 1
    line = (f"{what}: national median {ours} from {basis}, against Eurostat's {theirs} for "
            f"1 January {when} ({ours - theirs:+.2f} years, bound {bound:.1f})")
    log("  " + line)
    if round(abs(ours - theirs), 2) > bound:
        raise SystemExit(f"{what}: the national median recomputed from {basis}, {ours}, is "
                         f"{ours - theirs:+.2f} years off Eurostat's {theirs} for 1 January "
                         f"{when}")
    return line
