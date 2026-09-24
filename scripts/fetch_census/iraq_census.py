"""Iraq's districts: the 2024 census, from the Annual Abstract of Statistics.

Iraq counted its people in November 2024, the first census since 1997, and
COSIT prints the result in Part Two of its Annual Abstract of Statistics 2024:
Table 11/2 gives every sub-district (nahiya) its population, by sex and by
urban and rural, under its district (qadhaa) and governorate, each with its
COSIT code, and a total for every district and governorate. OCHA's population
tables for Iraq stop at the governorate and Wikidata has no figure for most
districts, so 86 of the map's 101 were blank.

**The census's districts are not the map's.** The census has 180 districts;
the boundary file, like OCHA's boundaries, has the 101 of before the
subdivisions of recent years -- Baghdad's Kadhimiya has since lost Sama
al-Kadhimiya and Fada' al-Kazimia, Sulaymaniyah's districts have become
seventeen. A census district joined to a map district by name alone would put
part of a district's people on the whole of it, which looks exactly like a
right answer. So each census district is placed inside one of OCHA's 101 (the
same units the map draws), by its own name where that is one of them and
otherwise by its centre's sub-district in OCHA's gazetteer (cod-ab-irq, CC
BY-IGO), and a map district is the sum of the census districts placed in it.

That is only as good as the placing, so a governorate is written only when
every check holds:

  * every one of its census districts is placed;
  * every one of its map districts receives at least one;
  * no sub-district the gazetteer knows sits in a different map district from
    the one its census district was placed in;
  * and no map district shares its name with a census district of another
    governorate -- Kifri and Khanaqin are each counted partly under
    Sulaymaniyah and partly under Diyala, and Makhmour under Ninewa where the
    map files it under Erbil, so none of those takes a figure at all.

The governorates' own totals are written for every governorate: they are the
census's, exact, and the districts of each written governorate add up to them.

``--dump`` writes the table's pages and OCHA's gazetteer to data/raw/iraq;
``--offline`` reads them from there.

Usage:
    python -m scripts.fetch_census.iraq_census --dump
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
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "iraq" / "aas2024_table11.txt"
GAZ_DUMP = ROOT / "data" / "raw" / "iraq" / "ocha_admin3.txt"
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
# How alike two romanisations must be, inside one governorate, to be one name.
ALIKE = 0.85
# Census districts that are a map district under another name. Sadr City was
# al-Thawra until 2003 and the census counts it as two districts.
RENAMED = {"2303": "Al-Thawra", "2304": "Al-Thawra"}

NUM = re.compile(r"\s*(\d{1,3}(?:,\d{3})+|\d+)\s")
CODE2 = re.compile(r"(?<![\d,])(\d{2})\s*-")
CODE4 = re.compile(r"(?<![\d,])(\d{4})(?!\d)")
TOTAL = re.compile(r"\btota?l?\b|Total", re.I)
EN_BEFORE = re.compile(r"([A-Za-z][A-Za-z .'()\-]*?)\s*(?:Tota?l?)?\s*-?\s*(\d{4})(?!\d)", re.I)
EN_AFTER = re.compile(r"(?<![\d,])(\d{4})\s*-?\s*([A-Za-z][A-Za-z .'()\-]*[A-Za-z)])")
AR_AFTER4 = re.compile(r"(?<![\d,])(\d{4})\s*-\s*([؀-ۿ][^A-Za-z\d]*)")
NAHIYA = re.compile(r"([A-Za-z][A-Za-z .'()\-]*?)?\s*-\s*(\d{5})(?!\d)\s*-?\s*"
                    r"([؀-ۿ][^A-Za-z\d]*)?")


def arabic(visual: str) -> str:
    """Arabic as the PDF lays it out, back in reading order."""
    return " ".join(word[::-1] for word in visual.split()[::-1])


def ar_key(text: str) -> str:
    text = re.sub(r"[ً-ْـ]", "", text or "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"),
                 ("ی", "ي"), ("ک", "ك"), ("ۆ", "و"), ("ێ", "ي"), ("ە", "ه")):
        text = text.replace(a, b)
    text = re.sub(r"(ق\.?\s?م|م\.?\s?ق|مركز|قضاء|ناحية)", " ", text)
    text = re.sub(r"(^|\s)ال", " ", text)
    # The lam-alef ligature comes out of the PDF in the wrong order; both
    # sides are folded to one spelling of it.
    text = text.replace("ال", "لا")
    return re.sub(r"[^؀-ۿ]", "", text)


def en_key(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\b(d\.?\s?c\.?(\s*of)?|markaz|center|centre|district|distric|"
                  r"qadha|nahiya|total|tota)\b", " ", text)
    text = re.sub(r"\(.*?\)", " ", text)
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
    candidates: dict[str, list[int]] = defaultdict(list)
    grand = None
    for line in text.split("\n"):
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
        nahiya = NAHIYA.search(tail)
        if nahiya and not TOTAL.search(tail.split(nahiya.group(2))[-1][:12]):
            nahiyas.setdefault(nahiya.group(2), (clean(nahiya.group(1) or ""),
                                                 arabic(nahiya.group(3) or ""), value))
        if not TOTAL.search(tail):
            # A district total printed without the word -- Panjwin's -- is
            # kept as a candidate, and taken below only if it is exactly the
            # sum of the district's own sub-districts.
            if not nahiya:
                for code in CODE4.findall(tail):
                    candidates[code].append(value)
            continue
        if "Grand Total" in tail:
            grand = value
        elif "Governorate" in tail:
            code = CODE2.search(tail.split("Governorate", 1)[1])
            if code:
                governorates[code.group(1)] = value
            else:
                unlabelled.append(value)
        else:
            codes = CODE4.findall(tail)
            if codes:
                districts.setdefault(codes[-1], value)
    by_district: Counter = Counter()
    for code, (_en, _ar, value) in nahiyas.items():
        by_district[code[:4]] += value
    for code, values in candidates.items():
        if code not in districts and by_district.get(code) in values:
            districts[code] = by_district[code]
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
            "ar_names": ar_names, "nahiyas": nahiyas, "grand": grand, "sums": sums}


def clean(name: str) -> str:
    name = re.sub(r"\b(Tota?l?|total|D\.?\s?C\.?(\s*of)?)\b", " ", name, flags=re.I)
    return " ".join(name.replace(" - ", "-").split()).strip(" -)(")


def read_gazetteer(text: str) -> list[dict[str, str]]:
    lines = text.split("\n")
    header = lines[0].split("\t")
    rows = [dict(zip(header, line.split("\t"))) for line in lines[1:]]
    return [r for r in rows if (r.get("adm3_pcode") or "").startswith("IQG")]


def alike(a: str, b: str) -> bool:
    return bool(a and b) and (a == b or SequenceMatcher(None, a, b).ratio() >= ALIKE)


def crosswalk(table: dict[str, Any], gazetteer: list[dict[str, str]]
              ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Each map district's census count, for the governorates that pass every check."""
    districts, names, ar_names = table["districts"], table["names"], table["ar_names"]
    by_gov: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    subs: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in gazetteer:
        by_gov[row["adm1_name"]].setdefault(row["adm2_name"], row)
        subs[row["adm1_name"]].append(row)

    def matches(code: str, candidates: dict[str, dict[str, str]]) -> list[str]:
        keys = {en_key(n) for n in names.get(code, {})}
        ak = ar_key(ar_names.get(code, ""))
        return [d for d, row in candidates.items()
                if any(alike(k, en_key(d)) for k in keys)
                or (ak and ak == ar_key(row.get("adm2_name1")))]

    # A census district that shares its name with a map district of another
    # governorate: that map district is counted in two places.
    split: set[tuple[str, str]] = set()
    for code in districts:
        home = GOVERNORATE.get(code[:2])
        for gov, candidates in by_gov.items():
            if gov != home:
                split.update((gov, d) for d in matches(code, candidates))

    out: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    for g2, gov in GOVERNORATE.items():
        candidates = by_gov.get(gov, {})
        placed: dict[str, str] = {}
        unplaced: list[str] = []
        for code in sorted(c for c in districts if c[:2] == g2):
            found = ([RENAMED[code]] if code in RENAMED and RENAMED[code] in candidates
                     else matches(code, candidates))
            if len(found) != 1:
                # A district made since out of a sub-district keeps its name:
                # placed where the gazetteer has that sub-district.
                keys = {en_key(n) for n in names.get(code, {})}
                ak = ar_key(ar_names.get(code, ""))
                found = sorted({r["adm2_name"] for r in subs[gov]
                                if any(alike(k, en_key(r["adm3_name"])) for k in keys)
                                or (ak and ak == ar_key(r.get("adm3_name1")))})
            if len(found) != 1:
                # Or by the sub-districts of it the gazetteer knows, when they
                # all lie in one map district.
                found = sorted({r["adm2_name"]
                                for n, (en, ar, _v) in table["nahiyas"].items()
                                if n[:4] == code
                                for r in subs[gov]
                                if alike(en_key(en), en_key(r["adm3_name"]))
                                or (ar_key(ar) and ar_key(ar) == ar_key(r.get("adm3_name1")))})
            if len(found) == 1:
                placed[code] = found[0]
            else:
                unplaced.append(names[code].most_common(1)[0][0] if names.get(code) else code)
        empty = [d for d in candidates if d not in placed.values()]
        wrong = []
        for code, (en, ar, _value) in table["nahiyas"].items():
            if code[:2] != g2 or code[:4] not in placed:
                continue
            homes = {r["adm2_name"] for r in subs[gov]
                     if alike(en_key(en), en_key(r["adm3_name"]))
                     or (ar_key(ar) and ar_key(ar) == ar_key(r.get("adm3_name1")))}
            if len(homes) == 1 and placed[code[:4]] not in homes:
                wrong.append(f"{en} in {homes.pop()}, not {placed[code[:4]]}")
        if unplaced or empty or wrong:
            why = "; ".join(filter(None, [
                unplaced and f"census districts not placed: {', '.join(unplaced)}",
                empty and f"map districts given none: {', '.join(empty)}",
                wrong and f"sub-districts elsewhere: {', '.join(wrong[:3])}"]))
            notes.append(f"{gov}: not written -- {why}")
            for district, row in candidates.items():
                out[f"{gov}/{district}"] = {
                    "governorate": gov, "district": district,
                    "arabic": row.get("adm2_name1"), "value": None,
                    "why": (f"The 2024 census counts {gov}'s districts on boundaries "
                            f"redrawn since the boundary file's"
                            + (f" ({', '.join(unplaced[:4])} among the districts made "
                               f"since)" if unplaced else "")
                            + (f", and has moved {', '.join(w.split(' in ')[0] for w in wrong[:2])} "
                               f"from one district to another" if wrong else "")
                            + ", so its figures cannot be put on these shapes. The "
                              "governorate's own count is on the governorate.")}
            continue
        members: dict[str, list[str]] = defaultdict(list)
        for code, district in placed.items():
            members[district].append(code)
        for district, codes in members.items():
            if (gov, district) in split:
                notes.append(f"{gov} {district}: counted partly in another governorate; "
                             f"left out")
                continue
            out[f"{gov}/{district}"] = {
                "governorate": gov, "district": district,
                "arabic": by_gov[gov][district].get("adm2_name1"),
                "value": sum(districts[c] for c in codes),
                "parts": [(names[c].most_common(1)[0][0] if names.get(c) else c,
                           districts[c]) for c in sorted(codes)],
            }
        notes.append(f"{gov}: {len(members)} districts from {len(placed)} census districts")
    return out, notes


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


def table_pages(text: str) -> list[str]:
    """The pages of Table 11/2: those whose header names a nahiya."""
    return [page for page in text.split(PAGE_BREAK) if "Nahiya" in page]


def build(text: str, gazetteer_text: str) -> list[dict[str, Any]]:
    table = parse(text)
    govs = table["governorates"]
    bad = {g: (v, table["sums"][g]) for g, v in govs.items() if table["sums"][g] != v}
    log(f"  {len(table['districts'])} districts, {len(govs)} governorates, "
        f"{len(table['nahiyas'])} sub-districts; governorates sum to "
        f"{sum(govs.values()):,} against the grand total {table['grand']:,}")
    if len(govs) != len(GOVERNORATE) or sum(govs.values()) != NATIONAL or bad:
        raise SystemExit(f"the table does not add up (governorates {sorted(govs)}, "
                         f"mismatched {bad}); nothing written")
    mapped, notes = crosswalk(table, read_gazetteer(gazetteer_text))
    for line in notes:
        log(f"  {line}")
    cite = [{"field": "population", "name": SOURCE, "url": URL}]
    rows = []
    for code, value in sorted(govs.items()):
        gov = GOVERNORATE[code]
        rows.append(record(f"IRQ-CEN-{code}", gov, level="admin1", parent="IRQ",
                           country="IRQ", population=measure(value, year=YEAR, source=SOURCE),
                           sources=cite))
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
                + " districts, made since the boundary file was drawn: "
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
        f"{len(rows) - len(govs) - written} with the reason they have none")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true", help="save the table and gazetteer")
    ap.add_argument("--offline", action="store_true", help="read the saved copies")
    args = ap.parse_args()
    if args.offline:
        text = DUMP.read_text(encoding="utf-8")
        gazetteer = GAZ_DUMP.read_text(encoding="utf-8")
    else:
        blob = fetch_blob(URL)
        log(f"  {URL}: {len(blob):,} bytes")
        text = PAGE_BREAK.join(table_pages(laid_out(blob)))
        gazetteer = "\n".join("\t".join(r) for r in gazetteer_rows(fetch_blob(GAZETTEER)))
        if args.dump:
            DUMP.parent.mkdir(parents=True, exist_ok=True)
            DUMP.write_text(text, encoding="utf-8")
            GAZ_DUMP.write_text(gazetteer, encoding="utf-8")
            log(f"  wrote {DUMP.relative_to(ROOT)} and {GAZ_DUMP.relative_to(ROOT)}")
            return 0
    write_json(OUT, build(text, gazetteer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
