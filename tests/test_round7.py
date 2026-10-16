"""Round 7: a subdivision shows the most recent figure it was offered.

An encyclopaedia's population, or a projection held behind an office's census,
takes an older count's place where the two are the same ground by every test
the figures allow; the count comes back if a later check refuses the newer
figure. No network.
"""

import copy
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from scripts import build_entities as be

CENSUS = "Statistics Office, 2021 census"


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def unit(uid, people, year=2021, *, newer=None, newer_year=2025, match="name",
         note="Everyone the 2021 census counted.", source_file="office_census.json",
         country="XYZ", newer_file="wikidata_admin2.json"):
    """A second-level unit as the merge leaves it: the office's count shown,
    Wikidata's newer figure held behind it."""
    entity = {"id": uid, "name": f"Unit {uid}", "level": "admin2", "country": country,
              "wikidata": f"Q{uid}"}
    be.merge_adapter(entity, {
        "_source": newer_file, "_match": match, "wikidata": f"Q{uid}",
        "population": {"value": newer if newer is not None else people, "year": newer_year,
                       "source": "Wikidata (CC0)"},
        "sources": [{"field": "population", "name": "Wikidata"}]})
    be.merge_adapter(entity, {
        "_source": source_file, "_match": "shape_id",
        "population": {"value": people, "year": year, "source": CENSUS},
        "population_note": note,
        "sources": [{"field": "population", "name": CENSUS},
                    {"field": "population/religion", "name": "Census tables"}]})
    return entity


def country(*entities, iso3="XYZ"):
    return {iso3: list(entities)}


class NewerFigures(unittest.TestCase):
    def peers(self, n=5, rate=0.0, iso3="XYZ"):
        return [unit(f"P{i}", 10_000, newer=round(10_000 * (1 + rate) ** 4), country=iso3)
                for i in range(n)]

    def test_the_merge_still_holds_wikidata_behind_the_count(self):
        entity = unit("A", 4_975, newer=4_488)
        self.assertEqual(entity["population"]["value"], 4_975)
        self.assertEqual(entity["_held"]["population"][0]["value"]["value"], 4_488)

    def test_a_newer_figure_takes_the_counts_place(self):
        # Ponazyrevsky District: the 2020 census's 4,975 and Rosstat's 2025
        # estimate of 4,488 through Wikidata, a decline of 2.5% a year among
        # districts declining about as fast.
        target = unit("A", 4_975, newer=4_488)
        peers = self.peers(rate=-0.02)
        taken, kept = be.prefer_newer_figures({}, country(target, *peers))
        self.assertEqual(len(taken), 6)
        self.assertEqual(kept, [])
        self.assertEqual(target["population"],
                         {"value": 4_488, "year": 2025, "source": "Wikidata (CC0)"})
        # The count's own note and citation go with it, and are held for a
        # check that refuses the newer figure; a citation of several fields
        # stays.
        self.assertNotIn("population_note", target)
        self.assertEqual([s["name"] for s in target["sources"]], ["Census tables", "Wikidata"])
        held = target["_held"]["population"][0]
        self.assertEqual(held["value"]["value"], 4_975)
        self.assertEqual(held["unit_note"], "Everyone the 2021 census counted.")
        self.assertEqual(held["file"], "office_census.json")
        self.assertEqual(target["_from"]["population"], "wikidata_admin2.json")

    def test_far_from_its_countrys_change_it_is_kept_off(self):
        # Viet Nam's 2024 figures are mostly the provinces of 2025's merger,
        # 8.7% a year above the 2019 census; Cao Bang, never merged, moved 1%.
        merged = [unit(f"M{i}", 1_000_000, 2019, newer=round(1_000_000 * 1.09 ** 5),
                       newer_year=2024) for i in range(6)]
        cao_bang = unit("C", 530_341, 2019, newer=558_500, newer_year=2024)
        taken, kept = be.prefer_newer_figures(country(*merged, cao_bang), {})
        self.assertEqual(taken, [])
        self.assertEqual(len(kept), 7)
        self.assertEqual(cao_bang["population"]["value"], 530_341)

    def test_a_figure_joined_by_a_fragment_of_the_name_is_not_compared(self):
        # Norway's 2026 Kristiansand, three of 2019's kommuner since 2020.
        target = unit("K", 92_282, 2019, newer=119_287, newer_year=2026, match="prefix+state")
        taken, kept = be.prefer_newer_figures({}, country(target, *self.peers(rate=0.01)))
        self.assertEqual(target["population"]["value"], 92_282)
        self.assertNotIn("XYZ Unit K", " ".join(taken + kept))

    def test_a_count_put_together_for_the_polygon_stays(self):
        composed = unit("S", 135_932, 2001, newer=83_543, newer_year=2009,
                        note="The polygon is Konotopskyi Raion with Konotop (Miskrada), "
                             "which the census counts apart and the map draws inside it.")
        pinned = unit("E", 39_620, 2017, newer=52_362, newer_year=2023,
                      source_file="estonia_municipality.json")
        be.prefer_newer_figures({}, country(composed, pinned, *self.peers(rate=0.01)))
        self.assertEqual(composed["population"]["value"], 135_932)
        self.assertEqual(pinned["population"]["value"], 39_620)

    def test_more_than_ten_years_apart_is_not_compared(self):
        far = unit("F", 100_000, 2011, newer=110_000, newer_year=2025)
        be.prefer_newer_figures({}, country(far, *self.peers(rate=0.007)))
        self.assertEqual(far["population"]["value"], 100_000)

    def test_with_few_units_offered_the_band_is_narrow(self):
        # Trinidad and Tobago's Diego Martin: 102,957 in the 2011 census and
        # a round 150,000 for 2020, 4.3% a year in a country that hardly grows.
        diego = unit("D", 102_957, 2011, newer=150_000, newer_year=2020)
        port = unit("P", 37_074, 2015, newer=40_000, newer_year=2020)
        taken, kept = be.prefer_newer_figures(country(diego, port), {})
        self.assertEqual(diego["population"]["value"], 102_957)
        self.assertEqual(port["population"]["value"], 40_000)
        self.assertEqual((len(taken), len(kept)), (1, 1))

    def test_a_refusal_shows_the_count_again_with_its_note(self):
        target = unit("A", 4_975, newer=4_488)
        target["wikidata"] = "Q-town"
        be.prefer_newer_figures({}, country(target, *self.peers(rate=-0.02)))
        self.assertEqual(target["population"]["value"], 4_488)
        refused = be.gap(be.NOT_AVAILABLE, "A town's figure, so the figure is left out.")
        target["population"] = refused
        # As refuse_settlement_figures asks: anything but the refused item's.
        self.assertTrue(be.fall_back(target, refused, usable=lambda held: be.a_unit(
            held, "QA", {})))
        self.assertEqual(target["population"]["value"], 4_975)
        self.assertIn("shown instead", target["population"]["note"])
        self.assertEqual(target["population_note"], "Everyone the 2021 census counted.")
        self.assertEqual(target["wikidata"], "Q-town")
        self.assertIn(CENSUS, [s["name"] for s in target["sources"]])

    def test_a_stated_reason_is_never_replaced(self):
        entity = {"id": "G", "name": "Gap", "level": "admin2", "country": "XYZ"}
        be.merge_adapter(entity, {"_source": "office_census.json",
                                  "population": be.gap(be.NOT_AVAILABLE, "Not this ground.")})
        be.merge_adapter(entity, {"_source": "wikidata_admin2.json", "_match": "name",
                                  "population": {"value": 5, "year": 2025,
                                                 "source": "Wikidata (CC0)"}})
        # Filled, as an encyclopaedia's figure always filled a reason without
        # a year it displaces; nothing here is the recency pass's doing.
        before = copy.deepcopy(entity)
        be.prefer_newer_figures({}, country(entity))
        self.assertEqual(entity["population"], before["population"])


class HeldRows(unittest.TestCase):
    """A file held behind an office's count offers its population only."""

    def setUp(self):
        patcher = mock.patch.dict(be.HELD_ROWS, {"cod_ps_admin2.json": {"LAO": "laos_district.json"}})
        patcher.start()
        self.addCleanup(patcher.stop)

    def ocha(self, value=82_105, year=2024, iso3="LAO"):
        return be.offer_only({
            "_source": "cod_ps_admin2.json", "_match": "name", "country": iso3,
            "population": {"value": value, "year": year, "source": "OCHA COD-PS"},
            "sources": [{"field": "population", "name": "OCHA COD-PS"}]})

    def test_is_fill_only_by_country(self):
        self.assertTrue(be.is_fill_only("cod_ps_admin2.json", "LAO"))
        self.assertFalse(be.is_fill_only("cod_ps_admin2.json", "MOZ"))
        self.assertTrue(be.is_fill_only("wikidata_admin2.json", "MOZ"))

    def test_its_population_is_held_whatever_came_first(self):
        for order in ("ocha first", "census first"):
            entity = {"id": "C", "name": "Chanthabuly", "level": "admin2", "country": "LAO"}
            census = {"_source": "laos_district.json", "_match": "shape_id",
                      "population": {"value": 76_000, "year": 2015, "source": CENSUS}}
            rows = [self.ocha(), census] if order == "ocha first" else [census, self.ocha()]
            for row in rows:
                be.merge_adapter(entity, dict(row))
            self.assertEqual(entity["population"]["value"], 76_000, order)
            self.assertEqual([h["value"]["value"] for h in entity["_held"]["population"]],
                             [82_105], order)
            self.assertNotIn("OCHA COD-PS", [s["name"] for s in entity.get("sources", [])])

    def test_it_never_fills_a_stated_reason(self):
        entity = {"id": "C", "name": "Chanthabuly", "level": "admin2", "country": "LAO"}
        be.merge_adapter(entity, {"_source": "laos_district.json",
                                  "population": be.gap(be.NOT_AVAILABLE, "Drawn before a split.")})
        be.merge_adapter(entity, self.ocha())
        self.assertEqual(entity["population"]["note"], "Drawn before a split.")

    def test_it_stands_where_it_is_the_newer_same_ground(self):
        units = []
        for i in range(5):
            entity = {"id": f"D{i}", "name": f"District {i}", "level": "admin2", "country": "LAO"}
            be.merge_adapter(entity, {"_source": "laos_district.json", "_match": "shape_id",
                                      "population": {"value": 50_000, "year": 2015,
                                                     "source": CENSUS}})
            be.merge_adapter(entity, self.ocha(value=round(50_000 * 1.015 ** 9)))
            units.append(entity)
        taken, kept = be.prefer_newer_figures({}, {"LAO": units})
        self.assertEqual((len(taken), len(kept)), (5, 0))
        self.assertEqual(units[0]["population"]["source"], "OCHA COD-PS")
        self.assertEqual(units[0]["sources"], [{"field": "population", "name": "OCHA COD-PS"}])

    def test_a_row_keeps_only_what_places_it_and_its_population(self):
        row = {"id": "LAO-CODPS-LA0101", "name": "Chanthabuly", "country": "LAO",
               "level": "admin2", "parent_name": "Vientiane Capital",
               "_source": "cod_ps_admin2.json",
               "population": {"value": 82_105, "year": 2024},
               "median_age": {"status": "not_available"},
               "capital": {"status": "not_available"},
               "sources": [{"field": "population", "name": "OCHA"},
                           {"field": "median_age", "name": "OCHA"}]}
        kept = be.offer_only(row)
        self.assertTrue(kept["_offer"])
        self.assertNotIn("median_age", kept)
        self.assertNotIn("capital", kept)
        self.assertEqual(kept["sources"], [{"field": "population", "name": "OCHA"}])
        # Nothing of the mark reaches the record.
        entity = {"id": "C", "name": "Chanthabuly", "level": "admin2", "country": "LAO"}
        be.merge_adapter(entity, kept)
        self.assertNotIn("_offer", entity)
        self.assertNotIn("population", entity)

    def test_only_a_country_whose_office_file_is_read_holds_its_rows(self):
        with mock.patch.object(be, "ADAPTER_FILES", [f for f in be.ADAPTER_FILES
                                                     if f != "laos_district.json"]):
            self.assertNotIn("LAO", be.offered("cod_ps_admin2.json"))
        self.assertEqual(be.offered("cod_ps_admin2.json") & {"GTM", "DOM", "PRY"}, set())

    def test_held_and_dropped_countries_do_not_overlap(self):
        for filename, held in be.HELD_ROWS.items():
            self.assertEqual(set(held) & set(be.SUPERSEDED_ROWS.get(filename, {})), set(),
                             filename)


OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-lao), reference year 2024"


class ParentsFromNewerDivisions(unittest.TestCase):
    """A province's older count gives way to its districts' newer one-source sum."""

    def tables(self, own, own_year=2015, values=(410_000, 450_000), year=2024,
               source=OCHA, iso3="LAO"):
        parent = {"id": "P", "name": "Province", "parent": None,
                  "population": {"value": own, "year": own_year,
                                 "source": "Lao Statistics Bureau, 2015 census"},
                  "population_note": "The 2015 census's count.",
                  "sources": [{"field": "population", "name": "Lao Statistics Bureau"}]}
        kids = [{"id": f"K{i}", "name": f"District {i}", "parent": "P",
                 "population": {"value": v, "year": year, "source": source},
                 "sources": [{"field": "population", "name": source, "url": "u"}]}
                for i, v in enumerate(values)]
        return {iso3: [parent]}, {iso3: kids}, parent

    def test_an_older_count_takes_the_newer_sum(self):
        a1, a2, parent = self.tables(760_000)
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2), [])
        done = be.restate_encyclopaedia_parents(a1, a2, counts=True)
        self.assertEqual(done, ["LAO Province 760,000 -> 860,000"])
        self.assertEqual(parent["population"]["value"], 860_000)
        self.assertEqual(parent["population"]["year"], 2024)
        self.assertEqual(parent["population"][be.RESTATED_FROM]["value"], 760_000)
        self.assertIn("It replaces 760,000 for 2015, an older figure from Lao Statistics "
                      "Bureau.", parent["population_note"])
        self.assertEqual([s["name"] for s in parent["sources"]], [OCHA])

    def test_a_sum_further_off_than_growth_is_other_ground(self):
        # 40% above a count nine years older: more than people make.
        a1, a2, parent = self.tables(400_000)
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2, counts=True), [])
        self.assertEqual(parent["population"]["value"], 400_000)

    def test_a_projection_a_year_on_and_an_undated_count_stay(self):
        a1, a2, parent = self.tables(850_000, own_year=2023)
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2, counts=True), [])
        a1, a2, parent = self.tables(760_000)
        del parent["population"]["year"]
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2, counts=True), [])


if __name__ == "__main__":
    unittest.main()
