"""New Zealand: reading tiers and compositions out of Stats NZ's SDMX.

The fixtures are the shape the API actually returns, cut down to a handful of
codes. Nothing here touches the network or the API key: the parsing is the part
that can be wrong, and it is the part that is tested.
"""

import unittest

from scripts.fetch_census import new_zealand as nz


# One codelist per tier total, with the collision that made this necessary:
# 076 is Auckland the territorial authority, 102 is Auckland the health
# district, and they are the same width and the same name.
AREAS = """
<structure:Codelist id="CL_CEN23_GEO_002">
  <structure:Code id="01"><common:Name>Northland Region</common:Name>
    <structure:Parent><Ref id="9999" /></structure:Parent></structure:Code>
  <structure:Code id="076"><common:Name>Auckland</common:Name>
    <structure:Parent><Ref id="999999" /></structure:Parent></structure:Code>
  <structure:Code id="047"><common:Name>Wellington City</common:Name>
    <structure:Parent><Ref id="999999" /></structure:Parent></structure:Code>
  <structure:Code id="07604"><common:Name>Kaipātiki Local Board Area</common:Name>
    <structure:Parent><Ref id="999999" /></structure:Parent></structure:Code>
  <structure:Code id="10"><common:Name>Northern Region</common:Name>
    <structure:Parent><Ref id="99999" /></structure:Parent></structure:Code>
  <structure:Code id="102"><common:Name>Auckland</common:Name>
    <structure:Parent><Ref id="10" /></structure:Parent></structure:Code>
  <structure:Code id="047100"><common:Name>Thorndon-Tinakori Road</common:Name>
    <structure:Parent><Ref id="047" /></structure:Parent></structure:Code>
</structure:Codelist>
"""

RELIGIONS = """
<structure:Codelist id="CL_CEN23_REA_003">
  <structure:Code id="05"><common:Name>Catholicism</common:Name></structure:Code>
  <structure:Code id="24"><common:Name>No religion</common:Name></structure:Code>
  <structure:Code id="25"><common:Name>Object to answering</common:Name></structure:Code>
  <structure:Code id="999"><common:Name>Total - religious affiliation</common:Name></structure:Code>
</structure:Codelist>
"""


def obs(area, code, value, status="", dim="CEN23_REA_003"):
    return {"CEN23_GEO_002": area, dim: code, "OBS_VALUE": value,
            "OBS_STATUS": status}


class Tiers(unittest.TestCase):
    def setUp(self):
        self.tiers = nz.levels(AREAS)

    def test_regional_councils_and_the_talb_tier_are_kept(self):
        self.assertEqual(self.tiers["01"], "admin1")
        self.assertEqual(self.tiers["047"], "admin2")
        self.assertEqual(self.tiers["07604"], "admin2")
        self.assertEqual(self.tiers["076"], "admin2")

    def test_health_areas_are_not_a_geography_this_map_shows(self):
        # 102 is Auckland the health district. Three digits, same name as the
        # territorial authority, and emitting it would make Auckland ambiguous.
        self.assertNotIn("102", self.tiers)
        self.assertNotIn("10", self.tiers)

    def test_statistical_areas_are_left_out(self):
        self.assertNotIn("047100", self.tiers)

    def test_a_local_board_keeps_its_macrons(self):
        names = nz.codelist(AREAS, "CL_CEN23_GEO_002")
        self.assertEqual(names["07604"], "Kaipātiki Local Board Area")


class Compositions(unittest.TestCase):
    def setUp(self):
        self.tiers = nz.levels(AREAS)
        self.labels = nz.codelist(RELIGIONS, "CL_CEN23_REA_003")

    def build(self, rows):
        return nz.compositions(rows, "CEN23_REA_003", self.labels, self.tiers)

    def test_the_printed_total_is_the_denominator(self):
        got = self.build([
            obs("047", "999", "1000"),
            obs("047", "05", "250"),
            obs("047", "24", "600"),
        ])
        self.assertEqual(got["047"]["total"], 1000)
        self.assertEqual(got["047"]["counts"],
                         {"Catholicism": 250, "No religion": 600})

    def test_a_withheld_cell_is_named_not_zeroed(self):
        # Stats NZ suppresses cells too small to publish. Reading one as zero
        # would turn "we will not say" into "nobody".
        got = self.build([
            obs("047", "999", "1000"),
            obs("047", "05", "", "c"),
            obs("047", "24", "600"),
        ])
        self.assertNotIn("Catholicism", got["047"]["counts"])
        self.assertEqual(got["047"]["suppressed"], ["Catholicism"])

    def test_health_areas_never_reach_a_composition(self):
        got = self.build([obs("102", "999", "1000"), obs("102", "05", "250")])
        self.assertNotIn("102", got)

    def test_the_national_row_is_kept_even_though_it_is_no_tier(self):
        got = self.build([obs("999999", "999", "4993923"),
                          obs("999999", "05", "449466")])
        self.assertIn("999999", got)


class NationalControls(unittest.TestCase):
    def test_the_published_figures_are_required(self):
        built = {"999999": {"total": 4_993_923,
                            "counts": {"No religion": 2_576_049,
                                       "Catholicism": 449_466,
                                       "Hinduism": 144_753,
                                       "Islam": 75_138},
                            "suppressed": []}}
        nz.check_national("religion", built)   # does not raise

    def test_a_different_slice_stops_the_run(self):
        built = {"999999": {"total": 4_993_923,
                            "counts": {"No religion": 2_000_000,
                                       "Catholicism": 449_466,
                                       "Hinduism": 144_753,
                                       "Islam": 75_138},
                            "suppressed": []}}
        with self.assertRaises(SystemExit):
            nz.check_national("religion", built)

    def test_a_wrong_population_stops_the_run(self):
        built = {"999999": {"total": 5_000_000, "counts": {}, "suppressed": []}}
        with self.assertRaises(SystemExit):
            nz.check_national("religion", built)


class Hierarchy(unittest.TestCase):
    def test_only_level_one_ethnicity_is_read(self):
        # 1 European is the parent of 111 New Zealand European and the rest.
        # Both levels are in one codelist, so summing the column would count
        # most of the country twice.
        self.assertEqual(nz.ETHNICITY_LEVEL_1,
                         {"1", "2", "3", "4", "5", "6", "9"})
        for child in ("111", "122", "311", "421", "511"):
            self.assertNotIn(child, nz.ETHNICITY_LEVEL_1)


if __name__ == "__main__":
    unittest.main()
