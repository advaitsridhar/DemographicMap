"""The Factbook's major urban areas: every city read, and the largest named.

No network: the strings are the Factbook's own entries. Its lists put a small
capital first, separate entries of different years with a semicolon, and write
thousands with a comma -- and once, a count with a stray "million".
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_factbook  # noqa: E402


def profile(text):
    return {"People and Society": {"Major urban areas - population": {"text": text}}}


def cities(text):
    largest, listed = fetch_factbook.parse_major_urban(profile(text))
    return largest, [(c["name"], c["population"]) for c in listed]


class MajorUrbanAreas(unittest.TestCase):
    def test_a_semicolon_separates_and_a_thousands_comma_does_not(self):
        largest, listed = cities("285,000 PORTO-NOVO (capital) (2018); 1.253 million "
                                 "Abomey-Calavi, 722,000 COTONOU (seat of government) (2022)")
        self.assertEqual(listed, [("Porto-Novo", 285000), ("Abomey-Calavi", 1253000),
                                  ("Cotonou", 722000)])
        self.assertEqual(largest, "Abomey-Calavi")

    def test_the_largest_is_the_most_populous_not_the_first(self):
        self.assertEqual(cities("231,000 YAMOUSSOUKRO (capital) (2018), 5.686 million "
                                "ABIDJAN (seat of government) (2023)")[0], "Abidjan")
        self.assertEqual(cities("262,000 Dodoma (legislative capital) (2018), 7.776 million "
                                "DAR ES SALAAM (administrative capital), 1.311 million "
                                "Mwanza, 800,000 Zanzibar (2023)")[0], "Dar Es Salaam")

    def test_a_count_with_a_stray_million_is_a_count(self):
        largest, listed = cities("7.682 million RIYADH (capital), 4.863 million Jeddah, "
                                 "872,000 million Hufuf-Mubarraz (2023)")
        self.assertEqual(listed[-1], ("Hufuf-Mubarraz", 872000))
        self.assertEqual(largest, "Riyadh")

    def test_an_ordinary_list_is_read_as_before(self):
        self.assertEqual(cities("3.574 million BERLIN (capital), 1.788 million Hamburg"),
                         ("Berlin", [("Berlin", 3574000), ("Hamburg", 1788000)]))


if __name__ == "__main__":
    unittest.main()
