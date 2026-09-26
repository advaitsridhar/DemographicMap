"""Tests for the Dominican census reader: ONE's Volume III layout, no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import dominican_census as dc  # noqa: E402


def block(label, total, men, women, ages, ratio=True):
    """An area row and its age rows, all urban, as Cuadro 2 lays them out."""
    row = [label, total, men, women, total, men, women, 0, 0, 0]
    if ratio:
        row.append(100 * men / women)
    rows = [row]
    for age, (m, w) in ages.items():
        rows.append([age, m + w, m, w, m + w, m, w, 0, 0, 0, 100 * m / w if w else 0])
    return rows


AGES_A = {"Menos de 1": (1, 1), "1-4": (4, 4), "5-9": (5, 5), "100 o más": (1, 1),
          "No declarado": (1, 0)}
AGES_B = {"Menos de 1": (2, 2), "1-4": (3, 3), "5-9": (5, 5), "100 o más": (0, 0),
          "No declarado": (0, 0)}


def cuadro_2(provinces=32):
    """A country of one region and ``provinces`` provinces of one municipio and one part."""
    rows = [["Cuadro 2"], ["REPÚBLICA DOMINICANA: ..."]]
    per = {k: (a[0] + b[0], a[1] + b[1]) for (k, a), b in zip(AGES_A.items(), AGES_B.values())}
    men, women = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
    n = provinces
    rows += block("Total", n * (men + women), n * men, n * women,
                  {k: (n * m, n * w) for k, (m, w) in per.items()})
    rows += block("Región Ozama", n * (men + women), n * men, n * women,
                  {k: (n * m, n * w) for k, (m, w) in per.items()})
    for i in range(n):
        name = "Distrito nacional" if i == 0 else f"Provincia P{i}"
        rows += block(name, men + women, men, women, per)
        a_m, a_w = sum(v[0] for v in AGES_A.values()), sum(v[1] for v in AGES_A.values())
        b_m, b_w = sum(v[0] for v in AGES_B.values()), sum(v[1] for v in AGES_B.values())
        rows += block(f"Municipio A{i}", a_m + a_w, a_m, a_w, AGES_A)
        rows += block(f"A{i}", a_m + a_w, a_m, a_w, AGES_A)
        rows += block(f"Municipio B{i}", b_m + b_w, b_m, b_w, AGES_B)
    return rows


class LayoutTest(unittest.TestCase):
    def test_age_rows(self):
        self.assertEqual(dc.band("Menos de 1"), (0, 0))
        self.assertEqual(dc.band("12-14."), (12, 14))
        self.assertEqual(dc.band("100 y más"), (100, None))
        self.assertIsNone(dc.band("No declarado"))
        self.assertEqual(dc.kind("Distrito nacional"), "province")
        self.assertEqual(dc.kind("Municipio Santo Domingo Este"), "municipio")
        self.assertEqual(dc.kind("Santo Domingo Este", "Municipio Santo Domingo Este"), "part")
        self.assertEqual(dc.kind("San Luis (D.M.)", "Municipio Santo Domingo Este"), "part")
        self.assertEqual(dc.kind("Espaillat", "Municipio Pedro Brand"), "province")

    def test_tree_reads_municipios_under_their_province(self):
        rows = cuadro_2()
        national = rows[2][1]
        provinces = dc.tree(dc.areas(rows, 10), 9, "test", national)
        self.assertEqual(len(provinces), 32)
        self.assertEqual([dc.bare(a["label"]) for a in provinces["P1"]["municipios"]],
                         ["A1", "B1"])
        self.assertIn("Distrito nacional", provinces)

    def test_municipios_that_miss_their_province_stop_the_run(self):
        rows = cuadro_2()
        national = rows[2][1]
        for row in rows:
            if row[0] == "Municipio B3":
                for i in (1, 2, 4, 5):
                    row[i] += 5
        with self.assertRaises(SystemExit):
            dc.tree(dc.areas(rows, 10), 9, "test", national)

    def test_a_rounding_of_one_is_read_and_logged(self):
        # Santo Domingo Este's age rows make one man fewer than its row.
        rows = cuadro_2()
        national = rows[2][1]
        for row in rows:
            if row[0] == "Municipio B3":
                for i in (1, 2, 4, 5):
                    row[i] += 1
        dc.tree(dc.areas(rows, 10), 9, "test", national)
        self.assertTrue(any("Municipio B3's age rows (by 1)" in d for d in dc.DISCREPANCIES))

    def test_age_figures_leave_undeclared_ages_out_of_the_median(self):
        area = dc.areas(block("Municipio A", 23, 12, 11, AGES_A), 10)[0]
        out = dc.age_figures(area)
        self.assertEqual(out["population"]["value"], 23)
        self.assertEqual(out["sex_ratio"]["value"], round(1000 * 12 / 11))
        self.assertIn("the 1 people whose age was not declared", out["median_age_note"])
        # 22 people with an age: the middle one is the 11th, in 1-4.
        self.assertEqual(out["median_age"]["value"], round(1 + (11 - 2) / 8 * 4, 1))

    def test_a_printed_ratio_that_disagrees_stops_the_run(self):
        rows = block("Municipio A", 23, 12, 11, AGES_A)
        rows[0][10] = 90.0
        with self.assertRaises(SystemExit):
            dc.age_figures(dc.areas(rows, 10)[0])

    def test_perception_shares_leave_out_no_answer(self):
        header = [*dc.PERCEIVED, dc.UNANSWERED]
        area = {"label": "Provincia X", "values": [100, 10, 30, 5, 5, 30, 0, 15, 0, 5], "ages": []}
        out = dc.perception_fields(area, header)
        got = {g["group"]: g["pct"] for g in out["ethnicity"]}
        self.assertEqual(got["Indio (Dominican Republic)"], round(100 * 30 / 95, 1))
        self.assertNotIn(dc.UNANSWERED, got)
        self.assertIn("of whom 5 are", out["ethnicity_note"])

    def test_perception_answers_that_miss_the_total_stop_the_run(self):
        header = [*dc.PERCEIVED, dc.UNANSWERED]
        area = {"label": "Provincia X", "values": [101, 10, 30, 5, 5, 30, 0, 15, 0, 5], "ages": []}
        with self.assertRaises(SystemExit):
            dc.perception_fields(area, header)


if __name__ == "__main__":
    unittest.main()
