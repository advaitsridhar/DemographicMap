"""Panama's districts on REDATAM: later districts folded back, keys as panama_census writes them."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import panama_redatam as pr  # noqa: E402


def table(name, rows):
    return {"area": "x", "name": name, "title": "3.EDAD", "rows": rows,
            "total": sum(n for _, n in rows), "na": None}


PROVINCES = {"01": {"name": "BOCAS DEL TORO"}, "08": {"name": "PANAMÁ"},
             "12": {"name": "COMARCA NGÄBE BUGLÉ"}}


class Districts(unittest.TestCase):
    def test_a_district_made_since_2010_is_counted_with_the_one_it_came_from(self):
        ages = {"0102": table("CHANGUINOLA", [("10", 3), ("30", 2)]),
                "0104": table("ALMIRANTE", [("20", 4), ("No declarada", 1)])}
        sexes = {code: {"total": t["total"]} for code, t in ages.items()}
        units = pr.merged(ages, sexes, PROVINCES)
        self.assertEqual(list(units), [("bocasdeltoro", "changuinola")])
        unit = units[("bocasdeltoro", "changuinola")]
        self.assertEqual(unit["people"], 10)
        self.assertEqual(unit["unstated"], 1)
        self.assertEqual(unit["ages"], {10: 3, 30: 2, 20: 4})
        self.assertEqual(unit["parts"], ["CHANGUINOLA", "ALMIRANTE"])

    def test_the_bases_spelling_of_calovebora_reaches_kusapin(self):
        ages = {"1207": table("KUSAPÍN", [("5", 1)]),
                "1209": table("SANTA CATALINA O CALOVÉVORA (BLEDESHIA)", [("6", 1)])}
        sexes = {code: {"total": t["total"]} for code, t in ages.items()}
        self.assertEqual(list(pr.merged(ages, sexes, PROVINCES)),
                         [("comarcangabebugle", "kusapin")])

    def test_taboga_is_left_out_as_panama_census_leaves_it(self):
        ages = {"0811": table("TABOGA", [("40", 1)])}
        self.assertEqual(pr.merged(ages, {"0811": {"total": 1}}, PROVINCES), {})

    def test_age_and_sex_must_count_the_same_people(self):
        ages = {"0102": table("CHANGUINOLA", [("10", 3)])}
        with self.assertRaises(SystemExit):
            pr.merged(ages, {"0102": {"total": 4}}, PROVINCES)

    def test_a_district_under_no_province_stops_the_run(self):
        with self.assertRaises(SystemExit):
            pr.keyed(PROVINCES, "0999", "NOWHERE")


if __name__ == "__main__":
    unittest.main()
