"""The Dutch provinces' religion, which lives in an infobox and not a table."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import netherlands as m  # noqa: E402

GRONINGEN = ("68,4% geen [[Religie|gezindte]]<br />18,7% [[Protestantisme|"
             "Protestants]]<br> 6,7% overige [[Religie|gezindte]]<br> 4,9% "
             "[[Rooms-Katholieke Kerk|Rooms-katholiek]] <br />1,3% [[Moslim]]")
LIMBURG = ("46,5% [[Rooms-Katholieke Kerk|rooms-katholiek]]<br>42,1% geen "
           "[[Religie|gezindte]] <br />4,4% [[moslim]]<br />2,4% "
           "[[Protestantisme|protestant]]")


class TheInfoboxParameter(unittest.TestCase):
    """Every example here was taken from the probe, not invented."""

    def test_groningen_reads_as_the_article_prints_it(self):
        rows, why = m.shares(GRONINGEN)
        self.assertEqual(why, "")
        self.assertEqual({r["group"]: r["pct"] for r in rows},
                         {"No religion": 68.4, "Protestant": 18.7,
                          "Other religion": 6.7, "Roman Catholic": 4.9,
                          "Muslim": 1.3})
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0, places=1)

    def test_the_comma_is_a_decimal_point_and_not_a_thousands_mark(self):
        # 68,4 is sixty-eight point four. Read the other way it would be a
        # share of six hundred and eighty-four per cent.
        rows, _ = m.shares(GRONINGEN)
        self.assertEqual(rows[0]["pct"], 68.4)

    def test_every_spelling_of_the_line_break_separates_two_shares(self):
        # The same infobox uses <br />, <br> and " <br />" in one value.
        rows, _ = m.shares(GRONINGEN)
        self.assertEqual(len(rows), 5)

    def test_a_link_is_read_down_to_what_a_reader_sees(self):
        rows, _ = m.shares("50% [[Rooms-Katholieke Kerk|rooms-katholiek]]"
                           "<br>50% [[Moslim]]")
        self.assertEqual([r["group"] for r in rows],
                         ["Muslim", "Roman Catholic"])

    def test_both_vocabularies_mean_the_same_answer(self):
        # The 2015 release writes "geen gezindte", the 2025 one "Niet
        # godsdienstig". Same question, same answer, ten years apart.
        old, _ = m.shares("60% geen [[Religie|gezindte]]<br>40% [[Moslim]]")
        new, _ = m.shares("60% Niet godsdienstig<br>40% [[Moslim]]")
        self.assertEqual(old, new)

    def test_a_short_list_is_kept_and_a_long_one_refused(self):
        # Limburg's four groups add to 95.4: the infobox lists what it lists,
        # and that describes part of the province. Over 100 is different --
        # it means a group counted twice, and the arithmetic describes nobody.
        rows, why = m.shares(LIMBURG)
        self.assertEqual(why, "")
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 95.4, places=1)
        _, why = m.shares("60% geen gezindte<br>55% [[Moslim]]")
        self.assertIn("more than a whole", why)

    def test_a_label_with_no_entry_stops_the_province_rather_than_silently_going(self):
        rows, why = m.shares("60% geen gezindte<br>40% Pastafarisme")
        self.assertEqual(rows, [])
        self.assertIn("Pastafarisme", why)

    def test_one_group_written_twice_is_added_up(self):
        rows, _ = m.shares("50% geen gezindte<br>30% overige gezindte"
                           "<br>20% overig")
        self.assertEqual({r["group"]: r["pct"] for r in rows},
                         {"No religion": 50.0, "Other religion": 50.0})

    def test_a_value_that_is_not_shares_at_all_is_refused(self):
        _, why = m.shares("mostly Catholic")
        self.assertIn("is not a share", why)


class TheTwelve(unittest.TestCase):

    def test_every_province_is_named_as_the_boundary_file_names_it(self):
        import json
        path = (Path(__file__).resolve().parent.parent
                / "site" / "data" / "admin1" / "NLD.json")
        if not path.exists():
            self.skipTest("no built NLD file")
        shapes = {s["name"] for s in json.loads(path.read_text())}
        self.assertEqual(set(m.PROVINCES.values()), shapes)

    def test_the_two_titles_that_are_not_the_obvious_ones(self):
        # nl:Zeeland is a disambiguation page and nl:Limburg (Nederland) a
        # redirect; probing for them returned a 1,545-byte stub and a
        # 343-byte one.
        self.assertIn("Zeeland (provincie)", m.PROVINCES)
        self.assertIn("Limburg (Nederlandse provincie)", m.PROVINCES)
        self.assertNotIn("Zeeland", m.PROVINCES)
