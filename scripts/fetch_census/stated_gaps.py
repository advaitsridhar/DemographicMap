#!/usr/bin/env python3
"""Stated reasons for polygons whose fields are empty for a reason no source states.

Each polygon below is empty for a reason that was measured or read, not for
want of looking: a town drawn inside the territory that counts it, a piece of
ground on a disputed line, a district a language tabulation has no row for.
The panel otherwise says only that nothing was found. Each record here says
what is true instead, on the fields it concerns, and gives way to any figure
a source writes.

Every declaration names its polygon by id and by the name it is drawn under,
and most carry a premise checked against the files read for the neighbouring
polygons (a language tabulation that still has no row for the district, a
survey that still places no respondent there). A polygon no longer drawn, or
a premise no longer true, leaves its record out and says so in the log, so a
reason never outlives what made it true.

Measured on the CGAZ polygons, 10 October 2026:

* The seven DRC towns are enclaves: Tshimbulu (19.5 km2) shares its whole
  17.8 km edge with Dibaya, Lukalaba (6.3 km2) its 10.3 km with Tshilenge,
  Dingila (10.1 km2) 13.0 km with Bambesa, Kasaji (7.8 km2) 11.4 km with
  Dilolo, Kaoze (10.2 km2) 13.0 km with Moba, Yangambi (25.7 km2) 20.9 km
  with Isangi; Nioki (30 km2) shares 15.6 km with Kutu and 8.5 km with
  Mushie.
* Botswana's "South East" (668 km2) holds Lobatse; the polygon named
  "Gaborone" (1,296 km2) holds Tlokweng, Ramotswa and Otse besides the city
  (GeoNames' points).
* Maquival (613.5 km2) borders Nicoadala (24.2 km), Namacurra (49.1 km) and
  Quelimane city (23.6 km).
* Nigeria's Bakassi is 256 km2 around Ikang; the peninsula lies in Cameroon.
* Sudan's "Abyei PCA" is 40.8 km2 in two pieces; the boundary file draws the
  Abyei Area itself (10,654 km2) as disputed ground of its own.

Usage:
    python -m scripts.fetch_census.stated_gaps
"""

from __future__ import annotations

import argparse
import gzip
import json
from typing import Any, Callable

from ._shared import NOT_AVAILABLE, PROCESSED, RAW, gap, log, record, write_json

OUT = "stated_gaps.json"
SITE = PROCESSED.parent.parent / "site" / "data"
ALL = ("population", "median_age", "sex_ratio", "religion", "language", "ethnicity")


def clear_ids() -> set[str]:
    return {r["id"] for r in json.loads((PROCESSED / "clear_global_language.json").read_text())}


def no_clear_row(code: str, sibling: str) -> Callable[[], str | None]:
    """The premise of a language note: CLEAR Global has no row ``code`` and
    does have ``sibling``, a neighbour whose shares are shown."""
    def check() -> str | None:
        ids = clear_ids()
        if code in ids:
            return f"CLEAR Global now has a row {code}"
        if sibling not in ids:
            return f"CLEAR Global has no row {sibling} either"
        return None
    return check


def no_ess_respondents(prefixes: tuple[str, ...]) -> Callable[[], str | None]:
    """The European Social Survey's regional tables place nobody in these NUTS codes."""
    def check() -> str | None:
        tabs = json.loads(gzip.decompress((RAW / "ess" / "ess_region_tabs.json.gz").read_bytes()))
        for prefix, entry in tabs["rounds"].items():
            for region in entry["religion"]["n"]:
                if region.startswith(prefixes):
                    return f"ESS {prefix} places respondents in {region}"
        return None
    return check


def town(name: str, territory: str) -> str:
    return (f"This polygon is the town of {name}, drawn inside {territory} territory. The "
            f"population statistics and language data read for the DRC count its people "
            f"within {territory}'s figures, shown on that territory's polygon, and none counts "
            "the town apart, so no figures are shown here.")


CLEAR_IRQ = ("CLEAR Global's tabulation of Iraq's 1997 census, the source of the language "
             "shares shown for the other districts of {gov}, has no row for {name}, so no "
             "shares are shown here.")

# (country, level, polygon id, name drawn, fields, reason, premise or None)
DECLARED: list[tuple[str, str, str, str, tuple[str, ...], str,
                     Callable[[], str | None] | None]] = [
    ("COD", "admin2", "63176286B74390580243640", "Tshimbulu", ALL,
     town("Tshimbulu", "Dibaya"), None),
    ("COD", "admin2", "63176286B63969135863157", "Lukalaba", ALL,
     town("Lukalaba", "Tshilenge"), None),
    ("COD", "admin2", "63176286B70830242214620", "Dingila", ALL,
     town("Dingila", "Bambesa"), None),
    ("COD", "admin2", "63176286B96753486418064", "Kasaji", ALL,
     town("Kasaji", "Dilolo"), None),
    ("COD", "admin2", "63176286B47747519497786", "Kaoze", ALL,
     town("Kaoze", "Moba"), None),
    ("COD", "admin2", "63176286B49026377824569", "Yangambi", ALL,
     town("Yangambi", "Isangi"), None),
    ("COD", "admin2", "63176286B71096802464930", "Nioki", ALL,
     ("This polygon is the town of Nioki, drawn on the edge of Kutu and Mushie "
      "territories. The population statistics and language data read for the DRC count "
      "its people within its territory's figures, shown on the territories' polygons, and "
      "none counts the town apart, so no figures are shown here."), None),
    ("COD", "admin2", "63176286B55786633055845", "Kungu", ("language",),
     ("CLEAR Global's language data for the DRC, from a 2016 survey of its territories, "
      "has no row for Kungu territory, so no language shares are shown here."),
     no_clear_row("COD-CG-CD4204", "COD-CG-CD4202")),
    ("COD", "admin2", "63176286B82661241826895", "Mbandaka", ("language",),
     ("CLEAR Global's language data for the DRC, from a 2016 survey of its territories, "
      "has no row for the city of Mbandaka, so no language shares are shown here."),
     no_clear_row("COD-CG-CD4101", "COD-CG-CD41")),
    ("BWA", "admin2", "55941954B89738474745599", "South East", ("population",),
     ("This polygon holds Lobatse and the south of South-East District. The 2011 census "
      "counts Gaborone, Lobatse and South East district as separate units, and none of "
      "them is drawn here: the polygon named Gaborone also takes in Tlokweng, Ramotswa and "
      "Otse. No census figure fits this polygon, so none is shown."), None),
    ("MOZ", "admin2", "85939544B65123265698186", "Maquival", ALL,
     ("This polygon is Maquival, an administrative post of Nicoadala district, drawn apart "
      "from the rest of the district. The population statistics read count it within "
      "Nicoadala's figures, and none counts the post alone, so no figures are shown here."),
     None),
    ("NGA", "admin2", "59680162B77398299052023", "Bakassi", ("population",),
     ("Bakassi's only census count, 31,641 in 2006, is for the local government area when "
      "it held the Bakassi peninsula, which passed to Cameroon in 2008. This polygon is "
      "the 256 km2 left on the Nigerian side, around Ikang, and no figure for it is "
      "published, so none is shown here."), None),
    ("SDN", "admin1", "86620642B69119058579524", "Abyei PCA", ("population", "language"),
     ("This polygon is 41 km2 in two pieces at the edge of the Abyei Area, which Sudan and "
      "South Sudan both claim and which the boundary file draws apart as disputed ground. "
      "No statistics read for either country count it, so no figures are shown here."),
     None),
    ("SDN", "admin2", "16777658B69119058579524", "Abyei PCA area", ("population", "language"),
     ("This polygon is 41 km2 in two pieces at the edge of the Abyei Area, which Sudan and "
      "South Sudan both claim and which the boundary file draws apart as disputed ground. "
      "No statistics read for either country count it, so no figures are shown here."),
     None),
    ("IRQ", "admin2", "34846034B54493291917017", "Al-Ramadi", ("language",),
     CLEAR_IRQ.format(gov="Al-Anbar", name="Al-Ramadi"),
     no_clear_row("IRQ-CG-IQG01Q03", "IRQ-CG-IQG01Q01")),
    ("IRQ", "admin2", "34846034B64994125853328", "Al-Faw", ("language",),
     CLEAR_IRQ.format(gov="Al-Basrah", name="Al-Faw"),
     no_clear_row("IRQ-CG-IQG02Q03", "IRQ-CG-IQG02Q01")),
    ("IRQ", "admin2", "34846034B73479794656328", "Al-Salman", ("language",),
     CLEAR_IRQ.format(gov="Al-Muthanna", name="Al-Salman"),
     no_clear_row("IRQ-CG-IQG03Q03", "IRQ-CG-IQG03Q01")),
    ("IRQ", "admin2", "34846034B91170973982462", "Al-Thawra", ("language",),
     CLEAR_IRQ.format(gov="Baghdad", name="Al-Thawra (in 1997, Saddam City)"),
     no_clear_row("IRQ-CG-IQG08Q07", "IRQ-CG-IQG08Q01")),
    ("IRQ", "admin2", "34846034B94422481549269", "Ain Al-Tamur", ("language",),
     CLEAR_IRQ.format(gov="Karbala", name="Ain Al-Tamur"),
     no_clear_row("IRQ-CG-IQG12Q01", "IRQ-CG-IQG12Q03")),
    ("IRQ", "admin2", "34846034B21026183347642", "Dibis", ("language",),
     CLEAR_IRQ.format(gov="Kirkuk", name="Dibis"),
     no_clear_row("IRQ-CG-IQG13Q03", "IRQ-CG-IQG13Q01")),
    ("IRQ", "admin2", "34846034B90360229888797", "Badra", ("language",),
     CLEAR_IRQ.format(gov="Wasit", name="Badra"),
     no_clear_row("IRQ-CG-IQG18Q05", "IRQ-CG-IQG18Q01")),
    ("IRQ", "admin2", "34846034B43190647810772", "Aqra", ("language",),
     ("Iraq's 1997 census, the source of the language shares shown for Ninawa's other "
      "districts, has no figures for Aqra, which the Kurdistan Regional Government has "
      "administered since 1991, so no shares are shown here."),
     no_clear_row("IRQ-CG-IQG15Q01", "IRQ-CG-IQG15Q02")),
    ("MWI", "admin2", "42251766B55477981037231", "Likoma", ("language",),
     ("CLEAR Global's tabulation of Malawi's 1998 census, the source of the language "
      "shares shown for the other districts, has no row for Likoma, so no shares are "
      "shown here."), no_clear_row("MWI-CG-MW106", "MWI-CG-MW101")),
    ("NAM", "admin2", "8085530B55251971881937", "Linyanti", ("language",),
     ("CLEAR Global's tabulation of Afrobarometer's 2014 survey of Namibia, the source of "
      "the language shares shown for the other constituencies, has no row for Linyanti, "
      "so no shares are shown here."), no_clear_row("NAM-CG-NA0105", "NAM-CG-NA0101")),
    ("NAM", "admin2", "8085530B91972581324678", "Guinas", ("language",),
     ("CLEAR Global's tabulation of Afrobarometer's 2014 survey of Namibia, the source of "
      "the language shares shown for the other constituencies, has no row for Guinas, so "
      "no shares are shown here."), no_clear_row("NAM-CG-NA1202", "NAM-CG-NA12")),
    ("SOM", "admin1", "83879307B33420401553888", "Middle Juba", ("language",),
     ("CLEAR Global's language data for Somalia, a tabulation of the Joint Multi-Cluster "
      "Needs Assessment of 2021, has no row for Middle Juba or any of its districts, so no "
      "language shares are shown here."), no_clear_row("SOM-CG-SO27", "SOM-CG-SO28")),
    ("CHE", "admin2", "98125504B74528098758836", "Bodensee", ("religion", "language", "ethnicity"),
     ("This polygon is Thurgau's part of Lake Constance (Bodensee), not a district. Nobody "
      "is counted on the lake. Its shore takes in part of the lakeside commune of Horn, "
      "whose residents the Federal Statistical Office counts in the district of Arbon, "
      "where the map shows them."), None),
    ("FRA", "admin1", "19338628B22604203385446", "Corse", ("religion",),
     ("The European Social Survey (rounds 5 to 11), which gives France's other regions "
      "their religion shares, places none of its respondents in Corsica, so no shares can "
      "be estimated for it."), no_ess_respondents(("FRM", "FR83"))),
]


def build(units: dict[tuple[str, str], dict[str, dict[str, Any]]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    records, report = [], []
    for iso3, level, sid, name, fields, reason, premise in DECLARED:
        shape = units.get((iso3, level), {}).get(sid)
        if shape is None or shape.get("name") != name:
            report.append(f"{iso3} {name}: polygon {sid} is not drawn under that name; left out")
            continue
        why = premise() if premise else None
        if why:
            report.append(f"{iso3} {name}: {why}; left out")
            continue
        records.append(record(
            f"{iso3}-stated-{sid}", name, level=level, parent=iso3, country=iso3,
            match_by="shape_id", shape_id=sid, **{f: gap(NOT_AVAILABLE, reason) for f in fields}))
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    units: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for iso3, level, *_ in DECLARED:
        if (iso3, level) not in units:
            path = SITE / level / f"{iso3}.units.json"
            units[(iso3, level)] = {u["id"]: u for u in json.loads(path.read_text())}
    records, report = build(units)
    for line in report:
        log("  " + line)
    log(f"  {len(records)} of {len(DECLARED)} polygons given their reason")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
