"""Syria's 2004 census reader, on a two-district country built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import syria_census as sc  # noqa: E402
from scripts.fetch_census import west_asia_common as wac  # noqa: E402

GEO = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL", "NSO_CODE"]
AGES = [f"{a:02d}{a + 4:02d}" for a in range(0, 80, 5)]


def age_row(name, adm1, adm2, level, code, men_by_group, women_by_group):
    both = [m + w for m, w in zip(men_by_group, women_by_group)]
    row = [name, adm1, adm2, level, code, sum(both), sum(men_by_group), sum(women_by_group)]
    for prefix, values in (("B", both), ("M", men_by_group), ("F", women_by_group)):
        row += values
    return row


def age_sheet(rows):
    names = GEO + ["BTOTL", "MTOTL", "FTOTL"]
    for prefix in "BMF":
        names += [f"{prefix}{g}" for g in AGES] + [f"{prefix}80PL"]
    return [names, names] + rows


def groups(scale):
    return [scale * (17 - i) for i in range(17)]


def book(district_b_nat_other=0):
    m1, w1 = groups(10), groups(9)
    m2, w2 = groups(4), groups(5)
    tot = [a + b for a, b in zip(m1, m2)], [a + b for a, b in zip(w1, w2)]
    ages = age_sheet([
        age_row("SYRIA", None, None, 0, "SY", *tot),
        age_row("DIMASHQ", "DIMASHQ", None, 1, "SY01", *tot),
        age_row("DIMASHQ", "DIMASHQ", "DIMASHQ", 2, "SY0100", m1, w1),
        age_row("QATANA", "DIMASHQ", "QATANA", 2, "SY0108", m2, w2),
    ])
    t1, t2 = sum(m1) + sum(w1), sum(m2) + sum(w2)
    nat_names = GEO + [sc.NAT_TOTAL] + list(sc.NATIONALITY)
    zeros = [0] * (len(sc.NATIONALITY) - 2)

    def nat(total, palestinian, other=0):
        return [total, total - palestinian - other, palestinian] + zeros[:-1] + [other]
    ethnicity = [nat_names, nat_names,
                 ["SYRIA", None, None, 0, "SY"] + nat(t1 + t2, 30, district_b_nat_other),
                 ["DIMASHQ", "DIMASHQ", None, 1, "SY01"] + nat(t1 + t2, 30, district_b_nat_other),
                 ["DIMASHQ", "DIMASHQ", "DIMASHQ", 2, "SY0100"] + nat(t1, 20),
                 ["QATANA", "DIMASHQ", "QATANA", 2, "SY0108"] + nat(t2, 10, district_b_nat_other)]
    est_names = GEO + ["EST_POP11A", "EST_MAL11A", "EST_FEM11A"]
    est_alias = GEO + ["Both sexes population estimate, January 2011",
                       "Male population estimate, January 2011",
                       "Female population estimate, January 2011"]
    estimates = [est_names, est_alias,
                 ["SYRIA", None, None, 0, "SY", 3000, 1600, 1400],
                 ["DIMASHQ", "DIMASHQ", None, 1, "SY01", 3000, 1600, 1400]]
    return {"Metadata": [["Syria Population and Housing Census 2004"]], "Age-Sex": ages,
            "Ethnicity": ethnicity, "Population Estimates": estimates}


GAZ = {"syr_adm1": [["adm1_name", "adm1_pcode"], ["Damascus", "SY01"]],
       "syr_adm2": [["adm1_name", "adm2_name", "adm2_pcode"],
                    ["Damascus", "Damascus", "SY0100"], ["Damascus", "Qatana", "SY0108"]]}
ADMIN1 = [{"id": "g1", "name": "Damascus", "parent": "SYR"}]
ADMIN2 = [{"id": "d1", "name": "Damascus", "parent": "g1"},
          {"id": "d2", "name": "Qatana", "parent": "g1"}]


class TheReader(unittest.TestCase):
    def setUp(self):
        self.rows = sc.build(book(), GAZ, ADMIN1, ADMIN2, {"g1": "Damascus"})
        self.by = {r["shape_id"]: r for r in self.rows}

    def test_every_drawn_unit_is_bound_by_its_p_code(self):
        self.assertEqual(sorted(self.by), ["d1", "d2", "g1"])
        self.assertEqual(self.by["d2"]["codes"], {"pcode": "SY0108"})

    def test_districts_carry_the_census_and_the_governorate_the_estimate(self):
        self.assertEqual(self.by["d1"]["population"]["year"], 2004)
        self.assertEqual(self.by["g1"]["population"]["value"], 3000)
        self.assertEqual(self.by["g1"]["population"]["year"], 2011)

    def test_sex_ratio_is_men_per_hundred_women(self):
        ratio = self.by["d1"]["sex_ratio"]
        self.assertEqual(ratio["unit"], "males_per_100_females")
        self.assertAlmostEqual(ratio["value"], round(100 * 10 / 9, 1))

    def test_nationality_is_carried_as_ethnicity_and_says_so(self):
        d1 = self.by["d1"]
        self.assertEqual(d1["ethnicity_basis"], "nationality")
        groups = {g["group"]: g["count"] for g in d1["ethnicity"]}
        self.assertEqual(groups["Palestinian"], 20)
        self.assertIn("not ethnicity", d1["ethnicity_note"])

    def test_labels_name_no_people_the_census_did_not_count(self):
        labels = set(sc.NATIONALITY.values())
        self.assertIn("Syrian citizens", labels)
        # The continents' groups, never read as the US or Australia.
        self.assertFalse(labels & {"Syrian", "American", "Australian"})
        d1 = self.by["d1"]
        self.assertIn("Syrian citizens", {g["group"] for g in d1["ethnicity"]})
        self.assertIn("Kurd", d1["ethnicity_note"])

    def test_language_says_why_it_is_empty(self):
        for row in self.rows:
            self.assertEqual(row["language"]["status"], "not_available")
            self.assertIn("no language table", row["language"]["note"])

    def test_the_golan_districts_say_what_the_census_did_not_count(self):
        gaz = {"syr_adm1": [["adm1_name", "adm1_pcode"], ["Quneitra", "SY14"]],
               "syr_adm2": [["adm1_name", "adm2_name", "adm2_pcode"]]}
        self.assertIn("Golan", sc.GOLAN_NOTE)
        self.assertIn("SY1402", sc.GOLAN)
        del gaz

    def test_a_district_sum_that_misses_its_governorate_stops_the_run(self):
        broken = book()
        broken["Age-Sex"][5][5] += 1          # Qatana's total, not its groups
        with self.assertRaises(SystemExit):
            sc.build(broken, GAZ, ADMIN1, ADMIN2, {"g1": "Damascus"})

    def test_an_unbound_label_is_left_out_not_guessed(self):
        admin2 = ADMIN2 + [{"id": "d3", "name": "Nowhere", "parent": "g1"}]
        rows = sc.build(book(), GAZ, ADMIN1, admin2, {"g1": "Damascus"})
        self.assertNotIn("d3", {r["shape_id"] for r in rows})


class TinyGroups(unittest.TestCase):
    """Afrin's 172,095 people listed five foreign groups of 1 to 19 people."""

    COUNTS = {"Syrian citizens": 172055, "Asian nationalities": 19,
              "European nationalities": 3, "Other Arab nationalities": 5,
              "Other nationalities": 12, "Palestinian": 1, "Oceanian nationalities": 0}

    def test_groups_under_the_threshold_go_to_the_census_residual(self):
        out, moved = sc.folded(self.COUNTS, 172095)
        self.assertEqual(out, {"Syrian citizens": 172055, "Other nationalities": 40})
        self.assertEqual([k for k, _v in moved], ["Asian nationalities", "Other Arab nationalities",
                                                  "European nationalities", "Palestinian"])
        self.assertEqual(sum(out.values()), 172095)

    def test_a_group_at_or_over_the_threshold_keeps_its_bar(self):
        out, moved = sc.folded({"Syrian citizens": 9900, "Palestinian": 100}, 10000)
        self.assertEqual(out, {"Syrian citizens": 9900, "Palestinian": 100})
        self.assertEqual(moved, [])

    def test_the_note_names_what_was_moved_and_explains_only_what_is_shown(self):
        out, moved = sc.folded(self.COUNTS, 172095)
        nat = {"total": 172095, "counts": self.COUNTS}
        note = sc.nationality_note("SY0200", nat, 172095, moved)
        self.assertIn("Asian nationalities (19)", note)
        self.assertIn("Palestinian (1)", note)
        self.assertNotIn("refugees", note)       # no Palestinian bar is shown here
        self.assertNotIn("owner", note)
        self.assertNotIn("decision", note)


class TheHelpers(unittest.TestCase):
    def test_age_groups_must_run_without_a_gap(self):
        row = {"AREA_NAME": "x", "B0004": 1, "B1014": 1, "B15PL": 1}
        with self.assertRaises(SystemExit):
            wac.age_groups(row, "B")

    def test_age_groups_pick_one_year_of_several(self):
        row = {"AREA_NAME": "x", "B0004_6": 1, "B05PL_6": 2, "B0004_7": 3, "B05PL_7": 4}
        self.assertEqual(wac.age_groups(row, "B", "_7"), [(0, 4, 3.0), (5, None, 4.0)])

    def test_romanised_names_fold_together(self):
        self.assertEqual(wac.key("Al-Hasakeh"), wac.key("Al Hasakah"))
        self.assertEqual(wac.key("Ash Shaykh Badr"), wac.key("Sheikh Badr"))


if __name__ == "__main__":
    unittest.main()
