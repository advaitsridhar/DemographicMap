"""Catalonia's religion and first language from the CEO's barometer microdata.

No network: the open-data listing and the respondents are built here in the
shapes the CEO publishes them in.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import catalonia_ceo as c  # noqa: E402
from scripts.fetch_census import spain_cis  # noqa: E402

NAN = float("nan")

LISTING = [
    {"codi_serie": "BOP_telefonica", "univers": "Població amb ciutadania espanyola de 18 i més "
     "anys resident a Catalunya", "microdades_1": {"url": "https://x/bop_telefonica.sav"}},
    {"codi_serie": "BOP_presencial", "titol_serie": "Microdades acumulades dels BOP presencials",
     "univers": "Població amb ciutadania espanyola de 18 i més anys resident a Catalunya",
     "microdades_1": {"url": "https://documents.dadesobertes.gencat.cat/ceo/docs/x.sav"}},
]


def person(prov, religion=1, first=1, other=NAN, wave=64, citizen=1, weight=1.0):
    return {"PONDERA": weight, "BOP_NUM": wave, "ANY": 2026, "MES": 6, "PROVINCIA": prov,
            "CIUTADANIA": citizen, "RELIGIO": religion, "LLENGUA_PRIMERA_1_3": first,
            "LLENGUA_PRIMERA_ALTRES": other}


def sample():
    rows = []
    for prov, n in ((8, 400), (17, 150), (25, 120), (43, 130)):
        for i in range(n):
            religion = (1, 9, 8, 3, 99)[i % 5]
            first, other = ((1, NAN), (2, NAN), (80, 1), (80, 3), (98, NAN))[i % 5]
            rows.append(person(prov, religion, first, other, wave=62 + i % 3))
    return rows


class TestListing(unittest.TestCase):
    def test_the_face_to_face_series(self):
        got = c.series(LISTING)
        self.assertTrue(got["url"].endswith("x.sav"))

    def test_another_universe_stops(self):
        listing = [dict(LISTING[1], univers="Població de 16 i més anys resident a Catalunya")]
        with self.assertRaises(SystemExit):
            c.series(listing)


class TestLabels(unittest.TestCase):
    def test_the_labels_the_codes_carry(self):
        labels = {1.0: "Catolicisme", 2.0: "Cristianisme evangèlic/protestant", 3.0: "Islam",
                  4.0: "Testimonis cristians de Jehovà", 5.0: "Budisme",
                  6.0: "Cristianisme ortodox", 7.0: "Judaisme", 8.0: "Cap: Agnosticisme",
                  9.0: "Cap: Ateisme", 80.0: "Altres", 98.0: "No ho sap", 99.0: "No contesta"}
        c.check_labels(labels, c.RELIGION, "RELIGIO")
        # A recoded question stops the run rather than being mislabelled.
        labels[9.0], labels[8.0] = labels[8.0], labels[9.0]
        with self.assertRaises(SystemExit):
            c.check_labels(labels, c.RELIGION, "RELIGIO")

    def test_the_language_labels(self):
        c.check_labels({1.0: "Català", 2.0: "Castellà", 80.0: "Altres opcions",
                        98.0: "No ho sap", 99.0: "No contesta"}, c.FIRST, "LLENGUA_PRIMERA_1_3")
        c.check_labels({1.0: "Català i castellà per igual", 2.0: "Aranès", 3.0: "Àrab",
                        4.0: "Romanès", 80.0: "Altres llengües o combinacions"},
                       c.OTHER_FIRST, "LLENGUA_PRIMERA_ALTRES")


class TestTally(unittest.TestCase):
    def test_each_province_and_catalonia(self):
        got = c.tally(sample())
        self.assertEqual(got["waves"], [62, 63, 64])
        self.assertTrue(got["uniform"])
        lleida = got["provinces"]["25"]
        self.assertEqual(lleida["n"], 120)
        self.assertEqual(lleida["religion"]["Catholic"], 24)
        self.assertEqual(lleida["religion"]["Not stated"], 24)
        self.assertEqual(lleida["language"]["Catalan and Spanish"], 24)
        self.assertEqual(lleida["language"]["Arabic"], 24)
        self.assertEqual(sum(lleida["language"].values()), 120)
        self.assertEqual(got["catalonia"]["n"], 800)
        self.assertEqual(sum(got["catalonia"]["religion"].values()), 800)

    def test_what_stops_the_run(self):
        for bad in (person(8, citizen=3), person(8, religion=NAN), person(8, religion=6.5),
                    person(8, first=80, other=NAN), person(8, first=NAN), person(9)):
            with self.assertRaises(SystemExit):
                c.tally(sample() + [bad])

    def test_a_province_missing_stops(self):
        with self.assertRaises(SystemExit):
            c.tally([r for r in sample() if r["PROVINCIA"] != 25])


class TestRecords(unittest.TestCase):
    def test_records(self):
        provinces, comunidades = spain_cis.bind(*spain_cis.load_units())
        got = c.tally(sample())
        dates = {62: (2025, 6), 63: (2025, 10), 64: (2026, 6)}
        records, skipped = c.build(got, dates, provinces, comunidades)
        self.assertEqual(skipped, [])
        by = {(r["level"], r["name"]): r for r in records}
        self.assertEqual(len(records), 5)
        lleida = by[("admin2", "Lleida")]
        self.assertEqual(lleida["shape_id"], provinces["25"]["id"])
        self.assertTrue(lleida["religion_basis"].startswith("survey estimate"))
        self.assertTrue(lleida["language_basis"].startswith("survey estimate"))
        self.assertIn("Low precision", lleida["religion_note"])
        self.assertIn("120 respondents in the province of Lleida", lleida["language_note"])
        self.assertIn("BOP 62 (June 2025), 63 (October 2025) and 64 (June 2026)",
                      lleida["religion_note"])
        self.assertEqual(lleida["religion_year"], 2026)
        self.assertTrue(all("count" not in row for row in lleida["religion"]))
        self.assertAlmostEqual(sum(r["pct"] for r in lleida["language"]), 100.0, delta=0.3)
        self.assertEqual({s["field"] for s in lleida["sources"]}, {"religion", "language"})
        barcelona = by[("admin2", "Barcelona")]
        self.assertNotIn("Low precision", barcelona["religion_note"])
        catalonia = by[("admin1", "Cataluña/Catalunya")]
        self.assertEqual(catalonia["shape_id"], comunidades["09"]["id"])
        self.assertIsInstance(catalonia["religion"], list)
        self.assertNotIsInstance(catalonia["language"], list)   # EULP's, not this file's
        self.assertIn("800 respondents in Catalonia", catalonia["religion_note"])
        # Since when the census has not asked, and what the question counts.
        self.assertIn("Constitution of 1978", lleida["religion_note"])
        self.assertIn("2021 round was drawn from registers", lleida["language_note"])
        self.assertIn("European Social Survey", catalonia["religion_note"])
        self.assertIn("nominal Catholics", catalonia["religion_note"])
        self.assertNotIn("European Social Survey", lleida["language_note"])


if __name__ == "__main__":
    unittest.main()
