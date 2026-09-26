"""Ecuador's 2022 census by province and canton: median age and sex ratio from sheet 2.1."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import ecuador_profile as ep  # noqa: E402

BANDS = [("De 0-4", 30, 30), ("De 5-9", 20, 20), ("10 o más", 10, 20)]


def block(province, canton, parish, bands=BANDS):
    men = sum(m for _, m, _ in bands)
    women = sum(w for _, _, w in bands)
    rows = [["", province, canton, parish, f"Total {parish}", str(men + women), str(men),
             str(women)]]
    rows += [["", province, canton, parish, label, str(m + w), str(m), str(w)]
             for label, m, w in bands]
    return rows


def sheet(canton_bands=BANDS):
    doubled = [(label, 2 * m, 2 * w) for label, m, w in BANDS]
    return (block("Azuay", "Total Azuay", "Total Azuay", doubled)
            + block("Azuay", "Cuenca", "Total Cuenca")
            + block("Azuay", "Cuenca", "Baños")   # a parish, read past
            + block("Azuay", "Gualaceo", "Total Gualaceo", canton_bands))


class Profile(unittest.TestCase):
    def test_provinces_and_cantons_with_median_and_ratio(self):
        out = {r["name"]: r for r in ep.build(sheet())}
        self.assertEqual(set(out), {"Azuay", "Cuenca", "Gualaceo"})
        # 130 people: the 65th falls 5 of 40 into ages 5-9.
        self.assertEqual(out["Cuenca"]["median_age"]["value"], 5.6)
        self.assertEqual(out["Cuenca"]["sex_ratio"]["value"], 857)
        self.assertEqual(out["Cuenca"]["parent_name"], "Azuay")

    def test_cantons_that_miss_their_province_are_refused(self):
        with self.assertRaises(SystemExit):
            ep.build(sheet([("De 0-4", 31, 30), ("De 5-9", 20, 20), ("10 o más", 10, 20)]))


if __name__ == "__main__":
    unittest.main()
