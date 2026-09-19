"""Japan's prefectures under the owner's decision: what is read, what is
modelled, and what the arithmetic promises.

The believers figures are e-Stat table 0003282963 at 2025年度 as the runner
read them (data/processed/last-run.log of the probe that fetched all 240
values); the nationality table is synthetic, built so its national row is
the Statistics Bureau's published one and its prefectures sum to it.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import common  # noqa: E402
from scripts.fetch_census import japan as m  # noqa: E402

# 全国 and three prefectures, 信者 by 宗教系統 (総数, 神道系, 仏教系, キリスト教系,
# 諸教), as e-Stat served them for 2025年度.
SIGNAL = {
    "00000": (175054047, 86359612, 80463918, 1872320, 6358197),
    "13000": (43771635, 7238190, 35352899, 481024, 699522),      # Tokyo
    "42000": (2069631, 1043216, 962734, 41932, 21749),           # Nagasaki
    "47000": (895540, 809800, 48264, 25722, 11754),              # Okinawa
}


def believers_for(codes):
    """A believers table over the named prefectures, the rest filled so the
    47 sum exactly to the national row."""
    table = {}
    named = [c for c in codes if c != "00000"]
    for c in ["00000"] + named:
        total, *parts = SIGNAL[c]
        table[c] = {"100": total, "110": parts[0], "120": parts[1],
                    "130": parts[2], "140": parts[3]}
    rest = [p for p in m.PREFECTURES if p not in named]
    parts = ("110", "120", "130", "140")
    remainder = {k: table["00000"][k] - sum(table[c][k] for c in named) for k in parts}
    for i, p in enumerate(rest):
        table[p] = {k: remainder[k] // len(rest) + (remainder[k] % len(rest) if i == 0 else 0)
                    for k in parts}
        table[p]["100"] = sum(table[p][k] for k in parts)
    return table


def nationality_table():
    nat = dict(m.PUBLISHED)
    counts = {"2": 121_541_220, "101": nat["Korean"], "102": nat["Chinese"],
              "103": nat["Filipino"], "104": nat["Thai"], "105": nat["Indonesian"],
              "106": nat["Vietnamese"], "107": 36_000, "108": nat["Nepalese"],
              "109": 13_000, "110": nat["American"], "111": nat["Brazilian"],
              "112": nat["Peruvian"]}
    counts["113"] = nat["foreign"] - sum(v for k, v in counts.items() if k != "2")
    counts["3"] = 2_202_419
    prefs = list(m.PREFECTURES)
    table = {p: {k: v // len(prefs) for k, v in counts.items()} for p in prefs}
    for k, v in counts.items():
        table["13000"][k] += v - sum(table[p][k] for p in prefs)
    for p in prefs:
        table[p]["1"] = sum(table[p][c] for c in m.NATIONALITY_CODES if c != "2")
        table[p]["0"] = table[p]["2"] + table[p]["1"] + table[p]["3"]
    table["00000"] = {k: sum(table[p][k] for p in prefs) for k in table["13000"]}
    return table


class Tilt(unittest.TestCase):
    PRIOR = {"Buddhism": 30.0, "Shinto": 4.0, "Christianity": 1.0, "Other religions": 1.0}
    NATIONAL = {"Buddhism": 50.0, "Shinto": 40.0, "Christianity": 5.0, "Other religions": 5.0}

    def test_a_unit_with_the_national_pattern_is_the_prior(self):
        shares, ratios, held = m.tilt(self.PRIOR, 64.0, self.NATIONAL, dict(self.NATIONAL),
                                      caps={})
        for g in self.PRIOR:
            self.assertAlmostEqual(ratios[g], 1.0)
            self.assertAlmostEqual(shares[g], self.PRIOR[g])
        self.assertEqual(shares["No religion"], 64.0)
        self.assertEqual(held, [])

    def test_the_tilt_is_relative_and_the_affiliated_total_is_kept(self):
        # Christianity is 10 of 80 here against 5 of 100 nationally, Buddhism
        # 25 of 80 against 50 of 100: the ratios say so, and the four still
        # sum to the prior's 36.
        unit = {"Buddhism": 25.0, "Shinto": 40.0, "Christianity": 10.0, "Other religions": 5.0}
        shares, ratios, _ = m.tilt(self.PRIOR, 64.0, self.NATIONAL, unit, caps={})
        self.assertAlmostEqual(ratios["Christianity"], 0.125 / 0.05)
        self.assertAlmostEqual(ratios["Buddhism"], 0.3125 / 0.5)
        self.assertAlmostEqual(sum(shares[g] for g in self.PRIOR), 36.0)
        self.assertAlmostEqual(sum(shares.values()), 100.0)

    def test_the_ratio_is_clipped(self):
        unit = {"Buddhism": 1.0, "Shinto": 1.0, "Christianity": 98.0, "Other religions": 0.0}
        _, ratios, _ = m.tilt(self.PRIOR, 64.0, self.NATIONAL, unit, bound=3.0, caps={})
        self.assertEqual(ratios["Christianity"], 3.0)
        self.assertAlmostEqual(ratios["Buddhism"], 1 / 3)
        self.assertAlmostEqual(ratios["Other religions"], 1 / 3)

    def test_a_cap_holds_the_share_and_rescales_the_rest(self):
        unit = {"Buddhism": 1.0, "Shinto": 1.0, "Christianity": 98.0, "Other religions": 0.0}
        shares, _, held = m.tilt(self.PRIOR, 64.0, self.NATIONAL, unit, bound=10.0,
                                 caps={"Christianity": 5.0})
        self.assertEqual(held, ["Christianity"])
        self.assertAlmostEqual(shares["Christianity"], 5.0)
        self.assertAlmostEqual(sum(shares[g] for g in self.PRIOR), 36.0)
        self.assertGreater(shares["Buddhism"], 0)

    def test_the_stated_bounds_bind_on_the_real_signal(self):
        # Okinawa reports 90% of its believers as Shinto; the bound is what
        # keeps that artefact off the map.
        prior, none = m.prior_shares()
        national = {m.TRADITIONS[c]: float(SIGNAL["00000"][i + 1])
                    for i, c in enumerate(("110", "120", "130", "140"))}
        okinawa = {m.TRADITIONS[c]: float(SIGNAL["47000"][i + 1])
                   for i, c in enumerate(("110", "120", "130", "140"))}
        shares, ratios, held = m.tilt(prior, none, national, okinawa)
        self.assertIn("Shinto", held)
        self.assertLessEqual(shares["Shinto"], m.CAPS["Shinto"])
        self.assertLessEqual(shares["Christianity"], m.CAPS["Christianity"])
        self.assertAlmostEqual(sum(shares.values()), 100.0)

    def test_the_prior_leaves_out_the_no_answer_and_sums_to_100(self):
        prior, none = m.prior_shares()
        self.assertAlmostEqual(sum(prior.values()) + none, 100.0)
        self.assertAlmostEqual(none / sum(prior.values()), m.PRIOR_NONE / sum(m.PRIOR.values()))


class Hundred(unittest.TestCase):
    def test_rounds_to_exactly_100(self):
        rows = m.hundred({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0)
        self.assertEqual([r["pct"] for r in rows], [33.4, 33.3, 33.3])

    def test_a_zero_share_is_dropped_and_ties_break_on_the_name(self):
        rows = m.hundred({"b": 1.0, "a": 1.0, "z": 0.0})
        self.assertEqual([r["group"] for r in rows], ["a", "b"])


class Language(unittest.TestCase):
    def test_every_nationality_has_a_language_that_the_tree_places(self):
        import canonical_groups as cg
        for label in m.NATIONALITY_CODES.values():
            self.assertIn(label, m.LANGUAGE_OF)
            self.assertGreater(len(cg.ancestry("language", m.LANGUAGE_OF[label])), 1,
                               m.LANGUAGE_OF[label])
            self.assertGreater(len(cg.ancestry("ethnicity", label)), 1, label)

    def test_nationalities_sharing_a_language_are_summed(self):
        out = m.languages_from({"American": 30.0, "British": 10.0, "Japanese": 9960.0})
        self.assertEqual(out["English"], 40.0)
        self.assertEqual(out["Japanese"], 9960.0)

    def test_a_language_too_small_to_round_folds_into_other(self):
        out = m.languages_from({"Japanese": 99_990.0, "Thai": 5.0, "Other nationalities": 5.0})
        self.assertNotIn("Thai", out)
        self.assertEqual(out["Other languages"], 10.0)

    def test_an_unmapped_nationality_is_refused(self):
        with self.assertRaises(KeyError):
            m.languages_from({"Martian": 1.0})


class Checks(unittest.TestCase):
    def test_the_nationality_table_must_reproduce_the_published_figures(self):
        table = nationality_table()
        m.check_nationality(table)      # no exception
        bad = {k: dict(v) for k, v in table.items()}
        bad["13000"]["102"] += 1000
        bad["00000"]["102"] += 1000
        bad["13000"]["1"] += 1000
        bad["00000"]["1"] += 1000
        bad["13000"]["0"] += 1000
        bad["00000"]["0"] += 1000
        with self.assertRaises(SystemExit) as cm:
            m.check_nationality(bad)
        self.assertIn("published", str(cm.exception))

    def test_a_prefecture_that_does_not_sum_to_the_national_row_is_refused(self):
        table = nationality_table()
        table["13000"]["102"] += 1
        with self.assertRaises(SystemExit) as cm:
            m.check_nationality(table)
        self.assertIn("national", str(cm.exception))

    def test_a_signal_that_partitions_the_population_is_not_this_signal(self):
        table = believers_for(["13000"])
        population = {"00000": 126_146_099}
        m.check_believers(table, population)
        with self.assertRaises(SystemExit):
            m.check_believers(table, {"00000": 500_000_000})


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = m.build(nationality_table(), believers_for(["13000", "42000", "47000"]))
        cls.by_name = {r["name"]: r for r in cls.records}

    def test_47_prefectures_named_as_the_boundary_file_names_them(self):
        self.assertEqual(len(self.records), 47)
        self.assertEqual({r["name"] for r in self.records},
                         {name for _, name in m.PREFECTURES.values()})
        for r in self.records:
            self.assertEqual(r["level"], "admin1")
            self.assertEqual(r["parent"], "JPN")
            self.assertEqual(r["country"], "JPN")

    def test_ethnicity_is_a_list_and_the_estimates_are_estimates(self):
        for r in self.records:
            self.assertIsInstance(r["ethnicity"], list)
            self.assertEqual(r["ethnicity_basis"], "nationality")
            self.assertEqual(r["ethnicity_year"], 2020)
            self.assertTrue(common.is_estimate(r["religion"]))
            self.assertTrue(common.is_estimate(r["language"]))
            self.assertTrue(common.is_gap(r["religion"]))
            self.assertTrue(common.is_gap(r["language"]))
            self.assertEqual(r["religion"]["method"], m.RELIGION_METHOD)
            self.assertEqual(r["language"]["method"], "tier1-nationality-to-language")

    def test_every_composition_sums_to_100(self):
        for r in self.records:
            self.assertAlmostEqual(sum(g["pct"] for g in r["ethnicity"]), 100.0, delta=0.3)
            for field in ("religion", "language"):
                self.assertAlmostEqual(sum(g["pct"] for g in r[field]["estimate"]), 100.0,
                                       delta=0.05)

    def test_no_backtest_is_claimed(self):
        for r in self.records:
            self.assertNotIn("backtest", r["religion"])
            self.assertNotIn("backtest", r["language"])
            self.assertIn("No backtest is possible", r["religion"]["note"])
            self.assertIn("No backtest is possible", r["language"]["note"])

    def test_the_notes_say_what_they_are_and_when_it_was_decided(self):
        for r in self.records:
            for field in ("religion", "language"):
                note = r[field]["note"]
                self.assertTrue(note.startswith("MODELLED, not read"))
                self.assertIn(m.DECISION, note)
                self.assertIn("not evidence of what any census says", note)
            self.assertIn("NATIONALITY, not ethnicity", r["ethnicity_note"])
            self.assertIn("naturalised", r["ethnicity_note"])
            self.assertIn(m.DECISION, r["ethnicity_note"])

    def test_the_bounds_hold_on_every_prefecture(self):
        for r in self.records:
            shares = {g["group"]: g["pct"] for g in r["religion"]["estimate"]}
            self.assertLessEqual(shares.get("Shinto", 0), m.CAPS["Shinto"])
            self.assertLessEqual(shares.get("Christianity", 0), m.CAPS["Christianity"])
            self.assertIn("No religion", shares)

    def test_tokyo_tilts_towards_buddhism_and_okinawa_hits_the_bounds(self):
        tokyo = {g["group"]: g["pct"] for g in self.by_name["Tokyo"]["religion"]["estimate"]}
        prior, _ = m.prior_shares()
        self.assertGreater(tokyo["Buddhism"], prior["Buddhism"])
        self.assertGreater(self.by_name["Tokyo"]["religion"]["tilt"]["Buddhism"], 1.0)
        okinawa = self.by_name["Okinawa Prefecture"]["religion"]
        self.assertEqual(okinawa["capped"], ["Shinto", "Christianity"])
        self.assertIn("held there", okinawa["note"])

    def test_language_follows_nationality(self):
        r = self.by_name["Nagasaki Prefecture"]
        japanese = next(g for g in r["ethnicity"] if g["group"] == "Japanese")["pct"]
        spoken = {g["group"]: g["pct"] for g in r["language"]["estimate"]}
        self.assertEqual(spoken["Japanese"], japanese)
        self.assertIn(r["id"], r["language"]["inputs"])

    def test_an_estimate_survives_merge_adapter_onto_a_blank_shape(self):
        import build_entities as be
        row = dict(self.by_name["Kyoto Prefecture"])
        shape = {"id": "x", "name": "Kyoto Prefecture", "country": "JPN", "sources": [],
                 "religion": common.gap(common.NOT_AVAILABLE),
                 "language": common.gap(common.NOT_AVAILABLE),
                 "ethnicity": common.gap(common.NOT_AVAILABLE)}
        be.merge_adapter(shape, row)
        self.assertTrue(common.is_estimate(shape["religion"]))
        self.assertTrue(common.is_estimate(shape["language"]))
        self.assertIsInstance(shape["ethnicity"], list)
        self.assertEqual(shape["ethnicity_basis"], "nationality")
        # And the build's guard lets it through, now that Japan declares no policy.
        self.assertIsNone(common.collection_gap("JPN", "religion"))
        be.check_no_estimate_on_policy_field({"JPN": [shape]})


if __name__ == "__main__":
    unittest.main()
