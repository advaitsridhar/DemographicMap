#!/usr/bin/env python3
"""Uzbekistan: the 2026 census's preliminary results by region.

Uzbekistan counted its people in its first census since 1989, the Population
and Agricultural Census, at the critical moment of 15 January 2026. The
Statistics Committee published the preliminary results as a 67-page
compendium (*Предварительные результаты переписи населения и сельского
хозяйства, проведённой в Республике Узбекистан в 2026 году*, Tashkent 2026)
on its census portal, aholi.stat.uz, in Uzbek, Russian and English. The
Russian edition's tables are read here; each is found by its title, not its
page:

* "Распределение населения по регионам и полу" -- every region's people, men
  and women;
* "Распределение населения по регионам, возрастным группам и полу" -- the
  republic and each region by sex and five-year age group (0-4 to 80-84, 85
  and older);
* "Распределение населения по национальной принадлежности" -- every region's
  people by nationality: Uzbeks, Karakalpaks, Kazakhs, Tajiks, Kyrgyz,
  Russians, Turkmens and the rest as "other";
* "Распределение населения по регионам, национальной принадлежности и полу"
  -- the same by sex;
* "Распределение населения по регионам и родному языку" -- every region's
  people by native language, the same seven and "other".

The population is the census's permanent population, those living in the
country and those temporarily away from it (2,090,953 of the 39,047,321, most
of them working abroad), which is how the compendium counts every table.

**Binding.** The compendium's fourteen regions are the boundary file's
fourteen first-level units -- the Republic of Karakalpakstan, twelve regions
(viloyat) and the city of Tashkent -- and each is bound by its ISO 3166-2
code. The boundary file's second level puts three of Tashkent's districts
(Bektemir, Sergeli, Uchtepa) under Tashkent Region, because its district
outlines are drawn south-west of the first level's: the first-level polygon
drawn as Tashkent is 344 km2, the city's own area, and it is the city.

**Not written.** The preliminary results give no table below the region,
and none of religion; the final results are due by 1 July 2027 (the
compendium's foreword). Districts keep the statistics agency's own figures
(``uzbekistan_siat``), whose reasons say this.

**Checks.** Men and women make both sexes in every row; each region's age
groups make its people, sex by sex, and the regions make the republic group
by group; each region's nationalities make its people, the table by sex
agreeing with the table without it nationality by nationality; its native
languages make its people; every table's region totals agree with the
regions-by-sex table, and the regions make the republic's 39,047,321.

Usage:
    python -m scripts.fetch_census.uzbekistan_census
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, \
    write_json
from .cod_ps_age import grouped_median
from .kyrgyzstan_census import figures

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import as_drawn, read_json, shard_name  # noqa: E402

ISO3 = "UZB"
YEAR = 2026
OUT = "uzbekistan_census.json"
NATIONAL = 39_047_321
SITE = PROCESSED.parent.parent / "site" / "data"
URL = "https://aholi.stat.uz/images/kitob-rus_p51999.pdf"
PAGE = ("https://aholi.stat.uz/ru/publikatsii/predvaritelnye-rezultaty-perepisi-naseleniya-"
        "i-selskogo-khozyajstva-v-respublike-uzbekistan-v-2026-godu")
SOURCE = ("Statistics Committee of the Republic of Uzbekistan, Preliminary results of the "
          "Population and Agricultural Census of the Republic of Uzbekistan 2026 "
          "(Tashkent, 2026)")
LICENCE = "Official statistics of the Statistics Committee of the Republic of Uzbekistan"
PRELIMINARY = ("A preliminary result of the 2026 census (critical moment 15 January 2026), "
               "which the Committee may still revise; its final results are due by 1 July "
               "2027.")

# The compendium's regions (folded: lower case, letters only) -> ISO 3166-2.
REPUBLIC = "республикаузбекистан"
REGIONS = {
    "республикакаракалпакстан": "UZ-QR", "андижанскаяобласть": "UZ-AN",
    "бухарскаяобласть": "UZ-BU", "джизакскаяобласть": "UZ-JI",
    "кашкадарьинскаяобласть": "UZ-QA", "навоийскаяобласть": "UZ-NW",
    "наманганскаяобласть": "UZ-NG", "самаркандскаяобласть": "UZ-SA",
    "сурхандарьинскаяобласть": "UZ-SU", "сырдарьинскаяобласть": "UZ-SI",
    "ташкентскаяобласть": "UZ-TO", "ферганскаяобласть": "UZ-FA",
    "хорезмскаяобласть": "UZ-XO", "городташкент": "UZ-TK",
}
AREAS = (REPUBLIC, *REGIONS)
NATIONALITIES = {"узбеки": "Uzbek", "каракалпаки": "Karakalpak", "казахи": "Kazakh",
                 "таджики": "Tajik", "киргизы": "Kyrgyz", "русские": "Russian",
                 "туркмены": "Turkmen", "другие": "Other"}
LANGUAGES = {"узбекский": "Uzbek", "каракалпакский": "Karakalpak", "казахский": "Kazakh",
             "таджикский": "Tajik", "киргизский": "Kyrgyz", "русский": "Russian",
             "туркменский": "Turkmen", "другой": "Other languages"}
GROUPS = [(lo, lo + 4) for lo in range(0, 85, 5)] + [(85, None)]
DASHES = ("-", "–", "−")
PAGE_BREAK = "@@page@@"

TITLES = {
    "sexes": r"Распределение\s+населения\s+по\s+регионам\s+и\s+полу",
    "ages": r"Распределение\s+населения\s+по\s+регионам,\s+возрастным\s+группам\s+и\s+полу",
    "nations": r"Распределение\s+населения\s+по\s+национальной\s+принадлежности",
    "nation_sexes": (r"Распределение\s+населения\s+по\s+регионам,\s+национальной\s+"
                     r"принадлежности\s+и\s+полу"),
    "tongues": r"Распределение\s+населения\s+по\s+регионам\s+и\s+родному\s+языку",
}
# Where each table stops: the next table's title, or a section's heading.
ENDS = (r"Распределение\s+населения\s+по\s+регионам,\s+городской",
        r"Распределение\s+населения\s+по\s+регионам\s+и\s+основным",
        r"МЕСТО\s+РОЖДЕНИЯ", r"НАСЕЛЕНИЕ\s+ПО\s+ЛИНГВИСТИЧЕСКИМ", r"ЖИЛИЩНЫЕ\s+УСЛОВИЯ")

RELIGION_GAP = gap(NOT_AVAILABLE, (
    "The 2026 census's preliminary results (the Statistics Committee's 67-page compendium, "
    f"{PAGE}) tabulate population, sex, age, place of birth, nationality, native language "
    "and housing, and no religion, for the republic or any region; the final results are "
    "due by 1 July 2027."))


def fold(text: str) -> str:
    """'Кашкадарьинска\\nя область' -> 'кашкадарьинскаяобласть'."""
    return re.sub(r"[^а-яё]", "", text.lower()).replace("ё", "е")


def area_of(label: str) -> str | None:
    """The region a row's label ends with -- the label may carry a heading before it."""
    key = fold(label)
    found = [a for a in AREAS if key.endswith(a)]
    return max(found, key=len) if found else None


def pdf_pages(blob: bytes) -> list[str]:
    import logging

    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages]


def section(pages: list[str], title: str) -> str:
    """The text of one table, from its title to the next table or section."""
    text = f"\n{PAGE_BREAK}\n".join(pages)
    starts = [m for m in re.finditer(title, text)]
    # The contents pages name every table too; the table is the last mention.
    if not starts:
        raise SystemExit(f"uzbekistan_census: no table titled {title!r}")
    begin = starts[-1].end()
    stops = [m.start() for t in (*TITLES.values(), *ENDS)
             for m in re.finditer(t, text) if m.start() > begin]
    return text[begin:min(stops) if stops else len(text)]


def split_row(line: str) -> tuple[str, list[str]]:
    """('Андижанская область', ['3', '531', '777', ...]): words, then counts.

    The counts are the run of figures that ends the line, or ends where the
    shares begin ('50,4'): the tables print shares after the counts. A figure
    followed by words ('85 лет и старше') is part of the label.
    """
    parts = line.split()
    stop = next((i for i, t in enumerate(parts) if "," in t and re.search(r"\d", t)),
                len(parts))
    start = stop
    while start > 0 and (parts[start - 1].isdigit() or parts[start - 1] in DASHES):
        start -= 1
    return " ".join(parts[:start]), parts[start:stop]


def triple(tokens: list[str], where: str) -> tuple[int, int, int]:
    """(both sexes, men, women): the one reading of a row whose men and women add up."""
    found = figures(tokens, 3, lambda v: v[0] == v[1] + v[2])
    if len(found) != 1:
        raise SystemExit(f"uzbekistan_census: {where}: {len(found)} readings of "
                         f"{' '.join(tokens)!r} as both sexes, men and women")
    return tuple(found[0])  # type: ignore[return-value]


def rows(text: str) -> list[tuple[str, list[str]]]:
    """(label, counts) for every line with counts, a wrapped label joined to its line.

    A page break ends a wrapped label, and a page's number -- a line of one
    short figure -- is not a row.
    """
    out: list[tuple[str, list[str]]] = []
    pending = ""
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line == PAGE_BREAK:
            pending = ""
            continue
        if not line or re.fullmatch(r"\d{1,3}", line):
            continue
        label, counts = split_row(line)
        if not counts or all(t in DASHES for t in counts):
            pending = f"{pending} {label}".strip()
            continue
        out.append((f"{pending} {label}".strip(), counts))
        pending = ""
    return out


def keep(seen: dict[Any, Any], key: Any, value: Any, where: str) -> None:
    """Record a row once; a row printed twice must say the same both times."""
    if key in seen and seen[key] != value:
        raise SystemExit(f"uzbekistan_census: {where}: {key} printed as {seen[key]} and {value}")
    seen[key] = value


def parse_sexes(text: str) -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    for label, counts in rows(text):
        area = area_of(label)
        if area:
            keep(out, area, triple(counts, f"sexes {area}"), "sexes")
    return out


def parse_ages(text: str) -> dict[str, dict[tuple[int, int | None], tuple[int, int, int]]]:
    """{area: {(low, high): (both, men, women)}} with each area's own total under 'total'."""
    out: dict[str, dict[Any, tuple[int, int, int]]] = {}
    area = None
    for label, counts in rows(text):
        found = area_of(label)
        if found:
            area = found
            keep(out.setdefault(area, {}), "total", triple(counts, f"ages {area}"),
                 f"ages {area}")
            continue
        if area is None:
            continue
        m = re.search(r"(\d+)\s*-\s*(\d+)$", label)
        if m:
            band: tuple[int, int | None] = (int(m.group(1)), int(m.group(2)))
        elif re.search(r"85\s+лет\s+и\s+старше$", label):
            band = (85, None)
        else:
            continue
        keep(out[area], band, triple(counts, f"ages {area} {band}"), f"ages {area}")
    return out


def parse_nations(text: str) -> dict[str, list[int]]:
    """{area: [population, then the eight nationalities in the table's order]}."""
    head = " ".join(text.split()[:80]).lower()
    order = [w for w in re.findall(r"[а-яё]+", head) if w in NATIONALITIES]
    if order != list(NATIONALITIES):
        raise SystemExit(f"uzbekistan_census: nationality columns {order}")
    out: dict[str, list[int]] = {}
    for label, counts in rows(text):
        area = area_of(label)
        if not area:
            continue
        found = figures(counts, 9, lambda v: v[0] == sum(v[1:]))
        if len(found) != 1:
            raise SystemExit(f"uzbekistan_census: nationalities {area}: {len(found)} readings "
                             f"of {' '.join(counts)!r}")
        keep(out, area, found[0], "nationalities")
    return out


def parse_nation_sexes(text: str) -> dict[str, dict[str, tuple[int, int, int]]]:
    """{area: {'total' or a nationality: (both, men, women)}}."""
    out: dict[str, dict[str, tuple[int, int, int]]] = {}
    area = None
    for label, counts in rows(text):
        found = area_of(label)
        if found:
            area = found
            keep(out.setdefault(area, {}), "total", triple(counts, f"nationality {area}"),
                 f"nationality {area}")
            continue
        word = fold(label)
        name = next((n for n in NATIONALITIES if word.endswith(n)), None)
        if area is None or name is None:
            continue
        keep(out[area], name, triple(counts, f"nationality {area} {name}"),
             f"nationality {area}")
    return out


def parse_tongues(text: str) -> dict[str, list[int]]:
    """{area: [population, then the eight native languages in the table's order]}."""
    head = " ".join(text.split()[:60]).lower()
    order = [w for w in re.findall(r"[а-яё]+", head) if w in LANGUAGES]
    if order != list(LANGUAGES):
        raise SystemExit(f"uzbekistan_census: language columns {order}")
    out: dict[str, list[int]] = {}
    for label, counts in rows(text):
        area = area_of(label)
        if not area:
            continue
        found = figures(counts, 9, lambda v: v[0] == sum(v[1:]))
        if len(found) != 1:
            raise SystemExit(f"uzbekistan_census: native languages {area}: {len(found)} "
                             f"readings of {' '.join(counts)!r}")
        keep(out, area, found[0], "native languages")
    return out


def read_tables(pages: list[str]) -> dict[str, dict[str, Any]]:
    """Every area's sexes, age groups, nationalities and languages, every check passed."""
    sexes = parse_sexes(section(pages, TITLES["sexes"]))
    ages = parse_ages(section(pages, TITLES["ages"]))
    nations = parse_nations(section(pages, TITLES["nations"]))
    nation_sexes = parse_nation_sexes(section(pages, TITLES["nation_sexes"]))
    tongues = parse_tongues(section(pages, TITLES["tongues"]))
    for name, table in (("sexes", sexes), ("ages", ages), ("nationalities", nations),
                        ("nationalities by sex", nation_sexes), ("native languages", tongues)):
        missing = [a for a in AREAS if a not in table]
        if missing:
            raise SystemExit(f"uzbekistan_census: {name}: no row for {missing}")
    out: dict[str, dict[str, Any]] = {}
    for area in AREAS:
        both, men, women = sexes[area]
        where = f"uzbekistan_census: {area}"
        # Age groups: every band, adding up to the area sex by sex.
        bands = ages[area]
        if bands["total"] != sexes[area]:
            raise SystemExit(f"{where}: age table's total {bands['total']} against {sexes[area]}")
        if sorted((b for b in bands if b != "total"), key=lambda b: b[0]) != GROUPS:
            raise SystemExit(f"{where}: age bands {sorted(b for b in bands if b != 'total')}")
        made = tuple(sum(bands[g][i] for g in GROUPS) for i in range(3))
        if made != sexes[area]:
            raise SystemExit(f"{where}: age groups make {made} of {sexes[area]}")
        # Nationalities: both tables, the same figures, adding up to the area.
        row = nations[area]
        if row[0] != both:
            raise SystemExit(f"{where}: nationality table's total {row[0]:,} against {both:,}")
        by_sex = nation_sexes[area]
        if by_sex["total"] != sexes[area]:
            raise SystemExit(f"{where}: nationality-by-sex total {by_sex['total']}")
        for name, count in zip(NATIONALITIES, row[1:]):
            if name not in by_sex or by_sex[name][0] != count:
                raise SystemExit(f"{where}: {name} {count:,} against {by_sex.get(name)}")
        made = tuple(sum(by_sex[n][i] for n in NATIONALITIES) for i in range(3))
        if made != sexes[area]:
            raise SystemExit(f"{where}: nationalities by sex make {made} of {sexes[area]}")
        # Native languages, adding up to the area.
        langs = tongues[area]
        if langs[0] != both:
            raise SystemExit(f"{where}: language table's total {langs[0]:,} against {both:,}")
        out[area] = {"sexes": sexes[area], "bands": [bands[g] for g in GROUPS],
                     "nationality": dict(zip(NATIONALITIES.values(), row[1:])),
                     "language": dict(zip(LANGUAGES.values(), langs[1:]))}
    # The regions make the republic, figure by figure.
    regions = [out[a] for a in REGIONS]
    country = out[REPUBLIC]
    if country["sexes"][0] != NATIONAL:
        raise SystemExit(f"uzbekistan_census: the republic is {country['sexes'][0]:,}, not "
                         f"{NATIONAL:,}")
    checks = {"sexes": lambda r: r["sexes"],
              "age groups": lambda r: [x for band in r["bands"] for x in band],
              "nationalities": lambda r: list(r["nationality"].values()),
              "native languages": lambda r: list(r["language"].values())}
    for what, get in checks.items():
        made = [sum(col) for col in zip(*(get(r) for r in regions))]
        if made != list(get(country)):
            raise SystemExit(f"uzbekistan_census: the regions' {what} make {made}, the "
                             f"republic {list(get(country))}")
    log(f"  14 regions make the republic's {NATIONAL:,} in every table")
    return out


def build(areas: dict[str, dict[str, Any]], a1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code = {u.get("iso_3166_2"): u for u in a1}
    out: list[dict[str, Any]] = []
    src = [{"field": "population/sex_ratio/median_age/ethnicity/language", "name": SOURCE,
            "url": PAGE, "license": LICENCE}]
    for area, code in REGIONS.items():
        unit = by_code.get(code)
        if unit is None:
            raise SystemExit(f"uzbekistan_census: the map draws no {code}")
        data = areas[area]
        both, men, women = data["sexes"]
        out.append(record(
            f"UZB-CENSUS-{code}", unit["name"], level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=unit["id"], aliases=[code],
            population=measure(both, year=YEAR, source=SOURCE),
            population_note=("The census's permanent population: those living in the region "
                             "and those of them temporarily away, abroad included. "
                             + PRELIMINARY),
            sex_ratio=measure(round(100 * men / women, 1), year=YEAR, source=SOURCE,
                              unit="males_per_100_females"),
            sex_ratio_note=f"Men per 100 women, from the census's counts. {PRELIMINARY}",
            median_age=measure(grouped_median([(lo, hi, n[0]) for (lo, hi), n
                                               in zip(GROUPS, data["bands"])]),
                               year=YEAR, source=SOURCE),
            median_age_note=("Median interpolated within the five-year age group holding the "
                             "middle person; the preliminary results publish five-year "
                             f"groups (0-4 to 80-84, 85 and older) by region. {PRELIMINARY}"),
            ethnicity=shares(data["nationality"]),
            ethnicity_year=YEAR,
            ethnicity_note=("Nationality (национальная принадлежность) as each person "
                            "declared it: the seven the preliminary results tabulate by "
                            "region, the rest as other. " + PRELIMINARY),
            language=shares(data["language"]),
            language_year=YEAR,
            language_note=("Native language (родной язык) as each person named it: the seven "
                           "the preliminary results tabulate by region, the rest as other "
                           "languages. " + PRELIMINARY),
            religion=RELIGION_GAP,
            sources=src))
    return out


def drawn_admin1() -> list[dict[str, Any]]:
    return as_drawn(read_json(SITE / "admin1" / shard_name(ISO3), []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("uzbekistan_census: 2026 census, preliminary results")
    pages = pdf_pages(http_get(URL, binary=True, timeout=300))  # type: ignore[arg-type]
    areas = read_tables(pages)
    out = build(areas, drawn_admin1())
    for r in out:
        log(f"    {r['name']}: {r['population']['value']:,}, median "
            f"{r['median_age']['value']}, ratio {r['sex_ratio']['value']}, "
            + ", ".join(f"{g['group']} {g['pct']}%" for g in r["ethnicity"][:3]) + "; "
            + ", ".join(f"{g['group']} {g['pct']}%" for g in r["language"][:3]))
    country = areas[REPUBLIC]
    log(f"  republic: median {grouped_median([(lo, hi, n[0]) for (lo, hi), n in zip(GROUPS, country['bands'])])}, "
        f"ratio {round(100 * country['sexes'][1] / country['sexes'][2], 1)}, "
        + ", ".join(f"{g['group']} {g['pct']}%" for g in shares(country["nationality"])) + " | "
        + ", ".join(f"{g['group']} {g['pct']}%" for g in shares(country["language"])))
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
