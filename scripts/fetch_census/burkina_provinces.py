#!/usr/bin/env python3
"""Burkina Faso -- each province's sex ratio from the 2019 census's regional monographs.

INSD published a monograph of each of the 13 regions from the fifth census
(5e RGPH, 2019; December 2022). Each gives the region's population by province
and sex (Tableau 2.3 in most: *Répartition (%) des effectifs de la population
par province selon le sexe*), the count of men and women of every province.
OCHA's projection for 2023 gave the provinces their region's split by sex, so
the map's provinces had no sex ratio of their own: this writes the census's,
for the 45 provinces. Their populations are left to the newer projection, and
their median age to the reason they already give (the monographs tabulate ages
by region only).

The Centre region is the one province of Kadiogo, and its monograph's regional
count by sex (Tableau 2.1) is the province's.

**Religion and language by province.** Each monograph charts its provinces'
religions (Graphique 3.2, *Répartition (%) de la population des communautés
religieuses par province*: the census's six classes, to one decimal) and
tabulates the principal language spoken by residents aged 3 and over by sex
and province (Tableau 3.3; Nord's runs on as 3.4), with the region's column.
The chart is read from the labels its text keeps -- the values series by
series, the axis's ticks, the provinces -- where it keeps them; four regions'
charts (Centre-Nord, Centre-Ouest, Centre-Sud, Nord) are pictures, and their
provinces say so. Each region also takes its own languages (the table's
region column, or Tableau 3.2's), a census in front of the survey's shares;
its religion is burkina.py's.

**Checks before anything is written.** Every province's men and women make
its total; each region's provinces make the table's total row, or, where the
table has none, the region's count by sex in Tableau 2.1; every province on the
map is found once. A region whose table fails a check keeps what it had. A
province's six religious shares make 100 within the chart's rounding; in the
language table each both-sexes figure lies between the men's and the women's
and each column makes 100 within the table's rounding (a figure the text
breaks around its comma, "29 ,0", is joined; one broken elsewhere, "10 0,0",
only where that alone makes the row's count and the sexes agree).

Usage:
    python -m scripts.fetch_census.burkina_provinces
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob  # noqa: E402

BASE = "https://www.insd.bf/sites/default/files/"
# The map's regions -> the monographs' addresses (the Cascades' is tried under
# the names its siblings use).
MONOGRAPHS = {
    "Boucle du Mouhoun": ["2023-02/MONOGRAPHIE%20DE%20LA%20BOUCLE%20DU%20MOUHOUN%205E%20RGPH.pdf"],
    "Cascades": ["2023-02/MONOGRAPHIE%20DES%20CASCADES%205E%20RGPH.pdf",
                 "2023-02/MONOGRAPHIE%20DES%20CASCADES%205E%20RGPH_0.pdf",
                 "2023-07/MONOGRAPHIE%20DES%20CASCADES%205E%20RGPH.pdf",
                 "2023-02/MONOGRAPHIE%20DE%20LA%20REGION%20DES%20CASCADES%205E%20RGPH.pdf"],
    "Centre": ["2023-02/MONOGRAPHIE%20DU%20CENTRE%205E%20RGPH.pdf"],
    "Centre-Est": ["2023-02/MONOGRAPHIE%20DU%20CENTRE-EST%205E%20RGPH.pdf"],
    "Centre-Nord": ["2023-02/MONOGRAPHIE%20DU%20CENTRE-NORD%205E%20RGPH_0.pdf"],
    "Centre-Ouest": ["2023-02/MONOGRAPHIE%20DU%20CENTRE%20OUEST%205E%20RGPH.pdf"],
    "Centre-Sud": ["2023-02/MONOGRAPHIE%20DU%20CENTRE-SUD%205E%20RGPH.pdf"],
    "Est": ["2023-02/MONOGRAPHIE%20DE%20L%27EST%205E%20RGPH.pdf"],
    "Hauts-Bassins": ["2023-02/MONOGRAPHIE%20DES%20HAUTS-BASSINS%205E%20RGPH.pdf"],
    "Nord": ["2023-02/MONOGRAPHIE%20DU%20NORD%205E%20RGPH.pdf"],
    "Plateau Central": ["2023-02/MONOGRAPHIE%20DU%20PLATEAU%20CENTRAL%205E%20RGPH.pdf"],
    "Sahel": ["2023-07/MONO%20REGION%20DU%20SAHEL%205E%20RGPH.pdf"],
    "Sud-Ouest": ["2023-02/MONOGRAPHIE%20DU%20SUD%20OUEST%205E%20RGPH.pdf"],
}
PUBLISHER = "Institut National de la Statistique et de la Démographie (INSD) du Burkina Faso"
YEAR = 2019
LICENCE = "INSD publication (reuse with attribution)"
OUT = "burkina_provinces.json"
SITE = PROCESSED.parent.parent / "site" / "data"
# Other spellings the monographs may use for the map's provinces (folded).
SPELLINGS = {"komonjdjari": ["Komondjari", "Komandjari"], "kouritenga": ["Kourittenga"],
             "bale": ["Balé", "Bale"], "tuy": ["Tuy", "Tui"]}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def readings(tokens: list[str], start: int) -> list[tuple[int, int]]:
    if start >= len(tokens) or not tokens[start].isdigit():
        return []
    first = tokens[start]
    if len(first) > 3:
        return [(int(first), start + 1)]
    out, j = [(int(first), start + 1)], start + 1
    while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
        j += 1
        out.append((int("".join(tokens[start:j])), j))
    return out


def triple_at(tokens: list[str], start: int) -> tuple[int, int, int] | None:
    """(men, women, total) beginning at tokens[start], the first two making the third."""
    for a, ea in readings(tokens, start):
        for b, eb in readings(tokens, ea):
            for c, _ in readings(tokens, eb):
                if a + b == c and c >= 1000:
                    return a, b, c
    return None


def close(label: str, name: str) -> bool:
    """A label that is another spelling of the province's name: the same first
    three letters and most of the rest (Komondjari, Komandjoari...)."""
    a, b = fold(label), fold(name)
    return (len(a) >= 4 and a[:3] == b[:3]
            and difflib.SequenceMatcher(None, a, b).ratio() >= 0.75)


def total_row(tokens: list[str]) -> list[tuple[int, int, int]]:
    """Every (men, women, total) that follows an Ensemble or Total label."""
    return [t for i, token in enumerate(tokens) if fold(token) in ("ensemble", "total")
            for t in [triple_at(tokens, i + 1)] if t]


def province_table(text: str, provinces: list[str],
                   region: tuple[int, int, int] | None = None) -> dict[str, tuple[int, int, int]]:
    """{province (the map's name): (men, women, total)} from the table of the
    region's population by province and sex, taken only when the provinces make
    the table's own total row, or the region's count by sex (Tableau 2.1) where
    the table has none. A province named otherwise than on the map is taken from
    a row whose label is close to its name."""
    flat = re.sub(r"\s+", " ", text)
    out: dict[str, tuple[int, int, int]] = {}
    seen = ""
    spellings = {name: [name] + SPELLINGS.get(fold(name), []) for name in provinces}
    for title in re.finditer(r"(?i)par\s+province\s+selon\s+le\s+sexe", flat):
        window = flat[title.end():title.end() + 3000]
        if re.match(r"\s*\.{3,}|\s*_{3,}", window):
            continue                       # the list of tables
        tokens = window.split()
        found: dict[str, tuple[int, int, int]] = {}
        for i in range(len(tokens)):
            for name, forms in spellings.items():
                if name in found:
                    continue
                for form in forms:
                    words = form.split()
                    if fold(" ".join(tokens[i:i + len(words)])) == fold(form):
                        triple = triple_at(tokens, i + len(words))
                        if triple:
                            found[name] = triple
                            break
        for name in provinces:
            if name in found or len(name.split()) > 1:
                continue
            for i in range(len(tokens)):
                taken = set(found.values())
                for width in (1, 2):
                    words = tokens[i:i + width]
                    if any(not w[:1].isalpha() for w in words):
                        continue
                    label = "".join(words)
                    triple = triple_at(tokens, i + width)
                    if triple and triple not in taken and close(label, name):
                        log(f"    {name} is the table's {' '.join(tokens[i:i + width])}")
                        found[name] = triple
                        break
                if name in found:
                    break
        if len(found) == len(provinces):
            sums = tuple(sum(v[k] for v in found.values()) for k in range(3))
            totals = total_row(tokens)
            if sums in totals or (not totals and sums == region):
                return found
            seen = (f"; its provinces make {sums}, its total rows say {totals} and the "
                    f"region's count {region}")
            continue
        out = out if len(out) >= len(found) else found
        seen = seen or f"; the table's lines: {' '.join(tokens[:160])}"
    raise SystemExit(f"burkina_provinces: the province table gives {sorted(out)} of "
                     f"{provinces}{seen}")


def regional_total(text: str) -> tuple[int, int, int]:
    """The region's men, women and total (Tableau 2.1's Ensemble row): the first
    title of the table that is not the list of tables' entry for it."""
    flat = re.sub(r"\s+", " ", text)
    for m in re.finditer(r"(?i)milieu\s+de\s+r[ée]sidence\s+selon\s+le\s+sexe\s+en\s+2019", flat):
        window = flat[m.end():m.end() + 1500]
        if re.match(r"\s*\.{3,}|\s*_{3,}", window):
            continue                       # the list of tables
        tokens = window.split()
        rows = total_row(tokens)
        if rows:
            return rows[0]
    raise SystemExit("burkina_provinces: no regional count by sex")


# The census's six religious classes, as burkina.py names them for the regions.
RELIGIONS = ["Animist", "Islam", "Catholic", "Protestant", "Other religion", "No religion"]
# The monographs' language labels (folded, up to the first parenthesis) -> names.
LANGUAGES = {
    "moore": "Mooré", "markaoudafing": "Marka", "marka": "Marka", "bwamuoubwamou": "Bwamu",
    "bwamu": "Bwamu", "sansamoghouosamo": "Samo", "sanousamoghouosamo": "Samo", "san": "Samo",
    "samo": "Samo", "diouloubambara": "Dioula", "dioulaoubambara": "Dioula", "dioula": "Dioula",
    "fulfudeoupeulh": "Fulfulde", "fulfuldeoupeulh": "Fulfulde", "fulfulde": "Fulfulde",
    "fulfude": "Fulfulde", "bobo": "Bobo", "nuninounouma": "Nuni", "nuni": "Nuni",
    "dogonoukaado": "Dogon", "dogon": "Dogon", "ko": "Ko", "francais": "French",
    "bissa": "Bissa", "moba": "Moba", "koussasse": "Koussassé", "kusaal": "Kusaal",
    "gourmantcheougulmancema": "Gourmantché", "gourmantche": "Gourmantché",
    "birifor": "Birifor", "toussian": "Toussian", "gouin": "Gouin", "turka": "Turka",
    "karaboro": "Karaboro", "senoufo": "Senufo", "kassenaoukassem": "Kassena",
    "kassena": "Kassena", "nankana": "Nankana", "ninkare": "Ninkare", "koromfe": "Koromfé",
    "tamacheqeoubella": "Tamasheq", "tamachequeoubella": "Tamasheq", "tamacheque": "Tamasheq",
    "sonrhai": "Songhai", "djerma": "Zarma", "dagara": "Dagara", "lobioulobiri": "Lobi",
    "lobi": "Lobi", "dyan": "Dyan", "kaansaougan": "Kaansa", "kaansa": "Kaansa",
    "dogose": "Dogosé", "gourounsi": "Gurunsi", "lyele": "Lyélé", "yana": "Yana",
    "autreslangues": "Other languages", "autreslanguesnationales": "Other African languages",
    "autreslanguesetrangeres": "Other foreign languages", "autre": "Other languages",
    "autres": "Other languages", "fulfudepeulh": "Fulfulde", "fulfuldepeulh": "Fulfulde",
    "haoussa": "Hausa", "biali": "Biali",
}
TOTALS = ("ensemble", "total", "region", "ens")
SEXES = {"m", "f", "h", "mf", "hf", "e", "masc", "fem", "ens"}
# The words of a language table's heading, folded ("Principales langues parlées",
# "Principale langue parl ée", "(suite et fin)").
HEADING = {"principales", "principale", "langues", "langue", "parlees", "parlee", "parl",
           "ees", "ee", "suite", "et", "fin", "sexe"}
# Two decimals set apart from their figure ("29 ,0", "0, 1", "100 , 0") and two
# one-decimal figures run together ("22,320,5" for 22,3 and 20,5).
SPLIT = re.compile(r"(\d)\s*,\s*(\d)")
GLUED = re.compile(r"(?<![\d,])(\d{1,3},\d)(\d{1,3},\d)(?![\d,])")


def tokens_of(text: str) -> list[str]:
    text = SPLIT.sub(r"\1,\2", text)
    while True:
        joined = GLUED.sub(r"\1 \2", text)
        if joined == text:
            return text.split()
        text = joined


def is_number(token: str) -> bool:
    return re.fullmatch(r"\d+(?:,\d+)?", token) is not None


def value(token: str) -> float:
    return float(token.replace(",", "."))


def province_of(token: str, provinces: list[str]) -> str | None:
    key = fold(token)
    if len(key) < 3:
        return None
    for p in provinces:
        if fold(p) == key or key in [fold(s) for s in SPELLINGS.get(fold(p), [])]:
            return p
    near = [p for p in provinces if close(token, p)]
    return near[0] if len(near) == 1 else None


def language_name(label: str) -> str | None:
    key = fold(re.sub(r"\(.*", "", label)) if "(" in label else fold(label)
    full = fold(label)
    return LANGUAGES.get(full) or LANGUAGES.get(key)


def religion_charts(text: str, provinces: list[str]) -> dict[str, dict[str, float]]:
    """{province or "Ensemble": {religion: %}} from Graphique 3.2, a bar chart whose
    labels the text keeps: the values series by series (or category by category),
    the axis's ticks (0, 10, 20 ...), the provinces, then the six religions'
    legend. A province's six shares must make 100 within the chart's rounding.
    The key "_seen" lists the provinces any chart labels, read or not."""
    toks = tokens_of(text)
    out: dict[str, dict[str, float]] = {"_seen": {}}
    i = 0
    while i < len(toks) - 3:
        if not (toks[i] == "0" and toks[i + 1] == "10" and toks[i + 2] == "20"):
            i += 1
            continue
        j, tick = i, 0
        while j < len(toks) and toks[j] == str(tick):
            j, tick = j + 1, tick + 10
        cats, k = [], j
        while k < len(toks):
            p = province_of(toks[k], provinces)
            if p:
                cats.append(p)
            elif fold(toks[k]) == "ensemble":
                cats.append("Ensemble")
            else:
                break
            k += 1
        vals, b = [], i - 1
        while b >= 0 and is_number(toks[b]):
            vals.insert(0, value(toks[b]))
            b -= 1
        for c in cats:
            out["_seen"][c] = 1.0
        n = 6 * len(cats)
        if cats and len(vals) >= n:
            vals = vals[-n:]
            for grid in ([[vals[s * len(cats) + c] for s in range(6)] for c in range(len(cats))],
                         [[vals[c * 6 + s] for s in range(6)] for c in range(len(cats))]):
                if all(abs(sum(row) - 100) <= 0.6 for row in grid):
                    for c, name in enumerate(cats):
                        out.setdefault(name, dict(zip(RELIGIONS, grid[c])))
                    break
        i = max(k, i + 1)
    return out


def row_values(tokens: list[str], want: int) -> list[float] | None:
    """The row's figures: as printed, or with a whole number and the figure
    after it joined ("10 0,0" for 100,0) where that alone makes the count and
    every both-sexes figure lies between the men's and the women's."""
    vals = [value(t) for t in tokens]

    def fits(v: list[float]) -> bool:
        return len(v) == want and all(
            min(v[t], v[t + 1]) - 0.15 <= v[t + 2] <= max(v[t], v[t + 1]) + 0.15
            for t in range(0, want, 3))

    if fits(vals):
        return vals
    extra = len(vals) - want
    if not 0 < extra <= 2:
        return None
    found = []
    joinable = [t for t in range(len(tokens) - 1)
                if tokens[t].isdigit() and "," in tokens[t + 1]]
    from itertools import combinations
    for picks in combinations(joinable, extra):
        if any(b - a < 2 for a, b in zip(picks, picks[1:])):
            continue
        merged, t = [], 0
        while t < len(tokens):
            if t in picks:
                merged.append(value(tokens[t] + tokens[t + 1]))
                t += 2
            else:
                merged.append(value(tokens[t]))
                t += 1
        if fits(merged):
            found.append(merged)
    return found[0] if len(found) == 1 else None


def language_table(text: str, provinces: list[str]) -> dict[str, dict[str, float]]:
    """{province or "Ensemble": {language: % of residents aged 3 and over}} from
    the table of principal languages spoken by sex and province (Tableau 3.3; in
    Nord, 3.3 and 3.4). Each block names its provinces (and the region's total)
    in a heading, then each row a language and, for each column, men, women and
    both: the both-sexes figure must lie between the other two, and each column
    must make 100 within the table's rounding."""
    flat = re.sub(r"\s+", " ", text)
    folded_at = []                      # positions of each title in flat
    for m in re.finditer(r"(?i)par\s+sexe\s+et\s+(?:la\s+|par\s+)?province", flat):
        before = fold(flat[max(0, m.start() - 160):m.start()])
        if "langue" in before or "langu" in before:
            folded_at.append(m.end())
    out: dict[str, dict[str, float]] = {}
    for start in folded_at:
        stop = len(flat)
        for pat in (r"Tableau\s*3\s*\.?\s*[4-9]\s*:", r"Graphique\s*3", r"Source\s*:"):
            m = re.compile(pat).search(flat, start)
            if m and m.start() < stop:
                stop = m.start()
        toks = tokens_of(flat[start:stop])
        i = 0
        while i < len(toks):
            # A heading: the block's columns, then the sexes.
            cols: list[str] = []
            scanned = 0
            while i < len(toks) and scanned < 80:
                scanned += 1
                if is_number(toks[i]):
                    if cols:
                        break
                    i += 1                 # a page number or the running head's year
                    continue
                key = fold(toks[i])
                p = province_of(toks[i], provinces)
                if p and p not in cols:
                    cols.append(p)
                elif key in TOTALS and cols:
                    cols.append("Ensemble")
                elif key in SEXES or key in HEADING or key == "":
                    pass
                elif cols:
                    break                  # the first language's label
                i += 1
            if not cols:
                break
            want = 3 * len(cols)
            sums = [0.0] * len(cols)
            block: dict[str, dict[str, float]] = {c: {} for c in cols}
            ended = False
            while i < len(toks):
                label = []
                while i < len(toks) and not is_number(toks[i]):
                    label.append(toks[i])
                    i += 1
                figures = []
                while i < len(toks) and is_number(toks[i]):
                    figures.append(toks[i])
                    i += 1
                text_label = " ".join(label)
                if fold(text_label) in TOTALS or fold(text_label).startswith(("total",
                                                                              "ensemble")):
                    ended = True
                    break
                if (not fold(text_label) or "rgph" in fold(text_label)
                        or "monographie" in fold(text_label)) and len(figures) < want:
                    continue               # a page's rule, running head or number
                vals = row_values(figures, want)
                if vals is None:
                    log(f"    a row not read: {text_label!r} {' '.join(figures)}")
                    block = {}
                    break
                name = language_name(text_label)
                if name is None:
                    # A block that runs over a page repeats its heading there
                    # ("Principales langues par- lées Noumbiel Ensemble M F ...
                    # Dyan"): the heading's words go, the language stays.
                    for k in range(1, len(label)):
                        if all(fold(t) in HEADING | SEXES | {"", "par", "lees"}
                               or province_of(t, provinces) or fold(t) in TOTALS
                               for t in label[:k]):
                            name = language_name(" ".join(label[k:]))
                            if name:
                                break
                if name is None:
                    log(f"    a language not named: {text_label!r}")
                    block = {}
                    break
                for c, col in enumerate(cols):
                    block[col][name] = block[col].get(name, 0.0) + vals[3 * c + 2]
                    sums[c] += vals[3 * c + 2]
            if not ended or not block or any(abs(s - 100) > 1.5 for s in sums):
                log(f"    a block of {cols} not taken (sums {[round(s, 1) for s in sums]})")
                break
            for col in cols:
                out.setdefault(col, block[col])
    return out


def region_languages(text: str) -> dict[str, float]:
    """The region's principal languages, Tableau 3.2's last column (all residents
    of both sexes): for a region of one province, the province's."""
    flat = re.sub(r"\s+", " ", text)
    # The title is also in the list of tables: each place it stands is tried.
    for m in re.finditer(r"(?i)principales?\s+langues?\s+parl\s*[ée]es?\s+selon\s+le\s+milieu",
                         flat):
        stop = re.compile(r"Tableau\s*3\s*\.?\s*[3-9]\s*:|Source\s*:|Graphique").search(
            flat, m.end())
        found = residence_languages(tokens_of(flat[m.end():stop.start() if stop else len(flat)]))
        if found:
            return found
    return {}


def residence_languages(toks: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    i = 0
    while i < len(toks):
        label = []
        while i < len(toks) and not is_number(toks[i]):
            label.append(toks[i])
            i += 1
        figures = []
        while i < len(toks) and is_number(toks[i]):
            figures.append(value(toks[i]))
            i += 1
        text_label = " ".join(label)
        if fold(text_label).startswith(("total", "ensemble")) and figures:
            break
        # The first row's label follows the heading's words: its longest
        # ending that names a language is the label.
        name = next((n for k in range(len(label))
                     for n in [language_name(" ".join(label[k:]))] if n), None)
        if name and len(figures) in (3, 6, 9):
            out[name] = out.get(name, 0.0) + figures[-1]
    return out if out and abs(sum(out.values()) - 100) <= 1.5 else {}


def region_religion(text: str) -> dict[str, float]:
    """The region's religions, Tableau 3.1's last column (both sexes)."""
    flat = re.sub(r"\s+", " ", text)
    for m in re.finditer(r"(?i)par\s+religion\s+selon\s+le\s+sexe", flat):
        found = sex_religions(tokens_of(flat[m.end():m.end() + 600]))
        if found:
            return found
    return {}


def sex_religions(toks: list[str]) -> dict[str, float]:
    labels = {"animiste": "Animist", "musulman": "Islam", "catholique": "Catholic",
              "protestant": "Protestant", "autre": "Other religion", "autres": "Other religion",
              "sansreligion": "No religion"}
    out: dict[str, float] = {}
    i = 0
    while i < len(toks) and len(out) < 6:
        label = []
        while i < len(toks) and not is_number(toks[i]):
            label.append(toks[i])
            i += 1
        figures = []
        while i < len(toks) and is_number(toks[i]):
            figures.append(value(toks[i]))
            i += 1
        name = labels.get(fold(" ".join(label[-2:]))) or labels.get(fold(label[-1]) if label
                                                                   else "")
        if name and len(figures) == 3:
            out[name] = figures[-1]
    return out if len(out) == 6 and abs(sum(out.values()) - 100) <= 0.6 else {}


def read(region: str) -> tuple[str, str]:
    from pypdf import PdfReader

    for path in MONOGRAPHS[region]:
        url = BASE + path
        try:
            blob = fetch_blob(url)
        except Exception as err:  # noqa: BLE001 -- the next name is tried
            log(f"  {region}: {url}: {type(err).__name__}: {err}")
            continue
        if blob.startswith(b"%PDF"):
            log(f"  {region}: read {url}: {len(blob):,} bytes, sha256 "
                f"{hashlib.sha256(blob).hexdigest()}")
            reader = PdfReader(io.BytesIO(blob))
            return url, "\f".join((p.extract_text() or "") for p in reader.pages[:70])
    return "", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.add_argument("--dump", default="", help="log each monograph's pages on religion and "
                    "languages by province instead of writing anything (a label)")
    args = ap.parse_args()
    admin1 = json.loads((SITE / "admin1" / "BFA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "BFA.units.json").read_text())
    regions = {u["id"]: u["name"] for u in admin1}
    provinces: dict[str, list[dict[str, Any]]] = {}
    for u in admin2:
        provinces.setdefault(regions[u["parent"]], []).append(u)
    if args.dump:
        for region, shapes in sorted(provinces.items()):
            url, text = read(region)
            names = [fold(s["name"]) for s in shapes]
            for n, page in enumerate(text.split("\f")):
                flat = fold(page)
                about = ("religion" in flat or "musulman" in flat or "langue" in flat)
                if about and sum(1 for name in names if name in flat) >= min(2, len(names)):
                    log(f"=== {region} page {n + 1} ===")
                    log(page[:5000])
        return 0
    records = []
    shape_of = {u["name"]: u for u in admin1}
    for region, shapes in sorted(provinces.items()):
        url, text = read(region)
        if not text:
            log(f"  {region}: no monograph read; its provinces are left as they are")
            continue
        records += region_records(region, shapes, shape_of.get(region), url, text)
    n2 = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {n2} provinces and {len(records) - n2} regions written")
    write_json(PROCESSED / OUT, records)
    return 0


def listed(shares: dict[str, float]) -> list[dict[str, Any]]:
    """Shares as the map lists them, largest first, those printed as nought left out."""
    return [{"group": g, "pct": round(p, 1)}
            for g, p in sorted(shares.items(), key=lambda kv: (-kv[1], kv[0])) if p > 0]


def region_records(region: str, shapes: list[dict[str, Any]], shape: dict[str, Any] | None,
                   url: str, text: str) -> list[dict[str, Any]]:
    """The region's provinces (sex ratio, religion, language) and the region itself
    (language), from its monograph's text."""
    names = [s["name"] for s in shapes]
    monograph = (f"{PUBLISHER}, Cinquième Recensement Général de la Population et de "
                 f"l'Habitat (RGPH) 2019, Monographie de la région {region}")
    table = None
    try:
        if len(shapes) == 1:
            table = {names[0]: regional_total(text)}
            where = "Tableau 2.1, the region's count, the province being the whole region"
        else:
            try:
                count = regional_total(text)
            except SystemExit:
                count = None
            table = province_table(text, names, count)
            where = "Tableau 2.3, population by province and sex"
    except SystemExit as err:
        log(f"  {region}: {err}; its provinces keep the sex ratio they had")
        where = ""
    if len(shapes) == 1:
        own_religion = region_religion(text)
        religions = {names[0]: own_religion} if own_religion else {}
        region_language = region_languages(text)
        languages = {names[0]: region_language} if region_language else {}
    else:
        religions = religion_charts(text, names)
        charted = set(religions.pop("_seen"))
        languages = language_table(text, names)
        region_language = languages.get("Ensemble") or region_languages(text)
    log(f"  {region}: religion for {sorted(n for n in religions if n in names)}, languages "
        f"for {sorted(n for n in languages if n in names)}, the region's languages "
        f"{'read' if region_language else 'not read'}")
    one = len(shapes) == 1
    out = []
    for s in shapes:
        name = s["name"]
        fields: dict[str, Any] = {}
        sources = []
        if table:
            men, women, total = table[name]
            log(f"    {name}: {men:,} men, {women:,} women, {total:,}")
            fields["sex_ratio"] = measure(round(1000 * men / women),
                                          unit="males_per_1000_females", year=YEAR,
                                          source=f"{monograph} ({where})")
            fields["sex_ratio_note"] = (f"The 2019 census's count of the province: {men:,} men "
                                        f"and {women:,} women.")
            sources.append({"field": "sex_ratio", "name": f"{monograph} ({where})", "url": url,
                            "license": LICENCE, "year": YEAR})
        if name in religions:
            what = ("Tableau 3.1, the region's religions, the province being the whole region"
                    if one else "Graphique 3.2, the religions of each province")
            fields["religion"] = listed(religions[name])
            fields["religion_year"] = YEAR
            fields["religion_note"] = (
                "The 2019 census's shares of the province's residents by religion, as the "
                "monograph of the region " + ("tabulates them for the region, which is this "
                                              "one province." if one else
                                              "charts them by province, to one decimal."))
            sources.append({"field": "religion", "name": f"{monograph} ({what})", "url": url,
                            "license": LICENCE, "year": YEAR})
            log(f"      religion: {listed(religions[name])[:3]}")
        elif not one and not charted & set(names):
            # No chart of the region labels any province: the chart is a picture.
            fields["religion"] = gap(NOT_AVAILABLE, (
                f"The 2019 census's monograph of the {region} region charts religion by "
                "province (Graphique 3.2) without printing the figures, and tabulates it for "
                "the region only (Tableau 3.1)."))
        if name in languages:
            what = ("Tableau 3.2, the region's languages, the province being the whole region"
                    if one else "Tableau 3.3, principal languages spoken by sex and province")
            fields["language"] = listed(languages[name])
            fields["language_year"] = YEAR
            fields["language_note"] = (
                "The principal language usually spoken by the province's residents aged 3 and "
                "over, in the 2019 census" + (", as the monograph tabulates it for the region, "
                                              "which is this one province." if one else
                                              ", as the monograph of the region tabulates it "
                                              "by province."))
            sources.append({"field": "language", "name": f"{monograph} ({what})", "url": url,
                            "license": LICENCE, "year": YEAR})
            log(f"      language: {listed(languages[name])[:3]}")
        if fields:
            out.append(record(f"BFA-RGPH2019-{fold(name)}", name, level="admin2", parent="BFA",
                              country="BFA", match_by="shape_id", shape_id=s["id"],
                              sources=sources, **fields))
    if shape and region_language:
        what = ("Tableau 3.3, principal languages spoken by sex and province, the region's "
                "column" if languages.get("Ensemble") else
                "Tableau 3.2, principal language spoken by residence")
        out.append(record(
            f"BFA-RGPH2019-region-{fold(region)}", region, level="admin1", parent="BFA",
            country="BFA", match_by="shape_id", shape_id=shape["id"],
            language=listed(region_language), language_year=YEAR,
            language_note=("The principal language usually spoken by the region's residents "
                           "aged 3 and over, in the 2019 census, as its monograph tabulates it."),
            sources=[{"field": "language", "name": f"{monograph} ({what})", "url": url,
                      "license": LICENCE, "year": YEAR}]))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
