"""Argentina's 2022 census: INDEC's sheets read, and departments bound to the right polygons."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import argentina_census as ac  # noqa: E402


def age_sheet(counts: dict[int, tuple[int, int]], open_from: int, open_counts: tuple[int, int]):
    """A sex-by-single-year sheet as INDEC lays it out: groups, then their years."""
    women = sum(w for w, _ in counts.values()) + open_counts[0]
    men = sum(m for _, m in counts.values()) + open_counts[1]
    rows = [["Censo Nacional"], ["Cuadro 4.6.1. Provincia de Córdoba, departamento Calamuchita."],
            ["Edad", "Total de población", "Sexo registrado al nacer"],
            [None, None, "Mujer / Femenino", "Varón / Masculino"],
            ["Total", women + men, women, men, 107]]
    for low in range(0, open_from, 5):
        years = range(low, min(low + 5, open_from))
        w = sum(counts[a][0] for a in years)
        m = sum(counts[a][1] for a in years)
        rows.append([f"{low}-{low + 4}", w + m, w, m, 100])
        rows += [[float(a), sum(counts[a]), counts[a][0], counts[a][1], 100] for a in years]
    rows.append([f"{open_from} y más", sum(open_counts), *open_counts, 100])
    rows.append(["Fuente: INDEC, Censo Nacional de Población, Hogares y Viviendas 2022."])
    return rows


class Cells(unittest.TestCase):
    def test_a_dash_is_zero_and_three_slashes_is_not_applicable(self):
        self.assertEqual(ac.number("-"), 0)
        self.assertIsNone(ac.number("///"))
        self.assertEqual(ac.number(3840905.0), 3840905)

    def test_an_age_stored_as_a_float_reads_as_its_year(self):
        self.assertEqual(ac.label(5.0), "5")


class Sheets(unittest.TestCase):
    def test_buenos_aires_names_its_sheets_without_a_space_and_its_province_zero(self):
        class Book:
            sheetnames = ["Carátula", "Cuadro4.2.0", "Cuadro4.2.1", "Cuadro\xa04.6", "Cuadro1.2 bis"]

            def __getitem__(self, name):
                class Sheet:
                    def iter_rows(self, values_only):
                        return iter([("Cuadro", name)])
                return Sheet()
        keys = set(ac.cuadros(Book()))
        self.assertEqual(keys, {(2, None), (2, 1), (6, None)})

    def test_a_subtotal_repeating_the_province_code_is_collected_not_kept(self):
        repeats: dict = {}
        rows = [["06", "Total", 15625084, 17523996], ["06", "24 partidos", 9916715, 10849299],
                [6007, "Adolfo Alsina", 17072, 17571]]
        out = ac.coded(rows, repeats)
        self.assertEqual(out["06"][1][1], 17523996)
        self.assertEqual([r[1] for r in repeats["06"]], [17523996, 10849299])
        self.assertEqual(out["06007"], ("Adolfo Alsina", [17072, 17571]))

    def test_a_department_with_no_2010_figure_keeps_its_2022_one_in_place(self):
        out = ac.coded([["94015", "Tolhuin", "///", 9245]])
        self.assertEqual(out["94015"][1], [None, 9245])


class Ages(unittest.TestCase):
    def test_the_median_is_interpolated_within_the_middle_year(self):
        counts = {a: (5, 5) for a in range(10)}           # 100 people aged 0-9
        women, men, median = ac.ages(age_sheet(counts, 10, (0, 0)), "test")
        self.assertEqual((women, men), (50, 50))
        self.assertEqual(median, 5.0)

    def test_ages_that_do_not_make_the_total_are_refused(self):
        rows = age_sheet({a: (5, 5) for a in range(10)}, 10, (0, 0))
        rows[6][1] += 1                                   # age 0 now one too many
        with self.assertRaises(SystemExit):
            ac.ages(rows, "test")

    def test_a_group_that_its_years_do_not_make_is_refused(self):
        rows = age_sheet({a: (5, 5) for a in range(10)}, 10, (0, 0))
        rows[5][1] += 1                                   # the 0-4 row
        with self.assertRaises(SystemExit):
            ac.ages(rows, "test")


class DepartmentSheets(unittest.TestCase):
    def test_a_sheet_is_the_department_its_title_names_not_a_shorter_namesake(self):
        sheets = {(6, None): [["Cuadro 1.6. Provincia de Córdoba."]],
                  (6, 1): [["Cuadro 1.6.1. Provincia de Córdoba, departamento General San Martín."]],
                  (6, 2): [["Cuadro 1.6.2. Provincia de Córdoba, departamento San Martín."]]}
        names = {"14042": "General San Martín", "14099": "San Martín"}
        out = ac.dept_sheet(sheets, 6, names, "test")
        self.assertIs(out["14042"], sheets[(6, 1)])
        self.assertIs(out["14099"], sheets[(6, 2)])

    def test_a_capital_comuna_is_found_by_its_own_name(self):
        sheets = {(1, 3): [["Cuadro 1.1.3. Ciudad Autónoma de Buenos Aires, comuna 3."]]}
        out = ac.dept_sheet(sheets, 1, {"02003": "Comuna 3"}, "test")
        self.assertIn("02003", out)


class Binding(unittest.TestCase):
    parents = {"P-BA": "Buenos Aires", "P-CBA": "Córdoba", "P-SDE": "Santiago del Estero",
               "P-CABA": "Ciudad Autónoma de Buenos Aires"}

    def shape(self, sid, name, parent, x, y):
        return {"id": sid, "name": name, "parent": parent, "point": [x, y]}

    def test_misfiled_polygons_are_bound_by_a_name_nothing_else_shares(self):
        shapes = [self.shape("s1", "Rivadavia", "P-BA", -63.0, -35.6),
                  self.shape("s2", "Rivadavia", "P-CBA", -62.3, -30.1),      # really Santiago's
                  self.shape("s3", "Lanús", "P-CABA", -58.4, -34.7),         # really Buenos Aires's
                  self.shape("s4", "Capital", "P-CBA", -64.2, -31.4),
                  self.shape("s5", "Banda", "P-SDE", -64.2, -27.7),
                  self.shape("s6", "Capital", "P-SDE", -64.3, -27.8)]
        departments = {"06707": ("Rivadavia", "Buenos Aires"),
                       "86119": ("Rivadavia", "Santiago del Estero"),
                       "06434": ("Lanús", "Buenos Aires"),
                       "14014": ("Capital", "Córdoba"),
                       "86049": ("Banda", "Santiago del Estero"),
                       "86035": ("Capital", "Santiago del Estero")}
        bound, missing = ac.bind(departments, shapes, self.parents)
        self.assertEqual(missing, [])
        self.assertEqual(bound, {"06707": "s1", "86119": "s2", "06434": "s3", "14014": "s4",
                                 "86049": "s5", "86035": "s6"})

    def test_two_namesakes_in_one_polygon_province_are_told_apart_by_place(self):
        # Entre Ríos is drawn inside Buenos Aires, so its Colón sits beside
        # Buenos Aires's under the same parent.
        shapes = [self.shape("ba1", "Azul", "P-BA", -59.8, -36.8),
                  self.shape("ba2", "Arrecifes", "P-BA", -60.1, -34.1),
                  self.shape("ba3", "Tandil", "P-BA", -59.1, -37.3),
                  self.shape("c1", "Colón", "P-BA", -61.0, -33.8),
                  self.shape("c2", "Colón", "P-BA", -58.4, -32.0),
                  self.shape("er1", "Paraná", "P-BA", -60.3, -31.7),
                  self.shape("er2", "Uruguay", "P-BA", -58.6, -32.5)]
        departments = {"06007": ("Azul", "Buenos Aires"), "06008": ("Arrecifes", "Buenos Aires"),
                       "06009": ("Tandil", "Buenos Aires"), "06210": ("Colón", "Buenos Aires"),
                       "30015": ("Colón", "Entre Ríos"), "30084": ("Paraná", "Entre Ríos"),
                       "30113": ("Uruguay", "Entre Ríos")}
        bound, missing = ac.bind(departments, shapes, self.parents)
        self.assertEqual(missing, [])
        self.assertEqual(bound["06210"], "c1")
        self.assertEqual(bound["30015"], "c2")

    def test_a_department_with_no_polygon_is_left_out_not_given_a_namesakes(self):
        shapes = [self.shape("s1", "San Martín", "P-CBA", -63.0, -32.0)]
        departments = {"14140": ("San Martín", "Córdoba"),
                       "86147": ("San Martín", "Santiago del Estero")}
        bound, missing = ac.bind(departments, shapes, self.parents)
        self.assertEqual(bound, {"14140": "s1"})
        self.assertEqual(missing, ["San Martín (86147)"])


if __name__ == "__main__":
    unittest.main()
