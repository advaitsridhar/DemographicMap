"""The group tree: what it promises, and what the shipped index must carry.

Three claims are load-bearing once a map can be coloured by a family rather
than by a label, and each is easy to break by editing a table:

* a group's share is the sum of its own rows and its descendants', counted
  once each;
* every canonical name reaches a top-level family, with no cycle and no
  orphan pointing at a name that does not exist;
* the index the frontend reads says, for each group, both what it covers on
  its own and what it covers with its children, because the picker shows the
  second and the record shows the first.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import canonical_groups as cg  # noqa: E402

FIELDS = ("religion", "language", "ethnicity")


class TheTreeIsWellFormed(unittest.TestCase):
    def test_no_group_is_its_own_ancestor(self):
        for field in FIELDS:
            for name in cg.PARENT.get(field, {}):
                trail = cg.ancestry(field, name)
                self.assertEqual(len(trail), len(set(trail)),
                                 f"{field}: {name} loops through {trail}")

    def test_every_parent_is_reachable_as_a_group(self):
        """A parent must be a name the tables can produce, or it is a dead end.

        Either it is a canonical name in the label table, or it is a pure
        grouping node that exists only to hold children -- "Germanic
        languages" is one, since no census writes it. What it may not be is a
        typo: "Cristianity" would silently give its children no family.
        """
        import group_tree
        for field in FIELDS:
            table = cg.TABLES[field]
            kids = cg.children(field)
            placed = group_tree.parents(field)
            for child, parent in list(cg.PARENT.get(field, {}).items()) + \
                                 list(placed.items()):
                self.assertTrue(
                    parent in table or parent in kids or parent in placed
                    or parent in group_tree.tier1_names(field),
                    f"{field}: {child} points at unknown {parent!r}")

    def test_every_top_grouping_has_a_colour(self):
        """The map takes its hue from the nearest coloured ancestor, so a
        tier-1 node without one leaves its whole subtree grey."""
        import group_tree
        for field in FIELDS:
            for name in group_tree.tier1_names(field):
                self.assertIsNotNone(group_tree.hue(field, name),
                                     f"{field}: {name} has no colour")

    def test_every_family_has_a_colour(self):
        """And a tier-2 node without one takes its ancestry's, which would
        make every family in that band the same shade."""
        import group_tree
        for field in FIELDS:
            for name, parent in group_tree.parents(field).items():
                if parent not in group_tree.tier1_names(field):
                    continue
                self.assertIsNotNone(group_tree.hue(field, name),
                                     f"{field}: {name} has no colour")

    def test_a_child_is_never_also_its_parents_label(self):
        """The same string may not be both a group and one of its parent's
        labels, which would count it at two levels of one record."""
        for field in FIELDS:
            table = cg.lookup(field)
            for child, parent in cg.PARENT.get(field, {}).items():
                self.assertNotEqual(table.get(cg.key(child)), parent,
                                    f"{field}: {child} is also a label of {parent}")


class RollingUp(unittest.TestCase):
    def test_a_share_counts_each_row_once_at_every_level(self):
        counts = cg.canonicalise(
            [{"group": "Roman Catholic", "pct": 60.0},
             {"group": "Lutheran", "pct": 10.0},
             {"group": "Sunni", "pct": 5.0},
             {"group": "Shia", "pct": 2.0}], "religion")
        self.assertEqual(cg.share_of(counts, "religion", "Catholicism"), 60.0)
        self.assertEqual(cg.share_of(counts, "religion", "Protestantism"), 10.0)
        self.assertEqual(cg.share_of(counts, "religion", "Christianity"), 70.0)
        self.assertEqual(cg.share_of(counts, "religion", "Islam"), 7.0)
        # And the whole thing still adds to what was published.
        rolled = cg.roll_up(counts, "religion")
        self.assertEqual(rolled["Christianity"] + rolled["Islam"], 77.0)

    def test_a_group_outside_the_composition_is_zero_not_missing(self):
        counts = cg.canonicalise([{"group": "Hindu", "pct": 80.0}], "religion")
        self.assertEqual(cg.share_of(counts, "religion", "Christianity"), 0.0)

    def test_an_unmapped_label_is_its_own_family(self):
        # Nothing is lost by being absent from the tables: an unlisted group
        # is a top-level group of one.
        counts = cg.canonicalise([{"group": "Squirrel Fanciers", "pct": 3.2}],
                                 "religion")
        self.assertEqual(cg.family("religion", "Squirrel Fanciers"),
                         "Squirrel Fanciers")
        self.assertEqual(
            cg.share_of(counts, "religion", "Squirrel Fanciers"), 3.2)


class TheShippedIndex(unittest.TestCase):
    """site/data/groups.json is the only thing the frontend reads."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / "site" / "data" / "groups.json"
        if not path.exists():
            raise unittest.SkipTest("site/data has not been built")
        cls.index = json.loads(path.read_text())

    def entries(self, field):
        return {g["name"]: g for g in self.index[field]["groups"]}

    def test_every_parent_named_is_present_in_the_index(self):
        for field in FIELDS:
            groups = self.entries(field)
            for name, group in groups.items():
                if group["parent"] is not None:
                    self.assertIn(group["parent"], groups,
                                  f"{field}: {name}'s parent is not listed")

    def test_children_and_parents_agree(self):
        for field in FIELDS:
            groups = self.entries(field)
            for name, group in groups.items():
                for kid in group["children"]:
                    self.assertEqual(groups[kid]["parent"], name,
                                     f"{field}: {kid} is listed under {name} "
                                     f"but points at {groups[kid]['parent']}")

    def test_a_parent_reaches_at_least_what_its_children_reach(self):
        """The picker's reach figure includes the subtree, so a parent can
        never cover fewer units than a child of it does."""
        for field in FIELDS:
            groups = self.entries(field)
            for name, group in groups.items():
                for kid in group["children"]:
                    self.assertGreaterEqual(
                        group["units"], groups[kid]["units"],
                        f"{field}: {name} covers fewer units than {kid}")

    def test_own_reach_never_exceeds_rolled_up_reach(self):
        for field in FIELDS:
            for name, group in self.entries(field).items():
                self.assertLessEqual(group["own_units"], group["units"],
                                     f"{field}: {name} owns more than it covers")

    def test_christianity_reaches_the_censuses_that_only_say_catholic(self):
        """The case the tree was built for.

        Poland's powiaty say "Roman Catholic" and never "Christian". Before
        the split, Christianity swallowed the label and Catholicism could not
        be asked for at all; the tree has to give both, and Christianity has
        to still cover every unit Catholicism does.
        """
        groups = self.entries("religion")
        self.assertIn("Catholicism", groups)
        self.assertEqual(groups["Catholicism"]["parent"], "Christianity")
        self.assertGreater(groups["Catholicism"]["units"], 5000)
        self.assertGreater(groups["Christianity"]["units"],
                           groups["Christianity"]["own_units"])

    def test_the_families_that_colour_the_map_carry_a_hue(self):
        # The most-populous-group map takes its colour from the group's own
        # entry or its family's, so the groups that actually lead somewhere
        # have to have one.
        for field, expected in (("religion", "Abrahamic religions"),
                                ("language", "Indo-European languages"),
                                ("ethnicity", "African ancestry")):
            groups = self.entries(field)
            self.assertIsNotNone(groups[expected]["hue"],
                                 f"{field}: {expected} has no colour")


if __name__ == "__main__":
    unittest.main()


class TheThreeTiers(unittest.TestCase):
    """Every field is three deep, and the tiers mean the same thing in each."""

    def test_each_field_has_a_small_set_of_top_groupings(self):
        """Tier 1 is a legend on a world map, so it has to be readable.

        Counted over the groups that actually lead somewhere rather than over
        the table: a people nobody else reports is its own tier-1 node and
        costs the legend nothing, because it never leads a unit.
        """
        import group_tree
        for field in FIELDS:
            named = group_tree.tier1_names(field)
            self.assertLessEqual(len(named), 25, f"{field}: {len(named)} tiers")
            self.assertGreaterEqual(len(named), 6, field)

    def test_rolling_to_a_tier_never_goes_past_the_top(self):
        import group_tree
        for field, name in (("religion", "Catholicism"),
                            ("language", "Mandarin"),
                            ("ethnicity", "Zulu")):
            top = group_tree.at_tier(field, name, 1)
            self.assertIn(top, group_tree.tier1_names(field))
            # Asking for a tier deeper than the tree goes gives the leaf, not
            # an error and not a level that does not exist.
            self.assertEqual(group_tree.at_tier(field, name, 9), name)

    def test_a_census_category_is_not_a_parent_of_a_people(self):
        """The rule the ethnicity tree is built on.

        "Black or African American" and Bantu peoples are siblings under
        African ancestry. If a census category ever became a people's parent,
        the map would assert a mapping no census publishes.
        """
        import group_tree
        categories = group_tree.census_categories()
        for child, parent in group_tree.parents("ethnicity").items():
            if child in group_tree.ETHNIC_PEOPLES:
                self.assertNotIn(parent, categories,
                                 f"{child} is filed under {parent}")

    def test_the_ethnicity_tiers_carry_both_kinds_of_answer(self):
        # The integration claim: an ethnonym and a census race category that
        # mean the same part of the world land in the same tier-1 node.
        import group_tree
        for name in ("Zulu", "Yoruba", "Black or African American (non-Hispanic)",
                     "Nigerian"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "African ancestry"
                             if name != "Nigerian" else "Stated as a nationality",
                             name)
        for name in ("Croatian", "White (non-Hispanic)",
                     "White: English, Welsh, Scottish, Northern Irish or British"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "European ancestry", name)
