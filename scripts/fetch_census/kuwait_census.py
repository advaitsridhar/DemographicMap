#!/usr/bin/env python3
"""Kuwait's governorates and areas in the 2021 register-based census.

The Central Statistical Bureau's first register-based census (التعداد
التسجيلي لدولة الكويت 2021, with the Public Authority for Civil Information)
publishes its tables on census.csb.gov.kw, each exportable as a workbook
(``CensusData?st_id=N&handler=ExportExcel``). Four are read:

* Table 1 (st_id 4): every governorate's people by nationality (Kuwaiti,
  non-Kuwaiti) and sex;
* Table 2 (st_id 5): every governorate's people by five-year age group and sex;
* Table 6 (st_id 26): every governorate's people by nationality group (Gulf,
  Arab, Asian, African, European, North American, South American,
  Australian) and sex;
* Table 52 (st_id 72): the people habitually resident in each of the 158
  areas (مناطق), by nationality and sex.

**What is written.** For each governorate: population, males per hundred
females, median age, and people by nationality on the ethnicity field --
Kuwaitis (Table 1), the other Gulf states' citizens (Table 6's Gulf group
less the Kuwaitis), and the rest by Table 6's groups. For each area the map
draws that the census counts as one area: population, males per hundred
females, and Kuwaiti against non-Kuwaiti nationals.

**Which area is which governorate's** is measured, not assumed: Table 52
lists the areas governorate by governorate, and the running sum of its rows
must close on each governorate's Table 1 total in turn, or the run stops.

**Binding an area.** The boundary file's labels are its own romanisations
("Bnaid_Al-QR", "Egaila"); each is paired below, by hand and one to one,
with the census's English name, and the pair must sit in the same
governorate. A drawn area left out of the table below is one the census does
not count on its own: drawn twice (Mina_Doha, Abdali), cut finer than the
census (the Shuwaikh industrial blocks, Sulaibiya's two agricultural
polygons), or with no census area of its name.

**Checks** (any failure stops the run): every table's rows add up (men and
women to the total, Kuwaitis and others to everyone); the governorates make
the census's total; age groups and nationality groups make each
governorate; the areas close on the governorates; each census area is
bound once.

Usage:
    python -m scripts.fetch_census.kuwait_census
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .west_asia_common import check, median_age, sex_ratio, units, workbook

ISO3 = "KWT"
OUT = "kuwait_census.json"
YEAR = 2021
EXPORT = "https://census.csb.gov.kw/CensusData?st_id={}&handler=ExportExcel"
TABLES = {"nationality": 4, "ages": 5, "groups": 26, "areas": 72}
PAGE = "https://census.csb.gov.kw/CensusData_EN?id=1"
SOURCE = ("Central Statistical Bureau (Kuwait), Register-based Census 2021, Table {}")
LICENCE = "Central Statistical Bureau of Kuwait, published census tables"
DECISION = "19 September 2026"
# The census's total, the first figure on census.csb.gov.kw: 4,385,717.
NATIONAL = 4_385_717
# Table 1's governorates, in the order the area table lists them, and the
# boundary file's labels for them.
GOVERNORATES = {
    "The Capital": "Al Asimah",
    "Hawalli": "Hawalli",
    "Al-Ahmadi": "Ahmadi",
    "Al-Jahra": "Jahra",
    "Al-Farwaniya": "Farwaniya",
    "Mubarak Al-Kabeer": "Mubarak Al-Kabeer",
}
# Table 6's nationality groups, as the map writes them.
GROUPS = {
    "Gulf": None,             # split into Kuwaitis and other GCC citizens
    "Arabic": "Other Arab nationalities",
    "Asian": "Asian nationalities",
    "African": "African nationalities",
    "European": "European nationalities",
    "North America": "North American nationalities",
    "South America": "South American nationalities",
    "Australian": "Australian",
}
# The boundary file's area label -> the census's English area name (Table 52).
AREAS = {
    # The Capital
    "Abdulla_Al-Salem": "ABDULLAH AL-SALEM", "Adailiya": "AL-ADAILIYA",
    "Bnaid_Al-QR": "BNIED AL-GAR", "Daiya": "AL-DAIYA", "Dasma": "AL-DASMA",
    "Dasman": "DASMAN", "Doha": "AL-DOHA RESIDENTIAL", "Faiha": "AL-FAIHA",
    "Fylaka": "FAILAKA ISLAND", "Ghornata": "GARNATA", "Khaldiya": "AL-KHALIDIYA",
    "Kifan": "KAIFAN", "Mansouriya": "AL-MANSOURIA", "Mirqab": "AL-MURGAB",
    "Mubarakiya_Camps": "AL-MUBARAKIYA CAMPS", "Nuzha": "AL-NUZHA",
    "Qadsiya": "AL-QADISIYA", "Qibla": "AL-QIBLA", "Qortuba": "QURTOBA",
    "Rawda": "AL-RAWDA", "Shamiya": "AL-SHAMIYA", "Sharq": "AL-SHARQ",
    "Shuwaikh_Health": "AL-SHUWAIKH MEDICAL", "Sulaibikhat": "AL-SULAIBIKHAT",
    "Surra": "AL-SURA", "Suwaikh": "AL-SHUWAIKH", "Yarmouk": "AL-YARMOUK",
    # Al-Nahda, the old East Sulaibikhat: the boundary file draws it in the
    # Capital, the census counts it in Al-Jahra (see CROSSING).
    "Elnahda_Shark_Elsolybekhat": "AL-NAHDA",
    # Hawalli
    "Angafa": "ANJAFA", "Bayan": "BAYAN", "Hawalli": "HAWALLI", "Hitteen": "HATEEN",
    "Jabriya": "AL-JABRIYA", "Mishrift": "MISHRIEF",
    "MubarakAlAbdullah_MishriftWest": "MUBARAK AL-ABDULLAH",
    "Rumaithiya": "AL-RUMAITHIYA", "Salam": "AL-SALAM", "Salmiya": "AL-SALMIYA",
    "Salwa": "SALWA", "Shaab": "ALSHAAB", "Shuhada": "AL-SHUHADA",
    "Siddiq": "AL-SIDDIQ", "Zahra": "AL-ZAHRA",
    # Al-Ahmadi
    "Abu_Halifa": "ABU HALIFA", "Al_Fantas": "AL-FINTAS",
    "Bar_Elahmadi": "AL-AHMADI GOVERNORATE DESERT", "Dhaher": "AL-DHAHER",
    "Egaila": "AL-AQILA", "El_Zoor": "AL-ZOOR", "Elahmdi": "AL-AHMADI CITY",
    "Fahad_Al-Ahmad": "FAHAD AL-AHMAD AL-JABER", "Fahaheel": "AL-FAHAHEEL",
    "Hadiya": "HADIYA", "Jaber_Al-Ali": "JABER AL-ALI", "Mahboula": "AL-MAHBULA",
    "Mangaf": "ALMANGAF", "Mina_Abdulla": "ABDULLAH PORT", "Riqqa": "AL-RIQQA",
    "Sabahiya": "AL-SABAHIYA", "South_Sabahiya": "SOUTH AL-SABAHIYA",
    "UmAl-Hayman-AliSabahAs-Salem": "ALI SABAH AL-SALIM",
    # Al-Jahra
    "Amghara": "AMGHARA INDUSTRIAL", "Bar Jahra": "AL-JAHRA GOVERNORATE DESERT",
    "Jahra": "AL-JAHRA", "Jahra_Industrial": "AL-JAHRA INDUSTRIAL 1", "Kabad": "KABAD",
    "Makaber_Elsolybekhat": "AL-SULAIBIKHAT CEMETERY", "Naeem": "AL-NAEEEM",
    "Nasseem": "AL-NASSEEM", "Oyoun": "AL-OYOUN", "Qasr": "AL-QASR",
    "Sad_Elabdallah": "SAAD AL-ABDULLAH", "Salmy": "AL-SALMI",
    "Sulaibiya": "AL-SULAIBIYA RESIDENTIAL",
    "Sulaibiya_Industrial_1": "AL-SULAIBIYA INDUSTRAIL 1",
    "Sulaibiya_Industrial_2": "AL-SULAIBIYA INDUSTRAIL 2", "Taima": "TAIMA",
    "Waha": "AL-WAHA",
    # Al-Farwaniya
    "Airport_District": "THE AIRPORT", "Andalous": "AL-ANDALUS", "Ardhiya": "AL-ARDIYA",
    "Ardhiya_Herafiya": "AL-ARDIYA INDUSTRIAL", "Ardhiya_Makhzen": "AL-ARDIYA STORES",
    "Ashbelya": "ASHBELYA", "Dhajeej": "AL-DHAJEEJ", "Farwaniya": "AL-FARAWANIYA",
    "Ferdous": "AL-FORDOUS", "Jleeb_Al- Shiyoukh": "JLEEB AL-SHUYOUKH",
    "Khaitan": "KHAITAN", "Omariya": "AL-OMARIYA", "Rabiya": "AL-RABIYA", "Rai": "AL-RAI",
    "Rehab": "AL-RIHAB", "Riggai": "AL-RIGGAE", "Sabah_Al_Nasser": "SABAH AL-NASSER",
    # Abdullah Al-Mubarak Al-Sabah, built as "West Jleeb" and still so called.
    "West_Jleedb": "ABDULLAH AL-MUBARAK",
    # Mubarak Al-Kabeer
    "Abo_Elhaseena": "ABU AL-HASANIYA", "Abu_Fataira": "ABU FUTAIRA", "Al_Adan": "AL-ADAN",
    "Al_Qurain": "AL-QURIAN", "Fnaitees": "AL-FUNAITEES", "Messila": "AL-MISILA",
    "Mubarak_Al_Kabeer": "MUBARAK AL-KABEER", "Sabah_Al-Salem": "SABAH AL-SALEM",
    "Subhan": "SABHAN INDUSTRAIL",
}
# Areas the census counts in another governorate than the boundary file draws.
CROSSING = {"AL-NAHDA": ("Al-Jahra", "Al Asimah")}
SEXES = ("Male", "Female", "Total")


def numbers(row: list[Any]) -> list[float]:
    return [float(c) for c in row if isinstance(c, (int, float)) and not isinstance(c, bool)]


ARABIC = re.compile(r"[؀-ۿ]")


def english(row: list[Any]) -> list[str]:
    """A row's English labels: text cells with no Arabic letter, spaces made plain."""
    out = []
    for c in row:
        if not isinstance(c, str):
            continue
        text = " ".join(c.replace("\xa0", " ").split())
        if text and not ARABIC.search(text) and re.search(r"[A-Za-z0-9>]", text):
            out.append(text)
    return out


def governorate_of(label: str) -> str | None:
    text = re.sub(r"\s*Governorate\s*$", "", label.strip(), flags=re.I)
    return text if text in GOVERNORATES else None


def table1(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Governorate -> Kuwaiti/other/all by sex, from Table 1."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        words, figures = english(row), numbers(row)
        if len(figures) != 9 or not words:
            continue
        gov = governorate_of(words[-1])
        name = gov or words[-1]
        km, kf, kt, nm, nf, nt, tm, tf, tt = figures
        for a, b, c, what in ((km, kf, kt, "Kuwaitis"), (nm, nf, nt, "others"),
                              (tm, tf, tt, "everyone")):
            check(a + b == c, f"kuwait_census: Table 1 {name} {what}: {a:,.0f} + {b:,.0f} "
                              f"!= {c:,.0f}")
        check(kt + nt == tt, f"kuwait_census: Table 1 {name}: nationalities do not make {tt:,.0f}")
        out[name] = {"kuwaiti": kt, "other": nt, "men": tm, "women": tf, "total": tt}
    check(set(GOVERNORATES) <= set(out), f"kuwait_census: Table 1 rows {sorted(out)}")
    made = sum(out[g]["total"] for g in GOVERNORATES) + out.get("Not Stated", {}).get("total", 0)
    check(out.get("Total", {}).get("total") == NATIONAL == made,
          f"kuwait_census: Table 1 makes {made:,.0f}, its total row "
          f"{out.get('Total', {}).get('total')}, the census {NATIONAL:,}")
    return out


AGE = re.compile(r"^(\d+)\s*-\s*(\d+)$|^>\s*(\d+)$")


def table2(rows: list[list[Any]]) -> dict[str, list[tuple[int, int | None, float]]]:
    """Governorate -> both sexes' five-year groups, from Table 2."""
    groups: dict[str, list[tuple[int, int | None, float]]] = {g: [] for g in GOVERNORATES}
    current = None
    for row in rows:
        words, figures = english(row), numbers(row)
        if len(figures) != 8:
            continue
        for w in words:
            m = AGE.match(w)
            if m:
                current = ((int(m.group(1)), int(m.group(2))) if m.group(1)
                           else (int(m.group(3)) + 1, None))
            elif w == "Total" and words.index(w) > 0:
                current = None
        if "Total" not in words[:1] or current is None:
            continue
        for gov, people in zip(GOVERNORATES, figures[:6]):
            groups[gov].append((current[0], current[1], people))
    for gov, got in groups.items():
        got.sort(key=lambda g: g[0])
        edge = 0
        for low, high, _n in got:
            check(low == edge, f"kuwait_census: Table 2 {gov}: age groups break at {edge}")
            edge = high + 1 if high is not None else -1
        check(got and got[-1][1] is None, f"kuwait_census: Table 2 {gov}: no open group")
    return groups


def table6(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Governorate -> nationality group -> people (both sexes), from Table 6."""
    out: dict[str, dict[str, float]] = {}
    current = None
    for row in rows:
        words, figures = english(row), numbers(row)
        # A block's first row carries its sex and its place ("Male", "Not
        # Stated"); the place holds until the next block's first row.
        if len(words) >= 2 and words[0] in SEXES:
            current = governorate_of(words[1])
        if len(figures) != len(GROUPS) + 1 or words[:1] != ["Total"] or current is None:
            continue
        check(sum(figures[:-1]) == figures[-1],
              f"kuwait_census: Table 6 {current}: groups do not make {figures[-1]:,.0f}")
        out[current] = dict(zip(GROUPS, figures[:-1])) | {"total": figures[-1]}
    check(set(GOVERNORATES) <= set(out), f"kuwait_census: Table 6 governorates {sorted(out)}")
    return out


def table52(rows: list[list[Any]], govs: dict[str, dict[str, float]]
            ) -> dict[str, dict[str, Any]]:
    """Area -> its people by nationality and sex, and its governorate.

    The governorate is found by the running sum: the rows close on each
    governorate's Table 1 total in Table 1's order, or the run stops.
    """
    areas: list[tuple[str, list[float]]] = []
    for row in rows:
        words, figures = english(row), numbers(row)
        if len(figures) != 9 or not words:
            continue
        name = words[-1]
        km, kf, kt, nm, nf, nt, tm, tf, tt = figures
        check(km + kf == kt and nm + nf == nt and tm + tf == tt and kt + nt == tt,
              f"kuwait_census: Table 52 {name}: its cells do not add up")
        areas.append((name, figures))
    out: dict[str, dict[str, Any]] = {}
    order = list(GOVERNORATES)
    gov_i, run = 0, 0.0
    for name, f in areas:
        if name in ("NOT STATED", "TOTAL"):
            continue
        check(gov_i < len(order), f"kuwait_census: Table 52 runs past the governorates at {name}")
        gov = order[gov_i]
        check(name not in out, f"kuwait_census: Table 52 lists {name} twice")
        out[name] = {"governorate": gov, "kuwaiti": f[2], "other": f[5], "men": f[6],
                     "women": f[7], "total": f[8]}
        run += f[8]
        if run == govs[gov]["total"]:
            gov_i, run = gov_i + 1, 0.0
        check(run < govs[gov]["total"], f"kuwait_census: Table 52's areas overrun {gov}")
    check(gov_i == len(order), f"kuwait_census: Table 52's areas close on {gov_i} governorates")
    return out


def nationality_shares(kuwaiti: float, other: float, total: float) -> list[dict[str, Any]]:
    return shares({"Kuwaiti": kuwaiti, "Foreign nationals": other}, total=total)


def build(t1: list[list[Any]], t2: list[list[Any]], t6: list[list[Any]], t52: list[list[Any]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          parents: dict[str, str]) -> list[dict[str, Any]]:
    govs = table1(t1)
    ages = table2(t2)
    groups = table6(t6)
    areas = table52(t52, govs)
    out: list[dict[str, Any]] = []
    drawn1 = {u["name"]: u for u in admin1}
    for gov, label in GOVERNORATES.items():
        check(label in drawn1, f"kuwait_census: {label} is not drawn")
        g = govs[gov]
        aged = sum(n for _a, _b, n in ages[gov])
        check(aged == g["total"], f"kuwait_census: {gov}'s age groups make {aged:,.0f}, "
                                  f"not {g['total']:,.0f}")
        grp = groups[gov]
        check(grp["total"] == g["total"], f"kuwait_census: Table 6 {gov} makes "
                                          f"{grp['total']:,.0f}, not {g['total']:,.0f}")
        check(grp["Gulf"] >= g["kuwaiti"], f"kuwait_census: {gov}: fewer Gulf citizens than "
                                           f"Kuwaitis")
        counts = {"Kuwaiti": g["kuwaiti"], "GCC nationals": grp["Gulf"] - g["kuwaiti"]}
        counts.update({lab: grp[k] for k, lab in GROUPS.items() if lab})
        population = measure(g["total"], year=YEAR, source=SOURCE.format(1))
        population["note"] = (f"The 2021 register-based census: {g['men']:,.0f} men and "
                              f"{g['women']:,.0f} women.")
        out.append(record(
            f"KWT-CEN2021-{label}", label, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=drawn1[label]["id"],
            aliases=[f"{gov} Governorate"],
            population=population,
            sex_ratio=sex_ratio(g["men"], g["women"], year=YEAR, source=SOURCE.format(1)),
            sex_ratio_note=f"Males per 100 females in the 2021 census: {g['men']:,.0f} men and "
                           f"{g['women']:,.0f} women.",
            median_age=median_age(ages[gov], year=YEAR, source=SOURCE.format(2)),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person, from the 2021 census's count of the governorate by "
                             "five-year age group (Table 2)."),
            ethnicity=shares({k: v for k, v in counts.items() if v}, total=g["total"]),
            ethnicity_year=YEAR, ethnicity_basis="nationality",
            ethnicity_note=(
                "Nationality, not ethnicity: the census counts citizenship and no ethnic "
                f"group. Carried on this field under the owner's decision of {DECISION}. "
                "Kuwaitis are Table 1's; GCC nationals are Table 6's Gulf group less the "
                "Kuwaitis; the rest are Table 6's groups of other countries' citizens."),
            sources=[{"field": "population/sex_ratio/median_age/ethnicity",
                      "name": SOURCE.format("1, 2 and 6"), "url": PAGE, "year": YEAR,
                      "license": LICENCE}]))
    # Areas.
    labels: dict[str, list[dict[str, Any]]] = {}
    for unit in admin2:
        labels.setdefault(unit["name"], []).append(unit)
    used: set[str] = set()
    for label, census_name in AREAS.items():
        found = labels.get(label, [])
        check(len(found) == 1, f"kuwait_census: {len(found)} drawn areas are labelled {label!r}")
        unit = found[0]
        hits = [a for a in areas if a == census_name]
        check(len(hits) == 1, f"kuwait_census: no census area {census_name!r} for {label}")
        a = areas[census_name]
        check(census_name not in used, f"kuwait_census: {census_name} bound twice")
        used.add(census_name)
        drawn_gov = parents.get(unit["parent"])
        census_gov = GOVERNORATES[a["governorate"]]
        if (census_gov != drawn_gov
                and CROSSING.get(census_name) != (a["governorate"], drawn_gov)):
            raise SystemExit(f"kuwait_census: {label} is drawn in {drawn_gov}, the census "
                             f"counts {census_name} in {census_gov}")
        population = measure(a["total"], year=YEAR, source=SOURCE.format(52))
        population["note"] = (f"The 2021 register-based census's habitual residents of "
                              f"{census_name.title()}: {a['men']:,.0f} men and "
                              f"{a['women']:,.0f} women."
                              + (f" The census counts the area in {census_gov}."
                                 if census_gov != drawn_gov else ""))
        out.append(record(
            f"KWT-CEN2021-{label}", label, level="admin2", parent=ISO3, country=ISO3,
            parent_name=drawn_gov, match_by="shape_id", shape_id=unit["id"],
            aliases=[census_name.title()],
            population=population,
            sex_ratio=(sex_ratio(a["men"], a["women"], year=YEAR, source=SOURCE.format(52))
                       if a["women"] else None),
            sex_ratio_note=(f"Males per 100 females in the 2021 census: {a['men']:,.0f} men "
                            f"and {a['women']:,.0f} women." if a["women"] else None),
            ethnicity=nationality_shares(a["kuwaiti"], a["other"], a["total"])
            if a["total"] else None,
            ethnicity_year=YEAR if a["total"] else None,
            ethnicity_basis="nationality" if a["total"] else None,
            ethnicity_note=(
                "Nationality, not ethnicity: Kuwaiti citizens and everyone else, as Table 52 "
                f"counts them. Carried on this field under the owner's decision of "
                f"{DECISION}.") if a["total"] else None,
            sources=[{"field": "population/sex_ratio/ethnicity", "name": SOURCE.format(52),
                      "url": PAGE, "year": YEAR, "license": LICENCE}]))
    left = sorted(set(labels) - set(AREAS))
    log(f"  areas bound: {len(AREAS)} of {len(admin2)} drawn; census areas unused: "
        f"{len(areas) - len(used)}")
    log(f"  drawn areas the census does not count alone: {len(left)}: {'; '.join(left)}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    sheets = {k: next(iter(workbook(EXPORT.format(v)).values())) for k, v in TABLES.items()}
    admin1, admin2 = units(ISO3, "admin1"), units(ISO3, "admin2")
    parents = {u["id"]: u["name"] for u in admin1}
    rows = build(sheets["nationality"], sheets["ages"], sheets["groups"], sheets["areas"],
                 admin1, admin2, parents)
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
