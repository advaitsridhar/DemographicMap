#!/usr/bin/env python3
"""South Korea: religion by province and district, from the 2015 census.

Korea's census asks religion in the years ending in 5: the register-based
census counts everyone from the registers, and its sample survey enumerates a
fifth of households in the field and asks them; Statistics Korea publishes
the answers weighted to the whole population. The 2015 round's table by city, county and district is KOSIS
DT_1PM1502 (성, 연령 및 종교별 인구 - 시군구). KOSIS's viewer builds it in the
browser, but the table's bulk download (대용량 다운로드) is one file:
mass_list.jsp lists it as a hidden input ``file_data_0`` ("5581/
101_DT_1PM1502_F_2015"); the page's own fileDown() asks mass_down_seq.jsp for a
download number and then posts the same form to /file_mass/file_down.jsp. That
answers a zip holding one cp949 CSV of every area by sex, age and religion.
This reads the rows for both sexes and all ages together, and keeps only those
(``KEPT``), so a later run needs no network.

**The table.** One row per area: the nation, its urban and rural parts (동부,
읍부, 면부), the 17 provinces with their own urban and rural parts, every city,
county and autonomous district (a five-figure code ending in 0), and the
districts inside a city (수원시 장안구: a code ending 1 to 9). Columns: 계 (the
population the table covers), 종교있음-계 (with a religion) and its nine
religions, and 종교없음-계 (no religion).

**Checks**, each a refusal: in every row the nine religions add up to 종교있음
and that with 종교없음 to 계; the nation's urban and rural parts add up to it;
the provinces add up to the nation and every province's cities, counties and
districts to the province; a city's districts add up to the city; and the
nation's figures are the ones Statistics Korea published for the round
(``NATIONAL``).

**Binding** is ``korea_nationality``'s crosswalk, by province and the district's
own name, with the two names the 2015 table writes otherwise: Incheon's Nam-gu,
renamed Michuhol-gu in 2018, and Sejong, which the table calls 세종시. Gunwi
was North Gyeongsang's until July 2023, so in 2015 it is counted there, which
is also where the boundary file draws it; the map files it under Daegu, as
the register does now, and its note says when it moved (``MOVED_SINCE``).
The drawn units are read keyed by either province of a district the boundary
file draws in another's polygon. Jeonnam's Yeonggwang-gun has no
polygon and counts only towards its province.

**Labels.** The census's religions in the map's words. Daesun Jinrihoe
(41,176 people nationally) and Daejongism (3,101) are joined to 'Other
religions', the table's own 기타, as the group tree places neither; the note
gives the numbers.

Usage:
    python -m scripts.fetch_census.korea_religion            # reads the kept rows, or fetches
    python -m scripts.fetch_census.korea_religion --fetch     # fetches afresh
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .east_asia_common import drawn, hundred
from .korea_nationality import (
    DISTRICTS, DRAWN_ELSEWHERE, KEEP, SIDO, UNDRAWN, drawn_where, either_parent,
)

OUT = "korea_religion.json"
YEAR = 2015
# A district counted in another province in 2015 than the one the map files
# it under now, and what the note says of it.
MOVED_SINCE: dict[tuple[str, str], str] = {
    ("North Gyeongsang", "Gunwi-gun"): (
        "In 2015 Gunwi-gun was a county of North Gyeongsang, and this census counts it "
        "there; it has been part of Daegu since July 2023."),
}
ORG, TABLE = "101", "DT_1PM1502"
PAGE = f"https://kosis.kr/statHtml/statHtml.do?orgId={ORG}&tblId={TABLE}"
MASS = "https://kosis.kr/statisticsList/mass/"
DOWN = "https://kosis.kr/file_mass/file_down.jsp"
KEPT = KEEP / f"kosis_{TABLE}_{YEAR}_totals.json"
UA = ("DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
      "python-urllib")
SOURCE = ("Statistics Korea, 2015 Population and Housing Census, sample survey: population by "
          "sex, age and religion, by city, county and district (KOSIS DT_1PM1502, 성, 연령 및 "
          "종교별 인구 - 시군구)")
LICENCE = "Korea Open Government License Type 1 (공공누리 제1유형): attribution"

# The table's columns, in the map's words. 계 and the two subtotals are
# checked and not written.
TOTAL, RELIGIOUS, NONE = "계", "종교있음-계", "종교없음-계"
RELIGIONS: dict[str, str] = {
    "불교": "Buddhism", "기독교(개신교)": "Protestant", "기독교(천주교)": "Roman Catholic",
    "원불교": "Won Buddhism", "유교": "Confucianism", "천도교": "Cheondoism",
    "대순진리회": "Daesun Jinrihoe", "대종교": "Daejongism", "기타": "Other religions",
}
POOLED = ("Daesun Jinrihoe", "Daejongism")       # joined to "Other religions"
NO_RELIGION = "No religion"

# The nation as Statistics Korea published the round (보도자료, 19 December
# 2016: 종교 있음 2,155만 4천 명, 43.9%), to the person.
NATIONAL = {TOTAL: 49_052_389, RELIGIOUS: 21_553_674, NONE: 27_498_715}

# Names the 2015 table writes for units the crosswalk knows by today's name.
NAMES_2015: dict[tuple[str, str], str] = {
    ("Incheon", "남구"): "미추홀구",                   # renamed Michuhol-gu, 1 July 2018
    ("Sejong", "세종시"): "세종특별자치시",
}
URBAN_RURAL = ("03", "04", "05")                  # 동부, 읍부, 면부

RELIGION_NOTE = (
    "Statistics Korea's 2015 census counted everyone from the registers and asked religion in "
    "its sample survey, which enumerated a fifth of households in the field; the answers are "
    "published weighted to the whole population (KOSIS DT_1PM1502), and the "
    "table counts {total:,} people here, {religious:,} with a religion and {none:,} with none. "
    "The question is asked in the years ending in 5; KOSIS's table by district holds the 2015 "
    "round.{pooled}{where}")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def form_fields(text: str, name: str) -> dict[str, str]:
    """The inputs of the form called ``name``, as {name: value}."""
    for form in re.finditer(r"(?is)<form\b([^>]*)>(.*?)</form>", text):
        if re.search(rf"""\bname\s*=\s*["']{re.escape(name)}["']""", form.group(1)):
            out = {}
            for tag in re.finditer(r"(?is)<input\b([^>]*)>", form.group(2)):
                attrs = dict((k.lower(), a or b) for k, a, b in re.findall(
                    r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""", tag.group(1)))
                if attrs.get("name"):
                    out[attrs["name"]] = attrs.get("value", "")
            return out
    return {}


def kosis_mass(org: str, table: str, row: int = 0) -> bytes:
    """A KOSIS table's bulk file, fetched the way its download page's own
    script fetches it, with one cookie jar: mass_list.jsp's file_data_N gives
    "number/name"; fileDown() copies both into the upfrm form, submits it to
    mass_down_seq.jsp, whose answer calls setDownNo(n), and then submits the
    same form to /file_mass/file_down.jsp with file_type ONE, down_cnt 1 and
    use_no n."""
    import http.cookiejar
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(url: str, fields: dict[str, str] | None, referer: str | None) -> bytes:
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        headers = {"User-Agent": UA, **({"Referer": referer} if referer else {})}
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        last: Exception | None = None
        for attempt in range(3):
            try:
                with opener.open(req, timeout=300) as resp:
                    return resp.read()
            except urllib.error.HTTPError:
                raise
            except Exception as exc:  # noqa: BLE001 - kosis.kr times out now and then
                last = exc
                log(f"  retry {attempt + 1}/3 :: {url} :: {exc!r}")
                time.sleep(10 * (attempt + 1))
        raise SystemExit(f"korea_religion: {url} did not answer: {last!r}")

    listing = (f"{MASS}mass_list.jsp?org_id={org}&tbl_id={table}&vw_cd=MT_ZTITLE&list_id="
               "&process=statHtml")
    text = call(listing, None, None).decode("utf-8", "replace")
    entry = form_fields(text, "myfrm").get(f"file_data_{row}")
    up = form_fields(text, "upfrm")
    if not entry or not up:
        raise SystemExit(f"korea_religion: {listing} lists no file_data_{row} or no upfrm form")
    number, _, name = entry.partition("/")
    up.update({"filename": name, "file_no": number})
    seq = call(f"{MASS}mass_down_seq.jsp", up, listing).decode("utf-8", "replace")
    found = re.search(r"setDownNo\(\s*['\"]?(\d+)", seq)
    if not found:
        raise SystemExit("korea_religion: mass_down_seq.jsp gave no download number")
    up.update({"file_type": "ONE", "down_cnt": "1", "use_no": found.group(1)})
    blob = call(DOWN, up, listing)
    log(f"  {name}: {len(blob):,} bytes from {DOWN}")
    return blob


def totals_rows(blob: bytes) -> list[list[str]]:
    """The CSV inside the zip, as rows, keeping the header and the rows for
    both sexes (성별 0) and all ages (연령별 000)."""
    if blob[:2] != b"PK":
        raise SystemExit(f"korea_religion: the download is not a zip: {blob[:60]!r}")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        members = [i for i in zf.infolist() if i.filename.lower().endswith(".csv")]
        if len(members) != 1:
            raise SystemExit(f"korea_religion: the zip holds {zf.namelist()}")
        text = zf.read(members[0]).decode("cp949").lstrip("﻿")
    rows = list(csv.reader(io.StringIO(text)))
    head = next((i for i, r in enumerate(rows) if r and r[0].startswith("C행정구역별")), None)
    if head is None:
        raise SystemExit("korea_religion: no header row starting C행정구역별")
    keep = [rows[head]]
    for row in rows[head + 1:]:
        if len(row) > 5 and row[2].lstrip("'") == "0" and row[4].lstrip("'") == "000":
            keep.append(row)
    return keep


def fetch() -> list[list[str]]:
    rows = totals_rows(kosis_mass(ORG, TABLE))
    KEPT.parent.mkdir(parents=True, exist_ok=True)
    KEPT.write_text(json.dumps(rows, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"  kept {KEPT.name}: {len(rows) - 1} areas")
    return rows


def load(refresh: bool = False) -> list[list[str]]:
    if not refresh and KEPT.exists():
        log(f"  reading the kept {KEPT.name}")
        return json.loads(KEPT.read_text(encoding="utf-8"))
    return fetch()


# ---------------------------------------------------------------------------
# Reading and checking
# ---------------------------------------------------------------------------

def number(cell: str) -> int:
    value = float(cell.replace(",", "").strip() or 0)
    if value != int(value):
        raise SystemExit(f"korea_religion: {cell!r} is not a whole number of people")
    return int(value)


def read(rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    """{area code: {"name", "counts": {column: people}}}, after the row checks."""
    header = [h.strip() for h in rows[0]]
    wanted = [TOTAL, RELIGIOUS, *RELIGIONS, NONE]
    missing = [w for w in wanted if w not in header]
    if missing:
        raise SystemExit(f"korea_religion: the header lacks {missing}: {header}")
    year_col = header.index("시점")
    out: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        code, name = row[0].lstrip("'").strip(), row[1].strip()
        if row[year_col].strip() != str(YEAR):
            raise SystemExit(f"korea_religion: {name} is for {row[year_col]}, not {YEAR}")
        counts = {w: number(row[header.index(w)]) for w in wanted}
        named = sum(counts[k] for k in RELIGIONS)
        if named != counts[RELIGIOUS]:
            raise SystemExit(f"korea_religion: {name} ({code}): the religions add to {named:,}, "
                             f"종교있음 is {counts[RELIGIOUS]:,}")
        if counts[RELIGIOUS] + counts[NONE] != counts[TOTAL]:
            raise SystemExit(f"korea_religion: {name} ({code}): with and without a religion "
                             f"make {counts[RELIGIOUS] + counts[NONE]:,}, not {counts[TOTAL]:,}")
        if code in out:
            raise SystemExit(f"korea_religion: {code} appears twice")
        out[code] = {"name": name, "counts": counts}
    return out


def add(cells: list[dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for cell in cells:
        for k, v in cell.items():
            out[k] = out.get(k, 0) + v
    return out


def classify(areas: dict[str, dict[str, Any]]
             ) -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """({province code: province}, {province code: [its city, county and
    district codes]}, {city code: [its districts' codes]}), after checking
    that every part adds up to its whole."""
    def sums_to(whole: str, parts: list[str], what: str) -> None:
        summed = add([areas[p]["counts"] for p in parts])
        if summed != areas[whole]["counts"]:
            diff = {k: summed[k] - areas[whole]["counts"][k] for k in summed
                    if summed[k] != areas[whole]["counts"][k]}
            raise SystemExit(f"korea_religion: {what} of {areas[whole]['name']} miss it: {diff}")

    if "00" not in areas:
        raise SystemExit("korea_religion: no national row")
    if {k: areas["00"]["counts"][k] for k in NATIONAL} != NATIONAL:
        raise SystemExit(f"korea_religion: the nation counts {areas['00']['counts']}, "
                         f"not the published {NATIONAL}")
    sums_to("00", list(URBAN_RURAL), "the urban and rural parts")
    provinces = {c: SIDO.get(a["name"], "") for c, a in areas.items()
                 if len(c) == 2 and c not in ("00", *URBAN_RURAL)}
    unknown = [areas[c]["name"] for c, p in provinces.items() if not p]
    if unknown or len(provinces) != 17:
        raise SystemExit(f"korea_religion: {len(provinces)} provinces; unknown {unknown}")
    sums_to("00", list(provinces), "the provinces")
    districts: dict[str, list[str]] = {c: [] for c in provinces}
    gu: dict[str, list[str]] = {}
    for code in areas:
        if len(code) != 5:
            if len(code) != 2:
                raise SystemExit(f"korea_religion: an area code {code!r} of neither length")
            continue
        if code[:2] not in provinces:
            raise SystemExit(f"korea_religion: {code} is in no province")
        if code[2:] in ("003", "004", "005"):
            continue                              # the province's urban and rural parts
        if code.endswith("0"):
            districts[code[:2]].append(code)
        else:
            gu.setdefault(code[:4] + "0", []).append(code)
    for province, codes in districts.items():
        sums_to(province, codes, "the cities, counties and districts")
    for city, codes in gu.items():
        if city not in areas:
            raise SystemExit(f"korea_religion: districts {codes} of a city {city} not listed")
        sums_to(city, codes, "the districts")
    return provinces, districts, gu


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def composition(counts: dict[str, int]) -> tuple[list[dict[str, Any]], str]:
    """The shares, and the sentence saying what 'Other religions' holds."""
    groups: dict[str, int] = {}
    held: list[str] = []
    for column, label in RELIGIONS.items():
        if label in POOLED:
            if counts[column]:
                held.append(f"{label} ({counts[column]:,})")
            label = "Other religions"
        groups[label] = groups.get(label, 0) + counts[column]
    groups[NO_RELIGION] = counts[NONE]
    # Said as what the figures are, not as a limit of this map's labels.
    note = (f" 'Other religions' joins the table's own 기타 ('other') with "
            f"{' and '.join(held)}, which the census counts apart." if held else "")
    return hundred(groups), note


def unit_record(rid: str, name: str, *, level: str, parent: str, shape: str,
                counts: dict[str, int], where: str = "") -> dict[str, Any]:
    shares, pooled = composition(counts)
    return record(
        rid, name, level=level, parent=parent, country="KOR",
        match_by="shape_id", shape_id=shape,
        religion=shares, religion_year=YEAR, religion_basis="self-identification",
        religion_note=RELIGION_NOTE.format(total=counts[TOTAL], religious=counts[RELIGIOUS],
                                           none=counts[NONE], pooled=pooled,
                                           where=f" {where}" if where else ""),
        sources=[{"field": "religion", "name": SOURCE, "url": PAGE, "year": YEAR,
                  "license": LICENCE}])


def build(rows: list[list[str]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    areas = read(rows)
    provinces, districts, gu = classify(areas)
    log(f"  {len(areas)} areas: 17 provinces, {sum(map(len, districts.values()))} cities, "
        f"counties and districts, {sum(map(len, gu.values()))} districts of cities; every part "
        "adds up to its whole")
    province_shapes = {u["name"]: u["id"] for u in admin1}
    names1 = {u["id"]: u["name"] for u in admin1}
    district_shapes: dict[tuple[str, str], str] = {}
    for u in admin2:
        key = (names1.get(u.get("parent"), ""), u["name"])
        if key in district_shapes:
            raise SystemExit(f"korea_religion: two drawn units are {key}")
        district_shapes[key] = u["id"]
    # A district drawn in another province's polygon, by either province.
    district_shapes = either_parent(district_shapes)
    records: list[dict[str, Any]] = []
    for code, province in sorted(provinces.items(), key=lambda kv: kv[1]):
        if province not in province_shapes:
            raise SystemExit(f"korea_religion: no drawn province called {province!r}")
        records.append(unit_record(f"KOR-{province}", province, level="admin1", parent="KOR",
                                   shape=province_shapes[province],
                                   counts=areas[code]["counts"]))
    bound: dict[str, str] = {}
    for pcode, codes in districts.items():
        province = provinces[pcode]
        for code in codes:
            word = areas[code]["name"]
            word = NAMES_2015.get((province, word), word)
            name = DISTRICTS.get(province, {}).get(word)
            if name is None:
                if (province, word) in UNDRAWN:
                    log(f"  {province} {word}: no polygon; counted in its province only")
                    continue
                raise SystemExit(f"korea_religion: the crosswalk does not know {province} {word}")
            under = DRAWN_ELSEWHERE.get((province, name), province)
            shape = district_shapes.get((under, name))
            if shape is None:
                raise SystemExit(f"korea_religion: no drawn unit {name!r} under {under or 'KOR'}")
            if shape in bound:
                raise SystemExit(f"korea_religion: {shape} is bound to {bound[shape]} and {code}")
            bound[shape] = code
            where = drawn_where(name, province, under) if under != province else ""
            if (province, name) in MOVED_SINCE:
                where = (where + " " if where else "") + MOVED_SINCE[(province, name)]
            records.append(unit_record(f"KOR-{province}-{name}", name, level="admin2",
                                       parent=f"KOR-{province}", shape=shape,
                                       counts=areas[code]["counts"], where=where))
    missing = sorted(k for k, v in district_shapes.items() if v not in bound)
    if missing:
        raise SystemExit(f"korea_religion: drawn districts with no row: {missing}")
    none = [r["religion"] for r in records if r["level"] == "admin2"]
    share = sorted(next(g["pct"] for g in r if g["group"] == NO_RELIGION) for r in none)
    log(f"  {len(records)} records: 17 provinces and {len(none)} districts; no religion "
        f"{share[0]}-{share[-1]}% across districts")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="fetch the table afresh")
    args = ap.parse_args()
    log(f"korea_religion: {SOURCE}")
    records = build(load(args.fetch), drawn("KOR", "admin1"), drawn("KOR", "admin2"))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
