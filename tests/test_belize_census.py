"""Belize's 2022 General Characteristics tables: read by district and checked."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import belize_census as bc  # noqa: E402

D = bc.DISTRICTS


def table(title: str, rows: list[tuple[str, list[object]]]) -> list[list[object]]:
    """A by-district sheet as SIB lays it out: a blank first column, three cells a district."""
    names = [None, title, "Total", None, None]
    kinds = [None, None, "Total", "Male", "Female"]
    for d in D:
        names += [d, None, None]
        kinds += ["Total", "Male", "Female"]
    out = [[None, "Table: ..."], names, kinds]
    for label, values in rows:
        line = [None, label]
        for v in values:
            line += [v, 0, 0]
        out.append(line)
    out.append([None, "Source: Statistical Institute of Belize."])
    return out


class Tables(unittest.TestCase):
    def test_districts_are_read_from_their_total_columns(self):
        rows = table("Ethnicity", [("Total", [70, 10, 10, 10, 10, 10, 20]),
                                   ("Mestizo/Hispanic/Latino", [40, 5, 5, 5, 5, 5, 15]),
                                   ("Creole", [30, 5, 5, 5, 5, 5, 5])])
        counts, hidden, totals = bc.by_district(rows, bc.ETHNICITY, "ethnicity")
        self.assertEqual(counts["Toledo"], {"Mestizo": 15.0, "Creole": 5.0})
        self.assertEqual(totals["Total"], 70.0)
        self.assertEqual(hidden["Corozal"], 0)

    def test_a_suppressed_cell_is_counted_as_hidden_not_as_zero_silently(self):
        rows = table("Religion", [("Total", [30, 5, 5, 5, 5, 5, 5]),
                                  ("Roman Catholic", [30, 5, 5, 5, 5, 5, "<10"])])
        counts, hidden, _ = bc.by_district(rows, bc.RELIGION, "religion")
        self.assertEqual(hidden["Toledo"], 1)
        pop = {d: 5.0 for d in D} | {"Total": 30.0}
        bc.check_partition(counts, hidden, pop, "religions")
        pop["Belize"] = 50.0
        with self.assertRaises(SystemExit):
            bc.check_partition(counts, hidden, pop, "religions")

    def test_an_unknown_category_stops_the_run(self):
        rows = table("Ethnicity", [("Total", [1] * 7), ("Martian", [1] * 7)])
        with self.assertRaises(SystemExit):
            bc.by_district(rows, bc.ETHNICITY, "ethnicity")

    def test_age_groups_make_the_district_and_give_a_median(self):
        rows = [[None, "Table 6"], [None, "District", "Age Group", "Census 2010", "Census 2022"],
                [None, "Corozal", "Total", 0, 100], [None, None, "Less than 1", 0, 10],
                [None, None, "1-4", 0, 20], [None, None, "5-9", 0, 30],
                [None, None, "10-14", 0, 30], [None, None, "85+", 0, 10],
                [None, "Source: SIB"]]
        groups = bc.ages(rows)
        self.assertEqual(groups["Corozal"][0], (0, 0, 10.0))
        self.assertEqual(bc.grouped_median(groups["Corozal"]), 8.3)
        rows[3][4] = 20
        with self.assertRaises(SystemExit):
            bc.ages(rows)

    def test_sexes_must_make_the_total(self):
        rows = [[None, "Table 5"],
                [None, None, "Census 2010", None, None, None, "Census 2022", None, None],
                [None, None, "Total", "Males", "Females", "DK", "Total", "Males", "Females"],
                [None, "National", 1, 1, 0, 0, 100.4, 50.2, 50.2]]
        self.assertEqual(bc.sexes(rows)["National"], (100.4, 50.2, 50.2))
        rows[3][7] = 60
        with self.assertRaises(SystemExit):
            bc.sexes(rows)


if __name__ == "__main__":
    unittest.main()
