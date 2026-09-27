#!/usr/bin/env python3
"""European Social Survey: religion and home language by region, rounds 5-11.

Most of Western and Northern Europe does not ask religion or home language in
its census -- France, Spain, Belgium, Austria, Sweden, Greece and more carry a
``not_collected`` policy for one or both -- and the map's first-level units
there have had nothing. The European Social Survey asks both of about 1,500 to
3,000 adults (15 and over) in each country every second year, and it records
the NUTS region every respondent lives in. Pooled over several rounds, a
region holds hundreds of respondents: enough for a composition with a stated
precision, and the only regional figure that exists for most of these units.

**Where the figures come from.** The microdata sit behind the ESS Data
Portal's registration, which this project does not have and does not get
around. What the portal serves openly, with no account, is its own
tabulation service -- the GraphQL endpoint (``api.nsd.no/graphql``) behind
the portal's variable viewer, which returns weighted and unweighted
frequency tables. This reader asks it for the tables it needs and nothing
else: religious belonging and denomination, and the language most often
spoken at home, each split by region with the service's own ``byVariables``
option (the one the viewer uses to split by country). No microdata are read
or stored; the tables are aggregates, and they are kept in
``data/raw/ess/ess_region_tabs.json.gz`` so the build can be re-run and
checked without the network.

**The questions.** ``rlgblg`` "Do you consider yourself as belonging to any
particular religion or denomination?" and, if yes, ``rlgdnm`` "Which one?"
(Roman Catholic, Protestant, Eastern Orthodox, other Christian, Jewish,
Islamic, Eastern religions, other non-Christian). "No" is written as "No
religion": it is an answer. Refusals, don't-knows and no-answers are left out
of the base and counted in the note. ``lnghom1`` "What language or languages
do you speak most often at home? (first mentioned)", coded to ISO 639-2; the
respondent names up to two and only the first is read. The universe is the
resident population aged 15 and over living in private households; people
who cannot take the interview in one of the country's survey languages are
not in it, which undercounts recent immigrants' languages.

**Weights and pooling.** Every table is weighted by ``pspwght``, the
post-stratification weight including the design weight, which the ESS
prescribes for analyses within one country; the service returns the weighted
counts rounded to whole respondents. Within a region, each round's weighted
counts are rescaled to that round's respondents there before the rounds are
added, so the weights correct who was sampled inside a round and each round
counts in proportion to its interviews -- a round whose weights are on
another scale by region (ESS10 in Norway) cannot outweigh the rest. The
default pool is rounds 7 to 11 (fieldwork 2014-2024); a unit those rounds
leave under ``MIN_N`` = 100 respondents with a valid answer, unweighted, is
pooled from round 5 (2010) instead, and its note says so. 100-299 is marked
low precision in the note.

**Geography.** Respondents carry a NUTS code, at NUTS 1, 2 or 3 depending on
the country and round. Codes from older NUTS versions are mapped to NUTS 2024
only where the older region is exactly a newer one or exactly a union of them
(``OLD_CODES``: France's 2016 merger of its 22 regions into 13, Greece's 2016
recoding, Italy's 2010 recoding, the Netherlands' 2021 recoding). A NUTS code
is aggregated to its NUTS parents -- the hierarchy is exact within one
version -- so a country coded at NUTS 2 also gives NUTS 1 estimates. A region
is then bound to a polygon only if ``data/processed/nuts_crosswalk.json``
places it there by outline (following ``superseded_by`` to the finer code of
the same outline); a region the crosswalk refuses or does not place is left
out and logged. A region's estimate is never copied onto its members.

**Licence.** ESS data are published under CC BY-NC-SA 4.0 by ESS ERIC; the
source line cites the rounds with that licence.

Usage:
    python -m scripts.fetch_census.ess_region --fetch      # tables from the portal, then build
    python -m scripts.fetch_census.ess_region              # build from the stored tables
    python -m scripts.fetch_census.ess_region --discover FR,ES
    python -m scripts.fetch_census.ess_region --by ESS11 rlgblg region pspwght 30
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from ._shared import PROCESSED, RAW, log, read_json, record, shares, write_json
from common import USER_AGENT  # noqa: E402  (on the path through _shared)

API = "https://api.nsd.no/graphql"
PORTAL = "https://ess.sikt.no/en/series/321b06ad-1b98-4b7d-93ad-ca8a24e8788a"
SERIES = "321b06ad-1b98-4b7d-93ad-ca8a24e8788a"
AGENCY = "INT_ESSERIC"
HERE = RAW / "ess"
TABS = HERE / "ess_region_tabs.json.gz"
NATIONAL = HERE / "ess_national.json"
CROSSWALK = PROCESSED / "nuts_crosswalk.json"
OUT = "ess_region_survey.json"
WEIGHT = "pspwght"
LICENCE = "CC BY-NC-SA 4.0 (ESS ERIC)"

MIN_N = 100
LOW_PRECISION = 300
# A home language named by fewer respondents than this in a unit is folded
# into "Other languages": one interview is half a point in a unit of 200.
MIN_LANGUAGE_N = 5

# The rounds read, by the label prefix of their integrated file on the portal,
# with the year the round is named for and its fieldwork years. ESS10 was
# fielded in two files: face to face, and self-completion where the pandemic
# stopped interviewing (Austria, Germany, Spain, Latvia, Poland, Sweden ...).
ROUNDS: dict[str, tuple[int, int, str]] = {
    "ESS5": (5, 2010, "2010-2011"),
    "ESS6": (6, 2012, "2012-2013"),
    "ESS7": (7, 2014, "2014-2015"),
    "ESS8": (8, 2016, "2016-2017"),
    "ESS9": (9, 2018, "2018-2019"),
    "ESS10": (10, 2020, "2020-2022"),
    "ESS10SC": (10, 2021, "2021-2022"),
    "ESS11": (11, 2023, "2023-2024"),
}
FIRST_ROUND = 7

# rlgdnm: the denomination of those who belong (rlgblg = 1).
DENOMINATIONS = {
    "1": "Roman Catholic", "2": "Protestant", "3": "Orthodox",
    "4": "Other Christian", "5": "Judaism", "6": "Islam",
    "7": "Eastern religions", "8": "Other religions",
}

# lnghom1, ISO 639-2 (bibliographic) as the ESS codes it, in the map's words.
# A code whose ISO name is a historical stage of a living language is a
# coder's slip for the living one (French, Middle for French); a code that
# cannot be what a resident of Europe speaks at home (Apache, Egyptian
# (Ancient)) is not guessed at and goes to "Other languages" with the codes
# not listed here, and every one of them is logged.
LANGUAGES: dict[str, str] = {
    "ALB": "Albanian", "AMH": "Amharic", "ARA": "Arabic", "ARC": "Aramaic",
    "ARG": "Aragonese", "ARM": "Armenian", "AST": "Asturian", "AZE": "Azerbaijani",
    "BAQ": "Basque", "BAM": "Bambara", "BEL": "Belarusian", "BEN": "Bengali",
    "BER": "Berber", "BOS": "Bosnian", "BRE": "Breton", "BUL": "Bulgarian",
    "CAT": "Catalan", "CHE": "Chechen", "CHI": "Chinese", "COS": "Corsican",
    "CPF": "Creole", "CPP": "Creole", "CRP": "Creole", "CZE": "Czech",
    "DAN": "Danish", "DUT": "Dutch", "ENG": "English", "ENM": "English",
    "EST": "Estonian", "FAO": "Faroese", "FIL": "Filipino", "FIN": "Finnish",
    "FRE": "French", "FRM": "French", "FRO": "French", "FRR": "Frisian",
    "FRS": "Frisian", "FRY": "Frisian", "FUL": "Fula", "FUR": "Friulian",
    "GEO": "Georgian", "GER": "German", "GLA": "Scottish Gaelic", "GLE": "Irish",
    "GLG": "Galician", "GRE": "Greek", "GSW": "Swiss German", "HEB": "Hebrew",
    "HIN": "Hindi", "HRV": "Croatian", "HUN": "Hungarian", "IBO": "Igbo",
    "ICE": "Icelandic", "IND": "Indonesian", "ITA": "Italian", "JPN": "Japanese",
    "KAB": "Kabyle", "KIN": "Kinyarwanda", "KOR": "Korean", "KUR": "Kurdish",
    "LAD": "Ladino", "LAV": "Latvian", "LIM": "Limburgish", "LIN": "Lingala",
    "LIT": "Lithuanian", "LTZ": "Luxembourgish", "MAC": "Macedonian", "MAY": "Malay",
    "MLT": "Maltese", "NAP": "Neapolitan", "NDS": "Low German", "NEP": "Nepali",
    "NNO": "Norwegian", "NOB": "Norwegian", "NOR": "Norwegian", "OCI": "Occitan",
    "PAN": "Punjabi", "PAP": "Papiamento", "PER": "Persian", "POL": "Polish",
    "POR": "Portuguese", "PRO": "Occitan", "PUS": "Pashto", "ROH": "Romansh",
    "ROM": "Romani", "RUM": "Romanian", "RUP": "Aromanian", "RUS": "Russian",
    "SCN": "Sicilian", "SCO": "Scots", "SCR": "Croatian", "SCC": "Serbian",
    "SIN": "Sinhala", "SLO": "Slovak", "SLV": "Slovene", "SMA": "Sami",
    "SME": "Sami", "SMI": "Sami", "SOM": "Somali", "SPA": "Spanish",
    "SRD": "Sardinian", "SRP": "Serbian", "SWA": "Swahili", "SWE": "Swedish",
    "SYR": "Syriac", "TAM": "Tamil", "TGL": "Tagalog", "THA": "Thai",
    "TIR": "Tigrinya", "TUR": "Turkish", "TWI": "Twi", "UKR": "Ukrainian",
    "URD": "Urdu", "VEC": "Venetian", "VIE": "Vietnamese", "WEL": "Welsh",
    "WLN": "Walloon", "WOL": "Wolof", "YID": "Yiddish", "YOR": "Yoruba",
    "ZGH": "Berber", "CNR": "Montenegrin", "MAL": "Malayalam", "GUJ": "Gujarati",
    "TAT": "Tatar", "CHV": "Chuvash", "SNK": "Soninke",
}
# A code that names a language only where it is spoken: Romansh is Swiss, and
# "ROH" from a Slovak or Czech interview is a slip the coder made, most likely
# for Romani (ROM) -- which is not guessed at either.
ONLY_IN = {"ROH": {"CH"}}
# ISO's Alemannic (GSW, "Swiss German") is Alsatian when a French respondent
# names it, and a dialect of German in Germany and Austria.
BY_COUNTRY = {("FR", "GSW"): "Alsatian", ("DE", "GSW"): "German", ("AT", "GSW"): "German"}
# Not an answer: refusal, don't know, no answer, and ISO's own non-answers.
NO_LANGUAGE = {"777", "888", "999", "", ".", "MIS", "UND", "ZXX", "MUL"}
OTHER_LANGUAGES = "Other languages"

# NUTS codes of an older version that are exactly a NUTS 2024 region, or
# exactly part of one. Everything else from an older version is left out.
OLD_CODES: dict[str, str] = {
    # France, 2016: the 22 regions of NUTS 2013 (NUTS 2) merged into the 13
    # of NUTS 2016 (NUTS 1), by loi n° 2015-29 of 16 January 2015. Each old
    # region is wholly inside one new one.
    "FR21": "FRF", "FR41": "FRF", "FR42": "FRF",
    "FR22": "FRE", "FR30": "FRE",
    "FR23": "FRD", "FR25": "FRD",
    "FR24": "FRB",
    "FR26": "FRC", "FR43": "FRC",
    "FR51": "FRG", "FR52": "FRH",
    "FR53": "FRI", "FR61": "FRI", "FR63": "FRI",
    "FR62": "FRJ", "FR81": "FRJ",
    "FR71": "FRK", "FR72": "FRK",
    "FR82": "FRL", "FR83": "FRM",
    # Greece, NUTS 2016: the same thirteen regions regrouped and recoded.
    "EL11": "EL51", "EL12": "EL52", "EL13": "EL53", "EL14": "EL61",
    "EL21": "EL54", "EL22": "EL62", "EL23": "EL63", "EL24": "EL64", "EL25": "EL65",
    # Italy, NUTS 2010: Nord-Est and Centro recoded (ITD -> ITH, ITE -> ITI).
    "ITD1": "ITH1", "ITD2": "ITH2", "ITD3": "ITH3", "ITD4": "ITH4", "ITD5": "ITH5",
    "ITE1": "ITI1", "ITE2": "ITI2", "ITE3": "ITI3", "ITE4": "ITI4",
    # The Netherlands, NUTS 2021: Utrecht and Zuid-Holland recoded when
    # Vijfheerenlanden (57,000 people) moved from the one to the other in 2019.
    "NL31": "NL35", "NL33": "NL36",
}
# A code that kept its name across a NUTS revision while its outline moved,
# with the first round coded to the newer version: the older rounds' figure
# for it is not the polygon's, and is not counted. Norway's NO02 was Hedmark
# og Oppland in NUTS 2016 (rounds 5-9) and is Innlandet in NUTS 2021 (rounds
# 10-11), without Lunner and Jevnaker, which moved to Viken in 2020.
DIFFERENT_BEFORE = {"NO02": 10}
# Where the pool starts when the default rounds hold fewer than MIN_N.
EXTEND_TO = 5
RECODED_NOTE = {
    "NL35": " save Vijfheerenlanden, which joined Utrecht from Zuid-Holland in 2019",
    "NL36": " save Vijfheerenlanden, which left for Utrecht in 2019",
}
# ESS country codes where NUTS uses another.
PREFIX = {"GR": "EL", "GB": "UK"}
ISO3 = {
    "AL": "ALB", "AT": "AUT", "BE": "BEL", "BG": "BGR", "CH": "CHE", "CY": "CYP",
    "CZ": "CZE", "DE": "DEU", "DK": "DNK", "EE": "EST", "EL": "GRC", "ES": "ESP",
    "FI": "FIN", "FR": "FRA", "HR": "HRV", "HU": "HUN", "IE": "IRL", "IS": "ISL",
    "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "ME": "MNE", "MK": "MKD",
    "NL": "NLD", "NO": "NOR", "PL": "POL", "PT": "PRT", "RS": "SRB", "SE": "SWE",
    "SI": "SVN", "SK": "SVK", "TR": "TUR", "UK": "GBR", "XK": "XKX",
}
NUTS_SHAPE = re.compile(r"^[A-Z]{2}[0-9A-Z]{1,3}$")

TABULATE = """query($input: FrequencyTabulationInput!) { analysis {
  frequencyTabulation(input: $input) {
    variableValues { name values codeList { value label isMissing } }
    table { path count } } } }"""

TABULATE_BY = """query($input: FrequencyTabulationInput!) { analysis {
  frequencyTabulationByVariables(input: $input) { responses {
    by { variable value label }
    response { variableValues { name values codeList { value label isMissing } }
               table { path count } } } } } }"""

STUDIES = """query($id: ID!) { search {
  seriesMetadata(id: $id, instance: PUBLISHED, agencyId: INT_ESSERIC) {
    title { en }
    studies { id version title { en }
      mainDataFiles { id version label { en } } } } } }"""

VARIABLES = """query($id: ID!, $version: Int) { search {
  dataFileMetadata(id: $id, version: $version, agencyId: INT_ESSERIC, instance: PUBLISHED) {
    label { en } disseminationLimitation defaultWeight { name { en } }
    variableList { name { en } label { en } } } } }"""

TABLES = {"religion": ["rlgblg", "rlgdnm"], "language": ["lnghom1"]}
# ESS10's self-completion file has no rlgblg: its questionnaire routes the
# non-belonging past the denomination, which the file codes 66 ("not
# applicable"). Its keys are rewritten into the belonging/denomination form
# the other rounds use, so 66 reads as No religion and 77/88/99 as non-answers.
SINGLE_QUESTION = {"ESS10SC"}


def one_question_key(code: str) -> str:
    """rlgdnm alone -> 'rlgblg/rlgdnm': 66 -> 2/66, 3 -> 1/3, 99 -> 9/99."""
    if code == "66":
        return "2/66"
    if code in DENOMINATIONS:
        return f"1/{code}"
    return {"77": "7/77", "88": "8/88"}.get(code, "9/99")


# ---------------------------------------------------------------------------
# The portal's tabulation service
# ---------------------------------------------------------------------------

def gql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST one query; a GraphQL error stops the run with the server's message."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json",
        "Accept": "application/json"})
    payload: dict[str, Any] = {}
    for wait in (5, 20, 60, None):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if wait is None:
                raise SystemExit(f"ess_region: {API} unreachable: {exc}")
            log(f"  retrying after {exc} in {wait}s")
            time.sleep(wait)
    if payload.get("errors"):
        raise SystemExit(f"ess_region: the portal refused a query: "
                         f"{json.dumps(payload['errors'])[:600]}")
    return payload["data"]


def _cells(tab: dict[str, Any]) -> dict[tuple[str, ...], float]:
    values = [v["values"] for v in tab["variableValues"]]
    cells: dict[tuple[str, ...], float] = {}
    for cell in tab["table"]:
        if cell["count"]:
            key = tuple(values[i][j] for i, j in enumerate(cell["path"]))
            cells[key] = cells.get(key, 0) + cell["count"]
    return cells


def tabulate(datafile: dict[str, Any], variables: list[str],
             weight: str | None) -> tuple[list[dict[str, Any]], dict[tuple[str, ...], float]]:
    """The service's crosstab of ``variables``: their code lists and the cells by code."""
    data = gql(TABULATE, {"input": {
        "datafile": {"id": datafile["id"], "version": datafile["version"]},
        "instance": "PUBLISHED", "agencyId": AGENCY, "breakVariables": variables,
        "weightVariable": weight, "includeMissing": True, "includeEmpty": False,
        "metadataLanguage": "en"}})
    tab = data["analysis"]["frequencyTabulation"]
    return tab["variableValues"], _cells(tab)


def tabulate_by(datafile: dict[str, Any], variables: list[str], by: str,
                weight: str | None) -> dict[tuple[str, str], dict[tuple[str, ...], float]]:
    """One crosstab of ``variables`` per value of ``by``, as the viewer splits by country."""
    data = gql(TABULATE_BY, {"input": {
        "datafile": {"id": datafile["id"], "version": datafile["version"]},
        "instance": "PUBLISHED", "agencyId": AGENCY, "breakVariables": variables,
        "byVariables": [by], "weightVariable": weight, "includeMissing": True,
        "includeEmpty": False, "metadataLanguage": "en"}})
    out: dict[tuple[str, str], dict[tuple[str, ...], float]] = {}
    for resp in data["analysis"]["frequencyTabulationByVariables"]["responses"]:
        key = (resp["by"][0]["value"], resp["by"][0].get("label") or "")
        out[key] = _cells(resp["response"])
    return out


def studies() -> list[dict[str, Any]]:
    data = gql(STUDIES, {"id": SERIES})
    return data["search"]["seriesMetadata"]["studies"]


def main_files() -> dict[str, dict[str, Any]]:
    """{label: datafile} for every round's main files, e.g. 'ESS11e04_2'."""
    return {df["label"]["en"]: df for study in studies()
            for df in study.get("mainDataFiles") or []}


def pick(files: dict[str, dict[str, Any]], prefix: str) -> dict[str, Any]:
    """The one integrated file whose label is ``prefix`` and an edition ('ESS10e03_3')."""
    hits = [df for label, df in files.items() if re.fullmatch(prefix + r"e\d.*", label)]
    if len(hits) != 1:
        raise SystemExit(f"ess_region: {prefix!r} names {len(hits)} datafiles: {sorted(files)}")
    return hits[0]


def fetch(rounds: list[str]) -> dict[str, Any]:
    """Every table the build needs, from the portal, checked for completeness."""
    files = main_files()
    out: dict[str, Any] = {"fetched": date.today().isoformat(), "api": API,
                           "weight": WEIGHT, "rounds": {}}
    national: dict[str, Any] = {}
    for prefix in rounds:
        df = pick(files, prefix)
        label = df["label"]["en"]
        log(f"== {label} (id {df['id']} v{df['version']})")
        entry: dict[str, Any] = {"file": label, "id": df["id"], "version": df["version"],
                                 "labels": {}}
        national[prefix] = {}
        for name, variables in TABLES.items():
            rewrite = None
            if name == "religion" and prefix in SINGLE_QUESTION:
                variables, rewrite = ["rlgdnm"], one_question_key
                entry["religion_variables"] = variables
            entry[name] = {}
            national[prefix][name] = {}
            for key, weight in (("weighted", WEIGHT), ("n", None)):
                split = tabulate_by(df, variables, "region", weight)
                entry[name][key] = {}
                for (region, _), cells in sorted(split.items()):
                    slot = entry[name][key].setdefault(region, {})
                    for code, count in sorted(cells.items()):
                        joined = "/".join(code)
                        joined = rewrite(joined) if rewrite else joined
                        slot[joined] = slot.get(joined, 0) + count
                for (region, lab) in split:
                    entry["labels"].setdefault(region, lab)
                _, whole = tabulate(df, ["cntry", *variables], weight)
                by_country: dict[str, dict[str, float]] = defaultdict(dict)
                for code, count in whole.items():
                    joined = "/".join(code[1:])
                    joined = rewrite(joined) if rewrite else joined
                    by_country[code[0]][joined] = by_country[code[0]].get(joined, 0) + count
                national[prefix][name][key] = dict(sorted(by_country.items()))
                # Every respondent the country table counts must be in some
                # region's table: a region split that lost people would bias
                # every share it gives. A respondent with no region recorded
                # is the only allowed loss, and it must be small.
                regional = sum(sum(c.values()) for c in entry[name][key].values())
                total = sum(sum(c.values()) for c in by_country.values())
                log(f"   {name} {key}: {len(split)} regions hold {regional:,.0f} of "
                    f"{total:,.0f}")
                if key == "n" and not total * 0.99 <= regional <= total:
                    raise SystemExit(f"ess_region: {label} {name}: the regions hold "
                                     f"{regional} respondents and the countries {total}")
        out["rounds"][prefix] = entry
    HERE.mkdir(parents=True, exist_ok=True)
    TABS.write_bytes(gzip.compress(json.dumps(out, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":")).encode(), mtime=0))
    write_json(NATIONAL, {"fetched": out["fetched"], "api": API, "weight": WEIGHT,
                          "rounds": national})
    log(f"  wrote {TABS.name} ({TABS.stat().st_size // 1024} kB) and {NATIONAL.name}")
    return out


# ---------------------------------------------------------------------------
# From tables to compositions
# ---------------------------------------------------------------------------

def religion_group(code: str) -> str | None:
    """'rlgblg/rlgdnm' -> the map's label, or None for a non-answer."""
    belong, _, denomination = code.partition("/")
    if belong == "2":
        return "No religion"
    if belong == "1":
        return DENOMINATIONS.get(denomination)
    return None


def language_group(code: str, country: str | None = None) -> str | None:
    """'lnghom1' -> the map's label, or None for a non-answer."""
    code = code.strip().upper()
    if code in NO_LANGUAGE:
        return None
    if country and code in ONLY_IN and country not in ONLY_IN[code]:
        return OTHER_LANGUAGES
    if country and (country, code) in BY_COUNTRY:
        return BY_COUNTRY[(country, code)]
    return LANGUAGES.get(code, OTHER_LANGUAGES)


def nuts2024(code: str) -> str | None:
    """A respondent's region code as a NUTS 2024 code, or None if it is not one."""
    code = code.strip().upper()
    if len(code) >= 2 and code[:2] in PREFIX:
        code = PREFIX[code[:2]] + code[2:]
    code = OLD_CODES.get(code, code)
    return code if NUTS_SHAPE.match(code) else None


def ancestors(code: str) -> list[str]:
    """The code and its NUTS parents down to NUTS 1: FRK -> [FRK]; ITC4 -> [ITC, ITC4]."""
    return [code[:n] for n in range(3, len(code) + 1)]


def pool(tabs: dict[str, Any], field: str, first_round: int,
         quiet: bool = False) -> dict[str, dict[str, Any]]:
    """{NUTS code: weighted and unweighted counts by group, rounds, non-answers}.

    Every respondent is added to their region and to each of its NUTS
    parents, round by round, from ``first_round`` on.
    """
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "w": Counter(), "n": Counter(), "missing": 0, "rounds": set(), "recoded": set(),
        "labels": set()})
    per_round: dict[tuple[str, str], dict[str, Counter]] = defaultdict(
        lambda: {"w": Counter(), "n": Counter()})
    unplaced: Counter = Counter()
    unlisted: Counter = Counter()
    for prefix, entry in tabs["rounds"].items():
        number, year, _ = ROUNDS[prefix]
        if number < first_round:
            continue
        table = entry[field]
        for region, cells in table["n"].items():
            code = nuts2024(region)
            weighted = table["weighted"].get(region, {})
            if code is None:
                unplaced[region] += sum(cells.values())
                continue
            country = code[:2]

            def classify(key: str) -> str | None:
                if field == "religion":
                    return religion_group(key)
                return language_group(key, country)

            if field == "language":
                for key, n in cells.items():
                    if key.strip().upper() not in LANGUAGES | dict.fromkeys(NO_LANGUAGE):
                        unlisted[f"{country}:{key}"] += n
            original = PREFIX.get(region[:2], region[:2]) + region[2:]
            for target in ancestors(code):
                if number < DIFFERENT_BEFORE.get(target, 0):
                    continue
                slot = out[target]
                slot["rounds"].add((prefix, year))
                if original.strip().upper() != code:
                    slot["recoded"].add(original.strip().upper())
                elif target == code and (entry.get("labels") or {}).get(region):
                    slot["labels"].add(entry["labels"][region].strip())
                part = per_round[(target, prefix)]
                for key, n in cells.items():
                    group = classify(key)
                    if group is None:
                        slot["missing"] += n
                        continue
                    part["n"][group] += n
                    part["w"][group] += weighted.get(key, 0)
    # Each round's weighted counts in a region are rescaled to that round's
    # respondents there before the rounds are added. The weights then do
    # their job inside a round -- correcting for who was sampled and who
    # answered -- and each round counts in proportion to its interviews. The
    # tables need it: ESS10's Norwegian weights put 382 weighted respondents
    # on the 120 interviewed in Innlandet and 221 on the 536 in Oslo og
    # Viken, and added unscaled, one round would have outweighed four.
    for (target, _), part in per_round.items():
        n, w = sum(part["n"].values()), sum(part["w"].values())
        factor = n / w if w else 0.0
        slot = out[target]
        for group, count in part["n"].items():
            slot["n"][group] += count
            slot["w"][group] += part["w"][group] * factor if w else count
    if unplaced and not quiet:
        log(f"  {field}: {sum(unplaced.values()):,.0f} respondents carry no NUTS region "
            f"({', '.join(f'{k or repr(k)}={v:,.0f}' for k, v in unplaced.most_common(8))})")
    if unlisted and not quiet:
        log(f"  language codes read as Other languages: "
            + ", ".join(f"{k}={v:,.0f}" for k, v in unlisted.most_common(40)))
    return dict(out)


def composition(slot: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Weighted shares, with a language named by too few respondents folded into Other."""
    weighted = Counter(slot["w"])
    if field == "language":
        for group, n in slot["n"].items():
            if group != OTHER_LANGUAGES and n < MIN_LANGUAGE_N:
                weighted[OTHER_LANGUAGES] += weighted.pop(group, 0)
    rows = shares({g: v for g, v in weighted.items() if v > 0})
    total = sum(r["pct"] for r in rows)
    if rows and abs(total - 100) > 0.6:
        raise SystemExit(f"ess_region: shares sum to {total}")
    return rows


def placement(code: str, crosswalk: dict[str, Any]) -> list[dict[str, Any]]:
    """The polygons the crosswalk says this NUTS code is: its own, and a twin's."""
    entry = crosswalk.get(code)
    seen = set()
    while entry and entry.get("superseded_by") and entry["superseded_by"] not in seen:
        seen.add(entry["superseded_by"])
        entry = crosswalk.get(entry["superseded_by"])
    if not entry or "shape_id" not in entry:
        return []
    out = [{"level": entry["level"], "shape_id": entry["shape_id"], "name": entry["name"]}]
    out += [{"level": t["level"], "shape_id": t["shape_id"], "name": t["name"]}
            for t in entry.get("also") or []]
    return out


def describe_rounds(rounds: set[tuple[str, int]]) -> str:
    years = sorted(ROUNDS[p][2] for p, _ in rounds)
    names = sorted({ROUNDS[p][0] for p, _ in rounds})
    span = f"{years[0][:4]}-{years[-1][-4:]}"
    return f"ESS round{'s' if len(names) > 1 else ''} {', '.join(map(str, names))} ({span})"


QUESTION = {
    "religion": ("religious belonging and denomination (rlgblg, rlgdnm): \"Do you consider "
                 "yourself as belonging to any particular religion or denomination?\" and, if "
                 "so, which; \"no\" is written as No religion"),
    "language": ("the language most often spoken at home, first mentioned (lnghom1); "
                 f"a language named by fewer than {MIN_LANGUAGE_N} respondents here is in "
                 "Other languages"),
}
CENSUS = {
    "religion": "The census does not ask religion here, or its figure is not published for "
                "this unit; a census or register count replaces this estimate wherever one "
                "is read.",
    "language": "The census does not ask home language here, or its figure is not published "
                "for this unit; a census or register count replaces this estimate wherever "
                "one is read.",
}


def build(tabs: dict[str, Any], crosswalk: dict[str, Any],
          first_round: int = FIRST_ROUND) -> tuple[list[dict[str, Any]], list[str]]:
    """Records for every polygon a pooled NUTS region reaches with n >= MIN_N."""
    by_shape: dict[tuple[str, str], dict[str, Any]] = {}
    report: list[str] = []
    def size(slot: dict[str, Any] | None) -> int:
        return int(sum(slot["n"].values())) if slot else 0

    for field in ("religion", "language"):
        pooled = pool(tabs, field, first_round)
        # The same tables pooled from round EXTEND_TO, for a region the
        # default rounds leave under MIN_N: older answers are better than
        # none, and the note says how far back the pool reaches and why.
        wider = pool(tabs, field, EXTEND_TO, quiet=True) if EXTEND_TO < first_round else {}
        for code in sorted(set(pooled) | set(wider)):
            slot, short = pooled.get(code), None
            n = size(slot)
            if n < MIN_N and size(wider.get(code)) >= MIN_N:
                short, slot = n, wider[code]
                n = size(slot)
            places = placement(code, crosswalk)
            iso3 = ISO3.get(code[:2])
            if not places or iso3 is None:
                if len(code) > 2 and n >= MIN_N and code in crosswalk:
                    report.append(f"{field} {code} n={n}: crosswalk "
                                  f"{json.dumps(crosswalk[code])[:120]}")
                continue
            if n < MIN_N:
                report.append(f"{field} {code} -> {places[0]['name']}: n={n} "
                              f"({size(wider.get(code))} from round {EXTEND_TO}) < {MIN_N}, "
                              f"left out")
                continue
            for place in places:
                key = (place["level"], place["shape_id"])
                current = by_shape.get(key, {}).get(field)
                # Recent rounds first, then the larger pool.
                if current and (current["short"] is None, current["n"]) >= (short is None, n):
                    continue
                by_shape.setdefault(key, {"place": place, "iso3": iso3})[field] = {
                    "code": code, "n": n, "slot": slot, "short": short}
    records = []
    for (level, shape_id), item in sorted(by_shape.items()):
        place, iso3 = item["place"], item["iso3"]
        fields: dict[str, Any] = {}
        sources = []
        for field in ("religion", "language"):
            got = item.get(field)
            if not got:
                continue
            slot, n = got["slot"], got["n"]
            rounds = describe_rounds(slot["rounds"])
            precision = " Low precision: under 300 respondents." if n < LOW_PRECISION else ""
            if got["short"] is not None:
                first = ROUNDS[f"ESS{first_round}"][2][:4]
                precision += (f" Rounds {first_round}-11 ({first}-2024) hold only "
                              f"{got['short']} respondents here, under the {MIN_N} this map "
                              f"requires, so the pool reaches back to round {EXTEND_TO} "
                              f"({ROUNDS[f'ESS{EXTEND_TO}'][2][:4]}).")
            if slot.get("recoded"):
                precision += (f" Rounds coded to an older NUTS version count here through "
                              f"{', '.join(sorted(slot['recoded']))}, each wholly inside "
                              f"{got['code']}{RECODED_NOTE.get(got['code'], '')}.")
            if field == "religion" and any(p in SINGLE_QUESTION for p, _ in slot["rounds"]):
                precision += (" Round 10 here is the self-completion file, which asks the "
                              "denomination alone: those it routes past it are counted as "
                              "No religion, and the written mode draws more of them than an "
                              "interview does.")
            fields[field] = composition(slot, field)
            fields[f"{field}_year"] = max(year for _, year in slot["rounds"])
            fields[f"{field}_basis"] = ("survey estimate: self-identification, residents "
                                        "aged 15 and over in private households")
            fields[f"{field}_note"] = (
                f"European Social Survey, {rounds}, pooled: {QUESTION[field]}. A survey "
                f"estimate, not a count: {n:,} respondents in NUTS region {got['code']} "
                f"gave an answer ({int(slot['missing']):,} refused, did not know or did not "
                f"answer and are left out), weighted within each round by the "
                f"post-stratification weight (pspwght), rescaled to that round's "
                f"respondents here, and pooled.{precision} Universe: residents aged 15 "
                f"and over in private households who could be interviewed in a survey "
                f"language. Tabulated by the ESS Data Portal's open analysis service. "
                f"{CENSUS[field]}")
            sources.append({"field": field,
                            "name": f"European Social Survey (ESS ERIC), {rounds}: {field} "
                                    f"by NUTS region {got['code']}",
                            "url": PORTAL, "license": LICENCE})
        # The survey's own names for the region, so a count read later under
        # the region's official name is recognised as the same place.
        aliases = sorted({label for f in ("religion", "language") if f in item
                          for label in item[f]["slot"].get("labels", ())
                          if label and label != place["name"]})
        records.append(record(
            f"ESS-{iso3}-{level}-{shape_id}", place["name"], level=level, parent=iso3,
            country=iso3, match_by="shape_id", shape_id=shape_id, sources=sources,
            aliases=aliases or None,
            codes={"nuts": sorted({item[f]["code"] for f in ("religion", "language")
                                   if f in item}),
                   "ess_n": {f: item[f]["n"] for f in ("religion", "language") if f in item}},
            **fields))
    return records, report


def weight_scale(tabs: dict[str, Any]) -> list[str]:
    """Each round's and country's weighted respondents over its unweighted ones.

    pspwght is scaled to average 1 within a country and round. pool() rescales
    every round in every region to its respondents, so a round off that scale
    no longer counts for more than its interviews; it is reported here so the
    log shows where the rescaling mattered.
    """
    lines = []
    for prefix, entry in tabs["rounds"].items():
        for field in ("religion",):
            n: Counter = Counter()
            w: Counter = Counter()
            for region, cells in entry[field]["n"].items():
                code = nuts2024(region)
                country = code[:2] if code else region[:2]
                n[country] += sum(cells.values())
                w[country] += sum(entry[field]["weighted"].get(region, {}).values())
            for country in sorted(n):
                ratio = w[country] / n[country] if n[country] else 0
                if not 0.97 <= ratio <= 1.03:
                    lines.append(f"{prefix} {country}: weighted {w[country]:,.0f} for "
                                 f"{n[country]:,.0f} respondents ({ratio:.2f})")
    return lines


def national(first_round: int = FIRST_ROUND) -> dict[str, dict[str, Any]]:
    """Pooled national compositions, for the curated country rows (logged, not written)."""
    data = read_json(NATIONAL, {}) or {}
    out: dict[str, dict[str, Any]] = {}
    for field in ("religion", "language"):
        pooled: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "w": Counter(), "n": Counter(), "missing": 0, "rounds": set()})
        for prefix, tables in (data.get("rounds") or {}).items():
            if ROUNDS[prefix][0] < first_round:
                continue
            for cntry, cells in tables[field]["n"].items():
                slot = pooled[cntry]
                slot["rounds"].add((prefix, ROUNDS[prefix][1]))
                part_n: Counter = Counter()
                part_w: Counter = Counter()
                for key, n in cells.items():
                    group = (religion_group(key) if field == "religion"
                             else language_group(key, PREFIX.get(cntry, cntry)))
                    if group is None:
                        slot["missing"] += n
                        continue
                    part_n[group] += n
                    part_w[group] += tables[field]["weighted"][cntry].get(key, 0)
                # Rescaled to the round's respondents, as pool() does.
                factor = sum(part_n.values()) / sum(part_w.values()) if sum(part_w.values()) else 0
                for group, n in part_n.items():
                    slot["n"][group] += n
                    slot["w"][group] += part_w[group] * factor if factor else n
        for cntry, slot in pooled.items():
            out.setdefault(cntry, {})[field] = {
                "n": int(sum(slot["n"].values())), "rounds": describe_rounds(slot["rounds"]),
                "year": max(y for _, y in slot["rounds"]), "groups": composition(slot, field)}
    return out


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover(countries: list[str]) -> None:
    for study in studies():
        title = study["title"]["en"]
        for df in study.get("mainDataFiles") or []:
            log(f"== {title} :: {df['label']['en']} id={df['id']} v={df['version']}")
            for probe in (["cntry", "lnghom1"], ["cntry", "rlgdnm"]):
                try:
                    codes, cells = tabulate(df, probe, None)
                except SystemExit as exc:
                    log(f"   {probe[1]}: {str(exc)[:200]}")
                    continue
                labels = {c["value"]: c["label"] or "" for c in codes[1]["codeList"] or []}
                for cc in countries:
                    row = sorted(((k[1], v) for k, v in cells.items() if k[0] == cc),
                                 key=lambda kv: -kv[1])
                    if row:
                        log(f"   {probe[1]} {cc} n={int(sum(v for _, v in row))}: "
                            + " ".join(f"{k}={labels.get(k, '?')[:22]}:{int(v)}"
                                       for k, v in row[:40]))


def show_variables(prefixes: str, pattern: str) -> None:
    files = main_files()
    rx = re.compile(pattern, re.I)
    for prefix in prefixes.split(","):
        df = pick(files, prefix)
        meta = gql(VARIABLES, {"id": df["id"], "version": df["version"]})["search"]["dataFileMetadata"]
        log(f"== {meta['label']['en']} limitation={meta.get('disseminationLimitation')} "
            f"weight={meta.get('defaultWeight')} variables={len(meta['variableList'])}")
        for var in meta["variableList"]:
            name, label = var["name"]["en"], (var.get("label") or {}).get("en") or ""
            if rx.search(name) or rx.search(label):
                log(f"   {name}: {label[:90]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help="read the tables from the portal before building")
    ap.add_argument("--first-round", type=int, default=FIRST_ROUND,
                    help=f"pool rounds from this one on (default {FIRST_ROUND})")
    ap.add_argument("--curated", default=None,
                    help="print curated country rows, e.g. AT:religion+language,FR:religion")
    ap.add_argument("--regions", default=None,
                    help="with the build: log every pooled region of these NUTS country codes")
    ap.add_argument("--discover", default=None,
                    help="comma-separated ESS country codes: list rounds and their codes")
    ap.add_argument("--variables", nargs=2, metavar=("ROUNDS", "REGEX"),
                    help="list rounds' variables whose name or label matches")
    ap.add_argument("--by", nargs="+", metavar="ARG",
                    help="ROUND VAR1,VAR2 BYVAR [WEIGHT [LIMIT]]: one tabulation per BYVAR value")
    args = ap.parse_args()
    if args.discover:
        discover(args.discover.split(","))
        return 0
    if args.variables:
        show_variables(*args.variables)
        return 0
    if args.by:
        df = pick(main_files(), args.by[0])
        weight = args.by[3] if len(args.by) > 3 and args.by[3] != "-" else None
        limit = int(args.by[4]) if len(args.by) > 4 else 20
        split = tabulate_by(df, args.by[1].split(","), args.by[2], weight)
        log(f"   {len(split)} values of {args.by[2]}")
        for (value, label), cells in sorted(split.items())[:limit]:
            log(f"   {value} {label[:30]} n={sum(cells.values())}: "
                + " ".join(f"{'/'.join(k)}={v}" for k, v in sorted(cells.items())[:14]))
        return 0

    log(f"ess_region: European Social Survey by region, rounds {args.first_round}-11")
    if args.fetch or not TABS.exists():
        tabs = fetch(list(ROUNDS))
    else:
        tabs = json.loads(gzip.decompress(TABS.read_bytes()))
    crosswalk = read_json(CROSSWALK, {}) or {}
    if not crosswalk:
        raise SystemExit(f"ess_region: {CROSSWALK} is missing")
    if args.regions:
        wanted = set(args.regions.split(","))
        for prefix, entry in tabs["rounds"].items():
            codes = sorted(r for r in entry["religion"]["n"] if (nuts2024(r) or r)[:2] in wanted)
            log(f"  {prefix}: " + " ".join(
                f"{r}={int(sum(entry['religion']['n'][r].values()))}" for r in codes))
        for code, slot in sorted(pool(tabs, "religion", args.first_round).items()):
            if code[:2] in wanted:
                log(f"  religion {code} n={int(sum(slot['n'].values()))} "
                    f"rounds={sorted(p for p, _ in slot['rounds'])} "
                    f"-> {[p['name'] for p in placement(code, crosswalk)]}")
    scale = weight_scale(tabs)
    for line in scale:
        log(f"  weight scale: {line}")
    if args.regions:
        for prefix, entry in tabs["rounds"].items():
            for region in sorted(entry["religion"]["n"]):
                if (nuts2024(region) or region)[:2] in set(args.regions.split(",")):
                    n = sum(entry["religion"]["n"][region].values())
                    w = sum(entry["religion"]["weighted"].get(region, {}).values())
                    log(f"  weights {prefix} {region}: {w:,.0f} weighted for {n:,.0f}")
    records, report = build(tabs, crosswalk, args.first_round)
    for line in report:
        log(f"  {line}")
    by_country = Counter((r["country"], r["level"]) for r in records)
    for (iso3, level), count in sorted(by_country.items()):
        filled = [r for r in records if r["country"] == iso3 and r["level"] == level]
        log(f"  {iso3} {level}: {count} units -- " + "; ".join(
            f"{r['name']} [{','.join(r['codes']['nuts'])}] "
            + " ".join(f"{f[:3]} n={n}" for f, n in r["codes"]["ess_n"].items())
            for r in filled))
    whole = national(args.first_round)
    for cntry, fields in sorted(whole.items()):
        for field, got in fields.items():
            log(f"  national {cntry} {field} n={got['n']} {got['rounds']}: "
                + ", ".join(f"{g['group']} {g['pct']}" for g in got["groups"][:8]))
    # Country rows for data/curated/admin0_detail.json, printed and not
    # written: an adapter cannot reach a country record, so these are
    # proposals for the curated file, where the owner decides.
    for item in (args.curated or "").split(","):
        if not item:
            continue
        cntry, _, fields = item.partition(":")
        for field in fields.split("+"):
            got = whole.get(cntry, {}).get(field)
            if not got:
                log(f"  curated {cntry} {field}: no national table")
                continue
            iso3 = ISO3[PREFIX.get(cntry, cntry)]
            print(json.dumps({
                "country": iso3, "field": field, "year": got["year"],
                "basis": "survey estimate: self-identification, residents aged 15 and over "
                         "in private households",
                # count: weighted respondents, as on the regional records.
                "groups": got["groups"],
                "source": f"European Social Survey (ESS ERIC), {got['rounds']}, national "
                          f"samples pooled: {field}",
                "url": PORTAL, "license": LICENCE,
                "note": (f"European Social Survey, {got['rounds']}, pooled: "
                         f"{QUESTION[field]}. A survey estimate, not a count: {got['n']:,} "
                         f"respondents aged 15 and over in private households, weighted within "
                         f"each round by the post-stratification weight (pspwght), rescaled to "
                         f"the round's respondents, and pooled. The census does not ask this "
                         f"question. Where one of the country's regions holds {MIN_N} "
                         f"respondents or more, its division carries the same survey's "
                         f"regional estimate (ess_region_survey.json)."),
            }, ensure_ascii=False), flush=True)
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
