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

**Reading Volume IV.** Its text layer was typeset from spreadsheets and shows
it, so the reader takes each table by position and lets the sums decide:

* a figure broken at the end of a line ("64,80" over "9") is put back
  together, and a TOTAL row whose figures run over several lines is read
  across them;
* the age groups are read in order, 0-4 to 85+, whatever their labels say:
  Kebbi's and Nasarawa's print 5-9 and 10-14 as the dates "05-Sep" and
  "Oct-14", the Federal Capital Territory's drop the dashes ("1014"), Lagos's
  and Niger's print 5-9 as "4 - 9", and one of Babura's is garbled; every
  label that is not its group's is logged;
* a table's name is the nearest line above its TOTAL row that is neither a
  heading (nor a heading word the line breaks in two, "Femal" / "es") nor a
  row of figures, and the table after a page of single years of age is
  Nigeria's or a state's, every other one an area of the state before it.

**Volume III names the areas.** Volume IV prints Sabon Gari's table under
Makarfi's name, so each Volume IV table is paired with the Volume III row of
its state carrying the same men, women and persons, and both names are
offered to the boundary file; every disagreement is logged.

**Bakassi.** The 2006 census counted Bakassi local government area while it
still held the Bakassi peninsula, which passed to Cameroon in 2008. The
polygon drawn under that name is the 256 km2 left on the Nigerian side, so the
area's figures are not written on it, and Cross River's note says that its
2006 count includes the peninsula's people.

**Checks before anything is written.** Every table: men and women make the
total, in the total and in every age group, and the age groups make the
total; a table that fails is written without the figure it cannot give, and
says why. Every state's areas make the state, the states make Nigeria, and
Nigeria is 140,431,790 (71,345,488 men, 69,086,302 women). Every polygon is
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
SOURCE3 = ("National Population Commission, 2006 Population and Housing Census, Priority "
           "Table Volume III, Population Distribution by Sex, State, LGA and Senatorial "
           "District")
LICENCE = "National Population Commission publication (reuse with attribution)"
YEAR = 2006
NATIONAL = (140_431_790, 71_345_488, 69_086_302)
OUT = "nigeria_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
UNIT = "males_per_100_females"

# Table DS5's age groups, in order: (low, high); the open top group has no high.
GROUPS = [(a, a + 4) for a in range(0, 85, 5)] + [(85, None)]
# Labels a spreadsheet turned into dates.
DATE_LABELS = {"05-sep": (5, 9), "5-sep": (5, 9), "sep-05": (5, 9), "oct-14": (10, 14),
               "14-oct": (10, 14)}

NUM = r"\d[\d,]*"
FIGURE = re.compile(rf"^{NUM}$")
# A row: whatever label, then exactly three figures.
ROW = re.compile(rf"^(?P<label>.*?)\s*(?P<a>{NUM})\s+(?P<b>{NUM})\s+(?P<c>{NUM})\s*$")
# A figure broken at the end of a line: its last group has one or two digits.
BROKEN = re.compile(r"\d,\d{1,2}$")
# Words of the table's headings and the page's running head; a line of these,
# or of pieces of them, is never an area's name.
HEADING = frozenset("""table ds5 distribution of population by five year age groups and sex
total males females single years both sexes male female""".split())

# The census's state names -> the boundary file's, reduced (see key()).
STATES = {"fctabuja": "abujafederalcapitalterritory", "fct": "abujafederalcapitalterritory",
          "federalcapitalterritory": "abujafederalcapitalterritory",
          "abuja": "abujafederalcapitalterritory", "nassarawa": "nasarawa"}
# The 36 states and the Federal Capital Territory, reduced as the boundary
# file names them.
STATE_KEYS = frozenset("""abia abujafederalcapitalterritory adamawa akwaibom anambra bauchi
bayelsa benue borno crossriver delta ebonyi edo ekiti enugu gombe imo jigawa kaduna kano
katsina kebbi kogi kwara lagos nasarawa niger ogun ondo osun oyo plateau rivers sokoto taraba
yobe zamfara""".split())
# (state, the boundary file's reduced name) -> the census's reduced name,
# within the same state; each checked against both volumes' spellings.
ALIASES: dict[tuple[str, str], str] = {
    ("abujafederalcapitalterritory", "municipalareacouncil"): "abujamunicipal",
    # Spellings.
    ("abia", "isuikwuato"): "isiukwuato", ("abia", "obinwga"): "obingwa",
    ("bauchi", "dambam"): "damban", ("crossriver", "bekwarra"): "bekwara",
    ("edo", "iguegben"): "igueben", ("ekiti", "ilejemeje"): "ilejemeji",
    ("imo", "mbatoli"): "mbaitoli", ("imo", "onuimo"): "unuimo",
    ("jigawa", "kirikasama"): "kirikasamma", ("kano", "garunmalam"): "garummallam",
    ("kano", "nassarawa"): "nasarawa", ("kebbi", "bagudu"): "bagudo",
    ("kogi", "olamaboro"): "olamabolo", ("nasarawa", "nasarawaegon"): "nasarawaeggon",
    ("niger", "munya"): "muya", ("osun", "atakunmosaeast"): "atakumosaeast",
    ("osun", "atakunmosawest"): "atakumosawest", ("osun", "ayedade"): "aiyedade",
    ("osun", "ayedire"): "aiyedire", ("plateau", "barkinladi"): "barikinladi",
    ("rivers", "emuoha"): "emohua", ("rivers", "obioakpor"): "obiaakpor",
    ("yobe", "tarmuwa"): "tarmua", ("zamfara", "birninmagajikiyaw"): "birninmagaji",
    # Names the census uses for areas since renamed: Atisbo was Atigbo, and
    # Yewa North and South were Egbado North and South.
    ("oyo", "atisbo"): "atigbo", ("ogun", "yewanorth"): "egbadonorth",
    ("ogun", "yewasouth"): "egbadosouth",
}
# The census area whose figures fit no polygon: Bakassi as it stood in 2006.
NOT_DRAWN = {("crossriver", "bakassi")}
# Tables of people a state's total counts outside all its areas.
UNPLACED = {"disputedareas"}
UNPLACED_NOTE = ("The count includes {n:,} people whom the census counts in areas it marks as "
                 "disputed, outside all of the state's local government areas.")
BAKASSI = ("The 2006 census counted Bakassi local government area while it held the Bakassi "
           "peninsula, which passed to Cameroon in 2008; this polygon is the part left on the "
           "Nigerian side, around Ikang, and no figure is published for it alone.")
CROSS_RIVER = ("This count includes Bakassi local government area as it stood in 2006, with "
               "the Bakassi peninsula that passed to Cameroon in 2008 ({n:,} people in the "
               "whole area).")
MEDIAN_NOTE = ("Interpolated within the five-year age group that holds the middle person, "
               "from the 2006 census's count by age.")


def key(name: str) -> str:
    """A name reduced to its letters, without STATE or a closing LGA."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\bstate\b|\blga\s*$", " ", s.strip())
    return "".join(c for c in s if "a" <= c <= "z")


def keys(name: str) -> list[str]:
    """Every reduction a census name may be drawn under: whole, without what
    it puts in brackets, and the bracketed name itself ("IBADAN CENTRAL [IBADAN
    NORTH EAST]", "ABUJA MUNICIPAL [AMAC]", "NAFADA (BAJOGA)")."""
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
    """A line of heading words, page numbers, dashes, or the pieces a heading
    word is broken into at a line's end ("Femal" / "es")."""
    words = line.lower().replace(":", " ").split()
    if not words:
        return True
    for w in words:
        if w in HEADING or w.isdigit() or w in ("-", "–", "—"):
            continue
        if len(w) >= 2 and any(h.startswith(w) or h.endswith(w) for h in HEADING):
            continue
        return False
    return True


def is_name(line: str) -> bool:
    """A line that can be (part of) an area's name: letters, not a heading,
    not a row of figures (a single year's row begins with its age)."""
    return (any(c.isalpha() for c in line) and not line[:1].isdigit()
            and not is_heading(line) and not line.upper().startswith("TOTAL")
            and not ROW.match(line))


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def pages_of(blob: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


SINGLE_YEARS = "\x00single years\x00"


def mend(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Put back the figures a line's end breaks: "64,80" then "9" is 64,809."""
    out: list[tuple[int, str]] = []
    for page, line in lines:
        if out and BROKEN.search(out[-1][1]) and re.match(r"^\d{1,2}(?:\s|$)", line):
            head, _, rest = line.partition(" ")
            out[-1] = (out[-1][0], out[-1][1] + head)
            if rest.strip():
                out.append((page, rest.strip()))
            continue
        out.append((page, line))
    return out


def label_ok(label: str, low: int, high: int | None) -> bool:
    """Whether a row's printed label is its group's, in any of the forms used."""
    text = " ".join(label.lower().split())
    if text in DATE_LABELS:
        return DATE_LABELS[text] == (low, high)
    digits = re.sub(r"\D", "", text)
    return digits == (f"{low}{high}" if high is not None else f"{low}")


def parse_tables(pages: list[str]) -> list[dict[str, Any]]:
    """Every Table DS5 in the volume, in order: name, page, total and groups.

    A page of single years of age (Nigeria and each state have one, before
    their five-year table) is skipped -- its rows are not five-year groups,
    and the same area is printed in five-year groups on the page after it --
    and the next table is marked as the one that page belongs to: that is how
    a state's table is told from its areas', since the volume names some
    states with "STATE" and others not ("LAGOS"), and several areas carry
    their state's name (Bauchi, Gombe, Ebonyi).
    """
    raw: list[tuple[int, str]] = []
    for page_number, text in enumerate(pages, 1):
        if "single years" in text.lower():
            raw.append((page_number, SINGLE_YEARS))
            continue
        raw.extend((page_number, ln.strip()) for ln in text.splitlines() if ln.strip())
    lines = mend(raw)
    tables: list[dict[str, Any]] = []
    after_single = False
    i = 0
    while i < len(lines):
        page, line = lines[i]
        if line == SINGLE_YEARS:
            after_single = True
            i += 1
            continue
        if not re.match(r"^TOTAL\b", line):
            i += 1
            continue
        # The total's three figures, from this line and any lines of figures after it.
        figures = [t for t in line.split()[1:] if FIGURE.match(t)]
        k = i + 1
        while len(figures) < 3 and k < len(lines) \
                and all(FIGURE.match(t) for t in lines[k][1].split()):
            figures.extend(lines[k][1].split())
            k += 1
        restored = False
        if len(figures) == 2:
            # Zing's TOTAL row prints its men and women and no total: the total
            # is their sum, which the age groups' sums then check.
            figures = [f"{number(figures[0]) + number(figures[1])}", *figures]
            restored = True
        if len(figures) != 3:
            log(f"  page {page}: a TOTAL row with figures {figures} is not read")
            i += 1
            continue
        j, name = i - 1, []
        while j >= 0 and is_heading(lines[j][1]):
            j -= 1
        while j >= 0 and lines[j][1] != SINGLE_YEARS and is_name(lines[j][1]) and len(name) < 2:
            name.insert(0, lines[j][1])
            j -= 1
        rows: list[tuple[str, tuple[int, int, int]]] = []
        noise = 0
        while k < len(lines) and len(rows) < len(GROUPS):
            text = lines[k][1]
            r = ROW.match(text)
            # A row whose figures run on to the next line ("0 - 4 20,746" then
            # "10,793 9,953"): read the two lines as one.
            if not r and k + 1 < len(lines) and lines[k + 1][1].split() \
                    and all(FIGURE.match(t) for t in lines[k + 1][1].split()):
                r = ROW.match(f"{text} {lines[k + 1][1]}")
                if r:
                    k += 1
            if r and not text.upper().startswith("TOTAL"):
                rows.append((r.group("label"), (number(r.group("a")), number(r.group("b")),
                                                number(r.group("c")))))
            elif is_heading(text):
                pass
            elif len(text) <= 12 and noise < 3 and not re.search(r"[a-z]{3}", text):
                noise += 1             # a garbled label: "G23720 -", "24"
            else:
                break
            k += 1
        groups, misprints = [], []
        for (low, high), (label, (gt, gm, gf)) in zip(GROUPS, rows):
            if not label_ok(label, low, high):
                misprints.append(f"{label or '(none)'} for {low}-{high if high else ''}")
            groups.append((low, high, gt, gm, gf))
        table = {"name": " ".join(name), "page": page,
                 "total": tuple(number(x) for x in figures), "groups": groups,
                 "single_before": after_single}
        if misprints:
            table["misprints"] = misprints
        if restored:
            table["misprints"] = [*table.get("misprints", []), "no total printed: men plus women"]
        tables.append(table)
        after_single = False
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
    """{"nation": table, "states": [{"table": ..., "areas": [table, ...]}, ...]}.

    A table that follows a page of single years is Nigeria's or a state's;
    every other table is an area of the state before it. A state table whose
    name is not one of the 37 is refused rather than guessed at."""
    nation, states = None, []
    expect_state, pending = False, []
    for t in tables:
        name = t["name"].upper()
        expect_state = expect_state or t.get("single_before")
        if key(name) in UNPLACED:
            # Taraba's "*DISPUTED AREAS", printed between the state's single
            # years and its five-year table: counted in the state's total and
            # in none of its areas.
            t["unplaced"] = True
            if expect_state:
                pending.append(t)
            elif states:
                states[-1]["areas"].append(t)
            continue
        if expect_state and name == "NIGERIA":
            nation = t
        elif expect_state:
            if state_key(name) not in STATE_KEYS:
                raise SystemExit(f"nigeria_census: page {t['page']}: {t['name']!r} follows a "
                                 "page of single years but is no state")
            states.append({"table": t, "areas": pending})
            pending = []
        elif not states:
            raise SystemExit(f"nigeria_census: {t['name']!r} (page {t['page']}) comes "
                             "before any state")
        else:
            states[-1]["areas"].append(t)
        expect_state = False
    if nation is None:
        raise SystemExit("nigeria_census: no table for Nigeria")
    return {"nation": nation, "states": states}


def check(book: dict[str, Any]) -> dict[int, list[str]]:
    """The volume's sums, checked; {id(table): its own problems} for the
    tables that do not add up, which are written without what they cannot give."""
    nation = book["nation"]
    if nation["total"] != NATIONAL:
        raise SystemExit(f"nigeria_census: Nigeria is {nation['total']}, not {NATIONAL}")
    if len(book["states"]) != 37:
        raise SystemExit(f"nigeria_census: {len(book['states'])} states, not 37: "
                         f"{[s['table']['name'] for s in book['states']]}")
    areas = sum(1 for s in book["states"] for a in s["areas"] if not a.get("unplaced"))
    if areas != 774:
        counts = {s["table"]["name"]: len(s["areas"]) for s in book["states"]}
        raise SystemExit(f"nigeria_census: {areas} local government areas, not 774: {counts}")
    for col in range(3):
        made = sum(s["table"]["total"][col] for s in book["states"])
        if made != nation["total"][col]:
            raise SystemExit(f"nigeria_census: the states make {made:,} in column {col}, "
                             f"not Nigeria's {nation['total'][col]:,}")
    bad: dict[int, list[str]] = {}
    for s in book["states"]:
        for col in range(3):
            made = sum(a["total"][col] for a in s["areas"])
            if made != s["table"]["total"][col]:
                raise SystemExit(f"nigeria_census: {s['table']['name']}'s areas make {made:,} "
                                 f"in column {col}, not {s['table']['total'][col]:,}")
        for t in [s["table"], *s["areas"]]:
            if t.get("from_vol3"):
                continue
            p = problems(t)
            if p:
                bad[id(t)] = p
                log(f"  does not add up: {s['table']['name']}/{t['name']}: {'; '.join(p)}")
            if t.get("misprints"):
                log(f"  read by position: {s['table']['name']}/{t['name']}: {t['misprints']}")
    return bad


VOL3_ROW = re.compile(rf"^(\d+)\s+(.+?)\s+([A-C])\s+([\d,.]+)\s+({NUM})\s+({NUM})\s+({NUM})\s*$")


def parse_vol3(pages: list[str]) -> dict[str, list[tuple[str, int, int, int]]]:
    """{state key: [(area name, men, women, persons), ...]} from Volume III's
    pages of areas, each headed by its state's name in capitals."""
    out: dict[str, list[tuple[str, int, int, int]]] = {}
    for text in pages:
        if "POPULATION DISTRIBUTION BY LGA" not in text.upper():
            continue
        state = None
        for line in mend([(0, ln.strip()) for ln in text.splitlines() if ln.strip()]):
            line = line[1]
            r = VOL3_ROW.match(line)
            if r and state:
                out[state].append((r.group(2), number(r.group(5)), number(r.group(6)),
                                   number(r.group(7))))
                continue
            m = re.match(r"^([A-Z][A-Z .'-]+?)(?:\s+STATE)?$", line)
            if m and state_key(m.group(1)) in STATE_KEYS:
                state = state_key(m.group(1))
                out.setdefault(state, [])
    return out


def name_from_vol3(book: dict[str, Any], vol3: dict[str, list[tuple[str, int, int, int]]]
                   ) -> list[str]:
    """Each area's Volume III name, from the row of its state with the same
    men, women and persons; the differences between the volumes, in words."""
    said = []
    for s in book["states"]:
        sk = state_key(s["table"]["name"])
        rows = vol3.get(sk, [])
        if not rows:
            said.append(f"{s['table']['name']}: no Volume III page read")
            continue
        by_counts: dict[tuple[int, int, int], list[str]] = {}
        for name, m, f, p in rows:
            by_counts.setdefault((p, m, f), []).append(name)
        unmatched = []
        areas = [a for a in s["areas"] if not a.get("unplaced")]
        matched: set[tuple[int, int, int]] = set()
        for a in areas:
            names = by_counts.get(tuple(a["total"]), [])
            if len(names) == 1:
                a["vol3"] = names[0]
                matched.add(tuple(a["total"]))
                if not set(keys(names[0])) & set(keys(a["name"])):
                    said.append(f"{s['table']['name']}: Volume IV's {a['name']!r} "
                                f"{a['total']} is Volume III's {names[0]!r}")
            else:
                unmatched.append(f"{a['name']} {a['total']}")
        if unmatched:
            said.append(f"{s['table']['name']}: no single Volume III row has the counts of "
                        f"{unmatched}")
        # An area Volume IV prints no table for (Kaduna's Kaura): its count and
        # sexes from Volume III, and no ages.
        for name, m, f, p in rows:
            if (p, m, f) not in matched and len(areas) < len(rows):
                s["areas"].append({"name": name, "vol3": name, "page": None, "total": (p, m, f),
                                   "groups": [], "from_vol3": True})
                said.append(f"{s['table']['name']}: Volume IV prints no table for Volume III's "
                            f"{name!r} {(p, m, f)}; its count and sexes are read from Volume III")
        if len(rows) != len(areas):
            said.append(f"{s['table']['name']}: Volume III lists {len(rows)} areas, "
                        f"Volume IV {len(areas)}")
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


def area_keys(a: dict[str, Any]) -> list[str]:
    """The keys an area may be drawn under: Volume III's name first."""
    out = keys(a["vol3"]) if a.get("vol3") else []
    return out + [k for k in keys(a["name"]) if k not in out]


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
        state = states_by_key.get(sk)
        found = [a for a in (state["areas"] if state else [])
                 if k in area_keys(a) and not a.get("unplaced")]
        # A name both volumes agree on wins over one only Volume IV prints.
        if len(found) > 1:
            found = [a for a in found if k in keys(a.get("vol3") or "")] or found
        if len(found) != 1 or id(found[0]) in used:
            left.append(f"{shape['name']!r} ({sk}, {k}: {[a['name'] for a in found]})")
            continue
        used.add(id(found[0]))
        bound[shape["id"]] = {"state": state, "area": found[0]}
    if left:
        raise SystemExit(f"nigeria_census: {len(left)} polygons with no single census area: "
                         f"{left}")
    unused = sorted(f"{s['table']['name']}: {a['name']} ({a.get('vol3')})"
                    for s in book["states"] for a in s["areas"] if id(a) not in used
                    and not a.get("unplaced")
                    and (state_key(s["table"]["name"]), key(a["name"])) not in NOT_DRAWN)
    if unused:
        raise SystemExit(f"nigeria_census: census areas on no polygon: {unused}")
    return by_polygon, bound, not_drawn


def title(name: str) -> str:
    """A census name as it reads in a sentence: "OBIO/AKPOR" -> "Obio/Akpor"."""
    s = re.sub(r"(^|[\s\-/\[(])([a-z])", lambda m: m.group(1) + m.group(2).upper(),
               " ".join(str(name).lower().split()))
    s = re.sub(r"\s+Lga$", "", s)
    return re.sub(r"[\[(](amac|fct)[\])]", lambda m: f"({m.group(1).upper()})", s, flags=re.I)


def area_note(a: dict[str, Any], drawn_name: str) -> str:
    """The count's note, naming the census's area where it is spelled otherwise."""
    census_name = a.get("vol3") or a["name"]
    if key(drawn_name) in area_keys(a):
        return f"The 2006 census's count for {title(census_name)}."
    return f"The 2006 census's count for this area, which it names {title(census_name)}."


def fields(t: dict[str, Any], wrong: list[str] | None, note: str) -> dict[str, Any]:
    total, men, women = t["total"]
    if t.get("from_vol3"):
        return {
            "population": measure(total, year=YEAR, source=SOURCE3),
            "population_note": note,
            "sex_ratio": measure(round(100 * men / women, 1), unit=UNIT, year=YEAR,
                                 source=SOURCE3),
            "median_age": gap(NOT_AVAILABLE, "The 2006 census's volume of ages by local "
                                             "government area (Priority Table Volume IV) "
                                             "prints no table for this area, so no median age "
                                             "is shown."),
            "sources": [{"field": "population/sex_ratio", "name": SOURCE3, "url": VOL3,
                         "license": LICENCE, "year": YEAR}],
        }
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


def build(book: dict[str, Any], bad: dict[int, list[str]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_polygon, bound, not_drawn = bind(book, admin1, admin2)
    records: list[dict[str, Any]] = []
    for shape in admin2:
        b = bound.get(shape["id"])
        if b is None:
            continue
        s, a = b["state"], b["area"]
        records.append(record(
            f"NGA-NPC2006-{state_key(s['table']['name'])}-{key(a.get('vol3') or a['name'])}",
            shape["name"], level="admin2", parent="NGA", country="NGA", match_by="shape_id",
            shape_id=shape["id"], **fields(a, bad.get(id(a)), area_note(a, shape["name"]))))
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
        bare = re.sub(r"(?i)\s+state$", "", t["name"])
        named = ("the Federal Capital Territory" if sk == "abujafederalcapitalterritory"
                 else f"{title(bare)} State")
        note = f"The 2006 census's count for {named}."
        if sk == "crossriver" and bakassi is not None:
            note += " " + CROSS_RIVER.format(n=bakassi["total"][0])
        unplaced = sum(a["total"][0] for a in by_polygon[shape["id"]]["areas"]
                       if a.get("unplaced"))
        if unplaced:
            note += " " + UNPLACED_NOTE.format(n=unplaced)
        records.append(record(
            f"NGA-NPC2006-state-{sk}", shape["name"], level="admin1", parent="NGA",
            country="NGA", match_by="shape_id", shape_id=shape["id"],
            **fields(t, bad.get(id(t)), note)))
    return records


def read(dump: bool = False) -> dict[str, Any]:
    blob4 = http_get(VOL4, binary=True, timeout=300)
    assert isinstance(blob4, bytes)
    log(f"  Volume IV: {len(blob4):,} bytes, sha256 {digest(blob4)}")
    pages4 = pages_of(blob4)
    tables = parse_tables(pages4)
    log(f"  {len(pages4)} pages, {len(tables)} tables read")
    book = organise(tables)
    blob3 = http_get(VOL3, binary=True, timeout=300)
    assert isinstance(blob3, bytes)
    log(f"  Volume III: {len(blob3):,} bytes, sha256 {digest(blob3)}")
    vol3 = parse_vol3(pages_of(blob3))
    log(f"  Volume III: {sum(len(v) for v in vol3.values())} areas in {len(vol3)} states")
    for line in name_from_vol3(book, vol3):
        log(f"  Volume III: {line}")
    if dump:
        for s in book["states"]:
            t = s["table"]
            log(f"STATE p{t['page']} {t['name']!r} {t['total']} median {median(t['groups'])} "
                f"{len(s['areas'])} areas {problems(t) or ''}")
            for a in s["areas"]:
                log(f"   p{a['page']} {a['name']!r} [{a.get('vol3')}] {a['total']} median "
                    f"{median(a['groups'])} {problems(a) or ''}")
    book["bad"] = check(book)
    return book


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", action="store_true", help="print the tables read and stop")
    args = ap.parse_args()
    book = read(dump=args.dump)
    if args.dump:
        return 0
    admin1 = json.loads((SITE / "admin1" / "NGA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "NGA.units.json").read_text())
    records = build(book, book["bad"], admin1, admin2)
    for r in records:
        if r["name"] in ("Ibadan South East", "Atakunmosa West", "Kano Municipal", "Oyo",
                         "Cross River", "Bakassi", "Municipal Area Council", "Sabon Gari",
                         "Makarfi", "Miga"):
            log(f"  {r['level']} {r['name']}: {r['population']} | {r['sex_ratio']} | "
                f"{r['median_age']} | {r.get('population_note')}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin2')} of {len(admin2)} areas and "
        f"{sum(1 for r in records if r['level'] == 'admin1')} of {len(admin1)} states written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
