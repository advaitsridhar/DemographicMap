"""Figures read from the source a Wikipedia article cites."""
import unittest
from pathlib import Path

from scripts.fetch_census import cited_sources as cs

# citypopulation.de's Somalia table, as its probe read it on 23 September 2026:
# name, abbreviation, area, 2005, 2014, 2019.
SOMALIA = [
    ("Somalia", "SOM", "637,657", "7,502,700", "12,316,895", "15,626,000"),
    ("Awdal", "ADL", "21,374", "305,500", "673,263", "1,010,600"),
    ("Bakool", "BKL", "26,962", "310,600", "367,226", "383,400"),
    ("Banaadir", "BND", "370", "901,200", "1,650,227", "2,330,700"),
    ("Bari [ East ]", "BAR", "70,088", "367,600", "719,512", "949,700"),
    ("Bay", "BAY", "35,156", "620,600", "792,182", "1,035,900"),
    ("Galgaduud ( Galguduud )", "GGD", "46,126", "330,100", "569,434", "634,300"),
    ("Gedo", "GED", "60,389", "328,400", "508,405", "566,300"),
    ("Hiiraan [ Hiran ]", "HRN", "31,510", "329,800", "520,685", "566,400"),
    ("Jubbada Dhexe [ Middle Juba ]", "JBD", "9,836", "238,900", "362,921", "432,200"),
    ("Jubbada Hoose [ Lower Juba ]", "JBH", "42,876", "385,800", "489,307", "632,900"),
    ("Mudug", "MDG", "72,933", "350,100", "717,863", "864,700"),
    ("Nugaal [ Nugal ]", "NGL", "26,180", "145,300", "392,698", "473,900"),
    ("Sanaag", "SNG", "53,374", "270,400", "544,123", "578,100"),
    ("Shabeellaha Dhexe [ Middle Shebelle ]", "SBD", "22,663", "514,900", "516,036", "622,700"),
    ("Shabeellaha Hoose [ Lower Shebelle ]", "SBH", "25,285", "850,700", "1,202,219", "1,218,700"),
    ("Sool", "SOL", "25,036", "150,300", "327,428", "618,600"),
    ("Togdheer", "TOG", "38,663", "402,300", "721,363", "962,400"),
    ("Woqooyi Galbeed [ Northwest ]", "WGB", "28,836", "700,300", "1,242,003", "1,744,400"),
]
HEAD = ("Name", "Abbr.", "Area A (km²)", "Population Estimate (E) 2005-08-01",
        "Population Estimate (E) 2014-01-01", "Population Calculation (UP) 2019-01-01")


def page(rows, head=HEAD):
    # As the live page lays it out: an empty cell opens every row, the header
    # included, and a sort key and a link close each region's.
    th = "<th></th>" + "".join(f"<th>{h.replace(' (', '<br>(')}</th>" for h in head)
    body = "".join(
        "<tr><td></td>" + f'<td><a href="#"><span>{r[0]}</span></a></td>'
        + "".join(f"<td>{c}</td>" for c in r[1:])
        + '<td>2696200</td><td><a href="#">→</a></td></tr>'
        for r in rows)
    return f"<p>Pre-war Regions</p><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


class SomaliasTable(unittest.TestCase):
    def test_reads_every_regions_2019_figure(self):
        figures, why = cs.somalia_rows(page(SOMALIA))
        self.assertEqual(why, "")
        self.assertEqual(len(figures), 18)
        self.assertEqual(figures["Bakool"], 383400)
        self.assertEqual(figures["Hiiraan"], 566400)
        self.assertEqual(figures["Jubbada Hoose"], 632900)

    def test_a_table_inside_a_layout_table_is_read(self):
        html = "<table><tr><td>Layout, 2019 <div>" + page(SOMALIA) + "</div></td></tr></table>"
        figures, why = cs.somalia_rows(html)
        self.assertEqual((len(figures), why), (18, ""))

    def test_every_region_has_a_shape(self):
        self.assertEqual(len(set(cs.SOMALIA.values())), 18)

    def test_a_header_shifted_by_a_cell_is_refused(self):
        # One header cell missing, so "2019" sits over the 2014 figures: every
        # column still adds up, and only the rounding shows the shift.
        head = HEAD[:2] + HEAD[3:] + ("",)
        figures, why = cs.somalia_rows(page(SOMALIA, head))
        self.assertEqual(figures, {})
        self.assertIn("does not sit over its figures", why)

    def test_a_missing_region_writes_nothing(self):
        figures, why = cs.somalia_rows(page([r for r in SOMALIA if r[0] != "Bakool"]))
        self.assertEqual(figures, {})
        self.assertIn("Bakool", why)

    def test_an_inflated_region_fails_the_national_sum(self):
        rows = [r if r[0] != "Hiiraan [ Hiran ]" else r[:5] + ("2,566,400",) for r in SOMALIA]
        figures, why = cs.somalia_rows(page(rows))
        self.assertEqual(figures, {})
        self.assertIn("sum to", why)


TABLE10 = (Path(__file__).parent / "fixtures" / "seychelles_nbs_2019_table10.txt").read_text()


class SeychellesTable10(unittest.TestCase):
    def test_reads_the_outer_islands_mid_2019(self):
        self.assertEqual(cs.seychelles_rows(TABLE10), ({"Other Islands": 574}, ""))

    def test_a_changed_district_fails_the_total(self):
        text = TABLE10.replace("Anse Aux Pins 3,850 3,955 4,008 4,159 4,198 4,236",
                               "Anse Aux Pins 3,850 3,955 4,008 4,159 4,198 5,236")
        figures, why = cs.seychelles_rows(text)
        self.assertEqual(figures, {})
        self.assertIn("Total row", why)

    def test_no_table_writes_nothing(self):
        figures, why = cs.seychelles_rows("Nothing here")
        self.assertEqual(figures, {})
        self.assertIn("Table 10", why)


if __name__ == "__main__":
    unittest.main()
