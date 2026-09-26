"""Bolivia's 2024 census: median age, sex ratio, nación o pueblo and mother tongue by province.

INE publishes the whole 2024 enumeration (the Censo de Población y Vivienda of
23 March 2024) as one database on its census portal, with a row for each
person counted. The map had no census figure below the country for Bolivia:
its provinces' language was CLEAR Global's tabulation of the 2012 IPUMS
sample, and median age and sex ratio were OCHA's 2022 projections for the
departments alone. This reads the database on the runner, counts people by
department and province, and writes the counts. The rows themselves are never
kept.

What it reads, in the words of INE's data dictionary (``--describe`` prints it
whole):

* P32, "Se autoidentifica con alguna nación pueblo indígena originario
  campesino o afroboliviano", put to everyone of every age, and grouped by INE
  into 58 nations and peoples (P32_PUEBLOS). Written as ethnicity. Those who
  answer no are the remainder, "Mestizo or white (neither indigenous nor
  Afro-descendant)" as for Chile and Argentina: the census asks nothing about
  mestizo or white identity, and the note says so. The unanswered are left out
  of the shares, and the note counts them.
* P34.1, the first language a person learned to speak in childhood, also put
  to everyone; children who do not yet speak are "No habla". Written as
  language, of those with a language stated.
* P25 and P26, sex and age in completed years (100 and over recorded as 100).
  Written as the sex ratio and the median age, interpolated within the middle
  year; INE's database gives the ages, not the median.

Labels are read from the dictionary in the archive, not typed here: a code
whose label this file does not know stops the run. The file is vouched for by
what it says: its rows by department must be INE's published count of each of
the nine, to the person (DEPARTMENTS), or nothing is written.

**Binding.** Provinces are bound to the map's polygons by shape id
(``binding.py``). The boundary file draws the Cercado provinces of Beni,
Cochabamba, Oruro and Tarija as one feature filed under Beni; a polygon that
reaches well beyond its own department is several places drawn as one, and no
province is bound to it. The Territorio Indígena Multiétnico, a Beni province
in INE's catalogue, has no polygon either. Their people are in their
departments' figures.

Usage:
    python -m scripts.fetch_census.bolivia_census --describe
    python -m scripts.fetch_census.bolivia_census
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import bind, fold

URL = "https://nimbus.ine.gob.bo/index.php/s/qEmK9gnkGCZ3K7D/download"
PAGE = "https://cpv2024.ine.gob.bo/index.php/principal/descargas/"
UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"
PERSON = "Persona_CPV-2024.csv"
DICTIONARY = "Diccionario de variables CPV 2024.xlsx"
QUESTIONNAIRE = "Cuestionario censal 2024.pdf"
SITE = PROCESSED.parent.parent / "site" / "data"
OUT = PROCESSED / "bolivia_census.json"
YEAR = 2024
SOURCE = "INE Bolivia, Censo de Población y Vivienda 2024, person database"

# INE's published 2024 count of each department, as Wikidata carries it (the
# nine sum to 11,365,333), read on 26 September 2026. The person file's rows
# matched all nine exactly on that day.
DEPARTMENTS = {1: 606_027, 2: 3_030_917, 3: 2_016_357, 4: 571_471, 5: 861_292,
               6: 534_210, 7: 3_122_605, 8: 488_260, 9: 134_194}

REST = "Mestizo or white (neither indigenous nor Afro-descendant)"
NO_PEOPLE = "Indigenous originario campesino (no people named)"
# INE's groups of P32 (P32_PUEBLOS), as its dictionary spells them, to the
# names this map uses: the peoples by their own names, as Argentina's and
# Chile's censuses print them.
PUEBLOS = {
    "Afroboliviano": "Afro-Bolivian", "Araona": "Araona", "Aymara": "Aymara",
    "Ayoreo": "Ayoreo", "Baure": "Baure", "Canichana": "Canichana", "Cavineño": "Cavineño",
    "Cayubaba": "Cayubaba", "Chácobo": "Chácobo", "Charka Qhara Qhara": "Charka Qhara Qhara",
    "Chichas": "Chichas", "Chiquitano": "Chiquitano", "Chuwi": "Chuwi", "Ese Ejja": "Ese Ejja",
    "Guaraní": "Guaraní", "Guarasu´we": "Guarasu'we", "Gwarayu": "Gwarayu",
    "Itonama": "Itonama", "Jach'a Carangas": "Jach'a Carangas", "Jalq'a": "Jalq'a",
    "Joaquiniano": "Joaquiniano", "Kallawaya": "Kallawaya", "Killacas": "Killacas",
    "Leco": "Leco", "Lípez": "Lípez", "Lupaca": "Lupaca", "Machineri": "Machineri",
    "Maropa": "Maropa", "Mojeño": "Mojeño", "Mojeño Ignaciano": "Mojeño Ignaciano",
    "Mojeño Trinitario": "Mojeño Trinitario", "Moré": "Moré", "Mosetén": "Mosetén",
    "Movima": "Movima", "Pacahuara": "Pacahuara", "Pakajaqi": "Pakajaqi",
    "Paunaca": "Paunaca", "Puquina": "Puquina", "Qhapaq Uma Suyu": "Qhapaq Uma Suyu",
    "Quechua": "Quechua", "Qullas": "Qullas", "Raqaypampa": "Raqaypampa",
    "Sirionó": "Sirionó", "Sora": "Sora", "Tacana": "Tacana", "Tapiete": "Tapiete",
    "Toromona": "Toromona", "Tsimane´": "Tsimane'", "Uru-Chipaya": "Uru-Chipaya",
    "Weenhayek": "Weenhayek", "Yaminawa": "Yaminawa", "Yampara": "Yampara",
    "Yuqui": "Yuqui", "Yurakaré": "Yurakaré",
    "Quechua - Aymara": "Quechua and Aymara",
    "Más de una descripción": "More than one nation or people",
    # Everyone who answered yes and named a term rather than a people --
    # Campesino, Originario, Indígena, Nación, an ayllu or marka -- or named
    # none: INE's dictionary lists them under P32_PUEBLO_COD's 900s and 999.
    "Otras declaraciones": NO_PEOPLE,
    "Otros pueblos indígenas extranjeros": "Indigenous peoples from abroad",
    "No se autoidentifica": REST,
}
UNANSWERED = "Sin respuesta"

OTHER_FOREIGN = "Other foreign language"
# INE's mother-tongue labels (IDIOMA_MAT) to the names this map uses: English
# names for the languages of other countries, Bolivia's own by the names its
# census prints.
LANGUAGES = {
    "Castellano": "Spanish", "Quechua": "Quechua", "Aymara": "Aymara", "Guaraní": "Guarani",
    "Araona": "Araona", "Baure": "Baure", "Bésiro": "Bésiro", "Canichana": "Canichana",
    "Kabineña": "Kabineña", "Cayubaba": "Cayubaba", "Chácobo": "Chácobo",
    "Tsimane´": "Tsimane'", "Ese Ejja": "Ese Ejja", "Guarasu´we": "Guarasu'we",
    "Gwarayu": "Gwarayu", "Itonama": "Itonama", "Leco": "Leco",
    "Macha´juyay Kallawaya": "Machaj-Juyai Kallawaya", "Machineri": "Machineri",
    "Maropa": "Maropa", "Mojeño Ignaciano": "Mojeño Ignaciano",
    "Mojeño Trinitario": "Mojeño Trinitario", "Moré": "Moré", "Mosetén": "Mosetén",
    "Movima": "Movima", "Pacahuara": "Pacahuara", "Puquina": "Puquina",
    "Sirionó": "Sirionó", "Tacana": "Tacana", "Tapiete": "Tapiete", "Toromona": "Toromona",
    "Uru-Chipaya": "Uru-Chipaya", "Weenhayek": "Weenhayek", "Yaminawa": "Yaminawa",
    "Yuqui": "Yuqui", "Yurakaré": "Yurakaré", "Zamuco": "Zamuco", "Joaquiniano": "Joaquiniano",
    "Qom (toba)": "Qom (Toba)", "Afroboliviano": "Afro-Bolivian Spanish",
    "Albanés": "Albanian", "Alemán": "German", "Árabe": "Arabic", "Búlgaro": "Bulgarian",
    "Catalán": "Catalan", "Chino": "Chinese", "Coreano": "Korean", "Croata": "Croatian",
    "Danés": "Danish", "Finlandés": "Finnish", "Francés": "French", "Holandés": "Dutch",
    "Húngaro": "Hungarian", "Inglés": "English", "Italiano": "Italian",
    "Japonés": "Japanese", "Noruego": "Norwegian", "Portugués": "Portuguese",
    "Rumano": "Romanian", "Ruso": "Russian", "Serbio": "Serbian", "Sueco": "Swedish",
    "Tailandés": "Thai", "Turco": "Turkish", "Ucraniano": "Ukrainian", "Vasco": "Basque",
    "Vietnamés": "Vietnamese", "Hebreo": "Hebrew", "Polaco": "Polish", "Checo": "Czech",
    "Griego": "Greek", "Persa": "Persian", "Latin": "Latin", "Taiwanés": "Taiwanese",
    "Gallego": "Galician", "Valenciano": "Valencian",
    # Labels naming a nationality or a continent, not one language, and
    # Quinamaya, which is no language this file can place.
    "Escocés": OTHER_FOREIGN, "Suizo": OTHER_FOREIGN, "Africano": OTHER_FOREIGN,
    "Quinamaya": "Other language", "Otras declaraciones": "Other language",
    "Otro idioma extranjero": OTHER_FOREIGN, "Lenguaje de señas": "Sign language",
}
NOT_SPEAKING = "No habla"

# INE's spelling of a province -> the boundary file's, where they differ by
# more than accents, case and spacing.
ALIASES = {"Sur Yungas": "Sud Yungas", "Sud Cinti": "Sur Cinti", "Avilez": "Avilés",
           "General Bernardino Bilbao": "General Bilbao"}
# How far, in degrees, a province's polygon may reach beyond its department's
# box before it is taken for several places drawn as one.
REACH = 0.5
COLUMNS = ("idep", "iprov", "p25_sexo", "p26_edad", "p32_pueblos", "idioma_mat")

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


def spoken(text: Any) -> str:
    """A dictionary cell as text, with its spacing evened out."""
    if isinstance(text, float) and text.is_integer():
        text = int(text)
    return re.sub(r"\s+", " ", str(text)).strip()


def read_labels(rows: Iterable[Iterable[Any]]) -> dict[str, dict[int, str]]:
    """Value labels by variable, from the PERSONA sheet of INE's dictionary.

    A variable's block reads "Etiqueta | ...", "Nombre | NAME | Alias ...",
    "Tipo | ...", "Categorías", then one "code | label" row a value.
    """
    labels: dict[str, dict[int, str]] = {}
    current = None
    for row in rows:
        cells = [spoken(c) for c in row if c not in (None, "")]
        if not cells:
            continue
        if cells[0] == "Nombre" and len(cells) > 1:
            current = cells[1].upper()
            labels[current] = {}
        elif cells[0] == "Etiqueta":
            current = None
        elif current and len(cells) == 2 and cells[0].isdigit():
            labels[current][int(cells[0])] = cells[1]
    return labels


def translate(codes: dict[int, str], names: dict[str, str], question: str,
              known: Iterable[str] = ()) -> dict[int, str]:
    """INE's codes to this map's names, refusing any label this file does not know."""
    unknown = sorted(set(codes.values()) - set(names) - set(known))
    if unknown:
        raise SystemExit(f"bolivia_census: {question}: INE's dictionary has labels this "
                         f"file does not know: {unknown}")
    return {code: names[label] for code, label in codes.items() if label in names}


def code_of(labels: dict[int, str], label: str, question: str) -> int:
    hits = [c for c, text in labels.items() if text.lower() == label.lower()]
    if len(hits) != 1:
        raise SystemExit(f"bolivia_census: {question}: INE's dictionary labels it "
                         f"{labels}, with no single {label!r}")
    return hits[0]


def count(rows: Iterable[list[str]], header: list[str]) -> dict[int, dict[str, Counter]]:
    """People by province (department * 100 + province): sex, age, P32 group, mother tongue."""
    at = {name.strip().lower(): i for i, name in enumerate(header)}
    dep, prov, sex, age, pueblo, idioma = (at[c] for c in COLUMNS)
    out: dict[int, dict[str, Counter]] = {}
    for row in rows:
        code = int(row[dep]) * 100 + int(row[prov])
        unit = out.get(code)
        if unit is None:
            unit = out[code] = {"sex": Counter(), "ages": Counter(), "pueblo": Counter(),
                                "idioma": Counter()}
        unit["sex"][row[sex].strip()] += 1
        unit["ages"][row[age].strip()] += 1
        unit["pueblo"][row[pueblo].strip()] += 1
        unit["idioma"][row[idioma].strip()] += 1
    return out


def median_age(ages: Counter) -> float | None:
    """The age half the people are younger than, interpolated within its year."""
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


def merged(shapes: list[dict[str, Any]], departments: list[dict[str, Any]]
           ) -> list[dict[str, Any]]:
    """Polygons reaching well beyond their own department: several places drawn as one."""
    boxes = {d["id"]: d["bbox"] for d in departments}
    out = []
    for shape in shapes:
        box, own = boxes.get(shape["parent"]), shape["bbox"]
        if box and (own[0] < box[0] - REACH or own[1] < box[1] - REACH
                    or own[2] > box[2] + REACH or own[3] > box[3] + REACH):
            out.append(shape)
    return out


def fields(unit: dict[str, Counter], sexes: tuple[str, str], pueblos: dict[int, str],
           idiomas: dict[int, str], not_speaking: int) -> dict[str, Any]:
    """The written fields for one department or province."""
    people = sum(unit["sex"].values())
    women, men = unit["sex"][sexes[0]], unit["sex"][sexes[1]]
    ages = Counter({int(a): n for a, n in unit["ages"].items()})
    eth: Counter = Counter()
    unanswered = 0
    for value, n in unit["pueblo"].items():
        if value and int(value) in pueblos:
            eth[pueblos[int(value)]] += n
        else:
            unanswered += n
    lang: Counter = Counter()
    silent = unstated = 0
    for value, n in unit["idioma"].items():
        if not value:
            unstated += n
        elif int(value) == not_speaking:
            silent += n
        else:
            lang[idiomas[int(value)]] += n
    answered, stated = sum(eth.values()), sum(lang.values())
    return {
        "population": measure(people, year=YEAR, source=SOURCE),
        "median_age": measure(median_age(ages), unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "the ages of everyone INE's 2024 person database counts here (100 and over "
            "recorded as 100); INE publishes the ages, not the median."),
        "sex_ratio": (measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE) if women else None),
        "ethnicity": shares(eth),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Question 32 of the 2024 census, put to everyone of every age: whether a person "
            "identifies with a nación o pueblo indígena originario campesino or as "
            "Afro-Bolivian, and if so which, grouped as INE groups the answers. Those who "
            "answered no are the remainder: the census asks nothing about mestizo or white "
            f"identity. \"{NO_PEOPLE}\" is everyone who answered yes with a term "
            "(campesino, originario, indígena, an ayllu or marka) or no people named. "
            + (f"Counted from INE's person database: all {people:,} people here."
               if not unanswered else
               f"Counted from INE's person database: the {answered:,} of {people:,} people "
               f"here who answered; {unanswered:,} did not.")),
        "language": shares(lang),
        "language_year": YEAR,
        "language_note": (
            "The first language each person learned to speak in childhood (question 34, put "
            f"to everyone), of the {stated:,} of {people:,} people here with one stated; "
            f"{silent:,} children who do not yet speak and {unstated:,} people whose answer "
            "was not specified are left out. Counted from INE's 2024 person database."),
        "sources": [{"field": "population/median age/sex ratio/ethnicity/language",
                     "name": SOURCE, "url": PAGE, "year": YEAR}],
    }


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
            import openpyxl
            book = openpyxl.load_workbook(io.BytesIO(archive.read(member(archive, DICTIONARY))),
                                          read_only=True)
            sheet = next(s for s in book.worksheets if s.title.strip().upper() == "PERSONA")
            labels = read_labels(sheet.iter_rows(values_only=True))
            pueblos = translate(labels["P32_PUEBLOS"], PUEBLOS, "P32_PUEBLOS", [UNANSWERED])
            idiomas = translate(labels["IDIOMA_MAT"], LANGUAGES, "IDIOMA_MAT", [NOT_SPEAKING])
            not_speaking = code_of(labels["IDIOMA_MAT"], NOT_SPEAKING, "IDIOMA_MAT")
            sexes = (str(code_of(labels["P25_SEXO"], "Mujer", "P25_SEXO")),
                     str(code_of(labels["P25_SEXO"], "Hombre", "P25_SEXO")))
            dept_names = labels["DEP_NAC_COD"]
            prov_names = labels["PROV_NAC_COD"]
            log(f"  dictionary: {len(pueblos)} groups of P32, {len(idiomas)} languages, "
                f"{len(prov_names)} province entries")
            with archive.open(member(archive, PERSON)) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                reader = csv.reader(text, delimiter=";")
                header = next(reader)
                counts = count(reader, header)

    # -- every value labelled, every department INE's published count
    by_dept: dict[int, dict[str, Counter]] = {}
    for code, unit in counts.items():
        if code not in prov_names:
            raise SystemExit(f"bolivia_census: province {code} has rows and no name in "
                             "INE's catalogue")
        for key, seen, known in (("P25_SEXO", unit["sex"], set(sexes)),
                                 ("P32_PUEBLOS", unit["pueblo"],
                                  {str(c) for c in labels["P32_PUEBLOS"]} | {""}),
                                 ("IDIOMA_MAT", unit["idioma"],
                                  {str(c) for c in labels["IDIOMA_MAT"]} | {""})):
            if set(seen) - known:
                raise SystemExit(f"bolivia_census: {key}: province {code} has values INE's "
                                 f"dictionary does not label: {sorted(set(seen) - known)}")
        if not all(a.isdigit() for a in unit["ages"]):
            raise SystemExit(f"bolivia_census: province {code} has an age that is not a number")
        whole = by_dept.setdefault(code // 100, {k: Counter() for k in unit})
        for k, v in unit.items():
            whole[k].update(v)
    wrong = {d: (sum(u["sex"].values()), DEPARTMENTS.get(d)) for d, u in by_dept.items()
             if sum(u["sex"].values()) != DEPARTMENTS.get(d)}
    if wrong or set(by_dept) != set(DEPARTMENTS):
        raise SystemExit("bolivia_census: the person file does not reproduce INE's published "
                         f"department counts (counted, published): {wrong or sorted(by_dept)}")
    people = sum(DEPARTMENTS.values())
    log(f"  {people:,} people in {len(counts)} provinces and {len(by_dept)} departments, "
        "each department INE's published count")

    # -- binding
    admin1 = json.loads((SITE / "admin1" / "BOL.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "BOL.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    admin1_ids = {fold(u["name"]): u["id"] for u in admin1}
    several = merged(admin2, admin1)
    for shape in several:
        log(f"  polygon {shape['name']!r} (filed under {parents.get(shape['parent'])}) reaches "
            f"{shape['bbox']}, well beyond its department: several places drawn as one, and "
            "no province is bound to it")
    drawn = [s for s in admin2 if s not in several]
    bound, missing = bind({str(c): (prov_names[c], dept_names[c // 100]) for c in counts},
                          drawn, parents, ALIASES)
    log(f"  {len(bound)} provinces bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    labels_of = {s["id"]: s["name"] for s in drawn}
    unbound = sorted(s["name"] for s in drawn if s["id"] not in set(bound.values()))
    log(f"  polygons with no province: {unbound}")
    for c, sid in bound.items():
        was = next((s.get("population") or {}).get("value") for s in drawn if s["id"] == sid)
        now = sum(counts[int(c)]["sex"].values())
        if was and was != now:
            log(f"  check: {prov_names[int(c)]} ({c}) has {now:,} people; the polygon "
                f"{labels_of[sid]!r} carried {was:,}")

    records = []
    for d, unit in sorted(by_dept.items()):
        name = dept_names[d]
        shape = admin1_ids.get(fold(name))
        if shape is None:
            raise SystemExit(f"bolivia_census: department {name} has no polygon")
        records.append(record(f"BOL-INE-{d:02d}", name, level="admin1", parent="BOL",
                              country="BOL", codes={"ine": f"{d:02d}"}, match_by="shape_id",
                              shape_id=shape, **fields(unit, sexes, pueblos, idiomas,
                                                       not_speaking)))
    for c in sorted(counts):
        sid = bound.get(str(c))
        if sid is None:
            continue
        name, label = prov_names[c], labels_of[sid]
        records.append(record(f"BOL-INE-{c}", name, level="admin2", parent="BOL",
                              country="BOL", parent_name=dept_names[c // 100],
                              codes={"ine": str(c)}, match_by="shape_id", shape_id=sid,
                              aliases=[label] if label != name else [],
                              **fields(counts[c], sexes, pueblos, idiomas, not_speaking)))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
