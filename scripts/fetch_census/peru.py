#!/usr/bin/env python3
"""Peru: religion and mother tongue by department, Censos Nacionales 2017.

INEI's *Perfil Sociodemográfico del Perú* (Lib1539) prints the 2017 census
by department: Cuadro 2.64 gives the mother tongue learned in childhood of
everyone aged 5 and over, and Cuadros 2.78 to 2.81 give, one religion at a
time, the population aged 12 and over that professes the Catholic faith,
the Evangelical faith, another religion, and none. The four are one
partition of the same total, so read together they are the composition.
Nothing was recorded for Peru before, so this fills a gap.

**How the book is read.** Every figure is printed with spaces for thousands
and a comma for decimals, and two of the religion tables are set in a font
pdfplumber sees one letter at a time ("T o ta l 2 0 8 5 0 5 0 2"), so a row
read as text cannot say where a number ends. Each row is therefore read
from word positions: tokens closer than GAP points are one cell, whatever
they are, and a department is recognised by the letters of its name with
spaces and footnote marks removed. Every religion table's share is checked
against its own count and total, the four tables must agree on each
department's total, their counts must sum to it, and the two halves of the
language table must agree on the department's total.

**Lima.** The book lists Lima whole and then Provincia de Lima (the 43
districts) and Región Lima (the other nine provinces) separately; the
boundary file draws the two parts, so the parts are read and the whole is
used only as a check.

Usage:
    python -m scripts.fetch_census.peru
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
from probe_pdf import PAGE_BREAK, fetch_blob, laid_out  # noqa: E402

OUT = "peru_department.json"
YEAR = 2017
URL = "https://www.inei.gob.pe/media/MenuRecursivo/publicaciones_digitales/Est/Lib1539/libro.pdf"
SOURCE = ("INEI, Censos Nacionales 2017: XII de Población y VII de Vivienda, Perú: Perfil "
          "Sociodemográfico (Informe Nacional)")
LICENCE = "Official statistics publication of the Instituto Nacional de Estadística e Informática"

# Book label -> shape name. "Lima" whole is a check, not a shape.
DEPARTMENTS: dict[str, str] = {
    "Amazonas": "Amazonas", "Áncash": "Ancash", "Apurímac": "Apurímac", "Arequipa": "Arequipa",
    "Ayacucho": "Ayacucho", "Cajamarca": "Cajamarca", "Prov. Const. del Callao": "El Callao",
    "Cusco": "Cusco", "Huancavelica": "Huancavelica", "Huánuco": "Huánuco", "Ica": "Ica",
    "Junín": "Junín", "La Libertad": "La Libertad", "Lambayeque": "Lambayeque",
    "Loreto": "Loreto", "Madre de Dios": "Madre de Dios", "Moquegua": "Moquegua",
    "Pasco": "Pasco", "Piura": "Piura", "Puno": "Puno", "San Martín": "San Martín",
    "Tacna": "Tacna", "Tumbes": "Tumbes", "Ucayali": "Ucayali",
    "Provincia de Lima": "Municipalidad Metropolitana de Lima",
    "Región Lima": "Lima",
}
ALIASES = {"Ancash": ["Áncash"], "El Callao": ["Callao", "Prov. Const. del Callao"],
           "Municipalidad Metropolitana de Lima": ["Provincia de Lima", "Lima Metropolitana"],
           "Lima": ["Región Lima"]}
WHOLE = "Lima (whole)"              # the row that is the two Lima parts summed

LANGUAGE_A = ["TOTAL", "Spanish", "%", "Quechua", "%", "Aymara", "%"]
LANGUAGE_B = ["Asháninka", "Awajún", "Shipibo-Konibo", "Shawi", "Other native language",
              "Foreign language", "Deaf, does not speak", "Peruvian Sign Language",
              "Not stated"]
RELIGIONS = {"2.78": "Catholic", "2.79": "Evangelical", "2.80": "Other religion",
             "2.81": "No religion"}
NOTES = {
    "language": "Cuadro 2.64: lengua materna aprendida en la niñez of the population aged "
                "5 and over, as the census groups it (Otra lengua nativa folds Matsigenka, "
                "Achuar, Kichwa, Tikuna, Nomatsigenga and others).",
    "religion": "Cuadros 2.78 to 2.81: religión que profesa of the population aged 12 and "
                "over, in the four classes the census publishes; Otra folds Cristiano, "
                "Adventista, Testigo de Jehová, Mormón, Israelita, Budismo, Judaísmo and "
                "Musulmán.",
}

WORD = re.compile(r"(\S+?)\[(\d+)-(\d+)\]")
BOX = re.compile(r"\[\d+-\d+\]")
GAP = 4.5


def key(text: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return "".join(c for c in folded.lower() if c.isalpha())


DEPARTMENT_KEYS = {key(k): v for k, v in DEPARTMENTS.items()}
DEPARTMENT_KEYS[key("Lima")] = WHOLE


def cells(line: str) -> list[str]:
    """Tokens closer than GAP joined: "20[178-186] 850[188-199] 502[200-211]" is
    one cell "20850502"; "T[87-91] o[91-95] ta[95-101] l[101-102]" is "Total"."""
    out: list[str] = []
    last = None
    for text, a, b in WORD.findall(line):
        a, b = float(a), float(b)
        if out and last is not None and a - last <= GAP:
            out[-1] += text
        else:
            out.append(text)
        last = b
    return out


def number(cell: str) -> float | None:
    cell = cell.replace(" ", "")
    if cell in ("-", "–"):
        return 0.0
    if re.fullmatch(r"-?\d+", cell):
        return float(cell)
    if re.fullmatch(r"-?\d+,\d+", cell):
        return float(cell.replace(",", "."))
    return None


def parse_row(line: str) -> tuple[str | None, list[float]]:
    """(department, numbers) for a table row, or (None, []) for any other line."""
    parts = cells(line)
    label = ""
    values: list[float] = []
    for c in parts:
        n = number(c)
        if n is None:
            if values:
                return None, []            # letters after numbers: not a data row
            label += c
        else:
            values.append(n)
    return (DEPARTMENT_KEYS.get(key(label)) if label else None), values


def table_pages(text: str, heading: str) -> list[str]:
    return [p for p in text.split(PAGE_BREAK) if heading in BOX.sub("", p)]


def merged(*lines: str) -> str:
    """Two baselines of one row as one line, in x order: on the letter-spaced
    pages Región Lima's percentages sit on one line and its counts on the
    next, and which column each belongs to is a matter of position."""
    words = [(float(a), m) for line in lines for m in WORD.finditer(line)
             for a in (m.group(2),)]
    return " ".join(m.group(0) for _, m in sorted(words, key=lambda w: w[0]))


def rows_of(page: str, width: int) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    lines = page.splitlines()
    for i, line in enumerate(lines):
        name, values = parse_row(line)
        if not name:
            continue
        if len(values) != width:
            # A short row: its other figures may sit on the line below or above.
            for j in (i + 1, i - 1):
                if 0 <= j < len(lines) and parse_row(lines[j])[0] is None \
                        and cells(lines[j]) \
                        and all(number(c) is not None for c in cells(lines[j])):
                    name2, values2 = parse_row(merged(line, lines[j]))
                    if name2 == name and len(values2) == width:
                        values = values2
                        break
        if len(values) == width:
            if name in out:
                raise SystemExit(f"peru: {name} appears twice on one page")
            out[name] = values
    return out


def complete(field: str, rows: dict[str, list[float]]) -> None:
    missing = sorted((set(DEPARTMENTS.values()) | {WHOLE}) - set(rows))
    if missing:
        raise SystemExit(f"peru: {field} lacks rows for {missing}")


def read_language(text: str) -> dict[str, dict[str, float]]:
    """{shape: {label: count, 'TOTAL': n}} from the two halves of Cuadro 2.64."""
    pages = table_pages(text, "2.64")
    first = next((rows_of(p, len(LANGUAGE_A)) for p in pages
                  if len(rows_of(p, len(LANGUAGE_A))) >= len(DEPARTMENTS)), None)
    second = next((rows_of(p, len(LANGUAGE_B)) for p in pages
                   if len(rows_of(p, len(LANGUAGE_B))) >= len(DEPARTMENTS)), None)
    if first is None or second is None:
        raise SystemExit(f"peru: Cuadro 2.64 is not on two pages of {len(LANGUAGE_A)} and "
                         f"{len(LANGUAGE_B)} figures per department ({len(pages)} pages name it)")
    complete("language", first)
    complete("language", second)
    out: dict[str, dict[str, float]] = {}
    for name, a in first.items():
        total = a[0]
        counts = {"Spanish": a[1], "Quechua": a[3], "Aymara": a[5]}
        for label, pct, count in (("Spanish", a[2], a[1]), ("Quechua", a[4], a[3]),
                                  ("Aymara", a[6], a[5])):
            if abs(100 * count / total - pct) > 0.06:
                raise SystemExit(f"peru: {name} {label} {count:,.0f} of {total:,.0f} is not "
                                 f"the printed {pct}%")
        counts.update(dict(zip(LANGUAGE_B, second[name])))
        if abs(sum(counts.values()) - total) > 2:
            raise SystemExit(f"peru: {name} languages sum to {sum(counts.values()):,.0f} "
                             f"against a total of {total:,.0f}")
        counts["TOTAL"] = total
        out[name] = counts
    return out


def read_religion(text: str) -> dict[str, dict[str, float]]:
    """{shape: {label: count, 'TOTAL': n}} from Cuadros 2.78 to 2.81, the 2017
    columns (total, count, percent) of each."""
    out: dict[str, dict[str, float]] = {}
    for number_, label in RELIGIONS.items():
        pages = table_pages(text, f"Nº {number_}")
        rows = next((rows_of(p, 9) for p in pages if len(rows_of(p, 9)) >= len(DEPARTMENTS)), None)
        if rows is None:
            raise SystemExit(f"peru: Cuadro {number_} yields no page of 9 figures per department")
        complete(f"religion {label}", rows)
        for name, v in rows.items():
            total, count, pct = v[3], v[4], v[5]
            if abs(100 * count / total - pct) > 0.06:
                raise SystemExit(f"peru: {name} {label} {count:,.0f} of {total:,.0f} is not "
                                 f"the printed {pct}%")
            entry = out.setdefault(name, {"TOTAL": total})
            if entry["TOTAL"] != total:
                raise SystemExit(f"peru: {name} totals differ between religion tables: "
                                 f"{entry['TOTAL']:,.0f} vs {total:,.0f}")
            entry[label] = count
    for name, entry in out.items():
        summed = sum(v for k, v in entry.items() if k != "TOTAL")
        if abs(summed - entry["TOTAL"]) > 2:
            raise SystemExit(f"peru: {name} religions sum to {summed:,.0f} against "
                             f"{entry['TOTAL']:,.0f}")
    return out


def checked_whole(field: str, table: dict[str, dict[str, float]]) -> None:
    """Lima whole must be its two parts summed, then it is dropped."""
    whole = table.pop(WHOLE)
    parts = [table["Municipalidad Metropolitana de Lima"], table["Lima"]]
    for label, n in whole.items():
        if abs(sum(p[label] for p in parts) - n) > 2:
            raise SystemExit(f"peru: {field} {label}: Lima's parts sum to "
                             f"{sum(p[label] for p in parts):,.0f} against {n:,.0f}")


def build(text: str) -> list[dict[str, Any]]:
    fields = {"language": read_language(text), "religion": read_religion(text)}
    for field, table in fields.items():
        checked_whole(field, table)
    src = [{"field": "religion/language", "name": SOURCE, "url": URL, "license": LICENCE}]
    from common import slugify
    records = []
    for shape in sorted(set(DEPARTMENTS.values())):
        values: dict[str, Any] = {}
        for field, table in fields.items():
            entry = table[shape]
            total = entry["TOTAL"]
            values[field] = shares({k: v for k, v in entry.items() if k != "TOTAL" and v},
                                   total=total)
            values[f"{field}_year"] = YEAR
            values[f"{field}_note"] = f"{SOURCE}. {NOTES[field]}"
        records.append(record(f"PER-{slugify(shape)}", shape, level="admin1", parent="PER",
                              country="PER", aliases=ALIASES.get(shape, []), sources=src,
                              **values))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=None, help="a saved probe_pdf --layout --boxes dump")
    args = ap.parse_args()
    log(f"peru: {SOURCE}")
    text = (Path(args.text).read_text(encoding="utf-8") if args.text
            else laid_out(fetch_blob(URL), boxes=True))
    records = build(text)
    log(f"  {len(records)} departments")
    if len(records) != 26:
        raise SystemExit(f"peru: expected 26 shapes, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
