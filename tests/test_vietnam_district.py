"""Viet Nam: district populations and sex ratios, province medians, 2019 census.

No network and no tiles: Table 1 is built here as the PDF's text lines, and
the map's admin1 tiles are stood in for by an empty location.
"""

import unittest
from unittest import mock

from scripts.fetch_census import vietnam_district as vd


def nine(total_m, total_f, urban_m, urban_f):
    """A row's nine figures as the PDF prints them: whole, urban, rural x T/M/F."""
    rural_m, rural_f = total_m - urban_m, total_f - urban_f
    return " ".join(str(n) for n in (total_m + total_f, total_m, total_f,
                                     urban_m + urban_f, urban_m, urban_f,
                                     rural_m + rural_f, rural_m, rural_f))


def table1_page(lines):
    return "\n".join(["Biểu 1 - Table 1", "Dân số chia theo thành thị, nông thôn", "", *lines])


HAU_GIANG = [
    "HẬU GIANG " + nine(150, 160, 50, 60),
    "Thị xã - Town Long Mỹ " + nine(50, 60, 50, 60),
    "Huyện - District Long Mỹ " + nine(60, 50, 0, 0),
    "Thành phố - City",
    "Vị Thanh " + nine(40, 50, 0, 0),
]


class Table1Test(unittest.TestCase):
    def test_districts_under_their_province(self):
        rows, provinces, _ = vd.parse_table1([table1_page(HAU_GIANG)])
        self.assertEqual(provinces["Hậu Giang"][:3], [310, 150, 160])
        self.assertEqual([(r["type"], r["name"]) for r in rows],
                         [("Town", "Long Mỹ"), ("District", "Long Mỹ"), ("City", "Vị Thanh")])
        self.assertEqual(rows[2]["n"][:3], [90, 40, 50])

    def test_a_numbered_quarter_takes_its_number(self):
        rows, _, _ = vd.parse_table1([table1_page([
            "HỒ CHÍ MINH " + nine(10, 10, 10, 10),
            "Quận - Quarter 1 " + nine(10, 10, 10, 10)])])
        self.assertEqual(rows[0]["name"], "Quận 1")

    def test_an_untyped_row_refuses(self):
        with self.assertRaises(SystemExit):
            vd.parse_table1([table1_page(HAU_GIANG + ["Somewhere " + nine(1, 1, 0, 0)])])


def row(prov, kind, name, men=10, women=10):
    return {"province": prov, "type": kind, "name": name, "n": [men + women, men, women]}


ADMIN1 = [{"id": "HG", "name": "Hậu Giang"}, {"id": "CT", "name": "Cần Thơ"},
          {"id": "HP", "name": "Hải Phòng"}, {"id": "HD", "name": "Hải Dương"},
          {"id": "BD", "name": "Bình Định"}]


def shape(sid, name, parent):
    return {"id": sid, "name": name, "parent": parent, "point": [0, 0]}


class BindTest(unittest.TestCase):
    def bind(self, rows, admin2, joined=None, placed=None):
        with mock.patch.object(vd, "locate", return_value={}), \
                mock.patch.object(vd, "JOINED", joined or {}), \
                mock.patch.object(vd, "PLACED", placed or {}):
            return vd.bind(rows, ADMIN1, admin2)

    def test_a_divided_district_is_joined_on_its_old_polygon(self):
        rows = [row("Hậu Giang", "District", "Long Mỹ", 60, 50),
                row("Hậu Giang", "Town", "Long Mỹ", 50, 60)]
        bound, left_c, left_s = self.bind(
            rows, [shape("LM", "Long My", "HG")],
            joined={("Hậu Giang", "longmy"): [("District", "Long Mỹ"), ("Town", "Long Mỹ")]})
        self.assertEqual(len(bound["LM"]), 2)
        self.assertEqual((left_c, left_s), ([], []))
        rec = vd.district_records(bound, [shape("LM", "Long My", "HG")])[0]
        self.assertEqual(rec["population"]["value"], 220)
        self.assertEqual(rec["sex_ratio"]["value"], 100.0)
        self.assertIn("drawn before the census divided it", rec["population_note"])

    def test_a_shared_name_goes_by_province(self):
        rows = [row("Hải Phòng", "District", "An Lão"), row("Bình Định", "District", "An Lão")]
        admin2 = [shape("A1", "An Lao", "HD"), shape("A2", "An Lao", "BD")]
        # Filed under Hải Dương, the first polygon binds to nothing by its parent...
        bound, left_c, left_s = self.bind(rows, admin2)
        self.assertEqual(bound["A2"][0]["province"], "Bình Định")
        self.assertEqual(len(left_c), 1)
        # ...until it is declared.
        placed = {("Hải Phòng", "District", "An Lão"): ("An Lao", "Hải Dương")}
        bound, left_c, left_s = self.bind(rows, admin2, placed=placed)
        self.assertEqual(bound["A1"][0]["province"], "Hải Phòng")
        self.assertEqual((left_c, left_s), ([], []))

    def test_a_placement_under_a_province_with_that_district_refuses(self):
        rows = [row("Hải Phòng", "District", "An Lão"), row("Hải Dương", "District", "An Lão")]
        placed = {("Hải Phòng", "District", "An Lão"): ("An Lao", "Hải Dương")}
        with self.assertRaises(SystemExit):
            self.bind(rows, [shape("A1", "An Lao", "HD"), shape("A3", "An Lao", "HP")],
                      placed=placed)

    def test_the_declarations_name_real_census_rows(self):
        names = {(p, k, vd.key(n)) for (p, k, n) in vd.PLACED}
        self.assertEqual(len(names), len(vd.PLACED))
        for (prov, _), parts in vd.JOINED.items():
            self.assertGreaterEqual(len(parts), 2, prov)


if __name__ == "__main__":
    unittest.main()
