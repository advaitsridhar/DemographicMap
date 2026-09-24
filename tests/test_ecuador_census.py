import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import ecuador_census as ec  # noqa: E402


@unittest.skipUnless(ec.DUMP.exists(), "INEC sheet not saved")
class TheCensusSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = [line.split("\t") for line in ec.DUMP.read_text(encoding="utf-8").split("\n")]
        cls.cantons, cls.national = ec.parse(rows)

    def test_the_cantons_are_the_country(self):
        self.assertEqual(self.national, ec.NATIONAL)
        self.assertEqual(sum(sum(c.values()) for c in self.cantons.values()), ec.NATIONAL)

    def test_a_canton_named_like_its_province_is_a_canton(self):
        # Cañar canton, in Cañar: not the province's total.
        self.assertEqual(self.cantons["Cañar"]["Cañar"], 52_150)
        self.assertGreater(sum(self.cantons["Cañar"].values()), 52_150)


if __name__ == "__main__":
    unittest.main()
