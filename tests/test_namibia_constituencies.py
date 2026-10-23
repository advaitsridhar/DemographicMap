"""Namibia's 2023 census by constituency, from the census site's region pages
(scripts/fetch_census/namibia_constituencies)."""

import html
import json
import unittest
from unittest import mock

from scripts.fetch_census import namibia_constituencies as nc


def page(*tables):
    """A region page as the census site writes it: each table a chart
    widget's data-chart_data attribute."""
    return "".join(f'<div class="chart" data-chart_data="{html.escape(json.dumps(t))}"></div>'
                   for t in tables)


def table(columns, rows):
    return {"columns": [{"title": c} for c in columns], "data": rows}


POP = ["Constituency", "Population", "Area in km²", "Persons per km²"]
# Rows as the site printed them in 2025 (Erongo, Hardap, Omaheke, Khomas, Oshikoto).
ERONGO = table(POP, [[" Arandis", " 13 542", " 13 519.74", "1.0"],
                     ["Daures", " 14 601", " 17 786.64", "0.8"]])
LOCALITIES = table(["Constituency", "Male", "Female", "Area in km²", "Persons per km²",
                    "Population"], [["Arandis", " 3 102", " 2 624", " 30.6625 ", " 186.7 ", " 5 726"]])
HARDAP = table(POP, [["Gibeon", "8034", "10156.39", "0.8"]])
OMAHEKE = table(POP, [["Epukiro", "7 880", "10 926.12", "0.7"],
                      ["Otjinene", "12 415", "6 420.01", "1.9"]])
KHOMAS = table(POP, [["Moses//Garoeb", "68932", "32.37", "2129.2"],
                     ["Tobias Hainyeko", "67067", "18.51", "3623.3"]])
OSHIKOTO = table(POP, [["Onayena", "16669", "371.47.5", "44.9"], ["Oniipa", "3372", "371.47", "9.1"]])


def at(rows, url):
    """A page's rows as main() keeps them, each with the page's address."""
    return {k: {**row, "url": url} for k, row in rows.items()}


class NamibiaConstituenciesTest(unittest.TestCase):
    def test_the_population_table_is_the_one_with_areas(self):
        rows = nc.constituencies(page(ERONGO, LOCALITIES))
        self.assertEqual(rows["daures"], {"name": "Daures", "population": 14_601,
                                          "area": 17_786.64})
        self.assertEqual(len(rows), 2)
        self.assertIsNone(nc.constituencies(page(OSHIKOTO))["onayena"]["area"])
        with self.assertRaises(SystemExit):
            nc.constituencies(page(LOCALITIES))

    def test_a_region_that_does_not_make_its_count_is_left_out(self):
        pages = {"erongo": nc.constituencies(page(ERONGO)),
                 "oshikoto-region": nc.constituencies(page(OSHIKOTO))}
        with mock.patch.object(nc, "log"):
            good = nc.checked(pages, {"erongo": 28_143, "oshikoto": 257_302})
        self.assertEqual(sorted(good), ["erongo"])

    def test_a_polygon_gets_the_count_only_on_the_census_ground(self):
        admin1 = [{"id": "E", "name": "Erongo"}, {"id": "H", "name": "Hardap"},
                  {"id": "O", "name": "Omaheke"}, {"id": "K", "name": "Khomas"}]
        admin2 = [{"id": "8085530B95120422656670", "name": "Daures", "parent": "E"},
                  {"id": "8085530B21041761137658", "name": "Gibeon", "parent": "H"},
                  {"id": "8085530B69443629768018", "name": "Epukiro and Otjinene", "parent": "O"},
                  {"id": "8085530B20678123815895", "name": "Moses Garoeb and Tobias Hainyeko",
                   "parent": "K"}]
        regions = {"erongo": at(nc.constituencies(page(ERONGO)), "u"),
                   "hardap": at(nc.constituencies(page(HARDAP)), "h"),
                   "omaheke": at(nc.constituencies(page(OMAHEKE)), "o"),
                   "khomas": at(nc.constituencies(page(KHOMAS)), "k")}
        with mock.patch.object(nc, "log"):
            recs = {r["name"]: r for r in nc.build(regions, admin1, admin2)}
        # Gibeon is drawn over 50,525 km2 against the census's 10,156; the two
        # Windhoek constituencies' 50.9 km2 against 53.2 is 4.6%, over the 2%
        # allowed where 2,673 people live to the km2.
        self.assertEqual(sorted(recs), ["Daures", "Epukiro and Otjinene"])
        self.assertEqual(recs["Daures"]["population"]["value"], 14_601)
        self.assertEqual(recs["Daures"]["sources"][0]["url"], "u")
        self.assertEqual(recs["Epukiro and Otjinene"]["population"]["value"], 7_880 + 12_415)
        self.assertIn("Epukiro and Otjinene constituencies added together",
                      recs["Epukiro and Otjinene"]["population_note"])
        self.assertIn("17,346 km² in the census's tables, 17,510 km²",
                      recs["Epukiro and Otjinene"]["population_note"])

    def test_a_constituency_cites_the_page_its_row_is_on(self):
        # Kavango East's and West's pages both feed the map's one Kavango;
        # Mashare is on the first page only.
        east = table(POP, [["Mashare", "19 478", "9 139.89", "2.1"]])
        west = table(POP, [["Mpungu", "21098", "7976.76", "2.6"]])
        pages = {"kavango-east-region": at(nc.constituencies(page(east)), "east"),
                 "kavango-west-region": at(nc.constituencies(page(west)), "west")}
        with mock.patch.object(nc, "log"):
            regions = nc.checked(pages, {"kavango": 19_478 + 21_098})
            recs = {r["name"]: r for r in nc.build(
                regions, [{"id": "V", "name": "Kavango"}],
                [{"id": "8085530B8620298556926", "name": "Mashare", "parent": "V"},
                 {"id": "8085530B94702234009846", "name": "Mpungu", "parent": "V"}])}
        self.assertEqual([s["url"] for s in recs["Mashare"]["sources"]], ["east"])
        self.assertEqual([s["url"] for s in recs["Mpungu"]["sources"]], ["west"])

    def test_gibeon_is_gibeon_and_daweb(self):
        # Daweb, made in 2013, has no polygon; with Gibeon it is the polygon's
        # 50,525 km2 to within 0.3%.
        hardap = table(POP, [["Daweb", "6092", "40 209.89", "0.2"],
                             ["Gibeon", "8034", "10156.39", "0.8"]])
        regions = {"hardap": at(nc.constituencies(page(hardap)), "h")}
        with mock.patch.object(nc, "log"):
            recs = nc.build(regions, [{"id": "H", "name": "Hardap"}],
                            [{"id": "8085530B21041761137658", "name": "Gibeon", "parent": "H"}])
        self.assertEqual(recs[0]["population"]["value"], 8_034 + 6_092)
        self.assertIn("Gibeon and Daweb constituencies added together",
                      recs[0]["population_note"])

    def test_every_polygon_has_an_area(self):
        self.assertEqual(len(nc.AREAS), 103)
        self.assertTrue(all(a > 0 for _, a in nc.AREAS.values()))


if __name__ == "__main__":
    unittest.main()
