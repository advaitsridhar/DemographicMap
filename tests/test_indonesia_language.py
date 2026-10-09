"""Indonesia: first language from the 2020 census Long Form, as a survey estimate.

No network: the Language sheet is built here in the Bureau's two-row-header layout.
"""

import unittest
import unittest.mock

from scripts.fetch_census import indonesia_language as lang

NAMES = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL", "NSO_CODE", "NSO_NAME",
         "LNG_BTOTL", "LNG_YESIN", "LNG_NOTIN", "LNG_1STIN", "LNG_1STRG", "LNG_1STFOR",
         "LNG_1STSGN"]
ALIASES = ["", "", "", "", "", "", "Total population", "Can speak, Indonesian",
           "Cannot speak, Indonesian", "First language, Indonesian",
           "First language, regional", "First language, foreign", "First language, sign"]
JAK = "Jakarta Special Capital Region"
OTHERS = [p for p in lang.age.indonesia.PROVINCES if p not in (JAK, "Bengkulu")]


def row(level, adm1, adm2, ind, reg, foreign=0, sign=0, cannot=0):
    total = ind + reg + foreign + sign
    return [adm2 or adm1 or "INDONESIA", adm1, adm2, level, "", adm2, total, total - cannot,
            cannot, ind, reg, foreign, sign]


def sheet(extra=0, lake=True):
    rows = [NAMES, ALIASES,
            row(2, "JAKARTA", "KOTA ADMINISTRASI JAKARTA UTARA", 80, 20),
            row(2, "JAKARTA", "KABUPATEN ADMINISTRASI KEPULAUAN SERIBU", 5, 5),
            row(2, "BENGKULU", "KOTA BENGKULU", 30, 70, sign=1, cannot=2),
            row(1, "JAKARTA", "", 85, 25),
            row(1, "BENGKULU", "", 30 + extra, 70, sign=1, cannot=2)]
    if lake:
        rows.append(["DANAU TOBA", "SUMATERA UTARA", "DANAU TOBA", 2, "", ""] + [None] * 7)
    for p in OTHERS:
        rows += [row(2, p.upper(), f"KABUPATEN {p.upper()} ONE", 1, 9),
                 row(1, p.upper(), "", 1, 9)]
    rows.append(row(0, "", "", 115 + extra + len(OTHERS), 95 + 9 * len(OTHERS), sign=1,
                    cannot=2))
    return rows


ADMIN1 = [{"id": e, "name": e} for e in lang.age.indonesia.PROVINCES]
ADMIN2 = ([{"id": "J", "name": "Kota Jakarta Utara", "parent": JAK},
           {"id": "K", "name": "Kota Bengkulu", "parent": "Bengkulu"},
           {"id": "L", "name": "Danau Toba", "parent": "North Sumatra"}]
          + [{"id": f"X{i}", "name": f"{p} One", "parent": p} for i, p in enumerate(OTHERS)])


class LanguageTest(unittest.TestCase):
    def build(self, rows):
        parsed = lang.read_rows(rows)
        national = next(r["total"] for r in parsed if r["level"] == 0)
        with unittest.mock.patch.object(lang, "NATIONAL_5PLUS", national):
            return {r["shape_id"]: r for r in lang.build(parsed, ADMIN1, ADMIN2)}

    def test_shares_basis_and_labels(self):
        recs = self.build(sheet())
        k = {g["group"]: g["pct"] for g in recs["K"]["language"]}
        self.assertEqual(k["Regional languages of Indonesia"], 69.3)
        self.assertEqual(k["Indonesian"], 29.7)
        self.assertTrue(recs["K"]["language_basis"].startswith("survey estimate"))
        self.assertEqual(recs["K"]["language_year"], 2022)
        # Jakarta is its own row, Thousand Islands and all.
        j = {g["group"]: g["count"] for g in recs[JAK]["language"]}
        self.assertEqual(j["Indonesian"], 85)
        self.assertNotIn("L", recs)

    def test_output_is_a_survey_file(self):
        self.assertTrue(lang.OUT.endswith("_survey.json"))

    def test_a_province_its_regencies_do_not_make_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(sheet(extra=5))

    def test_classes_must_make_the_total(self):
        rows = sheet()
        rows[4][6] += 10      # Kota Bengkulu's total no longer its classes' sum
        with self.assertRaises(SystemExit):
            lang.read_rows(rows)


if __name__ == "__main__":
    unittest.main()
