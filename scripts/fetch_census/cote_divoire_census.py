#!/usr/bin/env python3
"""Côte d'Ivoire -- the 2021 census (RGPH 2021) by region, from ANStat's regional pages.

The national statistics agency (ANStat, formerly INS) published the 2021
census's results for each of the 31 regions and the two autonomous districts
on its census site, rp2021.anstat.ci: a page per region with its seat ("Sa
capitale est Bouaké"), its departments' seats, and a synoptic table of the
region against the country -- everyone by sex in 2021 (and 1998), the mean age,
the population in broad age groups -- and a paragraph giving the share of
Ivorians among its residents. The site refuses an automated client; the
Internet Archive's captures of January 2026 are read instead.

Written for each region and autonomous district: population and sex ratio
(2021), its seat where the map names none, and the Ivorian and non-Ivorian
shares of its people on the ethnicity field under its basis (nationality: the
census's question is nationality, and the page gives only those two shares).
The median age says why there is none: the table gives the mean age and broad
groups only. Each of the 14 districts takes its regions added together; the map
draws the two autonomous districts at both levels. The pages name no seat for a
district of several regions: its seat is the one English Wikipedia's table of the
districts (set up by Décret n° 2011-263 of 28 September 2011) gives it, written
where that is also the seat of one of its regions on the census's pages; failing
that, the district names its regions and their seats.
Where a page prints the country's column wrongly ("29 276 660,00", "29
389150") or a region's figure with a space misplaced ("61 2029"), the figure
is read only as far as the men and women make it.

**Checks before anything is written.** Each table's men and women make its
total, for 2021 and for 1998; the national column is the census's 29,389,150;
the regions make the country within the table's rounding; every region and
district on the map is found once.

The archive refuses connections in bursts: a page not reached is tried again
in two later passes, and a page still refused keeps the figures an earlier run
read from it (kept, with the day they were read, in
cote_divoire_census_pages.json beside the output).

Usage:
    python -m scripts.fetch_census.cote_divoire_census
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json

SITE_URL = "https://rp2021.anstat.ci/"
ARCHIVE = "https://web.archive.org/web/2026/" + SITE_URL
# The capture as the site served it, without the archive's own frame.
ARCHIVE_RAW = "https://web.archive.org/web/2026id_/" + SITE_URL
PAUSE = 3
SOURCE = ("Agence Nationale de la Statistique (ANStat) de Côte d'Ivoire, Recensement Général de "
          "la Population et de l'Habitat (RGPH) 2021, regional monograph page, Tableau "
          "synoptique de la région")
LICENCE = "ANStat publication (reuse with attribution)"
YEAR = 2021
NATIONAL = (15_344_990, 14_044_160, 29_389_150)
OUT = "cote_divoire_census.json"
# Each page's reading, kept from run to run: the archive refuses connections in
# bursts, and a page it refuses this time keeps the figures read from it before.
MEMORY = "cote_divoire_census_pages.json"
PASSES, REST = 3, 90
SITE = PROCESSED.parent.parent / "site" / "data"

# The census site's page for each region, and the map's name for it (folded).
PAGES = {
    "district-autonome-abidjan-mono": "districtautonomedabidjan",
    "district-autonome-yamoussoukro-mono": "districtautonomedeyamoussoukro",
    "mono-region-gbokle": "gbokle", "mono-region-nawa": "nawa",
    "mono-region-de-san-pedro": "sanpedro", "region-indenie-djuablin-mono": "indeniedjuablin",
    "region-sud-comoe-mono": "sudcomoe", "region-folon-mono": "folon",
    "region-kabadougou-mono": "kabadougou", "region-goh-mono": "goh",
    "region-loh-djiboua-mono": "lohdjiboua", "region-belier-mono": "belier",
    "region-iffou-mono": "iffou", "region-moronou-mono": "moronou", "region-nzi-mono": "nzi",
    "region-agneby-tiassa-mono": "agnebytiassa", "region-grands-ponts-mono": "grandsponts",
    "region-la-me-mono": "me", "region-cavally-mono": "cavally", "region-guemon-mono": "guemon",
    "region-tonkpi-mono": "tonkpi", "region-haut-sassandra-mono": "hautsassandra",
    "region-marahoue-mono": "marahoue", "region-bagoue-mono": "bagoue",
    "region-poro-mono": "poro", "region-tchologo-mono": "tchologo",
    "region-gbeke-mono": "gbeke", "region-hambol-mono": "hambol",
    "region-bafing-mono": "bafing", "region-bere-mono": "bere",
    "region-du-worodougou-mono": "worodougou", "region-bounkani-mono": "bounkani",
    "region-gontougo-mono": "gontougo",
}
# The seat of each district of several regions, from the "District capital" column of
# English Wikipedia's table of the districts, which the reorganisation of 28 September
# 2011 set up (Décret n° 2011-263). The census's pages name the regions' seats only;
# a district's seat is written where it is also the seat of one of its regions there.
DISTRICT_SEATS = {
    "bassassandra": "San-Pédro", "comoe": "Abengourou", "denguele": "Odienné",
    "gohdjiboua": "Gagnoa", "lacs": "Dimbokro", "lagunes": "Dabou", "montagnes": "Man",
    "sassandramarahoue": "Daloa", "savanes": "Korhogo", "valleedubandama": "Bouaké",
    "woroba": "Séguéla", "zanzan": "Bondoukou",
}
# The map's spelling of a district where it differs from the table's (folded).
MAP_SPELLING = {"valledubandama": "valleedubandama"}
SEATS_SOURCE = {"field": "capital", "name": "English Wikipedia, Districts of Ivory Coast",
                "url": "https://en.wikipedia.org/wiki/Districts_of_Ivory_Coast",
                "license": "CC BY-SA 4.0"}
NO_MEDIAN = ("The 2021 census's synoptic table for the {unit} gives the mean age ({mean} "
             "years) and the population in a few broad age groups (under 5, under 15, under 18, "
             "15 to 64, 60 and over, 65 and over), from which no median age can be taken.")


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def strip(page: str) -> str:
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()


def readings(tokens: list[str], start: int) -> list[tuple[int, int]]:
    """(value, end) for each way a number can be read from tokens[start:]."""
    if start >= len(tokens) or not tokens[start].isdigit():
        return []
    first = tokens[start]
    if len(first) > 3:
        return [(int(first), start + 1)]
    out, j = [(int(first), start + 1)], start + 1
    while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
        j += 1
        out.append((int("".join(tokens[start:j])), j))
    return out


def row_numbers(text: str, label: str, national: int) -> list[list[int | None]]:
    """The candidate (region 2021, region 1998) readings of a synoptic row, after
    the country's own figure; 1998 is None where the table gives '-'."""
    # The country's figure as some pages print it: "29 389150", "29 389 150,00".
    spaced = r"\s*".join(str(national)) + r"(?:,00)?"
    text = re.sub(rf"(?<=\s){spaced}(?=\s)", str(national), text)
    m = re.search(rf"{label}\s+((?:[\d-]+(?:,00)?\s+){{1,12}})", text + " ")
    if not m:
        raise SystemExit(f"cote_divoire_census: no row {label!r}")
    tokens = [t[:-3] if t.endswith(",00") else t for t in m.group(1).split()]
    starts = [end for value, end in readings(tokens, 0) if value == national]
    if not starts:
        # The country's column misprinted on a page: any reading near it.
        starts = [end for value, end in readings(tokens, 0)
                  if abs(value - national) <= national // 100]
    if not starts:
        raise SystemExit(f"cote_divoire_census: {label!r} does not open with {national:,}: "
                         f"{' '.join(tokens)}")
    out = []
    # A region's figure with its space misplaced ("61 2029" for 612,029) is
    # also offered, joined: only a reading the men and women make is taken.
    joined = [(int("".join(tokens[starts[0]:starts[0] + k])), starts[0] + k) for k in (2, 3)
              if len(tokens) >= starts[0] + k
              and all(t.isdigit() for t in tokens[starts[0]:starts[0] + k])]
    for value, end in readings(tokens, starts[0]) + joined:
        rest = tokens[end:]
        if rest and rest[0] == "-":
            out.append([value, None])
        for old, old_end in readings(tokens, end):
            out.append([value, old])
    return out


def synoptic(text: str) -> dict[str, Any]:
    """The region's 2021 (and 1998) men, women and total, and its mean age."""
    total = row_numbers(text, "Population totale", NATIONAL[2])
    men = row_numbers(text, "Population masculine", NATIONAL[0])
    women = row_numbers(text, "Population f[ée]minine", NATIONAL[1])
    # A region has well over 50,000 people; a reading of "1 352 900" as 1,352
    # (and the rest as 1998's) is the digits split in the wrong place.
    for t in (t for t in total if t[0] >= 50_000):
        for m in men:
            for w in women:
                if abs(m[0] + w[0] - t[0]) > 1:
                    continue
                if None not in (t[1], m[1], w[1]) and abs(m[1] + w[1] - t[1]) > 1:
                    continue
                mean = re.search(r"(?i)[AÂ]ge\s+moyen\s+de\s+la\s+population\s*"
                                 r"(?:\(ans\))?\s+([\d,]+)\s+([\d,]+)", text)
                return {"men": m[0], "women": w[0], "total": t[0],
                        "mean": mean.group(2).replace(",", ".") if mean else None}
    raise SystemExit("cote_divoire_census: the synoptic table's sexes do not make its total")


def shares(text: str) -> tuple[float, float] | None:
    """(Ivorian %, non-Ivorian %) from the page's sentence on nationality, however
    worded ("composée à 91,1% d'Ivoiriens et 8,9% non ivoiriens", "de 76,5 %
    d'Ivoiriens et de 23,5 % de non-Ivoiriens"...): its first two percentages, the
    one followed by "non" being the other nationals' share, and the two making 100."""
    at = re.search(r"(?i)Nationalit[ée]\s*:", text)
    if not at:
        return None
    sentence = text[at.end():at.end() + 260]
    found = list(re.finditer(r"(\d+(?:[,.]\d+)?)\s*%", sentence))[:2]
    if len(found) != 2:
        return None
    own = other = None
    for m in found:
        value = float(m.group(1).replace(",", "."))
        after = fold(sentence[m.end():m.end() + 24])
        if after.startswith(("non", "denon", "dnon", "dentrangers", "detrangers", "detranger")):
            other = value
        elif re.match(r"(?:d|de|des)?ivoirien", after):
            own = value
    if own is None or other is None or abs(own + other - 100) > 0.5:
        return None
    return own, other


def page_facts(text: str) -> dict[str, Any]:
    facts = synoptic(text)
    # The seat as the page's heading prints it, in capitals (the heading lists
    # the departments' seats before or after it); spelled as the page's
    # sentence spells it where the two are the same name.
    # The heading's seat runs to the next heading word (CHEF LIEU, POPULATION,
    # SUPERFICIE, DISTRICT) or to the first word not in capitals ("ABOISSO Sud
    # Comoe - Tableau..."); an autonomous district's says only "CHEF LIEU".
    head = re.search(r"CHEF[ -]LIEU\s+(?:(?:DE\s+)?(?:LA\s+)?R[EÉ]GION\s*)?:\s*(.+?)"
                     r"(?=\s+(?:CHEF[ -]LIEU|POPULATION|SUPERFICIE|DISTRICT)\b"
                     r"|\s+[A-Z][a-zà-ÿ]|\s*$)", text)
    said = re.search(r"(?:Sa capitale|Son chef-lieu) est ([^.]+?)\s*(?:\.|CHEF)", text)
    seat = head.group(1).strip(" ,;") if head else None
    if said and (seat is None or fold(said.group(1)) == fold(seat)):
        seat = said.group(1).strip()
    elif seat and seat.isupper():
        seat = seat.title()
    if seat and (len(seat) > 40 or ":" in seat):
        seat = None                        # more than a name was taken
    facts["seat"] = seat
    facts["ivorian"] = shares(text)
    return facts


def around(text: str, pattern: str, width: int = 260) -> str:
    m = re.search(pattern, text)
    return text[max(0, m.start() - 40):m.start() + width] if m else "(nothing)"


def nationality(shares: tuple[float, float], unit: str) -> dict[str, Any]:
    ivorian, other = shares
    return {"ethnicity": [{"group": "Ivorian", "pct": ivorian},
                          {"group": "Non-Ivorian", "pct": other}],
            "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
            "ethnicity_note": ("Nationality, not ethnicity: the 2021 census's shares of "
                               f"Ivorians and of other nationals among the {unit}'s residents, "
                               "as ANStat's regional page gives them; it gives no breakdown "
                               "by ethnic group or by country.")}


def build(facts: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    report: list[str] = []
    by_key = {PAGES[slug]: f for slug, f in facts.items()}
    src = {"name": SOURCE, "url": SITE_URL, "license": LICENCE, "year": YEAR}
    parents: dict[str, list[dict[str, Any]]] = {}
    for shape in admin2:
        f = by_key.get(fold(shape["name"]))
        if f is None:
            report.append(f"region polygon {shape['name']!r}: no page")
            continue
        parents.setdefault(shape["parent"], []).append({**f, "region": shape["name"]})
        unit = "region" if not shape["name"].startswith("District") else "district"
        fields: dict[str, Any] = {
            "population": measure(f["total"], year=YEAR, source=SOURCE),
            "sex_ratio": measure(round(1000 * f["men"] / f["women"]),
                                 unit="males_per_1000_females", year=YEAR, source=SOURCE),
            "median_age": gap(NOT_AVAILABLE, NO_MEDIAN.format(unit=unit, mean=f["mean"] or "?"))
            if f["mean"] else gap(NOT_AVAILABLE),
        }
        cited = ["population", "sex_ratio"]
        if f["seat"]:
            fields["capital"] = f["seat"]
            cited.append("capital")
        if f["ivorian"]:
            fields.update(nationality(f["ivorian"], unit))
            cited.append("ethnicity")
        records.append(record(f"CIV-RGPH2021-{fold(shape['name'])}", shape["name"],
                              level="admin2", parent="CIV", country="CIV", match_by="shape_id",
                              shape_id=shape["id"],
                              sources=[{**src, "field": "/".join(cited)}], **fields))
    drawn = {}
    for shape in admin2:
        drawn[shape["parent"]] = drawn.get(shape["parent"], 0) + 1
    for shape in admin1:
        parts = parents.get(shape["id"], [])
        if not parts or len(parts) != drawn.get(shape["id"]):
            report.append(f"district polygon {shape['name']!r}: {len(parts)} of its "
                          f"{drawn.get(shape['id'], 0)} regions read")
            continue
        men, women, total = (sum(p[k] for p in parts) for k in ("men", "women", "total"))
        fields = {
            "population": measure(total, year=YEAR, source=SOURCE),
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "median_age": gap(NOT_AVAILABLE, (
                "The 2021 census's synoptic tables give each region's mean age and broad age "
                "groups only, from which no median age can be taken.")),
        }
        sources = []
        if len(parts) > 1:
            fields["population_note"] = ("The 2021 census's counts of the district's "
                                         f"{len(parts)} regions, added.")
            seat, region = district_seat(shape["name"], parts)
            if seat:
                fields["capital"] = seat
                fields["capital_note"] = (
                    f"{seat} is the district's seat, as English Wikipedia's table of the "
                    "districts set up by Décret n° 2011-263 of 28 September 2011 gives it; it "
                    f"is also the seat of the {region} region on the 2021 census's pages.")
                sources.append(dict(SEATS_SOURCE))
            else:
                report.append(f"district polygon {shape['name']!r}: the table's seat "
                              f"{DISTRICT_SEATS.get(district_key(shape['name']))!r} is none of "
                              f"its regions' seats {[p['seat'] for p in parts]}")
                named = [f"{p['region']} (seat {p['seat']})" if p["seat"] else p["region"]
                         for p in parts]
                fields["capital"] = gap(NOT_AVAILABLE, (
                    "The district groups the regions of " + ", ".join(named[:-1]) + " and "
                    + named[-1] + ", as the 2021 census's regional pages give them; they name "
                    "no seat for the district itself."))
        elif parts[0]["seat"]:
            # An autonomous district is one region: its page names the city.
            fields["capital"] = parts[0]["seat"]
        cited = ["population", "sex_ratio"] + (["capital"] if isinstance(fields.get("capital"), str)
                                                and not sources else [])
        records.append(record(f"CIV-RGPH2021-district-{fold(shape['name'])}", shape["name"],
                              level="admin1", parent="CIV", country="CIV", match_by="shape_id",
                              shape_id=shape["id"],
                              sources=[{**src, "field": "/".join(cited)}] + sources, **fields))
    return records, report


def district_key(name: str) -> str:
    key = fold(name)
    return MAP_SPELLING.get(key, key)


def district_seat(name: str, parts: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """The seat the table gives a district of several regions, and the region whose seat
    it also is on the census's pages; (None, None) unless one of them agrees."""
    seat = DISTRICT_SEATS.get(district_key(name))
    if seat:
        for p in parts:
            if p["seat"] and fold(p["seat"]) == fold(seat):
                return seat, p["region"]
    return None, None


def remember(memory: dict[str, Any], slug: str, f: dict[str, Any], url: str,
             day: str) -> None:
    """Keep a page's reading, so that a later run the archive refuses can use it."""
    memory[slug] = {"men": f["men"], "women": f["women"], "total": f["total"],
                    "mean": f["mean"], "seat": f["seat"],
                    "ivorian": list(f["ivorian"]) if f["ivorian"] else None,
                    "url": url, "read": day}


def recalled(memory: dict[str, Any], slug: str) -> dict[str, Any] | None:
    """An earlier run's reading of a page, checked as a fresh one would be."""
    kept = memory.get(slug)
    if not isinstance(kept, dict):
        return None
    try:
        men, women, total = int(kept["men"]), int(kept["women"]), int(kept["total"])
    except (KeyError, TypeError, ValueError):
        return None
    if abs(men + women - total) > 1 or total < 50_000:
        return None
    ivorian = kept.get("ivorian")
    return {"men": men, "women": women, "total": total, "mean": kept.get("mean"),
            "seat": kept.get("seat"),
            "ivorian": (float(ivorian[0]), float(ivorian[1])) if ivorian else None}


def fetch(slug: str) -> tuple[str | None, str | None]:
    """The page as the archive's raw capture, or its framed one, and the address used."""
    for url in (ARCHIVE_RAW + slug + "/", ARCHIVE + slug + "/"):
        try:
            body = http_get(url, cache=False, timeout=90, retries=3)
            return (body if isinstance(body, str) else body.decode("utf-8", "replace")), url
        except Exception as err:  # noqa: BLE001 -- the other address, then the next page
            log(f"  {slug}: {url}: {type(err).__name__}: {err}")
            time.sleep(4 * PAUSE)
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    try:
        memory = json.loads((PROCESSED / MEMORY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        memory = {}
    if not isinstance(memory, dict):
        memory = {}
    day = time.strftime("%Y-%m-%d", time.gmtime())
    facts = {}
    pending = list(PAGES)
    for attempt in range(PASSES):
        if attempt:
            log(f"  pass {attempt + 1}: {len(pending)} pages not reached; trying them again "
                f"after {REST} s")
            time.sleep(REST)
        missed = []
        for n, slug in enumerate(pending):
            if n:
                time.sleep(PAUSE)          # the Internet Archive refuses a hurried client
            body, url = fetch(slug)
            if body is None:
                missed.append(slug)
                continue
            text = strip(body)
            try:
                f = page_facts(text)
            except SystemExit as err:
                at = text.find("Tableau Synoptique")
                log(f"  {slug}: {err} :: {text[at:at + 700] if at >= 0 else text[:300]}")
                continue
            log(f"  {slug}: {f['total']:,} ({f['men']:,} men), seat {f['seat']}, mean age "
                f"{f['mean']}, Ivorians {f['ivorian']}")
            if not f["seat"]:
                log(f"    its heading: {around(text, r'(?i)chef[ -]lieu|sa capitale')}")
            if not f["ivorian"]:
                log(f"    its nationality: {around(text, r'(?i)nationalit|ivoiriens')}")
            if not f["mean"]:
                log(f"    its ages: {around(text, r'(?i)ge moyen')}")
            facts[slug] = f
            remember(memory, slug, f, url or "", day)
        pending = missed
        if not pending:
            break
    for slug in pending:
        f = recalled(memory, slug)
        if f is None:
            log(f"  {slug}: not reached; left out")
            continue
        log(f"  {slug}: not reached; its reading of {memory[slug].get('read')} kept: "
            f"{f['total']:,} ({f['men']:,} men), seat {f['seat']}, mean age {f['mean']}, "
            f"Ivorians {f['ivorian']}")
        facts[slug] = f
    write_json(PROCESSED / MEMORY, {slug: memory[slug] for slug in PAGES if slug in memory})
    made = sum(f["total"] for f in facts.values())
    if len(facts) == len(PAGES) and abs(made - NATIONAL[2]) > 50:
        raise SystemExit(f"cote_divoire_census: the regions make {made:,}, not {NATIONAL[2]:,}")
    log(f"  {len(facts)} of {len(PAGES)} pages read; they make {made:,} against the "
        f"country's {NATIONAL[2]:,}")
    admin1 = json.loads((SITE / "admin1" / "CIV.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CIV.units.json").read_text())
    records, report = build(facts, admin1, admin2)
    for line in report:
        log("  " + line)
    if len(facts) < 30:
        raise SystemExit("cote_divoire_census: fewer than 30 regional pages read")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
