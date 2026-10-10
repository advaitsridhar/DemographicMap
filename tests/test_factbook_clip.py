"""The Factbook's free text, cut where a reader can follow it.

No network: the strings are the Factbook's ethnic-group entries, whose first
180 characters the country panels printed cut mid-word or mid-bracket.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_factbook  # noqa: E402

AFG = ("current, reliable statistical data on ethnicity in Afghanistan are not "
       "available; Afghanistan's 2004 Constitution cited Pashtun, Tajik, Hazara, Uzbek, "
       "Turkman, Baluch, Pashaie, Nuristani, Gujur, Arab, Brahwui, Qizilbash, Aimaq, and "
       "Pashai and Kyrghyz")
MDG = ("Malayo-Indonesian (Merina and related Betsileo), Cotiers (mixed African, "
       "Malayo-Indonesian, and Arab ancestry - Betsimisaraka, Tsimihety, Antaisaka, "
       "Sakalava), French, Indian, Creole, Comoran")
STP = ("Mestico, Angolares (descendants of Angolan slaves), Forros (descendants of freed "
       "slaves), Servicais (contract laborers from Angola, Mozambique, and Cabo Verde), "
       "Tongas (children of Servicais born on the islands), Europeans (primarily "
       "Portuguese), Asians (mostly Chinese)")


class Clip(unittest.TestCase):
    def test_a_short_text_is_whole(self):
        self.assertEqual(fetch_factbook.clip("Kazakh 70%,  Russian 15%", 180),
                         "Kazakh 70%, Russian 15%")

    def test_cut_at_a_clause_outside_brackets(self):
        afg = fetch_factbook.clip(AFG, 180)
        self.assertTrue(afg.endswith("Turkman, Baluch, Pashaie..."), afg)
        mdg = fetch_factbook.clip(MDG, 180)
        self.assertTrue(mdg.endswith("Sakalava), French, Indian..."), mdg)
        stp = fetch_factbook.clip(STP, 180)
        self.assertTrue(stp.endswith("Mozambique, and Cabo Verde)..."), stp)
        for cut in (afg, mdg, stp):
            self.assertLessEqual(len(cut), 180)
            self.assertEqual(cut.count("("), cut.count(")"), cut)

    def test_no_clause_falls_back_to_a_word_before_any_open_bracket(self):
        text = "word " * 20 + "(an aside that runs on " + "and on " * 30 + ")"
        cut = fetch_factbook.clip(text, 120)
        self.assertTrue(cut.endswith("word..."), cut)
        self.assertNotIn("(", cut)


class TheCommittedFile(unittest.TestCase):
    def test_no_free_text_note_stops_mid_word(self):
        rows = json.loads((ROOT / "data" / "processed" / "admin0.json").read_text("utf-8"))
        for row in rows:
            for field in ("religion", "language", "ethnicity"):
                value = row.get(field)
                note = value.get("note") if isinstance(value, dict) else None
                if not note or "free text only: " not in note:
                    continue
                text = note.split("free text only: ", 1)[1]
                self.assertLessEqual(len(text), 180, row.get("id"))
                if len(text) >= 170:
                    # Long enough to have been cut: it says so, at a boundary.
                    self.assertTrue(text.endswith("..."), (row.get("id"), field, text))
                    self.assertEqual(text.count("("), text.count(")"), (row.get("id"), text))


if __name__ == "__main__":
    unittest.main()
