"""Chad's provinces for 2023 and its departments' seats, on small inputs (no network)."""

import unittest

from scripts.fetch_census import chad_departments as cd

WIKI = """{| class="wikitable sortable"
! Department !! Pop. 2009 !! Capital !! Sub-prefectures
|-
| [[Abdi Department|Abdi]] || {{formatnum:114055}} || {{ill|Abdi (ville)|fr|3=Abdi (ville)}} || Abdi
|-
| [[Barh Azoum Department|Barh Azoum]] (Barh-Azoum) || {{formatnum:224984}} || [[Am Timan]] || Am Timan
|-
| [[Grande Sido]] || {{formatnum:105375}} || {{ill|Maro|fr|3=Maro (Tchad)}} || Maro
|-
| [[Wadi Hawar Department|Wadi Hawar]] || || ||
|}"""


class Seats(unittest.TestCase):
    def test_names_and_seats(self):
        seat_of = cd.seats(WIKI)
        self.assertEqual(seat_of[cd.key("Abdi")], "Abdi")
        self.assertEqual(seat_of[cd.key("Bahr-Azoum")], "Am Timan")    # Bahr and Barh made one
        self.assertEqual(seat_of[cd.key("Grande Sido")], "Maro")
        self.assertNotIn(cd.key("Wadi Hawar"), seat_of)

    def test_build(self):
        adm1 = [{"ADM1_NAME": "N'Djamena", "T_TL": "18000000"},
                {"ADM1_NAME": "Salamat", "T_TL": "496719"}]
        admin1 = [{"id": "N", "name": "N'Djamena Region"}, {"id": "S", "name": "Salamat"}]
        admin2 = [{"id": "a", "name": "Bahr-Azoum", "parent": "S"},
                  {"id": "b", "name": "N'Djaména", "parent": "N"},
                  {"id": "c", "name": "Fouli", "parent": "S"}]
        records, report = cd.build(adm1, cd.seats(WIKI), admin1, admin2)
        by = {(r["level"], r["name"]): r for r in records}
        self.assertEqual(by[("admin1", "Salamat")]["population"]["value"], 496_719)
        self.assertEqual(by[("admin1", "Salamat")]["population"]["year"], 2023)
        self.assertEqual(by[("admin2", "Bahr-Azoum")]["capital"], "Am Timan")
        self.assertEqual(by[("admin2", "N'Djaména")]["capital"], "N'Djamena")
        self.assertNotIn(("admin2", "Fouli"), by)
        self.assertTrue(any("Fouli: no seat named" in line for line in report))

    def test_too_few_people_refused(self):
        with self.assertRaises(SystemExit):
            cd.build([{"ADM1_NAME": "Salamat", "T_TL": "496719"}], {},
                     [{"id": "S", "name": "Salamat"}], [])


if __name__ == "__main__":
    unittest.main()
