"""Tabulating CFPS microdata: what counts, what is weighed, what is refused."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.fetch_census import cfps_microdata as m  # noqa: E402


class Tabulate(unittest.TestCase):
    def test_weighted_shares_and_unweighted_counts(self):
        rows = [(31, 1, 2.0), (31, 6, 1.0), (31, 6, 1.0),   # Shanghai: Buddhism 2 of 4 weight
                (31, -8, 5.0), (31, -1, 5.0),                # non-answers: out of both
                (21, 4, 1.0)]
        t = m.tabulate(rows)
        self.assertEqual(t[31]["n"], 3)
        self.assertEqual(t[31]["shares"], {"Buddhism": 50.0, "No religion": 50.0})
        self.assertEqual(t[21], {"n": 1, "shares": {"Protestant": 100.0}})

    def test_a_missing_weight_is_left_out_only_when_weighing(self):
        rows = [(31, 1, None), (31, 6, 1.0)]
        self.assertEqual(m.tabulate(rows), {31: {"n": 1, "shares": {"No religion": 100.0}}})
        self.assertEqual(m.tabulate(rows, weighted=False),
                         {31: {"n": 2, "shares": {"Buddhism": 50.0, "No religion": 50.0}}})

    def test_the_self_check_allows_the_re_release_s_few_rows(self):
        by_name = {name: (shares, n) for name, _, shares, n in m.PAPER_TABLE}
        table = {}
        for code in m.SELF_REPRESENTATIVE:
            shares, n = by_name[m.PROVINCES[code]]
            table[code] = {"n": n + 3, "shares": dict(zip(m.PAPER_GROUPS, shares))}
        m.check_against_paper(table)   # three rows more is the re-release, not an error
        table[31]["n"] = by_name["Shanghai Municipality"][1] + 300
        with self.assertRaises(SystemExit):
            m.check_against_paper(table)

    def test_the_self_check_refuses_a_wrong_count(self):
        table = {code: {"n": 1, "shares": {"No religion": 100.0}}
                 for code in m.SELF_REPRESENTATIVE}
        with self.assertRaises(SystemExit) as cm:
            m.check_against_paper(table)
        self.assertIn("against the paper's", str(cm.exception))

    def test_the_self_check_passes_the_paper_itself(self):
        # The paper's own table, fed back as if tabulated, must pass.
        by_name = {name: (shares, n) for name, _, shares, n in m.PAPER_TABLE}
        table = {}
        for code in m.SELF_REPRESENTATIVE:
            shares, n = by_name[m.PROVINCES[code]]
            table[code] = {"n": n, "shares": dict(zip(m.PAPER_GROUPS, shares))}
        m.check_against_paper(table)   # no exception

    def test_only_five_provinces_are_self_representative(self):
        self.assertEqual({m.PROVINCES[c] for c in m.SELF_REPRESENTATIVE},
                         {"Shanghai Municipality", "Liaoning Province", "Henan Province",
                          "Gansu Province", "Guangdong"})
