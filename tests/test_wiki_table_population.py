"""Populations by declared arithmetic over Wikipedia tables and infoboxes."""
import unittest

from scripts.fetch_census import wiki_table_population as wt

ETHNIC = """== Ethnic groups ==
{| class="wikitable"
! rowspan=2|Ethnic group !! colspan=2|Census 2009 !! colspan=2|Census 2019<ref>x</ref>
|-
! Number !! % !! Number !! %
|-
| Azerbaijanis || 8,172,809 || 91.6 || 9,436,123 || 94.8
|-
| '''Total''' || colspan=2|8,922,447 || colspan=2|9,951,409
|}
"""

NAKHCHIVAN = """{{Infobox settlement
| name = Nakhchivan Autonomous Republic
| population_census_year = [[Census in Azerbaijan|2019]]
| population_census = 458,910
}}
Text."""

GAMBIA = """{| class="wikitable"
! Name !! Capital !! Population (2013) !! Population (2024)
|-
| [[Upper River Division|Upper River]] || Basse Santa Su || 237,220 || 261,160
|-
| Lower River || Mansa Konko || 81,042 || 90,624
|}"""

PROVINCES = """{| class="wikitable sortable"
! Map Key !! Province !! Capital !! Population (2007 census) !! Population (2017 census)
|-
| 10 || [[Maputo|Maputo City]] || Maputo || 1,094,628 || 1,101,170
|-
| 11 || [[Maputo Province|Maputo]] || [[Matola]] || 1,205,709 || 2,507,098
|}"""


def pages(**texts):
    return lambda title, lang: (texts.get(title, ""), title)


class ACell(unittest.TestCase):
    def test_reads_the_row_under_the_named_year(self):
        self.assertEqual(wt.cell(GAMBIA, "Upper River", r"Population \(2024\)", 2024),
                         (261160, ""))

    def test_a_merged_cell_row_lines_up_with_its_own_header(self):
        # The header has one cell per census and so does the Total row.
        self.assertEqual(wt.cell(ETHNIC, "Total", "Census 2019", 2019), (9951409, ""))

    def test_a_row_that_cannot_be_lined_up_is_refused(self):
        value, why = wt.cell(ETHNIC, "Azerbaijanis", "Census 2019", 2019)
        self.assertIsNone(value)
        self.assertIn("cannot be lined up", why)

    def test_a_column_that_does_not_name_the_year_is_refused(self):
        value, why = wt.cell(GAMBIA, "Upper River", r"Population \(2013\)", 2024)
        self.assertIsNone(value)
        self.assertIn("does not name 2024", why)

    def test_a_missing_row_is_refused(self):
        value, why = wt.cell(GAMBIA, "Central River", r"Population \(2024\)", 2024)
        self.assertIsNone(value)
        self.assertIn("0 tables", why)


class AFigure(unittest.TestCase):
    def test_contiguous_azerbaijan_is_the_census_total_less_nakhchivan(self):
        fig = wt.FIGURES[("AZE", "Contiguous Azerbaijan")]
        row = wt.figure_row("AZE", "Contiguous Azerbaijan", fig, "SHAPE", pages(**{
            "Demographics of Azerbaijan": ETHNIC,
            "Nakhchivan Autonomous Republic": NAKHCHIVAN}))
        pop = row["population"]
        self.assertEqual(pop["value"], 9951409 - 458910)
        self.assertEqual(pop["year"], 2019)
        self.assertIn("9,951,409 (the Total row of Demographics of Azerbaijan) less "
                      "458,910 (Nakhchivan Autonomous Republic's infobox)", pop["note"])
        self.assertIn("Artsakh", pop["note"])
        self.assertEqual((row["shape_id"], row["match_by"]), ("SHAPE", "shape_id"))
        self.assertEqual(len(row["sources"]), 2)

    def test_a_term_from_another_year_writes_nothing(self):
        fig = wt.FIGURES[("AZE", "Contiguous Azerbaijan")]
        stale = NAKHCHIVAN.replace("|2019]]", "|2009]]")
        self.assertIsNone(wt.figure_row("AZE", "Contiguous Azerbaijan", fig, "SHAPE", pages(**{
            "Demographics of Azerbaijan": ETHNIC,
            "Nakhchivan Autonomous Republic": stale})))

    def test_a_missing_article_writes_nothing(self):
        fig = wt.FIGURES[("AZE", "Contiguous Azerbaijan")]
        self.assertIsNone(wt.figure_row("AZE", "Contiguous Azerbaijan", fig, "SHAPE",
                                        pages(**{"Demographics of Azerbaijan": ETHNIC})))

    def test_basse_is_the_upper_river_row(self):
        fig = wt.FIGURES[("GMB", "Basse")]
        row = wt.figure_row("GMB", "Basse", fig, "SHAPE",
                            pages(**{"Subdivisions of the Gambia": GAMBIA}))
        self.assertEqual((row["population"]["value"], row["population"]["year"]),
                         (261160, 2024))

    def test_maputo_is_the_city_and_the_province_from_one_column(self):
        fig = wt.FIGURES[("MOZ", "Maputo")]
        row = wt.figure_row("MOZ", "Maputo", fig, "SHAPE",
                            pages(**{"Provinces of Mozambique": PROVINCES}))
        self.assertEqual(row["population"]["value"], 1101170 + 2507098)
        self.assertIn("1,101,170 (the Maputo City row of Provinces of Mozambique) plus "
                      "2,507,098 (the Maputo row", row["population"]["note"])


if __name__ == "__main__":
    unittest.main()
