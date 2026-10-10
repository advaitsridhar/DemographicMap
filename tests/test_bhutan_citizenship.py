"""Bhutan 2017: citizenship from each dzongkhag report's Table 2.2, held to Table 2.1.

Pages arrive as pdfplumber's words would -- (left x, right x, text) -- in the
order a report prints them: the contents page naming Table 2.2, Table 2.1,
then Table 2.2 under its own title. No PDF, no network.
"""

import unittest
from unittest import mock

from scripts.fetch_census import bhutan as bt


def row(*words: str):
    out, x = [], 10.0
    for word in words:
        out.append((x, x + 4.0 * len(word), word))
        x += 4.0 * len(word) + 8.0
    return out


def contents():
    return [row("Table", "2.1", "Population", "Distribution", "by", "Gewog", "and",
                "Town,", "Tsirang", "2017", "........4"),
            row("Table", "2.2", "Distribution", "of", "Bhutanese", "Population", "by",
                "Sex", "and", "Gewog/Town,", "Tsirang", "2017", "........8")]


def table21():
    return [row("Table", "2.1", "Population", "Distribution", "by", "Gewog", "and",
                "Town,", "Tsirang", "2017"),
            row("Gewog/Town", "Male", "Female", "Total"),
            row("Urban"),
            row("Tsirang", "Town", "1,854", "1,594", "3,448"),
            row("Rural"),
            row("Barshong", "423", "419", "842"),
            row("Patshaling", "567", "592", "1,159"),
            row("Total", "2,844", "2,605", "5,449")]


def table22(barshong=("421", "417", "838"), extra=()):
    rows = [row("Table", "2.2", "Distribution", "of", "Bhutanese", "Population", "by",
                "Sex", "and", "Gewog/Town,", "Tsirang", "2017"),
            row("Number", "of", "Persons", "Percent"),
            row("Gewog/Town", "Male", "Female", "Total", "Male", "Female", "Total",
                "Sex", "Ratio"),
            row("Urban", "1,622", "1,571", "3,193", "50.8", "49.2", "100.0", "103"),
            row("Tsirang", "Town", "1,622", "1,571", "3,193", "50.8", "49.2", "100.0",
                "103"),
            row("Rural", "986", "1003", "1989", "49.6", "50.4", "100.0", "98"),
            row("Barshong", *barshong, "50.2", "49.8", "100.0", "101"),
            row("Patshaling", "565", "586", "1,151", "49.1", "50.9", "100.0", "96"),
            *extra]
    male = 1622 + int(barshong[0]) + 565
    female = 1571 + int(barshong[1]) + 586
    rows.append(row("Both", "Areas", f"{male:,}", f"{female:,}", f"{male + female:,}",
                    "50.2", "49.8", "100.0", "101"))
    return rows


def pages(t22=None):
    return [contents(), table21(), t22 if t22 is not None else table22()]


def reading(page_list):
    return mock.patch.object(bt, "words_by_row",
                             lambda blob, tolerance=2.0: iter(page_list))


class Citizenship(unittest.TestCase):
    def read(self, page_list):
        with reading(page_list):
            read = bt.table(b"", "Tsirang")
        with reading(page_list):
            return read, bt.citizens(b"", "Tsirang", read)

    def test_table_21_is_still_table_21(self):
        read, _ = self.read(pages())
        self.assertEqual(read.printed, 5449)
        self.assertEqual(read.gewogs, {"Barshong": 842, "Patshaling": 1159})
        self.assertEqual(read.towns, {"Tsirang Town": 3448})

    def test_table_22_is_read_under_its_title_not_the_contents_entry(self):
        _, (found, why) = self.read(pages())
        self.assertEqual(why, "")
        self.assertEqual(found.gewogs, {"Barshong": 838, "Patshaling": 1151})
        self.assertEqual(found.towns, {"Tsirang Town": 3193})
        self.assertEqual(found.printed, 3193 + 838 + 1151)

    def test_the_fields_are_citizenship_with_everyone_else_beside_it(self):
        fields = bt.citizenship(838, 842)
        self.assertEqual(fields["ethnicity_basis"], "citizenship")
        self.assertEqual(fields["ethnicity_year"], 2017)
        counts = {r["group"]: r["count"] for r in fields["ethnicity"]}
        self.assertEqual(counts, {"Bhutanese": 838, "Non-Bhutanese": 4})
        self.assertIn("not ethnicity", fields["ethnicity_note"])
        everyone = bt.citizenship(842, 842)
        self.assertEqual([r["group"] for r in everyone["ethnicity"]], ["Bhutanese"])

    def test_the_note_says_what_it_is_and_nothing_of_how_it_was_decided(self):
        note = bt.citizenship(838, 842)["ethnicity_note"]
        self.assertNotIn("owner", note)
        self.assertIn("asks no ethnicity", note)

    def test_a_far_from_even_ratio_names_its_counts_and_the_non_citizens(self):
        # Daga: 6,057 people, 209 females per 1,000 males, 3,853 not Bhutanese.
        text = bt.ratio_context(5010, 1047, 6057, 2204, (1100, 1104))
        self.assertIn("5,010 males and 1,047 females", text)
        self.assertIn("3,853 of the 6,057 are not Bhutanese citizens", text)
        # Table 2.2's sexes are used only where they make its row and fit 2.1's.
        self.assertIn("3,910 of them male and 0 female",
                      bt.ratio_context(5010, 1047, 6057, 2147, (1100, 1047)))
        self.assertNotIn("of them male", bt.ratio_context(5010, 1047, 6057, 2204, (1, 1)))
        # Naro: almost everyone a citizen; the counts are still given.
        naro = bt.ratio_context(163, 87, 250, 249)
        self.assertIn("1 of the 250 is not", naro)
        # An even enough ratio adds nothing.
        self.assertEqual(bt.ratio_context(500, 480, 980, 970), "")
        self.assertEqual(bt.ratio_context(0, 5, 5), "")

    def test_more_bhutanese_than_people_is_refused(self):
        _, (found, why) = self.read(pages(table22(barshong=("430", "419", "849"))))
        self.assertIsNone(found)
        self.assertIn("Barshong", why)

    def test_a_gewog_table_21_does_not_have_is_refused(self):
        extra = [row("Somewhere", "10", "10", "20", "50.0", "50.0", "100.0", "100")]
        t22 = table22(extra=extra)
        t22[-1] = row("Both", "Areas", "2,618", "2,584", "5,202")
        _, (found, why) = self.read(pages(t22))
        self.assertIsNone(found)
        self.assertIn("Somewhere", why)

    def test_rows_short_of_the_closing_row_are_refused(self):
        t22 = table22()
        t22[-1] = row("Both", "Areas", "2,608", "2,574", "5,183")
        _, (found, why) = self.read(pages(t22))
        self.assertIsNone(found)
        self.assertIn("5,183", why)

    def test_town_names_wrapped_above_the_word_town_are_put_back(self):
        # Gasa sets a town's name on one line and "Town" beside its figures
        # on the next; two rows both called "Town" used to stop the run.
        t22 = table22()
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Tsirang")
        t22[at:at + 1] = [row("Tsirang"),
                          row("Town", "1,600", "1,550", "3,150", "50.8", "49.2",
                              "100.0", "103"),
                          row("Damji"),
                          row("Town", "22", "21", "43", "51.2", "48.8", "100.0", "105")]
        _, (found, why) = self.read(pages(t22))
        self.assertEqual(why, "")
        self.assertEqual(found.towns, {"Tsirang Town": 3150, "Damji Town": 43})

    def test_a_refusal_inside_the_reading_costs_only_the_citizenship(self):
        t22 = table22()
        t22.insert(7, row("Barshong", "1", "1", "2", "50.0", "50.0", "100.0", "100"))
        _, (found, why) = self.read(pages(t22))
        self.assertIsNone(found)
        self.assertIn("Table 2.2", why)

    def test_a_title_with_a_colon_is_still_the_title(self):
        t22 = table22()
        t22[0] = row("Table", "2.2:", "Distribution", "of", "Bhutanese", "Population")
        _, (found, why) = self.read(pages(t22))
        self.assertEqual(why, "")
        self.assertEqual(found.gewogs["Barshong"], 838)

    def test_a_gewog_name_cut_short_by_its_wrap_is_the_one_it_begins(self):
        t22 = table22()
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Patshaling")
        t22[at] = row("Patsha-", *[w for _a, _b, w in t22[at][1:]])
        _, (found, why) = self.read(pages(t22))
        self.assertEqual(why, "")
        self.assertEqual(found.gewogs, {"Barshong": 838, "Patshaling": 1151})

    def test_a_name_whole_in_table_22_and_cut_in_table_21_is_table_21s(self):
        # Samtse: Table 2.1 reads "Sang-Ngag-", Table 2.2 the whole name.
        t21 = table21()
        at = next(i for i, r in enumerate(t21) if r[0][2] == "Patshaling")
        t21[at] = row("Patsha-", "567", "592", "1,159")
        t22 = table22()
        page_list = [contents(), t21, t22]
        read, (found, why) = self.read(page_list)
        self.assertIn("Patsha-", read.gewogs)
        self.assertEqual(why, "")
        self.assertEqual(found.gewogs, {"Barshong": 838, "Patsha-": 1151})

    def test_two_town_rows_this_reader_cannot_name_are_kept_apart(self):
        t22 = table22()
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Tsirang")
        t22[at:at + 1] = [row("Town", "1,600", "1,550", "3,150", "50.8", "49.2"),
                          row("Town", "22", "21", "43", "51.2", "48.8")]
        _, (found, why) = self.read(pages(t22))
        self.assertEqual(why, "")
        self.assertEqual(sum(found.towns.values()), 3193)

    def test_a_table_22_with_table_21s_total_is_refused(self):
        # Lhuentse, Paro, Punakha and Trashigang: no non-Bhutanese at all is
        # not what the report says.
        t22 = table22(barshong=("423", "419", "842"))
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Patshaling")
        t22[at] = row("Patshaling", "567", "592", "1,159")
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Tsirang")
        t22[at] = row("Tsirang", "Town", "1,854", "1,594", "3,448")
        t22[-1] = row("Both", "Areas", "2,844", "2,605", "5,449")
        _, (found, why) = self.read(pages(t22))
        self.assertIsNone(found)
        self.assertIn("same total", why)

    def test_a_header_word_broken_at_its_slash_is_still_the_header(self):
        # Bumthang: "Gewog/" on a line of its own, "Town Male Female ..."
        # on the next.
        t22 = table22()
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Gewog/Town")
        t22[at:at + 1] = [row("Gewog/"),
                          row("Town", "Male", "Female", "Total", "Male", "Female",
                              "Total", "Sex", "Ratio")]
        _, (found, why) = self.read(pages(t22))
        self.assertEqual(why, "")
        self.assertEqual(found.gewogs, {"Barshong": 838, "Patshaling": 1151})
        self.assertEqual(found.towns, {"Tsirang Town": 3193})

    def test_labels_set_left_of_the_header_word_are_read(self):
        # Gasa: "Gewog/Town" starts ten points right of the labels under it.
        def shifted(cells, by):
            return [(x0 + by, x1 + by, t) for x0, x1, t in cells]
        t22 = table22()
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Gewog/Town")
        t22[at] = shifted(t22[at], 10.0)
        _, (found, why) = self.read(pages(t22))
        self.assertEqual(why, "")
        self.assertEqual(found.gewogs, {"Barshong": 838, "Patshaling": 1151})
        self.assertEqual(found.printed, 3193 + 838 + 1151)

    def test_labels_far_left_of_the_header_word_are_still_cut(self):
        # Past the slack a label is the prose beside the table, and the
        # table does not reconcile.
        def shifted(cells, by):
            return [(x0 + by, x1 + by, t) for x0, x1, t in cells]
        t22 = table22()
        at = next(i for i, r in enumerate(t22) if r[0][2] == "Gewog/Town")
        t22[at] = shifted(t22[at], 30.0)
        _, (found, why) = self.read(pages(t22))
        self.assertIsNone(found)

    def test_table_21_headed_name_is_table_21_not_table_22(self):
        # Paro and Lhuentse head the column "Name". Read without the title,
        # the first header this reader knew was Table 2.2's, and the
        # Bhutanese population went on the map as everyone.
        t21 = table21()
        at = next(i for i, r in enumerate(t21) if r[0][2] == "Gewog/Town")
        t21[at] = row("Name", "Male", "Female", "Total")
        read, (found, why) = self.read([contents(), t21, table22()])
        self.assertEqual(read.printed, 5449)
        self.assertEqual(read.gewogs, {"Barshong": 842, "Patshaling": 1159})
        self.assertEqual(why, "")
        self.assertEqual(found.printed, 3193 + 838 + 1151)

    def test_table_21_headed_gewog_space_slash_town_is_read(self):
        # Punakha: "Gewog /Town", two words.
        t21 = table21()
        at = next(i for i, r in enumerate(t21) if r[0][2] == "Gewog/Town")
        t21[at] = row("Gewog", "/Town", "Male", "Female", "Total")
        read, _ = self.read([contents(), t21, table22()])
        self.assertEqual(read.printed, 5449)

    def test_table_21_with_its_header_on_two_lines_is_read(self):
        # Trashigang: "Gewog/Town Persons" over "Male Female Total".
        t21 = table21()
        at = next(i for i, r in enumerate(t21) if r[0][2] == "Gewog/Town")
        t21[at:at + 1] = [row("Gewog/Town", "Persons"),
                          [(c[0] + 60.0, c[1] + 60.0, c[2])
                           for c in row("Male", "Female", "Total")]]
        read, _ = self.read([contents(), t21, table22()])
        self.assertEqual(read.printed, 5449)
        self.assertEqual(read.gewogs, {"Barshong": 842, "Patshaling": 1159})

    def test_table_22_is_never_taken_for_table_21(self):
        # A Table 2.1 header nothing here can recognise, and no title on its
        # page: the ungated read finds Table 2.2 and the run refuses it.
        t21 = table21()
        t21[0] = row("Population", "Distribution", "by", "Gewog")
        at = next(i for i, r in enumerate(t21) if r[0][2] == "Gewog/Town")
        t21[at] = row("Place", "Male", "Female", "Total")
        with reading([contents(), t21, table22()]), \
                self.assertRaises(SystemExit) as stop:
            bt.table(b"", "Tsirang")
        self.assertIn("Table 2.2", str(stop.exception))

    def test_no_table_22_at_all_is_said(self):
        _, (found, why) = self.read([contents(), table21()])
        self.assertIsNone(found)
        self.assertIn("not found", why)


if __name__ == "__main__":
    unittest.main()
