#!/usr/bin/env python3
"""Indonesia's federated open-data portals, for the regencies the infobox
could not answer for.

``indonesia.py`` reads each kabupaten's religion from its own Indonesian
Wikipedia infobox and refuses a figure that carries no citation or no year.
That left 55 of the 513 regency shapes empty -- not because Indonesia does not
count religion, but because the article's editor did not say where the numbers
came from. BPS itself answers an automated reader 403 on every host it owns.

Indonesia's **Satu Data** is federated: each province and many regencies run
their own portal, and a good number of them are CKAN with the datastore open.
That is the Singapore pattern -- an office that refuses a reader publishes the
same tables somewhere that does not -- and it is where the tables in this
module come from. ``scripts/probe_ckan.py`` walked 113 hostnames to find them
and ``docs/SOURCES.md`` records the status of every one.

Four tables were found, and between them they cover **eight** of the 55:

* **West Sumatra**, all 19 kabupaten and kota. The provincial civil-registry
  office's *Buku Data Kependudukan Semester II 2023*, sheet ``AGAMA - JENIS
  KELAMIN``, on ``data.sumbarprov.go.id``. Fills Kota Bukittinggi, Kota
  Pariaman, Kota Payakumbuh, Kota Sawah Lunto and Pasaman.
* **East Kalimantan**, all 10. *Data Jumlah Pemeluk Agama per KabKot Prov.
  Kaltim Tahun 2023*, published on ``data.kaltimprov.go.id`` by the province's
  Kanwil Kementerian Agama -- a ministry count of adherents, not a registry.
  Fills Kota Samarinda.
* **Bengkulu**, all 10. The provincial civil-registry office's *Data Jumlah
  Penduduk Provinsi Bengkulu Menurut Agama Tahun 2024*, on
  ``data.bengkuluprov.go.id``. Fills Lebong.
* **Kota Tangerang Selatan**, by kecamatan, summed to the city. Its own
  registry office's *Data Konsolidasi Bersih 2021*, on
  ``data.tangerangselatankota.go.id``.

**Which column is Protestant.** Dukcapil's tables have a "Kristen" column and
a "Katolik" column, and in its own usage "Kristen" is the Protestant one. The
West Sumatra workbook heads them the other way round, "KATHOLIK" before
"KRISTEN", over data in the usual order -- the same office's Pasaman file
(``data.pasamankab.go.id``) prints the identical 2023 figures under the labels
the other way. Rather than decide that by reading, ``resolve_pair`` measures
it: for every unit in the table that already carries a composition read from
its article, it scores both assignments against that composition and takes the
winner, refusing unless the winner is decisively better. On West Sumatra the
swapped reading wins on all 14 checkable regencies -- Kota Padang's 14,230 is
1.52% of the city, which is exactly the Protestant share Dukcapil's own
visualisation publishes -- and on Bengkulu and East Kalimantan the printed
order wins. Nothing here assumes; the run says what it found.

``--fetch`` writes each table into ``data/raw/indonesia_portals/`` as a long
CSV of unit, faith and count, and the adapter reads those, so a build with no
network still runs and what was served is committed beside the code that read
it.

Usage:
    python -m scripts.fetch_census.indonesia_portals --fetch   # refresh the CSVs
    python -m scripts.fetch_census.indonesia_portals           # print what they hold
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import RAW, log  # noqa: E402

from ._shared import measure  # noqa: E402

RAWDIR = RAW / "indonesia_portals"
LICENCE = "Official statistics; compilation CC BY-SA 4.0"

# Honest and identifying; no portal in this module asked for anything else.
HEADERS = {"User-Agent": "DemographicMap/1.0 "
                         "(+https://github.com/advaitsridhar/DemographicMap)"}
TIMEOUT = 120

# The faith names these tables use -> the label the map carries. "Kristen"
# alone would be Christianity, but in a Dukcapil or Kemenag table it stands
# beside a Katolik column and means the Protestant half of it; which column is
# which is not taken on trust, see resolve_pair.
FAITHS: dict[str, str] = {
    "islam": "Islam",
    "kristen": "Protestantism", "protestan": "Protestantism",
    "kristen protestan": "Protestantism",
    "katolik": "Catholicism", "katholik": "Catholicism",
    "kristen katolik": "Catholicism",
    "hindu": "Hinduism",
    "budha": "Buddhism", "buddha": "Buddhism",
    "konghucu": "Confucianism", "khonghucu": "Confucianism",
    "kepercayaan": "Kepercayaan (traditional belief)",
    "kepercayaan terhadap tuhan": "Kepercayaan (traditional belief)",
    "kepercayaan terhadap tuhan yme": "Kepercayaan (traditional belief)",
    "aliran kepercayaan": "Kepercayaan (traditional belief)",
}
# The pair whose order the workbooks disagree about.
PAIR = ("Protestantism", "Catholicism")
# A row of the table that is the whole province, or an arithmetic footer.
NOT_A_UNIT = re.compile(r"^(?:%|(?:total|jumlah|provinsi|prov\.?|sumber)\b)", re.I)


class Source(NamedTuple):
    key: str                 # the CSV's basename under data/raw/indonesia_portals
    province: str            # the map's province name
    host: str                # the portal, for the record's source URL
    dataset: str             # the CKAN package
    url: str                 # the resource actually read
    year: int
    kind: str                # 'dukcapil' or 'kemenag', as indonesia.py names them
    publisher: str
    title: str
    reader: str              # which of the shapes below the file has
    native: str = ""         # the province as the table writes it: a row, not a unit
    sums_to: str | None = None   # a table by kecamatan is summed to this unit


SOURCES: tuple[Source, ...] = (
    Source(
        key="sumbar",
        province="West Sumatra",
        host="data.sumbarprov.go.id",
        dataset="buku-data-kependudukan-semester-ii-tahun-2023-prov-sumatera-barat",
        url="https://data.sumbarprov.go.id/dataset/76470dbf-cddc-46bd-90f1-966f5a428aa1"
            "/resource/418513f6-c45b-40fb-9151-61df45d5ee81/download/agama-jenis-kelamin.xlsx",
        year=2023,
        kind="dukcapil",
        publisher="Dinas Kependudukan dan Pencatatan Sipil Provinsi Sumatera Barat",
        title="Buku Data Kependudukan Semester II 2023, tabel Agama - Jenis Kelamin",
        reader="wide_xlsx",
        native="Sumatera Barat",
    ),
    Source(
        key="kaltim",
        province="East Kalimantan",
        host="data.kaltimprov.go.id",
        dataset="data-jumlah-pemeluk-agama-provinsi-kaltim-tahun-2021",
        url="https://data.kaltimprov.go.id/dataset/4dd429f3-3cc7-461d-8dd4-2f221c9c8c15"
            "/resource/31b549ab-6cda-4d27-82c7-c991d1f9fde0/download/"
            "data-jumlah-pemeluk-agama-per-kabkot-prov.-kaltim-tahun-2023.xlsx",
        year=2023,
        kind="kemenag",
        publisher="Kanwil Kementerian Agama Provinsi Kalimantan Timur",
        title="Data Jumlah Pemeluk Agama per Kabupaten/Kota Prov. Kaltim Tahun 2023",
        reader="wide_xlsx",
        native="Kalimantan Timur",
    ),
    Source(
        key="bengkulu",
        province="Bengkulu",
        host="data.bengkuluprov.go.id",
        dataset="data-jumlah-penduduk-menurut-agama-tahun-2024",
        url="https://data.bengkuluprov.go.id/dataset/192aeb53-6c0c-4aca-9c06-e879ce3861e6"
            "/resource/cc6c8dd4-639b-426f-bc80-76cdbf267c36/download/"
            "data-jumlah-penduduk-provinsi-bengkulu-menurut-agama-tahun-2024.xlsx",
        year=2024,
        kind="dukcapil",
        publisher="Dinas Kependudukan dan Pencatatan Sipil Provinsi Bengkulu",
        title="Data Jumlah Penduduk Provinsi Bengkulu Menurut Agama Tahun 2024",
        reader="wide_xlsx",
        native="Provinsi Bengkulu",
    ),
    Source(
        key="tangsel",
        province="Banten",
        host="data.tangerangselatankota.go.id",
        dataset="jumlah-penduduk-menurut-kecamatan-dan-di-agama-kota-tangerang-selatan-tahun-2021",
        url="https://data.tangerangselatankota.go.id/dataset/"
            "72e8d9bc-1c7d-491a-af72-77e8aa3fb18f/resource/"
            "2575b89b-a403-4829-8aab-bdbff1785a4a/download/"
            "1d.-jumlah-penduduk-menurut-kecamatan-dan-di-agama-kota-tangerang-selatan-"
            "data-konsolidasi-bersi.csv",
        year=2021,
        kind="dukcapil",
        publisher="Dinas Kependudukan dan Pencatatan Sipil Kota Tangerang Selatan",
        title="Jumlah Penduduk Menurut Kecamatan dan Agama, Data Konsolidasi Bersih 2021",
        reader="wide_csv",
        native="Kota Tangerang Selatan",
        sums_to="Kota Tangerang Selatan",
    ),
)

# The table's spelling of a unit -> the map's. Only where they differ; the
# comparison is otherwise on the name with its Kabupaten/Kota prefix and its
# punctuation taken off, so "Kab. Kutai Kartanegara" finds "Kutai Kartanegara"
# without an entry here.
ALIASES: dict[str, str] = {
    "kota sawahlunto": "Kota Sawah Lunto",
    "kota pematangsiantar": "Kota Pematang Siantar",
    "banyuasin": "Banyu Asin",
    # The regency is Mahakam Ulu in its own province's tables and Mahakam Hulu
    # in the boundary file; ulu and hulu are the same word.
    "mahakam ulu": "Mahakam Hulu",
}


# ---------------------------------------------------------------------------
# Fetching, and the committed CSVs
# ---------------------------------------------------------------------------

def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def clean(text: Any) -> str:
    return " ".join(str(text if text is not None else "").split())


def as_count(cell: Any) -> int | None:
    """A cell that is a count, or None. A share, a code and a blank are None."""
    text = clean(cell).replace(".", "").replace(",", "").replace(" ", "")
    if not text or not re.fullmatch(r"\d+", text):
        return None
    return int(text)


def faith_of(header: str) -> str | None:
    """The map's label for a column heading, or None if it is not a faith.

    A heading is "ISLAM", "ISLAM (L)", "ISLAM(JML)" or "Kepercayaan terhadap
    Tuhan"; the sex in brackets is dropped and the halves are added, and a
    workbook that also prints a (JML) column would double the faith, so the
    totals column is skipped where the parts are there.
    """
    key = clean(header).lower()
    key = re.sub(r"\s*\((?:l|lk|p|pr|jml|jumlah|laki-laki|perempuan)\)\s*$", "", key)
    key = re.sub(r"^agama\s+", "", key).strip(" .:")
    return FAITHS.get(key)


def is_total_column(header: str) -> bool:
    return bool(re.search(r"\((?:jml|jumlah)\)\s*$", clean(header), re.I))


def rows_from_grid(grid: list[list[Any]], label_column_names: Iterable[str],
                   skip: str = "") -> list[tuple[str, dict[str, int]]]:
    """(unit, {faith: count}) for a table whose faiths are its columns.

    The header is found by content -- the first row holding a cell that names
    a faith -- because these workbooks put a title, a blank and sometimes a
    numbered "(1) (2) (3)" row above it, and no two of them the same way.
    """
    wanted = [clean(n).lower() for n in label_column_names]
    header_at = None
    for i, row in enumerate(grid):
        if sum(1 for cell in row if faith_of(cell)) >= 2:
            header_at = i
            break
    if header_at is None:
        raise SystemExit("indonesia_portals: no header row naming two faiths")
    header = grid[header_at]
    label_at = None
    for name in wanted:                       # in priority order, see LABELS
        label_at = next((j for j, cell in enumerate(header)
                         if clean(cell).lower() == name), None)
        if label_at is not None:
            break
    if label_at is None:
        raise SystemExit(f"indonesia_portals: no unit column in {header}")
    # Where a faith has both halves and a total, the total is redundant; where
    # it has only a total, that is the figure.
    columns: dict[int, str] = {}
    have_parts: set[str] = set()
    for j, cell in enumerate(header):
        faith = faith_of(cell)
        if faith and not is_total_column(cell):
            have_parts.add(faith)
    for j, cell in enumerate(header):
        faith = faith_of(cell)
        if not faith:
            continue
        if is_total_column(cell) and faith in have_parts:
            continue
        columns[j] = faith
    out: list[tuple[str, dict[str, int]]] = []
    for row in grid[header_at + 1:]:
        unit = clean(row[label_at]) if label_at < len(row) else ""
        if not unit or NOT_A_UNIT.match(unit) or (skip and normal(unit) == normal(skip)):
            continue
        counts: dict[str, int] = {}
        for j, faith in columns.items():
            value = as_count(row[j]) if j < len(row) else None
            if value is not None:
                counts[faith] = counts.get(faith, 0) + value
        if counts and sum(counts.values()) > 0:
            out.append((unit, counts))
    return out


# Where the unit's name is, most particular first. "No." is deliberately last:
# three of these four sheets have a row number in their first column, and the
# East Kalimantan one headed "No. | Kabupaten / Kota" gave ten regencies named
# 1 to 10 when the first matching column won.
LABELS = ("kabupaten / kota", "kabupaten/kota", "provinsi / kabupaten",
          "provinsi/kabupaten", "wilayah/kecamatan", "nama kecamatan",
          "wilayah", "kabupaten", "kecamatan", "no.")


def read_wide_xlsx(payload: bytes, skip: str = "") -> list[tuple[str, dict[str, int]]]:
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    sheet = book[book.sheetnames[0]]
    grid = [list(row) for row in sheet.iter_rows(values_only=True)]
    book.close()
    return rows_from_grid(grid, LABELS, skip)


def read_wide_csv(payload: bytes, skip: str = "") -> list[tuple[str, dict[str, int]]]:
    text = payload.decode("utf-8-sig", "replace")
    sample = text[:4000]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    grid = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    return rows_from_grid(grid, LABELS, skip)


READERS: dict[str, Callable[..., list[tuple[str, dict[str, int]]]]] = {
    "wide_xlsx": read_wide_xlsx,
    "wide_csv": read_wide_csv,
}


def csv_path(source: Source) -> Path:
    return RAWDIR / f"{source.key}.csv"


def refresh(source: Source) -> list[tuple[str, dict[str, int]]]:
    """Fetch the portal's table and write it out as the long CSV that is
    committed. What lands in git is what the portal served, one row per unit
    and faith, so a later reading can be diffed against this one."""
    payload = fetch(source.url)
    log(f"  {source.key}: {len(payload):,} bytes from {source.host}")
    rows = READERS[source.reader](payload, source.native)
    RAWDIR.mkdir(parents=True, exist_ok=True)
    with csv_path(source).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["unit", "faith", "count"])
        for unit, counts in rows:
            for faith in sorted(counts):
                writer.writerow([unit, faith, counts[faith]])
    log(f"  {source.key}: {len(rows)} units -> {csv_path(source)}")
    return rows


def committed(source: Source) -> list[tuple[str, dict[str, int]]]:
    path = csv_path(source)
    if not path.exists():
        return []
    out: dict[str, dict[str, int]] = {}
    order: list[str] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            unit = row["unit"]
            if unit not in out:
                out[unit] = {}
                order.append(unit)
            out[unit][row["faith"]] = int(row["count"])
    return [(unit, out[unit]) for unit in order]


# ---------------------------------------------------------------------------
# Which column is Protestant, measured rather than assumed
# ---------------------------------------------------------------------------

# The two assignments have to be this far apart in total error before either
# is believed; below it the table is published without the Christian split.
DECISIVE = 2.0
# And the winner has to be this close, in points summed over the units, or
# neither reading describes the same places and the table is the wrong table.
MAX_ERROR = 1.5


def shares(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {k: 100.0 * v / total for k, v in counts.items()} if total else {}


def resolve_pair(key: str, rows: list[tuple[str, dict[str, int]]],
                 known: dict[str, dict[str, float]]) -> bool:
    """Should this table's Protestant and Catholic columns be swapped?

    ``known`` is what the map already holds for units of this table, read from
    their own articles and citing the same offices. Each assignment is scored
    by the mean absolute error of the two Christian shares against that, over
    the units that carry both; the better one wins, and only if it wins
    clearly. A table with too few units to score is left as printed and the
    caller says so.
    """
    scores = {False: [], True: []}                       # type: dict[bool, list[float]]
    checked = 0
    for unit, counts in rows:
        name = match_unit(unit, known)
        if not name or not (set(PAIR) <= counts.keys()):
            continue
        theirs = known[name]
        if not set(PAIR) <= theirs.keys():
            continue
        mine = shares(counts)
        checked += 1
        for swap in (False, True):
            a, b = (PAIR[1], PAIR[0]) if swap else PAIR
            scores[swap].append(abs(mine[a] - theirs[PAIR[0]])
                                + abs(mine[b] - theirs[PAIR[1]]))
    if checked < 5:
        log(f"  {key}: only {checked} unit(s) to check the Christian columns against; "
            f"read as the table heads them")
        return False
    mean = {swap: sum(v) / len(v) for swap, v in scores.items()}
    swap = mean[True] < mean[False]
    log(f"  {key}: Christian columns checked on {checked} units already read -- "
        f"as printed {mean[False]:.2f} points of error, swapped {mean[True]:.2f}; "
        f"taking {'the swapped' if swap else 'the printed'} order")
    if min(mean.values()) > MAX_ERROR or max(mean.values()) < DECISIVE * min(mean.values()):
        raise SystemExit(
            f"indonesia_portals: {key}: neither reading of the Christian columns is "
            f"decisive (as printed {mean[False]:.2f}, swapped {mean[True]:.2f} points "
            f"over {checked} units); not published rather than guessed")
    return swap


def swapped(counts: dict[str, int]) -> dict[str, int]:
    out = dict(counts)
    if set(PAIR) <= counts.keys():
        out[PAIR[0]], out[PAIR[1]] = counts[PAIR[1]], counts[PAIR[0]]
    return out


# ---------------------------------------------------------------------------
# Joining to the map's names
# ---------------------------------------------------------------------------

def normal(name: str) -> str:
    text = clean(name).lower()
    text = re.sub(r"^(?:kab\.?|kabupaten|kota administrasi|kotamadya)\s+", "", text)
    text = re.sub(r"^kota\s+", "kota ", text)
    return re.sub(r"[^a-z ]", "", text).strip()


def match_unit(unit: str, names: dict[str, Any]) -> str | None:
    """The map's name for a table's row, or None. Never a near miss: an
    unmatched row is left out and logged, which is the whole point."""
    key = normal(unit)
    if key in ALIASES:
        key = normal(ALIASES[key])
    index = {normal(n): n for n in names}
    if key in index:
        return index[key]
    # A kota's row may or may not carry the word; the map always does.
    for alternative in (f"kota {key}", key.removeprefix("kota ")):
        if alternative in index:
            return index[alternative]
    return None


def readings(source: Source, known: dict[str, dict[str, float]],
             names: dict[str, Any]) -> tuple[dict[str, dict[str, int]], bool]:
    """{the map's unit name: counts by faith} for one source, and whether the
    Christian columns were taken swapped."""
    rows = committed(source)
    if not rows:
        return {}, False
    swap = resolve_pair(source.key, rows, known)
    if source.sums_to:
        # A table by kecamatan is one unit's composition split up; the map
        # draws the kota, so the parts are added back.
        total: dict[str, int] = {}
        for _, counts in rows:
            for faith, value in counts.items():
                total[faith] = total.get(faith, 0) + value
        rows = [(source.sums_to, total)]
    out: dict[str, dict[str, int]] = {}
    missed: list[str] = []
    for unit, counts in rows:
        name = match_unit(unit, names)
        if not name:
            missed.append(unit)
            continue
        out[name] = swapped(counts) if swap else counts
    if missed:
        log(f"  {source.key}: {len(missed)} row(s) match no shape: {', '.join(missed)}")
    return out, swap


# ---------------------------------------------------------------------------
# The note and the source line a record carries
# ---------------------------------------------------------------------------

CAVEAT = {
    "dukcapil": "A registry count of the religion on residents' identity cards, "
                "not a census answer.",
    "kemenag": "A ministry count of adherents, not a census answer.",
}


def fields(source: Source, counts: dict[str, int], swap: bool) -> dict[str, Any]:
    """The religion fields for one record: the composition, its year, a note of
    two or three sentences and the dataset it came from."""
    total = sum(counts.values())
    # A faith the registry counts a handful of people in rounds to 0.00% at
    # the two decimals every other row on this map carries, and a row printed
    # as 0.0% says less than no row at all. Kota Pariaman's two Buddhists of
    # 101,680 are dropped; the shares still add to 100.00.
    rows = [{"group": g, "pct": round(100.0 * v / total, 2)}
            for g, v in counts.items() if v and 100.0 * v / total >= 0.005]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    sentences = [
        f"Population by religion for {source.year} from {source.publisher}, "
        f"read from '{source.title}' on the {source.host} open-data portal; "
        f"shares computed from the counts.",
        CAVEAT[source.kind],
    ]
    if swap:
        sentences.append("The workbook heads its Christian columns in the reverse of "
                         "the order it prints them in, which is corrected here against "
                         "the province's other regencies.")
    # The table's own total is a head count, and these eight regencies had
    # none: the shares come from counts, the counts are the registry's, and
    # the registry files every registered resident under exactly one of the
    # faiths the table columns. Summing them is reading the total the table
    # already states row by row, not estimating one. It is the same registry
    # that supplies the head count on 255 of the regencies read from their
    # own articles, so the figures are comparable with those.
    return {
        "religion": rows,
        "religion_year": source.year,
        "religion_note": " ".join(sentences),
        "religion_source": {
            "field": "religion",
            "name": f"{source.publisher}, {source.title} ({source.year})",
            "url": f"https://{source.host}/dataset/{source.dataset}",
            "license": LICENCE,
        },
        "population": measure(total, year=source.year,
                              source=f"{source.publisher}, {source.title}"),
        "population_note": (
            f"Total population for {source.year} from {source.publisher}, "
            f"summed across the faiths of '{source.title}' on the "
            f"{source.host} open-data portal -- the same table the religion "
            f"shares are computed from. {CAVEAT[source.kind]}"),
        "population_source": {
            "field": "population",
            "name": f"{source.publisher}, {source.title} ({source.year})",
            "url": f"https://{source.host}/dataset/{source.dataset}",
            "license": LICENCE,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help="re-read every portal and rewrite the committed CSVs")
    ap.add_argument("--only", default="", help="one source key")
    args = ap.parse_args()
    log("indonesia_portals: religion by regency from the Satu Data portals")
    for source in SOURCES:
        if args.only and source.key != args.only:
            continue
        rows = refresh(source) if args.fetch else committed(source)
        if not rows:
            log(f"  {source.key}: nothing committed; run with --fetch")
            continue
        log(f"  {source.key} ({source.province}, {source.year}, {source.kind}): "
            f"{len(rows)} units")
        for unit, counts in rows:
            pretty = ", ".join(f"{k} {v:,}" for k, v in sorted(counts.items()))
            log(f"    {unit}: {pretty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
