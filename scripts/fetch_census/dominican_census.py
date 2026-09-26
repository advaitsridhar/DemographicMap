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
# ONE's 2022 spellings of municipios -> the boundary file's, beyond those
# uscb_age_sex writes for the Bureau's 2010 names.
MUNICIPIOS = {"Villa La Mata": "La Mata", "Cambita Garavitos": "Cambita Garabito"}
# Polygons the boundary file draws for a distrito municipal rather than a
# municipio -> ONE's name for the district. The district's figures go to its
# polygon, and are taken out of its municipio's, whose polygon leaves it out.
DISTRICT_POLYGONS = {"La Laguna de Nisibón": "Las Lagunas de Nisibón"}
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


def workbook_rows(url: str, stamp: str) -> tuple[list[list[Any]], set[str]]:
    """A Volume III workbook's table, and the provinces its index sheet names.

    Every table carries a second sheet ("Hoja2") listing its areas; the one
    list that writes "Provincia" before a province's name is the only place
    the tables say which bare names are provinces.
    """
    import openpyxl
    body = http_get(WAYBACK.format(stamp=stamp, url=url), binary=True, cache=False)
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    rows = [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]
    named: set[str] = set()
    for sheet in book.worksheets[1:]:
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                text = re.sub(r"\s+", " ", str(cell or "")).strip()
                if text.startswith("Provincia ") or fold(text) == "distritonacional":
                    named.add(fold(bare(text)))
    return rows, named


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


def kind(label: str, municipio: str | None = None, provinces: set[str] | None = None) -> str:
    """What an area of Volume III is, from its label and the municipio it follows.

    Regions and municipios carry their word ("Región", "Municipio") and
    distritos municipales a "(D.M.)"; provinces carry nothing but their name
    (the Distrito Nacional aside), and nor does the head district of a
    municipio, which follows it. So a bare name is a province only if the
    workbook's index names it as one (``provinces``) and it is not the head
    district of the municipio just read -- Monte Cristi is both -- and a
    part otherwise. The sums then check it: a province must be its
    municipios, a region its provinces, and a municipio its districts.
    """
    if label == "Total":
        return "country"
    if label.startswith("Región "):
        return "region"
    if label.startswith("Municipio "):
        return "municipio"
    if label.endswith("(D.M.)"):
        return "part"
    if label.startswith("Provincia ") or fold(label) == "distritonacional":
        return "province"
    if municipio is not None and fold(label) == fold(bare(municipio)):
        return "part"
    if provinces is not None and fold(label) not in provinces:
        return "part"
    return "province"


def classify(found: list[dict[str, Any]], provinces: set[str] | None = None
             ) -> list[dict[str, Any]]:
    """Each area with its kind, read in order."""
    municipio = None
    for area in found:
        area["kind"] = kind(area["label"], municipio, provinces)
        if area["kind"] == "municipio":
            municipio = area["label"]
        elif area["kind"] != "part":
            municipio = None
    return found


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


def agree(made: list[float], printed: list[float], parts: int, what: str,
          fatal: bool = True) -> None:
    """Sums of ``parts`` rounded figures against the printed ones, within rounding.

    ``fatal`` False is for figures nothing here uses -- a distrito
    municipal's age rows -- whose disagreement is logged and not a reason to
    refuse the tables around them.
    """
    slack = max(1, (parts + 1) // 2)
    worst = max(abs(a - b) for a, b in zip(made, printed))
    if worst > slack and not fatal:
        DISCREPANCIES.append(f"{what} (by {worst}, beyond rounding; not used)")
        return
    if worst > slack:
        raise SystemExit(f"dominican_census: {what}: the parts make {made}, the printed "
                         f"figures {printed}; {worst} apart, more than {parts} rounded "
                         "figures can be")
    if worst:
        DISCREPANCIES.append(f"{what} (by {worst})")


def check_area(area: dict[str, Any], columns: int, what: str, fatal: bool = True) -> None:
    """An area's age rows make it, column by column, within rounding."""
    made = [sum(v[i] for _, v in area["ages"]) for i in range(columns)]
    agree(made, area["values"][:columns], len(area["ages"]),
          f"{what}: {area['label']}'s age rows", fatal)


def tree(found: list[dict[str, Any]], columns: int, what: str, total: int,
         named: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Province -> {area, municipios}, after every level is checked against the one above.

    A province with no municipio beneath it -- the Distrito Nacional, whose
    one municipio Volume III does not print apart -- is its own municipio.
    """
    order = ["country", "region", "province", "municipio", "part"]
    stack: dict[str, dict[str, Any]] = {}
    children: dict[int, list[dict[str, Any]]] = {}
    provinces: dict[str, dict[str, Any]] = {}
    country = None
    for area in classify(found, named):
        k = area["kind"]
        check_area(area, columns, what, fatal=k != "part")
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
        if k == "part" and "municipio" in stack:
            stack["municipio"].setdefault("parts", []).append(area)
    if country is None or country["values"][0] != total:
        raise SystemExit(f"dominican_census: {what}: the country is "
                         f"{country and country['values'][0]}, not ONE's {total:,}")
    for area in found:
        kids = children.get(id(area))
        if kids:
            made = [sum(k["values"][i] for k in kids) for i in range(columns)]
            agree(made, area["values"][:columns], len(kids), f"{what}: {area['label']}'s parts")
    if len(provinces) != 32:
        raise SystemExit(f"dominican_census: {what}: {len(provinces)} provinces, not 32: "
                         f"{sorted(provinces)}")
    for name, entry in provinces.items():
        if not entry["municipios"] and any(a["kind"] == "municipio" for a in found):
            entry["municipios"] = [{**entry["area"], "label": f"Municipio {name}"}]
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


def perception(rows: list[list[Any]], named: set[str] | None = None
               ) -> tuple[list[str], dict[str, dict[str, Any]]]:
    head_row = next((r for r in rows if any(str(c or "").strip() == "Negra o negro" for c in r)),
                    None)
    if head_row is None:
        raise SystemExit("dominican_census: Cuadro 12 has no header naming its answers")
    header = [re.sub(r"\s+", " ", str(c or "")).strip() for c in head_row[2:11]]
    if header != [*PERCEIVED, UNANSWERED]:
        raise SystemExit(f"dominican_census: Cuadro 12's answers are {header}, not "
                         f"{[*PERCEIVED, UNANSWERED]}")
    return header, tree(areas(rows, 10), 10, "Cuadro 12", NATIONAL_12, named)


def districts_2010() -> dict[tuple[str, str], str]:
    """(province, distrito municipal) -> the municipio it lay in at the 2010 census.

    Read from the US Census Bureau's workbook of the 2010 census, whose
    fourth level is the distritos municipales. A municipio created since
    from one of them has no polygon of its own: the boundary file draws the
    2010 municipio, which still takes it in.
    """
    import openpyxl
    from . import uscb
    url = uscb.workbook_url(uscb_age_sex.COUNTRIES[0].dataset)
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    rows = uscb.sheet_rows(book, "Age-Sex")
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    out = {}
    for row in rows[2:]:
        if str(row[at["ADM_LEVEL"]]).strip() == "4":
            out[(fold(row[at["ADM2_NAME"]]), fold(row[at["ADM4_NAME"]]))] = str(
                row[at["ADM3_NAME"]]).strip()
    return out


def absorb(provinces: dict[str, dict[str, Any]], unbound: list[str],
           districts: dict[tuple[str, str], str]) -> list[str]:
    """Fold each municipio made since 2010 from a distrito municipal into its 2010 municipio.

    Its counts and age rows are added to the municipio it was carved from,
    so that the figures describe the extent the boundary file draws; the
    printed sex ratio no longer applies and is dropped. Returns what was done.
    """
    done = []
    for province, entry in provinces.items():
        keep = []
        for area in entry["municipios"]:
            name = bare(area["label"])
            parent = districts.get((fold(province), fold(name)))
            # A municipio's own head district shares its name, so a 2010
            # district of the same name (Oviedo's) is no parent to fold into.
            host = next((a for a in entry["municipios"]
                         if parent and a is not area and fold(parent) != fold(name)
                         and fold(bare(a["label"])) == fold(parent)), None)
            if name not in unbound or host is None:
                keep.append(area)
                continue
            host["values"] = [a + b for a, b in zip(host["values"][:9], area["values"][:9])]
            host["values"].append(None)
            # A small municipio prints no row for an age group it has nobody
            # in, so the two are added group by group, in age order.
            mine, theirs = dict(host["ages"]), dict(area["ages"])
            labels = sorted(set(mine) | set(theirs),
                            key=lambda lb: (band(lb) is None, (band(lb) or (0, 0))[0]))
            zero = [0] * 9
            host["ages"] = [(lb, [a + b for a, b in zip(mine.get(lb, zero)[:9],
                                                        theirs.get(lb, zero)[:9])] + [None])
                            for lb in labels]
            host.setdefault("absorbed", []).append(name)
            done.append(f"{name} into {bare(host['label'])} ({province})")
        entry["municipios"] = keep
    return done


def carve(municipio: dict[str, Any], district: dict[str, Any]) -> dict[str, Any]:
    """A municipio's area less one of its districts: counts and age rows, group by group."""
    mine, theirs = dict(municipio["ages"]), dict(district["ages"])
    missing = sorted(set(theirs) - set(mine))
    if missing:
        raise SystemExit(f"dominican_census: {district['label']} has ages {missing} that "
                         f"{municipio['label']} has not")
    zero = [0] * 9
    ages = [(lb, [a - b for a, b in zip(v[:9], theirs.get(lb, zero)[:9])] + [None])
            for lb, v in municipio["ages"]]
    if any(n < 0 for _, v in ages for n in v[:9]):
        raise SystemExit(f"dominican_census: {district['label']} has more people in an age "
                         f"group than {municipio['label']}")
    return {**municipio, "values": [a - b for a, b in zip(municipio["values"][:9],
                                                          district["values"][:9])] + [None],
            "ages": ages, "carved": bare(district["label"].replace("(D.M.)", ""))}


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
    header, perceived = perception(*workbook_rows(*PERCEPTION))
    rows, named = workbook_rows(*AGES)
    # The index sheets spell some provinces two ways ("Puerta Plata",
    # "Monseñol Nouel" beside the right spellings), so it names more than 32;
    # the tree still finds exactly 32 or stops.
    if len(named) < 32:
        raise SystemExit(f"dominican_census: Cuadro 2's index names {len(named)} provinces: "
                         f"{sorted(named)}")
    provinces = tree(areas(rows, 10), 9, "Cuadro 2", NATIONAL, named)
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
    unit_alias = {fold(k): v for k, v in (*country.units, *MUNICIPIOS.items())}

    def offices_of() -> tuple[dict[str, tuple[str, str]], dict[str, dict[str, Any]]]:
        offices, areas_by = {}, {}
        for name, entry in provinces.items():
            for area in entry["municipios"]:
                code = f"{fold(name)}-{fold(bare(area['label']))}"
                offices[code] = (bare(area["label"]), shape_of(name)["name"])
                areas_by[code] = area
        return offices, areas_by

    offices, areas_by = offices_of()
    aliases = {n: unit_alias[fold(n)] for n, _ in offices.values() if fold(n) in unit_alias}
    bound, missing = bind(offices, admin2, parents, aliases)
    unbound = [offices[c][0] for c in offices if c not in bound]
    merged = absorb(provinces, unbound, districts_2010())
    log(f"  municipios made since 2010 from a distrito municipal, added back into the 2010 "
        f"municipio whose polygon takes them in: {merged}")
    offices, areas_by = offices_of()
    bound, missing = bind(offices, admin2, parents, aliases)
    log(f"  {len(bound)} municipios bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    # A polygon the boundary file draws for a distrito municipal: its figures
    # are the district's, and its municipio's polygon is the municipio less it.
    taken = set(bound.values())
    for shape in admin2:
        district_name = DISTRICT_POLYGONS.get(shape["name"])
        if shape["id"] in taken or district_name is None:
            continue
        found = [(code, part) for code, area in areas_by.items() for part in area.get("parts", [])
                 if fold(part["label"].replace("(D.M.)", "")) == fold(district_name)
                 and offices[code][1] == parents.get(shape["parent"])]
        if len(found) != 1:
            raise SystemExit(f"dominican_census: {len(found)} districts named {district_name!r} "
                             f"in {parents.get(shape['parent'])}")
        code, part = found[0]
        areas_by[code] = carve(areas_by[code], part)
        new_code = f"{code.split('-')[0]}-{fold(district_name)}"
        offices[new_code] = (district_name, offices[code][1])
        areas_by[new_code] = part
        bound[new_code] = shape["id"]
        log(f"  {shape['name']}: the distrito municipal {part['label']} "
            f"({part['values'][0]:,}), taken out of {offices[code][0]}")
    in_2010 = binding_2010(admin1, admin2)
    labels = {s["id"]: s["name"] for s in admin2}
    refused = []
    for code, sid in sorted(bound.items()):
        area = areas_by[code]
        before = in_2010.get(sid)
        growth = area["values"][0] / before if before else None
        # A district's polygon had no municipio of its own in 2010 to compare
        # with; it is bound by its name within its municipio, above.
        district = offices[code][0] in DISTRICT_POLYGONS.values()
        if not district and (growth is None or not GROWTH[0] <= growth <= GROWTH[1]):
            refused.append(f"{offices[code][0]} ({labels[sid]}): {area['values'][0]:,} in 2022 "
                           f"against {before} in 2010")
            continue
        fields = age_figures(area)
        if area.get("carved"):
            fields["population_note"] = (
                f"{offices[code][0]} without the distrito municipal of {area['carved']}, which "
                "the boundary file draws as a polygon of its own and which carries its own "
                "figures there.")
        if area.get("absorbed"):
            fields["population_note"] = (
                f"{offices[code][0]} with {', '.join(area['absorbed'])}, a distrito municipal of "
                f"{offices[code][0]} at the 2010 census and a municipio of its own since, which "
                "this polygon takes in; the median age and sex ratio are of the two together.")
        records.append(record(
            f"DOM-ONE-{code}", labels[sid], level="admin2", parent="DOM", country="DOM",
            parent_name=offices[code][1], match_by="shape_id", shape_id=sid,
            aliases=[offices[code][0]] if offices[code][0] != labels[sid] else [],
            **fields, ethnicity=gap(NOT_AVAILABLE, MUNICIPAL_GAP),
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
    ap.add_argument("--labels", action="store_true",
                    help="print Cuadro 2's areas in order, with the level each is read as")
    ap.add_argument("--in-2010", dest="in_2010",
                    help="comma-separated names to find among the 2010 census's areas of every "
                         "level in the US Census Bureau's workbook, with their parents")
    args = ap.parse_args()
    if args.in_2010:
        import openpyxl
        from . import uscb
        wanted = {fold(n) for n in args.in_2010.split(",")}
        url = uscb.workbook_url(uscb_age_sex.COUNTRIES[0].dataset)
        book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                      read_only=True, data_only=True)
        for sheet in ("Population", "Age-Sex"):
            try:
                rows = uscb.sheet_rows(book, sheet)
            except SystemExit:
                continue
            names, _ = uscb.columns(rows)
            at = {n: i for i, n in enumerate(names) if n}
            for row in rows[2:]:
                cells = {k: row[i] for k, i in at.items()
                         if k.startswith("ADM") or k in ("GEO_MATCH", "NSO_NAME", "BTOTL",
                                                          "POP_BTOTL")}
                if any(fold(str(v or "")) in wanted for k, v in cells.items()
                       if k.endswith("_NAME") or k == "NSO_NAME"):
                    print(f"  {sheet}: {cells}")
        return 0
    if args.labels:
        rows, named = workbook_rows(*AGES)
        print(f"  the index names {len(named)} provinces: {sorted(named)}")
        for area in classify(areas(rows, 10), named):
            print(f"  {area['kind']:9} {area['values'][0]:>9} {area['label']!r}")
        return 0
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
