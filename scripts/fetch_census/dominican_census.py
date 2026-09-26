#!/usr/bin/env python3
"""The Dominican Republic's census, tabulated on ONE's REDATAM WebServer.

ONE's own site refused this map's reader (HTTP 403), and its REDATAM server,
redatam.one.gob.do, sends its leaf certificate without the intermediate above
it, which Python reports as *unable to get local issuer certificate*. The
chain is completed from the certificate's own Authority Information Access
extension and verified in full (scripts/probe_tls.py, as argentina_census.py
does for censo.gob.ar); nothing here turns a check off.

``--probe`` opens the server's portals and prints what each base offers;
``--run`` sends one Redatam+SP program and prints the tables parsed back.

Usage:
    python -m scripts.fetch_census.dominican_census --probe CPV2010,CPV2022
    python -m scripts.fetch_census.dominican_census --run CPV2010 FREQUENCY OF PERSONA.P27 AREABREAK PROVIN
"""

from __future__ import annotations

import argparse
import http.cookiejar
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.probe_redatam import Session, attrs, report

from .redatam import Server, tables

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_tls import ca_issuers, decode, leaf_der  # noqa: E402

HOST = "redatam.one.gob.do"
ROOT = f"https://{HOST}"
PORTAL = ROOT + "/bindom/RpWebEngine.exe/Portal?BASE={base}&lang=esp"
CMDSET = ROOT + "/bindom/RpWebStats.exe/CmdSet"


def certificates(blob: bytes) -> list[bytes]:
    """Every certificate an AIA URL serves, as DER: PEM, DER or a PKCS#7 bundle."""
    if b"-----BEGIN CERTIFICATE-----" in blob:
        return [ssl.PEM_cert_to_DER_cert(p) for p in re.findall(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            blob.decode("ascii", "replace"), re.S)]
    try:
        decode(blob)
        return [blob]
    except ssl.SSLError:
        from cryptography.hazmat.primitives.serialization import Encoding, pkcs7
        return [c.public_bytes(Encoding.DER) for c in pkcs7.load_der_pkcs7_certificates(blob)]


def chained_context(host: str) -> tuple[ssl.SSLContext, list[str]]:
    """The system's own roots plus the intermediates the server did not send.

    The same repair as probe_tls.completed_context, stricter in one respect:
    a self-signed certificate fetched from an AIA URL is never added, so the
    chain must still end at a root the system already trusts. Only the links
    between are taken from the network, and they are believed only if they
    verify up to that root, which the handshake then tests.
    """
    context = ssl.create_default_context()
    notes: list[str] = []
    der = leaf_der(host)
    for _ in range(4):
        urls = ca_issuers(decode(der))
        if not urls:
            break
        with urllib.request.urlopen(urls[0], timeout=30) as resp:
            found = certificates(resp.read())
        links = [c for c in found if decode(c).get("subject") != decode(c).get("issuer")]
        for link in links:
            context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(link))
        notes.append(f"  {urls[0]}: {len(found)} certificate(s), {len(links)} intermediate(s) "
                     "added; a root is never taken from the network")
        if not links:
            break
        der = links[0]
    return context, notes


class ChainSession(Session):
    """A REDATAM session over a verified connection with the chain completed."""

    def __init__(self, host: str = HOST) -> None:
        context, notes = chained_context(host)
        for note in notes:
            print(note)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def probe(session: ChainSession, bases: list[str], follow: str, limit: int) -> None:
    for page_url in [ROOT + "/", *[PORTAL.format(base=b) for b in bases]]:
        print(f"page: {page_url}")
        try:
            page = session.get(page_url)
        except Exception as exc:  # noqa: BLE001 - the probe reports what it met
            print(f"  {type(exc).__name__}: {exc}")
            continue
        links = report(page_url, page, limit)
        frames = [urllib.parse.urljoin(page_url, attrs(t)["src"])
                  for t in re.findall(r"(?is)<i?frame\b[^>]*>", page) if attrs(t).get("src")]
        words = [w for w in follow.split(",") if w]
        for label, url in [("frame", f) for f in frames] + [
                (label, url) for label, url in links if any(w in label for w in words)]:
            print(f"follow: {label!r} -> {url}")
            try:
                body = session.get(url)
            except Exception as exc:  # noqa: BLE001
                print(f"  {type(exc).__name__}: {exc}")
                continue
            report(url, body, limit)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", help="comma-separated base names whose portals to open")
    ap.add_argument("--follow", default="", help="comma-separated words of links to open")
    ap.add_argument("--run", nargs="+", metavar="WORD",
                    help="a base name, then a Redatam+SP program as words")
    ap.add_argument("--header", default="Casos")
    ap.add_argument("--limit", type=int, default=3000)
    args = ap.parse_args()
    session = ChainSession()
    if args.probe:
        probe(session, args.probe.split(","), args.follow, args.limit)
    if args.run:
        base, *words = args.run
        text = re.sub(r"\s+(?=(?:TABLE|AS|OF|BY|AREABREAK|DEFINE|TYPE|FOR|UNIVERSE)\s)",
                      "\n    ", " ".join(words))
        program = "RUNDEF Job\n    SELECTION ALL\n\nTABLE T1\n    " + text + "\n"
        print(program)
        session.get(PORTAL.format(base=base))
        server = Server(CMDSET, base, session=session, who="dominican_census")
        for page in server.output(program):
            report(CMDSET, page, args.limit)
            for t in tables(page, args.header):
                print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                      f"total={t['total']} na={t['na']} rows={t['rows'][:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
