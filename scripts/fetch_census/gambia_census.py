#!/usr/bin/env python3
"""The Gambia -- the 2024 census by local government area, the 2013 census by district.

The Gambia Bureau of Statistics (GBoS) has published one product of its 2024
Population and Housing Census so far, the Preliminary Report (August 2024),
and it counts the eight local government areas (LGAs) and nothing below them.
The 2013 census's reports, on GBoS's download site, go further:

* **2024, Preliminary Report**: Table 12, the de facto population by sex and
  LGA; Table 8, the ethnic groups of each LGA's Gambian nationals (the table's
  population is the 2,306,066 Gambians of Table 1).
* **2013, Volume 5, Spatial Distribution**: Annex F, the population of each
  LGA by five-year age group and sex; Annex H, by religion.
* **2013, Volume 10, Directory of Settlements**: every LGA, district and
  settlement, with the population of both sexes and of women.

Written for the eight LGAs: population and sex ratio from 2024, ethnicity
from 2024, median age and religion from 2013 (the 2024 report publishes ages
by LGA only in three broad groups, and no religion). For the districts:
population and sex ratio from 2013, the newest count below the LGA, and for
their median age, religion and ethnicity the reason there is none.

**The districts.** The census counts 44 districts and the boundary file draws
48: it divides Kanifing municipality, which the census counts as one
district, into five (Bakau, Jeshwang and three of Serrekunda), and the census
places Kanifing's nineteen settlements in no part of it, so those five carry
no figure and say why. Each other polygon is one census district, matched by
name within its LGA.

**Reading the directory.** Its text is read by the words' positions (pdfplumber),
which puts each row's figures on one line; a settlement name broken over two
lines is joined. The directory prints no marker for a district: a district's
row is the next one naming a district of the LGA, and an LGA's the next one
naming the following LGA once its predecessor's districts are all read. The
LGAs' districts must make them exactly and the LGAs The Gambia, 1,857,181;
a district's settlements must come near it, and thirteen districts'
settlements make a little more than the district (logged, see close_enough).

**Reading the 2013 annexes.** Annex F's tables print each LGA's men, women
and both for every five-year group, then the urban and rural figures; each
row must add up, the rows the total, and the total the directory's count.
Annex H's table of Kerewan's people of both sexes is a copy of its urban
table (50,188 people of 220,080), so Kerewan's religions are its tables of men
and of women added together; the eight LGAs then make the table of The
Gambia exactly.

**The 2024 tables.** Read by position too. Table 12's rows print three counts
and three percentages in an order the text layer does not always keep; the
total is the count the other two make, and the men the count whose share
is the first percentage. Table 8's two halves are read under their headings,
each LGA's ten shares must make 100 within their rounding, and the LGAs'
Gambians the country's 2,306,066.

Usage:
    python -m scripts.fetch_census.gambia_census
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from probe_pdf import PAGE_BREAK, laid_out  # noqa: E402

DIRECTORY = "https://www.gbosdata.org/downloads-file/7-census-2013-directory-of-settlement"
SPATIAL = "https://www.gbosdata.org/downloads-file/213-census-2013-spatial-distribution-report"
PRELIMINARY = "https://www.gbosdata.org/downloads-file/544-2024-gphc-preliminary-report"
PUBLISHER = "Gambia Bureau of Statistics"
SRC_DIR = (f"{PUBLISHER}, 2013 Population and Housing Census, Volume 10: Directory of "
           "Settlements")
SRC_AGE = (f"{PUBLISHER}, 2013 Population and Housing Census, Volume 5: Spatial Distribution, "
           "Annex F")
SRC_REL = (f"{PUBLISHER}, 2013 Population and Housing Census, Volume 5: Spatial Distribution, "
           "Annex H")
SRC_POP24 = f"{PUBLISHER}, 2024 Population and Housing Census, Preliminary Report, Table 12"
SRC_ETH24 = f"{PUBLISHER}, 2024 Population and Housing Census, Preliminary Report, Table 8"
SRC_SPATIAL = f"{PUBLISHER}, 2013 Population and Housing Census, Volume 5: Spatial Distribution"
SRC_PRELIM = f"{PUBLISHER}, 2024 Population and Housing Census, Preliminary Report"
LICENCE = "Gambia Bureau of Statistics publication (reuse with attribution)"
NATIONAL_2013 = 1_857_181
NATIONAL_2024 = (2_422_712, 1_186_293, 1_236_419)
OUT = "gambia_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
UNIT = "males_per_100_females"

LGAS = ("Banjul", "Kanifing", "Brikama", "Mansakonko", "Kerewan", "Kuntaur", "Janjanbureh",
        "Basse")
# The census's districts, by LGA, as the boundary file names them; Kanifing
# is one district, its LGA.
DISTRICTS = {
    "Banjul": ("Banjul Central", "Banjul North", "Banjul South"),
    "Kanifing": ("Kanifing",),
    "Brikama": ("Kombo North", "Kombo South", "Kombo Central", "Kombo East", "Foni Brefet",
                "Foni Bintang Karanai", "Foni Kansala", "Foni Bondali", "Foni Jarrol"),
    "Mansakonko": ("Kiang West", "Kiang Central", "Kiang East", "Jarra West", "Jarra Central",
                   "Jarra East"),
    "Kerewan": ("Lower Niumi", "Upper Niumi", "Jokadu", "Lower Badibu", "Central Badibu",
                "Illiasa", "Sabach Sanjar"),
    "Kuntaur": ("Lower Saloum", "Upper Saloum", "Nianija", "Niani", "Sami"),
    "Janjanbureh": ("Niamina Dankunku", "Niamina West", "Niamina East", "Lower Fuladu West",
                    "Upper Fuladu West", "Janjanbureh"),
    "Basse": ("Jimara", "Basse", "Tumana", "Kantora", "Wuli West", "Wuli East", "Sandu"),
}
# The directory's spelling -> the boundary file's, reduced (see key()).
SPELLINGS = {"sabachsanjal": "sabachsanjar", "illiassa": "illiasa", "upperbadibu": "illiasa",
             "janjangbureh": "janjanbureh", "fonikansalla": "fonikansala",
             "fonibundali": "fonibondali", "fulladueast": "fuladueast"}
# The polygons Kanifing's one census district is drawn as.
KANIFING_PARTS = ("Bakau", "Jeshwang", "Serrekunda Central", "Serrekunda East",
                  "Serrekunda West")
KANIFING_WHY = ("The 2013 census counts Kanifing municipality as one district, of {n:,} people, "
                "and its directory of settlements places the municipality's nineteen "
                "settlements in none of the five parts it is drawn as here, so no census figure "
                "is shown for this part.")

VAL = r"(?:\d[\d,]*|-)"
DIR_ROW = re.compile(rf"^(?P<name>.*?)\s*(?P<vals>(?:{VAL}\s+){{19}}{VAL})$")
# Table 8's ten columns, as it heads them; its population is Gambian nationals.
ETHNIC_24 = ("Mandinka", "Fula", "Wollof", "Jola", "Sarahule", "Serere", "Krio/Aku Marabou",
             "Manjago", "Bambara", "Other ethnic groups")
GAMBIANS_2024 = 2_306_066
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d[\d,]*")
# Annex F's age groups; the last is open.
AGE_GROUPS = [(low, low + 4) for low in range(0, 85, 5)] + [(85, None)]
AGE_LABELS = [f"{lo}-{hi}" for lo, hi in AGE_GROUPS[:-1]] + ["85+"]
F_TITLE = re.compile(r"Table F\.\d+:[^(\n]*\((?P<lga>[A-Za-z ]+)\)")
F_ROW = re.compile(r"^(?P<label>\d+-\d+|85\+|Not stated|Total)\s+(?P<m>\d[\d,]*)\s+"
                   r"(?P<f>\d[\d,]*)\s+(?P<b>\d[\d,]*)")
# Annex H's columns, and its table of The Gambia's both sexes (H.1).
RELIGIONS_13 = ("Islam", "Christianity", "Traditional", "Other", "Not stated")
NATIONAL_RELIGION_13 = (1_782_859, 69_638, 1_028, 2_686, 970)
H_TITLE = re.compile(r"Table H\.\d+:[^(\n]*\((?P<what>[^)\n]*)\)")
H_TOTAL = re.compile(r"^Total((?:[ \t]+\d[\d,]*)+)[ \t]*$", re.M)
# An Annex H heading runs from "Age group" to the first row, over as many lines
# as it takes (Basse's sets "Not" and "stated Total" on lines of their own).
H_HEADING = re.compile(r"^\s*Age group\s+(.+?)\s*^\s*0-4\s", re.M | re.S)
# Its words for the columns, longest first: some tables print "Tradition".
H_COLUMNS = (("Christianity", "Christianity"), ("Traditional", "Traditional"),
             ("Tradition", "Traditional"), ("Not stated", "Not stated"), ("Islam", "Islam"),
             ("Other", "Other"), ("Total", "Total"))


def columns(heading: str) -> list[str] | None:
    """An Annex H heading's columns, in order, or None for one it cannot name."""
    names, rest = [], " ".join(heading.split())
    while rest:
        found = next(((word, name) for word, name in H_COLUMNS if rest.startswith(word)), None)
        if found is None:
            return None
        names.append(found[1])
        rest = rest[len(found[0]):].strip()
    return names


def key(name: str) -> str:
    s = "".join(c for c in str(name or "").lower() if "a" <= c <= "z")
    return SPELLINGS.get(s, s)


def value(text: str) -> int:
    return 0 if text == "-" else int(text.replace(",", ""))


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def directory_rows(pages: list[str]) -> list[tuple[str, int, int]]:
    """Every row of the directory in order: (name, both sexes, women).

    A line of a name and no figures is the first part of the next row's name
    ("Brikama Bojang" / "Kunda 1,882 ..."); a line of figures and no name
    takes the name above it ("Banjul" / "31,054 ..."). A line of figures that
    is not a row (The Gambia's, two of whose figures run together) is skipped
    and stops a name from carrying past it.
    """
    out: list[tuple[str, int, int]] = []
    for page in pages:
        pending: list[str] = []
        for line in (ln.strip() for ln in page.splitlines()):
            if not line or line.startswith(("Name BOTH", "LGA/District", "Settlement Total",
                                             "[")) or re.fullmatch(r"\d{1,2}", line):
                continue
            m = DIR_ROW.match(line)
            if m:
                name = " ".join([*pending, m.group("name")]).strip()
                vals = [value(v) for v in m.group("vals").split()]
                out.append((name, vals[0], vals[10]))
                pending = []
            elif re.search(r"[A-Za-z]", line) and not re.search(r"\d{3}", line):
                pending.append(line)
            else:
                pending = []
    return out


def close_enough(made: int, printed: int) -> bool:
    """Whether a district's settlements make its printed count, within what
    the directory's own rows differ by. Most districts' settlements make
    their count exactly; thirteen make a little more (Kombo North 339,434
    against 339,377, Kiang Central 8,829 against 8,661, Jarra East 17,810
    against 16,034). The districts' counts are the ones that make their LGA
    and The Gambia, so they are the figures used, and the differences are
    logged; a district row the reader missed would leave a whole district's
    settlements under the one above, which this margin does not cover."""
    return abs(made - printed) <= max(10, 0.15 * printed)


def districts_2013(rows: list[tuple[str, int, int]]) -> dict[str, dict[str, Any]]:
    """{LGA: {"total": (both, women), "districts": {district: (both, women)},
    "settled": {district: the settlements' sum}}}, walking the rows.

    The directory marks no row as a district's. A row is a district's when it
    names a district of the current LGA not yet read (Banjul's three list no
    settlements under them); an LGA's when it names the next LGA in the
    directory's order once every district of the current one is read and the
    last one's settlements come near it (Kanifing has a settlement named
    Kanifing); every other row is a settlement of the district above it. Each
    district's settlements must come near its count, and the LGA's districts
    must make its count exactly. Districts are kept under the boundary file's
    spelling (the text layer splits some names: "Il liasa", "Sa ndu").
    """
    lgas = {key(n): n for n in LGAS}
    out: dict[str, dict[str, Any]] = {}
    current, district, settled = None, None, 0

    def complete() -> bool:
        if current is None:
            return True
        d = out[current]
        done = {key(n) for n in d["districts"]} >= {key(n) for n in DISTRICTS[current]}
        return done and (settled == 0 or close_enough(settled, d["districts"][district][0]))

    def follows(lga: str) -> bool:
        return LGAS.index(lga) == (0 if current is None else LGAS.index(current) + 1)

    def close() -> None:
        if current is not None and district is not None:
            out[current]["settled"][district] = settled

    for name, both, women in rows:
        k = key(name)
        if current is None and name.lower().startswith("the gambia"):
            continue
        if k in lgas and follows(lgas[k]) and complete():
            close()
            current = lgas[k]
            out[current] = {"total": (both, women), "districts": {}, "settled": {}}
            district, settled = None, 0
            if current == "Kanifing":
                # One district, the LGA itself: its settlements follow.
                out[current]["districts"]["Kanifing"] = (both, women)
                district = "Kanifing"
            continue
        if current is None:
            raise SystemExit(f"gambia_census: {name!r} ({both:,}) before any LGA")
        expected = {key(n) for n in DISTRICTS[current]}
        seen = {key(n) for n in out[current]["districts"]}
        if k in expected - seen:
            close()
            district = next(n for n in DISTRICTS[current] if key(n) == k)
            settled = 0
            out[current]["districts"][district] = (both, women)
            continue
        if district is None:
            raise SystemExit(f"gambia_census: {current}: {name!r} before any district")
        settled += both
    close()
    for lga, d in out.items():
        for name, made in d["settled"].items():
            printed = d["districts"][name][0]
            if made and not close_enough(made, printed):
                raise SystemExit(f"gambia_census: {lga}/{name}: settlements make {made:,}, "
                                 f"the district {printed:,}")
            if made and made != printed:
                log(f"  {lga}/{name}: settlements make {made:,}, the district {printed:,}")
        made = tuple(sum(v[j] for v in d["districts"].values()) for j in (0, 1))
        if made != d["total"]:
            raise SystemExit(f"gambia_census: {lga}'s districts make {made}, not {d['total']}")
    if sorted(out) != sorted(LGAS):
        raise SystemExit(f"gambia_census: LGAs read {sorted(out)}")
    if sum(d["total"][0] for d in out.values()) != NATIONAL_2013:
        raise SystemExit("gambia_census: the LGAs do not make The Gambia's 1,857,181")
    for lga in LGAS:
        got = sorted(key(n) for n in out[lga]["districts"])
        if got != sorted(key(n) for n in DISTRICTS[lga]):
            raise SystemExit(f"gambia_census: {lga}'s districts read "
                             f"{sorted(out[lga]['districts'])}")
    return out


def table_lines(pages: list[str], title: str) -> list[str]:
    """The lines under a table's title, to the page's footer or the next
    table's title."""
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines()]
        for i, line in enumerate(lines):
            if title in line:
                out = []
                for ln in lines[i + 1:]:
                    if ln.startswith(("PAGE ", "Table ", "[")):
                        break
                    out.append(ln)
                return out
    raise SystemExit(f"gambia_census: no page carries {title!r}")


def blocks(lines: list[str], heads: tuple[str, ...]) -> list[tuple[str, list[str]]]:
    """A table's rows as (label, figures). The text layer sets some of a row's
    figures a line below its label ("Banjul 14,192 53.6 12,269 46.4" /
    "26,461 100.0"), and Basse's male count below the rest, so a row runs
    until the next line that starts with a label."""
    out: list[tuple[str, list[str]]] = []
    for line in lines:
        head = next((h for h in heads if line == h or line.startswith(h + " ")), None)
        if head:
            out.append((head, NUMBER.findall(line[len(head):])))
        elif out:
            out[-1][1].extend(NUMBER.findall(line))
    return out


def table12(pages: list[str]) -> dict[str, tuple[int, int, int]]:
    """Table 12, the 2024 population by sex and LGA: {LGA: (total, men,
    women)}. Each row prints three counts and three percentages, in an order
    the text layer does not keep; the total is the count the other two make,
    and the men are the count whose share is the row's first percentage."""
    rows = blocks(table_lines(pages, "Table 12: Population Distribution by Sex and LGA"),
                  ("Total",) + LGAS)
    out = {}
    for head, figures in rows:
        counts = [int(f.replace(",", "")) for f in figures if "." not in f]
        pcts = [float(f) for f in figures if "." in f]
        if len(counts) != 3 or len(pcts) != 3:
            raise SystemExit(f"gambia_census: Table 12's {head} row reads {figures}")
        total = max(counts)
        rest = sorted(counts)[:2]
        if sum(rest) != total:
            raise SystemExit(f"gambia_census: Table 12's {head} row: {rest} do not make {total}")
        men = min(rest, key=lambda n: abs(100 * n / total - pcts[0]))
        women = total - men
        if abs(100 * men / total - pcts[0]) > 0.11 or abs(100 * women / total - pcts[1]) > 0.11:
            raise SystemExit(f"gambia_census: Table 12's {head} row: {men:,} and {women:,} are "
                             f"not {pcts[0]}% and {pcts[1]}% of {total:,}")
        out[head] = (total, men, women)
    if sorted(out) != sorted(("Total",) + LGAS) or out["Total"] != NATIONAL_2024:
        raise SystemExit(f"gambia_census: Table 12 reads {out}")
    made = tuple(sum(out[lga][j] for lga in LGAS) for j in range(3))
    if made != NATIONAL_2024:
        raise SystemExit(f"gambia_census: Table 12's LGAs make {made}, not {NATIONAL_2024}")
    del out["Total"]
    return out


def table8(pages: list[str]) -> dict[str, tuple[int, dict[str, float]]]:
    """Table 8, the ethnic groups of each LGA's Gambian nationals in 2024:
    {LGA: (Gambians, {group: per cent})}. The table prints its ten columns in
    two halves of five shares and then each LGA's Gambians; every half is
    read under its own heading, whose columns are checked, and each LGA's ten
    shares must make 100 to within their rounding."""
    lines = table_lines(pages, "Table 8: Distribution of Ethnic Groups by LGA")
    halves: list[list[str]] = []
    for line in lines:
        if line == "LGA" or line.startswith("LGA "):
            halves.append([line])
        elif halves:
            halves[-1].append(line)
    if len(halves) != 3 or not halves[0][0].startswith("LGA Mandinka Fula Wollof Jola Sarahule") \
            or not halves[1][0].startswith("LGA Serere Krio/Aku Marabou Manjago") \
            or halves[2][0] != "LGA Total":
        raise SystemExit(f"gambia_census: Table 8's headings read {[h[0] for h in halves]}")
    heads = ("The Gambia",) + LGAS
    first, second = ({h: [float(f) for f in figs] for h, figs in blocks(half, heads)}
                     for half in halves[:2])
    totals = {h: [int(f.replace(",", "")) for f in figs] for h, figs in blocks(halves[2], heads)}
    out = {}
    for head in heads:
        a, b, n = first.get(head, []), second.get(head, []), totals.get(head, [])
        if len(a) != 5 or len(b) != 5 or len(n) != 1:
            raise SystemExit(f"gambia_census: Table 8's {head} reads {a} / {b} / {n}")
        shares = dict(zip(ETHNIC_24, a + b))
        if abs(sum(shares.values()) - 100) > 0.4:
            raise SystemExit(f"gambia_census: Table 8's {head} shares make {sum(shares.values())}")
        out[head] = (n[0], shares)
    if out["The Gambia"][0] != GAMBIANS_2024 or \
            sum(out[lga][0] for lga in LGAS) != GAMBIANS_2024:
        raise SystemExit("gambia_census: Table 8's LGAs do not make the 2,306,066 Gambians")
    del out["The Gambia"]
    return out


def annex_f(pages: list[str], d2013: dict[str, dict[str, Any]]) -> dict[str, list[int]]:
    """Annex F, each LGA's people of both sexes by five-year age group in
    2013: {LGA: [0-4, ..., 85+]}. A row prints men, women and both, for the
    LGA and then (outside Banjul and Kanifing) for its urban and rural parts;
    the first three figures are the LGA's. Every row's men and women must
    make it, the groups and those whose age is not stated the total, and the
    total the LGA's count in the directory of settlements."""
    out: dict[str, list[int]] = {}
    for page in pages:
        title = F_TITLE.search(page)
        if not title or title.group("lga") not in LGAS:
            continue
        lga = title.group("lga")
        rows: dict[str, tuple[int, ...]] = {}
        for line in page[title.end():].splitlines():
            m = F_ROW.match(line.strip())
            if m and m.group("label") not in rows:
                rows[m.group("label")] = tuple(int(m.group(k).replace(",", "")) for k in "mfb")
        if not set(AGE_LABELS) | {"Not stated", "Total"} <= set(rows):
            continue          # a list of tables, not the table
        if lga in out:
            raise SystemExit(f"gambia_census: Annex F prints {lga} twice")
        for label, (men, women, both) in rows.items():
            if men + women != both:
                raise SystemExit(f"gambia_census: Annex F, {lga} {label}: {men:,} + {women:,} "
                                 f"is not {both:,}")
        made = [sum(rows[label][j] for label in [*AGE_LABELS, "Not stated"]) for j in range(3)]
        if made != list(rows["Total"]) or (rows["Total"][2], rows["Total"][1]) \
                != d2013[lga]["total"]:
            raise SystemExit(f"gambia_census: Annex F, {lga}: the rows make {made}, the total "
                             f"is {rows['Total']}, the directory {d2013[lga]['total']}")
        out[lga] = [rows[label][2] for label in AGE_LABELS]
    if sorted(out) != sorted(LGAS):
        raise SystemExit(f"gambia_census: Annex F reads {sorted(out)}")
    return out


def median(counts: list[int]) -> float | None:
    """The age half the people are younger than, within its five-year group."""
    half, before = sum(counts) / 2, 0
    for (low, high), n in zip(AGE_GROUPS, counts):
        if before + n >= half:
            if high is None or n <= 0:
                return None
            return round(low + (half - before) / n * (high - low + 1), 1)
        before += n
    return None


def annex_h(pages: list[str], d2013: dict[str, dict[str, Any]]
            ) -> tuple[dict[str, list[int]], dict[str, int]]:
    """Annex H, each LGA's people by religion in 2013: ({LGA: [Islam,
    Christianity, Traditional, Other, Not stated]}, {LGA: the total of a
    both-sexes table not used}).

    Each table's Total row is read under the columns its heading names: a
    table leaves out a religion nobody in it follows (Kuntaur's men's has no
    Traditional column), which is then none. An LGA's table of both sexes is
    used where its columns make its total and that total is the LGA's;
    Kerewan's is not -- it repeats Kerewan's urban table, 50,188 people of
    220,080 -- and for it the tables of men and of women are added instead,
    which make the 220,080. The LGAs must make the report's table of The
    Gambia, H.1."""
    text = "\n".join(pages)
    titles = list(H_TITLE.finditer(text))
    tables: dict[str, list[int] | None] = {}
    for i, title in enumerate(titles):
        end = titles[i + 1].start() if i + 1 < len(titles) else len(text)
        heading = H_HEADING.search(text, title.end(), end)
        total = H_TOTAL.search(text, title.end(), end)
        if heading and total:
            names = columns(heading.group(1))
            nums = [int(n.replace(",", "")) for n in total.group(1).split()]
            if names is None or len(names) != len(nums) or names[-1] != "Total":
                tables.setdefault(title.group("what").strip(), None)
                continue
            got = dict(zip(names, nums))
            tables.setdefault(title.group("what").strip(),
                              [got.get(name, 0) for name in RELIGIONS_13] + [got["Total"]])

    def row(what: str) -> list[int] | None:
        nums = tables.get(what)
        if nums is None or sum(nums[:5]) != nums[5]:
            return None
        return nums

    national = row("The Gambia-Both sexes")
    if national is None or tuple(national[:5]) != NATIONAL_RELIGION_13:
        raise SystemExit(f"gambia_census: Annex H's table of The Gambia reads {national}")
    out: dict[str, list[int]] = {}
    unused: dict[str, int] = {}
    for lga in LGAS:
        people = d2013[lga]["total"][0]
        both = row(f"{lga}-Both sexes")
        if both and both[5] == people:
            out[lga] = both[:5]
            continue
        men, women = row(f"{lga}-Male"), row(f"{lga}-Female")
        if not (men and women and men[5] + women[5] == people):
            raise SystemExit(f"gambia_census: Annex H, {lga}: both sexes {both}, men {men}, "
                             f"women {women}, against {people:,} people")
        out[lga] = [a + b for a, b in zip(men[:5], women[:5])]
        unused[lga] = (tables.get(f"{lga}-Both sexes") or [0])[-1]
        log(f"  Annex H: {lga}'s table of both sexes totals {unused[lga]:,}; its tables of "
            f"men and of women, which make {people:,}, are added instead")
    made = tuple(sum(out[lga][j] for lga in LGAS) for j in range(5))
    if made != NATIONAL_RELIGION_13:
        raise SystemExit(f"gambia_census: Annex H's LGAs make {made}, not The Gambia's "
                         f"{NATIONAL_RELIGION_13}")
    return out, unused


def percentages(shares: dict[str, float]) -> list[dict[str, Any]]:
    out = [{"group": g, "pct": round(p, 1)} for g, p in shares.items() if p > 0]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def lga_shapes(admin1: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    drawn = {shape["name"]: shape for shape in admin1}
    if sorted(drawn) != sorted(LGAS):
        raise SystemExit(f"gambia_census: LGA polygons {sorted(drawn)}")
    return drawn


def bind_lgas(admin1: list[dict[str, Any]], tables: dict[str, Any]) -> list[dict[str, Any]]:
    """One record per LGA polygon: population, sex ratio and ethnic groups from
    the 2024 census, median age and religion from the 2013 census."""
    records = []
    for lga, shape in lga_shapes(admin1).items():
        total, men, women = tables["population"][lga]
        gambians, groups = tables["ethnicity"][lga]
        faiths = dict(zip(RELIGIONS_13, tables["religion"][lga]))
        people13 = sum(faiths.values())
        religion_note = (f"Religion of the {people13:,} people the 2013 census counted in {lga}; "
                         "the 2024 census's preliminary results give no religion.")
        if lga in tables["religion_unused"]:
            religion_note += (f" The 2013 report's table of {lga}'s people of both sexes "
                              "repeats its table of the area's urban people "
                              f"({tables['religion_unused'][lga]:,}); these shares are from its "
                              f"tables of men and of women added together, which make the "
                              f"{people13:,}.")
        age = median(tables["ages"][lga])
        records.append(record(
            f"GMB-2024-{key(lga)}", lga, level="admin1", parent="GMB", country="GMB",
            match_by="shape_id", shape_id=shape["id"],
            population=measure(total, year=2024, source=SRC_POP24),
            population_note=(f"The 2024 census's count of the people present in {lga} on "
                             "census night, from its preliminary results."),
            sex_ratio=measure(round(100 * men / women, 1), unit=UNIT, year=2024,
                              source=SRC_POP24),
            sex_ratio_note=(f"From the 2024 census's preliminary count of {men:,} men and "
                            f"{women:,} women."),
            median_age=(measure(age, unit="years", year=2013, source=SRC_AGE) if age is not None
                        else gap(NOT_AVAILABLE)),
            median_age_note=("Interpolated within the five-year age group that holds the middle "
                             "person, from the 2013 census's count by age; the 2024 census's "
                             "preliminary results give each local government area's ages only "
                             "in three broad groups."),
            religion=shares(faiths, total=people13),
            religion_year=2013,
            religion_note=religion_note,
            ethnicity=percentages(groups),
            ethnicity_year=2024,
            ethnicity_note=(f"Ethnic group of the {gambians:,} Gambian nationals the 2024 census "
                            f"counted in {lga}, of its {total:,} people; the table counts no one "
                            "of another nationality. From the census's preliminary results."),
            sources=[
                {"field": "population/sex_ratio", "name": SRC_POP24, "url": PRELIMINARY,
                 "license": LICENCE, "year": 2024},
                {"field": "ethnicity", "name": SRC_ETH24, "url": PRELIMINARY,
                 "license": LICENCE, "year": 2024},
                {"field": "median_age", "name": SRC_AGE, "url": SPATIAL, "license": LICENCE,
                 "year": 2013},
                {"field": "religion", "name": SRC_REL, "url": SPATIAL, "license": LICENCE,
                 "year": 2013},
            ]))
    return records


DISTRICT_MEDIAN = ("The 2013 census's directory gives each district's people in age bands too "
                   "wide for a median (7-14, 15-49), and its tables by five-year age group stop "
                   "at the local government area.")
DISTRICT_RELIGION = ("The 2013 census publishes religion by local government area, not by "
                     "district, and the 2024 census's preliminary results give none.")
DISTRICT_ETHNICITY = ("The 2013 census publishes ethnic group by local government area, not by "
                      "district, and so do the 2024 census's preliminary results.")


def bind_districts(d2013: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
                   admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lga_of = {shape["id"]: name for name, shape in lga_shapes(admin1).items()}
    unanswered = {"median_age": gap(NOT_AVAILABLE, DISTRICT_MEDIAN),
                  "religion": gap(NOT_AVAILABLE, DISTRICT_RELIGION),
                  "ethnicity": gap(NOT_AVAILABLE, DISTRICT_ETHNICITY)}
    # The publications those reasons rest on: the directory's age bands, the
    # spatial report's tables by LGA, the 2024 preliminary report's.
    reasons_cited = [
        {"field": "median_age", "name": SRC_DIR, "url": DIRECTORY, "license": LICENCE,
         "year": 2013},
        {"field": "median_age/religion/ethnicity", "name": SRC_SPATIAL, "url": SPATIAL,
         "license": LICENCE, "year": 2013},
        {"field": "religion/ethnicity", "name": SRC_PRELIM, "url": PRELIMINARY,
         "license": LICENCE, "year": 2024},
    ]
    records = []
    for shape in admin2:
        lga = lga_of.get(shape["parent"])
        if lga is None:
            raise SystemExit(f"gambia_census: {shape['name']!r} is drawn in no LGA")
        if lga == "Kanifing" and shape["name"] in KANIFING_PARTS:
            why = KANIFING_WHY.format(n=d2013["Kanifing"]["total"][0])
            records.append(record(
                f"GMB-2013-{key(shape['name'])}", shape["name"], level="admin2", parent="GMB",
                country="GMB", match_by="shape_id", shape_id=shape["id"],
                population=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
                **unanswered,
                sources=[{"field": "population/sex_ratio", "name": SRC_DIR, "url": DIRECTORY,
                          "license": LICENCE, "year": 2013}, *reasons_cited]))
            continue
        found = [(n, v) for n, v in d2013[lga]["districts"].items()
                 if key(n) == key(shape["name"])]
        if len(found) != 1:
            raise SystemExit(f"gambia_census: {shape['name']!r} ({lga}) matches {found}")
        name, (both, women) = found[0]
        men = both - women
        records.append(record(
            f"GMB-2013-{key(shape['name'])}", shape["name"], level="admin2", parent="GMB",
            country="GMB", match_by="shape_id", shape_id=shape["id"],
            population=measure(both, year=2013, source=SRC_DIR),
            population_note=(f"The 2013 census's count for {name} district, in {lga}: the "
                             "newest count of the district, since the 2024 census has so far "
                             "published its local government areas only."),
            sex_ratio=measure(round(100 * men / women, 1), unit=UNIT, year=2013,
                              source=SRC_DIR),
            sex_ratio_note=("From the 2013 census's count of both sexes and of women; the "
                            "directory prints no count of men, which is the difference."),
            **unanswered,
            sources=[{"field": "population/sex_ratio", "name": SRC_DIR, "url": DIRECTORY,
                      "license": LICENCE, "year": 2013}, *reasons_cited]))
    return records


def fetch(url: str) -> bytes:
    blob = http_get(url, binary=True, timeout=300)
    assert isinstance(blob, bytes)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"gambia_census: {url} is not a PDF")
    log(f"  {url}: {len(blob):,} bytes, sha256 {digest(blob)}")
    return blob


def read_pages(url: str) -> list[str]:
    """A PDF's pages with each row's words put back on one line by position."""
    return laid_out(fetch(url)).split(PAGE_BREAK)


def read_text(url: str) -> list[str]:
    """A PDF's pages as its text layer gives them: the spatial report's 373
    pages, whose annex tables read cleanly so and slowly by position."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(fetch(url)))
    return [page.extract_text() or "" for page in reader.pages]


def read() -> dict[str, Any]:
    d2013 = districts_2013(directory_rows(read_pages(DIRECTORY)))
    for lga, d in d2013.items():
        log(f"  {lga}: {d['total']}: " + ", ".join(f"{n} {v[0]:,}" for n, v in
                                                   d["districts"].items()))
    prelim = read_pages(PRELIMINARY)
    spatial = read_text(SPATIAL)
    religion, unused = annex_h(spatial, d2013)
    return {"districts": d2013, "population": table12(prelim), "ethnicity": table8(prelim),
            "ages": annex_f(spatial, d2013), "religion": religion, "religion_unused": unused}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    ap.parse_args()
    tables = read()
    for lga in LGAS:
        log(f"  {lga}: 2024 {tables['population'][lga]}, median 2013 "
            f"{median(tables['ages'][lga])}, religion 2013 {tables['religion'][lga]}")
    admin1 = json.loads((SITE / "admin1" / "GMB.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GMB.units.json").read_text())
    records = bind_lgas(admin1, tables) + bind_districts(tables["districts"], admin1, admin2)
    log(f"  {len(records)} records")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
