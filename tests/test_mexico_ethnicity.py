"""Mexico's ethnicity: the codes are read off INEGI's table, and the two answers are crossed, not stacked."""
from __future__ import annotations

import io
import sys
import unittest
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import mexico_ethnicity as m  # noqa: E402

YES_IN_PART = (frozenset({"1", "2"}), frozenset({"1", "2"}), False)
YES_ONLY = (frozenset({"1"}), frozenset({"1"}), False)

# One municipio on the Costa Chica, weighted: (age band, indigenous, Afro).
COAST = Counter({
    ("3+", "1", "1"): 300,      # indigenous and Afro-Mexican
    ("3+", "2", "3"): 100,      # indigenous in part, not Afro
    ("3+", "3", "1"): 200,      # Afro-Mexican only
    ("3+", "3", "3"): 350,      # neither
    ("3+", "9", "3"): 30,       # indigenous not stated
    ("3+", "3", "4"): 20,       # does not know whether Afro-Mexican
    ("0-2", "", "1"): 70,       # too young for the indigenous question
    ("unstated", "3", "3"): 5,
})


def person_file(rows):
    header = "ENT,MUN,LOC50K,FACTOR,EDAD,PERTE_INDIGENA,AFRODES\n"
    body = "".join(",".join(r) + "\n" for r in rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Personas12.CSV", header + body)
    return buf.getvalue()


class Reading(unittest.TestCase):
    def test_the_reading_that_reproduces_the_table_is_the_one_that_agrees(self):
        # 400 of 1,000 aged 3+ say yes or yes-in-part: 40%.
        table = {"base": 1000, "yes": 40.0, "no": 57.0, "unstated": 3.0}
        self.assertTrue(m.agrees(COAST, table, YES_IN_PART))
        self.assertFalse(m.agrees(COAST, table, YES_ONLY))

    def test_a_base_off_by_the_unstated_ages_does_not_agree(self):
        table = {"base": 1000, "yes": 40.0, "no": 57.0, "unstated": 3.0}
        with_unstated_age = (YES_IN_PART[0], YES_IN_PART[1], True)
        self.assertFalse(m.agrees(COAST, table, with_unstated_age))


class Split(unittest.TestCase):
    def test_people_who_say_yes_to_both_are_counted_once(self):
        base, split = m.composition(COAST, YES_IN_PART)
        self.assertEqual(base, 1000)
        self.assertEqual(split, {
            "Indigenous and Afro-Mexican": 300,
            "Indigenous (self-identified)": 100,
            "Afro-Mexican or Afro-descendant": 200,
            "Mestizo or white (neither indigenous nor Afro-Mexican)": 350,
            "Not stated": 50,
        })
        self.assertEqual(sum(split.values()), base)

    def test_children_under_three_are_outside_the_base(self):
        base, split = m.composition(COAST, YES_IN_PART)
        self.assertNotIn(70, split.values())
        self.assertEqual(base, sum(v for (band, _, _), v in COAST.items() if band == "3+"))


class Tally(unittest.TestCase):
    def test_people_are_weighted_by_their_expansion_factor(self):
        blob = person_file([
            ("12", "001", "0001", "20", "35", "1", "3"),
            ("12", "001", "0001", "15", "2", "", "1"),
            ("12", "002", "0001", "30", "999", "3", "3"),
        ])
        counts = m.tally("12", "test.zip", blob)
        self.assertEqual(counts["001"], Counter({("3+", "1", "3"): 20, ("0-2", "", "1"): 15}))
        self.assertEqual(counts["002"], Counter({("unstated", "3", "3"): 30}))

    def test_a_person_from_another_state_stops_the_run(self):
        blob = person_file([("13", "001", "0001", "20", "35", "1", "3")])
        with self.assertRaises(SystemExit):
            m.tally("12", "test.zip", blob)


class Note(unittest.TestCase):
    def test_the_coefficient_of_variation_is_quoted_when_published(self):
        self.assertIn("7.7%", m.note_for({"cv": 7.691905}))
        self.assertEqual(m.note_for({}), m.NOTE)


if __name__ == "__main__":
    unittest.main()
