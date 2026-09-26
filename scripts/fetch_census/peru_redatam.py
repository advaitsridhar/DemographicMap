#!/usr/bin/env python3
"""Peru's 2017 census by province, tabulated on INEI's REDATAM WebServer.

INEI publishes the 2017 census (Censos Nacionales 2017: XII de Población, VII
de Vivienda y III de Comunidades Indígenas) for on-line tabulation as the
public base CPV2017DI, and its "Procesador Estadístico En-línea" runs a
Redatam+SP program sent to it. This sends one program a question, each a
frequency table broken by province, and reads the tables back.

``--probe NAME`` sends one of the programs in PROBES and prints what comes
back -- the page's text, frames, links and forms -- so the output's shape is
read before a parser is written against it.

Usage:
    python -m scripts.fetch_census.peru_redatam --probe religion-dept
"""

from __future__ import annotations

import argparse
import re
import urllib.error
import urllib.parse

from scripts.probe_redatam import Session, attrs, report

PORTAL = "https://censos2017.inei.gob.pe/bininei/RpWebEngine.exe/Portal?BASE=CPV2017DI&lang=esp"
CMDSET = "https://censos2017.inei.gob.pe/bininei/RpWebStats.exe/CmdSet"
FORM = {"MAIN": "WebServerMain.inl", "BASE": "CPV2017DI", "LANG": "esp",
        "CODIGO": "XXUSUARIOXX", "ITEM": "PROGRED", "MODE": "RUN", "Submit": "Ejecutar"}

PROBES = {
    # Religion (question 26, asked of those aged 12 and over), by department:
    # 25 small tables, enough to see how the output is laid out.
    "religion-dept": """RUNDEF Job
    SELECTION ALL

TABLE TABLE1
    AS FREQUENCY
    FOR POBLACIO.C5P26
    AREABREAK DEPARTAM
""",
    # The same as a crosstab against the province code, the other way the
    # program could be written.
    "sex-prov-cross": """RUNDEF Job
    SELECTION ALL

DEFINE POBLACIO.PROV
    AS PROVINCI.CCPP
    TYPE STRING

TABLE TABLE1
    AS CROSSTABS
    OF POBLACIO.PROV BY POBLACIO.C5P2
""",
}


def run(session: Session, program: str) -> str:
    """The page the processor answers a program with, error pages included.

    The processor's own page is opened first, as a browser does before
    submitting its form, and the program's lines end in CRLF, as a browser
    sends a textarea's.
    """
    session.get(f"{CMDSET}?BASE=CPV2017DI&ITEM=PROGRED&lang=esp")
    program = program.replace("\r\n", "\n").replace("\n", "\r\n")
    data = urllib.parse.urlencode({**FORM, "CMDSET": program}).encode()
    try:
        return session.get(CMDSET, data=data)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code} for the program; the server's page follows")
        return body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=sorted(PROBES))
    ap.add_argument("--limit", type=int, default=6000)
    args = ap.parse_args()
    session = Session()
    session.get(PORTAL)
    if args.probe:
        page = run(session, PROBES[args.probe])
        print(f"program {args.probe}: {len(page):,} characters back")
        links = report(CMDSET, page, args.limit)
        links += [("frame", urllib.parse.urljoin(CMDSET, attrs(t)["src"]))
                  for t in re.findall(r"(?is)<i?frame\b[^>]*>", page) if attrs(t).get("src")]
        for label, url in links:
            if any(k in url for k in ("Tempo", ".xls", ".htm", "Text?")):
                print(f"follow: {label!r} -> {url}")
                report(url, session.get(url), args.limit)
        return 0
    raise SystemExit("peru_redatam: only --probe is written so far")


if __name__ == "__main__":
    raise SystemExit(main())
