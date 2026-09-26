"""Venezuela's 2011 census: the indigenous-peoples and parroquia tables read and checked."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import venezuela_census as vc  # noqa: E402

PEOPLES = [["", "Población indígena por sexo, según entidad federal y pueblo", "", ""],
           ["", "Entidad Federal", "", "Total", "", "Hombres"],
           ["", "", "Total", 1300.0],
           ["", "Distrito Capital", "", 300.0],
           ["", "", "Wayuu/Guajiro", 200.0],
           ["", "", "Warao", 100.0],
           ["", "Estado:", "", ""],
           ["", "Estado Vargas", "", 1000.0],
           ["", "", "Añú/Paraujano", 990.0],
           ["", "", "Kaketío", 10.0]]
POPULATION = [["", "Población empadronada por sexo, según entidad federal"],
              ["", "Código UBIGEO", "Entidad Federal", "Municipio", "Parroquia", "Total"],
              ["", "", "", "", "Total", 6000],
              ["", "010101", "Distrito Capital", "Distrito Capital, Libertador", "Altagracia", 2000],
              ["", "010102", "Distrito Capital", "Distrito Capital, Libertador", "Antímano", 1000],
              ["", "240101", "Estado Vargas", "Vargas, Vargas", "Caraballeda", 3000]]


class Tables(unittest.TestCase):
    def test_peoples_are_read_by_state_with_inei_s_names_joined(self):
        states, national = vc.peoples_table(PEOPLES)
        self.assertEqual(national, 1300)
        self.assertEqual(states[vc.state_key("Distrito Capital")][2],
                         {"Wayuu": 200, "Warao": 100})
        self.assertEqual(states[vc.state_key("La Guaira")][2]["Añú (Paraujano)"], 990)

    def test_peoples_that_do_not_make_their_state_are_refused(self):
        rows = [list(r) for r in PEOPLES]
        rows[4][3] = 201.0
        with self.assertRaises(SystemExit):
            vc.peoples_table(rows)

    def test_an_answer_is_not_taken_for_a_people(self):
        with self.assertRaises(SystemExit):
            vc.people_name("Otros pueblos")

    def test_parroquias_are_summed_to_their_state_and_must_make_the_total(self):
        states, national = vc.population_table(POPULATION)
        self.assertEqual(national, 6000)
        self.assertEqual(states[vc.state_key("Distrito Capital")], 3000)
        rows = [list(r) for r in POPULATION]
        rows[5][5] = 2999
        with self.assertRaises(SystemExit):
            vc.population_table(rows)


if __name__ == "__main__":
    unittest.main()
