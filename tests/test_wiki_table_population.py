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

BAHAMAS = """== New Providence ==
{| class="wikitable"
! Name !! Population (2022)
|-
| Killarney || 17,679
|}
== Demographics ==
The 2022 census.<ref name=":0">{{Cite web |title=Census of The Bahamas 2022 |url=u}}</ref>
{| class="wikitable"
! District(s) or Other Area !! Island Group !! Population
|-
| North Eleuthera || Eleuthera || 3,923
|-
| South Eleuthera + Central Eleuthera || Eleuthera || 5,324
|}
== Types of councils ==
{| class="wikitable"
! Island Group !! Population
|-
| Eleuthera || 12,717<ref name=":0" />
|}
"""


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

    def test_an_undated_column_is_dated_by_its_sections_citation(self):
        self.assertEqual(wt.cell(BAHAMAS, "North Eleuthera", "^Population$", 2022,
                                 cite="Census of The Bahamas 2022"), (3923, ""))

    def test_an_undated_column_with_no_citation_is_refused(self):
        value, why = wt.cell(BAHAMAS, "Eleuthera", "^Population$", 2022,
                             cite="Census of The Bahamas 2022")
        self.assertIsNone(value)
        self.assertIn("cites nothing", why)

    def test_a_group_row_is_not_a_member(self):
        value, _ = wt.cell(BAHAMAS, "Central Eleuthera", "^Population$", 2022,
                           cite="Census of The Bahamas 2022")
        self.assertIsNone(value)

    def test_every_citation_names_its_figures_year(self):
        for (iso3, name), fig in wt.FIGURES.items():
            for term in fig.terms:
                if term.cite:
                    self.assertIn(str(fig.year), term.cite, (iso3, name))


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
        self.assertEqual(len(row["sources"]), 1)


DAR = """{| class="wikitable"
! colspan=3 | Districts of Dar es Salaam Region
|-
! District !! Population (2022) !! Area km<sup>2</sup>
|-
| Ilala District || 1,649,912 || 210
|-
| '''Dar es Salaam Region''' || '''5,383,728''' || 1,393
|}"""

# As the page renders the list of Ivory Coast's districts: the district name
# spans four columns and the district figure two.
IVORY = """<table><tr><th>Map no.</th><th>District</th><th>District capital</th><th>Regions</th>
<th>Region seat</th><th>Population<br>(District)</th><th>Population Regions</th><th>Area KM²</th></tr>
<tr><th>1</th><td colspan="4">Abidjan (District Autonome d'Abidjan)</td>
<td colspan="2">4,707,404</td><td>2,119 (818)</td></tr>
<tr><th>13</th><td colspan="4">Yamoussoukro (District Autonome de Yamoussoukro)</td>
<td colspan="2">355,573</td><td>3,500 (1,350)</td></tr></table>"""

CAPE = """<table><tr><th>Map #</th><th>Municipality</th><th>Island(s)</th><th>Area (km<sup>2</sup>)</th>
<th>Population<br>(2010 census)<sup>[2]</sup></th><th>Population<br>(2021 Census)<sup>[3]</sup></th></tr>
<tr><td>72</td><td>Municipality of Santa Catarina</td><td>Santiago</td><td>242.6</td><td>43,297</td><td>37,472</td></tr>
<tr><td>83</td><td>Municipality of Santa Catarina do Fogo</td><td>Fogo</td><td>153.0</td><td>5,299</td><td>4,725</td></tr></table>"""


def rendered_as(html):
    return lambda title: (html, title)


class MoreTables(unittest.TestCase):
    def test_a_caption_row_above_the_header_is_passed_over(self):
        self.assertEqual(wt.cell(DAR, "Dar es Salaam Region", r"Population \(2022\)", 2022),
                         (5383728, ""))

    def test_a_rendered_table_expands_merged_cells(self):
        # The list's undated district column, read as the page renders it.
        fig = wt.Figure(
            year=None,
            terms=(wt.Term("Districts of Ivory Coast", row="Yamoussoukro", key=r"^District$",
                           column=r"^Population \(District\)", rendered=True),),
            source="English Wikipedia, Districts of Ivory Coast; the list gives no year",
            note="The district's row: {terms}.")
        row = wt.figure_row("CIV", "Yamoussoukro", fig, "SHAPE", renderer=rendered_as(IVORY))
        self.assertEqual(row["population"]["value"], 355573)
        self.assertNotIn("year", row["population"])
        self.assertIn("gives no year", row["population"]["source"])

    def test_yamoussoukro_is_the_districts_2021_census_count(self):
        # The infobox's population_total is the district's (both departments);
        # its blank1 is the city's and is not read.
        infobox = ("{{Infobox settlement\n| population_as_of = 14 Dec. 2021 census\n"
                   "| population_blank1 = 279977\n| population_blank1_title = City\n"
                   "| population_total = 422072\n}}\n")
        fig = wt.FIGURES[("CIV", "District Autonome De Yamoussoukro")]
        row = wt.figure_row("CIV", "District Autonome De Yamoussoukro", fig, "SHAPE",
                            fetcher=lambda title, lang: (infobox, title))
        self.assertEqual((row["population"]["value"], row["population"]["year"]),
                         (422072, 2021))
        self.assertIn("Attiégouakro", row["population"]["note"])
        self.assertNotIn("3,500", row["population"]["note"])
        # An infobox dated to another census is refused, not read as 2021's.
        older = infobox.replace("2021 census", "2014 census")
        self.assertIsNone(wt.figure_row("CIV", "District Autonome De Yamoussoukro", fig,
                                        "SHAPE", fetcher=lambda title, lang: (older, title)))

    def test_tarrafal_is_read_from_its_own_row(self):
        page = CAPE.replace("</table>", (
            "<tr><td>80</td><td>Municipality of Tarrafal</td><td>Santiago</td><td>120.8</td>"
            "<td>18,565</td><td>16,620</td></tr><tr><td>90</td><td>Municipality of Tarrafal "
            "de São Nicolau</td><td>São Nicolau</td><td>119.0</td><td>5,237</td><td>4,825</td>"
            "</tr></table>"))
        row = wt.figure_row("CPV", "Tarrafal", wt.FIGURES[("CPV", "Tarrafal")], "SHAPE",
                            renderer=rendered_as(page))
        self.assertEqual((row["population"]["value"], row["population"]["year"]), (16620, 2021))

    def test_an_undated_reading_refuses_a_dated_column(self):
        term = wt.Term("X", row="Municipality of Santa Catarina", column="Population",
                       rendered=True, key="^Municipality$")
        value, _, why = wt.term_value(term, None, renderer=rendered_as(CAPE))
        self.assertIsNone(value)

    def test_a_municipality_is_its_own_row_not_a_longer_name(self):
        fig = wt.FIGURES[("CPV", "Santa Catarina")]
        row = wt.figure_row("CPV", "Santa Catarina", fig, "SHAPE", renderer=rendered_as(CAPE))
        self.assertEqual((row["population"]["value"], row["population"]["year"]), (37472, 2021))
        fig = wt.FIGURES[("CPV", "Santa Catarina do Fogo")]
        row = wt.figure_row("CPV", "Santa Catarina do Fogo", fig, "SHAPE",
                            renderer=rendered_as(CAPE))
        self.assertEqual(row["population"]["value"], 4725)

    def test_a_bracketed_gloss_is_not_a_different_name(self):
        self.assertTrue(wt.labelled("Lagunes (District des Lagunes)", "Lagunes"))
        self.assertFalse(wt.labelled("Maputo City", "Maputo"))


if __name__ == "__main__":
    unittest.main()
