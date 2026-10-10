#!/usr/bin/env python3
"""Every parent against the complete sum of its divisions, and what says why they differ.

A first-level unit's population and the populations of the second-level
divisions drawn inside it are two answers to one question. Where every
non-water division carries a figure, their total is comparable with the
unit's own, and the two should agree; the same holds for a country and its
first level. When they disagree by more than ``GAP`` (15%), the reader is
owed a sentence saying why -- older children under a newer estimate, two
sources placing people differently, ground the map draws elsewhere -- in the
parent's population note. This lists every such disagreement whose parent
says nothing about it.

The build writes that sentence itself (build_entities.note_population_gaps)
using the same helpers, so a disagreement this finds after a build is one
the build could not see: a note that names neither the divisions' total nor
the difference between the two. The unit test (tests/test_round6_rollups.py)
runs this on site/data and fails on any gap not in ``ROLLUP_ALLOWLIST``, the
file of known gaps with their reasons.

Usage:
    python3 scripts/check_rollups.py            # site/data
    python3 scripts/check_rollups.py --data DIR --all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "site" / "data"
ALLOWLIST = ROOT / "tests" / "rollup_allowlist.json"

# How far a parent and the complete sum of its divisions may differ before
# the parent's note must say why. The audits of this round used the same.
GAP = 0.15
# How close a number in a note must come to a total for the note to be
# taken as naming it: the sum of rounded or slightly later figures.
NAMED = 0.005


def published(value: Any) -> float | None:
    if isinstance(value, dict) and isinstance(value.get("value"), (int, float)) \
            and not isinstance(value.get("value"), bool):
        return float(value["value"])
    return None


def vintage(value: Any) -> int | None:
    if isinstance(value, dict) and isinstance(value.get("year"), int):
        return value["year"]
    return None


def is_encyclopaedic(value: Any) -> bool:
    """A figure an encyclopaedia gives: Wikidata's, or a Wikipedia article's."""
    src = str(value.get("source") or "") if isinstance(value, dict) else ""
    return bool(re.search(r"\bWikidata\b|\bWikipedia\b", src))


def short_source(source: str) -> str:
    """A source as a sentence can name it."""
    if "Common Operational Dataset" in source:
        return "OCHA's common operational dataset"
    if source.startswith("Wikidata"):
        return "Wikidata"
    if "Wikipedia" in source:
        return "Wikipedia"
    if source.startswith("summed from"):
        return "sums of their own divisions"
    head = re.split(r",|;| -- | \(", source, maxsplit=1)[0].strip()
    return head or "an unnamed source"


def complete_sum(children: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """The total of children that all carry a population, with what they are.

    None when there are no children or any of them lacks a figure: a partial
    sum says nothing about the parent.
    """
    kids = [c for c in children if not c.get("water")]
    if not kids:
        return None
    values = [published(c.get("population")) for c in kids]
    if any(v is None for v in values):
        return None
    sources = {str((c.get("population") or {}).get("source") or "") for c in kids}
    years = {vintage(c.get("population")) for c in kids}
    return {"total": sum(values), "n": len(kids), "sources": sources, "years": years}


NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")


def numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in NUMBER.findall(text or "")]


def explained(texts: Iterable[str], own: float, total: float) -> bool:
    """Whether a note already accounts for the divisions' total.

    It does when it names that total, or the difference between it and the
    figure, to within rounding: "the 7 divisions drawn here add up to
    1,234,567" and "which leaves 52,871 for Yeonggwang-gun" both say it.
    """
    gap = abs(total - own)
    for text in texts:
        for n in numbers(text):
            if total and abs(n - total) <= NAMED * total:
                return True
            if gap and abs(n - gap) <= NAMED * gap:
                return True
    return False


def notes_of(entity: dict[str, Any]) -> list[str]:
    pop = entity.get("population")
    return [str(entity.get("population_note") or ""),
            str(pop.get("note") or "") if isinstance(pop, dict) else ""]


def disagrees(own: float, total: float) -> bool:
    return bool(own) and abs(total / own - 1) > GAP


def gap_sentence(summed: dict[str, Any], own: float, own_year: int | None,
                 level: str = "divisions", own_source: str | None = None) -> str:
    """What the divisions add up to, and the one reason the data itself gives.

    The reason is said only where the figures show it: the divisions counted
    in another year than the parent, or two sources' estimates of one year.
    Where parent and divisions are one source and one year and still differ,
    the divisions drawn are not the ground the parent's figure counts, and
    which ground is a question the figures cannot answer, so nothing is said
    beyond the arithmetic.
    """
    n, total = summed["n"], summed["total"]
    sources = sorted(s for s in summed["sources"] if s)
    years = sorted(y for y in summed["years"] if y is not None)
    undated = None in summed["years"]
    # Named as a reader knows them: twenty-two Wikipedia articles are one
    # source here, not twenty-two.
    named = sorted({short_source(s) for s in sources})
    if len(named) == 1:
        what = named[0]
    else:
        what = f"{len(named)} sources"
    if len(years) == 1:
        when = f", {years[0]}" + (" and undated" if undated else "")
    elif years:
        when = f", {years[0]} to {years[-1]}" + (" and undated" if undated else "")
    else:
        when = ", undated"
    pct = 100 * (total - own) / own
    side = "above" if total > own else "below"
    one = n == 1
    said = (f"{'The one' if one else f'Its {n}'} {level[:-1] if one else level} drawn on "
            f"this map {'carries' if one else 'add up to'} {total:,.0f} ({what}{when}), "
            f"{abs(pct):.0f}% {side} this figure")
    if len(years) == 1 and not undated and own_year and years[0] != own_year:
        gap = abs(years[0] - own_year)
        said += (f"; {'its figure is' if one else 'their figures are'} for {years[0]}, "
                 f"{gap} year{'s' if gap != 1 else ''} "
                 f"{'before' if years[0] < own_year else 'after'} this one")
    elif (len(years) == 1 and not undated and own_year == years[0] and len(sources) == 1
          and own_source is not None and own_source != sources[0]):
        said += "; the two are different sources' figures for the same year"
        # Inside a country, two estimates of one year that differ have put the
        # same people in different places. Two national totals that differ
        # have counted different people -- residents only, or everyone -- and
        # the figures alone cannot say which.
        if level == "divisions":
            said += ", which place people differently"
    return said + "."


def load(data: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]],
                              dict[str, list[dict[str, Any]]], set[str]]:
    admin0 = json.loads((data / "admin0.json").read_text(encoding="utf-8"))
    tables: dict[str, dict[str, list[dict[str, Any]]]] = {"admin1": {}, "admin2": {}}
    for level, table in tables.items():
        for path in sorted((data / level).glob("*.units.json")):
            table[path.name.split(".")[0]] = json.loads(path.read_text(encoding="utf-8"))
    build = json.loads((data / "build.json").read_text(encoding="utf-8")) \
        if (data / "build.json").exists() else {}
    partial = {p["iso3"] for p in build.get("partial_levels") or []
               if p.get("level") == "admin2"}
    return admin0, tables["admin1"], tables["admin2"], partial


def disagreements(data: Path = SITE_DATA, *, every: bool = False) -> list[dict[str, Any]]:
    """Every parent whose complete divisions differ from it by more than GAP.

    ``every`` keeps the ones a note already explains; by default only the
    unexplained ones are returned.
    """
    admin0, admin1, admin2, partial = load(data)
    found: list[dict[str, Any]] = []

    def judge(iso3: str, level: str, parent: dict[str, Any],
              children: list[dict[str, Any]]) -> None:
        own = published(parent.get("population"))
        summed = complete_sum(children)
        if own is None or summed is None or not disagrees(own, summed["total"]):
            return
        ok = explained(notes_of(parent), own, summed["total"])
        if ok and not every:
            return
        found.append({"iso3": iso3, "level": level, "id": parent.get("id"),
                      "name": parent.get("name"), "own": own, "sum": summed["total"],
                      "ratio": round(summed["total"] / own, 3), "n": summed["n"],
                      "explained": ok})

    for country in admin0:
        iso3 = country.get("id")
        if iso3 in admin1:
            judge(iso3, "admin0", country, admin1[iso3])
    for iso3, parents in sorted(admin1.items()):
        if iso3 in partial:
            continue
        kids: dict[Any, list[dict[str, Any]]] = {}
        for child in admin2.get(iso3, []):
            kids.setdefault(child.get("parent"), []).append(child)
        for parent in parents:
            if parent.get("water"):
                continue
            judge(iso3, "admin1", parent, kids.get(parent.get("id"), []))
    return found


def allowlist(path: Path = ALLOWLIST) -> dict[tuple[str, str], str]:
    """(level, id) -> why the gap stays, for the known gaps this round cannot fix."""
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("gaps", [])
    return {(r["level"], r["id"]): r["reason"] for r in rows}


def unexplained(data: Path = SITE_DATA, allowed: dict[tuple[str, str], str] | None = None
                ) -> list[dict[str, Any]]:
    """The disagreements nothing explains: no note, and not in the allowlist."""
    allowed = allowlist() if allowed is None else allowed
    return [d for d in disagreements(data) if (d["level"], d["id"]) not in allowed]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=SITE_DATA)
    ap.add_argument("--all", action="store_true",
                    help="list the explained disagreements too")
    args = ap.parse_args(argv)
    rows = disagreements(args.data, every=args.all)
    allowed = allowlist()
    bad = 0
    for row in rows:
        mark = ("explained" if row["explained"] else
                "allowed" if (row["level"], row["id"]) in allowed else "UNEXPLAINED")
        bad += mark == "UNEXPLAINED"
        print(f"{mark:11} {row['iso3']} {row['level']} {row['name']}: "
              f"{row['n']} divisions add up to {row['sum']:,.0f} against "
              f"{row['own']:,.0f} (x{row['ratio']})")
    print(f"{bad} unexplained disagreements over {GAP:.0%}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
