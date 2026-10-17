"""Tests for the Kenya 2019 census adapter (counties and constituencies), no network."""

import csv
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import kenya_census as kc  # noqa: E402
from scripts.fetch_census.binding import fold  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"


def unit_rows(county, sub, per_age, unstated=0):
    """Volume III rows for one unit: single years 0-99, 100+, not stated and total."""
    rows = []
    for age, n in enumerate(per_age[:100]):
        rows.append([county, sub, str(age), n // 2, n - n // 2, n])
    rows.append([county, sub, "100+", per_age[100] // 2, per_age[100] - per_age[100] // 2,
                 per_age[100]])
    rows.append([county, sub, "Not Stated", unstated // 2, unstated - unstated // 2, unstated])
    male = sum(n // 2 for n in per_age) + unstated // 2
    total = sum(per_age) + unstated
    rows.append([county, sub, "Total", male, total - male, total])
    return rows


def ages(young, old=0):
    """101 single-year counts: `young` people a year to 39, `old` from 40."""
    return [young if a < 40 else old for a in range(101)]


def table(units):
    """Volume III text from {(county, sub): per_age}, with each county's ALL rows."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["County", "Sub-County", "Age", "Male", "Female", "Total"])
    counties = {}
    for (county, sub), per_age in units.items():
        acc = counties.setdefault(county, [0] * 101)
        for i, n in enumerate(per_age):
            acc[i] += n
    for county, per_age in counties.items():
        for row in unit_rows(county, "ALL", per_age):
            w.writerow(row)
        for (c, sub), sub_ages in units.items():
            if c == county:
                for row in unit_rows(c, sub, sub_ages):
                    w.writerow(row)
    return out.getvalue()


def vol1_row(name, vol3_entry, intersex=0):
    a = vol3_entry["all"]
    return {"name": name, "male": a["male"], "female": a["female"], "intersex": intersex,
            "total": a["total"] + intersex}


class ReadVol3Test(unittest.TestCase):
    def test_single_years_sexes_and_totals_are_read(self):
        vol3 = kc.read_vol3(table({("KERICHO", "BURETI"): ages(10), ("KERICHO", "BELGUT"): ages(20)}))
        entry = vol3["kericho"]
        self.assertEqual(entry["all"]["total"], 30 * 40)
        self.assertTrue(entry["subs_ok"])
        self.assertTrue(entry["subs"]["bureti"]["ages_ok"])
        self.assertEqual(entry["subs"]["belgut"]["total"], 20 * 40)

    def test_a_name_with_a_comma_spills_and_is_rejoined(self):
        text = table({("NYERI", "TETU"): ages(4)})
        text = text.replace("NYERI,TETU,", "NYERI,TETU, WEST,")
        vol3 = kc.read_vol3(text)
        self.assertIn(fold("TETU, WEST"), vol3["nyeri"]["subs"])

    def test_a_date_in_a_single_year_row_leaves_the_ages_out(self):
        text = table({("NYERI", "TETU"): ages(4)})
        text = text.replace("NYERI,TETU,15,2,2,4", "NYERI,TETU,15,15-Aug,2,4")
        unit = kc.read_vol3(text)["nyeri"]["subs"]["tetu"]
        self.assertFalse(unit["ages_ok"])

    def test_five_year_rows_are_not_read(self):
        text = table({("NYERI", "TETU"): ages(4)})
        text += "NYERI,TETU,10 -14,15-Aug,x,y\n"
        self.assertTrue(kc.read_vol3(text)["nyeri"]["subs"]["tetu"]["ages_ok"])

    def test_a_few_people_short_are_taken_as_unstated(self):
        text = table({("KWALE", "MATUGA"): ages(400)})
        # The county's total says twelve more people than its single years make.
        text = text.replace("KWALE,ALL,Total,8000,8000,16000", "KWALE,ALL,Total,8006,8006,16012")
        entry = kc.read_vol3(text)["kwale"]
        self.assertTrue(entry["all"]["ages_ok"])
        self.assertEqual(entry["all"]["unstated"], 12)


class CountyRecordsTest(unittest.TestCase):
    def setUp(self):
        self.vol3 = kc.read_vol3(table({
            ("KERICHO", "BURETI"): ages(10, 2), ("KERICHO", "BELGUT"): ages(30),
            ("BOMET", "SOTIK"): ages(20, 4)}))
        self.vol1 = {"kericho": vol1_row("Kericho", self.vol3["kericho"], intersex=3),
                     "bomet": vol1_row("Bomet", self.vol3["bomet"], intersex=1)}
        self.admin1 = [{"id": "K1", "name": "Kericho"}, {"id": "B1", "name": "Bomet"}]

    def test_a_moved_sub_county_is_added_to_one_polygon_and_taken_from_the_other(self):
        records, shape_of = kc.county_records(self.vol1, self.vol3, self.admin1)
        by = {r["name"]: r for r in records}
        bureti = self.vol3["kericho"]["subs"]["bureti"]["total"]
        self.assertEqual(by["Bomet"]["population"]["value"], self.vol1["bomet"]["total"] + bureti)
        self.assertEqual(by["Kericho"]["population"]["value"],
                         self.vol1["kericho"]["total"] - bureti)
        self.assertIn("Bureti sub-county of Kericho County", by["Bomet"]["population_note"])
        self.assertIn("less Bureti sub-county", by["Kericho"]["population_note"])
        self.assertIn("3 intersex persons", by["Kericho"]["population_note"])
        self.assertEqual(shape_of, {"K1": "kericho", "B1": "bomet"})
        # Kericho without Bureti is Belgut alone: 30 a year to 39, so the middle
        # person is 20 years into the run.
        self.assertEqual(by["Kericho"]["median_age"]["value"], 20.0)
        self.assertIn("without Bureti", by["Kericho"]["median_age_note"])

    def test_without_a_move_the_county_is_its_own_count(self):
        with mock.patch.object(kc, "MOVED", {}):
            records, _ = kc.county_records(self.vol1, self.vol3, self.admin1)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Kericho"]["population"]["value"], self.vol1["kericho"]["total"])
        self.assertEqual(by["Kericho"]["population_note"],
                         "The 2019 census's count of everyone in the county, 3 intersex persons "
                         "included.")
        self.assertEqual(by["Bomet"]["sex_ratio"]["unit"], "males_per_1000_females")


class ConstituencyTest(unittest.TestCase):
    def setUp(self):
        self.vol3 = kc.read_vol3(table({
            ("KERICHO", "BURETI"): ages(10), ("KERICHO", "KIPKELION"): ages(30),
            ("BOMET", "SOTIK"): ages(20), ("BOMET", "BOMET EAST"): ages(6),
            ("BOMET", "KONOIN"): ages(8), ("BOMET", "MAU FOREST"): ages(2, 0)}))
        self.vol1 = {"kericho": vol1_row("Kericho", self.vol3["kericho"]),
                     "bomet": vol1_row("Bomet", self.vol3["bomet"])}
        self.admin1 = [{"id": "K1", "name": "Kericho"}, {"id": "B1", "name": "Bomet"}]
        self.admin2 = [{"id": "c1", "name": "Buret", "parent": "B1"},
                       {"id": "c2", "name": "Bomet East", "parent": "B1"},
                       {"id": "c3", "name": "Konoin", "parent": "B1"},
                       {"id": "c4", "name": "Kipkelion West", "parent": "K1"},
                       {"id": "c5", "name": "Sotik", "parent": "B1"}]
        self.crosswalk = {"bomet": {"Buret": ["kericho/bureti"], "Bomet East": ["bometeast"],
                                    "Sotik": ["sotik", "konoin"]},
                          "kericho": {"Kipkelion West": ["kipkelion"]}}

    def build(self):
        with mock.patch.object(kc, "CROSSWALK", self.crosswalk):
            _, shape_of = kc.county_records(self.vol1, self.vol3, self.admin1)
            plans, report = kc.constituency_plans(self.vol3, self.admin2, shape_of)
            records = kc.constituency_records(self.vol3, self.admin2, shape_of, plans)
        return {r["name"]: r for r in records}, report

    def test_crosswalk_entries_are_written_and_the_rest_say_why(self):
        by, report = self.build()
        self.assertEqual(by["Buret"]["population"]["value"], 400)
        self.assertEqual(by["Buret"]["population_note"],
                         "The 2019 census's count for Bureti sub-county of Kericho County, which "
                         "is this constituency's ground.")
        self.assertEqual(by["Bomet East"]["population_note"],
                         "The 2019 census's count for Bomet East sub-county.")
        self.assertEqual(by["Kipkelion West"]["population_note"],
                         "The 2019 census's count for Kipkelion sub-county, which is this "
                         "constituency's ground.")
        self.assertEqual(by["Sotik"]["population"]["value"], 1120)
        self.assertIn("Sotik and Konoin, added up", by["Sotik"]["population_note"])
        self.assertIn("of its sub-counties together", by["Sotik"]["median_age_note"])
        konoin = by["Konoin"]["population"]
        self.assertEqual(konoin["status"], "not_available")
        self.assertIn("cannot be shown to be one sub-county", konoin["note"])
        self.assertTrue(any("3 of 4 constituencies" in line for line in report))

    def test_a_crosswalk_naming_no_constituency_stops_the_run(self):
        self.crosswalk["bomet"]["Chepalungu"] = ["sotik"]
        with self.assertRaises(SystemExit):
            self.build()

    def test_a_crosswalk_naming_no_sub_county_stops_the_run(self):
        self.crosswalk["bomet"]["Konoin"] = ["konoinnorth"]
        with self.assertRaises(SystemExit):
            self.build()

    def test_same_names_making_the_county_partition_it(self):
        self.crosswalk = {}
        self.admin2 = [{"id": "k1", "name": "Bureti", "parent": "K1"},
                       {"id": "k2", "name": "Kipkelion", "parent": "K1"}]
        with mock.patch.object(kc, "MOVED", {}):
            by, report = self.build()
        self.assertEqual(by["Kipkelion"]["population"]["value"], 1200)
        self.assertTrue(any("sub-counties of the same names" in line for line in report))


class CrosswalkDataTest(unittest.TestCase):
    """The crosswalk and the moves name real constituencies of the right counties."""

    def test_every_label_is_a_constituency_of_its_county(self):
        admin1 = json.loads((SITE / "admin1" / "KEN.units.json").read_text())
        admin2 = json.loads((SITE / "admin2" / "KEN.units.json").read_text())
        county_id = {fold(u["name"]): u["id"] for u in admin1}
        for key, label in kc.COUNTY_ALIASES.items():
            county_id[key] = county_id[fold(label)]
        under = {}
        for u in admin2:
            under.setdefault(u["parent"], set()).add(u["name"].strip())
        for county, entries in kc.CROSSWALK.items():
            self.assertIn(county, county_id, county)
            for label, refs in entries.items():
                self.assertIn(label, under[county_id[county]], f"{county}: {label}")
                self.assertTrue(refs and all(r == fold(r.split("/")[-1]) or "/" in r
                                             for r in refs), f"{county}: {label}")

    def test_no_sub_county_is_taken_twice(self):
        seen = {}
        for county, entries in kc.CROSSWALK.items():
            for label, refs in entries.items():
                for ref in refs:
                    key = ref if "/" in ref else f"{county}/{ref}"
                    self.assertNotIn(key, seen, f"{label} and {seen.get(key)}")
                    seen[key] = label

    def test_moves_point_at_a_crosswalk_entry_of_the_receiving_county(self):
        for (home, sub), into in kc.MOVED.items():
            self.assertIn(f"{home}/{sub}", [r for refs in kc.CROSSWALK[into].values()
                                             for r in refs])


class TitleTest(unittest.TestCase):
    def test_capitals_become_names(self):
        self.assertEqual(kc.title("MUKURWE-INI"), "Mukurwe-ini")
        self.assertEqual(kc.title("MURANG'A SOUTH"), "Murang'a South")
        self.assertEqual(kc.title("TRANS NZOIA WEST"), "Trans Nzoia West")


if __name__ == "__main__":
    unittest.main()
