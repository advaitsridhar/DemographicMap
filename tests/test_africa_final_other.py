"""The Africa round's final sweep, the national readers outside North Africa.

Names as the census or a sentence writes them (Somalia's districts, Gabon's
departments, Seychelles' districts cut at ten characters); source names that
name a publisher, not a web address; a reason written beside the figure
another source gives (Liberia's 55 districts), or that says itself why a unit
has no composition (Eritrea); and the men and women counted beside a sex ratio
far from the country's. No network.
"""

import json
import sys
import types
import unittest
from unittest import mock

from scripts import build_entities as be
from scripts.fetch_census import cited_sources as cs
from scripts.fetch_census import congo_census as cg
from scripts.fetch_census import djibouti_census as dj
from scripts.fetch_census import eritrea_census as er
from scripts.fetch_census import ethiopia_census as et
from scripts.fetch_census import gabon_census as gc
from scripts.fetch_census import liberia_census as lb
from scripts.fetch_census import mauritania_census as mc
from scripts.fetch_census import namibia_census as nm
from scripts.fetch_census import nigeria_census as ng
from scripts.fetch_census import seychelles_census as sc
from scripts.fetch_census import somalia_survey as ss

import common  # noqa: E402  (on the path once the readers are imported)


def quiet(*_args, **_kwargs):
    return None


class SomaliaDistricts(unittest.TestCase):
    def test_a_district_is_named_as_a_sentence_writes_it(self):
        rows = ss.districts([{"id": "a", "name": "BENDER BAYLA"}, {"id": "b", "name": " EYL "},
                             {"id": "c", "name": "Galkayu North"}])
        self.assertEqual([r["name"] for r in rows], ["Bender Bayla", "Eyl", "Galkayu North"])
        # Bound by id, so the record names its polygon and the build keeps the
        # capitals as an alias.
        self.assertEqual([(r["match_by"], r["shape_id"]) for r in rows],
                         [("shape_id", "a"), ("shape_id", "b"), ("shape_id", "c")])


class SourceNames(unittest.TestCase):
    """A source's name names its publisher; the web address is the url's."""

    def test_somalia_s_regions_name_city_population_and_say_what_the_figure_is(self):
        from tests.test_cited_sources import SOMALIA, page
        drawn = {shape: f"id-{shape}" for shape in cs.SOMALIA.values()}
        with mock.patch.object(cs, "http_get", return_value=page(SOMALIA)), \
                mock.patch.object(cs, "log", quiet):
            rows = {r["name"]: r for r in cs.somalia(drawn)}
        bay = rows["Bay"]
        self.assertEqual(bay["population"]["value"], 1_035_900)
        self.assertEqual(bay["population"]["source"],
                         "OCHA Somalia, 2019 calculation, as City Population tabulates it")
        self.assertEqual(bay["population"]["note"],
                         "An estimate, not a count: OCHA Somalia's Information Management "
                         "Working Group's calculation for 1 January 2019, for the eighteen "
                         "pre-war regions, as City Population tabulates it.")
        cited = bay["sources"][0]
        self.assertEqual(cited["name"], "City Population (Thomas Brinkhoff), after OCHA Somalia")
        self.assertEqual(cited["url"], cs.SOMALIA_URL)
        for text in (bay["population"]["source"], bay["population"]["note"], cited["name"]):
            self.assertNotIn("citypopulation", text.lower())
        # Nor how the table came to be read.
        self.assertNotIn("Wikipedia", bay["population"]["note"])

    def test_djibouti_s_and_the_congo_s_censuses_name_the_tabulator(self):
        for source in (dj.SOURCE, cg.SOURCE):
            self.assertNotIn("citypopulation", source.lower())
            self.assertIn("as City Population (Thomas Brinkhoff) tabulates", source)
        table = {"regions": {"obock": {"name": "Obock", "total": 100, "parts": 100, "men": 52,
                                       "women": 48, "page": dj.URL + "4__obock/"}}}
        obock = dj.build(table, [{"id": "o", "name": "Obock"}], [])[0]
        self.assertEqual(obock["population"]["source"], dj.SOURCE)
        self.assertEqual({s["name"] for s in obock["sources"]}, {dj.SOURCE})

    def test_a_transcript_s_citation_names_no_folder(self):
        # The citation's note is printed under the source in the panel. The PDF
        # reader is never reached: the archive refuses first.
        import probe_pdf
        with mock.patch.dict(sys.modules, {"pypdf": types.SimpleNamespace(PdfReader=None)}), \
                mock.patch.object(probe_pdf, "fetch_blob", side_effect=OSError("refused")), \
                mock.patch.object(cs.time, "sleep", quiet), mock.patch.object(cs, "log", quiet):
            text, via = cs.archived_text(cs.NBS_ARCHIVED, cs.TRANSCRIPT, "23 September 2026")
        self.assertIn("Table 10", text)
        self.assertEqual(via, f"a transcript of the Internet Archive's copy, {cs.NBS_ARCHIVED}, "
                              "made on 23 September 2026")


class EritreaCompositions(unittest.TestCase):
    def test_each_says_there_has_never_been_a_census(self):
        units = {"admin1": [{"id": "r", "name": "Anseba Region"}],
                 "admin2": [{"id": "s", "name": "Hamelmalo"}]}
        records = er.build(units)
        for r in records:
            for field in ("religion", "language", "ethnicity"):
                note = r[field]["note"]
                self.assertTrue(note.startswith("Eritrea has never taken a national census"))
                self.assertTrue(note.endswith(f"gives its {field}."), note)
                self.assertNotIn("whether the census asks", note)
        # The build's general sentence leaves a stated reason as it is.
        entity = json.loads(json.dumps(records[0]))
        be.say_why_empty(entity, "Eritrea")
        self.assertEqual(entity["language"], records[0]["language"])


class GabonDepartments(unittest.TestCase):
    TABLE = {"provinces": {"OGOOUE-IVINDO": (2_000, 1_200, 3_200)},
             "departments": {"OGOOUE-IVINDO": {"Lopé": (1_000, 600, 1_600),
                                               "Zadié": (1_000, 600, 1_600)}}}
    ADMIN1 = [{"id": "P", "name": "Ogooué-Ivindo", "parent": "GAB", "point": [12.0, 0.0]}]
    ADMIN2 = [{"id": "L", "name": "Lopè", "parent": "P", "point": [11.5, -0.5]},
              {"id": "Z", "name": "Zadiè", "parent": "P", "point": [13.0, 0.5]}]

    def test_a_department_takes_the_census_s_spelling(self):
        records, _ = gc.build(self.TABLE, self.ADMIN1, self.ADMIN2)
        by = {r["shape_id"]: r["name"] for r in records}
        self.assertEqual((by["L"], by["Z"]), ("Lopé", "Zadié"))
        # After a rebuild has renamed them, read as drawn, the same polygons bind.
        renamed = [dict(u, name=by[u["id"]], shape_name=u["name"]) for u in self.ADMIN2]
        again, _ = gc.build(self.TABLE, self.ADMIN1, common.as_drawn(renamed))
        self.assertEqual({r["shape_id"]: r["name"] for r in again if r["level"] == "admin2"},
                         {"L": "Lopé", "Z": "Zadié"})

    def test_the_counts_ride_beside_the_ratio(self):
        # Haute-Banio: 1,022 men and 391 women.
        f = gc.figures_fields(1_022, 391, 1_413, "note")
        self.assertEqual(f["sex_ratio"]["value"], 2_614)
        self.assertEqual(f["sex_ratio_note"], "Men per 1,000 women among the residents the 2013 "
                                              "census counted (1,022 men, 391 women).")
        # The build puts the ratio per 100 and keeps the counts.
        entity = {"id": "x", "sex_ratio": f["sex_ratio"], "sex_ratio_note": f["sex_ratio_note"]}
        be.one_sex_ratio_unit([entity])
        self.assertEqual(entity["sex_ratio"]["value"], 261.4)
        self.assertEqual(entity["sex_ratio_note"], "Men per 100 women among the residents the 2013 "
                                                   "census counted (1,022 men, 391 women).")


class MauritaniaSexes(unittest.TestCase):
    def test_each_ratio_says_whose_men_and_women_it_is_of(self):
        from tests.test_mauritania_census import ADMIN1, ADMIN2, LEAFLET, SYNTHETIC
        records, report = mc.build(mc.parse(LEAFLET + "\n" + SYNTHETIC), ADMIN1, ADMIN2)
        self.assertEqual(report, [])
        by = {(r["level"], r["name"]): r for r in records}
        benichab = by[("admin2", "Benichab")]
        self.assertEqual(benichab["sex_ratio"]["value"], round(1000 * 9_151 / 2_195))
        self.assertEqual(benichab["sex_ratio_note"],
                         "The 2023 census's count of the moughataa: 9,151 men and 2,195 women.")
        self.assertEqual(by[("admin2", "Amourj")]["sex_ratio_note"],
                         "The 2023 census's count of Amourj and Adel Bagrou together: 68,353 men "
                         "and 82,650 women.")
        self.assertEqual(by[("admin1", "Inchiri")]["sex_ratio_note"],
                         "The 2023 census's count of the wilaya and the moughataa of Chami "
                         "together: 23,455 men and 13,411 women.")
        self.assertEqual(by[("admin1", "Dakhlet Nouadhibou")]["sex_ratio_note"],
                         "The 2023 census's count of the moughataa of Nouadhibou: 97,955 men "
                         "and 79,122 women.")
        self.assertIn("the three wilayas of Nouakchott together",
                      by[("admin1", "Nouakchott")]["sex_ratio_note"])
        # A moughataa the census does not count as drawn shows no ratio and no note.
        self.assertNotIn("sex_ratio_note", by[("admin2", "Ksar")])


class SeychellesDistricts(unittest.TestCase):
    def table(self, *keys):
        from tests.test_seychelles_census import TEXT
        return {k: v for k, v in sc.parse(TEXT).items() if k in keys}

    def test_only_a_ratio_past_two_men_to_a_woman_carries_its_counts(self):
        self.assertEqual(sc.counted(4_751, 1_908),
                         "Men per 1,000 women among the people the 2022 census counted here: "
                         "4,751 men and 1,908 women (Table 2.4).")
        self.assertIn("1,000 men and 75 women", sc.counted(1_000, 75))
        self.assertIsNone(sc.counted(2_095, 1_442))      # La Digue and Inner Islands, 145
        self.assertIsNone(sc.counted(2_000, 1_000))
        # No national ratio beside it: the country shows the Factbook's.
        self.assertNotIn("country", sc.counted(1_000, 75))
        # The build puts it per 100, as the figure is shown.
        entity = {"id": "c", "sex_ratio": {"value": 2_490, "unit": "males_per_1000_females"},
                  "sex_ratio_note": sc.counted(4_751, 1_908)}
        be.one_sex_ratio_unit([entity])
        self.assertTrue(entity["sex_ratio_note"].startswith(
            "Men per 100 women among the people the 2022 census counted here: 4,751 men"))

    def test_cascade_carries_its_counts_and_anse_boileau_does_not(self):
        table = self.table("cascade", "anseboileau", "ileperseverance")
        recs = {r["shape_id"]: r for r in sc.build(table, [{"id": "c", "name": "Cascade"},
                                                           {"id": "a", "name": "Anse Boile"}])}
        self.assertIn("4,751 men and 1,908 women (Table 2.4)", recs["c"]["sex_ratio_note"])
        self.assertNotIn("sex_ratio_note", recs["a"])

    def test_the_other_islands_carry_their_counts_from_the_age_tables(self):
        from tests.test_seychelles_census import AGES_BOTH, AGES_MEN, TABLE24, TEXT
        table = self.table(*TABLE24)
        with mock.patch.object(sc, "DISTRICTS", ("Cascade", "La Digue and Inner Islands",
                                                 "Outer Islands")), \
                mock.patch.object(sc, "NATIONAL", 6_659 + 3_624 + 988), \
                mock.patch.object(sc, "NATIONAL_MEN", 4_751 + 2_172 + 923), \
                mock.patch.object(sc, "GROUPS2", {"eastmahe": ("Cascade",)}):
            age = sc.ages(AGES_BOTH, AGES_MEN, table)
            recs = {r["shape_id"]: r for r in sc.build2(
                table, age, sc.island_composition(TEXT),
                [{"id": "e", "name": "East Mahe"}, {"id": "l", "name": "La Digue"},
                 {"id": "o", "name": "Other Islands"}])}
        self.assertEqual(recs["o"]["sex_ratio_note"],
                         "Men per 1,000 women among the people the 2022 census counted here: "
                         "1,329 men and 150 women (Tables A2.1 and A2.2).")
        self.assertNotIn("sex_ratio_note", recs["l"])

    def test_a_cut_label_takes_the_name_it_is_cut_from(self):
        from tests.test_seychelles_census import A7
        table = self.table("anseboileau", "englishriver", "ladigueandinnerislands",
                           "ileperseverance")
        a7 = sc.parse_a7(A7)
        admin1 = [{"id": "a", "name": "Anse Boile"}, {"id": "r", "name": "La Rivière"},
                  {"id": "d", "name": "La Digue a"}]
        declared = {("SYC", "Anse Boile"): "Anse Boileau",
                    ("SYC", "La Rivière"): "La Rivière Anglaise",
                    ("SYC", "La Digue a"): "La Digue and Inner Islands"}
        with mock.patch.dict(common.MISSPELLED, declared):
            recs = {r["shape_id"]: r for r in sc.build(table, admin1, None, a7)}
            # Once the build reads the labels respelled, the cut ones stay aliases.
            full = [dict(u, name=declared[("SYC", u["name"])]) for u in admin1]
            again = {r["shape_id"]: r for r in sc.build(table, full, None, a7)}
        self.assertEqual((recs["a"]["name"], recs["a"]["aliases"]),
                         ("Anse Boileau", ["Anse Boile"]))
        self.assertEqual(recs["r"]["population"]["value"], 3_508)      # English River's
        self.assertIn("La Digue and Inner Islands is one of the census's regions",
                      recs["d"]["ethnicity_note"])
        self.assertEqual((again["a"]["name"], again["a"]["aliases"]),
                         ("Anse Boileau", ["Anse Boile"]))
        # Where nothing declares it, the label is the name, with no alias.
        plain = {r["shape_id"]: r for r in sc.build(table, admin1, None, a7)}
        self.assertEqual(plain["a"]["name"], "Anse Boile")
        self.assertNotIn("aliases", plain["a"])

    def test_the_alias_lets_the_encyclopaedia_s_row_share_the_polygon(self):
        # Wikipedia's rows are bound to these polygons by id and named by the
        # cut labels: without the alias, the build refuses the census's row.
        polygon = {"id": "4304713B87843643892528", "name": "Anse Etoil"}
        claimed: dict[int, set[str]] = {}
        be.claim(claimed, polygon, {"name": "Anse Etoil"}, "SYC", polygon["id"])
        be.claim(claimed, polygon, {"name": "Anse Etoile", "aliases": ["Anse Etoil"]}, "SYC",
                 polygon["id"])
        with self.assertRaises(SystemExit):
            be.claim({id(polygon): {"Anse Etoil"}}, polygon, {"name": "Anse Etoile"}, "SYC",
                     polygon["id"])


class NamibiaOshikoto(unittest.TestCase):
    CITE = {"field": "population",
            "name": ("OCHA, Common Operational Dataset -- population statistics (cod-ps-nam), "
                     "reference year 2023"),
            "url": "https://data.humdata.org/dataset/cod-ps-nam", "year": 2023}

    def rows(self):
        own = [{"country": "NAM", "level": "admin2", "name": f"C{i}", "parent_name": "Oshikoto",
                "population": {"value": 1_000 + i, "year": 2023}, "sources": [self.CITE]}
               for i in range(10)]
        return own + [{"country": "NAM", "level": "admin2", "name": "Kabbe",
                       "parent_name": "Zambezi", "population": {"value": 5, "year": 2023},
                       "sources": [self.CITE]}]

    def test_ocha_s_constituencies_are_added_up_for_oshikoto_alone(self):
        made, year, cite = nm.ocha_sums(self.rows())["oshikoto"]
        self.assertEqual((made, year), (10_045, 2023))
        self.assertEqual(cite, {**self.CITE, "field": "population note"})
        self.assertEqual(set(nm.ocha_sums(self.rows())), {"oshikoto"})

    def test_a_constituency_without_a_figure_or_a_second_year_gives_no_sum(self):
        rows = self.rows()
        rows[0]["population"] = {"status": "not_available"}
        self.assertEqual(nm.ocha_sums(rows), {})
        rows = self.rows()
        rows[1]["population"] = {"value": 7, "year": 2020}
        self.assertEqual(nm.ocha_sums(rows), {})

    def test_the_region_s_note_says_what_they_add_up_to_and_cites_ocha(self):
        from tests.test_namibia_census import TEXT
        sums = {"karas": (227_737, 2023, {**self.CITE, "field": "population note"})}
        with mock.patch.object(nm, "REGIONS", ("//Kharas", "Kavango East", "Kavango West")), \
                mock.patch.object(nm, "NATIONAL", 469_172):
            table = nm.parse(TEXT)
            recs = {r["shape_id"]: r for r in nm.build(
                table, [{"id": "K", "name": "Karas"}, {"id": "V", "name": "Kavango"}], sums)}
        self.assertTrue(recs["K"]["population_note"].endswith(
            " OCHA's projections of its constituencies for 2023 add up to 227,737."))
        self.assertIn({**self.CITE, "field": "population note"}, recs["K"]["sources"])
        self.assertNotIn("OCHA", recs["V"]["population_note"])

    def test_today_s_table_makes_227_737_for_oshikoto(self):
        path = nm.PROCESSED / nm.OCHA_FILE
        if not path.exists():
            self.skipTest(f"{nm.OCHA_FILE} is not in this checkout")
        made, year, _ = nm.ocha_sums(json.loads(path.read_text()))["oshikoto"]
        self.assertEqual((made, year), (227_737, 2023))


OCHA_LBR = ("OCHA, Common Operational Dataset -- population statistics (cod-ps-lbr), reference "
            "year 2020")


class LiberiaDistricts(unittest.TestCase):
    """Liberia's 55 districts the 2022 tables cannot be placed on show OCHA's
    2020 figures, and say why beside them."""

    def row(self, c="grandkru", name="Barclayville"):
        why, beside = lb.not_the_drawn(c)
        row = lb.record(f"LBR-2022-{c}-{name.lower()}", name, level="admin2", parent="LBR",
                        country="LBR", match_by="shape_id", shape_id=name,
                        **lb.district_fields(name, None, "Grand Kru County", why, beside=beside))
        return dict(row, _source="liberia_census.json"), why, beside

    def test_the_reason_reads_beside_ocha_s_figure(self):
        why, beside = lb.not_the_drawn("sinoe")
        self.assertTrue(why.endswith("so no district's 2022 count is shown."))
        self.assertTrue(beside.endswith("so no district's 2022 count can be given; the figure "
                                        "shown is OCHA's projection for 2020."))
        self.assertIn("not Dugbe River", beside)

    def test_the_notes_stay_beside_ocha_s_figures(self):
        row, why, beside = self.row()
        entity = {"id": "x", "country": "LBR", "level": "admin2",
                  "population": {"value": 15_153, "year": 2020, "source": OCHA_LBR},
                  "sex_ratio": {"value": 997, "unit": "males_per_1000_females", "year": 2020,
                                "source": OCHA_LBR},
                  "sex_ratio_note": "Males per 1,000 females in OCHA's COD-PS for this country.",
                  "sources": [{"field": "population", "name": OCHA_LBR},
                              {"field": "sex_ratio", "name": OCHA_LBR}],
                  "_from": {"population": "cod_ps_admin2.json", "sex_ratio": "cod_ps_age.json"}}
        be.merge_adapter(entity, row)
        self.assertEqual((entity["population"]["value"], entity["sex_ratio"]["value"]),
                         (15_153, 997))
        self.assertEqual((entity["population_note"], entity["sex_ratio_note"]), (beside, beside))
        self.assertIn("population note/sex_ratio note", [s["field"] for s in entity["sources"]])

    def test_where_ocha_gives_no_sex_ratio_the_stated_gap_shows(self):
        # Kpi and Wlogba: OCHA's table of sexes has neither.
        row, why, _ = self.row(name="Kpi")
        entity = {"id": "k", "country": "LBR", "level": "admin2",
                  "population": {"value": 2_091, "year": 2020, "source": OCHA_LBR},
                  "sex_ratio": {"status": "not_available"},
                  "sources": [{"field": "population", "name": OCHA_LBR}],
                  "_from": {"population": "cod_ps_admin2.json"}}
        be.merge_adapter(entity, row)
        self.assertEqual(entity["sex_ratio"], {"status": "not_available", "note": why})
        self.assertEqual(entity["population"]["value"], 2_091)


class NigeriaSexes(unittest.TestCase):
    TABLE = {"name": "LAGOS", "total": (400, 210, 190),
             "groups": [(0, 4, 160, 85, 75), (5, 9, 120, 62, 58), (10, 14, 80, 42, 38),
                        (15, 19, 40, 21, 19)] + [(a, a + 4, 0, 0, 0) for a in range(20, 85, 5)]
             + [(85, None, 0, 0, 0)]}
    BAKASSI = {"name": "BAKASSI", "total": (40, 24, 16),
               "groups": [(0, 4, 20, 12, 8), (5, 9, 10, 6, 4), (10, 14, 10, 6, 4)]
               + [(a, a + 4, 0, 0, 0) for a in range(15, 85, 5)] + [(85, None, 0, 0, 0)]}

    def test_an_area_s_ratio_carries_its_men_and_women(self):
        f = ng.fields(dict(self.TABLE, name="GWALE"), None, "note")
        self.assertEqual(f["sex_ratio_note"], "The 2006 census's count of the local government "
                                              "area: 210 men and 190 women.")
        # Volume III's figures for an area Volume IV prints no table of, too.
        vol3 = ng.fields(dict(self.TABLE, from_vol3=True), None, "note")
        self.assertIn("210 men and 190 women", vol3["sex_ratio_note"])

    def test_a_state_s_names_the_state(self):
        fct = ng.state_fields(dict(self.TABLE, name="FCT ABUJA"), None,
                              "abujafederalcapitalterritory", 0, None, {})
        self.assertEqual(fct["sex_ratio_note"], "The 2006 census's count of the Federal Capital "
                                                "Territory: 210 men and 190 women.")
        taraba = ng.state_fields(dict(self.TABLE, name="TARABA"), None, "taraba", 19_964, None, {})
        self.assertTrue(taraba["sex_ratio_note"].startswith(
            "The 2006 census's count of Taraba State: 210 men and 190 women. The count includes "
            "19,964 people"))
        cross = ng.state_fields(dict(self.TABLE, name="CROSS RIVER"), None, "crossriver", 0,
                                self.BAKASSI, {})
        self.assertEqual(cross["sex_ratio_note"], ng.CROSS_RIVER_SEXES.format(m=24, f=16))

    def test_no_note_where_no_ratio_is_taken(self):
        f = ng.fields(self.TABLE, ["men 210 and women 190 make 400, not the total 401"], "note")
        self.assertEqual(f["sex_ratio"]["status"], "not_available")
        self.assertNotIn("sex_ratio_note", f)


class EthiopiaWeredaNames(unittest.TestCase):
    """A zone's note names a wereda without the marks OCHA's table tells namesakes apart by."""

    def test_the_region_s_code_and_the_stray_bracket_come_off(self):
        self.assertEqual(et.spoken("Dera (AM)"), "Dera")
        self.assertEqual(et.spoken("Malka Jabti /M.Jebdu)"), "Malka Jabti")
        self.assertEqual(et.spoken("Bahirdar Zuria"), "Bahirdar Zuria")


class UgandaRatios(unittest.TestCase):
    """A lopsided county's note gives the country's ratio in the unit the map shows."""

    def test_the_country_s_ratio_reads_per_100(self):
        from scripts.fetch_census import uganda_census as ug
        unit = {"name": "Bufumbira", "male": 251_631, "female": 182_031, "total": 433_662}
        note = ug.fields([unit], "x")["sex_ratio_note"]
        self.assertIn("the country counted 94.6 men per 100 women.", note)
        self.assertTrue(be.PRINTED_RATIO.search(note))


class VisitorText(unittest.TestCase):
    """What the new notes say is what a figure is and where it comes from."""

    BANNED = ("adapter", "pipeline", "this project", ".json", "boundary file", "the build",
              "fetched", "scraped", "http", "citypopulation")

    def test_no_new_note_says_how_the_map_was_made(self):
        texts = [cs.SOMALIA_NOTE, cs.SOMALIA_SOURCE, cs.SOMALIA_CITED, dj.SOURCE, cg.SOURCE,
                 *lb.not_the_drawn("sinoe"), sc.counted(1_000, 75),
                 gc.figures_fields(1_022, 391, 1_413, "x")["sex_ratio_note"],
                 *(er.COMPOSITION.format(field=f) for f in ("religion", "language", "ethnicity"))]
        for text in texts:
            self.assertFalse([w for w in self.BANNED if w in text.lower()], text)


if __name__ == "__main__":
    unittest.main()
