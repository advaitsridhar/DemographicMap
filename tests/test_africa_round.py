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


if __name__ == "__main__":
    unittest.main()
