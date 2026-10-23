"""Sierra Leone's district capitals, from Wikipedia's Districts of Sierra Leone.

The table below is written in the article's form with its rows as the
runner's probe of the article printed them (7143457).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import sierra_leone_capitals as sc  # noqa: E402

ROWS = [("Kailahun", "Eastern", "Kailahun"), ("Kenema", "Eastern", "Kenema"),
        ("Kono", "Eastern", "Koidu Town"), ("Bombali", "Northern", "Makeni"),
        ("Falaba", "Northern", "Bendugu"), ("Koinadugu", "Northern", "Kabala"),
        ("Tonkolili", "Northern", "Magburaka"), ("Kambia", "North West", "Kambia"),
        ("Karene", "North West", "Kamakwie"), ("Port Loko", "North West", "Port Loko"),
        ("Bo", "Southern", "Bo"), ("Bonthe", "Southern", "Bonthe"),
        ("Moyamba", "Southern", "Moyamba"), ("Pujehun", "Southern", "Pujehun"),
        ("Western Rural", "Western", "Waterloo"), ("Western Urban", "Western", "Freetown")]
WIKITEXT = ("{| class=\"wikitable sortable\"\n! District !! Province !! Capital !! Area\n"
            + "".join(f"|-\n| [[{d} District|{d}]] || {p} || [[{c}]] || 1\n" for d, p, c in ROWS)
            + "|}\n")
DRAWN = ["Kailahun", "Kenema", "Kono", "Bombali", "Kambia", "Koinadugu", "Port Loko",
         "Tonkolili", "Bo", "Bonthe", "Moyamba", "Pujehun", "Western Area Rural",
         "Western Area Urban"]


class SierraLeoneCapitalsTest(unittest.TestCase):
    def test_the_table(self):
        listed = sc.capitals(WIKITEXT)
        self.assertEqual(len(listed), 16)
        self.assertEqual(listed["Kono"], "Koidu Town")

    def test_bound_to_the_fourteen_drawn(self):
        admin2 = [{"id": f"s{i}", "name": n} for i, n in enumerate(DRAWN)]
        records = {r["name"]: r for r in sc.bind(sc.capitals(WIKITEXT), admin2)}
        self.assertEqual(len(records), 13)
        self.assertNotIn("Bonthe", records)
        self.assertEqual(records["Western Area Urban"]["capital"], "Freetown")
        self.assertIn("Karene", records["Bombali"]["capital_note"])
        self.assertNotIn("capital_note", records["Kono"])

    def test_a_drawn_district_left_without_a_capital_stops_the_write(self):
        admin2 = [{"id": f"s{i}", "name": n} for i, n in enumerate(DRAWN + ["Somewhere"])]
        with self.assertRaises(SystemExit):
            sc.bind(sc.capitals(WIKITEXT), admin2)


if __name__ == "__main__":
    unittest.main()
