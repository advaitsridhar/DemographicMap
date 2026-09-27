#!/usr/bin/env python3
"""Uruguay's 2023 census by department and municipio.

Draft: probes only, while INE's microdata files are read. Person-level rows
never leave the runner: the probes print column names and counts of values.

Usage:
    python -m scripts.fetch_census.uruguay_census --probe microdata --catalog 781
    python -m scripts.fetch_census.uruguay_census --probe columns --catalog 781 --file 1503 \
        --count MUNICIPIO_136,DEPARTAMENTO --weight W
    python -m scripts.fetch_census.uruguay_census --probe ddi --catalog 781 --vars PERER02
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
    """(encoding, delimiter) of a CSV, from its first 8 MB.

    INE's personas file has an ASCII header and Latin-1 further down, so the
    first line alone reads as UTF-8 and the file then fails a hundred MB in.
    """
    with path.open("rb") as fh:
        raw = fh.read(8 << 20)
    raw = raw[:raw.rfind(b"\n") + 1] or raw
    encoding = "latin-1"
    try:
        raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        pass
    head = raw.decode(encoding, "replace").split("\n", 1)[0]
    delimiter = max((",", ";", "\t", "|"), key=head.count)
    return encoding, delimiter


DDI = ("https://www4.ine.gub.uy/Anda5/index.php/metadata/export/{catalog}/ddi",
       "https://www4.ine.gub.uy/Anda5/index.php/catalog/{catalog}/export/ddi",
       "https://www4.ine.gub.uy/Anda5/index.php/ddibrowser/{catalog}/export/?format=ddi")


def ddi_text(fragment: str) -> str:
    fragment = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", fragment, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def ddi_variables(xml: str) -> dict[str, dict]:
    """Each variable of a DDI codebook: its label, file and categories."""
    out: dict[str, dict] = {}
    for m in re.finditer(r"(?s)<(?:\w+:)?var\b([^>]*)>(.*?)</(?:\w+:)?var>", xml):
        attrs, body = m.group(1), m.group(2)
        name = re.search(r'\bname="([^"]+)"', attrs)
        if not name:
            continue
        label = re.search(r"(?s)<(?:\w+:)?labl\b[^>]*>(.*?)</(?:\w+:)?labl>", body)
        cats = [(ddi_text(v), ddi_text(lab)) for v, lab in re.findall(
            r"(?s)<(?:\w+:)?catgry\b[^>]*>.*?<(?:\w+:)?catValu>(.*?)</(?:\w+:)?catValu>"
            r".*?<(?:\w+:)?labl\b[^>]*>(.*?)</(?:\w+:)?labl>.*?</(?:\w+:)?catgry>", body)]
        files = re.search(r'\bfiles="([^"]+)"', attrs)
        out[name.group(1)] = {"label": ddi_text(label.group(1)) if label else "",
                              "file": files.group(1) if files else "", "categories": cats}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=["microdata", "columns", "ddi"])
    ap.add_argument("--catalog", default="781", help="the ANDA catalogue entry")
    ap.add_argument("--file", help="with --probe columns: the entry's file id")
    ap.add_argument("--count", default="", help="columns whose values are counted")
    ap.add_argument("--limit", type=int, default=300, help="values printed per column")
    ap.add_argument("--weight", default="", help="with --probe columns: sum this column too")
    ap.add_argument("--vars", default="", help="with --probe ddi: variables printed in full")
    args = ap.parse_args()
    open_ = opener()
    if args.probe == "ddi":
        for template in DDI:
            url = template.format(catalog=args.catalog)
            try:
                body, headers = fetch(open_, url)
            except Exception as err:                  # noqa: BLE001
                print(f"{url}: {type(err).__name__}: {str(err)[:200]}")
                continue
            xml = body.decode("utf-8", "replace")
            print(f"{url}: {len(body):,} bytes, {headers.get('Content-Type')}")
            for fid, fname in re.findall(
                    r'(?s)<(?:\w+:)?fileDscr\b[^>]*ID="([^"]+)".*?'
                    r"<(?:\w+:)?fileName>(.*?)</(?:\w+:)?fileName>", xml):
                print(f"  file {fid}: {fname.strip()}")
            found = ddi_variables(xml)
            if not found:
                print(f"  no variables; starts {xml[:300]!r}")
                continue
            wanted = [v for v in args.vars.split(",") if v]
            for name, var in found.items():
                cats = var["categories"]
                shown = f": {cats[:args.limit]}" if name in wanted else ""
                print(f"  {var['file']} {name}: {var['label']!r}; {len(cats)} categories{shown}")
            return 0
        return 1
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
                with path.open(encoding=encoding, errors="replace", newline="") as fh:
                    reader = csv.reader(fh, delimiter=delimiter)
                    header = next(reader)
                    print(f"  {encoding}, {delimiter!r}, {len(header)} columns: {header}")
                    wanted = [c for c in args.count.split(",") if c]
                    idx = {c: header.index(c) for c in wanted if c in header}
                    missing = [c for c in wanted if c not in header]
                    if missing:
                        print(f"  no such columns: {missing}")
                    counts = {c: Counter() for c in idx}
                    weights = {c: Counter() for c in idx}
                    w = header.index(args.weight) if args.weight in header else None
                    rows, total = 0, 0.0
                    for row in reader:
                        rows += 1
                        weight = float(row[w].replace(",", ".") or 0) if w is not None else 0.0
                        total += weight
                        for c, i in idx.items():
                            value = row[i] if i < len(row) else ""
                            counts[c][value] += 1
                            weights[c][value] += weight
                    print(f"  {rows:,} rows; {args.weight or 'no weight'} sums to {total:,.3f}")
                    for c, counter in counts.items():
                        print(f"  {c}: {len(counter)} values: "
                              f"{sorted(counter.items())[:args.limit]}")
                        if w is not None:
                            summed = [(k, round(v, 2)) for k, v in sorted(weights[c].items())]
                            print(f"  {c} weighted: {summed[:args.limit]}")
        return 0
    log("uruguay_census: nothing but probes yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
