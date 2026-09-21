#!/usr/bin/env python3
"""OCHA's Common Operational Dataset -- Population Statistics, by district.

30,170 of this map's 49,349 second-level shapes have no published population,
and that is what stops a parent's composition from being subtracted down to
its one unread district: a share cannot be turned into a count without a
weight. Bolivia has a population for 9 of 9 departments and 0 of 110
provinces, Iraq 12 of 18 governorates and 0 of 101 districts.

Wikidata was the only global attempt and its ceiling is low: of 18,656 admin2
items it carries P1082 for 6,441, and about 4,900 of those reach a shape.

COD-PS is the other candidate. OCHA publishes one dataset per country, agreed
with the national statistical office, giving population by P-code at every
level the country has. It is the reference population table for humanitarian
work, which is both why it is good (an office's own figures, a stated
reference year) and why it must be read carefully (some of it is projected
forward from an old census, and the licences are not uniform -- cod-ps-idn is
"humanitarian use only" and not an open licence at all).

This runs as a probe first, deliberately. Nothing is written until the log has
said, per country, what the licence is, what the resources are called and
which administrative levels they carry. That is the lesson of cod-ps-idn: the
family name does not tell you the licence, and a dataset that looks like the
others can be the one that may not be used.

Usage:
    python -m scripts.fetch_census.cod_ps --probe        # measure, write nothing
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from typing import Any

from ._shared import log

API = "https://data.humdata.org/api/3/action"
TIMEOUT = 120
HEADERS = {"Accept": "application/json",
           "User-Agent": "DemographicMap/1.0 "
                         "(+https://github.com/advaitsridhar/DemographicMap)"}


def get(path: str, **params: object) -> Any:
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(
            urllib.request.Request(url, headers=HEADERS), timeout=TIMEOUT) as fh:
        return json.load(fh)["result"]


def catalogue() -> list[dict[str, Any]]:
    """Every cod-ps dataset, paged. CKAN caps rows per request."""
    out: list[dict[str, Any]] = []
    start = 0
    while True:
        page = get("package_search", q="name:cod-ps-*", rows=100, start=start)
        got = page.get("results") or []
        out.extend(got)
        start += len(got)
        if not got or start >= int(page.get("count") or 0):
            break
    return out


def licence(package: dict[str, Any]) -> str:
    """The licence as the catalogue states it, never as the family implies."""
    title = str(package.get("license_title") or "").strip()
    other = str(package.get("license_other") or "").strip()
    return (f"{title or 'unstated'} -- license_id={package.get('license_id')!r}, "
            f"isopen={package.get('isopen')}"
            + (f", license_other={other!r}" if other else ""))


def iso3(package: dict[str, Any]) -> str:
    for group in package.get("groups") or ():
        code = str(group.get("name") or "").upper()
        if len(code) == 3:
            return code
    name = str(package.get("name") or "")
    tail = name.rsplit("-", 1)[-1].upper()
    return tail if len(tail) == 3 else ""


def probe() -> None:
    packages = catalogue()
    log(f"cod_ps: {len(packages)} cod-ps dataset(s) on HDX")
    open_count = 0
    for package in sorted(packages, key=lambda p: str(p.get("name"))):
        terms = licence(package)
        if package.get("isopen"):
            open_count += 1
        log(f"  {str(package.get('name')):22} {iso3(package) or '?':4} {terms}")
        for resource in package.get("resources") or ():
            log(f"      {str(resource.get('name'))[:78]:80} "
                f"{str(resource.get('format'))}")
    log(f"  {open_count} of {len(packages)} carry an open licence")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="describe every dataset and write nothing")
    args = ap.parse_args()
    if not args.probe:
        raise SystemExit("cod_ps: only --probe is implemented; "
                         "nothing is written until the probe has been read")
    probe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
