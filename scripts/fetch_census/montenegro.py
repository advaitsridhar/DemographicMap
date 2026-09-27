#!/usr/bin/env python3
"""Montenegro: the 2023 census by municipality, from Monstat's own tables.

Monstat published the first results of the 2023 Census of Population,
Households and Dwellings as workbooks beside its releases
(monstat.org, "Konačni rezultati Popisa ... u 2023. godini"):

* release I (``TABELA_Popis stanovnistva 2023 I_CG.xlsx``), table 4 --
  population by five-year age group (0-4 ... 70-74, 75+) and sex, by
  municipality;
* release II (``TABELA_Popis stanovnistva 2023 II_CG.xlsx``), table 1 --
  national or ethnic affiliation, table 2 -- religion, table 3 -- mother
  tongue, each by municipality.

**Boundary vintage.** The map draws the 23 municipalities of 2014-2018, before
Tuzi (2018) and Zeta (2022) were separated from Podgorica; the census counts
25. Both were formed wholly from Podgorica's territory, so the map's Podgorica
is the census's Podgorica, Tuzi and Zeta summed, and every other municipality
is the census's own. The map draws each municipality at both levels.

**Protected cells.** Monstat prints ``z`` for a cell withheld for
confidentiality and ``-`` for none. The people a row's ``z`` cells hide are
exactly its total less its printed cells; they are kept as one bar,
"Suppressed (disclosure control)", never spread over the answers. A row with
no ``z`` must add up exactly.

Median age is interpolated within the five-year group that holds the middle
person (Monstat publishes nothing finer by municipality); sex ratio is males
per 100 females, to one decimal.

Usage:
    python -m scripts.fetch_census.montenegro
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .balkans_common import check_sum, fold, grouped_median, shapes

OUT = "montenegro_census.json"
YEAR = 2023
BASE = "https://www.monstat.org/uploads/files/popis%202021/saopstenja/"
RELEASE_I = BASE + "TABELA_Popis%20stanovnistva%202023%20I_CG.xlsx"
RELEASE_II = BASE + "TABELA_Popis%20stanovnistva%202023%20II_CG.xlsx"
PAGE = "https://www.monstat.org/cg/page.php?id=2282&pageid=1992"
SOURCE = ("Monstat (Statistical Office of Montenegro), Popis stanovništva, domaćinstava i "
          "stanova 2023, {release}, tabela {table}")
LICENCE = "Monstat (reuse with attribution)"
NATIONAL = 623_633
SUPPRESSED = "Suppressed (disclosure control)"
# Podgorica as the map draws it: the census's three municipalities formed from it.
PODGORICA = ("podgorica", "tuzi", "zeta")

LABELS: dict[str, dict[str, str]] = {
    "ethnicity": {
        "crnogorci": "Montenegrin", "srbi": "Serbian", "bosnjaci": "Bosniak",
        "albanci": "Albanian", "muslimani": "Muslim (ethnic)", "hrvati": "Croatian",
        "bjelorusi": "Belarusian", "bosanci": "Bosnian",
        "crnogorcimuslimani": "Montenegrin-Muslim", "crnogorcisrbi": "Montenegrin-Serbian",
        "egipcani": "Balkan Egyptian", "goranci": "Gorani", "jugosloveni": "Yugoslav",
        "madari": "Hungarian", "makedonci": "Macedonian",
        "muslimanicrnogorci": "Muslim-Montenegrin", "njemci": "German", "romi": "Roma",
        "rusi": "Russian", "slovenci": "Slovene", "srbicrnogorci": "Serbian-Montenegrin",
        "tatari": "Tatar", "turci": "Turkish", "ukrajinci": "Ukrainian",
        "regionalnapripadnost": "Regional affiliation", "ostalenacije": "Other",
        "ostalo": "Other", "nezelidaseizjasni": "Not declared", "nepoznato": "Not stated",
    },
    "religion": {
        "pravoslavna": "Orthodox", "katolicka": "Catholic", "protestantska": "Protestant",
        "jehovinisvjedoci": "Jehovah's Witnesses", "ostalehriscanske": "Other Christian",
        "islamska": "Islam", "budisticka": "Buddhism", "ostalevjere": "Other religion",
        "ateisti": "Atheism", "agnostici": "Agnosticism", "nezelidaseizjasni": "Not declared",
        "ostalo": "Other religion", "nepoznato": "Not stated",
    },
    "language": {
        "crnogorski": "Montenegrin", "srpski": "Serbian", "bosanski": "Bosnian",
        "albanski": "Albanian", "hrvatski": "Croatian", "bjeloruski": "Belarusian",
        "bokeljski": "Other", "bosnjacki": "Bosnian",
        "crnogorskisrpski": "Serbo-Croatian", "crnogorskisrpskibosanskihrvatski": "Serbo-Croatian",
        "hrvatskosrpski": "Serbo-Croatian", "srpskicrnogorski": "Serbo-Croatian",
        "srpskohrvatski": "Serbo-Croatian", "jugoslovenski": "Serbo-Croatian",
        "engleski": "English", "goranski": "Gorani", "makedonski": "Macedonian",
        "maternji": "Other", "njemacki": "German", "romski": "Romani", "ruski": "Russian",
        "turski": "Turkish", "ukrajinski": "Ukrainian", "ostalijezici": "Other",
        "ostalo": "Other", "nezelidaseizjasni": "Not declared", "nepoznato": "Not stated",
    },
}
# A row that is part of the row above it: "of which Bokelji", under regional
# affiliation.
NESTED = re.compile(r"^od toga\b", re.I)
NOTES = {
    "ethnicity": ("National or ethnic affiliation, 2023 census, free and optional declaration; "
                  "the census's combined answers (Montenegrin-Serbian, Serbian-Montenegrin, "
                  "Montenegrin-Muslim, Muslim-Montenegrin) are kept as given, as are regional "
                  "affiliation and those who did not wish to declare. 'Other' is the census's "
                  "other nations and other answers."),
    "religion": ("Religion, 2023 census, free and optional declaration; atheists, agnostics "
                 "and those who did not wish to declare are their own bars."),
    "language": ("Mother tongue, 2023 census, free declaration. Answers naming two or more of "
                 "Montenegrin, Serbian, Bosnian and Croatian ('Montenegrin-Serbian', "
                 "'Serbo-Croatian', 'Croato-Serbian' and the like) and 'Yugoslav' are shown "
                 "together as Serbo-Croatian; Bosniak is shown with Bosnian; the regional "
                 "'Bokeljski' and the answer 'maternji' are with Other."),
}
MEDIAN_NOTE = ("Interpolated within the five-year age group that holds the middle person, from "
               "the census's population by age group and sex (release I, table 4): Monstat "
               "publishes nothing finer by municipality.")


def sheets(url: str) -> dict[str, list[tuple[Any, ...]]]:
    import openpyxl
    blob = http_get(url, binary=True, timeout=300)
    log(f"  {url.rsplit('/', 1)[-1]}: {len(blob):,} bytes")
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return {ws.title.strip(): [tuple(r) for r in ws.iter_rows(values_only=True)]
            for ws in wb.worksheets}


def text(cell: Any) -> str:
    return " ".join(str(cell if cell is not None else "").split())


def number(cell: Any) -> float | None:
    """A count; None for Monstat's protected 'z'; 0 for '-'."""
    if isinstance(cell, (int, float)):
        return float(cell)
    t = text(cell)
    if t.lower() == "z":
        return None
    if t in ("", "-", "–"):
        return 0.0
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        raise SystemExit(f"montenegro: cannot read {cell!r} as a count")


UNKNOWN: dict[str, set[str]] = defaultdict(set)


def label(field: str, raw: str) -> str:
    k = fold(raw)
    if k in LABELS[field]:
        return LABELS[field][k]
    UNKNOWN[field].add(raw)
    return raw


def settle(field: str, where: str, total: float, groups: dict[str, float], stars: int) -> dict[str, float]:
    """The printed groups, and what the row's protected cells hide as one bar."""
    shown = sum(groups.values())
    short = total - shown
    if short < -0.5 or (stars == 0 and short > 0.5):
        raise SystemExit(f"montenegro: {field} of {where}: the groups add to {shown:,.0f} "
                         f"against {total:,.0f} with {stars} protected cells")
    out = dict(groups)
    if short > 0.5:
        out[SUPPRESSED] = short
    return out


def by_columns(field: str, rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """Tables 1 and 3: a row per group, a column pair (count, %) per municipality."""
    head = next(i for i, r in enumerate(rows) if text(r[0]).lower().startswith(
        ("nacionalna", "maternji", "vjeroispov")) or text(r[1] if len(r) > 1 else "") == "Crna Gora")
    names = rows[head + 1]
    cols = {1: "Crna Gora"}
    for j in range(3, len(names)):
        n = text(names[j])
        if n and n != "u %":
            cols[j] = n
    units: dict[str, dict[str, Any]] = {n: {"total": None, "groups": defaultdict(float), "stars": 0}
                                        for n in cols.values()}
    for r in rows[head + 2:]:
        name = text(r[0])
        if not name or name.startswith(('"', "“")):
            continue
        if NESTED.match(name):
            continue
        is_total = fold(name) == "ukupno"
        group = None if is_total else label(field, name)
        for j, unit in cols.items():
            value = number(r[j]) if j < len(r) else 0.0
            if is_total:
                units[unit]["total"] = value
            elif value is None:
                units[unit]["stars"] += 1
            else:
                units[unit]["groups"][group] += value
    return units


def religion(rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """Table 2: a row per municipality, a column pair per religion, two header rows."""
    head = next(i for i, r in enumerate(rows) if fold(text(r[0])) == "opstine")
    top, sub = rows[head], rows[head + 1]
    cols: dict[int, str] = {}
    for j in range(3, max(len(top), len(sub))):
        name = text(sub[j]) if j < len(sub) and text(sub[j]) else (text(top[j]) if j < len(top) else "")
        if name and name != "u %" and fold(name) != "hriscanstvo":
            cols[j] = label("religion", name)
    out: dict[str, dict[str, Any]] = {}
    for r in rows[head + 2:]:
        name = text(r[0])
        if not name or name.startswith(('"', "“")):
            continue
        unit = {"total": number(r[1]), "groups": defaultdict(float), "stars": 0}
        for j, group in cols.items():
            value = number(r[j]) if j < len(r) else 0.0
            if value is None:
                unit["stars"] += 1
            else:
                unit["groups"][group] += value
        out[name] = unit
    return out


def ages(rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """Release I table 4: {municipality: {"total", "groups", "men", "women"}}."""
    head = next(i for i, r in enumerate(rows) if any(text(c) == "0-4" for c in r))
    bands = []
    for j, c in enumerate(rows[head]):
        t = text(c)
        m, top = re.match(r"^(\d+)-(\d+)$", t), re.match(r"^(\d+)\+$", t)
        if m:
            bands.append((j, float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1)))
        elif top:
            bands.append((j, float(top.group(1)), None))
    out: dict[str, dict[str, Any]] = {}
    current = None
    for r in rows[head + 1:]:
        name = text(r[0])
        if not name:
            continue
        total = number(r[1]) if len(r) > 1 else None
        if total is None:
            continue
        if fold(name) == "musko" and current:
            out[current]["men"] = total
        elif fold(name) == "zensko" and current:
            out[current]["women"] = total
        else:
            current = name
            groups = [(lo, w, number(r[j]) or 0.0) for j, lo, w in bands]
            check_sum(sum(n for _, _, n in groups), total, f"montenegro: ages of {name}")
            out[name] = {"total": total, "groups": groups, "men": None, "women": None}
    for name, unit in out.items():
        check_sum((unit["men"] or 0) + (unit["women"] or 0), unit["total"],
                  f"montenegro: sexes of {name}")
    return out


def build() -> list[dict[str, Any]]:
    first = sheets(RELEASE_I)
    second = sheets(RELEASE_II)
    age = ages(first["Tabela 4"])
    comps = {"ethnicity": by_columns("ethnicity", second["Tabela 1"]),
             "religion": religion(second["Tabela 2"]),
             "language": by_columns("language", second["Tabela 3"])}
    if any(UNKNOWN.values()):
        raise SystemExit("montenegro: categories with no entry in LABELS: "
                         + "; ".join(f"{f}: {sorted(v)}" for f, v in UNKNOWN.items() if v))
    country = next(n for n in age if fold(n) == "crnagora")
    munis = [n for n in age if n != country]
    if len(munis) != 25:
        raise SystemExit(f"montenegro: {len(munis)} municipalities in table 4, not 25")
    check_sum(age[country]["total"], NATIONAL, "montenegro: the country")
    check_sum(sum(age[m]["total"] for m in munis), NATIONAL, "montenegro: municipalities")
    for field, table in comps.items():
        by_key = {fold(k): v for k, v in table.items()}
        for m in munis + [country]:
            unit = by_key.get(fold(m))
            if unit is None:
                raise SystemExit(f"montenegro: {field} has no column or row for {m}")
            check_sum(unit["total"], age[m]["total"], f"montenegro: {field} total of {m}")
        comps[field] = by_key
    log(f"  country: {NATIONAL:,}, median {grouped_median(age[country]['groups'])} "
        "from five-year groups")

    # The map's 23 municipalities: Podgorica is three of the census's.
    drawn = {level: {fold(re.sub(r"\s+Municipality$", "", s["name"])): s for s in shapes("MNE", level)}
             for level in ("admin1", "admin2")}
    parts: dict[str, list[str]] = defaultdict(list)
    for m in munis:
        parts["podgorica" if fold(m) in PODGORICA else fold(m)].append(m)
    missing = sorted(set(parts) - set(drawn["admin2"]))
    spare = sorted(set(drawn["admin2"]) - set(parts))
    if missing or spare:
        raise SystemExit(f"montenegro: census municipalities with no polygon {missing}; "
                         f"polygons with no municipality {spare}")
    records = []
    for k, names in sorted(parts.items()):
        total = sum(age[m]["total"] for m in names)
        men = sum(age[m]["men"] for m in names)
        women = sum(age[m]["women"] for m in names)
        groups: dict[tuple[float, float | None], float] = defaultdict(float)
        for m in names:
            for lo, w, n in age[m]["groups"]:
                groups[(lo, w)] += n
        median = grouped_median([(lo, w, n) for (lo, w), n in groups.items()])
        fields: dict[str, Any] = {
            "population": measure(int(total), year=YEAR, source=SOURCE.format(release="release I", table=4)),
            "median_age": measure(median, unit="years", year=YEAR,
                                  source=SOURCE.format(release="release I", table=4)),
            "median_age_note": MEDIAN_NOTE,
            "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                                 year=YEAR, source=SOURCE.format(release="release I", table=4)),
        }
        joined = (" Podgorica is drawn as it was before Tuzi (2018) and Zeta (2022) were formed "
                  "from it, so its figures are the three municipalities' summed.") if len(names) > 1 else ""
        if joined:
            fields["population_note"] = joined.strip()
            fields["median_age_note"] += joined
        cite = [{"field": "population/median_age/sex_ratio",
                 "name": SOURCE.format(release="release I", table=4), "url": RELEASE_I,
                 "page": PAGE, "year": YEAR, "license": LICENCE}]
        for field, table in (("ethnicity", 1), ("religion", 2), ("language", 3)):
            summed: dict[str, float] = defaultdict(float)
            whole = 0.0
            for m in names:
                unit = comps[field][fold(m)]
                for g, n in settle(field, m, unit["total"], unit["groups"], unit["stars"]).items():
                    summed[g] += n
                whole += unit["total"]
            fields[field] = shares({g: n for g, n in summed.items() if n}, total=whole)
            fields[f"{field}_year"] = YEAR
            fields[f"{field}_note"] = NOTES[field] + (
                " Cells Monstat protects (printed z) are one bar, 'Suppressed (disclosure "
                "control)': their people are counted, their answers not published.") + joined
            cite.append({"field": field, "name": SOURCE.format(release="release II", table=table),
                         "url": RELEASE_II, "page": PAGE, "year": YEAR, "license": LICENCE})
        for level in ("admin1", "admin2"):
            shape = drawn[level][k]
            records.append(record(f"MNE-2023-{level}-{k}", shape["name"], level=level,
                                  parent="MNE", country="MNE", match_by="shape_id",
                                  shape_id=shape["id"], sources=cite, **fields))
        log(f"  {' + '.join(names)}: {total:,.0f}, median {median}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("montenegro: Monstat, 2023 census")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
