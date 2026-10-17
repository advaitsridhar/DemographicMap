"""Equatorial Guinea's 2015 census tables from INEGE's 2020 yearbook, as the runner printed them."""

import unittest

from scripts.fetch_census import equatorial_guinea_census as eg

PAGES = ["""Anuario Estadístico de G.E.- 2020
LISTA DE TABLAS
Tabla 20: Distribución de la población de G.E. por año censal y área geográfica ........ 56
Tabla 23: Población por distrito según la nacionalidad y la zona.2015 ........ 59""",
"""Tabla 20: Distribución de la población de G.E. por año censal y
área geográfica
Área geográfica 1983 1994 2001 2015
Región Continental 240.140 463.155 749.529 885.015
Centro Sur 52.630 88.546 125.856 141.986
Kie Ntem 69.730 136.146 167.279 183.664
Litoral 66.750 146.811 298.414 367.348
Wele Nzas 51.030 91.652 157.980 192.017
Región Insular 59.860 132.840 265.470 340.362
Annobón 2.120 4.138 5.008 5.314
Bioko Norte 47.170 110.258 231.428 300.374
Bioko Sur 10.570 18.444 29.034 34.674
Guinea Ecuatorial 300.000 595.995 1.014.999 1.225.377
Fuente: Censos de población de Guinea Ecuatorial
Tabla 21: Distribución de la Población por área geográfica según sexo,
nacionalidad y zona (%). 2015
Hombres Mujeres Nacionales Extranjeros Urbana Rural
Región Insular 52,9 47,1 87,7 12,3 87,5 12,5
Annobón 48,9 51,1 98,3 1,7 100 -
Bioko Norte 52,9 47,1 87,3 12,7 88,8 11,2
Bioko Sur 52,5 47,5 93,9 6,1 56,9 43,1
Región Continental 52,1 47,9 87,5 12,5 70,0 30
Centro Sur 51,2 48,8 89,9 10,1 52,3 47,7
Kie-Ntem 50,1 49,9 89,5 10,5 38,3 61,7
Litoral 52,3 47,7 87,7 12,3 90,2 9,8
Wele-Nzas 53,7 46,3 83,5 16,5 40,1 59,9
Guinea Ecuatorial 52,4 47,6 87,6 12,4 76,1 23,9
Fuente: IV CGPV-MEPIP (2015)""",
"""Tabla 23: Población por distrito según la nacionalidad y la zona.2015
Bata 309.345 25,3 87,3 12,7 95,3 4,7
Malabo 271.008 22,1 86,4 13,6 94,8 5,2
Ebibeyin 94.019 7,7 87,8 12,2 42,4 57,6
Mongomo 88.326 7,2 81,8 18,2 39,1 60,9
Añisok 62.924 5,1 82,2 17,8 40,9 59,1
Niefang 61.708 5,0 91,9 8,1 49,6 50,4
Evinayong 56.664 4,6 91,3 8,7 58,0 42,0
Micomiseng 51.725 4,2 93,0 7,0 32,6 67,4
Nsok Nsomo 37.920 3,1 90,5 9,5 36,1 63,9
Baney 29.366 2,4 93,0 7,0 41,4 58,6
Cogo 29.341 2,4 92,8 7,2 31,1 68,9
Mbini 28.662 2,4 94,3 5,7 27,8 72,2
Luba 26.331 2,2 93,7 6,3 66,2 33,8
Aconibe 24.346 2,0 93,6 6,4 40,2 59,8
Acurenam 23.614 1,9 84,0 16,0 44,1 55,9
Nsork 16.421 1,3 89,7 10,3 42,6 57,4
Riaba 8.343 0,7 94,6 5,4 25,6 74,4
Annobón 5.314 0,4 98,3 1,7 100 -
Guinea Ecuatorial 1.225.377 100 87,6 12,4 76,1 23,9
Fuente: IV CGPV-MEPIP (2015)"""]


def units():
    admin1 = [{"id": f"P{i}", "name": n} for i, n in enumerate(
        ["Annobón", "Bioko Norte", "Bioko Sur", "Centro Sur Province", "Kié-Ntem Province",
         "Litoral Province", "Wele-Nzas Province"])]
    pid = {u["name"]: u["id"] for u in admin1}
    drawn = {"Annobón": ["ANNOBON"], "Bioko Norte": ["MALABO", "BANEY"],
             "Bioko Sur": ["LUBA", "RIABA"],
             "Centro Sur Province": ["ACURENAM", "BICURGA", "EVINAYONG", "NIEFANG", "NKIMI"],
             "Kié-Ntem Province": ["EBEBIYIN", "MICOMISENG", "NKUE", "NSOC NSOMO"],
             "Litoral Province": ["BATA", "BITICA", "COGO", "MACHINDA", "MBINI"],
             "Wele-Nzas Province": ["ACONIBE", "AYENE", "AÑISOC", "MONGOMO", "MONGOMOYEN", "NSORK"]}
    admin2 = [{"id": f"D{p}{n}", "name": n, "parent": pid[p]} for p, ns in drawn.items() for n in ns]
    return admin1, admin2


class Tables(unittest.TestCase):
    def test_read_adds_up(self):
        provinces, problems = eg.read(PAGES)
        self.assertEqual(problems, [])
        self.assertEqual(provinces["Litoral"]["total"], 367_348)
        self.assertEqual(provinces["Bioko Norte"]["districts"]["Malabo"]["foreigners"], 13.6)

    def test_a_district_out_of_place_is_reported(self):
        broken = [PAGES[0], PAGES[1], PAGES[2].replace("Baney 29.366", "Baney 29.367")]
        _, problems = eg.read(broken)
        self.assertTrue(any("districts make" in p for p in problems))


class Build(unittest.TestCase):
    def test_records(self):
        provinces, _ = eg.read(PAGES)
        admin1, admin2 = units()
        records, _ = eg.build(provinces, admin1, admin2)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["MALABO"]["population"]["value"], 271_008)
        self.assertEqual(by["MALABO"]["ethnicity_basis"], "nationality")
        self.assertEqual(by["Litoral Province"]["sex_ratio"]["value"], round(1000 * 52.3 / 47.7))
        # Annobón district is the whole province, so it takes the province's sex ratio.
        self.assertEqual(by["ANNOBON"]["sex_ratio"]["value"], round(1000 * 48.9 / 51.1))
        bata = by["BATA"]["population"]
        self.assertEqual(bata["displaces_before"], 2015)
        self.assertIn("309,345", bata["note"])
        self.assertIn("Bitica and Machinda", bata["note"])
        self.assertIn("not one", by["NKUE"]["population"]["note"])
        self.assertIn("Kié-Ntem", by["NKUE"]["population"]["note"])
        for r in records:
            for field in ("population", "sex_ratio", "median_age"):
                value = r[field]
                self.assertTrue("value" in value or value.get("note"), (r["name"], field))


if __name__ == "__main__":
    unittest.main()
