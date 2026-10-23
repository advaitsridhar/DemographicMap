"""Botswana's 2022 census by district, from Statistics Botswana's Analytical
Report Volume 1, Appendix Table 3 (scripts/fetch_census/botswana_census)."""

import unittest

from scripts.fetch_census import botswana_census as bw

# Appendix Table 3 as the report's text layer gives it (page 38).
TEXT = """Botswana Population Housing Census 2022 | Analytical Report
Appendices
Table 3: Population Distribution by Census District and Sex 2022
Census District Total Male Female Sex Ratio
Gaborone 246,327 118,729 127,598 93.0
Francistown 103,416 49,647 53,769 92.3
Lobatse 29,772 14,634 15,138 96.7
Selibe Phikwe 42,486 20,018 22,468 89.1
Orapa 8,648 3,987 4,661 85.5
Jwaneng 18,785 9,775 9,010 108.5
Sowa 3,267 1,851 1,416 130.7
Southern 139,356 67,315 72,041 93.4
Barolong 58,904 28,875 30,029 96.2
Ngwaketse West 23,663 11,951 11,712 102.0
South East 111,447 53,066 58,381 90.9
Kweneng East 330,220 160,912 169,308 95.0
Kweneng West 57,763 29,631 28,132 105.3
Kgatleng (Wards) 121,873 60,240 61,633 97.7
Central Serowe /Palapye 202,741 98,763 103,978 95.0
Central Mahalapye 131,975 64,446 67,529 95.4
Central Bobonong 77,504 36,989 40,515 91.3
Central Boteti 74,553 37,211 37,342 99.6
Central Tutume 164,955 79,016 85,939 91.9
North East 69,353 32,734 36,619 89.4
Ngamiland East 121,396 60,331 61,065 98.8
Ngamiland West 74,151 35,485 38,666 91.8
Chobe 28,742 14,623 14,119 103.6
Delta 2,889 1,593 1,296 122.9
Ghanzi 56,077 29,016 27,061 107.2
CKGR 488 272 216 125.9
Kgalagadi South 35,346 17,574 17,772 98.9
Kgalagadi North 23,512 11,931 11,581 103.0
Total 2,359,609 1,150,615 1,208,994 95.2
38 Botswana Population Housing Census 2022 | Analytical Report"""

ADMIN1 = [{"id": k, "name": n} for k, n in (
    ("C", "Central District"), ("H", "Chobe District"), ("G", "Ghanzi District"),
    ("K", "Kgalagadi District"), ("T", "Kgatleng District"), ("W", "Kweneng District"),
    ("N", "North-East District"), ("V", "North-West District"), ("S", "South-East District"),
    ("U", "Southern District"))]
ADMIN2 = [{"id": "m", "name": "Masungu", "parent": "N"},
          {"id": "g", "name": "Ghanzi", "parent": "G"},
          {"id": "p", "name": "Palapye", "parent": "C"}]


class BotswanaCensusTest(unittest.TestCase):
    def test_the_table_adds_up_and_every_district_is_placed(self):
        table = bw.parse(TEXT)
        self.assertEqual(table["Total"]["total"], 2_359_609)
        self.assertEqual(len(table), 29)

    def test_districts_polygons_and_the_older_sub_districts(self):
        recs = {r["shape_id"]: r for r in bw.build(bw.parse(TEXT), ADMIN1, ADMIN2)}
        self.assertEqual(recs["C"]["population"]["value"], 706_129)
        self.assertEqual(recs["S"]["population"]["value"], 246_327 + 111_447 + 29_772)
        self.assertEqual(recs["m"]["population"]["value"], 69_353 + 103_416)
        self.assertEqual(recs["g"]["population"]["value"], 56_077 + 488)
        self.assertEqual(recs["p"]["population"]["status"], "not_available")
        self.assertIn("older division", recs["p"]["population"]["note"])
        self.assertEqual(sum(r["population"]["value"] for r in recs.values()
                             if r["level"] == "admin1"), 2_359_609)

    def test_a_line_whose_sexes_miss_its_total_is_refused(self):
        with self.assertRaises(SystemExit):
            bw.parse(TEXT.replace("Chobe 28,742 14,623 14,119", "Chobe 28,742 14,623 14,118"))


if __name__ == "__main__":
    unittest.main()
