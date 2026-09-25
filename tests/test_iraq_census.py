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

    def test_every_sub_district_is_read(self):
        # Rows whose code the layout lost are recovered from what their
        # district's total leaves over; only Wasit's Kut and Maysan's Ali
        # al-Gharbi, whose rows trade 867 people, do not add up.
        self.assertEqual(sorted(set(self.table["districts"]) - self.table["whole"]),
                         ["2601", "3402"])

    def test_a_total_printed_without_the_word_is_taken_only_when_it_is_the_sum(self):
        # Panjwin's total line carries no "Total".
        self.assertEqual(self.table["districts"]["1306"], 52_251)


@unittest.skipUnless(DUMP.exists() and GAZ.exists(), "Iraq dumps not present")
class TheCrosswalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        table = ic.parse(DUMP.read_text(encoding="utf-8"))
        cls.table = table
        cls.result = ic.crosswalk(table, ic.read_gazetteer(GAZ.read_text(encoding="utf-8")))
        cls.mapped = cls.result["districts"]
        cls.govs = cls.result["governorates"]

    def test_a_written_governorate_s_districts_add_up_to_it(self):
        districts = [e for e in self.mapped.values()
                     if e["governorate"] == "Al-Muthanna" and e["value"] is not None]
        self.assertEqual(len(districts), 4)
        self.assertEqual(sum(e["value"] for e in districts),
                         self.table["governorates"]["32"])

    def test_a_sub_district_moved_between_districts_follows_its_ground(self):
        # The census files Altun Kupri under Kirkuk district; the boundary
        # file draws it in Dibis. Its people go to Dibis.
        dibis = self.mapped["Kirkuk/Dibis"]
        self.assertIsNotNone(dibis["value"])
        self.assertTrue(any("Alton" in name for name, _v in dibis["parts"]))

    def test_a_namesake_across_a_governorate_line_is_not_taken_alone(self):
        # Ninewa's Faeda (186,456) is not OCHA's 34 km2 Fayde in Duhok.
        tilkaef = self.mapped["Ninewa/Tilkaef"]
        self.assertEqual(tilkaef["value"], self.table["districts"]["1204"])
        self.assertNotIn("Faeda", str(self.govs["Duhok"].get("note")))

    def test_ground_counted_under_another_governorate_moves_with_it(self):
        # Duhok counts Aqra, Shekhan and Bardarash; the map draws them in
        # Ninewa, and Makhmour, counted under Ninewa, in Erbil.
        census = {ic.GOVERNORATE[g]: v for g, v in self.table["governorates"].items()}
        for gov in ("Duhok", "Ninewa", "Erbil"):
            self.assertNotEqual(self.govs[gov]["value"], census[gov], gov)
        self.assertEqual(sum(e["value"] for e in self.govs.values()), ic.NATIONAL)

    def test_a_district_that_cannot_be_placed_leaves_a_reason(self):
        for entry in self.mapped.values():
            if entry["value"] is None:
                self.assertTrue(entry["why"])


class Names(unittest.TestCase):
    def test_reversed_arabic_is_read_back_in_order(self):
        self.assertEqual(ic.arabic("كوهد"), "دهوك")

    def test_a_second_name_in_brackets_is_a_name_too(self):
        self.assertEqual(ic.variants("Akd (Al-Daggara"), ["Akd", "Al-Daggara"])

    def test_kurdish_vowels_fold_to_the_arabic_spelling(self):
        self.assertEqual(ic.ar_loose("مهيدان"), ic.ar_loose("ميدان"))

    def test_short_romanisations_must_be_the_same(self):
        self.assertFalse(ic.alike(ic.en_key("Sowran"), ic.en_key("Shwan")))

    def test_the_lam_alef_ligature_is_folded(self):
        self.assertEqual(ic.ar_key("كربالء"), ic.ar_key("كربلاء"))


if __name__ == "__main__":
    unittest.main()
