"""Bhutan 2017: the dzongkhag reports' annex Tables A2.6 and A2.7.

Rows arrive as pdfplumber's words would -- (left x, right x, text) -- in the
order the report prints them: A2.6's single years under its heading, then
A2.7's gewogs, each its chiwogs and an All Chiwogs block. Most reports print
A2.7 on its side, and a page of that is built the way the PDF reads: a row
per age group, a column per series, every word's letters reversed. No PDF,
no network.
"""

import unittest

from scripts.fetch_census import bhutan as bt


def row(*words: str):
    out, x = [], 10.0
    for word in words:
        out.append((x, x + 4.0 * len(word), word))
        x += 4.0 * len(word) + 8.0
    return out


def at(*pairs):
    """Words at given left edges: at((10, "Age"), (40, "Male"))."""
    return [(x, x + 4.0 * len(w), w) for x, w in pairs]


# The A2.6 header's columns: left edges of Age, then the nine figure columns.
HEADER_X = [47, 107, 136, 181, 218, 248, 292, 330, 360, 404]


def header():
    return at(*zip(HEADER_X, bt.AGE_HEADER))


def figures_row(label, values, blanks=()):
    """An A2.6 row, each figure right-aligned under its header word."""
    cells = [(47.0, 47.0 + 4 * len(label), label)]
    for i, value in enumerate(values):
        if i in blanks:
            continue
        right = HEADER_X[i + 1] + 4.0 * len(bt.AGE_HEADER[i + 1])
        text = f"{value:,}"
        cells.append((right - 4.0 * len(text), right, text))
    return cells


def single_years(oldest: int = 90):
    """A2.6 rows: at age a, urban 1 man and 1 woman, rural (90 - a) of each."""
    rows = [row("Table", "A2.6", "Population", "by", "Age,", "Sex", "and", "Area"),
            row("Urban", "Rural", "Both", "Areas"), header()]
    totals = [0] * 9
    for age in range(0, oldest + 1):
        r = max(0, 90 - age)
        values = [1, 1, 2, r, r, 2 * r, 1 + r, 1 + r, 2 + 2 * r]
        totals = [t + v for t, v in zip(totals, values)]
        rows.append(figures_row(str(age), values))
    rows.append([(47.0, 59.0, "All"), (62.0, 78.0, "Ages")]
                + figures_row("x", totals)[1:])
    return rows, totals


def gewog_block(name: str, males: list[int], females: list[int]):
    """A gewog's heading, one chiwog, and its All Chiwogs rows."""
    persons = [m + f for m, f in zip(males, females)]
    def line(label, values):
        return row(*label.split(), *map(str, values), str(sum(values)))
    return [row(name.upper()),
            line("Somechiwog", persons), line("Male", males), line("Female", females),
            line("All Chiwogs", persons), line("Male", males), line("Female", females)]


MALES = [10, 9, 8, 7, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 1]
FEMALES = [11, 9, 8, 8, 6, 6, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1]
LABELS = [f"{a}-{a + 4}" for a in range(0, 75, 5)] + ["75+", "Total"]


def report():
    singles, totals = single_years()
    a27 = [row("Table", "A2.7", "Population", "by", "Age,", "Sex,", "Chiwog", "and",
               "Gewog/Town"),
           row("Chiwog/Sex", "0-4", "5-9", "75+", "Total")]
    a27 += gewog_block("Barshong", MALES, FEMALES)
    a27 += gewog_block("Kilkhorthang", FEMALES, MALES)
    # A town's heading, whose rows must not be read as Kilkhorthang's.
    a27 += [row("DAMPHU", "TOWN"), row("All", "Chiwogs", *["1"] * 16, "16")]
    tail = [row("Table", "A3.1", "Population", "6", "Years", "and", "Above")]
    return [singles, a27, tail], totals


class Read2017:
    """Table 2.1 as bhutan.table returns it, for the checks to hold against."""

    def __init__(self, printed, gewogs, sexes):
        self.printed, self.gewogs, self.sexes = printed, gewogs, sexes


def table21(totals):
    m, f = sum(MALES), sum(FEMALES)
    return Read2017(totals[8], {"Barshong": m + f, "Kilkhorthang": m + f},
                    {"Barshong": (m, f), "Kilkhorthang": (f, m)})


def checked(annex, read, national=None):
    """Every outcome: the dzongkhag's reason and each gewog's."""
    reason, note = bt.single_outcome("Tsirang", annex, read, national)
    gewogs = {name: bt.gewog_outcome(name, annex["gewogs"].get(name), read)
              for name in read.gewogs}
    return reason, note, gewogs


class Annex(unittest.TestCase):
    def test_both_tables_are_read_and_checked(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        self.assertEqual(set(annex["gewogs"]), {"Barshong", "Kilkhorthang"})
        self.assertEqual(len(annex["single"]), 91)
        reason, note, gewogs = checked(annex, table21(totals))
        self.assertIsNone(reason)
        self.assertEqual(gewogs, {"Barshong": None, "Kilkhorthang": None})
        self.assertGreater(bt.dzongkhag_median(annex)["median_age"]["value"], 0)
        gewog = bt.gewog_median(annex["gewogs"]["Barshong"])
        self.assertIn("five-year group", gewog["median_age_note"])

    def test_a_gewog_that_is_not_table_21s_loses_only_its_own_median(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        read = table21(totals)
        read.gewogs["Barshong"] += 1
        reason, _note, gewogs = checked(annex, read)
        self.assertIsNone(reason)
        self.assertIn("Table 2.1", gewogs["Barshong"])
        self.assertIsNone(gewogs["Kilkhorthang"])
        self.assertEqual(bt.age_gap(gewogs["Barshong"])["median_age"]["status"],
                         "not_available")

    def test_a_missing_year_declines_the_dzongkhag(self):
        pages, totals = report()
        pages[0] = [r for r in pages[0] if r[0][2] != "40"]
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        reason, _note, _gewogs = checked(annex, table21(totals))
        self.assertIn("40", reason)

    def test_a_gewog_with_no_age_block_is_named(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong"])
        _reason, _note, gewogs = checked(annex, table21(totals))
        self.assertIn("no All Chiwogs block", gewogs["Kilkhorthang"])

    def test_the_median_of_the_single_years(self):
        pages, _totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        got = bt.dzongkhag_median(annex)["median_age"]["value"]
        # Both areas hold 2 + 2(90 - a) people at age a: the middle of 8,372
        # people falls in the year a little past 26.
        self.assertTrue(26 <= got < 27, got)

    def test_a_gewog_running_onto_the_next_page(self):
        # Bumthang's Ura: the heading and a chiwog on one page, then the
        # table's title printed again and the All Chiwogs rows under it.
        pages, totals = report()
        a27 = pages[1]
        at_ = next(i for i, r in enumerate(a27) if r[0][2] == "KILKHORTHANG") + 2
        title = row("Table", "A2.7", "Population", "by", "Age,", "Sex,", "Chiwog",
                    "and", "Gewog/Town,", "Tsirang", "Dzongkhag", "2017")
        pages[1:2] = [a27[:at_], [row("ANNEX", "2:", "Statistical", "Tables"), title,
                                  row("Gewog/Town/"), *a27[at_:]]]
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        self.assertEqual(set(annex["gewogs"]), {"Barshong", "Kilkhorthang"})
        _reason, _note, gewogs = checked(annex, table21(totals))
        self.assertEqual(gewogs, {"Barshong": None, "Kilkhorthang": None})


class SingleYears(unittest.TestCase):
    def test_a_blank_cell_is_placed_by_its_column_and_counted_nought(self):
        # Gasa's age 51: no urban males, the cell left blank.
        pages, totals = report()
        a26 = pages[0]
        i = next(k for k, r in enumerate(a26) if r[0][2] == "90")
        a26[i] = figures_row("90", [0, 1, 1, 0, 0, 0, 0, 1, 1], blanks=(0,))
        totals = [t - v + w for t, v, w in
                  zip(totals, [1, 1, 2, 0, 0, 0, 1, 1, 2], [0, 1, 1, 0, 0, 0, 0, 1, 1])]
        a26[-1] = [(47.0, 59.0, "All"), (62.0, 78.0, "Ages")] + figures_row("x", totals)[1:]
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        self.assertEqual(annex["single"][90], (0, 1, 1, 0, 0, 0, 0, 1, 1))
        self.assertEqual(annex["placed"], [90])
        read = table21(totals)
        reason, _note, _gewogs = checked(annex, read)
        self.assertIsNone(reason)

    def test_an_all_ages_row_set_in_two_lines_is_put_back_together(self):
        # Monggar: two of the All Ages figures a little below the others.
        pages, totals = report()
        a26 = pages[0]
        whole = figures_row("x", totals)[1:]
        a26[-1] = [(47.0, 59.0, "All"), (62.0, 78.0, "Ages")] + whole[:7]
        a26.append(whole[7:])
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        self.assertEqual(annex["all_ages"], tuple(totals))

    def test_rows_whose_sexes_miss_their_total_are_named_not_refused(self):
        # Chhukha past 80: the totals add up everywhere, the sexes do not.
        pages, totals = report()
        a26 = pages[0]
        i = next(k for k, r in enumerate(a26) if r[0][2] == "88")
        old = [1, 1, 2, 2, 2, 4, 3, 3, 6]
        new = [1, 1, 3, 2, 2, 4, 3, 3, 7]
        a26[i] = figures_row("88", new)
        totals = [t - o + n for t, o, n in zip(totals, old, new)]
        a26[-1] = [(47.0, 59.0, "All"), (62.0, 78.0, "Ages")] + figures_row("x", totals)[1:]
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        read = table21(totals)
        reason, note, _gewogs = checked(annex, read)
        self.assertIsNone(reason)
        self.assertIn("ages 88", note)

    def test_a_short_table_21_needs_the_national_figure(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        read = table21(totals)
        read.printed -= 100
        reason, _note, _gewogs = checked(annex, read, national=None)
        self.assertIn("Table 2.1", reason)
        reason, note, _gewogs = checked(annex, read, national=bt.NATIONAL_ANALYSED)
        self.assertIsNone(reason)
        self.assertIn("100 more", note)


def sideways(columns, labels, title=True):
    """A page of A2.7 on its side.

    ``columns`` maps a left edge to the 17 figures of that series (16 groups,
    then the total); ``labels`` is a list of (left edge, label) words, read the
    right way round. Everything comes out reversed, as the PDF's text does.
    """
    rows = [at((234, "ANNEX"), (264, "2:"), (274, "Statistical"), (317, "Tables"))]
    for index in range(16, -1, -1):
        cells = [(71.0, 91.0, LABELS[index][::-1])]
        for x, values in sorted(columns.items()):
            text = f"{values[index]:,}"[::-1]
            cells.append((x, x + 4.0, text))
        rows.append(cells)
    if title:
        rows.append(at((42, "A2.7"[::-1])))
    for x, word in labels:
        rows.append(at((x, word[::-1])))
    rows.append(at((42, "Table"[::-1])))
    return rows


def series(values):
    return [*values, sum(values)]


class OnItsSide(unittest.TestCase):
    def pages(self):
        persons = [m + f for m, f in zip(MALES, FEMALES)]
        swapped = [f + m for m, f in zip(MALES, FEMALES)]
        first = sideways(
            {97: series(persons), 110: series(MALES), 124: series(FEMALES),
             137: series(persons), 151: series(MALES), 164: series(FEMALES),
             191: series(swapped), 205: series(FEMALES), 218: series(MALES)},
            [(83, "BARSHONG"), (97, "Somechiwog"), (110, "Male"), (124, "Female"),
             (137, "Chiwogs"), (137, "All"), (151, "Male"), (164, "Female"),
             (178, "KILKHORTHANG"), (191, "Otherchiwog"), (205, "Male"),
             (218, "Female")])
        second = sideways(
            {97: series(swapped), 110: series(FEMALES), 124: series(MALES),
             151: series([1] * 16), 164: series([1] * 16), 178: series([0] * 16)},
            [(97, "Chiwogs"), (97, "All"), (110, "Male"), (124, "Female"),
             (137, "TOWN"), (137, "DAMPHU"), (151, "Areas"), (151, "Local"),
             (151, "All"), (164, "Male"), (178, "Female")])
        return first, second

    def test_a_table_on_its_side_is_read_the_right_way_round(self):
        first, second = self.pages()
        singles, totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        self.assertEqual(annex["rotated"], 2)
        self.assertEqual(set(annex["gewogs"]), {"Barshong", "Kilkhorthang"})
        self.assertEqual(annex["gewogs"]["Barshong"]["male"], series(MALES))
        self.assertEqual(annex["gewogs"]["Kilkhorthang"]["male"], series(FEMALES))
        _reason, _note, gewogs = checked(annex, table21(totals))
        self.assertEqual(gewogs, {"Barshong": None, "Kilkhorthang": None})
        self.assertEqual(annex["problems"], [])

    def test_a_block_under_a_name_table_21_does_not_know_is_nobodys(self):
        first, second = self.pages()
        first = [[(x0, x1, "GNOHSRABX" if t == "GNOHSRAB" else t) for x0, x1, t in r]
                 for r in first]
        singles, totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        self.assertNotIn("Barshong", annex["gewogs"])
        self.assertTrue(any("XBARSHONG" in p for p in annex["problems"]))

    def test_a_label_a_line_away_from_its_figures(self):
        first, second = self.pages()
        at_ = next(i for i, r in enumerate(first) if r[0][2] == "4-0")
        label, figures = first[at_][:1], first[at_][1:]
        first[at_:at_ + 1] = [label, figures]
        singles, totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        self.assertEqual(annex["gewogs"]["Barshong"]["persons"][0], MALES[0] + FEMALES[0])
        _reason, _note, gewogs = checked(annex, table21(totals))
        self.assertEqual(gewogs, {"Barshong": None, "Kilkhorthang": None})

    def test_a_heading_with_a_dash_is_still_a_heading(self):
        # An unrecognised name in capitals must close the gewog before it,
        # whatever punctuation it carries: "NA–RANG" with an en dash.
        first, second = self.pages()
        first = [[(x0, x1, "GNAR–AN" if t == "KILKHORTHANG"[::-1] else t) for x0, x1, t in r]
                 for r in first]
        singles, _totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        self.assertNotIn("Kilkhorthang", annex["gewogs"])
        self.assertEqual(set(annex["gewogs"]), {"Barshong"})

    def test_table_21_chooses_between_two_blocks_under_one_name(self):
        first, second = self.pages()
        # Kilkhorthang's heading unread: its block falls to Barshong as well.
        first = [[(x0, x1, "kilkhorthang"[::-1] if t == "KILKHORTHANG"[::-1] else t)
                  for x0, x1, t in r] for r in first]
        singles, totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        self.assertTrue(annex["alternates"].get("Barshong"))
        read = table21(totals)
        block, why, _note = bt.choose_gewog("Barshong", annex, read, False)
        self.assertIsNone(why)
        self.assertEqual(block["male"], series(MALES))

    def test_a_short_table_21_admits_a_little_more_and_says_so(self):
        first, second = self.pages()
        singles, totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        read = table21(totals)
        m, f = read.sexes["Barshong"]
        read.gewogs["Barshong"] -= 2
        read.sexes["Barshong"] = (m - 1, f - 1)
        _block, why, _note = bt.choose_gewog("Barshong", annex, read, False)
        self.assertIn("Table 2.1", why)
        block, why, note = bt.choose_gewog("Barshong", annex, read, True)
        self.assertIsNone(why)
        self.assertIn("2 more than", note)
        # Never fewer than Table 2.1, and never by more than the limit.
        read.gewogs["Barshong"] += 50
        _block, why, _note = bt.choose_gewog("Barshong", annex, read, True)
        self.assertIsNotNone(why)

    def test_a_figure_under_no_column_spoils_the_page(self):
        first, second = self.pages()
        first[5].append((300.0, 304.0, "9"))
        singles, _totals = single_years()
        annex = bt.annex_ages([singles, first, second], ["Barshong", "Kilkhorthang"])
        self.assertNotIn("Barshong", annex["gewogs"])
        self.assertTrue(annex["problems"])


if __name__ == "__main__":
    unittest.main()
