#!/usr/bin/env python3
"""Does site/data still reflect the adapter output sitting beside it?

An adapter run and a site build are separate acts. ``run-adapter.yml`` writes
to ``data/processed`` and deliberately does not rebuild ``site/data`` -- that
join needs the CGAZ boundary files, ~550 MB and not in git, so fetching them on
every adapter run would be the wrong trade. Only the full pipeline joins the
two.

Which means a merged adapter and a country visible on the map are different
states, and until this script nothing connected them. South Africa's nine
provinces sat correct in ``data/processed`` and absent from the map for a week
after the adapter merged, through two further pull requests, and what finally
surfaced it was a person asking "I don't see anything for South Africa?".

So the build now records what each adapter file held when it ran, and this
compares that against the files on disk. It exits 0 by default: a pull request
that adds an adapter *cannot* rebuild the site, so failing it would block the
very change it is reporting on. The point is to say so where somebody will
read it, not to stop the merge.

Usage:
    python3 scripts/check_site_fresh.py            # report, always exit 0
    python3 scripts/check_site_fresh.py --strict   # exit 1 if stale
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_entities import ADAPTER_FILES  # noqa: E402
from common import PROCESSED, ROOT, read_json  # noqa: E402

SITE_DATA = ROOT / "site" / "data"

REFRESH = ("Run the 'Refresh demographic data' workflow (with_census off, "
           "rebuild_tiles off) to join it in.")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def compare(stamped: dict[str, str] | None, processed: Path,
            files: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Adapter files that are new, changed, or gone since the last build.

    ``stamped`` is None for a build.json written before this check existed.
    That is not the same as "nothing has changed" and must not be reported as
    though it were -- an old stamp tells you nothing, and saying "up to date"
    on no evidence is the failure this whole script exists to prevent.
    """
    if stamped is None:
        return ([], [], [])
    added, changed, removed = [], [], []
    for filename in files:
        path = processed / filename
        if not path.exists():
            if filename in stamped:
                removed.append(filename)
            continue
        if filename not in stamped:
            added.append(filename)
        elif stamped[filename] != digest(path):
            changed.append(filename)
    return (added, changed, removed)


def announce(kind: str, message: str) -> None:
    """A line in the log, and an annotation when a workflow is watching."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{kind}::{message}")
    else:
        print(f"{kind}: {message}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when site/data is behind data/processed")
    args = ap.parse_args()

    build = read_json(SITE_DATA / "build.json", None)
    if not build:
        announce("warning", "site/data/build.json is missing -- the site has "
                            "never been built from this checkout.")
        return 1 if args.strict else 0

    stamped = build.get("adapters")
    if stamped is None:
        announce("warning",
                 "site/data was built before this check existed, so what went "
                 "into it is unknown. " + REFRESH)
        return 1 if args.strict else 0

    added, changed, removed = compare(stamped, PROCESSED, list(ADAPTER_FILES))
    if not (added or changed or removed):
        print(f"site/data is current with all {len(stamped)} adapter files.")
        return 0

    for filename in added:
        announce("warning", f"{filename} has never reached the map: it is in "
                            f"data/processed and not in this site build. "
                            f"{REFRESH}")
    for filename in changed:
        announce("warning", f"{filename} has changed since the site was "
                            f"built, so the map still shows the older "
                            f"figures. {REFRESH}")
    for filename in removed:
        announce("warning", f"{filename} went into the last site build and is "
                            f"no longer in data/processed. {REFRESH}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
