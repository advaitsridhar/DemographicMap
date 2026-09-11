#!/usr/bin/env python3
"""Which hostnames a server's certificate covers, and what its chain is missing.

A statistical office whose HTTPS certificate does not match its own hostname
is not necessarily unreachable -- often the same server answers to another
name that the certificate does cover, and finding that name is the difference
between an adapter and a shrug. Nepal's census portal is one of these: it
answers on censusnepal.cbs.gov.np with a certificate that is not valid for
censusnepal.cbs.gov.np.

The default mode connects without verification *and reads nothing back*. It
reports the certificate's subject and subjectAltName and closes. No request is
sent, no body is read, and nothing here is a route for fetching data over an
untrusted connection: if the certificate names a host that works, the adapter
uses that host over an ordinary verified connection, and if it does not, the
source is unreachable and should be recorded as such.

``--chain`` answers the other failure, which looks the same from the outside
and is not the same at all. *unable to get local issuer certificate* is usually
not a bad certificate: it is a server that sends its leaf and omits the
intermediate that links it to a public root, so the client has the two ends of
a chain and not the middle. A browser hides this -- it caches intermediates it
has seen and fetches the rest through the certificate's Authority Information
Access extension -- and Python's ssl module does neither, so the same server
that works in Chrome fails in urllib. censusindia.gov.in is one of these.

The repair is to supply the missing link, **not to stop checking**: read the
AIA caIssuers URL out of the leaf, fetch that intermediate, add it to a context
that still carries the public roots, and connect again with hostname checking
and CERT_REQUIRED on. An intermediate fetched this way needs no trust of its
own -- it is only believed if it verifies up to a root already trusted, which
is exactly what the handshake then tests. Verification is never turned off
here, and any adapter that reaches such a host must build its context the same
way.

Usage:
    python scripts/probe_tls.py censusnepal.cbs.gov.np,cbs.gov.np
    python scripts/probe_tls.py censusindia.gov.in --chain
    python scripts/probe_tls.py censusindia.gov.in --chain \\
        --fetch https://censusindia.gov.in/nada/index.php/catalog/11398 \\
        --match xlsx,download
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import ssl
import sys
import tempfile
import urllib.parse
import urllib.request

TIMEOUT = 15
# How many intermediates deep the AIA walk will go. A public chain is leaf ->
# one or two intermediates -> root; anything deeper than this is a loop or a
# misconfiguration, and following it forever is not a diagnosis.
MAX_CHAIN = 4


def names(cert: dict) -> list[str]:
    """Every name the certificate claims, from the subject and the SANs.

    The subject is a tuple of relative distinguished names, each of which is
    itself a tuple of (key, value) pairs -- two levels of nesting, not one.
    """
    out = []
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                out.append(f"CN={value}")
    for kind, value in cert.get("subjectAltName", ()):
        out.append(f"{kind}:{value}")
    return out


def decode(der: bytes) -> dict:
    """DER bytes -> the dict ssl would have given for a verified peer.

    ssl cannot parse a certificate to a dict without a file on disk, and
    getpeercert() returns an empty dict when the peer was not verified -- which
    is exactly the case this module exists to look at. So the DER is written
    out and decoded from there.
    """
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        os.write(fd, ssl.DER_cert_to_PEM_cert(der).encode())
        os.close(fd)
        return ssl._ssl._test_decode_cert(path)   # noqa: SLF001
    finally:
        os.unlink(path)


def leaf_der(host: str, port: int = 443) -> bytes:
    """The certificate the server presents, fetched without verifying it.

    Nothing is sent and nothing is read: the handshake alone carries the
    certificate, and the connection is closed as soon as it has been copied.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as tls:
            return tls.getpeercert(binary_form=True) or b""


def ca_issuers(cert: dict) -> tuple[str, ...]:
    """The AIA caIssuers URLs, which are where the missing intermediate lives.

    These are http:// by design and that is not a hole: a certificate fetched
    over plain HTTP is not trusted because of where it came from, it is trusted
    only if it verifies up to a root, which the handshake decides afterwards.
    """
    return tuple(cert.get("caIssuers") or ())


def fetch_der(url: str) -> bytes:
    """One certificate from an AIA URL, as DER, whatever the server wrapped it in.

    Authorities publish these as DER (.crt, .cer) and occasionally as PEM, and
    a few wrap a chain in PKCS#7, which this does not unpack -- it says so
    instead of guessing.
    """
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        blob = resp.read()
    if b"-----BEGIN CERTIFICATE-----" in blob:
        return ssl.PEM_cert_to_DER_cert(blob.decode("ascii", "replace"))
    if blob[:1] != b"\x30":
        raise ValueError(f"not a DER or PEM certificate ({len(blob)} bytes)")
    return blob


def completed_context(host: str, port: int = 443) -> tuple[ssl.SSLContext, list[str]]:
    """A fully verifying context with the intermediates the server left out.

    Returns the context and a log of what was added, so a caller can print the
    repair rather than perform it silently. The context starts from the
    system's own roots and only ever gains certificates; check_hostname and
    CERT_REQUIRED are never touched.
    """
    ctx = ssl.create_default_context()
    notes: list[str] = []
    der = leaf_der(host, port)
    if not der:
        raise ValueError("server presented no certificate")
    for _ in range(MAX_CHAIN):
        cert = decode(der)
        urls = ca_issuers(cert)
        if not urls:
            notes.append("  chain ends here: no AIA caIssuers on this certificate")
            break
        url = urls[0]
        try:
            der = fetch_der(url)
        except Exception as err:                  # noqa: BLE001 - reported
            notes.append(f"  AIA {url} unusable: {type(err).__name__}: {err}")
            break
        issuer = decode(der)
        ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(der))
        notes.append(f"  added intermediate from {url}")
        notes.append(f"    subject {names(issuer)} until {issuer.get('notAfter')}")
        # A self-issued certificate is the root; the chain is complete.
        if issuer.get("subject") == issuer.get("issuer"):
            notes.append("    this is a self-signed root; chain complete")
            break
    return ctx, notes


def verified_opener(host: str, port: int = 443) -> urllib.request.OpenerDirector:
    """An opener that verifies normally, with the server's own chain completed."""
    ctx, _ = completed_context(host, port)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def report(host: str, port: int = 443) -> None:
    print(f"{host}:{port}")
    try:
        der = leaf_der(host, port)
    except Exception as err:                      # noqa: BLE001
        print(f"  unreachable: {type(err).__name__}: {str(err)[:200]}")
        return
    if not der:
        print("  no certificate presented")
        return
    try:
        cert = decode(der)
    except Exception as err:                      # noqa: BLE001
        print(f"  unparsed: {type(err).__name__}: {err}")
        return
    print(f"  issuer: {cert.get('issuer')}")
    print(f"  notAfter: {cert.get('notAfter')}")
    for name in names(cert):
        print(f"  {name}")
    for url in ca_issuers(cert):
        print(f"  AIA caIssuers: {url}")


def report_chain(host: str, port: int = 443) -> ssl.SSLContext | None:
    """Complete the chain, then prove it by handshaking with verification on."""
    print(f"{host}:{port} -- completing the chain from AIA")
    try:
        ctx, notes = completed_context(host, port)
    except Exception as err:                      # noqa: BLE001
        print(f"  cannot read the certificate: {type(err).__name__}: {err}")
        return None
    for note in notes:
        print(note)
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                print(f"  VERIFIED handshake ok, {tls.version()}")
    except Exception as err:                      # noqa: BLE001
        print(f"  still fails with verification on: {type(err).__name__}: {err}")
        return None
    return ctx


def show_links(ctx: ssl.SSLContext, url: str, match: str) -> None:
    """Fetch a page over the repaired connection and print the links that match.

    The same job probe_links does, done here because the whole point is that
    this host cannot be reached with a default context -- so the ordinary probe
    cannot get far enough to list anything.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    opener.addheaders = [("User-Agent", "Mozilla/5.0 (compatible; DemographicMap/1.0)")]
    print(f"\npage: {url}")
    try:
        with opener.open(url, timeout=60) as resp:
            body = resp.read().decode("utf-8", "replace")
            print(f"  {resp.status} {resp.headers.get('Content-Type')} "
                  f"{len(body)} bytes")
    except Exception as err:                      # noqa: BLE001
        print(f"  unreachable: {type(err).__name__}: {str(err)[:300]}")
        return
    wanted = [w.strip().lower() for w in match.split(",") if w.strip()]
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', body):
        full = urllib.parse.urljoin(url, href)
        if full in seen:
            continue
        if wanted and not any(w in full.lower() for w in wanted):
            continue
        seen.add(full)
        print(f"  link: {full}")
        req = urllib.request.Request(full, method="HEAD")
        try:
            with opener.open(req, timeout=60) as head:
                print(f"    {head.status} {head.headers.get('Content-Type')} "
                      f"{head.headers.get('Content-Length')} bytes "
                      f"{head.headers.get('Content-Disposition') or ''}")
        except Exception as err:                  # noqa: BLE001
            print(f"    HEAD failed: {type(err).__name__}: {str(err)[:160]}")
    if not seen:
        print("  no links matched")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hosts", help="comma-separated hostnames")
    ap.add_argument("--chain", action="store_true",
                    help="complete the chain from AIA and re-handshake, verifying")
    ap.add_argument("--fetch", default="",
                    help="with --chain: GET this page over the repaired connection")
    ap.add_argument("--match", default="xlsx,xls,download",
                    help="with --fetch: substrings a link must contain")
    args = ap.parse_args()
    for host in [h.strip() for h in args.hosts.split(",") if h.strip()]:
        if not args.chain:
            report(host)
            continue
        report(host)
        ctx = report_chain(host)
        if ctx is not None and args.fetch:
            show_links(ctx, args.fetch, args.match)
    return 0


if __name__ == "__main__":
    sys.exit(main())
