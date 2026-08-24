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
    "JPN": {
        "ethnicity": "Japan's census collects nationality, not ethnicity.",
        "religion": "Japan's census does not ask religion; published figures are religious-body self-reports that exceed the population.",
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
    "KOR": {"ethnicity": "South Korea's census does not collect ethnicity."},
    "NLD": {"ethnicity": "The Netherlands records migration background, not ethnicity."},
    "SWE": {"ethnicity": "Sweden records country of birth and citizenship, not ethnicity."},
    "NOR": {"ethnicity": "Norway records immigrant background, not ethnicity."},
    "DNK": {"ethnicity": "Denmark records ancestry/citizenship, not ethnicity."},
    "BEL": {"ethnicity": "Belgium does not collect ethnicity; language community is administrative, not a census question."},
    "ITA": {"ethnicity": "Italy's census records citizenship, not ethnicity."},
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
             cache_dir: Path | None = None) -> bytes | str:
    """GET with a content-addressed disk cache and exponential backoff.

    Retries only network/5xx errors; a 404 raises immediately so callers can
    treat "this country has no ADM2" as data rather than as a failure.
    """
    cache_dir = cache_dir or (RAW / "http_cache")
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    path = cache_dir / key
    if cache and path.exists():
        blob = path.read_bytes()
        return blob if binary else blob.decode("utf-8", "replace")

    req_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    req_headers.update(headers or {})
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    for part in _split_top_level(clean, ","):
        part = part.strip(" .")
        if not part:
            continue
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
            if ";" in aside or aside.count("%") != 1:
                continue
            match = _SHARE.search(part)
            if not match:
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
