"""Libya's 2006 census reader: the shabiyat, their baladiyat, and the areas drawn."""

import sys
import unittest
from pathlib import Path
from unittest import mock

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


def sheet(abyar=False):
    """Every shabiyah of SHAPES with one baladiyah of its own name and one
    mahallah; Banghazi with a second baladiyah, Tukrah, of the men only (and
    with ``abyar`` a third, Al Ibyar, likewise)."""
    names = header()
    rows = [names, names]   # the sheet's two header rows: names, then aliases
    per = 3
    total = 0
    for key in sorted(lc.SHAPES):
        if key == "banghazi":
            extra = 2 if abyar else 1
            rows.append(row(names, key.upper(), key.upper(), 1, per + extra, per))
            rows.append(row(names, key.upper(), key.upper(), 2, per, per))
            rows.append(row(names, "TUKRAH", key.upper(), 2, 1, 0))
            if abyar:
                rows.append(row(names, "AL IBYAR", key.upper(), 2, 1, 0))
            rows.append(row(names, key.upper() + " MAHALLAH", key.upper(), 3, per + extra, per))
            total += (2 * per + extra) * (len(BANDS) + 1)
            continue
        rows.append(row(names, key.upper(), key.upper(), 1, per, per))
        rows.append(row(names, key.upper(), key.upper(), 2, per, per))
        rows.append(row(names, key.upper() + " MAHALLAH", key.upper(), 3, per, per))
        total += 2 * per * (len(BANDS) + 1)
    level = names.index("ADM_LEVEL")
    shabiyat = [r for r in rows[2:] if r[level] == 1]
    national = [sum(r[i] for r in shabiyat) if isinstance(shabiyat[0][i], int) else None
                for i in range(len(names))]
    national[names.index("AREA_NAME")], national[level] = "LIBYA", 0
    rows.insert(2, national)
    return rows, total


class Reading(unittest.TestCase):
    def read(self, total, rows):
        with mock.patch.object(lc, "NATIONAL", total):
            return lc.read(rows)

    def test_the_shabiyat_are_read_and_checked(self):
        rows, total = sheet()
        table = self.read(total, rows)
        self.assertEqual(len(table["shabiyat"]), 22)
        self.assertEqual(len(table["baladiyat"]), 23)
        unit = table["shabiyat"]["darnah"]
        self.assertEqual(unit["men"], unit["women"])
        # Eighteen equal groups: the middle person closes the ninth, 40-44.
        self.assertEqual(lc.grouped_median(unit["groups"]), 45.0)

    def test_a_wrong_national_total_stops_the_run(self):
        rows, total = sheet()
        with self.assertRaises(SystemExit):
            self.read(total + 1, rows)


class Areas(unittest.TestCase):
    def table(self):
        rows, total = sheet()
        with mock.patch.object(lc, "NATIONAL", total):
            return lc.read(rows), total

    def shapes(self):
        shapes = [{"id": sid, "name": f"label-{key}"} for key, sid in lc.SHAPES.items()]
        for s in shapes:
            if s["id"] == lc.SHAPES["darnah"]:
                s["name"] = "Al Qubbah"
        return shapes

    def test_a_moved_baladiyah_is_counted_where_its_seat_lies(self):
        table, total = self.table()
        moved = {("banghazi", "tukrah"): "almarj"}
        with mock.patch.object(lc, "NATIONAL", total), mock.patch.object(lc, "MOVED", moved), \
                mock.patch.object(lc, "UNSURE", {}):
            shapes = self.shapes()
            records = lc.build(table, {"admin1": shapes, "admin2": shapes})
        self.assertEqual(len(records), 44)
        marj = [r for r in records if r["shape_id"] == lc.SHAPES["almarj"]][0]
        benghazi = [r for r in records if r["shape_id"] == lc.SHAPES["banghazi"]][0]
        per_area = 2 * 3 * (len(BANDS) + 1)
        self.assertEqual(marj["population"]["value"], per_area + len(BANDS) + 1)
        self.assertEqual(benghazi["population"]["value"], per_area)
        self.assertIn("which the census counts with Banghazi", marj["population_note"])
        self.assertIn("without Tukrah", benghazi["population_note"])
        self.assertGreater(marj["sex_ratio"]["value"], 1000)
        self.assertEqual(benghazi["sex_ratio"]["value"], 1000)

    def test_relabelled_areas_take_their_shabiyah_name_and_unsure_ones_say_why(self):
        table, total = self.table()
        with mock.patch.object(lc, "NATIONAL", total), mock.patch.object(lc, "MOVED", {}):
            shapes = self.shapes()
            records = lc.build(table, {"admin1": shapes, "admin2": shapes})
        darnah = [r for r in records if r["shape_id"] == lc.SHAPES["darnah"]]
        self.assertEqual({r["name"] for r in darnah}, {"Darnah"})
        self.assertIn("Al Qubbah, a name this area is also given", darnah[0]["population_note"])
        tripoli = [r for r in records if r["shape_id"] == lc.SHAPES["tarabulus"]][0]
        self.assertEqual(tripoli["population"]["status"], "not_available")
        self.assertIn("Sidi as Sayih", tripoli["population"]["note"])
        # The reason gives way to no encyclopaedia's figure for other ground.
        self.assertTrue(tripoli["population"]["displaces_undated"])
        self.assertEqual(tripoli["population"]["displaces_before"], lc.DISPLACES_BEFORE)
        sabha = [r for r in records if r["shape_id"] == lc.SHAPES["sabha"]][0]
        self.assertEqual(sabha["name"], "label-sabha")
        self.assertEqual(sabha["sex_ratio"]["unit"], "males_per_1000_females")

    def test_one_baladiyah_left_out_lies_outside_it(self):
        table, total = self.table()
        moved = {("banghazi", "tukrah"): "almarj"}
        with mock.patch.object(lc, "NATIONAL", total), mock.patch.object(lc, "MOVED", moved), \
                mock.patch.object(lc, "UNSURE", {}):
            shapes = self.shapes()
            records = lc.build(table, {"admin1": shapes, "admin2": shapes})
        benghazi = [r for r in records if r["shape_id"] == lc.SHAPES["banghazi"]][0]
        self.assertIn("without Tukrah (18), which lies outside it", benghazi["population_note"])

    def test_baladiyat_gained_from_one_shabiyah_are_named_together(self):
        rows, total = sheet(abyar=True)
        moved = {("banghazi", "tukrah"): "almarj", ("banghazi", "alibyar"): "almarj"}
        with mock.patch.object(lc, "NATIONAL", total):
            table = lc.read(rows)
        with mock.patch.object(lc, "NATIONAL", total), mock.patch.object(lc, "MOVED", moved), \
                mock.patch.object(lc, "UNSURE", {}):
            shapes = self.shapes()
            records = lc.build(table, {"admin1": shapes, "admin2": shapes})
        marj = [r for r in records if r["shape_id"] == lc.SHAPES["almarj"]][0]
        self.assertIn("with Tukrah (18) and Al Ibyar (18), which the census counts with "
                      "Banghazi; added up", marj["population_note"])
        benghazi = [r for r in records if r["shape_id"] == lc.SHAPES["banghazi"]][0]
        self.assertIn("without Tukrah (18) and Al Ibyar (18), which lie outside it",
                      benghazi["population_note"])

    def test_the_2020_estimate_for_a_shabiyah_drawn_unchanged(self):
        table, total = self.table()
        moved = {("banghazi", "tukrah"): "almarj"}
        estimates = {key: 1000 + i for i, key in enumerate(sorted(lc.SHAPES))}
        nationality = {(lc.fold(b["shabiyah"]), lc.fold(b["name"])): (b["total"] - 1, 1)
                       for b in table["baladiyat"]}
        with mock.patch.object(lc, "NATIONAL", total), mock.patch.object(lc, "MOVED", moved), \
                mock.patch.object(lc, "UNSURE", {}):
            shapes = self.shapes()
            records = lc.build(table, {"admin1": shapes, "admin2": shapes}, estimates,
                               "US Census Bureau, population estimate for 2020", nationality)
        by = {r["shape_id"]: r for r in records if r["level"] == "admin1"}
        sabha = by[lc.SHAPES["sabha"]]
        self.assertEqual(sabha["population"]["value"], estimates["sabha"])
        self.assertEqual(sabha["population"]["year"], 2020)
        self.assertIn("the 2006 census counted", sabha["population_note"])
        self.assertEqual(sabha["median_age"]["year"], 2006)
        benghazi = by[lc.SHAPES["banghazi"]]          # without Tukrah: other ground
        self.assertEqual(benghazi["population"]["year"], 2006)
        self.assertIn("not of this area", benghazi["population_note"])
        self.assertEqual(sabha["ethnicity_basis"], "nationality")
        self.assertEqual([g["group"] for g in sabha["ethnicity"]], ["Libyan", "Foreign nationals"])
        darnah = by[lc.SHAPES["darnah"]]
        self.assertIn("the area shown is the shabiyah of Darnah", darnah["population_note"])

    def test_a_recomposed_relabelled_area_is_only_close_to_its_shabiyah(self):
        table, total = self.table()
        moved = {("banghazi", "tukrah"): "darnah"}
        with mock.patch.object(lc, "NATIONAL", total), mock.patch.object(lc, "MOVED", moved), \
                mock.patch.object(lc, "UNSURE", {}):
            shapes = self.shapes()
            records = lc.build(table, {"admin1": shapes, "admin2": shapes})
        darnah = [r for r in records if r["shape_id"] == lc.SHAPES["darnah"]][0]
        self.assertIn("is close to the shabiyah of Darnah", darnah["population_note"])

    def test_the_estimates_must_make_the_country(self):
        names = ["AREA_NAME", "ADM_LEVEL", "POP2020"]
        aliases = ["Name", "Level", "Total population, 2020 estimate"]
        rows = [names, aliases, ["LIBYA", 0, 30], ["SABHA", 1, 10], ["GHAT", 1, 20]]
        self.assertEqual(lc.read_estimates(rows)[0], {"sabha": 10, "ghat": 20})
        rows[2][2] = 31
        with self.assertRaises(SystemExit):
            lc.read_estimates(rows)

    def test_a_moved_baladiyah_the_census_does_not_have_stops_the_run(self):
        table, total = self.table()
        with mock.patch.object(lc, "NATIONAL", total), \
                mock.patch.object(lc, "MOVED", {("banghazi", "nowhere"): "almarj"}):
            with self.assertRaises(SystemExit):
                lc.compose(table)

    def test_a_polygon_set_that_is_not_the_22_stops_the_run(self):
        table, total = self.table()
        shapes = self.shapes()[:21]
        with mock.patch.object(lc, "MOVED", {}):
            with self.assertRaises(SystemExit):
                lc.build(table, {"admin1": shapes})


if __name__ == "__main__":
    unittest.main()
