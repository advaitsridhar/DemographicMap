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

Read-only, and the output is the log. Credentials, if any are set, are read
from the environment and never from a command line.

Usage:
    python -m scripts.probe_genesis
    python -m scripts.probe_genesis --instances zensus
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


def call(base: str, path: str, creds: dict[str, str], **params: object) -> object:
    """One GENESIS REST call. Returns the parsed body, or an error marker."""
    query = {"language": "de", **creds, **params}
    url = f"{base}/{path}?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
            body = fh.read()
    except urllib.error.HTTPError as err:
        return {"__error__": f"HTTP {err.code} {err.reason}"}
    except Exception as err:                        # noqa: BLE001 -- reported
        return {"__error__": f"{type(err).__name__}: {err}"}
    try:
        return json.loads(body)
    except ValueError:
        return {"__error__": "not JSON: " + body[:200].decode("utf-8", "replace")}


def status_of(payload: object) -> str:
    """GENESIS answers 200 with the refusal in the body, so read the body."""
    if isinstance(payload, dict):
        if "__error__" in payload:
            return str(payload["__error__"])
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
    print(f"    logincheck: {status_of(who)}")
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", default=",".join(INSTANCES),
                    help="comma-separated: " + ", ".join(INSTANCES))
    args = ap.parse_args(argv)

    wanted = [k.strip() for k in args.instances.split(",") if k.strip()]
    unknown = [k for k in wanted if k not in INSTANCES]
    if unknown:
        print(f"unknown instance(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    print("Region variables a usable table would carry:")
    for code, meaning in REGION_CODES.items():
        print(f"  {code:<8} {meaning}")

    for key in wanted:
        probe(key, INSTANCES[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
