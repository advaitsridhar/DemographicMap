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
the live page requests it. Only filters in force for these requests are
kept: not one confined to other sites (``domain=``), to third-party requests,
or to resource types other than the xhr the map's fetch() is filed as.
Exceptions (``@@``) that match are reported beside it.

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


HOST = "advaitsridhar.github.io"
TYPES = {"script", "image", "stylesheet", "css", "object", "subdocument", "frame", "font",
         "media", "websocket", "ping", "other", "xmlhttprequest", "xhr", "document", "doc",
         "popup", "inline-script", "inline-font"}
MODIFIERS = {"removeparam", "queryprune", "uritransform", "urlskip", "redirect-rule", "csp",
             "header", "permissions", "replace", "to", "ipaddress", "strict3p", "strict1p",
             "cname", "denyallow", "responseheader", "method"}
# The map reads its data and tiles with fetch(), which a blocker files as xhr.
OURS = {"xmlhttprequest", "xhr", "other"}


def applies(options: str) -> bool:
    """Whether a filter's options leave it in force for this site's own fetches."""
    opts = [o.strip() for o in options.split(",") if o.strip()]
    if "badfilter" in opts:
        return False
    # Filters that rewrite or redirect rather than refuse a request.
    if any(o.split("=")[0].lstrip("~") in MODIFIERS for o in opts):
        return False
    for opt in opts:
        key, _, value = opt.partition("=")
        if key in ("domain", "from"):
            sites = [d for d in value.split("|") if not d.startswith("~")]
            if sites and not any(HOST.endswith(d) or d in ("github.io",) for d in sites):
                return False
        if key in ("3p", "third-party"):
            return False            # the site's files are all first party
    kinds = [o for o in opts if o.lstrip("~") in TYPES]
    wanted = [k for k in kinds if not k.startswith("~")]
    unwanted = [k[1:] for k in kinds if k.startswith("~")]
    if wanted:
        return any(k in OURS for k in wanted)
    return not any(k in OURS for k in unwanted)


def site_urls() -> list[str]:
    out = []
    for path in sorted((ROOT / "site").rglob("*")):
        if path.is_file():
            out.append(SITE + path.relative_to(ROOT / "site").as_posix() + "?v=0123456789ab")
    return out


def candidate_urls(template: str) -> list[str]:
    """Every country's shard at both levels under another naming scheme."""
    codes = sorted({f.name.split(".")[0] for f in (ROOT / "site" / "data" / "admin1").glob("*.json")})
    return [SITE + "data/" + template.format(level=level, iso=iso) + "?v=0123456789ab"
            for level in ("admin1", "admin2") for iso in codes]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", action="append", default=[],
                    help="test shard names under this scheme too, e.g. '{level}/{iso}.units.json'")
    args = ap.parse_args()
    urls = site_urls()
    for template in args.template:
        urls += candidate_urls(template)
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
            if not applies(options):
                continue
            if body.strip("*|") == "":
                continue            # every URL: a modifier's carrier, not a block
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
