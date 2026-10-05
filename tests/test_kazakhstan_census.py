import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import kazakhstan as kz  # noqa: E402
from scripts.fetch_census import kazakhstan_census as kc  # noqa: E402
from scripts.fetch_census.redatam import median_age  # noqa: E402

A1 = [{"id": "R1", "name": "Akmola Region"}, {"id": "R2", "name": "Jambyl Region"},
      {"id": "R3", "name": "Almaty"}, {"id": "R4", "name": "South Kazakhstan Region"},
      {"id": "R5", "name": "Astana"}]
A2 = [{"id": "z", "name": "Zerendinskiy", "parent": "R1"},
      {"id": "a", "name": "Akkol`skiy", "parent": "R1"},
      {"id": "t", "name": "Tselinogradskiy", "parent": "R1"},
      {"id": "q", "name": "Zhualynskiy", "parent": "R2"},
      {"id": "q2", "name": "Zhualy", "parent": "R2"},
      {"id": "c", "name": "Almaty (Alma-Ata)", "parent": "R3"},
      {"id": "s", "name": "Shymkent", "parent": "R4"},
      {"id": "m", "name": "Maktaaral`skiy", "parent": "R4"}]


class Placement(unittest.TestCase):
    def test_spellings_of_one_unit_are_one_key(self):
        self.assertEqual(kz.key("Кокшетау г.а."), kz.key("Кокшетау Г.А."))
        self.assertEqual(kz.key("Кокшетау г.а"), kz.key("город Кокшетау"))
        self.assertEqual(kz.key("Район им.Габита Мусрепова"), kz.key("Район Им. Габита Мусрепова"))
        self.assertEqual(kz.key("Aршалынский район"), kz.key("Аршалынский район"))   # Latin A

    def test_units_land_on_the_polygon_around_them(self):
        placed = kz.place("Akmola Region", ["Зерендинский район", "Кокшетау Г.А.",
                                            "Аккольский район", "Степногорск г.а.",
                                            "Целиноградский район", "г.Косшы"], A1, A2)
        self.assertEqual(sorted(placed["z"]), ["Зерендинский район", "Кокшетау Г.А."])
        self.assertEqual(sorted(placed["a"]), ["Аккольский район", "Степногорск г.а."])
        self.assertEqual(sorted(placed["t"]), ["Целиноградский район", "г.Косшы"])

    def test_a_split_district_goes_back_to_the_drawn_one(self):
        placed = kz.place("South Kazakhstan Region",
                          ["Мактааральский район", "Жетисайский район", "г.Шымкент"], A1, A2)
        self.assertEqual(sorted(placed["m"]), ["Жетисайский район", "Мактааральский район"])
        self.assertEqual(placed["s"], ["г.Шымкент"])

    def test_city_and_empty_polygon(self):
        self.assertEqual(kz.place("Almaty", ["г.Алматы"], A1, A2), {"c": ["г.Алматы"]})
        # The stray Zhualy polygon is allowed to stay empty, and only it.
        self.assertEqual(kz.place("Jambyl Region", ["Жуалынский район"], A1, A2),
                         {"q": ["Жуалынский район"]})

    def test_an_unknown_unit_or_an_empty_polygon_stops(self):
        with self.assertRaises(SystemExit):
            kz.place("Akmola Region", ["Зерендинский район", "Аккольский район",
                                       "Целиноградский район", "Новый район"], A1, A2)
        with self.assertRaises(SystemExit):
            kz.place("Akmola Region", ["Зерендинский район", "Аккольский район"], A1, A2)

    def test_note_names_the_namesake_first(self):
        note = kz.polygon_note("Zerendinskiy", ["Кокшетау Г.А.", "Зерендинский район"])
        self.assertIn("holds Зерендинский район and also Кокшетау Г.А.", note)
        self.assertIsNone(kz.polygon_note("Zerendinskiy", ["Зерендинский район"]))


class TableTwoTwo(unittest.TestCase):
    def test_spaced_thousands_read_whole(self):
        self.assertEqual(kc.split_row("4 899 2 520 2 379 1 059 48 630 22 014 26 616 827"),
                         [4899, 2520, 2379, 1059, 48630, 22014, 26616, 827])
        self.assertEqual(kc.split_row("27 120 13 280 13 840 960 24 808 12 479 12 329 1012"),
                         [27120, 13280, 13840, 960, 24808, 12479, 12329, 1012])

    def test_a_row_that_does_not_add_up_is_not_read(self):
        self.assertIsNone(kc.split_row("27 120 13 280 13 840 960 24 808 12 479 12 328 1012"))

    def test_rows_go_to_their_region_by_totals(self):
        text = ("Content\n2.2 Population by city and district ....... 30\n"
                "1.2 Population change\nUrban population 1 1 0 0 1 1 0 0\n"
                "2.2 Population by city and district\n"
                "Akmola region 1 000 500 500 1000 3 000 1 400 1 600 875\n"
                "   Kokshetau c.d. 400 200 200 1000 2 000 900 1 100 818\n"
                "         Inner district 100 50 50 1000 700 300 400 750\n"
                "   Zerendi district 600 300 300 1000 1 000 500 500 1000\n"
                "Urban population\n"
                "Akmola region 1 1 0 0 1 1 0 0\n")
        rows = kc.table_rows(text)
        self.assertEqual(len(rows), 4)
        regions = {"11": {"total": 3000, "units": [
            {"kato": "111000000", "name": "Кокшетау Г.А.", "total": 2000},
            {"kato": "115600000", "name": "Зерендинский район", "total": 1000}]}}
        sexes = kc.sexes_by_unit(rows, regions)
        self.assertEqual(sexes, {"111000000": (900, 1100), "115600000": (500, 500)})
        regions["11"]["units"].append({"kato": "116000000", "name": "x", "total": 77})
        with self.assertRaises(SystemExit):
            kc.sexes_by_unit(rows, regions)


def sheet11(regions):
    """A sheet 1.1 with the given {name: (men by age, women by age)}."""
    names, kinds, sexes = ["Регионы"], ["Тип местности"], ["Пол"]
    for name in ["Республика Казахстан", *regions]:
        names += [name, None, None, None, None, None, None, None, None]
        for kind in ("Всего", "город", "село"):
            kinds += [kind, None, None]
            sexes += ["Всего", "Мужчины", "Женщины"]
    rows = [("1.1",), tuple(names), tuple(kinds), tuple(sexes)]
    ages = len(next(iter(regions.values()))[0])
    totals = ["Возраст \\ Всего"] + [0] * 9
    for men, women in regions.values():
        totals += [sum(men) + sum(women), sum(men), sum(women)] + [0] * 6
    rows.append(tuple(totals))
    for age in range(ages):
        label = f"{age}+" if age == ages - 1 else str(age)
        row = [label] + [0] * 9
        for men, women in regions.values():
            row += [men[age] + women[age], men[age], women[age]] + [0] * 6
        rows.append(tuple(row))
    return rows


class Sheets(unittest.TestCase):
    def test_sheet_11_by_region_and_sex(self):
        regions = {name: ([1, 2, 3], [1, 1, 1]) for name in
                   ["Акмолинская", "Актюбинская", "Алматинская", "Атырауская",
                    "Западно-Казахстанская", "Жамбылская", "Карагандинская", "Костанайская",
                    "Кызылординская", "Мангистауская", "Павлодарская",
                    "Северо-Казахстанская", "Туркестанская", "Восточно-Казахстанская",
                    "г.Нур-Султан", "г.Алматы", "г.Шымкент"]}
        out = kc.parse_regions(sheet11(regions))
        self.assertEqual(len(out), 17)
        self.assertEqual(out["11"]["men"], Counter({0: 1, 1: 2, 2: 3}))
        self.assertEqual(out["79"]["both"][2], 4)

    def test_sheet_31_and_its_sums(self):
        rows = [("3.1",), ("Уровень", "КАТО", "Наименование\\Возраст", "Всего", 0, 1, "2+")]
        rows.append((0, "000000000", "Республика Казахстан", kc.NATIONAL, 0, 0, kc.NATIONAL))
        localities = kc.parse_localities(rows + [(2, "111000000", "Кокшетау Г.А.", 6, 1, 2, 3)])
        self.assertEqual(localities[1]["ages"], Counter({0: 1, 1: 2, 2: 3}))
        with self.assertRaises(SystemExit):
            kc.parse_localities(rows + [(2, "111000000", "Кокшетау Г.А.", 7, 1, 2, 3)])


class Records(unittest.TestCase):
    def test_a_pooled_polygon_takes_the_pooled_median_and_ratio(self):
        a1 = [{"id": "R1", "name": "Akmola Region"}]
        a2 = [{"id": "z", "name": "Zerendinskiy", "parent": "R1"}]
        old_regions = kc.KATO_REGION
        kc.KATO_REGION = {"11": "Akmola Region"}
        try:
            regions = {"11": {"name": "Акмолинская область", "total": 10,
                              "ages": Counter({10: 4, 40: 6}), "units": [
                                  {"kato": "111000000", "name": "Кокшетау Г.А.", "total": 4,
                                   "ages": Counter({10: 4})},
                                  {"kato": "115600000", "name": "Зерендинский район",
                                   "total": 6, "ages": Counter({40: 6})}]}}
            sexes = {"11": {"both": Counter({10: 4, 40: 6}), "men": Counter({10: 2, 40: 3}),
                            "women": Counter({10: 2, 40: 3})}}
            by_unit = {"111000000": (2, 2), "115600000": (3, 3)}
            out = kc.build(regions, sexes, by_unit, a1, a2)
        finally:
            kc.KATO_REGION = old_regions
        polygon = next(r for r in out if r["level"] == "admin2")
        self.assertEqual(polygon["shape_id"], "z")
        self.assertEqual(polygon["median_age"]["value"], median_age(Counter({10: 4, 40: 6})))
        self.assertEqual(polygon["sex_ratio"]["value"], 100.0)
        self.assertIn("Кокшетау Г.А.", polygon["median_age_note"])
        # Language is a gap that says why, at both levels.
        for row in out:
            self.assertEqual(row["language"]["status"], "not_available")
            self.assertIn("native language", row["language"]["note"])

    def test_the_stray_polygon_says_why_on_every_field_it_answers(self):
        a1 = [{"id": "R2", "name": "Jambyl Region"}]
        a2 = [{"id": "q", "name": "Zhualynskiy", "parent": "R2"},
              {"id": "q2", "name": "Zhualy", "parent": "R2"}]
        old_regions = kc.KATO_REGION
        kc.KATO_REGION = {"31": "Jambyl Region"}
        try:
            regions = {"31": {"name": "Жамбылская область", "total": 6,
                              "ages": Counter({40: 6}), "units": [
                                  {"kato": "314000000", "name": "Жуалынский район",
                                   "total": 6, "ages": Counter({40: 6})}]}}
            sexes = {"31": {"both": Counter({40: 6}), "men": Counter({40: 3}),
                            "women": Counter({40: 3})}}
            out = kc.build(regions, sexes, {"314000000": (3, 3)}, a1, a2)
        finally:
            kc.KATO_REGION = old_regions
        stray = next(r for r in out if r["shape_id"] == "q2")
        for field in ("median_age", "sex_ratio", "language"):
            self.assertIn("second, small polygon", stray[field]["note"])


if __name__ == "__main__":
    unittest.main()
