#!/usr/bin/env python3
"""Liberia -- the 2022 Population and Housing Census, by county and district.

LISGIS published the 2022 census's final results in 2023 and a thematic report
on population size, distribution and structure in June 2024. Its own host no
longer serves either file to a script (the final results' address answers a
2 kB page), so both are read as the Internet Archive keeps them.

* **Final Results**: Table A3, the population by sex and county; Table A7,
  the population by ethnic group, nationally; and Appendix B, Tables B1-B15,
  the population by county, administrative district and sex.
* **Thematic Report on Population Size, Distribution and Structure**:
  Appendices 4a-18a, the population of each county by five-year age group
  and sex; Table 4.3, religious affiliation by county; and Table 4.1, which
  distributes each ethnic group across the counties (each row adds to 100).

Written for the 15 counties: population and sex ratio (Table A3), median age
(interpolated in the county's five-year groups), religion (Table 4.3) and
ethnicity. The census publishes no ethnic composition of a county as such:
each county's share of each group is in Table 4.1, to one decimal, and each
group's national count in Table A7, so a county's count of a group is the two
multiplied, and its composition those counts over its population. Every share
carries the rounding of Table 4.1, a twentieth of a per cent of the group's
national count, and the note says so. Table A7 does not print the "Other
African" group's count; it is taken as the national population less the
groups it prints, less the non-Africans of Table 4.2 (0.2 per cent).

**The districts.** The boundary file draws the 136 districts of the 2008
census, and the 2022 census counts 155. Where a county's districts are the
same in both lists, each polygon gets its district's count and sex ratio:
Bong, Gbarpolu, Grand Cape Mount, Grand Gedeh, Maryland, Nimba, River Gee and
Rivercess, and Grand Bassa, where Owensgrove is the one district the table
does not print. Elsewhere the 2022 list holds districts the 2008 one does not
-- Tehr in Bomi, Penicess in Grand Kru, four more in Lofa, Kabah
Administrative in Margibi, eleven townships in Montserrado, Jlah, Krah,
Sarboh and Bar-Nakay in Sinoe -- and the publications do not say which drawn
district each was made from, so no 2022 figure is put on those polygons and
each says why.

**Corrections the arithmetic makes.** Gounwolaila's row is printed under
Grand Cape Mount and under Margibi and not under Gbarpolu; each of the first
two counties' districts make its total only without it, and Gbarpolu's fall
short by exactly its figures, so it is read as Gbarpolu's. Grand Bassa's
seven printed districts fall 14,422 short of the county (7,391 men, 7,031
women), and Owensgrove, the district missing from its table, says so.

**Checks.** Men and women make every total; each county's age groups make its
total and its sexes as Table A3 prints them; the counties make Liberia,
5,250,187; each bound county's districts make the county; each religion row
makes 100; each ethnic group's row makes 100.

Usage:
    python -m scripts.fetch_census.liberia_census
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from probe_pdf import PAGE_BREAK, laid_out  # noqa: E402

FINAL = "https://www.lisgis.gov.lr/document/LiberiaCensus2022Report.pdf"
FINAL_CAPTURE = f"https://web.archive.org/web/2024id_/{FINAL}"
THEMATIC = ("https://lisgis.gov.lr/censusreport/thematic/"
            "ThematicReportonPopulationSizeDistributionandStructure.pdf")
THEMATIC_CAPTURE = f"https://web.archive.org/web/2025id_/{THEMATIC}"
PUBLISHER = "Liberia Institute of Statistics and Geo-Information Services (LISGIS)"
SRC_POP = f"{PUBLISHER}, 2022 Population and Housing Census, Final Results, Table A3"
SRC_DIST = (f"{PUBLISHER}, 2022 Population and Housing Census, Final Results, Appendix B "
            "(Tables B1-B15)")
SRC_AGE = (f"{PUBLISHER}, 2022 Population and Housing Census, Thematic Report on Population "
           "Size, Distribution and Structure (2024), Appendices 4a-18a")
SRC_REL = (f"{PUBLISHER}, 2022 Population and Housing Census, Thematic Report on Population "
           "Size, Distribution and Structure (2024), Table 4.3")
SRC_ETH = (f"{PUBLISHER}, 2022 Population and Housing Census, Thematic Report on Population "
           "Size, Distribution and Structure (2024), Table 4.1, with Final Results Table A7")
LICENCE = "LISGIS publication (reuse with attribution)"
YEAR = 2022
NATIONAL = (5_250_187, 2_644_027, 2_606_160)
NON_AFRICAN_PCT = 0.2          # Table 4.2's national share, the one group not distributed
OUT = "liberia_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
UNIT = "males_per_100_females"

COUNTIES = ("Bomi", "Bong", "Gbarpolu", "Grand Bassa", "Grand Cape Mount", "Grand Gedeh",
            "Grand Kru", "Lofa", "Margibi", "Maryland", "Montserrado", "Nimba", "River Cess",
            "River Gee", "Sinoe")
# Counties whose 2022 districts are the 2008 districts the boundary file draws.
SAME_DISTRICTS = ("bong", "gbarpolu", "grandcapemount", "grandgedeh", "maryland", "nimba",
                  "rivergee", "rivercess", "grandbassa")
# The districts the 2022 census counts and the 2008 one did not, by county:
# the reason the county's drawn districts carry no 2022 figure.
NEW_DISTRICTS = {
    "bomi": "Tehr", "grandkru": "Penicess",
    "lofa": "Lukambeh, Wahasa, Waum and Tengia", "margibi": "Kabah Administrative",
    "montserrado": "eleven townships", "sinoe": "Jlah, Krah, Sarboh and Bar-Nakay",
}
# (county, the boundary file's reduced name) -> the census's reduced name.
ALIASES = {("grandbassa", "commonwealth2"): "commonwealth",
           ("grandcapemount", "commonwealth"): "commonwealthrobertsport"}
MISSING_ROW = {("grandbassa", "owensgrove")}
ETHNIC = ("Bassa", "Belle", "Dey", "Gbandi", "Gio", "Gola", "Grebo", "Kpelle", "Kissi",
          "Krahn", "Kru", "Lorma", "Mandingo", "Mano", "Mende", "Sapo", "Vai")
RELIGIONS = ("Christian", "Muslim", "Traditional African Religion", "Other religion",
             "No religion")
NUM = r"\d[\d,]*(?:\.\d+)?"


def key(name: str) -> str:
    """A district or county name reduced: lower case, "Number"/"#" as "no", without
    "County", "District" or what it puts in brackets."""
    s = re.sub(r"\([^)]*\)", " ", str(name or "").lower())
    s = re.sub(r"\bnumber\b|#|\bno\.", " no ", s)
    s = re.sub(r"\b(county|district|dist|statutory)\b", " ", s)
    return "".join(c for c in s if c.isalnum())


def number(text: str) -> float:
    return float(text.replace(",", ""))


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def rows(text: str, count: int) -> list[tuple[str, list[float]]]:
    """The lines of a page that are a name and exactly ``count`` figures."""
    # A name may hold a figure of its own ("Karluway Number 1"): the row is
    # whatever stands before exactly ``count`` figures at the line's end.
    row = re.compile(rf"^(?P<name>[A-Za-z].*?)\s+(?P<nums>{NUM}(?:\s+{NUM}){{{count - 1}}})$")
    out = []
    for line in (ln.strip() for ln in text.splitlines()):
        m = row.match(line)
        if m:
            out.append((" ".join(m.group("name").split()), [number(x) for x in
                                                           m.group("nums").split()]))
    return out


def pages_with(pages: list[str], *needles: str) -> list[str]:
    return [p for p in pages if all(n.lower() in " ".join(p.split()).lower() for n in needles)]


def read_counties(pages: list[str]) -> dict[str, tuple[int, int, int]]:
    """Table A3: {county key: (total, men, women)}, Liberia under "liberia"."""
    for page in pages_with(pages, "Table A3", "Distribution of the Population by Sex and County"):
        part = page.split("Table A3")[1].split("Table A4")[0]
        got = {key(n): (int(v[0]), int(v[1]), int(v[3])) for n, v in rows(part, 5)}
        if len(got) >= 16:
            return got
    raise SystemExit("liberia_census: Table A3 not found")


def read_ethnic_counts(pages: list[str]) -> dict[str, int]:
    """Table A7: {group: national count}."""
    for page in pages_with(pages, "Table A7", "Ethnic Affiliation"):
        part = page.split("Table A7")[1].split("Table A8")[0]
        got = {n: int(v[0]) for n, v in rows(part, 4)}
        if len(got) >= 17:
            return got
    raise SystemExit("liberia_census: Table A7 not found")


def read_districts(pages: list[str]) -> dict[str, dict[str, Any]]:
    """Appendix B: {county key: {"total": (t, m, f), "rows": [(name, (t, m, f))]}}."""
    out: dict[str, dict[str, Any]] = {}
    for page in pages:
        for block in re.split(r"(?=Table B\d+\s*:)", page)[1:]:
            if "Administrative District" not in block:
                continue
            county, items = None, []
            for line in (ln.strip() for ln in block.splitlines()[1:]):
                found = rows(line, 3)
                if not found:
                    # A name the table breaks over two lines ("Commonwealth" /
                    # "Robertsport"): the second line joins the row above.
                    if items and re.fullmatch(r"[A-Za-z .'/-]+", line) \
                            and not line.startswith(("Total", "Table", "APPENDIX")):
                        items[-1] = (f"{items[-1][0]} {line}", items[-1][1])
                    continue
                name, v = found[0]
                t = (int(v[0]), int(v[1]), int(v[2]))
                if county is None:
                    county = key(name)
                    out[county] = {"total": t, "rows": items, "label": name}
                else:
                    items.append((name, t))
    return out


AGE_ROW = re.compile(rf"^(?P<low>\d+)\s*(?:[-–]\s*(?P<high>\d+)|\+)\s+"
                     rf"(?P<nums>{NUM}(?:\s+{NUM}){{8}})$")


def read_ages(pages: list[str]) -> dict[str, list[tuple[int, int | None, int, int, int]]]:
    """Appendices 4a-18a: {county key: [(low, high, total, men, women), ...]},
    from each row's last three columns (the county's men, women and total)."""
    out: dict[str, list[tuple[int, int | None, int, int, int]]] = {}
    for page in pages:
        m = re.search(r"Appendix \d+[a-z]: Distribution of population by age, sex and residence\s*"
                      r"[-–]\s*(?P<county>.+?)\s+Urban\b", " ".join(page.split()))
        if not m:
            continue
        groups = []
        for line in (ln.strip() for ln in page.splitlines()):
            g = AGE_ROW.match(line)
            if g:
                v = [int(number(x)) for x in g.group("nums").split()]
                groups.append((int(g.group("low")),
                               int(g.group("high")) if g.group("high") else None,
                               v[8], v[6], v[7]))
        out[key(m.group("county"))] = groups
    return out


def read_religion(pages: list[str]) -> dict[str, dict[str, float]]:
    """Table 4.3 (it runs over two pages): {county key: {religion: share}}."""
    out: dict[str, dict[str, float]] = {}
    at = [i for i, p in enumerate(pages) if "Table 4.3: Religious affiliation by type of "
          "residence and county" in " ".join(p.split()) and "Christian" in p]
    for page in [pages[i + d] for i in at[:1] for d in (0, 1) if i + d < len(pages)]:
        for name, v in rows(page, 6):
            k = key(name)
            if k in {key(c) for c in COUNTIES} and k not in out:
                if abs(v[5] - 100) > 0.05 or abs(sum(v[:5]) - 100) > 0.3:
                    raise SystemExit(f"liberia_census: Table 4.3: {name}'s religions make "
                                     f"{sum(v[:5]):.1f}")
                out[k] = dict(zip(RELIGIONS, v[:5]))
        if len(out) == len(COUNTIES):
            return out
    raise SystemExit(f"liberia_census: Table 4.3 has {sorted(out)}")


def read_ethnic_spread(pages: list[str]) -> dict[str, list[float]]:
    """Table 4.1: {group: [its share in each county, in COUNTIES order]}."""
    for page in pages_with(pages, "Table 4.1", "Population by ethnic groups and county"):
        got = {}
        for name, v in rows(page, 16):
            if abs(v[15] - 100) > 0.05 or abs(sum(v[:15]) - 100) > 0.35:
                raise SystemExit(f"liberia_census: Table 4.1: {name} makes {sum(v[:15]):.1f}")
            got[name] = v[:15]
        if len(got) >= 18:
            return got
    raise SystemExit("liberia_census: Table 4.1 not found")


def median(groups: list[tuple[int, int | None, int, int, int]]) -> float | None:
    base = sum(g[2] for g in groups)
    half, before = base / 2, 0
    for low, high, n, _, _ in groups:
        if before + n >= half:
            if high is None or n <= 0:
                return None
            return round(low + (half - before) / n * (high - low + 1), 1)
        before += n
    return None


def place_strays(districts: dict[str, dict[str, Any]]) -> list[str]:
    """Move a row printed under the wrong county to the one its figures make
    whole (Gounwolaila), and drop its other copies; the moves, in words."""
    said = []

    def short(c: str) -> tuple[int, int, int]:
        d = districts[c]
        return tuple(d["total"][i] - sum(t[i] for _, t in d["rows"]) for i in range(3))

    for c, d in districts.items():
        for name, t in list(d["rows"]):
            over = tuple(-x for x in short(c))
            if over != t:
                continue
            homes = [o for o in districts if o != c and short(o) == t]
            d["rows"].remove((name, t))
            if len(homes) == 1:
                districts[homes[0]]["rows"].append((name, t))
                said.append(f"{name} {t} printed under {d['label']} belongs to "
                            f"{districts[homes[0]]['label']}")
            else:
                said.append(f"{name} {t} printed again under {d['label']}: dropped")
    return said


def check(counties: dict[str, tuple[int, int, int]], districts: dict[str, dict[str, Any]],
          ages: dict[str, list]) -> None:
    for c, (t, m, f) in counties.items():
        if m + f != t:
            raise SystemExit(f"liberia_census: {c}: men and women make {m + f:,}, not {t:,}")
    if counties.get("liberia") != NATIONAL:
        raise SystemExit(f"liberia_census: Liberia is {counties.get('liberia')}")
    drawn = [key(c) for c in COUNTIES]
    for col in range(3):
        if sum(counties[c][col] for c in drawn) != NATIONAL[col]:
            raise SystemExit("liberia_census: the counties do not make Liberia")
    for c in drawn:
        g = ages.get(c, [])
        if len(g) != 17 or tuple(sum(x[i] for x in g) for i in (2, 3, 4)) != counties[c]:
            raise SystemExit(f"liberia_census: {c}'s ages ({len(g)} groups) do not make "
                             f"{counties[c]}")
        if c not in districts or districts[c]["total"] != counties[c]:
            raise SystemExit(f"liberia_census: Appendix B's {c} is not Table A3's")
    for c in SAME_DISTRICTS:
        made = tuple(sum(t[i] for _, t in districts[c]["rows"]) for i in range(3))
        if made != counties[c] and c != "grandbassa":
            raise SystemExit(f"liberia_census: {c}'s districts make {made}, not {counties[c]}")


def ethnic_shares(spread: dict[str, list[float]], counts: dict[str, int],
                  counties: dict[str, tuple[int, int, int]]
                  ) -> tuple[dict[str, dict[str, float]], int]:
    """{county key: {group: share of the county}} and the Other African count used."""
    named = {g: counts[g] for g in ETHNIC}
    other_liberian = next(v for k, v in counts.items() if k.lower().startswith("other liberian"))
    other_african = round(NATIONAL[0] - sum(named.values()) - other_liberian
                          - NON_AFRICAN_PCT / 100 * NATIONAL[0])
    national = {**named, "Other Liberian": other_liberian, "Other African": other_african}
    rows_ = {}
    for name, v in spread.items():
        label = ("Other Liberian" if name.lower().startswith("other liberian") else
                 "Other African" if name.lower().startswith("other african") else name)
        if label not in national:
            raise SystemExit(f"liberia_census: Table 4.1's {name!r} has no national count")
        rows_[label] = v
    if set(rows_) != set(national):
        raise SystemExit(f"liberia_census: Table 4.1 lacks {sorted(set(national) - set(rows_))}")
    out = {}
    for i, county in enumerate(COUNTIES):
        c = key(county)
        out[c] = {g: 100 * rows_[g][i] / 100 * national[g] / counties[c][0] for g in national}
    return out, other_african


def shares_list(shares: dict[str, float]) -> list[dict[str, Any]]:
    out = [{"group": g, "pct": round(p, 1)} for g, p in shares.items() if round(p, 1) > 0]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def county_fields(c: str, label: str, counties: dict, ages: dict, religion: dict,
                  ethnicity: dict) -> dict[str, Any]:
    t, m, f = counties[c]
    return {
        "population": measure(t, year=YEAR, source=SRC_POP),
        "population_note": f"The 2022 census's count for {label}.",
        "sex_ratio": measure(round(100 * m / f, 1), unit=UNIT, year=YEAR, source=SRC_POP),
        "median_age": measure(median(ages[c]), unit="years", year=YEAR, source=SRC_AGE),
        "median_age_note": ("Interpolated within the five-year age group that holds the middle "
                            "person, from the 2022 census's count of the county by age."),
        "religion": shares_list(religion[c]),
        "religion_year": YEAR,
        "religion_note": "Religious affiliation as the 2022 census counts it.",
        "ethnicity": shares_list(ethnicity[c]),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Ethnic group as the 2022 census counts it. The census prints each group's spread "
            "across the counties, to one decimal, and each group's national count, so each "
            "share here is the two multiplied over the county's population; the rounding of "
            "that one decimal can move a large group's share in a small county by up to about "
            "half a percentage point. Non-Africans, 0.2 per cent of Liberia, are not spread by "
            "county and are not shown."),
        "sources": [
            {"field": "population/sex_ratio", "name": SRC_POP, "url": FINAL,
             "archived": FINAL_CAPTURE, "license": LICENCE, "year": YEAR},
            {"field": "median_age", "name": SRC_AGE, "url": THEMATIC,
             "archived": THEMATIC_CAPTURE, "license": LICENCE, "year": YEAR},
            {"field": "religion", "name": SRC_REL, "url": THEMATIC,
             "archived": THEMATIC_CAPTURE, "license": LICENCE, "year": YEAR},
            {"field": "ethnicity", "name": SRC_ETH, "url": THEMATIC,
             "archived": THEMATIC_CAPTURE, "license": LICENCE, "year": YEAR},
        ],
    }


AGE_BY_COUNTY = ("The 2022 census's published results give ages by county, not by district, "
                 "so no median age is shown for a district.")
COMPOSITION_BY_COUNTY = ("The 2022 census asks {field}, and its published results give it by "
                         "county, not by district.")


def district_fields(name: str, t: tuple[int, int, int] | None, county_label: str,
                    why: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "median_age": gap(NOT_AVAILABLE, AGE_BY_COUNTY),
        "religion": gap(NOT_AVAILABLE, COMPOSITION_BY_COUNTY.format(field="religion")),
        "ethnicity": gap(NOT_AVAILABLE, COMPOSITION_BY_COUNTY.format(field="ethnicity")),
    }
    if t is None:
        out["population"] = gap(NOT_AVAILABLE, why)
        out["sex_ratio"] = gap(NOT_AVAILABLE, why)
        return out
    out.update({
        "population": measure(t[0], year=YEAR, source=SRC_DIST),
        "population_note": f"The 2022 census's count for {name}, in {county_label}.",
        "sex_ratio": measure(round(100 * t[1] / t[2], 1), unit=UNIT, year=YEAR,
                             source=SRC_DIST),
        "sources": [{"field": "population/sex_ratio", "name": SRC_DIST, "url": FINAL,
                     "archived": FINAL_CAPTURE, "license": LICENCE, "year": YEAR}],
    })
    return out


def build(tables: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    counties, districts = tables["counties"], tables["districts"]
    county_of = {}
    for shape in admin1:
        c = key(shape["name"])
        if c not in {key(x) for x in COUNTIES}:
            raise SystemExit(f"liberia_census: county polygon {shape['name']!r} is no county")
        county_of[shape["id"]] = c
    if len(set(county_of.values())) != len(COUNTIES):
        raise SystemExit("liberia_census: the county polygons are not the 15 counties")
    label = {key(c): c for c in COUNTIES}
    records = []
    for shape in admin1:
        c = county_of[shape["id"]]
        records.append(record(
            f"LBR-2022-county-{c}", shape["name"], level="admin1", parent="LBR", country="LBR",
            match_by="shape_id", shape_id=shape["id"],
            **county_fields(c, f"{label[c]} County", counties, tables["ages"],
                            tables["religion"], tables["ethnicity"])))
    used: dict[str, set[str]] = {}
    for shape in admin2:
        c = county_of.get(shape["parent"])
        if c is None:
            raise SystemExit(f"liberia_census: {shape['name']!r} is drawn in no county")
        k = key(shape["name"])
        k = ALIASES.get((c, k), k)
        where = f"{label[c]} County"
        if c in SAME_DISTRICTS:
            found = [(n, t) for n, t in districts[c]["rows"] if key(n) == k]
            if (c, k) in MISSING_ROW and not found:
                d = districts[c]
                short = tuple(d["total"][i] - sum(t[i] for _, t in d["rows"]) for i in range(3))
                why = (f"The 2022 census's final results print no row for {shape['name']}; the "
                       f"districts they print for {where} fall {short[0]:,} people short of the "
                       "county's count, so no figure is shown here.")
                fields = district_fields(shape["name"], None, where, why)
            elif len(found) == 1 and found[0][0] not in used.setdefault(c, set()):
                used[c].add(found[0][0])
                fields = district_fields(found[0][0], found[0][1], where, None)
            else:
                raise SystemExit(f"liberia_census: {shape['name']!r} ({c}, {k}) matches "
                                 f"{found}")
        else:
            why = (f"The 2022 census counts {where} in districts that are not those drawn here: "
                   f"its list adds {NEW_DISTRICTS[c]}, made since the 2008 census, without "
                   "saying which drawn district each came from, so no 2022 figure is shown.")
            fields = district_fields(shape["name"], None, where, why)
        records.append(record(
            f"LBR-2022-{c}-{key(shape['name'])}", shape["name"], level="admin2", parent="LBR",
            country="LBR", match_by="shape_id", shape_id=shape["id"], **fields))
    for c in SAME_DISTRICTS:
        left = sorted(n for n, _ in districts[c]["rows"] if n not in used.get(c, set()))
        if left:
            raise SystemExit(f"liberia_census: {c}'s districts on no polygon: {left}")
    return records


def read() -> dict[str, Any]:
    final = http_get(FINAL_CAPTURE, binary=True, timeout=300)
    thematic = http_get(THEMATIC_CAPTURE, binary=True, timeout=300)
    assert isinstance(final, bytes) and isinstance(thematic, bytes)
    for label, blob in (("Final Results", final), ("Thematic report", thematic)):
        if not blob.startswith(b"%PDF"):
            raise SystemExit(f"liberia_census: the {label} capture is not a PDF")
        log(f"  {label}: {len(blob):,} bytes, sha256 {digest(blob)}")
    p_final = laid_out(final).split(PAGE_BREAK)
    p_them = laid_out(thematic).split(PAGE_BREAK)
    districts = read_districts(p_final)
    for line in place_strays(districts):
        log(f"  Appendix B: {line}")
    tables = {"counties": read_counties(p_final), "districts": districts,
              "ages": read_ages(p_them), "religion": read_religion(p_them)}
    check(tables["counties"], districts, tables["ages"])
    tables["ethnicity"], other_african = ethnic_shares(
        read_ethnic_spread(p_them), read_ethnic_counts(p_final), tables["counties"])
    log(f"  Other African, nationally: {other_african:,}")
    return tables


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    tables = read()
    for county in COUNTIES:
        c = key(county)
        made = sum(tables["ethnicity"][c].values())
        log(f"  {county}: {tables['counties'][c]}, median {median(tables['ages'][c])}, "
            f"religion {tables['religion'][c]}, ethnic groups make {made:.1f}%: "
            f"{shares_list(tables['ethnicity'][c])[:3]}")
    admin1 = json.loads((SITE / "admin1" / "LBR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "LBR.units.json").read_text())
    records = build(tables, admin1, admin2)
    bound = sum(1 for r in records if r["level"] == "admin2" and "value" in r["population"])
    log(f"  {len(records)} records: {bound} districts with a 2022 count")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
