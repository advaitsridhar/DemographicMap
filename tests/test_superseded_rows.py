"""build_entities.load_adapters drops a file's rows for a country another file counts.

OCHA's 2023 projections for the Solomon Islands' constituencies stood in front
of the 2019 census's counts under the year rule. They give way to
solomon_census.json -- but only once that file is registered and has rows, so
the constituencies are never left with nothing. No network.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities  # noqa: E402

COD_PS = [{"id": "SLB-CODPS-SB010101", "name": "South Choiseul", "level": "admin2",
           "country": "SLB", "population": {"value": 10336, "year": 2023}},
          {"id": "FJI-CODPS-FJ0101", "name": "Ba", "level": "admin2", "country": "FJI",
           "population": {"value": 247685, "year": 2017}}]
CENSUS = [{"id": "SLB-CENSUS-SOUTHCHOISEUL", "name": "South Choiseul", "level": "admin2",
           "country": "SLB", "population": {"value": 9688, "year": 2019}}]


class SupersededRows(unittest.TestCase):
    def load(self, files, written):
        with tempfile.TemporaryDirectory() as tmp:
            for name, rows in written.items():
                (Path(tmp) / name).write_text(json.dumps(rows))
            with mock.patch.object(build_entities, "PROCESSED", Path(tmp)), \
                    mock.patch.object(build_entities, "ADAPTER_FILES", files):
                return build_entities.load_adapters()

    def test_the_projection_gives_way_to_the_registered_census(self):
        got = self.load(["cod_ps_admin2.json", "solomon_census.json"],
                        {"cod_ps_admin2.json": COD_PS, "solomon_census.json": CENSUS})
        self.assertEqual([r["_source"] for r in got["SLB"]], ["solomon_census.json"])
        self.assertEqual([r["_source"] for r in got["FJI"]], ["cod_ps_admin2.json"])

    def test_without_the_census_registered_the_projection_stays(self):
        got = self.load(["cod_ps_admin2.json"],
                        {"cod_ps_admin2.json": COD_PS, "solomon_census.json": CENSUS})
        self.assertEqual([r["_source"] for r in got["SLB"]], ["cod_ps_admin2.json"])

    def test_a_registered_census_with_no_rows_keeps_the_projection(self):
        got = self.load(["cod_ps_admin2.json", "solomon_census.json"],
                        {"cod_ps_admin2.json": COD_PS})
        self.assertEqual([r["_source"] for r in got["SLB"]], ["cod_ps_admin2.json"])


if __name__ == "__main__":
    unittest.main()
