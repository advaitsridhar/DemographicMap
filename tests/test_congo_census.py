"""The Republic of the Congo's 2023 departments and its second level's reasons (no network)."""

import unittest

from scripts.fetch_census import congo_census as cc

INDEX = ('<a href="/en/congo/admin/07__cuvette/">x</a>'
         '<a href="/en/congo/admin/cuvette/0711__bokoma/">y</a>'
         '<a href="https://www.citypopulation.de/en/congo/admin/03__lékoumou/">z</a>'
         '<a href="/en/congo/admin/l%C3%A9koumou/0302x__sibiti/">w</a>')
CUVETTE = ("<table><tr><th>Name</th><th>Status</th><th>Population Census 2023-05-17</th></tr>"
           "<tr><td><a href='x'>Cuvette</a></td><td>Department</td><td>316,599</td><td></td></tr>"
           "<tr><td>Bokoma</td><td>District</td><td>4,588</td></tr></table>"
           "<table><tr><td>Males</td><td>153,648</td></tr>"
           "<tr><td>Females</td><td>162,951</td></tr></table>")


class Pages(unittest.TestCase):
    def test_links_and_department(self):
        deps, districts = cc.links(INDEX)
        self.assertEqual(len(deps), 2)
        self.assertTrue(any(d.endswith("03__l%C3%A9koumou/") for d in deps))
        self.assertEqual(districts, 2)
        self.assertEqual(cc.department(CUVETTE),
                         {"name": "Cuvette", "total": 316_599, "men": 153_648, "women": 162_951})

    def test_build(self):
        found = [cc.department(CUVETTE)]
        admin1 = [{"id": "C", "name": "Cuvette"}]
        sid = "1427508B80151114352270"
        admin2 = [{"id": sid, "name": "Zanaga", "parent": "B"}]
        records, report = cc.build(found, 92, admin1, admin2, {"Cuvette": "https://x"})
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Cuvette"]["sex_ratio"]["value"], round(1000 * 153_648 / 162_951))
        note = by["Zanaga"]["population"]["note"]
        self.assertIn("Brazzaville (Brazzaville)", note)
        self.assertIn("92 districts and communes", note)
        # Polygons no longer drawn as measured are left out and said.
        self.assertTrue(any("no longer drawn" in line for line in report))

    def test_notes(self):
        self.assertIn("holds the town of that name",
                      cc.town_note("Mossendjo", (("Mossendjo", "Niari"),), 90))
        self.assertIn("no town", cc.town_note("Boundji", (), 90))


if __name__ == "__main__":
    unittest.main()
