#!/usr/bin/env python3
"""Which of the site's own files a reader's content blocker would refuse.

Guatemala's second-level file is ``data/admin2/GTM.json``, and EasyPrivacy --
on by default in uBlock Origin, the blocker most Firefox readers run -- has
network filters aimed at Google Tag Manager's ``gtm.js``. A filter is matched
against the whole URL, case-blind, so ``/gtm.js`` finds itself inside
``/GTM.json``: the file never arrives, and the map says it could not load the
country, every time, in that browser only. No check of the data can see this,
because the data is fine; only the blocklists can.

This fetches the lists uBlock Origin and AdBlock Plus enable by default, turns
their network filters into patterns (``||`` domain anchor, ``|`` start or end
anchor, ``*`` wildcard, ``^`` separator), and tests every file under site/ as
the live page requests it. A filter whose options confine it to other
resource types is still reported, with its options, because the map fetches
its data by XHR and the options decide the verdict. Exceptions (``@@``) that
match are reported beside it.

Read-only; the output is the log.

Usage:
    python -m scripts.probe_blocklists            # runner: fetches the lists
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://advaitsridhar.github.io/DemographicMap/"
LISTS = {
    "EasyList": "https://easylist.to/easylist/easylist.txt",
    "EasyPrivacy": "https://easylist.to/easylist/easyprivacy.txt",
    "uBO filters": "https://ublockorigin.github.io/uAssets/filters/filters.txt",
    "uBO privacy": "https://ublockorigin.github.io/uAssets/filters/privacy.txt",
    "uBO badware": "https://ublockorigin.github.io/uAssets/filters/badware.txt",
    "uBO unbreak": "https://ublockorigin.github.io/uAssets/filters/unbreak.txt",
    "Peter Lowe": "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=adblockplus&mimetype=plaintext",
}
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}


def pattern(body: str) -> re.Pattern | None:
    """An ABP network filter body as a regular expression over a URL."""
    if body.startswith("/") and body.endswith("/") and len(body) > 2:
        try:
            return re.compile(body[1:-1], re.I)
        except re.error:
            return None
    out = ""
    if body.startswith("||"):
        out, body = r"^[a-z-]+://([^/]*\.)?", body[2:]
    elif body.startswith("|"):
        out, body = "^", body[1:]
    end = body.endswith("|")
    body = body[:-1] if end else body
    for ch in body:
        out += {"*": ".*", "^": r"(?:[^\w.%-]|$)"}.get(ch, re.escape(ch))
    return re.compile(out + ("$" if end else ""), re.I)


def literal(body: str) -> str:
    """The longest plain run in a filter, to skip filters no URL could match."""
    runs = re.split(r"[*^|]", body.strip("|"))
    return max(runs, key=len).lower() if runs else ""


def site_urls() -> list[str]:
    out = []
    for path in sorted((ROOT / "site").rglob("*")):
        if path.is_file():
            out.append(SITE + path.relative_to(ROOT / "site").as_posix() + "?v=0123456789ab")
    return out


def main() -> int:
    urls = site_urls()
    haystack = "\n".join(urls).lower()
    print(f"{len(urls)} site files")
    found = 0
    for name, url in LISTS.items():
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - a list that fails is reported, not fatal
            print(f"{name}: unreachable ({exc})")
            continue
        rules = [line.strip() for line in text.splitlines()]
        rules = [r for r in rules if r and not r.startswith(("!", "[")) and "##" not in r
                 and "#@#" not in r and "#?#" not in r and "#$#" not in r]
        print(f"{name}: {len(rules)} network filters")
        for rule in rules:
            exception = rule.startswith("@@")
            body, _, options = (rule[2:] if exception else rule).partition("$")
            lit = literal(body)
            if len(lit) >= 3 and lit not in haystack:
                continue
            rx = pattern(body)
            if rx is None:
                continue
            hits = [u for u in urls if rx.search(u)]
            if hits:
                found += 1
                kind = "EXCEPTION" if exception else "BLOCK"
                shown = ", ".join(h.replace(SITE, "") for h in hits[:6])
                more = f" (+{len(hits) - 6} more)" if len(hits) > 6 else ""
                print(f"  {kind} {rule!r} [{options or 'all types'}] -> {shown}{more}")
    print(f"{found} filters match a site file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
