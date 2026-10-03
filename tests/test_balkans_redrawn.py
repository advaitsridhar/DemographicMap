"""A Balkan reader sees the map as redrawn, whether or not the site is rebuilt."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.fetch_census import balkans_common


class RedrawnAway(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "admin2_redrawn.geojson").write_text(json.dumps({
            "type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": None, "properties": {
                    "shapeID": "keep", "shapeGroup": "HRV", "replaces": ["keep", "b", "c"]}},
                {"type": "Feature", "geometry": None, "properties": {
                    "shapeID": "x-1", "shapeGroup": "BOL", "replaces": ["x"]}},
            ]}))
        self.patch = mock.patch("scripts.fetch_census._shared.PROCESSED", root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_a_merge_keeps_its_first_feature_and_drops_the_rest(self):
        self.assertEqual(balkans_common.redrawn_away("HRV"), {"b", "c"})

    def test_another_countrys_redraw_is_not_this_ones(self):
        self.assertEqual(balkans_common.redrawn_away("ROU"), set())

    def test_second_level_shapes_leave_the_replaced_out(self):
        units = [{"id": "keep", "name": "Opicina Pirovac"},
                 {"id": "b", "name": "Opicina Muter-Kornati"},
                 {"id": "c", "name": "Otok Kornat"}, {"id": "d", "name": "Tisno"}]
        with mock.patch("scripts.fetch_census.balkans_common.read_json",
                        side_effect=lambda path, default=None: (
                            units if str(path).endswith(".units.json")
                            else json.loads(Path(path).read_text()))):
            kept = [u["id"] for u in balkans_common.shapes("HRV", "admin2")]
        self.assertEqual(kept, ["keep", "d"])


if __name__ == "__main__":
    unittest.main()
