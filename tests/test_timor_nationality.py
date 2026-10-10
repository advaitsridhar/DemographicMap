"""Timor-Leste: Timorese and foreign nationals by municipality, 2015 census.

No network: table 9's sheets are built here in the workbook's layout.
"""

import unittest

from scripts.fetch_census import timor_nationality as t

MUNIS = ["Aileu", "Ainaro", "Baucau", "Bobonaro", "Covalima", "Dili", "Ermera", "Lautém",
         "Liquiçá", "Manatuto", "Manufahi", "Oecusse", "Viqueque"]


def sheet(title, timorese_m, other_m, timorese_f, other_f):
    m, f = timorese_m + other_m, timorese_f + other_f
    return [[title, "", ""], ["Age", "Both sexes", "", "", "Male"],
            ["", "Total", "Timorese", "Other nationality/citizenship"],
            ["1.0", "2.0", "3.0"],
            ["Total", m + f, timorese_m + timorese_f, other_m + other_f, m, timorese_m, other_m,
             f, timorese_f, other_f, "", 0.0]]


def book():
    sheets = {"Index": [["x"]]}
    for i, mun in enumerate(MUNIS):
        sheets[f"2.9.{'abcdefghijklm'[i]}"] = sheet(
            f"Table 9.{'abcdefghijklm'[i]} Timorese and foreign population by age and sex, "
            f"{mun}", 100, 1, 99, 0)
    n = len(MUNIS)
    sheets["2.9"] = sheet("Table 9 Timorese and foreign population", 100 * n, n, 99 * n, 0)
    return sheets


class NationalityTest(unittest.TestCase):
    def test_reads_and_checks(self):
        municipalities, country = t.read(book())
        self.assertEqual(len(municipalities), 13)
        self.assertEqual(country[0], 200 * 13)

    def test_the_workbooks_own_spelling_of_liquica(self):
        sheets = book()
        sheets["2.9.i"][0][0] = "Table 9.i Timorese and foreign-born populations, Liquicia"
        municipalities, _ = t.read(sheets)
        self.assertIn("Liquiçá", municipalities)

    def test_a_sheet_naming_no_municipality_refuses(self):
        sheets = book()
        sheets["2.9.a"][0][0] = "Table 9.a Timorese and foreign population"
        with self.assertRaises(SystemExit):
            t.read(sheets)

    def test_municipalities_off_the_country_refuse(self):
        sheets = book()
        sheets["2.9"] = sheet("Table 9", 100 * 13, 14, 99 * 13, 0)
        with self.assertRaises(SystemExit):
            t.read(sheets)

    def test_records(self):
        municipalities, _ = t.read(book())
        recs = t.build(municipalities, [{"id": "A", "name": "Aileu"}])
        eth = {g["group"]: g["pct"] for g in recs[0]["ethnicity"]}
        self.assertEqual(eth, {"East Timorese": 99.5, "Foreign nationals": 0.5})
        self.assertEqual(recs[0]["ethnicity_basis"], "nationality")


if __name__ == "__main__":
    unittest.main()
