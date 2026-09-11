"""Census areas that share one boundary shape, summed into it.

Two real cases. Every figure and every area name here is the adapter's own
output for them -- ``data/processed/pakistan_language.json`` and
``data/processed/ethiopia_region.json``, which is what the reader printed when
it last ran against the workbooks:

* **Karachi.** The 2017 census counts six districts; geoBoundaries draws one
  shape. All six reached no shape, so Karachi -- 16.0 million people, the
  largest second-level language gap left in a country otherwise 114 districts
  full -- carried nothing.
* **Addis Ababa.** The 2007 census counts ten sub-cities; geoBoundaries draws
  one second-order shape inside the region, labelled "Region 14". The ten were
  declared as having no shape, which left that one empty.

Addis Ababa is also the control. Its ten sub-cities come to 2,739,551 against
a region row of 2,739,551 -- the source's own arithmetic saying these ten are
all of it -- so the assembly is asserted against a figure this project did not
compute.

**Why these tests go through ``read()`` and not straight into ``combine()``.**
The first version of them did the latter, handing ``combine()`` a mapping this
file had built, whose area names this file had chosen. It passed, and the
adapter then merged nothing in either country on the runner: the workbooks
print "KARACHI CENTRAL DISTRICT" where the config says "Karachi Central
District", and a test that writes both sides itself cannot see a disagreement
between them. So the fixture is now a sheet, every test reads it the way a run
reads it, and the sheet is read in both spellings -- see ``CASES``.

The workbooks themselves are not in the repository (they are fetched from HDX
at run time). The geography column names below are quoted from ``uscb``'s own
``GEOGRAPHY`` set and the group labels are the ones the adapter publishes; the
group columns' identifiers are the one thing reconstructed, and the one thing
nothing depends on, because ``groups()`` takes the label from the second header
row rather than from the name. Ethiopia's religion sheet is really reported by
sex and its fixture here is not: ``check_sexes`` is a different guard with its
own reason, and splitting these figures by sex to satisfy it would mean
inventing numbers.
"""

import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import uscb  # noqa: E402


# The two spellings a sheet has been seen in. Pakistan's Table 11 prints its
# areas in capitals -- the run's own log names "ASTORE DISTRICT, AZAD KASHMIR,
# BAGH DISTRICT" among the areas it found -- and the declarations are written
# the way `record()` publishes them, which is `str.title()` of that. Both are
# read here because which case a given workbook uses is not something this
# project should have to know, and the run that did know produced a silent
# no-op.
CASES = {"as the sheet prints it": str.upper,
         "as the record spells it": lambda text: text}


# Table 11, population by mother tongue, for the six districts of Karachi,
# for Badin -- a district of Sindh that is not part of it -- and for Sindh's
# own row, which is what the assembly is checked against.
LANGUAGES = ("Urdu", "Punjabi", "Sindhi", "Pushto", "Balochi", "Kashmiri",
             "Sareiki", "Hindko", "Brahvi", "Other language")

KARACHI = {
    "Karachi Central District":
        (2102769, 195162, 76396, 164192, 25065, 8199, 161746, 41911, 7723, 188219),
    "Karachi East District":
        (1078474, 382224, 332204, 400048, 67203, 16288, 241023, 94570, 10575, 252706),
    "Karachi South District":
        (453340, 195832, 279310, 176071, 188842, 8016, 65938, 89819, 10365, 301697),
    "Karachi West District":
        (1315095, 364846, 268821, 1158292, 188896, 14640, 149424, 230253, 39238, 177560),
    "Korangi District":
        (1580946, 349176, 149407, 134743, 21537, 8743, 103697, 91521, 3882, 133904),
    "Malir District":
        (248518, 232396, 603739, 372665, 157421, 7898, 76203, 131465, 24337, 69704),
}
BADIN = (14982, 62221, 1698882, 5792, 1908, 124, 8997, 5070, 4093, 2889)
SINDH = (8707714, 2542913, 29476764, 2613790, 956516, 69836, 1067751, 753736,
         350014, 1315476)

# The 2007 census's religion sheet for Addis Ababa's ten sub-cities, and the
# region's own printed row. Six groups rather than the language sheet's ninety,
# because the merge does not care which field it is folding and a fixture that
# fits on a screen can be read.
RELIGIONS = ("Orthodox", "Protestant", "Catholic", "Islamic", "Traditional",
             "Other religion")

ADDIS = {
    "Addis Ketema": (160487, 14867, 580, 78104, 117, 1217),
    "Akaki Kaliti": (147271, 11623, 339, 20074, 199, 1764),
    "Arada": (166559, 10685, 1536, 30824, 68, 1829),
    "Bole": (229904, 29160, 2632, 43235, 154, 3910),
    "Gulele": (218484, 18436, 960, 28050, 103, 1591),
    "Kirkos": (179898, 15056, 1855, 22339, 93, 1993),
    "Kolfe Keranyo": (260696, 44609, 1904, 118661, 219, 2806),
    "Lideta": (151923, 12000, 779, 35467, 88, 1456),
    "Nefas Silk Lafto": (237376, 30968, 1428, 43689, 168, 2654),
    "Yeka": (292847, 25503, 1189, 23582, 168, 3375),
}
ADDIS_REGION = (2045445, 212907, 13202, 444025, 1377, 22595)

LANGUAGE = uscb.Topic("Mother Tongue", "language", prefix="LNG_")
RELIGION = uscb.Topic("Religion", "religion")


class Book:
    """Just enough of an openpyxl workbook for ``sheet_rows()``."""

    def __init__(self, name: str, rows: list[list]):
        self.sheetnames = [name]
        self._rows = rows

    def __getitem__(self, _name):
        rows = self._rows

        class Sheet:
            @staticmethod
            def iter_rows(values_only=True):
                return iter(rows)
        return Sheet()


def pakistan_sheet(case=str.upper, province: str = "Sindh") -> Book:
    """Table 11 as the workbook lays it out: province at level 1, districts
    at level 3, with the divisions at level 2 that this map does not read."""
    names = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM3_NAME", "ADM_LEVEL"]
    aliases = ["", "", "", "", ""]
    for index, label in enumerate(LANGUAGES):
        names.append(f"LNG_G{index:02d}")
        aliases.append(label)
    names.append("LNG_TOTAL")
    aliases.append("Total population")
    rows = [names, aliases]

    rows.append([case(province), case(province), "", "", 1,
                 *SINDH, sum(SINDH)])
    for name, figures in KARACHI.items():
        rows.append([case(name), case(province), case("Karachi Division"),
                     case(name), 3, *figures, sum(figures)])
    rows.append([case("Badin District"), case(province),
                 case("Hyderabad Division"), case("Badin District"), 3,
                 *BADIN, sum(BADIN)])
    return Book("Mother Tongue", rows)


def ethiopia_sheet(case=str.upper) -> Book:
    """The religion sheet: region at level 1, sub-cities at level 2, and no
    published denominator -- Ethiopia's workbook has no such column."""
    names = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL"]
    aliases = ["", "", "", ""]
    for index, label in enumerate(RELIGIONS):
        names.append(f"RLG_G{index:02d}")
        aliases.append(label)
    rows = [names, aliases]
    region = "Ādīs Ābeba"
    rows.append([case(region), case(region), "", 1, *ADDIS_REGION])
    for name, figures in ADDIS.items():
        rows.append([case(name), case(region), case(name), 2, *figures])
    return Book("Religion", rows)


def read_and_combine(book, country, topic):
    found = uscb.read(book, country, topic)
    uscb.combine(country, topic, found)
    return found


class Karachi(unittest.TestCase):
    """Six districts, one shape, read off the sheet in either spelling."""

    def test_the_six_become_one_area(self):
        for label, case in CASES.items():
            with self.subTest(label):
                found = read_and_combine(pakistan_sheet(case),
                                         uscb.PAKISTAN, LANGUAGE)
                self.assertIn(("Sindh", "Karachi"), found,
                              "no assembled Karachi; the declaration reached "
                              "none of the sheet's areas")
                karachi = found[("Sindh", "Karachi")]
                self.assertEqual(karachi["assembled"], tuple(KARACHI))
                self.assertEqual(karachi["level"], 3)
                self.assertEqual(karachi["summed"], 16024894)
                self.assertEqual(karachi["published"], 16024894)

    def test_every_language_adds_up_and_none_is_invented(self):
        found = read_and_combine(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        karachi = found[("Sindh", "Karachi")]
        self.assertEqual(sorted(karachi["counts"]), sorted(LANGUAGES))
        for index, label in enumerate(LANGUAGES):
            self.assertEqual(karachi["counts"][label],
                             sum(f[index] for f in KARACHI.values()), label)

    def test_the_parts_do_not_survive_the_fold(self):
        found = read_and_combine(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        # Folded, because an area the fold did not touch keeps the sheet's own
        # spelling and only the assembled one carries the declaration's.
        left = sorted(uscb.spelling(uscb.PAKISTAN, *key)[1] for key in found)
        self.assertEqual(left, ["Badin District", "Karachi", "Sindh"],
                         "a part that has been summed must not also remain "
                         "as an area of its own")

    def test_the_shares_sum_to_a_hundred(self):
        found = read_and_combine(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        row = found[("Sindh", "Karachi")]
        published = uscb.shares(row["counts"], total=row["published"])
        self.assertAlmostEqual(sum(g["pct"] for g in published), 100.0,
                               delta=0.15)
        self.assertEqual(published[0]["group"], "Urdu")
        self.assertEqual(published[0]["count"], 6779142)

    def test_the_folded_sheet_still_reconciles(self):
        found = read_and_combine(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        uscb.check_total(uscb.PAKISTAN, LANGUAGE, found)     # no SystemExit


class AddisAbaba(unittest.TestCase):
    """Ten sub-cities, one shape, and the region row that proves the ten."""

    def test_the_ten_become_one_area(self):
        for label, case in CASES.items():
            with self.subTest(label):
                found = read_and_combine(ethiopia_sheet(case),
                                         uscb.ETHIOPIA, RELIGION)
                self.assertIn(("Ādīs Ābeba", "Ādīs Ābeba"), found,
                              "no assembled Addis Ababa; the declaration "
                              "reached none of the sheet's areas")
                assembled = found[("Ādīs Ābeba", "Ādīs Ābeba")]
                self.assertEqual(assembled["level"], 2,
                                 "the assembly stays at the level of its parts")
                self.assertEqual(assembled["summed"], 2739551.0)

    def test_the_assembly_equals_the_region_the_source_prints(self):
        found = read_and_combine(ethiopia_sheet(), uscb.ETHIOPIA, RELIGION)
        assembled = found[("Ādīs Ābeba", "Ādīs Ābeba")]
        region = next(row for key, row in found.items()
                      if row["level"] == 1)
        self.assertEqual(assembled["counts"], region["counts"])
        self.assertIsNone(assembled["published"],
                          "Ethiopia's sheet publishes no denominator, and a "
                          "denominator must not be invented from the parts")

    def test_no_sub_city_is_left_as_a_record_of_its_own(self):
        """The regression the runner found: sub-cities out of `no_shape` and
        into nothing, matching no shape with nothing saying why."""
        found = read_and_combine(ethiopia_sheet(), uscb.ETHIOPIA, RELIGION)
        for sub in ADDIS:
            self.assertNotIn(("Ādīs Ābeba", sub), found, sub)
        self.assertEqual(len(found), 2, sorted(found))


class Refusals(unittest.TestCase):
    """Every one of these is a way for a wrong merge to look like a right one."""

    def test_a_declaration_that_matches_nothing_is_refused(self):
        """The silent failure: a full, reconciled read that merged nothing."""
        country = dataclasses.replace(
            uscb.PAKISTAN,
            merged={("Sindh", "Karachi"): ("Karachi Centre District",)})
        with self.assertRaises(SystemExit) as caught:
            read_and_combine(pakistan_sheet(), country, LANGUAGE)
        message = str(caught.exception)
        self.assertIn("not one of them is in the sheet", message)
        # And it says what the sheet does have, which is where the answer is.
        self.assertIn("Karachi Central District", message)

    def test_a_declaration_whose_parent_matches_nothing_is_refused(self):
        """What actually happened: the key was compared against a spelling no
        cell in the sheet carries."""
        country = dataclasses.replace(
            uscb.PAKISTAN,
            merged={("Sind", "Karachi"): uscb.PAKISTAN.merged[
                ("Sindh", "Karachi")]})
        with self.assertRaises(SystemExit) as caught:
            read_and_combine(pakistan_sheet(), country, LANGUAGE)
        self.assertIn("no areas under Sind at all", str(caught.exception))

    def test_a_missing_part_is_refused(self):
        book = pakistan_sheet()
        book._rows = [r for r in book._rows
                      if str(r[0]).upper() != "MALIR DISTRICT"]
        with self.assertRaises(SystemExit) as caught:
            read_and_combine(book, uscb.PAKISTAN, LANGUAGE)
        self.assertIn("Malir District", str(caught.exception))
        self.assertIn("part of an area's people", str(caught.exception))

    def test_an_assembled_area_the_sheet_also_prints_is_refused(self):
        book = pakistan_sheet()
        book._rows.append(["KARACHI", "SINDH", "KARACHI DIVISION", "KARACHI",
                           3, *BADIN, sum(BADIN)])
        with self.assertRaises(SystemExit) as caught:
            read_and_combine(book, uscb.PAKISTAN, LANGUAGE)
        self.assertIn("twice", str(caught.exception))

    def test_parts_at_two_levels_are_refused(self):
        found = uscb.read(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        found[("SINDH", "MALIR DISTRICT")]["level"] = 1
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("two levels", str(caught.exception))

    def test_a_half_published_denominator_is_refused(self):
        found = uscb.read(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        found[("SINDH", "MALIR DISTRICT")]["published"] = None
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("denominator", str(caught.exception))

    def test_a_part_also_declared_absent_is_refused(self):
        country = dataclasses.replace(
            uscb.PAKISTAN,
            no_shape=frozenset((("Sindh", "Malir District"),)))
        with self.assertRaises(SystemExit) as caught:
            read_and_combine(pakistan_sheet(), country, LANGUAGE)
        self.assertIn("Malir District", str(caught.exception))
        self.assertIn("no_shape", str(caught.exception))

    def test_an_assembly_larger_than_its_parent_is_refused(self):
        found = uscb.read(pakistan_sheet(), uscb.PAKISTAN, LANGUAGE)
        row = found[("SINDH", "MALIR DISTRICT")]
        row["counts"]["Urdu"] += 40_000_000
        row["published"] += 40_000_000
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("not all inside", str(caught.exception))


class Declarations(unittest.TestCase):
    """What the configs claim, checked against each other rather than trusted."""

    def test_every_declared_name_is_spelt_the_way_records_are(self):
        """The invariant the fold rests on.

        `record()` publishes `str.title()` of the sheet's cell, and `aliases`,
        `no_shape` and `merged` are all written in that spelling. A
        declaration written any other way matches nothing, which is what
        happened, so it is asserted rather than assumed.
        """
        for country in uscb.COUNTRIES.values():
            declared = []
            for (parent, name), parts in country.merged.items():
                declared += [parent, name, *parts]
            for (parent, name) in country.no_shape:
                declared += [parent, name]
            for text in declared:
                self.assertEqual(text, " ".join(text.split()).title(),
                                 f"{country.iso3}: {text!r} is not written "
                                 "the way record() spells an area")

    def test_no_area_is_both_absent_and_a_part(self):
        for country in uscb.COUNTRIES.values():
            for (parent, _name), parts in country.merged.items():
                for part in parts:
                    self.assertNotIn(
                        (parent or country.name, part), country.no_shape,
                        f"{country.iso3}: {part} is declared both no_shape "
                        "and part of a merge")

    def test_no_part_is_claimed_by_two_merges(self):
        for country in uscb.COUNTRIES.values():
            seen = set()
            for (parent, _name), parts in country.merged.items():
                for part in parts:
                    self.assertNotIn((parent, part), seen,
                                     f"{country.iso3}: {part} is a part of "
                                     "two different shapes")
                    seen.add((parent, part))

    def test_pakistan_declares_the_six_districts_of_2017(self):
        parts = uscb.PAKISTAN.merged[("Sindh", "Karachi")]
        self.assertEqual(len(parts), 6)
        self.assertNotIn("Keamari District", parts,
                         "Keamari was split out of Karachi West in 2020, "
                         "after the census this workbook carries")

    def test_ethiopia_declares_all_ten_sub_cities(self):
        parts = uscb.ETHIOPIA.merged[("Ādīs Ābeba", "Ādīs Ābeba")]
        self.assertEqual(sorted(parts), sorted(ADDIS))

    def test_the_region_alias_reaches_the_boundary_name(self):
        self.assertIn("Region 14", uscb.ETHIOPIA.aliases["Ādīs Ābeba"])


class Spelling(unittest.TestCase):

    def test_case_and_padding_fold_to_one_key(self):
        fold = uscb.spelling
        self.assertEqual(fold(uscb.PAKISTAN, "SINDH", "KARACHI WEST DISTRICT"),
                         ("Sindh", "Karachi West District"))
        self.assertEqual(fold(uscb.PAKISTAN, "Sindh", "Karachi West District"),
                         ("Sindh", "Karachi West District"))
        self.assertEqual(fold(uscb.PAKISTAN, " Sindh ", "Karachi  West "
                                                        "District"),
                         ("Sindh", "Karachi West District"))

    def test_an_empty_parent_reads_as_the_country(self):
        """A first-order row has no parent cell, and `no_shape` names the
        country there. The fold has to agree with it."""
        self.assertEqual(uscb.spelling(uscb.PAKISTAN, "", "PUNJAB"),
                         ("Pakistan", "Punjab"))


if __name__ == "__main__":
    unittest.main()
