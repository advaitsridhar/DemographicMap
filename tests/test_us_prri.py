"""Tests for the PRRI county-religion reader in scripts/fetch_census/us_prri.py.

The fixture is real. ``REAL_HEADER`` and ``REAL_ROWS`` are the header and the
first six data rows of
``https://datawrapper.dwcdn.net/d76SP/7/dataset.csv`` exactly as the adapter's
own ``--probe`` printed them from a GitHub Actions runner, which is the only
place in this project with egress to the CDN. The wider tables built here for
the county-count and join tests are generated in that same shape, and say so.

Two facts from that probe shape everything below. Every chart serves the *whole*
table -- all eighteen group columns, plus population, FIPS, county name and the
diversity index -- so this reads one chart rather than joining eighteen. And
the table's ``year`` column is ``2024`` in every row, which looks exactly like
a county FIPS code to any test that only asks "four or five digits beginning
with a valid state prefix", because 20 is Kansas. That near-miss is the reason
a key column has to prove it is distinct and non-constant as well.

The refusals are the point. Every case here is a way a wide table can be read
wrongly without anything looking wrong: a renamed column shifting which figure
is read as which religion, an unpadded FIPS silently dropping every state from
01 to 09, a category filed under the wrong node leaving the sums perfect and
the map wrong.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.fetch_census.us_prri as us_prri  # noqa: E402
from scripts.fetch_census.us_prri import (  # noqa: E402
    CHARTS, CHRISTIAN, CHRISTIAN_CATEGORIES, COLLAPSE, COLUMNS, EXCLUDED,
    PUBLISHED_CATEGORY, STRUCTURAL, build, censored,
    check_collapse, check_national, check_population, check_sums, collapse,
    cross_check,
    looks_like_key, normalise, read_table, split_rows,
)

REAL_HEADER = (
    "year,Population,fipsstcnty,fips_fct,white_evangelical_protestant,"
    "white_mainline_protestant,white_catholic,black_protestant,"
    "hispanic_catholic,hispanic_protestant,mormon,other_catholic,"
    "other_protestant,jehovahs_witness,orthodox_christian,jewish,muslim,"
    "buddhist,hindu,unitarian_universalist,other_religion,unaffiliated,"
    "diversity_index"
)

REAL_ROWS = [
    '2024,44335,1001,"Autauga County, AL",37.9,15.6,3.0,13.9,0.5,0.7,0.5,0.6,'
    '3.6,0.4,0.3,0.4,0.3,0.3,0.3,0.3,0.5,21.1,0.496',
    '2024,175265,1003,"Baldwin County, AL",31.9,22.4,8.5,6.3,2.4,2.8,0.9,1.0,'
    '5.1,0.6,0.5,0.8,0.5,0.6,0.5,0.4,0.8,14.1,0.558',
    '2024,18031,1005,"Barbour County, AL",30.0,11.2,2.8,27.6,1.2,1.6,0.5,0.4,'
    '1.6,0.4,0.3,0.3,0.4,0.4,0.4,0.3,0.4,20.3,0.493',
    '2024,17421,1007,"Bibb County, AL",47.4,13.7,2.8,8.3,0.4,0.5,0.4,0.3,0.5,'
    '0.3,0.3,0.2,0.2,0.2,0.2,0.2,0.3,23.7,0.502',
    '2024,45114,1009,"Blount County, AL",60.7,11.6,2.3,3.7,2.1,1.2,0.4,0.4,'
    '2.3,0.4,0.3,0.3,0.2,0.3,0.2,0.2,0.4,13.1,0.393',
    '2024,8440,1011,"Bullock County, AL",5.7,2.3,0.3,86.5,0.2,0.3,0.1,0.1,0.5,'
    '0.1,0.1,0.1,0.1,0.1,0.1,0.1,0.1,3.2,0.103',
]

REAL = "\n".join([REAL_HEADER] + REAL_ROWS)


def edit(row: str, column: str, value: str) -> str:
    """Replace one field of a real row, by column name."""
    names = REAL_HEADER.split(",")
    cells = next(iter(__import__("csv").reader([row])))
    cells[names.index(column)] = value
    return ",".join(f'"{c}"' if "," in c else c for c in cells)


def fips_at(i: int) -> str:
    """A plausible county FIPS, unpadded as PRRI writes them."""
    return f"{i // 100 + 1:d}{i % 100 + 1:03d}"


def wide(rows: int) -> str:
    """A table in the real shape, with invented numbers. Sums to 100.2 like
    Autauga does, so the sum checks see something realistic."""
    body = []
    for i in range(rows):
        shares = REAL_ROWS[0].split(",")[-19:]        # 18 groups + diversity
        body.append(",".join(["2024", "40000", fips_at(i), f"County {i}"] + shares))
    return "\n".join([REAL_HEADER] + body)


def nodes_for(rows: int) -> dict[str, dict[str, float]]:
    """{FIPS: {religion node: pct}} straight from the real composition."""
    counties, _ = read_table(wide(rows), chart="d76SP")
    return collapse(counties)


def universe(n: int, *, names: dict[str, str] | None = None,
             population: int = 60_000) -> list[dict]:
    """The county universe us_acs.py writes, reduced to what the join uses."""
    names = names or {}
    out = []
    for i in range(n):
        fips = fips_at(i).zfill(5)
        out.append({
            "id": f"USA-{fips}", "name": names.get(fips, f"County {i}"),
            "parent": f"USA-{fips[:2]}",
            "codes": {"geoid": fips, "fips_state": fips[:2],
                      "fips_county": fips[2:]},
            "population": {"value": population},
        })
    return out


class RealTable(unittest.TestCase):
    """The reader against the bytes PRRI actually serves."""

    def setUp(self):
        self.counties, self.year = read_table(REAL, chart="d76SP")

    def test_reads_every_row(self):
        self.assertEqual(len(self.counties), len(REAL_ROWS))

    def test_takes_the_year_from_the_data_not_the_title(self):
        """The article is titled 2023; the table says 2024."""
        self.assertEqual(self.year, 2024)

    def test_pads_the_fips(self):
        """PRRI writes Autauga as 1001. Joined unpadded against a 5-digit key,
        every state from 01 to 09 would silently match nothing."""
        self.assertIn("01001", self.counties)
        self.assertNotIn("1001", self.counties)

    def test_carries_the_name_and_population(self):
        autauga = self.counties["01001"]
        self.assertEqual(autauga["name"], "Autauga County, AL")
        self.assertEqual(autauga["population"], 44335)

    def test_reads_all_eighteen_groups_from_one_chart(self):
        """The chart titled 'White Evangelical Protestant' carries the lot."""
        self.assertEqual(len(self.counties["01001"]["shares"]), 18)
        self.assertEqual(set(self.counties["01001"]["shares"]), set(COLUMNS.values()))

    def test_shares_sum_to_about_100(self):
        self.assertAlmostEqual(
            sum(self.counties["01001"]["shares"].values()), 100.2, places=6)
        self.assertAlmostEqual(
            sum(self.counties["01011"]["shares"].values()), 100.0, places=6)

    def test_the_diversity_index_is_not_a_group(self):
        """It is a 0-1 score and it sits in every CSV as a column as well as
        being a chart of its own. Read as a nineteenth share it would add half
        a point to every county."""
        self.assertIn("mL9BH", EXCLUDED)
        self.assertNotIn("mL9BH", CHARTS)
        self.assertIn("diversity_index", STRUCTURAL)
        self.assertNotIn("diversity_index", COLUMNS)
        for row in self.counties.values():
            self.assertNotIn(0.496, list(row["shares"].values()))

    def test_values_are_percentages_not_proportions(self):
        self.assertEqual(self.counties["01001"]["shares"]
                         ["White Evangelical Protestant"], 37.9)


class KeyColumn(unittest.TestCase):
    """Which column is the key, and the one that nearly passes for it."""

    def test_the_fips_column_is_a_key(self):
        ok, _ = looks_like_key(["1001", "1003", "1005"])
        self.assertTrue(ok)

    def test_the_year_column_is_not(self):
        """2024 is four digits and 20 is a valid state prefix, so the only
        thing separating it from a FIPS code is that it never varies."""
        ok, why = looks_like_key(["2024"] * 6)
        self.assertFalse(ok)
        self.assertIn("constant", why)

    def test_a_repeated_code_is_not_a_key(self):
        ok, why = looks_like_key(["1001", "1003", "1003"])
        self.assertFalse(ok)
        self.assertIn("distinct", why)

    def test_a_population_column_is_not_a_key(self):
        """Populations stray outside the 01-56 state prefixes almost at once."""
        ok, _ = looks_like_key([str(90000 + i) for i in range(20)])
        self.assertFalse(ok)

    def test_refuses_when_the_named_key_stops_being_one(self):
        rows = [edit(r, "fipsstcnty", "1001") for r in REAL_ROWS]
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([REAL_HEADER] + rows), chart="d76SP")
        self.assertIn("not a county key", str(cm.exception))


class HeaderChanges(unittest.TestCase):
    """A column that moves, vanishes or appears must stop the run."""

    def test_refuses_a_renamed_column(self):
        """Renaming is the dangerous one: the run would otherwise continue with
        one religion's figures read as another's."""
        header = REAL_HEADER.replace("hispanic_catholic", "latino_catholic")
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([header] + REAL_ROWS), chart="d76SP")
        self.assertIn("hispanic_catholic", str(cm.exception))

    def test_refuses_an_unknown_new_column(self):
        header = REAL_HEADER + ",neo_druid"
        rows = [r + ",0.1" for r in REAL_ROWS]
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([header] + rows), chart="d76SP")
        self.assertIn("neo_druid", str(cm.exception))

    def test_column_order_does_not_matter(self):
        """Columns are found by name, so a reordered table reads the same."""
        import csv as _csv
        import io as _io
        names = REAL_HEADER.split(",")
        order = list(reversed(range(len(names))))
        out = [",".join(names[i] for i in order)]
        for row in REAL_ROWS:
            cells = next(iter(_csv.reader(_io.StringIO(row))))
            out.append(",".join(f'"{cells[i]}"' if "," in cells[i] else cells[i]
                                for i in order))
        counties, _ = read_table("\n".join(out), chart="d76SP")
        self.assertEqual(counties["01001"]["shares"]
                         ["White Evangelical Protestant"], 37.9)

    def test_covers_every_column_in_the_real_header(self):
        self.assertEqual(set(REAL_HEADER.split(",")), set(COLUMNS) | STRUCTURAL)


class BadCells(unittest.TestCase):

    def test_refuses_mixed_years(self):
        rows = list(REAL_ROWS)
        rows[0] = edit(rows[0], "year", "2023")
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([REAL_HEADER] + rows), chart="d76SP")
        self.assertIn("mixes data years", str(cm.exception))

    def test_refuses_a_censored_value(self):
        """PRRI censors nothing today. If a revision does, reading '<0.5' as
        zero understates the group and reading it as 0.5 invents a number."""
        rows = list(REAL_ROWS)
        rows[0] = edit(rows[0], "muslim", "<0.5")
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([REAL_HEADER] + rows), chart="d76SP")
        self.assertIn("censors 1 values", str(cm.exception))

    def test_refuses_a_blank_share(self):
        """A blank is not a zero and must not be read as one."""
        rows = list(REAL_ROWS)
        rows[0] = edit(rows[0], "jewish", "")
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([REAL_HEADER] + rows), chart="d76SP")
        self.assertIn("no number", str(cm.exception))

    def test_refuses_a_duplicated_county(self):
        """Caught by the key check rather than row by row -- a key that repeats
        is not a key -- so the message names the repeated code."""
        with self.assertRaises(SystemExit) as cm:
            read_table("\n".join([REAL_HEADER] + REAL_ROWS + [REAL_ROWS[0]]),
                       chart="d76SP")
        self.assertIn("repeated twice or more: ['1001']", str(cm.exception))

    def test_censored_detects_both_bounds(self):
        self.assertTrue(censored("<0.5"))
        self.assertTrue(censored(" > 99"))
        self.assertFalse(censored("0.5"))
        self.assertFalse(censored(""))

    def test_detects_a_tab_separated_table(self):
        """Read with the comma reader, a TSV is one fused column and the
        refusal that follows blames the wrong thing."""
        tsv = REAL.replace('"Autauga County, AL"', "Autauga County AL")
        tsv = "\n".join(line.replace(",", "\t") for line in tsv.splitlines())
        _, delimiter = split_rows(tsv)
        self.assertEqual(delimiter, "\t")


class CrossCheck(unittest.TestCase):
    """Every chart is supposed to serve the same table. Proved, not assumed."""

    def setUp(self):
        self.primary, _ = read_table(REAL, chart="d76SP")

    def test_an_identical_table_agrees(self):
        other, _ = read_table(REAL, chart="CLuyf")
        cross_check(self.primary, other, chart="CLuyf")

    def test_refuses_a_chart_with_different_numbers(self):
        rows = list(REAL_ROWS)
        rows[0] = edit(rows[0], "muslim", "9.9")
        other, _ = read_table("\n".join([REAL_HEADER] + rows), chart="CLuyf")
        with self.assertRaises(SystemExit) as cm:
            cross_check(self.primary, other, chart="CLuyf")
        self.assertIn("Muslim", str(cm.exception))

    def test_refuses_a_chart_with_different_counties(self):
        other, _ = read_table("\n".join([REAL_HEADER] + REAL_ROWS[:-1]),
                              chart="CLuyf")
        with self.assertRaises(SystemExit) as cm:
            cross_check(self.primary, other, chart="CLuyf")
        self.assertIn("different counties", str(cm.exception))


class Categories(unittest.TestCase):
    """The race-crossed categories, and how they collapse."""

    def setUp(self):
        self.counties, _ = read_table(REAL, chart="d76SP")
        self.nodes = collapse(self.counties)

    def test_every_column_has_a_decided_node(self):
        self.assertEqual(sorted(COLUMNS.values()), sorted(COLLAPSE))

    def test_protestant_variants_sum_into_one_node(self):
        # 37.9 evangelical + 15.6 mainline + 13.9 Black + 0.7 Hispanic
        # + 3.6 other Protestant of colour
        self.assertAlmostEqual(self.nodes["01001"]["Protestantism"], 71.7, places=6)
        # 3.0 white + 0.5 Hispanic + 0.6 other Catholic of colour
        self.assertAlmostEqual(self.nodes["01001"]["Catholicism"], 4.1, places=6)

    def test_a_majority_black_protestant_county_reads_as_protestant(self):
        """Bullock County is 86.5% Black Protestant. Race is dropped, so what
        the map shows is a 95.3% Protestant county."""
        self.assertAlmostEqual(self.nodes["01011"]["Protestantism"], 95.3, places=6)

    def test_race_detail_is_gone_not_refiled(self):
        """No node carries a racial term. Keeping 'White Evangelical
        Protestant' as a group would put race in the religion tree, where a
        reader filtering Protestantism misses most American Protestants."""
        for node in self.nodes["01001"]:
            for word in ("White", "Black", "Hispanic", "of Color", "white"):
                self.assertNotIn(word, node)

    def test_unaffiliated_becomes_no_religion(self):
        self.assertAlmostEqual(self.nodes["01001"]["No religion"], 21.1, places=6)

    def test_unitarians_land_in_other_religions(self):
        # 0.3 Unitarian Universalist + 0.5 other non-Christian
        self.assertAlmostEqual(self.nodes["01001"]["Other religions"], 0.8, places=6)

    def test_refuses_a_category_it_has_not_decided_about(self):
        counties = {"01001": {"name": "x", "population": 1.0,
                              "shares": {"Neo-Druid": 1.0}}}
        with self.assertRaises(SystemExit) as cm:
            collapse(counties)
        self.assertIn("Neo-Druid", str(cm.exception))


class Sums(unittest.TestCase):

    def test_accepts_the_real_composition(self):
        check_sums(nodes_for(50))

    def test_refuses_one_county_far_from_100(self):
        nodes = nodes_for(50)
        nodes["01001"]["Protestantism"] += 40.0
        with self.assertRaises(SystemExit) as cm:
            check_sums(nodes)
        self.assertIn("01001", str(cm.exception))

    def test_refuses_a_systematically_missing_column(self):
        """The per-county band is loose enough to miss a small group going
        astray; the median is not. Losing the Jewish column leaves every
        county at 99.8, which the median catches at 0.2... so this drops
        Catholicism, 4.1 points, which stays inside the per-county band."""
        nodes = nodes_for(50)
        for groups in nodes.values():
            groups.pop("Catholicism")
        with self.assertRaises(SystemExit) as cm:
            check_sums(nodes)
        self.assertIn("systematic", str(cm.exception))

    def test_a_proportion_table_fails_the_sum_check(self):
        """If a revision stored 0.379 rather than 37.9 every column test still
        passes. The sums are what notice, so this checks they do."""
        nodes = {f: {k: v / 100 for k, v in g.items()}
                 for f, g in nodes_for(50).items()}
        with self.assertRaises(SystemExit):
            check_sums(nodes)


class Collapse(unittest.TestCase):
    """The exact check on the mapping, which replaced a fuzzy numeric one.

    PRRI's 66% Christian includes Latter-day Saints, Jehovah's Witnesses and
    Orthodox Christians -- footnote [1] puts all three inside the 41% who are
    white Christians and footnote [2] inside the 25% who are Christians of
    colour, and 41 + 25 = 66. This map's Christianity subtree includes them
    too, so the two definitions agree and the roll-up compares like with like.
    """

    def test_the_shipped_mapping_agrees_with_prri(self):
        check_collapse()

    def test_every_christian_category_is_one_of_prris(self):
        self.assertTrue(CHRISTIAN_CATEGORIES <= set(COLLAPSE))

    def test_prri_counts_the_three_small_churches_as_christian(self):
        """The thing that looks like a discrepancy from a distance."""
        for category in ("Latter-day Saint (Mormon)", "Jehovah's Witness",
                         "Orthodox Christian"):
            self.assertIn(category, CHRISTIAN_CATEGORIES)
            self.assertIn(COLLAPSE[category], CHRISTIAN)

    def test_refuses_a_christian_category_filed_outside_christianity(self):
        """Catches the one-point mistakes a published-figure tolerance never
        could: moving Orthodox Christians out shifts the national total by
        0.6 points, far inside any band that would tolerate vintage drift."""
        with mock.patch.dict(us_prri.COLLAPSE,
                             {"Orthodox Christian": "Other religions"}):
            with self.assertRaises(SystemExit) as cm:
                check_collapse()
        self.assertIn("Orthodox Christian", str(cm.exception))

    def test_refuses_a_non_christian_category_filed_inside_christianity(self):
        with mock.patch.dict(us_prri.COLLAPSE, {"Muslim": "Protestantism"}):
            with self.assertRaises(SystemExit) as cm:
                check_collapse()
        self.assertIn("overstate", str(cm.exception))

    def test_refuses_a_christian_node_no_category_can_fill(self):
        with mock.patch.object(us_prri, "CHRISTIAN",
                               us_prri.CHRISTIAN | {"Coptic Orthodoxy"}):
            with self.assertRaises(SystemExit) as cm:
                check_collapse()
        self.assertIn("Coptic Orthodoxy", str(cm.exception))


class National(unittest.TestCase):
    """The roll-up is reported against PRRI's figures, and gated only on bands
    no difference of vintage could reach. See check_national for why."""

    def setUp(self):
        self.shares = {"01001": {"White Evangelical Protestant": 13.0,
                                 "White Catholic": 22.0,
                                 "Religiously Unaffiliated": 28.0,
                                 "Muslim": 1.0}}
        self.nodes = {
            "01001": {"Protestantism": 40.0, "Catholicism": 22.0,
                      "Latter-day Saints": 1.5, "Orthodoxy": 0.5,
                      "Jehovah's Witnesses": 2.0, "Judaism": 2.0,
                      "Islam": 1.0, "Buddhism": 1.0, "Hinduism": 1.0,
                      "Other religions": 1.0, "No religion": 28.0},
        }
        self.pops = {"01001": 44335.0}

    def test_accepts_a_rollup_matching_the_published_figures(self):
        check_national(self.shares, self.nodes, self.pops)

    def test_accepts_the_gap_the_real_data_shows(self):
        """The first real run put Christians at 70.1% against a published 66%,
        with Catholicism exact and the deviation a transfer between
        Protestantism and the unaffiliated. That is vintage, not mis-filing,
        and it must not stop the run."""
        nodes = {"01001": {"Protestantism": 44.7, "Catholicism": 22.0,
                           "No religion": 23.1, "Other religions": 1.8,
                           "Judaism": 1.8, "Latter-day Saints": 1.8,
                           "Buddhism": 1.0, "Islam": 1.0,
                           "Jehovah's Witnesses": 0.9, "Hinduism": 0.8,
                           "Orthodoxy": 0.6}}
        check_national(self.shares, nodes, self.pops)

    def test_refuses_a_gross_mis_collapse(self):
        """Filing Catholicism as a non-Christian religion puts the
        non-Christian share at 28% and Christians at 48%; both are far past
        anything vintage explains."""
        nodes = {f: dict(g) for f, g in self.nodes.items()}
        for groups in nodes.values():
            groups["Islam"] = groups.pop("Catholicism") + groups["Islam"]
        with self.assertRaises(SystemExit) as cm:
            check_national(self.shares, nodes, self.pops)
        self.assertIn("sanity band", str(cm.exception))

    def test_refuses_when_no_county_has_a_population(self):
        with self.assertRaises(SystemExit) as cm:
            check_national(self.shares, self.nodes, {})
        self.assertIn("cannot be weighted", str(cm.exception))

    def test_published_categories_are_all_real_categories(self):
        self.assertTrue(set(PUBLISHED_CATEGORY) <= set(COLLAPSE))


class Population(unittest.TestCase):
    """PRRI's denominator is adults; the ACS count is residents."""

    def test_accepts_an_adult_sized_denominator(self):
        counties, _ = read_table(REAL, chart="d76SP")
        # Autauga: 44,335 adults against roughly 59,800 residents.
        check_population(counties, universe(6, population=59_800))

    def test_refuses_a_denominator_that_is_not_a_subset(self):
        """If Population were residents, or something else entirely, weighting
        the national roll-up by it would be wrong."""
        counties, _ = read_table(REAL, chart="d76SP")
        with self.assertRaises(SystemExit) as cm:
            check_population(counties, universe(6, population=10_000))
        self.assertIn("not the adult denominator", str(cm.exception))


class Join(unittest.TestCase):
    """FIPS is the key. The name is only ever a check on it."""

    def setUp(self):
        self.n = 3_100
        self.nodes = nodes_for(self.n)

    def test_builds_a_record_per_county(self):
        got = build(self.nodes, universe(self.n), year=2024)
        self.assertEqual(len(got), self.n)
        first = got[0]
        self.assertEqual(first["id"], "USA-01001")
        self.assertEqual(first["level"], "admin2")
        self.assertEqual(first["parent"], "USA-01")
        self.assertEqual(first["country"], "USA")
        self.assertEqual(first["codes"]["geoid"], "01001")
        self.assertEqual(first["religion_year"], 2024)
        self.assertEqual(first["religion_basis"], "self-identification")
        self.assertEqual(first["sources"][0]["field"], "religion")

    def test_religion_rows_are_sorted_and_sum_to_the_table(self):
        got = build(self.nodes, universe(self.n), year=2024)
        rows = got[0]["religion"]
        self.assertEqual([r["pct"] for r in rows],
                         sorted((r["pct"] for r in rows), reverse=True))
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.2, places=1)
        self.assertEqual(rows[0]["group"], "Protestantism")

    def test_takes_the_name_from_the_map_not_from_prri(self):
        got = build(self.nodes, universe(self.n, names={"01001": "Autauga County, Alabama"}),
                    year=2024)
        self.assertEqual(got[0]["name"], "Autauga County, Alabama")

    def test_accepts_prris_state_abbreviation(self):
        """PRRI writes 'Autauga County, AL' and the map 'Autauga County,
        Alabama'. The same place, and the check must not say otherwise."""
        got = build(self.nodes,
                    universe(self.n, names={"01001": "Autauga County, Alabama"}),
                    year=2024, prri_names={"01001": "Autauga County, AL"})
        self.assertEqual(len(got), self.n)

    def test_refuses_a_fips_naming_a_different_county(self):
        """A FIPS whose name moved is usually a FIPS that was reassigned --
        Connecticut's 2022 planning regions are the live case. Joining it
        anyway puts one county's religion on another county's shape."""
        with self.assertRaises(SystemExit) as cm:
            build(self.nodes,
                  universe(self.n, names={"01001": "Autauga County, Alabama"}),
                  year=2024, prri_names={"01001": "Litchfield County, CT"})
        self.assertIn("different county", str(cm.exception))

    def test_refuses_when_too_little_joins(self):
        """Part-matching two county vintages is worse than refusing both."""
        with self.assertRaises(SystemExit) as cm:
            build(self.nodes, universe(2_800), year=2024)
        self.assertIn("different county vintages", str(cm.exception))

    def test_refuses_an_implausible_county_count(self):
        with self.assertRaises(SystemExit) as cm:
            build(nodes_for(100), universe(100), year=2024)
        self.assertIn("3,143", str(cm.exception))

    def test_unmatched_counties_are_dropped_not_forced(self):
        """A PRRI county with no shape is a visible gap, not a guess."""
        got = build(self.nodes, universe(self.n)[:-20], year=2024)
        self.assertEqual(len(got), self.n - 20)


class Probe(unittest.TestCase):
    """The read-only path that corrected the column rules against the file."""

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
        self.assertEqual(seen, list(CHARTS))
        self.assertEqual(code, 1)

    def test_refuses_a_chart_id_it_does_not_know(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main(["--probe", "--chart", "NOPE"], lambda chart, rows: None)
        self.assertIn("no such chart", str(cm.exception))

    def test_arguments_are_xargs_safe(self):
        """The runner passes these through
        ``printf '%s' "$ADAPTER" | xargs python3 -m``, which splits on
        whitespace and strips quotes. Any flag or default carrying a space or a
        quote would arrive as two arguments."""
        parser = us_prri.build_parser()
        for action in parser._actions:
            for flag in action.option_strings:
                self.assertNotRegex(flag, r"[\s\"']")
            if isinstance(action.default, str):
                self.assertNotRegex(action.default, r"[\s\"']")


class Normalise(unittest.TestCase):

    def test_strips_type_words_and_state(self):
        self.assertEqual(normalise("Autauga County, AL"), "autauga")
        self.assertEqual(normalise("Autauga County, Alabama"), "autauga")
        self.assertEqual(normalise("Orleans Parish, LA"), "orleans")
        self.assertEqual(normalise("Doña Ana County"), normalise("Dona Ana"))

    def test_keeps_genuinely_different_names_apart(self):
        self.assertNotEqual(normalise("Litchfield"), normalise("Autauga"))


if __name__ == "__main__":
    unittest.main()


class CountiesTheUniverseDoesNotCarry(unittest.TestCase):
    """Connecticut, where the survey and the shapes agree and the list between
    them does not.

    The ACS county list moved to Connecticut's nine planning regions when the
    state replaced its counties in 2022. The boundary file still draws the
    eight old counties and PRRI still reports them, so joining through the ACS
    list dropped 3.6 million people -- not because anything disagreed about
    the ground, but because the intermediary had moved on.
    """

    def setUp(self):
        self.n = 3_100
        self.nodes = nodes_for(self.n)
        # The condition under test is a universe that does NOT list these,
        # which is exactly what the ACS list does for Connecticut. The generic
        # fixture invents a county at every FIPS, so the declared ones are
        # taken back out or the code path never runs.
        self.universe = [row for row in universe(self.n)
                         if (row.get("codes") or {}).get("geoid")
                         not in us_prri.OUTSIDE_UNIVERSE]

    def test_a_declared_county_is_emitted_against_its_shape(self):
        nodes = dict(self.nodes)
        nodes["09001"] = {"Protestantism": 40.0, "Catholicism": 30.0,
                          "No religion": 30.0}
        got = build(nodes, self.universe, year=2024,
                    prri_names={"09001": "Fairfield County, CT"})
        fairfield = [r for r in got if r["id"] == "USA-09001"]
        self.assertEqual(len(fairfield), 1)
        self.assertEqual(fairfield[0]["name"], "Fairfield")
        # The state has to travel with it: the build matches a second-level
        # name inside its parent, and "Middlesex" is a county in Connecticut
        # and another in Massachusetts.
        self.assertEqual(fairfield[0]["parent_name"], "Connecticut")
        self.assertEqual(fairfield[0]["codes"]["geoid"], "09001")

    def test_the_name_check_is_not_run_against_a_declared_shape(self):
        """PRRI writes "Fairfield County, CT"; the boundary file writes
        "Fairfield". They are the same county, and the declaration is what
        says so -- so the check that refuses a FIPS whose two names disagree
        must not fire on one it was told about."""
        nodes = dict(self.nodes)
        nodes["09005"] = {"Protestantism": 100.0}
        got = build(nodes, self.universe, year=2024,
                    prri_names={"09005": "Litchfield County, CT"})
        self.assertTrue(any(r["id"] == "USA-09005" for r in got))

    def test_every_declared_county_names_a_shape_and_a_state(self):
        for fips, (shape, state) in us_prri.OUTSIDE_UNIVERSE.items():
            self.assertRegex(fips, r"^\d{5}$")
            self.assertTrue(shape and state, fips)

    def test_an_undeclared_missing_county_is_still_left_out(self):
        """The declaration is the whole permission; nothing else gets through."""
        nodes = dict(self.nodes)
        nodes["99999"] = {"Protestantism": 100.0}
        got = build(nodes, self.universe, year=2024)
        self.assertFalse(any(r["id"] == "USA-99999" for r in got))


class StatesAndTheNation(unittest.TestCase):
    """A source that fills one level and leaves the others makes the map
    contradict itself.

    Before this, the United States read as PRRI 2024 at county level, the 2020
    Religion Census at state level and a 2014 Factbook estimate nationally --
    three answers to one question, the two coarser ones from the source that
    had just been superseded. Zooming out changed the figures and nothing said
    why.
    """

    def setUp(self):
        self.n = 3_100
        self.nodes = nodes_for(self.n)
        self.universe = universe(self.n)
        self.pops = {fips: 1_000.0 for fips in self.nodes}

    def wider(self, **kw):
        return us_prri.aggregate(self.nodes, self.pops, self.universe,
                                 year=2024, **kw)

    def test_states_come_back_and_a_nation_deliberately_does_not(self):
        got = self.wider()
        self.assertTrue(got)
        self.assertEqual({r["level"] for r in got}, {"admin1"})
        self.assertTrue(all(r["religion_year"] == 2024 for r in got))

    def test_a_state_is_the_weighted_mean_of_its_counties(self):
        """Equal weights, so the state is the plain mean -- and the check is
        that it is the mean of *its own* counties and not of all of them."""
        nodes = {"01001": {"Protestantism": 80.0, "No religion": 20.0},
                 "01003": {"Protestantism": 60.0, "No religion": 40.0},
                 "02001": {"Protestantism": 10.0, "No religion": 90.0}}
        pops = {"01001": 100.0, "01003": 100.0, "02001": 100.0}
        got = us_prri.aggregate(nodes, pops, self.universe, year=2024)
        alabama = next(r for r in got if r["id"] == "USA-01")
        shares = {g["group"]: g["pct"] for g in alabama["religion"]}
        self.assertEqual(shares["Protestantism"], 70.0)
        self.assertEqual(shares["No religion"], 30.0)

    def test_population_weights_are_used_not_a_plain_average(self):
        nodes = {"01001": {"Protestantism": 100.0},
                 "01003": {"No religion": 100.0}}
        pops = {"01001": 900.0, "01003": 100.0}
        got = us_prri.aggregate(nodes, pops, self.universe, year=2024)
        alabama = next(r for r in got if r["id"] == "USA-01")
        shares = {g["group"]: g["pct"] for g in alabama["religion"]}
        self.assertEqual(shares["Protestantism"], 90.0)

    def test_counties_with_no_population_between_them_refuse(self):
        """Weighting by nothing would produce a figure with no basis."""
        nodes = {"01001": {"Protestantism": 100.0}}
        with self.assertRaises(SystemExit) as cm:
            us_prri.aggregate(nodes, {"01001": 0.0}, self.universe, year=2024)
        self.assertIn("no population", str(cm.exception))

    def test_the_note_says_the_figure_was_summed(self):
        note = self.wider()[0]["religion_note"]
        self.assertIn("Summed from the", note)
        self.assertIn("weighted by", note)


class TheNationIsNotThisAdaptersToFile(unittest.TestCase):
    """PRRI surveyed the 50 states and the District of Columbia.

    It asked nobody in Puerto Rico, Guam, the U.S. Virgin Islands, American
    Samoa or the Northern Mariana Islands, so a record filed as "United States"
    would state a figure for 3.6 million people who were never in the sample,
    and the record itself would have no way to say so. The build sums the
    country from its first-level divisions instead, which reaches the same
    arithmetic and can name the five that are outside it.

    What stays here is the number, computed for the fetch log: it is what a
    reader checks against PRRI's own national release.
    """

    def setUp(self):
        self.universe = universe(3_100)

    def test_no_record_claims_to_be_the_country(self):
        got = us_prri.aggregate(nodes_for(3_100),
                                {f: 1_000.0 for f in nodes_for(3_100)},
                                self.universe, year=2024)
        self.assertFalse([r for r in got if r["level"] == "admin0"])
        self.assertFalse([r for r in got if r["id"] == "USA"])

    def test_the_figure_is_every_county_not_every_state_averaged(self):
        """Averaging states would give Wyoming the weight of California."""
        nodes = {"01001": {"Protestantism": 100.0},
                 "02001": {"No religion": 100.0}}
        pops = {"01001": 9_000.0, "02001": 1_000.0}
        shares = {g["group"]: g["pct"]
                  for g in us_prri.nationally(nodes, pops)}
        self.assertEqual(shares["Protestantism"], 90.0)

    def test_it_agrees_with_summing_the_states_it_does_write(self):
        # The build's country roll-up weights the states by the denominator
        # each one's percentages were taken against, which is why the state
        # rows carry counts. Same numbers, other order.
        nodes = {"01001": {"Protestantism": 100.0},
                 "01003": {"No religion": 100.0},
                 "02001": {"No religion": 100.0}}
        pops = {"01001": 6_000.0, "01003": 1_000.0, "02001": 3_000.0}
        states = us_prri.aggregate(nodes, pops, self.universe, year=2024)
        summed: dict[str, float] = {}
        for state in states:
            for row in state["religion"]:
                summed[row["group"]] = summed.get(row["group"], 0) + row["count"]
        base = sum(summed.values())
        direct = {g["group"]: g["pct"] for g in us_prri.nationally(nodes, pops)}
        for group, count in summed.items():
            self.assertAlmostEqual(100 * count / base, direct[group], places=1)
        self.assertEqual(base, 10_000)

    def test_counts_are_prris_adult_base_not_the_states_population(self):
        nodes = {"01001": {"Protestantism": 75.0, "No religion": 25.0}}
        states = us_prri.aggregate(nodes, {"01001": 4_000.0},
                                   self.universe, year=2024)
        counts = {g["group"]: g["count"] for g in states[0]["religion"]}
        self.assertEqual(counts, {"Protestantism": 3_000, "No religion": 1_000})
