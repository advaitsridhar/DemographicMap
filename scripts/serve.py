#!/usr/bin/env python3
"""Static server for local development, with HTTP Range support.

PMTiles works by asking for byte ranges of a single large file, so a dev server
that ignores ``Range`` and returns the whole 79 MB archive on every tile request
makes the map look broken. Python's ``http.server`` does exactly that, hence this
wrapper. It also sends the CORS and cache headers the production host needs, so
what you see locally matches what GitHub Pages serves.

Usage:
    python scripts/serve.py [--port 8899] [--root site]
"""

from __future__ import annotations

import argparse
import os
import re
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class RangeHandler(SimpleHTTPRequestHandler):
    quiet = False
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".pmtiles": "application/octet-stream",
        ".geojson": "application/geo+json",
        ".json": "application/json",
        ".mjs": "text/javascript",
    }

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Expose-Headers",
                         "Content-Range, Content-Length, Accept-Ranges")
        self.send_header("Accept-Ranges", "bytes")
        if self.path.endswith((".pmtiles", ".js", ".css")):
            self.send_header("Cache-Control", "public, max-age=3600")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib naming
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def send_head(self):
        header = self.headers.get("Range")
        if not header:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            fh = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        size = os.fstat(fh.fileno()).st_size
        match = RANGE_RE.fullmatch(header.strip())
        if not match:
            fh.close()
            self.send_error(HTTPStatus.BAD_REQUEST, "Malformed Range header")
            return None

        start_raw, end_raw = match.groups()
        if start_raw:
            start = int(start_raw)
            end = int(end_raw) if end_raw else size - 1
        else:  # suffix range: the last N bytes
            start = max(0, size - int(end_raw or 0))
            end = size - 1
        end = min(end, size - 1)

        if start > end or start >= size:
            fh.close()
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        fh.seek(start)
        return _Slice(fh, end - start + 1)

    def log_message(self, fmt: str, *args: object) -> None:
        if not self.quiet:
            super().log_message(fmt, *args)


class _Slice:
    """A file-like view of ``length`` bytes, so copyfile() stops at the range end."""

    def __init__(self, fh, length: int):
        self.fh = fh
        self.remaining = length

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        want = self.remaining if size is None or size < 0 else min(size, self.remaining)
        chunk = self.fh.read(want)
        self.remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self.fh.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--root", type=Path,
                    default=Path(__file__).resolve().parent.parent / "site")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    RangeHandler.quiet = args.quiet
    handler = partial(RangeHandler, directory=str(args.root))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving {args.root} at http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
