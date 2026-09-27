#!/usr/bin/env python3
"""Armenia's marzes and Yerevan: nationality, mother tongue and religion, 2011.

The 2022 census's results pages carry no tables yet, so the latest census with
compositions by marz is 2011's. Armstat publishes its results for each marz
and for Yerevan as one PDF per table, listed on the marz's page in the
Armenian-language site (the English pages list none):

* table 5.2-1 -- the permanent population by nationality, sex and mother
  tongue: its first block (both sexes, urban and rural together) gives each
  nationality's count down the side and each mother tongue's across;
* table 5.4 -- the same population by nationality, sex and religious belief:
  its first row gives each religion's count.

The column headings are set sideways, one glyph at a time, so each column's
heading is rebuilt from the glyphs above it and read for a known word
("առաքելական" is Armenian Apostolic, "Եհովա" Jehovah's Witnesses, "Եզդիերեն"
the Yezidi tongue); a heading that names nothing known stops the run and prints
what it read. Every count is checked: the nationalities make the total, the
tongues make it, and the religions make it.

"Refused to answer" and "religion not indicated" are written together as "Not
stated".

Usage:
    python -m scripts.fetch_census.armenia_2011
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, record, shares, write_json

SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "armenia_2011.json"
YEAR = 2011
PAGE = "https://armstat.am/am/?nid={nid}"
FILE = re.compile(r'href="\.\./file/doc/(\d+)\.pdf"[^>]*>\s*Աղյուսակ\s*(5\.2-1|5\.2|5\.4)\s')
SOURCE = ("Statistical Committee of the Republic of Armenia (Armstat), 2011 population "
          "census of the Republic of Armenia, {unit}: table {table}")
LICENCE = "Armstat, open publication"

# The Armenian-language page of each marz's results -> (the map's unit, the
# stem of its name the table's own heading carries).
MARZ = {533: ("Yerevan", "Երևան"), 534: ("Aragatsotn", "Արագածոտն"),
        535: ("Ararat", "Արարատ"), 536: ("Armavir", "Արմավիր"),
        537: ("Gegharkunik", "Գեղարքունիք"), 538: ("Lori", "Լոռ"),
        539: ("Kotayk", "Կոտայք"), 540: ("Shirak", "Շիրակ"), 541: ("Syunik", "Սյունիք"),
        542: ("Vayots Dzor", "Վայոցձոր"), 543: ("Tavush", "Տավուշ")}

TOTAL = ("ընդամենը", "բնակչություն")
# Heading words -> label, tried in order (the first that a heading holds).
RELIGION = [
    ("դավանանքով", None), ("ունեցող", None),          # everyone with a religion
    ("չունեն", "No religion"), ("չունի", "No religion"),
    ("հրաժարվ", "Not stated"), ("նշված", "Not stated"),
    ("առաքել", "Armenian Apostolic"), ("կաթոլ", "Catholic"),
    ("ուղղափառ", "Orthodox"), ("ավետարան", "Evangelical"),
    ("բողոք", "Protestant"), ("եհովա", "Jehovah's Witnesses"),
    ("մոլոկ", "Molokan"), ("շարֆադ", "Yazidi"), ("եզդի", "Yazidi"),
    ("հեթանոս", "Paganism"), ("իսլամ", "Muslim"), ("մահմեդ", "Muslim"),
    ("հուդա", "Judaism"), ("մորմոն", "Latter-day Saints"),
    ("այլ", "Other religion"),
]
LANGUAGE = [
    ("հրաժարվ", "Not stated"),
    ("հայերեն", "Armenian"), ("եզդիերեն", "Yazidi"), ("ռուսերեն", "Russian"),
    ("քրդերեն", "Kurdish"), ("ասորերեն", "Assyrian"), ("հունարեն", "Greek"),
    ("ուկրաիներեն", "Ukrainian"), ("վրացերեն", "Georgian"), ("պարսկերեն", "Persian"),
    ("անգլերեն", "English"), ("գերմաներեն", "German"), ("ֆրանսերեն", "French"),
    ("արաբերեն", "Arabic"), ("ադրբեջաներեն", "Azerbaijani"), ("բելառուսերեն", "Belarusian"),
    ("այլ", "Other language"),
]
NATIONALITY = {
    "հայ": "Armenian", "եզդի": "Yazidi", "ռուս": "Russian", "քուրդ": "Kurdish",
    "ասորի": "Assyrian", "հույն": "Greek", "ուկրաինացի": "Ukrainian", "վրացի": "Georgian",
    "պարսիկ": "Persian", "հրեա": "Jewish", "գերմանացի": "German", "բելառուս": "Belarusian",
    "լեհ": "Polish", "թաթար": "Tatar", "ադրբեջանցի": "Azerbaijani", "մոլդովացի": "Moldovan",
    "այլ": "Other ethnicity", "այլազգություն": "Other ethnicity",
    "հրաժարվելենպատասխանել": "Not stated",
}
# A block of rows after the first: the urban, rural, men's or women's.
NEXT_BLOCK = ("քաղաք", "գյուղ", "տղամարդ", "կին")
NUMBER = re.compile(r"^\d{1,3}(,\d{3})*$")


def squeeze(text: str) -> str:
    return re.sub(r"[\s\-‐–]", "", text).lower()


def lines_of(chars: list[dict[str, Any]], upright: bool) -> list[str]:
    """Glyphs grouped into lines of text. Upright glyphs share a baseline and
    read left to right. Sideways ones are set either in columns (sharing an x,
    read from the bottom up) or turned right over (sharing a baseline, read
    right to left); whichever grouping makes fewer lines is the one used, and
    a line read the wrong way round is matched reversed (see classify)."""
    by_top: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_x: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for c in chars:
        by_top[round(c["top"] / 2.5)].append(c)
        by_x[round(c["x0"] / 2.5)].append(c)
    if upright or len(by_top) <= len(by_x):
        return ["".join(c["text"] for c in sorted(by_top[k], key=lambda c: c["x0"]))
                for k in sorted(by_top)]
    return ["".join(c["text"] for c in sorted(by_x[k], key=lambda c: -c["top"]))
            for k in sorted(by_x)]


def page_rows(page) -> list[tuple[float, list[dict[str, Any]]]]:
    """Upright words grouped by baseline: [(top, words left to right)]."""
    words = [w for w in page.extract_words(keep_blank_chars=False) if w.get("upright", True)]
    rows: list[tuple[float, list[dict[str, Any]]]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= 2.5:
            rows[-1][1].append(w)
        else:
            rows.append((w["top"], [w]))
    return [(top, sorted(ws, key=lambda w: w["x0"])) for top, ws in rows]


def split(words: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    label = [w["text"] for w in words if not NUMBER.match(w["text"])]
    numbers = [w for w in words if NUMBER.match(w["text"])]
    return " ".join(label), numbers


def read_table(blob: bytes, stem: str) -> dict[str, Any]:
    """{"headings": [text per column], "total": [n per column],
    "rows": {label: [n per column]}} for the first block of page 1."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        page = pdf.pages[0]
        rows = page_rows(page)
        chars = page.chars
    texts = [(top, squeeze("".join(w["text"] for w in ws))) for top, ws in rows]
    unit_top = next((top for top, t in texts if "մշտական" in t), None)
    if unit_top is None or not any(squeeze(stem) in t for _, t in texts):
        raise SystemExit(f"armenia_2011: the table's heading does not name {stem}: "
                         f"{[t for _, t in texts[:4]]}")
    total_at = next((i for i, (top, ws) in enumerate(rows)
                     if split(ws)[0] and squeeze(split(ws)[0]) == "ընդամենը"
                     and len(split(ws)[1]) > 2), None)
    if total_at is None:
        raise SystemExit("armenia_2011: no 'Ընդամենը' row with figures")
    total_top, total_words = rows[total_at]
    _, numbers = split(total_words)
    edges = [w["x1"] for w in numbers]
    total = [int(w["text"].replace(",", "")) for w in numbers]
    # The label column ends where the widest row label does.
    label_edge = max((w["x1"] for _, ws in rows[total_at:] for w in ws
                      if not NUMBER.match(w["text"]) and w["x1"] < numbers[0]["x0"]),
                     default=numbers[0]["x0"] - 30)
    bands = list(zip([label_edge] + edges[:-1], edges))
    zone = [c for c in chars if unit_top + 4 < c["top"] < total_top - 1]
    headings = []
    for lo, hi in bands:
        inside = [c for c in zone if lo + 1 < (c["x0"] + c["x1"]) / 2 <= hi + 2]
        sideways = [c for c in inside if not c.get("upright", True)]
        if sideways:
            text = "".join(lines_of(sideways, upright=False))
        else:
            text = "".join(lines_of(inside, upright=True))
        headings.append(squeeze(text))
    # The first block's rows: after the total, until the next block begins.
    body: dict[str, list[int]] = {}
    pending = ""
    for top, ws in rows[total_at + 1:]:
        label, numbers = split(ws)
        if not label:
            continue                # a page number
        key = squeeze(pending + label)
        if not numbers:
            if key.startswith(NEXT_BLOCK) and not pending:
                break
            pending += label
            continue
        pending = ""
        if key in NEXT_BLOCK or key.startswith(NEXT_BLOCK) and key not in NATIONALITY:
            break
        if len(numbers) != len(total):
            raise SystemExit(f"armenia_2011: row {label!r} has {len(numbers)} figures, "
                             f"the total {len(total)}")
        body[key] = [int(w["text"].replace(",", "")) for w in numbers]
    return {"headings": headings, "total": total, "rows": body}


def classify(headings: list[str], words: list[tuple[str, str | None]], what: str
             ) -> list[str | None | bool]:
    """Each column's label; True for the total, None for a subtotal."""
    out: list[str | None | bool] = []
    for text in headings:
        if any(t in text or t[::-1] in text for t in TOTAL) and not out:
            out.append(True)
            continue
        hit = next((label for word, label in words if word in text or word[::-1] in text),
                   "?")
        if hit == "?":
            raise SystemExit(f"armenia_2011: a {what} heading names nothing known: "
                             f"{text!r}; all headings: {headings}")
        out.append(hit)
    return out


def composition(values: list[int], labels: list[str | None | bool], what: str, unit: str
                ) -> dict[str, float]:
    total = values[labels.index(True)]
    counts: dict[str, float] = defaultdict(float)
    for label, n in zip(labels, values):
        if isinstance(label, str):
            counts[label] += n
    if abs(sum(counts.values()) - total) > 0.5:
        raise SystemExit(f"armenia_2011: {unit} {what}: the columns make "
                         f"{sum(counts.values()):,.0f}, the total {total:,}")
    return dict(counts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    admin1 = {u["name"]: u for u in json.loads((SITE / "admin1" / "ARM.units.json").read_text())}
    records = []
    for nid, (name, stem) in MARZ.items():
        unit = admin1.get(name)
        if unit is None:
            raise SystemExit(f"armenia_2011: the map has no first-level unit {name!r}")
        html = http_get(PAGE.format(nid=nid), timeout=120)
        files = {table: doc for doc, table in FILE.findall(html)}
        language_file = files.get("5.2-1") or files.get("5.2")
        if not language_file or "5.4" not in files:
            raise SystemExit(f"armenia_2011: {name}'s page lists tables {sorted(files)}")
        lang = read_table(http_get(f"https://armstat.am/file/doc/{language_file}.pdf",
                                   binary=True, timeout=180), stem)
        faith = read_table(http_get(f"https://armstat.am/file/doc/{files['5.4']}.pdf",
                                    binary=True, timeout=180), stem)
        log(f"  {name}: 5.2-1 headings {lang['headings']}")
        log(f"  {name}: 5.4 headings {faith['headings']}")
        tongues = composition(lang["total"], classify(lang["headings"], LANGUAGE, "language"),
                              "mother tongue", name)
        religions = composition(faith["total"],
                                classify(faith["headings"], RELIGION, "religion"),
                                "religion", name)
        total = lang["total"][0]
        nations: dict[str, float] = defaultdict(float)
        for key, values in lang["rows"].items():
            label = NATIONALITY.get(key)
            if label is None:
                raise SystemExit(f"armenia_2011: {name}: a nationality row {key!r} is "
                                 "not configured")
            nations[label] += values[0]
        if abs(sum(nations.values()) - total) > 0.5:
            raise SystemExit(f"armenia_2011: {name}: the nationalities make "
                             f"{sum(nations.values()):,.0f}, the total {total:,}")
        if faith["total"][0] != total:
            raise SystemExit(f"armenia_2011: {name}: table 5.4 counts {faith['total'][0]:,}, "
                             f"table 5.2-1 {total:,}")
        log(f"  {name}: {total:,} people; " + ", ".join(
            f"{k} {v:,.0f}" for k, v in sorted(religions.items(), key=lambda kv: -kv[1])[:5]))
        src = {t: SOURCE.format(unit=name, table=t) for t in ("5.2-1", "5.4")}
        url = PAGE.format(nid=nid)
        records.append(record(
            f"ARM-2011-{unit['id']}", name, level="admin1", parent="ARM", country="ARM",
            match_by="shape_id", shape_id=unit["id"],
            ethnicity=shares(dict(nations), total=total), ethnicity_year=YEAR,
            ethnicity_note=("Nationality (ազգություն) as each person stated it, 2011 census, "
                            "the permanent population. The 2022 census has published no "
                            "table by marz yet."),
            language=shares(dict(tongues), total=total), language_year=YEAR,
            language_note=("Mother tongue (մայրենի լեզու), 2011 census, the permanent "
                           "population; 'Yazidi' is the tongue the census names apart "
                           "from Kurdish."),
            religion=shares(dict(religions), total=total), religion_year=YEAR,
            religion_note=("Religious belief (կրոնական դավանանք), 2011 census, the "
                           "permanent population; 'Yazidi' is the census's Sharfadin. "
                           "'Not stated' joins those who refused to answer and those "
                           "whose belief was not recorded."),
            sources=[{"field": "ethnicity", "name": src["5.2-1"], "url": url,
                      "license": LICENCE, "year": YEAR},
                     {"field": "language", "name": src["5.2-1"], "url": url,
                      "license": LICENCE, "year": YEAR},
                     {"field": "religion", "name": src["5.4"], "url": url,
                      "license": LICENCE, "year": YEAR}]))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
