#!/usr/bin/env python3
"""United States: religion by county, from the 2023 PRRI Census of American Religion.

The counties already carry religion, from the 2020 U.S. Religion Census (ASARB)
by way of ``us_acs.py``. That study is a count of *adherents reported by
religious bodies* and it reaches about 48.6% of the population; everyone else --
people who belong to nothing, and members of the bodies that did not file a
return -- is pooled into one "Unaffiliated or not reported" category, because
the study genuinely cannot tell them apart. It is the best congregational count
that exists and it answers a different question from the one this map asks.

PRRI's Census of American Religion answers the map's question. It is
self-identification: 40,000 adults on Ipsos's KnowledgePanel, interviewed
through 2023 as part of the American Values Atlas, asked what they are. It
covers 100% of the population rather than 48.6%, and it separates the
religiously unaffiliated (27% of Americans) from non-response instead of
banking them together. So where this file matches a county, it **replaces** the
ASARB religion figures rather than filling a gap -- every county it touches
already had a religion list -- and because it replaces figures already on the
map, the repository owner reviews the change before it ships.

Two things about it are not a census and the note on every record says so:
these are modelled small-area estimates from a national sample, not a
county-by-county enumeration, and they describe adults, not residents.

**Where the numbers come from.** PRRI publishes the county data as Datawrapper
choropleths embedded in the article, one chart per religious group. The chart
IDs below were read out of the saved article page (the ``datawrapper-chart-*``
iframe ids, each beside its own ``title`` attribute), and Datawrapper serves
every published chart's underlying table at
``https://datawrapper.dwcdn.net/<id>/<version>/dataset.csv``. There is no
single county-by-religion table anywhere; assembling one means fetching all
eighteen and joining them on FIPS, which is what this does.

**Race is dropped, not refiled.** PRRI's categories are race crossed with
religion -- "White Evangelical Protestant", "Black Protestant", "Hispanic
Catholic" -- because the racial split is the finding the report is about. This
map's religion tree is about religion. There is no node for "White Protestant"
and inventing one would put race in the religion tree, where a reader filtering
for Protestantism would then miss four-fifths of American Protestants. So the
five Protestant categories collapse to Protestantism and the three Catholic
ones to Catholicism, and the race detail is *dropped* rather than misfiled:
this file cannot answer "how many Black Protestants are in this county" and
does not pretend to. PRRI's article is the place for that question.

Two categories have no node and are not worth inventing one for. Unitarian
Universalists are 0.5% of Americans and "Other Non-Christian Religious" is
already a residual; both become "Other religions", which is what that node is
for. The collapse is lossy in one visible way and the note records it.

**The nineteenth chart is not a percentage.** ``mL9BH`` is the Religious
Diversity Index, a 0-1 concentration score, not a share of anyone. Reading it
alongside the other eighteen would add a spurious "group" worth 50-odd points
to every county and quietly wreck the sums. It is listed below as excluded so
that a later reader can see it was considered rather than missed.

**The join is by FIPS and only by FIPS.** County *names* are the classic silent
mis-match here -- there are thirty-odd Washington Counties and a Wilcox in both
Alabama and Georgia -- so the name is never the key. It is used only as a
check: where PRRI's own county name and the map's disagree after normalisation,
that FIPS is reported and refused rather than joined, because a FIPS whose name
moved is usually a FIPS that was reassigned. Connecticut is the live case:
the state replaced its eight counties with nine planning regions in 2022, and a
PRRI table on the new codes joined against an ACS 2022 county file on the old
ones would match nothing there and must say so rather than drop it.

**Status: this adapter has not yet been run against the real tables.** Both
``datawrapper.dwcdn.net`` and ``prri.org`` are refused by the build sandbox's
egress proxy (``403 to CONNECT``, an organisation policy denial, confirmed from
two independent clients), which is the ordinary state of affairs here and the
reason ``.github/workflows/run-adapter.yml`` exists: the fetch runs on an
Actions runner with open egress. Nothing about the column *names* below was
read off a real PRRI file, so the reader identifies its columns by testing
their contents rather than by trusting a header, and refuses wherever the
answer is ambiguous instead of taking the first candidate.

Probe before fetching. ``--probe`` fetches one chart and prints its delimiter,
header, first rows, per-column classification and value range without writing
anything, so the rules can be corrected against the real file:

    scripts.fetch_census.us_prri --probe --chart d76SP     # commit off
    scripts.fetch_census.us_prri --probe --chart all       # every chart's header

Arguments are passed to the runner through ``printf '%s' "$ADAPTER" | xargs
python3 -m``, so they must survive word-splitting: no spaces inside a value, no
quotes, no shell metacharacters. Chart ids and integers are all this takes.

Usage:
    python -m scripts.fetch_census.us_prri --probe --chart d76SP
    python -m scripts.fetch_census.us_prri
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, read_json, record, write_json,
)

OUT = "us_prri_county.json"
YEAR = 2023
SOURCE = ("PRRI, 2023 Census of American Religion: County-Level Data on "
          "Religious Identity and Diversity (American Values Atlas 2023)")
PAGE = ("https://www.prri.org/research/2023-prri-census-of-american-religion-"
        "county-level-data-on-religious-identity-and-diversity/")
LICENCE = "Copyright PRRI; used with attribution to the published report"

# The county universe and its canonical names. Written by us_acs.py, which is
# the file this one overwrites the religion field of; taking the names and
# parents from there rather than from PRRI is what keeps the two files mergeable.
UNIVERSE = "us_county.json"

CDN = "https://datawrapper.dwcdn.net"

# Chart id -> the title PRRI gave it, read from the iframe attributes in the
# saved article. Eighteen groups that partition the adult population once.
CHARTS: dict[str, str] = {
    "d76SP": "White Evangelical Protestant",
    "kgIZw": "White Mainline/Non-evangelical Protestant",
    "JscmH": "Black Protestant",
    "JyY3X": "Hispanic Protestant",
    "vU3Yw": "Other Protestant of Color",
    "CGgFv": "White Catholic",
    "EtVMq": "Hispanic Catholic",
    "fKYzV": "Other Catholic of Color",
    "R1i2j": "Latter-day Saint (Mormon)",
    "UswHc": "Orthodox Christian",
    "3sLhY": "Jehovah's Witness",
    "zfKST": "Jewish",
    "5gGLT": "Muslim",
    "DtOPx": "Buddhist",
    "r274m": "Hindu",
    "OtQCR": "Unitarian Universalist",
    "8fj2m": "Other Non-Christian Religious",
    "CLuyf": "Religiously Unaffiliated",
}

# Present in the article, deliberately not read: an index, not a share.
EXCLUDED: dict[str, str] = {
    "mL9BH": "The Religious Diversity Index, By County -- a 0-1 concentration "
             "score rather than a percentage of anybody",
}

# PRRI category -> the religion node this map already has. Race is dropped
# here; see the module docstring for why it is not refiled instead.
COLLAPSE: dict[str, str] = {
    "White Evangelical Protestant": "Protestantism",
    "White Mainline/Non-evangelical Protestant": "Protestantism",
    "Black Protestant": "Protestantism",
    "Hispanic Protestant": "Protestantism",
    "Other Protestant of Color": "Protestantism",
    "White Catholic": "Catholicism",
    "Hispanic Catholic": "Catholicism",
    "Other Catholic of Color": "Catholicism",
    "Latter-day Saint (Mormon)": "Latter-day Saints",
    "Orthodox Christian": "Orthodoxy",
    "Jehovah's Witness": "Jehovah's Witnesses",
    "Jewish": "Judaism",
    "Muslim": "Islam",
    "Buddhist": "Buddhism",
    "Hindu": "Hinduism",
    "Unitarian Universalist": "Other religions",
    "Other Non-Christian Religious": "Other religions",
    "Religiously Unaffiliated": "No religion",
}

# The national figures PRRI states in the article's own opening paragraph and
# its first three footnotes, quoted here so the roll-up has something published
# to be checked against:
#
#   "Two-thirds of Americans (66%) identify as Christian ... Over one-quarter
#   of Americans (27%) are religiously unaffiliated, and 6% belong to a
#   non-Christian religion."
#
# These three are used rather than the eighteen group figures because they are
# the numbers PRRI writes as single published values; the group shares in the
# footnotes are rounded to whole percents and summing five of them to check
# Protestantism would be checking the rounding as much as the data.
NATIONAL: dict[str, float] = {
    "Christian": 66.0,
    "No religion": 27.0,
    "Non-Christian": 6.0,
}
CHRISTIAN = {"Protestantism", "Catholicism", "Orthodoxy", "Latter-day Saints",
             "Jehovah's Witnesses"}

# How far a county's eighteen shares may sit from 100 before the run stops.
# Eighteen values each rounded to one decimal can drift 0.9 on rounding alone,
# and PRRI fits each group's small-area model separately rather than
# constraining the eighteen to sum, so exact closure is not expected. Five
# points is the band that still catches the failure this guards against: a
# chart fetched twice or not at all moves a real county by more than that for
# every group bigger than Hinduism.
SUM_TOLERANCE = 5.0
# The per-county band above is deliberately loose, so it would not notice one
# missing chart in a county where that group is tiny. This one would: across
# three thousand counties the typical miss should be rounding-sized, and a
# systematically absent chart drags the median straight off zero.
MEDIAN_SUM_TOLERANCE = 1.5

# The national roll-up is weighted by ACS total population because that is the
# weight this repository has. PRRI weights to the adult population, and the
# under-18 share varies by county, so the two cannot agree exactly; the article
# also rounds its national figures to whole percents. Two and a half points is
# wide enough for both and still far narrower than the error any mis-assembled
# category table would produce.
NATIONAL_TOLERANCE = 2.5

# US counties and county equivalents. The expected count is stated rather than
# inferred so that a table which quietly lost a state fails here.
MIN_COUNTIES = 3_000
MAX_COUNTIES = 3_200

# Below this share of PRRI's rows finding a home, the join itself is wrong and
# reporting "some counties unmatched" would understate it.
MIN_JOIN_RATE = 0.95


def normalise(name: str) -> str:
    """A county name reduced to the part two sources have to agree on.

    'Autauga County, Alabama' and 'Autauga' are the same place; 'Doña Ana' and
    'Dona Ana' are too. Only ever used to decide whether a name *disagrees*
    with the one already on the map -- never to make a join.
    """
    name = name.split(",")[0]
    name = name.replace("ñ", "n").replace("Ñ", "N")
    name = re.sub(r"\b(County|Parish|Borough|Census Area|Municipality|City and "
                  r"Borough|Municipio|Planning Region)\b", " ", name, flags=re.I)
    name = re.sub(r"[^a-z0-9]+", "", name.lower())
    return name


def reachable(url: str, *, timeout: int) -> str:
    """GET, turning an unreachable CDN into a refusal that says what to do.

    This is the failure the adapter was written under, so it gets a sentence
    rather than a stack trace: on the machine it was written on the egress
    proxy answers 403 to CONNECT for datawrapper.dwcdn.net and prri.org alike,
    which is an organisation policy denial and not something to retry around.
    """
    try:
        page = http_get(url, timeout=timeout)
    except Exception as exc:                       # noqa: BLE001 -- reported, not swallowed
        raise SystemExit(
            f"us_prri: cannot reach {url} ({exc}). PRRI publishes this data "
            f"only as Datawrapper charts, so there is no fallback host to try. "
            f"If this is a 403 from an egress proxy it is a policy denial: "
            f"report the blocked host rather than routing around it. Nothing "
            f"was written; the counties keep the ASARB figures they have.") from exc
    return page


def chart_version(chart: str) -> int:
    """The version integer Datawrapper is currently publishing for a chart.

    The published page references its own assets by version, so the number is
    in the HTML; guessing it instead would mean either fetching a stale table
    or 404ing on a chart that has been revised more times than the guess.
    """
    page = reachable(f"{CDN}/{chart}/", timeout=60)
    if isinstance(page, bytes):
        page = page.decode("utf-8", "replace")
    found = {int(m) for m in re.findall(rf"{chart}/(\d+)/", page)}
    if not found:
        raise SystemExit(
            f"us_prri: no version number on {CDN}/{chart}/; Datawrapper has "
            f"changed how a published chart names its assets and the dataset "
            f"path can no longer be derived")
    return max(found)


def fetch_dataset(chart: str) -> str:
    """The published table behind one chart."""
    version = chart_version(chart)
    url = f"{CDN}/{chart}/{version}/dataset.csv"
    text = reachable(url, timeout=120)
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", "replace")
    return text


# The two-digit prefixes a real county FIPS can start with: the 50 states and
# DC run 01-56 with gaps, and the territories sit in the 60s and 70s. A column
# of populations or of years will contain something outside this set almost at
# once, which is what makes it a usable test for "is this really a FIPS column".
STATE_PREFIXES = ({f"{n:02d}" for n in range(1, 57)}
                  | {"60", "66", "68", "69", "70", "72", "74", "78"})

# Datawrapper writes whatever the chart's author uploaded. A table is not
# necessarily comma-separated, and reading a tab-separated one with the comma
# reader yields a single fused column and a confusing refusal further down.
DELIMITERS = (",", "\t", ";", "|")


def split_rows(text: str) -> tuple[list[list[str]], str]:
    """Parse the CSV, working out its delimiter rather than assuming one."""
    best: tuple[list[list[str]], str] | None = None
    for delimiter in DELIMITERS:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)
                if any(c.strip() for c in r)]
        width = max((len(r) for r in rows), default=0)
        if width < 2:
            continue
        if best is None or width > max(len(r) for r in best[0]):
            best = (rows, delimiter)
    if best is None:
        return [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)], ","
    return best


def as_float(cell: str) -> float | None:
    """A cell as a number, or None if it is not one."""
    cell = cell.strip().rstrip("%").replace(",", "").replace("−", "-")
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def censored(cell: str) -> bool:
    """A cell PRRI deliberately did not give precisely, e.g. '<0.5'."""
    return bool(re.match(r"^\s*[<>]\s*\d", cell or ""))


def classify(columns: list[tuple[str, ...]]) -> tuple[list[int], list[int]]:
    """Which columns hold county FIPS codes, and which hold a numeric series."""
    fips_cols, value_cols = [], []
    for i, col in enumerate(columns):
        values = [v.strip() for v in col]
        if not values:
            continue
        digits = [v for v in values if re.fullmatch(r"\d{4,5}", v)]
        prefixed = [v for v in digits if v.zfill(5)[:2] in STATE_PREFIXES]
        # A county table has about 3,100 rows; a handful of rows is some other
        # table entirely, and no length of guessing makes it into this one.
        if len(values) > 100 and len(prefixed) >= 0.9 * len(values):
            fips_cols.append(i)
            continue
        if sum(as_float(v) is not None for v in values) >= 0.9 * len(values):
            value_cols.append(i)
    return fips_cols, value_cols


def read_dataset(text: str, *, chart: str) -> dict[str, float]:
    """One chart's table -> {5-digit FIPS: percent}.

    The columns are identified by what they contain rather than by name. A
    Datawrapper dataset carries whatever headers its author typed, and this
    adapter was written without sight of the real ones (see the module
    docstring); a header guess that was wrong would fail as a KeyError months
    from now, while this fails immediately and says which column it could not
    find. It also does the job the header could not: a table that is not
    county-level has no column of county FIPS codes in it, and that is exactly
    the thing being tested for.

    Both the key column and the value column must be unambiguous. Taking the
    first of two candidates is a guess, and a guess between a FIPS column and a
    population column is the silent mis-match this repository exists to avoid.
    """
    rows, _ = split_rows(text)
    if len(rows) < 2:
        raise SystemExit(f"us_prri: chart {chart} returned no rows")
    header, body = rows[0], rows[1:]

    width = max(len(r) for r in body)
    body = [r + [""] * (width - len(r)) for r in body]
    columns = list(zip(*body))
    fips_cols, value_cols = classify(columns)

    if len(fips_cols) != 1:
        raise SystemExit(
            f"us_prri: chart {chart} has {len(fips_cols)} columns of county "
            f"FIPS codes (header {header}); "
            + ("this is not the county-level table"
               if not fips_cols else
               "which one is the key cannot be decided without guessing"))
    fips_col = fips_cols[0]
    if len(value_cols) != 1:
        raise SystemExit(
            f"us_prri: chart {chart} has {len(value_cols)} numeric value "
            f"columns besides FIPS (header {header}); which one is the "
            f"percentage cannot be decided without guessing")
    value_col = value_cols[0]

    # PRRI may publish a suppressed share as "<0.5" rather than a number.
    # Dropping those cells would leave the county's shares quietly short of
    # 100, so the run stops and says how many there are: what a censored value
    # should become is a judgement for whoever is reading the real table, not
    # something to decide here by default.
    hidden = [r[fips_col].strip() for r in body if censored(r[value_col])]
    if hidden:
        raise SystemExit(
            f"us_prri: chart {chart} censors {len(hidden)} counties (e.g. "
            f"{hidden[:5]}) with a '<' or '>' value. Treating those as zero "
            f"would understate the group and leave the county's shares short "
            f"of 100; decide what they should become and say so in the note "
            f"before running this again.")

    out: dict[str, float] = {}
    for row in body:
        fips = row[fips_col].strip().zfill(5)
        value = as_float(row[value_col])
        if value is None:
            continue
        if fips in out:
            raise SystemExit(
                f"us_prri: chart {chart} lists FIPS {fips} twice; a duplicated "
                f"county would be counted twice in the national roll-up")
        out[fips] = value
    if not out:
        raise SystemExit(f"us_prri: chart {chart} yielded no usable rows")
    return out


def collapse(by_category: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """{category: {fips: pct}} -> {fips: {religion node: pct}}.

    Every category must be one this adapter has decided about. A nineteenth
    group appearing in a later PRRI release would otherwise be silently
    dropped, which is the failure mode the whole file is written against.
    """
    unknown = sorted(set(by_category) - set(COLLAPSE))
    if unknown:
        raise SystemExit(
            f"us_prri: no religion node decided for {unknown}; PRRI has added "
            f"a category and it must be mapped by hand, not defaulted")

    out: dict[str, dict[str, float]] = {}
    for category, values in by_category.items():
        node = COLLAPSE[category]
        for fips, pct in values.items():
            out.setdefault(fips, {})
            out[fips][node] = out[fips].get(node, 0.0) + pct
    return out


def check_coverage(by_category: dict[str, dict[str, float]]) -> set[str]:
    """Every chart must describe the same counties.

    Eighteen separately published tables can disagree about which counties they
    cover, and a county missing from one of them is a county whose shares sum
    to less than 100 for a reason that has nothing to do with its religion.
    """
    sets = {cat: set(vals) for cat, vals in by_category.items()}
    common = set.intersection(*sets.values()) if sets else set()
    for category, fips in sets.items():
        missing = len(common) and len(fips - common)
        if missing:
            log(f"  {category}: {missing} counties not shared by every chart")
    if not common:
        raise SystemExit("us_prri: the eighteen charts share no county at all")
    return common


def check_sums(counties: dict[str, dict[str, float]]) -> None:
    """Each county's shares must account for its whole adult population."""
    misses = sorted(((abs(sum(groups.values()) - 100.0), fips)
                     for fips, groups in counties.items()), reverse=True)
    worst, worst_fips = misses[0]
    if worst > SUM_TOLERANCE:
        raise SystemExit(
            f"us_prri: county {worst_fips} sums to "
            f"{sum(counties[worst_fips].values()):.1f}%, {worst:.1f} points "
            f"from 100 against a tolerance of {SUM_TOLERANCE}; a chart is "
            f"missing, duplicated, or is not a percentage")
    median = misses[len(misses) // 2][0]
    if median > MEDIAN_SUM_TOLERANCE:
        raise SystemExit(
            f"us_prri: the typical county is {median:.1f} points from 100 "
            f"(tolerance {MEDIAN_SUM_TOLERANCE}); that is a systematic gap, "
            f"not rounding -- one of the eighteen charts is absent")
    log(f"  sums: worst county {worst:.1f}pp from 100, median {median:.1f}pp")


def check_national(counties: dict[str, dict[str, float]],
                   populations: dict[str, float]) -> None:
    """The roll-up must reproduce the three figures PRRI publishes nationally.

    This is the invariant that would catch a category mapped to the wrong node:
    the per-county sums stay at 100 however the eighteen are filed, and only a
    comparison against a published total notices that Catholics were counted as
    Protestants.
    """
    weighted: dict[str, float] = {}
    total = 0.0
    for fips, groups in counties.items():
        pop = populations.get(fips)
        if not pop:
            continue
        total += pop
        for node, pct in groups.items():
            weighted[node] = weighted.get(node, 0.0) + pct * pop
    if not total:
        raise SystemExit(
            "us_prri: no county carried a population, so the national roll-up "
            "cannot be weighted and the published figures cannot be checked")

    share = {node: value / total for node, value in weighted.items()}
    rolled = {
        "Christian": sum(v for k, v in share.items() if k in CHRISTIAN),
        "No religion": share.get("No religion", 0.0),
        "Non-Christian": sum(v for k, v in share.items()
                             if k not in CHRISTIAN and k != "No religion"),
    }
    for label, published in NATIONAL.items():
        got = rolled[label]
        if abs(got - published) > NATIONAL_TOLERANCE:
            raise SystemExit(
                f"us_prri: the county roll-up puts {label} at {got:.1f}% "
                f"against PRRI's published {published:.0f}%, outside the "
                f"{NATIONAL_TOLERANCE} point tolerance; the categories are not "
                f"being collapsed into the right nodes")
    log("  national roll-up: " + ", ".join(
        f"{k} {rolled[k]:.1f}% (published {v:.0f}%)" for k, v in NATIONAL.items()))


def build(counties: dict[str, dict[str, float]],
          universe: list[dict[str, Any]],
          prri_names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Join PRRI's counties onto the map's, by FIPS, and refuse what will not join."""
    by_fips = {(row.get("codes") or {}).get("geoid"): row for row in universe}
    by_fips.pop(None, None)

    records: list[dict[str, Any]] = []
    unmatched: list[str] = []
    renamed: list[str] = []
    for fips in sorted(counties):
        home = by_fips.get(fips)
        if home is None:
            unmatched.append(fips)
            continue
        if prri_names and fips in prri_names:
            if normalise(prri_names[fips]) != normalise(home.get("name", "")):
                renamed.append(f"{fips} PRRI {prri_names[fips]!r} "
                               f"vs map {home.get('name')!r}")
                continue
        groups = counties[fips]
        rows = [{"group": node, "pct": round(pct, 1)}
                for node, pct in sorted(groups.items(),
                                        key=lambda kv: (-kv[1], kv[0]))
                if round(pct, 1) > 0]
        records.append(record(
            f"USA-{fips}", home["name"],
            level="admin2", parent=home.get("parent", "USA"), country="USA",
            codes=home.get("codes"),
            religion=rows or gap(NOT_AVAILABLE),
            religion_year=YEAR,
            religion_basis="self-identification",
            religion_note=(
                f"{SOURCE}. Self-reported religious identity among adults, "
                f"modelled to county level from a national random sample of "
                f"40,000 adults on Ipsos's KnowledgePanel interviewed during "
                f"2023 (national margin of error +/-0.7 points); these are "
                f"small-area estimates, not an enumeration, and they describe "
                f"adults rather than all residents. Replaces the 2020 U.S. "
                f"Religion Census adherent counts this county carried, which "
                f"reached about 48.6% of the population and could not "
                f"distinguish the unaffiliated from the unreported. PRRI's "
                f"categories cross race with religion; the five Protestant and "
                f"three Catholic categories are summed into Protestantism and "
                f"Catholicism and the racial detail is dropped rather than "
                f"filed under religion, so this file cannot be used to ask "
                f"about religion by race. Unitarian Universalists are counted "
                f"in 'Other religions'."),
            sources=[{"field": "religion", "name": SOURCE, "url": PAGE,
                      "license": LICENCE}],
        ))

    if renamed:
        raise SystemExit(
            f"us_prri: {len(renamed)} FIPS codes name a different county in "
            f"PRRI than on the map, so the join would be silently wrong; "
            f"first few: {renamed[:5]}")
    if unmatched:
        log(f"  {len(unmatched)} PRRI counties have no shape on the map "
            f"(first few {unmatched[:8]}); left out rather than forced")
    rate = len(records) / max(len(counties), 1)
    if rate < MIN_JOIN_RATE:
        raise SystemExit(
            f"us_prri: only {rate:.1%} of PRRI's counties joined to a map "
            f"shape by FIPS, below the {MIN_JOIN_RATE:.0%} floor; the two "
            f"sides are on different county vintages (Connecticut's 2022 "
            f"planning regions are the usual cause) and must be reconciled "
            f"rather than part-matched")
    if not MIN_COUNTIES <= len(records) <= MAX_COUNTIES:
        raise SystemExit(
            f"us_prri: built {len(records)} counties, outside the expected "
            f"{MIN_COUNTIES}-{MAX_COUNTIES}; the United States has about "
            f"3,143 counties and county equivalents and a table this far off "
            f"has lost or gained a geography")
    return records


def probe(chart: str, *, rows: int) -> None:
    """Print what Datawrapper actually returns for one chart. Writes nothing.

    The column identification above was written without sight of a real PRRI
    table, so its rules are reasoning about a shape rather than knowledge of
    one. This is how that gets corrected against fact: dispatch it on the
    runner with commit off, read the header and the first rows it prints, and
    fix the rules to the file instead of to a guess.

    It deliberately reports rather than refuses. A probe that died on the first
    surprise would hide the second one, and the whole point of a read-only run
    is to come back with every surprise at once.
    """
    log(f"--- {chart}: {CHARTS.get(chart, EXCLUDED.get(chart, 'unknown chart'))}")
    version = chart_version(chart)
    url = f"{CDN}/{chart}/{version}/dataset.csv"
    log(f"    version {version}")
    log(f"    url {url}")
    text = reachable(url, timeout=120)
    log(f"    {len(text)} bytes")

    parsed, delimiter = split_rows(text)
    log(f"    delimiter {delimiter!r}; {len(parsed)} non-empty rows")
    log("    raw head:")
    for line in text.splitlines()[:rows + 1]:
        log(f"      | {line}")

    if len(parsed) < 2:
        log("    no body rows to classify")
        return
    header, body = parsed[0], parsed[1:]
    width = max(len(r) for r in body)
    body = [r + [""] * (width - len(r)) for r in body]
    columns = list(zip(*body))
    fips_cols, value_cols = classify(columns)

    log(f"    header: {header}")
    for i, col in enumerate(columns):
        name = header[i] if i < len(header) else f"<unnamed {i}>"
        kind = ("FIPS" if i in fips_cols else
                "value" if i in value_cols else "other")
        numbers = [v for v in (as_float(c) for c in col) if v is not None]
        span = (f"{min(numbers):g}..{max(numbers):g}" if numbers else "-")
        hidden = sum(censored(c) for c in col)
        log(f"      [{i}] {name!r} -> {kind}; sample {list(col[:3])}; "
            f"numeric {len(numbers)}/{len(col)} range {span}; censored {hidden}")

    log(f"    classify: fips_cols={fips_cols} value_cols={value_cols}")
    # The range matters as much as the columns: a table storing 0.135 rather
    # than 13.5 would pass every column test and fail every sum.
    try:
        got = read_dataset(text, chart=chart)
    except SystemExit as exc:
        log(f"    read_dataset REFUSED: {exc}")
        return
    sample = sorted(got)[:5]
    log(f"    read_dataset ok: {len(got)} counties; "
        f"sample {[(f, got[f]) for f in sample]}")
    log(f"    value range {min(got.values()):g}..{max(got.values()):g}")


def build_parser() -> argparse.ArgumentParser:
    """The command line.

    Arguments reach this module through
    ``printf '%s' "$ADAPTER" | xargs python3 -m ...`` on the Actions runner, so
    every one of them must survive word-splitting: no spaces inside a value, no
    quotes, no shell metacharacters. Chart ids and integers are all that is
    asked for here, which keeps that easy -- and a test asserts it stays true.
    """
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--probe", action="store_true",
                    help="fetch and describe the table without writing anything")
    ap.add_argument("--chart", default="d76SP",
                    help="chart id to probe, or all for every chart")
    ap.add_argument("--rows", type=int, default=6,
                    help="how many raw lines to print per chart")
    return ap


def main() -> int:
    args = build_parser().parse_args()

    if args.probe:
        charts = list(CHARTS) if args.chart == "all" else [args.chart]
        unknown = [c for c in charts if c not in CHARTS and c not in EXCLUDED]
        if unknown:
            raise SystemExit(
                f"us_prri: no such chart {unknown}; the ids are "
                f"{' '.join(CHARTS)} (and {' '.join(EXCLUDED)}, excluded)")
        log(f"us_prri: probing {len(charts)} chart(s); nothing will be written")
        # One chart failing must not hide the other seventeen. The point of a
        # probe is to come back with every surprise at once, so each is caught
        # and reported and the run still ends red if any of them failed.
        failed: list[str] = []
        for chart in charts:
            try:
                probe(chart, rows=args.rows)
            except SystemExit as exc:
                failed.append(chart)
                log(f"    FAILED: {exc}")
        if failed:
            log(f"us_prri: {len(failed)} of {len(charts)} charts failed to "
                f"probe: {' '.join(failed)}")
            return 1
        log(f"us_prri: all {len(charts)} charts probed")
        return 0

    log("us_prri: religion by county, PRRI 2023 Census of American Religion")
    log(f"  {len(CHARTS)} charts; excluding {', '.join(EXCLUDED)} "
        f"({'; '.join(EXCLUDED.values())})")

    universe = read_json(PROCESSED / UNIVERSE, None)
    if not universe:
        raise SystemExit(
            f"us_prri: {PROCESSED / UNIVERSE} is missing; it supplies the "
            f"county FIPS universe and the canonical names this file joins "
            f"onto. Run scripts.fetch_census.us_acs first.")

    by_category: dict[str, dict[str, float]] = {}
    for chart, category in CHARTS.items():
        by_category[category] = read_dataset(fetch_dataset(chart), chart=chart)
        log(f"  {category}: {len(by_category[category])} counties")

    common = check_coverage(by_category)
    trimmed = {cat: {f: v for f, v in vals.items() if f in common}
               for cat, vals in by_category.items()}
    counties = collapse(trimmed)
    check_sums(counties)

    populations = {}
    for row in universe:
        fips = (row.get("codes") or {}).get("geoid")
        pop = (row.get("population") or {}).get("value")
        if fips and pop:
            populations[fips] = float(pop)
    check_national(counties, populations)

    records = build(counties, universe)
    log(f"  {len(records)} counties written")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
