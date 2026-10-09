#!/usr/bin/env python3
"""Kazakhstan: religion by region (2021 census) and by district (2009 census).

**By region, 2021.** The Bureau's *Brief results* of the 2021 National
Population Census (Краткие итоги / Қысқаша қорытындылар, 2022) carry table
7.1, "Население по вероисповеданию в разрезе регионов": the republic and its
17 regions of 2021 by religion -- Islam; Christianity, with Orthodoxy,
Catholicism and Protestantism; Judaism; Buddhism; other; those who declined
to say; non-believers -- for both sexes, men and women, then the urban and
rural population. The figures are printed with a space between the
thousands, so each row is read as the one split of its digit groups whose
religions make its total and whose three denominations make Christianity
(``row_2021``); the regions must make the republic's 19,186,015 column by
column, and men and women must make both sexes. Turkestan Region and the
city of Shymkent are drawn as one polygon (South Kazakhstan Region) and take
their sum. This is the table the 'Religion in Kazakhstan' article on
Wikipedia transcribes; read from the Bureau, it replaces that transcription.

**By district, 2009.** The 2009 National Population Census published three
volumes for each region. Volume 2 ("Итоги Национальной переписи населения
Республики Казахстан 2009 года", том 2) carries table 1.6, "Население районов
по вероисповеданию": every district and city akimat of the region by
religion -- Islam, Christianity, Judaism, Buddhism, other, non-believers, and
those who declined to say -- in people and in per cent, for both sexes, men
and women.

It is the only religion below the region the Bureau has published. The 2021
census's brief results stop at the region, and its national volume
(*National composition, religion and language proficiency*, 2023) tabulates
religion by nationality, age and education (tables 12-14, printed pages
391-421) for the republic and its urban and rural population only. The
Bureau's two 2021 census dashboards (stat.gov.kz/ru/instuments/dashboards/
28424 and 28478) are Qlik Sense apps on qap.stat.gov.kz that serve no table
of their own.

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
        "Buddhism, another religion, non-believer, or declined to say. The 2021 census asked "
        "it again and the Bureau publishes it by region (brief results, table 7.1) and for "
        "the republic by nationality, age and education (National composition, religion "
        "and language proficiency, 2023, tables 12-14), for no district.")
CITY_TOTAL = {"Almaty": "г.Алматы"}

# The 2021 census's brief results, from the Bureau's media library; the
# Internet Archive's capture of the same book under its older address is the
# fallback.
BRIEF_URL = (BASE + "e62/b1e0sokkht34a1iyu2qdmu30dayt6sz1/"
             "%D0%9A%D1%80%D0%B0%D1%82%D0%BA%D0%B8%D0%B5%20%D0%B8%D1%82%D0%BE%D0%B3%D0%B8%20"
             "%D0%9F%D0%B5%D1%80%D0%B5%D0%BF%D0%B8%D1%81%D0%B8%20%D0%BD%D0%B0%D1%81%D0%B5"
             "%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F.pdf")
BRIEF_ARCHIVE = ("https://web.archive.org/web/20220902140633id_/"
                 "https://stat.gov.kz/api/getFile/?docId=ESTAT464825")
BRIEF_PAGE = "https://stat.gov.kz/ru/national/2021/"
BRIEF_SOURCE = ("Bureau of National Statistics of Kazakhstan, Brief results of the 2021 National "
                "Population Census (2022), table 7.1: population by religion by region")
YEAR_2021 = 2021
NATIONAL_2021 = 19_186_015
REPUBLIC = "Қазақстан Республикасы"
# Table 7.1's regions, as the book names them in Kazakh -> the drawn region.
REGIONS_2021 = {
    "Ақмола": "Akmola Region", "Ақтөбе": "Aktobe Region", "Алматы": "Almaty Region",
    "Атырау": "Atyrau Region", "Батыс Қазақстан": "West Kazakhstan Region",
    "Жамбыл": "Jambyl Region", "Қарағанды": "Karaganda Region",
    "Қостанай": "Kostanay Region", "Қызылорда": "Kyzylorda Region",
    "Маңғыстау": "Mangystau Region", "Павлодар": "Pavlodar Region",
    "Солтүстік Қазақстан": "North Kazakhstan Region",
    "Түркістан": "South Kazakhstan Region", "Шығыс Қазақстан": "East Kazakhstan Region",
    "Нұр-Сұлтан қаласы": "Astana", "Алматы қаласы": "Almaty",
    "Шымкент қаласы": "South Kazakhstan Region",
}
# Table 7.1's columns in the order printed: the total, Islam, Christianity and
# its three denominations, Judaism, Buddhism, other, declined, non-believers.
COLUMNS_2021 = ("Total", "Islam", "Christianity", "Orthodox", "Catholic", "Protestant",
                "Judaism", "Buddhism", "Other religions", "Not stated", "No religion")
# What a region's bars are: Christianity is shown as its three denominations,
# which make it to the person.
BARS_2021 = ("Islam", "Orthodox", "Catholic", "Protestant", "Judaism", "Buddhism",
             "Other religions", "No religion", "Not stated")
NOTE_2021 = ("Religion as each person named it at the 2021 census -- Islam; Christianity, "
             "shown as Orthodoxy, Catholicism and Protestantism; Judaism; Buddhism; another "
             "religion -- with the non-believers ('No religion') and those who declined to "
             "say ('Not stated'): every resident, of every age. Table 7.1 of the Bureau's "
             "brief results of the census, by region; the Bureau publishes no 2021 religion "
             "by district.")


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
    import logging

    from pypdf import PdfReader
    # pypdf warns once per font that it wants fontTools for the CFF encoding;
    # the glyph names it falls back to are what ``decode`` reads.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(io.BytesIO(blob))
    return decode("\n".join((page.extract_text() or "") for page in reader.pages))


START = re.compile(r"(?:\d\.\d+\s*)?Население\s+(?:городов\s+и\s+)?районов\s+по\s+"
                   r"вероисповеданию", re.IGNORECASE)
END = re.compile(r"(?m)^\s*2\.\s*(?:1\s+)?(?:ОБРАЗОВАТЕЛЬНЫЙ|Население\s+по\s+уровню)")
LINE = re.compile(r"^(?P<label>[^\d]*?)\s*(?P<figures>\d[\d\s,]*)$")


def section(text: str) -> str:
    starts = [m.end() for m in START.finditer(text)]
    if not starts:
        near = [line for line in text.splitlines() if "вероисп" in line.lower()][:6]
        raise SystemExit(f"kazakhstan_religion: the district religion table was not found; "
                         f"lines naming religion: {near}; text opens "
                         f"{' '.join(text[:400].split())!r}")
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
            # A label wrapped onto the next line ('Енбекшильдерский' / 'район ...',
            # 'Район Магжана' / 'Жумабаева ...').
            if (re.search(r"(район|г\.а|акимат|[а-я]ский)$", low) or low.startswith("район ")
                    or pending):
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
    """The one reading of a row (see ``readings``), or None if there is not one."""
    found = readings(figures, pct)
    return found[0] if len(found) == 1 else None


def readings(figures: str, pct: list[float] | None) -> list[list[int]]:
    """Every way a row's run of digits can be its total and seven religions.

    Every split of the digits into eight numbers is tried; one is kept when
    the seven make the first and each is within the printed share's rounding
    of it.
    """
    digits = re.sub(r"\D", "", figures or "")
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
    return [list(f) for f in sorted({tuple(f) for f in found})]


def unit_counts(body: str, region: str) -> dict[str, list[int]]:
    """{label: [total, seven religions]} for both sexes, every row read whole.

    A row's digits sometimes allow two readings that both agree with its
    shares -- '2 28' read as 2 and 28 or as 22 and 8, when both round to the
    same tenth of a per cent. The table prints men and women too, and the
    reading kept is then the one that is the sum of a reading of the men's row
    and one of the women's.
    """
    table = blocks(body)

    def options(sex: str, label: str) -> list[list[int]]:
        figures = table.get((sex, "count"), {}).get(label)
        printed = table.get((sex, "pct"), {}).get(label)
        return readings(figures, percentages(printed) if printed else None) if figures else []

    both, pct = table.get(("both", "count"), {}), table.get(("both", "pct"), {})
    out: dict[str, list[int]] = {}
    unread = []
    for label, figures in both.items():
        found = options("both", label)
        if len(found) > 1:
            men, women = options("men", label), options("women", label)
            found = [b for b in found
                     if any(all(b[i] == m[i] + w[i] for i in range(8))
                            for m in men for w in women)]
        if len(found) != 1:
            unread.append(f"{label}: {figures!r} / {pct.get(label)!r} ({len(found)} readings)")
            continue
        out[label] = found[0]
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


# --------------------------------------------------------------------------
# By region, 2021: table 7.1 of the census's brief results.

def row_2021(figures: str) -> list[list[int]]:
    """Every reading of a row's digit groups as table 7.1's eleven columns.

    '19 186 015 13 297 775 3 297 550 ...' is a run of groups, each number one
    group of one to three digits and then any groups of exactly three. A
    reading is kept when the religions make the total and the three
    denominations make Christianity.
    """
    groups = figures.split()
    if not groups or not all(g.isdigit() for g in groups):
        return []
    found: list[list[int]] = []

    def walk(i: int, acc: list[int]) -> None:
        if len(acc) == len(COLUMNS_2021):
            total, islam, christ, orth, cath, prot, jud, bud, other, refused, none = acc
            if (i == len(groups) and christ == orth + cath + prot
                    and total == islam + christ + jud + bud + other + refused + none):
                found.append(list(acc))
            return
        if i >= len(groups) or len(groups[i]) > 3 or (len(groups[i]) > 1
                                                      and groups[i].startswith("0")):
            return
        text = groups[i]
        j = i + 1
        while True:
            value = int(text)
            if acc and value > acc[0]:
                return
            walk(j, acc + [value])
            if j < len(groups) and len(groups[j]) == 3:
                text += groups[j]
                j += 1
            else:
                return

    walk(0, [])
    return found


LINE_2021 = re.compile(r"^(?P<label>[^\d]+?)\s+(?P<figures>\d[\d ]*)$")


def table_2021(pages: list[str]) -> dict[str, dict[str, list[int]]]:
    """{sex: {region: [eleven columns]}} from table 7.1's whole-population pages.

    The table starts where its title is followed by "Все население" and ends
    at the urban population ("Городское население") or at the percentages
    ("в процентах"). Each row must read one way only; where its digit groups
    allow two, the men's and women's rows decide.
    """
    text = "\n".join(pages)
    starts = [m.end() for m in re.finditer(
        r"Население по вероисповеданию в разрезе регионов\s*\n\s*Барлық халық\s*\n\s*"
        r"Все население", text)]
    if len(starts) != 1:
        raise SystemExit(f"kazakhstan_religion: table 7.1's whole population found "
                         f"{len(starts)} times")
    body = text[starts[0]:]
    end = re.search(r"в процентах|Городское население", body)
    body = body[:end.start()] if end else body
    rows: dict[str, dict[str, str]] = {"both": {}, "men": {}, "women": {}}
    sex = None
    for raw in body.splitlines():
        line = " ".join(raw.split())
        if line == "Оба пола":
            sex = "both"
        elif line == "Мужчины":
            sex = "men"
        elif line == "Женщины":
            sex = "women"
        m = LINE_2021.match(line)
        if not m or sex is None:
            continue
        label = m.group("label").strip()
        if label != REPUBLIC and label not in REGIONS_2021:
            continue
        if label in rows[sex]:
            raise SystemExit(f"kazakhstan_religion: table 7.1 has {label} twice ({sex})")
        rows[sex][label] = m.group("figures")
    wanted = {REPUBLIC, *REGIONS_2021}
    for sex, found in rows.items():
        if set(found) != wanted:
            raise SystemExit(f"kazakhstan_religion: table 7.1 ({sex}) lacks "
                             f"{sorted(wanted - set(found))}, has {sorted(set(found) - wanted)}")
    out: dict[str, dict[str, list[int]]] = {"both": {}, "men": {}, "women": {}}
    for label in sorted(wanted):
        options = {sex: row_2021(rows[sex][label]) for sex in rows}
        pairs = [(b, m, w) for b in options["both"] for m in options["men"]
                 for w in options["women"]
                 if all(b[i] == m[i] + w[i] for i in range(len(COLUMNS_2021)))]
        if len(pairs) != 1:
            raise SystemExit(f"kazakhstan_religion: table 7.1's {label} reads "
                             f"{len(pairs)} ways: {rows['both'][label]!r}")
        for sex, values in zip(("both", "men", "women"), pairs[0]):
            out[sex][label] = values
    for sex, found in out.items():
        made = [sum(found[r][i] for r in REGIONS_2021) for i in range(len(COLUMNS_2021))]
        if made != found[REPUBLIC]:
            raise SystemExit(f"kazakhstan_religion: table 7.1's regions make {made} against "
                             f"the republic's {found[REPUBLIC]} ({sex})")
    if out["both"][REPUBLIC][0] != NATIONAL_2021:
        raise SystemExit(f"kazakhstan_religion: table 7.1 counts {out['both'][REPUBLIC][0]:,}, "
                         f"not the census's {NATIONAL_2021:,}")
    return out


def records_2021(table: dict[str, list[int]], a1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One religion record per drawn region, Turkestan and Shymkent together."""
    ids = {u["name"]: u["id"] for u in a1}
    pooled: dict[str, list[str]] = defaultdict(list)
    for label, region in REGIONS_2021.items():
        pooled[region].append(label)
    if set(pooled) != set(ids):
        raise SystemExit(f"kazakhstan_religion: drawn regions {sorted(set(ids) ^ set(pooled))} "
                         f"do not match table 7.1's")
    src = [{"field": "religion", "name": BRIEF_SOURCE, "url": BRIEF_PAGE,
            "year": YEAR_2021, "license": LICENCE}]
    out = []
    for region, labels in sorted(pooled.items()):
        row = [sum(table[label][i] for label in labels) for i in range(len(COLUMNS_2021))]
        counts = dict(zip(COLUMNS_2021, row))
        bars = shares({k: counts[k] for k in BARS_2021 if counts[k]}, total=row[0])
        note = NOTE_2021 + (" Turkestan Region and the city of Shymkent, a region of its own "
                            "since 2018, together: the map draws them as one."
                            if len(labels) > 1 else "")
        out.append(record(
            f"KAZ-REL2021-{ids[region]}", region, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=ids[region], aliases=labels,
            religion=bars, religion_year=dated(bars, YEAR_2021), religion_note=note,
            sources=src))
    return out


def read_2021(a1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import logging

    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    blob: bytes | str = b""
    for url in (BRIEF_URL, BRIEF_ARCHIVE):
        try:
            blob = http_get(url, binary=True, timeout=300)
        except RuntimeError as err:
            log(f"  brief results: {url} refused ({err}); trying the next copy")
            continue
        if isinstance(blob, bytes) and blob[:5] == b"%PDF-":
            break
        log(f"  brief results: {url} is not a PDF ({bytes(blob[:40])!r})")
        blob = b""
    if not blob:
        raise SystemExit("kazakhstan_religion: neither copy of the 2021 brief results was read")
    assert isinstance(blob, bytes)
    pages = [(p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages]
    table = table_2021(pages)
    rows = records_2021(table["both"], a1)
    log(f"  2021 by region: {len(rows)} drawn regions from {len(REGIONS_2021)} regions, "
        f"{table['both'][REPUBLIC][0]:,} people")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="one drawn region, for a quick look")
    args = ap.parse_args()
    from urllib.parse import quote
    a1, a2 = kz.drawn_units()
    out: list[dict[str, Any]] = []
    failed: list[str] = []
    for region, path in VOLUMES.items():
        if args.only and region != args.only:
            continue
        blob = http_get(BASE + quote(path), binary=True, timeout=300)
        assert isinstance(blob, bytes)
        # Every volume is read before stopping, so one run names every
        # region's trouble; nothing is written unless all of them read whole.
        try:
            out += read_region(region, volume_text(blob), a1, a2)
        except SystemExit as err:
            log(f"  {region}: {err}")
            failed.append(region)
    if failed:
        raise SystemExit(f"kazakhstan_religion: {len(failed)} volumes not read: {failed}")
    if not args.only:
        out = read_2021(a1) + out
    log(f"kazakhstan_religion: {len(out)} records")
    for r in out:
        bars = r["religion"]
        if isinstance(bars, list):
            log(f"    {r['name']}: " + ", ".join(f"{b['group']} {b['pct']}" for b in bars[:3]))
    write_json(PROCESSED / OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
