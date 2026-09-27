#!/usr/bin/env python3
"""The Bahamas: the 2010 census's island reports, for the islands the map draws whole.

The Department of Statistics published a report of the 2010 Census of
Population and Housing for each island. Each prints, for that island:

* Table 2.0, every island's population by sex (the same table in each);
* Table 4.x (4.1 New Providence, 4.4 Acklins, ...), its population by sex
  and single year of age;
* Table 7.0, its population by religion; Table 8.0, by racial group.

The census tabulates by island, and the map draws Abaco, Andros, Eleuthera,
Grand Bahama and Exuma as several districts each; an island's figures are
none of those districts'. Thirteen islands the map draws whole: New
Providence, Acklins, the Berry Islands, the Biminis, Cat Island, Crooked
Island (with Long Cay), Harbour Island, Inagua, Long Island, Mayaguana,
Ragged Island, San Salvador and Spanish Wells; Rum Cay, which has no report
of its own, has Table 2.0's count and sexes.

What this writes:

* **The first-level districts**: religion, for the thirteen. (Their median
  age and sex ratio are caribbean_uscb.py's and their racial groups uscb.py's,
  both from the Census Bureau's tabulation of the same census.)
* **The second-level units**, a separate drawing whose islands carry the
  same names ("Bimini", "Crooked Island and Long Cay"): population, sex ratio,
  median age (within the single year holding the middle person), religion and
  racial group, for the islands it draws whole. The 2010 count is written
  there because the map has none at that level.

Checks, each of which stops the run: each report's Table 2.0 row for its own
island is its age table's total, its religions' and its racial groups'; the
single years make their five-year groups and the table's total; the sexes
make the total.

Usage:
    python -m scripts.fetch_census.bahamas_census
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .binding import fold
from .redatam import median_age

OUT = PROCESSED / "bahamas_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
BASE = "https://stats.gov.bs/wp-content/uploads/2020/08/"
YEAR = 2010
SOURCE = ("Department of Statistics of The Bahamas, 2010 Census of Population and Housing, "
          "island report")
# The map's first-level district -> (its report, the Table 2.0 row, the second-level unit).
ISLANDS = {
    "New Providence": ("NEW-PROVIDENCE-2010-CENSUS-REPORT.pdf", "NEWPROVIDENCE", "New Providence"),
    "Acklins": ("ACKLINS-2010-CENSUS-REPORT.pdf", "ACKLINS", "Acklins"),
    "Berry Islands": ("BERRY-ISLANDS-2010-CENSUS-REPORT.pdf", "BERRYISLANDS", "Berry Islands"),
    "Biminis": ("BIMINIS-2010-CENSUS-REPORT.pdf", "BIMINIS", "Bimini"),
    "Cat Island": ("CAT-ISLAND-2010-CENSUS-REPORT.pdf", "CATISLAND", "Cat Island"),
    "Crooked Island": ("CROOKED-ISLAND-2010-CENSUS-REPORT.pdf", "CROOKEDISLAND",
                       "Crooked Island and Long Cay"),
    "Harbour Island": ("HARBOUR-ISLAND-2010-CENSUS-REPORT.pdf", "HARBOURISLAND", None),
    "Inagua": ("INAGUA-2010-CENSUS-REPORT.pdf", "INAGUA", "Inagua"),
    "Long Island": ("LONG-ISLAND-2010-CENSUS-REPORT.pdf", "LONGISLAND", "Long Island"),
    "Mayaguana": ("MAYAGUANA-2010-CENSUS-REPORT.pdf", "MAYAGUANA", "Mayaguana"),
    "Ragged Island": ("RAGGED-ISLAND-2010-CENSUS-REPORT.pdf", "RAGGEDISLAND", "Ragged Island"),
    "San Salvador": ("SAN-SALVADOR-2010-CENSUS-REPORT.pdf", "SANSALVADOR", "San Salvador"),
    "Spanish Wells": ("SPANISH-WELLS-2010-CENSUS-REPORT.pdf", "SPANISHWELLS", "Spanish Wells"),
}
RUM_CAY = ("RUMCAY", "Rum Cay")
RELIGION = {
    "anglican": "Anglican", "assembliesofgod": "Assemblies of God", "baptist": "Baptist",
    "brethren": "Brethren", "churchofgod": "Church of God",
    "greekorthodox": "Greek Orthodox", "jehovahswitnesses": "Jehovah's Witnesses",
    "lutheran": "Lutheran", "methodist": "Methodist", "pentecostal": "Pentecostal",
    "presbyterian": "Presbyterian", "romancatholic": "Roman Catholic",
    "seventhdayadventist": "Seventh-day Adventist", "mormon": "Mormon",
    "otherchristian": "Other Christian", "otherchristiandenomination": "Other Christian",
    "otherchristiandenominations": "Other Christian",
    "othernonchristiandenominations": "Other religion",
    "bahaifaith": "Baha'i", "hindu": "Hindu", "islammuslim": "Muslim",
    "judaismjewish": "Jewish", "rastafarian": "Rastafarian",
    "othernonchristiandenomination": "Other religion", "other": "Other religion",
    "none": "No religion", "notstated": "Not stated",
}
RACE = {"black": "Black", "blackandwhite": "Mixed (Black and White)",
        "blackandother": "Mixed (Black and other)", "white": "White",
        "whiteandother": "Mixed (White and other)", "asian": "Asian",
        "eastindian": "East Indian", "otherraces": "Other", "notstated": "Not stated"}
FIGURE = re.compile(r"^\d{1,3}(?:,\d{3})*$|^\d+$")


def present(counts: dict[str, float]) -> list[dict]:
    return shares({k: v for k, v in counts.items() if v})


def split(line: str) -> tuple[str, list[int]]:
    tokens = line.split()
    n = 0
    while n < len(tokens) and FIGURE.match(tokens[-1 - n]):
        n += 1
    return " ".join(tokens[:len(tokens) - n]), [int(t.replace(",", "")) for t in tokens[len(tokens) - n:]]


def titled_island(flat_title: str) -> str:
    """"acklins" from "table44contdacklins": what a page title names after the table."""
    return re.sub(r"^table[0-9]*(?:contd)?", "", flat_title)


def after(lines: list[str], title: str, island: str | None = None) -> list[str]:
    """The lines after every page title ``title`` (a table runs over pages), joined.

    With ``island``, only the pages whose title names that island: a report
    can carry a neighbour's table beside its own (San Salvador's has Rum
    Cay's).
    """
    out, inside = [], False
    for line in lines:
        flat = fold(line)
        if flat.startswith("table") and flat.startswith(fold(title)):
            named = titled_island(flat)
            if island is None:
                inside = True
            elif named:
                inside = fold(island).startswith(named) or named.startswith(fold(island))
            # A continuation title naming no island continues the table before it.
            continue
        if flat.startswith("table") and inside and not flat.startswith(fold(title)):
            inside = False
        if inside:
            out.append(line)
    return out


def table_2_0(lines: list[str]) -> dict[str, tuple[int, int, int]]:
    """{folded island or district: (total, men, women)} from Table 2.0."""
    out = {}
    for line in after(lines, "TABLE2.0"):
        label, figures = split(line)
        if len(figures) == 4 and label:
            total, men, women, _ = figures
            if men + women != total:
                raise SystemExit(f"bahamas_census: Table 2.0's {label} does not add up")
            out[fold(label)] = (total, men, women)
    return out


def table_4_5(lines: list[str], island: str | None = None) -> dict[str, Any]:
    """{"ages": Counter(age: people), "total", "men", "women", "unstated"} from Table 4.x."""
    ages: Counter = Counter()
    groups, whole, unstated = [], None, 0
    # Its number is the island's own: 4.1 for New Providence, 4.4 Acklins, 4.5 Andros.
    for line in after(lines, "TABLE4", island):
        label, figures = split(line)
        if not label and len(figures) == 4:
            # A single year: "1 127 70 57" is all figures, the age among them.
            label, figures = str(figures[0]), figures[1:]
        if len(figures) != 3:
            continue
        total, men, women = figures
        if men + women != total:
            raise SystemExit(f"bahamas_census: Table 4.x's {label} does not add up")
        flat = fold(label)
        if flat == "allages" and whole is not None:
            # A report may carry a second island's table after its own
            # (San Salvador's has Rum Cay's): the first is the island's.
            break
        if flat == "allages":
            whole = figures
        elif flat == "underoneyear":
            ages[0] += total
        elif flat == "notstated":
            unstated = total
        elif "-" in label:
            groups.append((label, total))
        elif re.fullmatch(r"\d+", flat):
            ages[int(flat)] += total
        elif m := re.fullmatch(r"(\d+)yearsandover", flat):
            ages[int(m[1])] += total
    if whole is None:
        raise SystemExit("bahamas_census: Table 4.x has no ALL AGES row")
    if sum(ages.values()) + unstated != whole[0]:
        raise SystemExit(f"bahamas_census: Table 4.x's single years make "
                         f"{sum(ages.values()) + unstated:,} of {whole[0]:,}")
    for label, total in groups:
        m = re.match(r"^(\d+)\s*-\s*(\d+)", label)
        if m and sum(ages[a] for a in range(int(m[1]), int(m[2]) + 1)) != total:
            raise SystemExit(f"bahamas_census: Table 4.x's {label} is not its single years")
    return {"ages": ages, "total": whole[0], "men": whole[1], "women": whole[2],
            "unstated": unstated}


def composition(lines: list[str], title: str, labels: dict[str, str], width: int,
                island: str | None = None) -> tuple[int, dict[str, int]]:
    """(the table's total, {group: people}) from Table 7.0 or 8.0's both-sexes rows."""
    total, counts, pending = None, {}, []
    for line in after(lines, title, island):
        label, figures = split(line)
        if len(figures) != width:
            if label and not figures and fold(label) not in ("male", "female"):
                pending.append(label)
            continue
        # A label wrapped onto the line above its figures ("OTHERCHRISTIAN" /
        # "DENOMINATION 41,214 ..."), after page headings gathered since the last
        # row: the lines above are tried longest run first, down to none.
        known = set(labels) | {"total", "male", "female"}
        tries = [fold(" ".join(pending[k:] + [label])) for k in range(len(pending) + 1)]
        flat = next((t for t in tries if t in known), None)
        if flat is None:
            # A misprint of a known category ("PENECOSTAL", "OTHER CHRISTIAN
            # DENOMIATION"), longest run first, logged.
            for t in tries:
                close = difflib.get_close_matches(t, list(labels), n=1, cutoff=0.88)
                if close:
                    log(f"  {title}: {' '.join(pending + [label])!r} read as "
                        f"{labels[close[0]]}")
                    flat = close[0]
                    break
        flat = flat or fold(label)
        pending = []
        if flat == "total":
            if total is not None:
                break
            total = figures[0]
            continue
        if flat in ("male", "female"):
            if title == "TABLE8.0" and flat == "male":
                break
            continue
        if flat not in labels:
            # The reports name their residual rows several ways ("OTHER",
            # "OTHER DENOMINATIONS", ...); any other unknown row stops the run.
            if not (title == "TABLE7.0" and flat.startswith("other")):
                raise SystemExit(f"bahamas_census: {title} category {label!r} is not one this "
                                 "reads")
            log(f"  {title}: {label!r} read as Other religion")
            flat = "other"
        counts[labels[flat]] = counts.get(labels[flat], 0) + figures[0]
    if total is None or sum(counts.values()) != total:
        raise SystemExit(f"bahamas_census: {title}'s groups make {sum(counts.values()):,} of "
                         f"{total}")
    return total, counts


def report_lines(name: str) -> list[str]:
    import pdfplumber
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(http_get(BASE + name, binary=True, cache=False))) as pdf:
        for page in pdf.pages[:45]:
            out += (page.extract_text() or "").splitlines()
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    admin1 = {fold(u["name"]): u for u in json.loads((SITE / "admin1" / "BHS.units.json").read_text())}
    admin2 = {fold(u["name"]): u for u in json.loads((SITE / "admin2" / "BHS.units.json").read_text())}
    records = []
    counts_2_0: dict[str, tuple[int, int, int]] = {}
    for district, (report, row, unit2) in ISLANDS.items():
        lines = report_lines(report)
        counts_2_0 = table_2_0(lines) or counts_2_0
        island = counts_2_0.get(fold(row))
        age = table_4_5(lines, row)
        religion_total, religion = composition(lines, "TABLE7.0", RELIGION, 9, row)
        race_total, race = composition(lines, "TABLE8.0", RACE, 11, row)
        if island is None or {island[0], age["total"], religion_total, race_total} != {island[0]}:
            raise SystemExit(f"bahamas_census: {district}: Table 2.0 {island}, ages "
                             f"{age['total']}, religions {religion_total}, races {race_total}")
        log(f"  {district}: {island[0]:,} in Table 2.0, the age table, religions and races")
        source = f"{SOURCE}: {district}"
        url = BASE + report
        rel_note = ("Religion, 2010 (Table 7.0 of the island's report). The smaller "
                    "islands' reports gather the smallest denominations -- Lutheran, "
                    "Presbyterian, Mormon, Muslim, Jewish and other non-Christian -- as "
                    "\"Other\", written here as Other religion.")
        shape1 = admin1.get(fold(district))
        if shape1 is None:
            raise SystemExit(f"bahamas_census: {district} has no first-level polygon")
        records.append(record(
            f"BHS-DOS-{fold(district)}", shape1["name"], level="admin1", parent="BHS",
            country="BHS", match_by="shape_id", shape_id=shape1["id"],
            religion=present(religion), religion_year=YEAR, religion_note=rel_note,
            sources=[{"field": "religion", "name": source, "url": url, "year": YEAR}]))
        if unit2 is None:
            continue
        shape2 = admin2.get(fold(unit2))
        if shape2 is None:
            raise SystemExit(f"bahamas_census: {unit2} has no second-level polygon")
        records.append(record(
            f"BHS-DOS-2-{fold(unit2)}", shape2["name"], level="admin2", parent="BHS",
            country="BHS", match_by="shape_id", shape_id=shape2["id"],
            population=measure(island[0], year=YEAR, source=source),
            population_note="Everyone the 2010 census counted on the island (Table 2.0).",
            sex_ratio=measure(round(1000 * island[1] / island[2]),
                              unit="males_per_1000_females", year=YEAR, source=source),
            sex_ratio_note="Men per thousand women, 2010 (Table 2.0).",
            median_age=measure(median_age(age["ages"]), unit="years", year=YEAR, source=source),
            median_age_note=("Interpolated within the single year holding the middle person "
                             "(Table 4.x of the island's report)" + (f"; {age['unstated']:,} of unstated age left out"
                                              if age["unstated"] else "") + "."),
            religion=present(religion), religion_year=YEAR, religion_note=rel_note,
            ethnicity=present(race), ethnicity_year=YEAR,
            ethnicity_note="Racial group, 2010 (Table 8.0 of the island's report).",
            sources=[{"field": "population/sex_ratio/median_age/religion/ethnicity",
                      "name": source, "url": url, "year": YEAR}]))
    rum = counts_2_0.get(fold(RUM_CAY[0]))
    shape2 = admin2.get(fold(RUM_CAY[1]))
    if rum and shape2:
        source = f"{SOURCE}, Table 2.0"
        records.append(record(
            "BHS-DOS-2-rumcay", shape2["name"], level="admin2", parent="BHS", country="BHS",
            match_by="shape_id", shape_id=shape2["id"],
            population=measure(rum[0], year=YEAR, source=source),
            population_note="Everyone the 2010 census counted on Rum Cay (Table 2.0).",
            sex_ratio=measure(round(1000 * rum[1] / rum[2]), unit="males_per_1000_females",
                              year=YEAR, source=source),
            sex_ratio_note="Men per thousand women, 2010 (Table 2.0).",
            sources=[{"field": "population/sex_ratio", "name": source,
                      "url": BASE + ISLANDS["San Salvador"][0], "year": YEAR}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {sum(1 for r in records if r['level'] == 'admin1')} districts, "
        f"{sum(1 for r in records if r['level'] == 'admin2')} second-level islands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
