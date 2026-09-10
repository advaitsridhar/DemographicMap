#!/usr/bin/env python3
"""Australia -- ABS Data API (SDMX-JSON), 2021 Census, states and SA3/LGA.

The ABS Data API serves census tables as SDMX-JSON dataflows.  This pulls:

* ``C21_G14_LGA`` religious affiliation
* ``C21_G08_LGA`` ancestry (multi-response: people may report two ancestries,
  so shares sum above 100% and are labelled as responses, not persons)
* ``C21_G13_LGA`` language used at home, cross-tabulated with proficiency in
  spoken English and sex; the total of both is read, so it is one answer per
  person and partitions the population

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
DATAFLOW_HINTS = {"religion": "C21_G14_{r}", "ancestry": "C21_G08_{r}",
                  "language": "C21_G13_{r}"}


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
    for table in ("G14", "G08", "G13"):
        ids = sorted(f[0] for f in flows if table in f[0].upper())
        if ids:
            log(f"  dataflows containing {table}: " + ", ".join(ids[:40]))

    out: dict[str, tuple[str, str, str]] = {}
    table_of = {"religion": "G14", "ancestry": "G08", "language": "G13"}
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
    "language": ("LANP", "LANGUAGE", "LANG"),
}
# G13 carries a third dimension, proficiency in spoken English, beside sex.
# A cross-tabulation summed over every cell counts each person once per
# proficiency category as well as once per sex; only the total of each
# extra dimension is a count of people.
TOTAL_VALUES = ("persons", "total", "all persons", "total persons")
# G13's one English category is worded as a behaviour; the chart names a
# language, so it is renamed to sit beside the others.
LANGUAGE_LABELS = {"Speaks English only": "English only"}


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
    """"Christianity Total" is what the UI would otherwise print.

    G13 writes its families as "Chinese: Total", so the colon goes too.
    """
    if label.lower().endswith(TOTAL_SUFFIX):
        label = label[: -len(TOTAL_SUFFIX)]
    return label.rstrip(": ")


def without_duplicated_parent(candidate: dict[str, float], total: float,
                              tolerance: float, groups: set[str]) -> dict[str, float]:
    """Drop the one marked group whose children are also in the set.

    G13 lists "Other Languages Total" beside every language under it, and its
    code, "O_T", is no prefix of "3103" Italian or "52" Indo-Aryan, so the
    code tree cannot see that it is their parent. Arithmetic can: the set
    over-counts the published total by that one row. Only a category the ABS
    marks "... Total" is tried, and the one whose removal lands nearest the
    total is taken -- by the same tolerance the rest of this module uses,
    because the parent's own value and its children's sum differ by the
    perturbation of every cell: in an LGA of 524 people the group read 96 and
    its children 83, and a band on the parent's value found nothing.
    """
    excess = sum(candidate.values()) - total
    if excess <= tolerance:
        return candidate
    best: tuple[float, str] | None = None
    for label in groups:
        if label not in candidate:
            continue
        miss = abs(sum(candidate.values()) - candidate[label] - total)
        if miss <= tolerance and (best is None or miss < best[0]):
            best = (miss, label)
    if best is None:
        return candidate
    return {k: v for k, v in candidate.items() if k != best[1]}


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


# A code ending in the total marker stands for the branch itself rather than a
# category beneath it: "7_T" is the Secular branch, and its children are "7101",
# "7102" and so on -- numbered from "7", not from "7_T". Stripping the marker is
# what makes a parent a prefix of its own children.
CODE_TOTAL_SUFFIX = "_T"
# A parent the codes and the marker both miss. G13's "Other" (code _O)
# holds "Australian Indigenous Languages" (code 8): in the Northern
# Territory the two read 40,850 and 36,082 and the block summed only with
# the second inside the first, and the same in every LGA where both are
# non-zero. Declared, because no rule could see it.
CHILDREN_OF = {"_O": ("8",)}


def branch_code(code: str) -> str:
    return code[: -len(CODE_TOTAL_SUFFIX)] if code.endswith(CODE_TOTAL_SUFFIX) else code


def outermost_by_code(coded: dict[tuple[str, str], float]) -> dict[str, float]:
    """The level of a code tree nothing else sits above.

    ABS classification codes nest by prefix, and not by width -- the real tree
    is "1" Buddhism, "2" Christianity Total, "6_T" Other Religions Total, "_N"
    not stated, with "207" Catholic under "2" and "7101" No Religion under
    "7_T". A rule that kept the shortest codes would have thrown away every
    branch whose code carries the marker, and one that ignored the marker would
    have kept "7101" beside its own parent.

    So: a category is outermost when no other category's branch code is a
    proper prefix of its own. Buddhism has no children and no marker, and this
    is the only rule that sees it -- which is the whole point, because it and
    Hinduism, Islam and Judaism were being dropped from all 565 LGAs.
    """
    # The grand total is nobody's parent. Its code is "_T", which the marker
    # strip turns into the empty string -- a prefix of every code there is, so
    # leaving it in excluded every category and returned nothing at all.
    codes = {code for (label, code) in coded
             if code and label.strip().lower() not in GRAND_TOTAL}
    if not codes:
        return {}                          # no codes: nothing to judge with
    # Only a category the ABS marks as a group can be a parent. G13 codes
    # "Speaks English only" as "1", and "1" is a prefix of "1403" Afrikaans
    # -- a language it has nothing to do with -- so 109 LGAs lost Afrikaans,
    # Dutch and Norwegian to a parent that is no parent, and none of them
    # then summed. Every real group in these tables is written "... Total".
    branches = {b for b in (branch_code(code) for (label, code) in coded
                            if code and label.lower().endswith(TOTAL_SUFFIX)) if b}
    hidden = {child for parent, children in CHILDREN_OF.items() if parent in codes
              for child in children}
    out: dict[str, float] = {}
    for (label, code), value in coded.items():
        if not code or label.strip().lower() in GRAND_TOTAL:
            continue
        mine = branch_code(code)
        if code in hidden:
            continue                       # a declared child of a present code
        if any(mine != other and mine.startswith(other) for other in branches):
            continue                       # something sits above it
        out[strip_total(label)] = out.get(strip_total(label), 0.0) + value
    return out


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
        # The ABS perturbs every published count to protect small cells, and
        # that perturbation is an absolute number of people rather than a
        # proportion -- so a proportional tolerance alone fails exactly the
        # regions the perturbation matters most in. Leonora, population 1,588,
        # came out 53 people short and fell back to the marker rule; so did 47
        # other LGAs, none of them above 2,520 people, and none out by more
        # than 53. A level that is missing a whole category is out by far more
        # than either bound -- Australia's was out by 8.7%, 2.2 million people.
        tolerance = max(0.005 * total, 60)
        if abs(sum(candidate.values()) - total) <= tolerance:
            return candidate, name
        if name != "code tree":
            continue                       # only where the structure is known
        groups = {strip_total(label) for (label, _) in coded
                  if label.lower().endswith(TOTAL_SUFFIX)}
        trimmed = without_duplicated_parent(candidate, total, tolerance, groups)
        if trimmed is not candidate and abs(sum(trimmed.values()) - total) <= tolerance:
            return trimmed, f"{name} less a duplicated parent"
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


def restrict_extra_dimensions(rows: list[tuple[dict[str, str], float]],
                              keep: tuple[str, ...]
                              ) -> list[tuple[dict[str, str], float]]:
    """Keep only the Total of every dimension that is not the region, the
    characteristic or time. G13's proficiency-in-English dimension is why:
    without this, every language was counted once per proficiency level and
    the shares summed to several hundred percent."""
    for did in dimension_ids(rows):
        if did in keep or any(h in did.upper() for h in REGION_HINTS + TIME_HINTS):
            continue
        values = {lab.get(did) for lab, _ in rows if lab.get(did)}
        if len(values) < 2:
            continue
        total = next((v for v in values if v.strip().lower() in TOTAL_VALUES), None)
        if total is None:
            continue
        rows = [(lab, val) for lab, val in rows if lab.get(did) == total]
        log(f"  restricted {did}={total!r} so its categories are not summed")
    return rows


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
    rows = restrict_extra_dimensions(rows, (label_dim, region_dim))

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
    # When no rule adds up, the categories themselves are the diagnosis, and a
    # log that only reports the verdict makes the next run a guess. One region
    # per verdict is enough to show the shape of the classification -- and
    # one per verdict rather than one per run, because 109 LGAs fell to the
    # suffix rule for language while 354 did not, and the run's log showed
    # neither what they looked like nor why.
    shown: set[str] = set()
    for region, counts in out.items():
        published = next((v for (label, _), v in counts.items()
                          if label.strip().lower() in GRAND_TOTAL), None)
        _, how = top_level(counts, published)
        if how.startswith("code tree") or how in shown:
            continue
        shown.add(how)
        log(f"  ! {how}: {label_dim} for region {region}; published total {published}")
        for (label, code), value in sorted(counts.items(), key=lambda kv: -kv[1])[:28]:
            log(f"      {code!r:>10}  {value:>12,.0f}  {label}")
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
    language_rows = unpack(sdmx(flows["language"])) if "language" in flows else []

    log(f"  religion rows {len(religion_rows)}, ancestry rows {len(ancestry_rows)}, "
        f"language rows {len(language_rows)}")
    log(f"  dimensions seen: {dimension_ids(religion_rows or ancestry_rows)}")

    region_dim = (REGION_DIMENSION.get(args.level)
                  or pick_region_dimension(religion_rows or ancestry_rows))
    religion_dim = pick_dimension(religion_rows, "religion")
    ancestry_dim = pick_dimension(ancestry_rows, "ancestry")
    language_dim = pick_dimension(language_rows, "language")
    log(f"  using region={region_dim!r} religion={religion_dim!r} "
        f"ancestry={ancestry_dim!r} language={language_dim!r}")

    religion, persons = (group_by_region(religion_rows, religion_dim, region_dim)
                         if religion_dim else ({}, {}))
    # Ancestry's total counts responses, not people -- up to two per person --
    # so it is never a population and is discarded here.
    ancestry, _ = (group_by_region(ancestry_rows, ancestry_dim, region_dim)
                   if ancestry_dim else ({}, {}))
    language, _ = (group_by_region(language_rows, language_dim, region_dim)
                   if language_dim else ({}, {}))
    if religion_rows and not religion:
        log("  ! religion rows returned but none grouped -- dimension detection failed")
    if language_rows and not language:
        log("  ! language rows returned but none grouped -- dimension detection failed")

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
    for code in sorted(set(religion) | set(ancestry) | set(language)):
        rel = {k: v for k, v in religion.get(code, {}).items() if not k.lower().startswith("total")}
        anc = {k: v for k, v in ancestry.get(code, {}).items() if not k.lower().startswith("total")}
        lan = {LANGUAGE_LABELS.get(k, k): v for k, v in language.get(code, {}).items()
               if not k.lower().startswith("total")}
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
            language=shares(lan) or gap(NOT_AVAILABLE),
            language_note="ABS 2021 language used at home (G13), one answer per person, "
                          "at the outermost level of the ABS classification; 'not stated' "
                          "is retained as its own category.",
            ethnicity=gap(NOT_COLLECTED,
                          "Australia's census does not ask ethnicity. It asks ancestry and "
                          "country of birth, plus a separate Aboriginal and Torres Strait "
                          "Islander status question."),
            sources=[{"field": "population/religion/ancestry/language", "name": src,
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
