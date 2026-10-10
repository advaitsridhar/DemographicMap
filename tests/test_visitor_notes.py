"""What a reader of the map is told: notes that say what a figure counts, and
reasons for a gap that are about that gap. No network, no build."""

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402

SITE = ROOT / "site" / "data"
CURATED = ROOT / "data" / "curated" / "admin0_detail.json"


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


class CountryFiguresThatCountOtherGround(unittest.TestCase):
    """Israel's national figures count East Jerusalem and the Golan, which the
    map draws outside its shape; Antarctica has no permanent population."""

    def rows(self):
        return [r for r in json.loads(CURATED.read_text())["rows"]
                if r["country"] in ("ISR", "ATA")]

    def test_israel_s_rows_say_what_the_figures_count(self):
        rows = {(r["country"], r["field"]): r for r in self.rows()}
        for field in ("population", "religion", "ethnicity"):
            note = rows[("ISR", field)]["note"]
            self.assertIn("East Jerusalem", note, field)
            self.assertIn("Golan", note, field)
            self.assertLessEqual(set(rows[("ISR", field)]), be.NOTE_ONLY)

    def test_a_note_only_row_leaves_the_figure_and_says_what_it_counts(self):
        israel = {"id": "ISR", "population": {"value": 9_402_617, "year": 2024,
                                              "source": "CIA World Factbook"}}
        antarctica = {"id": "ATA", "population": {"status": "not_available"}}
        counted = quiet(be.apply_country_figures, [israel, antarctica],
                        {"ISR": [r for r in self.rows() if r["country"] == "ISR"],
                         "ATA": [r for r in self.rows() if r["country"] == "ATA"]})
        self.assertEqual(counted, set())
        self.assertEqual(israel["population"]["value"], 9_402_617)
        self.assertIn("East Jerusalem", israel["population_note"])
        self.assertEqual(antarctica["population"]["status"], "not_applicable")
        self.assertIn("no permanent population", antarctica["population"]["note"])
        self.assertNotIn("population_note", antarctica)

    def test_a_row_with_a_value_still_needs_a_year_and_a_source(self):
        with self.assertRaises(SystemExit):
            quiet(be.apply_country_figures, [{"id": "ISR"}],
                  {"ISR": [{"country": "ISR", "field": "population", "value": 1,
                            "note": "x"}]})


class DisputedOutlines(unittest.TestCase):
    def test_each_declared_outline_is_drawn(self):
        if not (SITE / "admin0.json").exists():
            raise unittest.SkipTest("site/data has not been built")
        records = json.loads((SITE / "admin0.json").read_text())
        disputed = {r["name"] for r in records if r.get("disputed")}
        for iso3, name in be.DRAWN_AS_DISPUTED.items():
            self.assertIn(name, disputed, iso3)
            self.assertTrue(any(r["id"] == iso3 for r in records), iso3)


class PerFieldReasons(unittest.TestCase):
    """Egypt's religion reason is not its language's or ethnicity's."""

    def unit(self, level):
        return {"id": "E1", "name": "Abnub", "country": "EGY", "level": level,
                "religion": {"status": "not_available"},
                "language": {"status": "not_available"},
                "ethnicity": {"status": "not_available"}}

    def test_each_field_says_its_own_reason(self):
        for level in ("admin1", "admin2"):
            e = self.unit(level)
            be.mark_disputed_or_hint(e, "EGY")
            self.assertNotIn("gap_reason", e)
            be.say_why_empty(e, "Egypt")
            self.assertIn("CAPMAS collected religion", e["religion"]["note"])
            for field in ("language", "ethnicity"):
                self.assertNotIn("religion", e[field]["note"], (level, field))
                self.assertIn(field, e[field]["note"], (level, field))
        self.assertIn("not among them", self.said("admin1"))
        self.assertNotIn("not among them", self.said("admin2"))

    def said(self, level):
        e = self.unit(level)
        be.say_why_empty(e, "Egypt")
        return e["religion"]["note"]

    def test_iran_s_language_reason_carries_no_religion(self):
        e = {"id": "I1", "name": "Ardal", "country": "IRN", "level": "admin2",
             "language": {"status": "not_available"}}
        be.mark_disputed_or_hint(e, "IRN")
        be.say_why_empty(e, "Iran")
        self.assertNotIn("Religion", e["language"]["note"])
        self.assertNotIn("nothing to fetch", e["language"]["note"])
        self.assertIn("no Iranian census has ever asked it", e["language"]["note"])
        self.assertNotIn("nothing to fetch", be.ADAPTER_GAPS["IRN"])

    def test_a_note_already_there_is_kept(self):
        e = self.unit("admin1")
        e["language"] = {"status": "not_collected", "note": "Afrobarometer coded one value."}
        be.say_why_empty(e, "Egypt")
        self.assertEqual(e["language"]["note"], "Afrobarometer coded one value.")


class UndrawnParts(unittest.TestCase):
    def test_a_first_level_count_says_which_unit_it_takes_in(self):
        jeolla = {"id": "J", "name": "South Jeolla", "population": {"value": 1_853_327}}
        temotu = {"id": "T", "name": "Temotu", "population": {"value": 22_319},
                  "population_note": "Total population, 2019 Census (Basic Tables, P2.2)."}
        kids_k = [{"id": f"k{i}", "parent": "J", "population": {"value": v}}
                  for i, v in enumerate((900_000, 900_456))]
        kids_s = [{"id": "s1", "parent": "T", "population": {"value": 10_000}},
                  {"id": "s2", "parent": "T", "population": {"value": 6_924}}]
        said = be.note_undrawn_parts({"KOR": [jeolla], "SLB": [temotu]},
                                     {"KOR": kids_k, "SLB": kids_s})
        self.assertEqual(len(said), 2)
        self.assertIn("Yeonggwang-gun", jeolla["population_note"])
        self.assertIn("add up to 1,800,456, which leaves 52,871", jeolla["population_note"])
        self.assertTrue(temotu["population_note"].startswith("Total population, 2019 Census"))
        self.assertIn("leaves 5,395 for Temotu Pele", temotu["population_note"])

    def test_nothing_is_said_where_a_division_has_no_figure(self):
        jeolla = {"id": "J", "name": "South Jeolla", "population": {"value": 1_853_327}}
        kids = [{"id": "k", "parent": "J", "population": {"status": "not_available"}}]
        temotu = {"id": "T", "name": "Temotu", "population": {"value": 22_319}}
        be.note_undrawn_parts({"KOR": [jeolla], "SLB": [temotu]}, {"KOR": kids})
        self.assertNotIn("population_note", jeolla)


class PlainWording(unittest.TestCase):
    def test_pipeline_wording_is_put_plainly(self):
        record = {
            "sources": [{"license": "Creative Commons Attribution Share-Alike (CC BY-SA) "
                                    "-- license_id='cc-by-sa', isopen=True"}],
            "language_note": "Methodology as the publisher states it: Census; "
                             "representivity very_high. Licence: Creative Commons "
                             "Attribution Share-Alike (CC BY-SA) -- license_id='cc-by-sa', "
                             "isopen=True.",
            "ethnicity": {"status": "not_available",
                          "note": "no table of it by regency could be retrieved: BPS answers "
                                  "automated requests with HTTP 403 on every bps.go.id host, "
                                  "and its 2010 census site serves one page."},
            "religion_note": "A person answers once. Bound to this boundary shape by the "
                             "shape's own id rather than by its name. geoBoundaries draws "
                             "Nepal's map.",
            "url": "https://example.org/?license_id='x', isopen=True",
        }
        self.assertEqual(be.plain_record(record), 4)
        text = json.dumps(record)
        for word in ("license_id", "representivity", "HTTP 403", "automated",
                     "Bound to this boundary shape"):
            self.assertNotIn(word, text.replace(record["url"], ""), word)
        self.assertEqual(record["sources"][0]["license"],
                         "Creative Commons Attribution Share-Alike (CC BY-SA)")
        self.assertIn("representativeness rated very high", record["language_note"])
        self.assertIn("BPS's own websites could not be read", record["ethnicity"]["note"])
        self.assertEqual(record["religion_note"],
                         "A person answers once. geoBoundaries draws Nepal's map.")
        self.assertIn("isopen", record["url"])     # not a visitor's text

    def test_thailand_s_reason_names_no_reader(self):
        self.assertNotIn("automated", be.ADAPTER_GAPS["THA"])
        self.assertIn("modelled", be.ADAPTER_GAPS["THA"])


if __name__ == "__main__":
    unittest.main()
