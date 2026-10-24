"""Thailand's 2010 census, read from each province's report.

Each composition comes from a block of section 1.5's table that the report's
own key indicators bear out, or else from the indicators, and the note says
why. The samples are the reports' own text layer, as the runner's probes of
the archived reports printed it. No network.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import thailand_2010 as t  # noqa: E402
from scripts.fetch_census.sea_common import fold  # noqa: E402

# Bueng Kan's report: the key indicators (page 9) and section 1.5's table (page 24).
BUENG_KAN = """\
      ประชากรที่มีสัญชาติไทย (%) 99.7   Thai citizenship (%)
      ประชากรที่ไม่ใช่สัญชาติไทย (%) 0.3   Non Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 99.4   Buddhism (%)
      ประชากรที่นับถือศาสนาคริสต์ (%) 0.5   Christianity (%)
    ตาราง  5  ร้อยละของประชากร  จําแนกตามศาสนา สัญชาติ และ
    เขตการปกครอง ศาสนาและสัญชาติ รวม
    ในเขตเทศบาล นอกเขตเทศบาล
        ศาสนา    100.0       100.0        100.0
    พุทธ 99.4 99.6 99.3
    อิสลาม 0.1 a 0.1
    คริสต์ 0.5 0.3 0.6
    อื่นๆ a a a

    สัญชาติ    100.0       100.0        100.0
    ไทย 99.7 99.6 99.7
    ลาว 0.3 0.3 0.3
    อื่นๆ a 0.1 a
    a  น้อยกว่าร้อยละ 0.1
    1.6  สถานภาพสมรส
""".splitlines()

# Nong Khai's: the indicators print 1990, 2000 and 2010; the religion block ends
# page 25 and the nationality block is on page 26, "Table 5 (continued)".
NONG_KHAI = """\
      ประชากรที่มีสัญชาติไทย (%) na 99.5 99.4   Thai citizenship (%)
      ประชากรที่ไม่ใช่สัญชาติไทย (%) na 0.5 0.6   Non Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 99.5 99.1 99.5   Buddhism (%)
      ประชากรที่นับถือศาสนาอิสลาม (%) 0.1 0.1 0.1   Muslims (%)
    ตาราง  5  ร้อยละของประชากร  จําแนกศาสนา สัญชาติ และเขตการปกครอง
    ศาสนาและสัญชาติ รวม เขตการปกครอง ในเขตเทศบาล นอกเขตเทศบาล
    ศาสนา 100.0 100.0 100.0
    พุทธ 99.5 99.4 99.5
    อิสลาม 0.1 0.1 0.1
    คริสต์ 0.4 0.5 0.4
    อื่นๆ a a a
\x20
\x20
    ตาราง  5  ร้อยละของประชากร  จําแนกศาสนา สัญชาติ และเขตการปกครอง (ต่อ)
    ศาสนาและสัญชาติ รวม เขตการปกครอง ในเขตเทศบาล นอกเขตเทศบาล
    สัญชาติ    100.0      100.0       100.0
    ไทย 99.4 99.2 99.6
    ลาว 0.5 0.6  0.4
    เวียดนาม a 0.1 a
    อื่นๆ  0.1  0.1  a
    a   น้อยกว่าร้อยละ 0.1
\x20
    1.6  สถานภาพสมรส
""".splitlines()

# Yala's: two nationality rows whose figures fall to the next line.
YALA = """\
      ประชากรที่มีสัญชาติไทย (%) na 99.8 99.0   Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 35.9 31.0 23.3   Buddhism (%)
      ประชากรที่นับถือศาสนาอิสลาม (%) 63.8 68.9 76.6   Muslims (%)
        ศาสนา    100.0        100.0         100.0
    พุทธ 23.3 48.7 13.6
    อิสลาม 76.6 51.1 86.3
    อื่นๆ  0.1  0.2   0.1
\x20\x20\x20\x20
    สัญชาติ    100.0        100.0         100.0
    ไทย
     99.0 97.7 98.5
    จีน  0.1  0.3   0.2
    มาเลเซีย  0.1  0.1   0.1
    ลาว  0.1  0.1   1.0
    พม่า
            0.6            1.6             0.1
    อื่นๆ  0.1    0.2    0.1
""".splitlines()

# Saraburi's: a blank line between a label and its figures.
SARABURI_NATIONALITY = """\
          สัญชาติ 100.0 100.0 100.0
              ไทย 98.3 98.3 98.3
              ลาว 0.4 0.2 0.5
              พม่า
\x20
    0.8 0.9 0.8
              อื่นๆ 0.5 0.6 0.4
\x20\x20
    1.6  สถานภาพสมรส
""".splitlines()

# Ratchaburi's: a footnote mark after a label, and the footnote under the block.
RATCHABURI_NATIONALITY = """\
    สัญชาติ 100.0 100.0 100.0
    ไทย 96.0 94.2 97.1
    จีน 0.2 0.4 0.1
    กัมพูชา 0.1 0.2 0.1
    ลาว 0.1 0.2 0.1
    พม่า 2.6 4.2 1.6
    อื่นๆ 1/ 1.0 0.8 1.0
             1/  ไม่รวมผู้ที่ไม่ทราบสัญชาติ
""".splitlines()

# Phuket's: a figure split at its point, and the British.
PHUKET = """\
      ประชากรที่มีสัญชาติไทย (%) na 98.5 82.0   Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 82.8 81.6 79.5   Buddhism (%)
      ประชากรที่นับถือศาสนาอิสลาม (%) 16.9 17.1 16.0   Muslims (%)
           ศาสนา           100.0    100.0    100.0
      พุทธ              79.5     86.4      64.8
      อิสลาม              16.0       8.6      31.8
      คริสต์                3. 6       4.0       2.8
      อื่นๆ                0.9       1.0        0.6
       สัญชาติ           100.0    100.0     100.0
      ไทย              82.0      79.7      86.8
      พม่า              11.1      12.3        8.6
      สหราชอาณาจักร                1.1       1.0        1.4
      อื่นๆ                5.8             7.0        3.2
            1/  ไม่รวมไม่ทราบ
""".splitlines()

# Krabi's: "Buddihism", a non-Thai share with two decimals, and 614 misprinted
# for the non-municipal Buddhists.
KRABI = """\
      ประชากรที่มีสัญชาติไทย (%) na 99.8 98.8   Thai citizenship (%)
      ประชากรที่ไม่ใช่สัญชาติไทย (%) na 0.2 1.16   Non Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 64.2 65.2 65.0   Buddihism (%)
      ประชากรที่นับถือศาสนาอิสลาม (%) 35.6 34.7 34.6   Muslims (%)
    ศาสนา    100.0 100.0 100.0
    พุทธ 65.0 86.1 614
    อิสลาม 34.6 13.2 38.3
    คริสต์ 0.1 0.4 0.1
    อื่นๆ 0.3 0.3 0.2
    สัญชาติ    100.0 100.0 100.0
    ไทย 98.8 99.4 98.7
    พม่า 1.0 0.3 1.1
    ลาว 0.1 0.1 0.1
    อื่นๆ 0.1 0.2 0.1
\x20\x20\x20\x20
    1.6  สถานภาพสมรส
""".splitlines()

# Bangkok's: one column, its own words for the indicators, and a nationality
# block whose text comes apart (``FROM_PAGE`` holds it).
BANGKOK = """\
      ประชากรที่มีสัญชาติไทย (%) na 99.0 91.4   Thai nationalities (%)
      ประชากรที่ไม่ใช่สัญชาติไทย (%) na 1.0 8.6   Non Thai nationalities (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 95.1 94.5 92.6   Buddhists (%)
      ประชากรที่นับถือศาสนาอิสลาม (%) 4.0 4.1 4.6   Muslims (%)
    ตาราง  5  ร้อยละของประชากร  จําแนกตามศาสนา และสัญชาติ
    ศาสนาและสัญชาติ                           ร้อยละ
    ศาสนา    100.0
     พุทธ 92.5
      อิสลาม  4.6
      คริสต์  1.9
      ฮินดู  0.3
      ขงจื้อ  0.1
      ซิกซ์  0.1
      อื่นๆ  0.3
      ไม่มีศาสนา  0.2
\x20
    สัญชาติ
    ไทย
    พม่า
    กัมพูช
""".splitlines()

# Mae Hong Son's: a table four points of Thai nationality over its indicators.
MAE_HONG_SON = """\
      ประชากรที่มีสัญชาติไทย (%) na 93.1 90.0   Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 81.0 79.1 76.2   Buddhism (%)
    ศาสนา 100.0 100.0 100.0
    พุทธ 76.2 88.0 74.2
    คริสต์ 22.8 10.7 24.9
    อิสลาม 0.6 1.3 0.5
    อื่นๆ 0.3 0.1 0.3
    สัญชาติ 100.0 100.0 100.0
    ไทย 94.1 97.7 93.5
    พม่า 3.8 1.9 4.2
    จีน 0.2 0.1 0.3
    อื่นๆ 1.8 0.3 2.1
    a น้อยกว่าร้อยละ 0.1
""".splitlines()

# Nakhon Phanom's: nationality rows that add to 100.9.
NAKHON_PHANOM = """\
      ประชากรที่มีสัญชาติไทย (%) na 99.2 98.9   Thai citizenship (%)
      ประชากรที่นับถือศาสนาพุทธ (%) 99.0 98.9 99.1   Buddhism (%)
    ศาสนา 100.0 100.0 100.0
    พุทธ 99.1 98.8 99.2
    คริสต์ 0.8 1.0 0.7
    อิสลาม 0.1 0.1 a
    อื่นๆ a 0.1 a
    สัญชาติ 100.0 100.0 100.0
    ไทย 98.9 98.4 99.1
    ลาว 0.9 1.3 0.8
    เวียดนาม a 0.1 a
    อื่นๆ 1.1 1.7 1.0
    a น้อยกว่าร้อยละ 0.1
""".splitlines()


def groups(rows):
    return {r["group"]: r["pct"] for r in rows}


def nationality(lines, head=("      ประชากรที่มีสัญชาติไทย (%) 98.3   Thai citizenship (%)",)):
    return t.read("Saraburi", list(head) + list(lines))


class ReadingTheTable(unittest.TestCase):

    def test_the_province_s_own_column_is_read_and_a_rows_are_left_out(self):
        reading = t.read("Bueng Kan", BUENG_KAN)
        self.assertEqual(reading.problems, [])
        self.assertEqual((reading.religion_from, reading.nationality_from), ("table", "table"))
        self.assertEqual(groups(reading.religion),
                         {"Buddhism": 99.4, "Islam": 0.1, "Christianity": 0.5})
        self.assertEqual(groups(reading.nationality), {"Thai": 99.7, "Lao": 0.3})

    def test_a_block_continued_on_the_next_page_is_read(self):
        reading = t.read("Nong Khai", NONG_KHAI)
        self.assertEqual(reading.problems, [])
        self.assertEqual(groups(reading.nationality),
                         {"Thai": 99.4, "Lao": 0.5, "Other nationalities": 0.1})

    def test_figures_that_fall_to_the_next_line_join_their_label(self):
        reading = t.read("Yala", YALA)
        self.assertEqual(reading.problems, [])
        self.assertEqual(groups(reading.nationality),
                         {"Thai": 99.0, "Chinese": 0.1, "Malaysian": 0.1, "Lao": 0.1,
                          "Burmese": 0.6, "Other nationalities": 0.1})
        reading = nationality(SARABURI_NATIONALITY)
        self.assertEqual(groups(reading.nationality),
                         {"Thai": 98.3, "Lao": 0.4, "Burmese": 0.8, "Other nationalities": 0.5})

    def test_a_footnote_mark_after_a_label_and_the_footnote_under_the_block(self):
        reading = nationality(RATCHABURI_NATIONALITY,
                              ("  ประชากรที่มีสัญชาติไทย (%) na 99.3 96.0   Thai citizenship (%)",))
        self.assertEqual(reading.nationality_from, "table")
        self.assertEqual(groups(reading.nationality)["Other nationalities"], 1.0)
        self.assertEqual(round(sum(groups(reading.nationality).values()), 1), 100.0)

    def test_a_figure_split_at_its_point_is_whole(self):
        reading = t.read("Phuket", [t.clean(line) for line in PHUKET])
        self.assertEqual(reading.problems, [])
        self.assertEqual(groups(reading.religion)["Christianity"], 3.6)
        self.assertEqual(groups(reading.nationality)["British"], 1.1)

    def test_only_the_first_column_must_be_a_figure(self):
        reading = t.read("Krabi", KRABI)
        self.assertEqual(reading.problems, [])
        self.assertEqual(groups(reading.religion)["Buddhism"], 65.0)
        self.assertEqual(reading.religion_from, "table")

    def test_private_use_marks_are_the_letters_they_draw(self):
        self.assertEqual(t.clean("    คริสต 0.5 0.3 0.6"), "    คริสต์ 0.5 0.3 0.6")
        self.assertEqual(t.clean("พมา​ 0.4"), "พม่า 0.4")

    def test_the_note_speaks_of_a_remainder_only_where_one_is_shown(self):
        bueng_kan = t.read("Bueng Kan", BUENG_KAN)                # "อื่นๆ a" in both
        self.assertNotIn("remainder", bueng_kan.religion_note)
        self.assertNotIn("remainder", bueng_kan.nationality_note)
        self.assertTrue(bueng_kan.religion_note.endswith(
            "is left out." + t.NOTE_SPLIT["Bueng Kan"]))
        nong_khai = t.read("Nong Khai", NONG_KHAI)                # "อื่นๆ 0.1" for nationality
        self.assertIn("'Other nationalities' is the table's own remainder",
                      nong_khai.nationality_note)
        self.assertNotIn("remainder", nong_khai.religion_note)

    def test_a_row_printed_0_0_is_left_out(self):
        lines = [line.replace("อื่นๆ a a a", "อื่นๆ 0.0 0.0 0.0") for line in BUENG_KAN]
        self.assertNotIn("Other religions", groups(t.read("Bueng Kan", lines).religion))

    def test_a_row_the_labels_do_not_name_is_a_problem_not_a_guess(self):
        lines = [line.replace("ลาว 0.3", "ฮ่องกง 0.3") for line in BUENG_KAN]
        self.assertTrue(any("ฮ่องกง" in p for p in t.read("Bueng Kan", lines).problems))

    def test_two_rows_of_one_nationality_are_a_problem(self):
        lines = [line.replace("ลาว 0.3 0.3 0.3", "ไทย 0.3 0.3 0.3") for line in BUENG_KAN]
        self.assertIn("nationality: two rows are Thai", t.read("Bueng Kan", lines).problems)


class TheKeyIndicators(unittest.TestCase):

    def test_the_2010_column_is_the_last_before_the_english_label(self):
        key = t.indicators(NONG_KHAI)
        self.assertEqual(key["thai"], "99.4")
        self.assertEqual(key["faiths"], {"Buddhism": "99.5", "Islam": "0.1"})

    def test_each_report_s_own_words_for_them(self):
        self.assertEqual(t.indicators(KRABI)["faiths"], {"Buddhism": "65.0", "Islam": "34.6"})
        key = t.indicators(BANGKOK)
        self.assertEqual((key["thai"], key["faiths"]["Buddhism"]), ("91.4", "92.6"))

    def test_one_in_the_last_digit_from_them_the_table_stands(self):
        lines = [line.replace("99.7   Thai", "99.6   Thai") for line in BUENG_KAN]
        reading = t.read("Bueng Kan", lines)
        self.assertEqual(reading.nationality_from, "table")
        self.assertEqual(groups(reading.nationality)["Thai"], 99.7)

    def test_a_table_they_contradict_gives_way_to_them(self):
        reading = t.read("Mae Hong Son", MAE_HONG_SON)
        self.assertEqual(reading.nationality_from, "indicators")
        self.assertEqual(groups(reading.nationality),
                         {"Thai": 90.0, t.RESIDUAL_NATIONALITY: 10.0})
        self.assertIn("it prints Thai nationality 94.1% where the key indicators print 90.0%",
                      reading.nationality_note)
        self.assertTrue(reading.nationality_note.startswith("Nationality, not ethnicity"))
        self.assertEqual(reading.religion_from, "table")       # its own, and agreeing

    def test_a_table_that_does_not_add_up_gives_way_to_them(self):
        reading = t.read("Nakhon Phanom", NAKHON_PHANOM)
        self.assertEqual(reading.problems, [])
        self.assertEqual(reading.nationality_from, "indicators")
        self.assertIn("its rows add to 100.9%", reading.nationality_note)
        self.assertEqual(groups(reading.nationality),
                         {"Thai": 98.9, t.RESIDUAL_NATIONALITY: 1.1})

    def test_a_report_whose_table_cannot_be_read_gives_their_figures(self):
        reading = t.read("Bueng Kan", BUENG_KAN[:4])
        self.assertEqual(reading.problems, [])
        self.assertEqual((reading.religion_from, reading.nationality_from),
                         ("indicators", "indicators"))
        self.assertEqual(groups(reading.religion),
                         {"Buddhism": 99.4, "Christianity": 0.5, t.RESIDUAL_FAITH: 0.1})
        self.assertIn(t.WHY_NONE, reading.religion_note)

    def test_no_table_and_no_indicators_is_a_problem(self):
        reading = t.read("Bueng Kan", BUENG_KAN[4:])
        self.assertIn("religion: no key indicator to check the table by", reading.problems)

    def test_bangkok_s_nationality_rows_are_the_page_s(self):
        reading = t.read("Bangkok", BANGKOK)
        self.assertEqual(reading.problems, [])
        self.assertEqual((reading.religion_from, reading.nationality_from), ("table", "table"))
        self.assertEqual(groups(reading.religion),
                         {"Buddhism": 92.5, "Islam": 4.6, "Christianity": 1.9, "Hinduism": 0.3,
                          "Confucianism": 0.1, "Sikhism": 0.1, "Other religions": 0.3,
                          "No religion": 0.2})
        self.assertEqual(groups(reading.nationality),
                         {"Thai": 91.4, "Burmese": 2.6, "Cambodian": 0.9, "Chinese": 0.9,
                          "Japanese": 0.8, "Lao": 0.6, "Other nationalities": 2.8})


class TwoReportsAlike(unittest.TestCase):
    """A block printed in two reports word for word stands only on the exact figure."""

    def test_the_one_its_indicators_print_exactly_keeps_it_and_the_other_gives_way(self):
        texts = {"Bueng Kan": BUENG_KAN,
                 "Nong Khai": [line.replace("99.7   Thai", "99.6   Thai")
                               for line in BUENG_KAN]}
        first = {p: t.read(p, lines) for p, lines in texts.items()}
        self.assertEqual(first["Nong Khai"].nationality_from, "table")     # within a digit
        readings, lines = t.settle(texts)
        self.assertEqual(readings["Bueng Kan"].nationality_from, "table")
        self.assertEqual(readings["Nong Khai"].nationality_from, "indicators")
        self.assertIn("its rows are Bueng Kan's, word for word, and print Thai nationality "
                      "99.7% where the key indicators print 99.6%",
                      readings["Nong Khai"].nationality_note)
        self.assertIn("the nationality block of Nong Khai's report is Bueng Kan's, word for "
                      "word; held to the exact figure, it gives way to the key indicators", lines)
        self.assertIn("the nationality block of Bueng Kan's report is Nong Khai's, word for "
                      "word; held to the exact figure, it stands", lines)

    def test_reports_with_their_own_blocks_are_read_once(self):
        readings, lines = t.settle({"Bueng Kan": BUENG_KAN, "Yala": YALA})
        self.assertEqual(lines, [])
        self.assertEqual(readings["Yala"].nationality_from, "table")


class TheSplitAndTheMap(unittest.TestCase):

    def test_bueng_kan_and_nong_khai_say_what_their_reports_cover(self):
        self.assertIn("March 2011", t.read("Bueng Kan", BUENG_KAN).religion_note)
        nong_khai = t.read("Nong Khai", NONG_KHAI)
        for note in (nong_khai.religion_note, nong_khai.nationality_note):
            self.assertIn("as it was at the census, with the eight districts that became "
                          "Bueng Kan", note)

    def test_every_report_names_a_drawn_province(self):
        path = ROOT / "site" / "data" / "admin1" / "THA.units.json"
        if not path.exists():
            self.skipTest("Thailand's units are not in this checkout")
        drawn = {fold(u["name"].removesuffix(" Province"))
                 for u in json.loads(path.read_text(encoding="utf-8"))}
        self.assertFalse([p for p in t.CAPTURES if fold(p) not in drawn])
        self.assertEqual(len(t.CAPTURES), 75)
        self.assertNotIn("Lampang", t.CAPTURES)
        self.assertNotIn("Suphan Buri", t.CAPTURES)

    def test_the_written_file_fills_bueng_kan(self):
        path = ROOT / "data" / "processed" / t.OUT
        if not path.exists():
            self.skipTest(f"{t.OUT} is not in this checkout")
        rows = {r["name"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
        bueng_kan = rows["Bueng Kan Province"]
        self.assertEqual(groups(bueng_kan["religion"])["Buddhism"], 99.4)
        self.assertEqual(groups(bueng_kan["ethnicity"])["Thai"], 99.7)
        self.assertEqual(bueng_kan["ethnicity_basis"], "nationality")
        self.assertEqual(len(rows), 75)


if __name__ == "__main__":
    unittest.main()
