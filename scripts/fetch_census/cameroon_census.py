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

**2025.** OCHA's Common Operational Dataset for Cameroon (cod-ps-cmr) gives
the ten regions' projected population for 2025 (cmr_admpop_adm1_2025) and the
two metropolises' (cmr_admpop_met_2025: the city of Douala, which is Wouri,
and the city of Yaoundé, which is Mfoundi, bound by their P-codes CM005004
and CM002007), with five-year age groups by sex. They are written to
cameroon_projection.json: the populations, which as the newer figures stand
in front of the 2005 counts, and for Wouri and Mfoundi a median age taken
from their own age groups, where those are not their region's (the copy
test of cod_ps_age), to fill the median the census does not give. No sex
ratio is written from them: the census's stands.

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
RATIO = re.compile(r"^(?:\d+(?:[,.]\d+)?|-|#\S+)$")
DIGITS = re.compile(r"^\d+$")
DEPARTMENT = re.compile(r"^d[ée]partement\s+(?:du|de\s+la|de\s+l['’]|des|de)\s*", re.I)
PROVINCE = re.compile(r"^province\s+(?:du|de\s+la|de\s+l['’]|des|de)\s*", re.I)
HEADER = re.compile(r"^(tableau|circonscription|population|administrative|r[ée]partition|sexe$|"
                    r"rapport|d[ée]partement\s+et\s+par|arrondissement/district|l['’]?\s*$)", re.I)

# The table's department names the map spells otherwise (folded keys, '&' read as 'et').
DRAWN_AS = {"nyongetsoo": "Nyong-et-So", "kadey": "Kadei", "ngoketundjia": "Ngo-ketunjia",
            "koupeetmanengouba": "Kupe-Manenguba"}

AGE_GAP = ("BUCREP's tables of the 2005 census by department count each department's residents "
           "by sex and by urban or rural residence, not by age, so the census gives no median "
           "age for the department.")

# OCHA's 2025 tables (cod-ps-cmr): the regions, and the two metropolises.
OCHA_DATASET = "https://data.humdata.org/dataset/e8db7923-6cd2-4974-ad57-14a157978cfd"
OCHA_ADM1 = (OCHA_DATASET + "/resource/09be4b94-28bb-4921-a7e0-19967c178230/download/"
             "copy-of-cmr_admpop_adm1_2025.csv")
OCHA_MET = (OCHA_DATASET + "/resource/c23633c8-f033-44bd-b43b-e8a1bc487784/download/"
            "copy-of-cmr_admpop_met_2025.csv")
OCHA_YEAR = 2025
OCHA = (f"OCHA, Common Operational Dataset -- population statistics (cod-ps-cmr), reference "
        f"year {OCHA_YEAR}")
OCHA_URL = "https://data.humdata.org/dataset/cod-ps-cmr"
OCHA_LICENCE = "Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO)"
PROJECTION_OUT = "cameroon_projection.json"
# The metropolises by P-code: the department each is, as the table's ADM2_FR names it.
METROPOLISES = {"CM005004": "Wouri", "CM002007": "Mfoundi"}
# OCHA's region names (ADM1_FR, ADM1_EN) -> the map's first-level names.
OCHA_REGIONS = {**PROVINCES, "adamawa": "Adamaoua", "east": "East", "farnorth": "Far North",
                "north": "North", "northwest": "North-West", "west": "West", "south": "South",
                "southwest": "South-West"}


def split3(groups: list[str]) -> list[tuple[int, int, int]]:
    """Every way to read digit groups as total, men and women with men + women = total.

    A figure is a leading group followed by groups of exactly three digits:
    the table mostly prints 10465 but sometimes 10 465.
    """
    out = []
    n = len(groups)
    for i in range(1, n - 1):
        for j in range(i + 1, n):
            parts = [groups[:i], groups[i:j], groups[j:]]
            if any(any(len(g) != 3 for g in p[1:]) for p in parts):
                continue
            t, m, f = (int("".join(p)) for p in parts)
            if m + f == t:
                out.append((t, m, f))
    return out


def figures(line: str) -> tuple[str, tuple[int, int, int]] | None:
    """(label, (total, men, women)) for a line ending in figures and a ratio.

    The label keeps as many of its own trailing numbers as it can ("YAOUNDE 3",
    "DOUALA 1"): the fewest digit groups that read as three figures adding up
    are the figures.
    """
    tokens = line.split()
    if len(tokens) < 4 or not RATIO.match(tokens[-1]):
        return None
    body = tokens[:-1]
    k = len(body)
    while k > 0 and DIGITS.match(body[k - 1]):
        k -= 1
    groups = body[k:]
    for start in range(len(groups) - 3, -1, -1):
        found = split3(groups[start:])
        if len(found) == 1:
            return " ".join(body[:k] + groups[:start]), found[0]
    return None


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
        read = figures(line)
        if read:
            label, (t, m, f) = read
            if not label and before:
                label, open_end = before, True
            else:
                open_end = False
            out.append([label, t, m, f])
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
                if len(title) < 200 and not figures(line) and not current:
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


def spelled(name: str) -> str:
    """A department as the table names it, '&' written out: 'MBAM & KIM' -> 'Mbam Et Kim'."""
    return re.sub(r"\s*&\s*", " et ", name).title()


def seat_key(name: str) -> str:
    """A name with its 'et' dropped, so Koupé-Manengouba meets Koupe & Manengouba."""
    return fold(re.sub(r"(?i)[\s-]+et[\s-]+", " ", name))


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
    cite_region = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "year": YEAR,
                    "license": LICENCE}]
    # A department's median-age reason rests on the same table.
    cite = [{**cite_region[0], "field": "population/sex_ratio/median_age note"}]
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
            country="CMR", match_by="shape_id", shape_id=poly["id"], sources=cite_region,
            **fields(t, m, f, f"The resident population of the {region} region at the 2005 "
                              f"census, its departments added up.")))
        report.append(f"  {region}: {t:,} ({m:,} men, {f:,} women), "
                      f"{len(s['departments'])} departments")
        for dep, (figures, _arrs) in s["departments"].items():
            code = f"{key}:{dep}"
            departments[code] = (spelled(dep), region)
            counts[code] = figures
    aliases = {name: DRAWN_AS[fold(name)] for name, _r in departments.values()
               if fold(name) in DRAWN_AS}
    bound, missing = bind(departments, admin2, parents, aliases)
    if missing:
        raise SystemExit("cameroon_census: departments with no polygon: " + ", ".join(missing))
    shapes = {u["id"]: u for u in admin2}
    unbound = sorted(u["name"] for u in admin2 if u["id"] not in set(bound.values()))
    if unbound:
        raise SystemExit("cameroon_census: polygons no department reached: " + ", ".join(unbound))
    seat_keys = {seat_key(k): v for k, v in seat_of.items()}
    for code, sid in sorted(bound.items(), key=lambda kv: kv[0]):
        t, m, f = counts[code]
        shape = shapes[sid]
        dep_name = departments[code][0]
        extra: dict[str, Any] = {"median_age": gap(NOT_AVAILABLE, AGE_GAP)}
        sources = list(cite)
        seat = seat_keys.get(seat_key(dep_name)) or seat_keys.get(seat_key(shape["name"]))
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


def projection(adm1_rows: list[dict[str, str]], met_rows: list[dict[str, str]],
               admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
               ) -> tuple[list[dict[str, Any]], list[str]]:
    """OCHA's 2025 regions and metropolises: populations, and the metropolises'
    medians where their age groups are not their region's."""
    from .cod_ps_age import age_columns, same_structure, unit_figures  # noqa: PLC0415
    report: list[str] = []
    records: list[dict[str, Any]] = []
    cite = [{"field": "population", "name": OCHA, "url": OCHA_URL, "year": OCHA_YEAR,
             "license": OCHA_LICENCE}]
    first = {u["name"]: u for u in admin1}
    cols1 = age_columns(list(adm1_rows[0].keys())) if adm1_rows else None
    regions: dict[str, Any] = {}
    total = 0
    for row in adm1_rows:
        name = (OCHA_REGIONS.get(fold(row.get("ADM1_FR") or ""))
                or OCHA_REGIONS.get(fold(row.get("ADM1_EN") or "")))
        poly = first.get(name or "")
        if poly is None:
            raise SystemExit(f"cameroon_census: OCHA's region {row.get('ADM1_FR')!r} has no polygon")
        people = int(float(row["T_TL"]))
        total += people
        regions[str(row.get("ADM1_PCODE") or "").strip()] = (
            unit_figures(row, cols1)[0] if cols1 else None)
        records.append(record(
            f"CMR-CODPS{OCHA_YEAR}-{poly['id']}", poly["name"], level="admin1", parent="CMR",
            country="CMR", match_by="shape_id", shape_id=poly["id"], sources=cite,
            population=measure(people, year=OCHA_YEAR, source=OCHA),
            population_note=(f"OCHA's projected population of the {name} region for "
                             f"{OCHA_YEAR}.")))
        report.append(f"  2025: {name}: {people:,}")
    if len(records) != 10 or not 20_000_000 < total < 45_000_000:
        raise SystemExit(f"cameroon_census: OCHA's 2025 table: {len(records)} regions, {total:,}")
    report.append(f"  2025: the regions make {total:,}")
    by_name = {fold(u["name"]): u for u in admin2}
    cols2 = age_columns(list(met_rows[0].keys())) if met_rows else None
    for row in met_rows:
        code = str(row.get("ADM2_PCODE") or "").strip()
        dep = METROPOLISES.get(code)
        if dep is None or fold(row.get("ADM2_FR") or "") != fold(dep):
            report.append(f"  2025: metropolis {code} {row.get('ADM2_FR')!r} not bound")
            continue
        poly = by_name.get(fold(dep))
        if poly is None:
            raise SystemExit(f"cameroon_census: no polygon for {dep}")
        city = re.sub(r"(?i)^ville\s+de\s+", "", str(row.get("Metropolis") or dep)).strip()
        people = int(float(row["T_TL"]))
        fields: dict[str, Any] = {
            "population": measure(people, year=OCHA_YEAR, source=OCHA),
            "population_note": (f"OCHA's projected population of the city of {city} for "
                                f"{OCHA_YEAR}; the city is the {dep} department.")}
        found = unit_figures(row, cols2)[0] if cols2 else None
        region = regions.get(str(row.get("ADM1_PCODE") or "").strip())
        sources = list(cite)
        if found and region and not same_structure(found["groups"], region["groups"]):
            fields["median_age"] = {"value": found["median"], "unit": "years",
                                    "year": OCHA_YEAR, "source": OCHA}
            fields["median_age_note"] = (
                f"Interpolated within the five-year age group that holds the middle person, "
                f"from OCHA's projected population of the city of {city} by age for "
                f"{OCHA_YEAR}: a projection, not a count.")
            sources = [{**cite[0], "field": "population/median_age"}]
            report.append(f"  2025: {dep} ({city}): {people:,}, median {found['median']}")
        else:
            why = "its region's age proportions" if found else "no ages"
            report.append(f"  2025: {dep} ({city}): {people:,}; no median ({why})")
        records.append(record(
            f"CMR-CODPS{OCHA_YEAR}-{poly['id']}", poly["name"], level="admin2", parent="CMR",
            country="CMR", match_by="shape_id", shape_id=poly["id"], sources=sources, **fields))
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    import csv                                      # noqa: PLC0415
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

    def csv_rows(url: str) -> list[dict[str, str]]:
        text = http_get(url, binary=True, cache=False, timeout=180).decode("utf-8-sig", "replace")
        return [{(k or "").strip(): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]

    projected, lines = projection(csv_rows(OCHA_ADM1), csv_rows(OCHA_MET), admin1, admin2)
    for line in lines:
        log(line)
    write_json(PROCESSED / PROJECTION_OUT, projected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
