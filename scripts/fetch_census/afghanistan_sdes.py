#!/usr/bin/env python3
"""Afghanistan -- median age by district from the Socio-Demographic and Economic Survey.

Afghanistan has had no census since the abandoned count of 1979, and the
statistics office's yearly population estimates give age for the nation alone
(see ``afghanistan_estimates.py``). What it did measure, province by province
from 2011 to 2016, is the **Socio-Demographic and Economic Survey (SDES)**,
which the Central Statistics Organization (now the National Statistics and
Information Authority) ran with UNFPA as a stand-in for the census it could
not hold: every house of a province was mapped and every household listed,
and every other listed household -- half of them -- was interviewed about
each member's age, sex, education, work and migration ("listing and mapping
of all households and establishments and enumeration of half of the
households in each enumeration area/village", as the Herat report puts it).
So the figures are the office's own **survey estimates from a half sample**,
not a count; per district that half is thousands of people, far above any
threshold for an estimate. Each provincial report has a table "Median Age in
Years of the Population by District", for both sexes, males and females
(Table 3; Table 5 in the 2012 reports, which print whole years).

The survey reached twelve provinces (``REPORTS``, in its own order), and every
report is read here, from the office's site or UNFPA's as the Internet Archive
holds them:

    Bamyan     September 2011   the whole province
    Ghor       September 2012   the whole province (whole years)
    Daykundi   September 2012   the centre and seven districts; no Gizab (whole years)
    Kabul      December 2013    the whole province
    Kapisa     September 2014   5 of 7 districts (Tagab and Alasay, for insecurity)
    Parwan     September 2014   the whole province
    Samangan   April 2015       the whole province
    Balkh      December 2015    the whole province
    Takhar     September 2015   the whole province
    Herat      March 2016       the city and 12 of 15 districts (Gulran,
                                Shindand and Fersi, for insecurity)
    Nimroz     May 2016         4 of 5 districts (Khashrod, for insecurity)
    Baghlan    December 2016    the whole province

**The office publishes the median, and the median is what is written** --
its own figure for the district, not one recomputed here. Each table is held
to itself before anything is written: its first row is the province, every
other row a district the reader knows for that province (``REPORTS``, the
report's spelling against the code the office's 1396 estimates give the
district), none twice and none missing, every figure between 5 and 40 years,
the both-sexes median within a year of its male and female medians, the
province's within the range of its districts' -- as the median of a whole
always is -- and the province's equal to the figure the later reports print
for it in their "Text Box 1" (``Report.box``; within half a year where the
table prints whole years). Some reports set part of their text in fonts that
carry no character map, which a PDF reader returns as "(cid:N)"; the glyph
numbers are the standard ones, N + 29 being the character, and a decoded row
is held to the same checks as any other.

**Which polygon.** A row is bound to the drawn district through the office's
own district code, the one ``afghanistan_estimates.CROSSWALK`` binds to each
of the 398 drawn shapes -- so a district the boundary file draws in another
province (Mahmudi Raqi, counted in Kapisa and drawn in Parwan; Feroz
Nakhchir, counted in Samangan and drawn in Balkh) takes its own row from the
report of the province that counted it. Some drawn districts are an original
district *and* temporary districts cut from it later (``TEMPORARY_PARENT``):
a report of the whole province that lists no temporary district counted it
inside its original (Bamyan's Yakawlang, surveyed in 2011, holds the later
Yakawlang No. 2), so its row is the polygon's; a report that lists one apart,
or that did not cover the whole province, is not written for the polygon.

**Provinces** take the report's provincial median only where the report
covered the whole province and the boundary file draws the province as the
office counts it (``afghanistan_estimates.drawn_apart``). Each one that does
not says why.

This file writes the median age -- a figure, or the reason there is none --
of every drawn district the office counts in a surveyed province, and of
those provinces; ``afghanistan_estimates`` leaves the field to it there and
says why everywhere else (``age_gap``). The figures are survey estimates, so
the file is named as one.

Usage:
    python -m scripts.fetch_census.afghanistan_sdes
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any, Iterable, Iterator, NamedTuple

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .south_asia_common import load_units

OUT = "afghanistan_sdes_survey.json"
SOURCE = ("Central Statistics Organization of Afghanistan (now the National Statistics "
          "and Information Authority) with UNFPA, Socio-Demographic and Economic Survey "
          "(SDES), provincial report: median age in years of the population by district")
LICENCE = "Afghanistan Central Statistics Organization publication"
CSO = "https://web.archive.org/web/{stamp}id_/http://cso.gov.af/Content/files/{path}"
UNFPA = ("https://web.archive.org/web/{stamp}id_/https://afghanistan.unfpa.org/sites/"
         "default/files/pub-pdf/{path}")


class Report(NamedTuple):
    province: str                 # the 1396 tables' province code
    name: str                     # the report's own first row
    url: str                      # the archived English report
    when: str                     # the survey's reference month, as printed
    year: int
    rows: dict[str, str]          # the report's district label -> 1396 code
    whole: bool                   # every district of the province covered
    coverage: str = ""            # what the report says it did not cover
    box: float | None = None      # the province's median in later reports' Text Box 1
    table: str = "3"              # the table's number in the report
    whole_years: bool = False     # the table prints whole years


REPORTS: list[Report] = [
    Report("10", "Bamiyan",
           CSO.format(stamp="20170511164651", path=(
               "Afghanistan%20SDES%20Bamiyan%20Final%20Report%20-%2024%20April%202013.pdf")),
           "September 2011", 2011,
           {"Provincial Center": "1001", "Shibar": "1002", "Saighan": "1003",
            "Kahmard": "1004", "Yakawlang": "1005", "Panjab": "1006", "Waras": "1007"},
           whole=True, box=16.6),
    Report("23", "Ghor",
           UNFPA.format(stamp="20210816022526", path="SDES-Ghor-English-Low-Resolution-Version.pdf"),
           "September 2012", 2012,
           {"Chighcheran": "2301", "Duleena": "2302", "Dawlatyar": "2303", "Char Sada": "2304",
            "Pasaband": "2305", "Shahrak": "2306", "Lal Wa Sarjangal": "2307",
            "Taywara": "2308", "Tulak": "2309", "Saghar": "2310"},
           whole=True, box=16.3, table="5", whole_years=True),
    Report("24", "Daykundi",
           UNFPA.format(stamp="20210816022918", path="SDES-DaikundiReport-Part1-pag-1-50.pdf"),
           "September 2012", 2012,
           {"Nili": "2401", "Shahristan": "2402", "Ishterlai": "2403", "Khedir": "2404",
            "Geti": "2405", "Miramor": "2406", "Sang-e-Takht": "2407", "Kejran": "2408"},
           whole=False,
           coverage="Its Table 5 lists the provincial centre and seven districts, and "
                    "not Gizab.",
           box=15.2, table="5", whole_years=True),
    Report("01", "Kabul",
           UNFPA.format(stamp="20210816022304",
                        path="Kabul_Socio-demographic-Economic-Survey_English.pdf"),
           "December 2013", 2013,
           {"Kabul City": "0101", "Paghman": "0102", "Chahar Asyab": "0103", "Bagrami": "0104",
            "Dehsabz": "0105", "Shakar Dara": "0106", "Musahi": "0107", "Mir Bacha Kot": "0108",
            "Khak-e-Jabar": "0109", "Kalakan": "0110", "Guldara": "0111", "Farza": "0112",
            "Estalef": "0113", "Qara Bagh": "0114", "Surubi": "0115"},
           whole=True, box=17.7),
    Report("02", "Kapisa",
           CSO.format(stamp="20170511124634", path="SDES%20Kapisa%20Report%20-%20Final.pdf"),
           "September 2014", 2014,
           {"Mahmudi Raqi": "0201", "Hissa-e-Duwumi Kohistan": "0202", "Koh Band": "0203",
            "Hissa-e-Awali Kohistan": "0204", "Nijrab": "0205"},
           whole=False,
           coverage="The report says: \"Tagab and Alasay districts were not covered during "
                    "the listing and enumeration due to security problems in those areas.\"",
           box=17.1),
    Report("03", "Parwan",
           CSO.format(stamp="20170511131324", path="SDES%20Parwan%20Report%20-%20Final.pdf"),
           "September 2014", 2014,
           {"Charikar": "0301", "Bagram": "0302", "Shinwari": "0303", "Sayid Khail": "0304",
            "Jabulussaraj": "0305", "Salang": "0306", "Syahgirdi Ghorband": "0307",
            "Kohi Safi": "0308", "Surkhi Parsa": "0309", "Shaykh Ali": "0310"},
           whole=True, box=17.1),
    Report("20", "Samangan",
           UNFPA.format(stamp="20210816023651",
                        path="Samangan%20Report%20English%20V1_Reza_13Dec2015_webquality.pdf"),
           "April 2015", 2015,
           {"Aybak": "2001", "Hazrat-e-Sultan": "2002", "Khuram Wa Sarbagh": "2003",
            "Feroz Nakhcheer": "2004", "Roi-Do-Ab": "2005", "Dara-e-Soof-e-Payin": "2006",
            "Dara-e-Soof-e-Bala": "2007"},
           whole=True, box=17.5),
    Report("21", "Balkh",
           CSO.format(stamp="20170511124330", path="SDES/Balkh%20FR%20Final2.pdf"),
           "December 2015", 2015,
           {"Mazar-E-Sharif": "2101", "Nahr-E-Shahi": "2102", "Dehdadi": "2103",
            "Char Kent": "2104", "Marmul": "2105", "Balkh": "2106", "Sholgara": "2107",
            "Chimtal": "2108", "Dawlat Abad": "2109", "Khulm": "2110", "Char Bolak": "2111",
            "Shortepa": "2112", "Kaldar": "2113", "Kishendeh": "2114", "Zari": "2115"},
           whole=True, box=17.1),
    Report("18", "Takhar",
           UNFPA.format(stamp="20200701051731",
                        path="Takhar%20Socio-Demographic%20and%20Economic%20Survey.pdf"),
           "September 2015", 2015,
           {"Taluqan": "1801", "Hazar Samoch": "1802", "Baharak": "1803", "Bangi": "1804",
            "Chal": "1805", "Namak Ab": "1806", "Kalafghan": "1807", "Farkhar": "1808",
            "Khwaja Ghar": "1809", "Rustaq": "1810", "Eshkamesh": "1811",
            "Dasht-E-Qala": "1812", "Warsaj": "1813", "Khwaja Bahawuddin": "1814",
            "Darqad": "1815", "Chahab": "1816", "Yangi Qala": "1817"},
           whole=True, box=16.3),
    Report("32", "Herat",
           CSO.format(stamp="20170511124125", path="SDES/Highlight%20Herat%20Fr%204%20March.pdf"),
           "March 2016", 2016,
           {"Herat City": "3201", "Enjil": "3202", "Nizam-E-Shahid": "3203", "Karrukh": "3204",
            "Zendajan": "3205", "Pashtun Zarghun": "3206", "Kushk (Rubat-E-Sangi)": "3207",
            "Adraskan": "3209", "Kushk-E-Kuhna": "3210", "Ghoryan": "3211", "Obe": "3212",
            "Kohsan": "3213", "Chisht-E-Sharif": "3216"},
           whole=False,
           coverage="The report says: \"Due to security problems, the districts of "
                    "Gulran, Shindand and Fersi were not covered.\"",
           box=16.8),
    Report("34", "Nimroz",
           CSO.format(stamp="20170511124002",
                      path="SDES/NImroz%20FR%203%20copy%20April%2012%20%20Final.pdf"),
           "May 2016", 2016,
           {"Zaranj": "3401", "Kang": "3402", "Asl-E-Chakhansur": "3403",
            "Char Burjak": "3404"},
           whole=False,
           coverage="The report says the survey covered every district \"except in "
                    "Khashrod District which was not covered due to insecurity.\"",
           box=14.5),
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
READ = {report.province for report in REPORTS}
PROVINCE_NAME = {"10": "Bamyan"}     # the province's usual spelling, where the report's differs

LOW, HIGH = 5.0, 40.0
FIGURE = re.compile(r"\d{1,2}\.\d")
WHOLE = re.compile(r"(?<![\d.])\d{1,2}(?![\d.])")
TITLE = re.compile(r"(?i)median\s+age\s+in\s+years\s+of\s+(?:the\s+)?population\s+by\s+district")
NEXT = re.compile(r"(?i)^(?:table|figure|text\s+box)\s*\d")
CID = re.compile(r"\(cid:(\d+)\)")
# The population pyramid's legend, which a two-page spread can set on a row's
# line; no district is called either.
LEGEND = re.compile(r"(?i)\b(?:fe)?males?\b")
NO_CENSUS = ("Afghanistan has had no census since 1979, and the statistics office's "
             "yearly estimates give age for the whole country only (the 1396 release's "
             "age workbook, \"گروپ سنین\", has five-year groups by sex for the rural, "
             "urban and nomadic population of Afghanistan and no province or district "
             "rows). OCHA's 2021 provincial age table (cod-ps-afg) applies one national "
             "age structure to every province, so it measures nothing about any one of "
             "them.")


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def province_name(report: Report) -> str:
    return PROVINCE_NAME.get(report.province, report.name)


def age_gap(code: str) -> str:
    """Why a unit the office counts in a province the survey never reached has
    no median age; ``code`` is its 1396 province or district code."""
    if code[:2] in READ:
        raise ValueError(f"{code}: the survey's own file says why")
    whose = "this province" if len(code) == 2 else "the province the office counts it in"
    names = [province_name(report) for report in REPORTS]
    return (f"{NO_CENSUS} Below the national level the office measured age only in its "
            f"Socio-Demographic and Economic Survey, which listed every household and "
            f"interviewed half of them in twelve provinces between 2011 and 2016 "
            f"({listed(names)}); {whose} was not one of them.")


def fold(label: str) -> str:
    return re.sub(r"[^a-z]", "", label.lower())


def decode(line: str) -> str:
    """A line with its "(cid:N)" glyphs written as the characters they are."""
    return CID.sub(lambda m: chr(int(m.group(1)) + 29) if 3 <= int(m.group(1)) <= 93
                   else m.group(0), line)


def table_rows(pages: Iterable[str], report: Report) -> dict[str, tuple[float, ...]]:
    """The report's table of median ages: {1396 code: (both sexes[, male, female])}.

    The table follows its title ("Median Age in Years of (the) Population by
    District"). Its rows are lines that end in one or three figures -- 16.6,
    or 16 where the table prints whole years -- whose label is the province
    (the first row, taken by its place: Balkh's own district is called Balkh
    too) or one of its districts. Lines between them that are not rows are
    passed over: a two-page spread sets the population pyramid's age labels
    and its legend on the same lines ("79-75 Samangan 17.5 17.7 17.3",
    "Female Male 69-65 Aybak 17.4 17.4 17.5"). The table ends at the
    next table's or figure's title, or once every row is in. The list of
    tables names the table too, and is passed over because no rows follow it.
    """
    figure = WHOLE if report.whole_years else FIGURE
    district = {fold(label): code for label, code in report.rows.items()}
    every = 1 + len(report.rows)
    for text in pages:
        lines = [" ".join(decode(ln).split()) for ln in text.splitlines()]
        for at, line in enumerate(lines):
            if not TITLE.search(line):
                continue
            found: dict[str, tuple[float, ...]] = {}
            for follow in lines[at + 1:]:
                if NEXT.match(follow) or len(found) == every:
                    break
                figures = figure.findall(follow)
                if len(figures) not in (1, 3) or not follow.endswith(figures[-1]):
                    continue
                label = fold(LEGEND.sub("", figure.sub("", follow)))
                if not found and label == fold(report.name):
                    code = report.province
                elif found and label in district:
                    code = district[label]
                else:
                    continue
                if code in found:
                    raise SystemExit(f"afghanistan_sdes: {report.name}: {follow!r} "
                                     f"repeats a row of the table")
                found[code] = tuple(float(f) for f in figures)
            if found:
                return found
    return {}


def check(report: Report, found: dict[str, tuple[float, ...]]) -> None:
    """The table against itself and against the province's figure elsewhere."""
    expected = {report.province, *report.rows.values()}
    if set(found) != expected:
        raise SystemExit(f"afghanistan_sdes: {report.name}: the table as read has "
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
    whole = found[report.province][0]
    districts = [found[code][0] for code in report.rows.values()]
    if not min(districts) <= whole <= max(districts):
        raise SystemExit(f"afghanistan_sdes: {report.name}: the province's median "
                         f"{whole} is outside its districts' {min(districts)}-{max(districts)}")
    if report.box is not None and abs(whole - report.box) > (0.5 if report.whole_years else 0.0):
        raise SystemExit(f"afghanistan_sdes: {report.name}: the table's provincial median "
                         f"{whole} is not the {report.box} the later reports print")


def survey(report: Report) -> str:
    return (f"The statistics office's Socio-Demographic and Economic Survey of "
            f"{province_name(report)}, {report.when}, which listed every household of "
            f"the districts it covered and interviewed every other one about each "
            f"member's age and sex: an estimate from half the households, not a count.")


def value_note(report: Report, figures: tuple[float, ...], scope: str, extra: str = "") -> str:
    shown = [f"{f:g}" for f in figures]
    sexes = (f" (males {shown[1]}, females {shown[2]})" if len(figures) == 3 else "")
    whole = " The table prints whole years." if report.whole_years else ""
    return (f"{survey(report)} Its Table {report.table} prints {shown[0]} years as the "
            f"median age of {scope}{sexes}.{whole}{extra} Afghanistan has had no census "
            f"since 1979, and this survey is the office's only measurement of age below "
            f"the national level.")


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
                    f"{label_of[key]} cannot be shown to cover "
                    f"{'them' if len(parts) > 1 else 'it'} as well."))}
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
                f"{figures[0]:g} years, is theirs, not the province's; they carry their "
                f"own."))}
        elif report.province in apart:
            fields = {"median_age": gap(NOT_AVAILABLE, (
                f"Not written: {survey(report)} Its median for the province, "
                f"{figures[0]:g} years, is for {shown(unit)} as the office counts it, and "
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


def pages_of(blob: bytes) -> Iterator[str]:
    """Each page's text, read only as far as the table is looked for: a
    report runs to a hundred pages and its table is in the first thirty."""
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            yield page.extract_text() or ""


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("afghanistan_sdes: SDES median age by district, twelve provincial reports")
    found_by_report: dict[str, dict[str, tuple[float, ...]]] = {}
    for report in REPORTS:
        blob = http_get(report.url, binary=True)
        if blob[:4] != b"%PDF":
            raise SystemExit(f"afghanistan_sdes: {report.name}: not a PDF")
        found = table_rows(pages_of(blob), report)
        check(report, found)
        found_by_report[report.province] = found
        log(f"  {report.name}: Table {report.table} read, {len(found) - 1} district(s); "
            f"the province {found[report.province][0]:g}"
            + (f" (Text Box 1: {report.box:g})" if report.box is not None else ""))
    records = build(found_by_report, load_units("AFG", "admin1"), load_units("AFG", "admin2"))
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
