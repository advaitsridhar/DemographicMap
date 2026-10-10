#!/usr/bin/env python3
"""Zambia -- the 2022 census's final counts, by district and province.

The Zambia Statistics Agency published preliminary results of the 2022 Census
of Population and Housing first (19,610,769 people) and the final count later
(19,693,423). Summary Report Volume II, Table 5.2, prints the de jure
population by sex and by rural and urban residence for the country, every
province, district, constituency and ward. The district and province lines
are read here, from the table's pages only; a line reads

    SHANG'OMBO DISTRICT 74,654 ...  (total, male, female, then rural and urban
                                     each as total, male, female; "-" is none)

**Checks before anything is written.** Each line's men and women make its
total, and its rural and urban parts make it too; each province's districts
make the province; the provinces make the national line, which must be the
final count.

**Binding.** Districts are matched to the map's second level by name across
the whole country, since district names are unique and the boundary file files
a few districts under a different province from the census's (Chama, Chirundu,
Itezhi-Tezhi). ALIASES holds the spellings no reduction joins; a label still
left over is paired only with its mutually closest census name. A first-level
polygon gets its province's count when the districts drawn in it are exactly
the census's districts of that province; where the boundary file draws a
district under another province, the polygon gets the sum of the districts
drawn in it, all from the same table, and says so.

Usage:
    python -m scripts.fetch_census.zambia_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

URL = ("https://www.zamstats.gov.zm/Publications/Revised%202022%20Census%20of%20Population"
       "%20and%20Housing%20Summary%20Report%20Volume%20II.pdf")
SOURCE = ("Zambia Statistics Agency, 2022 Census of Population and Housing, final results "
          "(Summary Report Volume II, Table 5.2)")
LICENCE = "Zambia Statistics Agency publication (reuse with attribution)"
YEAR = 2022
NATIONAL = 19_693_423
PAGES = range(40, 140)               # 1-based; the table is read where its title is
TITLE = "TABLE 5.2"
OUT = "zambia_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The boundary file's reduced label -> the census's.
ALIASES = {
    "chikankanta": "chikankata",
    "chiengi": "chienge",
    "milengi": "milenge",
    "mushindano": "mushindamo",
    "ikelenge": "ikelengi",
}
SPELLING = 0.85

NUM = r"(?:\d{1,3}(?:,\d{3})*|-)"
LINE = re.compile(rf"^(?P<name>.*?[A-Z].*?)\s+(?P<nums>{NUM}(?:\s+{NUM}){{8}})\s*$")


def norm(name: str) -> str:
    """A name reduced to its letters, without DISTRICT or PROVINCE."""
    text = re.sub(r"(?i)\b(?:district|province)\b", " ", str(name or ""))
    return "".join(c for c in text.lower() if "a" <= c <= "z")


def key(name: str) -> str:
    k = norm(name)
    return ALIASES.get(k, k)


def numbers(text: str) -> list[int]:
    return [0 if part == "-" else int(part.replace(",", "")) for part in text.split()]


def parse(lines: list[str]) -> dict[str, Any]:
    """{"national": row, "provinces": {key: row}, "districts": {key: row}} from
    the table's lines, each row with its name, total, men, women and province."""
    out: dict[str, Any] = {"national": None, "provinces": {}, "districts": {}}
    province = None
    for line in lines:
        hit = LINE.match(line.strip())
        if not hit:
            continue
        name = hit.group("name").strip()
        upper = name.upper()
        total, men, women, rt, rm, rw, ut, um, uw = numbers(hit.group("nums"))
        if men + women != total or rt + ut != total or rm + um != men or rw + uw != women:
            raise SystemExit(f"zambia_census: {name}: its parts do not make {total:,}")
        row = {"name": name, "total": total, "men": men, "women": women}
        if upper.startswith("ZAMBIA"):
            if out["national"] not in (None, row):
                raise SystemExit("zambia_census: the national line is printed two ways")
            out["national"] = row
        elif re.search(r"\bPROVINCE\b", upper):
            province = key(name)
            if out["provinces"].get(province, row) != row:
                raise SystemExit(f"zambia_census: {name} is printed two ways")
            out["provinces"][province] = row
        elif re.search(r"\bDISTRICT\b", upper):
            if province is None:
                raise SystemExit(f"zambia_census: {name} comes before any province")
            row["province"] = province
            k = key(name)
            if out["districts"].get(k, row) != row:
                raise SystemExit(f"zambia_census: {name} is printed two ways")
            out["districts"][k] = row
    check(out)
    return out


def check(table: dict[str, Any]) -> None:
    national = table["national"]
    if national is None or national["total"] != NATIONAL:
        raise SystemExit(f"zambia_census: the national line is {national}, not the final "
                         f"count {NATIONAL:,}")
    made = sum(p["total"] for p in table["provinces"].values())
    if made != NATIONAL:
        raise SystemExit(f"zambia_census: the provinces make {made:,}")
    for k, province in table["provinces"].items():
        rows = [d for d in table["districts"].values() if d["province"] == k]
        for field in ("total", "men", "women"):
            if sum(d[field] for d in rows) != province[field]:
                raise SystemExit(f"zambia_census: {province['name']}'s {len(rows)} districts "
                                 f"do not make its {field}")


def read(blob: bytes) -> dict[str, Any]:
    import pdfplumber                               # noqa: PLC0415
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for number in PAGES:
            if number > len(pdf.pages):
                break
            text = pdf.pages[number - 1].extract_text() or ""
            if TITLE not in text.upper():
                continue
            lines += text.splitlines()
    return parse(lines)


def fields(row: dict[str, Any], note: str) -> dict[str, Any]:
    return {"population": measure(row["total"], year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * row["men"] / row["women"]),
                                 unit="males_per_1000_females", year=YEAR, source=SOURCE),
            "sources": [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                         "license": LICENCE, "year": YEAR}]}


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def bind_districts(table: dict[str, Any], admin2: list[dict[str, Any]]
                   ) -> tuple[dict[str, str], list[str]]:
    """{shape id: census district key} and a report."""
    report: list[str] = []
    bound: dict[str, str] = {}
    taken: set[str] = set()
    left = []
    for shape in admin2:
        k = key(shape["name"])
        if k in table["districts"] and k not in taken:
            bound[shape["id"]] = k
            taken.add(k)
        else:
            left.append(shape)
    spare = [k for k in table["districts"] if k not in taken]
    for shape in left:
        k = key(shape["name"])
        best = max(spare, key=lambda d: ratio(k, d), default=None)
        if best is None or ratio(k, best) < SPELLING:
            report.append(f"{shape['name']!r} ({k}): no census district")
            continue
        back = max(left, key=lambda s: ratio(key(s["name"]), best))
        if back is not shape:
            report.append(f"{shape['name']!r}: {best} is closer to {back['name']!r}")
            continue
        bound[shape["id"]] = best
        spare.remove(best)
        report.append(f"{shape['name']!r} bound to {table['districts'][best]['name']!r} "
                      "by spelling")
    report.append("census districts not drawn: "
                  f"{[table['districts'][k]['name'] for k in spare]}")
    return bound, report


def joined(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def summed_note(province: str, n: int, extra: list[tuple[str, str]],
                missing: list[tuple[str, str]]) -> str:
    """What a first-level polygon's added-up count covers. ``extra``: (district,
    the census's province for it); ``missing``: (district, the polygon it is
    drawn in)."""
    text = (f"The 2022 census's final counts for the {n} districts drawn here, added up: "
            f"{province} Province's districts")
    if missing:
        where = {p for _, p in missing}
        if len(where) == 1:
            text += (f" other than {joined([d for d, _ in missing])}, which this map draws "
                     f"under {where.pop()}")
        else:
            text += " other than " + joined([f"{d} (drawn under {p})" for d, p in missing])
    if extra:
        where = {p for _, p in extra}
        if len(where) == 1:
            text += (f"{',' if missing else ''} and {joined([d for d, _ in extra])}, which "
                     f"the census counts under {where.pop()} Province")
        else:
            text += (f"{',' if missing else ''} and "
                     + joined([f"{d} (counted under {p} Province)" for d, p in extra]))
    return text + "."


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    bound, report = bind_districts(table, admin2)
    drawn: dict[str, list[str]] = defaultdict(list)
    label: dict[str, str] = {}
    polygon: dict[str, str] = {}
    first = {shape["id"]: shape["name"] for shape in admin1}
    for shape in admin2:
        k = bound.get(shape["id"])
        if k is None:
            drawn[shape["parent"]].append("")
            continue
        row = table["districts"][k]
        drawn[shape["parent"]].append(k)
        label[k] = shape["name"]
        polygon[k] = first.get(shape["parent"], "")
        records.append(record(
            f"ZMB-2022-{k}", shape["name"], level="admin2", parent="ZMB", country="ZMB",
            match_by="shape_id", shape_id=shape["id"],
            **fields(row, f"The 2022 census's final count for {shape['name']} district.")))
    names = {key(p["name"]): k for k, p in table["provinces"].items()}
    census_name = {k: label.get(k) for k in table["districts"]}
    for shape in admin1:
        k = names.get(key(shape["name"]))
        here = drawn.get(shape["id"], [])
        if k is None or not here or "" in here:
            report.append(f"province polygon {shape['name']!r}: not every district drawn in it "
                          "is bound; nothing written")
            continue
        own = sorted(d for d, row in table["districts"].items() if row["province"] == k)
        if sorted(here) == own:
            row = table["provinces"][k]
            note = f"The 2022 census's final count for {shape['name']} Province."
        else:
            rows = [table["districts"][d] for d in here]
            row = {"total": sum(r["total"] for r in rows), "men": sum(r["men"] for r in rows),
                   "women": sum(r["women"] for r in rows)}
            province_of = {key(p["name"]): s["name"] for s in admin1
                           for p in table["provinces"].values() if key(p["name"]) == key(s["name"])}
            extra = [(census_name[d] or d, province_of.get(table["districts"][d]["province"], ""))
                     for d in sorted(set(here) - set(own))]
            missing = [(census_name[d] or d, polygon.get(d) or "another province")
                       for d in sorted(set(own) - set(here))]
            note = summed_note(shape["name"], len(here), extra, missing)
            report.append(f"province polygon {shape['name']!r}: the sum of its drawn districts "
                          f"({row['total']:,}): {note}")
        records.append(record(f"ZMB-2022-{k}", shape["name"], level="admin1", parent="ZMB",
                              country="ZMB", match_by="shape_id", shape_id=shape["id"],
                              **fields(row, note)))
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"zambia_census: {URL} is not a PDF: {blob[:80]!r}")
    table = read(blob)
    log(f"  {len(table['provinces'])} provinces and {len(table['districts'])} districts, "
        f"making {table['national']['total']:,}")
    admin1 = json.loads((SITE / "admin1" / "ZMB.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "ZMB.units.json").read_text())
    records, report = build(table, admin1, admin2)
    for line in report:
        log("  " + line)
    for k in ("shangombo", "senanga", "sesheke", "western"):
        row = table["districts"].get(k) or table["provinces"].get(k)
        if row:
            log(f"  {row['name']}: {row['total']:,}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin2')} of {len(admin2)} districts "
        f"and {sum(1 for r in records if r['level'] == 'admin1')} of {len(admin1)} provinces "
        "written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
