"""Papua New Guinea's two census publications, and the guards on reading them."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
from fetch_census import png  # noqa: E402

# Two pages of the 2011 National Report's provincial Summary Indicators, as
# pypdf extracts them: four regional blocks, and the religion row printed two
# different ways -- figures on the label's own line in three of them, on the
# line below in the fourth.
SUMMARY_28 = """Papua New Guinea 2011 National Report
28
Summary Indicators Provinces, 2011 Census
Southern Region
Citizen population Western Gulf Central NCD MBP Northern
Female heads of households
(% of household heads)
Total 11.4 14.3 13.4 12.8 17.2 9.1
Evan.All. U/Church U/Church U/Church U/Church Anglican
Main religion (% of population) Total 37.1 30.1 40.0 23.0 54.9 60.6
Male 36.8 30.4 40.1 22.9 55.4 60.7
Citizen Population
Highlands Region
SHP Enga WHP Chimbu EHP Hela Jiwaka
Female heads of households
(% of household heads)
Total 10.4 9.1 15.7 7.1 12.2 20.2 11.5
R/Cath. Evan.Luth Evan.Luth R/Cath. SDA Evan.All R/Cath.
Main religion (% of population) Total 19.7 26.4 26.0 34.4 39.6 19.7 29.6
Male 20.0 26.6 26.3 34.7 39.3 19.4 29.8
"""
SUMMARY_29 = """Papua New Guinea 2011 National Report
29
Momase Region
Citizen population Morobe Madang ESP WSP
Female heads of households                     Total 12.9 11.2 17.0 14.0
(% of household heads)
Evan.Luth Evan.Luth R/Cath R/Cath.
Main religion (% of population) Total 67.0 38.4 43.0 40.4
Male 67.4 38.4 43.4 41.3
Citizen Population New Guinea Islands Region
Manus NIP ENBP WNBP AROB
Female heads of households
(% of household heads)
Total 22.4 17.0 20.9 12.9 17.0
Main religion (% of population) R/Cath. R/Cath. R/Cath. R/Cath. R/Cath.
Total 38.5 31.3 42.8 55.3 68.4
Male 38.7 31.3 42.9 55.3 68.3
"""

# One Provincial Snapshot of the 2024 booklet, with the office's kerning
# intact: "41 2 ,15 8" is 412,158 and "T otal" is Total.
SNAPSHOT = """2024 National Population Census Final Figures
11
05. MILNE BAY PROVINCE
Population in brief
41 2 ,1 5 8 216,985 1 9 5,1 7 3
T otal Population Male Female
Districts Total Male Female
Alotau 149,806 79,618 7 0,18 8
Samarai-Murua 82,930 43,679 39,251
Kiriwina-Goodenough 94,002 48,759 45,243
Esa'ala 85,420 44,929 40,491
Proportion of PNG's total population  4.0%
Annual growth rate since 2011 census 3.1%
Sex Ratio (males per 100 females)  111
District with highest population count Alotau
"""


# Table 1 of the 2024 booklet, with the prose that surrounds it on the page.
TABLE_1 = """2024 National Population Census Final Figures
2. PROVINCIAL OVERVIEW
Of the 22 provinces that make up PNG, Morobe recorded the highest, nearing a million mark, and
Eastern Highlands Province with 800,072. T able 1 below shows the population distribution for each
province.
T able 1: Population by sex, sex ratio and province, 2024
Province Persons Males Females Sex Ratio
Papua New Guinea 10,18 5, 3 6 3 5,336,546 4,848,817 110
1.  Western 300,019 156,603 143,416 109
2. Gulf 203,545 106,948 96,597 111
3. Central 373,779 198,877 174,902 114
4. National Capital District 756,754 403,291 353,463 114
5. Milne Bay 41 2 ,15 8 216,985 1 95,1 73 111
6. Northern 273,950 144,626 129,324 112
7 .  Southern Highlands 602,085 311,380 290,705 107
8. Enga 489,971 256,586 233,385 110
9. Western Highlands 462,566 237 ,582 224,984 106
10. Chimbu 458,406 242,663 215,743 112
11. Eastern Highlands 800,072 4 1 7, 2 7 3 382,799 109
12. Hela 365,806 194,762 171,044 114
13. Jiwaka 455,208 2 3 7,0 5 1 218, 157 109
14. Morobe 997 ,545 526,505 471,040 112
15. Madang 761,15 4 401,885 359,269 112
16. East Sepik 631,791 321,593 310, 198 104
17 . West Sepik 362,721 189,334 173,387 109
18. Manus 69,560 36,232 33,328 109
19. New Ireland 2 3 7,7 8 0 125,634 11 2 ,1 4 6 112
20. East New Britain 434,757 226,079 208,678 108
21. West New Britain 368,643 1 95,180 173,463 113
22.  Autonomous Region of Bougainville 3 6 7,0 9 3 189,477 1 7 7, 6 1 6 107
Population Distribution by Region
At the provincial level, Morobe has the highest percentage (9.8%), followed by Eastern Highlands
Province (7 .9%), Madang (7 .5%) and National Capital District (7 .4%).
"""


class TheProvinceTable(unittest.TestCase):
    def setUp(self):
        self.read = png.read_province_table([TABLE_1])

    def test_all_twenty_two_provinces_are_read(self):
        self.assertEqual(set(self.read), set(png.PROVINCES))
        self.assertEqual(sum(u.total for u in self.read.values()), 10_185_363)

    def test_a_longer_name_is_not_eaten_by_a_shorter_one(self):
        # "Western Highlands" starts with "Western". Taking the shorter name
        # first read row 9 as a second Western and lost the province.
        self.assertEqual(self.read["Western"].total, 300_019)
        self.assertEqual(self.read["Western Highlands"].total, 462_566)

    def test_the_prose_around_the_table_is_not_read_as_a_row(self):
        # The paragraph above ends "... Eastern Highlands Province with
        # 800,072. Table 1 below shows ...", which is not a row.
        self.assertEqual(self.read["Eastern Highlands"].male, 417_273)

    def test_a_file_that_is_not_the_2024_final_figures_is_refused(self):
        moved = TABLE_1.replace("10,18 5, 3 6 3 5,336,546 4,848,817 110",
                                "10,185,364 5,336,547 4,848,817 110")
        with self.assertRaises(SystemExit) as caught:
            png.read_province_table([moved])
        self.assertIn("2024 Final Figures", str(caught.exception))


class ReadingAKernedRow(unittest.TestCase):
    """The office's PDFs break a figure into groups; the row's own arithmetic
    is what says where one figure ends and the next begins."""

    def test_the_national_row(self):
        self.assertEqual(
            png.split_figures("10,18 5, 3 6 3 5,336,546 4,848,817 110", 4, ratio=True),
            (10_185_363, 5_336_546, 4_848_817, 110))

    def test_a_province_row(self):
        self.assertEqual(
            png.split_figures("41 2 ,15 8 216,985 1 95,1 73 111", 4, ratio=True),
            (412_158, 216_985, 195_173, 111))

    def test_a_district_row(self):
        self.assertEqual(png.split_figures("39,676 20,516 1 9,1 6 0", 3),
                         (39_676, 20_516, 19_160))

    def test_a_row_whose_sexes_do_not_add_up_is_refused(self):
        # Males and females one short of the total: no cut of these digits
        # satisfies the census's own arithmetic, so nothing is written.
        with self.assertRaises(SystemExit):
            png.split_figures("39,677 20,516 19,160", 3)

    def test_a_row_with_no_digits_is_refused(self):
        with self.assertRaises(SystemExit):
            png.split_figures("District with highest population count", 3)

    def test_a_capital_read_away_from_its_word_is_put_back(self):
        self.assertEqual(png.unkern("T elefomin 63,479"), "Telefomin 63,479")
        self.assertEqual(png.unkern("T awae/Siassi"), "Tawae/Siassi")


class TheProvincialReligionRow(unittest.TestCase):
    def setUp(self):
        self.read = png.read_main_religion([SUMMARY_28, SUMMARY_29])

    def test_every_province_is_read(self):
        self.assertEqual(set(self.read), set(png.PROVINCES))

    def test_the_denominations_come_out_as_the_report_abbreviates_them(self):
        self.assertEqual(self.read["Autonomous Region of Bougainville"],
                         ("Roman Catholic", 68.4))
        self.assertEqual(self.read["Morobe"], ("Evangelical Lutheran", 67.0))
        self.assertEqual(self.read["Northern"], ("Anglican", 60.6))
        self.assertEqual(self.read["Eastern Highlands"],
                         ("Seventh Day Adventist", 39.6))
        self.assertEqual(self.read["Western"], ("Evangelical Alliance", 37.1))

    def test_a_table_that_contradicts_the_reports_own_prose_is_refused(self):
        # The report says in prose that Morobe is Evangelical Lutheran at 67%.
        # A column read one place out would make it Roman Catholic, and that
        # is the reading this check exists to stop.
        moved = SUMMARY_29.replace("Evan.Luth Evan.Luth R/Cath R/Cath.",
                                   "R/Cath. Evan.Luth Evan.Luth R/Cath.")
        with self.assertRaises(SystemExit) as caught:
            png.read_main_religion([SUMMARY_28, moved])
        self.assertIn("prose", str(caught.exception))

    def test_an_unknown_abbreviation_is_refused_not_dropped(self):
        renamed = SUMMARY_28.replace("SDA", "Luth.Ren")
        with self.assertRaises(SystemExit) as caught:
            png.read_main_religion([renamed, SUMMARY_29])
        self.assertIn("0 readings", str(caught.exception))
        self.assertIn("Highlands Region", str(caught.exception))

    def test_a_missing_block_is_refused(self):
        with self.assertRaises(SystemExit):
            png.read_main_religion([SUMMARY_28])

    def test_the_same_block_in_another_chapter_is_not_a_second_reading(self):
        # The report heads these columns once per chapter -- six Summary
        # Indicators pages carry the Southern Region's -- and only chapter
        # 2's has a religion row beneath it.
        chapter_4 = """Summary Indicators Provinces, 2011 Census
Southern Region
Citizen population Western Gulf Central NCD MBP Northern
Literacy rate
(% of population aged 10 years and over)
Total 61.0 62.7 71.9 94.2 77.8 69.0
"""
        read = png.read_main_religion([chapter_4, SUMMARY_28, SUMMARY_29])
        self.assertEqual(read["Western"], ("Evangelical Alliance", 37.1))
        self.assertEqual(len(read), 22)

    def test_the_national_religion_row_is_not_read_as_a_block(self):
        # Chapter 2 opens with the national Summary Indicators, whose row
        # carries the same label and three columns -- the census years. It
        # sits inside the window of the previous chapter's last block, so
        # only the width tells it apart.
        national = """Summary Indicators PNG, 1980, 1990, 2000 and 2011 Censuses
R/Cath. R/Cath. R/Cath.
Main religion (% of population) Total 26.0 27.6 28.4 na
Male 26.1 27.8 28.5 na
"""
        read = png.read_main_religion([SUMMARY_28, national, SUMMARY_29])
        self.assertEqual(read["Manus"], ("Roman Catholic", 38.5))
        self.assertEqual(len(read), 22)

    def test_the_labels_are_the_projects_canon(self):
        import canonical_groups as cg
        for label in set(png.DENOMINATIONS.values()):
            self.assertTrue(cg.ancestry("religion", label), label)


class TheProvincialSnapshot(unittest.TestCase):
    def test_a_snapshots_districts_are_read_with_their_names(self):
        province, districts = png.read_snapshot(SNAPSHOT)
        self.assertEqual(province, "Milne Bay")
        self.assertEqual([d.name for d in districts],
                         ["Alotau", "Samarai-Murua", "Kiriwina-Goodenough", "Esa'ala"])
        self.assertEqual(sum(d.total for d in districts), 412_158)
        self.assertEqual(districts[0].ratio, 113)

    def test_a_trailing_word_district_is_not_part_of_the_name(self):
        page = SNAPSHOT.replace("Alotau 149,806", "Alotau District 149,806")
        _, districts = png.read_snapshot(page)
        self.assertEqual(districts[0].name, "Alotau")


class PlacingDistrictsOnShapes(unittest.TestCase):
    def unit(self, name, total):
        half = total // 2
        return png.Unit(name, total, total - half, half)

    def test_a_shape_whose_name_names_its_two_districts_is_their_sum(self):
        placed, left = png.place_districts("Hela", [
            self.unit("Komo Hulia", 77_114), self.unit("Koroba Kopiago", 130_425),
            self.unit("Tari/Pori", 102_081), self.unit("Magarima", 56_186)])
        self.assertEqual(left, [])
        self.assertEqual(sorted(placed), ["Komo/Magarima District",
                                          "Koroba/Kopiago District",
                                          "Tari/Pori District"])
        self.assertEqual(placed["Komo/Magarima District"].total, 77_114 + 56_186)
        self.assertEqual(placed["Komo/Magarima District"].parts,
                         ("Komo Hulia", "Magarima"))
        self.assertEqual(placed["Tari/Pori District"].parts, ())

    def test_a_summed_shape_says_what_was_summed(self):
        placed, _ = png.place_districts("Hela", [
            self.unit("Komo Hulia", 77_114), self.unit("Koroba Kopiago", 130_425),
            self.unit("Tari/Pori", 102_081), self.unit("Magarima", 56_186)])
        note = png.district_record(
            "Hela", "Komo/Magarima District",
            placed["Komo/Magarima District"], "")["population_note"]
        self.assertIn("Komo Hulia, Magarima", note)
        self.assertIn("Hela", note)

    def test_a_renamed_district_reaches_its_shape(self):
        placed, _ = png.place_districts("Western Highlands", [
            self.unit("Dei", 91_051), self.unit("Hagen Central", 160_914),
            self.unit("Mul/Baiyer", 110_252), self.unit("Tambul/Nebilyer", 100_349)])
        self.assertIn("Mt Hagen District", placed)
        self.assertEqual(len(placed), png.SHAPES["Western Highlands"])

    def test_a_province_with_a_district_no_shape_draws_is_left_whole(self):
        # Delta Fly has been carved out since 2011 and the booklet does not
        # say from which district, so none of Western's three shapes is
        # written -- a count on the wrong one would be invisible.
        placed, left = png.place_districts("Western", [
            self.unit("Middle Fly", 39_676), self.unit("North Fly", 102_633),
            self.unit("South Fly", 81_613), self.unit("Delta Fly", 76_097)])
        self.assertEqual(placed, {})
        self.assertEqual(left, ["Delta Fly"])


class WhatIsDeclared(unittest.TestCase):
    def test_the_shapes_declared_are_the_boundary_files_eighty_seven(self):
        self.assertEqual(sum(png.SHAPES.values()), 87)
        self.assertEqual(set(png.SHAPES), set(png.PROVINCES))

    def test_every_redrawn_province_lists_all_of_its_shapes(self):
        self.assertEqual(sorted(png.REDRAWN_SHAPES), png.REDRAWN)
        for province, shapes in png.REDRAWN_SHAPES.items():
            self.assertEqual(len(shapes), png.SHAPES[province], province)

    def test_sixteen_shapes_are_the_ones_left_without_a_count(self):
        self.assertEqual(sum(len(s) for s in png.REDRAWN_SHAPES.values()), 16)

    def test_a_union_only_ever_joins_districts_of_one_province(self):
        # Every part of a declared union must be a district name, never a
        # shape name, or the sum would be of the wrong things.
        for parts in png.UNIONS.values():
            for part in parts:
                self.assertNotIn(" District", part)


class TheDeclarationsAboutWhatTheCensusAsks(unittest.TestCase):
    def test_ethnicity_and_language_are_declared_not_collected(self):
        for field in ("ethnicity", "language"):
            marker = common.collection_gap("PNG", field)
            self.assertIsNotNone(marker, field)
            self.assertEqual(marker["status"], common.NOT_COLLECTED)

    def test_religion_is_not_declared_because_the_census_asks_it(self):
        self.assertIsNone(common.collection_gap("PNG", "religion"))

    def test_the_language_declaration_says_what_is_asked_instead(self):
        note = common.collection_policy("PNG", "language")
        self.assertIn("literacy", note.lower())
        self.assertIn("Tokples", note)

    def test_the_ethnicity_declaration_names_the_questionnaire(self):
        note = common.collection_policy("PNG", "ethnicity")
        self.assertIn("33 questions", note)

    def test_a_declaration_never_states_a_share(self):
        # The rule the Maldives' "100% Islam" was written down to prevent.
        for field in ("ethnicity", "language"):
            self.assertNotIn("%", common.collection_policy("PNG", field))


if __name__ == "__main__":
    unittest.main()
