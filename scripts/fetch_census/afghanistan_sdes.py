#!/usr/bin/env python3
"""Afghanistan -- median age by district from the Socio-Demographic and Economic Survey.

Afghanistan has had no census since the abandoned count of 1979, and the
statistics office's yearly population estimates give age for the nation alone
(see ``afghanistan_estimates.py``). What it did measure, province by province
from 2011 to 2016, is the **Socio-Demographic and Economic Survey (SDES)**:
the Central Statistics Organization (now the National Statistics and
Information Authority), with UNFPA, listed and interviewed *every household*
of a province -- a complete enumeration, not a sample -- and published a
report for each, whose Table 3 is "Median Age in Years of the Population by
District", for both sexes, males and females. Twelve provinces were surveyed
(``SURVEYED``); the reports read here are the office's own English editions,
as the Internet Archive holds them (``REPORTS``):

    Bamyan     September 2011   the whole province, 7 districts
    Kapisa     September 2014   5 of its 7 districts (Tagab and Alasay not covered)
    Parwan     September 2014   the whole province, 10 districts
    Balkh      December 2015    the whole province, 15 districts
    Herat      March 2016       the city and 12 of its 15 districts (Gulran,
                                Shindand and Fersi not covered, for insecurity)
    Nimroz     May 2016         4 of its 5 districts (Khash Rod not covered)
    Baghlan    December 2016    the whole province, 15 districts

The other five reports (Ghor, Daykundi, Kabul, Samangan, Takhar) are archived
only cut off (``UNREAD``), and their districts keep a gap that says so.

**The office publishes the median, and the median is what is written** --
its own figure for the district, not one recomputed here. Each table is held
to itself before anything is written: its first row is the province, every
other row is a district the reader knows for that province (``REPORTS``, the
report's spelling against the code the office's 1396 estimates give the
district), no district twice and none missing, every figure between 5 and
40 years, the both-sexes median within a year of its male and female
medians, and the province's median between the lowest and the highest of its
districts' -- as the median of a whole always is.

**Which polygon.** A row is bound to the drawn district through the office's
own district code, the one ``afghanistan_estimates.CROSSWALK`` binds to each
of the 398 drawn shapes -- so a district the boundary file draws in another
province (Mahmudi Raqi, counted in Kapisa and drawn in Parwan) takes its own
row from the report of the province that counted it. Some drawn districts are
an original district *and* temporary districts cut from it later
(``TEMPORARY_PARENT``): a report of the whole province that lists no
temporary district counted it inside its original (Bamyan's Yakawlang,
surveyed in 2011, holds the later Yakawlang No. 2), so its row is the
polygon's; a report that lists one apart, or that did not cover the whole
province, is not written for the polygon.

**Provinces** take the report's provincial median only where the report
covered the whole province and the boundary file draws the province as the
office counts it (``afghanistan_estimates.drawn_apart``): Bamyan and
Baghlan. Kapisa, Herat and Nimroz were not covered whole; Parwan and Balkh
are drawn otherwise than counted. Each says why.

This file writes the median age -- a figure or the reason there is none -- of
every drawn district the office counts in a province whose report is read,
and of those provinces; ``afghanistan_estimates`` leaves the field to it
there and writes the reason (``age_gap``) everywhere else.

Usage:
    python -m scripts.fetch_census.afghanistan_sdes
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any, NamedTuple

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .south_asia_common import load_units

OUT = "afghanistan_sdes.json"
SOURCE = ("Central Statistics Organization of Afghanistan (now the National Statistics "
          "and Information Authority) with UNFPA, Socio-Demographic and Economic Survey "
          "(SDES), provincial report, Table 3: median age in years of the population "
          "by district")
LICENCE = "Afghanistan Central Statistics Organization publication"
CSO = "https://web.archive.org/web/{stamp}id_/http://cso.gov.af/Content/files/{path}"


class Report(NamedTuple):
    province: str                 # the 1396 tables' province code
    name: str                     # the report's own first row
    url: str                      # the archived English report
    when: str                     # the survey's reference month, as printed
    year: int
    rows: dict[str, str]          # the report's district label -> 1396 code
    whole: bool                   # every district of the province covered
    coverage: str = ""            # what the report says it did not cover


REPORTS: list[Report] = [
    Report("10", "Bamiyan",
           CSO.format(stamp="20170511164651", path=(
               "Afghanistan%20SDES%20Bamiyan%20Final%20Report%20-%2024%20April%202013.pdf")),
           "September 2011", 2011,
           {"Provincial Center": "1001", "Shibar": "1002", "Saighan": "1003",
            "Kahmard": "1004", "Yakawlang": "1005", "Panjab": "1006", "Waras": "1007"},
           whole=True),
    Report("02", "Kapisa",
           CSO.format(stamp="20170511124634", path="SDES%20Kapisa%20Report%20-%20Final.pdf"),
           "September 2014", 2014,
           {"Mahmudi Raqi": "0201", "Hissa-e-Duwumi Kohistan": "0202", "Koh Band": "0203",
            "Hissa-e-Awali Kohistan": "0204", "Nijrab": "0205"},
           whole=False,
           coverage="Its tables cover five of the province's seven districts, "
                    "and not Tagab or Alasay."),
    Report("03", "Parwan",
           CSO.format(stamp="20170511131324", path="SDES%20Parwan%20Report%20-%20Final.pdf"),
           "September 2014", 2014,
           {"Charikar": "0301", "Bagram": "0302", "Shinwari": "0303", "Sayid Khail": "0304",
            "Jabulussaraj": "0305", "Salang": "0306", "Syahgirdi Ghorband": "0307",
            "Kohi Safi": "0308", "Surkhi Parsa": "0309", "Shaykh Ali": "0310"},
           whole=True),
    Report("21", "Balkh",
           CSO.format(stamp="20170511124330", path="SDES/Balkh%20FR%20Final2.pdf"),
           "December 2015", 2015,
           {"Mazar-E-Sharif": "2101", "Nahr-E-Shahi": "2102", "Dehdadi": "2103",
            "Char Kent": "2104", "Marmul": "2105", "Balkh": "2106", "Sholgara": "2107",
            "Chimtal": "2108", "Dawlat Abad": "2109", "Khulm": "2110", "Char Bolak": "2111",
            "Shortepa": "2112", "Kaldar": "2113", "Kishendeh": "2114", "Zari": "2115"},
           whole=True),
    Report("32", "Herat",
           CSO.format(stamp="20170511124125", path="SDES/Highlight%20Herat%20Fr%204%20March.pdf"),
           "March 2016", 2016,
           {"Herat City": "3201", "Enjil": "3202", "Nizam-E-Shahid": "3203", "Karrukh": "3204",
            "Zendajan": "3205", "Pashtun Zarghun": "3206", "Kushk (Rubat-E-Sangi)": "3207",
            "Adraskan": "3209", "Kushk-E-Kuhna": "3210", "Ghoryan": "3211", "Obe": "3212",
            "Kohsan": "3213", "Chisht-E-Sharif": "3216"},
           whole=False,
           coverage="The report says: \"Due to security problems, the districts of "
                    "Gulran, Shindand and Fersi were not covered.\""),
    Report("34", "Nimroz",
           CSO.format(stamp="20170511124002",
                      path="SDES/NImroz%20FR%203%20copy%20April%2012%20%20Final.pdf"),
           "May 2016", 2016,
           {"Zaranj": "3401", "Kang": "3402", "Asl-E-Chakhansur": "3403",
            "Char Burjak": "3404"},
           whole=False,
           coverage="Its tables cover four of the province's five districts, and not "
                    "Khash Rod."),
    Report("09", "Baghlan",
           CSO.format(stamp="20181113161729", path=(
               "Surveys/SDES/Baghlan%20SDES%20Report%20English_AM_21082017_Print%20Quality(1).pdf")),
           "December 2016", 2016,
           {"Pul-E-Khumri": "0901", "Dahana-E-Ghuri": "0902", "Dushi": "0903",
            "Nahreen": "0904", "Baghlan-E-Jadeed": "0905", "Khinjan": "0906",
            "Andarab": "0907", "Deh Salah": "0908", "Jalga": "0909", "Burka": "0910",
            "Tala Wa Barfak": "0911", "Pul-E-Hisar": "0912", "Khost Wa Firing": "0913",
            "Gozargah-E-Noor": "0914", "Firing Wa Gharu": "0915"},
           whole=True),
]

# Every province the survey reached, in its order, with the year: the reports'
# own "Text Box 1" lists them, and Herat's calls itself the tenth.
SURVEYED: dict[str, tuple[str, int]] = {
    "10": ("Bamyan", 2011), "23": ("Ghor", 2012), "24": ("Daykundi", 2012),
    "01": ("Kabul", 2013), "02": ("Kapisa", 2014), "03": ("Parwan", 2014),
    "21": ("Balkh", 2015), "18": ("Takhar", 2015), "20": ("Samangan", 2015),
    "32": ("Herat", 2016), "34": ("Nimroz", 2016), "09": ("Baghlan", 2016),
}
# Surveyed, but every archived copy of the English report stops at exactly
# 1 MiB (1,048,576 bytes) and does not open.
UNREAD = {"23", "24", "01", "18", "20"}
READ = {report.province for report in REPORTS}

LOW, HIGH = 5.0, 40.0
FIGURE = re.compile(r"\d{1,2}\.\d")
TITLE = re.compile(r"(?i)median\s+age\s+in\s+years\s+of\s+(?:the\s+)?population\s+by\s+district")
NO_CENSUS = ("Afghanistan has had no census since 1979, and the statistics office's "
             "yearly estimates give age for the whole country only (the 1396 release's "
             "age workbook, \"گروپ سنین\", has five-year groups by sex for the rural, "
             "urban and nomadic population of Afghanistan and no province or district "
             "rows). OCHA's 2021 provincial age table (cod-ps-afg) applies one national "
             "age structure to every province, so it measures nothing about any one of "
             "them.")


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def age_gap(code: str) -> str:
    """Why a unit the office counts in a province whose report is not read here
    has no median age; ``code`` is its 1396 province or district code."""
    province = code[:2]
    if province in READ:
        raise ValueError(f"{code}: the survey's own file says why")
    whose = "this province" if len(code) == 2 else "the province the office counts it in"
    if province not in SURVEYED:
        names = [name for name, _year in SURVEYED.values()]
        return (f"{NO_CENSUS} Below the national level the office measured age only in "
                f"its Socio-Demographic and Economic Survey, a listing of every household "
                f"in twelve provinces between 2011 and 2016 ({listed(names)}); "
                f"{whose} was not one of them.")
    name, year = SURVEYED[province]
    return (f"{NO_CENSUS} The office's Socio-Demographic and Economic Survey of {name} "
            f"({year}), a listing of every household, did measure age by district there, "
            f"but every copy of its English report the Internet Archive holds stops at "
            f"exactly 1 MiB and does not open, and the office's own site no longer "
            f"serves it.")


def fold(label: str) -> str:
    return re.sub(r"[^a-z]", "", label.lower())


def table_rows(pages: list[str], report: Report) -> dict[str, tuple[float, ...]]:
    """The report's Table 3: {1396 code: (both sexes[, male, female])}.

    The table follows its title ("Median Age in Years of (the) Population by
    District"); its rows are lines that end in one or three figures of the
    form 16.6, the first of them the province's and the rest its districts'
    (Balkh's own district is called Balkh too, so the first row is taken as
    the province by its place). The list of tables names Table 3 as well, and
    is passed over because no rows follow it there; the table ends at the
    first line after its rows that is not one.
    """
    district = {fold(label): code for label, code in report.rows.items()}
    for text in pages:
        lines = [" ".join(ln.split()) for ln in text.splitlines()]
        for at, line in enumerate(lines):
            if not TITLE.search(line):
                continue
            found: dict[str, tuple[float, ...]] = {}
            for follow in lines[at + 1:]:
                figures = FIGURE.findall(follow)
                label = fold(FIGURE.sub("", follow))
                row = len(figures) in (1, 3) and follow.endswith(figures[-1])
                if row and not found and label == fold(report.name):
                    code = report.province
                elif row and found and label in district:
                    code = district[label]
                elif found:
                    break
                else:
                    continue
                if code in found:
                    raise SystemExit(f"afghanistan_sdes: {report.name}: {follow!r} "
                                     f"repeats a row of Table 3")
                found[code] = tuple(float(f) for f in figures)
            if found:
                return found
    return {}


def check(report: Report, found: dict[str, tuple[float, ...]]) -> None:
    """Table 3 against itself: every row, once, plausible, sexes around both,
    the province within the range of its districts."""
    expected = {report.province, *report.rows.values()}
    if set(found) != expected:
        raise SystemExit(f"afghanistan_sdes: {report.name}: Table 3 as read has "
                         f"{sorted(found)}, not {sorted(expected)}")
    for code, figures in found.items():
        if not all(LOW <= f <= HIGH for f in figures):
            raise SystemExit(f"afghanistan_sdes: {report.name}/{code}: {figures} "
                             f"is not a median age")
        if len(figures) == 3:
            both, male, female = figures
            if not min(male, female) - 1.0 <= both <= max(male, female) + 1.0:
                raise SystemExit(f"afghanistan_sdes: {report.name}/{code}: both sexes "
                                 f"{both} against males {male} and females {female}")
    districts = [found[code][0] for code in report.rows.values()]
    if not min(districts) <= found[report.province][0] <= max(districts):
        raise SystemExit(f"afghanistan_sdes: {report.name}: the province's median "
                         f"{found[report.province][0]} is outside its districts' "
                         f"{min(districts)}-{max(districts)}")


def survey(report: Report) -> str:
    return (f"The statistics office's Socio-Demographic and Economic Survey of "
            f"{report.name if report.name != 'Bamiyan' else 'Bamyan'}, {report.when}: "
            f"a listing and interview of every household in the districts it covered, "
            f"not a sample.")


def value_note(report: Report, figures: tuple[float, ...], scope: str, extra: str = "") -> str:
    sexes = (f" (males {figures[1]}, females {figures[2]})" if len(figures) == 3 else "")
    return (f"{survey(report)} Its Table 3 prints {figures[0]} years as the median age "
            f"of {scope}{sexes}.{extra} Afghanistan has had no census since 1979, and "
            f"this survey is the office's only measurement of age below the national "
            f"level.")


def build(found_by_report: dict[str, dict[str, tuple[float, ...]]],
          units1: list[dict[str, Any]], units2: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    from .afghanistan_estimates import (TEMPORARY_PARENT, drawn_apart, drawn_districts,
                                        province_units, shown)
    apart, _counted_in = drawn_apart(units1, units2)
    provinces = province_units(units1)
    children: dict[str, list[str]] = {}
    for temp, parent in TEMPORARY_PARENT.items():
        children.setdefault(parent, []).append(temp)
    out: list[dict[str, Any]] = []
    for report in REPORTS:
        found = found_by_report[report.province]
        cite = [{"field": "median_age", "name": SOURCE, "url": report.url,
                 "year": report.year, "license": LICENCE}]
        label_of = {code: label for label, code in report.rows.items()}
        written = declined = uncovered = 0
        for unit, province, key in drawn_districts(units1, units2):
            if key[:2] != report.province:
                continue
            fields: dict[str, Any]
            parts = children.get(key, [])
            if key not in label_of:
                fields = {"median_age": gap(NOT_AVAILABLE, (
                    f"{survey(report)} It did not cover this district, and it is the "
                    f"office's only measurement of age below the national level here. "
                    f"{report.coverage} Afghanistan has had no census since 1979, and "
                    f"the office's yearly estimates give age for the whole country "
                    f"only."))}
                uncovered += 1
            elif parts and (not report.whole or any(t in label_of for t in parts)):
                fields = {"median_age": gap(NOT_AVAILABLE, (
                    f"Not written: {survey(report)} The boundary file draws this "
                    f"district with the temporary district{'s' if len(parts) > 1 else ''} "
                    f"later cut from it, and the survey's figure for "
                    f"{label_of[key]} cannot be shown to cover {'them' if len(parts) > 1 else 'it'} "
                    f"as well."))}
                declined += 1
            else:
                figures = found[key]
                extra = (" The survey lists no temporary district: the one later cut "
                         "from this district, drawn inside this polygon, was counted "
                         "within it." if parts else "")
                fields = {"median_age": measure(figures[0], unit="years", year=report.year,
                                                source=SOURCE),
                          "median_age_note": value_note(report, figures,
                                                        f"{label_of[key]} district", extra),
                          "sources": cite}
                written += 1
            out.append(record(
                f"AFG-SDES-{key}", unit["name"], level="admin2", parent="AFG",
                country="AFG", match_by="shape_id", shape_id=unit["id"],
                parent_name=province, **fields))
        unit = provinces[report.province]
        figures = found[report.province]
        if not report.whole:
            fields = {"median_age": gap(NOT_AVAILABLE, (
                f"Not written: {survey(report)} It did not cover the whole province. "
                f"{report.coverage} Its median for the districts it covered, "
                f"{figures[0]} years, is theirs, not the province's; they carry their "
                f"own."))}
        elif report.province in apart:
            fields = {"median_age": gap(NOT_AVAILABLE, (
                f"Not written: {survey(report)} Its median for the province, "
                f"{figures[0]} years, is for {shown(unit)} as the office counts it, and "
                f"the boundary file draws it otherwise -- {'; '.join(apart[report.province])}. "
                f"The districts drawn in it carry their own."))}
        else:
            fields = {"median_age": measure(figures[0], unit="years", year=report.year,
                                            source=SOURCE),
                      "median_age_note": value_note(report, figures,
                                                    "the province's whole population"),
                      "sources": cite}
        out.append(record(
            f"AFG-SDES-{report.province}", unit["name"], level="admin1", parent="AFG",
            country="AFG", match_by="shape_id", shape_id=unit["id"], **fields))
        log(f"  {report.name} ({report.when}): {written} district(s) written, "
            f"{declined} declined, {uncovered} not covered; the province "
            + ("written" if "median_age_note" in fields else "not written"))
    return out


def pages_of(blob: bytes) -> list[str]:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("afghanistan_sdes: SDES Table 3, median age by district")
    found_by_report: dict[str, dict[str, tuple[float, ...]]] = {}
    for report in REPORTS:
        blob = http_get(report.url, binary=True)
        if blob[:4] != b"%PDF":
            raise SystemExit(f"afghanistan_sdes: {report.name}: not a PDF")
        found = table_rows(pages_of(blob), report)
        check(report, found)
        found_by_report[report.province] = found
        log(f"  {report.name}: Table 3 read, {len(found) - 1} district(s); the province "
            f"{found[report.province][0]}")
    records = build(found_by_report, load_units("AFG", "admin1"), load_units("AFG", "admin2"))
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
