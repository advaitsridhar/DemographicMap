"""Tests for the Burundi 2008 census adapter (sex ratios by province and commune), no network."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import burundi_census as bc  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"

# Tableau 1.6 as the institute's workbook gives it (sheet ETA6): the national
# row, then each province's row followed by its communes'. Makamba's first
# "MAKAMBA" is the annex's Mabanda.
ROWS = [
    ("BURUNDI", 3964906, 4088668, 8053574), ("BUBANZA", 174468, 163555, 338023),
    ("BUBANZA", 42062, 41616, 83678), ("GIHANGA", 30339, 25005, 55344),
    ("MPANDA", 29313, 29600, 58913), ("MUSIGATI", 41035, 41172, 82207),
    ("RUGAZI", 31719, 26162, 57881), ("BUJUMBURA RURAL", 275215, 280718, 555933),
    ("BUGARAMA", 14898, 15584, 30482), ("ISALE", 38708, 40032, 78740),
    ("KABEZI", 23180, 25899, 49079), ("KANYOSHA", 38203, 40620, 78823),
    ("MUBIMBI", 20515, 21174, 41689), ("MUGONGOMANGA", 13862, 14123, 27985),
    ("MUHUTA", 31119, 29514, 60633), ("MUKIKE", 11901, 12759, 24660),
    ("MUTAMBU", 20885, 22878, 43763), ("MUTIMBUZI", 35809, 33716, 69525),
    ("NYABIRABA", 26135, 24419, 50554), ("BURURI", 282363, 291650, 574013),
    ("BURAMBI", 28068, 29099, 57167), ("BURURI", 40889, 42725, 83614),
    ("BUYENGERO", 29110, 29560, 58670), ("MATANA", 20763, 22014, 42777),
    ("MUGAMBA", 28383, 30701, 59084), ("RUMONGE", 73196, 71878, 145074),
    ("RUTOVU", 22127, 23984, 46111), ("SONGA", 25351, 26480, 51831),
    ("VYANDA", 14476, 15209, 29685), ("CANKUZO", 112342, 116531, 228873),
    ("CANKUZO", 23543, 24429, 47972), ("CENDAJURU", 15887, 16571, 32458),
    ("GISAGARA", 27777, 29545, 57322), ("KIGAMBA", 20156, 20617, 40773),
    ("MISHIHA", 24979, 25369, 50348), ("CIBITOKE", 228858, 231577, 460435),
    ("BUGANDA", 34069, 34976, 69045), ("BUKINANYANA", 37362, 38388, 75750),
    ("MABAYI", 33177, 33190, 66367), ("MUGINA", 43531, 44920, 88451),
    ("MURWI", 41545, 40690, 82235), ("RUGOMBO", 39174, 39413, 78587),
    ("GITEGA", 346480, 378743, 725223), ("BUGENDANA", 51830, 56557, 108387),
    ("BUKIRASAZI", 15641, 17073, 32714), ("BURAZA", 22634, 24851, 47485),
    ("GIHETA", 34213, 38804, 73017), ("GISHUBI", 26199, 29728, 55927),
    ("GITEGA", 77217, 77788, 155005), ("ITABA", 24204, 26935, 51139),
    ("MAKEBUKO", 27462, 31994, 59456), ("MUTAHO", 30894, 34460, 65354),
    ("NYARUSANGE", 19532, 21372, 40904), ("RYANSORO", 16654, 19181, 35835),
    ("KARUSI", 210225, 226218, 436443), ("BUGENYUZI", 39443, 42495, 81938),
    ("BUHUGA", 34967, 36507, 71474), ("GIHOGAZI", 32315, 35312, 67627),
    ("GITARAMUKA", 37616, 40504, 78120), ("MUTUMBA", 20141, 21335, 41476),
    ("NYABIKERE", 23645, 25348, 48993), ("SHOMBO", 22098, 24717, 46815),
    ("KAYANZA", 281957, 303455, 585412), ("BUTAGANZWA", 24066, 27535, 51601),
    ("GAHOMBO", 18868, 20765, 39633), ("GATARA", 31041, 33071, 64112),
    ("KABARORE", 30332, 31971, 62303), ("KAYANZA", 47827, 49425, 97252),
    ("MATONGO", 34193, 36082, 70275), ("MUHANGA", 30629, 33851, 64480),
    ("MURUTA", 27791, 30097, 57888), ("RANGO", 37210, 40658, 77868),
    ("KIRUNDO", 303791, 324465, 628256), ("BUGABIRA", 42756, 46503, 89259),
    ("BUSONI", 70809, 74615, 145424), ("BWAMBARANGWE", 32281, 34535, 66816),
    ("GITOBE", 27406, 29920, 57326), ("KIRUNDO", 45510, 47600, 93110),
    ("NTEGA", 47333, 51332, 98665), ("VUMBI", 37696, 39960, 77656),
    ("MAKAMBA", 214430, 216469, 430899), ("KAYOGORO", 43938, 44614, 88552),
    ("KIBAGO", 22697, 22281, 44978), ("MAKAMBA", 22910, 22926, 45836),
    ("MAKAMBA", 46268, 47290, 93558), ("NYANZA LAC", 56638, 56114, 112752),
    ("VUGIZO", 21979, 23244, 45223), ("MURAMVYA", 139669, 152920, 292589),
    ("BUKEYE", 31265, 34825, 66090), ("KIGANDA", 23060, 25670, 48730),
    ("MBUYE", 25838, 29504, 55342), ("MURAMVYA", 40143, 41114, 81257),
    ("RUTEGAMA", 19363, 21807, 41170), ("MUYINGA", 308016, 324393, 632409),
    ("BUHINYUZA", 26231, 28251, 54482), ("BUTIHINDA", 46968, 49922, 96890),
    ("GASHOHO", 31912, 34195, 66107), ("GASORWE", 39377, 42621, 81998),
    ("GITERANYI", 74158, 77072, 151230), ("MUYINGA", 68305, 69922, 138227),
    ("MWAKIRO", 21065, 22410, 43475), ("MWARO", 128913, 144230, 273143),
    ("BISORO", 16440, 17735, 34175), ("GISOZI", 13484, 14470, 27954),
    ("KAYOKWE", 23380, 25747, 49127), ("NDAVA", 26873, 30411, 57284),
    ("NYABIHANGA", 27972, 32339, 60311), ("RUSAKA", 20764, 23528, 44292),
    ("NGOZI", 323037, 337680, 660717), ("BUSIGA", 31629, 33514, 65143),
    ("GASHIKANWA", 27268, 29818, 57086), ("KIREMBA", 45527, 47809, 93336),
    ("MARANGARA", 33765, 34067, 67832), ("MWUMBA", 30144, 31440, 61584),
    ("NGOZI", 61438, 59119, 120557), ("NYAMURENZA", 27879, 29323, 57202),
    ("Ruhororo", 29318, 33019, 62337), ("TANGARA", 36069, 39571, 75640),
    ("RUTANA", 162809, 170701, 333510), ("BUKEMBA", 18115, 17356, 35471),
    ("GIHARO", 45098, 48267, 93365), ("GITANGA", 21435, 22292, 43727),
    ("MPINGA", 25358, 27463, 52821), ("MUSONGATI", 25674, 27275, 52949),
    ("RUTANA", 27129, 28048, 55177), ("RUYIGI", 197357, 203173, 400530),
    ("BUTAGANZWA", 31302, 31884, 63186), ("BUTEZI", 19139, 20039, 39178),
    ("BWERU", 18272, 19230, 37502), ("GISURU", 49440, 50021, 99461),
    ("KINYINYA", 25815, 27223, 53038), ("NYABITSINDA", 25261, 26273, 51534),
    ("RUYIGI", 28128, 28503, 56631), ("BUJUMBURA MAIRIE", 274976, 222190, 497166),
    ("BUTERERE", 14540, 13831, 28371), ("BUYENZI", 27460, 19903, 47363),
    ("BWIZA", 21464, 16224, 37688), ("CIBITOKE", 26658, 24241, 50899),
    ("GIHOSHA", 21953, 17550, 39503), ("KAMENGE", 27031, 23039, 50070),
    ("KANYOSHA", 30589, 28592, 59181), ("KINAMA", 25880, 23896, 49776),
    ("KININDO", 12302, 9618, 21920), ("MUSAGA", 25837, 17898, 43735),
    ("NGAGARA", 18272, 12024, 30296), ("NYAKABIGA", 11732, 9151, 20883),
    ("ROHERO", 11258, 6223, 17481),
]


def sheet(rows=ROWS):
    return ([["Tableau 1.6. Répartition de la population résidante"], [None],
             ["Provinces/Communes", "Masculin", "Féminin", "Total"]]
            + [[n, m, f, t] for n, m, f, t in rows])


class TableTest(unittest.TestCase):
    def test_seventeen_provinces_and_their_communes_make_the_country(self):
        table = bc.provinces(bc.read_rows(sheet()))
        self.assertEqual(len(table), 17)
        self.assertEqual(sum(len(p["communes"]) for p in table.values()), 129)
        self.assertIn("MABANDA", table["MAKAMBA"]["communes"])
        self.assertEqual(table["MAKAMBA"]["communes"]["MAKAMBA"]["total"], 93_558)

    def test_a_row_whose_sexes_do_not_make_it_stops_the_run(self):
        rows = [r if r[0] != "CENDAJURU" else ("CENDAJURU", 15887, 16570, 32458) for r in ROWS]
        with self.assertRaises(SystemExit):
            bc.read_rows(sheet(rows))

    def test_a_province_its_communes_do_not_make_stops_the_run(self):
        rows = [r if r[0] != "MISHIHA" else ("MISHIHA", 24979, 25368, 50347) for r in ROWS]
        with self.assertRaises(SystemExit):
            bc.provinces(bc.read_rows(sheet(rows)))


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.admin1 = json.loads((SITE / "admin1" / "BDI.units.json").read_text())
        self.admin2 = json.loads((SITE / "admin2" / "BDI.units.json").read_text())
        table = bc.provinces(bc.read_rows(sheet()))
        self.records, self.report = bc.build(table, self.admin1, self.admin2)
        self.by = {(r["level"], r["name"]): r for r in self.records}

    def test_every_province_and_commune_drawn_is_written(self):
        self.assertEqual(sum(1 for r in self.records if r["level"] == "admin1"), 18)
        self.assertEqual(sum(1 for r in self.records if r["level"] == "admin2"), 119)
        self.assertFalse([line for line in self.report if "not written" in line
                          or "on no polygon" in line], self.report)

    def test_a_commune_takes_its_own_men_and_women(self):
        cendajuru = self.by[("admin2", "Cendajuru")]
        self.assertEqual(cendajuru["sex_ratio"], {"value": 959, "unit": "males_per_1000_females",
                                                  "year": 2008, "source": bc.SOURCE})
        self.assertIn("2008 census", cendajuru["sex_ratio_note"])
        self.assertIn("(15,887 men and 16,571 women)", cendajuru["sex_ratio_note"])
        self.assertEqual(self.by[("admin2", "Mabanda")]["sex_ratio"]["value"], 999)
        self.assertEqual(self.by[("admin2", "Mpinga-Kayove")]["sex_ratio"]["value"], 923)
        self.assertEqual([s["field"] for s in cendajuru["sources"]], ["sex_ratio"])

    def test_bujumbura_communes_are_their_zones_of_2008_added_up(self):
        muha = self.by[("admin2", "Muha")]
        self.assertEqual(muha["sex_ratio"]["value"], round(1000 * 68_728 / 56_108))
        self.assertIn("Kanyosha, Kinindo and Musaga", muha["sex_ratio_note"])
        rural = self.by[("admin2", "Kanyosha")]
        self.assertEqual(rural["sex_ratio"]["value"], round(1000 * 38_203 / 40_620))

    def test_provinces_are_the_communes_that_make_them_as_drawn(self):
        rumonge = self.by[("admin1", "Rumonge")]
        men = 14898 + 31119 + 28068 + 29110 + 73196
        women = 15584 + 29514 + 29099 + 29560 + 71878
        self.assertEqual(rumonge["sex_ratio"]["value"], round(1000 * men / women))
        bururi = self.by[("admin1", "Bururi")]
        self.assertIn("without Burambi and Buyengero and Rumonge", bururi["sex_ratio_note"]
                      .replace(", ", " and "))
        self.assertEqual(self.by[("admin1", "Karuzi")]["sex_ratio"]["value"],
                         round(1000 * 210_225 / 226_218))
        mairie = self.by[("admin1", "Bujumbura Mairie")]
        self.assertEqual(mairie["sex_ratio"]["value"], round(1000 * 274_976 / 222_190))


if __name__ == "__main__":
    unittest.main()
