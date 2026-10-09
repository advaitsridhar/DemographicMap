#!/usr/bin/env python3
"""Thailand: people of Thai nationality and everyone else, by province, 2000 census.

Thailand's census does not ask ethnicity; it asks nationality. Under the
owner's rule of 19 September 2026 a census's nationality count stands where
ethnicity is not counted, published under ``ethnicity_basis: "nationality"``
-- Japan's and Korea's nationality files are the model, Timor-Leste's
(``timor_nationality``) the nearest -- and this file does that for the 76
provinces of 2000.

**The source.** The 2000 Population and Housing Census published a final
report for each province (``web.nso.go.th/pop2000/finalrep/``, gone from the
Office's host and kept by the Internet Archive; ``PRINTED`` names each file
and capture). Page 1 of each is "Key indicators of the population and
households, Population and Housing Census 1990 and 2000", and its row "Thai
nationality (%)" is the share of the province's people of Thai nationality in
2000 -- the row's other column is the 1970 census's, as its footnote says, and
is not read. "Foreign, stateless or unknown" is the rest, 100 less that share:
people of another nationality, people of none -- in 2000 many hill people of
the northern provinces, born in Thailand, held no nationality -- and anyone
whose nationality was not recorded.

**How it was read.** The reports' text layer is font-encoded -- a PDF reader
gets glyph numbers, not digits (probe 47ef4ad) -- and only three provinces'
workbooks were archived. So the rows were read off the page:
``sea_probe strips`` rendered page 1 of every archived report on the runner
(9789a13 and 0e94189; 3068cd8 again at 150 dpi for the eleven whose rows sit
one higher or lower, and for Amnat Charoen and Nong Bua Lam Phu, which print
2000 alone) and cut out the title and the 2000 column's rows "Total
population ('000)", "Thai nationality (%)" and "Buddhism (%)" with their
English labels, and the three numbers are written in ``PRINTED`` as printed.
Read against other readings of the same cells: Table 1 (below) gives 75 of
the 76 populations to the printed rounding and Phuket's within its last digit
(249.5 printed, 249,446 counted); Ranong's archived workbook (``ranong1.xls``,
sheet "indicators") prints 93.4; and the Wikipedia article "Nationality,
religion, and language data for the provinces of Thailand", which transcribes
the same rows from the same reports (a second reading, not a source; compared
once, by hand), agrees on 75 of the 76 nationality shares -- it has
Sukhothai's two rows the wrong way round, 99.6 and 99.8 where the page prints
99.8 Thai nationality and 99.6 Buddhism, which ``thailand`` now corrects.

**Checks**, each a refusal, run every time:

* the 2000 census's own Table 1 by province (``TABLE1``, an HTML table the
  Office published and the Internet Archive kept) gives every province's
  population: each report's "Total population ('000)" as written here must be
  that count in thousands within one in the last digit -- which ties every
  row read to its province -- and the provinces must make the kingdom's
  60,916,441;
* each report's "Buddhism (%)" as written here must be the 2000 Buddhist share
  ``thailand_province.json`` carries for the province -- the same row of the
  same report, read by other hands;
* every province of 2000 once, every polygon but Bueng Kan bound, and a share
  of Thai nationals between 50 and 100.

**Bueng Kan** was carved out of Nong Khai in 2011, so the 2000 census has no
row for it and it says so; **Nong Khai**'s figure is the province as it was in
2000, Bueng Kan included, and its note says that too.

The labels are "Thai" -- the nationality, which names no one people: the
Isan, the Malay-speaking south, the Khmer, Kuy and hill peoples who hold it
are all in it -- and "Foreign, stateless or unknown", both placed in the group
tree (the second beside "Foreign", among the answers that name no ancestry).
It replaces "Foreign nationals", which said nothing of the people of no
nationality the residual holds.

Usage:
    python -m scripts.fetch_census.thailand_nationality
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, write_json
from .sea_common import drawn, fold, html_rows

OUT = "thailand_nationality.json"
YEAR = 2000
KINGDOM = 60_916_441
LICENCE = "Open Government Data of Thailand (NSO publication)"
LABELS = ("Thai", "Foreign, stateless or unknown")
REPORTS = "http://web.nso.go.th/pop2000/finalrep/"
SOURCE = ("National Statistical Office, 2000 Population and Housing Census, {province} "
          "final report: key indicators of the population and households (page 1), "
          "row 'Thai nationality (%)'")
TABLE1 = ("http://web.archive.org/web/20060209030103id_/"
          "http://web.nso.go.th:80/pop2000/indiregion/wholetab1.htm")
RELIGION = PROCESSED / "thailand_province.json"
# How far a report's "Total population ('000)" may sit from Table 1's count, in
# thousands: one in the last printed digit. Phuket's report prints 249.5 and
# Table 1 counts 249,446; no two provinces are within a hundred people.
POPULATION_SLACK = 0.1
NEW = {"Bueng Kan": "Nong Khai"}                  # carved out since 2000 -> from

# Province, as the boundary file names it less "Province" -> (report, capture,
# "Total population ('000)", "Thai nationality (%)", "Buddhism (%)"), the
# three as page 1 prints them in the 2000 column.
PRINTED: dict[str, tuple[str, str, float, float, float]] = {
    "Amnat Charoen": ("amnatchafn.pdf", "20210420233828", 359.4, 99.8, 98.8),
    "Ang Thong": ("angthongfn.pdf", "20210420233925", 269.4, 99.8, 98.1),
    "Bangkok": ("bangkok1.pdf", "20061231140920", 6355.1, 99.0, 94.5),
    "Buri Ram": ("burirumfn1.pdf", "20170308141834", 1493.4, 99.8, 99.4),
    "Chachoengsao": ("chacheongfn.pdf", "20210420233824", 635.2, 99.8, 92.7),
    "Chai Nat": ("chainatfn.pdf", "20210420233916", 359.8, 99.8, 99.5),
    "Chaiyaphum": ("chaiphumfn.pdf", "20210420233827", 1095.4, 99.9, 99.4),
    "Chanthaburi": ("chanburifn.pdf", "20170308140242", 480.1, 99.8, 97.9),
    "Chiang Mai": ("cheingmaifn.pdf", "20160306141633", 1500.1, 96.6, 92.2),
    "Chiang Rai": ("cheingraifn.pdf", "20210420233835", 1129.7, 92.0, 90.6),
    "Chon Buri": ("chonburifn.pdf", "20210420233815", 1040.9, 99.4, 96.9),
    "Chumphon": ("chumphonfn.pdf", "20210420233813", 446.2, 99.2, 98.9),
    "Kalasin": ("kalasinfn.pdf", "20210420233818", 921.4, 99.8, 99.5),
    "Kamphaeng Phet": ("kampangfn.pdf", "20210420233814", 674.0, 99.8, 99.0),
    "Kanchanaburi": ("kanchanafn.pdf", "20210420233812", 734.4, 96.0, 99.0),
    "Khon Kaen": ("khonkhaen.pdf", "20210420233834", 1733.4, 99.8, 99.4),
    "Krabi": ("krabifn.pdf", "20210420233830", 336.2, 99.8, 65.2),
    "Lampang": ("lampangfn.pdf", "20210420233816", 782.2, 99.8, 98.7),
    "Lamphun": ("lamphunfn.pdf", "20210420233922", 413.3, 99.8, 99.5),
    "Loei": ("loeifn.pdf", "20210420233839", 607.1, 99.4, 99.4),
    "Lopburi": ("lopburifn.pdf", "20210420233833", 745.5, 99.8, 99.5),
    "Mae Hong Son": ("maehongfn.pdf", "20210420233910", 210.5, 94.0, 74.9),
    "Maha Sarakham": ("mahakamfn.pdf", "20170308140609", 947.3, 99.9, 99.8),
    "Mukdahan": ("mukdafn.pdf", "20210420233838", 310.7, 99.2, 98.8),
    "Nakhon Nayok": ("nkhonnayokfn.pdf", "20210420233849", 241.1, 99.8, 93.5),
    "Nakhon Pathom": ("nkpathomfn.pdf", "20210420233900", 815.1, 99.8, 98.8),
    "Nakhon Phanom": ("nkphanomfn.pdf", "20210420233858", 684.4, 99.5, 98.9),
    "Nakhon Ratchasima": ("nksimafn.pdf", "20210420233857", 2556.3, 99.8, 99.1),
    "Nakhon Sawan": ("nksawanfn.pdf", "20210420233819", 1090.4, 99.4, 99.2),
    "Nakhon Si Thammarat": ("nksritamfn.pdf", "20210420233836", 1519.8, 99.9, 93.1),
    "Nan": ("nanfn.pdf", "20210420233825", 458.0, 99.7, 95.8),
    "Narathiwat": ("narathifn.pdf", "20120201004755", 662.4, 99.8, 17.9),
    "Nong Bua Lam Phu": ("nongbuafn1.pdf", "20210420233929", 482.2, 99.9, 99.9),
    "Nong Khai": ("nongkaifn.pdf", "20210420233836", 883.7, 99.5, 99.1),
    "Nonthaburi": ("nonburifn.pdf", "20210420233904", 816.6, 99.6, 95.2),
    "Pathum Thani": ("pathumfn.pdf", "20210420233831", 677.6, 99.7, 96.3),
    "Pattani": ("pattanifn.pdf", "20210420233843", 596.0, 99.9, 19.2),
    "Phangnga": ("phangngafn.pdf", "20210420233824", 234.2, 97.8, 76.3),
    "Phatthalung": ("phatlungfn.pdf", "20161216132148", 498.5, 99.9, 88.3),
    "Phayao": ("payaofn.pdf", "20210420233822", 502.8, 99.6, 97.9),
    "Phetchabun": ("phetchafn.pdf", "20210420233854", 965.8, 99.8, 99.1),
    "Phetchaburi": ("phetchafn1.pdf", "20070306103715", 435.4, 99.7, 97.1),
    "Phichit": ("phichitfn.pdf", "20210420233833", 573.0, 99.9, 99.2),
    "Phitsanulok": ("phitnulokfn.pdf", "20210420233826", 792.7, 99.8, 99.3),
    "Phra Nakhon Si Ayutthaya": ("ayuthayafn.pdf", "20210420233919", 727.3, 99.8, 94.3),
    "Phrae": ("phraefn.pdf", "20210420233851", 492.6, 99.9, 99.0),
    "Phuket": ("phuketfn.pdf", "20210420233842", 249.5, 98.5, 81.6),
    "Prachin Buri": ("prachinfn.pdf", "20210420233901", 406.7, 99.8, 98.8),
    "Prachuap Khiri Khan": ("prachaupfn.pdf", "20210420233831", 449.5, 99.3, 98.3),
    "Ranong": ("ranongfn.pdf", "20210420233828", 161.2, 93.4, 88.5),
    "Ratchaburi": ("ratchaburifn.pdf", "20210420233816", 791.2, 99.3, 98.3),
    "Rayong": ("rayongfn.pdf", "20210420233845", 522.1, 99.7, 98.4),
    "Roi Et": ("roietfn.pdf", "20170308142330", 1256.5, 99.9, 99.4),
    "Sa Kaeo": ("sakaeofn.pdf", "20170308144148", 485.6, 99.7, 99.4),
    "Sakon Nakhon": ("sakonfn.pdf", "20210420233813", 1040.8, 99.8, 96.8),
    "Samut Prakan": ("smprakanfn.pdf", "20210420233904", 1028.4, 99.8, 97.7),
    "Samut Sakhon": ("sakhonfn.pdf", "20210420233839", 466.3, 99.0, 98.9),
    "Samut Songkhram": ("smsongkmfn.pdf", "20210420233907", 204.2, 99.6, 98.3),
    "Saraburi": ("sraburifn.pdf", "20210420233840", 575.1, 99.6, 97.7),
    "Satun": ("stunfn.pdf", "20210420233932", 247.9, 99.9, 31.9),
    "Si Sa Ket": ("srisaketfn.pdf", "20110615044703", 1405.5, 99.9, 99.4),
    "Sing Buri": ("singburifn.pdf", "20210420233821", 232.8, 99.8, 99.2),
    "Songkhla": ("songkhlafn.pdf", "20210420233837", 1255.7, 99.8, 76.6),
    "Sukhothai": ("sukhofn.pdf", "20210420233846", 593.3, 99.8, 99.6),
    "Suphan Buri": ("suphanfn.pdf", "20210420233840", 855.9, 99.8, 99.2),
    "Surat Thani": ("suratfn.pdf", "20210420233855", 869.4, 99.7, 97.3),
    "Surin": ("surinfn.pdf", "20110615044613", 1327.9, 99.5, 99.3),
    "Tak": ("takfn.pdf", "20210420233843", 486.1, 93.3, 95.1),
    "Trang": ("trangfn.pdf", "20210420233819", 595.1, 99.8, 86.0),
    "Trat": ("tradfn.pdf", "20210420233913", 219.3, 97.0, 97.0),
    "Ubon Ratchathani": ("ubonfn.pdf", "20170308215744", 1691.4, 99.7, 99.4),
    "Udon Thani": ("udonfn.pdf", "20210420233822", 1467.2, 99.8, 99.4),
    "Uthai Thani": ("uthaifn.pdf", "20210420233830", 304.1, 99.9, 99.6),
    "Uttaradit": ("uttraditfn.pdf", "20210420233848", 464.5, 99.7, 99.2),
    "Yala": ("yalafn.pdf", "20120201004740", 415.5, 99.8, 31.0),
    "Yasothon": ("yasothonfn.pdf", "20210420233907", 561.4, 99.9, 98.7),
}

# Table 1's spelling where it is not the boundary file's.
TABLE1_NAMES = {"Bangkok Metropolis": "Bangkok", "Lop Buri": "Lopburi",
                "Narathiwat'": "Narathiwat"}

NOTE = ("Nationality, not ethnicity: Thailand's census does not ask ethnicity, and this is "
        "the 2000 census's share of the province's people of Thai nationality, as the "
        "province's final report prints it in its key indicators. 'Foreign, stateless or "
        "unknown' is everyone else, 100 less that share: people of another nationality, "
        "people of none -- in 2000 many hill people of the northern provinces, born in "
        "Thailand, held no nationality -- and anyone whose nationality was not recorded. "
        "It is shown on this field because the census counts nationality and asks no "
        "ethnicity. 'Thai' names no one people: the Isan, Malay, Khmer, Kuy, hill peoples "
        "and Chinese who hold Thai nationality are all in it.")
GAP_NEW = ("Bueng Kan was carved out of Nong Khai in 2011; the 2000 census has no figure of "
           "its own for it, and Nong Khai's covers both.")


def table1(body: bytes) -> dict[str, int]:
    """Table 1's population of every province, checked against the kingdom's."""
    counts: dict[str, int] = {}
    kingdom = None
    for rows in html_rows(body):
        for row in rows:
            if len(row) < 2:
                continue
            label = " ".join(row[0].split())
            number = row[1].replace(",", "").strip()
            if not number.isdigit():
                continue
            if label == "Total" and kingdom is None:
                kingdom = int(number)
            name = TABLE1_NAMES.get(label, label)
            if name in PRINTED:
                if name in counts:
                    raise SystemExit(f"thailand_nationality: Table 1 has {name} twice")
                counts[name] = int(number)
    missing = sorted(set(PRINTED) - set(counts))
    if missing:
        raise SystemExit(f"thailand_nationality: Table 1 has no row for {missing}")
    if kingdom != KINGDOM or sum(counts.values()) != KINGDOM:
        raise SystemExit(f"thailand_nationality: Table 1's provinces make "
                         f"{sum(counts.values()):,} and its total is {kingdom}, against "
                         f"{KINGDOM:,}")
    return counts


def buddhists(path: Any = RELIGION) -> dict[str, float]:
    """thailand_province.json's 2000 Buddhist share by province, under every name it has."""
    out: dict[str, float] = {}
    for r in json.loads(path.read_text()):
        share = {g["group"]: g["pct"] for g in r.get("religion") or []
                 if isinstance(g, dict)}.get("Buddhism")
        if share is None:
            continue
        for name in [r["name"], *(r.get("aliases") or [])]:
            out[fold(name.removesuffix(" Province"))] = share
    return out


def check(counts: dict[str, int], buddhist: dict[str, float]) -> None:
    """Every row written here against Table 1's count and the other reading of Buddhism."""
    wrong = []
    for name, (_, _, thousands, thai, buddhism) in PRINTED.items():
        if abs(counts[name] / 1000 - thousands) > POPULATION_SLACK:
            wrong.append(f"{name}: population {thousands} written, Table 1 {counts[name]:,}")
        elif round(counts[name] / 1000, 1) != thousands:
            log(f"  {name}: the report prints {thousands} thousand, Table 1 counts "
                f"{counts[name]:,}")
        other = buddhist.get(fold(name))
        if other is not None and other != buddhism:
            wrong.append(f"{name}: Buddhism {buddhism} written, thailand_province {other}")
        if not 50.0 <= thai <= 100.0:
            wrong.append(f"{name}: Thai nationality {thai}")
    if wrong:
        raise SystemExit("thailand_nationality: " + "; ".join(wrong))


def build(admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for shape in admin1:
        name = shape["name"].removesuffix(" Province")
        key = next((k for k in [*PRINTED, *NEW] if fold(k) == fold(name)), None)
        if key is None:
            raise SystemExit(f"thailand_nationality: no report for {shape['name']!r}")
        seen.add(key)
        common = dict(level="admin1", parent="THA", country="THA", match_by="shape_id",
                      shape_id=shape["id"])
        if key in NEW:
            out.append(record(f"THA-NAT2000-{fold(key)}", shape["name"], **common,
                              ethnicity=gap(NOT_AVAILABLE, GAP_NEW)))
            continue
        report, capture, _, thai, _ = PRINTED[key]
        note = NOTE
        if key in NEW.values():
            note += (f" The figure is {key}'s as it was in 2000, "
                     f"{', '.join(k for k, v in NEW.items() if v == key)} included, which "
                     f"was carved out of it in 2011 and is drawn apart.")
        shares = [{"group": LABELS[0], "pct": thai}]
        if thai < 100.0:
            shares.append({"group": LABELS[1], "pct": round(100.0 - thai, 1)})
        src = [{"field": "ethnicity", "name": SOURCE.format(province=key),
                "url": f"http://web.archive.org/web/{capture}/{REPORTS}{report}",
                "year": YEAR, "license": LICENCE}]
        out.append(record(f"THA-NAT2000-{fold(key)}", shape["name"], **common, sources=src,
                          ethnicity=shares, ethnicity_year=YEAR,
                          ethnicity_basis="nationality", ethnicity_note=note))
    missing = sorted(set(PRINTED) - seen)
    if missing:
        raise SystemExit(f"thailand_nationality: no polygon for {missing}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("thailand_nationality: 2000 census, provincial final reports' key indicators")
    counts = table1(http_get(TABLE1, binary=True))
    log(f"  Table 1: {len(counts)} provinces making the kingdom's {KINGDOM:,}")
    check(counts, buddhists())
    log(f"  {len(PRINTED)} reports' populations agree with Table 1 and their Buddhist "
        f"shares with thailand_province.json")
    thai = sum(counts[n] * PRINTED[n][3] for n in PRINTED) / sum(counts.values())
    log(f"  the provinces weighted by Table 1: {thai:.2f}% of Thai nationality")
    records = build(drawn("THA", "admin1"))
    for r in records:
        if isinstance(r["ethnicity"], list):
            log(f"    {r['name']:32} " + ", ".join(f"{g['group']} {g['pct']}"
                                                   for g in r["ethnicity"]))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
