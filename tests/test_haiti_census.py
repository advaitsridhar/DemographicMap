"""Tests for the Haiti reader: IHSI's 2015 hierarchy and UNFPA's ages, no network."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import haiti_census as hc  # noqa: E402

HEAD = ["AREA_NAME", "GEO_MATCH", "ADM1_NAME", "ADM2_NAME", "ADM3_NAME", "ADM_LEVEL",
        "POP_BTOTL", "POP_MTOTL", "POP_FTOTL"]


def row(name, code, level, total, men, women, dept="", arr="", commune=""):
    return [name, code, dept, arr, commune, level, total, men, women]


def sheet(national):
    rows = [HEAD, ["alias"] * len(HEAD), row("HAITI", "HTI_GEO1_00", 0, national, 0, 0)]
    rows[2][7], rows[2][8] = national // 2, national - national // 2
    per = national // 10
    for d in range(1, 11):
        dcode = f"HTI_GEO1_{d:02d}"
        dm, dw = per // 2, per - per // 2
        rows.append(row(f"D{d}", dcode, 1, per, dm, dw, dept=f"D{d}"))
        # Forty-two arrondissements: four in each of the first two
        # departments, and four or five in the rest.
        count = 5 if d > 8 else 4
        sizes = [per // count] * (count - 1) + [per - per // count * (count - 1)]
        mens = [dm // count] * (count - 1) + [dm - dm // count * (count - 1)]
        for a, (size, men) in enumerate(zip(sizes, mens), 1):
            acode = f"{dcode}_{a:02d}"
            rows.append(row(f"A{d}{a}", acode, 2, size, men, size - men, dept=f"D{d}",
                            arr=f"A{d}{a}"))
            rows.append(row(f"C{d}{a}", f"{acode}_01", 3, size, men, size - men, dept=f"D{d}",
                            arr=f"A{d}{a}", commune=f"C{d}{a}"))
    return rows


class NamesTest(unittest.TestCase):
    def test_the_word_for_what_a_unit_is_comes_off(self):
        self.assertEqual(hc.plain("Arrondissement de l’Anse-à-Veau"), "Anse-à-Veau")
        self.assertEqual(hc.plain("Département de la Grande-Anse"), "Grande-Anse")
        self.assertEqual(hc.plain("Nord-Ouest Department"), "Nord-Ouest")
        self.assertEqual(hc.plain("Arrondissement Belle-Anse"), "Belle-Anse")
        self.assertEqual(hc.plain("Port-au-Prince"), "Port-au-Prince")


class EstimatesTest(unittest.TestCase):
    @mock.patch.object(hc, "NATIONAL", 10_000)
    def test_a_sound_hierarchy_is_read(self):
        # Two departments of five arrondissements and eight of four make 42.
        units = hc.estimates(sheet(10_000))
        self.assertEqual(len(units[1]), 10)
        self.assertEqual(len(units[2]), 42)
        self.assertEqual(units[0][0]["total"], 10_000)

    @mock.patch.object(hc, "NATIONAL", 10_000)
    def test_sexes_that_miss_the_total_stop_the_run(self):
        rows = sheet(10_000)
        rows[5][7] += 1
        with self.assertRaises(SystemExit):
            hc.estimates(rows)

    @mock.patch.object(hc, "NATIONAL", 10_000)
    def test_communes_that_miss_their_arrondissement_stop_the_run(self):
        rows = sheet(10_000)
        commune = next(r for r in rows if r[5] == 3)
        commune[6] += 2
        commune[7] += 1
        commune[8] += 1
        with self.assertRaises(SystemExit):
            hc.estimates(rows)


class AgesTest(unittest.TestCase):
    def test_median_from_unfpa_groups(self):
        groups = [f"{lo:02d}_{lo + 4:02d}" for lo in range(0, 80, 5)]
        columns = ["F_TL", "M_TL", "T_TL"] + [f"{s}_{g}" for s in "FMT" for g in groups] + [
            "F_80Plus", "M_80Plus", "T_80Plus"]
        row = {c: 0 for c in columns}
        for s, n in (("F", 5), ("M", 5)):
            row[f"{s}_00_04"] = n
            row[f"{s}_05_09"] = n
        row.update({"T_00_04": 10, "T_05_09": 10, "F_TL": 10, "M_TL": 10, "T_TL": 20})
        out = hc.median_fields(row, columns, "test")
        self.assertEqual(out["median_age"]["value"], 5.0)
        self.assertEqual(out["median_age"]["year"], 2024)

    def test_gaps_say_why(self):
        self.assertIn("Tableau 206", hc.gaps()["religion"]["note"])


if __name__ == "__main__":
    unittest.main()
