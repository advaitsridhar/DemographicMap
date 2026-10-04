#!/usr/bin/env python3
"""Northern Cyprus: the census taken in 2011 in the north, by village and quarter.

The Turkish Cypriot administration in the north of Cyprus (not recognised
internationally) took a population and housing census on 4 December 2011
("2011 Nüfus ve Konut Sayımı"), in one day under a curfew. Its results count
the de jure population -- everyone whose permanent residence (an intention to
live there a year or more) is in the north -- at 286,257: 150,483 men and
135,774 women. The State Planning Organisation (Devlet Planlama Örgütü,
devplan.org) published them in 2012-2013, and the statistics institute of the
same administration (İstatistik Kurumu, istatistik.gov.ct.tr) keeps them as
nine population tables. This reads four:

* Tablo 1 -- population by ilçe (district) and sex;
* Tablo 3 -- population by ilçe, bucak (sub-district), belediye (municipality)
  and mahalle (quarter), and sex: 250 quarters, a former village being one
  quarter of its municipality;
* Tablo 4 -- population by single year of age (to 85 and over), ilçe, bucak
  and sex;
* Tablo 5 -- population by ilçe, sex and citizenship (tabiiyet).

The Republic of Cyprus's censuses since 1974 have been taken only in the areas
under the effective control of its Government (``cyprus_census``), so for the
communities in the north this is the only count there is. Its institute's
census page lists the 2006 and 2011 censuses and nothing later (read on
4 October 2026), so 2011 is the newest.

**Binding.** The map draws the Republic's communities under their Greek names;
the census names its quarters in Turkish. ``BIND`` places each quarter on the
polygon it is, by three kinds of evidence, all of them binding evidence only
and none of them data: the names (GeoNames' alternate names and Wikidata's
Turkish and Greek labels say which community a Turkish name is); the points
(GeoNames', Wikidata's and OpenStreetMap's points for the village fall in or
beside the polygon of that name); and the outlines (OpenStreetMap's outline of
the quarter lies mostly inside that polygon -- 72 to 100 per cent for the
villages, the rest digitising noise along shared edges). Where the boundary
file draws two or three of the Republic's communities as one polygon (Agios
Ilias with Bogazi and Monarga; Kazafani with Karakoumi), the polygon carries
the sum of their quarters. A town's quarters go on the town's polygon where
their outlines lie in it (Famagusta, Kythrea, Lapithos, Morfou, Rizokarpaso,
Karavas). The probe module ``cyprus_north_probe`` reads all of this evidence,
and its logs are where the figures in the notes come from.

**The binding rule**, one for every polygon. A quarter is placed in a polygon
when at least 85% of the buildings OpenStreetMap maps in its outline stand in
it, or, where its buildings were not all counted, when at least 70% of its
outline lies in it and the village's point does. A polygon carries the sum of
the quarters placed in it only when the residents of those quarters estimated
to live outside it, plus those of other quarters estimated to live inside it,
come to at most a tenth of that sum (``MAX_OVERLAP``): estimated from the
buildings, at each quarter's own residents per building, wherever its whole
outline was counted and five or more of its buildings stand across the line.
``OVERLAP`` keeps the measured share for every polygon where any was found,
and the run stops if a bound polygon's exceeds the tenth or a polygon left off
for its overlap does not.

What is left off, and why, is in ``UNPLACED`` (quarters) and ``LEFT_OFF``
(polygons): a quarter that the census counts as one and the map draws as two
villages; the quarters of north Nicosia and of Kyrenia's edge, whose outlines
and buildings cross the polygons' lines; villages the census lists no quarter
for; and the villages both censuses count a part of (``BOTH``: Pyla,
Pergamos, Acheritou, Agios Dometios and Nicosia's own polygon), on which the
Republic's 2021 count stands and nothing is written here. Every quarter of
Tablo 3 is placed exactly once, on a polygon or in a district, and the run
stops if one is not. A polygon left off displaces an encyclopaedia's figure
from before 2011 (``displaces_before``): the census taken that year counted
the whole north, and gives the polygon no count of its own.

**The Republic's count stands.** ``check_republic`` reads cyprus_census.json
and stops the run if any polygon written here is one the Republic's 2021
census counts anyone in. Two it lists with no residents, Louroukina and Pano
Zodeia, are villages the census in the north counts (``ZERO_IN_REPUBLIC``);
they are written only once cyprus_census.json gives them a gap instead of its
0, which is a change to that adapter (shared.patch), so that the two figures
never stand side by side.

**Kyrenia.** Every quarter of the census's Girne ilçe lies in the Republic's
Kyrenia district and no quarter of another ilçe does (``check_kyrenia``). The
district is filled only as the sum of the villages bound to its polygons, and
only when they cover it completely: every polygon of the district bound, and
their quarters all of the district's (then the ilçe's ages and citizenship
are theirs). Today 33 of its 46 polygons are bound, holding 53,072 of its
69,163 residents, so every field of the district says why it is empty. No
ilçe figure is put on a district of the Republic.

**What the census does not give.** Ages are published by bucak at the finest,
which is no drawn unit, so no village has a median age. Citizenship is
published by ilçe only. No table of religion, language or ethnicity was
published (the institute's 2011 page lists nine population tables: sex,
municipality and quarter, age, citizenship, birthplace); each polygon says so.
Tablo 4 and Tablo 5 are still read: they are checked against Tablo 3, district
by district and sub-district by sub-district.

**Nothing newer.** The institute's population and demography bulletin of
4 March 2025 says the north has had three censuses, of 21 December 1996,
30 April 2006 and 4 December 2011; its figures since are projections for the
north as a whole, and its note of 11 November 2024 says figures by settlement
await an address-based population register still being set up.

Usage:
    python -m scripts.fetch_census.cyprus_north_census
"""

from __future__ import annotations

import argparse
import re
import urllib.error
from collections import Counter
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, read_json, record,
                      write_json)
from .balkans_common import check_sum, exact_shares, fold, sex_ratio, shapes
from .redatam import median_age

OUT = "cyprus_north_census.json"
YEAR = 2011
HOST = "https://istatistik.gov.ct.tr/Portals/39/"
PAGE = "https://istatistik.gov.ct.tr/TEMEL-%C4%B0STAT%C4%B0ST%C4%B0KLER/N%C3%9CFUS-SAYIMLARI/N%C3%BCfus-Say%C4%B1m%C4%B1-2011"
TABLES = {
    "ilce": "Tablo-1-IlceCinsiyet.xls",
    "mahalle": "Tablo-3-Mahalle_Cinsiyet.xls",
    "ages": "Tablo-4-Yas_YasGrubu.xls",
    "citizenship": "Tablo-5-Citizenship.xls",
}
# The same workbooks as devplan.org published them, in the Internet Archive:
# read only when the institute's host does not answer.
WAYBACK = {
    "ilce": ("20201019105833", "http://www.devplan.org/Nufus-2011/Tablolar/Tablo-1-IlceCinsiyet.xls"),
    "mahalle": ("20200326175144", "http://www.devplan.org/Nufus-2011/Tablolar/Tablo-3-Mahalle_Cinsiyet.xls"),
    "ages": ("20201022030009", "http://www.devplan.org/Nufus-2011/Tablolar/Tablo-4-Yas_YasGrubu.xls"),
    "citizenship": ("20201019112632", "http://www.devplan.org/Nufus-2011/Tablolar/Tablo-5-Citizenship.xls"),
}
TITLES = {
    "ilce": "Tablo 1, usually resident (de jure) population by district (ilçe) and sex",
    "mahalle": ("Tablo 3, usually resident (de jure) population by district, sub-district, "
                "municipality, quarter (mahalle) and sex"),
    "ages": "Tablo 4, usually resident (de jure) population by single year of age, district, "
            "sub-district and sex",
    "citizenship": "Tablo 5, usually resident (de jure) population by district, sex and citizenship",
}
SOURCE = ("Census taken on 4 December 2011 by the Turkish Cypriot administration in the north of "
          "Cyprus (not recognised internationally), 2011 Nüfus ve Konut Sayımı, {title}; published "
          "by its statistics institute (İstatistik Kurumu)")
LICENCE = "Published by the İstatistik Kurumu; terms of reuse not stated"
# The national figures the bulletin of the final results states (DPÖ, 2013).
PUBLISHED = {"total": 286257, "men": 150483, "women": 135774}
GIRNE = "girne"
KYRENIA = "Kyrenia"
WHO = ("the census taken on 4 December 2011 by the Turkish Cypriot administration in the north "
       "of Cyprus (not recognised internationally)")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def rows_of(blob: bytes) -> list[list[Any]]:
    """A legacy workbook's first sheet as a list of rows."""
    import xlrd
    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    return [sheet.row_values(r) for r in range(sheet.nrows)]


def table(name: str) -> tuple[list[list[Any]], str]:
    """(rows, url read): the institute's copy, else the archived devplan one."""
    import xlrd
    url = HOST + TABLES[name]
    try:
        return rows_of(http_get(url, binary=True, timeout=180, retries=2)), url
    except (urllib.error.URLError, RuntimeError, xlrd.XLRDError) as exc:
        stamp, old = WAYBACK[name]
        log(f"  {TABLES[name]}: the institute's host gave {type(exc).__name__}; reading the "
            f"Internet Archive's copy of devplan.org's ({stamp})")
        url = f"https://web.archive.org/web/{stamp}id_/{old}"
        return rows_of(http_get(url, binary=True, timeout=180, retries=2)), url


def text(value: Any) -> str:
    """A cell as text. Not ``str(value or "")``: Tablo 4's first age is the
    number 0.0, which is falsy, and would read as an empty label."""
    return "" if value is None else re.sub(r"\s+", " ", str(value)).strip()


def number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    t = text(value).replace(",", "")
    return float(t) if re.fullmatch(r"\d+(\.\d+)?", t) else None


def key(belediye: str, mahalle: str) -> str:
    """'GİRNE', 'AŞAĞI GİRNE' -> 'girne/asagigirne'."""
    return f"{fold(belediye)}/{fold(mahalle)}"


def quarters(rows: list[list[Any]], published: dict[str, float] | None = None) -> dict[str, Any]:
    """Tablo 3 as {"quarters": {key: q}, "municipalities", "bucaks", "ilces",
    "total"}; each q carries ilce, bucak, belediye, mahalle, total, men, women.

    The table nests by indentation: the district's name sits in the first
    column beside "İlçe Toplam", the sub-district's in the second beside
    "Bucak Toplamı", a municipality's in the third with nothing after it, and
    a quarter's in the fourth. Every level is checked against the one above,
    every row's sexes against its total, and the whole against the totals
    the census published (``PUBLISHED`` unless given).
    """
    published = published or PUBLISHED
    out: dict[str, Any] = {"quarters": {}, "municipalities": {}, "bucaks": {}, "ilces": {},
                           "total": None}
    ilce = bucak = belediye = None
    for row in rows:
        cells = [text(c) for c in row[:4]] + [None] * max(0, 4 - len(row))
        vals = [number(c) for c in row[4:7]]
        if len(vals) < 3 or any(v is None for v in vals):
            continue
        total, men, women = vals
        a, b, c, d = cells[:4]
        check_sum(men + women, total, f"cyprus_north_census: the sexes of {' / '.join(filter(None, [a, b, c, d]))}")
        unit = {"total": total, "men": men, "women": women}
        # Folded, because Python lower-cases "İ" to an "i" with a combining
        # dot: "İlçe Toplam".lower() is not "ilçe toplam".
        if fold(a) == "geneltoplam":
            out["total"] = unit
        elif a and fold(b) == "ilcetoplam":
            ilce, bucak, belediye = a, None, None
            out["ilces"][fold(ilce)] = dict(unit, name=ilce)
        elif b and fold(c) == "bucaktoplami":
            bucak, belediye = b, None
            out["bucaks"][fold(bucak)] = dict(unit, name=bucak, ilce=fold(ilce))
        elif c and not d:
            belediye = c
            out["municipalities"][fold(c)] = dict(unit, name=c, ilce=fold(ilce), bucak=fold(bucak))
        elif d:
            if not (ilce and bucak and belediye):
                raise SystemExit(f"cyprus_north_census: quarter {d!r} before its municipality")
            k = key(belediye, d)
            if k in out["quarters"]:
                raise SystemExit(f"cyprus_north_census: quarter {k} twice")
            out["quarters"][k] = dict(unit, ilce=fold(ilce), bucak=fold(bucak), belediye=belediye,
                                      mahalle=d)
        else:
            raise SystemExit(f"cyprus_north_census: a row of Tablo 3 with no name: {row[:7]}")
    if not out["total"]:
        raise SystemExit("cyprus_north_census: Tablo 3 has no Genel Toplam")
    qs = list(out["quarters"].values())
    for name, m in out["municipalities"].items():
        part = [q for q in qs if fold(q["belediye"]) == name]
        for sex in ("total", "men", "women"):
            check_sum(sum(q[sex] for q in part), m[sex], f"cyprus_north_census: the quarters of {m['name']}, {sex}")
    for name, b in out["bucaks"].items():
        for sex in ("total", "men", "women"):
            check_sum(sum(q[sex] for q in qs if q["bucak"] == name), b[sex],
                      f"cyprus_north_census: the quarters of {b['name']} bucak, {sex}")
    for name, i in out["ilces"].items():
        for sex in ("total", "men", "women"):
            check_sum(sum(q[sex] for q in qs if q["ilce"] == name), i[sex],
                      f"cyprus_north_census: the quarters of {i['name']} ilçe, {sex}")
    for sex in ("total", "men", "women"):
        check_sum(sum(q[sex] for q in qs), out["total"][sex], f"cyprus_north_census: the quarters, {sex}")
        check_sum(out["total"][sex], published[sex], f"cyprus_north_census: Tablo 3 against the published {sex}")
    return out


def districts(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Tablo 1: {ilçe key or 'total': {total, men, women}}."""
    out = {}
    for row in rows:
        name = text(row[0]) if row else ""
        vals = [number(c) for c in row[1:4]]
        if not name or len(vals) < 3 or any(v is None for v in vals):
            continue
        check_sum(vals[1] + vals[2], vals[0], f"cyprus_north_census: Tablo 1, the sexes of {name}")
        out["total" if fold(name) == "geneltoplam" else fold(name)] = dict(
            zip(("total", "men", "women"), vals))
    return out


def first_row(rows: list[list[Any]], label: str) -> int:
    """The index of the first row whose first cell folds to ``label`` and
    which carries a number: where a table's header ends."""
    for i, row in enumerate(rows):
        if row and fold(text(row[0])) == label and any(number(c) is not None for c in row[1:]):
            return i
    raise SystemExit(f"cyprus_north_census: no {label!r} row")


def single_years(rows: list[list[Any]], ilces: set[str]) -> dict[tuple[str, str | None], dict[str, Any]]:
    """Tablo 4: {(ilçe key, bucak key or None for the whole ilçe):
    {"ages": Counter (both sexes), "men", "women", "total", and per sex
    "men_ages", "women_ages"}}; and ("total", None) for the whole north.

    The header names each ilçe above its "Toplam" column and each bucak
    ("... BUCAĞI") above its three (Toplam, Erkek, Kadın); the rows are
    single years, five-year sums (skipped) and "85 VE ÜZERİ", the open top.
    ``ilces`` are the district keys Tablo 3 knows: a header cell is read as
    a district only if it is one.
    """
    start = first_row(rows, "toplam")
    header = rows[:start]
    width = max(len(r) for r in rows)
    ilce_at: dict[int, str | None] = {}
    bucak_at: dict[int, str | None] = {}
    sex_at: dict[int, str] = {}
    current_ilce: str | None = None
    current_bucak: str | None = None
    for col in range(1, width):
        for r in header:
            lab = text(r[col]) if col < len(r) else ""
            f = fold(lab)
            if f.endswith("bucagi"):
                current_bucak = fold(re.sub(r"(?i)\s*BUCA\S*$", "", lab))
            elif f in ilces:
                current_ilce, current_bucak = f, None
        if col == 1:
            current_ilce, current_bucak = "total", None
        ilce_at[col], bucak_at[col] = current_ilce, current_bucak
        last = next((fold(text(r[col])) for r in reversed(header) if col < len(r) and text(r[col])), "")
        sex_at[col] = {"erkek": "men", "kadin": "women"}.get(last, "total")
    out: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in rows[start:]:
        label = text(row[0]) if row else ""
        low = fold(label)
        single = re.fullmatch(r"(\d+)(\.0)?", label)
        top = re.fullmatch(r"(\d+)veuzeri", low)
        if not (single or top or low == "toplam"):
            continue                                  # a five-year sum, or a note
        for col in range(1, len(row)):
            v = number(row[col])
            if v is None or ilce_at.get(col) is None:
                continue
            unit = out.setdefault((ilce_at[col], bucak_at[col]),
                                  {"ages": Counter(), "men": 0.0, "women": 0.0, "total": 0.0})
            sex = sex_at[col]
            if low == "toplam":
                unit[sex] = v
            elif sex == "total":
                unit["ages"][int((single or top).group(1))] += v
            else:
                unit.setdefault(f"{sex}_ages", Counter())[int((single or top).group(1))] += v
    for (ilce, bucak), unit in out.items():
        where = f"{ilce}{' / ' + bucak if bucak else ''}"
        if unit["ages"]:
            check_sum(sum(unit["ages"].values()), unit["total"], f"cyprus_north_census: Tablo 4, the ages of {where}")
        for sex in ("men", "women"):
            if unit.get(f"{sex}_ages"):
                check_sum(sum(unit[f"{sex}_ages"].values()), unit[sex],
                          f"cyprus_north_census: Tablo 4, the {sex}'s ages of {where}")
        if unit["men"] or unit["women"]:
            check_sum(unit["men"] + unit["women"], unit["total"], f"cyprus_north_census: Tablo 4, the sexes of {where}")
    return out


# Tablo 5's rows (folded) -> the labels the map shows: what the census
# counts, in English. The three rows under "KKTC TOPLAM" split the citizens
# of the administration in the north ("TRNC") by whether they also hold
# another citizenship; the total row is their sum and is not a group of its
# own. "Diğer" is everyone of a citizenship the table does not name.
CITIZENSHIP = {
    "yalnizkktc": "TRNC citizen", "kktcturkiye": "TRNC and Turkish citizen",
    "kktcdiger": "TRNC and other citizen", "turkiye": "Turkish citizen",
    "birlesikkrallik": "British citizen", "turkmenistan": "Turkmen citizen",
    "nijerya": "Nigerian citizen", "iranislamcumhuriyeti": "Iranian citizen",
    "pakistan": "Pakistani citizen", "bulgaristan": "Bulgarian citizen",
    "azerbeycan": "Azerbaijani citizen", "azerbaycan": "Azerbaijani citizen",
    "diger": "Other",
}
TRNC = ("TRNC citizen", "TRNC and Turkish citizen", "TRNC and other citizen")


def citizenship(rows: list[list[Any]], ilces: set[str]) -> dict[str, dict[str | None, float]]:
    """Tablo 5: {ilçe key or 'total': {label: count, None: total}}, both sexes
    together (the first of each district's three columns). The rows add to
    "GENEL TOPLAM" in every column, and the TRNC's three rows to "KKTC
    TOPLAM"; a row with no label here stops the run."""
    start = first_row(rows, "geneltoplam")
    cols: dict[str, int] = {"total": 2}
    for r in rows[:start]:
        for col, cell in enumerate(r):
            f = fold(text(cell))
            if f in ilces:
                cols.setdefault(f, col)
    if set(cols) - {"total"} != ilces:
        raise SystemExit(f"cyprus_north_census: Tablo 5 names districts {sorted(cols)}, not {sorted(ilces)}")
    out: dict[str, dict[str | None, float]] = {k: {} for k in cols}
    kktc: dict[str, float] = {}
    unknown = []
    for row in rows[start:]:
        a, b = (text(row[0]) if row else ""), (text(row[1]) if len(row) > 1 else "")
        label = b or a
        if not label or all(number(c) is None for c in row[2:]):
            continue
        k = fold(label)
        if k not in CITIZENSHIP and k not in ("geneltoplam", "kktctoplam"):
            unknown.append(label)
            continue
        for ilce, col in cols.items():
            v = number(row[col]) if col < len(row) else None
            if v is None:
                raise SystemExit(f"cyprus_north_census: Tablo 5, no count for {label!r} in {ilce}")
            if k == "geneltoplam":
                out[ilce][None] = v
            elif k == "kktctoplam":
                kktc[ilce] = v
            else:
                out[ilce][CITIZENSHIP[k]] = out[ilce].get(CITIZENSHIP[k], 0.0) + v
    if unknown:
        raise SystemExit(f"cyprus_north_census: Tablo 5 rows with no label: {unknown}")
    for ilce, groups in out.items():
        check_sum(sum(v for g, v in groups.items() if g), groups[None], f"cyprus_north_census: Tablo 5, {ilce}")
        check_sum(sum(groups.get(g, 0.0) for g in TRNC), kktc[ilce],
                  f"cyprus_north_census: Tablo 5, the TRNC's citizens in {ilce}")
    return out


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

# The drawn polygon (shape id; its label as the boundary file draws it, as a
# check) -> the census quarters ("MUNICIPALITY/QUARTER", as Tablo 3 spells
# them) whose usual residents it holds. Measured by cyprus_north_probe's
# GeoNames, Wikidata and OpenStreetMap evidence: see the module docstring and
# NOTES for every polygon that is not one village.
BIND: dict[str, tuple[str, ...]] = {
    "46923920B30360023901504": ("Afanteia-Orniti", "DEĞİRMENLİK/GAZİKÖY"),
    "46923920B99001486535743": ("Agia Eirini Keryneias", "LAPTA (ÇAMLIBEL)/AKDENİZ"),
    "46923920B83418385302054": ("Agia Kepir", "DEĞİRMENLİK/DİLEKKAYA"),
    "46923920B13972666362047": ("Agia Trias", "YENİ ERENKÖY/SİPAHİ"),
    "46923920B74811643881920": ("Agios Andronikos Karpasias", "YENİ ERENKÖY/YEŞİLKÖY"),
    "46923920B63709506451414": ("Agios Andronikos Trikomou", "İSKELE/TOPÇUKÖY"),
    "46923920B730618297548": ("Agios Chariton", "SERDARLI/ERGENEKON"),
    "46923920B27642326051003": ("Agios Efstathios", "BÜYÜKKONUK/ZEYBEKKÖY"),
    "46923920B11647519105740": ("Agios Epiktitos", "ÇATALKÖY/ÇATALKÖY"),
    "46923920B200198305742": ("Agios Ermolaos", "DİKMEN/ŞİRİNEVLER"),
    "46923920B20670764204994": ("Agios Georgios Ammochostou", "İSKELE/AYGÜN"),
    "46923920B51635093907886": ("Agios Georgios Keryneias", "GİRNE/KARAOĞLANOĞLU"),
    "46923920B93502330061419": ("Agios Iakovos", "İSKELE/ALTINOVA"),
    "46923920B56788308456175": ("Agios Ilias", "İSKELE/BOĞAZ", "İSKELE/BOĞAZTEPE", "İSKELE/YARKÖY"),
    "46923920B28206074202604": ("Agios Nikolaos Ammochostou", "GEÇİTKALE/YAMAÇKÖY"),
    "46923920B79563673366387": ("Agios Sergios", "YENİ BOĞAZİÇİ/YENİ BOĞAZİÇİ"),
    "46923920B72100366560122": ("Agios Symeon", "YENİ ERENKÖY/AVTEPE"),
    "46923920B90190427209928": ("Agios Theodoros Ammochostou", "MEHMETÇİK/ÇAYIROVA"),
    "46923920B32976107487407": ("Agios Vasileios", "ALAYKÖY/TÜRKELİ"),
    "46923920B13856899738172": ("Agridaki", "LAPTA (ÇAMLIBEL)/ALEMDAĞ"),
    "46923920B6502915475397": ("Aigialousa", "YENİ ERENKÖY/YENİ ERENKÖY"),
    "46923920B90668943493632": ("Akanthou",
        "TATLISU/AKTUNÇ", "TATLISU/KÜÇÜKERENKÖY", "TATLISU/YALI"),
    "46923920B56157666761112": ("Alayköy", "ALAYKÖY/ALAYKÖY"),
    "46923920B29030775604089": ("Aloda", "YENİ BOĞAZİÇİ/ATLILAR"),
    "46923920B15488277877643": ("Ammochostos",
        "GAZİMAĞUSA/ANADOLU", "GAZİMAĞUSA/BAYKAL", "GAZİMAĞUSA/CANBOLAT", "GAZİMAĞUSA/ÇANAKKALE",
        "GAZİMAĞUSA/DUMLUPINAR", "GAZİMAĞUSA/HARİKA", "GAZİMAĞUSA/KAPALI MARAŞ",
        "GAZİMAĞUSA/KARAKOL", "GAZİMAĞUSA/LALA MUSTAFA PAŞA", "GAZİMAĞUSA/NAMIK KEMAL",
        "GAZİMAĞUSA/PERTEV PAŞA", "GAZİMAĞUSA/PİYALE PAŞA", "GAZİMAĞUSA/SAKARYA",
        "GAZİMAĞUSA/SURİÇİ", "GAZİMAĞUSA/ZAFER"),
    "46923920B7308228974018": ("Ampelikou", "LEFKE/BAĞLIKÖY"),
    "46923920B58567235428408": ("Angastina", "PAŞAKÖY/ASLANKÖY"),
    "46923920B8588599925202": ("Angolemi", "LEFKE/TAŞPINAR"),
    "46923920B85221731865635": ("Ardana", "İSKELE/ARDAHAN"),
    "46923920B73133986650844": ("Argaki", "GÜZELYURT/AKÇAY"),
    "46923920B52091218012578": ("Arnadi", "İSKELE/KUZUCUK"),
    "46923920B32733260957571": ("Arsos Larnakas", "DEĞİRMENLİK/YİĞİTLER"),
    "46923920B6105070977728": ("Askeia", "PAŞAKÖY/PAŞAKÖY"),
    "46923920B22292626900654": ("Asomatos Keryneias", "LAPTA (ÇAMLIBEL)/ÖZHAN"),
    "46923920B2873986073585": ("Avgolida", "İSKELE/KURTULUŞ"),
    "46923920B35066056619311": ("Beïkioï", "DEĞİRMENLİK/BEYKÖY"),
    "46923920B54371485006502": ("Charkeia", "ESENTEPE/KARAAĞAÇ"),
    "46923920B64844622441299": ("Davios", "BÜYÜKKONUK/KAPLICA", "KANTARA/KANTARA"),
    "46923920B66967696615816": ("Diorios", "LAPTA (ÇAMLIBEL)/TEPEBAŞI"),
    "46923920B42441045079611": ("Elia Lefkosias", "LEFKE/DOĞANCI"),
    "46923920B40684211252077": ("Ella Keryneias", "ALSANCAK/YEŞİLTEPE"),
    "46923920B25776414767341": ("Epicho", "DEĞİRMENLİK/CİHANGİR"),
    "46923920B67887725742244": ("Eptakomi", "BÜYÜKKONUK/YEDİKONUK"),
    "46923920B63490584599042": ("Exo Metochi", "DEĞİRMENLİK/DÜZOVA"),
    "46923920B70745451588805": ("Flamoudi", "BÜYÜKKONUK/MERSİNLİK"),
    "46923920B41218230383335": ("Fota", "DİKMEN/DAĞYOLU"),
    "46923920B75200378291295": ("Fyllia", "GÜZELYURT/GAYRETKÖY", "GÜZELYURT/SERHATKÖY"),
    "46923920B93612483186560": ("Gaidouras", "İNÖNÜ/KORKUTELİ"),
    "46923920B49628554196420": ("Galateia", "MEHMETÇİK/MEHMETÇİK"),
    "46923920B55142884438741": ("Galinoporni", "DİPKARPAZ/KALEBURNU"),
    "46923920B84775184962851": ("Gastria", "İSKELE/KALECİK"),
    "46923920B92957944756443": ("Genagra", "GEÇİTKALE/NERGİSLİ"),
    "46923920B71486587223903": ("Gerani", "İSKELE/TURNALAR"),
    "46923920B80700863058224": ("Goufes", "GEÇİTKALE/ÇAMLICA"),
    "46923920B91151164993764": ("Gypsou", "YENİ BOĞAZİÇİ/AKOVA"),
    "46923920B84708400671300": ("Kalo Chorio Kapouti", "GÜZELYURT/KALKANLI"),
    "46923920B82951092544014": ("Kalo Chorio Soleas", "LEFKE/ÇAMLIKÖY"),
    "46923920B49066435072009": ("Kalograia", "ESENTEPE/BAHÇELİ"),
    "46923920B75029215318719": ("Kalopsida", "BEYARMUDU/ÇAYÖNÜ"),
    "46923920B14026353956813": ("Kalyvakia", "DEĞİRMENLİK/KALAVAÇ"),
    "46923920B20752671423120": ("Kampyli", "LAPTA (ÇAMLIBEL)/HİSARKÖY"),
    "46923920B42902060181801": ("Kanli", "GÖNYELİ/KANLIKÖY"),
    "46923920B26333175037014": ("Karavas",
        "ALSANCAK/ÇAĞLAYAN", "ALSANCAK/YAYLA", "ALSANCAK/YEŞİLOVA"),
    "46923920B41676558074930": ("Karavostasi",
        "LEFKE/DENİZLİ", "LEFKE/GEMİKONAĞI", "LEFKE/YEDİDALGA"),
    "46923920B2275839415846": ("Karpaseia", "LAPTA (ÇAMLIBEL)/KARPAŞA"),
    "46923920B4985084471398": ("Kato Zodeia", "GÜZELYURT/AŞAĞI BOSTANCI"),
    "46923920B85367038784493": ("Katokopia", "GÜZELYURT/ZÜMRÜTKÖY"),
    "46923920B14139084564412": ("Kazivera", "LEFKE/GAZİVEREN"),
    "46923920B20243992884618": ("Keryneia", "GİRNE/AŞAĞI GİRNE", "GİRNE/YUKARI GİRNE"),
    "46923920B15009716922247": ("Kiados", "SERDARLI/SERDARLI"),
    "46923920B18186320704547": ("Kiomourtzou", "DİKMEN/KÖMÜRCÜ"),
    "46923920B14813142167534": ("Kioneli", "GÖNYELİ/GÖNYELİ", "GÖNYELİ/YENİKENT"),
    "46923920B25595466119807": ("Klepini", "ÇATALKÖY/ARAPKÖY"),
    "46923920B61069170158691": ("Knodara", "SERDARLI/GÖNENDERE"),
    "46923920B29026112812514": ("Koilanemos", "YENİ ERENKÖY/ESENKÖY"),
    "46923920B1495178663042": ("Koma tou Gialou", "MEHMETÇİK/KUMYALI"),
    "46923920B77535309338235": ("Komi Kepir", "BÜYÜKKONUK/BÜYÜKKONUK"),
    "46923920B33893861397598": ("Kontea", "BEYARMUDU/TÜRKMENKÖY"),
    "46923920B62470816278945": ("Kontemenos", "LAPTA (ÇAMLIBEL)/KILIÇARSLAN"),
    "46923920B82125334474321": ("Kormakitis", "LAPTA (ÇAMLIBEL)/KORUÇAM"),
    "46923920B14049283421613": ("Kornokipos", "SERDARLI/GÖRNEÇ"),
    "46923920B36797029965158": ("Koroveia", "YENİ ERENKÖY/KURUOVA"),
    "46923920B61611069046028": ("Kouklia Ammochostou", "BEYARMUDU/KÖPRÜLÜ"),
    "46923920B54534863217064": ("Kourou Monastiri", "DEĞİRMENLİK/ÇUKUROVA"),
    "46923920B77233656237897": ("Koutsoventis", "DİKMEN/GÜNGÖR"),
    "46923920B22982448470937": ("Krideia", "BÜYÜKKONUK/KİLİTKAYA"),
    "46923920B47600547023009": ("Krini", "DİKMEN/PINARBAŞI"),
    "46923920B69110697471106": ("Kyra", "GÜZELYURT/MEVLEVİ"),
    "46923920B79735080950655": ("Kythrea",
        "DEĞİRMENLİK/BAHÇELİEVLER", "DEĞİRMENLİK/BAŞPINAR", "DEĞİRMENLİK/CAMİALTI",
        "DEĞİRMENLİK/MEHMETÇİK", "DEĞİRMENLİK/SARAY", "DEĞİRMENLİK/TEPEBAŞI"),
    "46923920B60691928275078": ("Lapathos", "İSKELE/BOĞAZİÇİ"),
    "46923920B16403791533064": ("Lapithos",
        "LAPTA (GİRNE)/BAŞPINAR", "LAPTA (GİRNE)/SAKARYA", "LAPTA (GİRNE)/ADATEPE",
        "LAPTA (GİRNE)/KOCATEPE", "LAPTA (GİRNE)/TINAZTEPE", "LAPTA (GİRNE)/TÜRK",
        "LAPTA (GİRNE)/YAVUZ"),
    "46923920B93505429851808": ("Larnakas Lapithou", "LAPTA (ÇAMLIBEL)/KOZAN"),
    "46923920B88309634492013": ("Lefka", "LEFKE/LEFKE"),
    "46923920B58626774901810": ("Lefkonoiko", "GEÇİTKALE/GEÇİTKALE"),
    "46923920B82945546489957": ("Leonarisso", "YENİ ERENKÖY/ZİYAMET"),
    "46923920B52729899789511": ("Livadia Ammochostou", "BÜYÜKKONUK/SAZLIKÖY"),
    "46923920B2893427374385": ("Livera", "LAPTA (ÇAMLIBEL)/SADRAZAMKÖY"),
    "46923920B13222892315728": ("Loutros", "LEFKE/BADEMLİKÖY"),
    "46923920B59905101389216": ("Lysi", "AKDOĞAN/AKDOĞAN"),
    "46923920B82296583493570": ("Lythragkomi", "YENİ ERENKÖY/BOLTAŞLI"),
    "46923920B17010547008979": ("Makrasyka", "BEYARMUDU/İNCİRLİ"),
    "46923920B48793600754585": ("Mandres", "İSKELE/AĞILLAR"),
    "46923920B5435388082406": ("Maratha", "YENİ BOĞAZİÇİ/MURATAĞA"),
    "46923920B63450565530308": ("Marathovounos", "PAŞAKÖY/ULUKIŞLA"),
    "46923920B88721309897809": ("Masari", "GÜZELYURT/ŞAHİNLER"),
    "46923920B8194209200989": ("Melanarga", "YENİ ERENKÖY/ADAÇAY"),
    "46923920B6129674637399": ("Melounta", "GEÇİTKALE/MALLIDAĞ"),
    "46923920B81614403917932": ("Melouseia", "DEĞİRMENLİK/KIRIKKALE"),
    "46923920B95697923922739": ("Mia Milia", "LEFKOŞA/HASPOLAT"),
    "46923920B90595863135808": ("Milia Ammochostou", "YENİ BOĞAZİÇİ/YILDIRIM"),
    "46923920B52703620430879": ("Mora", "DEĞİRMENLİK/MERİÇ"),
    "46923920B39754802683787": ("Morfou",
        "GÜZELYURT/LALA MUSTAFA PAŞA", "GÜZELYURT/PİYALE PAŞA", "GÜZELYURT/İSMET PAŞA",
        "GÜZELYURT/YUVACIK"),
    "46923920B47977238929858": ("Mousoulita", "PAŞAKÖY/KURUDERE"),
    "46923920B74910454629938": ("Myrtou", "LAPTA (ÇAMLIBEL)/ÇAMLIBEL"),
    "46923920B38170479802577": ("Neta", "YENİ ERENKÖY/TAŞLICA"),
    "46923920B78041797088340": ("Nikitas", "GÜZELYURT/GÜNEŞKÖY"),
    "46923920B94328330432967": ("Orga", "LAPTA (ÇAMLIBEL)/KAYALAR"),
    "46923920B72580164360540": ("Ovgoros", "İSKELE/ERGAZİ"),
    "46923920B63602794647925": ("Palaikythro", "DEĞİRMENLİK/BALIKESİR"),
    "46923920B46239783627479": ("Panagra", "LAPTA (ÇAMLIBEL)/GEÇİTKÖY"),
    "46923920B57147511667034": ("Patanissos", "MEHMETÇİK/BALALAN"),
    "46923920B77958582681624": ("Patriki", "BÜYÜKKONUK/TUZLUCA"),
    "46923920B34029116615265": ("Pentageia", "LEFKE/YEŞİLYURT"),
    "46923920B2935108629033": ("Peristeronari", "LEFKE/CENGİZKÖY"),
    "46923920B30542922336508": ("Petra tou Digeni", "DEĞİRMENLİK/YENİCEKÖY"),
    "46923920B51203162214587": ("Pileri", "DİKMEN/GÖÇERİ"),
    "46923920B1049795521369": ("Platani", "GEÇİTKALE/ÇINARLI"),
    "46923920B46952699508518": ("Prastio Ammochostou", "İNÖNÜ/DÖRTYOL"),
    "46923920B44664776517554": ("Prastio Lefkosias", "GÜZELYURT/AYDINKÖY"),
    "46923920B47767845876682": ("Psyllatos", "GEÇİTKALE/SÜTLÜCE"),
    "46923920B31691504288871": ("Pyrga Ammochostou", "İNÖNÜ/PİRHAN"),
    "46923920B57718110047043": ("Rizokarpaso",
        "DİPKARPAZ/ERSİN PAŞA", "DİPKARPAZ/POLAT PAŞA", "DİPKARPAZ/SANCAR PAŞA"),
    "46923920B66935539070734": ("Santalaris", "YENİ BOĞAZİÇİ/SANDALLAR"),
    "46923920B30915554603571": ("Sichari", "DİKMEN/AŞAĞI TAŞKENT"),
    "46923920B25910914763137": ("Sinta", "İNÖNÜ/İNÖNÜ"),
    "46923920B82441247909764": ("Skylloura", "ALAYKÖY/YILMAZKÖY"),
    "46923920B58685009423806": ("Spathariko", "İSKELE/ÖTÜKEN"),
    "46923920B68545316730877": ("Strongylos", "VADİLİ/TURUNÇLU"),
    "46923920B94821377513364": ("Sygkrasi", "İSKELE/SINIRÜSTÜ"),
    "46923920B59852999590656": ("Sysklipos", "DİKMEN/AKÇİÇEK"),
    "46923920B83443733114652": ("Tavrou", "MEHMETÇİK/PAMUKLU"),
    "46923920B22613060517459": ("Tremetousia", "DEĞİRMENLİK/ERDEMLİ"),
    "46923920B99382767312259": ("Trimithi", "GİRNE/EDREMİT"),
    "46923920B43934732420538": ("Trypimeni", "SERDARLI/TİRMEN"),
    "46923920B59196916955997": ("Tymvou", "DEĞİRMENLİK/KIRKLAR"),
    "46923920B45317993304691": ("Vasileia", "LAPTA (GİRNE)/KARŞIYAKA"),
    "46923920B59357153035483": ("Vasili", "YENİ ERENKÖY/GELİNCİK"),
    "46923920B79733432634450": ("Vatili", "VADİLİ/VADİLİ"),
    "46923920B87437157702699": ("Vitsada", "SERDARLI/PINARLI"),
    "46923920B93195640595309": ("Vokolida", "MEHMETÇİK/BAFRA"),
    "46923920B56038902330980": ("Voni", "DEĞİRMENLİK/GÖKHAN"),
    "46923920B71614438662685": ("Vothylakas", "YENİ ERENKÖY/DERİNCE"),
    "46923920B84175879227777": ("Vouno", "DİKMEN/YUKARI TAŞKENT"),
    "46923920B79378418277595": ("Xerovounos", "LEFKE/YEŞİLIRMAK"),
}

# What a polygon of several quarters is, and how the evidence placed them.
NOTES = {
    "46923920B56788308456175": (
        "The boundary file draws the Republic's communities of Agios Ilias, Bogazi and Monarga as one "
        "polygon (GeoNames' points for all three communities lie in it); it carries the census's three "
        "quarters for them: Yarköy, Boğaz and Boğaztepe."),
    "46923920B90668943493632": (
        "Akanthou is Tatlısu municipality, whose three quarters (Aktunç, Küçükerenköy, Yalı) the census "
        "counts apart; OpenStreetMap's outline of the municipality lies 99% in this polygon."),
    "46923920B15488277877643": (
        "The fifteen quarters of Gazimağusa (Famagusta) municipality other than Tuzla (the village of "
        "Enkomi) and Mutluyaka (Stylloi), each lying in this polygon by OpenStreetMap's outlines "
        "(86-100% of each quarter's area, 93-100% of its mapped buildings). Some buildings of Sakarya, "
        "Karakol and Çanakkale stand in the Enkomi and Deryneia polygons next door: about 2% of this "
        "figure, by their share of the buildings."),
    "46923920B64844622441299": (
        "Kaplıca, the village of Davlos, and the hamlet of Kantara below Kantara castle, which the "
        "census counts as a quarter of its own (21 residents) and GeoNames and OpenStreetMap place in "
        "this polygon."),
    "46923920B75200378291295": (
        "Serhatköy, the village of Fyllia, and Gayretköy, the village of Avlona, whose houses lie in "
        "this polygon by GeoNames', Wikidata's and OpenStreetMap's points and by 90% of OpenStreetMap's "
        "outline of it; the smaller polygon labelled Avlona beside it holds neither village."),
    "46923920B26333175037014": (
        "Alsancak municipality's quarters Yayla, Çağlayan and Yeşilova, which are Karavas (93-99% "
        "inside by OpenStreetMap's outlines). Its other quarters are the villages of Ella (Yeşiltepe), "
        "Ftericha (Ilgaz), and Palaiosofos and Motides (one quarter, Malatya - İncesu)."),
    "46923920B41676558074930": (
        "Gemikonağı (Karavostasi), Yedidalga (Potamos tou Kampou) and Denizli (Xeros): villages the "
        "Republic's community list does not keep apart from Karavostasi, whose OpenStreetMap outlines "
        "lie 91-100% in this polygon."),
    "46923920B20243992884618": (
        "Girne municipality's town quarters, Aşağı Girne and Yukarı Girne (94-100% of their mapped "
        "buildings inside). The municipality's other quarters are villages with polygons of their own; "
        "Aşağı Karaman (675 residents), which no evidence places, is not in this figure."),
    "46923920B14813142167534": (
        "Gönyeli municipality's quarters Gönyeli and Yenikent (99-100% of their mapped buildings in "
        "this polygon); its third, Kanlıköy, is the village of Kanli. Fringes of neighbouring quarters "
        "(Ortaköy, Aydemet, Alayköy, Aşağı Dikmen) also reach into the polygon by OpenStreetMap's "
        "outlines; their residents there, at most about a tenth of this figure by building counts, are "
        "not in it."),
    "46923920B79735080950655": (
        "Değirmenlik municipality's six town quarters (Bahçelievler, Başpınar, Camialtı, Mehmetçik, "
        "Saray, Tepebaşı), 94-100% inside by OpenStreetMap's outlines; its other quarters are villages "
        "with polygons of their own."),
    "46923920B16403791533064": (
        "The seven town quarters of Lapta municipality in the census's Girne sub-district, 95-100% "
        "inside by OpenStreetMap's outlines; the eighth, Karşıyaka, is the village of Vasileia, and the "
        "municipality's quarters in Çamlıbel sub-district are villages with polygons of their own."),
    "46923920B39754802683787": (
        "Güzelyurt municipality's town quarters Lala Mustafa Paşa, Piyale Paşa and İsmet Paşa, and the "
        "hamlet of Yuvacık (Chrysiliou), 96-99% of whose mapped buildings stand in this polygon; the "
        "municipality's other quarters are villages with polygons of their own."),
    "46923920B57718110047043": (
        "Dipkarpaz municipality's three town quarters (Ersin Paşa, Polat Paşa, Sancar Paşa); its fourth, "
        "Kaleburnu, is the village of Galinoporni."),
    "46923920B51635093907886": (
        "Karaoğlanoğlu, the village of Agios Georgios, now a quarter of Girne municipality: 82% of "
        "OpenStreetMap's outline of it, and 90% of its mapped buildings on land, lie in this polygon."),
}

# Communities the Republic's 2021 census lists with no residents -- the part
# under the Government's control is empty -- and the census in the north
# counts as inhabited. Written only once cyprus_census.json gives them a gap
# rather than its 0 (shared.patch), or the two counts would sit side by side.
ZERO_IN_REPUBLIC: dict[str, tuple[str, ...]] = {
    "46923920B91087779274595": ("Louroukina", "AKINCILAR/AKINCILAR"),
    "46923920B9088194369426": ("Pano Zodeia", "GÜZELYURT/YUKARI BOSTANCI"),
}

WHY_NO_QUARTER = ("That census lists no quarter for this village ({tr} in its own naming), and nor "
                  "does its comparison of 2011 with the 2006 census, quarter by quarter; its 250 "
                  "quarters are where its 286,257 residents live, so it counts no one here as a "
                  "quarter of its own, and does not say whether anyone living here is counted in a "
                  "neighbouring one.")
# Northern polygons with no figure here: (label, why). Each reason follows a
# sentence naming the census in the north, which "that census" refers to.
LEFT_OFF: dict[str, tuple[str, str]] = {
    "46923920B71811128536936": ("Trachonas", (
        "That census's quarters of north Nicosia do not follow this polygon's lines. By "
        "OpenStreetMap's outlines and buildings Kızılay, Marmara and Taşkınköy (10,463 residents) lie "
        "almost wholly in it, but so do 44% of Göçmenköy's mapped buildings, 48% of Kumsal's and parts "
        "of Yenişehir's and Ortaköy's: no sum of whole quarters is the polygon's population.")),
    "46923920B2976518119869": ("Ortakioï", (
        "That census's quarters of north Nicosia do not follow this polygon's lines. Ortaköy (8,868 "
        "residents) has 86% of its mapped buildings here, but 56% of Göçmenköy's and 23% of Kumsal's "
        "are here too: no sum of whole quarters is the polygon's population.")),
    "46923920B85136596681423": ("Mandres Lefkosias", (
        "Hamitköy (5,338 residents) is this village and lies wholly in the polygon, but so does the "
        "northern edge of Küçük Kaymaklı, 295 of its 2,967 buildings mapped in OpenStreetMap, about a "
        "thousand residents by their share: Hamitköy's count would leave them out.")),
    "46923920B46036306691539": ("Agios Amvrosios Keryneias", (
        "That census's Esentepe quarter (1,754 residents) spans this polygon and Trapeza's: of its "
        "buildings mapped in OpenStreetMap, 48% stand here and 46% in Trapeza.")),
    "46923920B69284380366179": ("Trapeza", (
        "Beşparmak (30 residents) is that census's quarter for this village, but nearly half of the "
        "Esentepe quarter's mapped buildings stand in this polygon too, so Beşparmak's count is not "
        "its population.")),
    "46923920B19762948788890": ("Agirda", (
        "That census's Boğazköy quarter (1,943 residents) spans Agirda and Kato Dikomo: "
        "OpenStreetMap's outline of it lies 62% and 32% in them, and its lower part, Aşağı Boğazköy, "
        "is in Kato Dikomo's. Neither Ağırdağ's count (745) nor Aşağı Dikmen's is its polygon's "
        "population.")),
    "46923920B88544101025022": ("Kato Dikomo", (
        "Aşağı Dikmen (3,553 residents) is this village, but the Boğazköy quarter (1,943) spans it and "
        "Agirda (OpenStreetMap's outline lies 32% here, with its lower part, Aşağı Boğazköy), so Aşağı "
        "Dikmen's count is not the polygon's population.")),
    "46923920B69759348119058": ("Trachoni Lefkosias", (
        "That census counts the villages of Trachoni (Demirhan, 530 residents) and Neo Chorio "
        "(Minareliköy, 1,334) apart, but GeoNames', Wikidata's and OpenStreetMap's points all put "
        "Demirhan's houses in the polygon labelled Neo Chorio Lefkosias, 170-320 m from this one, while "
        "OpenStreetMap's outline of Demirhan lies 73% here: which polygon its people live in is not "
        "settled.")),
    "46923920B66080060660819": ("Neo Chorio Lefkosias", (
        "Minareliköy (1,334 residents) is this village, but GeoNames', Wikidata's and OpenStreetMap's "
        "points all put the houses of Demirhan (Trachoni, 530) in this polygon too, while "
        "OpenStreetMap's outline of Demirhan lies mostly in Trachoni's: which polygon its people live "
        "in is not settled.")),
    "46923920B22969958505776": ("Stylloi", (
        "Mutluyaka (407 residents) is this village, but OpenStreetMap's outline of the quarter holds a "
        "cluster of 86 buildings inside the polygon labelled Limnia, so Mutluyaka's count is not this "
        "polygon's population.")),
    "46923920B85062050143920": ("Limnia", (
        "Mormenekşe (1,033 residents) is this village, but a cluster of 86 buildings of the Mutluyaka "
        "quarter (Stylloi) stands in this polygon too, by OpenStreetMap's outlines, so Mormenekşe's "
        "count is not the polygon's population.")),
    "46923920B99720560567436": ("Peristerona Ammochostou", (
        "That census counts this village and Pigi as one quarter, Alaniçi (860 residents), which the "
        "map draws as two polygons.")),
    "46923920B21676423374692": ("Pigi", (
        "That census counts this village and Peristerona as one quarter, Alaniçi (860 residents), "
        "which the map draws as two polygons.")),
    "46923920B16450205187108": ("Palaiosofos", (
        "That census counts Malatya (this village) and İncesu (Motides) as one quarter, Malatya - "
        "İncesu (180 residents), which the map draws as two polygons.")),
    "46923920B57620727838735": ("Motides", (
        "That census counts İncesu (this village) and Malatya (Palaiosofos) as one quarter, Malatya - "
        "İncesu (180 residents), which the map draws as two polygons.")),
    "46923920B7341573367823": ("Ftericha", (
        "Ilgaz (72 residents) is this village, but a quarter of the buildings OpenStreetMap maps in the "
        "Malatya - İncesu quarter's outline stand in this polygon, so Ilgaz's count is not all of its "
        "residents.")),
    "46923920B51848202529544": ("Karmi", (
        "That census counts the old village as Karaman (Yukarı Karmi), 55 residents, and the lower part "
        "of its land as Aşağı Karaman (675), a quarter of Girne municipality that no evidence places for "
        "certain (Wikidata's point for Karaman falls in the lower part of this polygon), so neither "
        "count alone is the polygon's population.")),
    "46923920B79471002373027": ("Templos", (
        "Zeytinlik Köy and Zeytinlik Kesim (1,090 residents together) are this village, but buildings "
        "of Kyrenia's Yukarı Girne quarter, some 150 residents by their share, stand in this polygon "
        "too.")),
    "46923920B3571581876318": ("Thermeia", (
        "Doğanköy (868 residents) is this village, but only 79% of its mapped buildings stand in this "
        "small polygon (0.8 km2); the rest are in Kazafani's and Kyrenia's.")),
    "46923920B35244398471877": ("Kazafani", (
        "Ozanköy and Karakum (3,792 residents together) are the villages of Kazafani and Karakoumi, "
        "which the boundary file draws as this one polygon, but 10 of Karakum's 60 mapped buildings "
        "stand in Kyrenia's polygon, and some of Doğanköy's, Çatalköy's, Beylerbeyi's and Yukarı "
        "Girne's stand in this one.")),
    "46923920B81569607832165": ("Belapais", (
        "Beylerbeyi (918 residents) is this village, but 43 of its 641 mapped buildings stand in "
        "Kazafani's polygon, and 20 of Ozanköy's in this one.")),
    "46923920B27145570377181": ("Pano Dikomo", (
        "Yukarı Dikmen (416 residents) is this village, but 7 of the 551 mapped buildings of Aşağı "
        "Dikmen, the larger village below it, stand in this polygon too.")),
    "46923920B44802407724135": ("Agkomi Ammochostou", (
        "Tuzla (2,645 residents) is the village of Enkomi, but buildings of Famagusta's Sakarya and "
        "Karakol quarters, some 470 residents by their share, stand in this polygon too.")),
    "46923920B17336171931984": ("Syrianochori", (
        "Güzelyurt municipality's Yayla quarter (850 residents) is this village, but 21% of its mapped "
        "buildings stand in Morfou's polygon.")),
    "46923920B71155103656071": ("Trikomo", (
        "İskele municipality's quarters include İskele (1,948 residents) and Cevizli (1,110), which no "
        "evidence places: Perivolia (Bahçeler) has no quarter of its own, so Cevizli may be Perivolia "
        "or part of Trikomo, and İskele's count alone may not be this polygon's population.")),
    "46923920B19952645693487": ("Perivolia Trikomou", (
        "That census lists no quarter named for this village (Bahçeler); İskele municipality's Cevizli "
        "quarter (1,110 residents), which no evidence places, may be it or part of Trikomo.")),
    "46923920B38965206429869": ("Avlona", (
        "The village of Avlona (Gayretköy, 367 residents) lies in the polygon labelled Fyllia, by "
        "GeoNames', Wikidata's and OpenStreetMap's points and by 90% of OpenStreetMap's outline of "
        "Gayretköy; its count is there.")),
    "46923920B60275250769381": ("Agia Marina Skyllouras", WHY_NO_QUARTER.format(tr="Gürpınar")),
    "46923920B58040369726665": ("Agios Georgios Soleas", WHY_NO_QUARTER.format(tr="Madenliköy")),
    "46923920B8865059682023": ("Agios Ioannis Selemani", WHY_NO_QUARTER.format(tr="Süleymaniye")),
    "46923920B64835616919063": ("Alevga", WHY_NO_QUARTER.format(tr="Alevkayası")),
    "46923920B28653091355318": ("Ammadies", WHY_NO_QUARTER.format(tr="Günebakan")),
    "46923920B69592041186855": ("Dyo Potamoi", WHY_NO_QUARTER.format(tr="İkidere")),
    "46923920B95052440954476": ("Frodisia", WHY_NO_QUARTER.format(tr="Yağmuralan")),
    "46923920B41086018803178": ("Galini", WHY_NO_QUARTER.format(tr="Ömerli")),
    "46923920B20193016295799": ("Katydata", WHY_NO_QUARTER.format(
        tr="Ayyorgi, the Agios Georgios of Lefka")),
    "46923920B39759064245656": ("Kokkina", WHY_NO_QUARTER.format(tr="Erenköy")),
    "46923920B73680512248487": ("Margo", WHY_NO_QUARTER.format(tr="Margo")),
    "46923920B47303866383678": ("Petra", WHY_NO_QUARTER.format(tr="Taşköy")),
    "46923920B75368188924059": ("Pyrogi", WHY_NO_QUARTER.format(tr="Gaziler")),
    "46923920B45268143409663": ("Selladi tou Appi", WHY_NO_QUARTER.format(tr="Selçuklu")),
    "46923920B52002347954875": ("Variseia", WHY_NO_QUARTER.format(tr="Şirinköy")),
    "46923920B3651826109354": ("Artemi", WHY_NO_QUARTER.format(tr="Arıdamı")),
}

# Communities both censuses count a part of: the Republic's 2021 census
# counts the part under its Government's control, and its count stands on
# the polygon; nothing is written here for them. (label, the Republic's 2021
# count, checked against cyprus_census.json)
BOTH: dict[str, tuple[str, int]] = {
    "46923920B2904001069887": ("Lefkosia", 56479),
    "46923920B17515684625849": ("Agios Dometios", 12906),
    "46923920B48961032543563": ("Pyla", 3869),
    "46923920B91768316626560": ("Pergamos", 207),
    "46923920B61147384181121": ("Acheritou", 1901),
}

# Census quarters on no polygon: the district they lie in, and the polygon
# (in LEFT_OFF or BOTH) whose entry says why, or "" where nothing places them
# more finely than their municipality.
UNPLACED: dict[str, tuple[str, str]] = {
    **{f"LEFKOŞA/{q}": ("Nicosia", "Lefkosia") for q in (
        "ABDİ ÇAVUŞ", "AKKAVUK", "ARABAHMET", "AYYILDIZ", "ÇAĞLAYAN", "HAYDARPAŞA", "İBRAHİMPAŞA",
        "İPLİKPAZARI", "KAFESLİ", "KARAMANZADE", "KÖŞKLÜÇİFTLİK", "KÜÇÜK KAYMAKLI", "MAHMUTPAŞA",
        "SELİMİYE", "YENİCAMİ", "YENİŞEHİR")},
    "LEFKOŞA/AYDEMET": ("Nicosia", "Agios Dometios"),
    "LEFKOŞA/KIZILAY": ("Nicosia", "Trachonas"),
    "LEFKOŞA/MARMARA": ("Nicosia", "Trachonas"),
    "LEFKOŞA/TAŞKINKÖY": ("Nicosia", "Trachonas"),
    "LEFKOŞA/KUMSAL": ("Nicosia", "Trachonas"),
    "LEFKOŞA/GÖÇMENKÖY": ("Nicosia", "Ortakioï"),
    "LEFKOŞA/ORTAKÖY": ("Nicosia", "Ortakioï"),
    "LEFKOŞA/HAMİTKÖY": ("Nicosia", "Mandres Lefkosias"),
    "DEĞİRMENLİK/MİNARELİKÖY": ("Nicosia", "Neo Chorio Lefkosias"),
    "DEĞİRMENLİK/DEMİRHAN": ("Nicosia", "Trachoni Lefkosias"),
    "PİLE/PİLE": ("Larnaca", "Pyla"),
    "BEYARMUDU/BEYARMUDU": ("Larnaca", "Pergamos"),
    "BEYARMUDU/GÜVERCİNLİK": ("Famagusta", "Acheritou"),
    "GAZİMAĞUSA/TUZLA": ("Famagusta", "Agkomi Ammochostou"),
    "GAZİMAĞUSA/MUTLUYAKA": ("Famagusta", "Stylloi"),
    "YENİ BOĞAZİÇİ/MORMENEKŞE": ("Famagusta", "Limnia"),
    "YENİ BOĞAZİÇİ/ALANİÇİ": ("Famagusta", "Peristerona Ammochostou"),
    "İSKELE/İSKELE": ("Famagusta", "Trikomo"),
    "İSKELE/CEVİZLİ": ("Famagusta", ""),
    "GÜZELYURT/YAYLA": ("Nicosia", "Syrianochori"),
    "GİRNE/AŞAĞI KARAMAN": (KYRENIA, ""),
    "GİRNE/DOĞANKÖY": (KYRENIA, "Thermeia"),
    "GİRNE/OZANKÖY": (KYRENIA, "Kazafani"),
    "GİRNE/KARAKUM": (KYRENIA, "Kazafani"),
    "GİRNE/BEYLERBEYİ": (KYRENIA, "Belapais"),
    "DİKMEN/YUKARI DİKMEN": (KYRENIA, "Pano Dikomo"),
    "GİRNE/ZEYTİNLİK KESİM": (KYRENIA, "Templos"),
    "GİRNE/ZEYTİNLİK KÖY": (KYRENIA, "Templos"),
    "ALSANCAK/ILGAZ": (KYRENIA, "Ftericha"),
    "ALSANCAK/MALATYA - İNCESU": (KYRENIA, "Palaiosofos"),
    "DİKMEN/AŞAĞI DİKMEN": (KYRENIA, "Kato Dikomo"),
    "DİKMEN/AĞIRDAĞ": (KYRENIA, "Agirda"),
    "DİKMEN/BOĞAZKÖY": (KYRENIA, "Agirda"),
    "ESENTEPE/ESENTEPE": (KYRENIA, "Agios Amvrosios Keryneias"),
    "ESENTEPE/BEŞPARMAK": (KYRENIA, "Trapeza"),
    "KARAMAN (YUKARI KARMİ)/KARAMAN (YUKARI KARMİ)": (KYRENIA, "Karmi"),
}

# The binding rule (module docstring). A quarter is placed in a polygon when
# 85% of its mapped buildings stand in it, or, where its buildings were not
# all counted, 70% of its outline lies in it with the village's point; and a
# polygon carries the sum of the quarters placed in it only when the
# residents on the wrong side of its lines -- its quarters' outside it, other
# quarters' inside it -- come to at most this share of that sum.
MAX_OVERLAP = 0.10
# That share as measured, for every polygon where any was found, and for the
# polygons left off because of it (the rest of LEFT_OFF are left for other
# reasons: a quarter spanning two polygons, one quarter for two villages, no
# quarter at all). OpenStreetMap's buildings in cyprus_north_probe's boxes
# (runs 0c9bd20 and 9c2da10), each quarter's residents spread evenly over
# its mapped buildings, and only where five or more of them stand across the
# line; a quarter whose outline was not counted whole is placed by area and
# its own buildings across a line are not estimated.
OVERLAP: dict[str, tuple[str, float]] = {
    "46923920B85136596681423": ("Mandres Lefkosias", 0.224),   # 5,338: 31 out, 1,165 in
    "46923920B44802407724135": ("Agkomi Ammochostou", 0.177),  # 2,645: 0 out, 469 in
    "46923920B79471002373027": ("Templos", 0.173),             # 1,090: 31 out, 158 in
    "46923920B35244398471877": ("Kazafani", 0.150),            # 3,792: 168 out, 401 in
    "46923920B81569607832165": ("Belapais", 0.119),            # 918: 62 out, 48 in
    "46923920B27145570377181": ("Pano Dikomo", 0.109),         # 416: 0 out, 45 in
    "46923920B78041797088340": ("Nikitas", 0.078),             # 505: 0 out, 40 in
    "46923920B14813142167534": ("Kioneli", 0.046),             # 17,045: 114 out, 664 in
    "46923920B73133986650844": ("Argaki", 0.041),              # 1,008: 0 out, 42 in
    "46923920B20243992884618": ("Keryneia", 0.035),            # 20,851: 541 out, 198 in
    "46923920B56157666761112": ("Alayköy", 0.030),             # 2,777: 59 out, 23 in
    "46923920B11647519105740": ("Agios Epiktitos", 0.027),     # 5,110: 138 out, 0 in
    "46923920B4985084471398": ("Kato Zodeia", 0.022),          # 1,822: 40 out, 0 in
    "46923920B15488277877643": ("Ammochostos", 0.018),         # 37,868: 700 out, 0 in
    "46923920B39754802683787": ("Morfou", 0.017),              # 7,465: 92 out, 34 in
    "46923920B84708400671300": ("Kalo Chorio Kapouti", 0.007),  # 2,305: 0 out, 17 in
}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

# Below this many residents no sex ratio is shown, as in cyprus_census: 21
# people with 19 men would read as a ratio of 950.
MIN_RESIDENTS = 50
# A polygon in the north given no count here displaces an encyclopaedia's
# figure for it from before the census taken in 2011 (the build's
# ``displaces_before``). That census counted the whole north, so an older
# figure -- Wikidata's 1973 counts, the last census of the whole island, or a
# later one like the 85 of 1976 it gives Agios Nikolaos of Lefka -- is not the
# polygon's population now. A count is never displaced, nor a figure of 2011
# or later.
DISPLACES_BEFORE = YEAR
WHO_CAP = WHO[0].upper() + WHO[1:]
# Quarters the census attaches to no municipality (Tablo 3's footnote).
NO_MUNICIPALITY = {"pile", "karamanyukarikarmi", "kantara"}
# Lapta municipality has quarters in two sub-districts, and Tablo 3 names it
# after each.
MUNICIPALITY_NAME = {"laptagirne": "Lapta", "laptacamlibel": "Lapta"}

NOT_REPUBLIC = ("The Republic of Cyprus's censuses since 1974 have been taken only in the areas "
                "under the effective control of its Government, which do not include this "
                "community.")
ABOUT = (f"The count is of usual residents (de jure), by {WHO}; the Republic of Cyprus's "
         "censuses since 1974 have not been taken here.")
WHY_NO_AGES = (f"{WHO_CAP} publishes ages by sub-district (bucak) at the finest (its Tablo 4), "
               "which is no community's, so no community has a median age; the Republic of "
               "Cyprus's censuses since 1974 have not been taken here.")
WHY_NO_COMPOSITION = (
    f"Neither census publishes it for this community. {WHO_CAP} published nine population "
    "tables -- by sex, age, citizenship and birthplace -- and none of religion, language or "
    "ethnicity; its citizenship (tabiiyet) is by district (ilçe) only. The Republic of Cyprus's "
    "censuses since 1974 have not been taken here.")
KYRENIA_OUTSIDE = ("Kyrenia district has been outside the effective control of the Government of "
                   "the Republic of Cyprus since 1974, and the Republic's censuses since then have "
                   "not counted it.")


def spec_key(spec: str) -> str:
    """'GİRNE/AŞAĞI GİRNE', a quarter as the tables above write it -> its key."""
    belediye, _, mahalle = spec.partition("/")
    return key(belediye, mahalle)


def tr_title(name: str) -> str:
    """'AŞAĞI GİRNE' -> 'Aşağı Girne', 'İSKELE' -> 'İskele', 'ILGAZ' -> 'Ilgaz':
    Turkish capitals, whose I and İ lower-case to ı and i."""
    low = name.replace("I", "ı").replace("İ", "i").lower()
    return re.sub(r"(^|[\s(\-])(\w)",
                  lambda m: m.group(1) + {"i": "İ", "ı": "I"}.get(m.group(2), m.group(2).upper()),
                  low)


def count_of(n: float, one: str, many: str | None = None) -> str:
    """'1 man', '2 men', '0 women'."""
    return f"{n:,.0f} {one if round(n) == 1 else (many or one + 's')}"


def has_value(field: Any) -> bool:
    return isinstance(field, dict) and field.get("value") is not None


def check_tables(t3: dict[str, Any], t1: dict[str, dict[str, float]],
                 ages: dict[tuple[str, str | None], dict[str, Any]],
                 cit: dict[str, dict[str | None, float]]) -> None:
    """The four tables describe the same 286,257 people: Tablo 1's districts,
    Tablo 4's districts and sub-districts and Tablo 5's districts are Tablo
    3's, sex by sex."""
    if set(t1) - {"total"} != set(t3["ilces"]):
        raise SystemExit(f"cyprus_north_census: Tablo 1 names {sorted(t1)}, Tablo 3 {sorted(t3['ilces'])}")
    for name, unit in [("total", t3["total"]), *t3["ilces"].items()]:
        for sex in ("total", "men", "women"):
            check_sum(t1[name][sex], unit[sex], f"cyprus_north_census: Tablo 1 against Tablo 3, {name}, {sex}")
        check_sum(ages[(name, None)]["total"], unit["total"],
                  f"cyprus_north_census: Tablo 4 against Tablo 3, {name}")
        check_sum(cit[name][None], unit["total"], f"cyprus_north_census: Tablo 5 against Tablo 3, {name}")
    in_t4 = {(i, b) for i, b in ages if b is not None}
    in_t3 = {(b["ilce"], k) for k, b in t3["bucaks"].items()}
    if in_t4 != in_t3:
        raise SystemExit(f"cyprus_north_census: Tablo 4's sub-districts {sorted(in_t4)} are not "
                         f"Tablo 3's {sorted(in_t3)}")
    for (ilce, bucak) in in_t4:
        for sex in ("total", "men", "women"):
            check_sum(ages[(ilce, bucak)][sex], t3["bucaks"][bucak][sex],
                      f"cyprus_north_census: Tablo 4 against Tablo 3, {bucak}, {sex}")


def check_binding(t3: dict[str, Any], admin1: list[dict[str, Any]],
                  admin2: list[dict[str, Any]]) -> dict[str, str]:
    """The tables above against Tablo 3 and the drawn polygons. Each polygon is
    in one table under the label the map draws it with; each quarter of
    Tablo 3 is placed exactly once. Returns the map district each quarter
    lies in, by key."""
    by_id = {s["id"]: s for s in admin2}
    district = {s["id"]: s["name"] for s in admin1}
    seen: dict[str, str] = {}
    for name, entries in (("BIND", BIND), ("ZERO_IN_REPUBLIC", ZERO_IN_REPUBLIC),
                          ("LEFT_OFF", LEFT_OFF), ("BOTH", BOTH)):
        for sid, entry in entries.items():
            if sid in seen:
                raise SystemExit(f"cyprus_north_census: polygon {sid} is in {seen[sid]} and in {name}")
            seen[sid] = name
            shape = by_id.get(sid)
            if shape is None:
                raise SystemExit(f"cyprus_north_census: {name} names polygon {sid} ({entry[0]}), "
                                 "which the map does not draw")
            if shape["name"] != entry[0]:
                raise SystemExit(f"cyprus_north_census: {name} calls polygon {sid} {entry[0]!r}; "
                                 f"the map labels it {shape['name']!r}")
            if shape.get("parent") not in district:
                raise SystemExit(f"cyprus_north_census: polygon {sid} ({entry[0]}) is in no district")
    if set(NOTES) - set(BIND):
        raise SystemExit(f"cyprus_north_census: NOTES for unbound polygons {sorted(set(NOTES) - set(BIND))}")
    several = [entry[0] for sid, entry in BIND.items() if len(entry) > 2 and sid not in NOTES]
    if several:
        raise SystemExit(f"cyprus_north_census: polygons of several quarters with no note: {several}")
    for sid, (label, share) in OVERLAP.items():
        table = "BIND" if sid in BIND else "LEFT_OFF" if sid in LEFT_OFF else None
        if table is None or (BIND.get(sid) or LEFT_OFF.get(sid))[0] != label:
            raise SystemExit(f"cyprus_north_census: OVERLAP names {label} ({sid}), which neither BIND nor "
                             "LEFT_OFF has under that label")
        if table == "BIND" and share > MAX_OVERLAP:
            raise SystemExit(f"cyprus_north_census: {label} is bound with {share:.1%} of its count across "
                             f"its lines, over the {MAX_OVERLAP:.0%} the rule allows")
        if table == "LEFT_OFF" and share <= MAX_OVERLAP:
            raise SystemExit(f"cyprus_north_census: {label} is left off for an overlap of {share:.1%}, "
                             f"which the rule's {MAX_OVERLAP:.0%} allows")
    where: dict[str, str] = {}

    def place(spec: str, dname: str, what: str) -> None:
        k = spec_key(spec)
        if k not in t3["quarters"]:
            raise SystemExit(f"cyprus_north_census: {what} names {spec!r}, which Tablo 3 does not list")
        if k in where:
            raise SystemExit(f"cyprus_north_census: {spec!r} is placed twice")
        where[k] = dname

    for entries, what in ((BIND, "BIND"), (ZERO_IN_REPUBLIC, "ZERO_IN_REPUBLIC")):
        for sid, (label, *specs) in entries.items():
            if not specs:
                raise SystemExit(f"cyprus_north_census: {what} gives {label} no quarter")
            for spec in specs:
                place(spec, district[by_id[sid]["parent"]], f"{what} ({label})")
    explained = {entry[0]: sid for entries in (LEFT_OFF, BOTH) for sid, entry in entries.items()}
    for spec, (dname, polygon) in UNPLACED.items():
        if dname not in district.values():
            raise SystemExit(f"cyprus_north_census: UNPLACED puts {spec!r} in {dname!r}, no district")
        if polygon:
            sid = explained.get(polygon)
            if sid is None:
                raise SystemExit(f"cyprus_north_census: UNPLACED sends {spec!r} to {polygon!r}, which "
                                 "is in neither LEFT_OFF nor BOTH")
            if district[by_id[sid]["parent"]] != dname:
                raise SystemExit(f"cyprus_north_census: UNPLACED puts {spec!r} in {dname}, but "
                                 f"{polygon} is in {district[by_id[sid]['parent']]}")
        place(spec, dname, "UNPLACED")
    missing = sorted(set(t3["quarters"]) - set(where))
    if missing:
        raise SystemExit(f"cyprus_north_census: quarters placed nowhere: {missing}")
    return where


def check_kyrenia(t3: dict[str, Any], where: dict[str, str]) -> float:
    """Kyrenia district holds every quarter of the census's Girne district and
    no other, so its population is that district's; returns it. Stops the
    run if any binding says otherwise."""
    girne = {k for k, q in t3["quarters"].items() if q["ilce"] == GIRNE}
    inside = {k for k, dname in where.items() if dname == KYRENIA}
    if girne != inside:
        raise SystemExit(f"cyprus_north_census: Kyrenia district holds {sorted(inside - girne)} of other "
                         f"districts and not {sorted(girne - inside)} of Girne's")
    total = sum(t3["quarters"][k]["total"] for k in inside)
    check_sum(total, t3["ilces"][GIRNE]["total"], "cyprus_north_census: the quarters in Kyrenia district")
    return total


def check_republic(republic: dict[str, dict[str, Any]]) -> set[str]:
    """The Republic's 2021 records (cyprus_census.json, by shape id) against
    the tables: nothing here is written where it counts anyone. Returns the
    ZERO_IN_REPUBLIC polygons it now leaves a gap on, which are written."""
    def population(sid: str) -> Any:
        rec = republic.get(sid)
        if rec is None:
            raise SystemExit(f"cyprus_north_census: cyprus_census.json has no record for polygon {sid}")
        return rec.get("population")

    for name, entries in (("BIND", BIND), ("LEFT_OFF", LEFT_OFF)):
        counted = [entry[0] for sid, entry in entries.items() if has_value(population(sid))]
        if counted:
            raise SystemExit(f"cyprus_north_census: {name} has polygons the Republic's census counts: {counted}")
    for sid, (label, count) in BOTH.items():
        pop = population(sid)
        if not has_value(pop) or pop["value"] != count:
            raise SystemExit(f"cyprus_north_census: BOTH has {label} at {count:,}; cyprus_census.json "
                             f"gives {pop}")
    write = set()
    for sid, (label, *_) in ZERO_IN_REPUBLIC.items():
        pop = population(sid)
        if has_value(pop) and pop["value"] > 0:
            raise SystemExit(f"cyprus_north_census: the Republic's census counts {pop['value']} in {label}")
        if has_value(pop):
            log(f"  {label}: cyprus_census.json still gives it {pop['value']}; not written until it "
                "gives a gap (shared.patch)")
        else:
            write.add(sid)
    return write


def republic_records() -> dict[str, dict[str, Any]]:
    """cyprus_census.json's second-level records by shape id."""
    path = PROCESSED / "cyprus_census.json"
    if not path.exists():
        raise SystemExit(f"cyprus_north_census: {path} is missing; cyprus_census runs first")
    return {r["shape_id"]: r for r in read_json(path, []) if r.get("level") == "admin2"}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def cite(name: str, field: str, url: str) -> dict[str, Any]:
    return {"field": field, "name": SOURCE.format(title=TITLES[name]), "url": url, "page": PAGE,
            "year": YEAR, "license": LICENCE}


def quarter_phrase(q: dict[str, Any]) -> str:
    """'Dilekkaya, a quarter (mahalle) of Değirmenlik municipality'."""
    bel = fold(q["belediye"])
    if bel in NO_MUNICIPALITY:
        return f"{tr_title(q['mahalle'])}, a quarter (mahalle) of no municipality"
    town = MUNICIPALITY_NAME.get(bel) or tr_title(q["belediye"])
    return f"{tr_title(q['mahalle'])}, a quarter (mahalle) of {town} municipality"


def ratio_fields(men: float, women: float, source: str) -> dict[str, Any]:
    """sex_ratio (and its note), as cyprus_census writes it."""
    total = men + women
    if total < MIN_RESIDENTS:
        return {"sex_ratio": gap(NOT_AVAILABLE, (
            f"{WHO_CAP} counts {count_of(total, 'resident')} here ({count_of(men, 'man', 'men')} and "
            f"{count_of(women, 'woman', 'women')}); below {MIN_RESIDENTS} residents a ratio of men to "
            "women describes a handful of people, and is not shown."))}
    if not women:
        return {"sex_ratio": gap(NOT_AVAILABLE, (
            f"{WHO_CAP} counts {count_of(men, 'man', 'men')} and no women here, so a ratio of men to "
            "women is not defined."))}
    out: dict[str, Any] = {"sex_ratio": sex_ratio(men, women, year=YEAR, source=source)}
    if not 70 <= out["sex_ratio"]["value"] <= 140:
        out["sex_ratio_note"] = (f"As the census counts it: {count_of(men, 'man', 'men')} and "
                                 f"{count_of(women, 'woman', 'women')}.")
    return out


def community(sid: str, shape: dict[str, Any], dname: str, qs: list[dict[str, Any]], lead: str,
              tail: str, src: dict[str, str], urls: dict[str, str]) -> dict[str, Any]:
    """The record of a polygon that carries the sum of ``qs``."""
    men = sum(q["men"] for q in qs)
    women = sum(q["women"] for q in qs)
    total = sum(q["total"] for q in qs)
    check_sum(men + women, total, f"cyprus_north_census: the sexes of {shape['name']}")
    return record(
        f"CYP-north-{YEAR}-{sid}", shape["name"], level="admin2", parent="CYP", country="CYP",
        match_by="shape_id", shape_id=sid, parent_name=dname,
        population=measure(int(total), year=YEAR, source=src["mahalle"]),
        population_note=f"{lead} {tail}",
        median_age=gap(NOT_AVAILABLE, WHY_NO_AGES),
        religion=gap(NOT_AVAILABLE, WHY_NO_COMPOSITION), language=gap(NOT_AVAILABLE, WHY_NO_COMPOSITION),
        ethnicity=gap(NOT_AVAILABLE, WHY_NO_COMPOSITION),
        sources=[cite("mahalle", "population/sex_ratio", urls["mahalle"])],
        **ratio_fields(men, women, src["mahalle"]))


def build(t3: dict[str, Any], ages: dict[tuple[str, str | None], dict[str, Any]],
          cit: dict[str, dict[str | None, float]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], republic: dict[str, dict[str, Any]],
          urls: dict[str, str]) -> list[dict[str, Any]]:
    """Every record: the polygons the census's quarters are bound to, the
    northern polygons left without a figure (each saying why), and Kyrenia."""
    where = check_binding(t3, admin1, admin2)
    kyrenia_total = check_kyrenia(t3, where)
    zero_written = check_republic(republic)
    by_id = {s["id"]: s for s in admin2}
    district = {s["id"]: s["name"] for s in admin1}
    src = {k: SOURCE.format(title=v) for k, v in TITLES.items()}
    quarter = t3["quarters"]
    records: list[dict[str, Any]] = []

    for sid, (label, *specs) in BIND.items():
        qs = [quarter[spec_key(s)] for s in specs]
        lead = NOTES.get(sid) or f"The census counts this community as {quarter_phrase(qs[0])}."
        if sid in OVERLAP:
            lead += (f" By OpenStreetMap's mapped buildings, about {OVERLAP[sid][1]:.0%} of this count is "
                     "on the wrong side of the polygon's lines (residents of these quarters outside it, "
                     "and of others inside it); a count is put on a polygon only when that is at most a "
                     "tenth.")
        records.append(community(sid, by_id[sid], district[by_id[sid]["parent"]], qs, lead, ABOUT,
                                 src, urls))
    for sid in sorted(zero_written):
        label, *specs = ZERO_IN_REPUBLIC[sid]
        qs = [quarter[spec_key(s)] for s in specs]
        lead = (f"The census taken in the north counts the village as {quarter_phrase(qs[0])}. The "
                "Republic of Cyprus's 2021 census lists the community with no residents: the part of "
                "it under the effective control of its Government is empty.")
        records.append(community(sid, by_id[sid], district[by_id[sid]["parent"]], qs, lead,
                                 f"The count is of usual residents (de jure), by {WHO}.", src, urls))
    for sid, (label, reason) in LEFT_OFF.items():
        why = (f"{NOT_REPUBLIC} {WHO_CAP} counts the north's residents by quarter (mahalle), and "
               f"none of its counts is put on this polygon. {reason}")
        if sid in OVERLAP:
            why += (f" By those buildings, at each quarter's residents per building, about "
                    f"{OVERLAP[sid][1]:.0%} of the count would be on the wrong side of the polygon's "
                    "lines; a count is put on a polygon only when that is at most a tenth.")
        records.append(record(
            f"CYP-north-{YEAR}-none-{sid}", label, level="admin2", parent="CYP", country="CYP",
            match_by="shape_id", shape_id=sid, parent_name=district[by_id[sid]["parent"]],
            population=dict(gap(NOT_AVAILABLE, why), displaces_before=DISPLACES_BEFORE),
            sex_ratio=gap(NOT_AVAILABLE, why), median_age=gap(NOT_AVAILABLE, WHY_NO_AGES),
            religion=gap(NOT_AVAILABLE, WHY_NO_COMPOSITION),
            language=gap(NOT_AVAILABLE, WHY_NO_COMPOSITION),
            ethnicity=gap(NOT_AVAILABLE, WHY_NO_COMPOSITION)))

    records.append(kyrenia(t3, ages, cit, admin1, admin2, kyrenia_total, src, urls))

    bound_people = sum(r["population"]["value"] for r in records
                       if r["level"] == "admin2" and r["shape_id"] in BIND)
    log(f"  {len(BIND)} polygons carry {sum(len(e) - 1 for e in BIND.values())} quarters, "
        f"{bound_people:,} residents of {t3['total']['total']:,.0f}; {len(zero_written)} of "
        f"{len(ZERO_IN_REPUBLIC)} the Republic lists empty written; {len(LEFT_OFF)} northern polygons "
        f"say why they have no figure; {len(UNPLACED)} quarters on no polygon "
        f"({sum(quarter[spec_key(s)]['total'] for s in UNPLACED):,.0f} residents)")
    return records


def kyrenia(t3: dict[str, Any], ages: dict[tuple[str, str | None], dict[str, Any]],
            cit: dict[str, dict[str | None, float]], admin1: list[dict[str, Any]],
            admin2: list[dict[str, Any]], total: float, src: dict[str, str], urls: dict[str, str],
            bind: dict[str, tuple[str, ...]] | None = None) -> dict[str, Any]:
    """Kyrenia district's record. Its figures are the sum of the villages bound
    to its polygons, written only when those cover it completely: every polygon
    of the district bound, and their quarters all of the residents the census
    counts in it (``total``, the Girne district's, by check_kyrenia), whose
    ages and citizenship are then theirs. Otherwise each field says why it is
    empty, with the coverage measured."""
    bind = BIND if bind is None else bind
    shape = next((s for s in admin1 if s["name"] == KYRENIA), None)
    if shape is None:
        raise SystemExit("cyprus_north_census: the map draws no Kyrenia district")
    polygons = [s for s in admin2 if s.get("parent") == shape["id"]]
    bound = [s for s in polygons if s["id"] in bind]
    left = sorted(s["name"] for s in polygons if s["id"] not in bind)
    qs = [t3["quarters"][spec_key(spec)] for s in bound for spec in bind[s["id"]][1:]]
    people = sum(q["total"] for q in qs)
    g = t3["ilces"][GIRNE]
    unit = ages[(GIRNE, None)]
    check_sum(sum(unit["ages"].values()), total, "cyprus_north_census: Tablo 4's ages of Girne")
    groups = {k: v for k, v in cit[GIRNE].items() if k is not None}
    check_sum(sum(groups.values()), total, "cyprus_north_census: Tablo 5's Girne")
    median = median_age(unit["ages"])
    log(f"  Kyrenia: {len(bound)} of its {len(polygons)} polygons bound, holding {people:,.0f} of the "
        f"{total:,.0f} residents the census counts in it ({100 * people / total:.1f}%); not bound: "
        + (", ".join(left) or "none"))
    log(f"  (the census's Girne district: median {median}, "
        f"{round(100 * g['men'] / g['women'], 1)} men per 100 women)")
    sid = f"CYP-north-{YEAR}-kyrenia"
    other_why = (f"{KYRENIA_OUTSIDE} {WHO_CAP}, which counts its residents, published no table of "
                 "religion or language.")
    if left or people != total:
        rest = (f"The other {len(left)} ({', '.join(left)}) carry none of its counts, each saying why, so"
                if left else "The rest live in quarters bound to no polygon, so")
        why = (f"{KYRENIA_OUTSIDE} {WHO_CAP} counts the north's residents by quarter (mahalle), and its "
               f"quarters are bound to {len(bound)} of this district's {len(polygons)} community "
               f"polygons, which hold {people:,.0f} of the {total:,.0f} residents it counts in the "
               f"district. {rest} no sum of the district's villages is its population, and that "
               "census's figures for its own districts (ilçe) are not put on the Republic's.")
        return record(
            sid, KYRENIA, level="admin1", parent="CYP", country="CYP", match_by="shape_id",
            shape_id=shape["id"],
            population=dict(gap(NOT_AVAILABLE, why), displaces_before=DISPLACES_BEFORE),
            sex_ratio=gap(NOT_AVAILABLE, why),
            median_age=gap(NOT_AVAILABLE, (
                f"{KYRENIA_OUTSIDE} {WHO_CAP} publishes ages by its own districts and sub-districts "
                "(ilçe, bucak) at the finest, whose figures are not put on the Republic's districts, "
                "and by no village.")),
            ethnicity=gap(NOT_AVAILABLE, (
                f"{KYRENIA_OUTSIDE} {WHO_CAP} asks citizenship, not ethnicity, and publishes it by its "
                "own districts (ilçe) only, whose figures are not put on the Republic's districts.")),
            religion=gap(NOT_AVAILABLE, other_why), language=gap(NOT_AVAILABLE, other_why))
    composition = exact_shares(groups, cit[GIRNE][None])
    if abs(sum(r["pct"] for r in composition) - 100.0) > 0.05:
        raise SystemExit(f"cyprus_north_census: Kyrenia's citizenship adds to {sum(r['pct'] for r in composition)}")
    men, women = sum(q["men"] for q in qs), sum(q["women"] for q in qs)
    placed = (f"Every polygon of the district carries the quarters (mahalle) of {WHO} bound to it, and "
              "together they are all of its Girne district (ilçe), and nothing else.")
    return record(
        sid, KYRENIA, level="admin1", parent="CYP", country="CYP", match_by="shape_id",
        shape_id=shape["id"],
        population=measure(int(people), year=YEAR, source=src["mahalle"]),
        population_note=(f"The sum of the district's villages, usual residents (de jure) as {WHO} "
                         f"counts them. {placed} {KYRENIA_OUTSIDE}"),
        sex_ratio=sex_ratio(men, women, year=YEAR, source=src["mahalle"]),
        median_age=measure(median, unit="years", year=YEAR, source=src["ages"]),
        median_age_note=("Interpolated within the single year of age that holds the middle person, "
                         f"from the population by single year of age and district (Tablo 4) of {WHO}, "
                         f"its Girne district's column. {placed}"),
        ethnicity=composition, ethnicity_year=YEAR, ethnicity_basis="citizenship",
        ethnicity_note=(
            f"Citizenship (tabiiyet) as {WHO} counts it in its Girne district (Tablo 5): CITIZENSHIP, "
            "not ethnicity, which that census does not ask. 'TRNC citizen' counts those who hold only "
            "the citizenship that administration issues (KKTC in the census's Turkish); 'TRNC and "
            "Turkish citizen' and 'TRNC and other citizen' those who hold it with a second; the other "
            "rows are citizens of the countries the table names, and 'Other' of those it does not. "
            + placed),
        religion=gap(NOT_AVAILABLE, other_why), language=gap(NOT_AVAILABLE, other_why),
        sources=[cite("mahalle", "population/sex_ratio", urls["mahalle"]),
                 cite("ages", "median_age", urls["ages"]),
                 cite("citizenship", "ethnicity", urls["citizenship"])])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("cyprus_north_census: the census taken in the north of Cyprus on 4 December 2011")
    rows3, url3 = table("mahalle")
    t3 = quarters(rows3)
    rows1, url1 = table("ilce")
    rows4, url4 = table("ages")
    rows5, url5 = table("citizenship")
    ilces = set(t3["ilces"])
    ages = single_years(rows4, ilces)
    cit = citizenship(rows5, ilces)
    check_tables(t3, districts(rows1), ages, cit)
    log(f"  {len(t3['quarters'])} quarters, {len(t3['municipalities'])} municipalities, "
        f"{len(t3['bucaks'])} sub-districts, {len(ilces)} districts; {t3['total']['total']:,.0f} residents")
    log("  medians from single years: north " + str(median_age(ages[("total", None)]["ages"])) + "; "
        + ", ".join(f"{t3['ilces'][i]['name']} {median_age(ages[(i, None)]['ages'])}" for i in sorted(ilces)))
    records = build(t3, ages, cit, shapes("CYP", "admin1"), shapes("CYP", "admin2"),
                    republic_records(),
                    {"mahalle": url3, "ilce": url1, "ages": url4, "citizenship": url5})
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
