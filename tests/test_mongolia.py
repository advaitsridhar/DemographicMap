"""Mongolia: how a row of glyphs becomes a row of figures, how a soum finds
its shape, and what the reader refuses rather than writes."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import mongolia as M  # noqa: E402

RAW = ROOT / "data" / "raw" / "mongolia"
OUT = ROOT / "data" / "processed" / "mongolia.json"


def boxed(*words):
    """A line as --fetch writes it: each word with the span it occupies."""
    return " ".join(f"{text}[{x0:.0f}-{x1:.0f}]" for text, x0, x1 in words)


class Aimags(unittest.TestCase):
    def test_the_twenty_two_are_the_boundary_file_s_own_names(self):
        first = json.loads((ROOT / "site" / "data" / "admin1" / "MNG.json").read_text())
        self.assertEqual(sorted(M.AIMAGS), sorted(row["name"] for row in first))

    def test_every_aimag_has_an_english_name_and_a_book(self):
        for name, (english, files) in M.AIMAGS.items():
            self.assertTrue(english, name)
            self.assertTrue(files, name)
            self.assertTrue(all(f.endswith(".pdf") for f in files), name)

    def test_the_raw_file_name_is_ascii(self):
        for name in M.AIMAGS:
            self.assertEqual(M.raw_name(name), M.raw_name(name).encode().decode("ascii"))


class Folding(unittest.TestCase):
    """The boundary file romanises Mongolian one way and the books write it in
    Cyrillic; the fold is what the two agree on."""

    def test_the_boundary_file_s_spellings_are_reached_from_cyrillic(self):
        for cyrillic, latin in (
                ("Адаацаг", "Adaacag"), ("Алдархаан", "Aldarxaan"),
                ("Алтанцөгц", "Altanco'gc"), ("Өндөр-Улаан", "O'ndor-Ulaan"),
                ("Бор-Өндөр", "Bor-Ondor"), ("Хэрлэн", "Herlen"),
                ("Хэрлэн", "Xerlen"), ("Сайнцагаан", "Saintsagaan"),
                ("Цагаандэлгэр", "Cagaandelger"), ("Замын-Үүд", "Zamyn U'ud"),
                ("Халхгол", "Xalx gol"), ("Их-Хэт", "Ix xet"),
                ("Баян-Агт", "Bayan agt"), ("Есөнбулаг", "Yeso'nbulag"),
                ("Төвшрүүлэх", "To'vshru'ulex"), ("Рэнчинлхүмбэ", "Renchinlxu'mbe"),
                ("Чандмань", "Chandmani"), ("Мянгад", "Myangad"),
                ("Шарынгол", "Sharyngol"), ("Ерөө", "Yero'o"),
                ("Хөлөнбуйр", "Xo'lonbuir")):
            self.assertEqual(M.fold(cyrillic), M.fold(latin), f"{cyrillic}/{latin}")

    def test_two_soums_of_khuvsgul_do_not_fold_together(self):
        # Цагааннуур and Цагаан-Уур are different places, and collapsing a
        # doubled vowel would make them one name and the join a guess.
        self.assertNotEqual(M.fold("Цагааннуур"), M.fold("Цагаан-Уур"))

    def test_the_generic_word_is_not_part_of_the_name(self):
        self.assertEqual(M.soum_key("Булган сум"), M.soum_key("Булган"))
        self.assertEqual(M.soum_key("Баянгол дүүрэг"), M.soum_key("Баянгол"))

    def test_every_shape_folds_to_itself_within_its_aimag(self):
        geometry = M.shapes()
        self.assertEqual(sum(len(v) for v in geometry.values()), 339)
        # Three aimags each have a soum called Altai, and each match is made
        # inside one aimag, so none of the three is ambiguous.
        altai = [a for a, names in geometry.items() if M.fold("Алтай") in names]
        self.assertEqual(len(altai), 3)


class Rows(unittest.TestCase):
    """A line of glyphs read as a row of figures."""

    def test_a_row_of_percentages_is_read_word_by_word(self):
        line = boxed(("Шүтдэггүй", 62, 110), ("24.5", 150, 170), ("27.1", 200, 220),
                     ("21.8", 250, 270), ("21.6", 300, 320), ("23.7", 350, 370),
                     ("19.7", 400, 420))
        self.assertEqual(M.rows_in(line),
                         [("Шүтдэггүй", [24.5, 27.1, 21.8, 21.6, 23.7, 19.7])])

    def test_a_thousands_space_is_joined_and_a_column_gap_is_not(self):
        # "Бүгд 81 228 57 139 90 465" is six words and three numbers: the
        # space inside a number is three points and the gap between two
        # columns is forty.
        line = boxed(("Бүгд", 62, 88), ("81", 125, 134), ("228", 137, 151),
                     ("57", 192, 202), ("139", 204, 218), ("90", 257, 266),
                     ("465", 269, 283))
        self.assertEqual(M.rows_in(line, 3), [("Бүгд", [81228.0, 57139.0, 90465.0])])

    def test_two_tables_side_by_side_are_two_rows(self):
        line = boxed(("Тариат", 62, 95), ("5.2", 150, 165), ("5.3", 200, 215),
                     ("Өөлд", 300, 330), ("100.0", 350, 375), ("8.4", 400, 415),
                     ("2.0", 430, 445))
        self.assertEqual(M.rows_in(line),
                         [("Тариат", [5.2, 5.3]), ("Өөлд", [100.0, 8.4, 2.0])])

    def test_a_dash_is_nil_and_not_a_missing_figure(self):
        line = boxed(("Ислам", 56, 82), ("0.0", 150, 165), ("-", 200, 205),
                     ("-", 250, 255))
        self.assertEqual(M.rows_in(line), [("Ислам", [0.0, None, None])])

    def test_the_leading_figures_are_this_table_s_row(self):
        # The row carries its neighbour's figures too; the first `width` are
        # this table's and the rest are left to the other run.
        line = boxed(("Хайрхан", 62, 100), ("3.9", 150, 165), ("4.0", 200, 215),
                     ("0.3", 250, 265), ("100.0", 400, 425), ("38.6", 450, 470))
        self.assertEqual(M.rows_in(line, 3), [("Хайрхан", [3.9, 4.0, 0.3])])


class Headers(unittest.TestCase):
    """The columns a table has, against the ones its header line names."""

    def test_a_heading_split_over_three_baselines_is_put_back_together(self):
        page = [
            boxed(("аймгийн", 153, 191), ("Дарь-", 416, 442), ("Уриан-", 453, 485)),
            boxed(("Сум", 62, 81), ("Халх", 203, 226), ("Казах", 242, 268),
                  ("Дөрвөд", 280, 315), ("Буриад", 326, 360)),
            boxed(("харъяат-", 150, 191), ("ганга", 418, 442), ("хай", 469, 485)),
            boxed(("Бүгд", 170, 191)),
        ]
        self.assertEqual(
            M.header_columns(page, 1),
            (["Khalkh", "Kazakh", "Durvud", "Buriad", "Dariganga", "Uriankhai"], True))

    def test_a_header_naming_a_word_that_is_not_a_group_is_refused(self):
        page = [boxed(("Сум", 62, 81), ("Халх", 203, 226), ("Ажиллагчид", 242, 300),
                      ("Дөрвөд", 320, 355))]
        self.assertIsNone(M.header_columns(page, 0))
        self.assertIsNone(M.header_groups(page[0]))


class Shapes(unittest.TestCase):
    """The three ways a book prints the same table, each told by its own
    arithmetic."""

    def test_rows_that_open_at_a_hundred_are_each_soum_s_own_composition(self):
        block = {"Баянхонгор": [100.0, 99.5, None, 0.1, 0.1],
                 "Баацагаан": [100.0, 99.9, None, None, None]}
        self.assertEqual(M.classify(block, [100.0, 99.7, 0.1, 0.1, 0.1], True),
                         "row shares")

    def test_a_unit_line_of_a_hundred_in_every_column_is_the_transpose(self):
        # Each column is one group's distribution over the soums, so it is the
        # columns that add to a hundred and not the rows.
        block = {"Эрдэнэбулган": [22.8, 23.1, 3.2, 42.6],
                 "Батцэнгэл": [77.2, 76.9, 96.8, 57.4]}
        self.assertEqual(M.classify(block, [100.0, 100.0, 100.0, 100.0], True),
                         "column shares")

    def test_whole_numbers_adding_to_the_unit_s_line_are_counts(self):
        block = {"Булган": [12472.0, 12252.0, 4.0],
                 "Баян-Агт": [3273.0, 3265.0, 0.0]}
        total = [15745.0, 15517.0, 4.0]
        self.assertEqual(M.classify(block, total, True), "counts")

    def test_a_block_whose_arithmetic_fits_nothing_is_refused(self):
        block = {"Булган": [12472.0, 3.5, 4.0], "Баян-Агт": [3273.0, 99.0, 0.2]}
        self.assertIsNone(M.classify(block, None, True))


class Checks(unittest.TestCase):
    """What stops a table being written."""

    def table(self, shape, rows, aimag=None, weight=None):
        out = M.Soums()
        out.shape, out.rows = shape, rows
        out.aimag = aimag or {}
        out.weight = weight or {}
        return out

    def test_a_table_one_column_out_of_step_is_refused(self):
        # Sukhbaatar, where the column that is really Dariganga would be read
        # as Zakhchin: the report says Zakhchin is 0.1% of the aimag.
        table = self.table("row shares", {"Асгат": {"Khalkh": 17.3, "Zakhchin": 81.3}},
                           aimag={"Khalkh": 59.6, "Zakhchin": 39.0})
        why = M.check_soums("Sükhbaatar", table, {"Khalkh": 59.6, "Zakhchin": 0.1})
        self.assertIsNotNone(why)
        self.assertIn("Appendix Table 3.6", why)

    def test_a_table_that_agrees_with_the_report_is_kept(self):
        table = self.table("row shares", {"Асгат": {"Khalkh": 17.3, "Dariganga": 81.3}},
                           aimag={"Khalkh": 59.6, "Dariganga": 39.0})
        self.assertIsNone(
            M.check_soums("Sükhbaatar", table, {"Khalkh": 59.6, "Dariganga": 39.0}))

    def test_a_distribution_table_is_checked_against_its_own_first_column(self):
        # Arkhangai prints, beside each group's distribution over the soums,
        # the soum's own share of the aimag; weighting the one by the report's
        # shares has to give the other.
        rows = {"Эрдэнэбулган": {"Khalkh": 23.1, "Uuld": 3.2}}
        report = {"Khalkh": 97.1, "Uuld": 2.3}
        self.assertIsNone(M.check_soums(
            "Arkhangai", self.table("column shares", rows, weight={"Эрдэнэбулган": 22.5}),
            report))
        self.assertIsNotNone(M.check_soums(
            "Arkhangai", self.table("column shares", rows, weight={"Эрдэнэбулган": 60.0}),
            report))


class Composition(unittest.TestCase):
    def test_shares_add_to_exactly_a_hundred(self):
        rows = M.composition({"Khalkh": 91553, "Uuld": 2181, "Durvud": 162,
                              "Bayad": 91, "Other ethnic groups": 267})
        self.assertAlmostEqual(sum(row["pct"] for row in rows), 100.0, places=6)
        self.assertEqual(rows[0]["group"], "Khalkh")

    def test_a_group_under_a_twentieth_of_a_point_goes_to_the_residual(self):
        rows = M.composition({"Khalkh": 100000, "Tsaatan (Dukha)": 10,
                              "Kazakh": 900})
        # The Dukha are folded into the residual, which rounds to nothing and
        # is not written; the Kazakhs, above the floor, are kept.
        self.assertEqual([row["group"] for row in rows], ["Khalkh", "Kazakh"])
        self.assertAlmostEqual(sum(row["pct"] for row in rows), 100.0, places=6)

    def test_religion_is_the_share_who_follow_one_split_by_which(self):
        faith = M.read_religion([[
            boxed(("Шүтдэггүй", 62, 110), ("24.5", 150, 170), ("27.1", 200, 220),
                  ("21.8", 250, 270), ("21.6", 300, 320), ("23.7", 350, 370),
                  ("19.7", 400, 420)),
            boxed(("Шүтдэг", 62, 95), ("75.5", 150, 170), ("72.9", 200, 220),
                  ("78.2", 250, 270), ("78.4", 300, 320), ("76.3", 350, 370),
                  ("80.3", 400, 420)),
            boxed(("Будда", 56, 80), ("97.9", 150, 170), ("98.0", 200, 220),
                  ("97.7", 250, 270), ("98.5", 300, 320), ("98.7", 350, 370),
                  ("98.3", 400, 420)),
            boxed(("Бөө", 56, 71), ("0.9", 150, 165), ("1.0", 200, 215),
                  ("0.9", 250, 265), ("0.5", 300, 315), ("0.4", 350, 365),
                  ("0.6", 400, 415)),
            boxed(("Христ", 56, 79), ("0.9", 150, 165), ("0.7", 200, 215),
                  ("1.1", 250, 265), ("0.9", 300, 315), ("0.8", 350, 365),
                  ("1.0", 400, 415)),
            boxed(("Бусад", 56, 80), ("0.3", 150, 165), ("0.3", 200, 215),
                  ("0.3", 250, 265), ("0.1", 300, 315), ("0.1", 350, 365),
                  ("0.1", 400, 415)),
        ]])
        self.assertIsNotNone(faith)
        self.assertAlmostEqual(faith["No religion"], 21.6, places=3)
        self.assertAlmostEqual(faith["Buddhism"], 78.4 * 98.5 / 100.0, places=3)
        # The reader stops at the first set of religions that adds to a
        # hundred, so a row below it worth a tenth of a point may be left out.
        self.assertAlmostEqual(sum(faith.values()), 100.0, places=0)


@unittest.skipUnless(OUT.exists(), "data/processed/mongolia.json not built")
class Written(unittest.TestCase):
    """What the file says, once it has been built."""

    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(OUT.read_text())
        cls.by_name = {row["name"]: row for row in cls.rows
                       if row["level"] == "admin1"}

    def test_every_aimag_and_every_soum_is_written(self):
        first = [row for row in self.rows if row["level"] == "admin1"]
        second = [row for row in self.rows if row["level"] == "admin2"]
        self.assertEqual(len(first), 22)
        self.assertEqual(len(second), 339)
        self.assertEqual(len({row["id"] for row in self.rows}), len(self.rows))

    def test_every_aimag_carries_the_census_s_ethnic_composition(self):
        for name, row in self.by_name.items():
            self.assertIsInstance(row["ethnicity"], list, name)
            self.assertEqual(row["ethnicity_year"], 2020, name)
            self.assertAlmostEqual(sum(g["pct"] for g in row["ethnicity"]),
                                   100.0, places=6, msg=name)

    def test_bayan_olgii_is_kazakh_and_muslim_and_nowhere_else_is(self):
        kazakh = self.by_name["Bayan-Ölgii"]["ethnicity"][0]
        self.assertEqual(kazakh["group"], "Kazakh")
        self.assertGreater(kazakh["pct"], 85.0)
        muslim = {name: next((g["pct"] for g in row["religion"]
                              if g["group"] == "Islam"), 0.0)
                  for name, row in self.by_name.items()
                  if isinstance(row["religion"], list)}
        self.assertGreater(muslim["Bayan-Ölgii"], 75.0)
        self.assertTrue(all(share < 10.0 for name, share in muslim.items()
                            if name != "Bayan-Ölgii"))

    def test_khovd_is_the_aimag_the_report_describes(self):
        # "Khovd is a home to many ethnicities which consists of Khalkh (28.1
        # percent), Zakhchin (25.3 percent), Kazakh (11.2 percent) ..."
        shares = {g["group"]: g["pct"] for g in self.by_name["Khovd"]["ethnicity"]}
        self.assertEqual(shares["Khalkh"], 28.1)
        self.assertEqual(shares["Zakhchin"], 25.3)
        self.assertEqual(shares["Kazakh"], 11.2)

    def test_every_field_with_no_figure_says_why(self):
        for row in self.rows:
            for field in ("ethnicity", "religion"):
                value = row[field]
                if isinstance(value, dict):
                    self.assertTrue(value.get("note"), f"{row['id']} {field}")
                    self.assertGreater(len(value["note"]), 60, f"{row['id']} {field}")

    def test_a_soum_carries_its_aimag_as_its_parent(self):
        first = {row["id"] for row in self.rows if row["level"] == "admin1"}
        for row in self.rows:
            if row["level"] == "admin2":
                self.assertIn(row["parent"], first, row["id"])


if __name__ == "__main__":
    unittest.main()
