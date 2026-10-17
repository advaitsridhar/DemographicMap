"""Gabon's 2013 census Tableau 6 and the departments' seats, on small text (no network)."""

import unittest

from scripts.fetch_census import gabon_census as gc

TABLEAU_6 = """Tableau 6 : Répartition de la population résidente par département selon le sexe
Province / département Hommes Femmes Total Rang Densité
Libreville 359 688 344 252 703 940 1er 3724,6
Komo-Mondah 46 410 43 686 90 096 2e 15,8
Owendo 41 112 38 188 79 300 3e 520,1
ESTUAIRE 447 210 426 126 873 336
Mulundu 14 300 13 450 27 750 1er 3,2
OGOOUE- 14 300 13 450 27 750
LOLO
"""


def unit(uid, name, parent):
    return {"id": uid, "name": name, "parent": parent, "point": [9.0, 0.0]}


class Reading(unittest.TestCase):
    def test_three_reads_spaced_thousands(self):
        self.assertEqual(gc.three(["359", "688", "344", "252", "703", "940"]),
                         (359_688, 344_252, 703_940))
        self.assertIsNone(gc.three(["12", "34"]))

    def test_parse(self):
        table = gc.parse([TABLEAU_6])
        self.assertEqual(table["provinces"]["ESTUAIRE"], (447_210, 426_126, 873_336))
        self.assertEqual(table["provinces"]["OGOOUE-LOLO"], (14_300, 13_450, 27_750))
        self.assertEqual(table["departments"]["ESTUAIRE"]["Owendo"], (41_112, 38_188, 79_300))
        problems = gc.check(table)
        self.assertTrue(any("provinces read" in p for p in problems))


class Seats(unittest.TestCase):
    WIKI = """{| class="wikitable"
! Nom !! Province !! Population (cens. 2013) !! Chef-lieu
|-
| [[Komo-Mondah]] || Estuaire || {{formatnum:90096}} || [[Ntoum]]
|-
| [[Akanda (département)|Akanda]] || Estuaire || {{formatnum:703940}} || Akanda
|-
| Mulundu || Ogooué-Lolo || {{formatnum:27750}} || [[Lastoursville]]
|}"""

    def test_seat_only_where_the_count_agrees(self):
        table = gc.parse([TABLEAU_6])
        seat_of = gc.seats(self.WIKI)
        admin1 = [unit("E", "Estuaire", "GAB"), unit("O", "Ogooué-Lolo", "GAB")]
        admin2 = [unit("L", "Libreville", "E"), unit("K", "Komo-Mondah", "E"),
                  unit("M", "Mouloundou", "O")]
        records, _ = gc.build(table, admin1, admin2, seat_of)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Komo-Mondah"]["population"]["value"], 169_396)   # with Owendo
        self.assertEqual(by["Komo-Mondah"]["capital"], "Ntoum")
        self.assertEqual(by["Mouloundou"]["capital"], "Lastoursville")
        # The article's Akanda row carries Libreville's count; Libreville is its own seat.
        self.assertEqual(by["Libreville"]["capital"], "Libreville")
        self.assertEqual(by["Libreville"]["sex_ratio"]["value"], round(1000 * 359_688 / 344_252))
        self.assertIn("2013 census", by["Libreville"]["population_note"])


if __name__ == "__main__":
    unittest.main()
