#!/usr/bin/env python3
"""Spain: the regional statistics offices' language surveys.

INE's census does not ask language, and the European Social Survey is the only
thing on the map for most of Spain: a few hundred respondents an autonomous
community, drawn to compare countries. Two of the communities with a language
of their own measure it themselves, with samples drawn to describe them:

* **Catalonia** -- Idescat and the Generalitat's *Enquesta d'usos lingüístics
  de la població* (EULP), 2023: the population aged 15 and over by habitual
  language (Idescat table 3202), as weighted estimates in thousands, read from
  Idescat's API. Idescat publishes it for Catalonia, for the areas of the
  Territorial Plan and for its own sampling strata -- none of which is a
  province -- so it is written for the autonomous community only.
* **Galicia** -- the IGE's *Enquisa estrutural a fogares: coñecemento e uso do
  galego*: the population aged 5 and over by the language they usually speak
  (always Galician, more Galician than Spanish, more Spanish than Galician,
  always Spanish), for Galicia and each of its four provinces -- IGE table
  2953, the latest wave (2023), read from the IGE's API.

(The Basque Country's home language is not here: Eustat asks it in its own
census, which is a count; see ``basque_language``.)

Survey estimates, so the file's name ends in ``_survey``: they fill what no
count describes, and as a national (regional) office's survey they stand in
front of the European Social Survey.

**How many respondents.** Neither office publishes the respondents per unit,
so each note carries what each office's methodology states, read from it on
every run: Idescat's effective EULP 2023 sample for Catalonia (8,682 people
aged 15 and over), and the IGE's design for its household survey -- 512 census
sections of 18 dwellings each, every member of each household interviewed,
allocated A Coruña 180, Lugo 90, Ourense 91, Pontevedra 151 sections (so at
least 1,620 dwellings in the smallest province).

Checks, each of which stops the run:

* every unit's categories make its published total;
* for Galicia, the four provinces make Galicia (the IGE's estimates are
  calibrated to the population by province);
* each methodology still states the sample it is quoted for, and the sections
  add to the total.

Usage:
    python -m scripts.fetch_census.spain_language_survey
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, shares, write_json
from .binding import fold

OUT = "spain_language_survey.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# --- Catalonia -------------------------------------------------------------

EULP_YEAR = 2023
EULP = "https://api.idescat.cat/taules/v2/eulp/3202/23138/cat/data?lang=en"
EULP_PAGE = "https://www.idescat.cat/pub/?id=eulp&lang=en"
EULP_SOURCE = ("Idescat and the Generalitat of Catalonia, Survey on Language Uses of the "
               "Population (EULP) 2023: population aged 15 and over by habitual language")
EULP_LABELS = {
    "CA": "Catalan", "ES": "Spanish", "CA_ES": "Catalan and Spanish",
    "OC_ARANESE": "Aranese Occitan",
    "CA_OTHER_LANG": "Catalan and another language",
    "ES_OTHER_LANG": "Spanish and another language",
    "CA_ES_OTHER_LANG": "Catalan, Spanish and another language",
    "AR": "Arabic", "OTHER_LANG": "Other language",
    "OTHER_COMB_LANG": "Other language combinations", "_U": "Not stated",
}
CATALONIA = "Cataluña/Catalunya"
EULP_METHOD = "https://www.idescat.cat/pub/?id=eulp&lang=en&m=m"


def eulp_sample(page: str) -> int:
    """The effective sample Idescat's methodology page states for the EULP 2023."""
    import html
    import re
    flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    m = re.search(r"La mostra efectiva ha estat de ([\d.]+) individus", flat)
    if not m:
        raise SystemExit("spain_language_survey: Idescat's methodology no longer states the "
                         "EULP's effective sample")
    return int(m.group(1).replace(".", ""))


def jsonstat_cells(payload: dict[str, Any]) -> list[tuple[dict[str, str], float]]:
    """A JSON-stat 2.0 dataset -> [(dimension -> category code, value)]."""
    ids, sizes = payload["id"], payload["size"]
    orders = []
    for name in ids:
        index = payload["dimension"][name]["category"]["index"]
        orders.append(sorted(index, key=index.get) if isinstance(index, dict) else list(index))
    values = payload["value"]
    if isinstance(values, dict):
        total = 1
        for size in sizes:
            total *= size
        values = [values.get(str(i)) for i in range(total)]
    out = []
    for flat, value in enumerate(values):
        if value is None:
            continue
        key, rest = {}, flat
        for i in range(len(ids) - 1, -1, -1):
            key[ids[i]] = orders[i][rest % sizes[i]]
            rest //= sizes[i]
        out.append((key, float(value)))
    return out


def catalonia(payload: dict[str, Any], sample: int | None = None) -> dict[str, Any]:
    cells = {key["LAN_ISO"]: value for key, value in jsonstat_cells(payload)}
    total = cells.pop("TOTAL", None)
    unknown = sorted(set(cells) - set(EULP_LABELS))
    if unknown:
        raise SystemExit(f"spain_language_survey: EULP categories not declared: {unknown}")
    if total is None or abs(sum(cells.values()) - total) > 0.5:
        raise SystemExit(f"spain_language_survey: EULP categories make "
                         f"{sum(cells.values()):,.1f} thousand against {total}")
    counts = {EULP_LABELS[k]: v * 1000 for k, v in cells.items()}
    rows = shares(counts, total=total * 1000)
    return {
        "language": rows,
        "language_year": EULP_YEAR,
        "language_basis": "survey estimate: habitual language, residents aged 15+",
        "language_note": (
            f"Idescat and the Generalitat's Survey on Language Uses of the Population (EULP) "
            f"{EULP_YEAR}: residents aged 15 and over by the language they habitually speak -- "
            "one language, two or three together, or another; those who did not say are Not "
            f"stated. A weighted survey estimate ({total:,.1f} thousand people aged 15 and over), "
            "not a count, calibrated to the population register by sex, age, place of birth and "
            "sub-area"
            + (f", from an effective sample of {sample:,} people aged 15 and over (Idescat's "
               "methodology)" if sample else "")
            + "; Idescat publishes it for Catalonia and for territorial areas that are not "
            "provinces, so the provinces are left to other sources. INE's census does not "
            "ask language."),
        "sources": [{"field": "language", "name": EULP_SOURCE, "url": EULP_PAGE,
                     "year": EULP_YEAR, "license": "Idescat (CC BY 4.0)"}],
    }


# --- Galicia ---------------------------------------------------------------

IGE = "https://www.ige.gal/igebdt/igeapi/csv/datos/2953"
IGE_PAGE = "https://www.ige.gal/igebdt/selector.jsp?COD=2953&paxina=001&c=0206004"
IGE_SOURCE = ("IGE, Enquisa estrutural a fogares: coñecemento e uso do galego -- persons aged "
              "5 and over by the language they usually speak (table 2953)")
IGE_LABELS = {
    "En galego sempre": "Galician only",
    "Máis galego ca castelán": "Mostly Galician",
    "Máis castelán ca galego": "Mostly Spanish",
    "En castelán sempre": "Spanish only",
}
IGE_OTHER = {"outra": "Other language", "non sabe": "Not stated", "non consta": "Not stated",
             "ns/nc": "Not stated"}
GALICIA = {"12": "Galicia", "15": "Coruna", "27": "Lugo", "32": "Ourense", "36": "Pontevedra"}
IGE_METHOD = "https://www.ige.gal/estatico/pdfs/s3/metodoloxias/met_EEF_gl.pdf"


def ige_sample(text: str) -> dict[str, int]:
    """The IGE's household survey design: census sections by province, and dwellings.

    Returns {province code: dwellings}, and "12" for Galicia, from the sentence
    the methodology states it in; the sections must add to the total.
    """
    import re
    flat = re.sub(r"\s+", " ", text)
    m = re.search(r"A mostra consta de (\d+) secci\S+ coa seguinte repartici\S+ por "
                  r"provincias: A Coruña (\d+); Lugo (\d+); Ourense (\d+); Pontevedra (\d+)\. "
                  r"En cada secci\S+ entrev ?\S*stanse (\d+) vivendas, co que resulta un total "
                  r"de ([\d.]+) vivendas", flat)
    if not m:
        raise SystemExit("spain_language_survey: the IGE's methodology no longer states the "
                         "survey's sample as it did")
    total, coruna, lugo, ourense, pontevedra, per, dwellings = (
        int(g.replace(".", "")) for g in m.groups())
    if coruna + lugo + ourense + pontevedra != total or total * per != dwellings:
        raise SystemExit(f"spain_language_survey: the IGE's sample does not add up: {m.groups()}")
    return {"12": dwellings, "15": coruna * per, "27": lugo * per, "32": ourense * per,
            "36": pontevedra * per}


def ige_label(label: str) -> str:
    label = " ".join(label.split())
    if label in IGE_LABELS:
        return IGE_LABELS[label]
    for start, english in IGE_OTHER.items():
        if label.lower().startswith(start):
            return english
    raise SystemExit(f"spain_language_survey: an IGE language category not declared: {label!r}")


def galicia(text: str) -> tuple[int, dict[str, dict[str, Any]]]:
    """Table 2953 as the IGE's API writes it -> geography code -> shares (and counts)."""
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "Lingua na que fala habitualmente" not in rows[0]:
        raise SystemExit(f"spain_language_survey: IGE 2953 has columns {list(rows[0]) if rows else []}")
    year = max(int(r["CodTempo"]) for r in rows)
    measures = {r["Medidas"].strip() for r in rows}
    measure = next((m for m in measures if m.lower().startswith("n")), None) or "Porcentaxe"
    cells: dict[str, dict[str, float]] = {}
    for r in rows:
        if int(r["CodTempo"]) != year or " ".join(r["Idade"].split()) != "Total":
            continue
        if r["Medidas"].strip() != measure or r["CodEspazo"].strip() not in GALICIA:
            continue
        language = " ".join(r["Lingua na que fala habitualmente"].split())
        value = float(r["DatoN"]) if r["DatoN"].strip() else None
        if value is None:
            continue
        cells.setdefault(r["CodEspazo"].strip(), {})[language] = value
    if sorted(cells) != sorted(GALICIA):
        raise SystemExit(f"spain_language_survey: IGE 2953 {year} covers {sorted(cells)}")
    out: dict[str, dict[str, Any]] = {}
    for code, row in cells.items():
        total = row.pop("Total", None)
        counts: dict[str, float] = {}
        for label, value in row.items():
            english = ige_label(label)
            counts[english] = counts.get(english, 0.0) + value
        whole = total if total is not None else (100.0 if measure == "Porcentaxe" else None)
        if whole is None or abs(sum(counts.values()) - whole) > max(0.6, 0.005 * whole):
            raise SystemExit(f"spain_language_survey: IGE {GALICIA[code]}: categories make "
                             f"{sum(counts.values()):,.2f} against {whole}")
        out[code] = {"counts": counts, "total": whole, "measure": measure}
    if measure != "Porcentaxe":
        for label in out["12"]["counts"]:
            made = sum(out[c]["counts"].get(label, 0.0) for c in GALICIA if c != "12")
            if abs(made - out["12"]["counts"][label]) > max(2.0, 0.002 * made):
                raise SystemExit(f"spain_language_survey: the provinces make {made:,.0f} "
                                 f"{label}, Galicia {out['12']['counts'][label]:,.0f}")
    return year, out


def galicia_fields(entry: dict[str, Any], year: int, name: str,
                   dwellings: int | None = None) -> dict[str, Any]:
    counted = entry["measure"] != "Porcentaxe"
    rows = shares(entry["counts"], total=entry["total"])
    if not counted:
        rows = [{"group": r["group"], "pct": r["pct"]} for r in rows]
    size = f" ({entry['total']:,.0f} people aged 5 and over)" if counted else ""
    return {
        "language": rows,
        "language_year": year,
        "language_basis": "survey estimate: language usually spoken, residents aged 5+",
        "language_note": (
            f"The IGE's household survey on knowledge and use of Galician, {year}: residents of "
            f"{name} aged 5 and over{size} by the language they usually speak -- always "
            "Galician, more Galician than Spanish, more Spanish than Galician, or always "
            "Spanish. A weighted survey estimate, not a count; the IGE publishes it for Galicia "
            "and each province and does not publish the respondents per province"
            + (f". Its household survey is designed to interview every member of the "
               f"households in {dwellings:,} dwellings here (census sections of 18 dwellings, "
               "by the IGE's methodology)" if dwellings else "")
            + ". INE's census does not ask language."),
        "sources": [{"field": "language", "name": IGE_SOURCE, "url": IGE_PAGE, "year": year,
                     "license": "IGE (attribution)"}],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    admin1 = {fold(u["name"]): u for u in json.loads((SITE / "admin1" / "ESP.units.json").read_text())}
    admin2 = {fold(u["name"]): u for u in json.loads((SITE / "admin2" / "ESP.units.json").read_text())}
    records: list[dict[str, Any]] = []

    from ._shared import http_get
    import io
    from pypdf import PdfReader
    method = http_get(IGE_METHOD, binary=True, cache=True, timeout=180)
    assert isinstance(method, bytes)
    design = ige_sample(" ".join(page.extract_text() or ""
                                 for page in PdfReader(io.BytesIO(method)).pages))
    log(f"  IGE design: {design}")
    raw = http_get(IGE, binary=True, cache=False, timeout=180)
    assert isinstance(raw, bytes)
    year, gal = galicia(raw.decode("latin-1"))
    for code, name in GALICIA.items():
        level, units = ("admin1", admin1) if code == "12" else ("admin2", admin2)
        shape = units.get(fold(name))
        if shape is None:
            raise SystemExit(f"spain_language_survey: no drawn {name!r}")
        if level == "admin2" and shape.get("parent") != admin1[fold("Galicia")]["id"]:
            raise SystemExit(f"spain_language_survey: {name} is not drawn inside Galicia")
        records.append(record(f"ESP-IGE-LANG-{code}", shape["name"], level=level, parent="ESP",
                              country="ESP", match_by="shape_id", shape_id=shape["id"],
                              codes={"ine_province": code} if code != "12" else {"ine_ccaa": "12"},
                              **galicia_fields(gal[code], year, shape["name"], design[code])))

    shape = admin1.get(fold(CATALONIA))
    if shape is None:
        raise SystemExit(f"spain_language_survey: no drawn {CATALONIA!r}")
    page = http_get(EULP_METHOD, cache=True, timeout=120)
    assert isinstance(page, str)
    sample = eulp_sample(page)
    log(f"  EULP effective sample: {sample:,}")
    cat = catalonia(http_json(EULP, cache=False, timeout=120), sample)
    records.append(record("ESP-EULP-CAT", shape["name"], level="admin1", parent="ESP",
                          country="ESP", match_by="shape_id", shape_id=shape["id"], **cat))

    for r in records:
        log(f"  {r['level']} {r['name']}: "
            + ", ".join(f"{g['group']} {g['pct']}" for g in r["language"]))
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
