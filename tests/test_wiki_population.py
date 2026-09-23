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
        # A figure in whole millions is a guess more than a count.
        for text in ("1.727.524", "12.5", "40,000-45,000", "50–100",
                     "unknown", "", "2 million", "1,15,6400"):
            value, why = wp.number(text)
            self.assertIsNone(value, text)
            self.assertTrue(why, text)

    def test_a_figure_with_its_year_in_brackets(self):
        value, tail = wp.number("12,998 (2024)")
        self.assertEqual(value, 12998)
        self.assertEqual(wp.year_of(tail)[0], 2024)

    def test_a_maintenance_tag_beside_the_figure_is_not_part_of_it(self):
        # All five of Eritrea's regions print the 2005 estimate this way, and
        # all five were refused as "not a whole number" for the tag.
        self.assertEqual(wp.number("893,587{{citation needed|date=November 2023}}")[0],
                         893587)
        self.assertEqual(wp.number("1,103,742 {{citation needed|date=November 2023}}")[0],
                         1103742)

    def test_an_arrow_beside_the_figure_is_not_part_of_it(self):
        # All three of Cambodia's unread provinces print the figure with an
        # arrow saying which way it moved, which is about the series.
        self.assertEqual(wp.number("{{decrease}} 898,484")[0], 898484)
        self.assertEqual(wp.number("{{increase}} 889,970")[0], 889970)

    def test_a_parameter_that_ran_on_into_the_next_one(self):
        # Maldives' Shaviyani Atoll writes two parameters on one line.
        self.assertEqual(wp.number("12,091 noofislands=51")[0], 12091)

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


class WhatTheArticleIsAbout(unittest.TestCase):
    def test_the_infobox_says_what_the_place_is(self):
        self.assertEqual(wp.kind(ZAMBIA), "province")
        self.assertEqual(wp.kind(infobox(settlement_type="City")), "city")
        self.assertEqual(wp.kind(infobox(settlement_type="[[Districts of Libya|District]]")),
                         "district")
        self.assertEqual(wp.kind(infobox(official_name="X")), "")

    def test_a_country_that_agrees_on_one_kind(self):
        # Libya: eleven districts and the city of Zawiya, which is inside one
        # of them and whose 200,000 people are not a district's.
        self.assertEqual(wp.odd_one_out(["district"] * 11 + ["city"]), "district")

    def test_a_country_that_agrees_on_nothing_accuses_no_one(self):
        self.assertIsNone(wp.odd_one_out(["city", "town", "district"]))
        self.assertIsNone(wp.odd_one_out(["", "", ""]))
        self.assertIsNone(wp.odd_one_out([]))

    def test_a_country_whose_units_are_themselves_settlements(self):
        # Malta's 68 localities. Nothing here stands against anything.
        self.assertIsNone(wp.odd_one_out(["town"] * 40 + ["city"] * 28))


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

    def test_a_country_whose_names_are_cut_may_lose_a_whole_word(self):
        # Seychelles' boundary file stops at ten characters, and does it to
        # twelve of the twenty-four, which is the evidence that it is cutting.
        # "Baie Saint" is Baie Sainte Anne.
        seychelles = units("Baie Saint", "Anse Etoil", "Mont Buxto", "Cascade")
        self.assertTrue(wp.truncates(seychelles))
        got = wp.resolve(seychelles,
                         pool(("Baie Sainte Anne", "Baie Sainte Anne"),
                              ("Anse Etoile", "Anse Etoile"),
                              ("Mont Buxton", "Mont Buxton"),
                              ("Cascade", "Cascade")))
        self.assertEqual(got["u1"][:2], ("Q1", "Baie Sainte Anne"))

    def test_a_country_whose_names_are_not_cut_may_not(self):
        # Jamaica has two names of ten characters out of fourteen, which is
        # coincidence, not a cut. Saint Thomas in the Vale is a different
        # parish from Saint Thomas, and the second run matched them.
        jamaica = units("Saint Thomas", "Clarendon", "Manchester", "Saint Mary")
        self.assertFalse(wp.truncates(jamaica))
        got = wp.resolve(jamaica, pool(
            ("Saint Thomas in the Vale Parish", "Saint Thomas in the Vale Parish, Jamaica"),
            ("Clarendon Parish", "Clarendon Parish, Jamaica"),
            ("Manchester Parish", "Manchester Parish"),
            ("Saint Mary Parish", "Saint Mary Parish, Jamaica")))
        self.assertNotIn("u1", got)
        self.assertEqual(got["u2"][:2], ("Q2", "Clarendon Parish, Jamaica"))

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


class Europe(unittest.TestCase):
    """Every European gap in the first sweep failed at finding the article.

    Belgium, France, Italy and Portugal because their shapes carry names in
    their own languages and the reader asked Wikidata for English labels
    only; Lithuania, Italy and Ukraine because the P131 search stopped at four
    thousand items before reaching them; Bulgaria and Belarus because a city
    and the unit around it fold to one name.
    """

    def test_a_name_that_is_all_generic_words_is_kept_whole(self):
        self.assertEqual(wp.fold("Capital Region"), "capitalregion")
        self.assertEqual(wp.fold("Capital Region"),
                         wp.fold(wp.disambiguated("Capital Region (Iceland)")))

    def test_the_generic_words_of_the_map_s_own_languages(self):
        self.assertEqual(wp.fold("Vlaams Gewest"), wp.fold("Vlaams Gewest (region)"))
        self.assertEqual(wp.fold("Wallonne Gewest"), wp.fold("Région wallonne"))
        self.assertEqual(wp.fold("LISBOA"), wp.fold("Distrito de Lisboa"))
        self.assertEqual(wp.fold("Epirus-Western Macedonia"),
                         wp.fold("Decentralized Administration of Epirus and Western Macedonia"))

    def test_the_item_another_shape_holds_is_not_this_shape_s(self):
        # Belarus draws Minsk Region and Minsk the city as two shapes.
        got = wp.resolve(units("Minsk City"),
                         pool(("Minsk Region", "Minsk Region"), ("Minsk", "Minsk")),
                         exclude={"Q1"})
        self.assertEqual(got["u1"][:2], ("Q2", "Minsk"))

    def test_the_name_written_exactly_as_the_map_writes_it_settles_a_tie(self):
        # The town, the district municipality and the county all fold to
        # "alytus"; only one of them is called "Alytus County".
        got = wp.resolve(units("Alytus County"),
                         pool(("Alytus", "Alytus"),
                              ("Alytus District Municipality", "Alytus District Municipality"),
                              ("Alytus County", "Alytus County")))
        self.assertEqual(got["u1"][:2], ("Q3", "Alytus County"))

    def test_a_tie_nothing_written_settles_is_still_refused(self):
        got = wp.resolve(units("Sofia"),
                         pool(("Sofia", "Sofia"), ("Sofia Province", "Sofia Province")))
        self.assertEqual(got, {})

    def test_a_census_year_in_the_parameter_s_name(self):
        # Infobox Russian federal subject, as the Sakha Republic uses it.
        text = ("{{Infobox Russian federal subject\n| name = Sakha\n"
                "| pop_2021census = 995,686\n| pop_2021census_rank = 55th\n"
                "| pop_2010census = 958,528\n| pop_density = 0.3\n}}")
        self.assertEqual(wp.read(text)[:2], (995686, 2021))

    def test_an_empty_newer_census_falls_back_to_the_older_one(self):
        text = "{{Infobox X\n| pop_2021census = \n| pop_2010census = 958,528\n}}"
        self.assertEqual(wp.read(text)[:2], (958528, 2010))


class TheCountryItsOwnDivisionsFirst(unittest.TestCase):
    """Sofia, end to end, with the network replaced by what Wikidata says."""

    def setUp(self):
        self.saved = {name: getattr(wp, name) for name in (
            "country_item", "claims_of", "entities", "children", "contains",
            "search", "by_title", "languages")}
        items = {
            "Q472": {"names": ["Sofia"], "title": "Sofia"},
            "Q1": {"names": ["Sofia Province"], "title": "Sofia Province"},
            "Q2": {"names": ["Sofia City Province"], "title": "Sofia City Province"},
        }
        wp.country_item = lambda iso3: "Q219"
        wp.claims_of = lambda qid: {}
        wp.languages = lambda claims: ["en"]
        wp.statements = self.saved.get("statements", wp.statements)
        wp.entities = lambda qids, langs=("en",): {q: items[q] for q in qids if q in items}
        wp.children = lambda qid: ["Q472"]
        wp.contains = lambda qid: []
        wp.search = lambda *a, **k: {}
        wp.by_title = lambda *a, **k: None
        self.divisions = ["Q1", "Q2"]
        original = wp.statements
        wp.statements = lambda claims, prop: self.divisions if prop == "P150" else []
        self.saved["statements"] = original

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(wp, name, value)

    def test_the_province_is_found_before_the_city_is_ever_offered(self):
        shapes = [{"id": "a", "name": "Sofia"},
                  {"id": "b", "name": "Sofia City", "wikidata": "Q2"}]
        got = wp.article_for("BGR", shapes[:1], shapes, "Bulgaria")
        self.assertEqual(got["a"][:2], ("Q1", "Sofia Province"))


class WhatThisReaderAnswersFor(unittest.TestCase):
    def test_its_own_earlier_answers_and_every_gap_and_nothing_else(self):
        shapes = [
            {"id": "gap", "population": {"status": "not_available"}},
            {"id": "mine", "population": {"value": 12998, "year": 2024,
                                          "source": "English Wikipedia, Attard (infobox)"}},
            {"id": "census", "population": {"value": 5, "year": 2021,
                                            "source": "National Statistics Office"}},
            {"id": "wikidata", "population": {"value": 7, "source": "Wikidata (CC0)"}},
        ]
        self.assertEqual([u["id"] for u in wp.to_read(shapes)], ["gap", "mine"])


class FollowingARedirect(unittest.TestCase):
    """Burkina Faso's old region names survive only as Wikipedia redirects."""

    def setUp(self):
        self.saved = (wp.api, wp.in_country)

        def api(endpoint, **params):
            titles = params["titles"].split("|")
            return {"query": {
                "redirects": [{"from": "Boucle du Mouhoun Region", "to": "Bankui Region"}],
                "pages": [
                    {"title": "Bankui Region", "pageprops": {"wikibase_item": "Q850000"}},
                    {"title": "Boucle du Mouhoun", "pageprops": {"disambiguation": ""}},
                ] + [{"title": t, "missing": True} for t in titles
                     if t not in ("Boucle du Mouhoun Region", "Boucle du Mouhoun")]}}
        wp.api = api
        wp.in_country = lambda item, country: item == "Q850000"

    def tearDown(self):
        wp.api, wp.in_country = self.saved

    def test_the_old_name_reaches_the_renamed_region(self):
        got = wp.by_title({"name": "Boucle du Mouhoun"}, "Burkina Faso", "Q965", set())
        self.assertEqual(got, ("Q850000", "Bankui Region"))

    def test_an_item_another_shape_holds_is_passed_over(self):
        got = wp.by_title({"name": "Boucle du Mouhoun"}, "Burkina Faso", "Q965",
                          {"Q850000"})
        self.assertIsNone(got)

    def test_an_item_outside_the_country_is_passed_over(self):
        wp.in_country = lambda item, country: False
        got = wp.by_title({"name": "Boucle du Mouhoun"}, "Burkina Faso", "Q965", set())
        self.assertIsNone(got)


class WhatThePageShowsAndWhereThePlaceIs(unittest.TestCase):
    def test_an_infobox_that_prints_wikidata_s_figure_is_recognised(self):
        # France's regions and Latvia's municipalities, verbatim.
        for value in ("{{France metadata Wikidata|population_total}}",
                      "{{wikidata|property|qualifier|best||P1082}}"):
            self.assertEqual(wp.read(infobox(population_total=value)),
                             (None, None, wp.FROM_WIKIDATA))

    def test_every_infobox_on_the_page_is_read_first_one_first(self):
        text = ("{{Infobox World Heritage Site\n| name = Mount Athos\n| year = 1988\n}}\n"
                "{{Infobox settlement\n| name = Athos\n| population_total = 1,746\n"
                "| population_as_of = 2021\n}}\n")
        self.assertEqual(wp.read(text)[:2], (1746, 2021))

    def test_a_figure_in_millions_is_read_as_approximate(self):
        # West Darfur's, from OCHA's state profile of 2023.
        self.assertEqual(wp.read(infobox(population_total="1.9 million<ref>OCHA</ref>",
                                         population_as_of="2023")),
                         (1900000, 2023, "approximate"))
        # One significant digit is not read, nor a malformed number.
        for value in ("2 million", "1,15,6400", "1.032"):
            self.assertIsNone(wp.number(value)[0], value)

    def test_a_parameter_run_on_after_a_comment_is_read(self):
        # Tanzania's Iringa Region, verbatim but for the dashes.
        text = ("{{Infobox settlement\n| name = Iringa Region\n"
                "| elevation_max_point = Luhombero <!-- Population ------>"
                "| population_total = 1,192,728\n| population_as_of = 2022\n"
                "| area_note = {{convert|1|km<!-- x -->|mi}}\n}}\n")
        self.assertEqual(wp.read(text), (1192728, 2022, ""))
        # A comment inside a template, before an unnamed argument, is not split.
        self.assertIn("|mi}}", wp.params(text)["area_note"])

    def test_a_split_never_reaches_across_to_a_later_comment(self):
        # Nakhchivan's: a comment with text after it, parameters, then a
        # comment that does run on. Only the second is split.
        text = ("{{Infobox settlement\n| name = N <!-- a --> text\n"
                "| population_census = 458,910\n| population_census_year = 2019\n"
                "| area_km2 = 5,502 <!-- b -->| demonym = x\n}}\n")
        self.assertEqual(wp.read(text), (458910, 2019, ""))
        self.assertEqual(wp.params(text)["demonym"].strip(), "x")

    def test_a_region_cannot_be_given_to_a_city_shape_it_could_not_fit_in(self):
        # Minsk Region, offered for the shape Belarus's boundary file draws
        # as "Minsk City": its coordinates are south of the city's box and
        # its area is 157 times the box's.
        saved = wp.claim_values
        claims = {
            "P625": [{"mainsnak": {"datavalue": {"value": {"latitude": 53.667, "longitude": 27.75}}}}],
            "P2046": [{"mainsnak": {"datavalue": {"value": {
                "amount": "+39854", "unit": "http://www.wikidata.org/entity/Q712226"}}}}],
        }
        wp.claim_values = lambda qid, prop: claims.get(prop, [])
        try:
            city_box = [27.4751, 53.8232, 27.733, 53.9583]
            self.assertIn("cannot fit", wp.refuted("Q192959", city_box))
            region_box = [26.0139, 52.3913, 29.4894, 55.009]
            claims["P625"] = [{"mainsnak": {"datavalue": {"value": {"latitude": 53.667, "longitude": 27.75}}}}]
            self.assertEqual(wp.refuted("Q192959", region_box), "")
        finally:
            wp.claim_values = saved

    def test_a_place_far_from_its_shape_is_somewhere_else(self):
        # Argentina's "La Roja" (La Rioja) offered Rojas Partido, in Buenos
        # Aires province.
        saved = wp.claim_values
        wp.claim_values = lambda qid, prop: [
            {"mainsnak": {"datavalue": {"value": {"latitude": -34.20, "longitude": -60.73}}}}
        ] if prop == "P625" else []
        try:
            la_rioja = [-69.6341, -31.9212, -65.3285, -27.7359]
            self.assertIn("outside the shape", wp.refuted("Q2621930", la_rioja))
        finally:
            wp.claim_values = saved

    def test_coordinates_a_little_off_do_not_refute_a_right_answer(self):
        # Both were refused by the first version of this check, and both
        # figures were right.
        saved = wp.claim_values
        try:
            for point, box in (((25.50, -76.63), [-76.811, 25.5375, -76.7438, 25.5512]),
                               ((14.38, -80.28), [-81.7356, 12.4831, -81.3496, 13.3859])):
                wp.claim_values = lambda qid, prop, pt=point: [
                    {"mainsnak": {"datavalue": {"value": {"latitude": pt[0], "longitude": pt[1]}}}}
                ] if prop == "P625" else []
                self.assertEqual(wp.refuted("Q1", box), "", point)
        finally:
            wp.claim_values = saved

    def test_the_figure_wikidata_ranks_best_and_dates_latest(self):
        saved = wp.claim_values

        def claim(amount, year, rank="normal"):
            return {"rank": rank,
                    "mainsnak": {"datavalue": {"value": {"amount": f"+{amount}"}}},
                    "qualifiers": {"P585": [{"datavalue": {"value": {
                        "time": f"+{year}-01-01T00:00:00Z"}}}]}}
        wp.claim_values = lambda qid, prop: [claim(3300000, 2019), claim(3325032, 2021),
                                             claim(1, 2023, "deprecated")]
        try:
            self.assertEqual(wp.wikidata_population("Q18677983"), (3325032, 2021))
        finally:
            wp.claim_values = saved

    def test_a_short_name_may_gain_an_ending(self):
        got = wp.resolve(units("East"),
                         pool(("Eastern Statistical Region", "Eastern Statistical Region")))
        self.assertEqual(got["u1"][:2], ("Q1", "Eastern Statistical Region"))


class Declarations(unittest.TestCase):
    def test_a_genitive_ending_is_the_same_name(self):
        self.assertTrue(wp.same_place_name("Rēzeknes", "Rēzekne"))
        self.assertTrue(wp.same_place_name("Valletta", "Valletta"))
        # The city of Zawiya is not Az Zawiyah district.
        self.assertFalse(wp.same_place_name("Az Zawiyah", "Zawiya"))
        self.assertFalse(wp.same_place_name("Saint Thomas", "Saint Thomas in the Vale"))

    def test_a_declared_article_is_still_proved(self):
        saved = (wp.api, wp.in_country)
        wp.api = lambda endpoint, **params: {"query": {"pages": [
            {"title": "Central Italy", "pageprops": {"wikibase_item": "Q1127320"}}]}}
        try:
            wp.in_country = lambda item, country: True
            self.assertEqual(wp.declared("ITA", {"name": "Centro"}, "Q38", set()),
                             ("Q1127320", "Central Italy"))
            # Held by another shape: refused.
            self.assertIsNone(wp.declared("ITA", {"name": "Centro"}, "Q38", {"Q1127320"}))
            # Wikidata's country statement is not asked: it refused
            # Somaliland's Togdheer. Geometry guards a declaration instead.
            wp.in_country = lambda item, country: False
            self.assertEqual(wp.declared("ITA", {"name": "Centro"}, "Q38", set()),
                             ("Q1127320", "Central Italy"))
            # The country itself only where the country is its one shape.
            self.assertIsNone(wp.declared("ITA", {"name": "Centro"}, "Q1127320", set()))
            self.assertEqual(wp.declared("ITA", {"name": "Centro"}, "Q1127320", set(),
                                         alone=True), ("Q1127320", "Central Italy"))
            # Nothing declared, nothing asked.
            self.assertIsNone(wp.declared("ITA", {"name": "Lazio"}, "Q38", set()))
        finally:
            wp.api, wp.in_country = saved

    def test_a_gross_area_mismatch_refutes_and_a_wrong_wikidata_area_does_not(self):
        saved = wp.claim_values

        def area(km2):
            return lambda qid, prop: [{"mainsnak": {"datavalue": {"value": {
                "amount": f"+{km2}", "unit": "http://www.wikidata.org/entity/Q712226"}}}}
            ] if prop == "P2046" else []
        try:
            wp.claim_values = area(161)   # Mgarr, as Wikidata has it
            self.assertEqual(wp.refuted("Q691220", [14.33, 35.90, 14.40, 35.93]), "")
            wp.claim_values = area(39854)  # Minsk Region
            self.assertIn("cannot fit", wp.refuted("Q192959", [27.4751, 53.8232, 27.733, 53.9583]))
        finally:
            wp.claim_values = saved


class CountedTwice(unittest.TestCase):
    def test_italy_s_five_as_first_read_are_reported(self):
        # "Southern Italy" is the Mezzogiorno with the islands, which Insular
        # Italy had already counted.
        values = {"Centro": 11699125, "Isole": 6329684, "Nord-Est": 11618783,
                  "Nord-Ovest": 15955242, "Sud": 19669678}
        shapes = [{"id": n, "population": {"status": "not_available"}} for n in values]
        read_out = [{"unit": {"id": n}, "value": v} for n, v in values.items()]
        self.assertGreater(wp.overcount("ITA", shapes, read_out, 58_934_177), wp.OVERCOUNT)

    def test_southern_italy_is_no_longer_declared_for_sud(self):
        self.assertNotIn(("ITA", "Sud"), wp.TITLES)

    def test_a_census_figure_already_on_the_map_is_counted_too(self):
        shapes = [{"id": "a", "population": {"value": 60, "source": "Census"}},
                  {"id": "b", "population": {"status": "not_available"}}]
        read_out = [{"unit": {"id": "b"}, "value": 40}]
        self.assertAlmostEqual(wp.overcount("X", shapes, read_out, 100), 1.0)


class APartIsNotTheWhole(unittest.TestCase):
    def test_a_governorate_split_off_a_region_is_not_the_region(self):
        self.assertTrue(wp.a_part_of("Al Batinah", "Al Batinah South Governorate"))
        self.assertTrue(wp.a_part_of("Ash Sharqiyah", "Ash Sharqiyah South Governorate"))

    def test_a_name_that_is_a_direction_in_another_language_is_not_refused(self):
        self.assertFalse(wp.a_part_of("Debub Region", "Southern region (Eritrea)"))
        self.assertFalse(wp.a_part_of("Département de l'Ouest", "Ouest (department)"))
        self.assertFalse(wp.a_part_of("Nord-Est", "Northeast Italy"))
        self.assertFalse(wp.a_part_of("North Darfur", "North Darfur"))
        self.assertFalse(wp.a_part_of("Attard", "Attard"))

    def test_the_half_is_passed_over_for_the_whole(self):
        got = wp.resolve(units("Al Batinah"),
                         {"Q1": {"names": ["Al Batinah"], "title": "Al Batinah South Governorate"},
                          "Q2": {"names": ["Al Batinah Region"], "title": "Al Batinah Region"}})
        self.assertEqual(got["u1"][:2], ("Q2", "Al Batinah Region"))


class ATownForTheRegionAroundIt(unittest.TestCase):
    """Morogoro, Brikama, Basse and Ajdabiya all arrived by redirect."""

    def setUp(self):
        self.saved = wp.claim_values

    def tearDown(self):
        wp.claim_values = self.saved

    def area(self, km2):
        wp.claim_values = lambda qid, prop: [{"mainsnak": {"datavalue": {"value": {
            "amount": f"+{km2}", "unit": "http://www.wikidata.org/entity/Q712226"}}}}
        ] if prop == "P2046" and km2 is not None else []

    def test_the_town_is_a_sliver_of_the_region_s_box(self):
        morogoro_region = [35.3, -10.0, 38.5, -5.8]
        self.area(260)
        self.assertIn("of the shape's", wp.too_small("Q243319", morogoro_region))

    def test_a_town_that_is_the_shape_fills_it(self):
        # Rezekne, 17.5 km^2, for the polygon Latvia draws for the state city.
        self.area(17.5)
        self.assertEqual(wp.too_small("Q180379", [27.28, 56.48, 27.39, 56.54]), "")

    def test_no_area_no_redirect(self):
        self.area(None)
        self.assertIn("no area", wp.too_small("Q916988", [16.5, 13.1, 16.9, 13.4]))

    def test_an_island_group_is_not_sized_by_its_ocean(self):
        # The Gilbert Islands: 279 km^2 of land in a box of 291,657. The shape
        # is the same sliver of the same box, so the share proves nothing.
        wp.claim_values = lambda qid, prop: (
            [{"mainsnak": {"datavalue": {"value": {"id": "Q33837"}}}}] if prop == "P31"
            else [{"mainsnak": {"datavalue": {"value": {
                "amount": "+279", "unit": "http://www.wikidata.org/entity/Q712226"}}}}]
            if prop == "P2046" else [])
        self.assertEqual(wp.too_small("Q271876", [172.7664, -2.6696, 176.8454, 3.1004]), "")

    def test_a_town_is_still_sized_whatever_else_it_is(self):
        # Maputo the city, for Maputo Province: a city, and 1% of the box.
        wp.claim_values = lambda qid, prop: (
            [{"mainsnak": {"datavalue": {"value": {"id": "Q515"}}}}] if prop == "P31"
            else [{"mainsnak": {"datavalue": {"value": {
                "amount": "+347", "unit": "http://www.wikidata.org/entity/Q712226"}}}}]
            if prop == "P2046" else [])
        self.assertIn("of the shape's", wp.too_small("Q3889", [31.9, -26.9, 33.0, -25.0]))


class ATitleThatNamesTheDivision(unittest.TestCase):
    def test_the_redirect_titles_that_name_their_kind(self):
        # Waived: the title is the division's. Asked: the title is a town's.
        for title in ("Quba District (Libya)", "Mizda District", "Iringa Region"):
            self.assertTrue(wp.says_its_kind(wp.disambiguated(title)), title)
        for title in ("Morogoro", "Zawiya, Libya", "Brikama", "Basse Santa Su", "Ajdabiya"):
            self.assertFalse(wp.says_its_kind(wp.disambiguated(title)), title)


class NotAnAdministrativeUnit(unittest.TestCase):
    def test_an_electoral_constituency_is_passed_over_for_the_region(self):
        got = wp.resolve(units("Northeastern Region"),
                         {"Q1": {"names": ["Northeastern"], "title": "Northeast (Althing constituency)"},
                          "Q2": {"names": ["Northeastern Region"], "title": "Northeastern Region (Iceland)"}})
        self.assertEqual(got["u1"][:2], ("Q2", "Northeastern Region (Iceland)"))

    def test_a_district_named_for_a_river_is_still_a_district(self):
        # Seychelles' La Riviere Anglaise district.
        self.assertIsNone(wp.NOT_A_UNIT.search("English River, Seychelles"))
        self.assertIsNone(wp.NOT_A_UNIT.search("Saint Andrew Parish, Jamaica"))


class AJoinTheBuildMadeBadly(unittest.TestCase):
    """Iceland's region shapes carried the constituencies' Wikidata items."""

    def setUp(self):
        self.saved = {n: getattr(wp, n) for n in (
            "country_item", "claims_of", "entities", "children", "contains",
            "search", "by_title", "languages", "statements", "declared")}
        items = {
            "Q_CONST": {"names": ["Northeast"], "title": "Northeast (Althing constituency)"},
            "Q_REGION": {"names": ["Northeastern Region"], "title": "Northeastern Region (Iceland)"},
        }
        wp.country_item = lambda iso3: "Q189"
        wp.claims_of = lambda qid: {}
        wp.languages = lambda claims: ["en"]
        wp.statements = lambda claims, prop: ["Q_REGION"] if prop == "P150" else []
        wp.entities = lambda qids, langs=("en",): {q: items[q] for q in qids if q in items}
        wp.children = lambda qid: []
        wp.contains = lambda qid: []
        wp.search = lambda *a, **k: {}
        wp.by_title = lambda *a, **k: None
        wp.declared = lambda *a, **k: None

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(wp, n, v)

    def test_the_constituency_is_dropped_and_the_region_found(self):
        shape = {"id": "ne", "name": "Northeastern Region", "wikidata": "Q_CONST"}
        got = wp.article_for("ISL", [shape], [shape], "Iceland")
        self.assertEqual(got["ne"][:2], ("Q_REGION", "Northeastern Region (Iceland)"))


class TwoRegionsInOneShape(unittest.TestCase):
    def setUp(self):
        self.saved = wp.api

    def tearDown(self):
        wp.api = self.saved

    def pages(self, **texts):
        wp.api = lambda endpoint, **params: {"parse": {
            "title": params["page"], "wikitext": texts.get(params["page"], "")}}

    def test_both_parts_read_and_are_summed(self):
        self.pages(**{"Tahoua Region": infobox(population_total="3,328,365",
                                                population_as_of="2012 census"),
                      "Agadez Region": infobox(population_total="487,620",
                                               population_as_of="2012 census")})
        got = wp.composite({"name": "Tahoua/Agadez"}, ("Tahoua Region", "Agadez Region"))
        self.assertEqual((got["value"], got["year"]), (3815985, 2012))
        self.assertEqual(got["title"], "Tahoua Region + Agadez Region")

    def test_one_part_missing_takes_nothing(self):
        self.pages(**{"Zinder Region": infobox(population_total="3,539,764")})
        self.assertIsNone(wp.composite({"name": "Zinder/Diffa"},
                                       ("Zinder Region", "Diffa Region")))

    def test_the_older_part_dates_the_sum(self):
        self.pages(**{"A": infobox(population_total="10", population_as_of="2012"),
                      "B": infobox(population_total="5", population_as_of="2020")})
        self.assertEqual(wp.composite({"name": "A/B"}, ("A", "B"))["year"], 2012)


class ARiverIsNotARegion(unittest.TestCase):
    def test_titles(self):
        for t in ("Togdheer River", "Mbomou River"):
            self.assertTrue(wp.NOT_A_UNIT.search(t), t)
        for t in ("English River, Seychelles", "Rivière du Rempart District", "Togdheer"):
            self.assertFalse(wp.NOT_A_UNIT.search(t), t)


class NobodyLivesThere(unittest.TestCase):
    def test_a_zero_is_read_where_the_article_says_uninhabited(self):
        text = infobox(population_total="0") + "Redonda is an uninhabited island."
        self.assertEqual(wp.read(text)[0], 0)

    def test_a_zero_is_not_read_where_it_might_be_a_blank(self):
        value, _, why = wp.read(infobox(population_total="0"))
        self.assertIsNone(value)
        self.assertIn("uninhabited", why)

    def test_the_word_itself_is_a_figure(self):
        text = infobox(population_total="Uninhabited") + "The islands are uninhabited."
        self.assertEqual(wp.read(text)[0], 0)


class TheStatisticsBlock(unittest.TestCase):
    def test_stat_pop1_with_its_own_year(self):
        # Cote d'Ivoire's regions keep the census figure here.
        text = infobox(stat_year1="2021", stat_pop1="1,000,508", stat_area1="12345")
        self.assertEqual(wp.read(text)[:2], (1000508, 2021))

    def test_population_total_still_comes_first(self):
        text = infobox(population_total="10", population_as_of="2020",
                       stat_year1="2014", stat_pop1="20")
        self.assertEqual(wp.read(text)[:2], (10, 2020))


class AnEmptyParameter(unittest.TestCase):
    def test_is_passed_over_for_the_next(self):
        text = infobox(population_census="", population_estimate="2,098,389",
                       population_estimate_year="2023")
        self.assertEqual(wp.read(text)[:2], (2098389, 2023))

    def test_an_unreadable_one_still_stops_the_reader(self):
        value, _, why = wp.read(infobox(population_total="1,15,6400",
                                        population_estimate="1156400"))
        self.assertIsNone(value)
        self.assertIn("population_total", why)


class AFailedDeclarationIsFinal(unittest.TestCase):
    """Gedaref's declared title was not an article, and the search found the city."""

    def setUp(self):
        self.saved = {n: getattr(wp, n) for n in (
            "country_item", "claims_of", "entities", "children", "contains",
            "search", "by_title", "languages", "statements", "declared")}
        wp.country_item = lambda iso3: "Q1049"
        wp.claims_of = lambda qid: {}
        wp.languages = lambda claims: ["en"]
        wp.statements = lambda claims, prop: []
        wp.entities = lambda qids, langs=("en",): {}
        wp.children = lambda qid: []
        wp.contains = lambda qid: []
        wp.search = lambda *a, **k: {"Q311199": {"names": ["Gedaref"], "title": "El-Gadarif"}}
        wp.by_title = lambda *a, **k: ("Q311199", "El-Gadarif")
        wp.declared = lambda *a, **k: None

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(wp, n, v)

    def test_the_name_is_not_tried_after_it(self):
        unit = {"id": "g", "name": "Gedaref"}
        self.assertIn(("SDN", "Gedaref"), wp.TITLES)
        self.assertEqual(wp.article_for("SDN", [unit], [unit], "Sudan"), {})

    def test_a_unit_with_no_declaration_still_searches(self):
        unit = {"id": "g", "name": "Gedaref"}
        self.assertEqual(wp.article_for("XXX", [unit], [unit], "Nowhere")["g"][0], "Q311199")


class AShapeNoArticleIsTheWholeOf(AFailedDeclarationIsFinal):
    """A shape declared unreadable is not searched for a part to publish as it."""

    def setUp(self):
        super().setUp()
        self.saved_unreadable = dict(wp.UNREADABLE)
        wp.UNREADABLE[("XXX", "Az Zahirah")] = "it holds three governorates"

    def tearDown(self):
        wp.UNREADABLE.clear()
        wp.UNREADABLE.update(self.saved_unreadable)
        super().tearDown()

    def test_nothing_is_searched_for(self):
        wp.search = lambda *a, **k: {"Q1468596": {"names": ["Az Zahirah"],
                                                  "title": "Al Dhahirah Governorate"}}
        unit = {"id": "z", "name": "Az Zahirah"}
        self.assertEqual(wp.article_for("XXX", [unit], [unit], "Oman"), {})


class DeclaredComposites(unittest.TestCase):
    """Shapes the map draws as several units, read as their articles summed."""

    def test_az_zahirah_is_three_governorates(self):
        self.assertEqual(set(wp.COMPOSITES[("OMN", "Az Zahirah")]),
                         {"Al Dhahirah Governorate", "Al Buraimi Governorate",
                          "Musandam Governorate"})

    def test_sud_is_mainland_southern_italy(self):
        parts = wp.COMPOSITES[("ITA", "Sud")]
        self.assertEqual(len(parts), 6)
        self.assertNotIn("Sicily", parts)
        self.assertNotIn("Southern Italy", parts)


class ADeclarationOverridesTheBuildsJoin(AFailedDeclarationIsFinal):
    """Savanes was joined on Wikidata to Savanes Region, a part of the district."""

    def setUp(self):
        super().setUp()
        self.saved_entities = wp.entities
        region = {"names": ["Savanes"], "title": "Savanes Region (Ivory Coast)"}
        wp.entities = lambda qids, langs=("en",): {q: region for q in qids if q == "Q1"}

    def unit(self):
        return {"id": "s", "name": "Savanes", "wikidata": "Q1"}

    def test_the_declared_district_wins(self):
        wp.declared = lambda *a, **k: ("Q2", "Savanes District")
        got = wp.article_for("CIV", [self.unit()], [self.unit()], "Ivory Coast")
        self.assertEqual(got["s"], ("Q2", "Savanes District", "declaration"))

    def test_a_failed_declaration_does_not_leave_the_join_standing(self):
        wp.declared = lambda *a, **k: None
        got = wp.article_for("CIV", [self.unit()], [self.unit()], "Ivory Coast")
        self.assertEqual(got, {})


class IvoryCoastsDistrictsAreNotItsRegions(unittest.TestCase):
    def test_each_redirect_that_reached_a_region_is_declared_to_the_district(self):
        for name in ("Denguele", "Lacs", "Montagnes", "Savanes", "Valle Du Bandama", "Zanzan"):
            self.assertTrue(wp.TITLES[("CIV", name)].endswith(" District"), name)


class Approximately(unittest.TestCase):
    """A stated figure with a stated uncertainty is read, and said to be approximate."""

    def test_the_real_ones(self):
        # The Gaza Strip, Beirut and the Liancourt Rocks, verbatim.
        for text, want in (("~2,050,000", 2050000), ("{{circa|433249}}", 433249),
                           ("Approximately 25", 25), ("c. 40,000", 40000)):
            self.assertEqual(wp.number(text)[0], want, text)
            self.assertTrue(wp.approximate(text), text)

    def test_read_carries_the_mark(self):
        value, year, remark = wp.read(infobox(population_estimate="~2,050,000",
                                              population_estimate_year="2023"))
        self.assertEqual((value, year), (2050000, 2023))
        self.assertEqual(remark, "approximate")

    def test_an_exact_figure_carries_none(self):
        self.assertEqual(wp.read(ZAMBIA)[2], "")
        self.assertFalse(wp.approximate("2252483"))


class ReadingsOffTheParameter(unittest.TestCase):
    """Figures an article gives some other way than a population parameter."""

    def test_a_un_template_is_recognised_and_expanded(self):
        text = infobox(population_total="{{UN_Population|Western Sahara}}{{UN_Population|ref}}",
                       population_note="({{UN_Population|Year}})")
        self.assertEqual(wp.read(text), (None, None, wp.FROM_UN))
        saved = wp.api
        answers = {"{{UN_Population|Western Sahara}}": "590,000", "{{UN_Population|Year}}": "2024"}
        wp.api = lambda endpoint, **p: {"expandtemplates": {"wikitext": answers[p["text"]]}}
        try:
            self.assertEqual(wp.un_population(text), (590000, 2024))
        finally:
            wp.api = saved

    def test_an_uninhabited_place_reads_zero_only_where_the_article_says_so(self):
        said = "{{Infobox islands\n| name = Senkaku Islands\n}}\nThe islands had been uninhabited."
        self.assertEqual(wp.declared_reading("127", "Senkakus", said, "")[:2], (0, None))
        silent = "{{Infobox islands\n| name = Senkaku Islands\n}}\nA group of islets."
        self.assertIsNone(wp.declared_reading("127", "Senkakus", silent, "")[0])

    def test_a_sole_settlement_is_read_only_where_it_is_the_only_one(self):
        base = "{{Infobox islands\n| name = Phoenix Islands\n| country1_largest_city_population = 20\n}}\n"
        self.assertEqual(wp.declared_reading(
            "KIR", "Phoenix Islands", base + "Kanton is the only inhabited one.", "")[:2], (20, None))
        self.assertIsNone(wp.declared_reading("KIR", "Phoenix Islands", base, "")[0])

    def test_an_undeclared_unit_is_not_read_off_the_parameter(self):
        text = "{{Infobox islands\n| country1_largest_city_population = 20\n}}\nuninhabited"
        self.assertEqual(wp.declared_reading("XXX", "Nowhere", text, "why"), (None, None, "why"))
