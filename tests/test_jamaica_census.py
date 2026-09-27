"""Jamaica's 2022 community table: read, checked against its parishes, bound with care."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import jamaica_census as jc  # noqa: E402

PAGE = """<table><tr><th>Parish</th><th>Community</th><th>Total Population</th>
<th>Number of Dwellings</th></tr>
<tr><td>Kingston</td><td>- Kingston Communities</td><td>1,000</td><td>400</td></tr>
<tr><td>Kingston</td><td>Tivoli Gardens</td><td>600</td><td>200</td></tr>
<tr><td>Kingston</td><td>Rae Town</td><td>401</td><td>200</td></tr>
<tr><td>St.Elizabeth</td><td>- St.Elizabeth Communities</td><td>500</td><td>100</td></tr>
<tr><td>St. Elizabeth</td><td>Warminster</td><td>300</td><td>60</td></tr>
<tr><td>St.Elizabeth</td><td>Pepper Part 1</td><td>200</td><td>40</td></tr>
</table>"""

ADMIN1 = [{"id": "K", "name": "Kingston", "bbox": [-77.0, 17.9, -76.7, 18.0]},
          {"id": "E", "name": "Saint Elizabeth", "bbox": [-78.0, 17.8, -77.5, 18.3]},
          {"id": "W", "name": "Westmoreland", "bbox": [-78.4, 18.0, -77.9, 18.4]}]
ADMIN2 = [{"id": "a", "name": "Tivoli Gardens", "parent": "K", "point": [-76.8, 17.97]},
          {"id": "b", "name": "Rae Town", "parent": "K", "point": [-76.78, 17.96]},
          {"id": "c", "name": "Warminister", "parent": "E", "point": [-77.7, 18.1]},
          {"id": "d", "name": "Pepper", "parent": "E", "point": [-77.8, 18.0]}]


class Table(unittest.TestCase):
    def test_rows_are_gathered_by_parish_however_statin_spells_it(self):
        table = jc.communities(jc.table_rows(PAGE))
        self.assertEqual(sorted(table), ["kingston", "saintelizabeth"])
        self.assertEqual(table["saintelizabeth"]["total"], 500)
        self.assertEqual(len(table["saintelizabeth"]["communities"]), 2)

    def test_a_parish_far_from_its_subtotal_is_refused(self):
        with self.assertRaises(SystemExit):
            jc.communities(jc.table_rows(PAGE.replace("401", "480")))

    def test_the_parish_page_must_make_its_total(self):
        rows = [["Parish", "Total Population 2022", "Total Population 2011"],
                ["Kingston & St. Andrew", "700", "1"], ["St. Thomas", "300", "1"],
                ["Total", "1,000", "2"]]
        page, national = jc.parish_page(rows)
        self.assertEqual(page, {"kingston & saintandrew": 700, "saintthomas": 300})
        rows[-1][1] = "1,200"
        with self.assertRaises(SystemExit):
            jc.parish_page(rows)


class Binding(unittest.TestCase):
    def test_same_name_and_shared_spellings_bind_and_the_rest_is_left_out(self):
        table = jc.communities(jc.table_rows(PAGE))
        bound, left = jc.bind(table, ADMIN1, ADMIN2)
        self.assertEqual({k: v["id"] for k, v in bound.items()},
                         {("Kingston", "Tivoli Gardens"): "a", ("Kingston", "Rae Town"): "b",
                          ("St.Elizabeth", "Warminster"): "c"})
        self.assertTrue(any("Pepper Part 1" in line for line in left))

    def test_a_count_far_from_the_2012_estimate_is_not_the_same_ground(self):
        table = jc.communities(jc.table_rows(PAGE))
        bound, _ = jc.bind(table, ADMIN1, ADMIN2)
        people = {(e["label"], n): v for e in table.values() for n, v in e["communities"]}
        before = {("kingston", "tivoligardens"): 610, ("kingston", "raetown"): 150,
                  # the outline's spelling, which is how the 2012 list writes it
                  ("saintelizabeth", "warminister"): 320}
        kept, dropped = jc.steady(bound, people, before)
        self.assertEqual(sorted(k[1] for k in kept), ["Tivoli Gardens", "Warminster"])
        self.assertEqual(len(dropped), 1)
        self.assertIn("Rae Town", dropped[0])

    def test_names_written_with_st_and_mt_are_one_key(self):
        self.assertEqual(jc.community_key("St. Paul's"), jc.community_key("Saint Pauls"))
        self.assertEqual(jc.community_key("Mt. Salem"), jc.community_key("Mount Salem"))
        self.assertEqual(jc.parish_key("St.Thomas"), jc.parish_key("Saint Thomas"))


if __name__ == "__main__":
    unittest.main()
