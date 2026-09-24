"""Ecuador's cantons: the 2022 census count Spanish Wikipedia's list transcribes.

INEC publishes the 2022 census by canton at censoecuador.gob.ec, and that host
answers an automated reader with 403 however it announces itself; this map
does not get round a refusal. Spanish Wikipedia's "Anexo:Cantones de Ecuador"
transcribes the same census into one table of every canton, its province and
its 2022 population, and is read instead -- as what it is, an encyclopaedia's
transcription, which fills a canton the map has nothing for and never
replaces a count.

Wikidata already carries the 2022 figure for 188 of the map's 223 cantons.
The other 35 are the reason this exists: sixteen joined no item, and nineteen
joined the item for the canton's town, whose figure the build refuses.

Two checks stand between the table and the map:

*Every row must read.* A canton is the cell that begins "Cantón", followed by
its province's ISO 3166-2 letter, the year it was constituted and its
population. A row that does not read that way is reported and skipped rather
than guessed at.

*The cantons must add up to the country.* INEC counted 16,938,986 people in
2022. A table whose rows sum to anything else by more than one percent is
not the table this was written against, and nothing is written.

Usage:
    python -m scripts.fetch_census.ecuador_cantons
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .europe_wiki import fetch, number

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import measure, slugify  # noqa: E402
from probe_wikitable import tables  # noqa: E402

TITLE = "Anexo:Cantones de Ecuador"
LANG = "es"
OUT = PROCESSED / "ecuador_cantons.json"
YEAR = 2022
LICENCE = "CC BY-SA 4.0"
# INEC, Censo de Población y Vivienda 2022, national total.
NATIONAL = 16_938_986
TOLERANCE = 0.01

# ISO 3166-2:EC, the letters the table's province column is written in, to
# the names the map's first level carries.
PROVINCE = {
    "A": "Azuay", "B": "Bolívar", "F": "Cañar", "C": "Carchi", "H": "Chimborazo",
    "X": "Cotopaxi", "O": "El Oro", "E": "Esmeraldas", "W": "Galápagos",
    "G": "Guayas", "I": "Imbabura", "L": "Loja", "R": "Los Ríos", "M": "Manabi",
    "S": "Morona Santiago", "N": "Napo", "D": "Orellana", "Y": "Pastaza",
    "P": "Pichincha", "SE": "Santa Elena", "SD": "Santo Domingo de los Tsáchilas",
    "U": "Sucumbios", "T": "Tungurahua", "Z": "Zamora Chinchipe",
}
CANTON = re.compile(r"^Cant[oó]n\s+(.+)$")


def value(cell: str) -> str:
    """A cell's content, its attributes (``align=right|``) gone."""
    return cell.rsplit("|", 1)[-1].strip()


def population(cell: str) -> int | None:
    text = value(cell)
    m = re.search(r"formatnum:\s*([\d.]+)", text)
    figure = float(m.group(1)) if m else number(text, ",")
    return int(figure) if figure and figure > 0 else None


def parse(rows: list[list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    """(cantons, rows that did not read)."""
    found, skipped = [], []
    for row in rows:
        cells = [value(c) for c in row]
        at = next((i for i, c in enumerate(cells) if CANTON.match(c)), None)
        if at is None:
            continue
        name = CANTON.match(cells[at]).group(1).strip()
        rest = row[at + 1:]
        if len(rest) < 3:
            skipped.append(f"{name}: {len(rest)} cells after the name")
            continue
        code, founded, people = value(rest[0]).upper(), value(rest[1]), population(rest[2])
        if code not in PROVINCE or not re.fullmatch(r"\d{4}", founded) or not people:
            skipped.append(f"{name}: {code!r} {founded!r} {rest[2]!r}")
            continue
        found.append({"name": name, "province": PROVINCE[code], "population": people})
    return found, skipped


def cites_inec(wikitext: str) -> bool:
    return bool(re.search(r"<ref[^>]*>[^<]*(INEC|censoecuador|ecuadorencifras)", wikitext, re.I))


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    wikitext, title = fetch(TITLE, LANG)
    if not wikitext:
        raise SystemExit(f"{TITLE}: no wikitext")
    found = tables(wikitext)
    cantons, skipped = parse(found[0] if found else [])
    for line in skipped:
        log(f"  skipped {line}")
    total = sum(c["population"] for c in cantons)
    log(f"  {len(cantons)} cantons in {len({c['province'] for c in cantons})} provinces, "
        f"{total:,} people against INEC's {NATIONAL:,}")
    if not cantons or abs(total - NATIONAL) > TOLERANCE * NATIONAL:
        raise SystemExit("the cantons do not add up to the country; nothing written")
    url = f"https://{LANG}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
    source = f"Spanish Wikipedia, {title}" + (
        " (transcribing INEC, Censo de Población y Vivienda 2022)" if cites_inec(wikitext)
        else "")
    rows = []
    for canton in cantons:
        name = canton["name"]
        rows.append(record(
            f"ECU-WL-{slugify(canton['province'])}-{slugify(name)}", name,
            level="admin2", parent="ECU", country="ECU",
            parent_name=canton["province"], aliases=[f"Cantón {name}"],
            population=measure(canton["population"], year=YEAR, source=source),
            sources=[{"field": "population", "name": source, "url": url,
                      "license": LICENCE}]))
    write_json(OUT, rows)
    log(f"  wrote {len(rows)} cantons to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
