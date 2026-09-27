#!/usr/bin/env python3
"""Estonia: the pre-2017 municipalities and counties the map draws, from Statistics Estonia.

**What the map draws.** Both Estonian layers predate the administrative reform
of October 2017, which merged 213 municipalities into 79 and moved several
across county lines. The counties are the old ones: Hanila and Lihula are
filed under Lääne, Avinurme and Lohusuu under Ida-Viru. Statistics Estonia
marks the change in its own codes -- every county whose territory the reform
changed got a new code (Ida-Viru 44 became 45, Tartu 78 became 79), and only
Harju (37), Hiiu (39), Saare (74) and Viljandi (84) kept theirs. The
municipalities are those of 2013-2014: the October 2013 mergers are drawn
(Hiiu, Lääne-Nigula, Viljandi, Kose), the 2014 one is not -- Kaarma and Kärla
are drawn on their own, and the polygon labelled "Lääne-Saare" covers only the
west of Saaremaa that was Lümanda.

So every figure here is for those units:

* **Population, median age, sex ratio (admin2 and admin1).** Table RV0241
  (archived: population by sex, single year of age and administrative unit on
  1 January, 2012-2017, each year in that year's units). 1 January 2017 for
  every unit that still existed then; for a unit merged away before 2017 and
  drawn on its own (Kaarma, Kärla, Lümanda), its last count. The counties'
  own rows are the old counties.
* **Ethnicity, mother tongue, religion (admin2).** The 2011 census, by the units
  of 31 December 2011: RL0429 (ethnic nationality), RL0433 (mother tongue) and
  RL0452 (religion, aged 15 and over). A drawn unit formed by the 2013 mergers
  is the sum of the 2011 units it was formed from. The 2021 census is
  tabulated by the post-reform municipalities, which the map does not draw.
  RL0429 names only the larger units and folds the rest into "other local
  governments of the county"; those get no ethnicity.
* **Ethnicity (admin1).** Statistics Estonia's register count RV0222U is by the
  new counties, and ``pxweb`` withholds the eleven that changed. For those,
  RV0222 (archived, 2012-2017, old counties) on 1 January 2017 -- the same
  register, on the drawn territory.
* **Mother tongue, religion (admin1).** For the four unchanged counties the 2021
  census (RL21434, RL21452); for the eleven changed, the 2011 census.

Binding: the boundary file's Estonian names are damaged in places ("Kohtla-
Jlrve linn", "Valgjhrve vald", and "K" and "M" cut off at the first non-ASCII
letter); ``DRAWN`` restores them, and says which it restores from location
alone. A unit is bound within its own county only, and a merged unit is never
bound where one of the units it was merged from is drawn.

Usage:
    python -m scripts.fetch_census.estonia
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import AgeSex, check_parts, load_units, parent_names, request_json, unplaced
from .pxweb import unstack

STAT = "https://andmed.stat.ee/api/v1/en/stat"
ARCHIVE = (f"{STAT}/Lepetatud_tabelid/Rahvastik.Arhiiv/"
           "Rahvastikun%C3%A4itajad%20ja%20koosseis.%20Arhiiv")
C11 = f"{STAT}/rahvaloendus/rel2011/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad"
C21 = f"{STAT}/rahvaloendus/rel2021/rahvastiku-demograafilised-ja-etno-kultuurilised-naitajad"
TABLES = {
    "RV0241": f"{ARCHIVE}/RV0241.PX",
    "RV0222": f"{ARCHIVE}/RV0222.PX",
    "RL0429": f"{C11}/rahvus-emakeel-ja-keelteoskus-murded/RL0429.PX",
    "RL0433": f"{C11}/rahvus-emakeel-ja-keelteoskus-murded/RL0433.PX",
    "RL0452": f"{C11}/usk/RL0452.PX",
    "RL21434": f"{C21}/rahvus-emakeel/RL21434.px",
    "RL21452": f"{C21}/usk/RL21452.px",
}
PAGE = "https://andmed.stat.ee/en/stat/{table}"
SOURCE = "Statistics Estonia"
OUT = PROCESSED / "estonia_municipality.json"
YEAR = 2017
CENSUS_YEAR = 2011

# Old county code -> the boundary file's name.
COUNTIES = {"37": "Harju maakond", "39": "Hiiu maakond", "44": "Ida-Viru maakond",
            "49": "Jõgeva maakond", "51": "Järva maakond", "57": "Lääne maakond",
            "59": "Lääne-Viru maakond", "65": "Põlva maakond", "67": "Pärnu maakond",
            "70": "Rapla maakond", "74": "Saare maakond", "78": "Tartu maakond",
            "82": "Valga maakond", "84": "Viljandi maakond", "86": "Võru maakond"}
# The four counties whose code the reform left alone -> their 2021 census code.
UNCHANGED = {"37": "00370000000000", "39": "00390000000000",
             "74": "00740000000000", "84": "00840000000000"}

# The boundary file's damaged or cut names -> the unit's name. Most restore a
# letter the file lost ("l" for "ä", "j" for "õ"). Four rest on location:
#   "K"   (centre 22.26E 58.32N, Saare county): Kärla, between Kaarma and
#          Kihelkonna, both drawn on their own;
#   "M"   (27.32E 59.22N, Ida-Viru): Mäetaguse;
#   "Alaj", "Kivi": Alajõe (27.49E 59.03N) and the town of Kiviõli (26.97E
#          59.35N), both cut at the "õ";
#   "Laane-Saare": a polygon spanning 21.83-22.21E, 58.19-58.36N, the west of
#          Saaremaa that was Lümanda. The Lääne-Saare formed in 2014 also took
#          in Kaarma and Kärla, which are drawn beside it, so this polygon is
#          not that parish and is not given its figures.
DRAWN = {"Alaj": "Alajõe vald", "Kivi": "Kiviõli linn", "K": "Kärla vald", "M": "Mäetaguse vald",
         "Laane-Saare": "Lümanda vald", "Tallinna linn": "Tallinn linn",
         "Kohtla-Jlrve linn": "Kohtla-Järve linn", "Kohtla-Nlmme vald": "Kohtla-Nõmme vald",
         "Narva-Jvesuu linn": "Narva-Jõesuu linn", "Raikklla vald": "Raikküla vald",
         "Valgjhrve vald": "Valgjärve vald", "Kasepem vald": "Kasepää vald",
         "Peipsinare vald": "Peipsiääre vald", "Mikitamie vald": "Mikitamäe vald",
         "Jaarva-Jaani": "Järva-Jaani vald"}

# Units discontinued between 2012 and 2017 -> the unit they merged into, as
# (name, kind). Every unit RV0241 marks as discontinued must be here, or the
# run stops rather than bind a merged unit it does not know is merged.
SUCCESSOR = {
    ("Kärdla", "linn"): ("Hiiu", "vald"), ("Kõrgessaare", "vald"): ("Hiiu", "vald"),
    ("Oru", "vald"): ("Lääne-Nigula", "vald"), ("Risti", "vald"): ("Lääne-Nigula", "vald"),
    ("Taebla", "vald"): ("Lääne-Nigula", "vald"),
    ("Paistu", "vald"): ("Viljandi", "vald"), ("Pärsti", "vald"): ("Viljandi", "vald"),
    ("Saarepeedi", "vald"): ("Viljandi", "vald"), ("Viiratsi", "vald"): ("Viljandi", "vald"),
    ("Maidla", "vald"): ("Lüganuse", "vald"), ("Püssi", "linn"): ("Lüganuse", "vald"),
    ("Kõue", "vald"): ("Kose", "vald"), ("Põlva", "linn"): ("Põlva", "vald"),
    ("Lavassaare", "vald"): ("Audru", "vald"),
    ("Kaisma", "vald"): ("Vändra", "vald"), ("Vändra", "vald"): ("Vändra", "vald"),
    ("Kaarma", "vald"): ("Lääne-Saare", "vald"), ("Kärla", "vald"): ("Lääne-Saare", "vald"),
    ("Lümanda", "vald"): ("Lääne-Saare", "vald"),
}

KIND = (("rural municipality", "vald"), ("small town", "alev"), ("city", "linn"),
        ("town", "alev"), ("vald", "vald"), ("linn", "linn"), ("alev", "alev"))
COUNTY_ROW = re.compile(r"[A-ZÕÄÖÜŠŽ\- ]+ COUNTY")


def split(name: str) -> tuple[str, str]:
    """'Keila city' / 'Keila linn' -> ('Keila', 'linn'); a bare name -> (name, '')."""
    name = name.strip().rstrip("*").strip()
    for suffix, kind in KIND:
        if name.lower().endswith(" " + suffix):
            return name[: -len(suffix)].strip(), kind
    return name, ""


def county_of(label: str) -> str | None:
    head = label[: -len(" COUNTY")]
    return next((c for c, n in COUNTIES.items() if fold(n[: -len(" maakond")]) == fold(head)),
                None)


def query(table: str, pins: dict[str, Any]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    return unstack(request_json(TABLES[table], {"query": [
        {"code": k, "selection": ({"filter": "all", "values": ["*"]} if v == "*"
                                   else {"filter": "item", "values": list(v)})}
        for k, v in pins.items()], "response": {"format": "json-stat2"}}, pause=0.5))


def meta(table: str) -> dict[str, dict[str, Any]]:
    return {v["code"]: v for v in request_json(TABLES[table], pause=0.5)["variables"]}


def units_of(values: list[str], texts: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """A place variable's municipalities, and its county rows (old code -> row code).

    The office nests places by indentation: a county in capitals, then its
    municipalities, each followed by the settlements inside it one level
    further in. RV0241 indents municipalities by two dots and settlements by
    four; the census tables leave municipalities flush and indent the
    settlements. A municipality with no type word (RV0241's "..Tallinn") is
    a city.
    """
    depths = [len(t) - len(t.lstrip(".")) for t in texts
              if re.search(r"(city|rural municipality)\*?$", t)]
    unit_depth = min(depths) if depths else 0
    out: dict[str, dict[str, Any]] = {}
    counties: dict[str, str] = {}
    county = None
    for code, text in zip(values, texts):
        bare = text.lstrip(".")
        depth = len(text) - len(bare)
        if COUNTY_ROW.fullmatch(bare):
            county = county_of(bare)
            if county:
                counties[county] = code
            continue
        if (depth != unit_depth or county is None or ":" in bare
                or "county" in bare.lower() or "_" in code):
            continue
        base, kind = split(bare)
        out[code] = {"name": bare.rstrip("*").strip(), "base": base, "kind": kind or "linn",
                     "county": county, "gone": bare.endswith("*")}
    return out, counties


def pick(candidates: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    """One office unit for a drawn polygon: by kind if given, then the one still standing."""
    if kind:
        same = [c for c in candidates if c["kind"] == kind]
        candidates = same or candidates
    if len(candidates) > 1:
        standing = [c for c in candidates if not c["gone"]]
        candidates = standing or candidates
    return candidates[0] if len(candidates) == 1 else None


ETHNIC = {"estonians": "Estonian", "russians": "Russian", "ukrainians": "Ukrainian",
          "belarusians": "Belarusian", "belorussians": "Belarusian", "finns": "Finnish",
          "tatars": "Tatar", "jews": "Jewish", "latvians": "Latvian", "lithuanians": "Lithuanian",
          "poles": "Polish", "germans": "German", "armenians": "Armenian",
          "azerbaijanis": "Azerbaijani", "other ethnic nationalities": "Other",
          "ethnic nationality unknown": "Not stated"}


def labels_ethnicity(label: str) -> str:
    bare = label.lstrip(".").strip()
    return ETHNIC.get(bare.lower(), bare)


def labels_language(label: str) -> str:
    bare = label.lstrip(".").strip()
    return {"Other mother tongue": "Other language",
            "Mother tongue unknown": "Not stated"}.get(bare, bare)


def labels_religion(label: str) -> str:
    bare = label.lstrip(".").strip()
    return {"Does not feel an affiliation to any religion": "No religion",
            "Refused to answer": "Not stated", "Religious affiliation unknown": "Not stated",
            "Religion unknown": "Not stated"}.get(bare, bare)


def composition(rows, place: str, var: str, total_code: str, skip: set[str],
                relabel) -> dict[str, dict[str, float]]:
    """{place code: {label: count}}, the total under '__total__'; categories must make it."""
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for key, value in rows:
        code, (cat, text) = key[place][0], key[var]
        if cat == total_code:
            out[code]["__total__"] += value
        elif cat not in skip:
            out[code][relabel(text)] += value
    for code, counts in out.items():
        parts = sum(v for k, v in counts.items() if k != "__total__")
        if abs(parts - counts["__total__"]) > 0.5:
            raise SystemExit(f"{var} at {code}: categories make {parts:,.0f} of "
                             f"{counts['__total__']:,.0f}")
    return out


WHAT = {
    "ethnicity": "Ethnic nationality as answered in the census",
    "language": "Mother tongue as answered in the census",
    "religion": ("Religious affiliation, asked of everyone aged 15 and over; 'Not stated' joins "
                 "those who refused, those whose affiliation is unknown, and those who said "
                 "they had one without saying which"),
}


def census_block(field: str, table: str, counts: dict[str, float], total: float,
                 parts: list[str], year: int) -> dict[str, Any]:
    return {
        field: shares(counts, total=total),
        f"{field}_year": year,
        f"{field}_note": (
            f"{WHAT[field]}, 31 December {year} (Statistics Estonia, {table})."
            + (f" Summed from the {year} units {', '.join(parts)}, which the drawn unit was "
               "formed from." if len(parts) > 1 else "")
            + (" The 2021 census is tabulated by the municipalities formed in 2017, which the "
               "map does not draw." if year == CENSUS_YEAR else "")),
        "sources": [{"field": field, "name": f"{SOURCE}, {table}",
                     "url": PAGE.format(table=table), "year": year}],
    }


def ethnicity_2017() -> dict[str, dict[str, float]]:
    """RV0222 on 1 January 2017 by old county: {county: {label: count, '__total__'}}."""
    rows = query("RV0222", {"Aasta": [str(YEAR)], "Sugu": ["1"], "Maakond": "*", "Rahvus": "*"})
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    children: dict[str, float] = defaultdict(float)
    for key, value in rows:
        county, (cat, text) = key["Maakond"][0], key["Rahvus"]
        if county not in COUNTIES:
            continue
        if cat == "1":
            out[county]["__total__"] += value
        elif text.startswith(".."):
            out[county][labels_ethnicity(text)] += value
            children[county] += value
        else:
            out[county][labels_ethnicity(text)] += value
    for county in out:
        # "Other ethnic nationalities" holds the ones listed beneath it.
        out[county]["Other"] -= children[county]
        parts = sum(v for k, v in out[county].items() if k != "__total__")
        if abs(parts - out[county]["__total__"]) > 0.5 or out[county]["Other"] < 0:
            raise SystemExit(f"RV0222 {county}: categories make {parts:,.0f} of "
                             f"{out[county]['__total__']:,.0f}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log("estonia: Statistics Estonia RV0241, RV0222 and the 2011 and 2021 censuses")

    # --- 1. Population by single year of age, 2012-2017, in each year's units.
    m = meta("RV0241")
    place = next(c for c in m if c.startswith("Haldus"))
    units, county_rows = units_of(m[place]["values"], m[place]["valueTexts"])
    gone = {c: u for c, u in units.items() if u["gone"]}
    log(f"  RV0241: {len(units)} municipalities, {len(gone)} discontinued by {YEAR}: "
        + ", ".join(sorted(f"{u['name']} ({u['kind']})" for u in gone.values())))
    unknown = sorted({(u["base"], u["kind"]) for u in gone.values()} - set(SUCCESSOR))
    if unknown:
        raise SystemExit(f"RV0241 marks discontinued units whose successor this adapter does "
                         f"not know: {unknown}")
    whole = next(c for c, t in zip(m[place]["values"], m[place]["valueTexts"])
                 if t == "Whole country")
    # People whose county the register does not know are in the country's
    # total and in no county's.
    nowhere = [c for c, t in zip(m[place]["values"], m[place]["valueTexts"])
               if t == "County unknown"]
    ages = [a for a in m["Vanus"]["values"] if a != "000"]
    open_top = max(ages, key=int)            # "87" is "85 and older"
    people: dict[tuple[str, str], AgeSex] = defaultdict(AgeSex)
    totals: dict[tuple[str, str], float] = {}

    def read_ages(codes: list[str], years: list[str]) -> None:
        for chunk in (codes[i:i + 90] for i in range(0, len(codes), 90)):
            for key, value in query("RV0241", {"Aasta": years, place: chunk,
                                               "Sugu": ["2", "3"], "Vanus": ["000"] + ages}):
                code, year = key[place][0], key["Aasta"][0]
                age, sex = key["Vanus"][0], key["Sugu"][0]
                if age == "000":
                    totals[(code, year)] = totals.get((code, year), 0.0) + value
                else:
                    people[(code, year)].add(85 if age == open_top else int(age),
                                             "m" if sex == "2" else "f", value)

    read_ages(sorted(units) + sorted(county_rows.values()) + [whole] + nowhere, [str(YEAR)])
    read_ages(sorted(gone), [str(y) for y in range(2012, YEAR)])
    for key, got in people.items():
        if abs(got.total - totals.get(key, -1)) > 0.5:
            raise SystemExit(f"RV0241 {key}: single years make {got.total:,.0f} against "
                             f"{totals.get(key)}")
    last = {c: max((int(y) for (cc, y), a in people.items() if cc == c and a.total > 0),
                   default=None) for c in units}
    standing = [c for c in units if last[c] == YEAR]
    check_parts({**{cc: totals[(row, str(YEAR))] for cc, row in county_rows.items()},
                 **{"unknown": totals.get((c, str(YEAR)), 0.0) for c in nowhere}},
                totals[(whole, str(YEAR))],
                f"RV0241 {YEAR}: counties and county unknown -> Estonia", 0)
    for cc, row in county_rows.items():
        check_parts({c: totals[(c, str(YEAR))] for c in standing if units[c]["county"] == cc},
                    totals[(row, str(YEAR))], f"RV0241 {YEAR}: units -> {COUNTIES[cc]}", 0)
    log(f"  Estonia 1 January {YEAR}: median age {people[(whole, str(YEAR))].median()}")

    # --- 2. Bind the drawn polygons, each within its own county.
    shapes = load_units("EST", "admin2")
    parents = parent_names("EST")
    by_base: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for code, u in units.items():
        if last[code] is not None:
            by_base[(fold(u["base"]), u["county"])].append({**u, "code": code})
    drawn_county = {s["id"]: next((c for c, n in COUNTIES.items()
                                   if n == parents.get(s["parent"])), None) for s in shapes}
    drawn_kinds: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for s in shapes:
        base, kind = split(DRAWN.get(s["name"], s["name"]))
        drawn_kinds[(fold(base), drawn_county[s["id"]])].append(kind)
    bound: dict[str, str] = {}
    left = []
    for s in shapes:
        base, kind = split(DRAWN.get(s["name"], s["name"]))
        cc = drawn_county[s["id"]]
        if not kind and "vald" in drawn_kinds[(fold(base), cc)]:
            kind = "linn"                  # "Voru" beside "Voru vald" is the town
        choice = pick(by_base.get((fold(base), cc), []), kind)
        if choice is None or choice["code"] in bound.values():
            left.append(f"{s['name']} ({parents.get(s['parent'])})")
            continue
        bound[s["id"]] = choice["code"]
    # A merged unit is not its parts: refuse it wherever one of them is drawn.
    drawn_parts = {(units[c]["base"], units[c]["kind"]) for c in bound.values()
                   if units[c]["gone"]}
    for sid, code in list(bound.items()):
        key = (units[code]["base"], units[code]["kind"])
        parts = {p for p, s in SUCCESSOR.items() if s == key and p != key} & drawn_parts
        if not units[code]["gone"] and parts:
            del bound[sid]
            left.append(f"{units[code]['name']} (merged from {sorted(parts)}, drawn apart)")
    log(f"  EST admin2: {len(bound)} of {len(shapes)} polygons bound")
    if left:
        log(f"    polygons left unbound ({len(left)}): " + "; ".join(left))
    unused = sorted(units[c]["name"] for c in standing if c not in bound.values())
    if unused:
        log(f"    units standing in {YEAR} with no polygon ({len(unused)}): " + "; ".join(unused))

    # --- 3. The 2011 census, by the units of 31 December 2011.
    specs = {
        "ethnicity": ("RL0429", "Rahvus", "TOTAL", set(), labels_ethnicity),
        "language": ("RL0433", "Emakeel", "TOTAL", set(), labels_language),
        "religion": ("RL0452", "Usk", "899", {"898"}, labels_religion),
    }
    census: dict[str, dict[str, dict[str, float]]] = {}
    census_units: dict[str, dict[str, dict[str, Any]]] = {}
    census_counties: dict[str, dict[str, str]] = {}
    for field, (table, var, total, skip, relabel) in specs.items():
        mm = meta(table)
        census_units[field], census_counties[field] = units_of(mm["Elukoht"]["values"],
                                                               mm["Elukoht"]["valueTexts"])
        rows = query(table, {"Vanuserühm": ["Y_TOTAL"], "Sugu": ["T"], "Elukoht": "*", var: "*"})
        census[field] = composition(rows, "Elukoht", var, total, skip, relabel)
        log(f"  {table}: {len(census_units[field])} municipalities of {CENSUS_YEAR}")

    def parts_2011(code: str, field: str) -> list[str] | None:
        """The 2011 units that make the drawn unit, or None if one is not published."""
        u = units[code]
        key = (u["base"], u["kind"])
        preds = set() if u["gone"] else {p for p, s in SUCCESSOR.items() if s == key and p != key}
        found = {(cu["base"], cu["kind"]): c for c, cu in census_units[field].items()
                 if cu["county"] == u["county"] and (cu["base"], cu["kind"]) in preds | {key}}
        if not preds <= set(found) or not found:
            return None
        # A unit formed in 2013 did not exist in 2011; one that absorbed
        # others did, and must then be found too.
        if key not in found and key not in set(SUCCESSOR.values()):
            return None
        return list(found.values())

    records = []
    for sid, code in sorted(bound.items(), key=lambda kv: units[kv[1]]["name"]):
        u = units[code]
        year = last[code]
        fields = people[(code, str(year))].fields(
            year=year, source=f"{SOURCE}, RV0241", url=PAGE.format(table="RV0241"),
            date=f"1 January {year}", extra_note=(
                " The municipality as it stood before the 2017 reform, which is the unit the "
                "map draws." + (" It was merged away after this date, so this is its last "
                                "count." if u["gone"] else "")))
        fields["population"]["value"] = int(round(totals[(code, str(year))]))
        for field, (table, *_rest) in specs.items():
            parts = parts_2011(code, field)
            if not parts:
                continue
            counts: dict[str, float] = defaultdict(float)
            for c in parts:
                for k, v in census[field][c].items():
                    counts[k] += v
            total = counts.pop("__total__")
            if field != "religion" and not 0.6 < total / totals[(code, str(year))] < 1.6:
                log(f"  {u['name']}: {table} counts {total:,.0f} in {CENSUS_YEAR} against "
                    f"{totals[(code, str(year))]:,.0f} in {year}; {field} left out")
                continue
            block = census_block(field, table, counts, total,
                                 [census_units[field][c]["name"] for c in parts], CENSUS_YEAR)
            fields["sources"] += block.pop("sources")
            fields.update(block)
        shape = next(s for s in shapes if s["id"] == sid)
        records.append(record(
            f"EST-SE-{year}-{code}", u["name"], level="admin2", parent="EST", country="EST",
            parent_name=COUNTIES[u["county"]], codes={"rv0241": code, "vintage": year},
            match_by="shape_id", shape_id=sid, aliases=[shape["name"]], **fields))

    # --- 4. The old counties.
    admin1 = {fold(a["name"]): a for a in load_units("EST", "admin1")}
    eth17 = ethnicity_2017()
    now = {
        "language": ("RL21434", composition(query("RL21434", {
            "Aasta": ["2021"], "Vanuserühm": ["1"], "Sugu": ["1"],
            "Elukoht": list(UNCHANGED.values()), "Emakeel": "*"}),
            "Elukoht", "Emakeel", "1", set(), labels_language)),
        "religion": ("RL21452", composition(query("RL21452", {
            "Aasta": ["2021"], "Elukoht": list(UNCHANGED.values()), "Usk": "*"}),
            "Elukoht", "Usk", "1", {"2"}, labels_religion)),
    }
    for cc, row in sorted(county_rows.items()):
        shape = admin1[fold(COUNTIES[cc])]
        fields = people[(row, str(YEAR))].fields(
            year=YEAR, source=f"{SOURCE}, RV0241", url=PAGE.format(table="RV0241"),
            date=f"1 January {YEAR}", extra_note=(
                " The county as it stood before the 2017 reform, which is the unit the map "
                "draws."))
        fields["population"]["value"] = int(round(totals[(row, str(YEAR))]))
        if cc in UNCHANGED:
            for field, (table, data) in now.items():
                counts = dict(data[UNCHANGED[cc]])
                total = counts.pop("__total__")
                block = census_block(field, table, counts, total, [COUNTIES[cc]], 2021)
                fields["sources"] += block.pop("sources")
                fields.update(block)
        else:
            counts = dict(eth17[cc])
            total = counts.pop("__total__")
            fields["ethnicity"] = shares(counts, total=total)
            fields["ethnicity_year"] = YEAR
            fields["ethnicity_note"] = (
                f"Ethnic nationality as recorded in the population register on 1 January {YEAR}, "
                "for the county as it stood before the 2017 reform (Statistics Estonia, RV0222). "
                "The register's current table is by the counties formed in 2017, whose "
                "territory differs from the drawn one.")
            fields["sources"].append({"field": "ethnicity", "name": f"{SOURCE}, RV0222",
                                      "url": PAGE.format(table="RV0222"), "year": YEAR})
            for field in ("language", "religion"):
                row11 = census_counties[field].get(cc)
                if row11 is None or row11 not in census[field]:
                    continue
                counts = dict(census[field][row11])
                total = counts.pop("__total__")
                block = census_block(field, specs[field][0], counts, total, [COUNTIES[cc]],
                                     CENSUS_YEAR)
                fields["sources"] += block.pop("sources")
                fields.update(block)
        records.append(record(
            f"EST-SE-C{cc}", shape["name"], level="admin1", parent="EST", country="EST",
            codes={"old_county": cc}, match_by="shape_id", shape_id=shape["id"], **fields))

    labels: dict[str, set[str]] = defaultdict(set)
    for r in records:
        for field in ("ethnicity", "language", "religion"):
            if isinstance(r.get(field), list):
                labels[field] |= {g["group"] for g in r[field]}
    for field, names in sorted(labels.items()):
        log(f"  {field} labels the group tree cannot place: {unplaced(field, names)}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
