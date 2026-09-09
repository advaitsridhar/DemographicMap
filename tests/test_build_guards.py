"""Regression checks for failures that previously produced misleading builds."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class BuildGuards(unittest.TestCase):
    def test_cocos_and_cook_islands_do_not_share_a_code(self):
        import fetch_factbook

        self.assertEqual(fetch_factbook.MANUAL_CODE_ISO["ck"], "CCK")

    def test_secondary_territory_profiles_are_retained(self):
        import build_entities

        rows = [
            {"id": "PSE", "name": "Gaza", "codes": {"iso3": "PSE"}},
            {"id": "PSE-WE", "name": "West Bank", "codes": {"iso3": "PSE"}},
        ]
        primary = build_entities.primary_country_profiles(rows)
        kept = build_entities.geometryless_profiles(rows, primary, {"PSE"})
        self.assertEqual([row["id"] for row in kept], ["PSE-WE"])
        self.assertEqual(kept[0]["codes"]["iso3"], "PSE")

    def test_tile_failure_is_fatal_to_the_pipeline(self):
        source = (ROOT / "scripts" / "build_all.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/build_tiles.sh || exit 1", source)

    def test_tippecanoe_does_not_disable_compression_with_a_value(self):
        source = (ROOT / "scripts" / "build_tiles.sh").read_text(encoding="utf-8")
        self.assertNotIn("--no-tile-compression", source)

    def test_commit_checkbox_is_used_as_a_boolean(self):
        source = (ROOT / ".github" / "workflows" / "run-adapter.yml").read_text(encoding="utf-8")
        self.assertIn("if: always() && inputs.commit\n", source)
        self.assertNotIn("inputs.commit != 'false'", source)

    def test_pmtiles_download_is_pinned_and_fails_on_http_errors(self):
        source = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(encoding="utf-8")
        self.assertIn("PMTILES_VERSION: \"1.31.2\"", source)
        self.assertIn("curl --fail", source)
        self.assertIn("Linux_x86_64.tar.gz", source)


if __name__ == "__main__":
    unittest.main()
