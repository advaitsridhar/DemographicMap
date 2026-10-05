"""Jordan's DoS estimates and 2015 census tables, read from rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import jordan_dos as jd  # noqa: E402

# The tables' spellings, and the map's.
TABLE_NAMES = ["Amman", "Balqa", "Zarqa", "Madaba", "Irbid", "Mafraq", "Jarash", "Ajloun",
               "Karak", "Tafiela", "Ma'an", "Aqaba"]
DRAWN = ["Amman", "Balqa", "Zarqa", "Madaba", "Irbid", "Mafraq", "Jerash", "Ajloun", "Karak",
         "Tafilah", "Ma'an", "Aqaba"]
AR = "ﺎﻤﻋ"          # any Arabic, as the PDFs print beside each label


def triple(f, m):
    return [f, m, f + m]


def estimates_sheets(broken=False):
    rows21 = [["Table 2.1 Population of the Kingdom by Sex for Some Selected Years"],
              ["Year", "Male", "Female", "Total"]]
    rows22 = [[None, "Table 2.2 Estimated Population of the Kingdom by Governorate and Sex, "
                     "at End of 2025"], ["المحافظة", "ذكور", "اناث", "المجموع", None, "Governorate"]]
    men = women = 0
    for i, name in enumerate(TABLE_NAMES):
        m, w = 1000 * (i + 2), 900 * (i + 2)
        men, women = men + m, women + w
        rows22.append(["عربي", m, w, m + w, 1.0, name])
    rows22.append(["المجموع", men, women, men + women + (1 if broken else 0), 100, "Total"])
    rows21.append([2024, 10, 10, 20])
    rows21.append([2025, men, women, men + women])
    return {"2.2": rows21, "2.3": rows22}


def census_cells(i):
    """Jordanians abroad, non-Jordanians, Jordanians and all three of governorate i.

    Each as women, men, total, as Table 3.1 prints them: its total column
    counts the Jordanians abroad too.
    """
    abroad = triple(1, 2)
    non = triple(100 * (i + 1), 120 * (i + 1))
    jor = triple(1000 * (i + 1), 1010 * (i + 1))
    return abroad + non + jor + triple(1 + non[0] + jor[0], 2 + non[1] + jor[1])


def inside(cells):
    return cells[5] + cells[8]


def line(label, cells):
    return f"{label} " + " ".join(str(c) for c in cells) + f" {AR}"


def totals_text():
    lines = ["Table 3.1: Distribution of Population by Population Category",
             "Female Male Total Female Male Total Female Male Total Female Male Total"]
    kingdom = [sum(census_cells(i)[k] for i in range(12)) for k in range(12)]
    lines += [f"Jordan {AR}", line("Urban", kingdom), line("Total", kingdom)]
    for i, name in enumerate(TABLE_NAMES):
        cells = census_cells(i)
        lines += [f"{name} {AR}", line("Urban", cells), line("Total", cells),
                  f"{name} Qasabah District {AR}", line("Total", [7] * 12)]
    return "\n".join(lines)


AGE_LABELS = ["<1", "1-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
              "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]


def ages_text():
    lines = []
    blocks = [("Jordan", [sum(census_cells(i)[k] for i in range(12)) for k in range(12)])]
    blocks += [(name, census_cells(i)) for i, name in enumerate(TABLE_NAMES)]
    for name, cells in blocks:
        # Everyone inside Jordan, by sex; the abroad column stays empty by age.
        f_all, m_all = cells[3] + cells[6], cells[4] + cells[7]
        # Everyone in the 20-24 group but what the other groups hold.
        f_rows, m_rows = [1] * len(AGE_LABELS), [1] * len(AGE_LABELS)
        f_rows[5] = f_all - (len(AGE_LABELS) - 1)
        m_rows[5] = m_all - (len(AGE_LABELS) - 1)
        lines.append(f"{name} {AR}")
        for k, label in enumerate(AGE_LABELS):
            lines.append(line(label, [0, 0, 0] * 2 + triple(f_rows[k], m_rows[k]) * 2))
        lines.append(line("Total", cells))
        lines.append(f"{name} - Urban {AR}")
        lines.append(line("<1", [0] * 12))
        lines.append(line("Total", [0] * 12))
    return "\n".join(lines)


def nationalities_text(broken=False):
    lines = ["Table 8.1: Distribution of Non-Jordanian Population Living in Jordan",
             "Female Male Total Female Male Total Female Male Total"]
    blocks = [("Jordan", None)] + [(name, i) for i, name in enumerate(TABLE_NAMES)]
    for name, i in blocks:
        if i is None:
            f = sum(census_cells(j)[3] for j in range(12))
            m = sum(census_cells(j)[4] for j in range(12))
        else:
            f, m = census_cells(i)[3], census_cells(i)[4]
        syria_f, syria_m = f - 3, m - 3
        lines += [f"{name} {AR}", f"Arab Asian Countries {AR}",
                  line("Syria", [0, 0, 0] + triple(syria_f, syria_m) + triple(syria_f, syria_m)),
                  line("Oman", [0, 0, 0] + triple(1, 1) + triple(1, 1)),
                  line("Total", [0, 0, 0] + triple(syria_f + 1, syria_m + 1)
                       + triple(syria_f + 1, syria_m + 1)),
                  f"Non-Arab African Countries {AR}",
                  line("Democratic Republic of Congo -", [0, 0, 0] + triple(1, 1)
                       + triple(1, 1)),
                  "Zaire",
                  f"Other {AR}",
                  line("Others", [0, 0, 0] + triple(1, 1) + triple(1, 1)),
                  line("Total", [0, 0, 0] + triple(f, m) + triple(f, m + (1 if broken else 0)))]
    return "\n".join(lines)


ADMIN1 = [{"id": f"g{i}", "name": n, "parent": "JOR"} for i, n in enumerate(DRAWN)]


class TheReaders(unittest.TestCase):
    def test_estimates_by_governorate_with_the_year(self):
        year, est = jd.read_estimates(estimates_sheets())
        self.assertEqual(year, 2025)
        self.assertEqual(est["Jerash"], {"men": 8000, "women": 7200, "total": 15200})
        self.assertEqual(len(est), 12)

    def test_estimates_that_do_not_add_up_stop_the_run(self):
        with self.assertRaises(SystemExit):
            jd.read_estimates(estimates_sheets(broken=True))

    def test_census_totals_take_the_governorate_not_its_districts(self):
        totals = jd.read_totals(totals_text())
        self.assertEqual(totals["Amman"], census_cells(0))
        self.assertEqual(totals["Tafilah"][11], census_cells(9)[11])
        self.assertIn("kingdom", totals)

    def test_ages_stop_at_the_urban_block(self):
        ages = jd.read_ages(ages_text())
        self.assertEqual(ages["Irbid"]["total"], inside(census_cells(4)))
        self.assertEqual(ages["Irbid"]["groups"][0], (0, 0, 2))
        self.assertEqual(ages["Irbid"]["groups"][-1], (80, None, 2))

    def test_nationalities_by_section_and_name(self):
        nats = jd.read_nationalities(nationalities_text())
        aqaba = nats["Aqaba"]["counts"]
        self.assertEqual(aqaba["Syrian"], census_cells(11)[5] - 6)
        self.assertEqual(aqaba["Other Arab nationalities"], 2)
        self.assertEqual(aqaba["African nationalities"], 2)
        self.assertEqual(aqaba["Other nationalities"], 2)

    def test_nationalities_that_miss_their_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            jd.read_nationalities(nationalities_text(broken=True))


class TheRecords(unittest.TestCase):
    def setUp(self):
        year, est = jd.read_estimates(estimates_sheets())
        self.rows = {r["shape_id"]: r for r in jd.build(
            year, est, jd.read_totals(totals_text()), jd.read_ages(ages_text()),
            jd.read_nationalities(nationalities_text()), ADMIN1)}

    def test_every_drawn_governorate_is_written_once(self):
        self.assertEqual(sorted(self.rows), sorted(u["id"] for u in ADMIN1))

    def test_population_and_sex_from_the_estimates(self):
        jerash = self.rows["g6"]
        self.assertEqual(jerash["population"]["value"], 15200)
        self.assertEqual(jerash["population"]["year"], 2025)
        self.assertEqual(jerash["sex_ratio"]["value"], round(100 * 8000 / 7200, 1))

    def test_nationality_makes_everyone_counted(self):
        amman = self.rows["g0"]
        self.assertEqual(amman["ethnicity_basis"], "nationality")
        made = sum(s["count"] for s in amman["ethnicity"])
        self.assertEqual(made, inside(census_cells(0)))
        self.assertIn("abroad left out", amman["ethnicity_note"])
        self.assertEqual(amman["ethnicity"][0]["group"], "Jordanian")

    def test_median_from_the_census_groups(self):
        self.assertEqual(self.rows["g4"]["median_age"]["year"], 2015)
        self.assertTrue(20 <= self.rows["g4"]["median_age"]["value"] < 25)

    def test_an_unknown_drawn_governorate_stops_the_run(self):
        year, est = jd.read_estimates(estimates_sheets())
        drawn = ADMIN1[:-1] + [{"id": "gx", "name": "Nowhere", "parent": "JOR"}]
        with self.assertRaises(SystemExit):
            jd.build(year, est, jd.read_totals(totals_text()), jd.read_ages(ages_text()),
                     jd.read_nationalities(nationalities_text()), drawn)


if __name__ == "__main__":
    unittest.main()
