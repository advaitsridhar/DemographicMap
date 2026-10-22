#!/usr/bin/env python3
"""Mauritania -- the 2023 census (RGPH 2023) by wilaya and moughataa.

ANSADE's leaflet of the census's first results, *Population des Wilayas,
Moughataa et Communes* (2024), prints everyone by sex for the 15 wilayas, the
63 moughataas and every commune: 4,927,532 people counted between 25 December
2023 and 8 January 2024. ansade.mr does not answer an automated client; the
leaflet is read from ANSADE's own file (wp-content/uploads/2024/09) as the
Internet Archive captured it on 25 September 2025, and cited so. Where the
Archive refuses, the copy the Centre Rachad publishes stands in, and the
source says whose copy it is; the run logs which was read and its sha256.

**The ground the map draws.** The map draws 13 wilayas (Nouakchott as one) and
57 moughataas on their lines of the 2013 census. OCHA's 2024 boundaries of the
63 moughataas were placed on the map's polygons point by point:

* six moughataas were made from one each since: Adel Bagrou from Amourj, Touil
  from Tintane, Lexeiba 1 from Kaédi, Maal from Aleg, Tékane from R'Kiz and
  Wompou from Sélibaby. Each of those six polygons takes the two counts added.
* Chami is drawn in Inchiri; the census counts it in Dakhlet Nouadhibou. Its
  count goes to Chami's polygon and to Inchiri, and Dakhlet Nouadhibou is the
  moughataa of Nouadhibou.
* Nouakchott is three wilayas since 2014; the map's Nouakchott takes the
  three. Its nine moughataas are not bound: the lines drawn for them do not
  follow the moughataas as OCHA's boundaries of the census's units draw them
  (29 of the 33 points of OCHA's Ksar fall in what is drawn as Ouad Naga; its
  admin2 labels Toujounine and Teyarett are swapped against the communes it
  files under them, so neither is named), and the polygon drawn as Ouad Naga
  holds the outer parts of seven of them. Each says why, citing OCHA's
  boundaries, which the reason measures them by.

Written for every other wilaya and moughataa: population and sex ratio (men
per 1,000 women), 2023.

**Ages.** The leaflet gives no ages. ANSADE's report on the census's structure
by sex and age (*Thème 2 : Structure par sexe et par âge de la population*,
2024, on admin.ansade.mr, which answers a script where ansade.mr does not)
gives every wilaya's population by five-year age group in its annex (Tableau
A.2.2), and no moughataa's. Each wilaya the map draws on the census's ground
takes the median interpolated from that table, Nouakchott's three wilayas
added group by group: the census's median, in front of OCHA's projection for
2022. Inchiri and Dakhlet Nouadhibou do not: the table counts Chami in Dakhlet
Nouadhibou and gives it no ages apart, and the map draws Chami in Inchiri.
Each moughataa says the census tabulates ages by wilaya only, citing both.

**Checks before anything is written.** Every row's men and women make its
total; each moughataa's communes make it; each wilaya's moughataas make the
wilaya's total row and the first page's table; the wilayas make 4,927,532.
In the age table, each wilaya's eighteen groups make its total row, and the
leaflet's count, within the table's rounding (three people); the country's
column is 4,927,532, and its median (18.7) the report's 18 in whole years.

Usage:
    python -m scripts.fetch_census.mauritania_census
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .cod_ps_age import grouped_median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob, laid_out  # noqa: E402

# ANSADE's own file, and the Internet Archive's capture of it (eleven captures
# from November 2024 to September 2025; CDX probe 0c45ffc).
OFFICE = "https://ansade.mr/wp-content/uploads/2024/09/Depliant-RGPH5-1.pdf"
URL = "https://web.archive.org/web/20250925063203id_/" + OFFICE
# The same leaflet as the Centre Rachad republishes it, read only where the
# Archive refuses.
MIRROR = "https://centre-rachad.org/wp-content/uploads/2024/10/Depliant-RGPH5_vf.pdf"
SOURCE = ("Agence Nationale de la Statistique et de l'Analyse Démographique et Economique "
          "(ANSADE), Recensement Général de la Population et de l'Habitat (RGPH 2023), "
          "Population des Wilayas, Moughataa et Communes (2024)")
LICENCE = "ANSADE publication (reuse with attribution)"
YEAR = 2023
# What every record cites: the office's file as the Archive keeps it; main()
# names the Centre Rachad's copy instead where that is the one read.
CITE: dict[str, Any] = {"name": SOURCE, "url": URL, "page": OFFICE, "license": LICENCE,
                        "year": YEAR}
# ANSADE's report on the census's structure by sex and age, on the office's
# own site: its annex's Tableau A.2.2 gives every wilaya by age group.
AGES_URL = "https://admin.ansade.mr/wp-content/uploads/2024/09/Theme-2.pdf"
AGES_SOURCE = ("Agence Nationale de la Statistique et de l'Analyse Démographique et Economique "
               "(ANSADE), Recensement Général de la Population et de l'Habitat (RGPH-5, 2023), "
               "Thème 2 : Structure par sexe et par âge de la population (2024), Tableau A.2.2")
AGES_CITE: dict[str, Any] = {"name": AGES_SOURCE, "url": AGES_URL, "license": LICENCE,
                             "year": YEAR}
# The table's rows: under one year, 1-4, then five-year groups to 80 and over.
AGE_BOUNDS: list[tuple[int, int | None]] = (
    [(0, 0), (1, 4)] + [(low, low + 4) for low in range(5, 80, 5)] + [(80, None)])
# The report's median for the country, in whole years (Tableau 2.6).
NATIONAL_MEDIAN = 18
# Wilayas the map draws on other ground than the census's: the table counts
# Chami in Dakhlet Nouadhibou, with no ages of its own, and the map draws it
# in Inchiri.
NO_CENSUS_MEDIAN = {"Dakhlet Nouadhibou", "Inchiri"}
NATIONAL = (2_375_470, 2_552_062, 4_927_532)
OUT = "mauritania_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

WILAYAS = ["Hodh Chargui", "Hodh El Gharbi", "Assaba", "Gorgol", "Brakna", "Trarza", "Adrar",
           "Dakhlet Nouadhibou", "Tagant", "Guidimakha", "Tiris Zemmour", "Inchiri",
           "Nouakchott-Ouest", "Nouakchott-Nord", "Nouakchott-Sud"]
NOUAKCHOTT = ["Nouakchott-Ouest", "Nouakchott-Nord", "Nouakchott-Sud"]

# The map's wilayas (folded) -> the census's.
WILAYA_OF = {"hodhechchargui": "Hodh Chargui", "hodhelgharbi": "Hodh El Gharbi",
             "assaba": "Assaba", "gorgol": "Gorgol", "brakna": "Brakna", "trarza": "Trarza",
             "adrar": "Adrar", "dakhletnouadhibou": "Dakhlet Nouadhibou", "tagant": "Tagant",
             "guidimaka": "Guidimakha", "tiriszemmour": "Tiris Zemmour", "inchiri": "Inchiri",
             "nouakchott": "Nouakchott"}
# The map's moughataas (folded) -> (census wilaya, the census's moughataas, folded).
MOUGHATAAS: dict[str, tuple[str, list[str]]] = {
    "amourj": ("Hodh Chargui", ["amourj", "adelbagrou"]),
    "basseknou": ("Hodh Chargui", ["bassiknou"]),
    "djigueni": ("Hodh Chargui", ["djigueni"]),
    "moughataadenneama": ("Hodh Chargui", ["nema"]),
    "nbeiketlehouach": ("Hodh Chargui", ["nbeiketlahwache"]),
    "oualata": ("Hodh Chargui", ["oualata"]),
    "timbedgha": ("Hodh Chargui", ["timbedra"]),
    "eayouneelatrous": ("Hodh El Gharbi", ["aioun"]),
    "koubenni": ("Hodh El Gharbi", ["koubenni"]),
    "tamchekett": ("Hodh El Gharbi", ["tamcheket"]),
    "tintane": ("Hodh El Gharbi", ["tintane", "touil"]),
    "barkeol": ("Assaba", ["barkewol"]),
    "boumdeid": ("Assaba", ["boumdeid"]),
    "guerrou": ("Assaba", ["guerou"]),
    "kankossa": ("Assaba", ["kankoussa"]),
    "kiffa": ("Assaba", ["kiffa"]),
    "kaedi": ("Gorgol", ["kaedi", "lexeiba"]),
    "mbout": ("Gorgol", ["mbout"]),
    "maghama": ("Gorgol", ["maghama"]),
    "monguel": ("Gorgol", ["mounguel"]),
    "aleg": ("Brakna", ["aleg", "maal"]),
    "bababe": ("Brakna", ["bababe"]),
    "boghe": ("Brakna", ["boghe"]),
    "mbagne": ("Brakna", ["mbagne"]),
    "magtalahjar": ("Brakna", ["magtalahjar"]),
    "boutilimitt": ("Trarza", ["boutilimit"]),
    "keurmacene": ("Trarza", ["keurmacene"]),
    "mederdra": ("Trarza", ["mederdra"]),
    "rkiz": ("Trarza", ["rkiz", "tekane"]),
    "rosso": ("Trarza", ["rosso"]),
    "aoujeft": ("Adrar", ["aoujeft"]),
    "atar": ("Adrar", ["atar"]),
    "chinguitti": ("Adrar", ["chinguitti"]),
    "ouadane": ("Adrar", ["ouadane"]),
    "nouadhibou": ("Dakhlet Nouadhibou", ["nouadhibou"]),
    "chami": ("Dakhlet Nouadhibou", ["chami"]),
    "akjoujt": ("Inchiri", ["akjoujt"]),
    "benichab": ("Inchiri", ["bennechab"]),
    "elmejrya": ("Tagant", ["moudjeria"]),
    "tichitt": ("Tagant", ["tichit"]),
    "tijigja": ("Tagant", ["tidjikja"]),
    "birmoghrein": ("Tiris Zemmour", ["birmoghrein"]),
    "fderick": ("Tiris Zemmour", ["fderick"]),
    "zoueratt": ("Tiris Zemmour", ["zouerate"]),
    "ghabou": ("Guidimakha", ["ghabou"]),
    "ouldyenge": ("Guidimakha", ["ouldyenge"]),
    "selibabi": ("Guidimakha", ["selibaby", "wompou"]),
}
# The census's spellings that fold differently from the ones above.
SPELLINGS = {"birmogrein": "birmoghrein", "fdeirik": "fderick", "zoueratt": "zouerate",
             "tidjikdja": "tidjikja",
             "timbedra": "timbedra", "fdeirick": "fderick", "zoueirat": "zouerate",
             "zouerat": "zouerate", "birmoughrein": "birmoghrein", "tidjikja": "tidjikja",
             "tijikja": "tidjikja", "moudjeria": "moudjeria", "tichitt": "tichit",
             "lexeibe": "lexeiba", "lexeibeun": "lexeiba", "lexeibaun": "lexeiba",
             "kankossa": "kankoussa", "barkeol": "barkewol", "monguel": "mounguel",
             "nbeiketlehwach": "nbeiketlahwache", "selibabi": "selibaby", "magtalahjar":
             "magtalahjar", "aleg": "aleg"}
NOUAKCHOTT_POLYGONS = {"arafat", "darnaim", "elmina", "ksar", "riyadh", "sebkha", "tevraghzein",
                       "teyarett", "toujounine"}
NOT_BOUND = {
    **{k: ("The 2023 census counts Nouakchott's nine moughataas, but the lines drawn here for "
           "them do not follow the moughataas as OCHA's 2024 boundaries of the census's units "
           "draw them: OCHA's Ksar, for one, lies mostly over what is drawn here as Ouad Naga. "
           "No count is placed on these polygons; Nouakchott as a whole carries the census's "
           "count of its three wilayas.") for k in NOUAKCHOTT_POLYGONS},
    "ouadnaga": ("The 2023 census counts the moughataa of Ouad Naga, but the polygon drawn here "
                 "also takes in the outer parts of seven of Nouakchott's moughataas as OCHA's "
                 "2024 boundaries of the census's units draw them, so the moughataa's count is "
                 "not this polygon's."),
}
# Seats drawn at or beyond their polygon's edge (OCHA's capitals and GeoNames'
# points against the map's polygons).
EDGE = {
    "akjoujt": (" The town of Akjoujt, where nearly all of the moughataa's people live, lies on "
                "this polygon's edge with the one drawn as Benichab."),
    "selibabi": (" The town of Sélibaby, the moughataa's seat, is drawn about 5 km outside this "
                 "polygon, in the one drawn as Ghabou."),
}
NO_AGES = ("The 2023 census's results give each moughataa's population by sex, not by age: "
           "its report on the population's structure by sex and age tabulates ages by wilaya "
           "only.")
# OCHA's boundaries of the census's units, by which the reasons of Nouakchott's
# moughataas and Ouad Naga measure the lines drawn here: cited for those notes.
COD_AB = {"name": "OCHA, Mauritania - Subnational Administrative Boundaries (COD-AB, 2024)",
          "url": "https://data.humdata.org/dataset/cod-ab-mrt", "license": "CC BY-IGO",
          "year": 2024}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def key(text: str) -> str:
    k = fold(text)
    return SPELLINGS.get(k, k)


def numbers(tokens: list[str]) -> list[list[tuple[int, int]]]:
    out = []
    for i in range(len(tokens)):
        options = []
        if tokens[i].isdigit() and not (len(tokens[i]) > 1 and tokens[i].startswith("0")):
            if len(tokens[i]) > 3:
                options.append((int(tokens[i]), i + 1))
            else:
                j = i + 1
                options.append((int(tokens[i]), j))
                while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
                    j += 1
                    options.append((int("".join(tokens[i:j])), j))
        out.append(options)
    return out


def row_of(line: str) -> tuple[str, tuple[int, int, int]] | None:
    """(label, (men, women, total)) for a line whose first figures make a row."""
    tokens = line.split()
    start = next((i for i, t in enumerate(tokens) if t.isdigit()), None)
    if not start:
        return None
    label = " ".join(tokens[:start])
    digits = []
    for t in tokens[start:]:
        if not t.isdigit():
            break
        digits.append(t)
    readings = numbers(digits)
    # Exact first; a row whose men and women miss its total by a person or two
    # is printed too (Néma's commune of Bangou: 6,108 + 7,564 against 13,673).
    for slack in (0, 2):
        for a, ea in (readings[0] if readings else []):
            for b, eb in (readings[ea] if ea < len(readings) else []):
                for c, _ in (readings[eb] if eb < len(readings) else []):
                    if abs(a + b - c) <= slack:
                        return label, (a, b, c)
    return None


def near(a: tuple[int, int, int], b: tuple[int, int, int], rows: int) -> bool:
    """The same figures within a person per row added: the leaflet rounds each cell
    on its own (Hodh Chargui's moughataas make 625,644 against its 625,643)."""
    return all(abs(a[k] - b[k]) <= max(rows, 2) for k in range(3))


def parse(text: str) -> dict[str, Any]:
    """{"wilayas": {name: (m, w, t)}, "moughataas": {wilaya: {key: {"name", "figures",
    "communes"}}}}, every sum checked."""
    lines = text.splitlines()
    summary: dict[str, tuple[int, int, int]] = {}
    blocks: dict[str, list[tuple[str, tuple[int, int, int]]]] = {}
    totals: dict[str, tuple[int, int, int]] = {}
    current = None
    wanted = {fold(w): w for w in WILAYAS}
    for line in lines:
        head = re.match(r"^\s*Wilaya\s*:\s*(.+?)\s+Population\b", line)
        if head:
            current = wanted.get(fold(head.group(1)))
            if current is None:
                raise SystemExit(f"mauritania_census: a block for {head.group(1)!r}")
            blocks[current] = []
            continue
        row = row_of(line)
        if row is None:
            continue
        label, figures = row
        total = re.match(r"^Total\s*:?\s*(.+)$", label)
        if total:
            name = fold(total.group(1))
            if name == "mauritanie":
                summary["Total"] = figures
            elif name in wanted:
                totals[wanted[name]] = figures
                current = None
            continue
        if current is None:
            if fold(label) in wanted and wanted[fold(label)] not in summary:
                summary[wanted[fold(label)]] = figures
            continue
        blocks[current].append((label, figures))
    if summary.get("Total") != NATIONAL or any(w not in summary for w in WILAYAS):
        raise SystemExit(f"mauritania_census: the first page reads {summary}")
    made = tuple(sum(summary[w][i] for w in WILAYAS) for i in range(3))
    if not near(made, NATIONAL, len(WILAYAS)):
        raise SystemExit(f"mauritania_census: the wilayas make {made}")
    moughataas: dict[str, dict[str, Any]] = {}
    for wilaya in WILAYAS:
        rows = blocks.get(wilaya)
        if not rows or totals.get(wilaya) != summary[wilaya]:
            raise SystemExit(f"mauritania_census: {wilaya}: block of {len(rows or [])} rows, "
                             f"total {totals.get(wilaya)} against {summary[wilaya]}")
        out: dict[str, Any] = {}
        i = 0
        while i < len(rows):
            name, figures = rows[i]
            # Nouakchott's moughataas are one commune each, printed on one line
            # with the name twice: "Ksar Ksar 29 043 28 715 57 758".
            words = name.split()
            half = len(words) // 2
            if words and len(words) % 2 == 0 and words[:half] == words[half:]:
                name = " ".join(words[:half])
                out[key(name)] = {"name": name, "figures": figures, "communes": [name]}
                i += 1
                continue
            acc, j, communes = (0, 0, 0), i + 1, []
            while j < len(rows) and acc[2] < figures[2] - 2:
                acc = tuple(acc[k] + rows[j][1][k] for k in range(3))
                communes.append(rows[j][0])
                j += 1
            if not near(acc, figures, len(communes)):
                raise SystemExit(f"mauritania_census: {wilaya}/{name}: its communes make {acc}, "
                                 f"not {figures}")
            out[key(name)] = {"name": name, "figures": figures, "communes": communes}
            i = j
        made = tuple(sum(m["figures"][k] for m in out.values()) for k in range(3))
        if not near(made, summary[wilaya], len(out)):
            raise SystemExit(f"mauritania_census: {wilaya}'s moughataas make {made}")
        moughataas[wilaya] = out
    return {"wilayas": summary, "moughataas": moughataas}


def parse_ages(text: str) -> dict[str, list[tuple[int, int | None, int]]]:
    """Each census wilaya's population by age group (Tableau A.2.2), with the
    country's as "Total", every column checked against its total row."""
    # The table's own title, not the text's mention of it ("le tableau A.2.2").
    title = re.search(r"Tableau A\.2\.2\s*:", text)
    if title is None:
        raise SystemExit("mauritania_census: the age report has no Tableau A.2.2")
    start = title.start()
    columns = len(WILAYAS) + 1
    rows: list[tuple[str, list[int]]] = []
    total: list[int] | None = None
    for line in text[start:].splitlines()[1:]:
        if line.strip().startswith("Source"):
            break
        tokens = line.split()
        figures: list[int] = []
        while tokens and tokens[-1].isdigit():
            figures.insert(0, int(tokens.pop()))
        if len(figures) != columns:
            continue
        label = " ".join(tokens)
        if fold(label).startswith("total"):
            total = figures
        else:
            rows.append((label, figures))
    if total is None or len(rows) != len(AGE_BOUNDS):
        raise SystemExit(f"mauritania_census: Tableau A.2.2 reads {len(rows)} age groups and "
                         f"{'a' if total else 'no'} total row")
    for (label, _), (low, high) in zip(rows[1:], AGE_BOUNDS[1:]):
        bounds = [int(n) for n in re.findall(r"\d+", label)]
        if bounds != ([low, high] if high is not None else [low]):
            raise SystemExit(f"mauritania_census: Tableau A.2.2's row {label!r} where "
                             f"{low}-{high} was expected")
    if total[-1] != NATIONAL[2]:
        raise SystemExit(f"mauritania_census: Tableau A.2.2's country is {total[-1]:,}")
    ages: dict[str, list[tuple[int, int | None, int]]] = {}
    for i, name in enumerate([*WILAYAS, "Total"]):
        groups = [(low, high, figures[i]) for (low, high), (_, figures) in zip(AGE_BOUNDS, rows)]
        made = sum(n for _, _, n in groups)
        if abs(made - total[i]) > 3:
            raise SystemExit(f"mauritania_census: {name}'s age groups make {made:,}, not its "
                             f"{total[i]:,}")
        ages[name] = groups
    median = grouped_median(ages["Total"])
    if median is None or not NATIONAL_MEDIAN <= median < NATIONAL_MEDIAN + 1:
        raise SystemExit(f"mauritania_census: the country's median comes to {median}, the "
                         f"report's {NATIONAL_MEDIAN}")
    return ages


def wilaya_median(wilaya: str, ages: dict[str, list[tuple[int, int | None, int]]],
                  counts: dict[str, tuple[int, int, int]]) -> tuple[float, str] | None:
    """The census's median for a wilaya as drawn, and its note; None where the map
    draws the wilaya on other ground."""
    if wilaya in NO_CENSUS_MEDIAN:
        return None
    parts = NOUAKCHOTT if wilaya == "Nouakchott" else [wilaya]
    for part in parts:
        made = sum(n for _, _, n in ages[part])
        if abs(made - counts[part][2]) > 3:
            raise SystemExit(f"mauritania_census: {part}'s age groups make {made:,}, the "
                             f"leaflet's count {counts[part][2]:,}")
    groups = [(low, high, sum(ages[part][i][2] for part in parts))
              for i, (low, high) in enumerate(AGE_BOUNDS)]
    median = grouped_median(groups)
    if median is None:
        return None
    whose = ("the three wilayas of Nouakchott by age, added group by group"
             if wilaya == "Nouakchott" else "the wilaya by age")
    return median, ("Interpolated within the five-year age group that holds the middle person, "
                    f"from the 2023 census's count of {whose} (Thème 2, Tableau A.2.2).")


def fields(figures: tuple[int, int, int], note: str, ages_noted: bool = False
           ) -> dict[str, Any]:
    """A unit's count and sex ratio, cited to the leaflet -- and its median-age
    reason, which quotes the leaflet, where the unit carries one."""
    men, women, total = figures
    return {"population": measure(total, year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "sources": [{**CITE, "field": "population/sex_ratio"
                         + ("/median_age note" if ages_noted else "")}]
            + ([{**AGES_CITE, "field": "median_age note"}] if ages_noted else [])}


def added(*parts: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(sum(p[k] for p in parts) for k in range(3))


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]],
          ages: dict[str, list[tuple[int, int | None, int]]] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    wil, mou = table["wilayas"], table["moughataas"]
    chami = mou["Dakhlet Nouadhibou"]["chami"]["figures"]
    nouadhibou = mou["Dakhlet Nouadhibou"]["nouadhibou"]["figures"]
    records: list[dict[str, Any]] = []
    report: list[str] = []
    for shape in admin1:
        k = fold(shape["name"])
        wilaya = WILAYA_OF.get(k)
        if wilaya is None:
            report.append(f"wilaya polygon {shape['name']!r}: not placed")
            continue
        if wilaya == "Nouakchott":
            figures = added(*(wil[w] for w in NOUAKCHOTT))
            note = ("The 2023 census's count for the three wilayas of Nouakchott together: "
                    + ", ".join(f"{w} {wil[w][2]:,}" for w in NOUAKCHOTT[:2])
                    + f" and {NOUAKCHOTT[2]} {wil[NOUAKCHOTT[2]][2]:,}.")
        elif wilaya == "Dakhlet Nouadhibou":
            figures = nouadhibou
            note = (f"The 2023 census counts {wil[wilaya][2]:,} people in the wilaya, with the "
                    f"moughataa of Chami ({chami[2]:,}); the map draws Chami in Inchiri, so "
                    "this is the moughataa of Nouadhibou, the rest of the wilaya.")
        elif wilaya == "Inchiri":
            figures = added(wil[wilaya], chami)
            note = (f"The 2023 census's count for the wilaya ({wil[wilaya][2]:,}) and for the "
                    f"moughataa of Chami ({chami[2]:,}), which the census counts in Dakhlet "
                    "Nouadhibou and the map draws here.")
        else:
            figures = wil[wilaya]
            note = "The 2023 census's count for the wilaya."
        seat: dict[str, Any] = {}
        unit = fields(figures, note)
        median = wilaya_median(wilaya, ages, wil) if ages else None
        if median:
            seat["median_age"] = measure(median[0], unit="years", year=YEAR, source=AGES_SOURCE)
            seat["median_age_note"] = median[1]
            unit["sources"].append({**AGES_CITE, "field": "median_age"})
        if wilaya == "Nouakchott":
            seat["capital"] = gap(NOT_AVAILABLE, (
                "The polygon is the city of Nouakchott, three wilayas since 2014 "
                "(Nouakchott-Ouest, Nouakchott-Nord and Nouakchott-Sud), each with a seat of "
                "its own."))
        records.append(record(f"MRT-RGPH2023-{fold(wilaya)}", shape["name"], level="admin1",
                              parent="MRT", country="MRT", match_by="shape_id",
                              shape_id=shape["id"], **seat, **unit))
    used: set[tuple[str, str]] = set()
    for shape in admin2:
        k = fold(shape["name"])
        if k in NOT_BOUND:
            records.append(record(
                f"MRT-RGPH2023-{k}", shape["name"], level="admin2", parent="MRT", country="MRT",
                match_by="shape_id", shape_id=shape["id"],
                population=gap(NOT_AVAILABLE, NOT_BOUND[k]),
                sex_ratio=gap(NOT_AVAILABLE, NOT_BOUND[k]),
                median_age=gap(NOT_AVAILABLE, NO_AGES),
                # The census the notes quote, not the source of a figure shown,
                # and OCHA's boundaries, by which the reason measures the lines.
                sources=[{**CITE, "field": "population note/sex_ratio note/median_age note"},
                         {**AGES_CITE, "field": "median_age note"},
                         {**COD_AB, "field": "population note/sex_ratio note"}]))
            continue
        if k not in MOUGHATAAS:
            report.append(f"moughataa polygon {shape['name']!r}: not placed")
            continue
        wilaya, parts = MOUGHATAAS[k]
        found = [mou[wilaya].get(p) for p in parts]
        if any(f is None for f in found):
            report.append(f"moughataa polygon {shape['name']!r}: {wilaya} has no "
                          f"{[p for p, f in zip(parts, found) if f is None]}; it has "
                          f"{sorted(mou[wilaya])}")
            continue
        used.update((wilaya, p) for p in parts)
        figures = added(*(f["figures"] for f in found))
        if len(found) > 1:
            note = (f"Drawn on its outline from before the moughataa of {found[1]['name']} was "
                    f"made from it; the 2023 census counts the two apart, {found[0]['name']} "
                    f"{found[0]['figures'][2]:,} and {found[1]['name']} "
                    f"{found[1]['figures'][2]:,}, added here.")
        elif k == "chami":
            note = ("The 2023 census's count for the moughataa of Chami, which it counts in "
                    "the wilaya of Dakhlet Nouadhibou.")
        else:
            note = f"The 2023 census's count for the moughataa of {found[0]['name']}."
        note += EDGE.get(k, "")
        records.append(record(f"MRT-RGPH2023-{k}", shape["name"], level="admin2", parent="MRT",
                              country="MRT", match_by="shape_id", shape_id=shape["id"],
                              median_age=gap(NOT_AVAILABLE, NO_AGES),
                              **fields(figures, note, ages_noted=True)))
    left = sorted(f"{w}/{m['name']}" for w, ms in mou.items() if w not in NOUAKCHOTT
                  for p, m in ms.items() if (w, p) not in used and p != "ouadnaga")
    if left:
        report.append(f"moughataas not placed: {left}")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    blob, read = b"", ""
    for url in (URL, MIRROR):
        try:
            blob = fetch_blob(url)
        except Exception as err:  # noqa: BLE001 -- the next copy is tried
            log(f"  {url}: {type(err).__name__}: {err}")
            continue
        if blob.startswith(b"%PDF"):
            read = url
            break
        log(f"  {url} is not a PDF: {blob[:60]!r}")
    if not read:
        raise SystemExit("mauritania_census: no copy of the leaflet could be read")
    log(f"  read {read}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    if read == MIRROR:
        CITE.update(name=SOURCE + ", as the Centre Rachad republishes it", url=MIRROR)
        CITE.pop("page", None)
    text = laid_out(blob)
    table = parse(text)
    for wilaya in WILAYAS:
        log(f"  {wilaya}: {table['wilayas'][wilaya][2]:,}; "
            + ", ".join(f"{m['name']} {m['figures'][2]:,}"
                        for m in table["moughataas"][wilaya].values()))
    ages_blob = fetch_blob(AGES_URL)
    if not ages_blob.startswith(b"%PDF"):
        raise SystemExit(f"mauritania_census: {AGES_URL} is not a PDF: {ages_blob[:60]!r}")
    log(f"  read {AGES_URL}: {len(ages_blob):,} bytes, "
        f"sha256 {hashlib.sha256(ages_blob).hexdigest()}")
    ages = parse_ages(laid_out(ages_blob))
    log(f"  the country's median from Tableau A.2.2: {grouped_median(ages['Total'])}")
    admin1 = json.loads((SITE / "admin1" / "MRT.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "MRT.units.json").read_text())
    records, report = build(table, admin1, admin2, ages)
    for r in records:
        if r["level"] == "admin1":
            m = r["median_age"]
            log(f"  {r['name']}: median {m.get('value', '(none: other ground)')}")
    for line in report:
        log("  " + line)
    n1 = sum(1 for r in records if r["level"] == "admin1")
    n2 = sum(1 for r in records if r["level"] == "admin2" and "value" in r["population"])
    log(f"  {n1} wilayas and {n2} moughataas with counts written")
    if report:
        raise SystemExit("mauritania_census: units left unplaced (above)")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
