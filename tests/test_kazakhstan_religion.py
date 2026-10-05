import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import kazakhstan_religion as kr  # noqa: E402

TEXT = """Содержание
1.6   Население районов по вероисповеданию .....................111
1.5 Население по вероисповеданию и отдельным группам возрастов
Всего100 52,5 40,6 0,0 0,0 0,0 6,2 0,6
1.6 Население районов по вероисповеданию
человек
Все
население
из них указавшие:Отказались
указатьислам христианство иудаизм буддизм другое неверующие
Оба пола
Всего по области34221 15385 16366 4 2 4 2170 290
Астраханский район 27419 12266 13377424 1591 175
Егиндыкольский
район 6802 3119 2989000 5 7 9 1 1 5
Агентство Республики Казахстан по статистике 1 1 3
Продолжение
проценты
Всего по области100 45,0 47,8 0,0 0,0 0,0 6,3 0,8
Астраханский район 100 44,7 48,8 0,0 0,0 0,0 5,8 0,6
Егиндыкольский район 100 45,9 43,9 0,0 0,0 0,0 8,5 1,7
Продолжение
человек
Мужчины
Всего по области1 1 0 0 0 0 0 0
2. ОБРАЗОВАТЕЛЬНЫЙ УРОВЕНЬ НАСЕЛЕНИЯ
Астраханский район 1 1 0 0 0 0 0 0
"""

A1 = [{"id": "R", "name": "Akmola Region"}]
A2 = [{"id": "a", "name": "Astrakhansiy", "parent": "R"},
      {"id": "e", "name": "Egindykol`skiy", "parent": "R"}]


class Reading(unittest.TestCase):
    def test_glyph_names_decode(self):
        self.assertEqual(kr.decode("/g570/g612/g614/g3/g20/g19"), "Акм 10")

    def test_glued_and_spread_digits_are_read_against_the_shares(self):
        self.assertEqual(kr.counts("27419 12266 13377424 1591 175",
                                   [44.7, 48.8, 0.0, 0.0, 0.0, 5.8, 0.6]),
                         [27419, 12266, 13377, 4, 2, 4, 1591, 175])
        self.assertEqual(kr.counts("6802 3119 2989000 5 7 9 1 1 5",
                                   [45.9, 43.9, 0.0, 0.0, 0.0, 8.5, 1.7]),
                         [6802, 3119, 2989, 0, 0, 0, 579, 115])

    def test_a_run_that_cannot_make_its_total_is_not_read(self):
        self.assertIsNone(kr.counts("6802 3119 2989000 5 7 9 1 1 6",
                                    [45.9, 43.9, 0.0, 0.0, 0.0, 8.5, 1.7]))
        # Shares that disagree with every split leave nothing to read either.
        self.assertIsNone(kr.counts("6802 3119 2989000 5 7 9 1 1 5",
                                    [40.9, 48.9, 0.0, 0.0, 0.0, 8.5, 1.7]))

    def test_percentages_glued_or_not(self):
        self.assertEqual(kr.percentages("100 44,7 48,8 0,0 0,0 0,0 5,8 0,6"),
                         [44.7, 48.8, 0.0, 0.0, 0.0, 5.8, 0.6])
        self.assertEqual(kr.percentages("10044,748,80,00,00,05,80,6"),
                         [44.7, 48.8, 0.0, 0.0, 0.0, 5.8, 0.6])


AMBIGUOUS = """1.6 Население районов по вероисповеданию
человек
Оба пола
Всего по области46937 46808 85 7 4 3 2 28
Бейнеуский район 46937 46808 85743 2 28
проценты
Всего по области100 99,7 0,2 0,0 0,0 0,0 0,0 0,0
Бейнеуский район 100 99,7 0,2 0,0 0,0 0,0 0,0 0,0
человек
Мужчины
Всего по области23000 22950 40 3 2 1 1 3
Бейнеуский район 23000 22950 40 3 2 1 1 3
проценты
Всего по области100 99,8 0,2 0,0 0,0 0,0 0,0 0,0
Бейнеуский район 100 99,8 0,2 0,0 0,0 0,0 0,0 0,0
человек
Женщины
Всего по области23937 23858 45 4 2 2 1 25
Бейнеуский район 23937 23858 45 4 2 2 1 25
проценты
Всего по области100 99,7 0,2 0,0 0,0 0,0 0,0 0,1
Бейнеуский район 100 99,7 0,2 0,0 0,0 0,0 0,0 0,1
"""


class Table(unittest.TestCase):
    def test_two_readings_are_settled_by_the_men_and_women(self):
        self.assertEqual(len(kr.readings("46937 46808 85743 2 28",
                                         [99.7, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0])), 2)
        rows = kr.unit_counts(kr.section(AMBIGUOUS), "Mangystau Region")
        self.assertEqual(rows["Бейнеуский район"], [46937, 46808, 85, 7, 4, 3, 2, 28])

    def test_the_table_reads_whole_and_binds(self):
        rows = kr.unit_counts(kr.section(TEXT), "Akmola Region")
        total, units = kr.region_rows(rows, "Akmola Region")
        self.assertEqual(total[0], 34221)
        self.assertEqual(units["Егиндыкольский район"][6], 579)
        out = kr.records("Akmola Region", units, A1, A2)
        by_shape = {r["shape_id"]: r for r in out}
        islam = next(b for b in by_shape["a"]["religion"] if b["group"] == "Islam")
        self.assertEqual(islam, {"group": "Islam", "pct": 44.7, "count": 12266})
        self.assertEqual(by_shape["e"]["religion_year"], 2009)

    def test_units_that_do_not_make_the_region_stop(self):
        text = TEXT.replace("Всего по области34221", "Всего по области34222").replace(
            "по области100 45,0", "по области100 45,0")
        with self.assertRaises(SystemExit):
            rows = kr.unit_counts(kr.section(text), "Akmola Region")
            kr.region_rows(rows, "Akmola Region")


if __name__ == "__main__":
    unittest.main()
