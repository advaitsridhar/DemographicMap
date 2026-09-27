#!/usr/bin/env python3
"""The Caribbean's fields no census source fills, each with the reason it is empty.

The other Caribbean readers (jamaica_census, tto_census, guyana_census,
suriname_census, belize_census, bahamas_census, barbados_census,
lucia_census, grenada_census, vincent_census, antigua_census,
caribbean_uscb) write what the offices publish. This writes the rest as
gaps whose notes say what was read and what it holds -- a gap never
replaces a value, so a unit another reader fills keeps its figure.

Every reason below was measured, and each names where:

* **Language** is asked by no census here except Belize's and Suriname's
  (whose readers fill it): Jamaica's 2011 individual questionnaire, Trinidad
  and Tobago's 2011 questionnaire, Dominica's 2011 questionnaire, The
  Bahamas' 2010 individual questionnaire (as the First Release's preface lists
  its topics) have no language question; Barbados's full 2010 and 2021 table
  sets and Grenada's 2021 tables and 2011 report tabulate none.
* **Dominica** tabulates ethnic group and religion for the whole country only.
* **Saint Kitts and Nevis** publishes nothing by parish that could be read.
* **The Bahamas** tabulates by island, and the map splits five islands into
  districts; the second-level drawing has districts the census never counts.
* **Guyana's** language: nothing read says whether its census asks.
* **Redonda** is uninhabited.

Usage:
    python -m scripts.fetch_census.caribbean_gaps
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, log, record,
                      write_json)
from .bahamas_census import ISLANDS
from .binding import fold
from common import NOT_APPLICABLE  # noqa: E402  (on the path _shared sets)

OUT = PROCESSED / "caribbean_gaps.json"
SITE = PROCESSED.parent.parent / "site" / "data"
FIELDS = ("population", "median_age", "sex_ratio", "religion", "ethnicity", "language")

LANGUAGE = {
    "JAM": ("Jamaica's census asks no language question: STATIN's 2011 Individual "
            "Questionnaire (statinja.gov.jm, 4 pages) asks religion and ethnic origin and "
            "nothing on language."),
    "TTO": ("Trinidad and Tobago's census asks no language question: the CSO's 2011 "
            "questionnaire (21 pages) asks religion and ethnic group, and 'speak' appears only "
            "in its disability questions."),
    "DMA": ("Dominica's census asks no language question: the 2011 Population and Housing "
            "Census questionnaire (stats.gov.dm, 15 pages) asks ethnic group (Q44) and "
            "religion (Q45); 'language' appears only in its disability questions."),
    "BHS": ("The Bahamas' 2010 census asked no language question: the First Release's preface "
            "lists the individual questionnaire's topics -- age, sex, marital and union status, "
            "religion, racial group, citizenship and education -- and no island report "
            "tabulates language."),
    "BRB": ("Barbados's census tabulates no language: neither the 2021 census's table "
            "workbook (Census-2020-Tables.xlsx) nor the 2010 census's (Census-Tables-2010.xlsx) "
            "has a language table among their 156 sheets; 'speak' appears only among "
            "disabilities."),
    "GRD": ("Grenada's census tabulates no language: the 2021 preliminary results' 38 tables "
            "and the 2011 census report's 230 pages (stats.gov.gd) have no language table and "
            "no mention of language."),
    "KNA": None,  # set below, with the parish reason
    "GUY": ("Nothing read says whether Guyana's census asks a language question: the 2012 "
            "individual questionnaire the Bureau of Statistics posts (2012_Census_"
            "QuestionnaireForm-BIND.pdf, 12,158 bytes) is not a readable PDF, and neither the "
            "2012 compendia nor the 2022 preliminary report tabulates language."),
}
KITTS = ("Saint Kitts and Nevis publishes nothing below the country from its 2011 census that "
         "could be read: the Statistics Department's site (stats.gov.kn) holds a household "
         "listing form, a census FAQ, a 2021 census page and a national results infographic "
         "(census-2011-results-1.png); CELADE's REDATAM server has no Saint Kitts base "
         "(prod.redatam.org/binkna/RpWebEngine.exe/Portal answers 404), and the US Census "
         "Bureau's HDX series has no Saint Kitts workbook.")
LANGUAGE["KNA"] = KITTS
DOMINICA = ("Dominica's 2011 census report (stats.gov.dm, 2011 Population and Housing "
            "Census) tabulates ethnic group and religion for the whole country only (Tables 5 "
            "and 6, by age group and sex), and the US Census Bureau's Dominica workbook holds "
            "age and sex only.")
BAHAMAS_SPLIT = ("The Bahamas' 2010 census tabulates age, sex, religion and racial group by "
                 "island (one report an island); the map draws this island as several "
                 "districts, and an island's figures are none of them.")
BAHAMAS_UNCOUNTED = ("The Bahamas' 2010 census tabulates by island and, within the larger "
                     "islands, by its own supervisory districts; this unit of the map's "
                     "second-level drawing is neither, so nothing is written for it.")
REDONDA = "Redonda is uninhabited; the census counts no one there."


def units(iso: str, level: str) -> list[dict[str, Any]]:
    return json.loads((SITE / level / f"{iso}.units.json").read_text())


def gaps(iso: str, level: str, shape: dict, notes: dict[str, str], status: str = NOT_AVAILABLE
         ) -> dict[str, Any]:
    return record(f"{iso}-GAP-{level}-{shape['id']}", shape["name"], level=level, parent=iso,
                  country=iso, match_by="shape_id", shape_id=shape["id"],
                  **{field: gap(status, note) for field, note in notes.items()})


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    records = []
    for iso in ("JAM", "TTO", "DMA", "BRB", "GRD", "GUY"):
        for level in ("admin1", "admin2") if iso in ("JAM", "GUY") else ("admin1",):
            for shape in units(iso, level):
                notes = {"language": LANGUAGE[iso]}
                if iso == "DMA":
                    notes.update(religion=DOMINICA, ethnicity=DOMINICA)
                records.append(gaps(iso, level, shape, notes))
    for shape in units("KNA", "admin1"):
        records.append(gaps("KNA", "admin1", shape, {f: KITTS for f in FIELDS
                                                      if f != "population"}))
    whole1 = {fold(d) for d in ISLANDS}
    whole2 = {fold(u) for _, _, u in ISLANDS.values() if u}
    for level, whole in (("admin1", whole1), ("admin2", whole2)):
        for shape in units("BHS", level):
            notes = {"language": LANGUAGE["BHS"]}
            name = fold(shape["name"])
            if name not in whole:
                why = BAHAMAS_SPLIT if level == "admin1" else BAHAMAS_UNCOUNTED
                fields = ("median_age", "sex_ratio", "religion", "ethnicity")
                notes.update({f: why for f in fields + (("population",) if level == "admin2"
                                                        else ())})
            records.append(gaps("BHS", level, shape, notes))
    for shape in units("ATG", "admin1"):
        if fold(shape["name"]) == "redonda":
            records.append(gaps("ATG", "admin1", shape,
                                {f: REDONDA for f in FIELDS if f != "population"},
                                status=NOT_APPLICABLE))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} units' gaps with their reasons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
