"""Europe, read from each unit's own Wikipedia article.

The fixtures are wikitext as the runner's probe printed it -- a Slovak
district's two tables, a North Macedonian municipality's two-census table --
cut down to what the reader looks at. Every refusal rule has a test, because
the refusals are what make the figures that do get written worth having.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import europe_wiki as m  # noqa: E402

CITE = ('<ref>[https://census2011.statistics.sk/tabulky.html '
        'Sčítanie obyvateľov, domov a bytov 2011. Výsledky]</ref>')

SK_ETHNIC = """== Národnostné zloženie ==
Podľa sčítania.{cite}
{{| class="wikitable"
! národnosť !! počet !! %
|-
| slovenská || 69 283 || 91,41
|-
| rómska || 2 254 || 2,97
|-
| rusínska a ukrajinská || 3 150 || 4,16
|-
| maďarská || 51 || 0,07
|-
| česká a moravská || 227 || 0,30
|-
| iná a nezistená || 825 || 1,09
|}}
"""

SK_RELIGION = """== Náboženské zloženie ==
Podľa sčítania.{cite}
{{| class="wikitable"
! náboženstvo !! počet (2011) !! % (2011)
|-
| Rímskokatolícka cirkev || 46 512 || 61,37
|-
| Gréckokatolícka cirkev || 14 467 || 19,09
|-
| Pravoslávna cirkev || 2 000 || 2,64
|-
| bez vyznania || 5 000 || 6,60
|-
| nezistené || 7 800 || 10,30
|}}
"""

# Two censuses side by side: count, share, count, share, and one row that
# carries only the newer pair.
MK = """== Demographics ==
The 2021 census.<ref>{{cite web |url=https://www.stat.gov.mk/pdf/2022/2.1.22.10-mk-en.pdf
|title=Попис на населението 2021}}</ref>
{| class="wikitable"
! !! colspan=2 | 2002 !! colspan=2 | 2021
|-
! !! Number !! % !! Number !! %
|-
| TOTAL || 95,385 || 100 || 85,164 || 100
|-
| Macedonians || 84,616 || 88.71 || 69,182 || 81.23
|-
| Albanians || 4,164 || 4.37 || 4,018 || 4.72
|-
| Roma || 2,613 || 2.74 || 2,890 || 3.39
|-
| Vlachs || 1,270 || 1.33 || 1,205 || 1.41
|-
| Turks || 1,610 || 1.69 || 1,174 || 1.38
|-
| Serbs || 541 || 0.57 || 359 || 0.42
|-
| Bosniaks || 21 || 0.02 || 49 || 0.05
|-
| Others || 550 || 0.57 || 782 || 0.94
|-
| Persons for whom data are taken from administrative sources || || || 5,505 || 6.46
|}
"""

SVK = m.SPECS["SVK"]
MKD = m.SPECS["MKD"]
ETHNIC, RELIGION = m.SK_FIELDS


def sk(body: str, cite: str = CITE) -> str:
    return body.format(cite=cite)


class WhatIsRead(unittest.TestCase):
    def test_a_slovak_district_reads_both_fields(self):
        text = sk(SK_ETHNIC) + sk(SK_RELIGION)
        got, why = m.read_field(text, ETHNIC, SVK, "Bardejov (okres)", "sk")
        self.assertEqual(why, "")
        self.assertEqual(got["year"], 2011)
        self.assertEqual(got["kind"], "census")
        self.assertEqual(got["dated"], "its citation")
        self.assertEqual(got["rows"][0], {"group": "Slovak", "pct": 91.41})
        got, why = m.read_field(text, RELIGION, SVK, "Bardejov (okres)", "sk")
        self.assertEqual(why, "")
        self.assertEqual({r["group"] for r in got["rows"]},
                         {"Roman Catholic", "Greek Catholic", "Orthodox",
                          "No religion", "Not stated"})

    def test_a_comma_is_the_decimal_mark_where_the_country_says_so(self):
        self.assertEqual(m.number("91,41", ","), 91.41)
        self.assertEqual(m.number("69 283", ","), 69283.0)
        self.assertEqual(m.number("112.084", ","), 112084.0)
        self.assertEqual(m.number("77,956", "."), 77956.0)
        self.assertEqual(m.number("77.1%", "."), 77.1)
        self.assertIsNone(m.number("n/a", "."))

    def test_a_flag_before_the_label_is_not_part_of_it(self):
        self.assertEqual(m.label_for("Slovensko slovenská", m.SK_ETHNICITY)[0],
                         "Slovak")
        self.assertEqual(m.label_for("22px rómska", m.SK_ETHNICITY)[0], "Romani")
        self.assertIsNone(m.label_for("marťanská", m.SK_ETHNICITY)[0])

    def test_two_censuses_side_by_side_read_the_newer_one(self):
        got, why = m.read_field(MK, m.MK_ETHNICITY, MKD, "Bitola Municipality", "en")
        self.assertEqual(why, "")
        self.assertEqual(got["year"], 2021)
        self.assertEqual(got["rows"][0], {"group": "Macedonian", "pct": 81.23})

    def test_a_row_of_only_one_census_is_dropped_and_said_so(self):
        got, _ = m.read_field(MK, m.MK_ETHNICITY, MKD, "Bitola Municipality", "en")
        self.assertIn("carry figures for only one of the censuses", got["remark"])
        self.assertIn(m.REMAINDER, {r["group"] for r in got["rows"]})


class WhatIsRefused(unittest.TestCase):
    def refusal(self, text, spec=ETHNIC, country=SVK):
        got, why = m.read_field(text, spec, country, "T", "sk")
        self.assertIsNone(got)
        return why

    def test_a_table_with_no_citation_is_not_read(self):
        self.assertIn("cites nothing", self.refusal(sk(SK_ETHNIC, cite="")))

    def test_a_citation_that_cannot_be_dated_is_not_read(self):
        undated = "<ref>[https://statistics.sk/tabulky.html Výsledky]</ref>"
        self.assertIn("no date", self.refusal(sk(SK_ETHNIC, cite=undated)))

    def test_an_undated_citation_beside_a_dated_header_reads_and_says_so(self):
        undated = "<ref>[https://statistics.sk/tabulky.html Výsledky]</ref>"
        got, why = m.read_field(sk(SK_RELIGION, cite=undated), RELIGION, SVK,
                                "T", "sk")
        self.assertEqual(why, "")
        self.assertEqual(got["year"], 2011)
        self.assertEqual(got["dated"], "the table's own header")
        note = m.field_fields(got, RELIGION, SVK, "T", "sk")["religion_note"]
        self.assertIn("citation carries no year", note)

    def test_a_reference_the_page_never_defines_is_a_citation_to_nothing(self):
        named = '<ref name="scitanie" />'
        self.assertIn("cites nothing", self.refusal(sk(SK_ETHNIC, cite=named)))

    def test_a_label_the_reader_has_no_entry_for_refuses_the_table(self):
        text = sk(SK_ETHNIC).replace("| rómska ", "| marťanská ")
        why = self.refusal(text)
        self.assertIn("no entry for", why)
        self.assertIn("marťanská", why)

    def test_shares_that_are_not_a_composition_are_not_read(self):
        text = sk(SK_ETHNIC).replace("|| 91,41", "|| 41,41")
        self.assertIn("add to 50", self.refusal(text))

    def test_a_missing_section_says_which_one(self):
        elsewhere = sk(SK_ETHNIC).replace("== Národnostné zloženie ==",
                                          "== Doprava ==")
        self.assertIn("no section matching", self.refusal(elsewhere))

    def test_a_table_whose_header_is_not_the_known_one_is_refused(self):
        text = sk(SK_ETHNIC).replace("! národnosť !!", "! skupina !!")
        self.assertIn("reorganised", self.refusal(text))

    def test_a_list_of_languages_is_not_a_composition(self):
        """A section that names languages and gives a share for none of them
        has no row to read, and nothing is invented from it."""
        text = ("== Národnostné zloženie ==\n"
                "Hovorí sa tu po slovensky, po maďarsky a po rómsky." + CITE
                + '\n{| class="wikitable"\n! národnosť !! poznámka\n|-\n'
                  "| slovenská || väčšina\n|-\n| maďarská || menšina\n|-\n"
                  "| rómska || menšina\n|}\n")
        self.assertIn("no row this reader could read", self.refusal(text))


class WhereTheArticleIs(unittest.TestCase):
    def test_every_slovak_district_matches_its_own_spelling(self):
        names = [u["name"][len("District of "):] for u in
                 m.read_json(m.SITE / "admin2" / "SVK.json", [])]
        matched, refused = m.match_spellings(names, list(m.SK_DISTRICTS))
        self.assertEqual(refused, {})
        self.assertEqual(len(matched), 79)
        self.assertEqual(matched["Banskk vtiavnica"], "Banská Štiavnica")
        self.assertEqual(matched["Bonovce nad Bebra*"], "Bánovce nad Bebravou")
        self.assertEqual(matched["Gala"], "Šaľa")
        self.assertEqual(matched["Galanta"], "Galanta")
        self.assertEqual(matched["Kovice - okolie"], "Košice-okolie")

    def test_an_ascii_letter_must_be_the_same_letter(self):
        self.assertTrue(m.could_be("Bansks Bystrica", "Banská Bystrica"))
        self.assertFalse(m.could_be("Banskx Rystrica", "Banská Bystrica"))
        self.assertFalse(m.could_be("Banská Bystrica x", "Banská Bystrica"))

    def test_a_spelling_that_fits_two_names_is_refused_not_guessed(self):
        matched, refused = m.match_spellings(["Nov"], ["Nová Baňa", "Nové Mesto"])
        self.assertEqual(matched, {})
        self.assertIn("fits 2", refused["Nov"])

    def test_a_spelling_that_fits_nothing_says_so(self):
        _, refused = m.match_spellings(["Atlantis"], list(m.SK_DISTRICTS))
        self.assertIn("none of the country's own unit names", refused["Atlantis"])

    def test_a_digraph_romanisation_folds_to_the_letter_it_stands_for(self):
        """North Macedonia's boundary file spells the Cyrillic out in English
        digraphs, which is a longer string than the name it came from."""
        self.assertEqual(m.folded("Bogdantsi"), m.folded("Bogdanci"))
        self.assertEqual(m.folded("Arachinovo"), m.folded("Aračinovo"))
        self.assertEqual(m.folded("Cheshinovo - Obleshevo"),
                         m.folded("Češinovo-Obleševo"))
        self.assertEqual(m.folded("Arandjelovac"), m.folded("Aranđelovac"))
        self.assertNotEqual(m.folded("Bitola"), m.folded("Butel"))

    def test_the_extra_word_is_not_part_of_the_name(self):
        self.assertEqual(m.trimmed("Ada Municipality", r"\s+Municipality$"), "Ada")
        self.assertEqual(m.trimmed("Ada, Serbia", r",\s*Serbia$"), "Ada")


class ThePopulationGuard(unittest.TestCase):
    def test_percentages_have_nothing_to_weigh(self):
        reading = {"counts": {"a": 82.6, "b": 17.4}}
        self.assertTrue(m.fits_population(
            reading, {"population": {"value": 57687}}, "T", ETHNIC))

    def test_shares_that_add_to_exactly_a_hundred_still_pass(self):
        reading = {"counts": {"a": 50.0, "b": 30.0, "c": 20.0}}
        self.assertTrue(m.fits_population(
            reading, {"population": {"value": 600000}}, "T", ETHNIC))

    def test_a_table_about_the_town_is_not_read_onto_the_district(self):
        reading = {"counts": {"a": 9000.0, "b": 500.0}}
        self.assertFalse(m.fits_population(
            reading, {"population": {"value": 101100}}, "T", ETHNIC))

    def test_a_shape_with_no_population_cannot_refuse_anything(self):
        reading = {"counts": {"a": 9000.0, "b": 500.0}}
        self.assertTrue(m.fits_population(
            reading, {"population": {"status": "not_available"}}, "T", ETHNIC))


class WhatACitationIs(unittest.TestCase):
    def test_a_census_is_told_from_an_office_and_from_a_registry(self):
        self.assertEqual(m.describe_citation(
            "[https://census2011.statistics.sk/x Sčítanie 2011]")[0], "census")
        self.assertEqual(m.describe_citation(
            "{{cite web|url=https://www.stat.gov.rs/x|title=Statistical "
            "yearbook|year=2020}}")[0], "office")
        self.assertEqual(m.describe_citation(
            "{{cite web|url=https://x.gov/y|title=Population register 2019}}"
        )[0], "registry")

    def test_the_year_never_comes_from_an_access_date(self):
        kind, year, _ = m.describe_citation(
            "{{cite web|url=https://x.gov/y|title=Naselenie|access-date=2024-01-01}}")
        self.assertIsNone(year)

    def test_a_bare_link_is_dated_by_its_own_text(self):
        _, year, _ = m.describe_citation(
            "[https://census2011.statistics.sk/x Sčítanie obyvateľov 2011]")
        self.assertEqual(year, 2011)


if __name__ == "__main__":
    unittest.main()


class ThePatternIsNotUsedWhereThereIsAList(unittest.TestCase):
    """The boundary file's transliteration is never an article title when
    the country's own list of names is available.

    It was, at first, and that made the list dead code: every unit got
    "{name} Municipality" built from the spelling in the boundary file, so
    North Macedonia's reader asked for "Bogdantsi Municipality" while the
    category had already said the article is "Bogdanci Municipality".
    """

    def setUp(self):
        self.calls = []
        self.members = m.category_members
        m.category_members = lambda category, lang: (
            self.calls.append((category, lang))
            or ["Bogdanci Municipality", "Brvenica Municipality"])

    def tearDown(self):
        m.category_members = self.members

    def test_a_listed_level_takes_its_titles_from_the_list(self):
        level = m.Level(level="admin2", lang="en", title="{name} Municipality",
                        match="folded",
                        category="Category:Municipalities of North Macedonia",
                        article_trim=r"\s+Municipality(,.*)?$",
                        fields=(m.MK_ETHNICITY,))
        titles, refused = m.article_titles(m.SPECS["MKD"], level,
                                           ["Bogdantsi", "Brvenitsa", "Atlantis"])
        self.assertEqual(titles, {"Bogdantsi": "Bogdanci Municipality",
                                  "Brvenitsa": "Brvenica Municipality"})
        self.assertIn("none of the names on the country's own list",
                      refused["Atlantis"])
        self.assertEqual(self.calls, [("Category:Municipalities of North Macedonia", "en")])


class TwoLabelsInOneCell(unittest.TestCase):
    """A spanning cell leaks the group it spans into the row under it.

    Blagoevgrad's ethnic table has one "Drugi" cell spanning seven rows, and
    the flattener hands the first of them over as "Drugi Rusnatsi" with one
    pair of figures in it. Which of the two the figures belong to is not
    something the table says, so the outer label wins: it is the residual,
    and a residual cannot overstate a people.
    """

    def test_the_outer_label_of_a_spanning_cell_wins(self):
        self.assertEqual(m.label_for("Други Руснаци", m.BG_ETHNICITY)[0], "Other")
        self.assertEqual(m.label_for("Руснаци", m.BG_ETHNICITY)[0], "Russian")

    def test_a_flag_is_still_dropped_from_the_front(self):
        self.assertEqual(m.label_for("Slovensko slovenská", m.SK_ETHNICITY)[0],
                         "Slovak")


class TwoTablesUnderOneHeading(unittest.TestCase):
    """Where a section prints the same table once per census and says so
    nowhere in either header, nothing is read."""

    SECTION = """== Етнически състав ==
Преброяване.<ref>[http://pop-stat.mashke.org/bulgaria-ethnic-loc2011.htm Етнически състав 2011 census]</ref>
{one}
{two}
"""
    TABLE = """{{| class="wikitable"
! !! Численост !! Дял (в %)
|-
| Общо || {total} || 100.00
|-
| Българи || 1 || {bulgarians}
|-
| Цигани || 1 || {roma}
|}}
"""

    def table(self, total, bulgarians, roma):
        return self.TABLE.format(total=total, bulgarians=bulgarians, roma=roma)

    def test_one_table_is_read(self):
        text = self.SECTION.format(one=self.table("17 994", "90.20", "9.80"), two="")
        spec = next(f for f in m.BG_MUNICIPALITY if f.field == "ethnicity")
        got, why = m.read_field(text, spec, m.SPECS["BGR"], "T", "bg")
        self.assertEqual(why, "")
        self.assertEqual(got["year"], 2011)
        self.assertEqual(got["kind"], "compilation")
        note = m.field_fields(got, spec, m.SPECS["BGR"], "T", "bg")["ethnicity_note"]
        self.assertIn("third-party compilation", note)

    def test_two_tables_refuse_the_unit(self):
        text = self.SECTION.format(one=self.table("17 994", "90.20", "9.80"),
                                   two=self.table("19 118", "80.91", "19.09"))
        spec = next(f for f in m.BG_MUNICIPALITY if f.field == "ethnicity")
        got, why = m.read_field(text, spec, m.SPECS["BGR"], "T", "bg")
        self.assertIsNone(got)
        self.assertIn("which census each is", why)


class TheYearInAUrl(unittest.TestCase):
    """A citation's year is often glued to a word in its URL, and a word
    boundary finds none of them.

    Every Serbian district was refused for want of a date that was in its
    citation all along: the Statistical Office publishes at
    publikacije.stat.gov.rs/G2023/ and popis2022.stat.gov.rs. What must not
    happen instead is reading four digits out of the middle of an
    identifier, so a year may touch letters and not digits.
    """

    def year(self, body):
        return m.describe_citation(body)[1]

    def test_a_year_glued_to_a_word_is_read(self):
        self.assertEqual(self.year(
            "{{Cite web|url=https://popis2022.stat.gov.rs/media/x.pdf|title=Попис}}"),
            2022)
        self.assertEqual(self.year(
            "{{Cite web|url=https://publikacije.stat.gov.rs/G2023/Pdf/G20234001.pdf"
            "|title=Национална припадност}}"), 2023)

    def test_four_digits_inside_an_identifier_are_not_a_year(self):
        self.assertIsNone(self.year(
            "{{cite web|url=http://miris.eurac.edu/do/blob.html?serial=1039432230349"
            "|title=Minorities}}"))


class ACitationInAnotherLanguage(unittest.TestCase):
    """bg.wikipedia's {{Цитат уеб}} takes заглавие and уеб_адрес.

    Reading only the English parameter names left every Bulgarian citation
    looking like a bare body with no title and no URL, and all 28 provinces'
    mother-tongue tables were refused as undated.
    """

    CITE = ("{{Цитат уеб| уеб_адрес = http://www.nsi.bg/Census/MotherTongue.htm "
            "| заглавие = Население към 1.03.2001 г. по области и майчин език "
            "| дата_на_достъп = 2024-05-01}}")

    def test_the_localised_title_is_found_and_dated(self):
        kind, year, cited = m.describe_citation(self.CITE)
        self.assertEqual(year, 2001)
        self.assertTrue(cited.startswith("Население"))

    def test_the_access_date_is_still_never_the_year(self):
        kind, year, _ = m.describe_citation(
            "{{Цитат уеб| уеб_адрес = http://www.nsi.bg/x | заглавие = Население "
            "| дата_на_достъп = 2024-05-01}}")
        self.assertIsNone(year)

    def test_a_word_hyphenated_by_the_table_width_is_one_word(self):
        self.assertEqual(m.label_for("Не се само- определят", m.BG_ETHNICITY)[0],
                         "Not declared")


class TwoWaysASectionCanBeEmpty(unittest.TestCase):
    """A heading with no table at all is a different fact from a heading with
    a table this reader does not know, and a reader of the map should not
    have to guess which happened.

    Montenegro's municipality articles have a Demographics heading with prose
    under it and the only table on the page is the council's party seats.
    """

    def why(self, body):
        _, _, why = m.find_table(body, ETHNIC)
        return why

    def test_a_heading_with_no_table_says_the_article_publishes_none(self):
        self.assertIn("no table in it at all", self.why(
            "== Obyvateľstvo ==\nV okrese žije veľa ľudí.\n"))

    def test_a_heading_with_a_table_of_another_kind_says_so(self):
        self.assertIn("header this reader does not know", self.why(
            '== Obyvateľstvo ==\n{| class="wikitable"\n! strana !! kreslá\n|-\n'
            "| SNS || 12\n|-\n| SaS || 5\n|}\n"))

    def test_no_heading_at_all_names_the_pattern(self):
        self.assertIn("no section matching", self.why("== Doprava ==\nCesty.\n"))


class TheMarkThatSeparatesAFraction(unittest.TestCase):
    """Which mark it is is a fact about the country, except where it is not.

    Bulgaria's provinces write "89.72" and its municipalities write "64,81",
    in the same edition and under the same heading, and 110 municipalities
    were refused for it. The declared mark is tried first and the other one
    after it, and the arbiter is the check that would otherwise refuse the
    table: only a reading whose shares add to about a hundred is taken, and
    reading "64,81" as six thousand adds to ten thousand.
    """

    TABLE = """== Вероизповедания ==
Преброяване.<ref>{{Цитат уеб| уеб_адрес = http://pop-stat.mashke.org/x.htm
| заглавие = Religious composition: 2011 census}}</ref>
{| class="wikitable"
! !! Численост !! Дял (в %)
|-
| Общо || 20 426 || 100,00
|-
| Православие || 13 240 || 64,81
|-
| Нямат || 827 || 4,04
|-
| Непоказано || 4 973 || 31,15
|}
"""

    def test_a_comma_fraction_is_read_where_the_point_gives_no_composition(self):
        spec = next(f for f in m.BG_MUNICIPALITY if f.field == "religion")
        got, why = m.read_field(self.TABLE, spec, m.SPECS["BGR"], "T", "bg")
        self.assertEqual(why, "")
        self.assertEqual(got["rows"][0], {"group": "Orthodox", "pct": 64.81})
        self.assertIn('writes a fraction with ","', got["remark"])
        self.assertEqual(got["kind"], "compilation")


class TheYearOfTheColumnRead(unittest.TestCase):
    """Where a table prints two censuses and cites the older one first, the
    figures read are the newer column's and the date must be the newer.

    Blagoevgrad's ethnic table prints 2001 and 2011 side by side and cites
    the 2001 release first, so the 2011 column -- which is the one read --
    was being stamped 2001. A figure dated by the wrong census is worse
    than no figure.
    """

    TABLE = """== Етнически състав ==
Преброявания.<ref>{{Цитат уеб| уеб_адрес = http://www.nsi.bg/Census/Ethnos.htm
| заглавие = Население към 1.03.2001 г. по области и етническа група}}</ref>
{| class="wikitable"
! !! colspan=2 | Численост !! colspan=2 | Дял (в %)
|-
! 2001 !! 2011 !! 2001 !! 2011
|-
| Общо || 341 173 || 323 552 || 100.00 || 100.00
|-
| Българи || 286 491 || 251 097 || 83.97 || 77.60
|-
| Турци || 31 857 || 17 027 || 9.33 || 5.26
|-
| Цигани || 12 405 || 9739 || 3.63 || 3.01
|-
| Неотговорили || 659 || 39 996 || 0.19 || 14.13
|}
"""

    def test_the_header_year_of_the_column_read_is_the_record_s_year(self):
        spec = next(f for f in m.BG_PROVINCE if f.field == "ethnicity")
        got, why = m.read_field(self.TABLE, spec, m.SPECS["BGR"], "T", "bg")
        self.assertEqual(why, "")
        self.assertEqual(got["year"], 2011)
        self.assertEqual(got["dated"], "the table's own header")
        self.assertEqual(got["rows"][0], {"group": "Bulgarian", "pct": 77.6})

    def test_a_citation_dated_otherwise_is_said_so_on_the_record(self):
        spec = next(f for f in m.BG_PROVINCE if f.field == "ethnicity")
        got, _ = m.read_field(self.TABLE, spec, m.SPECS["BGR"], "T", "bg")
        self.assertIn("The citation is for 2001", got["remark"])
        note = m.field_fields(got, spec, m.SPECS["BGR"], "T", "bg")["ethnicity_note"]
        self.assertIn("2011", note)
        self.assertIn("The citation is for 2001", note)
