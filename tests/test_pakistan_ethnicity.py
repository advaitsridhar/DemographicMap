"""Pakistan's ethnicity field, and the difference between its two silences.

Every Pakistani unit -- seven provinces and territories, and the districts
under them -- used to carry ``{"status": "not_available"}`` with nothing in
it. The map draws that as an empty panel, and an empty panel says "nobody has
run this fetch yet", which for this field is the opposite of true: Pakistan's
census does not ask ethnicity at all.

The two statuses are opposite claims about the state. ``not_available`` says
the question was asked and the answer was not published at this level -- what
Gilgit-Baltistan's religion and language fields say, and true of them.
``not_collected`` says the question was never put. This asserts that Pakistan
gets the second, that every unit gets a reason, and that the reason points the
reader at mother tongue without ever turning mother tongue into ethnicity.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import pakistan as pk  # noqa: E402


def unit(entity_id: str, language=None, ethnicity=None):
    """A record as ``say_ethnicity`` meets it: after ``record()`` has run.

    The shape matters more than it looks. ``record()`` fills an unsupplied
    field with ``gap(NOT_AVAILABLE)``, which is a dict with a ``status`` key
    and no ``note`` -- not ``None``, and not a ``{"value": ...}`` measure. A
    reader that checked the wrong one of those three would report this whole
    country fixed or broken without either being so.
    """
    row = {"id": entity_id, "ethnicity": pk.gap(pk.NOT_AVAILABLE)}
    if language is not None:
        row["language"] = language
    if ethnicity is not None:
        row["ethnicity"] = ethnicity
    return row


class TheQuestionWasNeverPut(unittest.TestCase):
    def test_the_status_is_not_collected_and_not_not_available(self):
        rows = [unit("PAK-punjab")]
        pk.say_ethnicity(rows)
        self.assertEqual(rows[0]["ethnicity"]["status"], pk.NOT_COLLECTED)

    def test_every_unit_gets_a_reason(self):
        rows = [unit(f"PAK-{n}") for n in range(133)]
        self.assertEqual(pk.say_ethnicity(rows), 133)
        self.assertTrue(all(row["ethnicity"].get("note") for row in rows))

    def test_the_reason_cites_the_report_and_what_it_lists(self):
        note = pk.ETHNICITY_GAP
        self.assertIn("National Census Report 2023", note)
        # The eight characteristics the Bureau says the census collected.
        # Ethnicity's absence from that list is the finding; naming the list
        # is what lets a reader check it.
        for field in ("age", "mother tongue", "religion", "disability",
                      "migration", "literacy", "employment", "nationality"):
            self.assertIn(field, note)

    def test_the_reason_rules_out_nationality_in_the_bureaus_words(self):
        self.assertIn("and not as ethnicity", pk.ETHNICITY_GAP)

    def test_the_reason_says_what_scheduled_castes_is_instead(self):
        # Table 9's one caste-shaped column is a category of the religion
        # question. A reader who spots it and concludes Pakistan enumerates
        # caste should find the answer in the same note.
        self.assertIn("Scheduled Castes", pk.ETHNICITY_GAP)
        self.assertIn("category of the religion question", pk.ETHNICITY_GAP)

    def test_the_reason_names_both_statuses_so_the_choice_is_readable(self):
        self.assertIn("not_collected", pk.ETHNICITY_GAP)
        self.assertIn("not_available", pk.ETHNICITY_GAP)


class MotherTongueIsPointedAtAndNeverRelabelled(unittest.TestCase):
    def test_a_unit_with_a_language_names_its_leading_tongue(self):
        rows = [unit("PAK-kp", language=[{"group": "Pushto", "pct": 81.0},
                                         {"group": "Hindko", "pct": 9.4}])]
        pk.say_ethnicity(rows)
        note = rows[0]["ethnicity"]["note"]
        self.assertIn("Pushto leads at 81.0%", note)
        self.assertIn("language field", note)

    def test_the_pointer_says_a_language_is_not_an_ethnicity(self):
        rows = [unit("PAK-sindh", language=[{"group": "Sindhi", "pct": 61.6}])]
        pk.say_ethnicity(rows)
        self.assertIn("a language is not an ethnicity",
                      rows[0]["ethnicity"]["note"])

    def test_the_field_stays_a_gap_and_never_becomes_the_language_list(self):
        # The failure this whole field exists to avoid. Sindhi speakers are
        # not "Sindhis" counted by the census, and a composition here would
        # be a mis-match: invisible on the map and worse than the gap.
        rows = [unit("PAK-sindh", language=[{"group": "Sindhi", "pct": 61.6}])]
        pk.say_ethnicity(rows)
        self.assertIsInstance(rows[0]["ethnicity"], dict)
        self.assertNotIn("Sindhi", rows[0]["ethnicity"]["note"].split(
            "language field")[0])

    def test_a_unit_with_no_language_sends_the_reader_there_anyway(self):
        # Gilgit-Baltistan's ten districts have a stated language gap rather
        # than a composition, and the sentence has to work for that too.
        rows = [unit("PAK-gb-astore",
                     language={"status": pk.NOT_AVAILABLE, "note": "..."})]
        pk.say_ethnicity(rows)
        note = rows[0]["ethnicity"]["note"]
        self.assertIn("or why nothing is", note)
        self.assertNotIn("leads at", note)


class AFigureWouldWin(unittest.TestCase):
    def test_a_composition_already_there_is_left_alone(self):
        counted = [{"group": "Somebody", "pct": 100.0}]
        rows = [unit("PAK-somewhere", ethnicity=counted)]
        self.assertEqual(pk.say_ethnicity(rows), 0)
        self.assertEqual(rows[0]["ethnicity"], counted)


if __name__ == "__main__":
    unittest.main()
