#!/usr/bin/env python3
"""Kenya: the 2019 census's head count, sex ratio and median age by county and constituency.

The Kenya National Bureau of Statistics published the 2019 Kenya Population and
Housing Census in four volumes, and Code for Africa's openAFRICA portal holds
the Bureau's tables from them as CSV (KNBS's own site fails TLS verification on
a clean client). Three are read here:

* Volume I, *Distribution of Population by Sex and County*: everyone counted,
  by sex (male, female, intersex), for the country and the 47 counties.
* Volume III, *Distribution of Population by Age, Sex, County and Sub-County*:
  everyone by single year of age (to 99, then 100 and over, and "not stated")
  and by sex, for every county ("ALL") and every sub-county.
* Volume II, *Distribution of Population by Sex, Number of Households, Land
  Area, Population Density and Sub County*: everyone by sex for every
  sub-county, its totals counting intersex persons as well. Its totals are the
  constituencies' head counts, and its men and women must be Volume III's.

**Counties.** Population is Volume I's count of everyone, intersex persons
included; the sex ratio is men per 1,000 women; the median age is interpolated
within the single year of age that holds the middle person, leaving out the
ages not stated. The map carried the county totals of Volume IV's religion
table until now, which count a little fewer people than Volume I.

**Constituencies.** The map's second level is the 290 constituencies; the
census tabulates its 340-odd sub-counties, and the two are not the same units
everywhere. A constituency is written only where its census figures are
established: where its ground is known to be one sub-county or a set of whole
ones (CROSSWALK), or, failing that, where every constituency of the county is
a sub-county of the same name and those sub-counties make the county. OCHA's
boundary dataset has no sub-county outlines (its second level is the
constituencies), so CROSSWALK rests on the land area Volume II gives each
sub-county against the area of the constituency's polygon, with names that
correspond; the rule is set out above the constant. Every other constituency
gets a gap that says why. And every constituency says why it has no religion,
ethnicity or language (COMPOSITION): Volume IV publishes the first by county
and the second for the country only, and no volume tabulates the third.

**Bomet and Kericho.** The map's Bomet County polygon takes in Bureti, which
the census counts as a sub-county of Kericho (OCHA's boundaries put Buret
constituency in Kericho too): Bomet's 2,507 km2 and Bureti's 321 make 2,828
against the polygon's 2,819, and Kericho's 2,436 less Bureti's make 2,115
against 2,102. So the Bomet polygon gets Bomet County and Bureti added up, and
the Kericho polygon Kericho County less Bureti (MOVED).

**Checks.** Every row's single years make its total and its sexes make it too;
each county's sub-counties make the county; Volume III's county totals are
Volume I's without the intersex persons.

Usage:
    python -m scripts.fetch_census.kenya_census --points
    python -m scripts.fetch_census.kenya_census
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = "kenya_census.json"
YEAR = 2019
SITE = PROCESSED.parent.parent / "site" / "data"
PAGE = "https://open.africa/dataset/2019-kenya-population-and-housing-census"
BASE = "https://open.africa/dataset/9b94fe50-9d75-4b92-be00-6354c6e6cc88/resource/"
VOL1 = BASE + ("384b93cf-ede0-4e05-9f36-a8e8e09b21a7/download/"
               "kenya-population-by-sex-and-county.csv")
VOL3 = BASE + ("b7edfdb4-2a07-4332-8796-2f00968aff0e/download/"
               "distribution-of-population-by-age-sex-county-and-sub-county-kenya-2019-census-"
               "volume-iii.csv")
VOL2 = BASE + ("ddddbe91-b5fa-4449-a50d-846401e701c4/download/"
               "distribution-of-population-by-sex-and-sub-county-2019-census-volume-ii.csv")
SOURCE1 = ("Kenya National Bureau of Statistics, 2019 Kenya Population and Housing Census, "
           "Volume I: Population by County and Sub-County, distribution of population by sex "
           "and county")
SOURCE2 = ("Kenya National Bureau of Statistics, 2019 Kenya Population and Housing Census, "
           "Volume II: Distribution of Population by Administrative Units, population by sex "
           "and sub-county")
SOURCE3 = ("Kenya National Bureau of Statistics, 2019 Kenya Population and Housing Census, "
           "Volume III: Distribution of Population by Age and Sex, by county and sub-county")
SOURCE4 = ("Kenya National Bureau of Statistics, 2019 Kenya Population and Housing Census, "
           "Volume IV: Distribution of Population by Socio-Economic Characteristics")
# What the census publishes on religion, ethnicity and language, said on every
# constituency: Volume IV gives religion by county (Table 2.30, kenya.py) and
# ethnicity for the country only (openAFRICA's table of it has one row per
# group and no county), and no volume tabulates language.
COMPOSITION = ("Kenya's 2019 census reports give religion by county and ethnicity for the "
               "country as a whole, and no languages, so none of the three is published for "
               "a constituency.")
LICENCE = "Creative Commons Attribution (openAFRICA copy of a KNBS publication)"
NATIONAL = 47_564_296
POINTS = "kenya_subcounty_points.json"
COD_AB = "cod-ab-ken"
# Share of a county's people the matched sub-counties must make before its
# constituencies are taken to be its sub-counties (forest and park rows of a
# few hundred people are the rest).
PARTITION = 0.995

# The map's county label where it is not the census's name folded.
COUNTY_ALIASES = {"tharakanithi": "Tharaka", "taitataveta": "Taita Taveta"}
# Constituencies whose ground is one census sub-county or a set of whole ones,
# by county: {county fold: {constituency label: [sub-county folds, or
# "county/sub-county" for another county's]}}. The evidence is the land area
# the census gives each sub-county (Volume II, "Distribution of Population by
# Land Area, Density and Sub County") against the area of the constituency's
# polygon, with names that correspond (the same name, or the sub-county the
# constituency was known by: Rachuonyo North for Karachuonyo, Athi River for
# Mavoko). Where every constituency of a county is listed, each is within 7%;
# a lakeside polygon takes in water of Lake Victoria that the census leaves
# out, and is settled by its name and by the county's other constituencies
# being settled. Where only some are listed, each is within 3% or 1 km2. The
# figures after each entry are the census's km2 and the polygon's.
CROSSWALK: dict[str, dict[str, list[str]]] = {
    "transnzoia": {
        "Cherangany": ["transnzoiaeast"],  # 629 against 627
        "Endebess": ["endebess"],  # 678 against 667
        "Kiminini": ["kiminini"],  # 367 against 370
        "Kwanza": ["kwanza"],  # 465 against 464
        "Saboti": ["transnzoiawest"],  # 355 against 354
    },
    "nandi": {
        "Aldai": ["nandisouth"],  # 457 against 468
        "Chesumei": ["chesumei"],  # 475 against 488
        "Emgwen": ["nandicentral"],  # 362 against 362
        "Mosop": ["nandinorth"],  # 606 against 584
        "Nandi Hills": ["nandieast"],  # 392 against 394
        "Tinderet": ["tinderet"],  # 557 against 542
    },
    "machakos": {
        "Kangundo": ["kangundo"],  # 173 against 171
        "Kathiani": ["kathiani"],  # 204 against 207
        "Machakos Town": ["machakos", "kalama"],  # 760 against 758
        "Masinga": ["masinga"],  # 1,407 against 1,405
        "Matungulu": ["matungulu"],  # 581 against 580
        "Mavoko": ["athiriver"],  # 835 against 842
        "Mwala": ["mwala"],  # 1,013 against 1,019
        "Yatta": ["yatta"],  # 1,062 against 1,060
    },
    "kajiado": {
        "Kajiado Central": ["kajiadocentral"],  # 4,239 against 4,304
        "Kajiado East": ["isinya", "mashuuru"],  # 3,323 against 3,268
        "Kajiado North": ["kajiadonorth"],  # 111 against 113
        "Kajiado South": ["loitokitok"],  # 6,337 against 6,369
        "Kajiado West": ["kajiadowest"],  # 7,862 against 7,858
    },
    "isiolo": {
        "Isiolo North": ["isiolo", "merti"],  # 15,447 against 15,321
        "Isiolo South": ["garbatulla"],  # 9,902 against 10,078
    },
    "tanariver": {
        "Bura": ["tananorth"],  # 13,305 against 13,601
        "Galole": ["tanariver"],  # 9,167 against 9,687
        "Garsen": ["tanadelta"],  # 15,432 against 15,902
    },
    "westpokot": {
        "Kacheliba": ["pokotnorth"],  # 3,911 against 4,069
        "Kapenguria": ["westpokot"],  # 1,855 against 1,774
        "Pokot South": ["pokotsouth", "kipkomo"],  # 1,303 against 1,268
        "Sigor": ["pokotcentral"],  # 2,055 against 2,149
    },
    "busia": {
        "Budalangi": ["bunyala"],  # 192 against 306, lakeside
        "Butula": ["butula"],  # 247 against 242
        "Funyula": ["samia"],  # 262 against 273
        "Matayos": ["busia"],  # 196 against 192
        "Nambale": ["nambale"],  # 238 against 232
        "Teso North": ["tesonorth"],  # 261 against 258
        "Teso South": ["tesosouth"],  # 303 against 308
    },
    "siaya": {
        "Alego Usonga": ["siaya"],  # 599 against 609
        "Bondo": ["bondo"],  # 599 against 1,306, lakeside
        "Gem": ["gem"],  # 405 against 403
        "Rarieda": ["rarieda"],  # 402 against 678, lakeside
        "Ugenya": ["ugenya"],  # 324 against 322
        "Ugunja": ["ugunja"],  # 201 against 198
    },
    "homabay": {
        "Homa Bay": ["homabay"],  # 182 against 269, lakeside
        "Kabondo Kasipul": ["rachuonyoeast"],  # 251 against 247
        "Karachuonyo": ["rachuonyonorth"],  # 435 against 748, lakeside
        "Kasipul": ["rachuonyosouth"],  # 256 against 257
        "Ndhiwa": ["ndhiwa"],  # 713 against 696
        "Rangwe": ["rangwe"],  # 274 against 291
        "Suba North": ["subanorth"],  # 406 against 1,042, lakeside
        "Suba South": ["subasouth"],  # 634 against 1,150, lakeside
    },
    "kakamega": {
        "Butere": ["butere"],  # 210 against 209
        "Ikolomani": ["kakamegasouth"],  # 146 against 145
        "Khwisero": ["khwisero"],  # 146 against 146
        "Lugari": ["lugari", "matete"],  # 357 against 367
        "Malava": ["kakameganorth"],  # 421 against 424
        "Matungu": ["matungu"],  # 276 against 280
        "Navakholo": ["navakholo"],  # 259 against 257
        "Shinyalu": ["kakamegaeast"],  # 417 against 408
    },
    "kiambu": {
        "Githunguri": ["githunguri"],  # 174 against 173
        "Kiambu": ["kiambu"],  # 98 against 100
        "Kikuyu": ["kikuyu"],  # 173 against 174
        "Limuru": ["limuru"],  # 285 against 286
    },
    "baringo": {
        "Baringo North": ["baringonorth"],  # 1,629 against 1,633
        "Eldama Ravine": ["koibatek"],  # 939 against 933
        "Mogotio": ["mogotio"],  # 1,375 against 1,386
    },
    "narok": {
        "Narok East": ["narokeast"],  # 2,042 against 2,046
        "Narok West": ["narokwest"],  # 5,563 against 5,443
        "Kilgoris": ["transmarawest"],  # 2,546 against 2,539
    },
    "bomet": {
        "Bomet East": ["bometeast"],  # 305 against 306
        "Buret": ["kericho/bureti"],  # 321 against 315
    },
    "kericho": {
        "Kipkelion West": ["kipkelion"],  # 350 against 352
        "Sigowet/Soin": ["soinsigowet"],  # 466 against 463
    },
    "embu": {
        "Gachoka": ["mbeeresouth"],  # 1,312 against 1,325
        "Siakago": ["mbeerenorth"],  # 784 against 769
    },
    "nyeri": {
        "Mukurweni": ["mukurweini"],  # 179 against 178
        "Nyeri Town": ["nyericentral"],  # 168 against 170
    },
    "makueni": {
        "Mbooni": ["mboonieast", "mbooniwest"],  # 964 against 979
        "Kilome": ["mukaa"],  # 804 against 823
    },
    "meru": {
        "Tigania West": ["tiganiawest"],  # 399 against 390
    },
    "marsabit": {
        "Moyale": ["moyale", "sololo"],  # 9,391 against 9,370
    },
    "wajir": {
        "Wajir South": ["wajirsouth", "habaswein"],  # 21,646 against 21,580
    },
    "mandera": {
        "Mandera East": ["manderaeast"],  # 2,506 against 2,554
    },
    "turkana": {
        "Turkana East": ["turkanaeast"],  # 11,396 against 11,184
    },
    "nairobi": {
        "Kibra": ["kibra"],  # 12 against 11.6
        "Makadara": ["makadara"],  # 12 against 12.1
        "Mathare": ["mathare"],  # 3 against 3.3
    },
    "samburu": {
        "Samburu East": ["samburueast"],  # 10,016 against 10,060
    },
    "nakuru": {
        "Kuresoi North": ["kuresoinorth"],  # 618 against 612
    },
    "kwale": {
        "Matuga": ["matuga"],  # 1,034 against 1,050
    },
}
# A sub-county the census counts in one county that the map draws inside
# another's polygon: {(county, sub-county): county whose polygon holds it}.
MOVED = {("kericho", "bureti"): "bomet"}


def number(cell: Any) -> int:
    """A count; KNBS writes none as "-" and, in Volume III, as "_"."""
    text = str(cell or "").replace(",", "").strip()
    return int(float(text)) if text not in ("", "-", "_") else 0


def title(name: str) -> str:
    """KNBS writes names in capitals: MUKURWE-INI -> Mukurwe-ini, MURANG'A -> Murang'a."""
    out = re.sub(r"'([A-Z])", lambda m: "'" + m.group(1).lower(), name.strip().title())
    return re.sub(r"-([A-Z][a-z]{0,2})\b", lambda m: "-" + m.group(1).lower(), out)


def read_vol1(text: str) -> dict[str, dict[str, int]]:
    """{county fold: {male, female, intersex, total}} from Volume I's sex table."""
    out: dict[str, dict[str, int]] = {}
    rows = list(csv.reader(io.StringIO(text)))
    start = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() == "name"), None)
    if start is None:
        raise SystemExit("kenya_census: Volume I's table has no 'name' header row")
    for row in rows[start + 1:]:
        if not row or not row[0].strip():
            continue
        male, female, inter, total = (number(c) for c in row[1:5])
        if male + female + inter != total:
            raise SystemExit(f"kenya_census: {row[0]}: its sexes make {male + female + inter:,}, "
                             f"not {total:,}")
        out[fold(row[0])] = {"name": row[0].strip(), "male": male, "female": female,
                             "intersex": inter, "total": total}
    national = out.pop("kenya", None)
    if not national or national["total"] != NATIONAL:
        raise SystemExit(f"kenya_census: Volume I's Kenya row is not {NATIONAL:,}")
    if sum(c["total"] for c in out.values()) != NATIONAL or len(out) != 47:
        raise SystemExit(f"kenya_census: {len(out)} counties making "
                         f"{sum(c['total'] for c in out.values()):,}")
    return out


AGE = re.compile(r"^\d{1,2}$")


def read_vol3(text: str) -> dict[str, dict[str, Any]]:
    """{county fold: {"all": unit, "subs": {sub-county fold: unit}}}, each unit's single
    years, sexes and total checked."""
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip().lower() for h in rows[0]]
    if header[:6] != ["county", "sub-county", "age", "male", "female", "total"]:
        raise SystemExit(f"kenya_census: Volume III's header is {header[:6]}")
    units: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows[1:]:
        if len(row) < 6 or not row[0].strip():
            continue
        # A sub-county name with a comma in it, unquoted, spills into the next
        # column: the last three cells are always the counts and the one
        # before them the age.
        county, age = row[0].strip(), row[-4].strip()
        sub = ",".join(row[1:-4]).strip()
        unit = units.setdefault((county, sub), {"county": county, "name": sub, "ages": {},
                                                "unstated": 0, "total": None, "bad": []})
        # Five-year rows ("0 - 4", "10 -14") repeat the single years and are
        # not read: a spreadsheet turned some of their cells into dates.
        if not (age.lower() in ("total", "not stated") or AGE.match(age)
                or age.replace(" ", "") == "100+"):
            continue
        try:
            male, female, total = (number(c) for c in row[-3:])
        except ValueError:
            # A cell a spreadsheet turned into a date ("15-Aug"): the unit fails
            # its sums below and is left out, never read with the row missing.
            unit["bad"].append(f"age {age}: {row[-3:]}")
            continue
        if male + female != total:
            unit["bad"].append(f"age {age}: sexes make {male + female:,}, not {total:,}")
            continue
        if age.lower() == "total":
            unit.update(total=total, male=male, female=female)
        elif AGE.match(age):
            unit["ages"][int(age)] = total
        elif age.replace(" ", "") == "100+":
            unit["ages"][100] = total
        elif age.lower() == "not stated":
            unit["unstated"] = total
    out: dict[str, dict[str, Any]] = {}
    for (county, sub), unit in units.items():
        made = sum(unit["ages"].values()) + unit["unstated"]
        entry = out.setdefault(fold(county), {"name": county, "all": None, "subs": {},
                                              "unread": []})
        # Kwale's county row's single years fall 12 people short of its
        # 866,802 (its "not stated" row is missing): a gap this small moves no
        # median and is not a misread table, so it is logged and allowed.
        short = (unit["total"] or 0) - made
        if unit["total"] and not unit["bad"] and len(unit["ages"]) == 101 \
                and 0 < short <= max(20, unit["total"] // 10_000):
            entry["unread"].append(f"{sub}: single years {short:,} short of its total; "
                                   "taken as ages not stated")
            unit["unstated"] += short
            made = unit["total"]
        if (unit["bad"] or unit["total"] is None or made != unit["total"]
                or len(unit["ages"]) != 101):
            # Its count still stands where Volume II gives it; its ages do not.
            entry["unread"].append(f"{sub}: {len(unit['ages'])} single years making {made:,} "
                                   f"against {unit['total']}; {unit['bad'][:3]}")
            unit["ages_ok"] = False
        else:
            unit["ages_ok"] = True
        if sub.upper() == "ALL":
            entry["all"] = unit
        else:
            entry["subs"][fold(sub)] = unit
    for key, entry in out.items():
        if entry["all"] is None or entry["all"]["total"] is None:
            raise SystemExit(f"kenya_census: {entry['name']} has no county total")
        made = sum(u["total"] or 0 for u in entry["subs"].values())
        # A county whose sub-county rows do not make it (Kwale's Kinango rows
        # are missing from the CSV) gives no constituency anything.
        entry["subs_ok"] = made == entry["all"]["total"]
        if not entry["subs_ok"]:
            entry["unread"].append(f"its sub-counties make {made:,}, not "
                                   f"{entry['all']['total']:,}: none of them is used")
    return out


def read_vol2(text: str, vol1: dict[str, dict[str, int]], counties: int = 47
              ) -> dict[str, dict[str, dict[str, int]]]:
    """{county key: {sub-county fold: {total, male, female}}} from Volume II's table of
    population by sex and sub-county, whose totals count intersex persons too. A
    county's row is the one with its name and Volume I's total; the rows after it, to
    the next county's, are its sub-counties, and they must make it."""
    rows = list(csv.reader(io.StringIO(text)))
    start = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() == "sub county"),
                 None)
    if start is None:
        raise SystemExit("kenya_census: Volume II's table has no 'Sub County' header row")
    out: dict[str, dict[str, dict[str, int]]] = {}
    current = None
    for row in rows[start + 1:]:
        if len(row) < 4 or not row[0].strip():
            continue
        name = row[0].strip()
        total, male, female = (number(c) for c in row[1:4])
        key = re.sub(r"city$", "", fold(name))
        if key == "kenya":
            continue
        if key in vol1 and total == vol1[key]["total"]:
            current = out.setdefault(key, {})
            continue
        if current is None:
            raise SystemExit(f"kenya_census: Volume II's {name} comes before any county")
        current[fold(name)] = {"name": name, "total": total, "male": male, "female": female}
    for key, subs in out.items():
        made = sum(s["total"] for s in subs.values())
        if made != vol1[key]["total"]:
            raise SystemExit(f"kenya_census: Volume II's sub-counties of {vol1[key]['name']} make "
                             f"{made:,}, not {vol1[key]['total']:,}")
    if len(out) != counties:
        raise SystemExit(f"kenya_census: Volume II gives {len(out)} counties, not {counties}")
    return out


def attach_vol2(vol2: dict[str, dict[str, dict[str, int]]], vol3: dict[str, dict[str, Any]],
                vol1: dict[str, dict[str, int]]) -> None:
    """Give each Volume III sub-county its Volume II count of everyone (``everyone``),
    where the two volumes' men and women agree. Volume III cuts long names short
    ("NYANDARUA CENTRA"), so a name may match the one Volume II name it begins."""
    by_name = {re.sub(r"city$", "", k): v for k, v in vol3.items()}
    for key in vol1:
        entry = vol3.get(key) or by_name.get(key)
        subs2 = vol2.get(key, {})
        for sub, unit in entry["subs"].items():
            hit = subs2.get(sub)
            if hit is None:
                starts = [s for s in subs2 if s.startswith(sub)]
                hit = subs2[starts[0]] if len(starts) == 1 else None
            if hit is None or unit["total"] is None:
                continue
            if (hit["male"], hit["female"]) != (unit["male"], unit["female"]):
                entry["unread"].append(f"{unit['name']}: Volume II has {hit['male']:,} men and "
                                       f"{hit['female']:,} women, Volume III {unit['male']:,} "
                                       f"and {unit['female']:,}")
                continue
            unit["everyone"] = hit["total"]


def median(units: list[dict[str, Any]]) -> float | None:
    """The median of several units' single years added together, ages not stated left out."""
    groups = [(a, a, sum(u["ages"][a] for u in units)) for a in range(100)]
    groups.append((100, None, sum(u["ages"][100] for u in units)))
    return grouped_median(groups)


def age_fields(units: list[dict[str, Any]], of: str) -> dict[str, Any]:
    if not all(u.get("ages_ok") for u in units):
        return {}
    value = median(units)
    if value is None:
        return {}
    unstated = sum(u["unstated"] for u in units)
    return {"median_age": measure(value, unit="years", year=YEAR, source=SOURCE3),
            "median_age_note": (
                "Interpolated within the single year of age that holds the middle person, "
                f"from the 2019 census's count of men and women by single year of age{of}"
                + (f", leaving out the {unstated:,} whose age was not stated." if unstated
                   else "."))}


def less(whole: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    """A unit's single years and sexes with another unit inside it taken out."""
    ages = {a: whole["ages"][a] - part["ages"][a] for a in whole["ages"]}
    out = {"name": f"{whole['name']} less {part['name']}", "ages": ages,
           "unstated": whole["unstated"] - part["unstated"], "total": whole["total"] - part["total"],
           "male": whole["male"] - part["male"], "female": whole["female"] - part["female"],
           "ages_ok": whole.get("ages_ok") and part.get("ages_ok")}
    if min(ages.values()) < 0 or out["unstated"] < 0 or min(out["male"], out["female"]) <= 0:
        raise SystemExit(f"kenya_census: {out['name']}: a count falls below nought")
    return out


def county_records(vol1: dict[str, dict[str, int]], vol3: dict[str, dict[str, Any]],
                   admin1: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    shapes = {fold(s["name"]): s for s in admin1}
    # Volume III writes "NAIROBI CITY" where Volume I writes "Nairobi".
    by_name = {re.sub(r"city$", "", k): v for k, v in vol3.items()}
    tables = {key: vol3.get(key) or by_name.get(key) for key in vol1}
    records, shape_of = [], {}
    for key, row in sorted(vol1.items()):
        label = COUNTY_ALIASES.get(key)
        shape = shapes.get(fold(label)) if label else shapes.get(key)
        ages = tables[key]
        if shape is None or ages is None:
            raise SystemExit(f"kenya_census: county {row['name']}: polygon {bool(shape)}, "
                             f"age table {bool(ages)}")
        if ages["all"]["total"] != row["male"] + row["female"]:
            raise SystemExit(f"kenya_census: {row['name']}: Volume III counts "
                             f"{ages['all']['total']:,}, Volume I {row['male'] + row['female']:,} "
                             "men and women")
        shape_of[shape["id"]] = key
        total, male, female = row["total"], row["male"], row["female"]
        units, of = [ages["all"]], ""
        note = (f"The 2019 census's count of everyone in the county, {row['intersex']:,} "
                "intersex persons included." if row["intersex"] else
                "The 2019 census's count of everyone in the county.")
        for (home, sub), into in MOVED.items():
            part = tables[home]["subs"].get(sub)
            if part is None or part["total"] is None or "everyone" not in part:
                raise SystemExit(f"kenya_census: {home}/{sub}: no such sub-county in both "
                                 "Volumes II and III")
            name, home_name = title(part["name"]), title(vol1[home]["name"])
            if into == key:
                total, male, female = (total + part["everyone"], male + part["male"],
                                       female + part["female"])
                units, of = units + [part], f", of the county and {name} together"
                note = (f"The 2019 census's counts of everyone in {shape['name']} County and in "
                        f"{name} sub-county of {home_name} County, added up: the county is "
                        f"drawn here with {name}'s ground.")
            elif home == key:
                total, male, female = (total - part["everyone"], male - part["male"],
                                       female - part["female"])
                units, of = [less(ages["all"], part)], f", of the county without {name}"
                note = (f"The 2019 census's count of everyone in {shape['name']} County less "
                        f"{name} sub-county, which is drawn here within "
                        f"{title(vol1[into]['name'])} County.")
        moved = total != row["total"]
        records.append(record(
            f"KEN-2019-{shape['id']}", shape["name"], level="admin1", parent="KEN",
            country="KEN", match_by="shape_id", shape_id=shape["id"],
            population=measure(total, year=YEAR, source=SOURCE1),
            population_note=note,
            sex_ratio=measure(round(1000 * male / female),
                              unit="males_per_1000_females", year=YEAR, source=SOURCE1),
            **age_fields(units, of),
            sources=[{"field": "population/sex_ratio", "name": SOURCE1, "url": PAGE,
                      "year": YEAR, "license": LICENCE},
                     *([{"field": "population/sex_ratio", "name": SOURCE2, "url": PAGE,
                         "year": YEAR, "license": LICENCE}] if moved else []),
                     {"field": "median_age", "name": SOURCE3, "url": PAGE, "year": YEAR,
                      "license": LICENCE}]))
        ages["key"] = key
    return records, shape_of


def constituency_plans(vol3: dict[str, dict[str, Any]], admin2: list[dict[str, Any]],
                       shape_of: dict[str, str]
                       ) -> tuple[dict[str, list[tuple[str, str]]], list[str]]:
    """{constituency shape id: [(county key, sub-county fold)]} for the constituencies whose
    census figures are established, and a report of each county's outcome."""
    plans: dict[str, list[tuple[str, str]]] = {}
    report: list[str] = []
    by_key = {e["key"]: e for e in vol3.values() if e.get("key")}
    under: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in admin2:
        under[shape["parent"]].append(shape)
    for parent, shapes in sorted(under.items(), key=lambda kv: shape_of.get(kv[0], "")):
        key = shape_of.get(parent)
        if key is None:
            report.append(f"{len(shapes)} constituencies under no county polygon")
            continue
        entry = by_key[key]
        subs = entry["subs"]
        crosswalk = CROSSWALK.get(key)
        if crosswalk:
            labels = {s["name"].strip(): s for s in shapes}
            if set(crosswalk) - set(labels):
                raise SystemExit(f"kenya_census: {entry['name']}: the crosswalk names "
                                 f"{sorted(set(crosswalk) - set(labels))}, which are not its "
                                 "constituencies")
            for label, refs in crosswalk.items():
                taken = [tuple(ref.split("/")) if "/" in ref else (key, ref) for ref in refs]
                for home, sub in taken:
                    unit = by_key[home]["subs"].get(sub)
                    # A sub-county the crosswalk takes must be read whole, even in a
                    # county whose other rows fall short (Kwale's Kinango).
                    if unit is None or unit["total"] is None or unit["bad"]:
                        raise SystemExit(f"kenya_census: {label}: sub-county {home}/{sub} is "
                                         "not in Volume III whole")
                plans[labels[label]["id"]] = taken
            report.append(f"{entry['name']}: {len(crosswalk)} of {len(shapes)} constituencies "
                          f"from the crosswalk ({sorted(crosswalk)})")
            continue
        if not entry["subs_ok"]:
            report.append(f"{entry['name']}: its sub-county rows do not make it; not written")
            continue
        names = {s["id"]: fold(s["name"]) for s in shapes}
        if all(n in subs for n in names.values()):
            made = sum(subs[n]["total"] for n in names.values())
            if made >= PARTITION * entry["all"]["total"]:
                for sid, n in names.items():
                    plans[sid] = [(key, n)]
                report.append(f"{entry['name']}: {len(shapes)} constituencies are its "
                              f"sub-counties of the same names ({made:,} of "
                              f"{entry['all']['total']:,})")
                continue
        report.append(f"{entry['name']}: {len(shapes)} constituencies, {len(subs)} sub-counties "
                      f"({sorted(subs)}); not written")
    return plans, report


def constituency_records(vol3: dict[str, dict[str, Any]], admin2: list[dict[str, Any]],
                         shape_of: dict[str, str], plans: dict[str, list[tuple[str, str]]]
                         ) -> list[dict[str, Any]]:
    by_key = {e["key"]: e for e in vol3.values() if e.get("key")}
    records = []
    for shape in admin2:
        key = shape_of.get(shape["parent"])
        if key is None:
            continue
        composition = {field: gap(NOT_AVAILABLE, COMPOSITION)
                       for field in ("religion", "language", "ethnicity")}
        unpublished = {"field": "religion/language/ethnicity", "name": SOURCE4, "url": PAGE,
                       "year": YEAR, "license": LICENCE}
        taken = plans.get(shape["id"])
        if not taken:
            why = ("The 2019 census was published for sub-counties, and this constituency's "
                   "ground cannot be shown to be one sub-county or a set of whole ones, so no "
                   "census count is given for it.")
            stated = gap(NOT_AVAILABLE, why)
            records.append(record(f"KEN-2019-{shape['id']}", shape["name"], level="admin2",
                                  parent="KEN", country="KEN", match_by="shape_id",
                                  shape_id=shape["id"], population=stated, median_age=stated,
                                  sex_ratio=stated, **composition,
                                  sources=[{"field": "population/median_age/sex_ratio",
                                            "name": SOURCE2, "url": PAGE, "year": YEAR,
                                            "license": LICENCE}, unpublished]))
            continue
        units = [by_key[home]["subs"][sub] for home, sub in taken]
        if any("everyone" not in u for u in units):
            raise SystemExit(f"kenya_census: {shape['name']}: a sub-county of {taken} has no "
                             "Volume II count agreeing with Volume III")
        total = sum(u["everyone"] for u in units)
        male, female = sum(u["male"] for u in units), sum(u["female"] for u in units)
        names = [title(u["name"]) for u in units]
        if len(units) == 1:
            home = taken[0][0]
            where = (f" of {title(by_key[home]['name'])} County" if home != key else "")
            same = fold(names[0]) == fold(shape["name"])
            note = (f"The 2019 census's count for {names[0]} sub-county{where}"
                    + ("." if same and not where else ", which is this constituency's ground."))
            of = ""
        else:
            note = ("The 2019 census's counts for the sub-counties of "
                    + ", ".join(names[:-1]) + " and " + names[-1]
                    + ", added up: the constituency is the sub-counties together.")
            of = ", of its sub-counties together"
        records.append(record(
            f"KEN-2019-{shape['id']}", shape["name"], level="admin2", parent="KEN",
            country="KEN", match_by="shape_id", shape_id=shape["id"],
            population=measure(total, year=YEAR, source=SOURCE2), population_note=note,
            sex_ratio=measure(round(1000 * male / female), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE2),
            **age_fields(units, of), **composition,
            sources=[{"field": "population/sex_ratio", "name": SOURCE2, "url": PAGE,
                      "year": YEAR, "license": LICENCE},
                     {"field": "median_age", "name": SOURCE3, "url": PAGE, "year": YEAR,
                      "license": LICENCE}, unpublished]))
    return records


def fetch(url: str) -> str:
    body = http_get(url, cache=False, timeout=300)
    text = body if isinstance(body, str) else body.decode("utf-8-sig", "replace")
    log(f"  read {url}: {len(text):,} characters, sha256 "
        f"{hashlib.sha256(text.encode()).hexdigest()}")
    return text.lstrip("﻿")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", action="store_true",
                    help="write points sampled over OCHA's sub-county outlines, for CROSSWALK")
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    if args.points:
        from .uganda_census import write_cod_points  # noqa: PLC0415
        return write_cod_points(COD_AB, 2, POINTS)
    vol1 = read_vol1(fetch(VOL1))
    vol3 = read_vol3(fetch(VOL3))
    vol2 = read_vol2(fetch(VOL2), vol1)
    attach_vol2(vol2, vol3, vol1)
    log(f"  Volume I: 47 counties making {NATIONAL:,}; Volume II: "
        f"{sum(len(s) for s in vol2.values())} sub-counties making their counties; Volume III: "
        f"{len(vol3)} counties and {sum(len(e['subs']) for e in vol3.values())} sub-counties, "
        f"{sum(1 for e in vol3.values() for u in e['subs'].values() if 'everyone' in u)} of them "
        "agreeing with Volume II's men and women")
    for entry in vol3.values():
        for line in entry["unread"]:
            log(f"  ages not read for {entry['name']}, {line}")
    admin1 = json.loads((SITE / "admin1" / "KEN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "KEN.units.json").read_text())
    records, shape_of = county_records(vol1, vol3, admin1)
    plans, report = constituency_plans(vol3, admin2, shape_of)
    for line in report:
        log("  " + line)
    records += constituency_records(vol3, admin2, shape_of, plans)
    written = [r for r in records if r["level"] == "admin2" and "value" in r["population"]]
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} counties and {len(written)} of "
        f"{len(admin2)} constituencies with figures")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
