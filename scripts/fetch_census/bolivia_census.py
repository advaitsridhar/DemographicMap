"""Bolivia's 2024 census: median age, sex ratio, nación o pueblo and mother tongue by province.

INE publishes the whole 2024 enumeration (the Censo de Población y Vivienda of
23 March 2024) as one database on its census portal, with a row for each
person counted. The map had no census figure below the country for Bolivia:
its provinces' language was CLEAR Global's tabulation of the 2012 IPUMS
sample, and median age and sex ratio were OCHA's 2022 projections for the
departments alone. This reads the database on the runner, counts people by
province, and writes the counts. The rows themselves are never kept.

Usage:
    python -m scripts.fetch_census.bolivia_census --describe
    python -m scripts.fetch_census.bolivia_census
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sys
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

from ._shared import log

URL = "https://nimbus.ine.gob.bo/index.php/s/qEmK9gnkGCZ3K7D/download"
PAGE = "https://cpv2024.ine.gob.bo/index.php/principal/descargas/"
UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"
PERSON = "Persona_CPV-2024.csv"
DICTIONARY = "Diccionario de variables CPV 2024.xlsx"
QUESTIONNAIRE = "Cuestionario censal 2024.pdf"

# The columns --describe counts the values of, and who answered each.
DESCRIBE = ["idep", "p25_sexo", "p32_pueblo_per", "p32_pueblo_cod", "p32_pueblos",
            "p341_idiomat_cod", "p342_idiomat_no", "idioma_mat", "p331_idiohab1_cod",
            "p334_idiohab_no", "idioma_mayor_uso", "p353_paisnac_cod", "p35_lugnac"]


def download(dest: Path) -> None:
    """The database, streamed to disk, with its size and SHA-256 logged."""
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    digest = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=900) as resp, open(dest, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
    log(f"  {URL}: {dest.stat().st_size:,} bytes, sha256 {digest.hexdigest().upper()}")


def member(archive: zipfile.ZipFile, suffix: str) -> zipfile.ZipInfo:
    return next(i for i in archive.infolist() if i.filename.endswith(suffix))


def describe(archive: zipfile.ZipFile) -> None:
    """The archive's members, INE's dictionary, the questionnaire's wording, and the values."""
    for info in archive.infolist():
        log(f"  {info.filename}: {info.file_size:,} bytes")
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(archive.read(member(archive, DICTIONARY))),
                                  read_only=True)
    for sheet in book.worksheets:
        log(f"-- {DICTIONARY} / {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [re.sub(r"\s+", " ", str(c)).strip() for c in row if c not in (None, "")]
            if cells:
                log("   " + " | ".join(cells))
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(archive.read(member(archive, QUESTIONNAIRE))))
        log(f"-- {QUESTIONNAIRE}: {len(reader.pages)} pages")
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            log(f"   page {number}: {len(text):,} characters of text")
            if re.search(r"religi|pueblo|idioma|naci[oó]n|afro", text, re.I):
                log(re.sub(r"[ \t]+", " ", text)[:4000])
    except Exception as exc:  # the wording is a help, not a requirement
        log(f"-- {QUESTIONNAIRE}: not read ({exc})")

    info = member(archive, PERSON)
    values: dict[str, Counter] = {c: Counter() for c in DESCRIBE}
    # Who each question was put to: answers and blanks by single year of age.
    answered: dict[str, Counter] = {c: Counter() for c in DESCRIBE}
    blank: dict[str, Counter] = {c: Counter() for c in DESCRIBE}
    provinces: Counter = Counter()
    municipios: set[tuple[str, str, str]] = set()
    ages: Counter = Counter()
    with archive.open(info) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        first = text.readline()
        delimiter = max(",;|\t", key=first.count)
        header = next(csv.reader([first], delimiter=delimiter))
        log(f"-- {PERSON}: delimiter {delimiter!r}, {len(header)} columns")
        at = {name: i for i, name in enumerate(header)}
        rows = 0
        for row in csv.reader(text, delimiter=delimiter):
            rows += 1
            age = row[at["p26_edad"]].strip()
            ages[age if not age.isdigit() else min(int(age), 120)] += 1
            key = min(int(age), 20) if age.isdigit() else age
            provinces[(row[at["idep"]], row[at["iprov"]])] += 1
            municipios.add((row[at["idep"]], row[at["iprov"]], row[at["imun"]]))
            for column in DESCRIBE:
                value = row[at[column]].strip()
                if len(values[column]) < 400 or value in values[column]:
                    values[column][value] += 1
                (answered if value else blank)[column][key] += 1
    log(f"   {rows:,} rows, {len(provinces)} provinces, {len(municipios)} municipios")
    by_dept: Counter = Counter()
    for (dept, _), n in provinces.items():
        by_dept[dept] += n
    log("   by department: " + ", ".join(f"{d}={n:,}" for d, n in sorted(by_dept.items())))
    log("   by province: " + ", ".join(f"{d}{p}={n:,}" for (d, p), n in sorted(provinces.items())))
    odd = {a: n for a, n in ages.items() if not isinstance(a, int)}
    log(f"   ages: {min(a for a in ages if isinstance(a, int))} to "
        f"{max(a for a in ages if isinstance(a, int))}; not a number: {odd}")
    for column in DESCRIBE:
        log(f"   {column}: {len(values[column])} values: {sorted(values[column].items())}")
        log(f"     answered by age (20 = 20+): {sorted(answered[column].items(), key=str)}")
        log(f"     blank by age (20 = 20+): {sorted(blank[column].items(), key=str)}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "cpv2024.zip"
        download(dest)
        with zipfile.ZipFile(dest) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise SystemExit(f"bolivia_census: the archive is damaged at {bad}")
            log("  CRC check: every member intact")
            if "--describe" in sys.argv:
                describe(archive)
                return 0
    raise SystemExit("bolivia_census: only --describe is written so far")


if __name__ == "__main__":
    raise SystemExit(main())
