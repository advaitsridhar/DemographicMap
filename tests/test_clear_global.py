"""CLEAR Global's language files, and the guards on reading them as a composition."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import clear_global as cg  # noqa: E402


def quiet(fn, *args, **kwargs):
    """Run it with its log captured; ``log`` writes to stderr."""
    out = io.StringIO()
    with contextlib.redirect_stderr(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


def row(code, name, language, value, level="1", **extra):
    base = {"location_code": code, "location_name": name,
            "location_level": level, "language_name": language,
            "proportion_value": str(value),
            "datetime_published": "12-31-2009",
            "dataset_name": "Somewhere Census 2009 (IPUMS extract)",
            "source": "IPUMS International",
            "representivity_rating": "very_high"}
    base.update(extra)
    return base


TWO_UNITS = [
    row("A1", "Alpha", "Kirghiz", 0.6), row("A1", "Alpha", "Russian", 0.4),
    row("A2", "Beta", "Kirghiz", 0.9), row("A2", "Beta", "Russian", 0.1),
]

PACKAGE = {
    "name": "somewhere-languages", "title": "Somewhere: Languages",
    "groups": [{"name": "kgz"}],
    "license_id": "cc-by-sa",
    "license_title": "Creative Commons Attribution Share-Alike (CC BY-SA)",
    "isopen": True,
    "methodology": "Census",
    "dataset_date": "[2009-12-31T00:00:00 TO 2009-12-31T23:59:59]",
    "resources": [
        {"name": "clearglobal_language_use_KGZ_admin0.csv", "url": "http://x/0"},
        {"name": "clearglobal_language_use_KGZ_admin1.csv", "url": "http://x/1"},
        {"name": "clearglobal_language_use_KGZ_admin2.csv", "url": "http://x/2"},
    ],
}


def csv_text(rows):
    columns = ["location_code", "location_name", "location_level",
               "language_name", "proportion_value", "datetime_published",
               "dataset_name", "source", "representivity_rating"]
    lines = [",".join(columns)]
    for r in rows:
        lines.append(",".join('"%s"' % r.get(c, "") for c in columns))
    return "\n".join(lines) + "\n"


class Compose(unittest.TestCase):
    def test_shares_are_percentages_of_the_unit(self):
        kept, refused, unnamed = cg.compose(TWO_UNITS)
        self.assertEqual(refused, [])
        self.assertEqual(kept["A1"]["shares"],
                         [{"group": "Kirghiz", "pct": 60.0},
                          {"group": "Russian", "pct": 40.0}])

    def test_only_the_first_level_is_read(self):
        rows = TWO_UNITS + [row("A101", "Alphaville", "Kirghiz", 1.0, level="2")]
        kept, _, _u = cg.compose(rows)
        self.assertEqual(sorted(kept), ["A1", "A2"])

    def test_a_unit_that_does_not_add_to_one_is_dropped_with_its_arithmetic(self):
        rows = TWO_UNITS + [row("A3", "Gamma", "Thai", 0.997),
                            row("A3", "Gamma", "Other", 0.036)]
        kept, refused, unnamed = cg.compose(rows)
        self.assertNotIn("A3", kept)
        self.assertEqual(len(refused), 1)
        self.assertIn("1.033", refused[0])

    def test_a_unit_the_file_cannot_name_is_dropped_but_does_not_condemn_the_file(self):
        """Sudan's fault: two named states and one "sudan: level 1 unknown".

        An unnamed row says the study could not place some respondents, not
        that the table is the wrong shape, so it is dropped and kept out of
        the count that refuses a country's file whole.
        """
        rows = TWO_UNITS + [row("HT01XXX", "west: level 2 unknown", "Haitian", 1.0)]
        kept, refused, unnamed = cg.compose(rows)
        self.assertEqual(sorted(kept), ["A1", "A2"])
        self.assertEqual(refused, [])
        self.assertIn("does not say which unit", unnamed[0])

    def test_one_language_listed_twice_is_added_up_not_overwritten(self):
        rows = [row("A1", "Alpha", "Kirghiz", 0.6), row("A1", "Alpha", "Kirghiz", 0.4)]
        kept, _, _u = cg.compose(rows)
        self.assertEqual(kept["A1"]["shares"], [{"group": "Kirghiz", "pct": 100.0}])

    def test_a_share_that_rounds_to_nothing_is_not_printed_as_a_group(self):
        rows = [row("A1", "Alpha", "Kirghiz", 0.9996),
                row("A1", "Alpha", "Japanese", 0.0004)]
        kept, _, _u = cg.compose(rows)
        self.assertEqual([r["group"] for r in kept["A1"]["shares"]], ["Kirghiz"])


class Catalogue(unittest.TestCase):
    def test_the_licence_is_quoted_and_not_summarised(self):
        terms = cg.licence({"license_id": "hdx-other", "license_title": "Other",
                            "license_other": "humanitarian use only",
                            "isopen": False})
        self.assertIn("humanitarian use only", terms)
        self.assertIn("isopen=False", terms)

    def test_the_first_level_file_is_found_by_name(self):
        self.assertEqual(cg.admin1_resource(PACKAGE)["url"], "http://x/1")

    def test_a_dataset_with_no_first_level_file_has_none(self):
        package = dict(PACKAGE, resources=[
            {"name": "cd_lang_admin2_V01.csv", "url": "http://x/2"}])
        self.assertIsNone(cg.admin1_resource(package))

    def test_the_older_files_version_suffix_does_not_hide_them(self):
        """th_lang_admin1_v01.csv is a first-level file and must be found.

        Not so that it can be read -- it is the wide format and the header
        test refuses it -- but so that the refusal says the true reason. A
        pattern that ended at "admin1" reported "no first-level file on this
        dataset" for Thailand, Colombia, India and the older DRC entry, which
        is not what is wrong with any of them.
        """
        package = dict(PACKAGE, resources=[
            {"name": "th_lang_admin1_v01.csv", "url": "http://x/1"}])
        self.assertEqual(cg.admin1_resource(package)["url"], "http://x/1")

    def test_the_year_comes_from_the_catalogues_range(self):
        self.assertEqual(cg.reference_year(PACKAGE, TWO_UNITS), 2009)

    def test_a_file_that_disagrees_about_the_year_says_so(self):
        rows = [row("A1", "Alpha", "Kirghiz", 1.0, datetime_published="12-31-1997")]
        year, printed = quiet(cg.reference_year, PACKAGE, rows)
        self.assertEqual(year, 2009)
        self.assertIn("1997", printed)


class CountryRecords(unittest.TestCase):
    def setUp(self):
        self._fetch = cg.fetch

    def tearDown(self):
        cg.fetch = self._fetch

    def serve(self, text):
        cg.fetch = lambda url: text

    def test_a_country_is_written_with_its_licence_on_every_record(self):
        self.serve(csv_text(TWO_UNITS))
        records, printed = quiet(cg.country_records, PACKAGE)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["id"], "KGZ-CG-A1")
        self.assertEqual(records[0]["parent"], "KGZ")
        self.assertEqual(records[0]["language_year"], 2009)
        for entry in records[0]["sources"]:
            self.assertIn("Creative Commons Attribution Share-Alike", entry["license"])
        self.assertIn("Somewhere Census 2009", records[0]["language_note"])
        self.assertIn("2 unit(s) written", printed)

    def test_a_wide_format_file_is_refused_on_its_header_not_its_name(self):
        self.serve("adm1_name,Thai,Other\nBangkok,0.997,0.036\n")
        records, printed = quiet(cg.country_records, PACKAGE)
        self.assertEqual(records, [])
        self.assertIn("not the long format", printed)
        self.assertIn("proportion_value", printed)

    def test_a_country_that_says_the_same_thing_everywhere_is_refused(self):
        rows = [row("HT02", "South-East", "Haitian", 1.0),
                row("HT07", "South", "Haitian", 1.0),
                row("HT05", "Artibonite", "Haitian", 1.0)]
        self.serve(csv_text(rows))
        records, printed = quiet(cg.country_records, PACKAGE)
        self.assertEqual(records, [])
        self.assertIn("identical", printed)

    def test_a_file_where_most_units_are_not_a_composition_is_refused_whole(self):
        rows = []
        for n in range(6):
            rows.append(row(f"B{n}", f"Unit {n}", "Thai", 0.99))
            rows.append(row(f"B{n}", f"Unit {n}", "Other", 0.2))
        rows += TWO_UNITS
        self.serve(csv_text(rows))
        records, printed = quiet(cg.country_records, PACKAGE)
        self.assertEqual(records, [])
        self.assertIn("not a composition", printed)

    def test_a_dataset_with_no_iso3_is_refused_rather_than_guessed(self):
        self.serve(csv_text(TWO_UNITS))
        records, printed = quiet(cg.country_records, dict(PACKAGE, groups=[]))
        self.assertEqual(records, [])
        self.assertIn("no ISO3", printed)


class Written(unittest.TestCase):
    """The committed file, where a run has produced one."""

    PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / cg.OUT

    def setUp(self):
        if not self.PATH.exists():
            self.skipTest(f"{self.PATH.name} has not been fetched")
        import json
        self.rows = json.loads(self.PATH.read_text(encoding="utf-8"))

    def test_every_record_carries_a_language_a_year_and_a_licence(self):
        for row_ in self.rows:
            self.assertTrue(row_["language"], row_["id"])
            self.assertIsInstance(row_["language_year"], int, row_["id"])
            self.assertTrue(row_["sources"][0]["license"], row_["id"])

    def test_no_unit_claims_more_than_a_whole_population(self):
        for row_ in self.rows:
            total = sum(r["pct"] for r in row_["language"])
            self.assertLessEqual(total, 100.6, f"{row_['id']}: {total}")

    def test_ids_are_unique(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_country_says_the_same_thing_in_every_unit(self):
        by_country: dict[str, set] = {}
        for row_ in self.rows:
            key = tuple(sorted((r["group"], r["pct"]) for r in row_["language"]))
            by_country.setdefault(row_["parent"], set()).add(key)
        for iso, signatures in by_country.items():
            if len([r for r in self.rows if r["parent"] == iso]) > 1:
                self.assertGreater(len(signatures), 1, iso)


if __name__ == "__main__":
    unittest.main()


class TheBoundaryAliases(unittest.TestCase):
    """Every declared alias must name a shape that exists, and buy something."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        cls.admin1 = cls.root / "site" / "data" / "admin1"

    def shapes(self, iso):
        import json
        path = self.admin1 / f"{iso}.json"
        if not path.exists():
            self.skipTest(f"no built admin1 file for {iso}")
        return {s["name"] for s in json.loads(path.read_text())}

    def test_every_alias_names_a_shape_that_exists(self):
        # The point of declaring a name rather than letting the matcher guess
        # is that a declaration can be checked. An alias naming a shape this
        # repository does not have is a typo that would fail silently: the row
        # would fall back to the prefix pass, which is the behaviour the table
        # exists to stop.
        import unicodedata
        def flat(s):
            s = unicodedata.normalize("NFKD", s)
            return "".join(c for c in s if not unicodedata.combining(c)).lower()
        for iso, table in cg.BOUNDARY_ALIASES.items():
            names = {flat(n) for n in self.shapes(iso)}
            for source_name, shape_name in table.items():
                with self.subTest(iso=iso, name=source_name):
                    self.assertIn(
                        flat(shape_name), names,
                        f"{iso}: {source_name!r} is aliased to {shape_name!r}, "
                        f"which is not a shape in site/data/admin1/{iso}.json")

    def test_no_two_units_of_one_country_are_aliased_to_one_shape(self):
        # Two rows on one shape is the collision the build refuses, and a
        # refusal loses both. Declaring one is a way of asking for that, so it
        # is a mistake in the table rather than a fact about the country.
        for iso, table in cg.BOUNDARY_ALIASES.items():
            targets = list(table.values())
            with self.subTest(iso=iso):
                self.assertEqual(
                    len(targets), len(set(targets)),
                    f"{iso}: two source units are aliased to the same shape")

    def test_an_alias_is_never_the_name_it_already_has(self):
        # An alias equal to the row's own name buys nothing: the exact pass
        # would already have matched it. One here means the table was written
        # against a guess rather than against the boundary file.
        for iso, table in cg.BOUNDARY_ALIASES.items():
            for source_name, shape_name in table.items():
                with self.subTest(iso=iso, name=source_name):
                    self.assertNotEqual(source_name.lower(), shape_name.lower())

    def test_the_written_file_carries_the_aliases_it_declares(self):
        # The table only matters if it reaches the records. This is the test
        # that would have failed while the adapter had the table and the
        # output did not.
        import json
        path = self.root / "data" / "processed" / "clear_global_language.json"
        if not path.exists():
            self.skipTest("clear_global_language.json has not been written")
        records = json.loads(path.read_text())
        declared = sum(len(t) for t in cg.BOUNDARY_ALIASES.values())
        carried = 0
        for rec in records:
            want = cg.BOUNDARY_ALIASES.get(rec["parent"], {}).get(rec["name"])
            if want is not None:
                self.assertEqual(rec.get("aliases"), [want], rec["name"])
                carried += 1
        # Not every declared alias need appear -- a country whose file CLEAR
        # Global refused writes no records at all -- but most must, or the
        # table is describing a file this adapter is not producing.
        self.assertGreater(carried, declared * 0.8,
                           f"only {carried} of {declared} declared aliases "
                           f"reached the written file")
