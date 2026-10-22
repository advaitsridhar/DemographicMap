"""The Africa round: every bare population, median age and sex ratio says why.

The build already gave each bare religion, language and ethnicity the reason
the sources used allow. Populations, median ages and sex ratios went out bare
instead -- 5,700 median ages, 5,300 sex ratios and 850 populations before this
round, nearly all in Africa -- and the panel showed only a status label. No
network.
"""

import unittest

from scripts import build_entities as be

OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-ken), reference year 2019"


def unit(uid, *, population=None, median=None, ratio=None, sources=(), match="name",
         disputed=False):
    def value(v, unit=None):
        if v is None:
            return {"status": "not_available"}
        return {"value": v, "year": 2019, "source": OCHA, **({"unit": unit} if unit else {})}
    entity = {"id": uid, "name": f"Unit {uid}", "level": "admin2", "country": "KEN",
              "population": value(population), "median_age": value(median, "years"),
              "sex_ratio": value(ratio, "males_per_1000_females"),
              "sources": list(sources), "match": match}
    if disputed:
        entity["disputed"] = True
    return entity


def ocha(fields):
    return {"field": fields, "name": OCHA, "url": "https://data.humdata.org/dataset/cod-ps-ken"}


class ScalarReasons(unittest.TestCase):
    def test_beside_units_that_carry_it_the_note_says_how_far_the_source_reaches(self):
        rows = [unit("a", population=100, median=18.5, sources=[ocha("population/median_age")]),
                unit("b", population=200, median=19.0, sources=[ocha("population/median_age")]),
                unit("c", population=300, sources=[ocha("population")])]
        joined = be.joined_here(rows)
        be.say_why_scalar_empty(rows[2], "Kenya", joined)
        note = rows[2]["median_age"]["note"]
        self.assertIn("No median age figure has been found for this unit.", note)
        self.assertIn("gives it for 2 of the 3 units of Kenya at this level", note)
        self.assertEqual(rows[2]["median_age"]["status"], "not_available")
        # The sex ratio, which no unit carries, takes the other sentence.
        self.assertIn("gives a sex ratio for them", rows[2]["sex_ratio"]["note"])

    def test_where_no_unit_carries_it_the_note_names_the_sources_used(self):
        rows = [unit("a", population=100, sources=[ocha("population")]),
                unit("b", population=200, sources=[ocha("population")])]
        joined = be.joined_here(rows)
        be.say_why_scalar_empty(rows[0], "Kenya", joined)
        note = rows[0]["sex_ratio"]["note"]
        self.assertTrue(note.startswith("None of the sources used for the units of Kenya "
                                        "at this level ("), note)
        self.assertIn("gives a sex ratio for them", note)

    def test_with_no_source_at_all_it_says_so(self):
        rows = [unit("a", match=None), unit("b", match=None)]
        joined = be.joined_here(rows)
        self.assertEqual(be.say_why_scalar_empty(rows[0], "Kenya", joined), "no source read")
        self.assertIn("none of the sources used here gives figures for the units of Kenya",
                      rows[0]["population"]["note"])

    def test_a_figure_or_a_stated_reason_is_never_touched(self):
        rows = [unit("a", population=100, sources=[ocha("population")])]
        rows[0]["median_age"] = {"status": "not_available", "note": "The census gives ages by county only."}
        joined = be.joined_here(rows)
        be.say_why_scalar_empty(rows[0], "Kenya", joined)
        self.assertEqual(rows[0]["population"]["value"], 100)
        self.assertEqual(rows[0]["median_age"]["note"], "The census gives ages by county only.")

    def test_disputed_ground_gets_the_disputed_reason(self):
        rows = [unit("a", disputed=True)]
        be.say_why_scalar_empty(rows[0], "Kenya", be.joined_here(rows))
        self.assertEqual(rows[0]["median_age"]["note"], be.DISPUTED_GAP)

    def test_the_country_is_named_as_a_sentence_names_it(self):
        self.assertEqual(be.country_phrase("The Gambia"), "the Gambia")
        self.assertEqual(be.country_phrase("DRC"), "the DRC")
        self.assertEqual(be.country_phrase("Kenya"), "Kenya")


def shares(group):
    return [{"group": group, "pct": 100.0, "count": 10}]


class CompositionCitations(unittest.TestCase):
    """A survey cited for religion, ethnicity and language, beside a census
    that gives the first two, is cited for language alone."""

    SURVEY = {"_source": "afrobarometer_region.json", "religion": shares("Survey"),
              "ethnicity": shares("Survey"), "language": shares("Survey"),
              "sources": [{"field": "religion/ethnicity/language", "name": "Afrobarometer"}]}
    CENSUS = {"_source": "gambia_census.json", "religion": shares("Census"),
              "ethnicity": shares("Census"),
              "sources": [{"field": "religion/ethnicity", "name": "Gambia Bureau of Statistics"}]}

    def cited(self, entity):
        return {src["name"]: src["field"] for src in entity["sources"]}

    def test_a_census_read_after_the_survey_takes_its_fields_from_the_citation(self):
        entity = {"id": "x", "country": "GMB"}
        be.merge_adapter(entity, dict(self.SURVEY))
        be.merge_adapter(entity, dict(self.CENSUS))
        self.assertEqual(entity["religion"][0]["group"], "Census")
        self.assertEqual(self.cited(entity), {"Afrobarometer": "language",
                                              "Gambia Bureau of Statistics": "religion/ethnicity"})

    def test_a_survey_read_after_the_census_is_cited_for_what_it_gives(self):
        # A *_survey.json is ranked behind any count whatever the order read
        # (Afrobarometer's files are simply read first).
        entity = {"id": "x", "country": "GMB"}
        be.merge_adapter(entity, dict(self.CENSUS))
        be.merge_adapter(entity, dict(self.SURVEY, _source="gambia_region_survey.json"))
        self.assertEqual(entity["ethnicity"][0]["group"], "Census")
        self.assertEqual(entity["language"][0]["group"], "Survey")
        self.assertEqual(self.cited(entity)["Afrobarometer"], "language")

    def test_an_entry_citing_only_what_was_replaced_goes(self):
        self.assertIsNone(be.without_fields({"field": "religion"}, {"religion"}))
        same = {"field": "religion note"}
        self.assertIs(be.without_fields(same, {"religion"}), same)


class SeatReasons(unittest.TestCase):
    def test_where_seats_were_sought_a_bare_capital_says_so(self):
        entity = {"id": "a", "level": "admin2", "capital": {"status": "not_available"}}
        self.assertTrue(be.say_why_no_capital(entity, "ZMB"))
        self.assertEqual(entity["capital"]["note"], be.NO_SEAT_NAMED)

    def test_what_is_known_of_a_level_is_said_instead(self):
        entity = {"id": "a", "level": "admin2", "capital": {"status": "not_available"}}
        be.say_why_no_capital(entity, "KEN")
        self.assertIn("electoral areas", entity["capital"]["note"])

    def test_elsewhere_and_where_a_reason_or_a_seat_stands_nothing_changes(self):
        bare = {"id": "a", "level": "admin2", "capital": {"status": "not_available"}}
        self.assertFalse(be.say_why_no_capital(bare, "JPN"))
        self.assertNotIn("note", bare["capital"])
        stated = {"id": "b", "level": "admin2",
                  "capital": {"status": "not_available", "note": "The seat is contested."}}
        self.assertFalse(be.say_why_no_capital(stated, "SLE"))
        self.assertEqual(stated["capital"]["note"], "The seat is contested.")
        named = {"id": "c", "level": "admin2", "capital": "Kasama"}
        self.assertFalse(be.say_why_no_capital(named, "ZMB"))


class SeatFixes(unittest.TestCase):
    """Three seats Wikidata gets wrong, five GeoNames gives where its seats are
    not taken country-wide, and two labels that carry their disambiguation."""

    def test_the_wrong_seats_leave_their_rows(self):
        withdrawn = be.WITHDRAWN_FIELDS["wikidata_admin1.json"]
        for row_id in ("LBY-WD-Q32845", "LBY-WD-Q26023", "DZA-WD-Q233645", "ETH-WD-Q193494",
                       "TZA-WD-Q498067", "RWA-WD-Q845807", "GAB-WD-Q281109", "AGO-WD-Q191299"):
            self.assertEqual(set(withdrawn[row_id]), {"capital"})

    def test_a_declared_seat_fills_a_bare_capital_and_nothing_else(self):
        bare = {"id": "43142294B98309179755088", "capital": {"status": "not_available"}}
        held = {"id": "46179711B78983565091897", "capital": "Tanta City"}
        be.fill_capitals_from_geonames({"DZA": [bare], "EGY": [held]}, {})
        self.assertEqual(bare["capital"], "Tizi Ouzou")
        self.assertEqual(bare["sources"][-1]["name"], "GeoNames")
        self.assertEqual(bare["sources"][-1]["field"], "capital")
        self.assertEqual(held["capital"], "Tanta City")

    def test_a_declared_seat_stands_over_another_unit_s_seat_in_the_polygon(self):
        # Ouham as drawn holds Batangafo, Ouham-Fafa's seat since 2020.
        ouham = {"id": "63714938B89906779781300", "capital": {"status": "not_available"}}
        be.fill_capitals_from_geonames({"CAF": [ouham]}, {})
        self.assertEqual(ouham["capital"], "Bossangoa")

    def test_a_seat_that_is_another_unit_s_is_not_worn(self):
        rwampara = {"id": "47994165B31232091804297", "capital": {"status": "not_available"}}
        be.fill_capitals_from_geonames({}, {"UGA": [rwampara]})
        self.assertIn("Kibingo, is the seat of Sheema District", rwampara["capital"]["note"])

    def test_a_disambiguated_label_is_written_as_the_place_is_called(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        rows = [{"id": "COG-WD-Q855327", "country": "COG", "name": "Kouilou Department",
                 "level": "admin1", "capital": "Loango, Republic of Congo",
                 "sources": [{"field": "population/capital/coordinates", "name": "Wikidata"}]},
                {"id": "USA-WD-Q3551781", "country": "USA", "name": "District of Columbia",
                 "level": "admin1", "capital": "Washington, D.C."}]
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "wikidata_admin1.json").write_text(json.dumps(rows))
            with mock.patch.object(be, "PROCESSED", Path(tmp)), \
                    mock.patch.object(be, "ADAPTER_FILES", ["wikidata_admin1.json"]), \
                    mock.patch.object(be, "log", lambda *a, **k: None):
                loaded = be.load_adapters()
        self.assertEqual(loaded["COG"][0]["capital"], "Loango")
        self.assertEqual(loaded["USA"][0]["capital"], "Washington, D.C.")


class DisputedAndUnrecognisedSeats(unittest.TestCase):
    def test_a_disputed_polygon_says_why_it_has_no_seat_or_largest_settlement(self):
        entity = {"id": "111", "name": "Abyei", "level": "admin0",
                  "capital": {"status": "not_available"},
                  "largest_settlement": {"status": "not_available"},
                  "population": {"status": "not_available"}}
        be.disputed_record(entity, {})
        self.assertTrue(entity["capital"]["note"].endswith("No source used here names a seat for it."))
        self.assertIn("names a largest settlement", entity["largest_settlement"]["note"])
        self.assertEqual(entity["population"]["note"], be.DISPUTED_GAP)

    def test_western_sahara_says_at_the_country_what_its_units_say(self):
        admin0 = [{"id": "ESH", "capital": {"status": "not_available"}},
                  {"id": "MAR", "capital": "Rabat"},
                  {"id": "TKL", "capital": {"status": "not_available"}}]
        self.assertEqual(be.say_why_no_country_seat(admin0), 1)
        self.assertEqual(admin0[0]["capital"]["note"], be.NO_SEAT["ESH"])
        self.assertEqual(admin0[1]["capital"], "Rabat")
        self.assertNotIn("note", admin0[2]["capital"])


class LanguagesPlaced(unittest.TestCase):
    """Three languages that led a unit with no family to colour it."""

    def test_each_takes_its_family(self):
        import group_tree
        for name, parent in (("Subiya", "Bantu languages"),
                             ("Basa (Nigeria)", "Volta-Niger languages"),
                             ("Shetagna", "Semitic languages")):
            self.assertEqual(group_tree.parent_of("language", name), parent, name)
        # Talé is still not reliably one family.
        self.assertIsNone(group_tree.parent_of("language", "Tal\u00e9"))


if __name__ == "__main__":
    unittest.main()
