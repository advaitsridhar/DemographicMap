"""Viet Nam: religion by province from the 2009 census's Tables 7 and 1.

No network: the two tables' pages are written here as the volume's text reads.
"""

import unittest
import unittest.mock

from scripts.fetch_census import vietnam_religion as v


def fmt(n):
    return "-" if n == 0 else f"{n:,}".replace(",", ".")


def row(label, total, male, urban, urban_male):
    rural, rural_male = total - urban, male - urban_male
    cells = [total, male, total - male, urban, urban_male, urban - urban_male,
             rural, rural_male, rural - rural_male]
    return f"{label} " + " ".join(fmt(c) for c in cells)


def pages(hanoi_catholics=150, extra_line=None):
    """Two provinces, Hà Nội (01) and Hà Giang (02), in one region and the country."""
    table1 = "\n".join([
        "Biểu - Table 1",
        row("TOÀN QUỐC - ENTIRE COUNTRY", 3000, 1500, 1000, 500),
        "V1 Trung du và miền núi phía Bắc",
        row("Northern Midlands and Mountains", 3000, 1500, 1000, 500),
        row("01 Hà Nội", 2000, 1000, 1000, 500),
        row("02 Hà Giang", 1000, 500, 0, 0),
    ])
    hanoi = [row("01 Phật Giáo - Buddish", 100, 50, 60, 30),
             row("02 Công Giáo - Catholics", hanoi_catholics, 75, 40, 20),
             row("06 Minh Sư Đạo", 1, 1, 0, 0),
             row("Không xác định tôn giáo - Not stated", 2, 1, 0, 0)]
    hagiang = [row("08 Tin Lành - Protestantism", 300, 150, 0, 0)]
    region = [row("01 Phật Giáo - Buddish", 100, 50, 60, 30),
              row("02 Công Giáo - Catholics", 150, 75, 40, 20),
              row("06 Minh Sư Đạo", 1, 1, 0, 0),
              row("08 Tin Lành - Protestantism", 300, 150, 0, 0),
              row("Không xác định tôn giáo - Not stated", 2, 1, 0, 0)]
    table7 = "\n".join(
        ["Biểu - Table 7", "TOÀN QUỐC - ENTIRE COUNTRY", row("Tổng số - Total", 553, 277, 100, 50)]
        + region
        + ["V1. TRUNG DU VÀ MIỀN NÚI PHÍA BẮC - NORTHERN MIDLANDS AND MOUNTAINS",
           row("       Tổng số - Total", 553, 277, 100, 50)] + region
        + [row("1. HÀ NỘI", 103 + hanoi_catholics, 127, 100, 50)] + hanoi
        + [row("2. HÀ GIANG", 300, 150, 0, 0)] + hagiang
        + ([extra_line] if extra_line else []))
    return ["front matter", table1, "Biểu - Table 10 other", table7]


ADMIN1 = [{"id": "HN", "name": "Hà Nội"}, {"id": "HG", "name": "Hà Giang"},
          {"id": "CD", "name": "Côn Đảo"}]


class ReligionTest(unittest.TestCase):
    def run_all(self, pp):
        with unittest.mock.patch.multiple(v, NATIONAL_POPULATION=3000, NATIONAL_FOLLOWERS=553,
                                          PROVINCE_COUNT=2, REGION_COUNT=1):
            _, pops = v.read_populations(pp)
            units = v.read_religions(pp)
            v.check(units, pops)
            return {r["shape_id"]: r for r in v.build(units, pops, ADMIN1)}

    def test_no_religion_is_population_less_followers(self):
        recs = self.run_all(pages())
        hanoi = {g["group"]: g["count"] for g in recs["HN"]["religion"]}
        self.assertEqual(hanoi["No religion"], 2000 - 253)
        self.assertEqual(hanoi["Catholicism"], 150)
        self.assertEqual(hanoi["Not stated"], 2)
        self.assertEqual(hanoi["Other religions"], 1)            # Minh Su Dao
        self.assertIn("Minh Su Dao 1", recs["HN"]["religion_note"])
        self.assertEqual(round(sum(g["pct"] for g in recs["HN"]["religion"]), 1), 100.0)
        self.assertEqual(recs["HN"]["religion_year"], 2009)
        hagiang = {g["group"]: g["pct"] for g in recs["HG"]["religion"]}
        self.assertEqual(hagiang, {"No religion": 70.0, "Protestantism": 30.0})
        # Côn Đảo is no province: it says so, and takes nothing.
        self.assertEqual(recs["CD"]["religion"]["status"], "not_available")

    def test_religions_that_miss_the_total_refuse(self):
        with self.assertRaises(SystemExit):
            self.run_all(pages(hanoi_catholics=151))

    def test_a_row_whose_sexes_do_not_add_refuses(self):
        with self.assertRaises(SystemExit):
            v.numbers("10 6 5 0 0 0 10 6 5", "test")

    def test_a_code_under_another_religion_refuses(self):
        bad = pages(extra_line=row("04 Phật Giáo - Buddish", 1, 1, 0, 0))
        with self.assertRaises(SystemExit):
            self.run_all(bad)


if __name__ == "__main__":
    unittest.main()
