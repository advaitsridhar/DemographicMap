"""The shared REDATAM WebServer client: programs and the frequency-table parser."""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import redatam  # noqa: E402


def page(rows):
    return "<table>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


class Tables(unittest.TestCase):
    def test_thousands_written_any_way(self):
        for text in ("12 345", "12\xa0345", "12.345", "12,345"):
            self.assertEqual(redatam.count(text), 12345)
        self.assertIsNone(redatam.count("12,5%"[:-1] + "x"))

    def test_areas_rows_total_and_na(self):
        html = page([["AREA # 01", "Atlántida"],
                     ["Religión", "Casos", "%", "Acumulado %"],
                     ["Católica", "1 000", "50", "50"], ["Evangélica", "1 000", "50", "100"],
                     ["Total", "2 000", "100", "100"], ["No Aplica : 300"],
                     ["AREA # 02", "Colón"],
                     ["Religión", "Casos", "%", "Acumulado %"],
                     ["Católica", "5", "100", "100"], ["Total", "5", "100", "100"]])
        found = redatam.tables(html)
        self.assertEqual([(t["area"], t["name"], t["total"], t["na"]) for t in found],
                         [("01", "Atlántida", 2000, 300), ("02", "Colón", 5, None)])
        self.assertEqual(found[0]["rows"], [("Católica", 1000), ("Evangélica", 1000)])

    def test_another_header_word(self):
        html = page([["Sexo", "Cases", "%"], ["Hombre", "3", "60"], ["Mujer", "2", "40"],
                     ["Total", "5", "100"]])
        self.assertEqual(redatam.tables(html), [])
        (table,) = redatam.tables(html, header="Cases")
        self.assertEqual((table["area"], table["total"]), (None, 5))

    def test_program(self):
        self.assertEqual(redatam.frequency_program("PERSONA.P03", "MUNIC"),
                         "RUNDEF Job\n    SELECTION ALL\n\nTABLE TABLE1\n    AS FREQUENCY\n"
                         "    OF PERSONA.P03\n    AREABREAK MUNIC\n")

    def test_median(self):
        self.assertEqual(redatam.median_age(Counter({0: 1, 1: 1})), 1.0)
        self.assertIsNone(redatam.median_age(Counter()))


if __name__ == "__main__":
    unittest.main()
