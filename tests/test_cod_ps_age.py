"""COD-PS age tables: median from five-year groups, ratio from the sex totals, and the checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import cod_ps_age as cpa  # noqa: E402

BANDS = [(0, 4), (5, 9), (10, 14), (15, 19)]


def columns(sexes="FM", open_at=20, total="T_TL"):
    cols = ["ADM1_ES", "ADM1_PCODE", "F_TL", "M_TL"] + ([total] if total else [])
    for s in sexes:
        cols += [f"{s}_{lo:02d}_{hi:02d}" for lo, hi in BANDS] + [f"{s}_{open_at}Plus"]
    return cols


def row(f_counts, m_counts):
    out = {"ADM1_ES": "Amazonas", "ADM1_PCODE": "PE01",
           "F_TL": sum(f_counts), "M_TL": sum(m_counts), "T_TL": sum(f_counts) + sum(m_counts)}
    for s, counts in (("F", f_counts), ("M", m_counts)):
        for (lo, hi), n in zip(BANDS, counts):
            out[f"{s}_{lo:02d}_{hi:02d}"] = n
        out[f"{s}_20Plus"] = counts[-1]
    return out


class MethodQuote(unittest.TestCase):
    def test_whole_sentences_up_to_the_length(self):
        # Honduras's quotation ended "...Then, muncipality-..." at 220 characters.
        method = ("Projections by INE. Then, municipality-level estimates were derived "
                  "from the census. " + "Further detail follows here. " * 20)
        quoted = cpa.method_quote(method)
        self.assertTrue(quoted.endswith("."), quoted)
        self.assertLessEqual(len(quoted), cpa.QUOTE_LENGTH)
        self.assertTrue(quoted.startswith("Projections by INE. Then, municipality-level"))

    def test_a_first_sentence_is_quoted_whole_however_long(self):
        method = "One long sentence " + "of words " * 60 + "ends here. Then more."
        self.assertTrue(cpa.method_quote(method).endswith("ends here."))

    def test_no_method_no_quote(self):
        self.assertEqual(cpa.method_quote(""), "")


class GroupedMedian(unittest.TestCase):
    def test_interpolates_within_the_group_holding_the_middle_person(self):
        # 100 people; the 50th falls 10 of 40 into ages 10-14.
        self.assertEqual(cpa.grouped_median([(0, 4, 20), (5, 9, 20), (10, 14, 40),
                                             (15, None, 20)]), 11.2)

    def test_none_when_the_middle_person_is_in_the_open_group(self):
        self.assertIsNone(cpa.grouped_median([(0, 4, 10), (5, None, 90)]))


class Columns(unittest.TestCase):
    def test_reads_female_and_male_groups(self):
        cols = cpa.age_columns(columns())
        self.assertEqual(cols["sexes"], "FM")
        self.assertEqual(cols["opens"]["F"], (20, "F_20Plus"))

    def test_prefers_the_both_sexes_groups(self):
        self.assertEqual(cpa.age_columns(columns("TFM"))["sexes"], "T")

    def test_a_gap_in_the_ages_is_no_breakdown(self):
        self.assertIsNone(cpa.age_columns(columns(open_at=25)))

    def test_venezuela_writes_its_totals_bare(self):
        cols = cpa.age_columns([c for c in columns(total="T") if c not in ("F_TL", "M_TL")]
                               + ["F", "M"])
        self.assertEqual(cols["totals"], {"T": "T", "F": "F", "M": "M"})


class UnitFigures(unittest.TestCase):
    def setUp(self):
        self.cols = cpa.age_columns(columns())

    def test_median_and_ratio(self):
        figures, _ = cpa.unit_figures(row([10, 10, 20, 10, 0], [10, 10, 20, 10, 0]), self.cols)
        self.assertEqual(figures["median"], 11.2)
        self.assertEqual(figures["ratio"], 1000)
        # The groups the median is taken from, both sexes added, for the build
        # to add a union's parts together.
        self.assertEqual(figures["groups"], [(0, 4, 20), (5, 9, 20), (10, 14, 40),
                                             (15, 19, 20), (20, None, 0)])

    def test_groups_that_miss_the_total_are_refused(self):
        bad = row([10, 10, 20, 10, 0], [10, 10, 20, 10, 0])
        bad["T_TL"] = 150
        bad["F_TL"] = bad["M_TL"] = 75
        figures, why = cpa.unit_figures(bad, self.cols)
        self.assertIsNone(figures)
        self.assertIn("age groups", why)

    def test_women_and_men_must_make_the_total(self):
        bad = row([10, 10, 20, 10, 0], [10, 10, 20, 10, 0])
        bad["M_TL"] = 80
        figures, why = cpa.unit_figures(bad, self.cols)
        self.assertIsNone(figures)
        self.assertIn("do not add up", why)


class Coverage(unittest.TestCase):
    def test_the_default_run_reads_the_americas_and_africa(self):
        # A run with no --only rewrites the whole file, so a default that
        # dropped either region would empty its units on the next refresh.
        self.assertTrue(cpa.AMERICAS <= cpa.DEFAULT)
        self.assertTrue(cpa.AFRICA <= cpa.DEFAULT)
        self.assertEqual(len(cpa.AFRICA), 54)
        self.assertFalse(cpa.AMERICAS & cpa.AFRICA)


if __name__ == "__main__":
    unittest.main()
