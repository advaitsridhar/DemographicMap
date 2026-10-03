#!/usr/bin/env python3
"""Albania: ethnicity, religion and home language by prefecture, 2023 census.

The Institute of Statistics (INSTAT) published the 2023 Population and
Housing Census's cultural tables by prefecture (qark), one workbook per
question with a sheet per prefecture, each by sex:

* Tab. 1.12 -- resident population by ethnicity (përkatësia etnike);
* Tab. 1.13 -- by religion (besimi fetar);
* Tab. 1.14 -- by the language usually spoken at home (not mother tongue,
  which the 2011 census asked instead).

The three questions were voluntary. "Not available" (nuk disponohet) is the
census's own row for residents whose record came from administrative sources
rather than an interview -- 134,451 people, 5.6% of the country -- and is kept
as a bar of its own, as are "prefer not to answer" and "none". A cell INSTAT
prints as ".." (a count too small to publish) is left out of its row and the
people it hides are kept together as one bar, so every row still adds to its
prefecture.

The prefectures keep Eurostat's newer head count, median age and sex ratio;
this writes their compositions.

The map's second level is the 36 districts of 2000-2015, which no INSTAT
table is by. Their head count and sex ratio are summed from the 2011 census's
373 municipalities and communes (Tab. 2.1.2), each placed in the district it
lay in (``DISTRICTS``, measured against GeoNames and the district polygons);
the twelve districts that are exactly one municipality of 2015 take that
municipality's 2023 count instead (Tab. 7). Ages by commune and municipality
come only in three broad groups, so no district has a median; ethnicity,
religion and language are published by prefecture at the finest. Both say so.

Checks: every row's categories (with what the ".." cells hide) add to its
total, the sexes to the total, the three tables agree on each prefecture's
count and with Tab. 6's, and the prefectures add to the country. For the
districts: every commune's age groups and sexes add to its total, the communes
to their prefecture and the prefectures to 2011's 2,800,138, Tab. 7's
municipalities to 2023's 2,402,113; every commune is in exactly one district,
of its own prefecture.

Usage:
    python -m scripts.fetch_census.albania_census
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .balkans_common import check_sum, fold, shapes, spreadsheetml

OUT = "albania_census.json"
YEAR = 2023
MEDIA = "https://www.instat.gov.al/media/"
TABLES = {
    "ethnicity": MEDIA + "14409/tab_1_12_popullsia-banuese-sipas-përkatësisë-etnike-dhe-gjinisë_qarqe.xls",
    "religion": MEDIA + "14411/tab_1_13_popullsia-banuese-sipas-besimit-fetar-dhe-gjinisë_qarqe.xls",
    "language": MEDIA + "14412/tab_1_14_popullsia-banuese-sipas-gjuhës-që-flitet-zakonisht-në-shtëpi-dhe-gjinisë_qarqe.xls",
}
TITLES = {
    "ethnicity": "Tab. 1.12, resident population by ethnicity and sex, by prefecture",
    "religion": "Tab. 1.13, resident population by religion and sex, by prefecture",
    "language": ("Tab. 1.14, resident population by language usually spoken at home and sex, "
                 "by prefecture"),
}
PAGE = "https://www.instat.gov.al/en/themes/censuses/census-of-population-and-housing/"
SOURCE = "Institute of Statistics of Albania (INSTAT), Population and Housing Census 2023, {title}"
LICENCE = "Institute of Statistics of Albania (reuse with attribution)"
NATIONAL = 2_402_113
SUPPRESSED = "Suppressed (disclosure control)"
# The Albanian half of a row's label, folded, as it begins -> the bar. The
# longer beginnings are tried first ("myslimanbektashi" before "mysliman").
LABELS: dict[str, dict[str, str]] = {
    "ethnicity": {
        "shqiptare": "Albanian", "greke": "Greek", "maqedonase": "Macedonian",
        "malazeze": "Montenegrin", "aromune": "Aromanian", "rome": "Roma",
        "egjyptiane": "Balkan Egyptian", "boshnjake": "Bosniak", "serbe": "Serbian",
        "bullgare": "Bulgarian", "tjetergrupetnokulturor": "Other",
        "grupetnokulturoriperzier": "Mixed", "asnje": "None",
        "preferojtemospergjigjem": "Not declared", "nukdisponohet": "Not stated",
    },
    "religion": {
        "myslimanbektashi": "Bektashi", "mysliman": "Islam",
        "krishterekatolik": "Catholic", "krishtereortodoks": "Orthodox",
        "krishtereungjillore": "Protestant", "tjeterbesimfetar": "Other religion",
        "besimtaretepacilesuar": "Unaffiliated believer",
        "besimtaretepacilcesuar": "Unaffiliated believer", "ateist": "Atheism",
        "asnje": "No religion", "preferojtemospergjigjem": "Not declared",
        "nukdisponohet": "Not stated",
    },
    "language": {
        "shqip": "Albanian", "gjuhetjeter": "Other", "disagjuhe": "Mixed languages",
        "preferojtemospergjigjem": "Not declared", "nukdisponohet": "Not stated",
    },
}
NOTES = {
    "ethnicity": ("Ethnic affiliation (përkatësia etnike), 2023 census, resident population, a "
                  "voluntary question. 'Not stated' is the census's 'not available': residents "
                  "whose record came from administrative sources rather than an interview. "
                  "Those who preferred not to answer, who named none, or who named a mixed "
                  "affiliation are their own bars; 'Balkan Egyptian' is the census's Egjyptiane."),
    "religion": ("Religion (besimi fetar), 2023 census, resident population, a voluntary "
                 "question. 'Unaffiliated believer' is the census's believers without a "
                 "denomination (besimtarë të pacilësuar); Bektashi are counted apart from other "
                 "Muslims, as the census does. 'Not stated' is the census's 'not available': "
                 "residents whose record came from administrative sources."),
    "language": ("Language usually spoken at home, 2023 census, resident population -- not "
                 "mother tongue, which the 2011 census asked instead. INSTAT publishes Albanian, "
                 "any other language, and several languages; 'Not stated' is the census's 'not "
                 "available': residents whose record came from administrative sources."),
}


def label_of(field: str, text: str) -> str | None:
    """The bar a row is shown as; None for the total row; '' if unknown."""
    f = fold(text)
    if f.startswith("gjithsej"):
        return None
    for start in sorted(LABELS[field], key=len, reverse=True):
        if f.startswith(start):
            return LABELS[field][start]
    return ""


def cell(value: Any) -> float | None:
    """A count; None for INSTAT's '..' (too small to publish)."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if text in ("..", "…"):
        return None
    if text in ("", "-"):
        return 0.0
    return float(text.replace(",", ""))


def read(field: str) -> dict[str, dict[str, Any]]:
    """{prefecture (folded): {"name", "total", "men", "women", "groups"}}."""
    # The file names carry ë: sent percent-encoded, as a browser sends them.
    blob = http_get(urllib.parse.quote(TABLES[field], safe=":/%?=&"), binary=True, timeout=300)
    sheets = spreadsheetml(blob)
    out: dict[str, dict[str, Any]] = {}
    unknown = set()
    for sheet, rows in sheets.items():
        # "Qarku Berat | Prefecture Berat": the prefecture as the table names it.
        head = next((str(r[0]) for r in rows if r and str(r[0] or "").strip().lower().startswith("qarku")), None)
        if head is None:
            raise SystemExit(f"albania_census: {field}: sheet {sheet!r} names no prefecture")
        # One cell or two: "Qarku Fier" | "Prefecture Fier", or "Qarku Fier  Prefecture Fier".
        name = re.match(r"Qarku\s+(.+?)(?:\s{2,}|\s+Prefecture\b|$)", head.strip()).group(1).strip()
        unit: dict[str, Any] = {"name": name, "groups": {}, "hidden": 0}
        for r in rows:
            if not r or r[0] is None or len(r) < 4:
                continue
            label = label_of(field, str(r[0]))
            if label == "":
                if cell_is_number(r[1]) or str(r[1] or "").strip() == "..":
                    unknown.add(str(r[0]).strip())
                continue
            total, men, women = (cell(v) for v in r[1:4])
            if label is None:
                unit["total"], unit["men"], unit["women"] = total, men, women
                continue
            if total is None:
                unit["hidden"] += 1
                continue
            unit["groups"][label] = unit["groups"].get(label, 0.0) + total
        if "total" not in unit:
            raise SystemExit(f"albania_census: {field}: no total row for {name}")
        check_sum(unit["men"] + unit["women"], unit["total"], f"albania_census: {field} sexes of {name}")
        shown = sum(unit["groups"].values())
        short = unit["total"] - shown
        if unit["hidden"]:
            if short < 0:
                raise SystemExit(f"albania_census: {field} of {name}: rows add to {shown:,.0f}, "
                                 f"more than the total {unit['total']:,.0f}")
            if short:
                unit["groups"][SUPPRESSED] = short
        else:
            check_sum(shown, unit["total"], f"albania_census: {field} of {name}")
        out[fold(name)] = unit
    if unknown:
        raise SystemExit(f"albania_census: {field} rows with no label: {sorted(unknown)}")
    check_sum(sum(u["total"] for u in out.values()), NATIONAL, f"albania_census: {field}, prefectures")
    log(f"  {field}: {len(out)} prefectures; hidden cells in "
        f"{sum(1 for u in out.values() if u['hidden'])}")
    return out


def cell_is_number(value: Any) -> bool:
    if value is None or not str(value).strip():
        return False
    try:
        return cell(value) is not None
    except ValueError:
        return False

# ---------------------------------------------------------------------------
# The 36 former districts
# ---------------------------------------------------------------------------
# The map's second level is the 36 districts (rrethe) of 2000-2015. INSTAT
# publishes nothing by district, but the 2011 census counts each of the 373
# municipalities and communes of its day by sex and broad age group
# (tab_2_1_2.xls, a sheet per prefecture), and every one of those lay in one
# district. The 2023 census counts the 61 municipalities of 2015 the same way
# (Tab. 7), and twelve of them are exactly a former district.
COMMUNES_2011 = MEDIA + "3140/tab_2_1_2.xls"
MUNICIPALITIES_2023 = MEDIA + "13652/tab7.xlsx"
TITLE_2011 = ("Population and Housing Census 2011, Tab. 2.1.2, resident population by "
              "municipality/commune, sex and age group")
TITLE_2023 = "Population and Housing Census 2023, Tab. 7, resident population by municipality, sex and age group"
NATIONAL_2011 = 2_800_138
# tab_2_1_2's sheets, in the order of DISTRICTS' second field -> the map's prefecture.
SHEETS_2011 = ("Berat", "Diber", "Durres", "Elbasan", "Fier", "Gjirokaster", "Korce", "Kukes", "Lezhe",
               "Shkoder", "Tirane", "Vlore")
# Each district polygon -> (its name, the sheet of tab_2_1_2 it is in, the
# municipalities and communes of 2011 it was made of, as the table spells
# them less a trailing dot).
#
# Measured, not copied: every commune was given a point -- its seat of the
# same name in GeoNames (271), else its GeoNames administrative unit (74),
# else a declared pair for the "centre" communes and other spellings (28) --
# and placed in the district polygon of its own prefecture that holds it
# (four seats a few hundred metres over a line, to the nearest). Where the
# seat and the unit put a commune in different districts (17 of 373), it is
# the district the commune belonged to in 2011: Gostimë (Elbasan), Poroçan
# (Gramsh), Dushk (Lushnjë), Ngraçan (Mallakastër), Mollaj (Korçë), Mollas
# and Novoselë (Kolonjë), Blinisht and Shëngjin (Lezhë), Selitë (Mirditë),
# Bushat (Shkodër) and Shëngjergj (Tiranë); the rest agree. Checked: the
# sums for Bulqizë, Dibër, Gramsh, Kukës, Kurbin, Mirditë and Peqin, whose
# 2015 municipality is the old district, equal Wikidata's 2011 figures for
# those municipalities exactly.
#
# The boundary file labels the Korçë district's polygon "Kuçovë" (it lies in
# Korçë prefecture and holds Korçë and its communes); it is bound by its id.
DISTRICTS: dict[str, tuple[str, int, str]] = {
    "67620474B3220488890929": ("Berat", 0, "BERAT|CUKALAT|KUTALLI|LUMAS|OTLLAK|POSHNJË|ROSHNIK|SINJË|TERPAN|URA VAJGURORE|VELABISHT|VERTOP"),
    "67620474B36949901982284": ("Kuçovë", 0, "KOZARE|KUÇOVË|PERONDI"),
    "67620474B62055143354216": ("Skrapar", 0, "BOGOVË|GJERBËS|LESHNJË|POLIÇAN|POTOM|QENDËR SKRAPAR|VENDRESHË|ZHEPË|ÇEPAN|ÇOROVODË"),
    "67620474B60153855067708": ("Bulqizë", 1, "BULQIZË|FUSHË BULQIZË|GJORICË|MARTANESH|OSTREN|SHUPENZË|TREBISHT|ZERQAN"),
    "67620474B73468897065558": ("Dibër", 1, "ARRAS|FUSHË MUHUR|FUSHË ÇIDHËN|KALA E DODËS|KASTRIOT|LURË|LUZNI|MAQELLARË|MELAN|PESHKOPI|QENDËR TOMIN|SELISHTË|SLLOVË|ZALL DARDHË|ZALL REÇ"),
    "67620474B55788488782298": ("Mat", 1, "BAZ|BURREL|DERJAN|GURRË|KLOS|KOMSI|LIS|MACUKULL|RUKAJ|SUÇ|ULËZ|XIBËR"),
    "67620474B45959085094100": ("Durrës", 2, "DURRËS|GJEPALAJ|KATUND I RI|MAMINAS|MANËZ|RRASHBULL|SHIJAK|SUKTH|XHAFZOTAJ"),
    "67620474B91291617478666": ("Krujë", 2, "BUBQ|CUDHI|FUSHË KRUJË|ISHËM|KODËR THUMANË|KRUJË|NIKËL"),
    "67620474B34590160208903": ("Elbasan", 3, "BELSH|BRADASHESH|CËRRIK|ELBASAN|FIERZË|FUNARË|GJERGJAN|GJINAR|GOSTIMË|GRACEN|GREKAN|KAJAN|KLOS|LABINOT FUSHË|LABINOT MAL|MOLLAS|PAPËR|RRASË|SHALËS|SHIRGJAN|SHUSHICË|TREGAN|ZAVALIN"),
    "67620474B60363170083379": ("Gramsh", 3, "GRAMSH|KODOVJAT|KUKUR|KUSHOVË|LENIE|PISHAJ|POROÇAN|SKËNDERBEGAS|SULT|TUNJË"),
    "67620474B87569046172350": ("Librazhd", 3, "HOTOLISHT|LIBRAZHD|LUNIK|ORENJË|POLIS|PËRRENJAS|QENDËR|QUKËS|RRAJCË|STRAVAJ|STËBLEVË"),
    "67620474B93113119561724": ("Peqin", 3, "GJOCAJ|KARINË|PAJOVË|PEQIN|PËRPARIM|SHEZË"),
    "67620474B94080737422449": ("Fier", 4, "CAKRAN|DERMENAS|FIER|FRAKULL|KUMAN|KURJAN|LEVAN|LIBOFSHË|MBROSTAR|PATOS|PORTËZ|QENDËR (FIER)|ROSKOVEC|RUZHDIE|STRUM|TOPOJË|ZHARRËS"),
    "67620474B73435711419495": ("Lushnjë", 4, "ALLKAJ|BALLAGAT|BUBULLIMË|DIVJAKË|DUSHK|FIERSHEGAN|GOLEM|GRABIAN|GRADISHTË|HYSGJOKAJ|KARBUNARË|KOLONJË|KRUTJE|LUSHNJE|RREMAS|TËRBUF"),
    "67620474B72354996665991": ("Mallakastër", 4, "ARANITAS|BALLSH|FRATAR|GRESHICË|HEKAL|KUTË|NGRAÇAN|QENDËR (MALLAKASTËR)|SELITË"),
    "67620474B28188595050305": ("Gjirokastër", 5, "ANTIGONË|CEPO|DROPULL I POSHTËM|DROPULL I SIPËRM|GJIROKASTËR|LAZARAT|LIBOHOVË|LUNXHËRI|ODRIE|PICAR|POGON|QENDËR LIBOHOVË|ZAGORI"),
    "67620474B23103740146981": ("Përmet", 5, "BALLABAN|DISHNICË|FRASHËR|KËLCYRË|PETRAN|PËRMET|QENDËR PISKOVË|SUKË|ÇARÇOVË"),
    "67620474B25662331989090": ("Tepelenë", 5, "BUZ|FSHAT MEMALIAJ|KRAHËS|KURVELESH|LOPËS|LUFTINJË|MEMALIAJ|QENDËR (TEPELENË)|QESARAT|TEPELENË"),
    "67620474B41402008781007": ("Devoll", 6, "BILISHT|HOÇISHT|MIRAS|PROGËR|QENDËR BILISHT"),
    "67620474B91947048364679": ("Kolonjë", 6, "BARMASH|ERSEKË|LESKOVIK|MOLLAS|NOVOSELË|QENDËR ERSEKE|QENDËR LESKOVIK|ÇLIRIM"),
    "67620474B90792074310011": ("Korçë", 6, "DRENOVË|GORË|KORÇË|LEKAS|LIBONIK|LIQENAS|MALIQ|MOGLICË|MOLLAJ|PIRG|POJAN|QENDËR KORCE|VITHKUQ|VOSKOP|VOSKOPOJË|VRESHTAS"),
    "67620474B77805918454880": ("Pogradec", 6, "BUÇIMAS|DARDHAS|HUDENISHT|POGRADEC|PROPTISHT|TREBINJË|VELÇAN|ÇËRRAVË"),
    "67620474B51228836218093": ("Has", 7, "FAJZA|GJINAJ|GOLAJ|KRUMË"),
    "67620474B92464717887955": ("Kukës", 7, "ARRËN|BICAJ|BUSHTRICË|GRYKË ÇAJË|KALIS|KOLSH|KUKËS|MALZI|SHISHTAVEC|SHTIQËN|SURROJ|TOPOJAN|TËRTHORE|UJËMISHT|ZAPOD"),
    "67620474B51082079967557": ("Tropojë", 7, "BAJRAM CURRI|BUJAN|BYTYÇ|FIERZË|LEKBIBAJ|LLUGAJ|MARGEGAJ|TROPOJË"),
    "67620474B66777869203493": ("Kurbin", 8, "FUSHË KUQE|LAÇ|MAMURRAS|MILOT"),
    "67620474B20431026689517": ("Lezhë", 8, "BALLDREN I RI|BLINISHT|DAJÇ|KALLMET|KOLÇ|LEZHË|SHËNGJIN|SHËNKOLL|UNGREJ|ZEJMEN"),
    "67620474B99888539945274": ("Mirditë", 8, "FAN|KAÇINAR|KTHJELLË|OROSH|RRËSHEN|RUBIK|SELITË"),
    "67620474B62137861373373": ("Malësi e Madhe", 9, "GRUEMIRË|KASTRAT|KELMEND|KOPLIK|QENDËR|SHKREL"),
    "67620474B73280275449109": ("Pukë", 9, "BLERIM|FIERZË|FUSHË ARRËZ|GJEGJAN|IBALLË|PUKË|QAFË MALI|QELËZ|QERRET|RRAPË"),
    "67620474B15717375113052": ("Shkodër", 9, "ANA E MALIT|BUSHAT|BËRDICË|DAJÇ|GURI I ZI|HAJMEL|POSTRIBË|PULT|RRETHINAT|SHALË|SHKODËR|SHLLAK|SHOSH|TEMAL|VAU I DEJËS|VELIPOJË|VIG-MNELË"),
    "67620474B5524789266710": ("Kavajë", 10, "GOLEM|GOSË|HELMËS|KAVAJË|KRYEVIDH|LEKAJ|LUZ I VOGEL|RROGOZHINË|SINABALLAJ|SYNEJ"),
    "67620474B90997304428465": ("Tiranë", 10, "BALDUSHK|BËRXULLË|BËRZHITË|DAJT|FARKË|KAMËZ|KASHAR|KËRRABË|NDROQ|PASKUQAN|PETRELË|PEZË|PREZË|SHËNGJERGJ|TIRANË|VAQARR|VORË|ZALL BASTAR|ZALL HERR"),
    "67620474B1879164611880": ("Delvinë", 11, "DELVINË|FINIQ|MESOPOTAM|VERGO"),
    "67620474B70468291702657": ("Sarandë", 11, "ALIKO|DHIVËR|KONISPOL|KSAMIL|LIVADHJA|LUKOVË|MARKAT|SARANDË|XARRË"),
    "67620474B72762453157270": ("Vlorë", 11, "ARMEN|BRATAJ|HIMARË|KOTE|NOVOSELË|ORIKUM|QENDËR|SELENICË|SEVASTER|SHUSHICË|VLLAHINË|VLORË|VRANISHT"),
}
# Districts that are exactly one municipality of 2015 -- every one of its
# communes went to that municipality, and the municipality took no other --
# and so have the 2023 census's count: the polygon -> the municipality as
# Tab. 7 names it.
SAME_2023 = {
    "67620474B60153855067708": "Bulqizë", "67620474B73468897065558": "Dibër",
    "67620474B60363170083379": "Gramsh", "67620474B93113119561724": "Peqin",
    "67620474B72354996665991": "Mallakastër", "67620474B41402008781007": "Devoll",
    "67620474B51228836218093": "Has", "67620474B92464717887955": "Kukës",
    "67620474B51082079967557": "Tropojë", "67620474B62137861373373": "Malësi e Madhe",
    "67620474B66777869203493": "Kurbin", "67620474B99888539945274": "Mirditë",
}
WHY_MEDIAN = ("INSTAT counts the municipalities and communes by age only in three broad groups "
              "(0-14, 15-64, 65 and over: 2011 Tab. 2.1.2, 2023 Tab. 7), from which no median can "
              "be read, and publishes finer ages by prefecture only.")
WHY_COMPOSITION = ("INSTAT publishes the 2023 census's ethnicity, religion and home language by "
                   "prefecture at the finest (Tab. 1.12-1.14), and the 2011 census's for the whole "
                   "country (Tab. 1.1.12-1.1.14); no table reaches the districts, or the "
                   "municipalities and communes that made them up.")


def unit_name(text: Any) -> str:
    """'MOLLAS.' / 'QENDËR    .' -> 'MOLLAS' / 'QENDËR'."""
    return " ".join(re.sub(r"[\s.]+$", "", str(text or "")).split())


def sheets_of(blob: bytes) -> dict[str, list[list[Any]]]:
    if blob.lstrip()[:5] == b"<?xml":
        return spreadsheetml(blob)
    if blob[:2] == b"PK":
        import io
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    import xlrd
    wb = xlrd.open_workbook(file_contents=blob)
    return {sh.name: [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            for sh in wb.sheets()}


def sex_rows(rows: list[list[Any]], what: str) -> tuple[dict[str, tuple[float, float, float]],
                                                        tuple[float, float, float]]:
    """({unit: (total, men, women)}, the table's own total) from a sheet laid
    out total | 0-14 | 15-64 | 65+ for both sexes, then men, then women."""
    units: dict[str, tuple[float, float, float]] = {}
    whole = None
    for r in rows:
        if not r or len(r) < 10 or not isinstance(r[1], (int, float)):
            continue
        name = unit_name(r[0])
        total, men, women = float(r[1]), float(r[5]), float(r[9])
        check_sum(sum(float(v) for v in r[2:5]), total, f"albania_census: {what} {name}'s ages")
        check_sum(men + women, total, f"albania_census: {what} {name}'s sexes")
        if fold(name).startswith("gjithsej"):
            whole = (total, men, women)
        elif name in units:
            raise SystemExit(f"albania_census: {what} lists {name!r} twice")
        else:
            units[name] = (total, men, women)
    if whole is None:
        raise SystemExit(f"albania_census: {what} has no total row")
    check_sum(sum(u[0] for u in units.values()), whole[0], f"albania_census: {what}'s units")
    return units, whole


def districts(admin1_names: dict[str, str]) -> list[dict[str, Any]]:
    """The 36 districts: head count and sex ratio from 2023 where the district
    is one municipality of 2015, from 2011 otherwise; the rest stated."""
    books = sheets_of(http_get(COMMUNES_2011, binary=True, timeout=300))
    communes: dict[int, dict[str, tuple[float, float, float]]] = {}
    national = 0.0
    for i, sheet in enumerate(SHEETS_2011):
        if sheet not in books:
            raise SystemExit(f"albania_census: tab_2_1_2 has no sheet {sheet!r}: {list(books)}")
        communes[i], whole = sex_rows(books[sheet], f"2011 {sheet}")
        national += whole[0]
    check_sum(national, NATIONAL_2011, "albania_census: the 2011 prefectures against the country")
    munis, whole = sex_rows(next(iter(sheets_of(http_get(MUNICIPALITIES_2023, binary=True,
                                                          timeout=300)).values())), "2023 Tab. 7")
    check_sum(whole[0], NATIONAL, "albania_census: Tab. 7 against the country")
    by_fold = {fold(k): v for k, v in munis.items()}
    polys = {s["id"]: s for s in shapes("ALB", "admin2")}
    if set(polys) != set(DISTRICTS):
        raise SystemExit(f"albania_census: the map's districts are not DISTRICTS': "
                         f"{sorted(set(polys) ^ set(DISTRICTS))}")
    placed: dict[int, set[str]] = {i: set() for i in communes}
    records = []
    for sid, (name, sheet, listed) in DISTRICTS.items():
        shape = polys[sid]
        prefecture = admin1_names.get(shape.get("parent"), "")
        if fold(prefecture)[:5] != fold(SHEETS_2011[sheet])[:5]:
            raise SystemExit(f"albania_census: {name} is drawn in {prefecture!r}, its communes are "
                             f"in the sheet {SHEETS_2011[sheet]!r}")
        parts = listed.split("|")
        missing = [p for p in parts if p not in communes[sheet]]
        if missing:
            raise SystemExit(f"albania_census: {name}'s communes {missing} are not in the 2011 table")
        placed[sheet] |= set(parts)
        total = sum(communes[sheet][p][0] for p in parts)
        men = sum(communes[sheet][p][1] for p in parts)
        women = sum(communes[sheet][p][2] for p in parts)
        year, title, url = 2011, TITLE_2011, COMMUNES_2011
        note = (f"The 2011 census's {len(parts)} municipalities and communes that made up the district "
                "of " + name + ", summed (Tab. 2.1.2); the district is not a unit of the 2023 census.")
        if sid in SAME_2023:
            key = fold(SAME_2023[sid])
            if key not in by_fold:
                raise SystemExit(f"albania_census: Tab. 7 has no municipality {SAME_2023[sid]!r}")
            total, men, women = by_fold[key]
            year, title, url = YEAR, TITLE_2023, MUNICIPALITIES_2023
            note = (f"The 2023 census's municipality of {SAME_2023[sid]} (Tab. 7), which is the former "
                    f"district of {name}: the {len(parts)} municipalities and communes of 2011 that made "
                    "up the one made up the other.")
        if shape["name"] != name:
            note += (f" The boundary file labels this polygon {shape['name']!r}; it lies in {prefecture} "
                     f"prefecture and holds {name} and its communes.")
        src = f"Institute of Statistics of Albania (INSTAT), {title}"
        fields: dict[str, Any] = {
            "population": measure(round(total), year=year, source=src),
            "population_note": note,
            "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females", year=year,
                                 source=src),
            "median_age": gap(NOT_AVAILABLE, WHY_MEDIAN),
        }
        for f in ("ethnicity", "religion", "language"):
            fields[f] = gap(NOT_AVAILABLE, WHY_COMPOSITION)
        records.append(record(
            f"ALB-district-{sid}", name, level="admin2", parent="ALB", country="ALB",
            match_by="shape_id", shape_id=sid, parent_name=prefecture,
            sources=[{"field": "population/sex_ratio", "name": src, "url": url, "page": PAGE,
                      "year": year, "license": LICENCE}], **fields))
        log(f"  {name}: {total:,.0f} ({year}), {fields['sex_ratio']['value']} men per 100 women")
    left = {SHEETS_2011[i]: sorted(set(c) - placed[i]) for i, c in communes.items() if set(c) - placed[i]}
    if left:
        raise SystemExit(f"albania_census: 2011 communes in no district: {left}")
    return records


def build() -> list[dict[str, Any]]:
    tables = {f: read(f) for f in ("ethnicity", "religion", "language")}
    polys = {fold(s["name"]): s for s in shapes("ALB", "admin1")}
    names = set(tables["ethnicity"])
    for f, t in tables.items():
        if set(t) != names:
            raise SystemExit(f"albania_census: the {f} table's prefectures differ: {sorted(set(t) ^ names)}")
    records = []
    bound = set()
    for key in sorted(names):
        shape = polys.get(key) or next((s for k, s in polys.items() if k[:5] == key[:5]), None)
        if shape is None or shape["id"] in bound:
            raise SystemExit(f"albania_census: no single polygon for the prefecture {key!r}; "
                             f"polygons {sorted(polys)}")
        bound.add(shape["id"])
        total = tables["ethnicity"][key]["total"]
        fields: dict[str, Any] = {}
        cites = []
        for f in ("ethnicity", "religion", "language"):
            unit = tables[f][key]
            check_sum(unit["total"], total, f"albania_census: {f} against ethnicity for {unit['name']}")
            fields[f] = shares({k: v for k, v in unit["groups"].items() if v}, total=unit["total"])
            fields[f"{f}_year"] = YEAR
            fields[f"{f}_note"] = NOTES[f] + (
                f" {unit['groups'].get(SUPPRESSED, 0):,.0f} people in cells INSTAT does not publish "
                "(too few to show) are one bar." if SUPPRESSED in unit["groups"] else "")
            cites.append({"field": f, "name": SOURCE.format(title=TITLES[f]), "url": TABLES[f],
                          "page": PAGE, "year": YEAR, "license": LICENCE})
        records.append(record(f"ALB-2023-{key}", shape["name"], level="admin1", parent="ALB",
                              country="ALB", match_by="shape_id", shape_id=shape["id"],
                              sources=cites, **fields))
        eth = fields["ethnicity"][:3]
        log(f"  {shape['name']}: {total:,.0f}; " + ", ".join(f"{r['group']} {r['pct']}" for r in eth))
    spare = [s["name"] for s in polys.values() if s["id"] not in bound]
    if spare:
        raise SystemExit(f"albania_census: prefectures with no table: {spare}")
    records += districts({s["id"]: s["name"] for s in shapes("ALB", "admin1")})
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("albania_census: INSTAT, 2023 census by prefecture")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
