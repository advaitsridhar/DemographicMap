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
  not.
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
1,010,531, and the 70 missing are its hijra. So the shares here are of the
population the religion table classifies, which is a few dozen people short of
the district in most zila, and the note says so. Both figures are kept -- the
district's own population, and the denominator the shares are of -- because
silently using one for the other is how a footnote becomes a wrong number.

Usage:
    python -m scripts.fetch_census.bangladesh
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
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
MERGED_SHEET = "Merged_All_Table"

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

    And the religions must account for the district's population apart from
    the third gender, which is well under a tenth of a percent everywhere. A
    gap wider than that is not the hijra count and means these are not the
    columns this reader thinks they are.
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
        whole = row["population"]
        if not whole:
            bad.append(f"{row['name']}: no district population")
        elif not 0 <= whole - classified <= max(200, 0.001 * whole):
            bad.append(f"{row['name']}: religions classify {classified:,} of "
                       f"{whole:,}, a gap of {whole - classified:+,}")
    if bad:
        raise SystemExit(f"{len(bad)} checks failed — " + "; ".join(bad[:4]))
    unclassified = sum(r["population"] - sum(r["counts"].values())
                       for r in districts)
    log(f"    every religion's total matches its own male plus female, and "
        f"the religions account for every district bar {unclassified:,} "
        f"people not classified by religion")


def read(blob: bytes) -> list[dict[str, Any]]:
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    try:
        merged = table(sheet(book, MERGED_SHEET))
        religion = table(sheet(book, RELIGION_SHEET))
    finally:
        book.close()
    log(f"    {len(merged)} districts in {MERGED_SHEET}, "
        f"{len(religion)} in {RELIGION_SHEET}")

    whole = {str(row["District"]).strip(): row for row in merged}
    missing = [str(r["District"]).strip() for r in religion
               if str(r["District"]).strip() not in whole]
    if missing:
        # Named, because a district in one sheet and not the other is a fact
        # about the workbook rather than a row to quietly drop.
        raise SystemExit("districts in the religion sheet and not in "
                         f"{MERGED_SHEET}: {', '.join(missing)}")

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
            "division": str(whole[name].get("Division") or "").strip(),
            "geocode": number(whole[name].get("District_Geocode")),
            "population": number(whole[name].get("Population_Total")),
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
            parent_name=row["division"] or None,
            population=measure(row["population"], year=YEAR, source=SOURCE),
            religion=shares(row["counts"], total=classified) or gap(NOT_AVAILABLE),
            religion_year=YEAR, religion_note=NOTE,
            sources=[{"field": "population/religion", "name": SOURCE,
                      "url": URL, "license": LICENCE}]))

    out = args.out or PROCESSED / "bangladesh_district.json"
    write_json(out, records)
    log(f"  {len(records)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
