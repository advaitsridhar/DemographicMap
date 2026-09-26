#!/usr/bin/env python3
"""Grenada: the 2021 census by parish, from the Central Statistical Office's preliminary results.

The CSO's "2021 National Housing & Population Census Results (Preliminary)"
tabulates the non-institutional population in private dwellings, 108,279
people, by parish:

* Table 17, men and women -- the population and the sex ratio;
* Tables 11 to 15, men and women by five-year age group -- the median age;
* Table 22, ethnic group; Table 23, religion.

The CSO counts the Town of St. George apart from the rest of the parish; the
map draws one Saint George, so the two are summed. Carriacou and Petite
Martinique are the map's Southern Grenadine Islands.

The age tables print each parish as a block of age groups closed by its
total, the parish's name wherever it fell; a block is known by its total,
which must be exactly one parish's men, women and total in Table 17. The
tables label the group 80-84 "80-89" (85-89 follows it); groups are read by
their place.

Checks, each of which stops the run: Table 17's parishes make 108,279, men
and women each; every age block's groups make its total; each of Table 22's
and Table 23's rows makes its total, their columns make the total row, and
their parish totals are Table 17's.

Usage:
    python -m scripts.fetch_census.grenada_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = PROCESSED / "grenada_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
REPORT = ("https://stats.gov.gd/wp-content/uploads/2025/04/"
          "2021-National-Housing-Population-Census-Results-Latest-PRELIMINARY.pdf")
SOURCE = ("Central Statistical Office of Grenada, 2021 National Housing & Population Census "
          "Results (Preliminary)")
YEAR = 2021
TOTAL = 108_279
PARISHES = ("rest of st george", "town of st george", "st john", "st mark", "st patrick",
            "st andrew", "st david", "carriacou")
MAP = {"Saint George": ("rest of st george", "town of st george"),
       "Saint John": ("st john",), "Saint Mark": ("st mark",),
       "Saint Patrick": ("st patrick",), "Saint Andrew": ("st andrew",),
       "Saint David": ("st david",), "Southern Grenadine Islands": ("carriacou",)}
AGES = [(lo, lo + 4) for lo in range(0, 95, 5)] + [(95, None)]
ETHNIC_COLUMNS = ("African descent", "Indigenous", "East Indian", "Chinese", "Syrian/Lebanese",
                  "White", "Hispanic", "Other Asian", "Mixed (African and East Indian)",
                  "Mixed (Black and White)", "Mixed (other)", "Other", "Not stated")
RELIGION = {
    "ANGLICAN": "Anglican", "BUDDHIST": "Buddhist", "BAHAI": "Baha'i",
    "BRETHREN": "Brethren", "CHURCH OF GOD": "Church of God", "EVANGELICAL": "Evangelical",
    "HINDU": "Hindu", "INDEPENDENT BAPTISTE": "Baptist",
    "JEHOVAH WITNESSES": "Jehovah's Witnesses", "METHODIST": "Methodist",
    "MENNONITE": "Mennonite", "MORAVIAN": "Moravian", "MORMOM": "Mormon",
    "MUSLIM": "Muslim", "PENTECOSTAL": "Pentecostal", "PRESBYTERIAN": "Presbyterian",
    "RASTAFARIAN": "Rastafarian", "ROMAN CATHOLIC": "Roman Catholic",
    "SALVATION ARMY": "Salvation Army", "SEVENTH DAY ADVENTIST": "Seventh-day Adventist",
    "SPIRITUAL BAPTIST": "Spiritual Baptist", "LUTHERAN": "Lutheran", "ATHEIST": "Atheist",
    "NO RELIGIOUS AFFILIATION": "No religion", "OTHER (SPECIFY)": "Other religion",
    "NOT STATED": "Not stated", "TOTAL": "_total",
}
FIGURE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+|-)$")


def value(token: str) -> int:
    return 0 if token == "-" else int(token.replace(",", ""))


def present(counts: dict[str, float]) -> list[dict]:
    return shares({k: v for k, v in counts.items() if v})


def parish_key(label: str) -> str | None:
    """"TOWN OF ST.GEORGE" -> "town of st george"; the CSO runs words together."""
    flat = fold(label)
    if flat.startswith("carriacou"):
        return "carriacou"
    if flat in ("stgeorge", "restofstgeorge"):
        return "rest of st george"
    for key in PARISHES:
        if fold(key) == flat:
            return key
    if flat == "total":
        return "total"
    return None


def split(line: str, width: int) -> tuple[list[str], list[int] | None]:
    tokens = line.split()
    if len(tokens) >= width and all(FIGURE.match(t) for t in tokens[-width:]):
        return tokens[:-width], [value(t) for t in tokens[-width:]]
    return tokens, None


def rows(lines: list[str], width: int, known) -> list[tuple[str, list[int]]]:
    """(label, figures) for each line with ``width`` figures, its wrapped label rebuilt.

    A label may begin on the lines above its figures and end on the lines
    below. The words gathered above (headings among them) are tried longest
    first, down to none, each with the line's own words and then run on with
    the lines below until ``known`` accepts them; the lines below that a label
    takes are not the next one's.
    """
    parsed = [split(line, width) for line in lines if line.strip()]
    out, pending, i = [], [], 0
    while i < len(parsed):
        words, figures = parsed[i]
        i += 1
        if figures is None:
            pending += words
            continue
        following = []
        j = i
        while j < len(parsed) and parsed[j][1] is None:
            following.append(parsed[j][0])
            j += 1
        chosen = None
        for k in range(len(pending) + 1):
            label, used = pending[k:] + list(words), 0
            while not known(" ".join(label)) and used < len(following):
                label += following[used]
                used += 1
            if known(" ".join(label)):
                chosen = (" ".join(label), used)
                break
        if chosen is None:
            raise SystemExit(f"grenada_census: row {' '.join(pending + words)!r} with "
                             f"{figures} is not one this reads")
        out.append((chosen[0], figures))
        pending = []
        i += chosen[1]
    return out


def table_17(lines: list[str]) -> dict[str, tuple[int, int, int]]:
    """{parish: (men, women, total) in 2021} from Table 17."""
    out = {}
    for label, figures in rows(lines, 6, lambda l: parish_key(l) is not None):
        men, women, total = figures[:3]
        if men + women != total:
            raise SystemExit(f"grenada_census: Table 17's {label} does not add up")
        out[parish_key(label)] = (men, women, total)
    whole = out.pop("total", None)
    if whole is None or whole[2] != TOTAL or set(out) != set(PARISHES):
        raise SystemExit(f"grenada_census: Table 17 has {sorted(out)} and total {whole}")
    for i in range(3):
        if sum(v[i] for v in out.values()) != whole[i]:
            raise SystemExit("grenada_census: Table 17's parishes do not make its total")
    return out


AGE_LINE = re.compile(r"^(\d+)\s*-\s*(\d+)$|^(\d+)\s*\+$")


def age_blocks(lines: list[str]) -> list[dict[str, Any]]:
    """[{"groups": [(low, high, both)], "total": (men, women, both)}] from Tables 11-15."""
    blocks, groups, label = [], [], None
    for line in lines:
        text = line.strip()
        if AGE_LINE.match(text):
            label = text
            continue
        if text.upper() == "TOTAL":
            label = "TOTAL"
            continue
        tokens = text.split()
        if len(tokens) < 3 or not all(FIGURE.match(t) for t in tokens[-3:]):
            continue
        # "CARRIACOU& 45-49 122 100 222": the parish, its group and its figures on one line.
        inline = [t for t in tokens[:-3] if AGE_LINE.match(t)]
        if inline:
            label = inline[-1]
        if label is None:
            continue
        men, women, both = (value(t) for t in tokens[-3:])
        if label == "TOTAL":
            if len(groups) != len(AGES):
                raise SystemExit(f"grenada_census: an age block has {len(groups)} groups")
            for n, (lo, hi) in enumerate(AGES):
                if groups[n][0] != (lo, hi):
                    log(f"  age tables: the group of {lo}-{hi} is labelled {groups[n][2]!r}; "
                        "read by its place")
            made = [sum(g[1][k] for g in groups) for k in range(3)]
            if made != [men, women, both]:
                raise SystemExit(f"grenada_census: an age block makes {made}, its total "
                                 f"{[men, women, both]}")
            blocks.append({"groups": [(lo, hi, g[1][2]) for (lo, hi), g in zip(AGES, groups)],
                           "total": (men, women, both)})
            groups = []
        else:
            m = AGE_LINE.match(label)
            span = (int(m[1]), int(m[2])) if m[1] else (int(m[3]), None)
            groups.append((span, (men, women, both), label))
        label = None
    return blocks


def grid(lines: list[str], width: int, known, what: str) -> dict[str, list[int]]:
    """{label: figures} for a table whose last column is each row's total, checked."""
    out = {label: figures for label, figures in rows(lines, width, known)}
    for label, figures in out.items():
        if sum(figures[:-1]) != figures[-1]:
            raise SystemExit(f"grenada_census: {what}'s {label} makes {sum(figures[:-1]):,} "
                             f"of {figures[-1]:,}")
    return out


def pages() -> list[list[str]]:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(http_get(REPORT, binary=True, cache=False))) as pdf:
        return [(page.extract_text() or "").splitlines() for page in pdf.pages]


def table(all_pages: list[list[str]], number: int) -> list[str]:
    """The lines of the page holding Table ``number`` after its title.

    The contents pages are passed over: their entries wrap, so a title's
    first line there has no dotted leader to tell it by.
    """
    title = re.compile(rf"^Table\s*{number}\s*\.")
    for lines in all_pages:
        if any(line.startswith("Table of Contents") for line in lines):
            continue
        for i, line in enumerate(lines):
            if title.match(line) and not re.search(r"\.{4,}", line):
                rest = lines[i + 1:]
                nxt = next((k for k, l in enumerate(rest) if re.match(r"^Table\s*\d+\s*\.", l)),
                           len(rest))
                return rest[:nxt]
    raise SystemExit(f"grenada_census: the report has no Table {number}")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    report = pages()
    sexes = table_17(table(report, 17))
    blocks = [b for n in range(11, 16) for b in age_blocks(table(report, n))]
    ages: dict[str, list] = {}
    for block in blocks:
        match = [p for p, v in sexes.items() if v == block["total"]]
        if block["total"][2] == TOTAL:
            continue
        if len(match) != 1 or match[0] in ages:
            raise SystemExit(f"grenada_census: an age block totalling {block['total']} is "
                             f"{match}")
        ages[match[0]] = block["groups"]
    if set(ages) != set(PARISHES):
        raise SystemExit(f"grenada_census: age blocks found for {sorted(ages)}")
    parish_known = (lambda l: parish_key(l) is not None)
    ethnic = grid(table(report, 22), 14, parish_known, "Table 22")
    religion = grid(table(report, 23), 9, lambda l: fold(l) in {fold(k) for k in RELIGION},
                    "Table 23")
    ethnic = {parish_key(k): v for k, v in ethnic.items()}
    religion = {next(v for k, v in RELIGION.items() if fold(k) == fold(label)): figures
                for label, figures in religion.items()}
    for key in PARISHES:
        if ethnic[key][-1] != sexes[key][2]:
            raise SystemExit(f"grenada_census: Table 22's {key} is {ethnic[key][-1]:,}")
    for j, key in enumerate(PARISHES):
        column = {name: figures[j] for name, figures in religion.items() if name != "_total"}
        if sum(column.values()) != religion["_total"][j] or religion["_total"][j] != sexes[key][2]:
            raise SystemExit(f"grenada_census: Table 23's {key} does not make its total")
    for j in range(14):
        if sum(v[j] for k, v in ethnic.items() if k != "total") != ethnic["total"][j]:
            raise SystemExit(f"grenada_census: Table 22's column {j + 1} does not add up")
    log(f"  eight parishes making {TOTAL:,} in Tables 17, 22 and 23 and in their age blocks")

    admin1 = json.loads((SITE / "admin1" / "GRD.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    records = []
    for name, keys in MAP.items():
        shape = shapes.get(fold(name))
        if shape is None:
            raise SystemExit(f"grenada_census: {name} has no polygon")
        men = sum(sexes[k][0] for k in keys)
        women = sum(sexes[k][1] for k in keys)
        groups = [(lo, hi, sum(dict(((g[0], g[1]), g[2]) for g in ages[k])[(lo, hi)]
                               for k in keys)) for lo, hi in AGES]
        eth = {c: sum(ethnic[k][j] for k in keys) for j, c in enumerate(ETHNIC_COLUMNS)}
        rel: dict[str, int] = {}
        for label, figures in religion.items():
            if label != "_total":
                rel[label] = rel.get(label, 0) + sum(figures[PARISHES.index(k)] for k in keys)
        joined = " (the Town of St. George and the rest of the parish together)" \
            if len(keys) > 1 else ""
        records.append(record(
            f"GRD-CSO-{fold(name)}", shape["name"], level="admin1", parent="GRD",
            country="GRD", match_by="shape_id", shape_id=shape["id"],
            population=measure(men + women, year=YEAR, source=SOURCE),
            population_note=("The 2021 census's non-institutional population in private "
                             f"dwellings{joined}, Table 17."),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            sex_ratio_note="Men per thousand women, Table 17.",
            median_age=measure(grouped_median(groups), unit="years", year=YEAR, source=SOURCE),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person (Tables 11 to 15)."),
            ethnicity=present(eth), ethnicity_year=YEAR,
            ethnicity_note="Ethnic group of the non-institutional population, Table 22.",
            religion=present(rel), religion_year=YEAR,
            religion_note=("Religion of the non-institutional population, Table 23; "
                           "\"Independent Baptiste\" is written as Baptist and \"No religious "
                           "affiliation\" as No religion."),
            sources=[{"field": "population/sex_ratio/median_age/ethnicity/religion",
                      "name": SOURCE, "url": REPORT, "year": YEAR}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} parishes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
