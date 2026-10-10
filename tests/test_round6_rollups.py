"""Round 6, roll-ups: parents against their divisions, and the figures behind both.

Afghanistan's provinces from their drawn districts; OCHA's projections giving
way to an office's census; country populations from censuses and registers;
the reconcile pass that replaces an encyclopaedia's parent figure with its
divisions' one-source sum or says why the two differ; the country notes for
declared refusals; Greece's first level summed under its policy note; the
reasons for Antarctica's and Abyei's empty populations; one sex-ratio unit;
and scripts/check_rollups.py, which finds any disagreement nothing explains.
No network.
"""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
import check_rollups as cr  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SITE = ROOT / "site" / "data"
CURATED = ROOT / "data" / "curated" / "admin0_detail.json"


def processed(name):
    return json.loads((PROCESSED / name).read_text(encoding="utf-8"))


def curated(iso3, field):
    rows = json.loads(CURATED.read_text(encoding="utf-8"))["rows"]
    found = [r for r in rows if r["country"] == iso3 and r["field"] == field]
    assert len(found) == 1, (iso3, field, len(found))
    return found[0]


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def unit(uid, name, people=None, year=None, source="Wikidata (CC0)", parent=None, **more):
    pop = ({"value": people, "year": year, "source": source} if people is not None
           else {"status": "not_available"})
    if pop.get("year") is None:
        pop.pop("year", None)
    return {"id": uid, "name": name, "parent": parent, "population": pop, "sources": [], **more}


# --------------------------------------------------------------------------
# Afghanistan
# --------------------------------------------------------------------------

class AfghanProvinces(unittest.TestCase):
    """The five provinces take their drawn districts' sums (rollups-1..5, 62)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {r["id"]: r for r in processed("afghanistan_estimates.json")}

    def test_the_five_provinces_take_their_drawn_sums_and_sex_ratios(self):
        expected = {"02": (430894, 103.1), "14": (568031, 105.7), "13": (596814, 105.4),
                    "12": (448496, 106.4), "08": (103881, 105.3)}
        for code, (people, ratio) in expected.items():
            rec = self.rows[f"AFG-EST-{code}"]
            self.assertEqual(rec["population"]["value"], people, rec["name"])
            self.assertEqual(rec["population"]["year"], 2017)
            self.assertEqual(rec["sex_ratio"]["value"], ratio, rec["name"])
            self.assertNotIn("no_child_sum", rec["population"])
            self.assertIn("The office's own total for the province", rec["population_note"])
            self.assertIn("outlines that do not line up exactly", rec["population_note"])

    def test_the_notes_cite_the_office_totals_and_where_districts_are_drawn(self):
        kapisa = self.rows["AFG-EST-02"]["population_note"]
        self.assertIn("455,574", kapisa)
        self.assertIn("Mahmudi Raqi, which the office counts here, is drawn in Parwan", kapisa)
        self.assertIn("Rukha, drawn here, is counted by the office in Panjshir", kapisa)
        self.assertIn("593,691", self.rows["AFG-EST-14"]["population_note"])
        self.assertIn("Spira, which the office counts here, is drawn in Paktika",
                      self.rows["AFG-EST-14"]["population_note"])
        self.assertIn("158,548", self.rows["AFG-EST-08"]["population_note"])
        self.assertIn("Shutul, which the office counts here, is drawn in Parwan",
                      self.rows["AFG-EST-08"]["population_note"])

    def test_the_provinces_make_the_settled_total(self):
        provinces = [r for r in self.rows.values() if r["level"] == "admin1"]
        self.assertEqual(len(provinces), 34)
        self.assertTrue(all("value" in r["population"] for r in provinces))
        six = sum(self.rows[f"AFG-EST-{c}"]["population"]["value"]
                  for c in ("02", "14", "13", "12", "08", "03"))
        self.assertEqual(six, 2_914_706)

    def test_khost_wa_firing_is_its_sexes_sum(self):
        rec = self.rows["AFG-EST-0913"]
        self.assertEqual(rec["population"]["value"], 66568)
        self.assertEqual(rec["population"]["year"], 2017)
        self.assertIn("69,568", rec["population_note"])
        self.assertIn("32,201 females and 34,367 males", rec["population_note"])
        districts = [r for r in self.rows.values()
                     if r["level"] == "admin2" and r.get("parent_name") == "Baghlan"]
        self.assertEqual(sum(r["population"]["value"] for r in districts), 943_394)

    def test_district_plan_shares_are_summed_into_their_provinces(self):
        if not (SITE / "admin2" / "AFG.units.json").exists():
            raise unittest.SkipTest("site/data has not been built")
        a1 = json.loads((SITE / "admin1" / "AFG.units.json").read_text(encoding="utf-8"))
        a2 = json.loads((SITE / "admin2" / "AFG.units.json").read_text(encoding="utf-8"))
        expected = {"Laghman": [("Pashtun", 52.0), ("Pashai", 26.7), ("Tajik", 21.3)],
                    "Nuristan": [("Nuristani", 99.8), ("Other or not stated", 0.2)]}
        for parent in a1:
            if parent["name"] not in expected:
                continue
            kids = [c for c in a2 if c.get("parent") == parent["id"] and not c.get("water")]
            work = copy.deepcopy(parent)
            work["ethnicity"] = {"status": "not_available"}
            self.assertIsNone(be.roll_up_field(work, kids, "ethnicity"))
            self.assertEqual([(g["group"], g["pct"]) for g in work["ethnicity"]],
                             expected[parent["name"]])
            self.assertEqual(work["ethnicity_basis"], "district development plan")
        self.assertEqual(be.UNSUMMED_BASES, frozenset())


# --------------------------------------------------------------------------
# OCHA's projections against an office's census
# --------------------------------------------------------------------------

class SupersededProjections(unittest.TestCase):
    """COD-PS gives way where the office's file covers every drawn unit (rollups-17, 22, 26, 27)."""

    WANTED = {"LAO": "laos_district.json", "PHL": "philippines_age.json",
              "PRY": "paraguay_census.json", "NIC": "nicaragua_census.json",
              "CRI": "costa_rica_census.json", "MEX": "mexico_municipality.json",
              "GEO": "georgia.json", "GTM": "guatemala_census.json",
              "DOM": "dominican_census.json"}

    def test_the_census_files_supersede_the_projection(self):
        rows = be.SUPERSEDED_ROWS["cod_ps_admin2.json"]
        for iso3, file in self.WANTED.items():
            self.assertEqual(rows.get(iso3), file, iso3)
            self.assertIn(file, be.ADAPTER_FILES, file)
        # Myanmar keeps one vintage at both levels.
        self.assertNotIn("MMR", rows)

    def test_every_drawn_unit_bound_by_shape_has_a_count_or_a_reason(self):
        for iso3 in ("PHL", "PRY", "NIC", "CRI", "GEO"):
            path = SITE / "admin2" / f"{iso3}.units.json"
            if not path.exists():
                raise unittest.SkipTest("site/data has not been built")
            drawn = {u["id"] for u in json.loads(path.read_text(encoding="utf-8"))
                     if not u.get("water")}
            rows = {r.get("shape_id"): r for r in processed(self.WANTED[iso3])
                    if r.get("level") == "admin2"}
            for sid in drawn:
                self.assertIn(sid, rows, f"{iso3} {sid}")
                pop = rows[sid]["population"]
                self.assertTrue("value" in pop or pop.get("note"), f"{iso3} {sid}")

    def test_laos_districts_make_their_provinces(self):
        rows = processed("laos_district.json")
        self.assertEqual(len([r for r in rows if r["level"] == "admin2"]), 148)
        self.assertEqual(sum(r["population"]["value"] for r in rows
                             if r["level"] == "admin2"), 6_481_625)

    def test_guatemala_writes_everyone_enumerated_at_both_levels(self):
        rows = processed("guatemala_census.json")
        depts = [r for r in rows if r["level"] == "admin1"]
        self.assertEqual(sum(r["population"]["value"] for r in depts), 14_901_286)
        for r in rows:
            counted = sum(g["count"] for g in r["ethnicity"])
            self.assertEqual(r["population"]["value"], counted, r["name"])
        by = {r["name"]: r["population"]["value"] for r in depts}
        self.assertEqual((by["Quiché"], by["Alta Verapaz"], by["Petén"]),
                         (949_261, 1_215_038, 545_600))

    def test_dominican_provinces_carry_the_census_their_municipios_make(self):
        rows = processed("dominican_census.json")
        provinces = [r for r in rows if r["level"] == "admin1"]
        self.assertEqual(len(provinces), 32)
        self.assertEqual(sum(r["population"]["value"] for r in provinces), 10_773_983)
        by_parent = {}
        for r in rows:
            if r["level"] == "admin2" and "value" in r["population"]:
                by_parent[r["parent_name"]] = by_parent.get(r["parent_name"], 0) \
                    + r["population"]["value"]
        for r in provinces:
            self.assertEqual(by_parent[r["name"]], r["population"]["value"], r["name"])


class PhilippinePolygons(unittest.TestCase):
    """Maguindanao and Cotabato fit no province; the ARMM takes its 2020 count (rollups-19, 20)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {r["name"]: r for r in processed("philippines_age.json")}

    def test_the_armm_and_soccsksargen_carry_2020_with_the_arithmetic(self):
        armm = self.rows["ARMM"]
        self.assertEqual((armm["population"]["value"], armm["population"]["year"]),
                         (4_404_288, 2020))
        self.assertIn("3,062,109", armm["population_note"])
        self.assertIn("1,342,179", armm["population_note"])
        socc = self.rows["Soccsksargen"]
        self.assertEqual(socc["population"]["value"], 4_901_486)
        self.assertIn("2,556,816", socc["population_note"])
        self.assertIn("2,344,670", socc["population_note"])
        self.assertNotIn("third of Cotabato", socc["population_note"])

    def test_the_two_polygons_state_their_gaps(self):
        for name in ("Maguindanao", "Cotabato"):
            rec = self.rows[name]
            self.assertNotIn("value", rec["population"])
            self.assertIn("No census figure fits this polygon", rec["population"]["note"])
            self.assertIsInstance(rec["population"]["displaces_before"], int)
            for field in ("religion", "ethnicity", "language"):
                self.assertIs(rec[field]["not_this_ground"], True, (name, field))


# --------------------------------------------------------------------------
# Country populations
# --------------------------------------------------------------------------

class CountryCounts(unittest.TestCase):
    """The curated rows are each figure as its source or reader holds it (rollups-12..16, 58, 64)."""

    def test_values_match_the_readers_national_totals(self):
        from scripts.fetch_census import (kuwait_census, microstates, moldova_age,
                                          paraguay_census, turkmenistan_census)
        self.assertEqual(curated("TKM", "population")["value"], turkmenistan_census.NATIONAL)
        self.assertEqual(curated("KWT", "population")["value"], kuwait_census.NATIONAL)
        self.assertEqual(curated("PRY", "population")["value"], paraguay_census.NATIONAL)
        self.assertEqual(curated("MDA", "population")["value"], moldova_age.NATIONAL)
        self.assertEqual(curated("MCO", "population")["value"], microstates.MCO_TOTAL)
        depts = [r for r in processed("guatemala_census.json") if r["level"] == "admin1"]
        self.assertEqual(curated("GTM", "population")["value"],
                         sum(r["population"]["value"] for r in depts))

    def test_values_match_the_first_level_they_stand_over(self):
        for iso3, value in (("OMN", 5_165_602), ("XKX", 1_602_515)):
            path = SITE / "admin1" / f"{iso3}.units.json"
            if not path.exists():
                raise unittest.SkipTest("site/data has not been built")
            units = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sum(u["population"]["value"] for u in units), value, iso3)
            self.assertEqual(curated(iso3, "population")["value"], value)

    def test_the_maldives_note_adds_up(self):
        row = curated("MDV", "population")
        self.assertEqual(row["value"], 211_908 + 303_224)
        self.assertEqual(214_582 + 211_908 + 79_465 + 9_177, row["value"])
        for figure in ("214,582", "211,908", "79,465", "9,177"):
            self.assertIn(figure, row["note"])

    def test_monaco_takes_its_census_age_and_sex(self):
        self.assertEqual(curated("MCO", "median_age")["value"], 50.0)
        self.assertEqual(curated("MCO", "sex_ratio")["value"], 969)

    def test_note_only_rows_leave_the_figure(self):
        for iso3 in ("BTN", "LAO", "UKR"):
            row = curated(iso3, "population")
            self.assertLessEqual(set(row), be.NOTE_ONLY, iso3)
        self.assertIn("18.6% below", curated("BTN", "population")["note"])
        self.assertIn("7,631,798", curated("LAO", "population")["note"])

    def test_visitor_notes_name_no_files_or_code(self):
        rows = json.loads(CURATED.read_text(encoding="utf-8"))["rows"]
        for row in rows:
            if row["country"] in ("TKM", "KWT", "OMN", "MDV", "PRY", "GTM", "XKX", "MCO",
                                  "MDA", "GEO", "BTN", "LAO", "UKR") and \
                    row["field"] in ("population", "median_age", "sex_ratio"):
                for bad in (".json", ".py", "adapter", "build", "SUPERSEDED", "cod-ps"):
                    self.assertNotIn(bad, row["note"], (row["country"], bad))


# --------------------------------------------------------------------------
# The reconcile pass
# --------------------------------------------------------------------------

OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-xyz), reference year 2022"


class RestateEncyclopaediaParents(unittest.TestCase):
    """An encyclopaedia's parent gives way to one source's newer divisions (rollups-21, 29, 34-50, 63)."""

    def tables(self, parent, kids, iso3="XYZ"):
        return {iso3: [parent]}, {iso3: kids}

    def kids(self, year=2022, source=OCHA, values=(600, 500)):
        return [unit(f"K{i}", f"Kid {i}", v, year, source, parent="P")
                for i, v in enumerate(values)]

    def test_an_older_wikidata_figure_takes_the_sum_and_names_what_it_replaced(self):
        parent = unit("P", "Parent", 800, 2011)
        parent["sources"] = [{"field": "population", "name": "Wikidata"},
                             {"field": "population/capital/coordinates", "name": "Wikidata"}]
        kids = self.kids()
        kids[0]["sources"] = [{"field": "population", "name": OCHA, "url": "u"}]
        a1, a2 = self.tables(parent, kids)
        done = be.restate_encyclopaedia_parents(a1, a2)
        self.assertEqual(len(done), 1)
        self.assertEqual(parent["population"], {"value": 1100, "year": 2022,
                                                "source": "summed from 2 second-level divisions"})
        note = parent["population_note"]
        self.assertIn("all 2 divisions", note)
        self.assertIn("OCHA's common operational dataset", note)
        self.assertIn("It replaces 800 for 2011, an older figure from Wikidata.", note)
        self.assertEqual([s["field"] for s in parent["sources"]],
                         ["population/capital/coordinates", "population"])

    def test_an_undated_wikipedia_figure_gives_way_too(self):
        parent = unit("P", "Parent", 5000, None, "English Wikipedia, Parent (infobox)")
        a1, a2 = self.tables(parent, self.kids(2001))
        be.restate_encyclopaedia_parents(a1, a2)
        self.assertEqual(parent["population"]["value"], 1100)
        self.assertIn("which gives no year for it", parent["population_note"])

    def test_what_stays(self):
        cases = {
            "a count": (unit("P", "Parent", 800, 2011, "INE census"), self.kids()),
            "older divisions": (unit("P", "Parent", 800, 2023), self.kids(2022)),
            "same year": (unit("P", "Parent", 800, 2022), self.kids(2022)),
            "mixed years": (unit("P", "Parent", 800, 2011),
                            self.kids()[:1] + self.kids(2020)[1:]),
            "mixed sources": (unit("P", "Parent", 800, 2011),
                              self.kids()[:1] + self.kids(source="Other")[1:]),
            "encyclopaedic divisions": (unit("P", "Parent", 800, 2011),
                                        self.kids(source="Wikidata (CC0)")),
            "a division without a figure": (unit("P", "Parent", 800, 2011),
                                             self.kids() + [unit("K9", "Kid 9", parent="P")]),
            "one division": (unit("P", "Parent", 800, 2011), self.kids(values=(1100,))),
        }
        for case, (parent, kids) in cases.items():
            a1, a2 = self.tables(parent, kids)
            self.assertEqual(be.restate_encyclopaedia_parents(a1, a2), [], case)
            self.assertEqual(parent["population"]["value"], 800, case)

    def test_water_does_not_count_and_kept_countries_keep(self):
        parent = unit("P", "Parent", 800, 2011)
        kids = self.kids() + [unit("L", "Lake", parent="P", water=True)]
        a1, a2 = self.tables(parent, kids)
        self.assertEqual(len(be.restate_encyclopaedia_parents(a1, a2)), 1)
        parent = unit("P", "Parent", 800, 2011)
        a1, a2 = self.tables(parent, self.kids(), iso3="ZWE")
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2), [])

    def test_a_count_that_takes_in_undrawn_ground_keeps_it(self):
        parent = unit("P", "Temotu", 800, 2011)
        a1, a2 = self.tables(parent, self.kids(), iso3="SLB")
        self.assertIn(("SLB", "Temotu"), be.UNDRAWN_PARTS)
        self.assertEqual(be.restate_encyclopaedia_parents(a1, a2), [])


class NotePopulationGaps(unittest.TestCase):
    """Every disagreement over 15% says what the divisions add up to (rollups-21, 52-57, 59)."""

    def test_a_parent_far_from_its_divisions_says_so_with_the_reason(self):
        parent = unit("P", "Arequipa", 1_656_215, 2025, "Wikidata (CC0)")
        kids = [unit(f"K{i}", f"Kid {i}", v, 2017, "INEI, Censos Nacionales 2017", parent="P")
                for i, v in enumerate((1_000_000, 382_730))]
        said = be.note_population_gaps([], {"PER": [parent]}, {"PER": kids})
        self.assertEqual(len(said), 1)
        note = parent["population_note"]
        self.assertIn("Its 2 divisions drawn on this map add up to 1,382,730 (INEI, 2017), "
                      "17% below this figure", note)
        self.assertIn("their figures are for 2017, 8 years before this one", note)
        self.assertTrue(cr.explained([note], 1_656_215, 1_382_730))

    def test_close_or_explained_parents_are_left_alone(self):
        parent = unit("P", "Close", 1000, 2020)
        kids = [unit("K", "Kid", 900, 2020, "X", parent="P")]
        be.note_population_gaps([], {"A": [parent]}, {"A": kids})
        self.assertNotIn("population_note", parent)
        parent = unit("P", "Said", 1000, 2020)
        parent["population_note"] = "Its districts add up to 500."
        kids = [unit("K", "Kid", 500, 2020, "X", parent="P")]
        be.note_population_gaps([], {"A": [parent]}, {"A": kids})
        self.assertEqual(parent["population_note"], "Its districts add up to 500.")

    def test_same_source_same_year_gives_no_invented_reason(self):
        parent = unit("P", "Buenos Aires City", 3_121_707, 2022, "INDEC")
        kids = [unit("K1", "A", 3_000_000, 2022, "INDEC", parent="P"),
                unit("K2", "B", 3_147_121, 2022, "INDEC", parent="P")]
        be.note_population_gaps([], {"ARG": [parent]}, {"ARG": kids})
        self.assertNotIn("place people differently", parent["population_note"])
        self.assertTrue(parent["population_note"].endswith("97% above this figure."))

    def test_a_figure_note_is_kept_in_front_of_the_sentence(self):
        parent = unit("P", "Unit", 1000, 2020)
        parent["population"]["note"] = "The register at the end of 2020."
        kids = [unit("K", "Kid", 500, 2010, "Census", parent="P")]
        be.note_population_gaps([], {"A": [parent]}, {"A": kids})
        self.assertTrue(parent["population_note"].startswith("The register at the end of 2020. "))

    def test_a_country_is_compared_with_its_first_level(self):
        country = {"id": "KEN", "name": "Kenya",
                   "population": {"value": 55_751_717, "year": 2025, "source": "CIA"}}
        regions = [unit("R1", "One", 20_000_000, 2019, "KNBS, census", parent="KEN"),
                   unit("R2", "Two", 27_213_282, 2019, "KNBS, census", parent="KEN")]
        be.note_population_gaps([country], {"KEN": regions}, {})
        self.assertIn("Its 2 first-level divisions drawn on this map add up to 47,213,282 "
                      "(KNBS, 2019), 15% below this figure", country["population_note"])

    def test_a_partial_level_is_not_compared(self):
        parent = unit("P", "Tongatapu", 1000, 2021)
        kids = [unit("K", "Kid", 100, 2021, "X", parent="P")]
        be.note_population_gaps([], {"TON": [parent]}, {"TON": kids})
        self.assertNotIn("population_note", parent)


class CountryNotSummed(unittest.TestCase):
    """A declared refusal reaches the country's own note (rollups-24)."""

    def test_the_reason_is_appended_once(self):
        admin0 = [{"id": "SUR", "religion": [{"group": "Protestant", "pct": 23.6}],
                   "religion_note": "The Factbook's line."},
                  {"id": "EST", "ethnicity": {"status": "not_available", "note": "None."}}]
        said = be.note_country_not_summed(admin0)
        self.assertIn("SUR religion", said)
        self.assertTrue(admin0[0]["religion_note"].startswith("The Factbook's line. Its "
                                                              "first-level divisions are not "
                                                              "added up into this figure: "))
        self.assertIn(be.COUNTRY_NOT_SUMMED[("SUR", "religion")], admin0[0]["religion_note"])
        self.assertIn("register of 2017", admin0[1]["ethnicity"]["note"])
        be.note_country_not_summed(admin0)
        self.assertEqual(admin0[0]["religion_note"].count("are not added up"), 1)


class PolicyParentsSummed(unittest.TestCase):
    """Greece's not-collected first level is summed from its surveyed regions (rollups-23)."""

    def kid(self, name, people, groups):
        return {"name": name, "id": name, "population": {"value": people, "year": 2023},
                "religion": [{"group": g, "pct": round(100 * n / sum(groups.values()), 1),
                              "count": n} for g, n in groups.items()],
                "religion_year": 2023,
                "religion_basis": "survey estimate: self-identification"}

    def test_every_child_measured_is_summed_under_the_policy_sentence(self):
        policy = "Greece's census has not asked religion since 1951."
        parent = {"population": {"value": 1000, "year": 2023},
                  "religion": {"status": "not_collected", "note": policy}}
        kids = [self.kid("A", 600, {"Orthodox": 90, "No religion": 10}),
                self.kid("B", 400, {"Orthodox": 80, "No religion": 20})]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion"))
        self.assertIsInstance(parent["religion"], list)
        self.assertTrue(parent["religion_note"].startswith(policy + " Summed from all 2"))
        self.assertIn("Every division's figure is a survey estimate", parent["religion_note"])

    def test_one_child_without_a_figure_leaves_the_policy_standing(self):
        parent = {"population": {"value": 1000, "year": 2023},
                  "religion": {"status": "not_collected", "note": "Not asked."}}
        kids = [self.kid("A", 600, {"Orthodox": 90}),
                {"name": "B", "id": "B", "population": {"value": 400, "year": 2023},
                 "religion": {"status": "not_collected", "note": "Not asked."}}]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion"))
        self.assertEqual(parent["religion"]["status"], "not_collected")


class StatedPopulationGaps(unittest.TestCase):
    """Antarctica has no permanent population; Abyei is disputed (rollups-60)."""

    def test_antarctica_and_abyei(self):
        reason = {"status": "not_applicable", "note": "Antarctica has no permanent population."}
        admin0 = [{"id": "ATA", "population": reason}]
        ata = unit("A", "Antarctica")
        ata.update(median_age={"status": "not_available"}, sex_ratio={"status": "not_available"})
        abyei = unit("B", "Abyei PCA")
        other = unit("C", "Khartoum")
        said = be.state_population_gaps(admin0, {"ATA": [ata], "SDN": [abyei, other]})
        self.assertEqual(sorted(said), ["ATA Antarctica", "SDN Abyei PCA"])
        self.assertEqual(ata["population"], reason)
        self.assertEqual(ata["median_age"]["status"], "not_applicable")
        self.assertEqual(abyei["population"]["note"], be.DISPUTED_NOTE)
        self.assertNotIn("note", other["population"])

    def test_a_gap_that_already_says_why_is_kept(self):
        abyei = unit("B", "Abyei PCA")
        abyei["population"]["note"] = "Its own reason."
        be.state_population_gaps([], {"SDN": [abyei]})
        self.assertEqual(abyei["population"]["note"], "Its own reason.")


class OneSexRatioUnit(unittest.TestCase):
    """Every level's sex ratio in males per 100 females (rollups-66)."""

    def test_conversions_and_notes(self):
        rows = [
            {"id": "a", "sex_ratio": {"value": 1017, "unit": "males_per_1000_females"},
             "sex_ratio_note": "Males per 1,000 females in OCHA's table."},
            {"id": "b", "sex_ratio": {"value": 968, "unit": "females_per_1000_males"},
             "sex_ratio_note": "Females per 1,000 males, derived from the columns."},
            {"id": "c", "sex_ratio": {"value": 706, "unit": "females_per_1000_males"},
             "sex_ratio_note": "706 females per 1,000 males against 943 for India."},
            {"id": "d", "sex_ratio": {"value": 98.5, "unit": "males_per_100_females"}},
            {"id": "e", "sex_ratio": {"value": 1100, "unit": "males_per_1000_females"},
             "sex_ratio_note": "Men per thousand women, Table 5.1."},
            {"id": "f", "sex_ratio": {"status": "not_available"}},
        ]
        self.assertEqual(be.one_sex_ratio_unit(rows, {"X": []}), 4)
        self.assertEqual(rows[0]["sex_ratio"]["value"], 101.7)
        self.assertEqual(rows[0]["sex_ratio_note"], "Males per 100 females in OCHA's table.")
        self.assertEqual(rows[1]["sex_ratio"]["value"], 103.3)
        self.assertTrue(rows[1]["sex_ratio_note"].startswith("Males per 100 females, derived"))
        self.assertEqual(rows[2]["sex_ratio"]["value"], 141.6)
        self.assertIn("706 females per 1,000 males", rows[2]["sex_ratio_note"])
        self.assertEqual(rows[3]["sex_ratio"]["value"], 98.5)
        self.assertEqual(rows[4]["sex_ratio_note"], "Men per hundred women, Table 5.1.")
        for row in rows[:5]:
            self.assertEqual(row["sex_ratio"]["unit"], "males_per_100_females")

    def test_an_unknown_unit_stops_the_build(self):
        with self.assertRaises(SystemExit):
            be.one_sex_ratio_unit([{"id": "x", "sex_ratio": {"value": 5, "unit": "per_mille"}}])


class BahamasGroups(unittest.TestCase):
    """The seven districts the 2022 census prints in groups say so (rollups-61)."""

    def test_the_grouped_districts_are_declared(self):
        from scripts.fetch_census import wiki_table_population as wt
        self.assertEqual({name for _iso, name in wt.GROUPED},
                         {"Black Point", "Central Abaco", "Central Eleuthera", "Mangrove Cay",
                          "Moore's Island", "South Abaco", "South Eleuthera"})

    def test_the_written_gaps_name_their_group(self):
        rows = {r["name"]: r for r in processed("wiki_table_population.json")
                if r["id"].startswith("BHS")}
        for name in ("Black Point", "Central Abaco", "Central Eleuthera", "Mangrove Cay",
                     "Moore's Island", "South Abaco", "South Eleuthera"):
            pop = rows[name]["population"]
            self.assertNotIn("value", pop, name)
            self.assertTrue(pop["note"].startswith(f"The 2022 census prints {name} together "
                                                   f"with"), name)
            self.assertNotIn("Wikidata", pop["note"])
        self.assertIn("6,530 people", rows["South Abaco"]["population"]["note"])


# --------------------------------------------------------------------------
# scripts/check_rollups.py
# --------------------------------------------------------------------------

class CheckRollups(unittest.TestCase):
    def site(self, tmp, admin1_note=None):
        root = Path(tmp)
        (root / "admin1").mkdir()
        (root / "admin2").mkdir()
        country = {"id": "XYZ", "population": {"value": 100_000, "year": 2025}}
        parent = unit("P", "Parent", 1_000, 2020)
        if admin1_note:
            parent["population_note"] = admin1_note
        sibling = unit("Q", "Close", 99_000, 2020)
        kids = [unit("K1", "Kid", 400, 2010, "Census", parent="P"),
                unit("K2", "Kid", 300, 2010, "Census", parent="P"),
                unit("K3", "Lake", parent="P", water=True),
                unit("K4", "Kid", 99_100, 2010, "Census", parent="Q")]
        (root / "admin0.json").write_text(json.dumps([country]))
        (root / "admin1" / "XYZ.units.json").write_text(json.dumps([parent, sibling]))
        (root / "admin2" / "XYZ.units.json").write_text(json.dumps(kids))
        (root / "build.json").write_text(json.dumps({"partial_levels": [],
                                                     "rollup_gap": cr.GAP}))
        return root

    def test_an_unexplained_gap_is_found_and_a_named_total_explains_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = cr.disagreements(self.site(tmp))
            self.assertEqual([(d["level"], d["id"], d["sum"]) for d in found],
                             [("admin1", "P", 700.0)])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cr.disagreements(self.site(tmp, "They add up to 700.")), [])
        with tempfile.TemporaryDirectory() as tmp:
            # the difference named is as good as the total
            self.assertEqual(cr.disagreements(self.site(tmp, "It leaves 300 undrawn.")), [])

    def test_the_allowlist_excuses_a_known_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.site(tmp)
            self.assertEqual(cr.unexplained(root, {("admin1", "P"): "known"}), [])
            self.assertEqual(len(cr.unexplained(root, {})), 1)
            self.assertEqual(quiet(cr.main, ["--data", str(root)]), 1)

    def test_the_allowlist_file_gives_a_reason_for_every_row(self):
        rows = json.loads(cr.ALLOWLIST.read_text(encoding="utf-8"))["gaps"]
        for row in rows:
            self.assertTrue(row.get("reason"), row)
            self.assertIn(row["level"], ("admin0", "admin1"))

    def test_the_build_writes_the_sentence_the_check_accepts(self):
        summed = cr.complete_sum([unit("K", "Kid", 52_871, 2020, "X")])
        sentence = cr.gap_sentence(summed, 1_000, 2020)
        self.assertTrue(cr.explained([sentence], 1_000, summed["total"]))

    def test_site_data_has_no_unexplained_gap(self):
        build = SITE / "build.json"
        if not build.exists():
            raise unittest.SkipTest("site/data has not been built")
        if "rollup_gap" not in json.loads(build.read_text(encoding="utf-8")):
            raise unittest.SkipTest("site/data was built before parents said what their "
                                    "divisions add up to; rebuild it to run this check")
        left = cr.unexplained()
        self.assertEqual(left, [], "\n".join(
            f"{d['iso3']} {d['level']} {d['name']}: {d['sum']:,.0f} against {d['own']:,.0f}"
            for d in left[:20]))


if __name__ == "__main__":
    unittest.main()
