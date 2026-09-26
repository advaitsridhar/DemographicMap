"""Bolivia's 2024 census: INE's dictionary read, people counted, and polygons checked."""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import bolivia_census as bc  # noqa: E402

DICTIONARY = [
    ("DICCIONARIO DE VARIABLES DE PERSONA", None),
    ("Etiqueta", "25. Es mujer u hombre"),
    ("Nombre", "P25_SEXO", "Alias (Redatam)", "SEXO", "Entidad (Redatam)", "PERSONA"),
    ("Tipo", "INTEGER", "Rango", "1 - 2"),
    ("Categorías",),
    (1, "Mujer"),
    (2.0, "Hombre"),
    (None,),
    ("Etiqueta", "Se autoidentifica ... (agrupado según CTAI)"),
    ("Nombre", "P32_PUEBLOS", "Alias (Redatam)", "PUEBLOGR"),
    ("Tipo", "INTEGER", "Rango", "1 - 99"),
    ("Categorías",),
    (1, "Afroboliviano"),
    (3, "Aymara"),
    (40, "Quechua"),
    (57, "Otras declaraciones"),
    (98, "No se autoidentifica"),
    (99, "Sin respuesta"),
    ("Etiqueta", "Idioma materno"),
    ("Nombre", "IDIOMA_MAT", "Alias (Redatam)", "Entidad (Redatam)", "PERSONA"),
    ("Categorías",),
    (6, "Castellano"),
    (27, "Quechua"),
    (998, "No habla"),
]


class Dictionary(unittest.TestCase):
    def test_labels_are_read_by_variable_whatever_type_the_code_cell_is(self):
        labels = bc.read_labels(DICTIONARY)
        self.assertEqual(labels["P25_SEXO"], {1: "Mujer", 2: "Hombre"})
        self.assertEqual(labels["P32_PUEBLOS"][98], "No se autoidentifica")
        self.assertEqual(labels["IDIOMA_MAT"], {6: "Castellano", 27: "Quechua", 998: "No habla"})

    def test_a_label_this_file_does_not_know_stops_the_run(self):
        with self.assertRaises(SystemExit):
            bc.translate({1: "Aymara", 2: "Pueblo nuevo"}, bc.PUEBLOS, "P32_PUEBLOS")

    def test_the_unanswered_and_the_not_yet_speaking_are_known_but_not_translated(self):
        labels = bc.read_labels(DICTIONARY)
        pueblos = bc.translate(labels["P32_PUEBLOS"], bc.PUEBLOS, "P32_PUEBLOS", [bc.UNANSWERED])
        self.assertNotIn(99, pueblos)
        self.assertEqual(pueblos[98], bc.REST)
        self.assertEqual(pueblos[1], "Afro-Bolivian")

    def test_sex_codes_come_from_the_labels_not_from_an_assumption(self):
        labels = bc.read_labels(DICTIONARY)
        self.assertEqual(bc.code_of(labels["P25_SEXO"], "Mujer", "P25_SEXO"), 1)
        self.assertEqual(bc.code_of(labels["P25_SEXO"], "Hombre", "P25_SEXO"), 2)


class Counting(unittest.TestCase):
    header = ["idep", "iprov", "imun", "p25_sexo", "p26_edad", "p32_pueblos", "idioma_mat"]

    def rows(self):
        return [["02", "01", "01", "1", "30", "3", "6"],
                ["02", "01", "01", "2", "40", "98", "6"],
                ["02", "01", "01", "2", "1", "99", "998"],
                ["02", "17", "01", "1", "61", "40", "27"],
                ["02", "17", "01", "2", "59", "57", ""]]

    def test_people_are_counted_by_department_and_province(self):
        out = bc.count(self.rows(), self.header)
        self.assertEqual(set(out), {201, 217})
        self.assertEqual(sum(out[201]["sex"].values()), 3)

    def test_the_unanswered_and_the_unspecified_are_left_out_of_the_shares_and_counted(self):
        labels = bc.read_labels(DICTIONARY)
        pueblos = bc.translate(labels["P32_PUEBLOS"], bc.PUEBLOS, "P32_PUEBLOS", [bc.UNANSWERED])
        idiomas = bc.translate(labels["IDIOMA_MAT"], bc.LANGUAGES, "IDIOMA_MAT", [bc.NOT_SPEAKING])
        out = bc.count(self.rows(), self.header)
        f = bc.fields(out[201], ("1", "2"), pueblos, idiomas, 998)
        self.assertEqual({g["group"]: g["count"] for g in f["ethnicity"]},
                         {"Aymara": 1, bc.REST: 1})
        self.assertIn("1 did not", f["ethnicity_note"])
        self.assertEqual(f["language"], [{"group": "Spanish", "pct": 100.0, "count": 2}])
        self.assertIn("1 children who do not yet speak", f["language_note"])
        self.assertEqual(f["sex_ratio"]["value"], 2000)
        self.assertEqual(f["population"]["value"], 3)

    def test_the_median_is_interpolated_within_the_middle_year(self):
        self.assertEqual(bc.median_age(Counter({a: 10 for a in range(10)})), 5.0)


class Polygons(unittest.TestCase):
    departments = [{"id": "BENI", "bbox": [-67.6, -16.5, -61.5, -10.4]},
                   {"id": "ORURO", "bbox": [-69.0, -20.0, -66.0, -17.0]}]

    def test_a_polygon_reaching_far_outside_its_department_is_several_places(self):
        cercado = {"id": "c", "parent": "BENI", "bbox": [-67.7, -21.9, -63.6, -14.0]}
        moxos = {"id": "m", "parent": "BENI", "bbox": [-66.9, -15.9, -64.9, -14.2]}
        self.assertEqual(bc.merged([cercado, moxos], self.departments), [cercado])


if __name__ == "__main__":
    unittest.main()
