#!/usr/bin/env python3
"""Senegal -- the 2023 census's regional reports: median age and language by region.

ANSD published one *Rapport de présentation des résultats* of the fifth census
(RGPH-5, 2023) for each of the fourteen regions (April 2026). Each gives, for
its region:

* the mean and median age by sex and by urban and rural residence, in whole
  years (*Age moyen et âge médian de la population selon le sexe et le milieu
  de résidence*); the region's median is the table's last figure;
* the principal language usually spoken by residents aged 3 and over, by sex
  (*Répartition de la population résidente de 3 ans ou plus par principale
  langue couramment parlée selon le sexe*), in counts and percentages, or in
  percentages alone;
* each department's population in three broad age groups only (under 15,
  15-64, 65 and over), from which no median can be taken: each department
  says so.

Written: every region's median age and language, and a stated reason for the
median age of every department drawn in a region whose report was read. The
census's language table is newer than, and outranks, the survey's shares the
regions showed.

**Checks before anything is written.** The median is a whole number of years
between 14 and 35, the last of the six or nine figures of its row; a language
table's rows make its total row (counts: men and women make each row's total;
percentages: the column makes 100 within rounding); the department table holds
the three broad groups and no five-year ones.

Usage:
    python -m scripts.fetch_census.senegal_regional_reports
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

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob  # noqa: E402

BASE = "https://www.ansd.sn/sites/default/files/recensements/rapport/"
PAGE = "https://www.ansd.sn/rapports/rgph-5-2023"
REPORTS = {
    "Dakar": "RGPH-5_DAKAR_Avril%202026.pdf",
    "Diourbel": "RGPH-5%20RR_DIOURBEL_27112025_Version%20Formate%CC%81%20ok_Avril%202026.pdf",
    "Fatick": "RGPH-5%20RR_FATICK_Avril%202026_0.pdf",
    "Kaffrine": "RGPH-5%20RR_KAFFRINE_Avril%202026.pdf",
    "Kaolack": "RGPH-5%20RR_KAOLACK_27112025_Version%20Formate%CC%81%20ok_Avril%202026_0.pdf",
    "Kédougou": "RGPH-5%20RR_KEDOUGOU_Avril%202026.pdf",
    "Kolda": "RGPH-5%20RR_KOLDA_27112025_Version%20Formate%CC%81%20ok_Avril%202026_0.pdf",
    "Louga": "RGPH-5%20RR_LOUGA_27112025_Version%20Formate%CC%81%20ok_Avril%202026.pdf",
    "Matam": "RGPH-5%20RR_MATAM_27112025_Version%20Formate%CC%81%20ok_Avril%202026_0.pdf",
    "Saint-Louis": "RGPH-5%20RR_SAINT_LOUIS_Avril%202026.pdf",
    "Sédhiou": "RGPH-5%20RR_SEDHIOU_27112025_Version%20Formate%CC%81%20ok_Avril%202026.pdf",
    "Tambacounda": "RGPH-5%20RR_TAMBACOUNDA_Avril%202026_0.pdf",
    "Thiès": "RGPH-5%20RR_THIES_Avril%202026.pdf",
    "Ziguinchor": "RGPH-5_ZIGUINCHOR_Avril%202026_0.pdf",
}
PUBLISHER = "Agence Nationale de la Statistique et de la Démographie (ANSD)"
YEAR = 2023
LICENCE = "ANSD publication (reuse with attribution)"
OUT = "senegal_regional_reports.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The census's language labels (folded) -> the names the map uses elsewhere.
LANGUAGES = {
    "wolof": "Wolof", "pulaar": "Pulaar", "sereer": "Serer", "joola": "Jola",
    "mandienka": "Mandinka", "mandinka": "Mandinka", "mandingue": "Mandinka",
    "soninke": "Soninke", "hasaniyamaure": "Hassaniya", "hassaniyamaure": "Hassaniya",
    "hasaniya": "Hassaniya", "balant": "Balanta", "mankaan": "Mankanya",
    "manjaku": "Manjak", "menik": "Bedik", "oniyan": "Bassari", "gunuun": "Guñuun",
    "kanjad": "Jaad", "jalunga": "Yalunka", "bayot": "Bayot", "womey": "Wamey",
    "saafisaafi": "Saafi-Saafi", "noon": "Noon", "laalaa": "Lehar", "ndut": "Ndut",
    "paloor": "Palor", "badiaranke": "Badiaranke", "baynunk": "Bainouk",
    "francais": "French", "tourka": "Tourka", "languesetrangere": "Other foreign languages",
    "autreslanguesafricaines": "Other African languages",
    "languesetrangeres": "Other foreign languages",
    "autreslanguesetrangeresnonafricaines": "Other non-African foreign languages",
    "langagedessignessourdmuet": "Sign language", "languedessignes": "Sign language",
    "nd": "Not stated", "nondeclare": "Not stated",
}
# A count, its thousands set apart by a space of any width (Matam's report
# uses the thin space), and a share, printed with or without its decimal.
N = r"\d{1,3}(?:[    ]\d{3})+|\d+"
P = r"\d{1,3},\d+|\d{1,3}"
ROW6 = re.compile(rf"^(?P<label>\D+?)\s+(?P<m>{N})\s+(?P<mp>{P})\s+(?P<f>{N})\s+(?P<fp>{P})"
                  rf"\s+(?P<t>{N})\s+(?P<tp>{P})\s*$")
ROW3 = re.compile(rf"^(?P<label>\D+?)\s+(?P<mp>{P})\s+(?P<fp>{P})\s+(?P<tp>{P})\s*$")
TITLE_LANG = re.compile(r"(?i)principale\s+langue\s+couramment")
TITLE_MEDIAN = re.compile(r"(?i)[aâ]ges?\s+moyens?\s+et\s+(?:[aâ]ge\s+)?m[ée]dian")
MEDIAN_ROW = re.compile(r"(?i)^\s*(?:[aâ]ge\s+)?m[ée]dian(?:e)?\s*(?:\(ans\))?\s+"
                        r"((?:\d+(?:,\d+)?\s*)+)$")
TABLE_NO = re.compile(r"(?i)tableau\s*([IVX]+\s*[-\u2013\u2011.]\s*\d+|\d+(?:\.\d+)+)")


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def integer(text: str) -> int:
    return int(re.sub(r"\D", "", text))


def percent(text: str) -> float:
    return float(text.replace(",", "."))


def is_contents(line: str) -> bool:
    """A line of a table of contents: dot or underscore leaders."""
    return "__" in line or "...." in line or ". . ." in line


# The words of a table's title and header lines, which are not a row's label.
HEADER = re.compile(r"(?i)^(sexe|masculin|f[ée]minin|effectif|source|principale\s+langue)|"
                    r"selon\s+le|tableau|r[ée]partition|couramment\s+parl")
NUMBERS_ONLY = re.compile(rf"^(?:{N})\s+(?:{P})\s+(?:{N})\s+(?:{P})\s+(?:{N})\s+(?:{P})\s*$|"
                          rf"^(?:{P})\s+(?:{P})\s+(?:{P})\s*$")
TOTALS = {"total", "ensemble"}


def title_at(lines: list[str], i: int, title: re.Pattern) -> bool:
    """A table's title starts on line ``i`` (it may run onto the next line), and
    the line is not one of the contents' entries."""
    here = lines[i]
    after = lines[i + 1] if i + 1 < len(lines) else ""
    return ("Tableau" in here and bool(title.search(here + " " + after))
            and not is_contents(here) and not is_contents(after))


def table_number(line: str) -> str:
    m = TABLE_NO.search(line)
    return ("Tableau " + re.sub(r"[\u2013\u2011]", "-", re.sub(r"\s+", "", m.group(1)))) if m else ""


def parse_median(text: str) -> tuple[int, str]:
    """(the region's median age, the table's number)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not title_at(lines, i, TITLE_MEDIAN):
            continue
        for row in lines[i + 1:i + 14]:
            m = MEDIAN_ROW.match(row)
            if m:
                values = ages(m.group(1))
                if len(values) not in (3, 6, 9) or not 14 <= values[-1] <= 35:
                    raise SystemExit(f"senegal_regional_reports: the median row reads {values}")
                return values[-1], table_number(line)
    # A title the text layer broke up: the table's own row, which no other
    # table of these reports has, is the table.
    rows = [line for line in lines if MEDIAN_ROW.match(line)]
    if rows:
        values = ages(MEDIAN_ROW.match(rows[0]).group(1))
        if len(values) in (3, 6, 9) and 14 <= values[-1] <= 35:
            return values[-1], ""
    raise SystemExit("senegal_regional_reports: no median-age table")


def ages(cells: str) -> list[int | float]:
    """A median row's figures: whole years, or with a decimal ("17,0")."""
    out: list[int | float] = []
    for cell in cells.split():
        value = float(cell.replace(",", "."))
        out.append(int(value) if value.is_integer() else value)
    return out


def language_label(label: str) -> str:
    key = fold(label)
    if key in LANGUAGES:
        return LANGUAGES[key]
    return re.sub(r"\s+", " ", label).strip()


def parse_language(text: str) -> tuple[dict[str, float], str, str]:
    """({language: count or percentage}, "count" or "pct", the table's number)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not title_at(lines, i, TITLE_LANG):
            continue
        rows: dict[str, float] = {}
        kind = ""
        total: float | None = None
        carry = ""
        for row in lines[i + 1:i + 60]:
            row = row.strip()
            if not row or HEADER.search(row):
                if row.lower().startswith("source") and rows:
                    break
                # The title's and the header's words are not a label's start.
                carry = ""
                continue
            # A label that wraps puts its figures on a line of their own:
            # "Langage des signes" / "(Sourd-Muet)" / "2813 0,7 2894 0,7 5707 0,7".
            if carry and NUMBERS_ONLY.match(row):
                row, carry = f"{carry} {row}", ""
            m6, m3 = ROW6.match(row), ROW3.match(row)
            m = m6 or m3
            if not m:
                if not re.search(r"\d", row):
                    carry = (carry + " " + row).strip()
                continue
            label = (carry + " " + m.group("label")).strip()
            carry = ""
            if m6:
                # The census's counts are weighted for its coverage survey and
                # each cell is rounded on its own, so men and women may miss
                # the row's total by a person or two (Dakar's Hassaniya:
                # 568 + 447 against 1,014).
                men, women, both = (integer(m6.group(k)) for k in ("m", "f", "t"))
                if abs(men + women - both) > 2:
                    raise SystemExit(f"senegal_regional_reports: {label!r}: {men:,} + "
                                     f"{women:,} is not {both:,}")
                value, this = float(both), "count"
            else:
                value, this = percent(m3.group("tp")), "pct"
            if kind and this != kind:
                raise SystemExit(f"senegal_regional_reports: {label!r} mixes counts and shares")
            kind = this
            if fold(label) in TOTALS:
                total = value
                break
            name = language_label(label)
            rows[name] = rows.get(name, 0.0) + value
        if not rows or total is None:
            raise SystemExit("senegal_regional_reports: the language table has no total row")
        made = sum(rows.values())
        if kind == "count" and abs(made - total) > 2 * len(rows):
            raise SystemExit(f"senegal_regional_reports: languages make {made:,.0f}, "
                             f"not {total:,.0f}")
        if kind == "pct" and abs(made - 100.0) > 1.0:
            raise SystemExit(f"senegal_regional_reports: language shares make {made:.1f}")
        return rows, kind, table_number(line)
    raise SystemExit("senegal_regional_reports: no language table")


def departments_in_broad_groups(text: str) -> bool:
    """The report's age table by department holds the three broad groups only:
    the table itself, from its title to its source line (a chart or the
    region's five-year table may share its page)."""
    for title in re.finditer(r"(?i)groupes?\s+d.[aâ]ges?\s+(?:quinquennaux\s+)?selon\s+le\s+"
                             r"d[ée]partement", text):
        rest = text[title.end():title.end() + 2500]
        if is_contents(rest.split("\n", 1)[0]) or re.match(r"[^\n]*\.{4,}", rest):
            continue                       # the list of tables
        end = re.search(r"(?i)\bsource\s*:", rest)
        table = rest[:end.start()] if end else rest[:1500]
        if re.search(r"(?i)moins\s+de\s*\n?\s*15", table) and \
                re.search(r"(?i)65\s+ans\s+et\s+plus", table):
            return not re.search(r"(?im)^\s*(?:5\s*-\s*9|10\s*-\s*14)\s", table)
    return False


def read(region: str) -> dict[str, Any]:
    from pypdf import PdfReader

    url = BASE + REPORTS[region]
    blob = fetch_blob(url, aia=True)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"senegal_regional_reports: {url} is not a PDF: {blob[:60]!r}")
    log(f"  {region}: read {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    reader = PdfReader(io.BytesIO(blob))
    # The state and structure chapter is within the first 80 pages of every
    # report; reading the rest (up to 200 pages, slowly) ran the job out of time.
    text = "\f".join((page.extract_text() or "") for page in reader.pages[:80])
    return parsed(region, text, url)


def parsed(region: str, text: str, url: str) -> dict[str, Any]:
    """What the report gives; a table that cannot be read is left out, and why is
    kept in ``problems`` (with the lines around it, for the log)."""
    out: dict[str, Any] = {"region": region, "url": url, "median": None, "median_table": "",
                           "language": {}, "kind": "", "language_table": "",
                           "broad": departments_in_broad_groups(text), "problems": []}
    try:
        out["median"], out["median_table"] = parse_median(text)
    except SystemExit as err:
        out["problems"].append((str(err), context(text, TITLE_MEDIAN, r"(?i)m[ée]dian")))
    try:
        out["language"], out["kind"], out["language_table"] = parse_language(text)
    except SystemExit as err:
        out["problems"].append((str(err), context(text, TITLE_LANG, r"(?i)couramment")))
    if not out["broad"]:
        out["problems"].append(("the department age table is not the three broad groups",
                                context(text, re.compile(r"(?i)selon\s+le\s+d[ée]partement"),
                                        r"(?i)d[ée]partement")))
    return out


def context(text: str, title: re.Pattern, pattern: str, after: int = 45,
            limit: int = 140) -> list[str]:
    """For the log: the lines below each title of the table (not the list of
    tables), or else below each line matching ``pattern``."""
    lines = text.splitlines()
    starts = [i for i in range(len(lines)) if title_at(lines, i, title)]
    if not starts:
        starts = [i for i, line in enumerate(lines) if re.search(pattern, line)]
        after = 12
    out: list[str] = []
    for i in starts:
        out.extend(f"    | {x}" for x in lines[i:i + after])
        out.append("    | ---")
        if len(out) >= limit:
            break
    return out[:limit]


def source_name(region: str, table: str) -> str:
    return (f"{PUBLISHER}, Cinquième Recensement Général de la Population et de l'Habitat "
            f"(RGPH-5) 2023, Rapport de présentation des résultats, Région de {region}"
            + (f", {table}" if table else ""))


def build(reports: list[dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    by_fold = {fold(r["region"]): r for r in reports}
    records: list[dict[str, Any]] = []
    report: list[str] = []
    bound: dict[str, dict[str, Any]] = {}
    for shape in admin1:
        rr = by_fold.get(fold(shape["name"]))
        if rr is None:
            report.append(f"region polygon {shape['name']!r}: no report read")
            continue
        bound[shape["id"]] = rr
        region = rr["region"]
        fields: dict[str, Any] = {}
        sources = []
        if rr["median"] is not None:
            median_source = source_name(region, rr["median_table"])
            fields.update(
                median_age=measure(rr["median"], unit="years", year=YEAR, source=median_source),
                median_age_note=("The 2023 census's median age of the region's residents, "
                                 "which its regional report gives in whole years."))
            sources.append({"field": "median_age", "name": median_source, "url": rr["url"],
                            "page": PAGE, "license": LICENCE, "year": YEAR})
        if rr["language"]:
            language_source = source_name(region, rr["language_table"])
            language = shares(rr["language"])
            if rr["kind"] == "pct":
                for row in language:
                    row.pop("count", None)
            fields.update(
                language=language, language_year=YEAR,
                language_note=("The principal language usually spoken by residents aged 3 and "
                               "over, as the 2023 census tabulates it for the region."))
            sources.append({"field": "language", "name": language_source, "url": rr["url"],
                            "page": PAGE, "license": LICENCE, "year": YEAR})
        if not fields:
            report.append(f"region polygon {shape['name']!r}: nothing read from its report")
            continue
        records.append(record(
            f"SEN-RGPH5-RR-{fold(region)}", shape["name"], level="admin1", parent="SEN",
            country="SEN", match_by="shape_id", shape_id=shape["id"], sources=sources,
            **fields))
    for shape in admin2:
        rr = bound.get(shape.get("parent"))
        if rr is None:
            continue
        if not rr["broad"]:
            report.append(f"{shape['name']!r}: the {rr['region']} report's department ages "
                          "are not the three broad groups")
            continue
        records.append(record(
            f"SEN-RGPH5-RR-dept-{fold(shape['name'])}", shape["name"], level="admin2",
            parent="SEN", country="SEN", match_by="shape_id", shape_id=shape["id"],
            median_age=gap(NOT_AVAILABLE, (
                f"The 2023 census's report for the {rr['region']} region gives each "
                "department's population in three broad age groups only (under 15, 15 to 64, "
                "65 and over), and no median age can be taken from them; no other table of "
                "the census gives a department's ages.")),
            sources=[{"field": "median_age", "name": source_name(rr["region"], ""),
                      "url": rr["url"], "page": PAGE, "license": LICENCE, "year": YEAR}]))
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    reports = []
    for region in REPORTS:
        rr = read(region)
        top = sorted(rr["language"].items(), key=lambda kv: -kv[1])[:4]
        log(f"  {region}: median {rr['median']} ({rr['median_table']}); language "
            f"{rr['kind']} ({rr['language_table']}): "
            + ", ".join(f"{k} {v:,.1f}" for k, v in top)
            + f"; departments in broad groups: {rr['broad']}")
        for problem, lines in rr["problems"]:
            log(f"  {region}: {problem}")
            for line in lines:
                log(line)
        reports.append(rr)
    admin1 = json.loads((SITE / "admin1" / "SEN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SEN.units.json").read_text())
    records, report = build(reports, admin1, admin2)
    for line in report:
        log("  " + line)
    n1 = sum(1 for r in records if r["level"] == "admin1")
    n2 = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {n1} regions and {n2} departments written")
    if n1 == 0:
        raise SystemExit("senegal_regional_reports: nothing read from any report")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
