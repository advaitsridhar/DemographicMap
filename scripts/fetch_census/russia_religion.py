#!/usr/bin/env python3
"""Russia: religion by federal subject from Sreda's *Arena* survey (2012).

No Russian census since 1937 has asked religion; the 2002, 2010 and 2020
censuses asked nationality and native language, which the map carries from
Rosstat (``russia.py``). The one measurement of religion by federal subject is
a survey: Sreda's *Arena* ("Атлас религий и национальностей России"),
fieldwork by the Public Opinion Foundation (FOM) in its MegaFOM omnibus, 29
May to 25 June 2012, face to face at home, 56,900 people aged 18 and over in
79 of the 83 subjects -- 500 to 800 in each. The four left out are Chechnya,
Ingushetia, Chukotka and Nenets AO, which is why the survey says it covers
98.8% of Russia's population, and why its Arkhangelsk Oblast and Tyumen Oblast
are the oblasts without their autonomous okrugs (the okrugs of Tyumen are
subjects of the survey in their own right): the same areas the map draws.

Sreda publishes its tabulation as a workbook, ``arena_statistic.xls``, on the
atlas's own site: the share of each answer by subject. The religion question
is a card with one answer: which statement fits you best -- "I profess
Orthodoxy and belong to the Russian Orthodox Church", "I believe in God (a
higher power) but profess no particular religion", "I do not believe in God",
Sunni, Shia or other Islam, and so on. Those are the categories written, one
for one; "затрудняюсь ответить" is written as "Don't know".

**Respondents.** The workbook gives no count per subject, but within a subject
every share is a whole number of respondents out of the same n (Belgorod's
are multiples of 1/800, Karelia's of 1/500), so n is read off the shares: the
smallest n for which every share of every single-answer question in the
subject's column -- religion, sex, age, education, nationality, settlement
type -- is a whole count. The run fails if there is no such n between 100 and
3,000, and a subject under 100 would be left out; none is.

**Weights.** Sreda's figures for Russia and its federal districts weight the
subjects by population ("Доли групп"); within a subject its shares are the
respondents' own answers, which is what is written here.

These are **survey estimates**: ``religion_basis`` says so, and the file is
``russia_religion_survey.json``, which the build uses only where no census or
register count exists.

Usage:
    python -m scripts.fetch_census.russia_religion
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json

WORKBOOK = "http://sreda.org/maps/arena_russia_main/arena_statistic.xls"
PAGE = "http://sreda.org/arena"
SOURCE = ("Sreda, Arena: Atlas of Religions and Nationalities of Russia (2012), "
          "arena_statistic.xls -- 'Распределение ответов в регионах РФ'")
LICENCE = "Sreda, published aggregate tabulation"
OUT = PROCESSED / "russia_religion_survey.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2012

# The workbook's subject headings -> ISO 3166-2, written out; every one is
# checkable against the published standard.
SUBJECTS = {
    "Белгородская область": "RU-BEL", "Брянская область": "RU-BRY",
    "Владимирская область": "RU-VLA", "Воронежская область": "RU-VOR",
    "Ивановская область": "RU-IVA", "Калужская область": "RU-KLU",
    "Костромская область": "RU-KOS", "Курская область": "RU-KRS",
    "Липецкая область": "RU-LIP", "Московская область": "RU-MOS",
    "Орловская область": "RU-ORL", "Рязанская область": "RU-RYA",
    "Смоленская область": "RU-SMO", "Тамбовская область": "RU-TAM",
    "Тверская область": "RU-TVE", "Тульская область": "RU-TUL",
    "Ярославская область": "RU-YAR", "город Москва": "RU-MOW",
    "Республика Карелия": "RU-KR", "Республика Коми": "RU-KO",
    "Архангельская область": "RU-ARK", "Вологодская область": "RU-VLG",
    "Калининградская область": "RU-KGD", "Ленинградская область": "RU-LEN",
    "Мурманская область": "RU-MUR", "Новгородская область": "RU-NGR",
    "Псковская область": "RU-PSK", "город Санкт-Петербург": "RU-SPE",
    "Республика Адыгея": "RU-AD", "Республика Калмыкия": "RU-KL",
    "Краснодарский край": "RU-KDA", "Астраханская область": "RU-AST",
    "Волгоградская область": "RU-VGG", "Ростовская область": "RU-ROS",
    "Республика Дагестан": "RU-DA", "Кабардино-Балкарская Республика": "RU-KB",
    "Карачаево-Черкесская Республика": "RU-KC",
    "Республика Северная Осетия-Алания": "RU-SE", "Ставропольский край": "RU-STA",
    "Республика Башкортостан": "RU-BA", "Республика Марий Эл": "RU-ME",
    "Республика Мордовия": "RU-MO", "Республика Татарстан": "RU-TA",
    "Удмуртская Республика": "RU-UD", "Чувашская Республика": "RU-CU",
    "Кировская область": "RU-KIR", "Нижегородская область": "RU-NIZ",
    "Оренбургская область": "RU-ORE", "Пензенская область": "RU-PNZ",
    "Самарская область": "RU-SAM", "Саратовская область": "RU-SAR",
    "Ульяновская область": "RU-ULY", "Пермский край": "RU-PER",
    "Курганская область": "RU-KGN", "Свердловская область": "RU-SVE",
    "Тюменская область": "RU-TYU", "Челябинская область": "RU-CHE",
    "Ханты-Мансийский автономный округ": "RU-KHM",
    "Ямало-Ненецкий автономный округ": "RU-YAN",
    "Республика Алтай": "RU-AL", "Республика Бурятия": "RU-BU",
    "Республика Тыва": "RU-TY", "Республика Хакасия": "RU-KK",
    "Алтайский край": "RU-ALT", "Красноярский край": "RU-KYA",
    "Иркутская область": "RU-IRK", "Кемеровская область": "RU-KEM",
    "Новосибирская область": "RU-NVS", "Омская область": "RU-OMS",
    "Томская область": "RU-TOM", "Забайкальский край": "RU-ZAB",
    "Республика Саха (Якутия)": "RU-SA", "Приморский край": "RU-PRI",
    "Хабаровский край": "RU-KHA", "Амурская область": "RU-AMU",
    "Магаданская область": "RU-MAG", "Сахалинская область": "RU-SAK",
    "Еврейская автономная область": "RU-YEV", "Камчатский край": "RU-KAM",
}
NOT_SURVEYED = {"RU-CE": "Chechnya", "RU-IN": "Ingushetia", "RU-CHU": "Chukotka",
                "RU-NEN": "Nenets AO"}

QUESTION = "Выберите, пожалуйста, из предлагаемого списка одно утверждение"
NEXT_QUESTION = "А теперь выберите"
# The card's answers, as the workbook words them (to their first distinctive
# words), -> the label written.
ANSWERS = {
    "исповедую православие и принадлежу к Русской православной церкви":
        "Russian Orthodox Church",
    "верю в Бога (в высшую силу), но конкретную религию не исповедую":
        "Believe in God, no specific religion",
    "не верю в Бога": "Atheist",
    "исповедую ислам, но не являюсь ни суннитом, ни шиитом":
        "Muslim (neither Sunni nor Shia)",
    "исповедую христианство, но не считаю себя ни православным, ни католиком, ни "
    "протестантом": "Non-denominational Christian",
    "исповедую ислам суннитского направления": "Sunni Islam",
    "исповедую православие, но не принадлежу к Русской православной церкви и не "
    "являюсь старообрядцем": "Orthodox (outside the Russian Orthodox Church)",
    "исповедую традиционную религию своих предков, поклоняюсь богам и силам природы":
        "Traditional religion of ancestors",
    "исповедую буддизм": "Buddhism",
    "исповедую православие, являюсь старообрядцем (старовером)": "Orthodox Old Believers",
    "исповедую протестантизм (лютеранство, баптизм, евангелизм, англиканство)":
        "Protestant",
    "исповедую ислам шиитского направления": "Shia Islam",
    "исповедую католицизм": "Catholic",
    "исповедую иудаизм": "Judaism",
    "исповедую восточные религии и духовные практики (индуизм, кришнаизм, другие "
    "направления)": "Eastern religions and spiritual practices",
    "исповедую пятидесятничество": "Pentecostalism",
    "другое": "Other religion",
    "затрудняюсь ответить": "Don't know",
}
# Questions with one answer each, whose shares therefore all rest on the
# subject's whole n: they pin n down together with the religion card.
SINGLE_ANSWER = ("Пол", "Возраст", "Образование", "Ежемесячный доход",
                 "Материальное положение семьи", "Род занятий",
                 "Скажите, пожалуйста, кто Вы по национальности",
                 "Тип населённого пункта")
LOWEST, HIGHEST = 100, 3000
SLACK = 1e-6  # of a respondent: the workbook keeps full floating-point shares


def folded(text: str) -> str:
    return " ".join(str(text).replace("ё", "е").replace("Ё", "Е").split()).lower()


def respondents(shares: list[float]) -> int | None:
    """The smallest n for which every share (in %) is a whole count of n."""
    shares = [s for s in shares if s]
    for n in range(LOWEST, HIGHEST + 1):
        if all(abs(s * n / 100 - round(s * n / 100)) < SLACK for s in shares):
            return n
    return None


def blocks(rows: list[list[Any]]) -> dict[str, list[tuple[str, list[Any]]]]:
    """{question heading: [(answer, row)]}: a heading is a row with text in the
    first column and no figures."""
    out: dict[str, list[tuple[str, list[Any]]]] = {}
    current = None
    for row in rows:
        head = str(row[0]).strip() if row and row[0] not in (None, "") else ""
        figures = [c for c in row[1:] if isinstance(c, (int, float))]
        if head and not figures:
            current = head
            out[current] = []
        elif head and current is not None:
            out[current].append((head, row))
    return out


def read(blob: bytes) -> tuple[dict[str, dict[str, float]], dict[str, int], dict[str, float]]:
    """({subject: {label: %}}, {subject: n}, {label: % for Russia})."""
    import xlrd

    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    rows = [sheet.row_values(i) for i in range(sheet.nrows)]
    names = {folded(s): s for s in SUBJECTS}
    header = next(i for i, r in enumerate(rows) if any(folded(c) in names for c in r))
    columns = {names.get(folded(c), str(c).strip()): j for j, c in enumerate(rows[header])
               if folded(c)}
    unknown = [c for c in columns if c not in SUBJECTS]
    missing = [s for s in SUBJECTS if s not in columns]
    if unknown or missing:
        raise SystemExit(f"russia_religion: headings not configured {unknown}; "
                         f"configured and absent {missing}")
    whole = next((j for r in rows[:header + 1] for j, c in enumerate(r)
                  if folded(c) == "население в целом"), None)
    if whole is None:
        raise SystemExit("russia_religion: no column for the whole population")
    questions = blocks(rows[header + 1:])
    card = next((q for q in questions if q.startswith(QUESTION)), None)
    if card is None:
        raise SystemExit("russia_religion: the religion card is not in the workbook")
    answers = {folded(a): row for a, row in questions[card]}
    wanted = {folded(a): label for a, label in ANSWERS.items()}
    if set(answers) != set(wanted):
        raise SystemExit(f"russia_religion: answers not configured "
                         f"{sorted(set(answers) - set(wanted))}; configured and absent "
                         f"{sorted(set(wanted) - set(answers))}")
    others = [q for q in questions if q.startswith(SINGLE_ANSWER)]
    if len(others) != len(SINGLE_ANSWER):
        raise SystemExit(f"russia_religion: single-answer questions found: {others}")

    def cell(row: list[Any], j: int) -> float:
        value = row[j]
        return float(value) if isinstance(value, (int, float)) else 0.0

    table: dict[str, dict[str, float]] = {}
    sizes: dict[str, int] = {}
    for subject, j in columns.items():
        shares = {wanted[a]: cell(row, j) for a, row in answers.items()}
        if abs(sum(shares.values()) - 100) > 0.5:
            raise SystemExit(f"russia_religion: {subject}'s answers make "
                             f"{sum(shares.values()):.2f}%")
        pool = list(shares.values()) + [cell(row, j) for q in others for _, row in questions[q]]
        n = respondents(pool)
        if n is None:
            raise SystemExit(f"russia_religion: {subject}'s shares are no whole count of any "
                             f"n from {LOWEST} to {HIGHEST}")
        table[subject], sizes[subject] = shares, n
    national = {wanted[a]: cell(row, whole) for a, row in answers.items()}
    return table, sizes, national


def country_row(national: dict[str, float], respondents: int) -> dict[str, Any]:
    """Russia's shares as weighted counts of ``respondents``, largest first.

    The shares are Sreda's, weighted by the subjects' populations, so the
    counts are respondents re-weighted, not people who answered so: they add
    up to the survey's whole sample, as the European Social Survey's pooled
    national rows do."""
    total = sum(national.values())
    if abs(total - 100) > 0.5:
        raise SystemExit(f"russia_religion: Russia's answers make {total:.2f}%")
    groups = [{"group": g, "pct": round(p, 1), "count": round(p / total * respondents)}
              for g, p in national.items() if p > 0]
    return {"field": "religion", "respondents": respondents,
            "groups": sorted(groups, key=lambda r: (-r["pct"], r["group"]))}


def build(blob: bytes) -> list[dict[str, Any]]:
    table, sizes, national = read(blob)
    log(f"  {len(table)} subjects, {sum(sizes.values()):,} respondents in all "
        f"(n from {min(sizes.values())} to {max(sizes.values())})")
    log("  Russia: " + ", ".join(f"{k} {v:.1f}" for k, v in
                                 sorted(national.items(), key=lambda kv: -kv[1])))
    # The country's row, for a curated country record (an adapter cannot reach
    # admin0): Sreda's population-weighted shares at the workbook's full
    # precision, and as weighted counts of the respondents -- the convention
    # the European Social Survey's pooled rows follow.
    log("  country " + json.dumps(country_row(national, sum(sizes.values())),
                                  ensure_ascii=False))
    units = json.loads((SITE / "admin1" / "RUS.units.json").read_text())
    by_code = {u.get("iso_3166_2"): u for u in units}
    lost = [s for s, code in SUBJECTS.items() if code not in by_code]
    if lost:
        raise SystemExit(f"russia_religion: no polygon carries the code of {lost}")
    records = []
    for subject, code in SUBJECTS.items():
        n = sizes[subject]
        if n < 100:
            log(f"  {subject}: {n} respondents, left out")
            continue
        unit = by_code[code]
        rows = sorted(({"group": g, "pct": round(p, 1)} for g, p in table[subject].items()
                       if p > 0), key=lambda r: (-r["pct"], r["group"]))
        precision = " Low precision: fewer than 300 respondents." if n < 300 else ""
        records.append(record(
            f"RUS-ARENA-{code}", unit["name"], level="admin1", parent="RUS", country="RUS",
            match_by="shape_id", shape_id=unit["id"],
            religion=rows, religion_year=YEAR,
            religion_basis="survey estimate: self-identification, adults 18+",
            religion_note=(
                "Sreda's Arena survey (fieldwork by FOM, MegaFOM omnibus, 29 May-25 June "
                "2012, face to face at home), adults 18 and over; "
                f"{n} respondents in this subject. One answer from a card: the statement "
                "that fits the respondent best -- 'Russian Orthodox Church' is 'I profess "
                "Orthodoxy and belong to the Russian Orthodox Church', 'Believe in God, no "
                "specific religion' is 'I believe in God (a higher power) but profess no "
                "particular religion', 'Atheist' is 'I do not believe in God'. Sreda's "
                "shares as published, the respondents' own answers with no weighting within "
                "the subject." + precision + " A survey estimate: no Russian census since "
                "1937 has asked religion."),
            sources=[{"field": "religion", "name": SOURCE, "url": PAGE, "license": LICENCE,
                      "year": YEAR}]))
    left = [f"{name} ({code})" for code, name in NOT_SURVEYED.items()]
    log(f"  {len(records)} records; not surveyed: {', '.join(left)}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    blob = http_get(WORKBOOK, binary=True, timeout=300)
    log(f"  {WORKBOOK}: {len(blob):,} bytes")
    records = build(blob)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
