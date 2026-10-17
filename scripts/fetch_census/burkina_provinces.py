#!/usr/bin/env python3
"""Burkina Faso -- each province's sex ratio from the 2019 census's regional monographs.

INSD published a monograph of each of the 13 regions from the fifth census
(5e RGPH, 2019; December 2022). Each gives the region's population by province
and sex (Tableau 2.3 in most: *Répartition (%) des effectifs de la population
par province selon le sexe*), the count of men and women of every province.
OCHA's projection for 2023 gave the provinces their region's split by sex, so
the map's provinces had no sex ratio of their own: this writes the census's,
for the 45 provinces. Their populations are left to the newer projection, and
their median age to the reason they already give (the monographs tabulate ages
by region only).

The Centre region is the one province of Kadiogo, and its monograph's regional
count by sex (Tableau 2.1) is the province's.

**Checks before anything is written.** Every province's men and women make
its total; each region's provinces make the region's total row; every province
on the map is found once.

Usage:
    python -m scripts.fetch_census.burkina_provinces
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob  # noqa: E402

BASE = "https://www.insd.bf/sites/default/files/"
# The map's regions -> the monographs' addresses (the Cascades' is tried under
# the names its siblings use).
MONOGRAPHS = {
    "Boucle du Mouhoun": ["2023-02/MONOGRAPHIE%20DE%20LA%20BOUCLE%20DU%20MOUHOUN%205E%20RGPH.pdf"],
    "Cascades": ["2023-02/MONOGRAPHIE%20DES%20CASCADES%205E%20RGPH.pdf",
                 "2023-02/MONOGRAPHIE%20DES%20CASCADES%205E%20RGPH_0.pdf",
                 "2023-07/MONOGRAPHIE%20DES%20CASCADES%205E%20RGPH.pdf",
                 "2023-02/MONOGRAPHIE%20DE%20LA%20REGION%20DES%20CASCADES%205E%20RGPH.pdf"],
    "Centre": ["2023-02/MONOGRAPHIE%20DU%20CENTRE%205E%20RGPH.pdf"],
    "Centre-Est": ["2023-02/MONOGRAPHIE%20DU%20CENTRE-EST%205E%20RGPH.pdf"],
    "Centre-Nord": ["2023-02/MONOGRAPHIE%20DU%20CENTRE-NORD%205E%20RGPH_0.pdf"],
    "Centre-Ouest": ["2023-02/MONOGRAPHIE%20DU%20CENTRE%20OUEST%205E%20RGPH.pdf"],
    "Centre-Sud": ["2023-02/MONOGRAPHIE%20DU%20CENTRE-SUD%205E%20RGPH.pdf"],
    "Est": ["2023-02/MONOGRAPHIE%20DE%20L%27EST%205E%20RGPH.pdf"],
    "Hauts-Bassins": ["2023-02/MONOGRAPHIE%20DES%20HAUTS-BASSINS%205E%20RGPH.pdf"],
    "Nord": ["2023-02/MONOGRAPHIE%20DU%20NORD%205E%20RGPH.pdf"],
    "Plateau Central": ["2023-02/MONOGRAPHIE%20DU%20PLATEAU%20CENTRAL%205E%20RGPH.pdf"],
    "Sahel": ["2023-07/MONO%20REGION%20DU%20SAHEL%205E%20RGPH.pdf"],
    "Sud-Ouest": ["2023-02/MONOGRAPHIE%20DU%20SUD%20OUEST%205E%20RGPH.pdf"],
}
PUBLISHER = "Institut National de la Statistique et de la Démographie (INSD) du Burkina Faso"
YEAR = 2019
LICENCE = "INSD publication (reuse with attribution)"
OUT = "burkina_provinces.json"
SITE = PROCESSED.parent.parent / "site" / "data"
# Other spellings the monographs may use for the map's provinces (folded).
SPELLINGS = {"komonjdjari": ["Komondjari", "Komandjari"], "kouritenga": ["Kourittenga"],
             "bale": ["Balé", "Bale"], "tuy": ["Tuy", "Tui"]}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def readings(tokens: list[str], start: int) -> list[tuple[int, int]]:
    if start >= len(tokens) or not tokens[start].isdigit():
        return []
    first = tokens[start]
    if len(first) > 3:
        return [(int(first), start + 1)]
    out, j = [(int(first), start + 1)], start + 1
    while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
        j += 1
        out.append((int("".join(tokens[start:j])), j))
    return out


def triple_at(tokens: list[str], start: int) -> tuple[int, int, int] | None:
    """(men, women, total) beginning at tokens[start], the first two making the third."""
    for a, ea in readings(tokens, start):
        for b, eb in readings(tokens, ea):
            for c, _ in readings(tokens, eb):
                if a + b == c and c >= 1000:
                    return a, b, c
    return None


def close(label: str, name: str) -> bool:
    """A label that is another spelling of the province's name: the same first
    three letters and most of the rest (Komondjari, Komandjoari...)."""
    a, b = fold(label), fold(name)
    return (len(a) >= 4 and a[:3] == b[:3]
            and difflib.SequenceMatcher(None, a, b).ratio() >= 0.75)


def total_row(tokens: list[str]) -> list[tuple[int, int, int]]:
    """Every (men, women, total) that follows an Ensemble or Total label."""
    return [t for i, token in enumerate(tokens) if fold(token) in ("ensemble", "total")
            for t in [triple_at(tokens, i + 1)] if t]


def province_table(text: str, provinces: list[str]) -> dict[str, tuple[int, int, int]]:
    """{province (the map's name): (men, women, total)} from the table of the
    region's population by province and sex. A province named otherwise than on
    the map is taken from a row whose label is close to its name, and only when
    the provinces then make the table's own total row."""
    flat = re.sub(r"\s+", " ", text)
    out: dict[str, tuple[int, int, int]] = {}
    seen = ""
    spellings = {name: [name] + SPELLINGS.get(fold(name), []) for name in provinces}
    for title in re.finditer(r"(?i)par\s+province\s+selon\s+le\s+sexe", flat):
        window = flat[title.end():title.end() + 3000]
        if re.match(r"\s*\.{3,}|\s*_{3,}", window):
            continue                       # the list of tables
        tokens = window.split()
        found: dict[str, tuple[int, int, int]] = {}
        for i in range(len(tokens)):
            for name, forms in spellings.items():
                if name in found:
                    continue
                for form in forms:
                    words = form.split()
                    if fold(" ".join(tokens[i:i + len(words)])) == fold(form):
                        triple = triple_at(tokens, i + len(words))
                        if triple:
                            found[name] = triple
                            break
        for name in provinces:
            if name in found or len(name.split()) > 1:
                continue
            for i in range(len(tokens)):
                taken = set(found.values())
                for width in (1, 2):
                    words = tokens[i:i + width]
                    if any(not w[:1].isalpha() for w in words):
                        continue
                    label = "".join(words)
                    triple = triple_at(tokens, i + width)
                    if triple and triple not in taken and close(label, name):
                        log(f"    {name} is the table's {' '.join(tokens[i:i + width])}")
                        found[name] = triple
                        break
                if name in found:
                    break
        if len(found) == len(provinces):
            sums = tuple(sum(v[k] for v in found.values()) for k in range(3))
            totals = total_row(tokens)
            if sums in totals:
                return found
            seen = (f"; its provinces make {sums}, and its total rows say {totals}")
            continue
        out = out if len(out) >= len(found) else found
        seen = seen or f"; the table's lines: {' '.join(tokens[:160])}"
    raise SystemExit(f"burkina_provinces: the province table gives {sorted(out)} of "
                     f"{provinces}{seen}")


def regional_total(text: str) -> tuple[int, int, int]:
    """The region's men, women and total (Tableau 2.1's Ensemble row): the first
    title of the table that is not the list of tables' entry for it."""
    flat = re.sub(r"\s+", " ", text)
    for m in re.finditer(r"(?i)milieu\s+de\s+r[ée]sidence\s+selon\s+le\s+sexe\s+en\s+2019", flat):
        window = flat[m.end():m.end() + 1500]
        if re.match(r"\s*\.{3,}|\s*_{3,}", window):
            continue                       # the list of tables
        tokens = window.split()
        rows = total_row(tokens)
        if rows:
            return rows[0]
    raise SystemExit("burkina_provinces: no regional count by sex")


def read(region: str) -> tuple[str, str]:
    from pypdf import PdfReader

    for path in MONOGRAPHS[region]:
        url = BASE + path
        try:
            blob = fetch_blob(url)
        except Exception as err:  # noqa: BLE001 -- the next name is tried
            log(f"  {region}: {url}: {type(err).__name__}: {err}")
            continue
        if blob.startswith(b"%PDF"):
            log(f"  {region}: read {url}: {len(blob):,} bytes, sha256 "
                f"{hashlib.sha256(blob).hexdigest()}")
            reader = PdfReader(io.BytesIO(blob))
            return url, "\f".join((p.extract_text() or "") for p in reader.pages[:70])
    return "", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    admin1 = json.loads((SITE / "admin1" / "BFA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "BFA.units.json").read_text())
    regions = {u["id"]: u["name"] for u in admin1}
    provinces: dict[str, list[dict[str, Any]]] = {}
    for u in admin2:
        provinces.setdefault(regions[u["parent"]], []).append(u)
    records = []
    for region, shapes in sorted(provinces.items()):
        url, text = read(region)
        if not text:
            log(f"  {region}: no monograph read; its provinces are left as they are")
            continue
        names = [s["name"] for s in shapes]
        try:
            if len(shapes) == 1:
                table = {names[0]: regional_total(text)}
                where = "Tableau 2.1, the region's count, the province being the whole region"
            else:
                table = province_table(text, names)
                where = "Tableau 2.3, population by province and sex"
        except SystemExit as err:
            log(f"  {region}: {err}; its provinces are left as they are")
            continue
        source = (f"{PUBLISHER}, Cinquième Recensement Général de la Population et de "
                  f"l'Habitat (RGPH) 2019, Monographie de la région {region} ({where})")
        for s in shapes:
            men, women, total = table[s["name"]]
            log(f"    {s['name']}: {men:,} men, {women:,} women, {total:,}")
            records.append(record(
                f"BFA-RGPH2019-{fold(s['name'])}", s["name"], level="admin2", parent="BFA",
                country="BFA", match_by="shape_id", shape_id=s["id"],
                sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                                  year=YEAR, source=source),
                sex_ratio_note=(f"The 2019 census's count of the province: {men:,} men and "
                                f"{women:,} women."),
                sources=[{"field": "sex_ratio", "name": source, "url": url,
                          "license": LICENCE, "year": YEAR}]))
    log(f"  {len(records)} provinces written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
