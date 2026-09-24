"""Guatemala's 2018 census: pueblo and mother tongue by department and municipio.

INE publishes the whole 2018 enumeration as one database -- a row for each of
the 14,901,286 people counted -- on its census portal. Nothing else carries
these two questions below the country: the map's language was a 2002 sample
tabulated by CLEAR Global, and ethnicity was empty. This reads the database in
the runner, counts people by municipio, and writes the counts; the rows
themselves are never kept.

The two questions, in the words of INE's own data dictionary:

* PCP12, "Segun su origen o historia, como se considera o auto identifica?" --
  Maya, Garifuna, Xinka, Afrodescendiente/Creole/Afromestizo, Ladina(o),
  Extranjera(o). Written as ethnicity.
* PCP15, "Cual es el idioma en el que aprendio a hablar?" -- the language a
  person learned to speak in: 22 Mayan languages, Xinka, Garifuna, Spanish,
  English, sign language, another language, or none. Written as language.

Labels are read from the dictionary in the archive, not typed here: a code
whose label is not one this file knows stops the run.

The file cannot be vouched for by hash. The portal prints 399 MB and SHA-256
C0F23CED... beside the link, and on 24 September 2026 it served 322,771,575
bytes hashing 82C57488... Inside, INE's own list of hashes matches only the
migration file: the household and dwelling files are the listed sizes with
other hashes, and the person file is listed as PERSONA_BDP.csv at
3,510,737,511 bytes and ships as "PERSONA - BDP.csv" at 3,181,672,941 --
re-exported, it seems, after the list was written. So it is vouched for by
what it says instead. Its 14,901,286 rows are INE's published national count,
and its rows by department are INE's published count of all 22 departments,
to the person; DEPARTMENTS below holds those, and a run that disagrees with
any of them writes nothing. The archive's CRCs are tested before a row is read.

Usage:
    python -m scripts.fetch_census.guatemala_census --probe
    python -m scripts.fetch_census.guatemala_census --check
    python -m scripts.fetch_census.guatemala_census
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
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json

URL = "https://censo2018.ine.gob.gt/archivos/bdd/db_csv_.zip"
PAGE = "https://censo2018.ine.gob.gt/"
SHA256 = "C0F23CED957F7BC126A5A689B728BE143D8B57B74F96CDF31869B28B01B820F9"
UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"
OUT = PROCESSED / "guatemala_census.json"
YEAR = 2018
SOURCE = ("INE Guatemala, XII Censo Nacional de Poblacion y VII de Vivienda "
          "2018, person database")

# INE's published 2018 count of each department, as the table in Wikipedia's
# "Departments of Guatemala" carries it (citing INE's Resultados Censo 2018,
# p. 85), read on 24 September 2026. Nineteen of them are also Wikidata's
# 2018 figures. The person file's rows matched all 22 exactly on that day.
DEPARTMENTS = {
    1: 3_015_081, 2: 176_632, 3: 330_469, 4: 615_776, 5: 733_181,
    6: 396_607, 7: 421_583, 8: 418_569, 9: 799_101, 10: 554_695,
    11: 326_828, 12: 1_032_277, 13: 1_170_669, 14: 949_261, 15: 299_476,
    16: 1_215_038, 17: 545_600, 18: 408_688, 19: 245_374, 20: 415_063,
    21: 342_923, 22: 488_395,
}

# INE's labels, as its dictionary spells them, to the names this map uses.
# Where a name is already on the map for Guatemala -- CLEAR Global's spellings
# of the Mayan languages, the Factbook's Afro-descendant category -- it is
# that one, so a group reads the same at every level.
PUEBLO = {
    "Maya": "Maya", "Garífuna": "Garifuna", "Xinka": "Xinka",
    "Afrodescendiente/Creole/Afromestizo": "Afro-descendant/Creole/Afro-mestizo",
    "Ladina (o)": "Ladino", "Extranjera (o)": "Foreigner",
}
IDIOMA = {
    "Achí": "Achi", "Akateko": "Akateko", "Awakateko": "Awakateko",
    "Ch'orti'": "Ch'orti'", "Chalchiteko": "Chalchiteko", "Chuj": "Chuj",
    "Itza'": "Itza'", "Ixil": "Ixil", "Jakalteko/Popti'": "Popti'",
    "K'iche'": "K'iche'", "Kaqchiquel": "Kaqchikel", "Mam": "Mam",
    "Mopan": "Mopan", "Poqomam": "Poqomam", "Poqomchi'": "Poqomchi'",
    "Q'anjob'al": "Q'anjob'al", "Q'eqchi'": "Q'eqchi'",
    "Sakapulteko": "Sakapulteko", "Sipakapense": "Sipakapense",
    "Tektiteko": "Tektiteko", "Tz'utujil": "Tz'utujil",
    "Uspanteko": "Uspanteko", "Xinka": "Xinka", "Garífuna": "Garifuna",
    "Español": "Spanish", "Inglés": "English", "Señas": "Sign language",
    "Otro idioma": "Other language", "No habla": "Does not speak",
}


def download(dest: Path) -> str:
    """The database, streamed to disk; its SHA-256, logged beside the published one.

    The portal's button submits a form by POST; a GET is tried first, as the
    plainer request, and the form's own method only if the server wants it.
    """
    for method in ("GET", "POST"):
        req = urllib.request.Request(URL, method=method, headers={"User-Agent": UA},
                                     data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
                digest = hashlib.sha256()
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
        except urllib.error.HTTPError as exc:
            log(f"  {method} {URL}: HTTP {exc.code}")
            continue
        got = digest.hexdigest().upper()
        log(f"  {method} {URL}: {dest.stat().st_size:,} bytes, sha256 {got}")
        if got != SHA256:
            log(f"  the portal prints {SHA256} beside the link: not this file")
        return got
    raise SystemExit("the database could not be downloaded")


def probe(archive: zipfile.ZipFile) -> None:
    """What the archive holds: its files, each CSV's header and rows, and the codebook."""
    for info in archive.infolist():
        log(f"  {info.filename}: {info.file_size:,} bytes")
    bad = archive.testzip()
    log(f"  CRC check: {'every member intact' if bad is None else 'damaged at ' + bad}")
    for info in archive.infolist():
        name = info.filename.lower()
        if name.endswith((".txt", ".md")) and info.file_size < 200_000:
            log(f"-- {info.filename}")
            log(archive.read(info).decode("utf-8", "replace")[:6000])
        if not name.endswith(".csv"):
            continue
        with archive.open(info) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            first = text.readline()
            delimiter = max(",;|\t", key=first.count)
            header = next(csv.reader([first], delimiter=delimiter))
            reader = csv.reader(text, delimiter=delimiter)
            log(f"-- {info.filename}: {len(header)} columns")
            log("   " + " | ".join(header))
            counts: dict[str, Counter] = {h: Counter() for h in header}
            rows = 0
            for rows, row in enumerate(reader, 1):
                if rows > 200_000:
                    continue
                for h, v in zip(header, row):
                    if len(counts[h]) < 60:
                        counts[h][v] += 1
            log(f"   {rows:,} rows")
            for h in header:
                top = counts[h].most_common(12)
                log(f"   {h}: {len(counts[h])} values in the first 200,000 rows; {top}")


def verify(archive: zipfile.ZipFile) -> None:
    """Each CSV against the SHA-256 list INE ships inside the archive."""
    listing = next(i for i in archive.infolist() if i.filename.endswith("SHA256.txt"))
    text = archive.read(listing).decode("utf-8", "replace")
    listed = dict(re.findall(r"Name:\s*(\S+)\s+Size:[^\n]*\n\s*SHA256:\s*([0-9A-F]{64})", text))
    for info in archive.infolist():
        if not info.filename.lower().endswith(".csv"):
            continue
        digest = hashlib.sha256()
        with archive.open(info) as raw:
            while chunk := raw.read(1 << 20):
                digest.update(chunk)
        got = digest.hexdigest().upper()
        base = info.filename.rsplit("/", 1)[-1]
        want = listed.get(base) or listed.get(base.replace(" - ", "_"))
        log(f"  {base}: {info.file_size:,} bytes, sha256 {got}; INE lists "
            f"{want or 'no hash'}{' -- matches' if want == got else ''}")


def dictionary(archive: zipfile.ZipFile, name: str) -> None:
    """Every row of one of INE's data dictionaries, as text."""
    import openpyxl
    info = next(i for i in archive.infolist() if i.filename.endswith(name))
    book = openpyxl.load_workbook(io.BytesIO(archive.read(info)), read_only=True)
    for sheet in book.worksheets:
        log(f"-- {name} / {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c not in (None, "")]
            if cells:
                log("   " + " | ".join(cells))


def totals(archive: zipfile.ZipFile) -> None:
    """People by department: person rows, and the households' own head counts."""
    for suffix, column in (("PERSONA - BDP.csv", None), ("HOGAR_BDP.csv", "TOTAL_PERS")):
        info = next(i for i in archive.infolist() if i.filename.endswith(suffix))
        by_dept: Counter = Counter()
        with archive.open(info) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            for row in reader:
                by_dept[int(row["DEPARTAMENTO"])] += int(row[column]) if column else 1
        log(f"  {suffix}: {sum(by_dept.values()):,} people; by department "
            + ", ".join(f"{d}={n:,}" for d, n in sorted(by_dept.items())))


def spoken(text: Any) -> str:
    """A dictionary cell as text, with its spacing evened out."""
    return re.sub(r"\s+", " ", str(text)).strip()


def read_dictionary(book: Any) -> tuple[dict[str, dict[int, str]],
                                        dict[int, tuple[str, int, str]]]:
    """Value labels by variable, and the municipio catalogue, from INE's workbook.

    The labels follow a row reading "Etiqueta de los valores": a variable's
    first value carries its name, and the rest leave that cell empty. The
    catalogue is its own sheet, one municipio a row.
    """
    labels: dict[str, dict[int, str]] = {}
    municipios: dict[int, tuple[str, int, str]] = {}
    for sheet in book.worksheets:
        rows = [[c for c in row if c not in (None, "")]
                for row in sheet.iter_rows(values_only=True)]
        rows = [r for r in rows if r]
        if sheet.title.lower().startswith("cat"):
            for cells in rows:
                if len(cells) < 4 or not spoken(cells[0]).isdigit():
                    continue                              # the header, or a note
                code, name, dept_name, dept = cells[0], cells[1], cells[2], cells[3]
                municipios[int(code)] = (spoken(name), int(dept), spoken(dept_name))
            continue
        current = None
        reading = False
        for cells in rows:
            if spoken(cells[0]).startswith("Etiqueta de los valores"):
                reading = True
                continue
            if not reading or spoken(cells[0]) == "Nombre":
                continue
            if len(cells) >= 3:
                current = spoken(cells[0])
                cells = cells[1:]
            if current is None or len(cells) < 2:
                continue
            try:
                code = int(float(str(cells[0])))
            except ValueError:
                continue
            labels.setdefault(current, {})[code] = spoken(cells[1])
    return labels, municipios


def translate(codes: dict[int, str], names: dict[str, str], question: str) -> dict[int, str]:
    """INE's codes to this map's names, refusing any label it does not know."""
    unknown = sorted(set(codes.values()) - set(names))
    if unknown:
        raise SystemExit(f"{question}: INE's dictionary has labels this file does "
                         f"not know: {unknown}")
    return {code: names[label] for code, label in codes.items()}


def count(rows: Iterable[list[str]], header: list[str]) -> dict[int, dict[str, Any]]:
    """People by municipio: in all, by pueblo, by first language, and who went unasked."""
    at = {name.lstrip("\ufeff"): i for i, name in enumerate(header)}
    muni, age, pueblo, idioma = at["MUNICIPIO"], at["PCP7"], at["PCP12"], at["PCP15"]
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        code = int(row[muni])
        unit = out.get(code)
        if unit is None:
            unit = out[code] = {"people": 0, "pueblo": Counter(), "idioma": Counter(),
                                "unasked": 0, "unasked_under_4": 0, "answered_under_4": 0}
        unit["people"] += 1
        young = row[age].strip().isdigit() and int(row[age]) < 4
        if row[pueblo].strip():
            unit["pueblo"][int(row[pueblo])] += 1
        if row[idioma].strip():
            unit["idioma"][int(row[idioma])] += 1
            unit["answered_under_4"] += young
        else:
            unit["unasked"] += 1
            unit["unasked_under_4"] += young
    return out


def build(counts: dict[int, dict[str, Any]], municipios: dict[int, tuple[str, int, str]],
          pueblos: dict[int, str], idiomas: dict[int, str]) -> list[dict[str, Any]]:
    """Records for the 22 departments and every municipio, after the totals are checked."""
    by_dept: Counter = Counter()
    for code, unit in counts.items():
        if code not in municipios:
            raise SystemExit(f"municipio {code} has rows and no entry in INE's catalogue")
        by_dept[municipios[code][1]] += unit["people"]
        for question, seen, known in (("PCP12", unit["pueblo"], pueblos),
                                      ("PCP15", unit["idioma"], idiomas)):
            if set(seen) - set(known):
                raise SystemExit(f"{question}: municipio {code} has codes INE's "
                                 f"dictionary does not label: {sorted(set(seen) - set(known))}")
    wrong = {d: (by_dept.get(d, 0), n) for d, n in DEPARTMENTS.items() if by_dept.get(d, 0) != n}
    if wrong or set(by_dept) != set(DEPARTMENTS):
        raise SystemExit("the person file does not reproduce INE's published department "
                         f"counts (counted, published): {wrong or sorted(by_dept)}")

    # Measured, not assumed: who PCP15 was put to. Where every blank is a
    # child under four and nobody under four answered, the question's
    # universe is people aged four and over, and the note says so.
    unasked = sum(u["unasked"] for u in counts.values())
    under = sum(u["unasked_under_4"] for u in counts.values())
    young_answers = sum(u["answered_under_4"] for u in counts.values())
    log(f"  PCP15 blank for {unasked:,} people, {under:,} of them under four; "
        f"{young_answers:,} under four answered it")
    four_plus = unasked == under and young_answers == 0

    def rows_for(unit: dict[str, Any]) -> dict[str, Any]:
        eth = Counter({pueblos[c]: n for c, n in unit["pueblo"].items()})
        lang: Counter = Counter()
        for c, n in unit["idioma"].items():
            lang[idiomas[c]] += n
        asked = sum(lang.values())
        people = unit["people"]
        return {
            "ethnicity": shares(eth),
            "ethnicity_year": YEAR,
            "ethnicity_note": (
                "Pueblo de pertenencia, the census's own question: \"Segun su "
                "origen o historia, como se considera o auto identifica?\" "
                "Counted from INE's 2018 person database: "
                + (f"all {people:,} people enumerated here."
                   if sum(eth.values()) == people else
                   f"the {sum(eth.values()):,} of the {people:,} people enumerated "
                   "here who answered it.")),
            "language": shares(lang),
            "language_year": YEAR,
            "language_note": (
                "The language each person learned to speak in -- the census asked "
                "\"Cual es el idioma en el que aprendio a hablar?\" -- "
                + (f"of the {asked:,} people aged four and over enumerated here, "
                   "the only people it was put to"
                   if four_plus else
                   f"of the {asked:,} of {people:,} people enumerated here who "
                   "answered it")
                + ". Counted from INE's 2018 person database."),
            "sources": [{"field": "ethnicity/language", "name": SOURCE, "url": PAGE}],
        }

    out: list[dict[str, Any]] = []
    departments: dict[int, dict[str, Any]] = {}
    for code in sorted(counts):
        name, dept, dept_name = municipios[code]
        unit = counts[code]
        out.append(record(f"GTM-INE-{code}", name, level="admin2",
                          parent=f"GTM-INE-D{dept}", country="GTM",
                          parent_name=dept_name, **rows_for(unit)))
        whole = departments.setdefault(dept, {
            "name": dept_name, "people": 0, "pueblo": Counter(), "idioma": Counter()})
        whole["people"] += unit["people"]
        whole["pueblo"].update(unit["pueblo"])
        whole["idioma"].update(unit["idioma"])
    for dept, whole in sorted(departments.items()):
        out.append(record(f"GTM-INE-D{dept}", whole["name"], level="admin1",
                          parent="GTM", country="GTM", **rows_for(whole)))
    return out


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "db_csv_.zip"
        download(dest)
        with zipfile.ZipFile(dest) as archive:
            if "--probe" in sys.argv:
                probe(archive)
                return
            if "--check" in sys.argv:
                verify(archive)
                dictionary(archive, "Diccionario_Base_PERSONA.xlsx")
                totals(archive)
                return
            bad = archive.testzip()
            if bad is not None:
                raise SystemExit(f"the archive is damaged at {bad}")
            import openpyxl
            info = next(i for i in archive.infolist()
                        if i.filename.endswith("Diccionario_Base_PERSONA.xlsx"))
            book = openpyxl.load_workbook(io.BytesIO(archive.read(info)), read_only=True)
            labels, municipios = read_dictionary(book)
            pueblos = translate(labels["PCP12"], PUEBLO, "PCP12")
            idiomas = translate(labels["PCP15"], IDIOMA, "PCP15")
            log(f"  dictionary: {len(municipios)} municipios, {len(pueblos)} pueblos, "
                f"{len(idiomas)} languages")
            info = next(i for i in archive.infolist() if i.filename.endswith("PERSONA - BDP.csv"))
            with archive.open(info) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
                header = next(reader)
                counts = count(reader, header)
    rows = build(counts, municipios, pueblos, idiomas)
    people = sum(u["people"] for u in counts.values())
    log(f"  {people:,} people in {len(counts)} municipios and {len(DEPARTMENTS)} departments")
    write_json(OUT, rows)
    log(f"  wrote {OUT.name}: {len(rows)} records")


if __name__ == "__main__":
    main()
