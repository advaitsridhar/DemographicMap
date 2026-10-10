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


def age_obs(area, age, sex, value, eth="999"):
    return {"CEN23_GEO_002": area, "CEN23_ETH_002": eth, "CEN23_AGE_001": age,
            "CEN23_SAB_002": sex, "OBS_VALUE": value, "OBS_STATUS": ""}


# The national row and Far North District as CEN23_POP_006 returns them.
NATIONAL_AGES = [
    age_obs("999999", "Median", "999", "38.1"),
    age_obs("999999", "99", "999", "4993923"),
    age_obs("999999", "99", "11", "2470893"),
    age_obs("999999", "99", "22", "2523030"),
]
FAR_NORTH = [
    age_obs("001", "Median", "999", "44.3"),
    age_obs("001", "99", "999", "71430"),
    age_obs("001", "99", "11", "35619"),
    age_obs("001", "99", "22", "35811"),
]


class AgeAndSex(unittest.TestCase):
    def setUp(self):
        self.tiers = {"01": "admin1", "001": "admin2", "067": "admin2"}

    def test_the_median_and_the_sexes_are_read(self):
        got = nz.age_sex(NATIONAL_AGES + FAR_NORTH, self.tiers)
        self.assertEqual(got["001"], {"median": 44.3, "total": 71430,
                                      "male": 35619, "female": 35811})
        nz.check_ages(got)

    def test_only_the_all_ethnicities_column_is_read(self):
        rows = FAR_NORTH + [age_obs("001", "Median", "999", "30.0", eth="2")]
        self.assertEqual(nz.age_sex(rows, self.tiers)["001"]["median"], 44.3)

    def test_the_fields_are_the_census_median_and_males_per_100_females(self):
        fields = nz.age_fields(nz.age_sex(FAR_NORTH, self.tiers)["001"])
        self.assertEqual(fields["median_age"]["value"], 44.3)
        self.assertEqual(fields["median_age"]["year"], 2023)
        self.assertEqual(fields["sex_ratio"]["value"], 99.5)
        self.assertEqual(fields["sex_ratio"]["unit"], "males_per_100_females")

    def test_sexes_that_do_not_make_the_total_stop_the_run(self):
        rows = [age_obs("001", "99", "999", "71430"), age_obs("001", "99", "11", "30000"),
                age_obs("001", "99", "22", "35811")]
        with self.assertRaises(SystemExit):
            nz.age_sex(rows, self.tiers)

    def test_a_different_national_median_stops_the_run(self):
        rows = [age_obs("999999", "Median", "999", "37.4")] + NATIONAL_AGES[1:]
        with self.assertRaises(SystemExit):
            nz.check_ages(nz.age_sex(rows, self.tiers))

    def test_an_area_with_no_counts_writes_nothing(self):
        self.assertEqual(nz.age_fields(None), {})


class SmallArea(unittest.TestCase):
    def test_a_withheld_figure_says_the_counts_are_randomly_rounded(self):
        # The Area Outside Territorial Authority: 72 people, 48 men and 27 women.
        from scripts.fetch_census.oceania_common import withhold_small
        fields = {"sex_ratio": {"value": 177.8, "unit": "males_per_100_females"},
                  "religion": [{"group": "No religion", "pct": 100.0}],
                  "median_age": {"value": 54.5}, "median_age_note": "Stats NZ's own median."}
        out = withhold_small(fields, 72, 48, 27, counting=nz.ROUNDING)
        said = ("72 people (48 men and 27 women; Stats NZ randomly rounds every count to base 3, "
                "so the men and the women need not add up to the total)")
        for field in ("religion", "sex_ratio"):
            self.assertIn(said, out[field]["note"])
        self.assertIn(said, out["median_age_note"])


class Chatham(unittest.TestCase):
    def test_the_territory_is_written_for_its_first_level_polygon(self):
        territory = nz.record("NZL-067", "Chatham Islands Territory", level="admin2",
                              parent=None, country="NZL", codes={"statsnz": "067"},
                              population={"value": 612, "year": 2023},
                              median_age={"value": 44.0, "year": 2023},
                              median_age_note="Stats NZ's own median.")
        other = nz.record("NZL-001", "Far North District", level="admin2", parent=None,
                          country="NZL", codes={"statsnz": "001"})
        region = nz.chatham_region([other, territory])
        self.assertEqual(region["level"], "admin1")
        self.assertEqual(region["parent"], "NZL")
        self.assertEqual(region["name"], "Chatham Islands Territory")
        self.assertEqual(region["population"]["value"], 612)
        self.assertIn("Area Outside Region", region["median_age_note"])
        # The territorial authority's own record is not changed.
        self.assertEqual(territory["level"], "admin2")
        self.assertNotIn("Area Outside Region", territory["median_age_note"])

    def test_no_territory_no_region(self):
        self.assertIsNone(nz.chatham_region([]))


if __name__ == "__main__":
    unittest.main()
