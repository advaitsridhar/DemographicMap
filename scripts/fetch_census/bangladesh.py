#!/usr/bin/env python3
"""Bangladesh -- Population and Housing Census 2022, religion by zila.

The Bureau of Statistics publishes a workbook of census indicators at admin-2,
one row per zila, and among its forty-two sheets is *Population by Religion,
Sex*: Muslim, Hindu, Christian, Buddhist and Others, each as a total and by
sex, for all sixty-four districts.

**It is read from a mirror, and that is a deliberate choice rather than a
convenience.** None of the office's own hosts can be fetched over a connection
that verifies:

* ``bbs.gov.bd`` has a valid Sectigo certificate that does cover the host, but
  the server never sends its intermediate, so no chain can be built. A browser
  papers over this by fetching the issuer named in the certificate; urllib does
  not -- **and neither did this project when that was written.** It does now:
  ``http_get(aia=True)`` fetches the missing intermediate from the
  certificate's own AIA ``caIssuers`` extension and verifies against it plus
  the public roots, which was measured on the runner as *VERIFIED handshake
  ok, TLSv1.3*. So this host is open, and the census's own National Report is
  read from it rather than from a mirror -- see ``NOT_COLLECTED_POLICY``'s
  Bangladesh entry, which rests on it. The workbook below still comes from
  HDX, which works; swapping a working data path is a change to make on its
  own evidence, not a side effect of this note.
* ``bbs.portal.gov.bd`` answers with a "Kubernetes Ingress Controller Fake
  Certificate" for ``ingress.local``.
* ``file.portal.gov.bd``, ``sid.portal.gov.bd`` and ``portal.gov.bd`` time out.

The alternative to a mirror is disabling certificate verification, which this
project does not do, or recording Bangladesh as uncollectable, which would be
false -- the census exists, is published, and is CC0. HDX carries the release
under the UN in Bangladesh, and the workbook is the office's own.

**The religion table does not count everybody.** Each religion's total is
exactly its male plus its female column, and Bangladesh enumerates a third
gender: Barguna's religions sum to 1,010,461 against a district population of
1,010,531, and the 70 missing are its hijra -- the number the population sheet
prints for Barguna in its own Hijra column. So the shares here are of the
population the religion table classifies, and the note says so. Both figures
are kept -- the district's own population, and the denominator the shares are
of -- because silently using one for the other is how a footnote becomes a
wrong number.

That also makes the check exact rather than approximate: the religions plus
the hijra must equal the published total, to the person, in every district.

**There is no mother tongue here, and that is a fact about the census rather
than about this adapter.** The workbook's forty-two topic sheets run from
dwelling type through religion, disability, literacy, work, banking and ethnic
population to cooking fuel, and not one of them is language. Nor is the
absence the mirror's: the census's own *National Report (Volume I)* describes
the questionnaire as two modules -- 15 household questions and 20 individual
ones, 35 in all -- and lists what the individual module asks (age, sex,
marital status, religion, disability, education, working status, training,
mobile phone and internet use, banking inclusion, ethnic population). Language
is not among them, and none of the report's 520 pages or 33 district tables is
a language table.

**But the census is not the whole of what the Bureau asked.** The *Report on
Socio-Economic and Demographic Survey 2023* (BBS, June 2024, 553 pp, ISBN
978-984-475-268-9) is the long-questionnaire survey run after the census on a
sample of 301,000 households, and is published as one of the five national
reports of the same Population and Housing Census 2021 Project. Its Module 4
collects **mother tongue** by name, beside religion and ethnic population, and
its Table 3.6 publishes it. So "Bangladesh does not collect mother tongue" is
false, and this field said it until the survey report was read.

What the survey publishes still cannot be drawn. Table 3.6 has exactly two
mother-tongue columns, **Bangla and Others**, for the eight divisions: 99.17%
against 0.83% nationally, 97.11% against 2.89% in Chattogram, the highest of
the eight. No mother tongue but Bangla is named anywhere in the report -- a
sweep of all 553 pages for Chakma, Marma, Santal, Garo, Tripura, Mro,
Rakhain, Manipuri, Urdu, Bishnupriya, Tanchangya, Khasi, Hajong, Munda,
Oraon, Rohingya, Bawm, Khumi, Chak, Pankho, Lushai, Koch, Dalu and Rajbanshi
returns zero. A named group against a residual is not a composition, and the
report publishes nothing below the division in any case: its list of tables
names *Division* 66 times and *District* not once, although the survey is
stratified on the 64 districts (64x2 + 12 city corporations = 140 strata) and
its own precision table quotes a district estimate.

So the language field here is ``not_available`` with that reason attached,
from ``NOT_COLLECTED_POLICY`` in ``scripts/common.py`` so the country and its
zilas cannot drift apart. It had been a bare ``not_available``, which on the
map reads as a fetch nobody has run yet; then ``not_collected``, which reads
as a question never put. It is neither: the question was put, answered, and
published in a shape that is not a composition and never reaches the zila --
the same shape as ethnicity two paragraphs down, and marked the same way.

**Ethnicity is asked, counted, and published as one number per district.**
Sheet *Ethnic Population by Sex* (Table P28) gives a district total and its
sex split: 1,650,478 people nationally, 1.00% of the country, but 57.6% of
Rangamati, 48.9% of Khagrachhari and 41.2% of Bandarban -- the three hill
districts -- against 0.01% in Nilphamari. Those shares are of the population
sheet's own district totals, the same denominator the religion check
reconciles against; the workbook's other population sheet differs by a few
hundred people in places, and mixing the two would put a share beside a total
it was not taken from. What it does not give is which
peoples they are. No sheet in the workbook names one; all 445 columns of the
merged table were searched for Chakma, Marma, Santal, Garo, Tripura, Mro,
Tanchangya, Khasi, Manipuri, Rakhain and eleven more, and none appears. The
named groups are published nationally and nowhere lower.

So this field stays a gap and the figure goes in its reason. A single total
and a residual is not a composition: drawn as two slices it would read as a
census that found two ethnicities, and the map would be stating something the
Bureau never said. It had been a bare ``not_available`` with no note at all --
the blank panel that reads as a fetch nobody ran, when the truth is a question
answered and published at a coarser grain than this map draws.

**The named groups are in the National Report, by division.** Table P29,
*Ethnic Population by Category, Sex and Division*, breaks the same 1,650,478
people into **fifty-one named categories** -- the groups scheduled under the
2010 Act -- for each of the eight divisions. Nationally: Chakma 483,365,
Marma 224,299, Tripura 156,620, Saontal 129,056, Oraon 85,858, Garo 76,854,
Munda 60,201, Mro 52,463, Tonchonga 45,974, Barman 44,671, and forty more
down to Vil at 95 and Kol's two people in one division.

It is read alongside Table P28 from the same report, and the two are what make
each other trustworthy: P28 gives which districts belong to which division and
a per-district ethnic total the **workbook states independently**, and P29's
division headers must equal P28's. Four checks, all to the person -- every
block's rows sum to its printed header; the eight divisions sum to the
national header; each category's national figure equals the sum of its eight
divisional ones, which is the table read down as well as across; and the
report's 64 district totals equal the workbook's. Two publications of one
census agreeing is what distinguishes this from a parse that merely did not
crash.

**The shares are of each division's whole population, and that is the whole
argument.** Chattogram's Chakma are 475,548 people: 48% of the division's
ethnic population and **1.4% of the division**. Published the first way, this
map would call Chakma the largest group in Chattogram, where they are one
person in seventy -- the invisible kind of wrong. So the denominator is the
division's own population, summed from the districts the report itself places
in it, and the list legitimately covers only 2.90% of Chattogram and 0.05% of
Barishal. The panel says so; the map declines to name a leader, because the
largest listed group cannot exceed what is unlisted.

Everyone else is **not shown and must not be**. The census publishes the
ethnic categories and no count and no label for anybody else; a slice invented
to fill the bar would be the fabrication the rules forbid.

Forty-seven of the fifty-one categories have no place in this project's group
tree yet, and are published under the census's own spelling rather than
guessed into a family. The tree having no opinion about Bom or Tonchonga is a
fact about the tree; inventing one from a resemblance would be a fact about
nothing.

**The workbook's own merged sheet is not used, because it is wrong.**
``Merged_All_Table`` flattens the forty-two sheets into 445 columns, and in it
Cumilla and Cox's Bazar hold each other's household and population figures --
Cumilla 2,823,268 against a real 6.2 million -- while their district geocodes,
19 and 22, stay correct. Joypurhat and Naogaon are wrong too, and Naogaon's
figure matches neither district, so it is not a clean transposition throughout.
The per-topic sheets it was built from are consistent, and those are read
instead. Nothing here takes the division names from the merged sheet either:
they may well be sound, but a sheet with three known transpositions in it is
not something to take an unverifiable field from.

Usage:
    python -m scripts.fetch_census.bangladesh
"""

from __future__ import annotations

import argparse
import collections
import io
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, collection_gap, gap, http_get, log, measure,
    record, shares, write_json,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import laid_out  # noqa: E402

SOURCE = ("Bangladesh Bureau of Statistics, Population and Housing Census 2022, "
          "district-level indicators")
URL = "https://data.humdata.org/dataset/populationa-and-housing-census-dataset"
LICENCE = "CC0 (public domain), published via HDX by the UN in Bangladesh"
YEAR = 2022

WORKBOOK = ("https://data.humdata.org/dataset/"
            "a6fedebe-72fe-4fc2-8657-1580acfa32c6/resource/"
            "72eaaa6c-6a30-4efd-bad9-02133b316ea8/download/"
            "bangladesh_bbs_population-and-housing-census-dataset_2022_admin-02.xlsx")

# Matched after stripping: the religion sheet's name begins with a space in
# the published file, and a lookup by the name as it reads would miss it.
RELIGION_SHEET = "Population by Religion, Sex"
POPULATION_SHEET = "Population by Sex, Dist & Loca"
ETHNIC_SHEET = "Ethnic Population by Sex"

# Table P28's three columns. The male one carries a stray space before its
# underscore in the published file -- "# Male _Ethnic Population" -- and is
# spelt here exactly as it is there rather than tidied, because a heading this
# code invents is a heading it stops being able to find.
ETHNIC_TOTAL = "# Overall_Ethnic Population"
ETHNIC_SEXED = ("# Male _Ethnic Population", "# Female_Ethnic Population")

# The order they appear in, and the names this map uses for them. "Others" is
# the office's own residual and is kept as one, rather than being dropped or
# guessed at.
RELIGIONS = ["Muslim", "Hindu", "Christian", "Buddhist", "Other religion"]
COLUMNS = {"Muslim": "# Total_Muslim", "Hindu": "# Total_Hindu",
           "Christian": "# Total_Christian", "Buddhist": "# Total_Buddhist",
           "Other religion": "# Total_Others"}
SEXED = {"Muslim": ("# Male_Muslim", "# Female_Muslim"),
         "Hindu": ("# Male_Hindu", "# Female_Hindu"),
         "Christian": ("# Male_Christian", "# Female_Christian"),
         "Buddhist": ("# Male_Buddhist", "# Female_Buddhist"),
         "Other religion": ("# Male_Others", "# Female_Others")}

# What geoBoundaries calls the same zila. Bangladesh respelled several
# districts in English in 2018 -- Chittagong became Chattogram, Comilla became
# Cumilla, Barisal Barishal, Jessore Jashore, Bogra Bogura -- and the boundary
# file still carries the older forms, alongside plain transliteration variants
# for three more. Declared rather than derived: "Nawabganj" and
# "Chapainababganj" share no word, and a rule loose enough to bridge them would
# bridge a great deal else.
ALIASES: dict[str, tuple[str, ...]] = {
    "Barishal": ("Barisal",),
    "Bogura": ("Bogra",),
    "Brahmanbaria": ("Brahamanbaria",),
    "Chapainababganj": ("Nawabganj", "Chapai Nawabganj"),
    "Chattogram": ("Chittagong",),
    "Cumilla": ("Comilla",),
    "Jashore": ("Jessore",),
    "Moulvibazar": ("Maulvibazar",),
}

# The National Report, from the Bureau's own storage rather than a mirror. The
# workbook above stops at a district total; the report is where the fifty-one
# named categories behind that total are, and it is the same census.
REPORT = ("https://objectstorage.ap-dcc-gazipur-1.oraclecloud15.com/n/axvjbnqprylg/"
          "b/V2Ministry/o/office-bbs/2024/12/9ce5bd160bb14a1ab1eabe886adddb9a.pdf")
REPORT_SOURCE = ("Bangladesh Bureau of Statistics, Population and Housing Census 2022, "
                 "National Report (Volume I), Table P29: ethnic population by "
                 "category, sex and division")
REPORT_PAGE = ("https://bbs.gov.bd/site/page/47856ad0-7e1c-4aab-bd78-892733bc06eb/"
               "Population-and-Housing-Census")

# Both tables are laid out the same way: a header row naming the nation or a
# division, then the rows that partition it. Every row carries six figures --
# a count, the literal 100.00 of its own row percentage, then male and female
# with theirs -- and that middle 100.00 is what separates a data row from the
# page furniture, which has no such column. The name may hold spaces, slashes
# and hyphens ("Mahato/Kurmi Mahato/Bedia Mahato"), so it is whatever precedes
# the six figures rather than a pattern of its own; it must start with a
# non-digit, or the "1 2 3 4 5 6 7" column-number line the report prints under
# every table heading would read as a category called "1".
REPORT_ROW = re.compile(
    r"^(?P<name>\D.*?)\s+(?P<total>[\d,]+(?:\.\d+)?)\s+100\.00\s+"
    r"[\d,]+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+[\d,]+(?:\.\d+)?\s+\d+(?:\.\d+)?$")

# What geoBoundaries calls each division. Bangladesh respelled Barisal and
# Chittagong in 2018 exactly as it respelled their districts, and the boundary
# file also writes Rajshahi as "Rajshani".
DIVISION_ALIASES: dict[str, tuple[str, ...]] = {
    "Barishal": ("Barisal",),
    "Chattogram": ("Chittagong",),
    "Rajshahi": ("Rajshani",),
}

# The Bureau's own two publications of this census disagree about two
# districts' spelling: the National Report writes Netrokona and
# Chapainawabganj where the workbook writes Netrakona and Chapainababganj.
# Declared rather than bridged by a rule, because a rule loose enough to join
# "Chapainawabganj" to "Chapainababganj" would join a great deal else, and
# these two names are how the report's figures find the workbook's -- a check
# that must fail loudly if a third spelling ever appears rather than quietly
# matching something near it.
REPORT_SPELLING = {
    "Netrokona": "Netrakona",
    "Chapainawabganj": "Chapainababganj",
}

# Taken from the one place that decides it rather than restated here -- the
# whole marker, status included, not just the sentence. A second copy of this
# is a second thing to keep true, and the country row and its zilas
# disagreeing about whether Bangladesh asks the question is exactly the
# failure the central table exists to prevent. The status is half of that
# claim, which is why it comes from there too: this field is `not_available`
# and not `not_collected`, because the Bureau does ask mother tongue -- in the
# census project's own sample survey -- and publishes an answer this map
# cannot draw.
LANGUAGE = collection_gap("BGD", "language")

def ethnicity_gap(name: str, ethnic: int, whole: int) -> str:
    """Why this district shows no ethnic composition, and what it does show.

    Bangladesh asks the question -- "ethnic population" is one of the twenty
    subjects the individual module covers -- and the answer reaches this level
    as a single number. Table P28 gives one total per district and no
    breakdown, and no sheet in the workbook names a single people: all 445
    columns of it were searched, and Chakma, Marma, Santal, Garo, Tripura and
    the rest appear in none of them. The named groups are published nationally
    and nowhere lower.

    So there is a measured share here and no composition to draw, and the two
    must not be confused. "Ethnic population" against everyone else is not a
    list of peoples; drawn as a two-slice chart it would read as a census that
    found two ethnicities, which is the kind of wrong this project ranks below
    a gap. The number itself is worth stating, though -- it is 57.6% in
    Rangamati and 0.01% in Nilphamari, and a blank panel says none of that --
    so it goes in the reason.
    """
    return (f"Census 2022 counts {ethnic:,} of {name}'s {whole:,} people as "
            f"ethnic population -- {ethnic / whole * 100:.2f}% -- but does not "
            "say which peoples they are. The Bureau publishes that total by "
            "district (Table P28) and the named groups only nationally; no "
            "sheet of its district workbook names one. A single figure and a "
            "residual is not a composition, so it is stated here rather than "
            "drawn as one.")


NOTE = ("Census 2022. The religion table classifies the male and female "
        "population only -- each religion's total is exactly its male plus "
        "its female column -- so these shares are of a denominator a few "
        "dozen people short of the district's own population, the difference "
        "being the third-gender (hijra) population the table does not "
        "classify.")


def fetch(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                      "+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/vnd.openxmlformats-officedocument."
                  "spreadsheetml.sheet,*/*",
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def sheet(book, wanted: str):
    """A sheet by its name with the surrounding space ignored.

    The published workbook names one of them " Population by Religion, Sex",
    with a leading space, and a lookup by the name as it reads would report a
    sheet that is plainly there as missing.
    """
    for name in book.sheetnames:
        if name.strip() == wanted:
            return book[name]
    raise SystemExit(
        f"no sheet named {wanted!r} in the workbook; it has: "
        + ", ".join(repr(n) for n in book.sheetnames))


def table(sheet) -> list[dict[str, Any]]:
    """A sheet's rows as dicts, stopping where the data does.

    openpyxl reports the declared dimension rather than the used one -- these
    sheets say a thousand rows and hold sixty-four -- so the end of the table
    is the first row with no district on it, not the end of the sheet.
    """
    rows = sheet.iter_rows(values_only=True)
    header = [("" if cell is None else str(cell).strip())
              for cell in next(rows)]
    out = []
    for values in rows:
        if not values or values[0] is None or not str(values[0]).strip():
            break
        out.append(dict(zip(header, values)))
    return out


def pick(row: dict[str, Any], prefix: str) -> Any:
    """One column by its name, or by the only name that starts with it.

    The population sheet's headings run "Population_Total",
    "Population_Hijra", "Population_rural_..." and so on, and reading a
    heading off a printed excerpt truncates it. A prefix that matches exactly
    one column is the column; a prefix that matches several is ambiguous and
    says so rather than taking the first.
    """
    if prefix in row:
        return row[prefix]
    hits = [key for key in row if key.startswith(prefix)]
    if len(hits) == 1:
        return row[hits[0]]
    raise SystemExit(
        f"{prefix!r} matches {len(hits)} columns ({hits[:4]}) of: "
        + ", ".join(list(row)[:14]))


def number(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").strip()
    try:
        return int(float(text))
    except ValueError:
        return None


def check(districts: list[dict[str, Any]]) -> None:
    """The workbook's own arithmetic, checked before any of it is used.

    Each religion's total must be its male plus its female column: that is the
    sheet stating the same figure twice, and the two agreeing is what makes
    the column headings trustworthy rather than assumed.

    And the religions plus the third gender must equal the district's
    published population exactly. Two separate sheets have to agree to the
    person for that to hold, which is what makes it worth having: the
    workbook's merged sheet fails this badly enough to have swapped two
    districts' populations, and a tolerance wide enough to admit a hijra count
    would have been wide enough to hide something worse.
    """
    bad = []
    for row in districts:
        for religion, (male, female) in SEXED.items():
            total = row["counts"][religion]
            parts = row["sexed"][religion]
            if None in parts:
                bad.append(f"{row['name']}: {religion} has no {male}/{female}")
            elif sum(parts) != total:
                bad.append(f"{row['name']}: {religion} totals {total:,} "
                           f"against {sum(parts):,} by sex")
        classified = sum(row["counts"].values())
        whole, hijra = row["population"], row["hijra"]
        if whole is None or hijra is None:
            bad.append(f"{row['name']}: no published population or hijra count")
        elif classified + hijra != whole:
            bad.append(f"{row['name']}: {classified:,} classified by religion "
                       f"plus {hijra:,} hijra is {classified + hijra:,}, "
                       f"against a published {whole:,}")
        # The ethnic total held to the same standard as a religion's: its own
        # male plus female, and never more people than the district has. The
        # figure is about to be published as a percentage of that population,
        # and a percentage over 100 is how a column read one place left
        # announces itself.
        ethnic, parts = row["ethnic"], row["ethnic_sexed"]
        if ethnic is None or None in parts:
            bad.append(f"{row['name']}: ethnic population has no total or no "
                       f"sex split ({ethnic}, {parts})")
        elif sum(parts) != ethnic:
            bad.append(f"{row['name']}: ethnic population totals {ethnic:,} "
                       f"against {sum(parts):,} by sex")
        elif whole is not None and ethnic > whole:
            bad.append(f"{row['name']}: {ethnic:,} ethnic population against "
                       f"a district population of {whole:,}")
    if bad:
        raise SystemExit(f"{len(bad)} checks failed — " + "; ".join(bad[:4]))
    hijra = sum(row["hijra"] for row in districts)
    log(f"    every religion's total matches its own male plus female, and "
        f"in every district the religions plus the hijra come to the "
        f"published population exactly ({hijra:,} hijra nationally, whom the "
        f"religion table does not classify)")
    ethnic = sum(row["ethnic"] for row in districts)
    people = sum(row["population"] for row in districts)
    top = max(districts, key=lambda row: row["ethnic"] / row["population"])
    log(f"    ethnic population {ethnic:,} of {people:,} nationally "
        f"({ethnic / people * 100:.2f}%), highest in {top['name']} at "
        f"{top['ethnic'] / top['population'] * 100:.1f}% -- a total per "
        f"district and no breakdown, so it is published as the reason this "
        f"field is a gap rather than as a composition")


def read(blob: bytes) -> list[dict[str, Any]]:
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    try:
        people = table(sheet(book, POPULATION_SHEET))
        religion = table(sheet(book, RELIGION_SHEET))
        ethnic = table(sheet(book, ETHNIC_SHEET))
    finally:
        book.close()
    log(f"    {len(people)} districts in {POPULATION_SHEET}, "
        f"{len(religion)} in {RELIGION_SHEET}, "
        f"{len(ethnic)} in {ETHNIC_SHEET}")

    whole = {str(row["District"]).strip(): row for row in people}
    missing = sorted({str(r["District"]).strip() for r in religion} - set(whole))
    if missing:
        # Named, because a district in one sheet and not the other is a fact
        # about the workbook rather than a row to quietly drop.
        raise SystemExit("districts in the religion sheet and not in "
                         f"{POPULATION_SHEET}: {', '.join(missing)}")

    peoples = {str(row["District"]).strip(): row for row in ethnic}
    missing = sorted(set(whole) - set(peoples))
    if missing:
        # The same rule the other way round. A district the ethnic sheet
        # skips must be said out loud: a reason built from a figure that was
        # never there would print a share of nothing.
        raise SystemExit("districts in " + POPULATION_SHEET + " and not in "
                         f"{ETHNIC_SHEET}: {', '.join(missing)}")

    out = []
    for row in religion:
        name = str(row["District"]).strip()
        counts = {religion_name: number(row.get(column))
                  for religion_name, column in COLUMNS.items()}
        if any(value is None for value in counts.values()):
            raise SystemExit(f"{name}: a religion column is missing or not a "
                             f"number: {counts}")
        out.append({
            "name": name,
            "population": number(pick(whole[name], "Population_Total")),
            "hijra": number(pick(whole[name], "Population_Hijra")),
            "ethnic": number(peoples[name].get(ETHNIC_TOTAL)),
            "ethnic_sexed": tuple(number(peoples[name].get(column))
                                  for column in ETHNIC_SEXED),
            "counts": counts,
            "sexed": {religion_name: tuple(number(row.get(column))
                                           for column in pair)
                      for religion_name, pair in SEXED.items()},
        })
    return out


def division_note(where: str, ethnic: int, whole: int,
                  counts: dict[str, int]) -> str:
    """What these shares are of, said before anybody reads them as a whole.

    The shares are of the division's entire population, not of its ethnic
    population, and that choice is the difference between a figure and a
    misstatement. Chattogram's Chakma are 475,548 people: 48% of the division's
    ethnic population and 1.4% of the division. Published the first way this
    map would call Chakma the largest group in Chattogram, where they are one
    person in seventy.

    So the list here covers only the few per cent of the division the census
    enumerates by ethnic category, and says so. Everyone else is not a group
    the census names -- it publishes no count of them and no label for them --
    and inventing one to fill the bar would be the fabrication the rules
    forbid.
    """
    biggest = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return (f"Census 2022, Table P29. These shares are of {where}'s whole "
            f"population of {whole:,}, of whom {ethnic:,} ({ethnic / whole * 100:.2f}%) "
            f"are enumerated by ethnic category; the largest is "
            f"{biggest[0]} at {biggest[1]:,}. The rest of the division is not "
            "shown because the census names no group for it: it publishes the "
            "ethnic categories and no label for anybody else, so the bar here "
            "describes the part of the population that was asked and answered "
            "this question.")


def report_blocks(lines: list[str], table: str, until: str | None) -> dict[str, Any]:
    """One report table as ``{where: {"total": n, "rows": {name: n}}}``.

    ``where`` is "National" or a division with the word "Division" dropped,
    because a division is the same place whether or not the word is printed
    and the shape it has to reach is named without it.
    """
    start = next((i for i, line in enumerate(lines)
                  if line.strip().startswith(table)), None)
    if start is None:
        raise SystemExit(f"{table} is not in the National Report; the report "
                         "it was read from has changed")
    end = len(lines)
    if until:
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].strip().startswith(until)), len(lines))

    out: dict[str, Any] = {}
    where = None
    for line in lines[start:end]:
        found = REPORT_ROW.match(" ".join(line.split()))
        if not found:
            continue
        name = found.group("name").strip()
        total = int(float(found.group("total").replace(",", "")))
        if name == "National" or name.endswith("Division"):
            where = name.removesuffix(" Division")
            out[where] = {"total": total, "rows": {}}
        elif where is not None:
            # Summed rather than assigned: a category that appeared twice in
            # one block would otherwise silently keep only the second figure,
            # and the reconciliation below would then be checking a number
            # against itself.
            out[where]["rows"][name] = out[where]["rows"].get(name, 0) + total
    return out


def read_report(blob: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Tables P28 and P29, checked against each other and against themselves.

    P28 is the ethnic population by district and P29 the same total broken
    into named categories, both grouped by division. Reading both is what
    makes this trustworthy rather than merely parsed: P28 gives which
    districts are in which division and a per-district total that the
    workbook states independently, and P29's division headers must equal
    P28's. Three tables, two publications, one set of figures.
    """
    lines = laid_out(blob).splitlines()
    districts = report_blocks(lines, "Table P28", "Table P29")
    categories = report_blocks(lines, "Table P29", "Table P30")
    log(f"    National Report: {len(districts) - 1} divisions in Table P28, "
        f"{sum(len(b['rows']) for k, b in districts.items() if k != 'National')} "
        f"districts; Table P29 names "
        f"{len(categories.get('National', {}).get('rows', {}))} categories")
    return districts, categories


def check_report(districts: dict[str, Any], categories: dict[str, Any],
                 workbook: dict[str, int]) -> None:
    """Every figure here is stated twice, and the two must agree to the person.

    Four checks, each of which has somewhere else to fall down:

    * every block's rows sum to the header printed above them -- a row lost to
      a page break, or a page of the table missed entirely, fails here;
    * the eight divisions sum to the national header;
    * each category's national figure equals the sum of its eight divisional
      ones, which is the table read down as well as across;
    * P28's district totals equal the workbook's, and P29's division headers
      equal P28's -- two separate publications of the same census agreeing,
      which is what makes the categories trustworthy rather than merely
      arithmetically consistent with themselves.
    """
    bad: list[str] = []
    for label, book in (("P28", districts), ("P29", categories)):
        for where, block in book.items():
            summed = sum(block["rows"].values())
            if block["rows"] and summed != block["total"]:
                bad.append(f"{label} {where}: rows sum to {summed:,} against a "
                           f"printed {block['total']:,}")
        divisions = sum(b["total"] for w, b in book.items() if w != "National")
        national = book.get("National", {}).get("total")
        if national is not None and divisions != national:
            bad.append(f"{label}: divisions sum to {divisions:,} against a "
                       f"national {national:,}")

    for name, count in categories.get("National", {}).get("rows", {}).items():
        summed = sum(b["rows"].get(name, 0)
                     for w, b in categories.items() if w != "National")
        if summed != count:
            bad.append(f"P29 {name}: national {count:,} against {summed:,} "
                       "summed over the divisions")

    for where, block in districts.items():
        if where == "National":
            continue
        if categories.get(where, {}).get("total") != block["total"]:
            bad.append(f"{where}: P28 has {block['total']:,} and P29 "
                       f"{categories.get(where, {}).get('total')}")
        for district, count in block["rows"].items():
            name = REPORT_SPELLING.get(district, district)
            if workbook.get(name) != count:
                bad.append(f"{district}: the report says {count:,} ethnic "
                           f"people and the workbook {workbook.get(name)}")
    if bad:
        raise SystemExit(f"{len(bad)} report checks failed — " + "; ".join(bad[:4]))
    log("    the report's district totals match the workbook's to the person, "
        "its division headers match between Tables P28 and P29, and every "
        "category's national figure is the sum of its eight divisional ones")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("bangladesh: BBS Population and Housing Census 2022, by zila")
    blob = fetch(WORKBOOK)
    log(f"    {len(blob):,} bytes from HDX")
    districts = read(blob)
    check(districts)

    records: list[dict[str, Any]] = []
    for row in districts:
        classified = sum(row["counts"].values())
        records.append(record(
            f"BGD-{row['name'].lower().replace(' ', '-')}",
            row["name"], level="admin2", parent="BGD",
            aliases=list(ALIASES.get(row["name"], ())),
            population=measure(row["population"], year=YEAR, source=SOURCE),
            religion=shares(row["counts"], total=classified) or gap(NOT_AVAILABLE),
            religion_year=YEAR, religion_note=NOTE,
            language=dict(LANGUAGE),
            ethnicity=gap(NOT_AVAILABLE, ethnicity_gap(
                row["name"], row["ethnic"], row["population"])),
            sources=[{"field": "population/religion", "name": SOURCE,
                      "url": URL, "license": LICENCE}]))

    report = http_get(REPORT, binary=True)
    log(f"    {len(report):,} bytes of National Report from the Bureau's own storage")
    by_district, by_category = read_report(report)
    check_report(by_district, by_category,
                 {row["name"]: row["ethnic"] for row in districts})

    population = {row["name"]: row["population"] for row in districts}
    for where, block in by_district.items():
        if where == "National":
            continue
        # The division's population is the sum of the districts the report
        # itself puts in it, taken from the workbook -- not a division figure
        # from somewhere else. The share and the denominator then come from
        # the same census read the same way, which is the whole point of
        # having checked the two publications against each other above.
        whole = sum(population[REPORT_SPELLING.get(name, name)]
                    for name in block["rows"])
        counts = by_category[where]["rows"]
        records.append(record(
            f"BGD-{where.lower()}", where, level="admin1", parent="BGD",
            aliases=list(DIVISION_ALIASES.get(where, ())),
            ethnicity=shares(counts, total=whole),
            ethnicity_year=YEAR,
            ethnicity_basis="the ethnic population the census enumerates",
            ethnicity_note=division_note(where, block["total"], whole, counts),
            sources=[{"field": "ethnicity", "name": REPORT_SOURCE,
                      "url": REPORT_PAGE, "license": LICENCE}]))
    log(f"    {len(by_category) - 1} divisions carry a named ethnic composition, "
        f"{sum(by_category[w]['total'] for w in by_category if w != 'National'):,} "
        "people across "
        f"{len(by_category.get('National', {}).get('rows', {}))} categories")

    out = args.out or PROCESSED / "bangladesh_district.json"
    write_json(out, records)
    log(f"  {len(records)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
