import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import uzbekistan_siat as uz  # noqa: E402


def unit(code, en, uz_name, series):
    return {"Code": code, "Klassifikator_en": en, "Klassifikator": uz_name,
            **{str(2020 + i): v for i, v in enumerate(series)}}


REGION = unit("1710", "Kashkadarya region", "Qashqadaryo viloyati", [100, 101, 102, 103])
SHAPES = {"Qashqadaryo Region": [
    {"id": "a", "name": "Chirakchi"}, {"id": "b", "name": "Kasbi"},
    {"id": "c", "name": "Guzar"}, {"id": "d", "name": "Balikchi"}]}


class Names(unittest.TestCase):
    def test_romanisations_fold_together(self):
        self.assertEqual(uz.key("Balykchi district"), uz.key("Balikchi"))
        self.assertEqual(uz.key("Jalаquduk district"), uz.key("Jalaquduk"))  # Cyrillic а
        self.assertEqual(uz.key("Khatyrchi district"), uz.key("Xatirchi tumani"))

    def test_a_city_is_not_its_district(self):
        rows, _ = uz.build([REGION, unit("1710401", "Chirakchi city", "Chiroqchi shahri",
                                         [1, 1, 1, 1])], SHAPES)
        self.assertEqual([r for r in rows if r["level"] == "admin2"], [])


class CarvedOut(unittest.TestCase):
    def test_a_sole_source_carries_its_new_unit(self):
        data = [REGION,
                unit("1710201", "Chirakchi district", "Chiroqchi tumani", [400, 405, 230, 235]),
                unit("1710240", "Kukdala district", "Ko'kdala tumani", [0, 0, 180, 185])]
        rows, notes = uz.build(data, SHAPES)
        chirakchi = next(r for r in rows if r["name"] == "Chirakchi")
        self.assertEqual(chirakchi["population"]["value"], 420_000)
        self.assertIn("Kukdala", chirakchi["population"]["note"])

    def test_several_sources_each_take_the_year_before(self):
        # Kegeyli and Chimbay both gave ground to Bozatau: each is drawn as it
        # was, and the agency's figure for the year before is that ground.
        data = [REGION,
                unit("1710201", "Chirakchi district", "Chiroqchi tumani", [400, 405, 330, 335]),
                unit("1710202", "Kasbi district", "Kasbi tumani", [300, 305, 230, 232]),
                unit("1710240", "Kukdala district", "Ko'kdala tumani", [0, 0, 150, 152])]
        rows, _ = uz.build(data, SHAPES)
        for name, value in (("Chirakchi", 405_000), ("Kasbi", 305_000)):
            row = next(r for r in rows if r["name"] == name)
            self.assertEqual(row["population"]["value"], value)
            self.assertEqual(row["population"]["year"], 2021)
            self.assertIn("Kukdala", row["population"]["note"])
            self.assertIn("1 January 2021", row["population"]["note"])
            # No age tables: the medians say why they are empty.
            self.assertIn("age tables", row["median_age"]["note"])

    def test_the_year_before_takes_that_year_s_ages(self):
        data = [REGION,
                unit("1710201", "Chirakchi district", "Chiroqchi tumani", [3.0, 2.1, 1.5, 1.52]),
                unit("1710202", "Kasbi district", "Kasbi tumani", [3.0, 2.0, 1.4, 1.42]),
                unit("1710240", "Kukdala district", "Ko'kdala tumani", [0, 0, 1.2, 1.21])]
        tables = merge(age_rows("1710201", WOMEN, MEN, "2021"),
                       age_rows("1710201", WOMEN, MEN, "2023"))
        # One row per unit and table, every year a key on it.
        for ident, rows_ in tables.items():
            merged = {}
            for row in rows_:
                merged.update(row)
            tables[ident] = [merged]
        rows, _ = uz.build(data, SHAPES, age_tables=tables)
        chirakchi = next(r for r in rows if r["name"] == "Chirakchi")
        self.assertEqual(chirakchi["median_age"]["year"], 2021)
        self.assertEqual(chirakchi["sex_ratio"]["value"], round(100 * 1040 / 1060, 1))
        self.assertIn("Kukdala", chirakchi["median_age_note"])

    def test_a_district_touched_twice_is_left_blank_and_displaces(self):
        data = [REGION,
                unit("1710201", "Chirakchi district", "Chiroqchi tumani", [400, 330, 260, 262]),
                unit("1710202", "Kasbi district", "Kasbi tumani", [300, 230, 160, 162]),
                unit("1710240", "Kukdala district", "Ko'kdala tumani", [0, 140, 141, 142]),
                unit("1710241", "Newdala district", "Yangi tumani", [0, 0, 140, 141])]
        rows, _ = uz.build(data, SHAPES)
        chirakchi = next(r for r in rows if r["name"] == "Chirakchi")
        self.assertNotIn("value", chirakchi["population"])
        self.assertIn("Kukdala", chirakchi["population"]["note"])
        self.assertIn("Newdala", chirakchi["population"]["note"])
        self.assertEqual(chirakchi["population"]["displaces_before"], uz.DISPLACES_BEFORE)
        self.assertIs(chirakchi["population"]["displaces_undated"], True)

    def test_an_undrawn_city_on_a_border_blanks_both_and_displaces(self):
        region = unit("1724", "Syrdarya region", "Sirdaryo viloyati", [800, 801, 802, 803])
        shapes = {"Sirdaryo Region": [{"id": "k", "name": "Khavas"}],
                  "Tashkent Region": [{"id": "b", "name": "Bekabad"}]}
        data = [region, unit("1727", "Tashkent region", "Toshkent viloyati", [9, 9, 9, 9]),
                unit("1724410", "Shirin city", "Shirin shahri", [18, 18, 19, 19]),
                unit("1724213", "Khavas district", "Xovos tumani", [80, 81, 82, 83]),
                unit("1727220", "Bekabad district", "Bekobod tumani", [150, 152, 154, 156])]
        rows, _ = uz.build(data, shapes)
        for name in ("Khavas", "Bekabad"):
            row = next(r for r in rows if r["name"] == name)
            self.assertNotIn("value", row["population"])
            self.assertIn("Shirin", row["population"]["note"])
            self.assertEqual(row["population"]["displaces_before"], uz.DISPLACES_BEFORE)
            self.assertIs(row["population"]["displaces_undated"], True)
        for row in rows:
            self.assertNotIn("October", row["ethnicity"]["note"])


def age_rows(code, women, men, year="2026"):
    """One unit's fourteen groups for each sex, as the agency's tables hold them."""
    tables = {}
    for (_, _, w_id, m_id), w, m in zip(uz.AGE_GROUPS, women, men):
        tables.setdefault(w_id, []).append({"Code": code, year: w})
        tables.setdefault(m_id, []).append({"Code": code, year: m})
    return tables


def merge(*parts):
    out = {}
    for part in parts:
        for ident, rows in part.items():
            out.setdefault(ident, []).extend(rows)
    return out


WOMEN = [60, 60, 40, 160, 40, 40, 100, 100, 100, 80, 120, 80, 30, 50]   # 1,060
MEN = [64, 62, 42, 168, 42, 41, 101, 98, 96, 76, 112, 72, 26, 40]        # 1,040


class Ages(unittest.TestCase):
    def test_profiles_take_the_newest_shared_year(self):
        tables = age_rows("1710201", WOMEN, MEN)
        tables[uz.AGE_GROUPS[0][2]][0]["2025"] = 1
        year, profiles = uz.age_profiles(tables)
        self.assertEqual(year, "2026")
        self.assertEqual(sum(n for *_, n in profiles["1710201"]["women"]), 1060)

    def test_median_and_ratio(self):
        _, profiles = uz.age_profiles(age_rows("1710201", WOMEN, MEN))
        fields = uz.age_fields(profiles["1710201"], "2026", 2100, "Chirakchi")
        self.assertEqual(fields["sex_ratio"]["value"], round(100 * 1040 / 1060, 1))
        # 2,100 people: the 1,050th lies in 25-29 (1,020 before it, 198 in it).
        self.assertEqual(fields["median_age"]["value"], round(25 + 30 / 198 * 5, 1))
        self.assertIn("25-29", fields["median_age_note"])

    def test_a_population_far_from_the_groups_stops_the_run(self):
        _, profiles = uz.age_profiles(age_rows("1710201", WOMEN, MEN))
        with self.assertRaises(SystemExit):
            uz.age_fields(profiles["1710201"], "2026", 2400, "Chirakchi")

    def test_two_units_are_added_group_by_group(self):
        _, profiles = uz.age_profiles(merge(age_rows("1", WOMEN, MEN), age_rows("2", WOMEN, MEN)))
        both = uz.summed([profiles["1"], profiles["2"]])
        self.assertEqual(sum(n for *_, n in both["men"]), 2080)
        self.assertEqual(both["women"][0][2], 120)

    def test_build_writes_ages_on_bound_districts_and_regions(self):
        region = unit("1710", "Kashkadarya region", "Qashqadaryo viloyati", [2.0, 2.0, 2.1, 2.1])
        data = [region, unit("1710201", "Chirakchi district", "Chiroqchi tumani", [2.0, 2.0, 2.1, 2.1])]
        tables = merge(age_rows("1710", WOMEN, MEN, "2023"), age_rows("1710201", WOMEN, MEN, "2023"))
        rows, _ = uz.build(data, SHAPES, ages=uz.age_profiles(tables),
                           region_ids={"Qashqadaryo Region": "R1"})
        district = next(r for r in rows if r["level"] == "admin2")
        self.assertEqual(district["shape_id"], "a")
        self.assertEqual(district["match_by"], "shape_id")
        self.assertIn("value", district["median_age"])
        region = next(r for r in rows if r["level"] == "admin1")
        self.assertEqual(region["shape_id"], "R1")
        self.assertIn("value", region["sex_ratio"])
        # Compositions are gaps that say what was searched.
        for row in (district, region):
            self.assertIn("SIAT", row["ethnicity"]["note"])
            self.assertIn("religion", row["religion"]["note"])


if __name__ == "__main__":
    unittest.main()
