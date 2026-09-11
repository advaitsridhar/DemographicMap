"""India: the post-2011 district table, and the checks that gate it.

The fixtures are rows as the two readers print them -- the census extract's own
column names and figures for four real districts, and the
``(state, district, area, group, persons)`` tuples
``india_language.read_workbook`` returns for Meghalaya. No network and no
workbook: both readers are pure functions of those rows.

What is being tested is mostly refusal. ``CREATED_AFTER_2011`` is a hand-built
table of prose about places, and prose nobody re-reads is how a wrong claim
ships; the point of :func:`check_new_districts` is that every line of it is
arithmetic against the census's own district list on every run. So each way it
can be wrong gets a test that proves the run stops.
"""

import unittest
from unittest import mock

from scripts.fetch_census import india_census, india_language


# Four real rows of the district extract, trimmed to the columns the reader
# reads. Jaintia Hills is one of the three districts SUBDIVIDED_SINCE_2011
# names; Surguja and Thane are predecessors the post-2011 table points at;
# Warangal is the predecessor that has itself since been abolished.
ROWS = [
    {"District code": "299", "State name": "MEGHALAYA", "District name": "Jaintia Hills",
     "Population": "395124", "Male": "196285", "Female": "198839",
     "Hindus": "12456", "Muslims": "1646", "Christians": "271596", "Sikhs": "34",
     "Buddhists": "284", "Jains": "45", "Others_Religions": "107559",
     "Religion_Not_Stated": "1504", "SC": "1317", "ST": "376099"},
    {"District code": "401", "State name": "CHHATTISGARH", "District name": "Surguja",
     "Population": "2359886", "Male": "1193129", "Female": "1166757",
     "Hindus": "2126195", "Muslims": "81442", "Christians": "97432", "Sikhs": "2303",
     "Buddhists": "1287", "Jains": "623", "Others_Religions": "48295",
     "Religion_Not_Stated": "2309", "SC": "115652", "ST": "1300628"},
    {"District code": "517", "State name": "MAHARASHTRA", "District name": "Thane",
     "Population": "11060148", "Male": "5865078", "Female": "5195070",
     "Hindus": "8716055", "Muslims": "1355630", "Christians": "280700",
     "Sikhs": "39149", "Buddhists": "449617", "Jains": "172052",
     "Others_Religions": "9862", "Religion_Not_Stated": "37083",
     "SC": "730089", "ST": "1542451"},
    {"District code": "540", "State name": "ANDHRA PRADESH", "District name": "Warangal",
     "Population": "3512576", "Male": "1759281", "Female": "1753295",
     "Hindus": "3273755", "Muslims": "197333", "Christians": "31377", "Sikhs": "1453",
     "Buddhists": "253", "Jains": "569", "Others_Religions": "126",
     "Religion_Not_Stated": "7710", "SC": "616102", "ST": "530656"},
]

# A table small enough to reason about, declaring one district against each of
# the three shapes of predecessor: one still standing (Surguja, Thane) and one
# abolished (Warangal).
TABLE = {
    "Chhattisgarh": (("Balrampur", 2012, ("Surguja",)),),
    "Maharashtra": (("Palghar", 2014, ("Thane",)),),
    "Telangana": (("Jangaon", 2016, ("Warangal",)),),
}


def emitted(table=TABLE, rows=ROWS):
    """The district records, with the post-2011 table swapped for a small one."""
    with mock.patch.dict(india_census.CREATED_AFTER_2011, table, clear=True):
        return {r["name"]: r for r in india_census.districts(rows)}


def refusal(table, rows=ROWS):
    """The message check_new_districts refuses `table` with, or '' if it allows it."""
    with mock.patch.dict(india_census.CREATED_AFTER_2011, table, clear=True):
        try:
            india_census.check_new_districts(rows)
        except SystemExit as exit_:
            return str(exit_)
    return ""


class NewDistricts(unittest.TestCase):
    def test_a_district_the_census_never_had_gets_a_gap_naming_its_predecessor(self):
        got = emitted()["Palghar"]
        note = got["religion"]["note"]
        self.assertEqual(got["religion"]["status"], india_census.NOT_AVAILABLE)
        self.assertIn("created in 2014", note)
        self.assertIn("Thane", note)
        # The reader is told where the measurement covering this ground is.
        self.assertIn("are on this map under that name", note)

    def test_a_predecessor_that_is_itself_gone_is_not_offered_as_somewhere_to_look(self):
        # Warangal was split six ways and its name is on no present-day shape,
        # so pointing at "the district of that name" would send the reader to a
        # place that does not exist.
        note = emitted()["Jangaon"]["religion"]["note"]
        self.assertIn("Warangal has itself since been subdivided", note)
        self.assertNotIn("are on this map under that name", note)

    def test_the_gap_reaches_every_field_the_census_would_have_filled(self):
        got = emitted()["Balrampur"]
        for field in ("population", "religion", "language"):
            with self.subTest(field=field):
                self.assertEqual(got[field]["status"], india_census.NOT_AVAILABLE)
                self.assertIn("Surguja", got[field]["note"])
        # Ethnicity is a different kind of absence and keeps its own status:
        # India does not ask the question of anyone, anywhere.
        self.assertEqual(got["ethnicity"]["status"], india_census.NOT_COLLECTED)

    def test_a_new_district_carries_no_figures_at_all(self):
        got = emitted()["Palghar"]
        for field in ("population", "religion", "language", "sex_ratio"):
            with self.subTest(field=field):
                self.assertNotIsInstance(got[field], list)
                self.assertIsNone(got[field].get("value"))

    def test_the_state_travels_with_the_row(self):
        # Chhattisgarh's Balrampur and Uttar Pradesh's are different districts
        # with one name, and only the state keeps this gap off the real figures
        # of the other.
        self.assertEqual(emitted()["Balrampur"]["parent_name"], "Chhattisgarh")

    def test_the_boundary_artefact_is_declared_not_a_district(self):
        note = emitted()["DATA NOT AVAILABLE"]["religion"]["note"]
        self.assertIn("not a district", note)
        self.assertIn("268 disjoint fragments", note)


class Refusals(unittest.TestCase):
    def test_declaring_a_district_the_census_enumerated(self):
        # The worst of the failures: a note saying no figure exists, hiding one
        # that does.
        message = refusal({"Maharashtra": (("Thane", 2014, ("Thane",)),)})
        self.assertIn("would hide a real figure", message)

    def test_a_predecessor_the_census_never_had(self):
        message = refusal({"Maharashtra": (("Palghar", 2014, ("Thana",)),)})
        self.assertIn("'Thana' is not a 2011 census district", message)

    def test_a_predecessor_from_the_wrong_state(self):
        # Surguja is real, and it is in Chhattisgarh. Naming it as Palghar's
        # parent is a claim about where these people were counted that the
        # census contradicts.
        message = refusal({"Maharashtra": (("Palghar", 2014, ("Surguja",)),)})
        self.assertIn("is not a 2011 census district of Maharashtra", message)

    def test_telangana_is_checked_against_andhra_pradesh(self):
        # Telangana did not exist in 2011, so its predecessors are Andhra
        # Pradesh's districts and the check has to know that. Warangal passes;
        # a Telangana spelling of a state that never enumerated it would not.
        self.assertEqual("", refusal({"Telangana": (("Jangaon", 2016, ("Warangal",)),)}))
        message = refusal({"Chhattisgarh": (("Jangaon", 2016, ("Warangal",)),)})
        self.assertIn("is not a 2011 census district of Chhattisgarh", message)

    def test_a_district_declared_twice(self):
        message = refusal({"Maharashtra": (("Palghar", 2014, ("Thane",)),
                                           ("Palghar", 2014, ("Thane",)))})
        self.assertIn("is declared twice", message)

    def test_a_district_that_is_also_a_subdivided_successor(self):
        # Both tables produce a gap record under the same name, which would put
        # two rows on one shape and let the later one decide what it says.
        message = refusal({"Telangana": (("Warangal (R)", 2016, ("Warangal",)),)})
        self.assertIn("SUBDIVIDED_SINCE_2011", message)

    def test_a_year_that_is_a_typo(self):
        message = refusal({"Maharashtra": (("Palghar", 1914, ("Thane",)),)})
        self.assertIn("is outside", message)

    def test_a_district_with_no_predecessor(self):
        message = refusal({"Maharashtra": (("Palghar", 2014, ()),)})
        self.assertIn("names no predecessor", message)

    def test_a_refusal_emits_nothing(self):
        with mock.patch.dict(india_census.CREATED_AFTER_2011,
                             {"Maharashtra": (("Palghar", 2014, ("Thana",)),)},
                             clear=True):
            with self.assertRaises(SystemExit):
                india_census.districts(ROWS)


class TableIsSelfConsistent(unittest.TestCase):
    """The real table, checked against the rest of the module rather than a fixture."""

    def names(self):
        return {(state, name)
                for state, entries in india_census.CREATED_AFTER_2011.items()
                for name, _, _ in entries}

    def test_every_spelling_correction_belongs_to_a_declared_district(self):
        declared = {name for _, name in self.names()}
        for boundary_name in india_census.NEW_DISTRICT_ALIASES:
            with self.subTest(name=boundary_name):
                self.assertIn(boundary_name, declared)

    def test_no_declared_district_is_also_a_subdivided_successor(self):
        successors = {name for names in india_census.SUBDIVIDED_SINCE_2011.values()
                      for name in names}
        self.assertEqual(set(), {n for _, n in self.names()} & successors)

    def test_the_states_that_did_not_exist_in_2011_are_mapped(self):
        # A state in FORMED_AFTER_2011 has no census rows of its own, so any
        # district declared under it must be checked against its 2011 state.
        for state in india_census.FORMED_AFTER_2011:
            if any(state == declared for declared, _ in self.names()):
                self.assertIn(state, india_census.STATE_IN_2011)
        self.assertEqual("Andhra Pradesh", india_census.STATE_IN_2011["Telangana"])


class Subdivided(unittest.TestCase):
    def test_the_undivided_row_is_not_emitted_under_its_own_name(self):
        got = emitted()
        self.assertNotIn("Jaintia Hills", got)
        self.assertIn("East Jaintia Hills", got)
        self.assertIn("West Jaintia Hills", got)

    def test_every_field_carries_the_reason_not_just_religion(self):
        # india_language.py emits a record for these successors under the same
        # id, and a gap with no note overwrites a gap that has one. Whichever
        # file runs last, the shape has to keep the explanation.
        got = emitted()["East Jaintia Hills"]
        for field in ("population", "religion", "language"):
            with self.subTest(field=field):
                self.assertIn("undivided Jaintia Hills", got[field]["note"])

    def test_both_adapters_write_the_same_reason(self):
        units = {("17", "299"): {"name": "Jaintia Hills",
                                 "counts": {"Khasi": 376245, "Bengali": 2068}},
                 ("17", "000"): {"name": "MEGHALAYA", "counts": {"Khasi": 1431344}}}
        rows = {r["name"]: r for r in india_language.build(units, "district")}
        for field in ("religion", "language"):
            with self.subTest(field=field):
                self.assertEqual(india_census.subdivided_reason("Jaintia Hills"),
                                 rows["East Jaintia Hills"][field]["note"])


class RealDistrictsAreUntouched(unittest.TestCase):
    def test_a_district_the_census_did_enumerate_keeps_its_figures(self):
        got = emitted()["Surguja"]
        self.assertEqual(2359886, got["population"]["value"])
        shares = {row["group"]: row["count"] for row in got["religion"]}
        self.assertEqual(2126195, shares["Hindu"])
        self.assertEqual(48295, shares["Other religions"])

    def test_the_religion_groups_account_for_everyone_enumerated(self):
        # Eight columns that partition the district, including the census's own
        # residual: if the reader ever dropped one, or counted a level twice,
        # this stops matching the population it was divided by.
        for name in ("Surguja", "Thane"):
            with self.subTest(district=name):
                got = emitted()[name]
                self.assertEqual(got["population"]["value"],
                                 sum(row["count"] for row in got["religion"]))

    def test_the_census_residual_keeps_the_census_label(self):
        # 48,295 people in Surguja are inside "Other religions and persuasions"
        # and C-01 publishes nothing beneath it -- the break-up is table C-01
        # Appendix, which the Registrar General publishes for states only. The
        # group is emitted as its own row rather than folded away, so the share
        # is visible even while its contents are not.
        groups = [row["group"] for row in emitted()["Surguja"]["religion"]]
        self.assertIn("Other religions", groups)
        self.assertIn("Not stated", groups)


if __name__ == "__main__":
    unittest.main()
