#!/usr/bin/env python3
"""Czechia: nationality, religious belief and mother tongue by kraj and okres,
from the 2021 census (SLDB 2021) open data.

The Czech Statistical Office publishes the census as one plain CSV per table
under "Výsledky sčítání 2021 - otevřená data": a long file with one row per
territory and category, the territory's kind in ``uzemi_cis`` (100 the 14
kraje, 101 the 77 okresy, 43 the municipalities) and the category's label in
the table's own ``*_txt`` column. The page and the three files used here were
requested on a runner and their columns and category lists read before this
was written; the nationality file alone is 76 MB because it repeats 79
nationalities for every one of 6,254 municipalities.

**Three questions, three shapes.**

Nationality (``narodnost``) was voluntary in 2021 and a person could declare
two; the file counts every declaration ("Česká celkem" is everyone who named
Czech, alone or beside another) and carries no row for the third of the
country that left the question blank. So this is multi-response: each share is
the percentage of the population that named that nationality, the shares of a
territory do not sum to 100, and the note on every record says so. The one
composition ČSÚ does not publish, single-nationality persons, cannot be
derived from it.

Religious belief (``vira``) is one answer per person and partitions the
population: no religious belief, believers of a registered church (one row
each), believers who wrote in a tradition or a belief rather than a church
("katolická víra", "křesťanství", "Jedi"), believers of no church, and not
stated. The churches are shown at the size ČSÚ publishes them where they have
an English name that means something on a world map; the rest are summed as
"Other Christian" or "Other religion" by what they are; a written "catholic"
is kept apart from the Roman Catholic Church's own count; a written "atheism"
or "agnosticism" is counted with the tick-box "no religious belief", which is
what it says. Nothing is dropped: a row not in the table is summed as
"Other religion" and named in the log, and a territory whose rows do not sum
to its population stops the build.

Mother tongue (``jazyk1``, "s jedním mateřským jazykem") lists thirteen
languages for people who named exactly one, and the not-stated. People who
named two mother tongues, or a single language outside the thirteen, are in
no row of that file; they are the territory's total less its rows, and are
kept as one bar so labelled rather than renormalised away. The companion file
``jazyk`` counts every mention ("Český celkem") and would sum past the
population; it is not used.

**Names.** ČSÚ writes the kraje as geoBoundaries does. Its okresy are Czech
("Praha-východ", "Brno-město", "Plzeň-sever") where the boundary file has
English ("Prague-East", "Brno-City", "Plzeň-North"); the record carries the
boundary file's spelling as an alias. Each okres names its kraj, from a table
in this file, because the open-data rows do not.

Usage:
    python -m scripts.fetch_census.czechia
"""

from __future__ import annotations

import argparse
import csv
import io
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json,
)

PAGE = "https://csu.gov.cz/produkty/vysledky-scitani-2021-otevrena-data"
DOCS = "https://csu.gov.cz/docs/107508/"
FILES = {
    "ethnicity": DOCS + "8c121222-8d78-85ed-95d8-dc86246c5ba0/sldb2021_narodnost.csv?version=1.0",
    "religion": DOCS + "4250766c-69e6-3845-0eb4-580f7a692558/sldb2021_vira.csv?version=2.0",
    "language": DOCS + "87997b45-9487-ccd0-980c-1b879f337058/sldb2021_jazyk1.csv?version=1.0",
}
LABEL_COLUMN = {"ethnicity": "narodnost_txt", "religion": "vira_txt", "language": "jazyk_txt"}
SOURCE = "Czech Statistical Office (ČSÚ), Population and Housing Census 2021 (SLDB 2021), open data"
LICENCE = "ČSÚ open data (free reuse with attribution)"
YEAR = 2021
LEVELS = {"100": "admin1", "101": "admin2"}
EXPECTED = {"admin1": 14, "admin2": 77}
NOT_STATED = "Nezjištěno"

NATIONALITY = {
    "Afghánská": "Afghan", "Albánská": "Albanian", "Americká (USA)": "American",
    "Anglická": "English", "Arabská": "Arab", "Arménská": "Armenian",
    "Australská": "Australian", "Azerbájdžánská": "Azerbaijani", "Baskická": "Basque",
    "Belgická": "Belgian", "Běloruská": "Belarusian", "Bosenská (muslimská)": "Bosniak",
    "Britská": "British", "Bulharská": "Bulgarian", "Čečenská": "Chechen",
    "Černohorská": "Montenegrin", "Česká": "Czech", "Československá": "Czechoslovak",
    "Čínská": "Chinese", "Dánská": "Danish", "Estonská": "Estonian",
    "Evropská": "European", "Finská": "Finnish", "Francouzská": "French",
    "Galicijská": "Galician", "Gruzínská": "Georgian", "Chorvatská": "Croatian",
    "Indická": "Indian", "Irácká": "Iraqi", "Irská": "Irish", "Islandská": "Icelandic",
    "Italská": "Italian", "Japonská": "Japanese", "Jiná": "Other",
    "Kanadská": "Canadian", "Katalánská": "Catalan", "Kazašská": "Kazakh",
    "Korejská": "Korean", "Kurdská": "Kurdish", "Kyrgyzská": "Kyrgyz",
    "Litevská": "Lithuanian", "Lotyšská": "Latvian", "Lužickosrbská": "Sorbian",
    "Maďarská": "Hungarian", "Makedonská": "Macedonian", "Moldavská": "Moldovan",
    "Mongolská": "Mongolian", "Moravská": "Moravian", "Německá": "German",
    "Nizozemská": "Dutch", "Norská": "Norwegian", "Palestinská": "Palestinian",
    "Polská": "Polish", "Portugalská": "Portuguese", "Rakouská": "Austrian",
    "Romská": "Roma", "Rumunská": "Romanian", "Rusínská": "Rusyn", "Ruská": "Russian",
    "Řecká": "Greek", "Skotská": "Scottish", "Slezská": "Silesian",
    "Slovenská": "Slovak", "Slovinská": "Slovene", "Srbská": "Serbian",
    "Syrská": "Syrian", "Španělská": "Spanish", "Švédská": "Swedish",
    "Švýcarská": "Swiss", "Tádžická": "Tajik", "Turecká": "Turkish",
    "Turkmenská": "Turkmen", "Ukrajinská": "Ukrainian", "Uzbecká": "Uzbek",
    "Valonská": "Walloon", "Velšská": "Welsh", "Vietnamská": "Vietnamese",
    "Vlámská": "Flemish", "Židovská": "Jewish",
}
# Every ČSÚ religion row, to the bar it is shown as. Named churches with a
# world-map meaning keep their own bar; the small registered churches are
# summed by what they are. A label absent here stops the build.
RELIGION = {
    "Bez náboženské víry": "No religion",
    "Církev římskokatolická": "Roman Catholic",
    "Církev řeckokatolická": "Greek Catholic",
    "Českobratrská církev evangelická": "Evangelical Church of Czech Brethren",
    "Církev československá husitská": "Czechoslovak Hussite",
    "Pravoslavná církev v českých zemích": "Orthodox",
    "Ruská pravoslavná církev, podvorje patriarchy moskevského a celé Rusi v České republice": "Orthodox",
    "Slezská církev evangelická augsburského vyznání": "Lutheran",
    "Evangelická církev augsburského vyznání v České republice": "Lutheran",
    "Luterská evangelická církev a. v. v České republice": "Lutheran",
    "Náboženská společnost Svědkové Jehovovi": "Jehovah's Witnesses",
    "Církev adventistů sedmého dne": "Seventh-day Adventist",
    "Církev Ježíše Krista Svatých posledních dnů v České republice": "Latter-day Saints",
    "Federace židovských obcí v České republice": "Judaism",
    "islám": "Islam",
    "Ústředí muslimských obcí": "Islam",
    "buddhismus": "Buddhism",
    "Buddhismus Diamantové cesty linie Karma Kagjü": "Buddhism",
    "hinduismus": "Hinduism",
    "Česká hinduistická náboženská společnost": "Hinduism",
    "Mezinárodní společnost pro vědomí Krišny, Hnutí Hare Krišna": "Hinduism",
    "Višva Nirmala Dharma": "Hinduism",
    # Other Christian churches and societies registered in Czechia.
    "Apoštolská církev": "Other Christian",
    "Bratrská jednota baptistů": "Other Christian",
    "Církev bratrská": "Other Christian",
    "Evangelická církev metodistická": "Other Christian",
    "Jednota bratrská": "Other Christian",
    "Křesťanské sbory": "Other Christian",
    "Novoapoštolská církev v ČR": "Other Christian",
    "Starokatolická církev v ČR": "Other Christian",
    "Církev Křesťanská společenství": "Other Christian",
    "Anglikánská církev": "Other Christian",
    "Církev živého Boha": "Other Christian",
    "Obec křesťanů v České republice": "Other Christian",
    "Církev sjednocení (moonisté)": "Other Christian",
    "Církev Nová naděje": "Other Christian",
    "Církev Slovo života": "Other Christian",
    "Církev víry": "Other Christian",
    "Církev Svatého Řehoře Osvětitele": "Other Christian",
    "Armáda spásy - církev": "Other Christian",
    "Církev Nový Život": "Other Christian",
    "Církev Oáza": "Other Christian",
    "Kněžské bratrstvo svatého Pia X.": "Other Christian",
    "Společenství baptistických sborů": "Other Christian",
    "Křesťanská církev essejská": "Other Christian",
    # Write-in beliefs that name a tradition but no church. A written
    # "catholic" is not the Roman Catholic Church's count and is not folded
    # into it.
    "katolická víra (katolík)": "Catholic (unspecified)",
    "protestantská/evangelická víra (protestant, evangelík)": "Protestant (unspecified)",
    "křesťanství": "Christian (unspecified)",
    "judaismus": "Judaism",
    "sikhismus": "Sikhism",
    "Théravádový buddhismus": "Buddhism",
    "Společenství buddhismu v České republice": "Buddhism",
    # Write-ins of no belief, entered in the believer's box. They mean what
    # they say, and are counted with the tick-box "no religious belief".
    "ateismus": "No religion",
    "agnosticismus": "No religion",
    # Other beliefs, including the parody answers ČSÚ lists as their own rows.
    "Náboženská společnost českých unitářů": "Other religion",
    "Scientologická církev": "Other religion",
    "Hnutí Grálu": "Other religion",
    "Hnutí Nového věku (New Age)": "Other religion",
    "esoterismus": "Other religion",
    "pohanství": "Other religion",
    "druidismus": "Other religion",
    "animismus": "Other religion",
    "šintoismus": "Other religion",
    "taoismus": "Other religion",
    "konfucianismus": "Other religion",
    "zoroastrismus": "Other religion",
    "deismus": "Other religion",
    "satanismus": "Other religion",
    "rastafariánství": "Other religion",
    "Bahá'í víra": "Other religion",
    "Společenství Josefa Zezulky": "Other religion",
    "Jedi": "Other religion",
    "Sith": "Other religion",
    "pastafariánství": "Other religion",
    "Jiné": "Other religion",
    "věřící - nehlásící se k žádné církvi ani náboženské společnosti": "Believer, no church",
    "Věřící - nehlásící se k žádné církvi ani náboženské společnosti": "Believer, no church",
    "věřící - hlásící se k církvi - název neuveden": "Believer, church not named",
    "Neuvedeno": "Not stated",
    NOT_STATED: "Not stated",
}
LANGUAGE = {
    "Český jazyk": "Czech", "Slovenský jazyk": "Slovak", "Anglický jazyk": "English",
    "Německý jazyk": "German", "Ruský jazyk": "Russian", "Polský jazyk": "Polish",
    "Ukrajinský jazyk": "Ukrainian", "Vietnamský jazyk": "Vietnamese",
    "Maďarský jazyk": "Hungarian", "Čínský jazyk": "Chinese", "Romský jazyk": "Romani",
    "Moravský jazyk": "Moravian", "Slezský jazyk": "Silesian",
    # The kraje and okresy list languages the municipal rows do not.
    "Francouzský jazyk": "French", "Italský jazyk": "Italian", "Španělský jazyk": "Spanish",
    "Bulharský jazyk": "Bulgarian", "Rumunský jazyk": "Romanian", "Řecký jazyk": "Greek",
    "Arabský jazyk": "Arabic", "Mongolský jazyk": "Mongolian", "Srbský jazyk": "Serbian",
    "Chorvatský jazyk": "Croatian", "Běloruský jazyk": "Belarusian",
    "Kazašský jazyk": "Kazakh", "Turecký jazyk": "Turkish", "Japonský jazyk": "Japanese",
    "Korejský jazyk": "Korean", "Portugalský jazyk": "Portuguese",
    "Nizozemský jazyk": "Dutch", "Švédský jazyk": "Swedish", "Hebrejský jazyk": "Hebrew",
    "Arménský jazyk": "Armenian", "Gruzínský jazyk": "Georgian", "Perský jazyk": "Persian",
    "Kurdský jazyk": "Kurdish", "Rusínský jazyk": "Rusyn", "Lužickosrbský jazyk": "Sorbian",
    "Makedonský jazyk": "Macedonian", "Litevský jazyk": "Lithuanian",
    "Lotyšský jazyk": "Latvian", "Norský jazyk": "Norwegian", "Dánský jazyk": "Danish",
    "Finský jazyk": "Finnish", "Hindský jazyk": "Hindi", "Uzbecký jazyk": "Uzbek",
    "Tádžický jazyk": "Tajik", "Albánský jazyk": "Albanian", "Slovinský jazyk": "Slovene",
    "Bosenský jazyk": "Bosnian", "Estonský jazyk": "Estonian", "Islandský jazyk": "Icelandic",
    "Irský jazyk": "Irish", "Katalánský jazyk": "Catalan", "Thajský jazyk": "Thai",
    "Filipínský jazyk": "Filipino", "Indonéský jazyk": "Indonesian",
    "Malajský jazyk": "Malay", "Nepálský jazyk": "Nepali", "Bengálský jazyk": "Bengali",
    "Urdský jazyk": "Urdu", "Paštský jazyk": "Pashto", "Ázerbájdžánský jazyk": "Azerbaijani",
    "Kyrgyzský jazyk": "Kyrgyz", "Turkmenský jazyk": "Turkmen", "Moldavský jazyk": "Moldovan",
    "Latinský jazyk": "Latin", "Esperanto": "Esperanto", "Znakový jazyk": "Sign language",
    "Český znakový jazyk": "Czech Sign Language",
    NOT_STATED: "Not stated",
}
LANGUAGE_REMAINDER = "Other language or two mother tongues"
# Rows seen but not named above, reported once at the end of the run so
# the next run can name them; until then they sit in the remainder bar,
# which is exactly what "other language" means.
UNNAMED: dict[str, dict[str, int]] = {"ethnicity": {}, "religion": {}, "language": {}}
NOTES = {
    "ethnicity": ("Nationality (národnost), SLDB 2021. Answering was voluntary and about a "
                  "third of the country left it blank; a person could declare two "
                  "nationalities and every declaration is counted, so each share is the "
                  "percentage of the population that named that nationality, and the "
                  "shares neither sum to 100 nor account for those who did not answer."),
    "religion": ("Religious belief, SLDB 2021: one answer per person, voluntary. Believers "
                 "are shown by church where the church has a world-map name; the other "
                 "registered churches are summed as Other Christian or Other religion. "
                 "Believers of no church, no religious belief and Not stated are kept as "
                 "their own bars."),
    "language": ("Mother tongue, SLDB 2021, for people who named exactly one of the "
                 "thirteen languages ČSÚ publishes. People who named two mother tongues "
                 "or a language outside those thirteen are the territory's total less its "
                 "rows, kept as one bar so labelled."),
}

# Okresy by their kraj, in ČSÚ's own order (the file lists them so); the
# open-data rows do not carry the kraj, and a district under the wrong
# region would be the invisible kind of mismatch.
OKRES_KRAJ = {
    "Hlavní město Praha": ["Praha"],
    "Středočeský kraj": ["Benešov", "Beroun", "Kladno", "Kolín", "Kutná Hora", "Mělník",
                         "Mladá Boleslav", "Nymburk", "Praha-východ", "Praha-západ",
                         "Příbram", "Rakovník"],
    "Jihočeský kraj": ["České Budějovice", "Český Krumlov", "Jindřichův Hradec", "Písek",
                       "Prachatice", "Strakonice", "Tábor"],
    "Plzeňský kraj": ["Domažlice", "Klatovy", "Plzeň-město", "Plzeň-jih", "Plzeň-sever",
                      "Rokycany", "Tachov"],
    "Karlovarský kraj": ["Cheb", "Karlovy Vary", "Sokolov"],
    "Ústecký kraj": ["Děčín", "Chomutov", "Litoměřice", "Louny", "Most", "Teplice",
                     "Ústí nad Labem"],
    "Liberecký kraj": ["Česká Lípa", "Jablonec nad Nisou", "Liberec", "Semily"],
    "Královéhradecký kraj": ["Hradec Králové", "Jičín", "Náchod", "Rychnov nad Kněžnou",
                             "Trutnov"],
    "Pardubický kraj": ["Chrudim", "Pardubice", "Svitavy", "Ústí nad Orlicí"],
    "Kraj Vysočina": ["Havlíčkův Brod", "Jihlava", "Pelhřimov", "Třebíč", "Žďár nad Sázavou"],
    "Jihomoravský kraj": ["Blansko", "Brno-město", "Brno-venkov", "Břeclav", "Hodonín",
                          "Vyškov", "Znojmo"],
    "Olomoucký kraj": ["Jeseník", "Olomouc", "Prostějov", "Přerov", "Šumperk"],
    "Zlínský kraj": ["Kroměříž", "Uherské Hradiště", "Vsetín", "Zlín"],
    "Moravskoslezský kraj": ["Bruntál", "Frýdek-Místek", "Karviná", "Nový Jičín", "Opava",
                             "Ostrava-město"],
}
KRAJ_OF = {okres: kraj for kraj, okresy in OKRES_KRAJ.items() for okres in okresy}
# The boundary file's spellings where they differ from ČSÚ's.
OKRES_ALIASES = {
    "Praha": ["Prague"], "Praha-východ": ["Prague-East"], "Praha-západ": ["Prague-West"],
    "Brno-město": ["Brno-City"], "Brno-venkov": ["Brno-Country"],
    "Plzeň-město": ["Plzeň-City"], "Plzeň-jih": ["Plzeň-South"], "Plzeň-sever": ["Plzeň-North"],
    "Ostrava-město": ["Ostrava-City"], "Rakovník": ["Rakovnik"],
}


def count(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def read_table(field: str) -> dict[tuple[str, str], dict[str, Any]]:
    """{(uzemi_cis, uzemi_kod): {"name", "total", "rows": {label: count}}} for
    the kraje and okresy of one open-data file."""
    label_column = LABEL_COLUMN[field]
    blob = http_get(FILES[field], binary=True, timeout=900)
    log(f"  {field}: {len(blob):,} bytes")
    units: dict[tuple[str, str], dict[str, Any]] = {}
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
    for column in ("uzemi_cis", "uzemi_kod", "uzemi_txt", "hodnota", label_column):
        if column not in (reader.fieldnames or []):
            raise SystemExit(f"czechia: {field} file has no column {column!r}; "
                             f"columns are {reader.fieldnames}")
    for row in reader:
        if row["uzemi_cis"] not in LEVELS:
            continue
        key = (row["uzemi_cis"], row["uzemi_kod"])
        unit = units.setdefault(key, {"name": row["uzemi_txt"].strip(), "total": None, "rows": {}})
        value = count(row["hodnota"])
        label = (row[label_column] or "").strip()
        if not label:
            unit["total"] = value          # the row with no category is the population
        elif value is not None:
            unit["rows"][label] = unit["rows"].get(label, 0) + value
    return units


def nationality(rows: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, n in rows.items():
        stem = label[:-len(" celkem")] if label.endswith(" celkem") else label
        english = NATIONALITY.get(stem)
        if english is None:
            UNNAMED["ethnicity"][label] = UNNAMED["ethnicity"].get(label, 0) + n
            english = "Other"
        out[english] = out.get(english, 0) + n
    return out


def religion(rows: dict[str, int], total: int, name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, n in rows.items():
        english = RELIGION.get(label)
        if english is None:
            UNNAMED["religion"][label] = UNNAMED["religion"].get(label, 0) + n
            english = "Other religion"
        out[english] = out.get(english, 0) + n
    summed = sum(out.values())
    if abs(summed - total) > max(0.005 * total, 20):
        raise SystemExit(f"czechia: {name} religion rows sum to {summed:,} against the "
                         f"population {total:,}; the rows do not partition it")
    return out


def language(rows: dict[str, int], total: int, name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, n in rows.items():
        english = LANGUAGE.get(label)
        if english is None:
            # A single language not named above belongs in the remainder bar,
            # which the subtraction below puts it in.
            UNNAMED["language"][label] = UNNAMED["language"].get(label, 0) + n
            continue
        out[english] = out.get(english, 0) + n
    remainder = total - sum(out.values())
    if remainder < 0 or remainder > 0.25 * total:
        raise SystemExit(f"czechia: {name} single-mother-tongue rows leave {remainder:,} "
                         f"of {total:,} unaccounted for; not the file this was written for")
    out[LANGUAGE_REMAINDER] = remainder
    return out


def build() -> list[dict[str, Any]]:
    log("czechia: SLDB 2021 open data, kraje and okresy")
    tables = {field: read_table(field) for field in FILES}
    keys = set(tables["religion"])
    for field, units in tables.items():
        if set(units) != keys:
            raise SystemExit(f"czechia: {field} lists {len(units)} territories, "
                             f"religion {len(keys)}")
    kraj_code = {u["name"]: kod for (cis, kod), u in tables["religion"].items() if cis == "100"}
    records = []
    for (cis, kod), unit in sorted(tables["religion"].items()):
        name, total = unit["name"], unit["total"]
        level = LEVELS[cis]
        if not total:
            raise SystemExit(f"czechia: {name} has no population row")
        fields: dict[str, Any] = {}
        fields["ethnicity"] = shares(nationality(tables["ethnicity"][(cis, kod)]["rows"]),
                                     total=total) or gap(NOT_AVAILABLE)
        fields["religion"] = shares(religion(unit["rows"], total, name), total=total) \
            or gap(NOT_AVAILABLE)
        fields["language"] = shares(language(tables["language"][(cis, kod)]["rows"], total, name),
                                    total=total) or gap(NOT_AVAILABLE)
        for key in ("ethnicity", "religion", "language"):
            fields[f"{key}_note"] = NOTES[key]
        if level == "admin1":
            parent, parent_name, aliases = "CZE", None, []
        else:
            kraj = KRAJ_OF.get(name)
            if kraj is None or kraj not in kraj_code:
                raise SystemExit(f"czechia: okres {name!r} is not under any kraj in OKRES_KRAJ")
            parent, parent_name = f"CZE-{kraj_code[kraj]}", kraj
            aliases = OKRES_ALIASES.get(name, [])
        records.append(record(
            f"CZE-{kod}", name, level=level, parent=parent, parent_name=parent_name,
            country="CZE", codes={"csu_uzemi_kod": kod, "csu_uzemi_cis": cis},
            aliases=aliases,
            population=measure(int(total), year=YEAR, source=SOURCE),
            sources=[{"field": "population/religion/ethnicity/language", "name": SOURCE,
                      "url": PAGE, "license": LICENCE}],
            **fields,
        ))
    by_level = {"admin1": 0, "admin2": 0}
    for r in records:
        by_level[r["level"]] += 1
    log(f"  {by_level}")
    if by_level != EXPECTED:
        raise SystemExit(f"czechia: expected {EXPECTED}, read {by_level}")
    for field, seen in UNNAMED.items():
        for label, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            log(f"  ! {field} row {label!r} has no English name here: {n:,} people "
                f"summed across territories, shown as "
                f"{'the remainder bar' if field == 'language' else 'Other'}")
    sample = next(r for r in records if r["level"] == "admin1")
    for key in ("ethnicity", "religion", "language"):
        top = sample[key][0] if isinstance(sample[key], list) and sample[key] else None
        log(f"  {sample['name']} {key}: {len(sample[key])} bars, largest "
            f"{top['group'] if top else '-'} {top['pct'] if top else '-'}%")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(PROCESSED / "czechia_kraj.json", [r for r in records if r["level"] == "admin1"])
    write_json(PROCESSED / "czechia_okres.json", [r for r in records if r["level"] == "admin2"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
