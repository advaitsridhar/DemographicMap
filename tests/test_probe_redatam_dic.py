"""The REDATAM dictionary probe: the readable names in a binary dictionary, in order."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.probe_redatam_dic import strings  # noqa: E402


class Strings(unittest.TestCase):
    def test_names_and_latin1_labels_come_out_in_file_order(self):
        blob = b"\x00\x05PERSONA\x00\x01\x02P05\x00Religi\xf3n que profesa\x00ab\x00"
        self.assertEqual(strings(blob), [(2, "PERSONA"), (12, "P05"),
                                         (16, "Religión que profesa")])

    def test_runs_shorter_than_three_are_not_names(self):
        self.assertEqual(strings(b"\x00ab\x00\x01cd\x02"), [])


if __name__ == "__main__":
    unittest.main()
