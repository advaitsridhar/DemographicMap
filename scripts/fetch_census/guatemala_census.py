"""Guatemala's 2018 census: pueblo and mother tongue by department and municipality.

INE publishes the whole 2018 enumeration as one database -- a person row for
everyone counted, 399 MB zipped -- on its results portal. Nothing else carries
these two questions below the country: the map's language was a 2002 sample
tabulated by CLEAR Global, and ethnicity was empty. This reads the database in
the runner, counts people by municipality, and writes the counts; the rows
themselves are never kept.

The portal prints a size and a SHA-256 beside the link (399 MB,
C0F23CED...), and on 24 September 2026 it served a different file: 322,771,575
bytes, SHA-256 82C57488... So the printed hash cannot vouch for what arrives,
and the file is vouched for in two other ways before a count is written: the
archive's own CRCs, which catch a damaged download, and INE's published 2018
population of every department, which catch a wrong or altered file.

Usage:
    python -m scripts.fetch_census.guatemala_census --probe
    python -m scripts.fetch_census.guatemala_census --check
    python -m scripts.fetch_census.guatemala_census
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
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


def download(dest: Path) -> str:
    """The database, streamed to disk; its SHA-256, logged beside the published one.

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
            log(f"  the portal prints {SHA256} beside the link: not this file")
        return got
    raise SystemExit("the database could not be downloaded")


def probe(archive: zipfile.ZipFile) -> None:
    """What the archive holds: its files, each CSV's header and rows, and the codebook."""
    for info in archive.infolist():
        log(f"  {info.filename}: {info.file_size:,} bytes")
    bad = archive.testzip()
    log(f"  CRC check: {'every member intact' if bad is None else 'damaged at ' + bad}")
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
            rows = 0
            for rows, row in enumerate(reader, 1):
                if rows > 200_000:
                    continue
                for h, v in zip(header, row):
                    if len(counts[h]) < 60:
                        counts[h][v] += 1
            log(f"   {rows:,} rows")
            for h in header:
                top = counts[h].most_common(12)
                log(f"   {h}: {len(counts[h])} values in the first 200,000 rows; {top}")


def verify(archive: zipfile.ZipFile) -> None:
    """Each CSV against the SHA-256 list INE ships inside the archive."""
    listing = next(i for i in archive.infolist() if i.filename.endswith("SHA256.txt"))
    text = archive.read(listing).decode("utf-8", "replace")
    listed = dict(re.findall(r"Name:\s*(\S+)\s+Size:[^\n]*\n\s*SHA256:\s*([0-9A-F]{64})", text))
    for info in archive.infolist():
        if not info.filename.lower().endswith(".csv"):
            continue
        digest = hashlib.sha256()
        with archive.open(info) as raw:
            while chunk := raw.read(1 << 20):
                digest.update(chunk)
        got = digest.hexdigest().upper()
        base = info.filename.rsplit("/", 1)[-1]
        want = listed.get(base) or listed.get(base.replace(" - ", "_"))
        log(f"  {base}: {info.file_size:,} bytes, sha256 {got}; INE lists "
            f"{want or 'no hash'}{' -- matches' if want == got else ''}")


def dictionary(archive: zipfile.ZipFile, name: str) -> None:
    """Every row of one of INE's data dictionaries, as text."""
    import openpyxl
    info = next(i for i in archive.infolist() if i.filename.endswith(name))
    book = openpyxl.load_workbook(io.BytesIO(archive.read(info)), read_only=True)
    for sheet in book.worksheets:
        log(f"-- {name} / {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c not in (None, "")]
            if cells:
                log("   " + " | ".join(cells))


def totals(archive: zipfile.ZipFile) -> None:
    """People by department: person rows, and the households' own head counts."""
    for suffix, column in (("PERSONA - BDP.csv", None), ("HOGAR_BDP.csv", "TOTAL_PERS")):
        info = next(i for i in archive.infolist() if i.filename.endswith(suffix))
        by_dept: Counter = Counter()
        with archive.open(info) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            for row in reader:
                by_dept[int(row["DEPARTAMENTO"])] += int(row[column]) if column else 1
        log(f"  {suffix}: {sum(by_dept.values()):,} people; by department "
            + ", ".join(f"{d}={n:,}" for d, n in sorted(by_dept.items())))


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "db_csv_.zip"
        download(dest)
        with zipfile.ZipFile(dest) as archive:
            if "--probe" in sys.argv:
                probe(archive)
                return
            if "--check" in sys.argv:
                verify(archive)
                dictionary(archive, "Diccionario_Base_PERSONA.xlsx")
                totals(archive)
                return
            raise SystemExit("only --probe and --check are written yet")


if __name__ == "__main__":
    main()
