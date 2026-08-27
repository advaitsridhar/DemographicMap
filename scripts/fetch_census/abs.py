#!/usr/bin/env python3
"""Australia -- ABS Data API (SDMX-JSON), 2021 Census, states and SA3/LGA.

The ABS Data API serves census tables as SDMX-JSON dataflows.  This pulls:

* ``C21_G14_LGA`` religious affiliation
* ``C21_G08_LGA`` ancestry (multi-response: people may report two ancestries,
  so shares sum above 100% and are labelled as responses, not persons)

Population comes out of the religion table rather than from a table of its own.
G14 carries its own total, and religion is asked of everyone -- the question is
voluntary, but a blank answer is coded "Not stated" rather than dropped -- so
that total is the region's counted persons. The docstring here used to promise
``C21_G01`` and the code never fetched it, which is why all 565 LGAs shipped
with no population at all.

Australia has no ethnicity question. It asks *ancestry* plus country of birth,
and separately Aboriginal and Torres Strait Islander status; the app keeps those
as distinct fields rather than folding them into an "ethnicity" bucket.
Religion is a voluntary question ("not stated" is its own category).

Usage:
    python -m scripts.fetch_census.abs --level state
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_get, log, measure,
    record, shares, write_json,
)

API = "https://data.api.abs.gov.au/rest/data/{agency},{dataflow},{version}/{key}"
CATALOGUE = "https://data.api.abs.gov.au/rest/dataflow/ABS?detail=allstubs"
# The ABS publishes no state-level census table: the catalogue offers CED, LGA,
# POA, RA, SA2, SAL, SED, SUA and UCL and nothing else, so asking for "STE" used
# to fall through to Remoteness Areas and return "Major Cities of Australia
# (NSW)" as though it were a state. The LGA table carries a STATE dimension,
# though, so the states are read off that -- the ABS's own assignment of each
# LGA to its state, rather than a guess from geometry.
REGION_TYPE = {"state": "LGA", "lga": "LGA", "sa3": "SA3"}
REGION_DIMENSION = {"state": "STATE"}
ASGS_LEVEL = {"state": "STE", "lga": "LGA", "sa3": "SA3"}
# Census 2021 table numbers: G14 religious affiliation, G08 ancestry.
DATAFLOW_HINTS = {"religion": "C21_G14_{r}", "ancestry": "C21_G08_{r}"}


def discover_dataflows(region: str) -> dict[str, tuple[str, str, str]]:
    """Resolve field -> (agency, dataflow id, version) from the live catalogue.

    The exact 2021-census dataflow ids were guessed once and 404ed, so instead
    of hardcoding them, list every dataflow the ABS publishes and pick the ones
    whose id matches the census table number and region suffix.
    """
    import re as _re
    xml = http_get(CATALOGUE, timeout=300,
                   headers={"Accept": "application/vnd.sdmx.structure+xml;version=2.1"})
    assert isinstance(xml, str)
    flows = _re.findall(
        r'<(?:str|structure):Dataflow[^>]*\bid="([^"]+)"[^>]*\bagencyID="([^"]+)"'
        r'[^>]*\bversion="([^"]+)"', xml)
    if not flows:  # attribute order is not guaranteed in XML
        flows = [(m.group("id"), m.group("agency"), m.group("version"))
                 for m in _re.finditer(
                     r'<[^>]*Dataflow(?=[^>]*\bid="(?P<id>[^"]+)")'
                     r'(?=[^>]*\bagencyID="(?P<agency>[^"]+)")'
                     r'(?=[^>]*\bversion="(?P<version>[^"]+)")[^>]*>', xml)]
    log(f"  {len(flows)} dataflows in the ABS catalogue")
    # When nothing matches, the census-looking ids are the diagnosis: print
    # them so a failed CI run documents the real naming scheme.
    # The G14/G08 sets are small; print them completely -- run 3's broad sample
    # was drowned in sixty CENSUS2011_B* ids before reaching the C21 block.
    for table in ("G14", "G08"):
        ids = sorted(f[0] for f in flows if table in f[0].upper())
        if ids:
            log(f"  dataflows containing {table}: " + ", ".join(ids[:40]))

    out: dict[str, tuple[str, str, str]] = {}
    table_of = {"religion": "G14", "ancestry": "G08"}
    for field, pattern in DATAFLOW_HINTS.items():
        wanted = pattern.format(r=region).upper()
        table = table_of[field]
        exact = [f for f in flows if f[0].upper() == wanted]
        # Same census table, right region.
        regional = [f for f in flows
                    if table in f[0].upper() and region in f[0].upper()]
        # Same census table at all: better one dataflow filtered by region
        # dimension at query time than nothing.
        any_region = [f for f in flows if table in f[0].upper()]
        chosen = (exact or regional or sorted(any_region, key=lambda f: len(f[0])) or [None])[0]
        if chosen:
            out[field] = (chosen[1], chosen[0], chosen[2])
            log(f"  {field}: dataflow {chosen[1]},{chosen[0]},{chosen[2]}")
        else:
            log(f"  {field}: nothing in the catalogue mentions table {table}")
    return out


def sdmx(flow: tuple[str, str, str], key: str = "all") -> dict[str, Any]:
    agency, dataflow, version = flow
    url = (API.format(agency=agency, dataflow=dataflow, version=version, key=key)
           + "?format=jsondata&detail=full")
    import json as _json
    return _json.loads(http_get(url, timeout=300,
                                headers={"Accept": "application/vnd.sdmx.data+json"}))


def unpack(payload: dict[str, Any]) -> list[tuple[dict[str, str], float]]:
    """SDMX-JSON series -> [(dimension label map, observation value)].

    Handles both wire formats the ABS serves: SDMX-JSON 1.0 puts a singular
    ``structure`` beside ``dataSets``; 2.0 puts a ``structures`` list there
    (the live API answered with the latter -- KeyError 'structure' in run 3).
    """
    body = payload["data"]
    data = body["dataSets"][0]
    struct_node = body.get("structure")
    if struct_node is None:
        candidates = body.get("structures") or payload.get("structures") or []
        struct_node = candidates[0] if candidates else {}
    struct = struct_node["dimensions"]
    series_dims = struct.get("series", [])
    obs_dims = struct.get("observation", [])
    out: list[tuple[dict[str, str], float]] = []
    for series_key, series in data.get("series", {}).items():
        idx = [int(i) for i in series_key.split(":")]
        labels = {dim["id"]: dim["values"][i]["name"]
                  for dim, i in zip(series_dims, idx)}
        codes = {dim["id"] + "_CODE": dim["values"][i]["id"]
                 for dim, i in zip(series_dims, idx)}
        labels.update(codes)
        for obs_key, obs in series.get("observations", {}).items():
            if obs and obs[0] is not None:
                entry = dict(labels)
                for dim, i in zip(obs_dims, [int(x) for x in obs_key.split(":")]):
                    entry[dim["id"]] = dim["values"][i]["name"]
                    # The code, not only the label. Series dimensions were
                    # already carrying theirs and observation dimensions were
                    # not, which is where the religion classification lives --
                    # so the one thing that says which categories nest inside
                    # which never reached the code that needed it.
                    entry[dim["id"] + "_CODE"] = dim["values"][i]["id"]
                out.append((entry, float(obs[0])))
    return out


# Dimension ids differ per dataflow and were guessed wrong on the first live
# run: every LGA came back named but with no religion or ancestry attached,
# because the observations were filed under an id this code never asked for.
# Rather than guess again, the characteristic dimension is discovered.
REGION_HINTS = ("REGION", "ASGS", "LGA", "STE", "SA2")
TIME_HINTS = ("TIME", "TIME_PERIOD", "FREQ", "MEASURE", "UNIT", "OBS")
CHARACTERISTIC_HINTS = {
    "religion": ("RELIGION", "RELIGP", "RLGP", "RELIG"),
    "ancestry": ("ANCP", "ANCESTRY", "ANC"),
}


def dimension_ids(rows: list[tuple[dict[str, str], float]]) -> list[str]:
    seen: list[str] = []
    for labels, _ in rows[:50]:
        for key in labels:
            if not key.endswith("_CODE") and key not in seen:
                seen.append(key)
    return seen


def pick_dimension(rows: list[tuple[dict[str, str], float]], field: str) -> str | None:
    """Find the dimension carrying the categories, by hint then by cardinality."""
    ids = dimension_ids(rows)
    if not ids:
        return None
    for hint in CHARACTERISTIC_HINTS.get(field, ()):
        for did in ids:
            if hint in did.upper():
                return did
    # Fall back to the non-region, non-time dimension with the most distinct
    # values -- a religion or ancestry breakdown is always the widest one.
    counts: dict[str, set[str]] = {did: set() for did in ids}
    for labels, _ in rows:
        for did in ids:
            if labels.get(did):
                counts[did].add(labels[did])
    candidates = [(len(v), k) for k, v in counts.items()
                  if not any(h in k.upper() for h in REGION_HINTS + TIME_HINTS)]
    if not candidates:
        return None
    best = max(candidates)
    return best[1] if best[0] > 1 else None


def pick_region_dimension(rows: list[tuple[dict[str, str], float]]) -> str:
    for did in dimension_ids(rows):
        if any(h in did.upper() for h in REGION_HINTS):
            return did
    return "REGION"


# ABS classifications are hierarchical: "Christianity Total" is reported
# alongside its own children (Catholic, Anglican, Uniting Church...). Summing
# both levels double-counts every person, which halved every share in the first
# populated run -- Albury came out 25.4% Christian where the real figure is
# about 50%. Where "... Total" rows exist they ARE the top level, so keep only
# those, plus the not-stated rows that sit beside them.
TOTAL_SUFFIX = " total"
KEEP_ALWAYS = ("not stated", "not applicable", "inadequately described")
GRAND_TOTAL = ("total", "total persons", "total all persons", "all persons")


def strip_total(label: str) -> str:
    """"Christianity Total" is what the UI would otherwise print."""
    return label[: -len(TOTAL_SUFFIX)] if label.lower().endswith(TOTAL_SUFFIX) else label


def collapse_hierarchy(counts: dict[str, float]) -> dict[str, float]:
    """Keep one level of a hierarchical classification, never two.

    The suffix rule alone is not enough, and cost Australia 2.2 million people.
    A category with sub-levels is published as "Christianity Total" beside its
    denominations, so the marker finds it -- but Buddhism, Hinduism, Islam and
    Judaism have no sub-levels, carry no marker, and were dropped from all 565
    LGAs. The shortfall was exactly their published national totals: 2,213,332
    missing against 2,213,173 counted, a difference of 159 people.

    Kept here for the flat case and as the last fallback; `top_level` prefers
    the classification's own code tree and checks its answer against the
    published total.
    """
    totals = {k: v for k, v in counts.items() if k.lower().endswith(TOTAL_SUFFIX)}
    if not totals:
        return counts                      # flat classification (ancestry)
    kept = dict(totals)
    for label, value in counts.items():
        low = label.lower()
        if low in GRAND_TOTAL:
            continue                       # the grand total is the denominator
        if any(tag in low for tag in KEEP_ALWAYS) and label not in kept:
            kept[label] = value
    return {strip_total(k): v for k, v in kept.items()}


def outermost_by_code(coded: dict[tuple[str, str], float]) -> dict[str, float]:
    """The level of a code tree nothing else sits above.

    ABS classification codes nest by prefix and by width -- Christianity "2"
    above Anglican "2_1" -- so the outermost level is the set of shortest codes.
    This is what the suffix rule could not see: a category with no children
    looks flat, and only its code says otherwise.
    """
    codes = {code for _, code in coded if code}
    if len(codes) != len(coded):
        return {}                          # a label without a code: cannot judge
    width = min(len(c) for c in codes)
    return {strip_total(label): value for (label, code), value in coded.items()
            if len(code) == width}


def top_level(coded: dict[tuple[str, str], float], total: float | None
              ) -> tuple[dict[str, float], str]:
    """Pick a partition of the population, and let arithmetic judge it.

    Two rules disagree about what the outermost level is, and the published
    total settles it: a partition of a population sums to that population. The
    code tree is tried first because it is the classification's own statement
    of its shape; the suffix rule is the fallback for a source that publishes
    no codes, and the answer is only preferred when it actually adds up.
    """
    flat = {strip_total(label): value for (label, _), value in coded.items()
            if label.lower() not in GRAND_TOTAL}
    suffix = collapse_hierarchy(
        {label: value for (label, _), value in coded.items()})
    if not total:
        return suffix, "suffix (no total to check against)"
    for name, candidate in (("code tree", outermost_by_code(coded)),
                            ("suffix", suffix),
                            ("flat", flat)):
        if not candidate:
            continue
        # Half a percent, for the small-cell perturbation the ABS applies to
        # every published count. A level that is missing a whole category is
        # out by far more than that -- Australia's was out by 8.7%.
        if abs(sum(candidate.values()) - total) <= 0.005 * total:
            return candidate, name
    return suffix, "suffix (nothing summed to the total)"


def sole_sex_dimension(rows: list[tuple[dict[str, str], float]]) -> tuple[str, str] | None:
    """The (dimension, value) carrying both sexes, so males and females are not
    added to the persons total and counted twice."""
    for labels, _ in rows[:50]:
        for key, value in labels.items():
            if key.endswith("_CODE") or "SEX" not in key.upper():
                continue
            values = {lab.get(key) for lab, _ in rows if lab.get(key)}
            for candidate in values:
                if candidate and candidate.strip().lower() in ("persons", "total", "all persons"):
                    return key, candidate
    return None


def group_by_region(rows: list[tuple[dict[str, str], float]], label_dim: str,
                    region_dim: str = "REGION"
                    ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """The categories per region, and the persons the classification totals to.

    The total was being dropped on the floor. `collapse_hierarchy` skips it --
    correctly, since it is the denominator and not a category -- but it is also
    the only population figure this fetch ever sees, and the LGAs had none.
    """
    sex = sole_sex_dimension(rows)
    if sex:
        key, value = sex
        rows = [(lab, val) for lab, val in rows if lab.get(key) == value]
        log(f"  restricted {key}={value!r} so the sexes are not counted twice")

    # Keyed on (label, code): the code is what says whether a category sits
    # under another one, and keying on the label alone threw it away before
    # anything could ask.
    out: dict[str, dict[tuple[str, str], float]] = {}
    for labels, value in rows:
        region = labels.get(region_dim + "_CODE") or labels.get(region_dim)
        label = labels.get(label_dim)
        if not region or not label:
            continue
        key = (label, labels.get(label_dim + "_CODE") or "")
        out.setdefault(region, {})[key] = out.setdefault(region, {}).get(key, 0.0) + value

    grouped: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    picked: dict[str, int] = {}
    for region, counts in out.items():
        published = next((v for (label, _), v in counts.items()
                          if label.strip().lower() in GRAND_TOTAL), None)
        kept, how = top_level(counts, published)
        picked[how] = picked.get(how, 0) + 1
        grouped[region] = kept
        # The table's own total where it publishes one. Otherwise the collapsed
        # categories' sum, which partitions the population for religion because
        # "not stated" is one of them -- but not for a multi-response
        # classification, which is why only religion's total is used below.
        totals[region] = published if published is not None else sum(kept.values())
    for how, n in sorted(picked.items(), key=lambda kv: -kv[1]):
        log(f"  outermost level chosen by {how} for {n} regions")
    return grouped, totals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="state", choices=list(REGION_TYPE))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    suffix = REGION_TYPE[args.level]
    log(f"abs: 2021 Census, {suffix}")
    flows = discover_dataflows(suffix)
    if not flows:
        log("  no matching dataflows; nothing to fetch")
        return 1
    religion_rows = unpack(sdmx(flows["religion"])) if "religion" in flows else []
    ancestry_rows = unpack(sdmx(flows["ancestry"])) if "ancestry" in flows else []

    log(f"  religion rows {len(religion_rows)}, ancestry rows {len(ancestry_rows)}")
    log(f"  dimensions seen: {dimension_ids(religion_rows or ancestry_rows)}")

    region_dim = (REGION_DIMENSION.get(args.level)
                  or pick_region_dimension(religion_rows or ancestry_rows))
    religion_dim = pick_dimension(religion_rows, "religion")
    ancestry_dim = pick_dimension(ancestry_rows, "ancestry")
    log(f"  using region={region_dim!r} religion={religion_dim!r} ancestry={ancestry_dim!r}")

    religion, persons = (group_by_region(religion_rows, religion_dim, region_dim)
                         if religion_dim else ({}, {}))
    # Ancestry's total counts responses, not people -- up to two per person --
    # so it is never a population and is discarded here.
    ancestry, _ = (group_by_region(ancestry_rows, ancestry_dim, region_dim)
                   if ancestry_dim else ({}, {}))
    if religion_rows and not religion:
        log("  ! religion rows returned but none grouped -- dimension detection failed")

    names = {}
    for labels, _ in religion_rows + ancestry_rows:
        code = labels.get(region_dim + "_CODE") or labels.get(region_dim)
        if code:
            names.setdefault(code, labels.get(region_dim, code))

    if persons:
        log(f"  population from the religion table's own total for "
            f"{sum(1 for v in persons.values() if v)} of {len(persons)} regions; "
            f"they sum to {sum(persons.values()):,.0f}")
    if religion:
        sample = next(iter(religion.values()))
        biggest = max(sample.values()) if sample else 0
        total = sum(sample.values()) or 1
        log(f"  sanity: largest religion category is {100 * biggest / total:.1f}% of the "
            f"sample region's total across {len(sample)} categories")

    src = "Australian Bureau of Statistics, Census of Population and Housing 2021"
    records: list[dict[str, Any]] = []
    for code in sorted(set(religion) | set(ancestry)):
        rel = {k: v for k, v in religion.get(code, {}).items() if not k.lower().startswith("total")}
        anc = {k: v for k, v in ancestry.get(code, {}).items() if not k.lower().startswith("total")}
        records.append(record(
            f"AUS-{code}", names.get(code, code),
            level="admin1" if args.level == "state" else "admin2",
            parent="AUS", codes={"asgs": code, "asgs_level": ASGS_LEVEL[args.level]},
            population=(measure(int(round(persons[code])), year=2021, source=src)
                        if persons.get(code) else gap(NOT_AVAILABLE)),
            religion=shares(rel) or gap(NOT_AVAILABLE),
            religion_note="ABS 2021 religious affiliation; the question is voluntary and "
                          "'not stated' is retained as its own category.",
            ancestry=shares(anc) or gap(NOT_AVAILABLE),
            ancestry_note="ABS ancestry is multi-response (up to two per person), so shares "
                          "are of responses and sum above 100%.",
            ethnicity=gap(NOT_COLLECTED,
                          "Australia's census does not ask ethnicity. It asks ancestry and "
                          "country of birth, plus a separate Aboriginal and Torres Strait "
                          "Islander status question."),
            sources=[{"field": "population/religion/ancestry", "name": src,
                      "url": "https://data.api.abs.gov.au/",
                      "license": "CC BY 4.0"}],
        ))
    # Australia has eight states and territories. A "state" run that comes back
    # with fifty-three of something is not a state run, and the last one wrote
    # remoteness areas into the file the build reads as admin-1.
    if args.level == "state" and not 5 <= len(records) <= 12:
        log(f"  ! {len(records)} records for --level state; Australia has 8 states "
            f"and territories. Refusing to write: {[r['name'] for r in records[:6]]}")
        return 1

    write_json(args.out or PROCESSED / f"australia_{args.level}.json", records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
