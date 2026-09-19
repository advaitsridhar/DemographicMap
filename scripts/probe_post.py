#!/usr/bin/env python3
"""What a form-driven download answers, before an adapter is written against it.

Some statistical sites serve their tables only through an HTML form that
posts its fields to a download endpoint -- the Ministry of the Interior's
resident-register site (jumin.mois.go.kr) builds a CSV from a dozen hidden
inputs and a ``downloadCsv.do`` action, and nothing on it is a link. The
fields are readable in the page source (``probe_links --find '<input[^>]*'``
prints them); which values the endpoint accepts, and what it sends back,
only a request settles. This makes that one request and reports what came
back: status, content type and disposition, size, and the first lines of
the body decoded as the server says or as ``--charset`` says.

Nothing is written; the output is the log. A body that is a zip or a
binary workbook is said to be one rather than printed.

Usage:
    python -m scripts.probe_post https://example.org/download.do \\
        --field tableId=month --field searchYearStart=2023 --lines 20
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import USER_AGENT, log  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--field", action="append", default=[], metavar="NAME=VALUE",
                    help="a form field; repeat for each")
    ap.add_argument("--lines", type=int, default=20, help="body lines to print")
    ap.add_argument("--width", type=int, default=200, help="characters per printed line")
    ap.add_argument("--charset", default=None, help="decode the body as this instead")
    ap.add_argument("--terms", default="", help="comma-separated: print only lines with one")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    fields = []
    for item in args.field:
        name, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"probe_post: --field {item!r} is not NAME=VALUE")
        fields.append((name, value))
    data = urllib.parse.urlencode(fields).encode()
    log(f"probe_post: {args.url}")
    log(f"  {len(fields)} field(s): {', '.join(n for n, _ in fields)}")
    req = urllib.request.Request(args.url, data=data, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            body = resp.read()
            status = resp.status
            headers = dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
        headers = dict(exc.headers)
    ctype = headers.get("Content-Type", "")
    log(f"  {status} {ctype} size={len(body):,}")
    if headers.get("Content-Disposition"):
        log(f"  disposition: {headers['Content-Disposition']}")
    if body[:2] == b"PK":
        log("  body is a zip (or an xlsx)")
        return 0
    if body[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        log("  body is a legacy .xls workbook")
        return 0
    charset = args.charset
    if not charset:
        found = re.search(r"charset=([\w-]+)", ctype)
        charset = found.group(1) if found else ("utf-8" if b"\xef\xbb\xbf" == body[:3] else "cp949")
    text = body.decode(charset, "replace")
    terms = [t for t in args.terms.split(",") if t]
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    log(f"  {len(lines):,} non-blank line(s) decoded as {charset}")
    shown = 0
    for ln in lines:
        if terms and not any(t in ln for t in terms):
            continue
        log("  " + ln[:args.width])
        shown += 1
        if shown >= args.lines:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
