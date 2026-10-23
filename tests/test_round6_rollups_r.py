"""Round 6, roll-ups repaired: what a verifier of the roll-ups found.

A country's sum of its first level is gated on the figures its units carry for
themselves, not on the divisions' sums the reconcile pass put on them, and
those sums never become the country's population (R6-ROLLUPS-V2). A gap
sentence gives the years or the sources as the reason only where the figures
show it, and never says how two sources place people (V3). The test of the
published records holds of a site built with the passes as well as before them
(V1). A restated unit cites its new source alone for its population, a note
beside an empty sex ratio is in the published unit, and the Bahamas' grouped
districts are described as the supervisory-district table they come from (V5,
V6). No network.
"""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import build_entities as be  # noqa: E402
import check_rollups as cr  # noqa: E402

OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-xyz)"
CENSUS = "Instituto Nacional de Estadística, census"
FACTBOOK = "CIA World Factbook (public domain)"


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def unit(uid, name, people=None, year=None, source="Wikidata (CC0)", parent=None, **more):
    pop = ({"value": people, "year": year, "source": source} if people is not None
           else {"status": "not_available"})
    if pop.get("year") is None:
        pop.pop("year", None)
    return {"id": uid, "name": name, "parent": parent, "population": pop, "sources": [], **more}


def groups(field, counts, year=None, basis=None):
    total = sum(counts.values())
    rows = [{"group": g, "pct": round(100 * n / total, 1), "count": n} for g, n in counts.items()]
    out = {field: rows}
    if year:
        out[f"{field}_year"] = year
    if basis:
        out[f"{field}_basis"] = basis
    return out


def restated(entity, people, year, before, before_year):
    """A first-level unit as restate_encyclopaedia_parents leaves it."""
    entity["population"] = {"value": people, "year": year,
                            "source": "summed from 4 second-level divisions",
                            be.RESTATED_FROM: {"value": before, "year": before_year,
                                               "source": "Wikidata (CC0)"}}
    return entity


def sum_country(country, children, field):
    return be.roll_up_field(country, children, field, level="first-level", over_published=True,
                            complete=True, min_coverage=be.COUNTRY_MIN_COVERAGE,
                            fill_population_only=True)


# --------------------------------------------------------------------------
# R6-ROLLUPS-V2: the country's composition gate
# --------------------------------------------------------------------------

class CountryGateOnOwnFigures(unittest.TestCase):
    """The restate pass moves no country composition (R6-ROLLUPS-V2)."""

    def honduras(self, marked=True):
        # Two departments for eighteen: the 2013 census's ethnicity counts,
        # OCHA's 2024 projections shown, Wikidata's 2013 figures before them.
        country = {"id": "HND", "population": {"value": 9_529_188, "year": 2024,
                                               "source": FACTBOOK},
                   "ethnicity": [{"group": "Mestizo", "pct": 90.0},
                                 {"group": "Indigenous", "pct": 7.0}]}
        north = unit("N", "North", **groups("ethnicity", {"Mestizo": 3_500_000, "Lenca": 300_000,
                                                          "White": 200_000}, 2013))
        south = unit("S", "South", **groups("ethnicity", {"Mestizo": 2_840_000, "Lenca": 145_000,
                                                          "White": 390_000}, 2013))
        if marked:
            restated(north, 5_000_000, 2024, 4_200_000, 2013)
            restated(south, 4_878_457, 2024, 4_141_022, 2013)
        else:
            north["population"] = {"value": 5_000_000, "year": 2024, "source": OCHA}
            south["population"] = {"value": 4_878_457, "year": 2024, "source": OCHA}
        return country, [north, south]

    def test_census_counts_are_summed_on_the_units_own_figures(self):
        country, kids = self.honduras()
        self.assertIs(be.control_population(kids[0]), kids[0]["population"][be.RESTATED_FROM])
        self.assertIsNone(sum_country(country, kids, "ethnicity"))
        self.assertEqual(country["ethnicity"][0]["group"], "Mestizo")
        note = country["ethnicity_note"]
        # The note quotes the populations the map shows.
        self.assertIn("Their populations total 9,878,457 against a published 9,529,188", note)
        self.assertNotIn("disagrees", note)
        # And the country keeps its own population.
        self.assertEqual(country["population"]["value"], 9_529_188)
        self.assertNotIn("population_note", country)

    def test_the_sums_alone_would_have_refused_them(self):
        # As the verifier found: OCHA's 2024 projections 4% above the
        # Factbook's estimate, same year, against the 2% allowed.
        country, kids = self.honduras(marked=False)
        why = sum_country(country, kids, "ethnicity")
        self.assertIn("children sum to 9,878,457 against a published 9,529,188", why)
        self.assertEqual(country["ethnicity"][0], {"group": "Mestizo", "pct": 90.0})

    def test_survey_interviews_do_not_replace_a_line_on_projections_close_to_it(self):
        # Burkina Faso: thirteen regions' Afrobarometer shares, 1,191
        # interviews; OCHA's 2023 sums run close to the Factbook's estimate,
        # the 2019 census figures they replaced do not.
        country = {"id": "BFA", "population": {"value": 23_490_300, "year": 2025,
                                               "source": FACTBOOK},
                   "language": [{"group": "Mossi", "pct": 52.9}, {"group": "Fula", "pct": 7.8}]}
        east = restated(unit("E", "East", **groups("language", {"Mooré": 300, "Gulmacema": 290})),
                        11_000_000, 2023, 10_000_000, 2019)
        west = restated(unit("W", "West", **groups("language", {"Mooré": 353, "Dioula": 248})),
                        11_389_271, 2023, 10_485_695, 2019)
        why = sum_country(country, [east, west], "language")
        self.assertIn("children sum to 20,485,695 against a published 23,490,300", why)
        self.assertIn("they now total 22,389,271", why)
        self.assertEqual(country["language"][0], {"group": "Mossi", "pct": 52.9})

    def test_a_restated_first_level_never_becomes_the_countrys_population(self):
        def country():
            return {"id": "XYZ", "population": {"value": 1_000, "year": 2020, "source": FACTBOOK},
                    "religion": [{"group": "A", "pct": 60.0}, {"group": "B", "pct": 40.0}]}

        def kids():
            return [unit("K1", "One", 520, 2023, CENSUS,
                         **groups("religion", {"A": 300, "B": 220}, 2023)),
                    unit("K2", "Two", 520, 2023, CENSUS,
                         **groups("religion", {"A": 310, "B": 210}, 2023))]

        # A country keeps the Factbook's estimate beside an office's newer
        # count of every unit...
        plain = country()
        self.assertIsNone(sum_country(plain, kids(), "religion"))
        self.assertEqual(plain["population"]["value"], 1_000)
        # ...and beside sums put on the units to match their divisions.
        held = country()
        marked = kids()
        for k in marked:
            k["population"][be.RESTATED_FROM] = {"value": 510, "year": 2021}
        self.assertIsNone(sum_country(held, marked, "religion"))
        self.assertIsInstance(held["religion"], list)
        self.assertEqual(held["population"], {"value": 1_000, "year": 2020, "source": FACTBOOK})

    def test_a_waived_gate_says_the_disagreement_the_map_shows(self):
        # A country that publishes names only: the sum stands whatever the
        # gate finds, and the note says how far apart the shown figures are.
        def country():
            return {"id": "CAF", "population": {"value": 5_750_570, "year": 2025,
                                                "source": FACTBOOK},
                    "language": [{"group": "French"}, {"group": "Sangho"}]}

        def kids(shown):
            a = unit("A", "A", **groups("language", {"Sango": 600_000, "Gbaya": 400_000}, 2003))
            b = unit("B", "B", **groups("language", {"Sango": 500_000, "Banda": 900_000}, 2003))
            restated(a, shown[0], 2015, 2_000_000, 2003)
            restated(b, shown[1], 2015, 2_161_599, 2003)
            return [a, b]

        far = country()
        self.assertIsNone(sum_country(far, kids((2_400_000, 2_415_409)), "language"))
        self.assertIn("disagrees with the divisions' total of 4,815,409 by -16%",
                      far["language_note"])
        # Shown figures within 2% of the country: nothing to say, and still
        # no population taken from them.
        close = country()
        self.assertIsNone(sum_country(close, kids((2_850_000, 2_850_000)), "language"))
        self.assertNotIn("disagrees", close["language_note"])
        self.assertEqual(close["population"]["value"], 5_750_570)

    def test_the_flag_is_not_written(self):
        entity = restated(unit("P", "P"), 10, 2023, 8, 2011)
        self.assertEqual(be.drop_build_flags(entity), 1)
        self.assertNotIn(be.RESTATED_FROM, entity["population"])
        self.assertIs(be.control_population(entity), entity["population"])

    def test_a_unit_restated_by_any_pass_is_gated_on_its_own_figure(self):
        # Burkina Faso's Centre: the sole-division pass gives it Kadiogo's
        # OCHA figure, which unflagged moved the country's gate.
        centre = unit("C", "Centre", 3_030_384, 2019, "English Wikipedia, Kadiogo Region")
        east = unit("E", "East", 1_941_505, 2019, "English Wikipedia, Goulmou Region")
        same = unit("S", "Same", 1_000, 2019, CENSUS)
        empty = unit("G", "Gap")
        a1 = {"BFA": [centre, east, same, empty]}
        own = be.own_population_figures(a1)
        self.assertNotIn(("BFA", "G"), own)
        # The reconcile pass flags what it restates; another pass does not.
        restated(east, 2_184_593, 2023, 1_941_505, 2019)
        centre["population"] = {"value": 3_510_028, "year": 2023, "source": OCHA}
        empty["population"] = {"value": 50, "year": 2023, "source": OCHA}
        self.assertEqual(be.mark_restated_since(a1, own), ["BFA Centre"])
        self.assertEqual(be.control_population(centre),
                         {"value": 3_030_384, "year": 2019,
                          "source": "English Wikipedia, Kadiogo Region"})
        self.assertEqual(be.control_population(east)["value"], 1_941_505)
        self.assertIs(be.control_population(same), same["population"])
        self.assertIs(be.control_population(empty), empty["population"])

    def test_burkina_fasos_lines_stand_whichever_pass_restated_its_regions(self):
        country = {"id": "BFA", "population": {"value": 23_490_300, "year": 2025,
                                               "source": FACTBOOK},
                   "language": [{"group": "Mossi", "pct": 52.9}, {"group": "Fula", "pct": 7.8}]}
        centre = unit("C", "Centre", 3_030_384, 2019, "English Wikipedia",
                      **groups("language", {"Mooré": 200, "Dioula": 30}))
        west = unit("W", "West", 8_727_478, 2019, "English Wikipedia",
                    **groups("language", {"Mooré": 253, "Dioula": 208}))
        east = unit("E", "East", 8_727_477, 2019, "English Wikipedia",
                    **groups("language", {"Mooré": 200, "Fulfuldé": 300}))
        a1 = {"BFA": [centre, west, east]}
        own = be.own_population_figures(a1)
        restated(west, 9_679_444, 2023, 8_727_478, 2019)
        restated(east, 9_679_443, 2023, 8_727_477, 2019)
        centre["population"] = {"value": 3_510_028, "year": 2023, "source": OCHA}
        be.mark_restated_since(a1, own)
        quiet(be.roll_up_countries, [country], a1)
        self.assertEqual(country["language"][0], {"group": "Mossi", "pct": 52.9})
        # Without the flag on Centre, as the sole-division pass leaves it,
        # the projections bring the regions within the gate.
        country["language"] = [{"group": "Mossi", "pct": 52.9}]
        centre["population"].pop(be.RESTATED_FROM)
        quiet(be.roll_up_countries, [country], a1)
        self.assertEqual(country["language"][0]["group"], "Mooré")


# --------------------------------------------------------------------------
# R6-ROLLUPS-V3: what a gap sentence gives as the reason
# --------------------------------------------------------------------------

class GapReasons(unittest.TestCase):
    """The years or the sources are said only where the figures show them (R6-ROLLUPS-V3)."""

    def sentence(self, kids_total, kids_year, own, own_year, source=OCHA,
                 own_source="Wikidata (CC0)", n=3):
        kids = [unit(f"K{i}", f"K{i}", kids_total / n, kids_year, source) for i in range(n)]
        return cr.gap_sentence(cr.complete_sum(kids), own, own_year, own_source=own_source)

    def test_years_growth_can_cover_are_said(self):
        # Peru's Arequipa: the 2017 census's provinces under 2025.
        said = self.sentence(1_382_730, 2017, 1_656_215, 2025, "INEI, census")
        self.assertTrue(said.endswith("their figures are for 2017, 8 years before this one."))
        # Ukraine's Sumy Oblast: the 2001 census's raions over 2022, 1.1% fewer a year.
        said = self.sentence(1_296_763, 2001, 1_035_772, 2022, "State Statistics Service")
        self.assertTrue(said.endswith("their figures are for 2001, 21 years before this one."))

    def test_years_growth_cannot_cover_are_not_given_as_the_reason(self):
        cases = {
            # Tanzania's Katavi: OCHA's 2020 projection a third below the 2022 census.
            "Katavi": (776_274, 2020, 1_152_958, 2022),
            # Dar es Salaam: the projection 31% above the census two years on.
            "Dar es Salaam": (7_037_577, 2020, 5_383_728, 2022),
            # Malawi's Northern Region holding a Southern district: 128% in 15 years.
            "Northern Region": (3_879_010, 2023, 1_698_502, 2008),
        }
        for case, (total, year, own, own_year) in cases.items():
            said = self.sentence(total, year, own, own_year)
            self.assertNotIn("year", said.split(")", 1)[1], case)
            self.assertTrue(cr.explained([said], own, total), case)

    def test_two_sources_are_said_only_as_far_apart_as_two_accounts_of_one_ground(self):
        # Congo's Lomami: OCHA's 2020 territories a third above the province.
        said = self.sentence(3_991_994, 2020, 3_001_500, 2020)
        self.assertTrue(said.endswith("the two are different sources' figures for the same "
                                      "year."))
        # Madagascar's Vatovavy-Fitovinany: its figure is not its districts' ground.
        said = self.sentence(1_731_243, 2018, 730_207, 2018)
        self.assertTrue(said.endswith("137% above this figure."), said)

    def test_nothing_says_where_two_sources_place_people(self):
        for total, own in ((14_879_755, 11_000_000), (2_449_136, 1_855_000), (504_410, 720_000)):
            self.assertNotIn("place people", self.sentence(total, 2020, own, 2020))

    def test_a_kept_first_level_gives_its_own_reason_and_not_a_years_growth(self):
        parent = unit("P", "Harare", 2_427_209, 2022, "English Wikipedia, Harare (infobox)")
        kids = [unit(f"K{i}", f"K{i}", v, 2023, OCHA, parent="P")
                for i, v in enumerate((2_000_000, 1_078_170))]
        be.note_population_gaps([], {"ZWE": [parent]}, {"ZWE": kids})
        self.assertTrue(parent["population_note"].endswith(
            "27% above this figure; " + be.RESTATE_KEEPS["ZWE"] + "."))

    def test_the_build_writes_what_the_check_accepts(self):
        for total, year, own, own_year in ((776_274, 2020, 1_152_958, 2022),
                                           (1_731_243, 2018, 730_207, 2018)):
            parent = unit("P", "P", own, own_year)
            kids = [unit("K1", "K1", total / 2, year, OCHA, parent="P"),
                    unit("K2", "K2", total / 2, year, OCHA, parent="P")]
            a1, a2 = {"XYZ": [parent]}, {"XYZ": kids}
            be.note_population_gaps([], a1, a2)
            be.check_population_gaps_said([], a1, a2)

    def test_the_stopgap_for_misfiled_divisions_is_empty_once_they_are_filed(self):
        # Mangochi and Mukwe are filed by DECLARED_PARENTS now; their regions
        # take their divisions' sums like any other.
        self.assertEqual(be.MISFILED_DIVISIONS, {})
        self.assertEqual(be.DECLARED_PARENTS["42251766B89682559169951"],
                         ("MWI", "Southern Region"))
        self.assertEqual(be.DECLARED_PARENTS["8085530B20929283489058"], ("NAM", "Kavango"))


# --------------------------------------------------------------------------
# R6-ROLLUPS-V1: the published-records test after a rebuild
# --------------------------------------------------------------------------

class PublishedRecordsTestAfterARebuild(unittest.TestCase):
    """The passes find nothing left to say on records built with them (R6-ROLLUPS-V1)."""

    def test_a_site_built_with_the_passes_passes(self):
        import test_round6_rollups as t6
        census = "INE Venezuela, XIV Censo Nacional de Población y Vivienda 2011"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "admin1").mkdir()
            (root / "admin2").mkdir()
            capital = unit("P", "Distrito Capital", 1_943_901, 2011, census, parent="VEN")
            capital["population_note"] = ("The Capital District is the municipality of "
                                          "Libertador, the one division drawn inside it.")
            libertador = unit("L", "Libertador", 1_943_901, 2011, census, parent="P")
            (root / "admin0.json").write_text(json.dumps([
                {"id": "VEN", "name": "Venezuela",
                 "population": {"value": 2_000_000, "year": 2025, "source": FACTBOOK}}]))
            (root / "admin1" / "VEN.units.json").write_text(json.dumps([capital]))
            (root / "admin2" / "VEN.units.json").write_text(json.dumps([libertador]))
            (root / "build.json").write_text(json.dumps({"partial_levels": [],
                                                         "rollup_gap": cr.GAP}))
            case = t6.CheckRollups("test_the_passes_leave_no_gap_unsaid_on_the_published_records")
            with mock.patch.object(t6, "SITE", root), \
                    mock.patch.object(be, "load_country_detail", lambda: {}):
                case.test_the_passes_leave_no_gap_unsaid_on_the_published_records()


# --------------------------------------------------------------------------
# R6-ROLLUPS-V5, V6: notes and sources
# --------------------------------------------------------------------------

class RestatedSources(unittest.TestCase):
    """A restated unit cites the encyclopaedia for what else it gives, not its population (V6)."""

    def test_the_population_is_taken_off_a_shared_citation(self):
        parent = unit("P", "Northern", 2_508_201, 2015)
        parent["sources"] = [{"field": "population/capital/coordinates", "name": "Wikidata"},
                             {"field": "religion", "name": "Census"}]
        kids = [unit(f"K{i}", f"K{i}", v, 2020, OCHA, parent="P") for i, v in
                enumerate((1_400_000, 1_277_408))]
        kids[0]["sources"] = [{"field": "population", "name": OCHA, "url": "u"}]
        self.assertEqual(len(be.restate_encyclopaedia_parents({"SLE": [parent]},
                                                              {"SLE": kids})), 1)
        self.assertEqual([(s["field"], s["name"]) for s in parent["sources"]],
                         [("capital/coordinates", "Wikidata"), ("religion", "Census"),
                          ("population", OCHA)])


class SexRatioNoteBesideAGap(unittest.TestCase):
    """A note beside an empty sex ratio is in the unit every published one is in (V6)."""

    def test_the_unit_is_put_in_the_published_one(self):
        rows = [{"id": "anbre",
                 "sex_ratio": {"status": "not_available",
                               "note": "The 2010 count here has 1 men and 0 women."},
                 "sex_ratio_note": "Men per thousand women among the 1 people the 2010 base "
                                   "holds in the settlement."},
                {"id": "printed", "sex_ratio": {"status": "not_available"},
                 "sex_ratio_note": "706 females per 1,000 males in the 2011 table."}]
        self.assertEqual(be.one_sex_ratio_unit(rows), 0)
        self.assertEqual(rows[0]["sex_ratio_note"], "Men per hundred women among the 1 people "
                                                    "the 2010 base holds in the settlement.")
        self.assertEqual(rows[1]["sex_ratio_note"], "706 females per 1,000 males in the 2011 "
                                                    "table.")


class BahamasGroupedDistricts(unittest.TestCase):
    """A grouped row is a supervisory district's figure, as the refused rows say (V5)."""

    def test_the_gap_says_what_the_table_is(self):
        from scripts.fetch_census import wiki_table_population as wt
        from test_wiki_table_population import BAHAMAS, pages
        term = wt.GROUPED[("BHS", "Central Eleuthera")]
        row = quiet(wt.grouped_row, "BHS", "Central Eleuthera", term, "X1",
                    fetcher=pages(**{term.title: BAHAMAS}))
        note = row["population"]["note"]
        self.assertTrue(note.startswith(
            "Wikipedia's table of the Bahamas' local-government districts prints one 2022 "
            "census figure, 5,324 people, on a row for South Eleuthera and Central Eleuthera "
            "together. "), note)
        self.assertIn("drawn like the parliamentary constituencies rather than like the "
                      "local-government districts the map draws", note)
        self.assertIn("drawn like the parliamentary constituencies rather than like the "
                      "local-government districts the map draws", wt.SUPERVISORY)
        self.assertNotIn("census prints", note)
        self.assertNotIn("value", row["population"])


if __name__ == "__main__":
    unittest.main()
