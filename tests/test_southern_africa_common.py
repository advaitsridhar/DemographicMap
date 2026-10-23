"""The helpers the Southern Africa and Indian Ocean census readers share
(scripts/fetch_census/southern_africa_common)."""

import unittest
from unittest import mock

from scripts.fetch_census import southern_africa_common as sa


class SouthernAfricaCommonTest(unittest.TestCase):
    def test_key_drops_accents_case_and_punctuation(self):
        self.assertEqual(sa.key("Rivière du Rempart"), "rivieredurempart")
        self.assertEqual(sa.key("Qacha's Nek"), "qachasnek")
        self.assertEqual(sa.key(None), "")

    def test_grouped_median_interpolates_in_the_middle_group(self):
        # 100 people: 40 aged 0-4, 40 aged 5-9, 20 aged 10+ (open). The 50th
        # person is a quarter of the way into 5-9.
        self.assertEqual(sa.grouped_median([(0, 5, 40), (5, 5, 40), (10, None, 20)]), 6.2)
        self.assertIsNone(sa.grouped_median([(0, 5, 0)]))
        with self.assertRaises(SystemExit):
            sa.grouped_median([(0, 5, 10), (5, None, 90)])

    def test_sex_ratio_is_men_per_thousand_women(self):
        m = sa.sex_ratio(950, 1000, year=2022, source="x")
        self.assertEqual(m["value"], 950)
        self.assertEqual(m["unit"], "males_per_1000_females")
        self.assertIsNone(sa.sex_ratio(0, 1000, year=2022, source="x"))

    def test_joined(self):
        self.assertEqual(sa.joined(["A"]), "A")
        self.assertEqual(sa.joined(["A", "B"]), "A and B")
        self.assertEqual(sa.joined(["A", "B", "C"]), "A, B and C")

    def test_fetch_falls_back_to_the_archive_and_skips_an_error_page(self):
        calls = []

        def get(url, **_):
            calls.append(url)
            if url.startswith("https://office"):
                raise OSError("refused")
            if "/web/1id_/" in url:
                return b"<html>not found</html>"
            return b"%PDF-1.7 body"

        with mock.patch.object(sa, "http_get", get), mock.patch.object(sa, "log"):
            body, came = sa.fetch("https://office/x.pdf", archive=("1", "2"), expect=b"%PDF")
        self.assertEqual(body, b"%PDF-1.7 body")
        self.assertEqual(came, "https://web.archive.org/web/2id_/https://office/x.pdf")
        self.assertEqual(len(calls), 3)
        with mock.patch.object(sa, "http_get", get), mock.patch.object(sa, "log"), \
                self.assertRaises(SystemExit):
            sa.fetch("https://office/x.pdf", archive=("1",), expect=b"%PDF")


if __name__ == "__main__":
    unittest.main()
