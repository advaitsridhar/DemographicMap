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

    def test_a_central_district_is_named_after_its_province(self):
        admin1 = [{"id": "P1", "name": "Karabük"}, {"id": "P2", "name": "Kırıkkale"},
                  {"id": "P3", "name": "Afyonkarahisar"}, {"id": "P4", "name": "Kütahya"}]
        admin2 = [{"id": "A", "name": "Merkez", "parent": "P1"},
                  {"id": "B", "name": "Kırıkkale (merkez)", "parent": "P2"},
                  {"id": "C", "name": "Karakeçeli", "parent": "P2"},
                  {"id": "D", "name": "Afyonkarahisar (Merkez İlçe)", "parent": "P3"},
                  {"id": "E", "name": "Gediz Merkez", "parent": "P4"},
                  {"id": "F", "name": "Kütahya merkez", "parent": "P4"}]
        rows = [{"name": "Karabuk", "province": "Karabuk", "pcode": "1"},
                {"name": "Kirikkale", "province": "Kirikkale", "pcode": "2"},
                {"name": "Karakecili", "province": "Kirikkale", "pcode": "3"},
                {"name": "Afyonkarahisar", "province": "Afyonkarahisar", "pcode": "4"},
                {"name": "Gediz", "province": "Kutahya", "pcode": "5"},
                {"name": "Kutahya", "province": "Kutahya", "pcode": "6"}]
        got, left_rows, left_shapes = t.bind(rows, admin1, admin2)
        self.assertEqual(got, {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E", "6": "F"})
        self.assertEqual((left_rows, left_shapes), ([], []))

    def test_a_polygon_named_like_a_row_keeps_its_own_name(self):
        admin1 = [{"id": "P1", "name": "Denizli"}]
        admin2 = [{"id": "A", "name": "Merkezefendi", "parent": "P1"},
                  {"id": "B", "name": "Denizli merkez", "parent": "P1"}]
        rows = [{"name": "Merkezefendi", "province": "Denizli", "pcode": "1"},
                {"name": "Denizli", "province": "Denizli", "pcode": "2"}]
        got, _, _ = t.bind(rows, admin1, admin2)
        self.assertEqual(got, {"1": "A", "2": "B"})


class BodyRowsTest(unittest.TestCase):
    def table(self, *rows):
        return {"label": "x.csv", "rows": list(rows)}

    def test_rows_of_bare_commas_are_passed_over(self):
        good = {"year": "2022", "ADM1_EN": "Adana", "type": "Resident population in Türkiye"}
        blank = {"year": "", "ADM1_EN": "", "type": ""}
        kept, empty = t.body_rows(self.table(good, blank, blank), "ADM1_EN")
        self.assertEqual((kept, empty), ([good], 2))

    def test_another_population_or_year_or_a_nameless_row_stops_the_run(self):
        for bad in ({"year": "2022", "ADM1_EN": "Adana", "type": "Syrians under temporary"},
                    {"year": "2021", "ADM1_EN": "Adana", "type": "Resident population"},
                    {"year": "2022", "ADM1_EN": "", "type": "Resident population"}):
            with self.assertRaises(SystemExit):
                t.body_rows(self.table(bad), "ADM1_EN")


if __name__ == "__main__":
    unittest.main()
