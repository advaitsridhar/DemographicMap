"""The build-side rules Western Asia's and Uzbekistan's statements rely on:
an undated encyclopaedia figure displaced where the statement says so, and
Lebanon's survey read after the encyclopaedic floor."""

import unittest

from scripts import build_entities as be


def wikidata(year=None, source="wikidata_admin2.json"):
    population = {"value": 80000, "source": "Wikidata (CC0)"}
    if year is not None:
        population["year"] = year
    return {"_source": source, "population": population,
            "sources": [{"field": "population", "name": "Wikidata"}]}


def statement(**extra):
    return {"_source": "uzbekistan_siat.json",
            "population": dict({"status": "not_available", "note": "no count reaches it",
                                "displaces_before": 2026}, **extra)}


class DisplacesUndatedTest(unittest.TestCase):
    def test_an_undated_figure_is_displaced_where_the_statement_says_so(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, wikidata())
        be.merge_adapter(entity, statement(displaces_undated=True))
        self.assertEqual(entity["population"]["status"], "not_available")
        self.assertEqual(entity["population"]["note"], "no count reaches it")
        self.assertEqual(entity["sources"], [])

    def test_without_the_flag_an_undated_figure_stands(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, wikidata())
        be.merge_adapter(entity, statement())
        self.assertEqual(entity["population"]["value"], 80000)

    def test_a_dated_figure_goes_by_its_year_as_before(self):
        for year, displaced in ((2014, True), (2026, False)):
            entity = {"id": "x"}
            be.merge_adapter(entity, wikidata(year))
            be.merge_adapter(entity, statement(displaces_undated=True))
            self.assertEqual("value" not in entity["population"], displaced, year)

    def test_a_count_is_never_displaced(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, {"_source": "some_census.json",
                                  "population": {"value": 5, "source": "a census"}})
        be.merge_adapter(entity, statement(displaces_undated=True))
        self.assertEqual(entity["population"]["value"], 5)


class LebanonOrderTest(unittest.TestCase):
    def test_lebanon_s_survey_is_read_after_the_encyclopaedic_floor(self):
        files = be.ADAPTER_FILES
        for floor in ("wikidata_admin1.json", "wikidata_admin2.json",
                      "wiki_population_admin1.json", "wiki_table_population.json"):
            self.assertLess(files.index(floor), files.index("lebanon_survey.json"), floor)

    def test_a_caza_statement_replaces_wikidata_s_bare_reason(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, {"_source": "wikidata_admin2.json",
                                  "population": {"status": "not_available",
                                                 "note": "No P1082 statement on Wikidata."}})
        be.merge_adapter(entity, {"_source": "lebanon_survey.json",
                                  "population": {"status": "not_available",
                                                 "note": "Lebanon has taken no census since 1932.",
                                                 "displaces_before": 2026,
                                                 "displaces_undated": True}})
        self.assertIn("1932", entity["population"]["note"])


if __name__ == "__main__":
    unittest.main()
