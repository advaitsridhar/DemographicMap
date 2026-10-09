"""Malaysia: median age and sex ratio from OpenDOSM's age and sex dimensions.

No network: the rows are built here in the files' own layout
(state,district,date,sex,age,ethnicity,population, population in thousands).
"""

import unittest

from scripts.fetch_census import malaysia as m

GROUPS = [f"{a}-{a + 4}" for a in range(0, 85, 5)] + ["85+"]


def rows_for(place: dict[str, str], date: str, counts: list[float],
             men: float, women: float) -> list[dict[str, str]]:
    """One place's rows: both sexes by group, the overall rows, sexes overall."""
    total = sum(counts)
    out = [{**place, "date": date, "sex": "both", "age": g, "ethnicity": "overall",
            "population": f"{n:.1f}"} for g, n in zip(GROUPS, counts)]
    out.append({**place, "date": date, "sex": "both", "age": "overall",
                "ethnicity": "overall", "population": f"{total:.1f}"})
    out.append({**place, "date": date, "sex": "male", "age": "overall",
                "ethnicity": "overall", "population": f"{men:.1f}"})
    out.append({**place, "date": date, "sex": "female", "age": "overall",
                "ethnicity": "overall", "population": f"{women:.1f}"})
    # One ethnicity row, so compositions() finds the date.
    out.append({**place, "date": date, "sex": "both", "age": "overall",
                "ethnicity": "bumi_malay", "population": f"{total:.1f}"})
    return out


class AgeTest(unittest.TestCase):
    def test_median_within_the_group_that_holds_the_middle_person(self):
        # 18 groups of 10.0 thousand: 180,000 people, the middle one at 90,000,
        # which is the end of the ninth group (40-44): median 45.0.
        counts = [10.0] * 18
        rows = rows_for({"state": "Johor"}, "2025-01-01", counts, 91.0, 89.0)
        unit = m.ages(rows, ("state",), "2025-01-01")[("Johor",)]
        fields = m.age_fields("Johor", unit, 2025, 180_000)
        self.assertEqual(fields["median_age"]["value"], 45.0)
        self.assertEqual(fields["sex_ratio"]["value"], round(100 * 91 / 89, 1))
        self.assertEqual(fields["sex_ratio"]["unit"], "males_per_100_females")
        self.assertIn("not a count", fields["median_age_note"])

    def test_groups_that_miss_the_total_refuse(self):
        rows = rows_for({"state": "Johor"}, "2025-01-01", [10.0] * 18, 91.0, 89.0)
        unit = m.ages(rows, ("state",), "2025-01-01")[("Johor",)]
        with self.assertRaises(SystemExit):
            m.age_fields("Johor", unit, 2025, 200_000)

    def test_sexes_that_miss_the_total_refuse(self):
        rows = rows_for({"state": "Johor"}, "2025-01-01", [10.0] * 18, 95.0, 80.0)
        unit = m.ages(rows, ("state",), "2025-01-01")[("Johor",)]
        with self.assertRaises(SystemExit):
            m.age_fields("Johor", unit, 2025, 180_000)

    def test_an_unknown_age_label_refuses(self):
        rows = rows_for({"state": "Johor"}, "2025-01-01", [10.0] * 18, 91.0, 89.0)
        rows[3]["age"] = "15-24"
        with self.assertRaises(SystemExit):
            m.ages(rows, ("state",), "2025-01-01")

    def test_a_missing_group_refuses(self):
        rows = rows_for({"state": "Johor"}, "2025-01-01", [10.0] * 18, 91.0, 89.0)
        del rows[4]
        with self.assertRaises(SystemExit):
            m.ages(rows, ("state",), "2025-01-01")

    def test_districts_are_checked_against_their_state(self):
        district_rows = rows_for({"state": "Perlis", "district": "Perlis"}, "2025-01-01",
                                 [2.0] * 18, 18.2, 17.8)
        state_ok = rows_for({"state": "Perlis"}, "2025-01-01", [2.0] * 18, 18.2, 17.8)
        state_bad = rows_for({"state": "Perlis"}, "2025-01-01", [3.0] * 18, 27.2, 26.8)
        date, comps = m.compositions(district_rows, ("state", "district"))
        m.check_against_states(comps, state_ok, date)
        with self.assertRaises(SystemExit):
            m.check_against_states(comps, state_bad, date)

    def test_a_state_record_carries_both_fields(self):
        rows = []
        for i in range(16):
            rows += rows_for({"state": f"State {i}"}, "2026-01-01", [2.0] * 18, 18.2, 17.8)
        records = m.build_states(rows)
        self.assertEqual(len(records), 16)
        self.assertEqual(records[0]["median_age"]["value"], 45.0)
        self.assertEqual(records[0]["median_age"]["year"], 2026)
        self.assertEqual(records[0]["sex_ratio"]["value"], round(100 * 18.2 / 17.8, 1))

    def test_the_indian_race_is_written_with_its_country(self):
        # A bare "Indian" is the nationality a European or Korean register
        # counts; DOSM's is Malaysia's own citizens of Indian descent.
        self.assertEqual(m.LABELS["indian"], "Indian (Malaysia)")


if __name__ == "__main__":
    unittest.main()
