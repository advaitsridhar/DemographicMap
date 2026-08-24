#!/usr/bin/env python3
"""Which hostnames a server's certificate actually covers.

A statistical office whose HTTPS certificate does not match its own hostname
is not necessarily unreachable -- often the same server answers to another
name that the certificate does cover, and finding that name is the difference
between an adapter and a shrug. Nepal's census portal is one of these: it
answers on censusnepal.cbs.gov.np with a certificate that is not valid for
censusnepal.cbs.gov.np.

This connects without verification *and reads nothing back*. It reports the
certificate's subject and subjectAltName and closes. No request is sent, no
body is read, and nothing here is a route for fetching data over an untrusted
connection: if the certificate names a host that works, the adapter uses that
host over an ordinary verified connection, and if it does not, the source is
unreachable and should be recorded as such.

Usage:
    python scripts/probe_tls.py censusnepal.cbs.gov.np,cbs.gov.np
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys

TIMEOUT = 15


def names(cert: dict) -> list[str]:
    out = []
    for key, value in cert.get("subject", ()):
        for k, v in ((key, value),) if isinstance(key, str) else key:
            if k == "commonName":
                out.append(f"CN={v}")
    for kind, value in cert.get("subjectAltName", ()):
        out.append(f"{kind}:{value}")
    return out


def report(host: str, port: int = 443) -> None:
    print(f"{host}:{port}")
    # No verification, because the whole question is what the certificate says.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                # getpeercert(True) returns DER even when unverified; the parsed
                # form is empty unless the peer was verified, so decode it.
                der = tls.getpeercert(binary_form=True)
    except Exception as err:                      # noqa: BLE001
        print(f"  unreachable: {type(err).__name__}: {str(err)[:200]}")
        return
    if not der:
        print("  no certificate presented")
        return
    try:
        import ssl as _ssl
        text = _ssl.DER_cert_to_PEM_cert(der)
    except Exception as err:                      # noqa: BLE001
        print(f"  undecodable: {err}")
        return
    # ssl cannot parse a PEM to a dict without a file, so write it to one.
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        os.write(fd, text.encode())
        os.close(fd)
        cert = ssl._ssl._test_decode_cert(path)   # noqa: SLF001
    except Exception as err:                      # noqa: BLE001
        print(f"  unparsed: {type(err).__name__}: {err}")
        return
    finally:
        os.unlink(path)
    print(f"  issuer: {cert.get('issuer')}")
    print(f"  notAfter: {cert.get('notAfter')}")
    for name in names(cert):
        print(f"  {name}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hosts", help="comma-separated hostnames")
    args = ap.parse_args()
    for host in [h.strip() for h in args.hosts.split(",") if h.strip()]:
        report(host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
