#!/usr/bin/env python3
"""Indonesia: ethnicity by province from the 2010 census, and religion by
province and regency from the figures each place's own article carries.

Indonesia is the largest population this map carried nothing for, and the
reason is recorded in docs/SOURCES.md: BPS answers 403 to an automated
reader, its WebAPI wants a key nobody has registered, and its 2010 census
service serves one page whatever is asked of it. On 19 September 2026 the
owner decided that Indonesia is to be resolved from every reachable official
and secondary source, each figure cited for what it is. This module is that
decision. Everything it writes is read from the Indonesian Wikipedia through
the MediaWiki API, which is the one host in this chain that answers a clean
client, and every record names the article it was read from and the source
that article cites.

**Ethnicity by province -- the 2010 census, transcribed.** BPS published
*Kewarganegaraan, Suku Bangsa, Agama, dan Bahasa Sehari-hari Penduduk
Indonesia: Hasil Sensus Penduduk 2010*, with population by ethnic group and
province. The Indonesian Wikipedia article of each province transcribes that
province's column as a table -- "No | Suku | Jumlah 2010 | %" in most, with
half a dozen variations in the header row that ``ethnic_table`` recognises
by content rather than by position. The counts are read, the shares are
recomputed from them against the table's own total row, and the printed
percentages are only a check. 32 of the 34 provinces the map draws carry
such a table; Bangka Belitung and West Sulawesi do not, in either language
edition, and stay empty for the field.

The labels are BPS's own groupings and they are not all peoples. Beside
Jawa, Sunda and Batak the census tabulates regional bundles -- "asal
Sulawesi lainnya", "asal NTT", "asal Sumatera Selatan" -- because its
published table rounds the long tail of a province's groups into the region
they came from. Those are carried under a regional label ("Other Sulawesi
peoples") rather than invented into a people, and the note on the record
says so. One row is carried as a residual against its label: East Nusa
Tenggara's article prints 14.5% "asal Kalimantan", a share of Kalimantan
migrants that no census of the province supports and that is the size of
the Sikka, Ende, Kedang and Nagekeo peoples the table otherwise omits. It is
kept as "Other ethnic groups" with the article's wording in the note, since
the reader cannot know which mistake the editor made.

**The national check.** The census's national figures are read from the
English article *Ethnic groups in Indonesia*, which transcribes BPS's table
(Javanese 95,217,022 of 236,728,379). The Javanese counts read across the
provinces must add to that within 0.5%, or the run refuses -- a transcribed
table can drop a row or a digit, and Javanese is the group present in every
province. Every province's shares must add to 100 within 0.3.

**Religion by regency and province -- the infobox, and what it cites.** The
Indonesian Wikipedia gives each kabupaten, kota and province a religion
composition in its infobox, as a percentage per faith with a citation
attached. The citation is nearly always one of four things: the Ministry of
Home Affairs' civil-registry visualisation (Dukcapil, *Visualisasi Data
Kependudukan*, which records the religion on every resident's identity
card), a provincial or regency BPS table of population by religion, the
Ministry of Religious Affairs' count, or the 2010 census itself. Those are
different kinds of figure and the record says which it is, with the year the
citation carries: a registry counts the religion people are registered
under, a census counts what they answered. An infobox figure with no
citation at all is not read.

The province of Papua and West Papua were divided in 2022 and their articles
now describe the smaller provinces that kept the names; the map draws the
2010 shapes. Their religion is therefore not read at province level, and the
regency figures inside them are.

**Language** is not written. The 2010 volume's "bahasa sehari-hari" table by
province is transcribed nowhere this reader can reach; the Indonesian
article *Demografi Indonesia* carries the national column only.

Usage:
    python -m scripts.fetch_census.indonesia                 # both levels
    python -m scripts.fetch_census.indonesia --level province
    python -m scripts.fetch_census.indonesia --infobox "Kabupaten Cilacap"  # probe
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_json, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402
from probe_wikitable import plain, tables  # noqa: E402

API = "https://id.wikipedia.org/w/api.php"
EN_API = "https://en.wikipedia.org/w/api.php"
OUT = "indonesia.json"
ISO3 = "IDN"
ETHNICITY_YEAR = 2010
CENSUS = ("Badan Pusat Statistik, Sensus Penduduk 2010: Kewarganegaraan, Suku Bangsa, "
          "Agama, dan Bahasa Sehari-hari Penduduk Indonesia (2011)")
LICENCE = "Official statistics; compilation CC BY-SA 4.0"
NATIONAL_PAGE = "Ethnic groups in Indonesia"
POPULATION_PAGE = "Demografi Indonesia"
SUM_TOLERANCE = 0.3          # a province's ethnic shares, against 100
TOTAL_TOLERANCE = 0.01       # a table's rows against its own printed total
RELIGION_TOLERANCE = 0.6     # an infobox's religion shares, against 100
SHORTFALL = 5.0              # below this much short of 100, the rest is a remainder row
REMAINDER = "Other or not stated"
NATIONAL_TOLERANCE = 0.005   # the Javanese sum, against the census

# The map's province name -> the Indonesian article, and the other spellings
# a reader may know the place by.
PROVINCES: dict[str, tuple[str, list[str]]] = {
    "Aceh": ("Aceh", ["Nanggroe Aceh Darussalam"]),
    "Bali": ("Bali", []),
    "Bangka-Belitung Islands": ("Kepulauan Bangka Belitung",
                                ["Bangka Belitung Islands", "Kepulauan Bangka Belitung",
                                 "Bangka Belitung"]),
    "Banten": ("Banten", []),
    "Bengkulu": ("Bengkulu", []),
    "Central Java": ("Jawa Tengah", ["Jawa Tengah"]),
    "Central Kalimantan": ("Kalimantan Tengah", ["Kalimantan Tengah"]),
    "Central Sulawesi": ("Sulawesi Tengah", ["Sulawesi Tengah"]),
    "East Java": ("Jawa Timur", ["Jawa Timur"]),
    "East Kalimantan": ("Kalimantan Timur", ["Kalimantan Timur"]),
    "East Nusa Tenggara": ("Nusa Tenggara Timur", ["Nusa Tenggara Timur"]),
    "Gorontalo": ("Gorontalo", []),
    "Jakarta Special Capital Region": ("Daerah Khusus Ibukota Jakarta",
                                       ["Jakarta", "DKI Jakarta",
                                        "Daerah Khusus Ibukota Jakarta"]),
    "Jambi": ("Jambi", []),
    "Lampung": ("Lampung", []),
    "Maluku": ("Maluku", []),
    "North Kalimantan": ("Kalimantan Utara", ["Kalimantan Utara"]),
    "North Maluku": ("Maluku Utara", ["Maluku Utara"]),
    "North Sulawesi": ("Sulawesi Utara", ["Sulawesi Utara"]),
    "North Sumatra": ("Sumatera Utara", ["Sumatera Utara"]),
    "Papua": ("Papua", []),
    "Riau": ("Riau", []),
    "Riau Islands": ("Kepulauan Riau", ["Kepulauan Riau"]),
    "South Kalimantan": ("Kalimantan Selatan", ["Kalimantan Selatan"]),
    "South Sulawesi": ("Sulawesi Selatan", ["Sulawesi Selatan"]),
    "South Sumatra": ("Sumatera Selatan", ["Sumatera Selatan"]),
    "Southeast Sulawesi": ("Sulawesi Tenggara", ["Sulawesi Tenggara"]),
    "Special Region of Yogyakarta": ("Daerah Istimewa Yogyakarta",
                                     ["Yogyakarta", "DI Yogyakarta",
                                      "Daerah Istimewa Yogyakarta"]),
    "West Java": ("Jawa Barat", ["Jawa Barat"]),
    "West Kalimantan": ("Kalimantan Barat", ["Kalimantan Barat"]),
    "West Nusa Tenggara": ("Nusa Tenggara Barat", ["Nusa Tenggara Barat"]),
    "West Papua": ("Papua Barat", ["Papua Barat"]),
    "West Sulawesi": ("Sulawesi Barat", ["Sulawesi Barat"]),
    "West Sumatra": ("Sumatera Barat", ["Sumatera Barat"]),
}
# The article describes a province the 2022 division left smaller than the
# shape the map draws, so its infobox figure is for a different population.
DIVIDED_2022 = {"Papua", "West Papua"}
# North Kalimantan was carved out of East Kalimantan in 2012; the map draws
# both, and each article's 2010 table is for its present extent.
SPLIT_2012 = {"East Kalimantan", "North Kalimantan"}
# Provinces whose article carries no 2010 ethnic table, in either edition.
NO_ETHNIC_TABLE = {"Bangka-Belitung Islands", "West Sulawesi"}

# The boundary file's admin2 layer has five polygons that are water or forest,
# not regencies, and they have no article to read.
NOT_REGENCIES = {"Hutan", "Wadung Kedungombo", "Waduk Cirata", "Danau", "Danau Toba"}
# Where the boundary file's spelling is not the article's, or the regency has
# been renamed since the shapes were drawn.
REGENCY_TITLES: dict[str, str] = {
    "Karang Asem": "Kabupaten Karangasem",
    "Kota Pangkal Pinang": "Kota Pangkalpinang",
    "Toli-Toli": "Kabupaten Tolitoli",
    "Tulangbawang": "Kabupaten Tulang Bawang",
    "Banyu Asin": "Kabupaten Banyuasin",
    "Kota Tanjung Pinang": "Kota Tanjungpinang",
    "Kota Banjar Baru": "Kota Banjarbaru",
    "Kota Baru": "Kabupaten Kotabaru",
    "Pangkajene Dan Kepulauan": "Kabupaten Pangkajene dan Kepulauan",
    "Kota Sawah Lunto": "Kota Sawahlunto",
    "Labuhan Batu": "Kabupaten Labuhanbatu",
    "Labuhan Batu Selatan": "Kabupaten Labuhanbatu Selatan",
    "Labuhan Batu Utara": "Kabupaten Labuhanbatu Utara",
    "Kota Pematang Siantar": "Kota Pematangsiantar",
    "Kota Tanjung Balai": "Kota Tanjungbalai",
    "Gunung Kidul": "Kabupaten Gunungkidul",
    "Toba Samosir": "Kabupaten Toba",
    "Mamuju Utara": "Kabupaten Pasangkayu",
    "Siau Tagulandang Biaro": "Kabupaten Kepulauan Siau Tagulandang Biaro",
    "Kota Jakarta Barat": "Kota Administrasi Jakarta Barat",
    "Kota Jakarta Pusat": "Kota Administrasi Jakarta Pusat",
    "Kota Jakarta Selatan": "Kota Administrasi Jakarta Selatan",
    "Kota Jakarta Timur": "Kota Administrasi Jakarta Timur",
    "Kota Jakarta Utara": "Kota Administrasi Jakarta Utara",
    "Mahakam Hulu": "Kabupaten Mahakam Ulu",
}

# BPS's row label, lower-cased and with "suku" and the footnote star
# stripped -> the label the map carries. A label not here refuses the run:
# it would be a category this was never read for.
ETHNIC_LABELS: dict[str, str] = {
    "jawa": "Javanese", "sunda": "Sundanese", "batak": "Batak", "madura": "Madurese",
    "betawi": "Betawi", "minangkabau": "Minangkabau", "bugis": "Buginese",
    "melayu": "Malay", "banten": "Bantenese", "banjar": "Banjar", "bali": "Balinese",
    "aceh": "Acehnese", "dayak": "Dayak", "sasak": "Sasak", "tionghoa": "Chinese Indonesian",
    "makassar": "Makassarese", "cirebon": "Cirebonese", "nias": "Nias",
    "lampung": "Lampung", "gayo": "Gayo", "aneuk jamee": "Aneuk Jamee",
    "singkil": "Singkil", "devayan": "Devayan", "mentawai": "Mentawai",
    "rejang": "Rejang", "serawai": "Serawai", "minahasa": "Minahasan",
    "manado": "Minahasan", "gorontalo": "Gorontalo", "toraja": "Torajan",
    "kutai": "Kutai", "paser": "Paser", "buton": "Butonese", "berau": "Berau",
    "mandar": "Mandar", "flores": "Florenese", "bajau": "Bajau", "mamuju": "Mamuju",
    "arab": "Arab", "palembang": "Palembang", "jambi": "Jambi Malay",
    "lombok": "Sasak", "papua": "Papuan", "asli papua": "Papuan",
    "asal papua": "Papuan", "asli papua barat dan papua barat daya": "Papuan",
    "melayu tamiang": "Tamiang Malay", "melayu bengkulu": "Bengkulu Malay",
    "melayu kotawaringin": "Kotawaringin Malay", "melayu jambi": "Jambi Malay",
    "melayu (selain melayu jambi)": "Malay", "melayu (diluar sumatera selatan)": "Malay",
    "maluku": "Moluccan", "asal maluku": "Moluccan",
    "ntt": "East Nusa Tenggara peoples", "asal ntt": "East Nusa Tenggara peoples",
    "flores / ntt": "East Nusa Tenggara peoples",
    "asal nusa tenggara barat": "Bima and Sumbawa peoples",
    "asal ntb": "Bima and Sumbawa peoples",
    "asli nusa tenggara timur": "East Nusa Tenggara peoples",
    "sasak/ntb": "Sasak", "sasak, ntb": "Sasak", "sasak / ntb": "Sasak",
    "asal sulawesi": "Other Sulawesi peoples",
    "asal sulawesi lainnya": "Other Sulawesi peoples",
    "sulawesi lainnya": "Other Sulawesi peoples",
    "asal sulawesi (termasuk toraja)": "Other Sulawesi peoples",
    "asal sulawesi tengah": "Central Sulawesi peoples",
    "asal sulawesi tenggara": "Southeast Sulawesi peoples",
    "asal sumatera selatan": "South Sumatra peoples", "asal sumsel": "South Sumatra peoples",
    "asal sumatra lainnya": "Other Sumatra peoples", "asal sumatra": "Other Sumatra peoples",
    "asal sumatera": "Other Sumatra peoples", "asal jambi": "Jambi peoples",
    "asal riau": "Riau peoples", "asal jawa lainnya": "Other Java peoples",
    "asal kalimantan lainnya": "Other Kalimantan peoples",
    "pribumi lainnya": "Other indigenous Bengkulu peoples",
    "warga negara asing": "Foreign nationals", "warga asing": "Foreign nationals",
    "lainnya": "Other ethnic groups", "lain-lain": "Other ethnic groups",
    "lain": "Other ethnic groups",
    "suku lainnya": "Other ethnic groups", "suku lain": "Other ethnic groups",
    "suku-suku lainnya": "Other ethnic groups",
    "suku bangsa lainnya": "Other ethnic groups",
}
# East Nusa Tenggara's "asal Kalimantan" row, carried as the residual: see
# the module docstring.
RESIDUAL_BY_PROVINCE: dict[tuple[str, str], str] = {
    ("East Nusa Tenggara", "asal kalimantan"): "Other ethnic groups",
}
RESIDUAL = "Other ethnic groups"
ETHNIC_NOTE = (
    "Counts as the 2010 Population Census published them, read from the Indonesian "
    "Wikipedia article '{title}', which transcribes the province's column of BPS's "
    "table of population by ethnic group; shares are recomputed from the counts. BPS "
    "groups a province's smaller peoples by the region they come from ('asal "
    "Sulawesi', 'asal NTT'), and those rows are carried under a regional label rather "
    "than as a people."
)

# The infobox's faith -> the label the map carries.
RELIGION_LABELS: dict[str, str] = {
    "islam": "Islam", "protestan": "Protestantism", "protestanisme": "Protestantism",
    "kristen protestan": "Protestantism", "katolik": "Catholicism",
    "kristen katolik": "Catholicism", "katolik roma": "Catholicism",
    "kristen": "Christianity", "kekristenan": "Christianity",
    "hindu": "Hinduism", "buddha": "Buddhism", "budha": "Buddhism",
    "konghucu": "Confucianism", "khonghucu": "Confucianism",
    "kepercayaan": "Kepercayaan (traditional belief)",
    "penghayat kepercayaan": "Kepercayaan (traditional belief)",
    "aliran kepercayaan": "Kepercayaan (traditional belief)",
    "kepercayaan lainnya": "Kepercayaan (traditional belief)",
    "penghayat": "Kepercayaan (traditional belief)",
    "kepercayaan terhadap tuhan yme": "Kepercayaan (traditional belief)",
    "kepercayaan terhadap tuhan yang maha esa": "Kepercayaan (traditional belief)",
    "konfusianisme": "Confucianism",
    "marapu": "Marapu", "aluk todolo": "Aluk Todolo", "ugamo malim": "Ugamo Malim",
    "kaharingan": "Kaharingan", "parmalim": "Ugamo Malim", "pemena": "Pemena",
    "sunda wiwitan": "Sunda Wiwitan", "kejawen": "Kejawen",
    "lainnya": "Other religion", "lain-lain": "Other religion",
    "agama lainnya": "Other religion", "konghucu dan kepercayaan": "Other religion",
    "kepercayaan dan lainnya": "Other religion", "kepercayaan/lainnya": "Other religion",
}
CHRISTIAN_PARENTS = {"Christianity"}
CHRISTIAN_CHILDREN = {"Protestantism", "Catholicism"}

# What a citation is, from the host it points at or the name it is given.
SOURCE_KINDS: tuple[tuple[str, str, str], ...] = (
    ("census2010", r"sp2010\.bps\.go\.id|sensus penduduk 2010|sensus 2010|sp2010",
     "the 2010 Population Census (BPS)"),
    ("bps", r"bps\.go\.id|badan pusat statistik|dalam angka",
     "a BPS (Statistics Indonesia) table of population by religion"),
    ("dukcapil", r"dukcapil|kementerian dalam negeri|kemendagri|capil|kependudukan",
     "the Ministry of Home Affairs' civil registry (Dukcapil), which records the "
     "religion on each resident's identity card"),
    ("kemenag", r"kemenag|kementerian agama",
     "the Ministry of Religious Affairs' count of adherents"),
    ("jakarta", r"statistik\.jakarta\.go\.id",
     "the Jakarta provincial statistics office"),
)
KIND_RANK = {"census2010": 0, "bps": 1, "kemenag": 2, "dukcapil": 3, "jakarta": 4, "other": 5}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch(title: str, lang: str = "id") -> tuple[str, str]:
    """The article's wikitext and the title it resolved to (after redirects)."""
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    api = API if lang == "id" else EN_API
    data = http_json(f"{api}?{q}", timeout=90)
    parsed = data.get("parse") or {}
    text = parsed.get("wikitext") or ""
    if not text:
        log(f"  [{lang}] {title!r}: nothing ({(data.get('error') or {}).get('code')})")
    return text, parsed.get("title") or title


# ---------------------------------------------------------------------------
# Infobox
# ---------------------------------------------------------------------------

def infobox_lines(wikitext: str) -> list[str]:
    """Top-level ``| key = value`` entries of the article's first infobox, whole.

    A value runs until the next top-level parameter, so a multi-line
    ``agama`` list comes back as one entry.
    """
    out: list[str] = []
    depth = 0
    current: list[str] | None = None
    for line in wikitext.split("\n"):
        opened = line.count("{{")
        closed = line.count("}}")
        if depth == 1 and line.lstrip().startswith("|") and "=" in line:
            if current is not None:
                out.append("\n".join(current))
            current = [line]
        elif current is not None and depth >= 1:
            current.append(line)
        depth += opened - closed
        if depth <= 0 and current is not None:
            out.append("\n".join(current))
            current = None
            depth = 0
            if out:
                break
    return out


def infobox_param(wikitext: str, key: str) -> str | None:
    for entry in infobox_lines(wikitext):
        m = re.match(r"\s*\|\s*([^=|]+?)\s*=", entry)
        if m and m.group(1).strip().lower() == key:
            return entry[m.end():]
    return None


REF = re.compile(r"<ref\b([^>/]*)(?:/>|>(.*?)</ref>)", re.S | re.I)
REF_NAME = re.compile(r"""name\s*=\s*["']?([^"'/>]+?)["']?\s*$""", re.I)


def ref_name(attrs: str) -> str | None:
    m = REF_NAME.search(attrs.strip())
    return m.group(1).strip().lower() if m else None


def ref_definitions(wikitext: str) -> dict[str, str]:
    """Every named reference's body, wherever on the page it is defined."""
    out: dict[str, str] = {}
    for m in REF.finditer(wikitext):
        body = m.group(2)
        name = ref_name(m.group(1))
        if body and name:
            out.setdefault(name, body)
    return out


def citations(value: str, definitions: dict[str, str]) -> list[str]:
    """The bodies of the references attached to one infobox value, in order.

    A reference used by name and defined nowhere on the page is a citation
    to nothing, and is listed as such by ``unresolved``.
    """
    out: list[str] = []
    for m in REF.finditer(value):
        body = m.group(2)
        name = ref_name(m.group(1))
        if not body and name:
            body = definitions.get(name, "")
        if body:
            out.append(body)
    return out


def unresolved(value: str, definitions: dict[str, str]) -> list[str]:
    return [ref_name(m.group(1)) or "?" for m in REF.finditer(value)
            if not m.group(2) and (ref_name(m.group(1)) or "") not in definitions]


def cite_field(body: str, field: str) -> str:
    m = re.search(r"\|\s*" + field + r"\s*=\s*([^|}]*)", body, re.I)
    return " ".join(m.group(1).split()) if m else ""


def describe_citation(body: str) -> tuple[str, int | None, str]:
    """(kind, year, what the citation says it is) for one reference body."""
    title = cite_field(body, "title")
    url = cite_field(body, "url")
    haystack = f"{title} {url} {body[:200]}".lower()
    kind = "other"
    for name, pattern, _ in SOURCE_KINDS:
        if re.search(pattern, haystack):
            kind = name
            break
    years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", title)]
    if not years:
        # BPS puts the table's year in the URL path only when the title
        # forgets it; the archive timestamp is not a year and is skipped.
        path = re.sub(r"web\.archive\.org/web/\d+/", "", url)
        years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", path)]
    year = max(years) if years else (2010 if kind == "census2010" else None)
    return kind, year, title or url or body[:80]


PERCENT = re.compile(r"(?<![\d,.])(\d{1,3}(?:[.,]\d{1,2})?)\s*%?")
LINK = re.compile(r"\[\[([^\]]+)\]\]")


def religion_items(value: str) -> list[tuple[str, float]]:
    """(label as printed, percentage) for each faith in an infobox value.

    Two layouts are in use -- a ``{{ublist}}`` of "98,62% [[Islam]]" items
    with the Christian split as a ``{{Tree list}}``, and a ``<br>``-separated
    list of "[[Islam]] 70,84%" with the split marked by dashes. Each is cut
    into items at its separators and an item is read whichever way round it
    is written.
    """
    text = REF.sub("", value)
    # A citation whose <ref> tag lost its bracket leaks into the value.
    text = re.sub(r"\{\{\s*cite[^{}]*\}\}", " ", text, flags=re.I)
    text = re.sub(r"ref\s+name\s*=[^>]*>", " ", text)
    text = re.sub(r"\{\{\s*(?:ublist|unbulleted list|plainlist)\b[^|}]*", " ", text, flags=re.I)
    text = re.sub(r"\{\{\s*Tree list(?:/end)?\s*\}\}", "|", text, flags=re.I)
    text = text.replace("{{", " ").replace("}}", " ")
    text = re.sub(r"<[^>]+>", "|", text)
    text = text.replace("&nbsp;", " ")
    # A piped link carries the separator inside it; resolve links to their
    # display text before the value is cut at pipes.
    text = LINK.sub(lambda m: m.group(1).split("|")[-1], text)
    out: list[tuple[str, float]] = []
    for piece in re.split(r"\||\n|(?:^|\s)\*+(?=\s)", text):
        piece = piece.strip().lstrip("*-—–• ").strip()
        if not piece or piece.lower().startswith("item_style"):
            continue
        m = PERCENT.search(piece)
        if not m:
            continue
        label = link_text(piece[:m.start()] + " " + piece[m.end():])
        if label:
            out.append((label, float(m.group(1).replace(",", "."))))
    return out


def link_text(label: str) -> str:
    """The label an item names, its markup and punctuation gone."""
    return " ".join(label.replace("[[", " ").replace("]]", " ").split()).strip(" .;:<>=()")


def religion_shares(items: list[tuple[str, float]]) -> tuple[list[dict[str, Any]], str | None]:
    """The map's rows, or (None, why-not).

    Christianity given beside its Protestant and Catholic parts is the same
    people twice, so the parent is dropped where its parts are present.
    """
    rows: dict[str, float] = {}
    unknown: list[str] = []
    for label, pct in items:
        key = re.sub(r"\s+", " ", label.lower()).strip()
        key = re.sub(r"^agama ", "", key)
        mapped = RELIGION_LABELS.get(key)
        if mapped is None:
            unknown.append(label)
            continue
        rows[mapped] = rows.get(mapped, 0.0) + pct
    if unknown:
        return [], f"unknown faith label(s) {unknown}"
    if rows.keys() & CHRISTIAN_CHILDREN:
        for parent in CHRISTIAN_PARENTS:
            rows.pop(parent, None)
    if not rows:
        return [], "no faiths"
    total = sum(rows.values())
    if total > 100.0 + RELIGION_TOLERANCE or total < 100.0 - SHORTFALL:
        return [], f"shares add to {total:.2f}"
    if total < 100.0 - RELIGION_TOLERANCE:
        # An infobox that lists the faiths it lists and stops: the rest is
        # published as the remainder, the way wiki_census does.
        rows[REMAINDER] = round(100.0 - total, 2)
    out = [{"group": g, "pct": round(p, 2)} for g, p in rows.items()]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out, None


def read_religion(wikitext: str, title: str) -> dict[str, Any] | None:
    """The infobox's religion composition with its citation, or None with a
    reason logged."""
    value = infobox_param(wikitext, "agama")
    if not value:
        log(f"    {title}: no religion in the infobox")
        return None
    definitions = ref_definitions(wikitext)
    cites = citations(value, definitions)
    broken = ""
    if not cites:
        # A reference used by a name the page never defines is a broken
        # citation. Where the name itself says what was cited -- DUKCAPIL,
        # KEMENAG, BPS -- that much is kept and the record says the
        # reference is broken; a name that says nothing is no citation.
        missing = unresolved(value, definitions)
        named = [n for n in missing if re.search(r"dukcapil|capil|kemenag|bps|sp2010", n)]
        if named:
            cites = [f"<broken reference named {named[0]!r}>"]
            broken = named[0]
        else:
            log(f"    {title}: religion figure carries no citation"
                + (f" (named references {missing} defined nowhere)" if missing else "")
                + "; not read")
            return None
    rows, why = religion_shares(religion_items(value))
    if why:
        log(f"    {title}: {why}; not read")
        return None
    described = [describe_citation(c) for c in cites]
    described.sort(key=lambda d: KIND_RANK[d[0]])
    kind, year, what = described[0]
    years = [d[1] for d in described if d[1]]
    year = year or (max(years) if years else None)
    explained = dict((k, e) for k, _, e in SOURCE_KINDS).get(
        kind, "a source that is neither the census nor a registry")
    return {"rows": rows, "kind": kind, "year": year, "cited": what, "explained": explained,
            "all": [d[2] for d in described], "broken": broken}


def religion_fields(reading: dict[str, Any], title: str) -> dict[str, Any]:
    cited = "; ".join(dict.fromkeys(reading["all"]))
    when = f" for {reading['year']}" if reading["year"] else ", year not stated"
    if reading.get("broken"):
        cited = (f"a reference named '{reading['broken']}' that the article never defines, "
                 f"so the source is known only by that name")
    note = (f"Shares as the Indonesian Wikipedia article '{title}' gives them in its "
            f"infobox, citing {cited}. The figure is from {reading['explained']}{when}"
            + (", not a census count." if reading["kind"] not in ("census2010",) else "."))
    source = {"census2010": "BPS, 2010 Population Census, population by religion",
              "bps": "BPS (Statistics Indonesia), population by religion",
              "dukcapil": "Kementerian Dalam Negeri, Dukcapil civil registry, population by religion",
              "kemenag": "Kementerian Agama, adherents by religion",
              "jakarta": "Jakarta provincial statistics office, population by religion",
              "other": "Regional government population-by-religion figure"}[reading["kind"]]
    if reading["year"]:
        source += f" ({reading['year']})"
    return {
        "religion": reading["rows"],
        "religion_year": reading["year"],
        "religion_note": note,
        "religion_source": {"field": "religion", "name": source,
                            "url": "https://id.wikipedia.org/wiki/" + title.replace(" ", "_"),
                            "license": LICENCE},
    }


# ---------------------------------------------------------------------------
# Ethnic tables
# ---------------------------------------------------------------------------

# A count is written with dots as thousands separators; one row in Aceh's
# table has commas instead, which is a typo and not a percentage (those
# carry a % sign and two decimals).
COUNT = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$|^\d{4,}$|^\d{1,3}$")
SUKU = re.compile(r"suku|etnis", re.I)


def as_count(cell: str) -> int | None:
    text = cell.replace(" ", "").strip()
    text = re.sub(r"^[^|]*\|", "", text).strip()          # "align=right| 1.234"
    if COUNT.match(text):
        return int(re.sub(r"[.,]", "", text))
    return None


def ethnic_table(wikitext: str) -> tuple[list[list[str]], int] | None:
    """The 2010 ethnic table and the index of its name column, or None.

    Recognised by a header cell naming the group ('Suku', 'Suku Bangsa',
    'Etnis') beside a count column; the header may be the table's first or
    second row, since a citation in the caption arrives as a row of its own.
    """
    for table in tables(wikitext):
        for h in range(min(2, len(table))):
            header = [re.sub(r"^[^|]*\|", "", c).strip() for c in table[h]]
            names = [i for i, c in enumerate(header) if SUKU.search(c)
                     and not c.lower().startswith("no")]
            counts = [i for i, c in enumerate(header)
                      if re.search(r"jumlah|sensus|populasi", c, re.I)]
            if names and counts and len(table) > h + 2:
                return table[h + 1:], names[0]
    return None


def normalise_label(name: str) -> str:
    text = plain(name).replace("*", "").strip()
    text = re.sub(r"^\s*suku\s+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text.lower()


def ethnic_label(province: str, key: str) -> str | None:
    """The map's label for a row, trying the row without its bracketed
    qualifier ('Dayak (termasuk Tidung dan Bulungan)') when the whole is
    not listed."""
    label = RESIDUAL_BY_PROVINCE.get((province, key)) or ETHNIC_LABELS.get(key)
    if label is None and "(" in key:
        label = ETHNIC_LABELS.get(re.sub(r"\s*\(.*?\)\s*", " ", key).strip())
    return label


def table_rows(rows: list[list[str]], name_col: int) -> list[tuple[str, int, bool]]:
    """(name as printed, count, numbered) for every row that carries a count.

    The count is the last integer-looking cell after the name, which is the
    2010 figure whether the table prints one census or two, and whether the
    percentages come before it (Jakarta) or after. ``numbered`` says whether
    the row carries a serial number before its name, which the total row
    does not.
    """
    out: list[tuple[str, int, bool]] = []
    for row in rows:
        if len(row) <= name_col:
            continue
        cells = [re.sub(r"^[^|]*\|", "", c).strip() if "|" in c and not c.strip().startswith("[[")
                 else c.strip() for c in row]
        numbers = [n for n in (as_count(c) for c in cells[name_col + 1:]) if n is not None]
        if not numbers:
            continue                     # a header continuation row ('Jumlah | %')
        name = cells[name_col]
        if name.startswith("*"):
            continue                     # a sub-row of the group above it
        numbered = name_col > 0 and bool(re.fullmatch(r"\d+\.?", cells[name_col - 1]))
        out.append((name, numbers[-1], numbered))
    return out


def split_total(rows: list[tuple[str, int, bool]], province: str, title: str
                ) -> tuple[list[tuple[str, int]], int | None]:
    """The group rows apart from the total row.

    The total is the row named as one ('Total', 'Provinsi Jambi'), or the
    unnumbered row named after the province -- unnumbered, because Aceh,
    Bali and Lampung are peoples as well as provinces and their own row is
    numbered like any other -- or, when a spanning cell has pushed the name
    out of its column, the row that is the sum of every other.
    """
    body: list[tuple[str, int]] = []
    total: int | None = None
    for name, count, numbered in rows:
        key = normalise_label(name)
        named = key.startswith("total") or key.startswith("provinsi") or key == "jumlah"
        after_province = key in (title.lower(), province.lower()) and not numbered
        if named or after_province:
            total = count
        else:
            body.append((name, count))
    if total is None and len(body) > 2:
        biggest = max(body, key=lambda r: r[1])
        rest = sum(c for _, c in body) - biggest[1]
        if rest and abs(biggest[1] - rest) <= SUM_TOLERANCE / 100 * rest:
            total = biggest[1]
            body.remove(biggest)
    return body, total


def read_ethnicity(wikitext: str, province: str, title: str
                   ) -> tuple[dict[str, int], int] | None:
    """{label: count} for the province and the table's total, or None."""
    found = ethnic_table(wikitext)
    if not found:
        log(f"    {province}: no 2010 ethnic table in '{title}'")
        return None
    rows, name_col = found
    body, total = split_total(table_rows(rows, name_col), province, title)
    counts: dict[str, int] = {}
    unknown: list[str] = []
    for name, count in body:
        key = normalise_label(name)
        if not key:
            continue
        label = ethnic_label(province, key)
        if label is None:
            unknown.append(name)
            continue
        counts[label] = counts.get(label, 0) + count
    if unknown:
        raise SystemExit(f"indonesia: {province}: ethnic labels not in ETHNIC_LABELS: {unknown}")
    if not counts:
        log(f"    {province}: the ethnic table has no readable rows")
        return None
    summed = sum(counts.values())
    if total is None:
        log(f"    {province}: no total row; the rows' sum {summed:,} stands as the total")
    elif abs(summed - total) > TOTAL_TOLERANCE * total:
        raise SystemExit(f"indonesia: {province}: rows add to {summed:,} against the table's "
                         f"total {total:,} ({100 * summed / total:.2f}%)")
    elif summed != total:
        # Central Kalimantan's rows add to 0.3% more than its printed total:
        # a transcription slip in one or the other. The rows are the figures
        # carried, so they are the denominator, and the slip is on record.
        log(f"    {province}: rows add to {summed:,} against the table's total {total:,} "
            f"({100 * summed / total:.2f}%); the rows' sum is the denominator")
    return counts, summed


def ethnic_rows(counts: dict[str, int], total: int) -> list[dict[str, Any]]:
    """Shares to two decimals, so twenty-odd rows still add to 100 within the
    tolerance the run enforces."""
    out = [{"group": g, "pct": round(100.0 * c / total, 2), "count": c}
           for g, c in counts.items()]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def national_figures(wikitext: str) -> dict[str, int]:
    """The census's national counts by group, from the English article's table.

    The article prints BPS's table and, beside it, one in millions to three
    decimals; the one in counts is the one whose Javanese figure is largest.
    """
    found: list[dict[str, int]] = []
    for table in tables(wikitext):
        header = [re.sub(r"^[^|]*\|", "", c).strip().lower() for c in table[0]]
        if header[:1] == ["ethnic group"] and any("population" in c for c in header):
            out: dict[str, int] = {}
            for row in table[1:]:
                if len(row) < 2:
                    continue
                n = re.sub(r"[^\d]", "", row[1])
                if n and row[0].strip():
                    out[row[0].strip()] = int(n)
            if out.get("Javanese"):
                found.append(out)
    if not found:
        raise SystemExit("indonesia: the national ethnic table was not found in "
                         f"'{NATIONAL_PAGE}'")
    return max(found, key=lambda t: t["Javanese"])


def census_populations(wikitext: str) -> dict[str, int]:
    """Each province's 2010 census population, from 'Demografi Indonesia'."""
    for table in tables(wikitext):
        header = [re.sub(r"^[^|]*\|", "", c).strip().lower() for c in table[0]]
        col = next((i for i, c in enumerate(header) if "2010" in c), None)
        if header[:1] == ["nama provinsi"] and col is not None:
            out: dict[str, int] = {}
            for row in table[1:]:
                if len(row) > col:
                    n = as_count(row[col])
                    if n:
                        out[plain(row[0]).strip()] = n
            return out
    return {}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def shapes(level: str) -> list[dict[str, Any]]:
    from common import read_json
    root = Path(__file__).resolve().parent.parent.parent / "site" / "data"
    if level == "admin1":
        return read_json(root / "admin1" / f"{ISO3}.json", []) or []
    return read_json(root / "admin2" / f"{ISO3}.json", []) or []


def province_records(fetch_page=fetch) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The 34 province records; also returns the Javanese count per province."""
    national = national_figures(fetch_page(NATIONAL_PAGE, "en")[0])
    populations = census_populations(fetch_page(POPULATION_PAGE, "id")[0])
    records: list[dict[str, Any]] = []
    javanese: dict[str, int] = {}
    read_counts: dict[str, int] = {}
    totals: dict[str, int] = {}
    for province, (title, aliases) in PROVINCES.items():
        wikitext, resolved = fetch_page(title, "id")
        fields: dict[str, Any] = {}
        sources: list[dict[str, str]] = []
        if wikitext and province not in NO_ETHNIC_TABLE:
            found = read_ethnicity(wikitext, province, resolved)
            if found:
                counts, total = found
                expected = populations.get(resolved) or populations.get(title)
                if province in SPLIT_2012:
                    # North Kalimantan left East Kalimantan in 2012, and each
                    # article's table is for the province as it now is
                    # while the 2010 population is for the province as it
                    # was. Their two tables add to it; the check is over
                    # the pair.
                    expected = None
                if expected and not 0.85 * expected <= total <= 1.03 * expected:
                    raise SystemExit(f"indonesia: {province}: the ethnic table's total "
                                     f"{total:,} is not the 2010 population {expected:,}")
                rows = ethnic_rows(counts, total)
                summed = sum(r["pct"] for r in rows)
                if abs(summed - 100.0) > SUM_TOLERANCE:
                    raise SystemExit(f"indonesia: {province}: shares add to {summed:.2f}")
                fields.update(ethnicity=rows, ethnicity_year=ETHNICITY_YEAR,
                              ethnicity_note=ETHNIC_NOTE.format(title=resolved))
                sources.append({"field": "ethnicity", "name": CENSUS,
                                "url": "https://id.wikipedia.org/wiki/" + resolved.replace(" ", "_"),
                                "license": LICENCE})
                javanese[province] = counts.get("Javanese", 0)
                totals[province] = total
                for label, n in counts.items():
                    read_counts[label] = read_counts.get(label, 0) + n
        elif province in NO_ETHNIC_TABLE:
            fields["ethnicity"] = gap(NOT_AVAILABLE,
                                      "The province's Wikipedia articles carry no 2010 "
                                      "census ethnic table in either language edition.")
        if province in DIVIDED_2022:
            fields["religion"] = gap(NOT_AVAILABLE,
                                     "The province was divided in 2022 and its article now "
                                     "describes the smaller province that kept the name; "
                                     "the map draws the 2010 shape.")
        elif wikitext:
            reading = read_religion(wikitext, resolved)
            if reading:
                rf = religion_fields(reading, resolved)
                sources.append(rf.pop("religion_source"))
                fields.update(rf)
        records.append(record(f"{ISO3}-{slugify(province)}", province, level="admin1",
                              parent=ISO3, country=ISO3, aliases=aliases, sources=sources,
                              **fields))
    kalimantan = sum(totals.get(p, 0) for p in SPLIT_2012)
    expected = populations.get("Kalimantan Timur")
    if kalimantan and expected and not 0.85 * expected <= kalimantan <= 1.03 * expected:
        raise SystemExit(f"indonesia: East and North Kalimantan's tables add to {kalimantan:,} "
                         f"against the 2010 population {expected:,}")
    check_national(national, read_counts, javanese)
    return records, javanese


def check_national(national: dict[str, int], read_counts: dict[str, int],
                   javanese: dict[str, int]) -> None:
    """The census's national figures against what the provinces add to."""
    published = national.get("Javanese")
    if not published:
        raise SystemExit("indonesia: no Javanese figure in the national table")
    summed = sum(javanese.values())
    log(f"  national check: Javanese {summed:,} across {len(javanese)} provinces against "
        f"the census's {published:,} ({100 * summed / published:.2f}%)")
    if abs(summed - published) > NATIONAL_TOLERANCE * published:
        raise SystemExit(f"indonesia: Javanese across the provinces is {summed:,} against "
                         f"the census's {published:,}; a province table is wrong")
    for label in ("Sundanese", "Batak", "Madurese", "Betawi", "Minangkabau", "Buginese",
                  "Bantenese", "Banjar", "Balinese", "Acehnese", "Dayak", "Sasak",
                  "Makassarese", "Cirebonese"):
        theirs = next((v for k, v in national.items() if k.startswith(label[:5])), None)
        mine = read_counts.get(label)
        if theirs and mine:
            log(f"    {label}: {mine:,} read, {theirs:,} published ({100 * mine / theirs:.1f}%)")


def regency_title(name: str) -> str:
    if name in REGENCY_TITLES:
        return REGENCY_TITLES[name]
    return name if name.startswith("Kota ") else f"Kabupaten {name}"


def regency_records(fetch_page=fetch) -> list[dict[str, Any]]:
    provinces = {s["id"]: s["name"] for s in shapes("admin1")}
    records: list[dict[str, Any]] = []
    kinds: dict[str, int] = {}
    unread: list[str] = []
    for shape in shapes("admin2"):
        name, province = shape["name"], provinces.get(shape["parent"], "")
        if name in NOT_REGENCIES or not province:
            continue
        title = regency_title(name)
        wikitext, resolved = fetch_page(title, "id")
        if not wikitext:
            unread.append(f"{province}/{name} ({title})")
            continue
        reading = read_religion(wikitext, resolved)
        if not reading:
            unread.append(f"{province}/{name}")
            continue
        kinds[reading["kind"]] = kinds.get(reading["kind"], 0) + 1
        rf = religion_fields(reading, resolved)
        source = rf.pop("religion_source")
        short = re.sub(r"^(Kabupaten|Kota Administrasi)\s+", "", resolved)
        records.append(record(f"{ISO3}-{slugify(province)}-{slugify(name)}", name,
                              level="admin2", parent=f"{ISO3}-{slugify(province)}",
                              parent_name=province, country=ISO3,
                              aliases=[short] if short != name else [],
                              sources=[source], **rf))
    log(f"  regencies: {len(records)} read; by kind of source: "
        + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    if unread:
        log(f"  not read ({len(unread)}): {', '.join(unread)}")
    return records


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

INFOBOX_KEYS = re.compile(r"^\s*\|\s*(agama|suku|suku[_ ]bangsa|bahasa|penduduk|"
                          r"tahun|sumber|populasi|jumlah_penduduk|population|"
                          r"religion|ethnic|kepadatan|data_tahun|tahun_data)"
                          r"[^=]*=", re.I)


def probe_infobox(titles: list[str], width: int) -> None:
    for title in titles:
        text, resolved = fetch(title)
        log(f"  [id] {title!r} -> {resolved!r}: {len(text):,} bytes")
        for entry in infobox_lines(text):
            if INFOBOX_KEYS.match(entry):
                flat = " ".join(entry.split())
                log(f"     {flat[:width]}")
        if text:
            reading = read_religion(text, resolved)
            if reading:
                log(f"     -> {reading['kind']} {reading['year']}: "
                    + ", ".join(f"{r['group']} {r['pct']}" for r in reading["rows"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="both", choices=["province", "regency", "both"])
    ap.add_argument("--infobox", nargs="+", default=[], metavar="TITLE",
                    help="print the demographic parameters of these articles' infoboxes")
    ap.add_argument("--width", type=int, default=900)
    args = ap.parse_args()
    if args.infobox:
        probe_infobox(args.infobox, args.width)
        return 0
    log("indonesia: ethnicity by province (2010 census) and religion by province and "
        "regency, read from the Indonesian Wikipedia")
    records: list[dict[str, Any]] = []
    if args.level in ("province", "both"):
        provinces, _ = province_records()
        with_eth = sum(1 for r in provinces if isinstance(r.get("ethnicity"), list))
        with_rel = sum(1 for r in provinces if isinstance(r.get("religion"), list))
        log(f"  provinces: {len(provinces)}; ethnicity on {with_eth}, religion on {with_rel}")
        records += provinces
    if args.level in ("regency", "both"):
        records += regency_records()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
