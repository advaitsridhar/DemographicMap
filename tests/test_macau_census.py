"""The three DSEC pages as pypdf prints them, and the cuts that read them."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import macau_census as mo  # noqa: E402

# Page 68 of the October 2022 revision, as the runner's probe printed it:
# the title, the column heads, then the Total block's MF/M/F rows and the
# first age group, figures set with a space for the thousands.
NATIONALITY = """6 POPULATION BY GENDER, AGE GROUP AND NATIONALITY
Total Chinese Filipino Other Asian countries Portuguese Others
MF 682 070 608 379 33 896 26 640 8 991 4 164
M 320 285 291 118 12 193 9 716 4 695 2 563
F 361 785 317 261 21 703 16 924 4 296 1 601
MF 32 464 31 041  480  126  632  185
M 16 863 16 162  238  48  305  110
F 15 601 14 879  242  78  327  75
Age group and gender
Total
0-4
Detailed Results of 2021 Population Census 66"""

# Page 72: the column heads are scattered by the reader, "Others" glued to
# the row-heading text, and the note on the universe sits at the foot.
LANGUAGE = """10 POPULATION BY GENDER, AGE GROUP AND USUAL LANGUAGE
Cantonese Mandarin Other Chinese
dialects
MF 663 782 537 981 31 405 36 032 3 949 23 635 19 154 11 626
M 310 877 255 748 13 392 17 055 1 996 7 082 9 372 6 232
F 352 905 282 233 18 013 18 977 1 953 16 553 9 782 5 394
MF 14 176 12 759  620  57  134  511  50  45
M 7 455 6 734  352  23  51  251  10  34
F 6 721 6 025  268  34  83  260  40  11
Total
3-4
Tagalog OthersAge group and gender Total
Chinese
Portuguese English
Note: Applicable to the population aged 3 and above.
Detailed Results of 2021 Population Census 70"""

# Page 40, Principal Characteristics of Population: the language table a
# second time, each count with its share, 2021 then 2011.
PRINCIPAL = """Characteristics
2021 2011
No. Structure (%)  No. Structure (%)
Population aged 3 and above 663 782 539 131
Usual language
Chinese 605 418 91.2 506 993 94.0
Cantonese 537 981 81.0 449 274 83.3
Mandarin 31 405 4.7 27 129 5.0
Other Chinese dialects 36 032 5.4 30 590 5.7
Portuguese 3 949 0.6 4 022 0.7
English 23 635 3.6 12 155 2.3
Other 30 780 4.6 15 961 3.0
Population aged 15 and above 583 089 486 633
Educational attainment
No schooling / Pre-primary education 9 354 1.6 16 502 3.4
Detailed Results of 2021 Population Census
40"""

# A page from the same window that must not be mistaken for any of them:
# the glossary names usual language without the table.
GLOSSARY = """ Usual language
The language an individual mostly used at home.
 Usual population
Individuals staying in Macao for at least three months."""

PAGES = {"nationality": NATIONALITY, "language": LANGUAGE, "principal": PRINCIPAL}


def replaced(page: str, old: str, new: str) -> str:
    assert page.count(old) == 1, old
    return page.replace(old, new)


class Cuts(unittest.TestCase):
    def test_every_cut_of_a_spaced_row_is_offered(self):
        cuts = mo.readings("682 070 608 379".split(), 2)
        self.assertIn([682070, 608379], cuts)
        self.assertIn([682, 70608379], cuts)
        self.assertIn([682070608, 379], cuts)
        self.assertEqual(len(cuts), 3)

    def test_a_four_digit_token_is_not_a_figure(self):
        self.assertEqual(mo.readings(["6820", "70"], 2), [])
        self.assertEqual(mo.readings(["682", "70"], 1), [])

    def test_the_total_row_is_the_cut_the_arithmetic_picks(self):
        total, counts = mo.total_row(NATIONALITY, mo.NATIONALITY_COLUMNS, "nationality")
        self.assertEqual(total, 682070)
        self.assertEqual(counts, {"Chinese": 608379, "Filipino": 33896,
                                  "Other Asian countries": 26640, "Portuguese": 8991,
                                  "Others": 4164})
        total, counts = mo.total_row(LANGUAGE, mo.LANGUAGE_COLUMNS, "usual language")
        self.assertEqual(total, 663782)
        self.assertEqual(counts["Cantonese"], 537981)
        self.assertEqual(counts["Tagalog"], 19154)
        self.assertEqual(counts["Others"], 11626)

    def test_a_row_the_arithmetic_cannot_cut_is_refused(self):
        page = replaced(NATIONALITY, "MF 682 070 608 379", "MF 682 071 608 379")
        with self.assertRaises(SystemExit):
            mo.total_row(page, mo.NATIONALITY_COLUMNS, "nationality")

    def test_a_missing_column_head_is_refused(self):
        page = replaced(NATIONALITY, "Other Asian countries", "Other Asian")
        with self.assertRaises(SystemExit):
            mo.total_row(page, mo.NATIONALITY_COLUMNS, "nationality")

    def test_the_principal_block_pairs_count_and_share(self):
        rows = mo.principal_language(PRINCIPAL)
        self.assertEqual(rows["Cantonese"], (537981, 81.0))
        self.assertEqual(rows["Other Chinese dialects"], (36032, 5.4))
        self.assertEqual(rows["Other"], (30780, 4.6))
        self.assertNotIn("Educational attainment", rows)
        self.assertEqual(len(rows), 7)


class Locating(unittest.TestCase):
    def test_pages_are_found_by_title_and_not_by_a_word(self):
        stream = [(45, GLOSSARY), (40, PRINCIPAL), (68, NATIONALITY), (72, LANGUAGE)]
        found = mo.locate(stream)
        self.assertEqual(found["principal"], PRINCIPAL)
        self.assertEqual(found["nationality"], NATIONALITY)
        self.assertEqual(found["language"], LANGUAGE)

    def test_a_missing_table_is_refused(self):
        with self.assertRaises(SystemExit):
            mo.locate([(40, PRINCIPAL), (68, NATIONALITY)])


class Record(unittest.TestCase):
    def test_the_record_as_the_census_prints_it(self):
        records = mo.build(PAGES)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["name"], "Macau Special Administrative Region")
        self.assertEqual(rec["id"], "CHN-macau-special-administrative-region")
        self.assertEqual((rec["country"], rec["parent"], rec["level"]),
                         ("CHN", "CHN", "admin1"))
        self.assertEqual(rec["population"]["value"], 682070)
        self.assertEqual(rec["ethnicity"][0], {"group": "Chinese", "pct": 89.2, "count": 608379})
        self.assertEqual(rec["ethnicity"][1], {"group": "Filipino", "pct": 5.0, "count": 33896})
        self.assertEqual([r["group"] for r in rec["ethnicity"]],
                         ["Chinese", "Filipino", "Other Asian nationality", "Portuguese",
                          "Other nationalities"])
        self.assertAlmostEqual(sum(r["pct"] for r in rec["ethnicity"]), 100.0, delta=0.3)
        self.assertEqual(rec["ethnicity_year"], 2021)
        self.assertEqual(rec["ethnicity_basis"], "nationality")
        self.assertEqual(rec["language"][0], {"group": "Cantonese", "pct": 81.0, "count": 537981})
        self.assertEqual([r["group"] for r in rec["language"]],
                         ["Cantonese", "Other Chinese dialects", "Mandarin", "English",
                          "Tagalog", "Other languages", "Portuguese"])
        self.assertAlmostEqual(sum(r["pct"] for r in rec["language"]), 100.0, delta=0.3)
        self.assertEqual(rec["language_year"], 2021)
        self.assertEqual(rec["language_basis"], "usual language, population aged 3 and over")
        # Religion is the China policy's business, not this file's.
        self.assertEqual(rec["religion"], {"status": "not_available"})
        self.assertEqual({s["field"] for s in rec["sources"]},
                         {"ethnicity", "language", "population"})
        self.assertTrue(all(s["url"] == mo.URL for s in rec["sources"]))

    def test_the_notes_are_short_and_say_what_first(self):
        rec = mo.build(PAGES)[0]
        for field in ("ethnicity", "language"):
            note = rec[f"{field}_note"]
            self.assertTrue(note.startswith(mo.SOURCE), note)
            self.assertLessEqual(note.count(". "), 4, note)
        self.assertIn("Nationality, not ethnicity", rec["ethnicity_note"])
        self.assertIn("aged 3 and over", rec["language_note"])
        # No caveat sentence: the tables agree with the report's prose.
        self.assertNotIn("differs", rec["ethnicity_note"])
        self.assertNotIn("differs", rec["language_note"])

    def test_the_policy_leaves_a_written_list_alone(self):
        from common import apply_collection_policy
        rec = mo.build(PAGES)[0]
        applied = apply_collection_policy(rec, "CHN")
        self.assertEqual(applied, ["religion"])
        self.assertEqual(rec["religion"]["status"], "not_collected")
        self.assertIsInstance(rec["ethnicity"], list)
        self.assertIsInstance(rec["language"], list)


class Refusals(unittest.TestCase):
    def test_a_total_that_is_not_the_published_population_is_refused(self):
        pages = dict(PAGES)
        pages["nationality"] = replaced(
            NATIONALITY, "MF 682 070 608 379 33 896", "MF 682 071 608 380 33 896")
        with self.assertRaises(SystemExit):
            mo.build(pages)

    def test_table_10_must_agree_with_the_principal_page_count_for_count(self):
        pages = dict(PAGES)
        pages["principal"] = replaced(PRINCIPAL, "English 23 635 3.6", "English 23 636 3.6")
        with self.assertRaises(SystemExit):
            mo.build(pages)

    def test_the_chinese_row_must_be_its_three_columns(self):
        pages = dict(PAGES)
        pages["principal"] = replaced(PRINCIPAL, "Chinese 605 418 91.2", "Chinese 605 419 91.2")
        with self.assertRaises(SystemExit):
            mo.build(pages)

    def test_a_printed_share_that_disagrees_is_a_sentence_not_a_refusal(self):
        pages = dict(PAGES)
        pages["principal"] = replaced(PRINCIPAL, "English 23 635 3.6", "English 23 635 3.9")
        rec = mo.build(pages)[0]
        self.assertEqual(rec["language"][3], {"group": "English", "pct": 3.6, "count": 23635})
        self.assertIn("English 3.6% against a printed 3.9%", rec["language_note"])

    def test_a_share_the_text_states_differently_is_a_sentence_too(self):
        caveats = []
        rows = mo.checked("ethnicity", {"Chinese": 608379, "Other nationalities": 73691},
                          682070, 682070, {"Chinese": 89.5}, caveats)
        self.assertEqual(rows[0]["pct"], 89.2)
        self.assertEqual(len(caveats), 1)
        self.assertIn("Chinese 89.2% here against 89.5%", caveats[0])

    def test_shares_that_do_not_sum_are_refused(self):
        with self.assertRaises(SystemExit):
            mo.checked("ethnicity", {"Chinese": 608379}, 682070, 682070, {}, [])


if __name__ == "__main__":
    unittest.main()
