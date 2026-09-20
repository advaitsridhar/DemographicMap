#!/usr/bin/env python3
"""Which of a country's open-data portals answer, and what they hold.

A statistical office that refuses an automated reader often publishes the same
tables on an open-data portal that does not, and in much of the world those
portals are CKAN or a CKAN-like service whose datastore serves rows without a
key. Indonesia's Satu Data is federated -- every province and many regencies
run their own -- so the first question is not "what is in the portal" but
"which of these forty hostnames exist at all", and the second is "does the one
that exists speak CKAN".

This asks both, for many hosts in one run, and prints the HTTP status of every
attempt. A host that does not resolve, one that answers 403 and one that
answers a CKAN catalogue of two hundred datasets are three different findings
and the log has to be able to tell them apart: a measured negative is a result,
and re-measuring it on the next run is waste.

Read-only. Nothing is written and nothing is committed; the output is the log.

Usage:
    # do these hosts exist, and do they speak CKAN?
    python -m scripts.probe_ckan data.jabarprov.go.id data.sumselprov.go.id

    # ... and what do they have on "agama"?
    python -m scripts.probe_ckan --hosts-file hosts.txt --query agama --rows 40

    # one dataset's resources, and the first rows of one of them
    python -m scripts.probe_ckan data.jakarta.go.id --package jumlah-pemeluk-agama
    python -m scripts.probe_ckan data.jakarta.go.id --datastore <resource-id>
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log  # noqa: E402

# Honest and identifying. The house rule is that a host refusing an automated
# reader is a result to write down, not a block to dress around, so this never
# claims to be a browser.
HEADERS = {
    "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
    "Accept": "application/json, text/html;q=0.8, */*;q=0.5",
}

# Short by the standards of the other probes, and deliberately: this walks
# dozens of hosts in one run and a dead one must cost seconds, not a minute.
# A host that is merely slow is reported as a timeout at this bound, which is
# a different line in the log from a refusal and can be re-measured longer.
TIMEOUT = 20

# The API roots CKAN has been mounted at. Indonesian portals run CKAN 2.8
# through 2.10 and a few sit behind a path prefix.
CKAN_ROOTS = ("/api/3/action", "/api/action")


def get(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    """(status, content-type, body). Status 0 means the request never got an
    HTTP answer, and the body says which failure it was."""
    timeout = TIMEOUT if timeout is None else timeout
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4_000_000).decode("utf-8", "replace")
            return response.status, response.headers.get("Content-Type", "?"), body
    except urllib.error.HTTPError as exc:
        body = exc.read(2000).decode("utf-8", "replace") if exc.fp else ""
        return exc.code, exc.headers.get("Content-Type", "?") if exc.headers else "?", body
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return 0, "", "DNS: no such host"
        if isinstance(reason, ssl.SSLError):
            return 0, "", f"TLS: {reason}"
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            return 0, "", f"timeout after {timeout}s"
        return 0, "", f"{type(reason).__name__}: {reason}"
    except TimeoutError:
        return 0, "", f"timeout after {timeout}s"
    except Exception as exc:                       # noqa: BLE001 - report anything
        return 0, "", f"{type(exc).__name__}: {exc}"


def as_json(body: str) -> Any:
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None


def ckan_root(host: str, scheme: str) -> str | None:
    """The API root this host answers ``status_show`` on, or None."""
    for root in CKAN_ROOTS:
        url = f"{scheme}://{host}{root}/status_show"
        status, ctype, body = get(url)
        payload = as_json(body)
        ok = status == 200 and isinstance(payload, dict) and payload.get("success")
        log(f"    {root}/status_show -> {status} {ctype.split(';')[0]}"
            + (f" CKAN {payload.get('result', {}).get('ckan_version', '?')}" if ok
               else f" {' '.join(body[:120].split())}" if body and status != 200 else ""))
        if ok:
            return root
    return None


def reach(host: str) -> tuple[str | None, str | None]:
    """(scheme that answered, CKAN API root). Either may be None."""
    for scheme in ("https", "http"):
        status, ctype, body = get(f"{scheme}://{host}/")
        detail = ""
        if status == 0:
            detail = body
        elif "html" in ctype.lower():
            title = ""
            lowered = body.lower()
            if "<title" in lowered:
                start = lowered.index("<title")
                start = body.index(">", start) + 1
                end = lowered.find("</title>", start)
                title = " ".join(body[start:end if end > 0 else start + 120].split())
            detail = f'"{title[:100]}"' if title else f"{len(body):,} bytes"
        else:
            detail = f"{len(body):,} bytes"
        log(f"  {scheme}://{host}/ -> {status} {ctype.split(';')[0]} {detail}")
        if status == 0 and "no such host" in body:
            return None, None          # http:// will not resolve either
        if status:
            return scheme, ckan_root(host, scheme)
    return None, None


def search(host: str, scheme: str, root: str, query: str, rows: int) -> None:
    q = urllib.parse.urlencode({"q": query, "rows": rows})
    url = f"{scheme}://{host}{root}/package_search?{q}"
    status, _, body = get(url)
    payload = as_json(body)
    if status != 200 or not isinstance(payload, dict) or not payload.get("success"):
        log(f"    package_search q={query!r} -> {status} {' '.join(body[:200].split())}")
        return
    result = payload.get("result", {})
    results = result.get("results", []) or []
    log(f"    package_search q={query!r} -> {status}, {result.get('count', 0)} matches, "
        f"{len(results)} shown")
    for pkg in results:
        formats = sorted({(r.get("format") or "?").lower()
                          for r in (pkg.get("resources") or [])})
        log(f"      - {pkg.get('name', '?')}: {' '.join(str(pkg.get('title', '')).split())[:110]}"
            f"  [{len(pkg.get('resources') or [])} res: {','.join(formats)[:60]}]")


def package(host: str, scheme: str, root: str, name: str) -> None:
    url = f"{scheme}://{host}{root}/package_show?id={urllib.parse.quote(name)}"
    status, _, body = get(url)
    payload = as_json(body)
    if status != 200 or not isinstance(payload, dict) or not payload.get("success"):
        log(f"    package_show {name!r} -> {status} {' '.join(body[:200].split())}")
        return
    pkg = payload.get("result", {})
    log(f"    package_show {name!r} -> {status}: {pkg.get('title', '?')}")
    for field in ("notes", "metadata_modified", "license_title", "author", "organization"):
        value = pkg.get(field)
        if isinstance(value, dict):
            value = value.get("title") or value.get("name")
        if value:
            log(f"      {field}: {' '.join(str(value).split())[:300]}")
    for res in pkg.get("resources") or []:
        log(f"      resource {res.get('id', '?')} [{res.get('format', '?')}] "
            f"datastore={res.get('datastore_active')} "
            f"{' '.join(str(res.get('name', '')).split())[:80]}")
        if res.get("url"):
            log(f"        {res['url']}")


def datastore(host: str, scheme: str, root: str, resource: str, limit: int) -> None:
    q = urllib.parse.urlencode({"resource_id": resource, "limit": limit})
    url = f"{scheme}://{host}{root}/datastore_search?{q}"
    status, _, body = get(url)
    payload = as_json(body)
    if status != 200 or not isinstance(payload, dict) or not payload.get("success"):
        log(f"    datastore_search {resource} -> {status} {' '.join(body[:300].split())}")
        return
    result = payload.get("result", {})
    fields = [f.get("id") for f in result.get("fields", [])]
    log(f"    datastore_search {resource} -> {status}, total {result.get('total')}, "
        f"fields {fields}")
    for row in result.get("records", [])[:limit]:
        log("      " + json.dumps(row, ensure_ascii=False, default=str)[:400])


def hosts_from(args: argparse.Namespace) -> list[str]:
    names = list(args.hosts)
    if args.hosts_file:
        text = Path(args.hosts_file).read_text(encoding="utf-8")
        names += [line.split("#")[0].strip() for line in text.splitlines()]
    seen: dict[str, None] = {}
    for name in names:
        name = name.strip().strip("/")
        if not name:
            continue
        if "://" in name:
            name = urllib.parse.urlsplit(name).netloc
        seen.setdefault(name, None)
    return list(seen)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hosts", nargs="*", help="hostnames, e.g. data.jabarprov.go.id")
    ap.add_argument("--hosts-file", help="a file of hostnames, one per line, # comments")
    ap.add_argument("--query", default="", help="package_search query, e.g. agama")
    ap.add_argument("--rows", type=int, default=25)
    ap.add_argument("--package", help="package_show this dataset on each host that answers")
    ap.add_argument("--datastore", help="datastore_search this resource id")
    ap.add_argument("--limit", type=int, default=5, help="datastore rows to print")
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    args = ap.parse_args()

    global TIMEOUT                                  # noqa: PLW0603
    TIMEOUT = args.timeout

    hosts = hosts_from(args)
    if not hosts:
        ap.error("no hosts given")
    log(f"probe_ckan: {len(hosts)} host(s), timeout {TIMEOUT}s")
    answered: list[str] = []
    ckan: list[str] = []
    for host in hosts:
        scheme, root = reach(host)
        if scheme:
            answered.append(host)
        if not root:
            continue
        ckan.append(host)
        if args.query:
            search(host, scheme, root, args.query, args.rows)
        if args.package:
            package(host, scheme, root, args.package)
        if args.datastore:
            datastore(host, scheme, root, args.datastore, args.limit)
    log(f"probe_ckan: {len(answered)} of {len(hosts)} answered; "
        f"{len(ckan)} speak CKAN: {', '.join(ckan) if ckan else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
