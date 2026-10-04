"""Israel's CBS Table 2.17, read from rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import israel_cbs as ic  # noqa: E402


def row(label, foreign, arabs, jews):
    israelis = round(arabs + jews, 1)
    return [label, foreign, arabs, jews, israelis, round(israelis + foreign, 1)]


SUBS = {
    "JERUSALEM DISTRICT": [],
    "NORTHERN DISTRICT": [("Zefat", 1.9, 14.4, 118.6), ("Kinneret", 1.9, 36.1, 86.9),
                          ("Yizre'el", 4.6, 299.2, 261.3), ("Akko", 3.1, 444.0, 240.9),
                          ("Golan(6)", 0.7, 27.4, 28.8)],
    "HAIFA DISTRICT": [("Haifa", 10.2, 76.8, 546.4), ("Hadera", 4.8, 205.8, 304.7)],
    "CENTRAL DISTRICT": [("Sharon", 10.2, 107.2, 395.6), ("Petah Tiqwa", 1.0, 10.0, 700.0),
                         ("Ramla", 1.0, 80.0, 300.0), ("Rehovot", 2.0, 2.0, 600.0)],
    "TEL AVIV DISTRICT": [],
    "SOUTHERN DISTRICT": [("Ashqelon", 2.0, 1.0, 600.0), ("Be'er Sheva", 5.0, 300.0, 500.0)],
}


def sheet():
    rows = [["TOTAL POPULATION", 0, 0, 0, 0, 0]]
    totals = [0.0, 0.0, 0.0]
    for district, subs in SUBS.items():
        if subs:
            f = round(sum(s[1] for s in subs), 1)
            a = round(sum(s[2] for s in subs), 1)
            j = round(sum(s[3] for s in subs), 1)
        elif district == "JERUSALEM DISTRICT":
            f, a, j = 52.4, 405.4, 840.4
        else:
            f, a, j = 30.0, 26.7, 1400.0
        totals = [totals[0] + f, totals[1] + a, totals[2] + j]
        rows.append(row(district, f, a, j))
        if district == "JERUSALEM DISTRICT":
            rows.append(row("   Judean Mountains", 49.2, 405.0, 652.7))
        for name, sf, sa, sj in subs:
            rows.append(row(f"   {name} S.D.", sf, sa, sj))
    rows[0] = row("TOTAL POPULATION(5)", *[round(t, 1) for t in totals])
    return {"ST02-17a": rows}


ADMIN1 = [{"id": f"d{i}", "name": n, "parent": "ISR"}
          for i, n in enumerate(["Jerusalem District", "Northern District", "Haifa",
                                 "Central District", "Tel Aviv", "Southern District"])]
PARENTS = {u["id"]: u["name"] for u in ADMIN1}
ADMIN2 = ([{"id": "s-jer", "name": "Jerusalem", "parent": "d0"}]
          + [{"id": f"s-{n}", "name": n, "parent": "d1"}
             for n in ("Zefat", "Kinneret", "Yizre'el", "Akko", "Golan")]
          + [{"id": f"s-{n}", "name": n, "parent": "d2"} for n in ("Haifa", "Hadera")]
          + [{"id": f"s-{n}", "name": n, "parent": "d3"}
             for n in ("HaSharon", "Petah Tiqwa", "Ramla", "Rehovot")]
          + [{"id": "s-ta", "name": "Tel Aviv", "parent": "d4"}]
          + [{"id": f"s-{n}", "name": n, "parent": "d5"} for n in ("Ashqelon", "Be'er Sheva")])


class TheReader(unittest.TestCase):
    def setUp(self):
        self.out = {r["shape_id"]: r for r in
                    ic.build(ic.read(sheet()), ADMIN1, ADMIN2, PARENTS)}

    def test_northern_district_leaves_the_golan_out(self):
        north = self.out["d1"]
        made = sum(1000 * (f + a + j) for n, f, a, j in SUBS["NORTHERN DISTRICT"]
                   if not n.startswith("Golan"))
        self.assertAlmostEqual(north["population"]["value"], made, delta=1)
        self.assertIn("other than the Golan", north["population"]["note"])

    def test_golan_and_jerusalem_say_why_they_are_empty(self):
        for sid in ("s-Golan", "s-jer", "d0"):
            self.assertEqual(self.out[sid]["population"]["status"], "not_available", sid)
        self.assertIn("Quneitra", self.out["s-Golan"]["population"]["note"])
        self.assertIn("East", self.out["d0"]["population"]["note"])

    def test_sub_districts_carry_population_groups(self):
        haifa = self.out["s-Haifa"]
        self.assertEqual(haifa["population"]["value"], round(1000 * (10.2 + 76.8 + 546.4)))
        groups = {s["group"] for s in haifa["ethnicity"]}
        self.assertEqual(groups, {"Foreign nationals", "Arabs", "Jews and others"})
        self.assertEqual(haifa["ethnicity_basis"], "population group")

    def test_tel_aviv_takes_the_district_row(self):
        self.assertEqual(self.out["s-ta"]["population"]["value"], round(1000 * 1456.7))

    def test_a_row_that_does_not_add_up_stops_the_run(self):
        broken = sheet()
        broken["ST02-17a"][3][5] += 1.0
        with self.assertRaises(SystemExit):
            ic.read(broken)


if __name__ == "__main__":
    unittest.main()
