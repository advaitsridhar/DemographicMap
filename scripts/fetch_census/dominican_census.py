#!/usr/bin/env python3
"""The Dominican Republic's 2022 census by province and municipio.

ONE's *X Censo Nacional de Población y Vivienda 2022* publishes its Volume III
(*Características demográficas básicas*, 2024) as one workbook a table. ONE's
site refuses this map's reader (HTTP 403), so the workbooks are read from the
Internet Archive's captures of ONE's own files, byte for byte (``id_``):

* **Cuadro 2** -- everyone by zone, sex and five-year age group, for every
  region, province, municipio and distrito municipal: median age and sex
  ratio for the 32 provinces and the municipios, and the municipios'
  population (the provinces keep the map's newer 2023 figures).
* **Cuadro 12** -- everyone aged 12 and over by question 64, the informant's
  perception of each household member's "facciones, color de piel y otras
  características culturales" (Negra, Morena, Mestiza, Mulata, India,
  Asiática, Blanca, Otro), by region, province and age group: ethnicity for
  the 32 provinces. ONE tabulates it no lower than the province, and its
  REDATAM server offers the 2010, 2002 and 1981 bases and not 2022's, so the
  municipios carry that as the reason for the gap.

The census asks neither religion nor language: the 2022 questionnaire
(Volume I, Anexo II) and the 2010 one (its REDATAM dictionary, every person
variable P26 to P60) are the evidence for NOT_COLLECTED_POLICY.

Checks, all exact: every area's sexes and zones make its total, and its age
groups make it column by column; municipios make their province, provinces
their region and regions the country, in Cuadro 2; the eight answers and
"no sabe" make each area's 12-and-over population, and provinces make regions
and the country, in Cuadro 12; each sex ratio agrees with the one ONE prints.
A municipio is bound to a polygon only if its 2022 count is within a factor of
the 2010 census's count for the same polygon (the US Census Bureau's
tabulation, which ``uscb_age_sex`` binds): a municipio created since the
boundary file was drawn leaves its parent smaller than the polygon, and that
is a mis-match this refuses.

ONE's REDATAM server, redatam.one.gob.do, sends its leaf certificate without
the intermediate above it. ``--probe`` and ``--run`` complete the chain from
the certificate's Authority Information Access extension -- never adding a
root -- and verify in full, to read what the server offers.

Usage:
    python -m scripts.fetch_census.dominican_census
    python -m scripts.fetch_census.dominican_census --probe CPV2010
    python -m scripts.fetch_census.dominican_census --run CPV2010 FREQUENCY OF PERSONA.P27 AREABREAK PROVIN
"""

from __future__ import annotations

import argparse
import http.cookiejar
import io
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts.probe_redatam import Session, attrs, report

from . import uscb_age_sex
from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from .binding import bind, fold
from .cod_ps_age import grouped_median
from .redatam import Server, tables

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_tls import ca_issuers, decode, leaf_der  # noqa: E402

OUT = "dominican_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2022
WAYBACK = "http://web.archive.org/web/{stamp}id_/{url}"
AGES = ("https://www.one.gob.do/media/2njp32ut/cuadro-2-volumen-iii.xlsx", "20241113000805")
PERCEPTION = ("https://www.one.gob.do/media/rmfhr5tj/cuadro-12-volumen-iii.xlsx",
              "20241103231121")
SOURCE = "ONE, X Censo Nacional de Población y Vivienda 2022, Volumen III"
AGES_SOURCE = (f"{SOURCE}, Cuadro 2: population by zone, sex and age group, by region, "
               "province, municipio and distrito municipal")
PERCEPTION_SOURCE = (f"{SOURCE}, Cuadro 12: population aged 12 and over by the informant's "
                     "perception of features, skin colour and culture, by region and province")
NATIONAL = 10_773_983
NATIONAL_12 = 8_616_295
# Question 64's answers, in the order Cuadro 12 prints them, as the map names them.
# "Morena" and "India" are colour terms in the Dominican Republic, not
# Afro-descendant or indigenous peoples, and carry the country's name.
PERCEIVED = {"Negra o negro": "Black", "Morena o moreno": "Moreno (Dominican Republic)",
             "Mestiza o mestizo": "Mestizo", "Mulata o mulato": "Mulatto",
             "India o indio": "Indio (Dominican Republic)", "Asiática o asiático": "Asian",
             "Blanca o blanco": "White", "Otro": "Other"}
UNANSWERED = "No sabe o no responde"
AGE_ROW = re.compile(r"^(?:Menos de 1|(\d+)-(\d+)\.?|(\d+) [oy] más|No declarado)$")
# ONE's province names -> the boundary file's, beyond uscb_age_sex's.
PROVINCES = {"Puerta Plata": "Puerto Plata"}
# How far a polygon's 2022 count may move from its 2010 count before the
# municipio is taken to be a different unit from the polygon's.
GROWTH = (0.75, 1.75)
MUNICIPAL_GAP = (
    "ONE publishes the 2022 census's question 64 (the informant's perception of each person's "
    "features, skin colour and culture) by region and province only -- Volume III, Cuadros 11 "
    "and 12 -- and its REDATAM server offers the 2010, 2002 and 1981 censuses, not 2022's, so "
    "no municipio figure has been published to read.")

HOST = "redatam.one.gob.do"
ROOT = f"https://{HOST}"
PORTAL = ROOT + "/bindom/RpWebEngine.exe/Portal?BASE={base}&lang=esp"
CMDSET = ROOT + "/bindom/RpWebStats.exe/CmdSet"


def certificates(blob: bytes) -> list[bytes]:
    """Every certificate an AIA URL serves, as DER: PEM, DER or a PKCS#7 bundle."""
    if b"-----BEGIN CERTIFICATE-----" in blob:
        return [ssl.PEM_cert_to_DER_cert(p) for p in re.findall(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            blob.decode("ascii", "replace"), re.S)]
    try:
        decode(blob)
        return [blob]
    except ssl.SSLError:
        from cryptography.hazmat.primitives.serialization import Encoding, pkcs7
        return [c.public_bytes(Encoding.DER) for c in pkcs7.load_der_pkcs7_certificates(blob)]


def chained_context(host: str) -> tuple[ssl.SSLContext, list[str]]:
    """The system's own roots plus the intermediates the server did not send.

    The same repair as probe_tls.completed_context, stricter in one respect:
    a self-signed certificate fetched from an AIA URL is never added, so the
    chain must still end at a root the system already trusts. Only the links
    between are taken from the network, and they are believed only if they
    verify up to that root, which the handshake then tests.
    """
    context = ssl.create_default_context()
    notes: list[str] = []
    der = leaf_der(host)
    for _ in range(4):
        urls = ca_issuers(decode(der))
        if not urls:
            break
        with urllib.request.urlopen(urls[0], timeout=30) as resp:
            found = certificates(resp.read())
        links = [c for c in found if decode(c).get("subject") != decode(c).get("issuer")]
        for link in links:
            context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(link))
        notes.append(f"  {urls[0]}: {len(found)} certificate(s), {len(links)} intermediate(s) "
                     "added; a root is never taken from the network")
        if not links:
            break
        der = links[0]
    return context, notes


class ChainSession(Session):
    """A REDATAM session over a verified connection with the chain completed."""

    def __init__(self, host: str = HOST) -> None:
        context, notes = chained_context(host)
        for note in notes:
            print(note)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def probe(session: ChainSession, bases: list[str], follow: str, limit: int) -> None:
    for page_url in [b if b.startswith("http") else PORTAL.format(base=b) for b in bases]:
        print(f"page: {page_url}")
        try:
            page = session.get(page_url)
        except Exception as exc:  # noqa: BLE001 - the probe reports what it met
            print(f"  {type(exc).__name__}: {exc}")
            continue
        links = report(page_url, page, limit)
        frames = [urllib.parse.urljoin(page_url, attrs(t)["src"])
                  for t in re.findall(r"(?is)<i?frame\b[^>]*>", page) if attrs(t).get("src")]
        words = [w for w in follow.split(",") if w]
        followed = [("frame", f) for f in frames]
        for label, url in followed:
            try:
                links += report(url, session.get(url), 0)
            except Exception as exc:  # noqa: BLE001
                print(f"  {type(exc).__name__}: {exc}")
        for label, url in [(label, url) for label, url in links
                           if any(w in label for w in words)]:
            print(f"follow: {label!r} -> {url}")
            try:
                body = session.get(url)
            except Exception as exc:  # noqa: BLE001
                print(f"  {type(exc).__name__}: {exc}")
                continue
            report(url, body, limit)


def number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        v = float(str(value).replace(",", ""))
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def workbook_rows(url: str, stamp: str) -> list[list[Any]]:
    import openpyxl
    body = http_get(WAYBACK.format(stamp=stamp, url=url), binary=True, cache=False)
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    return [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]


def areas(rows: list[list[Any]], width: int) -> list[dict[str, Any]]:
    """Each area's row and the age rows beneath it: [{label, values, ages}]."""
    out: list[dict[str, Any]] = []
    current = None
    for row in rows:
        label = re.sub(r"\s+", " ", str(row[0] or "")).strip()
        values = [number(c) for c in (list(row[1:1 + width]) + [None] * width)[:width]]
        if not label or any(v is None for v in values):
            continue
        if AGE_ROW.match(label):
            if current is None:
                raise SystemExit(f"dominican_census: an age row {label!r} before any area")
            current["ages"].append((label, values))
        else:
            current = {"label": label, "values": values, "ages": []}
            out.append(current)
    return out


def kind(label: str) -> str:
    if label == "Total":
        return "country"
    if label.startswith("Región "):
        return "region"
    if label.startswith("Provincia ") or fold(label) == "distritonacional":
        return "province"
    if label.startswith("Municipio "):
        return "municipio"
    return "part"


def bare(label: str) -> str:
    return re.sub(r"^(?:Provincia|Municipio|Región)\s+", "", label).strip()


def band(label: str) -> tuple[int, int | None] | None:
    """An age row's (low, high); None for "No declarado"."""
    m = AGE_ROW.match(label)
    if label == "Menos de 1":
        return 0, 0
    if m and m.group(1):
        return int(m.group(1)), int(m.group(2))
    if m and m.group(3):
        return int(m.group(3)), None
    return None


# ONE's 2022 figures are the count adjusted for the omission its coverage
# survey measured, province by province and municipio by municipio, and each
# printed figure is rounded on its own. So the n figures that make a total
# may miss it by up to n/2 -- Santo Domingo Este's age rows make 1,029,116
# people against the 1,029,117 printed for it. Within that, the difference
# is logged; beyond it the run stops, since then it is not rounding.
DISCREPANCIES: list[str] = []


def agree(made: list[float], printed: list[float], parts: int, what: str) -> None:
    """Sums of ``parts`` rounded figures against the printed ones, within rounding."""
    slack = max(1, (parts + 1) // 2)
    worst = max(abs(a - b) for a, b in zip(made, printed))
    if worst > slack:
        raise SystemExit(f"dominican_census: {what}: the parts make {made}, the printed "
                         f"figures {printed}; {worst} apart, more than {parts} rounded "
                         "figures can be")
    if worst:
        DISCREPANCIES.append(f"{what} (by {worst})")


def check_area(area: dict[str, Any], columns: int, what: str) -> None:
    """An area's age rows make it, column by column, within rounding."""
    made = [sum(v[i] for _, v in area["ages"]) for i in range(columns)]
    agree(made, area["values"][:columns], len(area["ages"]),
          f"{what}: {area['label']}'s age rows")


def tree(found: list[dict[str, Any]], columns: int, what: str, total: int,
         lowest: str) -> dict[str, dict[str, Any]]:
    """Province -> {area, municipios}, after every level is checked against the one above."""
    order = ["country", "region", "province", "municipio"]
    stack: dict[str, dict[str, Any]] = {}
    children: dict[int, list[dict[str, Any]]] = {}
    provinces: dict[str, dict[str, Any]] = {}
    country = None
    for area in found:
        k = kind(area["label"])
        if k == "part" or order.index(k) > order.index(lowest):
            continue
        check_area(area, columns, what)
        stack[k] = area
        for deeper in order[order.index(k) + 1:]:
            stack.pop(deeper, None)
        if k == "country":
            country = area
            continue
        parent = next((stack[p] for p in reversed(order[:order.index(k)]) if p in stack), None)
        if parent is None:
            raise SystemExit(f"dominican_census: {what}: {area['label']} has no parent")
        children.setdefault(id(parent), []).append(area)
        if k == "province":
            provinces[bare(area["label"])] = {"area": area, "municipios": []}
        if k == "municipio":
            provinces[bare(stack["province"]["label"])]["municipios"].append(area)
    if country is None or country["values"][0] != total:
        raise SystemExit(f"dominican_census: {what}: the country is "
                         f"{country and country['values'][0]}, not ONE's {total:,}")
    for area in found:
        kids = children.get(id(area))
        if kids:
            made = [sum(k["values"][i] for k in kids) for i in range(columns)]
            agree(made, area["values"][:columns], len(kids), f"{what}: {area['label']}'s parts")
    if len(provinces) != 32:
        raise SystemExit(f"dominican_census: {what}: {len(provinces)} provinces, not 32")
    return provinces


def zones_check(values: list[float], what: str) -> None:
    """Sexes and zones make their totals, each sum of two within rounding."""
    t, h, m, ut, uh, um, rt, rh, rm = values[:9]
    agree([h + m, uh + um, rh + rm, ut + rt, uh + rh, um + rm], [t, ut, rt, t, h, m], 2,
          f"{what}'s sexes and zones")


def age_figures(area: dict[str, Any]) -> dict[str, Any]:
    """Median age, sex ratio and population from an area of Cuadro 2."""
    values = area["values"]
    zones_check(values, area["label"])
    total, men, women = values[:3]
    printed = values[9] if len(values) > 9 else None
    if printed is not None and abs(100 * men / women - printed) > 0.01:
        raise SystemExit(f"dominican_census: {area['label']}: {men:,} men to {women:,} women "
                         f"is not the ratio {printed} ONE prints")
    groups = [(b[0], b[1], v[0]) for label, v in area["ages"] if (b := band(label))]
    unstated = sum(v[0] for label, v in area["ages"] if band(label) is None)
    note = ("Interpolated within the five-year age group that holds the middle person, from the "
            "2022 census's count by age group")
    return {
        "population": measure(total, unit="people", year=YEAR, source=AGES_SOURCE),
        "median_age": measure(grouped_median(groups), unit="years", year=YEAR,
                              source=AGES_SOURCE),
        "median_age_note": (f"{note}; the {unstated:,} people whose age was not declared are "
                            "left out." if unstated else f"{note}."),
        "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                             year=YEAR, source=AGES_SOURCE),
    }


def perception_fields(area: dict[str, Any], header: list[str]) -> dict[str, Any]:
    values = area["values"]
    total, answers = values[0], dict(zip(header, values[1:]))
    if sum(answers.values()) != total:
        raise SystemExit(f"dominican_census: {area['label']}'s answers make "
                         f"{sum(answers.values()):,}, not its {total:,}")
    counts = {PERCEIVED[k]: v for k, v in answers.items() if k != UNANSWERED}
    return {
        "ethnicity": shares(counts),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Question 64 of the 2022 census: the informant's perception of each household "
            "member's features, skin colour and other cultural characteristics (\"Las personas "
            "suelen definirse a sí mismas de acuerdo con sus facciones, color de piel y otras "
            "características culturales\"), in ONE's eight answers -- negra, morena, mestiza, "
            "mulata, india, asiática, blanca, otra. ONE tabulates it for everyone aged 12 and "
            f"over: {total:,} people here, of whom {answers[UNANSWERED]:,} are \"no sabe o no "
            "responde\" and left out of the shares. Morena and india are colour terms in the "
            "Dominican Republic, not Afro-descendant or indigenous peoples."),
    }


def perception(rows: list[list[Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    head_row = next((r for r in rows if any(str(c or "").strip() == "Negra o negro" for c in r)),
                    None)
    if head_row is None:
        raise SystemExit("dominican_census: Cuadro 12 has no header naming its answers")
    header = [re.sub(r"\s+", " ", str(c or "")).strip() for c in head_row[2:11]]
    if header != [*PERCEIVED, UNANSWERED]:
        raise SystemExit(f"dominican_census: Cuadro 12's answers are {header}, not "
                         f"{[*PERCEIVED, UNANSWERED]}")
    found = areas(rows, 10)
    # Cuadro 12 has no municipios: every area under a region is a province.
    for area in found:
        if kind(area["label"]) == "part":
            area["label"] = "Provincia " + area["label"]
    return header, tree(found, 10, "Cuadro 12", NATIONAL_12, "province")


def binding_2010(admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> dict[str, int]:
    """Polygon -> the 2010 census's count, bound exactly as uscb_age_sex binds it."""
    country = uscb_age_sex.COUNTRIES[0]
    units = uscb_age_sex.read(country)
    parents = {u["id"]: u["name"] for u in admin1}
    by_fold = {fold(u["name"]): u["name"] for u in admin1}
    for theirs, ours in country.parents:
        by_fold[fold(theirs)] = ours
    offices = {u["code"]: (u["name"], by_fold[fold(u["parent"])]) for u in units}
    aliases = {u["name"]: u["nso"] for u in units if u["nso"]}
    aliases.update(dict(country.units))
    bound, _ = bind(offices, admin2, parents, aliases)
    totals = {u["code"]: u["total"] for u in units}
    return {sid: totals[code] for code, sid in bound.items()}


def sources(fields: str, perception_too: bool) -> list[dict[str, Any]]:
    out = [{"field": fields, "name": AGES_SOURCE, "url": WAYBACK.format(stamp=AGES[1], url=AGES[0]),
            "year": YEAR}]
    if perception_too:
        out.append({"field": "ethnicity", "name": PERCEPTION_SOURCE,
                    "url": WAYBACK.format(stamp=PERCEPTION[1], url=PERCEPTION[0]), "year": YEAR})
    return out


def adapter() -> int:
    header, perceived = perception(workbook_rows(*PERCEPTION))
    provinces = tree(areas(workbook_rows(*AGES), 10), 9, "Cuadro 2", NATIONAL, "municipio")
    municipios = sum(len(p["municipios"]) for p in provinces.values())
    log(f"  Cuadro 2: 32 provinces and {municipios} municipios making ONE's {NATIONAL:,}, every "
        "area's age rows making it within rounding")
    log(f"  Cuadro 12: 32 provinces making ONE's {NATIONAL_12:,} aged 12 and over, every area's "
        "age rows making it")
    log(f"  {len(DISCREPANCIES)} sums within the rounding of ONE's adjusted figures but not "
        "exact: " + "; ".join(DISCREPANCIES))

    admin1 = json.loads((SITE / "admin1" / "DOM.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "DOM.units.json").read_text())
    country = uscb_age_sex.COUNTRIES[0]
    province_alias = {fold(k): v for k, v in (*country.parents, *PROVINCES.items())}
    first = {fold(u["name"]): u for u in admin1}

    def shape_of(name: str) -> dict[str, Any]:
        shape = first.get(fold(province_alias.get(fold(name), name)))
        if shape is None:
            raise SystemExit(f"dominican_census: province {name!r} has no polygon")
        return shape

    records = []
    perceived_by = {shape_of(k)["id"]: v for k, v in perceived.items()}
    for name, entry in provinces.items():
        shape = shape_of(name)
        fields = age_figures(entry["area"])
        fields.pop("population")   # the map's 2023 figures are newer
        answers = perceived_by.get(shape["id"])
        if answers is None:
            raise SystemExit(f"dominican_census: Cuadro 12 has no province {name!r}")
        records.append(record(
            f"DOM-ONE-{fold(name)}", shape["name"], level="admin1", parent="DOM", country="DOM",
            match_by="shape_id", shape_id=shape["id"],
            aliases=[name] if name != shape["name"] else [], **fields,
            **perception_fields(answers["area"], header),
            sources=sources("median age/sex ratio", True)))

    parents = {u["id"]: u["name"] for u in admin1}
    unit_alias = {fold(k): v for k, v in country.units}
    offices, areas_by = {}, {}
    for name, entry in provinces.items():
        for area in entry["municipios"]:
            code = f"{fold(name)}-{fold(bare(area['label']))}"
            offices[code] = (bare(area["label"]), shape_of(name)["name"])
            areas_by[code] = area
    aliases = {n: unit_alias[fold(n)] for n, _ in offices.values() if fold(n) in unit_alias}
    bound, missing = bind(offices, admin2, parents, aliases)
    log(f"  {len(bound)} municipios bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    in_2010 = binding_2010(admin1, admin2)
    labels = {s["id"]: s["name"] for s in admin2}
    refused = []
    for code, sid in sorted(bound.items()):
        area = areas_by[code]
        before = in_2010.get(sid)
        growth = area["values"][0] / before if before else None
        if growth is None or not GROWTH[0] <= growth <= GROWTH[1]:
            refused.append(f"{offices[code][0]} ({labels[sid]}): {area['values'][0]:,} in 2022 "
                           f"against {before} in 2010")
            continue
        records.append(record(
            f"DOM-ONE-{code}", labels[sid], level="admin2", parent="DOM", country="DOM",
            parent_name=offices[code][1], match_by="shape_id", shape_id=sid,
            aliases=[offices[code][0]] if offices[code][0] != labels[sid] else [],
            **age_figures(area), ethnicity=gap(NOT_AVAILABLE, MUNICIPAL_GAP),
            sources=sources("population/median age/sex ratio", False)))
    log(f"  refused, the polygon being another extent than the 2022 municipio: {refused}")
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no municipio: {unbound}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", help="comma-separated base names whose portals to open, or URLs")
    ap.add_argument("--follow", default="", help="comma-separated words of links to open")
    ap.add_argument("--run", nargs="+", metavar="WORD",
                    help="a base name, then a Redatam+SP program as words")
    ap.add_argument("--header", default="Casos")
    ap.add_argument("--limit", type=int, default=3000)
    args = ap.parse_args()
    if not (args.probe or args.run):
        return adapter()
    session = ChainSession()
    if args.probe:
        probe(session, args.probe.split(","), args.follow, args.limit)
    if args.run:
        base, *words = args.run
        text = re.sub(r"\s+(?=(?:TABLE|AS|OF|BY|AREABREAK|DEFINE|TYPE|FOR|UNIVERSE)\s)",
                      "\n    ", " ".join(words))
        program = "RUNDEF Job\n    SELECTION ALL\n\nTABLE T1\n    " + text + "\n"
        print(program)
        session.get(PORTAL.format(base=base))
        server = Server(CMDSET, base, session=session, who="dominican_census")
        for page in server.output(program):
            report(CMDSET, page, args.limit)
            for t in tables(page, args.header):
                print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                      f"total={t['total']} na={t['na']} rows={t['rows'][:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
