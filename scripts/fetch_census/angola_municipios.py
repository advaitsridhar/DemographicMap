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
compositions say why. On those eight polygons, and on Luanda's Belas,
Cacuaco and Luanda (OTHER_GROUND), the figures published for the
municipality of the polygon's name -- projections among them -- do not
describe the polygon either, and its population, median age and sex ratio
say so, in place of any such figure.

**Ages.** Each report publishes the median age of the province and of each
2024 municipality and commune (Quadro 1.7, "Idade média e mediana"). A
province drawn as one 2024 province shows its median as published; a
polygon that is one 2024 municipality shows that municipality's. An old
municipality made of several has no published median: it is taken from the
groups 0-14, 15-64 and 65+ (Quadro 1.4) and 0-19, 20-29, 30-54, 55-64,
65-74, 75+ (Quadro 1.5) of its new municipalities, added up (0-14, 15-19,
20-29, 30-54, 55-64, 65-74, 75+), and its note says so. Luanda, Moxico and
Cuando Cubango, each two 2024 provinces, take theirs from the two
provinces' five-year groups (Quadro 1.3), added up.

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
# One province's report, as a citation names it.
SOURCE_ONE = "INE Angola, Recenseamento Geral da População e Habitação 2024, Resultados Definitivos"
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
        "of its own, so no figure published for Caluquembe, whether the 2024 census's or a "
        "projection, describes it; nor do Cacula's, which cover the rest of Cacula as well."),
    "91424787B76902935205568": (
        "About 19% of this polygon lies in the municipality of Cacula, which has no polygon "
        "of its own, so no figure published for Quilengues, whether the 2024 census's or a "
        "projection, describes it; nor do Cacula's, which cover the rest of Cacula as well."),
    "91424787B65395745560852": (
        "About 11% of this polygon, a quarter of Cacula, lies in the municipality of Cacula, "
        "which has no polygon of its own, so no figure published for Quipungo, whether the "
        "2024 census's or a projection, describes it; nor do Cacula's, which cover the rest "
        "of Cacula as well."),
    "91424787B12923410016524": (
        "About 16% of this polygon lies in the municipality of Cacula, whose seat is inside it "
        "and which has no polygon of its own, so no figure published for Lubango, whether the "
        "2024 census's or a projection, describes it; nor do Cacula's, which cover the rest of "
        "Cacula as well."),
    # The polygon and the municipality of its name, as OCHA draws it, part ways.
    "91424787B4488869677577": (
        "Only about 39% of this polygon lies in Pango Aluquém as OCHA's boundaries of the "
        "municipalities draw it, and about 48% in Cambambe, so no figure published for Pango "
        "Aluquém, whether the 2024 census's or a projection, describes it."),
    "91424787B64555741816921": (
        "Only about 53% of this polygon lies in Quiculungo as OCHA's boundaries of the "
        "municipalities draw it, and the rest in Banga and Samba Cajú, so no figure published "
        "for Quiculungo, whether the 2024 census's or a projection, describes it."),
    "91424787B22609176467527": (
        "About a third of Cambundi-Catembo, as OCHA's boundaries of the municipalities draw "
        "it, lies outside this polygon, most of it in the polygon drawn as Xá-Muteba, so no "
        "figure published for Cambundi-Catembo, whether the 2024 census's or a projection, "
        "describes it."),
    "91424787B55001564307677": (
        "About 27% of this polygon lies in Cambundi-Catembo, in Malanje, as OCHA's boundaries "
        "of the municipalities draw it, so no figure published for Xá-Muteba, whether the 2024 "
        "census's or a projection, describes it."),
}

# Luanda's polygons drawn over more than one municipality: the census tabulates
# Luanda only by the municipalities of 2024 (their compositions say so), and
# the figures published for the municipality of each one's name, projections
# among them, do not describe it either.
OTHER_GROUND: dict[str, str] = {
    "91424787B66059706224288": (
        "About 63% of this polygon lies in Belas as OCHA's boundaries of the municipalities "
        "draw it, and about 30% in Viana, which has no polygon of its own, so no figure "
        "published for Belas, whether the 2024 census's or a projection, describes it."),
    "91424787B14243133178966": (
        "Only about 40% of this polygon lies in Cacuaco as OCHA's boundaries of the "
        "municipalities draw it, about 36% in Dande, in Bengo, and about 22% in Viana, so no "
        "figure published for Cacuaco, whether the 2024 census's or a projection, describes "
        "it."),
    "91424787B55521153380221": (
        "About 55% of this polygon lies in the municipality of Luanda as OCHA's boundaries of "
        "the municipalities draw it, and most of the rest in Cazenga, which has no polygon of "
        "its own, Belas and Cacuaco, so no figure published for the municipality of Luanda, "
        "whether the 2024 census's or a projection, describes it."),
}
GROUND_FIELDS = ("population", "median_age", "sex_ratio")
# OCHA's boundaries of the municipalities, on which the polygons were measured.
OCHA_BOUNDARIES = {"name": "OCHA, Angola administrative boundaries (cod-ab-ago), the "
                           "municipalities of Lei n.º 18/16",
                   "url": "https://data.humdata.org/dataset/cod-ab-ago", "year": 2018,
                   "license": "Published via HDX"}

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
    # Zaire's, Luanda's and Cuando's broad age groups are headed "População por
    # município, por área de residência"; Bié's other groups' heading breaks
    # after "segundo outros grupos".
    "age_broad": {"key": ("grandesgrupos", "pormunicipioporareaderesidencia",
                          "porprovinciaporareaderesidencia"), "labels": AGE_BROAD},
    "age_other": {"key": ("segundooutrosgruposetarios", "segundooutrosgrupos"),
                  "labels": AGE_OTHER},
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

    def figures(self, columns: list[float] | None = None) -> list[tuple[float, float, int]]:
        """Digit groups after the label, joined into figures by the gaps between them;
        a dash, which the reports print for none, is a nought. Given the table's
        columns (their right edges), a group that ends on one column's edge is a
        figure of its own, however close the next group: a 1 under one column and
        a 340 printed a few points away under the next are not 1,340."""
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
            if run and len(t) == 3 and x0 - run[-1][1] <= GAP \
                    and not (columns and ends_column(run[-1][1], x1, columns)):
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

    @property
    def is_single(self) -> bool:
        """A labelled row with one figure that is not the page's running footer: a
        unit with one answer only (Lunda Sul's Alto Chicapa, all of whose 3,801
        people aged 2 and over are under one column of the second group). A unit's
        name runs to a few words; a longer label is a line of text."""
        said = squeeze(self.label)
        return (bool(re.search(r"[^\W\d_]", self.label)) and len(self.figures()) == 1
                and len(self.label.split()) <= 5
                and not said.startswith(("resultados", "continua", "quadro", "fonte", "nota"))
                and "rgph" not in said)


# How close a figure's right end sits to its column's right edge, in points:
# the reports right-align their figures.
EDGE = 3.0


def ends_column(prev_x1: float, next_x1: float, columns: list[float]) -> bool:
    """Whether a digit group ending at ``prev_x1`` ends a column to the left of the
    one the next group ends in: the two are figures of two columns."""
    j = min(range(len(columns)), key=lambda k: abs(columns[k] - next_x1))
    return any(abs(prev_x1 - edge) <= EDGE for edge in columns[:j])


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


def blocks_of(rows: list[Row], lead: bool = False, singles: bool = False) -> list[Block]:
    """A page cut at each "Quadro" heading. Rows before the first belong to none,
    or, with ``lead``, to an untitled block: a table carried over from the page
    before (Huíla's prints its last columns on a page of their own). With
    ``singles``, a row of one figure inside a table's body is one of its rows."""
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
        if row.is_data or (singles and current.data and row.is_single):
            current.data.append(row)
        elif not current.data:
            current.header.append(row)
    return [b for b in out if b.data]


def reach(columns: list[float]) -> float:
    gaps = [b - a for a, b in zip(columns, columns[1:])]
    return max(COLUMN_REACH, 0.45 * min(gaps)) if gaps else COLUMN_REACH


def assign_columns(block: Block) -> list[str]:
    """Columns from the row with the most figures; every figure must sit on one.
    A row of one figure that sits on no column is not one of the table's rows (a
    line of the text printed under it) and is let go."""
    template = max(block.data, key=lambda r: len(r.figures()))
    block.columns = [x1 for _, x1, _ in template.figures()]
    near = reach(block.columns)
    problems = []
    kept = []
    for row in block.data:
        seen = set()
        misfits = []
        for _, x1, value in row.figures(block.columns):
            j = min(range(len(block.columns)), key=lambda k: abs(block.columns[k] - x1))
            if abs(block.columns[j] - x1) > near or j in seen:
                misfits.append(f"{row.label}: figure {value} at {x1:.0f} fits no column")
            seen.add(j)
        if misfits and row.is_single:
            continue
        problems += misfits
        kept.append(row)
    block.data = kept
    return problems


def values(block: Block, row: Row) -> list[int | None]:
    out: list[int | None] = [None] * len(block.columns)
    for _, x1, value in row.figures(block.columns):
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
    url: str = ""
    # Each table read -> its number in the report ("11", "1.7", "6.1").
    quadros: dict[str, str] = field(default_factory=dict)
    # Quadro 1.7: the province's median age, and each 2024 municipality's
    # (folded name -> median; None where the row is printed without figures).
    median: float | None = None
    medians: dict[str, float | None] = field(default_factory=dict)
    # Rows put together from their communes: table -> municipality (folded) ->
    # (how, the row as printed, the count taken).
    patched: dict[str, dict[str, tuple[str, int, int]]] = field(
        default_factory=lambda: defaultdict(dict))
    # Rows left out: table -> municipality (folded) -> why, for the notes.
    refusals: dict[str, dict[str, tuple[Any, ...]]] = field(
        default_factory=lambda: defaultdict(dict))
    # 2016 municipality (folded) -> the sets of 2024 ones that come within 2%
    # of it, where none or more than one does: [(names, total)].
    candidates: dict[str, list[tuple[list[str], int]]] = field(default_factory=dict)


def quadro_of(title: str) -> str:
    """The table's number from its heading: "Quadro 1. 7- Idade ..." -> "1.7"."""
    m = re.match(r"\s*Quadro\s*(\d[\d.\s]*?)\s*[-–—:]", title or "")
    return re.sub(r"\s+", "", m.group(1)).rstrip(".") if m else ""


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
                rep.quadros["new"] = quadro_of(block.title)
            elif any(k in title for k in SEX_TABLES) and widths == {6} and not old_rows:
                old_rows = rows
                rep.quadros["old"] = quadro_of(block.title)
            elif "porgruposetariosquinquenais" in title and not rep.five_year:
                rep.quadros["five_year"] = quadro_of(block.title)
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
    medians_of(rep, pages, texts)
    if not rep.new:
        return rep
    for name, spec in TABLES.items():
        rep.tables[name] = read_table(rep, name, spec, pages, texts)
    return rep


# Quadro 1.7, "Idade média e mediana da população": the median age of the
# province, its municipalities and their communes, printed as "18,0".
MEDIAN_KEY = "idademediaemediana"
# The words that put a page among those laid out for it: a text layer may break
# the heading's words apart.
MEDIAN_PAGES = (MEDIAN_KEY, "mediana", "idademedia")
DECIMAL = re.compile(r"^\d{1,3},\d{1,2}$")


def words_of(row: Row) -> str:
    return " ".join(t for _, _, t in row.words)


def median_entries(rows: list[Row]) -> tuple[str, list[tuple[str, float | None]]]:
    """Quadro 1.7's heading and rows in reading order, each (label, median); a
    row printed without figures (a heading, or one of Benguela's municipalities
    of several communes) has None.

    The table is printed in one column group or in two side by side (Malanje's,
    Bié's, Huíla's). The figures' right ends gather in two columns a group,
    média and mediana; a word that starts right of a group's mediana column
    belongs to a later group, which is read after it."""
    at = next((k for k, r in enumerate(rows) if MEDIAN_KEY in squeeze(words_of(r))), None)
    if at is None:
        return "", []
    end = next((k for k in range(at + 1, len(rows))
                if squeeze(words_of(rows[k])).startswith("quadro")), len(rows))
    body = rows[at + 1:end]
    clusters = decimal_columns(body)
    if not clusters or len(clusters) % 2 or len(clusters) > 6:
        return words_of(rows[at]), []
    bounds = [max(clusters[k]) + 1 for k in range(1, len(clusters) - 1, 2)]
    groups: list[list[tuple[str, float | None]]] = [[] for _ in range(len(bounds) + 1)]
    for row in body:
        parts: list[list[str]] = [[] for _ in groups]
        for x0, _, t in row.words:
            parts[sum(x0 > b for b in bounds)].append(t)
        for g, words in enumerate(parts):
            figures = [w for w in words if DECIMAL.match(w)]
            label = " ".join(w for w in words if not DECIMAL.match(w))
            if len(figures) == 2:
                groups[g].append((label, float(figures[1].replace(",", "."))))
            elif not figures and label:
                groups[g].append((label, None))
    return words_of(rows[at]), [e for g in groups for e in g]


def decimal_columns(rows: list[Row]) -> list[list[float]]:
    """The right ends of the figures printed as "18,0", gathered into columns."""
    ends = sorted(x1 for r in rows for _, x1, t in r.words if DECIMAL.match(t))
    clusters: list[list[float]] = []
    for x1 in ends:
        if clusters and x1 - clusters[-1][-1] <= 12:
            clusters[-1].append(x1)
        else:
            clusters.append([x1])
    return clusters


def medians_of(rep: Report, pages: list[list[Row]], texts: list[str]) -> None:
    """The province's median age and each 2024 municipality's, from Quadro 1.7.

    The province's row is the first with figures. The municipalities follow a
    heading ("Municípios", "Município / Comuna"), each before its communes and
    in the order of Quadro 10: each is the first row of its name after the one
    before it, so a commune of the same name, printed after it, is passed over."""
    # Every page laid out, not only those whose text layer names the table.
    for i in range(len(pages)):
        if not pages[i]:
            continue
        title, entries = median_entries(pages[i])
        first = next((k for k, (_, m) in enumerate(entries) if m is not None), None)
        if first is None:
            continue
        start = next((k for k in range(first + 1, len(entries)) if entries[k][1] is None
                      and squeeze(entries[k][0]).startswith("munic")), None)
        if start is None:
            start = next((k for k in range(first + 1, len(entries))
                          if squeeze(entries[k][0]) == "mulheres"), None)
        if start is None:
            continue
        rep.median = entries[first][1]
        rep.quadros["medians"] = quadro_of(title)
        used: set[int] = set()
        pos = start + 1
        for name, *_ in rep.new:
            key = fold(name)
            hit = next((k for k in range(pos, len(entries)) if fold(entries[k][0]) == key), None)
            if hit is None:
                # Printed out of Quadro 10's order: the first row of its name not taken.
                hit = next((k for k in range(start + 1, len(entries))
                            if k not in used and fold(entries[k][0]) == key), None)
            if hit is None:
                continue
            used.add(hit)
            rep.medians[key] = entries[hit][1]
            pos = max(pos, hit + 1)
        missing = [n for n, *_ in rep.new if fold(n) not in rep.medians]
        if missing:
            rep.problems.append(f"median ages: no row for {', '.join(missing)}")
        return
    rep.problems.append("median ages: Quadro 1.7 not read")


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
        for block in blocks_of(pages[i], lead=before, singles=True):
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
            # A row of one figure is a unit all of whose people are under the
            # columns of another group, which prints only its total here (Lunda
            # Sul's Alto Chicapa); one whose figure is not under the total is a
            # heading or a line of text, not a row of the table.
            at = labels.index("TOTAL") if "TOTAL" in labels else None
            block.data = [r for r in block.data
                          if not r.is_single or (at is not None and values(block, r)[at] is not None)]
            if block.title:
                rep.quadros.setdefault(name, quadro_of(block.title))
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
    communes do not make it, that municipality is left out and the walk picks
    up again at the next row that is a municipality's by its name and by its
    size against the municipality's residents.

    A municipality's row that its residents rule out is not its count:
    Cunene's mother tongues give Cafima 25,194 people aged 2 and over against
    19,163 residents, and Malanje's give Kunda dya Baze 494,052 against 14,843.
    Its communes' rows are added up in its place when they come to a count its
    residents allow; and where they do so only with that row itself, the row is
    its namesake commune's and the municipality's own was not printed
    (Cunene's ethnic groups list Cahama's two communes and no row for Cahama).
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
    met: set[str] = set()
    current: str | None = None
    own: dict[str, int] = {}
    summed: dict[str, int] = defaultdict(int)
    communes = 0
    placeholder = False

    def slack() -> int:
        # Each figure is rounded from a weighted count: Cabinda's Necuto is
        # 16,441 and its two communes 14,099 and 2,343.
        return 2 + communes

    def fits(key: str, vals: dict[str, int]) -> bool:
        return plausible(name, vals.get("TOTAL", 0), residents.get(key, 0))

    def close() -> None:
        if current is None:
            return
        if placeholder:
            alone = dict(summed)
            joined = {k: own.get(k, 0) + summed.get(k, 0) for k in set(own) | set(summed)}
            if communes and fits(current, alone):
                out[current] = alone
                rep.patched[name][current] = ("communes", own["TOTAL"], alone["TOTAL"])
            elif communes and fits(current, joined):
                out[current] = joined
                rep.patched[name][current] = ("namesake", own["TOTAL"], joined["TOTAL"])
            else:
                rep.problems.append(f"{name}: {current}'s row counts {own['TOTAL']:,} against "
                                    f"{residents.get(current, 0):,} residents, and its communes "
                                    f"do not make up for it; left out")
                rep.refusals[name][current] = ("plausible", own["TOTAL"],
                                               residents.get(current, 0))
                broken.add(current)
            return
        out[current] = own
        if not only and communes and abs(summed["TOTAL"] - own["TOTAL"]) > slack():
            rep.problems.append(f"{name}: communes of {current} make {summed['TOTAL']:,}, not "
                                f"{own['TOTAL']:,}; left out")
            rep.refusals[name][current] = ("communes", summed["TOTAL"], own["TOTAL"])
            broken.add(current)

    for label, vals in body:
        key = fold(label)
        fresh = key in names and key not in met
        made_up = bool(communes) and abs(summed["TOTAL"] - own["TOTAL"]) <= slack()
        if current is None or only:
            ready = True
        elif placeholder:
            # A row its residents rule out ends at the next municipality whose
            # row they allow, or at the next one at all once its communes make
            # it (Benguela's Baía Farta and Caimbambo trade 12,634 people
            # between their rows and their communes alike).
            ready = fresh and (fits(key, vals) or made_up)
        else:
            ready = made_up
        resume = fresh and not ready and fits(key, vals)
        if fresh and (ready or resume):
            close()
            current = key
            met.add(key)
            own = dict(vals)
            summed = defaultdict(int)
            communes = 0
            placeholder = not only and not fits(key, vals)
        elif current is not None:
            for k, v in vals.items():
                summed[k] += v
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
        for n in missing:
            rep.refusals[name].setdefault(fold(n), ("missing",))
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
    # For the notes: the sets that come within 2% of each municipality left
    # open, among the 2024 municipalities no other has taken (none, or two).
    taken = {k for ks in (*exact.values(), *near.values()) for k in ks}
    left = [k for k in pool if k not in taken]
    for o in old:
        if o not in out:
            rep.candidates[o] = [([names[k] for k in ks], sum(new[k][0] for k in ks))
                                 for ks in search(o, left, True)]
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


def shown_name(name: str) -> str:
    """A municipality's name as a note shows it: the census's "Cacongo(ex_Lândana)"
    and "Catabola (ex. Nova Sintra)" as "Cacongo (ex-Lândana)" and "Catabola
    (ex-Nova Sintra)"."""
    text = re.sub(r"\s*\(\s*ex[\s._-]*", " (ex-", name)
    return re.sub(r"\s+", " ", text).strip()


# What each table counts, inside a sentence, and the figures its field shows.
WHAT = {"ethnicity": "ethnic groups", "language": "mother tongues", "religion": "religions",
        "age_broad": "broad age groups", "age_other": "age groups"}
FIGURES = {"ethnicity": "ethnic group", "language": "mother tongue", "religion": "religion"}
FIELD_ORDER = ("population", "sex_ratio", "median_age", "ethnicity", "language", "religion")
AGE_GROUPS = "(0-14, 15-19, 20-29, 30-54, 55-64, 65-74, 75 and over)"


def cite(reps: list[Report], given: list[str], noted: list[str], quadros: list[str]
         ) -> list[dict[str, Any]]:
    """One citation for each report: the fields the record gives, those it only
    explains (as "<field> note"), the report's own address and its tables. A
    province's population and sex ratio come from Quadro 10, or from the table
    on the 2016 division where Quadro 10 was not printed ("total")."""
    fields = [f for f in FIELD_ORDER if f in given] + [
        f"{f} note" for f in FIELD_ORDER if f in noted and f not in given]
    out = []
    for rep in reps:
        keys = [("new" if rep.new else "old") if q == "total" else q for q in quadros]
        numbers = list(dict.fromkeys(rep.quadros[q] for q in keys if rep.quadros.get(q)))
        tables = (f": Quadro {numbers[0]}" if len(numbers) == 1 else
                  f": Quadros {listed(numbers)}" if numbers else "")
        out.append({"field": "/".join(fields),
                    "name": f"{SOURCE_ONE}, {SHOWN.get(rep.stem, rep.stem)} province report"
                            f"{tables}",
                    "url": rep.url or URL.format(stem=rep.stem), "year": YEAR,
                    "license": LICENCE})
    return out


def unmatched(name: str, residents: int, sets: list[tuple[list[str], int]]) -> str:
    """Why a municipality as it stood under Lei n.º 18/16 has no ethnic group,
    mother tongue or religion: the municipalities of 2024 do not make it in one
    way only. ``sets`` are those that come within 2% of it."""
    unit = f"{name} as it stood under Lei n.º 18/16 ({residents:,} residents)"
    if len(sets) > 1:
        (a, sa), (b, sb) = sets[:2]
        found = (f"more than one set of them comes within 2% of {unit} in its residents, "
                 f"its men and its women: {listed(a)} {'makes' if len(a) == 1 else 'make'} "
                 f"{sa:,}, and {listed(b)} {sb:,}")
    elif sets:
        (a, sa), = sets
        found = (f"{listed(a)} {'makes' if len(a) == 1 else 'make'} {sa:,}, within 2% of "
                 f"{unit}, but the province's other municipalities as they stood need some "
                 f"of the same ones")
    else:
        found = (f"no set of them comes within 2% of {unit} in its residents, its men and "
                 f"its women alike")
    return ("The 2024 census publishes ethnic group, mother tongue and religion only for the "
            f"municipalities created in 2024, and {found}, so it cannot be matched to one set "
            "of them, and its own figures for these are not shown.")


def short_note(rep: Report, name: str) -> str:
    """Why a municipality of a province whose table on the 2016 division falls
    short of the province (Huíla's) has no figure: no set of the 2024
    municipalities makes its row exactly."""
    total = rep.total[0] if rep.total else 0
    return (f"The 2024 census's table of {SHOWN.get(rep.stem, rep.stem)} province's "
            f"municipalities as they stood under Lei n.º 18/16 adds up to "
            f"{total - rep.short:,} residents, {rep.short:,} short of the province's "
            f"{total:,}, so only the rows that municipalities created in 2024 make exactly "
            f"are taken, and none makes {name}'s; its figures are not shown.")


def reason_note(rep: Report, table: str, part: str, reason: tuple[Any, ...],
                names: list[str], stood: str) -> str:
    """Why a table's figures are not shown for a polygon: what the table prints
    for one of the 2024 municipalities it is made of."""
    where = (f"In the 2024 census's table of {WHAT[table]} for "
             f"{SHOWN.get(rep.stem, rep.stem)} province, ")
    tail = (f", so the {FIGURES.get(table, 'age')} figures for {listed(names)} as {stood} "
            f"under Lei n.º 18/16 are not shown.")
    kind = reason[0]
    if kind == "plausible":
        return (where + f"{part}'s row counts {reason[1]:,} people, against the "
                f"{reason[2]:,} residents the census counts there, and its communes' rows "
                f"do not make up for it" + tail)
    if kind == "communes":
        return (where + f"the communes of {part} add up to {reason[1]:,} people, not the "
                f"{reason[2]:,} printed for it" + tail)
    if kind == "sums":
        return (where + f"the groups of {part}'s row add up to {reason[1]:,}, not the "
                f"{reason[2]:,} printed as its total" + tail)
    if kind == "table":
        return (where + f"the groups of {reason[1]} of its {reason[2]} municipalities' rows "
                f"do not add up to their totals" + tail)
    return where + f"no row can be told apart as {part}'s" + tail


def patched_note(rep: Report, tables: tuple[str, ...], keys: list[str],
                 labels: dict[str, str], sizes: dict[str, int],
                 where: str = "that table") -> str:
    """What was done with a 2024 municipality's row its residents rule out."""
    out = []
    for table in tables:
        for k in keys:
            got = rep.patched.get(table, {}).get(k)
            if not got:
                continue
            how, printed, used = got
            part = labels.get(k, k)
            if how == "communes":
                out.append(f" {part}'s own row in {where} counts {printed:,} people, against "
                           f"its {sizes.get(k, 0):,} residents; its communes' rows, which add "
                           f"up to {used:,}, are taken in its place.")
            else:
                out.append(f" {where[0].upper() + where[1:]} prints no row for the "
                           f"municipality of {part}, only for its communes, which are added "
                           f"up ({used:,} people).")
    return "".join(dict.fromkeys(out))


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
          apart: dict[tuple[str, str], str] | None = None,
          national: dict[tuple[str, str], str] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    """Records for the provinces and polygons; ``refused`` holds the (province as
    drawn, field) pairs whose provincial table disagrees with the national one,
    ``national`` the sentence that says how, and ``apart`` the sentence for
    those it differs from in one group only."""
    refused = refused or set()
    apart = apart or {}
    national = national or {}
    log_lines: list[str] = []
    provinces = {u["id"]: fold(u["name"]) for u in admin1}
    first = {fold(u["name"]): u for u in admin1}
    shapes = {u["id"]: u for u in admin2}
    # A 2016 municipality, keyed (its province as drawn, folded name): its 2024
    # counts, the 2024 municipalities it is made of, and their table rows.
    old_units: dict[tuple[str, str], dict[str, Any]] = {}
    shape_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    shape_groups: dict[str, dict[tuple[int, int | None], int]] = defaultdict(
        lambda: defaultdict(int))
    shape_reps: dict[str, list[Report]] = defaultdict(list)
    with_old = set()
    # Provinces as drawn whose report's table on the 2016 division only repeats
    # the 2024 municipalities of the same names: the report, and how many
    # municipalities of 2024 it leaves out.
    repeated: dict[str, tuple[Report, int]] = {}
    for rep in reports:
        shape = REPORTS[rep.stem]
        if rep.total:
            for j in range(3):
                shape_totals[shape][j] += rep.total[j]
            shape_reps[shape].append(rep)
            for low, high, n in rep.five_year:
                shape_groups[shape][(low, high)] += n
        if rep.namesakes:
            repeated[shape] = (rep, rep.namesakes)
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
                    rep.refusals[name][k] = ("plausible", vals["TOTAL"], sizes.get(k, 0))
                    del rows[name][k]
        valid = set()
        for name in TABLES:
            if name not in NOTES:
                if rows[name]:
                    valid.add(name)
                continue
            # A row whose groups do not make its total is left out; when more
            # than a third of them do not, the columns were not read right and
            # the table is.
            bad = {k: p for k, v in rows[name].items()
                   if (p := check_composition(name, k, v))}
            rep.problems += list(bad.values())
            if bad and 3 * len(bad) > len(rows[name]):
                for k in rows[name]:
                    rep.refusals[name].setdefault(k, ("table", len(bad), len(rows[name])))
                rows[name] = {}
                continue
            for k in bad:
                v = rows[name].pop(k)
                rep.refusals[name][k] = ("sums", sum(x for g, x in v.items() if g != "TOTAL"),
                                         v["TOTAL"])
            if rows[name]:
                valid.add(name)
        for n, t, m, f in rep.old:
            unit = old_units.setdefault((fold(shape), fold(n)), {
                "name": shown_name(n), "key": fold(n), "rep": rep, "counts": [0, 0, 0],
                "parts": [], "keys": [], "rows": [], "fields": set(TABLES), "exact": True,
                "resolved": True, "counted": True, "made": 0})
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
            unit["keys"] += [fold(part) for part in names]
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
                         if fold(o) in parts else
                         "? " + " | ".join(f"{' + '.join(a)} {s:,}"
                                           for a, s in rep.candidates.get(fold(o), [])))
            for o, *_ in rep.old))
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
        reps = shape_reps[shape]
        given = ["population", "sex_ratio"]
        quadros = ["total"]
        fields: dict[str, Any] = {
            "population": measure(t, year=YEAR, source=SOURCE),
            "sex_ratio": measure(ratio(m, f), unit="males_per_1000_females", year=YEAR,
                                 source=SOURCE),
            "sex_ratio_note": "Men per 1,000 women among the residents the 2024 census counted.",
        }
        shown = [SHOWN.get(r.stem, r.stem) for r in reps]
        if len(reps) > 1:
            fields["population_note"] = (
                f"The 2024 census's counts for {listed(shown)} provinces, which were made out "
                f"of this one in 2024, added together.")
        if len(reps) == 1 and reps[0].median is not None:
            fields["median_age"] = measure(reps[0].median, unit="years", year=YEAR,
                                           source=SOURCE)
            fields["median_age_note"] = "The median age the 2024 census publishes for the province."
            given.append("median_age")
            quadros.append("medians")
        else:
            flat = [(lo, hi, n) for (lo, hi), n in sorted(shape_groups[shape].items(),
                                                           key=lambda kv: kv[0][0])]
            med = (grouped_median(flat) if flat and abs(sum(n for *_, n in flat) - t)
                   <= 5 * len(reps) else None)
            if med is not None:
                fields["median_age"] = measure(med, unit="years", year=YEAR, source=SOURCE)
                if len(reps) > 1:
                    note = ("The median of the 2024 census's counts by five-year age group for "
                            f"{listed(shown)} provinces, added together")
                    if all(r.median is not None for r in reps):
                        note += ("; the census publishes "
                                 + listed([f"{r.median:g} years for {s}"
                                           for r, s in zip(reps, shown)])
                                 + ", not a median for the two together.")
                        quadros.append("medians")
                    else:
                        note += "."
                else:
                    note = "The median of the 2024 census's counts by five-year age group."
                    log_lines.append(f"  province {shape}: Quadro 1.7 not read; median from "
                                     f"the five-year groups")
                fields["median_age_note"] = note
                given.append("median_age")
                quadros.append("five_year")
        records.append(record(f"AGO-RGPH2024-{poly['id']}", poly["name"], level="admin1",
                              parent="AGO", country="AGO", match_by="shape_id",
                              shape_id=poly["id"], sources=cite(reps, given, [], quadros),
                              **fields))
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
    # Polygons no census figure describes: the note, the reports that say so,
    # and their tables.
    stated: dict[str, tuple[str, list[Report], list[str]]] = {
        sid: (note, [], []) for sid, note in NOT_DESCRIBED.items()}
    for sid, units in sorted(on_polygon.items(), key=lambda kv: shapes[kv[0]]["name"]):
        poly = shapes[sid]
        if sid in NOT_DESCRIBED or not units:
            continue
        if len(units) > 1 and sid not in DRAWN_TOGETHER:
            log_lines.append(f"  {poly['name']}: {len(units)} municipalities on it; left out")
            continue
        rep = units[0]["rep"]
        drawn_in = REPORTS[rep.stem]
        names = [u["name"] for u in units]
        stood = "it stood" if len(names) == 1 else "they stood"
        sizes = {fold(n): t for n, t, *_ in rep.new}
        labels = {fold(n): n for n, *_ in rep.new}
        if not all(u["counted"] for u in units):
            short = next(u for u in units if not u["counted"])
            stated[sid] = (short_note(rep, short["name"]), [rep], ["old"])
            log_lines.append(f"  {poly['name']}: its row not made by the 2024 municipalities; "
                             f"no count")
            continue
        t, m, f = (sum(u["counts"][j] for u in units) for j in range(3))
        given = ["population", "sex_ratio"]
        noted: list[str] = []
        quadros = ["old"]
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
            name for shape, name in refused if fold(shape) == fold(drawn_in)}
        parts = [p for u in units for p in u["parts"]]
        keys = [k for u in units for k in u["keys"]]
        rows = [r for u in units for r in u["rows"]]
        made = sum(u["made"] for u in units)
        if not all(u["resolved"] for u in units):
            open_unit = next(u for u in units if not u["resolved"])
            note = unmatched(open_unit["name"], open_unit["counts"][0],
                             rep.candidates.get(open_unit["key"], []))
            parts, keys, rows = [], [], []
            for name in NOTES:
                fields[name] = gap(NOT_AVAILABLE, note)
                noted.append(name)
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
                    fields[name] = gap(NOT_AVAILABLE, why_not(
                        rep, name, keys, labels, names, stood, drawn_in, refused, national))
                    noted.append(name)
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
                fields[f"{name}_note"] = (NOTES[name] + tail
                                          + patched_note(rep, (name,), keys, labels, sizes)
                                          + apart.get((drawn_in, name), ""))
                given.append(name)
                quadros.append(name)
            median_fields(rep, units, parts, keys, rows, names, stood, share, tail, usable,
                          labels, sizes, fields, given, quadros, log_lines, poly["name"])
        records.append(record(f"AGO-RGPH2024-{sid}", poly["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=sid,
                              sources=cite([rep], given, noted, quadros), **fields))
        log_lines.append(f"  {poly['name']}: {t:,} ({' + '.join(names)}; from "
                         f"{', '.join(parts) or '-'}; {', '.join(sorted(usable)) or 'no tables'}"
                         f"; median {fields.get('median_age', {}).get('value', '-')}"
                         f"; not shown: {', '.join(n for n in NOTES if n in noted) or '-'})")
    # The polygons no census figure describes say so.
    read = {rep.stem for rep in reports if rep.total}
    for shape, (rep, left_out) in sorted(repeated.items()):
        note = (f"The 2024 census publishes {SHOWN.get(rep.stem, rep.stem)} province's figures "
                f"only for the municipalities created in 2024; its table of the municipalities "
                f"as they stood before repeats the 2024 municipalities of the same names and "
                f"leaves out the {left_out} others, so none of its figures describes this "
                f"polygon.")
        stated.update({u["id"]: (note, [rep], ["old"]) for u in admin2
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
        stated.update({u["id"]: (note, shape_reps[shape], ["new"]) for u in admin2
                       if provinces.get(u["parent"]) == fold(shape) and u["id"] not in stated})
    for sid in sorted(set(stated) | set(OTHER_GROUND)):
        poly = shapes.get(sid)
        if poly is None:
            continue
        fields = {}
        sources: list[dict[str, Any]] = []
        if sid in stated:
            note, reps, quadros = stated[sid]
            fields.update({name: gap(NOT_AVAILABLE, note) for name in NOTES})
            sources += cite(reps, [], list(NOTES), quadros)
        ground = NOT_DESCRIBED.get(sid) or OTHER_GROUND.get(sid)
        if ground:
            # The figures published for the municipality of its name, the
            # projections among them, do not describe it either.
            for name in GROUND_FIELDS:
                fields[name] = {**gap(NOT_AVAILABLE, ground), "displaces_before": YEAR + 1,
                                "displaces_undated": True}
            explained = [*GROUND_FIELDS, *(NOTES if sid in NOT_DESCRIBED else ())]
            sources.append({**OCHA_BOUNDARIES, "field": "/".join(
                f"{f} note" for f in FIELD_ORDER if f in explained)})
        records.append(record(f"AGO-RGPH2024-{sid}", poly["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=sid,
                              sources=sources, **fields))
    return records, log_lines


def why_not(rep: Report, name: str, keys: list[str], labels: dict[str, str],
            names: list[str], stood: str, drawn_in: str, refused: set[tuple[str, str]],
            national: dict[tuple[str, str], str]) -> str:
    """The sentence for a composition the census prints but that is not shown."""
    if (drawn_in, name) in refused:
        return national.get((drawn_in, name)) or (
            f"The 2024 census's provincial report for {drawn_in} and its national report give "
            f"the province different {FIGURES[name]} figures, so the municipalities' are not "
            f"shown.")
    for k in keys:
        reason = rep.refusals.get(name, {}).get(k)
        if reason:
            return reason_note(rep, name, labels.get(k, k), reason, names, stood)
    return reason_note(rep, name, labels.get(keys[0], keys[0]) if keys else listed(names),
                       ("missing",), names, stood)


def median_fields(rep: Report, units: list[dict[str, Any]], parts: list[str], keys: list[str],
                  rows: list[dict[str, dict[str, int]]], names: list[str], stood: str,
                  share: str, tail: str, usable: set[str], labels: dict[str, str],
                  sizes: dict[str, int], fields: dict[str, Any], given: list[str],
                  quadros: list[str], log_lines: list[str], polygon: str) -> None:
    """A polygon's median age: the census's own (Quadro 1.7) where it is one
    municipality of 2024; otherwise taken from its municipalities' counts by age
    group, added together, and the note says so."""
    single = len(parts) == 1 and len(units) == 1
    published = [rep.medians.get(k) for k in keys]
    if single and published[0] is not None:
        fields["median_age"] = measure(published[0], unit="years", year=YEAR, source=SOURCE)
        fields["median_age_note"] = (f"The median age the 2024 census publishes for "
                                     f"{parts[0]}." + (tail or share))
        given.append("median_age")
        quadros.append("medians")
        return
    if not {"age_broad", "age_other"} <= usable:
        return
    med, why = median_of(rows)
    if med is None:
        log_lines.append(f"  {polygon}: no median ({why})")
        return
    if single and keys[0] in rep.medians:
        note = (f"The census prints no median age for {parts[0]} as a whole, only for its "
                f"communes; this one is taken from its counts by age group {AGE_GROUPS}.")
    elif single:
        note = f"Taken from the 2024 census's counts by age group {AGE_GROUPS}."
        log_lines.append(f"  {polygon}: no row of {parts[0]} in Quadro 1.7; median from its "
                         f"age groups")
    elif all(p is not None for p in published):
        note = ("The census publishes a median age for each municipality created in 2024 ("
                + listed([f"{p} {m:g}" for p, m in zip(parts, published)])
                + f" years), not for {listed(names)} as {stood} under Lei n.º 18/16; this one "
                f"is taken from their counts by age group {AGE_GROUPS}, added together.")
        quadros.append("medians")
    else:
        note = (f"Taken from the 2024 census's counts by age group {AGE_GROUPS} for "
                f"{listed(parts)}, added together; the census publishes no median age for "
                f"{listed(names)} as {stood} under Lei n.º 18/16.")
    fields["median_age"] = measure(med, unit="years", year=YEAR, source=SOURCE)
    fields["median_age_note"] = note + share + patched_note(
        rep, ("age_broad", "age_other"), keys, labels, sizes, where="the tables of age groups")
    given.append("median_age")
    quadros += ["age_broad", "age_other"]


def national_note(shape: str, name: str, off: list[tuple[str, int, int]]) -> str:
    """The sentence for a province whose provincial and national reports count a
    composition's groups differently: the largest difference, and the next."""
    (g, a, b), *rest = sorted(off, key=lambda o: -abs(o[1] - o[2]))
    extra = ""
    if rest:
        g2, c, d = rest[0]
        more = ", and other groups apart" if len(rest) > 1 else ""
        extra = f" (and {c:,} against {d:,} under {QUOTED.get(g2, g2)}{more})"
    return (f"The 2024 census's provincial report for {shape} counts {a:,} people under "
            f"{QUOTED.get(g, g)} where its national report counts {b:,}{extra}, so the "
            f"municipalities' {FIGURES[name]} figures are not shown.")


def compare_national(reports: list[Report], national_rows: list[dict[str, Any]],
                     apart: dict[tuple[str, str], str] | None = None,
                     notes: dict[tuple[str, str], str] | None = None
                     ) -> list[tuple[str, str, str]]:
    """Each province's composition against the national report's, by group, for
    the provinces as drawn whose every report's table was read; ``notes`` gets
    the sentence for each refused (province, field)."""
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
                    apart_of.append((group, mine[group], count))
            if len(off) > 1:
                problems.append((shape, name, f"{shape} {name}: " + "; ".join(off)))
                if notes is not None:
                    notes[(shape, name)] = national_note(shape, name, apart_of)
            elif off:
                log(f"  national check: {shape} {name}: one group apart, kept: {off[0]}")
                if apart is not None:
                    group, mine_count, theirs_count = apart_of[0]
                    apart[(shape, name)] = (
                        f" The provincial report counts {mine_count:,} people of {shape} "
                        f"province under {QUOTED.get(group, group)}, the census's "
                        f"national report {theirs_count:,}.")
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


# The census's site links Uíge's and Cuanza Sul's reports but answers 404 for
# them. INE also publishes the provincial reports among its own publications,
# under numbered file names; a copy is taken only when its first pages name
# the province and the 2024 definitive results.
INE_COPIES = {
    "Uige": ("https://www.ine.gov.ao/Arquivos/arquivosCarregados/Carregados/"
             "Publicacao_639105199780531702.pdf",
             "https://www.ine.gov.ao/Arquivos/arquivosCarregados/Carregados/"
             "Publicacao_639120325078684256.pdf"),
    "Cuanza_Sul": ("https://ine.gov.ao/Arquivos/arquivosCarregados/Carregados/"
                   "Publicacao_639065784580611643.pdf",),
}
COPY_OF = {"Uige": "provinciadouige", "Cuanza_Sul": "provinciadocuanzasul"}


def names_province(blob: bytes, stem: str) -> bool:
    from pypdf import PdfReader                      # noqa: PLC0415
    text = ""
    for page in PdfReader(io.BytesIO(blob)).pages[:8]:
        try:
            text += page.extract_text() or ""
        except Exception:                            # noqa: BLE001
            continue
    said = fold(text)
    return COPY_OF[stem] in said and "resultadosdefinitivos" in said and "2024" in said


def fetch_report(stem: str) -> tuple[bytes, str]:
    """The report and the address it is cited at."""
    import urllib.parse                              # noqa: PLC0415
    tried = []
    names = (f"Relatorio_Provincial_{stem}_Censo2024", *ALTERNATES.get(stem, ()), stem.upper())
    urls = ["https://censo2024.ine.gov.ao/" + urllib.parse.quote(n) + ".pdf" for n in names]
    # The Internet Archive's copy, where the site answers 404 for a file it links.
    archive = "https://web.archive.org/web/2026id_/" + urls[0]
    copies = INE_COPIES.get(stem, ())
    for url in [*urls, archive, *copies]:
        name = url.rsplit("/", 1)[-1]
        try:
            blob = http_get(url, binary=True, cache=False, timeout=600)
        except Exception as exc:                      # noqa: BLE001
            tried.append(f"{name}: {exc}")
            continue
        if blob[:4] != b"%PDF":
            tried.append(f"{name}: not a PDF")
            continue
        if url in copies and not names_province(blob, stem):
            tried.append(f"{name}: not the 2024 report of {SHOWN.get(stem, stem)}")
            continue
        return blob, urls[0] if url == archive else url
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


def inspect(stem: str, blob: bytes) -> None:
    """Each table's pages as the reader lays them out: the blocks' columns,
    headers and first rows, and Quadro 1.7's figure columns and rows."""
    import pdfplumber                                # noqa: PLC0415
    texts = page_texts(blob)
    specs = [*TABLES.items(), ("medians", {"key": MEDIAN_PAGES})]
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for name, spec in specs:
            hits = [i for i, t in enumerate(texts) if any(k in t for k in keys_of(spec))
                    and not t.count("quadro") > 12]       # not the list of tables
            log(f"== {stem} {name}: pages {[i + 1 for i in hits]}")
            for i in hits[:5]:
                rows = rows_of(pdf.pages[i].extract_words(use_text_flow=False,
                                                          keep_blank_chars=False))
                if name == "medians":
                    title, entries = median_entries(rows)
                    at = next((k for k, r in enumerate(rows)
                               if "mediana" in squeeze(words_of(r))), None)
                    columns = [round(min(c)) for c in decimal_columns(rows)]
                    log(f"  p{i + 1}: title {title[:90]!r}; first 'mediana' row "
                        f"{words_of(rows[at])[:90] if at is not None else None!r}; figure "
                        f"columns at {columns}; {len(entries)} entries: "
                        + "; ".join(f"{lab}={m}" for lab, m in entries[:45]))
                    continue
                for block in blocks_of(rows, lead=True, singles=True):
                    bad = assign_columns(block)
                    log(f"  p{i + 1} block {block.title[:90]!r}: {len(block.data)} rows, "
                        f"columns at {[round(c) for c in block.columns]}")
                    for j, t in enumerate(header_texts(block)):
                        log(f"    col {j}: {t[:90]}")
                    for r in block.data[:7]:
                        log(f"    row {r.label!r}: " + " ".join(
                            f"{v}@{x1:.0f}" for _, x1, v in r.figures(block.columns)))
                    for line in bad[:4]:
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
    parser.add_argument("--inspect", default="",
                        help="Stem,Stem -- print each table's pages as laid out, write nothing")
    args = parser.parse_args()
    import pdfplumber                                # noqa: PLC0415
    stems = [s for s in REPORTS if not args.only or s in args.only.split(",")]
    if args.inspect:
        for stem in args.inspect.split(","):
            try:
                inspect(stem, fetch_report(stem)[0])
            except Exception as exc:                  # noqa: BLE001
                log(f"== {stem}: {type(exc).__name__}: {exc}")
        return 0
    if args.debug:
        for part in args.debug.split(";"):
            stem, _, numbers = part.partition(":")
            try:
                debug(stem, fetch_report(stem)[0], [int(n) for n in numbers.split(",") if n])
            except Exception as exc:                  # noqa: BLE001
                log(f"== {stem}: {type(exc).__name__}: {exc}")
        return 0
    if args.survey:
        for stem in stems:
            try:
                survey(stem, fetch_report(stem)[0])
            except Exception as exc:                  # noqa: BLE001
                log(f"== {stem}: {type(exc).__name__}: {exc}")
        return 0
    reports: list[Report] = []
    failed: list[str] = []
    for stem in stems:
        try:
            blob, url = fetch_report(stem)
            texts = page_texts(blob)
            wanted = {i for i, t in enumerate(texts)
                      if any(k in t for k in (*SEX_TABLES, "porgruposetariosquinquenais",
                                              *MEDIAN_PAGES, *(k for s in TABLES.values()
                                                               for k in keys_of(s))))}
            wanted |= {i + 1 for i in wanted if i + 1 < len(texts)}
            pages: list[list[Row]] = [[] for _ in texts]
            with pdfplumber.open(io.BytesIO(blob)) as pdf:
                for i in sorted(wanted):
                    words = pdf.pages[i].extract_words(use_text_flow=False,
                                                       keep_blank_chars=False)
                    pages[i] = rows_of(words)
            rep = read_report(stem, pages, texts)
            rep.url = url
        except Exception as exc:                      # noqa: BLE001
            failed.append(stem)
            log(f"angola_municipios: {stem}: {type(exc).__name__}: {exc}")
            continue
        reports.append(rep)
        log(f"angola_municipios: {stem}: {url.rsplit('/', 1)[-1]}, {len(blob):,} bytes, "
            f"{len(texts)} pages, {len(wanted)} read; province {rep.province!r} {rep.total}; "
            f"{len(rep.new)} municipalities of 2024, {len(rep.old)} of 2016; "
            + ", ".join(f"{k} {len(v)} rows" for k, v in rep.tables.items())
            + f"; Quadros {rep.quadros}")
        log("    2016: " + "; ".join(f"{n} {t:,}" for n, t, *_ in rep.old))
        log("    2024: " + "; ".join(f"{n} {t:,}" for n, t, *_ in rep.new))
        log(f"    median ages (Quadro {rep.quadros.get('medians', '?')}): province {rep.median}; "
            + "; ".join(f"{n} {rep.medians.get(fold(n), '-')}" for n, *_ in rep.new))
        for table, got in rep.patched.items():
            for k, (how, printed, used) in got.items():
                log(f"    {table}: {k}'s row {printed:,} replaced by its communes ({how}): "
                    f"{used:,}")
    path = PROCESSED / "angola_province.json"
    national_rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    apart: dict[tuple[str, str], str] = {}
    national: dict[tuple[str, str], str] = {}
    disagree = compare_national(reports, national_rows, apart, national)
    for _, _, line in disagree[:80]:
        log(f"  national check: {line}")
    refused = {(shape, name) for shape, name, _ in disagree}
    for shape, name in sorted(refused):
        log(f"  {shape}: {name} left out, its provincial table not the national report's")
    admin1 = json.loads((SITE / "admin1" / "AGO.units.json").read_text(encoding="utf-8"))
    admin2 = json.loads((SITE / "admin2" / "AGO.units.json").read_text(encoding="utf-8"))
    records, lines = build(reports, admin1, admin2, refused, apart, national)
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
