"""How much of the map can the group tree actually colour?

A unit is drawn in its leading group's colour, and that colour comes from the
group's family. So a group the tree does not place leaves its unit in the
reserved "not yet classified" colour -- honest, but not an answer. This counts
those units, and the labels responsible, because the number is the only thing
that says whether the classification is keeping up with the data.

Two figures matter and they are different:

* how many *units* are led by an unplaced group -- what a reader sees;
* how many distinct *labels* are unplaced -- what there is to fix.

A hundred districts led by one unplaced label is one afternoon's work; a
hundred labels leading one district each is a long tail that may never be
worth finishing. Printing both keeps the two from being confused.

    python -m scripts.check_classified [--list N]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import canonical_groups as cg  # noqa: E402
import group_tree  # noqa: E402

FIELDS = ("religion", "language", "ethnicity")


def records():
    """Every unit the site ships, with the level it sits at."""
    data = ROOT / "site" / "data"
    files = [("admin0", data / "admin0.json")]
    for level in ("admin1", "admin2"):
        folder = data / level
        if folder.is_dir():
            files += [(level, path) for path in sorted(folder.iterdir())]
    for level, path in files:
        try:
            rows = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield level, row


def leader(record, field):
    """The group the map would colour this unit for, or None."""
    rows = record.get(field)
    if not isinstance(rows, list) or not rows:
        return None
    counts = cg.canonicalise(rows, field)
    if not counts:
        return None
    # Residuals lead only where nothing else does, which is what the map does.
    real = {k: v for k, v in counts.items() if not cg.is_residual(k)}
    return max((real or counts).items(), key=lambda kv: kv[1])[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", type=int, default=10, metavar="N",
                    help="show the N labels leading the most units (default 10)")
    args = ap.parse_args(argv)

    seen = collections.defaultdict(lambda: [0, 0])
    blame = collections.defaultdict(collections.Counter)
    for level, record in records():
        for field in FIELDS:
            name = leader(record, field)
            if name is None:
                continue
            tally = seen[(level, field)]
            tally[0] += 1
            if not group_tree.hue(field, name):
                tally[1] += 1
                blame[field][name] += 1

    print(f"{'level':8} {'field':10} {'units':>7} {'unplaced':>9} {'share':>7}")
    worst = 0.0
    for (level, field), (total, missed) in sorted(seen.items()):
        share = 100 * missed / total if total else 0.0
        worst = max(worst, share)
        print(f"{level:8} {field:10} {total:>7} {missed:>9} {share:>6.1f}%")

    for field in FIELDS:
        if not blame[field]:
            continue
        print(f"\n{field}: labels leading a unit with no family")
        for name, count in blame[field].most_common(args.list):
            print(f"   {count:>5}  {name}")
        print(f"   ({len(blame[field])} distinct labels in all)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
