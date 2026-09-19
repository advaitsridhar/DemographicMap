"""Malaysia's religion from the Kawasanku dashboard file, and its guards."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
from fetch_census import malaysia_religion as mr  # noqa: E402

JOHOR = {"muslim": 59.72259562507638, "christian": 3.029326602937399,
         "buddhist": 28.700716019024007, "hindu": 7.050879498811622,
         "other": 0.8068494414752335, "atheist": 0.6896328126753573}


def rows(area_type: str, area: str, comp: dict[str, float], chart: str = "religion"):
    return [(area_type, area, chart, variable, value) for variable, value in comp.items()]


class TheDashboardFile(unittest.TestCase):
    def test_only_the_religion_chart_is_read(self):
        data = rows("state", "Johor", JOHOR) + rows("state", "Johor", {"bumi": 60.0, "chinese": 40.0},
                                                    chart="ethnicity")
        out = mr.religion_shares(data)
        self.assertEqual(set(out), {("state", "Johor")})
        self.assertAlmostEqual(out[("state", "Johor")]["Islam"], 59.72, places=2)
        self.assertEqual(set(out[("state", "Johor")]), set(mr.LABELS.values()))

    def test_a_new_variable_is_refused_not_dropped(self):
        data = rows("state", "Johor", {**JOHOR, "sikh": 0.0})
        with self.assertRaises(SystemExit) as caught:
            mr.religion_shares(data)
        self.assertIn("sikh", str(caught.exception))

    def test_a_composition_short_of_100_is_refused(self):
        # A row missing from the file leaves five shares that look fine on
        # their own and sum to 99.3; the guard is the sum.
        short = {k: v for k, v in JOHOR.items() if k != "atheist"}
        with self.assertRaises(SystemExit):
            mr.religion_shares(rows("state", "Johor", short))

    def test_the_labels_are_the_project_canon(self):
        import canonical_groups as cg
        for label in mr.LABELS.values():
            self.assertTrue(cg.ancestry("religion", label), label)


class TheNationalCheck(unittest.TestCase):
    PUBLISHED = {"Islam": 63.5, "Buddhism": 18.7, "Christianity": 9.1, "Hinduism": 6.1,
                 "Other religions": 0.9, "No religion": 1.8}

    def test_the_census_figures_pass(self):
        mr.check_national(self.PUBLISHED)

    def test_a_rebased_file_is_refused(self):
        # A later estimate with the same file name: Islam a point higher.
        with self.assertRaises(SystemExit) as caught:
            mr.check_national({**self.PUBLISHED, "Islam": 64.6})
        self.assertIn("not the 2020 census", str(caught.exception))

    def test_other_and_none_are_checked_together(self):
        # DOSM announced 2.7 for everything outside the four religions and
        # did not split it, so the split is not what is checked.
        mr.check_national({**self.PUBLISHED, "Other religions": 1.5, "No religion": 1.2})
        with self.assertRaises(SystemExit):
            mr.check_national({**self.PUBLISHED, "Other religions": 2.0, "No religion": 2.0})


class PartsAgainstTheWhole(unittest.TestCase):
    A = {"Islam": 90.0, "Buddhism": 10.0}
    B = {"Islam": 50.0, "Buddhism": 50.0}

    def test_weighted_parts_reproduce_the_whole(self):
        # 3:1 weights: 80 / 20.
        mr.check_parts("X", {"Islam": 80.0, "Buddhism": 20.0}, {"a": self.A, "b": self.B},
                       {"a": 300, "b": 100})

    def test_unweighted_parts_do_not(self):
        with self.assertRaises(SystemExit) as caught:
            mr.check_parts("X", {"Islam": 70.0, "Buddhism": 30.0}, {"a": self.A, "b": self.B},
                           {"a": 300, "b": 100})
        self.assertIn("X", str(caught.exception))


class PlacingDistricts(unittest.TestCase):
    POP = {("Johor", "Muar"): 300_000, ("Sarawak", "Kuching"): 700_000,
           ("W.P. Labuan", "W.P. Labuan"): 95_000}

    def test_a_district_finds_its_state_by_name(self):
        placed, unmatched = mr.place_districts({"Muar": {}, "Kuching": {}}, self.POP)
        self.assertEqual(placed, {"Johor": {"Muar": {}}, "Sarawak": {"Kuching": {}}})
        self.assertEqual(unmatched, [])

    def test_an_unknown_name_is_reported_not_guessed(self):
        placed, unmatched = mr.place_districts({"Muar": {}, "Kuching Utara": {}}, self.POP)
        self.assertEqual(unmatched, ["Kuching Utara"])
        self.assertNotIn("Sarawak", placed)

    def test_a_name_in_two_states_is_refused(self):
        pop = {**self.POP, ("Kedah", "Muar"): 1}
        with self.assertRaises(SystemExit):
            mr.place_districts({"Muar": {}}, pop)


class TheRecord(unittest.TestCase):
    def setUp(self):
        comp = mr.religion_shares(rows("state", "Johor", JOHOR))[("state", "Johor")]
        self.rec = mr.build_record("MYS-Johor", "Johor", level="admin1", parent="MYS",
                                   parent_name=None, aliases=[], comp=comp,
                                   population=4_009_670)

    def test_counts_are_the_shares_on_the_2020_population(self):
        islam = next(r for r in self.rec["religion"] if r["group"] == "Islam")
        self.assertEqual(islam["pct"], 59.7)
        self.assertEqual(islam["count"], round(0.5972259562507638 * 4_009_670))
        self.assertAlmostEqual(sum(r["pct"] for r in self.rec["religion"]), 100.0, delta=0.3)

    def test_the_year_is_the_census_and_the_note_says_the_counts_are_derived(self):
        self.assertEqual(self.rec["religion_year"], 2020)
        self.assertIn("rounded", self.rec["religion_note"])
        self.assertIn("unknown", self.rec["religion_note"])

    def test_nothing_but_religion_is_claimed(self):
        # The ethnicity file owns population and ethnicity; a gap here never
        # displaces them when the two merge.
        self.assertTrue(common.is_gap(self.rec["population"]))
        self.assertTrue(common.is_gap(self.rec["ethnicity"]))
        self.assertEqual({s["field"] for s in self.rec["sources"]}, {"religion"})


class TheLanguagePolicy(unittest.TestCase):
    def test_malaysia_declares_language_never_asked(self):
        self.assertEqual(common.collection_status("MYS", "language"), common.NOT_COLLECTED)
        self.assertIsNone(common.collection_policy("MYS", "religion"))
        self.assertIsNone(common.collection_policy("MYS", "ethnicity"))


if __name__ == "__main__":
    unittest.main()
