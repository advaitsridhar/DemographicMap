#!/usr/bin/env python3
"""Afghanistan -- district ethnic shares from the district development plans themselves.

Afghanistan has had no census since the abandoned count of 1979, and no
official tabulation of ethnicity exists. What does exist, district by district,
is the *district development plan*: between 2008 and 2014 the Ministry of Rural
Rehabilitation and Development's National Area-Based Development Programme
(NABDP, with UNDP) had each district's development assembly draw one up, and
published an English summary of each on www.mrrd-nabdp.org. The summary opens
with a district profile -- "secondary information about the district from the
provincial authorities", reviewed by the assembly -- and one of its lines is
"Ethnic diversity": sometimes shares ("90% Pashtun, 10% Turkmen and Hazara"),
sometimes only names.

``afghanistan.py`` reads those shares as the provinces' English Wikipedia
articles transcribe them. This reads the plans: the ministry's site is gone,
and the Internet Archive holds its PDFs (``captures``). Each plan's cover names
its district and province, and its profile table the ethnic line, so a plan
says where it belongs without help from its file name.

**What is written, and only that.** A district whose plan states shares gets
them, read with the same rules as ``afghanistan.shares``/``usable`` (both
orders, "Pashtun 70%" and "70% Pashtun"; refused below 55% or above 101.5% in
all). A share the plan gives two groups together ("10% Turkmen and Hazara") is
not split -- it is left out of the composition, which then falls short by it,
and the note quotes the plan's whole line. A plan that names groups without
shares is logged and not written: turning "majority" into a number would be
inventing it. These are the provincial authorities' figures as a planning
summary prints them, not a count, and the note says so.

**Which polygon.** A plan's province is read off its cover and mapped to the
office's province code; its district is then looked for only among the drawn
districts the office counts in that province (``afghanistan_estimates``'s
crosswalk), under the drawn name, the office's own spelling in its 1396
estimates, the provinces' articles' spelling (``afghanistan.DISTRICT_ON_MAP``)
or a spelling declared here (``SPELLINGS``) -- exactly one, or nothing. Two
plans for one district (an assembly re-elected and its plan redrawn) leave the
later one, and say if the earlier differed.

Usage:
    python -m scripts.fetch_census.afghanistan_ddp --probe
    python -m scripts.fetch_census.afghanistan_ddp
"""

from __future__ import annotations

import argparse
import io
import re
import urllib.parse
from typing import Any

from ._shared import PROCESSED, http_get, http_json, log, read_json, record, write_json
from .afghanistan import DISTRICT_ON_MAP, PROVINCE_ON_MAP, shares, usable
from .south_asia_common import fold, load_units

OUT = "afghanistan_ddp.json"
CDX = "https://web.archive.org/cdx/search/cdx"
PATTERN = "www.mrrd-nabdp.org/attachments/article/*"
SOURCE = ("Ministry of Rural Rehabilitation and Development, National Area-Based "
          "Development Programme, summary of the district development plan")
LICENCE = "Ministry of Rural Rehabilitation and Development publication"
YEARS = "2008-2014"

# Province names as the plans' covers may spell them, against the office's
# province codes; the drawn and the articles' spellings are added at run time.
PROVINCE_SPELLINGS = {
    "bamiyan": "10", "bamian": "10", "daikundi": "24", "daykundy": "24",
    "jawzjan": "28", "jowzjan": "28", "juzjan": "28", "sarepul": "22", "saripul": "22",
    "sarepol": "22", "saripol": "22", "sarialpul": "22", "nimroz": "34", "nimruz": "34",
    "uruzgan": "25", "oruzgan": "25", "urozgan": "25", "paktya": "13", "paktia": "13",
    "hilmand": "30", "helmand": "30", "kunarha": "15", "kunar": "15", "maidanwardak": "04",
    "wardak": "04", "maidan": "04", "ghazni": "11", "ghanzi": "11", "khowst": "14",
    "khost": "14", "laghman": "07", "nangarhar": "06", "nangrahar": "06", "nooristan": "16",
    "nuristan": "16", "panjsher": "08", "panjshir": "08", "panjsheer": "08",
    "kapisa": "02", "kapisaa": "02", "logar": "05", "kabul": "01", "parwan": "03",
    "herat": "32", "hirat": "32", "badghis": "31", "badghes": "31", "farah": "33",
    "faryab": "29", "fariab": "29", "balkh": "21", "samangan": "20", "kunduz": "19",
    "konduz": "19", "takhar": "18", "badakhshan": "17", "baghlan": "09", "ghor": "23",
    "ghowr": "23", "kandahar": "27", "zabul": "26", "zabol": "26", "paktika": "12",
}
# A plan's district spelling that matches no drawn, office or article name in
# its province: (province code, plan's spelling) -> drawn name. Each was taken
# from a probe run's leftovers and kept only where one drawn district of that
# province is plainly the same place.
SPELLINGS: dict[tuple[str, str], str] = {}

COVER_DISTRICT = re.compile(r"^\s*(?:the\s+)?([A-Za-z][A-Za-z'’.\- ]{1,40}?)\s+DISTRICT\s*$", re.I)
COVER_PROVINCE = re.compile(r"^\s*([A-Za-z][A-Za-z'’.\- ]{1,30}?)\s+PROVINCE\s*$", re.I)
# "Ethnic diversity", "Ethnic groups", "Ethnicity" -- and "Ethic Diversity",
# as some plans misspell it, which is read only with the word after it.
ETHNIC = re.compile(r"(?i)\b(?:ethnic(?:ity|al)?(?:\s*(?:diversity|groups?|composition|"
                    r"structure|make[- ]?up))?|ethic\s*(?:diversity|groups?|composition))\b[:\s]*")
# A profile line that is not the ethnic one: where a wrapped ethnic line ends.
NEXT_FIELD = re.compile(r"(?i)^(?:sectoral|number|no\.|average|population|area|literacy|"
                        r"percentage|access|education|health|infrastructure|main|total|"
                        r"language|religion|agricultur|economic|general|livelihood|\d+\.)")
YEAR = re.compile(r"\b(20(?:0[5-9]|1[0-6]))\b")


# ---------------------------------------------------------------------------
# The archive's captures and one plan's text
# ---------------------------------------------------------------------------

def captures() -> list[tuple[str, str]]:
    """(timestamp, original URL) of every archived plan PDF, one per URL."""
    query = [("url", PATTERN), ("output", "json"),
             ("fl", "timestamp,original,statuscode,mimetype,length"),
             ("filter", "statuscode:200"), ("filter", "mimetype:application/pdf"),
             ("collapse", "urlkey"), ("limit", "100000")]
    rows = http_json(CDX + "?" + urllib.parse.urlencode(query))
    return sorted((r[0], r[1]) for r in rows[1:] if re.search(r"(?i)ddp", r[1]))


def file_label(url: str) -> str:
    """The plan's district as its file name gives it, a fallback for the cover."""
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    name = re.sub(r"(?i)\.pdf$", "", name)
    name = re.sub(r"(?i)summary of the ddp in english[- ]*", "", name)
    name = re.sub(r"(?i)\b(?:full\s+)?ddp\b.*$", "", name)
    return " ".join(name.replace("_", " ").replace("+", " ").split())


def article_of(url: str) -> str:
    found = re.search(r"/attachments/article/(\d+)/", url)
    return found.group(1) if found else ""


def page_texts(blob: bytes, pages: int = 4) -> list[str]:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages[:pages]]


def read_plan(texts: list[str], url: str) -> dict[str, Any]:
    """What one plan says: its district, province, year and ethnic line."""
    cover = [" ".join(line.split()) for line in (texts[0] if texts else "").splitlines()]
    district = province = None
    for line in cover:
        if district is None and (m := COVER_DISTRICT.match(line)):
            if not re.search(r"(?i)summary|development|plan|assembly", m.group(1)):
                district = m.group(1)
        if province is None and (m := COVER_PROVINCE.match(line)):
            province = m.group(1)
    years = [int(y) for line in cover for y in YEAR.findall(line)]
    ethnic = ""
    lines = [" ".join(line.split()) for text in texts for line in text.splitlines()]
    for i, line in enumerate(lines):
        found = ETHNIC.search(line)
        if not found:
            continue
        rest = line[found.end():].strip()
        for follow in lines[i + 1:i + 4]:
            if not follow or NEXT_FIELD.match(follow) or len(follow) > 60:
                break
            rest += " " + follow
        ethnic = rest.strip()
        break
    return {"district": district or file_label(url), "district_from": "cover" if district
            else "file name", "province": province, "year": max(years) if years else None,
            "ethnic": ethnic, "url": url}


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def province_codes(units1: list[dict[str, Any]]) -> dict[str, str]:
    """Folded province name -> office province code, every spelling known."""
    from .afghanistan_estimates import province_units   # noqa: PLC0415
    out = dict(PROVINCE_SPELLINGS)
    for code, unit in province_units(units1).items():
        out[fold(unit["name"])] = code
        out[fold(unit.get("site_name"))] = code
    for article, drawn in PROVINCE_ON_MAP.items():
        code = out.get(fold(drawn))
        if code:
            out[fold(article)] = code
    out.pop("", None)
    return out


def district_names(units1: list[dict[str, Any]], units2: list[dict[str, Any]],
                   office: dict[str, str] | None = None
                   ) -> dict[str, list[tuple[dict[str, Any], set[str]]]]:
    """Office province code -> its drawn districts, each with every name it answers to."""
    from .afghanistan_estimates import drawn_districts   # noqa: PLC0415
    office = office or {}
    by_drawn: dict[tuple[str, str], list[str]] = {}
    for (province, article_name), drawn in DISTRICT_ON_MAP.items():
        by_drawn.setdefault((PROVINCE_ON_MAP.get(province, province), drawn), []).append(article_name)
    out: dict[str, list[tuple[dict[str, Any], set[str]]]] = {}
    for unit, province, key in drawn_districts(units1, units2):
        names = {fold(unit["name"]), fold(unit.get("site_name"))}
        names.add(fold(office.get(key)))
        names.update(fold(n) for n in by_drawn.get((province, unit["name"]), ()))
        names.discard("")
        out.setdefault(key[:2], []).append((unit, names))
    return out


def bind_plan(plan: dict[str, Any], codes: dict[str, str],
              districts: dict[str, list[tuple[dict[str, Any], set[str]]]],
              article_province: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    """The one drawn district a plan is for, or None and why."""
    code = codes.get(fold(plan["province"])) if plan["province"] else None
    if code is None:
        code = article_province.get(article_of(plan["url"]))
        if code is None:
            return None, f"no province read from its cover ({plan['province']!r})"
    wanted = {fold(plan["district"])}
    declared = SPELLINGS.get((code, plan["district"]))
    if declared:
        wanted.add(fold(declared))
    # "Provincial Center", "Markaz" and the like name the centre district.
    hits = [unit for unit, names in districts.get(code, []) if names & wanted]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return None, f"no drawn district of province {code} answers to {plan['district']!r}"
    return None, (f"{len(hits)} drawn districts of province {code} answer to "
                  f"{plan['district']!r}")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def note(plan: dict[str, Any], province: str) -> str:
    when = f" of {plan['year']}" if plan["year"] else ""
    return (f"The district development plan{when} for {plan['district'].title()} "
            f"district, {province} province -- the Ministry of Rural Rehabilitation "
            f"and Development's National Area-Based Development Programme -- whose "
            f"district profile gives the ethnic diversity as \"{plan['ethnic']}\". "
            f"The profile is the provincial authorities' secondary information, "
            f"reviewed by the district's development assembly: a planning estimate, "
            f"not a count. Afghanistan has had no census since 1979, and no office "
            f"tabulates ethnicity.")


def build(plans: list[dict[str, Any]], units1: list[dict[str, Any]],
          units2: list[dict[str, Any]], office: dict[str, str] | None = None,
          probe: bool = False) -> list[dict[str, Any]]:
    from .afghanistan_estimates import province_units   # noqa: PLC0415
    codes = province_codes(units1)
    districts = district_names(units1, units2, office)
    provinces = province_units(units1)
    # An article folder holds one province's plans: where a cover names no
    # province, the folder's other plans do.
    votes: dict[str, dict[str, int]] = {}
    for plan in plans:
        code = codes.get(fold(plan["province"])) if plan["province"] else None
        if code:
            tally = votes.setdefault(article_of(plan["url"]), {})
            tally[code] = tally.get(code, 0) + 1
    article_province = {a: max(t, key=t.get) for a, t in votes.items()
                        if len(t) == 1 or sorted(t.values())[-1] > 2 * sorted(t.values())[-2]}

    chosen: dict[str, tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = {}
    tally = {"plans": len(plans), "bound": 0, "shares": 0, "names only": 0, "refused": 0}
    for plan in plans:
        unit, why = bind_plan(plan, codes, districts, article_province)
        parts = shares(plan["ethnic"]) if plan["ethnic"] else []
        state = ("shares" if parts and usable(parts, f"{plan['district']} ({plan['url']})")
                 else ("refused" if parts else "names only"))
        if probe or unit is None:
            log(f"  {plan['province'] or '?':<12} {plan['district']:<22} "
                f"[{plan['district_from']}] {plan['year'] or '?'}  "
                f"{(unit or {}).get('name', 'UNBOUND: ' + why):<28} {state:<10} "
                f"{plan['ethnic'][:90]!r}")
        if unit is None:
            continue
        tally["bound"] += 1
        tally[state] += 1
        if state != "shares":
            continue
        earlier = chosen.get(unit["id"])
        if earlier and (earlier[0]["year"] or 0) > (plan["year"] or 0):
            if earlier[2] != parts:
                log(f"    {unit['name']}: an earlier plan ({plan['year']}) gives {parts}, "
                    f"the later one kept")
            continue
        if earlier and earlier[2] != parts:
            log(f"    {unit['name']}: an earlier plan ({earlier[0]['year']}) gave "
                f"{earlier[2]}, this later one is kept")
        chosen[unit["id"]] = (plan, unit, parts)
    log(f"  {tally['plans']} plans: {tally['bound']} bound to a drawn district; of those "
        f"{tally['shares']} give shares, {tally['names only']} only names, "
        f"{tally['refused']} shares that do not add up; {len(chosen)} districts written")

    province_of = {u["id"]: u for u in units1}
    out = []
    for unit_id, (plan, unit, parts) in sorted(chosen.items(), key=lambda kv: kv[1][1]["name"]):
        province = province_of.get(unit.get("parent"), {}).get("name", "")
        rows = [{"group": p["group"], "pct": p["pct"]} for p in parts]
        out.append(record(
            f"AFG-DDP-{unit_id}", unit["name"], level="admin2", parent="AFG",
            country="AFG", match_by="shape_id", shape_id=unit_id, parent_name=province,
            ethnicity=rows, ethnicity_year=plan["year"] or YEARS,
            ethnicity_basis="district development plan",
            ethnicity_note=note(plan, (plan["province"] or province).title()),
            sources=[{"field": "ethnicity",
                      "name": f"{SOURCE}, {plan['district'].title()} district",
                      "url": plan["url"], "year": plan["year"] or YEARS,
                      "license": LICENCE}]))
    return out


def compare(records: list[dict[str, Any]], units1: list[dict[str, Any]],
            units2: list[dict[str, Any]]) -> None:
    """The plans' shares against the articles' transcription, district by district."""
    wiki = read_json(PROCESSED / "afghanistan_district.json", []) or []
    prov = {u["id"]: u["name"] for u in units1}
    by_name: dict[tuple[str, str], str] = {}
    for unit in units2:
        by_name[(fold(prov.get(unit.get("parent"))), fold(unit["name"]))] = unit["id"]
    transcribed = {}
    for row in wiki:
        uid = by_name.get((fold(row.get("parent_name")), fold(row.get("name"))))
        if uid and isinstance(row.get("ethnicity"), list):
            transcribed[uid] = {g["group"]: g["pct"] for g in row["ethnicity"]}
    same = differ = new = 0
    for rec in records:
        mine = {g["group"]: g["pct"] for g in rec["ethnicity"]}
        theirs = transcribed.get(rec["shape_id"])
        if theirs is None:
            new += 1
        elif theirs == mine:
            same += 1
        else:
            differ += 1
            log(f"    {rec['name']} ({rec['parent_name']}): the plan {mine}, "
                f"the article {theirs}")
    log(f"  against the articles' transcription: {same} districts the same, {differ} "
        f"different, {new} the articles do not carry; "
        f"{len(set(transcribed) - {r['shape_id'] for r in records})} the articles carry "
        f"and no archived plan gives shares for")


def office_names() -> dict[str, str]:
    """1396 district code -> the office's English spelling (afghanistan_estimates' workbook)."""
    from . import afghanistan_estimates as ae          # noqa: PLC0415
    import openpyxl                                     # noqa: PLC0415
    blob = http_get(ae.URL, binary=True)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows_ = [list(r) for r in book[ae.SHEET].iter_rows(values_only=True)]
    summary, blocks = ae.read_sheet(rows_)
    rows = ae.district_rows(ae.provinces_of(summary, blocks))
    return {key: str(row.get("en") or "").strip() for key, row in rows.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="print every plan's reading and binding, and write nothing")
    ap.add_argument("--limit", type=int, default=0, help="read only the first N plans")
    args = ap.parse_args()
    log("afghanistan_ddp: district development plan summaries, as the Internet Archive holds them")
    found = captures()
    log(f"  {len(found)} archived plan PDFs")
    if args.limit:
        found = found[:args.limit]
    plans = []
    for stamp, original in found:
        url = f"https://web.archive.org/web/{stamp}id_/{original}"
        try:
            blob = http_get(url, binary=True)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  !! {url}: {type(err).__name__} {str(err)[:80]}")
            continue
        if blob[:4] != b"%PDF":
            log(f"  !! {url}: not a PDF")
            continue
        try:
            texts = page_texts(blob)
        except Exception as err:                    # noqa: BLE001 -- reported
            log(f"  !! {url}: unreadable PDF ({type(err).__name__})")
            continue
        plans.append(read_plan(texts, url))
    units1, units2 = load_units("AFG", "admin1"), load_units("AFG", "admin2")
    records = build(plans, units1, units2, office_names(), probe=args.probe)
    compare(records, units1, units2)
    if args.probe:
        log("--probe: nothing written")
        return 0
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
