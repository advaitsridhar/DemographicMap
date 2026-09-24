import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import ecuador_cantons as ec  # noqa: E402
from probe_wikitable import tables  # noqa: E402

# The shape of the rows Spanish Wikipedia's list is written in, as the table
# reader returns them (measured on 24 September 2026).
WIKITEXT = """
{| class="wikitable sortable"
! Bandera !! Cantón !! Provincia !! Año de Cantonización !! Población (2022) !! Área
|-
| [[Archivo:x.svg|20px]] || [[Cantón San Lorenzo]] || E || 1941 || {{formatnum:48391}} || 3136
|-
| [[Archivo:y.svg|20px]] || [[Cantón Eloy Alfaro]] || E || 1941 || align=right| {{formatnum:46305}} || 4338
|-
| [[Archivo:z.svg|20px]] || [[Cantón Bolívar (Carchi)|Cantón Bolívar]] || C || 1985 || 13 953 || 356
|-
| [[Archivo:w.svg|20px]] || [[Cantón Nuevo]] || QQ || 2030 || 1 || 1
|}
"""


class Rows(unittest.TestCase):
    def setUp(self):
        self.cantons, self.skipped = ec.parse(tables(WIKITEXT)[0])

    def test_each_canton_reads_its_province_and_its_people(self):
        self.assertEqual(
            [(c["name"], c["province"], c["population"]) for c in self.cantons],
            [("San Lorenzo", "Esmeraldas", 48391), ("Eloy Alfaro", "Esmeraldas", 46305),
             ("Bolívar", "Carchi", 13953)])

    def test_a_row_that_does_not_read_is_reported_not_guessed(self):
        self.assertEqual(len(self.skipped), 1)
        self.assertIn("Nuevo", self.skipped[0])


class Citation(unittest.TestCase):
    def test_an_inec_reference_is_recognised(self):
        self.assertTrue(ec.cites_inec('<ref name="c">INEC, Censo 2022</ref>'))
        self.assertFalse(ec.cites_inec("<ref>Some atlas</ref>"))


if __name__ == "__main__":
    unittest.main()
