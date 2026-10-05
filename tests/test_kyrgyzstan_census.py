import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import kyrgyzstan_census as kg  # noqa: E402


def thousands(n):
    return f"{n:,}".replace(",", " ")


def age_block(name, rows, head="Все население", dash=False):
    """A territory's block of the age-group table as pypdf reads it."""
    total = [sum(r[i] for r in rows) for i in range(3)]
    lines = [f"  {name}"]
    if dash:
        lines += ["    Все население -",
                  f"    cельское население {' '.join(map(thousands, total))} 100 100"]
    else:
        lines.append(f"    {head} {' '.join(map(thousands, total))} 100 100")
    lines.append("    в том числе в возрасте, лет:")
    for label, (b, m, w) in zip(kg.GROUP_LABELS, rows):
        figs = " ".join("-" if v == 0 else thousands(v) for v in (b, m, w))
        lines.append(f"        {label} {figs} 1,0 1,1")
    lines += ["       Из общей численности-", "       моложе трудоспособного 9 5 4 1,0 1,0",
              "       Средний возраст населения, лет 30 29 31  -  -"]
    return "\n".join(lines)


def rows_for(scale):
    """21 age groups, men and women equal, the oldest empty."""
    out = [(2 * (scale + i) * 100, (scale + i) * 100, (scale + i) * 100) for i in range(20)]
    return out + [(0, 0, 0)]


AGES = "\n".join([
    "29", "мужчины женщины мужчины женщины",
    age_block("Чуйская область", [tuple(a + b for a, b in zip(x, y))
                                  for x, y in zip(rows_for(1), rows_for(3))]),
    "    Городское население 1 000 500 500 100 100",
    "    в том числе в возрасте, лет:",
    "        0-4 10 5 5 1,0 1,0",
    "Продолжение табл. 2.8",
    age_block("г.Токмок", rows_for(1)),
    age_block("Аламудунский район", rows_for(3), dash=True),
])

ETHNIC_TEXT = """55
оба пола мужчины женщины
Чуйская область
   Все население 1 000 500 500 100
в том числе:
кыргызы 900 450 450 90,0
русские 100 50 50 10,0
   Городское население 300 150 150 100
    в том числе:
кыргызы 250 125 125 83,3
русские 50 25 25 16,7
г. Токмок
   Все население 400 200 200 100
в том числе:
кыргызы 350 175 175 87,5
народы Индии и
Пакистана 50 30 20 12,5
Аламудунский район
   Все население 600 300 300 100
в том числе:
кыргызы 550 275 275 91,7
русские 49 25 25 8,2
Численность населения, человек Численность лиц
данной националь-
ности в процентах
ко всему населению
"""

LANGUAGE_TEXT = """73
язык своей
национальности кыргызский русский другие
Чуйская область
   Все население 1 000 940 20 30 10
в том числе:
кыргызы 900 890  - 8 2
русские 100 50 20  - 30
 г. Токмок
   Все население 400 380 5 10 5
в том числе:
кыргызы 350 345  - 4 1
 Аламудунский район 600 560 15 20 5
в том числе:
кыргызы 550 545  - 4 1
русские 49 15 15  - 19
"""


class Reading(unittest.TestCase):
    def test_spaced_thousands_are_read_by_what_adds_up(self):
        self.assertEqual(kg.sexes("1 056 758 525 054 531 704".split(), "x"),
                         (1056758, 525054, 531704))
        self.assertEqual(kg.sexes("7 - 7".split(), "x"), (7, 0, 7))
        with self.assertRaises(SystemExit):
            kg.sexes("288 140 128".split(), "x")
        self.assertEqual(kg.sexes("288 140 128".split(), "x", strict=False), (288, 140, 128))

    def test_names_fold(self):
        self.assertEqual(kg.key("г. Токмок"), "г.токмок")
        self.assertEqual(kg.key("  Аламудунский  район"), "аламудунский район")
        self.assertTrue(kg.is_territory("Кара-Сууский район"))
        self.assertFalse(kg.is_territory("кыргызы"))
        # One place under the spellings the books use for it.
        self.assertEqual(kg.key("Кара-Сууйский район"), "кара-сууский район")
        self.assertEqual(kg.key("Джалал-Абадская область"), "жалал-абадская область")
        self.assertEqual(kg.key("г.Джалал - Абад"), "г.жалал-абад")

    def test_a_share_split_at_its_comma_is_put_together(self):
        self.assertEqual(kg.tidy("55 18 37 0 ,0 0,0".split()), ["55", "18", "37", "0,0", "0,0"])
        self.assertEqual(kg.tidy("55 18 37 0, 0 0,0".split()), ["55", "18", "37", "0,0", "0,0"])
        self.assertEqual(kg.tidy("1 056 758".split()), ["1", "056", "758"])


class Tables(unittest.TestCase):
    def test_age_blocks_by_territory(self):
        blocks = kg.parse_groups(AGES, "Chuy")
        self.assertEqual(sorted(blocks), ["аламудунский район", "г.токмок", "чуйская область"])
        tokmok = blocks["г.токмок"]
        self.assertEqual(tokmok["groups"][0], (200, 100, 100))
        self.assertEqual(tokmok["groups"][-1], (0, 0, 0))
        # "Все население -" with the whole on the (all-rural) next row.
        self.assertEqual(blocks["аламудунский район"]["total"][0],
                         sum(r[0] for r in rows_for(3)))

    def test_an_age_block_that_does_not_add_up_stops(self):
        with self.assertRaises(SystemExit):
            kg.parse_groups(AGES.replace("0-4 200 100 100", "0-4 202 101 101"), "Chuy")

    def test_the_oldest_row_with_a_split_share(self):
        text = age_block("Таласская область", rows_for(1)[:20] + [(9, 3, 6)])
        text = text.replace("100 лет и старше 9 3 6 1,0 1,1", "100 лет и старше 9 3 6 0 ,0 0,0")
        self.assertIn("0 ,0", text)
        block = kg.parse_groups(text, "Talas")["таласская область"]
        self.assertEqual(block["groups"][-1], (9, 3, 6))

    def test_a_15_19_row_after_the_15_row(self):
        rows = rows_for(1)
        # Naryn prints "15-19" holding the 15-year-olds again ...
        again = age_block("Нарынская область", rows).replace(
            f"16-19 {' '.join(map(thousands, rows[4]))}",
            f"15-19 {' '.join(thousands(a + b) for a, b in zip(rows[3], rows[4]))}")
        self.assertIn("15-19", again)
        block = kg.parse_groups(again, "Naryn")["нарынская область"]
        self.assertEqual(block["groups"][4], rows[4])
        # ... and a "15-19" that is 16-19 misprinted is read as printed.
        misprint = age_block("Нарынская область", rows).replace("16-19 ", "15-19 ")
        block = kg.parse_groups(misprint, "Naryn")["нарынская область"]
        self.assertEqual(block["groups"][4], rows[4])

    def test_ethnic_groups_and_a_wrapped_name(self):
        ethnic = kg.parse_ethnic(ETHNIC_TEXT, "Chuy")
        self.assertEqual(ethnic["г.токмок"]["groups"]["People of India and Pakistan"], 50)
        self.assertEqual(ethnic["чуйская область"]["groups"], Counter(Kyrgyz=900, Russian=100))
        # Alamudun's printed groups miss one person: counted as other.
        self.assertEqual(ethnic["аламудунский район"]["groups"]["Other"], 1)

    def test_an_unknown_group_stops(self):
        with self.assertRaises(SystemExit):
            kg.parse_ethnic(ETHNIC_TEXT.replace("русские 100", "марсиане 100"), "Chuy")

    def test_native_languages(self):
        ethnic = kg.parse_ethnic(ETHNIC_TEXT, "Chuy")
        language = kg.parse_language(LANGUAGE_TEXT, "Chuy", ethnic)
        self.assertEqual(language["чуйская область"]["columns"], ["own", "Kyrgyz", "Russian", None])
        region = kg.languages(language["чуйская область"])
        # Kyrgyz: 890 Kyrgyz + 20 others naming Kyrgyz; Russian: 50 + 30.
        self.assertEqual(region, Counter({"Kyrgyz": 910, "Russian": 80, "Other languages": 10}))
        # Alamudun's name and figures share a line; its unlisted people's
        # own language (560 - 545 - 15 = 0) and the "other" column (5).
        alamudun = kg.languages(language["аламудунский район"])
        self.assertEqual(sum(alamudun.values()), 600)
        self.assertEqual(alamudun["Kyrgyz"], 545 + 15)

    def test_page_kinds(self):
        pages = ["СОДЕРЖАНИЕ 2.8. Численность ... 29",
                 "data 2.7. Численность постоянного городского и сельского населения по полу и "
                 "возрасту",
                 "Продолжение табл. 2.7 more",
                 "rows 2.8. Численность постоянного городского и сельского населения\n"
                 "по полу, возрастным группам и территории",
                 "продолжение табл.2.8 rows",
                 "Численность лиц данной национальности в процентах",
                 "язык своей национальности кыргызский русский другие",
                 "Продолжение табл. 4.1"]
        self.assertEqual(kg.page_kinds(pages), [None, "years", "years", "groups", "groups",
                                                "ethnic", "language", None])

    def test_page_kinds_from_the_rows_when_the_title_is_split(self):
        # Issyk-Kul: "по полу, возрастным группам" printed before the rows,
        # "2.8. Численность ..." after them; then a continuation page, and
        # table 3.3 (ethnic groups by age), whose rows look alike.
        rows = " в том числе в возрасте, лет: 0-4 59 638 30 356 29 282 Средний возраст 28,6"
        pages = ["3.3. Распределение постоянного городского и сельского населения отдельных "
                 "этнических групп по возрастным группам",
                 "по полу, возрастным группам и территории Иссык-Кульская область" + rows
                 + " 2.8. Численность постоянного городского и сельского населения в том числе",
                 "Продолжение таблицы 2.8 Тонский район 90-99 10 5 5",
                 "Продолжение табл. 3.3 кыргызы узбеки Кара-Сууский район" + rows]
        self.assertEqual(kg.page_kinds(pages), [None, "groups", "groups", None])


def unit(total, groups, ethnic, languages):
    return {"total": total, "groups": groups, "ethnic": Counter(ethnic),
            "languages": Counter(languages)}


def book(region, units, years=None):
    """A read book from {unit: (total, ethnic)}: every unit 40-year-olds."""
    ethnic, groups, language = {}, {}, {}
    for name, ((b, m, w), groups_) in units.items():
        ethnic[name] = {"total": (b, m, w), "groups": Counter(groups_)}
        ages = [(0, 0, 0)] * len(kg.GROUPS)
        ages[9] = (b, m, w)
        groups[name] = {"total": (b, m, w), "groups": ages}
        language[name] = {"total": [b, b, 0, 0, 0], "columns": ["own", "Kyrgyz", "Russian", None],
                          "groups": {g: [n, n, 0, 0, 0] for g, n in groups_.items()}}
    return {"region": region, "units": [u for u in units if u in kg.PLACE], "ethnic": ethnic,
            "groups": groups, "language": language, "years": years}


A1 = [{"id": "C", "name": "Chuy Region"}, {"id": "N", "name": "Naryn Region"},
      {"id": "J", "name": "Jalal-Abad Region"}]
A2 = [{"id": "a", "name": "Alamudun", "parent": "C"},
      {"id": "t", "name": "City of Tomok", "parent": "C"},
      {"id": "n", "name": "Naryn", "parent": "N"},
      {"id": "g", "name": "Toguz-Toro", "parent": "N"},
      {"id": "s", "name": "Suzak", "parent": "J"}]


class Records(unittest.TestCase):
    def setUp(self):
        self.books = {
            "Chuy": book("чуйская область", {
                "чуйская область": ((300, 150, 150), {"Kyrgyz": 300}),
                "аламудунский район": ((200, 100, 100), {"Kyrgyz": 200}),
                "г.токмок": ((100, 50, 50), {"Kyrgyz": 100})},
                years={"total": (300, 150, 150), "both": Counter({40: 300})}),
            "Bishkek": book("г.бишкек", {"г.бишкек": ((1000, 400, 600), {"Russian": 1000})},
                            years={"total": (1000, 400, 600), "both": Counter({30: 1000})}),
            "Naryn": book("нарынская область", {
                "нарынская область": ((50, 25, 25), {"Kyrgyz": 50}),
                "нарынский район": ((50, 25, 25), {"Kyrgyz": 50})},
                years={"total": (50, 25, 25), "both": Counter({40: 50})}),
            "Jalal-Abad": book("жалал-абадская область", {
                "жалал-абадская область": ((90, 45, 45), {"Uzbek": 90}),
                "тогуз-тороуский район": ((20, 10, 10), {"Kyrgyz": 20}),
                "сузакский район": ((70, 35, 35), {"Uzbek": 70})},
                years={"total": (90, 45, 45), "both": Counter({40: 90})}),
        }
        self.out = {r["shape_id"]: r for r in kg.build(self.books, A1, A2)}

    def test_a_city_is_added_to_the_district_that_holds_it(self):
        alamudun = self.out["a"]
        self.assertEqual(alamudun["population"]["value"], 1200)
        self.assertEqual(alamudun["sex_ratio"]["value"], round(100 * 500 / 700, 1))
        self.assertIn("г.бишкек", alamudun["population_note"])
        self.assertEqual(alamudun["ethnicity"][0]["group"], "Russian")
        self.assertEqual(alamudun["religion"]["status"], "not_available")

    def test_regions_carry_what_their_polygons_hold(self):
        chuy = self.out["C"]
        self.assertEqual(chuy["population"]["value"], 1300)
        self.assertIn("the city of Bishkek", chuy["population_note"])
        # Both books are whole: the single years are pooled.
        self.assertIn("single years", chuy["median_age_note"])
        naryn = self.out["N"]
        self.assertEqual(naryn["population"]["value"], 70)
        self.assertIn("Toguz-Toro", naryn["population_note"])
        self.assertIn("age group", naryn["median_age_note"])
        jalal = self.out["J"]
        self.assertEqual(jalal["population"]["value"], 70)
        self.assertIn("except Toguz-Toro", jalal["population_note"])

    def test_a_drawn_district_with_no_unit_stops(self):
        with self.assertRaises(SystemExit):
            kg.build(self.books, A1, A2 + [{"id": "x", "name": "Chatkal", "parent": "J"}])


if __name__ == "__main__":
    unittest.main()
