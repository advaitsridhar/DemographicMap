"""The build-side rules the Balkan census files rely on: which of two
compositions stands, when a statement displaces an encyclopaedia's head
count, and where the Balkan readers' labels sit in the group tree."""

import unittest

from scripts import build_entities as be
from scripts import canonical_groups as cg
from scripts import group_tree as gt


def composition(group: str) -> list[dict]:
    return [{"group": group, "pct": 100.0, "count": 10}]


class WikipediaTranscriptionTest(unittest.TestCase):
    """Serbia's district articles cite the 2022 census's 2023 release; RZS's
    own 2022 table must still stand in front of them."""

    WIKI = {"_source": "europe_wiki_serbia.json", "ethnicity": composition("Wikipedia"),
            "ethnicity_year": 2023}
    OFFICE = {"_source": "serbia_census.json", "ethnicity": composition("Serbian"),
              "ethnicity_year": 2022}

    def test_the_office_replaces_a_later_dated_transcription(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, dict(self.WIKI))
        be.merge_adapter(entity, dict(self.OFFICE))
        self.assertEqual(entity["ethnicity"][0]["group"], "Serbian")
        self.assertEqual(entity["ethnicity_year"], 2022)

    def test_a_transcription_read_after_the_office_is_held(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, dict(self.OFFICE))
        be.merge_adapter(entity, dict(self.WIKI))
        self.assertEqual(entity["ethnicity"][0]["group"], "Serbian")
        self.assertIn("ethnicity", entity["_held"])

    def test_two_transcriptions_still_go_by_year(self):
        entity = {"id": "x"}
        newer = dict(self.WIKI, _source="europe_wiki_bulgaria.json")
        older = dict(self.WIKI, ethnicity=composition("Older"), ethnicity_year=2011)
        be.merge_adapter(entity, newer)
        be.merge_adapter(entity, older)
        self.assertEqual(entity["ethnicity"][0]["group"], "Wikipedia")

    def test_a_survey_does_not_hold_a_transcription_back(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, {"_source": "ess_region_survey.json", "religion": composition("ESS"),
                                  "religion_year": 2020})
        be.merge_adapter(entity, {"_source": "europe_wiki_serbia.json", "religion": composition("Census"),
                                  "religion_year": 2011})
        self.assertEqual(entity["religion"][0]["group"], "Census")


class DisplacesBeforeTest(unittest.TestCase):
    """Cyprus: the census does not reach the north; Wikidata's 1973 figures
    stop standing in for its population."""

    STATEMENT = {"status": "not_available", "note": "outside the census", "displaces_before": 1974}

    def wikidata(self, year: int) -> dict:
        return {"_source": "wikidata_admin2.json", "population": {"value": 682, "year": year,
                                                                   "source": "Wikidata (CC0)"},
                "sources": [{"field": "population", "name": "Wikidata"}]}

    def test_a_1973_figure_is_displaced(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, self.wikidata(1973))
        be.merge_adapter(entity, {"_source": "cyprus_census.json", "population": dict(self.STATEMENT)})
        self.assertEqual(entity["population"]["status"], "not_available")
        self.assertEqual(entity["sources"], [])
        self.assertNotIn("population", entity.get("_held", {}))

    def test_a_later_figure_and_a_count_stand(self):
        for first in (self.wikidata(2011),
                      {"_source": "some_census.json", "population": {"value": 5, "year": 1960}}):
            entity = {"id": "x"}
            be.merge_adapter(entity, first)
            be.merge_adapter(entity, {"_source": "cyprus_census.json", "population": dict(self.STATEMENT)})
            self.assertIn("value", entity["population"])

    def test_a_plain_gap_still_never_overwrites(self):
        entity = {"id": "x"}
        be.merge_adapter(entity, self.wikidata(1973))
        be.merge_adapter(entity, {"_source": "cyprus_census.json",
                                  "population": {"status": "not_available", "note": "n"}})
        self.assertEqual(entity["population"]["value"], 682)


class BalkanLabelsTest(unittest.TestCase):
    """Every label the Balkan census files write reaches a tier-1 group or is
    a residual; the two argued-over identities are left unplaced."""

    PLACED = {
        "ethnicity": ["Bunjevac", "Transnistrian", "Cannot determine", "Suppressed (disclosure control)",
                      "Cypriot Maronite", "Cypriot Latin", "Not declared"],
        "language": ["Bunjevac", "Gorani", "Cannot determine", "No language data", "Not declared",
                     "Suppressed (disclosure control)"],
        "religion": ["Cannot determine", "Suppressed (disclosure control)", "Not declared"],
    }

    def test_placed(self):
        for field, labels in self.PLACED.items():
            tops = gt.tier1_names(field)
            for label in labels:
                name = next(iter(cg.canonicalise([{"group": label, "pct": 100.0, "count": 1}], field)))
                chain = gt.ancestry(field, name)
                self.assertTrue(cg.is_residual(name) and field != "language" or chain[-1] in tops,
                                f"{field}: {label} -> {chain}")

    def test_balkan_egyptian_is_not_egypts(self):
        self.assertIsNone(gt.parent_of("ethnicity", "Balkan Egyptian"))
        self.assertEqual(gt.parent_of("ethnicity", "Egyptian"), "Arab peoples")


if __name__ == "__main__":
    unittest.main()
