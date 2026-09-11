"""Census areas that share one boundary shape, summed into it.

Two real cases, and the figures here are the adapter's own output for them --
``data/processed/pakistan_language.json`` and ``data/processed/ethiopia_region.json``,
which is what ``uscb.read()`` printed when it last ran against the workbooks:

* **Karachi.** The 2017 census counts six districts; geoBoundaries draws one
  shape. All six reached no shape, so Karachi -- 16.0 million people, the
  largest second-level language gap left in a country otherwise 114 districts
  full -- carried nothing.
* **Addis Ababa.** The 2007 census counts ten sub-cities; geoBoundaries draws
  one second-order shape inside the region, labelled "Region 14". The ten were
  declared as having no shape, which left that one empty.

Addis Ababa is also the control. Its ten sub-cities come to 2,739,551 against
a region row of 2,739,551 -- the source's own arithmetic saying these ten are
all of it -- so the test asserts the assembly against a figure this project did
not compute.

The workbooks themselves are not in the repository (they are fetched from HDX
at run time), so the sheet used by the end-to-end test is built to the schema
the module documents: the geography column names are quoted from ``uscb``'s own
``GEOGRAPHY`` set, the labels in the second header row are the ones the adapter
publishes, and the figures and area names are the real ones above. The exact
spelling of a group column's identifier is the one thing reconstructed, and it
is the one thing nothing here depends on -- ``groups()`` takes the label from
the second header row, not from the name.
"""

import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import uscb  # noqa: E402


# Table 11, population by mother tongue, for the six districts of Karachi.
# Counts as data/processed/pakistan_language.json carries them.
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

# Badin, a district of Sindh that is not part of Karachi, from the same table.
BADIN = (14982, 62221, 1698882, 5792, 1908, 124, 8997, 5070, 4093, 2889)

# The 2007 census's religion sheet for Addis Ababa's ten sub-cities, and the
# region's own printed row beneath them. Six groups rather than the language
# sheet's ninety, because the merge does not care which field it is folding and
# a fixture that fits on a screen can be read.
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

# The region's own row in the same sheet, which the ten must come to.
ADDIS_REGION = (2045445, 212907, 13202, 444025, 1377, 22595)


def areas(table: dict[str, tuple[int, ...]], labels: tuple[str, ...],
          parent: str, level: int,
          published: dict[str, float] | None = None
          ) -> dict[tuple[str, str], dict]:
    """The mapping ``read()`` returns, for one sheet's worth of areas."""
    out = {}
    for name, figures in table.items():
        counts = {label: float(value)
                  for label, value in zip(labels, figures) if value}
        total = sum(counts.values())
        out[(parent, name)] = {
            "level": level, "parent": parent, "name": name,
            "counts": counts,
            "published": (published or {}).get(name, total),
            "summed": total}
    return out


def pakistan(**over) -> dict[tuple[str, str], dict]:
    return areas(KARACHI, LANGUAGES, "Sindh", 3, **over)


def ethiopia() -> dict[tuple[str, str], dict]:
    out = areas(ADDIS, RELIGIONS, "Ādīs Ābeba", 2)
    # The region's own row, keyed as read() keys a first-order area.
    counts = {label: float(v) for label, v in zip(RELIGIONS, ADDIS_REGION)}
    out[("", "Ādīs Ābeba")] = {
        "level": 1, "parent": "", "name": "Ādīs Ābeba", "counts": counts,
        "published": sum(counts.values()), "summed": sum(counts.values())}
    return out


LANGUAGE = uscb.Topic("Mother Tongue", "language", prefix="LNG_")
RELIGION = uscb.Topic("Religion", "religion")


class Merging(unittest.TestCase):

    def test_karachi_is_summed_into_one_area(self):
        found = pakistan()
        uscb.combine(uscb.PAKISTAN, LANGUAGE, found)

        self.assertIn(("Sindh", "Karachi"), found)
        for part in KARACHI:
            self.assertNotIn(("Sindh", part), found,
                             "a part that has been summed must not also "
                             "remain as an area of its own")
        karachi = found[("Sindh", "Karachi")]
        self.assertEqual(karachi["level"], 3)
        self.assertEqual(karachi["assembled"], tuple(KARACHI))

        # Every language adds up across the six, and nothing is invented: the
        # merged area's groups are exactly the groups the parts had.
        for index, label in enumerate(LANGUAGES):
            self.assertEqual(karachi["counts"][label],
                             sum(f[index] for f in KARACHI.values()),
                             label)
        self.assertEqual(karachi["summed"], 16024894)
        self.assertEqual(karachi["published"], 16024894)

    def test_karachi_shares_sum_to_a_hundred(self):
        found = pakistan()
        uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        row = found[("Sindh", "Karachi")]
        published = uscb.shares(row["counts"], total=row["published"])
        self.assertAlmostEqual(sum(g["pct"] for g in published), 100.0,
                               delta=0.15)
        # Urdu first, as it is in every one of the six districts but Malir.
        self.assertEqual(published[0]["group"], "Urdu")
        self.assertEqual(published[0]["count"], 6779142)

    def test_addis_matches_the_region_the_source_prints(self):
        """The control the file supplies itself."""
        found = ethiopia()
        uscb.combine(uscb.ETHIOPIA, RELIGION, found)

        assembled = found[("Ādīs Ābeba", "Ādīs Ābeba")]
        region = found[("", "Ādīs Ābeba")]
        self.assertEqual(assembled["counts"], region["counts"])
        self.assertEqual(assembled["summed"], 2739551.0)
        self.assertEqual(assembled["level"], 2,
                         "the assembly stays at the level of its parts")
        self.assertEqual(region["level"], 1,
                         "and the region's own row is untouched")

    def test_a_sheet_without_the_parts_is_left_alone(self):
        """A workbook whose sheet does not list the parts merges nothing."""
        found = {("Sindh", "Badin District"): {
            "level": 3, "parent": "Sindh", "name": "Badin District",
            "counts": {"Sindhi": 1.0}, "published": 1.0, "summed": 1.0}}
        uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertEqual(list(found), [("Sindh", "Badin District")])


class Refusals(unittest.TestCase):
    """Every one of these is a way for a wrong merge to look like a right one."""

    def test_a_missing_part_is_refused(self):
        found = pakistan()
        del found[("Sindh", "Malir District")]
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("Malir District", str(caught.exception))
        # And the five that are there are still five areas, not one wrong one.
        self.assertIn(("Sindh", "Korangi District"), found)

    def test_an_assembled_area_the_sheet_also_prints_is_refused(self):
        found = pakistan()
        found[("Sindh", "Karachi")] = {
            "level": 3, "parent": "Sindh", "name": "Karachi",
            "counts": {"Urdu": 1.0}, "published": 1.0, "summed": 1.0}
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("twice", str(caught.exception))

    def test_parts_at_two_levels_are_refused(self):
        found = pakistan()
        found[("Sindh", "Malir District")]["level"] = 2
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("two levels", str(caught.exception))

    def test_a_half_published_denominator_is_refused(self):
        found = pakistan()
        found[("Sindh", "Malir District")]["published"] = None
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        self.assertIn("denominator", str(caught.exception))

    def test_no_denominator_anywhere_is_allowed(self):
        """Ethiopia publishes none, and that is not the same fault."""
        found = ethiopia()
        for row in found.values():
            row["published"] = None
        uscb.combine(uscb.ETHIOPIA, RELIGION, found)
        self.assertIsNone(found[("Ādīs Ābeba", "Ādīs Ābeba")]["published"])
        self.assertEqual(found[("Ādīs Ābeba", "Ādīs Ābeba")]["summed"],
                         2739551.0)

    def test_a_part_also_declared_absent_is_refused(self):
        """Two declarations that contradict each other."""
        country = dataclasses.replace(
            uscb.PAKISTAN,
            no_shape=frozenset((("Sindh", "Malir District"),)))
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(country, LANGUAGE, pakistan())
        self.assertIn("Malir District", str(caught.exception))
        self.assertIn("no_shape", str(caught.exception))

    def test_an_assembly_larger_than_its_parent_is_refused(self):
        found = ethiopia()
        found[("Ādīs Ābeba", "Yeka")]["counts"]["Orthodox"] += 1_000_000
        found[("Ādīs Ābeba", "Yeka")]["published"] += 1_000_000
        with self.assertRaises(SystemExit) as caught:
            uscb.combine(uscb.ETHIOPIA, RELIGION, found)
        self.assertIn("not all inside", str(caught.exception))


class Sheet(unittest.TestCase):
    """The same merge, reached the way a run reaches it: through ``read()``."""

    def sheet(self) -> list[list]:
        names = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM3_NAME",
                 "ADM_LEVEL"]
        aliases = ["", "", "", "", ""]
        for index, label in enumerate(LANGUAGES):
            names.append(f"LNG_G{index:02d}")
            aliases.append(label)
        names.append("LNG_TOTAL")
        aliases.append("Total population")
        rows = [names, aliases]
        for name, figures in KARACHI.items():
            rows.append([name, "Sindh", "Karachi Division", name, 3,
                         *figures, sum(figures)])
        # One district that is not part of Karachi, to show the fold reaches
        # only what it is declared to reach. Badin's figures, like the rest,
        # are the adapter's own output for the real sheet.
        rows.append(["Badin District", "Sindh", "Hyderabad Division",
                     "Badin District", 3, *BADIN, sum(BADIN)])
        return rows

    def read(self):
        rows = self.sheet()

        class Book:
            sheetnames = ["Mother Tongue"]

            def __getitem__(self, _name):
                class Sheet_:
                    @staticmethod
                    def iter_rows(values_only=True):
                        return iter(rows)
                return Sheet_()

        found = uscb.read(Book(), uscb.PAKISTAN, LANGUAGE)
        uscb.combine(uscb.PAKISTAN, LANGUAGE, found)
        return found

    def test_the_sheet_folds_to_karachi_and_badin(self):
        found = self.read()
        self.assertEqual(sorted(found),
                         [("Sindh", "Badin District"), ("Sindh", "Karachi")])
        self.assertEqual(found[("Sindh", "Karachi")]["summed"], 16024894)

    def test_the_folded_sheet_still_reconciles(self):
        """check_total is the reconciliation, and an assembly must face it."""
        found = self.read()
        uscb.check_total(uscb.PAKISTAN, LANGUAGE, found)     # no SystemExit


class Declarations(unittest.TestCase):
    """What the configs claim, checked against each other rather than trusted."""

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


if __name__ == "__main__":
    unittest.main()
