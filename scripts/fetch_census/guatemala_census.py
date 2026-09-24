"""Guatemala's 2018 census: pueblo and mother tongue by department and municipality.

INE publishes the whole 2018 enumeration as one database -- a person row for
everyone counted, 399 MB zipped -- on its results portal. Nothing else carries
these two questions below the country: the map's language was a 2002 sample
tabulated by CLEAR Global, and ethnicity was empty. This reads the database in
the runner, counts people by municipality, and writes the counts; the rows
themselves are never kept.

The file is checked against the SHA-256 the portal prints beside the link
before a row is read.

Usage:
    python -m scripts.fetch_census.guatemala_census --probe
    python -m scripts.fetch_census.guatemala_census
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

from ._shared import log

URL = "https://censo2018.ine.gob.gt/archivos/bdd/db_csv_.zip"
SHA256 = "C0F23CED957F7BC126A5A689B728BE143D8B57B74F96CDF31869B28B01B820F9"
UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"


def download(dest: Path) -> None:
    """The database, streamed to disk and checked against the published hash.

    The portal's button submits a form by POST; a GET is tried first, as the
    plainer request, and the form's own method only if the server wants it.
    """
    for method in ("GET", "POST"):
        req = urllib.request.Request(URL, method=method, headers={"User-Agent": UA},
                                     data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
                digest = hashlib.sha256()
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
        except urllib.error.HTTPError as exc:
            log(f"  {method} {URL}: HTTP {exc.code}")
            continue
        got = digest.hexdigest().upper()
        log(f"  {method} {URL}: {dest.stat().st_size:,} bytes, sha256 {got}")
        if got != SHA256:
            raise SystemExit(f"the file's SHA-256 is {got}, not the {SHA256} the portal publishes")
        return
    raise SystemExit("the database could not be downloaded")


def probe(archive: zipfile.ZipFile) -> None:
    """What the archive holds: its files, each CSV's header, and the codebook."""
    for info in archive.infolist():
        log(f"  {info.filename}: {info.file_size:,} bytes")
    for info in archive.infolist():
        name = info.filename.lower()
        if name.endswith((".txt", ".md")) and info.file_size < 200_000:
            log(f"-- {info.filename}")
            log(archive.read(info).decode("utf-8", "replace")[:6000])
        if not name.endswith(".csv"):
            continue
        with archive.open(info) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            first = text.readline()
            delimiter = max(",;|\t", key=first.count)
            header = next(csv.reader([first], delimiter=delimiter))
            reader = csv.reader(text, delimiter=delimiter)
            log(f"-- {info.filename}: {len(header)} columns")
            log("   " + " | ".join(header))
            counts: dict[str, Counter] = {h: Counter() for h in header}
            for n, row in enumerate(reader):
                if n >= 200_000:
                    break
                for h, v in zip(header, row):
                    if len(counts[h]) < 60:
                        counts[h][v] += 1
            for h in header:
                top = counts[h].most_common(12)
                log(f"   {h}: {len(counts[h])} values in the first 200,000 rows; {top}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "db_csv_.zip"
        download(dest)
        with zipfile.ZipFile(dest) as archive:
            if "--probe" in sys.argv:
                probe(archive)
                return
            raise SystemExit("only --probe is written yet")


if __name__ == "__main__":
    main()
