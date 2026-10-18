"""Morocco's 2024 medians from HCP's regional workbooks and provincial notes."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import morocco_rgph2024_ages as ma  # noqa: E402

LABELS = ["0-4 ans", "5-9 ans", "10-14 ans", "15-19 ans", "20-24 ans", "25-29 ans",
          "30-34 ans", "35-39 ans", "40-44 ans", "45-49 ans", "50-54 ans", "55-59 ans",
          "60-64 ans", "65-69 ans", "70-74 ans", "75 ans et plus"]
# Préfecture de Rabat, Tableau 5 of HCP's provincial series.
RABAT = [4.5, 5.9, 6.8, 6.8, 7.1, 6.8, 6.7, 6.5, 6.9, 6.8, 6.9, 6.6, 6.5, 5.3, 4.2, 5.7]

ANNEX = """Province de Tétouan Région TTA
Milieu  Masculin Féminin Ensemble Masculin Féminin Ensemble
Urbain
Âge quinquennal (%)
0-4 ans 6,9 6,3 6,6 8,1 7,5 7,8
Rural
Âge quinquennal (%)
0-4 ans 8,8 8,7 8,7 8,8 8,9 8,8
Ensemble
Population municipale 304 418 303 469 607 887 2 035 494 1 973 161 4 008 655
Sexe (%) 50,1 49,9 100 50,8 49,2 100
Âge quinquennal (%)
0-4 ans 7,5 7,0 7,2 8,4 8,0 8,2
5-9 ans 9,2 8,7 9,0 9,7 9,4 9,6
10-14 ans 9,5 9,1 9,3 9,5 9,2 9,4
15-19 ans 8,3 8,1 8,2 8,0 7,9 7,9
20-24 ans 7,3 7,4 7,4 7,6 7,8 7,7
25-29 ans 6,8 7,1 7,0 7,6 7,8 7,7
30-34 ans 7,5 7,8 7,6 8,2 8,1 8,2
35-39 ans 7,5 7,6 7,5 7,9 7,8 7,8
40-44 ans 7,0 7,1 7,0 7,0 6,9 7,0
45-49 ans 6,0 6,1 6,0 5,7 5,8 5,7
50-54 ans 5,4 5,6 5,5 5,0 5,1 5,0
55-59 ans 4,6 4,9 4,7 4,0 4,3 4,1
60-64 ans 4,7 4,8 4,7 4,0 4,3 4,2
65-69 ans 3,4 3,3 3,3 3,0 2,9 2,9
70-74 ans 2,4 2,3 2,4 2,1 2,1 2,1
75 ans ou plus 3,0 3,3 3,1 2,4 2,7 2,6
"""


class Medians(unittest.TestCase):
    def test_rabat(self):
        groups = [(*ma.bounds(label), share) for label, share in zip(LABELS, RABAT)]
        ma.check("Rabat", groups)
        self.assertEqual(ma.median(groups), 39.2)

    def test_the_workbook_rows_by_code(self):
        rows = [["Milieu de résidence : Ensemble"],
                ["", "", "Population légale", "Population municipale", "Sexe (%)", ""]
                + ["Âge quinquennal (%)"],
                ["Code géographique", "Collectivités territoriales", "", "", "Masculin",
                 "Féminin"] + LABELS + LABELS,
                [None, "Ensemble du territoire national", 1, 1, 50, 50] + RABAT + RABAT,
                [4, "Région de Rabat-Salé-Kénitra", 1, 1, 50, 50] + RABAT + RABAT,
                [4421, "Préfecture de Rabat", 1, 1, 48, 52] + RABAT + RABAT,
                [4421010, "Commune de Rabat", 1, 1, 48, 52] + RABAT + RABAT]
        units = ma.read_workbook(rows)
        self.assertEqual(sorted(units), [4, 4421])
        self.assertEqual(ma.median(units[4421]["groups"]), 39.2)

    def test_shares_that_do_not_make_a_hundred_stop_the_run(self):
        groups = [(*ma.bounds(label), share) for label, share in zip(LABELS, RABAT)]
        groups[3] = (15, 19, 16.8)
        with self.assertRaises(SystemExit):
            ma.check("Rabat", groups)

    def test_the_annex_gives_the_province_and_the_region(self):
        province, region = ma.read_annex(ANNEX)
        self.assertEqual(len(province), 16)
        self.assertEqual(province[0], (0, 4, 7.2))
        self.assertEqual(region[-1], (75, None, 2.6))
        ma.check("Tétouan", province)
        self.assertEqual(ma.median(province), 31.2)        # 48.1% under 30


class Series(unittest.TestCase):
    def test_the_first_whole_table_of_men_women_and_both(self):
        text = "\n".join(["Répartition selon le groupe d'âges quinquennal",
                          "0-4 ans 7,7 7 7,3"]
                         + [f"{lo}-{lo + 4} ans 6 6 {s}".replace(".", ",")
                            for lo, s in zip(range(5, 75, 5), RABAT[1:15])]
                         + ["75ans et + 3,9 4,1 4", "0-4 ans 1 1 1"])
        groups = ma.read_series(text)
        self.assertEqual(len(groups), 16)
        self.assertEqual(groups[0], (0, 4, 7.3))
        self.assertEqual(groups[-1], (75, None, 4.0))

    def milieu_table(self, ages):
        """Urban, rural and both milieux, men, women and both, at each age."""
        rows = []
        for (label, share) in ages:
            urban, rural = share - 0.2, share + 0.6
            rows.append(f"{label} " + " ".join(
                f"{v:.1f}".replace(".", ",") for v in
                (urban + 0.1, urban - 0.1, urban, rural + 0.1, rural - 0.1, rural,
                 share + 0.1, share - 0.1, share)))
        return rows

    def test_a_table_by_milieu_and_sex_gives_both_milieux_column(self):
        ages = list(zip(["0-4ans"] + LABELS[1:15] + ["75 et+"], RABAT))
        # A table by sex only, further on, is not the one read.
        text = "\n".join(["Figure 7 : Population par milieu de résidence, sexe et âge"]
                         + self.milieu_table(ages) + ["0-4 ans 1 1 1"])
        groups = ma.read_series(text)
        self.assertEqual([s for _, _, s in groups], RABAT)
        self.assertEqual(groups[-1][:2], (75, None))

    def test_a_table_by_milieu_that_does_not_add_up_stops_the_run(self):
        ages = list(zip(["0-4ans"] + LABELS[1:15] + ["75 et+"], RABAT))
        rows = self.milieu_table(ages)
        # Both milieux put before the urban: the last column is the rural's.
        cut = rows[3].split()
        values = cut[2:]
        rows[3] = " ".join(cut[:2] + values[6:] + values[:6])
        with self.assertRaises(SystemExit):
            ma.read_series("\n".join(rows))

    def test_decimals_with_points_and_one_broken_by_a_space(self):
        self.assertEqual(ma.values_of("3.0 3.7 3. 4 5.3 5.9 5.7 4.5 5.2 4.9"),
                         [3.0, 3.7, 3.4, 5.3, 5.9, 5.7, 4.5, 5.2, 4.9])
        self.assertEqual(ma.values_of("7,7 7 7,3"), [7.7, 7.0, 7.3])

    def test_a_note_named_in_its_own_spelling(self):
        names = ("Préfecture d'Agadir-Ida-Ou-Tanane", "Préfecture d'Inezgane-Aït Melloul")
        self.assertEqual(ma.named_in(["", "Préfecture d’Inzegane Ait Melloul"], names),
                         ["Préfecture d'Inezgane-Aït Melloul"])
        self.assertEqual(ma.named_in(["", "Préfecture d’Agadir Ida Outanane"], names),
                         ["Préfecture d'Agadir-Ida-Ou-Tanane"])

    def test_shares_that_do_not_make_the_dashboard_s_stop_the_run(self):
        groups = [(*ma.bounds(label), share) for label, share in zip(LABELS, RABAT)]
        ma.broad_check("Rabat", groups, {(0, 14): 17.2, (60, None): 21.7})
        with self.assertRaises(SystemExit):
            ma.broad_check("Rabat", groups, {(0, 14): 26.5, (60, None): 21.7})


class Building(unittest.TestCase):
    def test_medians_where_published_and_reasons_elsewhere(self):
        table = {"regions": {4: {"name": "Rabat-Salé-Kénitra"},
                             10: {"name": "Guelmim-Oued Noun"}},
                 "provinces": {4421: {"name": "Préfecture de Rabat"},
                               10151: {"name": "Province d'Assa-Zag"}}}
        bound = [{"level": "admin1", "name": "R", "shape_id": "R", "codes": {"hcp": "4"},
                  "population": {"value": 1}},
                 {"level": "admin1", "name": "G", "shape_id": "G", "codes": {"hcp": "10"},
                  "population": {"value": 1}},
                 {"level": "admin2", "name": "P", "shape_id": "P", "codes": {"hcp": "4421"},
                  "population": {"value": 1}},
                 {"level": "admin2", "name": "A", "shape_id": "A", "codes": {"hcp": "10151"},
                  "population": {"value": 1}}]
        groups = [(*ma.bounds(label), share) for label, share in zip(LABELS, RABAT)]
        ages = {"rabat": {"groups": groups, "source": "HCP", "url": "u", "how": ""}}
        with mock.patch.object(ma.legal, "build", return_value=(bound, [])):
            records, _ = ma.build(table, [], [], ages)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["P"]["median_age"]["value"], 39.2)
        self.assertIn("31.3 years", by["G"]["median_age"]["note"])
        self.assertIn("Al Mahbass", by["G"]["median_age"]["note"])
        self.assertEqual(by["A"]["median_age"]["note"], ma.ONLY_SHARES)
        self.assertEqual(by["R"]["median_age"]["note"], ma.ONLY_SHARES)


if __name__ == "__main__":
    unittest.main()
