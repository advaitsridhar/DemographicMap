import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import turkmenistan_census as tm  # noqa: E402


def sp(n):
    return f"{n:,}".replace(",", " ") if n else "–"


def age_table(number, area, urban_rows, rural_rows, split=None):
    """A volume 2 age table: nine figures a row, urban, rural and all."""
    def row(label, u, r):
        a = tuple(x + y for x, y in zip(u, r))
        figs = " ".join(sp(v) for v in (*u, *r, *a))
        if split and label == split[0]:
            figs = figs.replace(split[1], split[2], 1)
        return f"{label} {figs}"
    labels = ["under 1 year", "1–4 years"] + [f"{lo}–{lo + 4} years" for lo in range(5, 85, 5)]
    total_u = tuple(sum(r[i] for r in urban_rows) for i in range(3))
    total_r = tuple(sum(r[i] for r in rural_rows) for i in range(3))
    lines = ["RESULTS OF THE COMPLETE POPULATION AND",
             f"{number}. Distribution of the number of population of {area} by sex and age "
             f"groups, persons", "Urban settlements Rural area All settlements",
             row("Total", total_u, total_r), "including:"]
    for label, u, r in zip(labels, urban_rows, rural_rows):
        lines.append(row(label, u, r))
    lines += ["85 years and", row("older", urban_rows[-1], rural_rows[-1]),
              "Out of the total", "population:", "Average age of",
              "years 30.0 28.8 31.3 27.5 26.9 28.0 28.7 27.8 29.6"]
    return "\n".join(lines)


def rows(scale):
    return [(scale * 2 * (i + 1), scale * (i + 1), scale * (i + 1)) for i in range(19)]


AGES = "\n".join([
    age_table("2.11", "Ashgabat city", rows(100), [(0, 0, 0)] * 19),
    age_table("2.12", "Ahal velayat", rows(10), rows(20), split=("Total", "11 400", "114 00")),
])

NATIONALITY = """4.3. National composition of the population of Ashgabat city
Total population Urban population Rural population
persons % persons % persons %
All nationalities 38 000 100.00 38 000 100,00 – –
including the most
numerous:
Turkmens 30 000 78.95 30 000 78.95 – –
Russians 8 000 21.05 8 000 21.05 – –
4.4.National composition of the population of Ahal velayat
Total population Urban population Rural population
All nationalities 11 400 100.00 3 800 100.00 7 600 100.00
Turkmens 11 000 96.49 3 500 92.11 7 500 98.68
other nationalities 400 3.51 300 7.89 100 1.32
"""


def tongue(number, sex, area, both, extra=""):
    head = (f"{number}. Distribution of the number of population{sex} of {area} by nationality\n"
            "and mother tongue, persons\nTotal\nincluding considered as their mother tonque:\n"
            "Turkmen\nRussian\nUkrainian\nUzbek\nKazakh\nTatar\nArmenian\nAzerbaijani\nBaloch\n"
            "other\nlanguages\n")
    return head + "All\nnationalities " + " ".join(sp(v) for v in both) + "\nincluding:\n" + extra


def halves(v):
    men = [x // 2 for x in v[1:]]
    women = [x - y for x, y in zip(v[1:], men)]
    return [sum(men)] + men, [sum(women)] + women


ASHGABAT = [38000, 30500, 7000, 100, 100, 50, 50, 50, 50, 50, 50]
AHAL = [11400, 11000, 200, 0, 50, 50, 0, 0, 50, 0, 50]
TONGUES = "\n".join(
    tongue(n, s, a, v) for n, s, a, v in [
        ("4.12", "", "Ashgabat city", ASHGABAT),
        ("4.13", " (male)", "Ashgabat city", halves(ASHGABAT)[0]),
        ("4.14", " (female)", "Ashgabat city", halves(ASHGABAT)[1]),
        ("4.15", "", "Ahal velayat", AHAL),
        ("4.16", " (male)", "Ahal velayat", halves(AHAL)[0]),
        ("4.17", " (female)", "Ahal velayat", halves(AHAL)[1])])


class Tables(unittest.TestCase):
    def test_age_tables_by_area(self):
        found = tm.area_pages([AGES], r"2\.1[1-6]\.\s+Distribution of the number of population of")
        self.assertEqual(sorted(found), ["Ahal velayat", "Ashgabat city"])
        ashgabat = tm.parse_ages(found["Ashgabat city"][0], "Ashgabat city")
        self.assertEqual(ashgabat["total"], (38000, 19000, 19000))
        self.assertEqual(ashgabat["groups"][-1], (3800, 1900, 1900))

    def test_a_figure_split_in_the_wrong_place_is_repaired_once(self):
        found = tm.area_pages([AGES], r"2\.1[1-6]\.\s+Distribution of the number of population of")
        self.assertIn("114 00", found["Ahal velayat"][0])
        ahal = tm.parse_ages(found["Ahal velayat"][0], "Ahal velayat")
        self.assertEqual(ahal["total"], (11400, 5700, 5700))
        self.assertEqual(ahal["groups"][6], (420, 210, 210))

    def test_nationalities(self):
        found = tm.area_pages([NATIONALITY], r"4\.[3-8]\.\s*National composition of the population of")
        ahal = tm.parse_nationalities(found["Ahal velayat"][0], "Ahal velayat")
        self.assertEqual(ahal["total"], 11400)
        self.assertEqual(ahal["groups"], Counter(Turkmen=11000, Other=400))

    def test_mother_tongues_add_up_three_ways(self):
        found = tm.area_pages([TONGUES], r"4\.(?:1[2-9]|2\d)\.\s+Distribution of the(?: the)? number")
        rows = tm.tongue_rows("\n".join(found["Ashgabat city"]))
        self.assertEqual(len(rows), 3)
        self.assertEqual(tm.parse_tongues(*rows, "Ashgabat city"), ASHGABAT)


A1 = [{"id": "A", "name": "Ahal"}]
A2 = [{"id": "x", "name": "Ak Bugday", "parent": "A"}]


class Records(unittest.TestCase):
    def test_ahal_carries_ashgabat(self):
        areas = {
            "Ashgabat city": {"age": {"total": (38000, 19000, 19000),
                                      "groups": [(0, 0, 0)] * 7 + [(38000, 19000, 19000)]
                                      + [(0, 0, 0)] * 11},
                              "nationality": Counter(Turkmen=30000, Russian=8000),
                              "tongues": Counter(Turkmen=30500, Russian=7500)},
            "Ahal velayat": {"age": {"total": (11400, 6000, 5400),
                                     "groups": [(0, 0, 0)] * 5 + [(11400, 6000, 5400)]
                                     + [(0, 0, 0)] * 13},
                             "nationality": Counter(Turkmen=11400),
                             "tongues": Counter(Turkmen=11400)},
        }
        old = tm.AREAS
        tm.AREAS = {"Ashgabat city": "Ahal", "Ahal velayat": "Ahal"}
        try:
            out = {r["shape_id"]: r for r in tm.build(areas, A1, A2)}
        finally:
            tm.AREAS = old
        ahal = out["A"]
        self.assertEqual(ahal["population"]["value"], 49400)
        self.assertEqual(ahal["sex_ratio"]["value"], round(100 * 25000 / 24400, 1))
        self.assertIn("Ashgabat city", ahal["population_note"])
        self.assertEqual(ahal["ethnicity"][0], {"group": "Turkmen", "pct": 83.8, "count": 41400})
        self.assertEqual(out["x"]["population"]["status"], "not_available")
        self.assertIn("etrap", out["x"]["population"]["note"])


if __name__ == "__main__":
    unittest.main()
