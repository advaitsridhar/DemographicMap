"""Afghanistan: median age by district from the Socio-Demographic and Economic Survey.

Synthetic report pages in the layout of the survey's Table 3, and synthetic
drawn units bound through the office's district codes. No network.
"""

import unittest
from unittest import mock

from scripts.fetch_census import afghanistan_estimates as ae
from scripts.fetch_census import afghanistan_sdes as sd

BALKH = sd.Report("21", "Balkh", "https://example.org/balkh.pdf", "December 2015", 2015,
                  {"Mazar-E-Sharif": "2101", "Balkh": "2106", "Char Bolak": "2111"},
                  whole=True)

PAGE = """Balkh Province Socio-Demographic and Economic Survey
The median age of the population in Balkh is 17.1 years, which is the same as
Balkh (2015) 17.1
Kapisa (2014)* 17.1
Table 3. Median Age in Years of Population by District: Balkh, December
2015
Province/District Both Sexes Male Female
Balkh 17.1 17.0 17.1
Mazar-E-Sharif 17.8 17.7 17.9
Balkh 16.1 16.0 16.3
Char Bolak 15.7 15.6 15.7
The proportion of the population under age 15 also provides an indication as to
whether a population is young or old; those with 35.0 percent or more below age 15
"""

CONTENTS = """LIST OF TABLES
Table 3 Median Age in Years of the Population by District: Balkh, December 2015 23
Table 4 Percent Distribution of Population by Age Group, Aged-Child Ratio, and District: Balkh,
Table 7 Median Age at First Marriage by Sex and District: Balkh, December 2015
"""


class TableThree(unittest.TestCase):
    def test_the_province_comes_first_and_a_district_may_share_its_name(self):
        found = sd.table_rows([CONTENTS, PAGE], BALKH)
        self.assertEqual(found, {"21": (17.1, 17.0, 17.1), "2101": (17.8, 17.7, 17.9),
                                 "2106": (16.1, 16.0, 16.3), "2111": (15.7, 15.6, 15.7)})
        sd.check(BALKH, found)

    def test_a_text_box_above_the_title_is_not_the_table(self):
        # Without its title the page has only the text box's "Balkh (2015)
        # 17.1", which is never read as the province's row.
        untitled = PAGE.replace("Median Age in Years of Population by District", "Ages")
        self.assertEqual(sd.table_rows([untitled], BALKH), {})

    def test_the_table_ends_at_the_first_line_that_is_not_a_row(self):
        cut = PAGE.replace("Balkh 16.1 16.0 16.3\n", "Note: see Appendix A1.\n"
                           "Balkh 16.1 16.0 16.3\n")
        found = sd.table_rows([cut], BALKH)
        self.assertEqual(set(found), {"21", "2101"})
        with self.assertRaises(SystemExit):
            sd.check(BALKH, found)

    def test_a_row_read_twice_stops_the_run(self):
        twice = PAGE.replace("Char Bolak 15.7 15.6 15.7\n",
                             "Char Bolak 15.7 15.6 15.7\nChar Bolak 15.9 15.6 16.0\n")
        with self.assertRaises(SystemExit):
            sd.table_rows([twice], BALKH)

    def test_implausible_tables_are_refused(self):
        good = sd.table_rows([PAGE], BALKH)
        for code, figures in (("2101", (47.8, 47.7, 47.9)),     # not a median age
                              ("2101", (19.8, 17.7, 17.9)),     # both sexes off its sexes
                              ("21", (18.9, 18.8, 19.0))):      # province above all districts
            bad = dict(good)
            bad[code] = figures
            with self.assertRaises(SystemExit, msg=(code, figures)):
                sd.check(BALKH, bad)


# Three provinces as the office counts them, drawn with Mahmudi Raqi (Kapisa's)
# in Parwan, and Bamyan's Yakawlang holding the temporary Yakawlang No. 2.
ISO = {"10": "AF-BAM", "02": "AF-KAP", "03": "AF-PAR"}
NAMES = {"10": "Bamyan", "02": "Kapisa", "03": "Parwan"}
CROSSWALK = {
    "Bamyan": {"Bamyan": "1001", "Yakawlang": "1005"},
    "Kapisa": {"Koh Band": "0203", "Tagab": "0206"},
    "Parwan": {"Mahmudi Raqi": "0201", "Chaharikar": "0301", "Bagram": "0302"},
}
REPORTS = [
    sd.Report("10", "Bamiyan", "https://example.org/bamyan.pdf", "September 2011", 2011,
              {"Provincial Center": "1001", "Yakawlang": "1005"}, whole=True),
    sd.Report("02", "Kapisa", "https://example.org/kapisa.pdf", "September 2014", 2014,
              {"Mahmudi Raqi": "0201", "Koh Band": "0203"}, whole=False,
              coverage="Its tables cover two of the province's three districts."),
    sd.Report("03", "Parwan", "https://example.org/parwan.pdf", "September 2014", 2014,
              {"Charikar": "0301", "Bagram": "0302"}, whole=True),
]
FOUND = {
    "10": {"10": (16.6, 16.9, 16.3), "1001": (16.5, 16.8, 16.2), "1005": (16.5, 16.8, 16.3)},
    "02": {"02": (17.1, 17.2, 17.0), "0201": (15.8, 15.9, 15.7), "0203": (15.9, 15.5, 16.3)},
    "03": {"03": (17.1, 17.3, 16.8), "0301": (17.0, 17.2, 16.9), "0302": (16.4, 16.5, 16.3)},
}


def units() -> tuple[list[dict], list[dict]]:
    units1 = [{"id": f"P{code}", "name": NAMES[code], "iso_3166_2": ISO[code]}
              for code in ISO]
    pid = {NAMES[code]: f"P{code}" for code in ISO}
    units2 = [{"id": f"D{key}", "name": label, "parent": pid[province]}
              for province, districts in CROSSWALK.items()
              for label, key in districts.items()]
    return units1, units2


class Build(unittest.TestCase):
    def build(self, reports=None, found=None, temporary=None) -> dict[str, dict]:
        units1, units2 = units()
        with mock.patch.multiple(ae, PROVINCE_ISO=ISO, CROSSWALK=CROSSWALK,
                                 POINT_ELSEWHERE={},
                                 TEMPORARY_PARENT=temporary or {"1008": "1005"}), \
                mock.patch.object(sd, "REPORTS", reports or REPORTS):
            return {r["id"]: r for r in sd.build(found or FOUND, units1, units2)}

    def test_districts_take_their_own_row_wherever_they_are_drawn(self):
        records = self.build()
        mahmudi = records["AFG-SDES-0201"]
        self.assertEqual(mahmudi["shape_id"], "D0201")
        self.assertEqual(mahmudi["parent_name"], "Parwan")
        self.assertEqual(mahmudi["median_age"]["value"], 15.8)
        self.assertEqual(mahmudi["median_age"]["year"], 2014)
        self.assertIn("Kapisa, September 2014", mahmudi["median_age_note"])
        self.assertIn("(males 15.9, females 15.7)", mahmudi["median_age_note"])
        self.assertEqual(mahmudi["sources"][0]["url"], "https://example.org/kapisa.pdf")
        self.assertEqual(records["AFG-SDES-0302"]["median_age"]["value"], 16.4)
        self.assertEqual(records["AFG-SDES-1001"]["median_age"]["value"], 16.5)

    def test_a_district_the_survey_did_not_cover_says_so(self):
        tagab = self.build()["AFG-SDES-0206"]["median_age"]
        self.assertEqual(tagab["status"], "not_available")
        self.assertIn("did not cover this district", tagab["note"])
        self.assertIn("two of the province's three districts", tagab["note"])

    def test_provinces_only_where_covered_whole_and_drawn_as_counted(self):
        records = self.build()
        self.assertEqual(records["AFG-SDES-10"]["median_age"]["value"], 16.6)
        self.assertEqual(records["AFG-SDES-10"]["shape_id"], "P10")
        kapisa = records["AFG-SDES-02"]["median_age"]
        self.assertIn("did not cover the whole province", kapisa["note"])
        self.assertNotIn("value", kapisa)
        parwan = records["AFG-SDES-03"]["median_age"]
        self.assertNotIn("value", parwan)
        self.assertIn("Mahmudi Raqi, drawn here, is counted by the office in Kapisa",
                      parwan["note"])

    def test_a_whole_province_report_holds_the_later_temporary_district(self):
        yakawlang = self.build()["AFG-SDES-1005"]
        self.assertEqual(yakawlang["median_age"]["value"], 16.5)
        self.assertIn("counted within it", yakawlang["median_age_note"])

    def test_a_temporary_district_listed_apart_or_a_partial_report_is_declined(self):
        listed = [REPORTS[0]._replace(rows={"Provincial Center": "1001",
                                            "Yakawlang": "1005", "Yakawlang 2": "1008"}),
                  *REPORTS[1:]]
        found = dict(FOUND, **{"10": dict(FOUND["10"], **{"1008": (15.0, 15.1, 14.9)})})
        yakawlang = self.build(reports=listed, found=found)["AFG-SDES-1005"]
        self.assertNotIn("value", yakawlang["median_age"])
        self.assertIn("temporary district", yakawlang["median_age"]["note"])
        partial = [REPORTS[0]._replace(whole=False, coverage="Not all of it."), *REPORTS[1:]]
        records = self.build(reports=partial)
        self.assertNotIn("value", records["AFG-SDES-1005"]["median_age"])
        self.assertEqual(records["AFG-SDES-1001"]["median_age"]["value"], 16.5)
        self.assertNotIn("value", records["AFG-SDES-10"]["median_age"])

    def test_every_district_counted_in_a_read_province_gets_a_record(self):
        records = self.build()
        districts = {k for k, r in records.items() if r["level"] == "admin2"}
        self.assertEqual(districts, {"AFG-SDES-1001", "AFG-SDES-1005", "AFG-SDES-0201",
                                     "AFG-SDES-0203", "AFG-SDES-0206", "AFG-SDES-0301",
                                     "AFG-SDES-0302"})


class Coverage(unittest.TestCase):
    def test_reports_and_surveyed_provinces_agree(self):
        self.assertEqual(len(sd.SURVEYED), 12)
        self.assertTrue(sd.READ <= set(sd.SURVEYED))
        self.assertEqual(sd.READ | sd.UNREAD, set(sd.SURVEYED))
        self.assertFalse(sd.READ & sd.UNREAD)
        for report in sd.REPORTS:
            self.assertTrue(all(code[:2] == report.province or report.province == "02"
                                for code in report.rows.values()), report.name)
            self.assertEqual(report.whole, not report.coverage, report.name)
            self.assertEqual(len(set(report.rows.values())), len(report.rows), report.name)


if __name__ == "__main__":
    unittest.main()
