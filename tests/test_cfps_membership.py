"""Membership of a religious organisation: a rate, and not religious belief."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import cfps_membership as m  # noqa: E402


class TheRate(unittest.TestCase):
    def rows(self, n_yes, n_no, code=31, w=1.0):
        return ([(code, m.YES, w)] * n_yes) + ([(code, m.NO, w)] * n_no)

    def test_a_weighted_share_with_its_base_and_sample(self) -> None:
        share, base, n = m.rate(self.rows(30, 570), 31)
        self.assertAlmostEqual(share, 5.0)
        self.assertEqual(n, 600)
        self.assertAlmostEqual(base, 600.0)

    def test_weights_are_applied_not_ignored(self) -> None:
        rows = [(31, m.YES, 9.0)] + [(31, m.NO, 1.0)] * 599
        share, _base, n = m.rate(rows, 31)
        self.assertEqual(n, 600, "the sample size counts respondents")
        self.assertGreater(share, 1.0, "one heavily weighted yes counts for more")

    def test_a_refusal_is_not_a_no(self) -> None:
        # CFPS codes don't-know and refused negative. Counting them as "no"
        # would report a lower membership rate than the survey found.
        got = m.rate(self.rows(30, 570) + [(31, -8, 1.0)] * 100, 31)
        self.assertEqual(got[2], 600, "only yes and no are answers")

    def test_a_thin_province_is_refused(self) -> None:
        self.assertIsNone(m.rate(self.rows(2, 20), 31),
                          "a share from a handful of respondents is not a share")

    def test_a_province_with_no_weight_is_refused(self) -> None:
        rows = [(31, m.YES, None)] * 400 + [(31, m.NO, None)] * 400
        self.assertIsNone(m.rate(rows, 31))

    def test_another_province_does_not_leak_in(self) -> None:
        got = m.rate(self.rows(30, 570, code=31) + self.rows(500, 0, code=44), 31)
        self.assertAlmostEqual(got[0], 5.0)
        self.assertEqual(got[2], 600)


class TheFieldIsNotReligion(unittest.TestCase):
    """Conflating the two is the error this file exists to avoid: the 2016
    affiliation question put Shanghai's 'no religion' at 86.7%, while this
    one puts organisational membership at 2.6%."""

    def test_it_writes_its_own_field(self) -> None:
        self.assertEqual(m.FIELD, "religious_membership")
        self.assertNotEqual(m.FIELD, "religion")

    def test_the_five_self_representative_provinces_only(self) -> None:
        self.assertEqual(m.SELF_REPRESENTATIVE, {31, 21, 41, 62, 44})

    def test_the_waves_are_newest_first_and_all_ask_qn4004(self) -> None:
        years = [w[0] for w in m.WAVES]
        self.assertEqual(years, sorted(years, reverse=True))
        self.assertTrue(all(w[3] == "qn4004" for w in m.WAVES),
                        "every wave here must be the same question")

    def test_no_wave_reuses_the_affiliation_variable(self) -> None:
        from scripts.fetch_census import cfps_microdata as old  # noqa: PLC0415
        affiliation = {w[3] for w in old.WAVES}
        self.assertTrue(affiliation.isdisjoint({w[3] for w in m.WAVES}),
                        "the two readers must not read the same variable")
