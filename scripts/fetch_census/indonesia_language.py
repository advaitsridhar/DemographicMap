#!/usr/bin/env python3
"""Indonesia: first language by province and regency, 2020 census Long Form (a sample).

The full count of the 2020 census asked no language question; its Long Form,
which BPS carried out in 2022 on a sample of households in every kabupaten
and kota, asked each person aged five and over two: whether they can speak
Indonesian, and which language they spoke first. BPS tabulates the second in
*The Result of Long Form Population Census 2020* (2023), Table 6.3, in four
classes: Indonesian, a regional language (bahasa daerah), a foreign language,
and sign language. The US Census Bureau's "Subnational Population and Housing
Data Tables" for Indonesia on HDX (CC BY) carry that table for the country,
the 34 provinces and every regency (sheet ``Language``, columns
``LNG_1STIN``, ``LNG_1STRG``, ``LNG_1STFOR``, ``LNG_1STSGN``, beside
``LNG_YESIN``/``LNG_NOTIN`` for the ability question and the population aged
five and over).

**Why a survey file.** The Long Form is a sample, weighted by BPS to its
population for 2022, so its shares are estimates; and its four classes are
coarser than the map's language compositions elsewhere in Indonesia (CLEAR
Global's tabulation of the 2010 census names the regional languages). The
output is therefore ``indonesia_language_survey.json``, which the build reads
as a survey: it fills a province or regency no count has given a language,
and replaces none. Every record's ``language_basis`` begins "survey
estimate".

**Labels.** "Indonesian"; "Regional languages of Indonesia" for the regional
class, which takes in Austronesian and Papuan languages alike (Javanese and
Sundanese, but also Dani and Lani in the highlands and Ternate in North
Maluku) and so names no one family; "Foreign languages"; "Sign language".

**Binding** is the age reader's (``indonesia_age.bind``): a province to its
polygon, a regency to the polygon of its name inside its province, renamed
regencies by their earlier names; the Thousand Islands have no polygon and
Lake Toba's row is blank. A province's composition is its own row.

**Checks**, each a refusal: in every row the four first-language classes make
the population aged five and over, and so do the two ability classes; the
regencies make their province class by class, and the provinces the country,
whose population aged five and over must be 253,679,348. Every cell is a
weighted estimate rounded on its own, so a sum may miss by a person per
class or per part, and by no more (the log names the widest miss).

Usage:
    python -m scripts.fetch_census.indonesia_language
"""

from __future__ import annotations

import argparse
import io
from collections import Counter
from typing import Any

from . import indonesia_age as age, uscb
from ._shared import PROCESSED, http_get, log, record, shares, write_json
from .sea_common import drawn, fold

OUT = "indonesia_language_survey.json"
YEAR = 2022
SOURCE = ("BPS-Statistics Indonesia, The Result of Long Form Population Census 2020 (2023), "
          "Table 6.3: Population 5 Years of Age and Over by Age Group, First Language Spoken, "
          "and Sex, as the U.S. Census Bureau tabulates it for HDX")
NATIONAL_5PLUS = 253_679_348
FIRST = {"LNG_1STIN": "Indonesian", "LNG_1STRG": "Regional languages of Indonesia",
         "LNG_1STFOR": "Foreign languages", "LNG_1STSGN": "Sign language"}
ABLE = ("LNG_YESIN", "LNG_NOTIN")
BASIS = ("survey estimate: the 2020 census Long Form, a sample of households in every "
         "regency weighted to BPS's population for 2022; first language of people aged 5 and "
         "over")


def total_column(names: list[str], aliases: list[str]) -> str:
    """The column of everyone aged five and over: the sheet's 'Total population'."""
    found = [n for n, a in zip(names, aliases)
             if n.startswith("LNG_") and "population" in a.lower()]
    if len(found) != 1:
        raise SystemExit(f"indonesia_language: no single total column: {found}")
    return found[0]


def read_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Every row's level, names and first-language counts, its sums checked."""
    names, aliases = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    missing = [c for c in (*FIRST, *ABLE) if c not in at]
    if missing:
        raise SystemExit(f"indonesia_language: the Language sheet lacks {missing}")
    total = total_column(names, aliases)
    out = []
    for row in rows[2:]:
        level = uscb.number(row[at["ADM_LEVEL"]])
        if level is None:
            continue
        level = int(level)
        unit = {"level": level,
                "adm1": str(row[at["ADM1_NAME"]] or "").strip() if level >= 1 else "",
                "adm2": str(row[at["ADM2_NAME"]] or "").strip() if level >= 2 else "",
                "nso": str(row[at["NSO_NAME"]] or "").strip() if "NSO_NAME" in at else "",
                "code": str(row[at["NSO_CODE"]] or "").strip() if "NSO_CODE" in at else ""}
        where = unit["adm2"] or unit["adm1"] or "the country"
        cells = [row[at[c]] for c in (total, *FIRST, *ABLE)]
        if level == 2 and all(c is None or str(c).strip() == "" for c in cells):
            unit["groups"] = None          # Lake Toba: no figures at all
            out.append(unit)
            continue
        everyone = age.count(row[at[total]], f"{where} {total}")
        first = {label: age.count(row[at[c]], f"{where} {c}") for c, label in FIRST.items()}
        able = sum(age.count(row[at[c]], f"{where} {c}") for c in ABLE)
        # Each cell is a weighted estimate rounded on its own, so the classes
        # may miss the total by a person per class, and no more.
        if abs(sum(first.values()) - everyone) > len(FIRST) or abs(able - everyone) > len(ABLE):
            raise SystemExit(f"indonesia_language: {where}: first languages make "
                             f"{sum(first.values()):,} and the ability question {able:,}, "
                             f"against {everyone:,} aged five and over")
        unit["groups"] = first
        unit["total"] = everyone
        out.append(unit)
    return out


def check_sums(rows: list[dict[str, Any]]) -> None:
    country = [r for r in rows if r["level"] == 0]
    provinces = [r for r in rows if r["level"] == 1]
    regencies = [r for r in rows if r["level"] == 2 and r["groups"] is not None]
    blank = [r["adm2"] for r in rows if r["level"] == 2 and r["groups"] is None]
    if any(age.key(n) not in age.NOT_REGENCIES for n in blank):
        raise SystemExit(f"indonesia_language: rows with no figures that are not water: {blank}")
    if len(country) != 1 or country[0]["total"] != NATIONAL_5PLUS:
        raise SystemExit(f"indonesia_language: the country's row is not {NATIONAL_5PLUS:,} "
                         f"people aged five and over")

    def add(parts: list[dict[str, Any]]) -> Counter:
        c: Counter = Counter()
        for p in parts:
            c.update(p["groups"])
        return c

    # Rounded estimates summed: a part may carry half a person's rounding
    # each way, so a whole may miss its parts' sum by up to one person per
    # part, and a wider miss is a misread.
    worst = (0, "")
    for whole, parts, what in (
            [(country[0], provinces, "the provinces")]
            + [(p, [r for r in regencies if fold(r["adm1"]) == fold(p["adm1"])],
                f"{p['adm1']}'s regencies") for p in provinces]):
        if not parts:
            raise SystemExit(f"indonesia_language: {what}: none")
        made = add(parts)
        for label in FIRST.values():
            miss = abs(made[label] - whole["groups"][label])
            if miss > len(parts):
                raise SystemExit(f"indonesia_language: {what} make {made[label]:,} for "
                                 f"{label}, against {whole['groups'][label]:,} for "
                                 f"{whole['adm1'] or 'the country'}")
            worst = max(worst, (miss, f"{label} in {whole['adm1'] or 'the country'}"))
    log(f"  {len(regencies)} regencies make their {len(provinces)} provinces and the provinces "
        f"the country's {NATIONAL_5PLUS:,} aged five and over, class by class (the widest "
        f"rounding miss {worst[0]} people, {worst[1]})")


def fields(row: dict[str, Any], whose: str) -> dict[str, Any]:
    regional = row["groups"]["Regional languages of Indonesia"]
    return {
        "language": shares(row["groups"]),
        "language_year": YEAR,
        "language_basis": BASIS,
        "language_note": (
            f"First language spoken, people aged 5 and over in {whose} ({row['total']:,} "
            f"weighted), from BPS's Long Form of the 2020 census, carried out in 2022 on a "
            f"sample of households in every regency and weighted to BPS's population for 2022 "
            f"(Table 6.3 of its 2023 results, as the US Census Bureau tabulates it; the "
            f"Bureau's dictionary dates the field to the census day, 15 September 2020). BPS "
            f"publishes four classes and does not name the regional languages: \"Regional "
            f"languages of Indonesia\" ({regional:,}) takes in every bahasa daerah, Austronesian "
            f"and Papuan alike. The table publishes weighted estimates only, not the number of "
            f"people sampled. The 2020 census's full count asked no language question."),
    }


def build(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    check_sums(rows)
    bound, regions = age.bind(rows, admin1, admin2)
    cite = {"field": "language", "name": SOURCE, "url": uscb.dataset_url(age.DATASET),
            "year": YEAR, "license": age.LICENCE}
    shapes = {s["id"]: s for s in admin2}
    out = []
    for sid, r in sorted(bound.items(), key=lambda kv: shapes[kv[0]]["name"]):
        whose = (r["nso"] or r["adm2"]).title()
        out.append(record(f"IDN-LF-LANG-{r['code'] or age.key(r['adm2'])}", shapes[sid]["name"],
                          level="admin2", parent="IDN", country="IDN", match_by="shape_id",
                          shape_id=sid, sources=[cite], **fields(r, whose)))
    for pid, prov in sorted(regions.items(), key=lambda kv: kv[1]["adm1"]):
        region = next(u for u in admin1 if u["id"] == pid)
        out.append(record(f"IDN-LF-LANG-{prov['code'] or fold(prov['adm1'])}", region["name"],
                          level="admin1", parent="IDN", country="IDN", match_by="shape_id",
                          shape_id=pid, sources=[cite],
                          **fields(prov, f"the province of {prov['adm1'].title()}")))
    for level in ("admin1", "admin2"):
        share = sorted(next(g["pct"] for g in r["language"] if g["group"] == "Indonesian")
                       for r in out if r["level"] == level)
        log(f"  {level}: {sum(1 for r in out if r['level'] == level)} units; Indonesian first "
            f"{share[0]}%-{share[-1]}%, median {share[len(share) // 2]}%")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl
    log(f"indonesia_language: {SOURCE}")
    url = uscb.workbook_url(age.DATASET)
    log(f"  {url}")
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    rows = read_rows(uscb.sheet_rows(book, "Language"))
    book.close()
    records = build(rows, drawn("IDN", "admin1"), drawn("IDN", "admin2"))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
