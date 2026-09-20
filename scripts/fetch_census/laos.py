#!/usr/bin/env python3
"""Lao PDR: ethnicity and religion by province and district, from the 2015
census's own village table.

The 4th Population and Housing Census 2015 asked ethnicity (the 49 official
groups) and religion. The Lao Statistics Bureau's English results volume --
"Results of Population and Housing Census 2015", 282 pages, published with
UNFPA -- prints both for the country and for nothing smaller: its Chapter 3
tables 3.4 and 3.5 are national, and so are the Appendix 1 tables they cite
(P2.7 ethnicity, P2.9 religion). Its other appendix tables cross province with
age, migration, literacy, schooling, economic activity, disability and
housing, and not once with either of these two. That reading is what
``--probe --routes p`` measured, and it stands.

What does publish them below the country is the census's **village indicator
table**, which LSB releases through Open Development Laos: one row for each of
the country's 8,500-odd villages, with the province, district and village
named in English and Lao, the village's total population, and 68 indicators
derived from the census returns. Among them are the ten ethno-linguistic
categories the census sorts its 49 groups into -- Lao, Tai-Thay, Khmuic,
Palaungic, Katuic, Bahnaric-Khmer, Vietic, Tibeto-Burman, Hmong and Mien --
each as a percentage of the village's people, and five religions -- Buddhist,
Christian, Bahai, Muslim and other -- the same way. The workbook's own Meta
sheet names every column in Lao and English and gives the source as "Lao
Population and Housing Census 2015" and the data owner as the Lao Statistics
Bureau.

Those ten categories are defined in Table 1 of the *Socio-Economic Atlas of
the Lao PDR 2015* (LSB with the Centre for Development and Environment of the
University of Bern), which is the publication this table underlies, and the
definition matters: the Atlas's "Lao" is not the census's Lao ethnic group.
Its Table 1 assigns the Lao of Huaphanh, Xiengkhuang, Borikhamxay, Vientiane
province and Hinboun district of Khammuane to "Tai-Thay" instead, so the
villages come to Lao 43.7% and Tai-Thay 18.3% where the volume's Table 3.4
prints Lao 53.2%. The two together are the volume's Lao-Tai family, 62.4%,
which is the level this reader checks at and the note on every row says so.

So the composition written here is the census's, read at the level the census
released it and added up. A percentage of a village is turned back into people
by the village's own published population, those counts are summed over the
villages of each district and of each province, and the shares are recomputed
against the unit's total.

**What the residual is.** The ten ethno-linguistic categories do not reach
100: the rest is the census's own other-and-not-stated together with the
foreign population, 1.2% and 0.7% of the country. The five religions do not
reach 100 either, and the missing part is larger and has a known composition.
The census defines a religion as a spiritual system with written doctrines, so
the animist beliefs of most non-Lao-Tai people -- the Satsana Phi, the
"religion of spirits" -- are not among the five and are recorded with the
people who stated nothing; the Atlas says this in as many words and calls the
result "no religion or not stated", which is the label used here. Nationally
it is 33.3%, of which the census publishes 31.4% as no religion and 1.8% as
not stated. Both residuals are published as one row apiece -- "Other or not
stated" and "No religion or not stated" -- because neither can be split unit
by unit, and the religion one is filed in the group tree beside the other
labels that weld a real answer to a non-answer.

**Language is not written, and is declared rather than left blank.** The 2015
census asked no language or mother-tongue question: the results volume has no
such table among its appendix tables, the village table has no such column
among its 68 indicators, and the census's own summary of what it measured
lists "Ethno-linguistic group" and "Religion" and nothing about language. The
ethno-linguistic category above is a classification of the ethnic group a
person gave, not a language anyone was asked to speak, and it is published on
the ethnicity field for that reason. ``NOT_COLLECTED_POLICY`` in
``scripts/common.py`` carries the declaration.

**Self-checks**, each of which refuses the run rather than writing:

* every village must name one of the 18 provinces this reader knows;
* the villages' population must come within 2% of the census's published
  6,492,228, and the districts must not hold more people than their provinces;
* the sex ratio must come within half a percent of the published national one,
  which is also what would catch the workbook's ratio being the other way up;
* the national shares recomputed from the villages must come within one
  percentage point of what the volume prints -- Lao 53.2%, the Lao-Tai family
  62.4%, Mon-Khmer 23.7%, Hmong-Mien 9.7%, Chinese-Tibetan 2.9%, Buddhist
  64.7%, Christian 1.7%, and 33.2% with no religion or none stated.

A district whose name this reader cannot place inside its province is logged
and left unwritten; the boundary file's own 148 names are the list it is
placed against, so a match is an identity and never a guess.

Usage:
    python -m scripts.fetch_census.laos --level both
    python -m scripts.fetch_census.laos --probe --routes adfhpwx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import (PROCESSED, RAW, download, http_get, http_json, log, measure,
                      record, write_json)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

USER_AGENT = ("DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
              "python-urllib")

OUT = {"province": "laos_province.json", "district": "laos_district.json"}
YEAR = 2015
XLSX = ("https://data.laos.opendevelopmentmekong.net/lo/dataset/"
        "7256198a-89af-411a-a850-9ccd1eca88a4/resource/"
        "130665a5-1e64-477a-a756-51fa65eeec02/download/lao-population-census-2015.xlsx")
LANDING = ("https://data.laos.opendevelopmentmekong.net/dataset/"
           "lao-population-and-housing-census-2015-general-demographic")
SOURCE = ("Lao Statistics Bureau, 4th Population and Housing Census 2015, village "
          "indicator table (population, ethno-linguistic category and religion for "
          "each of 8,500 villages), released through Open Development Laos")
LICENCE = ("Official statistics of the Lao Statistics Bureau, distributed by Open "
           "Development Laos")

# The census's own column codes, from the workbook's Meta sheet.
COL_VILLAGE = "uuid"
COL_VILLAGE_NAME = "uucne"
COL_DISTRICT = "usid"
COL_DISTRICT_NAME = "uscne"
COL_PROVINCE = "urid"
COL_PROVINCE_NAME = "urcne"
COL_POPULATION = "unpdeaa01"
COL_SEX_RATIO = "urpdeaa29"

# Percentage of the village's population, in the workbook's order.
ETHNICITY: dict[str, str] = {
    "urpetab69": "Lao",
    "urpetab70": "Tai-Thay",
    "urpetab71": "Khmuic",
    "urpetab72": "Palaungic",
    "urpetab73": "Katuic",
    "urpetab74": "Bahnaric-Khmer",
    "urpetab75": "Vietic",
    "urpetab76": "Tibeto-Burman",
    "urpetab77": "Hmong",
    "urpetab78": "Mien",
}
RELIGION: dict[str, str] = {
    "urpreab34": "Buddhism",
    "urpreab35": "Christianity",
    "urpreab36": "Baha'i",
    "urpreab37": "Islam",
    "urpreab38": "Other religions",
}
ETHNIC_RESIDUAL = "Other or not stated"
RELIGION_RESIDUAL = "No religion or not stated"
MIN_SHARE = 0.05            # below this share of the unit, a group joins the residual

# The four families the census reports its ten categories in, for the national
# check against the volume's own summary page.
FAMILY: dict[str, str] = {
    "Lao": "Lao-Tai", "Tai-Thay": "Lao-Tai",
    "Khmuic": "Mon-Khmer", "Palaungic": "Mon-Khmer", "Katuic": "Mon-Khmer",
    "Bahnaric-Khmer": "Mon-Khmer", "Vietic": "Mon-Khmer",
    "Tibeto-Burman": "Chinese-Tibetan",
    "Hmong": "Hmong-Mien", "Mien": "Hmong-Mien",
}

# What the volume prints for the country, and what this reader must reproduce.
# The population and the sex split are Table P2.9's totals; the ethnic shares
# are Table 3.4 and the summary page's ethno-linguistic block; the religions
# are Table 3.5 and Table P2.9.
NATIONAL_POPULATION = 6_492_228
NATIONAL_FEMALE = 3_237_458
NATIONAL_MALE = 3_254_770
POPULATION_TOLERANCE = 0.02      # the village table is the household population
SEX_RATIO_TOLERANCE = 0.005
SHARE_TOLERANCE = 1.0            # percentage points
# The check is at the family level and not at the category level, and the
# reason is the Atlas's own Table 1. Its "Lao" category is not the census's
# Lao ethnic group: the Lao of Huaphanh, Xiengkhuang, Borikhamxay, Vientiane
# province and Hinboun district of Khammuane are put in "Tai-Thay" instead, so
# the villages come to 43.7% Lao where Table 3.4 prints 53.2%. The two
# together reproduce the volume's Lao-Tai family exactly, which is what this
# checks; the run logs both figures every time so the difference stays on the
# record rather than being quietly tolerated.
NATIONAL_LAO_GROUP = 53.2        # Table 3.4, the Lao *ethnic group*
NATIONAL_FAMILY = {"Lao-Tai": 62.4, "Mon-Khmer": 23.7, "Hmong-Mien": 9.7,
                   "Chinese-Tibetan": 2.9}
NATIONAL_RELIGION = {"Buddhism": 64.7, "Christianity": 1.7,
                     RELIGION_RESIDUAL: 33.2}

# The 18 provinces as the boundary file spells them, with the spellings this
# project has met. The workbook's own spelling is matched against these after
# folding, and a province the fold does not reach refuses the run: a village
# belonging to nowhere is not a gap, it is a reader that has stopped
# understanding its source.
#
# The two Vientianes are why this table is written out rather than guessed at.
# The province and the capital are separate shapes, one wholly inside the
# other's reach by name, and a loose match between them is the mis-match this
# project ranks below a gap -- it has happened here already, Vientiane having
# once taken Vientiane Province's 388,833 people over the prefecture's (see
# scripts/build_entities.py). Neither carries an alias; province_of settles
# the two and nothing else may.
PROVINCES: dict[str, tuple[str, ...]] = {
    "Attapeu": ("Attapu",),
    "Bokeo": ("Bo Keo",),
    "Bolikhamsai": ("Bolikhamxai", "Borikhamxay", "Bolikhamxay", "Borikhamxai"),
    "Champasak": ("Champasack", "Champassak", "Champassack"),
    "Houaphan": ("Houaphanh", "Huaphanh", "Hua Phan", "Houa Phan"),
    "Khammouane": ("Khammuane", "Khammouan", "Khammuan"),
    "Luang Namtha": ("Luangnamtha", "Louang Namtha", "Luang Nam Tha"),
    "Luang Prabang": ("Luangprabang", "Louangphabang", "Luang Phabang",
                      "Louangprabang"),
    "Oudomxay": ("Oudomxai", "Udomxay", "Oudom Xay"),
    "Phongsaly": ("Phongsali", "Phong Saly"),
    "Salavan": ("Saravane", "Saravan", "Salavane"),
    "Savannakhet": ("Savannakhét",),
    "Vientiane": (),
    "Vientiane Capital": (),
    # The workbook's own spelling is "Xaignabouly"; the boundary file's is
    # "Xaignabouli", and the rest are what this province is called elsewhere.
    "Xaignabouli": ("Xaignabouly", "Xayabury", "Xayaboury", "Sayaboury",
                    "Sainyabuli", "Xaiyabouli", "Xayabouly", "Xaignabouri"),
    "Xaisomboun": ("Xaysomboun", "Xiasomboun", "Saysomboun"),
    "Xekong": ("Sekong", "Xe Kong"),
    "Xiangkhouang": ("Xiengkhuang", "Xieng Khouang", "Xiengkhouang",
                     "Xiangkhoang", "Xieng Khuang"),
}
# How the two Vientianes are told apart, whatever the source calls them.
VIENTIANE_CAPITAL = ("vientianecapital", "vientianeprefecture", "vientianecity",
                     "nakhonluangvientiane", "capitalvientiane",
                     "vientianecapitalprefecture")
VIENTIANE_PROVINCE = ("vientiane", "vientianeprovince", "vientianeprov")

# The 148 districts as the boundary file spells them, under their province.
# This is the list a census district name is placed against; a name the fold
# does not reach is logged and left unwritten.
DISTRICTS: dict[str, tuple[str, ...]] = {
    "Attapeu": (
        "Phouvong", "Samakkhixay", "Sanamxay", "Sanxay", "Xaysetha",
    ),
    "Bokeo": (
        "Huoixai", "Meung", "Paktha", "Pha Oudom", "Tonpheung",
    ),
    "Bolikhamsai": (
        "Bolikhanh", "Khamkeuth", "Pakkading", "Pakxane", "Thaphabath",
        "Viengthong", "Xaychamphone",
    ),
    "Champasak": (
        "Bachiangchaleunsook", "Champasack", "Khong", "Moonlapamok",
        "Pakse", "Paksxong", "Pathoomphone", "Phonthong", "Sanasomboon",
        "Sukhuma",
    ),
    "Houaphan": (
        "Add", "Hiem", "Huameuang", "Kuan", "Sopbao", "Viengxay", "Xamneua",
        "Xamtay", "Xiengkhor", "Xon",
    ),
    "Khammouane": (
        "Bualapha", "Hinboon", "Khounkham", "Mahaxay", "Nakay",
        "Nhommalath", "Nongbok", "Thakhek", "Xaybuathong", "Xebangfay",
    ),
    "Luang Namtha": (
        "Long", "Nalae", "Namtha", "Sing", "Viengphoukha",
    ),
    "Luang Prabang": (
        "Chomphet", "Luangprabang", "Nambak", "Nan", "Ngoi", "Pak Xeng",
        "Park Ou", "Phonthong", "Phonxay", "Phoukhoune", "Viengkham",
        "Xieng Ngeun",
    ),
    "Oudomxay": (
        "Beng", "Hoon", "La", "Namor", "Nga", "Pakbeng", "Xay",
    ),
    "Phongsaly": (
        "Boon Neua", "Boontay", "Khua", "May", "Nhot Ou", "Phongsaly",
        "Samphanh",
    ),
    "Salavan": (
        "Khongxedone", "Lakhonepheng", "Lao Ngarm", "Samuoi", "Saravane",
        "Ta Oi", "Toomlarn", "Vapy",
    ),
    "Savannakhet": (
        "Atsaphangthong", "Atsaphone", "Champhone", "Kaysone Phomvihane",
        "Nong", "Outhoomphone", "Phalanxay", "Phine", "Sepone", "Songkhone",
        "Thapangthong", "Vilabuly", "Xaybuly", "Xayphoothong", "Xonbuly",
    ),
    "Vientiane": (
        "Feuang", "Hinherb", "Kasy", "Keo Oudom", "Mad", "Meun", "Phonhong",
        "Thoulakhom", "Vangvieng", "Viengkham", "Xanakharm",
    ),
    "Vientiane Capital": (
        "Chanthabuly", "Hadxaifong", "Mayparkngum", "Naxaithong",
        "Sangthong", "Sikhottabong", "Sisattanak", "Xaysetha", "Xaythany",
    ),
    "Xaignabouli": (
        "Botene", "Hongsa", "Kenethao", "Khop", "Ngeun", "Parklai",
        "Phiang", "Thongmyxay", "Xayabury", "Xaysathan", "Xienghone",
    ),
    "Xaisomboun": (
        "Anouvong", "Home", "Longcheng", "Longsane", "Thathom",
    ),
    "Xekong": (
        "Dakcheung", "Kaleum", "Lamarm", "Thateng",
    ),
    "Xiangkhouang": (
        "Kham", "Khoune", "Mork", "Nonghed", "Pek", "Phaxay", "Phookood",
    ),
}
# The workbook's spelling, folded, -> the boundary file's, inside one
# province. Seven of the 148 names romanise differently in the two files, and
# each of these seven is an identity rather than a nearest match: in every one
# of the four provinces concerned, the number of census names the fold could
# not place equals the number of shapes left without a village, and each pair
# is one Lao name written two ways -- Houaphan's Hiem/Huim, Kuan/Kuane and
# Xon/Sone, Khammouane's Nakay/Nakai, Phongsaly's Boontay/Boontai, and
# Xiangkhouang's Mork/Morkmay and Phookood/Phoukoud. Nothing here is a guess
# about which shape a name is nearest to; a name with no such one-to-one
# answer stays unplaced and is logged.
DISTRICT_ALIASES: dict[tuple[str, str], str] = {
    ("Houaphan", "huim"): "Hiem",
    ("Houaphan", "kuane"): "Kuan",
    ("Houaphan", "sone"): "Xon",
    ("Khammouane", "nakai"): "Nakay",
    ("Phongsaly", "boontai"): "Boontay",
    ("Xiangkhouang", "morkmay"): "Mork",
    ("Xiangkhouang", "phoukoud"): "Phookood",
}
# Words a district name may carry and a shape name does not.
DISTRICT_NOISE = re.compile(r"\b(district|muang|city|municipality)\b", re.IGNORECASE)


def fold(text: str) -> str:
    """A name reduced to its letters: what two romanisations agree on."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c for c in text if c.isalnum())


PROVINCE_KEYS = {fold(k): name for name, others in PROVINCES.items()
                 for k in (name, *others)}
DISTRICT_KEYS = {province: {fold(d): d for d in names}
                 for province, names in DISTRICTS.items()}


def province_of(label: str) -> str | None:
    """The boundary file's name for the province this label means.

    The two Vientianes are settled here and nowhere else: the capital is
    recognised by its own qualifier, only a bare "Vientiane" is the province,
    and any other label starting with the word is refused rather than guessed
    at. Nothing loose runs between them.
    """
    key = fold(label)
    if not key:
        return None
    if key in VIENTIANE_CAPITAL:
        return "Vientiane Capital"
    if key in VIENTIANE_PROVINCE:
        return "Vientiane"
    if key.startswith("vientiane"):
        return None
    return PROVINCE_KEYS.get(key) or PROVINCE_KEYS.get(key.removesuffix("province"))


def district_of(province: str, label: str) -> str | None:
    """The boundary file's name for this district of this province."""
    key = fold(DISTRICT_NOISE.sub(" ", label or ""))
    if not key:
        return None
    known = DISTRICT_KEYS.get(province, {})
    return (DISTRICT_ALIASES.get((province, key))
            or known.get(key)
            or known.get(key.removesuffix("district")))


# ---------------------------------------------------------------------------
# Reading the workbook
# ---------------------------------------------------------------------------

NEEDED = [COL_VILLAGE, COL_VILLAGE_NAME, COL_DISTRICT, COL_DISTRICT_NAME,
          COL_PROVINCE, COL_PROVINCE_NAME, COL_POPULATION, COL_SEX_RATIO,
          *ETHNICITY, *RELIGION]


def number(value: Any) -> float:
    """A cell as a number. A blank is zero; the census's own dashes are too."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise SystemExit(f"laos: {value!r} where a figure was expected")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"-", "*", "..", "n/a", "N/A", "NA"}:
        return 0.0
    return float(text)


def villages(path: Path) -> list[dict[str, Any]]:
    """Every row of the workbook's Census sheet, as this reader needs it."""
    from openpyxl import load_workbook
    book = load_workbook(str(path), read_only=True, data_only=True)
    if "Census" not in book.sheetnames:
        raise SystemExit(f"laos: the workbook has no Census sheet, only {book.sheetnames}")
    rows = book["Census"].iter_rows(values_only=True)
    header = [str(c or "").strip() for c in next(rows)]
    index = {name: i for i, name in enumerate(header)}
    missing = [c for c in NEEDED if c not in index]
    if missing:
        raise SystemExit(f"laos: the Census sheet is missing {missing}; its columns are "
                         f"{header}")
    out: list[dict[str, Any]] = []
    for line in rows:
        if not line or all(c is None or c == "" for c in line):
            continue
        cell = {name: line[i] if i < len(line) else None for name, i in index.items()}
        out.append({
            "village": str(cell[COL_VILLAGE] or ""),
            "village_name": str(cell[COL_VILLAGE_NAME] or ""),
            "district_code": str(cell[COL_DISTRICT] or ""),
            "district_label": str(cell[COL_DISTRICT_NAME] or "").strip(),
            "province_code": str(cell[COL_PROVINCE] or ""),
            "province_label": str(cell[COL_PROVINCE_NAME] or "").strip(),
            "population": number(cell[COL_POPULATION]),
            "sex_ratio": number(cell[COL_SEX_RATIO]),
            "ethnicity": {label: number(cell[code]) for code, label in ETHNICITY.items()},
            "religion": {label: number(cell[code]) for code, label in RELIGION.items()},
        })
    book.close()
    log(f"  {len(out):,} village rows")
    return out


# ---------------------------------------------------------------------------
# Villages -> units
# ---------------------------------------------------------------------------

def blank_unit(name: str, province: str) -> dict[str, Any]:
    return {"name": name, "province": province, "villages": 0, "population": 0.0,
            "female": 0.0, "male": 0.0,
            "ethnicity": {label: 0.0 for label in ETHNICITY.values()},
            "religion": {label: 0.0 for label in RELIGION.values()}}


def add(unit: dict[str, Any], village: dict[str, Any]) -> None:
    """One village's people into the unit they belong to.

    A percentage of a village is turned back into people by that village's own
    population, which is the one figure the table gives as a count; the shares
    are recomputed against the unit's total afterwards. A village's sex ratio
    is males per hundred females, so its two halves follow from it and the
    population, and they are summed rather than averaged -- an average of
    ratios is not a ratio.
    """
    people = village["population"]
    unit["villages"] += 1
    unit["population"] += people
    ratio = village["sex_ratio"]
    if people and ratio > 0:
        female = people * 100.0 / (100.0 + ratio)
        unit["female"] += female
        unit["male"] += people - female
    for field in ("ethnicity", "religion"):
        for label, pct in village[field].items():
            unit[field][label] += pct * people / 100.0


def gather(rows: list[dict[str, Any]]) -> tuple[dict[str, dict],
                                                dict[tuple[str, str], dict],
                                                list[str]]:
    """The 18 provinces, the districts placed inside them, and what was not.

    A village whose province this reader cannot name refuses the run: the
    workbook is the census's own and its 18 provinces are known, so an
    unreadable one means the reader has stopped understanding the file. A
    village whose *district* cannot be placed is counted into its province and
    logged, because the province is still certain -- what is not certain is
    which of the 148 shapes below it the row belongs to, and a guess there is
    the mis-match this project refuses to make.
    """
    provinces: dict[str, dict[str, Any]] = {}
    districts: dict[tuple[str, str], dict[str, Any]] = {}
    unplaced: dict[str, float] = {}
    unknown: dict[str, int] = {}
    for village in rows:
        province = province_of(village["province_label"])
        if province is None:
            label = village["province_label"]
            unknown[label] = unknown.get(label, 0) + 1
            continue
        add(provinces.setdefault(province, blank_unit(province, province)), village)
        district = district_of(province, village["district_label"])
        if district is None:
            key = f"{province} / {village['district_label']}"
            unplaced[key] = unplaced.get(key, 0.0) + village["population"]
            continue
        add(districts.setdefault((province, district),
                                 blank_unit(district, province)), village)
    if unknown:
        listed = ", ".join(f"{label!r} ({n} villages)" for label, n in sorted(unknown.items()))
        raise SystemExit(f"laos: {len(unknown)} province name(s) none of the 18 this "
                         f"reader knows: {listed}. Add each to PROVINCES, or to the "
                         "Vientiane table if it is one of those two.")
    notes = [f"{key} ({people:,.0f} people)" for key, people in sorted(unplaced.items())]
    return provinces, districts, notes


# ---------------------------------------------------------------------------
# Units -> compositions
# ---------------------------------------------------------------------------

def whole_hundred(values: list[float]) -> list[float]:
    """Shares re-rounded to one decimal by largest remainder, adding to 100."""
    scaled = [v * 10 for v in values]
    floors = [int(s) for s in scaled]
    short = round(1000 - sum(floors))
    order = sorted(range(len(scaled)), key=lambda i: scaled[i] - floors[i], reverse=True)
    for i in order[:short]:
        floors[i] += 1
    return [f / 10 for f in floors]


def composition(counts: dict[str, float], total: float,
                residual: str) -> list[dict[str, Any]]:
    """Counts -> the map's rows, largest first, with the named residual last.

    Everything the table does not name is one row. For ethnicity that is the
    census's other-and-not-stated plus the foreign population; for religion it
    is no religion plus not stated. A category under 0.05% of the unit joins it
    rather than being printed as a zero, and the note says so.
    """
    if total <= 0:
        return []
    keep = {label: value for label, value in counts.items()
            if value > 0 and 100.0 * value / total >= MIN_SHARE}
    rows = sorted(keep.items(), key=lambda kv: (-kv[1], kv[0]))
    rest = total - sum(keep.values())
    if rest > 0 and 100.0 * rest / total >= MIN_SHARE:
        rows.append((residual, rest))
    if not rows:
        return []
    shares = whole_hundred([100.0 * value / total for _label, value in rows])
    return [{"group": label, "pct": pct, "count": int(round(value))}
            for (label, value), pct in zip(rows, shares)]


# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------

def national(units: dict[Any, dict[str, Any]], field: str) -> dict[str, float]:
    """The shares this reader comes to for the whole country."""
    total = sum(u["population"] for u in units.values())
    if not total:
        return {}
    counts: dict[str, float] = {}
    for unit in units.values():
        for label, value in unit[field].items():
            counts[label] = counts.get(label, 0.0) + value
    residual = ETHNIC_RESIDUAL if field == "ethnicity" else RELIGION_RESIDUAL
    counts[residual] = total - sum(counts.values())
    return {label: 100.0 * value / total for label, value in counts.items()}


def check(provinces: dict[str, dict], districts: dict[tuple[str, str], dict]) -> None:
    missing = sorted(set(PROVINCES) - set(provinces))
    if missing:
        raise SystemExit(f"laos: {len(provinces)} provinces read of 18; missing {missing}")
    people = sum(u["population"] for u in provinces.values())
    drift = abs(people - NATIONAL_POPULATION) / NATIONAL_POPULATION
    if drift > POPULATION_TOLERANCE:
        raise SystemExit(f"laos: the villages add to {people:,.0f} people against the "
                         f"census's published {NATIONAL_POPULATION:,} "
                         f"({people - NATIONAL_POPULATION:+,.0f}, {drift:.1%})")
    log(f"  18 provinces, {len(districts)} districts of 148, {people:,.0f} people "
        f"against the published {NATIONAL_POPULATION:,} "
        f"({(people - NATIONAL_POPULATION) / NATIONAL_POPULATION:+.2%})")

    female = sum(u["female"] for u in provinces.values())
    male = sum(u["male"] for u in provinces.values())
    got = 1000.0 * female / male if male else 0.0
    want = 1000.0 * NATIONAL_FEMALE / NATIONAL_MALE
    log(f"  sex ratio {got:.1f} females per 1,000 males against the published {want:.1f}")
    if not male or abs(got - want) / want > SEX_RATIO_TOLERANCE:
        raise SystemExit(
            f"laos: the villages come to {got:.1f} females per 1,000 males against the "
            f"census's published {want:.1f}. The workbook's u_sex_ratio is read as males "
            "per hundred females; if it is the other way round, this is what says so")

    ethnic = national(provinces, "ethnicity")
    families: dict[str, float] = {}
    for label, share in ethnic.items():
        family = FAMILY.get(label, ETHNIC_RESIDUAL)
        families[family] = families.get(family, 0.0) + share
    religion = national(provinces, "religion")
    for what, shares in (("ethnicity", ethnic), ("families", families),
                         ("religion", religion)):
        log(f"  {what:9} " + ", ".join(f"{k} {v:.1f}" for k, v in
                                       sorted(shares.items(), key=lambda kv: -kv[1])))
    log(f"  the Atlas's Lao category is {ethnic.get('Lao', 0.0):.1f}% and its Tai-Thay "
        f"{ethnic.get('Tai-Thay', 0.0):.1f}%, against {NATIONAL_LAO_GROUP:.1f}% for the "
        "Lao ethnic group in Table 3.4: its Table 1 puts the Lao of Huaphanh, "
        "Xiangkhouang, Bolikhamsai, Vientiane province and Hinboun in Tai-Thay")
    for what, got_shares, want_shares in (("ethno-linguistic family", families,
                                           NATIONAL_FAMILY),
                                          ("religion", religion, NATIONAL_RELIGION)):
        for label, want_share in want_shares.items():
            have = got_shares.get(label, 0.0)
            if abs(have - want_share) > SHARE_TOLERANCE:
                raise SystemExit(
                    f"laos: the villages come to {have:.1f}% {label} ({what}) against "
                    f"the volume's published {want_share:.1f}%")
    log(f"  every national figure within {SHARE_TOLERANCE:.1f} points of the volume's")

    by_district = sum(u["population"] for u in districts.values())
    if by_district > people + 1:
        raise SystemExit(f"laos: the districts hold {by_district:,.0f} people and their "
                         f"provinces {people:,.0f}")


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def note(field: str) -> str:
    """What the figure is, where it came from, and the one thing about it that
    would otherwise be read wrongly. The method is in docs/SOURCES.md."""
    if field == "ethnicity":
        what = ("the ten ethno-linguistic categories the 2015 census sorts the country's "
                "49 ethnic groups into")
        caveat = (
            f"'{ETHNIC_RESIDUAL}' is the census's own other-and-not-stated together with "
            "the foreign population, 1.9% of the country between them. 'Lao' here is the "
            "category and not the ethnic group: Table 1 of the Socio-Economic Atlas of "
            "the Lao PDR 2015, which defines these ten, puts the Lao of Huaphanh, "
            "Xiangkhouang, Bolikhamsai, Vientiane province and Hinboun district into "
            "'Tai-Thay', so nationally the two come to 43.7% and 18.3% where the census's "
            "own ethnic-group table prints Lao 53.2%; together they are its Lao-Tai "
            "family, 62.4%.")
    else:
        what = "the five religions the 2015 census counts"
        caveat = (
            f"'{RELIGION_RESIDUAL}' is everything the five leave, and it is large because "
            "the census defines a religion as a spiritual system with written doctrines: "
            "the animist beliefs of most non-Lao-Tai people are recorded in it, along "
            "with 1.8% of the country who stated nothing. Nationally it is 33.3%, of "
            "which the census publishes 31.4% as no religion.")
    return (f"Shares of {what}, summed from the Lao Statistics Bureau's village indicator "
            "table for the census -- each village's published percentage turned back into "
            "people by its own published population, then added up over this unit. A "
            f"category under 0.05% of the unit is inside the residual too. {caveat} The "
            "census's English results volume prints this composition for the country "
            "only.")


def build(units: dict[Any, dict[str, Any]], level: str) -> list[dict[str, Any]]:
    from common import slugify
    out: list[dict[str, Any]] = []
    for unit in sorted(units.values(), key=lambda u: (u["province"], u["name"])):
        name, province, total = unit["name"], unit["province"], unit["population"]
        ethnicity = composition(unit["ethnicity"], total, ETHNIC_RESIDUAL)
        religion = composition(unit["religion"], total, RELIGION_RESIDUAL)
        fields: dict[str, Any] = {
            "country": "LAO",
            "population": measure(int(round(total)), year=YEAR, source=SOURCE),
            "ethnicity": ethnicity or None,
            "religion": religion or None,
            "ethnicity_year": YEAR if ethnicity else None,
            "religion_year": YEAR if religion else None,
            "ethnicity_note": note("ethnicity") if ethnicity else None,
            "religion_note": note("religion") if religion else None,
            "sources": [{"field": field, "name": SOURCE, "url": LANDING,
                         "license": LICENCE}
                        for field in ("population", "ethnicity", "religion")],
        }
        if unit["male"]:
            fields["sex_ratio"] = measure(round(1000.0 * unit["female"] / unit["male"]),
                                          unit="females_per_1000_males", year=YEAR,
                                          source=SOURCE)
        if level == "province":
            out.append(record(f"LAO-{slugify(name)}", name, level="admin1",
                              parent="LAO", **fields))
        else:
            out.append(record(f"LAO-{slugify(province)}-{slugify(name)}", name,
                              level="admin2", parent=f"LAO-{slugify(province)}",
                              parent_name=province, **fields))
    return out


def run(level: str) -> int:
    log(f"laos: {SOURCE}")
    path = download(XLSX, RAW / "laos" / "lao-population-census-2015.xlsx")
    provinces, districts, unplaced = gather(villages(path))
    if unplaced:
        log(f"  {len(unplaced)} district name(s) this reader cannot place, left "
            "unwritten and counted only into their province:")
        for line in unplaced:
            log(f"    {line}")
    absent = sorted({f"{p} / {d}" for p, names in DISTRICTS.items() for d in names}
                    - {f"{p} / {d}" for p, d in districts})
    if absent:
        log(f"  {len(absent)} shape(s) of the boundary file with no village read for "
            f"them: {absent}")
    check(provinces, districts)
    for want in ("province", "district"):
        if level not in (want, "both"):
            continue
        records = build(provinces if want == "province" else districts, want)
        for r in records:
            top = ", ".join(f"{g['group']} {g['pct']}" for g in (r["ethnicity"] or [])[:3])
            log(f"    {r['name'][:26]:26} {r['population']['value']:>9,}  {top}")
        write_json(PROCESSED / OUT[want], records)
        log(f"  wrote {len(records)} {want} rows to {OUT[want]}")
    return 0


# ---------------------------------------------------------------------------
# --probe: the reconnaissance that found the table. Writes nothing.
# ---------------------------------------------------------------------------

PAGES = [
    ("LSB home", "https://lsb.gov.la/", r"\.pdf|\.xlsx?|census|populat|ethnic"),
    ("LSB home (www)", "https://www.lsb.gov.la/", r"\.pdf|\.xlsx?|census|populat"),
    ("LaoSIS", "https://laosis.lsb.gov.la/", r"\.pdf|\.xlsx?|census|populat"),
    ("UNFPA Laos publications", "https://lao.unfpa.org/en/publications",
     r"\.pdf|census|publication"),
    ("UNFPA Laos census page",
     "https://lao.unfpa.org/en/publications/"
     "results-population-and-housing-census-2015-english-version", r"\.pdf"),
    ("Open Development Laos, census search",
     "https://data.laos.opendevelopmentmekong.net/api/3/action/package_search"
     "?q=census&rows=25", ""),
    ("Open Development Laos, ethnicity search",
     "https://data.laos.opendevelopmentmekong.net/api/3/action/package_search"
     "?q=ethnic&rows=25", ""),
    ("decide.la", "https://www.decide.la/en/", r"\.pdf|\.xlsx?|census|ethnic"),
]
FILES = [
    "https://lao.unfpa.org/sites/default/files/pub-pdf/PHC-ENG-FNAL-WEB_0.pdf",
    "https://www.lsb.gov.la/wp-content/uploads/2021/03/PHC-ENG-FNAL-WEB.pdf",
    "https://www.unicef.org/laos/media/2216/file/LSIS%20II%20Report%20English.pdf",
    XLSX,
]
HDX_SEARCHES = ["Lao PDR census", "Laos population housing census 2015",
                "Lao ethnicity", "Lao PDR subnational population"]
WIKI_INSPECT = [("en", "Provinces of Laos"), ("en", "Demographics of Laos"),
                ("en", "Ethnic groups in Laos"), ("en", "Religion in Laos"),
                ("lo", "ປະເທດລາວ"), ("en", "Savannakhet province")]
WIKI_SEARCHES = [("en", "Laos census 2015 province ethnicity Khmu Hmong"),
                 ("lo", "ສຳຫຼວດພົນລະເມືອງ 2015 ຊົນເຜົ່າ")]
CENSUS_PDF = "https://lao.unfpa.org/sites/default/files/pub-pdf/PHC-ENG-FNAL-WEB_0.pdf"
PROVINCE_TERMS = ["Vientiane Capital", "Phongsaly", "Luangnamtha", "Oudomxay", "Bokeo",
                  "Luangprabang", "Huaphanh", "Xayabury", "Xiengkhuang", "Borikhamxay",
                  "Khammuane", "Savannakhet", "Saravane", "Sekong", "Champasack",
                  "Attapeu", "Xaysomboun"]
ETHNONYMS = ["Khmou", "Hmong", "Phouthay", "Makong", "Katang", "Lue", "Akha", "Katu",
             "Ta-oy", "Brao", "Oy", "Ngouan", "Suay", "Harak", "Yrou", "Trieng",
             "Lavy", "Lamed", "Lahou", "Ewmien", "Syla", "Lolo", "Pacoh", "Nhaheun"]
FAITHS = ["Buddhis", "Christian", "Bahai", "Islam", "Muslim", "No religion", "Religion"]
LANGUAGE_TERMS = ["Mother tongue", "mother tongue", "Language spoken", "Lao-Tai",
                  "Mon-Khmer", "Chine-Tibet", "Hmong-Mien", "Ethno-linguistic"]
WP_HOST = "https://www.lsb.gov.la"
PORTALS = ["https://laosis.lsb.gov.la/", "http://laosis.lsb.gov.la/",
           "https://www.decide.la/", "http://www.decide.la/"]
UNFPA_PAGES = [f"https://lao.unfpa.org/en/publications?page={n}" for n in range(0, 6)]
ODM_QUERIES = ["Lao population census 2015", "census 2015 ethnic", "LSIS",
               "Lao social indicator survey", "population province Laos"]
ODM_DATASETS = [
    "lao-population-and-housing-census-2015-general-demographic",
    "iv-2015", "4-2015", "socioeconomic-atlas-of-the-lao-pdr-2015",
    "population-census-lao-pdr-20051",
    "census-results-in-brief-laos-population-census-2005-and-1995",
    "lsis-ii-2017", "lao-social-indicator-survey-ii-201718",
    "lao-population-and-education-2019", "ethnic-family-of-lao-pdr",
]


def get(url: str, timeout: int = 45, limit: int = 400_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read(limit)
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{len(blob):>10}  {url}")
            return blob.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        log(f"  {exc.code} {exc.reason}  {url}")
    except Exception as exc:  # noqa: BLE001 -- the failure mode is the finding
        log(f"  !! {type(exc).__name__}: {str(exc)[:120]}  {url}")
    return ""


def head(url: str, timeout: int = 45) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{resp.headers.get('Content-Length', '?'):>12}  {url}")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            get(url, timeout=timeout, limit=2048)
        else:
            log(f"  {exc.code} {exc.reason}  {url}")
    except Exception as exc:  # noqa: BLE001
        log(f"  !! {type(exc).__name__}: {str(exc)[:120]}  {url}")


def probe_pages() -> None:
    log("== route (a): the office, its partners and the open-data portal")
    for label, url, pattern in PAGES:
        log(f"  -- {label}")
        body = get(url)
        if not body:
            continue
        if "action/package_search" in url:
            try:
                result = json.loads(body).get("result", {})
            except json.JSONDecodeError:
                log(f"      not JSON: {' '.join(body[:200].split())!r}")
                continue
            log(f"      {result.get('count', 0)} dataset(s)")
            for pkg in result.get("results", [])[:25]:
                log(f"      pkg {pkg.get('name')}: {str(pkg.get('title', ''))[:80]}")
            continue
        hrefs = sorted(set(re.findall(r'href="([^"]+)"', body)))
        hits = [h for h in hrefs if not pattern or re.search(pattern, h, re.IGNORECASE)]
        log(f"      {len(hrefs)} links, {len(hits)} matching")
        for href in hits[:60]:
            log(f"      -> {href[:170]}")


def probe_files() -> None:
    log("== route (f): the candidate volumes, by name")
    for url in FILES:
        head(url)


def probe_hdx() -> None:
    log("== route (h): HDX")
    for query in HDX_SEARCHES:
        url = ("https://data.humdata.org/api/3/action/package_search?"
               + urllib.parse.urlencode({"q": query, "rows": "20"}))
        body = get(url, limit=2_000_000)
        if not body:
            continue
        try:
            result = json.loads(body).get("result", {})
        except json.JSONDecodeError:
            log("      not JSON")
            continue
        log(f"  search {query!r}: {result.get('count', 0)} dataset(s)")
        for pkg in result.get("results", [])[:20]:
            org = (pkg.get("organization") or {}).get("name", "?")
            fmts = sorted({str(r.get("format", "?")) for r in pkg.get("resources", [])})
            log(f"    {org:28} {str(pkg.get('name', ''))[:60]:60} {fmts}")


def wiki_api(lang: str, **params: str) -> dict:
    q = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    return http_json(f"https://{lang}.wikipedia.org/w/api.php?{q}", timeout=90,
                     cache=False)


def probe_wiki(rows_shown: int = 3) -> None:
    log("== route (w): Wikipedia")
    for lang, query in WIKI_SEARCHES:
        try:
            hits = wiki_api(lang, action="query", list="search", srsearch=query,
                            srlimit="12").get("query", {}).get("search", [])
            log(f"  [{lang}] search {query!r}: " + "; ".join(h["title"] for h in hits))
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] search {query!r}: {type(exc).__name__}: {str(exc)[:100]}")
    for lang, title in WIKI_INSPECT:
        try:
            parsed = wiki_api(lang, action="parse", page=title, prop="wikitext",
                              redirects="1").get("parse") or {}
            text = parsed.get("wikitext") or ""
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] {title!r}: {type(exc).__name__}: {str(exc)[:100]}")
            continue
        found = tables(text)
        log(f"  [{lang}] {title!r}: {len(text):,} bytes, {len(found)} table(s)")
        for n, t in enumerate(found):
            if not t:
                continue
            log(f"     -- table {n}: {len(t)} rows x {len(t[0])} cols; "
                f"header {[c.strip()[:24] for c in t[0][:9]]}")
            for row in t[1:1 + rows_shown]:
                log(f"        {[c.strip()[:24] for c in row[:9]]}")


def page_texts(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    log(f"  {len(reader.pages)} pages")
    return [(page.extract_text() or "") for page in reader.pages]


def probe_volume(samples: int = 2, contents: str = "") -> None:
    """Which pages of the census volume cross one of the three fields with a
    province, and what its table captions promise."""
    log(f"== route (p): the census volume {CENSUS_PDF}")
    pages = page_texts(download(CENSUS_PDF, RAW / "laos" / "PHC-ENG-FNAL-WEB_0.pdf"))
    for n in [int(x) for x in contents.split(",") if x.strip().isdigit()]:
        if 1 <= n <= len(pages):
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines()
                             if line.strip())
            log(f"  -- page {n}:\n{body[:4000]}")
    for label, terms, need in (("ethnic", ETHNONYMS, 5), ("religion", FAITHS, 3),
                               ("language", LANGUAGE_TERMS, 2)):
        hits = [(n, [pv for pv in PROVINCE_TERMS if pv in page])
                for n, page in enumerate(pages, 1)
                if sum(t in page for t in terms) >= need]
        log(f"  {len(hits)} page(s) name {need}+ {label} terms; "
            f"{sum(1 for _n, pv in hits if pv)} of them beside a province")
        log("    " + " ".join(f"p{n}{'[' + ','.join(sorted(set(pv))[:3]) + ']' if pv else ''}"
                              for n, pv in hits)[:2500])
        shown = 0
        for n, pv in hits:
            if not pv or shown >= samples:
                continue
            shown += 1
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines()
                             if line.strip())
            log(f"  -- page {n} ({label}):\n{body[:3000]}")
    captions = sorted({" ".join(m.group(0).split()) for page in pages
                       for m in re.finditer(r"Table\s+[\dA-Z][\d.\-A-Z]*\s*:?[^\n]{0,140}",
                                            page)})
    log(f"  {len(captions)} distinct table captions:")
    for cap in captions:
        log(f"    {cap[:170]}")


def probe_wordpress() -> None:
    log("== route (x): lsb.gov.la's own file store, through the WordPress API")
    for page in range(1, 8):
        body = get(f"{WP_HOST}/wp-json/wp/v2/media?per_page=100&page={page}",
                   limit=4_000_000)
        if not body:
            break
        try:
            items = json.loads(body)
        except json.JSONDecodeError:
            log(f"      not JSON: {' '.join(body[:200].split())!r}")
            break
        if not isinstance(items, list) or not items:
            break
        for item in items:
            src = str(item.get("source_url", ""))
            if re.search(r"\.(pdf|xlsx?|csv|zip)$", src, re.IGNORECASE):
                log(f"    {str(item.get('date', ''))[:10]}  {src[:150]}")
        if len(items) < 100:
            break


def probe_portals() -> None:
    log("== route (x): the statistics portals")
    for url in PORTALS:
        get(url, limit=4000)
    log("  -- laosis with the intermediate certificate its server omits")
    try:
        body = http_get("https://laosis.lsb.gov.la/", cache=False, retries=0,
                        timeout=60, aia=True)
        assert isinstance(body, str)
        log(f"  aia 200 {len(body):>8}: {' '.join(body[:600].split())}")
    except Exception as exc:  # noqa: BLE001
        log(f"  aia !! {type(exc).__name__}: {str(exc)[:140]}")


def probe_unfpa() -> None:
    log("== route (x): every page of UNFPA Laos's publication list")
    seen: set[str] = set()
    for url in UNFPA_PAGES:
        for href in sorted(set(re.findall(r'href="([^"]+)"', get(url)))):
            if "/publications/" in href and href not in seen:
                seen.add(href)
                log(f"    {href[:160]}")


def probe_odm() -> None:
    log("== route (x): Open Development Laos, by phrase")
    for query in ODM_QUERIES:
        url = ("https://data.laos.opendevelopmentmekong.net/api/3/action/package_search?"
               + urllib.parse.urlencode({"q": query, "rows": "15"}))
        body = get(url, limit=2_000_000)
        if not body:
            continue
        try:
            result = json.loads(body).get("result", {})
        except json.JSONDecodeError:
            continue
        log(f"  {query!r}: {result.get('count', 0)} dataset(s)")
        for pkg in result.get("results", [])[:15]:
            log(f"    {str(pkg.get('name', ''))[:70]:70} {str(pkg.get('title', ''))[:70]}")


def probe_datasets() -> None:
    """Every resource of the datasets the phrase search named, whole: a CKAN
    listing truncates a URL and a truncated URL cannot be fetched."""
    log("== route (d): Open Development Laos, dataset by dataset")
    for name in ODM_DATASETS:
        url = ("https://data.laos.opendevelopmentmekong.net/api/3/action/package_show?"
               + urllib.parse.urlencode({"id": name}))
        body = get(url, limit=4_000_000)
        if not body:
            continue
        try:
            pkg = json.loads(body).get("result") or {}
        except json.JSONDecodeError:
            log("      not JSON")
            continue
        log(f"  == {name}: {str(pkg.get('title', ''))[:100]}")
        log(f"     licence: {pkg.get('license_title')!r} {pkg.get('license_id')!r} "
            f"{pkg.get('license_url')!r}")
        notes = " ".join(str(pkg.get("notes") or "").split())
        if notes:
            log(f"     notes: {notes[:500]}")
        for res in pkg.get("resources", []):
            log(f"     {str(res.get('format', '?')):9} {str(res.get('name', ''))[:70]}")
            log(f"         {res.get('url', '')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="both", choices=("province", "district", "both"))
    ap.add_argument("--probe", action="store_true",
                    help="reconnoitre the routes and write nothing")
    ap.add_argument("--routes", default="adfhpwx",
                    help="a (office and portal pages), d (portal datasets), f (files by "
                         "name), h (HDX), p (scan the census volume), w (Wikipedia), "
                         "x (file store, portals, UNFPA, phrases)")
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--contents", default="",
                    help="with route p: page numbers to print whole")
    args = ap.parse_args()
    if not args.probe:
        return run(args.level)
    if "a" in args.routes:
        probe_pages()
    if "d" in args.routes:
        probe_datasets()
    if "f" in args.routes:
        probe_files()
    if "h" in args.routes:
        probe_hdx()
    if "p" in args.routes:
        probe_volume(args.rows, args.contents)
    if "w" in args.routes:
        probe_wiki(args.rows)
    if "x" in args.routes:
        probe_wordpress()
        probe_portals()
        probe_unfpa()
        probe_odm()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
