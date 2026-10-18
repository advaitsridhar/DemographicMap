"""Ghana's district capitals, read from Wikipedia's Districts of Ghana.

The wikitext below is written in the article's form for three of its regions,
with rows copied from it (the runner's probe of the article, 9ab6aba).
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import ghana_capitals as gc  # noqa: E402

WIKITEXT = """'''Districts of Ghana''' are second-level administrative subdivisions.
== List of districts ==
=== Ahafo Region ===
{| class="wikitable sortable"
! District !! Category !! Capital !! Established !! Comments
|-
| [[Asunafo North Municipal District|Asunafo North]] || Municipal || [[Goaso]] || 1912 || Regional capital
|-
| [[Tano South Municipal District|Tano South]] || Municipal || [[Bechem]] || 2004 ||
|}
=== Eastern Region ===
{| class="wikitable sortable"
! District !! Category !! Capital !! Established !! Comments
|-
| [[Akuapim North Municipal District|Akuapim North]] || Municipal || [[Akropong]] || 1988 ||
|-
| [[Suhum Municipal District|Suhum]] || Municipal || [[Suhum, Ghana]] || July 2012 ||
|}
=== Western North Region ===
{| class="wikitable sortable"
! District !! Category !! Capital !! Established !! Comments
|-
| [[Sefwi-Wiawso Municipal District|Sefwi-Wiawso]] || Municipal || [[Sefwi Wiawso]] || ||
|}
== See also ==
{| class="wikitable"
! District !! Capital
|-
| Not a region || Nowhere
|}
"""


class GhanaCapitalsTest(unittest.TestCase):
    def test_the_longest_region_a_heading_names(self):
        self.assertEqual(gc.heading_region("Western North Region"), "Western North")
        self.assertEqual(gc.heading_region("Bono East Region"), "Bono East")
        self.assertIsNone(gc.heading_region("See also"))

    def test_capitals_by_region(self):
        rows = gc.capitals(WIKITEXT)
        self.assertEqual(rows["Ahafo"], [("Asunafo North", "Goaso"), ("Tano South", "Bechem")])
        self.assertIn(("Suhum", "Suhum"), rows["Eastern"])
        self.assertEqual(rows["Western North"], [("Sefwi-Wiawso", "Sefwi Wiawso")])
        self.assertEqual(sorted(rows), ["Ahafo", "Eastern", "Western North"])

    def test_bind_by_name_within_the_region(self):
        rows = gc.capitals(WIKITEXT)
        admin1 = [{"id": f"r{i}", "name": f"{r} Region"} for i, r in enumerate(gc.REGIONS)]
        region_id = {r: f"r{i}" for i, r in enumerate(gc.REGIONS)}
        admin2 = [
            {"id": "a", "name": "Asunafo North", "parent": region_id["Ahafo"]},
            {"id": "b", "name": "Tano South", "parent": region_id["Ahafo"]},
            {"id": "c", "name": "Akwapem North", "parent": region_id["Eastern"]},
            {"id": "d", "name": "Suhum Municipal", "parent": region_id["Eastern"]},
            {"id": "e", "name": "Sefwi Wiawso", "parent": region_id["Western North"]},
        ]
        with mock.patch.object(gc, "DISTRICTS", 5):
            records = {r["shape_id"]: r for r in gc.bind(rows, admin1, admin2)}
        self.assertEqual(records["c"]["capital"], "Akropong")
        self.assertEqual(records["d"]["capital"], "Suhum")
        self.assertEqual(records["e"]["capital"], "Sefwi Wiawso")
        self.assertEqual(records["a"]["sources"][0]["name"], "English Wikipedia, Districts of Ghana")
        # The revision read is what is cited, by its permanent address and year.
        from scripts.fetch_census import nigeria_capitals as nc
        article = {"title": "Districts of Ghana", "revid": 1359154973,
                   "timestamp": "2026-10-10T08:00:00Z"}
        with mock.patch.object(gc, "DISTRICTS", 5):
            records = {r["shape_id"]: r for r in gc.bind(rows, admin1, admin2, nc.cite(article))}
        src = records["a"]["sources"][0]
        self.assertEqual(src["url"], "https://en.wikipedia.org/w/index.php?"
                                     "title=Districts_of_Ghana&oldid=1359154973")
        self.assertEqual(src["year"], 2026)

    def test_a_polygon_left_over_stops_the_write(self):
        rows = gc.capitals(WIKITEXT)
        admin1 = [{"id": f"r{i}", "name": f"{r} Region"} for i, r in enumerate(gc.REGIONS)]
        admin2 = [{"id": "x", "name": "Nowhere Municipal", "parent": "r0"}]
        with mock.patch.object(gc, "DISTRICTS", 5), self.assertRaises(SystemExit):
            gc.bind(rows, admin1, admin2)


if __name__ == "__main__":
    unittest.main()
