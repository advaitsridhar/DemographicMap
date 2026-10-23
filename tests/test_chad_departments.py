"""Chad's provinces for 2023, their ages, the departments' 2024 figures and seats (no network)."""

import unittest
from unittest import mock

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

LOWS = list(range(0, 80, 5))


def province(name, groups, men_share=0.5):
    """An OCHA row: five-year groups 0-4 ... 75-79 and 80+, split by sex."""
    row = {"ADM1_NAME": name}
    total = sum(groups)
    for low, people in zip(LOWS + [80], groups):
        col = f"{low:02d}_{low + 4:02d}" if low < 80 else "80Plus"
        row[f"M_{col}"] = str(round(people * men_share))
        row[f"F_{col}"] = str(people - round(people * men_share))
    row["M_TL"] = str(sum(int(row[k]) for k in row if k.startswith("M_") and k != "M_TL"))
    row["F_TL"] = str(sum(int(row[k]) for k in row if k.startswith("F_") and k != "F_TL"))
    row["T_TL"] = str(total)
    return row


YOUNG = [1000 - 50 * i for i in range(17)]


class Seats(unittest.TestCase):
    def test_names_and_seats(self):
        seat_of = cd.seats(WIKI)
        self.assertEqual(seat_of[cd.key("Abdi")], "Abdi")
        self.assertEqual(seat_of[cd.key("Bahr-Azoum")], "Am Timan")    # Bahr and Barh made one
        self.assertEqual(seat_of[cd.key("Grande Sido")], "Maro")
        self.assertNotIn(cd.key("Wadi Hawar"), seat_of)
        _, listed = cd.listed_seats(WIKI)
        self.assertIn(cd.key("Wadi Hawar"), listed)

    def test_build(self):
        adm1 = [{"ADM1_NAME": "N'Djamena", "T_TL": "18000000"},
                {"ADM1_NAME": "Salamat", "T_TL": "496719"}]
        admin1 = [{"id": "N", "name": "N'Djamena Region"}, {"id": "S", "name": "Salamat"}]
        admin2 = [{"id": "a", "name": "Bahr-Azoum", "parent": "S"},
                  {"id": "b", "name": "N'Djaména", "parent": "N"},
                  {"id": "c", "name": "Fouli", "parent": "S"},
                  {"id": "d", "name": "Wadi Hawar", "parent": "S"}]
        seat_of, listed = cd.listed_seats(WIKI)
        records, report = cd.build(adm1, seat_of, admin1, admin2, listed)
        by = {(r["level"], r["name"]): r for r in records}
        self.assertEqual(by[("admin1", "Salamat")]["population"]["value"], 496_719)
        self.assertEqual(by[("admin1", "Salamat")]["population"]["year"], 2023)
        self.assertEqual(by[("admin1", "Salamat")]["population_note"],
                         "INSEED's projection of the population of Salamat for 2023, from the "
                         "2009 census (RGPH2), as OCHA publishes it.")
        self.assertEqual(by[("admin2", "Bahr-Azoum")]["capital"], "Am Timan")
        self.assertEqual(by[("admin2", "N'Djaména")]["capital"], "N'Djamena")
        # A department the list leaves out, and one it names without a seat.
        self.assertIn("does not include this department",
                      by[("admin2", "Fouli")]["capital"]["note"])
        self.assertIn("names this department but gives no seat",
                      by[("admin2", "Wadi Hawar")]["capital"]["note"])
        self.assertTrue(any("Fouli: no seat named" in line for line in report))
        # Each reason cites the list it rests on; N'Djaména's seat OCHA's tables.
        self.assertEqual([s["field"] for s in by[("admin2", "Fouli")]["sources"]],
                         ["capital note"])
        self.assertEqual([s["field"] for s in by[("admin2", "N'Djaména")]["sources"]],
                         ["capital"])

    def test_too_few_people_refused(self):
        with self.assertRaises(SystemExit):
            cd.build([{"ADM1_NAME": "Salamat", "T_TL": "496719"}], {},
                     [{"id": "S", "name": "Salamat"}], [])


class Structures(unittest.TestCase):
    """Ennedi Est and Ennedi Ouest carry one structure; Guéra's 10-14 group is impossible."""

    def rows(self):
        other = [1000 - 40 * i for i in range(17)]
        guera = list(YOUNG)
        guera[2] = 3 * guera[1]
        return [province("Ennedi Est", [2 * g for g in YOUNG], 0.53),
                province("Ennedi Ouest", YOUNG, 0.53),
                province("Batha", other, 0.49),
                province("Guéra", guera, 0.49)]

    def test_copied_and_impossible_structures_are_withdrawn(self):
        out, report = cd.structures(self.rows())
        self.assertEqual(set(out[cd.key("Ennedi Est")]), {"median_age", "sex_ratio"})
        self.assertIn("Ennedi Ouest", out[cd.key("Ennedi Est")]["median_age"])
        self.assertEqual(set(out[cd.key("Guéra")]), {"median_age"})
        self.assertIn("3.0 times as many", out[cd.key("Guéra")]["median_age"])
        self.assertNotIn(cd.key("Batha"), out)

    def test_the_reasons_displace_ochas_figures(self):
        admin1 = [{"id": k, "name": n} for k, n in
                  (("E", "Ennedi Est"), ("W", "Ennedi Ouest"), ("B", "Batha"), ("G", "Guéra"))]
        with mock.patch.object(cd, "NATIONAL_MIN", 0):
            records, _ = cd.build(self.rows(), {}, admin1, [])
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Guéra"]["median_age"]["displaces_before"], cd.YEAR + 1)
        self.assertNotIn("displaces_before", by["Batha"]["median_age"])
        self.assertNotIn("note", by["Batha"]["median_age"])
        self.assertIn("median_age note", by["Ennedi Est"]["sources"][0]["field"])


class Departments2024(unittest.TestCase):
    def test_the_2024_table_and_each_provinces_proportion(self):
        rows = [["ADM1_NAME", "ADM1_Pcode", "ADM2_NAME", "ADM2_Pcode", "Population_Projection_2024"],
                ["Salamat", "TD15", "Bahr-Azoum", "TD1501", 310249.44],
                ["Salamat", "TD15", "Aboudéia", "TD1502", 110127.8],
                ["Barh-El-Gazel", "TD19", "Barh-El-Gazel Oues", "TD1903", 102414.6],
                ["Sila", "TD21", "Kimiti", "TD2101", 680903.7]]
        admin2 = [{"id": "a", "name": "Bahr-Azoum"}, {"id": "b", "name": "Barh-El-Gazel Ouest"},
                  {"id": "c", "name": "Aboudéia"}, {"id": "k", "name": "Kimiti"}]
        previous = {cd.key("Bahr-Azoum"): 279_400, cd.key("Barh-El-Gazel Ouest"): 92_224,
                    cd.key("Aboudéia"): 99_182, cd.key("Kimiti"): 457_997}
        counts, report = cd.departments_2024(rows, previous, admin2)
        self.assertEqual(counts["a"]["value"], 310_249)
        self.assertEqual(counts["b"]["year"], 2024)
        self.assertIn("all of Salamat's departments by one proportion (11.0%)", counts["a"]["note"])
        self.assertIn("by one proportion (48.7%)", counts["k"]["note"])
        held = cd.held_2024(counts, admin2)
        dep = next(r for r in held if r["name"] == "Bahr-Azoum")
        self.assertEqual(dep["population"]["value"], 310_249)
        self.assertEqual(dep["population"]["year"], 2024)
        self.assertEqual(dep["match_by"], "shape_id")
        # The seats' records carry no population of their own.
        records, _ = cd.build([{"ADM1_NAME": "Salamat", "T_TL": "18000000"}], {},
                              [{"id": "S", "name": "Salamat"}], admin2, set())
        seat = next(r for r in records if r["name"] == "Bahr-Azoum")
        self.assertNotIn("value", seat["population"])


if __name__ == "__main__":
    unittest.main()
