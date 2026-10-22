#!/usr/bin/env python3
"""Republic of the Congo -- the 2023 census by department, and why its second level shows nothing.

**Departments.** The Institut National de la Statistique (INS) took the
fifth general census (RGPH-5) on 17 May 2023 and published preliminary
results: 6,142,180 people. citypopulation.de tabulates them by department and
district, citing INS, with each department's men and women. This writes each
of the 12 departments' count and sex ratio from those pages.

One district is counted under one department and drawn inside another:
Tchiamba-Nzassi, which the census counts under Pointe-Noire department, lies
inside the polygon drawn as Kouilou (Nzassi, GeoNames' point at -4.98111,
12.03972), and the polygon drawn as Pointe-Noire is the city's 80 km² alone
(measured on the CGAZ polygons). Its count is moved from the one to the other
(MOVED), with its men and women where its own page gives them, and both
records say so.

**The second level.** The map draws 46 second-level polygons for the country,
and their names are out of place: Brazzaville lies inside the polygon
labelled Zanaga, Pointe-Noire inside "Gamboma", Impfondo inside "Owando",
Owando and Oyo inside "Mbomo", Dolisie inside "Abala" (GeoNames' points,
measured on the CGAZ polygons in October 2026). Only one polygon of the 46,
Mossendjo, holds the town it is named after. The 2023 census counts the
country's districts and communes as they are now, and they are not drawn.
So no district's figures are shown on these polygons, and each says why,
naming the town that does lie inside it. The reason displaces an
encyclopaedia's figure bound to the polygon by its name (Wikidata's 8,941 for
the district of Komono stood on the polygon that holds Zanaga). No seat is
shown either, and the capital's reason is the polygon's own: the town it
holds, or that none shows which district it is.

Usage:
    python -m scripts.fetch_census.congo_census [--run LABEL]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
from typing import Any, Callable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold

ADMIN = "https://www.citypopulation.de/en/congo/admin/"
HOST = "https://www.citypopulation.de"
YEAR = 2023
OUT = "congo_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
NATIONAL = 6_142_180
SOURCE = ("Institut National de la Statistique (Congo), 5e Recensement Général de la Population "
          "et de l'Habitation 2023, preliminary results, as tabulated by citypopulation.de")
LICENCE = "citation of citypopulation.de required"

# Polygon id -> (label, the largest GeoNames places inside it, with their department).
FACTS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "1427508B96787194302936": ('Abala', (('Dolisie', 'Niari'),)),
    "1427508B17240885664000": ('Bambama', (('Kindamba', 'Pool'),)),
    "1427508B75307715996039": ('Boko', (('Mbinda', 'Niari'),)),
    "1427508B92601755498307": ('Boko-Songho', (('Souanké', 'Sangha'),)),
    "1427508B27104831936236": ('Boundji', ()),
    "1427508B11102510825408": ('Divenie', (('Sibiti', 'Lékoumou'),)),
    "1427508B96128266527522": ('Djambala', (('Mvouti', 'Kouilou'),)),
    "1427508B98957874622899": ('Dongou', (('Kinkala', 'Pool'), ('Baratier', 'Pool'))),
    "1427508B94586768331104": ('Epena', ()),
    "1427508B71494423838128": ('Ewo', (('Gamboma', 'Plateaux'),)),
    "1427508B88245699970735": ('Gamboma', (('Pointe-Noire', 'Pointe-Noire'), ('Loandjili', 'Pointe-Noire'))),
    "1427508B40681064196886": ('Impfondo', (('Mouyondzi', 'Bouenza'), ('Mabombo', 'Bouenza'))),
    "1427508B78448203427797": ('Kakamoeka', ()),
    "1427508B49132157501482": ('Kelle', (('Olombo', 'Plateaux'),)),
    "1427508B61088264973461": ('Kibangou', ()),
    "1427508B96831343191841": ('Kimongo', ()),
    "1427508B11009078407103": ('Kindamba', (('Divenié', 'Niari'),)),
    "1427508B20778125990981": ('Kinkala', ()),
    "1427508B55030741074917": ('Komono', (('Zanaga', 'Lékoumou'),)),
    "1427508B16336577504654": ('Lekana', (('Kibangou', 'Kouilou'),)),
    "1427508B18064452172812": ('Loandjili (Pointe Noire)', (('Boundji', 'Cuvette'),)),
    "1427508B48531502218736": ('Loudima', (('Kellé', 'Cuvette-Ouest'),)),
    "1427508B73097317113528": ('Loukela', (('Epéna', 'Likouala'),)),
    "1427508B57341338749174": ('Louvakou (Loubomo)', (('Loutété', 'Bouenza'), ('Bouansa', 'Bouenza'))),
    "1427508B65324977052506": ('Madingo-Kayes', (('Abala', 'Pool'), ('Ngabé', 'Pool'))),
    "1427508B79538566138262": ('Madingou', (('Ewo', 'Cuvette-Ouest'),)),
    "1427508B79819029922134": ('Makoua', (('Mossaka', 'Cuvette'), ('Ntokou-Raymondville', 'Cuvette'))),
    "1427508B81001765289527": ('Mayama', (('Ouesso', 'Sangha'), ('Pokola', 'Sangha'))),
    "1427508B56162922568882": ('Mayoko', (('Loudima', 'Bouenza'),)),
    "1427508B97285860455499": ('Mbomo', (('Owando', 'Cuvette'), ('Oyo', 'Cuvette'))),
    "1427508B75141491859674": ('Mfouati', ()),
    "1427508B59827830762916": ('Mindouli', (('Sémbé', 'Sangha'),)),
    "1427508B15105578077856": ('Mossaka', (('Makoua', 'Cuvette'), ('Etoumbi', 'Cuvette'))),
    "1427508B80480986798258": ('Mossendjo', (('Mossendjo', 'Niari'), ('Makabana', 'Niari'))),
    "1427508B15475197726652": ('Mouyondzi', (('Komono', 'Lékoumou'),)),
    "1427508B61990320035466": ('Mvouti', ()),
    "1427508B65710782923529": ('Ngabe', (('Bétou', 'Likouala'),)),
    "1427508B77398983922778": ('Ngamaba (Brazzaville)', (('Loukoléla', 'Cuvette'),)),
    "1427508B61361969612670": ('Nkayi District', ()),
    "1427508B68234406405678": ('Okoyo', (('Djambala', 'Plateaux'), ('Ngo', 'Plateaux'))),
    "1427508B53261587685070": ('Ouesso', (('Kimongo', 'Niari'),)),
    "1427508B2711916711363": ('Owando', (('Impfondo', 'Likouala'),)),
    "1427508B36736410961843": ('Sembe', ()),
    "1427508B97911920098137": ('Sibiti', (('Lékana', 'Plateaux'),)),
    "1427508B74488627772391": ('Souanke', (('Nkayi', 'Bouenza'), ('Kayes', 'Bouenza'))),
    "1427508B80151114352270": ('Zanaga', (('Brazzaville', 'Brazzaville'), ('Boukiéro', 'Brazzaville'))),
}

# A district the census counts under one department whose ground the map draws
# inside another department's polygon: (folded name) -> (counted under, drawn in).
MOVED: dict[str, tuple[str, str]] = {"tchiambanzassi": ("Pointe-Noire", "Kouilou")}
# The kinds of unit a department page lists below it.
UNIT_KINDS = frozenset({"District", "Commune", "Urban Commune", "Rural Commune",
                        "Arrondissement", "City", "Municipality"})

AGE_GAP = ("The 2023 census's preliminary results give each department's population by sex but "
           "not by age, so no median age is shown.")


def rows_of(page: str) -> list[list[str]]:
    return [cells for cells, _ in linked_rows(page)]


def linked_rows(page: str) -> list[tuple[list[str], str | None]]:
    """Each table row's cells, and the first link in it."""
    out = []
    for row in re.finditer(r"(?is)<tr\b.*?</tr>", page):
        raw = row.group(0)
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", raw)]
        href = re.search(r"""href=["']([^"']+)["']""", raw)
        if cells:
            out.append((cells, html.unescape(href.group(1)) if href else None))
    return out


def number(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def address(href: str) -> str:
    """A page's absolute address, as a request line can carry it."""
    full = href if href.startswith("http") else HOST + href
    return urllib.parse.quote(full, safe=":/%")


def sexes(page: str) -> tuple[int, int] | None:
    """A unit page's men and women, where it gives them."""
    rows = rows_of(page)
    men = next((number(r[1]) for r in rows if len(r) >= 2 and r[0] == "Males"), None)
    women = next((number(r[1]) for r in rows if len(r) >= 2 and r[0] == "Females"), None)
    return (men, women) if men and women else None


def department(page: str) -> dict[str, Any] | None:
    """A department page: its name, count, men and women, and the districts it lists."""
    rows = linked_rows(page)
    head = next((r for r, _ in rows if len(r) >= 3 and r[1] == "Department"), None)
    sexed = sexes(page)
    if head is None or sexed is None:
        return None
    districts = [{"name": cells[0], "status": cells[1], "total": number(cells[2]),
                  "url": address(href) if href and "/admin/" in href else None}
                 for cells, href in rows
                 if len(cells) >= 3 and number(cells[2])
                 and (cells[1] in UNIT_KINDS or (href and "/admin/" in href
                                                 and cells[1] not in ("Department", "Status")))]
    return {"name": head[0], "total": number(head[2]), "men": sexed[0], "women": sexed[1],
            "districts": districts}


def links(page: str) -> tuple[list[str], int]:
    """The department pages linked from the country page, and how many districts it lists."""
    hrefs = set(re.findall(r'href="([^"]*?/en/congo/admin/[^"]+)"', page))
    deps = sorted({h for h in hrefs if re.search(r"/admin/\d{2}__[^/]+/?$", h)})
    districts = {h for h in hrefs if re.search(r"/admin/[^/]+/\d{4}x?__[^/]+/?$", h)}
    full = [h if h.startswith("http") else HOST + h for h in deps]
    # Lékoumou's address has an accent, which a request line cannot carry as is.
    return [urllib.parse.quote(html.unescape(u), safe=":/%") for u in full], len(districts)


def moves(found: list[dict[str, Any]], get: Callable[[str], str]) -> list[dict[str, Any]]:
    """Each MOVED district as the census counts it: its count, and its men and women
    where its own page gives them and they make its count."""
    by = {fold(d["name"]): d for d in found}
    out = []
    for key, (counted, drawn) in MOVED.items():
        src, dst = by.get(fold(counted)), by.get(fold(drawn))
        if src is None or dst is None:
            raise SystemExit(f"congo_census: no department {counted} or {drawn}")
        hits = [d for d in src.get("districts") or [] if fold(d["name"]).startswith(key)]
        if not hits and any(fold(d["name"]).startswith(key) for d in dst.get("districts") or []):
            log(f"  {key}: counted under {drawn} now; nothing to move")
            continue
        if len(hits) != 1:
            raise SystemExit(f"congo_census: {counted}'s page lists no district {key}")
        hit = hits[0]
        men = women = None
        if hit.get("url"):
            found_sexes = sexes(get(hit["url"]))
            if found_sexes and sum(found_sexes) == hit["total"]:
                men, women = found_sexes
        out.append({"name": hit["name"], "total": hit["total"], "men": men, "women": women,
                    "from": src["name"], "to": dst["name"], "url": hit.get("url")})
        log(f"  {hit['name']}: {hit['total']:,} counted under {src['name']}, drawn in "
            f"{dst['name']}" + (f" ({men:,} men, {women:,} women)" if men else
                                "; its men and women not given apart"))
    return out


def town_note(label: str, places: tuple[tuple[str, str], ...], districts: int) -> str:
    if places and fold(places[0][0]) == fold(label.split("(")[0]):
        lead = f"This polygon is labelled {label} and holds the town of that name"
    elif places:
        towns = " and ".join(f"{n} ({d})" for n, d in places)
        lead = (f"This polygon is labelled {label}, but the "
                f"{'towns' if len(places) > 1 else 'town'} inside it "
                f"{'are' if len(places) > 1 else 'is'} {towns}")
    else:
        lead = f"This polygon is labelled {label}, and no town that would show its district lies in it"
    return (f"{lead}. The 46 polygons drawn for the Republic of the Congo at this level carry "
            f"names out of place across the country, and the 2023 census counts the "
            f"{districts} districts and communes of today, which are not drawn, so no district's "
            f"figures are shown here.")


def capital_note(label: str, places: tuple[tuple[str, str], ...]) -> str:
    """Why no seat is shown, from what the polygon holds."""
    name = label.split("(")[0].strip()
    if places and fold(places[0][0]) == fold(name):
        return (f"This polygon holds the town of {places[0][0]}, but the polygons drawn for the "
                f"Republic of the Congo at this level do not follow today's districts, so it "
                f"cannot be taken for one, and no district's seat is shown.")
    if places:
        towns = " and ".join(f"{n} ({d})" for n, d in places)
        return (f"The {'towns' if len(places) > 1 else 'town'} inside this polygon "
                f"{'are' if len(places) > 1 else 'is'} {towns}, not {name}, the name it is "
                f"drawn under, so it cannot be taken for the district of {name}, and no "
                f"district's seat is shown.")
    return ("No town inside this polygon shows which district it is, and the polygons drawn "
            "for the Republic of the Congo at this level carry names out of place across the "
            "country, so no district's seat is shown.")


def shown_counts(dep: dict[str, Any], moved: list[dict[str, Any]]
                 ) -> tuple[int, int, int, list[tuple[dict[str, Any], int]], bool]:
    """A department's count on the ground drawn for it, its men and women, the moves
    that touch it (each with its sign), and whether their men and women were known."""
    touching = [(m, -1) for m in moved if fold(m["from"]) == fold(dep["name"])] + \
               [(m, +1) for m in moved if fold(m["to"]) == fold(dep["name"])]
    total, men, women = dep["total"], dep["men"], dep["women"]
    sexed = all(m["men"] is not None for m, _ in touching)
    for m, sign in touching:
        total += sign * m["total"]
        if sexed:
            men += sign * m["men"]
            women += sign * m["women"]
    return total, men, women, touching, sexed


def build(found: list[dict[str, Any]], districts: int, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], urls: dict[str, str],
          moved: list[dict[str, Any]] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    moved = moved or []
    first = {fold(u["name"]): u for u in admin1}
    for dep in found:
        poly = first.get(fold(dep["name"]))
        if poly is None:
            raise SystemExit(f"congo_census: no polygon for department {dep['name']}")
        total, men, women, touching, sexed = shown_counts(dep, moved)
        # The median-age note rests on the same results, which give no ages.
        cite = [{"field": "population/sex_ratio/median_age note", "name": SOURCE,
                 "url": urls[dep["name"]], "year": YEAR, "license": LICENCE}]
        pop_note = (f"The population of {poly['name']} at the 2023 census, from its "
                    f"preliminary results.")
        ratio_note = (f"Men per 1,000 women among the people the 2023 census counted "
                      f"({men:,} men, {women:,} women), from its preliminary results.")
        for m, sign in touching:
            if sign > 0:
                pop_note = (f"The 2023 census's preliminary results count {dep['total']:,} "
                            f"people in {dep['name']} department and {m['total']:,} in the "
                            f"district of {m['name']}, which they count under {m['from']} "
                            f"department but which lies inside this polygon; the two are "
                            f"added here.")
                cite.append({"field": "population" + ("/sex_ratio" if sexed else ""),
                             "name": SOURCE, "url": m.get("url") or urls[m["from"]],
                             "year": YEAR, "license": LICENCE})
            else:
                pop_note = (f"The 2023 census's preliminary results count {dep['total']:,} "
                            f"people in {dep['name']} department, {m['total']:,} of them in "
                            f"the district of {m['name']}, which lies inside the polygon drawn "
                            f"as {m['to']}; the {total:,} others are shown here.")
            if sexed:
                ratio_note = (f"Men per 1,000 women among the people the 2023 census counted "
                              f"on this ground ({men:,} men, {women:,} women, the district of "
                              f"{m['name']} {'added' if sign > 0 else 'left out'}), from its "
                              f"preliminary results.")
            else:
                ratio_note = (f"Men per 1,000 women among the people the 2023 census counted in "
                              f"{dep['name']} department ({men:,} men, {women:,} women), "
                              + (f"without the district of {m['name']}" if sign > 0 else
                                 f"the district of {m['name']} included")
                              + ", whose men and women its preliminary results do not give "
                                "apart.")
        records.append(record(
            f"COG-RGPH2023-{poly['id']}", poly["name"], level="admin1", parent="COG", country="COG",
            match_by="shape_id", shape_id=poly["id"], sources=cite,
            population=measure(total, year=YEAR, source=SOURCE),
            population_note=pop_note,
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            sex_ratio_note=ratio_note,
            median_age=gap(NOT_AVAILABLE, AGE_GAP)))
        report.append(f"  {poly['name']}: {total:,} ({men:,} men, {women:,} women)"
                      + (f"; as counted {dep['total']:,}" if touching else ""))
    drawn = {u["id"]: u for u in admin2}
    # What each polygon's reasons rest on: the census's count of today's
    # districts, and GeoNames' towns inside the polygon. Neither gives a figure.
    reasons = [{"field": "population note/sex_ratio note/median_age note", "name": SOURCE,
                "url": ADMIN, "year": YEAR, "license": LICENCE},
               {"field": "population note/sex_ratio note/median_age note/capital note",
                "name": "GeoNames, populated places", "url": "https://www.geonames.org/",
                "license": "CC BY 4.0"}]

    def stated(note: str) -> dict[str, Any]:
        # The statement displaces an encyclopaedia's figure bound to the polygon
        # by its name, dated or not: the name is not the polygon's.
        return {**gap(NOT_AVAILABLE, note), "displaces_before": YEAR + 1,
                "displaces_undated": True}

    for sid, (label, places) in FACTS.items():
        u = drawn.get(sid)
        if u is None or u["name"] != label:
            report.append(f"  polygon {sid} ({label}): no longer drawn as measured; left out")
            continue
        note = town_note(label, places, districts)
        records.append(record(
            f"COG-RGPH2023-{sid}", label, level="admin2", parent="COG", country="COG",
            match_by="shape_id", shape_id=sid, population=stated(note),
            median_age=stated(note), sex_ratio=stated(note), sources=reasons,
            capital=gap(NOT_AVAILABLE, capital_note(label, places))))
    report.append(f"  {sum(r['level'] == 'admin2' for r in records)} second-level polygons given "
                  f"reasons")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()

    def get(url: str) -> str:
        return http_get(url, binary=True, cache=False, timeout=120).decode("utf-8", "replace")

    page = get(ADMIN)
    pages, districts = links(page)
    log(f"congo_census: {len(pages)} department pages, {districts} districts and communes listed")
    found, urls = [], {}
    for url in pages:
        dep = department(get(url))
        if dep is None or dep["total"] != dep["men"] + dep["women"]:
            raise SystemExit(f"congo_census: {url}: no count by sex read ({dep})")
        found.append(dep)
        urls[dep["name"]] = url
        made = sum(d["total"] for d in dep["districts"])
        log(f"  {dep['name']}: {len(dep['districts'])} districts and communes listed, making "
            f"{made:,} of {dep['total']:,}: "
            + "; ".join(f"{d['name']} {d['total']:,}" for d in dep["districts"]))
    total = sum(d["total"] for d in found)
    log(f"  the departments make {total:,}")
    if total != NATIONAL or len(found) != 12:
        raise SystemExit(f"congo_census: {len(found)} departments making {total:,}, not {NATIONAL:,}")
    moved = moves(found, get)
    admin1 = json.loads((SITE / "admin1" / "COG.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "COG.units.json").read_text())
    records, report = build(found, districts, admin1, admin2, urls, moved)
    for line in report:
        log(line)
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
