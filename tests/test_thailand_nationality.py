"""Thailand: Thai and foreign nationals by province, 2000 census.

No network: Table 1 is built here in the Office's HTML layout, and the
provinces' printed rows are patched in.
"""

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from scripts.fetch_census import thailand_nationality as t

PRINTED = {
    "Ranong": ("ranongfn.pdf", "20210420233828", 161.2, 93.4, 88.5),
    "Nong Khai": ("nongkaifn.pdf", "20210420233836", 883.7, 99.5, 98.9),
}


def page(ranong=161_210, nong_khai=883_704, total=None, extra=""):
    total = total if total is not None else ranong + nong_khai
    rows = [("Changwat and area", "Population"), ("Total", f"{total:,}"),
            ("Municipal Area", "1,000"), ("Southern Region", f"{ranong:,}"),
            ("Ranong", f"{ranong:,}"), ("Municipal Area", "100"),
            ("Northeastern Region", f"{nong_khai:,}"), ("Nong Khai", f"{nong_khai:,}")]
    cells = "".join(f"<tr><td>{a}</td><td>{b}</td><td>x</td></tr>" for a, b in rows)
    return f"<html><table>{cells}{extra}</table></html>".encode()


class Table1Test(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.multiple(t, PRINTED=PRINTED, KINGDOM=161_210 + 883_704)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reads_every_province(self):
        self.assertEqual(t.table1(page()), {"Ranong": 161_210, "Nong Khai": 883_704})

    def test_provinces_off_the_kingdom_refuse(self):
        with self.assertRaises(SystemExit):
            t.table1(page(total=1_000_000))

    def test_a_province_missing_refuses(self):
        body = page().replace(b"<td>Nong Khai</td>", b"<td>Nongkhai</td>")
        with self.assertRaises(SystemExit):
            t.table1(body)

    def test_a_province_twice_refuses(self):
        with self.assertRaises(SystemExit):
            t.table1(page(extra="<tr><td>Ranong</td><td>1</td></tr>"))


class CheckTest(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(t, "PRINTED", PRINTED)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.counts = {"Ranong": 161_210, "Nong Khai": 883_704}

    def test_agreeing_rows_pass(self):
        t.check(self.counts, {"ranong": 88.5, "nongkhai": 98.9})

    def test_a_population_read_from_another_report_refuses(self):
        with self.assertRaises(SystemExit):
            t.check({**self.counts, "Ranong": 162_310}, {})

    def test_a_buddhist_share_the_other_reading_does_not_give_refuses(self):
        with self.assertRaises(SystemExit):
            t.check(self.counts, {"ranong": 88.3})

    def test_buddhists_are_read_under_every_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thailand_province.json"
            path.write_text(json.dumps([{"name": "Buri Ram Province", "aliases": ["Buriram"],
                                         "religion": [{"group": "Buddhism", "pct": 99.4}]}]))
            got = t.buddhists(path)
        self.assertEqual(got, {"buriram": 99.4})


class BuildTest(unittest.TestCase):
    ADMIN1 = [{"id": "R", "name": "Ranong Province"}, {"id": "N", "name": "Nong Khai Province"},
              {"id": "B", "name": "Bueng Kan Province"}]

    def build(self, admin1=None):
        with unittest.mock.patch.object(t, "PRINTED", PRINTED):
            return {r["shape_id"]: r for r in t.build(admin1 or self.ADMIN1)}

    def test_records(self):
        recs = self.build()
        eth = {g["group"]: g["pct"] for g in recs["R"]["ethnicity"]}
        self.assertEqual(eth, {"Thai": 93.4, "Foreign, stateless or unknown": 6.6})
        self.assertEqual(recs["R"]["ethnicity_basis"], "nationality")
        self.assertEqual(recs["R"]["ethnicity_year"], 2000)
        self.assertIn("ranongfn.pdf", recs["R"]["sources"][0]["url"])
        self.assertEqual(recs["R"]["match_by"], "shape_id")

    def test_the_residual_says_it_holds_the_people_of_no_nationality(self):
        note = self.build()["R"]["ethnicity_note"]
        self.assertIn("people of none", note)
        self.assertIn("not recorded", note)
        self.assertNotIn("owner", note)

    def test_the_residual_label_is_placed_among_the_answers_naming_no_ancestry(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        import group_tree
        chain, label = [], t.LABELS[1]
        while label:
            chain.append(label)
            label = group_tree.parent_of("ethnicity", label)
        self.assertEqual(chain[-1], "Other or not stated ancestry")
        self.assertNotIn("Thai", chain[1:])

    def test_nong_khai_says_bueng_kan_is_inside_and_bueng_kan_says_why_it_is_empty(self):
        recs = self.build()
        self.assertIn("Bueng Kan included", recs["N"]["ethnicity_note"])
        self.assertNotIn("Bueng Kan", recs["R"]["ethnicity_note"])
        self.assertEqual(recs["B"]["ethnicity"]["status"], "not_available")
        self.assertIn("carved out of Nong Khai in 2011", recs["B"]["ethnicity"]["note"])

    def test_a_polygon_without_a_report_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(self.ADMIN1 + [{"id": "X", "name": "Atlantis Province"}])

    def test_a_report_without_a_polygon_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(self.ADMIN1[:1])


class PrintedTest(unittest.TestCase):
    def test_every_province_of_2000_once(self):
        self.assertEqual(len(t.PRINTED), 76)
        self.assertEqual(len({v[0] for v in t.PRINTED.values()}), 76)
        for name, (report, capture, thousands, thai, buddhism) in t.PRINTED.items():
            self.assertTrue(report.endswith(".pdf"), name)
            self.assertRegex(capture, r"^\d{14}$")
            self.assertTrue(100 < thousands < 7000, name)
            self.assertTrue(90 <= thai <= 100 and 0 < buddhism <= 100, name)

    def test_ranong_is_its_workbooks_figure(self):
        self.assertEqual(t.PRINTED["Ranong"][3], 93.4)


if __name__ == "__main__":
    unittest.main()
