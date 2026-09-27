"""Tests for the Russian census readers: Volume 2's age blocks, no network."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import russia  # noqa: E402


def book(rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    blob = io.BytesIO()
    wb.save(blob)
    return blob.getvalue()


def block(name, groups, men_share=0.5, median=None):
    """A subject's block as Volume 2 lays it out: name, everyone, groups, medians, urban."""
    total = sum(groups)
    men = round(total * men_share)
    rows = [[name, None, None, None],
            ["Городское и сельское население", total, men, total - men],
            ["в том числе в возрасте, лет:", None, None, None]]
    for i, n in enumerate(groups[:-1]):
        rows.append([f"{5 * i} – {5 * i + 4}", n, None, None])
    rows.append([f"{5 * (len(groups) - 1)} и более", groups[-1], None, None])
    rows.append(["Средний возраст", 30.0, None, None])
    rows.append(["Медианный возраст", median, None, None])
    # The urban block that follows must not be read as more of everyone.
    rows.append(["Городское население", 1, 1, 0])
    rows.append(["0 – 4", 999, None, None])
    return rows


class AgesTest(unittest.TestCase):
    def test_a_block_reads_everyone_and_stops_at_the_urban_population(self):
        rows = block("Белгородская область", [10, 10, 10, 10], median=10.0)
        got = russia.ages(book(rows))["Белгородская область"]
        self.assertEqual(got["total"], 40)
        self.assertEqual(got["median"], 10.0)
        self.assertEqual([g[2] for g in got["groups"]], [10, 10, 10, 10])
        self.assertIsNone(got["groups"][-1][1])

    def test_volume_twos_spellings_become_volume_fives(self):
        rows = (block("Ханты-Мансийский автономный округ – Югра", [5, 5], median=5.0)
                + block("Кемеровская область – Кузбасс", [5, 5], median=5.0))
        got = russia.ages(book(rows))
        self.assertIn("ХМАО", got)
        self.assertIn("Кемеровская область - Кузбасс", got)

    def test_the_grouped_median_is_interpolated_in_its_group(self):
        self.assertEqual(russia.grouped([(0, 4, 10), (5, 9, 10), (10, None, 0)]), 5.0)
        self.assertIsNone(russia.grouped([(0, 4, 1), (5, None, 10)]))

    def test_a_subject_whose_median_the_groups_cannot_reach_stops_the_run(self):
        table = {s: {"total": 20, "men": 10, "women": 10, "median": 5.0,
                     "groups": [(0, 4, 10), (5, 9, 10), (10, None, 0)]}
                 for s in russia.SUBJECTS}
        table["Белгородская область"]["median"] = 8.0
        with self.assertRaises(SystemExit):
            russia.check_ages(table)

    def test_groups_that_miss_the_total_stop_the_run(self):
        table = {s: {"total": 21, "men": 10, "women": 11, "median": 5.0,
                     "groups": [(0, 4, 10), (5, 9, 10), (10, None, 0)]}
                 for s in russia.SUBJECTS}
        with self.assertRaises(SystemExit):
            russia.check_ages(table)

    def test_sex_ratio_is_men_per_hundred_women(self):
        got = russia.age_fields({"total": 300, "men": 140, "women": 160, "median": 40.1})
        self.assertEqual(got["sex_ratio"]["value"], 87.5)
        self.assertEqual(got["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(got["median_age"]["value"], 40.1)
        self.assertEqual(got["population"]["value"], 300)


class UniverseNoteTest(unittest.TestCase):
    """A composition says it is a share of those who answered, and how many did not."""

    def test_the_note_counts_who_is_left_out(self):
        got = {"published": 800.0, "counts": {"Русские": 800.0}, "unstated": 200.0}
        note = russia.universe_note("ethnicity", got, 1000)
        self.assertIn("of the 800 people in the subject who stated one", note)
        self.assertIn("200 of the 1,000 counted (20.0%)", note)

    def test_a_no_answer_row_that_disagrees_stops_the_run(self):
        got = {"published": 800.0, "counts": {"Русские": 800.0}, "unstated": 150.0}
        with self.assertRaises(SystemExit):
            russia.universe_note("language", got, 1000)


if __name__ == "__main__":
    unittest.main()
