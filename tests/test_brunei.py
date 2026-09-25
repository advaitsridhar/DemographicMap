"""Brunei's BPP 2021 annex workbook, and the guards on reading it."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
from fetch_census import brunei as bn  # noqa: E402

# The header block of tables A3 and A4, as DEPS prints it: a merged cell per
# district over three columns, so the district's name shares a column with the
# first of its Orang / Lelaki / Perempuan trio.
HEADER = ["", "Jumlah", "", "", "Brunei Muara", "", "", "Belait", "", "",
          "Tutong", "", "", "Temburong", "", ""]
SUBHEAD = ["Race", "Orang", "Lelaki", "Perempuan"] + ["Orang", "Lelaki",
                                                      "Perempuan"] * 4


def figures(label, persons):
    """One printed row: a label and five Persons/Males/Females blocks."""
    row = [label]
    for value in persons:
        row += [value, value // 2, value - value // 2]
    return row


def caption(label):
    """The Malay caption above the figures, which carries no numbers."""
    return [label] + [""] * (len(HEADER) - 1)


# Table A3 and table A4 as the workbook prints them: country, then the four
# districts. The figures are DEPS's own.
A3 = [["Jadual A3 : Penduduk mengikut Bangsa, Daerah dan Jantina, 2021"],
      ["Table A3 : Population by Race, District and Sex, 2021"],
      HEADER, ["Bangsa", "Total"], SUBHEAD,
      caption("Melayu"), figures("Malays", [297_016, 222_772, 33_245, 35_283, 5_716]),
      caption("Cina"), figures("Chinese", [42_132, 28_522, 11_068, 2_318, 224]),
      caption("Lain-lain"), figures("Others", [101_567, 67_236, 21_218, 9_609, 3_504]),
      figures("Jumlah/Total", [440_715, 318_530, 65_531, 47_210, 9_444])]

A4 = [["Jadual A4"], ["Table A4 : Population by Religion, District and Sex, 2021"],
      HEADER, ["Ugama", "Total"], SUBHEAD,
      # The Malay for Islam is Islam, so A4 prints the label twice -- once
      # empty, once with the counts. That collision is the reason the reader
      # skips a row whose every figure is blank rather than keying on the label.
      caption("Islam"), figures("Islam", [362_035, 269_074, 46_072, 39_763, 7_126]),
      caption("Kristian"),
      figures("Christianity", [29_462, 20_076, 7_028, 1_151, 1_207]),
      caption("Buddha"),
      figures("Buddhism", [27_745, 19_306, 7_235, 1_104, 100]),
      caption("Lain-lain"), figures("Others", [21_473, 10_074, 5_196, 5_192, 1_011]),
      figures("Jumlah/Total", [440_715, 318_530, 65_531, 47_210, 9_444])]

# Table C1, which the workbook keeps on a sheet with C2 to C5 beneath it. The
# Brunei Muara block is DEPS's; the other three are shortened to one row each
# holding the district's whole population, which is all the sum check asks.
BRUNEI_MUARA = [
    ("Kianggeh", 8_102), ("Sungai Kedayan", 241), ("Saba", 827),
    ("Sungai Kebun", 4_282), ("Burong Pingai Ayer", 1_459), ("Peramu", 1_151),
    ("Tamoi", 942), ("Berakas A", 28_311), ("Berakas B", 39_284),
    ("Gadong A", 35_424), ("Gadong B", 38_067), ("Kota Batu", 12_676),
    ("Lumapas", 8_058), ("Kilanas", 24_981), ("Sengkurong", 40_972),
    ("Pangkalan Batu", 15_860), ("Mentiri", 39_324), ("Serasa", 18_569),
]


def c1_block(district, mukims):
    rows = [["District and Mukim", "Persons", "Males", "Females"],
            figures(district, [bn.PUBLISHED_DISTRICT[district]])]
    rows += [figures(name, [people]) for name, people in mukims]
    return rows


def even_split(district):
    """Every mukim of a district carrying an equal share of its total."""
    names = bn.MUKIMS[district]
    total = bn.PUBLISHED_DISTRICT[district]
    each = total // len(names)
    out = [(n, each) for n in names[:-1]]
    return out + [(names[-1], total - each * (len(names) - 1))]


C1 = (c1_block("Brunei Muara", BRUNEI_MUARA)
      + c1_block("Belait", even_split("Belait"))
      + c1_block("Tutong", even_split("Tutong"))
      + c1_block("Temburong", even_split("Temburong"))
      # C2 follows on the same sheet, listing kampungs under the same mukim
      # headings. The reader must already have stopped.
      + [["Jadual C2"], figures("Kianggeh", [8_102]),
         figures("Kampung Sungai Kedayan", [99])])

SHEETS = {"List A": [], "A3": A3, "A4": A4, "List C": [], "C1-C5": C1}


class TheDistrictTables(unittest.TestCase):
    def test_race_and_religion_read_and_reconcile(self):
        race, totals = bn.read_composition(A3, bn.RACE_LABELS, "A3")
        bn.check_composition("A3", race, totals, bn.PUBLISHED_RACE)
        self.assertEqual(race["Brunei Muara"],
                         {"Malay": 222_772, "Chinese": 28_522, "Others": 67_236})
        faith, faith_totals = bn.read_composition(A4, bn.RELIGION_LABELS, "A4")
        bn.check_composition("A4", faith, faith_totals, bn.PUBLISHED_RELIGION)
        self.assertEqual(faith["Temburong"]["Other, none, or not stated"], 1_011)
        self.assertEqual(totals, faith_totals)

    def test_the_malay_caption_is_not_read_as_a_row(self):
        # A4 prints "Islam" twice; only the row with figures is the table.
        faith, _ = bn.read_composition(A4, bn.RELIGION_LABELS, "A4")
        self.assertEqual(faith["Jumlah"]["Islam"], 362_035)

    def test_a_row_with_some_figures_missing_is_refused(self):
        broken = [r[:] for r in A3]
        row = next(r for r in broken if r[0] == "Chinese")
        row[7] = ""                                   # Belait's Persons cell
        with self.assertRaises(SystemExit) as caught:
            bn.read_composition(broken, bn.RACE_LABELS, "A3")
        self.assertIn("Belait", str(caught.exception))

    def test_a_reissued_table_that_is_not_the_census_is_refused(self):
        # A later estimate under the same sheet name: Malays a thousand higher.
        race, totals = bn.read_composition(A3, bn.RACE_LABELS, "A3")
        race["Jumlah"]["Malay"] += 1_000
        with self.assertRaises(SystemExit) as caught:
            bn.check_composition("A3", race, totals, bn.PUBLISHED_RACE)
        self.assertIn("not the 2021 census table", str(caught.exception))

    def test_districts_that_do_not_sum_to_the_country_are_refused(self):
        race, totals = bn.read_composition(A3, bn.RACE_LABELS, "A3")
        race["Tutong"]["Malay"] -= 5
        with self.assertRaises(SystemExit):
            bn.check_composition("A3", race, totals, bn.PUBLISHED_RACE)

    def test_a_table_with_no_district_header_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            bn.read_composition([["Bangsa", "Total"]], bn.RACE_LABELS, "A3")
        self.assertIn("districts", str(caught.exception))


class TheMukimTable(unittest.TestCase):
    def test_all_39_mukims_are_read_and_sum_to_their_districts(self):
        mukims = bn.read_mukims(C1)
        self.assertEqual(sum(len(v) for v in mukims.values()), 39)
        self.assertEqual(mukims["Brunei Muara"]["Mentiri"], 39_324)
        for district, counts in mukims.items():
            self.assertEqual(sum(counts.values()), bn.PUBLISHED_DISTRICT[district])

    def test_the_walk_stops_before_the_kampung_tables(self):
        # C2's first row repeats "Kianggeh". Reading it twice would double
        # Brunei Muara, which the sum check would catch -- but the reader
        # should never get there.
        mukims = bn.read_mukims(C1)
        self.assertEqual(mukims["Brunei Muara"]["Kianggeh"], 8_102)

    def test_a_renamed_mukim_is_refused_rather_than_dropped(self):
        broken = [r[:] for r in C1]
        row = next(r for r in broken if r[0] == "Melilas")
        row[0] = "Mukim Melilas"
        with self.assertRaises(SystemExit) as caught:
            bn.read_mukims(broken)
        self.assertIn("Melilas", str(caught.exception))


class TheRecords(unittest.TestCase):
    def setUp(self):
        self.rows = bn.build(SHEETS)
        self.by_name = {r["name"]: r for r in self.rows}

    def test_four_districts_and_thirty_eight_mukims(self):
        levels = [r["level"] for r in self.rows]
        self.assertEqual(levels.count("admin1"), 4)
        self.assertEqual(levels.count("admin2"), 38)

    def test_every_mukim_reaches_a_shape_by_name_or_declared_alias(self):
        # Four districts is too few for a join failure to be anything but a
        # bug, and 38 mukims is not many more. Every row must reach a shape
        # under its own name or a name it declares, and every shape must be
        # reached: the two sets are compared whole, so a mukim renamed on
        # either side shows up here rather than as an empty polygon.
        shapes = Path(__file__).resolve().parent.parent / "site/data/admin2/BRN.units.json"
        if not shapes.exists():                       # a checkout without site/
            self.skipTest("site/data/admin2/BRN.units.json is not in this checkout")
        import json
        drawn = {row["name"] for row in json.loads(shapes.read_text())}
        reached = set()
        for row in (r for r in self.rows if r["level"] == "admin2"):
            names = {row["name"], *row.get("aliases", [])} & drawn
            self.assertEqual(len(names), 1, row["name"])
            reached |= names
        self.assertEqual(reached, drawn)

    def test_gadong_is_the_two_census_mukims_added(self):
        gadong = self.by_name["Gadong"]
        self.assertEqual(gadong["population"]["value"], 35_424 + 38_067)
        self.assertIn("Gadong A and Gadong B", gadong["ethnicity"]["note"])

    def test_bokok_carries_the_boundary_file_s_spelling_as_an_alias(self):
        self.assertIn("Bunkok", self.by_name["Bokok"]["aliases"])

    def test_a_district_carries_both_compositions_with_the_census_year(self):
        muara = self.by_name["Brunei Muara"]
        leading = max(muara["ethnicity"], key=lambda r: r["pct"])
        self.assertEqual(leading["group"], "Malay")
        self.assertEqual(muara["ethnicity_year"], 2021)
        self.assertEqual(muara["religion_year"], 2021)
        self.assertAlmostEqual(sum(r["pct"] for r in muara["religion"]), 100.0,
                               delta=0.2)
        self.assertIn("Brunei-Muara", muara["aliases"])

    def test_a_mukim_carries_a_head_count_and_a_gap_that_says_why(self):
        mentiri = self.by_name["Mentiri"]
        self.assertEqual(mentiri["population"]["value"], 39_324)
        for field in ("ethnicity", "religion"):
            self.assertTrue(common.is_gap(mentiri[field]))
            self.assertIn("by district only", mentiri[field]["note"])
            self.assertIn("39,324", mentiri[field]["note"])
        self.assertIsNone(mentiri.get("ethnicity_year"))

    def test_language_is_asked_and_unpublished_everywhere(self):
        for row in self.rows:
            self.assertEqual(row["language"]["status"], common.NOT_AVAILABLE)
            self.assertIn("E27", row["language"]["note"])
        # Never not_collected: the census does ask, so the country must not
        # declare otherwise.
        self.assertIsNone(common.collection_policy("BRN", "language"))
        self.assertIsNone(common.collection_policy("BRN", "religion"))
        self.assertIsNone(common.collection_policy("BRN", "ethnicity"))

    def test_the_labels_are_the_project_canon(self):
        import canonical_groups as cg
        import group_tree
        for label in bn.RACE_LABELS.values():
            self.assertTrue(group_tree.hue("ethnicity", label), label)
        for label in bn.RELIGION_LABELS.values():
            self.assertTrue(group_tree.hue("religion", label), label)
        # The census's residual welds other faiths to no religion, so it must
        # not land anywhere that names a religion.
        self.assertEqual(cg.ancestry("religion", "Other, none, or not stated")[-1],
                         "Not stated")

    def test_the_notes_say_what_the_state_s_categories_mean(self):
        muara = self.by_name["Brunei Muara"]
        self.assertIn("Kedayan", muara["ethnicity_note"])
        self.assertIn("state religion", muara["religion_note"])

    def test_a_workbook_missing_a_sheet_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            bn.build({k: v for k, v in SHEETS.items() if k != "A4"})
        self.assertIn("A4", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
