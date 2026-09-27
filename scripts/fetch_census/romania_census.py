#!/usr/bin/env python3
"""Romania: the 2021 census for every county and UAT, from INS's own tables.

The National Institute of Statistics published the definitive results of the
2021 Population and Housing Census (RPL 2021) as workbooks on
recensamantromania.ro, several of them by county and by UAT (every municipiu,
oraș and comună, and Bucharest's six sectors):

* Tabel 1.03.2 -- resident population by five-year age group;
* Tabel 1.22   -- resident population by sex, for every UAT and locality;
* Tabel 2.02.2 -- by ethnicity; 2.03.2 -- by mother tongue; 2.04.2 -- by religion;
* Tabel 1.04   -- the country by single year of age (a check on the median).

**Read from the Internet Archive.** Every Romanian host is unreachable from the
runner (see ``romania.py``: insse.ro answers "Network is unreachable",
recensamantromania.ro times out). The Archive holds the office's own workbooks
byte for byte, captured in May-July 2023; each is fetched raw (``id_``) at a
named capture, so the run is repeatable.

**Suppressed cells.** INS prints ``*`` (``**`` in one table) for a cell it
withholds for disclosure control -- a small count, and cells beside it so the
small one cannot be worked out -- and ``-`` for zero. The people a row's
stars hide are exactly its total less its printed cells; they are kept as one
bar, "Suppressed (disclosure control)", never read as zero or spread over the
answers. A row with no star must add up exactly, and no row may add up to
more than its total.

**Median age** is interpolated within the five-year group that holds the
middle person: INS publishes nothing finer by UAT. The country's median from
the same groups is checked against the one from Tabel 1.04's single years.
**Sex ratio** is males per 1,000 females, from Tabel 1.22.

**Binding.** A UAT is matched to the map's polygon by name within its county,
with the office's prefixes (MUNICIPIUL, ORAȘ) and diacritics folded away and
â/î read both ways. The boundary file draws some UATs as several polygons of
one name (exclaves); the figures go on the largest (by extent), and the rest
are listed for a merge in make_redrawn. Anything left over on either side is
reported and left out.

Usage:
    python -m scripts.fetch_census.romania_census
"""

from __future__ import annotations

import argparse
import io
import re
import unicodedata
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .balkans_common import age_fields, check_sum, grouped_median, shapes
from .redatam import median_age

OUT = "romania_census.json"
YEAR = 2021
SITE = "https://www.recensamantromania.ro/wp-content/uploads"
FILES = {
    "age": (f"{SITE}/2023/05/Tabel-1.03_1.3.1-si-1.03.2.xls", "20230601175321", 1),
    "sex": (f"{SITE}/2023/05/Tabel-1.22.xlsx", "20230601175318", 0),
    "ethnicity": (f"{SITE}/2023/06/Tabel-2.02.1-si-Tabel-2.02.2.xlsx", "20230702045135", 1),
    "language": (f"{SITE}/2023/06/Tabel-2.03.1-si-Tabel-2.03.2.xlsx", "20230701100337", 1),
    "religion": (f"{SITE}/2023/06/Tabel-2.04.1-si-Tabel-2.04.2.xlsx", "20230701100330", 1),
    "single": (f"{SITE}/2023/05/Tabel-1.04.xls", "20230606002135", 0),
}
TABLE_NAMES = {"age": "Tabel 1.03.2", "sex": "Tabel 1.22", "ethnicity": "Tabel 2.02.2",
               "language": "Tabel 2.03.2", "religion": "Tabel 2.04.2", "single": "Tabel 1.04"}
PAGE = "https://www.recensamantromania.ro/rezultate-rpl-2021/rezultate-definitive/"
SOURCE = ("Institutul Național de Statistică, Recensământul Populației și Locuințelor 2021, "
          "rezultate definitive, {table}")
LICENCE = "Official statistics of Romania (reuse with attribution)"

# The header of each composition column, folded, to the map's label: matched
# on the start of the folded header, longest key first, so "ortodoxa sarba"
# is not read as "ortodoxa".
LABELS: dict[str, dict[str, str]] = {
    "ethnicity": {
        "romani": "Romanian", "maghiari": "Hungarian", "romi": "Roma", "ucraineni": "Ukrainian",
        "germani": "German", "turci": "Turkish", "rusi-lipoveni": "Lipovan Russian",
        "rusilipoveni": "Lipovan Russian", "tatari": "Tatar", "sarbi": "Serbian",
        "slovaci": "Slovak", "bulgari": "Bulgarian", "croati": "Croatian", "greci": "Greek",
        "italieni": "Italian", "evrei": "Jewish", "cehi": "Czech", "polonezi": "Polish",
        "ruteni": "Rusyn", "armeni": "Armenian", "albanezi": "Albanian",
        "macedoneni": "Macedonian", "ceangai": "Csango", "chinezi": "Chinese",
        "alta etnie": "Other", "informatie nedisponibila": "Not stated",
    },
    "language": {
        "romana": "Romanian", "maghiara": "Hungarian", "romani": "Romani",
        "ucraineana": "Ukrainian", "germana": "German", "turca": "Turkish", "rusa": "Russian",
        "tatara": "Tatar", "sarba": "Serbian", "slovaca": "Slovak", "bulgara": "Bulgarian",
        "croata": "Croatian", "italiana": "Italian", "greaca": "Greek", "ceha": "Czech",
        "polona": "Polish", "ruteana": "Rusyn", "armeana": "Armenian", "albaneza": "Albanian",
        "macedoneana": "Macedonian", "idis": "Yiddish", "alta limba": "Other",
        "informatie nedisponibila": "Not stated",
    },
    "religion": {
        "ortodoxa sarba": "Serbian Orthodox", "ortodoxa ucraineana": "Ukrainian Orthodox",
        "ortodoxa": "Orthodox", "romano-catolica": "Roman Catholic",
        "romanocatolica": "Roman Catholic", "reformata": "Reformed",
        "penticostala": "Pentecostal", "greco-catolica": "Greek Catholic",
        "grecocatolica": "Greek Catholic", "baptista": "Baptist",
        "adventista": "Seventh-day Adventist", "musulmana": "Islam", "unitariana": "Unitarian",
        "martorii lui iehova": "Jehovah's Witnesses",
        "crestina dupa evanghelie": "Christian Evangelical",
        "crestina de rit vechi": "Old Believer",
        "evanghelica lutherana": "Evangelical Lutheran",
        "evanghelica de confesiune augustana": "Evangelical Church of the Augsburg Confession",
        "evanghelica c.a": "Evangelical Church of the Augsburg Confession",
        "evanghelica": "Evangelical", "mozaica": "Judaism", "armeana": "Armenian Apostolic",
        "alta religie": "Other religion", "fara religie": "No religion", "atei": "Atheism",
        "ateu": "Atheism", "agnostic": "Agnosticism",
        "informatie nedisponibila": "Not stated",
    },
}
NOTES = {
    "ethnicity": ("Ethnicity (etnie), 2021 census, resident population, free declaration and "
                  "optional. 'Not stated' is the census's 'information not available' -- people "
                  "who declined or were counted from administrative sources, over a tenth of "
                  "Romania. Cells INS suppressed for disclosure control (printed *) are one bar, "
                  "'Suppressed (disclosure control)': their people are counted, their groups not published."),
    "language": ("Mother tongue (limba maternă), 2021 census, resident population, optional. "
                 "'Not stated' is the census's 'information not available'. Cells INS "
                 "suppressed (printed *) are one bar, 'Suppressed (disclosure control)'."),
    "religion": ("Religion (religia), 2021 census, resident population, optional: each "
                 "denomination as the census names it. 'Not stated' is the census's "
                 "'information not available'. Cells INS suppressed (printed *) are one bar, "
                 "'Suppressed (disclosure control)'."),
}
MEDIAN_NOTE = ("Interpolated within the five-year age group that holds the middle person, from "
               "the census's resident population by age group ({table}): INS publishes nothing "
               "finer by {level}.")

# The boundary file's spelling where it differs by more than diacritics, or
# names a UAT by an older name.
ALIASES = {
    ("ALBA", "RIMETEA"): "RAMETEA",
}
COUNTY_FLOOR = 150_000
# Romania's resident population on 1 December 2021, as every table prints it.
NATIONAL = 19_053_815


def fold(text: Any, i_hat: bool = False) -> str:
    """Upper-case-insensitive, diacritics off; â/î as 'i' when asked."""
    text = str(text or "").strip()
    if i_hat:
        text = re.sub("[âîÂÎ]", "i", text)
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text.lower() if c.isalnum() and not unicodedata.combining(c))


def bare(name: str) -> str:
    """A UAT's name without the office's prefix."""
    return re.sub(r"^(MUNICIPIUL|ORA[ȘSŞ]|COMUNA|SECTORUL|SECTOR)\s+", "", str(name).strip(),
                  flags=re.I)


def fetch(what: str) -> bytes:
    url, stamp, _ = FILES[what]
    blob = http_get(f"https://web.archive.org/web/{stamp}id_/{url}", binary=True, timeout=300)
    if blob[:15].lstrip().lower().startswith((b"<!doctype", b"<html")):
        raise SystemExit(f"romania_census: {url} played back as HTML, not the workbook")
    log(f"  {url.rsplit('/', 1)[-1]}: {len(blob):,} bytes, Archive capture {stamp[:8]}")
    return blob


def sheet(what: str) -> list[list[Any]]:
    blob = fetch(what)
    index = FILES[what][2]
    if blob[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        ws = wb.worksheets[index]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    import xlrd
    sh = xlrd.open_workbook(file_contents=blob).sheet_by_index(index)
    return [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]


def number(cell: Any) -> float | None:
    """A count; None for INS's suppressed '*'; 0 for its '-'."""
    if cell is None:
        return 0.0
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).strip()
    if text and set(text) == {"*"}:          # "*" and, in Tabel 2.03.2, "**"
        return None
    if text in ("", "-", "–", "—"):
        return 0.0
    try:
        return float(text.replace(" ", "").replace(",", ""))
    except ValueError:
        raise SystemExit(f"romania_census: cannot read {cell!r} as a count")


def text(cell: Any) -> str:
    return " ".join(str(cell or "").split())


def label_for(field: str, header: str) -> str:
    key = fold(header)
    spaced = " ".join(re.sub(r"[^a-z\- .]", " ", unicodedata.normalize("NFKD", header.lower())
                             .encode("ascii", "ignore").decode()).split())
    for prefix in sorted(LABELS[field], key=len, reverse=True):
        if spaced.startswith(prefix) or key.startswith(fold(prefix)):
            return LABELS[field][prefix]
    raise SystemExit(f"romania_census: {field} column {header!r} has no entry in LABELS")


def uat_rows(rows: list[list[Any]], counties: set[str], field: str | None
             ) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Read a UAT table: (group labels, {county: {"total", "groups", "uats": [...]}}).

    The header is the row holding the column letters ("A", "1", "2", ...);
    the categories are the row above it. A row whose first cell is a county
    (and not a MUNICIPIUL of the same name, save Bucharest) and whose total is
    a county's size opens a county; every other named row is a UAT of it.
    """
    letters = next(i for i, r in enumerate(rows) if text(r[0]) == "A" and text(r[1]) in ("1", "1.0"))
    width = len(rows[letters])
    columns: list[tuple[int, str]] = []
    if field:
        head = rows[letters - 1]
        for j in range(2, width):
            label = text(head[j]) if j < len(head) else ""
            if label and text(rows[letters][j]) not in ("A", ""):
                columns.append((j, label_for(field, label)))
    else:
        head_rows = rows[max(0, letters - 2):letters]
        for j in range(2, width):
            parts = [text(r[j]) for r in head_rows if j < len(r) and text(r[j])]
            label = " ".join(parts)
            m = re.search(r"(\d+)\s*-\s*(\d+)", label)
            top = re.search(r"(\d+)\s*ani\s*[sș]i\s*peste", label)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                # INS labels 80-84 as "80 - 85"; a group is five years wide.
                columns.append((j, (float(lo), 5.0)))
                if hi - lo not in (4, 5):
                    raise SystemExit(f"romania_census: age column {label!r}")
            elif top:
                columns.append((j, (float(top.group(1)), None)))
    out: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    country: dict[str, Any] | None = None
    for r in rows[letters + 1:]:
        name = text(r[0])
        if not name or len(r) < 2 or not re.fullmatch(r"[\d.,\s]+", text(r[1]) or "x"):
            continue                 # a blank, a note, or a heading: not a unit
        total = number(r[1])
        if not total:
            continue
        groups: dict[Any, float] = defaultdict(float)
        stars = 0
        for j, label in columns:
            value = number(r[j]) if j < len(r) else 0.0
            if value is None:
                stars += 1
                continue
            groups[label] += value
        row = {"name": name, "total": total, "groups": dict(groups), "stars": stars}
        folded = fold(bare(name))
        if fold(name) in ("romania",):
            country = row
            continue
        if total >= COUNTY_FLOOR and folded in counties and (
                not name.upper().startswith("MUNICIPIUL") or folded == "bucuresti"):
            current = {**row, "uats": []}
            out[folded] = current
            continue
        if current is None:
            continue
        current["uats"].append(row)
    if country is None:
        # Tabel 1.03.2 starts at the first county; the country is its counties.
        summed: dict[Any, float] = defaultdict(float)
        for c in out.values():
            for k, v in c["groups"].items():
                summed[k] += v
        country = {"name": "ROMÂNIA (summed)", "total": sum(c["total"] for c in out.values()),
                   "groups": dict(summed), "stars": sum(c["stars"] for c in out.values())}
    out[""] = {**country, "uats": []}
    return [c[1] for c in columns], out


SHORTFALL: dict[str, float] = {}
SUPPRESSED = "Suppressed (disclosure control)"


def check_row(row: dict[str, Any], what: str) -> None:
    """The printed groups and the stars account for the printed total exactly.

    INS prints * for a small count and, to stop it being worked out from the
    total, for other cells in the same row -- Albac's ethnicity hides 89
    people under two stars, one of them the "information not available"
    column. A star's size is not published, but the stars of a row together
    hide exactly the row's total less its printed cells. So the shortfall
    must never be negative, a row with no star must have none, and what the
    stars hide is kept as one bar of its own (``SUPPRESSED``) rather than
    spread over the answers or dropped.
    """
    shown = sum(v for k, v in row["groups"].items() if k != SUPPRESSED)
    short = row["total"] - shown
    if short < -0.5 or (row["stars"] == 0 and short > 0.5):
        raise SystemExit(f"romania_census: {what} {row['name']}: the groups add to {shown:,.0f} "
                         f"against {row['total']:,.0f} with {row['stars']} suppressed cells")
    if short > 0.5:
        row["groups"][SUPPRESSED] = short
    if row["total"]:
        SHORTFALL[what] = max(SHORTFALL.get(what, 0.0), short / row["total"])


def sexes(rows: list[list[Any]], counties: set[str], order: dict[str, list[dict[str, Any]]]
          ) -> tuple[dict[tuple[str, int], tuple[float, float]], dict[str, list[list[Any]]]]:
    """({(county, UAT index): (men, women)}, Tabel 1.22's rows by county),
    aligned on 1.03.2's UATs.

    Tabel 1.22 lists each UAT followed by its localities, a locality often
    named as its UAT. The UATs are found in 1.03.2's order: the next row whose
    name and total are the UAT's.
    """
    blocks: dict[str, list[list[Any]]] = defaultdict(list)
    current = None
    for r in rows:
        if len(r) < 6:
            continue
        name = text(r[2])
        if not name or not re.fullmatch(r"[\d.,\s]+", text(r[3]) or "x"):
            continue
        total = number(r[3])
        if not text(r[0]) and not text(r[1]) and fold(bare(name)) in counties:
            current = fold(bare(name))
            continue
        if current:
            blocks[current].append(r)
    out: dict[tuple[str, int], tuple[float, float]] = {}
    for county, uats in order.items():
        if not county:
            continue
        seq = blocks.get(county, [])
        at = 0
        for i, uat in enumerate(uats):
            want = fold(bare(uat["name"]))
            while at < len(seq):
                r = seq[at]
                at += 1
                if fold(bare(text(r[2]))) == want and number(r[3]) == uat["total"]:
                    men, women = number(r[4]), number(r[5])
                    if men is None or women is None:
                        break
                    check_sum(men + women, uat["total"], f"romania_census: sexes of {uat['name']}")
                    out[(county, i)] = (men, women)
                    break
            else:
                raise SystemExit(f"romania_census: {uat['name']} ({county}) not found in Tabel 1.22")
    return out, blocks


def single_year_median(rows: list[list[Any]]) -> float | None:
    from collections import Counter
    ages: Counter = Counter()
    age = None
    for r in rows:
        head = text(r[0])
        m = re.match(r"^(Sub 1 an|(\d+) an[i]?(?: si peste)?)", head)
        if m:
            age = 0 if head.startswith("Sub") else int(m.group(2))
        if age is None or len(r) < 3:
            continue
        value = number(r[2])
        if value:
            ages[age] += value
        if "ROMANIA" not in head and head and not m and not re.match(r"^\d", head):
            break
    return median_age(ages) if ages else None


def build() -> list[dict[str, Any]]:
    admin1 = shapes("ROU", "admin1")
    admin2 = shapes("ROU", "admin2")
    counties = {fold(s["name"]): s for s in admin1}
    tables = {}
    for field in ("age", "ethnicity", "language", "religion"):
        labels, data = uat_rows(sheet(field), set(counties), None if field == "age" else field)
        # Bucharest is published as one city in these tables: its sectors are
        # not broken out (Tabel 2.02.2 repeats the city's row as its own UAT,
        # 1.03.2 prints it once). The sectors come from Tabel 1.22 below.
        if "bucuresti" in data:
            data["bucuresti"]["uats"] = []
        tables[field] = data
        found = sorted(k for k in data if k)
        if len(found) != 42:
            raise SystemExit(f"romania_census: {field}: {len(found)} counties read, "
                             f"missing {sorted(set(counties) - set(found))}")
        country = data[""]
        check_sum(sum(data[c]["total"] for c in found), country["total"],
                  f"romania_census: {field}, counties against the country")
        check_sum(country["total"], NATIONAL,
                  f"romania_census: {field}, the country against the published {NATIONAL:,}")
        for c in found:
            if c != "bucuresti":
                check_sum(sum(u["total"] for u in data[c]["uats"]), data[c]["total"],
                          f"romania_census: {field}, UATs of {c}")
            if field != "age":
                check_row(data[c], field)
                for u in data[c]["uats"]:
                    check_row(u, field)
        log(f"  {field}: {country['total']:,.0f} residents, 42 counties, "
            f"{sum(len(data[c]['uats']) for c in found):,} UATs; {len(labels)} columns"
            + (f"; the most any row's stars hide is {100 * SHORTFALL[field]:.1f}% of it"
               if field in SHORTFALL else ""))
    # The four tables list the same UATs with the same totals, in the same order.
    base = tables["age"]
    for field in ("ethnicity", "language", "religion"):
        for c in counties:
            a = [(fold(bare(u["name"])), u["total"]) for u in base[c]["uats"]]
            b = [(fold(bare(u["name"])), u["total"]) for u in tables[field][c]["uats"]]
            if a != b:
                diff = [x for x, y in zip(a, b) if x != y][:3]
                raise SystemExit(f"romania_census: {field} lists {c}'s UATs differently: {diff}")
    sex, sex_rows = sexes(sheet("sex"), set(counties), {c: base[c]["uats"] for c in base})
    groups = [(lo, w, n) for (lo, w), n in base[""]["groups"].items()]
    national = grouped_median(groups)
    single = single_year_median(sheet("single"))
    log(f"  country median: {national} from five-year groups, {single} from single years")
    if single is None or abs(national - single) > 0.3:
        raise SystemExit(f"romania_census: the grouped national median {national} is not within "
                         f"0.3 years of the single-year {single}")

    # Bind: county by name; UAT by bare name within its county.
    by_county: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in admin2:
        parent = next((k for k, v in counties.items() if v["id"] == s["parent"]), None)
        if parent:
            by_county[parent].append(s)

    def area(s: dict[str, Any]) -> float:
        b = s.get("bbox") or [0, 0, 0, 0]
        return (b[2] - b[0]) * (b[3] - b[1])

    records: list[dict[str, Any]] = []
    left_units: list[str] = []
    parts_listed: list[str] = []
    used: set[str] = set()
    for county, shape1 in sorted(counties.items()):
        polys = by_county[county]
        keys = [defaultdict(list), defaultdict(list)]
        for s in polys:
            keys[0][fold(bare(s["name"]))].append(s)
            keys[1][fold(bare(s["name"]), True)].append(s)
        names = [fold(bare(u["name"])) for u in base[county]["uats"]]
        for i, uat in enumerate(base[county]["uats"]):
            name = bare(uat["name"])
            alias = ALIASES.get((shape1["name"], fold(name).upper()), None)
            if names.count(fold(name)) > 1:
                left_units.append(f"{uat['name']} ({county}): two UATs of this name")
                continue
            hits = []
            for k, table in enumerate(keys):
                hits = table.get(fold(alias or name, bool(k)), [])
                if hits:
                    break
            hits = [h for h in hits if h["id"] not in used]
            if not hits:
                left_units.append(f"{uat['name']} ({shape1['name']})")
                continue
            main = max(hits, key=area)
            if len(hits) > 1:
                parts_listed.append(f"{shape1['name']} {main['name']}: keep {main['id']}, merge "
                                    + ", ".join(h["id"] for h in hits if h is not main))
            for h in hits:
                used.add(h["id"])
            fields: dict[str, Any] = {
                "population": measure(int(uat["total"]), year=YEAR,
                                      source=SOURCE.format(table=TABLE_NAMES["age"])),
            }
            men, women = sex.get((county, i), (None, None))
            grouped = [(lo, w, n) for (lo, w), n in uat["groups"].items()]
            fields.update(age_fields(None, men or 0, women or 0, year=YEAR,
                                     source=SOURCE.format(table=TABLE_NAMES["age"]),
                                     note=MEDIAN_NOTE.format(table=TABLE_NAMES["age"], level="UAT"),
                                     grouped=grouped))
            if men is None:
                fields.pop("sex_ratio", None)
            elif "sex_ratio" in fields:
                fields["sex_ratio"]["source"] = SOURCE.format(table=TABLE_NAMES["sex"])
            cite = [{"field": "population/median_age", "name": SOURCE.format(table=TABLE_NAMES["age"]),
                     "url": FILES["age"][0], "archive": FILES["age"][1], "page": PAGE, "year": YEAR,
                     "license": LICENCE},
                    {"field": "sex_ratio", "name": SOURCE.format(table=TABLE_NAMES["sex"]),
                     "url": FILES["sex"][0], "archive": FILES["sex"][1], "page": PAGE, "year": YEAR,
                     "license": LICENCE}]
            for field in ("ethnicity", "language", "religion"):
                row = tables[field][county]["uats"][i]
                fields[field] = shares({k: v for k, v in row["groups"].items() if v}, total=row["total"])
                fields[f"{field}_year"] = YEAR
                fields[f"{field}_note"] = NOTES[field]
                cite.append({"field": field, "name": SOURCE.format(table=TABLE_NAMES[field]),
                             "url": FILES[field][0], "archive": FILES[field][1], "page": PAGE,
                             "year": YEAR, "license": LICENCE})
            records.append(record(f"ROU-2021-{county}-{fold(uat['name'])}", main["name"],
                                  level="admin2", parent="ROU", country="ROU",
                                  parent_name=shape1["name"], match_by="shape_id",
                                  shape_id=main["id"], sources=cite, **fields))
        # The county itself: its compositions and head count from the same tables.
        fields = {"population": measure(int(base[county]["total"]), year=YEAR,
                                        source=SOURCE.format(table=TABLE_NAMES["age"]))}
        cite = []
        for field in ("ethnicity", "language", "religion"):
            row = tables[field][county]
            fields[field] = shares({k: v for k, v in row["groups"].items() if v}, total=row["total"])
            fields[f"{field}_year"] = YEAR
            fields[f"{field}_note"] = NOTES[field]
            cite.append({"field": field, "name": SOURCE.format(table=TABLE_NAMES[field].replace(".2", ".2 (county row)")),
                         "url": FILES[field][0], "archive": FILES[field][1], "page": PAGE,
                         "year": YEAR, "license": LICENCE})
        records.append(record(f"ROU-2021-{county}", shape1["name"], level="admin1", parent="ROU",
                              country="ROU", match_by="shape_id", shape_id=shape1["id"],
                              sources=cite, **fields))
    # Bucharest's six sectors: Tabel 1.22 counts each by sex; the tables of
    # age, ethnicity, mother tongue and religion stop at the city.
    sectors = {}
    for r in sex_rows.get("bucuresti", []):
        m = re.search(r"SECTORUL\s+(\d)", text(r[2]).upper())
        if m:
            sectors[m.group(1)] = (number(r[3]), number(r[4]), number(r[5]))
    check_sum(sum(v[0] for v in sectors.values()), base["bucuresti"]["total"],
              "romania_census: Bucharest's sectors against the city")
    whole_city = ("INS publishes Bucharest's {what} for the city as a whole in the 2021 census "
                  "tables, not by sector; the city's figure is on the county, and a sector has "
                  "none of its own.")
    for n, (total, men, women) in sorted(sectors.items()):
        shape = next((x for x in by_county["bucuresti"] if fold(bare(x["name"])) == n), None)
        if shape is None or shape["id"] in used:
            left_units.append(f"SECTORUL {n} (bucuresti)")
            continue
        used.add(shape["id"])
        check_sum(men + women, total, f"romania_census: sexes of sector {n}")
        records.append(record(
            f"ROU-2021-bucuresti-sector-{n}", shape["name"], level="admin2", parent="ROU",
            country="ROU", parent_name="BUCURESTI", match_by="shape_id", shape_id=shape["id"],
            population=measure(int(total), year=YEAR, source=SOURCE.format(table=TABLE_NAMES["sex"])),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females", year=YEAR,
                              source=SOURCE.format(table=TABLE_NAMES["sex"])),
            median_age=gap(NOT_AVAILABLE, whole_city.format(what="population by age")),
            ethnicity=gap(NOT_AVAILABLE, whole_city.format(what="ethnicity")),
            religion=gap(NOT_AVAILABLE, whole_city.format(what="religion")),
            language=gap(NOT_AVAILABLE, whole_city.format(what="mother tongue")),
            sources=[{"field": "population/sex_ratio", "name": SOURCE.format(table=TABLE_NAMES["sex"]),
                      "url": FILES["sex"][0], "archive": FILES["sex"][1], "page": PAGE,
                      "year": YEAR, "license": LICENCE}]))
    spare = [f"{s['name']} ({next(k for k, v in counties.items() if v['id'] == s['parent'])})"
             for s in admin2 if s["id"] not in used]
    log(f"  {sum(1 for r in records if r['level'] == 'admin2'):,} UATs bound; "
        f"{len(left_units)} UATs unbound: {left_units}")
    log(f"  {len(spare)} polygons with no UAT: {spare}")
    log(f"  {len(parts_listed)} UATs drawn as several polygons (figures on the largest):")
    for line in parts_listed:
        log(f"    {line}")
    if len(left_units) > 25:
        raise SystemExit("romania_census: too many UATs unbound to trust the matching")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("romania_census: RPL 2021, definitive results, through the Internet Archive")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
