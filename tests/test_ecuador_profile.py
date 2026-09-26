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



def culture(cuenca=(70, 30)):
    head = ["Índice", "Provincia, cantón, área", "", "", "", "Número total de personas",
            "Autoidentificación"]
    cats = ["", "", "", "", "", "", "Indigena", "Mestiza/o"]
    rows = [head, cats,
            ["", "Azuay", "Total Azuay", "Total Azuay", "", "200", "90", "110"],
            ["", "Azuay", "Total Azuay", "Urbana", "", "150", "50", "100"],
            ["", "Azuay", "Cuenca", "Total", "", "100", str(cuenca[0]), str(cuenca[1])],
            ["", "Azuay", "Gualaceo", "Total", "", "100", "20", "80"]]
    return rows


class Compositions(unittest.TestCase):
    def test_categories_under_the_maps_labels(self):
        out = ep.composition_table(culture(), ep.ETHNIC, "test")
        self.assertEqual(out[("Azuay", "Cuenca")]["counts"], {"Indigenous": 70, "Mestizo": 30})
        self.assertEqual(out[("Azuay", "")]["total"], 200)

    def test_cantons_that_miss_their_province_are_refused(self):
        with self.assertRaises(SystemExit):
            ep.composition_table(culture((60, 40)), ep.ETHNIC, "test")

    def test_an_unread_category_is_refused(self):
        grid = culture()
        grid[1][7] = "Something new"
        with self.assertRaises(SystemExit):
            ep.composition_table(grid, ep.ETHNIC, "test")


if __name__ == "__main__":
    unittest.main()
