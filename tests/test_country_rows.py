"""Country rows, parent links and the sums between levels.

What the build may and may not do when a sum of divisions meets a figure
somebody published: a county's register count is not replaced by its drawn
townships' total when one township is drawn apart from it; an older census's
provinces do not replace a newer national table; planning estimates are not
added up into a province; and a country's curated census figures stand in
front of an estimate that cannot be the same people. No network.
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
import common  # noqa: E402
import fetch_geonames  # noqa: E402
import group_tree  # noqa: E402

CURATED = ROOT / "data" / "curated" / "admin0_detail.json"
SITE = ROOT / "site" / "data"


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def kid(name, people, groups, year=2021, basis=None, pop_year=None):
    row = {"name": name, "id": name,
           "population": {"value": people, "year": pop_year or year},
           "religion": [{"group": g, "pct": round(100 * n / sum(groups.values()), 1),
                         "count": n} for g, n in groups.items()],
           "religion_year": year}
    if basis:
        row["religion_basis"] = basis
    return row


class DeclaredParents(unittest.TestCase):
    """Kinmen's sixth township is drawn a degree away from the county."""

    def shapes(self):
        adm1 = [{"group": "TWN", "name": "Kinmen", "shape_id": "K"},
                {"group": "TWN", "name": "Matsu Islands", "shape_id": "M"}]
        adm2 = [{"group": "TWN", "name": "Wuqiu", "shape_id": "W", "parent_shape": None},
                {"group": "TWN", "name": "Jincheng", "shape_id": "J", "parent_shape": "K"}]
        return adm1, adm2

    def test_a_declared_polygon_is_filed_under_its_unit(self):
        adm1, adm2 = self.shapes()
        done = be.declare_parents(adm1, adm2, {"W": ("TWN", "Kinmen")})
        self.assertEqual(adm2[0]["parent_shape"], "K")
        self.assertEqual(adm2[1]["parent_shape"], "K")
        self.assertEqual(done, ["Wuqiu (TWN) under Kinmen"])

    def test_a_declaration_for_a_shape_not_drawn_stops_the_build(self):
        adm1, adm2 = self.shapes()
        with self.assertRaises(SystemExit):
            be.declare_parents(adm1, adm2, {"X": ("TWN", "Kinmen")})

    def test_a_unit_name_the_country_does_not_draw_stops_the_build(self):
        adm1, adm2 = self.shapes()
        with self.assertRaises(SystemExit):
            be.declare_parents(adm1, adm2, {"W": ("TWN", "Kinmen County")})

    def test_a_declaration_in_another_country_stops_the_build(self):
        adm1, adm2 = self.shapes()
        with self.assertRaises(SystemExit):
            be.declare_parents(adm1, adm2, {"W": ("CHN", "Kinmen")})

    def test_kiribati_s_islands_stay_where_they_are_drawn(self):
        # kiribati_census gives each island-group polygon the islands it draws
        # and stops if the map files Tarawa or Banaba under another polygon.
        self.assertNotIn("KIR", {iso3 for iso3, _ in be.DECLARED_PARENTS.values()})

    def test_every_declaration_names_a_drawn_shape_and_a_drawn_unit(self):
        # Read off the site the last build wrote: the polygon is drawn in that
        # country, and the unit is a first-level shape of it by its label.
        for shape_id, (iso3, name) in be.DECLARED_PARENTS.items():
            units2 = json.loads((SITE / "admin2" / f"{iso3}.units.json").read_text())
            self.assertIn(shape_id, {u["id"] for u in units2}, shape_id)
            units1 = json.loads((SITE / "admin1" / f"{iso3}.units.json").read_text())
            labels = {u.get("shape_name") or u["name"] for u in units1}
            self.assertIn(name, labels, (iso3, name))

    def test_samoa_and_the_solomons_are_filed_where_their_censuses_count_them(self):
        # Vaisigano East is by area mostly in Gaga'ifomauga, West Honiara in
        # Guadalcanal, and three Solomon constituencies in no province; each
        # census names the province it counts the polygon in, and the
        # declaration must be that province.
        declared = {}
        for name in ("samoa_census.json", "solomon_census.json"):
            data = json.loads((ROOT / "data" / "processed" / name).read_text())
            for row in data["records"] if isinstance(data, dict) else data:
                if row.get("shape_id") in be.DECLARED_PARENTS:
                    iso3, unit = be.DECLARED_PARENTS[row["shape_id"]]
                    self.assertEqual((iso3, unit), (row["country"], row["parent_name"]),
                                     row["name"])
                    declared[row["name"]] = unit
        self.assertEqual(declared, {
            "Vaisigano East": "Vaisigano",
            "West Honiara": "Capital Territory (Honiara)",
            "Ranongga-Simbo": "Western", "Malaita Outer Island": "Malaita",
            "Ulawa-Ugi": "Makira"})


class SameYearCounts(unittest.TestCase):
    def test_kinmen_keeps_its_register_count(self):
        parent = {"population": {"value": 137_208, "year": 2026}}
        kids = [kid(f"T{i}", n, {"A": n}, year=2026)
                for i, n in enumerate((40_328, 34_669, 11_830, 19_579, 30_205))]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion"))
        self.assertEqual(parent["population"], {"value": 137_208, "year": 2026})

    def test_with_the_sixth_township_the_sum_is_the_count(self):
        parent = {"population": {"value": 137_208, "year": 2026}}
        kids = [kid(f"T{i}", n, {"A": n}, year=2026)
                for i, n in enumerate((40_328, 34_669, 11_830, 19_579, 30_205, 597))]
        be.roll_up_field(parent, kids, "religion")
        self.assertEqual(parent["population"]["value"], 137_208)
        self.assertIn("Their populations total 137,208 against a published 137,208",
                      parent["religion_note"])

    def test_an_older_count_still_gives_way_to_the_children(self):
        parent = {"population": {"value": 8_325_666, "year": 2011}}
        be.roll_up_field(parent, [kid("A", 9_100_104, {"A": 9_100_104}, year=2022)],
                         "religion", whole_country=True)
        self.assertEqual(parent["population"]["value"], 9_100_104)


class PlanEstimates(unittest.TestCase):
    """Afghanistan's district plans are estimates of shares, not counts."""

    def test_plan_estimates_are_not_added_up_into_a_province(self):
        parent = {"population": {"value": 1_000, "year": 2017},
                  "religion": {"status": "not_available", "note": "the province's reason"}}
        kids = [kid("Aliabad", 600, {"Pashtun": 282, "Tajik": 198, "Hazara": 120},
                    year="2008-2014", basis="district development plan", pop_year=2017),
                kid("Chahar Dara", 400, {"Pashtun": 300}, year=2007,
                    basis="district development plan", pop_year=2017)]
        why = be.roll_up_field(parent, kids, "religion")
        self.assertIn("district development plan estimates", why)
        self.assertEqual(parent["religion"]["note"], "the province's reason")

    def test_the_afghan_plan_rows_carry_the_basis_that_is_not_summed(self):
        # If either reader ever words its basis differently, the provinces
        # would be summed again without anyone deciding so.
        for name in ("afghanistan_district.json", "afghanistan_ddp.json"):
            rows = common.read_json(ROOT / "data" / "processed" / name, []) or []
            bases = {r.get("ethnicity_basis") for r in rows if isinstance(r.get("ethnicity"), list)}
            self.assertTrue(bases, name)
            self.assertLessEqual(bases, be.UNSUMMED_BASES, name)


class CountedPeople(unittest.TestCase):
    def test_the_note_gives_the_counts_own_total_and_year(self):
        # Kazakhstan: 2025 register populations, 2021 census religion.
        parent = {"population": {"value": 2_000, "year": 2025}}
        kids = [kid("North", 1_050, {"Islam": 700, "Orthodox": 250}, year=2021, pop_year=2025),
                kid("South", 950, {"Islam": 800, "Orthodox": 50}, year=2021, pop_year=2025)]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion"))
        self.assertIn("Their populations total 2,000", parent["religion_note"])
        self.assertIn("the divisions' own counts, of 1,800 people in 2021",
                      parent["religion_note"])

    def test_the_disagreement_names_the_total_it_is_measured_against(self):
        # Italy: the divisions' own counts stood between the population total
        # and "disagrees with that by -3%", which then read as the counts' gap.
        parent = {"population": {"value": 60_924_851, "year": 2023},
                  "religion": [{"group": "Islam", "pct": None}]}
        kids = [kid("North", 30_000_000, {"Islam": 20_000_000, "Orthodox": 8_000_000},
                    year=2015, pop_year=2023),
                kid("South", 28_943_464, {"Islam": 20_000_000, "Orthodox": 9_251_233},
                    year=2015, pop_year=2023)]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion", level="first-level",
                                           over_published=True, complete=True))
        note = parent["religion_note"]
        self.assertRegex(note, r"own counts, of 57,25\d,\d{3} people in 2015\. The unit's")
        self.assertIn("The unit's own published population of 60,924,851 disagrees with "
                      "the divisions' total of 58,943,464 by -3%", note)
        self.assertNotIn("disagrees with that", note)

    def test_households_are_called_households(self):
        # Suriname's districts count households by the language most spoken
        # in them, not people.
        basis = "households by the language most spoken in them"
        parent = {"population": {"value": 2_000, "year": 2004}}
        kids = [kid("North", 1_050, {"Dutch": 300, "Sranan": 100}, year=2004, basis=basis),
                kid("South", 950, {"Dutch": 200, "Sranan": 150}, year=2004, basis=basis)]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion"))
        self.assertIn("the divisions' own counts, of 750 households in 2004",
                      parent["religion_note"])
        self.assertEqual(be.counted_noun("language of the household head"), "households")
        self.assertEqual(be.counted_noun("self-identification"), "people")
        self.assertEqual(be.counted_noun(None), "people")

    def test_counts_of_the_populations_themselves_need_no_second_total(self):
        parent = {"population": {"value": 2_000, "year": 2021}}
        kids = [kid("North", 1_000, {"Islam": 750, "Orthodox": 250}),
                kid("South", 1_000, {"Islam": 900, "Orthodox": 100})]
        be.roll_up_field(parent, kids, "religion")
        self.assertNotIn("own counts", parent["religion_note"])


class CountriesNotSummed(unittest.TestCase):
    def test_an_older_census_does_not_replace_a_newer_national_figure(self):
        for key in (("VNM", "religion"), ("THA", "ethnicity"), ("THA", "religion"),
                    ("VUT", "language"), ("LBN", "ethnicity"), ("TLS", "religion")):
            self.assertIn(key, be.COUNTRY_NOT_SUMMED)
        country = {"id": "VNM", "codes": {"iso3": "VNM"},
                   "population": {"value": 2_000, "year": 2019},
                   "religion": [{"group": "No religion", "pct": 86.3}],
                   "religion_year": 2019}
        kids = [kid("A", 1_000, {"No religion": 800, "Buddhism": 200}, year=2009, pop_year=2019),
                kid("B", 1_000, {"No religion": 850, "Buddhism": 150}, year=2009, pop_year=2019)]
        quiet(be.roll_up_countries, [country], {"VNM": kids})
        self.assertEqual(country["religion"], [{"group": "No religion", "pct": 86.3}])
        self.assertEqual(country["religion_year"], 2019)


class CuratedFigures(unittest.TestCase):
    """A census count in front of an estimate that cannot be the same people."""

    ROW = {"country": "MHL", "field": "population", "value": 42_418, "year": 2021,
           "source": "EPPSO, RMI 2021 Census Report, Volume 1", "url": "https://example.org",
           "note": "The 2021 census count of the Marshall Islands."}

    def country(self):
        return {"id": "MHL", "codes": {"iso3": "MHL"},
                "population": {"value": 82_011, "year": 2024, "source": "CIA World Factbook"},
                "religion": [{"group": "Protestant", "pct": 80.0}],
                "sources": [{"field": "*", "name": "CIA World Factbook"}]}

    def test_the_count_replaces_the_estimate_before_the_sums(self):
        mhl = self.country()
        counted = quiet(be.apply_country_figures, [mhl], {"MHL": [self.ROW]})
        self.assertEqual(counted, {"MHL"})
        self.assertEqual(mhl["population"]["value"], 42_418)
        self.assertEqual(mhl["population"]["year"], 2021)
        self.assertEqual(mhl["population_note"], self.ROW["note"])
        self.assertIn("EPPSO, RMI 2021 Census Report, Volume 1",
                      [s["name"] for s in mhl["sources"]])
        # The atolls the map draws are all but Lib's 156 people.
        kids = [kid("Majuro", 23_000, {"United Church of Christ": 23_000}),
                kid("Kwajalein", 19_262, {"United Church of Christ": 19_262})]
        quiet(be.roll_up_countries, [mhl], {"MHL": kids}, counted)
        self.assertEqual(mhl["religion"][0]["group"], "United Church of Christ")
        self.assertEqual(mhl["population"]["value"], 42_418)

    def test_an_estimate_still_gives_way_to_a_same_year_count(self):
        fin = {"id": "FIN", "codes": {"iso3": "FIN"},
               "population": {"value": 5_550_449, "year": 2025},
               "religion": [{"group": "Lutheran", "pct": 60.0}]}
        kids = [kid("North", 2_652_881, {"Lutheran": 2_652_881}, year=2025),
                kid("South", 3_000_000, {"Lutheran": 3_000_000}, year=2025)]
        quiet(be.roll_up_countries, [fin], {"FIN": kids})
        self.assertEqual(fin["population"]["value"], 5_652_881)

    def test_a_median_row_carries_its_unit(self):
        nru = {"id": "NRU", "median_age": {"value": 28.2, "unit": "years", "year": 2025}}
        quiet(be.apply_country_figures, [nru],
              {"NRU": [{"country": "NRU", "field": "median_age", "value": 21.6, "year": 2021,
                        "source": "Nauru Bureau of Statistics", "note": "n"}]})
        self.assertEqual(nru["median_age"], {"value": 21.6, "unit": "years", "year": 2021,
                                             "source": "Nauru Bureau of Statistics"})

    def test_a_figure_row_without_a_source_stops_the_build(self):
        with self.assertRaises(SystemExit):
            quiet(be.apply_country_figures, [self.country()],
                  {"MHL": [dict(self.ROW, source=None)]})

    def test_the_composition_pass_leaves_figure_rows_alone(self):
        mhl = self.country()
        quiet(be.apply_country_detail, [mhl], {"MHL": [self.ROW]})
        self.assertEqual(mhl["population"]["value"], 82_011)


class CuratedCompositions(unittest.TestCase):
    def test_a_status_row_states_the_gap_in_place_of_the_line(self):
        kaz = {"id": "KAZ", "language": [{"group": "Kazakh", "pct": 80.1},
                                         {"group": "Russian", "pct": 83.7}],
               "language_year": 2021,
               "sources": [{"field": "*", "name": "CIA World Factbook"},
                           {"field": "language", "name": "an old citation"}]}
        quiet(be.apply_country_detail, [kaz], {"KAZ": [
            {"country": "KAZ", "field": "language", "status": "not_available",
             "note": "proficiency, not a composition", "source": "Bureau of National Statistics"}]})
        self.assertEqual(kaz["language"], {"status": "not_available",
                                           "note": "proficiency, not a composition"})
        self.assertNotIn("language_year", kaz)
        self.assertNotIn("language_note", kaz)
        self.assertEqual([s["name"] for s in kaz["sources"]],
                         ["CIA World Factbook", "Bureau of National Statistics"])

    def test_a_status_row_must_be_a_gap(self):
        with self.assertRaises(SystemExit):
            quiet(be.apply_country_detail, [{"id": "KAZ"}], {"KAZ": [
                {"country": "KAZ", "field": "language", "status": "modelled", "note": "n"}]})

    def test_a_census_table_takes_the_sum_s_citations_with_it(self):
        vnm = {"id": "VNM", "religion": [{"group": "No religion", "pct": 81.8}],
               "religion_year": 2009, "religion_basis": "something",
               "sources": [{"field": "*", "name": "CIA World Factbook"},
                           {"field": "religion", "name": "2009 census, Table 7"},
                           {"field": "population/religion", "name": "a shared citation"}]}
        quiet(be.apply_country_detail, [vnm], {"VNM": [
            {"country": "VNM", "field": "religion", "year": 2019, "source": "2019 census, Table 3",
             "note": "n", "groups": [{"group": "No religion", "pct": 86.3, "count": 83}]}]})
        self.assertEqual(vnm["religion_year"], 2019)
        self.assertNotIn("religion_basis", vnm)
        self.assertEqual([s["name"] for s in vnm["sources"]],
                         ["CIA World Factbook", "a shared citation", "2019 census, Table 3"])

    def test_a_note_row_may_say_what_the_line_counts(self):
        tha = {"id": "THA", "ethnicity": [{"group": "Thai", "pct": 97.5}]}
        quiet(be.apply_country_detail, [tha], {"THA": [
            {"country": "THA", "field": "ethnicity", "basis": "nationality", "note": "n"}]})
        self.assertEqual(tha["ethnicity_basis"], "nationality")
        self.assertEqual(tha["ethnicity"], [{"group": "Thai", "pct": 97.5}])


class CuratedFile(unittest.TestCase):
    """data/curated/admin0_detail.json as written."""

    rows = json.loads(CURATED.read_text())["rows"]

    def row(self, country, field):
        hits = [r for r in self.rows if r["country"] == country and r["field"] == field]
        self.assertEqual(len(hits), 1, (country, field))
        return hits[0]

    def test_a_census_row_takes_each_share_from_its_count(self):
        # Mongolia's Uuld were printed at 0.4% beside 14,666 people of
        # 3,174,565, which is 0.46%. A survey's shares are weighted and its
        # counts are respondents, so only counts of people are held to this.
        for r in self.rows:
            if not r.get("groups") or "survey" in str(r.get("basis") or ""):
                continue
            base = sum(g["count"] for g in r["groups"])
            for g in r["groups"]:
                self.assertAlmostEqual(g["pct"], 100 * g["count"] / base, delta=0.051,
                                       msg=f"{r['country']} {r['field']} {g['group']}")

    def test_every_figure_row_says_what_it_is(self):
        for r in self.rows:
            if r["field"] not in be.FIGURE_ROWS:
                continue
            self.assertIsInstance(r.get("value"), (int, float), r)
            self.assertIsInstance(r.get("year"), int, r)
            self.assertTrue(r.get("source") and r.get("url"), r)
            self.assertGreater(len(r.get("note", "")), 80, r)

    def test_status_rows_are_gaps(self):
        for r in self.rows:
            if r.get("status"):
                self.assertIn(r["status"], be.CURATED_GAPS, r)
                self.assertNotIn("groups", r, r)

    def test_every_group_of_these_census_rows_is_placed_in_the_tree(self):
        # The tables written from the regions' own census files, whose labels
        # are the regions'. (Uganda's and Russia's older rows still carry a few
        # labels the tree files nowhere -- Karimojong, Napore, Atheist -- which
        # is group_tree's to place.)
        for r in self.rows:
            if (r["country"], r["field"]) not in {
                    ("VNM", "religion"), ("IRN", "religion"), ("KGZ", "ethnicity"),
                    ("KGZ", "language"), ("TKM", "ethnicity"), ("TKM", "language"),
                    ("MNG", "ethnicity"), ("PRK", "ethnicity"), ("TLS", "religion")}:
                continue
            for g in r.get("groups") or []:
                placed = (group_tree.parent_of(r["field"], g["group"]) is not None
                          or g["group"] in group_tree.tier1_names(r["field"]))
                self.assertTrue(placed, (r["country"], r["field"], g["group"]))

    def test_the_new_census_tables_make_their_totals(self):
        for (country, field), total in {("VNM", "religion"): 96_208_984,
                                        ("IRN", "religion"): 79_926_270,
                                        ("KGZ", "ethnicity"): 6_936_156,
                                        ("KGZ", "language"): 6_936_156,
                                        ("TKM", "ethnicity"): 7_057_841,
                                        ("TKM", "language"): 7_057_841,
                                        ("MNG", "ethnicity"): 3_174_565,
                                        ("TLS", "religion"): 1_248_705}.items():
            r = self.row(country, field)
            self.assertEqual(sum(g["count"] for g in r["groups"]), total, (country, field))
            self.assertIn(f"{total:,}", r["note"], (country, field))

    def test_timor_leste_s_2022_table(self):
        r = self.row("TLS", "religion")
        self.assertEqual(r["year"], 2022)
        self.assertIn("basic table 4.07", r["source"])
        counts = {g["group"]: g["count"] for g in r["groups"]}
        self.assertEqual((counts["Catholic"], counts["Traditional religion"],
                          counts["Not stated"]), (1_217_157, 240, 239))
        self.assertIn("3 and over in private households", r["note"])

    def test_north_korea_s_military_camps(self):
        note = self.row("PRK", "ethnicity")["note"]
        self.assertIn("702,372", note)
        self.assertEqual(24_052_231 - 23_349_859, 702_372)

    def test_mongolia_s_groups_in_order_of_size(self):
        groups = self.row("MNG", "ethnicity")["groups"]
        named = [g["count"] for g in groups if not g["group"].startswith("Other")]
        self.assertEqual(named, sorted(named, reverse=True))
        pct = {g["group"]: g["pct"] for g in groups}
        self.assertEqual((pct["Uuld"], pct["Myangad"]), (0.5, 0.3))

    def test_notes_carry_no_process_wording(self):
        for r in self.rows:
            for word in ("owner's decision", "runner", "the build"):
                self.assertNotIn(word, r.get("note", ""), (r["country"], r["field"], word))


class SettlementFigures(unittest.TestCase):
    """A named place's figure, weighed against the unit's final population."""

    def unit(self, name, people, town, figure, source="GeoNames (CC BY 4.0)",
             parent="P"):
        return {"id": name, "name": name, "parent": parent,
                "population": {"value": people, "year": 2023},
                "largest_settlement": town,
                "largest_settlement_population": {"value": figure, "source": source},
                "sources": [{"field": "largest settlement", "name": "GeoNames"},
                            {"field": "population", "name": "Census"}]}

    def test_a_city_the_district_is_part_of_is_not_named(self):
        # Kritar - Sirah, a district of Aden, given a population after the
        # place was named.
        e = self.unit("Kritar - Sirah", 76_723, "Aden", 1_079_670)
        self.assertEqual(be.settle_settlement_figures({}, {"YEM": [e]}), (1, 0))
        self.assertEqual(e["largest_settlement"]["status"], "not_available")
        self.assertEqual(e["largest_settlement"]["note"],
                         "No GeoNames place is named: Aden (1,079,670) is more than the "
                         "unit (76,723): a city it is part of, or across a boundary.")
        self.assertNotIn("largest_settlement_population", e)
        self.assertEqual([s["name"] for s in e["sources"]], ["Census"])

    def test_a_place_within_the_span_keeps_its_name_and_loses_its_figure(self):
        e = self.unit("Hirat", 506_896, "Herāt", 574_300)
        self.assertEqual(be.settle_settlement_figures({}, {"AFG": [e]}), (0, 1))
        self.assertEqual(e["largest_settlement"], "Herāt")
        self.assertNotIn("largest_settlement_population", e)
        self.assertEqual(len(e["sources"]), 2)

    def test_a_place_drawn_as_a_unit_elsewhere_is_not_named(self):
        e = self.unit("Rudaki District", 603_337, "Dushanbe", 679_400, parent="DRS")
        city = {"id": "DU", "name": "Dushanbe", "parent": "TJK"}
        self.assertEqual(be.settle_settlement_figures({"TJK": [city]}, {"TJK": [e]}), (1, 0))
        self.assertIn("the map draws a unit of that name apart from this one",
                      e["largest_settlement"]["note"])

    def test_a_city_beside_a_namesake_county_keeps_its_own_name(self):
        # Kyiv's 2001 count beside GeoNames' 2,952,301; "Kyiv Oblast" is
        # drawn under the same name, and so is Baltimore County.
        kyiv = self.unit("Kyiv", 2_566_953, "Kyiv", 2_952_301, parent="K1")
        oblast = {"id": "KO", "name": "Kyiv Oblast", "parent": "UKR"}
        city = {"id": "K1", "name": "Kyiv", "parent": "UKR"}
        self.assertEqual(be.settle_settlement_figures({"UKR": [city, oblast]},
                                                      {"UKR": [kyiv]}), (0, 1))
        self.assertEqual(kyiv["largest_settlement"], "Kyiv")
        self.assertNotIn("largest_settlement_population", kyiv)
        self.assertEqual(len(kyiv["sources"]), 2)

        town = self.unit("Kota Bekasi", 2_590_257, "Bekasi", 2_648_272)
        regency = {"id": "B", "name": "Bekasi", "parent": "P",
                   "largest_settlement": "Cikarang"}
        self.assertEqual(be.settle_settlement_figures({}, {"IDN": [regency, town]}), (0, 1))
        self.assertEqual(town["largest_settlement"], "Bekasi")
        self.assertEqual(regency["largest_settlement"], "Cikarang")

    def test_a_namesake_elsewhere_still_refuses_a_town_of_another_name(self):
        # The test is of this unit's own name, not of any name: Dushanbe in
        # Rudaki District is refused as before (see the test above).
        e = self.unit("San Pedro", 34_801, "San Vicente", 38_247)
        other = {"id": "SV", "name": "San Vicente", "parent": "Q"}
        self.assertEqual(be.settle_settlement_figures({}, {"ARG": [e, other]}), (1, 0))
        self.assertIn("apart from this one", e["largest_settlement"]["note"])

    def test_beyond_the_span_the_unit_s_very_name_stands_without_its_figure(self):
        drammen = self.unit("Drammen", 68_933, "Drammen", 106_013)
        self.assertEqual(be.settle_settlement_figures({}, {"NOR": [drammen]}), (0, 1))
        self.assertEqual(drammen["largest_settlement"], "Drammen")
        self.assertNotIn("largest_settlement_population", drammen)
        # Only the very name: a district named for the city it is part of is
        # still refused it.
        old_town = self.unit("Bratislava I", 47_896, "Bratislava", 423_737)
        self.assertEqual(be.settle_settlement_figures({}, {"SVK": [old_town]}), (1, 0))
        self.assertIn("a city it is part of", old_town["largest_settlement"]["note"])
        # ...and not where another unit is drawn under that name.
        twin = self.unit("Drammen", 68_933, "Drammen", 106_013)
        other = {"id": "D2", "name": "Drammen", "parent": "Q"}
        self.assertEqual(be.settle_settlement_figures({}, {"NOR": [twin, other]}), (1, 0))

    def test_a_metropolitan_figure_goes_and_the_name_stays(self):
        # Natural Earth's Tokyo is the metropolitan area's.
        e = self.unit("Tokyo", 14_047_594, "Tokyo", 35_676_000,
                      source="Natural Earth populated places (CC0)")
        self.assertEqual(be.settle_settlement_figures({"JPN": [e]}, {}), (0, 1))
        self.assertEqual(e["largest_settlement"], "Tokyo")
        self.assertNotIn("largest_settlement_population", e)

    def test_a_place_that_fits_or_a_unit_with_no_population_is_left_alone(self):
        fits = self.unit("Brest", 384_542, "Brest", 347_138)
        bare = self.unit("Somewhere", 1, "Town", 50_000)
        bare["population"] = {"status": "not_available"}
        self.assertEqual(be.settle_settlement_figures({}, {"BLR": [fits, bare]}), (0, 0))
        self.assertEqual(fits["largest_settlement_population"]["value"], 347_138)
        self.assertEqual(bare["largest_settlement_population"]["value"], 50_000)


class GeoNamesSpans(unittest.TestCase):
    """GeoNames' 'more than the unit' refusal, weighed against the final population."""

    def entity(self, unit_population, town="Temirtau", people=170_600):
        reason = fetch_geonames.largest(
            [{"name": town, "population": people, "code": "PPLA2"}], set(), 52_263)[1]
        self.assertIsNotNone(be.SPANS_REASON.match(reason), reason)
        e = {"id": "S1", "name": "Bukhar-Zhyrauskiy",
             "largest_settlement": {"status": "not_available",
                                    "note": f"No GeoNames place is named: {reason}.",
                                    "_spans": {"town": town, "people": people}}}
        if unit_population is not None:
            e["population"] = {"value": unit_population, "year": 2025}
        return e

    def test_the_fetch_reason_is_the_one_the_build_reads(self):
        why = fetch_geonames.largest(
            [{"name": "Kŭlob", "population": 214_700, "code": "PPLA2"}], set(), 96_000)[1]
        m = be.SPANS_REASON.match(why)
        self.assertEqual((m["town"], m["people"], m["unit"]), ("Kŭlob", "214,700", "96,000"))

    def test_a_place_the_unit_now_holds_is_named(self):
        e = self.entity(798_840)
        self.assertEqual(be.settle_geonames_spans({"KAZ": [e]}, {}), (1, 0))
        self.assertEqual(e["largest_settlement"], "Temirtau")
        self.assertEqual(e["largest_settlement_population"]["value"], 170_600)

    def test_a_place_larger_than_the_unit_but_within_the_span_is_named_without_its_figure(self):
        e = self.entity(120_000)
        be.settle_geonames_spans({}, {"KAZ": [e]})
        self.assertEqual(e["largest_settlement"], "Temirtau")
        self.assertNotIn("largest_settlement_population", e)

    def test_a_place_that_still_outnumbers_the_unit_quotes_the_population_shown(self):
        e = self.entity(60_000)
        self.assertEqual(be.settle_geonames_spans({}, {"KAZ": [e]}), (0, 1))
        self.assertIn("is more than the unit (60,000)", e["largest_settlement"]["note"])
        self.assertNotIn("_spans", e["largest_settlement"])

    def test_an_unchanged_population_leaves_the_reason_as_it_was(self):
        e = self.entity(52_263)
        before = e["largest_settlement"]["note"]
        self.assertEqual(be.settle_geonames_spans({}, {"KAZ": [e]}), (0, 0))
        self.assertEqual(e["largest_settlement"]["note"], before)

    def held(self, town, people):
        return {"status": "not_available", "note": "No GeoNames place is named.",
                "_spans": {"town": town, "people": people}}

    def test_a_place_drawn_as_a_unit_of_its_own_is_not_named_for_its_neighbour(self):
        rudaki = {"id": "R", "name": "Rudaki District", "parent": "DRS",
                  "population": {"value": 603_337, "year": 2020},
                  "largest_settlement": self.held("Dushanbe", 679_400)}
        admin1 = {"TJK": [{"id": "DRS", "name": "Districts of Republican Subordination",
                           "parent": "TJK"},
                          {"id": "DU", "name": "Dushanbe", "parent": "TJK",
                           "population": {"value": 948_251, "year": 2020},
                           "largest_settlement": "Dushanbe"}]}
        self.assertEqual(be.settle_geonames_spans(admin1, {"TJK": [rudaki]}), (0, 1))
        self.assertEqual(rudaki["largest_settlement"]["note"],
                         "No GeoNames place is named: Dushanbe (679,400) is more than the "
                         "unit (603,337), and the map draws a unit of that name apart from "
                         "this one.")
        self.assertNotIn("largest_settlement_population", rudaki)

    def test_a_place_bearing_the_unit_s_own_name_is_named_beside_its_namesake(self):
        # Oyama in Tochigi; the town of Oyama in Shizuoka is drawn too.
        city = {"id": "O1", "name": "Oyama", "parent": "TOC",
                "population": {"value": 166_666, "year": 2020},
                "largest_settlement": self.held("Oyama", 167_647)}
        town = {"id": "O2", "name": "Oyama", "parent": "SHZ"}
        self.assertEqual(be.settle_geonames_spans({}, {"JPN": [city, town]}), (1, 0))
        self.assertEqual(city["largest_settlement"], "Oyama")
        self.assertNotIn("largest_settlement_population", city)

    def test_beyond_the_span_only_the_unit_s_very_name_is_named(self):
        commune = {"id": "C", "name": "PERIAM", "parent": "TM",
                   "population": {"value": 4_196, "year": 2021},
                   "largest_settlement": self.held("Periam", 6_563)}
        lea = {"id": "L", "name": "GALWAY CITY CENTRAL LEA-6", "parent": "G",
               "population": {"value": 29_705, "year": 2022},
               "largest_settlement": self.held("Galway", 85_910)}
        self.assertEqual(be.settle_geonames_spans({}, {"ROU": [commune], "IRL": [lea]}),
                         (1, 1))
        self.assertEqual(commune["largest_settlement"], "Periam")
        self.assertNotIn("largest_settlement_population", commune)
        self.assertIn("a city it is part of", lea["largest_settlement"]["note"])

    def test_a_place_drawn_inside_the_unit_is_still_named(self):
        district = {"id": "P", "name": "District of Prishtina", "parent": "XKX",
                    "population": {"value": 511_307, "year": 2024},
                    "largest_settlement": self.held("Pristina", 550_000)}
        town = {"id": "M", "name": "Pristina", "parent": "P"}
        self.assertEqual(be.settle_geonames_spans({"XKX": [district]}, {"XKX": [town]}),
                         (1, 0))
        self.assertEqual(district["largest_settlement"], "Pristina")

    def test_a_place_that_fits_is_named_whatever_else_shares_its_name(self):
        unit = {"id": "B2", "name": "Brest", "parent": "B1",
                "population": {"value": 384_542, "year": 2024},
                "largest_settlement": self.held("Brest", 347_138)}
        other = {"id": "X", "name": "Brest", "parent": "BLR"}
        self.assertEqual(be.settle_geonames_spans({"BLR": [other]}, {"BLR": [unit]}), (1, 0))
        self.assertEqual(unit["largest_settlement_population"]["value"], 347_138)

    def test_a_unit_with_no_population_quotes_none(self):
        e = self.entity(None)
        be.settle_geonames_spans({}, {"KAZ": [e]})
        self.assertNotIn("52,263", e["largest_settlement"]["note"])
        self.assertIn("has none here", e["largest_settlement"]["note"])


class NepalDistricts(unittest.TestCase):
    def test_the_census_districts_take_the_place_of_the_projection(self):
        self.assertEqual(be.SUPERSEDED_ROWS["cod_ps_admin2.json"]["NPL"], "nepal_district.json")
        self.assertIn("nepal_district.json", be.ADAPTER_FILES)


class WikipediaFloor(unittest.TestCase):
    """The Wikipedia floor gives way where an office's file pins every polygon."""

    def rows(self, name):
        payload = common.read_json(ROOT / "data" / "processed" / name, []) or []
        return payload if isinstance(payload, list) else payload.get("records", [])

    def test_ghazni_and_the_gilbert_islands_are_the_offices(self):
        self.assertEqual(be.SUPERSEDED_ROWS["wiki_population_admin1.json"],
                         {"AFG": "afghanistan_estimates.json", "KIR": "kiribati_census.json"})

    def test_each_superseded_row_s_polygon_is_pinned_by_the_office_s_file(self):
        # Dropping a Wikipedia row loses nothing only if the file it gives way
        # to writes the same polygon.
        wiki = self.rows("wiki_population_admin1.json")
        for iso3, by in be.SUPERSEDED_ROWS["wiki_population_admin1.json"].items():
            self.assertIn(by, be.ADAPTER_FILES)
            pinned = {r.get("shape_id") for r in self.rows(by) if r.get("level") == "admin1"}
            mine = [r for r in wiki if (r.get("country") or r.get("id", "")[:3]) == iso3]
            self.assertTrue(mine, iso3)
            for r in mine:
                self.assertIn(r.get("shape_id"), pinned, (iso3, r.get("name")))

    def test_the_superseded_rows_are_not_loaded(self):
        loaded = quiet(be.load_adapters)
        for iso3 in ("AFG", "KIR"):
            sources = {r["_source"] for r in loaded.get(iso3, [])}
            self.assertNotIn("wiki_population_admin1.json", sources, iso3)


class TheBlockedLineIsGone(unittest.TestCase):
    def test_no_registration_is_marked_blocked(self):
        source = (ROOT / "scripts" / "build_entities.py").read_text()
        self.assertNotIn("[BLOCKED", source)


if __name__ == "__main__":
    unittest.main()
