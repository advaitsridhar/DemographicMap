#!/usr/bin/env python3
"""Tajikistan: population, median age and sex ratio from the 2020 census.

The Agency on Statistics publishes the 2020 Population and Housing Census
volume by volume as PDF tables. Two are read here, both from volume 2
("Population of the Republic of Tajikistan by sex, age and marital status",
2022):

* table 1 -- the republic and each region by sex and single year of age,
  for 2010 and 2020;
* table 5 -- men and women in every region, city and district, with the
  number of women per 1,000 men.

**Regions** take their median age from table 1's single years and their
sex ratio from its men and women; table 5's region totals must agree.

**Cities and districts** take their population (men plus women) and sex
ratio from table 5. Age is published for regions only, so their median age
is left as a stated gap.

**Nationality** is not tabulated by the 2020 census at all. The 2010 census
counted it, and its volume III (*National composition, language proficiency
and citizenship of the population of the Republic of Tajikistan*, 2012)
gives, in the table "Population of individual nationalities by sex and age
groups", the seven largest nationalities -- Tajiks, Uzbeks, Russians, Kyrgyz,
Turkmen, Tatars, Kazakhs -- for the republic and each region. The volume is
read from the Internet Archive's capture of the Agency's old site. A
region's composition is those seven and, as "other", the rest of its 2010
population, which table 1 of the 2020 volume 2 prints beside 2020's (the
2010 column); its year is 2010. Checks: men and women make both sexes in
every row, the regions make the republic nationality by nationality, the
regions' 2010 totals make the republic's, and no region's seven exceed its
total. Volume III gives nationality for no city or district, and native
language for the republic and its urban and rural population only.

**Binding.** Table 5 names each unit in Tajik ("ноҳияи Ванҷ", "шаҳри Исфара
- ҳамагӣ") above its Russian name; units are keyed by the Tajik name and
placed on the drawn polygon ``UNITS`` names. The boundary file is older than
the 2016 renamings, so several districts are drawn under the names they had
then (Jilikul is Dusti, Qumsangir Jayhun, Rumi Jaloliddini Balkhi, Shuro-obod
Shamsiddin Shohin, Dzhami Abdurahmoni Jomi, Jirgatol Lakhsh, Tavildara
Sangvor, Ghonchi Devashtich, Bokhtar District Kushoniyon, Sarband the town
of Levakant). Cities the file does not draw are placed on the polygon that
holds them, tested against the drawn outlines: Khujand, Guliston, Buston and
Istiqlol in Ghafurov District, Bokhtar in Bokhtar District, Khorog in
Shughnon. A polygon holding several units carries their sum. A city "-
total" ("- всего") includes the rural communities it administers, which is
the territory the boundary file draws as that city's district.

Usage:
    python -m scripts.fetch_census.tajikistan_census
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from .redatam import median_age

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import as_drawn, read_json, shard_name  # noqa: E402

ISO3 = "TJK"
YEAR = 2020
OUT = "tajikistan_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
BASE = "https://www.stat.tj/wp-content/uploads/2024/05/"
AGES_URL = BASE + ("tablicza-1.-raspredelenie-postoyannogo-naseleniya-respubliki-i-oblastej-"
                   "po-polu-i-vozrastu.pdf")
SEXES_URL = BASE + ("tablicza-5.-chislennost-muzhchin-i-zhenshhin-oblastej-gorodov-i-rajonov-"
                    "respubliki-tadzhikistan-po-dannym-perepisi-naseleniya-i-zhilishhnogo-"
                    "fonda-2020-go.pdf")
PAGE = "https://www.stat.tj/en/population-and-housing-census/"
AGES_SOURCE = ("Agency on Statistics under the President of the Republic of Tajikistan, 2020 "
               "Population and Housing Census, volume 2, table 1: population of the republic "
               "and regions by sex and age")
SEXES_SOURCE = ("Agency on Statistics under the President of the Republic of Tajikistan, 2020 "
                "Population and Housing Census, volume 2, table 5: men and women in regions, "
                "cities and districts")
LICENCE = "Official statistics of the Agency on Statistics; free to use with attribution"
YEAR_2010 = 2010
# The 2010 census's volume III as the Agency's old site served it, linked from
# its "Archive of publications" page (stat.tj/ru/electronic-versions-of-
# publications, Internet Archive capture of 18 November 2019).
VOLUME3 = "http://oldstat.ww.tj/ru/img/526b8592e834fcaaccec26a22965ea2b_1355501132.pdf"
VOLUME3_ARCHIVED = "https://web.archive.org/web/2019id_/" + VOLUME3
VOLUME3_PAGE = "https://stat.tj/ru/electronic-versions-of-publications"
VOLUME3_SOURCE = ("Agency on Statistics under the President of the Republic of Tajikistan, "
                  "2010 Population and Housing Census, volume III: National composition, "
                  "language proficiency and citizenship (2012), table 'Population of individual "
                  "nationalities by sex and age groups'")
TOTALS_2010_SOURCE = ("Agency on Statistics under the President of the Republic of Tajikistan, "
                      "2020 Population and Housing Census, volume 2, table 1 (its 2010 column)")
NATIONALITY_TITLE = "Население отдельных национальностей по полу и возрастным группам"
# The table's seven nationalities (Russian names) -> the map's labels.
NATIONALITIES = {"таджики": "Tajik", "узбеки": "Uzbek", "русские": "Russian",
                 "кыргызы": "Kyrgyz", "туркмены": "Turkmen", "татары": "Tatar",
                 "казахи": "Kazakh"}

# A region heading's keywords (Russian or Tajik, Tajik letters folded) -> the
# drawn first-level label.
REGIONS = {
    "Gorno-Badakhshan Autonomous Region": ("бадахш",),
    "Sughd Region": ("согд", "сугд"),
    "Khatlon Region": ("хатлон",),
    "Dushanbe": ("душанбе",),
    "Districts of Republican Subordination": ("подчинения", "тобеи"),
}

# Table 5's units (keyed by ``tj_key`` of the Tajik name) -> drawn polygon.
UNITS = {
    # Gorno-Badakhshan
    "хоруг": "Shughnon District",          # Khorog, 71.55E 37.49N, inside Shughnon
    "ванч": "Vanj District", "дарвоз": "Darvoz District", "ишкошим": "Ishkoshim District",
    "мургоб": "Murghob District", "рошткала": "Roshtqal'a District",
    "рушон": "Rushon District", "шугнон": "Shughnon District",
    # Sughd
    "хучанд": "Ghafurov District",         # Khujand, 69.62E 40.28N
    "истиклол": "Ghafurov District",       # Istiqlol, 69.64E 40.57N
    "гулистон": "Ghafurov District",       # Guliston, 69.82E 40.27N
    "бустон": "Ghafurov District",         # Buston, 69.70E 40.22N
    "гафуров": "Ghafurov District",
    "исфара": "Isfara District", "конибодом": "Konibodom District",
    "панчакент": "Panjakent District", "истаравшан": "Istaravshan District",
    "айни": "Ayni District", "ашт": "Asht District",
    "деваштич": "Ghonchi District",        # Ghonchi District, renamed Devashtich 2016
    "зафаробод": "Zafarobod District", "расулов": "Jabbor Rasulov District",
    "кухистонимастчох": "Kuhistoni Mastchoh District", "мастчох": "Mastchoh District",
    "спитамен": "Spitamen District", "шахристон": "Shahriston District",
    # Khatlon
    "бохтар": "Bokhtar District",          # Bokhtar city, 68.78E 37.84N
    "кушониен": "Bokhtar District",        # Bokhtar District, renamed Kushoniyon 2018
    "кулоб": "Kulob District", "норак": "Norak District",
    "левакант": "Sarband District",        # Sarband, the town renamed Levakant
    "балчувон": "Baljuvon District", "хусрав": "Nosiri Khusrav District",
    "вахш": "Vakhsh District", "восе": "Vose' District", "хуросон": "Khuroson District",
    "дангара": "Danghara District",
    "дусти": "Jilikul District",           # Jilikul, renamed Dusti 2016
    "кубодиен": "Qabodiyon District",
    "балхи": "Rumi District",              # Rumi 2007-2016, then Jaloliddini Balkhi
    "чайхун": "Qumsangir District",        # Qumsangir, renamed Jayhun 2016
    "хамадони": "Hamadoni District", "муминобод": "Muminobod District",
    "фархор": "Farkhor District", "панч": "Panj District", "темурмалик": "Temurmalik District",
    "ховалинг": "Khovaling District",
    "чоми": "Dzhami District",             # Abdurahmoni Jomi
    "шахритус": "Shahrtuz District",
    "шохин": "Shuro-obod District",        # Shuro-obod, renamed Shamsiddin Shohin 2016
    "евон": "Yovon District",
    # Cities and districts of republican subordination
    "вахдат": "Vahdat District", "рогун": "Roghun District",
    "турсунзода": "Tursunzoda District", "хисор": "Hisor District",
    "варзоб": "Varzob District",
    "лахш": "Jirgatol District",           # Jirgatol, renamed Lakhsh 2016
    "нуробод": "Nurobod District", "рудаки": "Rudaki District", "рашт": "Rasht District",
    "сангвор": "Tavildara District",       # Tavildara, renamed Sangvor 2016
    "точикобод": "Tojikobod District", "файзобод": "Faizobod District",
    "шахринав": "Sharinav District",
}
TAJIK = str.maketrans({"ҳ": "х", "ҷ": "ч", "қ": "к", "ғ": "г", "ӯ": "у", "ӣ": "и",
                       "ё": "е", "ъ": ""})
MEDIAN_GAP = ("The 2020 census publishes single years of age for the republic and its regions "
              "only (volume 2, table 1); for cities and districts it gives men and women "
              "alone (table 5). The 2010 census's volume 2 (Population of the Republic of "
              "Tajikistan by sex, age and marital status, 2012) is laid out the same way -- "
              "age by sex for the republic and its regions, men and women alone for cities "
              "and districts -- so no census of either round gives a city's or a district's "
              "ages.")
VOLUMES = ("The Agency on Statistics has published the 2020 census in nine volumes -- "
           "population size and distribution; age, sex and marital status; education; "
           "households; sources of livelihood; employment; housing; migration; fertility -- "
           f"listed at {PAGE}")
COMPOSITION_GAP = (
    f"{VOLUMES}. None tabulates nationality or language, for the republic or any area. The "
    "2010 census's volume III (National composition, language proficiency and citizenship, "
    "2012) gives nationality for the republic and its five regions only, and native language "
    "for the republic and its urban and rural population only; it has no city or district "
    "table of either.")
LANGUAGE_GAP = (
    f"{VOLUMES}. None tabulates language. The 2010 census's volume III gives native language "
    "for the republic and its urban and rural population only (table 'Distribution of the "
    "population of the republic by sex, nationality and native language'), not by region, "
    "city or district.")
RELIGION_GAP = f"{VOLUMES}. None tabulates religion, for the republic or any area."


def tj_key(text: str) -> str:
    """'ноҳияи М.С.А.Ҳамадонӣ' -> 'мсахамадони'; 'шаҳри Исфара - ҳамагӣ' -> 'исфара'."""
    low = re.sub(r"\b(?:ноҳияи|шаҳри|ҳамагӣ)\b", " ", text.lower())
    return re.sub(r"[^а-я]", "", low.translate(TAJIK))


# A capital letter the PDF's text layer sets apart from the rest of its word
# ('ноҳияи К ушониён'): joined again for every name a reader sees.
SPLIT_CAPITAL = re.compile(r"(?<!\S)([А-ЯЁҚҒӮҲҶӢ]) (?=[а-яёқғӯҳҷӣ])")


def tidy(name: str) -> str:
    return SPLIT_CAPITAL.sub(r"\1", " ".join(name.split()))


def unit_label(text: str) -> str:
    """The drawn polygon a Tajik unit name belongs to; exact key first, then a suffix."""
    key = tj_key(text)
    if key in UNITS:
        return UNITS[key]
    hits = {UNITS[k] for k in UNITS if len(k) >= 4 and key.endswith(k)}
    if len(hits) != 1:
        raise SystemExit(f"tajikistan_census: no single polygon for {text!r} ({key}): {hits}")
    return hits.pop()


def region_of(line: str) -> str | None:
    """The region a heading line names, 'national' for the republic, else None."""
    low = line.lower()
    if "республика таджикистан" in low:
        return "national"
    folded = low.translate(TAJIK)
    for region, words in REGIONS.items():
        if any(word in folded for word in words):
            return region
    return None


# --------------------------------------------------------------------------
# Table 5: men and women by region, city and district.

SEX_ROW = re.compile(r"^(?P<label>.*?)\s*(?P<men>\d+)\s+(?P<women>\d+)\s+(?P<ratio>\d+,\d)\s*$")
TAJIK_LETTERS = set("ҳҷқғӯӣҲҶҚҒӮӢ")
# Column headings repeated on every page, in Tajik letters and lower case.
COLUMN_WORDS = {"мардҳо", "занҳо"}


def continues(pending: str, line: str) -> bool:
    """Whether ``line`` carries on the Tajik unit name begun in ``pending``.

    A name runs over when the line before is the bare word ("ноҳияи" above
    "М.С.А.Ҳамадонӣ"), ends on a dash ("шаҳри Левакант -" above "ҳамагӣ"), or
    the next line is lower-case Tajik ("ноҳияи Кӯҳистони" above "мастчоҳ").
    The Russian name follows in Russian letters and is not part of it.
    """
    if not pending:
        return False
    if pending.lower() in ("ноҳияи", "шаҳри") or pending.endswith("-"):
        return True
    return (line[0].islower() and any(c in TAJIK_LETTERS for c in line)
            and line.lower() not in COLUMN_WORDS)


def parse_sexes(text: str) -> tuple[dict[str, tuple[int, int]],
                                     dict[str, list[tuple[str, int, int]]]]:
    """({region: (men, women)}, {region: [(Tajik unit name, men, women)]}).

    Each unit is named in Tajik on its own line(s), then in Russian on the
    line that carries its figures; its urban and rural rows follow and are
    skipped. A region's "Все население" row is its total. Dushanbe is one row.
    """
    totals: dict[str, tuple[int, int]] = {}
    units: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    region = "national"
    pending = ""
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        low = line.lower()
        m = SEX_ROW.match(line)
        if not m:
            if low.startswith(("ноҳияи", "шаҳри ")) or low == "шаҳри":
                pending = line
            elif continues(pending, line):
                pending = f"{pending} {line}"
            elif not pending:
                region = region_of(line) or region
            continue
        men, women = int(m.group("men")), int(m.group("women"))
        ratio = float(m.group("ratio").replace(",", "."))
        if men and abs(1000 * women / men - ratio) > 0.11:
            raise SystemExit(f"tajikistan_census: {line!r}: {women} women per {men} men is not "
                             f"{ratio} per thousand")
        label = m.group("label").lower()
        if "городское население" in label or "сельское население" in label:
            continue
        if "все население" in label:
            if region in totals:
                raise SystemExit(f"tajikistan_census: two totals for {region}: {line!r}")
            totals[region] = (men, women)
            pending = ""
            continue
        if "душанбе" in label:
            totals["Dushanbe"] = (men, women)
            pending = ""
            continue
        if not pending:
            raise SystemExit(f"tajikistan_census: a row with no unit named above it: {line!r}")
        units[region].append((pending, men, women))
        pending = ""
    if "national" in units:
        raise SystemExit(f"tajikistan_census: units before any region: {units['national'][:3]}")
    for name, rows in units.items():
        men, women = sum(r[1] for r in rows), sum(r[2] for r in rows)
        if (men, women) != totals.get(name):
            raise SystemExit(f"tajikistan_census: {name}'s units make {men:,} men and "
                             f"{women:,} women against {totals.get(name)}")
    regions = [totals.get(region) for region in REGIONS]
    if None in regions or "national" not in totals:
        raise SystemExit(f"tajikistan_census: table 5 totals found for {sorted(totals)}")
    if (sum(r[0] for r in regions), sum(r[1] for r in regions)) != totals["national"]:
        raise SystemExit(f"tajikistan_census: the regions make {regions}, the republic "
                         f"{totals['national']}")
    return totals, dict(units)


# --------------------------------------------------------------------------
# Table 1: sex and single year of age, republic and regions.

FIGURES = re.compile(r"((?:(?:\d+|-)\s+){5}(?:\d+|-))\s*$")


def age_label(label: str) -> int | None:
    """'до 1 года' -> 0, '21 года' -> 21, '100 лет и старше' -> 100; else None."""
    low = label.lower()
    if re.search(r"\bдо\s*1\s*год", low):
        return 0
    m = re.search(r"\b(\d{1,3})\s*(?:года|год|лет)\b", low)
    return int(m.group(1)) if m else None


def parse_ages(text: str) -> dict[str, dict[str, Any]]:
    """{region: {'total': (both, men, women), 'ages', 'men', 'women'}} for 2020.

    Rows carry six figures, both sexes, men and women for 2010 and then for
    2020; the last three are read. Each area prints its urban-and-rural
    block, then an urban and a rural block. The first is read; an area with
    no rural block (Dushanbe) may print its urban block alone, which is then
    the whole. Single years are kept, five-year groups ("0 - 4 лет")
    skipped; an open top ("100 лет и старше") counts as its first year when
    no single year above it is printed. The regions' single years must make
    the republic's, age by age.
    """
    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    region: str | None = None
    kind = None

    def open_block(name: str, part: str) -> dict[str, Any]:
        return blocks.setdefault((name, part), {
            "ages": Counter(), "men": Counter(), "women": Counter(), "total": None,
            "open": {}, "unstated": (0, 0, 0)})

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        low = line.lower()
        nums = FIGURES.search(line)
        if not nums:
            heading = region_of(line)
            if heading and heading != region:
                region, kind = heading, None
            if "городское и сельское" in low:
                kind = "all"
            elif low.startswith("городское"):
                kind = "urban"
            elif low.startswith("сельское"):
                kind = "rural"
            continue
        label = line[:nums.start()].strip(" .…")
        tag = label.lower()
        values = [0 if v == "-" else int(v) for v in nums.group(1).split()]
        both, men, women = values[3:]
        if men + women != both:
            raise SystemExit(f"tajikistan_census: {line!r}: men and women do not make both")
        if "городское и сельское" in tag:
            kind = "all"
        elif tag.startswith("городское"):
            kind = "urban"
        elif tag.startswith("сельское"):
            kind = "rural"
        if kind is None or region is None:
            continue
        entry = open_block(region, kind)
        if "население" in tag:
            if entry["total"] is not None:
                raise SystemExit(f"tajikistan_census: {region}: a second total {line!r}")
            entry["total"] = (both, men, women)
            entry["total2010"] = tuple(values[:3])
            if values[1] + values[2] != values[0]:
                raise SystemExit(f"tajikistan_census: {line!r}: 2010's men and women do not "
                                 f"make both")
            continue
        if "указ" in tag:
            entry["unstated"] = (both, men, women)
            continue
        if "-" in tag:
            continue                           # a five-year group
        age = age_label(tag)
        if age is None:
            continue
        if "старше" in tag or "более" in tag:
            entry["open"][age] = (both, men, women)
            continue
        if age in entry["ages"]:
            raise SystemExit(f"tajikistan_census: {region}: age {age} twice")
        entry["ages"][age] = both
        entry["men"][age] = men
        entry["women"][age] = women
    out: dict[str, dict[str, Any]] = {}
    for region in {name for name, _ in blocks}:
        if (region, "all") in blocks:
            part = "all"
        elif (region, "urban") in blocks and (region, "rural") not in blocks:
            part = "urban"
        else:
            raise SystemExit(f"tajikistan_census: {region}: no urban-and-rural block")
        entry = out[region] = blocks[(region, part)]
        if entry["total"] is None:
            raise SystemExit(f"tajikistan_census: {region} ({part}): no total row")
        top = max(entry["ages"], default=-1)
        for age, (both, men, women) in entry["open"].items():
            if age > top:
                entry["ages"][age] += both
                entry["men"][age] += men
                entry["women"][age] += women
        made = tuple(sum(entry[k].values()) + entry["unstated"][i]
                     for i, k in enumerate(("ages", "men", "women")))
        if made != entry["total"]:
            raise SystemExit(f"tajikistan_census: {region} ({part}): single years make {made} "
                             f"against {entry['total']}")
        if sorted(entry["ages"]) != list(range(len(entry["ages"]))):
            raise SystemExit(f"tajikistan_census: {region} ({part}): single years are not 0 "
                             f"to {len(entry['ages']) - 1} without a break")
    if "national" in out:
        for k in ("ages", "men", "women"):
            parts: Counter = Counter()
            for region in REGIONS:
                parts.update(out.get(region, {}).get(k, Counter()))
            if +parts != +out["national"][k]:
                wrong = sorted(a for a in set(parts) | set(out["national"][k])
                               if parts[a] != out["national"][k][a])
                raise SystemExit(f"tajikistan_census: the regions' {k} do not make the "
                                 f"republic's at ages {wrong[:10]}")
    return out


# --------------------------------------------------------------------------
# Volume III of the 2010 census: the seven largest nationalities by region.

SEX_LINE = re.compile(r"^(оба пола|мужчины|женщины)\s+(\d+|-)")


def nationality_text(pages: list[str]) -> str:
    """The pages of the table by nationality, sex and age group, and no others.

    It starts on the page that carries its title and figures (the contents
    page names it too, without figures) and runs until the next table's
    title, marital status, appears.
    """
    start = next((i for i, page in enumerate(pages)
                  if NATIONALITY_TITLE in " ".join(page.split()) and "Оба пола" in page), None)
    if start is None:
        raise SystemExit("tajikistan_census: volume III has no table of nationalities by sex "
                         "and age")
    kept = []
    for page in pages[start:]:
        if kept and "состоянию в браке" in " ".join(page.split()):
            break
        kept.append(page)
    return "\n".join(kept)


def parse_nationalities(text: str) -> dict[str, dict[str, tuple[int, int, int]]]:
    """{region or 'national': {label: (both, men, women)}} for the seven nationalities."""
    out: dict[str, dict[str, list[int | None]]] = defaultdict(dict)
    region: str | None = None
    nationality: str | None = None
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        low = line.lower()
        if not re.search(r"\d", line) and not SEX_LINE.match(low):
            heading = region_of(line)
            if heading:
                region, nationality = heading, None
            elif low in NATIONALITIES and region:
                nationality = NATIONALITIES[low]
                if nationality in out[region]:
                    raise SystemExit(f"tajikistan_census: volume III: {line} twice in {region}")
                out[region][nationality] = [None, None, None]
            continue
        m = SEX_LINE.match(low)
        if not m or not region or not nationality:
            continue
        slot = ("оба пола", "мужчины", "женщины").index(m.group(1))
        if out[region][nationality][slot] is not None:
            raise SystemExit(f"tajikistan_census: volume III: {region} {nationality}: "
                             f"{m.group(1)} twice")
        out[region][nationality][slot] = 0 if m.group(2) == "-" else int(m.group(2))
    table: dict[str, dict[str, tuple[int, int, int]]] = {}
    for name, rows in out.items():
        if sorted(rows) != sorted(NATIONALITIES.values()):
            raise SystemExit(f"tajikistan_census: volume III: {name} lists {sorted(rows)}")
        for label, (both, men, women) in rows.items():
            if None in (both, men, women) or men + women != both:
                raise SystemExit(f"tajikistan_census: volume III: {name} {label}: "
                                 f"{men} men and {women} women against {both}")
        table[name] = {label: tuple(v) for label, v in rows.items()}  # type: ignore[misc]
    if sorted(table) != sorted(["national", *REGIONS]):
        raise SystemExit(f"tajikistan_census: volume III covers {sorted(table)}")
    for label in NATIONALITIES.values():
        made = tuple(sum(table[r][label][i] for r in REGIONS) for i in range(3))
        if made != table["national"][label]:
            raise SystemExit(f"tajikistan_census: volume III: the regions' {label} make {made} "
                             f"against the republic's {table['national'][label]}")
    return table


def ethnicity_2010(table: dict[str, dict[str, tuple[int, int, int]]],
                   totals2010: dict[str, tuple[int, int, int]]) -> dict[str, dict[str, Any]]:
    """Each region's 2010 nationalities, the rest of its 2010 population as other."""
    if tuple(sum(totals2010[r][i] for r in REGIONS) for i in range(3)) != totals2010["national"]:
        raise SystemExit("tajikistan_census: the regions' 2010 totals do not make the "
                         "republic's")
    out: dict[str, dict[str, Any]] = {}
    for region in REGIONS:
        listed = {label: v[0] for label, v in table[region].items()}
        total = totals2010[region][0]
        other = total - sum(listed.values())
        if other < 0:
            raise SystemExit(f"tajikistan_census: {region}: its seven nationalities make "
                             f"{sum(listed.values()):,} of {total:,} in 2010")
        counts = {k: v for k, v in listed.items() if v}
        if other:
            counts["Other"] = other
        # The groups the 2010 census coded apart, Lakai and Kungrat among them,
        # are named only where the review asked for them, Khatlon; elsewhere
        # 'Other' is named for what it is -- in GBAO it is 72 people.
        among = (", among them the groups the census coded apart, such as Lakai and "
                 "Kungrat" if region == "Khatlon Region" else "")
        out[region] = {
            "ethnicity": shares(counts, total=total),
            "ethnicity_year": YEAR_2010,
            "ethnicity_note": (
                "Nationality (национальность) as each person declared it in the 2010 census, "
                "the latest to tabulate it: volume III's table of individual nationalities by "
                "sex and age groups names the seven largest -- Tajiks, Uzbeks, Russians, "
                "Kyrgyz, Turkmen, Tatars and Kazakhs -- by region; the rest of the region's "
                f"{total:,} people in 2010 ({other:,}) are 'Other'{among}. The counts are the "
                "2010 census's and add up to that year's population, not to the 2020 "
                "population this region carries. The 2020 census does not tabulate "
                "nationality.")}
    return out


# --------------------------------------------------------------------------
# Records.

def drawn_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (as_drawn(read_json(SITE / "admin1" / shard_name(ISO3), [])),
            as_drawn(read_json(SITE / "admin2" / shard_name(ISO3), [])))


def build(ages: dict[str, dict[str, Any]], totals: dict[str, tuple[int, int]],
          units: dict[str, list[tuple[str, int, int]]], a1: list[dict[str, Any]],
          a2: list[dict[str, Any]],
          nationalities: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    src = [{"field": "median_age", "name": AGES_SOURCE, "url": PAGE, "license": LICENCE},
           {"field": "population/sex_ratio", "name": SEXES_SOURCE, "url": PAGE,
            "license": LICENCE}]
    nationalities = nationalities or {}
    region_ids = {u["name"]: u["id"] for u in a1}
    if sorted(region_ids) != sorted(REGIONS):
        raise SystemExit(f"tajikistan_census: the map draws {sorted(region_ids)}")
    out: list[dict[str, Any]] = []
    for region in REGIONS:
        if region not in ages or region not in totals:
            raise SystemExit(f"tajikistan_census: {region} missing from a table")
        both, men, women = ages[region]["total"]
        if (men, women) != totals[region]:
            raise SystemExit(f"tajikistan_census: {region}: table 1 has {men:,}/{women:,}, "
                             f"table 5 {totals[region]}")
        out.append(record(
            f"TJK-CENSUS-{region_ids[region]}", region, level="admin1", parent=ISO3,
            country=ISO3, match_by="shape_id", shape_id=region_ids[region],
            population=measure(both, year=YEAR, source=SEXES_SOURCE),
            median_age=measure(median_age(ages[region]["ages"]), year=YEAR, source=AGES_SOURCE),
            median_age_note=("Median of the census's single years of age, interpolated "
                             "within the year holding the middle person."),
            sex_ratio=measure(round(100 * men / women, 1), year=YEAR, source=SEXES_SOURCE,
                              unit="males_per_100_females"),
            sources=src + ([{"field": "ethnicity", "name": VOLUME3_SOURCE + "; " +
                             TOTALS_2010_SOURCE, "url": VOLUME3_PAGE, "year": YEAR_2010,
                             "license": LICENCE}] if region in nationalities else []),
            **{**composition_gaps(), **nationalities.get(region, {})}))
    parent_of = {u["id"]: u["parent"] for u in a2}
    name_of = {u["id"]: u["name"] for u in a1}
    polygons: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for region, rows in units.items():
        for name, men, women in rows:
            label = unit_label(name)
            hits = [u for u in a2 if u["name"] == label and name_of.get(parent_of[u["id"]]) == region]
            if len(hits) != 1:
                raise SystemExit(f"tajikistan_census: {name} -> {label} in {region}: "
                                 f"{len(hits)} drawn polygons")
            polygons[hits[0]["id"]].append((name, men, women))
    missing = [u["name"] for u in a2 if u["id"] not in polygons]
    if missing:
        raise SystemExit(f"tajikistan_census: drawn polygons with no unit: {missing}")
    for shape in a2:
        rows = polygons[shape["id"]]
        men, women = sum(r[1] for r in rows), sum(r[2] for r in rows)
        region = name_of[shape["parent"]]
        note = (f"The polygon drawn as {shape['name']} holds "
                f"{', '.join(tidy(r[0]) for r in rows)}: the boundary file does not draw them "
                f"apart, so it carries their sum." if len(rows) > 1 else None)
        out.append(record(
            f"TJK-CENSUS-{shape['id']}", shape["name"], level="admin2",
            parent=f"TJK-CENSUS-{shape['parent']}", parent_name=region, country=ISO3,
            match_by="shape_id", shape_id=shape["id"],
            aliases=sorted({tidy(r[0]) for r in rows}),
            population=measure(men + women, year=YEAR, source=SEXES_SOURCE),
            population_note=note,
            sex_ratio=measure(round(100 * men / women, 1), year=YEAR, source=SEXES_SOURCE,
                              unit="males_per_100_females"),
            sex_ratio_note=note,
            median_age=gap(NOT_AVAILABLE, MEDIAN_GAP),
            sources=src[1:], **composition_gaps()))
    return out


def composition_gaps() -> dict[str, Any]:
    return {"religion": gap(NOT_AVAILABLE, RELIGION_GAP),
            "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
            "ethnicity": gap(NOT_AVAILABLE, COMPOSITION_GAP)}


def pdf_pages(blob: bytes) -> list[str]:
    import logging

    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages]


def pdf_text(blob: bytes) -> str:
    return "\n".join(pdf_pages(blob))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("tajikistan_census: 2020 census volume 2, tables 1 and 5; 2010 census volume III")
    ages = parse_ages(pdf_text(http_get(AGES_URL, binary=True, timeout=300)))  # type: ignore[arg-type]
    log(f"  table 1: {sorted(ages)}")
    totals, units = parse_sexes(pdf_text(http_get(SEXES_URL, binary=True, timeout=300)))  # type: ignore[arg-type]
    log(f"  table 5: {sum(len(v) for v in units.values())} cities and districts")
    blob = http_get(VOLUME3_ARCHIVED, binary=True, timeout=600)
    assert isinstance(blob, bytes)
    if blob[:5] != b"%PDF-":
        raise SystemExit(f"tajikistan_census: {VOLUME3} came back as something other than a "
                         f"PDF: {blob[:80]!r}")
    table = parse_nationalities(nationality_text(pdf_pages(blob)))
    totals2010 = {region: ages[region]["total2010"] for region in ["national", *REGIONS]}
    nationalities = ethnicity_2010(table, totals2010)
    log(f"  volume III (2010): {', '.join(f'{r} {sum(v[0] for v in table[r].values()):,}' for r in REGIONS)}")
    a1, a2 = drawn_units()
    out = build(ages, totals, units, a1, a2, nationalities)
    for r in out:
        med = r["median_age"].get("value") if isinstance(r["median_age"], dict) else None
        eth = (", ".join(f"{x['group']} {x['pct']}" for x in r["ethnicity"][:3])
               if isinstance(r["ethnicity"], list) else "")
        log(f"    {r['level']} {r['name']}: {r['population']['value']:,}, median {med}, "
            f"ratio {r['sex_ratio']['value']} {eth}")
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
