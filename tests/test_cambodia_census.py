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
        # The note names the census once, and a polygon summed from communes
        # says so in a clause of its own.
        for rec in recs.values():
            note = rec.get("population_note", "")
            if note:
                self.assertTrue(note.startswith("The 2019 census's count of "), note)
                self.assertNotIn("The 2019 census:", note)
                self.assertNotIn(" -- ", note)
        summed = [r["population_note"] for r in recs.values()
                  if "communes of" in r.get("population_note", "")]
        self.assertTrue(summed)
        for note in summed:
            self.assertIn(", which lie in the district as it was drawn in 2018: people in "
                          "normal or regular households", note)

    def test_a_province_s_note_names_the_census_once(self):
        adm1 = [{"ADM1_PCODE": "KH01", "ADM1_EN": "Banteay Meanchey"}]

        def bind(iso3, level, rows, unit_col, parent_col):
            return ({0: {"id": "P1", "name": "Banteay Meanchey"}}, [], [])
        with mock.patch.object(kh, "bind_rows", bind):
            rec = kh.province_records({1: (40, 60, 100)}, adm1)[0]
        self.assertEqual(rec["population_note"],
                         "The 2019 census's count of the province's whole population, "
                         "migrants working abroad left out (Table 2.1.1).")

    def low_household_records(self):
        placed, _, broken = kh.crosswalk(annex_2019(), ADM3, ADM2)
        adm2 = [{"ADM2_PCODE": "KH0102", "ADM2_EN": "Mongkol Borei",
                 "ADM1_EN": "Banteay Meanchey"},
                {"ADM2_PCODE": "KH0103", "ADM2_EN": "Phnum Srok", "ADM1_EN": "Banteay Meanchey"}]

        def bind(iso3, level, rows, unit_col, parent_col):
            return ({i: {"id": r["ADM2_PCODE"], "name": r["ADM2_EN"]}
                     for i, r in enumerate(rows)}, [], [])
        with mock.patch.object(kh, "bind_rows", bind):
            return {r["shape_id"]: r for r in kh.district_records(
                annex_2019(), placed, broken, adm2, low={1: 0.709})}

    def test_a_province_below_the_floor_states_why_and_displaces_the_undercount(self):
        """Preah Sihanouk: its district tables leave out 29% of the province, and
        Wikidata's 2019 district figures are those same undercounts."""
        recs = self.low_household_records()
        pop = recs["KH0103"]["population"]
        self.assertEqual(pop["status"], kh.NOT_AVAILABLE)
        self.assertIn("lived outside them", pop["note"])
        self.assertEqual(pop["displaces_before"], 2020)
        self.assertNotIn("displaces_before", recs["KH0103"]["sex_ratio"])

    def test_the_build_drops_an_encyclopaedia_figure_of_the_census_year(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import build_entities as be
        row = dict(self.low_household_records()["KH0103"], _source=kh.OUT)
        for year, kept in ((2019, False), (2023, True)):
            entity = {"population": {"value": 73036, "year": year, "source": "Wikidata (CC0)"},
                      "_from": {"population": "wikidata_admin2.json"}, "sources": []}
            be.merge_adapter(entity, dict(row))
            self.assertEqual("value" in entity["population"], kept, year)


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

    def test_a_namesake_in_another_district_does_not_take_a_commune(self):
        # Siem Reap's "Sambuor" is the city's own sangkat, spelt "Sambour" there
        # in 2018, though Kralanh has a commune spelt exactly "Sambuor"; and a
        # sangkat divided since 2018 ("Ti 2") stays with its district.
        adm2 = {"KH1706": "Kralanh", "KH1710": "Siem Reap"}
        adm3 = [{"ADM3_PCODE": "KH170601", "ADM3_EN": "Sambuor", "ADM2_PCODE": "KH1706"},
                {"ADM3_PCODE": "KH171001", "ADM3_EN": "Sambour", "ADM2_PCODE": "KH1710"},
                {"ADM3_PCODE": "KH171002", "ADM3_EN": "Sla Kram", "ADM2_PCODE": "KH1710"}]
        n = (1, 4, 2, 2)
        annex = {17: {"name": "Siemreap", "n": None, "districts": {
            1706: {"name": "Kralanh", "n": n, "communes": {170601: {"name": "Sambuor", "n": n}}},
            1710: {"name": "Krong Siem Reab", "n": n, "communes": {
                171008: {"name": "Sambuor", "n": n},
                171002: {"name": "Sla Kram", "n": n},
                171013: {"name": "Sla Kram Ti 2", "n": n}}}}}}
        placed, left, broken = kh.crosswalk(annex, adm3, adm2)
        self.assertEqual(sorted(c for _, c, _ in placed["KH1710"]), [171002, 171008, 171013])
        self.assertEqual([c for _, c, _ in placed["KH1706"]], [170601])
        self.assertEqual((left, broken), ([], set()))

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
