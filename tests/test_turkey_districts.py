"""Tests for Turkey's district ages and sexes from the register, no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import cod_ps_age, turkey_districts as t  # noqa: E402

COLUMNS = (["ADM1_EN", "ADM2_EN", "ADM2_PCODE", "F_TL", "M_TL", "T_TL"]
           + [f"{s}_{a:02d}_{a + 4:02d}" for s in "FM" for a in range(0, 90, 5)]
           + ["F_90Plus", "M_90Plus"])


def row(women, men, ages_f, ages_m, **names):
    out = {"F_TL": str(women), "M_TL": str(men), "T_TL": str(women + men), **names}
    for i, a in enumerate(range(0, 90, 5)):
        out[f"F_{a:02d}_{a + 4:02d}"] = str(ages_f[i])
        out[f"M_{a:02d}_{a + 4:02d}"] = str(ages_m[i])
    out["F_90Plus"], out["M_90Plus"] = str(ages_f[-1]), str(ages_m[-1])
    return out


class FoldTest(unittest.TestCase):
    def test_dotless_and_dotted_i_meet(self):
        self.assertEqual(t.fold("Acıgöl"), t.fold("ACIGÖL"))
        self.assertEqual(t.fold("İnegöl"), "inegol")


class FiguresTest(unittest.TestCase):
    def setUp(self):
        self.cols = cod_ps_age.age_columns(COLUMNS)

    def test_a_district_gives_its_median_and_sexes(self):
        ages_f = [10] * 18 + [0]
        ages_m = [10] * 18 + [0]
        got = t.figures(row(180, 180, ages_f, ages_m), self.cols, "X")
        self.assertEqual((got["total"], got["women"], got["men"]), (360, 180, 180))
        self.assertEqual(got["median"], 45.0)

    def test_sexes_that_do_not_make_the_total_stop_the_run(self):
        bad = row(180, 180, [10] * 18 + [0], [10] * 18 + [0])
        bad["T_TL"] = "400"
        with self.assertRaises(SystemExit):
            t.figures(bad, self.cols, "X")


class BindTest(unittest.TestCase):
    def test_by_name_within_the_province_one_to_one(self):
        admin1 = [{"id": "P1", "name": "Çanakkale"}, {"id": "P2", "name": "Kırşehir"}]
        admin2 = [{"id": "A", "name": "Imbros", "parent": "P1"},
                  {"id": "B", "name": "Merkez", "parent": "P2"},
                  {"id": "C", "name": "Bayramiç", "parent": "P1"}]
        rows = [{"name": "Gökçeada", "province": "Çanakkale", "pcode": "1"},
                {"name": "Bayramiç", "province": "Çanakkale", "pcode": "2"},
                {"name": "Bayramiç", "province": "Kırşehir", "pcode": "3"}]
        got, left_rows, left_shapes = t.bind(rows, admin1, admin2)
        self.assertEqual(got, {"1": "A", "2": "C"})
        self.assertEqual(len(left_rows), 1)
        self.assertEqual(left_shapes, ["Merkez (P2)"])


if __name__ == "__main__":
    unittest.main()
