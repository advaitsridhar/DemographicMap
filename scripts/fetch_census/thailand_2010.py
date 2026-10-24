#!/usr/bin/env python3
"""Thailand: religion and nationality by province, from the 2010 census's provincial reports.

The 2000 census is read for all of Thailand (``thailand``, ``thailand_nationality``)
and has no row for **Bueng Kan**, which was made from eight districts of Nong
Khai in March 2011. The 2010 Population and Housing Census was taken in
September 2010, and the National Statistical Office published a report for
each of the 77 provinces it had by then, Bueng Kan among them
(``popcensus.nso.go.th/report/<Province>_T.pdf``). The Office's hosts refuse
this project (``thailand``'s docstring has the evidence), and the Internet
Archive kept 75 of the reports; ``CAPTURES`` names each file and the capture
read. Lampang's and Suphan Buri's were not captured, and those two keep 2000.

**What is read.** Each report's section 1.5, "Religion and nationality",
prints a table of the province's people by religion and by nationality, in
percent, for the province and for its municipal and non-municipal areas; the
province's own column, the first, is read. Its rows are the faiths and the
nationalities the province has: Buddhist, Muslim, Christian and others; Thai
and the two or three nationalities the province counts most of (Lao along the
Mekong, Burmese and Cambodian in the south, Chinese in the north), and
others. A row printed "a" -- under 0.1% -- is left out. The table is found by
its two 100.0 rows, not by its number: Bangkok's report numbers its tables
differently.

**Every table is checked against the report's own key indicators**, the page
near the front that prints "Thai citizenship (%)" and "Buddhism (%)" for 2010.
They are the same counts and must print the same figures, and in one report
they do not: Nong Khai's nationality rows -- Thai 99.3, Burmese 0.4, Cambodian
0.3, in all three columns -- are Pattani's, word for word, where Nong Khai's
key indicators print Thai 99.4% and its text names the Lao. A table whose
Thai or Buddhist row disagrees with the key indicators is not used, and the
key indicators stand in its place: the Thai share and everyone else, as the
2000 reading does, and Buddhism with the other faiths the indicators print.

**Bueng Kan and Nong Khai.** The Office published the eight districts' count
as Bueng Kan's report and Nong Khai's report without them, so each figure is
for the province as it is drawn now; the two reports' populations are logged
beside each other to show it.

Usage:
    python -m scripts.fetch_census.thailand_2010
    python -m scripts.fetch_census.thailand_2010 --probe          # print, write nothing
    python -m scripts.fetch_census.thailand_2010 --only "Bueng Kan"
"""

from __future__ import annotations

import argparse
import io
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .sea_common import drawn, fold

OUT = "thailand_2010.json"
YEAR = 2010
LICENCE = "Open Government Data of Thailand (NSO publication)"
REPORTS = "http://popcensus.nso.go.th/report/"
SOURCE = ("National Statistical Office, 2010 Population and Housing Census, {province} "
          "report: section 1.5, people by religion and nationality (percent)")
INDICATORS = ("National Statistical Office, 2010 Population and Housing Census, {province} "
              "report: key indicators, 2010")
# Seconds between two reports fetched from the Archive, which asks to be read
# gently; a report already in the cache costs nothing and waits for nothing.
PAUSE = 3.0
# The pages searched for the table and the indicators; both sit in the first
# thirty of a report of two hundred, and reading the rest costs minutes each.
PAGES = 60

# Province, as the boundary file names it less "Province" -> (report, capture).
CAPTURES: dict[str, tuple[str, str]] = {
    "Amnat Charoen": ("AmnatCharoen_T.pdf", "20160303183316"),
    "Ang Thong": ("AngThong_T.pdf", "20160303174311"),
    "Bangkok": ("Bangkok_T.pdf", "20160303213735"),
    "Bueng Kan": ("BuengKan_T.pdf", "20160304023534"),
    "Buri Ram": ("BuriRam_T.pdf", "20160304023555"),
    "Chachoengsao": ("Chachoengsao_T.pdf", "20160303170110"),
    "Chai Nat": ("ChaiNat_T.pdf", "20160303171649"),
    "Chaiyaphum": ("Chaiyaphum_T.pdf", "20160303210740"),
    "Chanthaburi": ("Chanthaburi_T.pdf", "20160414135618"),
    "Chiang Mai": ("ChiangMai_T.pdf", "20160303193158"),
    "Chiang Rai": ("ChiangRai_T.pdf", "20160415115826"),
    "Chon Buri": ("ChonBuri_T.pdf", "20160303222803"),
    "Chumphon": ("Chumphon_T.pdf", "20160303181955"),
    "Kalasin": ("Kalasin_T.pdf", "20160415120008"),
    "Kamphaeng Phet": ("KamphaengPhet_T.pdf", "20160303174244"),
    "Kanchanaburi": ("Kanchanaburi_T.pdf", "20160303174322"),
    "Khon Kaen": ("KhonKaen_T.pdf", "20160303195950"),
    "Krabi": ("Krabi_T.pdf", "20160303180748"),
    "Lamphun": ("Lamphun_T.pdf", "20160303211634"),
    "Loei": ("Loei_T.pdf", "20160303211822"),
    "Lopburi": ("LopBuri_T.pdf", "20160303170314"),
    "Mae Hong Son": ("MaeHongSon_T.pdf", "20160303200858"),
    "Maha Sarakham": ("MahaSarakham_T.pdf", "20160303193417"),
    "Mukdahan": ("Mukdahan_T.pdf", "20160303174302"),
    "Nakhon Nayok": ("NakhonNayok_T.pdf", "20160303191538"),
    "Nakhon Pathom": ("NakhonPathom_T.pdf", "20160415070607"),
    "Nakhon Phanom": ("NakhonPhanom_T.pdf", "20160303180617"),
    "Nakhon Ratchasima": ("NakhonRatchasima_T.pdf", "20160303193338"),
    "Nakhon Sawan": ("NakhonSawan_T.pdf", "20160303195111"),
    "Nakhon Si Thammarat": ("NakhonSiThammarat_T.pdf", "20160415064644"),
    "Nan": ("Nan_T.pdf", "20160303184452"),
    "Narathiwat": ("Narathiwat_T.pdf", "20160303221229"),
    "Nong Bua Lam Phu": ("NongBuaLamPhu_T.pdf", "20160304191439"),
    "Nong Khai": ("NongKhai_T.pdf", "20160303180930"),
    "Nonthaburi": ("Nonthaburi_T.pdf", "20160415065002"),
    "Pathum Thani": ("PathumThani_T.pdf", "20160304190447"),
    "Pattani": ("Pattani_T.pdf", "20160415071025"),
    "Phangnga": ("Phangnga_T.pdf", "20160303204915"),
    "Phatthalung": ("Phatthalung_T.pdf", "20160414124504"),
    "Phayao": ("Phayao_T.pdf", "20160303185250"),
    "Phetchabun": ("Phetchabun_T.pdf", "20160414134225"),
    "Phetchaburi": ("Phetchaburi_T.pdf", "20160303211411"),
    "Phichit": ("Phichit_T.pdf", "20160303171959"),
    "Phitsanulok": ("Phitsanulok_T.pdf", "20160303182704"),
    "Phra Nakhon Si Ayutthaya": ("Ayutthaya_T.pdf", "20160303165808"),
    "Phrae": ("Phrae_T.pdf", "20160303210845"),
    "Phuket": ("Phuket_T.pdf", "20160303190029"),
    "Prachin Buri": ("PrachinBuri_T.pdf", "20160303174413"),
    "Prachuap Khiri Khan": ("Phachuap_T.pdf", "20160303171211"),
    "Ranong": ("Ranong_T.pdf", "20150514081846"),
    "Ratchaburi": ("Ratchaburi_T.pdf", "20160304023635"),
    "Rayong": ("Rayong_T.pdf", "20160304023654"),
    "Roi Et": ("RoiEt_T.pdf", "20160415064341"),
    "Sa Kaeo": ("SaKaeo_T.pdf", "20160303215742"),
    "Sakon Nakhon": ("SakonNakhon_T.pdf", "20160304192229"),
    "Samut Prakan": ("SamutPrakan_T.pdf", "20160414131740"),
    "Samut Sakhon": ("SamutSakhon_T.pdf", "20160303220634"),
    "Samut Songkhram": ("SamutSongkhram_T.pdf", "20160303181232"),
    "Saraburi": ("Saraburi_T.pdf", "20160415070957"),
    "Satun": ("Satun_T.pdf", "20160304192756"),
    "Si Sa Ket": ("SiSaKet_T.pdf", "20160303182914"),
    "Sing Buri": ("SingBuri_T.pdf", "20160304023757"),
    "Songkhla": ("Songkhla_T.pdf", "20160304023900"),
    "Sukhothai": ("Sukhothai_T.pdf", "20160414135717"),
    "Surat Thani": ("SuratThani_T.pdf", "20150925065914"),
    "Surin": ("Surin_T.pdf", "20160303193242"),
    "Tak": ("Tak_T.pdf", "20160303193433"),
    "Trang": ("Trang_T.pdf", "20160303212107"),
    "Trat": ("Trat_T.pdf", "20160303182403"),
    "Ubon Ratchathani": ("Ubonatchathani_T.pdf", "20160303203058"),
    "Udon Thani": ("UdonThani_T.pdf", "20160303181252"),
    "Uthai Thani": ("UthaiThani_T.pdf", "20160303200042"),
    "Uttaradit": ("Uttaradit_T.pdf", "20160304023920"),
    "Yala": ("Yala_T.pdf", "20160303194707"),
    "Yasothon": ("Yasothon_T.pdf", "20160303204205"),
}

# The table's rows, in the words the map uses. A row the table prints and
# these do not name stops the run: a new label is read, not guessed at.
RELIGIONS = {"พุทธ": "Buddhism", "อิสลาม": "Islam", "คริสต์": "Christianity",
             "ฮินดู": "Hinduism", "ซิกข์": "Sikhism", "ไม่มีศาสนา": "No religion",
             "อื่นๆ": "Other religions"}
NATIONALITIES = {"ไทย": "Thai", "ลาว": "Lao", "พม่า": "Burmese", "กัมพูชา": "Cambodian",
                 "จีน": "Chinese", "เวียดนาม": "Vietnamese", "อินเดีย": "Indian",
                 "มาเลเซีย": "Malaysian", "ญี่ปุ่น": "Japanese",
                 "อื่นๆ": "Other nationalities"}
# The key indicators' faiths, as they print them in English.
FAITHS = {"Buddhism": "Buddhism", "Muslims": "Islam", "Islam": "Islam",
          "Christianity": "Christianity", "Christian": "Christianity"}
RESIDUAL_FAITH = "Other or not stated"
RESIDUAL_NATIONALITY = "Foreign, stateless or unknown"

VALUE = r"(?:a|-|\d+\.\d)"
HEAD = re.compile(r"^\s*(ศาสนา|สัญชาติ)\S*\s+100\.0(?:\s+100\.0){0,2}\s*$")
ROW = re.compile(rf"^\s*(\D+?)\s+({VALUE})(?:\s+{VALUE}){{0,2}}\s*$")
# The table's footnote -- "a less than 0.1" -- and a "note:" line, which the row
# pattern would otherwise read as one more row.
FOOTNOTE = re.compile(r"น้อยกว่า|หมายเหตุ")
THAI = re.compile(r"(\d+\.\d)\s+Thai citizenship \(%\)")
NON_THAI = re.compile(r"(\d+\.\d)\s+Non[- ]Thai citizenship \(%\)")
FAITH = re.compile(r"(\d+\.\d)\s+(Buddhism|Muslims|Islam|Christianity|Christian) \(%\)")
POPULATION = re.compile(r"([\d,]{5,})\s+Total population")

NOTE_RELIGION = (
    "The 2010 Population and Housing Census, the province's report: the province's people "
    "by religion, in percent, as section 1.5 prints them. 'Other religions' is the table's "
    "own remainder, every faith it does not name. A faith the table prints as under 0.1% is "
    "left out.")
NOTE_NATIONALITY = (
    "Nationality, not ethnicity: Thailand's census does not ask ethnicity, and this is the "
    "2010 census's count of the province's people by nationality, in percent, as section 1.5 "
    "of the province's report prints it. 'Thai' names no one people: the Isan, Malay, Khmer, "
    "Kuy, hill peoples and Chinese who hold Thai nationality are all in it. 'Other "
    "nationalities' is the table's own remainder, and a nationality it prints as under 0.1% "
    "is left out.")
NOTE_FROM_INDICATORS = (
    "The 2010 Population and Housing Census, the province's report: the province's people "
    "by {what}, in percent, as its key indicators print them. The report's section 1.5 "
    "table does not agree with them -- it prints {row} {table}% where the key indicators "
    "print {printed}% -- so the key indicators' figures are shown.")
NOTE_INDICATOR_FAITHS = (
    " They name only the faiths shown; '{residual}' is what those leave of 100%.")
NOTE_INDICATOR_NATIONALITY = (
    " They print the share of Thai nationality alone; '{residual}' is everyone else: people "
    "of another nationality, of none, and anyone whose nationality was not recorded.")
NOTE_SPLIT = {
    "Bueng Kan": (" Bueng Kan was made from eight districts of Nong Khai in March 2011, six "
                  "months after the census was taken; the Office published those districts' "
                  "count as Bueng Kan's own report."),
    "Nong Khai": (" The Office published Nong Khai's count without the eight districts that "
                  "became Bueng Kan in 2011, so the figure is for the province as drawn."),
}


@dataclass
class Reading:
    """One report's religion and nationality, and what was checked."""
    province: str
    religion: list[dict[str, Any]] = field(default_factory=list)
    nationality: list[dict[str, Any]] = field(default_factory=list)
    religion_from: str = "table"
    nationality_from: str = "table"
    religion_note: str = ""
    nationality_note: str = ""
    population: int | None = None
    problems: list[str] = field(default_factory=list)
    raw: dict[str, list[tuple[str, list[str]]]] = field(default_factory=dict)


def text_lines(body: bytes, pages: int = PAGES) -> list[str]:
    """A report's text layer, line by line, as far as the page where both the
    table and the key indicators have been seen."""
    from pypdf import PdfReader                      # noqa: PLC0415 -- optional
    reader = PdfReader(io.BytesIO(body))
    lines: list[str] = []
    for page in reader.pages[:pages]:
        lines.extend((page.extract_text() or "").splitlines())
        if blocks(lines) and THAI.search("\n".join(lines)):
            break
    return lines


def label(text: str) -> str:
    """A row's label without the spaces a text layer scatters through Thai."""
    return re.sub(r"\s+", "", text)


def blocks(lines: list[str]) -> dict[str, list[tuple[str, list[str]]]]:
    """The religion and nationality rows of the first table that has both."""
    found: dict[str, list[tuple[str, list[str]]]] = {}
    current: str | None = None
    for line in lines:
        head = HEAD.match(line)
        if head:
            current = "religion" if head.group(1) == "ศาสนา" else "nationality"
            if current in found:                     # the table again, further on
                break
            found[current] = []
            continue
        if current is None:
            continue
        if not line.strip():
            continue
        row = None if FOOTNOTE.search(line) else ROW.match(line)
        if row is None:
            if "religion" in found and "nationality" in found:
                break
            current = None
            continue
        values = re.findall(VALUE, line[row.start(2):])
        found[current].append((label(row.group(1)), values))
    return found if "religion" in found and "nationality" in found else {}


def indicators(lines: list[str]) -> dict[str, Any]:
    """The key indicators' 2010 figures: the last number before each English label."""
    text = "\n".join(lines)
    out: dict[str, Any] = {"faiths": {}}
    if m := THAI.search(text):
        out["thai"] = m.group(1)
    if m := NON_THAI.search(text):
        out["non_thai"] = m.group(1)
    for value, faith in FAITH.findall(text):
        out["faiths"].setdefault(FAITHS[faith], value)
    if m := POPULATION.search(text):
        out["population"] = int(m.group(1).replace(",", ""))
    return out


def shares(rows: list[tuple[str, list[str]]], names: dict[str, str],
           problems: list[str], what: str) -> list[dict[str, Any]]:
    """The first column of a block's rows, in the map's words; "a" rows left out."""
    out: list[dict[str, Any]] = []
    for text, values in rows:
        group = names.get(text)
        if group is None:
            problems.append(f"{what} row {text!r} is not in the table of labels")
            continue
        first = values[0]
        if first in ("a", "-"):
            continue
        out.append({"group": group, "pct": float(first)})
    return out


def first(rows: list[dict[str, Any]], group: str) -> str | None:
    pct = next((r["pct"] for r in rows if r["group"] == group), None)
    return None if pct is None else f"{pct:.1f}"


def read(province: str, lines: list[str]) -> Reading:
    """A report's table, checked against its key indicators."""
    reading = Reading(province)
    table = blocks(lines)
    reading.raw = table
    key = indicators(lines)
    reading.population = key.get("population")
    if not table:
        reading.problems.append("no table with a religion and a nationality 100.0 row")
    religion = shares(table.get("religion", []), RELIGIONS, reading.problems, "religion")
    nationality = shares(table.get("nationality", []), NATIONALITIES, reading.problems,
                         "nationality")

    buddhism = key["faiths"].get("Buddhism")
    if religion and (buddhism is None or first(religion, "Buddhism") == buddhism):
        reading.religion, reading.religion_note = religion, NOTE_RELIGION
    elif buddhism is not None:
        reading.religion_from = "indicators"
        faiths = [{"group": g, "pct": float(v)} for g, v in key["faiths"].items()]
        left = round(100.0 - sum(f["pct"] for f in faiths), 1)
        if left > 0:
            faiths.append({"group": RESIDUAL_FAITH, "pct": left})
        reading.religion = faiths
        reading.religion_note = (NOTE_FROM_INDICATORS.format(
                                     what="religion", row="Buddhism",
                                     table=first(religion, "Buddhism"), printed=buddhism)
                                 + NOTE_INDICATOR_FAITHS.format(residual=RESIDUAL_FAITH))
    else:
        reading.problems.append("religion: neither a table nor key indicators")

    thai = key.get("thai")
    if nationality and (thai is None or first(nationality, "Thai") == thai):
        reading.nationality, reading.nationality_note = nationality, NOTE_NATIONALITY
    elif thai is not None:
        reading.nationality_from = "indicators"
        rows = [{"group": "Thai", "pct": float(thai)}]
        if float(thai) < 100.0:
            rows.append({"group": RESIDUAL_NATIONALITY, "pct": round(100.0 - float(thai), 1)})
        reading.nationality = rows
        reading.nationality_note = ("Nationality, not ethnicity: Thailand's census does "
                                    "not ask ethnicity. "
                                    + NOTE_FROM_INDICATORS.format(
                                        what="nationality", row="Thai nationality",
                                        table=first(nationality, "Thai"), printed=thai)
                                    + NOTE_INDICATOR_NATIONALITY.format(
                                        residual=RESIDUAL_NATIONALITY))
    else:
        reading.problems.append("nationality: neither a table nor key indicators")

    for what, rows in (("religion", reading.religion), ("nationality", reading.nationality)):
        total = sum(r["pct"] for r in rows)
        if rows and not 99.5 <= total <= 100.5:
            reading.problems.append(f"{what} adds to {total:.1f}")
    split = NOTE_SPLIT.get(province, "")
    reading.religion_note += split
    reading.nationality_note += split
    return reading


def copied(readings: list[Reading]) -> list[str]:
    """Tables printed word for word in two reports, every column alike."""
    seen: dict[tuple, str] = {}
    out = []
    for r in readings:
        for what in ("religion", "nationality"):
            rows = tuple((t, tuple(v)) for t, v in r.raw.get(what, []))
            if not rows:
                continue
            other = seen.setdefault((what, rows), r.province)
            if other != r.province:
                out.append(f"{what} table of {r.province} is {other}'s, word for word")
    return out


def build(readings: list[Reading], admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {fold(r.province): r for r in readings}
    out = []
    for shape in admin1:
        reading = by_name.get(fold(shape["name"].removesuffix(" Province")))
        if reading is None:
            continue
        file, capture = CAPTURES[reading.province]
        url = f"http://web.archive.org/web/{capture}/{REPORTS}{file}"
        sources, fields = [], {}
        for what, rows, note, frm in (("religion", reading.religion, reading.religion_note,
                                       reading.religion_from),
                                      ("ethnicity", reading.nationality,
                                       reading.nationality_note, reading.nationality_from)):
            if not rows:
                continue
            fields[what] = rows
            fields[f"{what}_year"] = YEAR
            fields[f"{what}_note"] = note
            name = (SOURCE if frm == "table" else INDICATORS).format(province=reading.province)
            sources.append({"field": what, "name": name, "url": url, "year": YEAR,
                            "license": LICENCE})
        if "ethnicity" in fields:
            fields["ethnicity_basis"] = "nationality"
        out.append(record(f"THA-CEN2010-{fold(reading.province)}", shape["name"],
                          level="admin1", parent="THA", country="THA", match_by="shape_id",
                          shape_id=shape["id"], sources=sources, **fields))
    drawn_names = {fold(s["name"].removesuffix(" Province")) for s in admin1}
    missing = sorted(r.province for r in readings if fold(r.province) not in drawn_names)
    if missing:
        raise SystemExit(f"thailand_2010: no polygon for {missing}")
    return out


def fetch(province: str) -> bytes:
    file, capture = CAPTURES[province]
    return http_get(f"http://web.archive.org/web/{capture}id_/{REPORTS}{file}",
                    binary=True, timeout=300)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="print every report's table and indicators; write nothing")
    ap.add_argument("--only", action="append", default=[], help="a province, repeatable")
    args = ap.parse_args()

    provinces = args.only or sorted(CAPTURES)
    unknown = [p for p in provinces if p not in CAPTURES]
    if unknown:
        raise SystemExit(f"thailand_2010: no report for {unknown}")
    log(f"thailand_2010: {len(provinces)} provincial reports of the 2010 census")
    readings = []
    for province in provinces:
        started = time.monotonic()
        lines = text_lines(fetch(province))
        reading = read(province, lines)
        readings.append(reading)
        log(f"  {province}: religion ({reading.religion_from}) "
            + ", ".join(f"{r['group']} {r['pct']}" for r in reading.religion)
            + f"; nationality ({reading.nationality_from}) "
            + ", ".join(f"{r['group']} {r['pct']}" for r in reading.nationality)
            + (f"; population {reading.population:,}" if reading.population else ""))
        for problem in reading.problems:
            log(f"    PROBLEM {problem}")
        if args.probe:
            for what, rows in reading.raw.items():
                log(f"    {what}: " + "; ".join(f"{t} {' '.join(v)}" for t, v in rows))
        if time.monotonic() - started > 1.0:
            time.sleep(PAUSE)                        # a fetch, not the cache
    for line in copied(readings):
        log(f"  copied: {line}")
    if args.probe:
        return 0
    problems = [f"{r.province}: {p}" for r in readings for p in r.problems]
    if problems:
        raise SystemExit("thailand_2010: " + "; ".join(problems))
    split = {r.province: r.population for r in readings if r.province in NOTE_SPLIT}
    if len(split) == 2:
        log(f"  Bueng Kan {split['Bueng Kan'] or '?'} and Nong Khai {split['Nong Khai'] or '?'} "
            "people in their 2010 reports")
    records = build(readings, drawn("THA", "admin1"))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records "
        f"({sum(r.religion_from == 'indicators' for r in readings)} religion and "
        f"{sum(r.nationality_from == 'indicators' for r in readings)} nationality from "
        "the key indicators)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
