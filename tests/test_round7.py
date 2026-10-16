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
        self.assertEqual(target["population"], {
            "value": 4_488, "year": 2025, "source": "Wikidata (CC0)",
            be.RESTATED_FROM: {"value": 4_975, "year": 2021, "source": CENSUS}})
        # The count is what a sum of compositions is weighed on, and is not
        # written out.
        self.assertIs(be.control_population(target), target["population"][be.RESTATED_FROM])
        self.assertIs(be.gate_population(target), target["population"][be.RESTATED_FROM])
        written = copy.deepcopy(target)
        be.drop_build_flags(written)
        self.assertEqual(written["population"],
                         {"value": 4_488, "year": 2025, "source": "Wikidata (CC0)"})
        # The count's own note and citation go with it, and are held for a
        # check that refuses the newer figure; a citation of several fields
        # stays for the others alone.
        self.assertNotIn("population_note", target)
        self.assertEqual([(s["name"], s["field"]) for s in target["sources"]],
                         [("Census tables", "religion"), ("Wikidata", "population")])
        held = target["_held"]["population"][0]
        self.assertEqual(held["value"]["value"], 4_975)
        self.assertEqual([(s["name"], s["field"]) for s in held["sources"]],
                         [(CENSUS, "population"), ("Census tables", "population")])
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

    def test_every_way_a_note_says_the_count_was_put_together(self):
        # Belarus's Gomel: the raion with its city, and Wikidata's 2026 Gomel
        # is the city alone. Costa Rica's Grecia: the canton without Río
        # Cuarto, and OCHA's 2021 Grecia the canton with it.
        gomel = unit("G", 581_020, 2019, newer=571_000, newer_year=2023,
                     note="The г.Гомель, Гомельский район as the 2019 census counted it; "
                          "with it the city of Gomel, the raion's seat, counted apart.")
        grecia = unit("R", 65_824, 2011, newer=70_000, newer_year=2015,
                      note="Without Río Cuarto, a district of it in 2011 and a canton of "
                           "its own since, which the boundary file draws apart.")
        bugaba = unit("B", 92_395, 2023, newer=93_000, newer_year=2025,
                      note="Includes Tierras Altas, created from it since the boundary "
                           "file was drawn.")
        be.prefer_newer_figures({}, country(gomel, grecia, bugaba,
                                            *self.peers(rate=-0.004)))
        self.assertEqual([e["population"]["value"] for e in (gomel, grecia, bugaba)],
                         [581_020, 65_824, 92_395])

    def test_a_note_that_says_nothing_was_counted_apart_is_no_composition(self):
        # China's counties: "its prefecture lists no development zone counted
        # apart" says the count is the county's alone.
        county = unit("C", 260_000, 2020, newer=262_000, newer_year=2022,
                      note="The 2020 census count of this county, read for the polygon "
                           "because it is still this one county: its prefecture lists no "
                           "development zone counted apart.")
        be.prefer_newer_figures({}, country(county, *self.peers(rate=0.004)))
        self.assertEqual(county["population"]["value"], 262_000)
        self.assertTrue(be.composed("which the census counts apart"))
        self.assertFalse(be.composed("no special unit the yearbook counts apart stands on it"))

    def test_a_figure_of_other_people_is_not_compared(self):
        # Korea's provinces: the register's Koreans and registered foreigners,
        # and Wikidata's figure the Koreans alone.
        incheon = unit("I", 3_078_426, 2023, newer=3_049_315, newer_year=2025,
                       country="KOR", newer_file="wikidata_admin1.json")
        peers = [unit(f"P{i}", 10_000, 2023, newer=10_000, newer_year=2025, country="KOR",
                      newer_file="wikidata_admin1.json") for i in range(5)]
        taken, kept = be.prefer_newer_figures(country(incheon, *peers, iso3="KOR"), {})
        self.assertEqual(incheon["population"]["value"], 3_078_426)
        self.assertEqual((taken, kept), ([], []))

    def test_figures_their_cited_source_does_not_give_are_not_compared(self):
        # Cambodia: Wikipedia's 889,970 "as of 2024" for Tboung Khmum, citing the
        # 2019 census's final results, which count 776,841.
        tbong = unit("T", 776_841, 2019, newer=889_970, newer_year=2024, country="KHM",
                     newer_file="wiki_population_admin1.json")
        peers = [unit(f"P{i}", 10_000, 2019, newer=11_000, newer_year=2024, country="KHM",
                      newer_file="wiki_population_admin1.json") for i in range(5)]
        taken, kept = be.prefer_newer_figures(country(tbong, *peers, iso3="KHM"), {})
        self.assertEqual(tbong["population"]["value"], 776_841)
        self.assertEqual(taken, [])
        self.assertIn("2019 census", be.OTHER_PEOPLE[("KHM", "wiki_population_admin1.json")])

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


class TwinsShowOneFigure(unittest.TestCase):
    """A polygon drawn at both levels shows the newer figure on both copies."""

    def test_a_figure_put_in_front_of_the_count_reaches_the_other_copy(self):
        # Malta's Birkirkara: Wikipedia's 30,166 for 2026 in front of the 2021
        # census's 25,807 a level up, the census's 25,807 alone a level down.
        census = {"value": 25_807, "year": 2021, "source": "NSO Malta, Census 2021"}
        first = {"id": "B", "name": "Birkirkara", "level": "admin1",
                 "population": {"value": 30_166, "year": 2026,
                                "source": "English Wikipedia, Birkirkara (infobox)",
                                be.RESTATED_FROM: dict(census)},
                 "sources": [{"field": "population", "name": "English Wikipedia"}]}
        second = {"id": "B", "name": "Birkirkara", "level": "admin2", "parent": "B",
                  "population": dict(census),
                  "population_note": "Residents counted by the census of 21 November 2021.",
                  "sources": [{"field": "population", "name": "NSO Malta"}]}
        be.fill_same_polygons({"MLT": [first]}, {"MLT": [second]})
        self.assertEqual(second["population"]["value"], 30_166)
        self.assertEqual(second["population"][be.RESTATED_FROM]["value"], 25_807)
        self.assertNotIn("population_note", second)
        self.assertEqual([s["name"] for s in second["sources"]], ["English Wikipedia"])
        # And the other way round: the second copy's newer figure goes up.
        first2 = {"id": "D", "name": "Domagnano", "level": "admin1",
                  "population": {"value": 3_613, "year": 2025, "source": "Ufficio di Statistica"}}
        second2 = {"id": "D", "name": "Domagnano", "level": "admin2",
                   "population": {"value": 3_620, "year": 2026, "source": "Wikidata (CC0)",
                                  be.RESTATED_FROM: {"value": 3_613, "year": 2025,
                                                     "source": "Ufficio di Statistica"}}}
        be.fill_same_polygons({"SMR": [first2]}, {"SMR": [second2]})
        self.assertEqual(first2["population"]["value"], 3_620)
        self.assertEqual(first2["population"][be.RESTATED_FROM]["value"], 3_613)


class UnionsAcrossFiles(unittest.TestCase):
    """A polygon drawn as a municipio was before a newer one was made out of it."""

    def rows(self, filename, pops, ratios=None, medians=None):
        out = []
        for i, (name, pop) in enumerate(pops):
            row = {"id": f"MEX-{filename[:3]}-{i}", "name": name, "level": "admin2",
                   "country": "MEX", "_source": filename, "sources": []}
            if pop is not None:
                row["population"] = {"value": pop, "year": 2020, "source": "INEGI 2020"}
            if ratios:
                row["sex_ratio"] = {"value": ratios[i], "unit": "males_per_1000_females",
                                    "year": 2020}
            if medians:
                row["median_age"] = {"value": medians[i], "unit": "years", "year": 2020}
            out.append(row)
        return out

    def test_each_files_rows_are_pooled_onto_the_polygon(self):
        census = self.rows("census.json", [("Tecpatán", 21_426), ("Mezcalapa", 23_847)],
                           ratios=[990, 962])
        ages = self.rows("ages.json", [("Tecpatán", None), ("Mezcalapa", None)],
                         medians=[25.0, 22.0])
        adapters = {"MEX": census + ages}
        spec = {"parts": {"census.json": tuple(r["id"] for r in census),
                          "ages.json": tuple(r["id"] for r in ages)},
                "shapes": (("admin2", "S1"),),
                "note": "Mezcalapa has no outline of its own and lies inside this one."}
        with mock.patch.object(be, "ROW_UNIONS", {("MEX", "Tecpatán"): spec}), \
                mock.patch.object(be, "log"):
            done = be.pool_row_unions(adapters)
        self.assertEqual(len(done), 2)
        pooled = {r["_source"]: r for r in adapters["MEX"]}
        self.assertEqual(set(pooled), {"census.json", "ages.json"})
        self.assertEqual(pooled["census.json"]["population"]["value"], 45_273)
        self.assertEqual(pooled["census.json"]["shape_id"], "S1")
        # Men and women from each part's population and ratio, summed: exact,
        # where a mean of the two ratios weighted by population is not.
        men = 21_426 * 990 / 1990 + 23_847 * 962 / 1962
        women = 21_426 * 1000 / 1990 + 23_847 * 1000 / 1962
        self.assertEqual(pooled["census.json"]["sex_ratio"]["value"],
                         int(round(men / women * 1000)))
        self.assertIn("Mezcalapa has no outline", pooled["census.json"]["sex_ratio_note"])
        # A median of the two together cannot be had from their medians.
        median = pooled["ages.json"]["median_age"]
        self.assertNotIn("value", median)
        self.assertIn("Tecpatán and Mezcalapa separately: the median of the two together",
                      median["note"])
        self.assertEqual(be.union_row_ids("ages.json"), set())  # outside the patch

    def test_a_median_of_three_parts_says_three(self):
        # Siltepec with Capitán Luis Ángel Vidal and Honduras de la Sierra.
        parts = self.rows("ages.json", [("Siltepec", None), ("Capitán Luis Ángel Vidal", None),
                                        ("Honduras de la Sierra", None)],
                          medians=[22.0, 21.0, 23.0])
        pooled = be.pool_rows("Siltepec", parts, "MEX", "ages.json")
        self.assertIn("the median of the three together", pooled["median_age"]["note"])

    def test_ratios_with_no_populations_to_weigh_them_are_a_stated_gap(self):
        parts = self.rows("ocha.json", [("A", None), ("B", None)], ratios=[1017, 990])
        pooled = be.pool_rows("A", parts, "MEX", "ocha.json")
        self.assertEqual(pooled["sex_ratio"]["status"], be.NOT_AVAILABLE)
        self.assertIn("A and B separately", pooled["sex_ratio"]["note"])

    def test_a_pooled_newer_figure_stands_in_front_of_a_pooled_count(self):
        # Ensenada with San Quintín: the 2020 census's 561,375 and OCHA's
        # 595,451 for 2024, both the two municipios added up.
        entity = unit("E", 561_375, 2020, newer=595_451, newer_year=2024,
                      note="The sum of the figures published for Ensenada and San "
                           "Quintín; the map draws them as one unit.",
                      newer_file="cod_ps_admin2.json", country="MEX")
        entity["_held"]["population"][0]["row"] = "MEX-POOL-ensenada-codpsadmin2json-admin2"
        lone = unit("L", 100_000, 2020, newer=103_000, newer_year=2024,
                    note="The sum of the figures published for L and M; the map draws "
                         "them as one unit.", newer_file="cod_ps_admin2.json",
                    country="MEX")
        lone["_held"]["population"][0]["row"] = "MEX-CODPS-MX99999"
        with mock.patch.dict(be.HELD_ROWS["cod_ps_admin2.json"], {"MEX": "x.json"}):
            be.prefer_newer_figures({}, country(entity, lone, iso3="MEX"))
        self.assertEqual(entity["population"]["value"], 595_451)
        # A figure for the municipio alone is not the polygon's.
        self.assertEqual(lone["population"]["value"], 100_000)


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

    def promoted(self, a1, parent, value, year):
        """The parent as prefer_newer_figures leaves it: Wikidata's newer
        figure in front of the count."""
        count = dict(parent["population"])
        parent["population"] = {"value": value, "year": year, "source": "Wikidata (CC0)",
                                be.RESTATED_FROM: count}
        parent.pop("population_note")
        return a1

    def test_the_note_names_the_count_the_unit_showed(self):
        # Xiangkhouang: the 2015 census's 244,684, behind it Wikidata's 267,172
        # for 2020, and OCHA's 2024 districts. A map never showed 267,172.
        a1, a2, parent = self.tables(760_000)
        self.promoted(a1, parent, 800_000, 2020)
        be.restate_encyclopaedia_parents(a1, a2, counts=True)
        self.assertEqual(parent["population"]["value"], 860_000)
        self.assertIn("It replaces 760,000 for 2015, an older figure from Lao Statistics "
                      "Bureau.", parent["population_note"])
        self.assertEqual(parent["population"][be.RESTATED_FROM]["value"], 760_000)

    def test_a_same_year_sum_stands_in_front_of_a_figure_put_in_front_this_build(self):
        # Papua: Wikidata's 2024 figure in front of BPS's 2022 count, and the
        # 29 regencies' own 2024 figures.
        register = "Kementerian Dalam Negeri, Dukcapil civil registration"
        a1, a2, parent = self.tables(760_000, year=2024, source=register)
        self.promoted(a1, parent, 870_000, 2024)
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2, counts=True),
                         ["LAO Province 870,000 -> 860,000"])
        self.assertIn("It replaces 760,000 for 2015", parent["population_note"])
        # An encyclopaedia's figure the build did not put in front of a count
        # keeps its year's place: Angola's 2024 provinces are Wikidata's,
        # its municipalities OCHA's projection of 2024.
        a1, a2, parent = self.tables(760_000, year=2024, source=register)
        parent["population"] = {"value": 870_000, "year": 2024, "source": "Wikidata (CC0)"}
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2, counts=True), [])

    def test_the_ground_a_restated_unit_is_drawn_on_is_still_said(self):
        a1, a2, parent = self.tables(760_000, iso3="MOZ")
        parent["name"] = "Maputo"
        be.restate_encyclopaedia_parents(a1, a2, counts=True)
        self.assertTrue(parent["population_note"].startswith(
            "The map draws Maputo City and Maputo Province as one shape. The sum "
            "of both divisions"), parent["population_note"])



class SharesWeighedByTheirCensus(unittest.TestCase):
    """A census's shares are priced at that census's counts, not at a newer
    figure shown in front of them."""

    @staticmethod
    def province(uid, name, people, shares):
        return {"id": uid, "name": name, "parent": "KHM",
                "population": {"value": people, "year": 2019, "source": CENSUS},
                "religion": [{"group": g, "pct": p} for g, p in shares.items()],
                "religion_year": 2019, "sources": []}

    def cambodia(self):
        country = {"id": "KHM", "name": "Cambodia",
                   "population": {"value": 3_060_000, "year": 2019, "source": CENSUS}}
        capital = self.province("A", "Phnom Penh", 2_281_951,
                                {"Buddhism": 97.0, "Islam": 1.5, "Christianity": 1.5})
        east = self.province("B", "Tbong Khmum", 776_841,
                             {"Buddhism": 88.0, "Islam": 11.8, "Christianity": 0.2})
        # As prefer_newer_figures leaves it: a 2024 figure in front of the count.
        east["population"] = {"value": 889_970, "year": 2024, "source": "Wikipedia",
                              be.RESTATED_FROM: dict(east["population"])}
        return country, [capital, east]

    def test_shares_are_taken_of_the_count_the_newer_figure_replaced(self):
        country, kids = self.cambodia()
        self.assertIsNone(be.roll_up_field(
            country, kids, "religion", level="first-level", over_published=True,
            complete=True, min_coverage=be.COUNTRY_MIN_COVERAGE,
            fill_population_only=True))
        counts = {r["group"]: r["count"] for r in country["religion"]}
        # 1.5% of 2,281,951 and 11.8% of 776,841, not of 889,970.
        self.assertEqual(counts["Islam"], round(0.015 * 2_281_951 + 0.118 * 776_841))
        self.assertAlmostEqual(sum(counts.values()), 2_281_951 + 776_841, delta=2)
        self.assertEqual(country["religion_year"], 2019)
        note = country["religion_note"]
        self.assertIn("For Tbong Khmum the population taken is 776,841 for 2019, the "
                      "figure it carried before the newer one shown.", note)
        # The populations the note totals are the ones the map shows.
        self.assertIn("Their populations total 3,171,921", note)
        # Shares taken of populations are no division's own counts.
        self.assertNotIn("own counts", note)

    def test_a_unit_shown_its_own_count_is_priced_at_it(self):
        country, kids = self.cambodia()
        kids[1]["population"] = kids[1]["population"][be.RESTATED_FROM]
        be.roll_up_field(country, kids, "religion", level="first-level",
                         over_published=True, complete=True,
                         min_coverage=be.COUNTRY_MIN_COVERAGE, fill_population_only=True)
        self.assertNotIn("population taken", country["religion_note"])
        self.assertEqual(be.repriced_sentence([]), "")



class BelarusRegionsJoinTheirOwnRows(unittest.TestCase):
    """Wikidata names three of Belarus's regions in Belarusian romanisation."""

    def test_each_alias_is_the_region_its_iso_code_names(self):
        import json
        rows = {r["id"]: r for r in json.loads(
            (be.PROCESSED / "wikidata_admin1.json").read_text()) if r.get("country") == "BLR"}
        drawn = {"BY-BR": "Brest", "BY-HR": "Grodno", "BY-MA": "Mogilev"}
        aliased = {rid: names for rid, names in be.ROW_ALIASES["wikidata_admin1.json"].items()
                   if rid.startswith("BLR-")}
        self.assertEqual(len(aliased), 3)
        for rid, names in aliased.items():
            self.assertEqual(names, (drawn[rows[rid]["iso_3166_2"]],), rid)
            self.assertEqual(rows[rid]["population"]["year"], 2026)



class LaosDistrictsOfOneName(unittest.TestCase):
    """OCHA's rows for Laos's repeated district names bind by their P-code."""

    def test_each_row_lands_on_its_own_provinces_polygon(self):
        import json
        rows = {r["id"]: r for r in json.loads(
            (be.PROCESSED / "cod_ps_admin2.json").read_text()) if r.get("country") == "LAO"}
        provinces = {"LA06": "Louangphabang", "LA16": "Champasack"}
        placed = {rid: v for rid, v in be.ROW_SHAPES["cod_ps_admin2.json"].items()
                  if rid.startswith("LAO-")}
        self.assertEqual(len(placed), 3)
        for rid, (shape, label) in placed.items():
            row = rows[rid]
            self.assertEqual(row["name"], label, rid)
            self.assertEqual(row["parent_name"], provinces[rid.split("-")[-1][:4]], rid)
            self.assertEqual(row["population"]["year"], 2024)
        # Two Phonthongs, two polygons.
        self.assertEqual(len({shape for shape, _ in placed.values()}), 3)



class FigureNotesLeaveWithTheirFigure(unittest.TestCase):
    """A note beside a figure goes when a later file's figure replaces it."""

    def test_a_census_median_does_not_keep_a_projections_note(self):
        # Mexico: OCHA's 2024 projection is read first, INEGI's 2020 census
        # after it, and the census's figure stands with nothing beside it.
        entity = {"id": "1", "name": "Xoxocotla", "level": "admin2", "country": "MEX"}
        be.merge_adapter(entity, {
            "_source": "cod_ps_age.json", "_match": "name",
            "median_age": {"value": 25.5, "year": 2024, "source": "OCHA COD-PS"},
            "median_age_note": "Interpolated from OCHA's 2024 projection.",
            "sex_ratio": {"value": 103.7, "year": 2024, "source": "OCHA COD-PS"},
            "sex_ratio_note": "Males per 100 females in OCHA's 2024 projection."})
        be.merge_adapter(entity, {
            "_source": "mexico_municipality_age.json", "_match": "shape_id",
            "median_age": {"value": 24.0, "year": 2020, "source": "INEGI"},
            "sex_ratio": {"value": 100.7, "year": 2020, "source": "INEGI"}})
        self.assertEqual(entity["median_age"]["value"], 24.0)
        self.assertEqual(entity["sex_ratio"]["value"], 100.7)
        self.assertNotIn("median_age_note", entity)
        self.assertNotIn("sex_ratio_note", entity)

    def test_a_note_the_replacing_row_gives_is_kept(self):
        entity = {"id": "1", "name": "Unit", "level": "admin2", "country": "MEX"}
        be.merge_adapter(entity, {
            "_source": "cod_ps_age.json", "_match": "name",
            "median_age": {"value": 25.5, "year": 2024, "source": "OCHA COD-PS"},
            "median_age_note": "A projection."})
        be.merge_adapter(entity, {
            "_source": "mexico_municipality_age.json", "_match": "shape_id",
            "median_age": {"value": 24.0, "year": 2020, "source": "INEGI"},
            "median_age_note": "The census's own median."})
        self.assertEqual(entity["median_age_note"], "The census's own median.")

    def test_a_held_projection_leaves_the_census_note_alone(self):
        entity = {"id": "1", "name": "Unit", "level": "admin2", "country": "MEX"}
        be.merge_adapter(entity, {
            "_source": "mexico_municipality_age.json", "_match": "shape_id",
            "median_age": {"value": 24.0, "year": 2020, "source": "INEGI"},
            "median_age_note": "The census's own median."})
        be.merge_adapter(entity, {
            "_source": "cod_ps_age.json", "_match": "name",
            "median_age": {"value": 25.5, "year": 2024, "source": "OCHA COD-PS"},
            "median_age_note": "A projection."})
        self.assertEqual(entity["median_age"]["value"], 24.0)
        self.assertEqual(entity["median_age_note"], "The census's own median.")


class TheMapNotTheFile(unittest.TestCase):
    """A visitor's note names the map, not the file it is drawn from."""

    def test_the_boundary_file_reads_the_map(self):
        entity = {"population": {"value": 1, "note": "The boundary file draws it coarsely."},
                  "population_note": "Includes Tolhuin, created since the boundary file was "
                                     "drawn, on boundaries redrawn since the boundary file's.",
                  "sources": [{"name": "geoBoundaries", "note": "the boundary file"}]}
        self.assertEqual(be.plain_record(entity), 3)
        self.assertEqual(entity["population"]["note"], "The map draws it coarsely.")
        self.assertEqual(entity["population_note"],
                         "Includes Tolhuin, created since the map was drawn, on boundaries "
                         "redrawn since the map's.")
        self.assertEqual(entity["sources"][0]["note"], "the map")
        self.assertEqual(be.plain_wording("geoBoundaries draws it"), "geoBoundaries draws it")


if __name__ == "__main__":
    unittest.main()
