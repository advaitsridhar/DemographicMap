"""Samoa's 2021 census by the 2016 census's villages: nesting, matching, columns.

The fixtures are rows in the workbooks' shape -- names indented four spaces a
level -- cut down to a few villages; no network.
"""

import unittest
from unittest import mock

from scripts.fetch_census import samoa_census as sm


class Places(unittest.TestCase):
    def test_depth_is_the_indent(self):
        rows = [["Samoa", 10], ["    Savaii", 10], ["        Salega 1", 10],
                ["            Sagone", 4], [None, None]]
        got = sm.places(rows, 0)
        self.assertEqual([(d, n) for d, n, _ in got],
                         [(0, "Samoa"), (4, "Savaii"), (8, "Salega 1"), (12, "Sagone")])


OLD = [(("Rest of Upolu", "Safata"), "Fusi", 738), (("Rest of Upolu", "Safata"), "Lotofaga", 300),
       (("Rest of Upolu", "Safata"), "Saanapu Tai", 500),
       (("Rest of Upolu", "Lotofaga"), "Lotofaga", 900),
       (("Rest of Upolu", "Lotofaga"), "Vavau", 400),
       (("Rest of Upolu", "Anoamaa West"), "Fusi", 396),
       (("Apia Urban Area", "Faleata East"), "Tuanaimato East", 493),
       (("Apia Urban Area", "Faleata East"), "Moamoa", 1396)]


class Villages(unittest.TestCase):
    def test_a_renamed_village_finds_its_2016_district(self):
        new = [("Safata 2", "Fusi Safata", [833]), ("Anoamaa 2", "Fusi Anoamaa", [428])]
        placed, _ = sm.place_villages(OLD, new)
        self.assertEqual(placed[("Safata 2", "Fusi Safata")], ("Rest of Upolu", "Safata"))
        self.assertEqual(placed[("Anoamaa 2", "Fusi Anoamaa")], ("Rest of Upolu", "Anoamaa West"))

    def test_a_shared_name_goes_with_its_constituency(self):
        new = [("Safata 1", "Saanapu Tai", [500]), ("Safata 1", "Lotofaga", [310]),
               ("Lotofaga", "Vavau", [410]), ("Lotofaga", "Lotofaga", [950])]
        placed, _ = sm.place_villages(OLD, new)
        self.assertEqual(placed[("Safata 1", "Lotofaga")], ("Rest of Upolu", "Safata"))
        self.assertEqual(placed[("Lotofaga", "Lotofaga")], ("Rest of Upolu", "Lotofaga"))

    def test_a_new_village_goes_with_its_constituency_and_is_named(self):
        new = [("Faleata 1", "Moamoa", [1442]), ("Faleata 1", "Tunaimato West", [59])]
        placed, fresh = sm.place_villages(OLD, new)
        self.assertEqual(placed[("Faleata 1", "Tunaimato West")],
                         ("Apia Urban Area", "Faleata East"))
        self.assertEqual(len(fresh), 1)

    def test_a_village_with_nothing_to_go_by_stops_the_run(self):
        with self.assertRaises(SystemExit):
            sm.place_villages(OLD, [("Nowhere 1", "Unheard Of", [5])])


class Columns(unittest.TestCase):
    def test_ages_and_the_unknown_column(self):
        header = ["Place", "Total", None, None, "age 0", None, None, "age 1", None, None,
                  "DK", None, None]
        ages, unknown = sm.age_columns(header)
        self.assertEqual(ages, [(0, 4), (1, 7)])
        self.assertEqual(unknown, 10)

    def test_ages_that_skip_a_year_stop_the_run(self):
        with self.assertRaises(SystemExit):
            sm.age_columns(["Place", "Total", None, None, "age 0", None, None, "age 2"])

    def test_denominations_are_named_and_kept_apart(self):
        header = ["Place", "TOTAL", None, None, "CONGREGATIONAL CHRISTIAN CHURCH", None, None,
                  "LATTER  DAY SAINTS", None, None, "CONGREGATIONAL CHRISTIAN CHURCH", None,
                  None, "MUSLIM"]
        got = sm.religion_columns(header)
        self.assertEqual([n for n, _ in got],
                         ["Congregational Christian Church",
                          "Church of Jesus Christ of Latter-day Saints",
                          "Congregational Christian Church (2)", "Islam"])
        self.assertEqual([i for _, i in got], [4, 7, 10, 13])


# Table 8a's national row and Moataa's as the 2021 workbook prints them; the rest of
# the country is one village here, so that every sum the reader checks holds.
SAMOA_8A = [205557, 104853, 100704, 200508, 102245, 98263, 3127, 1572, 1555, 704, 364, 340,
            1218, 672, 546]
MOATAA_8A = [1420, 715, 705, 1383, 691, 692, 27, 16, 11, 8, 6, 2, 2, 2, 0]
HEADING_8A = ["Place of residence", "Total", None, None,
              "YES BORN IN SAMOA WITH CITIZEN PARENT(S)", None, None,
              "YES BORN ABROAD OF SAMOA WITH CITIZEN PARENT(S)", None, None,
              "YES SAMOA  CITIZEN BY NATURALISATION", None, None,
              "NO NOT A CITIZEN OF SAMOA", None, None]


def table_8a(national=SAMOA_8A, moataa=MOATAA_8A, heading=HEADING_8A):
    rest = [n - m for n, m in zip(national, moataa)]
    return [["Table 8a. Total population by sex, Samoan citizenship status and place of "
             "residence,2021"], [None], heading,
            [None] + ["Total", "MALE", "FEMALE"] * 5,
            ["Samoa"] + national, ["    Apia Urban Area"] + national,
            ["        Vaimauga 2"] + national, ["            Moataa"] + moataa,
            ["            Everywhere else"] + rest]


class Citizenship(unittest.TestCase):
    def test_the_answers_add_up_and_become_two_groups(self):
        got = sm.read_citizenship(table_8a())
        moataa = next(v for _, name, v in got["villages"] if name == "Moataa")
        fields = sm.citizenship_fields([moataa[i] for i in (0, 3, 6, 9, 12)])
        self.assertEqual(fields["ethnicity"], [
            {"group": "Samoan", "pct": 99.9, "count": 1418},
            {"group": "Foreign nationals", "pct": 0.1, "count": 2}])
        self.assertEqual(fields["ethnicity_basis"], "nationality")
        self.assertEqual(fields["ethnicity_year"], 2021)
        self.assertIn("not ethnicity", fields["ethnicity_note"])

    def test_answers_headed_out_of_order_stop_the_run(self):
        heading = list(HEADING_8A)
        heading[7], heading[10] = heading[10], heading[7]
        with self.assertRaises(SystemExit):
            sm.read_citizenship(table_8a(heading=heading))

    def test_answers_that_miss_their_total_stop_the_run(self):
        moataa = list(MOATAA_8A)
        moataa[12] += 1                       # one more non-citizen, the total unchanged
        moataa[13] += 1
        with self.assertRaises(SystemExit):
            sm.read_citizenship(table_8a(moataa=moataa))

    def test_a_country_the_fact_sheet_counts_otherwise_stops_the_run(self):
        national = list(SAMOA_8A)             # one non-citizen read as naturalised
        national[9] += 1
        national[10] += 1
        national[12] -= 1
        national[13] -= 1
        with self.assertRaises(SystemExit):
            sm.read_citizenship(table_8a(national=national))


def layout(males, females, top=None, unknown=(3, 2, 1)):
    """(sub-header, {place: Table 1's row}, ages_at, unknown_at) in Table 1's
    layout, to age ``top`` and then the age not known: every region ten a year of
    each sex at the ages given and ``unknown`` of unknown age, Samoa the four
    together."""
    top = top or max(list(males) + list(females))
    header = ["Place of residence", "Total", "", ""]
    sub = ["", "Total", "MALE", "FEMALE"]
    region = [0.0, 0.0, 0.0]
    for age in range(top + 1):
        header += [f"age {age}", "", ""]
        sub += ["Total", "MALE", "FEMALE"]
        m = 10.0 if age in males else 0.0
        f = 10.0 if age in females else 0.0
        region += [m + f, m, f]
    header += ["DK", "", ""]
    sub += ["Total", "MALE", "FEMALE"]
    region += [float(n) for n in unknown]
    region[:3] = [sum(region[3::3]), sum(region[4::3]), sum(region[5::3])]
    ages_at, unknown_at = sm.age_columns(header)
    rows = {name: list(region) for name in sm.REGIONS}
    rows["Samoa"] = [4 * v for v in region]
    return sub, rows, ages_at, unknown_at


# What the Final Report would print for that layout (males 0-39, females 0-45):
# 15 years of each sex under 15, 25 of males and 31 of females at 15-64.
REGION = {"0-14": (300, 150, 150), "15-64": (560, 250, 310), "65+": (0, 0, 0),
          "age not known": (3, 2, 1)}


def printed_counts(times=None):
    """The key indicators: each region REGION, Samoa four of them, Rural three."""
    times = times or {}
    scale = {"Samoa": 4, "Rural": 3, **times}
    return {place: {group: tuple(scale.get(place, 1) * n for n in counts)
                    for group, counts in REGION.items()}
            for place in ("Samoa", "Apia Urban Area", "North West Upolu", "Rest of Upolu",
                          "Savaii", "Rural")}


class KeyIndicators(unittest.TestCase):
    """Table 1's single years against the Final Report's key indicators."""

    MALES, FEMALES = range(40), range(46)

    def test_every_columns_counts_agree_and_the_medians_are_logged(self):
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES)
        with mock.patch.object(sm, "KEY_INDICATORS", printed_counts()):
            lines = sm.key_indicators(sub, rows, ages_at, unknown_at)
        self.assertIn("for all 6 columns", lines[0])
        # Males 0-39 (median 20.0), females 0-45 (23.0), everyone 21.5.
        self.assertIn("Samoa everyone 21.5 (22), males 20.0 (20), females 23.0 (21)", lines[1])

    def test_medians_far_from_the_printed_ones_do_not_stop_the_run(self):
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES)
        medians = {place: {"everyone": 30, "males": 30, "females": 30}
                   for place in sm.PRINTED_MEDIANS}
        with mock.patch.object(sm, "KEY_INDICATORS", printed_counts()), \
                mock.patch.object(sm, "PRINTED_MEDIANS", medians):
            lines = sm.key_indicators(sub, rows, ages_at, unknown_at)
        self.assertIn("Savaii everyone 21.5 (30)", lines[1])

    def test_a_broad_age_group_one_person_out_stops_the_run(self):
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES)
        table = printed_counts()
        table["Rest of Upolu"]["15-64"] = (561, 251, 310)
        with mock.patch.object(sm, "KEY_INDICATORS", table):
            with self.assertRaises(SystemExit) as caught:
                sm.key_indicators(sub, rows, ages_at, unknown_at)
        self.assertIn("Rest of Upolu 15-64 (560.0, 250.0, 310.0) (printed (561, 251, 310))",
                      str(caught.exception))

    def test_the_age_not_known_is_checked_by_sex(self):
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES)
        table = printed_counts()
        table["Savaii"]["age not known"] = (3, 1, 2)
        with mock.patch.object(sm, "KEY_INDICATORS", table):
            with self.assertRaises(SystemExit):
                sm.key_indicators(sub, rows, ages_at, unknown_at)

    def test_rural_is_samoa_less_the_apia_urban_area(self):
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES, top=55)
        _, older, _, _ = layout(range(50), range(56), top=55)      # an older capital
        rows["Apia Urban Area"] = older["Apia Urban Area"]
        rows["Samoa"] = [sum(rows[r][i] for r in sm.REGIONS) for i in range(len(rows["Samoa"]))]
        table = printed_counts()
        table["Apia Urban Area"] = {"0-14": (300, 150, 150), "15-64": (760, 350, 410),
                                    "65+": (0, 0, 0), "age not known": (3, 2, 1)}
        table["Samoa"] = {group: tuple(a + 3 * b for a, b in zip(table["Apia Urban Area"][group],
                                                                 REGION[group]))
                          for group in REGION}
        with mock.patch.object(sm, "KEY_INDICATORS", table):
            lines = sm.key_indicators(sub, rows, ages_at, unknown_at)
        self.assertIn("Rural everyone 21.5 (20), males 20.0 (20), females 23.0 (21)", lines[1])

    def test_the_rows_as_read_from_the_sheet_reach_the_age_not_known_by_sex(self):
        # The run reads Table 1 to table1_width; the age not known comes last,
        # and its MALE and FEMALE columns must be inside what is read.
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES)
        header = ["Place of residence", "Total", "", ""] + [
            label for age, _ in ages_at for label in (f"age {age}", "", "")] + ["DK", "", ""]
        sheet = [["Table 1:Total population by single age"], header, sub,
                 ["Samoa"] + rows["Samoa"]]
        for k, region in enumerate(sm.REGIONS):
            sheet += [["    " + region] + rows[region],
                      [f"        Constituency {k}"] + rows[region],
                      [f"            Village {k}"] + rows[region]]
        width = sm.table1_width(ages_at, unknown_at)
        with mock.patch.object(sm, "NATIONAL", rows["Samoa"][0]):
            people = sm.read_2021(sheet, width)
        self.assertEqual(width, len(rows["Samoa"]))
        with mock.patch.object(sm, "KEY_INDICATORS", printed_counts()):
            lines = sm.key_indicators(sub, {"Samoa": people["total"], **people["regions"]},
                                      ages_at, unknown_at)
        self.assertIn("exactly", lines[0])

    def test_columns_that_are_not_total_male_female_stop_the_run(self):
        sub, rows, ages_at, unknown_at = layout(self.MALES, self.FEMALES)
        sub[5], sub[6] = "FEMALE", "MALE"
        with mock.patch.object(sm, "KEY_INDICATORS", printed_counts()):
            with self.assertRaises(SystemExit):
                sm.key_indicators(sub, rows, ages_at, unknown_at)

    def test_the_real_key_indicators_add_up(self):
        # The transcription of pp. 10-11: each column's groups make its people
        # (p. 10's Population rows), its sexes make each group, and Rural is
        # Samoa less the Apia Urban Area.
        people = {"Samoa": (205_557, 104_853, 100_704), "Apia Urban Area": (35_974, 17_990, 17_984),
                  "North West Upolu": (75_307, 38_331, 36_976),
                  "Rest of Upolu": (49_101, 25_383, 23_718), "Savaii": (45_175, 23_149, 22_026),
                  "Rural": (169_583, 86_863, 82_720)}
        for place, groups in sm.KEY_INDICATORS.items():
            made = tuple(sum(g[k] for g in groups.values()) for k in range(3))
            self.assertEqual(made, people[place], place)
            for group, (everyone, males, females) in groups.items():
                self.assertEqual(everyone, males + females, (place, group))
        for group in sm.KEY_INDICATORS["Samoa"]:
            self.assertEqual(sm.KEY_INDICATORS["Rural"][group],
                             tuple(a - b for a, b in zip(sm.KEY_INDICATORS["Samoa"][group],
                                                         sm.KEY_INDICATORS["Apia Urban Area"][group])))
            regions = tuple(sum(sm.KEY_INDICATORS[r][group][k] for r in sm.REGIONS) for k in range(3))
            self.assertEqual(regions, sm.KEY_INDICATORS["Samoa"][group], group)


if __name__ == "__main__":
    unittest.main()
