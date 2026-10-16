"""Round 6, derivations repaired: what a verifier of the derivations found.

A first-level unit the sole-division pass restates keeps the figure it carried
for itself for its country's gate, so Burkina Faso's census and Factbook lines
are not replaced by a survey's interviews; a restated or synced unit cites the
source of the figure it now shows and no other record's item; a country drawn
as one unit says in the country's words why it has no shares to hand down;
Aneityum's language note adds up as shown; a Swiss district straddled by a
merged commune says so in plain words. No network.
"""

import copy
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_entities as be  # noqa: E402
import common  # noqa: E402
from scripts.fetch_census import switzerland_nationality as sn  # noqa: E402
from scripts.fetch_census import vanuatu_census as vc  # noqa: E402

NA = common.NOT_AVAILABLE
GOOD = {"inside": 0.99, "share": 0.99, "spill": 0.0, "spill_by": None, "cover": [],
        "peopled": False}
OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-bfa), reference year 2023"
WIKIPEDIA = "English Wikipedia, Kadiogo Region (infobox)"
FACTBOOK = "CIA World Factbook (public domain), factbook.json mirror"
AFROBAROMETER = {"field": "religion/ethnicity/language", "name": "Afrobarometer Round 9",
                 "url": "https://www.afrobarometer.org/data/"}


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def unit(uid, name, parent=None, **fields):
    out = {"id": uid, "name": name, "parent": parent, "sources": []}
    for f in be.SOLE_FIELDS:
        out[f] = common.gap(NA)
    out.update(fields)
    return out


def counted(**counts):
    total = sum(counts.values())
    return [{"group": g, "pct": round(100 * n / total, 1), "count": n}
            for g, n in counts.items()]


def centre_and_kadiogo():
    """Burkina Faso's Centre over its one province, as the build has them."""
    centre = unit("C", "Centre", "BFA",
                  population={"value": 3_030_384, "year": 2019, "source": WIKIPEDIA},
                  religion=counted(Muslim=150, Catholic=80))
    centre["sources"] = [dict(AFROBAROMETER),
                         {"field": "population", "name": "Wikipedia",
                          "url": "https://en.wikipedia.org/wiki/Kadiogo_Region"}]
    kadiogo = unit("K", "Kadiogo", "C",
                   population={"value": 3_510_028, "year": 2023, "source": OCHA})
    kadiogo["sources"] = [{"field": "population/capital/coordinates", "name": "Wikidata",
                           "url": "https://www.wikidata.org/wiki/Q1074530"},
                          {"field": "population", "name": OCHA,
                           "url": "https://data.humdata.org/dataset/cod-ps-bfa"}]
    return centre, kadiogo


CODES = {"BFA": {be.norm("Centre"): ["Kadiogo"]}}


# --------------------------------------------------------------------------
# bfa-country-gate: a restated unit is gated on its own figure
# --------------------------------------------------------------------------

class RestatedParentsAreFlagged(unittest.TestCase):

    def test_centre_keeps_its_own_figure_for_the_countrys_gate(self):
        centre, kadiogo = centre_and_kadiogo()
        be.fill_sole_children({"BFA": [centre]}, {"BFA": [kadiogo]}, {"K": GOOD}, CODES)
        self.assertEqual(centre["population"]["value"], 3_510_028)
        own = {"value": 3_030_384, "year": 2019, "source": WIKIPEDIA}
        self.assertEqual(centre["population"][be.RESTATED_FROM], own)
        self.assertEqual(be.control_population(centre), own)
        # The roll-ups' own flagging finds it flagged already and leaves it.
        self.assertEqual(be.mark_restated_since({"BFA": [centre]},
                                                {("BFA", "C"): own}), [])
        # The flag is the build's and is not written.
        written = copy.deepcopy(centre)
        be.drop_build_flags(written)
        self.assertNotIn(be.RESTATED_FROM, written["population"])

    def test_an_office_count_synced_onto_the_parent_is_flagged(self):
        # The Bahamas' Long Island: Wikidata's undated 3,024 gives way to the
        # Department of Statistics' 3,094 for 2010 on its one division.
        parent = unit("P", "Long Island", "BHS",
                      population={"value": 3024, "source": "Wikidata (CC0)"})
        child = unit("C", "Long Island", "P",
                     population={"value": 3094, "year": 2010, "source": "DoS 2010"})
        be.fill_sole_children({"BHS": [parent]}, {"BHS": [child]}, {"C": GOOD}, {})
        self.assertEqual(parent["population"]["value"], 3094)
        self.assertEqual(be.control_population(parent),
                         {"value": 3024, "source": "Wikidata (CC0)"})
        # The division, which gave its figure, carries no flag.
        self.assertNotIn(be.RESTATED_FROM, child["population"])

    def test_the_figure_first_replaced_is_the_one_kept(self):
        centre, kadiogo = centre_and_kadiogo()
        first = {"value": 2_800_000, "year": 2015, "source": "Wikidata (CC0)"}
        centre["population"][be.RESTATED_FROM] = dict(first)
        be.fill_sole_children({"BFA": [centre]}, {"BFA": [kadiogo]}, {"K": GOOD}, CODES)
        self.assertEqual(centre["population"][be.RESTATED_FROM], first)

    def test_a_copied_figure_never_carries_another_records_flag(self):
        source = {"population": {"value": 5, "year": 2020, "source": "X",
                                 be.RESTATED_FROM: {"value": 4}}, "sources": []}
        target = {"population": common.gap(NA), "sources": []}
        be.copy_field(source, target, "population")
        self.assertEqual(target["population"], {"value": 5, "year": 2020, "source": "X"})
        self.assertIn(be.RESTATED_FROM, source["population"])

    def test_a_first_level_twin_that_gives_way_is_flagged(self):
        # One polygon at both levels: an office's count on the second copy,
        # at least as new as the encyclopaedia's on the first, shows on both.
        first = {"id": "S", "name": "S", "sources": [],
                 "population": {"value": 100, "year": 2019, "source": "Wikidata (CC0)"}}
        second = {"id": "S", "name": "S", "sources": [],
                  "population": {"value": 120, "year": 2020, "source": "A census"}}
        be.fill_same_polygons({"X": [first]}, {"X": [second]})
        self.assertEqual(first["population"]["value"], 120)
        self.assertEqual(be.control_population(first)["value"], 100)
        self.assertNotIn(be.RESTATED_FROM, second["population"])

    def test_burkina_fasos_lines_stand_after_centre_is_restated(self):
        # The regions' own figures, 20,485,695 for 2019, sit 12.8% under the
        # Factbook's 23,490,300 for 2025, outside the 11% their dates allow;
        # with Kadiogo's 3,510,028 for 2023 on Centre they come within it.
        def country():
            return {"id": "BFA", "name": "Burkina Faso",
                    "population": {"value": 23_490_300, "year": 2025, "source": FACTBOOK},
                    "ethnicity": [{"group": "Mossi", "pct": 53.7},
                                  {"group": "Fulani", "pct": 6.8}],
                    "language": [{"group": "Mossi", "pct": 52.9},
                                 {"group": "Fula", "pct": 7.8}]}

        def regions():
            centre, kadiogo = centre_and_kadiogo()
            centre.update(ethnicity=counted(Mossi=200, Gourounsi=30),
                          language=counted(Mooré=190, Dioula=40))
            west = unit("W", "West", "BFA",
                        population={"value": 8_727_478, "year": 2019, "source": "INSD 2019"},
                        ethnicity=counted(Mossi=253, Bobo=208),
                        language=counted(Mooré=243, Dioula=218))
            east = unit("E", "East", "BFA",
                        population={"value": 8_727_833, "year": 2019, "source": "INSD 2019"},
                        ethnicity=counted(Mossi=200, Gourmatche=300),
                        language=counted(Mooré=210, Gulmacema=290))
            a1 = {"BFA": [centre, west, east]}
            be.fill_sole_children(a1, {"BFA": [kadiogo]}, {"K": GOOD}, CODES)
            return a1

        nation, a1 = country(), regions()
        self.assertEqual(a1["BFA"][0]["population"]["value"], 3_510_028)
        quiet(be.roll_up_countries, [nation], a1)
        self.assertEqual(nation["ethnicity"][0], {"group": "Mossi", "pct": 53.7})
        self.assertEqual(nation["language"][0], {"group": "Mossi", "pct": 52.9})
        # Without the flag, as the pass once left it, the survey's sums win.
        nation, a1 = country(), regions()
        a1["BFA"][0]["population"].pop(be.RESTATED_FROM)
        quiet(be.roll_up_countries, [nation], a1)
        self.assertIn("count", nation["ethnicity"][0])


# --------------------------------------------------------------------------
# restated-parent-sources: the citation goes with the figure
# --------------------------------------------------------------------------

class RestatedParentsCiteTheirNewSource(unittest.TestCase):

    def test_centre_cites_ocha_alone_for_its_population(self):
        centre, kadiogo = centre_and_kadiogo()
        be.fill_sole_children({"BFA": [centre]}, {"BFA": [kadiogo]}, {"K": GOOD}, CODES)
        cites = [s for s in centre["sources"] if "population" in s["field"].split("/")]
        self.assertEqual(cites, [{"field": "population", "name": OCHA,
                                  "url": "https://data.humdata.org/dataset/cod-ps-bfa"}])
        # Kadiogo's own item is cited for nothing on Centre; the survey stays.
        self.assertFalse(any("Q1074530" in s.get("url", "") for s in centre["sources"]))
        self.assertIn(AFROBAROMETER, centre["sources"])

    def test_littoral_keeps_its_own_item_for_what_it_still_gives(self):
        parent = unit("P", "Littoral", "BEN",
                      population={"value": 678_874, "year": 2013, "source": "Wikidata (CC0)"})
        parent["sources"] = [{"field": "population/capital/coordinates", "name": "Wikidata",
                              "url": "https://www.wikidata.org/wiki/Q29158"}]
        child = unit("C", "Cotonou", "P",
                     population={"value": 665_209, "year": 2024,
                                 "source": "OCHA, Common Operational Dataset (cod-ps-ben)"})
        child["sources"] = [{"field": "population/capital/coordinates", "name": "Wikidata",
                             "url": "https://www.wikidata.org/wiki/Q43595"},
                            {"field": "population", "name": "OCHA",
                             "url": "https://data.humdata.org/dataset/cod-ps-ben"}]
        codes = {"BEN": {be.norm("Littoral"): ["Cotonou"]}}
        be.fill_sole_children({"BEN": [parent]}, {"BEN": [child]}, {"C": GOOD}, codes)
        self.assertEqual(parent["population"]["value"], 665_209)
        self.assertEqual(parent["sources"], [
            {"field": "capital/coordinates", "name": "Wikidata",
             "url": "https://www.wikidata.org/wiki/Q29158"},
            {"field": "population", "name": "OCHA",
             "url": "https://data.humdata.org/dataset/cod-ps-ben"}])

    def test_a_synced_island_cites_its_report_for_its_population_alone(self):
        # Crooked Island's median age and sex ratio are cited to other tables;
        # the island report comes for the population, beside its religion.
        report = {"name": "DoS 2010, island report: Crooked Island", "url": "dos.pdf"}
        parent = unit("P", "Crooked Island", "BHS",
                      population={"value": 323, "source": "Wikidata (CC0)"})
        parent["sources"] = [{"field": "population/capital/coordinates", "name": "Wikidata",
                              "url": "https://www.wikidata.org/wiki/Q1140993"},
                             {"field": "religion", **report},
                             {"field": "median_age/sex_ratio", "name": "USCB tables",
                              "url": "hdx"}]
        child = unit("C", "Crooked Island and Long Cay", "P",
                     population={"value": 330, "year": 2010, "source": report["name"]})
        child["sources"] = [{"field": "population/sex_ratio/median_age/religion/ethnicity",
                             **report}]
        be.fill_sole_children({"BHS": [parent]}, {"BHS": [child]}, {"C": GOOD}, {})
        self.assertEqual(parent["population"]["value"], 330)
        self.assertEqual(parent["sources"], [
            {"field": "capital/coordinates", "name": "Wikidata",
             "url": "https://www.wikidata.org/wiki/Q1140993"},
            {"field": "population/religion", **report},
            {"field": "median_age/sex_ratio", "name": "USCB tables", "url": "hdx"}])

    def test_a_division_takes_a_survey_entry_for_the_fields_it_took(self):
        # Cotonou keeps CLEAR Global's languages and takes Littoral's survey
        # for religion and ethnicity only, cited once, in the entry's order.
        parent = unit("P", "Littoral", "BEN", religion=[{"group": "A", "pct": 100.0}],
                      language=[{"group": "B", "pct": 100.0}],
                      ethnicity=[{"group": "C", "pct": 100.0}])
        parent["sources"] = [dict(AFROBAROMETER)]
        child = unit("C", "Cotonou", "P", language=[{"group": "Fon", "pct": 80.0}])
        child["sources"] = [{"field": "language", "name": "CLEAR Global", "url": "clear"}]
        codes = {"BEN": {be.norm("Littoral"): ["Cotonou"]}}
        be.fill_sole_children({"BEN": [parent]}, {"BEN": [child]}, {"C": GOOD}, codes)
        self.assertEqual(child["sources"], [
            {"field": "language", "name": "CLEAR Global", "url": "clear"},
            {**AFROBAROMETER, "field": "religion/ethnicity"}])

    def test_with_no_entry_naming_the_figures_source_each_citing_entry_comes(self):
        source = {"population": {"value": 16_620, "year": 2021,
                                 "source": "2021 census of Cape Verde, as a list gives it"},
                  "sources": [{"field": "population/capital/coordinates", "name": "Wikidata",
                               "url": "q1"},
                              {"field": "population", "name": "Wikipedia", "url": "w"}]}
        target = {"population": common.gap(NA), "sources": []}
        be.copy_field(source, target, "population")
        self.assertEqual(target["sources"], [
            {"field": "population", "name": "Wikidata", "url": "q1"},
            {"field": "population", "name": "Wikipedia", "url": "w"}])

    def test_names_source(self):
        self.assertTrue(be.names_source({"name": "Wikidata"}, {"source": "Wikidata (CC0)"}))
        self.assertTrue(be.names_source({"name": "Wikipedia"}, {"source": WIKIPEDIA}))
        self.assertTrue(be.names_source({"name": OCHA}, {"source": OCHA}))
        self.assertFalse(be.names_source({"name": "Wikidata"}, {"source": OCHA}))
        self.assertFalse(be.names_source({"name": "INE"}, {"source": "INEI, Censos 2017"}))
        self.assertFalse(be.names_source({"name": "Wikidata"}, [{"group": "A"}]))


# --------------------------------------------------------------------------
# esh-vat-gap-notes: a single unit's empty fields in the country's words
# --------------------------------------------------------------------------

class SingleUnitGapReasons(unittest.TestCase):

    def nation(self):
        return {"id": "ESH", "name": "Western Sahara",
                "median_age": {"value": 21.8, "unit": "years", "source": FACTBOOK},
                "language": [{"group": "Hassaniya Arabic", "pct": None, "pct_status": NA}],
                "religion": common.gap(NA, "Factbook reports free text only: Muslim"),
                "ethnicity": common.gap(NA, "Factbook reports free text only: Arab, Berber"),
                "sources": [{"field": "*", "name": "CIA World Factbook"}]}

    def test_western_saharas_religion_says_the_factbook_gives_only_words(self):
        first = unit("DIS020", "Western Sahara", "ESH",
                     population={"value": 565_581, "year": 2021})
        twin = unit("DIS020", "Western Sahara", "DIS020")
        done = be.inherit_single_unit([self.nation()], {"ESH": [first]}, {"ESH": [twin]})
        self.assertIn("ESH Western Sahara religion (the country's reason)", done)
        for record in (first, twin):
            note = record["religion"]["note"]
            self.assertEqual(record["religion"]["status"], NA)
            self.assertEqual(note, (
                "Western Sahara is drawn as a single first-level unit, so the country's own "
                "figures are this unit's. The country has no religion shares to give it: the "
                "CIA World Factbook gives only the words “Muslim”."))
            self.assertIn("“Arab, Berber”", record["ethnicity"]["note"])
            # The languages the Factbook names, with no shares, are a list.
            self.assertIn("so this is the country's own list: it describes exactly this "
                          "ground", record["language_note"])
            self.assertIn("own figure", record["median_age_note"])
            # The last pass that names a bare field's reason leaves it alone.
            be.say_why_empty({**record, "match": {"by": "name"}}, "Western Sahara", None)
        # Nor does the generic sentence ever name the Factbook as lacking it.
        probe = {**first, "match": {"by": "name"}}
        be.say_why_empty(probe, "Western Sahara", None)
        self.assertNotIn("carries language and not religion", probe["religion"]["note"])

    def test_a_country_note_of_another_kind_is_carried_in_its_own_words(self):
        why = be.country_gap_reason(
            {"name": "Antarctica",
             "religion": common.gap(NA, "No composition published by the Factbook for "
                                        "this entity.")}, "religion")
        self.assertTrue(why.endswith("to give it: no composition published by the Factbook "
                                     "for this entity."))
        self.assertIsNone(be.country_gap_reason({"religion": common.gap(NA)}, "religion"))

    def test_a_unit_given_nothing_and_a_stated_reason_are_left_alone(self):
        nation = self.nation()
        nation.pop("median_age")
        nation.pop("language")
        first = unit("DIS020", "Western Sahara", "ESH",
                     population={"value": 565_581, "year": 2021})
        self.assertEqual(be.inherit_single_unit([nation], {"ESH": [first]}), [])
        self.assertNotIn("note", first["religion"])
        first = unit("DIS020", "Western Sahara", "ESH",
                     religion=common.gap(NA, "A source's own reason."))
        be.inherit_single_unit([self.nation()], {"ESH": [first]})
        self.assertEqual(first["religion"]["note"], "A source's own reason.")


# --------------------------------------------------------------------------
# aneityum-note-sums: a made row's note adds up as shown
# --------------------------------------------------------------------------

class AneityumNoteAddsUp(unittest.TestCase):
    COUNTS = {"English": 28, "French": 6, "Bislama": 174, vc.VERNACULAR: 1052,
              "Not stated": 0}

    def test_the_made_rows_note_gives_its_parts_and_the_totals_apart(self):
        note = vc.completed_note({"total": 1261, "completed_from": "TAFEA",
                                  "completed_panels": 2, "counts": self.COUNTS})
        self.assertIn("not stated 0, 1,260 people in all.", note)
        self.assertIn("The table's totals, taken the same way, give 1,261", note)
        note = vc.completed_note({"total": 1260, "completed_from": "TAFEA",
                                  "completed_panels": 2, "counts": self.COUNTS})
        self.assertNotIn("totals, taken the same way", note)

    def test_the_shares_add_up_as_the_map_shows_them(self):
        people = {"total": 1400, "male": 700, "female": 700, "private": 1390}
        language = {"total": 1261, "completed_from": "TAFEA", "completed_panels": 2,
                    "counts": self.COUNTS}
        religion = ethnicity = {"total": 1390, "counts": {"A": 1390}}
        fields = vc.fields_for(people, [100] * len(vc.AGE_GROUPS), religion, ethnicity,
                               language, aged=1338)
        shown = [s["pct"] for s in fields["language"]]
        self.assertEqual(shown, [78.6, 13.0, 2.1, 0.4])
        note = fields["language_note"]
        self.assertIn("1,260 of the 1,338 people aged three and over", note)
        self.assertIn("the shares add up to 94.1% rather than 100%", note)
        self.assertNotIn("94.2", note)


# --------------------------------------------------------------------------
# policy-precedence-scale: the Swiss districts' own reason in plain words
# --------------------------------------------------------------------------

class SwissStraddledDistricts(unittest.TestCase):

    def test_one_commune(self):
        self.assertEqual(sn.straddled_note(["Lyss"]), (
            "No nationality figure is given for this district. The map draws it as it was "
            "in 2009, and today's commune of Lyss merged 2009 communes from inside and "
            "outside it; BFS publishes nationality by today's communes only and does not "
            "split a merged commune."))

    def test_several_communes(self):
        note = sn.straddled_note(["Kallnach", "Lyss", "Rapperswil (BE)"])
        self.assertIn("today's communes of Kallnach, Lyss and Rapperswil (BE) each merged",
                      note)
        self.assertNotIn("Not written", note)


if __name__ == "__main__":
    unittest.main()
