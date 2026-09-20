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
import time
import urllib.parse
from pathlib import Path
from typing import Any

from . import indonesia_portals as portals
from ._shared import (NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_json,
                      log, measure, record, write_json)

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
RELIGION_TOLERANCE = 0.6     # an infobox's religion shares, against 100: beyond it, a remark
RELIGION_BOUNDS = (90.0, 103.0)   # beyond these, the figure is refused rather than remarked on
REMAINDER = "Other or not stated"
NATIONAL_TOLERANCE = 0.005   # the Javanese sum, against the census: beyond it, a remark
NATIONAL_REFUSAL = 0.03      # beyond this, a province table is wrong and the run refuses

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
# Five of the shapes the boundary file draws at this level are not regencies
# and nobody lives in them. That is not a guess from their names: UN OCHA's
# COD-PS catalogue entry for Indonesia says the boundary set "includes 17
# uninhabited features (comprising lakes, reservoirs, and a park) that are
# not represented in this dataset", and lists these among the eight it names
# at admin2 -- Danau ID1388/ID1688/ID1888/ID7188, Danau Toba ID1288, Hutan
# ID3399, Waduk Cirata ID3288, Wadung Kedungombo ID3388.
#
# They were skipped in silence, so each fell through to the build's generic
# "nothing was read for this unit", which is true and is the wrong reason: it
# reads as a regency awaiting data. Each now gets a record that says what the
# shape is. There is no composition to find and no head count to look for.
NOT_REGENCIES: dict[str, str] = {
    "Danau": "a lake",
    "Danau Toba": "Lake Toba",
    "Hutan": "a forest",
    "Waduk Cirata": "the Cirata reservoir",
    "Wadung Kedungombo": "the Kedungombo reservoir",
}
COD_AB_CAVEAT = ("UN OCHA Common Operational Dataset, Indonesia subnational "
                 "population statistics (COD-PS), catalogue caveat on the "
                 "uninhabited features of the matching boundary set")
COD_AB_URL = "https://data.humdata.org/dataset/cod-ps-idn"
UNINHABITED = (
    "This shape is {what}, not a regency, and nobody lives in it. The "
    "boundary file draws it at the same level as Indonesia's regencies and "
    "cities; UN OCHA's population dataset for the same boundaries names it "
    "as one of seventeen uninhabited features -- lakes, reservoirs and a "
    "park -- that carry no population, and publishes no row for it. There is "
    "no composition to be missing here.")
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
    "suku bangsa lainnya": "Other ethnic groups", "bangsa lainnya": "Other ethnic groups",
    "bangsa lain": "Other ethnic groups", "etnis lainnya": "Other ethnic groups",
    "etnis lain": "Other ethnic groups",
}
# An unknown row this small is carried in the residual and named in the
# note; a larger one refuses the run, since it would be a people unplaced.
SMALL_UNKNOWN = 0.01
# East Nusa Tenggara's "asal Kalimantan" row, carried as the residual: see
# the module docstring.
RESIDUAL_BY_PROVINCE: dict[tuple[str, str], str] = {
    ("East Nusa Tenggara", "asal kalimantan"): "Other ethnic groups",
}
# What a province's table does that its note has to say. Banten's folds the
# census's Bantenese (4.66 million nationally, nearly all of them in Banten)
# into its Sunda row, which is why the national check reads Sundanese at
# 112% of the census figure and Bantenese at 2%.
PROVINCE_REMARKS: dict[str, str] = {
    "Banten": "The article's 'Sunda' row folds the census's Bantenese, 4.66 million "
              "nationally, into Sundanese; the two are not separated here.",
}
RESIDUAL = "Other ethnic groups"
# Two sentences, and a third only where the table needed a decision; the
# method is in docs/SOURCES.md, not on every row.
ETHNIC_NOTE = (
    "2010 Population Census counts by ethnic group (BPS), as the Indonesian Wikipedia "
    "article '{title}' transcribes them; shares recomputed from the counts. BPS files a "
    "province's smaller peoples by region of origin ('asal Sulawesi'), carried here "
    "under a regional label."
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
    # A bucket naming two faiths at once is not two rows: the article gives
    # Puncak Jaya's Hindus and Buddhists together as 0.01%, and splitting
    # that would be inventing the split. It goes where "Konghucu dan
    # kepercayaan" already goes, for the same reason.
    "hindu/buddha": "Other religion", "buddha/hindu": "Other religion",
    "hindu dan buddha": "Other religion", "buddha dan hindu": "Other religion",
}
CHRISTIAN_PARENTS = {"Christianity"}
CHRISTIAN_CHILDREN = {"Protestantism", "Catholicism"}

# What a citation is, from the host it points at or the name it is given.
SOURCE_KINDS: tuple[tuple[str, str, str], ...] = (
    ("census2010", r"sp2010\.bps\.go\.id|sensus penduduk 2010|sensus 2010|sp2010",
     "the 2010 Population Census (BPS)"),
    ("bps", r"bps\.go\.id|badan pusat statistik|dalam angka",
     "a BPS (Statistics Indonesia) population-by-religion table"),
    ("dukcapil", r"dukcapil|kementerian dalam negeri|kemendagri|capil|kependudukan",
     "the Ministry of Home Affairs' civil registry (Dukcapil)"),
    ("kemenag", r"kemenag|kementerian agama",
     "the Ministry of Religious Affairs (Kemenag)"),
    ("jakarta", r"statistik\.jakarta\.go\.id",
     "the Jakarta provincial statistics office"),
)
EXPLAINED = dict((k, e) for k, _, e in SOURCE_KINDS)
EXPLAINED["other"] = "a regional government figure"
# One sentence on what kind of figure it is.
CAVEAT = {
    "census2010": "A census count.",
    "bps": "A statistical-office table, not the census.",
    "dukcapil": "A registry count of the religion on residents' identity cards, not a "
                "census answer.",
    "kemenag": "A ministry count of adherents, not a census answer.",
    "jakarta": "A provincial statistics figure, not a census count.",
    "other": "A regional government figure, not a census count.",
}
KIND_RANK = {"census2010": 0, "bps": 1, "kemenag": 2, "dukcapil": 3, "jakarta": 4, "other": 5}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

PAUSE = 0.4            # seconds between requests: 550 articles, and the API is shared
BACKOFF = (60, 120, 240)   # after http_get's own retries have failed on a 429


def fetch(title: str, lang: str = "id") -> tuple[str, str]:
    """The article's wikitext and the title it resolved to (after redirects).

    The MediaWiki API answers 429 when a client asks too fast, and the
    runner is shared with other probes; requests are spaced, and a refusal
    that outlasts http_get's own retries waits a minute or more and asks
    again before giving up.
    """
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    api = API if lang == "id" else EN_API
    time.sleep(PAUSE)
    for wait in (*BACKOFF, None):
        try:
            data = http_json(f"{api}?{q}", timeout=90)
            break
        except RuntimeError as exc:
            if wait is None:
                raise
            log(f"  [{lang}] {title!r}: {exc}; waiting {wait}s")
            time.sleep(wait)
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
    m = re.search(r"\|\s*" + re.escape(field) + r"\s*=\s*([^|}]*)", body, re.I)
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
    if not years:
        # The citation's own date of publication; never its access date,
        # which is when the editor read it.
        dated = " ".join(cite_field(body, f) for f in ("year", "date", "publication-date"))
        years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", dated)]
    year = max(years) if years else (2010 if kind == "census2010" else None)
    return kind, year, title or url or body[:80]


# Up to three decimals. Two cut Jakarta Timur's "0,454% Buddha" in half and
# left "4% Buddha" as the faith's name, which is no faith and refused the
# whole regency. The lookbehind still refuses to start inside a number, so
# this cannot walk into a thousands separator.
PERCENT = re.compile(r"(?<![\d,.])(\d{1,3}(?:[.,]\d{1,3})?)\s*%?")
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
    text = re.sub(r"&nbsp;|[   ]", " ", text)
    # A piped link carries the separator inside it; resolve links to their
    # display text before the value is cut at pipes.
    # A space either side, because the markup is the only separator between a
    # link and the word next to it: Minahasa Tenggara writes "[[Buddhisme|
    # Budha]] dan[[Agama Hindu|Hindu]]", which resolved bare reads
    # "Budha danHindu". The pieces are whitespace-collapsed after, so a link
    # that already had a space either side is unchanged.
    text = LINK.sub(lambda m: " " + m.group(1).split("|")[-1] + " ", text)
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
    """The label an item names, its markup and punctuation gone.

    "%" is stripped with the rest: Bangka Barat and Bangka Tengah write their
    Christian share "1,93%%" and "5,08%%", and the second sign is left behind
    on the label, where "% Kristen" is not a faith this reader knows.
    """
    return " ".join(label.replace("[[", " ").replace("]]", " ").split()).strip(" .;:<>=()%")


def religion_shares(items: list[tuple[str, float]]
                    ) -> tuple[list[dict[str, Any]], str | None, str]:
    """The map's rows, why they could not be read, and a remark for the
    note where the shares needed a decision.

    Christianity given beside its Protestant and Catholic parts is the same
    people twice, so the parent is dropped where its parts are present. A
    list that stops short of 100 carries the rest as a remainder row; one
    that overruns by a little is published as printed with the overrun in
    the note, by the owner's instruction, and only one that is far off is
    refused.
    """
    rows: dict[str, float] = {}
    unknown: list[str] = []
    for label, pct in items:
        key = re.sub(r"\s+", " ", label.lower()).strip()
        key = re.sub(r"^agama ", "", key)
        # "Budha" is the everyday Indonesian spelling of "Buddha" and the
        # articles use both, including inside a joint bucket -- Minahasa
        # Tenggara's "Budha dan Hindu" against Puncak Jaya's "Hindu/Buddha".
        # One spelling, so a joint bucket does not need four entries.
        key = re.sub(r"\bbudha\b", "buddha", key)
        # "Hindu/Buddha" and "Hindu / Buddha" are the same bucket; the space
        # is only there because Puncak Jaya writes the two as separate links
        # and a link resolves with a space either side.
        key = re.sub(r"\s*/\s*", "/", key)
        mapped = RELIGION_LABELS.get(key)
        if mapped is None:
            unknown.append(label)
            continue
        rows[mapped] = rows.get(mapped, 0.0) + pct
    if unknown:
        return [], f"unknown faith label(s) {unknown}", ""
    if rows.keys() & CHRISTIAN_CHILDREN:
        for parent in CHRISTIAN_PARENTS:
            rows.pop(parent, None)
    if not rows:
        return [], "no faiths", ""
    total = sum(rows.values())
    remark = ""
    if not RELIGION_BOUNDS[0] <= total <= RELIGION_BOUNDS[1]:
        return [], f"shares add to {total:.2f}", ""
    if total < 100.0 - RELIGION_TOLERANCE:
        rows[REMAINDER] = round(100.0 - total, 2)
        remark = f"The article's faiths add to {total:.1f}%; the rest is carried as a remainder."
    elif total > 100.0 + RELIGION_TOLERANCE:
        remark = f"As printed the shares add to {total:.1f}%, and are carried as printed."
    out = [{"group": g, "pct": round(p, 2)} for g, p in rows.items()]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out, None, remark


def read_religion(wikitext: str, title: str) -> dict[str, Any] | None:
    """The infobox's religion composition with its citation, or None with a
    reason logged."""
    value = infobox_param(wikitext, "agama")
    if not value:
        log(f"    {title}: no religion in the infobox")
        return None
    definitions = ref_definitions(wikitext)
    cites = citations(value, definitions)
    if not cites:
        # A reference used by a name the page never defines is a citation
        # to nothing: it has no year and no table behind it, whatever the
        # name suggests.
        missing = unresolved(value, definitions)
        log(f"    {title}: religion figure carries no citation"
            + (f" (named references {missing} defined nowhere)" if missing else "")
            + "; not read")
        return None
    rows, why, remark = religion_shares(religion_items(value))
    if why:
        log(f"    {title}: {why}; not read")
        return None
    described = [describe_citation(c) for c in cites]
    described.sort(key=lambda d: KIND_RANK[d[0]])
    kind, year, what = described[0]
    years = [d[1] for d in described if d[1]]
    year = year or (max(years) if years else None)
    if year is None:
        # A composition with no year is a claim the map cannot date, and an
        # editor's access date is when the page was read, not when the
        # office counted. Not read, rather than stamped with a guess.
        log(f"    {title}: the citation carries no year; not read")
        return None
    if remark:
        log(f"    {title}: {remark}")
    return {"rows": rows, "kind": kind, "year": year, "cited": what,
            "all": [d[2] for d in described], "remark": remark}


def religion_fields(reading: dict[str, Any], title: str) -> dict[str, Any]:
    """The record's religion fields, with a note of two or three sentences:
    what the figure is and where from, what kind of count it is, and the one
    thing about this article that needed saying, if anything."""
    kind = reading["kind"]
    when = f" for {reading['year']}" if reading["year"] else ""
    sentences = [f"Population by religion{when} from {EXPLAINED[kind]}, as the Indonesian "
                 f"Wikipedia article '{title}' cites it.", CAVEAT[kind]]
    if reading.get("remark"):
        sentences.append(reading["remark"])
    note = " ".join(sentences)
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
# The head count, read from the same infobox as the faiths
# ---------------------------------------------------------------------------

# A count written with dots or spaces as thousands separators, or bare.
HEAD_COUNT = re.compile(r"(\d{1,3}(?:[.\u00a0 ]\d{3})+|\d{4,9})")
# What the count is, per kind of citation. Kemenag counts adherents and never
# a population, so a head count citing it is not one of these and is refused
# with the rest of "other".
POPULATION_KINDS: dict[str, str] = {
    "census2010": "BPS, 2010 Population Census, total population",
    "bps": "BPS (Statistics Indonesia), total population",
    "dukcapil": "Kementerian Dalam Negeri, Dukcapil civil registry, "
                "registered population",
    "jakarta": "Jakarta provincial statistics office, total population",
}


def read_population(wikitext: str,
                    title: str) -> tuple[dict[str, Any] | None, str]:
    """The infobox's head count with its year and citation, and why not.

    Returns ``(reading, "")`` when the count is read and ``(None, reason)``
    when it is refused. The reason is written onto the record, because a
    refusal that leaves a bare gap tells a reader of the map nothing: 44
    regencies carried an empty population field and not one of them said
    whether the figure was missing, uncited or undated.

    This exists because of a refusal. The regency compositions are
    percentages and nothing else -- not one of the 491 articles prints a
    count beside a faith -- so summing a province out of its regencies means
    pricing each regency's percentages against that regency's population, and
    Wikidata has none for eleven of the shapes inside Papua and West Papua.
    The build therefore refused both provinces ("5 children have no
    population") while every regency under them carried a composition. The
    weight was sitting in the same infobox as the shares, one parameter
    above them, and citing the same registry.

    The rules are the ones ``read_religion`` keeps, and for the same reasons:
    a figure with no citation is not read, and a figure the citation cannot
    date is not read. A registry total and a census total are different
    counts, so which it is goes in the record.
    """
    value = infobox_param(wikitext, "penduduk")
    if not value:
        return None, "the article's infobox carries no head count at all"
    definitions = ref_definitions(wikitext)
    # The year is written under either of two names. The infobox template
    # accepts both, and reading only one of them refused a figure that was
    # there and dated -- Banyuwangi's 1,785,316 for 30 June 2024 is under
    # "tahun populasi", not "penduduktahun".
    dated = (infobox_param(wikitext, "penduduktahun")
             or infobox_param(wikitext, "tahun populasi") or "")
    # The count's own reference lives in a parameter of its own, which is
    # where nearly every article puts it; a few attach it to the value, and a
    # few to the year beside it -- Musi Rawas Utara writes
    # "penduduktahun = 2023<ref name=DUKCAPIL>...". A reference on the year
    # that dates the count is a reference for the count: it is the same
    # snapshot, and it is the one the editor put there for it. A reference
    # anywhere *else* in the infobox is not, and is still not read.
    cites = (citations(value, definitions)
             + citations(infobox_param(wikitext, "pendudukref") or "", definitions)
             + citations(dated, definitions))
    if not cites:
        log(f"    {title}: the head count carries no citation; not read")
        return None, ("the article prints a head count and cites nothing for "
                      "it; an uncited figure is not read")
    text = REF.sub("", value).replace("[[", " ").replace("]]", " ")
    m = HEAD_COUNT.search(text)
    if not m:
        log(f"    {title}: no head count in {' '.join(text.split())[:60]!r}; not read")
        return None, ("the infobox's population parameter holds no number this "
                      "reader can take as a head count")
    total = int(re.sub(r"[.\u00a0 ]", "", m.group(1)))
    # In citation order, not by rank. ``read_religion`` ranks because several
    # references may each describe the one composition and the best of them
    # should be named; a head count is one number as of one date, and the
    # reference the article puts first beside it is the one it came from.
    # Kota Jayapura cites the registry and then a 2021 BPS yearbook, and its
    # 404,799 is the registry's figure for 31 December 2024, not the
    # yearbook's for 2021.
    described = [describe_citation(c) for c in cites]
    kind = described[0][0]
    if kind not in POPULATION_KINDS:
        log(f"    {title}: the head count cites {kind}, which does not "
            f"publish one; not read")
        return None, (f"the head count's citation is {EXPLAINED.get(kind, kind)}, "
                      f"which does not publish a head count for a regency; a "
                      f"reference the page never defines reads as one of these")
    # "31 Desember [[2024]]" -- the date the count is *as of*, which is the
    # year that describes it. The citation's own year is the fallback, and it
    # is a worse one: an editor updates the figure more often than the
    # reference beside it.
    asof = re.findall(r"\b(19\d\d|20[0-2]\d)\b", dated)
    year = int(asof[-1]) if asof else described[0][1]
    if year is None:
        log(f"    {title}: the head count carries no year; not read")
        return None, ("neither the head count nor its citation carries a year, "
                      "so there is no date the figure is as of")
    return {"total": total, "year": year, "kind": kind}, ""


def population_fields(reading: dict[str, Any], title: str) -> dict[str, Any]:
    """The record's population fields: the count, its year, and one sentence
    saying which of the two national counts it is."""
    name = POPULATION_KINDS[reading["kind"]]
    registry = reading["kind"] == "dukcapil"
    note = (f"Total population for {reading['year']} from {EXPLAINED[reading['kind']]}, "
            f"as the Indonesian Wikipedia article '{title}' cites it."
            + (" A registry counts the people holding an identity card for the "
               "regency, which is not the same number as a census count."
               if registry else ""))
    return {
        "population": measure(reading["total"], year=reading["year"], source=name),
        "population_note": note,
        "population_source": {"field": "population", "name": name,
                              "url": "https://id.wikipedia.org/wiki/"
                                     + title.replace(" ", "_"),
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
    if label is None and key.startswith("asli papua"):
        label = "Papuan"       # "Asli Papua", "Asli Papua Barat dan ...": the native peoples
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
        if rest and abs(biggest[1] - rest) <= TOTAL_TOLERANCE * rest:
            total = biggest[1]
            body.remove(biggest)
    # A row whose name is a number is the total row with its name pushed
    # out of its column; if it was not the sum of the rest it is dropped
    # here rather than refused as an unknown people.
    body = [(name, count) for name, count in body if not as_count(name)]
    return body, total


def read_ethnicity(wikitext: str, province: str, title: str, expected: int | None = None
                   ) -> tuple[dict[str, int], int, str] | None:
    """{label: count} for the province, the denominator and a remark for the
    note where the table needed a decision, or None.

    ``expected`` is the province's 2010 census population. Riau's table
    prints a total that is not the sum of its rows and not the 2010
    population either (6.4 million against 5.5), while its rows add to
    what the census counted; where the rows fit the census and the printed
    total does not, the rows win and the slip is on record.
    """
    found = ethnic_table(wikitext)
    if not found:
        log(f"    {province}: no 2010 ethnic table in '{title}'")
        return None
    rows, name_col = found
    body, total = split_total(table_rows(rows, name_col), province, title)
    counts: dict[str, int] = {}
    unknown: list[tuple[str, int]] = []
    for name, count in body:
        key = normalise_label(name)
        if not key:
            continue
        label = ethnic_label(province, key)
        if label is None:
            unknown.append((name, count))
            continue
        counts[label] = counts.get(label, 0) + count
    if not counts:
        log(f"    {province}: the ethnic table has no readable rows")
        return None
    remark = ""
    if unknown:
        whole = sum(counts.values()) + sum(c for _, c in unknown)
        big = [n for n, c in unknown if c > SMALL_UNKNOWN * whole]
        if big:
            raise SystemExit(f"indonesia: {province}: ethnic labels not in ETHNIC_LABELS: {big}")
        for name, count in unknown:
            counts[RESIDUAL] = counts.get(RESIDUAL, 0) + count
        remark = ("Rows the reader has no label for are in 'Other ethnic groups': "
                  + ", ".join(f"'{n}' ({100 * c / whole:.1f}%)" for n, c in unknown) + ".")
    summed = sum(counts.values())
    if total is None:
        log(f"    {province}: no total row; the rows' sum {summed:,} stands as the total")
    elif abs(summed - total) > TOTAL_TOLERANCE * total:
        if expected and fits(summed, expected) and not fits(total, expected):
            remark = join(remark, f"The table's printed total, {total:,}, is not the 2010 "
                          f"census population; its rows add to {summed:,}, which is, and "
                          "are the denominator.")
        else:
            raise SystemExit(f"indonesia: {province}: rows add to {summed:,} against the "
                             f"table's total {total:,} ({100 * summed / total:.2f}%)")
    elif summed != total:
        # Central Kalimantan's rows add to 0.3% more than its printed total:
        # a transcription slip in one or the other. The rows are the figures
        # carried, so they are the denominator, and the slip is on record.
        remark = join(remark, f"The table's rows add to {summed:,} against its printed "
                      f"total {total:,}; the rows are the denominator.")
    if province in {p for p, _ in RESIDUAL_BY_PROVINCE}:
        remark = join(remark, "The article's 'asal Kalimantan' row, 14.5%, is carried in "
                      "'Other ethnic groups': no census of the province supports a "
                      "Kalimantan share of that size.")
    if province in PROVINCE_REMARKS:
        remark = join(remark, PROVINCE_REMARKS[province])
    if remark:
        log(f"    {province}: {remark}")
    return counts, summed, remark


def join(remark: str, sentence: str) -> str:
    return f"{remark} {sentence}" if remark else sentence


def fits(total: int, expected: int) -> bool:
    """Whether a table's population is the 2010 census's, allowing for the
    respondents a census tabulation of ethnicity leaves out."""
    return 0.85 * expected <= total <= 1.03 * expected


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
            expected = populations.get(resolved) or populations.get(title)
            if province in SPLIT_2012:
                # North Kalimantan left East Kalimantan in 2012, and each
                # article's table is for the province as it now is while the
                # 2010 population is for the province as it was. Their two
                # tables add to it; the check is over the pair.
                expected = None
            found = read_ethnicity(wikitext, province, resolved, expected)
            if found:
                counts, total, remark = found
                if expected and not fits(total, expected):
                    ratio = total / expected
                    if not 0.7 <= ratio <= 1.15:
                        raise SystemExit(f"indonesia: {province}: the ethnic table's total "
                                         f"{total:,} is not the 2010 population {expected:,}")
                    remark = (remark + " " if remark else "") + (
                        f"The table covers {total:,} people, {100 * ratio:.1f}% of the "
                        f"province's 2010 census population.")
                    log(f"    {province}: {remark}")
                rows = ethnic_rows(counts, total)
                summed = sum(r["pct"] for r in rows)
                if abs(summed - 100.0) > SUM_TOLERANCE:
                    raise SystemExit(f"indonesia: {province}: shares add to {summed:.2f}")
                fields.update(ethnicity=rows, ethnicity_year=ETHNICITY_YEAR,
                              ethnicity_note=ETHNIC_NOTE.format(title=resolved)
                              + (f" {remark}" if remark else ""))
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
    if kalimantan and expected and not fits(kalimantan, expected):
        log(f"  East and North Kalimantan's tables add to {kalimantan:,} against the 2010 "
            f"population {expected:,}")
    remark = check_national(national, read_counts, javanese)
    if remark:
        for r in records:
            if isinstance(r.get("ethnicity"), list):
                r["ethnicity_note"] += " " + remark
    return records, javanese


def check_national(national: dict[str, int], read_counts: dict[str, int],
                   javanese: dict[str, int]) -> str:
    """The census's national figures against what the provinces add to.

    Within half a percent is agreement. Off by more than that but by a
    little, the figures are published and the disagreement goes on every
    province's note in one sentence, by the owner's instruction; off by a
    lot, a province table is wrong and the run refuses.
    """
    published = national.get("Javanese")
    if not published:
        raise SystemExit("indonesia: no Javanese figure in the national table")
    summed = sum(javanese.values())
    ratio = summed / published
    log(f"  national check: Javanese {summed:,} across {len(javanese)} provinces against "
        f"the census's {published:,} ({100 * ratio:.2f}%)")
    remark = ""
    if abs(ratio - 1) > NATIONAL_TOLERANCE:
        if abs(ratio - 1) > NATIONAL_REFUSAL:
            raise SystemExit(f"indonesia: Javanese across the provinces is {summed:,} "
                             f"against the census's {published:,}; a province table is wrong")
        remark = (f"Summed over the provinces read, Javanese come to {100 * ratio:.1f}% of "
                  f"the census's national figure.")
    for label in ("Sundanese", "Batak", "Madurese", "Betawi", "Minangkabau", "Buginese",
                  "Bantenese", "Banjar", "Balinese", "Acehnese", "Dayak", "Sasak",
                  "Makassarese", "Cirebonese"):
        theirs = next((v for k, v in national.items() if k.startswith(label[:5])), None)
        mine = read_counts.get(label)
        if theirs and mine:
            log(f"    {label}: {mine:,} read, {theirs:,} published ({100 * mine / theirs:.1f}%)")
    return remark


def regency_title(name: str) -> str:
    if name in REGENCY_TITLES:
        return REGENCY_TITLES[name]
    return name if name.startswith("Kota ") else f"Kabupaten {name}"


def regency_shape_names(province: str) -> dict[str, dict[str, Any]]:
    provinces = {s["id"]: s["name"] for s in shapes("admin1")}
    return {s["name"]: s for s in shapes("admin2")
            if provinces.get(s["parent"], "") == province
            and s["name"] not in NOT_REGENCIES}


def regency_record(name: str, province: str, fields: dict[str, Any],
                   sources: list[dict[str, str]], resolved: str = "") -> dict[str, Any]:
    short = re.sub(r"^(Kabupaten|Kota Administrasi)\s+", "", resolved) if resolved else name
    return record(f"{ISO3}-{slugify(province)}-{slugify(name)}", name,
                  level="admin2", parent=f"{ISO3}-{slugify(province)}",
                  parent_name=province, country=ISO3,
                  aliases=[short] if short != name else [],
                  sources=sources, **fields)


def hapi_by_province() -> dict[str, dict[str, dict[str, Any]]]:
    """HAPI's regency head counts, keyed by the province name this map uses.

    HAPI names a province in Indonesian where this map names it in English,
    and PROVINCES already holds both -- the article title and the aliases --
    so the join is a lookup rather than a second table to keep in step. All
    34 match; a province that stopped matching would silently lose its
    regencies, so the count is logged.
    """
    from . import indonesia_hapi                   # noqa: PLC0415 -- optional

    lookup: dict[str, str] = {}
    for english, (title, aliases) in PROVINCES.items():
        for name in [english, title, *aliases]:
            lookup[re.sub(r"[^a-z]", "", name.lower())] = english
    out: dict[str, dict[str, dict[str, Any]]] = {}
    unknown: set[str] = set()
    for row in indonesia_hapi.committed():
        english = lookup.get(re.sub(r"[^a-z]", "", row["admin1_name"].lower()))
        if not english:
            unknown.add(row["admin1_name"])
            continue
        out.setdefault(english, {})[row["admin2_name"]] = row
    if unknown:
        log(f"  hapi: {len(unknown)} province name(s) match none of this map's: "
            f"{', '.join(sorted(unknown))}")
    if out:
        log(f"  hapi: {sum(len(v) for v in out.values())} regency head counts "
            f"available across {len(out)} provinces, as a last resort")
    return out


def hapi_fields(row: dict[str, Any], name: str, why: str) -> dict[str, Any]:
    """The population fields for a regency filled from HAPI.

    The licence is on the record rather than only in the docs, because this
    one is not open and a reader of the map should be able to see that
    without going looking for it.
    """
    from . import indonesia_hapi                   # noqa: PLC0415 -- optional

    year = int(row["year"])
    return {
        "population": measure(int(row["population"]), year=year,
                              source=indonesia_hapi.PUBLISHER),
        "population_note": (
            f"Total population for {year} from {indonesia_hapi.PUBLISHER}, "
            f"served through UN OCHA's Humanitarian API. Used because the "
            f"article route found none: {why}. {indonesia_hapi.CAVEAT} "
            f"{indonesia_hapi.TERMS}"),
        "population_source": {
            "field": "population",
            "name": indonesia_hapi.PUBLISHER,
            "url": indonesia_hapi.DATASET,
            "license": indonesia_hapi.LICENCE,
        },
    }


def portal_records(known: dict[str, dict[str, dict[str, float]]],
                   unread: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """The regencies the infobox could not answer for, from the provincial and
    regency open-data portals.

    ``known`` is every regency already read, by province, which is what
    ``resolve_pair`` scores a workbook's Christian columns against; ``unread``
    is the ones still empty, by province, mapped to the reason they are. A
    portal table covers a whole province and most of its units are already
    read from their own articles; only the empty ones are written, because a
    composition already carried is not improved by a second one of a different
    vintage.
    """
    records: list[dict[str, Any]] = []
    for source in portals.SOURCES:
        names = regency_shape_names(source.province)
        if not names:
            log(f"  portals: {source.key}: no shapes under {source.province}")
            continue
        counts, swap = portals.readings(source, known.get(source.province, {}), names)
        if not counts:
            log(f"  portals: {source.key}: nothing committed under "
                f"data/raw/indonesia_portals; run --fetch on the runner")
            continue
        wanted = unread.get(source.province, {})
        filled = [n for n in counts if n in wanted]
        log(f"  portals: {source.key} ({source.host}, {source.year}): {len(counts)} units, "
            f"{len(filled)} of them unread -- {', '.join(sorted(filled)) or 'none'}")
        for name in sorted(filled):
            fields = portals.fields(source, counts[name], swap)
            sources = [fields.pop("religion_source")]
            # The table's own total is this regency's head count, and these
            # eight had none at all: the shares are computed from counts, so
            # the count is there to be read.
            if "population_source" in fields:
                sources.append(fields.pop("population_source"))
            records.append(regency_record(name, source.province, fields, sources))
    return records


def regency_records(fetch_page=fetch) -> list[dict[str, Any]]:
    provinces = {s["id"]: s["name"] for s in shapes("admin1")}
    records: list[dict[str, Any]] = []
    kinds: dict[str, int] = {}
    unread: dict[str, dict[str, str]] = {}
    refusals: dict[str, int] = {}
    known: dict[str, dict[str, dict[str, float]]] = {}
    counted = uninhabited = from_hapi = 0
    hapi = hapi_by_province()
    for shape in shapes("admin2"):
        name, province = shape["name"], provinces.get(shape["parent"], "")
        if not province:
            continue
        if name in NOT_REGENCIES:
            why = UNINHABITED.format(what=NOT_REGENCIES[name])
            records.append(regency_record(
                name, province,
                {field: gap(NOT_COLLECTED, why) for field in
                 ("religion", "ethnicity", "language")}
                | {"population": gap(NOT_COLLECTED, why)},
                [{"field": "religion/ethnicity/language/population",
                  "name": COD_AB_CAVEAT, "url": COD_AB_URL}]))
            uninhabited += 1
            continue
        title = regency_title(name)
        wikitext, resolved = fetch_page(title, "id")
        if not wikitext:
            unread.setdefault(province, {})[name] = f"no article at '{title}'"
            continue
        reading = read_religion(wikitext, resolved)
        if not reading:
            unread.setdefault(province, {})[name] = "the infobox figure is uncited, "\
                                                    "undated or unreadable"
            continue
        kinds[reading["kind"]] = kinds.get(reading["kind"], 0) + 1
        known.setdefault(province, {})[name] = {r["group"]: r["pct"] for r in reading["rows"]}
        fields = religion_fields(reading, resolved)
        sources = [fields.pop("religion_source")]
        head, why = read_population(wikitext, resolved)
        if head:
            counted += 1
            fields.update(population_fields(head, resolved))
            sources.append(fields.pop("population_source"))
        elif (last := hapi.get(province, {}).get(name)):
            # Last resort, and only ever into an empty field: the article
            # route is a count for 2023-2025 and this is a projection for
            # 2020 under a licence that is not open, so it fills a regency
            # that has nothing and never replaces one that has something.
            from_hapi += 1
            fields.update(hapi_fields(last, name, why))
            sources.append(fields.pop("population_source"))
        else:
            refusals[why] = refusals.get(why, 0) + 1
            fields["population"] = gap(
                NOT_AVAILABLE,
                f"No head count is published for this regency here: "
                f"{why}. The Indonesian Wikipedia article "
                f"'{resolved}' is what was read.")
        records.append(regency_record(name, province, fields, sources, resolved))
    log(f"  regencies: {len(records)} read from the infobox; by kind of source: "
        + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    log(f"  regencies with a head count: {counted} of {len(records)}")
    log(f"  {uninhabited} shapes at this level are uninhabited features, not "
        f"regencies, and say so: {', '.join(sorted(NOT_REGENCIES))}")
    for why, n in sorted(refusals.items(), key=lambda kv: -kv[1]):
        log(f"    {n} without one because {why}")
    if from_hapi:
        log(f"  {from_hapi} of those filled from HAPI instead -- a 2020 "
            f"projection under a licence that is not open; see "
            f"scripts/fetch_census/indonesia_hapi.py")
    flat = sorted(f"{prov}/{name}" for prov, names in unread.items() for name in names)
    if flat:
        log(f"  the infobox does not answer for {len(flat)}: {', '.join(flat)}")
    from_portals = portal_records(known, unread)
    for row in from_portals:
        unread.get(row["parent_name"], {}).pop(row["name"], None)
    records += from_portals
    log(f"  regencies: {len(records)} carry a composition, {len(from_portals)} of them "
        f"from an open-data portal")
    still = sorted(f"{prov}/{name}" for prov, names in unread.items() for name in names)
    if still:
        log(f"  still not read ({len(still)}): {', '.join(still)}")
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
        # Every named reference the whole page defines. Eight of the unread
        # regencies attach their faiths to a reference the page never defines
        # -- <ref name="dukcapil"/> and nothing behind it -- and the question
        # that settles is whether the definition is somewhere else on the page,
        # hung off a different parameter. Printing the names answers it.
        names = sorted(ref_definitions(text))
        log(f"     named references defined on the page ({len(names)}): "
            + (", ".join(names) if names else "none"))
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
