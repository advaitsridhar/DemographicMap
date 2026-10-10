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

        A conjunction of two ancestries that share no node above them is one
        category covering both. Reading it as either would put a real number
        under a heading nobody published, so the rule leaves it unplaced and
        visible as unplaced. (Argentina's "European and Mestizo" and Costa
        Rica's "White or Mestizo" are the Latino majority of their countries
        and are filed there by name, as Colombia's and Mexico's are; the rule
        is what applies where nobody has said so.)
        """
        import group_tree
        for name in ("African and Mestizo", "European and Asian"):
            self.assertIsNone(group_tree.parent_of("ethnicity", name), name)
        for name in ("European and Mestizo", "White or Mestizo"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Hispanic or Latino (census category)", name)

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
            # Scotland writes each census category three ways at once; its
            # Bangladeshi group is a South Asian census category, not the
            # Asian one the tree files as East and Southeast Asian.
            ("ethnicity", "Bangladeshi, Bangladeshi Scottish or Bangladeshi "
                          "British", "South Asian (census category)"),
            ("ethnicity", "Chinese, Chinese Scottish or Chinese British",
             "Asian (census category)"),
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
                # Two ancestries welded into one answer. (Macao's "Chinese
                # and Portuguese" was here; its census defines it as people
                # of both descents, and it is filed as mixed.)
                ("ethnicity", "Afro-Asian"),
                ("ethnicity", "American or European"),
                # A nationality that is argued over, not a spelling.
                ("ethnicity", "Muslim"),
                ("ethnicity", "Ashkali"),
                # And the Balkan Egyptians, whose claimed descent is argued
                # over as the Ashkali's is -- not Egypt's Egyptians, where
                # the compound rule would file them.
                ("ethnicity", "Balkan Egyptian"),
                # (Ecuador's Montubio and Bolivia's Cholo/Chola were here, as
                # identities of mixture each census treats as its own. So are
                # Brazil's pardo and Guatemala's ladino, and all four are now
                # filed with the Latino majorities they belong to -- the
                # owner's rule of 25 September 2026.)
                # Ethiopia's 2007 tail, written with the Amharic language
                # suffix on a root no reference spells the same way.
                ("language", "Shetagna"),
                ("language", "Gedoligna"),
                # And the Central African Republic's, which is mostly
                # Ubangian and not reliably so.
                ("language", "Tal\u00e9"),
                # New Zealand's pooled Middle Eastern, Latin American and
                # African group: three ancestries with no node in common,
                # which the slash rule must not hand to the first of them.
                ("ethnicity", "Middle Eastern/Latin American/African"),
                # Two small mother tongues of Nepal's 2021 census that no
                # reference classifies, and the Myanmar township profiles'
                # transliterations that no reference spells.
                ("language", "Dhuleli"),
                ("language", "Done"),
                ("ethnicity", "Htanot"),
                ("ethnicity", "Kho Lone Li Shaw"),
                ("ethnicity", "Liz"),
                ("ethnicity", "Mong Wong"),
                ("ethnicity", "Myaing"),
                ("ethnicity", "Yinn"),
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

    def test_a_variant_may_not_merge_two_rows_a_source_prints_together(self):
        """A variant says two strings are one group. A source that prints
        both of them in one record says they are two, and the source wins.

        This is not pedantry about spelling: merging them adds one row's
        share to the other's, so a census that distinguishes Bosnian from
        Bosniak, or Nepali from Khas, would have a number invented for it.
        Each of those was a variant here until this test was written.
        """
        import group_tree
        folder = ROOT / "site" / "data"
        if not folder.is_dir():
            raise unittest.SkipTest("site/data has not been built")
        tables = {"language": group_tree.LANGUAGE_VARIANTS,
                  "ethnicity": group_tree.ETHNIC_VARIANTS}
        files = [folder / "admin0.json"]
        for level in ("admin1", "admin2"):
            if (folder / level).is_dir():
                files += sorted((folder / level).iterdir())
        for path in files:
            try:
                records = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                for field, variants in tables.items():
                    rows = record.get(field)
                    if not isinstance(rows, list):
                        continue
                    named = {r["group"] for r in rows
                             if isinstance(r, dict) and r.get("group")}
                    for name, target in variants.items():
                        self.assertFalse(
                            name in named and target in named,
                            f"{field}: {path.name} {record.get('id')} prints "
                            f"{name!r} and {target!r} as two rows, and the "
                            f"tree calls them one group")

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


class PlacementsAcrossTheWrongContinent(unittest.TestCase):
    """Labels the word rules had sent to another continent's family.

    Each case is a label the shipped map carries. A rule read a word in it
    -- a prefix, a substring, the first half of a slash -- and filed it with
    a namesake elsewhere: Nepal's Kisan with the San of the Kalahari,
    Pakistan's Saraiki with Chad's Sara, an Iranian dialect with a language
    of the upper Nile. A label filed wrongly never shows up as unplaced, so
    each is pinned here.
    """

    def check(self, cases):
        import group_tree
        for field, name, expected in cases:
            self.assertEqual(group_tree.parent_of(field, name), expected,
                             f"{field}: {name}")

    def test_south_asian_peoples(self):
        self.check((
            ("ethnicity", "Kisan", "Dravidian peoples"),
            ("ethnicity", "Saraiki", "Indo-Aryan peoples"),
            ("ethnicity", "Magar", "Himalayan and Tibeto-Burman peoples"),
            ("ethnicity", "indigenous or migrant tribes",
             "Himalayan and Tibeto-Burman peoples"),
            ("ethnicity", "Sri Lankan Chetty", "Dravidian peoples"),
        ))

    def test_south_asian_census_categories_are_south_asian(self):
        """A census category that names South Asia is South Asian ancestry.

        Filed with the Asian category, Hong Kong's "Other South Asian",
        Canada's "South Asian", the Caribbean's "East Indian" -- the largest
        group of Trinidad and Tobago and of Guyana -- and the United
        Kingdom's Pakistani and Bangladeshi groups were all drawn as East
        and Southeast Asian ancestry.
        """
        import group_tree
        for name in ("Other South Asian", "South Asian", "East Indian",
                     "Asian Indian", "Indian/Asian",
                     "Asian, Asian British or Asian Welsh: Indian",
                     "Asian, Asian British or Asian Welsh: Pakistani",
                     "Asian, Asian British or Asian Welsh: Bangladeshi",
                     "Pakistani, Pakistani Scottish or Pakistani British",
                     "Indian (Hong Kong)", "Nepalese (Hong Kong)",
                     "Pakistani (Hong Kong)"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "South Asian ancestry", name)
        self.assertEqual(group_tree.at_tier("ethnicity", "West Asian", 1),
                         "Middle Eastern and North African ancestry")
        self.assertEqual(group_tree.parent_of("ethnicity",
                                              "mixed - African/East Indian"),
                         "Mixed or multiple (census category)")
        # The generic Asian category and its East Asian members stay put.
        for name in ("Asian", "Southeast Asian",
                     "Asian, Asian British or Asian Welsh: Chinese"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "East and Southeast Asian ancestry", name)

    def test_hong_kong_ethnic_groups_have_their_own_names(self):
        """Hong Kong's census asks ethnicity; the bare adjectives are the
        nationalities other sources count, and stay filed as nationalities.
        """
        import group_tree
        self.assertEqual(group_tree.parent_of("ethnicity", "Indonesian (Hong Kong)"),
                         "Malay and Indonesian peoples")
        self.assertEqual(group_tree.parent_of("ethnicity", "Thai (Hong Kong)"),
                         "Mainland Southeast Asian peoples")
        for name in ("Indonesian", "Thai", "Indian", "Nepalese", "Pakistani"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "Stated as a nationality", name)

    def test_central_asia_and_the_hindu_kush(self):
        import group_tree
        for name in ("Tajik", "Pamiri"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Iranian peoples of Central Asia", name)
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "Turkic and Central Asian ancestry", name)
        # The Iranian peoples of Iran and of Afghanistan's south and centre
        # stay where they were.
        for name in ("Persian", "Pashtun", "Hazara", "Afghan"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Iranian peoples", name)
        # Nuristani beside the Iranian peoples, not under them.
        self.assertEqual(group_tree.parent_of("ethnicity", "Nuristani"),
                         "Nuristani peoples")
        self.assertEqual(group_tree.at_tier("ethnicity", "Nuristani", 1),
                         "Middle Eastern and North African ancestry")
        self.assertEqual(group_tree.parent_of("ethnicity", "Yugur"),
                         "Turkic peoples")

    def test_myanmar_and_the_moluccas(self):
        import group_tree
        self.assertEqual(group_tree.parent_of("ethnicity", "Naga (Myanmar)"),
                         "Tibeto-Burman peoples of China and Southeast Asia")
        # India's Naga stay with the Himalayan peoples.
        self.assertEqual(group_tree.parent_of("ethnicity", "Naga"),
                         "Himalayan and Tibeto-Burman peoples")
        self.assertEqual(group_tree.parent_of("ethnicity", "Moluccan"),
                         "Malay and Indonesian peoples")
        self.assertEqual(group_tree.parent_of("ethnicity", "Baya"),
                         "Central African peoples")
        self.assertEqual(group_tree.parent_of("ethnicity", "Korean-Chinese"),
                         "Korean peoples")
        self.assertEqual(group_tree.parent_of("ethnicity", "Vietnam"),
                         group_tree.parent_of("ethnicity", "Vietnamese"))

    def test_the_pacific(self):
        self.check((
            ("ethnicity", "Pacific Peoples", "Pacific Islander (census category)"),
            ("ethnicity", "iTaukei", "Melanesian peoples"),
            ("ethnicity", "Yap outer islanders", "Micronesian peoples"),
            ("ethnicity", "Tuvaluan/I-Kiribati", "Mixed or multiple (census category)"),
            ("ethnicity", "Tuvaluan/other", "Mixed or multiple (census category)"),
            ("ethnicity", "I-Kiribati/mixed", "Mixed or multiple (census category)"),
            ("language", "iTaukei", "Oceanic languages"),
            ("language", "Hiri Motu", "Creole languages"),
        ))

    def test_africa_and_its_namesakes(self):
        self.check((
            ("ethnicity", "Cotier/Ngoe/Oroko", "Bantu peoples"),
            ("ethnicity", "Baamba", "Bantu peoples"),
            ("ethnicity", "Maka", "Bantu peoples"),
            ("ethnicity", "Sudanese", "Other national identities"),
            # Sudan's Arabs stay Arab now that the nationality is filed apart.
            ("ethnicity", "Sudanese Arab", "Arab peoples"),
            ("ethnicity", "Caribbean, Caribbean Scottish or Caribbean British",
             "Black or African (census category)"),
            ("ethnicity", "Afro-Mauricien (Creole)",
             "Black or African (census category)"),
            ("language", "Bodo (Central African Republic)", "Bantu languages"),
            ("language", "Komo (Democratic Republic of Congo)", "Bantu languages"),
            ("language", "Kulung (Nigeria)", "Bantu languages"),
            ("language", "Maaka", "Chadic languages"),
            ("language", "Lala-Roba", "Adamawa-Ubangi languages"),
            ("language", "Lama, Lamba", "Gur languages"),
            ("language", "Mina, Guen", "Kwa languages"),
            # The bare homonyms keep their own families.
            ("language", "Bodo", "Tibeto-Burman languages"),
            ("language", "Kulung", "Tibeto-Burman languages"),
        ))

    def test_south_asian_and_iranian_languages(self):
        self.check((
            ("language", "Newari", "Tibeto-Burman languages"),
            ("language", "Pahari-Pothwari", "Indo-Aryan languages"),
            ("language", "Pakistani Pahari (with Mirpuri and Potwari)",
             "Indo-Aryan languages"),
            # Nepal's own Pahari is Tibeto-Burman and stays so.
            ("language", "Pahari", "Tibeto-Burman languages"),
            ("language", "Rāji", "Iranian languages"),
            ("language", "Rubāri", "Iranian languages"),
            ("language", "Banda (Indonesia)", "Malayo-Polynesian languages"),
            ("language", "Sara Bakati'", "Malayo-Polynesian languages"),
            ("language", "Armenic", "Armenian languages"),
        ))
        import group_tree
        self.assertEqual(group_tree.parent_of("language", "Kathmandu Valley Newari"),
                         "Newari")
        self.assertEqual(group_tree.at_tier("language", "Nepalbhasha (Newari)", 1),
                         "Sino-Tibetan languages")
        # Nepal's mother tongues as CLEAR Global names them.
        for name in ("Kham", "Kham-Hor", "Thangmi", "Chantyal", "Camling",
                     "Lamjung-Melamchi Yolmo", "Athpariya", "Belhariya",
                     "Byangsi", "Chintang", "Koi", "Manangba-Nar-Phu",
                     "Nachering", "Tichurong", "Wayu", "Baraamu"):
            self.assertEqual(group_tree.parent_of("language", name),
                             "Tibeto-Burman languages", name)
        for name in ("Tharuic", "Kumhali", "Kuswaric", "Soradi", "Surjapuri",
                     "Acchami", "Bajurali"):
            self.assertEqual(group_tree.parent_of("language", name),
                             "Indo-Aryan languages", name)

    def test_religions(self):
        import group_tree
        table = cg.lookup("religion")
        for name in ("non-Christian", "other non-Christian"):
            canonical = table.get(cg.key(name), name)
            self.assertNotIn("Christianity", cg.ancestry("religion", canonical),
                             name)
        # The negation is on "practising": a non-practising Catholic is a
        # Catholic.
        self.assertEqual(group_tree.parent_of("religion", "Non-practising Catholic"),
                         "Catholicism")
        self.assertEqual(cg.ancestry("religion", "Scheduled Castes"),
                         ["Scheduled Castes", "Hinduism", "Indian religions"])
        self.assertEqual(group_tree.parent_of("religion", "No religion/Refused"),
                         "Not stated")
        self.assertEqual(table[cg.key("none or atheist")], "No religion")
        self.assertEqual(group_tree.parent_of("religion", "Muslim/Jewish"),
                         "Abrahamic religions")


class ANegationIsNotWhatItNegates(unittest.TestCase):
    """"non-Qatari" names no Qatari, and no rule may file it as one."""

    def test_the_rules_never_file_a_label_under_what_it_excludes(self):
        import group_tree
        for field, name, excluded in (
                ("ethnicity", "non-Fijian", "Melanesian peoples"),
                ("ethnicity", "non-Zulu residents", "Bantu peoples"),
                ("ethnicity", "non-Sara groups", "Central African peoples"),
                ("religion", "non-Buddhist", "Buddhism"),
                ("religion", "non-Catholic Christians", "Catholicism")):
            self.assertNotIn(excluded, group_tree.ancestry(field, name),
                             f"{field}: {name}")

    def test_the_shipped_exclusions_are_residuals(self):
        import group_tree
        for name in ("non-Qatari", "non-Niuean", "non-Kenyan", "non-African",
                     "non-Central African Republic ethnic groups",
                     "Other non-Malian ethnic group"):
            self.assertEqual(group_tree.at_tier("ethnicity", name, 1),
                             "Other or not stated ancestry", name)

    def test_two_descents_are_mixed_not_the_half_the_rules_read(self):
        """Macao's descent rows, the Bahamas' two-race answers and Haiti's
        "mixed and White": the word rules read one half of each (with the
        negation skipped, "Chinese and non-Portuguese" reads as Chinese)."""
        import group_tree
        for name in ("Chinese and Portuguese", "Chinese and non-Portuguese",
                     "Portuguese and others", "Black and other",
                     "White and other", "mixed and White"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Mixed or multiple (census category)", name)

    def test_a_negation_inside_a_name_is_read_where_it_is(self):
        import group_tree
        self.assertTrue(group_tree._unnegated("Non-practising Catholic", "Catholic"))
        self.assertFalse(group_tree._unnegated("non-Christian", "Christian"))
        self.assertFalse(group_tree._unnegated("other non-Christian", "Christian"))
        self.assertTrue(group_tree._unnegated("Christian, non-denominational",
                                              "Christian"))


class APassportIsFiledAsOne(unittest.TestCase):
    """A label a source wrote as a nationality is filed as one."""

    def test_national_and_citizen_labels(self):
        import group_tree
        for name in ("Japanese national", "Chinese nationals",
                     "Indonesian national", "Kuwaiti citizens"):
            self.assertEqual(group_tree.parent_of("ethnicity", name),
                             "Other national identities", name)
        self.assertEqual(group_tree.parent_of("ethnicity", "American citizens"),
                         "Settler-nation identities")
        # The labels the tables already name keep their placement.
        self.assertEqual(group_tree.parent_of("ethnicity", "GCC nationals"),
                         "Arab peoples")
        self.assertEqual(group_tree.at_tier("ethnicity", "Foreign nationals", 1),
                         "Other or not stated ancestry")
        # A remainder or an exclusion names no state.
        self.assertIsNone(group_tree.nationality_parent("ethnicity",
                                                        "Other EU nationals"))
        self.assertIsNone(group_tree.nationality_parent("ethnicity",
                                                        "Non-Kenyan nationals"))


class EveryNameHasOneParent(unittest.TestCase):
    def test_no_name_is_listed_under_two_parents_in_two_tables(self):
        """Each table is inverted on its own and merged into one dict, so a
        name two tables list under different parents silently took the
        later table's -- "Indonesian" and "Thai" were Malay and Mainland
        peoples in one table and nationalities in the next, and nothing
        said which one the map drew."""
        import group_tree
        tables = {
            "ethnicity": [
                {n: "Unclassified ethnicity answers"
                 for n in group_tree.ETHNIC_RESIDUALS},
                group_tree._invert(group_tree.ETHNIC_PEOPLES),
                group_tree._invert(group_tree.ETHNIC_CENSUS),
                group_tree._invert(group_tree.ETHNIC_NATIONALITY),
                group_tree._invert(group_tree.ETHNIC_ANCESTRY),
                group_tree._invert(group_tree.ETHNIC_EXTRA)],
            "language": [
                group_tree._invert(group_tree.LANGUAGE_BRANCH),
                group_tree._invert(group_tree.LANGUAGE_BANDS),
                group_tree._invert(group_tree.LANGUAGE_FAMILY),
                group_tree._invert(group_tree.LANGUAGE_EXTRA)],
        }
        for field, parts in tables.items():
            seen = {}
            for part in parts:
                for child, parent in part.items():
                    self.assertEqual(seen.setdefault(child, parent), parent,
                                     f"{field}: {child!r} is under "
                                     f"{seen[child]!r} and {parent!r}")


class FamiliesAreToldApart(unittest.TestCase):
    def test_the_tibeto_burman_family_is_not_its_neighbours_colour(self):
        """The share ramp keeps a colour's hue and saturation and sets its
        lightness, so two families whose hue and saturation nearly match are
        one colour on the map whatever their hex says."""
        import colorsys
        import group_tree

        def hue_and_saturation(name):
            n = int(group_tree.hue("ethnicity", name).lstrip("#"), 16)
            h, _, s = colorsys.rgb_to_hls(((n >> 16) & 255) / 255,
                                          ((n >> 8) & 255) / 255,
                                          (n & 255) / 255)
            return h * 360, s

        node = "Tibeto-Burman peoples of China and Southeast Asia"
        tb_h, tb_s = hue_and_saturation(node)
        for other in ("Korean peoples", "Philippine peoples",
                      "Mainland Southeast Asian peoples"):
            h, s = hue_and_saturation(other)
            gap = min(abs(tb_h - h), 360 - abs(tb_h - h))
            self.assertTrue(gap >= 12 or abs(tb_s - s) >= 0.25,
                            f"{node} and {other} share a colour")
        # A people under it takes its colour.
        self.assertEqual(group_tree.hue("ethnicity", "Tibetan"),
                         group_tree.hue("ethnicity", node))
