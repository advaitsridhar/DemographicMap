#!/usr/bin/env python3
"""Taiwan: every township's population, median age, sex ratio and indigenous peoples, from the register, and its language from the 2020 census.

The Ministry of the Interior's Department of Household Registration serves
the household register through an open-data API
(www.ris.gov.tw/rs-opendata/api/v1/datastore/<dataset>/<ROC year and month>),
village by village (村里), 2,000 villages a page. Three datasets are read
for the end of August 2026 (period 11508) -- the month ``taiwan.py`` reads
the counties' registered populations for:

* **ODRP014** -- the registered population of every village by single year
  of age from 0 to 99 and 100 and over, by sex;
* **ODRP013** -- the same population by indigenous status: non-indigenous,
  plain indigenous, mountain indigenous and, since the register began to
  record it, Pingpu indigenous;
* **ODRP018** -- the people of indigenous status by people (族別): the
  sixteen recognised peoples, the ten Pingpu peoples and those who declared
  none.

The villages are added up to their township (鄉鎮市區, the first eight digits
of the village code) and the townships to their county.

**What is written.** For all 368 townships: the registered population, the
median age (interpolated within the single year of age that holds the
middle person; the open 100+ class never holds it), the sex ratio (men per
hundred women), and **ethnicity as indigenous status** -- the register's own
classification, a count of everyone: each of the sixteen recognised peoples
by its name, the ten Pingpu peoples together, the people of indigenous status
who declared no people, and everyone else as "Taiwanese (non-indigenous)",
under ``ethnicity_basis: "indigenous status (household register)"``. The
register records nothing finer about the non-indigenous majority -- Hoklo,
Hakka, mainlander or naturalised -- and the note says so; the counties keep
``taiwan.py``'s modelled composition. For the 22 counties: the median age
and sex ratio from the same townships' counts added up.

**Language** is the 2020 census's. Its results tables (109年普查統計結果表 on
www.stat.gov.tw) carry a report for each county and city (縣市別報告統計表),
and Table 6 of each, 6歲以上本國籍常住人口使用語言情形, prints for every
township (按鄉鎮市區別分) the residents of ROC nationality aged 6 and over and
the main language they currently use, per hundred: Mandarin, Taiwanese
Hokkien, Hakka, indigenous languages and other. That is the question and the
population ``taiwan.py`` writes for the counties from the national release,
so the two levels say the same thing. The 22 workbooks are read from
ws.dgbas.gov.tw, whose certificate chain is completed from its own Authority
Information Access extension (``aia``), never skipped. Checks, each a
refusal: every row's shares make 100 within ``LANGUAGE_ROW_TOLERANCE``; the
townships' bases add up to the county's; the county's shares are the
townships' weighted by their bases, within ``LANGUAGE_REBUILD_TOLERANCE``;
every township the register has is in a table, and every table row is a
township the register has.

**Religion** is not counted: Taiwan's census does not ask it and the register
does not record it (``not_collected``). Every township's record says so.

**Binding.** Each township is bound to its polygon by shape id through
``TOWNSHIPS``: the National Land Surveying and Mapping Center's point query
(api.nlsc.gov.tw/other/TownVillagePointQuery1) placed each drawn polygon's
label point in an official township -- 364 of them, one to one, every one in
the county the polygon is drawn under, which is how the boundary file's
"Xiaying" turned out to be 新營區 and its "Siaying" 下營區. The NLSC answered
nothing for four label points standing in the sea off narrow islands, and
those four are bound by name, each the only township of that name in its
county (``BY_NAME``). At run time the register's own code and name for each
township must agree with the table.

**Checks**, each a refusal: every village's single years add up to its men
and to its women, and men and women to its total; the three datasets count
the same people in every village; the indigenous peoples add up to the
people of indigenous status; every one of the 368 townships is bound once.

Usage:
    python -m scripts.fetch_census.taiwan_townships
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_COLLECTED, PROCESSED, RAW, gap, http_get, log, measure, record, write_json
from .east_asia_common import drawn, hundred, sex_ratio, single_year_median
from .taiwan import (
    LANGUAGE_BASIS, LANGUAGE_COLUMNS, LANGUAGE_LICENCE, LANGUAGE_ROW_TOLERANCE, LANGUAGE_YEAR,
)
from common import slugify  # noqa: E402 - on the path _shared sets

OUT = "taiwan_township.json"
PERIOD = "11508"
YEAR = 2026
AS_OF = "the end of August 2026"
API = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/{dataset}/{period}?page={page}"
PAGE_URL = "https://www.ris.gov.tw/app/portal/3053"
KEPT = RAW / "taiwan" / f"ris_townships_{PERIOD}.json"
MOI = "Ministry of the Interior, Department of Household Registration"
SOURCES = {
    "ODRP014": f"{MOI}, registered population by single year of age and sex, by village, {AS_OF} (open data ODRP014)",
    "ODRP013": f"{MOI}, registered population by indigenous status and sex, by village, {AS_OF} (open data ODRP013)",
    "ODRP018": f"{MOI}, registered indigenous population by people (族別) and sex, by village, {AS_OF} (open data ODRP018)",
}
LICENCE = "Open Government Data License, Taiwan (version 1.0)"
TOP = 100

# ODRP018's peoples, in the map's words. The ten Pingpu peoples, recorded
# since the register began to record Pingpu status, are written together.
PINGPU = "Indigenous Taiwanese (Pingpu peoples)"
PEOPLES: dict[str, str] = {
    "amis": "Amis", "atayal": "Atayal", "paiwan": "Paiwan", "bunun": "Bunun",
    "rukai": "Rukai", "pinuyumayan": "Puyuma", "cou": "Tsou", "saisiyat": "Saisiyat",
    "yami": "Yami (Tao)", "thao": "Thao", "kavalan": "Kavalan", "truku": "Truku",
    "sakizaya": "Sakizaya", "sediq": "Seediq", "hlaalua": "Hla'alua",
    "kanakanavu": "Kanakanavu",
    "siraya": PINGPU, "ketagalan": PINGPU, "taokas": PINGPU, "pazeh": PINGPU,
    "papora": PINGPU, "babuza": PINGPU, "hoanya": PINGPU, "kaxabu": PINGPU,
    "taivoan": PINGPU, "makatau": PINGPU,
    "undeclared": "Indigenous Taiwanese (people not declared)",
}
NON_INDIGENOUS = "Taiwanese (non-indigenous)"
ETHNICITY_BASIS = "indigenous status (household register)"

RELIGION_NOTE = (
    "Taiwan's census does not ask religion, and the household register does not record it, "
    "so nothing counts the religion of a township's people. The county carries a modelled "
    "estimate.")
LANGUAGE_NOTE = (
    "The 2020 census asked the language used at home and published it by county and city, "
    "which the county carries. The household register does not record language, so it has "
    "no township figure to give.")

# The 2020 census's county reports: each county's page among the results
# tables (109年普查統計結果表 > 縣市別報告統計表), whose Table 6 is the main
# language by township.
CENSUS_PAGE = "https://www.stat.gov.tw/News_Content.aspx?n=2755&s={page}"
CENSUS_TABLE = "https://ws.dgbas.gov.tw/001/Upload/463/relfile/11065/{page}/t006.xlsx"
CENSUS_REPORTS: dict[str, int] = {
    "新北市": 230886, "臺北市": 230887, "桃園市": 230883, "基隆市": 230888,
    "新竹市": 230889, "宜蘭縣": 230890, "新竹縣": 230892, "臺中市": 230893,
    "苗栗縣": 230894, "彰化縣": 230895, "南投縣": 230896, "雲林縣": 230897,
    "臺南市": 230898, "高雄市": 230899, "嘉義市": 230900, "嘉義縣": 230901,
    "屏東縣": 230902, "澎湖縣": 230903, "臺東縣": 230904, "花蓮縣": 230905,
    "金門縣": 230906, "連江縣": 230907,
}
LANGUAGE_KEPT = RAW / "taiwan" / "census2020_township_language.json"
# The main-language columns as Table 6 heads them, in LANGUAGE_COLUMNS' order.
LANGUAGE_HEADS = ("國語", "閩南語", "客語", "原住民族語", "其他")
SIGN = "臺灣手語"            # a column only some tables have; folded into "other"
BLOCK = "按鄉鎮市區別分"
LANGUAGE_REBUILD_TOLERANCE = 0.2   # points, the county row against its townships


# ---------------------------------------------------------------------------
# The register
# ---------------------------------------------------------------------------

def fetch_dataset(dataset: str, period: str = PERIOD) -> list[dict[str, Any]]:
    """Every village record of one dataset, page by page."""
    out: list[dict[str, Any]] = []
    page, pages = 1, None
    while pages is None or page <= pages:
        url = API.format(dataset=dataset, period=period, page=page)
        for attempt in range(4):
            try:
                blob = http_get(url, binary=True, cache=False, retries=2, timeout=180)
                data = json.loads(blob.decode("utf-8"))
                break
            except Exception as exc:  # noqa: BLE001 - the host drops a connection now and then
                log(f"  {dataset} page {page}: {exc!r}; retrying")
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"taiwan_townships: {dataset} page {page} never answered")
        if str(data.get("responseCode", "")).endswith("02-S"):
            raise SystemExit(f"taiwan_townships: {dataset}/{period}: {data.get('responseMessage')}")
        pages = int(data.get("totalPage") or 0)
        records = data.get("responseData") or []
        out.extend(records)
        size = int(data.get("totalDataSize") or 0)
        page += 1
    if len(out) != size:
        raise SystemExit(f"taiwan_townships: {dataset}: {len(out)} records of {size}")
    log(f"  {dataset}: {len(out):,} villages in {pages} pages")
    return out


def as_int(record_: dict[str, Any], key: str) -> int:
    value = record_.get(key)
    if value is None:
        raise SystemExit(f"taiwan_townships: {record_.get('site_id')} {record_.get('village')} "
                         f"has no {key}")
    return int(str(value).replace(",", "") or 0)


def aggregate(ages: list[dict[str, Any]], status: list[dict[str, Any]],
              peoples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{township code: {"name", "men", "women", "ages": {sex: {age: n}},
    "peoples": {label: n}, "indigenous": n}}, every village checked."""
    by_village: dict[str, dict[str, Any]] = {}
    for r in ages:
        code = str(r["district_code"])
        men, women = as_int(r, "people_total_m"), as_int(r, "people_total_f")
        if men + women != as_int(r, "people_total"):
            raise SystemExit(f"taiwan_townships: {r['site_id']} {r['village']}: men and women do "
                             "not make the total")
        row = {"name": r["site_id"], "men": men, "women": women,
               "ages": {"m": Counter(), "f": Counter()}}
        for sex in ("m", "f"):
            for age in range(TOP):
                row["ages"][sex][age] = as_int(r, f"people_age_{age:03d}_{sex}")
            row["ages"][sex][TOP] = as_int(r, f"people_age_100up_{sex}")
        if sum(row["ages"]["m"].values()) != men or sum(row["ages"]["f"].values()) != women:
            raise SystemExit(f"taiwan_townships: {r['site_id']} {r['village']}: the single years "
                             "do not make the men and women")
        if code in by_village:
            raise SystemExit(f"taiwan_townships: village {code} appears twice in ODRP014")
        by_village[code] = row
    indigenous: dict[str, int] = {}
    for r in status:
        code = str(r["district_code"])
        if code not in by_village:
            raise SystemExit(f"taiwan_townships: ODRP013 has a village {code} ODRP014 lacks")
        row = by_village[code]
        for sex, total in (("m", row["men"]), ("f", row["women"])):
            parts = [as_int(r, f"{k}_total_{sex}") for k in
                     ("nindigenous", "indigenous_plain", "indigenous_mountain")]
            parts.append(int(str(r.get(f"indigenous_pingpu_total_{sex}") or 0)))
            if sum(parts) != total:
                raise SystemExit(f"taiwan_townships: {r['site_id']} {r['village']}: ODRP013 counts "
                                 f"{sum(parts):,} of sex {sex}, ODRP014 {total:,}")
        indigenous[code] = (row["men"] + row["women"]
                            - as_int(r, "nindigenous_total_m") - as_int(r, "nindigenous_total_f"))
    if set(indigenous) != set(by_village):
        raise SystemExit("taiwan_townships: ODRP013 and ODRP014 list different villages")
    for r in peoples:
        code = str(r["district_code"])
        if code not in by_village:
            raise SystemExit(f"taiwan_townships: ODRP018 has a village {code} ODRP014 lacks")
        counts: Counter = Counter()
        for key, label in PEOPLES.items():
            counts[label] += as_int(r, f"indigenous_{key}_m") + as_int(r, f"indigenous_{key}_f")
        total = as_int(r, "indigenous_total")
        if sum(counts.values()) != total or total != indigenous[code]:
            raise SystemExit(f"taiwan_townships: {r['site_id']} {r['village']}: the peoples make "
                             f"{sum(counts.values()):,}, ODRP018's total {total:,}, ODRP013's "
                             f"indigenous {indigenous[code]:,}")
        by_village[code]["peoples"] = counts
    lacking = [c for c, row in by_village.items() if "peoples" not in row]
    if lacking:
        raise SystemExit(f"taiwan_townships: ODRP018 lacks {len(lacking)} villages")
    townships: dict[str, dict[str, Any]] = {}
    for code, row in by_village.items():
        town = townships.setdefault(code[:8], {
            "name": row["name"], "men": 0, "women": 0,
            "ages": {"m": Counter(), "f": Counter()}, "peoples": Counter()})
        if town["name"] != row["name"]:
            raise SystemExit(f"taiwan_townships: township {code[:8]} is both {town['name']} and "
                             f"{row['name']}")
        town["men"] += row["men"]
        town["women"] += row["women"]
        for sex in ("m", "f"):
            town["ages"][sex].update(row["ages"][sex])
        town["peoples"].update(row["peoples"])
    total = sum(t["men"] + t["women"] for t in townships.values())
    log(f"  {len(by_village):,} villages, every one adding up in all three datasets, in "
        f"{len(townships)} townships; {total:,} registered people")
    return townships


def keep(townships: dict[str, dict[str, Any]]) -> None:
    KEPT.parent.mkdir(parents=True, exist_ok=True)
    plain = {code: {"name": t["name"], "men": t["men"], "women": t["women"],
                    "ages": {s: [t["ages"][s][a] for a in range(TOP + 1)] for s in ("m", "f")},
                    "peoples": dict(t["peoples"])}
             for code, t in sorted(townships.items())}
    KEPT.write_text(json.dumps(plain, ensure_ascii=False), encoding="utf-8")
    log(f"  kept {KEPT.name} ({KEPT.stat().st_size / 1e3:.0f} kB)")


def load_kept() -> dict[str, dict[str, Any]]:
    plain = json.loads(KEPT.read_text(encoding="utf-8"))
    return {code: {"name": t["name"], "men": t["men"], "women": t["women"],
                   "ages": {s: Counter(dict(enumerate(t["ages"][s]))) for s in ("m", "f")},
                   "peoples": Counter(t["peoples"])}
            for code, t in plain.items()}


# ---------------------------------------------------------------------------
# Language: Table 6 of the 2020 census's county reports
# ---------------------------------------------------------------------------

def compact(cell: Any) -> str:
    return "".join(str(cell).split()) if cell is not None else ""


def share(cell: Any) -> float:
    text = compact(cell)
    if text in ("", "-", "－", "—"):
        return 0.0
    return float(text.replace(",", ""))


def read_language_table(rows: list[list[Any]], county: str) -> dict[str, dict[str, Any]]:
    """{county + township: {"base": residents of ROC nationality aged 6+, "main":
    {language: per hundred}}} from one county report's Table 6, the county's own
    row checked against its townships and left out."""
    title = "".join(compact(c) for row in rows[:5] for c in row)
    if county not in title or "使用語言" not in title:
        raise SystemExit(f"taiwan_townships: {county}'s Table 6 is headed {title[:50]!r}")
    head = next((i for i, row in enumerate(rows) if "國語" in [compact(c) for c in row]), None)
    block = next((i for i, row in enumerate(rows) if BLOCK in [compact(c) for c in row]), None)
    if head is None or block is None:
        raise SystemExit(f"taiwan_townships: {county}'s Table 6 has no language heads or no "
                         f"{BLOCK} block")
    heads = [compact(c) for c in rows[head]]
    cols = [heads.index(h) for h in LANGUAGE_HEADS]
    sign = heads.index(SIGN) if SIGN in heads[:cols[-1]] else None
    label_col = [compact(c) for c in rows[block]].index(BLOCK)
    # The column of residents is headed 6歲以上本國籍常住人口; the title above
    # says the same words and ends in 使用語言情形.
    base_col = next((j for i in range(head) for j, c in enumerate(rows[i])
                     if "本國籍常住" in compact(c) and "使用語言" not in compact(c)), None)
    if base_col is None:
        raise SystemExit(f"taiwan_townships: {county}'s Table 6 has no column of residents")
    table: dict[str, dict[str, Any]] = {}
    for row in rows[block + 1:]:
        name = compact(row[label_col]) if label_col < len(row) else ""
        # The block ends at a note, a blank row or the next block's head
        # (按性別分 follows on the same sheet in some counties' tables).
        if not name or name.startswith(("註", "按")) or compact(row[base_col]) == "":
            break
        main = {label: share(row[c]) for label, c in zip(LANGUAGE_COLUMNS, cols)}
        if sign is not None:
            main[LANGUAGE_COLUMNS[-1]] += share(row[sign])
        total = sum(main.values())
        if abs(total - 100) > LANGUAGE_ROW_TOLERANCE:
            raise SystemExit(f"taiwan_townships: {county} {name}: the main languages make "
                             f"{total:.1f} per hundred")
        table[name.replace("台", "臺")] = {"base": int(share(row[base_col])), "main": main}
    if county not in table or len(table) < 2:
        raise SystemExit(f"taiwan_townships: {county}'s Table 6 has no county row or no "
                         "townships")
    whole = table.pop(county)
    base = sum(t["base"] for t in table.values())
    if base != whole["base"]:
        raise SystemExit(f"taiwan_townships: {county}'s townships hold {base:,} residents 6+, "
                         f"its row {whole['base']:,}")
    for label in LANGUAGE_COLUMNS:
        rebuilt = sum(t["main"][label] * t["base"] for t in table.values()) / base
        if abs(rebuilt - whole["main"][label]) > LANGUAGE_REBUILD_TOLERANCE:
            raise SystemExit(f"taiwan_townships: {county}'s {label} is {whole['main'][label]} "
                             f"per hundred and its townships make {rebuilt:.2f}")
    return {county + name: row for name, row in table.items()}


def fetch_language() -> dict[str, dict[str, Any]]:
    import io

    import openpyxl
    out: dict[str, dict[str, Any]] = {}
    failed: list[str] = []
    for county, page in CENSUS_REPORTS.items():
        url = CENSUS_TABLE.format(page=page)
        blob = http_get(url, binary=True, cache=False, retries=2, timeout=120, aia=True)
        assert isinstance(blob, bytes)
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        sheets = [[list(r) for r in ws.iter_rows(values_only=True)] for ws in book.worksheets]
        rows = next((rows for rows in sheets
                     if any(BLOCK in [compact(c) for c in row] for row in rows)), None)
        try:
            if rows is None:
                raise SystemExit(f"taiwan_townships: {county}'s Table 6 has no sheet by "
                                 "township")
            table = read_language_table(rows, county)
        except SystemExit as exc:
            # Every county is read before refusing, so one run names every
            # table that reads otherwise than expected.
            failed.append(str(exc))
            continue
        out.update(table)
        log(f"  {county}: {len(table)} townships, {sum(t['base'] for t in table.values()):,} "
            "residents 6+")
    if failed:
        raise SystemExit("\n".join(failed))
    return out


def language_rows(main: dict[str, float]) -> list[dict[str, Any]]:
    rows = [{"group": label, "pct": round(pct, 1)} for label, pct in main.items() if pct > 0]
    return sorted(rows, key=lambda r: (-r["pct"], r["group"]))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def bind(townships: dict[str, dict[str, Any]], admin2: list[dict[str, Any]]
         ) -> dict[str, str]:
    """{shape id: township code}, one to one, the register agreeing with the table."""
    by_name = defaultdict(list)
    for code, t in townships.items():
        by_name[t["name"].replace("台", "臺")].append(code)
    out: dict[str, str] = {}
    for shape, (code, name) in TOWNSHIPS.items():
        if code not in townships:
            raise SystemExit(f"taiwan_townships: the register has no township {code} ({name})")
        if townships[code]["name"].replace("台", "臺") != name:
            raise SystemExit(f"taiwan_townships: the register calls {code} "
                             f"{townships[code]['name']}, the table {name}")
        out[shape] = code
    for shape, name in BY_NAME.items():
        codes = by_name.get(name, [])
        if len(codes) != 1:
            raise SystemExit(f"taiwan_townships: the register has {len(codes)} townships called "
                             f"{name}")
        out[shape] = codes[0]
    if len(set(out.values())) != len(out):
        raise SystemExit("taiwan_townships: a township is bound to two polygons")
    drawn_ids = {u["id"] for u in admin2}
    if set(out) != drawn_ids:
        raise SystemExit(f"taiwan_townships: polygons with no township: "
                         f"{sorted(drawn_ids - set(out))[:5]}; bound but not drawn: "
                         f"{sorted(set(out) - drawn_ids)[:5]}")
    unbound = sorted(set(townships) - set(out.values()))
    if unbound:
        raise SystemExit(f"taiwan_townships: townships with no polygon: "
                         f"{[townships[c]['name'] for c in unbound]}")
    return out


def figures(rid: str, name: str, level: str, parent: str, shape: str, men: int, women: int,
            ages: dict[str, Counter], where: str, **extra: Any) -> dict[str, Any]:
    both = Counter(ages["m"])
    both.update(ages["f"])
    base = (f"{MOI}: the {men + women:,} people registered in {where} at {AS_OF}, ROC "
            "nationals with a household registration; foreign residents are not on the "
            "household register.")
    return record(
        rid, name, level=level, parent=parent, country="TWN",
        match_by="shape_id", shape_id=shape,
        population=measure(men + women, year=YEAR, source=SOURCES["ODRP014"]),
        population_note=base,
        median_age=measure(single_year_median(dict(both)), unit="years", year=YEAR,
                           source=SOURCES["ODRP014"]),
        median_age_note=f"{base} Interpolated within the single year of age that holds the "
                        "middle person.",
        sex_ratio=sex_ratio(men, women, year=YEAR, source=SOURCES["ODRP014"]),
        sex_ratio_note=f"{men:,} men and {women:,} women.",
        **extra)


def township_record(shape: str, code: str, town: dict[str, Any], drawn_name: str,
                    parent: str, language: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = Counter({k: v for k, v in town["peoples"].items() if v})
    indigenous = sum(counts.values())
    counts[NON_INDIGENOUS] = town["men"] + town["women"] - indigenous
    note = (
        f"The household register's indigenous status at {AS_OF}: {indigenous:,} of the "
        f"{town['men'] + town['women']:,} registered people of this township hold indigenous "
        "status, by the people they declared; everyone else is 'Taiwanese (non-indigenous)', "
        "a category the register does not divide -- Hoklo, Hakka, mainlander and naturalised "
        "citizens are all in it. The ten Pingpu peoples are written together. Not an ethnicity "
        "question: the register records a legal status.")
    sources = [{"field": "population/median_age/sex_ratio", "name": SOURCES["ODRP014"],
                "url": PAGE_URL, "year": YEAR, "license": LICENCE},
               {"field": "ethnicity", "name": SOURCES["ODRP018"], "url": PAGE_URL,
                "year": YEAR, "license": LICENCE},
               {"field": "ethnicity", "name": SOURCES["ODRP013"], "url": PAGE_URL,
                "year": YEAR, "license": LICENCE}]
    spoken: dict[str, Any] = {"language": gap("not_available", LANGUAGE_NOTE)}
    if language is not None:
        county = next(zh for zh in CENSUS_REPORTS if language["key"].startswith(zh))
        spoken = {
            "language": language_rows(language["main"]), "language_year": LANGUAGE_YEAR,
            "language_basis": LANGUAGE_BASIS,
            "language_note": (
                f"2020 census, Table 6 of {county}'s report: the main language currently used, "
                f"one answer per person, by the {language['base']:,} residents of ROC "
                "nationality aged 6 and over in this township, per hundred as printed. 'Other "
                "languages' takes in other tongues, Taiwan Sign Language and none or not "
                "known. The census also recorded a secondary language, which is not read.")}
        sources.append({"field": "language",
                        "name": (f"DGBAS, 2020 Population and Housing Census, {county} report, "
                                 "Table 6: main language currently used by residents of ROC "
                                 "nationality aged 6 and over, by township"),
                        "url": CENSUS_TABLE.format(page=CENSUS_REPORTS[county]),
                        "year": LANGUAGE_YEAR, "license": LANGUAGE_LICENCE})
    return figures(
        f"TWN-{code}", drawn_name, "admin2", parent, shape, town["men"], town["women"],
        town["ages"], "this township",
        codes={"ris": code}, aliases=[town["name"]],
        ethnicity=hundred(dict(counts)), ethnicity_year=YEAR,
        ethnicity_basis=ETHNICITY_BASIS, ethnicity_note=note,
        religion=gap(NOT_COLLECTED, RELIGION_NOTE),
        **spoken,
        sources=sources)


def build(townships: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]],
          language: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    bound = bind(townships, admin2)
    spoken: dict[str, dict[str, Any] | None] = {code: None for code in bound.values()}
    if language is not None:
        keys = {code: townships[code]["name"].replace("台", "臺") for code in bound.values()}
        lacking = sorted(name for name in keys.values() if name not in language)
        extra = sorted(set(language) - set(keys.values()))
        if lacking or extra:
            raise SystemExit(f"taiwan_townships: townships with no language row: {lacking[:5]}; "
                             f"language rows with no township: {extra[:5]}")
        spoken = {code: dict(language[key], key=key) for code, key in keys.items()}
    names = {u["id"]: u["name"] for u in admin2}
    county_of = {u["id"]: u["name"] for u in admin1}
    # The parent is the county the boundary file draws the polygon under; it
    # draws Wuqiu under the country itself.
    parents = {u["id"]: (f"TWN-{slugify(county_of[u['parent']])}" if u.get("parent") in county_of
                         else "TWN") for u in admin2}
    records = [township_record(shape, code, townships[code], names[shape], parents[shape],
                               spoken[code])
               for shape, code in sorted(bound.items(), key=lambda kv: kv[1])]
    # The counties: the townships the register files under each (the first
    # five digits of the code), added up, bound to the county the boundary
    # file draws by its name.
    from .taiwan import COUNTIES
    counties: dict[str, dict[str, Any]] = {}
    for code, town in townships.items():
        county = next((zh for zh in COUNTIES if town["name"].replace("台", "臺").startswith(zh)),
                      None)
        if county is None:
            raise SystemExit(f"taiwan_townships: {town['name']} names no county")
        row = counties.setdefault(county, {"men": 0, "women": 0,
                                           "ages": {"m": Counter(), "f": Counter()}})
        row["men"] += town["men"]
        row["women"] += town["women"]
        for sex in ("m", "f"):
            row["ages"][sex].update(town["ages"][sex])
    shapes = {u["name"]: u["id"] for u in admin1}
    for zh, (drawn_name, _) in COUNTIES.items():
        if drawn_name not in shapes:
            raise SystemExit(f"taiwan_townships: no drawn county called {drawn_name!r}")
        row = counties[zh]
        records.append(figures(
            f"TWN-{slugify(drawn_name)}", drawn_name, "admin1", "TWN", shapes[drawn_name], row["men"],
            row["women"], row["ages"], "this county",
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCES["ODRP014"],
                      "url": PAGE_URL, "year": YEAR, "license": LICENCE}]))
    national = sum(r["population"]["value"] for r in records if r["level"] == "admin1")
    medians = [r["median_age"]["value"] for r in records if r["level"] == "admin2"]
    log(f"  {len(bound)} townships and {len(counties)} counties written, {national:,} people; "
        f"township medians {min(medians):.1f}-{max(medians):.1f}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refetch", action="store_true",
                    help="ask the register and the census even if kept")
    args = ap.parse_args()
    log(f"taiwan_townships: {MOI}, {AS_OF}")
    if KEPT.exists() and not args.refetch:
        log(f"  reading the kept {KEPT.name}")
        townships = load_kept()
    else:
        townships = aggregate(fetch_dataset("ODRP014"), fetch_dataset("ODRP013"),
                              fetch_dataset("ODRP018"))
        keep(townships)
    if LANGUAGE_KEPT.exists() and not args.refetch:
        log(f"  reading the kept {LANGUAGE_KEPT.name}")
        language = json.loads(LANGUAGE_KEPT.read_text(encoding="utf-8"))
    else:
        log("  the 2020 census's county reports, Table 6")
        language = fetch_language()
        LANGUAGE_KEPT.parent.mkdir(parents=True, exist_ok=True)
        LANGUAGE_KEPT.write_text(json.dumps(language, ensure_ascii=False, sort_keys=True),
                                 encoding="utf-8")
    records = build(townships, drawn("TWN", "admin1"), drawn("TWN", "admin2"), language)
    write_json(PROCESSED / OUT, records)
    return 0


# ---------------------------------------------------------------------------
# The polygons. Shape id -> (the register's township code, its name), as the
# NLSC's point query placed each drawn polygon's label point; the comment is
# the boundary file's label.
# ---------------------------------------------------------------------------

# Four label points the NLSC placed in no township -- the sea beside narrow
# islands. Each is bound by the one township of that name in its county.
BY_NAME: dict[str, str] = {
    "52511910B16548233454257": "澎湖縣白沙鄉",  # Baisha Town
    "52511910B25870488928169": "澎湖縣望安鄉",  # Wang'an Town
    "52511910B39055948947966": "連江縣東引鄉",  # Dongyin Town
    "52511910B78526013910080": "連江縣南竿鄉",  # 南竿鄉
}

TOWNSHIPS: dict[str, tuple[str, str]] = {
    "52511910B38062779232785": ("09007020", "連江縣北竿鄉"),  # Beigan
    "52511910B3516463668472": ("09007030", "連江縣莒光鄉"),  # Juguang
    "52511910B21260910933226": ("09020010", "金門縣金城鎮"),  # Jincheng Township
    "52511910B24095937104675": ("09020020", "金門縣金沙鎮"),  # 金沙鎮
    "52511910B57972476709593": ("09020030", "金門縣金湖鎮"),  # 金湖鎮
    "52511910B29261340686380": ("09020040", "金門縣金寧鄉"),  # Jinning Township
    "52511910B30921209280056": ("09020050", "金門縣烈嶼鄉"),  # 烈嶼鄉
    "52511910B62500214534323": ("09020060", "金門縣烏坵鄉"),  # Wuqiu
    "52511910B14816404731270": ("10002010", "宜蘭縣宜蘭市"),  # Yilan City
    "52511910B2005519933546": ("10002020", "宜蘭縣羅東鎮"),  # Luodong
    "52511910B76288634877329": ("10002030", "宜蘭縣蘇澳鎮"),  # Su'ao Township
    "52511910B1170609292065": ("10002040", "宜蘭縣頭城鎮"),  # Toucheng Township
    "52511910B67044835484249": ("10002050", "宜蘭縣礁溪鄉"),  # Jiaoxi Township
    "52511910B24217315836254": ("10002060", "宜蘭縣壯圍鄉"),  # Zhuangwei
    "52511910B30880402907345": ("10002070", "宜蘭縣員山鄉"),  # Yuanshan
    "52511910B8555120582575": ("10002080", "宜蘭縣冬山鄉"),  # Dongshan
    "52511910B7774942695724": ("10002090", "宜蘭縣五結鄉"),  # Wujie
    "52511910B30774246387934": ("10002100", "宜蘭縣三星鄉"),  # Sanxing
    "52511910B1281835166424": ("10002110", "宜蘭縣大同鄉"),  # Datong
    "52511910B58011485138839": ("10002120", "宜蘭縣南澳鄉"),  # Nan'ao
    "52511910B954183777842": ("10004010", "新竹縣竹北市"),  # Zhubei City
    "52511910B83254623159264": ("10004020", "新竹縣竹東鎮"),  # Zhudong
    "52511910B82760897224923": ("10004030", "新竹縣新埔鎮"),  # Xinpu
    "52511910B48556697809502": ("10004040", "新竹縣關西鎮"),  # Guanxi
    "52511910B77517078586613": ("10004050", "新竹縣湖口鄉"),  # Hukou
    "52511910B50770239456778": ("10004060", "新竹縣新豐鄉"),  # 新豐鄉
    "52511910B8433520860340": ("10004070", "新竹縣芎林鄉"),  # Qionglin
    "52511910B22102802824180": ("10004080", "新竹縣橫山鄉"),  # Hengshan
    "52511910B96314718972571": ("10004090", "新竹縣北埔鄉"),  # Beipu
    "52511910B70638918104863": ("10004100", "新竹縣寶山鄉"),  # Baoshan
    "52511910B53218930904512": ("10004110", "新竹縣峨眉鄉"),  # Emei
    "52511910B48822656668811": ("10004120", "新竹縣尖石鄉"),  # Jianshi
    "52511910B21980317252116": ("10004130", "新竹縣五峰鄉"),  # Wufeng
    "52511910B26440140856632": ("10005010", "苗栗縣苗栗市"),  # 苗栗市
    "52511910B80611967822771": ("10005020", "苗栗縣苑裡鎮"),  # 苑裡鎮
    "52511910B96063333949316": ("10005030", "苗栗縣通霄鎮"),  # 通霄鎮
    "52511910B68602378722707": ("10005040", "苗栗縣竹南鎮"),  # Zhunan Town
    "52511910B27389223998758": ("10005050", "苗栗縣頭份市"),  # 頭份市
    "52511910B26517515062770": ("10005060", "苗栗縣後龍鎮"),  # 後龍鎮
    "52511910B14763561478876": ("10005070", "苗栗縣卓蘭鎮"),  # Zhuolan Township
    "52511910B71032150875325": ("10005080", "苗栗縣大湖鄉"),  # 大湖鄉
    "52511910B29818712056723": ("10005090", "苗栗縣公館鄉"),  # 公館鄉
    "52511910B53728166380969": ("10005100", "苗栗縣銅鑼鄉"),  # 銅鑼鄉
    "52511910B42807411813200": ("10005110", "苗栗縣南庄鄉"),  # 南庄鄉
    "52511910B1289591480139": ("10005120", "苗栗縣頭屋鄉"),  # 頭屋鄉
    "52511910B13267113488931": ("10005130", "苗栗縣三義鄉"),  # 三義鄉
    "52511910B62200479590982": ("10005140", "苗栗縣西湖鄉"),  # 西湖鄉
    "52511910B63672424305930": ("10005150", "苗栗縣造橋鄉"),  # 造橋鄉
    "52511910B37723179298847": ("10005160", "苗栗縣三灣鄉"),  # 三灣鄉
    "52511910B1345857498627": ("10005170", "苗栗縣獅潭鄉"),  # 獅潭鄉
    "52511910B36549244443661": ("10005180", "苗栗縣泰安鄉"),  # 泰安鄉
    "52511910B76643025216805": ("10007010", "彰化縣彰化市"),  # Changhua City
    "52511910B67569609565838": ("10007020", "彰化縣鹿港鎮"),  # 鹿港鎮
    "52511910B24911018318465": ("10007030", "彰化縣和美鎮"),  # 和美鎮
    "52511910B4802898208422": ("10007040", "彰化縣線西鄉"),  # 線西鄉
    "52511910B66525116512935": ("10007050", "彰化縣伸港鄉"),  # Shengang Township
    "52511910B35262105049161": ("10007060", "彰化縣福興鄉"),  # 福興鄉
    "52511910B61439489120441": ("10007070", "彰化縣秀水鄉"),  # Xiushui Township
    "52511910B80020209032330": ("10007080", "彰化縣花壇鄉"),  # 花壇鄉
    "52511910B4018321552262": ("10007090", "彰化縣芬園鄉"),  # 芬園鄉
    "52511910B4946947315760": ("10007100", "彰化縣員林市"),  # 員林市
    "52511910B59824272814460": ("10007110", "彰化縣溪湖鎮"),  # 溪湖鎮
    "52511910B68305869820707": ("10007120", "彰化縣田中鎮"),  # 田中鎮
    "52511910B79023193352255": ("10007130", "彰化縣大村鄉"),  # 大村鄉
    "52511910B7838707993704": ("10007140", "彰化縣埔鹽鄉"),  # 埔鹽鄉
    "52511910B52234359951443": ("10007150", "彰化縣埔心鄉"),  # 埔心鄉
    "52511910B24462040337349": ("10007160", "彰化縣永靖鄉"),  # 永靖鄉
    "52511910B92709587856848": ("10007170", "彰化縣社頭鄉"),  # 社頭鄉
    "52511910B53055897182204": ("10007180", "彰化縣二水鄉"),  # 二水鄉
    "52511910B14295991899678": ("10007190", "彰化縣北斗鎮"),  # 北斗鎮
    "52511910B45758904415578": ("10007200", "彰化縣二林鎮"),  # 二林鎮
    "52511910B93844416805291": ("10007210", "彰化縣田尾鄉"),  # 田尾鄉
    "52511910B86901151057582": ("10007220", "彰化縣埤頭鄉"),  # Pitou Township
    "52511910B39925062868722": ("10007230", "彰化縣芳苑鄉"),  # 芳苑鄉
    "52511910B21046020325533": ("10007240", "彰化縣大城鄉"),  # 大城鄉
    "52511910B69050472249631": ("10007250", "彰化縣竹塘鄉"),  # 竹塘鄉
    "52511910B43288181316884": ("10007260", "彰化縣溪州鄉"),  # 溪州鄉
    "52511910B11437294536827": ("10008010", "南投縣南投市"),  # Nantou City
    "52511910B90712224530022": ("10008020", "南投縣埔里鎮"),  # Puli Town
    "52511910B24890266463781": ("10008030", "南投縣草屯鎮"),  # Caotun Town
    "52511910B648094459248": ("10008040", "南投縣竹山鎮"),  # Chushang
    "52511910B59553354826271": ("10008050", "南投縣集集鎮"),  # Jiji Town
    "52511910B95850947838113": ("10008060", "南投縣名間鄉"),  # Mingjian Town
    "52511910B8640641883305": ("10008070", "南投縣鹿谷鄉"),  # Lugu Town
    "52511910B28710323112279": ("10008080", "南投縣中寮鄉"),  # Zhongliao Township
    "52511910B58943778362560": ("10008090", "南投縣魚池鄉"),  # Yuchi Town
    "52511910B81868017791126": ("10008100", "南投縣國姓鄉"),  # Guoxing Township
    "52511910B97596648855860": ("10008110", "南投縣水里鄉"),  # Shueli Town
    "52511910B65736953470193": ("10008120", "南投縣信義鄉"),  # Xinyi Township
    "52511910B4023851996912": ("10008130", "南投縣仁愛鄉"),  # Ren'ai Township
    "52511910B54544949915679": ("10009010", "雲林縣斗六市"),  # Douliu
    "52511910B41918855057041": ("10009020", "雲林縣斗南鎮"),  # Dounan
    "52511910B66692058551395": ("10009030", "雲林縣虎尾鎮"),  # Huwei
    "52511910B93540688501820": ("10009040", "雲林縣西螺鎮"),  # Xiluo
    "52511910B60061263127196": ("10009050", "雲林縣土庫鎮"),  # Tuku
    "52511910B94627775761425": ("10009060", "雲林縣北港鎮"),  # Beigang
    "52511910B61790844495814": ("10009070", "雲林縣古坑鄉"),  # Gukeng
    "52511910B61192023784720": ("10009080", "雲林縣大埤鄉"),  # 大埤鄉 (Dapi)
    "52511910B82181877276071": ("10009090", "雲林縣莿桐鄉"),  # Citong
    "52511910B99182661436347": ("10009100", "雲林縣林內鄉"),  # Linnei
    "52511910B3173449865557": ("10009110", "雲林縣二崙鄉"),  # Erlun
    "52511910B99479800826846": ("10009120", "雲林縣崙背鄉"),  # Lunbei
    "52511910B12217989868885": ("10009130", "雲林縣麥寮鄉"),  # Mailiao
    "52511910B55591891530874": ("10009140", "雲林縣東勢鄉"),  # Dongshi
    "52511910B17799667237096": ("10009150", "雲林縣褒忠鄉"),  # Baozhong
    "52511910B40379944508344": ("10009160", "雲林縣臺西鄉"),  # Taixi
    "52511910B1376149917055": ("10009170", "雲林縣元長鄉"),  # Yuanchang
    "52511910B71690687423925": ("10009180", "雲林縣四湖鄉"),  # Sihu
    "52511910B9027234137610": ("10009190", "雲林縣口湖鄉"),  # Kouhu
    "52511910B61676244874246": ("10009200", "雲林縣水林鄉"),  # Shuilin
    "52511910B26426295483490": ("10010010", "嘉義縣太保市"),  # Taibao
    "52511910B67244265985329": ("10010020", "嘉義縣朴子市"),  # Puzi City
    "52511910B59176200579981": ("10010030", "嘉義縣布袋鎮"),  # Budai
    "52511910B15112316927565": ("10010040", "嘉義縣大林鎮"),  # Dalin
    "52511910B34768840903386": ("10010050", "嘉義縣民雄鄉"),  # Minxiong
    "52511910B40762326804108": ("10010060", "嘉義縣溪口鄉"),  # Xikou
    "52511910B52167757698823": ("10010070", "嘉義縣新港鄉"),  # Xingang
    "52511910B86399036189677": ("10010080", "嘉義縣六腳鄉"),  # Liujiao
    "52511910B91175598455743": ("10010090", "嘉義縣東石鄉"),  # Dongshi
    "52511910B19586040436612": ("10010100", "嘉義縣義竹鄉"),  # Yizhu
    "52511910B1429973809191": ("10010110", "嘉義縣鹿草鄉"),  # Lucao
    "52511910B78624558885304": ("10010120", "嘉義縣水上鄉"),  # Shuishang
    "52511910B68145786967648": ("10010130", "嘉義縣中埔鄉"),  # Zhongpu
    "52511910B55503333028627": ("10010140", "嘉義縣竹崎鄉"),  # Zhuqi
    "52511910B52477730632252": ("10010150", "嘉義縣梅山鄉"),  # Meishan
    "52511910B82353065981408": ("10010160", "嘉義縣番路鄉"),  # Fanlu
    "52511910B78382154896940": ("10010170", "嘉義縣大埔鄉"),  # Dapu
    "52511910B70473175587181": ("10010180", "嘉義縣阿里山鄉"),  # Alishan
    "52511910B78362812420952": ("10013010", "屏東縣屏東市"),  # Pingtung City
    "52511910B55551570232595": ("10013020", "屏東縣潮州鎮"),  # Chaozhou
    "52511910B63745543652662": ("10013030", "屏東縣東港鎮"),  # Dongang
    "52511910B47108576517123": ("10013040", "屏東縣恆春鎮"),  # Hengchun
    "52511910B53659520741831": ("10013050", "屏東縣萬丹鄉"),  # Wandan
    "52511910B94067910328765": ("10013060", "屏東縣長治鄉"),  # Changzhi
    "52511910B59245920767717": ("10013070", "屏東縣麟洛鄉"),  # Linluo
    "52511910B18270670997793": ("10013080", "屏東縣九如鄉"),  # Jiuru
    "52511910B32855735947523": ("10013090", "屏東縣里港鄉"),  # Ligang
    "52511910B65674101735888": ("10013100", "屏東縣鹽埔鄉"),  # Yanpu
    "52511910B31003231188752": ("10013110", "屏東縣高樹鄉"),  # Gaoshu
    "52511910B95398494564210": ("10013120", "屏東縣萬巒鄉"),  # Wanluan
    "52511910B65196754917234": ("10013130", "屏東縣內埔鄉"),  # Neipu
    "52511910B50234287801955": ("10013140", "屏東縣竹田鄉"),  # Zhutian
    "52511910B59671861776280": ("10013150", "屏東縣新埤鄉"),  # Xinpi
    "52511910B31717620625581": ("10013160", "屏東縣枋寮鄉"),  # Fangliao
    "52511910B1240337598967": ("10013170", "屏東縣新園鄉"),  # Xinyuan
    "52511910B86635109020715": ("10013180", "屏東縣崁頂鄉"),  # Kanding
    "52511910B8694284014765": ("10013190", "屏東縣林邊鄉"),  # Linbian
    "52511910B82588790657213": ("10013200", "屏東縣南州鄉"),  # Nanzhou
    "52511910B132067886793": ("10013210", "屏東縣佳冬鄉"),  # Jiadong
    "52511910B90795941917739": ("10013220", "屏東縣琉球鄉"),  # Xiaoliuqiu
    "52511910B47244734334087": ("10013230", "屏東縣車城鄉"),  # Checheng
    "52511910B96811995525646": ("10013240", "屏東縣滿州鄉"),  # Manzhou
    "52511910B32484376841800": ("10013250", "屏東縣枋山鄉"),  # Fangshan
    "52511910B78140930961679": ("10013260", "屏東縣三地門鄉"),  # Sandimen
    "52511910B41847670787440": ("10013270", "屏東縣霧臺鄉"),  # Wutai
    "52511910B55440888068193": ("10013280", "屏東縣瑪家鄉"),  # Majia
    "52511910B3118715998086": ("10013290", "屏東縣泰武鄉"),  # Taiwu
    "52511910B76864499188928": ("10013300", "屏東縣來義鄉"),  # Laiyi
    "52511910B70153095650041": ("10013310", "屏東縣春日鄉"),  # Chunri
    "52511910B47928826922149": ("10013320", "屏東縣獅子鄉"),  # Shizi
    "52511910B86664130512952": ("10013330", "屏東縣牡丹鄉"),  # Mudan
    "52511910B26321075911025": ("10014010", "臺東縣臺東市"),  # Taitung City
    "52511910B97060806511909": ("10014020", "臺東縣成功鎮"),  # Chenggong
    "52511910B59360103371589": ("10014030", "臺東縣關山鎮"),  # Guanshan
    "52511910B49397347460294": ("10014040", "臺東縣卑南鄉"),  # Beinan
    "52511910B14571669428725": ("10014050", "臺東縣鹿野鄉"),  # Luye
    "52511910B55567443002533": ("10014060", "臺東縣池上鄉"),  # Chishang
    "52511910B95876228816034": ("10014070", "臺東縣東河鄉"),  # Donghe
    "52511910B28406755893597": ("10014080", "臺東縣長濱鄉"),  # Changbin
    "52511910B85663060935330": ("10014090", "臺東縣太麻里鄉"),  # Taimali
    "52511910B16211515353621": ("10014100", "臺東縣大武鄉"),  # Dawu
    "52511910B398222474379": ("10014110", "臺東縣綠島鄉"),  # Green Island
    "52511910B3988585053627": ("10014120", "臺東縣海端鄉"),  # Haiduan
    "52511910B70456030054544": ("10014130", "臺東縣延平鄉"),  # Yanping
    "52511910B76622709081814": ("10014140", "臺東縣金峰鄉"),  # Jinfeng
    "52511910B9049907467318": ("10014150", "臺東縣達仁鄉"),  # Daren
    "52511910B19407638162060": ("10014160", "臺東縣蘭嶼鄉"),  # Orchid Island
    "52511910B56958480946992": ("10015010", "花蓮縣花蓮市"),  # Hualien City
    "52511910B17390178466990": ("10015020", "花蓮縣鳳林鎮"),  # Fenglin
    "52511910B43880613502989": ("10015030", "花蓮縣玉里鎮"),  # Yuli
    "52511910B49284203349487": ("10015040", "花蓮縣新城鄉"),  # Xincheng
    "52511910B33929030594907": ("10015050", "花蓮縣吉安鄉"),  # Ji'an
    "52511910B46580896438278": ("10015060", "花蓮縣壽豐鄉"),  # Shoufeng
    "52511910B4969786063416": ("10015070", "花蓮縣光復鄉"),  # Guangfu
    "52511910B98966812491458": ("10015080", "花蓮縣豐濱鄉"),  # Fengbin
    "52511910B22417450396653": ("10015090", "花蓮縣瑞穗鄉"),  # Ruisui
    "52511910B38320737099141": ("10015100", "花蓮縣富里鄉"),  # Fuli
    "52511910B12239492719020": ("10015110", "花蓮縣秀林鄉"),  # Xiulin
    "52511910B67072521171420": ("10015120", "花蓮縣萬榮鄉"),  # Wanrong
    "52511910B84254778922177": ("10015130", "花蓮縣卓溪鄉"),  # Zhuoxi
    "52511910B17356876538254": ("10016010", "澎湖縣馬公市"),  # Magong City
    "52511910B80624224978544": ("10016020", "澎湖縣湖西鄉"),  # Huxi Town
    "52511910B49192689587509": ("10016040", "澎湖縣西嶼鄉"),  # Xiyu Town
    "52511910B27783301561641": ("10016060", "澎湖縣七美鄉"),  # Qimei Town
    "52511910B92065650444302": ("10017010", "基隆市中正區"),  # Zhongzheng
    "52511910B49246730473855": ("10017020", "基隆市七堵區"),  # Qidu
    "52511910B3088598520620": ("10017030", "基隆市暖暖區"),  # Nuannuan
    "52511910B30709967967550": ("10017040", "基隆市仁愛區"),  # Ren'ai
    "52511910B84130893113897": ("10017050", "基隆市中山區"),  # Zhongshan
    "52511910B26024129556324": ("10017060", "基隆市安樂區"),  # Anle
    "52511910B33100646615087": ("10017070", "基隆市信義區"),  # Xinyi
    "52511910B28036042271757": ("10018010", "新竹市東區"),  # 東區
    "52511910B8569683364670": ("10018020", "新竹市北區"),  # 北區
    "52511910B39021201460320": ("10018030", "新竹市香山區"),  # Xiangshan District
    "52511910B45111644423638": ("10020010", "嘉義市東區"),  # East District
    "52511910B30977236715140": ("10020020", "嘉義市西區"),  # West District
    "52511910B27691000187918": ("63000010", "臺北市松山區"),  # Songshan District
    "52511910B97040583536387": ("63000020", "臺北市信義區"),  # Xinyi District
    "52511910B72557613719767": ("63000030", "臺北市大安區"),  # Da'an District
    "52511910B2433100174245": ("63000040", "臺北市中山區"),  # Zhongshan District
    "52511910B97228601381981": ("63000050", "臺北市中正區"),  # Zhongzheng District
    "52511910B40907976300093": ("63000060", "臺北市大同區"),  # Datong District
    "52511910B53442502489936": ("63000070", "臺北市萬華區"),  # Wanhua District
    "52511910B85672644454395": ("63000080", "臺北市文山區"),  # Wenshan District
    "52511910B46327040282414": ("63000090", "臺北市南港區"),  # Nangang District
    "52511910B60889717547120": ("63000100", "臺北市內湖區"),  # Neihu District
    "52511910B57344020400583": ("63000110", "臺北市士林區"),  # Shilin District
    "52511910B98030585757527": ("63000120", "臺北市北投區"),  # Beitou
    "52511910B3606287647189": ("64000010", "高雄市鹽埕區"),  # Yancheng
    "52511910B97258167764484": ("64000020", "高雄市鼓山區"),  # Gushan
    "52511910B44183742195819": ("64000030", "高雄市左營區"),  # Zuoying
    "52511910B91354507826004": ("64000040", "高雄市楠梓區"),  # Nanzi
    "52511910B99923381863543": ("64000050", "高雄市三民區"),  # Sanmin
    "52511910B42739382471676": ("64000060", "高雄市新興區"),  # Xinxing
    "52511910B68600157990452": ("64000070", "高雄市前金區"),  # Qianjin
    "52511910B57885575775117": ("64000080", "高雄市苓雅區"),  # Lingya
    "52511910B4874504546565": ("64000090", "高雄市前鎮區"),  # Cianjhen
    "52511910B42295955196197": ("64000100", "高雄市旗津區"),  # Qijin
    "52511910B46875128491": ("64000110", "高雄市小港區"),  # Siaogang
    "52511910B45067846009416": ("64000120", "高雄市鳳山區"),  # Fongshan
    "52511910B83654747413473": ("64000130", "高雄市林園區"),  # Linyuan
    "52511910B14985671444346": ("64000140", "高雄市大寮區"),  # Daliao
    "52511910B37639564414460": ("64000150", "高雄市大樹區"),  # Dashu
    "52511910B41569626445575": ("64000160", "高雄市大社區"),  # Dashe
    "52511910B30663215399885": ("64000170", "高雄市仁武區"),  # Renwu
    "52511910B94488542881377": ("64000180", "高雄市鳥松區"),  # Niaosong
    "52511910B81672195550340": ("64000190", "高雄市岡山區"),  # Gangshan
    "52511910B77588417233313": ("64000200", "高雄市橋頭區"),  # Ciaotou
    "52511910B73336698759549": ("64000210", "高雄市燕巢區"),  # Yanchao
    "52511910B51671938708352": ("64000220", "高雄市田寮區"),  # Tianliao
    "52511910B31970606922462": ("64000230", "高雄市阿蓮區"),  # Alian
    "52511910B54132966107148": ("64000240", "高雄市路竹區"),  # Luzhu
    "52511910B24425392494170": ("64000250", "高雄市湖內區"),  # Hunei
    "52511910B54123288304078": ("64000260", "高雄市茄萣區"),  # Jiading
    "52511910B94409074074623": ("64000270", "高雄市永安區"),  # Yong'an
    "52511910B79940153361499": ("64000280", "高雄市彌陀區"),  # Mituo
    "52511910B81270804246754": ("64000290", "高雄市梓官區"),  # Ziguan
    "52511910B19330386236783": ("64000300", "高雄市旗山區"),  # Qishan
    "52511910B30715783231624": ("64000310", "高雄市美濃區"),  # Meinong
    "52511910B66300742055958": ("64000320", "高雄市六龜區"),  # Liouguei
    "52511910B69477070610060": ("64000330", "高雄市甲仙區"),  # Jiasian
    "52511910B90052363141845": ("64000340", "高雄市杉林區"),  # Shanlin
    "52511910B49699122775209": ("64000350", "高雄市內門區"),  # Neimen
    "52511910B8366046265197": ("64000360", "高雄市茂林區"),  # Maolin
    "52511910B89557374460695": ("64000370", "高雄市桃源區"),  # Taoyuan
    "52511910B40932238962124": ("64000380", "高雄市那瑪夏區"),  # Namasia
    "52511910B6389603869041": ("65000010", "新北市板橋區"),  # Banqiao District
    "52511910B68505135665197": ("65000020", "新北市三重區"),  # Sanchong District
    "52511910B21407702399528": ("65000030", "新北市中和區"),  # Zhonghe District
    "52511910B68559401871490": ("65000040", "新北市永和區"),  # Yonghe District
    "52511910B29325635095698": ("65000050", "新北市新莊區"),  # Xinzhuang District
    "52511910B81807770672257": ("65000060", "新北市新店區"),  # Xindian District
    "52511910B57035161982504": ("65000070", "新北市樹林區"),  # Shulin District
    "52511910B16992601244944": ("65000080", "新北市鶯歌區"),  # Yingge District
    "52511910B98629971413037": ("65000090", "新北市三峽區"),  # Sanxia District
    "52511910B49336497562900": ("65000100", "新北市淡水區"),  # Tamsui District
    "52511910B94675128167590": ("65000110", "新北市汐止區"),  # Xizhi District
    "52511910B85706759339541": ("65000120", "新北市瑞芳區"),  # Ruifang District
    "52511910B24789968471650": ("65000130", "新北市土城區"),  # Tucheng District
    "52511910B86675185737242": ("65000140", "新北市蘆洲區"),  # Luzhou District
    "52511910B41832053670190": ("65000150", "新北市五股區"),  # Wugu District
    "52511910B75402986028359": ("65000160", "新北市泰山區"),  # Taishan District
    "52511910B70290379794397": ("65000170", "新北市林口區"),  # Linkou District
    "52511910B54921877123299": ("65000180", "新北市深坑區"),  # Shenkeng District
    "52511910B62556379472396": ("65000190", "新北市石碇區"),  # Shiding District
    "52511910B90991611037176": ("65000200", "新北市坪林區"),  # Pinglin District
    "52511910B22297779295169": ("65000210", "新北市三芝區"),  # Sanzhi District
    "52511910B62922031863482": ("65000220", "新北市石門區"),  # Shimen District
    "52511910B94458762678017": ("65000230", "新北市八里區"),  # Bali District
    "52511910B49041277824691": ("65000240", "新北市平溪區"),  # Pingxi District
    "52511910B77222989775801": ("65000250", "新北市雙溪區"),  # Shuangxi District
    "52511910B24338772487994": ("65000260", "新北市貢寮區"),  # Gongliao District
    "52511910B47117449404442": ("65000270", "新北市金山區"),  # Jinshan District
    "52511910B10855589670933": ("65000280", "新北市萬里區"),  # Wanli District
    "52511910B1435450581762": ("65000290", "新北市烏來區"),  # Wulai District
    "52511910B5845387986633": ("66000010", "臺中市中區"),  # Central District
    "52511910B56209015841977": ("66000020", "臺中市東區"),  # East District
    "52511910B54429610497624": ("66000030", "臺中市南區"),  # South District
    "52511910B31268860247424": ("66000040", "臺中市西區"),  # West District
    "52511910B62562257240113": ("66000050", "臺中市北區"),  # North District
    "52511910B1114695065436": ("66000060", "臺中市西屯區"),  # Xitun District
    "52511910B88737921309662": ("66000070", "臺中市南屯區"),  # Nantun District
    "52511910B1854707671717": ("66000080", "臺中市北屯區"),  # Beitun District
    "52511910B89393531563013": ("66000090", "臺中市豐原區"),  # Fengyuan District
    "52511910B5173446134858": ("66000100", "臺中市東勢區"),  # Dongshi District
    "52511910B39647585180353": ("66000110", "臺中市大甲區"),  # Dajia District
    "52511910B27876515321702": ("66000120", "臺中市清水區"),  # Qingshui District
    "52511910B95956240331763": ("66000130", "臺中市沙鹿區"),  # Shalu District
    "52511910B49492134849249": ("66000140", "臺中市梧棲區"),  # Wuqi District
    "52511910B49637011657057": ("66000150", "臺中市后里區"),  # Houli District
    "52511910B92990516943265": ("66000160", "臺中市神岡區"),  # Shengang District
    "52511910B80553421723016": ("66000170", "臺中市潭子區"),  # Tanzi District
    "52511910B79351211043156": ("66000180", "臺中市大雅區"),  # Daya District
    "52511910B79904820365756": ("66000190", "臺中市新社區"),  # Xinshe District
    "52511910B87526029786391": ("66000200", "臺中市石岡區"),  # Shigang District
    "52511910B37647459697968": ("66000210", "臺中市外埔區"),  # Waipu District
    "52511910B63167976390159": ("66000220", "臺中市大安區"),  # Da'an District
    "52511910B17490321584859": ("66000230", "臺中市烏日區"),  # Wuri District
    "52511910B3092467574862": ("66000240", "臺中市大肚區"),  # Dadu District
    "52511910B23437445078556": ("66000250", "臺中市龍井區"),  # Longjing District
    "52511910B92188863099631": ("66000260", "臺中市霧峰區"),  # Wufeng District
    "52511910B19191805182315": ("66000270", "臺中市太平區"),  # Taiping District
    "52511910B17517272780410": ("66000280", "臺中市大里區"),  # Dali District
    "52511910B1724778943765": ("66000290", "臺中市和平區"),  # Heping District
    "52511910B15727969780764": ("67000010", "臺南市新營區"),  # Xiaying
    "52511910B3549258104854": ("67000020", "臺南市鹽水區"),  # Yanshuei
    "52511910B83755823779571": ("67000030", "臺南市白河區"),  # Baihe
    "52511910B95098417504855": ("67000040", "臺南市柳營區"),  # Liouying
    "52511910B86463604693023": ("67000050", "臺南市後壁區"),  # Houbi
    "52511910B26605642536320": ("67000060", "臺南市東山區"),  # Dongshan
    "52511910B41349980343036": ("67000070", "臺南市麻豆區"),  # Madou
    "52511910B67622492960002": ("67000080", "臺南市下營區"),  # Siaying
    "52511910B9639721186799": ("67000090", "臺南市六甲區"),  # Liujia
    "52511910B66393591343605": ("67000100", "臺南市官田區"),  # Guantian
    "52511910B21548483035565": ("67000110", "臺南市大內區"),  # Danei
    "52511910B43412485397625": ("67000120", "臺南市佳里區"),  # Jiali
    "52511910B13500089926277": ("67000130", "臺南市學甲區"),  # Xuejia
    "52511910B54492038659997": ("67000140", "臺南市西港區"),  # Xigang
    "52511910B14944460308189": ("67000150", "臺南市七股區"),  # Qigu
    "52511910B80613047181881": ("67000160", "臺南市將軍區"),  # Jiangjun
    "52511910B93975188491166": ("67000170", "臺南市北門區"),  # Beimen
    "52511910B47006759189229": ("67000180", "臺南市新化區"),  # Sinhua
    "52511910B12240276172675": ("67000190", "臺南市善化區"),  # Shanhua
    "52511910B52040400722593": ("67000200", "臺南市新市區"),  # Xinshi
    "52511910B27035674370402": ("67000210", "臺南市安定區"),  # Anding
    "52511910B49735999236113": ("67000220", "臺南市山上區"),  # Shanshang
    "52511910B65003852157868": ("67000230", "臺南市玉井區"),  # Yujing
    "52511910B12166681712059": ("67000240", "臺南市楠西區"),  # Nanxi
    "52511910B59203276225690": ("67000250", "臺南市南化區"),  # Nanhua
    "52511910B71538284073489": ("67000260", "臺南市左鎮區"),  # Zuozhen
    "52511910B2226983620167": ("67000270", "臺南市仁德區"),  # Rende
    "52511910B83187520966287": ("67000280", "臺南市歸仁區"),  # Guiren
    "52511910B37391519791178": ("67000290", "臺南市關廟區"),  # Guanmiao
    "52511910B87738681480797": ("67000300", "臺南市龍崎區"),  # Longqi
    "52511910B38482668702502": ("67000310", "臺南市永康區"),  # Yongkang
    "52511910B558444185686": ("67000320", "臺南市東區"),  # Eastern District
    "52511910B45186727587827": ("67000330", "臺南市南區"),  # South District
    "52511910B67503722299641": ("67000340", "臺南市北區"),  # North District
    "52511910B51634678228857": ("67000350", "臺南市安南區"),  # Annan
    "52511910B44653158831279": ("67000360", "臺南市安平區"),  # Anping
    "52511910B28476693424992": ("67000370", "臺南市中西區"),  # West Central District
    "52511910B36399926613491": ("68000010", "桃園市桃園區"),  # Taoyuan District
    "52511910B96194264601254": ("68000020", "桃園市中壢區"),  # Zhongli District
    "52511910B95362195406961": ("68000030", "桃園市大溪區"),  # Daxi District
    "52511910B40704082736400": ("68000040", "桃園市楊梅區"),  # Yangmei District
    "52511910B98838605252897": ("68000050", "桃園市蘆竹區"),  # Luzhu District
    "52511910B2055603825455": ("68000060", "桃園市大園區"),  # Dayuan District
    "52511910B79239618011253": ("68000070", "桃園市龜山區"),  # Guishan District
    "52511910B50474008293669": ("68000080", "桃園市八德區"),  # Bade District
    "52511910B47715712995546": ("68000090", "桃園市龍潭區"),  # Longtan District
    "52511910B6162382764157": ("68000100", "桃園市平鎮區"),  # Pingzhen District
    "52511910B75183314272458": ("68000110", "桃園市新屋區"),  # Xinwu District
    "52511910B57239711193520": ("68000120", "桃園市觀音區"),  # Guanyin District
    "52511910B10215199478646": ("68000130", "桃園市復興區"),  # Fuxing District
}


if __name__ == "__main__":
    raise SystemExit(main())
