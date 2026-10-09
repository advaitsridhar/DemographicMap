"""abs.outermost_by_code names a declared child beside its parent.

G13's "Other" (code _O) holds the Australian Indigenous languages (code 8):
the Tiwi Islands' 81% 'Other' was its Indigenous languages. The child is
written under its own name and the parent keeps the rest, so the partition
still sums to the published total. No network.
"""

import unittest

from scripts.fetch_census import abs as abs_adapter

# The Northern Territory's shape: "Other" a fifth of the people, three
# quarters of it Indigenous.
G13 = {("Total", "_T"): 1000, ("Speaks English only", "1"): 720,
       ("Other Languages Total", "O_T"): 230, ("Italian", "3103"): 30,
       ("Other", "_O"): 200, ("Not stated", "_N"): 50,
       ("Australian Indigenous Languages", "8"): 150}


class IndigenousLanguagesOutOfOther(unittest.TestCase):
    def test_the_child_is_named_and_the_parent_keeps_the_rest(self):
        kept, how = abs_adapter.top_level(G13, 1000)
        self.assertEqual(kept["Australian Indigenous Languages"], 150)
        self.assertEqual(kept["Other"], 50)
        self.assertEqual(kept["Speaks English only"], 720)
        self.assertEqual(sum(kept.values()), 1000)
        self.assertTrue(how.startswith("code tree"), how)

    def test_without_the_child_other_is_whole(self):
        coded = {k: v for k, v in G13.items() if k[1] != "8"}
        kept, _ = abs_adapter.top_level(coded, 1000)
        self.assertEqual(kept["Other"], 200)
        self.assertNotIn("Australian Indigenous Languages", kept)

    def test_a_child_of_nobody_is_not_named(self):
        coded = dict(G13)
        coded[("Australian Indigenous Languages", "8")] = 0
        kept, _ = abs_adapter.top_level(coded, 1000)
        self.assertEqual(kept["Other"], 200)
        self.assertNotIn("Australian Indigenous Languages", kept)


if __name__ == "__main__":
    unittest.main()
