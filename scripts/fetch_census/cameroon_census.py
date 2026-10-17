#!/usr/bin/env python3
"""Cameroon -- the 2005 census's resident population by department and sex.

The Bureau Central des Recensements et des Études de Population (BUCREP)
published the Troisième Recensement Général de la Population et de l'Habitat
(3e RGPH, 11 November 2005) as, among other tables, *Répartition de la
population du Cameroun (par département, arrondissement, district) en 2010
par sexe* (2010): for each of the ten provinces (regions since 2008), a table
of its residents by department and by arrondissement or district, men and
women, then the same for its urban and for its rural residents. BUCREP's own
site is gone; the copy the Internet Archive kept in April 2016 is read.

What this writes:

* each of the 58 departments: the resident population and the sex ratio;
* each region: the same, its departments added up as the table adds them.

**Checks**, each of which stops the run: every line's men and women make its
total; every department's arrondissements make the department; every
province's departments make the province; and every department's urban and
rural residents make its total.

**Capitals.** French Wikipedia's *Départements du Cameroun* names each
department's seat (*préfecture*); it is read for the capital alone.

The table gives no ages, so no department has a median age from it.

Usage:
    python -m scripts.fetch_census.cameroon_census [--run LABEL]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import bind, fold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

ORIGINAL = ("http://www.bucrep.cm:80/index.php/fr/ressources-et-documentations/telechargement/"
            "category/1-etat-de-la-population?download=70:rpartition-de-la-population-du-cameroun-"
            "par-dpartement-arrondissement-district-en-2010-par-sexe")
URL = "https://web.archive.org/web/20160402231629id_/" + ORIGINAL
YEAR = 2005
OUT = "cameroon_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Bureau Central des Recensements et des Études de Population (BUCREP), 3e Recensement "
          "Général de la Population et de l'Habitat 2005, Répartition de la population du "
          "Cameroun par département, arrondissement et district, par sexe")
LICENCE = "Official statistics of the Republic of Cameroon (BUCREP), as the Internet Archive keeps it"
WIKI_TITLE = "Départements du Cameroun"
WIKI_URL = "https://fr.wikipedia.org/wiki/D%C3%A9partements_du_Cameroun"

# The table's provinces -> the map's first-level names.
PROVINCES = {"adamaoua": "Adamaoua", "centre": "Centre", "est": "East",
             "extremenord": "Far North", "littoral": "Littoral", "nord": "North",
             "nordouest": "North-West", "ouest": "West", "sud": "South", "sudouest": "South-West"}
FIGURES = re.compile(r"^(?P<label>.*?)\s*(?P<t>\d+)\s+(?P<m>\d+)\s+(?P<f>\d+)\s+"
                     r"(?P<r>\d+(?:[,.]\d+)?|-|#\S+)\s*$")
DEPARTMENT = re.compile(r"^d[ée]partement\s+(?:du|de\s+la|de\s+l['’]|des|de)\s*", re.I)
PROVINCE = re.compile(r"^province\s+(?:du|de\s+la|de\s+l['’]|des|de)\s*", re.I)
HEADER = re.compile(r"^(tableau|circonscription|population|administrative|r[ée]partition|sexe$|"
                    r"rapport|d[ée]partement\s+et\s+par|arrondissement/district|l['’]?\s*$)", re.I)

AGE_GAP = ("BUCREP's tables of the 2005 census by department count each department's residents "
           "by sex and by urban or rural residence, not by age, so no median age is published "
           "for the department.")


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c))


def entries(lines: list[str]) -> list[tuple[str, int, int, int]]:
    """(label, total, men, women) for a table's figure lines, in order.

    A name too long for its cell is printed on two lines around its figures
    ("Département du FARO ET" / figures / "DEO"); the line before and the one
    after are joined to it.
    """
    out: list[list[Any]] = []
    before: str | None = None
    open_end = False
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            continue
        m = FIGURES.match(line)
        if m:
            label = m.group("label").strip()
            if not label and before:
                label, open_end = before, True
            else:
                open_end = False
            out.append([label, int(m.group("t")), int(m.group("m")), int(m.group("f"))])
            before = None
            continue
        if HEADER.match(plain(line)) and not open_end:
            before = None
            continue
        if open_end and out:
            out[-1][0] = f"{out[-1][0]} {line}"
            open_end = False
            continue
        before = line
    return [tuple(e) for e in out]


def kind(title: str) -> str:
    t = plain(title).lower()
    return "urban" if "urbain" in t else "rural" if "rural" in t else "all"


def segments(pages: list[str]) -> list[tuple[str, str, list[str]]]:
    """(kind, title, lines) for each table, a table running from one title to the next."""
    out: list[tuple[str, str, list[str]]] = []
    current: list[str] | None = None
    title = ""
    for page in pages:
        for line in page.splitlines():
            if re.match(r"^\s*T\s*ableau\s*n", line):
                if current is not None:
                    out.append((kind(title), title, current))
                current, title = [], line
                continue
            if current is not None:
                if len(title) < 200 and not FIGURES.match(" ".join(line.split())) and not current:
                    title += " " + line
                current.append(line)
    if current is not None:
        out.append((kind(title), title, current))
    return out


def structure(rows: list[tuple[str, int, int, int]]) -> dict[str, Any]:
    """{"province": (name, t, m, f), "departments": {name: ((t, m, f), {arr: (t, m, f)})}}."""
    province = None
    departments: dict[str, Any] = {}
    current = None
    for label, t, m, f in rows:
        if t != m + f:
            raise SystemExit(f"cameroon_census: {label!r}: {m:,} + {f:,} is not {t:,}")
        if PROVINCE.match(plain(label)):
            province = (PROVINCE.sub("", plain(label)).strip(), t, m, f)
            current = None
        elif DEPARTMENT.match(plain(label)):
            current = DEPARTMENT.sub("", plain(label)).strip()
            departments[current] = ((t, m, f), {})
        elif current is not None:
            departments[current][1][label] = (t, m, f)
    return {"province": province, "departments": departments}


def read(pages: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """{province key: {"all": structure, "urban": ..., "rural": ...}} and problems."""
    tables_: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for what, title, lines in segments(pages):
        s = structure(entries(lines))
        if s["province"] is None:
            continue
        key = fold(s["province"][0])
        if key not in PROVINCES:
            problems.append(f"province {s['province'][0]!r} not known")
            continue
        if what in tables_.setdefault(key, {}):
            problems.append(f"{PROVINCES[key]}: two {what} tables")
            continue
        tables_[key][what] = s
    for key, name in PROVINCES.items():
        found = tables_.get(key, {})
        if "all" not in found:
            problems.append(f"{name}: no table of all residents")
            continue
        s = found["all"]
        made = [sum(d[0][i] for d in s["departments"].values()) for i in range(3)]
        if tuple(made) != s["province"][1:]:
            problems.append(f"{name}: departments make {made}, the province {s['province'][1:]}")
        for dep, (figures, arrs) in s["departments"].items():
            if arrs:
                summed = tuple(sum(a[i] for a in arrs.values()) for i in range(3))
                if summed != figures:
                    problems.append(f"{name} / {dep}: arrondissements make {summed}, "
                                    f"the department {figures}")
            parts = [found.get(w, {}).get("departments", {}).get(dep) for w in ("urban", "rural")]
            if all(parts):
                both = tuple(parts[0][0][i] + parts[1][0][i] for i in range(3))
                if both != figures:
                    problems.append(f"{name} / {dep}: urban and rural make {both}, all {figures}")
            else:
                problems.append(f"{name} / {dep}: no urban or rural line to check")
    return tables_, problems


def seats(wikitext: str) -> dict[str, str]:
    """Department -> its seat, from the article's table naming both."""
    out: dict[str, str] = {}
    for table in tables(wikitext):
        if not table:
            continue
        head = [fold(c) for c in table[0]]
        dep = next((i for i, c in enumerate(head) if c.startswith("departement")), None)
        seat = next((i for i, c in enumerate(head) if c in ("prefecture", "chefslieux", "chef-lieu")
                     or c.startswith("cheflieu") or c == "prefecture"), None)
        if dep is None or seat is None:
            continue
        for row in table[1:]:
            if len(row) > max(dep, seat) and row[dep] and row[seat]:
                out.setdefault(row[dep].strip(), row[seat].strip())
    return out


def ratio(m: int, f: int) -> int:
    return round(1000 * m / f)


def fields(t: int, m: int, f: int, note: str) -> dict[str, Any]:
    return {"population": measure(t, year=YEAR, source=SOURCE), "population_note": note,
            "sex_ratio": measure(ratio(m, f), unit="males_per_1000_females", year=YEAR,
                                 source=SOURCE),
            "sex_ratio_note": "Men per 1,000 women among the residents the 2005 census counted."}


def build(tables_: dict[str, dict[str, Any]], seat_of: dict[str, str],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    cite = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "year": YEAR,
             "license": LICENCE}]
    parents = {u["id"]: u["name"] for u in admin1}
    first = {u["name"]: u for u in admin1}
    records: list[dict[str, Any]] = []
    departments: dict[str, tuple[str, str]] = {}
    counts: dict[str, tuple[int, int, int]] = {}
    for key, found in tables_.items():
        region = PROVINCES[key]
        poly = first.get(region)
        s = found["all"]
        _name, t, m, f = s["province"]
        if poly is None:
            raise SystemExit(f"cameroon_census: no first-level polygon named {region}")
        records.append(record(
            f"CMR-RGPH2005-{poly['id']}", poly["name"], level="admin1", parent="CMR",
            country="CMR", match_by="shape_id", shape_id=poly["id"], sources=cite,
            **fields(t, m, f, f"The resident population of the {region} region at the 2005 "
                              f"census, its departments added up.")))
        report.append(f"  {region}: {t:,} ({m:,} men, {f:,} women), "
                      f"{len(s['departments'])} departments")
        for dep, (figures, _arrs) in s["departments"].items():
            code = f"{key}:{dep}"
            departments[code] = (dep.title(), region)
            counts[code] = figures
    bound, missing = bind(departments, admin2, parents)
    if missing:
        raise SystemExit("cameroon_census: departments with no polygon: " + ", ".join(missing))
    shapes = {u["id"]: u for u in admin2}
    unbound = sorted(u["name"] for u in admin2 if u["id"] not in set(bound.values()))
    if unbound:
        raise SystemExit("cameroon_census: polygons no department reached: " + ", ".join(unbound))
    seat_keys = {fold(k): v for k, v in seat_of.items()}
    for code, sid in sorted(bound.items(), key=lambda kv: kv[0]):
        t, m, f = counts[code]
        shape = shapes[sid]
        dep_name = departments[code][0]
        extra: dict[str, Any] = {"median_age": gap(NOT_AVAILABLE, AGE_GAP)}
        sources = list(cite)
        seat = seat_keys.get(fold(dep_name)) or seat_keys.get(fold(shape["name"]))
        if seat:
            extra["capital"] = seat
            sources.append({"field": "capital", "name": f"French Wikipedia, {WIKI_TITLE}",
                            "url": WIKI_URL, "license": "CC BY-SA 4.0"})
        records.append(record(
            f"CMR-RGPH2005-{sid}", shape["name"], level="admin2", parent="CMR", country="CMR",
            match_by="shape_id", shape_id=sid, sources=sources,
            **fields(t, m, f, f"The resident population of the {shape['name']} department at "
                              f"the 2005 census."), **extra))
        report.append(f"    {shape['name']} ({departments[code][1]}): {t:,}, "
                      f"{ratio(m, f)} men per 1,000 women, seat {seat or '-'}")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    import pdfplumber                               # noqa: PLC0415
    from .europe_wiki import fetch as wiki_fetch     # noqa: PLC0415
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    log(f"cameroon_census: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    if not blob.startswith(b"%PDF"):
        raise SystemExit("cameroon_census: the archived copy is not a PDF")
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    tables_, problems = read(pages)
    for p in problems:
        log(f"  check: {p}")
    if problems:
        for what, title, lines in segments(pages)[:3]:
            log(f"  --- {what}: {title}")
            for line in lines[:40]:
                log(f"    | {line}")
        raise SystemExit("cameroon_census: the tables do not add up as read")
    total = sum(f["all"]["province"][1] for f in tables_.values())
    log(f"  the ten provinces make {total:,} residents")
    wikitext, landed = wiki_fetch(WIKI_TITLE, "fr")
    seat_of = seats(wikitext)
    log(f"  {landed}: {len(seat_of)} departments with a seat")
    admin1 = json.loads((SITE / "admin1" / "CMR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CMR.units.json").read_text())
    records, report = build(tables_, seat_of, admin1, admin2)
    for line in report:
        log(line)
    write_json(PROCESSED / OUT, records)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} regions and "
        f"{sum(r['level'] == 'admin2' for r in records)} departments written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
