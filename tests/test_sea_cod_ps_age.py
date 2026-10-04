"""COD-PS medians and sex ratios for Southeast Asia: binding and figures.

No network and no tiles: the drawn units and the tiles' answer are stood in.
"""

import unittest
from unittest import mock

from scripts.fetch_census import sea_cod_ps_age as s
from scripts.fetch_census.cod_ps_age import age_columns

ADMIN1 = [{"id": "CM", "name": "Chiang Mai Province", "aliases": ["Chiang Mai"]},
          {"id": "LP", "name": "Lampang Province"}]
ADMIN2 = [{"id": "A", "name": "Mae Tha", "parent": "CM", "point": [98.9, 18.8]},
          {"id": "B", "name": "Mae Tha", "parent": "LP", "point": [99.6, 18.2]},
          {"id": "C", "name": "Ko Kha", "parent": "LP", "point": [99.4, 18.2]}]
BANDS = [(lo, lo + 4) for lo in range(0, 80, 5)]


def columns():
    cols = ["ADM1_EN", "ADM2_EN", "F_TL", "M_TL", "T_TL"]
    for sex in "FMT":
        cols += [f"{sex}_{lo:02d}_{hi:02d}" for lo, hi in BANDS] + [f"{sex}_80Plus"]
    return cols


def row(prov, name, per_band_f=10, per_band_m=11):
    out = {"ADM1_EN": prov, "ADM2_EN": name}
    n = len(BANDS) + 1
    out.update({"F_TL": per_band_f * n, "M_TL": per_band_m * n,
                "T_TL": (per_band_f + per_band_m) * n})
    for sex, v in (("F", per_band_f), ("M", per_band_m), ("T", per_band_f + per_band_m)):
        for lo, hi in BANDS:
            out[f"{sex}_{lo:02d}_{hi:02d}"] = v
        out[f"{sex}_80Plus"] = v
    return out


def fake_drawn(iso3, level):
    return ADMIN1 if level == "admin1" else ADMIN2


class BindTest(unittest.TestCase):
    def bind(self, rows, where):
        with mock.patch.object(s, "drawn", fake_drawn), \
                mock.patch.object(s, "locate", return_value=where):
            return s.bind_rows("THA", "admin2", rows, "ADM2_EN", "ADM1_EN")

    def test_shared_names_go_by_parent(self):
        rows = [row("Chiang Mai", "Mae Tha"), row("Lampang", "Mae Tha"), row("Lampang", "Ko Kha")]
        bound, left, unbound = self.bind(rows, {"A": "CM", "B": "LP"})
        self.assertEqual({i: u["id"] for i, u in bound.items()}, {0: "A", 1: "B", 2: "C"})
        self.assertEqual((left, unbound), ([], []))

    def test_a_shared_name_whose_polygon_lies_elsewhere_is_left(self):
        rows = [row("Chiang Mai", "Mae Tha"), row("Lampang", "Mae Tha")]
        bound, left, unbound = self.bind(rows, {"A": "LP", "B": "LP"})
        self.assertEqual([u["id"] for u in bound.values()], ["B"])
        self.assertEqual(len(left), 1)

    def test_a_unique_name_binds_whatever_its_parent_is_called(self):
        bound, _, _ = self.bind([row("Lampang Province (old)", "Ko Kha")], {})
        self.assertEqual(bound[0]["id"], "C")


class SpellingAndSeatTest(unittest.TestCase):
    def test_a_parent_spelt_the_datasets_way(self):
        admin1 = [{"id": "CH", "name": "Champasak"}, {"id": "LP", "name": "Luang Prabang"}]
        admin2 = [{"id": "P1", "name": "Phonthong", "parent": "CH", "point": [105.8, 15.0]},
                  {"id": "P2", "name": "Phonthong", "parent": "LP", "point": [102.2, 19.9]}]
        rows = [{"ADM1_EN": "Champasack", "ADM2_EN": "Phonthong"},
                {"ADM1_EN": "Louangphabang", "ADM2_EN": "Phonthong"}]
        with mock.patch.object(s, "drawn", lambda iso3, level: admin1 if level == "admin1"
                               else admin2), \
                mock.patch.object(s, "locate", return_value={"P1": "CH", "P2": "LP"}):
            bound, left, _ = s.bind_rows("LAO", "admin2", rows, "ADM2_EN", "ADM1_EN")
        self.assertEqual({i: u["id"] for i, u in bound.items()}, {0: "P1", 1: "P2"})

    def test_a_district_keeps_its_own_spelling(self):
        admin1 = [{"id": "CH", "name": "Champasak"}]
        admin2 = [{"id": "D", "name": "Champasack", "parent": "CH", "point": [105.9, 14.9]}]
        rows = [{"ADM1_EN": "Champasack", "ADM2_EN": "Champasack"}]
        with mock.patch.object(s, "drawn", lambda iso3, level: admin1 if level == "admin1"
                               else admin2), \
                mock.patch.object(s, "locate", return_value={}):
            bound, left, _ = s.bind_rows("LAO", "admin2", rows, "ADM2_EN", "ADM1_EN")
        self.assertEqual(bound[0]["id"], "D")

    def test_twins_placed_by_their_seats(self):
        admin1 = [{"id": "AY", "name": "Phra Nakhon Si Ayutthaya Province"}]
        admin2 = [{"id": "E", "name": "Bang Sai", "parent": "AY", "point": [100.47, 14.22]},
                  {"id": "W", "name": "Bang Sai", "parent": "AY", "point": [100.30, 14.30]}]
        rows = [{"ADM1_EN": "Phra Nakhon Si Ayutthaya", "ADM2_EN": "Bang Sai (1)",
                 "ADM2_PCODE": "TH1404"},
                {"ADM1_EN": "Phra Nakhon Si Ayutthaya", "ADM2_EN": "Bang Sai (2)",
                 "ADM2_PCODE": "TH1413"}]

        def where(points, level, iso3):
            if level == "admin2":
                return {"TH1404": "E", "TH1413": "W"}
            return {k: "AY" for k in points}
        with mock.patch.object(s, "drawn", lambda iso3, level: admin1 if level == "admin1"
                               else admin2), \
                mock.patch.object(s, "locate", side_effect=where):
            bound, left, unbound = s.bind_rows("THA", "admin2", rows, "ADM2_EN", "ADM1_EN")
        self.assertEqual({i: u["id"] for i, u in bound.items()}, {0: "E", 1: "W"})
        self.assertEqual((left, unbound), ([], []))


class RecordsTest(unittest.TestCase):
    def test_median_and_ratio(self):
        cols_ = columns()
        table = {"label": "tha_admpop_2023.xlsx tha_admpop_adm2_2023_", "level": "2",
                 "columns": cols_, "rows": [row("Lampang", "Ko Kha")],
                 "method": "Projections from 2017 to 2022 by the United States Bureau of the "
                           "Census"}
        with mock.patch.object(s, "drawn", fake_drawn), \
                mock.patch.object(s, "locate", return_value={}):
            recs = s.level_records("THA", "cod-ps-tha", "CC BY-IGO", "2", 2023, table,
                                   age_columns(cols_))
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["shape_id"], "C")
        self.assertEqual(r["sex_ratio"]["value"], 110.0)
        self.assertEqual(r["sex_ratio"]["unit"], "males_per_100_females")
        # 17 equal groups, 16 closed: the middle person is 8.5 groups in, at 42.5.
        self.assertEqual(r["median_age"]["value"], 42.5)
        self.assertIn("projection", r["median_age_note"])
        self.assertIn("United States Bureau of the Census", r["median_age_note"])

    def test_an_implausible_ratio_leaves_the_unit_out(self):
        cols_ = columns()
        table = {"label": "x adm2_", "level": "2", "columns": cols_,
                 "rows": [row("Lampang", "Ko Kha", per_band_f=20, per_band_m=9)], "method": ""}
        with mock.patch.object(s, "drawn", fake_drawn), \
                mock.patch.object(s, "locate", return_value={}):
            recs = s.level_records("THA", "cod-ps-tha", "CC BY-IGO", "2", 2023, table,
                                   age_columns(cols_))
        self.assertEqual(recs, [])


if __name__ == "__main__":
    unittest.main()
