#!/usr/bin/env python3
"""Median age and sex ratio from the US Census Bureau's subnational Age-Sex sheets.

The Bureau's "Subnational Population and Housing Data Tables" on HDX (read for
compositions by ``uscb.py``) carry an Age-Sex sheet too: everyone by sex and
five-year age group, for every level of the country. Where a level of this map
has no median age or sex ratio at all, that sheet is the census count to fill
it from.

* **Dominican Republic**: the 2010 census (ONE's IX Censo Nacional de
  Población y Vivienda), for the 155 municipalities, which had neither figure.
  The provinces keep what they have, and no population is written: the map's
  are newer. ``dominican_census`` reads the 2022 census over this where it
  binds, and uses this binding to check its own.

The boundary file draws the province of Pedernales as one polygon, where the
country has two municipalities (Pedernales and Oviedo): the two are added
together, age group by age group, for that polygon (``joined``), and the run
stops unless that polygon is its province's only one.

Median age is interpolated within the five-year group holding the middle
person. Every row's groups must make its total, its sexes must make it too,
and each province's municipalities must make the province.

Usage:
    python -m scripts.fetch_census.uscb_age_sex
"""

from __future__ import annotations

import argparse
import io
import json
import re
from dataclasses import dataclass
from typing import Any

from . import uscb
from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .binding import bind, fold
from .cod_ps_age import grouped_median

SITE = PROCESSED.parent.parent / "site" / "data"
GROUP = re.compile(r"^B(\d{2,3})(\d{2,3})$")
OPEN = re.compile(r"^B(\d{2,3})PL$")


@dataclass(frozen=True)
class Country:
    iso3: str
    dataset: str
    year: int
    census: str
    level: int            # the Bureau's ADM_LEVEL written as this map's admin2
    parent_level: int     # the level above it, which it must add up to
    out: str
    # The Bureau's name for a first-level unit -> the boundary file's, where
    # they differ by more than case and accents.
    parents: tuple[tuple[str, str], ...] = ()
    # The same for units, where the boundary file writes a municipality's full
    # official name and the Bureau its short one. Each pair is the one unbound
    # unit and the one unbound polygon of the same province, so the parent
    # check in binding still stands behind every one.
    units: tuple[tuple[str, str], ...] = ()
    # A unit with no polygon of its own -> the unit of the same parent whose
    # polygon is the whole parent's, and so takes both in: their age groups
    # and sexes are added together for it.
    joined: tuple[tuple[str, str], ...] = ()


COUNTRIES = (
    Country(iso3="DOM",
            dataset="dominican-republic-subnational-population-and-housing-data-tables-with-"
                    "administrative-boundaries",
            year=2010, census="ONE, IX Censo Nacional de Población y Vivienda 2010",
            level=3, parent_level=2, out="dominican_republic_age_sex.json",
            # Bahoruco and El Seybo as the boundary file spells them; Elías
            # Piña under its earlier name La Estrelleta (the polygon's capital
            # is Comendador, on the Haitian border); Hermanas Mirabal as
            # "Hermanas" (its capital, Salcedo).
            parents=(("BAORUCO", "Bahoruco"), ("EL SEIBO", "El Seybo"),
                     ("ELÍAS PIÑA", "La Estrelleta"), ("HERMANAS MIRABAL", "Hermanas")),
            # "La Laguna de Nisibón" is a municipal district, not a
            # municipality, and stays unbound here. Santo Domingo de Guzmán is
            # the Distrito Nacional's one municipality.
            units=(("PUERTO PLATA", "San Felipe de Puerto Plata"),
                   ("VILLA ISABELA", "La Isabela"), ("VILLA MONTELLANO", "Montellano"),
                   ("SANTIAGO", "Santiago de los Caballeros"), ("BISONÓ", "Villa Bisonó"),
                   ("LA VEGA", "Concepción de la Vega"), ("VILLA RIVA", "Villa Rivas"),
                   ("EUGENIO MARÍA DE HOSTOS", "Hostos"), ("SAMANÁ", "Santa Bárbara de Samaná"),
                   ("MONTE CRISTI", "San Fernando de Monte Cristi"),
                   ("CASTAÑUELAS", "Castañuela"), ("VILLA VÁSQUEZ", "Villa Vázquez"),
                   ("VILLA LOS ALMÁCIGOS", "Los Almácigos"), ("AZUA", "Azua de Compostela"),
                   ("TÁBARA ARRIBA", "Villa Tabara Arriba"),
                   ("CAMBITA GARABITOS", "Cambita Garabito"),
                   ("YAGUATE", "San Gregorio de Yaguate"), ("SAN GREGORIO DE NIGUA", "Nigua"),
                   ("NEIBA", "Neyba"), ("BARAHONA", "Santa Cruz de Barahona"),
                   ("SAN JUAN", "San Juan de la Maguana"), ("EL SEIBO", "Santa Cruz del Seybo"),
                   ("HIGÜEY", "Salvaleón de Higüey"), ("QUISQUEYA", "Quisquella"),
                   ("PERALVILLO", "Esperalvillo"), ("HATO MAYOR", "Hato Mayor del Rey"),
                   ("SANTO DOMINGO DE GUZMÁN", "Distrito Nacional"),
                   ("SAN ANTONIO DE GUERRA", "Guerra")),
            # The province of Pedernales is one polygon, the same extent as
            # the province's own: Oviedo is in it with Pedernales.
            joined=(("OVIEDO", "PEDERNALES"),)),
)


def number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def groups_of(row: list[Any], at: dict[str, int]) -> list[tuple[int, int | None, float]]:
    """(from, to, count) for each age group of a row, youngest first; ``to`` None when open."""
    groups: list[tuple[int, int | None, float]] = []
    for name, i in at.items():
        closed, open_ = GROUP.match(name), OPEN.match(name)
        if closed:
            groups.append((int(closed.group(1)), int(closed.group(2)), number(row[i]) or 0))
        elif open_:
            groups.append((int(open_.group(1)), None, number(row[i]) or 0))
    return sorted(groups, key=lambda g: g[0])


def figures(row: list[Any], at: dict[str, int], where: str) -> tuple[float | None, int, int, int]:
    """(median age, men, women, total) for one row, after its sums are checked."""
    groups = groups_of(row, at)
    total, men, women = (number(row[at[k]]) for k in ("BTOTL", "MTOTL", "FTOTL"))
    if not total or men is None or women is None:
        raise SystemExit(f"uscb_age_sex: {where}: no total, male or female count")
    if sum(g[2] for g in groups) != total or men + women != total:
        raise SystemExit(f"uscb_age_sex: {where}: groups make {sum(g[2] for g in groups):,}, "
                         f"sexes {men + women:,}, against a total of {total:,}")
    return grouped_median(groups), men, women, total


def read(country: Country) -> list[dict[str, Any]]:
    import openpyxl
    url = uscb.workbook_url(country.dataset)
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Metadata") for c in r if c)
    if str(country.year) not in meta:
        raise SystemExit(f"uscb_age_sex: {country.iso3}: the workbook's metadata never names "
                         f"{country.year}, the census year this file states")
    rows = uscb.sheet_rows(book, "Age-Sex")
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    level_of = at["ADM_LEVEL"]
    units, parents_total = [], {}
    for row in rows[2:]:
        level = number(row[level_of])
        if level == country.parent_level:
            key = str(row[at[f"ADM{country.parent_level}_NAME"]]).strip()
            parents_total[key] = figures(row, at, key)[3]
        elif level == country.level:
            name = str(row[at[f"ADM{country.level}_NAME"]]).strip()
            parent = str(row[at[f"ADM{country.parent_level}_NAME"]]).strip()
            median, men, women, total = figures(row, at, f"{parent}, {name}")
            nso = re.sub(r"^Municipio\s+", "", str(row[at["NSO_NAME"]] or "").strip())
            units.append({"code": str(row[at["GEO_MATCH"]]), "name": name, "nso": nso,
                          "parent": parent, "median": median, "men": men, "women": women,
                          "total": total, "groups": groups_of(row, at)})
    for parent, total in parents_total.items():
        made = sum(u["total"] for u in units if u["parent"] == parent)
        if made != total:
            raise SystemExit(f"uscb_age_sex: {country.iso3}: {parent}'s units make {made:,}, "
                             f"against its {total:,}")
    log(f"  {country.iso3}: {len(units)} units making {len(parents_total)} parents, every "
        "row's groups and sexes making its total")
    return join(units, country.joined)


def join(units: list[dict[str, Any]], joined: tuple[tuple[str, str], ...]
         ) -> list[dict[str, Any]]:
    """Each ``joined`` unit added into its host, age group by age group; the host's median anew."""
    for guest_name, host_name in joined:
        guest = [u for u in units if fold(u["name"]) == fold(guest_name)]
        host = [u for u in units if fold(u["name"]) == fold(host_name)
                and guest and u["parent"] == guest[0]["parent"]]
        if len(guest) != 1 or len(host) != 1:
            raise SystemExit(f"uscb_age_sex: {len(guest)} units named {guest_name} and "
                             f"{len(host)} named {host_name} beside it")
        g, h = guest[0], host[0]
        if [(a, b) for a, b, _ in g["groups"]] != [(a, b) for a, b, _ in h["groups"]]:
            raise SystemExit(f"uscb_age_sex: {guest_name} and {host_name} have other age groups")
        h["groups"] = [(a, b, n + m) for (a, b, n), (_, _, m) in zip(h["groups"], g["groups"])]
        for k in ("men", "women", "total"):
            h[k] += g[k]
        h["median"] = grouped_median(h["groups"])
        h.setdefault("joined", []).append(g["name"])
        units.remove(g)
        log(f"  {guest_name} added into {host_name}, whose polygon takes in both")
    return units


def sole_polygons(units: list[dict[str, Any]], bound: dict[str, str],
                  admin2: list[dict[str, Any]]) -> None:
    """A joined unit's polygon must be the only one of its parent, or the run stops."""
    parent_of = {s["id"]: s["parent"] for s in admin2}
    for u in units:
        if not u.get("joined"):
            continue
        sid = bound.get(u["code"])
        siblings = [s["name"] for s in admin2 if sid and s["parent"] == parent_of[sid]]
        if len(siblings) != 1:
            raise SystemExit(f"uscb_age_sex: {u['name']} takes in {u['joined']}, but its "
                             f"polygon is {'not bound' if not sid else 'one of ' + str(siblings)}")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    for country in COUNTRIES:
        units = read(country)
        admin1 = json.loads((SITE / "admin1" / f"{country.iso3}.units.json").read_text())
        admin2 = json.loads((SITE / "admin2" / f"{country.iso3}.units.json").read_text())
        parents = {u["id"]: u["name"] for u in admin1}
        by_fold = {fold(u["name"]): u["name"] for u in admin1}
        for theirs, ours in country.parents:
            by_fold[fold(theirs)] = ours
        missing_parents = sorted({u["parent"] for u in units if fold(u["parent"]) not in by_fold})
        if missing_parents:
            raise SystemExit(f"uscb_age_sex: {country.iso3}: no first-level unit for "
                             f"{missing_parents}")
        offices = {u["code"]: (u["name"], by_fold[fold(u["parent"])]) for u in units}
        # The statistics office's own spelling as a second one to match on:
        # the Bureau writes names in capitals and sometimes without the
        # office's article or accent.
        aliases = {u["name"]: u["nso"] for u in units if u["nso"]}
        aliases.update(dict(country.units))
        bound, missing = bind(offices, admin2, parents, aliases)
        log(f"  {country.iso3}: {len(bound)} units bound to their polygons; {len(missing)} "
            "not: " + "; ".join(missing))
        labels = {s["id"]: s["name"] for s in admin2}
        unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
        log(f"  {country.iso3}: polygons with no unit: {unbound}")
        sole_polygons(units, bound, admin2)
        source = (f"{country.census}, by sex and five-year age group, as the US Census Bureau "
                  "tabulates it for HDX")
        records = []
        for u in units:
            sid = bound.get(u["code"])
            if sid is None:
                continue
            records.append(record(
                f"{country.iso3}-USCB-{u['code']}", labels[sid], level="admin2",
                parent=country.iso3, country=country.iso3, parent_name=offices[u["code"]][1],
                match_by="shape_id", shape_id=sid,
                aliases=[u["name"].title()] if u["name"].title() != labels[sid] else [],
                median_age=measure(u["median"], unit="years", year=country.year, source=source),
                median_age_note=(
                    "Interpolated within the five-year age group that holds the middle person, "
                    f"from the {country.year} census's count of everyone by five-year age group"
                    + (f", of {u['name'].title()} and "
                       f"{' and '.join(n.title() for n in u['joined'])} together: the boundary "
                       "file draws their province as one polygon."
                       if u.get("joined") else ".")),
                sex_ratio=(measure(round(1000 * u["men"] / u["women"]),
                                   unit="males_per_1000_females", year=country.year,
                                   source=source) if u["women"] else None),
                sources=[{"field": "median age/sex ratio", "name": source,
                          "url": uscb.dataset_url(country.dataset), "year": country.year,
                          "license": "CC BY, published via HDX"}]))
        write_json(PROCESSED / country.out, records)
        log(f"  wrote {country.out}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
