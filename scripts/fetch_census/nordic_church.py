#!/usr/bin/env python3
"""Religion from the Church of Sweden's own membership count, for Sweden's kommuner.

Sweden's census is compiled from registers, and no state register has recorded
religion since the Church of Sweden separated from the state in 2000; SCB
publishes no religion table. What the Church publishes is its own membership by
parish, kommun and län, against the population of the same day -- both columns
produced by Statistics Sweden on the Church's commission, as the table's first
page says. The gap round's brief allows exactly that where the statistics
office publishes nothing: the Church's members against everyone else, with the
official population as the denominator, a count of membership and not of
belief, said so in every note.

The table is "Medlemmar i Svenska kyrkan i förhållande till folkmängd den
31.12.2021 per församling, kommun och län samt riket" (``NyckeltalLKF(1).pdf``
in the Church's statistics folder), the latest edition by kommun: the Church's
statistics page lists national series only since, the folder holds no later
edition under any name the Wayback Machine has seen, and Kolada carries no
membership figure (church_probe rounds c1-c3). The 290 kommuner have not changed
since 2003; they are bound by SCB's codes, as ``sweden.py`` binds them.

Forshaga and Munkfors are left out. Their one parish, Forshaga-Munkfors
församling (176301), spans both, and the table counts it whole under one of
them (Munkfors in 2018-2020, Forshaga in 2016 and 2021), so neither kommun's own
membership is published in any edition since 2016 (church_probe round c4). A
share of the two together is not either one's; the SWE policy says why the two
are blank.

The län are not written: the European Social Survey gives each a fuller
composition -- no religion, the Church, Islam, Catholics, Orthodox -- which a
two-row count would displace, since a count outranks a survey. Finland is read
from its population register instead (``finland_religion.py``), which counts
every community and beats any one church's figures.

Labels: "Church of Sweden" and "Not a member of the national church", as
Denmark's register rows read; the group tree files the second with the
answers that name no religion.

Checks: every row is read with its own percentage; the kommuner make their
län and the län with the people registered without a property make the
country's row, population and members; the country's population is SCB's of
the same day and each kommun's within a few per cent of SCB's (the table leaves
out the people SCB cannot place in a parish); every kommun is bound one to one.

Usage:
    python -m scripts.fetch_census.nordic_church --country SWE
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import request, request_json, unplaced
from .pxweb import unstack

BASIS = "registered membership"

SVK_URLS = (
    "https://www.svenskakyrkan.se/filer/1374643/NyckeltalLKF(1).pdf",
    "https://web.archive.org/web/20220401215825id_/https://www.svenskakyrkan.se/filer/1374643/"
    "NyckeltalLKF(1).pdf",
)
SVK_PAGE = "https://www.svenskakyrkan.se/statistik"
SVK_YEAR = 2021
SVK_TITLE = "Medlemmar i Svenska kyrkan i förhållande till folkmängd den 31.12.2021"
SWEDEN_CHURCH = "Church of Sweden"
SWEDEN_OUTSIDE = "Not a member of the national church"
# Each row prints two shares after its counts: the residents who are members
# of the Church, in whatever parish ("Folkbokförda medlemmar inom
# församlingen i % av folkmängden"), and the members of its own parishes
# against its population ("Medlemmar i församlingen i % av folkmängden") --
# the second is the counts' own ratio, rounded. They differ only where a
# parish without territory counts members who live elsewhere (Karlskrona's
# admiralty parish: 66.0% against 66.1%). The split of the counts must match
# the second to rounding, or the first within PCT_SLACK when only it is printed.
RATIO_SLACK = 0.06
PCT_SLACK = 0.6
ROW = re.compile(r"^(?P<name>.+?) (?P<kind>kommun|län)(?: \(\d+\))? (?P<rest>\d.*)$")
RIKET = re.compile(r"^Riket (?P<rest>\d.*)$")
UNPLACED = "På kommunen skrivna "
UNKNOWN_NAME = "Okänd"
# The table prints the people without a property twice -- as the parish "På
# kommunen skrivna" and as the kommun "Okänd" that holds it -- and the 2021
# edition's two rows differ by two members (5,935 against 5,933). The
# country's members are allowed that much against the län and the kommun.
MEMBER_SLACK = 10
# A kommun row is the sum of the parishes coded to it, against SCB's count by
# kommun: they differ by the people registered without a property, and where
# a parish crosses a kommun boundary.
KOMMUN_SLACK = 0.03


def numbers(groups: list[str]) -> int | None:
    """Digit groups printed with a space for the thousands -> the number, or
    None if they cannot be one ("027" opening a number, a short inner group)."""
    if not groups or any(not g.isdigit() for g in groups):
        return None
    if len(groups[0]) > 3 or (len(groups) > 1 and groups[0].startswith("0")):
        return None
    if any(len(g) != 3 for g in groups[1:]):
        return None
    return int("".join(groups))


def percent(token: str) -> float | None:
    """'71,8%' -> 71.8; the national row of some editions prints two decimals."""
    found = re.fullmatch(r"(\d+),(\d{1,2})%", token)
    return float(f"{found.group(1)}.{found.group(2)}") if found else None


def population_and_members(rest: str) -> tuple[int, int, float]:
    """The first two numbers of a row, told apart by the shares printed after
    them, and the first share: the residents who are members, in whatever parish.

    The table prints thousands with a space, so "556 399 71,8%" could be one
    number or two; it is the split whose members-over-population matches the
    printed ratio, members never more than the population. Anything but one
    such split stops the run. A leading code in brackets is passed over."""
    tokens = re.sub(r"^\(\d+\)\s+", "", rest).split()
    groups = []
    for token in tokens:
        if not re.fullmatch(r"\d{1,3}", token):
            break
        groups.append(token)
    shares_ = [percent(t) for t in tokens[len(groups):len(groups) + 2]]
    if not shares_ or shares_[0] is None:
        raise SystemExit(f"svenska kyrkan: no share after the counts in {rest[:80]!r}")
    residents = shares_[0]
    ratio, slack = ((shares_[1], RATIO_SLACK) if len(shares_) > 1 and shares_[1] is not None
                    else (residents, PCT_SLACK))
    fits = []
    for i in range(1, len(groups)):
        pop, members = numbers(groups[:i]), numbers(groups[i:])
        if pop and members is not None and members <= pop \
                and abs(100 * members / pop - ratio) <= slack:
            fits.append((pop, members))
    if len(fits) != 1:
        raise SystemExit(f"svenska kyrkan: {len(fits)} readings of {rest[:80]!r}: {fits}")
    return fits[0][0], fits[0][1], residents


Row = tuple[int, int, float]


def svk_rows(lines: list[str]) -> tuple[dict[str, Row], dict[str, Row], Row | None]:
    """{kommun: (population, members, residents' share)}, {län: ...} and the
    row of people registered in a kommun without a property ("På kommunen
    skrivna"), which the table prints once, for the whole country."""
    kommuner: dict[str, Row] = {}
    lan: dict[str, Row] = {}
    unplaced_row = None
    for line in lines:
        line = " ".join(line.split())
        if line.startswith(UNPLACED):
            if unplaced_row is not None:
                raise SystemExit("svenska kyrkan: two rows of people without a property")
            unplaced_row = population_and_members(line[len(UNPLACED):])
            continue
        found = ROW.match(line)
        if not found or "församling" in found.group("name"):
            continue
        target = kommuner if found.group("kind") == "kommun" else lan
        name = found.group("name")
        if name in target:
            raise SystemExit(f"svenska kyrkan: {name} {found.group('kind')} twice")
        target[name] = population_and_members(found.group("rest"))
    return kommuner, lan, unplaced_row


def riket_row(lines: list[str]) -> Row:
    """The country's row ("Riket"), which must be printed exactly once."""
    found = [RIKET.match(" ".join(line.split())) for line in lines]
    rows = [population_and_members(m.group("rest")) for m in found if m]
    if len(rows) != 1:
        raise SystemExit(f"svenska kyrkan: {len(rows)} rows for the whole country")
    return rows[0]


def check_country(lan: dict[str, Row], unknown: Row, riket: Row) -> None:
    """The län with the people registered without a property make the
    country's row: its population exactly, its members to MEMBER_SLACK."""
    people = sum(r[0] for r in lan.values()) + unknown[0]
    members = sum(r[1] for r in lan.values()) + unknown[1]
    if people != riket[0] or abs(members - riket[1]) > MEMBER_SLACK:
        raise SystemExit(f"svenska kyrkan: the län and the unplaced make {people:,} people and "
                         f"{members:,} members; the country's row {riket[0]:,} and {riket[1]:,}")


def match_names(printed: list[str], scb: dict[str, str]) -> dict[str, str]:
    """The table's genitive names ("Karlshamns", "Faluns", "Borås") -> SCB's
    codes: the name as printed, else without its genitive s; each as spelled
    before it is folded, since folding makes Håbo and Habo one name. One to
    one, or the run stops."""
    exact = {n: c for c, n in scb.items()}
    folded: dict[str, set[str]] = defaultdict(set)
    for c, n in scb.items():
        folded[fold(n)].add(c)

    def find(name: str) -> str | None:
        if name in exact:
            return exact[name]
        hits = folded.get(fold(name), set())
        return next(iter(hits)) if len(hits) == 1 else None

    out, missing = {}, []
    for name in printed:
        code = find(name)
        if code is None and name.endswith("s"):
            code = find(name[:-1])
        if code is None:
            missing.append(name)
        else:
            out[name] = code
    twice = sorted({c for c in out.values() if list(out.values()).count(c) > 1})
    if missing or twice:
        raise SystemExit(f"svenska kyrkan: no SCB code for {missing}; codes twice {twice}")
    return out


PARISH = re.compile(r"^(?P<name>.+?) församling \((?P<code>\d{6})\)")


def joined_kommuner(unread: list[str], read: set[str], names: dict[str, str],
                    lines: list[str]) -> dict[str, tuple[str, str]]:
    """Kommuner the table prints no row for -> (the kommun whose row holds
    them, the parish that joins them).

    A parish that spans two kommuner (Forshaga-Munkfors församling) is counted
    whole under the kommun its code places it in, and the other kommun gets
    no row. It is found by a parish row naming the missing kommun in its
    hyphenated name; a missing kommun no one such parish explains stops the
    run."""
    out: dict[str, tuple[str, str]] = {}
    for code in unread:
        hosts = set()
        for line in lines:
            found = PARISH.match(" ".join(line.split()))
            if found and fold(names[code]) in {fold(p) for p in found.group("name").split("-")}:
                hosts.add((found.group("code")[:4], found.group("name")))
        hosts = {(h, parish) for h, parish in hosts if h != code}
        if len(hosts) != 1 or next(iter(hosts))[0] not in read:
            raise SystemExit(f"svenska kyrkan: no row for {names[code]} ({code}), and no one "
                             f"parish places it in another kommun's: {sorted(hosts)}")
        out[code] = next(iter(hosts))
    return out


def lan_codes(lan: list[str], sv: dict[str, str]) -> dict[str, str]:
    """The table's län names ("Stockholms", "Kalmars") -> SCB's two-digit codes,
    one to one for all 21, or the run stops."""
    out = {name: next((c for c, n in sv.items() if len(c) == 2 and c != "00" and
                       fold(n.removesuffix(" län").rstrip("s")) == fold(name.rstrip("s"))),
                      None) for name in lan}
    if None in out.values() or len(set(out.values())) != 21 or len(out) != 21:
        raise SystemExit(f"svenska kyrkan: län not matched: {out}")
    return out


def check_lan(kommuner: dict[str, Row], lan: dict[str, Row], code_of: dict[str, str],
              lan_code: dict[str, str]) -> None:
    """Each län's kommuner make its row, population and members, exactly."""
    for name, code in lan_code.items():
        parts = [kommuner[k] for k, c in code_of.items() if c[:2] == code]
        for i, what in ((0, "population"), (1, "members")):
            if sum(p[i] for p in parts) != lan[name][i]:
                raise SystemExit(f"svenska kyrkan: {name}'s kommuner make "
                                 f"{sum(p[i] for p in parts):,} {what} of {lan[name][i]:,}")


def kommun_record(name: str, code: str, row: Row, sv: dict[str, str], shape_id: str,
                  source: dict[str, Any]) -> dict[str, Any]:
    pop, members, residents = row
    elsewhere = (f" Of the kommun's residents, {residents:.1f}% are members, in whatever "
                 "parish; the count above is of the members of its own parishes, wherever "
                 "they live -- the two differ where a parish without territory (Karlskrona's "
                 "admiralty parish) has members in more than one kommun."
                 if abs(residents - 100 * members / pop) >= 0.15 else "")
    return record(
        f"SWE-SVK-{code}", sv[code], level="admin2", parent="SWE", country="SWE",
        parent_name=sv[code[:2]], codes={"scb": code}, match_by="shape_id", shape_id=shape_id,
        religion=shares({SWEDEN_CHURCH: members, SWEDEN_OUTSIDE: pop - members}, total=pop),
        religion_year=SVK_YEAR, religion_basis=BASIS,
        religion_note=(
            f"Members of the Church of Sweden on 31 December {SVK_YEAR} against the kommun's "
            f"population the same day, {members:,} of {pop:,}, both counted by Statistics "
            "Sweden for the Church (Svenska kyrkan, 'Medlemmar i Svenska kyrkan i förhållande "
            f"till folkmängd den 31.12.{SVK_YEAR} per församling, kommun och län samt riket', "
            "the latest edition by kommun): the Church's registered membership, not belief. "
            "Everyone else -- members of other faiths and of none alike -- is one group: no "
            "state register records religion, and the Church's is the only membership count "
            "published by kommun. The population leaves out the few people registered in the "
            "kommun without a property, whom SCB cannot place in a parish." + elsewhere),
        sources=[source])


def sweden() -> list[dict[str, Any]]:
    import pdfplumber
    from .sweden import BASE, bind_kommuner
    raw, used = None, None
    for url in SVK_URLS:
        try:
            raw = request(url, accept="application/pdf,*/*", attempts=3)
        except (SystemExit, Exception) as exc:
            log(f"  {url}: {str(exc)[:120]}")
            continue
        if raw.startswith(b"%PDF"):
            used = url
            break
    if not used:
        raise SystemExit("svenska kyrkan: no copy of the table answered")
    with pdfplumber.open(io.BytesIO(raw)) as doc:
        lines = [line for page in doc.pages for line in (page.extract_text() or "").splitlines()]
    if not any(SVK_TITLE in " ".join(line.split()) for line in lines[:5]):
        raise SystemExit(f"svenska kyrkan: {used} is not the {SVK_YEAR} table: {lines[:2]}")
    kommuner, lan, nowhere = svk_rows(lines)
    riket = riket_row(lines)
    # The people SCB cannot place in a parish are printed as a parish of their
    # own ("På kommunen skrivna") of a kommun called "Okänd" (unknown): one
    # count, set aside from the kommuner and the län.
    unknown = [rows.pop(UNKNOWN_NAME) for rows in (lan, kommuner) if UNKNOWN_NAME in rows]
    if len(unknown) != 1:
        raise SystemExit(f"svenska kyrkan: {len(unknown)} rows for '{UNKNOWN_NAME}'")
    log(f"  {used}: {len(lines):,} lines, {len(kommuner)} kommuner, {len(lan)} län; the "
        f"country {riket}; registered without a property {nowhere}, as '{UNKNOWN_NAME}' "
        f"{unknown[0]}")
    check_country(lan, unknown[0], riket)
    meta = {v["code"]: v for v in request_json(BASE.format(lang="sv", table="BefolkningNy"))
            ["variables"]}
    sv = dict(zip(meta["Region"]["values"], meta["Region"]["valueTexts"]))
    scb_kommuner = {c: n for c, n in sv.items() if len(c) == 4}
    code_of = match_names(list(kommuner), scb_kommuner)
    read = set(code_of.values())
    joined = joined_kommuner(sorted(set(scb_kommuner) - read), read, scb_kommuner, lines)
    partners: dict[str, list[str]] = defaultdict(list)
    for code, (host, parish) in sorted(joined.items()):
        partners[host].append(code)
    lan_code = lan_codes(list(lan), sv)
    check_lan(kommuner, lan, code_of, lan_code)
    log(f"  the kommuner make their län, and the län with the unplaced the country: "
        f"{riket[0]:,} people, {riket[1]:,} members")
    # SCB's own count of the same day: the table's kommun populations leave
    # out only the people SCB cannot place on a property, and move a parish
    # across a kommun boundary whole.
    scb = scb_population()
    if abs(riket[0] - scb["00"]) > 0.0005 * scb["00"]:
        raise SystemExit(f"svenska kyrkan: the country's row counts {riket[0]:,} people, SCB "
                         f"{scb['00']:,.0f}")

    def scb_of(code: str) -> float:
        return scb[code] + sum(scb[c] for c in partners.get(code, []))

    off = sorted(((scb_of(c) - kommuner[k][0]) / scb_of(c), k) for k, c in code_of.items())
    log(f"  the country's row against SCB's {scb['00']:,.0f}: {riket[0] - scb['00']:+,.0f}; "
        f"kommun rows against SCB's: from {100 * off[0][0]:+.2f}% ({off[0][1]}) to "
        f"{100 * off[-1][0]:+.2f}% ({off[-1][1]}); "
        f"{sum(1 for d, _ in off if abs(d) > 0.005)} beyond 0.5%: "
        + ", ".join(f"{k} {100 * d:+.2f}%" for d, k in off if abs(d) > 0.005))
    if max(abs(d) for d, _ in off) > KOMMUN_SLACK:
        worst = max(off, key=lambda dk: abs(dk[0]))
        raise SystemExit(f"svenska kyrkan: {worst[1]} is {100 * worst[0]:+.1f}% off SCB's count")
    bound = bind_kommuner(sv, sorted(scb_kommuner))
    source = {"field": "religion", "name": "Church of Sweden (Svenska kyrkan), members against "
              f"population 31 December {SVK_YEAR}, counted by SCB", "url": used,
              "year": SVK_YEAR}
    records = []
    for name, code in sorted(code_of.items(), key=lambda kv: kv[1]):
        if code in partners:
            together = [code] + partners[code]
            pop, members, _ = kommuners_row = kommuner[name]
            log(f"  left out: {' and '.join(sv[c] for c in together)}, whose one parish "
                f"({joined[partners[code][0]][1]} församling) the table counts whole under "
                f"{sv[code]}: {members:,} members of {pop:,} together ({kommuners_row[2]}%)")
            continue
        records.append(kommun_record(name, code, kommuner[name], sv, bound[code], source))
    return records


def scb_population() -> dict[str, float]:
    """SCB's register population on 31 December of SVK_YEAR, by region."""
    from .sweden import BASE
    url = BASE.format(lang="en", table="BefolkningNy")
    meta = {v["code"]: v for v in request_json(url)["variables"]}
    content = next(c for c in meta["ContentsCode"]["values"])
    body = request_json(url, {"query": [
        {"code": "Region", "selection": {"filter": "item", "values": meta["Region"]["values"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [content]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [str(SVK_YEAR)]}},
    ], "response": {"format": "json-stat2"}})
    out: dict[str, float] = defaultdict(float)
    for key, value in unstack(body):
        out[key["Region"][0]] += value
    return dict(out)


READERS = {"SWE": (sweden, "sweden_church.json")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True, choices=sorted(READERS))
    args = ap.parse_args()
    reader, out = READERS[args.country]
    log(f"nordic_church: {args.country}")
    records = reader()
    labels = {g["group"] for r in records for g in r.get("religion") or []
              if isinstance(r.get("religion"), list)}
    log(f"  {len(records)} records; religion labels the group tree cannot place: "
        f"{unplaced('religion', labels) or 'none'}")
    write_json(PROCESSED / out, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
