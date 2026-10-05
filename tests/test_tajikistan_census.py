import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import tajikistan_census as tj  # noqa: E402

HEADER = """ ҲАЙАТИ СИННУ СОЛӢ, ҶИНСӢ ВА ҲОЛАТИ АҚДИ НИКОҲИ АҲОЛИИ ҶУМҲУРИИ ТОҶИКИСТОН
НАСЕЛЕНИЕ РЕСПУБЛИКИ ТАДЖИКИСТАН ПО ПОЛУ, ВОЗРАСТУ И СОСТОЯНИЮ В БРАКЕ
          Агентство по статистике при Президенте Республики Таджикистан, 2022
196
 мардҳо
мужчины
занҳо
женщины
"""

# Table 5 as pypdf reads it: the Tajik name on its own line(s), the Russian
# name with the figures, then the unit's urban and rural rows.
SEXES = HEADER + """Ҷумҳурии Тоҷикистон
Республика Таджикистан
Ҳамаи аҳолӣ
Все население 117667 113009 960,4
аҳолии шаҳр
городское население 1000 1000 1000,0
Вилояти Мухтори
Кӯҳистони Бадахшон
Горно - Бадахшанская
Автономная  Область
Ҳамаи аҳолӣ
Все население 116257 111659 960,4
аз он ҷумла:
в том числе:
шаҳри Хоруғ
город Хорог 15724 15048 957,0
ноҳияи Шуғнон
Шугнанский район 100533 96611 961,0
аҳолии деҳот
сельское население 100533 96611 961,0
Вилояти Суғд
Согдийская область
Ҳамаи аҳолӣ
Все население    300  280 933,3
шаҳри Хуҷанд
город Худжанд 100 95 950,0
ноҳияи Кӯҳистони
мастчоҳ
К ухистони
матчохский
 район 50 45 900,0
ноҳияи Мастчоҳ
Матчинский район 150 140 933,3
Вилояти Хатлон
Хатлонская область
Ҳамаи аҳолӣ
Все население 410 400 975,6
шаҳри Левакант -
ҳамагӣ
город Левакант - всего 100 100 1000,0
аҳолии шаҳр
городское население 40 41 1025,0
ноҳияи
М.С.А.Ҳамадонӣ
район
М.С.А.Хамадони 300 290 966,7
ноҳияи Ҷ. Балхӣ
""" + HEADER + """район Дж. Балхи 10 10 1000,0
Шаҳри Душанбе
Город Душанбе 500 480 960,0
Шаҳру ноҳияҳои тобеи
ҷумҳурӣ
Города и районы
республиканского
подчинения
Ҳамаи аҳолӣ
Все население 200 190 950,0
шаҳри Турсунзода -
ҳамагӣ
город Турсунзаде -
всего 120 115 958,3
      ноҳияи Сангвор
Сангворский район 80 75 937,5
"""


def block(heading, rows, label="Городское и сельское\nнаселение"):
    """A table 1 block: the 2010 columns are filler, the 2020 ones are read."""
    lines = [heading] if heading else []
    total = [sum(r[i] for r in rows.values()) for i in (0, 1)]
    lines.append(f"{label} 1 1 0 {total[0] + total[1]} {total[0]} {total[1]}")
    for name, (men, women) in rows.items():
        lines.append(f"{name}……….… 1 1 0 {men + women} {men} {women}")
    return "\n".join(lines)


def ages(m0, m1, m2, m3):
    return {"до 1 года": m0, "1 года": m1, "2 лет": m2, "3 лет и старше": m3}


AGES = "\n".join([
    HEADER,
    block("Ҷумҳурии Тоҷикистон - Республика Таджикистан",
          ages((100, 93), (96, 95), (91, 90), (200, 208))),
    block("Вилояти Мухтори Кӯҳистони Бадахшон - Горно-Бадахшанская автономная область",
          ages((10, 9), (10, 10), (9, 9), (20, 22))),
    block("Вилояти Суғд - Согдийская область", ages((20, 18), (19, 19), (18, 18), (40, 41))),
    # An urban block after the whole: read and checked, not used.
    block(None, {"до 1 года": (5, 5), "1 года": (5, 5), "2 лет": (5, 5)},
          label="Городское население"),
    "0 - 4 лет 1 1 0 999 500 499",
    block("Вилояти Хатлон - Хатлонская область", ages((30, 28), (29, 29), (28, 27), (60, 62))),
    # Dushanbe has no rural people and prints its urban block alone.
    block("ш. Душанбе - г. Душанбе", ages((15, 14), (14, 14), (13, 13), (30, 31)),
          label="Городское население"),
    block("Шаҳру ноҳияҳои тобеи ҷумҳурӣ - Районы республиканского подчинения",
          ages((25, 24), (24, 23), (23, 23), (50, 52))),
])


class Sexes(unittest.TestCase):
    def setUp(self):
        self.totals, self.units = tj.parse_sexes(SEXES)

    def test_regions_and_dushanbe(self):
        self.assertEqual(self.totals["Dushanbe"], (500, 480))
        self.assertEqual(self.totals["national"], (117667, 113009))
        self.assertEqual(self.totals["Gorno-Badakhshan Autonomous Region"], (116257, 111659))

    def test_names_run_over_lines_and_pages(self):
        self.assertEqual([u[0] for u in self.units["Sughd Region"]],
                         ["шаҳри Хуҷанд", "ноҳияи Кӯҳистони мастчоҳ", "ноҳияи Мастчоҳ"])
        self.assertEqual([u[0] for u in self.units["Khatlon Region"]],
                         ["шаҳри Левакант - ҳамагӣ", "ноҳияи М.С.А.Ҳамадонӣ", "ноҳияи Ҷ. Балхӣ"])
        self.assertEqual([u[0] for u in self.units["Districts of Republican Subordination"]],
                         ["шаҳри Турсунзода - ҳамагӣ", "ноҳияи Сангвор"])

    def test_units_take_the_polygons_the_map_draws(self):
        self.assertEqual(tj.unit_label("ноҳияи Кӯҳистони мастчоҳ"), "Kuhistoni Mastchoh District")
        self.assertEqual(tj.unit_label("ноҳияи Мастчоҳ"), "Mastchoh District")
        self.assertEqual(tj.unit_label("ноҳияи М.С.А.Ҳамадонӣ"), "Hamadoni District")
        self.assertEqual(tj.unit_label("ноҳияи Ҷ. Балхӣ"), "Rumi District")
        self.assertEqual(tj.unit_label("шаҳри Левакант - ҳамагӣ"), "Sarband District")
        self.assertEqual(tj.unit_label("ноҳияи К ушониён"), "Bokhtar District")
        with self.assertRaises(SystemExit):
            tj.unit_label("ноҳияи Нестӣ")

    def test_units_that_do_not_make_their_region_stop(self):
        with self.assertRaises(SystemExit):
            tj.parse_sexes(SEXES.replace("Матчинский район 150 140 933,3",
                                         "Матчинский район 151 141 933,8"))

    def test_a_ratio_that_disagrees_stops(self):
        with self.assertRaises(SystemExit):
            tj.parse_sexes(SEXES.replace("город Худжанд 100 95 950,0", "город Худжанд 100 95 960,0"))


class Ages(unittest.TestCase):
    def test_single_years_by_region(self):
        out = tj.parse_ages(AGES)
        self.assertEqual(sorted(out), sorted(list(tj.REGIONS) + ["national"]))
        sughd = out["Sughd Region"]
        self.assertEqual(sughd["total"], (193, 97, 96))
        self.assertEqual(sughd["ages"], Counter({0: 38, 1: 38, 2: 36, 3: 81}))
        self.assertEqual(out["Dushanbe"]["total"], (144, 72, 72))

    def test_regions_must_make_the_republic(self):
        with self.assertRaises(SystemExit):
            tj.parse_ages(AGES.replace("2 лет……….… 1 1 0 18 9 9", "2 лет……….… 1 1 0 19 10 9")
                          .replace("население 1 1 0 99 49 50", "население 1 1 0 100 50 50"))

    def test_a_missing_year_stops(self):
        with self.assertRaises(SystemExit):
            tj.parse_ages(AGES.replace("1 года……….… 1 1 0 20 10 10\n", ""))


A1 = [{"id": f"R{i}", "name": name} for i, name in enumerate(tj.REGIONS)]
IDS = {u["name"]: u["id"] for u in A1}
A2 = [
    {"id": "s1", "name": "Shughnon District", "parent": IDS["Gorno-Badakhshan Autonomous Region"]},
    {"id": "g1", "name": "Ghafurov District", "parent": IDS["Sughd Region"]},
    {"id": "g2", "name": "Kuhistoni Mastchoh District", "parent": IDS["Sughd Region"]},
    {"id": "g3", "name": "Mastchoh District", "parent": IDS["Sughd Region"]},
    {"id": "k1", "name": "Sarband District", "parent": IDS["Khatlon Region"]},
    {"id": "k2", "name": "Hamadoni District", "parent": IDS["Khatlon Region"]},
    {"id": "k3", "name": "Rumi District", "parent": IDS["Khatlon Region"]},
    {"id": "d1", "name": "Tursunzoda District",
     "parent": IDS["Districts of Republican Subordination"]},
    {"id": "d2", "name": "Tavildara District",
     "parent": IDS["Districts of Republican Subordination"]},
]


def fake_ages(totals):
    """Half of each region aged 20, half 40, so a region's median is 21.0."""
    return {region: {"total": (m + w, m, w),
                     "ages": Counter({20: (m + w) // 2, 40: m + w - (m + w) // 2})}
            for region, (m, w) in totals.items()}


class Records(unittest.TestCase):
    def setUp(self):
        self.totals, self.units = tj.parse_sexes(SEXES)

    def test_records_bind_by_shape_and_sum_what_one_polygon_holds(self):
        out = tj.build(fake_ages(self.totals), self.totals, self.units, A1, A2)
        by_shape = {r["shape_id"]: r for r in out}
        shughnon = by_shape["s1"]
        self.assertEqual(shughnon["population"]["value"], 15724 + 15048 + 100533 + 96611)
        self.assertEqual(shughnon["sex_ratio"]["value"],
                         round(100 * (15724 + 100533) / (15048 + 96611), 1))
        self.assertIn("holds", shughnon["population_note"])
        self.assertEqual(shughnon["median_age"]["status"], "not_available")
        gbao = by_shape[IDS["Gorno-Badakhshan Autonomous Region"]]
        self.assertEqual(gbao["level"], "admin1")
        self.assertEqual(gbao["median_age"]["value"], 21.0)
        self.assertEqual(gbao["sex_ratio"]["value"], 104.1)
        self.assertEqual(by_shape["k3"]["name"], "Rumi District")
        self.assertEqual(by_shape["k3"]["population"]["value"], 20)
        for row in (gbao, shughnon):
            self.assertIn("nationality or language", row["ethnicity"]["note"])
            self.assertIn("religion", row["religion"]["note"])

    def test_a_drawn_polygon_left_without_a_unit_stops(self):
        extra = A2 + [{"id": "x", "name": "Vanj District",
                       "parent": IDS["Gorno-Badakhshan Autonomous Region"]}]
        with self.assertRaises(SystemExit):
            tj.build(fake_ages(self.totals), self.totals, self.units, A1, extra)

    def test_table_one_and_table_five_must_agree(self):
        ages = fake_ages(self.totals)
        ages["Dushanbe"]["total"] = (981, 501, 480)
        with self.assertRaises(SystemExit):
            tj.build(ages, self.totals, self.units, A1, A2)


if __name__ == "__main__":
    unittest.main()
