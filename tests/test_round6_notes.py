"""Round 6, notes partition: okrug splits, sub-district reads and stated reasons. No network."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import russia_municipal as rm  # noqa: E402


def okrug(name, total, men, women, parts):
    unit = {"name": name, "total": total, "men": men, "women": women, "towns": [],
            "rural": 0.0, "places": [], "parts": parts}
    unit["stems"] = rm.census_stems(unit)
    return unit


def part(urban, total, men, women, places=(), sub=()):
    return {"urban": urban, "label": "", "total": total, "men": men, "women": women,
            "places": [list(p) for p in places], "sub": [list(s) for s in sub]}


NOVOZYBKOV = okrug("Новозыбковский городской округ", 49379, 22232, 27147, [
    part(True, 38680, 17208, 21472, places=[("г.", "Новозыбков", 38680, 17208, 21472)]),
    part(False, 10699, 5024, 5675)])

VYSHNY = okrug("Вышневолоцкий городской округ", 67163, 29445, 37718, [
    part(True, 50223, 21634, 28589, sub=[("г.", "Вышний Волочек", 45830, 19693, 26137),
                                         ("пгт", "Красномайский", 4393, 1941, 2452)]),
    part(False, 16940, 7811, 9129)])

NAMES = {"t": "Novozybkov", "d": "Novozybkovsky District"}
KINDS = {"t": "city", "d": "district"}


class RussiaOkrugSplitTest(unittest.TestCase):
    def test_the_town_row_goes_to_the_town_and_the_rest_to_the_district(self):
        got = rm.split_okrug(NOVOZYBKOV, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                             NAMES, KINDS)
        self.assertIsInstance(got, tuple)
        town, rest = got
        self.assertEqual((town["total"], town["men"], town["women"]), (38680, 17208, 21472))
        self.assertEqual((rest["total"], rest["men"], rest["women"]), (10699, 5024, 5675))
        self.assertIn("Novozybkovsky District", town["own_note"])
        self.assertIn("Novozybkov,", rest["own_note"])

    def test_an_urban_type_settlement_stays_with_the_district(self):
        town, rest = rm.split_okrug(VYSHNY, "t", "d",
                                    [("t", 45830, "Вышний Волочек", "г.")], NAMES, KINDS)
        self.assertEqual(town["total"], 45830)
        self.assertEqual(rest["total"], 21333)   # 4,393 + 16,940
        self.assertIn("Красномайский (4,393)", rest["own_note"])

    def test_the_town_must_lie_in_the_town_polygon(self):
        got = rm.split_okrug(NOVOZYBKOV, "t", "d", [("d", 38680, "Новозыбков", "г.")],
                             NAMES, KINDS)
        self.assertIsInstance(got, str)
        self.assertIsInstance(rm.split_okrug(NOVOZYBKOV, "t", "d", [], NAMES, KINDS), str)

    def test_another_settlement_in_the_town_polygon_refuses(self):
        got = rm.split_okrug(NOVOZYBKOV, "t", "d",
                             [("t", 38680, "Новозыбков", "г."), ("t", 3100, "Замишево", "село")],
                             NAMES, KINDS)
        self.assertIsInstance(got, str)

    def test_two_towns_refuse(self):
        two = okrug("Орехово-Зуевский городской округ", 300, 140, 160, [
            part(True, 200, 90, 110, sub=[("г.", "А", 120, 50, 70), ("г.", "Б", 80, 40, 40)]),
            part(False, 100, 50, 50)])
        self.assertIsInstance(rm.split_okrug(two, "t", "d", [("t", 120, "А", "г.")],
                                             NAMES, KINDS), str)

    def test_rows_that_do_not_make_the_total_refuse(self):
        bad = okrug("X", 50000, 22232, 27147, NOVOZYBKOV["parts"])
        self.assertIsInstance(rm.split_okrug(bad, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                                             NAMES, KINDS), str)

    def test_a_part_far_from_the_polygons_own_figure_refuses(self):
        # Serpukhov: the rest is 1.33 times what Serpukhovsky District carries.
        got = rm.split_okrug(NOVOZYBKOV, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                             NAMES, KINDS, {"d": 7000})
        self.assertIsInstance(got, str)
        self.assertIn("times", got)
        ok = rm.split_okrug(NOVOZYBKOV, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                            NAMES, KINDS, {"d": 10983, "t": None})
        self.assertIsInstance(ok, tuple)

    def test_the_polygons_must_be_a_towns_and_a_districts(self):
        self.assertIsInstance(rm.split_okrug(NOVOZYBKOV, "t", "d",
                                             [("t", 38680, "Новозыбков", "г.")], NAMES,
                                             {"t": "district", "d": "district"}), str)

    def test_a_spanning_reason_never_names_its_own_polygon(self):
        polygons = ["Ivanteyevka", "городской округ Красноарме", "Pushkinsky District"]
        held = {"городской округ Красноарме": 26492, "Pushkinsky District": 110868}
        text = rm.spanning_reason("Городской округ Пушкинский", 299385, polygons,
                                  "Pushkinsky District", held)
        self.assertIn("this one, Ivanteyevka and городской округ Красноарме.", text)
        self.assertIn("This one holds 110,868", text)
        self.assertNotIn("Pushkinsky District", text)

    @unittest.skipUnless((rm.RAW / "russia" / rm.TABLE).exists(), "workbook not checked in")
    def test_the_workbook_gives_each_okrugs_urban_and_rural_rows(self):
        table = rm.units((rm.RAW / "russia" / rm.TABLE).read_bytes())
        want = {
            "Брянская область": {"Новозыбковский городской округ": (38680, 10699),
                                 "Стародубский муниципальный округ": (17687, 17717)},
            "Ставропольский край": {"Георгиевский городской округ": (63221, 97017)},
            "Тверская область": {"Вышневолоцкий городской округ": (50223, 16940)},
            "Ярославская область": {
                "Городской округ город Переславль-Залесский": (37738, 18844)},
        }
        for subject, okrugs in want.items():
            units = {u["name"]: u for u in table[subject]["units"]}
            for name, (urban, rural) in okrugs.items():
                parts = units[name]["parts"]
                self.assertEqual([p["total"] for p in parts if p["urban"]], [urban], name)
                self.assertEqual([p["total"] for p in parts if not p["urban"]], [rural], name)
        vv = {u["name"]: u for u in table["Тверская область"]["units"]}
        sub = vv["Вышневолоцкий городской округ"]["parts"][0]["sub"]
        self.assertEqual([(s[0], s[1], s[2]) for s in sub],
                         [("г.", "Вышний Волочек", 45830), ("пгт", "Красномайский", 4393)])


if __name__ == "__main__":
    unittest.main()
