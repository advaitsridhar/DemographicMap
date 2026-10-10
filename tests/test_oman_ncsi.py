"""Oman's NCSI yearbook tables 7-2 and 9-2, read from laid-out pages built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import oman_ncsi as on  # noqa: E402
from scripts.fetch_census.oman_ncsi import PAGE_BREAK  # noqa: E402

BANDS = [(lo, lo + 4) for lo in range(0, 80, 5)] + [(80, None)]


def wilayat_numbers(i):
    # Expat/Omani for 2023, 2022, 2021.
    return [1000 + 10 * i, 2000 + 7 * i, 900 + 10 * i, 1900 + 7 * i, 800 + i, 1800 + i]


def fmt(n):
    return f"{n:,}"


def yearbook(break_sum=False):
    lines72 = []
    totals = [0] * 6
    gov_totals = {}
    i = 0
    for gov, wilayats in on.TABLE:
        rows = []
        made = [0] * 6
        for name in wilayats:
            nums = wilayat_numbers(i)
            i += 1
            made = [a + b for a, b in zip(made, nums)]
            rows.append(f"{name} " + " ".join(fmt(n) for n in nums) + " عربي")
        if break_sum and gov == "Dhofar":
            made[0] += 1
        gov_totals[gov] = made
        totals = [a + b for a, b in zip(totals, made)]
        lines72.append(f"{gov} :- " + " ".join(fmt(n) for n in made) + " -: عربي")
        lines72 += rows
    lines72.append("Sultanate Total " + " ".join(fmt(n) for n in totals) + " عربي")
    half = len(lines72) // 2
    head = ["65 64", "Total Population Registered in the Sultanate by Nationality , "
                     "Governorates & Wilayats", "Year 2023 2022 2021",
            "Expatriate Omani Expatriate Omani Expatriate Omani"]
    page1 = "\n".join(head + lines72[:half] + ["Population ناــكسلا"])
    page2 = "\n".join(["67 66", "Contd. 7-2", "Year 2023 2022 2021",
                       "Expatriate Omani Expatriate Omani Expatriate Omani"]
                      + lines72[half:] + ["Population ناــكسلا"])
    # Table 9-2: each governorate's 2023 people spread over 17 bands.
    people = {gov: gov_totals[gov][0] + gov_totals[gov][1] for gov, _w in on.TABLE}
    per_band = {g: [people[g] // 17] * 16 + [people[g] - 16 * (people[g] // 17)]
                for g in people}
    age_lines = ["Population Registered by Age Group, Governorates", "End of December 2023"]
    for b, (lo, hi) in enumerate(BANDS):
        cols = [per_band[g][b] for g in on.AGE_COLUMNS]
        label = f"{hi} - {lo}" if hi is not None else "80+"
        age_lines.append("2 " + " ".join(fmt(n) for n in [sum(cols)] + cols) + f" {label}")
    cols = [people[g] for g in on.AGE_COLUMNS]
    age_lines.append(" ".join(fmt(n) for n in [sum(cols)] + cols) + " Total ةلمجلا")
    page3 = "\n".join(age_lines)
    return PAGE_BREAK.join(["front matter", page1, page2, "Table 8-2", page3]), gov_totals


def drawn():
    admin1 = [{"id": f"r{i}", "name": n, "parent": "OMN"} for i, n in enumerate(
        ["Muscat", "Dhofar", "Al Wusta", "Ad Dakhiliyah", "Al Batinah", "Ash Sharqiyah",
         "Az Zahirah"])]
    region = {"Muscat": "r0", "Dhofar": "r1", "Al Wusta": "r10", "Ad Dakhiliyah": "r3",
              "Al Batinah North": "r4", "Al Batinah South": "r4", "Ash Sharqiyah South": "r5",
              "Ash Sharqiyah North": "r5", "Adh Dhahirah": "r6", "Al Buraymi": "r6",
              "Musandam": "r6"}
    region["Al Wusta"] = "r2"
    admin2 = []
    for gov, wilayats in on.TABLE:
        for name, label in wilayats.items():
            if not label:
                continue
            parent = "r6" if label == "WILAYAT MASIRAH" else region[gov]
            admin2.append({"id": f"w-{label}", "name": label, "parent": parent})
    return admin1, admin2, {u["id"]: u["name"] for u in admin1}


class TheYearbook(unittest.TestCase):
    def setUp(self):
        self.text, self.govs = yearbook()
        admin1, admin2, parents = drawn()
        self.rows = {r["shape_id"]: r for r in on.build(self.text, admin1, admin2, parents)}

    def test_every_drawn_wilayat_is_written(self):
        self.assertEqual(sum(1 for r in self.rows.values() if r["level"] == "admin2"), 61)

    def test_a_carved_wilayat_is_summed_into_the_drawn_one_holding_it(self):
        nizwa = self.rows["w-WILAYAT NIZWA"]
        self.assertIn("Al Jabal Al Akhdar", nizwa["population"]["note"])
        self.assertIsNone(nizwa.get("aliases"))

    def test_nationality_names_no_people(self):
        r = self.rows["w-WILAYAT SALALAH"]
        self.assertEqual({s["group"] for s in r["ethnicity"]},
                         {"Omani citizens", "Foreign nationals"})
        self.assertEqual(r["ethnicity_basis"], "nationality")

    def test_regions_sum_their_wilayats_and_whole_ones_carry_a_median(self):
        muscat = self.rows["r0"]
        self.assertEqual(muscat["population"]["value"], sum(self.govs["Muscat"][:2]))
        self.assertEqual(muscat["median_age"]["year"], 2023)
        batinah = self.rows["r4"]
        self.assertEqual(batinah["population"]["value"],
                         sum(self.govs["Al Batinah North"][:2])
                         + sum(self.govs["Al Batinah South"][:2]))
        self.assertIn("median_age", batinah)
        # Masirah is drawn in Az Zahirah: neither region is whole governorates.
        self.assertEqual(self.rows["r5"]["median_age"]["status"], "not_available")
        self.assertEqual(self.rows["r6"]["median_age"]["status"], "not_available")

    def test_a_governorate_its_wilayats_miss_stops_the_run(self):
        text, _g = yearbook(break_sum=True)
        admin1, admin2, parents = drawn()
        with self.assertRaises(SystemExit):
            on.build(text, admin1, admin2, parents)


if __name__ == "__main__":
    unittest.main()
