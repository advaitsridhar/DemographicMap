"""Chile's 2024 census: comunas summed to provinces, and what INE's stars hide kept apart."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import chile_census as cc  # noqa: E402

LABELS = {"Mapuche": "Mapuche", "Aymara": "Aymara"}


def comuna(region, province, code, **cells):
    return {"Código región": region, "Código provincia": province, "Código comuna": code,
            **cells}


class Names(unittest.TestCase):
    def test_the_boundary_files_prefix_is_not_part_of_the_name(self):
        self.assertEqual(cc.province_key("Provincia del Tamarugal"), cc.province_key("Tamarugal"))
        self.assertEqual(cc.province_key("Provincia de la Antártica Chilena"),
                         cc.province_key("Antártica Chilena"))
        self.assertEqual(cc.province_key("Provincia de Bío-Bío"), cc.province_key("Biobío"))


class Cells(unittest.TestCase):
    def test_a_star_is_unpublished_and_a_dash_is_zero(self):
        self.assertIsNone(cc.cell("*"))
        self.assertEqual(cc.cell("-"), 0)
        self.assertEqual(cc.cell(1623073), 1623073)


class Summing(unittest.TestCase):
    rows = [comuna(15, 151, 15101, Total=100, Mapuche=10, Aymara=80),
            comuna(15, 152, 15201, Total=20, Mapuche="*", Aymara=18)]

    def test_stars_are_counted_not_guessed(self):
        sums, hidden = cc.summed(self.rows, ["Total", "Mapuche", "Aymara"], "Código región")
        self.assertEqual(sums[15]["Mapuche"], 10)
        self.assertEqual(hidden[15]["Mapuche"], 1)

    def test_a_region_whose_comunas_do_not_add_up_is_refused(self):
        sums, hidden = cc.summed(self.rows, ["Total", "Aymara"], "Código región")
        with self.assertRaises(SystemExit):
            cc.check_regions(sums, hidden, {15: {"Total": 120, "Aymara": 99}},
                             ["Total", "Aymara"], "test")

    def test_a_starred_column_is_not_checked_against_the_region(self):
        sums, hidden = cc.summed(self.rows, ["Total", "Mapuche"], "Código región")
        cc.check_regions(sums, hidden, {15: {"Total": 120, "Mapuche": 11}},
                         ["Total", "Mapuche"], "test")


class Composition(unittest.TestCase):
    def test_what_the_stars_hid_is_a_line_of_its_own(self):
        out = cc.composition({"Mapuche": 0, "Aymara": 18}, LABELS, 20, cc.PEOPLES_HIDDEN)
        self.assertEqual(out, {"Aymara": 18, cc.PEOPLES_HIDDEN: 2})

    def test_categories_past_the_total_are_refused(self):
        with self.assertRaises(SystemExit):
            cc.composition({"Mapuche": 15, "Aymara": 18}, LABELS, 20, cc.PEOPLES_HIDDEN)

    def test_without_a_line_for_it_a_shortfall_is_refused(self):
        with self.assertRaises(SystemExit):
            cc.composition({"Mapuche": 1, "Aymara": 18}, LABELS, 20, None)


if __name__ == "__main__":
    unittest.main()
