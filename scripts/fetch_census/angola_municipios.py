#!/usr/bin/env python3
"""Angola: the 2024 census by municipality, on the municipalities the map draws.

The 2024 Recenseamento Geral da População e Habitação (INE Angola) has a
*Relatório dos Resultados Definitivos* for each of the 21 provinces created
in 2024. Each report tabulates its province by the municipalities and
communes of Lei n.º 14/24 (326 municipalities in the country), while the map
draws the 164 municipalities of Lei n.º 18/16 (157 polygons). Two things in
the reports join the two:

* **A table on the old division.** Each report outside Luanda and Icolo e
  Bengo prints the population by sex at the 2014 and 2024 censuses on the
  municipalities of Lei 18/16 ("Quadro 11 - População residente por
  município, segundo o sexo, Censos 2014 e 2024" in Bengo's): that is each
  drawn municipality's own 2024 count and sex ratio, as INE publishes it.
* **The new municipalities, added up.** Ethnic group (Quadro 6.1), mother
  tongue (6.2), religion (7.1, 7.2) and age (1.4, 1.5) are printed for the
  new municipalities only. Each new municipality lies within one old one,
  and which one is found from the counts themselves: the new municipalities'
  2024 totals (Quadro 10) must add up to each old municipality's 2024 total
  in the old-division table, and the men and the women separately. Names
  seed it (a new municipality named as an old one stays in it); the rest is
  an exact-cover search that must have one solution and only one, or the
  province's compositions are not written.

**Which polygons.** A polygon gets its namesake's figures where OCHA's
boundaries of the 2016 municipalities (cod-ab-ago, 2018) and the polygon
agree, at least 70% of each lying inside the other; the overlay was measured
offline and its exceptions are listed below (DRAWN_TOGETHER, NOT_DESCRIBED).
Lobito's polygon holds Catumbela (98% of it) and Chitato's holds Lóvua
(OCHA itself unites them), and their counts are added. Cacula has no polygon
and is spread over four (Caluquembe 31%, Quilengues 26%, Quipungo 25%,
Lubango 16% of it); four more polygons depart from the municipality of their
name by more than 30%; and Luanda's and Icolo e Bengo's reports have no
table on the old division. Those polygons get no census figure, and their
compositions say why.

**Ages.** The reports print no five-year groups below the province. The
median of an old municipality is taken from the groups 0-14, 15-64 and 65+
(Quadro 1.4) and 0-19, 20-29, 30-54, 55-64, 65-74, 75+ (Quadro 1.5) of its
new municipalities, added up: 0-14, 15-19, 20-29, 30-54, 55-64, 65-74, 75+.
A province's median comes from its five-year groups (Quadro 1.3).

**Checks**, each refusing what it covers: every composition row's groups
make its total (within 0.5%), and its two column groups carry the same
total; a commune table's communes make their municipality; the new
municipalities make the province; the crosswalk is unique and adds up for
the total, the men and the women; each province's composition by group
equals the national report's (angola_province.json) for that province.

Usage:
    python -m scripts.fetch_census.angola_municipios [--run LABEL] [--only Bengo,...]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json,
)
from .angola_seats import ALIASES as LAW_ALIASES, polygon_keys
from .binding import fold
from .cod_ps_age import grouped_median

OUT = "angola_municipios.json"
YEAR = 2024
SITE = PROCESSED.parent.parent / "site" / "data"
URL = "https://censo2024.ine.gov.ao/Relatorio_Provincial_{stem}_Censo2024.pdf"
SOURCE = ("INE Angola, Recenseamento Geral da População e Habitação 2024, Relatório dos "
          "Resultados Definitivos, provincial reports")
LICENCE = "Official statistics publication of the Instituto Nacional de Estatística de Angola"

# Report file stem -> the map's province (the 2016 division) it lies in.
REPORTS: dict[str, str] = {
    "Cabinda": "Cabinda", "Zaire": "Zaire", "Uige": "Uíge", "Bengo": "Bengo",
    "Luanda": "Luanda", "Icolo_e_Bengo": "Luanda", "Cuanza_Norte": "Cuanza Norte",
    "Cuanza_Sul": "Cuanza Sul", "Malanje": "Malanje", "Lunda_Norte": "Lunda Norte",
    "Lunda_Sul": "Lunda Sul", "Moxico": "Moxico", "Moxico_Leste": "Moxico", "Bie": "Bié",
    "Huambo": "Huambo", "Benguela": "Benguela", "Namibe": "Namibe", "Huila": "Huíla",
    "Cunene": "Cunene", "Cubango": "Cuando Cubango", "Cuando_Cubango": "Cuando Cubango",
}

# The provinces as drawn whose reports print no table on the 2016 division:
# Luanda's and Icolo e Bengo's, Moxico's and Moxico Leste's (Moxico's table said
# to be on Lei 18/16 lists the 2024 municipalities), Cubango's and Cuando's.
NO_2016_TABLE = frozenset({"Luanda", "Moxico", "Cuando Cubango"})

# The 2024 provinces as their reports name them (Cuando's report is filed as
# Cuando_Cubango), for the notes.
SHOWN = {"Uige": "Uíge", "Icolo_e_Bengo": "Icolo e Bengo", "Cuanza_Norte": "Cuanza Norte",
         "Cuanza_Sul": "Cuanza Sul", "Lunda_Norte": "Lunda Norte", "Lunda_Sul": "Lunda Sul",
         "Moxico_Leste": "Moxico Leste", "Bie": "Bié", "Huila": "Huíla",
         "Cuando_Cubango": "Cuando"}

# The census's spelling of a 2016 municipality (folded) -> the polygon's (folded),
# beyond the law's own spellings (angola_seats.ALIASES).
ALIASES: dict[str, str] = {
    **LAW_ALIASES,
    "dembos": "dembosquibaxe", "quibaxe": "dembosquibaxe", "kuito": "cuito",
    "ekunha": "ecunha", "tombwa": "tombwa", "tomboa": "tombwa", "kilambakiaxi": "kilambakiaxi",
    "gambos": "gamboschiange", "chiange": "gamboschiange", "cunhinga": "cunhinga",
    "quiculungo": "quiculongo", "kiwabanzoji": "kiuabanzoji", "kiwaba": "kiuabanzoji",
    "pangoaluquem": "pangoaluquem", "ngonguembo": "ngonguembo", "gonguembo": "ngonguembo",
    "sambacaju": "sambacaju", "cuvango": "cuvango", "kuvango": "cuvango",
    "tchicalatcholoanga": "tchikalatcholohanga", "chicalacholoanga": "tchikalatcholohanga",
    "katchiungo": "catchiungo", "lumbalanguimbo": "bundas", "bundas": "bundas",
    "luchazes": "luchazes", "cameia": "cameia", "lumeje": "cameia", "camanongue": "camanongue",
    "nharea": "nharea", "mbanzakongo": "mbanzacongo", "nzeto": "nzeto",
    "cangola": "cangola", "altocauale": "cangola", "sanzapombo": "sanzapombo",
    "maqueladozombo": "maqueladozombo", "cacongo": "cacongo", "landana": "cacongo",
    "uige": "uige", "quitexe": "quitexe", "dangequitexe": "quitexe",
    "cela": "cela", "wakukungo": "cela", "sumbe": "sumbe", "seles": "seles",
    "amboim": "amboim", "gabela": "amboim", "libolo": "libolo", "calulo": "libolo",
    "quissama": "quissama", "quicama": "quissama", "kissama": "quissama",
    "ombadja": "ombadja", "ombandja": "ombadja", "cuanhama": "cuanhama", "kwanhama": "cuanhama",
    "baiafarta": "baiafarta", "kambambe": "cambambe", "cassongue": "cassongue",
}

# Polygons holding two municipalities of 2016 whose counts are added.
DRAWN_TOGETHER: dict[str, tuple[tuple[str, ...], str]] = {
    "91424787B28058724982941": (("Lobito", "Catumbela"),
                                "Catumbela has no polygon of its own and lies inside this one."),
    "91424787B90607964239215": (("Chitato", "Lóvua"),
                                "Lóvua has no polygon of its own and lies inside this one."),
}

NOT_DESCRIBED: dict[str, str] = {
    # Cacula has no polygon; OCHA's boundaries place it across these four.
    "91424787B79663411061170": (
        "About 28% of this polygon lies in the municipality of Cacula, which has no polygon "
        "of its own, so the census's figures for Caluquembe do not describe it, and Cacula's, "
        "which cover the rest of Cacula as well, do not either."),
    "91424787B76902935205568": (
        "About 19% of this polygon lies in the municipality of Cacula, which has no polygon "
        "of its own, so the census's figures for Quilengues do not describe it, and Cacula's, "
        "which cover the rest of Cacula as well, do not either."),
    "91424787B65395745560852": (
        "About 11% of this polygon, a quarter of Cacula, lies in the municipality of Cacula, "
        "which has no polygon of its own, so the census's figures for Quipungo do not "
        "describe it, and Cacula's, which cover the rest of Cacula as well, do not either."),
    "91424787B12923410016524": (
        "About 16% of this polygon lies in the municipality of Cacula, whose seat is inside it "
        "and which has no polygon of its own, so the census's figures for Lubango do not "
        "describe it, and Cacula's, which cover the rest of Cacula as well, do not either."),
    # The polygon and the municipality of its name, as OCHA draws it, part ways.
    "91424787B4488869677577": (
        "Only about 39% of this polygon lies in Pango Aluquém as OCHA's boundaries of the "
        "municipalities draw it, and about 48% in Cambambe, so the census's figures for Pango "
        "Aluquém do not describe it."),
    "91424787B64555741816921": (
        "Only about 53% of this polygon lies in Quiculungo as OCHA's boundaries of the "
        "municipalities draw it, and the rest in Banga and Samba Cajú, so the census's figures "
        "for Quiculungo do not describe it."),
    "91424787B22609176467527": (
        "About a third of Cambundi-Catembo, as OCHA's boundaries of the municipalities draw "
        "it, lies outside this polygon, most of it in the polygon drawn as Xá-Muteba, so the "
        "census's figures for Cambundi-Catembo do not describe it."),
    "91424787B55001564307677": (
        "About 27% of this polygon lies in Cambundi-Catembo, in Malanje, as OCHA's boundaries "
        "of the municipalities draw it, so the census's figures for Xá-Muteba do not "
        "describe it."),
}

GAP = 4.0          # points: digit groups of one figure sit closer than this
# The words of a total's column: "População com 2 ou mais anos", "Número de
# pessoas com 2 ou mais anos", "Total da população com 2 ou mais anos", "Total".
TOTAL_KEYS = ("populacaocom", "pessoascom", "2oumaisanos", "total")
ROW_TOLERANCE = 2.0
ORPHAN_REACH = 12.0
COLUMN_REACH = 6.0

UNIVERSE = "population aged 2 and over"
ETHNIC = {
    "Bakongo": ("quicongo", "kikongu", "conguês", "congues"),
    "Ambundu": ("quimbundo", "tymbundu"),
    "Lunda-Chokwe": ("lunda", "quioco", "kioko"),
    # Umbundo in most reports, Umbundu (ou Ovimbundu) in Lunda Norte's and others'.
    "Ovimbundu": ("umbundo", "ovimbundo", "umbundu", "ovimbundu"),
    "Nyaneka-Humbe": ("nhaneca", "nyaneka", "humbe"),
    "Ovambo": ("ambo", "vahambo", "xikwanyama"),
    "Herero": ("herero", "helelo"),
    "Cuangar": ("cuangar",),
    "Khoisan": ("khoisan",),
    "Vátua": ("vatua",),
    "Kwoi": ("kwoi",),
    "Ndonga": ("xindonga", "oshindonga"),
    # Ovanganguela, first in Cubango's and Cuando's tables.
    "Ngangela": ("ovanganguela", "vanganguela", "nganguela"),
    "Not stated": ("naosabe",),
    "Other": ("outra",),
}
LANGUAGE = {
    "Portuguese": ("portugues",),
    "Kimbundu": ("kimbundu",),
    "Umbundu": ("umbundu",),
    "Chokwe": ("cokue", "chokwe", "kioko"),
    "Kikongo": ("kikongo",),
    "Ngangela": ("nganguela", "ngangela"),
    "Nyaneka": ("olunyaneka", "nhaneca", "nyaneka"),
    "Kwanyama": ("oxikwanhama", "kwanhama", "kwanyama"),
    "Fiote": ("ifyoti", "fiote"),
    "Humbi": ("muhumbi", "humbi"),
    "Luvale": ("luvale",),
    "Khoisan": ("khoisan",),
    "Foreign languages": ("estrangeir", "estangeir"),
    # Namibe's table names them one by one, as the national report does.
    "Mandarin": ("mandarim",), "English": ("ingles",), "French": ("frances",),
    "Spanish": ("espanhol",), "German": ("alemao",), "Russian": ("russo",),
    "Arabic": ("arabe",), "Lingala": ("lingala",), "Creole": ("criolo", "crioulo"),
    "Other languages": ("outras",),
    "Not stated": ("naosabe",),
}
RELIGION = {
    "Catholic": ("catolica",),
    "Bom Deus Church": ("bom",),
    "Islam": ("islamica", "muculmana"),
    "Animist": ("animista",),
    "Judaism": ("judaica",),
    "Protestant": ("protestante",),
    "Universal Church of the Kingdom of God": ("universal", "reino"),
    "New Apostolic": ("nova", "apostolica"),
    "Assemblies of God (Pentecostal)": ("assembleia", "pentecostal"),
    "Tocoist": ("tocoista",),
    "Kimbanguist": ("kimbanguista",),
    "Josafat Church": ("josafat",),
    "Methodist": ("metodista",),
    "Evangelical": ("evangelica",),
    "Adventist": ("adventista",),
    "Baptist": ("baptista",),
    "Jehovah's Witnesses": ("testemunha", "jeova"),
    "Mensagem dos Últimos Tempos Church": ("mensagem", "tempos"),
    "No religion": ("semreligiao",),
    "Other religion": ("outrareligiao", "outra", "outro"),
    "Not stated": ("naosabe", "respondeu"),
}
AGE_BROAD = {"0-14": ("0-14",), "15-64": ("15-64",), "65+": ("65ou", "65-ou", "65e", "65+")}
AGE_OTHER = {"0-19": ("0-19",), "20-29": ("20-29",), "30-54": ("30-54",), "55-64": ("55-64",),
             "65-74": ("65-74",), "75+": ("75ou", "75-ou", "75e", "75+")}

# Each table: the words of its heading (squeezed, accents dropped) and its labels.
TABLES: dict[str, dict[str, Any]] = {
    "ethnicity": {"key": ("gruposetnicos", "gruposetinicos", "outribos"), "labels": ETHNIC},
    # "segundo a língua materna", and "segundo línguas materna" in Namibe's,
    # Huíla's and Cunene's reports.
    "language": {"key": ("segundoalinguamaterna", "segundolinguasmaterna",
                         "segundoaslinguasmaternas"), "labels": LANGUAGE},
    "religion": {"key": "segundoareligiaoouespiritualidade", "labels": RELIGION},
    "age_broad": {"key": "grandesgrupos", "labels": AGE_BROAD},
    "age_other": {"key": "segundooutrosgruposetarios", "labels": AGE_OTHER},
}
NOTES = {
    "ethnicity": ("The 2024 census's count of the population aged 2 and over by ethnic group "
                  "(grupos étnicos ou tribos), as it names them: Quicongo is shown as Bakongo, "
                  "Quimbundo as Ambundu, Lunda-Quioco as Lunda-Chokwe, Umbundo as Ovimbundu, "
                  "Nhaneca-Humbe as Nyaneka-Humbe, Ambó as Ovambo, Helelo as Herero, "
                  "Xindonga as Ndonga and Ovanganguela as Ngangela."),
    "language": ("The 2024 census's count of the population aged 2 and over by mother tongue "
                 "(língua materna), in the census's groups."),
    "religion": ("The 2024 census's count of the population aged 2 and over by declared "
                 "religion, the denominations kept apart as printed."),
}


def keys_of(spec: dict[str, Any]) -> tuple[str, ...]:
    key = spec["key"]
    return key if isinstance(key, tuple) else (key,)


def squeeze(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalnum() or c in "-+")


DASHES = frozenset({"-", "–", "—"})


def numeric(token: str) -> bool:
    return token.isdigit() or token in DASHES


@dataclass
class Row:
    top: float
    words: list[tuple[float, float, str]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return " ".join(t for _, _, t in self.label_words())

    def label_words(self) -> list[tuple[float, float, str]]:
        last = max((i for i, (_, _, t) in enumerate(self.words) if not numeric(t)), default=-1)
        return self.words[:last + 1]

    def figures(self) -> list[tuple[float, float, int]]:
        """Digit groups after the label, joined into figures by the gaps between them;
        a dash, which the reports print for none, is a nought."""
        last = max((i for i, (_, _, t) in enumerate(self.words) if not numeric(t)), default=-1)
        out: list[tuple[float, float, int]] = []
        run: list[tuple[float, float, str]] = []
        for x0, x1, t in self.words[last + 1:]:
            if t in DASHES:
                if run:
                    out.append((run[0][0], run[-1][1], int("".join(r[2] for r in run))))
                    run = []
                out.append((x0, x1, 0))
                continue
            if run and len(t) == 3 and x0 - run[-1][1] <= GAP:
                run.append((x0, x1, t))
                continue
            if run:
                out.append((run[0][0], run[-1][1], int("".join(r[2] for r in run))))
            run = [(x0, x1, t)]
        if run:
            out.append((run[0][0], run[-1][1], int("".join(r[2] for r in run))))
        return out

    @property
    def is_data(self) -> bool:
        return bool(re.search(r"[^\W\d_]", self.label)) and len(self.figures()) >= 2


def rows_of(words: list[dict[str, Any]] | list[tuple[float, float, float, str]]) -> list[Row]:
    """A page's words as rows: words sharing a baseline, left to right; a row of
    figures alone, printed a little lower, joins the labelled row above it."""
    cells = [(w["top"], w["x0"], w["x1"], w["text"]) if isinstance(w, dict) else w
             for w in words]
    rows: list[Row] = []
    for top, x0, x1, text in sorted(cells, key=lambda c: (round(c[0], 1), c[1])):
        if rows and abs(rows[-1].top - top) <= ROW_TOLERANCE:
            rows[-1].words.append((x0, x1, text))
        else:
            rows.append(Row(top, [(x0, x1, text)]))
    merged: list[Row] = []
    for row in rows:
        row.words.sort()
        alone = all(numeric(t) for _, _, t in row.words) and any(
            t.isdigit() for _, _, t in row.words)
        if alone and merged and row.top - merged[-1].top <= ORPHAN_REACH \
                and re.search(r"[^\W\d_]", merged[-1].label):
            merged[-1].words = sorted(merged[-1].words + row.words)
        else:
            merged.append(row)
    return merged


@dataclass
class Block:
    title: str
    header: list[Row]
    data: list[Row]
    columns: list[float] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


def blocks_of(rows: list[Row], lead: bool = False) -> list[Block]:
    """A page cut at each "Quadro" heading. Rows before the first belong to none,
    or, with ``lead``, to an untitled block: a table carried over from the page
    before (Huíla's prints its last columns on a page of their own)."""
    out: list[Block] = []
    current: Block | None = Block("", [], []) if lead else None
    if current is not None:
        out.append(current)
    for row in rows:
        if squeeze(row.label).startswith("quadro"):
            current = Block(row.label, [], [])
            out.append(current)
            continue
        if current is None:
            continue
        if row.is_data:
            current.data.append(row)
        elif not current.data:
            current.header.append(row)
    return [b for b in out if b.data]


def reach(columns: list[float]) -> float:
    gaps = [b - a for a, b in zip(columns, columns[1:])]
    return max(COLUMN_REACH, 0.45 * min(gaps)) if gaps else COLUMN_REACH


def assign_columns(block: Block) -> list[str]:
    """Columns from the row with the most figures; every figure must sit on one."""
    template = max(block.data, key=lambda r: len(r.figures()))
    block.columns = [x1 for _, x1, _ in template.figures()]
    near = reach(block.columns)
    problems = []
    for row in block.data:
        seen = set()
        for _, x1, value in row.figures():
            j = min(range(len(block.columns)), key=lambda k: abs(block.columns[k] - x1))
            if abs(block.columns[j] - x1) > near or j in seen:
                problems.append(f"{row.label}: figure {value} at {x1:.0f} fits no column")
            seen.add(j)
    return problems


def values(block: Block, row: Row) -> list[int | None]:
    out: list[int | None] = [None] * len(block.columns)
    for _, x1, value in row.figures():
        j = min(range(len(block.columns)), key=lambda k: abs(block.columns[k] - x1))
        out[j] = value
    return out


def header_texts(block: Block) -> list[str]:
    """The header words above each column, left to right."""
    cols = block.columns
    widest = max((x1 - x0 for r in block.data for x0, x1, _ in r.figures()
                  if abs(x1 - cols[0]) <= COLUMN_REACH), default=30)
    left = cols[0] - widest - 20
    texts = [""] * len(cols)
    for row in block.header:
        for x0, x1, t in row.words:
            centre = (x0 + x1) / 2
            if centre < left:
                continue
            j = next((k for k, c in enumerate(cols) if centre <= c + 8), None)
            if j is not None:
                texts[j] += " " + t
    return [t.strip() for t in texts]


def label_columns(block: Block, spec: dict[str, tuple[str, ...]]) -> list[str] | None:
    """Each column's label from the header words above it; column 0 is the total."""
    cols = block.columns
    widest = max((x1 - x0 for r in block.data for x0, x1, _ in r.figures()
                  if abs(x1 - cols[0]) <= COLUMN_REACH), default=30)
    left = cols[0] - widest - 20
    texts = [""] * len(cols)
    for row in block.header:
        for x0, x1, t in row.words:
            centre = (x0 + x1) / 2
            if centre < left:
                continue
            j = next((k for k, c in enumerate(cols) if centre <= c + 8), None)
            if j is not None:
                texts[j] += " " + t
    labels: list[str] = []
    for j, text in enumerate(texts):
        s = squeeze(text)
        hits = [lab for lab, keys in spec.items() if any(k in s for k in keys)]
        if any(k in s for k in TOTAL_KEYS) and not hits:
            labels.append("TOTAL")
        elif len(hits) == 1:
            labels.append(hits[0])
        elif j == 0 and not hits:
            labels.append("TOTAL")         # its header printed left of the column
        else:
            return None
    if len(set(labels)) != len(labels):
        return None
    return labels


# -- reading a report -------------------------------------------------------

def page_texts(blob: bytes) -> list[str]:
    from pypdf import PdfReader                      # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    out = []
    for page in reader.pages:
        try:
            out.append(squeeze(page.extract_text() or ""))
        except Exception:                            # noqa: BLE001
            out.append("")
    return out


@dataclass
class Report:
    stem: str
    province: str = ""
    total: tuple[int, int, int] | None = None              # total, men, women
    new: list[tuple[str, int, int, int]] = field(default_factory=list)
    old: list[tuple[str, int, int, int]] = field(default_factory=list)
    tables: dict[str, list[tuple[str, dict[str, int]]]] = field(default_factory=dict)
    five_year: list[tuple[int, int | None, int]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    # The 2016 table falls this many residents short of the province: only the
    # municipalities the 2024 ones make exactly are taken from it.
    short: int = 0
    # The 2016 table repeats this many 2024 municipalities of the same names and
    # leaves out the rest: it is not on the 2016 division at all.
    namesakes: int = 0


def sexes_add_up(total: int, men: int, women: int) -> bool:
    """The reports' figures are rounded from weighted counts: a total may sit a
    person or two off its men and women."""
    return abs(total - men - women) <= 2


SEX_TABLES = ("residentepormunicipiosegundoosexo", "residenteporprovinciasegundoosexo")


def split_province(rows: list[tuple[str, list[int]]], col: int
                   ) -> tuple[tuple[str, list[int]] | None, list[tuple[str, list[int]]]]:
    """The province's row, wherever the table prints it (first, last, or not at
    all: Malanje's and Huíla's tables leave it out), and the municipalities' rows."""
    for i, (label, figs) in enumerate(rows):
        others = [f for j, (_, f) in enumerate(rows) if j != i]
        if len(others) > 1 and abs(figs[col] - sum(f[col] for f in others)) <= 2 + len(others):
            return (label, figs), [r for j, r in enumerate(rows) if j != i]
    return None, rows


def read_report(stem: str, pages: list[list[Row]], texts: list[str]) -> Report:
    rep = Report(stem)
    # The 2024 municipalities by sex (three figures a row) and the 2016 ones at
    # both censuses (six), told apart by their width; the title says "por
    # município" in most reports and "por província" in some.
    old_head: list[int] | None = None
    old_rows: list[tuple[str, list[int]]] = []
    for i, text in enumerate(texts):
        if not any(k in text for k in SEX_TABLES) and "porgruposetariosquinquenais" not in text:
            continue
        for block in blocks_of(pages[i]):
            title = squeeze(block.title)
            rows = [(r.label, [v for *_, v in r.figures()]) for r in block.data]
            widths = {len(f) for _, f in rows}
            if any(k in title for k in SEX_TABLES) and widths == {3} and not rep.new:
                head, rest = split_province(rows, 0)
                rep.province = head[0] if head else ""
                rep.new = [(lab, *f) for lab, f in rest]
                rep.total = tuple(head[1]) if head else tuple(
                    sum(f[j] for _, f in rest) for j in range(3))
            elif any(k in title for k in SEX_TABLES) and widths == {6} and not old_rows:
                old_rows = rows
            elif "porgruposetariosquinquenais" in title and not rep.five_year:
                for r in block.data:
                    m = re.match(r"(\d+)\s*-\s*(\d+)\s*anos", r.label)
                    m2 = re.match(r"(\d+)\s*(?:ou|e)\s*mais", r.label)
                    f = r.figures()
                    if m and len(f) == 3:
                        rep.five_year.append((int(m.group(1)), int(m.group(2)), f[0][2]))
                    elif m2 and len(f) == 3:
                        rep.five_year.append((int(m2.group(1)), None, f[0][2]))
    summed = False
    if old_rows:
        head, rest = split_province(old_rows, 3)
        if head is None and rep.total:
            # The province's row is printed although its municipalities do not
            # make it (Cuanza Norte's, Huambo's): it is the row that carries the
            # province's total.
            at = [k for k, (_, f) in enumerate(old_rows) if abs(f[3] - rep.total[0]) <= 2]
            if len(at) == 1:
                head = old_rows[at[0]]
                rest = [r for k, r in enumerate(old_rows) if k != at[0]]
        rep.old = [(lab, f[3], f[4], f[5]) for lab, f in rest]
        summed = head is None
        old_head = head[1][3:] if head else [sum(f[j] for _, f in rest) for j in (3, 4, 5)]
    if not rep.new and rep.old and old_head:
        # The 2024 municipalities not read: the 2016 table still gives the
        # municipalities drawn their counts, and the province its total.
        rep.total = tuple(old_head)
        rep.problems.append("no table of the 2024 municipalities by sex; compositions left out")
    elif not rep.new:
        rep.problems.append("no table of the 2024 municipalities by sex")
        return rep
    # A province's total added up from its municipalities' rows (Malanje's and
    # Huíla's tables print none) carries each row's rounding.
    whole = 2 if rep.province else 2 * max(len(rep.new), 1)
    for label, t, m, f, slack in [(rep.province or "province", *rep.total, whole),
                                  *((*r, 2) for r in rep.new), *((*r, 2) for r in rep.old)]:
        if abs(t - m - f) > slack:
            rep.problems.append(f"{label}: {t:,} is not {m:,} men and {f:,} women")
    if rep.new:
        made = sum(t for _, t, *_ in rep.new)
        if abs(made - rep.total[0]) > 2 + len(rep.new):
            rep.problems.append(f"the 2024 municipalities make {made:,}, not {rep.total[0]:,}")
    if rep.old and rep.new:
        made = sum(t for _, t, *_ in rep.old)
        slack = 2 + len(rep.old)          # each row rounded from a weighted count
        same = {fold(n): t for n, t, *_ in rep.new}
        if not summed and abs(old_head[0] - rep.total[0]) > (
                2 if rep.province else 2 + len(rep.new)):
            rep.problems.append(f"the 2016 table's province is {old_head[0]:,}, not "
                                f"{rep.total[0]:,}; table left out")
            rep.old = []
        elif abs(made - rep.total[0]) > slack and made < rep.total[0] and all(
                fold(n) in same and abs(same[fold(n)] - t) <= 2 for n, t, *_ in rep.old):
            # Each row is the 2024 municipality of its name, and the
            # municipalities created in 2024 are missing: the table is not on
            # the 2016 division.
            rep.namesakes = len(rep.new) - len(rep.old)
            rep.problems.append(f"the 2016 table repeats the 2024 municipalities of the same "
                                f"names and leaves out {rep.namesakes} others; table left out")
            rep.old = []
        elif abs(made - rep.total[0]) > slack:
            rep.short = rep.total[0] - made
            rep.problems.append(f"the 2016 municipalities make {made:,}, not {rep.total[0]:,}; "
                                f"only those the 2024 municipalities make exactly are kept")
    if rep.five_year and abs(sum(n for *_, n in rep.five_year) - rep.total[0]) > max(
            5, len(rep.five_year)):
        rep.problems.append("the five-year groups do not make the province; left out")
        rep.five_year = []
    if not rep.new:
        return rep
    for name, spec in TABLES.items():
        rep.tables[name] = read_table(rep, name, spec, pages, texts)
    return rep


def read_table(rep: Report, name: str, spec: dict[str, Any], pages: list[list[Row]],
               texts: list[str]) -> list[tuple[str, dict[str, int]]]:
    """The table's rows in order, each {label: count}, its column groups joined."""
    groups: dict[tuple[str, ...], list[tuple[str, list[int | None]]]] = {}
    order: list[tuple[str, ...]] = []
    last: Block | None = None
    before = False                 # the page before held a block of this table
    for i, text in enumerate(texts):
        if not before and not any(k in text for k in keys_of(spec)):
            continue
        here = False
        for block in blocks_of(pages[i], lead=before):
            if block.title and not any(k in squeeze(block.title) for k in keys_of(spec)):
                continue
            bad = assign_columns(block)
            if bad:
                rep.problems.append(f"{name} p{i + 1}: " + "; ".join(bad[:3]))
                continue
            labels = label_columns(block, spec["labels"])
            if labels is None and name == "age_broad":
                labels = sexed_age_labels(block)
            if labels is None and last is not None and len(last.columns) == len(block.columns) \
                    and all(abs(a - b) <= 4 for a, b in zip(last.columns, block.columns)):
                labels = last.labels
            if labels is None:
                if block.title:
                    rep.problems.append(f"{name} p{i + 1}: header not read "
                                        f"({len(block.columns)} columns: "
                                        + " | ".join(t[:40] for t in header_texts(block))
                                        + ")")
                continue
            block.labels = labels
            last = block
            here = True
            key = tuple(labels)
            rows = [(r.label, values(block, r)) for r in block.data]
            if key not in groups:
                groups[key] = []
                order.append(key)
            else:
                # The same columns again: the table's rows go on, under the
                # province's rows printed again (Cunene's ethnic groups).
                seen = {(same_row(lab), tuple(v)) for lab, v in groups[key][:4]}
                while rows and (same_row(rows[0][0]), tuple(rows[0][1])) in seen:
                    rows.pop(0)
            groups[key] += rows
        before = here
    if not order:
        rep.problems.append(f"{name}: not found")
        return []
    # A column group that adds no age group or answer is the same table printed
    # another way (Cunene's broad age groups by municipality, then by sex).
    covered: set[str] = set()
    kept = []
    for key in order:
        own = {lab.split("|")[0] for lab in key} - {"TOTAL"}
        if kept and own <= covered:
            continue
        kept.append(key)
        covered |= own
    order = kept
    first = groups[order[0]]
    out: list[tuple[str, dict[str, int]]] = []

    def total_of(key: tuple[str, ...], vals: list[int | None]) -> int | None:
        return vals[key.index("TOTAL")] if "TOTAL" in key else None

    for k, (label, vals) in enumerate(first):
        row: dict[str, int] = {}
        blank: list[str] = []
        for key in order:
            rows = groups[key]
            if k >= len(rows) or not aligned(rows[k][0], label, total_of(key, rows[k][1]),
                                             total_of(order[0], vals)):
                rep.problems.append(f"{name}: column groups do not list the same rows at "
                                    f"{label!r}")
                return []
            for lab, v in zip(key, rows[k][1]):
                if v is None:
                    blank.append(lab)
                    v = 0
                if lab == "TOTAL" and "TOTAL" in row and row["TOTAL"] != v:
                    rep.problems.append(f"{name}: {label}'s totals differ between column "
                                        f"groups ({row['TOTAL']} vs {v})")
                    return []
                row[lab] = v
        if blank and any("|" in lab for lab in blank):
            rep.problems.append(f"{name}: {label} has no figure under {', '.join(blank)}")
            return []
        if not join_sexes(row):
            rep.problems.append(f"{name}: {label}'s men and women do not make its total")
            return []
        if "TOTAL" not in row:
            rep.problems.append(f"{name}: no column group carries the total")
            return []
        if blank:
            # A cell printed empty is nobody, when the row's groups still make
            # its total to the rounding of its figures; otherwise a figure was
            # lost and the table is left out.
            parts = sum(v for lab, v in row.items() if lab != "TOTAL")
            if "TOTAL" in blank or abs(parts - row["TOTAL"]) > 2 + len(row):
                rep.problems.append(f"{name}: {label} has no figure under {', '.join(blank)}")
                return []
        out.append((label, row))
    return out


# Row labels misprinted in one column group and not the other.
ROW_SPELLINGS = {"urbama": "urbana"}


def same_row(label: str) -> str:
    key = fold(label)
    return ROW_SPELLINGS.get(key, key)


def aligned(one: str, other: str, total: int | None, other_total: int | None) -> bool:
    """Two column groups' rows are the same row: the same name, one name cut
    short in one group ("Jamba" for "Jamba Mineira"), or the same total."""
    a, b = same_row(one), same_row(other)
    if a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))):
        return True
    return bool(total) and total == other_total


def sexed_age_labels(block: Block) -> list[str] | None:
    """The broad age groups printed by sex: Total, Homens, Mulheres under each of
    0-14, 15-64 and 65+ (nine columns), or Homem, Mulher alone (six)."""
    texts = [squeeze(t) for t in header_texts(block)]
    joined = "".join(texts)
    at = [joined.find(k) for k in ("14", "15-64", "65")]
    if min(at) < 0 or at != sorted(at):
        return None
    groups = ("0-14", "15-64", "65+")
    if len(texts) == 9 and all("total" in texts[j] for j in (0, 3, 6)) \
            and all("homen" in texts[j] for j in (1, 4, 7)) \
            and all("mulher" in texts[j] for j in (2, 5, 8)):
        return [lab for g in groups for lab in (g, f"{g}|m", f"{g}|f")]
    if len(texts) == 6 and all("homem" in texts[j] or "homen" in texts[j] for j in (0, 2, 4)) \
            and all("mulher" in texts[j] for j in (1, 3, 5)):
        return [lab for g in groups for lab in (f"{g}|m", f"{g}|f")]
    return None


def join_sexes(row: dict[str, int]) -> bool:
    """Men and women under a group become the group, checked against its total
    where one is printed; the groups make the row's total where none is."""
    sexed = sorted({lab.split("|")[0] for lab in row if "|" in lab})
    for group in sexed:
        men, women = row.pop(f"{group}|m", None), row.pop(f"{group}|f", None)
        if men is None or women is None:
            return False
        if group in row and abs(row[group] - men - women) > 2:
            return False
        row.setdefault(group, men + women)
    if sexed and "TOTAL" not in row:
        row["TOTAL"] = sum(v for lab, v in row.items())
    return True


def municipalities(rep: Report, name: str, rows: list[tuple[str, dict[str, int]]]
                   ) -> dict[str, dict[str, int]]:
    """The 2024 municipalities' rows of a table that may also list communes.

    The province's own rows (it, urban, rural, men, women) come first and are
    passed over. A row is a municipality's when its name is one of the report's
    municipalities not yet met and the communes since the last one have made
    that one's total; the rest are its communes. Where a municipality's
    communes do not make it (Cunene's ethnic table leaves out Cahama's own
    row), that municipality is left out and the walk picks up again at the
    next row that is a municipality's by its name and by its size against the
    municipality's residents.
    """
    names = {fold(n) for n, *_ in rep.new}
    residents = {fold(n): t for n, t, *_ in rep.new}
    lead = {"urbana", "urbama", "rural", "homens", "mulheres"}
    start = 0
    for k, (label, _) in enumerate(rows[:8]):
        if fold(label) in lead:
            start = k + 1
    if start == 0 and rows and rows[0][1].get("TOTAL") == max(v["TOTAL"] for _, v in rows):
        start = 1                                  # the province's row alone
    body = rows[start:]
    only = len(body) == len(names) and all(fold(lab) in names for lab, _ in body)
    out: dict[str, dict[str, int]] = {}
    broken: set[str] = set()
    current: str | None = None
    made = 0
    communes = 0

    def slack() -> int:
        # Each figure is rounded from a weighted count: Cabinda's Necuto is
        # 16,441 and its two communes 14,099 and 2,343.
        return 2 + communes

    def close() -> None:
        if current is not None and not only and communes \
                and abs(made - out[current]["TOTAL"]) > slack():
            rep.problems.append(f"{name}: communes of {current} make {made:,}, not "
                                f"{out[current]['TOTAL']:,}; left out")
            broken.add(current)

    for label, vals in body:
        key = fold(label)
        fresh = key in names and key not in out
        ready = current is None or only or (
            communes and abs(made - out[current]["TOTAL"]) <= slack())
        resume = fresh and not ready and plausible(name, vals["TOTAL"], residents.get(key, 0))
        if fresh and (ready or resume):
            close()
            current = key
            out[key] = dict(vals)
            made = 0
            communes = 0
        elif current is not None:
            made += vals["TOTAL"]
            communes += 1
        else:
            rep.problems.append(f"{name}: {label} before any municipality")
            return {}
    close()
    for key in broken:
        out.pop(key, None)
    if len(out) + len(broken) != len(names):
        missing = [n for n, *_ in rep.new if fold(n) not in out and fold(n) not in broken]
        rep.problems.append(f"{name}: municipalities not found: {', '.join(missing)}")
    return out


def plausible(name: str, counted: int, residents: int) -> bool:
    """A municipality's row against its residents in Quadro 10: the age tables
    count everyone, the others the population aged 2 and over (Bengo's 95%)."""
    if name.startswith("age_"):
        return abs(counted - residents) <= 2 + 0.005 * residents
    return 0.85 * residents <= counted <= residents + 2


def check_composition(field_name: str, label: str, vals: dict[str, int]) -> str | None:
    total = vals["TOTAL"]
    summed = sum(v for k, v in vals.items() if k != "TOTAL")
    if abs(summed - total) > max(0.005 * total, 5):
        return f"{field_name}: {label}'s groups make {summed:,}, not {total:,}"
    return None


# -- which new municipality is in which old one -----------------------------

def crosswalk(rep: Report, limit: int = 2_000_000) -> dict[str, str] | None:
    """New municipality (folded) -> old one (folded), the only assignment whose
    totals, men and women all add up; None when there is none or more than one."""
    old = {fold(n): (t, m, f) for n, t, m, f in rep.old}
    new = {fold(n): (t, m, f) for n, t, m, f in rep.new}
    fixed = {k: k for k in new if k in old}
    remaining = {o: list(v) for o, v in old.items()}
    for k, o in fixed.items():
        for j in range(3):
            remaining[o][j] -= new[k][j]
    free = sorted((k for k in new if k not in fixed), key=lambda k: -new[k][0])
    tolerance = 2 + len(new) // 4
    solutions: list[dict[str, str]] = []
    nodes = 0

    def go(i: int, chosen: dict[str, str]) -> None:
        nonlocal nodes
        nodes += 1
        if len(solutions) > 1 or nodes > limit:
            return
        if i == len(free):
            if all(abs(v) <= tolerance for rem in remaining.values() for v in rem):
                solutions.append(dict(chosen))
            return
        k = free[i]
        for o in remaining:
            if remaining[o][0] + tolerance < new[k][0]:
                continue
            for j in range(3):
                remaining[o][j] -= new[k][j]
            chosen[k] = o
            go(i + 1, chosen)
            del chosen[k]
            for j in range(3):
                remaining[o][j] += new[k][j]

    go(0, {})
    if nodes > limit:
        rep.problems.append("crosswalk: search too large")
        return None
    if len(solutions) != 1:
        rep.problems.append(f"crosswalk: {len(solutions)} assignments add up")
        return None
    return {**fixed, **solutions[0]}


def census_keys(name: str) -> set[str]:
    """A municipality's name as the census prints it, and its parts:
    'Cacongo(ex_Lândana)', 'Cunhinga (Vouga)', 'Catabola (ex. Nova Sintra)'."""
    keys = polygon_keys(name)
    keys |= {k[2:] for k in keys if k.startswith("ex") and len(k) > 4}
    return keys | {ALIASES[k] for k in keys if k in ALIASES}


APPROXIMATE = 0.02      # an old municipality within 2% of the new ones that make it


def crosswalk_parts(rep: Report) -> dict[str, tuple[list[str], bool]]:
    """Old municipality (folded) -> the new municipalities it is made of, and
    whether they make it exactly.

    The province's one exact assignment, when there is one. Otherwise each old
    municipality on its own: its namesake, if it has one, and the one set of up
    to five other new municipalities that makes the rest exactly, the total, the
    men and the women; a new municipality two of them claim goes to neither.
    Where the old table makes the province, the old municipalities still open
    then take the one set of the new municipalities left that comes within 2%
    of them (Benguela's and Baía Farta's 2024 municipalities differ from them by
    1,578 people), and the records say how far from exact it is.
    """
    old = {fold(n): (t, m, f) for n, t, m, f in rep.old}
    new = {fold(n): (t, m, f) for n, t, m, f in rep.new}
    names = {fold(n): n for n, *_ in rep.new}
    if not rep.short:
        walk = crosswalk(rep)
        if walk:
            got: dict[str, list[str]] = defaultdict(list)
            for n, *_ in rep.new:
                got[walk[fold(n)]].append(n)
            return {o: (got.get(o, []), True) for o in old}
    seeds: dict[str, str] = {}
    for n, *_ in rep.old:
        hits = [k for k in new if k in census_keys(n)]
        if len(hits) == 1:
            seeds[fold(n)] = hits[0]
    claimed = Counter(seeds.values())
    seeds = {o: k for o, k in seeds.items() if claimed[k] == 1}
    pool = [k for k in new if k not in seeds.values()]

    def search(o: str, among: list[str], loose: bool) -> list[tuple[str, ...]]:
        base = [seeds[o]] if o in seeds else []
        need = [old[o][j] - sum(new[b][j] for b in base) for j in range(3)]
        found: list[tuple[str, ...]] = []
        for size in range(6):
            for combo in combinations(among, size):
                slack = 2 + size + len(base)
                if all(abs(sum(new[k][j] for k in combo) - need[j])
                       <= max(slack, APPROXIMATE * old[o][j] if loose else 0)
                       for j in range(3)):
                    found.append(tuple(base) + combo)
                    if len(found) > 1:
                        return found
        return found

    def keep(found: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        count = Counter(k for ks in found.values() for k in ks)
        return {o: ks for o, ks in found.items() if all(count[k] == 1 for k in ks)}

    def settle(loose: bool, done: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        # Each round takes the old municipalities that one set alone makes,
        # then tries the rest again without the new municipalities taken:
        # Moçâmedes is Moçâmedes, Sacomar and Lucira once Iona is Tômbwa's.
        found: dict[str, tuple[str, ...]] = {}
        while True:
            used = {k for ks in (*done.values(), *found.values()) for k in ks}
            left = [k for k in pool if k not in used]
            step = keep({o: hits[0] for o in old if o not in done and o not in found
                         and len(hits := search(o, left, loose)) == 1})
            if not step:
                return found
            found.update(step)

    exact = settle(False, {})
    out = {o: ([names[k] for k in ks], True) for o, ks in exact.items()}
    if rep.short:
        return out
    near = settle(True, exact)
    out.update({o: ([names[k] for k in ks], False) for o, ks in near.items()})
    return out


# -- the map's polygons -----------------------------------------------------

def polygon_for(name: str, province: str, admin2: list[dict[str, Any]],
                provinces: dict[str, str]) -> dict[str, Any] | None:
    wanted = census_keys(name)
    here = [u for u in admin2 if provinces.get(u["parent"]) == fold(province)
            and polygon_keys(u["name"]) & wanted]
    if len(here) == 1:
        return here[0]
    if not here:
        anywhere = [u for u in admin2 if polygon_keys(u["name"]) & wanted]
        if len(anywhere) == 1:
            return anywhere[0]
    return None


# -- records ----------------------------------------------------------------

def ratio(men: int, women: int) -> int | None:
    return round(1000 * men / women) if women else None


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def unmatched(names: list[str]) -> str:
    one = len(names) == 1
    return (f"The 2024 census publishes ethnic group, mother tongue and religion only for the "
            f"municipalities created in 2024, which do not match {listed(names)} as "
            f"{'it' if one else 'they'} stood before (Lei n.º 18/16), so "
            f"{'its' if one else 'their'} own figures for these are not published.")


def median_of(parts: list[dict[str, dict[str, int]]]) -> tuple[float | None, str | None]:
    broad = defaultdict(int)
    other = defaultdict(int)
    for part in parts:
        for k, v in part["age_broad"].items():
            broad[k] += v
        for k, v in part["age_other"].items():
            other[k] += v
    if abs(broad["TOTAL"] - other["TOTAL"]) > 2:
        return None, f"age tables disagree ({broad['TOTAL']} vs {other['TOTAL']})"
    teen = other["0-19"] - broad["0-14"]
    if teen < 0:
        return None, "0-19 smaller than 0-14"
    groups = [(0, 14, broad["0-14"]), (15, 19, teen), (20, 29, other["20-29"]),
              (30, 54, other["30-54"]), (55, 64, other["55-64"]), (65, 74, other["65-74"]),
              (75, None, other["75+"])]
    if abs(sum(n for *_, n in groups) - broad["TOTAL"]) > 3:
        return None, "age groups do not make the total"
    return grouped_median(groups), None


def build(reports: list[Report], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          refused: set[tuple[str, str]] | None = None,
          apart: dict[tuple[str, str], str] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    """Records for the provinces and polygons; ``refused`` holds the (province as
    drawn, field) pairs whose provincial table disagrees with the national one,
    ``apart`` the sentence for those it differs from in one group only."""
    refused = refused or set()
    apart = apart or {}
    log_lines: list[str] = []
    provinces = {u["id"]: fold(u["name"]) for u in admin1}
    first = {fold(u["name"]): u for u in admin1}
    shapes = {u["id"]: u for u in admin2}
    cite = [{"field": "population/sex_ratio/median_age/religion/language/ethnicity",
             "name": SOURCE, "url": "https://censo2024.ine.gov.ao/", "year": YEAR,
             "license": LICENCE}]
    # A 2016 municipality, keyed (its province as drawn, folded name): its 2024
    # counts, the 2024 municipalities it is made of, and their table rows.
    old_units: dict[tuple[str, str], dict[str, Any]] = {}
    shape_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    shape_groups: dict[str, dict[tuple[int, int | None], int]] = defaultdict(
        lambda: defaultdict(int))
    shape_reports: dict[str, list[str]] = defaultdict(list)
    with_old = set()
    # Provinces as drawn whose report's table on the 2016 division only repeats
    # the 2024 municipalities of the same names: the report's province, and how
    # many municipalities of 2024 it leaves out.
    repeated: dict[str, tuple[str, int]] = {}
    for rep in reports:
        shape = REPORTS[rep.stem]
        if rep.total:
            for j in range(3):
                shape_totals[shape][j] += rep.total[j]
            shape_reports[shape].append(SHOWN.get(rep.stem, rep.stem))
            for low, high, n in rep.five_year:
                shape_groups[shape][(low, high)] += n
        if rep.namesakes:
            repeated[shape] = (SHOWN.get(rep.stem, rep.stem), rep.namesakes)
        if not rep.old:
            log_lines.append(f"  {rep.stem}: no table on the 2016 municipalities")
            for p in rep.problems:
                log_lines.append(f"  {rep.stem}: {p}")
            continue
        with_old.add(shape)
        parts = crosswalk_parts(rep)
        sizes = {fold(n): t for n, t, *_ in rep.new}
        rows = {name: municipalities(rep, name, rep.tables.get(name) or [])
                for name in TABLES}
        for name in TABLES:
            for k, vals in list(rows[name].items()):
                if not plausible(name, vals["TOTAL"], sizes.get(k, 0)):
                    rep.problems.append(f"{name}: {k}'s row counts {vals['TOTAL']:,}, against "
                                        f"{sizes.get(k, 0):,} residents; left out")
                    del rows[name][k]
        valid = set()
        for name in TABLES:
            bad = [p for k, v in rows[name].items()
                   if name in NOTES and (p := check_composition(name, k, v))]
            rep.problems += bad
            if not bad and rows[name]:
                valid.add(name)
        for n, t, m, f in rep.old:
            unit = old_units.setdefault((fold(shape), fold(n)), {
                "name": n, "counts": [0, 0, 0], "parts": [], "rows": [], "fields": set(TABLES),
                "exact": True, "resolved": True, "counted": True, "made": 0})
            for j, v in enumerate((t, m, f)):
                unit["counts"][j] += v
            got = parts.get(fold(n))
            if got is None or (rep.short and not got[1]):
                # No set of the 2024 municipalities makes it. A table that
                # does not make its province is believed only where they do.
                unit["resolved"] = False
                unit["fields"] = set()
                unit["counted"] = unit["counted"] and not rep.short
                continue
            names, exact = got
            unit["exact"] = unit["exact"] and exact
            unit["parts"] += names
            unit["made"] += sum(sizes[fold(part)] for part in names)
            unit["rows"] += [{name: rows[name].get(fold(part), {}) for name in TABLES}
                             for part in names]
            unit["fields"] &= {name for name in valid
                               if all(fold(part) in rows[name] for part in names)}
        for p in rep.problems:
            log_lines.append(f"  {rep.stem}: {p}")
        log_lines.append(f"  {rep.stem}: " + "; ".join(
            f"{o} = " + (" + ".join(parts[fold(o)][0]) + ("" if parts[fold(o)][1] else
                                                          " (within 2%)")
                         if fold(o) in parts else "?") for o, *_ in rep.old))
    records: list[dict[str, Any]] = []
    # First level: the provinces as drawn, from the reports' totals.
    have = {rep.stem for rep in reports if rep.total}
    for shape, (t, m, f) in sorted(shape_totals.items()):
        if not all(s in have for s, m2 in REPORTS.items() if m2 == shape):
            log_lines.append(f"  province {shape}: not all its reports read; no total written")
            continue
        poly = first.get(fold(shape))
        if poly is None:
            log_lines.append(f"  province {shape}: no polygon")
            continue
        fields: dict[str, Any] = {
            "population": measure(t, year=YEAR, source=SOURCE),
            "sex_ratio": measure(ratio(m, f), unit="males_per_1000_females", year=YEAR,
                                 source=SOURCE),
            "sex_ratio_note": "Men per 1,000 women among the residents the 2024 census counted.",
        }
        if len(shape_reports[shape]) > 1:
            fields["population_note"] = (
                f"The 2024 census's counts for {listed(shape_reports[shape])} provinces, "
                f"which were made out of this one in 2024, added together.")
        flat = [(lo, hi, n) for (lo, hi), n in sorted(shape_groups[shape].items(),
                                                       key=lambda kv: kv[0][0])]
        if flat and abs(sum(n for *_, n in flat) - t) <= 5 * len(shape_reports[shape]):
            med = grouped_median(flat)
            if med is not None:
                fields["median_age"] = measure(med, unit="years", year=YEAR, source=SOURCE)
                fields["median_age_note"] = ("The median of the 2024 census's counts by "
                                             "five-year age group.")
        records.append(record(f"AGO-RGPH2024-{poly['id']}", poly["name"], level="admin1",
                              parent="AGO", country="AGO", match_by="shape_id",
                              shape_id=poly["id"], sources=cite, **fields))
    # Second level: each polygon and the 2016 municipalities it is.
    on_polygon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (shape_key, key), unit in old_units.items():
        shape = next(s for s in REPORTS.values() if fold(s) == shape_key)
        poly = polygon_for(unit["name"], shape, admin2, provinces)
        if poly is None:
            log_lines.append(f"  {unit['name']} ({shape}): no polygon of its own")
            continue
        on_polygon[poly["id"]].append(unit)
    for sid, (wanted, why) in DRAWN_TOGETHER.items():
        poly = shapes.get(sid)
        if poly is None:
            continue
        units = [old_units.get((provinces.get(poly["parent"], ""), fold(n))) for n in wanted]
        on_polygon[sid] = [u for u in units if u] if all(units) else []
        if not all(units):
            log_lines.append(f"  {poly['name']}: drawn with {listed(list(wanted))}, not all "
                             f"of them read")
    stated = dict(NOT_DESCRIBED)
    for sid, units in sorted(on_polygon.items(), key=lambda kv: shapes[kv[0]]["name"]):
        poly = shapes[sid]
        if sid in NOT_DESCRIBED or not units:
            continue
        if len(units) > 1 and sid not in DRAWN_TOGETHER:
            log_lines.append(f"  {poly['name']}: {len(units)} municipalities on it; left out")
            continue
        names = [u["name"] for u in units]
        if not all(u["counted"] for u in units):
            stated[sid] = unmatched(names)
            log_lines.append(f"  {poly['name']}: its row not made by the 2024 municipalities; "
                             f"no count")
            continue
        t, m, f = (sum(u["counts"][j] for u in units) for j in range(3))
        fields = {"population": measure(t, year=YEAR, source=SOURCE),
                  "sex_ratio": measure(ratio(m, f), unit="males_per_1000_females", year=YEAR,
                                       source=SOURCE),
                  "sex_ratio_note": ("Men per 1,000 women among the residents the 2024 census "
                                     "counted.")}
        if len(units) > 1:
            fields["population_note"] = (
                "The 2024 census's counts for "
                + listed([f"{u['name']} ({u['counts'][0]:,})" for u in units])
                + ", added together. " + DRAWN_TOGETHER[sid][1])
        usable = set.intersection(*(u["fields"] for u in units)) - {
            name for shape, name in refused if fold(shape) == provinces.get(poly["parent"])}
        parts = [p for u in units for p in u["parts"]]
        rows = [r for u in units for r in u["rows"]]
        made = sum(u["made"] for u in units)
        stood = "it stood" if len(names) == 1 else "they stood"
        if not all(u["resolved"] for u in units):
            parts = []
            for name in NOTES:
                fields[name] = gap(NOT_AVAILABLE, unmatched(names))
        if all(u["exact"] for u in units):
            share = ""
        elif len(parts) == 1:
            share = (f" It holds {made:,} residents, against the {t:,} the census counts in "
                     f"{listed(names)} as {stood} under Lei n.º 18/16.")
        else:
            share = (f" Together they hold {made:,} residents, against the {t:,} the census "
                     f"counts in {listed(names)} as {stood} under Lei n.º 18/16.")
        if not parts or (len(parts) == 1 and len(units) == 1 and not share
                         and fold(parts[0]) in census_keys(names[0])):
            tail = ""
        elif len(parts) == 1:
            tail = (f" The census tabulates the municipalities of 2024; {names[0]} as it stood "
                    f"under Lei n.º 18/16 is shown by {parts[0]}'s figures." + share)
        elif share:
            tail = (f" The census tabulates the municipalities of 2024: {listed(parts)} are "
                    f"added together for {listed(names)} as {stood} under Lei n.º 18/16."
                    + share)
        else:
            tail = (f" The census tabulates the municipalities of 2024: {listed(parts)}, "
                    f"which together are {listed(names)} as {stood} under Lei n.º 18/16, "
                    f"are added together.")
        if parts:
            for name in NOTES:
                if name not in usable:
                    continue
                total = sum(r[name]["TOTAL"] for r in rows)
                counts: dict[str, int] = defaultdict(int)
                for r in rows:
                    for k, v in r[name].items():
                        if k != "TOTAL":
                            counts[k] += v
                fields[name] = shares({k: v for k, v in counts.items() if v}, total=total) \
                    or gap(NOT_AVAILABLE)
                fields[f"{name}_year"] = YEAR
                drawn_in = next((sh for sh in set(REPORTS.values())
                                 if fold(sh) == provinces.get(poly["parent"])), "")
                fields[f"{name}_note"] = NOTES[name] + tail + apart.get((drawn_in, name), "")
            if {"age_broad", "age_other"} <= usable:
                med, why = median_of(rows)
                if med is not None:
                    fields["median_age"] = measure(med, unit="years", year=YEAR, source=SOURCE)
                    fields["median_age_note"] = (
                        "Taken from the 2024 census's counts by age group (0-14, 15-19, "
                        "20-29, 30-54, 55-64, 65-74, 75 and over)"
                        + (f" for {listed(parts)}, added together." if len(parts) > 1
                           else f" for {parts[0]}." if share else ".") + share)
                else:
                    log_lines.append(f"  {poly['name']}: no median ({why})")
        records.append(record(f"AGO-RGPH2024-{sid}", poly["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=sid, sources=cite,
                              **fields))
        log_lines.append(f"  {poly['name']}: {t:,} ({' + '.join(names)}; from "
                         f"{', '.join(parts) or '-'}; {', '.join(sorted(usable)) or 'no tables'})")
    # The polygons no census figure describes say so.
    read = {rep.stem for rep in reports if rep.total}
    for shape, (shown, left_out) in sorted(repeated.items()):
        note = (f"The 2024 census publishes {shown} province's figures only for the "
                f"municipalities created in 2024; its table of the municipalities as they "
                f"stood before repeats the 2024 municipalities of the same names and leaves "
                f"out the {left_out} others, so none of its figures describes this polygon.")
        stated.update({u["id"]: note for u in admin2
                       if provinces.get(u["parent"]) == fold(shape) and u["id"] not in stated})
    for shape in sorted(NO_2016_TABLE - with_old):
        stems = [s for s, m in REPORTS.items() if m == shape]
        if not all(s in read for s in stems):
            continue                       # a report not read says nothing of the rest
        names = sorted(SHOWN.get(s, s) for s in stems)
        note = (f"The 2024 census tabulates {listed(names)} "
                f"{'province' if len(names) == 1 else 'provinces'} only by the municipalities "
                f"created in 2024, which are not the municipalities drawn here, so none of its "
                f"figures describes this polygon.")
        stated.update({u["id"]: note for u in admin2
                       if provinces.get(u["parent"]) == fold(shape) and u["id"] not in stated})
    for sid, note in sorted(stated.items()):
        poly = shapes.get(sid)
        if poly is None:
            continue
        fields = {name: gap(NOT_AVAILABLE, note) for name in NOTES}
        records.append(record(f"AGO-RGPH2024-{sid}", poly["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=sid, sources=cite,
                              **fields))
    return records, log_lines


def compare_national(reports: list[Report], national_rows: list[dict[str, Any]],
                     apart: dict[tuple[str, str], str] | None = None
                     ) -> list[tuple[str, str, str]]:
    """Each province's composition against the national report's, by group, for
    the provinces as drawn whose every report's table was read."""
    problems: list[tuple[str, str, str]] = []
    by_shape: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int)))
    complete: dict[tuple[str, str], bool] = defaultdict(lambda: True)
    expected = defaultdict(set)
    for stem, shape in REPORTS.items():
        expected[shape].add(stem)
    seen = defaultdict(set)
    for rep in reports:
        seen[REPORTS[rep.stem]].add(rep.stem)
    for rep in reports:
        shape = REPORTS[rep.stem]
        for name in NOTES:
            rows = rep.tables.get(name) or []
            if not rows:
                complete[(shape, name)] = False
                continue
            label, vals = max(rows, key=lambda r: r[1].get("TOTAL", 0))
            for k, v in vals.items():
                by_shape[shape][name][k] += v
    for row in national_rows:
        shape = row.get("name")
        if seen.get(shape) != expected.get(shape):
            continue
        for name in NOTES:
            if not complete[(shape, name)]:
                continue
            theirs = {g["group"]: g.get("count") for g in row.get(name) or []
                      if isinstance(g, dict)}
            mine = by_shape.get(shape, {}).get(name)
            if not mine or not theirs:
                continue
            # The provincial reports and the national one differ by a few per
            # cent in most groups (and Cabinda's "no religion" by a fifth), so a
            # group that departs is not itself a fault. A column read under the
            # wrong heading moves several groups at once: two or more groups of
            # some size more than a tenth off refuses the table.
            total = mine.get("TOTAL") or sum(v for k, v in mine.items() if k != "TOTAL")
            off = []
            apart_of = []
            for group, count in theirs.items():
                if count is None or group not in mine or count < 0.005 * total:
                    continue
                ratio = mine[group] / count if count else 0.0
                if abs(ratio - 1) > 0.10:
                    off.append(f"{group} {mine[group]:,} against {count:,}")
                    apart_of.append((group, (mine[group], count)))
            if len(off) > 1:
                problems.append((shape, name, f"{shape} {name}: " + "; ".join(off)))
            elif off:
                log(f"  national check: {shape} {name}: one group apart, kept: {off[0]}")
                if apart is not None:
                    group, counts = apart_of[0]
                    apart[(shape, name)] = (
                        f" The provincial report counts {counts[0]:,} people of {shape} "
                        f"province under {QUOTED.get(group, group)}, the census's "
                        f"national report {counts[1]:,}.")
    return problems


# How a group reads inside a sentence.
QUOTED = {"No religion": "no religion", "Not stated": "no answer",
          "Other religion": "another religion", "Other languages": "other languages",
          "Other": "another ethnic group"}


# Linked from the census's site as Relatorio_Provincial_<stem>_Censo2024.pdf; some
# of those links answer 404, and the reports are also published under the
# province's name alone (BENGO.pdf).
ALTERNATES = {"Uige": ("UIGE", "Uíge", "UÍGE"), "Zaire": ("ZAIRE",),
              "Cuanza_Sul": ("CUANZA_SUL", "Cuanza-Sul", "CUANZA-SUL"),
              "Cuando_Cubango": ("CUANDO", "Cuando", "CUANDO_CUBANGO")}


def fetch_report(stem: str) -> bytes:
    import urllib.parse                              # noqa: PLC0415
    tried = []
    names = (f"Relatorio_Provincial_{stem}_Censo2024", *ALTERNATES.get(stem, ()), stem.upper())
    urls = ["https://censo2024.ine.gov.ao/" + urllib.parse.quote(n) + ".pdf" for n in names]
    # The Internet Archive's copy, where the site answers 404 for a file it links.
    urls.append("https://web.archive.org/web/2026id_/" + urls[0])
    for url in urls:
        name = url.rsplit("/", 1)[-1]
        try:
            blob = http_get(url, binary=True, cache=False, timeout=600)
        except Exception as exc:                      # noqa: BLE001
            tried.append(f"{name}: {exc}")
            continue
        if blob[:4] == b"%PDF":
            return blob
        tried.append(f"{name}: not a PDF")
    raise RuntimeError("; ".join(tried))


def survey(stem: str, blob: bytes) -> None:
    """Where each table is: every "Quadro" heading on the report's pages, and for
    the tables by municipality, the first rows as pdfplumber lays them out."""
    import pdfplumber                                # noqa: PLC0415
    from pypdf import PdfReader                      # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    log(f"== {stem}: {len(reader.pages)} pages")
    keys = ("municipio", "etnic", "lingua", "religi", "etari", "2014")
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for i, page in enumerate(reader.pages):
            if i < 14:
                continue
            raw = page.extract_text() or ""
            heads = [" ".join(line.split())[:120] for line in raw.splitlines()
                     if line.strip().lower().startswith("quadro")]
            if not heads:
                continue
            log(f"  p{i + 1}: " + " || ".join(heads))
            if not any(k in squeeze(" ".join(heads)) for k in keys):
                continue
            for block in blocks_of(rows_of(pdf.pages[i].extract_words(
                    use_text_flow=False, keep_blank_chars=False))):
                widths = sorted({len(r.figures()) for r in block.data})
                labels = [r.label for r in block.data[:4]]
                log(f"      block {block.title[:70]!r}: {len(block.data)} rows, widths {widths}, "
                    f"first {labels}")


def debug(stem: str, blob: bytes, numbers: list[int]) -> None:
    """Each block on the pages given: its columns, the header above each, its rows."""
    import pdfplumber                                # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for n in numbers:
            rows = rows_of(pdf.pages[n - 1].extract_words(use_text_flow=False,
                                                          keep_blank_chars=False))
            log(f"== {stem} p{n}: {len(rows)} rows")
            for block in blocks_of(rows):
                bad = assign_columns(block)
                log(f"  block {block.title[:90]!r}")
                log(f"    columns at {[round(c) for c in block.columns]}")
                for j, t in enumerate(header_texts(block)):
                    log(f"    col {j}: {t[:120]}")
                for r in block.data[:6 if len(block.data) > 30 else 30]:
                    log(f"    row {r.label!r}: "
                        + " ".join(f"{v}@{x1:.0f}" for _, x1, v in r.figures()))
                for line in bad[:6]:
                    log(f"    misfit: {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.add_argument("--only", default="", help="report stems, comma-separated")
    parser.add_argument("--survey", action="store_true",
                        help="print where each table is, and write nothing")
    parser.add_argument("--debug", default="",
                        help="Stem:page,page;Stem:page -- print those pages' blocks, write nothing")
    args = parser.parse_args()
    import pdfplumber                                # noqa: PLC0415
    stems = [s for s in REPORTS if not args.only or s in args.only.split(",")]
    if args.debug:
        for part in args.debug.split(";"):
            stem, _, numbers = part.partition(":")
            try:
                debug(stem, fetch_report(stem), [int(n) for n in numbers.split(",") if n])
            except Exception as exc:                  # noqa: BLE001
                log(f"== {stem}: {type(exc).__name__}: {exc}")
        return 0
    if args.survey:
        for stem in stems:
            try:
                survey(stem, fetch_report(stem))
            except Exception as exc:                  # noqa: BLE001
                log(f"== {stem}: {type(exc).__name__}: {exc}")
        return 0
    reports: list[Report] = []
    failed: list[str] = []
    for stem in stems:
        try:
            blob = fetch_report(stem)
            texts = page_texts(blob)
            wanted = {i for i, t in enumerate(texts)
                      if any(k in t for k in (*SEX_TABLES, "porgruposetariosquinquenais",
                                              *(k for s in TABLES.values()
                                                for k in keys_of(s))))}
            wanted |= {i + 1 for i in wanted if i + 1 < len(texts)}
            pages: list[list[Row]] = [[] for _ in texts]
            with pdfplumber.open(io.BytesIO(blob)) as pdf:
                for i in sorted(wanted):
                    words = pdf.pages[i].extract_words(use_text_flow=False,
                                                       keep_blank_chars=False)
                    pages[i] = rows_of(words)
            rep = read_report(stem, pages, texts)
        except Exception as exc:                      # noqa: BLE001
            failed.append(stem)
            log(f"angola_municipios: {stem}: {type(exc).__name__}: {exc}")
            continue
        reports.append(rep)
        log(f"angola_municipios: {stem}: {len(blob):,} bytes, {len(texts)} pages, "
            f"{len(wanted)} read; province {rep.province!r} {rep.total}; "
            f"{len(rep.new)} municipalities of 2024, {len(rep.old)} of 2016; "
            + ", ".join(f"{k} {len(v)} rows" for k, v in rep.tables.items()))
        log("    2016: " + "; ".join(f"{n} {t:,}" for n, t, *_ in rep.old))
        log("    2024: " + "; ".join(f"{n} {t:,}" for n, t, *_ in rep.new))
    path = PROCESSED / "angola_province.json"
    national = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    apart: dict[tuple[str, str], str] = {}
    disagree = compare_national(reports, national, apart)
    for _, _, line in disagree[:80]:
        log(f"  national check: {line}")
    refused = {(shape, name) for shape, name, _ in disagree}
    for shape, name in sorted(refused):
        log(f"  {shape}: {name} left out, its provincial table not the national report's")
    admin1 = json.loads((SITE / "admin1" / "AGO.units.json").read_text(encoding="utf-8"))
    admin2 = json.loads((SITE / "admin2" / "AGO.units.json").read_text(encoding="utf-8"))
    records, lines = build(reports, admin1, admin2, refused, apart)
    for line in lines:
        log(line)
    a2 = [r for r in records if r["level"] == "admin2"]
    log(f"  {sum(r['level'] == 'admin1' for r in records)} provinces; "
        f"{sum('value' in r['population'] for r in a2)} municipality polygons with a count, "
        f"{sum(isinstance(r['ethnicity'], list) for r in a2)} with ethnic groups, "
        f"{sum('value' in r['median_age'] for r in a2)} with a median age; "
        f"{len(a2)} second-level records")
    log(f"  the provinces make {sum(r['population']['value'] for r in records if r['level'] == 'admin1'):,}")
    if failed:
        log(f"  reports not read: {', '.join(failed)}")
    if len(failed) > 4:
        raise SystemExit(f"angola_municipios: {len(failed)} reports not read")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
