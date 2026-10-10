"""India C-13 single-year ages: the cell readers, the unit checks, the median.

No workbook and no network: the units are built as ``read_workbook`` builds
them, and the binding is exercised by the run's own checks on the runner.
"""

import collections
import unittest

from scripts.fetch_census import india_ages as ia


def unit(name="District - X (001)", per_age=10, unstated=(0, 0, 0)):
    ages = {s: collections.Counter() for s in "TMF"}
    for age in range(0, ia.OPEN_FROM + 1):
        ages["M"][age] = per_age
        ages["F"][age] = per_age
        ages["T"][age] = 2 * per_age
    total = tuple(sum(ages[s].values()) + u for s, u in zip("TMF", unstated))
    return ia.Unit(state="03", district="001", name=name, total=total,
                   ages=ages, unstated=unstated)


class TestCells(unittest.TestCase):
    def test_codes_are_padded(self):
        self.assertEqual(ia.code(3.0, 2), "03")
        self.assertEqual(ia.code("035", 3), "035")
        self.assertIsNone(ia.code("", 3))

    def test_ages(self):
        self.assertEqual(ia.single(0.0), 0)
        self.assertEqual(ia.single("99"), 99)
        self.assertEqual(ia.single("100+"), ia.OPEN_FROM)
        self.assertIsNone(ia.single("Age not stated"))


class TestUnits(unittest.TestCase):
    def test_a_consistent_unit_passes(self):
        ia.check_unit(unit(unstated=(4, 2, 2)))

    def test_a_missing_year_is_refused(self):
        bad = unit()
        del bad["ages"]["T"][37]
        with self.assertRaises(SystemExit):
            ia.check_unit(bad)

    def test_sexes_must_make_persons(self):
        bad = unit()
        bad["total"] = (bad["total"][0] + 1, bad["total"][1], bad["total"][2])
        with self.assertRaises(SystemExit):
            ia.check_unit(bad)

    def test_median_leaves_the_unstated_out(self):
        # 101 equal single years: the middle person is in the year 50.
        self.assertEqual(ia.median_of(unit(unstated=(1000, 500, 500))), 50.5)

    def test_combine_sums_year_by_year(self):
        a, b = unit(per_age=10), unit(per_age=30)
        both = ia.combine([a, b], "both")
        self.assertEqual(both["ages"]["T"][7], 80)
        self.assertEqual(both["total"][0], a["total"][0] + b["total"][0])
        ia.check_unit(both)

    def test_fields_name_the_unstated(self):
        fields = ia.age_fields(unit(unstated=(12, 6, 6)), "https://x")
        self.assertEqual(fields["median_age"]["unit"], "years")
        self.assertIn("12 people whose age was not stated", fields["median_age_note"])


class TestReasons(unittest.TestCase):
    def test_lost_territory_reason_names_the_successors(self):
        note = ia.lost_age_reason("Karimnagar", 23, (("Jagtial", 2016),
                                                     ("Peddapalli", 2016)))
        self.assertIn("Jagtial and Peddapalli (2016) were carved out", note)
        self.assertIn("23%", note)
        self.assertIn("not shown", note)


if __name__ == "__main__":
    unittest.main()
