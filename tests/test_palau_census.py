"""Palau: the 2020 census tables transcribed in the reader, and their checks. No network.

The transcriptions themselves are the fixture: they must add up as printed,
and a figure changed in any of the ways a misreading would change it must
stop the run.
"""

import unittest

from scripts.fetch_census import palau_census as pw
from scripts.fetch_census.oceania_common import load_units


def nsdp(koror: int = 11_400) -> str:
    people = {"Kayangel": 41, "Ngarchelong": 384, "Ngaraard": 396, "Ngiwal": 312,
              "Melekeok": 318, "Ngchesar": 319, "Airai": 2529, "Aimeliik": 363,
              "Ngatpang": 289, "Ngardmau": 238, "Ngeremlengui": 349, "Angaur": 114,
              "Peleliu": 470, "Koror": koror, "Sonsorol": 53, "Hatohobei": 39}
    codes = {name: code for code, name in pw.NSDP_CODES.items()}
    series = ['<Series INDICATOR="LP_PE_NUM"><Obs TIME_PERIOD="2015" OBS_VALUE="17661" />'
              '<Obs TIME_PERIOD="2020" OBS_VALUE="17614" /></Series>']
    series += [f'<Series INDICATOR="PLW_LP_{codes[name]}_PE_NUM"><Obs TIME_PERIOD="2020" '
               f'OBS_VALUE="{n}" /></Series>' for name, n in people.items()]
    return ('<?xml version="1.0"?><message:StructureSpecificData xmlns:message="urn:m">'
            f'<message:DataSet>{"".join(series)}</message:DataSet>'
            '</message:StructureSpecificData>')


class Transcriptions(unittest.TestCase):

    def test_every_table_adds_up_and_koror_is_its_hamlets(self):
        tables = pw.read_tables()
        self.assertEqual(tables["6"]["All Persons"]["Total"], 17_614)
        self.assertEqual(tables["23"]["All Persons"]["Madalaii"], 2_284)
        self.assertEqual(tables["10r"]["Modekngei"]["Ngatpang"], 114)

    def test_a_misread_figure_breaks_its_line(self):
        text = pw.TABLE_6.replace("Under 5 years | 1,013 4 19", "Under 5 years | 1,013 4 18")
        with self.assertRaises(SystemExit):
            pw.parse(text, pw.STATE_COLUMNS, "6")

    def test_figures_read_into_the_wrong_columns_break_a_column(self):
        text = pw.TABLE_6.replace("Under 5 years | 1,013 4 19", "Under 5 years | 1,013 19 4")
        with self.assertRaises(SystemExit):
            pw.read_ages(text, pw.STATE_COLUMNS, "6")

    def test_a_median_its_groups_do_not_give_stops_the_run(self):
        text = pw.TABLE_23.replace("Median | 37.4 37.2", "Median | 37.4 38.2")
        with self.assertRaises(SystemExit):
            pw.read_ages(text, pw.HAMLET_COLUMNS, "23")

    def test_the_data_page_counts_koror_with_the_people_from_elsewhere(self):
        tables = pw.read_tables()
        pw.agrees_with_nsdp(pw.read_nsdp(nsdp()), tables)
        with self.assertRaises(SystemExit):
            pw.agrees_with_nsdp(pw.read_nsdp(nsdp(koror=11_199)), tables)


class Records(unittest.TestCase):

    def test_states_koror_hamlets_and_the_reason_for_the_rest(self):
        admin1, admin2 = load_units("PLW", "admin1"), load_units("PLW", "admin2")
        if not admin1 or not admin2:
            self.skipTest("no PLW units in this checkout")
        records = pw.build(pw.read_tables(), admin1, admin2)
        self.assertEqual(len(records), len(admin1) + len(admin2))
        by_name = {(r["level"], r["name"]): r for r in records}
        koror = by_name[("admin1", "Koror")]
        self.assertEqual(koror["population"]["value"], 11_199)
        self.assertIn("11,400", koror["population_note"])
        self.assertEqual(koror["median_age"]["value"], 37.4)
        self.assertEqual(round(sum(s["pct"] for s in koror["language"])), 100)
        self.assertEqual(by_name[("admin2", "Medalaii")]["population"]["value"], 2_284)
        # A ratio's note gives the men and women it is made of.
        self.assertIn("(Table 23): 1,308 males, 976 females.",
                      by_name[("admin2", "Medalaii")]["sex_ratio_note"])
        self.assertEqual(by_name[("admin2", "Idid 03")]["population"]["value"], 537)
        gaps = [r for r in records if "value" not in r["population"]]
        self.assertEqual(len(gaps), len(admin2) - len(pw.HAMLETS))
        self.assertIn("Koror", gaps[0]["population"]["note"])
        self.assertEqual(len({r["id"] for r in records}), len(records))
        # Hatohobei's 39 people carry their count and median, not a ratio or shares.
        hatohobei = by_name[("admin1", "Hatohobei")]
        self.assertEqual(hatohobei["population"]["value"], 39)
        self.assertIn("value", hatohobei["median_age"])
        self.assertIn("the median of the 39 people", hatohobei["median_age_note"])
        for field in ("sex_ratio", "religion", "language", "ethnicity"):
            self.assertEqual(hatohobei[field]["status"], "not_available", field)
            self.assertIn("39 people", hatohobei[field]["note"])
        self.assertIsInstance(by_name[("admin1", "Angaur")]["religion"], list)


if __name__ == "__main__":
    unittest.main()
