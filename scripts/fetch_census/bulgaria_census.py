#!/usr/bin/env python3
"""Bulgaria: the 2021 census by district and municipality, from NSI's workbooks.

The National Statistical Institute publishes the 2021 census's results as
workbooks on its census page (nsi.bg, "Резултати от Преброяване 2021"):

* ``Census2021_Population_BG.xlsx`` -- the population by five-year age group
  (0-4 ... 80-84, 85+) and sex, for the country, its regions, the 28 districts
  (oblasti), the 265 municipalities (obshtini) and every settlement;
* ``Census2021_Ethnocultural characteristics_BG.xlsx`` -- ethnic group
  (sheet 2), mother tongue (sheet 3) and religion (sheet 4) for the country,
  the regions, the districts and the municipalities, at the categories the
  institute publishes below the national level.

**Voluntary questions.** Ethnic group, mother tongue and religion were
voluntary in 2021. Everyone the census counted is in the tables: those who
answered, those who said they could not determine it ("Cannot determine"),
those who did not wish to answer ("Not declared"), and the institute's
"непоказана" -- no answer recorded, which includes residents enumerated from
registers ("Not stated"). All are kept as bars.

**Names.** NSI writes the units in Cyrillic, the boundary file in the official
Latin transliteration (the 2009 Transliteration Act), so a municipality is
transliterated the same way and matched by name within its district; each
district is matched through its NSI code. Anything left over on either side
is reported and left out.

Median age is interpolated within the five-year group that holds the middle
person (NSI publishes nothing finer by municipality); sex ratio is males per
100 females.

Usage:
    python -m scripts.fetch_census.bulgaria_census
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .balkans_common import check_sum, fold, grouped_median, shapes

OUT = "bulgaria_census.json"
YEAR = 2021
POPULATION = "https://www.nsi.bg/file/download/63412e676270c92e166a333004767d40f0e23dc3"
ETHNOCULTURAL = "https://www.nsi.bg/file/download/d6bebedae9d8dc7824e050bfc47124b402d9129b"
PAGE = "https://www.nsi.bg/statistical-data/151/1349"
SOURCE = "National Statistical Institute of Bulgaria, Census 2021, {table}"
LICENCE = "NSI Bulgaria (reuse with attribution)"
NATIONAL = 6_519_789
SHEETS = {"ethnicity": "2", "language": "3", "religion": "4"}
TABLE_NAMES = {"age": "population by age group and sex (Census2021_Population_BG.xlsx)",
               "ethnicity": "population by ethnic group (Census2021_Ethnocultural characteristics_BG.xlsx, sheet 2)",
               "language": "population by mother tongue (Census2021_Ethnocultural characteristics_BG.xlsx, sheet 3)",
               "religion": "population by religion (Census2021_Ethnocultural characteristics_BG.xlsx, sheet 4)"}

LABELS = {
    "ethnicity": {"българска": "Bulgarian", "турска": "Turkish", "ромска": "Roma",
                  "друга": "Other", "не мога да определя": "Cannot determine",
                  "не желая да отговоря": "Not declared", "непоказана": "Not stated"},
    "language": {"български": "Bulgarian", "турски": "Turkish", "ромски": "Romani",
                 "друг": "Other", "не мога да определя": "Cannot determine",
                 "не желая да отговоря": "Not declared", "непоказан": "Not stated"},
    "religion": {"християнско": "Christian", "мюсюлманско": "Islam", "юдейско": "Judaism",
                 "друго": "Other religion", "нямам": "No religion",
                 "не мога да определя": "Cannot determine",
                 "не желая да отговоря": "Not declared", "непоказано": "Not stated"},
}
NOTES = {
    "ethnicity": ("Ethnic group (етническа принадлежност), 2021 census, a voluntary question: "
                  "the institute publishes Bulgarian, Turkish and Roma by municipality and the "
                  "rest as 'Other'. 'Cannot determine' and 'Not declared' are those who could "
                  "not or would not say; 'Not stated' is the census's 'непоказана', no answer "
                  "recorded (it includes residents counted from registers)."),
    "language": ("Mother tongue (майчин език), 2021 census, a voluntary question, at the "
                 "languages the institute publishes by municipality; the non-answers are kept "
                 "as bars as for ethnic group."),
    "religion": ("Religion (вероизповедание), 2021 census, a voluntary question, at the "
                 "institute's broad groups by municipality (Christian, Muslim, Jewish, other, "
                 "none); the non-answers are kept as bars as for ethnic group."),
}
MEDIAN_NOTE = ("Interpolated within the five-year age group that holds the middle person, "
               "from the census's population by age group and sex: NSI publishes nothing "
               "finer by {level}.")

# The 2009 Transliteration Act's table.
LATIN = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
         "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
         "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
         "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya"}
# NSI district codes to the boundary file's district names.
DISTRICTS = {
    "BLG": "Blagoevgrad", "BGS": "Burgas", "DOB": "Dobrich", "GAB": "Gabrovo",
    "HKV": "Haskovo", "KRZ": "Kardzhali", "KNL": "Kyustendil", "LOV": "Lovech",
    "MON": "Montana", "PAZ": "Pazardzhik", "PER": "Pernik", "PVN": "Pleven",
    "PDV": "Plovdiv", "RAZ": "Razgrad", "RSE": "Ruse", "SHU": "Shumen", "SLS": "Silistra",
    "SLV": "Sliven", "SML": "Smolyan", "SFO": "Sofia", "SOF": "Sofia City",
    "SZR": "Stara Zagora", "TGV": "Targovishte", "VAR": "Varna", "VTR": "Veliko Tarnovo",
    "VID": "Vidin", "VRC": "Vratsa", "JAM": "Yambol",
}
# The boundary file's spelling where it is not the transliteration.
ALIASES = {"Georgi Damyanovo": "Georgi Bamyanovo", "Dobrich-Selska": "Dobrichka",
           "Ruzhintsi": "Ruzhinsi", "Strumyani": "Strumyarni"}
# Municipalities formed since the boundary file's vintage, wholly from one it
# draws: Sarnitsa was separated from Velingrad in 2015.
INTO = {"Сърница": "Велинград"}


def latin(name: str) -> str:
    """The official Latin transliteration, letter by letter. The Act's -ия to
    -ia rule for a word's end is not applied: the boundary file writes
    Provadiya and Dolna Mitropoliya."""
    text = str(name).strip().lower()
    out = "".join(LATIN.get(c, c) for c in text)
    return "".join(w.capitalize() if w.isalpha() else w for w in re.split(r"(\W+)", out))


def text(cell: Any) -> str:
    return " ".join(str(cell if cell is not None else "").split())


def number(cell: Any) -> float:
    if isinstance(cell, (int, float)):
        return float(cell)
    t = text(cell)
    if t in ("", "-", "–"):
        return 0.0
    try:
        return float(t.replace(" ", ""))
    except ValueError:
        raise SystemExit(f"bulgaria_census: cannot read {cell!r} as a count")


def workbook(url: str) -> dict[str, list[tuple[Any, ...]]]:
    import openpyxl
    blob = http_get(url, binary=True, timeout=600)
    log(f"  {url.rsplit('/', 1)[-1][:12]}...: {len(blob):,} bytes")
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return {ws.title.strip(): [tuple(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def is_district(code: str) -> bool:
    return code in DISTRICTS


def is_municipality(code: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{3}\d{2}", code)) and code[:3] in DISTRICTS


def ages(rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """{code: {"name", "total", "groups", "men", "women"}} for the country,
    districts and municipalities (settlements are skipped)."""
    head = next(i for i, r in enumerate(rows) if any(text(c) == "0 - 4" for c in r))
    sexes = rows[head - 1]
    blocks: dict[str, list[tuple[int, float, float | None]]] = defaultdict(list)
    totals: dict[str, int] = {}
    for j, c in enumerate(rows[head]):
        label, sex = text(c), text(sexes[j]).lower()
        m, top = re.match(r"^(\d+) - (\d+)$", label), re.match(r"^(\d+)\+$", label)
        if label.lower() == "общо":
            totals[sex] = j
        elif m:
            blocks[sex].append((j, float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1)))
        elif top:
            blocks[sex].append((j, float(top.group(1)), None))
    if set(totals) != {"общо", "мъже", "жени"}:
        raise SystemExit(f"bulgaria_census: the age table's sex blocks are {list(totals)}")
    out: dict[str, dict[str, Any]] = {}
    for r in rows[head + 1:]:
        code = text(r[0])
        if not (code == "BG" or is_district(code) or is_municipality(code)):
            continue
        groups = [(lo, w, number(r[j])) for j, lo, w in blocks["общо"]]
        total, men, women = (number(r[totals[k]]) for k in ("общо", "мъже", "жени"))
        check_sum(sum(n for _, _, n in groups), total, f"bulgaria_census: ages of {code}")
        check_sum(men + women, total, f"bulgaria_census: sexes of {code}")
        out[code] = {"name": text(r[1]), "total": total, "groups": groups, "men": men,
                     "women": women}
    return out


def composition(field: str, rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    head = next(i for i, r in enumerate(rows) if any(text(c).lower() == "общо" for c in r[2:]))
    columns: dict[int, str | None] = {}
    unknown = []
    for j, c in enumerate(rows[head]):
        if j < 2 or not text(c):
            continue
        raw = re.sub(r"\d+$", "", text(c)).strip().lower()
        if raw == "общо":
            columns[j] = None
        elif raw in LABELS[field]:
            columns[j] = LABELS[field][raw]
        else:
            unknown.append(text(c))
    if unknown:
        raise SystemExit(f"bulgaria_census: {field} columns with no entry in LABELS: {unknown}")
    out: dict[str, dict[str, Any]] = {}
    for r in rows[head + 1:]:
        code = text(r[0])
        if not (code == "BG" or is_district(code) or is_municipality(code)):
            continue
        groups: dict[str, float] = defaultdict(float)
        total = None
        for j, group in columns.items():
            if group is None:
                total = number(r[j])
            else:
                groups[group] += number(r[j])
        check_sum(sum(groups.values()), total, f"bulgaria_census: {field} of {code}")
        out[code] = {"total": total, "groups": dict(groups)}
    return out


def build() -> list[dict[str, Any]]:
    pop = ages(workbook(POPULATION)["1"])
    culture = workbook(ETHNOCULTURAL)
    comps = {f: composition(f, culture[s]) for f, s in SHEETS.items()}
    districts = sorted(c for c in pop if is_district(c))
    munis = sorted(c for c in pop if is_municipality(c))
    if len(districts) != 28 or len(munis) != 265:
        raise SystemExit(f"bulgaria_census: {len(districts)} districts, {len(munis)} municipalities")
    check_sum(pop["BG"]["total"], NATIONAL, "bulgaria_census: the country")
    check_sum(sum(pop[c]["total"] for c in districts), NATIONAL, "bulgaria_census: districts")
    check_sum(sum(pop[c]["total"] for c in munis), NATIONAL, "bulgaria_census: municipalities")
    for d in districts:
        check_sum(sum(pop[m]["total"] for m in munis if m.startswith(d)), pop[d]["total"],
                  f"bulgaria_census: municipalities of {d}")
    for field, table in comps.items():
        for code in ["BG"] + districts + munis:
            if code not in table:
                raise SystemExit(f"bulgaria_census: {field} has no row for {code}")
            check_sum(table[code]["total"], pop[code]["total"], f"bulgaria_census: {field} total of {code}")
    log(f"  country: {NATIONAL:,}, median {grouped_median(pop['BG']['groups'])} from five-year groups")

    # Fold a municipality formed since the map's vintage into the one it was
    # formed from, in every table, and say so on the record.
    joined: dict[str, str] = {}
    for part_name, whole_name in INTO.items():
        part = next(c for c in munis if pop[c]["name"] == part_name)
        whole = next(c for c in munis if pop[c]["name"] == whole_name)
        a, b = pop[whole], pop[part]
        a["groups"] = [(lo, w, n + m) for (lo, w, n), (_, _, m) in zip(a["groups"], b["groups"])]
        for k in ("total", "men", "women"):
            a[k] += b[k]
        for table in comps.values():
            for g, n in table[part]["groups"].items():
                table[whole]["groups"][g] = table[whole]["groups"].get(g, 0.0) + n
            table[whole]["total"] += table[part]["total"]
        munis.remove(part)
        joined[whole] = (f"{latin(whole_name)} is drawn as it was before {latin(part_name)} was "
                         f"separated from it in 2015; its figures are the two municipalities' "
                         "summed.")
        log(f"  {latin(part_name)} ({part}) folded into {latin(whole_name)} ({whole})")

    admin1 = {s["name"]: s for s in shapes("BGR", "admin1")}
    admin2 = shapes("BGR", "admin2")
    missing = [n for n in DISTRICTS.values() if n not in admin1]
    if missing:
        raise SystemExit(f"bulgaria_census: districts with no polygon: {missing}")
    records: list[dict[str, Any]] = []

    def fields(code: str, level: str) -> dict[str, Any]:
        unit = pop[code]
        out: dict[str, Any] = {
            "population": measure(int(unit["total"]), year=YEAR, source=SOURCE.format(table=TABLE_NAMES["age"])),
            "median_age": measure(grouped_median(unit["groups"]), unit="years", year=YEAR,
                                  source=SOURCE.format(table=TABLE_NAMES["age"])),
            "median_age_note": MEDIAN_NOTE.format(level=level),
            "sex_ratio": measure(round(100 * unit["men"] / unit["women"], 1), unit="males_per_100_females",
                                 year=YEAR, source=SOURCE.format(table=TABLE_NAMES["age"])),
        }
        cite = [{"field": "population/median_age/sex_ratio", "name": SOURCE.format(table=TABLE_NAMES["age"]),
                 "url": POPULATION, "page": PAGE, "year": YEAR, "license": LICENCE}]
        for field in SHEETS:
            row = comps[field][code]
            out[field] = shares({g: n for g, n in row["groups"].items() if n}, total=row["total"])
            out[f"{field}_year"] = YEAR
            out[f"{field}_note"] = NOTES[field]
            cite.append({"field": field, "name": SOURCE.format(table=TABLE_NAMES[field]),
                         "url": ETHNOCULTURAL, "page": PAGE, "year": YEAR, "license": LICENCE})
        out["sources"] = cite
        return out

    for code in districts:
        shape = admin1[DISTRICTS[code]]
        records.append(record(f"BGR-2021-{code}", shape["name"], level="admin1", parent="BGR",
                              country="BGR", match_by="shape_id", shape_id=shape["id"],
                              **fields(code, "district")))

    # Municipalities by transliterated name within their district.
    by_parent: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for s in admin2:
        by_parent[s["parent"]][fold(s["name"])].append(s)
    left_units, used = [], set()
    for code in munis:
        district = admin1[DISTRICTS[code[:3]]]
        name = latin(pop[code]["name"])
        target = fold(ALIASES.get(name, name))
        hits = [h for h in by_parent[district["id"]].get(target, []) if h["id"] not in used]
        if not hits:
            left_units.append(f"{pop[code]['name']} = {name} ({code})")
            continue
        # A name drawn twice in one district is one municipality in two
        # features (Zlatitsa): the figures go on the larger, the other is
        # listed for a merge.
        shape = max(hits, key=lambda h: (h["bbox"][2] - h["bbox"][0]) * (h["bbox"][3] - h["bbox"][1]))
        if len(hits) > 1:
            log(f"  {name} is drawn as {len(hits)} polygons: figures on {shape['id']}, "
                f"merge {[h['id'] for h in hits if h is not shape]}")
        used.update(h["id"] for h in hits)
        extra = fields(code, "municipality")
        if code in joined:
            extra["population_note"] = joined[code]
            extra["median_age_note"] += " " + joined[code]
            for field in SHEETS:
                extra[f"{field}_note"] += " " + joined[code]
        records.append(record(f"BGR-2021-{code}", shape["name"], level="admin2", parent="BGR",
                              country="BGR", parent_name=district["name"], match_by="shape_id",
                              shape_id=shape["id"], codes={"nsi": code}, **extra))
    spare = [f"{s['name']} ({next(n for n, v in admin1.items() if v['id'] == s['parent'])})"
             for s in admin2 if s["id"] not in used]
    log(f"  {len(munis) - len(left_units)} municipalities bound; left over: {left_units}")
    log(f"  polygons with no municipality: {spare}")
    if len(left_units) > 5:
        raise SystemExit("bulgaria_census: too many municipalities unbound to trust the matching")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("bulgaria_census: NSI, Census 2021")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
