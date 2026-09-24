import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import iraq_census as ic  # noqa: E402

DUMP = ROOT / "data" / "raw" / "iraq" / "aas2024_table11.txt"
GAZ = ROOT / "data" / "raw" / "iraq" / "ocha_admin3.txt"


@unittest.skipUnless(DUMP.exists() and GAZ.exists(), "Iraq dumps not present")
class TheCensusTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ic.parse(DUMP.read_text(encoding="utf-8"))

    def test_every_governorate_adds_up_to_the_country(self):
        govs = self.table["governorates"]
        self.assertEqual(len(govs), 18)
        self.assertEqual(sum(govs.values()), ic.NATIONAL)
        self.assertEqual(self.table["grand"], ic.NATIONAL)

    def test_every_governorate_is_its_districts(self):
        for code, value in self.table["governorates"].items():
            self.assertEqual(self.table["sums"][code], value, code)

    def test_a_total_printed_without_the_word_is_taken_only_when_it_is_the_sum(self):
        # Panjwin's total line carries no "Total".
        self.assertEqual(self.table["districts"]["1306"], 52_251)


@unittest.skipUnless(DUMP.exists() and GAZ.exists(), "Iraq dumps not present")
class TheCrosswalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        table = ic.parse(DUMP.read_text(encoding="utf-8"))
        cls.table = table
        cls.mapped, cls.notes = ic.crosswalk(table, ic.read_gazetteer(GAZ.read_text(encoding="utf-8")))

    def test_a_written_governorate_s_districts_add_up_to_it(self):
        districts = [e for e in self.mapped.values()
                     if e["governorate"] == "Al-Muthanna" and e["value"] is not None]
        self.assertEqual(len(districts), 4)
        self.assertEqual(sum(e["value"] for e in districts),
                         self.table["governorates"]["32"])

    def test_a_district_moved_between_districts_blanks_its_governorate(self):
        kirkuk = self.mapped["Kirkuk/Kirkuk"]
        self.assertIsNone(kirkuk["value"])
        self.assertIn("moved", kirkuk["why"])


class Names(unittest.TestCase):
    def test_reversed_arabic_is_read_back_in_order(self):
        self.assertEqual(ic.arabic("كوهد"), "دهوك")

    def test_the_lam_alef_ligature_is_folded(self):
        self.assertEqual(ic.ar_key("كربالء"), ic.ar_key("كربلاء"))


if __name__ == "__main__":
    unittest.main()
