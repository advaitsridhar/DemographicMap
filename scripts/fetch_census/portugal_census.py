#!/usr/bin/env python3
"""Portugal: the 2021 census by municipality and district -- population,
median age, sex ratio and religion.

Portugal's 308 municipalities had a Wikidata head count, a mix of 2011, 2021
and 2025 figures, and nothing else; its eighteen districts and two autonomous
regions had an encyclopaedia's figure or Eurostat's, and no religion. INE's
own census tables fill all of it, read from its JSON indicator API
(``pindica.jsp``), one municipality at a time:

* ``0011626`` -- resident population by municipality, sex and **single year
  of age** (0 to 99, and 100 and over), Censos 2021;
* ``0011644`` -- resident population aged 15 and over by municipality and
  religion, Censos 2021. The religion question was optional and INE's table
  counts only those who answered; the rest of the residents aged 15 and over
  (from the single-year table) are carried as "Not stated", the way the ONS
  and NRS tables carry theirs.

**Districts are summed, not looked up.** The census tables are published on
the NUTS 2013 geography, which has no districts; a district is its
municipalities (the first two digits of INE's four-digit municipality code),
and the autonomous regions are theirs (31-32 Madeira, 41-49 the Azores). Their
single years and religion counts are added, and the median taken afresh.

**Binding.** Municipalities are bound to the map's polygons by name within the
district the boundary file files them under, then by a name no other polygon
shares -- ``binding.bind``, so Espinho, Mesão Frio, Sardoal and Tábua, which
geoBoundaries files under a neighbouring district, still land. Eight of the
boundary file's names are misspelt or shortened ("Setubul", "Praia da
Vitoria") and are declared below, and three polygons
are pinned by id because the boundary file draws two polygons under one name:

* Montijo's two parts (the municipality really is in two pieces) and
  Ílhavo's two: the figures go on the larger part, and the smaller part is
  left without them -- ``shared.patch`` proposes merging each pair in
  ``make_redrawn.py`` so the one municipality is one unit;
* "Oliveira de Frades" twice: a 144 km² polygon filed under Aveiro
  (``2272694B21944289016738``), the size of the municipality (145 km²), and a
  21 km² polygon under Viseu (``2272694B61775283939308``) between Tondela,
  Vouzela and Águeda. The figures go on the first. The second is not the
  municipality and what it is could not be established, so it is written as a
  stated gap (``UNIDENTIFIED``) rather than given anyone's figures -- the
  shared patch also keeps Wikidata's head count of the whole municipality off
  it, where it had shown the municipality twice.

**Districts are INE's, not the boundary file's.** Five municipalities are drawn
under a district other than INE's (Espinho, Mesão Frio, Sardoal, Tábua and
Oliveira de Frades), so a district's census figures differ from the sum of
the municipalities drawn inside its outline by up to 3%. Each district's note
names the municipalities concerned.

Checks, each of which stops the run:

* every municipality's single years make its total for each sex, and its two
  sexes make its both-sexes total;
* the municipalities make Portugal's own published total;
* INE publishes no median age for the census, but it does publish the mean
  (``0011707``, "idade média"): the national mean recomputed from the single
  years, each completed age read at its midpoint (age + 0.5, the convention
  INE's published 45.44 matches), must be within 0.05 years of it;
* the religion categories never exceed the published total of people aged 15
  and over, and the municipalities' religion totals make Portugal's;
* every polygon left without a municipality is one declared here: the smaller
  part of Montijo or Ílhavo (until ``make_redrawn`` merges them) or an
  ``UNIDENTIFIED`` one.

Usage:
    python -m scripts.fetch_census.portugal_census
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_json, log, measure, record, shares,
    write_json,
)
from .binding import bind, fold
from .redatam import median_age

OUT = "portugal_census.json"
YEAR = 2021
API = "https://www.ine.pt/ine/json_indicador/pindica.jsp?op=2&varcd={var}&Dim1=S7A2021&Dim2={geo}&lang=PT"
META = "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp?varcd={var}&lang=PT"
PAGE = "https://www.ine.pt/xportal/xmain?xpid=INE&xpgid=ine_indicadores&indOcorrCod={var}&contexto=bd&selTab=tab2"
AGES = "0011626"
RELIGION = "0011644"
SOURCE = "INE, Censos 2021 (Recenseamento da população e habitação)"
LICENCE = "INE open data (attribution)"
SITE = PROCESSED.parent.parent / "site" / "data"
MEAN_AGE = "0011707"
# How far the recomputed national mean age may sit from INE's published one.
MEAN_TOLERANCE = 0.05

DISTRICTS = {
    "01": "Aveiro", "02": "Beja", "03": "Braga", "04": "Bragança", "05": "Castelo Branco",
    "06": "Coimbra", "07": "Évora", "08": "Faro", "09": "Guarda", "10": "Leiria",
    "11": "Lisboa", "12": "Portalegre", "13": "Porto", "14": "Santarém", "15": "Setúbal",
    "16": "Viana do Castelo", "17": "Vila Real", "18": "Viseu",
    "31": "Região Autónoma da Madeira", "32": "Região Autónoma da Madeira",
}
for _island in range(41, 50):
    DISTRICTS[str(_island)] = "Região Autónoma dos Açores"

RELIGIONS = {
    "Católica": "Roman Catholic",
    "Ortodoxa": "Orthodox",
    "Protestante/Evangélica": "Protestant or Evangelical",
    "Testemunhas do Jeová": "Jehovah's Witnesses",
    "Testemunhas de Jeová": "Jehovah's Witnesses",
    "Outra cristã": "Other Christian",
    "Budista": "Buddhist",
    "Hindu": "Hindu",
    "Judaica": "Jewish",
    "Muçulmana": "Muslim",
    # "Other non-Christian" is what INE means; written that way the group
    # tree reads the word "Christian" and files it under Protestantism.
    "Outra não cristã": "Other religion",
    "Sem religião": "No religion",
}

# INE's name -> the boundary file's, where they differ by more than accents.
ALIASES = {
    "Alcanena": "Alcanenena",
    "Aljezur": "Alijezur",
    "Barreiro": "Barriero",
    "Setúbal": "Setubul",
    "Sever do Vouga": "Server do Vouga",
    "Ferreira do Alentejo": "Ferriera do Alentejo",
    "Póvoa de Lanhoso": "Povoa de Lanhosa",
    "Vila da Praia da Vitória": "Praia da Vitoria",
}
# INE code -> polygon, where the boundary file draws two polygons under the
# municipality's name (see the module docstring).
PINNED = {
    "1507": "2272694B10601306194261",   # Montijo, the 316 km² part inland
    "0110": "2272694B86153814936026",   # Ílhavo, the 19 km² part
    "1810": "2272694B21944289016738",   # Oliveira de Frades, the 144 km² polygon
}
# The other part of each municipality drawn in two (merged into the pinned one
# by make_redrawn.py once the shared patch is applied).
SECOND_PARTS = {
    "2272694B43421578736002": "1507",   # Montijo, the 20 km² part on the Tagus
    "2272694B64447610403706": "0110",   # Ílhavo, the 4 km² part
}
# Polygons that are no municipality INE counts, each with why.
UNIDENTIFIED = {
    "2272694B61775283939308": (
        "The boundary file draws two polygons named Oliveira de Frades. The municipality "
        "(145 km²) is the 144 km² one filed under Aveiro, which carries INE's 2021 census "
        "figures; this 21 km² polygon, filed under Viseu between Tondela, Vouzela and "
        "Águeda, is not the municipality, and which ground it is could not be established. "
        "No figure is put on it, since a municipality's figures on a shape that is not it "
        "would be a mis-match."),
}


def get(var: str, geo: str) -> list[dict[str, Any]]:
    """One indicator for one place, patiently: INE's host drops connections."""
    url = API.format(var=var, geo=geo)
    for attempt in range(6):
        try:
            # Only the first try may read the cache: an answer without data
            # is cached like any other, and retrying from the cache read the
            # same bad answer six times.
            payload = http_json(url, cache=attempt == 0, retries=3, timeout=180)
            if not (isinstance(payload, list) and payload and "Dados" in payload[0]):
                raise ValueError(f"no data in INE's answer: {str(payload)[:160]}")
            rows = payload[0]["Dados"][str(YEAR)]
            if not rows:
                raise SystemExit(f"portugal_census: {var} {geo}: no rows")
            return rows
        except SystemExit:
            raise
        except Exception as err:                    # noqa: BLE001 -- retried, then raised
            wait = 20 * (attempt + 1)
            log(f"  {var} {geo}: {type(err).__name__}: {str(err)[:120]}; again in {wait}s")
            time.sleep(wait)
    raise SystemExit(f"portugal_census: {var} {geo}: INE did not answer after six tries")


def municipalities() -> dict[str, str]:
    """INE code -> name, for the 308 municipalities of the census geography."""
    payload = http_json(META.format(var=AGES), cache=True, retries=4, timeout=180)
    entry = payload[0] if isinstance(payload, list) else payload
    out: dict[str, str] = {}
    for dim in entry["Dimensoes"]["Categoria_Dim"]:
        for key, cats in dim.items():
            if not key.startswith("Dim_Num2"):
                continue
            for cat in cats if isinstance(cats, list) else [cats]:
                code = str(cat.get("cat_id"))
                if len(code) == 4 and code.isdigit():
                    out[code] = cat.get("categ_dsg")
    if len(out) != 308:
        raise SystemExit(f"portugal_census: {len(out)} municipalities in the census "
                         "geography, not 308")
    return out


def age_of(label: str) -> int | None:
    text = label.strip().lower()
    if text == "total":
        return None
    if text.startswith("menos de 1"):
        return 0
    head = text.split()[0]
    if not head.isdigit():
        raise SystemExit(f"portugal_census: an age INE calls {label!r}")
    return int(head)


def read_ages(geo: str) -> dict[str, Any]:
    by_sex: dict[str, Counter] = {"HM": Counter(), "H": Counter(), "M": Counter()}
    totals: dict[str, float] = {}
    for row in get(AGES, geo):
        sex = row["dim_3_t"]
        value = float(row["valor"]) if row.get("valor") not in (None, "") else 0.0
        age = age_of(row["dim_4_t"])
        if age is None:
            totals[sex] = value
        else:
            by_sex[sex][age] += value
    for sex in ("HM", "H", "M"):
        made = sum(by_sex[sex].values())
        if sex not in totals or made != totals[sex]:
            raise SystemExit(f"portugal_census: {geo} {sex}: single years make {made:,.0f} "
                             f"against {totals.get(sex)}")
    if totals["H"] + totals["M"] != totals["HM"]:
        raise SystemExit(f"portugal_census: {geo}: men and women do not make the total")
    if max(by_sex["HM"]) < 99:
        raise SystemExit(f"portugal_census: {geo}: ages stop at {max(by_sex['HM'])}")
    return {"men": totals["H"], "women": totals["M"], "ages": by_sex["HM"]}


def read_religion(geo: str) -> dict[str, Any]:
    counts: dict[str, float] = {}
    total = None
    for row in get(RELIGION, geo):
        label = row["dim_3_t"].strip()
        value = float(row["valor"]) if row.get("valor") not in (None, "") else 0.0
        if label == "Total":
            total = value
        elif label in RELIGIONS:
            counts[RELIGIONS[label]] = counts.get(RELIGIONS[label], 0.0) + value
        else:
            raise SystemExit(f"portugal_census: {geo}: a religion INE calls {label!r}")
    if total is None:
        raise SystemExit(f"portugal_census: {geo}: no religion total")
    rest = total - sum(counts.values())
    if rest < 0:
        raise SystemExit(f"portugal_census: {geo}: religions make {sum(counts.values()):,.0f}, "
                         f"more than the {total:,.0f} people aged 15 and over")
    if rest:
        counts["Not stated"] = rest
    return {"counts": counts, "total": total}


def fields(ages: dict[str, Any], religion: dict[str, Any], what: str) -> dict[str, Any]:
    whole = ages["men"] + ages["women"]
    # INE's religion table counts the people who answered; everyone aged 15
    # and over is in the single-year table, so the difference is those who
    # did not answer. Both are the same census's counts of the same people.
    aged_15 = sum(n for age, n in ages["ages"].items() if age >= 15)
    answered = religion["total"] - religion["counts"].get("Not stated", 0.0)
    if religion["total"] > aged_15:
        raise SystemExit(f"portugal_census{what}: {religion['total']:,.0f} in the religion "
                         f"table, more than the {aged_15:,.0f} residents aged 15 and over")
    counts = dict(religion["counts"])
    counts["Not stated"] = counts.get("Not stated", 0.0) + aged_15 - religion["total"]
    rows = shares({k: v for k, v in counts.items() if v}, total=aged_15)
    return {
        "population": measure(int(whole), year=YEAR, source=SOURCE),
        "population_note": f"The resident population counted by the 2021 census{what}.",
        "median_age": measure(median_age(ages["ages"]), unit="years", year=YEAR,
                              source=SOURCE),
        "median_age_note": ("Interpolated within the single year of age holding the middle "
                            f"person, from INE table {AGES}{what}."),
        "sex_ratio": measure(round(1000 * ages["men"] / ages["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "religion": rows,
        "religion_year": dated(rows, YEAR),
        "religion_note": (
            f"Censos {YEAR} religion question (INE table {RELIGION}), of residents aged 15 and "
            f"over{what}. The question was optional: INE's table counts the "
            f"{answered:,.0f} who answered, and the other {aged_15 - answered:,.0f} of the "
            f"{aged_15:,.0f} residents aged 15 and over (table {AGES}) are shown as 'Not "
            "stated'. 'Other religion' is INE's 'outra não cristã' (another, non-Christian, "
            "religion)."),
        "sources": [{"field": "population/median age/sex ratio", "name": SOURCE,
                     "url": PAGE.format(var=AGES), "year": YEAR, "license": LICENCE},
                    {"field": "religion", "name": SOURCE,
                     "url": PAGE.format(var=RELIGION), "year": YEAR, "license": LICENCE}],
    }


def add(parts: list[dict[str, Any]], key: str) -> Any:
    if key == "ages":
        return sum((p["ages"] for p in parts), Counter())
    return sum(p[key] for p in parts)


def mean_age(ages: Counter) -> float:
    """The mean of completed ages, each read at its midpoint (age + 0.5)."""
    people = sum(ages.values())
    return sum((age + 0.5) * n for age, n in ages.items()) / people


def district_sums(parts_a: list[dict[str, Any]],
                  parts_r: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """A district's single years and religion counts: its municipalities' added."""
    summed_a = {k: add(parts_a, k) for k in ("men", "women", "ages")}
    counts: dict[str, float] = {}
    for part in parts_r:
        for label, value in part["counts"].items():
            counts[label] = counts.get(label, 0.0) + value
    summed_r = {"counts": counts, "total": sum(p["total"] for p in parts_r)}
    if summed_a["men"] + summed_a["women"] != sum(summed_a["ages"].values()):
        raise SystemExit("portugal_census: a district's single years do not make its people")
    return summed_a, summed_r


def bind_municipalities(names: dict[str, str], admin1: list[dict[str, Any]],
                        admin2: list[dict[str, Any]]
                        ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """INE code -> polygon id, and district prefix -> first-level polygon.

    Stops the run on a municipality with no polygon, two on one polygon, or a
    polygon left over that is not declared (SECOND_PARTS, UNIDENTIFIED).
    """
    first = {fold(u["name"]): u for u in admin1}
    district_shape: dict[str, dict[str, Any]] = {}
    for prefix, district in DISTRICTS.items():
        shape = first.get(fold(district))
        if shape is None:
            raise SystemExit(f"portugal_census: no first-level polygon for {district}")
        district_shape[prefix] = shape
    drawn = {s["id"] for s in admin2}
    for sid in list(PINNED.values()) + list(UNIDENTIFIED):
        if sid not in drawn:
            raise SystemExit(f"portugal_census: declared polygon {sid} is not drawn")
    parents = {u["id"]: u["name"] for u in admin1}
    offices = {code: (name, district_shape[code[:2]]["name"]) for code, name in names.items()
               if code not in PINNED}
    kept_out = set(PINNED.values()) | set(UNIDENTIFIED)
    bound, missing = bind(offices, [s for s in admin2 if s["id"] not in kept_out],
                          parents, ALIASES)
    bound.update({code: sid for code, sid in PINNED.items() if code in names})
    if missing:
        raise SystemExit(f"portugal_census: municipalities with no polygon: {missing}")
    if len(set(bound.values())) != len(bound):
        raise SystemExit("portugal_census: two municipalities on one polygon")
    left = sorted(s["id"] for s in admin2 if s["id"] not in bound.values())
    stray = [f"{s['name']} ({s['id']})" for s in admin2
             if s["id"] in left and s["id"] not in SECOND_PARTS and s["id"] not in UNIDENTIFIED]
    if stray:
        raise SystemExit(f"portugal_census: polygons with no municipality, undeclared: {stray}")
    log(f"  {len(bound)} municipalities bound; polygons left without one: "
        + ", ".join(f"{sid} ({'second part' if sid in SECOND_PARTS else 'unidentified'})"
                    for sid in left))
    return bound, district_shape


def drawn_elsewhere(bound: dict[str, str], names: dict[str, str],
                    admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
                    district_shape: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Municipalities the boundary file draws under a district other than INE's.

    Returns, by first-level polygon id, those drawn *out* of it (INE's, drawn
    under another) and *in* to it (another district's, drawn under it).
    """
    parent_of = {s["id"]: s.get("parent") for s in admin2}
    label = {u["id"]: u["name"] for u in admin1}
    out: dict[str, list[tuple[str, str]]] = {}
    into: dict[str, list[tuple[str, str]]] = {}
    lines = []
    for code in sorted(bound):
        own = district_shape[code[:2]]["id"]
        drawn = parent_of.get(bound[code])
        if drawn and drawn != own:
            out.setdefault(own, []).append((names[code], label.get(drawn, drawn)))
            into.setdefault(drawn, []).append((names[code], label[own]))
            lines.append(f"{names[code]}: INE's {label[own]}, drawn under {label.get(drawn)}")
    return {"out": out, "in": into, "lines": lines}


def district_note(out: list[tuple[str, str]], into: list[tuple[str, str]]) -> str:
    """What a district's outline on the map holds that its census figure does not."""
    parts = [f"{name} under {other.title()}" for name, other in out]
    if into:
        parts.append(" and ".join(f"{name} (INE's {other.title()})" for name, other in into)
                     + " inside this district's outline")
    if not parts:
        return ""
    return (" These figures are INE's district, its own municipalities; the boundary file "
            "draws " + " and ".join(parts) + ", so the municipalities drawn inside the "
            "outline do not add up to them.")


def unidentified_record(sid: str, name: str, why: str) -> dict[str, Any]:
    """A stated gap for a polygon that is no municipality INE counts."""
    return record(
        f"PRT-INE-unidentified-{sid}", name, level="admin2", parent="PRT", country="PRT",
        match_by="shape_id", shape_id=sid,
        population=gap(NOT_AVAILABLE, why), median_age=gap(NOT_AVAILABLE, why),
        sex_ratio=gap(NOT_AVAILABLE, why), religion=gap(NOT_AVAILABLE, why))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--pause", type=float, default=0.5,
                    help="seconds between requests to INE")
    args = ap.parse_args()

    names = municipalities()
    log(f"portugal_census: {len(names)} municipalities")
    ages: dict[str, dict[str, Any]] = {}
    religion: dict[str, dict[str, Any]] = {}
    for i, code in enumerate(sorted(names), 1):
        ages[code] = read_ages(code)
        religion[code] = read_religion(code)
        if i % 50 == 0:
            log(f"  {i} read")
        time.sleep(args.pause)
    national = read_ages("PT")
    national_religion = read_religion("PT")

    whole = sum(a["men"] + a["women"] for a in ages.values())
    if whole != national["men"] + national["women"]:
        raise SystemExit(f"portugal_census: the municipalities make {whole:,.0f}, Portugal "
                         f"{national['men'] + national['women']:,.0f}")
    if sum(r["total"] for r in religion.values()) != national_religion["total"]:
        raise SystemExit("portugal_census: the municipalities' religion totals do not make "
                         "Portugal's")
    published_mean = float(get(MEAN_AGE, "PT")[0]["valor"])
    mean = mean_age(national["ages"])
    if abs(mean - published_mean) > MEAN_TOLERANCE:
        raise SystemExit(f"portugal_census: Portugal's mean age from single years is "
                         f"{mean:.2f}, INE publishes {published_mean}")
    log(f"  Portugal: {whole:,.0f} people, median {median_age(national['ages'])}, mean "
        f"{mean:.2f} against INE's published {published_mean}")

    admin1 = json.loads((SITE / "admin1" / "PRT.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "PRT.units.json").read_text())
    bound, district_shape = bind_municipalities(names, admin1, admin2)
    labels = {s["id"]: s["name"] for s in admin2}
    elsewhere = drawn_elsewhere(bound, names, admin1, admin2, district_shape)
    for line in elsewhere["lines"]:
        log(f"  {line}")

    records: list[dict[str, Any]] = []
    for code in sorted(names):
        sid = bound[code]
        records.append(record(
            f"PRT-INE-{code}", labels[sid], level="admin2", parent="PRT", country="PRT",
            parent_name=district_shape[code[:2]]["name"], match_by="shape_id", shape_id=sid,
            codes={"dico": code},
            aliases=[names[code]] if names[code] != labels[sid] else [],
            **fields(ages[code], religion[code], f", in the municipality of {names[code]}")))
    for sid, why in UNIDENTIFIED.items():
        records.append(unidentified_record(sid, labels[sid], why))
    for shape in admin1:
        codes = [c for c in names if district_shape[c[:2]]["id"] == shape["id"]]
        if not codes:
            raise SystemExit(f"portugal_census: {shape['name']} has no municipality")
        summed_a, summed_r = district_sums([ages[c] for c in codes],
                                           [religion[c] for c in codes])
        entry = fields(summed_a, summed_r, f", summed over its {len(codes)} municipalities")
        entry["population_note"] += district_note(
            elsewhere["out"].get(shape["id"], []), elsewhere["in"].get(shape["id"], []))
        records.append(record(
            f"PRT-INE-{fold(shape['name'])}", shape["name"], level="admin1", parent="PRT",
            country="PRT", match_by="shape_id", shape_id=shape["id"], **entry))
        log(f"  {shape['name']}: {len(codes)} municipalities, "
            f"{summed_a['men'] + summed_a['women']:,.0f} people, median "
            f"{records[-1]['median_age']['value']}")
    write_json(args.out or PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
