"""Cameroon's 2005 census tables by department and sex, on text laid out as the runner printed it."""

import unittest

from scripts.fetch_census import cameroon_census as cc

# Adamaoua's three tables, the lines of the report much as pdfplumber gives them:
# a name too long for its cell is printed on either side of its figures.
ALL = """Tableau n°2.a- Répartition de la population résidant dans la province de
l'ADAMAOUA par Département et par Arrondissement/District, selon le sexe
Circonscription Sexe
Population Rapport de
administrative totale Masculin Féminin masculinité
PROVINCE DE
884289 438913 445376 98,55
L'ADAMAOUA
Département du DJEREM 124948 61677 63271 97,48
NGAOUNDAL 52867 26289 26578 98,91
TIBATI 72 081 35388 36693 96,44
Département du FARO ET
759341 377236 382105 98,7
DEO
GALIM TIGNERE 759341 377236 382105 98,7"""

URBAN = """Tableau n°2.b- Répartition de la population résidant en milieu urbain dans la province de l'ADAMAOUA
PROVINCE DE L'ADAMAOUA 400000 200000 200000 100
Département du DJEREM 48722 24417 24305 100,46
NGAOUNDAL 25853 12999 12854 101,13
TIBATI 22869 11418 11451 99,71
Département du FARO ET DEO 351278 175583 175695 99,9
GALIM TIGNERE 351278 175583 175695 99,9"""

RURAL = """Tableau n°2.c- Répartition de la population résidant en milieu rural dans la province de l'ADAMAOUA
PROVINCE DE L'ADAMAOUA 484289 238913 245376 97
Département du DJEREM 76226 37260 38966 95,6
NGAOUNDAL 27014 13290 13724 96,8
TIBATI 49212 23970 25242 94,9
Département du FARO ET DEO 408063 201653 206410 97,6
GALIM TIGNERE 408063 201653 206410 97,6"""

WIKI = """{| class="wikitable"
! Département !! Préfecture !! Sous-préfecture(s) !! Région
|-
| [[Djérem]] || [[Tibati]] || Tibati, Ngaoundal || Adamaoua
|-
| [[Faro-et-Déo]] || [[Tignère]] || Galim-Tignère || Adamaoua
|}"""


def unit(uid, name, parent, x=13.0):
    return {"id": uid, "name": name, "parent": parent, "point": [x, 7.0]}


class Figures(unittest.TestCase):
    def test_labels_keep_their_own_numbers(self):
        self.assertEqual(cc.figures("YAOUNDE 3 252501 126332 126169 100,13"),
                         ("YAOUNDE 3", (252_501, 126_332, 126_169)))
        self.assertEqual(cc.figures("DOUALA 1 0 0 0 0"), ("DOUALA 1", (0, 0, 0)))
        self.assertEqual(cc.figures("TCHOLLIRE 10 465 5560 4905 113,36"),
                         ("TCHOLLIRE", (10_465, 5_560, 4_905)))
        self.assertIsNone(cc.figures("Circonscription Sexe"))

    def test_wrapped_names(self):
        rows = cc.entries(ALL.splitlines())
        names = [r[0] for r in rows]
        self.assertEqual(names[0], "PROVINCE DE L'ADAMAOUA")
        self.assertIn("Département du FARO ET DEO", names)
        self.assertIn(("TIBATI", 72_081, 35_388, 36_693), rows)


class Tables(unittest.TestCase):
    def test_read_checks_every_sum(self):
        pages = [ALL + "\n" + URBAN + "\n" + RURAL]
        tables, problems = cc.read(pages)
        adamaoua = tables["adamaoua"]["all"]
        self.assertEqual(adamaoua["province"][1:], (884_289, 438_913, 445_376))
        self.assertEqual(sorted(adamaoua["departments"]), ["DJEREM", "FARO ET DEO"])
        # The other nine provinces are missing, and nothing else is wrong.
        self.assertEqual(len(problems), 9)
        self.assertTrue(all("no table of all residents" in p for p in problems))

    def test_a_department_its_arrondissements_do_not_make_is_reported(self):
        broken = ALL.replace("NGAOUNDAL 52867 26289 26578", "NGAOUNDAL 52868 26290 26578")
        _, problems = cc.read([broken + "\n" + URBAN + "\n" + RURAL])
        self.assertTrue(any("arrondissements make" in p for p in problems))

    def test_build(self):
        tables, _ = cc.read([ALL + "\n" + URBAN + "\n" + RURAL])
        admin1 = [{"id": "A", "name": "Adamaoua"}]
        admin2 = [unit("D", "Djerem", "A", 12.5), unit("F", "Faro-et-Deo", "A", 13.5)]
        records, _ = cc.build(tables, cc.seats(WIKI), admin1, admin2)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Djerem"]["population"]["value"], 124_948)
        self.assertEqual(by["Djerem"]["sex_ratio"]["value"], round(1000 * 61_677 / 63_271))
        self.assertEqual(by["Djerem"]["capital"], "Tibati")
        self.assertEqual(by["Faro-et-Deo"]["capital"], "Tignère")
        self.assertEqual(by["Adamaoua"]["population"]["value"], 884_289)
        self.assertIn("by age", by["Djerem"]["median_age"]["note"].replace("not by age", "by age"))


def ocha_row(groups, **names):
    """A row as OCHA's 2025 tables lay it out: totals and five-year groups by sex."""
    row = dict(names)
    lows = list(range(0, 80, 5))
    for low, people in zip(lows + [80], groups):
        col = f"{low:02d}_{low + 4:02d}" if low < 80 else "80Plus"
        row[f"M_{col}"] = str(people // 2)
        row[f"F_{col}"] = str(people - people // 2)
    row["M_TL"] = str(sum(int(v) for k, v in row.items() if k.startswith("M_")))
    row["F_TL"] = str(sum(int(v) for k, v in row.items() if k.startswith("F_")))
    row["T_TL"] = str(int(row["M_TL"]) + int(row["F_TL"]))
    return row


class Projection(unittest.TestCase):
    """OCHA's 2025 regions and metropolises: the newer populations, Wouri's and Mfoundi's ages."""

    REGIONS = ["Adamaoua", "Centre", "East", "Far North", "Littoral", "North", "North-West",
               "West", "South", "South-West"]

    def inputs(self, city_groups):
        young = [300_000 - 15_000 * i for i in range(17)]
        adm1 = [ocha_row(young, ADM1_FR=fr, ADM1_EN=en, ADM1_PCODE=f"CM{i:03d}")
                for i, (fr, en) in enumerate([("Adamaoua", "Adamawa"), ("Centre", "Centre"),
                                              ("Est", "East"), ("Extrême-Nord", "Far North"),
                                              ("Littoral", "Littoral"), ("Nord", "North"),
                                              ("Nord-Ouest", "North-West"), ("Ouest", "West"),
                                              ("Sud", "South"), ("Sud-Ouest", "South-West")], 1)]
        met = [ocha_row(city_groups, ADM1_PCODE="CM005", ADM2_FR="Wouri", ADM2_PCODE="CM005004",
                        Metropolis="Ville de Douala")]
        admin1 = [{"id": n, "name": n} for n in self.REGIONS]
        admin2 = [unit("W", "Wouri", "Littoral")]
        return adm1, met, admin1, admin2

    def test_regions_and_a_metropolis_with_its_own_ages(self):
        city = [200_000, 190_000, 190_000, 190_000, 180_000, 170_000, 150_000, 130_000,
                110_000, 90_000, 70_000, 50_000, 35_000, 25_000, 15_000, 10_000, 8_000]
        records, report = cc.projection(*self.inputs(city))
        by = {(r["level"], r["name"]): r for r in records}
        self.assertEqual(by[("admin1", "Centre")]["population"]["year"], 2025)
        wouri = by[("admin2", "Wouri")]
        self.assertEqual(wouri["population"]["value"], sum(city))
        self.assertIn("city of Douala", wouri["population_note"])
        self.assertIn("value", wouri["median_age"])
        # The census's sex ratio stands: none is written from the projection.
        self.assertNotIn("value", wouri["sex_ratio"])

    def test_a_metropolis_with_its_regions_ages_gets_no_median(self):
        young = [300_000 - 15_000 * i for i in range(17)]
        records, report = cc.projection(*self.inputs([g // 3 for g in young]))
        wouri = next(r for r in records if r["name"] == "Wouri")
        self.assertNotIn("value", wouri["median_age"])
        self.assertTrue(any("no median (its region's age proportions)" in line for line in report))


class Names(unittest.TestCase):
    def test_spelling(self):
        self.assertEqual(cc.spelled("MBAM & KIM"), "Mbam Et Kim")
        self.assertEqual(cc.seat_key("Koupé-Manengouba"), cc.seat_key("Koupe Et Manengouba"))
        self.assertEqual(cc.DRAWN_AS["kadey"], "Kadei")


if __name__ == "__main__":
    unittest.main()
