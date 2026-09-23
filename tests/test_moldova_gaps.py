"""Moldova's seven units the Europe reader refused.

Every table below is the one the probes printed: the four northern
districts' Romanian articles (commit 1381334) and the Transnistria article's
table of administrative divisions (commit 4906820).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import moldova_gaps as m  # noqa: E402

EDINET = [["Moldoveni", "59.195", "72,73%"], ["Ucraineni", "16.084", "19,76%"],
          ["Ruși", "5.083", "6,24%"], ["Țigani", "499", "0,61%"],
          ["Găgăuzi", "143", "0,17%"], ["Bulgari", "91", "0,11%"], ["Alții", "294", ""]]
FALESTI = [["Moldoveni/Români", "76&nbsp;169", "84,33%"], ["Ucraineni", "10&nbsp;711", "11,86%"],
           ["Ruși", "3&nbsp;064", "3,39%"], ["Țigani", "57", "0,06%"], ["Alții", "319", "0,36%"]]
RISCANI = [["Moldoveni Români 1", "50.391 777", "72,55% 1,12%"], ["Ucraineni", "15.632", "22,51%"],
           ["Ruși", "1.726", "2,49%"], ["Țigani", "602", "0,87%"], ["Găgăuzi", "61", "0,09%"],
           ["Bulgari", "60", "0,09%"], ["Polonezi", "42", "0,06%"], ["Alții", "163", "0,23%"]]


class TheNorthernDistricts(unittest.TestCase):
    def test_edinet_from_its_counts(self):
        # The table leaves the "others" share blank; the counts do not.
        got, why = m.ro_composition(EDINET)
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got}
        self.assertAlmostEqual(shares["Moldovan"], 72.73, places=1)
        self.assertAlmostEqual(shares["Other"], 0.36, places=1)
        self.assertAlmostEqual(sum(shares.values()), 100, places=1)

    def test_falesti_keeps_one_figure_for_two_answers(self):
        got, _ = m.ro_composition(FALESTI)
        self.assertEqual(got[0]["group"], "Moldovan or Romanian")
        self.assertAlmostEqual(got[0]["pct"], 84.33, places=1)

    def test_riscani_welded_row_is_split_back(self):
        got, _ = m.ro_composition(RISCANI)
        shares = {r["group"]: r["pct"] for r in got}
        self.assertAlmostEqual(shares["Moldovan"], 72.55, places=1)
        self.assertAlmostEqual(shares["Romanian"], 1.12, places=1)
        self.assertEqual(sum(r["count"] for r in got), 69454)

    def test_a_row_that_does_not_line_up_is_not_split(self):
        self.assertEqual(m.welded(["Alte etnii", "294", ""]), [["Alte etnii", "294", ""]])
        self.assertEqual(len(m.welded(["Moldoveni Români", "50.391", "72,55%"])), 1)

    def test_a_label_it_does_not_know_refuses_the_table(self):
        got, why = m.ro_composition(EDINET + [["Marțieni", "5", "0,01%"]])
        self.assertIsNone(got)
        self.assertIn("Marțieni", why)

    def test_a_census_named_in_the_citation_dates_the_table(self):
        body = ("{| class=wikitable\n|}\n<ref>{{Citat web |url=http://www.statistica.md/"
                "recensamint/Nationalitati_de_baza_ro.xls |titlu=''Recensământul populației "
                "2004'' }}</ref>")
        self.assertEqual(m.year_of(body), 2004)
        self.assertIsNone(m.year_of("{| class=wikitable\n|}\n"))


TRANSNISTRIA = """== Administrative divisions ==
{| class="wikitable"
! Name !! Capital !! Area !! Population (2025) !! Ethnic composition (2004)
|-
| Camenca District (Camenca, Каменка) || Camenca || km2 || 21,000 || 47.82% Moldovans, 42.55% Ukrainians, 6.89% Russians, 2.74% others
|-
| Rîbnița District (Rîbnița, Рыбница) || Rîbnița || km2 || 69,000 || 29.90% Moldovans, 45.41% Ukrainians, 17.22% Russians, 7.47% others
|-
| Dubăsari District (Dubăsari, Дубэсарь) || Dubăsari || km2 || 31,000 || 50.15% Moldovans, 28.29% Ukrainians, 19.03% Russians, 2.53% others
|-
| Grigoriopol District (Grigoriopol, Григориопол) || Grigoriopol || km2 || 40,000 || 64.83% Moldovans, 15.28% Ukrainians, 17.36% Russians, 2.26% others
|-
| Slobozia District (Slobozia, Слобозия) || Slobozia || km2 || 84,000 || 41.51% Moldovans, 21.71% Ukrainians, 26.51% Russians, 10.27% others
|-
| City of Tiraspol (Tiraspol, Тираспол) || Tiraspol || km2 || 126,306 || 18.41% Moldovans, 32.31% Ukrainians, 41.44% Russians, 7.82% others
|-
| City of Bender (Tighina, Тигина/Бендер) || Bender || km2 || 83,919 || 25.03% Moldovans, 17.98% Ukrainians, 43.35% Russians, 13.64% others
|}
"""


class Transnistria(unittest.TestCase):
    def setUp(self):
        self.saved = m.fetch
        m.fetch = lambda title, lang: (TRANSNISTRIA, title)

    def tearDown(self):
        m.fetch = self.saved

    def test_every_district_and_its_population(self):
        shares, people = m.transnistria()
        self.assertEqual(set(shares), {*m.LEFT_BANK, "Bender"})
        self.assertEqual(people["Bender"], 83919)
        self.assertEqual(people["Tiraspol"], 126306)

    def test_bender_is_read_as_the_table_gives_it(self):
        shares, _ = m.transnistria()
        self.assertEqual({r["group"]: r["pct"] for r in shares["Bender"]},
                         {"Moldovan": 25.03, "Ukrainian": 17.98, "Russian": 43.35, "Other": 13.64})


BALTI = [
    ["Grup etnic", "1959", "1970", "1979", "1989", "2004", "2014", "2024"],
    ["Număr", "%", "Număr", "%", "Număr", "%", "Număr", "%", "Număr", "%", "Număr", "%", "Număr", "%"],
    ["Moldoveni/Români", "16.100", "24.35", "29.000", "28.59", "41.400", "33.63", "63.876", "40.64", "65.079", "53.05", "56.078", "57.26", "67.606", "74.32"],
    ["Ucraineni", "16.400", "24.81", "25.800", "25.44", "33.400", "27.13", "40.804", "25.97", "29.668", "24.18", "16.976", "17.33", "12.156", "13.36"],
    ["Ruși", "20.700", "31.31", "30.300", "29.88", "33.700", "27.37", "38.309", "24.39", "24.341", "19.84", "14.982", "15.29", "9428", "10.36"],
    ["Romi", "", "", "", "", "", "", "305", "0.19", "272", "0.22", "154", "0.15", "144", "0.15"],
    ["Bulgari", "70", "0.10", "200", "0.19", "300", "0.24", "426", "0.27", "296", "0.24", "187", "0.19", "136", "0.14"],
    ["Găgăuzi", "30", "0.04", "200", "0.19", "300", "0.24", "534", "0.33", "234", "0.19", "126", "0.12", "114", "0.12"],
    ["Evrei", "11.600", "17.54", "12.900", "12.72", "10.500", "8.52", "8903", "5.66", "409", "0.33", "", "", "", ""],
    ["Alții", "", "", "", "", "", "", "2477", "1.57", "1514", "1.23", "1423", "1.45", "1067", "1,17"],
    ["Nedeclarat", "", "", "", "", "", "", "", "", "", "", "8004", "8.17", "303", "0.33"],
    ["Total", "66.100", "101.400", "123.100", "157.068", "122.669", "97.930", "90.954"],
    ["[https://statistica.gov.md/ro/rezultatele-finale Biroul Național de Statistică]"],
]


class BaltiEveryCensusSince1959(unittest.TestCase):
    def test_the_newest_column_is_read(self):
        year, column = m.latest(BALTI[0])
        self.assertEqual((year, column), (2024, 13))
        got, why = m.ro_composition(BALTI[1:], column)
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got}
        self.assertAlmostEqual(shares["Moldovan or Romanian"], 74.33, places=1)
        self.assertAlmostEqual(shares["Ukrainian"], 13.36, places=1)
        self.assertEqual(sum(r["count"] for r in got), 90954)
        # Nobody in 2024 is reported Jewish, and the 1959 figure does not leak in.
        self.assertNotIn("Jewish", shares)

    def test_a_single_census_table_reads_column_one(self):
        self.assertEqual(m.latest(["Grup etnic", "Populație", "% Procentaj"]), (None, 1))


# Balti's "Structura lingvistica" table as the runner's probe printed it from
# ro.wikipedia on 23 September 2026 (commit 64e85ca).
BALTI_LANGUAGE = [
    ["Limba", "2004", "2014", "2024"],
    ["Număr", "%", "Număr", "%", "Număr", "%"],
    ["Română", "50.558", "41.21", "41.170", "42.04", "45.488", "51.76"],
    ["Rusă", "67.833", "55.29", "46.775", "47.76", "40.521", "46.10"],
    ["Ucraineană", "3761", "3.06", "1018", "1.03", "1611", "1.83"],
    ["Romani", "N/A", "N/A", "101", "0.10", "79", "0.08"],
    ["Găgăuză", "21", "0.01", "0", "0.00", "32", "0.03"],
    ["Bulgară", "12", "0.00", "0", "0.00", "11", "0.01"],
    ["Alții", "281", "0.22", "189", "0.19", "102", "0.11"],
    ["Nedeclarată", "203", "0.16", "8673", "8.85", "35", "0.30"],
    ["Total", "122.669", "97.930", "87.879"],
    ["[https://statistica.gov.md/ro/"],
]


class BaltiLanguage(unittest.TestCase):
    def test_the_2024_column_from_its_counts(self):
        year, column = m.latest(BALTI_LANGUAGE[0])
        self.assertEqual((year, column), (2024, 5))
        got, why = m.ro_composition(BALTI_LANGUAGE[1:], column, m.RO_LANGUAGE)
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got}
        self.assertAlmostEqual(shares["Romanian"], 51.76, places=1)
        self.assertAlmostEqual(shares["Russian"], 46.11, places=1)
        # The table prints 0.30% beside 35 people; 35 of 87,879 is 0.04%.
        self.assertAlmostEqual(shares["Not declared"], 0.04, places=2)
        self.assertEqual(sum(r["count"] for r in got), 87879)

    def test_the_table_is_found_under_its_own_heading(self):
        text = ("== Structura etnică ==\n{|\n! Grup etnic !! Populație\n|-\n"
                "| Moldoveni || 10\n|}\n== Structura lingvistică ==\n{|\n"
                "! Limba !! 2024\n|-\n| Română || 10\n|-\n| Rusă || 5\n|}\n")
        table, _ = m.ro_table(text, "lingvistic", "limba")
        self.assertEqual(table[0][0], "Limba")

    def test_one_record_a_unit_carries_both_fields(self):
        a = m.row_for("Balti", "admin1", "s1", [{"group": "Moldovan", "pct": 100}],
                      year=2024, note="n", source="s", url="u")
        b = m.row_for("Balti", "admin1", "s1", [{"group": "Romanian", "pct": 100}],
                      year=2024, note="n", source="s", url="u", field="language")
        (row,) = m.merged([a, b])
        self.assertIn("ethnicity", row)
        self.assertIn("language", row)
        self.assertEqual({s["field"] for s in row["sources"]}, {"ethnicity", "language"})


class WhatTheEuropeReaderHasIsNotReplaced(unittest.TestCase):
    def test_only_lists_count_as_read(self):
        import json
        import tempfile
        from unittest import mock
        rows = [{"level": "admin1", "name": "Edinet",
                 "ethnicity": [{"group": "Moldovan", "pct": 77.4}],
                 "language": {"status": "not_available", "note": "n"}},
                {"level": "admin2", "name": "Edinet", "religion": [{"group": "x", "pct": 1}]}]
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "europe_wiki_moldova.json").write_text(json.dumps(rows))
            with mock.patch.object(m, "PROCESSED", Path(tmp)):
                self.assertEqual(m.already_read(), {"Edinet": {"ethnicity"}})
