#!/usr/bin/env python3
"""Finland: the 70 sub-regions (seutukunnat) the map draws, from Statistics Finland.

**What the map draws.** The admin2 layer is Finland's sub-regions, named in a
mix of Finnish genitive ("Etelä-Pirkanmaan seutukunta"), English ("Helsinki
sub-region", "North Eastern Savonia") and Swedish ("Raseborgs ekonomiska
region", "Sydösterbotten"). Seventy of them, which is not today's count:
Statistics Finland's key figures for 2026 carry 69. ``DRAWN`` maps each drawn
name to the sub-region's name in the office's classification, written out by
hand because no rule turns "Haapaveden-Siikalatvan" into "Haapavesi-
Siikalatva"; the run then asks the classification service, year by year, for
the latest municipality-to-sub-region key whose sub-regions are exactly those
seventy, and uses that year's key. A drawn name the key does not have stops the
run.

**Population, median age, sex ratio.** Table 11rf gives the population on 31
December by municipality *in the regional division of each reference year*,
by single year of age (0-99, 100+) and sex. The municipalities of the chosen
year are summed into that year's sub-regions: every municipality in the table
must belong to exactly one of them, and the sub-regions must make the
country.

**Language.** Table 11rm gives the mother tongue recorded in the population
register on 31 December, by municipality in the current division. Each current
municipality is placed in the chosen year's sub-region by its code; a current
code the chosen key does not know stops the language field rather than guess
where it belongs. Every language the register records is kept; the two total
rows are not.

**Religion.** The register records every resident's religious community, and
Statistics Finland publishes it only for the whole country (StatFin 11rx,
"Belonging to a religious community by age and sex", which has no area
variable). Nothing below the country is written; the report says so.

**Ethnicity** is the existing policy: not recorded.

Usage:
    python -m scripts.fetch_census.finland
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import AgeSex, bind_rows, check_parts, request_json
from .pxweb import unstack

STATFIN = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/vaerak"
KEY = ("https://data.stat.fi/api/classifications/v2/correspondenceTables/"
       "kunta_1_{y}0101%23seutukunta_1_{y}0101/maps?content=data&meta=max&lang=fi")
SOURCE = "Statistics Finland"
AGE_URL = "https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/statfin_vaerak_pxt_11rf.px"
LANG_URL = "https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/statfin_vaerak_pxt_11rm.px"
OUT = PROCESSED / "finland_subregion.json"
PAUSE = 1.5                     # StatFin answers 429 to a brisker pace

# The boundary file's name -> the sub-region's name in Statistics Finland's
# classification (Finnish and nominative, or Swedish where the sub-region is
# Swedish-speaking: "Jakobstadsregionen", "Mariehamns stad").
DRAWN = {
    "Etelä-Pirkanmaan seutukunta": "Etelä-Pirkanmaa",
    "Forssan seutukunta": "Forssa",
    "Haapaveden-Siikalatvan seutukunta": "Haapavesi-Siikalatva",
    "Helsinki sub-region": "Helsinki",
    "Hämeenlinnan seutukunta": "Hämeenlinna",
    "Imatran seutukunta": "Imatra",
    "Itä-Lapin seutukunta": "Itä-Lappi",
    "Joensuun seutukunta": "Joensuu",
    "Joutsa": "Joutsa",
    "Jyväskylä": "Jyväskylä",
    "Jämsä": "Jämsä",
    "Järviseudun seutukunta": "Järviseutu",
    "Kajaanin seutukunta": "Kajaani",
    "Kaustisen seutukunta": "Kaustinen",
    "Kehys-Kainuun seutukunta": "Kehys-Kainuu",
    "Kemi-Tornion seutukunta": "Kemi-Tornio",
    "Keski-Karjalan seutukunta": "Keski-Karjala",
    "Keuruun seutukunta": "Keuruu",
    "Koillismaan seutukunta": "Koillismaa",
    "Kokkolan seutukunta": "Kokkola",
    "Kotkan–Haminan seutukunta": "Kotka-Hamina",
    "Kouvolan seutukunta": "Kouvola",
    "Kuopio sub-region": "Kuopio",
    "Kuusiokuntien seutukunta": "Kuusiokunnat",
    "Kyrönmaan seutukunta": "Kyrönmaa",
    "Lahden seutukunta": "Lahti",
    "Lappeenrannan seutukunta": "Lappeenranta",
    "Loimaan seutukunta": "Loimaa",
    "Lounais-Pirkanmaan seutukunta": "Lounais-Pirkanmaa",
    "Loviisan seutukunta": "Loviisa",
    "Luoteis-Pirkanmaan seutukunta": "Luoteis-Pirkanmaa",
    "Mariehamns stad": "Mariehamns stad",
    "Mikkelin seutukunta": "Mikkeli",
    "Nivala–Haapajärven seutukunta": "Nivala-Haapajärvi",
    "North Eastern Savonia": "Koillis-Savo",
    "Oulun seutukunta": "Oulu",
    "Oulunkaaren seutukunta": "Oulunkaari",
    "Pieksämäen seutukunta": "Pieksämäki",
    "Pielisen Karjalan seutukunta": "Pielisen Karjala",
    "Pietarsaaren seutukunta": "Jakobstadsregionen",
    "Pohjois-Lapin seutukunta": "Pohjois-Lappi",
    "Pohjois-Satakunnan seutukunta": "Pohjois-Satakunta",
    "Porin seutukunta": "Pori",
    "Porvoon seutukunta": "Porvoo",
    "Raahen seutukunta": "Raahe",
    "Raseborgs ekonomiska region": "Raasepori",
    "Rauman seutukunta": "Rauma",
    "Riihimäen seutukunta": "Riihimäki",
    "Rovaniemen seutukunta": "Rovaniemi",
    "Saarijärvi-Viitasaari": "Saarijärvi-Viitasaari",
    "Salon seutukunta": "Salo",
    "Savonlinnan seutukunta": "Savonlinna",
    "Seinäjoen seutukunta": "Seinäjoki",
    "Sisä-Savon seutukunta": "Sisä-Savo",
    "Suupohjan seutukunta": "Suupohja",
    "Sydösterbotten": "Sydösterbotten",
    "Tampereen seutukunta": "Tampere",
    "Torniolaakson seutukunta": "Torniolaakso",
    "Tunturi-Lapin seutukunta": "Tunturi-Lappi",
    "Turun seutukunta": "Turku",
    "Turunmaan seutukunta": "Turunmaa",
    "Vaasa sub-region": "Vaasa",
    "Vakka-Suomen seutukunta": "Vakka-Suomi",
    "Varkauden seutukunta": "Varkaus",
    "Ylivieskan seutukunta": "Ylivieska",
    "Ylä-Pirkanmaan seutukunta": "Ylä-Pirkanmaa",
    "Ylä-Savon seutukunta": "Ylä-Savo",
    "Äänekoski": "Äänekoski",
    "Ålands landsbygd": "Ålands landsbygd",
    "Ålands skärgård": "Ålands skärgård",
}


def item(entry: dict[str, Any], side: str) -> tuple[str, str]:
    node = entry[f"{side}Item"]
    names = node.get("classificationItemNames") or [{}]
    return node["code"], names[0].get("name", "")


def key_for(year: int) -> tuple[dict[str, str], dict[str, str]]:
    """{municipality code: sub-region code} and {sub-region code: name} for one year."""
    maps = request_json(KEY.format(y=year), pause=PAUSE)
    muni, names = {}, {}
    for entry in maps:
        k, _ = item(entry, "source")
        s, name = item(entry, "target")
        muni[k] = s
        names[s] = name
    return muni, names


def match(names: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Drawn name -> sub-region code, and the drawn names the key does not have."""
    whole: dict[str, list[str]] = defaultdict(list)
    parts: dict[str, list[str]] = defaultdict(list)
    for code, name in names.items():
        whole[fold(name)].append(code)
        for part in re.split(r"\s*[-–]\s*", name):
            parts[fold(part)].append(code)
    found, missing = {}, []
    for drawn, office in DRAWN.items():
        # A whole name first; a part of one only failing that, because the
        # classification may write a bilingual name ("Åboland-Turunmaa").
        hits = whole.get(fold(office)) or parts.get(fold(office), [])
        if len(hits) == 1:
            found[drawn] = hits[0]
        else:
            missing.append(f"{drawn} -> {office} ({len(hits)} hits)")
    return found, missing


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log("finland: Statistics Finland 11rf and 11rm by sub-region")
    meta = {v["code"]: v for v in request_json(f"{STATFIN}/11rf.px", pause=PAUSE)["variables"]}
    years = sorted(int(y) for y in meta["timeperiod_y"]["values"])
    chosen = None
    for year in range(years[-1] + 1, 2009, -1):
        try:
            muni, names = key_for(year)
        except SystemExit as exc:
            log(f"  key {year}: {exc}")
            continue
        found, missing = match(names)
        spare = sorted(f"{c} {n}" for c, n in names.items() if c not in set(found.values()))
        log(f"  key {year}: {len(names)} sub-regions; {len(found)} of {len(DRAWN)} drawn "
            f"names found" + (f"; missing {missing}; unclaimed {spare}" if missing else ""))
        if not missing and len(names) == len(DRAWN):
            chosen = (year, muni, names, found)
            break
    if chosen is None:
        raise SystemExit("finland: no year's sub-regions are the seventy the map draws")
    key_year, muni, names, found = chosen
    area = "kunta_85_20190101"
    codes = [f"KU{k}" for k in sorted(muni)]
    ages = [a for a in meta["ikaryhma_10_20180101"]["values"] if a != "SSS"]

    def read(data_year: int) -> tuple[dict[str, AgeSex], str | None]:
        """11rf for one year by the key's municipalities, or the reason it does not fit."""
        people: dict[str, AgeSex] = defaultdict(AgeSex)
        published: dict[str, float] = {}
        for chunk in (codes[i:i + 110] for i in range(0, len(codes), 110)):
            body = request_json(f"{STATFIN}/11rf.px", {"query": [
                {"code": area, "selection": {"filter": "item", "values": chunk}},
                {"code": "timeperiod_y", "selection": {"filter": "item", "values": [str(data_year)]}},
                {"code": "sukupuoli_9_20180101", "selection": {"filter": "item", "values": ["1", "2"]}},
                {"code": "ikaryhma_10_20180101", "selection": {"filter": "item", "values": ages + ["SSS"]}},
                {"code": "contentscode", "selection": {"filter": "item", "values": ["vaerak-vaesto"]}},
            ], "response": {"format": "json-stat2"}}, pause=PAUSE)
            for key, value in unstack(body):
                code, age = key[area][0], key["ikaryhma_10_20180101"][0]
                sex = key["sukupuoli_9_20180101"][0]
                if age == "SSS":
                    published[code] = published.get(code, 0.0) + value
                    continue
                people[code].add(int(age.rstrip("-")), "m" if sex == "1" else "f", value)
        national = request_json(f"{STATFIN}/11rf.px", {"query": [
            {"code": area, "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "timeperiod_y", "selection": {"filter": "item", "values": [str(data_year)]}},
            {"code": "sukupuoli_9_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "ikaryhma_10_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
            {"code": "contentscode", "selection": {"filter": "item", "values": ["vaerak-vaesto"]}},
        ], "response": {"format": "json-stat2"}}, pause=PAUSE)
        whole = next(value for _, value in unstack(national))
        for code, got in people.items():
            if abs(got.total - published.get(code, -1)) > 0.5:
                raise SystemExit(f"11rf {code}: single years make {got.total:,.0f}, the "
                                 f"table's total is {published.get(code)}")
        empty = [c for c in codes if people[c].total == 0]
        if empty:
            return people, f"municipalities of the {key_year} key with nobody: {empty}"
        summed = sum(people[c].total for c in codes)
        if abs(summed - whole) > 0.5:
            return people, (f"the key's municipalities make {summed:,.0f} against "
                            f"{whole:,.0f}")
        check_parts({c: people[c].total for c in codes}, whole,
                    f"11rf {data_year}: municipalities -> Finland", 0)
        return people, None

    # The key's own year first: 11rf lays each year out in "the regional
    # division of the statistical reference year". If that is the next
    # year's division, the key's municipalities will not all be there and the
    # year before is the one counted in the key's division.
    for data_year in (min(key_year, years[-1]), key_year - 1):
        people, why = read(data_year)
        if why is None:
            break
        log(f"  11rf {data_year} does not fit the {key_year} key: {why}")
    else:
        raise SystemExit(f"finland: 11rf has no year in the {key_year} division")
    log(f"  the map's sub-regions are those of {key_year}; population on 31 December "
        f"{data_year}")
    region_people: dict[str, AgeSex] = defaultdict(AgeSex)
    for k, s in muni.items():
        region_people[s] += people[f"KU{k}"]

    # Language, from the current municipalities placed by the chosen key.
    lmeta = {v["code"]: v for v in request_json(f"{STATFIN}/11rm.px", pause=PAUSE)["variables"]}
    larea = next(c for c in lmeta if c.startswith("alue"))
    lvar = next(c for c in lmeta if c.startswith("kieli"))
    lyear = lmeta["timeperiod_y"]["values"][-1]
    current = [c for c in lmeta[larea]["values"] if c.startswith("KU")]
    unknown = [c for c in current if c[2:] not in muni]
    language: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    language_total: dict[str, float] = defaultdict(float)
    withheld: dict[str, float] = {}
    if unknown:
        log(f"  current municipalities the {key_year} key does not place: {unknown}; "
            "no language is written")
    else:
        labels = dict(zip(lmeta[lvar]["values"], lmeta[lvar]["valueTexts"]))
        for chunk in (current[i:i + 60] for i in range(0, len(current), 60)):
            body = request_json(f"{STATFIN}/11rm.px", {"query": [
                {"code": larea, "selection": {"filter": "item", "values": chunk}},
                {"code": lvar, "selection": {"filter": "all", "values": ["*"]}},
                {"code": "sukupuoli_9_20180101", "selection": {"filter": "item", "values": ["SSS"]}},
                {"code": "timeperiod_y", "selection": {"filter": "item", "values": [lyear]}},
                {"code": "contentscode", "selection": {"filter": "item", "values": ["vaerak-vaesto"]}},
            ], "response": {"format": "json-stat2"}}, pause=PAUSE)
            for key, value in unstack(body):
                code, lang = key[larea][0], key[lvar][0]
                region = muni[code[2:]]
                if lang == "SSS":
                    language_total[region] += value
                elif lang not in ("01", "02"):
                    language[region][labels[lang]] += value
        # A municipality's small language counts are withheld for
        # confidentiality and come back empty, so the published languages
        # fall a little short of the published total. The shortfall is
        # people whose language is one of the withheld ones: it is added to
        # "Other language" and counted in the note. The Åland archipelago's
        # small municipalities lose a hundred people of 1,990 this way; more
        # than 2% of a sub-region, or 200 people where that is more, is not
        # suppression and stops the run.
        for region, counts in language.items():
            short = language_total[region] - sum(counts.values())
            if short < -0.5 or short > max(0.02 * language_total[region], 200):
                raise SystemExit(f"11rm: {names[region]}'s languages make "
                                 f"{sum(counts.values()):,.0f} of {language_total[region]:,.0f}")
            if short > 0.5:
                counts["Other language"] += short
                withheld[region] = short
        log(f"  11rm {lyear}: languages make each sub-region's total; withheld small counts "
            f"added to 'Other language' in {len(withheld)} sub-regions, "
            f"{sum(withheld.values()):,.0f} people in all")

    shapes_rows = {found[d]: (d, "") for d in DRAWN}
    bound, _m, _l, _p = bind_rows("FIN", "admin2", shapes_rows)
    date = f"31 December {data_year}"
    records = []
    for region, (drawn, _) in sorted(shapes_rows.items()):
        sid = bound.get(region)
        if sid is None:
            continue
        fields = region_people[region].fields(
            year=data_year, source=f"{SOURCE}, table 11rf", url=AGE_URL, date=date,
            extra_note=(f" Summed from the municipalities of the sub-region as Statistics "
                        f"Finland's {key_year} classification draws it, which is the map's."))
        if language.get(region):
            fields["language"] = shares(language[region], total=language_total[region])
            fields["language_year"] = int(lyear)
            fields["language_note"] = (
                f"Mother tongue as recorded in the population register on 31 December {lyear} "
                f"(Statistics Finland, table 11rm), summed from the sub-region's current "
                f"municipalities. One language per resident, so these are shares of everyone."
                + (f" {int(withheld[region]):,} people whose language Statistics Finland "
                   "withholds at municipal level as too small a count are in 'Other language'."
                   if withheld.get(region) else ""))
            fields["sources"].append({"field": "language", "name": f"{SOURCE}, table 11rm",
                                      "url": LANG_URL, "year": int(lyear)})
        records.append(record(
            f"FIN-SK{key_year}-{region}", names[region], level="admin2", parent="FIN",
            country="FIN", codes={"seutukunta": region, "vintage": key_year},
            match_by="shape_id", shape_id=sid, aliases=[drawn], **fields))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
