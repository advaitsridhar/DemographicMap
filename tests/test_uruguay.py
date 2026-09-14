"""Uruguay's second administrative level is a partial one, and says so.

geoBoundaries CGAZ draws 124 second-order units for Uruguay -- its municipios --
and they cover 36.8% of the country. The other 63.2% is inside no municipio,
because a municipio is constituted around a population centre rather than carved
out of the map, and the map draws ground that is in no unit with the background
colour, which is the sea.

That looked like a build failure and was not one. The shapes are in the tiles,
their ids match the attribute file, and every parent resolves to a real
department; what was missing was any statement that the level is an overlay
rather than a tiling. These tests hold the statement to the boundary file, so
the specific figures a reader is shown cannot drift away from what is drawn.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402


def shape(group: str, level: str, area: float = 1.0) -> dict:
    """The shape of a row read_shapes produces, with only the fields used here."""
    return {
        "shape_id": f"{group}-{level}-{area}",
        "name": f"{group} {level}",
        "group": group,
        "point": [0.0, 0.0],
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "_geom": None,
        "area": area,
    }


class PartialLevelDeclaration(unittest.TestCase):
    def test_uruguay_admin2_is_declared_partial(self):
        self.assertIn(("URY", "admin2"), be.PARTIAL_LEVELS)

    def test_the_note_names_the_reason_and_the_level_that_does_cover(self):
        note = be.PARTIAL_LEVELS[("URY", "admin2")]["note"]
        # The reason, not just the fact: a blank level that says only "blank"
        # reads as an adapter nobody ran.
        self.assertIn("municipio", note)
        # And where the reader should go instead. A gap that does not point at
        # the level that does cover the country leaves them with nothing.
        self.assertIn("19 departments", note)

    def test_the_note_states_no_share_of_any_composition(self):
        # A declaration explains an absence and never states a demographic
        # share -- the rule the Maldives' "100% Islam" was written to prevent.
        note = be.PARTIAL_LEVELS[("URY", "admin2")]["note"]
        self.assertNotIn("%", note.replace("36.8%", "").replace("63.2%", ""))


class NoteAttachment(unittest.TestCase):
    """The declaration reaches the units it is about, and only those."""

    def mark(self, group: str, level: str) -> dict:
        entity = be.blank(shape(group, level), level, "parent")
        be.mark_disputed_or_hint(entity, group)
        return entity

    def test_uruguayan_municipios_carry_it(self):
        self.assertIn("note", self.mark("URY", "admin2"))

    def test_uruguayan_departments_do_not(self):
        # The departments tile the country and have data. Telling their reader
        # the level does not cover Uruguay would be false.
        self.assertNotIn("note", self.mark("URY", "admin1"))

    def test_other_countries_admin2_does_not(self):
        self.assertNotIn("note", self.mark("ARG", "admin2"))

    def test_the_adapter_hint_survives_alongside_it(self):
        # Two different questions -- why the level looks empty, and how this
        # unit would be filled -- and the note must not eat the answer to the
        # second.
        entity = self.mark("URY", "admin2")
        self.assertIn("adapter_hint", entity)
        self.assertIn("URY", entity["adapter_hint"])


class CoverageGuard(unittest.TestCase):
    """The declared figures are re-measured, so they cannot go stale."""

    def shapes(self, adm2_area: float, adm2_units: int) -> dict:
        each = adm2_area / adm2_units
        return {
            "ADM0": [shape("URY", "ADM0", 100.0)],
            "ADM1": [shape("URY", "ADM1", 99.9)],
            "ADM2": [shape("URY", "ADM2", each) for _ in range(adm2_units)],
        }

    def test_matching_boundaries_pass(self):
        be.check_level_coverage(self.shapes(36.8, 124))

    def test_drifted_coverage_stops_the_build(self):
        with self.assertRaises(SystemExit) as caught:
            be.check_level_coverage(self.shapes(80.0, 124))
        self.assertIn("36.8", str(caught.exception))

    def test_a_changed_unit_count_stops_the_build(self):
        with self.assertRaises(SystemExit) as caught:
            be.check_level_coverage(self.shapes(36.8, 130))
        self.assertIn("124", str(caught.exception))

    def test_a_level_that_becomes_a_tiling_stops_the_build(self):
        # The happier drift, and still a lie in front of a reader: if CGAZ ever
        # ships "resto del departamento" polygons, the note must go.
        with self.assertRaises(SystemExit):
            be.check_level_coverage(self.shapes(99.9, 124))

    def test_no_country_outlines_at_all_is_not_a_claim_to_check(self):
        # An empty ADM0 is "the outlines were not read on this run", which is
        # not evidence that a declaration is wrong.
        broken = self.shapes(36.8, 124)
        broken["ADM0"] = []
        be.check_level_coverage(broken)

    def test_a_country_that_loses_its_outline_but_keeps_units_is_caught(self):
        # Outlines were read, and Uruguay is not among them while its 124
        # municipios still are. There is then nothing to measure the coverage
        # against, and the note states a figure no longer derived from anything.
        broken = self.shapes(36.8, 124)
        broken["ADM0"] = [shape("ARG", "ADM0", 100.0)]
        with self.assertRaises(SystemExit) as caught:
            be.check_level_coverage(broken)
        self.assertIn("URY", str(caught.exception))

    def test_a_run_carrying_no_uruguayan_shapes_at_all_is_left_alone(self):
        # A caller passing a subset is not making a claim about Uruguay.
        be.check_level_coverage({
            "ADM0": [shape("ARG", "ADM0", 100.0)],
            "ADM1": [shape("ARG", "ADM1", 98.8)],
            "ADM2": [shape("ARG", "ADM2", 100.0)],
        })

    def test_countries_without_a_declaration_are_unaffected(self):
        be.check_level_coverage({
            "ADM0": [shape("ARG", "ADM0", 100.0)],
            "ADM1": [shape("ARG", "ADM1", 98.8)],
            "ADM2": [shape("ARG", "ADM2", 100.0)],
        })


class UndeclaredPartialLevels(unittest.TestCase):
    """A country that newly becomes partial is reported rather than silent."""

    def test_a_new_partial_level_is_logged_not_raised(self):
        # Logged, because it is a fact about an upstream boundary file that
        # this build cannot fix, and 217 other countries should still be
        # written.
        shapes = {
            "ADM0": [shape("XXX", "ADM0", 100.0)],
            "ADM1": [shape("XXX", "ADM1", 99.0)],
            "ADM2": [shape("XXX", "ADM2", 30.0)],
        }
        messages: list[str] = []
        original = be.log
        be.log = messages.append
        try:
            be.check_level_coverage(shapes)
        finally:
            be.log = original
        self.assertTrue(any("XXX" in m and "sea" in m for m in messages),
                        f"expected a report naming XXX, got {messages}")

    def test_an_ordinary_country_is_not_reported(self):
        shapes = {
            "ADM0": [shape("XXX", "ADM0", 100.0)],
            "ADM1": [shape("XXX", "ADM1", 99.0)],
            "ADM2": [shape("XXX", "ADM2", 98.0)],
        }
        messages: list[str] = []
        original = be.log
        be.log = messages.append
        try:
            be.check_level_coverage(shapes)
        finally:
            be.log = original
        self.assertEqual([], [m for m in messages if "XXX" in m])


class BuiltSiteData(unittest.TestCase):
    """What is on disk now, so a rebuild that drops Uruguay is visible.

    These read the built site data rather than rebuilding it -- the build takes
    thirteen minutes -- so they assert the things that were actually wrong in
    the report and are checkable cheaply: the file exists, it has the units the
    boundary file draws, and every one of them hangs off a real department.
    """

    @classmethod
    def setUpClass(cls):
        import json
        path = ROOT / "site" / "data" / "admin2" / "URY.json"
        if not path.exists():
            raise unittest.SkipTest("site/data/admin2/URY.json is not built")
        cls.records = json.loads(path.read_text())
        cls.admin1 = json.loads((ROOT / "site" / "data" / "admin1" / "URY.json").read_text())

    def test_every_municipio_the_boundary_file_draws_is_present(self):
        self.assertEqual(124, len(self.records))

    def test_every_municipio_hangs_off_a_real_department(self):
        departments = {row["id"] for row in self.admin1}
        orphans = [r["name"] for r in self.records if r["parent"] not in departments]
        self.assertEqual([], orphans)

    def test_none_of_them_is_filed_under_the_country(self):
        # The failure mode that hides a unit completely: a parent that is the
        # ISO3 rather than a department id.
        self.assertEqual([], [r["name"] for r in self.records if r["parent"] == "URY"])


if __name__ == "__main__":
    unittest.main()
