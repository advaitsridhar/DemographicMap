#!/usr/bin/env python3
"""New Zealand -- Census 2023 ethnicity, religion, languages, age and sex, by TA.

Stats NZ asks all of them, and publishes them through Aotearoa Data Explorer's
SDMX API. Three dataflows carry what this map wants, all broken down by the
geography geoBoundaries happens to use for New Zealand:

    CEN23_ECI_017   religious affiliation x ethnicity x gender
    CEN23_ECI_011   languages spoken x ethnicity x gender
    CEN23_POP_006   ethnicity x age x sex at birth, whose age list carries
                    Stats NZ's own median ("Median - age") beside the counts

**Median age and sex ratio** are the 2023 Census's: the median is the one
Stats NZ publishes for exactly each region, territorial authority and local
board (age code ``Median``), and the sex ratio is males per 100 females by sex
at birth, from the same table's totals. The national median must read the
published 38.1 years.

**The Chatham Islands** are drawn as a first-level unit of their own. Stats
NZ's regional-council tier has no such region: it files the territory under
"Area Outside Region" (code 99), 633 people, together with 21 people of other
outlying islands the map does not draw there. The territorial authority
(code 067, 612 people) is exactly the Chatham Islands Territory, so its
figures are written for the first-level polygon as well as the second.

**The API needs a key.** Only the bare dataflow catalogue is open; every
``/data/``, ``/datastructure/`` and ``?references=`` request is 401 without
one, because the Explorer's public member is captcha-gated. The key is read
from the environment (see ``KEY_VARS``) and sent as an Azure API Management
subscription header. It is never written to a file, a log or a command line.

**The geography is the one CGAZ has.** Stats NZ publishes census tables at
"territorial authority and Auckland local board area" -- 67 territorial
authorities with Auckland replaced by its 21 local boards -- and that is
exactly the 88-shape admin-2 layer geoBoundaries ships for New Zealand. No
other country in this project has lined up that neatly.

**Two things about the counts.** Ethnicity and languages are multi-response:
a person may name several, so the parts sum to more than the whole and the
shares are of responses rather than of people. And Stats NZ applies random
rounding to base 3 and suppresses small cells, which arrives as an
``OBS_STATUS`` of ``c`` (confidential) or ``_U`` (unavailable) rather than as
a zero -- a suppressed cell is a gap, not an absence.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
)
from .oceania_common import withhold_small

BASE = "https://api.data.stats.govt.nz/rest"
AGENCY = "STATSNZ"
YEAR = 2023
SOURCE = "Stats NZ, 2023 Census (Aotearoa Data Explorer)"
LICENSE = ("Creative Commons Attribution 4.0 International, "
           "as published by Stats NZ")
TIMEOUT = 180

# Environment variables that might carry the key, in the order they are tried.
KEY_VARS = ("NZ_STATS_API", "STATS_NZ_API_KEY", "STATSNZ_API_KEY",
            "STATS_NZ_KEY", "STATSNZ_KEY", "NZ_STATS_API_KEY")

# Stats NZ sits behind Azure API Management.
KEY_HEADER = "Ocp-Apim-Subscription-Key"

# SDMX-CSV rather than the XML: one header row naming the dimensions, then one
# row per observation, which is all this needs.
CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"
XML_ACCEPT = "application/vnd.sdmx.structure+xml;version=2.1"

FLOWS = {
    "religion": "CEN23_ECI_017",
    "language": "CEN23_ECI_011",
    "age": "CEN23_POP_006",
}
# Every area, all ethnicities together, the median and the all-ages total,
# for both sexes at birth and their sum.
AGE_SELECTION = "2023..999.Median+99.999+11+22"
MEDIAN_CODE, ALL_AGES = "Median", "99"
SEX_AT_BIRTH = {"999": "total", "11": "male", "22": "female"}
# The Chatham Islands Territory: its territorial authority, and the
# regional-council code Stats NZ files it under with other outlying islands.
CHATHAM_TA, OUTSIDE_REGION = "067", "99"

# Said beside a small area's men and women, which need not make its total.
ROUNDING = ("Stats NZ randomly rounds every count to base 3, so the men and the women need not "
            "add up to the total")

# A suppressed or unavailable cell is not a zero. Stats NZ randomly rounds
# every count to base 3 and withholds cells too small to publish; reading
# either as an absence would turn "we will not say" into "nobody".
SUPPRESSED = {"c", "_U", "..", "C"}


def api_key() -> str:
    for name in KEY_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            log(f"  key from {name} ({len(value)} characters)")
            return value
    raise SystemExit(
        "No Stats NZ API key in the environment. Aotearoa Data Explorer "
        "refuses every data request without one.\n"
        f"Set one of: {', '.join(KEY_VARS)}\n"
        "In CI it comes from a repository secret passed through the "
        "workflow's env block, never on a command line.")


def fetch(path: str, *, accept: str, key: str) -> str:
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "Accept-Encoding": "identity",
        "User-Agent": "DemographicMap/1.0 (+https://github.com/"
                      "advaitsridhar/DemographicMap)",
        KEY_HEADER: key,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")[:300]
        # The URL is safe to print; the key is a header and never in it.
        raise SystemExit(f"{url}\n  HTTP {err.code}: {body}") from err


def structure(flow: str, key: str) -> str:
    """The dataflow with every codelist it references."""
    return fetch(f"dataflow/{AGENCY}/{flow}/1.0?references=all",
                 accept=XML_ACCEPT, key=key)


def observations(flow: str, selection: str, key: str) -> list[dict[str, str]]:
    """One SDMX query, as rows keyed by the dimension ids in the header."""
    text = fetch(f"data/{AGENCY},{flow},1.0/{selection}",
                 accept=CSV_ACCEPT, key=key)
    rows = list(csv.DictReader(io.StringIO(text)))
    log(f"  {flow} [{selection}]: {len(rows):,} observations")
    return rows


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------

_CODELIST = re.compile(
    r'<structure:Codelist[^>]*\bid="(?P<id>[^"]+)"[^>]*>(?P<body>.*?)'
    r"</structure:Codelist>", re.S)
_CODE = re.compile(
    r'<structure:Code[^>]*\bid="(?P<id>[^"]+)"[^>]*>(?P<body>.*?)'
    r"</structure:Code>", re.S)
_NAME = re.compile(r"<common:Name[^>]*>(.*?)</common:Name>", re.S)


def codelist(xml: str, list_id: str) -> dict[str, str]:
    """{code: label} for one codelist inside a structure message."""
    for match in _CODELIST.finditer(xml):
        if match.group("id") != list_id:
            continue
        out = {}
        for code in _CODE.finditer(match.group("body")):
            name = _NAME.search(code.group("body"))
            out[code.group("id")] = (
                re.sub(r"\s+", " ", name.group(1)).strip() if name else code.group("id"))
        return out
    raise SystemExit(f"codelist {list_id} is not in the structure message")


# Totals and subtotals in a group dimension, which are never groups in a
# composition. "999" is also the code for Area Outside Territorial Authority,
# but that is a different dimension and never read from this set.
TOTALS = {"999", "9999", "777", "7777"}

# The three tier totals in the area dimension. The national figures are read
# from these, and they are the only areas kept that are not a tier member.
AREA_TOTALS = {"9999", "999999", "99999"}

# Ethnicity is hierarchical: 1 European is the parent of 111 New Zealand
# European, 122 Dutch and the rest, and both levels sit in one codelist. Only
# the six level-1 codes are read, plus the residual, because summing the column
# would count most of the country twice -- the same trap as India's mother
# tongue groups and the ABS "Christianity Total" row.
ETHNICITY_LEVEL_1 = {"1", "2", "3", "4", "5", "6", "9"}


# The codelist holds every geography Stats NZ publishes this table for, all in
# one flat list, and the widths overlap in ways that matter: "076" is Auckland
# the territorial authority and "102" is Auckland the Te Whatu Ora health
# district, both three digits and identically named. Reading the tiers off the
# code width would have put twenty health districts on the map as territorial
# authorities and made "Auckland" ambiguous.
#
# The file says so itself. Every code carries a Parent, and the three tier
# totals are distinct, so the tier a code belongs to is read rather than
# inferred.
TIER_REGION = "9999"        # Total - New Zealand by regional council
TIER_TALB = "999999"        # ... by territorial authority and Auckland local board
TIER_HEALTH = "99999"       # ... by health region/health district

_PARENT = re.compile(r'<structure:Parent>\s*<Ref id="([^"]+)"')


def levels(xml: str) -> dict[str, str]:
    """{area code: "admin1" | "admin2"}, from the codelist's own parent links.

    Regional councils hang off the regional-council total, territorial
    authorities and Auckland local boards off theirs. Anything below those --
    statistical areas, whose parent is a territorial authority -- and anything
    under the health total is left out.
    """
    for match in _CODELIST.finditer(xml):
        if match.group("id") != "CL_CEN23_GEO_002":
            continue
        out: dict[str, str] = {}
        for code in _CODE.finditer(match.group("body")):
            parent = _PARENT.search(code.group("body"))
            if not parent:
                continue
            if parent.group(1) == TIER_REGION:
                out[code.group("id")] = "admin1"
            elif parent.group(1) == TIER_TALB:
                out[code.group("id")] = "admin2"
        return out
    raise SystemExit("the area codelist is not in the structure message")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

# Spellings the boundary file uses for an area Stats NZ names otherwise. Only
# one differs, and it is the well-known one: the region took the "Whanganui"
# spelling in 2015 and CGAZ still carries "Wanganui", which normalisation
# cannot bridge because the h is a letter rather than an accent.
ALIASES = {
    "Manawatū-Whanganui Region": ("Manawatu-Wanganui Region",
                                  "Manawatu-Whanganui Region",
                                  "Manawatū-Wanganui Region"),
}

FIELD_NOTES = {
    "ethnicity": (
        "Total response ethnicity: a person may report more than one, so the "
        "parts sum to about 115% of the population and each share is the "
        "percentage of people who named that group, not a slice of a whole. "
        "The six groups shown are Stats NZ's level-1 classification; the "
        "detailed groups beneath them are not added, because that would count "
        "most people twice."),
    "language": (
        "Languages a person can hold an everyday conversation in. Multi"
        "-response -- the parts sum to about 125% of the population -- so each "
        "share is the percentage of people who speak that language, not a "
        "slice of a whole."),
    "religion": (
        "Religious affiliation is also multi-response in New Zealand, though "
        "only slightly: the parts sum to about 100.3%. \"Object to answering\" "
        "is kept as its own category rather than folded into a non-response "
        "bucket, because Stats NZ counts it inside \"total stated\" -- it is an "
        "answer people gave, not a question they skipped."),
}

# Published national figures, used as an independent control. Every one of
# these is printed in Stats NZ's own 2023 Census release; agreement means the
# right slice of the right dataflow was read, which a self-consistent set of
# shares could never establish on its own.
NATIONAL = {
    "population": 4_993_923,
    "median_age": 38.1,
    "ethnicity": {"European": 3_383_742, "Māori": 887_493,
                  "Asian": 861_576, "Pacific Peoples": 442_632},
    "religion": {"No religion": 2_576_049, "Catholicism": 449_466,
                 "Hinduism": 144_753, "Islam": 75_138},
    "language": {"English": 4_750_056, "Māori": 213_849, "Samoan": 110_541},
}
TOLERANCE = 0.001


def compositions(rows: list[dict[str, str]], dimension: str,
                 labels: dict[str, str], tiers: dict[str, str], *,
                 keep: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """{area code: {"total": n, "counts": {label: n}, "suppressed": [label]}}.

    A suppressed cell is not a zero. Stats NZ randomly rounds every count to
    base 3 and withholds cells too small to publish; the withheld groups are
    named rather than dropped silently, so a composition that is missing a
    group says why.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        area = row["CEN23_GEO_002"]
        if area not in tiers and area not in AREA_TOTALS:
            continue
        code = row[dimension]
        entry = out.setdefault(area, {"total": None, "counts": {},
                                      "suppressed": []})
        raw = (row.get("OBS_VALUE") or "").strip()
        status = (row.get("OBS_STATUS") or "").strip()
        if code in TOTALS:
            if code in {"999", "9999"} and raw:
                entry["total"] = int(raw)
            continue
        if keep is not None and code not in keep:
            continue
        label = labels.get(code, code)
        if not raw:
            if status in SUPPRESSED:
                entry["suppressed"].append(label)
            continue
        entry["counts"][label] = int(raw)
    return out


def check_national(field: str, built: dict[str, dict[str, Any]]) -> None:
    nation = built.get("999999") or built.get("9999")
    if not nation:
        raise SystemExit(f"{field}: no national row to check against")
    total = nation.get("total")
    if total is None or abs(total - NATIONAL["population"]) > 1:
        raise SystemExit(
            f"{field}: national population reads {total}, published is "
            f"{NATIONAL['population']:,}; this is not the slice the adapter "
            "was written against")
    for label, published in NATIONAL[field].items():
        got = nation["counts"].get(label)
        if got is None:
            raise SystemExit(f"{field}: no national figure for {label!r}; "
                             f"read {len(nation['counts'])} groups")
        drift = abs(got - published) / published
        log(f"  {field} {label}: {got:,} vs published {published:,} ({drift:.4%})")
        if drift > TOLERANCE:
            raise SystemExit(f"{field}: {label} is {drift:.2%} from the "
                             "published figure")


def age_sex(rows: list[dict[str, str]], tiers: dict[str, str]
            ) -> dict[str, dict[str, float]]:
    """{area: {"median", "total", "male", "female"}} from CEN23_POP_006.

    The median is Stats NZ's own, for exactly the area; the counts are the
    all-ages totals by sex at birth. A suppressed or missing cell leaves its
    key out, and the caller writes only what is there.
    """
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        area = row["CEN23_GEO_002"]
        if area not in tiers and area not in AREA_TOTALS:
            continue
        if row.get("CEN23_ETH_002") != "999":
            continue
        raw = (row.get("OBS_VALUE") or "").strip()
        if not raw:
            continue
        age, sex = row.get("CEN23_AGE_001"), SEX_AT_BIRTH.get(row.get("CEN23_SAB_002", ""))
        entry = out.setdefault(area, {})
        if age == MEDIAN_CODE and sex == "total":
            entry["median"] = float(raw)
        elif age == ALL_AGES and sex:
            entry[sex] = int(raw)
    for area, entry in out.items():
        if {"male", "female", "total"} <= set(entry):
            # Random rounding to base 3 moves each of the three cells by up
            # to two people on its own.
            slack = max(6, 0.001 * entry["total"])
            if abs(entry["male"] + entry["female"] - entry["total"]) > slack:
                raise SystemExit(
                    f"age: area {area}: males {entry['male']:,} and females "
                    f"{entry['female']:,} do not make {entry['total']:,}")
    return out


def check_ages(by_area: dict[str, dict[str, float]]) -> None:
    nation = by_area.get("999999") or by_area.get("9999")
    if not nation:
        raise SystemExit("age: no national row to check against")
    if nation.get("total") != NATIONAL["population"]:
        raise SystemExit(f"age: national population reads {nation.get('total')}, "
                         f"published is {NATIONAL['population']:,}")
    if nation.get("median") != NATIONAL["median_age"]:
        raise SystemExit(f"age: national median age reads {nation.get('median')}, "
                         f"published is {NATIONAL['median_age']}")
    log(f"  age: national median {nation['median']}, {nation['male']:,} males and "
        f"{nation['female']:,} females by sex at birth")


def age_fields(entry: dict[str, float] | None) -> dict[str, Any]:
    """The median age and sex ratio fields for one area, where both counts exist."""
    if not entry:
        return {}
    fields: dict[str, Any] = {}
    if entry.get("median") is not None:
        fields["median_age"] = measure(entry["median"], unit="years", year=YEAR,
                                       source=SOURCE)
        fields["median_age_note"] = (
            "Stats NZ's own median age for this area, 2023 Census usually resident "
            "population count (CEN23_POP_006).")
    if entry.get("male") and entry.get("female"):
        fields["sex_ratio"] = measure(round(100.0 * entry["male"] / entry["female"], 1),
                                      unit="males_per_100_females", year=YEAR,
                                      source=SOURCE)
        fields["sex_ratio_note"] = (
            f"Males per 100 females by sex at birth: {entry['male']:,} males and "
            f"{entry['female']:,} females in the 2023 Census usually resident population "
            "count (CEN23_POP_006). Stats NZ randomly rounds every count to base 3.")
    return fields


def chatham_region(admin2: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The Chatham Islands Territory's own figures, for its first-level polygon."""
    territory = next((r for r in admin2 if (r.get("codes") or {}).get("statsnz") == CHATHAM_TA),
                     None)
    if territory is None:
        return None
    region = json.loads(json.dumps(territory))
    region.update(id=f"NZL-{CHATHAM_TA}-region", level="admin1", parent="NZL",
                  codes={"statsnz": CHATHAM_TA})
    why = (" These are the Chatham Islands Territory's own figures (territorial "
           "authority 067): Stats NZ's regional-council tier files the territory under "
           "'Area Outside Region' together with 21 people of other outlying islands the "
           "map does not draw here.")
    for field in ("religion", "ethnicity", "language", "median_age", "sex_ratio"):
        if f"{field}_note" in region:
            region[f"{field}_note"] += why
    return region


def build(key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    religion_xml = structure(FLOWS["religion"], key)
    language_xml = structure(FLOWS["language"], key)
    areas = codelist(religion_xml, "CL_CEN23_GEO_002")
    labels = {
        "religion": codelist(religion_xml, "CL_CEN23_REA_003"),
        "ethnicity": codelist(religion_xml, "CL_CEN23_ETH_003"),
        "language": codelist(language_xml, "CL_CEN23_LAN_001"),
    }

    tiers = levels(religion_xml)
    log(f"  {sum(1 for v in tiers.values() if v == 'admin1')} regional councils, "
        f"{sum(1 for v in tiers.values() if v == 'admin2')} territorial "
        "authorities and local boards")

    built = {
        "religion": compositions(
            observations(FLOWS["religion"], "2023...9999.99", key),
            "CEN23_REA_003", labels["religion"], tiers),
        "ethnicity": compositions(
            observations(FLOWS["religion"], "2023..999..99", key),
            "CEN23_ETH_003", labels["ethnicity"], tiers,
            keep=ETHNICITY_LEVEL_1),
        "language": compositions(
            observations(FLOWS["language"], "2023...9999.99", key),
            "CEN23_LAN_001", labels["language"], tiers),
    }
    for field in built:
        check_national(field, built[field])
    ages = age_sex(observations(FLOWS["age"], AGE_SELECTION, key), tiers)
    check_ages(ages)

    admin1: list[dict[str, Any]] = []
    admin2: list[dict[str, Any]] = []
    for code, name in sorted(areas.items()):
        level = tiers.get(code)
        if level is None:
            continue
        fields: dict[str, Any] = {}
        population = None
        for field, by_area in built.items():
            entry = by_area.get(code)
            if not entry or not entry["counts"] or not entry["total"]:
                continue
            population = population or entry["total"]
            fields[field] = shares(entry["counts"], total=entry["total"])
            fields[f"{field}_year"] = YEAR
            note = FIELD_NOTES[field]
            if entry["suppressed"]:
                note += (" Stats NZ withheld " +
                         ", ".join(sorted(entry["suppressed"])) +
                         " here as too small to publish; withheld is not zero.")
            fields[f"{field}_note"] = note
        fields.update(age_fields(ages.get(code)))
        if not fields:
            continue
        population = population or (ages.get(code) or {}).get("total")
        # The Area Outside Territorial Authority -- the outlying islands, 72
        # people -- is the one area with too few to carry a ratio or a share.
        if population:
            fields = withhold_small(fields, population, (ages.get(code) or {}).get("male"),
                                    (ages.get(code) or {}).get("female"), counting=ROUNDING)
        record_ = record(
            f"NZL-{code}", name,
            aliases=list(ALIASES.get(name, ())) or None,
            level=level, parent="NZL" if level == "admin1" else None,
            country="NZL",
            population=(measure(population, year=YEAR, source=SOURCE)
                        if population else gap(NOT_AVAILABLE)),
            codes={"statsnz": code},
            sources=[{"field": "ethnicity/language/religion/median_age/sex_ratio",
                      "name": SOURCE, "url": "https://explore.data.stats.govt.nz/",
                      "license": LICENSE}],
            **fields,
        )
        (admin1 if level == "admin1" else admin2).append(record_)
    # "Area Outside Region" is not a polygon the map draws; the Chatham
    # Islands Territory is, and takes its territorial authority's figures.
    admin1 = [r for r in admin1 if r["codes"]["statsnz"] != OUTSIDE_REGION]
    chatham = chatham_region(admin2)
    if chatham is None:
        raise SystemExit("no territorial-authority record for the Chatham Islands (067)")
    admin1.append(chatham)
    return admin1, admin2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump-structure", choices=sorted(FLOWS),
                    help="write the dataflow's codelists somewhere readable "
                         "and stop; this is how the codes above were found")
    ap.add_argument("--dump-data", choices=sorted(FLOWS),
                    help="write one query's rows and stop")
    ap.add_argument("--selection", default="all",
                    help="SDMX key, dimensions dot-separated in order")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    key = api_key()

    if args.dump_structure:
        flow = FLOWS[args.dump_structure]
        text = structure(flow, key)
        out = args.out or (PROCESSED / f"nz-{flow}-structure.xml")
        out.write_text(text, encoding="utf-8")
        log(f"  wrote {out} ({len(text):,} bytes)")
        return 0

    if args.dump_data:
        flow = FLOWS[args.dump_data]
        text = fetch(f"data/{AGENCY},{flow},1.0/{args.selection}",
                     accept=CSV_ACCEPT, key=key)
        out = args.out or (PROCESSED / f"nz-{flow}-data.csv")
        out.write_text(text, encoding="utf-8")
        log(f"  wrote {out} ({len(text):,} bytes)")
        return 0

    admin1, admin2 = build(key)
    write_json(PROCESSED / "nz_region.json", admin1)
    write_json(PROCESSED / "nz_territorial.json", admin2)
    log(f"  {len(admin1)} regions, {len(admin2)} territorial authorities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
