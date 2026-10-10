"""Round 6, derivations: a parent's only division, twins, single units, residuals.

Each test is a case the October 2026 audit of the published map found, cut
down to the few records that decide it; no network and no boundary file.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_entities as be  # noqa: E402
import common  # noqa: E402
from scripts.fetch_census import switzerland_nationality as sn  # noqa: E402
from scripts.fetch_census import vanuatu_census as vc  # noqa: E402
from scripts.fetch_census import wiki_table_population as wt  # noqa: E402

NA = common.NOT_AVAILABLE
GOOD = {"inside": 0.99, "share": 0.99, "spill": 0.0, "spill_by": None, "cover": [],
        "peopled": False}


def unit(uid, name, parent=None, **fields):
    out = {"id": uid, "name": name, "parent": parent, "sources": []}
    for f in be.SOLE_FIELDS:
        out[f] = common.gap(NA)
    out.update(fields)
    return out


def comp(**shares):
    return [{"group": g, "pct": p} for g, p in shares.items()]


class SoleChildren(unittest.TestCase):
    """A first-level unit's only division takes its figures when it is the same ground."""

    def pair(self, iso="CPV", parent_name="Praia", child_name="Nossa Senhora da Graca", **pf):
        parent = unit("P", parent_name, iso, **pf)
        child = unit("C", child_name, "P")
        return {iso: [parent]}, {iso: [child]}, parent, child

    def test_all_six_fields_copy_with_their_sources_and_one_sentence(self):
        a1, a2, parent, child = self.pair(
            population={"value": 130271, "source": "Wikidata (CC0)"},
            median_age={"value": 25.1, "unit": "years", "year": 2010, "source": "X"},
            sex_ratio={"value": 98.0, "unit": "males_per_100_females", "year": 2010,
                       "source": "X"},
            religion=comp(Catholic=78.2, Other=21.8), religion_year=2022,
            religion_note="Afrobarometer Round 9: a survey of 448 respondents.",
            language=[{"group": "Creole", "pct": None}],
            ethnicity=comp(A=100.0))
        parent["sources"] = [{"field": "religion", "name": "Afrobarometer"},
                             {"field": "population", "name": "Wikidata"}]
        filled, refused = be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(refused, [])
        self.assertEqual(len(filled), 6)
        self.assertEqual(child["population"]["value"], 130271)
        self.assertIn("is Praia's only division and covers the same ground",
                      child["population"]["note"])
        self.assertEqual(child["religion"], parent["religion"])
        self.assertIsNot(child["religion"], parent["religion"])
        self.assertEqual(child["religion_year"], 2022)
        # The survey's own caveat is carried over, then the sentence.
        self.assertTrue(child["religion_note"].startswith("Afrobarometer Round 9"))
        self.assertIn("only division", child["religion_note"])
        self.assertIn({"field": "religion", "name": "Afrobarometer"}, child["sources"])
        self.assertEqual(child["language"], [{"group": "Creole", "pct": None}])

    def test_a_stated_reason_or_a_policy_is_never_overwritten(self):
        a1, a2, parent, child = self.pair(religion=comp(A=100.0), ethnicity=comp(A=100.0))
        child["religion"] = common.gap(common.NOT_COLLECTED, "never asked")
        child["ethnicity"] = {**common.gap(NA, "no figure fits"), "not_this_ground": True}
        be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(child["religion"]["status"], common.NOT_COLLECTED)
        self.assertEqual(child["ethnicity"]["status"], NA)

    def test_a_country_whose_second_level_redraws_its_first_is_refused(self):
        # Algeria: 48 wilayas, each drawn again once at the second level.
        a1 = {"DZA": [unit(f"P{i}", f"W{i}", "DZA",
                           population={"value": 1000 + i, "year": 2008}) for i in range(3)]}
        a2 = {"DZA": [unit(f"C{i}", f"W{i}", f"P{i}") for i in range(3)]}
        a2["DZA"][0]["population"] = common.gap(NA, (
            "The Wikidata item joined here by name gives 88,266 (2008), which is 22% of "
            "W0's 399,714, though it is the only division drawn under W0. It is probably "
            "the town of this name rather than this unit, so its figure is left out."))
        filled, refused = be.fill_sole_children(a1, a2, {f"C{i}": GOOD for i in range(3)}, {})
        self.assertEqual(filled, [])
        self.assertEqual(len(refused), 3)
        self.assertIn("draws the first again", refused[0])
        first = a2["DZA"][0]["population"]["note"]
        self.assertIn("probably the town", first)
        self.assertIn("draws the 48 wilayas a second time", first)
        self.assertIn("draws the 48 wilayas a second time", a2["DZA"][1]["median_age"]["note"])

    def test_nothing_shows_the_division_is_the_only_one(self):
        a1, a2, _, child = self.pair(iso="COG", parent_name="Brazzaville", child_name="Zanaga",
                                     religion=comp(A=100.0))
        filled, refused = be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(filled, [])
        self.assertIn("nothing shows", refused[0])

    def test_a_code_list_with_one_division_is_evidence_and_a_namesake_elsewhere_is_not(self):
        codes = {"BEN": {be.norm("Littoral"): ["Cotonou"]}}
        a1, a2, _, child = self.pair(iso="BEN", parent_name="Littoral", child_name="Cotonou",
                                     religion=comp(A=100.0))
        filled, _ = be.fill_sole_children(a1, a2, {"C": GOOD}, codes)
        self.assertEqual(filled, ["BEN Littoral > Cotonou religion"])
        codes = {"COG": {be.norm("Brazzaville"): ["Brazzaville"],
                         be.norm("Lekoumou"): ["Zanaga", "Sibiti"]}}
        a1, a2, _, _ = self.pair(iso="COG", parent_name="Brazzaville", child_name="Zanaga",
                                 religion=comp(A=100.0))
        filled, refused = be.fill_sole_children(a1, a2, {"C": GOOD}, codes)
        self.assertEqual(filled, [])

    def test_the_drawing_must_be_the_same_ground(self):
        for measure, why in (({**GOOD, "inside": 0.53}, "only 53%"),
                             ({**GOOD, "spill": 0.68, "spill_by": "Black Point"},
                              "68% of Black Point"),
                             ({**GOOD, "cover": [(0.34, "Central Eleuthera", "P")]},
                              "Central Eleuthera covers 34%")):
            a1, a2, _, child = self.pair(iso="XXX", parent_name="Kyiv", child_name="Kyiv",
                                         religion=comp(A=100.0))
            filled, refused = be.fill_sole_children(a1, a2, {"C": measure}, {})
            self.assertEqual(filled, [], why)
            self.assertIn(why, refused[0])

    def test_a_parent_drawn_too_large_is_waived_only_where_its_extra_land_is_empty(self):
        # Littoral covers a quarter of Seme-Kpodji besides Cotonou; nobody lives there.
        codes = {"BEN": {be.norm("Littoral"): ["Cotonou"]}}
        large = {**GOOD, "share": 0.65, "cover": [(0.264, "Seme-Kpodji", "OUEME")]}
        a1, a2, _, child = self.pair(iso="BEN", parent_name="Littoral", child_name="Cotonou",
                                     religion=comp(A=100.0))
        filled, _ = be.fill_sole_children(a1, a2, {"C": large}, codes)
        self.assertEqual(len(filled), 1)
        a1, a2, _, child = self.pair(iso="BEN", parent_name="Littoral", child_name="Cotonou",
                                     religion=comp(A=100.0))
        filled, refused = be.fill_sole_children(a1, a2, {"C": {**large, "peopled": True}}, codes)
        self.assertEqual(filled, [])
        self.assertIn("Seme-Kpodji covers 26%", refused[0])
        # Without a code list holding the pair there is no waiver at all.
        a1, a2, _, _ = self.pair(iso="SYC", parent_name="La Digue a", child_name="La Digue",
                                 religion=comp(A=100.0))
        filled, _ = be.fill_sole_children(
            a1, a2, {"C": {**GOOD, "share": 0.32,
                           "cover": [(0.67, "Other Islands", "OUTER")]}}, {})
        self.assertEqual(filled, [])

    def test_two_counts_of_one_year_must_be_the_same_people(self):
        # Tuvalu's Alamoni is a village of Nui, drawn over the island.
        a1, a2, _, child = self.pair(iso="TUV", parent_name="Nui", child_name="Alamoni",
                                     population={"value": 610, "year": 2017},
                                     religion=comp(A=100.0))
        child["population"] = {"value": 290, "year": 2017}
        codes = {"TUV": {be.norm("Nui"): ["Alamoni"]}}
        filled, refused = be.fill_sole_children(a1, a2, {"C": GOOD}, codes)
        self.assertEqual(filled, [])
        self.assertIn("48% of its parent's people", refused[0])

    def test_a_parent_figure_of_other_ground_is_refused_row_or_source(self):
        # Afrobarometer's whole-island Fogo on one municipality.
        a1, a2, _, child = self.pair(parent_name="Santa Catarina do Fogo",
                                     child_name="Santa Catarina do Fogo",
                                     religion=comp(A=100.0),
                                     population={"value": 4725, "year": 2021, "source": "INE"})
        filled, refused = be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(filled, ["CPV Santa Catarina do Fogo > Santa Catarina do Fogo "
                                  "population"])
        self.assertIn("whole island of Fogo", refused[0])
        # The Bahamas' 2022 district rows, whichever route brought them.
        a1, a2, _, child = self.pair(iso="BHS", parent_name="East Grand Bahama",
                                     child_name="East Grand Bahama",
                                     population={"value": 11011, "year": 2022,
                                                 "source": "Wikidata (CC0)"})
        filled, refused = be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(filled, [])
        self.assertIn("supervisory districts", refused[0])
        # And a figure flagged as another ground's by its own source.
        a1, a2, _, child = self.pair(iso="XXX", parent_name="Same", child_name="Same",
                                     population={"value": 5, "year": 2020,
                                                 "not_this_ground": True})
        filled, _ = be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(filled, [])

    def test_an_office_count_shows_on_both_only_when_at_least_as_new(self):
        a1, a2, parent, child = self.pair(iso="BHS", parent_name="Long Island",
                                          child_name="Long Island",
                                          population={"value": 3024,
                                                      "source": "Wikidata (CC0)"})
        child["population"] = {"value": 3094, "year": 2010, "source": "DoS 2010"}
        filled, _ = be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(parent["population"]["value"], 3094)
        self.assertIn("both show this figure", parent["population"]["note"])
        # An older count does not take a newer encyclopaedia figure off (El Callao).
        a1, a2, parent, child = self.pair(iso="PER", parent_name="Callao",
                                          child_name="Callao",
                                          population={"value": 1226200, "year": 2025,
                                                      "source": "English Wikipedia, X"})
        child["population"] = {"value": 994494, "year": 2017, "source": "INEI 2017"}
        be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(parent["population"]["value"], 1226200)
        # Nor does a projection take a census's figure off (Centre, Kadiogo).
        a1, a2, parent, child = self.pair(iso="BFA", parent_name="Centre",
                                          child_name="Centre",
                                          population={"value": 3030384, "year": 2019,
                                                      "source": "English Wikipedia, X"})
        child["population"] = {"value": 3510028, "year": 2023, "source": (
            "OCHA, Common Operational Dataset -- population statistics (cod-ps-bfa)")}
        be.fill_sole_children(a1, a2, {"C": GOOD}, {})
        self.assertEqual(parent["population"]["value"], 3030384)
        self.assertEqual(child["population"]["value"], 3510028)


class SoleChildMeasures(unittest.TestCase):
    """The drawing, measured, with whole uninhabited islands left out."""

    def shapes(self, parent, child, others=()):
        from shapely.geometry import box
        adm1 = [{"shape_id": "P", "name": "P", "group": "XXX", "bbox": list(parent.bounds),
                 "_geom": parent}]
        adm2 = [{"shape_id": "C", "name": "C", "group": "XXX", "bbox": list(child.bounds),
                 "parent_shape": "P"}]
        geoms = {"C": child}
        for i, (g, owner) in enumerate(others):
            adm2.append({"shape_id": f"D{i}", "name": f"D{i}", "group": "XXX",
                         "bbox": list(g.bounds), "parent_shape": owner})
            geoms[f"D{i}"] = g
        return {"ADM1": adm1, "ADM2": adm2}, (lambda wanted: ((k, geoms[k]) for k in wanted)), box

    def test_an_islet_with_nobody_is_left_out_of_the_share(self):
        from shapely.geometry import MultiPolygon, Point, box
        main = box(0, 0, 10, 10)
        islet = box(20, 0, 22, 2)          # 4 of 104: drawn under another division
        parent = MultiPolygon([main, islet])
        shapes, geometry, _ = self.shapes(parent, box(0, 0, 10, 10), [(islet, "Q")])
        m = be.measure_sole_children([("XXX", {"id": "P"}, {"id": "C"})], shapes,
                                     geometry=geometry, points={"XXX": [Point(5, 5)]})
        self.assertEqual(m["C"]["share"], 1.0)
        self.assertEqual(m["C"]["cover"], [])
        # With a populated place on it, it counts.
        m = be.measure_sole_children([("XXX", {"id": "P"}, {"id": "C"})], shapes,
                                     geometry=geometry, points={"XXX": [Point(21, 1)]})
        self.assertLess(m["C"]["share"], 1.0)
        self.assertTrue(m["C"]["peopled"])

    def test_most_of_a_polygon_is_never_an_islet(self):
        # La Digue's district: the island is a third of the polygon.
        from shapely.geometry import MultiPolygon, Point, box
        island = box(0, 0, 1, 1)
        inner = box(5, 5, 7, 6)
        shapes, geometry, _ = self.shapes(MultiPolygon([island, inner]), island,
                                          [(inner, "OUTER")])
        m = be.measure_sole_children([("XXX", {"id": "P"}, {"id": "C"})], shapes,
                                     geometry=geometry, points={"XXX": [Point(0.5, 0.5)]})
        self.assertAlmostEqual(m["C"]["share"], 1 / 3, places=3)
        self.assertEqual(m["C"]["cover"][0][1], "D0")


class CodeLists(unittest.TestCase):
    def test_parents_and_their_divisions_from_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "cod_ps_admin2.json").write_text(json.dumps([
                {"id": "BEN-CODPS-BJ0800", "country": "BEN", "name": "Cotonou",
                 "parent_name": "Littoral"}]))
            (base / "clear_global_language.json").write_text(json.dumps([
                {"id": "BWA-CG-BW13", "level": "admin1", "country": "BWA", "name": "North East"},
                {"id": "BWA-CG-BW1301", "level": "admin2", "country": "BWA",
                 "name": "North East"},
                {"id": "BWA-CG-BW12", "level": "admin1", "country": "BWA", "name": "Central"},
                {"id": "BWA-CG-BW1201", "level": "admin2", "country": "BWA", "name": "Serowe"},
                {"id": "BWA-CG-BW1202", "level": "admin2", "country": "BWA",
                 "name": "Mahalapye"}]))
            codes = be.code_hierarchy(base)
        self.assertEqual(codes["BEN"][be.norm("Littoral")], ["Cotonou"])
        self.assertEqual(codes["BWA"][be.norm("North-East District")], ["North East"])
        self.assertEqual(len(codes["BWA"][be.norm("Central")]), 2)


class Twins(unittest.TestCase):
    """One polygon at both levels shows one population."""

    def run_twin(self, first, second, qids=(None, None)):
        a1 = {"X": [{"id": "S", "name": "S", "population": first, "wikidata": qids[0],
                     "sources": []}]}
        a2 = {"X": [{"id": "S", "name": "S", "population": second, "wikidata": qids[1],
                     "sources": []}]}
        be.fill_same_polygons(a1, a2)
        return a1["X"][0]["population"]["value"], a2["X"][0]["population"]["value"]

    def test_the_first_levels_district_over_the_towns_item(self):
        # Mauritius's Port Louis and Libya's Az Zawiyah and Al Qubbah.
        self.assertEqual(self.run_twin(
            {"value": 118123, "year": 2019, "source": "English Wikipedia, Port Louis District"},
            {"value": 149194, "year": 2012, "source": "Wikidata (CC0)"},
            ("Q960645", "Q3929")), (118123, 118123))
        self.assertEqual(self.run_twin(
            {"value": 290993, "year": 2006, "source": "English Wikipedia, Zawiya District"},
            {"value": 198567, "year": 2008, "source": "Wikidata (CC0)"}), (290993, 290993))
        self.assertEqual(self.run_twin(
            {"value": 93895, "source": "English Wikipedia, Districts of Libya"},
            {"value": 60610, "year": 2008, "source": "Wikidata (CC0)"}), (93895, 93895))

    def test_one_item_at_both_levels_shows_its_newer_figure(self):
        self.assertEqual(self.run_twin(
            {"value": 100, "year": 2011, "source": "Wikidata (CC0)"},
            {"value": 120, "year": 2025, "source": "Wikidata (CC0)"}, ("Q1", "Q1")),
            (120, 120))

    def test_two_offices_or_a_projection_stand_where_they_are(self):
        self.assertEqual(self.run_twin({"value": 100, "year": 2020, "source": "A"},
                                       {"value": 120, "year": 2024, "source": "B"}),
                         (100, 120))
        self.assertEqual(self.run_twin(
            {"value": 100, "year": 2019, "source": "Wikidata (CC0)"},
            {"value": 120, "year": 2023, "source": "OCHA, Common Operational Dataset"}),
            (100, 120))


class SingleUnitCountries(unittest.TestCase):
    """Western Sahara and Vatican City take the country's figures, twin included."""

    def test_scalars_and_a_list_without_shares_are_handed_down(self):
        nation = {"id": "ESH", "name": "Western Sahara",
                  "median_age": {"value": 21.8, "unit": "years", "source": "Factbook"},
                  "sex_ratio": {"value": 990, "year": 2020, "source": "Factbook"},
                  "language": [{"group": "Hassaniya Arabic", "pct": None,
                                "pct_status": NA}],
                  "sources": [{"field": "*", "name": "CIA World Factbook"}]}
        first = unit("DIS020", "Western Sahara", "ESH",
                     population={"value": 565581, "year": 2021})
        twin = unit("DIS020", "Western Sahara", "DIS020")
        done = be.inherit_single_unit([nation], {"ESH": [first]}, {"ESH": [twin]})
        self.assertIn("ESH Western Sahara median_age", done)
        self.assertIn("ESH Western Sahara language (drawn again)", done)
        for record in (first, twin):
            self.assertEqual(record["median_age"]["value"], 21.8)
            self.assertIn("drawn as a single first-level unit", record["median_age"]["note"])
            self.assertEqual(record["sex_ratio"]["value"], 990)
            self.assertEqual(record["language"][0]["group"], "Hassaniya Arabic")
            self.assertIn("single first-level unit", record["language_note"])
            self.assertIn({"field": "language", "name": "CIA World Factbook"},
                          record["sources"])
        # The unit's own population is its own.
        self.assertEqual(first["population"]["value"], 565581)


class Residuals(unittest.TestCase):
    """Shares are weighed only by populations of their own year, or by counts."""

    def setup(self, counts=False, years=(2011, 2011, 2011)):
        src = [{"name": "Census", "field": "language"}]
        comp_year, pop_year, target_year = years

        def rows(shares):
            return [{"group": g, "pct": p, **({"count": c} if counts else {})}
                    for g, p, c in shares]
        parent = {"id": "P", "name": "P", "sources": src, "language_year": comp_year,
                  "population": {"value": 1000, "year": pop_year},
                  "language": rows([("A", 62.0, 620), ("B", 38.0, 380)])}
        known = [{"id": f"d{i}", "name": f"D{i}", "parent": "P", "sources": src,
                  "language_year": comp_year,
                  "population": {"value": 300, "year": pop_year},
                  "language": rows([("A", 50.0, 150), ("B", 50.0, 150)])} for i in (1, 2)]
        blank = {"id": "d3", "name": "D3", "parent": "P", "sources": [],
                 "population": {"value": 400, "year": target_year},
                 "language": common.gap(NA)}
        return parent, known, blank

    def test_shares_of_one_year_priced_by_people_of_another_are_refused(self):
        # Latvia's 2011 shares by 2026 populations, Morocco's 2014 by 2024.
        parent, known, blank = self.setup(years=(2011, 2026, 2026))
        filled, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
        self.assertEqual(filled, [])
        self.assertIn("not of one year (2011, 2026)", refused[0])

    def test_counts_are_subtracted_whatever_the_populations_year(self):
        parent, known, blank = self.setup(counts=True, years=(2011, 2026, 2011))
        filled, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
        self.assertEqual(filled, ["X D3 language"])
        self.assertEqual({r["group"]: r["pct"] for r in blank["language"]["estimate"]},
                         {"A": 80.0, "B": 20.0})

    def test_a_parent_that_is_its_other_units_sum_leaves_nothing(self):
        # Ropazu novads is its three 2009-2021 units' 2011 counts: nothing for Vangazi.
        parent, known, blank = self.setup(counts=True)
        parent["language"] = [{"group": "A", "pct": 50.0, "count": 300},
                              {"group": "B", "pct": 50.0, "count": 300}]
        filled, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
        self.assertEqual(filled, [])
        self.assertIn("nothing is left over", refused[0])
        self.assertEqual(blank["language"]["status"], NA)

    def test_counts_need_the_units_own_people_to_check_against(self):
        parent, known, blank = self.setup(counts=True)
        blank["population"] = common.gap(NA)
        filled, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
        self.assertEqual(filled, [])
        self.assertIn("no published population", refused[0])

    def test_a_label_below_the_parents_print_cut_is_taken_as_none(self):
        # Kampong Thom: 299 people speaking an unknown language, 0.044% of the
        # province, which CLEAR prints as nothing; the district takes them out.
        parent, known, blank = self.setup()
        parent["population"] = {"value": 100000, "year": 2011}
        for k in known:
            k["population"] = {"value": 30000, "year": 2011}
        blank["population"] = {"value": 40000, "year": 2011}
        known[0]["language"] = comp(A=49.9, B=50.0, Unknown=0.1)
        filled, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
        self.assertEqual(filled, ["X D3 language"])
        self.assertNotIn("Unknown", {r["group"] for r in blank["language"]["estimate"]})
        # A label well above the cut is a finer question than the parent's.
        known[0]["language"] = comp(A=45.0, B=50.0, Unknown=5.0)
        blank["language"] = common.gap(NA)
        filled, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
        self.assertIn("name groups the national figure does not (Unknown)", refused[0])

    def test_cambodias_province_is_weighed_by_its_districts(self):
        parent, known, blank = self.setup()
        parent["population"] = {"value": 1009, "year": 2011}   # a census total, not the sum
        with mock.patch.object(be, "RESIDUAL_TOLERANCE", 0.001):
            _, refused = be.residual_grandchild({"X": [parent]}, {"X": [*known, blank]})
            self.assertIn("sum to 1,000 against a national 1,009", refused[0])
            filled, _ = be.residual_grandchild({"KHM": [parent]}, {"KHM": [*known, blank]})
        self.assertEqual(filled, ["KHM D3 language"])

    def test_assa_zag_says_why_it_has_no_figure(self):
        parent, known, blank = self.setup(years=(2014, 2024, 2024))
        blank["name"] = "Assa-Zag Province"
        be.residual_grandchild({"MAR": [parent]}, {"MAR": [*known, blank]})
        self.assertIn("no row for Assa-Zag", blank["language"]["note"])


class PolicyReasons(unittest.TestCase):
    """A source's own reason stands where the field is published for the unit's neighbours."""

    def test_a_reason_for_this_unit_is_kept_and_a_bare_gap_takes_the_policy(self):
        rows = [{"ethnicity": comp(Swiss=80.0, Other=20.0)},
                {"ethnicity": common.gap(NA, "Lac's 2009 outline is straddled by Murten.")},
                {"ethnicity": common.gap(NA)}]
        published = be.fields_published(rows)
        self.assertEqual(published, {"ethnicity"})
        self.assertEqual(be.own_reasons(rows[1], published), {"ethnicity"})
        self.assertEqual(be.own_reasons(rows[2], published), set())

    def test_where_no_neighbour_carries_the_field_the_policy_speaks(self):
        rows = [{"language": common.gap(NA, "Jamaica's census asks no language question.")}]
        self.assertEqual(be.own_reasons(rows[0], be.fields_published(rows)), set())


class TownFigureWording(unittest.TestCase):
    def test_a_sole_division_is_not_said_to_cover_the_same_ground(self):
        a1 = {"X": [{"id": "P", "name": "Adrar", "population": {"value": 399714}}]}
        a2 = {"X": [{"id": "C", "name": "Adrar", "parent": "P",
                     "population": {"value": 88266, "year": 2008,
                                    "source": "Wikidata (CC0)"}}]}
        self.assertEqual(be.refuse_town_figures(a1, a2), 1)
        note = a2["X"][0]["population"]["note"]
        self.assertNotIn("covers the same ground", note)
        self.assertIn("the only division drawn under Adrar", note)


class BahamasSupervisoryDistricts(unittest.TestCase):
    def test_the_three_rows_are_reasons_not_figures(self):
        self.assertNotIn(("BHS", "East Grand Bahama"), wt.FIGURES)
        why = wt.REFUSED[("BHS", "East Grand Bahama")]
        self.assertIn("supervisory district", why)
        self.assertIn("11,011", why)
        row = wt.refused_row("BHS", "East Grand Bahama", why, "S1")
        self.assertEqual(row["population"]["status"], NA)
        self.assertEqual(row["population"]["note"], why)
        self.assertEqual(row["sources"], [])


class LacCountsMurtenWhole(unittest.TestCase):
    CANTON = {"2116": "FR", "2101": "FR", "0661": "BE", "0700": "BE"}

    def test_a_merger_across_a_cantonal_line_counts_in_the_district_holding_the_rest(self):
        self.assertTrue(sn.crosses_canton_only({"2116", "2101", "0661"}, {"2116", "2101"},
                                               self.CANTON))
        # A merger across a district line inside one canton still straddles.
        canton = {**self.CANTON, "2200": "FR"}
        self.assertFalse(sn.crosses_canton_only({"2116", "2200"}, {"2116"}, canton))
        # And the district on the other side does not take it.
        self.assertFalse(sn.crosses_canton_only({"2116", "2101", "0661"}, {"0661", "0700"},
                                                self.CANTON))

    def test_the_note_says_whose_people_are_added_and_how_many(self):
        with mock.patch.object(sn, "last_count", return_value=(2021, 46.0)):
            note = sn.took_in_note(["2275"], {"2275": {"2116", "2101", "0661"}},
                                   {"2116", "2101"}, {"0661": {"Name": "Clavaleyres"}},
                                   {"2275": "Murten"}, "Lac")
        self.assertIn("Murten is counted whole", note)
        self.assertIn("Clavaleyres", note)
        self.assertIn("46 residents on 31 December 2021", note)


class AneityumsCutPanel(unittest.TestCase):
    def test_the_second_panel_is_the_province_less_its_other_councils(self):
        first = [100, 50, 50, 10, 5, 5, 2, 1, 1]
        rows = {"Aneityum": {9: first}}
        full = {"TAFEA": [0] * 9 + [40, 20, 20, 100, 50, 50, 3],
                "Tanna": [0] * 9 + [10, 5, 5, 50, 25, 25, 1]}
        out = vc.completed_panels(rows, full, {"TAFEA": ["Tanna", "Aneityum"]})
        values, province = out["Aneityum"]
        self.assertEqual(province, "TAFEA")
        self.assertEqual(values[9:], [30, 15, 15, 50, 25, 25, 2])
        # 10 English + 2 French + 30 Bislama + 50 vernacular + 2 not stated = 94, not 100:
        # read_language would refuse it; here it is only completed.
        self.assertEqual(values[:9], first)

    def test_nothing_is_completed_when_two_councils_lack_a_panel(self):
        rows = {"A": {9: [1] * 9}, "B": {9: [1] * 9}}
        full = {"TAFEA": [0] * 16}
        self.assertEqual(vc.completed_panels(rows, full, {"TAFEA": ["A", "B"]}), {})

    def test_the_note_names_what_was_completed(self):
        note = vc.completed_note({"total": 1260, "completed_from": "TAFEA",
                                  "counts": {"English": 28, "French": 6, "Bislama": 174,
                                             vc.VERNACULAR: 1052, "Not stated": 0}})
        self.assertIn("Tafea's less its other councils'", note)
        self.assertIn("1,260 people", note)


if __name__ == "__main__":
    unittest.main()
