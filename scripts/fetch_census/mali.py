#!/usr/bin/env python3
"""Mali: religion, ethnic group and mother tongue by region, RGPH5 2022.

Mali's nine first-level shapes carried Afrobarometer's survey shares for
religion and ethnicity (a few hundred respondents per region, two regions too
thin to estimate) and the 2009 census for language. The fifth Recensement
Général de la Population et de l'Habitat, taken in 2022, asked all three of
everyone, and INSTAT's thematic report *Caractéristiques culturelles de la
population* prints them by region: Tableau 2.03 (religion) in the body, and
annex Tableau 5 (ethnie) and Tableau 6 (langue maternelle). A census beats a
survey wherever both exist, so this replaces the survey figures, and because
it replaces figures already on the map the repository owner reviews the change
before it ships.

**Twenty regions into nine shapes.** The report tabulates the 2023 layout of
19 regions and the District of Bamako. The boundary file draws the 2012
layout of eight regions and Bamako, and every new region was carved whole out
of one old one (Kita and Nioro from Kayes, Dioïla and Nara from Koulikoro,
Bougouni and Koutiala from Sikasso, San from Ségou, Bandiagara and Douentza
from Mopti, Taoudénit from Tombouctou, Ménaka from Gao), so the old region is
the sum of the new ones. Every table prints percentages and each region's
population, and the sum is taken on counts rebuilt from the two -- a percent
of a stated population -- never on percentages, which cannot be added.

**How the annex is read.** Tableau 2.03 is ordinary text and is read as
lines. The annex tables are landscape pages stored upside down: pdfplumber
sees every character mirrored, so a cell reads "arabmaB/nanamaB" and a
population "8361 855", and a text reader sees the same plus every wrapped
cell in fragments. So the annex is read cell by cell from the ruling lines
(``probe_pdf.tables_of``), each token of a cell is turned back round, and a
label is recognised by the letters it is made of rather than their order,
which a wrap or a mirror cannot change. Rows come out bottom-up, with a
region's name in the row of its figures or the row after, so a row's label
is whatever run of neighbouring fragments spells a region. Each region's
shares must sum to 100, and the national row is recomputed from the regions
and their populations and must agree with the printed one, which is the
check that the populations were read from the right cells.

Usage:
    python -m scripts.fetch_census.mali
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_blob, tables_of  # noqa: E402

OUT = "mali_rgph5_region.json"
YEAR = 2022
URL = ("https://www.instat-mali.org/laravel-filemanager/files/shares/rgph/"
       "rapport-caracteristiques-culturelles-population-rgph5_rpgh.pdf")
PAGE = ("https://www.instat-mali.org/fr/publications/"
        "recensement-general-de-la-population-et-de-lhabitat-rgph")
SOURCE = ("INSTAT Mali, 5ème Recensement Général de la Population et de l'Habitat (RGPH5, "
          "2022), rapport thématique Caractéristiques culturelles de la population")
LICENCE = "Official statistics publication of the Institut National de la Statistique du Mali"

# The report's 20 regions -> the boundary file's 9 shapes (2012 layout).
REGIONS: dict[str, str] = {
    "Kayes": "Kayes", "Kita": "Kayes", "Nioro": "Kayes",
    "Koulikoro": "Koulikoro", "Dioïla": "Koulikoro", "Nara": "Koulikoro",
    "Sikasso": "Sikasso", "Bougouni": "Sikasso", "Koutiala": "Sikasso",
    "Ségou": "Ségou", "San": "Ségou",
    "Mopti": "Mopti", "Bandiagara": "Mopti", "Douentza": "Mopti",
    "Tombouctou": "Tombouctou", "Taoudenni": "Tombouctou",
    "Gao": "Gao", "Ménaka": "Gao",
    "Kidal": "Kidal",
    "Bamako": "Bamako",
}
# The annex spells a few regions differently from the body.
SPELLINGS = {"Taoudénit": "Taoudenni", "Segou": "Ségou", "Dioila": "Dioïla", "Menaka": "Ménaka"}
# geoBoundaries writes an extra u into Koulikoro and no accent on Ségou.
ALIASES = {"Koulikoro": ["Koulikouro"], "Ségou": ["Segou"]}
MERGED_NOTE = {
    shape: "the report's " + ", ".join(r for r, s in REGIONS.items() if s == shape)
    + " regions of the 2023 layout, summed"
    for shape in set(REGIONS.values())
    if sum(1 for s in REGIONS.values() if s == shape) > 1
}

RELIGIONS = ["Islam", "Christianity", "Animist", "No religion", "Other religion"]
# Annex column labels as printed (a wrap or a mirror does not matter, only
# the letters), and the label each carries on the map.
ETHNICITIES = {
    "Bamanan/Bambara": "Bambara", "Malinke/Malinké": "Malinke", "Peulh": "Fula",
    "Songhay/Sonrhai/Zarma": "Songhai/Zarma", "Soninké/Sarakolé": "Soninke",
    "Khassonke": "Khassonke", "Sénoufo": "Senufo", "Dogon": "Dogon",
    "Souraka/Maure": "Moor", "Tamasheq/Touareg": "Tuareg", "Bo/Bwa/Bobo": "Bobo",
    "Dafing": "Dafing", "Mamala/Minianka": "Minianka", "Haoussa": "Hausa",
    "Samogo": "Samogo", "Bozo": "Bozo", "Arabe": "Arab", "Mossi": "Mossi",
    "Kakolo": "Kakolo", "Somono": "Somono",
    "Autre ethnie du Mali": "Other Malian ethnic group",
    "Autre ethnie non malienne": "Other non-Malian ethnic group",
}
LANGUAGES = {
    "Bambara/Bamanankan": "Bambara", "Malinké/Maninkakan": "Malinke",
    "Peulh/Fulfulde": "Fula/fulfulbe", "Sonrhai/Songhoy/Zarma": "Sonrhai/Djerma",
    "Sarakole/Sooninke": "Maraka/Soninke", "Khassonké/Xhassonkakan": "Khassonke",
    "Sénoufo/Syenara": "Senufo", "Dogon/Dôgôsô": "Dogon", "Maure/Hasaniya": "Hassaniya",
    "Tamasheq": "Tamasheq", "Bobo/Bomu": "Bobo", "Kunabere": "Kunabere",
    "Dafing": "Dafing", "Minianka/Mamara": "Minianka", "Haoussa": "Hausa",
    "Mossi/Moré": "Mossi", "Samogo/Dungooma": "Samogo", "Bozo/Tyako": "Bozo",
    "Arabe": "Arabic", "Autre langue du Mali": "Other Mali languages",
    "Autre langue africaine": "Other African languages",
    "Autre langue étrangère": "Other foreign language",
    "Autre langue non africaine": "Other non-African language",
}
HEADINGS = {"ethnicity": "A05 : Tableau 5", "language": "A06 : Tableau 6"}
NOTES = {
    "religion": "Tableau 2.03: the resident population by religion as the census asks it "
                "(Musulman, Chrétien, Animiste, Sans religion, Autre religion).",
    "ethnicity": "Annex Tableau 5: the 22 ethnies the census names, of the Malian "
                 "population (the report's Autre ethnie non malienne is kept as a group; "
                 "foreign nationals are outside the table). Bamanan/Bambara is shown as "
                 "Bambara, Peulh as Fula, Souraka/Maure as Moor, Tamasheq/Touareg as Tuareg.",
    "language": "Annex Tableau 6: langue maternelle as the census groups it, of the "
                "19.1 million people the table covers against a resident population of "
                "21.3 million; the report does not state the table's age floor. "
                "Sonrhai/Songhoy/Zarma is shown as Sonrhai/Djerma and Sarakole/Sooninke as "
                "Maraka/Soninke, the forms the 2009 census used on this map.",
}


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def key(text: str) -> str:
    """The letters of a label, sorted: what a wrap or a mirror leaves alone."""
    return "".join(sorted(c for c in fold(text).lower() if c.isalpha()))


REGION_KEYS = {key(r): r for r in REGIONS}
REGION_KEYS.update({key(a): r for a, r in SPELLINGS.items()})
REGION_KEYS[key("Ensemble")] = "Ensemble"
REGION_KEYS[key("Total")] = "Ensemble"
for _labels in (REGIONS, SPELLINGS, ETHNICITIES, LANGUAGES):
    assert len({key(k) for k in _labels}) == len(_labels), "two labels share their letters"


def number(text: str) -> float:
    return float(text.replace(" ", "").replace(",", "."))


def flip(cell: str | None) -> str:
    """A mirrored cell the right way round: each token reversed, tokens joined.

    "8361 855" is the population 1638558 wrapped over two lines; "0,001 0"
    is 100,00; "arabmaB/nanamaB" is Bamanan/Bambara.
    """
    return "".join(t[::-1] for t in re.split(r"[\s⏎]+", (cell or "").strip()) if t)


PERCENT = re.compile(r"^\d+,\d\d$")
COUNT = re.compile(r"^\d{2,}$")


def read_annex(rows: list[list[str]], groups: dict[str, str]
               ) -> dict[str, tuple[int | None, dict[str, float]]]:
    """{region: (population or None, {label: percent})} from one mirrored table.

    With ``groups`` empty the table is a continuation carrying only each
    region's total and population.
    """
    keys = {key(fr): en for fr, en in groups.items()}
    header: dict[int, str] = {}
    for row in rows:
        hit = {i: keys[key(c)] for i, c in enumerate(row) if c and key(c) in keys}
        if len(hit) > len(header):
            header = hit
    if len(header) != len(groups):
        raise SystemExit(f"mali: the annex table's header names {len(header)} of "
                         f"{len(groups)} expected columns")

    def label_of(fragments: list[str]) -> str | None:
        for width in range(len(fragments), 0, -1):
            for start in range(0, len(fragments) - width + 1):
                found = REGION_KEYS.get(key("".join(fragments[start:start + width])))
                if found:
                    return found
        return None

    out: dict[str, tuple[int | None, dict[str, float]]] = {}
    pending: list[Any] | None = None

    def close() -> None:
        if pending is None:
            return
        values, counts, fragments = pending
        name = label_of(fragments)
        if name is None:
            raise SystemExit(f"mali: an annex row's label spells no region: {fragments}")
        if len(counts) > 1:
            raise SystemExit(f"mali: {name} carries two populations: {counts}")
        if name in out:
            raise SystemExit(f"mali: {name} appears twice in one annex table")
        out[name] = (counts[0] if counts else None, values)

    for row in rows:
        cells = [flip(c) for c in row]
        values = {en: number(cells[i]) for i, en in header.items()
                  if i < len(cells) and PERCENT.match(cells[i])}
        counts = [int(c) for i, c in enumerate(cells) if i not in header and COUNT.match(c)]
        fragments = [c for i, c in enumerate(cells)
                     if i not in header and c and not PERCENT.match(c) and not COUNT.match(c)]
        is_data = len(values) == len(header) if header else bool(counts)
        if is_data:
            close()
            pending = [values, counts, fragments]
        elif pending is not None:
            pending[2].extend(fragments)
    close()
    return out


def religion_rows(text: str) -> dict[str, tuple[int, dict[str, float]]]:
    """{report region: (population, {religion: percent})} from Tableau 2.03."""
    # pypdf hands back accents as combining marks on some pages, so the text
    # is composed before any name is compared, and the header is checked
    # with the accents folded away.
    text = unicodedata.normalize("NFC", text)
    # The list of tables names Tableau 2.03 too; the table's page is the one
    # that also carries its column heads.
    head = re.compile(r"Musulman\s+Chretien\s+Animiste\s+Sans")
    named = [p for p in text.split(PAGE_BREAK) if "Tableau 2.03" in p]
    if not named:
        raise SystemExit("mali: no page carries 'Tableau 2.03'")
    page = next((p for p in named if head.search(fold(p))), None)
    if page is None:
        raise SystemExit("mali: no page naming Tableau 2.03 carries the columns Musulman, "
                         "Chrétien, Animiste, Sans religion, Autre religion")
    row = re.compile(r"^(\S+(?: \S+)?)\s+" + r"\s+".join([r"(\d+,\d+)"] * 5)
                     + r"\s+100,00\s+([\d ]+\d)\s*$")
    out: dict[str, tuple[int, dict[str, float]]] = {}
    for line in page.splitlines():
        m = row.match(line.strip())
        if not m:
            continue
        name = SPELLINGS.get(m.group(1), m.group(1))
        pcts = [number(g) for g in m.groups()[1:6]]
        if name == "Ensemble":
            continue
        if name not in REGIONS:
            raise SystemExit(f"mali: Tableau 2.03 names a region this reader does not "
                             f"know: {name!r}")
        out[name] = (int(number(m.group(7))), dict(zip(RELIGIONS, pcts)))
    return out


def checked(field: str, table: dict[str, tuple[int | None, dict[str, float]]]
            ) -> dict[str, tuple[int, dict[str, float]]]:
    """Every region present with a population, shares summing to 100, and the
    national row recomputed from the regions agreeing with the printed one."""
    national = table.pop("Ensemble", None)
    missing = sorted(set(REGIONS) - set(table))
    if missing or set(table) - set(REGIONS):
        raise SystemExit(f"mali: {field} lacks {missing}, has {sorted(set(table) - set(REGIONS))}")
    out: dict[str, tuple[int, dict[str, float]]] = {}
    for region, (pop, pcts) in table.items():
        if not pop:
            raise SystemExit(f"mali: {field} {region} has no population")
        if abs(sum(pcts.values()) - 100) > 0.3:
            raise SystemExit(f"mali: {field} {region} shares sum to {sum(pcts.values()):.2f}")
        out[region] = (pop, pcts)
    if national is not None:
        total = sum(p for p, _ in out.values())
        # A population read from the wrong cell moves a national share by whole
        # points. Tableau 6's own printed row differs from its regional rows by
        # 0.12 (Bambara) and 0.14 (Tamasheq) with every region summing to 100
        # and the populations summing to the printed total, which is the
        # report's arithmetic, not this reader's; Tableau 5 agrees to 0.02.
        for label, printed in national[1].items():
            rebuilt = sum(p * pcts[label] for p, pcts in out.values()) / total
            if abs(rebuilt - printed) > 0.2:
                raise SystemExit(f"mali: {field} {label} rebuilt from the regions is "
                                 f"{rebuilt:.2f} against a printed {printed:.2f}; a "
                                 f"population was read from the wrong cell")
        if national[0] and abs(national[0] - total) > 5:
            raise SystemExit(f"mali: {field} regions sum to {total:,} against a printed "
                             f"{national[0]:,}")
    return out


def summed(rows: dict[str, tuple[int, dict[str, float]]]
           ) -> dict[str, tuple[int, dict[str, float]]]:
    """Counts rebuilt from percent x population, added into the 2012 shapes."""
    out: dict[str, tuple[int, dict[str, float]]] = {}
    for region, (pop, pcts) in rows.items():
        shape = REGIONS[region]
        total, counts = out.get(shape, (0, {}))
        for label, pct in pcts.items():
            counts[label] = counts.get(label, 0.0) + pct * pop / 100.0
        out[shape] = (total + pop, counts)
    return out


def annex_pages(text: str) -> dict[str, int]:
    """{field: 0-based page} of each annex table: the last page naming it, since
    the list of tables names it first."""
    pages = text.split(PAGE_BREAK)
    out = {}
    for field, heading in HEADINGS.items():
        hits = [i for i, p in enumerate(pages) if heading in p]
        if not hits:
            raise SystemExit(f"mali: no page carries {heading!r}")
        out[field] = hits[-1]
    return out


def read_all(text: str, tables: dict[int, list[list[list[str]]]], where: dict[str, int]
             ) -> dict[str, dict[str, tuple[int, dict[str, float]]]]:
    """{field: {region: (population, {label: percent})}} for all three fields."""
    out = {"religion": checked("religion", dict(religion_rows(text)))}
    # Tableau 5 carries its populations; Tableau 6 prints them on the page after.
    ethnicity = best(tables[where["ethnicity"]], ETHNICITIES)
    out["ethnicity"] = checked("ethnicity", ethnicity)
    language = best(tables[where["language"]], LANGUAGES)
    totals = best(tables[where["language"] + 1], {})
    for region, (pop, pcts) in language.items():
        if region not in totals or not totals[region][0]:
            raise SystemExit(f"mali: the page after Tableau 6 carries no population for {region}")
        language[region] = (totals[region][0], pcts)
    out["language"] = checked("language", language)
    return out


def best(page_tables: list[list[list[str]]], groups: dict[str, str]
         ) -> dict[str, tuple[int | None, dict[str, float]]]:
    """The one table on a page that reads as the wanted one."""
    errors = []
    for table in page_tables:
        try:
            got = read_annex(table, groups)
        except SystemExit as e:
            errors.append(str(e))
            continue
        if len(got) >= len(REGIONS):
            return got
    raise SystemExit("mali: no table on the page reads as expected: " + "; ".join(errors))


def build(fields: dict[str, dict[str, tuple[int, dict[str, float]]]]) -> list[dict[str, Any]]:
    per_shape = {field: summed(rows) for field, rows in fields.items()}
    src = [{"field": "religion/ethnicity/language", "name": SOURCE, "url": URL,
            "license": LICENCE}]
    records: list[dict[str, Any]] = []
    from common import slugify
    for shape in sorted(set(REGIONS.values())):
        values: dict[str, Any] = {}
        for field in per_shape:
            pop, counts = per_shape[field][shape]
            values[field] = shares({k: v for k, v in counts.items() if v >= 0.5}, total=pop)
            note = (f"{SOURCE}. {NOTES[field]} The report prints each region's shares to "
                    f"two decimals and its population, and the counts here are the one "
                    f"applied to the other.")
            if shape in MERGED_NOTE:
                note += f" This shape is {MERGED_NOTE[shape]}."
            values[f"{field}_note"] = note
            values[f"{field}_year"] = YEAR
        records.append(record(
            f"MLI-{slugify(shape)}-rgph5", shape, level="admin1", parent="MLI", country="MLI",
            aliases=ALIASES.get(shape, []), sources=src, **values,
        ))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    import io
    from pypdf import PdfReader

    log(f"mali: {SOURCE}")
    blob = fetch_blob(URL)
    reader = PdfReader(io.BytesIO(blob))
    text = unicodedata.normalize(
        "NFC", PAGE_BREAK.join((p.extract_text() or "") for p in reader.pages))
    log(f"  {len(reader.pages)} pages")
    where = annex_pages(text)
    log(f"  annex tables on pages {', '.join(f'{f} {p + 1}' for f, p in where.items())}")
    wanted = sorted({where["ethnicity"], where["language"], where["language"] + 1})
    tables = {i - 1: t for i, t in tables_of(blob, [i + 1 for i in wanted]).items()}
    fields = read_all(text, tables, where)
    for field, rows in fields.items():
        log(f"  {field}: {len(rows)} regions, {sum(p for p, _ in rows.values()):,} people")
    records = build(fields)
    log(f"  {len(records)} shapes")
    if len(records) != 9:
        raise SystemExit(f"mali: expected 9 shapes, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
