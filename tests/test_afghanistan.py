"""Afghan district ethnicity: what the ministry's plans state, and no more."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import afghanistan as a  # noqa: E402


class TheProseThatStatesShares(unittest.TestCase):
    """Every string here came from a province article, not from invention."""

    def test_the_share_may_follow_the_name(self) -> None:
        self.assertEqual(
            a.shares("Pashtun 70%, Tajik 20%, Uzbek 10%"),
            [{"group": "Pashtun", "pct": 70.0}, {"group": "Tajik", "pct": 20.0},
             {"group": "Uzbek", "pct": 10.0}])

    def test_the_share_may_precede_it(self) -> None:
        got = a.shares("60% Uzbek, 20% Tajik, 10% Hazara, 10% Pashtun")
        self.assertEqual([p["group"] for p in got],
                         ["Uzbek", "Tajik", "Hazara", "Pashtun"])
        self.assertEqual(sum(p["pct"] for p in got), 100.0)

    def test_a_village_count_in_front_is_not_a_share(self) -> None:
        self.assertEqual(a.shares("51 villages. 100% Tajik."),
                         [{"group": "Tajik", "pct": 100.0}])

    def test_a_single_group_at_one_hundred_is_a_composition(self) -> None:
        self.assertTrue(a.usable(a.shares("100% Tajik"), "x"))


class TheProseThatDoesNot(unittest.TestCase):
    """A district that says "majority" is a gap, and must stay one.

    Turning majority and minority into numbers would invent the figures, and
    an invented composition is indistinguishable on the map from a measured
    one -- which is the whole reason this map prefers a visible hole.
    """

    def test_majority_and_minority_are_not_numbers(self) -> None:
        self.assertEqual(a.shares("Majority Turkmen, minority Tajik"), [])

    def test_predominantly_and_few_are_not_numbers(self) -> None:
        self.assertEqual(
            a.shares("Predominantly Pamiris (Ishkashimi), few Tajik"), [])

    def test_a_bare_group_name_is_not_a_composition(self) -> None:
        self.assertEqual(a.shares("Tajik"), [])

    def test_an_empty_cell_is_refused(self) -> None:
        self.assertFalse(a.usable(a.shares(""), "x"))


class WhatIsRefusedOnArithmetic(unittest.TestCase):
    def test_shares_that_overrun_are_dropped(self) -> None:
        # Over 100 means a group counted twice; the arithmetic then describes
        # nobody, so the district keeps its gap.
        self.assertFalse(
            a.usable([{"group": "Tajik", "pct": 80.0},
                      {"group": "Uzbek", "pct": 40.0}], "x"))

    def test_shares_that_fall_far_short_are_dropped(self) -> None:
        self.assertFalse(a.usable([{"group": "Tajik", "pct": 20.0}], "x"))

    def test_shares_that_fall_a_little_short_are_kept(self) -> None:
        # The plans list the groups they list; 90% of a district described is
        # a reading, not a fault.
        self.assertTrue(
            a.usable([{"group": "Pashtun", "pct": 70.0},
                      {"group": "Tajik", "pct": 20.0}], "x"))

    def test_a_group_named_twice_keeps_the_first_figure(self) -> None:
        got = a.shares("Tajik 60%, Uzbek 30%, 10% Tajik")
        self.assertEqual([p["group"] for p in got], ["Tajik", "Uzbek"])
        self.assertEqual(got[0]["pct"], 60.0)


class TheCellIsStrippedBeforeItIsRead(unittest.TestCase):
    def test_markup_alignment_and_references_come_out(self) -> None:
        self.assertEqual(
            a.clean("align=right| 145 villages. Majority [[Tajiks|Tajik]]."
                    "<ref name=x/>"),
            "145 villages. Majority Tajik.")

    def test_a_link_without_a_label_keeps_its_target(self) -> None:
        self.assertEqual(a.clean("[[Hazara]] 40%, [[Pashtun]] 60%"),
                         "Hazara 40%, Pashtun 60%")


class TheColumnIsFoundByShapeNotOneSpelling(unittest.TestCase):
    """Baghlan heads it "Notes"; Badakhshan runs two headings into one cell."""

    def test_notes(self) -> None:
        self.assertEqual(
            a.notes_column(["District", "Capital", "Population", "Notes"]), 3)

    def test_villages_and_ethnic_groups_run_together(self) -> None:
        self.assertEqual(
            a.notes_column(["District", "Population", "Villages Ethnic groups"]), 2)

    def test_a_table_with_no_such_column_is_passed_over(self) -> None:
        self.assertIsNone(a.notes_column(["District", "Capital", "Area"]))

    def test_the_district_column_is_found_by_name(self) -> None:
        self.assertEqual(a.name_column(["No.", "District", "Capital"]), 1)


class ThePolicyNoLongerForbidsIt(unittest.TestCase):
    def test_ethnicity_is_writable_and_the_other_two_are_not(self) -> None:
        from common import NOT_COLLECTED_POLICY               # noqa: PLC0415
        afg = NOT_COLLECTED_POLICY["AFG"]
        self.assertNotIn("ethnicity", afg,
                         "the owner's decision of 22 September 2026: where a "
                         "source exists it is read")
        self.assertIn("religion", afg, "no source was found for these two")
        self.assertIn("language", afg)


class AHeaderSplitByItsOwnCitation(unittest.TestCase):
    """Badghis heads a column "Area" and hangs a {{Cite web}} on it.

    The table parser splits cells on "|" and the template carries its own, so
    seven header cells were counted where every data row had six. The ethnic
    column's index came out one too high and all fifteen rows were skipped for
    being too short -- the province reported nothing rather than a refusal.
    """

    BADGHIS = ["District", "Capital", "Population",
               "Area {{Cite web|url=https://www.fao.org/|website=www.fao.org"
               "|accessdate=16 February 2024",
               "title=Food and Agriculture Organization}}",
               "Pop. density", "Ethnic categories"]

    def test_the_fragments_are_rejoined(self) -> None:
        self.assertEqual(len(a.repair_header(self.BADGHIS)), 6)

    def test_the_column_index_then_matches_the_data_rows(self) -> None:
        self.assertEqual(a.notes_column(a.repair_header(self.BADGHIS)), 5)
        self.assertEqual(a.notes_column(self.BADGHIS), 6,
                         "unrepaired, it points one past where the note is")

    def test_a_header_with_no_templates_is_unchanged(self) -> None:
        plain = ["District", "Capital", "Population", "Notes"]
        self.assertEqual(a.repair_header(plain), plain)

    def test_a_template_that_never_closes_does_not_swallow_the_rest(self) -> None:
        # Better one long cell than an exception or a silent drop.
        got = a.repair_header(["District", "Area {{Cite", "Notes"])
        self.assertEqual(got[0], "District")
        self.assertEqual(len(got), 2)


class TheTwoKindsOfOverrun(unittest.TestCase):
    """Rounding lands just over a hundred; a row that is not a district at
    all lands far over. The first run showed both and they do not overlap.
    """

    def test_a_rounding_overrun_is_kept(self) -> None:
        # Qala i Naw, refused by the first run at 101.0%.
        self.assertTrue(a.usable([{"group": "Pashtun", "pct": 60.0},
                                  {"group": "Tajik", "pct": 25.0},
                                  {"group": "Aimaq", "pct": 16.0}], "Qala i Naw"))

    def test_a_tenth_of_a_point_over_is_kept(self) -> None:
        # Herat, refused at 100.9%.
        self.assertTrue(a.usable([{"group": "Tajik", "pct": 80.9},
                                  {"group": "Pashtun", "pct": 20.0}], "Herat"))

    def test_a_province_summary_row_is_still_refused(self) -> None:
        # Badakhshan's own row concatenates every district's note: 185.4%.
        self.assertFalse(a.usable([{"group": "Tajik", "pct": 100.0},
                                   {"group": "Pashtun", "pct": 85.4}], "Badakhshan"))

    def test_the_gap_between_the_two_kinds_is_not_crossed(self) -> None:
        # Nothing observed sits between 103% and 144%; 110% is refused.
        self.assertFalse(a.usable([{"group": "Tajik", "pct": 70.0},
                                   {"group": "Uzbek", "pct": 40.0}], "x"))


class ADistrictNameThatRepeatsAcrossProvinces(unittest.TestCase):
    """Afghanistan has a Baharak in Badakhshan and another in Takhar, a
    Fayzabad in Badakhshan and another in Jowzjan -- nine such pairs.

    Keyed on the district name alone they collide before matching begins, and
    the survivor is then matched country-wide, where an ambiguous name is
    refused outright -- so both districts end up with nothing.
    """

    def rows(self):
        import re as _re
        out = []
        for province, district in (("Badakhshan", "Baharak"),
                                   ("Takhar", "Baharak")):
            slug = _re.sub(r"[^a-z0-9]+", "-",
                           f"{province} {district}".lower()).strip("-")
            out.append((f"AFG-admin2-{slug}", province, district))
        return out

    def test_the_id_carries_the_province(self) -> None:
        ids = [i for i, _, _ in self.rows()]
        self.assertEqual(len(set(ids)), 2, f"ids collide: {ids}")
        self.assertIn("badakhshan", ids[0])
        self.assertIn("takhar", ids[1])

    def test_the_reader_names_the_parent_on_every_record(self) -> None:
        src = (Path(__file__).resolve().parent.parent / "scripts"
               / "fetch_census" / "afghanistan.py").read_text()
        self.assertIn("parent_name=row[\"province\"]", src,
                      "match_admin2 resolves a repeated district name only "
                      "when the row says which province it is in")

    def test_the_province_is_carried_out_of_the_table_reader(self) -> None:
        src = (Path(__file__).resolve().parent.parent / "scripts"
               / "fetch_census" / "afghanistan.py").read_text()
        self.assertIn('"province": province', src)


class ADistrictTheTableNamesTwice(unittest.TestCase):
    """Four provinces have a district sharing the province's name and print
    two rows for it. Sometimes that is one figure at two precisions, and
    sometimes it is two sources that disagree.
    """

    def row(self, *pairs):
        return {"district": "X", "province": "P",
                "ethnicity": [{"group": g, "pct": p} for g, p in pairs]}

    def test_one_row_passes_through(self) -> None:
        kept, why = a.settle([self.row(("Tajik", 100.0))])
        self.assertEqual(why, "")
        self.assertEqual(len(kept), 1)

    def test_the_same_figures_rounded_twice_keep_the_finer_one(self) -> None:
        # Kunduz, as the article prints it.
        coarse = self.row(("Pashtun", 33.0), ("Uzbek", 27.0), ("Tajik", 22.0))
        fine = self.row(("Pashtun", 33.2), ("Uzbek", 26.8), ("Tajik", 21.8))
        kept, why = a.settle([coarse, fine])
        self.assertEqual(why, "")
        self.assertEqual(kept, [fine], "the finer reading is the one to keep")

    def test_two_readings_that_contradict_keep_neither(self) -> None:
        # Ghazni: Tajik at 50% in one row and 7.4% in the other.
        kept, why = a.settle([
            self.row(("Tajik", 50.0), ("Pashtun", 25.0), ("Hazara", 20.0)),
            self.row(("Tajik", 7.4), ("Pashtun", 48.1), ("Hazara", 43.8))])
        self.assertEqual(kept, [], "a district cannot be both")
        self.assertIn("Tajik", why)
        self.assertIn("50", why)

    def test_the_refusal_names_the_group_that_moved_most(self) -> None:
        _, why = a.settle([
            self.row(("Hazara", 76.0), ("Tajik", 20.0)),
            self.row(("Hazara", 83.9), ("Tajik", 20.0))])
        self.assertIn("Hazara", why)

    def test_readings_of_different_groups_keep_neither(self) -> None:
        kept, why = a.settle([self.row(("Tajik", 100.0)),
                              self.row(("Pashtun", 100.0))])
        self.assertEqual(kept, [])
        self.assertIn("different groups", why)

    def test_a_two_point_gap_is_rounding_and_is_kept(self) -> None:
        kept, why = a.settle([self.row(("Tajik", 60.0), ("Uzbek", 40.0)),
                              self.row(("Tajik", 61.5), ("Uzbek", 38.5))])
        self.assertEqual(why, "")
        self.assertEqual(len(kept), 1)


class TheAliasesNameShapesThatExist(unittest.TestCase):
    """An alias is a claim about the boundary file, so it is checked against
    it. A table of aliases nobody verifies is how a district ends up wearing
    another district's figures.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import json
        root = Path(__file__).resolve().parent.parent
        cls.a1 = {s["id"]: s["name"]
                  for s in json.loads((root / "site/data/admin1/AFG.units.json")
                                      .read_text())}
        cls.shapes = json.loads((root / "site/data/admin2/AFG.units.json").read_text())
        cls.provinces = set(cls.a1.values())
        cls.by_province = {}
        for s in cls.shapes:
            cls.by_province.setdefault(
                cls.a1.get(s["parent"], "?"), set()).add(s["name"])

    def test_every_renamed_province_is_on_the_map(self) -> None:
        for article, on_map in a.PROVINCE_ON_MAP.items():
            self.assertIn(on_map, self.provinces,
                          f"{article!r} -> {on_map!r} names no province")
            self.assertNotIn(article, self.provinces,
                             f"{article!r} is already on the map; no alias needed")

    def test_every_province_the_reader_lists_resolves(self) -> None:
        for p in a.PROVINCES:
            self.assertIn(a.PROVINCE_ON_MAP.get(p, p), self.provinces,
                          f"{p!r} reaches no province on the map")

    def test_every_district_alias_names_a_shape_in_that_province(self) -> None:
        for (province, article), on_map in a.DISTRICT_ON_MAP.items():
            here = self.by_province.get(a.PROVINCE_ON_MAP.get(province, province),
                                        set())
            self.assertIn(on_map, here,
                          f"{province}/{article!r} -> {on_map!r} is not a "
                          f"district of that province")

    def test_no_alias_points_at_a_name_the_article_already_uses(self) -> None:
        # If both spellings exist as shapes, renaming moves the figures off a
        # real district onto a different one -- the invisible error.
        for (province, article), on_map in a.DISTRICT_ON_MAP.items():
            here = self.by_province.get(a.PROVINCE_ON_MAP.get(province, province),
                                        set())
            if article in here:
                self.assertEqual(article, on_map,
                                 f"{province}/{article!r} is itself a shape; "
                                 f"aliasing it to {on_map!r} would move the "
                                 f"figures onto another district")

    def test_the_tables_have_no_duplicate_targets_in_one_province(self) -> None:
        import collections
        per = collections.defaultdict(list)
        for (province, article), on_map in a.DISTRICT_ON_MAP.items():
            per[(province, on_map)].append(article)
        clashes = {k: v for k, v in per.items() if len(v) > 1}
        self.assertEqual({}, clashes,
                         "two article names aliased onto one shape")


class TheProvinceTableIsSourcesNotACensus(unittest.TestCase):
    """Afghanistan has never counted its people, so a province article
    tabulates what a dozen bodies each estimated, one row per source.
    Every string here is Balkh's, as the article prints it.
    """

    HEAD = ["Ethnicity", "Tajik/ Farsiwan", "Hazara", "Arab", "Pashtun",
            "Turkmen", "Uzbek", "Others", "Sources"]

    def test_the_header_names_its_group_columns(self) -> None:
        cols = a.group_columns(self.HEAD)
        self.assertEqual(cols[1], "Tajik", "a slashed column is one people")
        self.assertEqual([cols[i] for i in sorted(cols)],
                         ["Tajik", "Hazara", "Arab", "Pashtun", "Turkmen",
                          "Uzbek", "Other"])
        self.assertNotIn(0, cols, "'Ethnicity' is a label, not a group")
        self.assertNotIn(8, cols, "'Sources' is a label, not a group")

    def test_a_whole_row_is_read_newest_first(self) -> None:
        rows = a.source_rows([self.HEAD,
            ["2011 USA", "50%", "12%", "7%", "11%", "10%", "10%", "0%", "-"],
            ["2018 UN", "46%", "12%", "7%", "10%", "15%", "10%", "0%", "-"]])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 2018, "newest first")
        self.assertEqual(rows[0][1], "UN")
        self.assertEqual(rows[0][2][0], {"group": "Tajik", "pct": 46.0})

    def test_a_row_with_a_stray_cell_is_refused_not_shifted(self) -> None:
        # The real trap. Read positionally this hands Balkh's Tajik plurality
        # to its Hazara minority -- the wrong answer wearing the right shape.
        rows = a.source_rows([self.HEAD,
            ["2018 UN", "", "46%", "12%", "7%", "10%", "15%", "10%", "-"]])
        self.assertEqual(rows, [], "a row that does not line up is not read")

    def test_a_range_is_refused(self) -> None:
        rows = a.source_rows([self.HEAD,
            ["2004-2021", "<=46%", "<=12%", "<=7%", "10 - 27%", "12 - 15%",
             "10 - 11%", "0%", "-"]])
        self.assertEqual(rows, [], "which end of a range is the answer")

    def test_a_colspan_row_is_refused(self) -> None:
        rows = a.source_rows([self.HEAD,
            ["2015 NPS", "colspan=3| 50%", "27%", "11.9%", "10.7%", "-",
             "-", "-", "-"]])
        self.assertEqual(rows, [], "one value covering three groups")

    def test_a_word_is_not_a_number(self) -> None:
        rows = a.source_rows([self.HEAD,
            ["2011 UCD", "majority", "minority", "-", "minority", "-", "-",
             "-", "-"]])
        self.assertEqual(rows, [])

    def test_a_header_naming_too_few_groups_reads_nothing(self) -> None:
        self.assertEqual(a.source_rows([["Period", "Sources"],
                                        ["2018 UN", "46%"]]), [])
