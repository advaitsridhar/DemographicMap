#!/usr/bin/env python3
"""Moldova's seven units without an ethnic composition, read where Wikipedia has one.

The Europe reader (europe_wiki.py) reads Moldova from each district's English
article, which carries the 2024 census table for thirty of its thirty-seven
units, and it refused the other seven in writing. By the owner's decision
of 22 September 2026 -- use the figures Wikipedia has; where the table cites
nothing, cite the article; where it is undated, say so -- five of those
refusals do not stand. The seven, and what this reads for each:

* Edinet, Falesti, Glodeni, Riscani. The English articles have no table; the
  Romanian ones have an ethnic structure table each, under "Structura
  etnica", of counts. Riscani's cites the 2004 census spreadsheet and is
  dated 2004. The other three cite nothing and name no year, so they are
  read and said to be undated -- not dated by inference from what their
  totals happen to match.
* Bender. The Transnistria article's table of administrative divisions gives
  each district's ethnic composition from Transnistria's own 2004 census,
  Bender among them. It is not the 2024 Moldovan census, which did not reach
  Bender, and the record says whose count it is.
* Transnistria. The map's shape is the left bank without Bender, which is
  six of the table's rows. Their shares are combined weighted by the same
  table's 2025 populations, because the table gives no 2004 ones -- which
  assumes the districts' relative sizes have held since 2004. That is an
  assumption, so the result is a modelled estimate, marked and hatched as
  one, and never a reading.
* Balti. Read from the Romanian article if it has the table; otherwise left
  as the gap it is, with the reason.

Two things in the tables are not what they look like. Falesti gives
"Moldoveni/Romani" as one row, which is one figure for two answers and is
written that way ("Moldovan or Romanian") rather than folded into either.
Riscani welds two rows into one cell -- "Moldoveni Romani 1 | 50.391 777 |
72,55% 1,12%", Moldovans and then Romanians -- and is split back into them
where the names, the counts and the shares line up one to one.

Shares are computed from the counts where the table gives counts, because
the counts are what the census published and Edinet's table leaves one
share blank.

Usage:
    python -m scripts.fetch_census.moldova_gaps
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, read_json, write_json
from .europe_wiki import fetch, sections

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import MODELLED, estimate  # noqa: E402
from probe_wikitable import tables  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = "moldova_ethnicity_gaps.json"

DISTRICTS = {
    "Edinet": "Raionul Edineț",
    "Falesti": "Raionul Fălești",
    "Glodeni": "Raionul Glodeni",
    "RIscani": "Raionul Rîșcani",
    "Balti": "Bălți",
}

# The Romanian tables' labels, as the Europe reader writes the same groups for
# the thirty districts it reads -- so a map at "as reported" puts the seven
# beside the thirty in the same words.
RO_ETHNIC = {
    "moldoveni": "Moldovan", "romani": "Romanian", "ucraineni": "Ukrainian",
    "rusi": "Russian", "tigani": "Romani", "romi": "Romani",
    "gagauzi": "Gagauz", "bulgari": "Bulgarian", "polonezi": "Polish",
    "evrei": "Jewish", "belarusi": "Belarusian", "germani": "German",
    "armeni": "Armenian", "altii": "Other", "alte": "Other",
    "moldoveni/romani": "Moldovan or Romanian",
    "nedeclarat": "Not declared", "nedeclarata": "Not declared",
}

# Rows of a table that are not groups: a sub-header, the total, and the
# citation some articles put in a row of its own under the table.
NOT_A_GROUP = {"numar", "total", "totallocuitori"}

TRANSNISTRIA = "Transnistria"
TR_LABELS = {"moldovans": "Moldovan", "ukrainians": "Ukrainian",
             "russians": "Russian", "others": "Other"}
LEFT_BANK = ("Camenca", "Rîbnița", "Dubăsari", "Grigoriopol", "Slobozia", "Tiraspol")


def fold(text: str) -> str:
    text = text.lower().replace("ș", "s").replace("ş", "s").replace("ț", "t")
    text = text.replace("ţ", "t").replace("ă", "a").replace("â", "a").replace("î", "i")
    return re.sub(r"[^a-z/]", "", text)


def count(text: str) -> int | None:
    """A whole number grouped any way: "59.195", "76&nbsp;169", "21,000"."""
    digits = re.sub(r"&nbsp;|[^0-9]", "", text or "")
    body = re.sub(r"&nbsp;|[\s.,\u00a0\u202f]", "", text or "")
    return int(digits) if digits and digits == body else None


def welded(row: list[str]) -> list[list[str]]:
    """A row that carries two groups in each of its cells, split back into two.

    Only where every cell splits into the same number of parts: names, counts
    and shares must line up one to one or the row is left as it is.
    """
    if len(row) < 2:
        return [row]
    names = [w for w in row[0].split() if not w.isdigit()]
    counts = (row[1] or "").split()
    if len(names) < 2 or len(names) != len(counts):
        return [row]
    shares = (row[2].split() if len(row) > 2 else [])
    if shares and len(shares) != len(names):
        return [row]
    return [[names[i], counts[i], *([shares[i]] if shares else [])]
            for i in range(len(names))]


def ro_table(wikitext: str) -> tuple[list[list[str]], str]:
    """The ethnic structure table, header included, and the text of its section."""
    for heading, body in sections(wikitext):
        if "etnic" in fold(heading):
            for table in tables(body):
                if table and "grup" in fold(table[0][0] if table[0] else ""):
                    return table, body
    return [], ""


def latest(header: list[str]) -> tuple[int | None, int]:
    """The newest census a table's header names, and the column of its count.

    Balti's table gives every census from 1959 to 2024, a count and a share
    for each, so the count for the k-th year is column 1 + 2k. A table with
    one set of figures and no years in its header is read from column 1.
    """
    years = [(k, int(c)) for k, c in enumerate(y for y in header[1:]
                                               if re.fullmatch(r"(?:19|20)\d\d", y.strip()))]
    if len(years) < 2:
        return None, 1
    k, year = max(years, key=lambda kv: kv[1])
    return year, 1 + 2 * k


def ro_composition(rows: list[list[str]], column: int = 1
                   ) -> tuple[list[dict[str, Any]] | None, str]:
    counts: dict[str, int] = {}
    unknown = []
    for raw in rows:
        if not raw or fold(raw[0]) in NOT_A_GROUP or raw[0].lstrip().startswith(("[", "http")):
            continue
        for row in (welded(raw) if column == 1 else [raw]):
            label = RO_ETHNIC.get(fold(row[0]))
            n = count(row[column]) if len(row) > column else None
            if label is None:
                unknown.append(row[0])
                continue
            if n is not None:
                counts[label] = counts.get(label, 0) + n
    if unknown:
        return None, f"labels this reader has no entry for: {unknown}"
    total = sum(counts.values())
    if not total:
        return None, "no counts"
    rows_out = [{"group": g, "pct": round(100 * n / total, 2), "count": n}
                for g, n in counts.items()]
    rows_out.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows_out, ""


def year_of(body: str) -> int | None:
    """The census year the section's own citation names, if it names one."""
    for ref in re.findall(r"<ref[^>]*>(.*?)</ref>", body, re.S):
        m = re.search(r"[Rr]ecens[aă]m[aâ]ntul[^'|]*?((?:19|20)\d\d)", ref)
        if m:
            return int(m.group(1))
    return None


def shapes() -> dict[tuple[str, str], str]:
    """(level, name) -> shape id, for Moldova's polygons at both levels."""
    out = {}
    for level in ("admin1", "admin2"):
        for u in read_json(ROOT / "site" / "data" / level / "MDA.json", []):
            out[(level, u["name"])] = u["id"]
    return out


def row_for(name: str, level: str, shape: str, value: Any, *, year: int | None,
            note: str, source: str, url: str) -> dict[str, Any]:
    row = {"id": f"MDA-gap-{level}-{name.lower()}", "level": level, "name": name,
           "parent": "MDA", "country": "MDA", "shape_id": shape, "match_by": "shape_id",
           "ethnicity": value, "ethnicity_note": note,
           "sources": [{"field": "ethnicity", "name": source, "url": url,
                        "license": "CC BY-SA 4.0"}]}
    if year and isinstance(value, list):
        row["ethnicity_year"] = year
    return row


def transnistria() -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Each district's 2004 shares, and its 2025 population, from the article."""
    text, _ = fetch("Transnistria", "en")
    shares: dict[str, list[dict[str, Any]]] = {}
    people: dict[str, int] = {}
    for heading, body in sections(text):
        if "administrative divisions" not in heading.lower():
            continue
        for table in tables(body):
            for row in table[1:]:
                if len(row) < 5:
                    continue
                name = row[0].split("(")[0].replace("District", "").replace("City of", "").strip()
                comp = []
                for pct, label in re.findall(r"([\d.]+)%\s*([A-Za-z]+)", row[4]):
                    group = TR_LABELS.get(label.lower())
                    if group:
                        comp.append({"group": group, "pct": float(pct)})
                if comp:
                    shares[name] = comp
                    people[name] = count(row[3]) or 0
    return shares, people


def main() -> int:
    ids = shapes()
    rows: list[dict[str, Any]] = []
    for name, title in DISTRICTS.items():
        text, landed = fetch(title, "ro")
        url = f"https://ro.wikipedia.org/wiki/{urllib.parse.quote(landed.replace(' ', '_'))}"
        table, body = ro_table(text)
        if not table:
            log(f"{name}: ro:{landed} has no ethnic structure table; left as it was")
            continue
        column_year, column = latest(table[0])
        comp, why = ro_composition(table[1:], column)
        if comp is None:
            log(f"{name}: ro:{landed}: {why}; left as it was")
            continue
        year = column_year or year_of(body)
        dated = (f"for {year}, the newest of the censuses its columns give" if column_year
                 else f"for {year}, from the census its citation names" if year
                 else "with no year: the table names none and cites nothing that does")
        note = (f"Ethnic structure as the ro.wikipedia article '{landed}' gives it, "
                f"{dated}. Shares computed from the table's own counts. Not the 2024 "
                f"census the neighbouring districts are read from, which the English "
                f"article for this district does not transcribe.")
        log(f"{name}: {comp[0]['group']} {comp[0]['pct']}%, {len(comp)} groups, "
            f"year {year or 'none stated'}")
        for level in ("admin1", "admin2"):
            if (level, name) in ids:
                rows.append(row_for(name, level, ids[(level, name)], comp, year=year,
                                    note=note, url=url,
                                    source=f"ro.wikipedia, '{landed}'"))

    shares, people = transnistria()
    url = "https://en.wikipedia.org/wiki/Transnistria"
    source = "Transnistria's 2004 census, as the en.wikipedia article 'Transnistria' tabulates it"
    bender = shares.get("Bender")
    if bender:
        note = ("Ethnic composition from Transnistria's own 2004 census, as the "
                "en.wikipedia article 'Transnistria' tabulates it by district. Bender "
                "is administered by Transnistria and the 2024 Moldovan census did not "
                "count it; this is the breakaway authority's count, not Moldova's.")
        for level in ("admin1", "admin2"):
            if (level, "Bender") in ids:
                rows.append(row_for("Bender", level, ids[(level, "Bender")], bender,
                                    year=2004, note=note, url=url, source=source))
        log(f"Bender: {bender}")
    else:
        log("Bender: not in the Transnistria article's table; left as it was")

    left = [d for d in LEFT_BANK if d in shares and people.get(d)]
    if len(left) == len(LEFT_BANK):
        weight = sum(people[d] for d in left)
        total: dict[str, float] = {}
        for d in left:
            for r in shares[d]:
                total[r["group"]] = total.get(r["group"], 0.0) + r["pct"] * people[d] / weight
        mix = sorted(({"group": g, "pct": round(v, 1)} for g, v in total.items()),
                     key=lambda r: -r["pct"])
        value = estimate(
            MODELLED, mix, method="district-weighted",
            inputs=[f"en.wikipedia 'Transnistria', {d}" for d in left],
            note=("Not read: nothing publishes the left bank without Bender. The "
                  "shares of Transnistria's six left-bank districts from its own "
                  "2004 census, combined weighted by the same table's 2025 "
                  "populations, which assumes the districts' relative sizes have "
                  "held since 2004. Breakaway authority's census; the 2024 Moldovan "
                  "census did not count this territory."))
        for level in ("admin1", "admin2"):
            if (level, TRANSNISTRIA) in ids:
                rows.append(row_for(TRANSNISTRIA, level, ids[(level, TRANSNISTRIA)], value,
                                    year=None, note=value["note"], url=url, source=source))
        log(f"Transnistria (modelled): {mix}")
    else:
        log(f"Transnistria: the table has {left} of the six left-bank districts; left as it was")

    write_json(PROCESSED / OUT, rows)
    log(f"wrote {len(rows)} records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
