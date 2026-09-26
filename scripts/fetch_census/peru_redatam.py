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
import html
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
    OF POBLACIO.C5P26
    AREABREAK DEPARTAM
""",
    # Every question's categories, nationally: the labels to translate.
    "labels": """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF POBLACIO.C5P2

TABLE T2
    AS FREQUENCY
    OF POBLACIO.C5P25

TABLE T3
    AS FREQUENCY
    OF POBLACIO.C5P25MC

TABLE T4
    AS FREQUENCY
    OF POBLACIO.C5P11

TABLE T5
    AS FREQUENCY
    OF POBLACIO.C5P26
""",
    # Single years of age for one small department's provinces: the shape of
    # a table whose category labels are numbers.
    "age-prov": """RUNDEF Job
    SELECTION ALL

TABLE TABLE1
    AS FREQUENCY
    OF POBLACIO.C5P41
    AREABREAK PROVINCI
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


AREA = re.compile(r"^AREA\s*#\s*(\d+)$")


def cells_of(page: str) -> list[list[str]]:
    """Every table row's cells as text, blanks included, in page order."""
    rows = []
    for tr in re.findall(r"(?is)<tr\b.*?</tr>", page):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", td))).strip()
                 for td in re.findall(r"(?is)<td\b.*?</td>", tr)]
        rows.append(cells)
    return rows


def count(text: str) -> int | None:
    """A Redatam count, written with spaces between thousands."""
    digits = text.replace("\xa0", "").replace(" ", "")
    return int(digits) if digits.isdigit() else None


def tables(page: str) -> list[dict]:
    """The frequency tables in an output page: [{area, name, title, rows, total, na}].

    A table opens with an "AREA # code" row naming its area (absent when the
    program has no area break), then a header row naming the variable, then
    one row a category -- label, count, per cent, cumulative per cent -- then
    Total, and a "No Aplica" row counting those the question was not put to.
    """
    out: list[dict] = []
    current: dict | None = None
    for cells in cells_of(page):
        text = [c for c in cells if c]
        if not text:
            continue
        area = next((AREA.match(c) for c in text if AREA.match(c)), None)
        if area:
            current = {"area": area.group(1), "name": text[-1] if len(text) > 1 else "",
                       "title": None, "rows": [], "total": None, "na": None}
            out.append(current)
            continue
        if len(text) >= 3 and text[1] == "Casos":
            if current is None or current["title"] is not None:
                current = {"area": None, "name": "", "title": None, "rows": [],
                           "total": None, "na": None}
                out.append(current)
            current["title"] = text[0]
            continue
        if current is None or current["title"] is None:
            continue
        if text[0].startswith("No Aplica"):
            current["na"] = count(text[0].split(":")[-1]) if ":" in text[0] else (
                count(text[1]) if len(text) > 1 else None)
            continue
        if len(text) >= 2 and count(text[1]) is not None:
            if text[0] == "Total":
                current["total"] = count(text[1])
            else:
                current["rows"].append((text[0], count(text[1])))
    return out


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
    ap.add_argument("--raw", type=int, default=0,
                    help="also print this many characters of each followed page's HTML")
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
            if any(k in url for k in ("Tempo", ".xls", ".htm", "Text?")) \
                    and not url.lower().endswith((".xlsx", ".pdf")) and "reporte." not in url:
                print(f"follow: {label!r} -> {url}")
                body = session.get(url)
                report(url, body, args.limit)
                if args.raw:
                    print(body[:args.raw])
                for table in tables(body)[:40]:
                    print(f"  table {table['area']} {table['name']!r} of {table['title']!r}: "
                          f"total {table['total']}, not applicable {table['na']}")
                    for label_, n in table["rows"][:60]:
                        print(f"    {label_!r}: {n}")
        return 0
    raise SystemExit("peru_redatam: only --probe is written so far")


if __name__ == "__main__":
    raise SystemExit(main())
