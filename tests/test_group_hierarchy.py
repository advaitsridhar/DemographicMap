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


class ReadingANameTheTablesDoNotSpell(unittest.TestCase):
    """The rules that place a label no table lists, and their refusals.

    Every rule here earns its place by what it refuses as much as by what it
    places: a label read wrongly is filed under a heading no census wrote,
    and unlike an unplaced one it never shows up again.
    """

    def test_a_spelling_difference_is_not_a_different_group(self):
        import group_tree
        for field, name, expected in (
                ("language", "Éwé", "Ewe"),
                ("language", "Banda Languages", "Banda"),
                ("language", "Alaba-K’abeena", "Alaba-K'abeena"),
                ("language", "Lushai/Mizo", "Mizo")):
            self.assertEqual(group_tree.parent_of(field, name),
                             group_tree.parent_of(field, expected),
                             f"{name} parts company with {expected}")

    def test_a_compound_lands_where_all_of_its_parts_agree(self):
        import group_tree
        # China's 1.4 billion, written as the people and as the country.
        self.assertEqual(group_tree.parent_of("ethnicity", "Han Chinese"),
                         group_tree.parent_of("ethnicity", "Han"))
        # Neither Amazigh nor Arab, but both are the same ancestry.
        self.assertEqual(
            group_tree.at_tier("ethnicity", "Amazigh and Arab", 1),
            "Middle Eastern and North African ancestry")

    def test_a_semicolon_lists_synonyms_and_not_two_languages(self):
        """ISO 639 names a language and lists its other names after a
        semicolon, and a register that types its code list into a census
        table brings the punctuation with it. Both names are one language,
        so the label belongs where that language belongs -- beside it, not
        under it, which is where reading only the last word had put it.
        """
        import group_tree
        for name, target in (("Catalan; Valencian", "Catalan"),
                             ("Avaric;  Avar;  Avarish", "Avar"),
                             ("Panjabi; Punjabi", "Punjabi"),
                             ("Kalaallisut; Greenlandic", "Greenlandic")):
            self.assertEqual(group_tree.parent_of("language", name),
                             group_tree.parent_of("language", target),
                             f"{name} parts company with {target}")
            self.assertNotEqual(group_tree.parent_of("language", name), target,
                                f"{name} was filed under {target}")

    def test_and_still_joins_two_different_answers(self):
        """The refusal the semicolon rule must not undo: a conjunction is
        not a synonym, and two languages of two families share no node."""
        import group_tree
        for name in ("Spanish and Guarani", "Niuean and English"):
            self.assertIsNone(group_tree.parent_of("language", name), name)

    def test_two_answers_welded_together_are_refused(self):
        """The refusal that keeps the rule honest.

        "European and Mestizo" is one census category covering two
        ancestries that share no node above them. Reading it as either would
        put a real number under a heading nobody published, so it stays
        unplaced and stays visible as unplaced.
        """
        import group_tree
        for name in ("European and Mestizo", "White or Mestizo"):
            self.assertIsNone(group_tree.parent_of("ethnicity", name), name)

    def test_a_bands_remainder_sits_under_the_band(self):
        """"Romance languages, n.i.e." is Romance, not its sibling.

        Read as a sibling, the family it is the leftover of would not count
        it, and Romance would come up short by exactly the rows the census
        could not name.
        """
        import group_tree
        self.assertEqual(
            group_tree.parent_of("language", "Italic (Romance) languages, n.i.e."),
            "Romance languages")
        self.assertEqual(group_tree.parent_of("language", "Turkic languages, n.i.e."),
                         "Turkic languages")

    def test_a_top_grouping_never_acquires_a_parent(self):
        """The invariant the word rules could break.

        "African ancestry" contains the word "African", which is a census
        category *underneath* it. Any rule that reads a name word by word can
        close that loop, and a loop in the tree hangs the first paint, so the
        top of each tree says no before the rules get a turn.
        """
        import group_tree
        for field in FIELDS:
            for name in group_tree.tier1_names(field):
                self.assertIsNone(group_tree.parent_of(field, name),
                                  f"{field}: {name} was given a parent")

    def test_every_label_in_the_shipped_data_terminates(self):
        """No label, however odd, may loop or run away climbing the tree."""
        import group_tree
        path = ROOT / "site" / "data" / "admin0.json"
        if not path.exists():
            raise unittest.SkipTest("site/data has not been built")
        for record in json.loads(path.read_text()):
            for field in FIELDS:
                rows = record.get(field)
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    name = row.get("group")
                    if not name:
                        continue
                    trail = cg.ancestry(field, name)
                    self.assertEqual(len(trail), len(set(trail)),
                                     f"{field}: {name} loops through {trail}")
                    self.assertLess(len(trail), 12, f"{field}: {name} is {trail}")


class TheTailOfNamesTheTablesNowCarry(unittest.TestCase):
    """The blocks a single census publishes, and what stays out of them.

    Each of these is a whole country's list rather than a name, and the
    argument for the block is what is tested: that Nepal's Tarai castes
    speak Indo-Aryan languages, that Kiranti is Tibeto-Burman, that a clan
    name in Lesotho is the clan root with a person prefix on it. The
    refusals beside them are the cases where the same reasoning would have
    to guess, and does not.
    """

    def test_a_national_block_lands_in_one_family(self):
        import group_tree
        cases = (
            # Nepal: the Tarai castes, the Kiranti (Rai) languages of the
            # eastern hills, and the far-western dialects of Nepali named
            # after the district that speaks them.
            ("ethnicity", "Sonar", "Indo-Aryan peoples"),
            ("ethnicity", "Kayastha", "Indo-Aryan peoples"),
            ("ethnicity", "Bantawa", "Himalayan and Tibeto-Burman peoples"),
            ("language", "Chamling", "Tibeto-Burman languages"),
            ("language", "Baitadeli", "Indo-Aryan languages"),
            ("language", "Santhali", "Munda languages"),
            # Russia's smallest counted peoples, by the language each speaks.
            ("language", "Bezhta", "Northeast Caucasian languages"),
            ("language", "Chukchi", "Chukotko-Kamchatkan languages"),
            ("language", "Teleut", "Turkic languages"),
            ("ethnicity", "Mountain Jew", "Jewish"),
            # Timor-Leste's Austronesian languages and its Papuan ones.
            ("language", "Tetun Prasa", "Malayo-Polynesian languages"),
            ("language", "Fataluku", "Papuan languages"),
            # The Congo basin, Zambia and Madagascar.
            ("ethnicity", "Bushoong", "Bantu peoples"),
            ("ethnicity", "Mangbetu", "Central African peoples"),
            ("ethnicity", "Namwanga", "Bantu peoples"),
            ("ethnicity", "Antanosy", "Malagasy peoples"),
            # Scotland writes each census category three ways at once.
            ("ethnicity", "Bangladeshi, Bangladeshi Scottish or Bangladeshi "
                          "British", "Asian (census category)"),
        )
        for field, name, expected in cases:
            self.assertEqual(group_tree.parent_of(field, name), expected, name)

    def test_a_clan_name_is_its_root_with_a_prefix_on_it(self):
        """Lesotho, Botswana, Uganda and Tanzania ask for the clan or the
        person, not the people: one Motaung of the Bataung, one Musoga of
        the Basoga. The roots are in the table and the prefix rule takes
        the marker off, so all three spellings are one group."""
        import group_tree
        for name in ("Motaung", "Mokgalagadi", "Musoga", "Mugishu",
                     "Mzigua", "Mkerewe"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Bantu peoples", name)
        # And where the root is a click-language people, it lands there
        # instead: Mosarwa is one of the Basarwa, and Msandawe one Sandawe.
        for name in ("Mosarwa", "Msandawe"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Khoisan peoples", name)

    def test_the_khoisan_languages_hang_from_nothing_else(self):
        """They are not one family, which is the reason they are a top
        grouping of their own rather than a corner of Niger-Congo."""
        import group_tree
        self.assertEqual(group_tree.parent_of("language", "Khoisan"),
                         "Khoisan languages")
        self.assertEqual(group_tree.at_tier("language", "Sesarwa", 1),
                         "Khoisan languages")
        # Burkina Faso writes "San" for the Samo language, which is Mande.
        # One three-letter string cannot be both, so the tree says neither.
        self.assertIsNone(group_tree.parent_of("language", "San"))

    def test_an_answer_that_names_no_group_is_not_given_one(self):
        """A marker, a count of languages, a ground of discrimination and a
        religion written into the ethnicity question are all answers to
        something other than the question asked. They are kept, and kept
        apart, rather than coloured as a group."""
        import group_tree
        self.assertEqual(
            group_tree.at_tier("language",
                               "some 839 living indigenous languages "
                               "are spoken", 1),
            "Other and unspecified languages")
        for name in ("Related to gender", "Orthodox (written as ethnicity)",
                     "Race not stated", "non-Gambian"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "Other or not stated ancestry", name)
        for name in ("Serbian (written as religion)", "other or none",
                     "Believer, no church"):
            self.assertEqual(group_tree.at_tier("religion", name, 1),
                             "Not stated", name)

    def test_a_church_is_still_a_church(self):
        """The rule above reads "Believer" as someone who names no church,
        and it must not take the churches with it."""
        import group_tree
        for name in ("Believers Church", "Jesus is Alive Community, Inc.",
                     "Filipino Assemblies of the First Born, Incorporated"):
            self.assertEqual(group_tree.at_tier("religion", name, 1),
                             "Abrahamic religions", name)
        self.assertEqual(
            group_tree.parent_of("religion",
                                 "Oblates of Mary Immaculate, Incorporated"),
            "Catholicism")

    def test_the_names_that_stay_unplaced(self):
        """What the tail is still made of, and why each is left alone.

        These are not oversights. A name whose identity is argued over, a
        people two censuses could mean two things by, and a row that is one
        census's tail with no root the references carry are all better read
        as a gap than as a guess.
        """
        import group_tree
        for field, name in (
                # Two ancestries welded into one answer.
                ("ethnicity", "Chinese and Portuguese"),
                ("ethnicity", "Afro-Asian"),
                ("ethnicity", "American or European"),
                # A nationality that is argued over, not a spelling.
                ("ethnicity", "Muslim"),
                ("ethnicity", "Ashkali"),
                # An identity defined by mixture whose census treats it as
                # its own thing.
                ("ethnicity", "Montubio"),
                ("ethnicity", "Cholo/Chola"),
                # Ethiopia's 2007 tail, written with the Amharic language
                # suffix on a root no reference spells the same way.
                ("language", "Shetagna"),
                ("language", "Gedoligna"),
                # And the Central African Republic's, which is mostly
                # Ubangian and not reliably so.
                ("language", "Tal\u00e9"),
        ):
            self.assertIsNone(group_tree.parent_of(field, name),
                              f"{field}: {name} was given a parent")


class SpellingVariantsAreSynonyms(unittest.TestCase):
    def test_a_variant_and_its_target_are_one_group(self):
        import group_tree
        for field, variant, target in (
                ("ethnicity", "Maure", "Moor"),
                ("ethnicity", "Wambo", "Ovambo"),
                ("ethnicity", "Han Chinese", "Han"),
                ("language", "Fulah", "Fula"),
                ("language", "Merina", "Malagasy")):
            self.assertEqual(group_tree.parent_of(field, variant),
                             group_tree.parent_of(field, target),
                             f"{variant} is not filed with {target}")

    def test_a_variant_may_not_shadow_a_name_the_tree_places(self):
        """Two tables disagreeing about one string is a bug, not a fallback.

        If the tree places "Malinke" and a variant also calls it a spelling
        of something else, whichever table is merged last silently wins. The
        builder refuses instead.
        """
        import group_tree
        with self.assertRaises(ValueError):
            group_tree._resolve_variants(
                "ethnicity", {"Zulu": "Xhosa"}, {"Zulu": "Bantu peoples"})


class TheTablesDoNotContradictEachOther(unittest.TestCase):
    def test_no_top_grouping_is_also_declared_a_child(self):
        """A tier-1 node named in some family's child list is a loop.

        "Other and unspecified languages" was a top grouping *and* a member of
        the band hanging under it, so each was the other's parent. Nothing
        caught it while `parent_of` answered from whichever table was merged
        last; it surfaced the moment the top of the tree began saying no.
        """
        import group_tree
        for field in FIELDS:
            tops = group_tree.tier1_names(field)
            for child, parent in group_tree.parents(field).items():
                self.assertNotIn(child, tops,
                                 f"{field}: top grouping {child!r} is also "
                                 f"listed as a child of {parent!r}")


class NounClassPrefixes(unittest.TestCase):
    """One root, however many class markers the censuses put in front of it."""

    def test_a_prefixed_name_is_the_root_it_is_built_on(self):
        import group_tree
        for name in ("Mzaramo", "Ciyao", "Mokgatla", "Muganda", "Xitswa",
                     "Msambaa", "Mbena"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Bantu peoples", name)

    def test_the_rule_only_fires_where_the_convention_holds(self):
        """The guard that keeps three spare letters from matching the world.

        Stripping "Se" from "Serb" leaves "rb", and on a big enough table
        some such remnant will collide with a real name. The rule therefore
        accepts a match only when the root lands in a family that actually
        uses these prefixes, so a European or Asian name is never reached
        this way.
        """
        import group_tree
        self.assertIsNone(group_tree.class_prefix_parent("ethnicity", "Serbian"))
        self.assertIsNone(group_tree.class_prefix_parent("ethnicity", "Mongolian"))
        self.assertIsNone(group_tree.class_prefix_parent("ethnicity", "Malay"))

    def test_an_exact_name_still_wins(self):
        # "Malinke" is in the tree; it must never be read as a prefixed form.
        import group_tree
        self.assertEqual(group_tree.parent_of("ethnicity", "Malinke"),
                         "West African peoples")
