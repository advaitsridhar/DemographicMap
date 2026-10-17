#!/usr/bin/env python3
"""Nigeria -- the 2006 Population and Housing Census, by state and local government area.

The National Population Commission published the 2006 census's final results
in its Priority Table series (April 2010). Volume IV, "Population Distribution
by Age & Sex (State & Local Government Area)", prints Table DS5 for Nigeria,
for every state and the Federal Capital Territory, and for each of the 774
local government areas under its state: the population by five-year age group
(0-4 to 80-84, then 85+) and sex, with the total on top. Volume III prints the
same areas' men, women and persons beside their senatorial district and land
area. The IHSN survey catalogue keeps both volumes (catalogue entry 3340, the
census's NGA_2006_PHC_v01_M); the Commission's own site no longer serves them.

Written for each local government area the map draws and for each state:
population, sex ratio (males per 100 females) and the median age,
interpolated within the five-year group that holds the middle person.

**What the figures are worth here.** The count is twenty years old. OCHA's
COD-PS table carries the Commission's own projection of every area to 2020,
from this census, and a population figure from here only fills where nothing
newer is shown. The sex ratio and the median age are the census's own
measurement and stand in front of the projection's: a projection carries the
census's structure forward, it does not measure it again.

**Bakassi.** The 2006 census counted Bakassi local government area while it
still held the Bakassi peninsula, which passed to Cameroon in 2008. The
polygon drawn under that name is the 256 km2 left on the Nigerian side, so the
area's figures are not written on it, and Cross River's note says that its
2006 count includes the peninsula's people.

**Checks before anything is written.** Every table: men and women make the
total, in the total and in every age group, and the age groups make the
total; a table that fails is written without the figure it cannot give, and
says why. Every state's areas make the state, the states make Nigeria, and
Nigeria is 140,431,790 (71,345,488 men, 69,086,302 women). Volume III's men
and women for each state's areas are compared with Volume IV's, area for area
(matched by their counts, so a spelling that differs between the two volumes
cannot hide a difference), and every difference is logged. Every polygon is
bound to one census area and every census area but Bakassi to one polygon,
within its state.

Usage:
    python -m scripts.fetch_census.nigeria_census
    python -m scripts.fetch_census.nigeria_census --dump    # print the tables read
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json

VOL4 = "https://datacatalog.ihsn.org/catalog/3340/download/48522"
VOL3 = "https://datacatalog.ihsn.org/catalog/3340/download/48521"
SOURCE = ("National Population Commission, 2006 Population and Housing Census, Priority "
          "Table Volume IV, Population Distribution by Age and Sex (State and Local "
          "Government Area), Table DS5")
LICENCE = "National Population Commission publication (reuse with attribution)"
YEAR = 2006
NATIONAL = (140_431_790, 71_345_488, 69_086_302)
OUT = "nigeria_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
UNIT = "males_per_100_females"

# Table DS5's age groups, in order: (low, high); the open top group has no high.
GROUPS = [(a, a + 4) for a in range(0, 85, 5)] + [(85, None)]

NUM = r"\d[\d,]*"
TOTAL = re.compile(rf"^TOTAL\s+({NUM})\s+({NUM})\s+({NUM})\s*$")
GROUP = re.compile(rf"^(\d+)\s*(?:[-–—]\s*(\d+)|\+)\s+({NUM})\s+({NUM})\s+({NUM})\s*$")
# Words of the table's headings and the page's running head; a line of these
# alone is never an area's name.
HEADING = frozenset("""table ds5 distribution of population by five year age groups and sex
total males females - – single years both sexes male female""".split())

# The census's state names -> the boundary file's, reduced (see key()).
STATES = {"fctabuja": "abujafederalcapitalterritory", "fct": "abujafederalcapitalterritory",
          "federalcapitalterritory": "abujafederalcapitalterritory",
          "abuja": "abujafederalcapitalterritory", "nassarawa": "nasarawa"}
# (state, the boundary file's reduced name) -> the census's reduced name,
# within the same state; each checked against Volume IV's spelling.
ALIASES: dict[tuple[str, str], str] = {}
# The census area whose figures fit no polygon: Bakassi as it stood in 2006.
NOT_DRAWN = {("crossriver", "bakassi")}
BAKASSI = ("The 2006 census counted Bakassi local government area while it held the Bakassi "
           "peninsula, which passed to Cameroon in 2008; this polygon is the part left on the "
           "Nigerian side, around Ikang, and no figure is published for it alone.")
CROSS_RIVER = ("This count includes Bakassi local government area as it stood in 2006, with "
               "the Bakassi peninsula that passed to Cameroon in 2008 ({n:,} people in the "
               "whole area).")
MEDIAN_NOTE = ("Interpolated within the five-year age group that holds the middle person, "
               "from the 2006 census's count by age.")


def key(name: str) -> str:
    """A name reduced to its letters, without STATE."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\bstate\b", " ", s)
    return "".join(c for c in s if "a" <= c <= "z")


def keys(name: str) -> list[str]:
    """Every reduction a census name may be drawn under: whole, without what
    it puts in brackets, and the bracketed name itself ("IBADAN CENTRAL [IBADAN
    NORTH EAST]", "ABUJA MUNICIPAL (AMAC)", "NAFADA (BAJOGA)")."""
    out = [key(name)]
    inside = re.findall(r"[\[(]([^\])]*)[\])]", name)
    bare = re.sub(r"[\[(][^\])]*[\])]", " ", name)
    for k in [key(bare), *(key(x) for x in inside)]:
        if k and k not in out:
            out.append(k)
    return out


def state_key(name: str) -> str:
    k = key(name)
    return STATES.get(k, k)


def number(text: str) -> int:
    return int(text.replace(",", ""))


def is_heading(line: str) -> bool:
    words = line.lower().replace(":", " ").split()
    return all(w in HEADING or w.isdigit() for w in words)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def pages_of(blob: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


def parse_tables(pages: list[str]) -> list[dict[str, Any]]:
    """Every Table DS5 in the volume, in order: name, page, total and groups.

    A page of single years of age (each state has one, before its five-year
    table) is skipped: its rows are not five-year groups, and the same state
    is printed in five-year groups on the page after it. A table's name is the
    nearest line above its TOTAL row that is neither a heading nor a row of
    figures -- the headings sit above the name on some pages and between the
    name and the total on others -- and a name broken over two lines is joined.
    """
    lines: list[tuple[int, str]] = []
    for page_number, text in enumerate(pages, 1):
        if "single years" in text.lower():
            continue
        lines.extend((page_number, ln.strip()) for ln in text.splitlines() if ln.strip())
    tables: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        page, line = lines[i]
        m = TOTAL.match(line)
        if not m:
            i += 1
            continue
        j, name = i - 1, []
        while j >= 0 and is_heading(lines[j][1]):
            j -= 1
        while j >= 0 and not is_heading(lines[j][1]) and not TOTAL.match(lines[j][1]) \
                and not GROUP.match(lines[j][1]) and len(name) < 2:
            name.insert(0, lines[j][1])
            j -= 1
        rows, k = [], i + 1
        while k < len(lines) and len(rows) < len(GROUPS):
            g = GROUP.match(lines[k][1])
            if g:
                rows.append(g)
            elif not is_heading(lines[k][1]):
                break
            k += 1
        groups = []
        for (low, high), g in zip(GROUPS, rows):
            got_low, got_high = int(g.group(1)), g.group(2)
            if got_low != low or (high is None) != (got_high is None) \
                    or (high is not None and int(got_high) != high):
                raise SystemExit(f"nigeria_census: page {page}: {' '.join(name)!r}: group "
                                 f"{g.group(0)!r} where {low}-{high} was expected")
            groups.append((low, high, number(g.group(3)), number(g.group(4)),
                           number(g.group(5))))
        tables.append({"name": " ".join(name), "page": page,
                       "total": tuple(number(x) for x in m.groups()), "groups": groups})
        i = k
    return tables


def problems(table: dict[str, Any]) -> list[str]:
    """What does not add up in one table, in words; empty when it all does."""
    out = []
    t, m, f = table["total"]
    if m + f != t:
        out.append(f"men {m:,} and women {f:,} make {m + f:,}, not the total {t:,}")
    if len(table["groups"]) != len(GROUPS):
        out.append(f"{len(table['groups'])} age groups where {len(GROUPS)} were expected")
        return out
    for low, high, gt, gm, gf in table["groups"]:
        if gm + gf != gt:
            out.append(f"ages {low}-{high if high is not None else ''}: men and women make "
                       f"{gm + gf:,}, not {gt:,}")
    for col, label in ((2, "everyone"), (3, "men"), (4, "women")):
        made = sum(g[col] for g in table["groups"])
        if made != table["total"][col - 2]:
            out.append(f"the age groups of {label} make {made:,}, not "
                       f"{table['total'][col - 2]:,}")
    return out


def organise(tables: list[dict[str, Any]]) -> dict[str, Any]:
    """{"nation": table, "states": [{"table": ..., "areas": [table, ...]}, ...]}."""
    nation, states = None, []
    for t in tables:
        name = t["name"].upper()
        if name == "NIGERIA":
            nation = t
        elif re.search(r"\bSTATE$", name) or key(name) in STATES:
            states.append({"table": t, "areas": []})
        elif not states:
            raise SystemExit(f"nigeria_census: {t['name']!r} (page {t['page']}) comes "
                             "before any state")
        else:
            states[-1]["areas"].append(t)
    if nation is None:
        raise SystemExit("nigeria_census: no table for Nigeria")
    return {"nation": nation, "states": states}


def check(book: dict[str, Any]) -> dict[str, list[str]]:
    """The volume's sums, checked; {"STATE/AREA": its own problems} for the
    tables that do not add up, which are written without what they cannot give."""
    nation = book["nation"]
    if nation["total"] != NATIONAL:
        raise SystemExit(f"nigeria_census: Nigeria is {nation['total']}, not {NATIONAL}")
    if len(book["states"]) != 37:
        raise SystemExit(f"nigeria_census: {len(book['states'])} states, not 37: "
                         f"{[s['table']['name'] for s in book['states']]}")
    areas = sum(len(s["areas"]) for s in book["states"])
    if areas != 774:
        raise SystemExit(f"nigeria_census: {areas} local government areas, not 774")
    for col in range(3):
        made = sum(s["table"]["total"][col] for s in book["states"])
        if made != nation["total"][col]:
            raise SystemExit(f"nigeria_census: the states make {made:,} in column {col}, "
                             f"not Nigeria's {nation['total'][col]:,}")
    bad: dict[str, list[str]] = {}
    for s in book["states"]:
        for col in range(3):
            made = sum(a["total"][col] for a in s["areas"])
            if made != s["table"]["total"][col]:
                raise SystemExit(f"nigeria_census: {s['table']['name']}'s areas make {made:,} "
                                 f"in column {col}, not {s['table']['total'][col]:,}")
        for t in [s["table"], *s["areas"]]:
            p = problems(t)
            if p:
                bad[f"{s['table']['name']}/{t['name']}"] = p
    for label, p in bad.items():
        log(f"  does not add up: {label}: {'; '.join(p)}")
    return bad


VOL3_ROW = re.compile(rf"^(\d+)\s+(.+?)\s+([A-C])\s+([\d,.]+)\s+({NUM})\s+({NUM})\s+({NUM})\s*$")


def parse_vol3(pages: list[str]) -> dict[str, list[tuple[str, int, int, int]]]:
    """{state key: [(area name, men, women, persons), ...]} from Volume III."""
    out: dict[str, list[tuple[str, int, int, int]]] = {}
    for text in pages:
        if "POPULATION DISTRIBUTION BY LGA" not in text.upper():
            continue
        state = None
        for line in (ln.strip() for ln in text.splitlines()):
            if VOL3_ROW.match(line) and state:
                r = VOL3_ROW.match(line)
                out[state].append((r.group(2), number(r.group(5)), number(r.group(6)),
                                   number(r.group(7))))
                continue
            m = re.match(r"^(.+?)\s+STATE$", line, re.I) or re.match(r"^(FCT\b.*)$", line)
            if m and state is None:
                state = state_key(m.group(1))
                out.setdefault(state, [])
    return out


def cross_check(book: dict[str, Any], vol3: dict[str, list[tuple[str, int, int, int]]]
                ) -> list[str]:
    """Each state's areas in Volume III against Volume IV, by their counts."""
    said = []
    for s in book["states"]:
        sk = state_key(s["table"]["name"])
        if sk not in vol3:
            said.append(f"{s['table']['name']}: no Volume III page read")
            continue
        four = Counter((a["total"][1], a["total"][2], a["total"][0]) for a in s["areas"])
        three = Counter((m, f, p) for _, m, f, p in vol3[sk])
        if four != three:
            said.append(f"{s['table']['name']}: Volume IV alone {sorted(four - three)}; "
                        f"Volume III alone {sorted(three - four)}")
    return said


def median(groups: list[tuple[int, int | None, int, int, int]]) -> float | None:
    """The age half the people are younger than, within its five-year group."""
    base = sum(g[2] for g in groups)
    if base <= 0:
        return None
    half, before = base / 2, 0
    for low, high, n, _, _ in groups:
        if before + n >= half:
            if high is None or n <= 0:
                return None
            return round(low + (half - before) / n * (high - low + 1), 1)
        before += n
    return None


def bind(book: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
         ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """({state polygon id: state}, {area polygon id: {"state", "area"}}, [the
    polygons no census area fits])."""
    states_by_key = {state_key(s["table"]["name"]): s for s in book["states"]}
    by_polygon: dict[str, dict[str, Any]] = {}
    for shape in admin1:
        k = key(shape["name"])
        if k not in states_by_key:
            raise SystemExit(f"nigeria_census: state polygon {shape['name']!r} ({k}) is no "
                             f"census state: {sorted(states_by_key)}")
        by_polygon[shape["id"]] = states_by_key[k]
    if len({id(s) for s in by_polygon.values()}) != 37:
        raise SystemExit("nigeria_census: the state polygons are not the 37 census states")
    state_of = {sid: state_key(s["table"]["name"]) for sid, s in by_polygon.items()}
    census: dict[tuple[str, str], dict[str, Any]] = {}
    for sk, s in states_by_key.items():
        for a in s["areas"]:
            for k in keys(a["name"]):
                if (sk, k) in census and census[(sk, k)] is not a:
                    raise SystemExit(f"nigeria_census: two areas of {sk} read {k!r}")
                census[(sk, k)] = a
    bound: dict[str, dict[str, Any]] = {}
    not_drawn: list[dict[str, Any]] = []
    used: set[int] = set()
    left = []
    for shape in admin2:
        sk = state_of.get(shape["parent"], "")
        k = key(shape["name"])
        if (sk, k) in NOT_DRAWN:
            not_drawn.append(shape)
            continue
        k = ALIASES.get((sk, k), k)
        a = census.get((sk, k))
        if a is None or id(a) in used:
            left.append(f"{shape['name']!r} ({sk}, {k})")
            continue
        used.add(id(a))
        bound[shape["id"]] = {"state": states_by_key[sk], "area": a}
    if left:
        raise SystemExit(f"nigeria_census: {len(left)} polygons with no census area: {left}")
    unused = sorted(f"{s['table']['name']}: {a['name']}" for s in book["states"]
                    for a in s["areas"] if id(a) not in used
                    and (state_key(s["table"]["name"]), key(a["name"])) not in NOT_DRAWN)
    if unused:
        raise SystemExit(f"nigeria_census: census areas on no polygon: {unused}")
    return by_polygon, bound, not_drawn


def title(name: str) -> str:
    """A census name as it reads in a sentence: "OBIO/AKPOR" -> "Obio/Akpor"."""
    s = re.sub(r"(^|[\s\-/\[(])([a-z])", lambda m: m.group(1) + m.group(2).upper(),
               " ".join(str(name).lower().split()))
    return re.sub(r"\((amac|fct)\)", lambda m: f"({m.group(1).upper()})", s, flags=re.I)


def area_note(census_name: str, drawn_name: str) -> str:
    """The count's note, naming the census's area where it is spelled otherwise."""
    if key(drawn_name) in keys(census_name):
        return f"The 2006 census's count for {title(census_name)}."
    return f"The 2006 census's count for this area, which it names {title(census_name)}."


def fields(t: dict[str, Any], wrong: list[str] | None, note: str) -> dict[str, Any]:
    total, men, women = t["total"]
    out: dict[str, Any] = {
        "population": measure(total, year=YEAR, source=SOURCE),
        "population_note": note,
        "sources": [{"field": "population/sex_ratio/median_age", "name": SOURCE, "url": VOL4,
                     "license": LICENCE, "year": YEAR}],
    }
    wrong = wrong or []
    if any(p.startswith("men ") for p in wrong):
        out["sex_ratio"] = gap(NOT_AVAILABLE, "The 2006 census's table for this area prints "
                                              "men and women that do not add up to its total, "
                                              "so no sex ratio is taken from it.")
    else:
        out["sex_ratio"] = measure(round(100 * men / women, 1), unit=UNIT, year=YEAR,
                                   source=SOURCE)
    if any("age" in p for p in wrong):
        out["median_age"] = gap(NOT_AVAILABLE, "The 2006 census's table for this area prints "
                                               "age groups that do not add up to its total, so "
                                               "no median age is taken from it.")
    else:
        out["median_age"] = measure(median(t["groups"]), unit="years", year=YEAR, source=SOURCE)
        out["median_age_note"] = MEDIAN_NOTE
    return out


def build(book: dict[str, Any], bad: dict[str, list[str]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_polygon, bound, not_drawn = bind(book, admin1, admin2)
    records: list[dict[str, Any]] = []
    for shape in admin2:
        b = bound.get(shape["id"])
        if b is None:
            continue
        s, a = b["state"], b["area"]
        label = f"{s['table']['name']}/{a['name']}"
        records.append(record(
            f"NGA-NPC2006-{state_key(s['table']['name'])}-{key(a['name'])}", shape["name"],
            level="admin2", parent="NGA", country="NGA", match_by="shape_id",
            shape_id=shape["id"], **fields(a, bad.get(label), area_note(a["name"], shape["name"]))))
    # The polygon drawn as Bakassi: the census area of that name is not its ground.
    for shape in not_drawn:
        records.append(record(
            f"NGA-NPC2006-notdrawn-{key(shape['name'])}", shape["name"], level="admin2",
            parent="NGA", country="NGA", match_by="shape_id", shape_id=shape["id"],
            median_age=gap(NOT_AVAILABLE, BAKASSI), sex_ratio=gap(NOT_AVAILABLE, BAKASSI)))
    bakassi = next((a for s in book["states"] for a in s["areas"]
                    if (state_key(s["table"]["name"]), key(a["name"])) in NOT_DRAWN), None)
    for shape in admin1:
        t = by_polygon[shape["id"]]["table"]
        sk = state_key(t["name"])
        named = ("the Federal Capital Territory" if sk == "abujafederalcapitalterritory"
                 else title(t["name"]))
        note = f"The 2006 census's count for {named}."
        if sk == "crossriver" and bakassi is not None:
            note += " " + CROSS_RIVER.format(n=bakassi["total"][0])
        records.append(record(
            f"NGA-NPC2006-state-{sk}", shape["name"], level="admin1", parent="NGA",
            country="NGA", match_by="shape_id", shape_id=shape["id"],
            **fields(t, bad.get(f"{t['name']}/{t['name']}"), note)))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", action="store_true", help="print the tables read and stop")
    args = ap.parse_args()
    blob4 = http_get(VOL4, binary=True, timeout=300)
    assert isinstance(blob4, bytes)
    log(f"  Volume IV: {len(blob4):,} bytes, sha256 {digest(blob4)}")
    pages4 = pages_of(blob4)
    log(f"  {len(pages4)} pages")
    tables = parse_tables(pages4)
    log(f"  {len(tables)} tables read")
    book = organise(tables)
    if args.dump:
        for s in book["states"]:
            t = s["table"]
            log(f"STATE p{t['page']} {t['name']!r} {t['total']} median {median(t['groups'])} "
                f"{len(s['areas'])} areas {problems(t) or ''}")
            for a in s["areas"]:
                log(f"   p{a['page']} {a['name']!r} {a['total']} median {median(a['groups'])} "
                    f"{problems(a) or ''}")
    bad = check(book)
    blob3 = http_get(VOL3, binary=True, timeout=300)
    assert isinstance(blob3, bytes)
    log(f"  Volume III: {len(blob3):,} bytes, sha256 {digest(blob3)}")
    for line in cross_check(book, parse_vol3(pages_of(blob3))):
        log(f"  Volume III differs: {line}")
    if args.dump:
        return 0
    admin1 = json.loads((SITE / "admin1" / "NGA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "NGA.units.json").read_text())
    records = build(book, bad, admin1, admin2)
    for r in records:
        if r["name"] in ("Ibadan South East", "Atakunmosa West", "Kano Municipal", "Oyo",
                         "Cross River", "Bakassi", "Municipal Area Council", "Ikeja"):
            log(f"  {r['level']} {r['name']}: {r['population']} | {r['sex_ratio']} | "
                f"{r['median_age']}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin2')} of {len(admin2)} areas and "
        f"{sum(1 for r in records if r['level'] == 'admin1')} of {len(admin1)} states written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
