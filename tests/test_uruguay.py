"""Uruguay's second level, and the ground it leaves out.

geoBoundaries CGAZ draws 124 second-order units for Uruguay -- its municipios --
and they cover 36.8% of the country. The other 63.2% is inside no municipio,
because a municipio is constituted around a population centre rather than carved
out of the map. It was first declared a partial level and left blank; since 24
September 2026 each department's remainder is drawn as a unit of its own
(scripts/make_remainders.py) and given its department's count less its
municipios'. The partial-level mechanism is still pinned here, on Tonga, the one
country it still describes.
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


class RemainderDeclaration(unittest.TestCase):
    def test_uruguay_is_drawn_whole_rather_than_declared_partial(self):
        self.assertNotIn(("URY", "admin2"), be.PARTIAL_LEVELS)
        self.assertIn("URY", be.REMAINDERS)

    def test_the_remainder_says_what_it_is(self):
        label, note = be.REMAINDERS["URY"]
        self.assertIn("municipio", label)
        # The reason, not just the fact: a unit named for what it is not.
        self.assertIn("municipio", note)
        # A description of ground, never a demographic share.
        self.assertNotIn("%", note)

    def test_tonga_is_still_declared(self):
        self.assertIn(("TON", "admin2"), be.PARTIAL_LEVELS)


class NoteAttachment(unittest.TestCase):
    """A partial-level declaration reaches the units it is about, and only those."""

    def mark(self, group: str, level: str) -> dict:
        entity = be.blank(shape(group, level), level, "parent")
        be.mark_disputed_or_hint(entity, group)
        return entity

    def test_tongan_districts_carry_it(self):
        self.assertIn("note", self.mark("TON", "admin2"))

    def test_tongan_island_groups_do_not(self):
        self.assertNotIn("note", self.mark("TON", "admin1"))

    def test_uruguayan_municipios_no_longer_do(self):
        self.assertNotIn("note", self.mark("URY", "admin2"))

    def test_other_countries_admin2_does_not(self):
        self.assertNotIn("note", self.mark("ARG", "admin2"))


class CoverageGuard(unittest.TestCase):
    """The declared figures are re-measured, so they cannot go stale."""

    def shapes(self, adm2_area: float, adm2_units: int) -> dict:
        each = adm2_area / adm2_units
        return {
            "ADM0": [shape("TON", "ADM0", 100.0)],
            "ADM1": [shape("TON", "ADM1", 99.9)],
            "ADM2": [shape("TON", "ADM2", each) for _ in range(adm2_units)],
        }

    def test_matching_boundaries_pass(self):
        be.check_level_coverage(self.shapes(67.2, 21))

    def test_drifted_coverage_stops_the_build(self):
        with self.assertRaises(SystemExit) as caught:
            be.check_level_coverage(self.shapes(80.0, 21))
        self.assertIn("67.2", str(caught.exception))

    def test_a_changed_unit_count_stops_the_build(self):
        with self.assertRaises(SystemExit) as caught:
            be.check_level_coverage(self.shapes(67.2, 30))
        self.assertIn("21", str(caught.exception))

    def test_a_level_that_becomes_a_tiling_stops_the_build(self):
        # The happier drift, and still a lie in front of a reader.
        with self.assertRaises(SystemExit):
            be.check_level_coverage(self.shapes(99.9, 21))

    def test_no_country_outlines_at_all_is_not_a_claim_to_check(self):
        broken = self.shapes(67.2, 21)
        broken["ADM0"] = []
        be.check_level_coverage(broken)

    def test_a_country_that_loses_its_outline_but_keeps_units_is_caught(self):
        broken = self.shapes(67.2, 21)
        broken["ADM0"] = [shape("ARG", "ADM0", 100.0)]
        with self.assertRaises(SystemExit) as caught:
            be.check_level_coverage(broken)
        self.assertIn("TON", str(caught.exception))

    def test_a_run_carrying_no_tongan_shapes_at_all_is_left_alone(self):
        be.check_level_coverage({
            "ADM0": [shape("ARG", "ADM0", 100.0)],
            "ADM1": [shape("ARG", "ADM1", 98.8)],
            "ADM2": [shape("ARG", "ADM2", 100.0)],
        })

    def test_uruguay_drawn_whole_is_not_reported(self):
        # With its remainders the second level covers the country again.
        be.check_level_coverage({
            "ADM0": [shape("URY", "ADM0", 100.0)],
            "ADM1": [shape("URY", "ADM1", 99.9)],
            "ADM2": [shape("URY", "ADM2", 36.8), shape("URY", "ADM2", 62.9)],
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
        self.assertEqual(124, len([r for r in self.records if not r.get("remainder")]))

    def test_the_ground_outside_them_is_drawn(self):
        rests = [r for r in self.records if r.get("remainder")]
        if not rests:
            self.skipTest("site data predates the remainders")
        self.assertEqual(15, len(rests))
        self.assertTrue(all("outside any municipio" in r["name"] for r in rests))

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
