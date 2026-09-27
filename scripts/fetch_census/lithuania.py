#!/usr/bin/env python3
"""Lithuania: population, median age and sex ratio for the 60 municipalities and 10 counties.

Statistics Lithuania's Official Statistics Portal answers SDMX 2.1 at
osp-rs.stat.gov.lt. Every observation in its "generic" data message carries
its own key (``dimensionAtObservation="AllDimensions"``), so the reader here
takes each ``Obs`` with its ``ObsKey`` rather than looking for series.

* **S3R167_M3010202** -- resident population at the beginning of the year by
  municipality, sex and single year of age (0-84, 85 and over, and a few of
  unknown age). The median age and the sex ratio come from it.
* **S3R167_M3010203** -- the same people by five-year group, which gives the
  population and checks the single years, sex by sex.
* **S3R629_M3010217** -- the median age the office publishes for each unit,
  in completed years (44 for the country at the beginning of 2026, where
  Eurostat's convention gives 44.6). The map gives medians to a tenth of a year,
  interpolated within the year that holds the middle person, and so does this
  adapter, from the office's own single years; the run checks that every
  interpolated median falls in the office's completed year.

The codes are those of ``savivaldybesRegdb`` (00 the country, 01-10 the
counties, the rest the municipalities), and the code list gives each a
Lithuanian and an English name. The boundary file names municipalities in
both languages -- "Akmenės rajono savivaldybė" beside "Alytus District
Municipality" -- so both are offered to the binder, with the office's
abbreviations ("r. sav.", "d. mun.") written out.

**Compositions.** The 2021 census's ethnicity, mother tongue and religion
come from its statistical survey, weighted to every resident. osp.stat.gov.lt
answers a scripted request with a Cloudflare challenge (HTTP 403), so the
office's workbooks are read from the Internet Archive's captures of them. The
2021 round published mother tongue by municipality; its ethnicity and
religion workbooks are for the whole country only, so those come from the
2011 census, which published both by municipality. Cells the office withholds
as confidential are counted in the "Other" answer, and the note says how
many people that is.

Usage:
    python -m scripts.fetch_census.lithuania
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import fold
from .nordic_common import (SEX_RATIO_UNIT, AgeSex, bind_rows, check_parts, load_units,
                            request, sex_ratio, unplaced)

OSP = "https://osp-rs.stat.gov.lt/rest_xml"
AGES = "S3R167_M3010203"
SINGLE = "S3R167_M3010202"
MEDIAN = "S3R629_M3010217"
SOURCE = "Statistics Lithuania"
PAGE = "https://osp.stat.gov.lt/statistiniu-rodikliu-analize?indicator={flow}"
OUT = PROCESSED / "lithuania_municipality.json"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def observations(flow: str, year: int) -> list[tuple[dict[str, str], float | None]]:
    raw = request(f"{OSP}/data/{flow}?startPeriod={year}&endPeriod={year}",
                  accept="application/xml")
    root = ET.fromstring(raw)
    out = []
    for obs in root.iter():
        if not obs.tag.endswith("}Obs"):
            continue
        key, value = {}, None
        for el in obs.iter():
            if el.tag.endswith("}Value") and el.get("id"):
                key[el.get("id")] = el.get("value")
            elif el.tag.endswith("}ObsValue"):
                text = el.get("value")
                value = None if text in (None, "", "NaN") else float(text)
        out.append((key, value))
    if not out:
        raise SystemExit(f"{flow} {year}: no observations -- "
                         + " ".join(raw[:400].decode("utf-8", "replace").split()))
    return out


def code_names(flow: str) -> dict[str, dict[str, str]]:
    """{code: {"lt": name, "en": name}} for the municipality code list."""
    raw = request(f"{OSP}/datastructure/LSD/{flow.split('_', 1)[1]}/latest?references=children",
                  accept="application/xml")
    root = ET.fromstring(raw)
    for codelist in root.iter():
        if codelist.tag.endswith("}Codelist") and codelist.get("id") == "savivaldybesRegdb":
            return {code.get("id"): {n.get(XML_LANG): n.text or "" for n in code
                                     if n.tag.endswith("}Name")}
                    for code in codelist if code.tag.endswith("}Code")}
    raise SystemExit(f"{flow}: no savivaldybesRegdb code list in its structure")


def expand_lt(name: str) -> str:
    return (name.replace(" r. sav.", " rajono savivaldybė")
                .replace(" m. sav.", " miesto savivaldybė")
                .replace(" sav.", " savivaldybė"))


def expand_en(name: str) -> str:
    return (name.replace(" d. mun.", " District Municipality")
                .replace(" c. mun.", " City Municipality")
                .replace(" t. mun.", " City Municipality")
                .replace(" mun.", " Municipality"))


# ---------------------------------------------------------------------------
# The censuses' compositions, from the office's own workbooks
# ---------------------------------------------------------------------------
#
# osp.stat.gov.lt answers a scripted request with a Cloudflare challenge (HTTP
# 403, "Just a moment..."), so its census workbooks are read from the Internet
# Archive's captures of the same files -- the office's files byte for byte, at
# the URLs the office published them under. The 2021 round published mother
# tongue by municipality; its ethnicity and religion workbooks are national
# only, so those two come from the 2011 census, which published both by
# municipality. The 60 municipalities have not changed since 2000.
ARCHIVE = "https://web.archive.org/web/{ts}id_/{url}"
LANG_2021 = ("20221227012930", "https://osp.stat.gov.lt/documents/10180/10367417/"
             "Population_by_mother_tongue_in_municipality-EN.xlsx/"
             "1c3c9ad4-5fa5-44b1-baa7-e6caef4b740b?version=1.0")
ETH_2011 = ("20130929225433", "http://osp.stat.gov.lt/documents/10180/217110/"
            "Gyventojai_pagal_tautybe_savivaldybese.xls/3b346c37-b28f-4dcc-9836-874b6ea951f7")
REL_2011 = ("20130929225123", "http://osp.stat.gov.lt/documents/10180/217110/"
            "Gyv_religine_bendr_savivald.xls/b845994c-bcf6-4568-9b02-e849b55d6d37")

ETHNIC_2011 = {"Lietuviai": "Lithuanian", "Lenkai": "Polish", "Rusai": "Russian",
               "Baltarusiai": "Belarusian", "Ukrainiečiai": "Ukrainian", "Žydai": "Jewish",
               "Totoriai": "Tatar", "Vokiečiai": "German", "Romai": "Romani",
               "Latviai": "Latvian", "Armėnai": "Armenian", "Kitos": "Other",
               "Nenurodė": "Not stated"}
RELIGION_2011 = {"Romos katalikų": "Roman Catholic", "Stačiatikių (ortodoksų)": "Orthodox",
                 # Old Believers are the Russian Orthodox of the 17th-century
                 # schism; the group tree files a bare "Old Believers" under
                 # Protestantism, which they are not.
                 "Sentikių": "Old Believers (Orthodox)",
                 "Evangelikų liuteronų": "Evangelical Lutheran",
                 "Evangelikų reformatų": "Evangelical Reformed",
                 "Musulmonų sunitų": "Sunni Muslim", "Judėjų": "Judaism",
                 "Graikų apeigų katalikų": "Greek Catholic", "Karaimų": "Karaite Judaism",
                 "Kitų": "Other religion", "Nė vienai": "No religion", "Nenurodė": "Not stated"}
LANGUAGE_2021 = {"Other": "Other language"}


def cell(value: Any) -> float | None:
    """A workbook cell as a count; a blank or a bullet is a withheld count."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text or text in ("•", "●", "-", "–"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def workbook_rows(raw: bytes) -> list[list[Any]]:
    if raw[:4] == b"\xd0\xcf\x11\xe0":
        import xlrd
        sheet = xlrd.open_workbook(file_contents=raw).sheets()[-1]
        return [sheet.row_values(i) for i in range(sheet.nrows)]
    import io
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = next(sh for sh in book.worksheets if sh.title != "XDO_METADATA")
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def read_table(source: tuple[str, str], labels: dict[str, str]) -> tuple[
        dict[str, dict[str, float]], dict[str, float], dict[str, float]]:
    """{row name: {label: count}}, {row name: total}, {row name: withheld}.

    The header is the row whose second cell reads "Iš viso" or "Total". A
    blank or bulleted cell is a count the office withheld as confidential;
    what the published cells leave of the row's total is those people, and
    is returned apart so the caller can say how many.
    """
    raw = request(ARCHIVE.format(ts=source[0], url=source[1]), accept="*/*", timeout=240)
    rows = workbook_rows(raw)
    head = next(i for i, r in enumerate(rows)
                if len(r) > 1 and str(r[1] or "").strip() in ("Iš viso", "Total"))
    columns = [str(c or "").strip() for c in rows[head]]
    out, totals, withheld = {}, {}, {}
    for row in rows[head + 1:]:
        name = str(row[0] or "").strip()
        total = cell(row[1]) if len(row) > 1 else None
        if not name or total is None:
            continue
        counts: dict[str, float] = defaultdict(float)
        for col, value in zip(columns[2:], row[2:]):
            n = cell(value)
            if col and n is not None:
                counts[labels.get(col, col)] += n
        short = total - sum(counts.values())
        if short < -0.5:
            raise SystemExit(f"{source[1].rsplit('/', 2)[-2]}: {name}'s categories make "
                             f"{sum(counts.values()):,.0f} of {total:,.0f}")
        out[name], totals[name], withheld[name] = counts, total, max(short, 0.0)
    return out, totals, withheld


def en_key(name: str) -> tuple[str, str]:
    """'Klaipėdos c. mun.' -> ('klaipedos', 'c'); 'Kazlų Rūda mun.' -> ('kazluruda', '')."""
    text = " ".join(str(name).replace("c.mun", "c. mun").replace("d.mun", "d. mun").split())
    kind = ""
    for mark in ("c", "d", "t"):
        if f" {mark}. mun" in text:
            kind, text = mark, text.split(f" {mark}. mun")[0]
            break
    else:
        text = text.split(" mun")[0]
    return fold(text), kind


def match_rows(rows: list[str], names: dict[str, str], wanted: list[str]) -> dict[str, str]:
    """The 2021 workbook's English row names -> codes, one to one.

    It writes some municipalities in Lithuanian genitive ("Klaipėdos c. mun.",
    "Panevėžio c.mun.") where the code list writes the nominative ("Klaipėda
    c. mun."). An exact name wins; failing it, the one code of the same kind
    whose name shares all but its last three letters. A code no row reaches
    stops the run.
    """
    keys = {code: en_key(names[code]) for code in wanted}
    out: dict[str, str] = {}
    for row in rows:
        stem, kind = en_key(row)
        exact = [c for c, k in keys.items() if k == (stem, kind)]
        if not exact:
            def shared(a: str, b: str) -> int:
                n = 0
                while n < min(len(a), len(b)) and a[n] == b[n]:
                    n += 1
                return n
            exact = [c for c, (st, kd) in keys.items() if kd == kind
                     and shared(st, stem) >= max(5, min(len(st), len(stem)) - 3)]
        if len(exact) == 1:
            if exact[0] in out.values():
                raise SystemExit(f"two workbook rows name code {exact[0]}: {row!r}")
            out[row] = exact[0]
    missing = sorted(set(wanted) - set(out.values()))
    if missing:
        raise SystemExit(f"workbook rows found for no {[names[c] for c in missing]}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    names = code_names(AGES)
    year = None
    for candidate in range(2027, 2019, -1):
        try:
            rows = observations(AGES, candidate)
        except SystemExit:
            continue
        year = candidate
        break
    if year is None:
        raise SystemExit(f"{AGES}: no year from 2020 on")
    log(f"lithuania: {AGES}, {SINGLE} and {MEDIAN}, beginning of {year}")
    people: dict[str, AgeSex] = defaultdict(AgeSex)
    totals: dict[tuple[str, str], float] = {}
    unknown: dict[str, float] = defaultdict(float)
    age_var = "Demogr_amziusM1411"
    for key, value in observations(SINGLE, year):
        if value is None:
            continue
        code, sex, age = key["savivaldybesRegdb"], key["Lytis"], key[age_var]
        if age == "g000g999":
            totals[(code, sex)] = value
        elif sex == "0":
            continue
        elif age == "gxxx":
            unknown[code] += value
        else:
            people[code].add(85 if age == "g085" else int(age), "m" if sex == "1" else "f", value)
    # The five-year table is the check on the single years: the same people,
    # tabulated a second time.
    grouped: dict[tuple[str, str], float] = {}
    for key, value in rows:
        if value is not None and key["Demogr_amziaus_grM1412"] == "g000g999":
            grouped[(key["savivaldybesRegdb"], key["Lytis"])] = value
    for code, got in people.items():
        whole = totals.get((code, "0"), grouped.get((code, "0"), -1))
        if abs(got.total + unknown[code] - whole) > 0.5:
            raise SystemExit(f"{SINGLE} {code}: single years make {got.total:,.0f} "
                             f"(+{unknown[code]:,.0f} of unknown age) against {whole:,.0f}")
        if abs(whole - grouped.get((code, "0"), whole)) > 0.5:
            raise SystemExit(f"{code}: {SINGLE} counts {whole:,.0f}, {AGES} "
                             f"{grouped.get((code, '0')):,.0f}")
        for sex, count in (("1", got.men), ("2", got.women)):
            if (code, sex) in grouped and abs(count - grouped[(code, sex)]) > unknown[code] + 0.5:
                raise SystemExit(f"{code} sex {sex}: single years make {count:,.0f} against "
                                 f"{grouped[(code, sex)]:,.0f}")
    medians = {key["savivaldybesRegdb"]: value for key, value in observations(MEDIAN, year)
               if key["Lytis"] == "0" and value is not None}

    def total(code: str) -> float:
        return grouped.get((code, "0"), people[code].total + unknown[code])

    counties = sorted(c for c in people if len(c) == 2 and c.isdigit() and 1 <= int(c) <= 10)
    municipalities = sorted(c for c in people if len(c) == 2 and c.isdigit() and int(c) > 10)
    check_parts({c: total(c) for c in counties}, total("00"),
                f"{AGES} {year}: counties -> Lithuania", 0)
    check_parts({c: total(c) for c in municipalities}, total("00"),
                f"{AGES} {year}: municipalities -> Lithuania", 0)
    # Statistics Lithuania publishes the median in completed years; the one
    # interpolated here from the same single years should fall in that year.
    off = [f"{c} {medians[c]:.0f} vs {people[c].median()}" for c in counties + municipalities
           + ["00"] if c in medians and int(people[c].median() or 0) != int(medians[c])]
    log(f"  national median {people['00'].median()} (the office: {medians.get('00')} in "
        f"completed years); units whose interpolated median is not in the office's year: "
        f"{off or 'none'}")

    def fields(code: str) -> dict[str, Any]:
        ages = people[code]
        date = f"1 January {year}"
        out: dict[str, Any] = {
            "population": measure(int(round(total(code))), year=year,
                                  source=f"{SOURCE}, {AGES}"),
            "population_note": f"Resident population at the beginning of {year}.",
            "median_age": measure(ages.median(), unit="years", year=year,
                                  source=f"{SOURCE}, {SINGLE}"),
            "median_age_note": (
                "Interpolated within the single year of age that holds the middle person, from "
                f"Statistics Lithuania's residents by single year of age on {date}. The office "
                f"publishes the median in completed years ({MEDIAN}: "
                f"{medians[code]:.0f} here); this is the same median to a tenth of a year, as "
                "the rest of the map gives it." if code in medians else
                "Interpolated within the single year of age that holds the middle person."),
            "sex_ratio": measure(sex_ratio(ages.men, ages.women), unit=SEX_RATIO_UNIT, year=year,
                                 source=f"{SOURCE}, {SINGLE}"),
            "sex_ratio_note": (f"Males per 100 females among residents on {date} "
                               f"({int(ages.men):,} males, {int(ages.women):,} females)."),
            "sources": [{"field": "population/median age/sex ratio",
                         "name": f"{SOURCE}, {SINGLE}",
                         "url": PAGE.format(flow=SINGLE.split("_")[0]), "year": year}],
        }
        return out

    # --- The censuses' compositions.
    comp: dict[str, dict[str, Any]] = defaultdict(dict)
    eth, eth_tot, eth_held = read_table(ETH_2011, ETHNIC_2011)
    rel, rel_tot, rel_held = read_table(REL_2011, RELIGION_2011)
    lang, lang_tot, lang_held = read_table(LANG_2021, LANGUAGE_2021)
    by_lt = {names[c]["lt"]: c for c in counties + municipalities}
    by_lt.update({names[c]["lt"].replace("apskritis", "apskr."): c for c in counties})
    en_rows = match_rows([r for r in lang if "mun" in r], {c: names[c]["en"] for c in municipalities},
                         municipalities)
    en_rows.update({r: c for r in lang for c in counties
                    if fold(r) == fold(names[c]["en"])})
    for field, table, totals_, held, year, keyed, what in (
            ("ethnicity", eth, eth_tot, eth_held, 2011, by_lt,
             "Ethnicity (tautybė) as answered in the 2011 census, of all residents"),
            ("religion", rel, rel_tot, rel_held, 2011, by_lt,
             "The religious community a resident said they belonged to, 2011 census, of all "
             "residents"),
            ("language", lang, lang_tot, lang_held, 2021, en_rows,
             "Mother tongue (gimtoji kalba) from the 2021 census's statistical survey of "
             "ethnicity, mother tongue and religion, weighted to all residents; 'Two mother "
             "tongues' is the office's own answer")):
        found = {keyed[r]: r for r in table if r in keyed}
        parts = {c: totals_[found[c]] for c in municipalities if c in found}
        national = next((totals_[r] for r in table if r in ("Iš viso", "Republic of Lithuanian",
                                                          "Republic of Lithuania")), None)
        if len(parts) != len(municipalities):
            raise SystemExit(f"{field}: rows for {len(parts)} of {len(municipalities)} "
                             "municipalities")
        if national is not None:
            check_parts(parts, national, f"{field} {year}: municipalities -> Lithuania", 0)
        for code, row in found.items():
            counts = dict(table[row])
            other = {"ethnicity": "Other", "religion": "Other religion",
                     "language": "Other language"}[field]
            if held[row] > 0.5:
                counts[other] = counts.get(other, 0.0) + held[row]
            comp[code].update({
                field: shares(counts, total=totals_[row]),
                f"{field}_year": year,
                f"{field}_note": (
                    f"{what} (Statistics Lithuania, {year} census)."
                    + (f" {int(held[row]):,} people are in cells the office withholds as "
                       f"confidential, and are counted in '{other}'." if held[row] > 0.5 else "")
                    + (" The 2021 round published ethnicity and religion only for the whole "
                       "country." if year == 2011 else "")),
                f"_{field}_source": {
                    "field": field, "name": f"{SOURCE}, {year} census",
                    "url": (LANG_2021 if field == "language" else
                            ETH_2011 if field == "ethnicity" else REL_2011)[1],
                    "archived": ARCHIVE.format(ts=(LANG_2021 if field == "language" else
                                                   ETH_2011 if field == "ethnicity"
                                                   else REL_2011)[0],
                                               url=(LANG_2021 if field == "language" else
                                                    ETH_2011 if field == "ethnicity"
                                                    else REL_2011)[1]).replace("id_/", "/"),
                    "year": year},
            })

    def with_census(code: str) -> dict[str, Any]:
        out = fields(code)
        extra = dict(comp.get(code, {}))
        for key in [k for k in extra if k.startswith("_") and k.endswith("_source")]:
            out["sources"].append(extra.pop(key))
        out.update(extra)
        return out

    rows_ = {c: (expand_lt(names[c]["lt"]), "") for c in municipalities}
    aliases = {expand_lt(names[c]["lt"]): expand_en(names[c]["en"]) for c in municipalities}
    bound, _m, _l, _p = bind_rows("LTU", "admin2", rows_, aliases=aliases)
    labels = {s["id"]: s["name"] for s in load_units("LTU", "admin2")}
    records = []
    for code in municipalities:
        sid = bound.get(code)
        if sid is None:
            continue
        name = rows_[code][0]
        records.append(record(
            f"LTU-OSP-{code}", name, level="admin2", parent="LTU", country="LTU",
            codes={"osp": code}, match_by="shape_id", shape_id=sid,
            aliases=sorted({labels[sid], expand_en(names[code]["en"])} - {name}),
            **with_census(code)))
    admin1 = {fold(u["name"].replace(" County", "")): u for u in load_units("LTU", "admin1")}
    for code in counties:
        english = names[code]["en"].replace(" county", "")
        shape = admin1.get(fold(english))
        if shape is None:
            raise SystemExit(f"lithuania: county {names[code]} has no polygon")
        records.append(record(
            f"LTU-OSP-{code}", shape["name"], level="admin1", parent="LTU", country="LTU",
            codes={"osp": code}, match_by="shape_id", shape_id=shape["id"],
            aliases=[names[code]["lt"], names[code]["en"]], **with_census(code)))
    for field in ("ethnicity", "religion", "language"):
        labels_ = {g["group"] for r in records if isinstance(r.get(field), list)
                   for g in r[field]}
        log(f"  {field} labels the group tree cannot place: {unplaced(field, labels_)}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
