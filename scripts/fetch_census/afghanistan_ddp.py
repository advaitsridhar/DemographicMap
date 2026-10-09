#!/usr/bin/env python3
"""Afghanistan -- district ethnic shares from the district development plans themselves.

Afghanistan has had no census since the abandoned count of 1979, and no
official tabulation of ethnicity exists. What does exist, district by district,
is the *district development plan*: from 2006 the Ministry of Rural
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
them (``plan_shares``): "Pashtun 70%" and "70% Pashtun" alike, under the
articles' group names (``afghanistan.GROUPS``) and the plans' own spellings
("Uzbak", "Pashtoon", "Brahawi"), refused below 55% or above 101.5% in all
(``afghanistan.usable``). A share the plan gives several groups together --
"10% Turkmen and Hazara", "1% Hazara, Tajik, Arab", "Mughol, Baloch 10%" -- is
neither split nor handed to one of them: it is left out, the composition falls
short by it, and the note quotes the plan's whole line. A name this map does
not know ("Palo", "Habash") is left out the same way. A plan that names groups
without shares is logged and not written: turning "majority" into a number
would be inventing it. These are the provincial authorities' figures as a
planning summary prints them, not a count, and the note says so.

**Which polygon.** A plan's province is read off its cover and mapped to the
office's province code; its district is then looked for only among the drawn
districts the office counts in that province (``afghanistan_estimates``'s
crosswalk), under the drawn name, the office's own spelling in its 1396
estimates, the provinces' articles' spelling (``afghanistan.DISTRICT_ON_MAP``)
or a spelling declared here (``SPELLINGS``) -- exactly one, or nothing. "Farah
Center" is the district of the provincial centre. Two plans for one district
(an assembly re-elected and its plan redrawn) leave the later one, and say if
the earlier differed.

**Between runs.** The archive answers the runner slowly and, in bursts, not at
all: one run had "Connection refused" for 50 of 150 plans. What each plan says
-- its cover's lines and its ethnic line, not the PDF -- is kept in
``afghanistan_ddp_plans.json`` beside the output, so a run asks only for the
plans no run has read yet, and every run's records are built from all of them.
That file is the reader's memory, not one the build reads.

Usage:
    python -m scripts.fetch_census.afghanistan_ddp --probe
    python -m scripts.fetch_census.afghanistan_ddp
"""

from __future__ import annotations

import argparse
import io
import re
import time
import urllib.parse
from typing import Any

from ._shared import PROCESSED, http_get, http_json, log, read_json, record, write_json
from .afghanistan import AFTER, BEFORE, DISTRICT_ON_MAP, GROUPS, PROVINCE_ON_MAP, usable
from .south_asia_common import fold, load_units

OUT = "afghanistan_ddp.json"
READINGS = "afghanistan_ddp_plans.json"
CDX = "https://web.archive.org/cdx/search/cdx"
PATTERN = "www.mrrd-nabdp.org/attachments/article/*"
SOURCE = ("Ministry of Rural Rehabilitation and Development, National Area-Based "
          "Development Programme, summary of the district development plan")
LICENCE = "Ministry of Rural Rehabilitation and Development publication"
# The covers date the plans 2006-2011; a cover that prints no year gets the range.
YEARS = "2006-2014"
# Seconds each worker waits after a request: the archive refuses bursts.
PAUSE = 2.0

# Province names as the plans' covers may spell them, against the office's
# province codes; the drawn and the articles' spellings are added at run time.
PROVINCE_SPELLINGS = {
    "bamiyan": "10", "bamian": "10", "daikundi": "24", "daykundy": "24", "daikudi": "24",
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
# from a probe run's leftovers and kept only where exactly one drawn district
# of that province is plainly the same place. Bost is Lashkar Gah's older
# name, Kushk-i Robat Sangi the full name of Kushk. Not here, and so unbound:
# Marja (counted inside Nad Ali, not drawn apart), Shotul (not drawn apart in
# Panjshir), Mianshin (not drawn in Kandahar), "Dardad" (Darqad, or a misprint
# of it -- not sure), Nasai, and Gizab, whose cover names no province.
SPELLINGS: dict[tuple[str, str], str] = {
    ("30", "BOST"): "Lashkar Gah", ("30", "NAWA"): "Nawa-I- Barak Zayi",
    ("30", "NAHRI SERAJ"): "Nahri Sarraj", ("30", "DISHO"): "Dishu",
    ("30", "KHANISHIN"): "Reg(Khanshin)",
    ("32", "KUSHK ROBAT SANGI"): "Koshk", ("32", "OBEH"): "Obe",
    ("34", "CHARBORJAK"): "Chahar Burjak", ("34", "CHAKHANSOR"): "Chakhansur",
    ("27", "NISH"): "Nesh",
    ("18", "ROSTAQ"): "Rustaq", ("18", "ESHKAMISH"): "Ishkamish",
    ("18", "KHWAJA GHAAR"): "Khwaja Ghar", ("18", "KHOWAJA BAHAUDDIN"): "Khwaja Bahawuddin",
    ("18", "CHALL"): "Chal", ("18", "Cha Ab"): "Chah Ab", ("18", "Hazar Somoch"): "Hazar Sumuch",
    ("33", "Lash Wa Jowani"): "Lash Wa Juwayn", ("33", "KHAKI SAFID"): "Khaki Safed",
    ("20", "AIBAK"): "Aybak", ("20", "RUYE DU AAB"): "Ruyi Du Ab",
    ("20", "Khuram Sarbagh"): "Khuram Wa Sarbagh", ("20", "Dari Suf Payan"): "Dara-I-Sufi Payin",
    ("17", "ISHKASHIM"): "Ishkashiem", ("17", "Faiz Abad"): "Fayzabad",
    ("17", "SHEGHNAN"): "Shighnan", ("17", "KHOWAHAN"): "Khwahan",
    ("17", "KERAN WA MENJAN"): "Kuran Wa Munjan",
    ("29", "KHAN CHARBAGH"): "Khani Chahar Bagh", ("29", "SHERIN TAGAB"): "Shirin Tagab",
    ("29", "ANDKHUY"): "Andkhoy", ("29", "KHAJA SABZPOSH WALI"): "Khwaja Sabz Posh",
    ("24", "SANG TAKHT"): "Sangi Takht", ("24", "KIJRAN"): "Kajran",
    ("24", "ASHTARLI"): "Ishtarlay",
    ("21", "CHEMTAL"): "Chimtal",
    # From the first full run's leftovers.
    ("33", "ANAR DARAH"): "Anar Dara", ("33", "SHEB KOH"): "Shib Koh",
    ("17", "YAFTAL SOFLA"): "Yaftal Sufla", ("17", "WARDOJ"): "Warduj",
    ("17", "DARAIM"): "Darayim", ("17", "TUSHKAN"): "Tashkan",
    ("17", "SHAHR-E-BOZORG"): "Shahri Buzurg",
    ("18", "DASHT-E-QALA"): "Dashti Qala",
    ("20", "DARI SUF BALA"): "Dara-I-Sufi Bala", ("20", "HAZRAT SULTAN"): "Hazrati Sultan",
    ("29", "PASHTOON KOT"): "Pashtun Kot",
    ("30", "MOSA QALA"): "Musa Qala", ("27", "KHAKRIZ"): "Khakrez",
    ("32", "KUSK-E-KOHNA"): "Koshki Kohna", ("22", "GOSFANDY"): "Gosfandi",
    ("08", "PARIYAN"): "Paryan",
}
# A plan whose ethnic line cannot be its own district's, and is not written.
# Sang Takht's (Daykundi, 2007) reads "50% Pashton, 30% Uzbak, 15% Arab, 1%
# Tajik, 2% Turkman, 2% Hazara": Uzbek, Arab and Turkmen majorities in a
# district of the Hazarajat whose neighbours' plans (Nili, Miramor,
# Ishtarlay) each say 100% Hazara -- a northern district's line carried into
# its summary. (province code, plan's spelling) -> why.
NOT_ITS_OWN: dict[tuple[str, str], str] = {
    ("24", "SANG TAKHT"): "an ethnic line with Uzbek, Arab and Turkmen shares in the "
                          "Hazarajat, where its neighbours' plans say 100% Hazara",
}
# The plans' own spellings of the groups, on top of the articles'. Each was
# read in a probe run's plans; none is invented.
PLAN_GROUPS = {**GROUPS, "uzbak": "Uzbek", "uzbaks": "Uzbek", "pashtoon": "Pashtun",
               "turkeman": "Turkmen", "torkman": "Turkmen", "brahawi": "Brahui",
               "other ethnicity": "Other", "other ethnicities": "Other",
               "other ethnic groups": "Other"}

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
# A line is carried on to the next only when the list plainly runs on: it
# stops on a connector ("10% Turkmen and" / "Hazara"), the next line starts
# with one or with a share ("Brahawi 10 %" / "and Tajik 1 %", "Palo 20%,
# Brahawi" / "15%, Tajik 10%"), or a list that puts its shares first stops on
# a share ("35%Tajik, 5%" / "Pashton, 5% other ethnicities"). Read any further,
# the first probe took in page numbers ("100% Pashtun 2"), headings
# ("Situation Analysis, Development Goals") and the profile's next row
# ("Needy groups", "Kochi population in winter").
CONNECTOR = re.compile(r"(?i)(?:[,;&]|\band|\bor|-)\s*$")
RUNS_ON = re.compile(r"(?i)^(?:[,;&]|and\b|or\b|\d{1,3}(?:\.\d+)?\s*%)")
SHARE_LAST = re.compile(r"\d\s*%\s*$")
SHARE_FIRST = re.compile(r"^\s*\d")
YEAR = re.compile(r"\b(20(?:0[5-9]|1[0-6]))\b")
CENTRE = re.compile(r"(?i)\b(?:center|centre|central|markaz)\b")
CENTRE_NOT_NAMESAKE = {"21"}
# The plans' file names as the archive holds them: "Chemtal DDP English
# Summary.pdf", "Summary of the DDP in English-Bakwa.pdf", "Dawlat Abad Full
# DDP.pdf", but also "Khost_Tani_Summary_Finalized.pdf", "Kabul_Guldara English
# summary finalized.pdf", "Gizab District Summary.pdf" and "Chardara
# Summery.pdf", which do not say "DDP" at all.
PLAN_FILE = re.compile(r"(?i)ddp|summ[ae]ry")
FULL_PLAN = re.compile(r"(?i)\bfull\b")
# What a share after a name may not have in front of it, and a share before a
# name may not have after it: another name with no share of its own -- the
# share is then theirs together.
NAME_AFTER = re.compile(r"^\s*(?:,|&|\band\b)\s*[A-Za-z][A-Za-z\- ]*?\s*(?:$|[,;&]|\band\b)")


# ---------------------------------------------------------------------------
# The archive's captures and one plan's text
# ---------------------------------------------------------------------------

def captures(attempts: int = 6, wait: float = 30.0) -> list[tuple[str, str]]:
    """(timestamp, original URL) of every archived plan PDF, one per URL.

    The archive's index answers 503 ("Temporarily Offline") for minutes at a
    time; the query is the same either way, so it is simply asked again, as a
    wildcard and then as a prefix, before the run gives up.
    """
    base = [("output", "json"), ("fl", "timestamp,original,statuscode,mimetype,length"),
            ("filter", "statuscode:200"), ("filter", "mimetype:application/pdf"),
            ("collapse", "urlkey"), ("limit", "100000")]
    shapes = [[("url", PATTERN)],
              [("url", PATTERN.rstrip("*")), ("matchType", "prefix")]]
    last: Exception | None = None
    for attempt in range(attempts):
        for shape in shapes:
            try:
                rows = http_json(CDX + "?" + urllib.parse.urlencode(shape + base),
                                 cache=False, retries=1)
            except Exception as err:                # noqa: BLE001 -- retried below
                last = err
                continue
            return prefer_summaries(sorted(
                (r[0], r[1]) for r in rows[1:]
                if PLAN_FILE.search(urllib.parse.unquote(r[1].rsplit("/", 1)[-1]))))
        log(f"  the archive's index did not answer ({last}); asking again in {wait:.0f}s")
        time.sleep(wait)
    raise SystemExit(f"afghanistan_ddp: the archive's index never answered: {last}")


def capture_url(stamp: str, original: str) -> str:
    return f"https://web.archive.org/web/{stamp}id_/{original}"


def still_to_read(found: list[tuple[str, str]], readings: dict[str, dict[str, Any]]
                  ) -> list[tuple[str, str]]:
    """The captures no earlier run has an answer for (a failed PDF is an answer)."""
    return [item for item in found if capture_url(*item) not in readings]


def prefer_summaries(found: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop a full plan where its folder also holds that district's summary.

    The summary is what is read, and the full plan (a document several times
    its size) repeats the same profile; it is kept only for a district whose
    summary the archive does not hold.
    """
    by_key: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for item in found:
        by_key.setdefault((article_of(item[1]), fold(file_label(item[1]))), []).append(item)
    out = []
    for items in by_key.values():
        summaries = [i for i in items
                     if not FULL_PLAN.search(urllib.parse.unquote(i[1].rsplit("/", 1)[-1]))]
        out.extend(summaries or items)
    return sorted(out)


def file_label(url: str) -> str:
    """The plan's district as its file name gives it, a fallback for the cover.

    "Chemtal DDP English Summary" -> "Chemtal"; "Summary of the DDP in
    English-Bakwa" -> "Bakwa"; "Khost_Tani_Summary_Finalized" -> "Khost Tani"
    (a province in front is left for the binding to recognise).
    """
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    name = re.sub(r"(?i)\.pdf$", "", name).replace("_", " ").replace("+", " ")
    name = re.sub(r"(?i)summary of the ddp in english[- ]*", "", name)
    name = re.sub(r"(?i)\b(?:(?:full|district)\s+)?(?:ddp|summ[ae]ry|english)\b.*$", "", name)
    return " ".join(name.split()).strip(" -")


def article_of(url: str) -> str:
    found = re.search(r"/attachments/article/(\d+)/", url)
    return found.group(1) if found else ""


def page_texts(blob: bytes, pages: int = 4) -> list[str]:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages[:pages]]


def excerpt(texts: list[str]) -> dict[str, list[str]]:
    """What reading a plan needs of its pages: the cover's lines and the ethnic line's.

    This, not the PDF, is what is kept between runs (``READINGS``).
    """
    cover = [" ".join(line.split()) for line in (texts[0] if texts else "").splitlines()]
    lines = [" ".join(line.split()) for text in texts for line in text.splitlines()]
    at = next((i for i, line in enumerate(lines) if ETHNIC.search(line)), None)
    return {"cover": [line for line in cover if line][:60],
            "lines": lines[at:at + 5] if at is not None else []}


def plan_of(ex: dict[str, list[str]], url: str) -> dict[str, Any]:
    """What one plan says: its district, province, year and ethnic line."""
    district = province = None
    for line in ex.get("cover", []):
        if district is None and (m := COVER_DISTRICT.match(line)):
            if not re.search(r"(?i)summary|development|plan|assembly", m.group(1)):
                district = m.group(1)
        if province is None and (m := COVER_PROVINCE.match(line)):
            province = m.group(1)
    years = [int(y) for line in ex.get("cover", []) for y in YEAR.findall(line)]
    ethnic = ""
    lines = ex.get("lines") or []
    if lines:
        found = ETHNIC.search(lines[0])
        rest = lines[0][found.end():].strip() if found else ""
        follow = lines[1:]
        # The label alone on its line, the answer on the next.
        if not rest and follow and follow[0] and not NEXT_FIELD.match(follow[0]):
            rest, follow = follow[0], follow[1:]
        for line in follow:
            if not line or NEXT_FIELD.match(line) or line.isdigit() or len(line) > 60:
                break
            if not (CONNECTOR.search(rest) or RUNS_ON.match(line)
                    or (SHARE_FIRST.match(rest) and SHARE_LAST.search(rest))):
                break
            rest += " " + line
        ethnic = rest.strip()
    return {"district": district or file_label(url), "district_from": "cover" if district
            else "file name", "province": province, "year": max(years) if years else None,
            "ethnic": ethnic, "url": url}


def read_plan(texts: list[str], url: str) -> dict[str, Any]:
    return plan_of(excerpt(texts), url)


def read_one(stamp: str, original: str, started: float, budget: float
             ) -> tuple[str, list[str] | None, str]:
    """One archived plan's first pages, or None and why."""
    url = capture_url(stamp, original)
    if time.monotonic() - started > budget:
        return url, None, "not read: the run's time ran out"
    try:
        blob = http_get(url, binary=True, retries=1, timeout=90)
    except Exception as err:                        # noqa: BLE001 -- reported
        return url, None, f"{type(err).__name__} {str(err)[:80]}"
    finally:
        time.sleep(PAUSE)
    if blob[:4] != b"%PDF":
        return url, None, "not a PDF"
    try:
        return url, page_texts(blob), ""
    except Exception as err:                        # noqa: BLE001 -- reported
        return url, None, f"unreadable PDF ({type(err).__name__})"


def read_plans(found: list[tuple[str, str]], workers: int = 2, minutes: float = 33.0
               ) -> tuple[dict[str, dict[str, Any]], int]:
    """What every plan says that could be fetched, within the runner's time.

    One plan after another took longer than the runner's 45 minutes, and
    three at once drew "Connection refused" for a third of them; two at once,
    each pausing between requests, is the compromise. A capture that is not a
    readable PDF is remembered as such (it will not become one); one the
    archive did not answer is not, and the next run asks for it again.
    Returns {capture URL: excerpt, or {"failed": why}} and how many were not
    reached for want of time.
    """
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
    started = time.monotonic()
    out: dict[str, dict[str, Any]] = {}
    unread = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = pool.map(lambda item: read_one(*item, started, minutes * 60), found)
        for n, (url, texts, why) in enumerate(jobs, 1):
            if texts is not None:
                out[url] = excerpt(texts)
            else:
                log(f"  !! {url}: {why}")
                if why.startswith("not read"):
                    unread += 1
                elif why == "not a PDF" or why.startswith(("unreadable PDF", "HTTPError")):
                    out[url] = {"failed": why}
            if n % 25 == 0:
                log(f"  {n}/{len(found)} plans asked for, {(time.monotonic() - started) / 60:.1f} min")
    return out, unread


# ---------------------------------------------------------------------------
# The shares
# ---------------------------------------------------------------------------

def group_of(name: str) -> str | None:
    return PLAN_GROUPS.get(" ".join(name.lower().split()).strip(" -"))


def bare_name_before(head: str) -> bool:
    """Whether a name with no share of its own stands just before, a comma apart."""
    head = head.rstrip()
    if not head.endswith(","):
        return False
    last = re.split(r"[,;&]|\band\b", head[:-1])[-1]
    return bool(re.search(r"[A-Za-z]", last)) and not re.search(r"[\d%]", last)


def plan_shares(text: str) -> list[dict[str, Any]]:
    """The groups a plan's ethnic line gives a share of their own, in its order."""
    # "Pashtun 34 % and Tajik 22%", "95% Pashtun and 5% Tajik": the "and"
    # joins two shares, not two groups.
    text = re.sub(r"%\s*(?:and|&)\s+", "%, ", text)
    text = re.sub(r"(\d\s*%\s*[A-Za-z][A-Za-z\- ]*?)\s+(?:and|&)\s+(?=\d)", r"\1, ", text)
    # "..., Pashtun, 5%" closing the list: the share is that name's.
    text = re.sub(r"([A-Za-z])\s*,\s*(\d{1,3}(?:\.\d+)?\s*%)\s*(?=$|[,;])", r"\1 \2", text)
    found: dict[str, float] = {}
    for pattern, gi, pi in ((AFTER, 1, 2), (BEFORE, 2, 1)):
        for m in pattern.finditer(text):
            name = group_of(m.group(gi))
            if not name:
                continue
            if pattern is AFTER and bare_name_before(text[:m.start()]):
                continue
            if pattern is BEFORE and NAME_AFTER.match(text[m.end():]):
                continue
            found.setdefault(name, float(m.group(pi)))
    return [{"group": g, "pct": p} for g, p in found.items()]


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
    labels = [plan["district"]]
    if plan["district_from"] == "file name":
        # "Khost Tani", "Samangan Aibak": a file name that leads with its
        # province -- and "Bamyan Centre", which names the province's centre
        # district after it, so the whole name is tried as well.
        words = labels[0].split()
        for cut in (1, 2):
            head = fold(" ".join(words[:cut]))
            if len(words) > cut and head in codes:
                code = code or codes[head]
                labels.append(" ".join(words[cut:]))
                break
    if code is None:
        code = article_province.get(article_of(plan["url"]))
        if code is None:
            return None, f"no province read from its cover ({plan['province']!r})"
    declared = {fold(k[1]): v for k, v in SPELLINGS.items() if k[0] == code}
    wanted = set()
    for label in labels:
        wanted.add(fold(label))
        # "Balkh Center" would be Mazar-i-Sharif's district, not Balkh's: the
        # one province whose namesake district is not its centre.
        if code not in CENTRE_NOT_NAMESAKE:
            wanted.add(fold(CENTRE.sub(" ", label)))
        if fold(label) in declared:
            wanted.add(fold(declared[fold(label)]))
    wanted.discard("")
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
            f"Shares the plan gives several groups together, and names this map "
            f"does not know, are left out rather than divided. The profile is the "
            f"provincial authorities' secondary information, reviewed by the "
            f"district's development assembly: a planning estimate, not a count. "
            f"Afghanistan has had no census since 1979, and no office tabulates "
            f"ethnicity.")


def build(plans: list[dict[str, Any]], units1: list[dict[str, Any]],
          units2: list[dict[str, Any]], office: dict[str, str] | None = None,
          probe: bool = False) -> list[dict[str, Any]]:
    codes = province_codes(units1)
    districts = district_names(units1, units2, office)
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
        parts = plan_shares(plan["ethnic"]) if plan["ethnic"] else []
        state = ("shares" if parts and usable(parts, f"{plan['district']} ({plan['url']})")
                 else ("refused" if parts else "names only"))
        code = codes.get(fold(plan["province"])) if plan["province"] else None
        doubt = {(k[0], fold(k[1])): v for k, v in NOT_ITS_OWN.items()}.get(
            (code, fold(plan["district"])))
        if doubt and state == "shares":
            log(f"    {plan['district']}: not written -- {doubt}")
            state = "refused"
        if probe or unit is None:
            log(f"  {plan['province'] or '?':<12} {plan['district']:<22} "
                f"[{plan['district_from']}] {plan['year'] or '?'}  "
                f"{(unit or {}).get('name', 'UNBOUND: ' + why):<28} {state:<10} "
                f"{plan['ethnic'][:90]!r}"
                + (f" -> {[(p['group'], p['pct']) for p in parts]}" if parts else ""))
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
    readings: dict[str, dict[str, Any]] = read_json(PROCESSED / READINGS, {}) or {}
    wanted = {capture_url(*item): item for item in found}
    todo = still_to_read(found, readings)
    log(f"  {len(wanted) - len(todo)} read by an earlier run; asking the archive for {len(todo)}")
    fresh, unread = read_plans(todo)
    readings.update(fresh)
    missing = [url for url in wanted if url not in readings]
    failed = [url for url in wanted if "failed" in readings.get(url, {})]
    log(f"  {len(fresh)} answered now; {len(failed)} not a readable PDF; {len(missing)} "
        f"not answered yet ({unread} for want of time) -- a later run asks for those again")
    plans = [plan_of(readings[url], url) for url in sorted(wanted)
             if url in readings and "failed" not in readings[url]]
    units1, units2 = load_units("AFG", "admin1"), load_units("AFG", "admin2")
    records = build(plans, units1, units2, office_names(), probe=args.probe)
    compare(records, units1, units2)
    if args.probe:
        log("--probe: nothing written")
        return 0
    write_json(PROCESSED / READINGS, {url: readings[url] for url in sorted(readings)})
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
