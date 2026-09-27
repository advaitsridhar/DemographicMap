#!/usr/bin/env python3
"""Belarus from the 2019 census's second volume.

Belstat publishes the 2019 census as statistical compendia; the second volume
("Итоги переписи населения Республики Беларусь 2019 года", том 2, Minsk
2021, 491 pages) is on its site as a PDF. This reads three of its tables:

* 1.4 -- the population of every oblast, city of oblast subordination and
  raion by sex in 1999, 2009 and 2019: each raion's count and men per hundred
  women, and each oblast's;
* 6.2 -- the national composition of each oblast and of Minsk (2019);
* 7.3 -- by oblast, the language each person usually speaks at home,
  Belarusian or Russian (2019).

**Units.** The map draws the 117 raions of 2019 bar one (Drybin, formed from
Horki raion in 1989 and drawn as part of it) and the city of Minsk. The census
counts each city of oblast subordination apart from the raion around it; the
map draws no polygon for any of them, so each goes with the raion it is the
seat of (Brest with Brest raion), and the two that are no raion's seat --
Navapolatsk and Zhodzina -- with the raion whose polygon holds the city's
centre (GeoNames), which the run checks rather than assumes.

**Not published by raion.** The volume's age tables stop at the country
(2.2, 2.3) or give the oblasts' mean age (2.1), not a median; nationality and
language stop at the oblast.

Usage:
    python -m scripts.fetch_census.belarus
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record,
                      shares, write_json)
from . import east_geo

SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "belarus.json"
VOLUME = "https://www.belstat.gov.by/upload/iblock/e2c/jpupn3rl7trtmxepj6vmh07qy6u5o09i.pdf"
PAGE = ("https://www.belstat.gov.by/ofitsialnaya-statistika/publications/izdania/"
        "public_compilation/index_41896/")
YEAR = 2019
SOURCE = ("National Statistical Committee of the Republic of Belarus (Belstat), Итоги "
          "переписи населения Республики Беларусь 2019 года, том 2, table {table}")
LICENCE = "Belstat, open publication"

OBLAST = {"Брестская": "Brest", "Витебская": "Vitebsk", "Гомельская": "Gomel",
          "Гродненская": "Grodno", "Минская": "Minsk", "Могилевская": "Mogilev",
          "Могилёвская": "Mogilev"}
MINSK_CITY = "Minsk City"
# The census's raion (its adjective) -> the map's polygon.
RAION = {
    # Brest
    "Барановичский": "Baranovichy", "Берёзовский": "Byaroza", "Березовский": "Byaroza",
    "Брестский": "Brest", "Ганцевичский": "Hantsavichy", "Дрогичинский": "Drahichyn",
    "Жабинковский": "Zhabinka", "Ивановский": "Ivanava", "Ивацевичский": "Ivatsevichy",
    "Каменецкий": "Kamenets", "Кобринский": "Kobryn", "Лунинецкий": "Luninets",
    "Ляховичский": "Lyakhavichy", "Малоритский": "Malaryta", "Пинский": "Pinsk",
    "Пружанский": "Pruzhany", "Столинский": "Stolin",
    # Vitebsk
    "Бешенковичский": "Beshankovichy", "Браславский": "Braslaw",
    "Верхнедвинский": "Verkhnyadzvinsk", "Витебский": "Vitebsk", "Глубокский": "Hlybokaye",
    "Городокский": "Haradok", "Докшицкий": "Dokshytsy", "Дубровенский": "Dubrowna",
    "Лепельский": "Lyepyel", "Лиозненский": "Liozna", "Миорский": "Miory",
    "Оршанский": "Orsha", "Полоцкий": "Polotsk", "Поставский": "Pastavy",
    "Россонский": "Rasony", "Сенненский": "Syanno", "Толочинский": "Talachyn",
    "Ушачский": "Ushachy", "Чашникский": "Chashniki", "Шарковщинский": "Sharkawshchyna",
    "Шумилинский": "Shumilina",
    # Gomel
    "Брагинский": "Brahin", "Буда-Кошелевский": "Buda-Kashalyova",
    "Буда-Кошелёвский": "Buda-Kashalyova", "Ветковский": "Vietka", "Гомельский": "Gomel",
    "Добрушский": "Dobrush", "Ельский": "Yelʹsk", "Житковичский": "Zhytkavichy",
    "Жлобинский": "Zhlobin", "Калинковичский": "Kalinkavichy", "Кормянский": "Karma",
    "Лельчицкий": "Lyelchytsy", "Лоевский": "Loyew", "Мозырский": "Mazyr",
    "Наровлянский": "Naroulia", "Октябрьский": "Akciabrski", "Петриковский": "Pyetrykaw",
    "Речицкий": "Rechytsa", "Рогачевский": "Rahachow", "Рогачёвский": "Rahachow",
    "Светлогорский": "Svietlahorsk", "Хойникский": "Khoiniki", "Чечерский": "Chachersk",
    # Grodno
    "Берестовицкий": "Byerastavitsa", "Волковысский": "Vawkavysk",
    "Вороновский": "Voranava", "Гродненский": "Grodno", "Дятловский": "Dzyatlava",
    "Зельвенский": "Zel'va", "Ивьевский": "Iwye", "Кореличский": "Karelichy",
    "Лидский": "Lida", "Мостовский": "Masty", "Новогрудский": "Novogrudok",
    "Островецкий": "Astravyets", "Ошмянский": "Ashmyany", "Свислочский": "Svislach",
    "Слонимский": "Slonim", "Сморгонский": "Smarhon", "Щучинский": "Shchuchyn",
    # Minsk region
    "Березинский": "Byerazino", "Борисовский": "Barysaw", "Вилейский": "Vileyka",
    "Воложинский": "Valozhyn", "Дзержинский": "Dzyarzhynsk", "Клецкий": "Kletsk",
    "Копыльский": "Kapyl", "Крупский": "Krupki", "Логойский": "Lahoysk",
    "Любанский": "Lyuban", "Минский": "Minsk", "Молодечненский": "Maladzyechna",
    "Мядельский": "Myadzyel", "Несвижский": "Nyasvizh", "Пуховичский": "Puchavičy",
    "Слуцкий": "Slutsk", "Смолевичский": "Smalyavichy", "Солигорский": "Salihorsk",
    "Стародорожский": "Staryya Darohi", "Столбцовский": "Stowbtsy", "Узденский": "Uzda",
    "Червенский": "Chervyen",
    # Mogilev
    "Белыничский": "Byalynichy", "Бобруйский": "Babruysk", "Быховский": "Bykhaw",
    "Глусский": "Hlusk", "Горецкий": "Horki", "Дрибинский": "Horki", "Кировский": "Kirawsk",
    "Климовичский": "Klimavichy", "Кличевский": "Klichaw", "Костюковичский": "Kastsyukovichy",
    "Краснопольский": "Krasnapolle", "Кричевский": "Krychaw", "Круглянский": "Kruhlaye",
    "Могилевский": "Mogilev", "Могилёвский": "Mogilev", "Мстиславский": "Mstsislaw",
    "Осиповичский": "Asipovichy", "Славгородский": "Slawharad", "Хотимский": "Khotsimsk",
    "Чаусский": "Chavusy", "Чериковский": "Cherykaw", "Шкловский": "Shklow",
}
# A city of oblast subordination -> the raion it is the seat of, or (for a
# city that is no raion's seat) the raion whose polygon is checked to hold it.
CITY = {
    "Брест": "Брестский", "Барановичи": "Барановичский", "Пинск": "Пинский",
    "Витебск": "Витебский", "Новополоцк": "Полоцкий", "Орша": "Оршанский",
    "Полоцк": "Полоцкий", "Гомель": "Гомельский", "Мозырь": "Мозырский",
    "Речица": "Речицкий", "Светлогорск": "Светлогорский", "Жлобин": "Жлобинский",
    "Гродно": "Гродненский", "Лида": "Лидский", "Борисов": "Борисовский",
    "Жодино": "Смолевичский", "Молодечно": "Молодечненский", "Солигорск": "Солигорский",
    "Слуцк": "Слуцкий", "Могилев": "Могилевский", "Могилёв": "Могилёвский",
    "Бобруйск": "Бобруйский",
}
NOT_SEAT = {"Новополоцк": "Navapolatsk", "Жодино": "Zhodzina"}
# Drybin raion, drawn as part of Horki's polygon: the run checks that Drybin's
# centre lies in it.
MERGED = {"Дрибинский": ("Drybin", "Horki")}

ETHNICITY = {"белорусы": "Belarusian", "русские": "Russian", "поляки": "Polish",
             "украинцы": "Ukrainian", "евреи": "Jewish", "армяне": "Armenian",
             "татары": "Tatar", "цыгане": "Romani", "азербайджанцы": "Azerbaijani",
             "литовцы": "Lithuanian", "туркмены": "Turkmen", "немцы": "German",
             "грузины": "Georgian", "молдаване": "Moldovan", "китайцы": "Chinese",
             "латыши": "Latvian", "узбеки": "Uzbek", "казахи": "Kazakh", "арабы": "Arab",
             "таджики": "Tajik"}


# ---------------------------------------------------------------------------
# Reading the PDF's rows with the positions of their words


def pdf_rows(blob: bytes) -> list[list[list[tuple[float, float, str]]]]:
    """[page][row] = [(x0, x1, word)], the words of a row sharing a baseline."""
    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            rows: list[tuple[float, list]] = []
            for w in sorted(page.extract_words(keep_blank_chars=False),
                            key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(w["top"], 1)
                cell = (w["x0"], w["x1"], w["text"])
                if rows and abs(rows[-1][0] - top) <= 2.0:
                    rows[-1][1].append(cell)
                else:
                    rows.append((top, [cell]))
            out.append([sorted(cells) for _, cells in rows])
    return out


DIGITS = re.compile(r"^[\d–-]+$")


def split_row(cells: list[tuple[float, float, str]], gap: float = 9.0
              ) -> tuple[str, list[float | None], str]:
    """(label before the figures, figures, label after them). A figure's digit
    groups are set a few points apart ("1 485 095"); figures are set further."""
    label, after, numbers = [], [], []
    current: list[tuple[float, float, str]] = []
    for x0, x1, text in cells:
        if DIGITS.match(text) and not after:
            if current and x0 - current[-1][1] > gap:
                numbers.append(current)
                current = []
            current.append((x0, x1, text))
        elif current or numbers:
            if current:
                numbers.append(current)
                current = []
            after.append(text)
        else:
            label.append(text)
    if current:
        numbers.append(current)
    values = []
    for group in numbers:
        text = "".join(t for *_, t in group)
        values.append(None if set(text) <= set("–-") else float(text))
    return " ".join(label), values, " ".join(after)


# ---------------------------------------------------------------------------
# Table 1.4: every oblast, city and raion by sex


def table_14(pages) -> dict[str, dict[str, dict[str, float]]]:
    """{oblast: {row label: {"all", "men", "women"}}}, the 2019 column of the
    all-population blocks."""
    start = next(i for i, rows in enumerate(pages)
                 if any("1.4." in " ".join(t for *_, t in r) for r in rows))
    out: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    section = None
    oblast = None
    unit = None
    for rows in pages[start:]:
        text = [" ".join(t for *_, t in r) for r in rows]
        if any(re.match(r"^\s*1\.5\.", t) for t in text):
            break
        for cells, line in zip(rows, text):
            if line.startswith("Все население"):
                section = "all"
                continue
            if line.startswith(("Городское население", "Сельское население")):
                section = "other"
                continue
            if section != "all":
                continue
            label, values, _ = split_row(cells)
            if len(values) != 3 or not label:
                continue
            value = values[2]
            if label in ("мужчины", "женщины"):
                if unit is None and oblast == "г.Минск":
                    continue
                if unit is None:
                    raise SystemExit(f"belarus: a sex row {line!r} follows no unit")
                out[oblast][unit]["men" if label == "мужчины" else "women"] = value
                continue
            if m := re.match(r"^(\S+) область$", label):
                oblast, unit = m.group(1), label
            elif label == "г.Минск":
                oblast, unit = "г.Минск", label
            elif oblast == "г.Минск":
                # Minsk's own districts, parts of the city the map draws whole.
                unit = None
                continue
            else:
                unit = label
            if oblast is None:
                raise SystemExit(f"belarus: table 1.4 row {label!r} before any oblast")
            out[oblast][unit] = {"all": value}
    return dict(out)


# ---------------------------------------------------------------------------
# Table 6.2 (nationality by oblast) and 7.3 (language by oblast)


def table_62(pages) -> dict[str, dict[str, float]]:
    """{oblast or 'г.Минск': {nationality: n, '_total': n}}, both sexes, 2019."""
    start = next(i for i, rows in enumerate(pages)
                 if any(" ".join(t for *_, t in r).startswith("6.2.") for r in rows))
    out: dict[str, dict[str, float]] = {}
    area = None
    block = None
    for rows in pages[start:]:
        text = [" ".join(t for *_, t in r) for r in rows]
        if any(t.startswith("6.3.") for t in text):
            break
        for cells, line in zip(rows, text):
            if m := re.match(r"^(\S+ область|г\.Минск)\s*/", line):
                area = m.group(1).replace(" область", "")
                block = "both"      # a continuation page names no sex before its rows
                continue
            if line.startswith("Мужчины и женщины"):
                block = "both"
                continue
            if line.startswith(("Мужчины /", "Женщины /")):
                block = "one sex"
                continue
            if block != "both" or area is None:
                continue
            label, values, _ = split_row(cells)
            if len(values) != 3:
                continue
            value = values[2] or 0.0
            key = label.strip().lower()
            if key.startswith("все население"):
                out.setdefault(area, {})["_total"] = value
            elif key:
                out.setdefault(area, {})[key] = value
    return out


def table_73(pages) -> dict[str, dict[str, float]]:
    """{oblast or 'г.Минск': {"total", "mother_be", "mother_ru", "home_be",
    "home_ru"}}, the whole population, 2019."""
    start = next(i for i, rows in enumerate(pages)
                 if any(" ".join(t for *_, t in r).startswith("7.3.") for r in rows))
    out: dict[str, dict[str, float]] = {}
    for rows in pages[start:start + 1]:
        for cells in rows:
            label, values, _ = split_row(cells)
            if len(values) != 5:
                continue
            name = label.split()[0] if label else ""
            key = {"Брестская": "Брестская", "Витебская": "Витебская",
                   "Гомельская": "Гомельская", "Гродненская": "Гродненская",
                   "г.Минск": "г.Минск", "Минская": "Минская", "Могилевская": "Могилевская",
                   "Могилёвская": "Могилевская"}.get(name)
            if key and key not in out:
                out[key] = dict(zip(("total", "mother_be", "mother_ru", "home_be",
                                     "home_ru"), values))
    return out


# ---------------------------------------------------------------------------


def cite(field: str, table: str) -> dict[str, Any]:
    return {"field": field, "name": SOURCE.format(table=table), "url": PAGE,
            "license": LICENCE, "year": YEAR}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    blob = http_get(VOLUME, binary=True, timeout=900)
    pages = pdf_rows(blob)
    log(f"  volume 2: {len(pages)} pages")

    t14 = table_14(pages)
    admin1 = {u["name"]: u for u in json.loads((SITE / "admin1" / "BLR.units.json").read_text())}
    admin2 = json.loads((SITE / "admin2" / "BLR.units.json").read_text())
    parent = {u["id"]: u["name"] for u in admin1.values()}
    by_name = {(parent[u["parent"]], u["name"]): u for u in admin2}

    # Checks: each unit's sexes make it, each oblast is its cities and raions,
    # the oblasts and Minsk make the country.
    country = 0.0
    for oblast, units in t14.items():
        head = f"{oblast} область" if oblast != "г.Минск" else "г.Минск"
        for name, v in units.items():
            if abs(v.get("men", 0) + v.get("women", 0) - v["all"]) > 0.5:
                raise SystemExit(f"belarus: {name}: men {v.get('men')} and women "
                                 f"{v.get('women')} do not make {v['all']}")
        if oblast == "г.Минск":
            country += units[head]["all"]
            continue
        made = sum(v["all"] for n, v in units.items() if n != head)
        if abs(made - units[head]["all"]) > 0.5:
            raise SystemExit(f"belarus: {head} is {units[head]['all']:,.0f}, its cities and "
                             f"raions {made:,.0f}")
        country += units[head]["all"]
    log(f"  table 1.4: {sum(len(u) for u in t14.values())} rows in {len(t14)} oblasts and "
        f"Minsk; every oblast is its cities and raions; the country makes {country:,.0f}")
    if abs(country - 9_413_446) > 0.5:
        raise SystemExit(f"belarus: the oblasts and Minsk make {country:,.0f}, the census "
                         "9,413,446")

    # Place every row on a polygon.
    places = {east_geo.fold(p["name"]): p for p in east_geo.places("BLR")}
    polys = east_geo.polygons("BLR")
    members: dict[str, list[tuple[str, str]]] = defaultdict(list)
    notes: dict[str, list[str]] = defaultdict(list)
    for oblast, units in t14.items():
        region = MINSK_CITY if oblast == "г.Минск" else OBLAST[oblast]
        for name in units:
            if name in (f"{oblast} область", "г.Минск"):
                if name == "г.Минск":
                    members[by_name[(MINSK_CITY, MINSK_CITY)]["id"]].append((oblast, name))
                continue
            if name.startswith("г."):
                city = name[2:]
                raion = CITY.get(city)
                if raion is None:
                    raise SystemExit(f"belarus: no raion is declared for the city {city}")
                target = by_name.get((region, RAION[raion]))
                if target is None:
                    raise SystemExit(f"belarus: {city}'s raion {raion} has no polygon")
                if city in NOT_SEAT:
                    p = places.get(east_geo.fold(NOT_SEAT[city]))
                    inside = (east_geo.containing(polys, p["lon"], p["lat"]) if p else [])
                    if inside != [target["id"]]:
                        raise SystemExit(f"belarus: {city}'s centre lies in {inside}, not "
                                         f"{target['name']!r}")
                    notes[target["id"]].append(
                        f"the city of {NOT_SEAT[city]}, counted apart and drawn inside this "
                        "polygon (its centre lies in it)")
                else:
                    notes[target["id"]].append(
                        f"the city of {target['name']}, the raion's seat, counted apart")
                members[target["id"]].append((oblast, name))
                continue
            m = re.match(r"^(\S+) район$", name)
            if not m or m.group(1) not in RAION:
                raise SystemExit(f"belarus: table 1.4 has a row {name!r} with no polygon")
            target = by_name.get((region, RAION[m.group(1)]))
            if target is None:
                raise SystemExit(f"belarus: {name} goes to {RAION[m.group(1)]!r} in {region}, "
                                 "which the map lacks")
            if m.group(1) in MERGED:
                town, host = MERGED[m.group(1)]
                p = places.get(east_geo.fold(town))
                inside = east_geo.containing(polys, p["lon"], p["lat"]) if p else []
                if inside != [target["id"]]:
                    raise SystemExit(f"belarus: {town}'s centre lies in {inside}, not {host!r}")
                notes[target["id"]].append(f"{name}, formed from Horki raion in 1989, which "
                                           "the map draws as part of this polygon")
            members[target["id"]].append((oblast, name))
    left = [u["name"] for u in admin2 if u["id"] not in members]
    log(f"  {len(members)} of {len(admin2)} polygons hold a census row; left: {left}")

    records = []
    src14 = SOURCE.format(table="1.4")
    for u in admin2:
        rows = members.get(u["id"])
        if not rows:
            continue
        total = sum(t14[o][n]["all"] for o, n in rows)
        men = sum(t14[o][n]["men"] for o, n in rows)
        women = sum(t14[o][n]["women"] for o, n in rows)
        extra = ("; with it " + "; ".join(notes[u["id"]]) if notes.get(u["id"]) else "")
        note = (f" The {', '.join(n for _, n in rows)} as the 2019 census counted it"
                + extra + ".")
        records.append(record(
            f"BLR-2019-{u['id']}", u["name"], level="admin2", parent="BLR", country="BLR",
            match_by="shape_id", shape_id=u["id"],
            population=measure(int(total), year=YEAR, source=src14),
            population_note="Everyone counted by the 2019 census." + note,
            sex_ratio=measure(round(100 * men / women, 1), unit="males_per_100_females",
                              year=YEAR, source=src14),
            sex_ratio_note=f"{int(men):,} men and {int(women):,} women." + note,
            median_age=gap(NOT_AVAILABLE, (
                "Belstat publishes no age distribution by raion from the 2019 census: its "
                "second volume's age tables stop at the country, and give the oblasts' "
                "mean age, not a median.")),
            sources=[cite("population", "1.4"), cite("sex_ratio", "1.4")]))

    # First level.
    t62 = table_62(pages)
    t73 = table_73(pages)
    for oblast, units in t14.items():
        name = MINSK_CITY if oblast == "г.Минск" else OBLAST[oblast]
        head = units["г.Минск" if oblast == "г.Минск" else f"{oblast} область"]
        u = admin1[name]
        values: dict[str, Any] = {
            "population": measure(int(head["all"]), year=YEAR, source=src14),
            "population_note": "Everyone counted by the 2019 census.",
            "sex_ratio": measure(round(100 * head["men"] / head["women"], 1),
                                 unit="males_per_100_females", year=YEAR, source=src14),
            "sex_ratio_note": f"{int(head['men']):,} men and {int(head['women']):,} women.",
        }
        cites = [cite("population", "1.4"), cite("sex_ratio", "1.4")]
        key62 = "г.Минск" if oblast == "г.Минск" else oblast
        eth = t62.get(key62)
        if eth:
            total = eth.pop("_total", None)
            counts = Counter()
            unknown = []
            for label, n in eth.items():
                if label in ETHNICITY:
                    counts[ETHNICITY[label]] += n
                else:
                    unknown.append(label)
            if total is None or sum(counts.values()) > total + 0.5:
                raise SystemExit(f"belarus: table 6.2 for {name}: {sum(counts.values())} "
                                 f"named against a total of {total}")
            if unknown:
                log(f"  table 6.2 {name}: rows not read as nationalities: {unknown}")
            counts["Other"] = total - sum(counts.values())
            values["ethnicity"] = shares(dict(counts), total=total)
            values["ethnicity_year"] = YEAR
            values["ethnicity_note"] = (
                "Nationality (национальность) as each person stated it, 2019 census, "
                f"everyone counted in the {'city' if name == MINSK_CITY else 'oblast'}. "
                "Table 6.2 names the twenty most numerous nationalities; 'Other' is the "
                "rest of the count, including those who stated none.")
            cites.append(cite("ethnicity", "6.2"))
        lang = t73.get("Могилевская" if oblast in ("Могилевская", "Могилёвская") else oblast)
        if lang:
            total = lang["total"]
            be, ru = lang["home_be"], lang["home_ru"]
            values["language"] = shares({"Belarusian": be, "Russian": ru,
                                         "Other": total - be - ru}, total=total)
            values["language_year"] = YEAR
            values["language_note"] = (
                "The language usually spoken at home (язык, на котором обычно "
                "разговаривают дома), 2019 census, everyone counted. Table 7.3 names "
                "Belarusian and Russian only; 'Other' is every other language and no "
                f"answer. Asked their mother tongue, {100 * lang['mother_be'] / total:.1f}% "
                f"named Belarusian and {100 * lang['mother_ru'] / total:.1f}% Russian.")
            cites.append(cite("language", "7.3"))
        records.append(record(f"BLR-2019-{u['id']}", name, level="admin1", parent="BLR",
                              country="BLR", match_by="shape_id", shape_id=u["id"],
                              sources=cites, **values))
    log(f"  table 6.2: {len(t62)} areas; table 7.3: {len(t73)} areas")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
