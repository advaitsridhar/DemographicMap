#!/usr/bin/env python3
"""Benin -- the 2013 census (RGPH-4): department ages and sexes, commune sexes.

INSAE (now INStaD) published the fourth census's results in a workbook of
principal indicators (*Doc_principaux_indicateurs*, "Résultats globaux") and a
leaflet for each of the 12 departments (*Synthèse des principaux résultats du
RGPH-4*, 2016). INStaD's site answers a script with 503; the Internet Archive's
captures of INStaD's own files are read instead.

* The workbook's sheet STRUCTURE_POPULATION (2) gives every department's
  population and its five-year age groups (as percentages of it); ETAT_POPULATION
  (2) gives the share of women in each department.
* Each leaflet's first table (*Evolution de la population ... de 2002 à 2013*)
  gives the department and each of its communes by sex, in 2013 and 2002.

**What this writes.** Each department's median age (interpolated within the
five-year group holding the middle person) and sex ratio, and each commune's
sex ratio, all of 2013: a census's figures, in front of OCHA's projections of
the same units. No population: OCHA's projected figures are newer counts of the
same ground.

**Checks before anything is written.** The departments make the country's
10,008,749; each department's age groups make 100% (to within half a point);
the national median taken from the departments' groups is within half a year of
the one taken from the country's own; in each leaflet every row's men and women
make its total (2013 and 2002), the communes make the department, and the
department's 2013 count is the workbook's; every department and commune on the
map is found once.

Usage:
    python -m scripts.fetch_census.benin_census
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .cod_ps_age import grouped_median

# The Internet Archive's captures, nearest these years (Donga's leaflet answers
# empty at the first three).
ARCHIVES = ["https://web.archive.org/web/2024id_/", "https://web.archive.org/web/2021id_/",
            "https://web.archive.org/web/2018id_/", "https://web.archive.org/web/2016id_/",
            "https://web.archive.org/web/2019id_/", "https://web.archive.org/web/2022id_/"]
FOLDER = ("instad.bj/images/docs/insae-statistiques/enquetes-recensements/RGPH/1.RGPH_4/"
          "resultats%20finaux/")
WORKBOOK = FOLDER + "Resultats%20globaux/Doc_principaux_indicateurs.xlsx"
# The map's departments (folded) -> each leaflet's file name.
LEAFLETS = {
    "alibori": "Plaquette_Alibori_final.pdf", "atakora": "Plaquette_Atacora_finale.pdf",
    "atlantique": "Plaquette_Atlantique_final.pdf", "borgou": "Plaquette_Borgou_final.pdf",
    "collines": "Plaquette_Collines_final.pdf", "kouffo": "Plaquette_Couffo_final.pdf",
    "donga": "Plaquette_Donga_Finale.pdf", "littoral": "Plaquette_Littoral_final.pdf",
    "mono": "Plaquette_Mono_final.pdf", "oueme": "Plaquette_Ou%C3%A9m%C3%A9%20-%20final.pdf",
    "plateau": "Plaquette_Plateau_final.pdf", "zou": "Plaquette_Zou_Final.pdf",
}
# The workbook's and the leaflets' spellings of the map's departments (folded).
DEPARTMENT_NAMES = {"atakora": "atacora", "kouffo": "couffo"}
# The leaflets' spellings of the map's communes (folded), where they differ.
COMMUNE_NAMES = {"dogbo": "dogbotota", "akpomisserete": "akpromisserete",
                 "boukombe": "boukoumbe", "semekpodji": "semepodji", "kobli": "cobly"}
PUBLISHER = "Institut National de la Statistique et de l'Analyse Economique (INSAE) du Bénin"
CENSUS = "Quatrième Recensement Général de la Population et de l'Habitation (RGPH-4) 2013"
# The workbook's two tables by department, by the titles it gives them.
WORKBOOK_SOURCE = (f"{PUBLISHER}, {CENSUS}, Résultats globaux: principaux indicateurs "
                   "(Structure de la population and État de la population, by department)")
LEAFLET_SOURCE = (f"{PUBLISHER}, {CENSUS}, Synthèse des principaux résultats du RGPH-4, "
                  "{department} (table 1, the population by commune and sex)")
LICENCE = "INSAE publication (reuse with attribution)"
YEAR = 2013
NATIONAL = 10_008_749
OUT = "benin_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def fetch(path: str, magic: bytes) -> tuple[bytes, str]:
    """The Internet Archive's copy of INStaD's file, under either host name."""
    last = ""
    for archive, host in ((a, h) for a in ARCHIVES for h in ("https://", "https://www.")):
        url = archive + host + path
        try:
            blob = http_get(url, binary=True, cache=False, timeout=120, retries=3)
        except Exception as err:  # noqa: BLE001 -- the other host is tried
            last = f"{type(err).__name__}: {err}"
            continue
        if blob.startswith(magic):
            log(f"  read {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
            return blob, url
        last = f"{url} is not the file: {blob[:40]!r}"
    raise SystemExit(f"benin_census: {path}: {last}")


def departments(blob: bytes) -> dict[str, dict[str, Any]]:
    """{department (folded, the workbook's spelling): {total, median, women_pct}}."""
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)

    def sheet(name: str) -> list[list[Any]]:
        for actual in book.sheetnames:
            if actual.strip().lower() == name.lower():
                return [list(r) for r in book[actual].iter_rows(values_only=True)]
        raise SystemExit(f"benin_census: no sheet {name!r} in {book.sheetnames}")

    ages = sheet("STRUCTURE_POPULATION (2)")
    head = next(r for r in ages if r and str(r[0] or "").strip().lower() == "total")
    names = [fold(c) for c in head[1:]]
    totals_row = ages[ages.index(head) + 1]
    out: dict[str, dict[str, Any]] = {n: {"total": int(round(float(v)))}
                                      for n, v in zip(names, totals_row[1:]) if n}
    groups: dict[str, list[list[Any]]] = {n: [] for n in out}
    for row in ages:
        label = str(row[0] or "").strip().lower()
        m = re.match(r"^(\d+)\s*-\s*(\d+)\s*ans", label) or re.match(r"^(\d+)\s*ans\s*(?:et|&)", label)
        if not m:
            continue
        low = int(m.group(1))
        high = int(m.group(2)) if m.lastindex and m.lastindex > 1 else None
        for n, v in zip(names, row[1:]):
            if n in groups and v is not None:
                groups[n].append([low, high, float(v)])
    for n, g in groups.items():
        made = sum(x[2] for x in g)
        if abs(made - 100) > 0.5:
            raise SystemExit(f"benin_census: {n}'s age groups make {made:.2f}%")
        out[n]["groups"] = g
        out[n]["median"] = grouped_median([(lo, hi, share) for lo, hi, share in g])
    state = sheet("ETAT_POPULATION (2)")
    head = next(r for r in state if r and str(r[0] or "").strip().lower() == "indicateurs")
    snames = [fold(c) for c in head[1:]]
    women = next(r for r in state if r and str(r[0] or "").lower().startswith("femmes"))
    women_row = state[state.index(women) + 1]
    for n, v in zip(snames, women_row[1:]):
        if n in out:
            share = float(v)
            if not 45 < share < 56:
                raise SystemExit(f"benin_census: {n}'s women make {share}%")
            out[n]["women_pct"] = share
    country = out.pop("benin")
    made = sum(d["total"] for d in out.values())
    if made != NATIONAL or country["total"] != NATIONAL:
        raise SystemExit(f"benin_census: the departments make {made:,}, not {NATIONAL:,}")
    pooled: dict[tuple[int, Any], float] = {}
    for d in out.values():
        for lo, hi, share in d["groups"]:
            pooled[(lo, hi)] = pooled.get((lo, hi), 0.0) + share * d["total"] / 100
    national = grouped_median([(lo, hi, n) for (lo, hi), n in sorted(
        pooled.items(), key=lambda kv: kv[0][0])])
    if abs(national - country["median"]) > 0.5:
        raise SystemExit(f"benin_census: the departments' ages make a median of {national}, "
                         f"the country's own {country['median']}")
    log(f"  national median {country['median']} (the departments' groups pooled: {national})")
    return out


def readings(tokens: list[str], start: int) -> list[tuple[int, int]]:
    if start >= len(tokens) or not tokens[start].isdigit():
        return []
    if len(tokens[start]) > 3:
        return [(int(tokens[start]), start + 1)]
    out, j = [(int(tokens[start]), start + 1)], start + 1
    while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
        j += 1
        out.append((int("".join(tokens[start:j])), j))
    return out


def triple(tokens: list[str], start: int) -> list[tuple[tuple[int, int, int], int]]:
    """Each (total, men, women) beginning at tokens[start] whose sexes make it."""
    out = []
    for t, a in readings(tokens, start):
        for m, b in readings(tokens, a):
            for f, c in readings(tokens, b):
                if m + f == t:
                    out.append(((t, m, f), c))
    return out


def leaflet_rows(text: str) -> list[tuple[str, tuple[int, int, int]]]:
    """(name, 2013 total/men/women) for each row of the leaflet's first table:
    a name, the 2013 and 2002 counts by sex, the growth rate and the weight."""
    rows = []
    text = re.sub(r"[\u00a0\u2009\u202f]", " ", text)
    for line in text.splitlines():
        # The growth rate may be negative (Zagnanado's), its sign a hyphen, a
        # minus or a dash, set apart or not.
        # The weight may be set with a space after its comma ("6, 5": Zagnanado's).
        m = re.match(r"^\s*([^\d]+?)\s+(\d[\d ]*\d)\s+([-\u2212\u2013]?\s?\d+,\s?\d+)"
                     r"(?:\s+(\d+,\s?\d+))?\s*$", line)
        if not m:
            continue
        tokens = m.group(2).split()
        for (t13, end) in ((r, e) for r, e in triple(tokens, 0)):
            if any(e2 == len(tokens) for _, e2 in triple(tokens, end)):
                rows.append((m.group(1).strip(), t13))
                break
    return rows


def match(name: str, wanted: list[str]) -> str | None:
    """The map's commune a leaflet's row names, within its department."""
    key = fold(name)
    for w in wanted:
        if COMMUNE_NAMES.get(fold(w), fold(w)) == key or fold(w) == key:
            return w
    close = [w for w in wanted
             if difflib.SequenceMatcher(None, fold(w), key).ratio() >= 0.85]
    return close[0] if len(close) == 1 else None


def commune_record(key: str, c: dict[str, Any], communes: list[dict[str, Any]],
                   found: dict[str, tuple[int, int, int]], whole: tuple[int, int, int],
                   derived: str | None, d: dict[str, Any], leaflet: dict[str, Any],
                   workbook: dict[str, Any]) -> dict[str, Any]:
    """A commune's sex ratio from its department's leaflet; a department of one
    commune (Littoral, which is Cotonou) is that commune's ground, so the
    department's median is the commune's too."""
    total, men, women_n = found[c["name"]]
    alone: dict[str, Any] = {}
    cited: list[dict[str, Any]] = []
    if len(communes) == 1:
        alone = {"median_age": measure(d["median"], unit="years", year=YEAR,
                                       source=WORKBOOK_SOURCE),
                 "median_age_note": ("The median of the department's five-year age groups in "
                                     "the 2013 census, interpolated within the group holding "
                                     "the middle person; the department is this one commune.")}
        cited = [workbook]
    return record(
        f"BEN-RGPH4-{key}-{fold(c['name'])}", c["name"], level="admin2", parent="BEN",
        country="BEN", match_by="shape_id", shape_id=c["id"],
        sex_ratio=measure(round(1000 * men / women_n), unit="males_per_1000_females",
                          year=YEAR, source=leaflet["name"]),
        sex_ratio_note=(
            f"The 2013 census's count of the commune, {men:,} men and {women_n:,} women: the "
            f"department's {whole[1]:,} men and {whole[2]:,} women less those of its other "
            f"{len(communes) - 1} communes, as the leaflet gives them." if c["name"] == derived
            else f"The 2013 census's count of the commune: {men:,} men and {women_n:,} women."),
        sources=[leaflet, *cited], **alone)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    from pypdf import PdfReader

    admin1 = json.loads((SITE / "admin1" / "BEN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "BEN.units.json").read_text())
    blob, book_url = fetch(WORKBOOK, b"PK")
    deps = departments(blob)
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    for shape in admin1:
        key = fold(shape["name"])
        d = deps.get(DEPARTMENT_NAMES.get(key, key))
        if d is None:
            problems.append(f"department {shape['name']!r}: not in the workbook")
            continue
        women = d["women_pct"]
        ratio = round(1000 * (100 - women) / women)
        log(f"  {shape['name']}: {d['total']:,}, median {d['median']}, {ratio} men per 1,000 "
            f"women")
        src = {"name": WORKBOOK_SOURCE, "url": book_url, "license": LICENCE, "year": YEAR}
        records.append(record(
            f"BEN-RGPH4-{key}", shape["name"], level="admin1", parent="BEN", country="BEN",
            match_by="shape_id", shape_id=shape["id"],
            median_age=measure(d["median"], unit="years", year=YEAR, source=WORKBOOK_SOURCE),
            median_age_note=("The median of the department's five-year age groups in the 2013 "
                             "census, interpolated within the group holding the middle person."),
            sex_ratio=measure(ratio, unit="males_per_1000_females", year=YEAR,
                              source=WORKBOOK_SOURCE),
            sex_ratio_note=(f"The 2013 census counted {d['total']:,} people in the department, "
                            f"{women:.1f}% of them women."),
            sources=[{**src, "field": "median_age/sex_ratio"}]))
        communes = [u for u in admin2 if u.get("parent") == shape["id"]]
        try:
            pdf, url = fetch(FOLDER + "Plaquettes/" + LEAFLETS[key], b"%PDF")
        except SystemExit as err:
            problems.append(f"{shape['name']}: {err}")
            continue
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages[:2])
        rows = leaflet_rows(text)
        whole = [r for r in rows if fold(r[0]) in (key, DEPARTMENT_NAMES.get(key, key))]
        if not whole or whole[0][1][0] != d["total"]:
            problems.append(f"{shape['name']}: the leaflet's department row {whole[:1]} is not "
                            f"the workbook's {d['total']:,}")
            continue
        found: dict[str, tuple[int, int, int]] = {}
        for name, figures in rows:
            hit = match(name, [c["name"] for c in communes])
            if hit and hit not in found:
                found[hit] = figures
        if not found and len(communes) == 1:
            # Littoral is the one commune of Cotonou, and its leaflet has no
            # row apart from the department's.
            found[communes[0]["name"]] = whole[0][1]
        missing = [c["name"] for c in communes if c["name"] not in found]
        for name in missing:
            key2 = fold(COMMUNE_NAMES.get(fold(name), name))[:5]
            log(f"    {name}: not read; its lines: "
                f"{[line for line in text.splitlines() if key2 in fold(line)][:3]}")
        derived = None
        if len(missing) == 1 and len(communes) > 1:
            # One commune's row not read: the department's count less its
            # other communes', when every figure of theirs is read.
            rest = [sum(v[i] for v in found.values()) for i in range(3)]
            left = tuple(whole[0][1][i] - rest[i] for i in range(3))
            if left[0] > 0 and left[1] > 0 and left[2] > 0 and left[1] + left[2] == left[0]:
                derived = missing[0]
                found[derived] = left
                log(f"    {derived}: the department's count less its other communes': "
                    f"{left[0]:,} ({left[1]:,} men, {left[2]:,} women)")
        if len(found) != len(communes) or sum(v[0] for v in found.values()) != d["total"]:
            problems.append(f"{shape['name']}: the leaflet gives {sorted(found)} of "
                            f"{sorted(c['name'] for c in communes)}, making "
                            f"{sum(v[0] for v in found.values()):,} of {d['total']:,}; its rows: "
                            f"{rows}")
            continue
        source = LEAFLET_SOURCE.format(department=shape["name"])
        for c in communes:
            log(f"    {c['name']}: {found[c['name']][0]:,} ({found[c['name']][1]:,} men, "
                f"{found[c['name']][2]:,} women)")
            records.append(commune_record(key, c, communes, found, whole[0][1], derived, d,
                                          {"field": "sex_ratio", "name": source, "url": url,
                                           "license": LICENCE, "year": YEAR},
                                          {**src, "field": "median_age"}))
    for line in problems:
        log("  " + line)
    n1 = sum(1 for r in records if r["level"] == "admin1")
    n2 = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {n1} departments and {n2} communes written")
    if n1 != len(admin1):
        raise SystemExit("benin_census: not every department was read")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
