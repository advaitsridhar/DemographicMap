#!/usr/bin/env python3
"""What Germany's statistics databases hold on religion, and whether it is free.

Germany is the largest European country this map still has nothing for below
the national line: sixteen Laender, eleven of them with a population figure and
none with a composition. The Eurostat adapter already records why ethnicity is
absent -- Germany counts citizenship and migration background, not ethnicity --
but it makes no such claim about religion, and the comment at the top of that
file says Germany does collect it. So religion is an open gap rather than a
refusal, and nobody has yet looked at what is actually published.

Three databases could answer it, all of them GENESIS instances speaking the
same REST dialect:

* GENESIS-Online, the federal database, which carries the national tables
* the Regionaldatenbank, which carries the same tables cut by region
* the Zensus 2022 results database, which carries that census alone

Two things have to be true before an adapter is worth writing, and neither is
guessable from outside. The data has to exist -- Zensus 2011 asked religion
twice, once for public-law membership and once, voluntarily, for belief, and
whether Zensus 2022 asked at all is exactly the question. And it has to be
reachable without a credential this project cannot hold, because a source that
needs an account only the repository owner can create is a different kind of
finding from one that is simply absent.

So this asks each instance who it thinks we are, searches its catalogue for the
words a religion table would be titled with, and prints what comes back with
the region variable each table offers. A table that exists but is cut only by
Germany as a whole is no use here and is reported as such rather than counted.

What the first runs established, so the next reader does not repeat them:

* All three instances answer POST and refuse GET with 405.
* The Zensus 2022 database admits an anonymous user called GAST, and answers
  its catalogue to that user. Zensus 2022 **did** ask religion: forty tables
  match, in two families -- ``1000A-*`` "Personen: Religion" and ``2000X-*``
  "Personen: Religion (ausfuehrlich)", which is the finer classification.
* The Regionaldatenbank admits GAST too but answers 401 to any catalogue
  search, so it needs a real account. GENESIS-Online answers 307 to POST.

That leaves one question between here and an adapter: which of those tables is
cut by a geography the boundary files can join. Four of them share the title
"Personen: Religion" and differ only in a letter -- 1018, 1E18, 1K18, 1W18 --
which is the Zensus habit of publishing one table once per regional level. A
table cut only by Germany as a whole cannot fill sixteen Laender, and the
title does not say which is which. So ``--tables`` asks each one for its own
structure and prints the variables it is cut by.

Read-only, and the output is the log. Credentials, if any are set, are read
from the environment and never from a command line.

Usage:
    python -m scripts.probe_genesis
    python -m scripts.probe_genesis --instances zensus
    python -m scripts.probe_genesis --instances zensus --tables 1000A-1018,2000X-1022
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 90

# The three instances, with the environment variable each one's credentials
# would come from. GENESIS and the Regionaldatenbank are separate registrations
# even though they are the same software.
INSTANCES: dict[str, dict[str, str]] = {
    "genesis": {
        "name": "GENESIS-Online (Destatis, federal)",
        "base": "https://www-genesis.destatis.de/genesisWS/rest/2020",
        "user_env": "GENESIS_USER", "pass_env": "GENESIS_PASSWORD",
    },
    "regional": {
        "name": "Regionaldatenbank Deutschland",
        "base": "https://www.regionalstatistik.de/genesisws/rest/2020",
        "user_env": "REGIONALSTATISTIK_USER",
        "pass_env": "REGIONALSTATISTIK_PASSWORD",
    },
    "zensus": {
        "name": "Zensus 2022 results database",
        "base": "https://ergebnisse.zensus2022.de/api/rest/2020",
        "user_env": "ZENSUS_USER", "pass_env": "ZENSUS_PASSWORD",
    },
}

# German first, because the catalogue is indexed in German and an English
# request returns the German titles anyway for tables that have no translation.
# "Religion" alone misses the 2011 wording, which is the one that matters if
# 2022 dropped the question.
TERMS = ("Religion", "Glaubensrichtung", "Religionsgesellschaft", "Konfession")

# A table cut only by the federal total cannot fill sixteen Laender. These are
# the region variable codes GENESIS uses, coarsest first.
REGION_CODES = {"DLAND": "Land (16)", "KREISE": "Kreis (~400)",
                "GEMEIN": "Gemeinde", "DG": "Germany as a whole",
                "REGBEZ": "Regierungsbezirk"}


# Endpoints that do not answer in JSON. Asking them for JSON earns a 406 Not
# Acceptable, which is content negotiation refusing the Accept header and not
# the server refusing the caller -- a distinction worth one line of code,
# because reading those two 406s as "GAST cannot reach data" would have closed
# Germany on the strength of a header this probe chose itself.
NOT_JSON = ("data/tablefile", "data/chart2table", "data/cube", "data/result")


def once(base: str, path: str, params: dict[str, object], method: str) -> object:
    """One call, by one method. Returns the parsed body or an error marker."""
    encoded = urllib.parse.urlencode(params)
    accept = "*/*" if path in NOT_JSON else "application/json"
    if method == "GET":
        req = urllib.request.Request(f"{base}/{path}?{encoded}",
                                     headers={"Accept": accept})
    else:
        req = urllib.request.Request(
            f"{base}/{path}", data=encoded.encode(),
            headers={"Accept": accept,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
            body = fh.read()
    except urllib.error.HTTPError as err:
        return {"__error__": f"HTTP {err.code} {err.reason or ''}".strip()}
    except Exception as err:                        # noqa: BLE001 -- reported
        return {"__error__": f"{type(err).__name__}: {err}"}
    try:
        return json.loads(body)
    except ValueError:
        # Not an error for the endpoints that answer in CSV: it is the answer.
        # Reporting the first lines and the size says whether a table came back
        # and how big it is, which is the whole question for data/tablefile.
        text = body.decode("utf-8", "replace")
        head = " | ".join(text.splitlines()[:3])
        return {"__text__": f"{len(body)} bytes; {head[:400]}"}


# Which HTTP method an instance answers on, learned from its first call rather
# than assumed. The first pass asked with GET and every endpoint on all three
# instances answered 405 Method Not Allowed -- which says the path is there and
# the verb is wrong, not that the data is absent or the account is missing.
# Those are three different findings and guessing between them is exactly what
# this probe exists to avoid, so it tries both and reports which one answered.
METHOD: dict[str, str] = {}


def call(base: str, path: str, creds: dict[str, str], **params: object) -> object:
    """One GENESIS REST call, by whichever method this instance accepts."""
    query = {"language": "de", **creds, **params}
    order = [METHOD[base]] if base in METHOD else ["POST", "GET"]
    last: object = {"__error__": "not attempted"}
    for method in order:
        last = once(base, path, query, method)
        if not (isinstance(last, dict) and str(last.get("__error__", ""))
                .startswith("HTTP 405")):
            METHOD.setdefault(base, method)
            return last
    return last


def status_of(payload: object) -> str:
    """GENESIS answers 200 with the refusal in the body, so read the body."""
    if isinstance(payload, dict):
        if "__error__" in payload:
            return str(payload["__error__"])
        if "__text__" in payload:
            return "non-JSON body: " + str(payload["__text__"])
        status = payload.get("Status") or payload.get("status") or {}
        if isinstance(status, dict):
            content = status.get("Content") or status.get("content")
            if content:
                return str(content)
    return "ok"


def tables_from(payload: object) -> list[dict]:
    """The table list out of a find or catalogue response, whatever it nests."""
    if not isinstance(payload, dict):
        return []
    for key in ("Tables", "tables", "List", "list"):
        found = payload.get(key)
        if isinstance(found, list):
            return [row for row in found if isinstance(row, dict)]
    return []


def probe(key: str, spec: dict[str, str]) -> None:
    creds = {}
    user = os.environ.get(spec["user_env"], "").strip()
    password = os.environ.get(spec["pass_env"], "").strip()
    if user and password:
        creds = {"username": user, "password": password}
    print(f"\n=== {spec['name']} ===")
    print(f"    {spec['base']}")
    print(f"    credentials: {'set via ' + spec['user_env'] if creds else 'none -- asking anonymously'}")

    who = call(spec["base"], "helloworld/logincheck", creds)
    print(f"    logincheck: {status_of(who)} [{METHOD.get(spec['base'], 'no method worked')}]")
    if isinstance(who, dict) and "__error__" not in who:
        print(f"      {json.dumps(who, ensure_ascii=False)[:300]}")

    for term in TERMS:
        found = call(spec["base"], "find/find", creds,
                     term=term, category="tables", pagelength=40)
        rows = tables_from(found)
        note = status_of(found)
        print(f"    find '{term}': {len(rows)} tables ({note})")
        for row in rows[:15]:
            code = row.get("Code") or row.get("code") or "?"
            title = (row.get("Content") or row.get("content") or "").strip()
            print(f"      {code:<16} {title[:110]}")


def variables_of(payload: object) -> list[dict]:
    """The variable list out of a metadata response, whatever it nests it in."""
    if not isinstance(payload, dict):
        return []
    obj = payload.get("Object") or payload.get("object") or {}
    for holder in (obj, payload):
        if not isinstance(holder, dict):
            continue
        struct = holder.get("Structure") or holder.get("structure") or {}
        if isinstance(struct, dict):
            out = []
            for side in ("Rows", "Columns", "rows", "columns"):
                rows = struct.get(side)
                if isinstance(rows, list):
                    out += [dict(r, __side__=side) for r in rows
                            if isinstance(r, dict)]
            if out:
                return out
    return []


def describe(key: str, spec: dict[str, str], tables: list[str]) -> None:
    """What each named table is cut by -- the question a title cannot answer."""
    creds = {}
    user = os.environ.get(spec["user_env"], "").strip()
    password = os.environ.get(spec["pass_env"], "").strip()
    if user and password:
        creds = {"username": user, "password": password}
    print(f"\n=== {spec['name']} -- table structures ===")
    for name in tables:
        meta = call(spec["base"], "metadata/table", creds, name=name)
        note = status_of(meta)
        obj = meta.get("Object", {}) if isinstance(meta, dict) else {}
        title = (obj.get("Content") or "").strip().replace("\n", " ")
        print(f"\n  {name}  ({note})")
        if title:
            print(f"    title: {title[:150]}")
        variables = variables_of(meta)
        if not variables:
            # Not a failure worth hiding: a table can be real and still refuse
            # its structure to GAST, and that is a different answer from absent.
            print(f"    no structure returned -- raw: "
                  f"{json.dumps(meta, ensure_ascii=False)[:400]}")
            continue
        for var in variables:
            code = var.get("Code") or var.get("code") or "?"
            content = (var.get("Content") or var.get("content") or "").strip()
            values = var.get("Values") or var.get("values") or "?"
            flag = "  <-- region" if str(code).upper() in REGION_CODES else ""
            print(f"    {str(code):<12} {str(values):>7} values  "
                  f"{content[:70]}{flag}")


# What an anonymous user may actually do, asked rather than assumed. GAST can
# search the catalogue and cannot read a table's metadata -- find/find answers
# and metadata/table returns 401 -- so the permission surface is per endpoint
# family, not per account. Whether GAST can reach the *data* is the question
# that decides whether Germany needs a registered account at all, and it is not
# answerable from the two endpoints already tried.
ENDPOINTS: tuple[tuple[str, dict[str, object]], ...] = (
    ("catalogue/tables", {"selection": "{table}"}),
    ("catalogue/variables", {"selection": "*", "pagelength": 5}),
    ("catalogue/timeseries", {"selection": "{table}"}),
    ("metadata/table", {"name": "{table}"}),
    ("metadata/variable", {"name": "RELIGT"}),
    ("data/table", {"name": "{table}", "area": "all", "compress": "false"}),
    ("data/tablefile", {"name": "{table}", "area": "all", "format": "ffcsv"}),
    ("data/chart2table", {"name": "{table}", "area": "all"}),
)


def endpoints(key: str, spec: dict[str, str], table: str) -> None:
    """Which endpoint families answer, for the credentials in hand."""
    creds = {}
    user = os.environ.get(spec["user_env"], "").strip()
    password = os.environ.get(spec["pass_env"], "").strip()
    if user and password:
        creds = {"username": user, "password": password}
    print(f"\n=== {spec['name']} -- endpoint surface for {table} ===")
    print(f"    credentials: {'set via ' + spec['user_env'] if creds else 'none -- GAST'}")
    for path, template in ENDPOINTS:
        params = {k: (v.format(table=table) if isinstance(v, str) else v)
                  for k, v in template.items()}
        answer = call(spec["base"], path, creds, **params)
        note = status_of(answer)
        # A body is the proof, not the status line: GENESIS answers 200 with a
        # refusal inside often enough that "ok" alone has been wrong twice here.
        shape = ""
        if isinstance(answer, dict) and "__error__" not in answer:
            keys = [k for k in answer if k not in ("Ident", "Status", "Copyright")]
            shape = f" keys={keys[:6]}"
            body = json.dumps(answer, ensure_ascii=False)
            shape += f" len={len(body)}"
        print(f"    {path:<22} {note[:80]}{shape}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", default=",".join(INSTANCES),
                    help="comma-separated: " + ", ".join(INSTANCES))
    ap.add_argument("--tables", default="",
                    help="comma-separated table codes to describe instead of "
                         "searching, e.g. 1000A-1018,1000A-1K18")
    ap.add_argument("--endpoints", default="",
                    help="one table code; report which endpoint families "
                         "answer for it, rather than searching or describing")
    args = ap.parse_args(argv)

    wanted = [k.strip() for k in args.instances.split(",") if k.strip()]
    unknown = [k for k in wanted if k not in INSTANCES]
    if unknown:
        print(f"unknown instance(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    if not args.tables and not args.endpoints:
        print("Region variables a usable table would carry:")
        for code, meaning in REGION_CODES.items():
            print(f"  {code:<8} {meaning}")

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    for key in wanted:
        if args.endpoints:
            endpoints(key, INSTANCES[key], args.endpoints.strip())
        elif tables:
            describe(key, INSTANCES[key], tables)
        else:
            probe(key, INSTANCES[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
