#!/usr/bin/env python3
"""Paraguay's 2022 census by department and district, tabulated on INE's REDATAM base.

Draft: probes only, while the base's layout is read.

Usage:
    python -m scripts.fetch_census.paraguay_census --probe districts
"""

from __future__ import annotations

import argparse

from scripts.probe_redatam import Session, report

from ._shared import log
from .redatam import Server, tables

CMDSET = "https://prod.redatam.org/binpry/RpWebStats.exe/CmdSet"
PORTAL = "https://prod.redatam.org/binpry/RpWebEngine.exe/Portal?BASE={base}&lang=esp"
BASE = "CPV2022"
BASE_2002 = "CPV2002"

SPOKEN = ("P1601", "P1602", "P1604", "P1605", "P1606", "P1607", "P1608", "P1609", "P1698")

PROBES = {
    # One small table a district: the district list, codes and names.
    "districts": (BASE, """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.P03
    AREABREAK DISTRITO
"""),
    # Who the language question was put to: anyone with an answer to any of
    # its items, against the age groups and the two operations.
    "language": (BASE, """RUNDEF Job
    SELECTION ALL

DEFINE PERSONA.HABLA
    AS SWITCH
    INCASE PERSONA.P1601 = 99
        ASSIGN 9
    INCASE PERSONA.P1601 = 1 OR PERSONA.P1602 = 2 OR PERSONA.P1604 = 4 OR PERSONA.P1605 = 5 OR PERSONA.P1606 = 6 OR PERSONA.P1607 = 7 OR PERSONA.P1608 = 8 OR PERSONA.P1609 = 9 OR PERSONA.P1698 = 98
        ASSIGN 1
    DEFAULT 0
    TYPE INTEGER
    RANGE 0-9

TABLE T1
    AS CROSSTABS
    OF PERSONA.GEDAD80 BY PERSONA.HABLA

TABLE T2
    AS CROSSTABS
    OF PERSONA.PERINDI BY PERSONA.HABLA

TABLE T3
    AS FREQUENCY
    OF PERSONA.P1605

TABLE T4
    AS FREQUENCY
    OF PERSONA.P1606

TABLE T5
    AS FREQUENCY
    OF PERSONA.P1607

TABLE T6
    AS FREQUENCY
    OF PERSONA.P1609
"""),
    # The 2002 base: religion (P17), which the 2022 census did not ask, its
    # universe, and the district list.
    "religion02": (BASE_2002, """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.P17

TABLE T2
    AS CROSSTABS
    OF PERSONA.EDADQUINQ BY PERSONA.P17

TABLE T3
    AS FREQUENCY
    OF PERSONA.P03
    AREABREAK DISTRITO
"""),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=sorted(PROBES))
    ap.add_argument("--limit", type=int, default=20000)
    args = ap.parse_args()
    if args.probe:
        base, program = PROBES[args.probe]
        session = Session()
        session.get(PORTAL.format(base=base))
        server = Server(CMDSET, base, session=session, who="paraguay_census")
        for page in server.output(program):
            report(CMDSET, page, args.limit)
            for t in tables(page):
                print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                      f"total={t['total']} na={t['na']} rows={t['rows'][:30]}")
        return 0
    log("paraguay_census: nothing but probes yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
