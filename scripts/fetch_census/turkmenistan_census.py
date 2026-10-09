#!/usr/bin/env python3
"""Turkmenistan: the 2022 census by velayat.

The State Committee of Turkmenistan on Statistics publishes the results of
the 2022 Complete Population and Housing Census in eleven PDF volumes, in
Turkmen, Russian and English. Two are read here, in English:

* volume 2, *Age and sex composition of the population and status in
  marriage*, tables 2.11-2.16: Ashgabat city and each velayat by sex and age
  group (under 1, 1-4, five-year groups to 80-84, 85 and older);
* volume 4, *National composition of the population and language
  proficiency*: tables 4.3-4.8, each area's fifteen most numerous
  nationalities and the rest; tables 4.12-4.29, each area's population by
  nationality and mother tongue, whose first row gives the area's mother
  tongues, for both sexes, men and women.

**Binding.** The boundary file's first level draws the five velayats; it
does not draw Ashgabat, a city with the status of a velayat, whose ground is
inside the polygon drawn as Ahal. Ahal's polygon therefore carries Ahal
velayat and Ashgabat together, and says so; the other four carry their own
velayat's figures.

**Checks.** Every row's men and women make both sexes and its urban and
rural parts make the whole; an area's age groups make its total; its
nationalities make its population, and its mother tongues do, for both
sexes and for men and women apart, which must add up column by column; the
age tables and the nationality tables agree on each area's population; and
the six areas make the country's 7,057,841.

**Second level.** Not written. The census publishes population by etrap and
city alone (volume 1, tables 1.4-1.15; volume 2, tables 2.2-2.7), for the
etraps as they stood in December 2022, and the boundary file draws another
division. The two were set side by side velayat by velayat (``ETRAP_GAP``),
with the census's own towns and villages placed on the drawn polygons by
GeoNames' points (whose populations are the census's): in no velayat is a
drawn polygon shown to hold the ground of the etrap the census counts under
its name. Most are shown not to -- even in Ahal, where the seven names
match, the towns of Babadaýhan and Gaňňaly lie in the polygon drawn as Tejen
and Berkarar in the one drawn as Kaka, and Ashgabat in the one drawn as Ak
Bugday. Eight polygons hold their etrap's placed towns and no other etrap's
(``UNSHOWN``), but a town's point places no border, and each lies in a
velayat whose division around it is not the census's; each says so on its
own record. Every drawn district carries its velayat's reason, and the
reason displaces an older encyclopaedic figure (``displaces_before``):
Wikidata's 144,119 on Ak Bugday is the etrap without Ashgabat, its 123,190
on Balkanabat the city without Gumdag and Jebel, and its 44,716 on Hojambaz
the count of 1995.

Usage:
    python -m scripts.fetch_census.turkmenistan_census
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, \
    write_json
from .cod_ps_age import grouped_median
from .kyrgyzstan_census import figures

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import as_drawn, read_json, shard_name  # noqa: E402

ISO3 = "TKM"
YEAR = 2022
OUT = "turkmenistan_census.json"
NATIONAL = 7_057_841
SITE = PROCESSED.parent.parent / "site" / "data"
BASE = "https://stat.gov.tm/population-census-pdfs/results/en/"
AGES_URL = BASE + "2.pdf"
NATIONALITY_URL = BASE + "4.pdf"
PAGE = "https://stat.gov.tm/en/population-census"
AGES_SOURCE = ("State Committee of Turkmenistan on Statistics, Results of the Complete "
               "Population and Housing Census of Turkmenistan 2022, volume 2: Age and sex "
               "composition of the population, tables 2.11-2.16")
NATIONALITY_SOURCE = ("State Committee of Turkmenistan on Statistics, Results of the Complete "
                      "Population and Housing Census of Turkmenistan 2022, volume 4: National "
                      "composition of the population and language proficiency, tables 4.3-4.8 "
                      "and 4.12-4.29")
LICENCE = "Official statistics of the State Committee of Turkmenistan on Statistics"

# The census's areas -> the drawn velayat that holds them.
AREAS = {"Ashgabat city": "Ahal", "Ahal velayat": "Ahal", "Balkan velayat": "Balkan",
         "Dashoguz velayat": "Dasoguz", "Lebap velayat": "Lebap", "Mary velayat": "Mary"}
AREA = re.compile(r"of\s+(?:the\s+)?(?:population\s+)?(?:\((?:male|female)\)\s+)?(?:of\s+)?"
                  r"(Ashgabat\s+city|Ahal\s+velayat|Balkan\s+velayat|Dashoguz\s+velayat|"
                  r"Lebap\s+velayat|Mary\s+velayat)")
GROUPS = [(0, 0), (1, 4)] + [(lo, lo + 4) for lo in range(5, 85, 5)] + [(85, None)]
NATIONALITIES = {
    "turkmens": "Turkmen", "uzbeks": "Uzbek", "russians": "Russian", "balochi": "Baloch",
    "azerbaijanis": "Azerbaijani", "armenians": "Armenian", "kazakhs": "Kazakh",
    "persians": "Persian", "tatars": "Tatar", "kurds": "Kurdish", "afghans": "Afghan",
    "ukrainians": "Ukrainian", "karakalpaks": "Karakalpak", "lezgins": "Lezgin",
    "koreans": "Korean", "other nationalities": "Other",
}
TONGUES = ["Turkmen", "Russian", "Ukrainian", "Uzbek", "Kazakh", "Tatar", "Armenian",
           "Azerbaijani", "Baloch", "Other languages"]
TONGUE_LABEL = {"Baloch": "Balochi"}
DASHES = ("-", "–", "−")
RELIGION_GAP = gap(NOT_AVAILABLE, (
    "None of the eleven volumes of the 2022 census results (population number and location; "
    "age and sex; education; national composition and language; fertility; migration and "
    "citizenship; sources of livelihood; households; employment; housing stock; housing "
    f"conditions -- {PAGE}) tabulates religion, for the country or any velayat."))
# Why no drawn etrap takes a 2022 figure, velayat by velayat: the census's
# etraps and cities of December 2022 (volume 1, tables 1.4-1.15) against the
# polygons the boundary file draws, with the census's towns placed on those
# polygons by GeoNames' points, whose populations are the census's own.
ETRAP_GAP = {
    "Ahal": (
        "The census counts Ahal's seven etraps under the names the map draws, but not on the "
        "same ground: of the census's towns, Babadaýhan (Babadayhan etrap) and Gaňňaly "
        "(Sarahs etrap) lie in the polygon drawn as Tejen, Berkarar (Ak bugday etrap) in the "
        "one drawn as Kaka, the new city of Arkadag, counted apart from every etrap, in the "
        "one drawn as Gokdepe, and Ashgabat, a city with the status of a velayat, in the one "
        "drawn as Ak Bugday."),
    "Balkan": (
        "The census counts Balkanabat and Türkmenbaşy cities and six etraps -- Esenguly, "
        "Bereket, Magtymguly, Gyzylarbat, Etrek and Türkmenbaşy -- where the map draws "
        "Avaza, Balkanabat, Bereket, Etrek, Hazar, Magtymguly and Turkmenbasy: the city of "
        "Gyzylarbat lies in the polygon drawn as Magtymguly, Esenguly in the one drawn as "
        "Etrek, Türkmenbaşy city in the one drawn as Avaza, and Oglanly, a town the census "
        "counts within Balkanabat city, in the one drawn as Turkmenbasy; Hazar, which the "
        "census also counts within Balkanabat city, is drawn as a polygon of its own."),
    "Dasoguz": (
        "The census counts Daşoguz city and seven etraps -- Boldumsaz, Köneürgenç, Akdepe, "
        "Saparmyrat Türkmenbaşy, Görogly, Şabat and Ruhubelent -- where the map draws "
        "Gubadag, Gurbansoltan Eje and S.A. Nyýazow besides five of them: Daşoguz city "
        "(201,142 people) lies in the polygon drawn as Boldumsaz, and Andalyp (Ylanly), "
        "which the census counts in Akdepe etrap, in the one drawn as Gurbansoltan Eye."),
    "Lebap": (
        "The census counts Türkmenabat city and eight etraps -- Darganata, Danew, Kerki, "
        "Saýat, Halaç, Hojambaz, Çärjew and Köýtendag -- where the map draws thirteen "
        "polygons: Dostluk, Döwletli and Farap, which the census counts within Köýtendag, "
        "Hojambaz and Çärjew etraps, are drawn as polygons of their own, one polygon has no "
        "name and Saýat is drawn twice; the city of Hojambaz lies in the polygon drawn as "
        "Halac, Kerki in the one drawn as Dostluk, Seydi, a city of Danew etrap, in the one "
        "drawn as Ferap, and Türkmenabat, a city counted apart from every etrap, in the one "
        "drawn as Carjew."),
    "Mary": (
        "The census counts Mary and Baýramaly cities and nine etraps -- Baýramaly, "
        "Wekilbazar, Ýolöten, Garagum, Mary, Murgap, Sakarçäge, Tagtabazar and Türkmengala "
        "-- where the map draws 24 polygons: eleven with no name, Bayramaly and Mary twice "
        "each, and Oguzhan, Serhetabat and Tedzhen Sovkhoz, which the census does not count "
        "as etraps (Oguzhan is a town of Murgap etrap, Serhetabat a city of Tagtabazar); "
        "the city of Türkmengala lies in the polygon drawn as Yoloten, and Ýagtyýol, "
        "Garagum etrap's one town, in the larger of the two drawn as Bayramaly, with "
        "Baýramaly city, which the census counts apart from every etrap."),
}
# The drawn polygons that hold every town GeoNames places of the etrap whose
# name they bear, and no town the census counts in another etrap. A
# town's point places no border, and each of these lies in a velayat whose
# division around it is not the census's (ETRAP_GAP), so none is shown to be
# the census's etrap; each says what was found on its own record.
#
# Measured on the boundary file at full resolution: the towns by point in
# polygon, the neighbours by shared border. Gubadag, S.A. Nyýazow and Oguzhan
# are drawn etraps the census no longer counts, so their ground lies in some
# census etrap, and that may be a neighbour's.
NOT_COUNTED = "which the census does not count as an etrap"
UNPLACED_DASOGUZ = ("the towns of Şabat and Ruhubelent, etraps the census counts and the map "
                    "does not draw, are not placed")
UNSHOWN = {
    "Ahal": {
        "Baherden": (
            "The polygon drawn as Baherden holds Bäherden etrap's towns, Bäherden and Arçman, "
            "and its village of Akdepe, but also Durdyhan and Tutlygala, villages GeoNames "
            "places in Balkan velayat that are not among the settlements the census counts "
            "in Bäherden etrap (volume 1, tables 1.5 and 1.10)."),
    },
    "Balkan": {
        "Bereket": (
            "The polygon drawn as Bereket holds Bereket, the etrap's one town, and no town "
            "the census counts in another etrap; that places no border, and each of the "
            "four polygons it borders -- Magtymguly, Turkmenbasy, Etrek and Balkanabat -- "
            "holds or lacks a town the census counts elsewhere."),
    },
    "Dasoguz": {
        "Gorogly": (
            "The polygon drawn as Gorogly holds Görogly, the etrap's one town, and no town "
            "the census counts in another etrap; that places no border, it borders the one "
            f"drawn as S.A. Nyyazow, {NOT_COUNTED}, and {UNPLACED_DASOGUZ}."),
        "Koneurgenc": (
            "The polygon drawn as Koneurgenc holds Köneürgenç city and no town the census "
            "counts in another etrap, but the etrap's other town, Bereket, is not placed; "
            f"it borders the one drawn as Gubadag, {NOT_COUNTED}, and {UNPLACED_DASOGUZ}."),
        "Saparmyrat Turkmenbasy": (
            "The polygon drawn as Saparmyrat Turkmenbasy holds the etrap's two towns and no "
            "town the census counts in another etrap; that places no border, it borders the "
            f"one drawn as Gubadag, {NOT_COUNTED}, and {UNPLACED_DASOGUZ}."),
    },
    "Lebap": {
        "Darganata": (
            "The polygon drawn as Darganata holds Gazojak and Darganata (Birata), two of the "
            "etrap's three towns, and no town the census counts in another etrap; that "
            "places no border, and the one polygon of Lebap it borders has no name."),
    },
    "Mary": {
        "Sakarcage": (
            "The polygon drawn as Sakarcage holds Sakarçäge, Şatlyk and Parahat, three of "
            "the etrap's four towns, and no town the census counts in another etrap; that "
            "places no border, and it borders a polygon with no name and the one drawn as "
            f"Oguzhan, {NOT_COUNTED}."),
        "Wekilbazar": (
            "GeoNames places neither of Wekilbazar etrap's towns (Wekilbazar and the town "
            "named after Mollanepes), so nothing but its name ties the polygon drawn as "
            "Wekilbazar to the census's etrap, and it borders four polygons with no name."),
    },
}
ETRAP_TAIL = (
    " No drawn polygon is shown to hold the ground of an etrap the census counts, so no "
    "etrap's figure is written. The census publishes population by etrap and city alone "
    "(volume 1, tables 1.4-1.15; volume 2, tables 2.2-2.7); age, nationality and mother "
    "tongue by velayat only (volumes 2 and 4).")
# An older encyclopaedic figure on a drawn etrap is not this census's either:
# the reason displaces it (see build_entities.merge_adapter).
DISPLACES_BEFORE = 2023


def etrap_gap(velayat: str | None, name: str | None = None) -> dict[str, Any]:
    """The velayat's evidence, the polygon's own where it has some, and the rule."""
    if velayat not in ETRAP_GAP:
        raise SystemExit(f"turkmenistan_census: no etrap reason for velayat {velayat!r}")
    own = UNSHOWN.get(velayat, {}).get(name or "")
    return gap(NOT_AVAILABLE, "Turkmenistan's 2022 census and the boundary file divide "
               f"{velayat} differently. " + ETRAP_GAP[velayat]
               + (f" {own}" if own else "") + ETRAP_TAIL)


def check_unshown(a1: list[dict[str, Any]], a2: list[dict[str, Any]]) -> None:
    """Every polygon UNSHOWN speaks for is drawn, once, in its velayat."""
    region = {u["id"]: u["name"] for u in a1}
    drawn = Counter((region.get(u["parent"]), u["name"]) for u in a2)
    for velayat, names in UNSHOWN.items():
        if velayat not in region.values():
            continue
        for name in names:
            if drawn[(velayat, name)] != 1:
                raise SystemExit(f"turkmenistan_census: {name!r} is drawn "
                                 f"{drawn[(velayat, name)]} times in {velayat}")


def tokens_of(line: str) -> tuple[str, list[str]]:
    """('1–4 years', ['227', '635', ...]): the label, then the figures."""
    parts = line.split()
    for i, token in enumerate(parts):
        if token[0].isdigit() and not re.match(r"^\d+[–-]\d+$", token) and not (
                i + 1 < len(parts) and parts[i + 1] in ("years", "year", "years,")):
            return " ".join(parts[:i]), parts[i:]
        if token in DASHES and i > 0:
            return " ".join(parts[:i]), parts[i:]
    return line, []


def figured(tokens: list[str]) -> bool:
    return bool(tokens) and all(re.fullmatch(r"\d+|[-–−]", t) for t in tokens)


ANY_TITLE = re.compile(r"(?m)^\s*\d\.\d+\.\s*\S")


def area_pages(pages: list[str], title: str) -> dict[str, list[str]]:
    """{area: [the text of each of its tables whose title matches ``title``]}.

    A table runs from its title to the next table's, across pages; two
    tables can share a page.
    """
    text = "\n".join(pages)
    starts = [m.start() for m in ANY_TITLE.finditer(text)] + [len(text)]
    out: dict[str, list[str]] = {}
    for m in re.finditer(title, text):
        end = next((s for s in starts if s > m.start() + 5), len(text))
        head = " ".join(text[m.start():m.start() + 300].split())
        area = AREA.search(head)
        if area:
            out.setdefault(" ".join(area.group(1).split()), []).append(text[m.start():end])
    return out


def age_row(tokens: list[str], where: str) -> tuple[int, int, int]:
    """The whole population's (both sexes, men, women) from a row of nine figures.

    A figure split in the wrong place ('168 04' for 16 804, Dashoguz's 20-24)
    reads no way at all; then each pair of tokens whose second is too short
    to be a group of thousands is tried joined, and a single repair that
    makes every figure add up is taken, and logged.
    """
    def ok(v: list[int]) -> bool:
        return v[6:9] == [a + b for a, b in zip(v[0:3], v[3:6])]
    found = figures(tokens, 9, ok, triples=True)
    if not found:
        repairs = []
        for i in range(len(tokens) - 1):
            if tokens[i].isdigit() and tokens[i + 1].isdigit() and len(tokens[i + 1]) < 3:
                joined = tokens[:i] + [tokens[i] + tokens[i + 1]] + tokens[i + 2:]
                repairs += [(i, v) for v in figures(joined, 9, ok, triples=True)]
        if len(repairs) == 1:
            i, reading = repairs[0]
            log(f"  {where}: '{tokens[i]} {tokens[i + 1]}' read as one figure, the only "
                f"reading that adds up")
            found = [reading]
    if len(found) != 1:
        raise SystemExit(f"turkmenistan_census: {where}: {len(found)} readings of "
                         f"{' '.join(tokens)!r}")
    return tuple(found[0][6:9])  # type: ignore[return-value]


def parse_ages(text: str, where: str) -> dict[str, Any]:
    """{'total': (b, m, w), 'groups': [(b, m, w), ...]} from one area's table 2.1x."""
    total = None
    groups: dict[tuple[int, int | None], tuple[int, int, int]] = {}
    pending = ""
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        if line.startswith("Out of the total"):
            break
        if line == "85 years and":
            pending = line
            continue
        if pending and line.startswith("older"):
            line, pending = f"{pending} {line}", ""
        label, tokens = tokens_of(line)
        if not figured(tokens):
            continue
        low = label.lower()
        if low == "total":
            total = age_row(tokens, f"{where} total")
            continue
        if low.startswith("under 1"):
            key = (0, 0)
        elif low.startswith("85"):
            key = (85, None)
        else:
            m = re.match(r"^(\d+)[–-](\d+) years", label)
            if not m:
                continue
            key = (int(m.group(1)), int(m.group(2)))
        if key in groups:
            raise SystemExit(f"turkmenistan_census: {where}: {label} twice")
        groups[key] = age_row(tokens, f"{where} {label}")
    if total is None or sorted(groups, key=lambda k: k[0]) != GROUPS:
        raise SystemExit(f"turkmenistan_census: {where}: total {total}, groups "
                         f"{sorted(groups, key=lambda k: k[0])}")
    made = tuple(sum(groups[g][i] for g in GROUPS) for i in range(3))
    if made != total:
        raise SystemExit(f"turkmenistan_census: {where}: age groups make {made} of {total}")
    return {"total": total, "groups": [groups[g] for g in GROUPS]}


def parse_nationalities(text: str, where: str) -> dict[str, Any]:
    """{'total': n, 'groups': Counter} from one area's table 4.3-4.8 (the first count)."""
    total = None
    counts: Counter = Counter()
    before = ""
    for raw in text.splitlines():
        line = " ".join(raw.split())
        parts = line.split()
        split = next((i for i, t in enumerate(parts) if t[0].isdigit() or t in DASHES), None)
        if split is None:
            before = line
            continue
        label, rest = " ".join(parts[:split]), parts[split:]
        pct = next((i for i, t in enumerate(rest) if re.search(r"[.,]", t)), None)
        if pct is None or not all(t.isdigit() for t in rest[:pct]) or not rest[:pct]:
            continue
        count = int("".join(rest[:pct]))
        name = label.lower()
        if name == "all nationalities":
            total = count
            continue
        group = NATIONALITIES.get(name) or NATIONALITIES.get(f"{before} {label}".lower())
        if group is None:
            raise SystemExit(f"turkmenistan_census: {where}: nationality {label!r} not known")
        counts[group] += count
    if total is None or sum(counts.values()) != total:
        raise SystemExit(f"turkmenistan_census: {where}: nationalities make "
                         f"{sum(counts.values()):,} of {total}")
    return {"total": total, "groups": counts}


def tongue_rows(text: str) -> list[list[str]]:
    """The tokens of each 'All nationalities' row of a mother-tongue table, in order."""
    rows = []
    lines = [" ".join(raw.split()) for raw in text.splitlines()]
    for i, line in enumerate(lines):
        joined = line
        if line == "All" and i + 1 < len(lines):
            joined = f"All {lines[i + 1]}"
        if joined.startswith("All nationalities"):
            rows.append(joined.split()[2:])
    return rows


def parse_tongues(both: list[str], men: list[str], women: list[str], where: str) -> list[int]:
    """The area's mother tongues (total first), the one reading that adds up three ways."""
    def read(tokens: list[str]) -> list[list[int]]:
        return figures(tokens, 11, lambda v: v[0] == sum(v[1:]))
    found = [(b, m, w) for b in read(both) for m in read(men) for w in read(women)
             if all(x == y + z for x, y, z in zip(b, m, w))]
    if len(found) != 1:
        raise SystemExit(f"turkmenistan_census: {where}: {len(found)} readings of the mother "
                         f"tongues")
    return found[0][0]


def pdf_pages(blob: bytes) -> list[str]:
    import logging

    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages]


def read_areas(age_pages: list[str], nat_pages: list[str]) -> dict[str, dict[str, Any]]:
    ages = area_pages(age_pages, r"2\.1[1-6]\.\s+Distribution of the number of population of")
    nats = area_pages(nat_pages, r"4\.[3-8]\.\s*National composition of the population of")
    tongues = area_pages(nat_pages, r"4\.(?:1[2-9]|2\d)\.\s+Distribution of the(?: the)? number")
    out: dict[str, dict[str, Any]] = {}
    for area in AREAS:
        for name, found in (("age", ages), ("nationality", nats), ("mother tongue", tongues)):
            if area not in found:
                raise SystemExit(f"turkmenistan_census: no {name} table for {area}; found "
                                 f"{sorted(found)}")
        age = parse_ages("\n".join(ages[area]), area)
        nat = parse_nationalities("\n".join(nats[area]), area)
        rows = tongue_rows("\n".join(tongues[area]))
        if len(rows) != 3:
            raise SystemExit(f"turkmenistan_census: {area}: {len(rows)} 'All nationalities' "
                             f"rows in the mother-tongue tables")
        tongue = parse_tongues(*rows, area)
        if not age["total"][0] == nat["total"] == tongue[0]:
            raise SystemExit(f"turkmenistan_census: {area}: ages {age['total'][0]:,}, "
                             f"nationalities {nat['total']:,}, mother tongues {tongue[0]:,}")
        out[area] = {"age": age, "nationality": nat["groups"],
                     "tongues": Counter(dict(zip(TONGUES, tongue[1:])))}
        log(f"  {area}: {age['total'][0]:,} people")
    country = sum(a["age"]["total"][0] for a in out.values())
    if country != NATIONAL:
        raise SystemExit(f"turkmenistan_census: the areas make {country:,}, the country "
                         f"{NATIONAL:,}")
    return out


def drawn_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (as_drawn(read_json(SITE / "admin1" / shard_name(ISO3), [])),
            as_drawn(read_json(SITE / "admin2" / shard_name(ISO3), [])))


def build(areas: dict[str, dict[str, Any]], a1: list[dict[str, Any]],
          a2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shape = {u["name"]: u for u in a1}
    out: list[dict[str, Any]] = []
    src = [{"field": "population/sex_ratio/median_age", "name": AGES_SOURCE, "url": PAGE,
            "license": LICENCE},
           {"field": "ethnicity/language", "name": NATIONALITY_SOURCE, "url": PAGE,
            "license": LICENCE}]
    for velayat in sorted(set(AREAS.values())):
        if velayat not in shape:
            raise SystemExit(f"turkmenistan_census: the map draws no {velayat!r}")
        parts = [a for a, v in AREAS.items() if v == velayat]
        total = tuple(sum(areas[a]["age"]["total"][i] for a in parts) for i in range(3))
        groups = [sum(areas[a]["age"]["groups"][g][0] for a in parts) for g in range(len(GROUPS))]
        nationality = sum((areas[a]["nationality"] for a in parts), Counter())
        tongues = sum((areas[a]["tongues"] for a in parts), Counter())
        note = (f"The polygon drawn as {velayat} holds {' and '.join(parts)}, which the census "
                f"counts apart (Ashgabat is a city with the status of a velayat); it carries "
                f"their sum." if len(parts) > 1 else None)
        extra = f" {note}" if note else ""
        both, men, women = total
        out.append(record(
            f"TKM-CENSUS-{shape[velayat]['id']}", velayat, level="admin1", parent=ISO3,
            country=ISO3, match_by="shape_id", shape_id=shape[velayat]["id"],
            aliases=parts,
            population=measure(both, year=YEAR, source=AGES_SOURCE),
            population_note=note,
            sex_ratio=measure(round(100 * men / women, 1), year=YEAR, source=AGES_SOURCE,
                              unit="males_per_100_females"),
            sex_ratio_note="Men per 100 women, from the census's counts." + extra,
            median_age=measure(grouped_median([(lo, hi, n) for (lo, hi), n
                                               in zip(GROUPS, groups)]),
                               year=YEAR, source=AGES_SOURCE),
            median_age_note=("Median interpolated within the age group holding the middle "
                             "person (under 1, 1-4, then five-year groups to 85 and older); "
                             "the census publishes no single years by velayat." + extra),
            ethnicity=shares(dict(nationality)),
            ethnicity_year=YEAR,
            ethnicity_note=("Nationality (milli degişliligi) as each person declared it: the "
                            "fifteen most numerous in the country, the rest as other "
                            "nationalities (tables 4.3-4.8)." + extra),
            language=shares({TONGUE_LABEL.get(k, k): v for k, v in tongues.items()}),
            language_year=YEAR,
            language_note=("Mother tongue, as each person named it: the nine languages the "
                           "census tabulates, the rest as other languages (tables 4.12-4.29, "
                           "first row)." + extra),
            religion=RELIGION_GAP,
            sources=src))
    region_name = {u["id"]: u["name"] for u in a1}
    check_unshown(a1, a2)
    for unit in a2:
        why = etrap_gap(region_name.get(unit["parent"]), unit["name"])
        out.append(record(
            f"TKM-CENSUS-{unit['id']}", unit["name"], level="admin2",
            parent=f"TKM-CENSUS-{unit['parent']}", parent_name=region_name.get(unit["parent"]),
            country=ISO3, match_by="shape_id", shape_id=unit["id"],
            population=dict(why, displaces_before=DISPLACES_BEFORE),
            median_age=dict(why, displaces_before=DISPLACES_BEFORE),
            sex_ratio=dict(why, displaces_before=DISPLACES_BEFORE),
            ethnicity=dict(why), language=dict(why),
            religion=RELIGION_GAP))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("turkmenistan_census: 2022 census, volumes 2 and 4")
    age_pages = pdf_pages(http_get(AGES_URL, binary=True, timeout=300))  # type: ignore[arg-type]
    nat_pages = pdf_pages(http_get(NATIONALITY_URL, binary=True,  # type: ignore[arg-type]
                                   timeout=300))
    areas = read_areas(age_pages, nat_pages)
    a1, a2 = drawn_units()
    out = build(areas, a1, a2)
    for r in out:
        if r["level"] == "admin1":
            log(f"    {r['name']}: {r['population']['value']:,}, median "
                f"{r['median_age']['value']}, ratio {r['sex_ratio']['value']}, "
                f"{r['ethnicity'][0]['group']} {r['ethnicity'][0]['pct']}%, "
                f"{r['language'][0]['group']} {r['language'][0]['pct']}%")
    log(f"  admin2: {sum(r['level'] == 'admin2' for r in out)} districts given the reason")
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
