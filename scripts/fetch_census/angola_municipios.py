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
from collections import defaultdict
from dataclasses import dataclass, field
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
LUANDA_NOTE = (
    "The 2024 census tabulates Luanda and Icolo e Bengo provinces only by the municipalities "
    "created in 2024, which cut across the municipalities drawn here, so none of its figures "
    "describes this polygon.")

GAP = 4.0          # points: digit groups of one figure sit closer than this
ROW_TOLERANCE = 2.0
ORPHAN_REACH = 12.0
COLUMN_REACH = 6.0

UNIVERSE = "population aged 2 and over"
ETHNIC = {
    "Bakongo": ("quicongo", "kikongu", "conguês", "congues"),
    "Ambundu": ("quimbundo", "tymbundu"),
    "Lunda-Chokwe": ("lunda", "quioco", "kioko"),
    "Ovimbundu": ("umbundo", "ovimbundo"),
    "Nyaneka-Humbe": ("nhaneca", "nyaneka", "humbe"),
    "Ovambo": ("ambo", "vahambo", "xikwanyama"),
    "Herero": ("herero", "helelo"),
    "Cuangar": ("cuangar",),
    "Khoisan": ("khoisan",),
    "Vátua": ("vatua",),
    "Kwoi": ("kwoi",),
    "Ndonga": ("xindonga", "oshindonga"),
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
    "Foreign languages": ("estrangeir",),
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
    "No religion": ("sem",),
    "Other religion": ("outra",),
    "Not stated": ("naosabe", "respondeu"),
}
AGE_BROAD = {"0-14": ("0-14",), "15-64": ("15-64",), "65+": ("65ou", "65e", "65+")}
AGE_OTHER = {"0-19": ("0-19",), "20-29": ("20-29",), "30-54": ("30-54",), "55-64": ("55-64",),
             "65-74": ("65-74",), "75+": ("75ou", "75e", "75+")}

# Each table: the words of its heading (squeezed, accents dropped) and its labels.
TABLES: dict[str, dict[str, Any]] = {
    "ethnicity": {"key": "gruposetnicosoutribos", "labels": ETHNIC},
    "language": {"key": "segundoalinguamaterna", "labels": LANGUAGE},
    "religion": {"key": "segundoareligiaoouespiritualidade", "labels": RELIGION},
    "age_broad": {"key": "segundograndesgruposetarios", "labels": AGE_BROAD},
    "age_other": {"key": "segundooutrosgruposetarios", "labels": AGE_OTHER},
}
NOTES = {
    "ethnicity": ("The 2024 census's count of the population aged 2 and over by ethnic group "
                  "(grupos étnicos ou tribos), as it names them: Quicongo is shown as Bakongo, "
                  "Quimbundo as Ambundu, Lunda-Quioco as Lunda-Chokwe, Umbundo as Ovimbundu, "
                  "Nhaneca-Humbe as Nyaneka-Humbe, Ambó as Ovambo, Helelo as Herero and "
                  "Xindonga as Ndonga."),
    "language": ("The 2024 census's count of the population aged 2 and over by mother tongue "
                 "(língua materna), in the census's groups; foreign languages are one group."),
    "religion": ("The 2024 census's count of the population aged 2 and over by declared "
                 "religion, the denominations kept apart as printed."),
}


def squeeze(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalnum() or c in "-+")


@dataclass
class Row:
    top: float
    words: list[tuple[float, float, str]] = field(default_factory=list)

    @property
    def label(self) -> str:
        return " ".join(t for _, _, t in self.label_words())

    def label_words(self) -> list[tuple[float, float, str]]:
        last = max((i for i, (_, _, t) in enumerate(self.words) if not t.isdigit()), default=-1)
        return self.words[:last + 1]

    def figures(self) -> list[tuple[float, float, int]]:
        """Digit groups after the label, joined into figures by the gaps between them."""
        last = max((i for i, (_, _, t) in enumerate(self.words) if not t.isdigit()), default=-1)
        out: list[tuple[float, float, int]] = []
        run: list[tuple[float, float, str]] = []
        for x0, x1, t in self.words[last + 1:]:
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
        alone = all(t.isdigit() for _, _, t in row.words)
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


def blocks_of(rows: list[Row]) -> list[Block]:
    """A page cut at each "Quadro" heading; rows before the first belong to none."""
    out: list[Block] = []
    current: Block | None = None
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


def assign_columns(block: Block) -> list[str]:
    """Columns from the row with the most figures; every figure must sit on one."""
    template = max(block.data, key=lambda r: len(r.figures()))
    block.columns = [x1 for _, x1, _ in template.figures()]
    problems = []
    for row in block.data:
        seen = set()
        for _, x1, value in row.figures():
            j = min(range(len(block.columns)), key=lambda k: abs(block.columns[k] - x1))
            if abs(block.columns[j] - x1) > COLUMN_REACH or j in seen:
                problems.append(f"{row.label}: figure {value} at {x1:.0f} fits no column")
            seen.add(j)
    return problems


def values(block: Block, row: Row) -> list[int | None]:
    out: list[int | None] = [None] * len(block.columns)
    for _, x1, value in row.figures():
        j = min(range(len(block.columns)), key=lambda k: abs(block.columns[k] - x1))
        out[j] = value
    return out


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
    labels = ["TOTAL"]
    for text in texts[1:]:
        s = squeeze(text)
        hits = [lab for lab, keys in spec.items() if any(k in s for k in keys)]
        if len(hits) != 1:
            return None
        labels.append(hits[0])
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


def sexes_add_up(total: int, men: int, women: int) -> bool:
    """The reports' figures are rounded from weighted counts: a total may sit a
    person or two off its men and women."""
    return abs(total - men - women) <= 2


def read_report(stem: str, pages: list[list[Row]], texts: list[str]) -> Report:
    rep = Report(stem)
    # Quadro 10 (the 2024 municipalities by sex: three figures a row) and
    # Quadro 11 (the 2016 ones at both censuses: six), told apart by their width.
    old_head: int | None = None
    for i, text in enumerate(texts):
        if "residentepormunicipiosegundoosexo" not in text and "porgruposetariosquinquenais" not in text:
            continue
        for block in blocks_of(pages[i]):
            title = squeeze(block.title)
            rows = [(r.label, r.figures()) for r in block.data]
            widths = {len(f) for _, f in rows}
            if "residentepormunicipiosegundoosexo" in title and widths == {3} and not rep.new:
                rep.province = rows[0][0]
                t = rows[0][1]
                rep.total = (t[0][2], t[1][2], t[2][2])
                rep.new = [(lab, f[0][2], f[1][2], f[2][2]) for lab, f in rows[1:]]
            elif "residentepormunicipiosegundoosexo" in title and widths == {6} and not rep.old:
                rep.old = [(lab, f[3][2], f[4][2], f[5][2]) for lab, f in rows[1:]]
                old_head = rows[0][1][3][2]
            elif "porgruposetariosquinquenais" in title and not rep.five_year:
                for r in block.data:
                    m = re.match(r"(\d+)\s*-\s*(\d+)\s*anos", r.label)
                    m2 = re.match(r"(\d+)\s*(?:ou|e)\s*mais", r.label)
                    f = r.figures()
                    if m and len(f) == 3:
                        rep.five_year.append((int(m.group(1)), int(m.group(2)), f[0][2]))
                    elif m2 and len(f) == 3:
                        rep.five_year.append((int(m2.group(1)), None, f[0][2]))
    if not rep.new:
        rep.problems.append("no table of the 2024 municipalities by sex")
        return rep
    for label, t, m, f in [(rep.province, *rep.total), *rep.new, *rep.old]:
        if not sexes_add_up(t, m, f):
            rep.problems.append(f"{label}: {t:,} is not {m:,} men and {f:,} women")
    made = sum(t for _, t, *_ in rep.new)
    if abs(made - rep.total[0]) > 2 + len(rep.new):
        rep.problems.append(f"the 2024 municipalities make {made:,}, not {rep.total[0]:,}")
    if rep.old:
        made = sum(t for _, t, *_ in rep.old)
        if old_head != rep.total[0] or abs(made - rep.total[0]) > 2 + len(rep.old):
            rep.problems.append(f"the 2016 municipalities make {made:,} (head {old_head}), "
                                f"not {rep.total[0]:,}; table left out")
            rep.old = []
    if rep.five_year and abs(sum(n for *_, n in rep.five_year) - rep.total[0]) > 5:
        rep.problems.append("the five-year groups do not make the province; left out")
        rep.five_year = []
    for name, spec in TABLES.items():
        rep.tables[name] = read_table(rep, name, spec, pages, texts)
    return rep


def read_table(rep: Report, name: str, spec: dict[str, Any], pages: list[list[Row]],
               texts: list[str]) -> list[tuple[str, dict[str, int]]]:
    """The table's rows in order, each {label: count}, its column groups joined."""
    groups: dict[tuple[str, ...], list[tuple[str, list[int | None]]]] = {}
    order: list[tuple[str, ...]] = []
    last: Block | None = None
    for i, text in enumerate(texts):
        if spec["key"] not in text:
            continue
        for block in blocks_of(pages[i]):
            if spec["key"] not in squeeze(block.title):
                continue
            bad = assign_columns(block)
            if bad:
                rep.problems.append(f"{name} p{i + 1}: " + "; ".join(bad[:3]))
                continue
            labels = label_columns(block, spec["labels"])
            if labels is None and last is not None and len(last.columns) == len(block.columns) \
                    and all(abs(a - b) <= 4 for a, b in zip(last.columns, block.columns)):
                labels = last.labels
            if labels is None:
                rep.problems.append(f"{name} p{i + 1}: header not read "
                                    f"({len(block.columns)} columns)")
                continue
            block.labels = labels
            last = block
            key = tuple(labels)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key] += [(r.label, values(block, r)) for r in block.data]
    if not order:
        rep.problems.append(f"{name}: not found")
        return []
    first = groups[order[0]]
    out: list[tuple[str, dict[str, int]]] = []
    for k, (label, vals) in enumerate(first):
        row: dict[str, int] = {}
        for key in order:
            rows = groups[key]
            if k >= len(rows) or fold(rows[k][0]) != fold(label):
                rep.problems.append(f"{name}: column groups do not list the same rows at "
                                    f"{label!r}")
                return []
            for lab, v in zip(key, rows[k][1]):
                if v is None:
                    rep.problems.append(f"{name}: {label} has no figure under {lab}")
                    return []
                if lab == "TOTAL" and "TOTAL" in row and row["TOTAL"] != v:
                    rep.problems.append(f"{name}: {label}'s totals differ between column "
                                        f"groups ({row['TOTAL']} vs {v})")
                    return []
                row[lab] = v
        out.append((label, row))
    return out


def municipalities(rep: Report, name: str, rows: list[tuple[str, dict[str, int]]]
                   ) -> dict[str, dict[str, int]]:
    """The 2024 municipalities' rows of a table that also lists communes.

    A row is a municipality's when its name is the next of the report's
    municipalities and the communes since the last one have made that one's
    total; the rest are communes.
    """
    names = [fold(n) for n, *_ in rep.new]
    out: dict[str, dict[str, int]] = {}
    i = 0
    current: str | None = None
    made = 0
    start = next((k for k, (lab, _) in enumerate(rows) if fold(lab) in names), None)
    if start is None:
        rep.problems.append(f"{name}: no municipality row")
        return {}
    only_municipalities = all(fold(lab) in names for lab, _ in rows[start:]) and \
        len(rows) - start == len(names)
    for label, vals in rows[start:]:
        key = fold(label)
        ready = current is None or only_municipalities or made == out[current]["TOTAL"]
        if i < len(names) and key == names[i] and ready:
            if current is not None and not only_municipalities and made != out[current]["TOTAL"]:
                rep.problems.append(f"{name}: communes of {current} make {made}")
            current = key
            out[key] = dict(vals)
            made = 0
            i += 1
        elif current is not None:
            made += vals["TOTAL"]
        else:
            rep.problems.append(f"{name}: {label} before any municipality")
    if current is not None and not only_municipalities and made != out[current]["TOTAL"]:
        rep.problems.append(f"{name}: communes of {current} make {made}, not "
                            f"{out[current]['TOTAL']}")
    if len(out) != len(names):
        missing = [n for n, *_ in rep.new if fold(n) not in out]
        rep.problems.append(f"{name}: municipalities not found: {', '.join(missing)}")
    return out


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


# -- the map's polygons -----------------------------------------------------

def polygon_for(name: str, province: str, admin2: list[dict[str, Any]],
                provinces: dict[str, str]) -> dict[str, Any] | None:
    key = fold(name)
    wanted = {key, ALIASES.get(key, key)}
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


def build(reports: list[Report], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
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
    for rep in reports:
        shape = REPORTS[rep.stem]
        if rep.total:
            for j in range(3):
                shape_totals[shape][j] += rep.total[j]
            shape_reports[shape].append(rep.province or rep.stem)
            for low, high, n in rep.five_year:
                shape_groups[shape][(low, high)] += n
        if not rep.old:
            log_lines.append(f"  {rep.stem}: no table on the 2016 municipalities")
            for p in rep.problems:
                log_lines.append(f"  {rep.stem}: {p}")
            continue
        with_old.add(shape)
        walk = crosswalk(rep)
        parts_of: dict[str, list[str]] = defaultdict(list)
        if walk:
            for n, *_ in rep.new:
                parts_of[walk[fold(n)]].append(n)
        rows = {name: municipalities(rep, name, rep.tables.get(name) or [])
                for name in TABLES}
        usable = set()
        for name in TABLES:
            bad = [p for k, v in rows[name].items()
                   if name in NOTES and (p := check_composition(name, k, v))]
            rep.problems += bad
            if not bad and rows[name] and len(rows[name]) == len(rep.new):
                usable.add(name)
        if not walk:
            usable = set()
        for n, t, m, f in rep.old:
            unit = old_units.setdefault((fold(shape), fold(n)), {
                "name": n, "counts": [0, 0, 0], "parts": [], "rows": [], "fields": set(TABLES)})
            for j, v in enumerate((t, m, f)):
                unit["counts"][j] += v
            unit["fields"] &= usable
            for part in parts_of.get(fold(n), []):
                unit["parts"].append(part)
                unit["rows"].append({name: rows[name].get(fold(part), {}) for name in TABLES})
        for p in rep.problems:
            log_lines.append(f"  {rep.stem}: {p}")
        if walk:
            log_lines.append(f"  {rep.stem}: " + "; ".join(
                f"{o} = {' + '.join(parts_of.get(fold(o), [])) or '-'}" for o, *_ in rep.old))
    records: list[dict[str, Any]] = []
    # First level: the provinces as drawn, from the reports' totals.
    for shape, (t, m, f) in sorted(shape_totals.items()):
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
    for sid, units in sorted(on_polygon.items(), key=lambda kv: shapes[kv[0]]["name"]):
        poly = shapes[sid]
        if sid in NOT_DESCRIBED or not units:
            continue
        if len(units) > 1 and sid not in DRAWN_TOGETHER:
            log_lines.append(f"  {poly['name']}: {len(units)} municipalities on it; left out")
            continue
        t, m, f = (sum(u["counts"][j] for u in units) for j in range(3))
        names = [u["name"] for u in units]
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
        usable = set.intersection(*(u["fields"] for u in units))
        parts = [p for u in units for p in u["parts"]]
        rows = [r for u in units for r in u["rows"]]
        if parts and len(parts) == 1 and len(units) == 1 and fold(parts[0]) == fold(names[0]):
            tail = ""
        elif len(parts) == 1:
            tail = (f" The census tabulates the municipalities of 2024, in which {names[0]} "
                    f"is {parts[0]}.")
        else:
            tail = (f" The census tabulates the municipalities of 2024: {listed(parts)}, "
                    f"which together are {listed(names)} as it stood under Lei n.º 18/16, "
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
                fields[f"{name}_note"] = NOTES[name] + tail
            if {"age_broad", "age_other"} <= usable:
                med, why = median_of(rows)
                if med is not None:
                    fields["median_age"] = measure(med, unit="years", year=YEAR, source=SOURCE)
                    fields["median_age_note"] = (
                        "Taken from the 2024 census's counts by age group (0-14, 15-19, "
                        "20-29, 30-54, 55-64, 65-74, 75 and over)"
                        + (f" for {listed(parts)}, added together." if len(parts) > 1 else "."))
                else:
                    log_lines.append(f"  {poly['name']}: no median ({why})")
        records.append(record(f"AGO-RGPH2024-{sid}", poly["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=sid, sources=cite,
                              **fields))
        log_lines.append(f"  {poly['name']}: {t:,} ({' + '.join(names)}; from "
                         f"{', '.join(parts) or '-'}; {', '.join(sorted(usable)) or 'no tables'})")
    # The polygons no census figure describes say so.
    stated = dict(NOT_DESCRIBED)
    if "Luanda" not in with_old:
        stated.update({u["id"]: LUANDA_NOTE for u in admin2
                       if provinces.get(u["parent"]) == fold("Luanda")})
    for sid, note in sorted(stated.items()):
        poly = shapes.get(sid)
        if poly is None:
            continue
        fields = {name: gap(NOT_AVAILABLE, note) for name in NOTES}
        records.append(record(f"AGO-RGPH2024-{sid}", poly["name"], level="admin2", parent="AGO",
                              country="AGO", match_by="shape_id", shape_id=sid, sources=cite,
                              **fields))
    return records, log_lines


def compare_national(reports: list[Report], national_rows: list[dict[str, Any]]) -> list[str]:
    """Each province's composition against the national report's, by group."""
    problems: list[str] = []
    by_shape: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for rep in reports:
        shape = REPORTS[rep.stem]
        for name in ("ethnicity", "language", "religion"):
            rows = rep.tables.get(name) or []
            if not rows:
                continue
            label, vals = rows[0]
            for k, v in vals.items():
                by_shape[shape][name][k] += v
    for row in national_rows:
        shape = row.get("name")
        for name in ("ethnicity", "language", "religion"):
            theirs = {g["group"]: g.get("count") for g in row.get(name) or []
                      if isinstance(g, dict)}
            mine = by_shape.get(shape, {}).get(name)
            if not mine or not theirs:
                continue
            for group, count in theirs.items():
                if count is None or group not in mine:
                    continue
                if abs(mine[group] - count) > max(0.01 * count, 50):
                    problems.append(f"{shape} {name} {group}: provincial {mine[group]:,}, "
                                    f"national {count:,}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.add_argument("--only", default="", help="report stems, comma-separated")
    args = parser.parse_args()
    import pdfplumber                                # noqa: PLC0415
    stems = [s for s in REPORTS if not args.only or s in args.only.split(",")]
    reports: list[Report] = []
    for stem in stems:
        url = URL.format(stem=stem)
        blob = http_get(url, binary=True, cache=False, timeout=600)
        texts = page_texts(blob)
        wanted = {i for i, t in enumerate(texts)
                  if any(k in t for k in ("residentepormunicipiosegundoosexo",
                                          "porgruposetariosquinquenais",
                                          *(s["key"] for s in TABLES.values())))}
        pages: list[list[Row]] = [[] for _ in texts]
        with pdfplumber.open(io.BytesIO(blob)) as pdf:
            for i in sorted(wanted):
                words = pdf.pages[i].extract_words(use_text_flow=False, keep_blank_chars=False)
                pages[i] = rows_of(words)
        rep = read_report(stem, pages, texts)
        reports.append(rep)
        log(f"angola_municipios: {stem}: {len(blob):,} bytes, {len(texts)} pages, "
            f"{len(wanted)} read; province {rep.province!r} {rep.total}; "
            f"{len(rep.new)} municipalities of 2024, {len(rep.old)} of 2016; "
            + ", ".join(f"{k} {len(v)} rows" for k, v in rep.tables.items()))
        log(f"    2016: " + "; ".join(f"{n} {t:,}" for n, t, *_ in rep.old))
        log(f"    2024: " + "; ".join(f"{n} {t:,}" for n, t, *_ in rep.new))
    national = json.loads((PROCESSED / "angola_province.json").read_text(encoding="utf-8")) \
        if (PROCESSED / "angola_province.json").exists() else []
    disagree = compare_national(reports, national)
    for line in disagree[:40]:
        log(f"  national check: {line}")
    if disagree:
        raise SystemExit(f"angola_municipios: {len(disagree)} provincial compositions differ "
                         f"from the national report's")
    admin1 = json.loads((SITE / "admin1" / "AGO.units.json").read_text(encoding="utf-8"))
    admin2 = json.loads((SITE / "admin2" / "AGO.units.json").read_text(encoding="utf-8"))
    records, lines = build(reports, admin1, admin2)
    for line in lines:
        log(line)
    a1 = sum(r["level"] == "admin1" for r in records)
    a2 = [r for r in records if r["level"] == "admin2"]
    log(f"  {a1} provinces; {sum(not isinstance(r['population'], dict) or 'value' in r['population'] for r in a2)} "
        f"municipality polygons with a count; {len(a2)} admin2 records")
    log(f"  country: {sum(r['population']['value'] for r in records if r['level'] == 'admin1'):,}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
