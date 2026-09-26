#!/usr/bin/env python3
"""A client for CELADE's REDATAM WebServer, shared by the census readers that use one.

Several Latin American offices publish a census for on-line tabulation on a
REDATAM WebServer (``RpWebEngine.exe`` / ``RpWebStats.exe``). Its "Procesador
Estadístico En-línea" runs a Redatam+SP program posted to it and answers with
a page whose frames hold the output tables. This is that exchange, and the
parser for the frequency tables it prints, written first for INEI's 2017 base
(``peru_redatam.py``) and kept general:

    server = Server("https://host/bin/RpWebStats.exe/CmdSet", base="CPV2017DI")
    found = server.frequency("POBLACIO.C5P26", areabreak="PROVINCI")

``found`` is one dict a table: ``{area, name, title, rows, total, na}``, where
``rows`` is ``[(label, count), ...]`` in the order printed, ``total`` the
table's Total row, and ``na`` its "No Aplica" count (those the question was
not put to). A table with no ``area`` is the whole base's, printed after the
areas when the program has an area break; readers use it as a check.

A server whose pages differ -- another header word than "Casos", another
language -- is handled by the reader that needs it, by passing ``header`` or
by parsing ``Server.pages`` itself; nothing here is specific to a country.

Usage (a probe; the output is the log):
    python -m scripts.fetch_census.redatam CMDSET_URL BASE "FREQUENCY OF POBLACIO.P02 AREABREAK DEPTO"
"""

from __future__ import annotations

import argparse
import html
import re
import urllib.error
import urllib.parse
from collections import Counter

from scripts.probe_redatam import Session, attrs, report

AREA = re.compile(r"^AREA\s*#\s*(\S+)$")


def cells_of(page: str) -> list[list[str]]:
    """Every table row's cells as text, blanks included, in page order."""
    rows = []
    for tr in re.findall(r"(?is)<tr\b.*?</tr>", page):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", td))).strip()
                 for td in re.findall(r"(?is)<td\b.*?</td>", tr)]
        rows.append(cells)
    return rows


def count(text: str) -> int | None:
    """A Redatam count, written with spaces (or dots or commas) between thousands."""
    digits = re.sub(r"[\s\xa0.,]", "", text)
    return int(digits) if digits.isdigit() else None


def tables(page: str, header: str = "Casos") -> list[dict]:
    """The frequency tables in an output page: [{area, name, title, rows, total, na}].

    A table opens with an "AREA # code" row naming its area (absent when the
    program has no area break), then a header row naming the variable and
    ``header`` ("Casos"), then one row a category -- label, count, per cent,
    cumulative per cent -- then Total, and a "No Aplica" row counting those
    the question was not put to.
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
        if len(text) >= 3 and text[1] == header:
            if current is None or current["title"] is not None:
                current = {"area": None, "name": "", "title": None, "rows": [],
                           "total": None, "na": None}
                out.append(current)
            current["title"] = text[0]
            continue
        if current is None or current["title"] is None:
            continue
        if text[0].startswith("No Aplica"):
            # "No Aplica : 97 779" in one cell, or the label and count in two.
            after = count(text[0].split(":", 1)[1]) if ":" in text[0] else None
            current["na"] = after if after is not None else (
                count(text[1]) if len(text) > 1 else None)
            continue
        if len(text) >= 2 and count(text[1]) is not None:
            if text[0] == "Total":
                current["total"] = count(text[1])
            else:
                current["rows"].append((text[0], count(text[1])))
    return out


def median_age(ages: Counter) -> float | None:
    """The age half the people are younger than, interpolated within its single year."""
    total = sum(ages.values())
    if total <= 0:
        return None
    half, cum = total / 2, 0.0
    for years in sorted(ages):
        n = ages[years]
        if cum + n >= half and n > 0:
            return round(years + (half - cum) / n, 1)
        cum += n
    return None


def frequency_program(variable: str, areabreak: str | None = None,
                      selection: str = "ALL") -> str:
    """A Redatam+SP program with one frequency table, optionally broken by area."""
    lines = ["RUNDEF Job", f"    SELECTION {selection}", "", "TABLE TABLE1",
             "    AS FREQUENCY", f"    OF {variable}"]
    if areabreak:
        lines.append(f"    AREABREAK {areabreak}")
    return "\n".join(lines) + "\n"


class Server:
    """One base on one REDATAM WebServer's statistical processor."""

    def __init__(self, cmdset: str, base: str, lang: str = "esp",
                 form: dict[str, str] | None = None, session: Session | None = None,
                 who: str = "redatam") -> None:
        self.cmdset = cmdset
        self.base = base
        self.lang = lang
        self.who = who
        self.session = session or Session()
        self.form = {"MAIN": "WebServerMain.inl", "BASE": base, "LANG": lang,
                     "CODIGO": "XXUSUARIOXX", "ITEM": "PROGRED", "MODE": "RUN",
                     "Submit": "Ejecutar", **(form or {})}
        self.pages: list[str] = []

    def run(self, program: str) -> str:
        """The page the processor answers a program with, error pages included.

        The processor's own page is opened first, as a browser does before
        submitting its form, and the program's lines end in CRLF, as a browser
        sends a textarea's.
        """
        self.session.get(f"{self.cmdset}?BASE={self.base}&ITEM=PROGRED&lang={self.lang}")
        program = program.replace("\r\n", "\n").replace("\n", "\r\n")
        data = urllib.parse.urlencode({**self.form, "CMDSET": program}).encode()
        try:
            return self.session.get(self.cmdset, data=data)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            print(f"HTTP {exc.code} for the program; the server's page follows")
            return body

    def output(self, program: str) -> list[str]:
        """The output frames' pages for a program; refuses an answer with none."""
        page = self.run(program)
        frames = [urllib.parse.urljoin(self.cmdset, attrs(t)["src"])
                  for t in re.findall(r"(?is)<i?frame\b[^>]*>", page) if attrs(t).get("src")]
        if not frames:
            raise SystemExit(f"{self.who}: the processor answered with no output: "
                             f"{page[:400]!r}")
        self.pages = [self.session.get(frame) for frame in frames]
        return self.pages

    def frequency(self, variable: str, areabreak: str | None = None,
                  header: str = "Casos", selection: str = "ALL") -> list[dict]:
        """One variable's frequency table, for every area of ``areabreak``."""
        pages = self.output(frequency_program(variable, areabreak, selection))
        return [t for page in pages for t in tables(page, header)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmdset", help="the processor's RpWebStats.exe/CmdSet URL")
    ap.add_argument("base", help="the base's name, as its portal's BASE= parameter")
    ap.add_argument("program", nargs="+",
                    help="Redatam+SP after RUNDEF/SELECTION, as words: a new line starts "
                         "at each TABLE/AS/OF/AREABREAK/DEFINE/TYPE/FOR/UNIVERSE keyword")
    ap.add_argument("--lang", default="esp")
    ap.add_argument("--header", default="Casos")
    args = ap.parse_args()
    # The dispatch splits arguments on spaces, so a program arrives as words;
    # a keyword starts a new line, as the processor expects.
    text = re.sub(r"\s+(?=(?:TABLE|AS|OF|AREABREAK|DEFINE|TYPE|FOR|UNIVERSE)\s)",
                  "\n    ", " ".join(args.program))
    program = "RUNDEF Job\n    SELECTION ALL\n\n" + text.replace("\n    TABLE", "\n\nTABLE") + "\n"
    print(program)
    server = Server(args.cmdset, args.base, lang=args.lang)
    for page in server.output(program):
        report(args.cmdset, page, 4000)
        for t in tables(page, args.header):
            print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                  f"total={t['total']} na={t['na']} rows={t['rows'][:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
