"""Wikidata fetch: a thin answer must not overwrite a full one.

Wikidata's SPARQL endpoint rate-limits and times out under load, and a timeout
looks exactly like a country with no units. Both of the guards here exist
because a New Zealand run reported "query failed after 4 retries" and then
wrote an empty file over the top.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_wikidata as fw  # noqa: E402


class Coverage(unittest.TestCase):
    def test_country_is_read_from_either_field(self):
        got = fw.countries_in([{"country": "NPL"}, {"id": "NZL-047"}])
        self.assertEqual(got, {"NPL", "NZL"})

    def test_an_empty_set_covers_nothing(self):
        self.assertEqual(fw.countries_in([]), set())

    def test_rows_with_neither_field_are_ignored(self):
        self.assertEqual(fw.countries_in([{"name": "somewhere"}]), set())

    def test_coverage_not_row_count_is_what_matters(self):
        # A country legitimately gains and loses units between rounds, so the
        # guard compares which countries were answered for, not how many rows
        # came back.
        many = [{"country": "IND"} for _ in range(500)]
        one = [{"country": "IND"}]
        self.assertEqual(fw.countries_in(many), fw.countries_in(one))


class ShrinkGuard(unittest.TestCase):
    """The condition the writer checks before replacing an existing file."""

    def dropped(self, existing, new):
        return fw.countries_in(existing) - fw.countries_in(new)

    def test_losing_a_country_is_caught(self):
        existing = [{"country": "NPL"}, {"country": "NZL"}, {"country": "IND"}]
        self.assertEqual(self.dropped(existing, [{"country": "NPL"}]),
                         {"NZL", "IND"})

    def test_the_same_countries_are_not_a_shrink(self):
        rows = [{"country": "NPL"}, {"country": "NZL"}]
        self.assertEqual(self.dropped(rows, rows), set())

    def test_gaining_a_country_is_not_a_shrink(self):
        self.assertEqual(
            self.dropped([{"country": "NPL"}],
                         [{"country": "NPL"}, {"country": "NZL"}]),
            set())

    def test_writing_over_nothing_is_never_a_shrink(self):
        self.assertEqual(self.dropped([], [{"country": "NPL"}]), set())


if __name__ == "__main__":
    unittest.main()
