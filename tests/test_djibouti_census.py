"""Tests for the Djibouti 2024 census adapter (regions, and why the rest is empty), no network."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import djibouti_census as dc  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"

ROWS = [
    ("Ali-Sabieh", "Region", "76,414"), ("Ali-Adeh", "Sub-Prefecture", "16,847"),
    ("Ali-Sabieh ( Ali-Sabieh-Ville )", "City", "45,092"),
    ("Ali-Sabieh-Périphérique", "Sub-Prefecture", "3,564"),
    ("Holl-Holl", "Sub-Prefecture", "10,911"),
    ("Arta", "Region", "48,922"), ("Arta ( Arta-Ville )", "City", "11,462"),
    ("Arta-Périphérique", "Sub-Prefecture", "9,152"), ("Damerjog", "Sub-Prefecture", "22,877"),
    ("Karta", "Sub-Prefecture", "5,431"),
    ("Dikhil", "Region", "66,196"), ("As-Eyla", "Sub-Prefecture", "14,562"),
    ("Dikhil ( Dikhil-Ville )", "City", "27,722"),
    ("Dikhil-Périphérique", "Sub-Prefecture", "5,538"), ("Mouloud", "Sub-Prefecture", "5,203"),
    ("Yoboki", "Sub-Prefecture", "13,171"),
    ("Djibouti ( Djibouti-Ville )", "City", "767,250"), ("Balbala", "Commune", "547,129"),
    ("Boulaos", "Commune", "212,074"), ("Rasdika", "Commune", "8,047"),
    ("Obock", "Region", "47,382"), ("Allaili-Dadda", "Sub-Prefecture", "6,967"),
    ("Khor-Angar", "Sub-Prefecture", "3,267"), ("Obock ( Obock-Ville )", "City", "29,954"),
    ("Obock-Périphérique", "Sub-Prefecture", "7,194"),
    ("Tadjourah", "Region", "60,645"), ("Adayllou", "Sub-Prefecture", "5,708"),
    ("Dorra", "Sub-Prefecture", "15,601"), ("Lac-Assal", "Sub-Prefecture", "5,222"),
    ("Randa", "Sub-Prefecture", "8,601"),
    ("Tadjourah ( Tadjourah-Ville )", "City", "19,527"),
    ("Tadjourah-Périphérique", "Sub-Prefecture", "5,986"),
    ("Djibouti", "Republic", "1,066,809"),
]


def page(rows=ROWS):
    body = "".join(f"<tr><td>{n}</td><td>{s}</td><td>{p}</td><td>→</td></tr>" for n, s, p in rows)
    return ("<html><table><tr><th>Name</th><th>Status</th><th>Population Census 2024-05-20</th>"
            f"<th></th></tr>{body}</table><table><tr><td>Males</td><td>530,362</td></tr></table>"
            "</html>")


class ReadTableTest(unittest.TestCase):
    def test_six_regions_making_the_country(self):
        regions = dc.read_table(page())["regions"]
        self.assertEqual(len(regions), 6)
        self.assertEqual(regions["djibouti"]["total"], 767_250)
        self.assertEqual(regions["obock"]["total"], 47_382)

    def test_a_region_its_parts_do_not_make_stops_the_run(self):
        rows = [r if r[0] != "Karta" else ("Karta", "Sub-Prefecture", "5,451") for r in ROWS]
        with self.assertRaises(SystemExit):
            dc.read_table(page(rows))

    def test_a_wrong_national_row_stops_the_run(self):
        rows = ROWS[:-1] + [("Djibouti", "Republic", "1,076,525")]
        with self.assertRaises(SystemExit):
            dc.read_table(page(rows))


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.admin1 = json.loads((SITE / "admin1" / "DJI.units.json").read_text())
        self.admin2 = json.loads((SITE / "admin2" / "DJI.units.json").read_text())
        self.records = dc.build(dc.read_table(page()), self.admin1, self.admin2)

    def test_regions_carry_the_count_and_say_why_ages_are_missing(self):
        by = {r["name"]: r for r in self.records if r["level"] == "admin1"}
        self.assertEqual(by["Djibouti"]["population"]["value"], 767_250)
        self.assertIn("a region of its own", by["Djibouti"]["population_note"])
        self.assertEqual(by["Obock"]["population"]["year"], 2024)
        self.assertIn("country as a whole", by["Arta"]["median_age"]["note"])

    def test_second_level_units_say_why_but_ali_sabeh_keeps_its_figure(self):
        by = {r["name"]: r for r in self.records if r["level"] == "admin2"}
        self.assertEqual(len(by), len(self.admin2))
        self.assertIn("not established", by["Dorra"]["population"]["note"])
        self.assertNotIn("note", by["Ali Sabeh"]["population"])


if __name__ == "__main__":
    unittest.main()
