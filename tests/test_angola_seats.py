"""Angola's municipality seats from the 2016 law's text, on a small page (no network)."""

import unittest

from scripts.fetch_census import angola_seats as an

PAGE = """<h2 id=a>CAPÍTULO II PROVÍNCIA DE CABINDA<a href=#a aria-label="Link">&#8203;</a></h2>
<ul><li>O Município de Cabinda, com sede em Cabinda, tem como limites a estrada</li>
<li>O Município de Cacongo, com sede na Vila de Lândana, tem como limites</li></ul>
<h2>CAPÍTULO V PROVÍNCIA DO BENGO</h2>
<p>O Município do Dande com sede na Cidade do Caxito, tem como limites</p>
<p>O Município de Pango Aluquém, com sede em Pango Aluquém, tem como limites</p>
<h2>CAPÍTULO XII PROVÍNCIA DO MOXICO</h2>
<p>O Município do Moxico, com sede na Cidade do Luena, tem como limites</p>
<h2>CAPÍTULO VI PROVÍNCIA DE LUANDA</h2>
<p>O Município de Luanda, com sede na Ingombota, tem como limites</p>
<p>A Comuna do Bailundo, com sede no Bailundo, tem</p>"""


class Seats(unittest.TestCase):
    def test_read(self):
        found = an.seats(an.text_of(PAGE))
        self.assertEqual(found["cabinda"]["cacongo"], "Lândana")
        self.assertEqual(found["bengo"]["dande"], "Caxito")
        self.assertEqual(found["moxico"]["luena"], "Luena")        # drawn under its seat's name
        self.assertNotIn("bailundo", found.get("luanda", {}))       # a commune, not a municipality

    def test_build(self):
        found = an.seats(an.text_of(PAGE))
        admin1 = [{"id": p, "name": n} for p, n in (("C", "Cabinda"), ("B", "Bengo"),
                                                   ("N", "Cuanza Norte"), ("M", "Moxico"),
                                                   ("L", "Luanda"))]
        admin2 = [{"id": "1", "name": "Cacongo (Landana)", "parent": "C"},
                  {"id": "2", "name": "Dande", "parent": "B"},
                  {"id": "3", "name": "Pango-Aluquem", "parent": "N"},
                  {"id": "4", "name": "Luena", "parent": "M"},
                  {"id": "5", "name": "Luanda", "parent": "L"}]
        records, report = an.build(found, admin1, admin2)
        by = {r["name"]: r["capital"] for r in records}
        self.assertEqual(by["Cacongo (Landana)"], "Lândana")
        self.assertEqual(by["Dande"], "Caxito")
        self.assertEqual(by["Pango-Aluquem"], "Pango Aluquém")     # filed under another province
        self.assertEqual(by["Luena"], "Luena")
        self.assertNotIn("Luanda", by)
        self.assertTrue(any("several municipalities" in line for line in report))


if __name__ == "__main__":
    unittest.main()
