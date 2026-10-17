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


def unit(name, level, groups, ratio=1000, parent=None):
    """A written record as country_records leaves it, groups [[low, high, people]]."""
    rec = cpa.record(f"X-{name}", name, level=level, parent="XXX", country="XXX",
                     parent_name=parent,
                     median_age={"value": 20.0, "unit": "years", "year": 2022, "source": "s"},
                     median_age_note="interpolated",
                     sex_ratio={"value": ratio, "unit": "males_per_1000_females",
                                "year": 2022, "source": "s"},
                     sex_ratio_note="males per 1,000 females",
                     sources=[{"field": "median_age/sex_ratio", "name": "s"}],
                     age_groups=[list(g) for g in groups])
    return rec


YOUNG = [(0, 14, 450.0), (15, 64, 520.0), (65, None, 30.0)]
OLDER = [(0, 14, 300.0), (15, 64, 600.0), (65, None, 100.0)]
MIDDLE = [(0, 14, 380.0), (15, 64, 560.0), (65, None, 60.0)]


def scaled(groups, k):
    return [(lo, hi, n * k) for lo, hi, n in groups]


class NamesakeLevel(unittest.TestCase):
    def test_a_short_table_landing_on_the_other_level_is_refused(self):
        # Niger: the file's adm1 table, eight regions, matched the departments
        # named after the regional capitals (67 drawn at the second level).
        regions = ["Agadez", "Diffa", "Dosso", "Maradi", "Niamey", "Tahoua", "Tillaberi", "Zinder"]
        why = cpa.namesake_level("1", "admin2", regions, 67)
        self.assertIsNotNone(why)
        self.assertIn("8 rows", why)

    def test_a_table_the_size_of_the_level_it_lands_on_stands(self):
        # Romania: the file's adm2 table is the 42 judete, this map's first level.
        self.assertIsNone(cpa.namesake_level("2", "admin1", [f"J{i}" for i in range(42)], 42))

    def test_agreement_is_never_refused(self):
        self.assertIsNone(cpa.namesake_level("2", "admin2", ["a", "b"], 300))


class CopiedStructures(unittest.TestCase):
    def test_one_structure_for_every_unit_withdraws_the_medians_and_keeps_the_ratios(self):
        # Liberia: every county carries the national proportions.
        recs = [unit(f"c{i}", "admin1", scaled(YOUNG, 1 + i), ratio=950 + 20 * i)
                for i in range(5)]
        out = cpa.drop_copied_structures("LBR", recs)
        for rec in out:
            self.assertEqual(rec["median_age"]["status"], "not_available")
            self.assertIn("the same age proportions", rec["median_age"]["note"])
            self.assertNotIn("median_age_note", rec)
            self.assertNotIn("age_groups", rec)
            self.assertIn("value", rec["sex_ratio"])
            self.assertEqual(rec["sources"][0]["field"], "sex_ratio")

    def test_districts_with_their_regions_proportions_and_ratios_lose_both(self):
        # Burkina Faso: each province carries its region's ages and sexes.
        regions = [unit("North", "admin1", YOUNG, ratio=930),
                   unit("South", "admin1", OLDER, ratio=980)]
        provinces = [unit(f"n{i}", "admin2", scaled(YOUNG, 0.2 + i), ratio=930, parent="North")
                     for i in range(3)] + \
                    [unit(f"s{i}", "admin2", scaled(OLDER, 0.3 + i), ratio=981, parent="South")
                     for i in range(3)]
        out = cpa.drop_copied_structures("BFA", regions + provinces)
        for rec in out:
            if rec["level"] == "admin1":
                self.assertIn("value", rec["median_age"])
                self.assertIn("value", rec["sex_ratio"])
            else:
                self.assertIn("first-level division it lies in", rec["median_age"]["note"])
                self.assertIn("men and women", rec["sex_ratio"]["note"])
                self.assertEqual(rec["sources"], [])

    def test_districts_with_their_own_share_of_men_keep_their_ratios(self):
        # Paraguay: the departments' ages, but each district's own sexes.
        regions = [unit("Central", "admin1", YOUNG, ratio=990),
                   unit("Guaira", "admin1", OLDER, ratio=1010)]
        districts = [unit(f"d{i}", "admin2", scaled(YOUNG, 0.1 + i), ratio=900 + 40 * i,
                          parent="Central") for i in range(4)]
        out = cpa.drop_copied_structures("PRY", regions + districts)
        for rec in out[2:]:
            self.assertEqual(rec["median_age"]["status"], "not_available")
            self.assertIn("value", rec["sex_ratio"])

    def test_one_district_like_its_region_is_no_copy(self):
        # A city that is nearly all of its province can honestly match it.
        regions = [unit("A", "admin1", YOUNG), unit("B", "admin1", OLDER)]
        districts = [unit("a1", "admin2", scaled(YOUNG, 0.9), parent="A"),
                     unit("a2", "admin2", OLDER, parent="A"),
                     unit("b1", "admin2", MIDDLE, parent="B"),
                     unit("b2", "admin2", YOUNG, parent="B")]
        out = cpa.drop_copied_structures("XXX", regions + districts)
        self.assertTrue(all("value" in rec["median_age"] for rec in out))

    def test_distinct_units_are_left_alone(self):
        recs = [unit("a", "admin1", YOUNG), unit("b", "admin1", OLDER),
                unit("c", "admin1", MIDDLE)]
        out = cpa.drop_copied_structures("XXX", recs)
        self.assertTrue(all("value" in rec["median_age"] for rec in out))


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
