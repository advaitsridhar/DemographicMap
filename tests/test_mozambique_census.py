"""Mozambique's 2017 census by district and province, from INE's archived
Quadros 3, 11 and 22 (scripts/fetch_census/mozambique_census)."""

import unittest

from scripts.fetch_census import mozambique_census as mz

HEAD = ["", "", "", 0, "1 - 4"] + [f"{a} - {a + 4}" for a in range(5, 80, 5)] + ["80 e +"]
SHARE = [3, 12, 14, 13, 11, 9, 8, 7, 5, 4, 3, 3, 2, 2, 1, 1, 1, 1]   # of every 100


def ages(total):
    out = [total * s // 100 for s in SHARE]
    out[2] += total - sum(out)
    return out


def block(name, men, women):
    """A unit's three Quadro 3 lines: both sexes, men, women."""
    rows = []
    for label, n in ((name, men + women), ("Homens", men), ("Mulheres", women)):
        a = ages(n)
        if label != name:          # split each group between the sexes
            continue
        rows.append([label, n, sum(a[4:])] + a)
    am, aw = ages(men), ages(women)
    rows[0] = [name, men + women, sum(am[4:]) + sum(aw[4:])] + [x + y for x, y in zip(am, aw)]
    rows.append(["Homens", men, sum(am[4:])] + am)
    rows.append(["Mulheres", women, sum(aw[4:])] + aw)
    return rows


def q3(units):
    men = sum(m for _, m, _ in units)
    women = sum(w for _, _, w in units)
    rows = [["QUADRO 3. POPULAÇÃO POR IDADE"], ["DISTRITO, ÁREA", "", "População de 15 anos e mais"],
            ["", "TOTAL"], HEAD, ["", 1, 2, 3, 4, 5]]
    rows += block("T O T A L", men, women)
    rows += block("URBANA", men // 2, women // 2)
    for name, m, w in units:
        rows += block(name, m, w)
    return rows


NIASSA = [("CIDADE DE LICHINGA", 120, 130), ("DISTRITO DE CUAMBA", 200, 210),
          ("CIDADE DE CUAMBA", 50, 55), ("DISTRITO DE N'GAUMA", 40, 45)]


class Quadro3Test(unittest.TestCase):
    def test_units_ages_and_sexes_are_read_and_checked(self):
        table = mz.read_q3(q3(NIASSA), by="unit")
        self.assertEqual(sorted(table), sorted(["TOTAL"] + [n for n, _, _ in NIASSA]))
        self.assertEqual(table["TOTAL"]["total"], sum(m + w for _, m, w in NIASSA))
        self.assertEqual(len(table["DISTRITO DE CUAMBA"]["ages"]), 18)
        self.assertEqual(table["DISTRITO DE CUAMBA"]["ages"][0][:2], (0, 1))

    def test_a_unit_whose_ages_do_not_make_its_total_is_refused(self):
        rows = q3(NIASSA)
        for row in rows:
            if row[0] == "CIDADE DE LICHINGA":
                row[5] += 1
        with self.assertRaises(SystemExit):
            mz.read_q3(rows, by="unit")

    def test_province_lines_of_the_country(self):
        rows = q3([("NIASSA", 100, 110), ("MAPUTO CIDADE", 90, 95)])
        table = mz.read_q3(rows, by="province")
        self.assertEqual(sorted(table), ["MAPUTO CIDADE", "NIASSA", "TOTAL"])


class BindingTest(unittest.TestCase):
    SHAPES = [{"id": "l", "name": "Cidade De Lichinga"}, {"id": "c", "name": "Cuamba"},
              {"id": "n", "name": "Ngauma"}, {"id": "lake", "name": "Lago Niassa"}]

    def test_a_city_and_a_district_of_one_name_share_its_polygon(self):
        table = mz.read_q3(q3(NIASSA), by="unit")
        got = mz.bind(table, self.SHAPES, "NIASSA")
        self.assertEqual(got["l"], ["CIDADE DE LICHINGA"])
        self.assertEqual(sorted(got["c"]), ["CIDADE DE CUAMBA", "DISTRITO DE CUAMBA"])
        self.assertEqual(got["n"], ["DISTRITO DE N'GAUMA"])
        self.assertNotIn("lake", got)

    def test_a_unit_with_no_polygon_is_refused(self):
        table = mz.read_q3(q3(NIASSA), by="unit")
        with self.assertRaises(SystemExit):
            mz.bind(table, self.SHAPES[:2], "NIASSA")


class Quadros11And22Test(unittest.TestCase):
    Q11 = [["QUADRO 11."], [], ["ÁREA DE", "", "TOTAL", "RELIGIÃO"],
           ["RESIDÊNCIA,", "TOTAL", "", "CATÓLICA", "ANGLICANA", "ISLÂMICA", "ZIONE/SIÃO",
            "EVANGÉLICA/", "SEM", "OUTRA", "DESCONHEC."],
           ["IDADE E SEXO", "", "", "", "", "", "", "PENTECOSTAL", "RELIGIÃO"],
           ["", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
           ["T O T A L", 1000, 990, 300, 50, 500, 40, 60, 20, 20, 10],
           ["Homens", 480, 476, 1, 1, 1, 1, 1, 1, 1, 1]]
    Q22 = [["QUADRO 22."], ["ÁREA", "", "GRUPOS"], ["", "TOTAL", "5 - 9"],
           ["TOTAL", 800, 100], ["PORTUGUÊS", 100, 10], ["EMAKHUWA", 500, 60],
           ["CIYAO", 150, 20], ["MUDO", 5, 1], ["OUTRAS LINGUAS MOÇAMBICANAS", 15, 3],
           ["DESCONHECIDA", 30, 6], ["HOMENS", 400, 50], ["PORTUGUÊS", 60, 5]]

    def test_religion_heads_spread_over_rows_are_joined(self):
        got = mz.read_q11(self.Q11)
        self.assertEqual(got["Catholic"], 300)
        self.assertEqual(got["Evangelical/Pentecostal"], 60)
        self.assertEqual(got["No religion"], 20)
        self.assertEqual(got["Zionist churches"], 40)
        self.assertEqual(got["UNKNOWN"], 10)

    def test_religions_must_make_the_total(self):
        rows = [list(r) for r in self.Q11]
        rows[6][3] += 7
        with self.assertRaises(SystemExit):
            mz.read_q11(rows)

    def test_mother_tongue_block_and_the_unstated(self):
        got = mz.read_q22(self.Q22)
        self.assertEqual(got["Makhuwa"], 500)
        self.assertEqual(got["UNSTATED"], 35)
        self.assertEqual(got["Other Mozambican languages"], 15)
        self.assertNotIn("Mudo", got)


class BuildTest(unittest.TestCase):
    def test_districts_and_provinces(self):
        prov = mz.read_q3(q3(NIASSA), by="unit")
        nat = {name: mz.summed(prov, ["TOTAL"]) for name in mz.PROVINCES}
        q11 = Quadros11And22Test.Q11
        q22 = Quadros11And22Test.Q22
        tables = {"national": nat, "q3": {"NIASSA": prov},
                  "q11": {n: mz.read_q11(q11) for n in mz.PROVINCES},
                  "q22": {n: mz.read_q22(q22) for n in mz.PROVINCES}}
        names = sorted({spec["map"] for spec in mz.PROVINCES.values()})
        admin1 = [{"id": f"P{i}", "name": n} for i, n in enumerate(names)]
        niassa = [a for a in admin1 if a["name"] == "Niassa"][0]["id"]
        admin2 = [dict(s, parent=niassa) for s in BindingTest.SHAPES]
        recs = mz.build(tables, admin1, admin2)
        by = {r["shape_id"]: r for r in recs}
        cuamba = by["c"]
        self.assertEqual(cuamba["population"]["value"], 200 + 210 + 50 + 55)
        self.assertIn("added together", cuamba["population_note"])
        self.assertEqual(cuamba["sex_ratio"]["value"], round(1000 * 250 / 265))
        self.assertEqual(cuamba["religion"]["status"], "not_available")
        self.assertIn("Quadro 11", cuamba["religion"]["note"])
        self.assertNotIn("lake", by)
        maputo = by[[a for a in admin1 if a["name"] == "Maputo"][0]["id"]]
        self.assertIn("Maputo Province and Maputo City", maputo["population_note"])
        # The quadros count the people enumerated, below INE's adjusted total.
        for rec in (cuamba, maputo):
            self.assertIn("count the people enumerated", rec["population_note"])
            self.assertIn("27,909,798", rec["population_note"])
        self.assertEqual(maputo["religion"][0]["group"], "Islam")
        self.assertEqual(maputo["language_basis"], mz.LANGUAGE_BASIS)
        self.assertIn("aged 5 and over", maputo["language_note"])


if __name__ == "__main__":
    unittest.main()
