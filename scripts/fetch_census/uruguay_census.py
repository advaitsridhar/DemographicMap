#!/usr/bin/env python3
"""Uruguay's 2023 census by department and municipio, from INE's microdata.

INE publishes the Censo de Población, Hogares y Viviendas 2023 as person-level
microdata. Those files are read on the runner and only the totals below are
written; no person's row leaves it.

What it writes, for the 19 departments and the municipios the boundary file
draws (and the ground outside them, drawn as one unit per department):

* **Population, median age and sex ratio**: everyone INE estimates the
  census counted -- 3,499,451 -- from the weighted person file of INE's July
  2026 release (ANDA catalogue 781), the release INE's own tables now use.
  The median is interpolated within the single year of age holding the
  middle person.
* **Ethnicity**: each person's principal ethnic-racial ancestry. The census
  asked everyone who answered its questionnaire whether they believe they
  have Afro or Black, Asian, White, Indigenous or other ancestry (yes or no
  to each), and those who said yes to more than one which is the principal.
  Those with one are counted with it, those who named several and no
  principal as "Mixed (several, no principal)", those who said no to all
  five as "None of these ancestries". People counted from administrative
  records or on the short questionnaire were not asked, and are left out;
  the note says how many.
* **Religion and language**: not asked. The 2023 questionnaire's only
  "religioso" is a kind of collective dwelling (Internado religioso), and it
  has no language question.

**Which municipios.** The boundary file draws the municipios of the 2020
electoral series (124 of its 125: Ismael Cortinas, Flores's one municipio,
is not drawn). INE's July 2026 release files each person under the 2025
series instead -- 136 municipios, eleven of them new and "the limits of
others revised" (INE's microdata guide, section 8.6) -- which the map does
not draw. INE's February 2026 release filed the same people under the 2020
series. So each person of the July file is placed in the municipio the
February file gives their dwelling's address (DIRECCION_ID; the two files
number their people differently). About a quarter of July's address codes
are not in the February file; those people are placed by their census
segment, in the municipio where the segment's other people all are. The
municipios are tallied with the July weights. Every placement is checked:
every address both files have must be in the same department in both, no
more than 1% of the people may go unplaced, every
2020 municipio must bind to one polygon of its own department, and the July
file tallied by its own 2025 series must make INE's Cuadro 14 municipio by
municipio, as its departments must make Cuadro 1.

Usage:
    python -m scripts.fetch_census.uruguay_census
    python -m scripts.fetch_census.uruguay_census --probe microdata --catalog 781
    python -m scripts.fetch_census.uruguay_census --probe columns --catalog 781 --file 1503 \\
        --count MUNICIPIO_136,DEPARTAMENTO --weight W
    python -m scripts.fetch_census.uruguay_census --probe ddi --catalog 781 --vars PERER02
"""

from __future__ import annotations

import argparse
import csv
import html
import http.cookiejar
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from ._shared import PROCESSED, gap, log, measure, record, shares, write_json
from .binding import bind, fold
from .redatam import median_age

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_tls import completed_context  # noqa: E402

ANDA = "https://www4.ine.gub.uy/Anda5/index.php/catalog/{catalog}"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}
OUT = PROCESSED / "uruguay_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2023
NATIONAL = 3_499_451

TABLES = "https://www5.ine.gub.uy/documents/CENSO%202023/Tabulados/Personas/"
CUADRO_1 = TABLES + "Cuadro_1_CAR_2023.xlsx"
CUADRO_14 = TABLES + "Cuadro_14_CAR_2023.xlsx"
JULY = ("781", "1503")                     # ANDA catalogue entry, file: personas_ext_07_2026
JULY_PAGE = "https://www4.ine.gub.uy/Anda5/index.php/catalog/781"
FEBRUARY = ("https://www5.ine.gub.uy/documents/CENSO%202023/Microdatos/"
            "personas_ext_26_02.rar")
SOURCE = ("INE Uruguay, Censo de Población, Hogares y Viviendas 2023, person microdata "
          "(July 2026 release, weighted)")
SOURCE_MUNICIPIO = (SOURCE + ", each person placed in the 2020-series municipio INE's "
                    "February 2026 release gives their address or census segment")

# INE's department codes, Montevideo first and the rest alphabetically; the
# map's first-level units carry the same names.
DEPARTMENTS = {
    "01": "Montevideo", "02": "Artigas", "03": "Canelones", "04": "Cerro Largo",
    "05": "Colonia", "06": "Durazno", "07": "Flores", "08": "Florida", "09": "Lavalleja",
    "10": "Maldonado", "11": "Paysandú", "12": "Río Negro", "13": "Rivera", "14": "Rocha",
    "15": "Salto", "16": "San José", "17": "Soriano", "18": "Tacuarembó",
    "19": "Treinta y Tres",
}
NO_MUNICIPIO = "Sin Municipio"
UNKNOWN = "9898"                            # no municipio recorded (Cuadro 14: "Sin dato")
# The February file's municipio names -> the boundary file's, where they
# differ by more than accents and case.
ALIASES = {
    **{f"Municipio {x}": f"Municipality {x}" for x in ("A", "B", "C", "CH", "D", "E", "F", "G")},
    "Joaquín Suarez": "Suárez", "La Paz - Canelones": "La Paz", "La Paz - Colonia": "La Paz",
    "Nicolich Ciudad Liber Seregni": "Nicolich",
    "Parque del Plata y Las Toscas": "Parque del Plata",
    "Quebracho - Cerro Largo": "Quebracho", "Quebracho - Paysandu": "Quebracho",
    "Colonia Miguelete": "Miguelete", "Juan Lacaze": "Juan L. Lacaze",
    "Pueblo Belén": "Belén", "Pueblo Rincón de Valentín": "Valentín",
    "Pueblo San Antonio": "San Antonio", "General Enrique Martínez": "Enrique Martínez",
}
# A municipio's people that INE files under a neighbouring department:
# (department, municipio) -> the municipio's own department. INE's note to
# Cuadro 14: the municipios were drawn on the Instituto Geográfico Militar's
# map and INE keeps the historical department lines, so a strip of a
# municipio falls on the other side of a line it does not cross.
ACROSS = {("12", "Piedras Coloradas"): "11"}
# Municipios the boundary file does not draw, whose ground lies inside the
# department's remainder polygon: (department, municipio) -> why.
UNDRAWN = {
    ("07", "Ismael Cortinas"): (
        "Flores's one municipio, Ismael Cortinas, is not drawn by the boundary file, so this "
        "polygon is the whole department and its people are counted here with the rest"),
}

# Ancestry: the five yes/no items and the principal (PERER02).
ANCESTRIES = {1: "Afro or Black", 2: "Asian", 3: "White", 4: "Indigenous", 5: "Other"}
MIXED = "Mixed (several, no principal)"
NONE_OF_THEM = "None of these ancestries"
NOT_ASKED = "not asked"
NO_ANSWER = "no answer"
PERSON = ["DIRECCION_ID", "DEPARTAMENTO", "PERPH02", "PERNA01", "PERER02"] + [
    f"PERER01_{k}" for k in ANCESTRIES]
# The share of the July file's weighted people that may go unplaced (no
# address the February file knows, in a segment that does not say which
# municipio) before the run stops.
UNPLACED = 0.01
# The share of a census segment's address-placed people that must be in one
# municipio for the segment to place the rest of its people there.
SEGMENT_SHARE = 0.98

NOT_COLLECTED = {
    "religion": ("Uruguay's 2023 census does not ask religion: the questionnaire's only "
                 "'religioso' is a kind of collective dwelling (Internado religioso), and "
                 "INE's data dictionary for the person file has no religion variable."),
    "language": ("Uruguay's 2023 census does not ask language: neither the questionnaire nor "
                 "INE's data dictionary for the person file has a language question."),
}


def opener(url: str = ANDA) -> urllib.request.OpenerDirector:
    """Cookies kept, and INE's certificate chain completed from its AIA (still verified)."""
    ctx, _ = completed_context(urllib.parse.urlsplit(url).hostname or "")
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.HTTPCookieProcessor(
                                           http.cookiejar.CookieJar()))


def fetch(open_: urllib.request.OpenerDirector, url: str, data: dict | None = None,
          limit: int | None = None) -> tuple[bytes, dict]:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=HEADERS)
    with open_.open(req, timeout=600) as resp:
        return (resp.read(limit) if limit else resp.read()), dict(resp.headers)


def accept(open_: urllib.request.OpenerDirector, catalog: str) -> str:
    """The catalogue entry's download page, after accepting INE's terms of use."""
    anda = ANDA.format(catalog=catalog)
    fetch(open_, f"{anda}/get-microdata")
    page, _ = fetch(open_, f"{anda}/get-microdata", {"accept": "Aceptar"})
    return page.decode("utf-8", "replace")


def download(open_: urllib.request.OpenerDirector, catalog: str, file_id: str,
             into: Path) -> Path:
    """One of the entry's files, saved on the runner (never committed)."""
    return download_url(open_, f"{ANDA.format(catalog=catalog)}/download/{file_id}", into)


def download_url(open_: urllib.request.OpenerDirector, url: str, into: Path) -> Path:
    """A file saved on the runner (never committed), named as the server names it."""
    req = urllib.request.Request(url, headers=HEADERS)
    with open_.open(req, timeout=1800) as resp:
        name = re.search(r'filename="([^"]+)"', resp.headers.get("Content-Disposition", ""))
        last = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])
        path = into / (name.group(1) if name else (last if "." in last else f"{last}.bin"))
        with open(path, "wb") as out:
            shutil.copyfileobj(resp, out, 1 << 20)
    log(f"  {url} -> {path.name} ({path.stat().st_size:,} bytes)")
    return path


def unpack(archive: Path, into: Path) -> list[Path]:
    """The archive's files, by whichever extractor the runner has."""
    into.mkdir(parents=True, exist_ok=True)
    for command in (["7z", "x", "-y", f"-o{into}", str(archive)],
                    ["bsdtar", "-xf", str(archive), "-C", str(into)],
                    ["unrar", "x", "-o+", str(archive), f"{into}/"]):
        if shutil.which(command[0]) is None:
            continue
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode == 0:
            log(f"  unpacked {archive.name} with {command[0]}")
            return sorted(p for p in into.rglob("*") if p.is_file())
        log(f"  {command[0]} failed on {archive.name}: {done.stderr[-300:]}")
    raise SystemExit(f"uruguay_census: nothing on this runner unpacks {archive.name}")


def sniff(path: Path) -> tuple[str, str]:
    """(encoding, delimiter) of a CSV, from its first 8 MB.

    INE's personas file has an ASCII header and Latin-1 further down, so the
    first line alone reads as UTF-8 and the file then fails a hundred MB in.
    """
    with path.open("rb") as fh:
        raw = fh.read(8 << 20)
    raw = raw[:raw.rfind(b"\n") + 1] or raw
    encoding = "latin-1"
    try:
        raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        pass
    head = raw.decode(encoding, "replace").split("\n", 1)[0]
    delimiter = max((",", ";", "\t", "|"), key=head.count)
    return encoding, delimiter


def csv_rows(archive: Path, into: Path, columns: Iterable[str]) -> Iterable[dict[str, str]]:
    """The rows of the one CSV in ``archive``, as dicts of ``columns``; the
    archive and the CSV are deleted once read."""
    found = [p for p in unpack(archive, into) if p.suffix.lower() == ".csv"]
    archive.unlink()
    if len(found) != 1:
        raise SystemExit(f"uruguay_census: {archive.name} holds {len(found)} CSV files")
    path = found[0]
    encoding, delimiter = sniff(path)
    try:
        with path.open(encoding=encoding, errors="replace", newline="") as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            header = next(reader)
            missing = [c for c in columns if c not in header]
            if missing:
                raise SystemExit(f"uruguay_census: {path.name} has no {missing}")
            at = [(c, header.index(c)) for c in columns]
            for row in reader:
                yield {c: row[i] for c, i in at}
    finally:
        path.unlink()


DDI = ("https://www4.ine.gub.uy/Anda5/index.php/metadata/export/{catalog}/ddi",
       "https://www4.ine.gub.uy/Anda5/index.php/catalog/{catalog}/export/ddi",
       "https://www4.ine.gub.uy/Anda5/index.php/ddibrowser/{catalog}/export/?format=ddi")


def ddi_text(fragment: str) -> str:
    fragment = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def ddi_variables(xml: str) -> dict[str, dict]:
    """Each variable of a DDI codebook: its label, file and categories."""
    out: dict[str, dict] = {}
    for m in re.finditer(r"(?s)<(?:\w+:)?var\b([^>]*)>(.*?)</(?:\w+:)?var>", xml):
        attrs, body = m.group(1), m.group(2)
        name = re.search(r'\bname="([^"]+)"', attrs)
        if not name:
            continue
        label = re.search(r"(?s)<(?:\w+:)?labl\b[^>]*>(.*?)</(?:\w+:)?labl>", body)
        cats = [(ddi_text(v), ddi_text(lab)) for v, lab in re.findall(
            r"(?s)<(?:\w+:)?catgry\b[^>]*>.*?<(?:\w+:)?catValu>(.*?)</(?:\w+:)?catValu>"
            r".*?<(?:\w+:)?labl\b[^>]*>(.*?)</(?:\w+:)?labl>.*?</(?:\w+:)?catgry>", body)]
        files = re.search(r'\bfiles="([^"]+)"', attrs)
        out[name.group(1)] = {"label": ddi_text(label.group(1)) if label else "",
                              "file": files.group(1) if files else "", "categories": cats}
    return out


# --- the tables INE publishes, to check the microdata against ---------------

def sheet_rows(blob: bytes) -> list[list[str]]:
    import openpyxl                                    # noqa: PLC0415
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = book.worksheets[0]
    return [["" if v is None else str(v).strip() for v in row]
            for row in sheet.iter_rows(values_only=True)]


def count(text: str) -> int:
    value = float(text)
    if value != int(value):
        raise SystemExit(f"uruguay_census: {text!r} is not a count")
    return int(value)


def department_code(name: str) -> str:
    match = [c for c, n in DEPARTMENTS.items() if fold(n) == fold(name)]
    if len(match) != 1:
        raise SystemExit(f"uruguay_census: {name!r} is no department")
    return match[0]


def cuadro_1(rows: list[list[str]]) -> dict[str, tuple[int, int, int]]:
    """{department code: (people, men, women)} from Cuadro 1."""
    out: dict[str, tuple[int, int, int]] = {}
    total = None
    for row in rows:
        if len(row) < 4 or not row[1].replace(".", "").isdigit():
            continue
        people, men, women = (count(v) for v in row[1:4])
        if abs(men + women - people) > 1:
            raise SystemExit(f"uruguay_census: Cuadro 1's {row[0]} is not its men and women")
        if row[0] == "Total":
            total = people
        elif fold(row[0]) != fold("Resto del país"):
            out[department_code(row[0])] = (people, men, women)
    if set(out) != set(DEPARTMENTS) or total != NATIONAL:
        raise SystemExit(f"uruguay_census: Cuadro 1 has departments {sorted(out)} and a total "
                         f"of {total}")
    if abs(sum(p for p, _, _ in out.values()) - NATIONAL) > len(out):
        raise SystemExit("uruguay_census: Cuadro 1's departments do not make its total")
    return out


def cuadro_14(rows: list[list[str]]) -> dict[tuple[str, str], int]:
    """{(department code, folded municipio or UNKNOWN): people} from Cuadro 14."""
    out: dict[tuple[str, str], int] = {}
    for row in rows:
        if len(row) < 3 or not row[2].replace(".", "").isdigit() or row[0] == "Total":
            continue
        name = UNKNOWN if fold(row[1]) == fold("Sin dato de Municipio") else fold(row[1])
        key = (department_code(row[0]), name)
        if key in out:
            raise SystemExit(f"uruguay_census: Cuadro 14 has {row[0]}'s {row[1]} twice")
        out[key] = count(row[2])
    if abs(sum(out.values()) - NATIONAL) > len(out):
        raise SystemExit(f"uruguay_census: Cuadro 14's rows make {sum(out.values()):,}")
    return out


# --- people -----------------------------------------------------------------

def principal(row: dict[str, str]) -> str:
    """A person's principal ancestry, NOT_ASKED (8888: the person was not asked),
    or NO_ANSWER (anything else short of an answer)."""
    answers = [row.get(f"PERER01_{k}", "") for k in ANCESTRIES]
    if "8888" in answers:
        return NOT_ASKED
    if any(a not in ("1", "2") for a in answers):
        return NO_ANSWER
    yes = [k for k, a in zip(ANCESTRIES, answers) if a == "1"]
    if not yes:
        return NONE_OF_THEM
    if len(yes) == 1:
        return ANCESTRIES[yes[0]]
    chosen = row.get("PERER02", "")
    if chosen == "6":
        return MIXED
    if chosen.isdigit() and int(chosen) in yes:
        return ANCESTRIES[int(chosen)]
    return NO_ANSWER


class Tally:
    """One unit's weighted people: by sex, single year of age and ancestry."""

    __slots__ = ("people", "men", "women", "ages", "ancestry", "yes", "rows")

    def __init__(self) -> None:
        self.people = self.men = self.women = 0.0
        self.ages: Counter = Counter()
        self.ancestry: Counter = Counter()
        self.yes: Counter = Counter()
        self.rows = 0

    def add(self, row: dict[str, str], weight: float) -> None:
        self.rows += 1
        self.people += weight
        sex = row.get("PERPH02")
        if sex == "1":
            self.men += weight
        elif sex == "2":
            self.women += weight
        else:
            raise SystemExit(f"uruguay_census: a person with sex {sex!r}")
        age = row.get("PERNA01", "")
        if not age.isdigit() or int(age) > 120:
            raise SystemExit(f"uruguay_census: a person aged {age!r}")
        self.ages[int(age)] += weight
        found = principal(row)
        self.ancestry[found] += weight
        if found not in (NOT_ASKED, NO_ANSWER):
            for k, label in ANCESTRIES.items():
                if row[f"PERER01_{k}"] == "1":
                    self.yes[label] += weight

    def merge(self, other: "Tally") -> None:
        self.people += other.people
        self.men += other.men
        self.women += other.women
        self.ages.update(other.ages)
        self.ancestry.update(other.ancestry)
        self.yes.update(other.yes)
        self.rows += other.rows


def weight_of(row: dict[str, str]) -> float:
    try:
        return float(row["W"].replace(",", "."))
    except (KeyError, ValueError):
        raise SystemExit(f"uruguay_census: a person with weight {row.get('W')!r}") from None


def shape_of(address: str) -> str:
    """What an address code looks like -- its length and which characters --
    for the log, which never prints the code itself."""
    kind = "digits" if address.isdigit() else ("empty" if not address else "other")
    return f"{len(address)} {kind}"


def address_key(address: str) -> str:
    """An address code as both files can be matched on it: a code one file
    writes as a number (no leading zero, or with '.0') is the same code."""
    address = address.strip()
    if address.endswith(".0"):
        address = address[:-2]
    return address.lstrip("0") if address.isdigit() else address


def placements(rows: Iterable[dict[str, str]]
               ) -> tuple[dict[str, tuple[str, str] | None], Counter, Counter]:
    """{address: (department, 2020 municipio)} from the February file, its
    people's counts by pair, and how many had no address or one in two places.

    The two releases number their people differently (ID_CENSO is not the same
    person in both), so a person is placed by the address the census gives
    their dwelling (DIRECCION_ID). An address the February file puts in two
    municipios is not used.
    """
    where: dict[str, tuple[str, str] | None] = {}
    pairs: dict[tuple[str, str], tuple[str, str]] = {}
    counts: Counter = Counter()
    stats: Counter = Counter()
    for row in rows:
        key = (row["DEPARTAMENTO"].zfill(2), row["MUNICIPIO_PAIS"].strip())
        key = pairs.setdefault(key, key)           # one tuple per pair, not per person
        counts[key] += 1
        raw = row["DIRECCION_ID"].strip()
        stats[f"address shape {shape_of(raw)}"] += 1
        address = address_key(raw)
        if not address:
            stats["no address"] += 1
            continue
        seen = where.setdefault(address, key)
        if seen is not None and seen != key:
            where[address] = None
            stats["address in two municipios"] += 1
    stats["addresses"] = len(where)
    return where, counts, stats


def tally(rows: Iterable[dict[str, str]], where: dict[str, tuple[str, str] | None]
          ) -> tuple[dict[str, Tally], dict[tuple[str, str], Tally], Counter, dict[str, float]]:
    """The July file, weighted: by its departments, by the February file's
    municipios, and by its own 2025-series municipios (people only).

    A person whose address the February file has is placed by it. About a
    quarter of the July file's address codes are not in the February file,
    though the rest agree to the department; those people are placed by their
    census segment (department, section, segment), in the municipio where
    the segment's placed people all are -- SEGMENT_SHARE of them at least.
    A segment whose placed people are split, or that has none, places no one.
    """
    departments: dict[str, Tally] = defaultdict(Tally)
    municipios: dict[tuple[str, str], Tally] = defaultdict(Tally)
    series_2025: Counter = Counter()
    unplaced: dict[str, Any] = {"people": 0.0, "rows": 0, "other_department": 0.0,
                                "total": 0.0, "by_address": 0.0, "by_segment": 0.0}
    lost: Counter = Counter()
    shapes: Counter = Counter()
    unplaced["by_department"] = lost
    unplaced["shapes"] = shapes
    votes: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    waiting: dict[tuple[str, str, str], Tally] = defaultdict(Tally)
    for row in rows:
        weight = weight_of(row)
        dept = row["DEPARTAMENTO"].zfill(2)
        unplaced["total"] += weight
        departments[dept].add(row, weight)
        name = row["MUNICIPIO_136"].strip()
        series_2025[(dept, UNKNOWN if name == UNKNOWN else fold(name))] += weight
        raw = row["DIRECCION_ID"].strip()
        place = where.get(address_key(raw))
        segment = (dept, row["SECCION"].strip(), row["SEGMENTO"].strip())
        if place is None:
            shapes[f"{shape_of(raw)} {'known' if address_key(raw) in where else 'unknown'}"] += 1
            waiting[segment].add(row, weight)
            continue
        shapes[f"{shape_of(raw)} placed"] += 1
        if place[0] != dept:
            unplaced["other_department"] += weight
        votes[segment][place] += weight
        unplaced["by_address"] += weight
        municipios[place].add(row, weight)
    splits: Counter = Counter()
    for segment, unit in waiting.items():
        seen = votes.get(segment)
        top, share = None, 0.0
        if seen and sum(seen.values()) > 0:        # some people weigh nothing
            top, most = seen.most_common(1)[0]
            share = most / sum(seen.values())
        if top is None or share < SEGMENT_SHARE:
            splits["segment with no placed people" if top is None else "segment split"] += 1
            unplaced["people"] += unit.people
            unplaced["rows"] += unit.rows
            lost[segment[0]] += unit.people
            continue
        splits["segment whole" if share == 1 else "segment nearly whole"] += 1
        unplaced["by_segment"] += unit.people
        municipios[top].merge(unit)
    unplaced["segments"] = splits
    return dict(departments), dict(municipios), series_2025, unplaced


# --- checks -----------------------------------------------------------------

def check_departments(departments: dict[str, Tally],
                      published: dict[str, tuple[int, int, int]]) -> None:
    for code, (people, men, women) in published.items():
        unit = departments.get(code)
        if unit is None or any(abs(a - b) > 1 for a, b in
                               ((unit.people, people), (unit.men, men), (unit.women, women))):
            got = (round(unit.people), round(unit.men), round(unit.women)) if unit else None
            raise SystemExit(f"uruguay_census: {DEPARTMENTS[code]} weighs {got} in the person "
                             f"file; Cuadro 1 publishes {(people, men, women)}")
    if set(departments) != set(published):
        raise SystemExit(f"uruguay_census: departments {sorted(set(departments) - set(published))}")
    log(f"  {len(published)} departments' weighted people, men and women make Cuadro 1")


def check_municipios(series_2025: Counter, published: dict[tuple[str, str], int]) -> None:
    wrong = {k: (round(series_2025.get(k, 0)), v) for k, v in published.items()
             if abs(series_2025.get(k, 0) - v) > 1}
    # A row the table leaves out must round to no one (San José's people with
    # no municipio recorded weigh less than one person).
    extra = sorted((k, round(v, 2)) for k, v in series_2025.items()
                   if k not in published and v >= 1)
    if wrong or extra:
        raise SystemExit(f"uruguay_census: the person file by its own municipios differs from "
                         f"Cuadro 14: {sorted(wrong.items())[:10]}; not in it: {extra[:10]}")
    small = {k: round(v, 3) for k, v in series_2025.items() if k not in published}
    if small:
        log(f"  in the person file and not in Cuadro 14, each under one weighted person: {small}")
    log(f"  the weighted person file makes Cuadro 14's {len(published)} rows, "
        "department by department and municipio by municipio")


def check_placements(unplaced: dict[str, float], rows_july: int) -> None:
    """Nearly every July person's address must be in the February file, and in
    the same department there."""
    log(f"  {rows_july - unplaced['rows']:,} of {rows_july:,} July rows placed: "
        f"{unplaced.get('by_address', 0):,.0f} weighted people by the February file's "
        f"addresses, {unplaced.get('by_segment', 0):,.0f} by their census segment; "
        f"{unplaced['people']:,.0f} not placed, {unplaced['other_department']:,.0f} placed in "
        f"another department; segments: {dict(unplaced.get('segments') or {})}")
    lost = unplaced.get("by_department") or {}
    log("  not placed, by department: " + ", ".join(
        f"{DEPARTMENTS.get(d, d)} {v:,.0f}" for d, v in sorted(lost.items())))
    log(f"  July address codes, by shape: {dict(unplaced.get('shapes') or {})}")
    if unplaced["people"] > UNPLACED * unplaced["total"] or \
            unplaced["other_department"] > 0.001 * unplaced["total"]:
        raise SystemExit(f"uruguay_census: {unplaced['people']:,.0f} weighted people of the July "
                         f"file have no address the February file places, and "
                         f"{unplaced['other_department']:,.0f} have one in another department")


def compare_series(municipios: dict[tuple[str, str], Tally],
                   published: dict[tuple[str, str], int]) -> None:
    """Log each 2020-series municipio against the 2025-series row of its name.

    Not a check: the two series differ where a municipio was divided or its
    limits revised (Joaquín Suárez gave Del Andaluz its ground), and the log
    says where and by how much.
    """
    differ = []
    for (d, m), unit in sorted(municipios.items()):
        if m in (NO_MUNICIPIO, UNKNOWN):
            continue
        row = published.get((d, fold(m)))
        if row is None:
            row = next((v for (pd, pm), v in published.items()
                        if pd == d and pm == fold(ALIASES.get(m, m))), None)
        if row is None or abs(unit.people - row) > max(5, 0.01 * row):
            differ.append(f"{m} ({DEPARTMENTS[d]}): {unit.people:,.0f} against "
                          f"{row if row is None else f'{row:,}'}")
    log(f"  2020-series municipios differing from the 2025 series row of their name by more "
        f"than 1%: {len(differ)}")
    for line in differ:
        log(f"    {line}")


# --- binding ----------------------------------------------------------------

def polygons(pairs: Iterable[tuple[str, str]], admin1: list[dict], admin2: list[dict]
             ) -> tuple[dict[tuple[str, str], str], list[tuple[str, str]], dict[str, str]]:
    """{(department, municipio): polygon id}, the pairs no polygon holds, and why.

    A municipio binds by name to one polygon of its own department. People a
    municipio has across a department line (ACROSS) go with the municipio; a
    department's "Sin Municipio" and its undrawn municipios (UNDRAWN) go to
    the department's remainder polygon. What is left -- people with no
    municipio recorded, and a department's "Sin Municipio" where the map
    draws no remainder -- is returned, and every drawn polygon must be bound.
    """
    names = {u["id"]: u["name"] for u in admin1}
    code_of = {u["id"]: department_code(u["name"]) for u in admin1}
    rest = {code_of[s["parent"]]: s["id"] for s in admin2 if s["id"].startswith("URY-REST-")}
    drawn = [s for s in admin2 if not s["id"].startswith("URY-REST-")]
    pairs = sorted(set(pairs))
    named = {(d, m) for d, m in pairs if m not in (NO_MUNICIPIO, UNKNOWN)
             and (d, m) not in ACROSS and (d, m) not in UNDRAWN}
    bound, missing = bind({f"{d}|{m}": (m, DEPARTMENTS[d]) for d, m in named}, drawn, names,
                          ALIASES)
    if missing:
        raise SystemExit(f"uruguay_census: municipios with no polygon: {missing}")
    out: dict[tuple[str, str], str] = {}
    shape_dept = {s["id"]: code_of[s["parent"]] for s in admin2}
    for key, sid in bound.items():
        d, m = key.split("|", 1)
        if shape_dept[sid] != d:
            raise SystemExit(f"uruguay_census: {m} bound to a polygon of another department")
        out[(d, m)] = sid
    empty = sorted(s["name"] for s in drawn if s["id"] not in out.values())
    if empty:
        raise SystemExit(f"uruguay_census: polygons with no municipio: {empty}")
    left: list[tuple[str, str]] = []
    why: dict[str, str] = {}
    for d, m in pairs:
        if (d, m) in ACROSS:
            home = [sid for (hd, hm), sid in out.items() if hd == ACROSS[(d, m)] and hm == m]
            if len(home) != 1:
                raise SystemExit(f"uruguay_census: {m} has people in {DEPARTMENTS[d]} and no "
                                 f"polygon in {DEPARTMENTS[ACROSS[(d, m)]]}")
            out[(d, m)] = home[0]
        elif m == NO_MUNICIPIO or (d, m) in UNDRAWN:
            if d in rest:
                out[(d, m)] = rest[d]
                if (d, m) in UNDRAWN:
                    why[rest[d]] = UNDRAWN[(d, m)]
            else:
                left.append((d, m))
        elif m == UNKNOWN:
            left.append((d, m))
    for d, sid in rest.items():
        if (d, NO_MUNICIPIO) not in out:
            raise SystemExit(f"uruguay_census: {DEPARTMENTS[d]}'s remainder has no one in it")
    return out, left, why


# --- fields -----------------------------------------------------------------

def core_fields(unit: Tally, source: str) -> dict[str, Any]:
    return {
        "population": measure(round(unit.people), year=YEAR, source=source),
        "median_age": measure(median_age(unit.ages), unit="years", year=YEAR, source=source),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "INE's weighted census microdata; INE tabulates ages, not the median."),
        "sex_ratio": measure(round(1000 * unit.men / unit.women), unit="males_per_1000_females",
                             year=YEAR, source=source),
    }


def ethnicity_fields(unit: Tally) -> dict[str, Any]:
    counts = {k: round(v) for k, v in unit.ancestry.items()
              if k not in (NOT_ASKED, NO_ANSWER) and round(v)}
    answered = sum(counts.values())
    if not answered:
        return {"ethnicity": gap("not_available", "No one here answered the census's ancestry "
                                 "questions.")}
    asked = round(unit.ancestry.get(NOT_ASKED, 0))
    silent = round(unit.ancestry.get(NO_ANSWER, 0))
    weighed = sum(v for k, v in unit.ancestry.items() if k not in (NOT_ASKED, NO_ANSWER))
    any_yes = {k: 100 * v / weighed for k, v in unit.yes.items()}
    return {
        "ethnicity": shares(counts),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Each person's principal ethnic-racial ancestry, from the 2023 census's two "
            "questions: whether a person believes they have Afro or Black, Asian, White, "
            "Indigenous or other ancestry (yes or no to each), and, of those who said yes to "
            "more than one, which is the principal. One yes is counted with its ancestry; "
            f"several and no principal is '{MIXED}'; no to all five is '{NONE_OF_THEM}'. "
            f"Counting every yes, {any_yes.get('Afro or Black', 0):.1f}% of the {answered:,} "
            f"who answered here have Afro or Black ancestry and "
            f"{any_yes.get('Indigenous', 0):.1f}% Indigenous ancestry. Left out: {asked:,} "
            "people here who were not asked -- counted from administrative records or on the "
            f"short questionnaire -- and {silent:,} who did not answer. Weighted counts."),
    }


def not_collected() -> dict[str, Any]:
    return {field: gap("not_collected", note) for field, note in NOT_COLLECTED.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=["microdata", "columns", "ddi"])
    ap.add_argument("--catalog", default="781", help="the ANDA catalogue entry")
    ap.add_argument("--file", help="with --probe columns: the entry's file id")
    ap.add_argument("--url", help="with --probe columns: an archive's URL, in place of --file")
    ap.add_argument("--count", default="", help="columns whose values are counted")
    ap.add_argument("--limit", type=int, default=300, help="values printed per column")
    ap.add_argument("--weight", default="", help="with --probe columns: sum this column too")
    ap.add_argument("--vars", default="", help="with --probe ddi: variables printed in full")
    args = ap.parse_args()
    if args.probe:
        return probe(args)

    admin1 = json.loads((SITE / "admin1" / "URY.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "URY.units.json").read_text())
    if {u["name"] for u in admin1} != set(DEPARTMENTS.values()):
        raise SystemExit(f"uruguay_census: the map's departments are "
                         f"{sorted(u['name'] for u in admin1)}")
    www5 = opener(TABLES)
    published_1 = cuadro_1(sheet_rows(fetch(www5, CUADRO_1)[0]))
    published_14 = cuadro_14(sheet_rows(fetch(www5, CUADRO_14)[0]))

    with tempfile.TemporaryDirectory() as tmp:
        where, february, stats = placements(csv_rows(
            download_url(www5, FEBRUARY, Path(tmp)), Path(tmp) / "feb",
            ["DIRECCION_ID", "DEPARTAMENTO", "MUNICIPIO_PAIS"]))
        log(f"  February file: {sum(february.values()):,} people in {len(february)} "
            f"(department, municipio) pairs; {dict(stats)}")
        anda = opener()
        accept(anda, JULY[0])
        rows_july = 0

        def counted(rows: Iterable[dict[str, str]]) -> Iterable[dict[str, str]]:
            nonlocal rows_july
            for row in rows:
                rows_july += 1
                yield row

        departments, municipios, series_2025, unplaced = tally(
            counted(csv_rows(download(anda, *JULY, Path(tmp)), Path(tmp) / "jul",
                             PERSON + ["W", "MUNICIPIO_136", "SECCION", "SEGMENTO"])), where)
        del where

    total = sum(u.people for u in departments.values())
    if abs(total - NATIONAL) > 1:
        raise SystemExit(f"uruguay_census: the July file weighs {total:,.1f}, not {NATIONAL:,}")
    check_departments(departments, published_1)
    check_municipios(series_2025, published_14)
    check_placements(unplaced, rows_july)
    compare_series(municipios, published_14)

    placed, left, why = polygons(municipios, admin1, admin2)
    for pair in left:
        log(f"  on no polygon: {DEPARTMENTS[pair[0]]} {pair[1]}: "
            f"{municipios[pair].people:,.0f} weighted people")
    by_polygon: dict[str, Tally] = defaultdict(Tally)
    parts: dict[str, list[str]] = defaultdict(list)
    for pair, sid in placed.items():
        by_polygon[sid].merge(municipios[pair])
        parts[sid].append(f"{pair[1]} ({DEPARTMENTS[pair[0]]})")

    records: list[dict[str, Any]] = []
    cite = {"name": SOURCE, "url": JULY_PAGE, "year": YEAR}
    drawn = {s["id"]: s for s in admin2}
    for sid, unit in sorted(by_polygon.items()):
        shape = drawn[sid]
        parent = next(u for u in admin1 if u["id"] == shape["parent"])
        fields = core_fields(unit, SOURCE_MUNICIPIO)
        notes = []
        if sid.startswith("URY-REST-"):
            notes.append("The people of the department INE files under no municipio")
            if sid in why:
                notes.append(why[sid])
        across = [p for p in parts[sid] if not p.endswith(f"({parent['name']})")]
        if across:
            notes.append(f"Includes {', '.join(across)}: the municipio's people on the other "
                         "side of INE's historical department line, which the municipio's "
                         "own limits cross")
        notes.append("INE's current tables file people under the 2025 electoral series of "
                     "municipios, which the boundary file does not draw; these are the same "
                     "weighted people, placed in the 2020-series municipio INE's February "
                     "2026 release gives their address (or, where the two releases code "
                     "the address differently, the municipio of the rest of their census "
                     "segment)")
        fields["population"]["note"] = ". ".join(notes) + "."
        records.append(record(
            f"URY-INE-{fold(parent['name'])}-{fold(shape['name'])}", shape["name"],
            level="admin2", parent="URY", country="URY",
            parent_name=parent["name"], match_by="shape_id", shape_id=sid,
            **fields, **ethnicity_fields(unit), **not_collected(),
            sources=[{"field": "population/median age/sex ratio/ethnicity", **cite},
                     {"field": "municipio", "name": "INE Uruguay, Censo 2023 person "
                      "microdata, February 2026 release", "url": FEBRUARY, "year": YEAR}]))
    for code, name in DEPARTMENTS.items():
        shape = next(u for u in admin1 if u["name"] == name)
        unit = departments[code]
        records.append(record(
            f"URY-INE-{code}", name, level="admin1", parent="URY", country="URY",
            codes={"ine": code}, match_by="shape_id", shape_id=shape["id"],
            **core_fields(unit, SOURCE), **ethnicity_fields(unit), **not_collected(),
            sources=[{"field": "population/median age/sex ratio/ethnicity", **cite},
                     {"field": "check", "name": "INE Uruguay, Censo 2023, Cuadro 1",
                      "url": CUADRO_1, "year": YEAR}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {sum(r['level'] == 'admin1' for r in records)} departments, "
        f"{sum(r['level'] == 'admin2' for r in records)} municipio and remainder polygons")
    return 0


def probe(args: argparse.Namespace) -> int:
    open_ = opener()
    if args.probe == "ddi":
        for template in DDI:
            url = template.format(catalog=args.catalog)
            try:
                body, headers = fetch(open_, url)
            except Exception as err:                  # noqa: BLE001
                print(f"{url}: {type(err).__name__}: {str(err)[:200]}")
                continue
            xml = body.decode("utf-8", "replace")
            print(f"{url}: {len(body):,} bytes, {headers.get('Content-Type')}")
            for fid, fname in re.findall(
                    r'(?s)<(?:\w+:)?fileDscr\b[^>]*ID="([^"]+)".*?'
                    r"<(?:\w+:)?fileName>(.*?)</(?:\w+:)?fileName>", xml):
                print(f"  file {fid}: {fname.strip()}")
            found = ddi_variables(xml)
            if not found:
                print(f"  no variables; starts {xml[:300]!r}")
                continue
            wanted = [v for v in args.vars.split(",") if v]
            for name, var in found.items():
                cats = var["categories"]
                shown = f": {cats[:args.limit]}" if name in wanted else ""
                print(f"  {var['file']} {name}: {var['label']!r}; {len(cats)} categories{shown}")
            return 0
        return 1
    if args.probe == "microdata":
        text = accept(open_, args.catalog)
        for href, label in re.findall(r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text):
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()
            if "download" in href and "Descarg" in label:
                print(f"  {label[:100]!r} -> {href}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        if args.url:
            archive = download_url(opener(args.url), args.url, Path(tmp))
        else:
            accept(open_, args.catalog)
            archive = download(open_, args.catalog, args.file, Path(tmp))
        for path in unpack(archive, Path(tmp) / "x"):
            print(f"file {path.name}: {path.stat().st_size:,} bytes")
            if path.suffix.lower() != ".csv":
                continue
            encoding, delimiter = sniff(path)
            with path.open(encoding=encoding, errors="replace", newline="") as fh:
                reader = csv.reader(fh, delimiter=delimiter)
                header = next(reader)
                print(f"  {encoding}, {delimiter!r}, {len(header)} columns: {header}")
                # "A+B" counts the pairs of two columns' values.
                wanted = [c for c in args.count.split(",") if c]
                idx = {c: [header.index(p) for p in c.split("+")] for c in wanted
                       if all(p in header for p in c.split("+"))}
                missing = [c for c in wanted if c not in idx]
                if missing:
                    print(f"  no such columns: {missing}")
                counts = {c: Counter() for c in idx}
                weights = {c: Counter() for c in idx}
                w = header.index(args.weight) if args.weight and args.weight in header else None
                rows, total = 0, 0.0
                for row in reader:
                    rows += 1
                    weight = float(row[w].replace(",", ".") or 0) if w is not None else 0.0
                    total += weight
                    for c, cols in idx.items():
                        value = "+".join(row[i] if i < len(row) else "" for i in cols)
                        counts[c][value] += 1
                        weights[c][value] += weight
                print(f"  {rows:,} rows; {args.weight or 'no weight'} sums to {total:,.3f}")
                for c, counter in counts.items():
                    print(f"  {c}: {len(counter)} values: {sorted(counter.items())[:args.limit]}")
                    if w is not None:
                        summed = [(k, round(v, 2)) for k, v in sorted(weights[c].items())]
                        print(f"  {c} weighted: {summed[:args.limit]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
