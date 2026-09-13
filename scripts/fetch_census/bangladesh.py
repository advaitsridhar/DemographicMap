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
import io
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, collection_gap, gap, log, measure, record,
    shares, write_json,
)

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

    out = args.out or PROCESSED / "bangladesh_district.json"
    write_json(out, records)
    log(f"  {len(records)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
