"""Morocco's legal population: a commune across the Western Sahara line taken out
of its province and region, and nationality written as ethnicity."""

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import morocco_rgph2024 as mr  # noqa: E402


def workbook(rows):
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Population légale du Royaume du Maroc"])
    sheet.append(["", "Marocains", "Étrangers", "Population", "Ménages", "", "Code"])
    for name, moroccans, foreigners, code in rows:
        sheet.append([name, moroccans, foreigners, moroccans + foreigners, 1, "", code])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


ROWS = [("Ensemble du territoire national", 990, 10, None),
        ("Région de Guelmim-Oued Noun", 990, 10, 10),
        ("Province d'Assa-Zag", 290, 10, 10151),
        ("Province de Guelmim", 700, 0, 10261),
        ("Commune d'Assa", 250, 10, 101510101),
        ("Commune d'Al Mahbass", 40, 0, 101510301),
        ("Commune de Guelmim", 700, 0, 102610101)]


class AcrossTheLine(unittest.TestCase):
    def setUp(self):
        with mock.patch.object(mr, "NATIONAL", 1000):
            self.table = mr.read(workbook(ROWS))

    def test_only_the_line_regions_communes_stay_in_communes(self):
        self.assertEqual(self.table["communes"], {})
        self.assertEqual(len(self.table["all_communes"]), 3)

    def test_al_mahbass_is_taken_out_of_assa_zag_and_its_region(self):
        admin1 = [{"id": "R", "name": "Guelmim-Oued Noun"}]
        admin2 = [{"id": "A", "name": "Assa-Zag Province", "parent": "R"},
                  {"id": "G", "name": "Guelmim Province", "parent": "R"}]
        records, _ = mr.build(self.table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["A"]["population"]["value"], 260)
        self.assertIn("without the commune of Al Mahbass (40 people)",
                      by["A"]["population_note"])
        self.assertEqual(by["R"]["population"]["value"], 960)
        self.assertEqual(by["G"]["population"]["value"], 700)
        self.assertNotIn("Mahbass", by["G"]["population_note"])

    def test_nationality_on_the_ethnicity_field(self):
        admin1 = [{"id": "R", "name": "Guelmim-Oued Noun"}]
        records, _ = mr.build(self.table, admin1, [])
        region = records[0]
        self.assertEqual(region["ethnicity_basis"], "nationality")
        shares = {g["group"]: g["count"] for g in region["ethnicity"]}
        self.assertEqual(shares, {"Moroccan": 950, "Foreign nationals": 10})

    def test_a_named_commune_the_province_lacks_stops_the_run(self):
        with mock.patch.object(mr, "ACROSS_COMMUNES", {"Assa-Zag": ("nowhere",)}):
            with self.assertRaises(SystemExit):
                mr.across_communes(self.table, 10151)


if __name__ == "__main__":
    unittest.main()
