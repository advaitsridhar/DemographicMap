"""The Central Africa probe's own helpers (no network)."""

import unittest

from scripts.fetch_census import central_africa_probe as cap


class Pages(unittest.TestCase):
    def test_page_ranges(self):
        self.assertEqual(cap.pages_of("3-5,9", 20), [3, 4, 5, 9])
        self.assertEqual(cap.pages_of("18-30", 20), [18, 19, 20])
        self.assertEqual(cap.pages_of("0,25", 20), [])

    def test_unknown_mode_is_said(self):
        lines = []
        original = cap.say
        cap.say = lines.append
        try:
            cap.probe("nonsense:https://example.org/")
        finally:
            cap.say = original
        self.assertTrue(any("unknown mode" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
