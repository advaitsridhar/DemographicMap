#!/usr/bin/env python3
"""Slovenia: ethnicity, religion and mother tongue by občina, from the 2002 census.

Slovenia's census has been register-based since 2011 and asks none of the
three questions; 2002 was the last time they were put to everyone. SURS
publishes that census on SiStat by the municipalities of 2002:

* 05W1002S -- population by ethnic affiliation ("declared as"): Slovenes,
  others, undeclared, did not want to reply, unknown;
* 05W1003S, 05W1004S, 05W1005S -- those declared as Italians, Hungarians and
  Roma, the three minorities the constitution names, by the same
  municipalities; they are part of "others", which keeps the rest;
* 05W1006S -- religion; 05W1007S -- mother tongue;
* 05W1001S -- population by sex and age, the census total the others must make.

**Vintage.** The map draws the 212 municipalities of today. Nineteen were
carved out of 2002 municipalities in 2006 and 2011 (Apače from Gornja Radgona,
Ankaran from Koper, Mirna from Trebnje and so on), so a 2002 figure fits a
drawn polygon only where the municipality has not changed since. Which ones
have not is measured rather than declared: SURS republished the 2002 count
recalculated to the municipalities of 1 January 2007 (0558601S), and a
municipality whose 2002 population is the same in both tables kept its
territory to 2007. Koper and Trebnje, which lost Ankaran and Mirna in 2011,
are excluded by name. Every other municipality -- the new ones and those they
were carved from -- is written as a stated gap.

**Cohesion regions** (the map's first level): every 2002 municipality lies in
one of the two, whether or not it was split later, so each region is the sum
of its 2002 municipalities, and the two must make the country.

Usage:
    python -m scripts.fetch_census.slovenia_census
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, dated, gap, log, record, shares, write_json
from .central_ages import check_sum, fold, units
from .slovenia import BASE, bind, code_like, query
from .pxweb import http_json

YEAR = 2002
PORTAL = "https://pxweb.stat.si/SiStatData/pxweb/en/Data/-/05W1002S.px"
SOURCE = ("Statistical Office of the Republic of Slovenia (SURS), Census 2002, SiStat "
          "05W1001S-05W1007S (by municipality)")
LICENCE = "SURS open data (free reuse with attribution)"
OUT = PROCESSED / "slovenia_census.json"
SPLIT_IN_2011 = {"Koper", "Trebnje"}      # lost Ankaran and Mirna after the 2007 recalculation
# Municipalities renamed since 2002 without a change of territory: the 2002
# name -> today's, which the 2007 recalculation and the map both use.
RENAMED = {"Sveti Jurij": "Sveti Jurij ob Ščavnici", "Kanal": "Kanal ob Soči",
           "Šentjur pri Celju": "Šentjur"}
EXPECTED_2002 = 192

ETHNIC_ROWS = ["Declared -Slovenes", "Declared -others", "Undeclared", "Did not want to reply",
               "Unknown"]
ETHNICITY = {"Declared -Slovenes": "Slovene", "Undeclared": "Not declared",
             "Did not want to reply": "Not stated", "Unknown": "Unknown"}
MINORITIES = {"05W1003S": "Italian", "05W1004S": "Hungarian", "05W1005S": "Roma"}
RELIGION = {"Catholic": "Catholic", "Evangelical and other Protestant": "Protestant",
            "Orthodox": "Orthodox", "Islam": "Islam", "other religion": "Other religion",
            "Believer but belongs to no religion": "Believer, no church",
            "Unbeliever, atheist": "Atheist", "Did no want to reply": "Not stated",
            "Unknown": "Unknown"}
LANGUAGE = {"Slovene": "Slovene", "Italian": "Italian", "Hungarian": "Hungarian",
            "Romany": "Romani", "Albanian": "Albanian", "Bosnian": "Bosnian",
            "Croatian": "Croatian", "Macedonian": "Macedonian", "German": "German",
            "Serbian": "Serbian", "Serbo-Croatian": "Serbo-Croatian", "Other": "Other",
            "Unknown": "Unknown"}

NOTES = {
    "ethnicity": ("Ethnic affiliation (narodna pripadnost), Census 2002 (31 March 2002), the whole "
                  "population, one answer. SURS publishes Slovenes and the three constitutional "
                  "minorities -- Italians, Hungarians, Roma -- by municipality; every other declared "
                  "affiliation (Croats, Serbs, Bosniaks, Muslims and the rest) is 'Other'. 'Not "
                  "declared' did not declare an ethnic affiliation; 'Not stated' did not want to "
                  "reply; 'Unknown' is those the census could not establish. SiStat blanks cells of "
                  "few people for confidentiality: one blank cell is rebuilt from the subtotal it "
                  "publishes beside it, and where two or more are blank their people are left out. "
                  "Slovenia's "
                  "census has been register-based since 2011 and has not asked the question since "
                  "2002."),
    "religion": ("Religion (veroizpoved), Census 2002 (31 March 2002), the whole population, one "
                 "answer; 'Believer, no church' believes but belongs to no religious community; "
                 "'Not stated' did not want to reply; 'Unknown' could not be established. SiStat "
                 "blanks cells of few people for confidentiality: one blank cell is rebuilt from "
                 "the subtotal published beside it, and where two or more are blank their people "
                 "are left out, so a municipality's shares can fall short of 100. Not "
                 "asked since 2002: the census has been register-based since 2011."),
    "language": ("Mother tongue (materni jezik), Census 2002 (31 March 2002), the whole population, "
                 "one answer; 'Other' is every language SURS does not name at municipal level. "
                 "SiStat blanks cells of few people for confidentiality: one blank cell is rebuilt "
                 "from the total, and where two or more are blank their people are left out, so a "
                 "municipality's shares can fall short of 100. "
                 "Not asked since 2002: the census has been register-based since 2011."),
}


def with_subtotal(cells: dict[str, float], subtotal: str, others: list[str],
                  total: float) -> dict[str, float]:
    """The subtotal, rebuilt as the total less the other rows where it is blank and they are not."""
    if subtotal in cells or any(k not in cells for k in others):
        return cells
    return {**cells, subtotal: total - sum(cells[k] for k in others)}


def fill_single(cells: dict[str, float], keys: list[str], whole: float | None,
                name: str) -> tuple[dict[str, float], float]:
    """Rebuild the one blank cell among ``keys`` from their published total.

    Returns the cells and, where two or more are blank, how many people they
    hold together (the total less the published ones), which the caller leaves
    out. Without a total nothing can be rebuilt and nothing may be blank.
    """
    blank = [k for k in keys if k not in cells]
    if whole is None:
        if blank:
            raise SystemExit(f"slovenia_census: {name}: {blank} blank with no total to measure them")
        return cells, 0.0
    rest = whole - sum(cells.get(k, 0.0) for k in keys)
    if rest < -0.5 or (not blank and abs(rest) > 0.5):
        raise SystemExit(f"slovenia_census: {name}: {keys} make {whole - rest:,.0f}, "
                         f"their total is {whole:,.0f}")
    if len(blank) == 1:
        return {**cells, blank[0]: max(rest, 0.0)}, 0.0
    return cells, max(rest, 0.0) if blank else 0.0


def table(name: str) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """{municipality label: {value label: count}} for a two-way table, and {code: label}.

    Every variable but the municipality is read whole, so a table with a third
    variable (sex, say) must be narrowed by the caller; this stops instead.
    """
    meta = {v["code"]: v for v in http_json(BASE + name + ".px")["variables"]}
    muni = code_like(meta, "MUNICIP")
    others = [c for c in meta if c != muni]
    log(f"  {name}: {http_json(BASE + name + '.px')['title']}; variables {list(meta)}")
    picks: dict[str, list[str] | None] = {muni: None}
    for code in others:
        values, texts = meta[code]["values"], meta[code]["valueTexts"]
        if len(others) > 1:
            totals = [v for v, t in zip(values, texts) if "total" in t.lower()]
            if len(totals) != 1 and code != others[-1]:
                raise SystemExit(f"slovenia_census: {name}: cannot narrow {code} {texts}")
            picks[code] = totals if code != others[-1] else None
        else:
            picks[code] = None
    out: dict[str, dict[str, float]] = {}
    for key, value in query(name + ".px", picks):
        label = key[muni][1].strip()
        what = key[others[-1]][1].strip()
        out.setdefault(label, {})[what] = value
    return out, {v: t for v, t in zip(meta[muni]["values"], meta[muni]["valueTexts"])}


def one_value(name: str) -> dict[str, float]:
    """{municipality label: count} from a table of one group by municipality."""
    rows, _ = table(name)
    out = {}
    for label, cells in rows.items():
        totals = {k: v for k, v in cells.items() if "total" in k.lower() or len(cells) == 1}
        if len(totals) != 1:
            raise SystemExit(f"slovenia_census: {name}: {label} has cells {cells}")
        out[label] = next(iter(totals.values()))
    return out


def today(name: str) -> str:
    return RENAMED.get(name, name)


def unchanged_since_2002() -> tuple[set[str], dict[str, float]]:
    """Municipalities (folded names of today) whose 2002 count is the same on the 2007 map."""
    def totals(name: str) -> dict[str, float]:
        meta = {v["code"]: v for v in http_json(BASE + name + ".px")["variables"]}
        muni, sex, age = (code_like(meta, "MUNICIP"), code_like(meta, "SEX"),
                          code_like(meta, "AGE"))
        picks = {sex: [meta[sex]["values"][0]], muni: None, age: [meta[age]["values"][0]]}
        return {fold(today(key[muni][1].strip())): value
                for key, value in query(name + ".px", picks)}
    in_2002, in_2007 = totals("05W1001S"), totals("0558601S")
    same = {m for m, n in in_2002.items() if m in in_2007 and in_2007[m] == n}
    changed = sorted(m for m in in_2002 if m not in same)
    log(f"  2002 count on the 2002 and the 2007 municipalities: {len(same)} of {len(in_2002)} "
        f"the same; changed or renamed: {changed}")
    log(f"  on the 2007 map and not in 2002: {sorted(m for m in in_2007 if m not in in_2002)}")
    return same, in_2002


def build() -> list[dict[str, Any]]:
    log("slovenia_census: Census 2002 by municipality, SiStat 05W1001S-05W1007S")
    same, census_total = unchanged_since_2002()
    ethnic, labels = table("05W1002S")
    religion, _ = table("05W1006S")
    language, _ = table("05W1007S")
    minority = {group: one_value(t) for t, group in MINORITIES.items()}
    national = next(k for k in ethnic if fold(k) == "slovenia")
    names = sorted(k for k in ethnic if k != national)
    log(f"  {len(names)} municipalities of 2002; Slovenia {ethnic[national]['POPULATION']:,.0f}")
    if len(names) != EXPECTED_2002:
        raise SystemExit(f"slovenia_census: {len(names)} municipalities, not {EXPECTED_2002}")

    counts: dict[str, dict[str, dict[str, float]]] = {}
    suppressed = {"religion": 0.0, "language": 0.0, "ethnicity": 0.0}
    for name in [national, *names]:
        e, r, lang = ethnic[name], religion[name], language[name]
        total = e["POPULATION"]
        key = fold(today(name))
        if key not in census_total or abs(census_total[key] - total) > 0.5:
            raise SystemExit(f"slovenia_census: {name}: 05W1002S counts {total:,.0f}, 05W1001S "
                             f"{census_total.get(key)}")
        for field, cells, wanted, totals in (
                ("ethnicity", e, ETHNIC_ROWS, {"POPULATION", "Declared - total"}),
                ("religion", r, RELIGION, {"Total", "Declared by religion - total"}),
                ("language", lang, LANGUAGE, {"Mother tongue - TOTAL"})):
            unknown = set(cells) - set(wanted) - totals
            if unknown:
                raise SystemExit(f"slovenia_census: {name}: {field} rows this reader does not "
                                 f"know: {sorted(unknown)} (it knows {sorted(wanted)})")
        # Blanked cells are rebuilt from the subtotals SiStat publishes beside
        # them: one blank cell in a group is its subtotal less the rest; two or
        # more are left out, and how many people they hold is still known.
        e = with_subtotal(e, "Declared - total", ETHNIC_ROWS[2:], total)
        r = with_subtotal(r, "Declared by religion - total", list(RELIGION)[5:], total)
        if "Declared - total" in e:
            e, hid_e1 = fill_single(e, ETHNIC_ROWS[:2], e["Declared - total"], name)
            e, hid_e2 = fill_single(e, ETHNIC_ROWS[2:], total - e["Declared - total"], name)
        else:
            e, hid_e1 = fill_single(e, ETHNIC_ROWS, total, name)
            hid_e2 = 0.0
        declared = r.get("Declared by religion - total")
        if declared is not None:
            r, hid_r1 = fill_single(r, list(RELIGION)[:5], declared, name)
            r, hid_r2 = fill_single(r, list(RELIGION)[5:], total - declared, name)
        else:
            r, hid_r1 = fill_single(r, list(RELIGION), total, name)
            hid_r2 = 0.0
        lang, hid_l = fill_single(lang, list(LANGUAGE), lang.get("Mother tongue - TOTAL"), name)
        for field, hidden in (("ethnicity", hid_e1 + hid_e2), ("religion", hid_r1 + hid_r2),
                              ("language", hid_l)):
            if hidden > 0.5:
                suppressed[field] += hidden
                log(f"  {name}: {field}: {hidden:,.0f} people in blanked cells, left out")
        named = {g: minority[g].get(name, 0.0) for g in MINORITIES.values()}
        other = e.get("Declared -others", 0.0) - sum(named.values())
        if other < -0.5:
            raise SystemExit(f"slovenia_census: {name}: the three minorities exceed 'others'")
        eth = {label: e.get(k, 0.0) for k, label in ETHNICITY.items()}
        eth.update(named)
        eth["Other"] = other
        rel = {label: r.get(k, 0.0) for k, label in RELIGION.items()}
        lan = {label: lang.get(k, 0.0) for k, label in LANGUAGE.items()}
        for field, got, hidden in (("ethnicity", eth, hid_e1 + hid_e2),
                                   ("religion", rel, hid_r1 + hid_r2), ("language", lan, hid_l)):
            if abs(sum(got.values()) + hidden - total) > 0.5 or hidden > 0.15 * total:
                raise SystemExit(f"slovenia_census: {name}: {field} rows make "
                                 f"{sum(got.values()):,.0f} and blanked cells {hidden:,.0f} of "
                                 f"{total:,.0f}")
        counts[name] = {"ethnicity": eth, "religion": rel, "language": lan, "total": {"": total}}
    check_sum((counts[n]["total"][""] for n in names), counts[national]["total"][""],
              "municipalities against Slovenia")
    log(f"  people in blanked cells, all municipalities: ethnicity "
        f"{suppressed['ethnicity']:,.0f}, religion {suppressed['religion']:,.0f}, "
        f"mother tongue {suppressed['language']:,.0f}")
    for group in MINORITIES.values():
        check_sum((minority[group].get(n, 0.0) for n in names), minority[group][national],
                  f"{group}s by municipality against Slovenia")

    bound = bind({str(i): today(n) for i, n in enumerate(names)})
    polygon = {names[int(i)]: shape for i, shape in bound.items()}
    source = [{"field": "religion/ethnicity/language", "name": SOURCE, "url": PORTAL,
               "license": LICENCE, "year": YEAR}]

    def fields(c: dict[str, dict[str, float]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        total = c["total"][""]
        for field in ("ethnicity", "religion", "language"):
            rows = shares({k: v for k, v in c[field].items() if v}, total=total)
            out[field] = rows
            out[f"{field}_year"] = dated(rows, YEAR)
            out[f"{field}_note"] = NOTES[field]
        return out

    records = []
    written: set[str] = set()
    for name in names:
        shape = polygon.get(name)
        if shape is None:
            log(f"  {name}: no polygon of that name; its 2002 figure counts in its cohesion "
                f"region only")
            continue
        if fold(today(name)) not in same or name in SPLIT_IN_2011:
            continue
        written.add(shape["id"])
        records.append(record(
            f"SVN-C2002-{fold(name)}", name, level="admin2", parent=shape["parent"], country="SVN",
            aliases=[shape["name"]] if shape["name"] != name else [], match_by="shape_id",
            shape_id=shape["id"], sources=source, **fields(counts[name])))
    why = ("Not written: the municipality's territory changed after the 2002 census (it was "
           "created from, or gave land to, a municipality formed in 2006 or 2011), and SURS "
           "publishes the 2002 ethnicity, religion and mother tongue by the municipalities of "
           "2002 only. Slovenia's census has not asked these questions since 2002.")
    for shape in units("SVN", "admin2"):
        if shape["id"] in written or shape["parent"] == "SVN":
            continue
        records.append(record(
            f"SVN-C2002-gap-{fold(shape['name'])}", shape["name"], level="admin2",
            parent=shape["parent"], country="SVN", match_by="shape_id", shape_id=shape["id"],
            **{f: gap(NOT_AVAILABLE, why) for f in ("ethnicity", "religion", "language")}))
    log(f"  {len(written)} municipalities written; "
        f"{sum(1 for r in records if r['id'].startswith('SVN-C2002-gap'))} stated gaps")

    regions = {u["id"]: u for u in units("SVN", "admin1")}
    sums: dict[str, dict[str, dict[str, float]]] = {}
    homeless = [n for n in names if polygon.get(n) is None or polygon[n]["parent"] not in regions]
    if homeless:
        raise SystemExit(f"slovenia_census: no polygon, so no cohesion region, for {homeless}")
    for name in names:
        shape = polygon[name]
        into = sums.setdefault(shape["parent"], {"ethnicity": {}, "religion": {}, "language": {},
                                                 "total": {"": 0.0}})
        for field, cells in counts[name].items():
            for k, v in cells.items():
                into[field][k] = into[field].get(k, 0.0) + v
    check_sum((s["total"][""] for s in sums.values()), counts[national]["total"][""],
              "cohesion regions against Slovenia")
    for region_id, c in sorted(sums.items()):
        region = regions[region_id]
        log(f"  {region['name']}: {c['total']['']:,.0f}")
        records.append(record(
            f"SVN-C2002-{fold(region['name'])}", region["name"], level="admin1", parent="SVN",
            country="SVN", match_by="shape_id", shape_id=region_id, sources=source, **fields(c)))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
