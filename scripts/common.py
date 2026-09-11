"""Shared helpers for the DemographicMap ETL pipeline.

Every fetch_* script writes *one JSON record per entity* with explicit gap
markers, so a missing value is always distinguishable from a value of zero.
See ``docs/SCHEMA.md`` for the full record contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
CURATED = DATA / "curated"
TILES = DATA / "tiles"

USER_AGENT = (
    "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
    "python-urllib"
)

# ---------------------------------------------------------------------------
# Gap semantics.  The editorial rule from the plan: never let "we did not fetch
# it" look like "the country does not collect it".
# ---------------------------------------------------------------------------
NOT_COLLECTED = "not_collected"   # country legally/administratively never gathers it
NOT_AVAILABLE = "not_available"   # exists somewhere, but not in this build
NOT_APPLICABLE = "not_applicable"  # meaningless for this entity (e.g. capital of a county)

GAP_STATUSES = {NOT_COLLECTED, NOT_AVAILABLE, NOT_APPLICABLE}


def gap(status: str, note: str | None = None) -> dict[str, Any]:
    """Build an explicit gap marker instead of a bare ``null``."""
    if status not in GAP_STATUSES:
        raise ValueError(f"unknown gap status {status!r}")
    out: dict[str, Any] = {"status": status}
    if note:
        out["note"] = note
    return out


def is_gap(value: Any) -> bool:
    return value is None or (isinstance(value, dict) and value.get("status") in GAP_STATUSES)


def measure(value: Any, *, year: Any = None, source: str | None = None, unit: str | None = None,
            **extra: Any) -> dict[str, Any] | None:
    """A value carrying its provenance.  Returns ``None`` when value is None."""
    if value is None:
        return None
    out: dict[str, Any] = {"value": value}
    if unit:
        out["unit"] = unit
    if year is not None:
        out["year"] = year
    if source:
        out["source"] = source
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


# ---------------------------------------------------------------------------
# Collection policy: which states do not gather a field AT ALL.
#
# This is the project's central editorial claim, so it lives in one place and is
# asserted only from a citable reason -- never inferred from an empty API
# response. It is keyed by ISO3 and applies to the whole country: if a national
# census does not ask a question, its provinces and districts have no answer to
# it either, so `apply_collection_policy` propagates the marker down every
# level. Before that propagation existed, 8,541 subnational fields in countries
# that demonstrably do not collect them still read "not yet available", which
# told the reader the exact opposite of the truth.
# ---------------------------------------------------------------------------

NOT_COLLECTED_POLICY: dict[str, dict[str, str]] = {
    "FRA": {
        "ethnicity": "France does not collect ethnicity; statistiques ethniques are barred by law (Loi Informatique et Libertes 1978, Conseil constitutionnel 2007).",
        "religion": "France does not collect religion in its census for the same reason.",
    },
    "DEU": {
        "ethnicity": "Germany does not collect ethnicity. The census records citizenship and migration background; religion comes from church-tax registration, not fine-grained self-ID.",
    },
    # Measured against e-Stat's catalogue rather than against the census
    # questionnaire alone -- see docs/SOURCES.md. The catalogue is the reason
    # each of these three is a declaration and not a gap: the API was asked, it
    # answered, and what it holds is not a composition.
    "JPN": {
        "ethnicity": "Japan's census collects nationality, not ethnicity. The eight tables in e-Stat carrying the word for ethnic group are museum holdings and prison nationality counts.",
        "religion": "Japan's census does not ask religion. The one official religion statistic counts adherents as religious bodies report them -- 175.1 million against 123.8 million people, and from 0.5 to 3.2 times a prefecture's population depending on where the corporations are registered.",
        # The third field, added for the same reason as the other two: the
        # Kokusei Chosa asks name, sex, date of birth, marital status,
        # nationality, household relationship, dwelling, employment, industry,
        # occupation and commuting. There is no language question, so the 47
        # prefectures' empty language field was reading as "not fetched yet"
        # when it is "never asked".
        "language": "Japan's census does not ask language; it records nationality instead. The only mother-tongue tables e-Stat holds count schoolchildren who need help with Japanese.",
    },
    "IND": {
        "ethnicity": "India does not collect ethnicity. Scheduled Caste / Scheduled Tribe shares and mother tongue are collected instead.",
    },
    "ESP": {
        "ethnicity": "Spain's census records nationality and birthplace, not ethnicity.",
        "religion": "Spain's census does not ask religion (CIS survey data exists instead).",
    },
    "CHN": {
        "religion": "China's census does not ask religion; it records the 56 official nationalities (minzu) instead.",
    },
    # Ireland asks about language twice and neither answer is a composition.
    # Census 2022 publishes "Speakers of foreign languages" -- a count of only
    # those people, split by which language, with English absent from it
    # entirely -- and "Ability to Speak Irish", which is a skill, not a
    # language spoken. Religion and ethnicity are read from the same census.
    "IRL": {
        "language": "Ireland's census asks which foreign languages a person "
                    "speaks and whether they can speak Irish. Neither is a "
                    "breakdown of the population by language: the first "
                    "excludes English speakers, the second counts an ability.",
    },
    # Measured rather than recalled: MEDAS, TUIK's statistical database, lists
    # 92 subjects and not one of them is religion, ethnicity or mother tongue.
    # The catalogue runs from the address-based population register through
    # births, deaths, marriages, life tables, labour force and prices to
    # theatre and prisons. Turkey's census last asked mother tongue and
    # ethnicity in 1965; what replaced it is an address register, which records
    # where a citizen lives rather than what they are.
    "TUR": {
        "religion": "Turkey does not publish religion. Its statistical database lists 92 subjects and none is religion; population figures come from an address-based register.",
        "ethnicity": "Turkey has not collected ethnicity since the 1965 census; its address-based register records residence and citizenship instead.",
        "language": "Turkey has not collected mother tongue since the 1965 census.",
    },
    # The entries below were written from the survey under survey/findings:
    # each names the census and the fact about its questionnaire the
    # declaration rests on. A wrong "not asked" would hide real data, so a
    # country whose questionnaire the survey could not settle is left alone.
    "NGA": {
        "religion": "Nigeria's census does not ask religion. The National Population Commission stated in 2022 and 2023 that the question was excluded from the 2023 questionnaire for its sensitivity, as it was from 1991 and 2006; the only subnational figures are survey estimates.",
        "ethnicity": "Nigeria's census does not ask ethnicity, excluded from the 2023 questionnaire with religion for the same stated reason; the only subnational figures are survey estimates.",
    },
    "TZA": {
        "religion": "Tanzania's census has not asked religion since 1967; the 2022 census did not, and the only subnational figures are survey estimates.",
        "ethnicity": "Tanzania's census has not asked ethnic group since 1973; the 2022 census did not.",
    },
    "SDN": {
        "religion": "Sudan's 2008 census, the last, dropped religion from the questionnaire by decision of the Presidency (UNSD country paper; IHSN catalogue); the only subnational figures are survey estimates.",
        "ethnicity": "Sudan's 2008 census dropped ethnicity with religion; the last count of ethnic group was 1956, on nine provinces that match no current boundary.",
    },
    "SSD": {
        "religion": "South Sudan has held no census since independence; the 2008 Sudan census that covered it dropped religion from the questionnaire by decision of the Presidency.",
        "ethnicity": "South Sudan has held no census since independence; the 2008 Sudan census that covered it dropped ethnicity with religion.",
    },
    "COL": {
        "religion": "Colombia's census does not ask religion; DANE publishes no religious statistics. The 2018 census asked ethnic self-recognition, which is on the map.",
        "language": "Colombia's 2018 census has no language question for the population; it asks only whether a person who is indigenous speaks their native language, which is not a composition.",
    },
    "DZA": {
        "religion": "Algeria's census does not ask religion; censuses on a religious, linguistic or ethnic basis are barred to preserve national unity. The 2022 RGPH form has no such question.",
        "ethnicity": "Algeria's census does not ask ethnicity, barred with religion and language; the 2022 RGPH form has no such question.",
        "language": "Algeria's census has not asked language since 1966, on a division set that matches no current boundary; the 2022 RGPH form has no such question.",
    },
    "SAU": {
        "religion": "Saudi Arabia's 2022 census asks citizenship (Saudi or non-Saudi, and country of citizenship) and not religion; there are no official religious statistics at any level.",
        "ethnicity": "Saudi Arabia's 2022 census records citizenship, not ethnicity.",
        "language": "Saudi Arabia's 2022 census does not ask language.",
    },
    "IRQ": {
        "ethnicity": "Iraq's 2024 census, the first nationwide count since 1987, deliberately excluded ethnicity from the questionnaire; religion was asked, sect was not.",
        "language": "Iraq's 2024 census deliberately excluded language from the questionnaire with ethnicity.",
    },
    "RUS": {
        "religion": "Russia's census has never asked religion; the 2020 census asked nationality and native language, which are on the map.",
    },
    "ARG": {
        "religion": "Argentina's census has not asked religion since 1960; only the 1947 and 1960 censuses carried the question. The 2022 census asks indigenous and Afro-descendant self-recognition instead.",
    },
    "BRA": {
        "language": "Brazil's census does not ask language of the population; the 2022 census asks which indigenous languages an indigenous person speaks, which is not a composition.",
    },
    "IRN": {
        "ethnicity": "Iran's census does not ask ethnicity; the 2016 census asked religion in the state's recognised categories, not ethnic group.",
        "language": "Iran's census does not ask language.",
    },
    "GRC": {
        "religion": "Greece's census has not asked religion since 1951; the 2021 census records citizenship and country of birth.",
        "language": "Greece's census has not asked mother tongue since 1951.",
    },
    "AFG": {
        "religion": "Afghanistan has never completed a population census: the 1979 count was abandoned partway and none has been held since, so no census question on religion exists; the NSIA publishes estimates only.",
        "ethnicity": "Afghanistan has never completed a population census, so no census question on ethnicity exists; the NSIA publishes estimates only.",
        "language": "Afghanistan has never completed a population census, so no census question on language exists; the NSIA publishes estimates only.",
    },
    "VEN": {
        "religion": "Venezuela's 2011 census asked indigenous and Afro-descendant self-recognition and not religion; no census since 1961 has carried a religion question.",
    },
    "PRK": {
        "religion": "North Korea's only modern census, 2008, asked no religion question, and the state publishes no other figures.",
        "ethnicity": "North Korea's 2008 census asked no ethnicity question.",
        "language": "North Korea's 2008 census asked no language question.",
    },
    "SYR": {
        "religion": "Syria's census has not asked religion since 1960; the 2004 census asked nationality (citizenship) only, as the US Census Bureau workbook's dictionary confirms.",
        "ethnicity": "Syria's census has never asked ethnicity; the 2004 sheet labelled Ethnicity is a distribution by nationality, which is citizenship.",
    },
    "TUN": {
        "religion": "Tunisia's census (2014, 2024) carries no religion question; the national figure is an estimate, not a count, and the only subnational figures are survey estimates.",
        "ethnicity": "Tunisia's census does not ask ethnicity.",
    },
    "KOR": {"ethnicity": "South Korea's census does not collect ethnicity."},
    "NLD": {"ethnicity": "The Netherlands records migration background, not ethnicity.",
            "language": "The Netherlands has had no questionnaire census since 1971 and no register records language."},
    "SWE": {"ethnicity": "Sweden records country of birth and citizenship, not ethnicity.",
            "religion": "Sweden's census is compiled from registers, and no register records religion; the state kept none after the Church of Sweden separated in 2000.",
            "language": "Sweden's census is compiled from registers, and no register records mother tongue."},
    "NOR": {"ethnicity": "Norway records immigrant background, not ethnicity."},
    "DNK": {"ethnicity": "Denmark records ancestry/citizenship, not ethnicity."},
    "BEL": {"ethnicity": "Belgium does not collect ethnicity; language community is administrative, not a census question.",
            "religion": "Belgium's census is compiled from registers and has never carried religion.",
            "language": "Belgium's language census was abolished by the law of 24 July 1961 after the 1947 count; the register-based census records none."},
    "ITA": {"ethnicity": "Italy's census records citizenship, not ethnicity."},
    "AUT": {
        "ethnicity": "Austria's census has been register-based since 2011 (Registerzählung) and records citizenship and country of birth; no register holds ethnicity.",
        "religion": "Austria's register-based census carries no religion; the last religion question was in the 2001 census.",
        "language": "Austria's register-based census carries no language; the last Umgangssprache question was in 2001.",
    },
    "SVN": {
        "ethnicity": "Slovenia's census has been register-based since 2011; ethnic affiliation was last asked in 2002.",
        "religion": "Slovenia's register-based census carries no religion; last asked in 2002.",
        "language": "Slovenia's register-based census carries no mother tongue; last asked in 2002.",
    },
    "ISL": {
        "ethnicity": "Iceland's census is register-based and records citizenship and country of birth, not ethnicity.",
        "language": "Iceland's register-based census carries no language.",
    },
    "FIN": {
        "ethnicity": "Finland's census is register-based and records citizenship, country of birth and mother tongue, not ethnicity.",
    },
    "CHE": {
        "ethnicity": "Switzerland's census records nationality, not ethnicity; religion and language come from the structural survey.",
    },
    "LUX": {
        "ethnicity": "Luxembourg's census records nationality, not ethnicity.",
        "religion": "Luxembourg's census (RP 2021) does not ask religion.",
    },
    "PRT": {
        "ethnicity": "Portugal's census records nationality, not ethnicity; an ethno-racial question was considered for 2021 and not included.",
    },
    "LVA": {
        "religion": "Latvia's census does not ask religion; it asks ethnicity and language.",
    },
    "UKR": {
        "religion": "Ukraine's 2001 census asked nationality and language, not religion.",
    },
    "BLR": {
        "religion": "Belarus's 2019 census asked nationality and language, not religion.",
    },
}


def collection_policy(iso3: str | None, field: str) -> str | None:
    """The documented reason a country does not collect ``field``, or None."""
    if not iso3:
        return None
    return NOT_COLLECTED_POLICY.get(iso3.upper(), {}).get(field)


def apply_collection_policy(record: dict[str, Any], iso3: str | None,
                            fields: Iterable[str] = ("religion", "ethnicity", "language"),
                            ) -> list[str]:
    """Mark fields the country never collects, in place.

    Only replaces a ``not_available`` marker: a real value from a subnational
    source always wins (a country can decline to ask nationally while a region
    publishes its own figures), and a more specific gap is left alone.
    """
    applied: list[str] = []
    for field in fields:
        reason = collection_policy(iso3, field)
        if not reason:
            continue
        current = record.get(field)
        if isinstance(current, dict) and current.get("status") == NOT_AVAILABLE:
            record[field] = gap(NOT_COLLECTED, reason)
            applied.append(field)
    return applied


# ---------------------------------------------------------------------------
# HTTP with on-disk cache + retry/backoff
# ---------------------------------------------------------------------------

def log(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def http_get(url: str, *, cache: bool = True, retries: int = 4, timeout: int = 120,
             headers: dict[str, str] | None = None, binary: bool = False,
             cache_dir: Path | None = None, aia: bool = False) -> bytes | str:
    """GET with a content-addressed disk cache and exponential backoff.

    Retries only network/5xx errors; a 404 raises immediately so callers can
    treat "this country has no ADM2" as data rather than as a failure.

    ``aia`` is for a server that sends its leaf certificate and omits the
    intermediate above it, which urllib reports as *unable to get local issuer
    certificate*. censusindia.gov.in is one: its certificate is properly issued
    and its chain is one link short, so a browser reaches it and Python does
    not. The repair is to fetch the missing intermediate from the certificate's
    own Authority Information Access extension and verify against it plus the
    public roots -- full verification, with the link the server failed to send
    supplied. It is never a way to skip the check: see scripts/probe_tls.py,
    which does the work and explains why an intermediate fetched over plain
    HTTP is safe to add (it is believed only if it chains to a trusted root,
    which the handshake then tests).
    """
    cache_dir = cache_dir or (RAW / "http_cache")
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    path = cache_dir / key
    if cache and path.exists():
        blob = path.read_bytes()
        return blob if binary else blob.decode("utf-8", "replace")

    req_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    req_headers.update(headers or {})
    opener = urllib.request.urlopen
    if aia:
        # Imported here, and with the directory put on the path first: this
        # module is reached both as `common` (scripts/ on sys.path) and as
        # `scripts.common`, and probe_tls is a sibling file rather than a
        # package member. Nothing above pays for it -- an adapter that does not
        # ask for the repair never runs this.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from probe_tls import verified_opener                 # noqa: PLC0415
        opener = verified_opener(urllib.parse.urlsplit(url).hostname or "").open
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with opener(req, timeout=timeout) as resp:
                blob = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    blob = gzip.decompress(blob)
            if cache:
                cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
            return blob if binary else blob.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            if exc.code in (400, 404, 403, 401):
                # Client errors will not get better on retry; fail fast so a
                # wrong table id costs one request, not 30 seconds of backoff.
                raise
            last = exc
        except Exception as exc:  # pragma: no cover - network shape varies
            last = exc
        if attempt < retries:
            log(f"  retry {attempt + 1}/{retries} after {delay:.0f}s :: {url} :: {last}")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"GET failed after {retries} retries: {url}") from last


def http_json(url: str, **kwargs: Any) -> Any:
    """GET + parse, tolerating the quirks national statistics APIs actually have.

    Statistics Canada prepends a UTF-8 BOM and sometimes a ``//`` guard line to
    its JSON; both make a raw ``json.loads`` fail with "Expecting value: line 1
    column 1".  And when a body still is not JSON, the parse error alone is
    useless in CI -- log the start of what the server actually sent, so a failed
    run diagnoses itself.
    """
    text = http_get(url, **kwargs)
    assert isinstance(text, str)
    cleaned = text.lstrip("\ufeff \n\r\t")
    if cleaned.startswith("//"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        preview = " ".join(text[:300].split())
        log(f"  ! non-JSON response from {url}\n    body starts: {preview!r}")
        raise


def download(url: str, dest: Path, *, force: bool = False, timeout: int = 3000) -> Path:
    """Stream a large file to disk, skipping the fetch when it already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        log(f"  cached {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    delay = 2.0
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as fh:
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
            tmp.replace(dest)
            log(f"  fetched {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
            return dest
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 403, 401):
                raise
            log(f"  retry {attempt + 1}/4 in {delay:.0f}s :: {exc}")
        except Exception as exc:  # pragma: no cover
            log(f"  retry {attempt + 1}/4 in {delay:.0f}s :: {exc}")
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"download failed: {url}")


# ---------------------------------------------------------------------------
# Parsing helpers for the free-text sources (Factbook, census footnotes)
# ---------------------------------------------------------------------------

_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?"
# "Greek Orthodox 81-90%" and "Muslim 98.0 - 99.0%": an optional second
# number makes the range explicit instead of leaving the row unmatched.
# Words that qualify a figure rather than name a group.
_QUALIFIER = re.compile(
    r"\b(?:approximately|approx\.?|about|roughly|around|est\.?|more than|over|"
    r"at least|greater than|less than|under|up to|nearly|almost|fewer than)\b",
    re.I)
_SHARE = re.compile(r"(?:^|\s)(<|>)?\s*(" + _NUM + r")"
                    r"(?:\s*[-\u2013\u2014]\s*(\d[\d,]*(?:\.\d+)?))?\s*%")


# The signature of UTF-8 bytes read as latin-1, written as the byte ranges it
# actually is: a two-or-more-byte lead (0xC2 and up) followed by a continuation
# byte (0x80-0xBF). Read as latin-1 those land on A-circumflex through sharp-s
# and then on a C1 control or Latin-1 punctuation -- a pair no real place name
# contains. Guessing at the visible lead characters instead missed Maori
# macrons, which encode from 0xC4 and 0xC5.
_MOJIBAKE = re.compile("[\u00c2-\u00df][\u0080-\u00bf]")


def repair(name: str) -> str:
    """Undo a name stored as UTF-8 that had been read as latin-1.

    geoBoundaries ships 33 such names across five countries -- Chile's regions
    read "Regi\u00c3\u00b3n Metropolitana de Santiago" -- and they are both
    shown to viewers and matched against by the census join, so every reader of
    the boundary file needs this, not just the one that builds the site.

    Re-encoding to latin-1 and decoding as UTF-8 is safe because it is
    self-checking: a name that really is latin-1 does not survive the round
    trip. "Ca\u00f1ete" encodes to bytes that are not valid UTF-8, so the
    decode raises and the name is left alone; only a string that *was* UTF-8
    all along comes back different and legible.
    """
    if not _MOJIBAKE.search(name):
        return name
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


# Names geoBoundaries spells wrong, and what they should be. Keyed by the
# country's ISO3 so a correction can never reach a similar name elsewhere.
#
# Unlike repair() above, nothing detects these. Mojibake is self-announcing --
# a byte pair no place name contains -- and the fix verifies itself by round
# trip. "Nothern Cape" is a perfectly well-formed string; only a reader who
# knows the place can tell it is wrong. So each entry is declared, matched
# exactly, and nothing is inferred: a rule loose enough to find these by
# similarity would also "correct" real names that merely resemble another, and
# "Nothern Cape" differs from "Northern Cape" by less than "Eastern Cape"
# differs from "Western Cape".
MISSPELLED: dict[tuple[str, str], str] = {
    ("ZAF", "Nothern Cape"): "Northern Cape",
    # geoBoundaries transposes Sagaing and drops a letter from Tanintharyi.
    # Both are well-formed words, so nothing can detect them; a reader who
    # knows Myanmar is the only test there is. The census, the Department of
    # Population and Myanmar's own English-language usage all agree.
    ("MMR", "Saigang"): "Sagaing",
    ("MMR", "Tanitharyi"): "Tanintharyi",
    # Two Brazilian states, and between them 21 million people who have had a
    # shape and no figures for as long as Brazil has been on this map. IBGE
    # publishes both; nothing reached them because geoBoundaries drops the "e"
    # from Grande and writes Janeiro as Jeneiro. Neither is detectable -- they
    # are well-formed words -- and both are the state's name in every Brazilian
    # source including the census this map reads.
    ("BRA", "Rio Granda do Norte"): "Rio Grande do Norte",
    ("BRA", "Rio de Jeneiro"): "Rio de Janeiro",
    # Five municipalities the 2022 census reached and the boundary file spells
    # its own way, found by reading the 22 shapes the join left unmatched. Each
    # right-hand side is IBGE's spelling, taken from the census file rather than
    # from anyone's memory: Arez keeps a z, Assu doubles its s, Graccho doubles
    # its c, and two prepositions differ -- Leverger takes "de" and Monte Alto
    # takes "do", which is the sort of thing no rule finds and no reader
    # doubts once the two lists are set side by side.
    ("BRA", "Arês"): "Arez",
    ("BRA", "Açu"): "Assú",
    ("BRA", "Gracho Cardoso"): "Graccho Cardoso",
    ("BRA", "Santo Antônio do Leverger"): "Santo Antônio de Leverger",
    ("BRA", "Barão de Monte Alto"): "Barão do Monte Alto",
    # China's most populous province, 126 million people, drawn under the name
    # of its capital city. Guangzhou is the city; Guangdong is the province, and
    # nothing that says Guangdong -- Wikidata included -- could ever reach a
    # shape called Guangzhou, so the province had a polygon and no figures.
    ("CHN", "Guangzhou Province"): "Guangdong",
    # And a doubled word: the shape is "Ningxia Ningxia Hui Autonomous Region".
    # It matched anyway, on the prefix, so this changes no join -- it changes
    # what a reader is shown, which is reason enough.
    ("CHN", "Ningxia Ningxia Hui Autonomous Region"): "Ningxia Hui Autonomous Region",
}


def respell(name: str, group: str | None = None) -> str:
    """The boundary file's name, with a declared misspelling corrected.

    Applied where the shapes are read, so the correct spelling is what the
    census join matches against as well as what a viewer sees. Without it the
    map labels a South African province "Nothern Cape" -- the data on it right,
    the name on it wrong -- and every source that spells the province correctly
    has to carry an alias to reach the shape at all.
    """
    if not group:
        return name
    return MISSPELLED.get((group, name), name)


def parse_number(text: str | None) -> float | int | None:
    if not text:
        return None
    m = re.search(_NUM, text.replace(" ", " "))
    if not m:
        return None
    raw = m.group(0).replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    return int(val) if val.is_integer() else val


def parse_year(text: str | None) -> int | None:
    """Pull the reference year out of strings like ``(2022 est.)``."""
    if not text:
        return None
    years = re.findall(r"(1[89]\d{2}|20\d{2})", text)
    return int(years[-1]) if years else None


def _split_top_level(text: str, separators: str = ",") -> list[str]:
    """Split on separators that are not inside parentheses or brackets.

    The Factbook nests commas and semicolons inside its asides -- "Muslim
    (official; predominantly Sunni) 99%, other (includes Christian, Jewish...)"
    -- so a naive ``split(",")`` invents groups called "Jewish" and "and
    Anglican)". Depth tracking is what keeps those inside their own aside.
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char in separators and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf))
    return parts


_YEAR = re.compile(r"\(\s*\d{4}")


def _pick_composition_block(text: str) -> str:
    """One composition out of a field that may carry several.

    The Factbook separates independent compositions with ``<br><br>``, and by
    the time the tags are stripped they read as one long list. Uruguay carries a
    detailed older survey followed by a 2023 estimate, so the merged reading put
    Roman Catholic in twice and totalled 158.2%.

    The most recent estimate wins, which is the last block carrying a vintage
    marker. Prose notes are dropped first: the World entry ends with three of
    them, so "take the last block" would return a sentence about how many
    languages exist rather than any figures at all.
    """
    blocks = [b for b in re.split(r"(?:<br\s*/?>\s*)+|\n{2,}", text) if b.strip()]
    if len(blocks) < 2:
        return text
    usable = [b for b in blocks
              if not re.match(r"\s*(?:<[^>]+>\s*)*note\b", b, re.I)
              and re.search(r"\d\s*%", b)]
    if not usable:
        return text
    dated = [b for b in usable if _YEAR.search(b)]
    return dated[-1] if dated else usable[0]


# A part that carries no readable share is still usually a group: the Factbook
# writes Mali's plurality language as "Bambara (official)" with no figure, and
# names South Sudan's Shilluk, Azande, Bari and fifteen more without one. Those
# used to be dropped, which is the worst of the three possible outcomes -- the
# remaining slivers were then presented as a whole composition, so Mali read as
# a country where the language half of it speaks does not exist. Keeping the
# member with an explicit gap says what the source actually says: this group is
# here, its share is not published.
#
# Three shapes are not members, and each is recognised by where it sits rather
# than by what it means:
_NOT_A_MEMBER = re.compile(
    r"^(?:including|and|or|some|mostly|mainly|largely|chiefly|such\s+as|"
    r"with|plus|note)\b", re.I)


def _shareless_member(parts: list[str], i: int) -> dict[str, Any] | None:
    """The row for a part naming a group the source gives no figure for.

    Only ever called for a text that carries at least one real share. A list
    with no figures anywhere is not a composition missing one member, it is a
    list of names, and ``parse_languages`` already renders those as the whole
    field being unquantified. Reading them here instead would turn the EU's
    24 official languages into 24 gaps in a chart nobody asked for.
    """
    part = parts[i]
    # (1) Commentary rather than a group: "including Liberian English variants"
    #     after Liberia's English, "some 839 living indigenous languages".
    if _NOT_A_MEMBER.match(part):
        return None
    # (2) A count of languages rather than a language: PNG's and the Solomon
    #     Islands' "120 indigenous languages".
    if re.match(r"^\d", part):
        return None
    # (3) One item of a name the comma-split tore apart. South Africa's
    #     "ancestral, tribal, animist, or other traditional African religions
    #     5.4%" is a single group whose share sits on the last fragment, and
    #     Botswana's bare "other" belongs to "including Kgalagadi ... 7%".
    #     What marks it is not the fragment but what closes the run it is in:
    #     a following part opening with "or" or "including" means every
    #     shareless part back to here was part of that one name.
    for j in range(i + 1, len(parts)):
        if re.match(r"^(?:or|including)\b", parts[j], re.I):
            return None
        if _SHARE.search(re.sub(r"\([^()]*\)", " ", parts[j])):
            break
    label = re.sub(r"\([^()]*\)", " ", part)
    # A figure the parser could not read -- the Factbook's "Christian 93/1%"
    # for the DRC, Andorra's "Christian 89.5" with the sign missing -- leaves
    # digits behind. The name in front of it is still the group; the mangled
    # figure is not repaired here, because inferring 93.1 from "93/1" is a
    # guess, and a named group with a stated gap is the honest reading.
    label = re.split(r"[<>\d]", label)[0]
    # Qualifiers are deliberately *not* stripped: they belong to a measurement,
    # and there is none. Rwanda's census category is "more than one language",
    # which stripping would leave as the nonsense "one language".
    label = re.sub(r"\s+", " ", label).strip(" .,;-")
    if not label or len(label) > 80 or not re.search(r"[^\W\d_]", label):
        return None
    # Cutting at the digit can leave the qualifier that introduced it and
    # nothing else -- Chad's "more than 120 languages", Niger's "over", Taiwan's
    # "approximately". A group name that is only a qualifier is not a group.
    if not _QUALIFIER.sub(" ", label).strip(" .,;-"):
        return None
    return {"group": label, "pct": None, "pct_status": NOT_AVAILABLE}


def parse_composition(text: str | None, *, source: str | None = None) -> list[dict[str, Any]] | None:
    """Turn ``"Hindu 79.8%, Muslim 14.2%, other 0.9%"`` into structured shares.

    Handles the Factbook's parenthetical asides, ``<1%`` markers and trailing
    ``(2011 est.)`` year tags.  Returns ``None`` when nothing parseable is found,
    which the caller renders as an explicit gap rather than as an empty chart.
    """
    if not text:
        return None
    # Before the tags go: they are what marks the boundary between two separate
    # compositions, and stripping them first silently welds the two together.
    text = _pick_composition_block(text)
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = clean.replace("\u00a0", " ")
    clean = re.sub(r"\s*note\s*\d*\s*:.*$", "", clean, flags=re.I | re.S)
    # Drop only the trailing vintage marker -- "(2011 est.)" -- not every aside.
    clean = re.sub(r"\((?:[^()]*?\b(?:est\.|census)\b[^()]*?|\s*\d{4}\s*)\)\s*$", " ", clean)
    # A top-level semicolon introduces commentary, not another group.
    clean = _split_top_level(clean, ";")[0]
    # A block may open with a heading -- "most-spoken language:" -- which once
    # stripped of its tags reads as part of the first group's name. Only a short
    # colon-terminated run before any figure qualifies, so a real label
    # containing a colon cannot be eaten.
    clean = re.sub(r"^[^,%:]{0,40}:\s*", "", clean.lstrip())
    # "1%-2%" is one range, written with a sign on each end. Normalising it to
    # "1-2%" lets the range arm read it, and lets an aside be judged on how many
    # figures it really carries rather than how many per-cent signs it contains.
    clean = re.sub(r"(\d[\d.,]*)\s*%\s*([-\u2013\u2014])\s*(\d[\d.,]*)\s*%",
                   r"\1\2\3%", clean)

    out: list[dict[str, Any]] = []
    parts = [p for p in (q.strip(" .") for q in _split_top_level(clean, ",")) if p]
    # Whether this text is a composition at all, which is what makes a member
    # with no figure worth recording. Decided once, over the whole text.
    quantified = _SHARE.search(clean) is not None
    for i, part in enumerate(parts):
        # Parenthetical asides go before the figure is read, not after. They
        # carry percentages of their own -- Iraq's "Muslim (official) 95-98%
        # (Shia 61-64%, Sunni 29-34%)" -- and a search that can see inside them
        # picks up a sub-split and reports it as the group's own share. It also
        # means a country whose only figures are inside an aside, as Saudi
        # Arabia's are, yields nothing and stays an honest gap.
        bare = re.sub(r"\([^()]*\)", " ", part)
        match = _SHARE.search(bare)
        if match:
            part = bare
        else:
            # Nothing outside the aside. Some asides do carry the group's own
            # share -- Sudan's "Sudanese Arab (approximately 70%)", the Solomon
            # Islands' "English (... spoken by only 1%-2% ...)" -- and dropping
            # those loses the only figure the entry has.
            #
            # Others carry a breakdown of the group instead, or a statistic
            # about something else entirely. Saudi Arabia's "(official; citizens
            # are 85-90% Sunni and 10-12% Shia)" would otherwise be read as the
            # Muslim share, and Sierra Leone's aside about Krio being "a first
            # language for 10%" as the country's whole language composition.
            # Both of those list several things: a semicolon, or more than one
            # figure. One figure and no list is the case worth trusting.
            aside = " ".join(re.findall(r"\(([^()]*)\)", part))
            match = None if (";" in aside or aside.count("%") != 1) else _SHARE.search(part)
            if not match:
                row = _shareless_member(parts, i) if quantified else None
                if row:
                    out.append(row)
                continue
        bound = match.group(1)
        low = float(match.group(2).replace(",", ""))
        high = match.group(3)
        # A range is the Factbook's way of saying it does not know precisely.
        # Dropping these rows -- which is what a pattern without the range arm
        # did -- left Greece with no Orthodox, Serbia with neither of its two
        # largest groups, and Saudi Arabia and the West Bank with nothing at
        # all, while the remaining slivers still read as a whole composition.
        # The midpoint is used and the range kept, so the figure can be shown
        # as the estimate it is rather than as false precision.
        pct = low if high is None else (low + float(high.replace(",", ""))) / 2
        label = part[: match.start()].strip(" .-")
        label = re.sub(r"\s*\([^)]*\)?\s*", " ", label)
        label = re.sub(r"\s+", " ", label)
        # A qualifier sitting between the group and its figure -- "approximately
        # 35-40%", "more than 95%" -- is part of the measurement, not of the
        # group's name. Taiwan is "Han Chinese", not "Han Chinese more than".
        # Where the qualifier is directional it is kept as a bound, which the
        # record format already carries for "<1%".
        tail = label[-24:].lower()
        if not bound:
            if re.search(r"\b(?:more than|over|at least|greater than)\s*$", tail):
                bound = ">"
            elif re.search(r"\b(?:less than|under|up to|nearly|almost|fewer than)\s*$", tail):
                bound = "<"
        label = re.sub(_QUALIFIER, " ", label)
        label = re.sub(r"\s+", " ", label).strip(" .-")
        if not label or len(label) > 80:
            continue
        row: dict[str, Any] = {"group": label, "pct": pct}
        if high is not None:
            row["range"] = [low, float(high.replace(",", ""))]
        # "<1%" is an upper bound, not a measurement; keep the distinction so a
        # chart cannot quietly promote it to an exact share.
        if bound:
            row["bound"] = bound
        out.append(row)
    return out or None


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", (text or "").lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def write_json(path: Path, payload: Any, *, compact: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")
    # A --out given on the command line is relative to the working directory,
    # not to ROOT, and relative_to raises rather than falling back. The write
    # has already happened by this point, so a tidier log line was taking down
    # runs whose real work had succeeded.
    try:
        shown = path.resolve().relative_to(ROOT)
    except ValueError:
        shown = path
    log(f"  wrote {shown} ({path.stat().st_size / 1e3:.0f} kB)")
    return path


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def chunked(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
