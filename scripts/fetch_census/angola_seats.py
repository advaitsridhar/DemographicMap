#!/usr/bin/env python3
"""Angola -- each municipality's seat, from the 2016 law on the country's division.

Lei n.º 18/16, de 17 de Outubro (Lei da Divisão Político-Administrativa)
divided Angola into 18 provinces and 164 municipalities, the units the map
draws (157 polygons; some of Luanda's municipalities are drawn as one). Each
municipality's article opens "O Município de X, com sede em Y, tem como
limites...". This reads every such sentence, each under the chapter of its
province, and writes Y as the seat of the polygon drawn for X.

A polygon whose name leaves no doubt which municipality it is gets that
municipality's seat; the rest are listed in the log and left as they are.
The law is read from lex.ao, which publishes Angola's legislation.

Usage:
    python -m scripts.fetch_census.angola_seats [--run LABEL]
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .binding import fold

URL = "https://lex.ao/docs/assembleia-nacional/2016/lei-n-o-18-16-de-17-de-outubro/"
OUT = "angola_seats.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Lei n.º 18/16, de 17 de Outubro, Lei da Divisão Político-Administrativa "
          "(Assembleia Nacional de Angola)")
LICENCE = "Legislation of the Republic of Angola, as lex.ao publishes it"

# The law's municipality names (folded) the map writes otherwise, or draws under
# the seat's name (Alto Cauale as Cangola, Moxico as Luena, Dange-Quitexe as Quitexe).
ALIASES = {"mbanzakongo": "mbanzacongo", "quicama": "quissama", "kiwabanzoji": "kiuabanzoji",
           "mocamedes": "namibe", "ucuma": "ukuma", "dembos": "dembosquibaxe",
           "cachiungo": "catchiungo", "kundadyabaze": "cundadiabaze", "londuimbali": "londuimbale",
           "moxico": "luena", "ombandja": "ombadja", "quiculungo": "quiculongo",
           "dangequitexe": "quitexe", "pombo": "sanzapombo", "altocauale": "cangola",
           "chicalacholoanga": "tchikalatcholohanga", "chinjenje": "tchinjenje"}
# Polygons drawn over more than one of the law's municipalities, whose seat would
# be one municipality's of several: Luanda's is drawn with the city's others.
SEVERAL = frozenset({"luanda"})
CHAPTER = re.compile(r"CAP[ÍI]TULO\s+[IVXLC]+\s+PROV[ÍI]NCIA\s+D[AEO]S?\s+(.+)", re.I)
SEAT = re.compile(r"O\s+Munic[íi]pio\s+d[eoa]s?\s+(?P<name>[^,]{2,60}?),?\s*com\s+[Ss]ede\s+"
                  r"(?:em|na|no|nas|nos)\s+(?:(?:[Cc]idade|[Vv]ila|[Ll]ocalidade|[Pp]ovoa[çc][ãa]o|"
                  r"[Aa]ldeia|[Ss]ede)\s+(?:d[eoa]s?\s+)?)?(?P<seat>[^,;:]{2,60}?)"
                  r"(?:\s*[,;:]|\s+tem\s)")


def text_of(page: str) -> list[str]:
    """The page's text, a line per heading, paragraph or list item."""
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)</?(h[1-6]|p|li|div|br|ul|ol|tr)\b[^>]*>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    lines = [" ".join(html.unescape(line).replace("​", " ").split())
             for line in page.splitlines()]
    return [line for line in lines if line]


def seats(lines: list[str]) -> dict[str, dict[str, str]]:
    """Province (folded) -> {municipality (folded): seat}."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    province = None
    for line in lines:
        m = CHAPTER.match(line)
        if m:
            province = fold(m.group(1))
            continue
        if province is None:
            continue
        for s in SEAT.finditer(line):
            name = fold(s.group("name"))
            out[province].setdefault(ALIASES.get(name, name), s.group("seat").strip())
    return out


def polygon_keys(name: str) -> set[str]:
    """A polygon's name, and its parts: 'Amboim (Gabela)', 'Dembos-Quibaxe'."""
    keys = {fold(name)}
    inner = re.findall(r"\((.*?)\)", name)
    outer = re.sub(r"\(.*?\)", " ", name)
    keys |= {fold(outer)} | {fold(i) for i in inner}
    return {k for k in keys if k}


def build(found: dict[str, dict[str, str]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    provinces = {u["id"]: fold(u["name"]) for u in admin1}
    cite = [{"field": "capital", "name": SOURCE, "url": URL, "year": 2016, "license": LICENCE}]
    everywhere: dict[str, list[str]] = defaultdict(list)
    for laws in found.values():
        for k, v in laws.items():
            everywhere[k].append(v)
    for u in sorted(admin2, key=lambda u: u["name"]):
        keys = polygon_keys(u["name"])
        if keys & SEVERAL:
            report.append(f"    {u['name']}: drawn over several municipalities; left out")
            continue
        laws = found.get(provinces.get(u["parent"], ""), {})
        hits = {k: v for k, v in laws.items() if k in keys}
        if not hits:
            # Filed under another province than the law's (Pango Aluquém, Bengo's
            # since 1984, is filed under Cuanza Norte): a name the law gives once.
            hits = {k: v[0] for k, v in everywhere.items() if k in keys and len(v) == 1}
        if len(set(hits.values())) != 1:
            report.append(f"    {u['name']}: {'no' if not hits else 'several'} municipality "
                          f"of the law ({sorted(hits)})")
            continue
        seat = next(iter(hits.values()))
        records.append(record(f"AGO-LEI1816-{u['id']}", u["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=u["id"],
                              capital=seat, sources=cite))
    report.insert(0, f"  {len(records)} of {len(admin2)} municipality polygons given a seat")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    page = http_get(URL, binary=True, cache=False, timeout=180).decode("utf-8", "replace")
    lines = text_of(page)
    found = seats(lines)
    log(f"angola_seats: {len(page):,} characters; {len(found)} provinces, "
        f"{sum(len(v) for v in found.values())} municipalities with a seat")
    for province, items in sorted(found.items()):
        log(f"  {province}: " + "; ".join(f"{k} -> {v}" for k, v in sorted(items.items())))
    admin1 = json.loads((SITE / "admin1" / "AGO.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "AGO.units.json").read_text())
    records, report = build(found, admin1, admin2)
    for line in report:
        log(line)
    if len(found) < 18:
        raise SystemExit(f"angola_seats: only {len(found)} provinces read")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
