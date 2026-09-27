#!/usr/bin/env python3
"""Uruguay's 2023 census by department and municipio.

Draft: probes only, while INE's microdata files are read. Person-level rows
never leave the runner: the probes print column names and counts of values.

Usage:
    python -m scripts.fetch_census.uruguay_census --probe microdata --catalog 781
    python -m scripts.fetch_census.uruguay_census --probe columns --catalog 781 --file 1503 \
        --count MUNICIPIO,DEPARTAMENTO
"""

from __future__ import annotations

import argparse
import csv
import html
import http.cookiejar
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from ._shared import log

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_tls import completed_context  # noqa: E402

ANDA = "https://www4.ine.gub.uy/Anda5/index.php/catalog/{catalog}"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}


def opener() -> urllib.request.OpenerDirector:
    """Cookies kept, and INE's certificate chain completed from its AIA (still verified)."""
    ctx, _ = completed_context(urllib.parse.urlsplit(ANDA.format(catalog=0)).hostname or "")
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.HTTPCookieProcessor(
                                           http.cookiejar.CookieJar()))


def fetch(open_: urllib.request.OpenerDirector, url: str, data: dict | None = None,
          limit: int | None = None) -> tuple[bytes, dict]:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=HEADERS)
    with open_.open(req, timeout=600) as resp:
        return (resp.read(limit) if limit else resp.read()), dict(resp.headers)


def accept(open_: urllib.request.OpenerDirector, catalog: str) -> str:
    """The catalogue entry's download page, after accepting INE's terms of use."""
    anda = ANDA.format(catalog=catalog)
    fetch(open_, f"{anda}/get-microdata")
    page, _ = fetch(open_, f"{anda}/get-microdata", {"accept": "Aceptar"})
    return page.decode("utf-8", "replace")


def download(open_: urllib.request.OpenerDirector, catalog: str, file_id: str,
             into: Path) -> Path:
    """One of the entry's files, saved on the runner (never committed)."""
    url = f"{ANDA.format(catalog=catalog)}/download/{file_id}"
    req = urllib.request.Request(url, headers=HEADERS)
    with open_.open(req, timeout=1800) as resp:
        name = re.search(r'filename="([^"]+)"', resp.headers.get("Content-Disposition", ""))
        path = into / (name.group(1) if name else f"{file_id}.bin")
        with open(path, "wb") as out:
            shutil.copyfileobj(resp, out, 1 << 20)
    log(f"  {url} -> {path.name} ({path.stat().st_size:,} bytes)")
    return path


def unpack(archive: Path, into: Path) -> list[Path]:
    """The archive's files, by whichever extractor the runner has."""
    into.mkdir(parents=True, exist_ok=True)
    for command in (["7z", "x", "-y", f"-o{into}", str(archive)],
                    ["bsdtar", "-xf", str(archive), "-C", str(into)],
                    ["unrar", "x", "-o+", str(archive), f"{into}/"]):
        if shutil.which(command[0]) is None:
            continue
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode == 0:
            log(f"  unpacked {archive.name} with {command[0]}")
            return sorted(p for p in into.rglob("*") if p.is_file())
        log(f"  {command[0]} failed on {archive.name}: {done.stderr[-300:]}")
    raise SystemExit(f"uruguay_census: nothing on this runner unpacks {archive.name}")


def sniff(path: Path) -> tuple[str, str]:
    """(encoding, delimiter) of a CSV, from its first line."""
    raw = path.open("rb").read(20000)
    encoding, head = "latin-1", raw.decode("latin-1").split("\n", 1)[0]
    try:
        head = raw.decode("utf-8-sig").split("\n", 1)[0]
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        pass
    delimiter = max((",", ";", "\t", "|"), key=head.count)
    return encoding, delimiter


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=["microdata", "columns"])
    ap.add_argument("--catalog", default="781", help="the ANDA catalogue entry")
    ap.add_argument("--file", help="with --probe columns: the entry's file id")
    ap.add_argument("--count", default="", help="columns whose values are counted")
    ap.add_argument("--limit", type=int, default=300, help="values printed per column")
    args = ap.parse_args()
    open_ = opener()
    if args.probe == "microdata":
        text = accept(open_, args.catalog)
        for href, label in re.findall(r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text):
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()
            if "download" in href and "Descarg" in label:
                print(f"  {label[:100]!r} -> {href}")
        return 0
    if args.probe == "columns":
        accept(open_, args.catalog)
        with tempfile.TemporaryDirectory() as tmp:
            archive = download(open_, args.catalog, args.file, Path(tmp))
            for path in unpack(archive, Path(tmp) / "x"):
                print(f"file {path.name}: {path.stat().st_size:,} bytes")
                if path.suffix.lower() != ".csv":
                    continue
                encoding, delimiter = sniff(path)
                with path.open(encoding=encoding, newline="") as fh:
                    reader = csv.reader(fh, delimiter=delimiter)
                    header = next(reader)
                    print(f"  {encoding}, {delimiter!r}, {len(header)} columns: {header}")
                    wanted = [c for c in args.count.split(",") if c]
                    idx = {c: header.index(c) for c in wanted if c in header}
                    missing = [c for c in wanted if c not in header]
                    if missing:
                        print(f"  no such columns: {missing}")
                    counts = {c: Counter() for c in idx}
                    rows = 0
                    for row in reader:
                        rows += 1
                        for c, i in idx.items():
                            counts[c][row[i] if i < len(row) else ""] += 1
                    print(f"  {rows:,} rows")
                    for c, counter in counts.items():
                        print(f"  {c}: {len(counter)} values: "
                              f"{sorted(counter.items())[:args.limit]}")
        return 0
    log("uruguay_census: nothing but probes yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
