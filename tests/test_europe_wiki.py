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

import canonical_groups  # noqa: E402
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

    # Two refusals are deliberately gone, by the owner's decision of 22
    # September 2026: an uncited table and an undated one are both read.
    # Refusing them threw away figures that are on the page, over where an
    # editor put a footnote -- twenty-nine Moldovan districts went empty that
    # way while three identical ones were read. What the record does instead
    # is say plainly what it is resting on.

    def test_a_table_with_no_citation_is_read_and_cites_the_article(self):
        got, why = m.read_field(sk(SK_ETHNIC, cite=""), ETHNIC, SVK, "T", "sk")
        self.assertEqual(why, "")
        self.assertTrue(got["rows"], "the figures are on the page; use them")
        self.assertIn("wikipedia.org", got["cited"])
        self.assertIn("cites nothing", got["remark"])

    def test_a_citation_that_cannot_be_dated_is_read_and_says_it_is_undated(self):
        undated = "<ref>[https://statistics.sk/tabulky.html Výsledky]</ref>"
        got, why = m.read_field(sk(SK_ETHNIC, cite=undated), ETHNIC, SVK,
                                "T", "sk")
        self.assertEqual(why, "")
        self.assertTrue(got["rows"])
        self.assertIsNone(got["year"])
        self.assertIn("unknown", got["remark"])
        self.assertEqual(got["dated"], "nothing on the page")

    def test_an_undated_citation_beside_a_dated_header_reads_and_says_so(self):
        undated = "<ref>[https://statistics.sk/tabulky.html Výsledky]</ref>"
        got, why = m.read_field(sk(SK_RELIGION, cite=undated), RELIGION, SVK,
                                "T", "sk")
        self.assertEqual(why, "")
        self.assertEqual(got["year"], 2011)
        self.assertEqual(got["dated"], "the table's own header")
        note = m.field_fields(got, RELIGION, SVK, "T", "sk")["religion_note"]
        self.assertIn("citation carries no year", note)

    def test_a_reference_the_page_never_defines_falls_back_to_the_article(self):
        named = '<ref name="scitanie" />'
        got, why = m.read_field(sk(SK_ETHNIC, cite=named), ETHNIC, SVK,
                                "T", "sk")
        self.assertEqual(why, "")
        self.assertIn("wikipedia.org", got["cited"])

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


class ANoteNeverSaysBothThings(unittest.TestCase):
    """Where a citation carries a year and the table's header carries
    another, the note must not also claim the citation carries none."""

    def test_the_two_sentences_are_exclusive(self):
        spec = next(f for f in m.BG_PROVINCE if f.field == "ethnicity")
        got, _ = m.read_field(TheYearOfTheColumnRead.TABLE, spec,
                              m.SPECS["BGR"], "T", "bg")
        note = m.field_fields(got, spec, m.SPECS["BGR"], "T", "bg")["ethnicity_note"]
        self.assertIn("The citation is for 2001", note)
        self.assertNotIn("The citation carries no year", note)

    def test_an_undated_citation_still_says_so(self):
        undated = "<ref>[https://statistics.sk/tabulky.html Výsledky]</ref>"
        got, _ = m.read_field(sk(SK_RELIGION, cite=undated), RELIGION, SVK,
                              "T", "sk")
        note = m.field_fields(got, RELIGION, SVK, "T", "sk")["religion_note"]
        self.assertIn("The citation carries no year", note)


class ACitationTheInfoboxGivesAndTheTableDoesNot(unittest.TestCase):
    """Moldova's districts transcribe one census into one table shape.

    Three of thirty-two carry the reference on the table; the rest cite it
    once from population_footnotes. Read strictly, twenty-nine districts sat
    empty over where an editor put a <ref>, not over anything about the
    figures.
    """

    TABLE = ("== Ethnic groups ==\n"
             "{| class=wikitable\n"
             "! Ethnic group !! % of total\n|-\n"
             "| Moldovans || 80.6\n|-\n| Ukrainians || 10.0\n|-\n"
             "| Russians || 9.0\n|}\n")
    CITE = ("{{Infobox settlement\n"
            "| population_as_of = [[2024 Moldovan census|2024]]\n"
            "| population_footnotes = <ref>{{cite web"
            "|url=https://statistica.gov.md/en/statistic_indicator_details/60"
            "|title=Final Results of the Population and Housing Census 2024"
            "|publisher=National Bureau of Statistics|year=2026}}</ref>\n"
            "| population_total = 72,775\n}}\n")

    def spec(self, **kw):
        return m.Country(iso3="MDA", out="x.json", decimal=".", census="C",
                         licence="L", levels=(), **kw)

    def test_without_the_opt_in_the_figures_are_still_read(self) -> None:
        # The table is read either way -- the figures are on the page. What
        # the opt-in changes is what the record rests on: the census the
        # infobox names, or the article itself.
        got, why = m.read_field(self.CITE + self.TABLE, m.MD_ETHNICITY,
                                self.spec(), "Cahul District", "en")
        self.assertEqual(why, "")
        self.assertTrue(got["rows"])
        self.assertIn("wikipedia.org", got["cited"])
        self.assertNotIn("statistica.gov.md", got["cited"])

    def test_with_it_the_infobox_citation_stands_in(self) -> None:
        got, why = m.read_field(
            self.CITE + self.TABLE, m.MD_ETHNICITY,
            self.spec(infobox_citation=r"statistica\.gov\.md"),
            "Cahul District", "en")
        self.assertEqual(why, "")
        self.assertIsNotNone(got)

    def test_the_record_says_the_citation_was_borrowed(self) -> None:
        got, _ = m.read_field(
            self.CITE + self.TABLE, m.MD_ETHNICITY,
            self.spec(infobox_citation=r"statistica\.gov\.md"),
            "Cahul District", "en")
        note = " ".join(str(v) for v in got.values())
        self.assertIn("infobox", note,
                      "a borrowed citation has to say it was borrowed")

    def test_a_citation_about_something_else_is_not_borrowed(self) -> None:
        # Still read -- but it must not claim the hill-elevations page as the
        # source of an ethnic composition. It falls back to the article.
        other = ("{{Infobox settlement\n| elevation_footnotes = <ref>"
                 "{{cite web|url=https://example.com/hills|title=Elevations"
                 "}}</ref>\n}}\n")
        got, why = m.read_field(
            other + self.TABLE, m.MD_ETHNICITY,
            self.spec(infobox_citation=r"statistica\.gov\.md"),
            "Cahul District", "en")
        self.assertEqual(why, "")
        self.assertNotIn("example.com", got["cited"])
        self.assertIn("wikipedia.org", got["cited"])

    def test_a_table_with_its_own_citation_does_not_borrow(self) -> None:
        own = self.TABLE.replace(
            "== Ethnic groups ==\n",
            "== Ethnic groups ==\n<ref>{{cite web"
            "|url=https://statistica.gov.md/ro/x|title=Recensamantul 2024"
            "}}</ref>\n")
        got, _ = m.read_field(
            self.CITE + own, m.MD_ETHNICITY,
            self.spec(infobox_citation=r"statistica\.gov\.md"),
            "Cahul District", "en")
        note = " ".join(str(v) for v in got.values())
        self.assertNotIn("infobox", note)


# Every string below is Moldova's own, as the runner's probe printed it from
# the English Wikipedia on 22 September 2026: the capital's three tables, the
# autonomous unit's three, Taraclia's two and Briceni's one. They are cut to
# the rows each test is about and nothing in them is retyped.
MD_CITE = ('<ref name=census24>[https://statistica.gov.md/ro/'
           'rezultatele-finale-ale-recensamantului-populatiei-si-locuintelor-'
           '2024-caracteris-10121_62043.html National Bureau of Statistics: '
           'Final results of the Census 2024]</ref>\n')

CHISINAU_RELIGION = """== Religion ==
""" + MD_CITE + """{| class="wikitable"
! Religious group !! colspan=2 | 2024
|-
! !! Number !! %
|-
| Eastern Orthodoxy || 665,659 || 92.44
|-
| Baptist || 4,705 || 0.65
|-
| Jehovah's Witnesses || 3,868 || 0.54
|-
| Evangelical || 1,864 || 0.26
|-
| Catholic || 1,463 || 0.20
|-
| Pentecostal || 1,458 || 0.20
|-
| Other Christians || 1,161 || 0.16
|-
! Christianity (total) !! 680,178 !! 94.45
|-
| Islam || 2,182 || 0.30
|-
| Other religions || 3,164 || 0.44
|-
| Agnostic / Atheist || 13,409 || 1.86
|-
| No religion || 12,377 || 1.72
|-
| Undeclared || 8,818 || 1.22
|-
! Total !! 720,128 !!
|}
"""

GAGAUZIA_RELIGION = """== Religion ==
""" + MD_CITE + """{| class="wikitable"
! Religion !! 2014 !! 2024
|-
! !! % !! %
|-
| Christians || 99.4 || 99.1
|-
| – Orthodox Christians || 97.2 || 95.9
|-
| – Other Christians || 2.2 || 3.2
|-
| Other religion || 0.5 || 0.3
|-
| Atheism and irreligion || 0.1 || 0.5
|}
"""

TARACLIA_RELIGION = """== Religion ==
""" + MD_CITE + """{| class="wikitable"
! Religion !! colspan=2|2004 !! colspan=2|2014 !! colspan=2|2024
|-
! !! Number !! % !! Number !! % !! Number !! %
|-
| Christians || 41,704 || 96.64 || 35,209 || 94.67 || 26,010 || 98.38
|-
| – Orthodox Christians || 40,701 || 94.31 || 34,480 || 92.72 || 25,160 || 95.17
|-
| – Baptists || 573 || 1.33 || 540 || 1.45 || 596 || 2.25
|-
| – Seventh-day Adventist || 84 || 0.19 || 15 || 0.04 || 30 || 0.11
|-
| – Penticostal || 110 || 0.25 || 73 || 0.2 || 35 || 0.13
|-
| – Old Believers || 3 || 0.01 || 0 || 0 || 3 || 0.01
|-
| – Evangelic Christian || 157 || 0.36 || 47 || 0.13 || 181 || 0.68
|-
| – Lutheran || - || - || 44 || 0.13 || - || -
|-
| – Roman Catholic || 14 || 0.03 || 10 || 0.02 || 5 || 0.01
|-
| – Presbyterian || 62 || 0.14 || - || - || - || -
|-
| Jehovah's Witnesses || - || - || 112 || 0.3 || 99 || 0.37
|-
| Atheist || 141 || 0.33 || 16 || 0.04 || 37 || 0.14
|-
| Judaism || - || - || 1 || 0.01 || - || -
|-
| Muslim || - || - || 21 || 0.5 || 17 || 0.06
|-
| Other || 802 || 1.86 || 5 || 0.01 || 156 || 0.59
|-
| Not Declared || 507 || 1.17 || 1,993 || 5.36 || 116 || 0.43
|-
! Total || 43,154 || 100 || 37,188 || 100 || 26,435 || 100
|}
"""

TARACLIA_ETHNIC = """== Demographics ==
""" + MD_CITE + """{| class="wikitable"
! Ethnicity !! colspan=2|2004 !! colspan=2|2014 !! colspan=2|2024
|-
| Bulgarians || 28,293 || 65.6 || 24,581 || 66.1 || 16,984 || 64.2
|-
| Moldovans{{efn|There is an [[Controversy over ethnic and linguistic identity in Moldova|ongoing controversy]] regarding the ethnic identification of Moldovans}} || 5,980 || 13.9 || 5,206 || 14.0 || 3,901 || 14.8
|-
| Gagauz || 3,587 || 8.3 || 3,346 || 9.0 || 2,730 || 10.3
|-
| Ukrainians || 2,646 || 6.1 || 1,934 || 5.2 || 1,305 || 4.9
|-
| Russians || 2,139 || 5.0 || 1,673 || 4.5 || 1,092 || 4.1
|-
| Romani || - || - || 186 || 0.5 || 152 || 0.6
|-
| Romanians || 29 || 0.1 || 74 || 0.2 || 71 || 0.3
|-
| Other || 480 || 1.1 || - || - || 140 || 0.5
|-
| Not Declared || 0 || 0 || 186 || 0.5 || 60 || 0.2
|-
! Total || 43,154 || 100 || 37,188 || 100 || 26,435 || 100
|}
"""

CHISINAU_LANGUAGE = """== Languages ==
""" + MD_CITE + """{| class="wikitable"
! First language (%) !! 1989 !! 2004 !! 2014 !! Speakers 2024 !! 2024
|-
| Romanian * || – || 37.06 || 43.78 || 343,146 || 47.65
|-
| Moldovan * || 46.15 || 28.56 || 29.55 || 206,594 || 28.69
|-
| Russian || 44.73 || 33.50 || 25.64 || 141,807 || 19.70
|-
| Other languages || 9.12 || 0.88 || 1.03 || 28,581 || 3.97
|}
"""

GAGAUZIA_LANGUAGE = """== Languages ==
""" + MD_CITE + """{| class="wikitable"
! !! colspan=2 | Mother tongue !! colspan=2 | Spoken at home
|-
! Language !! 2014 !! 2024 !! 2014 !! 2024
|-
! !! % !! % !! % !! %
|-
| Gagauz || 79.5 || 77.2 || 54.4 || 48.8
|-
| Russian || 10.4 || 12.1 || 42.5 || 47.3
|-
| Moldovan (Romanian) || 3.9 || 4.7 || 1.1 || 1.7
|-
| Bulgarian || 4.2 || 4.2 || 1.7 || 1.5
|-
| Ukrainian || 1.4 || 1.2 || 0.2 || 0.4
|-
| Others || 0.6 || 0.6 || 0.2 || 0.3
|}
"""

BRICENI_RELIGION = """== Religion ==
""" + MD_CITE + """{| class="wikitable"
! Religion !! Adherents (2004) !! % of total (2004) !! Adherents (2014) !! % of total (2014)
|-
| Christianity: (total) || 65,431 || 83.82% || ||
|-
| Orthodox Christians || 62,181 || 79.69% || 49,958 ||
|-
| Protestants: (total) || 3,218 || 4.12% || ||
|-
| Other religions || 6,184 || 7.92% || 93 ||
|-
| No religion || 3,269 || 4.18% || − || −
|}
"""

MDA = m.SPECS["MDA"]


class AParentAboveItsParts(unittest.TestCase):
    """A religion table that prints a subtotal over the rows it sums.

    All three of Moldova's readable religion tables do it, in two spellings:
    Chisinau writes "Christianity (total)" above Baptist, Evangelical,
    Catholic and the rest, and Gagauzia and Taraclia write "Christians" above
    "– Orthodox Christians" and "– Other Christians", the dash marking the
    child. Reading the parent as well as its parts counts those people twice:
    Gagauzia's table would add to 199.0%, and shares_of refuses that, so the
    unit is lost over it rather than published wrong. These tests hold the
    real rows.
    """

    def test_the_capital_s_subtotal_is_not_a_group(self):
        got, why = m.read_field(CHISINAU_RELIGION, m.MD_RELIGION, MDA,
                                "Chișinău", "en")
        self.assertEqual(why, "")
        self.assertNotIn(94.45, [r["pct"] for r in got["rows"]])
        self.assertAlmostEqual(sum(got["counts"].values()), 99.99, places=2)
        self.assertEqual(got["rows"][0], {"group": "Orthodox", "pct": 92.44})
        self.assertEqual(got["year"], 2024)

    def test_the_dashed_rows_are_read_and_their_parent_is_not(self):
        got, why = m.read_field(GAGAUZIA_RELIGION, m.MD_RELIGION, MDA,
                                "Gagauzia", "en")
        self.assertEqual(why, "")
        self.assertEqual({r["group"]: r["pct"] for r in got["rows"]},
                         {"Orthodox": 95.9, "Other Christian": 3.2,
                          "No religion": 0.5, "Other religion": 0.3})
        self.assertEqual(got["year"], 2024)

    def test_a_parent_read_with_its_parts_would_not_be_a_composition(self):
        # What the skip is for, said in figures: with "Christians" left in,
        # the table adds to 199% and nothing is published for the unit.
        loose = m.Composition(
            field="religion", section=r"religio", header=r"religio",
            value=-1, columns=True,
            labels={**m.MD_RELIGION_LABELS, "christians": "Other Christian"},
            skip=m.TOTALS + m.MD_HEADER_ROWS)
        counts, _, why = m.read_rows(m.tables(GAGAUZIA_RELIGION)[0], loose, ".")
        self.assertEqual(why, "")
        self.assertAlmostEqual(sum(counts.values()), 199.0, places=2)
        rows, bad, _ = m.shares_of(counts)
        self.assertEqual(rows, [])
        self.assertIn("199.00", bad)
        got, _ = m.read_field(GAGAUZIA_RELIGION, loose, MDA, "Gagauzia", "en")
        self.assertIsNone(got)


class AColumnACensusHasNoFigureIn(unittest.TestCase):
    """Taraclia prints three censuses side by side and writes "-" where a
    faith had nobody, so the last *figure* in a row and the last *column* of
    it are different things."""

    def test_the_column_is_read_and_not_the_last_figure(self):
        got, why = m.read_field(TARACLIA_RELIGION, m.MD_RELIGION, MDA,
                                "Taraclia District", "en")
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got["rows"]}
        # 0.13 and 0.14 are the Lutherans' 2014 and the Presbyterians' 2004,
        # which a reader counting figures would have published as 2024.
        self.assertNotIn("Lutheran", shares)
        self.assertNotIn("Presbyterian", shares)
        self.assertEqual(shares["Orthodox"], 95.17)
        # And the rows with a 2024 figure and no 2004 one are kept, which a
        # width check would have thrown away with the others.
        self.assertEqual(shares["Jehovah's Witnesses"], 0.37)
        self.assertEqual(shares["Islam"], 0.06)
        self.assertEqual(got["year"], 2024)
        self.assertIn("3 row(s) of the table print nothing in the column read",
                      got["remark"])

    def test_a_column_empty_in_every_row_says_that(self):
        got, why = m.read_field(BRICENI_RELIGION, m.MD_RELIGION, MDA,
                                "Briceni District", "en")
        self.assertIsNone(got)
        self.assertIn("empty in all 3 of them", why)


class AFootnoteIsNotPartOfTheLabel(unittest.TestCase):
    """Taraclia's ethnic table hangs an {{efn}} off the word "Moldovans".

    Collapsed the way every other template is -- to whatever follows its last
    pipe -- that left the row labelled "Moldovansongoing controversy]]
    regarding the ethnic identification of Moldovans", which is no label this
    reader has an entry for, and the whole table was refused for it.
    """

    def test_the_row_is_the_people_and_not_the_footnote(self):
        got, why = m.read_field(TARACLIA_ETHNIC, m.MD_ETHNICITY, MDA,
                                "Taraclia District", "en")
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got["rows"]}
        self.assertEqual(shares["Moldovan"], 14.8)
        self.assertEqual(shares["Bulgarian"], 64.2)
        self.assertEqual(got["year"], 2024)


class TwoShapesOfTheSameQuestion(unittest.TestCase):
    """Moldova asks about language twice and publishes it two ways."""

    def test_the_capital_s_table_is_read_by_the_first_spec(self):
        got, why = m.read_field(CHISINAU_LANGUAGE, m.MD_LANGUAGE_FIRST, MDA,
                                "Chișinău", "en")
        self.assertEqual(why, "")
        self.assertEqual({r["group"]: r["pct"] for r in got["rows"]},
                         {"Romanian": 47.65, "Moldovan": 28.69,
                          "Russian": 19.70, "Other": 3.97})
        self.assertEqual(got["year"], 2024)

    def test_the_first_spec_does_not_read_the_other_table(self):
        got, why = m.read_field(GAGAUZIA_LANGUAGE, m.MD_LANGUAGE_FIRST, MDA,
                                "Gagauzia", "en")
        self.assertIsNone(got)
        self.assertIn("header this reader does not know", why)

    def test_the_mother_tongue_column_is_named_not_counted_from_the_end(self):
        # The last column of Gagauzia's table is the language spoken at home,
        # which is a different question: Gagauz is 77.2% of mother tongues
        # and 48.8% of homes.
        got, why = m.read_field(GAGAUZIA_LANGUAGE, m.MD_LANGUAGE_MOTHER, MDA,
                                "Gagauzia", "en")
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got["rows"]}
        self.assertEqual(shares["Gagauz"], 77.2)
        self.assertEqual(shares["Moldovan (Romanian)"], 4.7)
        self.assertNotIn(48.8, shares.values())
        self.assertEqual(got["year"], 2024)


class AUnitThatIsNotInTheCategory(unittest.TestCase):
    """Five of Moldova's thirty-seven units are not districts.

    The reader builds its candidates from "Category:Districts of Moldova", so
    the capital, the second city, Gagauzia, Bender and Transnistria were
    never candidates and every one of them said the same thing: "is none of
    the names on the country's own list of units". Three of them have an
    article with a composition in it, and naming it is all it takes; the
    other two are refused in writing, because what their articles publish is
    Transnistria's own counting and not the census this reader names.
    """

    def setUp(self):
        self.members = m.category_members
        m.category_members = lambda category, lang: ["Taraclia District",
                                                     "Briceni District"]

    def tearDown(self):
        m.category_members = self.members

    def titles(self):
        return m.article_titles(
            MDA, MDA.levels[0],
            ["Taraclia", "Briceni", "Chisinau", "Balti", "Gagauzia",
             "Bender", "Transnistria"])

    def test_the_capital_is_reached_by_name(self):
        titles, _ = self.titles()
        self.assertEqual(titles["Chisinau"], "Chișinău")
        self.assertEqual(titles["Gagauzia"], "Gagauzia")
        self.assertEqual(titles["Balti"], "Bălți")

    def test_the_districts_still_come_from_the_category(self):
        titles, _ = self.titles()
        self.assertEqual(titles["Taraclia"], "Taraclia District")
        self.assertEqual(titles["Briceni"], "Briceni District")

    def test_what_is_refused_says_whose_census_it_would_have_been(self):
        titles, refused = self.titles()
        self.assertNotIn("Bender", titles)
        self.assertNotIn("Transnistria", titles)
        for name in ("Bender", "Transnistria"):
            self.assertIn("2024 Moldovan census did not count it",
                          refused[name])
        self.assertIn("2015", refused["Transnistria"])
        self.assertIn("0-5", refused["Bender"])


class ATableOfSharesIsNeverAPopulation(unittest.TestCase):
    """Briceni's ethnic table adds to 101.31% as printed.

    Above 101 the population guard took it for a table of counts and weighed
    nine percentages against a district of 46,894 people, which is 0.2% of
    it, so the district was refused at admin1 -- and read at admin2, where
    this map carries no population to weigh it against. The bound is now the
    one that decides what a composition is at all.
    """

    def test_a_hundred_and_one_point_three_is_still_shares(self):
        self.assertTrue(m.fits_population(
            {"counts": {"Moldovan": 72.6, "Ukrainian": 22.5, "Russian": 2.3,
                        "Romanian": 2.0, "Not declared": 1.21, "Other": 0.3,
                        "Romani": 0.2, "Bulgarian": 0.1, "Gagauz": 0.1}},
            {"population": {"value": 46894}}, "Briceni", m.MD_ETHNICITY))

    def test_a_table_of_counts_is_still_weighed(self):
        self.assertFalse(m.fits_population(
            {"counts": {"a": 9000.0, "b": 500.0}},
            {"population": {"value": 101100}}, "T", m.MD_ETHNICITY))


BASARABEASCA_RELIGION = """== Religion ==
""" + MD_CITE + """{| class="wikitable"
! Religion !! Number !! %
|-
| Christians || 14,717 || 98.7
|-
| Orthodox Christians || 14,200 || 95.2
|-
| Baptists || 230 || 1.5
|-
| Adventists || 152 || 1.0
|-
| Pentecostals || 66 || 0.4
|-
| Evangelicals || 30 || 0.2
|-
| Jehovah's Witnesses || 27 || 0.2
|-
| Catholics || 11 || 0.1
|-
| Old Believers || 1 || 0.0
|-
| Muslims || 7 || 0.0
|-
| Free thinkers || 2 || 0.0
|-
| Agnostics || 5 || 0.0
|-
| Atheists || 31 || 0.2
|-
| Irreligious || 90 || 0.6
|-
| Other || 6 || 0.0
|-
| Undeclared || 56 || 0.4
|-
! Total || 14,914 || 100
|}
"""


class AParentWithNoDashToMarkItsChildren(unittest.TestCase):
    """Basarabeasca is the third spelling of the same hazard, and the one
    with nothing in the markup to give it away: "Christians" 98.7 sits above
    eight rows that add to 98.6, and not one of them is marked as a child.

    It is also the district that made this reader's own labels visible. The
    run refused the table on seven words -- Baptists, Adventists,
    Pentecostals, Evangelicals, Old Believers, Free thinkers, Irreligious --
    which are the same faiths Chisinau and Taraclia name in the singular.
    """

    def test_the_parent_is_skipped_and_the_plurals_are_read(self):
        got, why = m.read_field(BASARABEASCA_RELIGION, m.MD_RELIGION, MDA,
                                "Basarabeasca District", "en")
        self.assertEqual(why, "")
        self.assertAlmostEqual(sum(got["counts"].values()), 99.8, places=2)
        shares = {r["group"]: r["pct"] for r in got["rows"]}
        self.assertEqual(shares["Orthodox"], 95.2)
        self.assertEqual(shares["Adventist"], 1.0)
        self.assertEqual(shares["Old Believer"], 0.0)
        self.assertNotIn(98.7, shares.values())

    def test_the_census_s_own_four_kinds_of_unbelief_stay_apart(self):
        # Atheists, agnostics, free thinkers and the irreligious are four
        # rows of one table, so the census means four different answers.
        # None of them is folded into another here.
        got, _ = m.read_field(BASARABEASCA_RELIGION, m.MD_RELIGION, MDA,
                              "Basarabeasca District", "en")
        shares = {r["group"]: r["pct"] for r in got["rows"]}
        self.assertEqual(shares["Atheism"], 0.2)
        self.assertEqual(shares["Agnosticism"], 0.0)
        self.assertEqual(shares["Freethinker"], 0.0)
        self.assertEqual(shares["Irreligious"], 0.6)

    def test_chisinau_s_two_irreligious_rows_are_not_one_inside_the_other(self):
        # "Agnostic / atheist" is the two leaves welded into one figure, so it
        # stays at the level that holds both; the row beneath it, written "No
        # religion" in English, is the census's fourth answer and not that
        # level. Written as the same canonical name, the pair stopped a build
        # that had already produced every site file.
        labels = m.MD_RELIGION_LABELS
        self.assertEqual(labels["no religion"], "Irreligious")
        self.assertEqual(labels["agnostic / atheist"], "Agnostic or atheist")
        rows = [{"group": labels["agnostic / atheist"], "pct": 3.6},
                {"group": labels["no religion"], "pct": 1.0}]
        self.assertEqual(canonical_groups.check_no_double_counting(rows, "religion"), [])

    def test_a_balkan_table_keeps_the_plain_category(self):
        # The override is Moldova's. Serbia and Bulgaria read a table with no
        # atheist row beside it, where "no religion" is the whole answer.
        self.assertEqual(m.BALKAN_RELIGION["no religion"], "No religion")

    def test_none_of_the_four_is_the_category_the_others_sit_in(self):
        # The fourth used to be written "No religion", which is the canonical
        # parent of the first two. A record naming a parent and its children
        # is counted once for itself and again for each child, so the build
        # stops on it -- as it did, after every site file had been written.
        got, _ = m.read_field(BASARABEASCA_RELIGION, m.MD_RELIGION, MDA,
                              "Basarabeasca District", "en")
        named = {r["group"] for r in got["rows"]}
        parents = {p for g in named
                   for p in canonical_groups.ancestry("religion", g)[1:]}
        self.assertEqual(named & parents, set())


# Anenii Noi District's Religion section as the runner fetched it from the
# English Wikipedia on 23 September 2026, and the infobox reference it cites
# by name. Muslims are indented under Christians in the article; that is how
# it is written, and the test keeps it.
ANENII_NOI = """{{Infobox settlement
| population_as_of = [[2024 Moldovan Census|2024]]
| population_footnotes = <ref name=":0">{{Cite web |date=2026-02-27 |title=Rezultatele finale ale Recensământului Populației și Locuințelor 2024 |url=https://statistica.gov.md/ro/x}}</ref>
| population_total = 57,687
}}
=== Ethnic groups ===
text
=== Religion ===
[[File:MD.AN.AN - St Demetrius church (rear) - nov 2012.JPG|thumb|Church of St. Dumitru, [[Anenii Noi|city of Anenii Noi]]]]
Source:<ref name=":0" />
*Christians – 96.7%
**[[Orthodoxy#Christianity|Orthodox Christians]] – 96.1%
**[[Protestant]] – 1.7%
**[[Catholics]] – 0.1%
**[[Muslims|Muslim]] - 0.2%
*Other – 0.1%
*No Religion – 0.8%
*Not declared - 0.9%
== Economy ==
There are 12,555 businesses registered in the district.
"""


class AListIsReadWhereThereIsNoTable(unittest.TestCase):
    """Moldova's districts publish their 2024 religion as bullets, not a table."""

    def test_the_lines_with_nothing_under_them_are_read(self):
        got, why = m.read_field(ANENII_NOI, m.MD_RELIGION, MDA,
                                "Anenii Noi District", "en")
        self.assertEqual(why, "")
        shares = {r["group"]: r["pct"] for r in got["rows"]}
        self.assertEqual(shares["Orthodox"], 96.1)
        self.assertEqual(shares["Protestant"], 1.7)
        self.assertEqual(shares["Islam"], 0.2)
        self.assertEqual(shares["Not declared"], 0.9)

    def test_the_subtotal_is_not_read_beside_its_parts(self):
        got, _ = m.read_field(ANENII_NOI, m.MD_RELIGION, MDA,
                              "Anenii Noi District", "en")
        self.assertNotIn("Christian", {r["group"] for r in got["rows"]})
        self.assertAlmostEqual(sum(r["pct"] for r in got["rows"]), 100.0, delta=0.6)

    def test_a_subtotal_that_is_not_its_parts_is_said_to_be(self):
        # 96.1 + 1.7 + 0.1 + 0.2 is 98.1, not the 96.7 the line above says.
        got, _ = m.read_field(ANENII_NOI, m.MD_RELIGION, MDA,
                              "Anenii Noi District", "en")
        self.assertIn('"Christians" gives 96.7%', got["remark"])
        self.assertIn("98.1%", got["remark"])
        self.assertIn("bulleted list", got["remark"])

    def test_it_is_dated_by_the_census_its_citation_names(self):
        # The reference is used by name in the section and defined in the
        # infobox; the title's 2024 dates it, not the 2026 publication date.
        got, _ = m.read_field(ANENII_NOI, m.MD_RELIGION, MDA,
                              "Anenii Noi District", "en")
        self.assertEqual(got["year"], 2024)
        self.assertIn("Recensământului", got["cited"])
        self.assertEqual(got["kind"], "census")

    def test_a_table_is_still_preferred_where_there_is_one(self):
        got, _ = m.read_field(BASARABEASCA_RELIGION, m.MD_RELIGION, MDA,
                              "Basarabeasca District", "en")
        self.assertNotIn("bulleted list", got["remark"])

    def test_without_the_opt_in_a_list_is_not_read(self):
        import dataclasses
        spec = dataclasses.replace(m.MD_RELIGION, bullets=False)
        got, why = m.read_field(ANENII_NOI, spec, MDA, "Anenii Noi District", "en")
        self.assertIsNone(got)
        self.assertIn("no table", why)

    def test_a_hyphen_inside_a_label_is_not_the_dash(self):
        rows, _, _ = m.find_list(
            "== Religion ==\n* Seventh-day Adventists – 0.3%\n"
            "* Orthodox Christians – 99.0%\n* Other – 0.7%\n", m.MD_RELIGION)
        self.assertIn(["Seventh-day Adventists", "0.3"], rows)

    def test_two_lines_are_not_a_composition(self):
        rows, _, _ = m.find_list(
            "== Religion ==\n* Orthodox – 99%\n* Other – 1%\n", m.MD_RELIGION)
        self.assertEqual(rows, [])
