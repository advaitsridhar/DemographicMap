#!/usr/bin/env python3
"""Mauritania -- the 2023 census (RGPH 2023) by wilaya and moughataa.

ANSADE's leaflet of the census's first results, *Population des Wilayas,
Moughataa et Communes* (2024), prints everyone by sex for the 15 wilayas, the
63 moughataas and every commune: 4,927,532 people counted between 25 December
2023 and 8 January 2024. ansade.mr does not answer an automated client; the
leaflet is read from the copy the Centre Rachad publishes.

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
per 1,000 women), 2023. The leaflet gives no ages: each moughataa says so.

**Checks before anything is written.** Every row's men and women make its
total; each moughataa's communes make it; each wilaya's moughataas make the
wilaya's total row and the first page's table; the wilayas make 4,927,532.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob, laid_out  # noqa: E402

URL = "https://centre-rachad.org/wp-content/uploads/2024/10/Depliant-RGPH5_vf.pdf"
SOURCE = ("Agence Nationale de la Statistique et de l'Analyse Démographique et Economique "
          "(ANSADE), Recensement Général de la Population et de l'Habitat (RGPH 2023), "
          "Population des Wilayas, Moughataa et Communes (2024)")
LICENCE = "ANSADE publication (reuse with attribution)"
YEAR = 2023
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
NO_AGES = ("The 2023 census's results published so far give each moughataa's population by "
           "sex, not by age.")
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


def fields(figures: tuple[int, int, int], note: str, ages_noted: bool = False
           ) -> dict[str, Any]:
    """A unit's count and sex ratio, cited to the leaflet -- and its median-age
    reason, which quotes the leaflet, where the unit carries one."""
    men, women, total = figures
    return {"population": measure(total, year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "sources": [{"field": "population/sex_ratio"
                         + ("/median_age note" if ages_noted else ""), "name": SOURCE,
                         "url": URL, "license": LICENCE, "year": YEAR}]}


def added(*parts: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(sum(p[k] for p in parts) for k in range(3))


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
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
        seat = {}
        if wilaya == "Nouakchott":
            seat["capital"] = gap(NOT_AVAILABLE, (
                "The polygon is the city of Nouakchott, three wilayas since 2014 "
                "(Nouakchott-Ouest, Nouakchott-Nord and Nouakchott-Sud), each with a seat of "
                "its own."))
        records.append(record(f"MRT-RGPH2023-{fold(wilaya)}", shape["name"], level="admin1",
                              parent="MRT", country="MRT", match_by="shape_id",
                              shape_id=shape["id"], **seat, **fields(figures, note)))
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
                sources=[{"field": "population note/sex_ratio note/median_age note",
                          "name": SOURCE, "url": URL, "license": LICENCE, "year": YEAR},
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
    blob = fetch_blob(URL)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"mauritania_census: {URL} is not a PDF: {blob[:60]!r}")
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    text = laid_out(blob)
    table = parse(text)
    for wilaya in WILAYAS:
        log(f"  {wilaya}: {table['wilayas'][wilaya][2]:,}; "
            + ", ".join(f"{m['name']} {m['figures'][2]:,}"
                        for m in table["moughataas"][wilaya].values()))
    admin1 = json.loads((SITE / "admin1" / "MRT.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "MRT.units.json").read_text())
    records, report = build(table, admin1, admin2)
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
