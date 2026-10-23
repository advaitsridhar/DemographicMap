#!/usr/bin/env python3
"""Egypt -- governorates, kisms and markazes: CAPMAS's 2017 census and 2023
estimate, and its 2006 census where today's units cannot be matched to 2006's.

The Central Agency for Public Mobilization and Statistics (CAPMAS) took the
Population, Housing and Establishments Census on 28 March 2017 and estimates
the population of every kism and markaz each year. Its own site serves none of
this to a reader outside Egypt; City Population (Thomas Brinkhoff) tabulates it
from CAPMAS (``URL``): every governorate, kism, markaz and police district with
its counts at the 1996, 2006 and 2017 censuses and the estimate for 1 July
2023, and for each, on its own page, the 2017 census's count of everyone by sex
and ten-year age group. OCHA publishes on HDX the 2006 census's count of every
kism and markaz by sex (``HDX_DATASET``).

**The outlines are 2006's.** The map's 364 second-level outlines are the kisms
and markazes of the 2006 census -- their labels are the English names of
OCHA's 2006 table, 2006's Muntaza, Amriya and Raml where CAPMAS now counts
Muntaza 1 and 2, Amriya 1 and 2, Raml 1 and 2. Each outline is bound to the
2006 unit of its label (in its governorate, or in another where the outline is
filed under the wrong one), a kism and a markaz of one name by size, and the
2006 unit to the units CAPMAS counts today by their Arabic names: the same
name, the parts numbered since ("قسم أول/ثان ..."), a unit renamed since
(``RENAMED``), and, where those fall short of the 2006 count, the one or two
units of other names whose 2006 people make up the rest (``carve``).

**The ground test.** CAPMAS's counts of today's units at the 2006 census,
added up, must make the 2006 unit's own count -- to within 2%, or to within 3%
once scaled by the governorate's two 2006 totals where those differ by less
than 5% (the two tabulations of 2006 differ by about 1% nationally), or to
within ``SLACK_PEOPLE`` people (a unit of a few dozen people in 2006, which a
guard post more or less puts out by a quarter). An outline that passes is
written with today's figures:

* the population: CAPMAS's estimate for 1 July 2023 (the 2017 count in the
  note);
* the median age, interpolated within the ten-year group that holds the middle
  person, and men per 1,000 women, from the 2017 census by sex and age.

An outline that does not is written with the 2006 census's own count and men
per 1,000 women, its notes say how far the two tables of 2006 disagree, and its
median age says why there is none.

**OCHA's table has keying errors** that leave a row's total whole: Beni Suef's
markaz holds a village of 4,696 men and 43,731 women. The ground test fails on
such a row and not on the ground, so ``SAME_GROUND`` declares the outlines
whose row is shown wrong by CAPMAS's own count of 2006 (each a sub-district
row set right by one digit), and no ratio of men to women is written from
2006 where it is far below every other unit's (``LOW``) or where the unit's
sub-district rows hold one with three times as many women as men -- OCHA's
sub-district rows that cannot be right are logged (``keyed_rows``).

**Ratios from few people.** No ratio of men to women is written from fewer
than ``FEW`` people (the Marina kism's 41 men and 1 woman in 2006); a ratio of
``HIGH`` or more says where such a share of men usually comes from.

The governorates are written the same way from their own rows and pages. Where
the governorate outline drawn holds other governorates' kisms and markazes, or
leaves out its own (``DRAWN_IN``), its notes say which; where those come to a
tenth of the governorate's people or more, its figures are refused there with
the reason, since they describe other ground.

**Not written.** The fourteen outlines labelled Zemam Out -- the land outside
the zimam, the bounds of the towns and villages, which no census table counts
as a district -- and the port police districts, which CAPMAS lists without a
population, say so, citing the tables they speak of. Hala'ib, the kism of the
triangle north of 22°N that Egypt and Sudan both claim, is not drawn on
Egypt's side; it is never written, and the Red Sea governorate is written
without it.

**Names.** An outline is written under the name its notes give the units it
holds -- CAPMAS's names today, as City Population writes them: the label
"DuqqI" is the kism of Ad-Duqqī, "Paris Paris" the markaz of Bārīs -- and a
kism and a markaz of one name in one governorate each say which they are. A
governorate takes the English name its notes use ("Luxor Governorate" for
the label "Luxor Governate"). Every label is kept as an alias.

Usage:
    python -m scripts.fetch_census.egypt_census
"""

from __future__ import annotations

import argparse
import io
import itertools
import json
import re
import time
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from typing import Any

from . import uscb
from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record,
                      write_json)
from common import as_drawn  # noqa: E402  (on the path through _shared)

URL = "https://www.citypopulation.de/en/egypt/admin/"
BASE = "https://www.citypopulation.de"
HDX_DATASET = "egypt-population-statistics-0"
OUT = "egypt_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
CAPMAS = "Central Agency for Public Mobilization and Statistics (CAPMAS)"
CP = "as City Population (Thomas Brinkhoff) tabulates it"
# Each publication by its own name: the figure card shows the publisher (the
# text before the first comma), the sources list each publication once.
SOURCE_2023 = (f"{CAPMAS}, population estimate for 1 July 2023 of every governorate, kism "
               f"and markaz, {CP}")
SOURCE_2017_COUNT = (f"{CAPMAS}, Population, Housing and Establishments Census 2017, population "
                     f"of every governorate, kism and markaz, {CP}")
SOURCE_2017 = (f"{CAPMAS}, Population, Housing and Establishments Census 2017, population by "
               f"sex and ten-year age group, {CP}")
SOURCE_2006_CP = (f"{CAPMAS}, Population, Housing and Establishments Census 2006, population of "
                  f"the units counted since, {CP}")
SOURCE_2006 = (f"{CAPMAS}, Population, Housing and Establishments Census 2006, population by "
               "sex of every kism and markaz, as OCHA publishes it on HDX")
CP_LICENCE = "citation of City Population (citypopulation.de) required"
# CAPMAS's governorate code -> the map's ISO 3166-2 code; two outlines carry no
# code and are found by label (``UNCODED``).
GOV_ISO = {"01": "EG-C", "02": "EG-ALX", "03": "EG-PTS", "04": "EG-SUZ", "11": "EG-DT",
           "12": "EG-DK", "13": "EG-SHR", "14": "EG-KB", "15": "EG-KFS", "16": "EG-GH",
           "17": "EG-MNF", "18": "EG-BH", "19": "EG-IS", "21": "EG-GZ", "22": "EG-BNS",
           "23": "EG-FYM", "24": "EG-MN", "25": "EG-AST", "26": "EG-SHG", "27": "EG-KN",
           "28": "EG-ASN", "29": "EG-LX", "31": "EG-BA", "32": "EG-WAD", "33": "EG-MT",
           "34": "EG-SIN", "35": "EG-JS"}
UNCODED = {"EG-GH": "Gharbiyya Governorate", "EG-MT": "Matrouh Governorate"}
GOV_EN = {"01": "Cairo", "02": "Alexandria", "03": "Port Said", "04": "Suez", "11": "Damietta",
          "12": "Dakahlia", "13": "Sharqia", "14": "Qalyubia", "15": "Kafr el-Sheikh",
          "16": "Gharbia", "17": "Monufia", "18": "Beheira", "19": "Ismailia", "21": "Giza",
          "22": "Beni Suef", "23": "Faiyum", "24": "Minya", "25": "Asyut", "26": "Sohag",
          "27": "Qena", "28": "Aswan", "29": "Luxor", "31": "Red Sea", "32": "New Valley",
          "33": "Matrouh", "34": "North Sinai", "35": "South Sinai"}
# A 2006 unit whose rows OCHA's table labels with another unit's English name
# (gov code, Arabic name) -> the label of its outline: Shaykh Zayed and Awsim,
# both labelled Waraq; 6th of October's two kisms, whose labels a spreadsheet
# read as dates ("06-Oct-01").
RELABEL = {("21", "قسم الشيخ زايد"): "Shaykh Zayed", ("21", "مركز أوسيم"): "Auseem",
           ("21", "قسم أول 6 أكتوبر"): "6 October-1", ("21", "قسم ثان 6 أكتوبر"): "6 October-2"}
# A 2006 unit CAPMAS counts under another name since (gov code, its Arabic
# name in OCHA's table) -> (today's Arabic name, the 2006 unit's English name).
# Marina al-Alamein's tourist kism is today's kism of al-Alamayn: each is the
# one unit of Matrouh the other table lacks, and both tables count about fifty
# people there in 2006 (OCHA 42, CAPMAS 52).
RENAMED = {("33", "قسم مارينا العلمين السياحية"): ("قسم العلمين", "Marina al-Alamein")}
# 2006 units whose row in OCHA's table is shown wrong by CAPMAS's own count of
# 2006, so that the ground test fails on the row and not on the ground (gov
# code, Arabic name) -> the evidence. Each takes today's figures.
SAME_GROUND = {
    # Sub-district 220202, al-Hakamina: 4,696 men and 43,731 women, a 4 keyed in
    # front of 3,731 (107 men per 1,000 women in one village). Without it the
    # markaz holds 152,303 men and 144,951 women, 297,254 people; CAPMAS's 2006
    # count of today's markaz is 298,047. Every other markaz of Beni Suef agrees
    # between the two tables to within 0.05%.
    ("22", "مركز بنى سويف"): "OCHA's sub-district 220202 holds 4,696 men and 43,731 women",
    # 100,724 men and 129,511 women, 778 per 1,000; CAPMAS's 2006 count of
    # today's markaz is 200,432, which with OCHA's men leaves 99,708 women, 1,010
    # men per 1,000 as in the markazes around it. Damietta's other units agree
    # between the two tables to within 0.7%, and its OCHA total exceeds CAPMAS's
    # by 26,578 where nearly every governorate's falls short.
    ("11", "مركز فارسكور"): "OCHA's row holds 29,803 more women than CAPMAS's count allows",
    # 216,280 men and 81,386 women, 2,657 per 1,000; CAPMAS's 2006 count of the
    # kism is 161,946 -- OCHA's women and 80,560 men, 990 per 1,000. CAPMAS's
    # count is OCHA's without a block of 135,720 men, not other ground; Cairo's
    # other kisms agree (Sharabiyya and Zawiya al-Hamra to the person).
    ("01", "قسم النزهة"): "OCHA's row holds 135,720 more men than CAPMAS's count of the kism",
    # The keyed rows the run logs (``keyed_rows``), each set right by one digit,
    # bring OCHA's count to CAPMAS's own count of 2006 of today's markaz:
    # Fariskur's al-Ubaydiya, 1,643 men and 31,648 women (with 1,648 women the
    # markaz holds 200,235; CAPMAS 200,432) -- the 29,803 above; Abu Tisht's
    # al-Awamir al-Gharbiya, 16,666 men and 1,979 women (with 1,666 men, 359,375;
    # CAPMAS 359,443); Awlad Saqr's Ibrahim Hassan, 8,685 men and 1,389 women
    # (with 1,685 men, 175,868; CAPMAS 175,665); Asyut's Dronka, 2,491 men and
    # 22,740 women (with 22,491 men, 397,063; CAPMAS 399,288, the governorate's
    # tables 1.7% apart).
    ("27", "مركز أبو طشت"): "OCHA's sub-district 270318 holds 16,666 men and 1,979 women",
    ("13", "مركز أولاد صقر"): "OCHA's sub-district 131902 holds 8,685 men and 1,389 women",
    ("25", "مركز أسيوط"): "OCHA's sub-district 250315 holds 2,491 men and 22,740 women",
}
# Two outlines labelled North Coast, both filed under Matrouh: the eastern one
# continues Burg al-Arab's side (Alexandria's) of the boundary at 29.38°E, the
# western one Al-Hammam's (Matrouh's). Shape id -> (gov code, Arabic name).
SHAPES = {"37247803B38142631960117": ("02", "الساحل الشمالى_جزء"),
          "37247803B36627997079635": ("33", "قسم الساحل الشمالى-جزء")}
# Kisms and markazes whose outline lies in another governorate's outline as
# the first level draws it: most of the outline's area, and every town of it
# GeoNames places, fall in the other polygon. Shape id -> the governorate code
# of the first-level outline that holds it.
DRAWN_IN = {
    "37247803B95427647060127": "29",   # Qus (Qena's): wholly in Luxor's outline
    "37247803B87719226438942": "29",   # Naqada (Qena's): 98%, and the town, in Luxor's
    "37247803B29149830762978": "27",   # Isna (Luxor's): Esna town in Qena's
    "37247803B51665438591487": "14",   # Marg (Cairo's): 95% in Qalyubia's
    "37247803B59541002076203": "14",   # Al Salam (Cairo's): 56% in Qalyubia's
    "37247803B72756565577460": "21",   # Zamalik (Cairo's): 98% in Giza's
    "37247803B47496652532681": "01",   # 10 Ramadan 1 (Sharqia's): wholly in Cairo's
    "37247803B42052057109088": "33",   # Burg al-Arab (Alexandria's): 70%, and the town
    "37247803B38142631960117": "33",   # North Coast, Alexandria's part: 98% in Matrouh's
    "37247803B87041728070842": "11",   # Minya al-Nasr (Dakahlia's): 58%, and its towns
    "37247803B60942546572959": "26",   # Al-Ghanayem (Asyut's): 55%, and the town, in Sohag's
    "37247803B67659065091710": "32",   # Guhayna al-Gharbiyya (Sohag's): 70%, and Juhayna
    "37247803B45887361748458": "32",   # Suhag City (Sohag's new city): wholly in New Valley's
}
# The share of a governorate's people in kisms and markazes its outline holds
# or lacks at which its figures are refused there.
GOV_LARGE = 0.10
# A statement of other ground displaces an encyclopaedia's older or undated
# figure for the governorate outline: theirs are CAPMAS's governorates too.
DISPLACES_BEFORE = 2026
ZEMAM = "zemamout"
# The kism of Hala'ib, in the triangle Egypt and Sudan both claim.
CLAIMED = {"3108"}
PLAIN, SCALED, SEARCH = 0.02, 0.03, 0.01
SLACK_PEOPLE = 50
# No ratio of men to women from fewer people than this.
FEW = 1000
# Men per 1,000 women at which a note says where such a share comes from.
HIGH = 1250
# Below this, for a unit of more than BIG people, a 2006 ratio is not written:
# no unit of Egypt that size counts so few men (the next lowest is 869).
LOW, BIG = 900, 50_000
HIGH_NOTE = (" The census counts people where they live, and a share of men this high usually "
             "comes from men living apart from their families: workers in hostels, staff "
             "housing and camps, soldiers in barracks, and prisoners.")
SCALE_LIMIT = 0.05
PAUSE = 0.4
AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": None,
                    "ئ": "ي", "ؤ": "و"})
ORDINALS = {"اول": 1, "ثان": 2, "ثاني": 2, "ثالث": 3, "رابع": 4, "خامس": 5, "سادس": 6,
            "سابع": 7, "ثامن": 8}
KINDS = (("قسم شرطه", "kism"), ("قسم", "kism"), ("مركز", "markaz"),
         ("اداره شرطه", "police"), ("شرطه", "police"), ("مدينه", "city"))
# City Population's status of a unit -> its kind, one and many.
STATUS_KINDS = (("kism", "kism", "kisms"), ("markaz", "markaz", "markazes"),
                ("new city", "new city", "new cities"),
                ("police", "police district", "police districts"), ("area", "area", "areas"))


# ---------------------------------------------------------------- names

def arfold(text: Any) -> str:
    out = unicodedata.normalize("NFKC", str(text or "")).translate(AR)
    out = "".join(c for c in out if unicodedata.category(c) != "Cf")
    return " ".join(re.sub(r"[_\-]", " ", out).split())


def arkey(text: Any) -> tuple[str, int | None, str]:
    """(kind, ordinal, name) of an Arabic unit name: 'قسم ثان المنتزة' ->
    ('kism', 2, 'المنتزه'). 'Police' and 'city' before the name are dropped,
    as the two tables write them for one unit and not the other ('مركز باريس',
    'مركز شرطة باريس'; 'قسم بدر', 'قسم مدينة بدر')."""
    name = arfold(text)
    kind = "other"
    for word, k in KINDS:
        if name.startswith(word):
            kind, name = k, name[len(word):].strip()
            break
    ordinal, rest = None, []
    for w in name.split():
        if w in ORDINALS and ordinal is None:
            ordinal = ORDINALS[w]
        elif w in ("شرطه", "مدينه") and not rest:
            continue
        else:
            rest.append(w)
    return kind, ordinal, re.sub(r"جزء$", "", "".join(rest))


def keys(native: str) -> set[tuple[str, int | None, str]]:
    """A unit CAPMAS names twice ('قسم أول 6 أكتوبر / قسم ثالث 6 أكتوبر') has both."""
    return {arkey(part) for part in str(native).split("/") if part.strip()}


def latin(text: Any) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalnum() and not unicodedata.combining(c))


def count(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def plural(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def listed(items: list[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ------------------------------------------------------- citypopulation

def strip_tags(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").split())


def clean(name: str) -> str:
    """'Al-Manṣūrah 1 [ El Mansoura ]' -> 'Al-Manṣūrah 1'; 'Shurṭah Bārīs'
    (Baris police district) -> 'Bārīs'."""
    name = re.sub(r"\s*\[.*?\]", "", str(name)).strip()
    return re.sub(r"^Shurṭah\s+", "", name)


def part_kind(unit: dict[str, Any]) -> tuple[str, str]:
    status = str(unit.get("status") or "").lower()
    for word, one, many in STATUS_KINDS:
        if status.startswith(word):
            return one, many
    return "unit", "units"


def describe_parts(parts: list[dict[str, Any]]) -> str:
    """Today's units by kind and name: 'the kism and the markaz of Abū Tīj',
    'the markazes of Al-Ḥusayniyah, Munshāh Abū 'Umar and Ṣān al-Ḥajar'."""
    names = [clean(c["name"]) for c in parts]
    kinds = [part_kind(c) for c in parts]
    if len(set(names)) == 1 and len(set(kinds)) == len(kinds):
        return " and ".join(f"the {one}" for one, _ in kinds) + f" of {names[0]}"
    groups: dict[tuple[str, str], list[str]] = {}
    for kind, name in zip(kinds, names):
        groups.setdefault(kind, []).append(name)
    return listed([f"the {one} of {ns[0]}" if len(ns) == 1 else f"the {many} of {listed(ns)}"
                   for (one, many), ns in groups.items()])


def parse_admin(html: str) -> dict[str, Any]:
    """{"govs": {code: row}, "units": {code: row}} from the table of every unit.

    A row: name, status, Arabic name, the counts of 1996, 2006, 2017 and the
    estimate of 2023 (None where the page has '...'), and the link to its page."""
    govs: dict[str, dict[str, Any]] = {}
    units: dict[str, dict[str, Any]] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        m = re.search(r'id="i(\d+)"', tr)
        status = re.search(r'<td class="rstatus">(.*?)</td>', tr, flags=re.S)
        native = re.search(r'<td class="rnative[^"]*">(.*?)</td>', tr, flags=re.S)
        if not (m and status and native):
            continue
        name = re.search(r'<td class="rname"[^>]*>(.*?)</td>', tr, flags=re.S)
        pops = [count(strip_tags(p)) for p in
                re.findall(r'<td class="rpop">(.*?)</td>', tr, flags=re.S)]
        link = re.search(r'href="(/en/egypt/admin/[^"]+)"', tr)
        if len(pops) != 4:
            raise SystemExit(f"egypt_census: row i{m.group(1)} has {len(pops)} counts, not 4")
        row = {"code": m.group(1), "name": strip_tags(name.group(1)) if name else "",
               "status": strip_tags(status.group(1)), "ar": strip_tags(native.group(1)),
               "p1996": pops[0], "p2006": pops[1], "p2017": pops[2], "p2023": pops[3],
               "href": link.group(1) if link else None}
        if row["status"] == "Governorate":
            row["code"] = row["code"].zfill(2)
            govs[row["code"]] = row
        elif len(row["code"]) == 4:
            row["gov"] = row["code"][:2]
            units[row["code"]] = row
    return {"govs": govs, "units": units}


def parse_pyramid(html: str) -> list[tuple[int, int | None, int, int]] | None:
    """The 2017 census's men and women by ten-year age group, from the page's
    chart data: [(low, high, men, women)], youngest first; None if absent."""
    if "Age Distribution (C 2017)" not in html:
        return None
    m = re.search(r"var addChartData = (\[.*?\]);?\s*</script>", html, flags=re.S)
    if not m:
        return None
    for chart in json.loads(m.group(1)):
        if chart.get("name") == "Age Distribution" and chart.get("type") == "pyramid":
            # Ten-year groups to an open 90+; a page leaves out a group no
            # one is in, which is a group of nobody, not a break.
            found: dict[int, tuple[int, int]] = {}
            for label, men, women in chart["data"][1:]:
                g = re.match(r"(\d+)\s*(?:-\s*(\d+)|\+)", str(label))
                low = int(g.group(1)) if g else -1
                high = int(g.group(2)) if g and g.group(2) else None
                if not g or low % 10 or (high is not None and high != low + 9) \
                        or (high is None and low != 90) or low > 90:
                    raise SystemExit(f"egypt_census: an age group reads {label!r}")
                found[low] = (abs(int(men)), abs(int(women)))
            return [(low, None if low == 90 else low + 9, *found.get(low, (0, 0)))
                    for low in range(0, 100, 10)]
    return None


def grouped_median(groups: list[tuple[int, int | None, int]]) -> float | None:
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def add(pyramids: list[list[tuple[int, int | None, int, int]]], sign: list[int] | None = None
        ) -> list[tuple[int, int | None, int, int]]:
    sign = sign or [1] * len(pyramids)
    first = pyramids[0]
    return [(lo, hi, sum(s * p[i][2] for s, p in zip(sign, pyramids)),
             sum(s * p[i][3] for s, p in zip(sign, pyramids)))
            for i, (lo, hi, _, _) in enumerate(first)]


# ------------------------------------------------------------------ HDX

def read_hdx(book: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """OCHA's 2006 workbook: (district rows, {gov code: province row})."""
    def rows(name: str) -> list[list[Any]]:
        if name not in book.sheetnames:
            raise SystemExit(f"egypt_census: the 2006 workbook has no sheet {name!r}")
        return [list(r) for r in book[name].iter_rows(values_only=True)]

    def num(v: Any) -> int | None:
        return None if v in (None, "") else int(round(float(v)))
    districts = []
    for r in rows("District")[1:]:
        if not r or r[0] in (None, "Total") or r[5] in (None, ""):
            continue
        districts.append({"gov": f"{int(r[2]):02d}", "en": str(r[3]).strip(),
                          "ar": str(r[4]).strip(), "code": int(r[5]),
                          "m": num(r[6]), "f": num(r[7]), "t": num(r[8])})
    provinces = {}
    for r in rows("Province")[1:]:
        if not r or r[0] in (None, "Total") or r[2] in (None, ""):
            continue
        provinces[f"{int(r[2]):02d}"] = {"m": num(r[3]), "f": num(r[4]), "t": num(r[5])}
    total = sum(d["t"] or 0 for d in districts)
    if total != sum(p["t"] for p in provinces.values()):
        raise SystemExit(f"egypt_census: the 2006 districts make {total:,}, not the "
                         f"governorates' {sum(p['t'] for p in provinces.values()):,}")
    for d in districts:
        if None not in (d["m"], d["f"], d["t"]) and d["m"] + d["f"] != d["t"]:
            raise SystemExit(f"egypt_census: 2006 {d['en']}: men and women do not make "
                             f"{d['t']:,}")
    return districts, provinces


def keyed_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """OCHA's sub-district rows whose men and women cannot both be right:
    more than twice as many of one sex as of the other among 1,000 people or
    more. A digit keyed in front of a count makes them, and the row's total,
    made from the two, is as wrong (al-Hakamina, Beni Suef: 4,696 men and
    43,731 women). Columns: governorate, district and sub-district names and
    codes, men, women, total."""
    out = []
    for r in rows[1:]:
        if not r or len(r) < 11:
            continue
        try:
            men, women, total = (int(round(float(v))) for v in r[8:11])
            district = int(r[5])
        except (TypeError, ValueError):
            continue
        if total >= 1000 and (men > 2 * women or women > 2 * men):
            out.append({"district": district, "district_ar": str(r[4]).strip(),
                        "sub": str(r[6]).strip(), "code": r[7], "m": men, "f": women,
                        "t": total})
    return out


def units_2006(districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OCHA's rows grouped into the 2006 units they count, by governorate and
    Arabic name, each with the English labels its rows carry."""
    groups: dict[tuple[str, tuple], list[dict[str, Any]]] = defaultdict(list)
    for d in districts:
        groups[(d["gov"], arkey(d["ar"]))].append(d)
    out = []
    for (gov, key), rows in groups.items():
        relabel = next((v for (g, a), v in RELABEL.items() if g == gov and arkey(a) == key), None)
        labels = {latin(relabel)} if relabel else {latin(r["en"]) for r in rows}
        known = all(r["t"] is not None for r in rows)
        out.append({"gov": gov, "key": key, "ar": rows[0]["ar"], "rows": rows,
                    "labels": labels, "codes": sorted({r["code"] for r in rows}),
                    "m": sum(r["m"] or 0 for r in rows) if known else None,
                    "f": sum(r["f"] or 0 for r in rows) if known else None,
                    "t": sum(r["t"] or 0 for r in rows) if known else None})
    return out


def lookup(table: dict[tuple[str, str], Any], unit: dict[str, Any]) -> Any:
    """A unit's entry in a table keyed (gov code, Arabic name)."""
    return next((v for (g, a), v in table.items() if g == unit["gov"] and arkey(a) == unit["key"]),
                None)


# -------------------------------------------------------------- binding

def size(shape: dict[str, Any]) -> float:
    b = shape.get("bbox") or [0, 0, 0, 0]
    return (b[2] - b[0]) * (b[3] - b[1])


def bind_outlines(shapes: list[dict[str, Any]], gov_of: dict[str, str],
                  units: list[dict[str, Any]], report: list[str]
                  ) -> dict[str, list[dict[str, Any]]]:
    """Outline id -> the 2006 units it holds."""
    bound: dict[str, list[dict[str, Any]]] = {}
    by_gov: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        by_gov[u["gov"]].append(u)
    labels_drawn: dict[str, set[str]] = defaultdict(set)
    for s in shapes:
        labels_drawn[gov_of[s["id"]]].add(latin(s["name"]))
    for s in shapes:
        gov, label = gov_of[s["id"]], latin(s["name"])
        if label == ZEMAM:
            continue
        if s["id"] in SHAPES:
            g, ar = SHAPES[s["id"]]
            hits = [u for u in by_gov[g] if u["key"] == arkey(ar)]
            if len(hits) != 1:
                raise SystemExit(f"egypt_census: SHAPES names {ar!r}, found {len(hits)} times")
            bound[s["id"]] = hits
            continue
        cands = [u for u in by_gov[gov] if label in u["labels"]]
        where = gov
        if not cands:
            # An outline filed under the wrong governorate: its label in the
            # one governorate that has it and draws no outline of that label.
            cands = [u for u in units if label in u["labels"]
                     and label not in labels_drawn[u["gov"]]]
            if len({u["gov"] for u in cands}) == 1:
                where = cands[0]["gov"]
                report.append(f"  {s['name']!r} (filed under {gov}): the 2006 unit of "
                              f"governorate {where}")
            else:
                cands = []
        if len(cands) > 1:
            sole = [u for u in cands if u["labels"] == {label}]
            cands = sole or cands
        twins = [t for t in shapes if gov_of[t["id"]] == gov and latin(t["name"]) == label]
        kinds = {u["key"][0] for u in cands}
        if len(twins) == 2 and len(cands) == 2 and kinds == {"kism", "markaz"}:
            small = min(twins, key=size)
            want = "kism" if s["id"] == small["id"] else "markaz"
            bound[s["id"]] = [u for u in cands if u["key"][0] == want]
        elif len(twins) == 1 and len(cands) == 1:
            bound[s["id"]] = cands
        elif len(twins) == 1 and len(cands) == 2 and kinds == {"kism", "markaz"}:
            bound[s["id"]] = cands
            report.append(f"  {s['name']!r}: one outline for the kism and the markaz")
        else:
            report.append(f"  {s['name']!r} ({gov}): {len(cands)} 2006 units "
                          f"{[u['ar'] for u in cands]} for {len(twins)} outlines; not bound")
    used = Counter(id(u) for us in bound.values() for u in us)
    twice = [u["ar"] for u in units if used[id(u)] > 1]
    if twice:
        raise SystemExit(f"egypt_census: 2006 units on two outlines: {twice}")
    for u in units:
        if not used[id(u)]:
            report.append(f"  2006 unit {u['ar']} ({u['gov']}, {u['t']}) on no outline")
    return bound


def named(unit: dict[str, Any], cp_units: dict[str, dict[str, Any]],
          numbered: set[int | None] = frozenset()) -> list[dict[str, Any]]:
    """Today's units of a 2006 unit's name: the same, its numbered parts (but
    not a number another 2006 unit of the name already had: 2006's '10th of
    Ramadan' is today's first kism, its second was 2006's too), or the same
    name of another kind -- in its governorate; else the same name and kind in
    the one governorate that has it (a markaz moved from Qena to Luxor). A
    unit renamed since (``RENAMED``) is looked up by its name today."""
    renamed = lookup(RENAMED, unit)
    key = arkey(renamed[0]) if renamed else unit["key"]
    kind, ordinal, base = key
    pool = [c for c in cp_units.values() if c["gov"] == unit["gov"]]
    same = [c for c in pool if key in keys(c["ar"])]
    if same or renamed:
        return same
    if ordinal is None:
        parts = [c for c in pool if any(k[0] == kind and k[2] == base and k[1]
                                        and k[1] not in numbered for k in keys(c["ar"]))]
        if parts:
            return parts
    loose = [c for c in pool if any(k[2] == base and k[1] == ordinal for k in keys(c["ar"]))]
    if loose:
        return loose
    moved = [c for c in cp_units.values() if key in keys(c["ar"])]
    return moved if len({c["gov"] for c in moved}) == 1 else []


def factor(gov: str, cp_govs: dict[str, dict[str, Any]], provinces: dict[str, dict[str, int]]
           ) -> float:
    """The governorate's 2006 count in CAPMAS's later tables against OCHA's,
    where the two differ by less than ``SCALE_LIMIT``; else 1."""
    k = (cp_govs[gov]["p2006"] or 0) / provinces[gov]["t"] if gov in provinces else 1.0
    return k if abs(k - 1) <= SCALE_LIMIT else 1.0


def same_ground(t2006: int | None, parts: list[dict[str, Any]], k: float,
                plain: float = PLAIN, scaled: float = SCALED, slack: int = SLACK_PEOPLE
                ) -> tuple[bool, float] | None:
    if not t2006 or not parts or any(c["p2006"] is None for c in parts):
        return None
    made = sum(c["p2006"] for c in parts)
    r = made / t2006
    return (abs(r - 1) <= plain or abs(r / k - 1) <= scaled or abs(made - t2006) <= slack), r


def carve(t2006: int, parts: list[dict[str, Any]], free: list[dict[str, Any]], k: float
          ) -> list[dict[str, Any]]:
    """The one or two units of other names that, with ``parts``, make the 2006
    unit's count to within ``SEARCH``; the closest; none if none does."""
    for n in (1, 2):
        best = None
        for extra in itertools.combinations(free, n):
            test = same_ground(t2006, parts + list(extra), k, SEARCH, SEARCH, 0)
            if test and test[0]:
                err = abs(test[1] / k - 1)
                if best is None or err < best[0]:
                    best = (err, list(extra))
        if best:
            return best[1]
    return []


def compose(bound: dict[str, list[dict[str, Any]]], cp: dict[str, Any],
            provinces: dict[str, dict[str, int]], report: list[str],
            every: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Outline id -> {"parts": today's units, "same": the ground test, "ratio"}."""
    out: dict[str, dict[str, Any]] = {}
    claimed: Counter = Counter()
    plans = {}
    for sid, units in bound.items():
        parts = []
        for u in units:
            numbered = {v["key"][1] for v in every if v is not u and v["gov"] == u["gov"]
                        and v["key"][0] == u["key"][0] and v["key"][2] == u["key"][2]}
            parts += [c for c in named(u, cp["units"], numbered) if c not in parts]
        plans[sid] = parts
        claimed.update(c["code"] for c in parts)
    taken: set[str] = set()
    for sid in sorted(bound):
        units, parts = bound[sid], plans[sid]
        gov = units[0]["gov"]
        t2006 = sum(u["t"] for u in units) if all(u["t"] for u in units) else None
        k = factor(gov, cp["govs"], provinces)
        test = same_ground(t2006, parts, k)
        how = ""
        declared = [lookup(SAME_GROUND, u) for u in units if lookup(SAME_GROUND, u)]
        if declared and test:
            test = (True, test[1])
            how = f"; declared the same ground: {'; '.join(declared)}"
        if test and not test[0] and test[1] < 1:
            free = [c for c in cp["units"].values() if c["gov"] == gov and not claimed[c["code"]]
                    and c["code"] not in taken and c["p2006"] and c["code"] not in CLAIMED]
            extra = carve(t2006, parts, free, k)
            if extra:
                parts = parts + extra
                taken.update(c["code"] for c in extra)
                test = same_ground(t2006, parts, k)
                how = f"; with {[c['name'] for c in extra]}, made from it since"
        out[sid] = {"parts": parts, "same": bool(test and test[0]),
                    "ratio": test[1] if test else None, "t2006": t2006,
                    "declared": bool(declared),
                    "renamed": any(lookup(RENAMED, u) for u in units)}
        report.append(f"    {units[0]['ar']} ({t2006}) -> {[c['name'] for c in parts]} "
                      f"2006 {[c['p2006'] for c in parts]}"
                      f"{'' if test is None else f' ratio {test[1]:.3f}'}"
                      f" {'SAME' if test and test[0] else 'redrawn'}{how}")
    return out


# --------------------------------------------------------------- records

def kind_word(unit: dict[str, Any]) -> str:
    return {"kism": "kism", "markaz": "markaz", "police": "police district",
            "city": "new city"}.get(unit["key"][0], "district")


def describe(units: list[dict[str, Any]]) -> str:
    return " and ".join(f"the {kind_word(u)} of {u['display']}" for u in units)


def ratio_fields(men: int, women: int, year: int, source: str, where: str = ""
                 ) -> dict[str, Any]:
    """Men per 1,000 women and its note, or why there is none."""
    people = men + women
    if people < FEW or not women:
        return {"sex_ratio": gap(NOT_AVAILABLE, (
            f"The {year} census counted only {plural(people, 'person', 'people')} here "
            f"({plural(men, 'man', 'men')} and {plural(women, 'woman', 'women')}), too few for "
            "a ratio of men to women to describe the unit."))}
    ratio = round(1000 * men / women)
    if year == 2006 and people > BIG and ratio < LOW:
        return {"sex_ratio": gap(NOT_AVAILABLE, (
            f"The 2006 census table gives {men:,} men and {women:,} women here, {ratio:,} men "
            "per 1,000 women -- far fewer men than any other unit of Egypt of its size, more "
            "likely a keying error in the table than a count, so no ratio is given."))}
    note = f"Men per 1,000 women at the {year} census{where}: {men:,} men and {women:,} women."
    if ratio >= HIGH:
        note += HIGH_NOTE
    return {"sex_ratio": measure(ratio, unit="males_per_1000_females", year=year,
                                 source=source),
            "sex_ratio_note": note}


def notes_2017(pyr: list[tuple[int, int | None, int, int]]) -> dict[str, Any]:
    men, women = sum(p[2] for p in pyr), sum(p[3] for p in pyr)
    groups = [(lo, hi, m + f) for lo, hi, m, f in pyr]
    median = grouped_median(groups)
    out = ratio_fields(men, women, 2017, SOURCE_2017)
    if median is not None:
        out["median_age"] = measure(median, unit="years", year=2017, source=SOURCE_2017)
        out["median_age_note"] = ("Interpolated within the ten-year age group that holds the "
                                  "middle person, from the 2017 census's count of everyone by "
                                  "sex and ten-year age group.")
    return out


def later(parts: list[dict[str, Any]], t2006: int, what: str) -> str:
    """Why today's units' figures are not taken: how the two 2006 tables
    disagree, or that one gives no count to compare."""
    if not parts:
        return "CAPMAS's later tables have no unit of this name."
    them = "it" if len(parts) == 1 else "them"
    missing = [c for c in parts if c["p2006"] is None]
    if len(missing) == len(parts):
        return (f"CAPMAS's later tables give no count at the 2006 census for "
                f"{describe_parts(parts)}, the {'unit' if len(parts) == 1 else 'units'} of "
                f"this name today, to compare with this one, so {what} for {them} "
                "are not taken for this outline.")
    if missing:
        return (f"CAPMAS's later tables name {describe_parts(parts)} here today and give no "
                f"count at the 2006 census for {describe_parts(missing)} to compare with this "
                f"one, so {what} for them are not taken for this outline.")
    made = sum(c["p2006"] for c in parts)
    return (f"CAPMAS's later tables put {made:,} people in {describe_parts(parts)} at the 2006 "
            f"census, against {t2006:,} in this count, so {what} for {them} are not taken for "
            "this outline.")


def page_url(unit: dict[str, Any]) -> str:
    return BASE + urllib.parse.quote(unit["href"])


def cited(fields: dict[str, Any], *names: str) -> str:
    """The fields a source entry is cited for, as the record holds them: a
    figure by its name, a stated reason by its note ('sex_ratio note'), so
    that a reason quoting a table's counts cites the table."""
    return "/".join(n if "value" in (fields.get(n) or {}) else f"{n} note"
                    for n in names if n in fields)


# Every note of a unit no table counts, or counts with no one in it.
NOTES = "population note/median_age note/sex_ratio note"


def outline_record(shape: dict[str, Any], units: list[dict[str, Any]], plan: dict[str, Any],
                   pyramids: dict[str, list], hdx_url: str, hdx_licence: str,
                   keyed: list[dict[str, Any]] = ()) -> dict[str, Any]:
    """``keyed``: OCHA's sub-district rows of these units with three times as
    many women as men or more, which no village of Egypt holds; with one, the
    2006 table's men and women for the unit are not used.

    Every publication a note quotes is cited for that note: the 2017 count the
    2023 estimate's note gives, the two tables of 2006 a reason compares."""
    parts = plan["parts"]
    wrong = "; ".join(f"{k['sub']} with {k['m']:,} men and {k['f']:,} women" for k in keyed)
    fields: dict[str, Any] = {"sources": []}
    what = describe(units)
    pyr = [pyramids.get(c["code"]) for c in parts]
    m = sum(u["m"] for u in units) if all(u["m"] is not None for u in units) else None
    f = sum(u["f"] for u in units) if all(u["f"] is not None for u in units) else None
    have_now = plan["same"] and parts and all(c["p2017"] for c in parts)
    if have_now:
        p2017 = sum(c["p2017"] for c in parts)
        since = ""
        then: list[dict[str, Any]] = []
        if plan.get("renamed") and m is not None and f is not None:
            p2006 = sum(c["p2006"] or 0 for c in parts)
            ground = (f"{describe_parts(parts)}, which the 2006 census counted as {what} "
                      f"({plural(m, 'man', 'men')} and {plural(f, 'woman', 'women')}; CAPMAS's "
                      f"later tables put {plural(p2006, 'person', 'people')} there in 2006)")
            # Both tables of 2006, which the note quotes.
            then = [{"field": "population note", "name": SOURCE_2006, "url": hdx_url,
                     "year": 2006, "license": hdx_licence},
                    {"field": "population note", "name": SOURCE_2006_CP,
                     "url": page_url(parts[0]), "year": 2006, "license": CP_LICENCE}]
        else:
            ground = f"{what} as drawn in 2006"
            if len(parts) > 1:
                since = (f" CAPMAS counts that ground today as {describe_parts(parts)}, added "
                         "together here.")
        if all(c["p2023"] for c in parts):
            fields["population"] = measure(sum(c["p2023"] for c in parts), year=2023,
                                           source=SOURCE_2023)
            fields["population_note"] = (f"CAPMAS's estimate for 1 July 2023 of {ground}; the "
                                         f"2017 census counted {p2017:,}.{since}")
            fields["sources"] += [{"field": "population", "name": SOURCE_2023,
                                   "url": page_url(parts[0]), "year": 2023,
                                   "license": CP_LICENCE},
                                  {"field": "population note", "name": SOURCE_2017_COUNT,
                                   "url": page_url(parts[0]), "year": 2017,
                                   "license": CP_LICENCE}]
        else:
            fields["population"] = measure(p2017, year=2017, source=SOURCE_2017_COUNT)
            fields["population_note"] = f"The 2017 census count of {ground}.{since}"
            fields["sources"].append({"field": "population", "name": SOURCE_2017_COUNT,
                                      "url": page_url(parts[0]), "year": 2017,
                                      "license": CP_LICENCE})
        fields["sources"] += then
        if all(pyr) and all(abs(sum(a + b for _, _, a, b in p) - c["p2017"]) <= 5
                            for p, c in zip(pyr, parts)):
            got = notes_2017(add(pyr))
            fields.update(got)
            fields["sources"].append({"field": cited(got, "median_age", "sex_ratio"),
                                      "name": SOURCE_2017, "url": page_url(parts[0]),
                                      "year": 2017, "license": CP_LICENCE})
            return fields
        fields["median_age"] = gap(NOT_AVAILABLE, (
            "The 2017 census's count by age is not tabulated for this ground, and the 2006 "
            "census's tables by kism and markaz give no ages."))
        if plan.get("declared"):
            # OCHA's row is the one shown wrong: its sexes are not used either.
            fields["sex_ratio"] = gap(NOT_AVAILABLE, (
                "The 2017 census's count by sex is not tabulated for this ground, and the 2006 "
                "census table's men and women for it do not agree with CAPMAS's own count."))
            return fields
    else:
        if m is None or f is None:
            return fields
        fields["population"] = measure(m + f, year=2006, source=SOURCE_2006)
        fields["population_note"] = (
            f"The 2006 census count of {what} as drawn then: {plural(m, 'man', 'men')} and "
            f"{plural(f, 'woman', 'women')}. "
            + later(parts, m + f, "CAPMAS's later figures"))
        if wrong:
            fields["population_note"] += (f" The table's rows for its villages include {wrong}, "
                                          "which cannot both be right, so this count may be out "
                                          "by thousands.")
        fields["median_age"] = gap(NOT_AVAILABLE, (
            "The 2006 census's tables by kism and markaz give no ages. "
            + later(parts, m + f, "the 2017 census's ages")))
        # Where the two tables of 2006 are compared, both notes quote CAPMAS's
        # later count beside this one ("put 69,616 people ... against 31,148").
        compared = bool(parts) and all(c["p2006"] is not None for c in parts)
        fields["sources"].append({"field": "population/median_age note" if compared
                                  else "population", "name": SOURCE_2006,
                                  "url": hdx_url, "year": 2006, "license": hdx_licence})
        if compared:
            fields["sources"].append({"field": "population note/median_age note",
                                      "name": SOURCE_2006_CP, "url": page_url(parts[0]),
                                      "year": 2006, "license": CP_LICENCE})
    # Men per 1,000 women from 2006, where 2017's cannot be used; a reason
    # given instead quotes the same table's men and women.
    if m is not None and f is not None and wrong:
        fields["sex_ratio"] = gap(NOT_AVAILABLE, (
            f"The 2006 census table's rows for {what} include {wrong}, which cannot both be "
            "right, so no ratio of men to women is given from it."))
        fields["sources"].append({"field": "sex_ratio note", "name": SOURCE_2006,
                                  "url": hdx_url, "year": 2006, "license": hdx_licence})
    elif m is not None and f is not None:
        got = ratio_fields(m, f, 2006, SOURCE_2006, f" in {what} as drawn then")
        fields.update(got)
        fields["sources"].append({"field": cited(got, "sex_ratio"), "name": SOURCE_2006,
                                  "url": hdx_url, "year": 2006, "license": hdx_licence})
    return fields


ZEMAM_NOTE = ("This is land outside the zimam -- the bounds of the governorate's towns and "
              "villages -- which no table of Egypt's census counts as a kism, markaz or police "
              "district, so no count is published for it.")
PORT_NOTE = "Egypt's census tables list this port police district with no population."


def build(cp: dict[str, Any], districts: list[dict[str, Any]],
          provinces: dict[str, dict[str, int]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], pages: dict[str, str], hdx_url: str,
          hdx_licence: str, keyed: list[dict[str, Any]] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    impossible: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for k in keyed or []:
        if k["f"] >= 3 * k["m"]:
            impossible[k["district"]].append(k)
    by_iso = {s.get("iso_3166_2"): s for s in admin1 if s.get("iso_3166_2")}
    by_label = {s["name"]: s for s in admin1}
    gov_shape = {}
    for gov, iso in GOV_ISO.items():
        shape = by_iso.get(iso) or by_label.get(UNCODED.get(iso, ""))
        if shape is None:
            raise SystemExit(f"egypt_census: no outline for governorate {gov} ({iso})")
        gov_shape[gov] = shape
    gov_of_parent = {s["id"]: g for g, s in gov_shape.items()}
    gov_of = {s["id"]: gov_of_parent[s["parent"]] for s in admin2}
    units = units_2006(districts)
    for u in units:
        u["display"] = display(u, cp["units"])
    bound = bind_outlines(admin2, gov_of, units, report)
    plans = compose(bound, cp, provinces, report, units)
    pyramids = {code: parse_pyramid(html) for code, html in pages.items()}
    records = []
    # Record id -> (governorate, the kinds of unit it holds, the outline's
    # label), for each outline written under the name of the units it holds.
    named: dict[str, tuple[str, str, str]] = {}

    def outline(s: dict[str, Any], us: list[dict[str, Any]] | None = None,
                parts: list[dict[str, Any]] = (), **fields: Any) -> dict[str, Any]:
        """The record of outline ``s``, under the name its notes give the 2006
        units it holds -- CAPMAS's names today, as City Population writes
        them: 'DuqqI' is the kism of Ad-Duqqī, 'Paris Paris' the markaz of
        Bārīs -- with its label kept as an alias. A unit renamed since goes by
        today's name (Marina al-Alamein's kism is Al-'Alamayn's). Land outside
        the zimam and the port police districts keep their labels: no table
        names them."""
        rid = f"EGY-CAPMAS-{s['id']}"
        name = s["name"]
        if us:
            names: list[str] = []
            for u in us:
                names += ([clean(c["name"]) for c in parts] if lookup(RENAMED, u) and parts
                          else [u["display"]])
            name = listed(list(dict.fromkeys(names)))
            named[rid] = (gov_of[s["id"]], listed(list(dict.fromkeys(kind_word(u) for u in us))),
                          s["name"])
        return record(rid, name, level="admin2", parent="EGY", country="EGY",
                      match_by="shape_id", shape_id=s["id"],
                      aliases=[s["name"]] if name != s["name"] else None, **fields)

    for s in admin2:
        label = latin(s["name"])
        if label == ZEMAM:
            # The reason is about the census's tables: CAPMAS's units as City
            # Population lists every one, and OCHA's of 2006, name no such unit.
            records.append(outline(
                s, population=gap(NOT_AVAILABLE, ZEMAM_NOTE),
                median_age=gap(NOT_AVAILABLE, ZEMAM_NOTE),
                sex_ratio=gap(NOT_AVAILABLE, ZEMAM_NOTE),
                sources=[{"field": NOTES, "name": SOURCE_2017_COUNT, "url": URL, "year": 2017,
                          "license": CP_LICENCE},
                         {"field": NOTES, "name": SOURCE_2006, "url": hdx_url, "year": 2006,
                          "license": hdx_licence}]))
            continue
        if s["id"] not in bound:
            continue
        us = bound[s["id"]]
        if all(u["key"][0] == "police" and u["t"] is None for u in us):
            # OCHA's table of 2006 lists the district with no count.
            records.append(outline(
                s, population=gap(NOT_AVAILABLE, PORT_NOTE),
                median_age=gap(NOT_AVAILABLE, PORT_NOTE),
                sex_ratio=gap(NOT_AVAILABLE, PORT_NOTE),
                sources=[{"field": NOTES, "name": SOURCE_2006, "url": hdx_url, "year": 2006,
                          "license": hdx_licence}]))
            continue
        plan = plans[s["id"]]
        if all(u["t"] == 0 for u in us) and not any(c["p2017"] for c in plan["parts"]):
            # OCHA's 2006 table carries 0 for the unit (New Tushka) and nothing
            # counts it since: CAPMAS's own 2006 count, where it has one.
            zero = {"field": NOTES, "name": SOURCE_2006, "url": hdx_url, "year": 2006,
                    "license": hdx_licence}
            other = [c for c in plan["parts"] if c["p2006"]]
            if other:
                why = (f"CAPMAS's tables give {describe_parts(other)} a count at the 2006 census "
                       "without its sexes or ages, and no count since; OCHA's table of the 2006 "
                       "census carries 0 for it.")
                records.append(outline(
                    s, us, plan["parts"],
                    codes={"capmas_2006": [c for u in us for c in u["codes"]],
                           "capmas": [c["code"] for c in other]},
                    population=measure(sum(c["p2006"] for c in other), year=2006,
                                       source=SOURCE_2006_CP),
                    population_note=(f"CAPMAS's count of {describe_parts(other)} at the 2006 "
                                     "census; OCHA's table of the 2006 census carries 0 for it, "
                                     "and CAPMAS gives it no count since."),
                    median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
                    sources=[{"field": "population/median_age note/sex_ratio note",
                              "name": SOURCE_2006_CP, "url": page_url(other[0]), "year": 2006,
                              "license": CP_LICENCE}, zero]))
                continue
            none = (f"OCHA's table of the 2006 census carries 0 for {describe(us)}, and CAPMAS "
                    "gives it no count.")
            records.append(outline(s, us, plan["parts"], population=gap(NOT_AVAILABLE, none),
                                   median_age=gap(NOT_AVAILABLE, none),
                                   sex_ratio=gap(NOT_AVAILABLE, none), sources=[zero]))
            continue
        if len(plan["parts"]) == 1 and plan["parts"][0]["p2017"] == 0 and not plan["t2006"]:
            empty = (f"The 2017 census counted no one in {describe(us)}, a city then still "
                     "being built, and CAPMAS gives it no estimate since.")
            records.append(outline(
                s, us, plan["parts"], population=gap(NOT_AVAILABLE, empty),
                median_age=gap(NOT_AVAILABLE, empty), sex_ratio=gap(NOT_AVAILABLE, empty),
                sources=[{"field": NOTES, "name": SOURCE_2017_COUNT,
                          "url": page_url(plan["parts"][0]), "year": 2017,
                          "license": CP_LICENCE}]))
            continue
        if not plan["same"] and plan["t2006"] is None:
            # No 2006 count to test today's units against: a unit named
            # alike, alone, is taken as the same ground (new cities, mostly).
            if len(plan["parts"]) == 1 and all(c["p2017"] for c in plan["parts"]):
                plan = {**plan, "same": True}
                report.append(f"  {s['name']!r}: no 2006 count; bound to "
                              f"{plan['parts'][0]['name']} by name")
        fields = outline_record(s, us, plan, pyramids, hdx_url, hdx_licence,
                                [k for u in us for c in u["codes"] for k in impossible[c]])
        if not fields.get("population"):
            report.append(f"  {s['name']!r}: nothing to write")
            continue
        records.append(outline(s, us, plan["parts"],
                               codes={"capmas_2006": [c for u in us for c in u["codes"]],
                                      "capmas": [c["code"] for c in plan["parts"]]},
                               **fields))
    # A kism and a markaz named for one town are two outlines of one
    # governorate under one name -- the boundary file labels them alike
    # ("Aswan" twice) or apart ("Kesm Tahta", "Tahta") -- and each says which
    # it is: "Ṭahṭā (kism)", "Ṭahṭā (markaz)".
    alike: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r["id"] in named:
            alike[(named[r["id"]][0], r["name"])].append(r)
    for (gov, name), same in sorted(alike.items()):
        kinds = [named[r["id"]][1] for r in same]
        if len(same) < 2:
            continue
        if len(set(kinds)) < len(kinds):
            report.append(f"  {len(same)} outlines of governorate {gov} named {name!r}, "
                          f"{kinds}: left alike")
            continue
        for r, kind in zip(same, kinds):
            r["name"] = f"{name} ({kind})"
            r["aliases"] = [named[r["id"]][2]]
    records += governorates(cp, gov_shape, pyramids, plans, report)
    return records, report


def display(unit: dict[str, Any], cp_units: dict[str, dict[str, Any]]) -> str:
    """A 2006 unit's name as CAPMAS's table today writes it -- its own, or the
    name its numbered parts share (2006's kism of Al-Minyā, today's Al-Minyā 1,
    2 and 3) -- else OCHA's label without a kind word ('Kesm Al-minya')."""
    renamed = lookup(RENAMED, unit)
    if renamed:
        return renamed[1]
    kind, _, base = unit["key"]
    pool = [c for c in cp_units.values() if c["gov"] == unit["gov"]]
    for c in pool:
        if unit["key"] in keys(c["ar"]):
            return clean(c["name"])
    for c in pool:
        if any(k[0] == kind and k[2] == base and k[1] for k in keys(c["ar"])):
            return re.sub(r"\s+\d+(\s*&\s*\d+)*$", "", clean(c["name"]))
    label = sorted(r["en"] for r in unit["rows"])[0]
    return re.sub(r"^(kesm|qism|kism|markaz|markz)\s+", "", label, flags=re.I)


def drawn_elsewhere(cp: dict[str, Any], plans: dict[str, dict[str, Any]]
                    ) -> tuple[dict[str, list], dict[str, list]]:
    """Per governorate: today's units its first-level outline holds that CAPMAS
    counts in another ({gov: [(unit, its gov)]}), and its own units another's
    outline holds ({gov: [(unit, the gov drawn)]})."""
    inn: dict[str, list] = defaultdict(list)
    out: dict[str, list] = defaultdict(list)
    for sid, there in DRAWN_IN.items():
        for c in (plans.get(sid) or {}).get("parts", []):
            if c["gov"] != there and c.get("p2023"):
                inn[there].append((c, c["gov"]))
                out[c["gov"]].append((c, there))
    return inn, out


def drawn_text(gov: str, inn: dict[str, list], out: dict[str, list]) -> tuple[str, int]:
    """What the governorate's outline holds of others' units and lacks of its
    own, and the larger of the two in people (2023)."""
    holds, lacks, held, lacked = [], [], 0, 0
    by_home: dict[str, list] = defaultdict(list)
    for c, home in inn.get(gov, []):
        by_home[home].append(c)
    for home, cs in sorted(by_home.items()):
        held += sum(c["p2023"] for c in cs)
        holds.append(f"{describe_parts(cs)} ({counts(cs)}), which CAPMAS counts in "
                     f"{GOV_EN[home]}")
    by_there: dict[str, list] = defaultdict(list)
    for c, there in out.get(gov, []):
        by_there[there].append(c)
    for there, cs in sorted(by_there.items()):
        lacked += sum(c["p2023"] for c in cs)
        lacks.append(f"{describe_parts(cs)} ({counts(cs)}), whose "
                     f"{'outline lies' if len(cs) == 1 else 'outlines lie'} wholly or mostly "
                     f"within the one drawn for {GOV_EN[there]}")
    said = []
    if holds:
        said.append("holds " + "; and ".join(holds))
    if lacks:
        said.append("leaves out " + "; and ".join(lacks))
    return "; and it ".join(said), max(held, lacked)


def counts(cs: list[dict[str, Any]]) -> str:
    return listed([f"{c['p2023']:,}" for c in cs]) + " people in 2023"


def governorates(cp: dict[str, Any], gov_shape: dict[str, dict[str, Any]],
                 pyramids: dict[str, list], plans: dict[str, dict[str, Any]],
                 report: list[str]) -> list[dict[str, Any]]:
    out = []
    inn, lack = drawn_elsewhere(cp, plans)
    for gov, row in sorted(cp["govs"].items()):
        shape = gov_shape[gov]
        pyr = pyramids.get(gov)
        claimed = [cp["units"][c] for c in CLAIMED if c in cp["units"] and
                   cp["units"][c]["gov"] == gov]
        less = ""
        p2023, p2017 = row["p2023"], row["p2017"]
        if claimed:
            p2023 -= sum(c["p2023"] or 0 for c in claimed)
            p2017 -= sum(c["p2017"] or 0 for c in claimed)
            cpyr = [pyramids.get(c["code"]) for c in claimed]
            if pyr and all(cpyr):
                pyr = add([pyr] + cpyr, [1] + [-1] * len(cpyr))
            else:
                pyr = None
            less = " " + " ".join(
                f"It leaves out the kism of {clean(c['name'])} ({c['p2023']:,} people in "
                "2023), in the triangle north of the 22nd parallel that Egypt and Sudan both "
                "claim." for c in claimed)
        aswan = (" Egypt's count does not include Bir Tawil, the uninhabited land south of the "
                 "22nd parallel that neither Egypt nor Sudan claims." if gov == "28" else "")
        drawn, moved = drawn_text(gov, inn, lack)
        # Each publication is cited for the notes that quote it: the 2017 count
        # the population's note gives, and the 2023 estimate of a kism left
        # out or of the units the outline holds or lacks, which the median's
        # and the ratio's notes give too.
        estimate = {"field": "population", "name": SOURCE_2023, "url": page_url(row),
                    "year": 2023, "license": CP_LICENCE}
        count_2017 = {"field": "population note", "name": SOURCE_2017_COUNT,
                      "url": page_url(row), "year": 2017, "license": CP_LICENCE}
        fields: dict[str, Any] = {
            "population": measure(p2023, year=2023, source=SOURCE_2023),
            "population_note": (f"CAPMAS's estimate for 1 July 2023; the 2017 census counted "
                                f"{p2017:,}.{less}{aswan}"),
            "sources": [estimate, count_2017]}
        if pyr and abs(sum(m + f for _, _, m, f in pyr) - p2017) <= 5:
            fields.update(notes_2017(pyr))
            if less:
                for key in ("sex_ratio_note", "median_age_note"):
                    if key in fields:
                        fields[key] += less
            fields["sources"].append({"field": cited(fields, "median_age", "sex_ratio"),
                                      "name": SOURCE_2017, "url": page_url(row),
                                      "year": 2017, "license": CP_LICENCE})
        else:
            report.append(f"  governorate {row['name']}: no 2017 ages")
        if drawn and moved >= GOV_LARGE * p2023:
            # The outline drawn is other ground than CAPMAS's governorate by a
            # tenth of its people or more: its figures are said, not shown.
            other = (f"but the outline drawn here is not that governorate's ground: it {drawn}. "
                     "The governorate's figures do not describe this outline.")
            refused = {"population": gap(NOT_AVAILABLE, (
                f"CAPMAS's estimate for 1 July 2023 puts {p2023:,} people in {GOV_EN[gov]} "
                f"governorate (the 2017 census counted {p2017:,}), {other}"))}
            refused["population"]["displaces_before"] = DISPLACES_BEFORE
            refused["population"]["displaces_undated"] = True
            if isinstance(fields.get("median_age"), dict) and "value" in fields["median_age"]:
                refused["median_age"] = gap(NOT_AVAILABLE, (
                    f"The 2017 census puts the median age of {GOV_EN[gov]} governorate at "
                    f"{fields['median_age']['value']} years, {other}"))
            if isinstance(fields.get("sex_ratio"), dict) and "value" in fields["sex_ratio"]:
                men, women = sum(p[2] for p in pyr), sum(p[3] for p in pyr)
                refused["sex_ratio"] = gap(NOT_AVAILABLE, (
                    f"The 2017 census counted {men:,} men and {women:,} women in "
                    f"{GOV_EN[gov]} governorate, {fields['sex_ratio']['value']:,} men per "
                    f"1,000 women, {other}"))
            # Every reason quotes the 2023 estimate (the governorate's, or the
            # units' it names), the population's the 2017 count too, the
            # median's and the ratio's the 2017 census by age and sex. Cairo,
            # Qalyubia, Damietta, Qena and Luxor cited none of them.
            said = [k for k in ("population", "median_age", "sex_ratio") if k in refused]
            refused["sources"] = [{**estimate, "field": "/".join(f"{k} note" for k in said)},
                                  count_2017]
            if said[1:]:
                refused["sources"].append({"field": "/".join(f"{k} note" for k in said[1:]),
                                           "name": SOURCE_2017, "url": page_url(row),
                                           "year": 2017, "license": CP_LICENCE})
            report.append(f"  governorate {GOV_EN[gov]}: refused, the outline {drawn}")
            fields = refused
        else:
            if drawn:
                said = (f" The outline drawn here is not quite the governorate's ground: it "
                        f"{drawn}.")
                for key in ("population_note", "median_age_note", "sex_ratio_note"):
                    if key in fields:
                        fields[key] += said
                report.append(f"  governorate {GOV_EN[gov]}: noted, the outline {drawn}")
            if less or drawn:
                estimate["field"] = "/".join(
                    ["population"] + [f"{k} note" for k in ("median_age", "sex_ratio")
                                      if f"{k}_note" in fields])
        # Under the name its notes give it ('Luxor governorate'); the boundary
        # file's label, misspelt for two ('Luxor Governate', 'Minya
        # Governate'), is kept as an alias.
        name = f"{GOV_EN[gov]} Governorate"
        out.append(record(f"EGY-CAPMAS-{gov}", name, level="admin1", parent="EGY",
                          country="EGY", match_by="shape_id", shape_id=shape["id"],
                          aliases=[shape["name"]] if shape["name"] != name else None,
                          codes={"capmas": gov}, **fields))
    return out


# ------------------------------------------------------------------ main

def drawn_units(level: str) -> list[dict[str, Any]]:
    """The map's governorates or kisms and markazes under the boundary file's
    own labels (common.as_drawn): the build names each outline as written
    here, and the binding (UNCODED, the 2006 table's labels) matches the
    labels."""
    return as_drawn(json.loads((SITE / level / "EGY.units.json").read_text()))


def fetch_pages(codes: list[str], hrefs: dict[str, str]) -> dict[str, str]:
    pages = {}
    for n, code in enumerate(codes, 1):
        url = BASE + urllib.parse.quote(hrefs[code])
        try:
            pages[code] = http_get(url, timeout=60)
        except Exception as exc:                    # noqa: BLE001 -- logged, unit skipped
            log(f"  page of {code} not read: {exc}")
            continue
        if n % 50 == 0:
            log(f"  {n} of {len(codes)} pages read")
        time.sleep(PAUSE)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    import openpyxl                                 # noqa: PLC0415
    package = uscb.package(HDX_DATASET)
    found = [r for r in package.get("resources", [])
             if str(r.get("name", "")).lower().endswith(".xlsx") and "2006" in str(r.get("name"))]
    if len(found) != 1:
        raise SystemExit(f"egypt_census: {len(found)} 2006 workbooks on HDX")
    hdx_licence = f"HDX licence: {package.get('license_title') or 'not stated'}"
    blob = http_get(found[0]["url"], binary=True, cache=False, timeout=120)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    districts, provinces = read_hdx(book)
    log(f"  2006: {len(districts)} rows, {len(provinces)} governorates, "
        f"{sum(p['t'] for p in provinces.values()):,} people; licence {hdx_licence!r}")
    keyed: list[dict[str, Any]] = []
    if "Sub-District" in book.sheetnames:
        keyed = keyed_rows([list(r) for r in book["Sub-District"].iter_rows(values_only=True)])
        log(f"  2006 sub-districts with more than twice as many of one sex as the other "
            f"(1,000 people or more): {len(keyed)}")
        for k in keyed:
            log(f"    {k['district']} {k['district_ar']} / {k['sub']} ({k['code']}): "
                f"{k['m']:,} men, {k['f']:,} women, {k['t']:,}")
    html = http_get(URL, cache=False, timeout=120)
    cp = parse_admin(html)
    log(f"  citypopulation: {len(cp['govs'])} governorates, {len(cp['units'])} units")
    if len(cp["govs"]) != 27:
        raise SystemExit("egypt_census: the table does not hold 27 governorates")
    for gov, row in cp["govs"].items():
        made = sum(u["p2017"] or 0 for u in cp["units"].values() if u["gov"] == gov)
        if made != row["p2017"]:
            log(f"  governorate {row['name']}: its units make {made:,} in 2017 against "
                f"{row['p2017']:,}")
    admin1, admin2 = drawn_units("admin1"), drawn_units("admin2")
    # First pass without pages, to know which units' pages are wanted.
    records, report = build(cp, districts, provinces, admin1, admin2, {},
                            uscb.dataset_url(HDX_DATASET), hdx_licence, keyed)
    wanted = sorted({c for r in records if r["level"] == "admin2"
                     and (r.get("population") or {}).get("year") in (2017, 2023)
                     for c in r["codes"]["capmas"]} | set(cp["govs"]) | CLAIMED)
    hrefs = {**{c: u["href"] for c, u in cp["units"].items()},
             **{g: r["href"] for g, r in cp["govs"].items()}}
    pages = fetch_pages([c for c in wanted if hrefs.get(c)], hrefs)
    log(f"  {len(pages)} pages read for the 2017 ages")
    records, report = build(cp, districts, provinces, admin1, admin2, pages,
                            uscb.dataset_url(HDX_DATASET), hdx_licence, keyed)
    for line in report:
        log(line)
    a2 = [r for r in records if r["level"] == "admin2"]
    log(f"  {sum(r['level'] == 'admin1' for r in records)} governorates; {len(a2)} of "
        f"{len(admin2)} outlines: "
        f"{Counter((r.get('population') or {}).get('year') for r in a2)} by year of the count; "
        f"{sum(bool((r.get('median_age') or {}).get('value')) for r in a2)} with a median")
    ratios = sorted((r["sex_ratio"]["value"], r["name"]) for r in records
                    if "value" in (r.get("sex_ratio") or {}))
    log(f"  men per 1,000 women run from {ratios[0]} to {ratios[-1]}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
