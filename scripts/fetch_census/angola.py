#!/usr/bin/env python3
"""Angola: ethnic group, mother tongue and religion by province, Censo 2024.

Angola's 18 provinces carried Afrobarometer's survey shares (a few dozen
respondents per province). The 2024 Recenseamento Geral da População e
Habitação counted all three for everyone aged two and over, and its
*Relatório dos Resultados Definitivos* prints each by province: Quadro 6.1
(grupos étnicos ou tribos), Quadro 6.2 (língua materna) and Quadro 7.1
(religião ou espiritualidade). A census beats a survey wherever both exist,
so this replaces the survey figures, and because it replaces figures already
on the map the repository owner reviews the change before it ships.

**How the PDF is read.** The report is a PDF and nothing else. Each table is
wider than a page, so its columns are printed in two groups on separate
pages, each group repeating the province rows; and each figure is printed
with spaces for thousands ("34 492 888"), so a row read as text cannot say
where one figure ends and the next begins ("5 614 198 210" is two figures or
three). The reader therefore takes every word with its x-coordinates from
pdfplumber (``probe_pdf.laid_out``), joins digit groups that sit within a few
points of each other into one figure, and refuses any row that does not
yield exactly the number of columns the table has. Every province's figures
are then checked against its own "2 or more years" total, which both column
groups carry, so a column read into the wrong slot cannot pass.

**21 provinces on paper, 18 on the map.** The census was tabulated on the
provinces created in 2024, which the boundary file predates: Icolo e Bengo
was carved out of Luanda, Moxico Leste out of Moxico, and Cuando Cubango was
split into Cuando and Cubango. These are counts, so each pair is summed back
into the shape it came from, which is exact.

**Universe.** All three tables cover the population aged two and over, and
the record says so.

Usage:
    python -m scripts.fetch_census.angola
    python -m scripts.fetch_census.angola --text saved-layout.txt   # offline
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, shares, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, laid_out  # noqa: E402

OUT = "angola_province.json"
YEAR = 2024
URL = "https://censo2024.ine.gov.ao/Relatorio_Geral_Angola_Censo2024.pdf"
PAGE = "https://censo2024.ine.gov.ao/"
SOURCE = ("INE Angola, Recenseamento Geral da População e Habitação 2024, Relatório dos "
          "Resultados Definitivos (Quadros 6.1, 6.2 and 7.1)")
LICENCE = "Official statistics publication of the Instituto Nacional de Estatística de Angola"
UNIVERSE = "population aged 2 and over"

# The report's 21 provinces -> the boundary file's 18 shapes.
PROVINCES: dict[str, str] = {
    "Cabinda": "Cabinda", "Zaire": "Zaire", "Uíge": "Uíge", "Bengo": "Bengo",
    "Luanda": "Luanda", "Cuanza-Norte": "Cuanza Norte", "Cuanza Sul": "Cuanza Sul",
    "Malanje": "Malanje", "Lunda Norte": "Lunda Norte", "Lunda Sul": "Lunda Sul",
    "Moxico": "Moxico", "Bié": "Bié", "Huambo": "Huambo", "Benguela": "Benguela",
    "Namibe": "Namibe", "Huíla": "Huíla", "Cunene": "Cunene",
    "Cubango": "Cuando Cubango", "Cuando": "Cuando Cubango",      # split in 2024
    "Icolo e Bengo": "Luanda",                                    # carved out of Luanda, 2024
    "Moxico Leste": "Moxico",                                     # carved out of Moxico, 2024
}
MERGED_NOTE = {
    "Cuando Cubango": "the report's Cuando and Cubango provinces, summed",
    "Luanda": "the report's Luanda and Icolo e Bengo provinces, summed",
    "Moxico": "the report's Moxico and Moxico Leste provinces, summed",
}

# Each table: its heading, and its column groups in page order. A group is
# the labels of its figures left to right, in the order the header words sit
# on the page (read from their x positions, since the header wraps over five
# lines and its reading order is not its column order: on 7.1 "Bom Deus" is
# the second column and "Universal do reino de Deus" the seventh); "TOTAL" marks the "2 or more
# years" column, which every row carries and which the check is made against.
TABLES: dict[str, dict[str, Any]] = {
    "ethnicity": {
        "heading": "Quadro 6.1",
        "groups": [
            ["Bakongo", "Ambundu", "Lunda-Chokwe", "Ovimbundu", "Nyaneka-Humbe", "Ovambo",
             "Herero"],
            ["Cuangar", "Khoisan", "Vátua", "Kwoi", "Ndonga", "Not stated", "Other", "TOTAL"],
        ],
    },
    "language": {
        "heading": "Quadro 6.2",
        "groups": [
            ["TOTAL", "Portuguese", "Kimbundu", "Umbundu", "Chokwe", "Kikongo", "Nyaneka",
             "Ngangela", "Kwanyama", "Fiote", "Humbi", "Luvale", "Khoisan"],
            ["TOTAL", "Mandarin", "English", "French", "Spanish", "German", "Russian",
             "Arabic", "Lingala", "Creole", "Other languages", "Not stated"],
        ],
    },
    "religion": {
        "heading": "Quadro 7.1",
        "groups": [
            ["TOTAL", "Catholic", "Bom Deus Church", "Islam", "Animist", "Judaism",
             "Protestant", "Universal Church of the Kingdom of God", "New Apostolic",
             "Tocoist"],
            ["TOTAL", "Kimbanguist", "Josafat Church", "Assemblies of God (Pentecostal)",
             "Jehovah's Witnesses", "Methodist", "Evangelical", "Adventist", "Baptist",
             "Mensagem dos Últimos Tempos Church", "No religion", "Other religion",
             "Not stated"],
        ],
    },
}
NOTES = {
    "ethnicity": "Grupos étnicos ou tribos as the census names them: Quicongo is shown as "
                 "Bakongo, Quimbundu as Ambundu, Lunda-Quioco as Lunda-Chokwe, Nhaneca-Humbe "
                 "as Nyaneka-Humbe, Ambó as Ovambo, Helelo as Herero, Xindonga as Ndonga.",
    "language": "Língua materna as the census groups it (its footnote folds Mbongala, Songo "
                "and Ngoya into Kimbundu, Mukubale into Umbundu, Lunda into Cokue, and so on).",
    "religion": "Religião declarada as the census lists it; the denominations are kept "
                "apart as printed.",
}

WORD = re.compile(r"(\S+?)\[(\d+)-(\d+)\]")
BOX = re.compile(r"\[\d+-\d+\]")
GAP = 4.5          # points; digit groups of one figure sit closer than this


def figures(cells: list[tuple[float, float, str]]) -> list[int]:
    """Digit groups joined into figures by the gaps between them."""
    out: list[int] = []
    run: list[str] = []
    last_x1 = None
    for x0, x1, text in cells:
        if not text.isdigit():
            if run:
                out.append(int("".join(run)))
                run = []
            last_x1 = None
            continue
        if run and last_x1 is not None and x0 - last_x1 <= GAP and len(text) == 3:
            run.append(text)
        else:
            if run:
                out.append(int("".join(run)))
            run = [text]
        last_x1 = x1
    if run:
        out.append(int("".join(run)))
    return out


def parse_row(line: str) -> tuple[str, list[int]]:
    """'Cuanza-Norte[40-95] 619[300-315] 011[317-330] ...' -> ('Cuanza-Norte', [619011, ...])."""
    cells = [(float(a), float(b), t) for t, a, b in WORD.findall(line)]
    label = " ".join(t for _, _, t in cells if not t.isdigit()).strip()
    return label, figures([c for c in cells if c[2].isdigit()])


def province_rows(page: str) -> dict[str, list[int]]:
    """The first block of province rows on a page: every name once, in order."""
    out: dict[str, list[int]] = {}
    for line in page.splitlines():
        label, values = parse_row(line)
        if label in PROVINCES and values:
            if label in out:
                break                      # the Urbana block repeats the names
            out[label] = values
    return out


def read_tables(text: str) -> dict[str, dict[str, dict[str, int]]]:
    """{field: {report province: {label: count, 'TOTAL': n}}} from the laid-out text."""
    pages = text.split(PAGE_BREAK)
    out: dict[str, dict[str, dict[str, int]]] = {}
    for field, spec in TABLES.items():
        # The heading's words carry their boxes ("Quadro[192-224] 6.1[226-239]"),
        # and the list of tables names every heading too, so the table's page
        # is the first that carries the heading and a province row of figures.
        start = next((i for i, p in enumerate(pages)
                      if spec["heading"] in BOX.sub("", p) and province_rows(p)), None)
        if start is None:
            raise SystemExit(f"angola: no page carries {spec['heading']!r} and province rows")
        counts: dict[str, dict[str, int]] = {p: {} for p in PROVINCES}
        page = start
        for labels in spec["groups"]:
            # The group's page is the next one whose province rows carry
            # exactly this many figures.
            while page < len(pages):
                rows = province_rows(pages[page])
                if len(rows) == len(PROVINCES) and all(len(v) == len(labels) for v in rows.values()):
                    break
                if rows and len(rows) == len(PROVINCES):
                    widths = sorted({len(v) for v in rows.values()})
                    if widths != [len(labels)]:
                        log(f"  {field}: page {page + 1} rows carry {widths} figures, "
                            f"wanted {len(labels)}")
                page += 1
            else:
                raise SystemExit(f"angola: no page after {spec['heading']} yields "
                                 f"{len(PROVINCES)} provinces x {len(labels)} figures")
            for province, values in province_rows(pages[page]).items():
                for label, n in zip(labels, values):
                    if label == "TOTAL" and "TOTAL" in counts[province] \
                            and counts[province]["TOTAL"] != n:
                        raise SystemExit(f"angola: {province} {field} totals disagree between "
                                         f"column groups: {counts[province]['TOTAL']} vs {n}")
                    counts[province][label] = n
            log(f"  {field}: {spec['heading']} group of {len(labels)} figures on page {page + 1}")
            page += 1
        out[field] = counts
    return out


def merged(counts: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for province, values in counts.items():
        target = out.setdefault(PROVINCES[province], {})
        for label, n in values.items():
            target[label] = target.get(label, 0) + n
    return out


def bars(field: str, shape: str, values: dict[str, int]) -> Any:
    total = values.get("TOTAL")
    if not total:
        raise SystemExit(f"angola: {shape} {field} has no total")
    groups = {k: v for k, v in values.items() if k != "TOTAL"}
    summed = sum(groups.values())
    if abs(summed - total) > max(0.005 * total, 5):
        raise SystemExit(f"angola: {shape} {field} sums to {summed:,} against the total "
                         f"{total:,}; a column was read into the wrong slot")
    return shares({k: v for k, v in groups.items() if v}, total=total) or gap(NOT_AVAILABLE)


def build(text: str) -> list[dict[str, Any]]:
    tables = read_tables(text)
    per_shape = {field: merged(counts) for field, counts in tables.items()}
    records: list[dict[str, Any]] = []
    src = [{"field": "ethnicity/language/religion", "name": SOURCE, "url": URL,
            "license": LICENCE}]
    for shape in sorted(set(PROVINCES.values())):
        fields: dict[str, Any] = {}
        for field in TABLES:
            fields[field] = bars(field, shape, per_shape[field][shape])
            note = f"{SOURCE}. A census count of the {UNIVERSE}. {NOTES[field]}"
            if shape in MERGED_NOTE:
                note += f" This shape is {MERGED_NOTE[shape]}."
            fields[f"{field}_note"] = note
        from common import slugify
        records.append(record(
            f"AGO-{slugify(shape)}", shape, level="admin1", parent="AGO", country="AGO",
            aliases=["Cuanza-Norte"] if shape == "Cuanza Norte" else [],
            sources=src, **fields,
        ))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=None,
                    help="a saved probe_pdf --layout --boxes dump, instead of the PDF")
    args = ap.parse_args()
    log(f"angola: {SOURCE}")
    if args.text:
        text = Path(args.text).read_text(encoding="utf-8")
    else:
        blob = http_get(URL, binary=True, timeout=600)
        log(f"  {len(blob):,} bytes")
        text = laid_out(blob, boxes=True)
    records = build(text)
    log(f"  {len(records)} provinces")
    if len(records) != 18:
        raise SystemExit(f"angola: expected 18 provinces, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
