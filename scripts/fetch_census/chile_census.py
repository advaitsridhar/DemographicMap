#!/usr/bin/env python3
"""Chile: the 2024 census by region and province.

Chile's 16 regions and 56 provinces had a population and nothing else: no
religion, language, ethnicity, median age or sex ratio. INE's first results
of the Censo de Población y Vivienda 2024 are published as workbooks, one per
subject, each with a sheet by region and a sheet by comuna:

- D1: everyone counted, by sex and five-year age group;
- P2: who is or considers themselves part of an indigenous people, and which;
- P3: which indigenous language people aged 5 and over speak or understand;
- P4: who is Afro-descendant, and how they name it;
- P6: the religion or creed of people aged 15 and over.

The map draws regions and provinces, so each comuna row is summed into its
province by INE's own province code, and the regions are read from their own
sheet. Every region's comunas must add up to that region's row, in every
column, before anything is written.

**Small cells.** INE prints "*" for a people or an Afro-descendant group too
small to publish in a comuna. A province's total is still exact, since the
comuna's total is printed; what the stars hide is kept as a line of its own
("Indigenous (people not published)"), never shared out among the peoples
that were printed.

**Ethnicity** is two questions, asked of everyone: indigenous people, and
Afro-descendant. Someone may answer yes to both, and INE publishes no
cross-tabulation, so both are shown and the remainder is everyone else; the
note says so. The census asks nothing about mestizo or white ancestry.

**Language.** The census asks only about indigenous languages. Everyone aged
5 or over who speaks or understands none is shown as Spanish, as Mexico's are,
and the note says that includes immigrants who speak another language.

Usage:
    python -m scripts.fetch_census.chile_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .cod_ps_age import grouped_median

OUT = "chile_census.json"
YEAR = 2024
BASE = "https://censo2024.ine.gob.cl/wp-content/uploads/"
FILES = {
    "age": "2025/03/D1_Poblacion-censada-por-sexo-y-edad-en-grupos-quinquenales.xlsx",
    "peoples": "2025/06/P2_Pueblos-indigenas.xlsx",
    "language": "2025/06/P3_Lenguas-indigenas.xlsx",
    "afro": "2025/06/P4-Afrodescendencia.xlsx",
    "religion": "2025/06/P6_Religion-o-credo.xlsx",
}
SOURCE = "INE Chile, Censo de Población y Vivienda 2024, resultados ({table})"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}
TIMEOUT = 120
SITE = PROCESSED.parent.parent / "site" / "data"

# INE's region codes, and the boundary file's name for each region.
REGIONS = {
    1: "Región de Tarapacá", 2: "Región de Antofagasta", 3: "Región de Atacama",
    4: "Región de Coquimbo", 5: "Región de Valparaíso",
    6: "Región del Libertador Bernardo O'Higgins", 7: "Región del Maule",
    8: "Región del Bío-Bío", 9: "Región de La Araucanía", 10: "Región de Los Lagos",
    11: "Región de Aysén del Gral.Ibañez del Campo",
    12: "Región de Magallanes y Antártica Chilena", 13: "Región Metropolitana de Santiago",
    14: "Región de Los Ríos", 15: "Región de Arica y Parinacota", 16: "Región de Ñuble",
}
# The one province the boundary file names in English.
PROVINCE_ALIASES = {"isladepascua": "Easter Island Province"}

RELIGION = {
    "Católica": "Catholic", "Evangélica o protestante": "Evangelical or Protestant",
    "Judía": "Judaism", "Musulmana": "Muslim",
    "Iglesia de Jesucristo de los Santos de los Últimos Días": "Latter-day Saints",
    "Católica Ortodoxa": "Orthodox", "Budista": "Buddhism", "Hinduista": "Hinduism",
    "Fe Bahá'í": "Bahá'í", "Testigo de Jehová": "Jehovah's Witnesses",
    "Otros cristianos y tradiciones relacionadas con Cristo": "Other Christian",
    "Otras religiones o credos": "Other religion", "Ninguna": "No religion",
    "Religión o credo no declarado": "Religion not stated",
}
PEOPLES = {
    "Mapuche": "Mapuche", "Aymara": "Aymara", "Rapa Nui": "Rapa Nui",
    "Atacameño o Lickanantay": "Atacameño", "Quechua": "Quechua", "Colla": "Colla",
    "Diaguita": "Diaguita", "Kawésqar": "Kawésqar", "Yagán": "Yagán", "Chango": "Chango",
    "Selk'nam": "Selk'nam", "Otro": "Other indigenous people",
    "Pueblo no declarado": "Indigenous (people not stated)",
}
AFRO = {
    "Afrodescendiente": "Afro-descendant", "Afrochileno/a": "Afro-Chilean",
    "Negro/a": "Black", "Del Pueblo Tribal Afrodescendiente": "Tribal Afro-descendant",
    "Moreno/a de Azapa": "Moreno of Azapa", "Negro/a de la Chimba": "Black of La Chimba",
}
AFRO_NONE, AFRO_UNSTATED = "Ninguna de las anteriores", "Afrodescendencia no declarada"
LANGUAGES = {
    "Mapuzungun (lengua mapuche)": "Mapudungun", "Aymara": "Aymara", "Quechua": "Quechua",
    "Rapa Nui": "Rapa Nui", "Ckunza": "Kunza", "Kawésqar": "Kawésqar", "Yagán": "Yaghan",
    "Otra lengua indígena de Chile": "Other indigenous languages of Chile",
    "No habla ni entiende ninguna lengua indígena u originaria": "Spanish",
    "Manejo de alguna lengua indígena u originaria no declarado": "Not stated",
}
REST = "Mestizo or white (neither indigenous nor Afro-descendant)"
PEOPLES_HIDDEN = "Indigenous (people not published)"
AFRO_HIDDEN = "Afro-descendant (group not published)"
AGE = re.compile(r"^(\d+) a (\d+)$")
OPEN = re.compile(r"^(\d+) o más$")


def fold(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in stripped.lower() if c.isalnum() and not unicodedata.combining(c))


def province_key(name: str) -> str:
    return fold(re.sub(r"^provincia\s+(?:de|del)\s+(?:la\s+)?", "", name.strip(), flags=re.I))


def cell(value: Any) -> int | None:
    """A count, or None for INE's "*" (too small to publish)."""
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value if value is not None else "").strip()
    if text in ("*", ""):
        return None
    if text == "-":
        return 0
    return int(float(text.replace(".", "").replace(",", ".")))


def table(book: Any, sheet: str) -> list[dict[str, Any]]:
    """A sheet's rows under the header that starts "Código región"."""
    rows = book[sheet].iter_rows(values_only=True)
    header: list[str] = []
    out: list[dict[str, Any]] = []
    for row in rows:
        first = str(row[0] if row and row[0] is not None else "").strip()
        if not header:
            if first == "Código región":
                header = [str(c).strip() if c is not None else "" for c in row]
            continue
        if not first.isdigit():
            if out:
                break
            continue
        out.append({h: v for h, v in zip(header, row) if h})
    if not out:
        raise SystemExit(f"chile_census: sheet {sheet!r} has no rows under 'Código región'")
    return out


def fetch(key: str) -> Any:
    import openpyxl
    url = BASE + FILES[key]
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                timeout=TIMEOUT) as fh:
        return openpyxl.load_workbook(io.BytesIO(fh.read()), read_only=True, data_only=True)


def resolve(header: dict[str, Any], wants: tuple[str, ...], what: str) -> dict[str, str]:
    """Each wanted column's name in this sheet.

    A header may run past the words used for it here ("Del Pueblo Tribal
    Afrodescendiente ..."): it is found by its start, if only one has it.
    """
    out = {}
    for want in wants:
        found = [c for c in header if c == want] or [c for c in header if c.startswith(want)]
        if len(found) != 1:
            raise SystemExit(f"chile_census: {what}: {len(found)} columns for {want!r}")
        out[want] = found[0]
    return out


def comunas(rows: list[dict[str, Any]], *, where: tuple[str, str] | None = None
            ) -> list[dict[str, Any]]:
    """The comuna rows: a real comuna code, and the named line where a sheet has several."""
    out = []
    for row in rows:
        if int(row["Código comuna"] or 0) == 0:
            continue
        if where and str(row.get(where[0]) or "").strip() != where[1]:
            continue
        out.append(row)
    return out


def regions(rows: list[dict[str, Any]], *, where: tuple[str, str] | None = None
            ) -> dict[int, dict[str, Any]]:
    out = {}
    for row in rows:
        code = int(row["Código región"] or 0)
        if code == 0:
            continue
        if where and str(row.get(where[0]) or "").strip() != where[1]:
            continue
        out[code] = row
    if sorted(out) != sorted(REGIONS):
        raise SystemExit(f"chile_census: a region sheet gave regions {sorted(out)}")
    return out


def summed(rows: list[dict[str, Any]], columns: list[str], by: str
           ) -> tuple[dict[int, dict[str, int]], dict[int, dict[str, int]]]:
    """Per-unit sums of each column, and of the stars hidden in each.

    ``hidden[unit][column]`` counts the comunas whose cell was "*": a sum
    over those is short by an amount the unit's total still pins down.
    """
    sums: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hidden: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        unit = int(row[by])
        for column in columns:
            value = cell(row.get(column))
            if value is None:
                hidden[unit][column] += 1
            else:
                sums[unit][column] += value
    return sums, hidden


def check_regions(sums: dict[int, dict[str, int]], hidden: dict[int, dict[str, int]],
                  region_rows: dict[int, dict[str, Any]], columns: list[str], what: str) -> None:
    """Every region's comunas add up to the region's own row, in every column."""
    bad = []
    for code, row in region_rows.items():
        for column in columns:
            want = cell(row.get(column))
            if want is None or hidden[code].get(column):
                continue
            if sums[code].get(column, 0) != want:
                bad.append(f"{REGIONS[code]} {column}: comunas {sums[code].get(column, 0):,} "
                           f"against {want:,}")
    if bad:
        raise SystemExit(f"chile_census: {what}: " + "; ".join(bad[:5]))
    log(f"  {what}: all {len(region_rows)} regions' comunas add up to the region, "
        f"in all {len(columns)} columns")


def composition(counts: dict[str, int], labels: dict[str, str], total: int,
                hidden_label: str | None) -> dict[str, int]:
    """Counts under the map's labels, with what the stars hid as a line of its own."""
    out = {labels[k]: v for k, v in counts.items() if k in labels and v}
    shown = sum(counts.get(k) or 0 for k in labels)
    if shown > total:
        raise SystemExit(f"chile_census: categories {shown:,} exceed the total {total:,}")
    if shown < total:
        if hidden_label is None:
            raise SystemExit(f"chile_census: categories {shown:,} fall short of {total:,}")
        out[hidden_label] = total - shown
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    shapes = json.loads((SITE / "admin2" / "CHL.units.json").read_text())
    by_key = {province_key(s["name"]): s["name"] for s in shapes}
    by_key.update({k: v for k, v in PROVINCE_ALIASES.items()})

    books = {key: fetch(key) for key in FILES}

    # -- population, sex and age
    age_rows = table(books["age"], "4")
    group_labels = [str(r["Grupos de edad"]).strip() for r in age_rows
                    if int(r["Código comuna"] or 0) == 0 and int(r["Código región"] or 0) == 0]
    bands = [g for g in group_labels if AGE.match(g) or OPEN.match(g)]
    by_band: dict[tuple[str, int], dict[str, dict[str, int]]] = {}
    province_names: dict[int, tuple[str, int]] = {}
    for row in comunas(age_rows):
        label = str(row["Grupos de edad"]).strip()
        if label not in bands:
            continue
        province_names[int(row["Código provincia"])] = (str(row["Provincia"]).strip(),
                                                        int(row["Código región"]))
        for level, code in (("region", int(row["Código región"])),
                            ("province", int(row["Código provincia"]))):
            unit = by_band.setdefault((level, code), {})
            for sex in ("Hombres", "Mujeres"):
                unit.setdefault(sex, defaultdict(int))[label] += cell(row[sex]) or 0
    region_totals = regions(table(books["age"], "1"))
    for code, row in region_totals.items():
        unit = by_band[("region", code)]
        for sex in ("Hombres", "Mujeres"):
            if sum(unit[sex].values()) != cell(row[sex]):
                raise SystemExit(f"chile_census: {REGIONS[code]} {sex}: age groups "
                                 f"{sum(unit[sex].values()):,} against {cell(row[sex]):,}")
    log(f"  age: {len(bands)} groups; every region's comunas add up to its men and women")

    def age_fields(level: str, code: int) -> dict[str, Any]:
        unit = by_band[(level, code)]
        men, women = sum(unit["Hombres"].values()), sum(unit["Mujeres"].values())
        groups = []
        for label in bands:
            people = unit["Hombres"][label] + unit["Mujeres"][label]
            if m := AGE.match(label):
                groups.append((int(m.group(1)), int(m.group(2)), people))
            else:
                groups.append((int(OPEN.match(label).group(1)), None, people))
        median = grouped_median(groups)
        source = SOURCE.format(table="D1, población censada por sexo y edad")
        return {
            "population": {"value": men + women, "year": YEAR, "source": source},
            "median_age": ({"value": median, "unit": "years", "year": YEAR, "source": source}
                           if median is not None else None),
            "median_age_note": ("Interpolated within the five-year age group that holds the "
                                "middle person, from INE's count of everyone by sex and age."),
            "sex_ratio": {"value": round(1000 * men / women), "unit": "males_per_1000_females",
                          "year": YEAR, "source": source},
        }

    # -- the four compositions, each summed by province and checked by region
    def read(key: str, labels: dict[str, str], total_col: str, *, extra: list[str] = (),
             where: tuple[str, str] | None = None, region_where: tuple[str, str] | None = None):
        rows = table(books[key], "2")
        wants = (total_col, *labels, *extra)
        actual = resolve(rows[0], wants, key)
        rows = [{want: row.get(col) for want, col in actual.items()} | {
            k: v for k, v in row.items() if k.startswith(("Código", "Pertenencia"))}
            for row in rows]
        columns = [total_col, *labels, *extra]
        chosen = comunas(rows, where=where)
        by_region = summed(chosen, columns, "Código región")
        by_province = summed(chosen, columns, "Código provincia")
        # What a residual is taken from is never itself hidden.
        for column in (total_col, *extra):
            starred = sum(h.get(column, 0) for h in by_province[1].values())
            if starred:
                raise SystemExit(f"chile_census: {key}: {column} is starred in {starred} comunas")
        region_table = table(books[key], "1")
        in_region = resolve(region_table[0], wants, f"{key} by region")
        region_rows = {code: {want: row[col] for want, col in in_region.items()}
                       for code, row in regions(region_table, where=region_where).items()}
        check_regions(*by_region, region_rows, columns, key)
        return by_province, {code: {c: cell(row.get(c)) for c in columns}
                             for code, row in region_rows.items()}

    religion = read("religion", RELIGION, "Población de 15 años o más")
    peoples_total = next(c for c in table(books["peoples"], "2")[0]
                         if c.startswith("Población que es o se considera"))
    peoples = read("peoples", PEOPLES, peoples_total)
    language = read("language", LANGUAGES, "Población de 5 años o más",
                    where=("Pertenencia a un pueblo indígena u originario", "Total Comuna"),
                    region_where=("Pertenencia a un pueblo indígena u originario",
                                  "Total Región"))
    afro = read("afro", AFRO, "Población censada", extra=[AFRO_NONE, AFRO_UNSTATED])

    def fields(level: str, code: int) -> dict[str, Any]:
        pick = (lambda pair: pair[1][code]) if level == "region" else (
            lambda pair: pair[0][0][code])
        out = age_fields(level, code)
        people = out["population"]["value"]

        rel = pick(religion)
        rel_total = rel["Población de 15 años o más"]
        out["religion"] = shares(composition(rel, RELIGION, rel_total, "Religion not published"))
        out["religion_year"] = YEAR
        out["religion_note"] = (f"Religion or creed of the {rel_total:,} people aged 15 or over, "
                                "as the 2024 census asked it.")

        lang = pick(language)
        lang_total = lang["Población de 5 años o más"]
        lang_counts = composition(lang, LANGUAGES, lang_total, "Not published (small counts)")
        out["language"] = shares(lang_counts)
        out["language_year"] = YEAR
        spanish = lang_counts.get("Spanish", 0)
        out["language_note"] = (
            f"The indigenous language each of the {lang_total:,} people aged 5 or over speaks "
            f"or understands. The census asks about no other language: the "
            f"{100 * spanish / lang_total:.1f}% who speak or understand none are shown as "
            "Spanish, the language nearly all of them speak, which also takes in immigrants "
            "whose language is another, Haitian Creole for one.")

        ind, afr = pick(peoples), pick(afro)
        indigenous = ind[peoples_total]
        eth = composition({k: v for k, v in ind.items() if k != peoples_total}, PEOPLES,
                          indigenous, PEOPLES_HIDDEN)
        afro_counts = {k: v for k, v in afr.items() if k in AFRO}
        afro_total = afr["Población censada"] - (afr[AFRO_NONE] or 0) - (afr[AFRO_UNSTATED] or 0)
        eth.update(composition(afro_counts, AFRO, afro_total, AFRO_HIDDEN))
        rest = people - indigenous - afro_total
        if rest < 0:
            raise SystemExit(f"chile_census: {level} {code}: indigenous and Afro-descendant "
                             f"people exceed the population")
        eth[REST] = rest
        out["ethnicity"] = shares(eth)
        out["ethnicity_year"] = YEAR
        out["ethnicity_note"] = (
            "Two questions the 2024 census asked everyone: whether a person is or considers "
            "themselves part of an indigenous people, and which; and whether they are "
            "Afro-descendant, and how they name it. Someone may answer yes to both, and INE "
            "publishes no cross of the two, so the remainder is the population less both "
            f"counts. It includes the {afr[AFRO_UNSTATED] or 0:,} who did not answer the "
            "Afro-descendant question, and immigrants; the census asks nothing about mestizo "
            "or white ancestry.")
        out["sources"] = [{"field": field, "name": SOURCE.format(table=name), "url": BASE + FILES[key],
                           "year": YEAR}
                          for field, name, key in (
                              ("population/median_age/sex_ratio", "D1", "age"),
                              ("religion", "P6, religión o credo", "religion"),
                              ("language", "P3, lenguas indígenas", "language"),
                              ("ethnicity", "P2, pueblos indígenas; P4, afrodescendencia",
                               "peoples"))]
        return out

    records = []
    for code, name in sorted(REGIONS.items()):
        records.append(record(f"CHL-INE-R{code:02d}", name, level="admin1", parent="CHL",
                              country="CHL", **fields("region", code)))
    unmatched = []
    for code, (ine_name, region) in sorted(province_names.items()):
        shape = by_key.get(province_key(ine_name))
        if shape is None:
            unmatched.append(ine_name)
            continue
        records.append(record(f"CHL-INE-P{code:03d}", shape, level="admin2", parent="CHL",
                              country="CHL", parent_name=REGIONS[region],
                              **fields("province", code)))
    drawn = {s["name"] for s in shapes}
    written = {r["name"] for r in records if r["level"] == "admin2"}
    if unmatched or drawn - written:
        raise SystemExit(f"chile_census: INE provinces with no shape: {unmatched}; "
                         f"shapes with no province: {sorted(drawn - written)}")
    log(f"  {len(REGIONS)} regions and {len(written)} provinces, "
        f"{sum(r['population']['value'] for r in records if r['level'] == 'admin1'):,} people")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
