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
does not print. Elsewhere the 2022 list holds districts the 2008 census does
not list -- Tehr in Bomi, Penicess in Grand Kru, four more in Lofa,
Farmington and Kabah Administrative in Margibi, eleven townships in
Montserrado, Jlah, Krah, Sarboh and Bar-Nakay in Sinoe -- or leaves out a
district drawn here, and does not say which drawn district a new one was made
from, so no 2022 figure is put on those polygons and each says what the list
holds (``NOT_THE_DRAWN``).

**Corrections the arithmetic makes.** Gounwolaila's row is printed under
Grand Cape Mount and under Margibi and not under Gbarpolu; each of the first
two counties' districts make its total only without it, and Gbarpolu's fall
short by exactly its figures, so it is read as Gbarpolu's. Grand Bassa's
seven printed districts fall 14,422 short of the county (7,391 men, 7,031
women), which is Owensgrove's count, the one district missing from its
table: the same arithmetic.

**The districts' ground.** Each bound district's 2022 count is set beside
the 2008 census's count of the district of the same name, as Statoids lists
the 2008 census report's 136 districts. A district whose count changes by
more than a population does in the fourteen years (check_rollups' bounds:
5% a year up, 3% down) is shown with a note giving the 2008 count and
saying that the 2022 census's district may not be the ground drawn here.
Most of those are the districts of county capitals and mining areas (Tchien,
Zwedru's; Potupo, Fish Town's; Commonwealth, Robertsport's; Central
Rivercess), and Maryland's -- Pleebo/Sodoken nearly doubled while Gwelekpoken,
Whojah, Nyorken and Karluway Number 2 lost from a third to more than half of
their people -- looks like ground moved between districts.

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
import html
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from check_rollups import DECLINE, GROWTH  # noqa: E402
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
SRC_THEMATIC = (f"{PUBLISHER}, 2022 Population and Housing Census, Thematic Report on Population "
                "Size, Distribution and Structure (2024)")
LICENCE = "LISGIS publication (reuse with attribution)"
YEAR = 2022
NATIONAL = (5_250_187, 2_644_027, 2_606_160)
NON_AFRICAN_PCT = 0.2          # Table 4.2's national share, the one group not distributed
OUT = "liberia_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
UNIT = "males_per_100_females"
# The 2008 census's districts, as Statoids lists the census report's 136.
STATOIDS = "https://statoids.com/ylr.html"
SRC_2008 = ("Liberia Institute of Statistics and Geo-Information Services (LISGIS), 2008 National "
            "Population and Housing Census, population by district, as Statoids lists it")
NATIONAL_2008 = 3_476_608
YEARS_BETWEEN = 14             # March 2008 to November 2022, in whole years
# HASC county codes -> county keys.
HASC = {"BG": "bong", "BM": "bomi", "CM": "grandcapemount", "GB": "grandbassa",
        "GD": "grandgedeh", "GK": "grandkru", "GP": "gbarpolu", "LF": "lofa", "MG": "margibi",
        "MO": "montserrado", "MY": "maryland", "NI": "nimba", "RG": "rivergee",
        "RI": "rivercess", "SI": "sinoe"}

COUNTIES = ("Bomi", "Bong", "Gbarpolu", "Grand Bassa", "Grand Cape Mount", "Grand Gedeh",
            "Grand Kru", "Lofa", "Margibi", "Maryland", "Montserrado", "Nimba", "River Cess",
            "River Gee", "Sinoe")
# Counties whose 2022 districts are the 2008 districts the boundary file draws.
SAME_DISTRICTS = ("bong", "gbarpolu", "grandcapemount", "grandgedeh", "maryland", "nimba",
                  "rivergee", "rivercess", "grandbassa")
# What each other county's 2022 list holds against the districts drawn: the
# reason its polygons carry no 2022 figure. Checked against Appendix B and
# against the 2008 census's list of districts.
NOT_THE_DRAWN = {
    "bomi": ("B1", "the four districts drawn here and Tehr, a district the 2008 census does not "
                   "list, without saying which drawn district it was made from"),
    "grandkru": ("B10", "the eighteen districts drawn here and Penicess, a district the 2008 "
                        "census does not list, without saying which drawn district it was "
                        "made from"),
    "lofa": ("B14", "the seven districts drawn here and Lukameh, Wahasa, Waum and Tengia, "
                    "districts the 2008 census does not list, without saying which drawn "
                    "districts they were made from"),
    "margibi": ("B5", "Gibi, Kakata and Mambahn Kabah, which are drawn here, Farmington and "
                      "Kabah Administrative, which the 2008 census does not list, and not "
                      "Firestone, without saying which drawn districts the two new ones were "
                      "made from"),
    "montserrado": ("B6", "Careysburg, St. Paul River, Todee and Greater Monrovia, eleven "
                          "townships apart from them (Paynesville, Gardnersville, New Georgia "
                          "and others) and no Commonwealth district, without saying which "
                          "drawn district each township lies in"),
    "sinoe": ("B8", "sixteen of the seventeen districts drawn here, not Dugbe River, and Jlah, "
                    "Krah, Sarboh and Bar-Nakay, districts the 2008 census does not list, "
                    "without saying which drawn districts they were made from"),
}
# Names the 2022 tables print that the 2008 list does not, by county: the
# check that NOT_THE_DRAWN's sentences still describe the tables.
LISTED_NEW = {"bomi": {"tehr"}, "grandkru": {"penicess"},
              "lofa": {"lukameh", "wahasa", "waum", "tengia"},
              "margibi": {"farmington", "kabahadministrative"},
              "sinoe": {"barnakay", "jlah", "krah", "sarboh"}}
# (county, the boundary file's reduced name) -> the census's reduced name.
ALIASES = {("grandbassa", "commonwealth2"): "commonwealth",
           ("grandcapemount", "commonwealth"): "commonwealthrobertsport"}
MISSING_ROW = {("grandbassa", "owensgrove")}
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
         9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
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
                # A line break kept in a printed name: "Pleebo/ Sodoken".
                name = re.sub(r"\s*/\s*", "/", name)
                t = (int(v[0]), int(v[1]), int(v[2]))
                if county is None:
                    county = key(name)
                    out[county] = {"total": t, "rows": items, "label": name}
                else:
                    items.append((name, t))
    return out


def read_2008(page: str) -> dict[str, dict[str, tuple[str, int]]]:
    """Statoids' table of the 2008 census's districts: {county key: {district
    key: (name, population)}}, checked to be 136 districts making 3,476,608."""
    out: dict[str, dict[str, tuple[str, int]]] = {}
    total = count = 0
    for row in re.findall(r"(?is)<tr\b.*?</tr>", page):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row)]
        if len(cells) < 3 or not re.fullmatch(r"LR\.[A-Z]{2}\.[A-Z]{2}", cells[1]) \
                or not re.fullmatch(r"[\d,]+", cells[2]):
            continue
        county = HASC[cells[1].split(".")[1]]
        pop = int(cells[2].replace(",", ""))
        out.setdefault(county, {})[key(cells[0])] = (cells[0], pop)
        total += pop
        count += 1
    if count != 136 or total != NATIONAL_2008:
        raise SystemExit(f"liberia_census: Statoids lists {count} districts of 2008 making "
                         f"{total:,}, not 136 making {NATIONAL_2008:,}")
    return out


# The 2008 list's names for districts the 2022 tables or the boundary file name
# otherwise, reduced: (county, key) -> the 2008 key.
NAMES_2008 = {("grandbassa", "commonwealth2"): "commonwealth",
              ("nimba", "weegbehyimahn"): "weegbehymahn"}


def change_note(name: str, where: str, then: int, now: int) -> str | None:
    """The note for a district whose count changes by more than a population
    does between the censuses, or None."""
    rate = (now / then) ** (1 / YEARS_BETWEEN) - 1
    if -DECLINE <= rate <= GROWTH:
        return None
    if rate > 0:
        told = (f"It is {now / then:.1f} times the 2008 census's {then:,} for the district of "
                f"that name, a rise of {rate:.1%} a year, faster than a population grows, so "
                "the district the 2022 census counts may take in ground the 2008 census "
                "counted in other districts.")
    else:
        told = (f"It is {now / then:.0%} of the 2008 census's {then:,} for the district of that "
                f"name, a fall of {-rate:.1%} a year, faster than a population shrinks, so the "
                "district the 2022 census counts may have lost ground to other districts since "
                "2008.")
    return f"The 2022 census's count for {name}, in {where}. {told}"


def check_not_the_drawn(districts: dict[str, dict[str, Any]],
                        d2008: dict[str, dict[str, tuple[str, int]]]) -> None:
    """NOT_THE_DRAWN's sentences against the tables: the new names are in the
    2022 table and not in the 2008 list, and the drawn names it says are left
    out are left out."""
    for c, new in LISTED_NEW.items():
        listed = {key(n) for n, _ in districts[c]["rows"]}
        if not new <= listed or new & set(d2008.get(c, {})):
            raise SystemExit(f"liberia_census: {c}'s 2022 table no longer lists {sorted(new)} "
                             f"as districts the 2008 census does not: {sorted(listed)}")
    left_out = {"margibi": "firestone", "sinoe": "dugberiver", "montserrado": "commonwealth"}
    for c, k in left_out.items():
        if k in {key(n) for n, _ in districts[c]["rows"]}:
            raise SystemExit(f"liberia_census: {c}'s 2022 table lists {k}")
    towns = [n for n, _ in districts["montserrado"]["rows"] if key(n) not in d2008["montserrado"]]
    if len(towns) != 11 or not all(re.search(r"(?i)township|borough", n) for n in towns):
        raise SystemExit(f"liberia_census: Montserrado's 2022 table lists {towns} apart")


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
            "across the counties, to one decimal, and each group's national count except Other "
            "African's, which is Liberia's population less the groups printed and the 0.2 per "
            "cent who are not African; each share here is the two multiplied over the "
            "county's population, and the rounding of that one decimal can move a large "
            "group's share in a small county by up to about half a percentage point. "
            "Non-Africans are not spread by county and are not shown."),
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
                    why: str | None, note: str | None = None,
                    then: int | None = None, beside: str | None = None) -> dict[str, Any]:
    """A district's record: its 2022 count and sex ratio, or ``why`` there are
    none, and the reasons for the fields the census publishes by county only,
    each citing the publication it rests on. ``note`` replaces the count's
    note; ``then`` is the 2008 census's count of the district, given in the
    note where the two are further apart than a population moves. ``beside``
    is the reason as it reads beside another source's figure."""
    out: dict[str, Any] = {
        "median_age": gap(NOT_AVAILABLE, AGE_BY_COUNTY),
        "religion": gap(NOT_AVAILABLE, COMPOSITION_BY_COUNTY.format(field="religion")),
        "ethnicity": gap(NOT_AVAILABLE, COMPOSITION_BY_COUNTY.format(field="ethnicity")),
        "sources": [{"field": "median_age/religion/ethnicity", "name": SRC_THEMATIC,
                     "url": THEMATIC, "archived": THEMATIC_CAPTURE, "license": LICENCE,
                     "year": YEAR},
                    {"field": "population/sex_ratio", "name": SRC_DIST, "url": FINAL,
                     "archived": FINAL_CAPTURE, "license": LICENCE, "year": YEAR}],
    }
    if t is None:
        # A gap's reason goes where another file's figure fills the field, and
        # OCHA's 2020 projection fills these districts: the reason is written
        # beside the figure too, or 55 districts show a 2020 figure beside
        # their neighbours' 2022 counts and never say why (Barclayville's
        # 15,153 people, Bodae's 155 men per 100 women). The gaps stay for
        # where OCHA gives nothing: its table of sexes has no Kpi or Wlogba.
        out["population"] = gap(NOT_AVAILABLE, why)
        out["sex_ratio"] = gap(NOT_AVAILABLE, why)
        if beside:
            out["population_note"] = out["sex_ratio_note"] = beside
        out["sources"][1]["field"] = "population note/sex_ratio note"
        return out
    moved = change_note(name, county_label, then, t[0]) if then else None
    out.update({
        "population": measure(t[0], year=YEAR, source=SRC_DIST),
        "population_note": note or moved or f"The 2022 census's count for {name}, in "
                                            f"{county_label}.",
        "sex_ratio": measure(round(100 * t[1] / t[2], 1), unit=UNIT, year=YEAR,
                             source=SRC_DIST),
    })
    if moved and not note:
        out["sources"].append({"field": "population note", "name": SRC_2008, "url": STATOIDS,
                               "year": 2008, "license": "Transcription of the census report; "
                                                        "terms of reuse not stated"})
    return out


def not_the_drawn(c: str) -> tuple[str, str]:
    """Why a county's districts carry no 2022 count (NOT_THE_DRAWN): as their
    gaps say it, and as it reads beside the figure OCHA gives each district."""
    table, holds = NOT_THE_DRAWN[c]
    listed = f"LISGIS's 2022 Final Results (Appendix B, Table {table}) list {holds}"
    return (f"{listed}, so no district's 2022 count is shown.",
            f"{listed}, so no district's 2022 count can be given; the figure shown is OCHA's "
            "projection for 2020.")


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
    d2008 = tables.get("districts_2008") or {}
    used: dict[str, set[str]] = {}
    for shape in admin2:
        c = county_of.get(shape["parent"])
        if c is None:
            raise SystemExit(f"liberia_census: {shape['name']!r} is drawn in no county")
        k = key(shape["name"])
        k = ALIASES.get((c, k), k)
        where = f"{label[c]} County"
        then = (d2008.get(c, {}).get(NAMES_2008.get((c, key(shape["name"])), key(shape["name"])))
                or (None, None))[1]
        if d2008 and c in SAME_DISTRICTS and then is None:
            raise SystemExit(f"liberia_census: {shape['name']!r} ({c}) is not in the 2008 list")
        if c in SAME_DISTRICTS:
            found = [(n, t) for n, t in districts[c]["rows"] if key(n) == k]
            if (c, k) in MISSING_ROW and not found:
                # The county's count less the districts printed: the same
                # arithmetic that moves Gounwolaila.
                d = districts[c]
                short = tuple(d["total"][i] - sum(t[i] for _, t in d["rows"]) for i in range(3))
                if min(short) <= 0 or short[1] + short[2] != short[0]:
                    raise SystemExit(f"liberia_census: {c} less its districts leaves {short}")
                printed = WORDS.get(len(d["rows"]), str(len(d["rows"])))
                note = (f"The 2022 census's final results print no row for {shape['name']}; "
                        f"this is {where}'s count less the {printed} districts they print for "
                        f"it: {short[0]:,} people, {short[1]:,} men and {short[2]:,} women.")
                fields = district_fields(shape["name"], short, where, None, note=note,
                                         then=then)
            elif len(found) == 1 and found[0][0] not in used.setdefault(c, set()):
                used[c].add(found[0][0])
                fields = district_fields(found[0][0], found[0][1], where, None, then=then)
            else:
                raise SystemExit(f"liberia_census: {shape['name']!r} ({c}, {k}) matches "
                                 f"{found}")
        else:
            why, beside = not_the_drawn(c)
            fields = district_fields(shape["name"], None, where, why, beside=beside)
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
    page = http_get(STATOIDS, binary=True, timeout=120)
    assert isinstance(page, bytes)
    tables["districts_2008"] = read_2008(page.decode("utf-8", "replace"))
    check_not_the_drawn(districts, tables["districts_2008"])
    return tables


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    ap.parse_args()
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
    for r in records:
        if r["level"] == "admin2" and "2008 census's" in str(r.get("population_note")):
            log(f"  further than a population moves: {r['population_note']}")
    log(f"  {len(records)} records: {bound} districts with a 2022 count")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
