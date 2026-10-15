"""Round 6, notes partition, repairs: Cabo Verde's municipalities and their only
parishes on the 2021 census, Tarfaya's part across the Western Sahara line,
Caió's polygons citing their table, and record ids that name their level.
No network."""

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import cabo_verde_parishes as cv  # noqa: E402

# Tabela 7 of INE's report on the 2021 census, as its page reads (the lines
# between the title and the source line).
TABLE_7 = """(RF), Cabo Verde, 2021
Sexo
RF
Concelho Ambos os sexos Masculino Feminino
(%)
Efetivos % Efetivos % Efetivos %
Cabo Verde 491 233 100,0 246 363 100,0 244 870 100,0 99,4
Ribeira Grande 15 128 3,1 8 066 3,3 7 062 2,9 87,6
Paul 5 770 1,2 3 178 1,3 2 592 1,1 81,6
Porto Novo 16 052 3,3 8 419 3,4 7 633 3,1 90,7
São Vicente 75 845 15,4 38 472 15,6 37 373 15,3 97,1
Ribeira Brava 6 996 1,4 3 652 1,5 3 344 1,4 91,6
Tarrafal de São Nicolau 5 310 1,1 2 725 1,1 2 585 1,1 94,9
Sal 33 615 6,8 17 946 7,3 15 669 6,4 87,3
Boavista 12 798 2,6 6 871 2,8 5 927 2,4 86,3
Maio 6 330 1,3 3 180 1,3 3 150 1,3 99,1
Tarrafal 16 892 3,4 8 043 3,3 8 849 3,6 110,0
Santa Catarina 37 982 7,7 17 943 7,3 20 039 8,2 111,7
Santa Cruz 25 152 5,1 12 450 5,1 12 702 5,2 102,0
Praia 145 378 29,6 71 803 29,1 73 575 30,0 102,5
São Domingos 14 051 2,9 6 915 2,8 7 136 2,9 103,2
São Miguel 12 966 2,6 6 125 2,5 6 841 2,8 111,7
São Salvador do Mundo 7 482 1,5 3 673 1,5 3 809 1,6 103,7
São Lourenço dos Órgãos 6 328 1,3 3 137 1,3 3 191 1,3 101,7
Ribeira Grande Santiago 7 757 1,6 3 829 1,6 3 928 1,6 102,6
Mosteiros 8 084 1,6 4 073 1,7 4 011 1,6 98,5
São Filipe 20 927 4,3 10 506 4,3 10 421 4,3 99,2
Santa Catarina do Fogo 4 743 1,0 2 423 1,0 2 320 0,9 95,7
Brava 5 647 1,1 2 934 1,2 2 713 1,1 92,5""".splitlines()


class CaboVerde2021Test(unittest.TestCase):
    def test_a_row_is_three_counts_each_before_its_share_and_the_ratio(self):
        self.assertEqual(cv.row_2021("Ribeira Grande 15 128 3,1 8 066 3,3 7 062 2,9 87,6"),
                         ("Ribeira Grande", 15128, 8066, 7062, 87.6))
        self.assertEqual(cv.row_2021("Cabo Verde 491 233 100,0 246 363 100,0 244 870 100,0 99,4"),
                         ("Cabo Verde", 491233, 246363, 244870, 99.4))
        for line in ("Efetivos % Efetivos % Efetivos %", "Concelho Ambos os sexos Masculino",
                     "99 99 98 97 Cabo Verde 99,4",              # the chart's labels
                     "Paul 5 770 1,2 3 178 1,3 2 592 1,1",        # no ratio
                     "Paul 5 7700 1,2 3 178 1,3 2 592 1,1 81,6"):  # not a thousands group
            self.assertIsNone(cv.row_2021(line), line)

    def test_the_table_gives_every_municipality_and_makes_the_country(self):
        got = cv.read_2021(TABLE_7)
        self.assertEqual(sorted(got), sorted(cv.NAMES_2021))
        self.assertEqual(got[74]["total"], 145378)
        self.assertEqual((got[41]["men"], got[41]["women"]), (17946, 15669))
        self.assertEqual(sum(r["total"] for r in got.values()), 491233)
        self.assertEqual(set(cv.NAMES_2021), set(cv.MUNICIPALITIES))

    def test_a_table_that_does_not_close_stops_the_run(self):
        for broken in (
                [line for line in TABLE_7 if not line.startswith("Brava")],   # a row missing
                TABLE_7 + ["Brava 5 647 1,1 2 934 1,2 2 713 1,1 92,5"],       # a row twice
                [line.replace("2 713 1,1 92,5", "2 714 1,1 92,5") for line in TABLE_7],
                [line.replace("1,1 81,6", "1,1 80,6") for line in TABLE_7],   # ratio not printed
                TABLE_7 + ["Santa Luzia 1 0,0 1 0,0 0 0,0 0,0"]):              # an unknown row
            with self.assertRaises(SystemExit):
                cv.read_2021(broken)

    def test_municipalities_and_their_only_parishes_take_the_2021_count(self):
        counts = cv.read_2021(TABLE_7)
        parishes = {41: [{"code": 411, "name": "N.S. das Dores", "total": 25481.0,
                          "zones": 9.0, "men": 13600.0, "women": 11881.0, "island": "Sal.xls",
                          "island_name": "Sal", "url": "u"}],
                    82: [{"code": 821, "name": "São Lourenço", "total": 8899.0, "zones": 18.0,
                          "men": 4306.0, "women": 4593.0, "island": "Fogo.xls",
                          "island_name": "Fogo", "url": "u"},
                         {"code": 822, "name": "N.S. Conceição", "total": 13328.0, "zones": 17.0,
                          "men": 6667.0, "women": 6661.0, "island": "Fogo.xls",
                          "island_name": "Fogo", "url": "u"}]}
        table = {"sal": {"total": 25765.0, "households": 25481.0},
                 "s. filipe": {"total": 22228.0, "households": 22227.0}}
        admin1 = [{"id": "S", "name": "Sal"}, {"id": "F", "name": "São Filipe"}]
        admin2 = [{"id": "d", "name": "Nossa Senhora Das Dores", "parent": "S"},
                  {"id": "l", "name": "Sao Lourenco", "parent": "F"},
                  {"id": "c", "name": "Nossa Senhora Da Conceicao", "parent": "F"}]
        saved = cv.MUNICIPALITIES
        cv.MUNICIPALITIES = {41: ("Sal", "Sal"), 82: ("São Filipe", "S. Filipe")}
        try:
            records = cv.records_of(parishes, table, admin1, admin2, counts)
        finally:
            cv.MUNICIPALITIES = saved
        got = {(r["level"], r["shape_id"]): r for r in records}
        self.assertEqual(len({r["id"] for r in records}), len(records))
        # The municipalities: the 2021 count and sex ratio.
        sal = got[("admin1", "S")]
        self.assertEqual((sal["population"]["value"], sal["population"]["year"]), (33615, 2021))
        self.assertEqual(sal["sex_ratio"]["value"], round(100 * 17946 / 15669, 1))
        self.assertEqual(got[("admin1", "F")]["population"]["value"], 20927)
        # Sal's only parish is Sal: the same 2021 count, not the 2010 one.
        dores = got[("admin2", "d")]
        self.assertEqual((dores["population"]["value"], dores["population"]["year"]),
                         (33615, 2021))
        self.assertEqual(dores["sex_ratio"]["value"], sal["sex_ratio"]["value"])
        self.assertEqual(dores["population_note"], "The 2021 census's count for the "
                         "municipality of Sal, of which this is the only parish.")
        self.assertIn("Censo 2021", dores["sources"][0]["name"])
        # São Filipe's two parishes keep their 2010 counts of private households.
        conceicao = got[("admin2", "c")]
        self.assertEqual((conceicao["population"]["value"], conceicao["population"]["year"]),
                         (13328, 2010))
        self.assertIn("private households", conceicao["population_note"])
        self.assertEqual(got[("admin2", "l")]["population"]["year"], 2010)

    def test_every_figure_says_where_it_was_read(self):
        counts = cv.read_2021(TABLE_7)
        row = cv.figures_2021(counts[74], "n")
        self.assertEqual(row["sources"][0]["url"],
                         "https://web.archive.org/web/20240611091530id_/" + cv.REPORT_ORIGINAL)
        self.assertEqual(row["sources"][0]["field"], "population/sex_ratio")


class TarfayaAcrossTheLineTest(unittest.TestCase):
    """Tarfaya Province is drawn north of the Western Sahara line only, and
    HCP counts it with Daoura, a commune south of the line."""

    def setUp(self):
        from scripts.fetch_census import morocco_rgph2024 as mr
        self.mr = mr
        self.national = mr.NATIONAL
        mr.NATIONAL = 640

    def tearDown(self):
        self.mr.NATIONAL = self.national

    def workbook(self, rows):
        import openpyxl
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(["Population légale du Royaume du Maroc"])
        sheet.append(["Collectivités territoriales", "", "", "", "", "", ""])
        sheet.append(["", "Marocains", "Étrangers", "Population", "Ménages", "", "Code"])
        for name, moroccans, foreigners, code in rows:
            sheet.append([name, moroccans, foreigners, moroccans + foreigners, 1, "", code])
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()

    ROWS = [("Ensemble du territoire national", 620, 20, None),
            ("Région de Laâyoune-Sakia El Hamra", 620, 20, 11),
            ("Préfecture de Laâyoune", 500, 18, 11321),
            ("Province d'Es-Semara", 50, 2, 11221),
            ("Province de Tarfaya", 70, 0, 11537),
            ("Commune de Tarfaya", 40, 0, 115370105),
            ("Cercle de Tarfaya", 30, 0, 1153705),
            ("Commune de Daoura", 20, 0, 115370501),
            ("Commune d'Akhfennir", 10, 0, 115370503),
            ("Commune d'Oujda", 300, 15, 24110123)]          # another region's: not kept

    def test_the_communes_of_the_regions_the_line_cuts_are_read(self):
        table = self.mr.read(self.workbook(self.ROWS))
        self.assertEqual(sorted(table["communes"]), [115370105, 115370501, 115370503])
        self.assertEqual(table["provinces"][11537]["total"], 70)

    def test_tarfaya_says_why_instead_of_the_whole_provinces_count(self):
        table = self.mr.read(self.workbook(self.ROWS))
        admin1 = [{"id": "R11", "name": "Laâyoune-Sakia El Hamra"}]
        admin2 = [{"id": "t", "name": "Tarfaya Province", "parent": "R11"}]
        records, report = self.mr.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        for field in self.mr.FIELDS:
            cell = by["t"][field]
            self.assertNotIn("value", cell)
            self.assertEqual(cell["displaces_before"], 2025)
        note = by["t"]["population"]["note"]
        self.assertEqual(note, "This polygon is the part of Tarfaya province north of the Western "
                               "Sahara line. The 2024 census counts Tarfaya province whole (70 "
                               "people), the commune of Daoura (20 people) south of that line "
                               "among them, and no figure for the part north of it alone has been "
                               "read, so none is shown here.")
        self.assertTrue(by["t"]["id"].startswith("MAR-RGPH2024-part-"))

    def test_communes_that_do_not_make_the_province_or_lack_daoura_stop_the_run(self):
        admin1 = [{"id": "R11", "name": "Laâyoune-Sakia El Hamra"}]
        admin2 = [{"id": "t", "name": "Tarfaya Province", "parent": "R11"}]
        short = [r for r in self.ROWS if r[0] != "Commune d'Akhfennir"]
        with self.assertRaises(SystemExit):
            self.mr.build(self.mr.read(self.workbook(short)), admin1, admin2)
        renamed = [("Commune de Hagounia", *r[1:]) if r[0] == "Commune de Daoura" else r
                   for r in self.ROWS]
        with self.assertRaises(SystemExit):
            self.mr.build(self.mr.read(self.workbook(renamed)), admin1, admin2)

    def test_display_names_drop_the_kind(self):
        self.assertEqual(self.mr.display_commune("Commune de Daoura"), "Daoura")
        self.assertEqual(self.mr.display_commune("Commune d'El Hagounia"), "El Hagounia")


class CaioCitesItsTableTest(unittest.TestCase):
    def test_both_caio_polygons_and_every_sector_cite_their_regions_pdf(self):
        from scripts.fetch_census import guinea_bissau_census as gb
        tables = {"Cacheu": gb.parse([
            "REGIÃO DE CACHEU 60 30 30 50,0", "Bigene - Rural 10 5 5 50,0",
            "Bula - Rural 10 5 5 50,0", "Cacheu - Rural 10 5 5 50,0",
            "Caió - Rural 10 5 5 50,0", "Canchungo - Rural 10 5 5 50,0",
            "SDomingos - Urbano 4 2 2 50,0", "São Domingos - Rural 6 3 3 50,0"], "Cacheu")}
        spec = gb.REGIONS["Cacheu"]
        admin1 = [{"id": spec["polygon"], "name": "Cacheu"}]
        admin2 = [{"id": sid, "name": sid, "parent": spec["polygon"]}
                  for sid in list(set(spec["sectors"].values()) - {None}) + list(gb.CAIO)]
        records, _ = gb.build(tables, admin1, admin2)
        pdf = gb.BASE + spec["file"]
        for r in records:
            self.assertEqual([s["url"] for s in r["sources"]], [pdf], r["name"])
            self.assertEqual(r["sources"][0]["name"], gb.SOURCE)
        caio = [r for r in records if r["shape_id"] in gb.CAIO]
        self.assertEqual(len(caio), 2)


class IdsNameTheirLevelTest(unittest.TestCase):
    def test_senegal_regions_and_departments_of_one_name_have_two_ids(self):
        from scripts.fetch_census import senegal_rgph5 as sn
        rows = [
            ["PROJECTION DE LA POPULATION - 2023-2050", "RGPH-5 2023", None, None, "2024"],
            [None, "HOMME", "FEMME", "ENSEMBLE", "HOMME"],
            ["REGION KOLDA", 40, 60, 100, 41],
            ["DEPARTEMENT  KOLDA", 20, 30, 50, 21],
            ["DEPARTEMENT MEDINA YORO FOULAH", 20, 30, 50, 20]]
        saved, sn.NATIONAL = sn.NATIONAL, 100
        try:
            records, _ = sn.build(sn.parse(rows), [{"id": "K", "name": "Kolda"}],
                                  [{"id": "k", "name": "Kolda", "parent": "K"},
                                   {"id": "m", "name": "Medina Yoroufoula", "parent": "K"}])
        finally:
            sn.NATIONAL = saved
        ids = {r["shape_id"]: r["id"] for r in records}
        self.assertEqual(ids["K"], "SEN-RGPH5-region-kolda")
        self.assertEqual(ids["k"], "SEN-RGPH5-kolda")
        self.assertEqual(len(set(ids.values())), 3)

    def test_zambia_lusaka_province_and_district_have_two_ids(self):
        from scripts.fetch_census import zambia_census as zc
        lines = ["TABLE 5.2:", "Province/District/",
                 "ZAMBIA TOTAL 100 45 55 100 45 55 - - -",
                 "LUSAKA PROVINCE 100 45 55 100 45 55 - - -",
                 "LUSAKA DISTRICT 100 45 55 100 45 55 - - -"]
        saved, zc.NATIONAL = zc.NATIONAL, 100
        try:
            records, _ = zc.build(zc.parse(lines), [{"id": "L", "name": "Lusaka"}],
                                  [{"id": "l", "name": "Lusaka", "parent": "L"}])
        finally:
            zc.NATIONAL = saved
        ids = {r["shape_id"]: r["id"] for r in records}
        self.assertEqual(ids, {"L": "ZMB-2022-province-lusaka", "l": "ZMB-2022-lusaka"})


if __name__ == "__main__":
    unittest.main()
