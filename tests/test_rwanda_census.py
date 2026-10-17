"""Tests for the Rwanda 2022 census adapter, no network."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import rwanda_census as rc  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"

# Table 1 of the Main Indicators workbook, as published.
TABLE1 = [
    ("Rwanda", 13246394, 6429326, 6817068),
    ("City of Kigali", 1745555, 888882, 856673), ("Nyarugenge", 374319, 195780, 178539),
    ("Gasabo", 879505, 443987, 435518), ("Kicukiro", 491731, 249115, 242616),
    ("Southern Province", 3002699, 1448455, 1554244), ("Nyanza", 365718, 178645, 187073),
    ("Gisagara", 397051, 188965, 208086), ("Nyaruguru", 318126, 151980, 166146),
    ("Huye", 381900, 188859, 193041), ("Nyamagabe", 371501, 176725, 194776),
    ("Ruhango", 359121, 172096, 187025), ("Muhanga", 358433, 173615, 184818),
    ("Kamonyi", 450849, 217570, 233279),
    ("Western Province", 2896484, 1384635, 1511849), ("Karongi", 373869, 178417, 195452),
    ("Rutsiro", 369180, 176498, 192682), ("Rubavu", 546683, 267299, 279384),
    ("Nyabihu", 319047, 150072, 168975), ("Ngororero", 367955, 171065, 196890),
    ("Rusizi", 485529, 236426, 249103), ("Nyamasheke", 434221, 204858, 229363),
    ("Northern Province", 2038511, 972960, 1065551), ("Rulindo", 360144, 171849, 188295),
    ("Gakenke", 365292, 172600, 192692), ("Musanze", 476522, 227340, 249182),
    ("Burera", 387729, 184782, 202947), ("Gicumbi", 448824, 216389, 232435),
    ("Eastern Province", 3563145, 1734394, 1828751), ("Rwamagana", 484953, 243794, 241159),
    ("Nyagatare", 653861, 318740, 335121), ("Gatsibo", 551164, 264461, 286703),
    ("Kayonza", 457156, 221448, 235708), ("Kirehe", 460860, 221763, 239097),
    ("Ngoma", 404048, 192720, 211328), ("Bugesera", 551103, 271468, 279635),
]
TABLE6 = [
    ["Table 6: Population by nationality and Province", None, None, None, None, None, None],
    [None, "Nationality", "Province", None, None, None, None],
    [None, None, "Rwanda", "City of Kigali", "Southern", "Western", "Northern", "Eastern"],
    [None, "Total", 13246394, 1745555, 3002699, 2896484, 2038511, 3563145],
    [None, "Rwandan", 13129019, 1725001, 2984491, 2880813, 2036204, 3502510],
    [None, "Foreigners", 117375, 20554, 18208, 15671, 2307, 60635],
]
KICUKIRO = """Nyarugunga 49,247 48,389 858 100 98.26 1.74
Source: Fifth Rwanda Population and Housing Census, 2022 (NISR)
2.1.2 Religious affiliation of the resident population of Kicukiro district
Kicukiro district 491,731 249,115 242,616
Rwanda 13,246,394 3,701,245 9,545,149
City of Kigali 1,745,555 1,517,168 228,387
Kicukiro district 491,731 487,200 4,531 100 100 100
Catholic 176,152 173,667 2,485 35.82 35.65 54.84
ADEPR 112,670 111,494 1,176 22.91 22.88 25.95
Protestant 50,883 50,579 304 10.35 10.38 6.71
Adventist 49,036 48,680 356 9.97 9.99 7.86
Other Christians 49,090 49,028 62 9.98 10.06 1.37
Muslim 19,479 19,438 41 3.96 3.99 0.90
Jehovah witness 5,272 5,261 11 1.07 1.08 0.24
Traditional/Animist 161 161   0.03 0.03
Other religion 14,527 14,511 16 2.95 2.98 0.35
No Religion 13,280 13,200 80 2.70 2.71 1.77
Not stated 1,181 1,181   0.24 0.24
Source: Fifth Rwanda Population and Housing Census, 2022 (NISR)
"""


# The profile's list of tables names Table 2.1 too, with no rows after it; the
# table itself follows in the body, its district row before its sectors'.
PROFILE = """Table 2.  1 Distribution (count and %) of the resident population of Kicukiro district by
Nationality and sector ................................................................................................. 10
Table 2.  2 Distribution (count and %) of the resident population of Kicukiro district by
Religious Affiliation and residence areas .................................................................. 11
Table 2.  1 Distribution (count and %) of the resident population of Kicukiro district
by Nationality and sector
 Sectors
Counts Percentage%
Total Rwandan Foreigners Total Rwandan Foreigners
Rwanda 13,246,394 13,129,019 117,375 100 99.11 0.89
City of Kigali 1,745,555 1,725,001 20,554 100 98.82 1.18
Kicukiro district 491,731 484,982 6,749 100 98.63 1.37
Gahanga 75,000 74,000 1,000 100 98.67 1.33
""" + KICUKIRO
# Nyarugenge's and Gasabo's rows, made up so that Kigali's three districts make
# Table 6's Rwandans and foreigners.
KIGALI = {"Kicukiro": {"Rwandan": 484982, "Foreign nationals": 6749},
          "Nyarugenge": {"Rwandan": 368319, "Foreign nationals": 6000},
          "Gasabo": {"Rwandan": 871700, "Foreign nationals": 7805}}


def table1_rows(rows=TABLE1):
    return [[None, n, t, m, f, 1.0, 100] for n, t, m, f in rows]


def median_rows():
    rows43 = []
    for province in rc.PROVINCES:
        rows43 += [[None, province], [None, "Urban", 24.0, 24.0, 24.0, 22, 21, 22],
                   [None, "Total", 23.0, 25.0, 24.0, 19, 21, 20]]
    rows44 = [[None, d, 23.0, 25.0, 24.0, 18, 20, 19]
              for ds in rc.PROVINCES.values() for d in ds]
    return rows43, rows44


class TablesTest(unittest.TestCase):
    def test_table1_reads_and_adds_up(self):
        t = rc.read_table1(table1_rows())
        self.assertEqual(t["Kicukiro"], {"total": 491731, "male": 249115, "female": 242616})

    def test_a_district_that_does_not_add_up_stops_the_run(self):
        rows = [r if r[0] != "Huye" else ("Huye", 381901, 188860, 193041) for r in TABLE1]
        with self.assertRaises(SystemExit):
            rc.read_table1(table1_rows(rows))

    def test_nationality_by_province(self):
        t6 = rc.read_table6(TABLE6, rc.read_table1(table1_rows()))
        self.assertEqual(t6["Eastern Province"], {"Rwandan": 3502510,
                                                  "Foreign nationals": 60635})

    def test_medians_for_every_province_and_district(self):
        medians = rc.read_medians(*median_rows())
        self.assertEqual(medians["Southern Province"], 20)
        self.assertEqual(medians["Bugesera"], 19)
        self.assertEqual(len(medians), 35)

    def test_the_religion_table_not_the_sex_table(self):
        counts = rc.read_religion(KICUKIRO, "Kicukiro")
        self.assertEqual(counts.pop("_total"), 491731)
        self.assertEqual(counts["Pentecostal"], 112670)
        self.assertEqual(counts["Traditional"], 161)
        self.assertEqual(sum(counts.values()), 491731)

    def test_no_table_reads_as_none(self):
        self.assertIsNone(rc.read_religion("Kicukiro district 491,731 249,115", "Kicukiro"))

    def test_nationality_is_the_district_row_of_table_2_1(self):
        self.assertEqual(rc.read_nationality(PROFILE, "Kicukiro"),
                         {"Rwandan": 484982, "Foreign nationals": 6749, "_total": 491731})
        # The religion table's own row (everyone, urban, rural, 100 three times)
        # is not taken for it, and neither is a profile without the table.
        self.assertIsNone(rc.read_nationality(KICUKIRO, "Kicukiro"))

    def test_a_row_whose_shares_disagree_reads_as_none(self):
        bad = PROFILE.replace("100 98.63 1.37", "100 97.63 2.37")
        self.assertIsNone(rc.read_nationality(bad, "Kicukiro"))

    def test_shares_to_one_decimal_and_a_title_broken_after_nationality(self):
        # Nyarugenge's profile prints the shares to one decimal; Huye's breaks
        # the title after "Nationality".
        text = ("Table 2.  1Distribution (count and %) of the resident population of Nyarugenge "
                "District by Nationality\nand sector\n"
                "Sectors Count Percentage Total Rwandan Foreigner Total Rwandan Foreigner\n"
                "Rwanda 13,246,394 13,129,019 117,375 100 99.1 0.9\n"
                "Nyarugenge district 374,319 371,043 3,276 100 99.1 0.9\n"
                "Nyarugenge 16,665 15,945 720 100 95.7 4.3\n")
        self.assertEqual(rc.read_nationality(text, "Nyarugenge", 374319),
                         {"Rwandan": 371043, "Foreign nationals": 3276, "_total": 374319})
        # Without the word "district", the sector of the same name is not taken
        # for it, its count not being the district's.
        bare = text.replace("Nyarugenge district 374,319", "Nyarugenge 374,319")
        self.assertEqual(rc.read_nationality(bare, "Nyarugenge", 374319)["_total"], 374319)
        sector_only = "\n".join(line for line in bare.splitlines() if "374,319" not in line)
        self.assertIsNone(rc.read_nationality(sector_only, "Nyarugenge", 374319))

    def test_a_rwandan_share_that_rounds_to_100(self):
        # Gakenke's and Ngororero's profiles, where foreigners are a few dozen
        # and the Rwandans' share prints as 100 (to one decimal, or none).
        gakenke = ("Table 2. 1 Distribution (Count and %) of the resident population of Gakenke "
                   "district by\nNationality and Sector.\n"
                   " Sectors Count Percentage (%)\n"
                   "Total Rwandan Foreigners Total Rwandan Foreigners\n"
                   "Rwanda 13,246,394 13,129,019 117,375 100.0 99.1 0.9\n"
                   "Northern Province 2,038,511 2,036,204 2,307 100.0 99.9 0.1\n"
                   "Gakenke district 365,292 365,194 98 100.0 100.0 0.0\n"
                   "Busengo 21,392 21,386 6 100.0 100.0 0.0\n")
        self.assertEqual(rc.read_nationality(gakenke, "Gakenke", 365292),
                         {"Rwandan": 365194, "Foreign nationals": 98, "_total": 365292})
        ngororero = ("Table 2.  1  Distribution (count and %) of the resident population of "
                     "Ngororero district by\nNationality and sector\n"
                     "Total Rwandan Foreigners Total Rwandan Foreigners\n"
                     "Ngororero district 367,955 367,883 72 100 100 0.0\n")
        self.assertEqual(rc.read_nationality(ngororero, "Ngororero", 367955)["Foreign nationals"],
                         72)
        # A religion row under the same title -- everyone, urban, rural, then
        # 100 three times -- still reads as none: its two "shares" cannot both
        # be 100.
        religion = ngororero.replace("367,883 72 100 100 0.0", "16,412 351,543 100 100 100")
        self.assertIsNone(rc.read_nationality(religion, "Ngororero", 367955))


class BuildTest(unittest.TestCase):
    def test_records_for_every_polygon(self):
        table1 = rc.read_table1(table1_rows())
        counts = rc.read_religion(KICUKIRO, "Kicukiro")
        counts.pop("_total")
        admin1 = json.loads((SITE / "admin1" / "RWA.units.json").read_text())
        admin2 = json.loads((SITE / "admin2" / "RWA.units.json").read_text())
        records = rc.build(table1, rc.read_table6(TABLE6, table1), rc.read_medians(*median_rows()),
                           {"Kicukiro": counts}, {"Kicukiro": "https://example/Kicukiro.pdf"},
                           admin1, admin2)
        by = {r["name"]: r for r in records}
        self.assertEqual(len(records), 35)
        self.assertEqual(by["Kicukiro"]["religion"][0]["group"], "Catholic")
        self.assertEqual(by["Kicukiro"]["sex_ratio"]["value"], 1027)
        self.assertNotIn("religion_note", by["Gasabo"])
        kigali = by["City of Kigali"]
        self.assertEqual(kigali["ethnicity_basis"], "nationality")
        self.assertNotIn("religion_note", kigali)      # two of its districts are unread
        self.assertEqual(kigali["median_age"]["value"], 20)
        # No profile's nationality was given: the districts say the census asks
        # no ethnicity, and every unit why it has no language.
        self.assertEqual(by["Kicukiro"]["ethnicity"]["note"],
                         "Rwanda's 2022 census asks no ethnicity.")
        for r in records:
            self.assertEqual(r["language"]["note"], rc.LANGUAGE)

    def build_kigali(self, nations):
        table1 = rc.read_table1(table1_rows())
        admin1 = json.loads((SITE / "admin1" / "RWA.units.json").read_text())
        admin2 = json.loads((SITE / "admin2" / "RWA.units.json").read_text())
        records = rc.build(table1, rc.read_table6(TABLE6, table1),
                           rc.read_medians(*median_rows()), {}, {}, admin1, admin2, nations)
        return {r["name"]: r for r in records}

    def test_districts_take_their_profiles_nationality_where_they_make_table_6(self):
        by = self.build_kigali(KIGALI)
        kicukiro = by["Kicukiro"]
        self.assertEqual(kicukiro["ethnicity_basis"], "nationality")
        self.assertEqual({g["group"]: g["count"] for g in kicukiro["ethnicity"]},
                         KIGALI["Kicukiro"])
        self.assertIn("Table 2.1", [s for s in kicukiro["sources"]
                                    if s["field"] == "ethnicity"][0]["name"])
        self.assertIsInstance(by["Nyarugenge"]["ethnicity"], list)
        # Another province, with no profile read, keeps its gap.
        self.assertEqual(by["Huye"]["ethnicity"]["status"], "not_available")

    def test_districts_that_do_not_make_table_6_write_none(self):
        nations = {d: dict(v) for d, v in KIGALI.items()}
        nations["Gasabo"]["Foreign nationals"] += 1
        nations["Gasabo"]["Rwandan"] -= 1
        by = self.build_kigali(nations)
        for d in KIGALI:
            self.assertEqual(by[d]["ethnicity"]["status"], "not_available")


if __name__ == "__main__":
    unittest.main()
