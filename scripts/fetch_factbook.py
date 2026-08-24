#!/usr/bin/env python3
"""Country-level demographics from the CIA World Factbook (public domain).

The Factbook site was retired in February 2026; this reads the community
``factbook/factbook.json`` mirror (CC0), which tracked it weekly until then.
Treat the result as a *frozen snapshot* and prefer live national statistics
for population currency -- every field carries its own reference year so the
staleness is visible in the UI rather than hidden.

Usage:
    python scripts/fetch_factbook.py [--refresh]
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import unicodedata
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    NOT_APPLICABLE,
    NOT_AVAILABLE,
    NOT_COLLECTED_POLICY,
    NOT_COLLECTED,
    PROCESSED,
    RAW,
    gap,
    http_get,
    log,
    measure,
    parse_composition,
    parse_number,
    parse_year,
    read_json,
    write_json,
)

REPO = "https://github.com/factbook/factbook.json"
MIRROR = "https://raw.githubusercontent.com/factbook/factbook.json/master"
LOCAL = RAW / "factbook"
REGIONS = [
    "africa", "antarctica", "australia-oceania", "central-america-n-caribbean",
    "central-asia", "east-n-southeast-asia", "europe", "middle-east",
    "north-america", "oceans", "south-america", "south-asia",
]

# Countries that legally or administratively do not collect a field at all.
# This is the "not collected" vs "not available" distinction the plan calls an
# editorial-integrity requirement -- an empty Factbook field is NOT proof of it.


# ---------------------------------------------------------------------------
# Source acquisition
# ---------------------------------------------------------------------------

def sync_repo(refresh: bool = False) -> Path | None:
    """Shallow-clone the mirror.  Falls back to per-file HTTP when git is absent."""
    if LOCAL.exists() and not refresh:
        log(f"  using cached factbook clone at {LOCAL}")
        return LOCAL
    if refresh and LOCAL.exists():
        shutil.rmtree(LOCAL)
    if not shutil.which("git"):
        return None
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    log(f"  cloning {REPO} (shallow)")
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", REPO, str(LOCAL)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        log(f"  git clone failed: {proc.stderr.strip()[:200]}")
        return None
    return LOCAL


def iter_profiles(local: Path | None) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield ``(region, gec_code, profile)`` for every Factbook entity."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    if local is not None:
        for region in REGIONS:
            folder = local / region
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                out.append((region, path.stem, read_json(path, {})))
        return out
    # HTTP fallback: probe every two-letter code in every region folder.
    log("  git unavailable -- probing the raw mirror over HTTP")
    import itertools
    import string
    for region, (a, b) in itertools.product(REGIONS, itertools.product(string.ascii_lowercase, repeat=2)):
        code = a + b
        try:
            profile = http_get(f"{MIRROR}/{region}/{code}.json")
        except Exception:
            continue
        import json as _json
        out.append((region, code, _json.loads(profile)))
    return out


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def dig(profile: dict[str, Any], *path: str) -> Any:
    node: Any = profile
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def text_at(profile: dict[str, Any], *path: str) -> str | None:
    node = dig(profile, *path)
    if isinstance(node, dict):
        node = node.get("text")
    if isinstance(node, str):
        # <br><br> separates independent compositions: a country may publish an
        # older detailed survey and a current estimate in one field. Collapsing
        # that boundary into a space welds them into a single list -- Uruguay's
        # religions then read 158.2% with Roman Catholic counted twice -- so the
        # blocks are cleaned separately and rejoined as blank lines, which
        # survive to parse_composition where the choice between them is made.
        blocks = []
        for block in re.split(r"(?:<br\s*/?>\s*)+", node):
            text = html.unescape(re.sub(r"<[^>]+>", " ", block))
            text = re.sub(r"[^\S\n]+", " ", text.replace("\u00a0", " ")).strip()
            if text:
                blocks.append(text)
        return "\n\n".join(blocks) or None
    return None


def parse_capital(profile: dict[str, Any]) -> tuple[str | None, list[float] | None]:
    name = text_at(profile, "Government", "Capital", "name")
    if name:
        name = re.split(r";|\(", name)[0].strip()
        name = re.sub(r"\s*note\s*:.*$", "", name, flags=re.I).strip(" ,.")
    coords = text_at(profile, "Government", "Capital", "geographic coordinates")
    lonlat = None
    if coords:
        m = re.match(r"(\d+)\s+(\d+)\s+([NS]),\s*(\d+)\s+(\d+)\s+([EW])", coords)
        if m:
            lat = int(m.group(1)) + int(m.group(2)) / 60
            lon = int(m.group(4)) + int(m.group(5)) / 60
            if m.group(3) == "S":
                lat = -lat
            if m.group(6) == "W":
                lon = -lon
            lonlat = [round(lon, 5), round(lat, 5)]
    return (name or None), lonlat


def parse_major_urban(profile: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    """``"3.574 million BERLIN (capital), 1.788 million Hamburg, ..."`` -> cities."""
    raw = text_at(profile, "People and Society", "Major urban areas - population")
    if not raw:
        return None, []
    year = parse_year(raw)
    cities: list[dict[str, Any]] = []
    for part in re.split(r",(?![^(]*\))", raw):
        part = part.strip()
        m = re.match(r"([\d.,]+)\s*(million|billion)?\s+(.+)$", part)
        if not m:
            continue
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2) == "million":
            value *= 1e6
        elif m.group(2) == "billion":
            value *= 1e9
        label = m.group(3)
        is_capital = "(capital)" in label.lower()
        label = re.sub(r"\([^)]*\)", "", label).strip(" ,.;")
        label = re.sub(r"\s*\d{4}.*$", "", label).strip()
        if not label:
            continue
        # The Factbook shouts capital names; normalise ALL CAPS to Title Case.
        if label.isupper():
            label = label.title()
        cities.append({
            "name": label,
            "population": int(value),
            "is_capital": is_capital,
            "year": year,
        })
    largest = cities[0]["name"] if cities else None
    return largest, cities


def parse_sex_ratio(profile: dict[str, Any]) -> dict[str, Any] | None:
    raw = text_at(profile, "People and Society", "Sex ratio", "total population")
    val = parse_number(raw)
    if val is None:
        return None
    return measure(round(float(val) * 1000), unit="males_per_1000_females",
                   year=parse_year(raw), source="CIA World Factbook")


def parse_age_structure(profile: dict[str, Any]) -> dict[str, Any] | None:
    node = dig(profile, "People and Society", "Age structure")
    if not isinstance(node, dict):
        return None
    out: dict[str, Any] = {}
    for band, payload in node.items():
        text = payload.get("text") if isinstance(payload, dict) else None
        pct = parse_number(text)
        if pct is not None:
            out[band] = pct
    return out or None


def parse_languages(profile: dict[str, Any]) -> list[dict[str, Any]] | None:
    raw = text_at(profile, "People and Society", "Languages", "Languages")
    if raw is None:
        raw = text_at(profile, "People and Society", "Languages")
    comp = parse_composition(raw)
    if comp:
        return comp
    if not raw:
        return None
    # No percentages published -- keep the named languages, flag the missing shares.
    names = [re.sub(r"\([^)]*\)", "", part).strip(" ,.;")
             for part in re.split(r"[,;]", raw.split("note")[0])]
    names = [n for n in names if n and len(n) < 60][:12]
    if not names:
        return None
    return [{"group": n, "pct": None, "pct_status": NOT_AVAILABLE} for n in names]

# ---------------------------------------------------------------------------
# GEC -> ISO3 resolution
#
# The mirror keys profiles by two-letter GEC (ex-FIPS 10-4) stems, but has
# migrated some entities to ISO-style stems (``in`` = India, ``id`` =
# Indonesia).  Resolving by stem alone therefore silently swaps countries, so
# we resolve by *name* against the Natural Earth country index and use the code
# only as a tie-breaker.  Anything still unresolved is reported, never guessed.
# ---------------------------------------------------------------------------

MANUAL_CODE_ISO = {
    # Entities whose Factbook name has no Natural Earth counterpart.
    "gz": "PSE",   # Gaza Strip        -> State of Palestine
    "we": "PSE",   # West Bank         -> State of Palestine
    "kv": "XKX",   # Kosovo (user-assigned code)
    "bm": "MMR",   # Burma             -> Myanmar
    "vt": "VAT",   # Holy See (Vatican City)
    "fk": "FLK",   # Falkland Islands (Islas Malvinas)
    "ck": "COK",   # Cook Islands
    "vq": "VIR",   # Virgin Islands    -> U.S. Virgin Islands
    "sh": "SHN",   # Saint Helena, Ascension, and Tristan da Cunha
    "sv": "SJM",   # Svalbard          -> Svalbard and Jan Mayen
    "jn": "SJM",   # Jan Mayen         -> Svalbard and Jan Mayen
    "kt": "CXR",   # Christmas Island
    "tl": "TKL",   # Tokelau
    "bv": "BVT",   # Bouvet Island
    "um": "UMI",   # United States Pacific Island Wildlife Refuges
    "wq": "UMI",   # Wake Island
    "bq": "UMI",   # Navassa Island
    # Deliberately code-less: supranational bodies, oceans, unresolved claims
    # and sovereign base areas have no ISO 3166-1 country code, so they keep a
    # GEC- id rather than borrowing someone else's.
    "ee": "None",  # European Union
    "ax": "None",  # Akrotiri (UK Sovereign Base Area)
    "dx": "None",  # Dhekelia (UK Sovereign Base Area)
    "pf": "None",  # Paracel Islands
    "pg": "None",  # Spratly Islands
}


# Leading/trailing qualifiers that can be dropped without changing identity.
# Note what is NOT here: "states", "kingdom", "union".  Stripping those collapses
# "United States" and "United Kingdom" onto the same key.
_PREFIXES = (
    "the ", "republic of ", "the republic of ", "islamic republic of ",
    "people's republic of ", "peoples republic of ", "democratic republic of ",
    "federal republic of ", "federative republic of ", "kingdom of ",
    "state of ", "united republic of ", "principality of ", "sultanate of ",
    "grand duchy of ", "commonwealth of ", "co-operative republic of ",
    "socialist republic of ", "arab republic of ", "bolivarian republic of ",
    "plurinational state of ", "independent state of ", "oriental republic of ",
)


def _norm_name(text: str | None) -> str:
    """Diacritic-free, punctuation-free key.  No word removal."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", html.unescape(text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _loose_name(text: str | None) -> str:
    """Same key with a leading constitutional qualifier removed."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", html.unescape(text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().strip()
    for prefix in _PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = re.sub(r",\s*(the|republic|kingdom|islamic republic)$", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


class CountryResolver:
    """Resolve a Factbook profile to an ISO 3166-1 alpha-3 code."""

    def __init__(self, index: list[dict[str, Any]]):
        self.index = index
        self.by_name: dict[str, str] = {}
        self.by_loose: dict[str, str] = {}
        self.by_fips: dict[str, str] = {}
        self.by_iso2: dict[str, str] = {}
        self.meta: dict[str, dict[str, Any]] = {row["iso3"]: row for row in index}
        # Sovereign states index first so a dependency never shadows its parent.
        for row in sorted(index, key=lambda r: (not r.get("sovereign"), r["iso3"])):
            iso3 = row["iso3"]
            for name in row["names"]:
                self.by_name.setdefault(_norm_name(name), iso3)
                self.by_loose.setdefault(_loose_name(name), iso3)
            if row.get("fips"):
                self.by_fips.setdefault(row["fips"], iso3)
            if row.get("iso2"):
                self.by_iso2.setdefault(row["iso2"], iso3)

    def resolve(self, code: str, profile: dict[str, Any]) -> tuple[str | None, str | None, str]:
        """Return ``(iso3, iso2, how)``.  ``iso3`` is None when unresolved."""
        manual = MANUAL_CODE_ISO.get(code.lower())
        if manual:
            iso3 = None if manual == "None" else manual
            return iso3, self.meta.get(iso3 or "", {}).get("iso2"), "manual"

        candidates = [
            text_at(profile, "Government", "Country name", "conventional short form"),
            text_at(profile, "Government", "Country name", "conventional long form"),
            text_at(profile, "Government", "Country name", "etymology"),
        ]
        for raw in candidates[:2]:
            iso3 = self.by_name.get(_norm_name(raw))
            if iso3:
                return iso3, self.meta[iso3].get("iso2"), "name"
        for raw in candidates[:2]:
            iso3 = self.by_loose.get(_loose_name(raw))
            if iso3:
                return iso3, self.meta[iso3].get("iso2"), "name-loose"

        for lookup, how in ((self.by_fips, "fips"), (self.by_iso2, "iso2")):
            iso3 = lookup.get(code.upper())
            if not iso3:
                continue
            # Only trust the code when the profile has no usable name at all;
            # a name that disagrees means the mirror re-keyed the entity.
            mine = {_loose_name(c) for c in candidates[:2] if c} - {""}
            known = {_loose_name(n) for n in self.meta[iso3]["names"]}
            if not mine or mine & known:
                return iso3, self.meta[iso3].get("iso2"), how
        return None, None, "unresolved"


def build_record(region: str, gec: str, profile: dict[str, Any],
                 iso3: str | None, iso2: str | None) -> dict[str, Any]:
    src = "CIA World Factbook (public domain), factbook.json mirror"
    name = (text_at(profile, "Government", "Country name", "conventional short form")
            or text_at(profile, "Government", "Country name", "conventional long form")
            or gec.upper())
    if name.lower() in {"none", "n/a"}:
        name = text_at(profile, "Government", "Country name", "conventional long form") or gec.upper()

    pop_text = text_at(profile, "People and Society", "Population", "total")
    pop = parse_number(pop_text)
    capital, capital_coords = parse_capital(profile)
    largest, cities = parse_major_urban(profile)
    median_text = text_at(profile, "People and Society", "Median age", "total")
    area_text = text_at(profile, "Geography", "Area", "total ")or text_at(profile, "Geography", "Area", "total")

    religion_text = text_at(profile, "People and Society", "Religions")
    ethnic_text = text_at(profile, "People and Society", "Ethnic groups")

    policy = NOT_COLLECTED_POLICY.get(iso3 or "", {})

    def composition(field: str, text: str | None) -> Any:
        if field in policy:
            return gap(NOT_COLLECTED, policy[field])
        comp = parse_composition(text)
        if comp:
            return comp
        if text:
            return gap(NOT_AVAILABLE, f"Factbook reports free text only: {text[:180]}")
        return gap(NOT_AVAILABLE, "No composition published by the Factbook for this entity.")

    languages = parse_languages(profile)

    return {
        "id": iso3 or f"GEC-{gec.upper()}",
        "level": "admin0",
        "name": name,
        "parent": None,
        "codes": {
            "iso3": iso3, "iso2": iso2, "gec": gec.upper(),
            "factbook_region": region,
        },
        "capital": capital or gap(NOT_APPLICABLE if region == "oceans" else NOT_AVAILABLE),
        "capital_coordinates": capital_coords,
        "largest_settlement": largest or gap(NOT_AVAILABLE,
                                             "Factbook lists no major urban areas for this entity."),
        "largest_settlements": cities,
        "population": measure(int(pop), year=parse_year(pop_text), source=src) if pop else gap(NOT_AVAILABLE),
        "area_km2": measure(parse_number(area_text), unit="km2", source=src) if area_text else gap(NOT_AVAILABLE),
        "median_age": measure(parse_number(median_text), unit="years",
                              year=parse_year(median_text), source=src) if median_text else gap(NOT_AVAILABLE),
        "sex_ratio": parse_sex_ratio(profile) or gap(NOT_AVAILABLE),
        "age_structure": parse_age_structure(profile) or gap(NOT_AVAILABLE),
        "life_expectancy": measure(
            parse_number(text_at(profile, "People and Society", "Life expectancy at birth", "total population")),
            unit="years", source=src),
        "fertility_rate": measure(
            parse_number(text_at(profile, "People and Society", "Total fertility rate")),
            unit="children_per_woman", source=src),
        "urban_population_pct": measure(
            parse_number(text_at(profile, "People and Society", "Urbanization", "urban population")),
            unit="percent", source=src),
        "religion": composition("religion", religion_text),
        "religion_year": parse_year(religion_text),
        "language": languages or gap(NOT_AVAILABLE),
        "ethnicity": composition("ethnicity", ethnic_text),
        "ethnicity_year": parse_year(ethnic_text),
        "sources": [{
            "field": "*",
            "name": "CIA World Factbook",
            "url": f"{MIRROR}/{region}/{gec}.json",
            "license": "Public domain",
            "retrieved_via": "factbook/factbook.json mirror",
        }],
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-clone the mirror")
    ap.add_argument("--out", type=Path, default=PROCESSED / "admin0.json")
    args = ap.parse_args()

    log("fetch_factbook: syncing source")
    local = sync_repo(args.refresh)
    profiles = iter_profiles(local)
    log(f"  {len(profiles)} Factbook entities")

    index = read_json(RAW / "codes" / "country_index.json", [])
    if not index:
        log("  ERROR: run scripts/fetch_natural_earth.py first "
            "(it writes data/raw/codes/country_index.json).")
        return 1
    resolver = CountryResolver(index)

    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    seen: dict[str, str] = {}
    for region, gec, profile in profiles:
        if not profile:
            continue
        iso3, iso2, how = resolver.resolve(gec, profile)
        if iso3 and iso3 in seen:
            log(f"  note: {gec} and {seen[iso3]} both map to {iso3}; keeping both, ids suffixed")
        record = build_record(region, gec, profile, iso3, iso2)
        if iso3:
            if iso3 in seen:
                record["id"] = f"{iso3}-{gec.upper()}"
            seen.setdefault(iso3, gec)
        else:
            unresolved.append(f"{region}/{gec}")
        records.append(record)
    if unresolved:
        log(f"  {len(unresolved)} entities without an ISO3 code (kept with GEC- ids): "
            + ", ".join(unresolved[:40]))

    records.sort(key=lambda r: r["name"])
    write_json(args.out, records)

    with_iso = sum(1 for r in records if r["codes"]["iso3"])
    with_rel = sum(1 for r in records if isinstance(r["religion"], list))
    with_eth = sum(1 for r in records if isinstance(r["ethnicity"], list))
    not_coll = sum(1 for r in records
                   if isinstance(r["ethnicity"], dict) and r["ethnicity"].get("status") == NOT_COLLECTED)
    log(f"  {len(records)} records | {with_iso} ISO3-matched | "
        f"religion {with_rel} | ethnicity {with_eth} | ethnicity not-collected {not_coll}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
