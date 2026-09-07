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

What the runs established, so the next reader does not repeat them. All three
instances answer POST and refuse GET with 405, and all three admit an anonymous
user called GAST:

* **GENESIS-Online** (the federal database) is open and searchable to GAST and
  holds no religion demography at all. "Religion" matches fifteen tables --
  television airtime, book titles, gross earnings, national accounts -- all of
  them "Deutschland, Jahre". The word is in their subject classifications, not
  their variables. Its documented host redirects: ask genesis.destatis.de.
* **The Regionaldatenbank** admits GAST and then answers 401 to every catalogue
  search. It needs a registered account and nothing about it is known.
* **The Zensus 2022 database has the data.** Zensus 2022 did ask religion:
  forty tables match, in two families -- 1000A-* "Personen: Religion" and
  2000X-* "Personen: Religion (ausfuehrlich)". GAST may search that catalogue
  and do nothing else with it: catalogue, metadata and data endpoints all
  answer 401. Germany is one free registration away.

What is still unknown, and what an account would settle first: four tables
share the title "Personen: Religion" and differ only by a letter -- 1018, 1E18,
1K18, 1W18 -- which is the Zensus habit of publishing one table once per
regional level. Which of them is cut by DLAND decides the adapter, and
metadata/table is exactly the endpoint GAST may not call.

Read-only, and the output is the log. Credentials, if any are set, are read
from the environment and never from a command line.

Usage:
    python -m scripts.probe_genesis
    python -m scripts.probe_genesis --instances zensus
    python -m scripts.probe_genesis --instances zensus --tables 1000A-1018,2000X-1022
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

TIMEOUT = 90

# The three instances, with the environment variable each one's credentials
# would come from. GENESIS and the Regionaldatenbank are separate registrations
# even though they are the same software.
INSTANCES: dict[str, dict[str, str]] = {
    "genesis": {
        # www-genesis.destatis.de, the host every Destatis document names,
        # answers 307 to this path and points at genesis.destatis.de. Following
        # it was refused on purpose -- a probe that wanders to another host is
        # no longer evidence about the one it was aimed at -- so the redirect
        # is taken as the address it is and written down here instead.
        "name": "GENESIS-Online (Destatis, federal)",
        "base": "https://genesis.destatis.de/genesisWS/rest/2020",
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


def _follow(url: str, params: dict[str, object], method: str, accept: str,
            headers: dict[str, str] | None = None) -> object:
    """Re-issue a request against an absolute URL, once, after a 307/308."""
    encoded = urllib.parse.urlencode(params)
    extra = dict(headers or {})
    if method == "GET":
        req = urllib.request.Request(f"{url}?{encoded}",
                                     headers={"Accept": accept, **extra})
    else:
        req = urllib.request.Request(
            url, data=encoded.encode(),
            headers={"Accept": accept,
                     "Content-Type": "application/x-www-form-urlencoded",
                     **extra},
            method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
            body = fh.read()
    except urllib.error.HTTPError as err:
        return {"__error__": f"after redirect: HTTP {err.code} {err.reason or ''}".strip()}
    except Exception as err:                        # noqa: BLE001 -- reported
        return {"__error__": f"after redirect: {type(err).__name__}: {err}"}
    try:
        return json.loads(body)
    except ValueError:
        text = body.decode("utf-8", "replace")
        return {"__text__": f"{len(body)} bytes; "
                            f"{' | '.join(text.splitlines()[:3])[:400]}"}


def once(base: str, path: str, params: dict[str, object], method: str,
         headers: dict[str, str] | None = None,
         *, _redirected: bool = False) -> object:
    """One call, by one method. Returns the parsed body or an error marker."""
    encoded = urllib.parse.urlencode(params)
    accept = "*/*" if path in NOT_JSON else "application/json"
    extra = dict(headers or {})
    if method == "GET":
        req = urllib.request.Request(f"{base}/{path}?{encoded}",
                                     headers={"Accept": accept, **extra})
    else:
        req = urllib.request.Request(
            f"{base}/{path}", data=encoded.encode(),
            headers={"Accept": accept,
                     "Content-Type": "application/x-www-form-urlencoded",
                     **extra},
            method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
            body = fh.read()
    except urllib.error.HTTPError as err:
        # 307 and 308 preserve the method and body; urllib follows neither for
        # a POST, so GENESIS-Online's redirect came back as an error and was
        # nearly filed as "this instance does not answer". One hop, once, to
        # the Location it names -- and a redirect that does not name one, or
        # points off the host, is reported rather than followed.
        target = err.headers.get("Location") if err.headers else None
        if err.code in (307, 308) and target and not _redirected:
            landing = urllib.parse.urljoin(f"{base}/{path}", target)
            if urllib.parse.urlparse(landing).netloc != urllib.parse.urlparse(base).netloc:
                return {"__error__": f"HTTP {err.code} -> off-host {target}"}
            return _follow(landing, params, method, accept, extra)
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


def call(base: str, path: str, creds: dict[str, str],
         headers: dict[str, str] | None = None, **params: object) -> object:
    """One GENESIS REST call, by whichever method this instance accepts."""
    query = {"language": "de", **creds, **params}
    order = [METHOD[base]] if base in METHOD else ["POST", "GET"]
    last: object = {"__error__": "not attempted"}
    for method in order:
        last = once(base, path, query, method, headers)
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


def without_username(payload: object) -> str:
    """A login-check body, with the username taken out of it.

    GENESIS echoes back whatever it took as the username, and for these
    accounts that is the address the person registered with -- while this log
    is committed to a public repository. The body is worth printing: it carries
    the concurrency limits and the session note. The name is not, and it has
    now been leaked twice by two different printers dumping this same object,
    which is why every one of them goes through here instead.
    """
    if not isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)[:300]
    safe = dict(payload)
    for key in ("Username", "username", "Kennung"):
        if key in safe:
            safe[key] = "<withheld>"
    return json.dumps(safe, ensure_ascii=False)[:300]


def account(spec: dict) -> tuple[dict[str, str], str]:
    """The credential as headers, and a description naming no secret value.

    Headers, not query parameters. Measured, not assumed: --whoami asked
    logincheck under four styles and only this one came back with the account
    -- query parameters, HTTP Basic and a bearer token each left the server
    still answering GAST, which reads exactly like a rejected account and is
    not one. Anything that sends credentials to GENESIS goes through here so
    that finding cannot be lost by one call spelling it differently.
    """
    user = os.environ.get(spec["user_env"], "").strip()
    password = os.environ.get(spec["pass_env"], "").strip()
    if user and password:
        return ({"username": user, "password": password},
                f"set via {spec['user_env']}")
    if user or password:
        missing = spec["pass_env"] if user else spec["user_env"]
        return {}, f"INCOMPLETE -- {missing} is empty"
    return {}, "none -- asking anonymously as GAST"


def probe(key: str, spec: dict[str, str]) -> None:
    auth, described = account(spec)
    creds: dict[str, str] = {}
    print(f"\n=== {spec['name']} ===")
    print(f"    {spec['base']}")
    print(f"    credentials: {described}")

    who = call(spec["base"], "helloworld/logincheck", creds, auth)
    print(f"    logincheck: {status_of(who)} [{METHOD.get(spec['base'], 'no method worked')}]")
    if isinstance(who, dict) and "__error__" not in who:
        print(f"      {without_username(who)}")

    for term in TERMS:
        found = call(spec["base"], "find/find", creds, auth,
                     term=term, category="tables", pagelength=40)
        rows = tables_from(found)
        note = status_of(found)
        print(f"    find '{term}': {len(rows)} tables ({note})")
        # All of them, not the first fifteen. The question this pass is being
        # asked now is whether a table exists at some regional level, and a
        # truncated list cannot answer it -- an absence in the first fifteen of
        # forty is not an absence.
        for row in rows:
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
    auth, described = account(spec)
    creds: dict[str, str] = {}
    print(f"\n=== {spec['name']} -- table structures ===")
    # Whether a credential was in hand is half of what a 401 means here, and
    # this pass used to print only the 401. A run with the secret missing and a
    # run with the secret rejected then looked identical, which sent one whole
    # round trip chasing an account that had never been passed to the process.
    print(f"    credentials: {described}")
    who = call(spec["base"], "helloworld/logincheck", creds, auth)
    print(f"    logincheck: {status_of(who)}")
    if isinstance(who, dict) and "__error__" not in who:
        print(f"      {without_username(who)}")
    for name in tables:
        meta = call(spec["base"], "metadata/table", creds, auth, name=name)
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
    auth, described = account(spec)
    creds: dict[str, str] = {}
    print(f"\n=== {spec['name']} -- endpoint surface for {table} ===")
    print(f"    credentials: {described}")
    for path, template in ENDPOINTS:
        params = {k: (v.format(table=table) if isinstance(v, str) else v)
                  for k, v in template.items()}
        answer = call(spec["base"], path, creds, auth, **params)
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


# How to present a credential. GENESIS has carried three schemes across its
# versions and the documentation for one instance does not settle another, so
# the styles are tried rather than chosen. helloworld/logincheck is the oracle:
# it answers with the username the server believes it is talking to, so a
# credential that is being ignored says GAST and one that is accepted says its
# own name. Nothing here prints a secret -- only which style was used and which
# name came back.
AUTH_STYLES = ("query", "header", "basic", "bearer")


def styled(style: str, user: str, password: str) -> tuple[dict, dict]:
    """Query parameters and headers presenting the credential one way."""
    if style == "query":
        return {"username": user, "password": password}, {}
    if style == "header":
        return {}, {"username": user, "password": password}
    if style == "basic":
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return {}, {"Authorization": f"Basic {token}"}
    if style == "bearer":
        # Some accounts are issued a token rather than a password, and it is
        # the password field it arrives in.
        return {}, {"Authorization": f"Bearer {password}"}
    raise ValueError(style)


def whoami(key: str, spec: dict[str, str]) -> None:
    """Which way of presenting this account the server actually recognises."""
    user = os.environ.get(spec["user_env"], "").strip()
    password = os.environ.get(spec["pass_env"], "").strip()
    print(f"\n=== {spec['name']} -- authentication styles ===")
    if not (user and password):
        missing = spec["user_env"] if not user else spec["pass_env"]
        print(f"    no credential: {missing} is empty in this environment")
        return
    print(f"    credential from {spec['user_env']} / {spec['pass_env']}"
          f" (user is {len(user)} chars, password {len(password)})")
    for style in AUTH_STYLES:
        params, headers = styled(style, user, password)
        answer = call(spec["base"], "helloworld/logincheck", params, headers)
        name = "?"
        if isinstance(answer, dict):
            name = answer.get("Username") or answer.get("username") or "?"
        note = status_of(answer)
        # The name itself is never printed. GENESIS echoes back whatever it
        # took as the username, and for these accounts that is the address the
        # person registered with -- which this log commits to a public
        # repository. The only thing worth reporting is whether the server
        # thinks it is talking to GAST or to somebody, and that is a yes or no.
        if name == "GAST":
            verdict = "IGNORED -- server still sees the anonymous GAST"
        elif name in ("?", ""):
            verdict = "no username in reply"
        else:
            verdict = "ACCEPTED -- server named the account (name withheld)"
        print(f"    {style:<8} -> {verdict}")
        if note != "ok" and not str(note).startswith("Sie wurden"):
            print(f"             {str(note)[:160]}")


def fetch(key: str, spec: dict[str, str], table: str, lines: int) -> None:
    """The table itself, printed, so the labels are read rather than guessed.

    ffcsv is GENESIS's flat format: one row per cell with its variable codes and
    labels spelled out beside the value, which is what an adapter has to map.
    Sixteen Laender by three categories is a small table, so it is printed in
    full -- the whole point is to see every category label exactly as published,
    including whichever one turns out to be the residual.
    """
    auth, described = account(spec)
    print(f"\n=== {spec['name']} -- {table} ===")
    print(f"    credentials: {described}")
    text = raw(spec["base"], "data/tablefile", auth,
               name=table, area="all", format="ffcsv", compress="false")
    rows = text.splitlines()
    print(f"    {len(text)} bytes, {len(rows)} lines")
    for row in rows[:lines]:
        # Whole lines. The header of an ffcsv is the thing worth reading here
        # -- an adapter looks its columns up by name -- and it is longer than
        # any truncation that suits a data row, so it was the one line the
        # first print cut off.
        print(f"    {row}")
    if len(rows) > lines:
        print(f"    ... {len(rows) - lines} more lines")


def unzipped(body: bytes) -> str:
    """The CSV out of the archive GENESIS answers with.

    data/tablefile returns a ZIP holding one .csv whatever compress=false says,
    so the first read of this table printed a screenful of binary and looked
    like a broken encoding. The archive is the delivery format, not damage.
    """
    if not body.startswith(b"PK"):
        return body.decode("utf-8", "replace")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        if not names:
            return "(empty archive)"
        # utf-8-sig: the file is UTF-8 and opens with a byte-order mark, which
        # a cp1252 read turns into a leading "i>>?" and every umlaut into
        # mojibake -- Bevoelkerung came back "BevÃ¶lkerung" on the first try.
        # The guess was Windows-1252 because that is what GENESIS's older
        # exports use; this one does not, and the file says so in its first
        # three bytes.
        text = archive.read(names[0]).decode("utf-8-sig", "replace")
        return f"[{names[0]}]\n{text}"


def raw(base: str, path: str, auth: dict[str, str], **params: object) -> str:
    """One call, returning the body as text however it is encoded."""
    encoded = urllib.parse.urlencode({"language": "de", **params})
    req = urllib.request.Request(
        f"{base}/{path}", data=encoded.encode(),
        headers={"Accept": "*/*",
                 "Content-Type": "application/x-www-form-urlencoded",
                 **auth},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
            return unzipped(fh.read())
    except urllib.error.HTTPError as err:
        return f"HTTP {err.code} {err.reason or ''}".strip()
    except Exception as err:                        # noqa: BLE001 -- reported
        return f"{type(err).__name__}: {err}"


def geography(key: str, spec: dict[str, str], selection: str) -> None:
    """Which geographies this database offers, and what is cut by each.

    Reading titles cannot answer whether a religion table exists at some
    regional level: the title says "Personen: Religion" for all four of them and
    nothing about the geography. So ask the catalogue instead -- first for the
    geographic variables themselves, then for the tables that use the ones that
    look like a Kreis. An absence established this way is a fact about the
    database; an absence inferred from a list of titles is a fact about titles.
    """
    auth, described = account(spec)
    print(f"\n=== {spec['name']} -- geographies matching {selection} ===")
    print(f"    credentials: {described}")
    found = call(spec["base"], "catalogue/variables", {}, auth,
                 selection=selection, area="all", pagelength=100)
    note = status_of(found)
    variables = []
    if isinstance(found, dict):
        for holder in ("List", "list", "Variables", "variables"):
            rows = found.get(holder)
            if isinstance(rows, list):
                variables = [r for r in rows if isinstance(r, dict)]
                break
    print(f"    {len(variables)} variable(s) ({note})")
    for var in variables:
        code = str(var.get("Code") or var.get("code") or "?")
        content = (var.get("Content") or var.get("content") or "").strip()
        values = var.get("Values") or var.get("values") or "?"
        print(f"    {code:<12} {str(values):>7} values  {content[:80]}")

    # For each geography, which tables are cut by it. This is the question.
    for var in variables:
        code = str(var.get("Code") or var.get("code") or "")
        if not code:
            continue
        used = call(spec["base"], "catalogue/tables2variable", {}, auth,
                    name=code, area="all", pagelength=100)
        rows = tables_from(used)
        titled = [r for r in rows
                  if "religion" in str(r.get("Content") or r.get("content") or "").lower()]
        print(f"\n    {code}: {len(rows)} table(s), {len(titled)} mentioning religion"
              f" ({status_of(used)})")
        for row in titled[:20]:
            name = row.get("Code") or row.get("code") or "?"
            content = (row.get("Content") or row.get("content") or "").strip()
            print(f"      {name:<16} {content[:100]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", default=",".join(INSTANCES),
                    help="comma-separated: " + ", ".join(INSTANCES))
    ap.add_argument("--tables", default="",
                    help="comma-separated table codes to describe instead of "
                         "searching, e.g. 1000A-1018,1000A-1K18")
    ap.add_argument("--geography", default="",
                    help="a variable selection such as GEO*; list the "
                         "geographies and, for each, the tables cut by it")
    ap.add_argument("--fetch", default="",
                    help="one table code; print its ffcsv body so the category "
                         "labels can be read rather than guessed")
    ap.add_argument("--lines", type=int, default=80,
                    help="how many lines of --fetch to print")
    ap.add_argument("--whoami", action="store_true",
                    help="report which way of presenting the credential the "
                         "server actually recognises")
    ap.add_argument("--endpoints", default="",
                    help="one table code; report which endpoint families "
                         "answer for it, rather than searching or describing")
    args = ap.parse_args(argv)

    wanted = [k.strip() for k in args.instances.split(",") if k.strip()]
    unknown = [k for k in wanted if k not in INSTANCES]
    if unknown:
        print(f"unknown instance(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    if not (args.tables or args.endpoints or args.whoami or args.fetch
            or args.geography):
        print("Region variables a usable table would carry:")
        for code, meaning in REGION_CODES.items():
            print(f"  {code:<8} {meaning}")

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    for key in wanted:
        if args.geography:
            geography(key, INSTANCES[key], args.geography.strip())
        elif args.fetch:
            fetch(key, INSTANCES[key], args.fetch.strip(), args.lines)
        elif args.whoami:
            whoami(key, INSTANCES[key])
        elif args.endpoints:
            endpoints(key, INSTANCES[key], args.endpoints.strip())
        elif tables:
            describe(key, INSTANCES[key], tables)
        else:
            probe(key, INSTANCES[key])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
