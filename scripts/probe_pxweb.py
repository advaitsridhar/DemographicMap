#!/usr/bin/env python3
"""Find census ethnicity/religion/language tables across national PxWeb APIs.

PxWeb is the statistics-database software most of Europe's national offices
run, and they expose the same REST shape: a navigable tree of folders ending in
tables, each describing its own variables. That makes one adapter serve many
countries the way the Eurostat one does, instead of a scraper per office -- but
only if the tables actually exist, are public, and break the figures down by a
geography the boundary files can join.

None of that is guessable from the outside, so this walks each instance and
reports what is really there: the tables whose titles mention the fields this
project cares about, the variables each one offers, and how many regions its
geography variable holds. Read-only; the output is the log.

Usage:
    python scripts/probe_pxweb.py --countries EST,LVA,LTU
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Base URLs are the language-scoped database roots. Where an office offers
# English it is used, because the table titles are what the keyword match reads.
INSTANCES: dict[str, dict[str, str]] = {
    # Finland records mother tongue in the population register for every
    # resident, by municipality. That is one of the four fields this project
    # maps, and a register count rather than a sample -- the first pass wrote
    # it off as "asks language rather than ethnicity", as though language were
    # a consolation prize.
    "FIN": {"name": "Statistics Finland",
            "base": "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin",
            # StatFin answers 429 under the default pace, and a walk that is
            # being throttled finds nothing and reports it as "nothing there".
            "throttle": 1.2, "budget": 220},
    "SWE": {"name": "Statistics Sweden",
            "base": "https://api.scb.se/OV0104/v1/doris/en/ssd"},
    # Norway, Iceland and Denmark do not ask religion, but they register
    # membership of religious and life-stance communities, which is a count of
    # the same thing by a different route. Iceland's is broken down by
    # organisation.
    "NOR": {"name": "Statistics Norway",
            "base": "https://data.ssb.no/api/v0/en/table"},
    "EST": {"name": "Statistics Estonia",
            "base": "https://andmed.stat.ee/api/v1/en/stat"},
    "LVA": {"name": "Statistics Latvia",
            "base": "https://data.stat.gov.lv/api/v1/en/OSP_PUB"},
    "LTU": {"name": "Statistics Lithuania",
            "base": "https://osp-rs.stat.gov.lt/rest_xml/data"},
    # NOT PxWeb: StatBank has its own REST shape (/v1/subjects, /v1/tables),
    # so the tree walk below cannot read it. Left listed and skipped by name
    # rather than deleted, because "we looked and it needs a different client"
    # is worth more to the next person than an absence.
    "DNK": {"name": "Statistics Denmark (StatBank, not PxWeb)",
            "base": "https://api.statbank.dk/v1", "skip": "not a PxWeb tree"},
    "ISL": {"name": "Statistics Iceland",
            "base": "https://px.hagstofa.is/pxen/api/v1/en/Ibuar"},
    # The offices this adapter is actually for. The Nordic instances above run
    # PxWeb well and ask none of the questions Eurostat leaves out; these ask
    # ethnicity and religion in the same census, which is the gap in the map.
    # Their base URLs are unverified from here -- the sandbox cannot reach a
    # statistical host -- so an unreachable one is a result too, and cheaper to
    # learn from a probe than from a guessed adapter.
    "SVN": {"name": "Statistical Office of Slovenia",
            "base": "https://pxweb.stat.si/SiStatData/api/v1/en/Data"},
    "SVK": {"name": "Statistical Office of Slovakia",
            "base": "https://datacube.statistics.sk/api/v1/en/DATAcube"},
    "MKD": {"name": "State Statistical Office of North Macedonia",
            "base": "https://makstat.stat.gov.mk/PXWeb/api/v1/en/MakStat"},
    "SRB": {"name": "Statistical Office of Serbia",
            "base": "https://data.stat.gov.rs/api/v1/en"},
    "HRV": {"name": "Croatian Bureau of Statistics",
            "base": "https://podaci.dzs.hr/api/v1/en"},
    "GRL": {"name": "Statistics Greenland",
            "base": "https://bank.stat.gl/api/v1/en/Greenland"},
    "FRO": {"name": "Statistics Faroe Islands",
            "base": "https://statbank.hagstova.fo/api/v1/en/H2"},
}

# What this project can put on a map. "Nationality" is included because several
# offices use it for what their census calls ethnicity.
WANTED = ("religio", "ethnic", "nationalit", "language", "mother tongue",
          "citizenship", "confession", "denomination",
          # What the Nordic registers call it. Norway files these under "life
          # stance communities" and Iceland under "life stance organisations";
          # neither string contains any of the words above except "religio",
          # and the folder holding them often does not contain that either.
          "life stance", "livssyn", "faith", "church", "creed",
          "trossamfunn", "tros")

# Geography variable names, in the languages these instances answer in.
# "Territorial unit" is Latvia's, and leaving it out made the probe report
# IRE031 -- population by ethnicity across 57 municipalities -- as national
# only, which is the one thing a geography probe must not get wrong.
GEO_HINTS = ("region", "municipal", "county", "area", "district", "province",
             "kommun", "maakond", "vald", "landsdel", "territorial", "unit",
             "obcina", "občina", "opstina", "okrug", "voivod", "powiat")

THROTTLE = 0.25
MAX_NODES = 250
# Seconds any one instance may consume. A node budget alone does not bound the
# work: a host that accepts a connection and then stalls costs the full request
# timeout each time, so 250 nodes at 30 seconds is over two hours and the first
# run of this probe had to be cancelled. Wall clock is what actually bounds it.
BUDGET_SECONDS = 70
# ...and what describing the finds may cost on top of it. Bounded separately
# because it is a different failure: a host that dribbles bytes holds a
# connection far longer than REQUEST_TIMEOUT, which urllib applies per read
# rather than to the whole response.
DESCRIBE_SECONDS = 60
REQUEST_TIMEOUT = 12


def get(url: str, timeout: int = REQUEST_TIMEOUT, tries: int = 3):
    """One GET, backing off when the office says it is being asked too fast.

    A 429 is not an absence and must not be reported as one. Statistics
    Finland returns it under any brisk pace, and the first walk of that
    instance came back empty -- which was written down as "Finland asks
    language rather than ethnicity", a conclusion the probe had not earned.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/json",
    })
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as err:
            if err.code not in (429, 503) or attempt == tries - 1:
                raise
            wait = float(err.headers.get("Retry-After") or 0) or 2.0 * (2 ** attempt)
            print(f"      (throttled, waiting {wait:.0f}s)")
            time.sleep(min(wait, 30.0))
    raise RuntimeError("unreachable")


def walk(base: str, budget: list[int], deadline: float,
         depth: int = 0, path: str = "", throttle: float = THROTTLE) -> list[dict]:
    """Depth-first over the PxWeb tree, collecting tables that look relevant."""
    if budget[0] <= 0 or depth > 4 or time.monotonic() > deadline:
        return []
    url = f"{base}/{path}" if path else base
    budget[0] -= 1
    try:
        time.sleep(throttle)
        node = get(url)
    except Exception as err:                      # noqa: BLE001
        if depth == 0:
            print(f"    unreachable: {type(err).__name__}: {str(err)[:90]}")
        return []
    if not isinstance(node, list):
        return []

    found = []
    for entry in node:
        if not isinstance(entry, dict):
            continue
        eid, etype = entry.get("id"), entry.get("type")
        text = (entry.get("text") or "")
        child = f"{path}/{eid}" if path else eid
        if etype == "t":
            if any(w in text.lower() for w in WANTED):
                found.append({"path": child, "title": text})
        elif etype == "l":
            # Only descend where the folder could plausibly hold what we want,
            # or near the root where names are broad ("Population").
            if depth <= 1 or any(w in text.lower() for w in WANTED + ("population", "census")):
                found.extend(walk(base, budget, deadline, depth + 1, child, throttle))
        if budget[0] <= 0 or time.monotonic() > deadline:
            break
    return found


def describe(base: str, table: dict, throttle: float = THROTTLE,
             deadline: float | None = None) -> None:
    """Print a table's variables, and the size of its geography dimension."""
    if deadline is not None and time.monotonic() > deadline:
        print("      (out of time — not described)")
        return
    try:
        time.sleep(throttle)
        meta = get(f"{base}/{table['path']}",
                   tries=1 if deadline is None else 2)
    except Exception as err:                      # noqa: BLE001
        print(f"      ! metadata failed: {str(err)[:70]}")
        return
    variables = meta.get("variables") or []
    parts = []
    geo = None
    for var in variables:
        label = (var.get("text") or var.get("code") or "")
        size = len(var.get("values") or [])
        parts.append(f"{label}({size})")
        if geo is None and any(h in label.lower() for h in GEO_HINTS) and size > 5:
            geo = (label, size, (var.get("valueTexts") or [])[:4])
    print(f"      vars: {', '.join(parts)[:150]}")
    if geo:
        print(f"      geography: {geo[0]} — {geo[1]} areas, e.g. {', '.join(geo[2])}")
    else:
        print("      geography: none with more than five values — national only")


def dump(base: str, path: str) -> int:
    """Every variable of one table, with the codes a query has to name.

    describe() prints labels, which is what a human reads to decide a table is
    the right one. A query is written against codes, and those are different
    strings -- Estonia labels a variable "Ethnic nationality" and codes it
    "Rahvus" -- so configuring an adapter needs this rather than that.
    """
    try:
        meta = get(f"{base}/{path}", timeout=30)
    except Exception as err:                      # noqa: BLE001
        print(f"  ! {type(err).__name__}: {str(err)[:120]}")
        return 1
    print(f"  title: {meta.get('title', '')[:150]}")
    for var in meta.get("variables") or []:
        values = var.get("values") or []
        texts = var.get("valueTexts") or []
        print(f"\n  code={var.get('code')!r}  text={var.get('text')!r}  "
              f"{len(values)} values  elimination={var.get('elimination')}"
              f"  time={var.get('time')}")
        for code, text in list(zip(values, texts))[:24]:
            print(f"      {code!r:<16} {text}")
        if len(values) > 24:
            print(f"      ... {len(values) - 24} more")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--countries", default=",".join(INSTANCES))
    ap.add_argument("--max-tables", type=int, default=3)
    # A walk from the root spends its budget on whatever it meets first. Once
    # the office's tree is known, naming the subtree is the difference between
    # sampling it and reading it: StatFin keeps population by language under
    # "vaerak", four folders in.
    ap.add_argument("--root", default="",
                    help="start the walk at this path instead of the database root")
    ap.add_argument("--dump", metavar="ISO:TABLE_PATH", action="append", default=[],
                    help="print one table's variable codes and values in full")
    args = ap.parse_args()

    for spec in args.dump:
        iso, _, path = spec.partition(":")
        instance = INSTANCES.get(iso.strip().upper())
        if not instance:
            print(f"\n== {iso}: no instance configured")
            continue
        print(f"\n== {iso} {instance['name']} :: {path}")
        dump(instance["base"], path)
    if args.dump:
        return 0

    for iso in [c.strip().upper() for c in args.countries.split(",") if c.strip()]:
        spec = INSTANCES.get(iso)
        if not spec:
            print(f"\n== {iso}: no instance configured")
            continue
        print(f"\n== {iso} {spec['name']}\n   {spec['base']}")
        if spec.get("skip"):
            print(f"    skipped: {spec['skip']}")
            continue
        # An office that answers slowly needs both a slower pace and longer to
        # spend at it; one budget for every instance means the throttled ones
        # report an empty tree, which reads as "nothing there".
        throttle = float(spec.get("throttle", THROTTLE))
        budget = int(spec.get("budget", BUDGET_SECONDS))
        started = time.monotonic()
        # The walk gets most of the budget; what is left pays for describing
        # what it found. A phase with no deadline is not bounded by one: the
        # first Nordic run spent fifty minutes inside describe() after a walk
        # that had correctly stopped at seventy seconds.
        walk_deadline = started + budget
        instance_deadline = started + budget + DESCRIBE_SECONDS
        tables = walk(spec["base"], [MAX_NODES], walk_deadline,
                      path=args.root, throttle=throttle)
        spent = time.monotonic() - started
        exhausted = spent > budget
        if exhausted:
            print(f"    (stopped after {spent:.0f}s — tree not fully walked)")
        if not tables:
            # Distinguish "walked it and there is nothing" from "ran out of
            # time or was throttled", because only the first is a finding.
            print("    no candidate tables"
                  + (" IN THE PART WALKED — not a finding" if exhausted else
                     " matching religion / ethnicity / language"))
            continue
        # Every path found, then the first few described. Listing is free --
        # the walk already has these -- and describing costs a request each.
        # Printing only the described ones hid the finding: Finland returned 44
        # candidates and the six shown were births, marriages and citizenship,
        # because a depth-first walk reaches those folders before the one
        # holding population by language.
        print(f"    {len(tables)} candidate table(s):")
        for table in tables:
            print(f"      {table['path']:<28} {table['title'][:88]}")
        print(f"    describing the first {min(args.max_tables, len(tables))}:")
        for table in tables[:args.max_tables]:
            print(f"    - {table['path']}")
            print(f"      {table['title'][:110]}")
            describe(spec["base"], table, throttle=throttle,
                     deadline=instance_deadline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
