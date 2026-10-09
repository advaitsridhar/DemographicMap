"""Lebanon's LFHLCS 2018-19 nationality tables, read from sheet rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import lebanon_survey as ls  # noqa: E402

# Table HL.6A as CAS prints it (thousands, rounded here to three places).
HL6A = [
    ("Beirut", 236.109, 105.615), ("Baabda", 410.719, 143.083), ("Matn", 395.932, 115.103),
    ("Chouf", 207.482, 69.485), ("Aley", 210.678, 90.101), ("Keserwan", 230.518, 29.934),
    ("Jbeil", 115.690, 13.847), ("Tripoli", 201.338, 42.495), ("Koura", 72.433, 12.130),
    ("Zgharta", 73.118, 14.631), ("Batroun", 53.355, 5.513), ("Akkar", 297.886, 26.080),
    ("Bcharre", 20.837, 1.262), ("Minieh-Danniyeh", 122.066, 18.731),
    ("Zahleh", 140.006, 37.395), ("West Beqaa", 67.832, 18.584), ("Baalbek", 192.906, 21.718),
    ("Hermel", 28.732, 1.725), ("Rachaya", 31.738, 2.104), ("Saida", 209.059, 87.559),
    ("Tyr", 197.069, 58.624), ("Jezzine", 27.164, 4.896), ("Nabatieh", 146.561, 33.656),
    ("Bint Jbeil", 84.782, 11.434), ("Marjaayoun", 64.528, 9.519), ("Hasbaya", 25.759, 2.945),
]
# Table HL.5's governorates and their cazas, in print order.
HL5_GOVS = [
    ("Beirut", ["Beirut"]),
    ("Mount Lebanon", ["Baabda", "Matn", "Chouf", "Aley", "Keserwan", "Jbeil"]),
    ("North Lebanon", ["Tripoli", "Koura", "Zgharta", "Batroun", "Bcharre", "Minieh-Danniyeh"]),
    ("Akkar", ["Akkar"]),
    ("Bekaa", ["Zahleh", "West Beqaa", "Rachaya"]),
    ("Baalbek-Hermel", ["Baalbek", "Hermel"]),
    ("South Lebanon", ["Saida", "Tyr", "Jezzine"]),
    ("Nabatieh", ["Nabatieh", "Bint Jbeil", "Marjaayoun", "Hasbaya"]),
]
DRAWN_GOV = {"Beirut": "Beyrouth", "Akkar": "Aakkâr", "Bekaa": "Béqaa",
             "Baalbek-Hermel": "Baalbek-Hermel", "North Lebanon": "Liban-Nord",
             "South Lebanon": "Liban-Sud", "Nabatieh": "Nabatîyé"}


def hl6(rows=HL6A, total_off=0.0):
    out = [["Table HL.6A: Distribution of residents according to group of nationality and "
            "caza, Lebanon, 2018 (in thousands)", "", "", "", ""],
           ["Caza", "Nationality", "", "الجنسية", "القضاء"],
           ["", "Lebanese", "Non-Lebanese", "Total", ""]]
    for name, leb, non in rows:
        out.append([name, leb, non, round(leb + non, 3), "عربي"])
    leb = sum(r[1] for r in rows)
    non = sum(r[2] for r in rows)
    out.append(["Total", leb, non, leb + non + total_off, "لبنان"])
    out.append(["Estimation below 2500 have a relative standard error above 20%", "", "", "",
                ""])
    out.append(["Table HL.6B: Percentage distribution", "", "", "", ""])
    out.append(["Beirut", 69.1, 30.9, 100.0, "بيروت"])
    return out


def hl5():
    people = {n: round(a + b, 3) for n, a, b in HL6A}
    out = [["Table HL.5: Distribution", "", "", "", "", "", ""],
           ["Governorates", "Caza of residence", "Sex", "", "الجنس", "", ""],
           ["", "", "Women", "Men", "Women & Men", "", ""]]
    for gov, cazas in HL5_GOVS:
        for i, caza in enumerate(cazas):
            both = people[caza]
            out.append([gov if i == 0 else "", caza, both / 2, both / 2, both, "x", "y"])
        total = sum(people[c] for c in cazas)
        out.append(["", "Total", total / 2, total / 2, total, "المجموع", ""])
    return out


def drawn():
    names = sorted({g for gs in ls.GOVERNORATES.values() for g in gs})
    admin1 = [{"id": f"g{i}", "name": n, "parent": "LBN"} for i, n in enumerate(names)]
    ids = {u["name"]: u["id"] for u in admin1}
    admin2 = []
    for gov, cazas in HL5_GOVS:
        for caza in cazas:
            if gov == "Mount Lebanon":
                parent = "Keserwan-Jbeil" if caza in ("Keserwan", "Jbeil") else "Mont-Liban"
            else:
                parent = DRAWN_GOV[gov]
            admin2.append({"id": f"c-{caza}", "name": ls.CAZAS[caza], "parent": ids[parent]})
    return admin1, admin2


class TheSurvey(unittest.TestCase):
    def setUp(self):
        admin1, admin2 = drawn()
        self.rows = {r["shape_id"]: r for r in ls.build(hl6(), hl5(), admin1, admin2)}

    def test_every_caza_and_governorate_is_written(self):
        levels = [r["level"] for r in self.rows.values()]
        self.assertEqual(levels.count("admin2"), 26)
        self.assertEqual(levels.count("admin1"), 9)

    def test_a_caza_carries_its_nationality_shares_as_a_survey_estimate(self):
        beirut = self.rows["c-Beirut"]
        shares = {s["group"]: s["pct"] for s in beirut["ethnicity"]}
        self.assertEqual(shares, {"Lebanese": 69.1, "Foreign nationals": 30.9})
        self.assertTrue(beirut["ethnicity_basis"].startswith("survey estimate"))
        self.assertIn("refugee camps", beirut["ethnicity_note"])
        # Compositions only: no population from a survey.
        self.assertEqual(beirut["population"]["status"], "not_available")

    def test_every_unit_says_why_it_has_no_religion_language_age_or_ratio(self):
        for r in self.rows.values():
            self.assertIn("confession", r["religion"]["note"], r["name"])
            self.assertIn("language", r["language"]["note"], r["name"])
            for field in ("population", "median_age", "sex_ratio"):
                self.assertEqual(r[field]["status"], "not_available", (r["name"], field))
                self.assertIn("compositions only", r[field]["note"], (r["name"], field))
            self.assertIn("no count", r["population"]["note"], r["name"])

    def test_keserwan_jbeil_is_the_sum_of_its_two_cazas(self):
        kj = self.rows["g" + str(sorted({g for gs in ls.GOVERNORATES.values() for g in gs})
                                  .index("Keserwan-Jbeil"))]
        counts = {s["group"]: s["count"] for s in kj["ethnicity"]}
        self.assertEqual(counts["Foreign nationals"], round((29.934 + 13.847) * 1000))
        self.assertIn("Keserwan, Jbeil", kj["ethnicity_note"])

    def test_a_small_estimate_is_marked_low_precision(self):
        self.assertIn("Low precision", self.rows["c-Bcharre"]["ethnicity_note"])
        self.assertNotIn("Low precision", self.rows["c-Baabda"]["ethnicity_note"])

    def test_a_lebanon_row_that_the_cazas_miss_stops_the_run(self):
        admin1, admin2 = drawn()
        with self.assertRaises(SystemExit):
            ls.build(hl6(total_off=5.0), hl5(), admin1, admin2)

    def test_a_caza_drawn_in_another_governorate_stops_the_run(self):
        admin1, admin2 = drawn()
        wrong = [dict(u, parent="g0") if u["id"] == "c-Tyr" else u for u in admin2]
        with self.assertRaises(SystemExit):
            ls.build(hl6(), hl5(), admin1, wrong)


if __name__ == "__main__":
    unittest.main()
