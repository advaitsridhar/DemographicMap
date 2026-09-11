"""Tests for the PRRI county-religion reader in scripts/fetch_census/us_prri.py.

A caveat that belongs at the top of this file rather than buried in it: the
fixtures below are **synthetic**. The adapter has never been run against the
real Datawrapper tables, because ``datawrapper.dwcdn.net`` and ``prri.org`` are
both refused by the egress proxy on the machine this was written on, so nobody
here has seen PRRI's actual CSV header. The fixtures reproduce the *shape* a
Datawrapper county choropleth table has -- a county name column, a column of
5-digit FIPS codes, one column of percentages -- and the percentages are made
up. What is being tested is therefore the reader's behaviour and its refusals,
not agreement with PRRI's numbers; the national roll-up check in the adapter is
the thing that tests agreement, and it can only run where the CDN is reachable.

The refusals are the point. Every case here is a way eighteen separate charts
can be joined into one county table wrongly without anything looking wrong: a
chart silently absent leaves every county summing to less than 100, a category
filed under the wrong node leaves the sums perfect and the map wrong, and a
FIPS code that was reassigned between vintages joins one county's religion onto
another county's shape.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.fetch_census.us_prri as us_prri  # noqa: E402

from scripts.fetch_census.us_prri import (  # noqa: E402
    CHARTS, COLLAPSE, EXCLUDED, build, censored, check_coverage, check_national,
    check_sums, classify, collapse, normalise, read_dataset, split_rows,
)

# Enough rows that the reader will accept the table as county-level at all;
# its FIPS test deliberately refuses anything short, because a real county
# table has about 3,100 rows and a 5-row one is a different table.
N_ROWS = 150


def fips_at(i: int) -> str:
    """A plausible 5-digit county FIPS, state 01 upward."""
    return f"{i // 100 + 1:02d}{i % 100 + 1:03d}"


def table(values: list[float] | None = None, *, header=("County", "FIPS", "Percent"),
          rows: int = N_ROWS) -> str:
    """A Datawrapper-shaped county CSV. Values are invented."""
    values = values if values is not None else [10.0] * rows
    out = [",".join(header)]
    for i in range(rows):
        out.append(f"County {i},{fips_at(i)},{values[i]}")
    return "\n".join(out)


def spread(national: dict[str, float], rows: int = N_ROWS) -> dict[str, dict[str, float]]:
    """Give every county the same made-up composition, keyed by category."""
    return {cat: {fips_at(i): pct for i in range(rows)}
            for cat, pct in national.items()}


# A synthetic composition whose collapsed roll-up lands on PRRI's published
# national anchors: Christian 66, religiously unaffiliated 27, non-Christian 6.
# Those three are whole-percent figures and they sum to 99, not 100 -- which is
# itself the reason the adapter's tolerances are not hairline. The fixture puts
# the missing point on the unaffiliated, the group whose "nothing in particular"
# tail is widest, so that it closes at 100 and still sits inside the 2.5-point
# national band. The individual numbers are invented; only the totals are meant
# to resemble anything.
COMPOSITION = {
    "White Evangelical Protestant": 13.0,
    "White Mainline/Non-evangelical Protestant": 13.0,
    "Black Protestant": 8.0,
    "Hispanic Protestant": 4.0,
    "Other Protestant of Color": 2.0,
    "White Catholic": 12.0,
    "Hispanic Catholic": 8.0,
    "Other Catholic of Color": 2.0,
    "Latter-day Saint (Mormon)": 1.5,
    "Orthodox Christian": 0.5,
    "Jehovah's Witness": 2.0,
    "Jewish": 2.0,
    "Muslim": 1.0,
    "Buddhist": 1.0,
    "Hindu": 1.0,
    "Unitarian Universalist": 0.5,
    "Other Non-Christian Religious": 0.5,
    "Religiously Unaffiliated": 28.0,
}


def universe(n: int, *, names: dict[str, str] | None = None) -> list[dict]:
    """The county universe us_acs.py writes, reduced to what the join uses."""
    names = names or {}
    out = []
    for i in range(n):
        fips = fips_at(i)
        out.append({
            "id": f"USA-{fips}",
            "name": names.get(fips, f"County {i}"),
            "parent": f"USA-{fips[:2]}",
            "codes": {"geoid": fips, "fips_state": fips[:2],
                      "fips_county": fips[2:]},
            "population": {"value": 10_000},
        })
    return out


class ReadDataset(unittest.TestCase):
    """One chart's CSV -> {FIPS: percent}."""

    def test_reads_a_county_table(self):
        got = read_dataset(table(), chart="d76SP")
        self.assertEqual(len(got), N_ROWS)
        self.assertEqual(got["01001"], 10.0)

    def test_pads_four_digit_fips(self):
        """Alabama's 01001 is often written 1001 once a spreadsheet has been
        near it. Joining '1001' against a map keyed on '01001' matches nothing,
        so the pad happens at the reader rather than at the join."""
        rows = ["County,FIPS,Percent"]
        rows += [f"County {i},{int(fips_at(i))},{10.0}" for i in range(N_ROWS)]
        got = read_dataset("\n".join(rows), chart="d76SP")
        self.assertIn("01001", got)

    def test_accepts_percent_signs_and_commas(self):
        rows = ["County,FIPS,Percent"]
        rows += [f"County {i},{fips_at(i)},10.5%" for i in range(N_ROWS)]
        got = read_dataset("\n".join(rows), chart="d76SP")
        self.assertAlmostEqual(got["01001"], 10.5)

    def test_finds_the_columns_whatever_they_are_called(self):
        """The header is not trusted: the adapter was written without sight of
        the real one, so the columns are found by content."""
        got = read_dataset(table(header=("name", "id", "value")), chart="d76SP")
        self.assertEqual(got["01001"], 10.0)

    def test_refuses_a_table_that_is_not_county_level(self):
        """A state table has no 5-digit FIPS column, and reading one as if it
        were counties is the mis-match this whole adapter is written against."""
        rows = ["State,FIPS,Percent"] + [f"State {i},{i:02d},10.0" for i in range(N_ROWS)]
        with self.assertRaises(SystemExit) as cm:
            read_dataset("\n".join(rows), chart="d76SP")
        self.assertIn("not the county-level table", str(cm.exception))

    def test_refuses_a_short_table(self):
        """Three thousand counties do not fit in five rows."""
        with self.assertRaises(SystemExit):
            read_dataset(table(rows=5), chart="d76SP")

    def test_refuses_two_candidate_value_columns(self):
        """Which of two numeric series is the percentage cannot be settled
        without guessing, so it is not guessed."""
        rows = ["County,FIPS,Percent,Margin"]
        rows += [f"County {i},{fips_at(i)},10.0,1.2" for i in range(N_ROWS)]
        with self.assertRaises(SystemExit) as cm:
            read_dataset("\n".join(rows), chart="d76SP")
        self.assertIn("numeric value", str(cm.exception))

    def test_refuses_a_duplicated_county(self):
        rows = ["County,FIPS,Percent"]
        rows += [f"County {i},{fips_at(i)},10.0" for i in range(N_ROWS)]
        rows.append("County 0 again,01001,99.0")
        with self.assertRaises(SystemExit) as cm:
            read_dataset("\n".join(rows), chart="d76SP")
        self.assertIn("twice", str(cm.exception))

    def test_refuses_an_empty_chart(self):
        with self.assertRaises(SystemExit):
            read_dataset("County,FIPS,Percent\n", chart="d76SP")


class FirstContact(unittest.TestCase):
    """The ways a real Datawrapper table can differ from the guessed one.

    None of this is known to be what PRRI publishes -- that is what the
    --probe path is for. These are the shapes that must not be read wrongly if
    they do turn up.
    """

    def test_reads_a_tab_separated_table(self):
        """Read with the comma reader, a TSV is one fused column and the
        refusal that follows blames the wrong thing."""
        rows = ["County\tFIPS\tPercent"]
        rows += [f"County {i}\t{fips_at(i)}\t10.0" for i in range(N_ROWS)]
        parsed, delimiter = split_rows("\n".join(rows))
        self.assertEqual(delimiter, "\t")
        self.assertEqual(read_dataset("\n".join(rows), chart="d76SP")["01001"], 10.0)

    def test_reads_a_semicolon_separated_table(self):
        rows = ["County;FIPS;Percent"]
        rows += [f"County {i};{fips_at(i)};10.0" for i in range(N_ROWS)]
        self.assertEqual(read_dataset("\n".join(rows), chart="d76SP")["01001"], 10.0)

    def test_refuses_two_columns_that_both_look_like_fips(self):
        """A population column is five digits too. Taking the first candidate
        would key three thousand counties on their populations."""
        rows = ["County,FIPS,Population,Percent"]
        rows += [f"County {i},{fips_at(i)},{12000 + i},10.0" for i in range(N_ROWS)]
        with self.assertRaises(SystemExit) as cm:
            read_dataset("\n".join(rows), chart="d76SP")
        self.assertIn("cannot be decided without guessing", str(cm.exception))

    def test_a_population_column_is_not_mistaken_for_fips(self):
        """Populations stray outside the 01-56 state prefixes almost at once,
        which is what keeps them out of the FIPS candidates."""
        columns = [tuple(f"{90000 + i}" for i in range(N_ROWS))]
        fips_cols, value_cols = classify(columns)
        self.assertEqual(fips_cols, [])
        self.assertEqual(value_cols, [0])

    def test_refuses_a_censored_value(self):
        """PRRI writes small shares as '<0.5'. Reading that as zero understates
        the group and leaves the county short of 100; reading it as 0.5
        invents a number. So it stops and says how many there are."""
        rows = ["County,FIPS,Percent"]
        rows += [f"County {i},{fips_at(i)},10.0" for i in range(N_ROWS - 1)]
        rows.append(f"County {N_ROWS - 1},{fips_at(N_ROWS - 1)},<0.5")
        with self.assertRaises(SystemExit) as cm:
            read_dataset("\n".join(rows), chart="d76SP")
        self.assertIn("censors 1 counties", str(cm.exception))

    def test_censored_detects_both_bounds(self):
        self.assertTrue(censored("<0.5"))
        self.assertTrue(censored(" > 99"))
        self.assertFalse(censored("0.5"))
        self.assertFalse(censored(""))

    def test_ragged_rows_do_not_shift_columns(self):
        """A short final row is common in a hand-edited export; zip() would
        silently truncate every column to its length."""
        rows = ["County,FIPS,Percent"]
        rows += [f"County {i},{fips_at(i)},10.0" for i in range(N_ROWS)]
        rows.append("County trailing,")
        got = read_dataset("\n".join(rows), chart="d76SP")
        self.assertEqual(len(got), N_ROWS)

    def test_a_proportion_table_fails_the_sum_check(self):
        """If Datawrapper stores 0.135 rather than 13.5 every column test still
        passes. The sums are what notice, so this checks they do."""
        counties = collapse(spread({k: v / 100 for k, v in COMPOSITION.items()},
                                   rows=50))
        with self.assertRaises(SystemExit):
            check_sums(counties)


class Categories(unittest.TestCase):
    """The race-crossed categories, and how they collapse."""

    def test_every_chart_has_a_decided_node(self):
        self.assertEqual(sorted(CHARTS.values()), sorted(COLLAPSE))

    def test_the_diversity_index_is_not_a_group(self):
        """mL9BH is a 0-1 score. Reading it as an eighteenth share would add
        fifty-odd points to every county."""
        self.assertIn("mL9BH", EXCLUDED)
        self.assertNotIn("mL9BH", CHARTS)

    def test_protestant_variants_sum_into_one_node(self):
        got = collapse(spread(COMPOSITION, rows=2))
        # 13 + 13 + 8 + 4 + 2
        self.assertAlmostEqual(got["01001"]["Protestantism"], 40.0)
        # 12 + 8 + 2
        self.assertAlmostEqual(got["01001"]["Catholicism"], 22.0)

    def test_race_detail_is_gone_not_refiled(self):
        """No node in the output carries a racial term. The alternative --
        keeping 'White Evangelical Protestant' as a group -- would put race in
        the religion tree, where a reader filtering Protestantism misses most
        American Protestants."""
        got = collapse(spread(COMPOSITION, rows=2))
        for node in got["01001"]:
            for word in ("White", "Black", "Hispanic", "of Color"):
                self.assertNotIn(word, node)

    def test_unitarians_land_in_other_religions(self):
        got = collapse(spread(COMPOSITION, rows=2))
        self.assertAlmostEqual(got["01001"]["Other religions"], 1.0)

    def test_refuses_a_category_it_has_not_decided_about(self):
        """A nineteenth group in a later PRRI release must be mapped by hand."""
        extra = dict(spread(COMPOSITION, rows=2))
        extra["Neo-Druid"] = {"01001": 1.0, "01002": 1.0}
        with self.assertRaises(SystemExit) as cm:
            collapse(extra)
        self.assertIn("Neo-Druid", str(cm.exception))


class Coverage(unittest.TestCase):

    def test_reports_and_intersects_disagreeing_charts(self):
        data = spread(COMPOSITION, rows=10)
        data["Muslim"].pop("01001")
        common = check_coverage(data)
        self.assertNotIn("01001", common)
        self.assertEqual(len(common), 9)

    def test_refuses_charts_with_nothing_in_common(self):
        data = {"Muslim": {"01001": 1.0}, "Jewish": {"01002": 1.0}}
        with self.assertRaises(SystemExit):
            check_coverage(data)


class Sums(unittest.TestCase):

    def test_accepts_a_composition_that_closes(self):
        check_sums(collapse(spread(COMPOSITION, rows=50)))

    def test_accepts_rounding_sized_slack(self):
        """Eighteen separately modelled shares are not constrained to sum."""
        near = dict(COMPOSITION, Muslim=1.6)
        check_sums(collapse(spread(near, rows=50)))

    def test_refuses_one_county_far_from_100(self):
        counties = collapse(spread(COMPOSITION, rows=50))
        counties["01001"]["Protestantism"] += 40.0
        with self.assertRaises(SystemExit) as cm:
            check_sums(counties)
        self.assertIn("01001", str(cm.exception))

    def test_refuses_a_systematically_missing_chart(self):
        """The per-county band is loose enough to miss this; the median is not.
        Losing the Jewish chart leaves every county at 98 -- well inside the
        five-point per-county tolerance, and nowhere near the median's."""
        without = {k: v for k, v in COMPOSITION.items() if k != "Jewish"}
        with self.assertRaises(SystemExit) as cm:
            check_sums(collapse(spread(without, rows=50)))
        self.assertIn("systematic", str(cm.exception))


class National(unittest.TestCase):

    def setUp(self):
        self.pops = {fips_at(i): 10_000.0 for i in range(50)}

    def test_accepts_a_rollup_matching_the_published_figures(self):
        check_national(collapse(spread(COMPOSITION, rows=50)), self.pops)

    def test_refuses_a_category_collapsed_into_the_wrong_node(self):
        """The sums stay at 100 however the eighteen are filed. Only the
        published national totals notice that Catholics became Muslims."""
        counties = collapse(spread(COMPOSITION, rows=50))
        for groups in counties.values():
            groups["Islam"] = groups.pop("Catholicism") + groups["Islam"]
        with self.assertRaises(SystemExit) as cm:
            check_national(counties, self.pops)
        self.assertIn("Christian", str(cm.exception))

    def test_refuses_when_no_county_has_a_population(self):
        with self.assertRaises(SystemExit) as cm:
            check_national(collapse(spread(COMPOSITION, rows=50)), {})
        self.assertIn("cannot be weighted", str(cm.exception))


class Join(unittest.TestCase):
    """FIPS is the key. The name is only ever a check on it."""

    def setUp(self):
        self.n = 3_100
        self.counties = collapse(spread(COMPOSITION, rows=self.n))

    def test_builds_a_record_per_county(self):
        got = build(self.counties, universe(self.n))
        self.assertEqual(len(got), self.n)
        first = got[0]
        self.assertEqual(first["id"], "USA-01001")
        self.assertEqual(first["level"], "admin2")
        self.assertEqual(first["parent"], "USA-01")
        self.assertEqual(first["country"], "USA")
        self.assertEqual(first["codes"]["geoid"], "01001")
        self.assertEqual(first["religion_year"], 2023)
        self.assertEqual(first["religion_basis"], "self-identification")
        self.assertEqual(first["sources"][0]["field"], "religion")

    def test_religion_rows_are_sorted_and_sum_to_100(self):
        got = build(self.counties, universe(self.n))
        rows = got[0]["religion"]
        self.assertEqual([r["pct"] for r in rows],
                         sorted((r["pct"] for r in rows), reverse=True))
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0, places=1)
        self.assertEqual(rows[0]["group"], "Protestantism")

    def test_takes_the_name_from_the_map_not_from_prri(self):
        names = {"01001": "Autauga County, Alabama"}
        got = build(self.counties, universe(self.n, names=names))
        self.assertEqual(got[0]["name"], "Autauga County, Alabama")

    def test_accepts_a_name_that_differs_only_in_decoration(self):
        """'Autauga County, Alabama' and 'Autauga' are the same place."""
        names = {"01001": "Autauga County, Alabama"}
        got = build(self.counties, universe(self.n, names=names),
                    prri_names={"01001": "Autauga"})
        self.assertEqual(len(got), self.n)

    def test_refuses_a_fips_naming_a_different_county(self):
        """A FIPS whose name moved is usually a FIPS that was reassigned --
        Connecticut's 2022 planning regions are the live case. Joining it
        anyway puts one county's religion on another county's shape, which is
        invisible once it is on the map."""
        names = {"01001": "Autauga County, Alabama"}
        with self.assertRaises(SystemExit) as cm:
            build(self.counties, universe(self.n, names=names),
                  prri_names={"01001": "Litchfield"})
        self.assertIn("different county", str(cm.exception))

    def test_refuses_when_too_little_joins(self):
        """Part-matching two county vintages is worse than refusing both."""
        with self.assertRaises(SystemExit) as cm:
            build(self.counties, universe(2_800))
        self.assertIn("different county vintages", str(cm.exception))

    def test_refuses_an_implausible_county_count(self):
        small = collapse(spread(COMPOSITION, rows=100))
        with self.assertRaises(SystemExit) as cm:
            build(small, universe(100))
        self.assertIn("3,143", str(cm.exception))

    def test_unmatched_counties_are_dropped_not_forced(self):
        """A PRRI county with no shape is a visible gap, not a guess."""
        short = universe(self.n)[:-20]
        got = build(self.counties, short)
        self.assertEqual(len(got), self.n - 20)


class Probe(unittest.TestCase):
    """The read-only path that corrects the column rules against the real file.

    It runs on the Actions runner, where the CDN is reachable; here only its
    argument handling and its refusal behaviour can be exercised, so the fetch
    itself is stubbed.
    """

    def run_main(self, argv: list[str], fake_probe):
        with mock.patch.object(us_prri, "probe", fake_probe), \
             mock.patch.object(sys, "argv", ["us_prri.py"] + argv):
            return us_prri.main()

    def test_probes_every_chart_and_writes_nothing(self):
        seen = []
        with mock.patch.object(us_prri, "write_json") as written:
            code = self.run_main(["--probe", "--chart", "all"],
                                 lambda chart, rows: seen.append(chart))
        self.assertEqual(code, 0)
        self.assertEqual(seen, list(CHARTS))
        written.assert_not_called()

    def test_one_failing_chart_does_not_hide_the_rest(self):
        """A probe's whole value is coming back with every surprise at once."""
        seen = []

        def flaky(chart, rows):
            seen.append(chart)
            if chart == "JscmH":
                raise SystemExit("us_prri: 404")

        code = self.run_main(["--probe", "--chart", "all"], flaky)
        self.assertEqual(seen, list(CHARTS))   # it kept going
        self.assertEqual(code, 1)              # and still ended red

    def test_refuses_a_chart_id_it_does_not_know(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main(["--probe", "--chart", "NOPE"], lambda chart, rows: None)
        self.assertIn("no such chart", str(cm.exception))

    def test_arguments_are_xargs_safe(self):
        """The runner passes these through
        ``printf '%s' "$ADAPTER" | xargs python3 -m``, which splits on
        whitespace and strips quotes. Any default carrying a space or a quote
        would arrive as two arguments."""
        parser = us_prri.build_parser()
        for action in parser._actions:
            for flag in action.option_strings:
                self.assertNotRegex(flag, r"[\s\"']")
            if isinstance(action.default, str):
                self.assertNotRegex(action.default, r"[\s\"']")


class Normalise(unittest.TestCase):

    def test_strips_type_words_and_state(self):
        self.assertEqual(normalise("Autauga County, Alabama"), "autauga")
        self.assertEqual(normalise("Orleans Parish, Louisiana"), "orleans")
        self.assertEqual(normalise("Doña Ana County"), normalise("Dona Ana"))

    def test_keeps_genuinely_different_names_apart(self):
        self.assertNotEqual(normalise("Litchfield"), normalise("Autauga"))


if __name__ == "__main__":
    unittest.main()
