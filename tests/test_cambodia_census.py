"""Cambodia: district and province populations and sex ratios, 2019 census.

No network: the annex pages and the 2018 gazetteer are built here.
"""

import unittest
from unittest import mock

from scripts.fetch_census import cambodia_census as kh

PAGE = """Table P-01. Total Population Banteay Meancheay 2019
Province/District/ Commune No. Population Sex Household
Household Ratio Size
Total Male Female
01 Banteay Meanchey
Total 10 40 20 20 100.0 4.0
Urban 4 16 8 8 100.0 4.0
Rural 6 24 12 12 100.0 4.0
102 Mongkol Borei 6 24 12 12 100.0 4.0
10201 Banteay Neang 3 12 6 6 100.0 4.0
10202 Bat Trang 3 12 6 6 100.0 4.0
103 Phnum Srok 4 16 8 8 100.0 4.0
10301 Nam Tau 4 16 8 8 100.0 4.0
Based on normal or regular households.
148"""


class AnnexTest(unittest.TestCase):
    def test_provinces_districts_and_communes(self):
        annex = kh.parse_annex([PAGE])
        prov = annex[1]
        self.assertEqual(prov["n"], (10, 40, 20, 20))
        self.assertEqual(sorted(prov["districts"]), [102, 103])
        self.assertEqual(sorted(prov["districts"][102]["communes"]), [10201, 10202])
        self.assertEqual(prov["districts"][103]["n"], (4, 16, 8, 8))

    def test_a_misprinted_district_code_is_read_from_its_communes(self):
        page = PAGE.replace("103 Phnum Srok", "211 Phnum Srok")
        annex = kh.parse_annex([page])
        self.assertEqual(annex[1]["districts"][103]["name"], "Phnum Srok")
        self.assertEqual(sorted(annex[1]["districts"][103]["communes"]), [10301])

    def full(self):
        """25 provinces of one district and one commune each."""
        out = {}
        for p in range(1, 26):
            n = (1, 4, 2, 2)
            out[p] = {"name": f"P{p}", "n": n, "districts": {
                p * 100 + 1: {"name": f"D{p}", "n": n,
                              "communes": {p * 10000 + 101: {"name": f"C{p}", "n": n}}}}}
        return out

    def test_a_district_row_at_odds_with_itself_is_its_communes_sum(self):
        annex = self.full()
        annex[3]["districts"][301]["n"] = (5, 5, 5, 5)
        kh.check_annex(annex)
        self.assertEqual(annex[3]["districts"][301]["n"], (1, 4, 2, 2))

    def test_a_name_wrapped_onto_its_figures_line(self):
        page = PAGE.replace("10202 Bat Trang 3 12 6 6 100.0 4.0",
                            "10202 Bat Trang\nCheung 3 12 6 6 100.0 4.0")
        annex = kh.parse_annex([page])
        self.assertEqual(annex[1]["districts"][102]["communes"][10202]["name"],
                         "Bat Trang Cheung")

    def test_a_name_and_its_figures_on_two_more_lines(self):
        page = PAGE.replace("10202 Bat Trang 3 12 6 6 100.0 4.0",
                            "10202 Bat Trang\nCheung\n3 12 6 6 100.0 4.0")
        annex = kh.parse_annex([page])
        self.assertEqual(annex[1]["districts"][102]["communes"][10202]["n"], (3, 12, 6, 6))

    def test_a_misspelt_total_row(self):
        annex = kh.parse_annex([PAGE.replace("Total 10 40", "Toatl 10 40")])
        self.assertEqual(annex[1]["n"], (10, 40, 20, 20))

    def test_a_province_total_row_the_households_and_whole_population_overrule(self):
        annex = self.full()
        annex[5]["n"] = (1, 3, 1, 2)          # people misprinted, households right
        kh.check_annex(annex, {p: (2, 2, 5) for p in range(1, 26)})
        self.assertEqual(annex[5]["n"], (1, 4, 2, 2))
        annex = self.full()
        annex[5]["n"] = (1, 3, 1, 2)
        with self.assertRaises(SystemExit):   # without the whole population, no ruling
            kh.check_annex(annex)

    def test_a_district_its_communes_do_not_make_refuses(self):
        annex = self.full()
        kh.check_annex(annex)
        annex[3]["districts"][301]["communes"][30101]["n"] = (1, 4, 3, 1)
        with self.assertRaises(SystemExit):
            kh.check_annex(annex)


ADM2 = {"KH0102": "Mongkol Borei", "KH0103": "Phnum Srok"}
ADM3 = [{"ADM3_PCODE": "KH010201", "ADM3_EN": "Banteay Neang", "ADM2_PCODE": "KH0102"},
        {"ADM3_PCODE": "KH010202", "ADM3_EN": "Bat Trang", "ADM2_PCODE": "KH0102"},
        {"ADM3_PCODE": "KH010301", "ADM3_EN": "Nam Tau", "ADM2_PCODE": "KH0103"}]


def annex_2019():
    """District 102 keeps Banteay Neang and gains a new commune; Bat Trang moved to a
    district made in 2019 (111)."""
    return {1: {"name": "Banteay Meanchey", "n": (10, 40, 20, 20), "districts": {
        102: {"name": "Mongkol Borei", "n": (4, 16, 8, 8), "communes": {
            10201: {"name": "Banteay Neang", "n": (3, 12, 6, 6)},
            10203: {"name": "Somewhere New", "n": (1, 4, 2, 2)}}},
        103: {"name": "Phnum Srok", "n": (4, 16, 8, 8), "communes": {
            10301: {"name": "Nam Tau", "n": (4, 16, 8, 8)}}},
        111: {"name": "Krong New", "n": (2, 8, 4, 4), "communes": {
            11101: {"name": "Bat Trang", "n": (2, 8, 4, 4)}}}}}}


class CrosswalkTest(unittest.TestCase):
    def test_communes_go_to_their_2018_district(self):
        placed, left, broken = kh.crosswalk(annex_2019(), ADM3, ADM2)
        self.assertEqual(sorted(c for _, c, _ in placed["KH0102"]), [10201, 10203, 11101])
        self.assertEqual([c for _, c, _ in placed["KH0103"]], [10301])
        self.assertEqual((left, broken), ([], set()))

    def test_a_new_khan_goes_to_the_district_it_was_cut_from(self):
        adm3 = [{"ADM3_PCODE": "KH120101", "ADM3_EN": "Boeng Keng Kang Ti Muoy",
                 "ADM2_PCODE": "KH1201"},
                {"ADM3_PCODE": "KH120102", "ADM3_EN": "Tonle Basak", "ADM2_PCODE": "KH1201"}]
        n = (1, 4, 2, 2)
        annex = {12: {"name": "Phnom Penh", "n": None, "districts": {
            1201: {"name": "Chamkar Mon", "n": n, "communes": {
                120102: {"name": "Tonle Basak", "n": n}}},
            1213: {"name": "Boeng Keng Kang", "n": n, "communes": {
                121301: {"name": "Boeng Keng Kang Muoy", "n": n},
                121304: {"name": "Oulampik", "n": n}}}}}}
        placed, left, broken = kh.crosswalk(annex, adm3, {"KH1201": "Chamkar Mon"})
        self.assertEqual(sorted(c for _, c, _ in placed["KH1201"]), [120102, 121301, 121304])
        self.assertEqual((left, broken), ([], set()))

    def test_records_sum_the_parts_and_check_a_whole_district(self):
        placed, _, broken = kh.crosswalk(annex_2019(), ADM3, ADM2)
        adm2 = [{"ADM2_PCODE": "KH0102", "ADM2_EN": "Mongkol Borei",
                 "ADM1_EN": "Banteay Meanchey"},
                {"ADM2_PCODE": "KH0103", "ADM2_EN": "Phnum Srok", "ADM1_EN": "Banteay Meanchey"}]

        def bind(iso3, level, rows, unit_col, parent_col):
            return ({i: {"id": r["ADM2_PCODE"], "name": r["ADM2_EN"]}
                     for i, r in enumerate(rows)}, [], [])
        with mock.patch.object(kh, "bind_rows", bind):
            recs = {r["shape_id"]: r for r in kh.district_records(annex_2019(), placed, broken,
                                                                  adm2)}
        self.assertEqual(recs["KH0102"]["population"]["value"], 24)
        self.assertIn("Krong New", recs["KH0102"]["population_note"])
        self.assertEqual(recs["KH0103"]["population"]["value"], 16)
        self.assertEqual(recs["KH0103"]["sex_ratio"]["value"], 100.0)
        self.assertIn("regular households", recs["KH0103"]["population_note"])


def renumbered():
    """Tboung Khmum: the census numbers its districts and communes afresh, so its
    2501 is Krong Suong where the 2018 gazetteer's KH2501 is Dambae."""
    adm2 = {"KH2501": "Dambae", "KH2506": "Suong"}
    adm3 = [{"ADM3_PCODE": "KH250101", "ADM3_EN": "Chong Cheach", "ADM2_PCODE": "KH2501"},
            {"ADM3_PCODE": "KH250102", "ADM3_EN": "Dambae", "ADM2_PCODE": "KH2501"},
            {"ADM3_PCODE": "KH250601", "ADM3_EN": "Suong", "ADM2_PCODE": "KH2506"},
            {"ADM3_PCODE": "KH250602", "ADM3_EN": "Vihear Luong", "ADM2_PCODE": "KH2506"}]
    annex = {25: {"name": "Tboung Khmum", "n": (6, 24, 12, 12), "districts": {
        2501: {"name": "Krong Suong", "n": (2, 8, 4, 4), "communes": {
            250101: {"name": "Suong", "n": (1, 4, 2, 2)},
            250102: {"name": "Vihear Luong", "n": (1, 4, 2, 2)}}},
        2505: {"name": "Dambae", "n": (4, 16, 8, 8), "communes": {
            250501: {"name": "Chong Cheach", "n": (2, 8, 4, 4)},
            250502: {"name": "Dambae", "n": (2, 8, 4, 4)}}}}}}
    return annex, adm3, adm2


class RenumberedTest(unittest.TestCase):
    def test_a_code_whose_name_differs_is_another_communes(self):
        annex, adm3, adm2 = renumbered()
        placed, left, broken = kh.crosswalk(annex, adm3, adm2)
        self.assertEqual(sorted(c for _, c, _ in placed["KH2506"]), [250101, 250102])
        self.assertEqual(sorted(c for _, c, _ in placed["KH2501"]), [250501, 250502])
        self.assertEqual((left, broken), ([], set()))

    def test_districts_are_matched_by_name_not_code(self):
        annex, _, adm2 = renumbered()
        self.assertEqual(kh.homes(annex, adm2), {2501: "KH2506", 2505: "KH2501"})
        annex = {2: {"name": "Battambang", "districts": {
            203: {"name": "Krong Bat Dambang"}, 211: {"name": "Phnom Proek"}}},
            12: {"name": "Phnom Penh", "districts": {
                1207: {"name": "Ruessei Kaev"}, 1214: {"name": "Kambol"}}}}
        adm2 = {"KH0203": "Battambang", "KH0211": "Phnum Proek", "KH1201": "Chamkar Mon",
                "KH1207": "Russey Keo", "KH1205": "Dangkao"}
        self.assertEqual(kh.homes(annex, adm2), {203: "KH0203", 211: "KH0211",
                                                 1207: "KH1207"})

    def test_a_commune_away_from_its_own_district_refuses(self):
        annex, adm3, adm2 = renumbered()
        # The census puts Suong's commune under Dambae, where the gazetteer has
        # it in Suong: a misreading or an undeclared transfer.
        annex[25]["districts"][2505]["communes"][250503] = {"name": "Vihear Luong",
                                                            "n": (1, 4, 2, 2)}
        del annex[25]["districts"][2501]["communes"][250102]
        with self.assertRaises(SystemExit):
            kh.crosswalk(annex, adm3, adm2)

    def test_a_renumbered_district_comes_back_to_its_own_row(self):
        annex, adm3, adm2 = renumbered()
        placed, _, broken = kh.crosswalk(annex, adm3, adm2)
        rows = [{"ADM2_PCODE": pc, "ADM2_EN": name, "ADM1_EN": "Tboung Khmum"}
                for pc, name in adm2.items()]

        def bind(iso3, level, rows, unit_col, parent_col):
            return ({i: {"id": r["ADM2_PCODE"], "name": r["ADM2_EN"]}
                     for i, r in enumerate(rows)}, [], [])
        with mock.patch.object(kh, "bind_rows", bind):
            recs = {r["shape_id"]: r for r in kh.district_records(annex, placed, broken, rows)}
        self.assertEqual(recs["KH2501"]["population"]["value"], 16)
        self.assertIn("Dambae district", recs["KH2501"]["population_note"])
        self.assertEqual(recs["KH2506"]["population"]["value"], 8)
        self.assertIn("Krong Suong district", recs["KH2506"]["population_note"])
        annex[25]["districts"][2505]["n"] = (4, 18, 9, 9)     # its row no longer its sum
        with mock.patch.object(kh, "bind_rows", bind), self.assertRaises(SystemExit):
            kh.district_records(annex, placed, broken, rows)


if __name__ == "__main__":
    unittest.main()
