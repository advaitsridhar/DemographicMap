"""Iraq's districts: the 2024 census, from the Annual Abstract of Statistics.

Iraq counted its people in November 2024, the first census since 1997, and
COSIT prints the result in Part Two of its Annual Abstract of Statistics 2024:
Table 11/2 gives every sub-district (nahiya) its population, by sex and by
urban and rural, under its district (qadhaa) and governorate, each with its
COSIT code, and a total for every district and governorate. OCHA's population
tables for Iraq stop at the governorate and Wikidata has no figure for most
districts, so 86 of the map's 101 were blank.

**The census's districts are not the map's.** The census has 181 districts
and 440 sub-districts; the boundary file, like OCHA's boundaries, has the 101
districts of before the subdivisions of recent years. A census district
joined to a map district by name alone would put part of a district's people
on the whole of it, which looks exactly like a right answer. So the census is
placed sub-district by sub-district, each on one of OCHA's 101 (the same
units the map draws), and a map district is the sum of what lands on it:

  * a sub-district by its own name, or the second name it carries in
    brackets, among OCHA's sub-districts (cod-ab-irq, CC BY-IGO) in its
    governorate -- Kurdish spellings folded to the Arabic ones OCHA writes;
  * a district's centre only where its district's own name puts it: a map
    district of that name, OCHA's sub-district of that name, or a town of
    that name in built-up ground among OCHA's populated places;
  * any other sub-district with the rest of its district, or where the town
    it is named for lies, among the districts its district points to.

A census district that lands whole on one map district gives it its printed
total; one split between map districts gives each its sub-districts'
figures, and only if those add up to its total. Where anything in a
governorate cannot be placed, the map districts it could be in are left
blank with the reason. A sub-district crosses a governorate line only with
its whole district: the Kurdistan Region's governorates count Aqra, Shekhan,
Bardarash and parts of Kifri and Khanaqin, which the map draws in Ninewa and
Diyala, and Ninewa counts Makhmour, which the map draws in Erbil -- but
Ninewa's Faeda (186,456 people) is not OCHA's 34 km2 Fayde in Duhok.

Every district so placed is then measured against Kontur's population grid
summed inside its shape: one whose count is more than three times, or less
than a third of, the grid's share of its governorate is not the same ground,
and is left blank with that reason. That is how Maysan's Al-Amara is caught:
the boundary file draws Amarah city in the shape it names Al-Kahla.

The governorates are the census's count of the ground the map draws, which
for Duhok, Ninewa, Erbil, Sulaymaniyah and Diyala is not the census's own
total; each says what moved.

``--dump`` writes the table's pages, OCHA's gazetteer and OCHA's populated
places to data/raw/iraq; ``--grid`` writes Kontur's population inside each of
OCHA's districts there; ``--offline`` reads them all from there.

Usage:
    python -m scripts.fetch_census.iraq_census --dump
    python -m scripts.fetch_census.iraq_census --grid
    python -m scripts.fetch_census.iraq_census
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import NOT_AVAILABLE, gap, measure, slugify  # noqa: E402
from probe_pdf import PAGE_BREAK, fetch_blob, laid_out  # noqa: E402

URL = "https://cosit.gov.iq/documents/AAS2024/02.pdf"
# OCHA's gazetteer of the boundaries the map draws (cod-ab-irq, CC BY-IGO):
# which sub-district lies in which of the 101 districts.
GAZETTEER = ("https://data.humdata.org/dataset/488bb3cd-3ce9-49d3-862a-3ce7975c63e1/"
             "resource/bde103b3-dc51-4e7b-9fd2-e38fa5600dc6/download/irq_admin_boundaries.xlsx")
# OCHA's populated places (CC BY-IGO), each P-coded to the sub-district and
# district of the boundaries the map draws: where a town the census names a
# district or sub-district after lies, when OCHA's gazetteer has no
# sub-district of that name.
PLACES = ("https://data.humdata.org/dataset/93170987-276d-4526-9e3d-c982759d8eba/"
          "resource/cf461e2e-4ae2-439d-a6c6-ec0c5e2f5bad/download/"
          "iraq-populated-places-2021-p-coded.xlsx")
PLACE_COLUMNS = ("PLACE_EN", "PLACE_AR", "PLACE_ALT", "ADM1_EN", "ADM2_EN", "ADM3_EN",
                 "WORLD_POP_")
# An independent check, never a figure: Kontur's population on 400 m H3
# hexagons (CC BY, November 2023), summed inside each of OCHA's districts
# (COD-AB, the map's). A district whose census figure sits far from its
# modelled share of the country has been put on the wrong ground.
KONTUR = ("https://geodata-eu-central-1-kontur-public.s3.amazonaws.com/"
          "kontur_datasets/kontur_population_IQ_20231101.gpkg.gz")
# A district refused by the grid: its census figure beyond this many times the
# grid's, or below its inverse; the grid used in a governorate only while its
# total there is within these bounds of the census's.
GRID_FAR = 3.0
GRID_FAIR = (2 / 3, 1.5)
BOUNDS = ("https://data.humdata.org/dataset/488bb3cd-3ce9-49d3-862a-3ce7975c63e1/"
          "resource/a9ed4d00-1182-4fdc-a0e4-82bbd20786db/download/"
          "irq_admin_boundaries.geojson.zip")
ROOT = Path(__file__).resolve().parent.parent.parent
GRID_DUMP = ROOT / "data" / "raw" / "iraq" / "kontur_adm2.txt"
DUMP = ROOT / "data" / "raw" / "iraq" / "aas2024_table11.txt"
GAZ_DUMP = ROOT / "data" / "raw" / "iraq" / "ocha_admin3.txt"
PLACES_DUMP = ROOT / "data" / "raw" / "iraq" / "ocha_places.txt"
OUT = PROCESSED / "iraq_census.json"
YEAR = 2024
NATIONAL = 46_118_793
SOURCE = ("COSIT, Annual Abstract of Statistics 2024, Table 11/2 (General "
          "Population and Housing Census 2024)")

# COSIT's governorate codes to OCHA's (and the map's) governorate names.
GOVERNORATE = {
    "11": "Duhok", "12": "Ninewa", "13": "Al-Sulaymaniyah", "14": "Kirkuk",
    "15": "Erbil", "21": "Diyala", "22": "Al-Anbar", "23": "Baghdad", "24": "Babil",
    "25": "Kerbala", "26": "Wassit", "27": "Salah Al-Din", "28": "Al-Najaf",
    "31": "Al-Qadissiya", "32": "Al-Muthanna", "33": "Thi Qar", "34": "Maysan",
    "35": "Al-Basrah",
}
# The map's first level spells seven governorates otherwise than OCHA's
# second-level file does; without these they took no census figure at all,
# and kept Wikidata's of 2011-2015 or the census's own totals as Wikipedia
# copies them, which count ground the map draws in another governorate.
MAP_NAMES = {
    "Duhok": ["Dohuk", "Dahuk"], "Ninewa": ["Ninawa", "Nineveh"],
    "Al-Sulaymaniyah": ["Al-Sulaimaniyah", "Sulaymaniyah"], "Al-Najaf": ["An-Najaf", "Najaf"],
    "Thi Qar": ["Dhi Qar"], "Kerbala": ["Karbala"], "Wassit": ["Wasit"],
    "Al-Qadissiya": ["Al-Qadisiyah", "Qadisiyah"], "Salah Al-Din": ["Salah al-Din"],
}
# How alike two romanisations must be, inside one governorate, to be one name;
# below SHORT letters they must be the same: "Suran" and "Shwan" are 0.89 alike.
ALIKE = 0.85
SHORT = 6
# OCHA's places carry WorldPop's density at the point; a district's centre is
# placed by a town only at one of the densest few percent (Al-Hur 34, Soran
# 21, Al-Mishkhab 15; the village called Haji Awa 3).
BUILT_UP = 10
# Sub-districts the census and OCHA spell differently, beyond what the keys
# fold: the Kurdish and the Arabic name of one place. (map governorate, the
# census's name's key) -> OCHA's sub-district.
DECLARED: dict[tuple[str, str], str] = {}
# The map's governorates whose ground a census governorate also counts, where a
# sub-district is looked for, by exact name only, when its own has none of
# that name. The Kurdistan Region administers parts of Ninewa, Kirkuk, Salah
# al-Din and Diyala, and the census counts them under Duhok, Erbil and
# Sulaymaniyah: Aqra and Shekhan under Duhok, the Kurdish-held parts of Kifri
# and Khanaqin under Sulaymaniyah; and Makhmour, which the map files under
# Erbil, under Ninewa.
NEIGHBOURS = {
    "11": ["Ninewa"],
    "12": ["Duhok", "Erbil"],
    "13": ["Diyala", "Kirkuk", "Erbil", "Salah Al-Din"],
    "14": ["Erbil", "Al-Sulaymaniyah", "Salah Al-Din"],
    "15": ["Ninewa", "Kirkuk", "Duhok"],
    "21": ["Al-Sulaymaniyah", "Salah Al-Din"],
    "27": ["Kirkuk", "Diyala"],
}
# Census districts that are a map district under another name. Sadr City was
# al-Thawra until 2003 and the census counts it as two districts.
# Amedi and Koya are the Kurdish names of Amadiya and Koysinjaq.
RENAMED = {"2303": "Al-Thawra", "2304": "Al-Thawra",
           "1104": "Al-Amadiya", "1506": "Koysinjaq"}

NUM = re.compile(r"\s*(\d{1,3}(?:,\d{3})+|\d+)\s")
CODE2 = re.compile(r"(?<![\d,])(\d{2})\s*-")
CODE4 = re.compile(r"(?<![\d,])(\d{4})(?!\d)")
TOTAL = re.compile(r"\btota?l?\b|Total", re.I)
EN_BEFORE = re.compile(r"([A-Za-z][A-Za-z .'()\-]*?)\s*(?:Tota?l?)?\s*-?\s*(\d{4})(?!\d)", re.I)
EN_AFTER = re.compile(r"(?<![\d,])(\d{4})\s*-?\s*([A-Za-z][A-Za-z .'()\-]*[A-Za-z)])")
AR_AFTER4 = re.compile(r"(?<![\d,])(\d{4})\s*-\s*([؀-ۿ][^A-Za-z\d]*)")
# A sub-district row: its English name, its five-digit code and its Arabic
# name, any of them glued to the next ("Hanebaje Taza13031", "13012-...").
NAHIYA = re.compile(r"(?:([A-Za-z][A-Za-z .'()\-]*?)\s*-?\s*)?(?<![\d,])(\d{5})(?!\d)"
                    r"\s*-?\s*([)(]*[؀-ۿ][^A-Za-z\d]*)?")
CENTRE = re.compile(r"^\s*D\.?\s?C\b", re.I)


def arabic(visual: str) -> str:
    """Arabic as the PDF lays it out, back in reading order."""
    return " ".join(word[::-1] for word in visual.split()[::-1])


def ar_key(text: str) -> str:
    text = re.sub(r"[ً-ْـ]", "", text or "")
    # Kurdish letters to the Arabic ones OCHA's gazetteer writes.
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"),
                 ("ی", "ي"), ("ک", "ك"), ("ۆ", "و"), ("ێ", "ي"), ("ە", "ه"),
                 ("ڕ", "ر"), ("ڵ", "ل"), ("ڤ", "ف"), ("گ", "ك"), ("چ", "ج"),
                 ("پ", "ب"), ("ژ", "ز")):
        text = text.replace(a, b)
    text = re.sub(r"(ق\.?\s?م|م\.?\s?ق|مركز|قضاء|ناحية)", " ", text)
    text = re.sub(r"(^|\s)ال", " ", text)
    # The lam-alef ligature comes out of the PDF in the wrong order; both
    # sides are folded to one spelling of it.
    text = text.replace("ال", "لا")
    return re.sub(r"[^؀-ۿ]", "", text)


def ar_loose(text: str) -> str:
    """ar_key without the medial ه that Kurdish spelling writes for a vowel
    Arabic spelling leaves out: Kurdish مهيدان is Arabic ميدان."""
    key = ar_key(text)
    return key[:1] + key[1:-1].replace("ه", "") + key[-1:] if len(key) > 2 else key


def en_key(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\b(d\.?\s?c\.?(\s*of)?|markaz|center|centre|district|distric|"
                  r"qadha|nahiya|total|tota)\b", " ", text)
    # A second name in brackets, closed or not: "Al-Kifl (Al-Nakhila".
    text = re.sub(r"\(.*?(\)|$)", " ", text)
    text = re.sub(r"\ba[li][- ]", " ", text)
    text = re.sub(r"[^a-z]", "", text)
    for a, b in (("kh", "h"), ("dh", "d"), ("th", "t"), ("sh", "s"), ("gh", "g"),
                 ("ch", "c"), ("ou", "u"), ("ee", "i"), ("oo", "u"), ("aa", "a"),
                 ("y", "i"), ("q", "k"), ("w", "u"), ("e", "i"), ("o", "u")):
        text = text.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", text)


def label(line: str) -> str:
    """The line with its leading figures taken off."""
    return re.sub(r"^\s*(?:(?:\d{1,3}(?:,\d{3})+|\d+|-)\s+)+", "", line)


def parse(text: str) -> dict[str, Any]:
    """The table's districts, sub-districts and governorates, with their totals."""
    districts: dict[str, int] = {}
    governorates: dict[str, int] = {}
    unlabelled: list[int] = []
    names: dict[str, Counter] = defaultdict(Counter)
    ar_names: dict[str, str] = {}
    nahiyas: dict[str, tuple[str, str, int]] = {}
    centres: set[str] = set()
    candidates: dict[str, list[int]] = defaultdict(list)
    # Rows with a figure and no code of their own, and where each district's
    # total row falls, to find the rows whose code the layout lost.
    loose: list[tuple[int, int, str]] = []
    ends: list[tuple[int, str | None]] = []
    grand = None
    for i, line in enumerate(text.split("\n")):
        tail = label(line)
        for m in EN_BEFORE.finditer(tail):
            name = clean(m.group(1))
            if name:
                names[m.group(2)][name] += 1
        for m in EN_AFTER.finditer(tail):
            name = clean(m.group(2))
            if name:
                names[m.group(1)][name] += 1
        for m in AR_AFTER4.finditer(tail):
            ar_names.setdefault(m.group(1), arabic(m.group(2)))
        first = NUM.match(line)
        if not first:
            continue
        value = int(first.group(1).replace(",", ""))
        rows = list(NAHIYA.finditer(tail))
        nahiya = rows[0] if len(rows) == 1 else None
        if nahiya and not TOTAL.search(tail.split(nahiya.group(2))[-1][:12]):
            code = nahiya.group(2)
            if code not in nahiyas:
                en = nahiya.group(1) or ""
                if not en:
                    after = re.match(r"\s*-?\s*([A-Za-z][A-Za-z .'()\-]*)",
                                     tail[nahiya.end(2):])
                    en = after.group(1) if after else ""
                ar = nahiya.group(3) or ""
                if not ar and en:
                    rest = re.search(r"[)(]*[؀-ۿ][^A-Za-z\d]*", tail[nahiya.end(2):])
                    ar = rest.group(0) if rest else ""
                nahiyas[code] = (clean(en), arabic(ar), value)
                if (CENTRE.search(nahiya.group(1) or "")
                        or re.search(r"م\s?\.\s?ق|ق\s?\.\s?م", nahiya.group(3) or "")):
                    centres.add(code)
        if not TOTAL.search(tail):
            # A district total printed without the word -- Panjwin's -- is
            # kept as a candidate, and taken below only if it is exactly the
            # sum of the district's own sub-districts.
            if not nahiya:
                for code in CODE4.findall(tail):
                    candidates[code].append(value)
                loose.append((i, value, tail))
            continue
        if "Grand Total" in tail:
            grand = value
            ends.append((i, None))
        elif "Governorate" in tail:
            code = CODE2.search(tail.split("Governorate", 1)[1])
            if code:
                governorates[code.group(1)] = value
            else:
                unlabelled.append(value)
            ends.append((i, None))
        else:
            codes = CODE4.findall(tail)
            if codes:
                districts.setdefault(codes[-1], value)
                ends.append((i, codes[-1]))
    by_district: Counter = Counter()
    for code, (_en, _ar, value) in nahiyas.items():
        by_district[code[:4]] += value
    for code, values in candidates.items():
        if code not in districts and by_district.get(code) in values:
            districts[code] = by_district[code]
    # A sub-district row whose code the layout lost (Semel's centre, printed
    # beside another table's caption; Al-Umarra's, printed as 4011) is the
    # one row among its district's with no code of its own whose figure is
    # exactly what the district's total leaves over, and is kept only when
    # there is one such row.
    start = -1
    for end, code in ends:
        if code and code in districts:
            rest = districts[code] - by_district[code]
            found = [(i, v, t) for i, v, t in loose if start < i < end and v == rest]
            if rest > 0 and len(found) == 1 and code + "0" not in nahiyas:
                own = names[code].most_common(1)[0][0] if names.get(code) else code
                if "D.C" in found[0][2]:
                    nahiyas[code + "0"] = (f"D.C of {own}", "", rest)
                    centres.add(code + "0")
                else:
                    nahiyas[code + "0"] = (f"{own} (a row printed without its code)", "", rest)
                by_district[code] += rest
        start = end
    # A governorate total printed without its code is the one its districts
    # add up to.
    sums: Counter = Counter()
    for code, value in districts.items():
        sums[code[:2]] += value
    for value in unlabelled:
        owners = [g for g, s in sums.items() if s == value and g not in governorates]
        if len(owners) == 1:
            governorates[owners[0]] = value
    return {"districts": districts, "governorates": governorates, "names": names,
            "ar_names": ar_names, "nahiyas": nahiyas, "centres": centres,
            "grand": grand, "sums": sums,
            "whole": {c for c, v in districts.items() if by_district[c] == v}}


def clean(name: str) -> str:
    name = re.sub(r"\b(Tota?l?|total|D\.?\s?C\.?(\s*of)?)\b", " ", name, flags=re.I)
    return " ".join(name.replace(" - ", "-").split()).strip(" -)(")


def read_gazetteer(text: str) -> list[dict[str, str]]:
    lines = text.split("\n")
    header = lines[0].split("\t")
    rows = [dict(zip(header, line.split("\t"))) for line in lines[1:]]
    return [r for r in rows if (r.get("adm3_pcode") or "").startswith("IQG")]


def variants(name: str) -> list[str]:
    """A name and the second name it carries in brackets, closed or not:
    "Akd (Al-Daggara" is Akd and Al-Daggara."""
    name = name or ""
    m = re.search(r"\(([^)]*)\)?", name)
    if not m:
        return [name] if name.strip() else []
    outside = (name[:m.start()] + " " + name[m.end():]).strip()
    return [v for v in (outside, m.group(1).strip()) if v]


def alike(a: str, b: str) -> bool:
    """Two keys that are one name: much alike, or -- for short ones, where a
    ratio says little -- the same consonants in the same order, as Graf and
    Garaf (Al-Gharraf) are and Suran and Suan (Soran, Shwan) are not, or
    one letter apart in five from the same first letter (Admia, Adamia; not
    Abara, Jabara)."""
    if not (a and b):
        return False
    if a == b:
        return True
    ratio = SequenceMatcher(None, a, b).ratio()
    if min(len(a), len(b)) >= SHORT:
        return ratio >= ALIKE
    bones = [re.sub(r"[aiu]", "", k) for k in (a, b)]
    return (bones[0] == bones[1] and len(bones[0]) >= 3) or (
        min(len(a), len(b)) >= 4 and ratio >= 0.9 and a[0] == b[0])


def crosswalk(table: dict[str, Any], gazetteer: list[dict[str, str]],
              places: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Each map district's and map governorate's census count, where it can be known.

    Every sub-district the census counts is put on one of the map's districts:
    by its own name among OCHA's sub-districts (in its governorate, or exactly
    in a governorate whose ground its governorate also counts), or else with
    its district -- its district's centre where the district's own name puts
    it, any other where its district's named sub-districts all lie. A census
    district whose sub-districts all land in one map district gives it its
    printed total; one split between map districts gives each its
    sub-districts' figures, and only if those add up to its total.
    """
    districts, names, ar_names = table["districts"], table["names"], table["ar_names"]
    nahiyas, centres = table["nahiyas"], table["centres"]
    by_gov: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    subs: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in gazetteer:
        by_gov[row["adm1_name"]].setdefault(row["adm2_name"], row)
        subs[row["adm1_name"]].append(row)

    def own(code: str) -> str:
        return names[code].most_common(1)[0][0] if names.get(code) else code

    # OCHA's populated places, by the keys of each of their names.
    towns: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    built: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in places or []:
        gov, district = row.get("ADM1_EN", ""), row.get("ADM2_EN", "")
        if gov not in by_gov or district not in by_gov[gov]:
            continue
        try:
            dense = float(row.get("WORLD_POP_") or 0) >= BUILT_UP
        except ValueError:
            dense = False
        keys = set()
        for name in (row.get("PLACE_EN"), row.get("PLACE_ALT")):
            for v in variants(name or ""):
                if re.search(r"[A-Za-z]", v) and len(en_key(v)) >= 3:
                    keys.add("en:" + en_key(v))
        for name in (row.get("PLACE_AR"), row.get("PLACE_ALT")):
            for v in variants(name or ""):
                if len(ar_key(v)) >= 3:
                    keys.add("ar:" + ar_key(v))
        for k in keys:
            towns[gov][k].add(district)
            if dense:
                built[gov][k].add(district)

    def town_named(en: str, ar: str, govs: list[str],
                   dense: bool = False) -> set[tuple[str, str]]:
        """The districts OCHA's places of this name lie in, exactly spelt;
        with ``dense``, only places in built-up ground."""
        keys = {"en:" + en_key(v) for v in variants(en) if len(en_key(v)) >= 3}
        keys |= {"ar:" + ar_key(v) for v in variants(ar) if len(ar_key(v)) >= 3}
        index = built if dense else towns
        for gov in govs:
            hit = {(gov, d) for k in keys for d in index[gov].get(k, ())}
            if hit:
                return hit
        return set()

    def reach(g2: str) -> tuple[list[str], list[str]]:
        return [GOVERNORATE[g2]], NEIGHBOURS.get(g2, [])

    def sub_rows(en: str, ar: str, gov: str, fuzzy: bool) -> list[dict[str, str]]:
        """OCHA's sub-districts in a governorate that are this name."""
        eks = {en_key(v) for v in variants(en)} - {""}
        aks = {ar_key(v) for v in variants(ar)} - {""}
        rows = [r for r in subs[gov]
                if en_key(r["adm3_name"]) in eks or ar_key(r.get("adm3_name1")) in aks
                or DECLARED.get((gov, en_key(en))) == r["adm3_name"]]
        if not rows and fuzzy:
            loose = {ar_loose(v) for v in variants(ar)} - {""}
            rows = [r for r in subs[gov]
                    if any(alike(k, en_key(r["adm3_name"])) for k in eks)
                    or (len(ar_loose(r.get("adm3_name1"))) >= 3
                        and ar_loose(r.get("adm3_name1")) in loose)]
        return rows

    def sub_named(en: str, ar: str, govs: list[str], fuzzy: bool) -> set[tuple[str, str]]:
        for gov in govs:
            hit = {(gov, r["adm2_name"]) for r in sub_rows(en, ar, gov, fuzzy)}
            if hit:
                return hit
        return set()

    def district_named(code: str, govs: list[str], fuzzy: bool) -> set[tuple[str, str]]:
        keys = {en_key(n) for n in names.get(code, {})} - {""}
        ak = ar_key(ar_names.get(code, ""))
        for gov in govs:
            if RENAMED.get(code) in by_gov[gov]:
                return {(gov, RENAMED[code])}
            hit = {(gov, d) for d, row in by_gov[gov].items()
                   if en_key(d) in keys or (ak and ak == ar_key(row.get("adm2_name1")))}
            if not hit and fuzzy:
                hit = {(gov, d) for d in by_gov[gov] if any(alike(k, en_key(d)) for k in keys)}
            if hit:
                return hit
        return set()

    def seat_of(code: str) -> set[tuple[str, str]]:
        """Where a census district's own name puts it: a map district of
        that name, or the sub-district it was made from."""
        home, far = reach(code[:2])
        variants = list(names.get(code, {})) or [""]
        for govs, fuzzy in ((home, True), (far, False)):
            found = district_named(code, govs, fuzzy)
            if not found:
                found = set().union(*(sub_named(n, ar_names.get(code, ""), govs, fuzzy)
                                      for n in variants))
            if found:
                return found
        # Or where its sub-districts are: Duhok's Akri is Ninewa's Aqra by
        # its Dinarta, Bejel and Kurdsin, when none of them is found at home
        # and at least two are found, all in one district, across the line.
        own_subs = [nahiyas[n] for n in nahiyas if n[:4] == code]
        if not any(sub_named(en, ar, home, True) for en, ar, _v in own_subs):
            across = [sub_named(en, ar, far, False) for en, ar, _v in own_subs]
            across = [hit for hit in across if hit]
            union = set().union(*across) if across else set()
            if len(across) >= 2 and len(union) == 1:
                return union
        # Or where the town it is named for lies, among OCHA's places -- a
        # place in built-up ground, for a village of the same name is
        # common: OCHA's only Haji Awa is a village by Sulaymaniyah, not the
        # town of Hajiawa that the census's district is named for.
        return set().union(*(town_named(n, ar_names.get(code, ""), home, dense=True)
                             for n in variants))

    seat = {code: seat_of(code) for code in districts}
    place: dict[str, tuple[str, str]] = {}
    by_name: set[str] = set()
    by_town: set[str] = set()
    how: dict[str, str] = {}
    for n, (en, ar, _v) in nahiyas.items():
        # A sub-district is looked for in another governorate only with its
        # whole district: the census's Faeda, under Ninewa's Telkef, has
        # 186,456 people, and OCHA's Fayde in Duhok 34 square kilometres.
        home, _far = reach(n[:2])
        crossed = sorted({g for g, _d in seat[n[:4]]} - set(home))
        found = sub_named(en, ar, home, True) or sub_named(en, ar, crossed, True)
        if len(found) == 1:
            place[n] = next(iter(found))
            by_name.add(n)
            how[n] = "its own name among OCHA's sub-districts"
    members: dict[str, list[str]] = defaultdict(list)
    for n in sorted(nahiyas):
        members[n[:4]].append(n)
    for code in districts:
        named = {place[n] for n in members[code] if n in place}
        own_seat = seat[code]
        # A sub-district no gazetteer name places goes where the town it is
        # named for lies -- but a village of the same name elsewhere is
        # common, so only among the districts its own district already
        # points to, when it points to any.
        within = named | own_seat
        for n in members[code]:
            if n in place or n in centres:
                continue
            home, _far = reach(n[:2])
            govs = sorted({g for g, _d in within}) or home
            found = town_named(nahiyas[n][0], nahiyas[n][1], govs)
            if within:
                found &= within
            if len(found) == 1:
                place[n] = next(iter(found))
                by_town.add(n)
                how[n] = "the town it is named for, among OCHA's places"
        named = {place[n] for n in members[code] if n in place}
        for n in members[code]:
            if n in place:
                continue
            if n in centres:
                # A centre goes only where its district's own name puts it:
                # Saed Sadiq's one other sub-district is OCHA's Saruchik in
                # Sharbazher, and Sayid Sadiq town is in Halabja.
                if len(own_seat) == 1:
                    place[n] = next(iter(own_seat))
                    how[n] = "the centre of its district, which is placed by its own name"
            elif len(named) == 1:
                place[n] = next(iter(named))
                how[n] = "with its district's other sub-districts"
            elif not named and len(own_seat) == 1:
                place[n] = next(iter(own_seat))
                how[n] = "with its district, which is placed by its own name"

    value: Counter = Counter()
    parts: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    soft: set[tuple[str, str]] = set()
    tainted: dict[tuple[str, str], list[str]] = defaultdict(list)
    gov_value: Counter = Counter()
    gov_unknown: dict[str, list[str]] = defaultdict(list)
    moved: list[tuple[str, str, str, int]] = []   # census gov, map gov, what, people
    notes: list[str] = []
    for code, total in sorted(districts.items()):
        census_gov = GOVERNORATE[code[:2]]
        ns = members[code]
        homes = {place[n] for n in ns if n in place}
        lost = [n for n in ns if n not in place]
        if lost:
            cands = homes | seat[code]
            # A centre not placed could be anywhere its district is; with no
            # seat, that is anywhere in the governorate.
            if not cands or (any(n in centres for n in lost) and not seat[code]):
                cands |= {(census_gov, d) for d in by_gov[census_gov]}
            what = ", ".join(nahiyas[n][0] or n for n in lost)
            for key in cands:
                tainted[key].append(
                    f"{own(code)} district" if all(n in centres for n in lost) or len(lost) == len(ns)
                    else f"{what} in {own(code)} district")
            notes.append(f"{census_gov} {own(code)}: not placed: {what}; "
                         f"could be in {', '.join(sorted(d for _, d in cands))}")
            govs = {g for g, _ in cands}
            if len(govs) == 1:
                gov = next(iter(govs))
                gov_value[gov] += total
                if gov != census_gov:
                    moved.append((census_gov, gov, f"{own(code)} district", total))
            else:
                for gov in govs:
                    gov_unknown[gov].append(own(code))
            continue
        if len(homes) == 1:
            key = next(iter(homes))
            value[key] += total
            parts[key].append((own(code), total))
            if any(n not in by_name for n in ns):
                soft.add(key)
            gov_value[key[0]] += total
            if key[0] != census_gov:
                moved.append((census_gov, key[0], f"{own(code)} district", total))
            continue
        if code not in table["whole"]:
            for key in homes:
                tainted[key].append(f"SPLIT{own(code)} district, whose sub-districts are split "
                                    f"between these shapes and do not add up to its total")
            for gov in {g for g, _ in homes}:
                gov_unknown[gov].append(own(code))
            continue
        for n in ns:
            key, (en, _ar, v) = place[n], nahiyas[n]
            value[key] += v
            parts[key].append((f"{en or n} ({own(code)})", v))
            if n not in by_name:
                soft.add(key)
            gov_value[key[0]] += v
            if key[0] != census_gov:
                moved.append((census_gov, key[0], f"{en or n} sub-district", v))

    # Ground the boundary file draws that the census names nowhere: a map
    # district whose every census sub-district was found by name, but one of
    # whose own sub-districts has no namesake in the census, may have lost
    # that sub-district's people to another district.
    found = set()
    for n, (en, ar, _v) in nahiyas.items():
        for gov in reach(n[:2])[0] + reach(n[:2])[1]:
            found.update(r["adm3_pcode"] for r in sub_rows(en, ar, gov, True))
    for code in districts:
        for gov in reach(code[:2])[0] + reach(code[:2])[1]:
            for name in names.get(code, {}):
                found.update(r["adm3_pcode"]
                             for r in sub_rows(name, ar_names.get(code, ""), gov, True))
    unnamed: dict[tuple[str, str], list[str]] = defaultdict(list)
    for gov, rows in subs.items():
        for r in rows:
            if r["adm3_pcode"] not in found:
                unnamed[(gov, r["adm2_name"])].append(r["adm3_name"])
    for key, missing in unnamed.items():
        if key in value and key not in soft:
            tainted[key].append(f"NOWHEREthe census names nowhere the boundary file's "
                                f"{', '.join(missing)}, drawn in this district")

    # A map district no census sub-district lands on: its people were put
    # somewhere else, so nothing in its governorate can be trusted.
    for gov, candidates in by_gov.items():
        empty = [d for d in candidates if (gov, d) not in value and (gov, d) not in tainted]
        if empty:
            notes.append(f"{gov}: no census sub-district lands on {', '.join(empty)}")
            for d in candidates:
                tainted[(gov, d)].append(f"EMPTY{', '.join(empty)}")

    out: dict[str, dict[str, Any]] = {}
    for gov, candidates in by_gov.items():
        for district, row in candidates.items():
            key = (gov, district)
            entry = {"governorate": gov, "district": district,
                     "arabic": row.get("adm2_name1"), "value": None}
            if key in tainted:
                reasons = sorted(set(tainted[key]))
                lost = [r for r in reasons if not r.startswith(("SPLIT", "NOWHERE", "EMPTY"))]
                bits = []
                if lost:
                    bits.append("nothing places " + ", ".join(lost[:4])
                                + (" and others" if len(lost) > 4 else "")
                                + " on these shapes, and "
                                + ("it" if len(lost) == 1 else "any of them")
                                + " could be on this one")
                bits += [r[5:] for r in reasons if r.startswith("SPLIT")]
                bits += [r[7:] for r in reasons if r.startswith("NOWHERE")]
                bits += [f"no census unit lands on {r[5:]}, so the people there were put "
                         f"somewhere else" for r in reasons if r.startswith("EMPTY")]
                entry["why"] = (
                    "The 2024 census counts this governorate on districts redrawn since "
                    "the boundary file's, and " + "; ".join(bits) + ", so this district's "
                    "figure is not known on its shape. The governorate's own count is on "
                    "the governorate.")
            else:
                entry["value"] = value[key]
                entry["parts"] = parts[key]
            out[f"{gov}/{district}"] = entry
        written = sum(1 for d in candidates if (gov, d) not in tainted)
        notes.append(f"{gov}: {written} of {len(candidates)} districts")

    govs: dict[str, dict[str, Any]] = {}
    census = {GOVERNORATE[g]: v for g, v in table["governorates"].items()}
    for gov in GOVERNORATE.values():
        if gov_unknown.get(gov):
            govs[gov] = {"value": None, "why": (
                f"The 2024 census counts {', '.join(sorted(set(gov_unknown[gov])))} on "
                f"ground split between this governorate and another as the map draws "
                f"them, so the governorate's count on these boundaries is not known.")}
            continue
        entry = {"value": gov_value[gov]}
        into = [m for m in moved if m[1] == gov]
        away = [m for m in moved if m[0] == gov]
        if into or away:
            bits = []
            if away:
                bits.append("counts " + ", ".join(f"{w} ({v:,})" for _c, _m, w, v in away)
                            + f" under {gov}, which the map draws in "
                            + ", ".join(sorted({m for _c, m, _w, _v in away})))
            if into:
                bits.append("counts " + ", ".join(f"{w} ({v:,})" for _c, _m, w, v in into)
                            + " under " + ", ".join(sorted({c for c, _m, _w, _v in into}))
                            + f", which the map draws in {gov}")
            entry["note"] = (f"The census's own total for {gov} is {census[gov]:,}. It "
                             + "; it ".join(bits)
                             + ". The figure is the census's count of the ground drawn here.")
        govs[gov] = entry
    placed = [(n, nahiyas[n][0] or n, own(n[:4]), nahiyas[n][2], place[n], how.get(n, ""))
              for n in sorted(place)]
    return {"districts": out, "governorates": govs, "notes": notes, "placed": placed}


def gazetteer_rows(blob: bytes) -> list[list[str]]:
    """Every sheet's rows that name a sub-district, as tab-separated text."""
    import io

    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    out: list[list[str]] = []
    for sheet in book.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c or "") for c in rows[0]]
        log(f"  sheet {sheet.title!r}: {len(rows) - 1} rows, {header[:14]}")
        if not any(h.upper().startswith("ADM3") for h in header):
            continue
        out.append(header)
        out.extend([["" if c is None else str(c) for c in row] for row in rows[1:]])
    return out


def place_rows(blob: bytes) -> list[list[str]]:
    """The master sheet's places, only the columns placing needs."""
    import io

    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = next((ws for ws in book.worksheets if "master" in ws.title.lower()),
                 book.worksheets[-1])
    rows = sheet.iter_rows(values_only=True)
    header = [str(c or "").strip() for c in next(rows)]
    at = [header.index(c) for c in PLACE_COLUMNS]
    out = [list(PLACE_COLUMNS)]
    for row in rows:
        cells = ["" if row[i] is None else " ".join(str(row[i]).split()) for i in at]
        # The second header row carries HXL tags, not a place.
        if cells[0] and not cells[0].startswith("#"):
            out.append(cells)
    log(f"  {PLACES}: {len(out) - 1:,} places")
    return out


def read_places(text: str) -> list[dict[str, str]]:
    lines = [line for line in (text or "").split("\n") if line]
    if not lines:
        return []
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:]]


def grid_totals() -> list[list[str]]:
    """Kontur's population inside each of OCHA's districts."""
    import gzip
    import io
    import json
    import math
    import tempfile
    import zipfile

    import fiona
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    book = zipfile.ZipFile(io.BytesIO(fetch_blob(BOUNDS)))
    name = next(n for n in book.namelist()
                if re.search(r"adm(in)?2", n, re.I) and n.lower().endswith("json"))
    features = json.loads(book.read(name))["features"]
    polygons = [shape(f["geometry"]) for f in features]
    tree = STRtree(polygons)
    totals = [0.0] * len(polygons)
    outside = 0.0
    with tempfile.NamedTemporaryFile(suffix=".gpkg") as tmp:
        tmp.write(gzip.decompress(fetch_blob(KONTUR)))
        tmp.flush()
        with fiona.open(tmp.name) as src:
            mercator = "3857" in str(src.crs)
            for feature in src:
                c = shape(feature["geometry"]).centroid
                x, y = c.x, c.y
                if mercator:
                    x = math.degrees(x / 6378137.0)
                    y = math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2)
                people = float(feature["properties"].get("population") or 0)
                hits = tree.query(Point(x, y), predicate="intersects")
                if len(hits):
                    totals[int(hits[0])] += people
                else:
                    outside += people
    log(f"  Kontur: {sum(totals):,.0f} people in {len(polygons)} districts, "
        f"{outside:,.0f} outside them")
    rows = [["adm1_name", "adm2_name", "population"]]
    for feature, total in zip(features, totals):
        props = feature["properties"]
        rows.append([props.get("adm1_name", ""), props.get("adm2_name", ""), f"{total:.0f}"])
    return rows


def read_grid(text: str) -> dict[tuple[str, str], float]:
    lines = [line.split("\t") for line in (text or "").split("\n") if line]
    return {(a, b): float(v) for a, b, v in lines[1:]} if lines else {}


def grid_check(result: dict[str, Any], grid: dict[tuple[str, str], float]) -> list[str]:
    """Refuse the written districts whose census figure is far from what the
    grid puts inside their shape, measured against their governorate's own
    ratio so that the grid's regional errors cancel; returns the log.

    Maysan's Al-Amara is where this bites: its census count, 759,526, is
    Amarah city's, and the boundary file draws Amarah city inside the shape
    it names Al-Kahla -- 7.9 times the grid there, and Al-Kahla 0.15. Where
    the grid is itself far from the census for a whole governorate (Duhok:
    Zakho alone 930,000 on the grid, 398,876 counted) it says nothing about
    the districts inside, and is not used."""
    if not grid:
        return []
    by_gov: dict[str, float] = defaultdict(float)
    for (gov, _d), people in grid.items():
        by_gov[gov] += people
    national = sum(e["value"] for e in result["governorates"].values() if e["value"])
    scale = national / sum(grid.values())
    lines = []
    for gov, entry in sorted(result["governorates"].items()):
        if not entry["value"] or not by_gov.get(gov):
            continue
        ratio = entry["value"] / by_gov[gov]
        if not GRID_FAIR[0] <= ratio / scale <= GRID_FAIR[1]:
            lines.append(f"{gov}: the grid holds {by_gov[gov]:,.0f} against the census's "
                         f"{entry['value']:,}; not used inside it")
            continue
        for e in result["districts"].values():
            if e["governorate"] != gov or e["value"] is None:
                continue
            modelled = grid.get((gov, e["district"]), 0) * ratio
            share = e["value"] / modelled if modelled else float("inf")
            lines.append(f"{share:5.2f}  {gov}/{e['district']}: census {e['value']:,}, "
                         f"grid {modelled:,.0f}")
            if not 1 / GRID_FAR <= share <= GRID_FAR:
                e["why"] = (
                    f"The 2024 census's count for the ground placed here, {e['value']:,}, "
                    f"is {share:.1f} times what Kontur's population grid puts inside this "
                    f"shape, scaled to {gov}'s census total, so the census's units and "
                    f"the boundary file's {e['district']} are not the same ground. The "
                    f"governorate's own count is on the governorate.")
                e["value"] = None
                e.pop("parts", None)
    return lines


def table_pages(text: str) -> list[str]:
    """The pages of Table 11/2: those whose header names a nahiya."""
    return [page for page in text.split(PAGE_BREAK) if "Nahiya" in page]


def build(text: str, gazetteer_text: str, places_text: str = "") -> list[dict[str, Any]]:
    table = parse(text)
    govs = table["governorates"]
    bad = {g: (v, table["sums"][g]) for g, v in govs.items() if table["sums"][g] != v}
    log(f"  {len(table['districts'])} districts, {len(govs)} governorates, "
        f"{len(table['nahiyas'])} sub-districts; governorates sum to "
        f"{sum(govs.values()):,} against the grand total {table['grand']:,}")
    if len(govs) != len(GOVERNORATE) or sum(govs.values()) != NATIONAL or bad:
        raise SystemExit(f"the table does not add up (governorates {sorted(govs)}, "
                         f"mismatched {bad}); nothing written")
    result = crosswalk(table, read_gazetteer(gazetteer_text), read_places(places_text))
    mapped = result["districts"]
    for line in result["notes"]:
        log(f"  {line}")
    grid = read_grid(GRID_DUMP.read_text(encoding="utf-8")) if GRID_DUMP.exists() else {}
    for line in grid_check(result, grid):
        log(f"  grid {line}")
    cite = [{"field": "population", "name": SOURCE, "url": URL}]
    rows = []
    codes = {gov: code for code, gov in GOVERNORATE.items()}
    for gov, entry in result["governorates"].items():
        if entry["value"] is None:
            population = gap(NOT_AVAILABLE, entry["why"])
        else:
            population = measure(entry["value"], year=YEAR, source=SOURCE)
            if entry.get("note"):
                population["note"] = entry["note"]
        rows.append(record(f"IRQ-CEN-{codes[gov]}", gov, level="admin1", parent="IRQ",
                           country="IRQ", population=population,
                           aliases=MAP_NAMES.get(gov),
                           sources=cite if entry["value"] is not None else None))
    for entry in mapped.values():
        if entry["value"] is None:
            rows.append(record(
                f"IRQ-CEN-{slugify(entry['governorate'])}-{slugify(entry['district'])}",
                entry["district"], level="admin2", parent="IRQ", country="IRQ",
                parent_name=entry["governorate"],
                aliases=[a for a in (entry["arabic"],) if a],
                population=gap(NOT_AVAILABLE, entry["why"])))
            continue
        population = measure(entry["value"], year=YEAR, source=SOURCE)
        if len(entry["parts"]) > 1:
            population["note"] = (
                "The census counts this ground as " + str(len(entry["parts"]))
                + " units, on boundaries redrawn since the boundary file's: "
                + ", ".join(f"{n} ({v:,})" for n, v in entry["parts"])
                + ". The figure is their sum.")
        rows.append(record(
            f"IRQ-CEN-{slugify(entry['governorate'])}-{slugify(entry['district'])}",
            entry["district"], level="admin2", parent="IRQ", country="IRQ",
            parent_name=entry["governorate"],
            aliases=[a for a in (entry["arabic"],) if a],
            population=population, sources=cite))
    written = sum(1 for r in rows if r["level"] == "admin2" and "value" in r["population"])
    log(f"  {written} map districts with a figure, "
        f"{len(mapped) - written} with the reason they have none")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true", help="save the table and gazetteer")
    ap.add_argument("--offline", action="store_true", help="read the saved copies")
    ap.add_argument("--grid", action="store_true",
                    help="save Kontur's population inside each of OCHA's districts")
    args = ap.parse_args()
    if args.grid:
        GRID_DUMP.parent.mkdir(parents=True, exist_ok=True)
        GRID_DUMP.write_text("\n".join("\t".join(r) for r in grid_totals()) + "\n",
                             encoding="utf-8")
        log(f"  wrote {GRID_DUMP.relative_to(ROOT)}")
        return 0
    if args.offline:
        text = DUMP.read_text(encoding="utf-8")
        gazetteer = GAZ_DUMP.read_text(encoding="utf-8")
        places = PLACES_DUMP.read_text(encoding="utf-8") if PLACES_DUMP.exists() else ""
    else:
        blob = fetch_blob(URL)
        log(f"  {URL}: {len(blob):,} bytes")
        text = PAGE_BREAK.join(table_pages(laid_out(blob)))
        gazetteer = "\n".join("\t".join(r) for r in gazetteer_rows(fetch_blob(GAZETTEER)))
        places = "\n".join("\t".join(r) for r in place_rows(fetch_blob(PLACES)))
        if args.dump:
            DUMP.parent.mkdir(parents=True, exist_ok=True)
            DUMP.write_text(text, encoding="utf-8")
            GAZ_DUMP.write_text(gazetteer, encoding="utf-8")
            PLACES_DUMP.write_text(places + "\n", encoding="utf-8")
            log(f"  wrote {DUMP.relative_to(ROOT)}, {GAZ_DUMP.relative_to(ROOT)} "
                f"and {PLACES_DUMP.relative_to(ROOT)}")
            return 0
    write_json(OUT, build(text, gazetteer, places))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
