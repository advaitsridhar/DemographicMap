#!/usr/bin/env python3
"""Venezuela's 2011 census by municipio, tabulated on INE's REDATAM base CPV2011.

Draft: probes only, while the base's layout is read.

Usage:
    python -m scripts.fetch_census.venezuela_redatam --probe munic
"""

from __future__ import annotations

import argparse

from scripts.probe_redatam import Session, report

from ._shared import log
from .redatam import Server, tables

PORTAL = ("http://redatam.ine.gob.ve/vencgibin/RpWebEngine.exe/PortalAction?&MODE=MAIN"
          "&BASE=CPV2011&MAIN=WebServerMain.inl")
CMDSET = "http://redatam.ine.gob.ve/vencgibin/RpWebEngine.exe/CmdSet"
BASE = "CPV2011"

PROBES = {
    "munic": """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.SEXO
    AREABREAK MUNICIPI
""",
    "indigena": """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.INDIGENA

TABLE T2
    AS CROSSTABS
    OF PERSONA.INDIGENA BY VIVIENDA.VIVFAMOCOL

TABLE T3
    AS CROSSTABS
    OF PERSONA.USTEDSEREC BY VIVIENDA.VIVFAMOCOL

TABLE T4
    AS FREQUENCY
    OF PERSONA.EDAD

TABLE T5
    AS FREQUENCY
    OF PERSONA.SEXO
    AREABREAK ENTIDAD
""",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=sorted(PROBES))
    ap.add_argument("--limit", type=int, default=20000)
    args = ap.parse_args()
    if args.probe:
        session = Session()
        session.get(PORTAL)
        server = Server(CMDSET, BASE, session=session, who="venezuela_redatam")
        for page in server.output(PROBES[args.probe]):
            report(CMDSET, page, args.limit)
            for t in tables(page):
                print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                      f"total={t['total']} na={t['na']} rows={t['rows'][:30]}")
        return 0
    log("venezuela_redatam: nothing but probes yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
