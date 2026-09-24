import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import uzbekistan_siat as uz  # noqa: E402


def unit(code, en, uz_name, series):
    return {"Code": code, "Klassifikator_en": en, "Klassifikator": uz_name,
            **{str(2020 + i): v for i, v in enumerate(series)}}


REGION = unit("1710", "Kashkadarya region", "Qashqadaryo viloyati", [100, 101, 102, 103])
SHAPES = {"Qashqadaryo Region": [
    {"id": "a", "name": "Chirakchi"}, {"id": "b", "name": "Kasbi"},
    {"id": "c", "name": "Guzar"}, {"id": "d", "name": "Balikchi"}]}


class Names(unittest.TestCase):
    def test_romanisations_fold_together(self):
        self.assertEqual(uz.key("Balykchi district"), uz.key("Balikchi"))
        self.assertEqual(uz.key("Jalаquduk district"), uz.key("Jalaquduk"))  # Cyrillic а
        self.assertEqual(uz.key("Khatyrchi district"), uz.key("Xatirchi tumani"))

    def test_a_city_is_not_its_district(self):
        rows, _ = uz.build([REGION, unit("1710401", "Chirakchi city", "Chiroqchi shahri",
                                         [1, 1, 1, 1])], SHAPES)
        self.assertEqual([r for r in rows if r["level"] == "admin2"], [])


class CarvedOut(unittest.TestCase):
    def test_a_sole_source_carries_its_new_unit(self):
        data = [REGION,
                unit("1710201", "Chirakchi district", "Chiroqchi tumani", [400, 405, 230, 235]),
                unit("1710240", "Kukdala district", "Ko'kdala tumani", [0, 0, 180, 185])]
        rows, notes = uz.build(data, SHAPES)
        chirakchi = next(r for r in rows if r["name"] == "Chirakchi")
        self.assertEqual(chirakchi["population"]["value"], 420_000)
        self.assertIn("Kukdala", chirakchi["population"]["note"])

    def test_several_sources_leave_each_blank(self):
        data = [REGION,
                unit("1710201", "Chirakchi district", "Chiroqchi tumani", [400, 405, 330, 335]),
                unit("1710202", "Kasbi district", "Kasbi tumani", [300, 305, 230, 232]),
                unit("1710240", "Kukdala district", "Ko'kdala tumani", [0, 0, 150, 152])]
        rows, _ = uz.build(data, SHAPES)
        for name in ("Chirakchi", "Kasbi"):
            row = next(r for r in rows if r["name"] == name)
            self.assertNotIn("value", row["population"])
            self.assertIn("Kukdala", row["population"]["note"])


if __name__ == "__main__":
    unittest.main()
