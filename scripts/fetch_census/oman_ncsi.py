#!/usr/bin/env python3
"""Oman's wilayats and regions: registered population by nationality and age, NCSI.

The National Centre for Statistics and Information's *Statistical Year Book
2024* (Issue 52; read from the Internet Archive's capture of the NCSI's own
PDF, the NCSI library's pages answering 404 to the runner) prints, in its
population chapter:

* Table 7-2 (pp. 32-33): the population registered in the Sultanate by
  nationality (Omani, expatriate) for every governorate and wilayat, at the
  end of 2021, 2022 and 2023;
* Table 9-2 (p. 35): the registered population by five-year age group and
  governorate at the end of December 2023.

The register is the NCSI's count of the population: Omanis from the civil
register, expatriates from the residence register.

**What is written.**

* Every drawn wilayat that is one of the yearbook's wilayats (59 of 61): its
  people at the end of 2023, and Omani citizens against foreign nationals on
  the ethnicity field (``ethnicity_basis: "nationality"``, the owner's
  decision of 19 September 2026). The citizens' row is "Omani citizens", a
  label naming no people: Oman's citizens are Arab, Baluchi, Jibbali, Mahri,
  Swahili-speaking and more, and a row read as "Omani" would colour Dhofar's
  mountains Arab, which no count says.
* The two wilayats made since the boundary file was drawn -- Al Jabal Al
  Akhdar and Sinaw -- are not drawn; the drawn wilayat holding each one's
  ground (``CARVED``) takes the sum of both, as a merged unit may.
* Every drawn region (the boundary file's seven, older than today's eleven
  governorates): the sum of the wilayats the boundary file nests in it, by
  nationality, and -- where the region is whole governorates (Muscat, Dhofar,
  Al Wusta, Ad Dakhiliyah, and Al Batinah, North and South) -- its median
  age, interpolated within Table 9-2's five-year groups. Ash Sharqiyah and
  Az Zahirah are drawn with Masirah moved between them, so no governorate's
  ages are theirs.

**Checks** (any failure stops the run): every governorate's wilayats make its
row, in each of the six columns; the governorates make the Sultanate's row;
Table 9-2's governorates make each age group and the groups make each
governorate; the two tables' totals agree, and each governorate's within
``AGES_SLACK`` (the tables allocate some 1,000 people of Ad Dakhiliyah and
Al Wusta to Ash Sharqiyah North differently, as the log shows); every drawn
wilayat is bound once.

Usage:
    python -m scripts.fetch_census.oman_ncsi
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import check, median_age, units

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from probe_pdf import PAGE_BREAK, fetch_blob, laid_out  # noqa: E402

ISO3 = "OMN"
OUT = "oman_ncsi.json"
URL = ("https://web.archive.org/web/20240801130251id_/https://www.ncsi.gov.om/Elibrary/"
       "LibraryContentDoc/bar_Statistical%20Year%20Book%202024%20Issue%2052_"
       "469215ea-35ad-4c19-baeb-be858bd6c934.pdf")
YEAR = 2023
SOURCE = ("National Centre for Statistics and Information (Oman), Statistical Year Book "
          "2024 (Issue 52), Table 7-2: total population registered by nationality, "
          "governorate and wilayat, end of 2023")
SOURCE_AGES = ("National Centre for Statistics and Information (Oman), Statistical Year Book "
               "2024 (Issue 52), Table 9-2: population registered by age group and "
               "governorate, end of December 2023")
LICENCE = "National Centre for Statistics and Information (Oman), published yearbook"
CITIZENS = "Omani citizens"
# Table 9-2's governorates may differ from Table 7-2's by this share.
AGES_SLACK = 0.005

# Table 7-2's rows in the order printed: each governorate, then its wilayats,
# with the boundary file's label for each wilayat it draws.
TABLE = [
    ("Muscat", {"Muscat": "WILAYAT MUSCAT", "Mutrah": "WILAYAT MUTRAH",
                "Al Amrat": "WILAYAT AL AMRAT", "Bawshar": "WILAYAT BAWSHAR",
                "As Seeb": "WILAYAT AS SEEB", "Qurayyat": "WILAYAT QURAYYAT"}),
    ("Dhofar", {"Salalah": "WILAYAT SALALAH", "Taqah": "WILAYAT TAQAH",
                "Mirbat": "WILAYAT MIRBAT", "Rakhyut": "WILAYAT RAKHYUT",
                "Thumrayt": "WILAYAT THUMRAYT", "Dalkut": "WILAYAT DALKUT",
                "Al Mazyunah": "WILAYAT AL MAZYUNAH", "Muqshin": "WILAYAT MUQSHIN",
                "Shalim wa Juzor al Hallaniyat": "WILAYAT SHALIM WA JUZOR AL HALLANIYAT",
                "Sadah": "WILAYAT SADAH"}),
    ("Musandam", {"Khasab": "WILAYAT KHASAB", "Daba": "WILAYAT DABA",
                  "Bukha": "WILAYAT BUKHA", "Madha": "WILAYAT MADHA"}),
    ("Al Buraymi", {"Al Buraymi": "WILAYAT AL BURAYMI", "Mahdah": "WILAYAT MAHADAH",
                    "As Sunaynah": "WILAYAT AS SUNAYNAH"}),
    ("Ad Dakhiliyah", {"Nizwa": "WILAYAT NIZWA", "Bahla": "WILAYAT BAHLA",
                       "Manah": "WILAYAT MANAH", "Al Hamra": "WILAYAT AL HAMRA",
                       "Adam": "WILAYAT ADAM", "Izki": "WILAYAT IZKI",
                       "Samail": "WILAYAT SAMAIL", "Bidbid": "WILAYAT BIDBID",
                       "Al Jabal Al Akhdar": None}),
    ("Al Batinah North", {"Sohar": "WILAYAT SOHAR", "Shinas": "WILAYAT SHINAS",
                          "Liwa": "WILAYAT LIWA", "Saham": "WILAYAT SAHAM",
                          "Al Khaburah": "WILAYAT AL KHABURAH",
                          "As Suwayq": "WILAYAT AS SUWAYQ"}),
    ("Al Batinah South", {"Ar Rustaq": "WILAYAT AR RUSTAQ", "Al Awabi": "WILAYAT AL AWABI",
                          "Nakhal": "WILAYAT NAKHAL",
                          "Wadi Al Maawil": "WILAYAT WADI AL MAAWIL",
                          "Barka": "WILAYAT BARKA", "Al Musanaah": "WILAYAT AL MUSANAAH"}),
    ("Ash Sharqiyah South", {"Sur": "WILAYAT SUR",
                             "Al Kamil wa Al Wafi": "WILAYAT AL KAMIL WA AL WAFI",
                             "Jaalan Bani Bu Hasan": "WILAYAT JAALAN BANI BU HASAN",
                             "Jaalan Bani Bu Ali": "WILAYAT JAALAN BANI BU ALI",
                             "Masirah": "WILAYAT MASIRAH"}),
    ("Ash Sharqiyah North", {"Ibra": "WILAYAT IBRA", "Al Mudaybi": "WILAYAT AL MUDAYBI",
                             "Bidiyah": "WILAYAT BIDIYAH", "Al Qabil": "WILAYAT AL QABIL",
                             "Wadi Bani Khalid": "WILAYAT WADI BANI KHALID",
                             "Dima wa At Taiyin": "WILAYAT DAMA WA AT TAIYIN",
                             "Sinaw": None}),
    ("Adh Dhahirah", {"Ibri": "WILAYAT IBRI", "Yanqul": "WILAYAT YANQUL",
                      "Dank": "WILAYAT DANK"}),
    ("Al Wusta", {"Hayma": "WILAYAT HAYMA", "Muhut": "WILAYAT MAHAWT",
                  "Ad Duqm": "WILAYAT AD DUQM", "Al Jazir": "WILAYAT AL JAZIR"}),
]
# Wilayats made since the boundary file was drawn -> the drawn wilayat whose
# ground holds them, and the GeoNames places that show it: each must lie in
# that drawn polygon on the map's own tiles, or the run stops. Al Jabal Al
# Akhdar's plateau villages (Sayq, Wadi Bani Habib and the wilayat's seat)
# lie in drawn Nizwa; Sinaw town in drawn Al Mudaybi.
CARVED: dict[str, str] = {"Al Jabal Al Akhdar": "WILAYAT NIZWA",
                          "Sinaw": "WILAYAT AL MUDAYBI"}
CARVED_PLACES = {
    "Al Jabal Al Akhdar": [("geonames:11806731 Al Jabal al Akhdar", 23.08148, 57.67924),
                           ("geonames:286515 Sayq", 23.07440, 57.63965),
                           ("geonames:288864 Wadi Bani Habib", 23.07797, 57.60673)],
    "Sinaw": [("geonames:286576 Sinaw", 22.50114, 58.03010)],
}
# Table 9-2's columns after its total, in the order printed (right to left in
# Arabic, left to right in the English header).
AGE_COLUMNS = ["Al Wusta", "Adh Dhahirah", "Ash Sharqiyah North", "Ash Sharqiyah South",
               "Al Batinah South", "Al Batinah North", "Ad Dakhiliyah", "Al Buraymi",
               "Musandam", "Dhofar", "Muscat"]
# The drawn regions that are whole governorates, for the median age.
WHOLE = {"Muscat": ["Muscat"], "Dhofar": ["Dhofar"], "Al Wusta": ["Al Wusta"],
         "Ad Dakhiliyah": ["Ad Dakhiliyah"],
         "Al Batinah": ["Al Batinah North", "Al Batinah South"]}
# What the yearbook does not publish, read across all 280 pages (runner probes
# c3e53be and 048cf9d): its population tables are Table 7-2 (nationality),
# 8-2 (nationality, age and sex, the Sultanate only) and 9-2 (age by
# governorate); "religion" appears only in spending and students' subjects,
# and "language" nowhere.
SEX_WHY = ("The NCSI's Statistical Year Book 2024 counts men and women for the Sultanate only "
           "(Table 8-2); its tables by governorate (9-2) and wilayat (7-2) count age and "
           "nationality, not sex.")
AGES_WHY = ("The NCSI publishes ages by governorate only (Statistical Year Book 2024, Table "
            "9-2); no table gives a wilayat's ages.")
RELIGION_WHY = ("The NCSI's Statistical Year Book 2024 counts the population by nationality, "
                "sex and age; it publishes no religion for any governorate or wilayat.")
LANGUAGE_WHY = ("The NCSI's Statistical Year Book 2024 counts the population by nationality, "
                "sex and age; it publishes no language for any governorate or wilayat.")


def unpublished() -> dict[str, Any]:
    """The fields no NCSI table gives below the Sultanate, each with its reason."""
    return {"sex_ratio": gap(NOT_AVAILABLE, SEX_WHY),
            "religion": gap(NOT_AVAILABLE, RELIGION_WHY),
            "language": gap(NOT_AVAILABLE, LANGUAGE_WHY)}


NUM = re.compile(r"(?<![\d,.])\d{1,3}(?:,\d{3})*(?![\d,.])")
ARABIC = re.compile(r"[؀-ۿ]+")


def pages(text: str, title: str) -> list[str]:
    """The pages whose text contains ``title``, and the 'Contd.' page after each."""
    sheets = text.split(PAGE_BREAK)
    out = []
    for i, page in enumerate(sheets):
        if title in page:
            out.append(page)
            if i + 1 < len(sheets) and "Contd" in sheets[i + 1]:
                out.append(sheets[i + 1])
    return out


Counts = dict[str, dict[str, int]]


def table72(text: str) -> tuple[Counts, Counts, dict[str, int]]:
    """(governorates, wilayats, Sultanate): each name -> its 2023 expatriates,
    Omanis and total. Governorates and wilayats are kept apart because some
    share a name (Muscat, Al Buraymi).

    Each row prints expat 2023, Omani 2023, expat 2022, Omani 2022, expat 2021
    and Omani 2021. The numbers are read in print order from the line after
    each page's column heads to its foot, and dealt to ``TABLE``'s rows six at
    a time; the sums below prove the dealing right.
    """
    found = pages(text, "Total Population Registered in the Sultanate by Nationality")
    check(len(found) == 2, f"oman_ncsi: Table 7-2 on {len(found)} pages, not 2")
    numbers: list[int] = []
    for page in found:
        started = False
        for line in page.splitlines():
            if re.search(r"Expatriate\s+Omani\s+Expatriate", line):
                started = True
                continue
            if not started:
                continue
            if line.startswith("[") or re.match(r"^\s*Population\b", line):
                break
            numbers += [int(n.replace(",", "")) for n in NUM.findall(ARABIC.sub(" ", line))]
    names = []
    for gov, wilayats in TABLE:
        names.append(("governorate", gov))
        names += [("wilayat", w) for w in wilayats]
    names.append(("total", "Sultanate"))
    check(len(numbers) == 6 * len(names),
          f"oman_ncsi: Table 7-2 gave {len(numbers)} figures for {len(names)} rows of six")
    rows = {}
    for i, (kind, name) in enumerate(names):
        rows[(kind, name)] = numbers[6 * i: 6 * i + 6]
    total = [0] * 6
    for gov, wilayats in TABLE:
        made = [sum(rows[("wilayat", w)][c] for w in wilayats) for c in range(6)]
        check(made == rows[("governorate", gov)],
              f"oman_ncsi: Table 7-2 {gov}'s wilayats make {made}, not "
              f"{rows[('governorate', gov)]}")
        total = [a + b for a, b in zip(total, made)]
    check(total == rows[("total", "Sultanate")],
          f"oman_ncsi: Table 7-2's governorates make {total}, not {rows[('total', 'Sultanate')]}")
    def counts(kind: str) -> Counts:
        return {name: {"expat": v[0], "omani": v[1], "total": v[0] + v[1]}
                for (k, name), v in rows.items() if k == kind}
    return counts("governorate"), counts("wilayat"), counts("total")["Sultanate"]


AGE_LABEL = re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})\s*$|(80)\s*\+\s*$")


def table92(text: str) -> dict[str, list[tuple[int, int | None, float]]]:
    """Governorate -> five-year age groups (0-4 ... 75-79, 80+), Table 9-2."""
    found = pages(text, "Population Registered by Age Group, Governorates")
    check(len(found) >= 1, "oman_ncsi: no Table 9-2")
    groups: dict[str, list[tuple[int, int | None, float]]] = {g: [] for g in AGE_COLUMNS}
    totals: list[int] | None = None
    for line in found[0].splitlines():
        plain = ARABIC.sub(" ", line).strip()
        m = AGE_LABEL.search(plain)
        if m and not plain.startswith("Total"):
            prefix = plain[:m.start()]
            values = [int(n.replace(",", "")) for n in NUM.findall(prefix)][-12:]
            if len(values) != 12:
                continue
            if m.group(3):
                low, high = 80, None
            else:
                # Printed high - low, as the Arabic reads.
                a, b = int(m.group(1)), int(m.group(2))
                low, high = min(a, b), max(a, b)
            check(sum(values[1:]) == values[0],
                  f"oman_ncsi: Table 9-2 ages {low}-{high}: governorates make "
                  f"{sum(values[1:]):,}, not {values[0]:,}")
            for gov, n in zip(AGE_COLUMNS, values[1:]):
                groups[gov].append((low, high, float(n)))
        elif plain.startswith("Total") or re.match(r"^[\d,\s]+Total", plain):
            values = [int(n.replace(",", "")) for n in NUM.findall(plain)]
            if len(values) >= 12:
                totals = values[-12:]
    check(totals is not None, "oman_ncsi: Table 9-2 has no total row")
    for gov, t in zip(AGE_COLUMNS, totals[1:]):
        got = sorted(groups[gov], key=lambda g: g[0])
        edge = 0
        for low, high, _n in got:
            check(low == edge, f"oman_ncsi: Table 9-2 {gov}: age groups break at {edge}")
            edge = (high + 1) if high is not None else -1
        check(got and got[-1][1] is None, f"oman_ncsi: Table 9-2 {gov}: no open last group")
        made = sum(n for _a, _b, n in got)
        check(round(made) == t, f"oman_ncsi: Table 9-2 {gov}: groups make {made:,.0f}, "
                                f"not {t:,}")
        groups[gov] = got
    groups["_total"] = [(0, None, float(totals[0]))]
    return groups


def nationality(omani: float, expat: float) -> dict[str, Any]:
    return {
        "ethnicity": shares({k: v for k, v in ((CITIZENS, omani),
                                               ("Foreign nationals", expat)) if v}),
        "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
        "ethnicity_note": (
            "Nationality, not ethnicity: the NCSI's registers count Omanis (the civil "
            "register) and expatriates (the residence register), and no ethnic group. "
            "Nationality is shown here in place of ethnicity. 'Omani "
            "citizens' is every Omani, of whatever people -- Arab, Baluchi, Jibbali, Mahri "
            "or another -- and the label names none of them."),
    }


def check_carved(admin2: list[dict[str, Any]]) -> None:
    """Each carved wilayat's places lie in the drawn wilayat said to hold it."""
    from .sea_common import locate
    ids = {u["name"]: u["id"] for u in admin2}
    points = {(w, p): (lon, lat) for w, places in CARVED_PLACES.items()
              for p, lat, lon in places}
    held = locate(points, "admin2", ISO3, zoom=8)
    for (wilayat, place), sid in held.items():
        check(sid == ids.get(CARVED[wilayat]),
              f"oman_ncsi: {place} ({wilayat}) lies in {sid}, not {CARVED[wilayat]}")
    log(f"  carved wilayats' places all lie in their drawn wilayat: {sorted(points)}")


def build(text: str, admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          parents: dict[str, str]) -> list[dict[str, Any]]:
    govs, rows, sultanate = table72(text)
    ages = table92(text)
    total = sultanate["total"]
    check(round(ages["_total"][0][2]) == total,
          f"oman_ncsi: Table 9-2 counts {ages['_total'][0][2]:,.0f}, Table 7-2 {total:,}")
    for gov, _w in TABLE:
        aged = sum(n for _a, _b, n in ages[gov])
        drift = abs(aged - govs[gov]["total"]) / govs[gov]["total"]
        log(f"    {gov}: Table 7-2 {govs[gov]['total']:,}, Table 9-2 {aged:,.0f}"
            + (f" ({drift:.2%} apart)" if drift else ""))
        check(drift <= AGES_SLACK, f"oman_ncsi: {gov}'s two tables differ by {drift:.2%}")
    log(f"  {len(rows)} wilayats, {len(govs)} governorates, {total:,} people at the end "
        f"of 2023")

    labels: dict[str, list[dict[str, Any]]] = {}
    for unit in admin2:
        labels.setdefault(unit["name"], []).append(unit)
    out: list[dict[str, Any]] = []
    # Drawn wilayat label -> the yearbook's wilayats whose people it carries.
    carries: dict[str, list[str]] = {}
    for _gov, wilayats in TABLE:
        for name, label in wilayats.items():
            label = label or CARVED.get(name)
            if label:
                carries.setdefault(label, []).append(name)
    unplaced = [w for _g, ws in TABLE for w, lab in ws.items() if not lab and w not in CARVED]
    sources = [{"field": "population/ethnicity", "name": SOURCE, "url": URL, "year": YEAR,
                "license": LICENCE}]
    region_of: dict[str, str] = {}
    for label, names in carries.items():
        found = labels.get(label, [])
        check(len(found) == 1, f"oman_ncsi: {len(found)} drawn wilayats labelled {label!r}")
        unit = found[0]
        region_of[label] = parents.get(unit["parent"], "")
        omani = sum(rows[n]["omani"] for n in names)
        expat = sum(rows[n]["expat"] for n in names)
        population = measure(omani + expat, year=YEAR, source=SOURCE)
        population["note"] = (f"The NCSI's registered population at the end of 2023: "
                              f"{omani:,} Omanis and {expat:,} expatriates."
                              + (" The sum of the wilayats " + " and ".join(names)
                                 + ", the second made since the boundary file was drawn from "
                                   "this wilayat's ground." if len(names) > 1 else ""))
        out.append(record(
            f"OMN-NCSI-{label}", label, level="admin2", parent=ISO3, country=ISO3,
            parent_name=region_of[label], match_by="shape_id", shape_id=unit["id"],
            aliases=[names[0]] if names[0].upper() not in label else None,
            population=population, sources=sources, median_age=gap(NOT_AVAILABLE, AGES_WHY),
            **unpublished(), **nationality(omani, expat)))
    drawn_left = sorted(set(labels) - set(carries))
    log(f"  drawn wilayats written: {len(carries)} of {len(labels)}; drawn but not in the "
        f"table: {drawn_left}; yearbook wilayats on no drawn polygon: {unplaced}")
    for label in drawn_left:
        unit = labels[label][0]
        why = (f"The NCSI's yearbook counts no wilayat of this name; the boundary file's "
               f"{label.title()} is not one of the 63 wilayats of 2023.")
        out.append(record(f"OMN-NCSI-{label}", label, level="admin2", parent=ISO3,
                          country=ISO3, parent_name=parents.get(unit["parent"]),
                          match_by="shape_id", shape_id=unit["id"],
                          population=gap(NOT_AVAILABLE, why)))
    # Regions: the wilayats the boundary file nests in each.
    by_region: dict[str, list[str]] = {}
    for label, names in carries.items():
        by_region.setdefault(region_of[label], []).extend(names)
    for name in unplaced:
        gov = next(g for g, ws in TABLE if name in ws)
        region = next((r for r, members in WHOLE.items() if gov in members), None)
        check(region is not None, f"oman_ncsi: {name} is drawn nowhere and its governorate "
                                  f"{gov} is no whole region")
        by_region.setdefault(region, []).append(name)
    drawn1 = {u["name"]: u for u in admin1}
    for region, names in sorted(by_region.items()):
        check(region in drawn1, f"oman_ncsi: no drawn region {region!r}")
        omani = sum(rows[n]["omani"] for n in names)
        expat = sum(rows[n]["expat"] for n in names)
        population = measure(omani + expat, year=YEAR, source=SOURCE)
        govs = sorted({g for g, ws in TABLE for n in names if n in ws})
        population["note"] = (f"The NCSI's registered population at the end of 2023: "
                              f"{omani:,} Omanis and {expat:,} expatriates, the sum of the "
                              f"{len(names)} wilayats the boundary file draws in this region "
                              f"(of the governorates {', '.join(govs)}).")
        fields: dict[str, Any] = {"population": population, **unpublished(),
                                  **nationality(omani, expat)}
        if region in WHOLE:
            parts = WHOLE[region]
            expected = sorted(n for g in parts for n in dict(TABLE)[g])
            check(sorted(names) == expected,
                  f"oman_ncsi: {region} is drawn as {sorted(names)}, not the wilayats of "
                  f"{parts}")
            grouped = [(lo, hi, sum(dict((g[0], g[2]) for g in ages[p])[lo] for p in parts))
                       for lo, hi, _n in ages[parts[0]]]
            fields["median_age"] = median_age(grouped, year=YEAR, source=SOURCE_AGES)
            fields["median_age_note"] = (
                "Interpolated within the five-year age group holding the middle person, from "
                "the registered population by age group of the governorate"
                + ("s " + " and ".join(parts) if len(parts) > 1 else " " + parts[0])
                + " at the end of December 2023 (Table 9-2).")
        else:
            fields["median_age"] = gap(NOT_AVAILABLE, (
                "The NCSI publishes ages by governorate only, and this region as the boundary "
                "file draws it is not whole governorates (Masirah is drawn in Az Zahirah, not "
                "Ash Sharqiyah), so no published age table is its."))
        out.append(record(
            f"OMN-NCSI-{region}", region, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=drawn1[region]["id"],
            sources=sources + ([{"field": "median_age", "name": SOURCE_AGES, "url": URL,
                                 "year": YEAR, "license": LICENCE}]
                               if region in WHOLE else []),
            **fields))
    made = sum(r["population"]["value"] for r in out if r["level"] == "admin1")
    check(made == total, f"oman_ncsi: the regions make {made:,}, the Sultanate {total:,}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    blob = fetch_blob(URL)
    log(f"  {URL}: {len(blob):,} bytes")
    text = laid_out(blob)
    admin1, admin2 = units(ISO3, "admin1"), units(ISO3, "admin2")
    check_carved(admin2)
    rows = build(text, admin1, admin2, {u["id"]: u["name"] for u in admin1})
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
