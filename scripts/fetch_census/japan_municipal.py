#!/usr/bin/env python3
"""Japan: every municipality and prefecture from the 2020 census, bound by JIS code.

Three e-Stat tables of the 2020 Population Census (令和２年国勢調査), every
one of them cut by 全国，都道府県，市区町村 -- the nation, the 47 prefectures
and every municipality and ward, 1,965 areas keyed by their JIS codes:

* **0004019308** (不詳補完結果: 男女，国籍総数か日本人別平均年齢及び年齢中位数)
  -- the median age of every area, with the ages the census could not
  establish imputed by the Statistics Bureau: the figures the Bureau itself
  quotes;
* **0004019309** (不詳補完結果: 男女，年齢（5歳階級），国籍総数か日本人別人口)
  -- the same areas' men and women by five-year age group, from which the sex
  ratio is taken, and the median age of a polygon that holds two
  municipalities (below);
* **0003445244** (人口等基本集計: 外国人 男女，国籍別人口) -- population by
  nationality, the thirteen nationalities the census names and the Japanese,
  which ``japan.py`` reads for the prefectures and this reads for every
  municipality. It is written on the ethnicity field under
  ``ethnicity_basis: "nationality"`` by the owner's decision of 19 September
  2026 -- a passport is not an ethnicity, and the note says so -- and its
  total is the census count written as the population.

**Binding.** The tables name areas by JIS code and in Japanese; the map's
polygons have romanised names of geoBoundaries' own spelling ("Aashikawa",
"Oomura", "Got2") and 24 of them none. Each value is bound to its polygon by
code: through ``data/processed/code_shapes.json`` (``scripts/wikidata_points.py``
binds a code only where a Wikidata item's coordinate and name both say which
polygon it is), and for the 144 polygons that test cannot settle through
``EXTRA_SHAPES`` below. Those were settled the same way by hand, on the
boundary file's own geometry: the municipality's Wikidata item (its office)
stands inside the polygon, or within 0.02 degrees of it where the office
stands on the coast or across a strait (Taketomi's on Ishigaki), no other
municipality's item does, and the polygon lies in the prefecture the code
names. They are the prefectures' capitals and the twelve designated cities
whose prefecture's own item stands in the same polygon -- two items passing
the name test, so the automatic pass kept neither -- and the polygons whose
romanisation the name test cannot bridge, or which the boundary file labels
wrongly ("Kume" is Kurume, "Oomura" in Fukuoka is Omuta, "Shibara" is
Shibata). A row bound that way carries the municipality's name, and the
polygon's own label is kept as an alias.

**What the boundary file draws differently.** Its Numata polygon in Gunma is
510.7 km2 against Numata's 443.5: it takes in the village of Showa (64.1 km2),
which it does not draw, and Showa's office stands inside it. That polygon is
written as the two municipalities together (``UNIONS``): their counts summed,
and the median interpolated within the five-year group from the two summed
age tables, which is the one figure here not read as published (the note says
so). A 0.2 km2 sliver in Saitama, between Saitama City, Kawagoe and Ageo,
carries no name and no municipality's item; it is no census area, and is
written as a stated gap (``SLIVERS``). The six villages of the islands north
of Hokkaido the census did not enumerate (Shikotan, Tomari, Ruyobetsu, Rubetsu,
Shana, Shibetoro), and the small islands the boundary file does not draw, have
no polygon and are left out.

**The prefectures.** The 47 are bound by name to the shapes the map draws
(``japan.PREFECTURES`` holds both spellings), and carry the median age and sex
ratio of the same two tables. Their population and nationality are
``japan.py``'s.

**Religion and language** are not asked by Japan's census, and no survey or
register measures either by municipality: every municipal record says so,
which is what the panel prints in place of a placeholder.

**Checks**, each a refusal: the national median within the prefectures'
range; the prefectures' men and women summing to the nation's; every area's
age groups summing to its total and its men and women to the same total in
both tables; every area's nationalities summing to its foreign total and
Japanese, foreign and unknown to its total; the municipalities of each
prefecture summing to it; no code bound to two polygons and no polygon to two
codes. The grouped-median method is measured against the Bureau's own medians
over every municipality before it is used once, and refused if the mean gap
exceeds ``GROUPED_TOLERANCE``.

Usage:
    python -m scripts.fetch_census.japan_municipal     # needs ESTAT_API
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ._shared import NOT_COLLECTED, PROCESSED, gap, log, measure, read_json, record, write_json
from .east_asia_common import drawn, grouped_median, hundred, sex_ratio
from .japan import (
    CODE_FOREIGN, CODE_TOTAL, CODE_UNKNOWN, DECISION, ESTAT_LICENCE, NATIONALITY_CODES,
    NATIONALITY_SOURCE, NATIONALITY_TABLE, NATIONALITY_URL, PREFECTURES, fetch_values,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_estat import app_id, call, listed, result_of  # noqa: E402

OUT = "japan_municipal.json"
YEAR = 2020
TIME = "2020000000"
NATIONAL = "00000"

TABLE = "0004019308"
MEDIAN = "2020i_40"
SOURCE = "Statistics Bureau of Japan, 2020 Census (e-Stat 0004019308, imputed)"
URL = f"https://www.e-stat.go.jp/dbview?sid={TABLE}"
SEX_TABLE = "0004019309"
SEX_SOURCE = "Statistics Bureau of Japan, 2020 Census (e-Stat 0004019309, imputed)"
SEX_URL = f"https://www.e-stat.go.jp/dbview?sid={SEX_TABLE}"
POPULATION_SOURCE = "Statistics Bureau of Japan, 2020 Population Census (e-Stat 0003445244)"

# 0004019309's age classes: 00 is all ages, 01-20 the five-year groups from
# 0-4 to 95-99, 21 is 100 and over.
AGE_TOTAL = "00"
AGE_GROUPS: dict[str, tuple[int, int | None]] = {
    **{f"{i:02d}": (5 * (i - 1), 5) for i in range(1, 21)}, "21": (100, None)}
GROUPED_TOLERANCE = 0.3      # years, mean gap of the grouped median to the Bureau's

# Polygons code_shapes leaves unbound, settled on the boundary file's geometry
# (see the docstring): shape id -> (JIS code, the municipality's name). The
# comment is the label the boundary file draws.
EXTRA_SHAPES: dict[str, tuple[str, str]] = {
    "22064153B13478238771349": ("01204", "Asahikawa"),  # drawn 'Aashikawa'
    "22064153B1959164331993": ("01219", "Monbetsu"),  # drawn 'Mombetsu'
    "22064153B49406403757983": ("01361", "Esashi"),  # drawn 'Esashi' (Hiyama)
    "22064153B1201849018172": ("01392", "Suttsu"),  # drawn 'Suttu'
    "22064153B97366391425501": ("01454", "Toma"),  # drawn 'Tohma'
    "22064153B39468717619426": ("01465", "Kenbuchi"),  # drawn 'Kembuchi'
    "22064153B74616285910388": ("01481", "Mashike"),  # drawn 'Mashike'
    "22064153B9027189950521": ("01563", "Omu"),  # drawn 'Oumu'
    "22064153B58836725591580": ("01646", "Hombetsu"),  # drawn 'Honbetsu'
    "22064153B6517008589479": ("02201", "Aomori"),  # drawn 'Aomori'
    "22064153B24219941645935": ("02423", "Oma"),  # drawn 'Ooma'
    "22064153B24156704144787": ("02424", "Higashidori"),  # drawn 'Higashidoori'
    "22064153B15735563052201": ("03484", "Tanohata"),  # drawn 'Tanohara'
    "22064153B40478377839978": ("03507", "Hirono"),  # drawn 'Hirono'
    "22064153B93921143123339": ("04323", "Shibata"),  # drawn 'Shibara'
    "22064153B61358356464849": ("04445", "Kami"),  # drawn 'Kammi'
    "22064153B19116581600045": ("05201", "Akita"),  # drawn 'Akita'
    "22064153B11591323942731": ("06201", "Yamagata"),  # drawn 'Yamagata'
    "22064153B57621405150559": ("06365", "Okura"),  # drawn 'Ohkura'
    "22064153B57801992155462": ("07201", "Fukushima"),  # drawn 'Fukushima'
    "22064153B40136139146839": ("08233", "Namegata"),  # drawn 'Namekata'
    "22064153B87072224192540": ("09210", "Otawara"),  # drawn 'Ootawara'
    "22064153B23148495981135": ("11100", "Saitama"),  # drawn 'Saitama'
    "22064153B16459031557594": ("12100", "Chiba"),  # drawn 'Chiba'
    "22064153B79630920379478": ("12213", "Togane"),  # drawn 'Toogane'
    "22064153B67581321748824": ("12234", "Minamiboso"),  # drawn 'Minamibouso'
    "22064153B825337930111": ("12235", "Sosa"),  # drawn 'Sousa'
    "22064153B71828449311091": ("12349", "Tonosho"),  # drawn 'Toonosho'
    "22064153B58604351029537": ("13421", "Ogasawara"),  # drawn 'Ogasawara'
    "22064153B90768154691941": ("14130", "Kawasaki"),  # drawn 'Kawasaki'
    "22064153B23217272115075": ("14341", "Oiso"),  # drawn 'Oiso'
    "22064153B8665907160310": ("14382", "Hakone"),  # drawn 'Hakone'
    "22064153B18479522971761": ("15100", "Niigata"),  # drawn 'Niigata'
    "22064153B11370403812277": ("16201", "Toyama"),  # drawn 'Toyama'
    "22064153B60503510934184": ("16204", "Uozu"),  # drawn 'Uodu'
    "22064153B59618567090175": ("17386", "Hodatsushimizu"),  # drawn 'Houdatsushimizu'
    "22064153B13144997370504": ("18201", "Fukui"),  # drawn 'Fukui'
    "22064153B39059468846862": ("18205", "Ono"),  # drawn 'Oono' (Fukui)
    "22064153B92561466668703": ("18483", "Oi"),  # drawn 'Ooi'
    "22064153B30747054135081": ("19201", "Kofu"),  # drawn 'Koufu' (Yamanashi)
    "22064153B45156088025009": ("19202", "Fujiyoshida"),  # drawn '?????'
    "22064153B41354551896797": ("19206", "Otsuki"),  # drawn 'Ootsuki'
    "22064153B519565970341": ("19208", "Minami-Alps"),  # drawn 'Minamiarupusu'
    "22064153B26111310234357": ("19213", "Koshu"),  # drawn 'Koushu'
    "22064153B87894076500012": ("19422", "Doshi"),  # drawn 'Doushi'
    "22064153B88669235683638": ("20201", "Nagano"),  # drawn 'Nagano'
    "22064153B43232659310460": ("20212", "Omachi"),  # drawn 'Oomachi' (Nagano)
    "22064153B36124177261104": ("20220", "Azumino"),  # drawn 'Adumino'
    "22064153B37672699687454": ("20417", "Oshika"),  # drawn 'Ooshika'
    "22064153B55696485794579": ("20429", "Otaki"),  # drawn 'Outaki'
    "22064153B10063200690088": ("20430", "Okuwa"),  # drawn 'Ookuwa'
    "22064153B61527088541433": ("20590", "Iizuna"),  # drawn 'Iiduna'
    "22064153B39922172056835": ("21201", "Gifu"),  # drawn 'Gifu'
    "22064153B18541020859979": ("21221", "Kaizu"),  # drawn 'Kaidu'
    "22064153B12869480434443": ("21381", "Godo"),  # drawn 'Goudo'
    "22064153B98871481609914": ("21403", "Ono"),  # drawn 'Oono' (Gifu)
    "22064153B35070175546875": ("22100", "Shizuoka"),  # drawn 'Shizuoka'
    "22064153B26463696706835": ("22203", "Numazu"),  # drawn 'Numadu'
    "22064153B10622080660464": ("22212", "Yaizu"),  # drawn 'Yaidu'
    "22064153B40173018789364": ("22215", "Gotemba"),  # drawn 'Gotenba'
    "22064153B87793948617144": ("22301", "Higashiizu"),  # drawn 'Higashiizu'
    "22064153B52291408422766": ("22302", "Kawazu"),  # drawn 'Kawadu'
    "22064153B85931137925845": ("23217", "Konan"),  # drawn 'Kounan' (Aichi)
    "22064153B94848562576718": ("23223", "Obu"),  # drawn 'Oobu'
    "22064153B13741289865163": ("23232", "Aisai"),  # drawn 'Ansai'
    "22064153B43785762223582": ("23302", "Togo"),  # drawn 'Tougou'
    "22064153B48186183517064": ("23501", "Kota"),  # drawn 'Kouta'
    "22064153B28414045924235": ("23562", "Toei"),  # drawn 'Touei'
    "22064153B30375928590829": ("24324", "Toin"),  # drawn 'Touin'
    "22064153B34425405263494": ("25214", "Maibara"),  # drawn 'Maibara'
    "22064153B57425006507818": ("26100", "Kyoto"),  # drawn 'Kyoto'
    "22064153B3938039280311": ("27100", "Osaka"),  # drawn 'Osaka'
    "22064153B38947998190164": ("27140", "Sakai"),  # drawn 'Sakai'
    "22064153B3707797018061": ("27222", "Habikino"),  # drawn 'Habikino'
    "22064153B67146630599686": ("28203", "Akashi"),  # drawn 'Akashi'
    "22064153B99520360805383": ("28221", "Tamba-Sasayama"),  # drawn 'Sasayama'
    "22064153B14409781546574": ("28226", "Awaji"),  # drawn 'Awaji'
    "22064153B21881953859573": ("29201", "Nara"),  # drawn 'Nara'
    "22064153B85437171259684": ("30201", "Wakayama"),  # drawn 'Wakayama'
    "22064153B65800581846028": ("30362", "Hirogawa"),  # drawn 'Hirogawa'
    "22064153B17536493511153": ("31201", "Tottori"),  # drawn 'Tottori'
    "22064153B55424285147191": ("31328", "Chizu"),  # drawn 'Chidu'
    "22064153B32308822660767": ("31364", "Misasa"),  # drawn 'Miasa'
    "22064153B69891847725817": ("31384", "Hiezu"),  # drawn 'Hiedu'
    "22064153B61047916899475": ("31390", "Hoki"),  # drawn 'Houki'
    "22064153B86478142547352": ("31403", "Kofu"),  # drawn 'Koufu' (Tottori)
    "22064153B3574187835078": ("32205", "Oda"),  # drawn 'Ooda'
    "22064153B86801747373252": ("32207", "Gotsu"),  # drawn 'Goutsu'
    "22064153B3969862222627": ("32449", "Onan"),  # drawn 'Oonan'
    "22064153B47469236554060": ("33100", "Okayama"),  # drawn 'Okayama'
    "22064153B8516585574683": ("33208", "Soja"),  # drawn 'Souja'
    "22064153B90382038348999": ("34100", "Hiroshima"),  # drawn 'Hiroshima'
    "22064153B7322851157107": ("34211", "Otake"),  # drawn 'Ootake'
    "22064153B61546273634487": ("34368", "Akiota"),  # drawn 'Akioota'
    "22064153B86297113496232": ("34545", "Jinsekikogen"),  # drawn 'Jinsekikougen'
    "22064153B28331596269752": ("35203", "Yamaguchi"),  # drawn 'Yamaguchi'
    "22064153B42900229299916": ("35206", "Hofu"),  # drawn 'Houfu'
    "22064153B58156912777265": ("35305", "Suo-Oshima"),  # drawn 'Suo Ooshima'
    "22064153B8024533352103": ("35341", "Kaminoseki"),  # drawn 'Kaminoseki'
    "22064153B17826218371858": ("36201", "Tokushima"),  # drawn 'Tokushima'
    "22064153B40400083075761": ("36321", "Sanagochi"),  # drawn 'Sanagouchi'
    "22064153B63401696697477": ("37206", "Sanuki"),  # drawn 'Sanuki'
    "22064153B17737822356535": ("37324", "Shodoshima"),  # drawn 'Syoudoshima'
    "22064153B59225820770411": ("37386", "Utazu"),  # drawn 'Utadu'
    "22064153B9452209011947": ("38215", "Toon"),  # drawn 'Touon'
    "22064153B20820198931231": ("38356", "Kamijima"),  # drawn 'Kamijima'
    "22064153B94443438334718": ("38386", "Kumakogen"),  # drawn 'Kumakougen'
    "22064153B81541803695444": ("39201", "Kochi"),  # drawn 'Kochi'
    "22064153B3528434639026": ("39211", "Konan"),  # drawn 'Kounan' (Kochi)
    "22064153B99823885045557": ("39301", "Toyo"),  # drawn 'Touyou'
    "22064153B5531323380958": ("40130", "Fukuoka"),  # drawn 'Fukuoka'
    "22064153B43185436543368": ("40202", "Omuta"),  # drawn 'Oomura'
    "22064153B51668010168839": ("40203", "Kurume"),  # drawn 'Kume'
    "22064153B45322323594402": ("40204", "Nogata"),  # drawn 'Noogata'
    "22064153B94127780812190": ("40205", "Iizuka"),  # drawn 'IIduka'
    "22064153B68363974409505": ("40212", "Okawa"),  # drawn 'Ookawa'
    "22064153B28508352708384": ("40216", "Ogori"),  # drawn 'Ogoori'
    "22064153B25569633235651": ("40219", "Onojo"),  # drawn 'Oonojo'
    # Miyawaka was formed in 2006 from Miyata and Wakamiya; the polygon is
    # 143 km2 against the city's 140 and holds the city's office, which
    # stands in the former Miyata: it is the whole city under one old name.
    "22064153B29173837278044": ("40226", "Miyawaka"),  # drawn 'Wakamiya'
    "22064153B98138334835392": ("40401", "Kotake"),  # drawn 'Kotake'
    "22064153B87980745802810": ("40522", "Oki"),  # drawn 'Ooki'
    "22064153B30545680019922": ("40609", "Aka"),  # drawn 'Akamura'
    "22064153B80945575612703": ("40646", "Koge"),  # drawn 'Kouge'
    "22064153B43898079170437": ("41201", "Saga"),  # drawn 'Saga'
    "22064153B80804439158864": ("41423", "Omachi"),  # drawn 'Oomachi' (Saga)
    "22064153B95884811797842": ("41424", "Kohoku"),  # drawn 'Kouhoku'
    "22064153B19125244688726": ("42201", "Nagasaki"),  # drawn 'Nagasaki'
    "22064153B18037782605293": ("42211", "Goto"),  # drawn 'Got2'
    "22064153B94045297720108": ("42212", "Saikai"),  # drawn 'Saikai'
    "22064153B36411435837789": ("43100", "Kumamoto"),  # drawn 'Kumamoto'
    "22064153B35633292127249": ("43216", "Koshi"),  # drawn 'Koushi'
    "22064153B70489840196790": ("43367", "Nankan"),  # drawn 'Minami Kan'
    "22064153B65854996769111": ("43403", "Ozu"),  # drawn 'Oodu'
    "22064153B39171502191048": ("43444", "Kosa"),  # drawn 'Kousa'
    "22064153B34289782846164": ("44201", "Oita"),  # drawn 'Ooita'
    "22064153B31214056666647": ("44212", "Bungo-Ono"),  # drawn 'Bungo Oono'
    "22064153B44963787773880": ("45201", "Miyazaki"),  # drawn 'Miyazaki'
    "22064153B27005462697609": ("45206", "Hyuga"),  # drawn 'Hyuuga'
    "22064153B25042190901764": ("46201", "Kagoshima"),  # drawn 'Kagoshima'
    "22064153B21914755064517": ("46217", "Soo"),  # drawn 'Soo'
    "22064153B32453256362792": ("46452", "Yusui"),  # drawn 'Yuusui'
    "22064153B27870068763569": ("46468", "Osaki"),  # drawn 'Oosaki'
    "22064153B79178271585243": ("46491", "Minamiosumi"),  # drawn 'Minami Oosumi'
    "22064153B3414994926035": ("47381", "Taketomi"),  # drawn 'Taketomi'
}

# Polygons that hold more than one municipality: shape id -> (the codes, the
# name, what the boundary file does).
UNIONS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "22064153B65367495834859": (
        ("10206", "10448"), "Numata",
        "The boundary file's Numata polygon (510.7 km2) takes in the village of Showa "
        "(Showa-mura, 64.1 km2), which it does not draw apart; Numata is 443.5 km2. "
        "This is the two municipalities' census counts added together."),
}

# Polygons that are no census area at all: shape id -> why.
SLIVERS: dict[str, str] = {
    "22064153B20100015994007": (
        "This 0.2 km2 polygon, with no name in the boundary file, lies between Saitama "
        "City, Kawagoe and Ageo and holds no municipality's office: it is a sliver of the "
        "boundary file and no census area, so the census has no figure for it."),
}

RELIGION_NOTE = (
    "Japan's census does not ask religion -- its one question about who a person is, "
    "in the 2020 round as before, is nationality -- and nothing measures religion by "
    "municipality: the Agency for Cultural Affairs' 宗教統計調査 counts adherents as "
    "religious corporations report them, by prefecture only, and they sum to 175 million "
    "in a country of 126 million. The prefecture carries a modelled estimate.")
LANGUAGE_NOTE = (
    "Japan's census does not ask language -- its one question about who a person is, "
    "in the 2020 round as before, is nationality -- and no survey or register "
    "measures the language spoken at home by municipality. The prefecture carries a "
    "modelled estimate from nationality.")


# ---------------------------------------------------------------------------
# Reading the tables
# ---------------------------------------------------------------------------

def area_levels(payload: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """{area code: (level, Japanese name)} from a getMetaInfo answer. The levels
    are e-Stat's: 1 the nation, 2 a prefecture, 4 a city or a Tokyo ward, 5 a
    designated city's ward, 6 a town or village; Tokyo's 特別区部, the wards
    taken together, sits at a ward's level and is told apart by its name
    (``AGGREGATES``)."""
    status, message, inner = result_of(payload, "GET_META_INFO")
    if status != 0:
        raise SystemExit(f"japan_municipal: getMetaInfo: status {status}: {message}")
    for obj in listed(((inner.get("METADATA_INF") or {}).get("CLASS_INF") or {}).get("CLASS_OBJ")):
        if obj.get("@id") == "area":
            return {str(e.get("@code")): (str(e.get("@level")), str(e.get("@name")))
                    for e in listed(obj.get("CLASS"))}
    raise SystemExit("japan_municipal: the table's metadata has no area class")


def read_medians(values: list[dict[str, Any]]) -> dict[str, float]:
    """{area: the Bureau's median age}, to the one decimal the Bureau prints;
    the API serves five."""
    out: dict[str, float] = {}
    for v in values:
        try:
            out[str(v.get("@area"))] = round(float(v.get("$")), 1)
        except (TypeError, ValueError):
            continue
    return out


# e-Stat prints a count of nobody as "-" rather than 0. Any other symbol --
# "x" for a suppressed cell, "…" for one not tabulated -- is not a number,
# is left out, and so fails the sum checks below rather than being read as 0.
ZERO = "-"


def count(cell: Any) -> int | None:
    """A cell of an e-Stat table as people: "-" is 0, a symbol is None."""
    text = str(cell).strip()
    if text == ZERO:
        return 0
    try:
        return int(text)
    except ValueError:
        return None


def read_ages(values: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, int]]]:
    """{area: {sex "1"/"2": {age class: people}}}."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    for v in values:
        n = count(v.get("$"))
        if n is None:
            continue
        out.setdefault(str(v.get("@area")), {}).setdefault(
            str(v.get("@cat03")), {})[str(v.get("@cat01"))] = n
    return out


def read_nationality(values: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """{area: {国籍 code: people}}, both sexes."""
    out: dict[str, dict[str, int]] = {}
    for v in values:
        n = count(v.get("$"))
        if n is None:
            continue
        out.setdefault(str(v.get("@area")), {})[str(v.get("@cat02"))] = n
    return out


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def is_prefecture(code: str) -> bool:
    return code.endswith("000") and code != NATIONAL


def check_medians(median: dict[str, float]) -> None:
    prefectures = [v for code, v in median.items() if is_prefecture(code)]
    national = median.get(NATIONAL)
    if len(prefectures) != 47 or national is None \
            or not min(prefectures) <= national <= max(prefectures):
        raise SystemExit(f"japan_municipal: national median {national} against "
                         f"{len(prefectures)} prefectures "
                         f"({min(prefectures, default=None)}-{max(prefectures, default=None)}); "
                         f"not a table of medians by area")
    log(f"  national median {national:.1f}, prefectures "
        f"{min(prefectures):.1f}-{max(prefectures):.1f}")


def check_ages(ages: dict[str, dict[str, dict[str, int]]]) -> None:
    """Every area's age groups add to its total, for each sex; the prefectures'
    men and women add to the nation's."""
    for area, by_sex in ages.items():
        for sex in ("1", "2"):
            row = by_sex.get(sex) or {}
            if AGE_TOTAL not in row:
                raise SystemExit(f"japan_municipal: {area} sex {sex} has no all-ages row")
            parts = sum(row.get(c, 0) for c in AGE_GROUPS)
            if parts != row[AGE_TOTAL]:
                raise SystemExit(f"japan_municipal: {area} sex {sex}: age groups sum to "
                                 f"{parts:,} against {row[AGE_TOTAL]:,}")
    national = ages.get(NATIONAL) or {}
    for sex in ("1", "2"):
        summed = sum(v[sex][AGE_TOTAL] for c, v in ages.items() if is_prefecture(c))
        if summed != national[sex][AGE_TOTAL]:
            raise SystemExit(f"japan_municipal: the prefectures hold {summed:,} of sex {sex}, "
                             f"the nation {national[sex][AGE_TOTAL]:,}")
    log(f"  ages: {len(ages)} areas; every area's groups add to its total; Japan "
        f"{national['1'][AGE_TOTAL]:,} men, {national['2'][AGE_TOTAL]:,} women")


def check_nationality(nat: dict[str, dict[str, int]], ages: dict[str, dict[str, dict[str, int]]]
                      ) -> None:
    """Every area's parts add up, and its total is the same census count as the
    age table's men and women together."""
    foreign_codes = [c for c in NATIONALITY_CODES if c != "2"]
    for area, row in nat.items():
        missing = [c for c in list(NATIONALITY_CODES) + [CODE_TOTAL, CODE_FOREIGN, CODE_UNKNOWN]
                   if c not in row]
        if missing:
            raise SystemExit(f"japan_municipal: nationality row {area} lacks {missing}")
        if sum(row[c] for c in foreign_codes) != row[CODE_FOREIGN]:
            raise SystemExit(f"japan_municipal: {area}: nationalities sum to "
                             f"{sum(row[c] for c in foreign_codes):,} against a foreign total "
                             f"of {row[CODE_FOREIGN]:,}")
        if row["2"] + row[CODE_FOREIGN] + row[CODE_UNKNOWN] != row[CODE_TOTAL]:
            raise SystemExit(f"japan_municipal: {area}: Japanese, foreign and unknown do not "
                             f"make its total {row[CODE_TOTAL]:,}")
        by_sex = ages.get(area)
        if by_sex and by_sex["1"][AGE_TOTAL] + by_sex["2"][AGE_TOTAL] != row[CODE_TOTAL]:
            raise SystemExit(f"japan_municipal: {area}: the age table counts "
                             f"{by_sex['1'][AGE_TOTAL] + by_sex['2'][AGE_TOTAL]:,}, the "
                             f"nationality table {row[CODE_TOTAL]:,}")
    log(f"  nationality: {len(nat)} areas; every row's parts add up and its total is the "
        "age table's")


# Tokyo's 特別区部 (13100), the 23 special wards taken together, is a row of
# the tables beside the 23 wards themselves. e-Stat files it at the wards'
# own level, so it is told apart by its name, and it is never a municipality:
# counting it would count 9.7 million people twice.
AGGREGATES = ("特別区部",)


def is_municipality(code: str, levels: dict[str, tuple[str, str]]) -> bool:
    """A city, a Tokyo ward, a town or a village: e-Stat level 4 or 6, and not
    an aggregate of wards. A designated city's wards (level 5) are inside
    their city."""
    level, name = levels.get(code, ("", ""))
    return level in ("4", "6") and not name.endswith(AGGREGATES)


def check_children(nat: dict[str, dict[str, int]], levels: dict[str, tuple[str, str]]) -> None:
    """The municipalities of each prefecture (cities, towns and villages, and
    Tokyo's wards; a designated city's wards are inside their city and are not
    counted again, nor is the 23 wards' aggregate) add up to the prefecture."""
    sums: Counter = Counter()
    for code in levels:
        if is_municipality(code, levels) and code in nat:
            sums[code[:2]] += nat[code][CODE_TOTAL]
    for code, row in nat.items():
        if not is_prefecture(code):
            continue
        if sums[code[:2]] != row[CODE_TOTAL]:
            raise SystemExit(f"japan_municipal: prefecture {code}'s municipalities sum to "
                             f"{sums[code[:2]]:,} against its {row[CODE_TOTAL]:,}")
    log("  the municipalities of every prefecture add up to it")


def grouped(ages: dict[str, dict[str, dict[str, int]]], codes: tuple[str, ...]) -> float | None:
    """The median of the codes' men and women together, interpolated within the
    five-year group."""
    counts: Counter = Counter()
    for code in codes:
        for sex in ("1", "2"):
            for age, n in ages[code][sex].items():
                if age in AGE_GROUPS:
                    counts[age] += n
    return grouped_median((AGE_GROUPS[a][0], AGE_GROUPS[a][1], n) for a, n in counts.items())


def check_grouped(ages: dict[str, dict[str, dict[str, int]]], median: dict[str, float]) -> float:
    """The grouped median against the Bureau's own, over every municipality
    with people in it."""
    pairs = [(grouped(ages, (code,)), median[code]) for code in median
             if code in ages and not code.endswith("000")]
    gaps = [abs(ours - theirs) for ours, theirs in pairs if ours is not None]
    mean = sum(gaps) / len(gaps)
    log(f"  grouped medians against the Bureau's over {len(gaps)} areas: mean gap "
        f"{mean:.2f} years, largest {max(gaps):.2f}")
    if mean > GROUPED_TOLERANCE:
        raise SystemExit(f"japan_municipal: the grouped median runs {mean:.2f} years from the "
                         "Bureau's on average; not a method to stand in for it")
    return mean


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def bindings(code_shapes: dict[str, dict[str, Any]], drawn_ids: set[str], *,
             extra: dict[str, tuple[str, str]] | None = None,
             unions: dict[str, tuple[tuple[str, ...], str, str]] | None = None,
             ) -> dict[str, tuple[tuple[str, ...], str, bool]]:
    """{shape id: (codes, name, named by this file)} for every admin2 polygon
    with a census area. Refuses a code bound to two polygons, a polygon bound
    twice, and an id the map does not draw."""
    out: dict[str, tuple[tuple[str, ...], str, bool]] = {}
    for code, entry in code_shapes.items():
        if entry.get("level") != "admin2":
            continue
        out[entry["shape_id"]] = ((code,), entry["name"], False)
    extra = EXTRA_SHAPES if extra is None else extra
    unions = UNIONS if unions is None else unions
    for shape, (code, name) in extra.items():
        # A later run of wikidata_points may come to bind one of these itself;
        # to the same code that is agreement, to another a contradiction.
        if shape in out and out[shape][0] != (code,):
            raise SystemExit(f"japan_municipal: {shape} ({name}) is bound to {code} here and "
                             f"to {out[shape][0]} by code_shapes")
        out[shape] = ((code,), name, True)
    for shape, (codes, name, _) in unions.items():
        out[shape] = (codes, name, True)
    seen: dict[str, str] = {}
    for shape, (codes, name, _) in out.items():
        if shape not in drawn_ids:
            raise SystemExit(f"japan_municipal: {name} is bound to {shape}, which the map "
                             "does not draw")
        for code in codes:
            if code in seen:
                raise SystemExit(f"japan_municipal: {code} is bound to {seen[code]} and {shape}")
            seen[code] = shape
    return out


def prefecture_shapes(units: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """{prefecture code: (shape id, drawn name)} for all 47, by the drawn name."""
    by_name = {u["name"]: u["id"] for u in units}
    out = {}
    for code, (_, name) in PREFECTURES.items():
        if name not in by_name:
            raise SystemExit(f"japan_municipal: no drawn prefecture called {name!r}")
        out[code] = (by_name[name], name)
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def nationality_shares(rows: list[dict[str, int]]) -> tuple[list[dict[str, Any]], int, int, int]:
    """(shares, people with a recorded nationality, people without, total) over
    one or more areas' rows."""
    counts: Counter = Counter()
    unknown = total = 0
    for row in rows:
        for code, label in NATIONALITY_CODES.items():
            counts[label] += row[code]
        unknown += row[CODE_UNKNOWN]
        total += row[CODE_TOTAL]
    known = sum(counts.values())
    return hundred({k: float(v) for k, v in counts.items()}), known, unknown, total


def sources() -> list[dict[str, Any]]:
    return [{"field": "median_age", "name": SOURCE, "url": URL, "license": ESTAT_LICENCE},
            {"field": "sex_ratio", "name": SEX_SOURCE, "url": SEX_URL,
             "license": ESTAT_LICENCE},
            {"field": "population/ethnicity", "name": NATIONALITY_SOURCE,
             "url": NATIONALITY_URL, "year": YEAR, "license": ESTAT_LICENCE}]


def municipal_record(shape: str, codes: tuple[str, ...], name: str, *,
                     median: dict[str, float], ages: dict[str, dict[str, dict[str, int]]],
                     nat: dict[str, dict[str, int]], note: str = "") -> dict[str, Any]:
    men = sum(ages[c]["1"][AGE_TOTAL] for c in codes)
    women = sum(ages[c]["2"][AGE_TOTAL] for c in codes)
    union = len(codes) > 1
    extra: dict[str, Any] = {}
    if union:
        med = measure(grouped(ages, codes), unit="years", year=YEAR, source=SEX_SOURCE)
        extra["median_age_note"] = (
            "Interpolated within the five-year age group from the two municipalities' "
            "imputed age tables added together, because the Bureau's medians are for each "
            "municipality alone. " + note)
        extra["population_note"] = note
        extra["sex_ratio_note"] = note
    else:
        med = (measure(median[codes[0]], unit="years", year=YEAR, source=SOURCE)
               if codes[0] in median else None)
    shares, known, unknown, total = nationality_shares([nat[c] for c in codes])
    if total == 0:
        return empty_record(shape, codes, name)
    where = "these two municipalities" if union else "this municipality"
    ethnicity_note = (
        f"2020 Population Census (e-Stat table {NATIONALITY_TABLE}): population by "
        "NATIONALITY, not ethnicity, which Japan's census does not ask. 'Japanese' is everyone "
        "holding Japanese nationality, naturalised citizens and people of any ancestry "
        "included; 'Korean' is the census's 韓国，朝鮮 row. Shares are of the "
        f"{known:,} people of {where} whose nationality the census recorded; {unknown:,} "
        f"({(unknown / total * 100) if total else 0:.1f}% of {total:,}) recorded as neither "
        "Japanese nor foreign are left out." + (f" {note}" if note else "")
        + f" Written by the map owner's decision of {DECISION}.")
    return record(
        f"JPN-{'+'.join(codes)}", name, level="admin2", parent="JPN", country="JPN",
        codes={"jis": "+".join(codes)}, match_by="shape_id", shape_id=shape,
        population=measure(total, year=YEAR, source=POPULATION_SOURCE),
        median_age=med, **extra,
        sex_ratio=sex_ratio(men, women, year=YEAR, source=SEX_SOURCE),
        ethnicity=shares, ethnicity_year=YEAR, ethnicity_basis="nationality",
        ethnicity_note=ethnicity_note,
        religion=gap(NOT_COLLECTED, RELIGION_NOTE),
        language=gap(NOT_COLLECTED, LANGUAGE_NOTE),
        sources=sources())


# Futaba, in Fukushima, was wholly under an evacuation order on census day
# in 2020, and the census counted nobody living there. That count is
# written; a median, a sex ratio and a composition of nobody are not.
EMPTY_NOTE = ("The 2020 census counted nobody living here: on census day, 1 October 2020, "
              "the whole municipality was under the evacuation order issued after the 2011 "
              "Fukushima Daiichi nuclear accident. There is no one to have a median age, a sex "
              "ratio or a nationality.")


def empty_record(shape: str, codes: tuple[str, ...], name: str) -> dict[str, Any]:
    return record(
        f"JPN-{'+'.join(codes)}", name, level="admin2", parent="JPN", country="JPN",
        codes={"jis": "+".join(codes)}, match_by="shape_id", shape_id=shape,
        population=measure(0, year=YEAR, source=POPULATION_SOURCE),
        population_note=EMPTY_NOTE,
        median_age=gap("not_available", EMPTY_NOTE), sex_ratio=gap("not_available", EMPTY_NOTE),
        ethnicity=gap("not_available", EMPTY_NOTE),
        religion=gap(NOT_COLLECTED, RELIGION_NOTE), language=gap(NOT_COLLECTED, LANGUAGE_NOTE),
        sources=[sources()[2]])


def build(median: dict[str, float], ages: dict[str, dict[str, dict[str, int]]],
          nat: dict[str, dict[str, int]], levels: dict[str, tuple[str, str]],
          code_shapes: dict[str, dict[str, Any]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]], *,
          extra: dict[str, tuple[str, str]] | None = None,
          unions: dict[str, tuple[tuple[str, ...], str, str]] | None = None,
          slivers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    check_medians(median)
    check_ages(ages)
    check_nationality(nat, ages)
    check_children(nat, levels)
    check_grouped(ages, median)
    unions = UNIONS if unions is None else unions
    slivers = SLIVERS if slivers is None else slivers
    labels = {u["id"]: u["name"] for u in admin2}
    bound = bindings(code_shapes, set(labels), extra=extra, unions=unions)
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for shape, (codes, name, named_here) in sorted(bound.items(), key=lambda kv: kv[1][0]):
        if any(c not in nat or c not in ages for c in codes):
            missing.append(f"{name} {codes}")
            continue
        if not all(is_municipality(c, levels) for c in codes):
            raise SystemExit(f"japan_municipal: {name} is bound to {codes}, which are not all "
                             "municipalities (e-Stat levels "
                             f"{[levels.get(c, ('?',))[0] for c in codes]})")
        note = unions[shape][2] if shape in unions else ""
        rec = municipal_record(shape, codes, name, median=median, ages=ages, nat=nat, note=note)
        aliases = [levels[c][1] for c in codes]
        if named_here and labels[shape] != name and labels[shape] != shape:
            aliases.insert(0, labels[shape])
        rec["aliases"] = aliases
        records.append(rec)
    if missing:
        raise SystemExit(f"japan_municipal: bound codes with no row in the tables: {missing}")
    for shape, why in slivers.items():
        if shape not in labels:
            raise SystemExit(f"japan_municipal: the sliver {shape} is not drawn")
        records.append(record(
            f"JPN-{shape}", labels[shape], level="admin2", parent="JPN", country="JPN",
            match_by="shape_id", shape_id=shape,
            population=gap("not_available", why), median_age=gap("not_available", why),
            sex_ratio=gap("not_available", why), ethnicity=gap("not_available", why),
            religion=gap(NOT_COLLECTED, RELIGION_NOTE),
            language=gap(NOT_COLLECTED, LANGUAGE_NOTE)))
    unbound = sorted(set(labels) - set(bound) - set(slivers))
    if unbound:
        raise SystemExit(f"japan_municipal: drawn polygons with no census area: "
                         f"{[labels[s] for s in unbound]}")
    # The prefectures: median age and sex ratio, by the drawn name.
    for code, (shape, name) in prefecture_shapes(admin1).items():
        records.append(record(
            f"JPN-{code}", name, level="admin1", parent="JPN", country="JPN",
            codes={"jis": code}, match_by="shape_id", shape_id=shape,
            median_age=measure(median[code], unit="years", year=YEAR, source=SOURCE),
            sex_ratio=sex_ratio(ages[code]["1"][AGE_TOTAL], ages[code]["2"][AGE_TOTAL],
                                year=YEAR, source=SEX_SOURCE),
            sources=sources()[:2]))
    # Coverage of each prefecture by the polygons written, and their sum
    # never exceeding it.
    covered: Counter = Counter()
    for rec in records:
        if rec["level"] == "admin2" and isinstance(rec["population"], dict) \
                and rec["population"].get("value"):
            covered[rec["codes"]["jis"][:2]] += rec["population"]["value"]
    short = []
    for code in PREFECTURES:
        whole = nat[code][CODE_TOTAL]
        if covered[code[:2]] > whole:
            raise SystemExit(f"japan_municipal: the polygons of {code} hold {covered[code[:2]]:,}, "
                             f"more than the prefecture's {whole:,}")
        if covered[code[:2]] < whole:
            short.append(f"{PREFECTURES[code][1]} {whole - covered[code[:2]]:,}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin2')} municipal polygons written "
        f"({len(bound)} bound, {len(slivers)} sliver), 47 prefectures; people in no drawn "
        f"polygon, by prefecture: {', '.join(short) or 'none'}")
    return records


def main() -> int:
    key = app_id()
    median = read_medians(fetch_values(key, TABLE, {
        "cdTab": MEDIAN, "cdCat01": "0", "cdCat02": "0", "cdTime": TIME}))
    ages = read_ages(fetch_values(key, SEX_TABLE, {
        "cdTab": "2020_01", "cdCat01": ",".join([AGE_TOTAL, *AGE_GROUPS]), "cdCat02": "0",
        "cdCat03": "1,2", "cdTime": TIME}, limit=100_000))
    nat = read_nationality(fetch_values(key, NATIONALITY_TABLE, {
        "cdCat01": "0", "cdTime": TIME}, limit=100_000))
    levels = area_levels(call("getMetaInfo", {"statsDataId": NATIONALITY_TABLE}, key))
    shapes = (read_json(PROCESSED / "code_shapes.json", {}) or {}).get("JPN", {})
    records = build(median, ages, nat, levels, shapes, drawn("JPN", "admin1"),
                    drawn("JPN", "admin2"))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
