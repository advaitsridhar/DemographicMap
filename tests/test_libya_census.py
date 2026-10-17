"""Libya's 2006 census reader: the 22 shabiyat, their checks and their polygons."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import libya_census as lc  # noqa: E402

BANDS = [(0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 34), (35, 39), (40, 44),
         (45, 49), (50, 54), (55, 59), (60, 64), (65, 69), (70, 74), (75, 79), (80, 84)]


def header():
    names = ["AREA_NAME", "ADM1_NAME", "ADM_LEVEL", "BTOTL", "MTOTL", "FTOTL"]
    for sex in "BMF":
        names += [f"{sex}{lo:02d}{hi:02d}" for lo, hi in BANDS] + [f"{sex}85PL"]
    return names


def row(names, name, shabiyah, level, per_band_m, per_band_f):
    m = [per_band_m] * (len(BANDS) + 1)
    f = [per_band_f] * (len(BANDS) + 1)
    b = [x + y for x, y in zip(m, f)]
    values = {"AREA_NAME": name, "ADM1_NAME": shabiyah, "ADM_LEVEL": level,
              "BTOTL": sum(b), "MTOTL": sum(m), "FTOTL": sum(f)}
    for sex, series in (("B", b), ("M", m), ("F", f)):
        for (lo, hi), v in zip(BANDS, series):
            values[f"{sex}{lo:02d}{hi:02d}"] = v
        values[f"{sex}85PL"] = series[-1]
    return [values.get(n) for n in names]


class Reading(unittest.TestCase):
    def sheet(self, extra_men=0):
        names = header()
        rows = [names, names]   # the sheet's two header rows: names, then aliases
        keys = sorted(lc.SHAPES)
        per = 3
        total = 0
        for key in keys:
            rows.append(row(names, key.upper(), key.upper(), 1, per, per))
            rows.append(row(names, key.upper() + " MAHALLAH", key.upper(), 3, per, per))
            total += 2 * per * (len(BANDS) + 1)
        rows.insert(2, row(names, "LIBYA", "", 0, per * len(keys), per * len(keys)))
        return rows, total

    def test_the_shabiyat_are_read_and_checked(self):
        rows, total = self.sheet()
        saved = lc.NATIONAL
        lc.NATIONAL = total
        try:
            table = lc.read(rows)
        finally:
            lc.NATIONAL = saved
        self.assertEqual(len(table["shabiyat"]), 22)
        unit = table["shabiyat"]["darnah"]
        self.assertEqual(unit["men"], unit["women"])
        # Eighteen equal groups: the middle person closes the ninth, 40-44.
        self.assertEqual(lc.grouped_median(unit["groups"]), 45.0)

    def test_a_wrong_national_total_stops_the_run(self):
        rows, total = self.sheet()
        saved = lc.NATIONAL
        lc.NATIONAL = total + 1
        try:
            with self.assertRaises(SystemExit):
                lc.read(rows)
        finally:
            lc.NATIONAL = saved

    def test_records_bind_by_shape_and_rename_the_five_relabelled(self):
        rows, total = self.sheet()
        saved = lc.NATIONAL
        lc.NATIONAL = total
        try:
            table = lc.read(rows)
        finally:
            lc.NATIONAL = saved
        shapes = [{"id": sid, "name": f"label-{key}"} for key, sid in lc.SHAPES.items()]
        shapes[[k for k in lc.SHAPES].index("darnah")]["name"] = "Al Qubbah"
        records = lc.build(table, {"admin1": shapes, "admin2": shapes})
        self.assertEqual(len(records), 44)
        darnah = [r for r in records if r["shape_id"] == lc.SHAPES["darnah"]]
        self.assertEqual({r["name"] for r in darnah}, {"Darnah"})
        self.assertIn("Al Qubbah, a name this area is also given", darnah[0]["population_note"])
        sabha = [r for r in records if r["shape_id"] == lc.SHAPES["sabha"]][0]
        self.assertEqual(sabha["name"], "label-sabha")
        self.assertEqual(sabha["sex_ratio"]["unit"], "males_per_1000_females")
        self.assertEqual(sabha["sex_ratio"]["value"], 1000)

    def test_a_polygon_set_that_is_not_the_22_stops_the_run(self):
        rows, total = self.sheet()
        saved = lc.NATIONAL
        lc.NATIONAL = total
        try:
            table = lc.read(rows)
        finally:
            lc.NATIONAL = saved
        shapes = [{"id": sid, "name": key} for key, sid in lc.SHAPES.items()][:21]
        with self.assertRaises(SystemExit):
            lc.build(table, {"admin1": shapes})


if __name__ == "__main__":
    unittest.main()
