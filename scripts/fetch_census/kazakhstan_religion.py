#!/usr/bin/env python3
"""Kazakhstan: religion by district, from the 2009 census's regional volumes.

The 2009 National Population Census published three volumes for each region.
Volume 2 ("Итоги Национальной переписи населения Республики Казахстан 2009
года", том 2) carries table 1.6, "Население районов по вероисповеданию": every
district and city akimat of the region by religion -- Islam, Christianity,
Judaism, Buddhism, other, non-believers, and those who declined to say -- in
people and in per cent, for both sexes, men and women.

It is the only religion below the region the Bureau has published. The 2021
census asked the question again, and its national volume (*National
composition, religion and language proficiency*, 2023) tabulates religion by
nationality, age and education, and by region; nothing finer.

**Reading the volumes.** The PDFs set their text in a font without a map to
characters, so a text extractor returns glyph names ('/g570' for 'А'); the
glyph numbers are the characters' own codes less a constant (29 below 128,
470 for Cyrillic), which ``decode`` adds back. Figures in narrow columns come
out glued together or split digit by digit ('13377424' for 13377, 4, 2 and 4;
'5 7 9' for 579), so each row's figures are read from its run of digits: the
one split into eight numbers whose seven religions make the total and agree,
to the printed tenth of a per cent, with the same row of the percentage
block. A row with no such split, or more than one, stops the run.

**Binding.** Districts and city akimats are placed on the drawn polygons by
``kazakhstan.place``, the rule the 2025 population and the 2021 census use:
by name, by a renaming, or onto the drawn polygon a city or a newer district
lies in, with the polygon taking the sum of its units. The 2009 districts
are close to the boundary file's own vintage, so few are pooled.

Usage:
    python -m scripts.fetch_census.kazakhstan_religion
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from . import kazakhstan as kz
from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, record, shares, write_json,
)

ISO3 = "KAZ"
YEAR = 2009
OUT = "kazakhstan_religion.json"
BASE = "https://stat.gov.kz/upload/medialibrary/"
# Volume 2 of each region, as the Bureau's 2009 census page lists them, by the
# drawn first-level region it covers.
VOLUMES = {
    "Akmola Region": "f2b/9y1vkc325pzgtx7e985e9qlwhml7sarg/Акмол обл рус 2 том.pdf",
    "West Kazakhstan Region":
        "2a1/20h6w5slvjq6v8xskotfxknttmuwrvi4/Западно-Казахстанская рус 2 том.pdf",
    "Mangystau Region": "791/mzn1o126w8lklnraxt9x48tioa4ze6bc/Мангистау рус 2 том.pdf",
    "Aktobe Region": "24d/8pe1bu3ba7itgxbpl18elhjeuwdwfik2/АКТОБЕ рус 2 том.pdf",
    "Atyrau Region": "06b/z2p5gyxoy3be10di46l10h1yzgsv2f6o/АТЫРАУ рус 2 том.pdf",
    "Karaganda Region": "42b/qwm2uqykx2ko6ci2kc3cu917sa1xa4nx/КАРАГАНДА рус 2 том.pdf",
    "Pavlodar Region": "5ff/oftpq1iuhaw53zz3ji35x3qbhkocpro5/ПАВЛОДАР рус 2 том.pdf",
    "Almaty Region": "6d1/t8ly1caqvv1j4lhvinbqi7ugd6z4wt96/Алматинская рус 2 том.pdf",
    "East Kazakhstan Region": "a70/cimw5we5grejsu0hc21ho2ycx2ecsc3v/ВКО рус 2 том.pdf",
    "Kostanay Region": "ea0/wwg71m4qdhs6lyp1y67esjr53huw1j8d/Костанайская рус 2 том.pdf",
    "North Kazakhstan Region": "4aa/ayccn4y0wmvs53brzbo4zcnzmjjasclf/СКО рус 2 том.pdf",
    "Almaty": "188/0tq86fys2d7l6w6te5qytjzdh2pewe0s/АЛМАТЫ рус 2 том.pdf",
    "Jambyl Region": "b1b/m12mrzc8hyzggq6swe2186cn1wnj1yxu/ЖАМБЫЛ рус 2 том.pdf",
    "Kyzylorda Region": "c79/72a6oy34qasxb6cdj79cix8odmid5uut/Кызылорда рус 2 том.pdf",
    "South Kazakhstan Region":
        "5ea/loipxc4bde42r32vnoqvi4sqyny3rhuv/Южно-Казахстанская рус 2 том.pdf",
}
# Astana's volume exists too; the map draws no second level there.
PAGE = "https://stat.gov.kz/ru/national/2009/region/"
SOURCE = ("Bureau of National Statistics of Kazakhstan (then the Agency of Statistics), "
          "2009 National Population Census, regional results, volume 2, table 1.6: "
          "population of districts by religion")
LICENCE = "Official statistics of the Bureau of National Statistics; free to use with attribution"
GROUPS = ("Islam", "Christianity", "Judaism", "Buddhism", "Other religions", "No religion",
          "Not stated")
NOTE = ("Religion the person named at the 2009 census: Islam, Christianity, Judaism, "
        "Buddhism, another religion, non-believer, or declined to say. The 2021 census's "
        "religion is published by region only.")
CITY_TOTAL = {"Almaty": "г.Алматы"}


def decode(text: str) -> str:
    """Glyph names back to characters (see the module's docstring)."""
    def char(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if 3 <= n <= 93:
            return chr(n + 29)
        if 570 <= n <= 633:
            return chr(n + 470)
        return ""
    return re.sub(r"/g(\d+)", char, text)


def volume_text(blob: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return decode("\n".join((page.extract_text() or "") for page in reader.pages))


START = re.compile(r"1\.6\s*Население\s+районов\s+по\s+вероисповеданию")
END = re.compile(r"(?m)^\s*2\.\s*(?:1\s+)?(?:ОБРАЗОВАТЕЛЬНЫЙ|Население\s+по\s+уровню)")
LINE = re.compile(r"^(?P<label>[^\d]*?)\s*(?P<figures>\d[\d\s,]*)$")


def section(text: str) -> str:
    starts = [m.end() for m in START.finditer(text)]
    if not starts:
        raise SystemExit("kazakhstan_religion: table 1.6 not found")
    # The contents page names the table too; the table is the last mention.
    body = text[starts[-1]:]
    end = END.search(body)
    return body[:end.start()] if end else body


def blocks(body: str) -> dict[tuple[str, str], dict[str, str]]:
    """{(sex, 'count'|'pct'): {label: figures}} in the order the table prints them."""
    out: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    sex, kind, pending = "both", "count", ""
    for raw in body.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        low = line.lower()
        if low.startswith("человек"):
            kind = "count"
        elif low.startswith("проценты"):
            kind = "pct"
        if "оба пола" in low:
            sex = "both"
        elif low.startswith("мужчины"):
            sex = "men"
        elif low.startswith("женщины"):
            sex = "women"
        m = LINE.match(line)
        if not m:
            # A label wrapped onto the next line ('Енбекшильдерский' / 'район ...').
            if re.search(r"(район|г\.а|акимат|[а-я]ский)$", low) or pending:
                pending = f"{pending} {line}".strip()
            continue
        label = f"{pending} {m.group('label')}".strip() if pending else m.group("label")
        pending = ""
        label = " ".join(label.split())
        # The running head ("Агентство Республики Казахстан по статистике 4 3")
        # ends in its page number and would read as a row.
        if (not label or "статистик" in label.lower()
                or label.lower().startswith(("из них", "продолжение"))):
            continue
        out[(sex, kind)].setdefault(label, m.group("figures"))
    return out


def percentages(figures: str) -> list[float] | None:
    """'100 41,7 48,1 ...' (or glued) -> the seven shares, or None."""
    s = re.sub(r"\s", "", figures)
    if not s.startswith("100"):
        return None
    parts = re.findall(r"\d+,\d", s[3:])
    if len(parts) != 7 or "".join(parts) != s[3:]:
        return None
    return [float(p.replace(",", ".")) for p in parts]


def counts(figures: str, pct: list[float] | None) -> list[int] | None:
    """The total and seven religions from a row's run of digits.

    Every split of the digits into eight numbers is tried; the one kept has
    the seven make the first and each within the printed share's rounding of
    it. More than one such split, or none, is no reading at all.
    """
    digits = re.sub(r"\D", "", figures)
    found: list[list[int]] = []

    def ok(text: str) -> bool:
        return text == "0" or not text.startswith("0")

    for k in range(1, min(8, len(digits)) + 1):
        if not ok(digits[:k]):
            continue
        total = int(digits[:k])
        if total <= 0:
            continue
        slack = 0.0006 * total + 1

        def walk(i: int, acc: list[int]) -> None:
            if len(acc) == 7:
                if i == len(digits) and sum(acc) == total:
                    found.append([total, *acc])
                return
            for j in range(i + 1, min(len(digits), i + 8) + 1):
                piece = digits[i:j]
                if not ok(piece):
                    break
                value = int(piece)
                if value > total:
                    break
                if pct is not None and abs(value - pct[len(acc)] * total / 100) > slack:
                    continue
                walk(j, acc + [value])

        walk(k, [])
    unique = {tuple(f) for f in found}
    return list(next(iter(unique))) if len(unique) == 1 else None


def unit_counts(body: str, region: str) -> dict[str, list[int]]:
    """{label: [total, seven religions]} for both sexes, every row read whole."""
    table = blocks(body)
    both, pct = table.get(("both", "count"), {}), table.get(("both", "pct"), {})
    out: dict[str, list[int]] = {}
    unread = []
    for label, figures in both.items():
        share = percentages(pct[label]) if label in pct else None
        row = counts(figures, share)
        if row is None:
            unread.append(f"{label}: {figures!r} / {pct.get(label)!r}")
            continue
        out[label] = row
    if unread:
        raise SystemExit(f"kazakhstan_religion: {region}: rows not read whole: {unread}")
    return out


def region_rows(rows: dict[str, list[int]], region: str) -> tuple[list[int], dict[str, list[int]]]:
    """(the region's own row, {unit: row}) with the units checked against it."""
    totals = [label for label in rows if label.lower().startswith("всего")]
    if len(totals) != 1:
        raise SystemExit(f"kazakhstan_religion: {region}: total rows {totals}")
    total = rows[totals[0]]
    units = {label: row for label, row in rows.items() if label != totals[0]}
    for i in range(8):
        summed = sum(row[i] for row in units.values())
        if units and summed != total[i]:
            raise SystemExit(f"kazakhstan_religion: {region}: units make {summed:,} in "
                             f"column {i} against {total[i]:,}")
    return total, units


def records(region: str, units: dict[str, list[int]], a1: list[dict[str, Any]],
            a2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    src = [{"field": "religion", "name": SOURCE, "url": PAGE, "license": LICENCE}]
    shapes = {u["id"]: u for u in a2}
    out = []
    for shape_id, names in sorted(kz.place(region, list(units), a1, a2).items()):
        label = shapes[shape_id]["name"]
        row = [sum(units[n][i] for n in names) for i in range(8)]
        bars = shares(dict(zip(GROUPS, row[1:])), total=row[0])
        note = kz.polygon_note(label, names)
        out.append(record(
            f"KAZ-REL2009-{shape_id}", label, level="admin2", parent=kz.region_id(region),
            parent_name=region, country=ISO3, match_by="shape_id", shape_id=shape_id,
            aliases=sorted(set(names) - {label}),
            religion=bars, religion_year=dated(bars, YEAR),
            religion_note=f"{SOURCE}. {NOTE}" + (f" {note}" if note else ""),
            sources=src))
    region_of = {u["id"]: u["name"] for u in a1}
    for (where, label), reason in kz.EMPTY.items():
        for shape in a2:
            if (where == region and shape["name"] == label
                    and region_of.get(shape.get("parent")) == region):
                out.append(record(
                    f"KAZ-REL2009-{shape['id']}", label, level="admin2",
                    parent=kz.region_id(region), parent_name=region, country=ISO3,
                    match_by="shape_id", shape_id=shape["id"],
                    religion=gap(NOT_AVAILABLE, reason)))
    return out


def read_region(region: str, text: str, a1: list[dict[str, Any]],
                a2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = unit_counts(section(text), region)
    total, units = region_rows(rows, region)
    if region in CITY_TOTAL:
        units = {CITY_TOTAL[region]: total}
    log(f"  {region}: {len(units)} units, {total[0]:,} people")
    return records(region, units, a1, a2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="one drawn region, for a quick look")
    args = ap.parse_args()
    from urllib.parse import quote
    a1, a2 = kz.drawn_units()
    out: list[dict[str, Any]] = []
    for region, path in VOLUMES.items():
        if args.only and region != args.only:
            continue
        blob = http_get(BASE + quote(path), binary=True, timeout=300)
        assert isinstance(blob, bytes)
        out += read_region(region, volume_text(blob), a1, a2)
    log(f"kazakhstan_religion: {len(out)} records")
    for r in out:
        bars = r["religion"]
        if isinstance(bars, list):
            log(f"    {r['name']}: " + ", ".join(f"{b['group']} {b['pct']}" for b in bars[:3]))
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
