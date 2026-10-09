"""India: Census 2011 table D-01, place of birth, as country of birth on the ethnicity field.

Synthetic sheets in the table's layout -- one state of three districts -- and
drawn units for them. No network.
"""

import collections
import unittest
from unittest import mock

from scripts.fetch_census import india_birthplace as ib

STATES = ("Jammu & Kashmir", "Punjab", "Testland")
ASIA = ("Bangladesh", "Nepal", "Pakistan", "China")


def split(n: int) -> tuple[int, int, int]:
    """Persons, males and females: twice the figure given, half men."""
    return 2 * n, n, n


def unit_rows(state: str, district: str, area: str, *, place: int, district_rest: int,
              others: int, states: dict[str, int], asia: dict[str, int],
              asia_rest: int, europe: dict[str, int], europe_rest: int,
              unclassifiable: int) -> list[list]:
    """One unit's rows, every sum the table implies kept."""
    within = place + district_rest + others
    other_states = sum(states.values())
    india = within + other_states
    asia_total = sum(asia.values()) + asia_rest
    europe_total = sum(europe.values()) + europe_rest
    outside = asia_total + europe_total
    total = india + outside + unclassifiable
    rows = [("Total Population", total), ("Born within India", india),
            ("Within the state of enumeration", within),
            ("Born in the place of enumeration", place),
            ("Born elsewhere in the district of enumeration", district_rest),
            ("Born in other districts of the state", others),
            ("States in India beyond the state of enumeration", other_states),
            *states.items(),
            ("Born Outside India", outside),
            ("Countries in Asia beyond India", asia_total), *asia.items(),
            ("Elsewhere", asia_rest),
            ("Countries in Europe", europe_total), *europe.items(),
            ("Elsewhere", europe_rest),
            ("Unclassifiable", unclassifiable)]
    return [["D0101", state, district, area, label, *split(n), *split(n), 0, 0, 0]
            for label, n in rows]


def district(code: str, name: str, scale: int) -> list[list]:
    return unit_rows("05", code, name, place=600 * scale, district_rest=200 * scale,
                     others=100 * scale,
                     states={"Jammu & Kashmir": 3 * scale, "Punjab": 7 * scale,
                             "Testland": 0},
                     asia={"Bangladesh": 40 * scale, "Nepal": 5 * scale,
                           "Pakistan": 9 * scale, "China": scale},
                     asia_rest=2 * scale, europe={"UK": scale}, europe_rest=scale,
                     unclassifiable=3 * scale)


def state_rows() -> list[list]:
    scales = {"101": 1, "102": 2, "103": 3}
    total = sum(scales.values())
    head = [["D-1: POPULATION CLASSIFIED BY PLACE OF BIRTH AND SEX - 2011"],
            ["Table name", "State", "District", "Area Name", "Birth place"],
            [None, None, None, None, 1, 2, 3, 4]]
    body = unit_rows("05", "000", "State - TESTLAND (05)", place=600 * total,
                     district_rest=200 * total, others=100 * total,
                     states={"Jammu & Kashmir": 3 * total, "Punjab": 7 * total,
                             "Testland": 0},
                     asia={"Bangladesh": 40 * total, "Nepal": 5 * total,
                           "Pakistan": 9 * total, "China": total},
                     asia_rest=2 * total, europe={"UK": total}, europe_rest=total,
                     unclassifiable=3 * total)
    for code, name in (("101", "Alpha"), ("102", "Beta"), ("103", "Gamma")):
        body += district(code, name, scales[code])
    return head + body


def read() -> dict:
    return {key: ib.interpret(unit) for key, unit in ib.read_rows(state_rows()).items()}


def census(n: int) -> dict:
    return {"value": n, "year": 2011, "source": "Census of India 2011, table C-01"}


def shapes(units: dict) -> tuple[list[dict], list[dict]]:
    shapes1 = [{"id": "S05", "name": "Testland", "codes": {"census2011_state": "05"},
                "population": census(units[("05", "000")]["total"])}]
    shapes2 = [
        {"id": "D101", "name": "Alpha", "parent": "S05",
         "codes": {"census2011_district": "101"},
         "population": census(units[("05", "101")]["total"])},
        {"id": "D102", "name": "Beta", "parent": "S05",
         "codes": {"census2011_district": "102"},
         "population": census(units[("05", "102")]["total"])},
        {"id": "Dnew", "name": "Delta", "parent": "S05"},
        {"id": "Dg1", "name": "Gamma East", "parent": "S05"},
        {"id": "Dg2", "name": "Gamma West", "parent": "S05"},
    ]
    return shapes1, shapes2


def tables():
    return mock.patch.multiple(
        ib, CREATED_AFTER_2011={"Testland": (("Delta", 2016, ("Beta",)),)},
        SUBDIVIDED_SINCE_2011={"gamma": ["Gamma East", "Gamma West"]},
        BOUNDARY_ARTEFACTS={},
        lost_territory=lambda: {("testland", "beta"): (60, (("Delta", 2016),))})


class Reading(unittest.TestCase):
    def test_every_unit_is_read_and_its_sums_checked(self):
        units = read()
        self.assertEqual(set(units), {("05", "000"), ("05", "101"), ("05", "102"),
                                      ("05", "103")})
        alpha = units[("05", "101")]
        self.assertEqual(alpha["india"], 1820)
        self.assertEqual(alpha["outside"], 118)
        self.assertEqual(alpha["unclassifiable"], 6)
        self.assertEqual(alpha["total"], 1944)
        self.assertEqual(alpha["countries"]["Bangladesh"], 80)
        self.assertEqual(alpha["elsewhere"], 6)

    def test_sexes_that_do_not_make_persons_stop_the_run(self):
        rows = state_rows()
        bad = next(r for r in rows if len(r) > 4 and r[4] == "Nepal")
        bad[6] += 1                                  # a male too many
        with self.assertRaises(SystemExit):
            [ib.interpret(u) for u in ib.read_rows(rows).values()]

    def test_a_continent_that_does_not_make_its_countries_stops_the_run(self):
        rows = state_rows()
        bad = next(r for r in rows if len(r) > 4 and r[4] == "UK")
        bad[5:8] = [bad[5] + 2, bad[6] + 1, bad[7] + 1]
        with self.assertRaises(SystemExit):
            [ib.interpret(u) for u in ib.read_rows(rows).values()]

    def test_a_row_the_table_does_not_have_stops_the_run(self):
        rows = state_rows()
        rows.insert(4, ["D0101", "05", "000", "State - TESTLAND (05)",
                        "Born on a ship", 1, 1, 0])
        with self.assertRaises(SystemExit):
            [ib.interpret(u) for u in ib.read_rows(rows).values()]

    def test_districts_must_make_their_state(self):
        units = read()
        india = ib.combine([units[("05", "000")]], "India")
        with mock.patch.multiple(ib, INDIA_POPULATION=india["total"], DISTRICTS_2011=3):
            ib.check_all(units, india)
            units[("05", "103")]["countries"]["Nepal"] += 1
            units[("05", "103")]["countries"]["Pakistan"] -= 1
            with self.assertRaises(SystemExit):
                ib.check_all(units, india)

    def test_the_all_india_total_is_checked(self):
        units = read()
        india = ib.combine([units[("05", "000")]], "India")
        with mock.patch.multiple(ib, INDIA_POPULATION=india["total"] + 1,
                                 DISTRICTS_2011=3), self.assertRaises(SystemExit):
            ib.check_all(units, india)


class Labels(unittest.TestCase):
    def test_countries_over_the_floor_are_named_and_the_rest_are_other(self):
        units = read()
        state = units[("05", "000")]
        with mock.patch.object(ib, "NAMED_FLOOR", 100):
            named = ib.named_countries(state)
        self.assertEqual(named, {"Bangladesh": "Bangladeshi", "Pakistan": "Pakistani"})
        counts = ib.composition(units[("05", "101")], named)
        self.assertEqual(counts, {"Indian": 1820, "Bangladeshi": 80, "Pakistani": 18,
                                  "Other": 20, "Not stated": 6})
        self.assertEqual(sum(counts.values()), units[("05", "101")]["total"])

    def test_a_large_country_without_a_label_stops_the_run(self):
        units = read()
        with mock.patch.object(ib, "NAMED_FLOOR", 10), self.assertRaises(SystemExit):
            ib.named_countries(units[("05", "000")])     # China, 12 people


class Binding(unittest.TestCase):
    def build(self, units: dict | None = None):
        units = units or read()
        shapes1, shapes2 = shapes(units)
        named = {"Bangladesh": "Bangladeshi", "Pakistan": "Pakistani"}
        with tables():
            return ib.records(units, {"05": "https://example.org/d01"}, named,
                              shapes1, shapes2)

    def test_an_unchanged_district_takes_its_row_by_code(self):
        main, successors, tally = self.build()
        alpha = next(r for r in main if r["shape_id"] == "D101")
        self.assertEqual(alpha["match_by"], "shape_id")
        self.assertEqual(alpha["ethnicity_basis"], "country of birth")
        self.assertEqual(alpha["ethnicity_year"], 2011)
        shares = {row["group"]: row["pct"] for row in alpha["ethnicity"]}
        self.assertEqual(shares["Indian"], round(100 * 1820 / 1944, 1))
        self.assertIn("not a citizenship or an ethnic group", alpha["ethnicity_note"])
        self.assertEqual(tally["district, unchanged since 2011"], 1)

    def test_a_shape_that_kept_a_name_is_a_gap_here_and_the_row_in_the_other_file(self):
        main, successors, _ = self.build()
        beta = next(r for r in main if r["shape_id"] == "D102")
        self.assertEqual(beta["ethnicity"]["status"], "not_available")
        self.assertIn("keeps about 60%", beta["ethnicity"]["note"])
        self.assertEqual([r["shape_id"] for r in successors], ["D102"])
        self.assertIn("Delta", successors[0]["ethnicity_note"])

    def test_new_and_divided_districts_say_why_they_have_nothing(self):
        main, _, tally = self.build()
        delta = next(r for r in main if r["shape_id"] == "Dnew")
        self.assertIn("created in 2016", delta["ethnicity"]["note"])
        east = next(r for r in main if r["shape_id"] == "Dg1")
        self.assertIn("undivided Gamma", east["ethnicity"]["note"])
        self.assertEqual(tally["successor of a district divided whole"], 2)
        self.assertEqual(tally["2011 district with no shape (divided since)"], 1)

    def test_the_state_takes_its_own_row(self):
        main, _, tally = self.build()
        state = next(r for r in main if r["level"] == "admin1")
        self.assertEqual(state["shape_id"], "S05")
        counts = collections.Counter({row["group"]: row["count"] for row in state["ethnicity"]})
        self.assertEqual(counts["Indian"], 1820 * 6)
        self.assertEqual(tally["state"], 1)

    def test_a_code_on_the_wrong_polygon_stops_the_run(self):
        units = read()
        shapes1, shapes2 = shapes(units)
        shapes2[0]["population"] = census(units[("05", "101")]["total"] + 1)
        with tables(), self.assertRaises(SystemExit):
            ib.records(units, {"05": "u"}, {}, shapes1, shapes2)

    def test_an_uncoded_shape_in_no_table_stops_the_run(self):
        units = read()
        shapes1, shapes2 = shapes(units)
        shapes2.append({"id": "Dx", "name": "Nowhere", "parent": "S05"})
        with tables(), self.assertRaises(SystemExit):
            ib.records(units, {"05": "u"}, {}, shapes1, shapes2)


def territory(code: str, area: str, scale: int) -> dict:
    rows = unit_rows(code, "000", area, place=600 * scale, district_rest=200 * scale,
                     others=100 * scale, states={"Testland": scale},
                     asia={"Bangladesh": scale}, asia_rest=0, europe={},
                     europe_rest=0, unclassifiable=scale)
    return ib.interpret(ib.read_rows(rows)[(code, "000")])


class MergedTerritory(unittest.TestCase):
    """Dadra and Nagar Haveli and Daman and Diu: two territories in 2011, one drawn."""

    def merged_shape(self, codes: dict) -> dict:
        return {"id": "S26", "name": "Dādra and Nagar Haveli and Damān and Diu",
                "site_name": "Dādra and Nagar Haveli and Damān and Diu", "codes": codes}

    def test_the_merged_territory_is_known_without_a_state_code(self):
        for codes in ({"census2011_state": "26"},
                      {"census2011_state_name": "Dadra and Nagar Haveli + Daman and Diu"},
                      {}):
            self.assertEqual(ib.state_code_2011(self.merged_shape(codes)), "26", codes)
        self.assertEqual(ib.state_code_2011({"name": "Goa", "codes": {"census2011_state": "30"}}),
                         "30")
        self.assertIsNone(ib.state_code_2011({"name": "Goa", "codes": {}}))

    def test_it_sums_both_territories_when_the_build_kept_only_their_names(self):
        units = read()
        units[("25", "000")] = territory("25", "State - DAMAN & DIU (25)", 1)
        units[("26", "000")] = territory("26", "State - DADRA & NAGAR HAVELI (26)", 2)
        shapes1, shapes2 = shapes(units)
        shapes1.append(self.merged_shape(
            {"census2011_state_name": "Dadra and Nagar Haveli + Daman and Diu"}))
        with tables():
            main, _, tally = ib.records(units, {"05": "u", "26": "https://example.org/26"},
                                        {"Bangladesh": "Bangladeshi"}, shapes1, shapes2)
        merged = next(r for r in main if r["shape_id"] == "S26")
        total = sum(row["count"] for row in merged["ethnicity"])
        self.assertEqual(total, units[("25", "000")]["total"] + units[("26", "000")]["total"])
        self.assertIn("merged in 2020", merged["ethnicity_note"])
        self.assertEqual(tally["state"], 2)


if __name__ == "__main__":
    unittest.main()
