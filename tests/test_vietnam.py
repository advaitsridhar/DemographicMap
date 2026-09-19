"""Reading Table 2 of Viet Nam's 2019 results volume: how a row's nine
figures are told apart, how a unit is told from a group, and what refuses."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.fetch_census import vietnam as v  # noqa: E402

# Two pages as pypdf extracts them from the volume (pages 61 and 63,
# shortened): the row label, then nine space-separated figures with a
# space as the thousands separator.
HEAD = ("60\nBiểu - Table 2 (Tiếp theo - Continued)\nĐơn vị: Người - Unit: Persons\n"
        " Dân tộc và đơn vị hành chính\nEthnic group and administration\n"
        "Tổng số - Total Thành thị - Urban Nông thôn - Rural\nChung\nTotal\nNam\nMale\n")
PAGE_A = HEAD + """ Hà Nội 8 053 663 3 991 919 4 061 744 3 962 310 1 942 345 2 019 965 4 091 353 2 049 574 2 041 779
     Kinh  7 945 411 3 942 379 4 003 032 3 923 490 1 925 835 1 997 655 4 021 921 2 016 544 2 005 377
     Tày 19 236 7 636 11 600 13 475 5 446 8 029 5 761 2 190 3 571
     Mường  62 239 30 105 32 134 8 696 3 699 4 997 53 543 26 406 27 137
     Hrê 14 10 4 9 9 - 5 1 4
     Brâu - - - - - - - - -
"""
PAGE_B = HEAD + """     Rơ Măm 1 - 1 1 - 1 - - -
     Người nước ngoài 279 182 97 265 171 94 14 11 3
     Không xác định 26 476 10 010 16 466 18 005 5 000 13 005 8 471 5 010 3 461
"""


class Figures(unittest.TestCase):
    def test_the_arithmetic_splits_the_digit_groups(self):
        self.assertEqual(
            v.figures("8 053 663 3 991 919 4 061 744 3 962 310 1 942 345 2 019 965 "
                      "4 091 353 2 049 574 2 041 779".split()),
            [8053663, 3991919, 4061744, 3962310, 1942345, 2019965, 4091353, 2049574, 2041779])
        self.assertEqual(v.figures("141 72 69 82 45 37 59 27 32".split()),
                         [141, 72, 69, 82, 45, 37, 59, 27, 32])

    def test_a_dash_is_a_zero(self):
        self.assertEqual(v.figures("1 - 1 1 - 1 - - -".split()), [1, 0, 1, 1, 0, 1, 0, 0, 0])
        self.assertEqual(v.figures("- - - - - - - - -".split()), [0] * 9)

    def test_a_row_the_arithmetic_cannot_settle_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            v.figures("1 2 4 1 1 1 1 1 1".split())      # 1 != 2 + 4
        self.assertIn("cannot be read", str(cm.exception))
        with self.assertRaises(SystemExit):
            v.figures("1 1 1 1".split())                # too few figures


class Labels(unittest.TestCase):
    def test_provinces_match_the_shapes_whatever_the_spelling(self):
        self.assertEqual(v.classify("Hoà Bình"), ("province", "Hòa Bình"))
        self.assertEqual(v.classify("TP. Hồ Chí Minh"), ("province", "Ho Chi Minh"))
        self.assertEqual(v.classify("Bà Rịa - Vũng Tàu"), ("province", "Bà Rịa–Vũng Tàu"))
        self.assertEqual(v.classify("Đăk Lăk"), ("province", "Đắk Lắk"))

    def test_the_country_and_the_regions_are_units_of_their_own(self):
        self.assertEqual(v.classify("TOÀN QUỐC")[0], "country")
        self.assertEqual(v.classify("Đồng bằng sông Cửu Long")[0], "region")

    def test_groups_match_across_the_spellings_in_use(self):
        for label in ("Gié Triêng", "Giẻ Triêng", "Gié-Triêng", "Raglay", "Ra Glai",
                      "H'Mông", "Mông", "Bru Vân Kiều", "Ê  Đê", "Không xác định"):
            self.assertEqual(v.classify(v.label_of(label))[0], "group", label)

    def test_an_unknown_label_refuses(self):
        with self.assertRaises(SystemExit) as cm:
            v.classify("Quận Ba Đình")
        self.assertIn("neither a unit nor", str(cm.exception))

    def test_the_sixty_three_provinces_are_listed_once_each(self):
        self.assertEqual(len(v.PROVINCES), 63)
        # Every name has a key of its own, and no two names fold together;
        # an alias may fold onto its own name ("Hoà Bình" and "Hòa Bình").
        self.assertEqual(len({v.fold(n) for n in v.PROVINCES}), 63)
        self.assertEqual(set(v.PROVINCE_KEYS.values()), set(v.PROVINCES))


class Parsing(unittest.TestCase):
    def test_rows_belong_to_the_unit_above_them_across_a_page_break(self):
        units = v.parse([PAGE_A, PAGE_B])
        self.assertEqual([u["name"] for u in units], ["Hà Nội"])
        u = units[0]
        self.assertEqual((u["total"], u["male"], u["female"]), (8053663, 3991919, 4061744))
        self.assertEqual(u["groups"]["Kinh"], 7945411)
        self.assertEqual(u["groups"]["Brâu"], 0)
        self.assertEqual(u["groups"]["Không xác định"], 26476)
        self.assertEqual(len(u["groups"]), 8)

    def test_the_table_s_first_page_heading_is_not_a_row(self):
        # "Biểu - Table 2" ends in a digit; a row ends in nine figures.
        first = PAGE_A.replace("Biểu - Table 2 (Tiếp theo - Continued)", "Biểu - Table 2")
        self.assertEqual([u["name"] for u in v.parse([first])], ["Hà Nội"])
        self.assertIsNone(v.ROW.match("Biểu - Table 2"))
        self.assertIsNone(v.ROW.match("Biểu 2: Dân số theo dân tộc 2"))

    def test_a_page_of_another_table_is_left_alone(self):
        other = PAGE_A.replace("Table 2", "Table 1").replace("Ethnic group", "Administration")
        self.assertEqual(v.parse([other]), [])

    def test_a_group_before_any_unit_refuses(self):
        with self.assertRaises(SystemExit) as cm:
            v.parse([PAGE_B])
        self.assertIn("before any", str(cm.exception))


class Checks(unittest.TestCase):
    def unit(self, name, kind="province", groups=None, total=None):
        groups = groups or {"Kinh": 90, "Tày": 10}
        total = total if total is not None else sum(groups.values())
        return {"kind": kind, "name": name, "label": name, "total": total,
                "male": total // 2, "female": total - total // 2, "groups": groups, "page": 1}

    def test_a_unit_whose_rows_do_not_add_to_its_total_refuses(self):
        full = {f"g{i}": 1 for i in range(54)}
        v.check_units([self.unit("Hà Nội", groups=full)])
        with self.assertRaises(SystemExit) as cm:
            v.check_units([self.unit("Hà Nội", groups=full, total=55)])
        self.assertIn("add to", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            v.check_units([self.unit("Hà Nội")])          # two rows, not 54
        self.assertIn("fewer than the 54", str(cm.exception))

    def test_the_provinces_must_add_to_the_published_national_figures(self):
        share = v.NATIONAL_KINH // 63
        units = [self.unit(name, groups={"Kinh": share, "Tày": v.NATIONAL_TOTAL // 63 - share})
                 for name in v.PROVINCES]
        v.check_national(units)                          # within rounding of 63 shares
        units[0]["groups"]["Kinh"] -= 1_000_000
        with self.assertRaises(SystemExit) as cm:
            v.check_national(units)
        self.assertIn("published national", str(cm.exception))

    def test_a_missing_or_doubled_province_refuses(self):
        units = [self.unit(name) for name in v.PROVINCES][:-1]
        with self.assertRaises(SystemExit) as cm:
            v.check_national(units)
        self.assertIn("missing ['Đồng Tháp']", str(cm.exception))


class Composition(unittest.TestCase):
    def test_shares_add_to_exactly_one_hundred_and_the_small_fold_together(self):
        groups = {"Kinh": 7945411, "Mường": 62239, "Tày": 19236, "Hrê": 14,
                  "Người nước ngoài": 279, "Không xác định": 27}
        total = sum(groups.values())
        rows = v.composition(groups, total)
        self.assertEqual([r["group"] for r in rows],
                         ["Kinh", "Mường", "Tày", "Other ethnic groups"])
        self.assertEqual(rows[-1]["count"], 14 + 279 + 27)
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0, places=6)
        self.assertEqual(sum(r["count"] for r in rows), total)

    def test_largest_remainder(self):
        self.assertEqual(v.whole_hundred([33.33, 33.33, 33.34]), [33.3, 33.3, 33.4])
        self.assertEqual(sum(v.whole_hundred([50.05, 49.95])), 100.0)


class Records(unittest.TestCase):
    def test_a_province_record_carries_counts_a_year_and_its_source(self):
        groups = {f"g{i}": 1 for i in range(53)}
        groups["Kinh"] = 947
        u = {"kind": "province", "name": "Hà Nội", "label": "Hà Nội", "total": 1000,
             "male": 400, "female": 600, "groups": groups, "page": 61}
        region = dict(u, kind="region", name="dongbangsonghong", label="Đồng bằng sông Hồng")
        records = v.build([region, u])
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual((r["id"], r["level"], r["parent"], r["country"]),
                         ("VNM-hà-nội", "admin1", "VNM", "VNM"))
        self.assertIn("Hanoi", r["aliases"])
        self.assertEqual(r["ethnicity_year"], 2019)
        self.assertEqual(r["ethnicity"][0], {"group": "Kinh", "pct": 94.7, "count": 947})
        self.assertEqual(r["population"]["value"], 1000)
        self.assertEqual(r["sex_ratio"]["value"], 1500)
        self.assertEqual({s["field"] for s in r["sources"]}, {"ethnicity", "population", "sex_ratio"})
        self.assertEqual(r["religion"]["status"], "not_available")
        self.assertIn("Table 3 gives it for the country only", r["ethnicity_note"])


if __name__ == "__main__":
    unittest.main()
