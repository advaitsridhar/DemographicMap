"""build_entities.load_adapters drops OCHA's Afghan district rows for the office's own.

cod-ps-afg (reference year 2026) stood in front of the statistics office's
1396 estimates under the year rule on about 266 districts, so a province's
districts added up to neither total. Its Afghan rows give way to
afghanistan_estimates.json -- but only once that file is registered and has
rows, so no district is left with nothing. No network.
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

COD_PS = [{"id": "AFG-CODPS-AF0101", "name": "Kabul", "level": "admin2", "country": "AFG",
           "population": {"value": 5_869_000, "year": 2026}},
          {"id": "PAK-CODPS-PK0101", "name": "Attock", "level": "admin2", "country": "PAK",
           "population": {"value": 2_170_000, "year": 2023}}]
ESTIMATES = [{"id": "AFG-1396-0101", "name": "Kabul", "level": "admin2", "country": "AFG",
              "population": {"value": 4_273_156, "year": 2017}}]


class SupersededAfghanRows(unittest.TestCase):
    def load(self, files, written):
        with tempfile.TemporaryDirectory() as tmp:
            for name, rows in written.items():
                (Path(tmp) / name).write_text(json.dumps(rows))
            with mock.patch.object(build_entities, "PROCESSED", Path(tmp)), \
                    mock.patch.object(build_entities, "ADAPTER_FILES", files):
                return build_entities.load_adapters()

    def test_ochas_afghan_rows_give_way_to_the_offices_estimates(self):
        got = self.load(["cod_ps_admin2.json", "afghanistan_estimates.json"],
                        {"cod_ps_admin2.json": COD_PS, "afghanistan_estimates.json": ESTIMATES})
        self.assertEqual([r["_source"] for r in got["AFG"]], ["afghanistan_estimates.json"])
        self.assertEqual([r["_source"] for r in got["PAK"]], ["cod_ps_admin2.json"])

    def test_without_the_estimates_registered_ochas_rows_stay(self):
        got = self.load(["cod_ps_admin2.json"],
                        {"cod_ps_admin2.json": COD_PS, "afghanistan_estimates.json": ESTIMATES})
        self.assertEqual([r["_source"] for r in got["AFG"]], ["cod_ps_admin2.json"])

    def test_registered_estimates_with_no_rows_keep_ochas(self):
        got = self.load(["cod_ps_admin2.json", "afghanistan_estimates.json"],
                        {"cod_ps_admin2.json": COD_PS})
        self.assertEqual([r["_source"] for r in got["AFG"]], ["cod_ps_admin2.json"])


if __name__ == "__main__":
    unittest.main()
