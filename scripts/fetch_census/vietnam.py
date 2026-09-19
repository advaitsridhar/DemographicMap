#!/usr/bin/env python3
"""Viet Nam: ethnicity by province from the 2019 census, read from the
office's own results volume.

The 2019 Population and Housing Census counted every province's people by
ethnic group (Kinh and the 53 recognised minorities) and by religion. The
English results volume that UNFPA co-published prints both for the country
only, and that is where an earlier pass stopped (docs/SOURCES.md, "Viet
Nam"). The Vietnamese volume -- "Kết quả toàn bộ Tổng điều tra dân số và
nhà ở năm 2019", 842 pages, Nhà xuất bản Thống kê 2020 -- is the full one:
its Table 2 is "Dân số theo dân tộc, thành thị/nông thôn, giới tính, vùng
kinh tế - xã hội và tỉnh/thành phố", population by ethnic group, urban/rural,
sex, socio-economic region **and province**, pages 43 to 209. Under each
province it prints all 54 groups, then foreign nationals and the
undetermined, each with Total, Male and Female for the whole, the urban and
the rural population. Its Table 3, religion, is for the country only, so
religion is not written here and the record says nothing about it.

The volume sits on the statistics office's renamed host, ``nso.gov.vn``,
which answered a plain client on 19 September 2026 where it had reset the
socket in early September; ``gso.gov.vn`` no longer resolves at all. It
was found by the owner's decision of that day to read the provincial table
from whichever route yields it, and this is the first route -- the
office's own file -- so no secondary source is involved. ``--probe`` keeps
the reconnaissance that found it: the office's pages, Kaggle's catalogue
(nothing for Viet Nam under six phrases) and the Vietnamese Wikipedia
(2009 prose in the province articles, and the Điện Biên article's citation
of this very volume for a 2019 provincial figure, which is what said the
table existed).

**Reading a row.** The volume prints figures with a space as the thousands
separator, so "8 053 663 3 991 919 4 061 744" is three numbers and nothing
in the text says where one ends. Every row carries nine figures --
Total, Male, Female for all, urban and rural -- and the publisher's own
arithmetic decides the split: Male plus Female must equal Total three
times over, and urban plus rural must equal the whole. A row with no
single split satisfying that is refused, with the row in the log. A dash
is a zero.

**Self-checks**, each of which refuses the run rather than writing:

* within every unit the 56 rows must add to the unit's own total;
* the 63 provinces' Kinh must add to the national Kinh, 82,085,826 of
  96,208,984, within half a percent (they add exactly);
* every province must be read, and no row may carry a label this reader
  does not know, so a page the text extraction garbles is a refusal and
  not a silent gap.

Shares are re-rounded to one decimal by largest remainder so each province
adds to exactly 100. A group under 0.05% of a province is folded into
"Other ethnic groups", together with foreign nationals and the census's
"không xác định" (undetermined), and the note says so.

Usage:
    python -m scripts.fetch_census.vietnam
    python -m scripts.fetch_census.vietnam --probe --routes acp
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, RAW, download, http_json, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

OUT = "vietnam_province.json"
YEAR = 2019
USER_AGENT = ("Mozilla/5.0 (compatible; DemographicMap/1.0; "
              "+https://github.com/advaitsridhar/DemographicMap)")
MAIN_PDF = ("https://www.nso.gov.vn/wp-content/uploads/2019/12/"
            "Ket-qua-toan-bo-Tong-dieu-tra-dan-so-va-nha-o-2019.pdf")
SOURCE = ("General Statistics Office of Viet Nam, Kết quả toàn bộ Tổng điều tra dân số "
          "và nhà ở năm 2019 (Completed Results of the 2019 Viet Nam Population and "
          "Housing Census), Table 2: population by ethnic group, urban/rural, sex, "
          "socio-economic region and province/city, 1 April 2019")
LICENCE = ("Official statistics of the General Statistics Office of Viet Nam (the "
           "National Statistics Office since 2025), Nhà xuất bản Thống kê 2020, "
           "cited as published")
NOTE = ("Counts as the census printed them for the province, read from Table 2 of "
        "the office's own Vietnamese results volume (pages 43-209), which crosses "
        "ethnic group with province; the English volume prints the same breakdown "
        "for the country only. Shares are the counts over the province's total, "
        "re-rounded to add to 100. 'Other ethnic groups' holds every group under "
        "0.05% of the province, together with foreign nationals ('người nước "
        "ngoài') and the census's undetermined ('không xác định'). Religion is not "
        "written: the volume's Table 3 gives it for the country only.")

# The published national figures, for the check across provinces.
NATIONAL_TOTAL = 96_208_984
NATIONAL_KINH = 82_085_826
KINH_TOLERANCE = 0.005
MIN_SHARE = 0.05          # a group below this share of the province goes to the residual
RESIDUAL = "Other ethnic groups"
NOT_A_GROUP = {"nguoinuocngoai", "khongxacdinh"}   # foreign nationals, undetermined

# The 63 provinces as the boundary file names them, with the spellings
# other sources use. The volume's own labels are matched to these after
# folding the diacritics, so "Hoà Bình" and "Hòa Bình" are one key.
PROVINCES: dict[str, list[str]] = {
    "An Giang": [], "Bà Rịa–Vũng Tàu": ["Bà Rịa - Vũng Tàu", "Ba Ria-Vung Tau"],
    "Bình Dương": [], "Bình Phước": [], "Bình Thuận": [], "Bình Định": [],
    "Bạc Liêu": [], "Bắc Giang": [], "Bắc Kạn": ["Bắc Cạn"], "Bắc Ninh": [],
    "Bến Tre": [], "Cao Bằng": [], "Cà Mau": [], "Cần Thơ": [], "Gia Lai": [],
    "Ho Chi Minh": ["Hồ Chí Minh", "Ho Chi Minh City", "Thành phố Hồ Chí Minh",
                    "TP. Hồ Chí Minh", "Saigon", "Sài Gòn"],
    "Hà Giang": [], "Hà Nam": [], "Hà Nội": ["Hanoi", "Ha Noi"], "Hà Tĩnh": [],
    "Hòa Bình": ["Hoà Bình"], "Hưng Yên": [], "Hải Dương": [], "Hải Phòng": ["Haiphong"],
    "Hậu Giang": [], "Khánh Hòa": ["Khánh Hoà"], "Kiên Giang": [], "Kon Tum": [],
    "Lai Châu": [], "Long An": [], "Lào Cai": [], "Lâm Đồng": [], "Lạng Sơn": [],
    "Nam Định": [], "Nghệ An": [], "Ninh Bình": [], "Ninh Thuận": [], "Phú Thọ": [],
    "Phú Yên": [], "Quảng Bình": [], "Quảng Nam": [], "Quảng Ngãi": [], "Quảng Ninh": [],
    "Quảng Trị": [], "Sóc Trăng": [], "Sơn La": [], "Thanh Hóa": ["Thanh Hoá"],
    "Thái Bình": [], "Thái Nguyên": [],
    "Thừa Thiên Huế": ["Thừa Thiên - Huế", "Thừa Thiên-Huế", "Huế"],
    "Tiền Giang": [], "Trà Vinh": [], "Tuyên Quang": [], "Tây Ninh": [], "Vĩnh Long": [],
    "Vĩnh Phúc": [], "Yên Bái": [], "Điện Biên": [], "Đà Nẵng": ["Da Nang", "Danang"],
    "Đắk Lắk": ["Đăk Lăk", "Dak Lak"], "Đắk Nông": ["Đăk Nông", "Dak Nong"],
    "Đồng Nai": [], "Đồng Tháp": [],
}
# The volume's other units: the country and the six socio-economic
# regions. Read and checked like a province, and not written.
COUNTRY = ["Toàn quốc", "Cả nước", "Tổng số", "Việt Nam", "Total", "Whole country"]
REGIONS = ["Đồng bằng sông Hồng", "Trung du và miền núi phía Bắc",
           "Bắc Trung Bộ và Duyên hải miền Trung", "Tây Nguyên", "Đông Nam Bộ",
           "Đồng bằng sông Cửu Long"]
# The 54 groups as the 2019 list spells them, with the spellings the
# volume or the literature also use; matched after folding, so "Gié
# Triêng", "Giẻ Triêng" and "Gié-Triêng" are one key. A row with any other
# label refuses the run.
GROUPS = [
    "Kinh", "Tày", "Thái", "Hoa", "Khmer", "Mường", "Nùng", "Mông", "H'Mông", "Dao",
    "Gia Rai", "Ngái", "Ê Đê", "Ba Na", "Xơ Đăng", "Sán Chay", "Cơ Ho", "Chăm",
    "Sán Dìu", "Hrê", "Mnông", "M'Nông", "Raglay", "Ra Glai", "Xtiêng", "X'Tiêng",
    "Bru Vân Kiều", "Bru-Vân Kiều", "Thổ", "Giáy", "Cơ Tu", "Gié Triêng", "Giẻ Triêng",
    "Mạ", "Khơ Mú", "Co", "Tà Ôi", "Chơ Ro", "Kháng", "Xinh Mun", "Hà Nhì", "Chu Ru",
    "Lào", "La Chí", "La Ha", "Phù Lá", "La Hủ", "Lự", "Lô Lô", "Chứt", "Mảng",
    "Pà Thẻn", "Cơ Lao", "Cờ Lao", "Cống", "Bố Y", "Si La", "Pu Péo", "Brâu", "Ơ Đu",
    "Rơ Măm", "Người nước ngoài", "Không xác định",
]
UNIT_PREFIX = re.compile(r"^(?:tp\.?|thành phố|tỉnh)\s+", re.IGNORECASE)


def fold(text: str) -> str:
    """A label reduced to its letters, without diacritics: what two
    spellings of one Vietnamese name agree on."""
    text = unicodedata.normalize("NFKD", text.lower()).replace("đ", "d")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c for c in text if c.isalnum())


PROVINCE_KEYS = {fold(k): name for name, others in PROVINCES.items() for k in [name, *others]}
COUNTRY_KEYS = {fold(k) for k in COUNTRY}
REGION_KEYS = {fold(k) for k in REGIONS}
GROUP_KEYS = {fold(k) for k in GROUPS}
# A row is a label and then at least nine tokens of digits or dashes: nine
# figures, each of one or more groups. Fewer is a heading -- the table's
# first page is headed "Biểu - Table 2", and that trailing 2 is not a figure.
ROW = re.compile(r"^\s*(?P<label>[^\d]*?[^\W\d][^\d]*?)\s+"
                 r"(?P<tail>(?:(?:\d{1,3}|-)\s+){8,}(?:\d{1,3}|-))\s*$")


def figures(tokens: list[str]) -> list[int]:
    """The nine figures of a row, from its digit groups, by the publisher's
    own arithmetic.

    "8 053 663 3 991 919" is tokens ['8', '053', '663', '3', '991', '919'],
    and nothing in the text says where one number ends. A number is a
    group of one to three digits followed by any run of three-digit groups,
    so every split into nine numbers is tried, and the one kept is the one
    where Total = Male + Female for the whole, the urban and the rural
    columns and the whole = urban + rural. A dash is a zero. Exactly one
    split must satisfy that; none or several refuses the row.
    """
    out: list[list[int]] = []

    def walk(i: int, acc: list[int]) -> None:
        if len(acc) == 9:
            if i == len(tokens) and consistent(acc):
                out.append(acc)
            return
        if i >= len(tokens):
            return
        tok = tokens[i]
        if tok == "-":
            walk(i + 1, [*acc, 0])
            return
        if not re.fullmatch(r"\d{1,3}", tok):
            return
        value, j = int(tok), i + 1
        walk(j, [*acc, value])
        while j < len(tokens) and re.fullmatch(r"\d{3}", tokens[j]):
            value = value * 1000 + int(tokens[j])
            j += 1
            walk(j, [*acc, value])

    walk(0, [])
    if len(out) != 1:
        raise SystemExit(f"vietnam: {len(out)} readings of the row {' '.join(tokens)!r} "
                         "satisfy Total = Male + Female and whole = urban + rural; "
                         "the row cannot be read")
    return out[0]


def consistent(n: list[int]) -> bool:
    return (n[0] == n[1] + n[2] and n[3] == n[4] + n[5] and n[6] == n[7] + n[8]
            and n[0] == n[3] + n[6])


def label_of(text: str) -> str:
    return " ".join(text.split())


def classify(label: str) -> tuple[str, str]:
    """("province", name) | ("country", key) | ("region", key) | ("group", key)."""
    key = fold(UNIT_PREFIX.sub("", label))
    if key in PROVINCE_KEYS:
        return "province", PROVINCE_KEYS[key]
    if key in COUNTRY_KEYS:
        return "country", key
    if key in REGION_KEYS:
        return "region", key
    key = fold(label)
    if key in GROUP_KEYS:
        return "group", key
    raise SystemExit(f"vietnam: the row label {label!r} is neither a unit nor one of "
                     "the 54 groups this reader knows; the table changed or the "
                     "text extraction garbled it")


def is_table_2(page: str) -> bool:
    """A page of Table 2: its head names the table and its column header
    says "Ethnic group and administration", which no other table's does."""
    head = "\n".join(page.splitlines()[:8])
    return bool(re.search(r"(?:Table|Biểu)\s*2\b", head)) and "Ethnic group" in head


def parse(pages: list[str]) -> list[dict[str, Any]]:
    """Every unit of Table 2 with its rows: {"kind", "name", "label", "total",
    "male", "female", "groups": {label: total}, "page"}, in the volume's order."""
    units: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for number, page in enumerate(pages, 1):
        if not is_table_2(page):
            continue
        for line in page.splitlines():
            m = ROW.match(line)
            if not m:
                continue
            label = label_of(m.group("label"))
            kind, key = classify(label)
            n = figures(m.group("tail").split())
            if kind == "group":
                if current is None:
                    raise SystemExit(f"vietnam: page {number} prints {label!r} before any "
                                     "province, region or country row")
                if label in current["groups"]:
                    raise SystemExit(f"vietnam: {current['name']!r} prints {label!r} twice")
                current["groups"][label] = n[0]
                continue
            current = {"kind": kind, "name": key, "label": label, "total": n[0],
                       "male": n[1], "female": n[2], "groups": {}, "page": number}
            units.append(current)
    return units


def check_units(units: list[dict[str, Any]]) -> None:
    for u in units:
        added = sum(u["groups"].values())
        if added != u["total"]:
            raise SystemExit(f"vietnam: {u['label']!r} (page {u['page']}) prints a total of "
                             f"{u['total']:,} and its {len(u['groups'])} rows add to "
                             f"{added:,} ({added - u['total']:+,})")
        if u["kind"] == "province" and len(u["groups"]) < 54:
            raise SystemExit(f"vietnam: {u['label']!r} (page {u['page']}) has "
                             f"{len(u['groups'])} rows, fewer than the 54 groups")


def check_national(units: list[dict[str, Any]]) -> None:
    provinces = [u for u in units if u["kind"] == "province"]
    names = [u["name"] for u in provinces]
    missing = sorted(set(PROVINCES) - set(names))
    twice = sorted({n for n in names if names.count(n) > 1})
    if missing or twice:
        raise SystemExit(f"vietnam: {len(provinces)} provinces read of {len(PROVINCES)}; "
                         f"missing {missing}; read twice {twice}")
    kinh = sum(kinh_of(u) for u in provinces)
    total = sum(u["total"] for u in provinces)
    for what, got, want in (("Kinh", kinh, NATIONAL_KINH), ("population", total, NATIONAL_TOTAL)):
        if abs(got - want) > KINH_TOLERANCE * want:
            raise SystemExit(f"vietnam: the provinces' {what} adds to {got:,}, against the "
                             f"published national {want:,} ({got - want:+,})")
    country = [u for u in units if u["kind"] == "country"]
    if country and (country[0]["total"] != total or kinh_of(country[0]) != kinh):
        raise SystemExit(f"vietnam: the volume's own national row ({country[0]['total']:,}, "
                         f"Kinh {kinh_of(country[0]):,}) disagrees with the provinces' sum "
                         f"({total:,}, Kinh {kinh:,})")
    log(f"  provinces add to {total:,} people and {kinh:,} Kinh; published "
        f"{NATIONAL_TOTAL:,} and {NATIONAL_KINH:,}"
        + ("; the volume's national row agrees" if country else ""))


def kinh_of(u: dict[str, Any]) -> int:
    return sum(c for g, c in u["groups"].items() if fold(g) == "kinh")


def whole_hundred(values: list[float]) -> list[float]:
    """Shares re-rounded to one decimal by largest remainder, so they add
    to exactly 100.0."""
    scaled = [v * 10 for v in values]
    floors = [int(s) for s in scaled]
    short = round(1000 - sum(floors))
    order = sorted(range(len(scaled)), key=lambda i: scaled[i] - floors[i], reverse=True)
    for i in order[:short]:
        floors[i] += 1
    return [f / 10 for f in floors]


def composition(groups: dict[str, int], total: int) -> list[dict[str, Any]]:
    """Counts -> the map's rows, largest first, the small folded into one."""
    keep = {g: c for g, c in groups.items()
            if fold(g) not in NOT_A_GROUP and 100.0 * c / total >= MIN_SHARE}
    rows = sorted(keep.items(), key=lambda kv: (-kv[1], kv[0]))
    rest = total - sum(keep.values())
    if rest > 0:
        rows.append((RESIDUAL, rest))
    shares = whole_hundred([100.0 * c / total for _g, c in rows])
    return [{"group": g, "pct": p, "count": c} for (g, c), p in zip(rows, shares)]


def build(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from common import slugify
    out: list[dict[str, Any]] = []
    for u in units:
        if u["kind"] != "province":
            continue
        name = u["name"]
        aliases = list(PROVINCES[name])
        if u["label"] != name and u["label"] not in aliases:
            aliases.append(u["label"])
        sources = [{"field": f, "name": SOURCE, "url": MAIN_PDF, "license": LICENCE}
                   for f in ("ethnicity", "population", "sex_ratio")]
        out.append(record(
            f"VNM-{slugify(name)}", name, level="admin1", parent="VNM", country="VNM",
            aliases=aliases,
            population=measure(u["total"], year=YEAR, source=SOURCE),
            sex_ratio=measure(round(1000.0 * u["female"] / u["male"]),
                              unit="females_per_1000_males", year=YEAR, source=SOURCE)
            if u["male"] else None,
            ethnicity=composition(u["groups"], u["total"]),
            ethnicity_year=YEAR, ethnicity_note=NOTE, sources=sources,
        ))
    return out


def page_texts(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    log(f"  {len(reader.pages)} pages")
    return [(page.extract_text() or "") for page in reader.pages]


def run() -> int:
    log(f"vietnam: {SOURCE}")
    pdf = download(MAIN_PDF, RAW / "vietnam" / MAIN_PDF.rsplit("/", 1)[-1])
    units = parse(page_texts(pdf))
    kinds = {k: sum(1 for u in units if u["kind"] == k) for k in ("country", "region", "province")}
    pages = [u["page"] for u in units]
    log(f"  Table 2: {kinds} units on pages {min(pages)}-{max(pages)}" if pages
        else "  Table 2: no unit rows read")
    labels = sorted({g for u in units for g in u["groups"]})
    log(f"  {len(labels)} row labels: {labels}")
    check_units(units)
    check_national(units)
    records = build(units)
    for r in records:
        top = ", ".join(f"{g['group']} {g['pct']}" for g in r["ethnicity"][:3])
        log(f"    {r['name']:16} {r['population']['value']:>11,}  {top}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} provinces to {OUT}")
    return 0


# ---------------------------------------------------------------------------
# --probe: the reconnaissance that found the table. Writes nothing.
# ---------------------------------------------------------------------------

OFFICE_URLS = [
    "https://www.nso.gov.vn/",
    "https://www.nso.gov.vn/du-lieu-va-so-lieu-thong-ke/2020/11/ket-qua-toan-bo-tong-dieu-tra-dan-so-va-nha-o-nam-2019/",
    "https://www.nso.gov.vn/en/data-and-statistics/2020/11/completed-results-of-the-2019-viet-nam-population-and-housing-census/",
    MAIN_PDF,
    "https://www.nso.gov.vn/wp-content/uploads/2020/07/01-Bao-cao-53-dan-toc-thieu-so-2019_ban-in.pdf",
    "http://tongdieutradanso.vn/",
    "https://data.vietnam.opendevelopmentmekong.net/api/3/action/package_search?q=d%C3%A2n+t%E1%BB%99c+2019&rows=10",
]
KAGGLE_SEARCHES = ["vietnam census", "vietnam ethnic", "vietnam population province",
                   "vietnam religion", "dân tộc", "tổng điều tra dân số"]
WIKI_INSPECT = [("vi", "Các dân tộc Việt Nam"), ("vi", "Điện Biên"), ("vi", "Lào Cai"),
                ("vi", "Hà Giang"), ("en", "Ethnic groups in Vietnam")]
WIKI_SEARCHES = [("vi", '"dân tộc" "tỉnh" 2019 "Kinh" "Tày" "Nùng" "Mông" "Dao"')]
ETHNONYMS = ["Tày", "Thái", "Mường", "Khmer", "Hoa", "Nùng", "Mông", "Dao",
             "Gia Rai", "Ê Đê", "Ba Na", "Sán Chay", "Chăm", "Cơ Ho", "Xơ Đăng"]
FAITHS = ["Phật giáo", "Công giáo", "Tin lành", "Cao Đài", "Hòa Hảo"]
PROVINCE_TERMS = ["Hà Nội", "Hà Giang", "Cao Bằng", "Lạng Sơn", "Sơn La", "Điện Biên",
                  "Đắk Lắk", "Trà Vinh", "Hồ Chí Minh", "An Giang", "Cà Mau", "Lào Cai"]


def head(url: str, timeout: int = 20) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{resp.headers.get('Content-Length', '?'):>12}  {url}")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            get(url, timeout=timeout, limit=0)
        else:
            log(f"  {exc.code} {url}")
    except Exception as exc:  # noqa: BLE001 -- the failure mode is the finding
        log(f"  !! {type(exc).__name__}: {str(exc)[:100]}  {url}")


def get(url: str, timeout: int = 30, limit: int = 300_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read(limit) if limit else resp.read(1024)
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{len(blob):>12}  {url}")
            return blob.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        log(f"  {exc.code} {url}")
    except Exception as exc:  # noqa: BLE001
        log(f"  !! {type(exc).__name__}: {str(exc)[:100]}  {url}")
    return ""


def probe_office() -> None:
    log("== route (a): the office's pages")
    for url in OFFICE_URLS:
        if url.lower().endswith(".pdf"):
            head(url)
            continue
        html = get(url)
        if "opendevelopmentmekong" in url and html:
            try:
                for pkg in json.loads(html).get("result", {}).get("results", []):
                    log(f"      pkg {pkg.get('name')}: {pkg.get('title', '')[:80]}")
                    for res in pkg.get("resources", [])[:6]:
                        log(f"          {res.get('format', '?'):6} {res.get('url', '')[:120]}")
            except json.JSONDecodeError:
                log("      (not JSON)")
            continue
        for href in sorted(set(re.findall(r'href="([^"]+)"', html))):
            if re.search(r"\.pdf|\.xlsx?|\.zip|dieu-tra|dan-so|dan-toc|census|ethnic",
                         href, re.IGNORECASE) and "nso.gov.vn" in href:
                log(f"      -> {href[:160]}")


def kaggle_auth() -> dict[str, str]:
    """The Authorization header Kaggle's REST API accepts, from the runner's
    environment; the value is used and never printed."""
    token = os.environ.get("KAGGLE_API_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    user, key = os.environ.get("KAGGLE_USERNAME", ""), os.environ.get("KAGGLE_KEY", "")
    if user and key:
        cred = base64.b64encode(f"{user}:{key}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}
    return {}


def kaggle_json(path: str, params: dict[str, str]) -> Any:
    url = f"https://www.kaggle.com/api/v1/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **kaggle_auth()})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def probe_kaggle() -> None:
    log("== route (b): Kaggle's catalogue "
        f"({'with' if kaggle_auth() else 'without'} credentials)")
    for term in KAGGLE_SEARCHES:
        try:
            found = kaggle_json("datasets/list", {"search": term, "page": "1"})
        except Exception as exc:  # noqa: BLE001
            log(f"  search {term!r}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        log(f"  search {term!r}: {len(found)} datasets")
        for ds in found[:12]:
            ref = ds.get("ref") or f"{ds.get('ownerRef')}/{ds.get('datasetSlug')}"
            log(f"    {ref:50} {ds.get('totalBytes', 0):>12,}  {str(ds.get('title', ''))[:70]}")


def wiki_api(lang: str, **params: str) -> Any:
    q = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    return http_json(f"https://{lang}.wikipedia.org/w/api.php?{q}", timeout=90, cache=False)


def probe_wiki(rows_shown: int = 3) -> None:
    log("== route (c): Wikipedia")
    for lang, query in WIKI_SEARCHES:
        try:
            hits = wiki_api(lang, action="query", list="search", srsearch=query,
                            srlimit="12").get("query", {}).get("search", [])
            log(f"  [{lang}] search {query!r}: " + "; ".join(h["title"] for h in hits))
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] search {query!r}: {type(exc).__name__}: {str(exc)[:100]}")
    for lang, title in WIKI_INSPECT:
        try:
            parsed = wiki_api(lang, action="parse", page=title, prop="wikitext",
                              redirects="1").get("parse") or {}
            text = parsed.get("wikitext") or ""
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] {title!r}: {type(exc).__name__}: {str(exc)[:100]}")
            continue
        found = tables(text)
        log(f"  [{lang}] {title!r}: {len(text):,} bytes, {len(found)} table(s)")
        for n, t in enumerate(found):
            if not t:
                continue
            log(f"     -- table {n}: {len(t)} rows x {len(t[0])} cols; "
                f"header {[c.strip()[:22] for c in t[0][:8]]}")
            for row in t[1:1 + rows_shown]:
                log(f"        {[c.strip()[:22] for c in row[:8]]}")
        for m in re.finditer(r"[^\n]{0,200}(?:dân tộc|ethnic)[^\n]{0,300}", text):
            s = m.group(0)
            if re.search(r"2019|2009", s) and re.search(r"\d[\d.,]*\s?%|người", s):
                log(f"     ~ {' '.join(s.split())[:400]}")
                break


def probe_pdf(full: int = 2) -> None:
    """Which pages of the volume cross ethnic group (or religion) with a
    province, and what the contents pages promise."""
    log(f"== route (a): the results volume {MAIN_PDF}")
    pages = page_texts(download(MAIN_PDF, RAW / "vietnam" / MAIN_PDF.rsplit("/", 1)[-1]))
    for n in (5, 6, 7, 8):
        if n <= len(pages):
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines() if line.strip())
            log(f"      -- contents page {n}:\n{body[:3500]}")
    for label, terms, need in (("ethnic", ETHNONYMS, 6), ("religion", FAITHS, 4)):
        hits = [(n, [pv for pv in PROVINCE_TERMS if pv in page])
                for n, page in enumerate(pages, 1) if sum(t in page for t in terms) >= need]
        log(f"      {len(hits)} page(s) name {need}+ {label} terms; "
            f"{sum(1 for _n, pv in hits if pv)} of them beside a province")
        log("      " + " ".join(f"p{n}{'[' + ','.join(pv) + ']' if pv else ''}"
                                for n, pv in hits)[:3000])
        shown = 0
        for n, pv in hits:
            if not pv or shown >= full:
                continue
            shown += 1
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines() if line.strip())
            log(f"      -- page {n} ({label}):\n{body[:2500]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="reconnoitre the routes and write nothing")
    ap.add_argument("--routes", default="acp",
                    help="with --probe: a (office pages), b (Kaggle), c (Wikipedia), "
                         "p (scan the results volume for the tables)")
    ap.add_argument("--rows", type=int, default=2, help="sample rows or pages, with --probe")
    args = ap.parse_args()
    if not args.probe:
        return run()
    if "a" in args.routes:
        probe_office()
    if "b" in args.routes:
        probe_kaggle()
    if "c" in args.routes:
        probe_wiki(args.rows)
    if "p" in args.routes:
        probe_pdf(args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
