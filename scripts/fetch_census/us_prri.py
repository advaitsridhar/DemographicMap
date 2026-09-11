#!/usr/bin/env python3
"""United States: religion by county, from the PRRI Census of American Religion.

The counties already carry religion, from the 2020 U.S. Religion Census (ASARB)
by way of ``us_acs.py``. That study is a count of *adherents reported by
religious bodies* and it reaches about 48.6% of the population; everyone else --
people who belong to nothing, and members of the bodies that did not file a
return -- is pooled into one "Unaffiliated or not reported" category, because
the study genuinely cannot tell them apart. It is the best congregational count
that exists and it answers a different question from the one this map asks.

PRRI's Census of American Religion answers the map's question. It is
self-identification: adults on Ipsos's KnowledgePanel asked what they are, as
part of the American Values Atlas, modelled down to county level. It covers
100% of the population rather than 48.6%, and it separates the religiously
unaffiliated (27% of Americans) from non-response instead of banking them
together. So where this file matches a county it **replaces** the ASARB
religion figures rather than filling a gap -- every county it touches already
had a religion list -- and because it replaces figures already on the map, the
repository owner reviews the change before it ships.

Two things about it are not a census and the note on every record says so:
these are modelled small-area estimates from a national sample, not a
county-by-county enumeration, and they describe adults, not residents.

**The article says 2023 and the data says 2024.** PRRI titles the report the
2023 Census of American Religion; the published table's own ``year`` column
reads 2024 in every row. The file is what this adapter has, so the file is what
it records -- ``religion_year`` is read out of the data rather than taken from
the title, and the note says both numbers so that nobody has to rediscover the
discrepancy. If a later revision carries a different year, that year is what
lands, and the log says which.

**Where the numbers come from, and what one fetch gets you.** PRRI publishes
the county data as Datawrapper choropleths embedded in the article, one chart
per religious group, and Datawrapper serves each published chart's underlying
table at ``https://datawrapper.dwcdn.net/<id>/<version>/dataset.csv``. The
chart IDs were read out of the saved article page (the ``datawrapper-chart-*``
iframe ids, each beside its own ``title`` attribute).

A probe of the first chart showed the thing that shapes this adapter: **every
chart carries the whole table.** The CSV behind "White Evangelical Protestant"
has all eighteen group columns in it, plus population, FIPS, county name and
the diversity index -- 3,142 rows, one per county. So this fetches one chart,
not eighteen, and then fetches a second and checks the two agree column for
column and county for county. That cross-check is the price of relying on the
observation: if PRRI ever publishes a chart from a different table, the run
stops instead of quietly preferring whichever one it read first.

**Race is dropped, not refiled.** PRRI's categories are race crossed with
religion -- ``white_evangelical_protestant``, ``black_protestant``,
``hispanic_catholic`` -- because the racial split is the finding the report is
about. This map's religion tree is about religion. There is no node for "White
Protestant" and inventing one would put race in the religion tree, where a
reader filtering for Protestantism would then miss four-fifths of American
Protestants. So the five Protestant columns collapse to Protestantism and the
three Catholic ones to Catholicism, and the race detail is *dropped* rather
than misfiled: this file cannot answer "how many Black Protestants are in this
county" and does not pretend to. PRRI's article is the place for that question.

Two categories have no node and are not worth inventing one for. Unitarian
Universalists are 0.5% of Americans and ``other_religion`` is already a
residual; both become "Other religions", which is what that node is for. The
collapse is lossy in one visible way and the note records it.

**The diversity index is not a share.** It appears twice -- as its own chart
``mL9BH`` and as a ``diversity_index`` column in every CSV -- and it is a 0-1
concentration score, not a percentage of anybody. Read as a nineteenth group it
would add half a point to every county and quietly spoil the sums. Both the
chart and the column are named below as excluded, so that a later reader can
see it was considered rather than missed.

**The join is by FIPS and only by FIPS.** County *names* are the classic silent
mis-match here -- there are thirty-odd Washington Counties and a Wilcox in both
Alabama and Georgia -- so the name is never the key. PRRI's FIPS arrive
unpadded (Autauga County, Alabama is ``1001``, not ``01001``), and joining
those against a five-digit key would silently lose every state from 01 to 09,
so they are padded at the reader. The name column ``fips_fct`` is used only as
a check: where PRRI's county name and the map's disagree after normalisation,
that FIPS is refused rather than joined, because a FIPS whose name moved is
usually a FIPS that was reassigned. Connecticut is the live case -- the state
replaced its eight counties with nine planning regions in 2022 -- and a
mismatch there must be reported, not absorbed.

**What the national roll-up is and is not checked against.** PRRI's published
national figures -- 66% Christian, 27% unaffiliated, 6% non-Christian -- are
the article's, for 2023. The table is year 2024, and it is a modelled
small-area estimate rather than the direct survey estimate the article quotes.
The first real run put Christians at 70.1% against that 66% and refused, which
was the check working as designed and reaching the wrong conclusion: the
collapse was right and the comparison was unsound.

The arithmetic says so plainly. Catholicism rolls up to 22.0% against a
published 22%, every non-Christian group lands within 0.2 points, and the whole
deviation is a near-exact transfer of about four points between Protestantism
(+4.7) and the religiously unaffiliated (-3.9). A category filed under the
wrong node moves a whole named quantity cleanly between two nodes and would
disturb Catholicism on the way; this does not. It is a difference of vintage
and method, not of filing.

So the aggregate is reported and not gated. What is gated instead is the thing
that can be checked exactly: ``check_collapse`` compares this adapter's mapping
against the membership PRRI enumerates in its own footnotes, with no tolerance
at all, and catches any category crossing the Christian boundary in either
direction -- including the one-point ones a published-figure tolerance could
never have seen. A published figure the data cannot be expected to reproduce is
not a check; it is a false alarm standing in the way of every future run.

One thing that is *not* in doubt: PRRI counts Latter-day Saints, Jehovah's
Witnesses and Orthodox Christians as Christian. Footnote [1] places all three
inside the 41% who are white Christians and footnote [2] places them inside the
25% who are Christians of color, and 41 + 25 = 66. This map's Christianity
subtree contains them too, so the two definitions agree. It is recorded here
because from a distance it looks like the kind of discrepancy somebody fixes by
moving a tree node.

**A key column is not just a column of numbers.** The probe caught this: the
table's ``year`` column is ``2024`` in every row, which looks exactly like a
county FIPS code to any test that only asks "are these four or five digits
beginning with a valid state prefix". Two further things are true of a key and
false of ``year``: a key takes as many distinct values as there are rows, and a
key is not constant. Both are checked, which is why the column is identified by
name and then *verified* by content rather than sniffed out of the header.

**Running it.** The build sandbox cannot reach ``datawrapper.dwcdn.net`` or
``prri.org`` -- the egress proxy answers 403 to CONNECT, an organisation policy
denial -- which is why ``.github/workflows/run-adapter.yml`` exists: the fetch
runs on an Actions runner with open egress. ``--probe`` fetches without writing
anything and prints the delimiter, header, first rows, per-column
classification and value ranges, which is how the rules above were fixed
against fact rather than guessed.

Arguments reach the runner through ``printf '%s' "$ADAPTER" | xargs python3
-m``, so they must survive word-splitting: no spaces inside a value, no quotes,
no shell metacharacters. Chart ids and integers are all this takes.

Usage:
    python -m scripts.fetch_census.us_prri --probe --chart d76SP
    python -m scripts.fetch_census.us_prri
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import statistics
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, read_json, record, write_json,
)

OUT = "us_prri_county.json"
SOURCE = ("PRRI, Census of American Religion: County-Level Data on Religious "
          "Identity and Diversity (American Values Atlas)")
PAGE = ("https://www.prri.org/research/2023-prri-census-of-american-religion-"
        "county-level-data-on-religious-identity-and-diversity/")
LICENCE = "Copyright PRRI; used with attribution to the published report"

# The county universe and its canonical names. Written by us_acs.py, which is
# the file this one overwrites the religion field of; taking the names and
# parents from there rather than from PRRI is what keeps the two mergeable.
UNIVERSE = "us_county.json"

CDN = "https://datawrapper.dwcdn.net"

# Chart id -> the title PRRI gave it, read from the iframe attributes in the
# saved article. Every one of these serves the same whole table; PRIMARY is the
# one fetched and CROSS_CHECK the one used to prove that claim on each run.
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
PRIMARY = "d76SP"
CROSS_CHECK = "CLuyf"

# Present in the article, deliberately not read: an index, not a share.
EXCLUDED: dict[str, str] = {
    "mL9BH": "The Religious Diversity Index, By County -- a 0-1 concentration "
             "score rather than a percentage of anybody",
}

# The table's own column names, as the probe found them.
KEY_COLUMN = "fipsstcnty"          # 1001, unpadded
NAME_COLUMN = "fips_fct"           # "Autauga County, AL"
POPULATION_COLUMN = "Population"
YEAR_COLUMN = "year"
DIVERSITY_COLUMN = "diversity_index"

# CSV column -> the category PRRI titles the matching chart with. Identified by
# name because the header is now known fact; a column that vanishes or is
# renamed stops the run rather than being skipped.
COLUMNS: dict[str, str] = {
    "white_evangelical_protestant": "White Evangelical Protestant",
    "white_mainline_protestant": "White Mainline/Non-evangelical Protestant",
    "black_protestant": "Black Protestant",
    "hispanic_protestant": "Hispanic Protestant",
    "other_protestant": "Other Protestant of Color",
    "white_catholic": "White Catholic",
    "hispanic_catholic": "Hispanic Catholic",
    "other_catholic": "Other Catholic of Color",
    "mormon": "Latter-day Saint (Mormon)",
    "orthodox_christian": "Orthodox Christian",
    "jehovahs_witness": "Jehovah's Witness",
    "jewish": "Jewish",
    "muslim": "Muslim",
    "buddhist": "Buddhist",
    "hindu": "Hindu",
    "unitarian_universalist": "Unitarian Universalist",
    "other_religion": "Other Non-Christian Religious",
    "unaffiliated": "Religiously Unaffiliated",
}

# Columns that are real and deliberately not religion shares.
STRUCTURAL = {KEY_COLUMN, NAME_COLUMN, POPULATION_COLUMN, YEAR_COLUMN,
              DIVERSITY_COLUMN}

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

# The national figures PRRI states in the article's own opening paragraph:
#
#   "Two-thirds of Americans (66%) identify as Christian ... Over one-quarter
#   of Americans (27%) are religiously unaffiliated, and 6% belong to a
#   non-Christian religion."
#
# These three are used rather than the eighteen group figures because they are
# the numbers PRRI writes as single published values; the group shares in the
# footnotes are rounded to whole percents and summing five of them to check
# Protestantism would be checking the rounding as much as the data. Note they
# sum to 99, not 100, which is why none of the tolerances here are hairline.
NATIONAL: dict[str, float] = {
    "Christian": 66.0,
    "No religion": 27.0,
    "Non-Christian": 6.0,
}

# Which of PRRI's own categories its "Christian" aggregate contains. This is
# not a judgement call; the article's first two footnotes enumerate it.
#
#   "[1] Among the 41% of Americans who identify as white Christians, 13% are
#   white evangelical Protestants, 13% are white mainline/non-evangelical
#   Protestants, 12% are white Catholics, and small percentages identify as
#   Latter-day Saints (1%), Jehovah's Witnesses (<0.5%), or Orthodox
#   Christians (<0.5%). [2] Among the one-quarter of Americans who identify as
#   Christians of color (25%), one in ten are Black Protestants (8%) and
#   Hispanic Catholics (8%), 4% are Hispanic Protestants, 2% are other
#   Protestants of color, 2% are other Catholics of color, and just 1% are
#   Jehovah's Witnesses, Latter-day Saints, or Orthodox Christians."
#
# 41 + 25 = 66, and Latter-day Saints, Jehovah's Witnesses and Orthodox
# Christians sit inside both halves. So PRRI's 66% counts them as Christian and
# so does this map's Christianity subtree: the two agree. Worth stating,
# because from a distance it looks like the kind of discrepancy somebody fixes
# by moving a tree node.
CHRISTIAN_CATEGORIES = {
    "White Evangelical Protestant", "White Mainline/Non-evangelical Protestant",
    "White Catholic", "Black Protestant", "Hispanic Catholic",
    "Hispanic Protestant", "Other Protestant of Color", "Other Catholic of Color",
    "Latter-day Saint (Mormon)", "Jehovah's Witness", "Orthodox Christian",
}
CHRISTIAN = {"Protestantism", "Catholicism", "Orthodoxy", "Latter-day Saints",
             "Jehovah's Witnesses"}

# Per-category national figures from the same three footnotes, for the ones the
# article states individually. Latter-day Saints, Jehovah's Witnesses, Orthodox
# Christians and other non-Christian religions are given only as "<0.5%" or
# pooled into "just 1%", so there is no figure to compare them against and they
# are deliberately absent rather than guessed at.
PUBLISHED_CATEGORY: dict[str, float] = {
    "White Evangelical Protestant": 13.0,
    "White Mainline/Non-evangelical Protestant": 13.0,
    "White Catholic": 12.0,
    "Black Protestant": 8.0,
    "Hispanic Catholic": 8.0,
    "Hispanic Protestant": 4.0,
    "Other Protestant of Color": 2.0,
    "Other Catholic of Color": 2.0,
    "Jewish": 2.0,
    "Muslim": 1.0,
    "Buddhist": 1.0,
    "Hindu": 1.0,
    "Unitarian Universalist": 0.5,
    "Religiously Unaffiliated": 27.0,
}

# Bands wide enough that a year of vintage drift cannot trip them and narrow
# enough that a gross mis-collapse must. Centred on PRRI's published 66/27/6:
# filing Catholicism as a non-Christian religion would put the non-Christian
# share at 28% and the Christian share at 48%, and both would stop the run.
# A sanity floor, not a validation of the figures -- the exact check on the
# collapse is check_collapse, which needs no tolerance at all.
SANITY: dict[str, tuple[float, float]] = {
    "Christian": (50.0, 80.0),
    "No religion": (15.0, 40.0),
    "Non-Christian": (2.0, 15.0),
}

# How far a county's eighteen shares may sit from 100 before the run stops.
# The real table is close: Autauga sums to 100.2, Bullock to 100.0. Eighteen
# values each rounded to one decimal can drift 0.9 on rounding alone, and PRRI
# fits each group's small-area model separately rather than constraining the
# eighteen to sum, so exact closure is not expected. Five points is the band
# that still catches the failure this guards against -- a column read twice or
# not at all -- while leaving the published rounding alone.
SUM_TOLERANCE = 5.0
# The per-county band above is deliberately loose, so it would not notice one
# missing column in a county where that group is tiny. This one would: across
# three thousand counties the typical miss should be rounding-sized, and a
# systematically absent column drags the median straight off zero.
MEDIAN_SUM_TOLERANCE = 1.5

# The national roll-up is weighted by the table's own Population column, which
# is PRRI's own denominator and so the right weight for PRRI's own shares.
# There is deliberately no published-figure tolerance here any more: the
# roll-up is checked against SANITY above, and the mapping itself is checked
# exactly by check_collapse. See check_national for why a tolerance against a
# published aggregate was the wrong instrument.

# US counties and county equivalents. The probe found 3,142 rows; the expected
# range is stated rather than inferred so that a table which quietly lost a
# state fails here.
MIN_COUNTIES = 3_000
MAX_COUNTIES = 3_200

# Below this share of PRRI's rows finding a home, the join itself is wrong and
# reporting "some counties unmatched" would understate it.
MIN_JOIN_RATE = 0.95

# PRRI's Population is smaller than the ACS resident count for the same county
# -- 44,335 against about 59,800 for Autauga -- which is what an adult (18+)
# base looks like, and adults are who PRRI asked. A median ratio outside this
# band means the column is not the denominator it appears to be.
POPULATION_RATIO = (0.55, 1.02)

# The two-digit prefixes a real county FIPS can start with: the 50 states and
# DC run 01-56 with gaps, and the territories sit in the 60s and 70s.
STATE_PREFIXES = ({f"{n:02d}" for n in range(1, 57)}
                  | {"60", "66", "68", "69", "70", "72", "74", "78"})

# Datawrapper writes whatever the chart's author uploaded. The real file is
# comma-separated, but reading a tab-separated one with the comma reader yields
# a single fused column and a confusing refusal further down.
DELIMITERS = (",", "\t", ";", "|")


def normalise(name: str) -> str:
    """A county name reduced to the part two sources have to agree on.

    PRRI writes "Autauga County, AL" and the map writes "Autauga County,
    Alabama"; 'Doña Ana' and 'Dona Ana' are the same place too. Only ever used
    to decide whether a name *disagrees* with the one already on the map --
    never to make a join.
    """
    name = name.split(",")[0]
    name = name.replace("ñ", "n").replace("Ñ", "N")
    name = re.sub(r"\b(County|Parish|Borough|Census Area|Municipality|City and "
                  r"Borough|Municipio|Planning Region)\b", " ", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def reachable(url: str, *, timeout: int) -> str:
    """GET, turning an unreachable CDN into a refusal that says what to do.

    On the build sandbox the egress proxy answers 403 to CONNECT for
    datawrapper.dwcdn.net and prri.org alike, which is an organisation policy
    denial and not something to retry around; the fetch belongs on the runner.
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
    if isinstance(page, bytes):
        page = page.decode("utf-8-sig", "replace")
    return page


def chart_version(chart: str) -> int:
    """The version integer Datawrapper is currently publishing for a chart.

    The published page references its own assets by version, so the number is
    in the HTML; guessing it would mean fetching a stale table or 404ing on a
    chart revised more times than the guess. The first chart probed was at
    version 7, which is why this is read rather than assumed to be 1.
    """
    page = reachable(f"{CDN}/{chart}/", timeout=60)
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
    log(f"  {chart} v{version}: {url}")
    return reachable(url, timeout=120)


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
        return ([r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)],
                ",")
    return best


def as_float(cell: str) -> float | None:
    """A cell as a number, or None if it is not one."""
    cell = (cell or "").strip().rstrip("%").replace(",", "").replace("−", "-")
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def censored(cell: str) -> bool:
    """A cell PRRI deliberately did not give precisely, e.g. '<0.5'.

    The real table censors nothing, which is worth knowing rather than
    assuming: this stays so that a later revision which does censor stops the
    run instead of being read as zero.
    """
    return bool(re.match(r"^\s*[<>]\s*\d", cell or ""))


def looks_like_key(values: list[str]) -> tuple[bool, str]:
    """Is this column a county FIPS key? Returns the verdict and why.

    Being four or five digits with a valid state prefix is not enough on its
    own: the table's ``year`` column is 2024 in every row and passes that test,
    because "20" is Kansas. A key is also distinct in every row and takes more
    than one value, and ``year`` fails both.
    """
    values = [v.strip() for v in values]
    if not values:
        return False, "empty"
    digits = [v for v in values if re.fullmatch(r"\d{4,5}", v)]
    if len(digits) < 0.99 * len(values):
        return False, f"only {len(digits)}/{len(values)} are 4-5 digit numbers"
    prefixed = [v for v in digits if v.zfill(5)[:2] in STATE_PREFIXES]
    if len(prefixed) < 0.99 * len(values):
        return False, f"only {len(prefixed)}/{len(values)} carry a state prefix"
    distinct = len(set(values))
    if distinct == 1:
        return False, f"constant ({values[0]}) -- a key is not one value"
    if distinct != len(values):
        seen: set[str] = set()
        repeated = sorted({v for v in values if v in seen or seen.add(v)})
        return False, (f"{distinct} distinct values in {len(values)} rows; "
                       f"repeated twice or more: {repeated[:5]}")
    return True, f"{distinct} distinct 5-digit codes"


def read_table(text: str, *, chart: str) -> tuple[dict[str, dict[str, Any]], int]:
    """One chart's CSV -> ({FIPS: {name, population, shares}}, data year).

    Every chart serves the same whole table, so this reads all eighteen group
    columns at once. The columns are named rather than sniffed -- the header is
    known fact now -- and then verified, because a header that has been
    reshuffled or renamed is exactly the change that must stop a run rather
    than quietly shift which column is read as which religion.
    """
    rows, _ = split_rows(text)
    if len(rows) < 2:
        raise SystemExit(f"us_prri: chart {chart} returned no rows")
    header = [h.strip() for h in rows[0]]
    body = [r + [""] * (len(header) - len(r)) for r in rows[1:]]

    missing = sorted((set(COLUMNS) | STRUCTURAL) - set(header))
    if missing:
        raise SystemExit(
            f"us_prri: chart {chart} is missing the columns {missing} "
            f"(header {header}); PRRI has changed the table and the mapping "
            f"has to be redone by hand rather than part-applied")
    unknown = sorted(set(header) - set(COLUMNS) - STRUCTURAL)
    if unknown:
        raise SystemExit(
            f"us_prri: chart {chart} has columns this adapter has not decided "
            f"about: {unknown}. If one is a new religious group it must be "
            f"mapped, and if it is not it must be named as structural -- "
            f"either way, not silently dropped.")

    index = {name: i for i, name in enumerate(header)}
    columns = {name: [r[i] for r in body] for name, i in index.items()}

    ok, why = looks_like_key(columns[KEY_COLUMN])
    if not ok:
        raise SystemExit(
            f"us_prri: chart {chart} column {KEY_COLUMN!r} is not a county key "
            f"({why}); joining on it would be a guess")

    years = {v.strip() for v in columns[YEAR_COLUMN] if v.strip()}
    if len(years) != 1:
        raise SystemExit(
            f"us_prri: chart {chart} mixes data years {sorted(years)}; a "
            f"single religion_year cannot describe it")
    year = as_float(years.pop())
    if year is None or not 1990 <= year <= 2100:
        raise SystemExit(f"us_prri: chart {chart} has an implausible year")

    hidden = sum(censored(cell) for name in COLUMNS for cell in columns[name])
    if hidden:
        raise SystemExit(
            f"us_prri: chart {chart} censors {hidden} values with a '<' or "
            f"'>'. Treating those as zero would understate the group and leave "
            f"the county short of 100; decide what they should become and say "
            f"so in the note before running this again.")

    counties: dict[str, dict[str, Any]] = {}
    for row_no, row in enumerate(body):
        # PRRI writes Autauga County, Alabama as 1001. Unpadded codes joined
        # against a 5-digit key lose every state from 01 to 09 in silence.
        fips = row[index[KEY_COLUMN]].strip().zfill(5)
        if fips in counties:
            raise SystemExit(
                f"us_prri: chart {chart} lists FIPS {fips} twice; a duplicated "
                f"county would be counted twice in the national roll-up")
        population = as_float(row[index[POPULATION_COLUMN]])
        shares: dict[str, float] = {}
        for column, category in COLUMNS.items():
            value = as_float(row[index[column]])
            if value is None:
                raise SystemExit(
                    f"us_prri: chart {chart} row {row_no + 2} has no number in "
                    f"{column!r} for FIPS {fips}; a blank share is not a zero "
                    f"and must not be read as one")
            shares[category] = value
        counties[fips] = {"name": row[index[NAME_COLUMN]].strip(),
                          "population": population, "shares": shares}
    if not counties:
        raise SystemExit(f"us_prri: chart {chart} yielded no usable rows")
    return counties, int(year)


def cross_check(primary: dict[str, dict[str, Any]],
                other: dict[str, dict[str, Any]], *, chart: str) -> None:
    """Prove that a second chart serves the same table as the first.

    The whole adapter rests on one observation -- that every chart carries all
    eighteen columns -- and an observation made once is worth re-making on
    every run. If PRRI ever publishes a chart from a different table, this is
    what stops the run instead of quietly preferring whichever was read first.
    """
    if set(primary) != set(other):
        only_primary = sorted(set(primary) - set(other))[:5]
        only_other = sorted(set(other) - set(primary))[:5]
        raise SystemExit(
            f"us_prri: chart {chart} covers different counties from "
            f"{PRIMARY} (only in {PRIMARY}: {only_primary}; only in {chart}: "
            f"{only_other}); the charts are not one table")
    for fips, row in primary.items():
        if row["shares"] != other[fips]["shares"]:
            differing = sorted(k for k, v in row["shares"].items()
                               if other[fips]["shares"].get(k) != v)
            raise SystemExit(
                f"us_prri: chart {chart} disagrees with {PRIMARY} for FIPS "
                f"{fips} on {differing}; the charts are not one table and "
                f"which is right cannot be decided here")
    log(f"  cross-check: {chart} matches {PRIMARY} across {len(primary)} counties")


def collapse(counties: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    """{FIPS: {..., shares}} -> {FIPS: {religion node: pct}}.

    Every category must be one this adapter has decided about. A nineteenth
    group appearing in a later PRRI release would otherwise be silently
    dropped, which is the failure mode the whole file is written against.
    """
    seen = {cat for row in counties.values() for cat in row["shares"]}
    unknown = sorted(seen - set(COLLAPSE))
    if unknown:
        raise SystemExit(
            f"us_prri: no religion node decided for {unknown}; PRRI has added "
            f"a category and it must be mapped by hand, not defaulted")

    out: dict[str, dict[str, float]] = {}
    for fips, row in counties.items():
        nodes: dict[str, float] = {}
        for category, pct in row["shares"].items():
            node = COLLAPSE[category]
            nodes[node] = nodes.get(node, 0.0) + pct
        out[fips] = nodes
    return out


def check_sums(counties: dict[str, dict[str, float]],
               names: dict[str, str] | None = None) -> None:
    """Each county's shares must account for its whole adult population.

    The worst few are named, not just counted. The first real run came back
    with a worst county 4.7 points from 100 against a median of 0.1, which is
    inside the band but is not nothing: one county behaving unlike the other
    three thousand is either a real outlier in PRRI's model or a row read
    oddly, and those look identical in a summary statistic.
    """
    misses = sorted(((abs(sum(groups.values()) - 100.0), fips)
                     for fips, groups in counties.items()), reverse=True)
    worst, worst_fips = misses[0]
    median = misses[len(misses) // 2][0]
    names = names or {}
    # Diagnostics before the refusals, so a run that stops still says which
    # counties it stopped on.
    log(f"  sums: worst county {worst:.1f}pp from 100, median {median:.1f}pp")
    log("    furthest from 100 -- " + "; ".join(
        f"{fips} {names.get(fips, '?')} {sum(counties[fips].values()):.1f}%"
        for _, fips in misses[:5]))
    if worst > SUM_TOLERANCE:
        raise SystemExit(
            f"us_prri: county {worst_fips} sums to "
            f"{sum(counties[worst_fips].values()):.1f}%, {worst:.1f} points "
            f"from 100 against a tolerance of {SUM_TOLERANCE}; a column is "
            f"missing, duplicated, or is not a percentage")
    if median > MEDIAN_SUM_TOLERANCE:
        raise SystemExit(
            f"us_prri: the typical county is {median:.1f} points from 100 "
            f"(tolerance {MEDIAN_SUM_TOLERANCE}); that is a systematic gap, "
            f"not rounding -- one of the eighteen columns is absent")


def check_collapse() -> None:
    """PRRI's Christian categories must land in this map's Christian nodes.

    This replaced a numeric check and is strictly the stronger of the two.
    Comparing a national roll-up against a published aggregate can only notice
    a mis-collapse big enough to move the total further than the tolerance, so
    it was blind to a one-point category going astray and, worse, it could be
    silenced by widening the band. This compares the mapping itself against the
    membership PRRI enumerates in its own footnotes: exact, no tolerance,
    indifferent to what vintage the data is, and it catches every crossing of
    the Christian boundary in either direction.
    """
    misfiled = sorted(c for c in CHRISTIAN_CATEGORIES if COLLAPSE[c] not in CHRISTIAN)
    if misfiled:
        raise SystemExit(
            f"us_prri: PRRI counts {misfiled} as Christian (article footnotes "
            f"1 and 2) but this adapter collapses them outside the Christian "
            f"nodes {sorted(CHRISTIAN)}; the roll-up would understate "
            f"Christianity and the map would file those people wrongly")
    leaked = sorted(c for c, node in COLLAPSE.items()
                    if node in CHRISTIAN and c not in CHRISTIAN_CATEGORIES)
    if leaked:
        raise SystemExit(
            f"us_prri: {leaked} collapse into a Christian node but PRRI does "
            f"not count them as Christian; the roll-up would overstate "
            f"Christianity")
    missing = sorted(CHRISTIAN - {COLLAPSE[c] for c in CHRISTIAN_CATEGORIES})
    if missing:
        raise SystemExit(
            f"us_prri: the Christian nodes {missing} receive no PRRI category, "
            f"so CHRISTIAN names something this table cannot fill")
    log(f"  collapse: PRRI's {len(CHRISTIAN_CATEGORIES)} Christian categories "
        f"all land in {sorted(CHRISTIAN)}")


def national(values: dict[str, dict[str, float]],
             populations: dict[str, float]) -> dict[str, float]:
    """Population-weighted national shares of whatever is keyed by county."""
    weighted: dict[str, float] = {}
    total = 0.0
    for fips, groups in values.items():
        pop = populations.get(fips)
        if not pop:
            continue
        total += pop
        for key, pct in groups.items():
            weighted[key] = weighted.get(key, 0.0) + pct * pop
    if not total:
        raise SystemExit(
            "us_prri: no county carried a population, so the national roll-up "
            "cannot be weighted and nothing can be compared against it")
    return {key: value / total for key, value in weighted.items()}


def check_national(shares: dict[str, dict[str, float]],
                   nodes: dict[str, dict[str, float]],
                   populations: dict[str, float]) -> None:
    """Report the national roll-up, and refuse only what is genuinely wrong.

    **Why this does not gate on PRRI's published 66/27/6.** It used to, and the
    first real run refused: the roll-up put Christians at 70.1% against a
    published 66%. That gap is not a mis-collapse. Catholicism rolls up to
    22.0% against a published 22%, every non-Christian group lands within 0.2
    points, and the entire deviation is a near-exact transfer of about four
    points between Protestantism (+4.7) and the religiously unaffiliated
    (-3.9). A category filed under the wrong node moves a whole named quantity
    -- 2, 4, 8 or 12 points -- cleanly from one node to another, and would
    disturb Catholicism on the way. This does not.

    What it is instead is a mismatch of vintage and method. The published
    figures are the article's, for 2023; the table's own year column says 2024,
    and it is a modelled small-area estimate rather than the direct survey
    estimate the article quotes. A 2023 headline cannot validate a 2024 model
    to within two and a half points, and pretending otherwise would leave a
    permanent false alarm in front of every future run.

    The honest response is not to widen the band until the gap fits, which
    would disarm the check for the very thing it was meant to catch. It is to
    check the mapping exactly where that is possible -- check_collapse does
    that, against PRRI's own enumeration -- and here to report the comparison
    in full while refusing only on bands no vintage drift could reach.
    """
    by_category = national(shares, populations)
    by_node = national(nodes, populations)

    log("  national roll-up by node: " + ", ".join(
        f"{k} {v:.1f}%" for k, v in sorted(by_node.items(), key=lambda kv: -kv[1])))
    log("  against PRRI's published 2023 figures (the data year may differ, so "
        "a difference here is not by itself an error):")
    for category, published in sorted(PUBLISHED_CATEGORY.items(),
                                      key=lambda kv: -kv[1]):
        got = by_category.get(category)
        if got is None:
            continue
        log(f"      {category:44} {got:5.1f}%  published {published:4.1f}  "
            f"{got - published:+5.1f}")
    unpublished = sorted(set(by_category) - set(PUBLISHED_CATEGORY))
    log(f"      (no published figure for {unpublished}; the article gives "
        f"those only as '<0.5%' or pooled)")

    rolled = {
        "Christian": sum(v for k, v in by_node.items() if k in CHRISTIAN),
        "No religion": by_node.get("No religion", 0.0),
        "Non-Christian": sum(v for k, v in by_node.items()
                             if k not in CHRISTIAN and k != "No religion"),
    }
    log("  aggregates: " + ", ".join(
        f"{k} {rolled[k]:.1f}% (2023 published {v:.0f}%)"
        for k, v in NATIONAL.items()))

    for label, (low, high) in SANITY.items():
        got = rolled[label]
        if not low <= got <= high:
            raise SystemExit(
                f"us_prri: the county roll-up puts {label} at {got:.1f}%, "
                f"outside the sanity band {low}-{high}. That is far past what "
                f"a difference of vintage could explain, so the categories are "
                f"not being collapsed into the right nodes -- read the per-node "
                f"roll-up logged above to see which one moved.")


def check_population(counties: dict[str, dict[str, Any]],
                     universe: list[dict[str, Any]]) -> None:
    """PRRI's denominator should look like the adults inside the ACS count.

    Not a hard identity -- the two are different vintages and different
    universes -- but a column that is not the denominator it appears to be
    would show up here as a ratio nowhere near one.
    """
    acs = {(row.get("codes") or {}).get("geoid"): (row.get("population") or {}).get("value")
           for row in universe}
    ratios = [counties[f]["population"] / acs[f]
              for f in counties
              if acs.get(f) and counties[f].get("population")]
    if not ratios:
        log("  population: no county could be compared with the ACS count")
        return
    median = statistics.median(ratios)
    low, high = POPULATION_RATIO
    if not low <= median <= high:
        raise SystemExit(
            f"us_prri: PRRI's Population is a median {median:.2f} of the ACS "
            f"resident count, outside the expected {low}-{high}; it is not the "
            f"adult denominator it was taken for, and weighting the national "
            f"roll-up by it would be wrong")
    log(f"  population: median {median:.2f} of the ACS resident count "
        f"(an adult base, as expected)")



# PRRI counties the ACS universe does not carry, and the shape each one is.
#
# The universe this joins onto is the American Community Survey's county list,
# which moved to Connecticut's nine planning regions when the state replaced
# its counties in 2022. The boundary file did not: it still draws the eight
# old counties, and PRRI still reports them. So for Connecticut the *survey*
# and the *shapes* agree with each other and disagree with the universe in
# between, and the join through that universe dropped 3.6 million people.
#
# Declared rather than derived, because inventing a bridge between two county
# vintages is exactly what must not happen here. Every line below is one
# county that PRRI reports, that the boundary file draws under that name, and
# that the ACS list does not mention. Alaska's Valdez-Cordova is the same
# story from a different year: dissolved into Chugach and Copper River in
# 2019, still in PRRI, still drawn by the boundary file.
#
# These are matched by name inside their state rather than by FIPS, which is
# what the build's own matcher does for every other country.
OUTSIDE_UNIVERSE: dict[str, tuple[str, str]] = {
    "09001": ("Fairfield", "Connecticut"),
    "09003": ("Hartford", "Connecticut"),
    "09005": ("Litchfield", "Connecticut"),
    "09007": ("Middlesex", "Connecticut"),
    "09009": ("New Haven", "Connecticut"),
    "09011": ("New London", "Connecticut"),
    "09013": ("Tolland", "Connecticut"),
    "09015": ("Windham", "Connecticut"),
    "02261": ("Valdez-Cordova", "Alaska"),
}

def build(counties: dict[str, dict[str, float]],
          universe: list[dict[str, Any]],
          *, year: int,
          prri_names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Join PRRI's counties onto the map's, by FIPS, and refuse what will not join."""
    by_fips = {(row.get("codes") or {}).get("geoid"): row for row in universe}
    by_fips.pop(None, None)

    records: list[dict[str, Any]] = []
    unmatched: list[str] = []
    renamed: list[str] = []
    declared: list[str] = []
    for fips in sorted(counties):
        home = by_fips.get(fips)
        if home is None and fips in OUTSIDE_UNIVERSE:
            shape, state = OUTSIDE_UNIVERSE[fips]
            home = {"name": shape, "parent": "USA", "parent_name": state,
                    "codes": {"geoid": fips}}
            declared.append(f"{shape}, {state}")
        if home is None:
            unmatched.append(fips)
            continue
        if prri_names and fips in prri_names and fips not in OUTSIDE_UNIVERSE:
            if normalise(prri_names[fips]) != normalise(home.get("name", "")):
                renamed.append(f"{fips} PRRI {prri_names[fips]!r} "
                               f"vs map {home.get('name')!r}")
                continue
        rows = [{"group": node, "pct": round(pct, 1)}
                for node, pct in sorted(counties[fips].items(),
                                        key=lambda kv: (-kv[1], kv[0]))
                if round(pct, 1) > 0]
        records.append(record(
            f"USA-{fips}", home["name"],
            level="admin2", parent=home.get("parent", "USA"), country="USA",
            codes=home.get("codes"),
            parent_name=home.get("parent_name"),
            religion=rows or gap(NOT_AVAILABLE),
            religion_year=year,
            religion_basis="self-identification",
            religion_note=(
                f"{SOURCE}, published as the 2023 PRRI Census of American "
                f"Religion; the released table's own year column reads {year}, "
                f"which is the year recorded here. Self-reported religious "
                f"identity among adults, modelled to county level from a "
                f"national random sample of 40,000 adults on Ipsos's "
                f"KnowledgePanel (national margin of error +/-0.7 points); "
                f"these are small-area estimates, not an enumeration, and they "
                f"describe adults rather than all residents. Replaces the 2020 "
                f"U.S. Religion Census adherent counts this county carried, "
                f"which reached about 48.6% of the population and could not "
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
    if declared:
        log(f"  {len(declared)} counties the ACS universe does not carry, "
            f"matched to the shape the boundary file draws: "
            f"{', '.join(declared)}")
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

    It deliberately reports rather than refuses. A probe that died on the first
    surprise would hide the second one, and the whole point of a read-only run
    is to come back with every surprise at once.
    """
    log(f"--- {chart}: {CHARTS.get(chart, EXCLUDED.get(chart, 'unknown chart'))}")
    text = fetch_dataset(chart)
    log(f"    {len(text)} bytes")

    parsed, delimiter = split_rows(text)
    log(f"    delimiter {delimiter!r}; {len(parsed)} non-empty rows")
    log("    raw head:")
    for line in text.splitlines()[:rows + 1]:
        log(f"      | {line}")

    if len(parsed) < 2:
        log("    no body rows to classify")
        return
    header = [h.strip() for h in parsed[0]]
    body = [r + [""] * (len(header) - len(r)) for r in parsed[1:]]
    log(f"    header: {header}")
    for i, name in enumerate(header):
        col = [r[i] for r in body]
        numbers = [v for v in (as_float(c) for c in col) if v is not None]
        span = f"{min(numbers):g}..{max(numbers):g}" if numbers else "-"
        key_ok, why = looks_like_key(col)
        role = ("group" if name in COLUMNS else
                "structural" if name in STRUCTURAL else "UNKNOWN")
        log(f"      [{i}] {name!r} -> {role}; sample {col[:3]}; "
            f"numeric {len(numbers)}/{len(col)} range {span}; "
            f"censored {sum(censored(c) for c in col)}; "
            f"key={'yes' if key_ok else 'no'} ({why})")

    try:
        counties, year = read_table(text, chart=chart)
    except SystemExit as exc:
        log(f"    read_table REFUSED: {exc}")
        return
    sample = sorted(counties)[:3]
    log(f"    read_table ok: {len(counties)} counties, year {year}")
    for fips in sample:
        row = counties[fips]
        total = sum(row["shares"].values())
        log(f"      {fips} {row['name']!r} pop {row['population']:.0f} "
            f"shares sum {total:.1f}")


def build_parser() -> argparse.ArgumentParser:
    """The command line.

    Arguments reach this module through
    ``printf '%s' "$ADAPTER" | xargs python3 -m ...`` on the Actions runner, so
    every one of them must survive word-splitting: no spaces inside a value, no
    quotes, no shell metacharacters. Chart ids and integers are all that is
    asked for here, and a test asserts it stays true.
    """
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--probe", action="store_true",
                    help="fetch and describe the table without writing anything")
    ap.add_argument("--chart", default=PRIMARY,
                    help="chart id to read or probe, or all to probe every one")
    ap.add_argument("--cross-check", default=CROSS_CHECK, dest="cross_check",
                    help="second chart id proving the tables agree, or none")
    ap.add_argument("--rows", type=int, default=6,
                    help="how many raw lines to print per chart when probing")
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

    if args.chart not in CHARTS:
        raise SystemExit(f"us_prri: no such chart {args.chart!r}; the ids are "
                         f"{' '.join(CHARTS)}")
    log("us_prri: religion by county, PRRI Census of American Religion")
    log(f"  excluding {' '.join(EXCLUDED)} and the {DIVERSITY_COLUMN} column "
        f"({'; '.join(EXCLUDED.values())})")

    universe = read_json(PROCESSED / UNIVERSE, None)
    if not universe:
        raise SystemExit(
            f"us_prri: {PROCESSED / UNIVERSE} is missing; it supplies the "
            f"county FIPS universe and the canonical names this file joins "
            f"onto. Run scripts.fetch_census.us_acs first.")

    counties, year = read_table(fetch_dataset(args.chart), chart=args.chart)
    log(f"  {len(counties)} counties, data year {year}")

    if args.cross_check and args.cross_check != "none":
        if args.cross_check not in CHARTS:
            raise SystemExit(f"us_prri: no such chart {args.cross_check!r} to "
                             f"cross-check against")
        other, other_year = read_table(fetch_dataset(args.cross_check),
                                       chart=args.cross_check)
        if other_year != year:
            raise SystemExit(
                f"us_prri: {args.chart} is year {year} and "
                f"{args.cross_check} is year {other_year}; the charts are not "
                f"one table")
        cross_check(counties, other, chart=args.cross_check)
    else:
        log("  cross-check skipped; the one-table claim is untested this run")

    check_collapse()
    check_population(counties, universe)
    nodes = collapse(counties)
    names = {f: r["name"] for f, r in counties.items()}
    check_sums(nodes, names)
    populations = {f: r["population"] for f, r in counties.items()
                   if r.get("population")}
    check_national({f: r["shares"] for f, r in counties.items()},
                   nodes, populations)

    records = build(nodes, universe, year=year,
                    prri_names={f: r["name"] for f, r in counties.items()})
    log(f"  {len(records)} counties written")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
