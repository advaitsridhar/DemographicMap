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

import collections
import io
import unittest
from unittest import mock

from scripts.fetch_census import india_census, india_language


# Four real rows of the district extract, trimmed to the columns the reader
# reads. Jaintia Hills is one of the three districts SUBDIVIDED_SINCE_2011
# names; Surguja and Thane are predecessors the post-2011 table points at, so
# both have since lost ground; Warangal is the predecessor that has itself been
# abolished; Raigarh is the control that lost nothing.
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
    # The control the others are measured against: a district nothing was
    # carved out of, which therefore still covers the ground the census
    # counted and still carries its figures.
    {"District code": "403", "State name": "CHHATTISGARH", "District name": "Raigarh",
     "Population": "1493984", "Male": "750278", "Female": "743706",
     "Hindus": "1422986", "Muslims": "17332", "Christians": "47653", "Sikhs": "2117",
     "Buddhists": "781", "Jains": "409", "Others_Religions": "1782",
     "Religion_Not_Stated": "924", "SC": "224942", "ST": "505609"},
]

# A table small enough to reason about, declaring one district against each of
# the three shapes of predecessor: one still standing (Surguja, Thane) and one
# abolished (Warangal).
TABLE = {
    "Chhattisgarh": (("Balrampur", 2012, ("Surguja",)),),
    "Maharashtra": (("Palghar", 2014, ("Thane",)),),
    "Telangana": (("Jangaon", 2016, ("Warangal",)),),
}

# The other side of the same three facts. Every predecessor in TABLE whose name
# still sits on a shape is a district that lost ground, so it appears here --
# Warangal does not, because its name survives on no present-day shape at all
# and SUBDIVIDED_SINCE_2011 already accounts for it. The two tables are
# required to agree, which is what :func:`check_lost_territory` is for.
LOST = {
    "Chhattisgarh": (("Surguja", 31),),
    "Maharashtra": (("Thane", 44),),
}


def emitted(table=TABLE, rows=ROWS, lost=LOST):
    """The district records, with the post-2011 tables swapped for small ones."""
    with mock.patch.dict(india_census.CREATED_AFTER_2011, table, clear=True), \
            mock.patch.dict(india_census.LOST_TERRITORY_SINCE_2011, lost, clear=True):
        return {r["name"]: r for r in india_census.districts(rows)}


def refusal(table, rows=ROWS, lost=LOST):
    """The message check_new_districts refuses `table` with, or '' if it allows it."""
    with mock.patch.dict(india_census.CREATED_AFTER_2011, table, clear=True), \
            mock.patch.dict(india_census.LOST_TERRITORY_SINCE_2011, lost, clear=True):
        try:
            india_census.check_new_districts(rows)
        except SystemExit as exit_:
            return str(exit_)
    return ""


def shrink_refusal(lost, table=TABLE, rows=ROWS):
    """The message check_lost_territory refuses `lost` with, or '' if it allows it."""
    with mock.patch.dict(india_census.CREATED_AFTER_2011, table, clear=True), \
            mock.patch.dict(india_census.LOST_TERRITORY_SINCE_2011, lost, clear=True):
        try:
            india_census.check_lost_territory(rows)
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
        # The reader is told where the measurement covering this ground is --
        # and it is not the district next door, which is a fragment too.
        self.assertIn("The state total carries it", note)
        self.assertIn("only the part left after this district was carved out", note)

    def test_a_predecessor_that_is_itself_gone_is_not_offered_as_somewhere_to_look(self):
        # Warangal was split six ways and its name is on no present-day shape,
        # so pointing at "the district of that name" would send the reader to a
        # place that does not exist.
        note = emitted()["Jangaon"]["religion"]["note"]
        self.assertIn("Warangal has itself since been subdivided", note)
        self.assertNotIn("the part left after this district", note)

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
        # A state in SPLIT_STATES has no census rows of its own, so any
        # district declared under it must be checked against its 2011 state.
        for state in india_census.SPLIT_STATES:
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


# The C-01 Appendix as probe_xlsx prints it: a title row, the header, a row of
# column numbers, then three rows per community. The India block is verbatim
# from the file -- and it reconciles, which is the first evidence that the
# columns are what the header says: Rural + Urban is Total and Males + Females
# is Persons on every one of these rows, and the 7,937,734 in the parent row is
# the same figure C-01 gives for "Other religions and persuasions" nationally.
#
# The two state blocks are built to match that India block rather than taken
# from the file, because the Appendix's per-state figures are what the run is
# for and are not known here. Their shape is the file's.
APPENDIX_ROWS = [
    ["C-1 APPENDIX - 2011 DETAILS OF RELIGIOUS COMMUNITY SHOWN UNDER "
     "'OTHER RELIGIONS AND PERSUASIONS' IN MAIN TABLE C-1"],
    ["Table  Name", "State Code", "Distt. Code", "Area Name", "Religion Code",
     "Religious Community", "Total/ Rural/ Urban", "Persons", "Males", "Females"],
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
    # -- India
    ["C01APX", "00", "000", "INDIA", "700000", "Other Religions and Persuasions",
     "Total", 7937734, 3952064, 3985670],
    ["C01APX", "00", "000", "INDIA", "700000", "Other Religions and Persuasions",
     "Rural", 7199007, 3583894, 3615113],
    ["C01APX", "00", "000", "INDIA", "700000", "Other Religions and Persuasions",
     "Urban", 738727, 368170, 370557],
    ["C01APX", "00", "000", "INDIA", "701002", "Addi Bassi", "Total", 86877, 43665, 43212],
    ["C01APX", "00", "000", "INDIA", "701002", "Addi Bassi", "Rural", 76629, 38318, 38311],
    ["C01APX", "00", "000", "INDIA", "701002", "Addi Bassi", "Urban", 10248, 5347, 4901],
    ["C01APX", "00", "000", "INDIA", "701003", "Adi", "Total", 24381, 12056, 12325],
    ["C01APX", "00", "000", "INDIA", "701003", "Adi", "Rural", 21541, 10642, 10899],
    ["C01APX", "00", "000", "INDIA", "701003", "Adi", "Urban", 2840, 1414, 1426],
    # -- Arunachal Pradesh: the whole of Adi, and most of the bucket unnamed.
    # 362,553 is the state's real "Other religions and persuasions" from C-01.
    # The "State - " on the area name is the file's own: every state row
    # carries a level marker and the India row above carries none, which is
    # why a sample of the India block alone does not show it.
    ["C01APX", "12", "000", "State - ARUNACHAL PRADESH", "700000",
     "Other Religions and Persuasions", "Total", 362553, 180000, 182553],
    ["C01APX", "12", "000", "State - ARUNACHAL PRADESH", "700000",
     "Other Religions and Persuasions", "Rural", 300000, 149000, 151000],
    ["C01APX", "12", "000", "State - ARUNACHAL PRADESH", "700000",
     "Other Religions and Persuasions", "Urban", 62553, 31000, 31553],
    ["C01APX", "12", "000", "State - ARUNACHAL PRADESH", "701003", "Adi",
     "Total", 24381, 12056, 12325],
    ["C01APX", "12", "000", "State - ARUNACHAL PRADESH", "701003", "Adi",
     "Rural", 21541, 10642, 10899],
    ["C01APX", "12", "000", "State - ARUNACHAL PRADESH", "701003", "Adi",
     "Urban", 2840, 1414, 1426],
    # -- Chhattisgarh: the whole of Addi Bassi.
    ["C01APX", "22", "000", "State - CHHATTISGARH", "700000",
     "Other Religions and Persuasions", "Total", 100000, 50000, 50000],
    ["C01APX", "22", "000", "State - CHHATTISGARH", "700000",
     "Other Religions and Persuasions", "Rural", 90000, 45000, 45000],
    ["C01APX", "22", "000", "State - CHHATTISGARH", "700000",
     "Other Religions and Persuasions", "Urban", 10000, 5000, 5000],
    ["C01APX", "22", "000", "State - CHHATTISGARH", "701002", "Addi Bassi",
     "Total", 86877, 43665, 43212],
    ["C01APX", "22", "000", "State - CHHATTISGARH", "701002", "Addi Bassi",
     "Rural", 76629, 38318, 38311],
    ["C01APX", "22", "000", "State - CHHATTISGARH", "701002", "Addi Bassi",
     "Urban", 10248, 5347, 4901],
]

# Arunachal Pradesh's own C-01 columns, summed from the district extract. The
# eight add to 1,383,727, the population the state enumerated.
ARUNACHAL = collections.Counter({
    "Population": 1383727, "Male": 713912, "Female": 669815,
    "Hindus": 401876, "Muslims": 27045, "Christians": 418732, "Sikhs": 3287,
    "Buddhists": 162815, "Jains": 771, "Others_Religions": 362553,
    "Religion_Not_Stated": 6648, "SC": 6188, "ST": 951821,
})


def workbook(rows=APPENDIX_ROWS) -> bytes:
    """The fixture rows as an .xlsx, so the reader is exercised end to end."""
    import openpyxl

    book = openpyxl.Workbook()
    for row in rows:
        book.worksheets[0].append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class Appendix(unittest.TestCase):
    def read(self, rows=APPENDIX_ROWS):
        return india_census.read_appendix(workbook(rows))

    def test_the_parent_row_is_the_bucket_and_not_a_religion(self):
        # C-01 writes "Other religions and persuasions" and this table writes
        # it with capitals, so the parent is recognised by its code. Read as a
        # member it would add the whole bucket a second time.
        units = self.read()
        self.assertEqual(7937734, units["00"]["bucket"])
        self.assertNotIn("Other Religions and Persuasions", units["00"]["counts"])
        self.assertEqual({"Addi Bassi": 86877, "Adi": 24381},
                         dict(units["00"]["counts"]))

    def test_only_the_total_rows_are_read(self):
        # Rural and Urban are the same people split. Summed in, every figure
        # in the table doubles.
        self.assertEqual(24381, self.read()["12"]["counts"]["Adi"])

    def test_a_state_code_that_arrives_as_a_number_is_still_india(self):
        # The same code is text in one census workbook and a number in
        # another; read without padding, India becomes a 36th state and
        # everything is counted twice.
        rows = [list(row) for row in APPENDIX_ROWS]
        for row in rows[3:]:
            if len(row) > 4 and row[1] == "00":
                row[1], row[2] = 0, 0
        self.assertIn("00", self.read(rows))

    def test_a_moved_column_stops_the_run(self):
        rows = [list(row) for row in APPENDIX_ROWS]
        rows[1][7], rows[1][8] = "Males", "Persons"
        with self.assertRaises(SystemExit) as caught:
            self.read(rows)
        self.assertIn("not where this reader expects them", str(caught.exception))

    def test_males_and_females_must_make_persons(self):
        rows = [list(row) for row in APPENDIX_ROWS]
        rows[6][8] = 43664
        with self.assertRaises(SystemExit) as caught:
            self.read(rows)
        self.assertIn("is not 86,877 persons", str(caught.exception))

    def test_rural_and_urban_must_make_the_total(self):
        rows = [list(row) for row in APPENDIX_ROWS]
        rows[8][7] = 10249
        with self.assertRaises(SystemExit) as caught:
            self.read(rows)
        self.assertIn("is not total", str(caught.exception))

    def test_a_cell_that_is_not_a_count_names_itself(self):
        # Offices mark a suppressed cell with a dash far more often than with
        # a blank, and int("-") is a traceback that says nothing about which
        # row it came from.
        rows = [list(row) for row in APPENDIX_ROWS]
        rows[6][7] = "-"
        with self.assertRaises(SystemExit) as caught:
            self.read(rows)
        self.assertIn("Addi Bassi", str(caught.exception))
        self.assertIn("Persons column", str(caught.exception))

    def test_a_district_row_would_overturn_the_claim_we_publish(self):
        # The note on every state says no district-level figure exists. If the
        # table ever carries one, that note is false and the reader is wrong
        # about the table rather than merely incomplete.
        rows = [list(row) for row in APPENDIX_ROWS]
        for row in rows:
            if len(row) > 4 and row[3] == "State - ARUNACHAL PRADESH":
                row[2] = "001"
        with self.assertRaises(SystemExit) as caught:
            self.read(rows)
        self.assertIn("not state-level after all", str(caught.exception))


class AppendixAgainstC01(unittest.TestCase):
    BUCKETS = {"arunachal pradesh": 362553, "chhattisgarh": 100000}

    def units(self, rows=APPENDIX_ROWS):
        return india_census.read_appendix(workbook(rows))

    def test_it_agrees_with_c01(self):
        india_census.check_appendix(self.units(), self.BUCKETS)

    def test_the_india_row_must_equal_the_states_summed(self):
        # The check that catches the whole table being read twice.
        # Two people taken off Chhattisgarh's Addi Bassi, with its own Rural,
        # Urban, Males and Females adjusted to match -- so every identity
        # inside the sheet still holds and only the cross-total is wrong. That
        # is the shape of the failure this check exists for: a table read at
        # two levels stays internally consistent.
        edits = {"Total": (86875, 43663, 43212), "Rural": (76629, 38318, 38311),
                 "Urban": (10246, 5345, 4901)}
        rows = [list(row) for row in APPENDIX_ROWS]
        for row in rows:
            if len(row) > 4 and row[3] == "State - CHHATTISGARH" and row[4] == "701002":
                row[7], row[8], row[9] = edits[row[6]]
        with self.assertRaises(SystemExit) as caught:
            india_census.check_appendix(self.units(rows), self.BUCKETS)
        self.assertIn("India row says 86,877", str(caught.exception))

    def test_a_bucket_c01_does_not_confirm_stops_the_run(self):
        buckets = dict(self.BUCKETS, **{"arunachal pradesh": 362554})
        with self.assertRaises(SystemExit) as caught:
            india_census.check_appendix(self.units(), buckets)
        self.assertIn("362,553 here and 362,554 in C-01", str(caught.exception))

    def test_named_religions_may_not_exceed_their_own_bucket(self):
        rows = [list(row) for row in APPENDIX_ROWS]
        for row in rows:
            if len(row) > 4 and row[3] == "State - ARUNACHAL PRADESH" and row[4] == "700000":
                row[7] = {"Total": 20000, "Rural": 18000, "Urban": 2000}[row[6]]
                row[8] = row[9] = row[7] // 2
        buckets = dict(self.BUCKETS, **{"arunachal pradesh": 20000})
        with self.assertRaises(SystemExit) as caught:
            india_census.check_appendix(self.units(rows), buckets)
        self.assertIn("more than the 20,000", str(caught.exception))

    def test_a_state_name_the_two_tables_spell_differently_still_matches(self):
        # Three disagreements between two tables of the same census: a level
        # marker on one side and not the other, an ampersand, and a state
        # renamed between the tables being written.
        self.assertEqual(india_census.state_key("JAMMU AND KASHMIR"),
                         india_census.state_key("State - JAMMU & KASHMIR"))
        self.assertEqual(india_census.state_key("ORISSA"),
                         india_census.state_key("State - ODISHA"))
        self.assertEqual(india_census.state_key("NCT OF DELHI"),
                         india_census.state_key("State - NCT OF DELHI"))

    def test_a_dash_inside_a_real_name_is_not_a_level_marker(self):
        # "Janjgir - Champa" and "Baloda Bazar - Bhatapara" are districts, so
        # stripping whatever precedes the first " - " would turn one of them
        # into Champa. Only the census's own level words are stripped.
        self.assertEqual(india_census.state_key("Janjgir - Champa"),
                         india_census.state_key("District - Janjgir - Champa"))
        self.assertIn("janjgir", india_census.state_key("Janjgir - Champa"))

    def test_an_unmatched_state_says_what_it_was_compared_against(self):
        # The first version of this refusal said only "no state of that name",
        # and the cause -- a level marker on every row of one table and none of
        # the other -- had to be spotted by eye. The two keys side by side are
        # what makes it readable from the log.
        with self.assertRaises(SystemExit) as caught:
            india_census.check_appendix(self.units(), {"kerala": 1})
        message = str(caught.exception)
        self.assertIn("normalises to 'arunachal pradesh'", message)
        self.assertIn("'kerala'", message)


class ResidualDetail(unittest.TestCase):
    """Substituting the Appendix's religions for C-01's one residual row."""

    def unit(self, counts, bucket=362553):
        return {"name": "State - ARUNACHAL PRADESH", "bucket": bucket,
                "counts": collections.Counter(counts)}

    def test_the_groups_still_add_to_the_population(self):
        got = india_census.religion_with_detail(
            ARUNACHAL, self.unit({"Doni Polo / Sidonyi Polo": 324742, "Nocte": 5000}))
        self.assertEqual(ARUNACHAL["Population"],
                         sum(row["count"] for row in got))

    def test_the_residual_is_replaced_rather_than_joined(self):
        got = {row["group"]: row["count"] for row in india_census.religion_with_detail(
            ARUNACHAL, self.unit({"Doni Polo / Sidonyi Polo": 324742}))}
        self.assertNotIn("Other religions", got)
        self.assertEqual(324742, got["Doni Polo / Sidonyi Polo"])
        # What the Appendix does not name is still shown, never dropped.
        self.assertEqual(362553 - 324742, got[india_census.ORP_REMAINDER])

    def test_the_six_named_religions_are_untouched(self):
        got = {row["group"]: row["count"] for row in india_census.religion_with_detail(
            ARUNACHAL, self.unit({"Doni Polo / Sidonyi Polo": 324742}))}
        self.assertEqual(418732, got["Christian"])
        self.assertEqual(162815, got["Buddhist"])
        self.assertEqual(6648, got["Not stated"])

    def test_the_tail_is_summed_and_not_dropped(self):
        tail = {f"Faith {n}": 10 for n in range(40)}
        got = {row["group"]: row["count"] for row in india_census.religion_with_detail(
            ARUNACHAL, self.unit(dict(tail, **{"Doni Polo / Sidonyi Polo": 324742})))}
        self.assertNotIn("Faith 0", got)
        self.assertEqual(362553 - 324742, got[india_census.ORP_REMAINDER])

    def test_a_bucket_that_does_not_match_c01_refuses(self):
        with self.assertRaises(SystemExit) as caught:
            india_census.religion_with_detail(
                ARUNACHAL, self.unit({"Doni Polo / Sidonyi Polo": 1}, bucket=2))
        self.assertIn("against an enumerated 1,383,727", str(caught.exception))

    def test_the_note_says_it_is_a_state_figure_with_no_district_below_it(self):
        counts = collections.Counter({"Doni Polo / Sidonyi Polo": 324742,
                                      "Nocte": 500, "Aka": 300})
        kept = india_census.named_residual(counts, 362553, ARUNACHAL["Population"])
        note = india_census.residual_note(kept, counts, 362553,
                                          ARUNACHAL["Population"])
        self.assertIn("states only", note)
        self.assertIn("no district-level figure", note)
        self.assertIn("362,553", note)


class TheTreePlacesWhatTheAppendixSurfaces(unittest.TestCase):
    """A religion the map draws and the tree does not place gets no colour.

    Surfacing Donyi-Polo and leaving it unclassified would trade one honest
    blank for another, so the labels the Appendix puts on the map are checked
    against the tree here rather than found in the shipped site.
    """

    def tiers(self, labels):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import canonical_groups  # noqa: PLC0415
        import group_tree        # noqa: PLC0415

        rows = [{"group": label, "pct": 1.0} for label in labels]
        placed = group_tree.parents("religion")
        return {name: placed.get(name)
                for name in canonical_groups.canonicalise(rows, "religion")}

    def test_the_adivasi_religions_land_under_folk_and_traditional(self):
        # The census's own spellings, including the two it writes as a
        # slash-joined pair rather than as a name.
        got = self.tiers(["Doni Polo / Sidonyi Polo", "Sarna", "Sanamahi",
                          "Khasi", "Niamtre", "Gond / Gondi", "Nocte"])
        self.assertIn("Donyi-Polo", got)
        self.assertIn("Gondi", got)
        for name, band in got.items():
            with self.subTest(religion=name):
                self.assertEqual("Folk and traditional religions", band)

    def test_the_unnamed_part_of_the_residual_is_placed_apart_from_them(self):
        # It is what is left of C-01's bucket, not a religion, so it belongs
        # where the bucket belongs and not with the faiths taken out of it.
        got = self.tiers([india_census.ORP_REMAINDER])
        self.assertEqual({india_census.ORP_REMAINDER: "Other and new religions"},
                         got)


# The 23 districts of undivided Andhra Pradesh, as the extract prints them.
# 532-541 are the ten that became Telangana in 2014 and 542-554 the thirteen
# that stayed, and what makes this a test rather than a restatement is that the
# two sums are checked against figures published outside this repository:
# 35,193,978 and 49,386,799, which add to the 84,580,777 the Registrar General
# published for the undivided state.
ANDHRA = [
    {"District code": "532", "District name": "Adilabad",
     "Population": "2741239", "Male": "1369597", "Female": "1371642",
     "Hindus": "2399901", "Muslims": "275970", "Christians": "15422", "Sikhs": "1377",
     "Buddhists": "25510", "Jains": "617", "Others_Religions": "322",
     "Religion_Not_Stated": "22120"},
    {"District code": "533", "District name": "Nizamabad",
     "Population": "2551335", "Male": "1250641", "Female": "1300694",
     "Hindus": "2123426", "Muslims": "391596", "Christians": "19653", "Sikhs": "2357",
     "Buddhists": "1847", "Jains": "542", "Others_Religions": "146",
     "Religion_Not_Stated": "11768"},
    {"District code": "534", "District name": "Karimnagar",
     "Population": "3776269", "Male": "1880800", "Female": "1895469",
     "Hindus": "3491139", "Muslims": "244723", "Christians": "24979", "Sikhs": "2086",
     "Buddhists": "332", "Jains": "312", "Others_Religions": "115",
     "Religion_Not_Stated": "12583"},
    {"District code": "535", "District name": "Medak",
     "Population": "3033288", "Male": "1523030", "Female": "1510258",
     "Hindus": "2637313", "Muslims": "342449", "Christians": "34301", "Sikhs": "1309",
     "Buddhists": "554", "Jains": "457", "Others_Religions": "217",
     "Religion_Not_Stated": "16688"},
    {"District code": "536", "District name": "Hyderabad",
     "Population": "3943323", "Male": "2018575", "Female": "1924748",
     "Hindus": "2046051", "Muslims": "1713405", "Christians": "87522", "Sikhs": "11446",
     "Buddhists": "1268", "Jains": "19560", "Others_Religions": "1929",
     "Religion_Not_Stated": "62142"},
    {"District code": "537", "District name": "Rangareddy",
     "Population": "5296741", "Male": "2701008", "Female": "2595733",
     "Hindus": "4458858", "Muslims": "617518", "Christians": "144037", "Sikhs": "8062",
     "Buddhists": "2041", "Jains": "3536", "Others_Religions": "1629",
     "Religion_Not_Stated": "61060"},
    {"District code": "538", "District name": "Mahbubnagar",
     "Population": "4053028", "Male": "2050386", "Female": "2002642",
     "Hindus": "3673456", "Muslims": "334172", "Christians": "21345", "Sikhs": "658",
     "Buddhists": "290", "Jains": "388", "Others_Religions": "267",
     "Religion_Not_Stated": "22452"},
    {"District code": "539", "District name": "Nalgonda",
     "Population": "3488809", "Male": "1759772", "Female": "1729037",
     "Hindus": "3249231", "Muslims": "188646", "Christians": "35025", "Sikhs": "937",
     "Buddhists": "241", "Jains": "250", "Others_Religions": "132",
     "Religion_Not_Stated": "14347"},
    {"District code": "540", "District name": "Warangal",
     "Population": "3512576", "Male": "1759281", "Female": "1753295",
     "Hindus": "3273755", "Muslims": "197333", "Christians": "31377", "Sikhs": "1453",
     "Buddhists": "253", "Jains": "569", "Others_Religions": "126",
     "Religion_Not_Stated": "7710"},
    {"District code": "541", "District name": "Khammam",
     "Population": "2797370", "Male": "1390988", "Female": "1406382",
     "Hindus": "2595321", "Muslims": "158887", "Christians": "33463", "Sikhs": "655",
     "Buddhists": "217", "Jains": "459", "Others_Religions": "539",
     "Religion_Not_Stated": "7829"},
    {"District code": "542", "District name": "Srikakulam",
     "Population": "2703114", "Male": "1341738", "Female": "1361376",
     "Hindus": "2666950", "Muslims": "9025", "Christians": "18879", "Sikhs": "193",
     "Buddhists": "77", "Jains": "160", "Others_Religions": "106",
     "Religion_Not_Stated": "7724"},
    {"District code": "543", "District name": "Vizianagaram",
     "Population": "2344474", "Male": "1161477", "Female": "1182997",
     "Hindus": "2299129", "Muslims": "16423", "Christians": "17853", "Sikhs": "380",
     "Buddhists": "114", "Jains": "815", "Others_Religions": "183",
     "Religion_Not_Stated": "9577"},
    {"District code": "544", "District name": "Visakhapatnam",
     "Population": "4290589", "Male": "2138910", "Female": "2151679",
     "Hindus": "4105320", "Muslims": "86330", "Christians": "77607", "Sikhs": "2301",
     "Buddhists": "850", "Jains": "2316", "Others_Religions": "286",
     "Religion_Not_Stated": "15579"},
    {"District code": "545", "District name": "East Godavari",
     "Population": "5154296", "Male": "2569688", "Female": "2584608",
     "Hindus": "4983330", "Muslims": "77777", "Christians": "77825", "Sikhs": "738",
     "Buddhists": "413", "Jains": "4149", "Others_Religions": "403",
     "Religion_Not_Stated": "9661"},
    {"District code": "546", "District name": "West Godavari",
     "Population": "3936966", "Male": "1964918", "Female": "1972048",
     "Hindus": "3733191", "Muslims": "86142", "Christians": "109120", "Sikhs": "288",
     "Buddhists": "209", "Jains": "1578", "Others_Religions": "211",
     "Religion_Not_Stated": "6227"},
    {"District code": "547", "District name": "Krishna",
     "Population": "4517398", "Male": "2267375", "Female": "2250023",
     "Hindus": "4023678", "Muslims": "307043", "Christians": "145598", "Sikhs": "1393",
     "Buddhists": "863", "Jains": "6320", "Others_Religions": "906",
     "Religion_Not_Stated": "31597"},
    {"District code": "548", "District name": "Guntur",
     "Population": "4887813", "Male": "2440521", "Female": "2447292",
     "Hindus": "4217597", "Muslims": "559770", "Christians": "89763", "Sikhs": "764",
     "Buddhists": "323", "Jains": "3282", "Others_Religions": "332",
     "Religion_Not_Stated": "15982"},
    {"District code": "549", "District name": "Prakasam",
     "Population": "3397448", "Male": "1714764", "Female": "1682684",
     "Hindus": "3150195", "Muslims": "220654", "Christians": "18775", "Sikhs": "266",
     "Buddhists": "97", "Jains": "204", "Others_Religions": "206",
     "Religion_Not_Stated": "7051"},
    {"District code": "550", "District name": "Sri Potti Sriramulu Nellore",
     "Population": "2963557", "Male": "1492974", "Female": "1470583",
     "Hindus": "2639737", "Muslims": "288378", "Christians": "26202", "Sikhs": "678",
     "Buddhists": "239", "Jains": "2610", "Others_Religions": "146",
     "Religion_Not_Stated": "5567"},
    {"District code": "551", "District name": "Y.S.R.",
     "Population": "2882469", "Male": "1451777", "Female": "1430692",
     "Hindus": "2391231", "Muslims": "454108", "Christians": "23281", "Sikhs": "367",
     "Buddhists": "105", "Jains": "751", "Others_Religions": "245",
     "Religion_Not_Stated": "12381"},
    {"District code": "552", "District name": "Kurnool",
     "Population": "4053463", "Male": "2039227", "Female": "2014236",
     "Hindus": "3328380", "Muslims": "670737", "Christians": "33165", "Sikhs": "737",
     "Buddhists": "255", "Jains": "2235", "Others_Religions": "434",
     "Religion_Not_Stated": "17520"},
    {"District code": "553", "District name": "Anantapur",
     "Population": "4081148", "Male": "2064495", "Female": "2016653",
     "Hindus": "3599372", "Muslims": "443456", "Christians": "20463", "Sikhs": "932",
     "Buddhists": "341", "Jains": "1417", "Others_Religions": "309",
     "Religion_Not_Stated": "14858"},
    {"District code": "554", "District name": "Chittoor",
     "Population": "4174064", "Male": "2090204", "Female": "2083860",
     "Hindus": "3737588", "Muslims": "397870", "Christians": "24129", "Sikhs": "867",
     "Buddhists": "253", "Jains": "1322", "Others_Religions": "358",
     "Religion_Not_Stated": "11677"},
]
ANDHRA = [dict(row, **{"State name": "ANDHRA PRADESH"}) for row in ANDHRA]

TELANGANA = india_census.SPLIT_STATES["Telangana"]


def andhra_states(rows=ANDHRA, splits=None):
    """The state records the extract's Andhra Pradesh rows produce, by name."""
    splits = {"Telangana": TELANGANA} if splits is None else splits
    with mock.patch.dict(india_census.SPLIT_STATES, splits, clear=True):
        return {r["name"]: r for r in india_census.states(rows)}


class TheStateSplit(unittest.TestCase):
    """Telangana's figure is nobody's publication, so every digit is checked."""

    def test_the_ten_districts_reconcile_to_telanganas_published_total(self):
        got = andhra_states()["Telangana"]
        self.assertEqual(35_193_978, got["population"]["value"])
        self.assertEqual(35_193_978,
                         sum(row["count"] for row in got["religion"]))

    def test_the_thirteen_that_stayed_reconcile_to_andhra_pradeshs(self):
        got = andhra_states()["Andhra Pradesh"]
        self.assertEqual(49_386_799, got["population"]["value"])
        self.assertEqual(49_386_799,
                         sum(row["count"] for row in got["religion"]))

    def test_the_two_halves_add_back_to_the_undivided_state(self):
        # The control that needs no table: whatever the split does, it must not
        # lose or duplicate a person, and 84,580,777 is what the Registrar
        # General published for Andhra Pradesh before the state was divided.
        got = andhra_states()
        self.assertEqual(84_580_777, got["Telangana"]["population"]["value"]
                         + got["Andhra Pradesh"]["population"]["value"])

    def test_the_residual_is_not_the_undivided_state(self):
        # The bug this replaced: 88.5% Hindu and 84.6 million people, which is
        # undivided Andhra Pradesh, sitting on the shape of the residual one.
        got = andhra_states()["Andhra Pradesh"]
        shares = {row["group"]: row["pct"] for row in got["religion"]}
        self.assertAlmostEqual(90.9, shares["Hindu"], places=1)
        self.assertAlmostEqual(7.3, shares["Muslim"], places=1)

    def test_telangana_is_more_muslim_than_what_was_left(self):
        # Not a rounding check: the split is worth making because the two
        # halves are genuinely different places, and the undivided figure
        # described neither.
        got = andhra_states()
        muslim = {name: next(r["pct"] for r in got[name]["religion"]
                             if r["group"] == "Muslim")
                  for name in ("Telangana", "Andhra Pradesh")}
        self.assertGreater(muslim["Telangana"], muslim["Andhra Pradesh"] + 4)

    def test_the_note_says_it_was_summed_and_from_which_districts(self):
        note = andhra_states()["Telangana"]["population_note"]
        self.assertIn("Summed from the 10 districts", note)
        for district in TELANGANA.districts:
            self.assertIn(district, note)
        # And what the sum does not cover, which is the whole reason the
        # published figure for the present-day state is a different number.
        self.assertIn("35,003,674", note)
        self.assertIn("190,304", note)

    def test_a_district_missing_from_the_extract_stops_the_run(self):
        short = [row for row in ANDHRA if row["District name"] != "Khammam"]
        with self.assertRaises(SystemExit) as ctx:
            andhra_states(short)
        self.assertIn("no district called 'Khammam'", str(ctx.exception))

    def test_a_sum_that_misses_the_published_total_stops_the_run(self):
        rows = [dict(row) for row in ANDHRA]
        rows[0]["Population"] = "2741240"        # one person too many
        with self.assertRaises(SystemExit) as ctx:
            andhra_states(rows)
        self.assertIn("against a published 35,193,978", str(ctx.exception))

    def test_a_wrong_district_code_stops_the_run(self):
        # Name and code are two independent handles on the same row, and the
        # religion extract keys on one while the mother-tongue workbooks key on
        # the other. A split right in one table and wrong in the other is what
        # this catches.
        wrong = TELANGANA._replace(codes=(532, 533, 534, 535, 536,
                                          537, 538, 539, 540, 999))
        with self.assertRaises(SystemExit) as ctx:
            andhra_states(splits={"Telangana": wrong})
        self.assertIn("SPLIT_STATES", str(ctx.exception))

    def test_two_states_may_not_claim_one_district(self):
        rival = TELANGANA._replace(districts=("Khammam",), codes=(541,))
        with self.assertRaises(SystemExit) as ctx:
            andhra_states(splits={"Telangana": TELANGANA, "Nowhere": rival})
        self.assertIn("claimed by both", str(ctx.exception))

    def test_a_state_split_from_a_state_it_is_not_split_from(self):
        wrong = TELANGANA._replace(parent="Karnataka")
        with self.assertRaises(SystemExit) as ctx:
            andhra_states(splits={"Telangana": wrong})
        self.assertIn("STATE_IN_2011", str(ctx.exception))


class DistrictsThatLostTheirGround(unittest.TestCase):
    """The other half of the same fact, and the one that was invisible."""

    def test_a_shrunken_district_does_not_carry_the_undivided_figure(self):
        got = emitted()["Surguja"]
        for field in ("population", "religion", "language", "sex_ratio",
                      "scheduled_groups"):
            with self.subTest(field=field):
                self.assertNotIsInstance(got[field], list)
                self.assertIsNone(got[field].get("value"))
                self.assertEqual(india_census.NOT_AVAILABLE,
                                 got[field]["status"])

    def test_the_gap_names_what_took_the_ground_and_how_much(self):
        note = emitted()["Surguja"]["religion"]["note"]
        self.assertIn("Balrampur", note)
        self.assertIn("2012", note)
        self.assertIn("31%", note)
        self.assertIn("The state total does.", note)

    def test_a_district_that_kept_more_than_half_makes_no_claim_about_people(self):
        # Area is what is measured and people are what is at stake, and the two
        # do not track each other. The sentence about where the people live is
        # only written where the area measurement alone establishes it.
        self.assertIn("Most of the people",
                      emitted()["Surguja"]["religion"]["note"])
        self.assertNotIn("Most of the people",
                         emitted(lost={"Maharashtra": (("Thane", 84),)},
                                 table={"Maharashtra": TABLE["Maharashtra"]},
                                 )["Thane"]["religion"]["note"])

    def test_a_district_that_lost_nothing_is_untouched(self):
        self.assertEqual(1493984, emitted()["Raigarh"]["population"]["value"])

    def test_hyderabad_keeps_its_figures(self):
        # The one Telangana district the 2016 reorganisation left alone: no
        # entry in CREATED_AFTER_2011 names it as a predecessor, so nothing was
        # carved out of it and its shape still covers what the census counted.
        carved = {p for entries in india_census.CREATED_AFTER_2011.values()
                  for _, _, preds in entries for p in preds}
        self.assertNotIn("Hyderabad", carved)
        self.assertNotIn(
            "Hyderabad",
            [name for name, _ in
             india_census.LOST_TERRITORY_SINCE_2011.get("Telangana", ())])

    def test_the_eight_telangana_districts_that_were_cut_down(self):
        # The nine Telangana shapes that carried 2011 figures, settled one by
        # one: eight are fragments of the district whose figure they wore, and
        # Hyderabad is not. Named here rather than counted, because the count
        # is the same whichever eight they are.
        self.assertEqual(
            {"Adilabad", "Karimnagar", "Khammam", "Mahbubnagar", "Medak",
             "Nalgonda", "Nizamabad", "Rangareddy"},
            {name for name, _
             in india_census.LOST_TERRITORY_SINCE_2011["Telangana"]})

    def test_every_predecessor_still_standing_is_measured(self):
        # The real tables, against each other. A district carved out of X
        # without X being measured here leaves X wearing the undivided figure,
        # which is the bug and is invisible on the map.
        message = shrink_refusal({"Chhattisgarh": (("Surguja", 31),)})
        self.assertIn("Maharashtra / Thane", message)
        self.assertIn("would keep the undivided district's figure", message)

    def test_measuring_a_district_nothing_was_carved_from(self):
        message = shrink_refusal(dict(LOST, Chhattisgarh=(("Surguja", 31),
                                                          ("Raigarh", 70))))
        self.assertIn("no district in CREATED_AFTER_2011 was carved out of it",
                      message)

    def test_a_district_the_census_never_enumerated(self):
        message = shrink_refusal(dict(LOST, Chhattisgarh=(("Surgooja", 31),)))
        self.assertIn("the census enumerated no district of that name", message)

    def test_a_share_that_is_not_a_share(self):
        message = shrink_refusal(dict(LOST, Maharashtra=(("Thane", 100),)))
        self.assertIn("is not a share of a district that lost some", message)

    def test_the_real_table_agrees_with_the_real_post_2011_table(self):
        # No fixtures: the two shipped tables, checked against each other and
        # against the census's own district list would need the extract, so
        # this checks the half that needs no network.
        declared = {(state, name)
                    for state, entries
                    in india_census.LOST_TERRITORY_SINCE_2011.items()
                    for name, _ in entries}
        derived = {(state, predecessor)
                   for state, entries in india_census.CREATED_AFTER_2011.items()
                   for _, _, predecessors in entries
                   for predecessor in predecessors
                   if predecessor.casefold()
                   not in india_census.SUBDIVIDED_SINCE_2011}
        self.assertEqual(derived, declared)


class RealDistrictsAreUntouched(unittest.TestCase):
    def test_a_district_the_census_did_enumerate_keeps_its_figures(self):
        got = emitted()["Raigarh"]
        self.assertEqual(1493984, got["population"]["value"])
        shares = {row["group"]: row["count"] for row in got["religion"]}
        self.assertEqual(1422986, shares["Hindu"])
        self.assertEqual(1782, shares["Other religions"])

    def test_the_religion_groups_account_for_everyone_enumerated(self):
        # Eight columns that partition the district, including the census's own
        # residual: if the reader ever dropped one, or counted a level twice,
        # this stops matching the population it was divided by.
        for name in ("Raigarh",):
            with self.subTest(district=name):
                got = emitted()[name]
                self.assertEqual(got["population"]["value"],
                                 sum(row["count"] for row in got["religion"]))

    def test_the_census_residual_keeps_the_census_label(self):
        # 1,782 people in Raigarh are inside "Other religions and persuasions"
        # and C-01 publishes nothing beneath it -- the break-up is table C-01
        # Appendix, which the Registrar General publishes for states only. The
        # group is emitted as its own row rather than folded away, so the share
        # is visible even while its contents are not.
        groups = [row["group"] for row in emitted()["Raigarh"]["religion"]]
        self.assertIn("Other religions", groups)
        self.assertIn("Not stated", groups)


if __name__ == "__main__":
    unittest.main()
