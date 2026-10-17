#!/usr/bin/env python3
"""Egypt -- governorates, kisms and markazes: CAPMAS's 2017 census and 2023
estimate, and its 2006 census where the units have been redrawn since.

The Central Agency for Public Mobilization and Statistics (CAPMAS) took the
Population, Housing and Establishments Census on 28 March 2017 and estimates
the population of every kism and markaz each year. Its own site serves none of
this to a reader outside Egypt; citypopulation.de tabulates it from CAPMAS
(``URL``): every governorate, kism, markaz and police district with its counts
at the 1996, 2006 and 2017 censuses and the estimate for 1 July 2023, and for
each, on its own page, the 2017 census's count of everyone by sex and ten-year
age group. OCHA publishes on HDX the 2006 census's count of every kism and
markaz by sex (``HDX_DATASET``).

**The outlines are 2006's.** The map's 364 second-level outlines are the kisms
and markazes of the 2006 census -- their labels are the English names of
OCHA's 2006 table, 2006's Muntaza, Amriya and Raml where CAPMAS now counts
Muntaza 1 and 2, Amriya 1 and 2, Raml 1 and 2. Each outline is bound to the
2006 unit of its label (in its governorate, or in another where the outline is
filed under the wrong one), a kism and a markaz of one name by size, and the
2006 unit to the units CAPMAS counts today by their Arabic names: the same
name, the parts numbered since ("قسم أول/ثان ..."), and, where those fall
short of the 2006 count, the one or two units of other names whose 2006 people
make up the rest (``carve``).

**The ground test.** CAPMAS's counts of today's units at the 2006 census,
added up, must make the 2006 unit's own count -- to within 2%, or to within 3%
once scaled by the governorate's two 2006 totals where those differ by less
than 5% (the two tabulations of 2006 differ by about 1% nationally). An
outline that passes is written with today's figures:

* the population: CAPMAS's estimate for 1 July 2023 (the 2017 count in the
  note);
* the median age, interpolated within the ten-year group that holds the middle
  person, and men per 1,000 women, from the 2017 census by sex and age.

An outline that does not -- its 2006 unit has been redrawn in a way that does
not follow its outline -- is written with the 2006 census's own count and men
per 1,000 women, and its median age says why there is none.

The governorates are written the same way from their own rows and pages.

**Not written.** The fourteen outlines labelled Zemam Out -- the land outside
the zimam, the bounds of the towns and villages, which no census table counts
as a district -- and the port police districts, which CAPMAS lists without a
population, say so. Hala'ib, the kism of the triangle north of 22°N that Egypt
and Sudan both claim, is not drawn on Egypt's side; it is never written, and
the Red Sea governorate is written without it.

Usage:
    python -m scripts.fetch_census.egypt_census
"""

from __future__ import annotations

import argparse
import io
import itertools
import json
import re
import time
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from typing import Any

from . import uscb
from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record,
                      write_json)

URL = "https://www.citypopulation.de/en/egypt/admin/"
BASE = "https://www.citypopulation.de"
HDX_DATASET = "egypt-population-statistics-0"
OUT = "egypt_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE_2017 = ("Central Agency for Public Mobilization and Statistics (CAPMAS), Population, "
               "Housing and Establishments Census 2017: population by sex and ten-year age "
               "group, as citypopulation.de tabulates it")
SOURCE_2023 = ("Central Agency for Public Mobilization and Statistics (CAPMAS), population "
               "estimate for 1 July 2023, as citypopulation.de tabulates it")
SOURCE_2006 = ("Central Agency for Public Mobilization and Statistics (CAPMAS), Population, "
               "Housing and Establishments Census 2006: population by sex of every kism and "
               "markaz, as OCHA publishes it on HDX")
CP_NAME = "citypopulation.de (Thomas Brinkhoff), after CAPMAS"
CP_LICENCE = "citation of citypopulation.de required"
# CAPMAS's governorate code -> the map's ISO 3166-2 code; two outlines carry no
# code and are found by label (``UNCODED``).
GOV_ISO = {"01": "EG-C", "02": "EG-ALX", "03": "EG-PTS", "04": "EG-SUZ", "11": "EG-DT",
           "12": "EG-DK", "13": "EG-SHR", "14": "EG-KB", "15": "EG-KFS", "16": "EG-GH",
           "17": "EG-MNF", "18": "EG-BH", "19": "EG-IS", "21": "EG-GZ", "22": "EG-BNS",
           "23": "EG-FYM", "24": "EG-MN", "25": "EG-AST", "26": "EG-SHG", "27": "EG-KN",
           "28": "EG-ASN", "29": "EG-LX", "31": "EG-BA", "32": "EG-WAD", "33": "EG-MT",
           "34": "EG-SIN", "35": "EG-JS"}
UNCODED = {"EG-GH": "Gharbiyya Governorate", "EG-MT": "Matrouh Governorate"}
# A 2006 unit whose rows OCHA's table labels with another unit's English name
# (gov code, Arabic name) -> the label of its outline: Shaykh Zayed and Awsim,
# both labelled Waraq; 6th of October's two kisms, whose labels a spreadsheet
# read as dates ("06-Oct-01").
RELABEL = {("21", "قسم الشيخ زايد"): "Shaykh Zayed", ("21", "مركز أوسيم"): "Auseem",
           ("21", "قسم أول 6 أكتوبر"): "6 October-1", ("21", "قسم ثان 6 أكتوبر"): "6 October-2"}
# Two outlines labelled North Coast, both filed under Matrouh: the eastern one
# continues Burg al-Arab's side (Alexandria's) of the boundary at 29.38°E, the
# western one Al-Hammam's (Matrouh's). Shape id -> (gov code, Arabic name).
SHAPES = {"37247803B38142631960117": ("02", "الساحل الشمالى_جزء"),
          "37247803B36627997079635": ("33", "قسم الساحل الشمالى-جزء")}
ZEMAM = "zemamout"
# The kism of Hala'ib, in the triangle Egypt and Sudan both claim.
CLAIMED = {"3108"}
PLAIN, SCALED, SEARCH = 0.02, 0.03, 0.01
# Men per 1,000 women at which a unit's note says why (Tura's 2,700).
INSTITUTIONS = 1500
SCALE_LIMIT = 0.05
PAUSE = 0.4
AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": None,
                    "ئ": "ي", "ؤ": "و"})
ORDINALS = {"اول": 1, "ثان": 2, "ثاني": 2, "ثالث": 3, "رابع": 4, "خامس": 5, "سادس": 6,
            "سابع": 7, "ثامن": 8}
KINDS = (("قسم شرطه", "kism"), ("قسم", "kism"), ("مركز", "markaz"),
         ("اداره شرطه", "police"), ("شرطه", "police"), ("مدينه", "city"))


# ---------------------------------------------------------------- names

def arfold(text: Any) -> str:
    out = unicodedata.normalize("NFKC", str(text or "")).translate(AR)
    out = "".join(c for c in out if unicodedata.category(c) != "Cf")
    return " ".join(re.sub(r"[_\-]", " ", out).split())


def arkey(text: Any) -> tuple[str, int | None, str]:
    """(kind, ordinal, name) of an Arabic unit name: 'قسم ثان المنتزة' ->
    ('kism', 2, 'المنتزه'). 'Police' and 'city' before the name are dropped,
    as the two tables write them for one unit and not the other ('مركز باريس',
    'مركز شرطة باريس'; 'قسم بدر', 'قسم مدينة بدر')."""
    name = arfold(text)
    kind = "other"
    for word, k in KINDS:
        if name.startswith(word):
            kind, name = k, name[len(word):].strip()
            break
    ordinal, rest = None, []
    for w in name.split():
        if w in ORDINALS and ordinal is None:
            ordinal = ORDINALS[w]
        elif w in ("شرطه", "مدينه") and not rest:
            continue
        else:
            rest.append(w)
    return kind, ordinal, re.sub(r"جزء$", "", "".join(rest))


def keys(native: str) -> set[tuple[str, int | None, str]]:
    """A unit CAPMAS names twice ('قسم أول 6 أكتوبر / قسم ثالث 6 أكتوبر') has both."""
    return {arkey(part) for part in str(native).split("/") if part.strip()}


def latin(text: Any) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalnum() and not unicodedata.combining(c))


def count(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


# ------------------------------------------------------- citypopulation

def strip_tags(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").split())


def clean(name: str) -> str:
    """'Al-Manṣūrah 1 [ El Mansoura ]' -> 'Al-Manṣūrah 1'; 'Shurṭah Bārīs'
    (Baris police district) -> 'Bārīs'."""
    name = re.sub(r"\s*\[.*?\]", "", str(name)).strip()
    return re.sub(r"^Shurṭah\s+", "", name)


def parse_admin(html: str) -> dict[str, Any]:
    """{"govs": {code: row}, "units": {code: row}} from the table of every unit.

    A row: name, status, Arabic name, the counts of 1996, 2006, 2017 and the
    estimate of 2023 (None where the page has '...'), and the link to its page."""
    govs: dict[str, dict[str, Any]] = {}
    units: dict[str, dict[str, Any]] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        m = re.search(r'id="i(\d+)"', tr)
        status = re.search(r'<td class="rstatus">(.*?)</td>', tr, flags=re.S)
        native = re.search(r'<td class="rnative[^"]*">(.*?)</td>', tr, flags=re.S)
        if not (m and status and native):
            continue
        name = re.search(r'<td class="rname"[^>]*>(.*?)</td>', tr, flags=re.S)
        pops = [count(strip_tags(p)) for p in
                re.findall(r'<td class="rpop">(.*?)</td>', tr, flags=re.S)]
        link = re.search(r'href="(/en/egypt/admin/[^"]+)"', tr)
        if len(pops) != 4:
            raise SystemExit(f"egypt_census: row i{m.group(1)} has {len(pops)} counts, not 4")
        row = {"code": m.group(1), "name": strip_tags(name.group(1)) if name else "",
               "status": strip_tags(status.group(1)), "ar": strip_tags(native.group(1)),
               "p1996": pops[0], "p2006": pops[1], "p2017": pops[2], "p2023": pops[3],
               "href": link.group(1) if link else None}
        if row["status"] == "Governorate":
            row["code"] = row["code"].zfill(2)
            govs[row["code"]] = row
        elif len(row["code"]) == 4:
            row["gov"] = row["code"][:2]
            units[row["code"]] = row
    return {"govs": govs, "units": units}


def parse_pyramid(html: str) -> list[tuple[int, int | None, int, int]] | None:
    """The 2017 census's men and women by ten-year age group, from the page's
    chart data: [(low, high, men, women)], youngest first; None if absent."""
    if "Age Distribution (C 2017)" not in html:
        return None
    m = re.search(r"var addChartData = (\[.*?\]);?\s*</script>", html, flags=re.S)
    if not m:
        return None
    for chart in json.loads(m.group(1)):
        if chart.get("name") == "Age Distribution" and chart.get("type") == "pyramid":
            # Ten-year groups to an open 90+; a page leaves out a group no
            # one is in, which is a group of nobody, not a break.
            found: dict[int, tuple[int, int]] = {}
            for label, men, women in chart["data"][1:]:
                g = re.match(r"(\d+)\s*(?:-\s*(\d+)|\+)", str(label))
                low = int(g.group(1)) if g else -1
                high = int(g.group(2)) if g and g.group(2) else None
                if not g or low % 10 or (high is not None and high != low + 9) \
                        or (high is None and low != 90) or low > 90:
                    raise SystemExit(f"egypt_census: an age group reads {label!r}")
                found[low] = (abs(int(men)), abs(int(women)))
            return [(low, None if low == 90 else low + 9, *found.get(low, (0, 0)))
                    for low in range(0, 100, 10)]
    return None


def grouped_median(groups: list[tuple[int, int | None, int]]) -> float | None:
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def add(pyramids: list[list[tuple[int, int | None, int, int]]], sign: list[int] | None = None
        ) -> list[tuple[int, int | None, int, int]]:
    sign = sign or [1] * len(pyramids)
    first = pyramids[0]
    return [(lo, hi, sum(s * p[i][2] for s, p in zip(sign, pyramids)),
             sum(s * p[i][3] for s, p in zip(sign, pyramids)))
            for i, (lo, hi, _, _) in enumerate(first)]


# ------------------------------------------------------------------ HDX

def read_hdx(book: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """OCHA's 2006 workbook: (district rows, {gov code: province row})."""
    def rows(name: str) -> list[list[Any]]:
        if name not in book.sheetnames:
            raise SystemExit(f"egypt_census: the 2006 workbook has no sheet {name!r}")
        return [list(r) for r in book[name].iter_rows(values_only=True)]

    def num(v: Any) -> int | None:
        return None if v in (None, "") else int(round(float(v)))
    districts = []
    for r in rows("District")[1:]:
        if not r or r[0] in (None, "Total") or r[5] in (None, ""):
            continue
        districts.append({"gov": f"{int(r[2]):02d}", "en": str(r[3]).strip(),
                          "ar": str(r[4]).strip(), "code": int(r[5]),
                          "m": num(r[6]), "f": num(r[7]), "t": num(r[8])})
    provinces = {}
    for r in rows("Province")[1:]:
        if not r or r[0] in (None, "Total") or r[2] in (None, ""):
            continue
        provinces[f"{int(r[2]):02d}"] = {"m": num(r[3]), "f": num(r[4]), "t": num(r[5])}
    total = sum(d["t"] or 0 for d in districts)
    if total != sum(p["t"] for p in provinces.values()):
        raise SystemExit(f"egypt_census: the 2006 districts make {total:,}, not the "
                         f"governorates' {sum(p['t'] for p in provinces.values()):,}")
    for d in districts:
        if None not in (d["m"], d["f"], d["t"]) and d["m"] + d["f"] != d["t"]:
            raise SystemExit(f"egypt_census: 2006 {d['en']}: men and women do not make "
                             f"{d['t']:,}")
    return districts, provinces


def units_2006(districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OCHA's rows grouped into the 2006 units they count, by governorate and
    Arabic name, each with the English labels its rows carry."""
    groups: dict[tuple[str, tuple], list[dict[str, Any]]] = defaultdict(list)
    for d in districts:
        groups[(d["gov"], arkey(d["ar"]))].append(d)
    out = []
    for (gov, key), rows in groups.items():
        relabel = next((v for (g, a), v in RELABEL.items() if g == gov and arkey(a) == key), None)
        labels = {latin(relabel)} if relabel else {latin(r["en"]) for r in rows}
        known = all(r["t"] is not None for r in rows)
        out.append({"gov": gov, "key": key, "ar": rows[0]["ar"], "rows": rows,
                    "labels": labels, "codes": sorted({r["code"] for r in rows}),
                    "m": sum(r["m"] or 0 for r in rows) if known else None,
                    "f": sum(r["f"] or 0 for r in rows) if known else None,
                    "t": sum(r["t"] or 0 for r in rows) if known else None})
    return out


# -------------------------------------------------------------- binding

def size(shape: dict[str, Any]) -> float:
    b = shape.get("bbox") or [0, 0, 0, 0]
    return (b[2] - b[0]) * (b[3] - b[1])


def bind_outlines(shapes: list[dict[str, Any]], gov_of: dict[str, str],
                  units: list[dict[str, Any]], report: list[str]
                  ) -> dict[str, list[dict[str, Any]]]:
    """Outline id -> the 2006 units it holds."""
    bound: dict[str, list[dict[str, Any]]] = {}
    by_gov: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        by_gov[u["gov"]].append(u)
    labels_drawn: dict[str, set[str]] = defaultdict(set)
    for s in shapes:
        labels_drawn[gov_of[s["id"]]].add(latin(s["name"]))
    for s in shapes:
        gov, label = gov_of[s["id"]], latin(s["name"])
        if label == ZEMAM:
            continue
        if s["id"] in SHAPES:
            g, ar = SHAPES[s["id"]]
            hits = [u for u in by_gov[g] if u["key"] == arkey(ar)]
            if len(hits) != 1:
                raise SystemExit(f"egypt_census: SHAPES names {ar!r}, found {len(hits)} times")
            bound[s["id"]] = hits
            continue
        cands = [u for u in by_gov[gov] if label in u["labels"]]
        where = gov
        if not cands:
            # An outline filed under the wrong governorate: its label in the
            # one governorate that has it and draws no outline of that label.
            cands = [u for u in units if label in u["labels"]
                     and label not in labels_drawn[u["gov"]]]
            if len({u["gov"] for u in cands}) == 1:
                where = cands[0]["gov"]
                report.append(f"  {s['name']!r} (filed under {gov}): the 2006 unit of "
                              f"governorate {where}")
            else:
                cands = []
        if len(cands) > 1:
            sole = [u for u in cands if u["labels"] == {label}]
            cands = sole or cands
        twins = [t for t in shapes if gov_of[t["id"]] == gov and latin(t["name"]) == label]
        kinds = {u["key"][0] for u in cands}
        if len(twins) == 2 and len(cands) == 2 and kinds == {"kism", "markaz"}:
            small = min(twins, key=size)
            want = "kism" if s["id"] == small["id"] else "markaz"
            bound[s["id"]] = [u for u in cands if u["key"][0] == want]
        elif len(twins) == 1 and len(cands) == 1:
            bound[s["id"]] = cands
        elif len(twins) == 1 and len(cands) == 2 and kinds == {"kism", "markaz"}:
            bound[s["id"]] = cands
            report.append(f"  {s['name']!r}: one outline for the kism and the markaz")
        else:
            report.append(f"  {s['name']!r} ({gov}): {len(cands)} 2006 units "
                          f"{[u['ar'] for u in cands]} for {len(twins)} outlines; not bound")
    used = Counter(id(u) for us in bound.values() for u in us)
    twice = [u["ar"] for u in units if used[id(u)] > 1]
    if twice:
        raise SystemExit(f"egypt_census: 2006 units on two outlines: {twice}")
    for u in units:
        if not used[id(u)]:
            report.append(f"  2006 unit {u['ar']} ({u['gov']}, {u['t']}) on no outline")
    return bound


def named(unit: dict[str, Any], cp_units: dict[str, dict[str, Any]],
          numbered: set[int | None] = frozenset()) -> list[dict[str, Any]]:
    """Today's units of a 2006 unit's name: the same, its numbered parts (but
    not a number another 2006 unit of the name already had: 2006's '10th of
    Ramadan' is today's first kism, its second was 2006's too), or the same
    name of another kind -- in its governorate; else the same name and kind in
    the one governorate that has it (a markaz moved from Qena to Luxor)."""
    kind, ordinal, base = unit["key"]
    pool = [c for c in cp_units.values() if c["gov"] == unit["gov"]]
    same = [c for c in pool if unit["key"] in keys(c["ar"])]
    if same:
        return same
    if ordinal is None:
        parts = [c for c in pool if any(k[0] == kind and k[2] == base and k[1]
                                        and k[1] not in numbered for k in keys(c["ar"]))]
        if parts:
            return parts
    loose = [c for c in pool if any(k[2] == base and k[1] == ordinal for k in keys(c["ar"]))]
    if loose:
        return loose
    moved = [c for c in cp_units.values() if unit["key"] in keys(c["ar"])]
    return moved if len({c["gov"] for c in moved}) == 1 else []


def factor(gov: str, cp_govs: dict[str, dict[str, Any]], provinces: dict[str, dict[str, int]]
           ) -> float:
    """The governorate's 2006 count in CAPMAS's later tables against OCHA's,
    where the two differ by less than ``SCALE_LIMIT``; else 1."""
    k = (cp_govs[gov]["p2006"] or 0) / provinces[gov]["t"] if gov in provinces else 1.0
    return k if abs(k - 1) <= SCALE_LIMIT else 1.0


def same_ground(t2006: int | None, parts: list[dict[str, Any]], k: float,
                plain: float = PLAIN, scaled: float = SCALED) -> tuple[bool, float] | None:
    if not t2006 or not parts or any(c["p2006"] is None for c in parts):
        return None
    r = sum(c["p2006"] for c in parts) / t2006
    return (abs(r - 1) <= plain or abs(r / k - 1) <= scaled), r


def carve(t2006: int, parts: list[dict[str, Any]], free: list[dict[str, Any]], k: float
          ) -> list[dict[str, Any]]:
    """The one or two units of other names that, with ``parts``, make the 2006
    unit's count to within ``SEARCH``; the closest; none if none does."""
    for n in (1, 2):
        best = None
        for extra in itertools.combinations(free, n):
            test = same_ground(t2006, parts + list(extra), k, SEARCH, SEARCH)
            if test and test[0]:
                err = abs(test[1] / k - 1)
                if best is None or err < best[0]:
                    best = (err, list(extra))
        if best:
            return best[1]
    return []


def compose(bound: dict[str, list[dict[str, Any]]], cp: dict[str, Any],
            provinces: dict[str, dict[str, int]], report: list[str],
            every: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Outline id -> {"parts": today's units, "same": the ground test, "ratio"}."""
    out: dict[str, dict[str, Any]] = {}
    claimed: Counter = Counter()
    plans = {}
    for sid, units in bound.items():
        parts = []
        for u in units:
            numbered = {v["key"][1] for v in every if v is not u and v["gov"] == u["gov"]
                        and v["key"][0] == u["key"][0] and v["key"][2] == u["key"][2]}
            parts += [c for c in named(u, cp["units"], numbered) if c not in parts]
        plans[sid] = parts
        claimed.update(c["code"] for c in parts)
    taken: set[str] = set()
    for sid in sorted(bound):
        units, parts = bound[sid], plans[sid]
        gov = units[0]["gov"]
        t2006 = sum(u["t"] for u in units) if all(u["t"] for u in units) else None
        k = factor(gov, cp["govs"], provinces)
        test = same_ground(t2006, parts, k)
        how = ""
        if test and not test[0] and test[1] < 1:
            free = [c for c in cp["units"].values() if c["gov"] == gov and not claimed[c["code"]]
                    and c["code"] not in taken and c["p2006"] and c["code"] not in CLAIMED]
            extra = carve(t2006, parts, free, k)
            if extra:
                parts = parts + extra
                taken.update(c["code"] for c in extra)
                test = same_ground(t2006, parts, k)
                how = f"; with {[c['name'] for c in extra]}, made from it since"
        out[sid] = {"parts": parts, "same": bool(test and test[0]),
                    "ratio": test[1] if test else None, "t2006": t2006}
        report.append(f"    {units[0]['ar']} ({t2006}) -> {[c['name'] for c in parts]} "
                      f"2006 {[c['p2006'] for c in parts]}"
                      f"{'' if test is None else f' ratio {test[1]:.3f}'}"
                      f" {'SAME' if test and test[0] else 'redrawn'}{how}")
    return out


# --------------------------------------------------------------- records

def kind_word(unit: dict[str, Any]) -> str:
    return {"kism": "kism", "markaz": "markaz", "police": "police district",
            "city": "new city"}.get(unit["key"][0], "district")


def describe(units: list[dict[str, Any]]) -> str:
    return " and ".join(f"the {kind_word(u)} of {u['display']}" for u in units)


def notes_2017(parts: list[dict[str, Any]], pyr: list[tuple[int, int | None, int, int]]
               ) -> dict[str, Any]:
    men, women = sum(p[2] for p in pyr), sum(p[3] for p in pyr)
    groups = [(lo, hi, m + f) for lo, hi, m, f in pyr]
    median = grouped_median(groups)
    ratio = round(1000 * men / women)
    out = {"sex_ratio": measure(ratio, unit="males_per_1000_females", year=2017,
                                source=SOURCE_2017),
           "sex_ratio_note": f"Men per 1,000 women at the 2017 census: {men:,} men and "
                             f"{women:,} women."}
    if ratio >= INSTITUTIONS and men + women >= 1000:
        out["sex_ratio_note"] += (" The census counts the people who live in barracks, "
                                  "camps and prisons where they are, and a share of men "
                                  "this high usually comes from such places.")
    if median is not None:
        out["median_age"] = measure(median, unit="years", year=2017, source=SOURCE_2017)
        out["median_age_note"] = ("Interpolated within the ten-year age group that holds the "
                                  "middle person, from the 2017 census's count of everyone by "
                                  "sex and ten-year age group.")
    return out


def outline_record(shape: dict[str, Any], units: list[dict[str, Any]], plan: dict[str, Any],
                   pyramids: dict[str, list], hdx_url: str, hdx_licence: str) -> dict[str, Any]:
    parts = plan["parts"]
    fields: dict[str, Any] = {"sources": []}
    what = describe(units)
    pyr = [pyramids.get(c["code"]) for c in parts]
    have_now = plan["same"] and parts and all(c["p2017"] for c in parts)
    if have_now:
        p2017 = sum(c["p2017"] for c in parts)
        since = ""
        if len(parts) > 1:
            since = (f" CAPMAS counts that ground today as {len(parts)} units ("
                     f"{', '.join(clean(c['name']) for c in parts)}), added together here.")
        if all(c["p2023"] for c in parts):
            fields["population"] = measure(sum(c["p2023"] for c in parts), year=2023,
                                           source=SOURCE_2023)
            fields["population_note"] = (f"CAPMAS's estimate for 1 July 2023 of {what} as "
                                         f"drawn in 2006; the 2017 census counted "
                                         f"{p2017:,}.{since}")
        else:
            fields["population"] = measure(p2017, year=2017, source=SOURCE_2017)
            fields["population_note"] = f"The 2017 census count of {what} as drawn in 2006.{since}"
        fields["sources"].append({"field": "population", "name": CP_NAME,
                                  "url": BASE + urllib.parse.quote(parts[0]["href"]),
                                  "year": 2023, "license": CP_LICENCE})
        if all(pyr) and all(abs(sum(m + f for _, _, m, f in p) - c["p2017"]) <= 5
                            for p, c in zip(pyr, parts)):
            fields.update(notes_2017(parts, add(pyr)))
            fields["sources"].append({"field": "median_age/sex_ratio", "name": CP_NAME,
                                      "url": BASE + urllib.parse.quote(parts[0]["href"]),
                                      "year": 2017, "license": CP_LICENCE})
            return fields
        fields["median_age"] = gap(NOT_AVAILABLE, (
            "The 2017 census's count by age is not tabulated for this ground, and the 2006 "
            "census's tables by kism and markaz give no ages."))
    else:
        m = sum(u["m"] for u in units) if all(u["m"] is not None for u in units) else None
        f = sum(u["f"] for u in units) if all(u["f"] is not None for u in units) else None
        if m is None or f is None:
            return fields
        fields["population"] = measure(m + f, year=2006, source=SOURCE_2006)
        later = (f" CAPMAS's later counts are of {', '.join(clean(c['name']) for c in parts)} "
                 "as redrawn since, which do not follow this outline." if parts else
                 " CAPMAS's later tables have no unit of this ground.")
        fields["population_note"] = (f"The 2006 census count of {what} as drawn then: "
                                     f"{m:,} men and {f:,} women.{later}")
        fields["median_age"] = gap(NOT_AVAILABLE, (
            "The 2006 census's tables by kism and markaz give no ages, and the 2017 census's "
            "ages are of the units as redrawn since, which do not follow this outline."))
        fields["sources"].append({"field": "population", "name": "OCHA (HDX), after CAPMAS",
                                  "url": hdx_url, "year": 2006, "license": hdx_licence})
    # Men per 1,000 women from 2006, where 2017's cannot be used.
    m = sum(u["m"] for u in units) if all(u["m"] is not None for u in units) else None
    f = sum(u["f"] for u in units) if all(u["f"] is not None for u in units) else None
    if m and f:
        fields["sex_ratio"] = measure(round(1000 * m / f), unit="males_per_1000_females",
                                      year=2006, source=SOURCE_2006)
        fields["sex_ratio_note"] = (f"Men per 1,000 women at the 2006 census in {what} as "
                                    f"drawn then: {m:,} men and {f:,} women.")
        fields["sources"].append({"field": "sex_ratio", "name": "OCHA (HDX), after CAPMAS",
                                  "url": hdx_url, "year": 2006, "license": hdx_licence})
    return fields


ZEMAM_NOTE = ("This is land outside the zimam -- the bounds of the governorate's towns and "
              "villages -- which no table of Egypt's census counts as a kism, markaz or police "
              "district, so no count is published for it.")
PORT_NOTE = "Egypt's census tables list this port police district with no population."


def build(cp: dict[str, Any], districts: list[dict[str, Any]],
          provinces: dict[str, dict[str, int]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], pages: dict[str, str], hdx_url: str,
          hdx_licence: str) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    by_iso = {s.get("iso_3166_2"): s for s in admin1 if s.get("iso_3166_2")}
    by_label = {s["name"]: s for s in admin1}
    gov_shape = {}
    for gov, iso in GOV_ISO.items():
        shape = by_iso.get(iso) or by_label.get(UNCODED.get(iso, ""))
        if shape is None:
            raise SystemExit(f"egypt_census: no outline for governorate {gov} ({iso})")
        gov_shape[gov] = shape
    gov_of_parent = {s["id"]: g for g, s in gov_shape.items()}
    gov_of = {s["id"]: gov_of_parent[s["parent"]] for s in admin2}
    units = units_2006(districts)
    for u in units:
        u["display"] = display(u, cp["units"])
    bound = bind_outlines(admin2, gov_of, units, report)
    plans = compose(bound, cp, provinces, report, units)
    pyramids = {code: parse_pyramid(html) for code, html in pages.items()}
    records = []
    for s in admin2:
        label = latin(s["name"])
        rid = f"EGY-CAPMAS-{s['id']}"
        if label == ZEMAM:
            records.append(record(rid, s["name"], level="admin2", parent="EGY", country="EGY",
                                  match_by="shape_id", shape_id=s["id"],
                                  population=gap(NOT_AVAILABLE, ZEMAM_NOTE),
                                  median_age=gap(NOT_AVAILABLE, ZEMAM_NOTE),
                                  sex_ratio=gap(NOT_AVAILABLE, ZEMAM_NOTE)))
            continue
        if s["id"] not in bound:
            continue
        us = bound[s["id"]]
        if all(u["key"][0] == "police" and u["t"] is None for u in us):
            records.append(record(rid, s["name"], level="admin2", parent="EGY", country="EGY",
                                  match_by="shape_id", shape_id=s["id"],
                                  population=gap(NOT_AVAILABLE, PORT_NOTE),
                                  median_age=gap(NOT_AVAILABLE, PORT_NOTE),
                                  sex_ratio=gap(NOT_AVAILABLE, PORT_NOTE)))
            continue
        plan = plans[s["id"]]
        if all(u["t"] == 0 for u in us) and not any(c["p2017"] for c in plan["parts"]):
            # OCHA's 2006 table counts no one here (New Tushka) and nothing
            # counts the unit since: no figure, and no count of 0 either.
            other = [c["p2006"] for c in plan["parts"] if c["p2006"]]
            later = (f", where CAPMAS's later tables put {sum(other):,} people in 2006"
                     if other else "")
            none = (f"The 2006 census, as OCHA publishes it, counts no one in {describe(us)}"
                    f"{later}, and CAPMAS gives it no count since.")
            records.append(record(rid, s["name"], level="admin2", parent="EGY", country="EGY",
                                  match_by="shape_id", shape_id=s["id"],
                                  population=gap(NOT_AVAILABLE, none),
                                  median_age=gap(NOT_AVAILABLE, none),
                                  sex_ratio=gap(NOT_AVAILABLE, none)))
            continue
        if len(plan["parts"]) == 1 and plan["parts"][0]["p2017"] == 0 and not plan["t2006"]:
            empty = (f"The 2017 census counted no one in {describe(us)}, a city then still "
                     "being built, and CAPMAS gives it no estimate since.")
            records.append(record(rid, s["name"], level="admin2", parent="EGY", country="EGY",
                                  match_by="shape_id", shape_id=s["id"],
                                  population=gap(NOT_AVAILABLE, empty),
                                  median_age=gap(NOT_AVAILABLE, empty),
                                  sex_ratio=gap(NOT_AVAILABLE, empty)))
            continue
        if not plan["same"] and plan["t2006"] is None:
            # No 2006 count to test today's units against: a unit named
            # alike, alone, is taken as the same ground (new cities, mostly).
            if len(plan["parts"]) == 1 and all(c["p2017"] for c in plan["parts"]):
                plan = {**plan, "same": True}
                report.append(f"  {s['name']!r}: no 2006 count; bound to "
                              f"{plan['parts'][0]['name']} by name")
        fields = outline_record(s, us, plan, pyramids, hdx_url, hdx_licence)
        if not fields.get("population"):
            report.append(f"  {s['name']!r}: nothing to write")
            continue
        records.append(record(rid, s["name"], level="admin2", parent="EGY", country="EGY",
                              match_by="shape_id", shape_id=s["id"],
                              codes={"capmas_2006": [c for u in us for c in u["codes"]],
                                     "capmas": [c["code"] for c in plan["parts"]]},
                              **fields))
    records += governorates(cp, gov_shape, pyramids, report)
    return records, report


def display(unit: dict[str, Any], cp_units: dict[str, dict[str, Any]]) -> str:
    """A 2006 unit's name as CAPMAS's table today writes it, else OCHA's label."""
    for c in cp_units.values():
        if c["gov"] == unit["gov"] and unit["key"] in keys(c["ar"]):
            return clean(c["name"])
    return sorted(r["en"] for r in unit["rows"])[0]


def governorates(cp: dict[str, Any], gov_shape: dict[str, dict[str, Any]],
                 pyramids: dict[str, list], report: list[str]) -> list[dict[str, Any]]:
    out = []
    for gov, row in sorted(cp["govs"].items()):
        shape = gov_shape[gov]
        pyr = pyramids.get(gov)
        claimed = [cp["units"][c] for c in CLAIMED if c in cp["units"] and
                   cp["units"][c]["gov"] == gov]
        less = ""
        p2023, p2017 = row["p2023"], row["p2017"]
        if claimed:
            p2023 -= sum(c["p2023"] or 0 for c in claimed)
            p2017 -= sum(c["p2017"] or 0 for c in claimed)
            cpyr = [pyramids.get(c["code"]) for c in claimed]
            if pyr and all(cpyr):
                pyr = add([pyr] + cpyr, [1] + [-1] * len(cpyr))
            else:
                pyr = None
            less = " " + " ".join(
                f"It leaves out the kism of {clean(c['name'])} ({c['p2023']:,} people in "
                "2023), in the triangle north of the 22nd parallel that Egypt and Sudan both "
                "claim." for c in claimed)
        aswan = (" Egypt's count does not include Bir Tawil, the uninhabited land south of the "
                 "22nd parallel that neither Egypt nor Sudan claims." if gov == "28" else "")
        fields: dict[str, Any] = {
            "population": measure(p2023, year=2023, source=SOURCE_2023),
            "population_note": (f"CAPMAS's estimate for 1 July 2023; the 2017 census counted "
                                f"{p2017:,}.{less}{aswan}"),
            "sources": [{"field": "population", "name": CP_NAME,
                         "url": BASE + urllib.parse.quote(row["href"]), "year": 2023,
                         "license": CP_LICENCE}]}
        if pyr and abs(sum(m + f for _, _, m, f in pyr) - p2017) <= 5:
            fields.update(notes_2017([], pyr))
            if less:
                fields["sex_ratio_note"] += less
                fields["median_age_note"] += less
            fields["sources"].append({"field": "median_age/sex_ratio", "name": CP_NAME,
                                      "url": BASE + urllib.parse.quote(row["href"]),
                                      "year": 2017, "license": CP_LICENCE})
        else:
            report.append(f"  governorate {row['name']}: no 2017 ages")
        out.append(record(f"EGY-CAPMAS-{gov}", shape["name"], level="admin1", parent="EGY",
                          country="EGY", match_by="shape_id", shape_id=shape["id"],
                          codes={"capmas": gov}, **fields))
    return out


# ------------------------------------------------------------------ main

def fetch_pages(codes: list[str], hrefs: dict[str, str]) -> dict[str, str]:
    pages = {}
    for n, code in enumerate(codes, 1):
        url = BASE + urllib.parse.quote(hrefs[code])
        try:
            pages[code] = http_get(url, timeout=60)
        except Exception as exc:                    # noqa: BLE001 -- logged, unit skipped
            log(f"  page of {code} not read: {exc}")
            continue
        if n % 50 == 0:
            log(f"  {n} of {len(codes)} pages read")
        time.sleep(PAUSE)
    return pages


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl                                 # noqa: PLC0415
    package = uscb.package(HDX_DATASET)
    found = [r for r in package.get("resources", [])
             if str(r.get("name", "")).lower().endswith(".xlsx") and "2006" in str(r.get("name"))]
    if len(found) != 1:
        raise SystemExit(f"egypt_census: {len(found)} 2006 workbooks on HDX")
    hdx_licence = f"HDX licence: {package.get('license_title') or 'not stated'}"
    blob = http_get(found[0]["url"], binary=True, cache=False, timeout=120)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    districts, provinces = read_hdx(book)
    log(f"  2006: {len(districts)} rows, {len(provinces)} governorates, "
        f"{sum(p['t'] for p in provinces.values()):,} people; licence {hdx_licence!r}")
    html = http_get(URL, cache=False, timeout=120)
    cp = parse_admin(html)
    log(f"  citypopulation: {len(cp['govs'])} governorates, {len(cp['units'])} units")
    if len(cp["govs"]) != 27:
        raise SystemExit("egypt_census: the table does not hold 27 governorates")
    for gov, row in cp["govs"].items():
        made = sum(u["p2017"] or 0 for u in cp["units"].values() if u["gov"] == gov)
        if made != row["p2017"]:
            log(f"  governorate {row['name']}: its units make {made:,} in 2017 against "
                f"{row['p2017']:,}")
    admin1 = json.loads((SITE / "admin1" / "EGY.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "EGY.units.json").read_text())
    # First pass without pages, to know which units' pages are wanted.
    records, report = build(cp, districts, provinces, admin1, admin2, {},
                            uscb.dataset_url(HDX_DATASET), hdx_licence)
    wanted = sorted({c for r in records if r["level"] == "admin2"
                     and (r.get("population") or {}).get("year") in (2017, 2023)
                     for c in r["codes"]["capmas"]} | set(cp["govs"]) | CLAIMED)
    hrefs = {**{c: u["href"] for c, u in cp["units"].items()},
             **{g: r["href"] for g, r in cp["govs"].items()}}
    pages = fetch_pages([c for c in wanted if hrefs.get(c)], hrefs)
    log(f"  {len(pages)} pages read for the 2017 ages")
    records, report = build(cp, districts, provinces, admin1, admin2, pages,
                            uscb.dataset_url(HDX_DATASET), hdx_licence)
    for line in report:
        log(line)
    a2 = [r for r in records if r["level"] == "admin2"]
    log(f"  {sum(r['level'] == 'admin1' for r in records)} governorates; {len(a2)} of "
        f"{len(admin2)} outlines: "
        f"{Counter((r.get('population') or {}).get('year') for r in a2)} by year of the count; "
        f"{sum(bool((r.get('median_age') or {}).get('value')) for r in a2)} with a median")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
