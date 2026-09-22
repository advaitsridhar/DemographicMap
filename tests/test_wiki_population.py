"""The first-level population read from a Wikipedia infobox.

Every wikitext string below is the real one, copied out of the probe that
settled the question on 22 September 2026 -- the run recorded in commit
f9f374b, which opened the five articles behind the five emptiest countries
and printed their infobox parameters. They are here because the five differ
in every way that matters: 2252483 and 253,462 and 12998 are the same kind of
number written three ways, and "2022", "2019 census" and "July 2024" are the
same kind of year written three ways.

The refusals are the other half. A figure this module cannot read is left
unread and said aloud, because a population nobody wrote is worse than a
population missing.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_census import wiki_population as wp  # noqa: E402


def infobox(**params):
    """An article that is nothing but an infobox with these parameters."""
    lines = "\n".join(f"| {k.replace('__', ' ')} = {v}" for k, v in params.items())
    return "{{Infobox settlement\n" + lines + "\n}}\n\nSome prose.\n"


# The five, verbatim.
ZAMBIA = infobox(official_name="Central",
                 settlement_type="[[Provinces of Zambia|Province]]",
                 population_as_of="2022",
                 population_footnotes='<ref name=":02" />',
                 population_note="",
                 population_total="2252483",
                 population_density_km2="auto")
JAMAICA = infobox(
    official_name="Clarendon",
    population_total="253,462",
    population_footnotes=('<ref name="CFCJ_1">{{cite web| title=Clarendon, Jamaica| '
                          'url=https://www.city-facts.com/clarendon/population| '
                          'website=city-facts| date=2024| access-date=14 December 2024}}</ref>'),
    population_as_of="2015",
    population_demonym="Clarendonies")
BURKINA = infobox(population_as_of="2019 census",
                  population_footnotes=("<ref>[https://www.citypopulation.de/en/burkinafaso/cities/ "
                                        "Citypopulation.de] Population of regions in Burkina Faso</ref>"),
                  population_note="",
                  population_total="1898133",
                  population_urban="183236")
MALTA = infobox(population_total="12998",
                population_as_of="July 2024",
                population_footnotes=('<ref name="nso_2012-2024">{{cite web '
                                      '|title=Mid-year population estimates by locality }}</ref>'),
                population_density_km2="1724")
HAITI = infobox(population_rank="[[Departments of Haiti|2nd]]",
                population_as_of="2015",
                population_density_km2="auto",
                population_total="1727524",
                population_urban="739787",
                population_rural="987737")


class ReadsTheFive(unittest.TestCase):
    def test_all_five_give_a_population_and_a_year(self):
        self.assertEqual(wp.read(ZAMBIA)[:2], (2252483, 2022))
        self.assertEqual(wp.read(JAMAICA)[:2], (253462, 2015))
        self.assertEqual(wp.read(BURKINA)[:2], (1898133, 2019))
        self.assertEqual(wp.read(MALTA)[:2], (12998, 2024))
        self.assertEqual(wp.read(HAITI)[:2], (1727524, 2015))

    def test_the_urban_and_rural_parts_are_not_mistaken_for_the_whole(self):
        # Haiti's infobox prints three populations. The total is the one the
        # article settled on, and the only one that describes the department.
        self.assertEqual(wp.read(HAITI)[0], 1727524)
        self.assertEqual(wp.read(BURKINA)[0], 1898133)

    def test_a_rank_is_not_a_population(self):
        # "population_rank = 2nd" sits above population_total in Haiti's
        # infobox and must never be read as two people.
        self.assertNotEqual(wp.read(HAITI)[0], 2)


class Numbers(unittest.TestCase):
    def test_grouping(self):
        for text, want in (("2252483", 2252483), ("253,462", 253462),
                           ("12998", 12998), ("1 727 524", 1727524),
                           ("1 727 524", 1727524),
                           ("{{formatnum:1898133}}", 1898133),
                           ("{{nowrap|45,000}}", 45000)):
            self.assertEqual(wp.number(text)[0], want, text)

    def test_what_it_refuses(self):
        # A dot is a thousands separator in half of Europe and a decimal point
        # in the other half, so a number carrying one is not read at all.
        for text in ("1.727.524", "12.5", "c. 40,000", "40,000-45,000",
                     "unknown", "", "approx 900", "1.2 million"):
            value, why = wp.number(text)
            self.assertIsNone(value, text)
            self.assertTrue(why, text)

    def test_a_figure_with_its_year_in_brackets(self):
        value, tail = wp.number("12,998 (2024)")
        self.assertEqual(value, 12998)
        self.assertEqual(wp.year_of(tail)[0], 2024)

    def test_a_reference_beside_the_figure_is_not_part_of_it(self):
        self.assertEqual(wp.number('253,462<ref name="x">{{cite web|y=1}}</ref>')[0],
                         253462)


class Years(unittest.TestCase):
    def test_the_three_shapes_the_probe_found(self):
        self.assertEqual(wp.year_of("2022")[0], 2022)
        self.assertEqual(wp.year_of("2019 census")[0], 2019)
        self.assertEqual(wp.year_of("July 2024")[0], 2024)
        self.assertEqual(wp.year_of("1 January 2011")[0], 2011)

    def test_two_years_in_one_value_date_nothing(self):
        year, why = wp.year_of("2011 census (2019 estimate)")
        self.assertIsNone(year)
        self.assertIn("several", why)

    def test_a_figure_with_no_year_is_still_a_figure(self):
        value, year, why = wp.read(infobox(population_total="12998"))
        self.assertEqual(value, 12998)
        self.assertIsNone(year)
        self.assertTrue(why)


class Refusals(unittest.TestCase):
    def test_an_article_with_no_infobox(self):
        self.assertEqual(wp.read("Just prose about a place.\n")[0], None)

    def test_an_infobox_with_no_population(self):
        value, _, why = wp.read(infobox(official_name="Nowhere", area_km2="12"))
        self.assertIsNone(value)
        self.assertIn("no population", why)

    def test_a_population_it_cannot_parse_is_not_skipped_over(self):
        # The refusal names the parameter, so the next run can be taught the
        # shape rather than quietly falling through to a worse figure.
        value, _, why = wp.read(infobox(population_total="1.727.524",
                                        population_estimate="1727524"))
        self.assertIsNone(value)
        self.assertIn("population_total", why)


class Names(unittest.TestCase):
    def test_the_boundary_file_and_the_encyclopaedia_agree(self):
        same = [("Central", "Central Province"),
                ("Clarendon", "Clarendon Parish"),
                ("Artibonite Department", "Artibonite"),
                ("Grand'Anse Mahé", "Grand Anse Mahe"),
                ("Saint Andrew", "Saint Andrew Parish"),
                ("Boucle du Mouhoun", "Boucle du Mouhoun Region")]
        for a, b in same:
            self.assertEqual(wp.fold(a), wp.fold(b), (a, b))

    def test_different_places_do_not_fold_together(self):
        for a, b in (("Centre-Est", "Centre-Nord"), ("North Abaco", "South Abaco"),
                     ("Saint Ann", "Saint Andrew"), ("Nord-Est", "Nord-Ouest")):
            self.assertNotEqual(wp.fold(a), wp.fold(b), (a, b))

    def test_a_disambiguating_tail_is_not_part_of_the_name(self):
        self.assertEqual(wp.disambiguated("Artibonite (department)"), "Artibonite")
        self.assertEqual(wp.disambiguated("Central Province, Zambia"), "Central Province")
        self.assertEqual(wp.disambiguated("Attard"), "Attard")


def pool(*pairs):
    return {f"Q{i}": {"names": [name], "title": title}
            for i, (name, title) in enumerate(pairs, start=1)}


def units(*names):
    return [{"id": f"u{i}", "name": n} for i, n in enumerate(names, start=1)]


class Resolving(unittest.TestCase):
    def test_an_exact_name_wins(self):
        got = wp.resolve(units("Central"),
                         pool(("Central Province", "Central Province, Zambia"),
                              ("Kabwe", "Kabwe")))
        self.assertEqual(got["u1"], ("Q1", "Central Province, Zambia", "name"))

    def test_a_truncated_boundary_name_is_reached_by_its_prefix(self):
        # Seychelles' boundary file cuts every name to ten characters.
        got = wp.resolve(units("Anse Etoil"),
                         pool(("Anse Etoile", "Anse Etoile"), ("Cascade", "Cascade")))
        self.assertEqual(got["u1"][:2], ("Q1", "Anse Etoile"))
        self.assertEqual(got["u1"][2], "prefix")

    def test_a_respelling_is_reached_by_the_near_pass(self):
        got = wp.resolve(units("Valle Du Bandama"),
                         pool(("Vallée du Bandama", "Vallée du Bandama"),
                              ("Woroba", "Woroba")))
        self.assertEqual(got["u1"][:2], ("Q1", "Vallée du Bandama"))
        self.assertEqual(got["u1"][2], "near")

    def test_two_candidates_settle_nothing(self):
        # "North" starts both, so neither is evidence.
        got = wp.resolve(units("Northern"),
                         pool(("Northern Province", "Northern Province, X"),
                              ("Northern Region", "Northern Region, X")))
        self.assertEqual(got, {})

    def test_one_article_is_never_given_to_two_units(self):
        got = wp.resolve(units("Saint Andrew", "Saint Andrew"),
                         pool(("Saint Andrew Parish", "Saint Andrew Parish, Jamaica")))
        self.assertEqual(len(got), 1)

    def test_an_item_with_no_english_article_is_not_a_candidate(self):
        got = wp.resolve(units("Ngatpang"), pool(("Ngatpang", None)))
        self.assertEqual(got, {})

    def test_a_prefix_that_adds_a_whole_word_is_a_different_place(self):
        # All three are from the first run of this reader, which published
        # none of them only because none of the three articles carried a
        # population. Clarendon Park is a town inside Clarendon parish, the
        # Valletta-Mdina railway is not Valletta, and a pottery phase named
        # after Tarxien is not Tarxien.
        for name, label, title in (
                ("Clarendon", "Clarendon Park", "Clarendon Park, Jamaica"),
                ("Valletta", "Valletta\u2013Mdina railway", "Malta Railway"),
                ("Tarxien", "Tarxien Cemetery phase", "Tarxien Cemetery phase")):
            self.assertEqual(wp.resolve(units(name), pool((label, title))), {}, name)

    def test_a_name_cut_to_the_boundary_file_s_width_may_lose_a_whole_word(self):
        # "Baie Saint" is ten characters because the boundary file stops
        # there, and the district is Baie Sainte Anne.
        got = wp.resolve(units("Baie Saint"),
                         pool(("Baie Sainte Anne", "Baie Sainte Anne")))
        self.assertEqual(got["u1"][:2], ("Q1", "Baie Sainte Anne"))

    def test_a_shorter_name_may_still_gain_an_ending(self):
        got = wp.resolve(units("Cascade"), pool(("Cascades", "Cascades")))
        self.assertEqual(got["u1"][:2], ("Q1", "Cascades"))

    def test_the_item_the_build_already_joined_wins(self):
        # A wider pool is consulted only for what the first pass left short,
        # so a match already made can never be taken away by one.
        preset = {"u1": ("Q9", "Attard", "wikidata")}
        got = wp.resolve(units("Attard", "Balzan"),
                         pool(("Attard", "Attard, Malta"), ("Balzan", "Balzan")),
                         preset)
        self.assertEqual(got["u1"], ("Q9", "Attard", "wikidata"))
        self.assertEqual(got["u2"][:2], ("Q2", "Balzan"))

    def test_a_short_name_is_not_prefix_matched(self):
        # "Bay" would start Bayamo, Bayan Olgii and a hundred other places.
        got = wp.resolve(units("Bay"), pool(("Bayamo", "Bayamo")))
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main()
