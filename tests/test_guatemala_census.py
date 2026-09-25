"""Guatemala's 2018 census, read from INE's person database."""
import unittest
from unittest import mock

import openpyxl

from scripts.fetch_census import guatemala_census as gt


def workbook():
    """INE's dictionary as it is laid out: variables, then value labels, then
    the municipio catalogue on a sheet of its own."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "PERSONA"
    for row in (
        ("Información de las variables",),
        ("Nombre", "Posición", "Etiqueta de la variable", "Formato"),
        ("PCP12", 22, "Según su origen o historia,¿cómo se considera o auto identifica?", "Numérico (1)"),
        (),
        ("Etiqueta de los valores",),
        ("Nombre", "Valor", "Etiqueta"),
        ("PCP6", 1, "Hombre"), (None, 2, "Mujer"),
        ("PCP12", 1, "Maya"), (None, 5, "Ladina  (o)"),
        ("PCP15", 10, "K'iche'"), (None, 25, "Español"), (None, 98, "No habla"),
    ):
        sheet.append(row)
    cat = book.create_sheet("Catálogo de Municipios")
    cat.append(("MUNICIPIO", "NOMBRE MUNICIPIO", "NOMBRE DEPARTAMENTO",
                "CÓDIGO DEPARTAMENTO", "CÓDIGO MUNICIPIO"))
    cat.append((101, "Guatemala", "Guatemala", 1, 1))
    cat.append((701, "Sololá", "Sololá", 7, 1))
    return book


HEADER = ["﻿DEPARTAMENTO", "MUNICIPIO", "PCP6", "PCP7", "PCP12", "PCP15"]


def person(muni, age, pueblo, idioma, sex=1):
    return [str(muni // 100), str(muni), str(sex), str(age), str(pueblo), str(idioma)]


PEOPLE = ([person(101, 30, 5, 25, 1)] * 3 + [person(101, 30, 5, 25, 2)] * 3
          + [person(101, 2, 5, " ", 2)]
          + [person(701, 40, 1, 10)] * 3 + [person(701, 20, 5, 25, 2),
                                           person(701, 1, 1, " ", 2)])


class Dictionary(unittest.TestCase):
    def test_reads_labels_and_catalogue(self):
        labels, municipios = gt.read_dictionary(workbook())
        self.assertEqual(labels["PCP12"], {1: "Maya", 5: "Ladina (o)"})
        self.assertEqual(labels["PCP15"][98], "No habla")
        self.assertEqual(municipios[701], ("Sololá", 7, "Sololá"))
        self.assertEqual(len(municipios), 2)

    def test_an_unknown_label_stops_the_run(self):
        with self.assertRaises(SystemExit) as ctx:
            gt.translate({1: "Maya", 7: "Mestiza"}, gt.PUEBLO, "PCP12")
        self.assertIn("Mestiza", str(ctx.exception))

    def test_every_label_the_dictionary_carries_is_known(self):
        # The labels as the 24 September 2026 check printed them.
        pueblo = ["Maya", "Garífuna", "Xinka", "Afrodescendiente/Creole/Afromestizo",
                  "Ladina (o)", "Extranjera (o)"]
        self.assertEqual(len(gt.translate(dict(enumerate(pueblo, 1)), gt.PUEBLO, "x")), 6)
        self.assertEqual(len(gt.IDIOMA), 29)


class Counting(unittest.TestCase):
    def setUp(self):
        labels, self.municipios = gt.read_dictionary(workbook())
        self.sexes = gt.sex_codes(labels)
        self.pueblos = gt.translate(labels["PCP12"], gt.PUEBLO, "PCP12")
        self.idiomas = gt.translate(labels["PCP15"], gt.IDIOMA, "PCP15")
        self.counts = gt.count(iter(PEOPLE), HEADER)

    def build(self, departments=None):
        with mock.patch.object(gt, "DEPARTMENTS", departments or {1: 7, 7: 5}):
            return gt.build(self.counts, self.municipios, self.pueblos, self.idiomas,
                            self.sexes)

    def unit(self, rows, level, name):
        found = [r for r in rows if r["level"] == level and r["name"] == name]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_counts_people_by_municipio(self):
        self.assertEqual(self.counts[101]["people"], 7)
        self.assertEqual(self.counts[701]["idioma"], {10: 3, 25: 1})

    def test_writes_both_levels(self):
        rows = self.build()
        solola = self.unit(rows, "admin2", "Sololá")
        ethnicity = {g["group"]: g["count"] for g in solola["ethnicity"]}
        self.assertEqual(ethnicity, {"Maya": 4, "Ladino": 1})
        self.assertEqual(solola["parent_name"], "Sololá")
        self.assertEqual(solola["ethnicity_year"], 2018)
        department = self.unit(rows, "admin1", "Sololá")
        self.assertEqual(department["parent"], "GTM")
        self.assertEqual(department["ethnicity"], solola["ethnicity"])

    def test_language_is_of_people_aged_four_and_over(self):
        # The blanks are all under four and nobody under four answered, so the
        # note names the universe; the shares are of the people asked.
        rows = self.build()
        guate = self.unit(rows, "admin2", "Guatemala")
        self.assertEqual(guate["language"], [{"group": "Spanish", "pct": 100.0, "count": 6}])
        self.assertIn("aged four and over", guate["language_note"])
        self.assertIn("all 7 people", guate["ethnicity_note"])

    def test_median_age_and_sex_ratio_are_counted(self):
        rows = self.build()
        guate = self.unit(rows, "admin2", "Guatemala")
        # Ages 2 and six of 30: half of seven people is 3.5, the 2.5th of the
        # six 30-year-olds.
        self.assertEqual(guate["median_age"]["value"], 30.4)
        self.assertEqual(guate["sex_ratio"]["value"], 750)
        solola = self.unit(rows, "admin1", "Sololá")
        self.assertEqual(solola["median_age"]["value"], 40.2)
        self.assertEqual(solola["sex_ratio"]["value"], 1500)

    def test_a_dictionary_without_hombre_and_mujer_stops_the_run(self):
        with self.assertRaises(SystemExit):
            gt.sex_codes({"PCP6": {1: "Masculino", 2: "Femenino"}})

    def test_population_is_left_to_newer_figures(self):
        rows = self.build()
        self.assertEqual(self.unit(rows, "admin2", "Sololá")["population"]["status"],
                         "not_available")

    def test_a_department_off_by_one_writes_nothing(self):
        with self.assertRaises(SystemExit) as ctx:
            self.build({1: 7, 7: 6})
        self.assertIn("published department", str(ctx.exception))

    def test_an_unlabelled_code_stops_the_run(self):
        self.counts[701]["pueblo"][9] += 1
        with self.assertRaises(SystemExit) as ctx:
            self.build()
        self.assertIn("PCP12", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
