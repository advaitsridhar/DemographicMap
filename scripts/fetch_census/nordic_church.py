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

**A kommun row is its parishes, not always its territory.** The table sums
each kommun's parishes, and a parish that crosses a kommun boundary is counted
whole under one kommun: in 2021 Gullspång's row holds 42% fewer people than SCB
counts in Gullspång and Töreboda's 23% more, and seventeen other rows are more
than half a per cent off. A row that is another territory is not the kommun's
figure. So each kommun takes the newest of the 2021, 2020 and 2019 editions in
which its row is within KOMMUN_TOLERANCE of SCB's count of the kommun on the
same day -- the people registered without a property, whom the table sets
apart, never make more than half a per cent -- and a kommun with no such
edition is left out and named in the log. Forshaga and Munkfors are always out:
their one parish, Forshaga-Munkfors församling (176301), is counted whole under
one of the two in every edition since 2016 (church_probe round c4).

The län are not written: the European Social Survey gives each a fuller
composition -- no religion, the Church, Islam, Catholics, Orthodox -- which a
two-row count would displace, since a count outranks a survey. Finland is read
from its population register instead (``finland_religion.py``), which counts
every community and beats any one church's figures.

Labels: "Church of Sweden" and "Not a member of the national church", as
Denmark's register rows read; the group tree files the second with the
answers that name no religion.

Checks, in every edition read: every row is read with its own percentage; the
kommuner make their län and the län with the people registered without a
property make the country's row, population and members; the country's
population is SCB's of the same day; every kommun written has a row within
KOMMUN_TOLERANCE of SCB's count of it; every kommun is bound one to one.

Usage:
    python -m scripts.fetch_census.nordic_church --country SWE
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import request, request_json, unplaced
from .pxweb import unstack

BASIS = "registered membership"

SVK = "https://www.svenskakyrkan.se/filer/1374643/"
WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"
LKF_2020 = ("Medlemmar%20i%20Svenska%20kyrkan%20i%20forhallande%20till%20folkmangd%2031%20"
            "december%202020%20per%20forsamling,%20kommun%20och%20lan%20samt%20riket%20(pdf).pdf")
# The editions read, newest first, each with the copies to try: the file names
# are the Church's own, which it reuses ("NyckeltalLKF.pdf" holds 2019's), so
# every copy is checked by the title on its first page.
EDITIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (2021, (SVK + "NyckeltalLKF(1).pdf",
            WAYBACK.format(ts="20220401215825", url=SVK + "NyckeltalLKF(1).pdf"))),
    (2020, (SVK + LKF_2020, WAYBACK.format(ts="20220120151620", url=SVK + LKF_2020))),
    (2019, (SVK + "NyckeltalLKF.pdf",
            WAYBACK.format(ts="20220205191123", url=SVK + "NyckeltalLKF.pdf"))),
)
SVK_PAGE = "https://www.svenskakyrkan.se/statistik"
SVK_TITLE = "Medlemmar i Svenska kyrkan i förhållande till folkmängd"
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
# The country's row: "Riket" in the 2016-2020 editions, "Totalsumma" in 2021's.
RIKET = re.compile(r"^(?:Riket|Totalsumma) (?P<rest>\d.*)$")
UNPLACED = "På kommunen skrivna "
UNKNOWN_NAME = "Okänd"
# The table prints the people without a property twice -- as the parish "På
# kommunen skrivna" and as the kommun "Okänd" that holds it -- and the 2021
# edition's two rows differ by two members (5,935 against 5,933). The
# country's members are allowed that much against the län and the kommun.
MEMBER_SLACK = 10
# A kommun row is the sum of the parishes printed under it, against SCB's count
# of the kommun: they differ by the people registered without a property (never
# more than 0.5% of a kommun in 2021) and wherever a parish crosses the
# boundary. A row within 2% is the kommun's -- the gate the build uses when a
# unit's parts are summed -- and a share taken from it is good to about 0.4
# points (2% of the people, at most 20 points apart); a row further off is
# another territory.
KOMMUN_TOLERANCE = 0.02


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
    """The country's row ("Riket", or "Totalsumma"), printed exactly once."""
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
                    lines: list[str], code_of: dict[str, str] | None = None
                    ) -> dict[str, tuple[str, str]]:
    """Kommuner the table prints no row for -> (the kommun whose row holds
    them, the parish that joins them).

    A parish that spans two kommuner (Forshaga-Munkfors församling) is counted
    whole under one of them, and the other kommun gets no row. It is found by a
    parish row naming the missing kommun in its hyphenated name. The kommun
    that holds it is the one whose row the parish is printed under -- given
    ``code_of``, the table's kommun names' codes -- because the parish's own
    code does not say: 176301 sat under Munkfors in the 2018-2020 editions and
    under Forshaga in 2016's and 2021's. Without ``code_of`` the code's first
    four digits stand in. A missing kommun no one such parish explains stops
    the run."""
    out: dict[str, tuple[str, str]] = {}
    for code in unread:
        hosts = set()
        under = None
        for line in lines:
            line = " ".join(line.split())
            row = ROW.match(line)
            if row and row.group("kind") == "kommun" and "församling" not in row.group("name"):
                under = (code_of or {}).get(row.group("name"))
            found = PARISH.match(line)
            if found and fold(names[code]) in {fold(p) for p in found.group("name").split("-")}:
                host = under if code_of is not None else found.group("code")[:4]
                hosts.add((host, found.group("name")))
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


@dataclass
class Edition:
    """One edition of the table, read and checked: the kommun rows by SCB code,
    the kommuner joined to another's row by a shared parish, and each kommun
    row's population against SCB's count of the kommun the same day."""
    year: int
    url: str
    rows: dict[str, Row]                   # SCB code -> its own row
    joined: dict[str, tuple[str, str]]     # code -> (the code whose row holds it, parish)
    off: dict[str, float]                  # code -> (SCB - row) / SCB


def read_edition(year: int, urls: tuple[str, ...], sv: dict[str, str]) -> Edition | None:
    """An edition's rows, every sum checked; None when no copy of it answers."""
    import pdfplumber
    title = f"{SVK_TITLE} den 31.12.{year}"
    lines, used = None, None
    for url in urls:
        try:
            raw = request(url, accept="application/pdf,*/*", attempts=3)
        except (SystemExit, Exception) as exc:
            log(f"  {year}: {url}: {str(exc)[:120]}")
            continue
        if not raw.startswith(b"%PDF"):
            log(f"  {year}: {url}: not a PDF")
            continue
        with pdfplumber.open(io.BytesIO(raw)) as doc:
            got = [line for page in doc.pages for line in (page.extract_text() or "").splitlines()]
        if any(title in " ".join(line.split()) for line in got[:5]):
            lines, used = got, url
            break
        log(f"  {year}: {url} holds another edition: {got[:1]}")
    if lines is None:
        return None
    kommuner, lan, nowhere = svk_rows(lines)
    riket = riket_row(lines)
    # The people SCB cannot place in a parish are printed as a parish of their
    # own ("På kommunen skrivna") of a kommun called "Okänd" (unknown): one
    # count, set aside from the kommuner and the län.
    unknown = [rows.pop(UNKNOWN_NAME) for rows in (lan, kommuner) if UNKNOWN_NAME in rows]
    if len(unknown) != 1:
        raise SystemExit(f"svenska kyrkan {year}: {len(unknown)} rows for '{UNKNOWN_NAME}'")
    check_country(lan, unknown[0], riket)
    scb_kommuner = {c: n for c, n in sv.items() if len(c) == 4}
    code_of = match_names(list(kommuner), scb_kommuner)
    read = set(code_of.values())
    joined = joined_kommuner(sorted(set(scb_kommuner) - read), read, scb_kommuner, lines,
                             code_of)
    check_lan(kommuner, lan, code_of, lan_codes(list(lan), sv))
    # SCB's own count of the same day. The table's kommun rows leave out the
    # people SCB cannot place on a property, and count a parish that crosses
    # a kommun boundary whole under one kommun.
    scb = scb_population(year)
    if abs(riket[0] - scb["00"]) > 0.0005 * scb["00"]:
        raise SystemExit(f"svenska kyrkan {year}: the country's row counts {riket[0]:,} people, "
                         f"SCB {scb['00']:,.0f}")
    hosts = {host for host, _ in joined.values()}
    rows = {c: kommuner[k] for k, c in code_of.items() if c not in hosts}
    off = {c: (scb[c] - row[0]) / scb[c] for c, row in rows.items()}
    beyond = sorted((d, c) for c, d in off.items() if abs(d) > 0.005)
    log(f"  {year} ({used}): {len(lines):,} lines; {len(kommuner)} kommun rows make their 21 "
        f"län, and the län with {unknown[0][0]:,} people without a property the country's "
        f"{riket[0]:,} people and {riket[1]:,} members, SCB's {scb['00']:,.0f}; "
        f"joined: {sorted((sv[c], sv[h], p) for c, (h, p) in joined.items())}; kommun rows "
        f"more than 0.5% off SCB's count: "
        + ", ".join(f"{sv[c]} {100 * d:+.2f}%" for d, c in beyond))
    return Edition(year, used, rows, joined, off)


def choose(editions: list[Edition], codes: list[str]
           ) -> tuple[dict[str, Edition], dict[str, list[str]]]:
    """Each kommun -> the newest edition whose row is the kommun's (within
    KOMMUN_TOLERANCE of SCB's count), and each kommun with none -> why not."""
    chosen: dict[str, Edition] = {}
    why: dict[str, list[str]] = defaultdict(list)
    for code in codes:
        for ed in editions:
            if code in ed.rows and abs(ed.off[code]) <= KOMMUN_TOLERANCE:
                chosen[code] = ed
                break
            if code in ed.rows:
                why[code].append(f"{ed.year}: its row counts {100 * -ed.off[code]:+.1f}% "
                                 "against SCB's count of the kommun")
            else:
                joined = ed.joined.get(code) or next(
                    ((c, p) for c, (h, p) in ed.joined.items() if h == code), None)
                why[code].append(f"{ed.year}: one parish, {joined[1] if joined else '?'} "
                                 "församling, joins it to a neighbour")
    return chosen, {c: w for c, w in why.items() if c not in chosen}


def kommun_record(code: str, row: Row, off: float, edition: Edition, sv: dict[str, str],
                  shape_id: str) -> dict[str, Any]:
    pop, members, residents = row
    year = edition.year
    elsewhere = (f" Of the kommun's residents, {residents:.1f}% are members, in whatever "
                 "parish; the count above is of the members of its own parishes, wherever "
                 "they live -- the two differ where a parish without territory (Karlskrona's "
                 "admiralty parish) has members in more than one kommun."
                 if abs(residents - 100 * members / pop) >= 0.15 else "")
    across = (f" The table counts the kommun's parishes, and one crosses its boundary: their "
              f"population is {100 * -off:+.1f}% against SCB's count of the kommun, so the "
              "share describes almost but not exactly the kommun."
              if abs(off) > 0.005 else "")
    newest = ("the latest edition by kommun" if year == EDITIONS[0][0] else
              f"the latest edition in which the kommun's own parishes make it; in the "
              f"{EDITIONS[0][0]} edition they do not")
    return record(
        f"SWE-SVK-{code}", sv[code], level="admin2", parent="SWE", country="SWE",
        parent_name=sv[code[:2]], codes={"scb": code}, match_by="shape_id", shape_id=shape_id,
        religion=shares({SWEDEN_CHURCH: members, SWEDEN_OUTSIDE: pop - members}, total=pop),
        religion_year=year, religion_basis=BASIS,
        religion_note=(
            f"Members of the Church of Sweden on 31 December {year} against the kommun's "
            f"population the same day, {members:,} of {pop:,}, both counted by Statistics "
            "Sweden for the Church (Svenska kyrkan, 'Medlemmar i Svenska kyrkan i förhållande "
            f"till folkmängd den 31.12.{year} per församling, kommun och län samt riket', "
            f"{newest}): the Church's registered membership, not belief. Everyone else -- "
            "members of other faiths and of none alike -- is one group: no state register "
            "records religion, and the Church's is the only membership count published by "
            "kommun. The population leaves out the few people registered in the kommun "
            "without a property, whom SCB cannot place in a parish." + across + elsewhere),
        sources=[{"field": "religion", "name": "Church of Sweden (Svenska kyrkan), members "
                  f"against population 31 December {year}, counted by SCB", "url": edition.url,
                  "year": year}])


def sweden() -> list[dict[str, Any]]:
    from .sweden import BASE, bind_kommuner
    meta = {v["code"]: v for v in request_json(BASE.format(lang="sv", table="BefolkningNy"))
            ["variables"]}
    sv = dict(zip(meta["Region"]["values"], meta["Region"]["valueTexts"]))
    codes = sorted(c for c in sv if len(c) == 4)
    editions = []
    for year, urls in EDITIONS:
        edition = read_edition(year, urls, sv)
        if edition is None:
            if year == EDITIONS[0][0]:
                raise SystemExit(f"svenska kyrkan: no copy of the {year} table answered")
            log(f"  {year}: no copy answered; the kommuner it would fill stay out")
            continue
        editions.append(edition)
    chosen, left = choose(editions, codes)
    bound = bind_kommuner(sv, codes)
    records = [kommun_record(c, chosen[c].rows[c], chosen[c].off[c], chosen[c], sv, bound[c])
               for c in codes if c in chosen]
    by_year = defaultdict(list)
    for c in chosen:
        by_year[chosen[c].year].append(sv[c])
    log("  kommuner by edition: " + "; ".join(
        f"{y}: {len(n)}" + (f" ({', '.join(sorted(n))})" if y != EDITIONS[0][0] else "")
        for y, n in sorted(by_year.items(), reverse=True)))
    for c, reasons in sorted(left.items()):
        log(f"  left out: {sv[c]} ({c}) -- " + "; ".join(reasons))
    return records


def scb_population(year: int) -> dict[str, float]:
    """SCB's register population on 31 December of ``year``, by region."""
    from .sweden import BASE
    url = BASE.format(lang="en", table="BefolkningNy")
    meta = {v["code"]: v for v in request_json(url)["variables"]}
    content = next(c for c in meta["ContentsCode"]["values"])
    body = request_json(url, {"query": [
        {"code": "Region", "selection": {"filter": "item", "values": meta["Region"]["values"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [content]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [str(year)]}},
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
