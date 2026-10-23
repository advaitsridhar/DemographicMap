"""The final sweep's fixes to the build's own tables, and the readers it shares.

Each class is one of the sweep's findings, put right where the build reads
its shapes, its rows or its seats: names cut or garbled in the boundary file,
places named for a unit they are not the largest of, seats outside their
outline, survey rows on another unit's ground, and the Factbook's misprints.
No network; the boundary files are read where the checkout has them.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_entities as be
from scripts import common

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
CURATED = ROOT / "data" / "curated" / "admin0_detail.json"
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_factbook  # noqa: E402


def loaded(filename, rows):
    """What load_adapters makes of ``rows`` as the file ``filename``."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, filename).write_text(json.dumps(rows))
        with mock.patch.object(be, "PROCESSED", Path(tmp)), \
                mock.patch.object(be, "ADAPTER_FILES", [filename]), \
                mock.patch.object(be, "log", lambda *a, **k: None):
            return be.load_adapters()


def processed(filename, row_id):
    for row in json.loads((PROCESSED / filename).read_text(encoding="utf-8")):
        if row.get("id") == row_id:
            return row
    raise AssertionError(f"{filename} has no row {row_id}")


def unit(uid, iso3, level="admin1", **fields):
    entity = {"id": uid, "country": iso3, "level": level, "name": uid,
              "capital": {"status": "not_available"},
              "largest_settlement": {"status": "not_available"}, "sources": []}
    entity.update(fields)
    return entity


class LabelsAsRead(unittest.TestCase):
    """Boundary labels cut, garbled, coded or doubled are put right where the
    shapes are read, and so is any record that copied one."""

    def test_seychelles_districts_take_their_whole_names(self):
        for cut, whole in (("Anse Boile", "Anse Boileau"), ("Baie Saint", "Baie Sainte Anne"),
                           ("La Digue a", "La Digue and Inner Islands"),
                           ("Pointe La", "Pointe Larue"), ("Roche Caïm", "Roche Caiman")):
            self.assertEqual(common.as_read(cut, "SYC", "ADM1"), whole)
        # English River's label arrives as mojibake, and is read before it is
        # respelt, under the name Wikidata's item also carries.
        self.assertEqual(common.as_read("La RiviÃ¨re", "SYC", "ADM1"),
                         "La Rivière Anglaise")

    def test_codes_and_abbreviations_become_names(self):
        for group, label, name in (("ETH", "KT", "Kembata Tembaro"),
                                   ("ETH", "Region 14", "Addis Ababa"),
                                   ("ETH", "Special Woreda", "Argoba Special Woreda"),
                                   ("ERI", "Maekel Deb.Keih Bahri", "Central Denkalia"),
                                   ("TZA", "Babati UrbanBabati Urban", "Babati Urban"),
                                   ("BDI", "Kanyosha1", "Kanyosha"),
                                   ("EGY", "Minya Governate", "Minya Governorate"),
                                   ("LSO", "Maseru (Berea Distict)", "Maseru (Berea District)")):
            self.assertEqual(common.as_read(label, group, "ADM2"), name, label)

    def test_two_north_shewas_stay_two(self):
        names = {common.as_read(f"North Shewa(R{n})", "ETH", "ADM2") for n in (3, 4)}
        self.assertEqual(names, {"North Shewa (Amhara)", "North Shewa (Oromia)"})

    def test_a_correction_for_one_level_is_made_only_there(self):
        # Tharaka-Nithi county is cut to "Tharaka"; Tharaka constituency, a
        # level down, is rightly called so.
        self.assertEqual(common.as_read("Tharaka", "KEN", "ADM1"), "Tharaka-Nithi")
        self.assertEqual(common.as_read("Tharaka", "KEN", "admin1"), "Tharaka-Nithi")
        self.assertEqual(common.as_read("Tharaka", "KEN", "ADM2"), "Tharaka")
        for (group, _level, wrong), right in common.MISSPELLED_AT.items():
            self.assertNotEqual(be.norm(wrong), be.norm(right))
            self.assertNotIn((group, wrong), common.ALSO_KNOWN_AS)
            self.assertNotIn((group, wrong), common.MISSPELLED)

    def test_spacing_and_direction_marks_go_and_joiners_stay(self):
        self.assertEqual(common.as_read("Kigoma  Urban", "TZA"), "Kigoma Urban")
        self.assertEqual(common.as_read("Bordj Bou Arreridj‎", "DZA"), "Bordj Bou Arreridj")
        self.assertEqual(common.as_read("‫عقارب‬", "TUN"), "عقارب")
        # The zero-width non-joiner and joiner spell Persian and Indic words.
        self.assertEqual(common.tidy("می‌خواهم"), "می‌خواهم")
        self.assertEqual(common.tidy("a‍b"), "a‍b")

    def test_a_stray_apostrophe_goes_though_no_join_needs_it(self):
        # norm() drops it, so MISSPELLED, whose entries must each change a
        # join, cannot take Lesotho's "'Maoa-Mafubelu"; the label showed it.
        self.assertEqual(common.as_read("'Maoa-Mafubelu", "LSO", "ADM2"), "Maoa-Mafubelu")
        for (group, wrong), right in common.MISPRINTED.items():
            self.assertEqual(be.norm(wrong), be.norm(right))
            self.assertNotIn((group, wrong), common.MISSPELLED)

    def test_no_correction_makes_two_units_of_one_name(self):
        try:
            import fiona
        except ImportError:
            self.skipTest("fiona is not installed")
        groups = sorted({g for g, _ in common.MISSPELLED} | {g for g, _ in common.MISPRINTED}
                        | {g for g, _, _ in common.MISSPELLED_AT})
        quoted = ", ".join(f"'{g}'" for g in groups)
        for level in ("ADM1", "ADM2"):
            path = be.BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg"
            if not path.exists():
                self.skipTest("the boundary files are not in this checkout")
            drawn, corrected = {}, set()
            with fiona.open(path) as src:
                for feat in src.filter(where=f"shapeGroup IN ({quoted})"):
                    props = feat["properties"]
                    name = common.as_read(props["shapeName"], props["shapeGroup"], level)
                    key = (props["shapeGroup"], name)
                    drawn[key] = drawn.get(key, 0) + 1
                    if name != common.tidy(common.repair(props["shapeName"] or "")):
                        corrected.add(key)
            self.assertTrue(corrected, level)
            for key in corrected:
                self.assertEqual(drawn[key], 1, f"{level} {key} drawn twice")

    def test_aliases_that_named_the_old_labels_name_the_new(self):
        aliases = be.ROW_ALIASES
        self.assertEqual(aliases["cod_ps_admin2.json"]["TZA-CODPS-TZ2106"], ("Babati Urban",))
        self.assertEqual(aliases["cod_ps_age.json"]["TZA-CODPSAGE-TZ2106"], ("Babati Urban",))
        self.assertEqual(aliases["cod_ps_admin2.json"]["BDI-CODPS-BDI002006"], ("Mugongomanga",))
        self.assertEqual(aliases["cod_ps_age.json"]["BDI-CODPSAGE-BDI016006"], ("Nyabitsinda",))
        self.assertEqual(aliases["cod_ps_admin2.json"]["ERI-CODPS-ER103"], ("Southern Denkalia",))
        self.assertEqual(aliases["afrobarometer_r56.json"]["EGY-AB5-Minya Governate"],
                         ("Minya Governorate",))
        old = {"Nyanrusang", "Nyabitsind", "Mugongoman", "Beneshangul Gumu",
               "Babati UrbanBabati Urban", "Kigoma  Urban", "Masasi  Township Authority"}
        for file, rows in aliases.items():
            for row, names in rows.items():
                self.assertFalse(old & set(names), (file, row))


class GeoNamesPlaces(unittest.TestCase):
    """Largest settlements: a district's figure on a town, a town filed under
    a council of its own, and places that stand outside the outline."""

    def setUp(self):
        if not (be.GEONAMES_SETTLEMENTS.exists() and (ROOT / "data/raw/geonames/places.tsv.gz").exists()):
            self.skipTest("GeoNames' files are not in this checkout")

    def fill(self, admin1=None, admin2=None):
        with mock.patch.object(be, "log", lambda *a, **k: None):
            be.fill_settlements_from_geonames(admin1 or {}, admin2 or {}, {})

    def test_a_district_figure_gives_way_to_the_largest_town(self):
        upper_west = unit("69750345B48673213774244", "GHA")
        winejok = unit("48771326B49579010016854", "SSD")
        self.fill({"GHA": [upper_west], "SSD": [winejok]})
        self.assertEqual(upper_west["largest_settlement"], "Wa")
        self.assertEqual(upper_west["largest_settlement_population"]["value"], 78_107)
        self.assertEqual(winejok["largest_settlement"], "Aweil")

    def test_a_level_down_the_town_is_named_without_the_district_s_figure(self):
        jirapa = unit("2480657B21686152565613", "GHA", "admin2")
        self.fill(admin2={"GHA": [jirapa]})
        self.assertEqual(jirapa["largest_settlement"], "Jirapa")
        self.assertNotIn("largest_settlement_population", jirapa)

    def test_botswana_s_towns_are_their_districts(self):
        north_east = unit("57670837B74109899498700", "BWA")
        south_east = unit("57670837B20379019036464", "BWA")
        self.fill({"BWA": [north_east, south_east]})
        self.assertEqual((north_east["largest_settlement"], south_east["largest_settlement"]),
                         ("Francistown", "Gaborone"))

    def test_a_seat_held_twice_does_not_hide_the_largest_town(self):
        joe_gqabi = unit("47623444B23123045321242", "ZAF", "admin2")
        self.fill(admin2={"ZAF": [joe_gqabi]})
        self.assertEqual(joe_gqabi["largest_settlement"], "Aliwal North")

    def test_places_outside_the_outline_are_not_its_own(self):
        tripoli = unit("10800210B53685260454781", "LBY")
        perseverance = unit("4304713B87843643892528", "SYC")
        north_east_gonja = unit("2480657B30922977157044", "GHA", "admin2")
        zimam = unit("37247803B81980397210132", "EGY", "admin2", name="Zemam Out")
        self.fill({"LBY": [tripoli], "SYC": [perseverance]},
                  {"GHA": [north_east_gonja], "EGY": [zimam]})
        self.assertIn("Tripoli and Tajura stand on a strip of coast",
                      tripoli["largest_settlement"]["note"])
        self.assertIn("Ile Perseverance", perseverance["largest_settlement"]["note"])
        self.assertIn("seat of East Gonja Municipal", north_east_gonja["largest_settlement"]["note"])
        self.assertIn("6th of October City, is counted by the census in a division of its own",
                      zimam["largest_settlement"]["note"])

    def test_natural_earth_s_smaller_places_are_declared(self):
        passed = be.NATURAL_EARTH_PASSED_OVER
        for key in (("SSD", "Central Equatoria", "Yei"), ("MAR", "Oriental", "Taza"),
                    ("LBY", "Al Jabal al Akhdar", "Shahhat"), ("NAM", "Kunene", "Outjo"),
                    ("SWZ", "Shiselweni", "Golela")):
            self.assertIn(key, passed)
        self.assertEqual(be.NATURAL_EARTH_MISFILED[("LBY", "Tajura' wa an Nawahi al Arba",
                                                    "Tripoli")],
                         "the strip of coast no first-level outline covers")


class UnsizedSeats(unittest.TestCase):
    """GeoNames' "its seat X" is said only beside the capital X."""

    def test_the_reason_is_read_against_the_capital_finally_shown(self):
        none = "No GeoNames place is named: its seat Egito Praia has no population in GeoNames."
        lobito = unit("x", "AGO", "admin2", capital="Lobito",
                      largest_settlement={"status": "not_available", "note": none})
        caue = unit("y", "STP", "admin2", capital="Caué",
                    largest_settlement={"status": "not_available", "note": (
                        "No GeoNames place is named: its seat Caué has no population in "
                        "GeoNames.")})
        self.assertEqual(be.say_unsized_seats({"AGO": [lobito]}, {"STP": [caue]}), 1)
        self.assertEqual(lobito["largest_settlement"]["note"], (
            "No GeoNames place is named: GeoNames gives no population for Egito Praia, the "
            "seat of a division it places in this unit, so which place is the largest "
            "cannot be told."))
        self.assertIn("its seat Caué", caue["largest_settlement"]["note"])


class Seats(unittest.TestCase):
    def test_declared_seats_fill_and_cite_their_source(self):
        brak = unit("10800210B20515568933500", "LBY")
        kufra = unit("10800210B89898169718474", "LBY", "admin2")
        analamanga = unit("27540722B10144800929043", "MDG")
        joe_gqabi = unit("47623444B23123045321242", "ZAF", "admin2")
        be.fill_capitals_from_geonames({"LBY": [brak], "MDG": [analamanga]},
                                       {"LBY": [kufra], "ZAF": [joe_gqabi]})
        self.assertEqual(brak["capital"], "Brak")
        self.assertEqual(brak["sources"][-1]["url"], "https://www.wikidata.org/wiki/Q48232")
        self.assertEqual(kufra["capital"], "Al Jawf")
        self.assertEqual(kufra["sources"][-1]["name"], "Wikidata")
        self.assertEqual(analamanga["capital"], "Antananarivo")
        self.assertEqual(analamanga["sources"][-1]["name"], "GeoNames")
        self.assertEqual(joe_gqabi["capital"], "Barkly East")

    def test_a_seat_outside_the_outline_is_said_to_be(self):
        tripoli = unit("10800210B53685260454781", "LBY", "admin2")
        laayoune = unit("70788906B89532291078161", "MAR")
        self.assertTrue(be.say_why_no_capital(tripoli, "LBY"))
        self.assertTrue(be.say_why_no_capital(laayoune, "MAR"))
        self.assertIn("Tripoli, stands on a strip of coast", tripoli["capital"]["note"])
        self.assertIn("south of 27°40'N", laayoune["capital"]["note"])

    def test_second_level_seats_say_what_is_known(self):
        for iso3 in ("MAR", "SDN", "SSD", "DZA", "EGY"):
            entity = unit("z", iso3, "admin2")
            self.assertTrue(be.say_why_no_capital(entity, iso3))
            self.assertNotEqual(entity["capital"]["note"], be.NO_SEAT_NAMED, iso3)
        self.assertNotIn("part of a town", be.NO_SEAT_REASONS[("EGY", "admin2")])

    def test_wrong_seats_leave_their_rows_and_labels_lose_their_glosses(self):
        rows = [{"id": "ZMB-WD-Q738382", "country": "ZMB", "name": "Southern Province",
                 "level": "admin1", "capital": "Livingstone",
                 "sources": [{"field": "population/capital/coordinates", "name": "Wikidata"}]},
                {"id": "ZMB-WD-Q823810", "country": "ZMB", "name": "Eastern Province",
                 "level": "admin1", "capital": "Chipata (Fort Jameson)"}]
        got = {r["id"]: r for r in loaded("wikidata_admin1.json", rows)["ZMB"]}
        self.assertNotIn("capital", got["ZMB-WD-Q738382"])
        self.assertEqual(got["ZMB-WD-Q738382"]["sources"][0]["field"], "population/coordinates")
        self.assertEqual(got["ZMB-WD-Q823810"]["capital"], "Chipata")
        for row_id in ("NAM-WD-Q876512", "MUS-WD-Q934126", "MAR-WD-Q19951088"):
            self.assertEqual(set(be.WITHDRAWN_FIELDS["wikidata_admin1.json"][row_id]),
                             {"capital"})
        self.assertEqual(be.DISAMBIGUATED["wikidata_admin2.json"]["NGA-WD-Q4701091"],
                         {"capital": "Moniya"})

    def test_an_item_with_no_capital_is_not_cited_for_one(self):
        rows = [{"id": "LBY-WD-Q172114", "country": "LBY", "name": "Kufra", "level": "admin2",
                 "capital": {"status": "not_available"},
                 "sources": [{"field": "population/capital/coordinates", "name": "Wikidata"}]}]
        got = loaded("wikidata_admin2.json", rows)["LBY"][0]
        self.assertEqual(got["sources"][0]["field"], "population/coordinates")


class Citations(unittest.TestCase):
    WIKIDATA = {"field": "population/capital/coordinates", "name": "Wikidata",
                "url": "https://www.wikidata.org/wiki/Q1"}

    def test_wikidata_is_not_cited_for_a_capital_or_population_shown_as_a_gap(self):
        entity = {"capital": {"status": "not_available", "note": be.NO_SEAT_NAMED},
                  "population": {"value": 5, "year": 2020, "source": "Wikidata (CC0)"},
                  "sources": [dict(self.WIKIDATA)]}
        be.tidy_citations(entity)
        self.assertEqual(entity["sources"][0]["field"], "population/coordinates")

    def test_a_note_that_names_the_item_keeps_it(self):
        entity = {"population": {"status": "not_available", "note": (
                      "Wikidata's item of this name is a town; its 7,739 are the town's.")},
                  "sources": [dict(self.WIKIDATA)]}
        be.tidy_citations(entity)
        self.assertEqual(entity["sources"][0]["field"], "population/capital/coordinates")


class RowNotes(unittest.TestCase):
    def test_kolwezi_still_has_no_date_and_its_note_says_so(self):
        row = processed("wikidata_admin2.json", "COD-WD-Q271404")
        self.assertNotIn("year", row["population"])
        got = loaded("wikidata_admin2.json", [row])["COD"][0]
        self.assertTrue(got["population_note"].startswith(
            "Wikidata gives this figure without a date."))
        self.assertIn("Mutshatsha territory", got["population_note"])
        cited = [s for s in got["sources"] if s["field"] == "population note"]
        self.assertEqual(cited[0]["url"], "https://data.humdata.org/dataset/cod-ps-cod")

    def test_red_sea_state_says_why_its_localities_make_no_figure(self):
        row = processed("wikidata_admin1.json", "SDN-WD-Q310120")
        got = loaded("wikidata_admin1.json", [row])["SDN"][0]
        self.assertIn("1,878,562", got["population_note"])
        self.assertIn("22nd parallel", got["population_note"])

    def test_east_gonja_s_seat_says_where_it_stands(self):
        row = processed("ghana_capitals.json", "GHA-SEAT-2480657B20562210440652")
        got = loaded("ghana_capitals.json", [row])["GHA"][0]
        self.assertIn("inside the one drawn as North East Gonja", got["capital_note"])

    def test_malawi_s_districts_with_their_city_say_why_no_shares(self):
        mzimba = {"id": "MWI-CG-MW105", "country": "MWI", "name": "Mzimba", "level": "admin2",
                  "language": [{"group": "Chitumbuka", "pct": 91.6}],
                  "sources": [{"field": "language", "name": "CLEAR Global"}]}
        self.assertNotIn("language", loaded("clear_global_language.json", [mzimba])["MWI"][0])
        census = processed("malawi_census.json", "MWI-2018-blantyre")
        got = loaded("malawi_census.json", [census])["MWI"][0]
        self.assertIn("Blantyre district and Blantyre City separately",
                      got["language"]["note"])
        self.assertIn("language note", [s["field"] for s in got["sources"]])


class Unions(unittest.TestCase):
    def test_botswana_s_districts_take_their_towns_ages(self):
        parts = [processed("cod_ps_age.json", rid)
                 for rid in ("BWA-CODPSAGE-BW13", "BWA-CODPSAGE-BW02")]
        pooled = be.pool_rows("North-East District", parts, "BWA", "cod_ps_age.json")
        self.assertEqual(pooled["median_age"]["value"], 26.4)
        spec = be.ROW_UNIONS[("BWA", "North-East District")]
        self.assertEqual(spec["shapes"], (("admin1", "57670837B74109899498700"),))
        for key in (("BWA", "South-East District"), ("BWA", "Central District"),
                    ("BWA", "Southern District"), ("MDG", "Vatovavy-Fitovinany")):
            self.assertIn(key, be.ROW_UNIONS)
        self.assertEqual(be.ROW_UNIONS[("MDG", "Vatovavy-Fitovinany")]["weigh"], "respondents")

    def test_a_pool_does_not_take_one_part_s_size_for_its_own(self):
        # Vatovavy and Fitovinany have 32 respondents each: the notes agree
        # word for word, and the pool of 64 kept "This region: 32 respondents".
        note = ("Afrobarometer Round 9. Regional shares are survey estimates. This region: "
                "32 respondents. Fewer than 50 respondents, so this share is imprecise and "
                "should be read as indicative.")
        self.assertEqual(be.shared_sentences([note, note]),
                         "Afrobarometer Round 9. Regional shares are survey estimates. ")
        self.assertEqual(be.shared_sentences(["The 2019 census's count."] * 2),
                         "The 2019 census's count. ")


class OutlineMixtures(unittest.TestCase):
    def test_a_mixture_keeps_no_other_ground_s_notes_or_citations(self):
        outline = {"kind": "mixed", "label": "Endola", "parts": ["Endola", "Omulonga"],
                   "shares": [["Endola", 0.6, 0.95], ["Omulonga", 0.4, 0.3]]}
        entity = {"id": "a", "country": "NAM", "outline": outline,
                  "language": [{"group": "Oshiwambo", "pct": 100.0}],
                  "language_note": "The main language spoken in the household.",
                  "median_age_note": "Interpolated from OCHA's age groups.",
                  "sources": [{"field": "language", "name": "CLEAR Global"},
                              {"field": "population/median_age/sex_ratio", "name": "OCHA"},
                              {"field": "median_age note", "name": "OCHA"},
                              {"field": "capital/coordinates", "name": "Wikidata"}]}
        self.assertEqual(be.settle_outline_mixtures({"NAM": [entity]}), 1)
        self.assertNotIn("language_note", entity)
        self.assertNotIn("median_age_note", entity)
        self.assertEqual(entity["sources"], [{"field": "coordinates", "name": "Wikidata"}])
        self.assertIn("not any one constituency", entity["language"]["note"])


class Parents(unittest.TestCase):
    def test_divisions_are_filed_where_they_are_counted(self):
        for shape, parent in (("37247803B30511282692114", ("EGY", "Monufia Governorate")),
                              ("37247803B91562573257971", ("EGY", "Port Said Governorate")),
                              ("37247803B61040397145628", ("EGY", "Port Said Governorate")),
                              ("11933810B93469460723803", ("TUN", "Mahdia"))):
            self.assertEqual(be.DECLARED_PARENTS[shape], parent)


class SumsSayWhatTheyAdd(unittest.TestCase):
    def test_a_survey_s_counts_are_its_respondents(self):
        self.assertEqual(be.counted_noun(None, surveyed=True), "survey respondents")
        self.assertEqual(be.counted_noun("households, by main language"), "households")
        self.assertEqual(be.counted_noun(None), "people")
        surveyed = {"language_note": "Afrobarometer Round 9 ... This region: 69 respondents."}
        tabulated = {"language_note": "Tabulated by CLEAR Global from Kenya Round 9 data "
                                      "(2023) (AfroBarometer)."}
        counted = {"language_note": "The 2019 census's count."}
        self.assertTrue(be.survey_shares(surveyed, "language"))
        self.assertTrue(be.survey_shares(tabulated, "language"))
        self.assertFalse(be.survey_shares(counted, "language"))

    def test_survey_sums_do_not_stand_for_these_countries(self):
        for key in (("NAM", "religion"), ("NAM", "language"), ("NAM", "ethnicity"),
                    ("ZWE", "ethnicity"), ("MUS", "ethnicity")):
            self.assertIn("Afrobarometer", be.COUNTRY_NOT_SUMMED[key])
        self.assertNotIn(("ZWE", "religion"), be.COUNTRY_NOT_SUMMED)

    def test_the_reason_follows_a_finished_sentence(self):
        # Mauritius's ethnicity is the Factbook's words with no full stop, and
        # the reason ran on from "Franco-Mauritian".
        words = ("Factbook reports free text only: Indo-Mauritian (compose approximately "
                 "two thirds of the total population), Creole, Sino-Mauritian, Franco-Mauritian")
        admin0 = [{"id": "MUS", "ethnicity": {"status": "not_available", "note": words}},
                  {"id": "ZWE", "ethnicity": [{"group": "African", "pct": 99.6}],
                   "ethnicity_note": "A sentence."}]
        be.note_country_not_summed(admin0)
        note = admin0[0]["ethnicity"]["note"]
        self.assertTrue(note.startswith("The CIA World Factbook gives only the words "
                                        "“Indo-Mauritian"), note)
        self.assertIn("Franco-Mauritian”. Its first-level divisions are not added up", note)
        self.assertEqual(be.plain_wording(note), note)
        self.assertTrue(admin0[1]["ethnicity_note"].startswith(
            "A sentence. Its first-level divisions"))
        self.assertEqual(be.ended("A list cut short..."), "A list cut short...")
        self.assertEqual(be.ended(""), "")


class BareFields(unittest.TestCase):
    """Libya's Tripoli, matched only by the census's reason it can give no
    count, read "None of the sources used for this unit (an unnamed source)"."""

    joined = {"sources": "Bureau of Statistics and Census Libya and Wikidata",
              "matched": 22, "units": 22, "fields": {"religion": {"n": 0, "sources": []}}}

    def test_a_unit_whose_rows_cite_nothing_takes_the_level_s_sentence(self):
        entity = unit("T", "XYZ", match="adapter:shape_id", religion={"status": "not_available"})
        be.say_why_empty(entity, "Libya", self.joined)
        note = entity["religion"]["note"]
        self.assertNotIn("unnamed", note)
        self.assertTrue(note.startswith("None of the sources used for the units of Libya at "
                                        "this level (Bureau of Statistics"), note)

    def test_a_unit_whose_sources_are_named_still_names_them(self):
        entity = unit("T", "XYZ", match="adapter:shape_id", religion={"status": "not_available"},
                      sources=[{"field": "population", "name": "Wikidata"}])
        be.say_why_empty(entity, "Libya", self.joined)
        self.assertTrue(entity["religion"]["note"].startswith(
            "None of the sources used for this unit (Wikidata)"), entity["religion"]["note"])


class CountryRows(unittest.TestCase):
    rows = json.loads(CURATED.read_text(encoding="utf-8"))["rows"]

    def row(self, country, field):
        hits = [r for r in self.rows if r["country"] == country and r["field"] == field]
        self.assertEqual(len(hits), 1, (country, field))
        return hits[0]

    def test_comoros_shows_the_census_s_national_columns(self):
        ethnicity = self.row("COM", "ethnicity")
        self.assertEqual(sum(g["count"] for g in ethnicity["groups"]), 758_316)
        self.assertEqual(ethnicity["basis"], "nationality")
        language = self.row("COM", "language")
        self.assertNotIn("groups", language)
        self.assertIn("677,246", language["note"])

    def test_zimbabwe_and_namibia_are_checked_against_their_censuses(self):
        self.assertEqual((self.row("ZWE", "population")["value"],
                          self.row("NAM", "population")["value"]), (15_178_957, 3_022_401))
        for country in ("ZWE", "NAM"):
            self.assertEqual(self.row(country, "population")["use"], "check")


class FactbookText(unittest.TestCase):
    """The Factbook's misprints, put right before its text is parsed."""

    def profile(self, religions, ethnic):
        return {"Government": {"Country name": {"conventional short form": {"text": "X"}}},
                "People and Society": {"Religions": {"text": religions},
                                       "Ethnic groups": {"text": ethnic}}}

    def test_cameroon_s_and_the_drc_s_shares_are_read_whole(self):
        cmr = fetch_factbook.build_record("africa", "cm", self.profile(
            "Roman Catholic 33.1%, Muslim 30.6%, Protestant 27.1% other Christian 6.1%, "
            "animist 1.3%, other 0.7%, none 1.2% (2022 est.)",
            "Bamileke-Bamu 22.2%, Beti/Bassa, Mbam 13.1%, Grassfields 9.9%, "
            "Adamawa-Ubangi, 9.8%, other 54.9% (2022 est.)"), "CMR", "CM")
        ethnic = {g["group"]: g["pct"] for g in cmr["ethnicity"]}
        self.assertEqual((ethnic["Beti/Bassa/Mbam"], ethnic["Adamawa-Ubangi"]), (13.1, 9.8))
        self.assertEqual({g["group"]: g["pct"] for g in cmr["religion"]}["other Christian"], 6.1)
        cod = fetch_factbook.build_record("africa", "cg", self.profile(
            "Christian 93/1% (Roman Catholic 29.9%, Protestant 26.7%, other Christian 36.5%), "
            "Kimbanguist 2.8% (2014 est.)", "Mongo, Luba, Kongo"), "COD", "CD")
        self.assertEqual(cod["religion"][0], {"group": "Christian", "pct": 93.1})

    def test_a_misprint_put_right_upstream_stops_the_run(self):
        with self.assertRaises(SystemExit):
            fetch_factbook.corrected("COD", "religion", "Christian 93.1% (2014 est.)")
        self.assertEqual(fetch_factbook.corrected("KEN", "religion", "Christian 85%"),
                         "Christian 85%")

    def test_the_source_named_beside_a_figure_is_the_factbook(self):
        record = fetch_factbook.build_record("africa", "xx", self.profile("x", "y"), "XYZ", "XY")
        self.assertNotIn("mirror", json.dumps(record["population"]))
        self.assertEqual(record["sources"][0]["retrieved_via"], "factbook/factbook.json mirror")

    def test_a_run_closed_by_or_or_including_keeps_its_whole_name(self):
        bw = common.parse_composition("Tswana (or Setswana) 79%, Kalanga 11%, Basarwa 3%, "
                                      "other, including Kgalagadi and people of European "
                                      "ancestry 7%")
        self.assertEqual(bw[-1], {"group": "other, including Kgalagadi and people of "
                                           "European ancestry", "pct": 7.0})
        za = common.parse_composition("Christian 86%, ancestral, tribal, animist, or other "
                                      "traditional African religions 5.4%, Muslim 1.9%")
        self.assertEqual(za[1]["group"], "ancestral, tribal, animist, or other traditional "
                                         "African religions")


class ReligionChip(unittest.TestCase):
    """Libya's religions under 1% are bounds, not answers that overlap."""

    SCRIPT = r"""
const fs = require("fs"); const vm = require("vm"); const path = require("path");
const root = process.argv[1];
const src = (n) => fs.readFileSync(path.join(root, "site", "js", n), "utf8");
const ctx = vm.createContext({
  window: { matchMedia: () => ({ matches: false }) }, console,
  document: { documentElement: { getAttribute: () => "light" } } });
vm.runInContext(src("data.js"), ctx); vm.runInContext(src("palette.js"), ctx);
ctx.window.DataStore = { country: () => null, get: () => null, children: () => [] };
vm.runInContext(src("dashboard.js"), ctx);
let html = "";
const box = { set innerHTML(h) { html = h; }, get innerHTML() { return html; },
              scrollTop: 0, querySelectorAll: () => [] };
const lt = (group) => ({ group, pct: 1.0, bound: "<" });
ctx.window.Dashboard.render({ id: "LBY", level: "admin0", name: "Libya", country: "LBY",
  religion: [{ group: "Muslim", pct: 96.6 }, { group: "Christian", pct: 2.7 },
             lt("Buddhist"), lt("Hindu"), lt("Jewish"), lt("folk religion"), lt("other"),
             lt("unaffiliated")] }, box);
const libya = html.includes("more than one answer allowed");
ctx.window.Dashboard.render({ id: "CHE", level: "admin0", name: "X", country: "CHE",
  language: [{ group: "German", pct: 62 }, { group: "French", pct: 23 },
             { group: "English", pct: 23 }] }, box);
console.log(JSON.stringify({ libya, multi: html.includes("more than one answer allowed") }));
"""

    def test_bounds_do_not_read_as_more_than_one_answer(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        out = subprocess.run([node, "-e", self.SCRIPT, str(ROOT)], capture_output=True,
                             text=True, check=True).stdout
        self.assertEqual(json.loads(out), {"libya": False, "multi": True})


if __name__ == "__main__":
    unittest.main()
