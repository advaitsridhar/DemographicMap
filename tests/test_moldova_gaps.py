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
