#!/usr/bin/env python3
"""Guinea -- the fourth census (RGPH-4, 2025) and the third (RGPH-3, 2014).

The map draws Guinea's eight regions (Conakry, the capital, among them) and its
33 prefectures with Conakry again as the 34th second-level polygon.

**RGPH-4, 2025: preliminary results.** INS Guinée's *Résultats préliminaires du
RGPH-4* (2025) prints the resident population by sex for every region (Tableau
1) and every prefecture (the first annex table), by sous-préfecture and urban
commune (Tableau A 1), and the median age of each region (Tableau 2, in whole
years). These are census counts, the newest for every unit, and they replace
OCHA's 2024 projections for population and sex ratio.

**Conakry, Coyah and Dubréka.** The 2025 census counts the city of Conakry as
thirteen communes. Ten are the city as the map draws it -- Kaloum, Dixinn,
Matam, Matoto and Ratoma, and the five communes carved out of them (Kassa from
Kaloum, Gbessia and Tombolia from Matoto, Lambanyi and Sonfonia from Ratoma).
The other three were taken into the city from neighbouring prefectures:
Kagbélen from Dubréka, and Manéah and Sanoyah, made of the former rural commune
of Manéah, from Coyah (the law of January 2024 creating the communes). The
boundary file draws Conakry, Coyah and Dubréka on their earlier lines, so each
polygon takes the communes on its own ground: Conakry the ten, Coyah its 2025
prefecture with Manéah and Sanoyah, Dubréka its 2025 prefecture with Kagbélen,
and the region of Kindia its 2025 region with all three. The region of Conakry
is the city's polygon again.

**Median age.** Tableau 2's regional medians stand for the six regions whose
ground is unchanged. For Conakry and Kindia it describes other ground (the city
of thirteen communes and the region without them), so those two take the 2014
census's median for the ground the map draws (*Etat et structure de la
population*, Tableau 3.06, to one decimal).

**RGPH-3, 2014.** The same report gives religion by region (Tableau 5.10) and
the principal language spoken by region (Tableau 5.08), the newest census to
tabulate either below the country: they replace Afrobarometer's survey shares
on the eight regions. The shares are written as printed. Religion's are of the
resident population and are applied to each region's 2014 population (Tableau
2.07) to carry counts; language's base row (Effectif) misprints Kindia's, so
they carry none. The prefecture of Conakry, the whole region, takes the
region's median.

**Checks before anything is written.** Every row's men and women make its
total; the prefectures make their regions and the regions make the country's
17,521,167; Conakry's thirteen communes make the city, and Coyah's and
Dubréka's 2025 prefectures with the communes added make the drawn ground;
every region's median row has its ten figures; religion and language shares
make 100 within rounding; the 2014 regions make the country's 10,523,261.

Usage:
    python -m scripts.fetch_census.guinea_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json

URL_2025 = ("https://www.stat-guinee.org/images/Documents/Publications/INS/rapports_enquetes/"
            "RGPH-4/Resultats_preliminaires_rgph_4.pdf")
URL_2014 = ("https://www.stat-guinee.org/images/Documents/Publications/INS/rapports_enquetes/"
            "RGPH3/RGPH3_etat_structure.pdf")
SOURCE_2025 = ("Institut National de la Statistique (INS) de Guinée, Quatrième Recensement "
               "Général de la Population et de l'Habitation (RGPH-4) 2025, Résultats préliminaires")
SOURCE_2014 = ("Institut National de la Statistique (INS) de Guinée, Troisième Recensement Général "
               "de la Population et de l'Habitation (RGPH-3) 2014, Etat et structure de la "
               "population (2017)")
LICENCE = "INS Guinée publication (reuse with attribution)"
YEAR_2025, YEAR_2014 = 2025, 2014
NATIONAL_2025 = (8_452_911, 9_068_256, 17_521_167)
NATIONAL_2014 = 10_523_261
OUT = "guinea_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

REGIONS = ["Boké", "Conakry", "Faranah", "Kankan", "Kindia", "Labé", "Mamou", "Nzérékoré"]
PREFECTURES = {
    "Boké": ["Boffa", "Boké", "Fria", "Gaoual", "Koundara"],
    "Conakry": ["Conakry"],
    "Faranah": ["Dabola", "Dinguiraye", "Faranah", "Kissidougou"],
    "Kankan": ["Kankan", "Kerouane", "Kouroussa", "Mandiana", "Siguiri"],
    "Kindia": ["Coyah", "Dubreka", "Forecariah", "Kindia", "Telimelé"],
    "Labé": ["Koubia", "Labé", "Lelouma", "Mali", "Tougué"],
    "Mamou": ["Dalaba", "Mamou", "Pita"],
    "Nzérékoré": ["Beyla", "Guéckedou", "Lola", "Macenta", "Nzérékoré", "Yomou"],
}
# The city of Conakry in 2025: its thirteen communes, and the three taken in
# from the prefecture each came from.
CONAKRY_COMMUNES = ["Dixinn", "Gbessia", "Kagbelen", "Kaloum", "Kassa", "Lambanyi", "Maneah",
                    "Matam", "Matoto", "Ratoma", "Sanoyah", "Sonfonia", "Tombolia"]
TAKEN_IN = {"Kagbelen": "Dubreka", "Maneah": "Coyah", "Sanoyah": "Coyah"}
# The regions whose 2025 median describes the ground the map draws.
MEDIAN_2025 = {"Boké", "Faranah", "Kankan", "Labé", "Mamou", "Nzérékoré"}

RELIGIONS = {"Sans religion": "No religion", "Musulmane": "Islam", "Chrétienne": "Christianity",
             "Animiste": "Animist", "Autres religions": "Other religion"}
# Tableau 5.08's rows, as printed, and the label each carries on the map.
LANGUAGES = {
    "Aucune": "No national language", "Soussou": "Susu", "Poular": "Pular", "Maninka": "Maninka",
    "Diakanka": "Jahanka", "Baga": "Baga", "Nalou": "Nalu", "Mikiforè": "Mikhifore",
    "Landouma": "Landoma", "Badiaranké": "Badyara", "Bassari": "Bassari",
    "Koniagui": "Coniagui", "Djalonké": "Yalunka", "Sarakolé/Marak": "Soninke",
    "Sarakolé/Maraka": "Soninke", "Kouranko": "Kuranko", "Kissi": "Kissi", "Lélé": "Lele",
    "Toma": "Toma", "Koniaka": "Konyanka", "Tomamania": "Toma-Mania", "Kpèlè": "Kpelle",
    "Mano": "Mano", "Kono": "Kono", "Autre langue nationale": "Other national language",
}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def digits_split(tokens: list[str], parts: int) -> list[tuple[int, ...]]:
    """Every way the digit tokens can be read as ``parts`` numbers, each made of
    whole tokens printed with thousands spaces (a first token of 1-3 digits,
    the rest of exactly 3)."""
    out: list[tuple[int, ...]] = []

    def grouped(chunk: list[str]) -> bool:
        return (bool(chunk) and 1 <= len(chunk[0]) <= 3
                and all(len(t) == 3 for t in chunk[1:]))

    def walk(start: int, left: int, acc: tuple[int, ...]) -> None:
        if left == 0:
            if start == len(tokens):
                out.append(acc)
            return
        for end in range(start + 1, len(tokens) + 1):
            chunk = tokens[start:end]
            if grouped(chunk):
                walk(end, left - 1, acc + (int("".join(chunk)),))

    walk(0, parts, ())
    return out


def sexed_row(rest: str) -> tuple[int, int, int] | None:
    """(men, women, total) from the figures after a name: men, their %, women,
    their %, the total, the men per hundred women and anything after. A share
    the page leaves out is allowed: men and women must make the total."""
    tokens = rest.split()
    cut = [i for i, t in enumerate(tokens) if "," in t]
    if not cut:
        return None
    before = tokens[:cut[0]]
    if len(cut) >= 2:
        women_tokens = tokens[cut[0] + 1:cut[1]]
        after = tokens[cut[1] + 1:]
        pairs = [(m, w) for (m,) in digits_split(before, 1)
                 for (w,) in digits_split(women_tokens, 1)]
    else:
        after = tokens[cut[0] + 1:]
        pairs = list(digits_split(before, 2))
    for m, w in pairs:
        # the total is a leading run of the tokens after the last share
        for end in range(1, len(after) + 1):
            for (t,) in digits_split(after[:end], 1):
                if m + w == t:
                    return m, w, t
    return None


def parse_regions_2025(text: str) -> dict[str, tuple[int, int, int]]:
    """Tableau 1: {region: (men, women, total)}, each row read as printed
    (total, men, their %, women, their %, men per hundred women)."""
    out: dict[str, tuple[int, int, int]] = {}
    names = {fold(r): r for r in REGIONS} | {"boke": "Boké", "nzerekore": "Nzérékoré"}
    for page in text.split("\f"):
        if "Tableau 1 : Répartition de la population par Région administrative" not in page:
            continue
        for line in page.splitlines():
            m = re.match(r"^\s*([A-Za-zÀ-ÿ'’ ]+?)\s+(\d.*)$", line)
            if not m or fold(m.group(1)) not in names:
                continue
            tokens = m.group(2).split()
            cut = [i for i, t in enumerate(tokens) if "," in t]
            if len(cut) != 2:
                continue
            for total, men in digits_split(tokens[:cut[0] - 0], 2) or []:
                women_tokens = tokens[cut[0] + 1:cut[1]]
                for (women,) in digits_split(women_tokens, 1):
                    if men + women == total:
                        out[names[fold(m.group(1))]] = (men, women, total)
    return out


def parse_prefectures_2025(text: str) -> dict[str, Any]:
    """The annex's prefecture table: {"regions": {region: (m, w, t)},
    "prefectures": {(region, prefecture): (m, w, t)}}. A "Région de" line puts
    the region's own row next, its prefectures after it."""
    regions: dict[str, tuple[int, int, int]] = {}
    prefectures: dict[tuple[str, str], tuple[int, int, int]] = {}
    page = next((p for p in text.split("\f")
                 if "Répartition de la population par préfecture selon le sexe" in p
                 and "Sous préfecture" not in p), None)
    if page is None:
        raise SystemExit("guinea_census: no page carries the prefecture table")
    region_names = {fold(r): r for r in REGIONS}
    lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
    region = None
    expect_region = False
    for line in lines:
        if line.startswith("Région de"):
            expect_region = True
            continue
        m = re.match(r"^([A-Za-zÀ-ÿ'’ ]+?)\s+(\d.*)$", line)
        if not m:
            continue
        name, figures = m.group(1).strip(), sexed_row(m.group(2))
        if figures is None:
            continue
        if expect_region:
            if fold(name) not in region_names:
                raise SystemExit(f"guinea_census: {name!r} follows 'Région de'")
            region = region_names[fold(name)]
            regions[region] = figures
            expect_region = False
            continue
        if region is None:
            continue
        known = {fold(p): p for p in PREFECTURES[region]}
        if fold(name) in known:
            prefectures[(region, known[fold(name)])] = figures
    return {"regions": regions, "prefectures": prefectures}


def parse_communes_2025(text: str) -> dict[str, tuple[int, int, int]]:
    """Tableau A 1's rows for the city of Conakry's thirteen communes."""
    wanted = {fold(c): c for c in CONAKRY_COMMUNES}
    out: dict[str, tuple[int, int, int]] = {}
    for page in text.split("\f"):
        if "Sous préfecture" not in page and "Sous-préfecture" not in page:
            continue
        for line in page.splitlines():
            m = re.match(r"^\s*([A-Z][A-Z'’ \-]+?)\s+(\d.*)$", line)
            if not m or fold(m.group(1)) not in wanted:
                continue
            figures = sexed_row(m.group(2))
            if figures:
                out.setdefault(wanted[fold(m.group(1))], figures)
    return out


def parse_medians_2025(layout_text: str) -> dict[str, float]:
    """Tableau 2, laid out: {region: median age, both sexes}. Each row prints
    the mean age (all, men, women, urban, rural) and then the median the same
    way; Conakry has no rural figures."""
    out: dict[str, float] = {}
    names = {fold(r): r for r in REGIONS}
    for line in layout_text.splitlines():
        m = re.match(r"^\s*([A-Za-zÀ-ÿ'’ ]+?)\s+((?:\d+,\d|--)(?:\s+(?:\d+,\d|--))+)\s*$", line)
        if not m:
            continue
        key = fold(m.group(1))
        if key not in names:
            continue
        values = m.group(2).split()
        if len(values) != 10:
            raise SystemExit(f"guinea_census: {m.group(1)}'s Tableau 2 row has {len(values)} "
                             "figures, not 10")
        out[names[key]] = float(values[5].replace(",", "."))
    return out


def parse_2014(text: str) -> dict[str, Any]:
    """The 2014 report's Tableau 2.07 (population by sex and region), 3.06
    (median age), 5.10 (religion) and 5.08 (language) as {table: {region: ...}}."""
    names = {fold(r): r for r in REGIONS}
    out: dict[str, Any] = {"population": {}, "median": {}, "religion": {}, "language": {}}
    pages = text.split("\f")

    def page_with(title: str) -> str:
        # The list of tables names every table too; the table itself is the
        # page where the title is followed by a row for most regions.
        for p in pages:
            if title not in p:
                continue
            after = p.split(title, 1)[1]
            rows = sum(1 for ln in after.splitlines()
                       if fold(re.split(r"\s+\d", ln.strip())[0]) in names)
            if rows >= 6:
                return p
        raise SystemExit(f"guinea_census: no page carries {title!r} with its rows")

    page = page_with("Tableau 2.07")
    for line in page.split("Tableau 2.07", 1)[1].splitlines():
        m = re.match(r"^\s*([A-Za-zÀ-ÿ'’ ]+?)\s+(\d.*)$", line)
        if not m or fold(m.group(1)) not in names:
            continue
        tokens = m.group(2).split()
        cut = [i for i, t in enumerate(tokens) if "," in t]
        if not cut:
            continue
        digits = "".join(tokens[:cut[0]])
        found = None
        for i in range(1, len(digits)):
            for j in range(i + 1, len(digits)):
                men, women, total = int(digits[:i]), int(digits[i:j]), int(digits[j:])
                if men + women == total and digits[i] != "0" and digits[j] != "0":
                    found = (men, women, total)
        if found:
            out["population"][names[fold(m.group(1))]] = found

    page = page_with("Tableau 3.06")
    for line in page.split("Tableau 3.06", 1)[1].splitlines():
        m = re.match(r"^\s*([A-Za-zÀ-ÿ'’ ]+?)\s+((?:\d+,\d\s*){6})$", line.strip() + " ")
        if m and fold(m.group(1)) in names:
            out["median"][names[fold(m.group(1))]] = float(m.group(2).split()[5].replace(",", "."))

    page = page_with("Tableau 5.10")
    for line in page.split("Tableau 5.10", 1)[1].splitlines():
        m = re.match(r"^\s*([A-Za-zÀ-ÿ'’ ]+?)\s+((?:\d+,\d\s*){6})$", line.strip() + " ")
        if m and fold(m.group(1)) in names:
            values = [float(v.replace(",", ".")) for v in m.group(2).split()]
            out["religion"][names[fold(m.group(1))]] = dict(zip(RELIGIONS.values(), values[:5]))

    page = next((p for p in pages if "Tableau 5.08" in p and "Soussou" in p.split("Tableau 5.08", 1)[1]),
                None)
    if page is None:
        raise SystemExit("guinea_census: no page carries Tableau 5.08 with its rows")
    body = page.split("Tableau 5.08", 1)[1]
    order = ["Boké", "Conakry", "Faranah", "Kankan", "Kindia", "Labé", "Mamou", "Nzérékoré"]
    # A label the page wraps ("Autre langue" over "nationale  1,1 0,6 ...")
    # is put back on one line with its figures.
    lines: list[str] = []
    for line in body.splitlines():
        if lines and re.match(r"^[a-zà-ÿ]+\s+\d", line.strip()) \
                and not re.search(r"\d", lines[-1]):
            lines[-1] = f"{lines[-1].strip()} {line.strip()}"
        else:
            lines.append(line)
    for line in lines:
        m = re.match(r"^\s*(.+?)\s+((?:\d+,\d\s+){8}\d+,\d)\s*$", line)
        if not m:
            continue
        label = m.group(1).strip()
        if label not in LANGUAGES:
            continue
        values = [float(v.replace(",", ".")) for v in m.group(2).split()]
        for region, value in zip(order, values[:8]):
            out["language"].setdefault(region, {})
            group = LANGUAGES[label]
            out["language"][region][group] = out["language"][region].get(group, 0.0) + value
    return out


def check_2025(regions: dict[str, tuple[int, int, int]], table: dict[str, Any],
               communes: dict[str, tuple[int, int, int]]) -> None:
    for name, (m, w, t) in list(regions.items()) + [
            (f"{r}/{p}", v) for (r, p), v in table["prefectures"].items()] + list(communes.items()):
        if m + w != t:
            raise SystemExit(f"guinea_census: {name}: {m:,} + {w:,} is not {t:,}")
    if set(regions) != set(REGIONS):
        raise SystemExit(f"guinea_census: Tableau 1 lacks {sorted(set(REGIONS) - set(regions))}")
    made = tuple(sum(v[i] for v in regions.values()) for i in range(3))
    if made != NATIONAL_2025:
        raise SystemExit(f"guinea_census: the regions make {made}, not {NATIONAL_2025}")
    wanted = {(r, p) for r, ps in PREFECTURES.items() for p in ps}
    if set(table["prefectures"]) != wanted:
        raise SystemExit("guinea_census: the prefecture table lacks "
                         f"{sorted(wanted - set(table['prefectures']))}")
    for region in REGIONS:
        rows = [v for (r, _), v in table["prefectures"].items() if r == region]
        made = tuple(sum(v[i] for v in rows) for i in range(3))
        if made != regions[region] or table["regions"].get(region, made) != made:
            raise SystemExit(f"guinea_census: {region}'s prefectures make {made}, not "
                             f"{regions[region]}")
    if set(communes) != set(CONAKRY_COMMUNES):
        raise SystemExit("guinea_census: Tableau A 1 lacks "
                         f"{sorted(set(CONAKRY_COMMUNES) - set(communes))}")
    made = tuple(sum(v[i] for v in communes.values()) for i in range(3))
    if made != regions["Conakry"]:
        raise SystemExit(f"guinea_census: Conakry's communes make {made}, not "
                         f"{regions['Conakry']}")


def drawn_ground(regions: dict[str, tuple[int, int, int]], table: dict[str, Any],
                 communes: dict[str, tuple[int, int, int]]) -> dict[str, Any]:
    """The 2025 counts on the ground the map draws: {"regions": {...},
    "prefectures": {...}}, Conakry, Coyah, Dubréka and Kindia recomposed."""

    def add(*rows: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(sum(r[i] for r in rows) for i in range(3))  # type: ignore[return-value]

    def sub(a: tuple[int, int, int], *rows: tuple[int, int, int]) -> tuple[int, int, int]:
        taken = add(*rows)
        return tuple(a[i] - taken[i] for i in range(3))  # type: ignore[return-value]

    taken = [communes[c] for c in TAKEN_IN]
    prefectures = {p: v for (_, p), v in table["prefectures"].items()}
    city = sub(regions["Conakry"], *taken)
    prefectures["Conakry"] = city
    for commune, prefecture in TAKEN_IN.items():
        prefectures[prefecture] = add(prefectures[prefecture], communes[commune])
    out_regions = dict(regions)
    out_regions["Conakry"] = city
    out_regions["Kindia"] = add(regions["Kindia"], *taken)
    made = add(*out_regions.values())
    if made != NATIONAL_2025:
        raise SystemExit(f"guinea_census: the recomposed regions make {made}")
    return {"regions": out_regions, "prefectures": prefectures}


def sex_ratio(men: int, women: int, year: int, source: str) -> dict[str, Any] | None:
    return measure(round(1000 * men / women), unit="males_per_1000_females", year=year,
                   source=source)


def notes_for(name: str, kind: str, figures: tuple[int, int, int],
              table: dict[str, Any], communes: dict[str, tuple[int, int, int]],
              regions: dict[str, tuple[int, int, int]]) -> str:
    total = figures[2]
    if kind == "prefecture" and name == "Conakry" or kind == "region" and name == "Conakry":
        return ("The 2025 census (preliminary results) counts the city of Conakry as thirteen "
                f"communes, {regions['Conakry'][2]:,} people; three of them -- Kagbélen, from "
                "Dubréka, and Manéah and Sanoyah, from Coyah -- lie outside the city as drawn "
                "here. This is the other ten communes, the city on the ground the map draws: "
                f"{total:,}.")
    if kind == "prefecture" and name in ("Coyah", "Dubreka"):
        added = [c for c, p in TAKEN_IN.items() if p == name]
        own = table["prefectures"][("Kindia", name)][2]
        shown = {"Kagbelen": "Kagbélen", "Maneah": "Manéah", "Sanoyah": "Sanoyah"}
        parts = " and ".join(f"{shown[c]} ({communes[c][2]:,})" for c in added)
        label = "Dubréka" if name == "Dubreka" else name
        return (f"The 2025 census (preliminary results) counts the prefecture of {label} as "
                f"{own:,} people, without {parts}, communes of the city of Conakry since 2024; "
                f"the polygon is drawn with them, so it carries them added: {total:,}.")
    if kind == "region" and name == "Kindia":
        return ("The 2025 census (preliminary results) counts the region of Kindia as "
                f"{regions['Kindia'][2]:,} people, without Kagbélen, Manéah and Sanoyah, "
                "communes of the city of Conakry since 2024; the region is drawn with them, so "
                f"it carries them added: {total:,}.")
    level = "region" if kind == "region" else "prefecture"
    return f"The 2025 census (RGPH-4) preliminary count for the {level} of {name}."


def build(text_2025: str, layout_2025: str, text_2014: str, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    regions = parse_regions_2025(text_2025)
    table = parse_prefectures_2025(text_2025)
    communes = parse_communes_2025(text_2025)
    check_2025(regions, table, communes)
    drawn = drawn_ground(regions, table, communes)
    medians = parse_medians_2025(layout_2025)
    if set(medians) != set(REGIONS):
        raise SystemExit(f"guinea_census: Tableau 2 lacks {sorted(set(REGIONS) - set(medians))}")
    old = parse_2014(text_2014)
    for key in ("population", "median", "religion", "language"):
        if set(old[key]) != set(REGIONS):
            raise SystemExit(f"guinea_census: the 2014 {key} table lacks "
                             f"{sorted(set(REGIONS) - set(old[key]))}")
    if sum(v[2] for v in old["population"].values()) != NATIONAL_2014:
        raise SystemExit("guinea_census: the 2014 regions do not make the country's "
                         f"{NATIONAL_2014:,}")
    for region in REGIONS:
        for key in ("religion", "language"):
            total = sum(old[key][region].values())
            if abs(total - 100) > 0.6:
                raise SystemExit(f"guinea_census: {region}'s 2014 {key} shares make {total:.1f}")

    src_2025 = {"name": SOURCE_2025, "url": URL_2025, "license": LICENCE, "year": YEAR_2025}
    src_2014 = {"name": SOURCE_2014, "url": URL_2014, "license": LICENCE, "year": YEAR_2014}
    records: list[dict[str, Any]] = []
    report: list[str] = []
    region_of: dict[str, str] = {}
    medians_drawn: dict[str, tuple[Any, str, dict[str, Any]]] = {}
    by_region = {fold(r): r for r in REGIONS}
    for shape in admin1:
        region = by_region.get(fold(shape["name"]))
        if region is None:
            report.append(f"region polygon {shape['name']!r}: no census region")
            continue
        region_of[shape["id"]] = region
        m, w, t = drawn["regions"][region]
        pop14 = old["population"][region][2]
        fields: dict[str, Any] = {
            "population": measure(t, year=YEAR_2025, source=SOURCE_2025),
            "population_note": notes_for(region, "region", (m, w, t), table, communes, regions),
            "sex_ratio": sex_ratio(m, w, YEAR_2025, SOURCE_2025),
        }
        sources = [{**src_2025, "field": "population/sex_ratio"}]
        if region in MEDIAN_2025:
            fields["median_age"] = measure(medians[region], unit="years", year=YEAR_2025,
                                           source=SOURCE_2025 + ", Tableau 2")
            fields["median_age_note"] = ("The 2025 census's preliminary results give each "
                                         "region's median age in whole years.")
            sources.append({**src_2025, "field": "median_age"})
        else:
            fields["median_age"] = measure(old["median"][region], unit="years", year=YEAR_2014,
                                           source=SOURCE_2014 + ", Tableau 3.06")
            ground = ("the city of thirteen communes" if region == "Conakry"
                      else "the region without the three communes it gave the city")
            fields["median_age_note"] = (
                f"The 2025 census's median for {region}, {medians[region]:g}, is for {ground}, "
                "not the ground drawn here; this is the 2014 census's median for the region on "
                "its earlier lines.")
            # The note quotes the 2025 median: the preliminary results are cited for it.
            sources[0] = {**src_2025, "field": "population/sex_ratio/median_age note"}
            sources.append({**src_2014, "field": "median_age"})
        # The shares as printed, not rescaled to make 100. Tableau 5.10 is of the
        # resident population, so its shares of the region's 2014 population
        # carry counts; Tableau 5.08's base row (Effectif) misprints Kindia's
        # (140,044 where the row's total wants 1,400,484), so its shares carry
        # no count.
        religion = {k: v * pop14 / 100 for k, v in old["religion"][region].items() if v}
        fields.update({
            "religion": shares(religion, total=pop14),
            "religion_year": YEAR_2014,
            "religion_note": ("Religion of the resident population as the 2014 census tabulates "
                              "it by region (Tableau 5.10): Muslim, Christian, animist, other, "
                              "none."),
            "language": [{"group": g, "pct": round(v, 1)} for g, v in
                         sorted(old["language"][region].items(), key=lambda kv: (-kv[1], kv[0]))
                         if v],
            "language_year": YEAR_2014,
            "language_note": ("The principal language spoken, as the 2014 census tabulates it by "
                              "region (Tableau 5.08); its national column is the one the report "
                              "gives for everyone aged 3 and over (Tableau 5.07)."),
        })
        sources.append({**src_2014, "field": "religion/language"})
        records.append(record(f"GIN-RGPH-region-{fold(region)}", shape["name"], level="admin1",
                              parent="GIN", country="GIN", match_by="shape_id",
                              shape_id=shape["id"], sources=sources, **fields))
        medians_drawn[region] = (fields["median_age"], fields["median_age_note"],
                                 sources[1], sources[0]["field"])
    by_prefecture = {fold(p): p for ps in PREFECTURES.values() for p in ps}
    used: set[str] = set()
    for shape in admin2:
        prefecture = by_prefecture.get(fold(shape["name"]))
        region = region_of.get(shape.get("parent"))
        if prefecture is None or region is None or prefecture not in PREFECTURES[region] \
                or prefecture in used:
            report.append(f"prefecture polygon {shape['name']!r}: not bound")
            continue
        used.add(prefecture)
        m, w, t = drawn["prefectures"][prefecture]
        # A region of one prefecture (Conakry) is that prefecture's ground: the
        # region's median is the prefecture's.
        same: dict[str, Any] = {}
        extra: list[dict[str, Any]] = []
        first = "population/sex_ratio"
        if PREFECTURES[region] == [prefecture] and region in medians_drawn:
            median, note, cited, first = medians_drawn[region]
            same = {"median_age": median,
                    "median_age_note": note + " The region is this one prefecture."}
            extra = [cited]
        records.append(record(
            f"GIN-RGPH-{fold(prefecture)}", shape["name"], level="admin2", parent="GIN",
            country="GIN", match_by="shape_id", shape_id=shape["id"],
            sources=[{**src_2025, "field": first}, *extra],
            population=measure(t, year=YEAR_2025, source=SOURCE_2025),
            population_note=notes_for(prefecture, "prefecture", (m, w, t), table, communes,
                                      regions),
            sex_ratio=sex_ratio(m, w, YEAR_2025, SOURCE_2025), **same))
    missing = sorted(set(by_prefecture.values()) - used)
    if missing:
        report.append(f"prefectures not bound: {missing}")
    return records, report


def fetch(url: str) -> bytes:
    blob = http_get(url, binary=True, cache=False, timeout=300)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"guinea_census: {url} is not a PDF: {blob[:60]!r}")
    log(f"  read {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    return blob


def pdf_text(blob: bytes) -> str:
    from pypdf import PdfReader                          # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    return "\f".join((page.extract_text() or "") for page in reader.pages)


def laid_out_page(blob: bytes, title: str) -> str:
    """The page carrying ``title``, laid out by pdfplumber (columns kept)."""
    import pdfplumber                                    # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if title in text and "Ensemble" in text:
                return page.extract_text(layout=True) or ""
    raise SystemExit(f"guinea_census: no page carries {title!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    blob_2025 = fetch(URL_2025)
    text_2025 = pdf_text(blob_2025)
    layout_2025 = laid_out_page(blob_2025, "Tableau 2 : Age moyen et âge médian")
    blob_2014 = fetch(URL_2014)
    text_2014 = pdf_text(blob_2014)
    admin1 = json.loads((SITE / "admin1" / "GIN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GIN.units.json").read_text())
    records, report = build(text_2025, layout_2025, text_2014, admin1, admin2)
    for line in report:
        log("  " + line)
    for r in records:
        pop = r["population"]["value"]
        sr = r["sex_ratio"]["value"]
        med = (r.get("median_age") or {}).get("value") if isinstance(r.get("median_age"), dict) else None
        log(f"  {r['level']} {r['name']}: {pop:,}, {sr} men per 1,000 women"
            + (f", median {med}" if med is not None else ""))
    n1 = sum(1 for r in records if r["level"] == "admin1")
    n2 = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {n1} regions and {n2} prefectures bound")
    if n1 != 8 or n2 != 34:
        raise SystemExit(f"guinea_census: expected 8 regions and 34 prefectures, bound {n1} and {n2}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
