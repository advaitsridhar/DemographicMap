"""Malaysia: median age and sex ratio from OpenDOSM's age and sex dimensions.

No network: the rows are built here in the files' own layout
(state,district,date,sex,age,ethnicity,population, population in thousands).
"""

import unittest
from unittest import mock

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

    def test_an_even_ratio_carries_no_counts(self):
        rows = rows_for({"state": "Johor"}, "2025-01-01", [10.0] * 18, 91.0, 89.0)
        unit = m.ages(rows, ("state",), "2025-01-01")[("Johor",)]
        note = m.age_fields("Johor", unit, 2025, 180_000, what="state")["sex_ratio_note"]
        self.assertNotIn("unusual", note)

    def test_an_unusual_ratio_gives_dosm_s_counts_and_no_cause(self):
        # Bukit Mabong: 6.4 thousand males and 4.2 thousand females, 152.4.
        place = {"state": "Sarawak", "district": "Bukit Mabong"}
        counts = [0.6] * 17 + [0.4]
        rows = rows_for(place, "2024-01-01", counts, 6.4, 4.2)
        unit = m.ages(rows, ("state", "district"), "2024-01-01")[("Sarawak", "Bukit Mabong")]
        fields = m.age_fields("Sarawak/Bukit Mabong", unit, 2024, 10_600)
        self.assertEqual(fields["sex_ratio"]["value"], 152.4)
        note = fields["sex_ratio_note"]
        self.assertIn("An unusual ratio for a whole district: DOSM's estimate for 2024 counts "
                      "6,400 males against 4,200 females here, each rounded to the nearest "
                      "hundred, and the table gives no reason.", note)
        for cause in ("plantation", "worker", "foreign"):
            self.assertNotIn(cause, note)

    def test_an_unusual_ratio_names_the_non_citizens_where_the_file_has_them(self):
        place = {"state": "Pahang", "district": "Cameron Highlands"}
        rows = rows_for(place, "2026-01-01", [2.5] * 17 + [2.4], 27.1, 17.8)
        rows += [{**place, "date": "2026-01-01", "sex": sex, "age": "overall",
                  "ethnicity": "other_noncitizen", "population": n}
                 for sex, n in (("male", "7.0"), ("female", "2.8"))]
        unit = m.ages(rows, ("state", "district"), "2026-01-01")[("Pahang", "Cameron Highlands")]
        note = m.age_fields("Pahang/Cameron Highlands", unit, 2026, 44_900)["sex_ratio_note"]
        self.assertIn("27,100 males against 17,800 females", note)
        self.assertIn("7,000 of the males and 2,800 of the females are not Malaysian citizens",
                      note)

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

    def test_a_state_whose_latest_rows_divide_a_drawn_district_is_read_before(self):
        # Sabah's 2026 rows carve Membakut out of Beaufort; the map draws the
        # Beaufort of before, so Sabah is read at 2025. Johor's districts are
        # all drawn in 2026, and W.P. Putrajaya, at every date and drawn as its
        # state only, holds no state back.
        rows, states = [], []
        layout = {"Johor": {"2025-01-01": {"Batu Pahat": 10.0},
                            "2026-01-01": {"Batu Pahat": 11.0}},
                  "Sabah": {"2025-01-01": {"Beaufort": 8.0},
                            "2026-01-01": {"Beaufort": 6.0, "Membakut": 2.0}},
                  "W.P. Putrajaya": {"2025-01-01": {"W.P. Putrajaya": 1.0},
                                     "2026-01-01": {"W.P. Putrajaya": 1.0}}}
        for state, dates in layout.items():
            for date, districts in dates.items():
                for district, people in districts.items():
                    rows += rows_for({"state": state, "district": district}, date,
                                     [people / 18] * 18, people / 2, people / 2)
                total = sum(districts.values())
                states.append({"state": state, "date": date, "sex": "both", "age": "overall",
                               "ethnicity": "overall", "population": f"{total:.1f}"})
        drawn = {m.district_key(n) for n in ("Batu Pahat", "Beaufort")}
        chosen = m.vintages(rows, drawn)
        self.assertEqual(chosen["Johor"], ("2026-01-01", []))
        self.assertEqual(chosen["Sabah"], ("2025-01-01", ["Membakut"]))
        self.assertEqual(chosen["W.P. Putrajaya"][0], "2026-01-01")
        with mock.patch.object(m, "DISTRICTS_EXPECTED", (1, 10)):
            recs = {r["name"]: r for r in m.build_districts(rows, states, drawn)}
        self.assertEqual(recs["Batu Pahat"]["population"]["value"], 11000)
        self.assertEqual(recs["Batu Pahat"]["population"]["year"], 2026)
        self.assertEqual(recs["Beaufort"]["population"]["value"], 8000)
        self.assertEqual(recs["Beaufort"]["population"]["year"], 2025)
        self.assertIn("(Membakut is new)", recs["Beaufort"]["population_note"])
        self.assertNotIn("Membakut", recs)
        self.assertFalse(recs["Batu Pahat"].get("population_note"))

    def test_the_new_districts_are_listed_in_a_sentence(self):
        self.assertEqual(m.new_districts(["Membakut"]), "Membakut is new")
        self.assertEqual(m.new_districts(["Gedong", "Lingga", "Pantu"]),
                         "Gedong, Lingga and Pantu are new")

    def test_the_indian_race_is_written_with_its_country(self):
        # A bare "Indian" is the nationality a European or Korean register
        # counts; DOSM's is Malaysia's own citizens of Indian descent.
        self.assertEqual(m.LABELS["indian"], "Indian (Malaysia)")


if __name__ == "__main__":
    unittest.main()
