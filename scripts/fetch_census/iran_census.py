#!/usr/bin/env python3
"""Iran: the 2016 census by province and shahrestan -- age, sex and citizenship.

**Where the tables are.** The Statistical Centre of Iran published the 2016
(1395) census's detailed tables as Excel workbooks under
``amar.org.ir/Portals/0/census/1395/results/tables/``. Its host ends the TLS
handshake before a standard client reads a byte (the reason this map's
Iranian provinces carried no age or composition), so the workbooks are read
from the Internet Archive's captures of those same files, raw (the ``id_``
modifier), as ``probe_xls --wayback`` reads them. Four families are used,
all from the jamiat (population) tafsili (detailed) series:

* ``ostani/1-jamiat_ostani.xls`` -- Table 1, population by single year of age
  and sex, one sheet per province (31), urban and rural;
* ``shahrestan/jamiatNN.xls`` -- the same Table 1 for every shahrestan, one
  workbook per province (NN, the Centre's province code 00-30) and one sheet
  per shahrestan, named with its four-digit code;
* ``3-jamiat-k.xls`` and ``shahrestan/3/3-jamiat-NN-k.xls`` -- Table 3,
  population by sex and country of citizenship (Iran, Afghanistan, Iraq,
  Pakistan, Turkey, other countries, not stated), by province and by
  shahrestan.

**What is written.** For every province and every shahrestan the map draws:
the census population; the median age, interpolated within the single year
of age that holds the middle person; men per hundred women; and the
citizenship composition as the ethnicity field under ``ethnicity_basis:
"citizenship"``, by the owner's decision of 19 September 2026 (the model is
Japan's and Korea's nationality files). Iran's census asks no ethnicity; it
counts citizenship, and that count is what this is -- a person's country of
citizenship, not their ethnic group. Religion was asked in 2016 too, but no
table of it at any level below the country is among the archived files.

**Binding.** The map's shahrestans are geoBoundaries' and their English
labels follow no one transliteration ("Kahlkhal", "Savdkuh", "Sharekurd").
The Centre's sheets are named in Persian. The bridge is OCHA's Common
Operational Dataset (cod-ab-irn), which names the same 2016 shahrestans in
Persian and in English: a sheet is matched to OCHA's row by its Persian name
inside its province, and OCHA's English name to the drawn polygon inside the
drawn province by a folded comparison, or by ``DRAWN`` where the boundary
file spells it differently. Every pair is one-to-one or the run stops. One
sheet is spelt otherwise by OCHA (``CENSUS_FA``: Khuzestan's Haftgel, "هفتگل"
in the census and "هفتکل" in cod-ab-irn).

**What the map draws differently from 2016, measured on the site's own
tiles.**

* Three 2016 shahrestans are each drawn as two polygons: Tehran ("Tehran"
  and "City of Tehran"), Isfahan ("Isfahan" and "Isfahan County") and
  Mehdishahr ("Mehdishahr" and "Shahmirzad", the county made from it in
  2020s). A 2016 figure describes the union and neither half, so none of the
  six polygons takes one (``SPLIT``); each carries a stated gap saying so.
* Abu Musa, an island county, is not drawn.
* Two polygons carry another county's label: the one labelled "Shahariar"
  in Alborz is Fardis (Fardis town, 35.72 N 50.98 E, lies in it; Shahriar is
  in Tehran province and drawn there), and the one labelled "Paveh" in
  Tehran province is Pardis (Pardis, 35.74 N 51.77 E; Paveh is in
  Kermanshah and drawn there). They are bound by id under the census's name.
* Bandar-e Gaz county (Golestan) is drawn under a first-level polygon of its
  own labelled "Mazandaran" (Bandar-e Gaz town, 36.77 N 53.95 E, lies in it).
  That small polygon takes Bandar-e Gaz's figures, and the drawn Golestan,
  which therefore lacks it, takes Golestan's less Bandar-e Gaz's -- exact,
  because these are counts by single year of age.

**Checks, each a stop.** Every sheet's single years add up to its total, for
both sexes; the five-year subtotals the sheet prints equal the single years
they cover; men and women add up to both sexes; every province's
shahrestans add up to the province; the provinces to the country's
79,926,270; every citizenship row's categories to its total, and that total
to the age table's.

Usage:
    python -m scripts.fetch_census.iran_census
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .redatam import median_age

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import NOT_AVAILABLE, as_drawn, gap, read_json, shard_name  # noqa: E402

ISO3 = "IRN"
YEAR = 2016
OUT = "iran_census.json"
ROOT = Path(__file__).resolve().parent.parent.parent
SITE = ROOT / "site" / "data"
BASE = "https://www.amar.org.ir/Portals/0/census/1395/results/tables/jamiat/tafsili"
WAYBACK = "https://web.archive.org/web/2019id_/{url}"
PROVINCE_AGES = f"{BASE}/ostani/1-jamiat_ostani.xls"
PROVINCE_CITIZENSHIP = f"{BASE}/3-jamiat-k.xls"
COUNTY_AGES = BASE + "/shahrestan/jamiat{nn:02d}.xls"
COUNTY_CITIZENSHIP = BASE + "/shahrestan/3/3-jamiat-{nn:02d}-k.xls"
CODAB = ("https://data.humdata.org/dataset/07f4ec78-42c7-4606-ae62-4f1bff918c45/resource/"
         "6536032d-54c1-43cd-b4a0-0ecb28dc18b6/download/irn_adminboundaries_tabulardata.xlsx")
SOURCE = ("Statistical Centre of Iran, National Population and Housing Census 2016 (1395), "
          "detailed tables (Table 1: population by age and sex; Table 3: population by sex "
          "and citizenship), as the Internet Archive captured them from amar.org.ir")
PAGE = "https://www.amar.org.ir/"
LICENCE = "Official statistics of the Statistical Centre of Iran"
NATIONAL = 79_926_270

# The Centre's province codes, with its Persian names (checked against every
# sheet) and the map's first-level labels.
PROVINCES: dict[int, tuple[str, str]] = {
    0: ("مرکزی", "Markazi"), 1: ("گیلان", "Gilan"), 2: ("مازندران", "Mazandaran"),
    3: ("آذربایجان شرقی", "East Azerbaijan"), 4: ("آذربایجان غربی", "West Azerbaijan"),
    5: ("کرمانشاه", "Kermanshah"), 6: ("خوزستان", "Khuzestan"), 7: ("فارس", "Fars"),
    8: ("کرمان", "Kerman"), 9: ("خراسان رضوی", "Razavi Khorasan"), 10: ("اصفهان", "Isfahan"),
    11: ("سیستان و بلوچستان", "Sistan and Baluchestan"), 12: ("کردستان", "Kurdistan"),
    13: ("همدان", "Hamadan"), 14: ("چهارمحال و بختیاری", "Chaharmahal and Bakhtiari"),
    15: ("لرستان", "Lorestan"), 16: ("ایلام", "Ilam"),
    17: ("کهگیلویه و بویراحمد", "Kohgiluyeh and Boyer-Ahmad"), 18: ("بوشهر", "Bushehr"),
    19: ("زنجان", "Zanjan"), 20: ("سمنان", "Semnan"), 21: ("یزد", "Yazd"),
    22: ("هرمزگان", "Hormozgan"), 23: ("تهران", "Tehran"), 24: ("اردبیل", "Ardabil"),
    25: ("قم", "Qom"), 26: ("قزوین", "Qazvin"), 27: ("گلستان", "Golestan"),
    28: ("خراسان شمالی", "North Khorasan"), 29: ("خراسان جنوبی", "South Khorasan"),
    30: ("البرز", "Alborz"),
}
# OCHA's first-level name for a shahrestan where it is not the province's:
# cod-ab-irn files Some'e Sara under a first level of its own, "Somee-Sara".
CODAB_PROVINCE = {"Somee-Sara": "Gilan"}

# OCHA's English name -> the boundary file's label, inside the same province.
DRAWN: dict[str, str] = {
    "Ardabil": "Ardebil", "Bilasavar": "Bilehsavar", "Germi": "Garmi", "Khalkhal": "Kahlkhal",
    "Kowsar": "Kosar", "Meshginshahr": "Meshkinshahr", "Dayyer": "Deyr", "Ganaveh": "Genaveh",
    "Kiaar": "Kiar", "Shahrekord": "Sharekurd", "Kalibar": "Kaleybar",
    "Kherameh": "Kharameh", "Khorrambid": "Khorambid", "Qir-o-Karzin": "Qir and Karzin",
    "Zarrindasht": "Zarindasht", "Astane-ye-Ashrafiyeh": "Astan-e-Ashrafieh",
    "Langrud": "Langerud", "Some'e-Sara": "Sowme'eh Sara", "Kolaleh": "Kalaleh",
    "Bandar-e-Torkaman": "Turkman", "Hamadan": "Hamedan", "Kabudarahang": "Kabutarahang",
    "Bandar-Abbas": "Bandar-e-Abbas", "Bandar-Lengeh": "Bandar-e-Lengeh",
    "Abdanan": "Abdanan County", "Badre": "Badreh", "Shirvan-o-Chardavol": "Chardavol",
    "Darreh Shahr": "Darreh Shahr County", "Dehloran": "Dehloran County",
    "Eyvan": "Eyvan County", "Mehran": "Mehran County", "Aran-o-Bidgol": "Aran and Bidgol",
    "Booeino Miyandasht": "Buin and Miandasht", "Borkhar": "Barkhar", "Dehaghan": "Dehaqan",
    "Falavarjan": "Falaverjan", "Faridan": "Fereydan", "Khorobiyabanak": "Khur and Biabanak",
    "Shahinshahro Meymeh": "Shahin Shahr and Meymeh", "Shahreza": "Sahreza",
    "Tiran-o-Korun": "Tiran and Karvan", "Ghaleye-Ganj": "Ghalehganj",
    "Kuhbonan": "Kuhbanan", "Normashir": "Narmashir", "Rabar": "Rabor",
    "Roudbar-e-Jonub": "Rudbar-e-Jonub", "Dalaho": "Dalahu",
    "Islamabad-e-Gharb": "Eslamabad-e Gharb", "Solas-e-Babajani": "Salas-e Babajani",
    "Guotvand": "Gotvand", "Hoveizeh": "Hoveyzeh", "Karoun": "Karun",
    "Khorramshahr": "Khoramshahr", "Mahshahr": "Bandar-e-Mahshahr", "Omidiyeh": "Omidieh",
    "Kohgeluyeh": "Kohkiluyeh", "Yasooj": "Buyerahmad", "Divandarreh": "Divandareh",
    "Qorveh": "Ghorveh", "Sannandaj": "Sanandaj", "Doureh": "Doreh",
    "Khorramabad": "Khoramabad", "Poldokhtar": "Pol-e-Dokhtar", "Romeshkan": "Rumeshkhan",
    "Komeijan": "Komijan", "Feredunkenar": "Fereydunkenar", "Qaemshahr": "Ghaemshahr",
    "Northern Savadkooh": "Savadkuh-e-Shomali", "Savadkuh": "Savdkuh",
    "Esfarayen": "Esfarayen County", "Faroj": "Faruj", "Germeh": "Garmeh",
    "Maneh-o-Samalqan": "Maneh and Samalqan", "Razo Jalgelan": "Raz and Jargalan",
    "Shirvan": "Shirwan", "Nishapur": "Neyshabur", "Rashtkhar": "Roshtkhar",
    "Torghabe-o-Shandiz": "Binalud", "Zave": "Zaveh", "Meyami": "Miami",
    "Dalgan": "Dalagan", "Fanouj": "Fanuj", "Ghasre Ghand": "Qasr-e-Ghand",
    "Hamoun": "Hamun", "Nimrouz": "Nimruz", "Sibo Soran": "Sib and Suran", "Zehak": "Zahak",
    "Qaen": "Ghaenat", "Zirkouh": "Zirkuh", "Qarchak": "Gharchak", "Shahr-e Qods": "Qods",
    "Oshnaviyeh": "Ashnavieh", "Chaldoran": "Chaldoran County", "Naqadeh": "Naghadeh",
    "Shahindej": "Shahindezh", "Eejrud": "Ijrud", "Khorramdarreh": "Khoramdareh",
    # The boundary file's label is another county's; the town is in the polygon.
    "Fardis": "Shahariar", "Pardis": "Paveh",
}
# Labels the boundary file puts on another county's polygon: the record is
# named by the census and the label kept as an alias.
MISLABELLED = {"Fardis": "Shahariar", "Pardis": "Paveh"}
# 2016 shahrestans the map draws as two polygons: neither half takes a figure.
SPLIT: dict[str, tuple[str, str]] = {
    "Tehran": ("Tehran", "City of Tehran"), "Isfahan": ("Isfahan", "Isfahan County"),
    "Mehdishahr": ("Mehdishahr", "Shahmirzad"),
}
# Each split county's drawn province, and what its two halves are (measured
# on the site's tiles: Azadi Square, Tajrish and the Bazaar fall in "City of
# Tehran", Soleqan in "Tehran"; Naqsh-e Jahan Square in "Isfahan", Ziar and
# Varzaneh in "Isfahan County"; Shahmirzad town in "Shahmirzad").
SPLIT_PROVINCE = {"Tehran": "Tehran", "Isfahan": "Isfahan", "Mehdishahr": "Semnan"}
SPLIT_WHAT = {
    "Tehran": "the city of Tehran and the rest of the county around it",
    "Isfahan": "the city of Isfahan and the rest of the county around it",
    "Mehdishahr": "Mehdishahr and Shahmirzad, the county made from its Shahmirzad district "
                  "after the census",
}
# Drawn nowhere: an island county.
NOT_DRAWN = {"Abumusa"}
# A shahrestan drawn under another first-level polygon than its province's:
# OCHA's English name -> the drawn province label, and which drawn polygon of
# that label (the one holding exactly this child).
ELSEWHERE = {"Bandar-e-Gaz": "Mazandaran"}
# A sheet whose Persian name OCHA spells otherwise, inside the same province:
# the Centre's sheet name -> OCHA's. Khuzestan's 0622 is "هفتگل" (Haftgel) in
# the census and "شهرستان هفتکل" (Haftkel, IR015013, English "Haftgol") in
# cod-ab-irn -- the two usual spellings of the one county, and the only sheet
# and the only OCHA row of Khuzestan's 27 left over when the others are paired.
CENSUS_FA = {"هفتگل": "هفتکل"}

LABELS = {"ایران": "Iranian", "افغانستان": "Afghan", "عراق": "Iraqi", "پاکستان": "Pakistani",
          "ترکیه": "Turkish", "سایر کشورها": "Other nationalities",
          "اظهار نشده": "Not stated"}

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def fa(text: Any) -> str:
    """Persian text with the Arabic letter forms, digits and spacing folded."""
    s = str(text or "").translate(PERSIAN_DIGITS)
    s = (s.replace("ي", "ی").replace("ى", "ی").replace("ئ", "ی").replace("ك", "ک")
         .replace("ة", "ه").replace("ؤ", "و")
         .replace("‌", "").replace("‏", "").replace("‎", "")
         .replace("أ", "ا").replace("إ", "ا").replace("آ", "ا"))
    return re.sub(r"\s+", "", s.replace("شهرستان", ""))


def fold(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name or "").lower())
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def number(cell: Any) -> int:
    text = str(cell if cell is not None else "").translate(PERSIAN_DIGITS).replace(",", "").strip()
    if text in ("", "-", "–", "*"):
        return 0
    return int(round(float(text)))


# --------------------------------------------------------------------------
# Table 1: population by single year of age and sex.

AGE_SINGLE = re.compile(r"^(\d+)ساله$")
AGE_GROUP = re.compile(r"^(\d+)-(\d+)ساله$")
AGE_OPEN = re.compile(r"^(\d+)ساله.*(?:بیشتر|بالا|بالاتر)$")


def age_of(label: Any) -> tuple[str, Any]:
    """('single', age) / ('group', (lo, hi)) / ('open', age) / ('total', None) / ('unstated', None)."""
    s = fa(label)
    if s in ("تمامیسنین", "جمع", "کل"):
        return "total", None
    if s == "کمترازیکساله":
        return "single", 0
    if s in ("اظهارنشده", "نامشخص"):
        return "unstated", None
    if m := AGE_OPEN.match(s):
        return "open", int(m.group(1))
    if m := AGE_SINGLE.match(s):
        return "single", int(m.group(1))
    if m := AGE_GROUP.match(s):
        return "group", (int(m.group(1)), int(m.group(2)))
    return "", None


def parse_ages(rows: list[list[Any]], label: str) -> dict[str, Any]:
    """One Table 1 sheet: {"total": (both, men, women), "men": Counter, "women": Counter}.

    The columns are found by the header row that reads both sexes, men,
    women ("مردوزن", "مرد", "زن") under the "all" heading; the first such
    triple is the whole population, before urban and rural.
    """
    head = None
    for i, row in enumerate(rows[:8]):
        cells = [fa(c) for c in row]
        for j in range(len(cells) - 2):
            if cells[j] in ("مردوزن", "مردوزن") and cells[j + 1] == "مرد" and cells[j + 2] == "زن":
                head = (i, j)
                break
        if head:
            break
    if head is None:
        raise SystemExit(f"iran_census: {label}: no both/men/women header row")
    both_col = head[1]
    label_col = None
    out = {"men": Counter(), "women": Counter(), "groups": {}, "unstated": [0, 0, 0]}
    total = None
    for row in rows[head[0] + 1:]:
        if label_col is None:
            for j in range(both_col):
                if age_of(row[j])[0] == "total":
                    label_col = j
                    break
            if label_col is None:
                continue
        kind, age = age_of(row[label_col])
        if not kind:
            continue
        both, men, women = (number(row[both_col + k]) for k in range(3))
        if men + women != both:
            raise SystemExit(f"iran_census: {label}, {row[label_col]!r}: men {men:,} and "
                             f"women {women:,} do not make {both:,}")
        if kind == "total":
            if total is None:
                total = (both, men, women)
        elif kind in ("single", "open"):
            if age in out["men"] or age in out["women"]:
                raise SystemExit(f"iran_census: {label}: age {age} twice")
            out["men"][age] += men
            out["women"][age] += women
            if kind == "open":
                out["open"] = age
        elif kind == "group":
            out["groups"][age] = (both, men, women)
        elif kind == "unstated":
            out["unstated"] = [both, men, women]
    if total is None:
        raise SystemExit(f"iran_census: {label}: no all-ages row")
    out["total"] = total
    check_ages(out, label)
    return out


def check_ages(table: dict[str, Any], label: str) -> None:
    both, men, women = table["total"]
    s_men = sum(table["men"].values()) + table["unstated"][1]
    s_women = sum(table["women"].values()) + table["unstated"][2]
    if (s_men, s_women) != (men, women):
        raise SystemExit(f"iran_census: {label}: single years make {s_men:,} men and "
                         f"{s_women:,} women against {men:,} and {women:,}")
    for (lo, hi), (g_both, g_men, g_women) in table["groups"].items():
        m = sum(n for a, n in table["men"].items() if lo <= a <= hi)
        w = sum(n for a, n in table["women"].items() if lo <= a <= hi)
        if (m, w) != (g_men, g_women):
            raise SystemExit(f"iran_census: {label}: ages {lo}-{hi} make {m:,} men and "
                             f"{w:,} women against the sheet's {g_men:,} and {g_women:,}")


def add_ages(tables: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"men": Counter(), "women": Counter(), "groups": {}, "unstated": [0, 0, 0],
           "total": (0, 0, 0)}
    for t in tables:
        out["men"].update(t["men"])
        out["women"].update(t["women"])
        out["unstated"] = [a + b for a, b in zip(out["unstated"], t["unstated"])]
        out["total"] = tuple(a + b for a, b in zip(out["total"], t["total"]))
    return out


def less(table: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    out = {"men": Counter(table["men"]), "women": Counter(table["women"]), "groups": {},
           "unstated": [a - b for a, b in zip(table["unstated"], part["unstated"])],
           "total": tuple(a - b for a, b in zip(table["total"], part["total"]))}
    out["men"].subtract(part["men"])
    out["women"].subtract(part["women"])
    if any(v < 0 for c in (out["men"], out["women"]) for v in c.values()):
        raise SystemExit("iran_census: a part has more people at some age than its whole")
    return out


# --------------------------------------------------------------------------
# Table 3: population by sex and citizenship.

def citizenship_columns(rows: list[list[Any]]) -> tuple[int, dict[int, str], int]:
    """(header row index, {column: label}, total column)."""
    for i, row in enumerate(rows[:6]):
        cells = [fa(c) for c in row]
        if fa("ایران") in cells and fa("افغانستان") in cells:
            columns = {}
            total = None
            for j, c in enumerate(cells):
                for persian, english in LABELS.items():
                    if c == fa(persian):
                        columns[j] = english
                if c == fa("جمع"):
                    total = j
            if total is None or len(columns) != len(LABELS):
                raise SystemExit(f"iran_census: citizenship header {row!r} lacks a column")
            return i, columns, total
    raise SystemExit("iran_census: no citizenship header row")


def parse_citizenship_block(rows: list[list[Any]], label: str) -> dict[str, Any]:
    """{name: (total, {label: count})} for the both-sexes block of a Table 3 sheet."""
    head, columns, total_col = citizenship_columns(rows)
    out: dict[str, Any] = {}
    in_block = False
    for row in rows[head + 1:]:
        name = fa(row[0]) if row else ""
        if name in ("مردوزن",):
            in_block = True
            out["*"] = read_citizenship(row, columns, total_col, label)
            continue
        if name in ("مرد", "زن"):
            if in_block:
                break
            continue
        if in_block and name:
            out[name] = read_citizenship(row, columns, total_col, f"{label} {row[0]}")
    if "*" not in out:
        raise SystemExit(f"iran_census: {label}: no both-sexes row")
    return out


def read_citizenship(row: list[Any], columns: dict[int, str], total_col: int,
                     label: str) -> tuple[int, dict[str, int]]:
    counts = {english: number(row[j]) for j, english in columns.items()}
    total = number(row[total_col])
    if sum(counts.values()) != total:
        raise SystemExit(f"iran_census: {label}: citizenships make {sum(counts.values()):,} "
                         f"against the total {total:,}")
    return total, counts


# --------------------------------------------------------------------------
# Reading the workbooks.

PAUSE = 10.0                          # seconds between two Wayback requests
COOLDOWNS = (120, 240, 300, 300)      # waits after the Archive refuses us
_last_request = [0.0]


def fetch(url: str) -> bytes:
    """One workbook from the Wayback Machine, spaced out and waited out.

    The Archive refuses connections for a minute or more when one address asks
    too often, and each capture costs two requests (the redirect to the exact
    timestamp, then the file). The first run was refused after six or seven
    workbooks in a row, so requests are spaced PAUSE seconds apart and a refusal
    is waited out for minutes rather than retried at once.
    """
    target = WAYBACK.format(url=url)
    blob: bytes | str = b""
    for cooldown in (*COOLDOWNS, None):
        wait = PAUSE - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        try:
            blob = http_get(target, binary=True, timeout=180, retries=1)
            break
        except RuntimeError as err:
            if cooldown is None:
                raise
            log(f"  the Archive refused {url.rsplit('/', 1)[-1]} ({err.__cause__}); "
                f"waiting {cooldown}s")
            time.sleep(cooldown)
        finally:
            _last_request[0] = time.monotonic()
    assert isinstance(blob, bytes)
    if blob[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise SystemExit(f"iran_census: {url} came back as something other than a "
                         f"workbook: {blob[:80]!r}")
    return blob


def sheets(blob: bytes) -> list[tuple[str, list[list[Any]]]]:
    import xlrd
    book = xlrd.open_workbook(file_contents=blob)
    return [(s.name, [s.row_values(i) for i in range(s.nrows)]) for s in book.sheets()]


SHEET_CODE = re.compile(r"^(.*?)(\d{2,4})$")


def split_sheet_name(name: str) -> tuple[str, str]:
    """('اراک', '0001') from 'اراک0001'."""
    s = name.strip().translate(PERSIAN_DIGITS)
    m = SHEET_CODE.match(s)
    if not m:
        raise SystemExit(f"iran_census: sheet {name!r} carries no code")
    return m.group(1).strip(), m.group(2)


# --------------------------------------------------------------------------
# Binding.

def load_codab(blob: bytes) -> dict[str, list[dict[str, str]]]:
    """OCHA's shahrestans by English province name: [{en, fa, pcode}]."""
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = book["ADM2"].iter_rows(values_only=True)
    header = [str(c or "").strip() for c in next(rows)]
    col = {h: i for i, h in enumerate(header)}
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if not row or not row[col["ADM2_EN"]]:
            continue
        en = str(row[col["ADM2_EN"]]).replace("_x000D_", "").strip()
        province = str(row[col["ADM1_EN"]]).strip()
        out[CODAB_PROVINCE.get(province, province)].append(
            {"en": en, "fa": str(row[col["ADM2_FA"]]), "pcode": str(row[col["ADM2_PCODE"]])})
    return out


def ocha_fa(name: str) -> str:
    """A census sheet's Persian name, folded, as OCHA spells it (CENSUS_FA)."""
    folded = fa(name)
    for census, ocha in CENSUS_FA.items():
        if folded == fa(census):
            return fa(ocha)
    return folded


def drawn_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    a1 = as_drawn(read_json(SITE / "admin1" / shard_name(ISO3), []))
    a2 = as_drawn(read_json(SITE / "admin2" / shard_name(ISO3), []))
    return a1, a2


def bind_counties(counties: list[dict[str, Any]], codab: dict[str, list[dict[str, str]]],
                  a1: list[dict[str, Any]], a2: list[dict[str, Any]]
                  ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Centre code -> drawn polygon, through OCHA's Persian and English names.

    Returns ({code: shape}, notes). A county in SPLIT or NOT_DRAWN is left
    out with a note; anything else unmatched stops the run.
    """
    name1 = {u["id"]: u["name"] for u in a1}
    by_province: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in a2:
        by_province[name1.get(u.get("parent"), "")].append(u)
    bound: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    used: set[str] = set()
    problems: list[str] = []
    for county in counties:
        province = PROVINCES[county["province"]][1]
        wanted = ocha_fa(county["name"])
        rows = [r for r in codab.get(province, []) if fa(r["fa"]) == wanted]
        if len(rows) != 1:
            # Excel cuts a sheet name at 31 characters; the code takes four.
            rows = [r for r in codab.get(province, [])
                    if fa(r["fa"]).startswith(wanted) and len(wanted) >= 4]
        if len(rows) != 1:
            unclaimed = [f"{r['en']}={r['fa']}" for r in codab.get(province, [])
                         if not any(fa(r["fa"]) == ocha_fa(c["name"]) for c in counties
                                    if c["province"] == county["province"])]
            problems.append(f"{province} {county['name']} ({county['code']}) matches "
                            f"{len(rows)} of OCHA's shahrestans; OCHA's unmatched there: "
                            f"{', '.join(unclaimed)}")
            continue
        en = rows[0]["en"]
        county["en"] = en
        if en in NOT_DRAWN:
            notes.append(f"{en} ({county['code']}): not drawn; left out")
            continue
        if en in SPLIT:
            notes.append(f"{en} ({county['code']}): drawn as {SPLIT[en][0]!r} and "
                         f"{SPLIT[en][1]!r}; neither takes the 2016 figure")
            continue
        drawn_province = ELSEWHERE.get(en, province)
        label = DRAWN.get(en, en)
        pool = by_province.get(drawn_province, [])
        hits = [u for u in pool if fold(u["name"]) == fold(label)]
        if en in ELSEWHERE:
            hits = [u for u in hits
                    if sum(1 for v in a2 if v.get("parent") == u.get("parent")) == 1]
        if len(hits) != 1 or hits[0]["id"] in used:
            problems.append(f"{province} {en} ({county['code']}) finds {len(hits)} drawn "
                            f"polygons labelled {label!r}")
            continue
        used.add(hits[0]["id"])
        bound[county["code"]] = hits[0]
    if problems:
        for line in problems:
            log(f"  unbound: {line}")
        raise SystemExit(f"iran_census: {len(problems)} shahrestans not bound (listed above)")
    return bound, notes


# --------------------------------------------------------------------------
# Records.

def fields(table: dict[str, Any], citizenship: tuple[int, dict[str, int]] | None,
           note_extra: str = "") -> dict[str, Any]:
    both, men, women = table["total"]
    ages = Counter({a: table["men"][a] + table["women"][a]
                    for a in set(table["men"]) | set(table["women"])})
    median = median_age(ages)
    out: dict[str, Any] = {
        "population": measure(both, year=YEAR, source=SOURCE),
        "median_age": measure(median, unit="years", year=YEAR, source=SOURCE),
        "median_age_note": ("Interpolated within the single year of age that holds the middle "
                            "person, from Table 1 of the 2016 census (population by single year "
                            "of age and sex)."
                            + (f" {table['unstated'][0]:,} people of unstated age are left "
                               f"out." if table["unstated"][0] else "") + note_extra),
        "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                             year=YEAR, source=SOURCE),
        "sex_ratio_note": f"{men:,} men and {women:,} women, 2016 census." + note_extra,
        "sources": [{"field": "population/median_age/sex_ratio", "name": SOURCE,
                     "url": PAGE, "year": YEAR, "license": LICENCE}],
    }
    if citizenship is not None:
        total, counts = citizenship
        if total != both:
            raise SystemExit(f"iran_census: citizenship total {total:,} against the age "
                             f"table's {both:,}")
        out["ethnicity"] = shares({k: v for k, v in counts.items() if v}, total=total)
        out["ethnicity_year"] = YEAR
        out["ethnicity_basis"] = "citizenship"
        out["ethnicity_note"] = (
            "Country of citizenship, from Table 3 of the 2016 census (population by sex and "
            "citizenship): Iranian citizens and the citizens of each other country the Centre "
            "tabulates. Iran's census does not ask ethnicity; by the owner's decision of 19 "
            "September 2026 the citizenship it counts is shown in its place, as Japan's and "
            "Korea's nationality is. It is citizenship, not ethnic group."
            + note_extra)
        out["sources"].append({"field": "ethnicity", "name": SOURCE, "url": PAGE,
                               "year": YEAR, "license": LICENCE})
    return out


def build(province_ages: dict[int, dict[str, Any]],
          province_citizenship: dict[str, tuple[int, dict[str, int]]],
          counties: list[dict[str, Any]], codab: dict[str, list[dict[str, str]]],
          a1: list[dict[str, Any]], a2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    # The provinces add up to the country, and each province's shahrestans to it.
    national = sum(t["total"][0] for t in province_ages.values())
    if national != NATIONAL:
        raise SystemExit(f"iran_census: the provinces make {national:,} against {NATIONAL:,}")
    for nn, table in province_ages.items():
        parts = [c["ages"] for c in counties if c["province"] == nn]
        summed = add_ages(parts)
        if summed["total"] != table["total"]:
            raise SystemExit(f"iran_census: {PROVINCES[nn][1]}'s shahrestans make "
                             f"{summed['total']} against the province's {table['total']}")
    bound, notes = bind_counties(counties, codab, a1, a2)
    rows: list[dict[str, Any]] = []
    for county in counties:
        shape = bound.get(county["code"])
        if shape is None:
            continue
        en = county["en"]
        name = en if en in MISLABELLED else shape["name"]
        extra = (f" The boundary file labels this polygon {MISLABELLED[en]!r}; "
                 f"it is {en} ({county['name']}), whose town lies in it."
                 if en in MISLABELLED else "")
        rows.append(record(
            f"IRN-CENSUS-{county['code']}", name, level="admin2", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=shape["id"],
            aliases=[county["name"], en] + ([shape["name"]] if en in MISLABELLED else []),
            codes={"sci": county["code"]},
            **fields(county["ages"], county["citizenship"], extra)))
    # The first level: every province whole, except where the map draws
    # Bandar-e Gaz under a first-level polygon of its own.
    gaz = next((c for c in counties if c.get("en") == "Bandar-e-Gaz"), None)
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in a1:
        by_label[u["name"]].append(u)
    children = Counter(u.get("parent") for u in a2)
    for nn, (persian, english) in PROVINCES.items():
        polygons = sorted(by_label.get(english, []), key=lambda u: -children[u["id"]])
        if not polygons:
            raise SystemExit(f"iran_census: the map draws no {english}")
        table = province_ages[nn]
        citizen = province_citizenship.get(fa(persian))
        if citizen is None:
            raise SystemExit(f"iran_census: Table 3 has no row for {persian}")
        extra = ""
        if english == "Golestan" and gaz is not None:
            table = less(table, gaz["ages"])
            total, counts = citizen
            g_total, g_counts = gaz["citizenship"]
            citizen = (total - g_total, {k: counts[k] - g_counts[k] for k in counts})
            extra = (" The map draws Bandar-e Gaz county under a first-level polygon of its "
                     "own, so this is Golestan less Bandar-e Gaz, from the same tables.")
        rows.append(record(
            f"IRN-CENSUS-P{nn:02d}", english, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=polygons[0]["id"], aliases=[persian],
            codes={"sci": f"{nn:02d}"}, **fields(table, citizen, extra)))
        if english == "Mazandaran" and len(polygons) > 1 and gaz is not None:
            small = polygons[-1]
            if children[small["id"]] != 1:
                raise SystemExit("iran_census: the second Mazandaran polygon does not hold "
                                 "exactly one shahrestan")
            rows.append(record(
                f"IRN-CENSUS-P{nn:02d}-GAZ", "Mazandaran", level="admin1", parent=ISO3,
                country=ISO3, match_by="shape_id", shape_id=small["id"],
                aliases=["Bandar-e Gaz"], codes={"sci": gaz["code"]},
                **fields(gaz["ages"], gaz["citizenship"],
                         " This first-level polygon holds Bandar-e Gaz county alone (a county "
                         "of Golestan province), so it carries Bandar-e Gaz's figures.")))
    return rows, notes


def split_records(a1: list[dict[str, Any]], a2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A stated gap on both halves of every 2016 shahrestan the map draws as two.

    The census counts the shahrestan whole; a figure for the whole describes
    neither half, and nothing it publishes divides it along the drawn line, so
    each polygon says so rather than sitting blank.
    """
    name1 = {u["id"]: u["name"] for u in a1}
    rows = []
    for en, halves in SPLIT.items():
        province = SPLIT_PROVINCE[en]
        for label in halves:
            hits = [u for u in a2 if u["name"] == label and name1.get(u.get("parent")) == province]
            if len(hits) != 1:
                raise SystemExit(f"iran_census: {len(hits)} drawn polygons labelled {label!r} "
                                 f"in {province}")
            note = (f"The 2016 census counts {en} shahrestan as one unit; the map draws it as "
                    f"two polygons, {halves[0]!r} and {halves[1]!r} -- {SPLIT_WHAT[en]}. A "
                    f"figure for the whole county describes neither polygon, and the census "
                    f"publishes none along that line, so none is written here.")
            missing = gap(NOT_AVAILABLE, note)
            rows.append(record(
                f"IRN-CENSUS-SPLIT-{fold(label)}", label, level="admin2", parent=ISO3,
                country=ISO3, match_by="shape_id", shape_id=hits[0]["id"],
                population=dict(missing), median_age=dict(missing), sex_ratio=dict(missing),
                ethnicity=dict(missing)))
    return rows


# What has been read is kept, as the tables' counts, under data/raw/iran (which
# the repository tracks): the Archive refuses a run that asks for all 64
# workbooks at once often enough that a run reads what it can within BUDGET,
# keeps it, and stops; the next run starts where it stopped. The kept files
# are the parsed tables -- counts by single year of age and sex, and by
# citizenship -- not the workbooks.
CACHE = PROCESSED.parent / "raw" / "iran"
BUDGET = 30 * 60


def table_json(table: dict[str, Any]) -> dict[str, Any]:
    return {"men": {str(a): n for a, n in sorted(table["men"].items())},
            "women": {str(a): n for a, n in sorted(table["women"].items())},
            "groups": [[lo, hi, *v] for (lo, hi), v in sorted(table["groups"].items())],
            "unstated": list(table["unstated"]), "total": list(table["total"]),
            **({"open": table["open"]} if "open" in table else {})}


def table_from(data: dict[str, Any]) -> dict[str, Any]:
    out = {"men": Counter({int(a): n for a, n in data["men"].items()}),
           "women": Counter({int(a): n for a, n in data["women"].items()}),
           "groups": {(g[0], g[1]): tuple(g[2:]) for g in data["groups"]},
           "unstated": list(data["unstated"]), "total": tuple(data["total"])}
    if "open" in data:
        out["open"] = data["open"]
    return out


def cached(name: str) -> Any:
    path = CACHE / f"census2016_{name}.json"
    return read_json(path, None) if path.exists() else None


def keep(name: str, payload: Any) -> None:
    write_json(CACHE / f"census2016_{name}.json", payload)


def read_provinces() -> tuple[dict[int, Any], dict[str, Any]]:
    kept = cached("provinces")
    if kept is None:
        province_ages: dict[int, dict[str, Any]] = {}
        for name, rows in sheets(fetch(PROVINCE_AGES)):
            persian, code = split_sheet_name(name)
            nn = int(code)
            if fa(persian) != fa(PROVINCES[nn][0]):
                raise SystemExit(f"iran_census: province sheet {name!r} is not "
                                 f"{PROVINCES[nn][0]}")
            province_ages[nn] = parse_ages(rows, name)
        if sorted(province_ages) != sorted(PROVINCES):
            raise SystemExit(f"iran_census: province sheets {sorted(province_ages)}")
        (_, rows), = sheets(fetch(PROVINCE_CITIZENSHIP))
        block = parse_citizenship_block(rows, "3-jamiat-k")
        kept = {"ages": {str(nn): table_json(t) for nn, t in province_ages.items()},
                "citizenship": {k: [v[0], v[1]] for k, v in block.items()}}
        keep("provinces", kept)
    ages = {int(nn): table_from(t) for nn, t in kept["ages"].items()}
    citizenship = {k: (v[0], v[1]) for k, v in kept["citizenship"].items()}
    for nn, table in ages.items():
        check_ages(table, f"province {nn:02d}")
    return ages, citizenship


def read_province(nn: int) -> list[dict[str, Any]]:
    """One province's shahrestans: [{province, code, name, ages, citizenship}]."""
    # Keyed by the sheet's code: the two workbooks may cut a long name at
    # different lengths, never the code.
    ages = {split_sheet_name(n)[1]: (split_sheet_name(n)[0], r)
            for n, r in sheets(fetch(COUNTY_AGES.format(nn=nn)))}
    cit = {split_sheet_name(n)[1]: r
           for n, r in sheets(fetch(COUNTY_CITIZENSHIP.format(nn=nn)))}
    if set(ages) != set(cit):
        raise SystemExit(f"iran_census: province {nn:02d}'s two tables carry different "
                         f"codes: {sorted(set(ages) ^ set(cit))}")
    counties = []
    for code, (persian, rows) in sorted(ages.items()):
        full = f"{nn:02d}{code[-2:]}"
        if len(code) == 4 and int(code[:2]) != nn:
            raise SystemExit(f"iran_census: sheet {persian}{code} is filed under "
                             f"province {nn:02d}")
        block = parse_citizenship_block(cit[code], f"3-jamiat-{nn:02d} {persian}")
        counties.append({"province": nn, "code": full, "name": persian,
                         "ages": parse_ages(rows, f"jamiat{nn:02d} {persian}"),
                         "citizenship": block["*"]})
    return counties


def read_all(budget: float = BUDGET, only: set[int] | None = None
             ) -> tuple[dict[int, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Every province's shahrestans, from data/raw/iran or the Archive.

    ``only`` limits the fetching to those provinces (the rest are read from
    data/raw/iran or left for another run), so that several runs on several
    machines can share the work the Archive rations.
    """
    started = time.monotonic()
    province_ages, province_citizenship = read_provinces()
    counties: list[dict[str, Any]] = []
    waiting = []
    for nn in sorted(PROVINCES):
        kept = cached(f"{nn:02d}")
        if kept is None:
            if time.monotonic() - started > budget or (only is not None and nn not in only):
                waiting.append(nn)
                continue
            fresh = read_province(nn)
            kept = [{**c, "ages": table_json(c["ages"]),
                     "citizenship": [c["citizenship"][0], c["citizenship"][1]]} for c in fresh]
            keep(f"{nn:02d}", kept)
        mine = [{**c, "ages": table_from(c["ages"]),
                 "citizenship": (c["citizenship"][0], c["citizenship"][1])} for c in kept]
        for c in mine:
            check_ages(c["ages"], f"{c['code']} {c['name']}")
        counties += mine
        log(f"  province {nn:02d} {PROVINCES[nn][1]}: {len(mine)} shahrestans")
    if waiting:
        raise SystemExit(f"iran_census: {len(waiting)} provinces not yet read ({waiting}); "
                         f"the {len(PROVINCES) - len(waiting)} read are kept in data/raw/iran "
                         f"and a re-run carries on from them")
    codab = load_codab(http_get(CODAB, binary=True))  # type: ignore[arg-type]
    return province_ages, province_citizenship, counties, codab


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provinces", default="",
                    help="fetch only these provinces' tables, e.g. 5-9,12 (SCI codes)")
    args = ap.parse_args()
    only = None
    if args.provinces:
        only = set()
        for part in args.provinces.split(","):
            low, _, high = part.partition("-")
            only.update(range(int(low), int(high or low) + 1))
    log("iran_census: 2016 census tables from the Internet Archive's captures of amar.org.ir")
    province_ages, province_citizenship, counties, codab = read_all(only=only)
    a1, a2 = drawn_units()
    rows, notes = build(province_ages, province_citizenship, counties, codab, a1, a2)
    gaps = split_records(a1, a2)
    for line in notes:
        log(f"  {line}")
    national = add_ages(list(province_ages.values()))
    ages = Counter({a: national["men"][a] + national["women"][a]
                    for a in set(national["men"]) | set(national["women"])})
    log(f"  Iran: median age {median_age(ages)}, {national['total'][1]:,} men and "
        f"{national['total'][2]:,} women")
    for level in ("admin1", "admin2"):
        mine = [r for r in rows if r["level"] == level]
        log(f"  {level}: {len(mine)} records")
    for r in rows:
        eth = ", ".join(f"{s['group']} {s['pct']}" for s in r["ethnicity"][:3])
        log(f"    {r['level']} {r['name']} [{r['shape_id']}]: {r['population']['value']:,}, "
            f"median {r['median_age']['value']}, ratio {r['sex_ratio']['value']}; {eth}")
    for r in gaps:
        log(f"    admin2 {r['name']} [{r['shape_id']}]: a stated gap (split since 2016)")
    write_json(PROCESSED / OUT, rows + gaps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
