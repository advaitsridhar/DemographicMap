"""Bhutan 2017: the dzongkhag reports' annex Tables A2.6 and A2.7.

Rows arrive as pdfplumber's words would -- (left x, right x, text) -- in the
order the report prints them: A2.6's single years under its heading, then
A2.7's gewogs, each its chiwogs and an All Chiwogs block. No PDF, no network.
"""

import unittest

from scripts.fetch_census import bhutan as bt


def row(*words: str):
    out, x = [], 10.0
    for word in words:
        out.append((x, x + 4.0 * len(word), word))
        x += 4.0 * len(word) + 8.0
    return out


def single_years(oldest: int = 90):
    """A2.6 rows: at age a, urban 1 man and 1 woman, rural (90 - a) of each."""
    rows = [row("Table", "A2.6", "Population", "by", "Age,", "Sex", "and", "Area"),
            row("Urban", "Rural", "Both", "Areas")]
    totals = [0] * 9
    for age in range(0, oldest + 1):
        r = max(0, 90 - age)
        values = [1, 1, 2, r, r, 2 * r, 1 + r, 1 + r, 2 + 2 * r]
        totals = [t + v for t, v in zip(totals, values)]
        rows.append(row(str(age), *map(str, values)))
    rows.append(row("All", "Ages", *(f"{v:,}" for v in totals)))
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


class Annex(unittest.TestCase):
    def test_both_tables_are_read_and_checked(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        self.assertEqual(set(annex["gewogs"]), {"Barshong", "Kilkhorthang"})
        self.assertEqual(len(annex["single"]), 91)
        bt.check_annex("Tsirang", annex, table21(totals))
        self.assertGreater(bt.dzongkhag_median(annex)["median_age"]["value"], 0)
        gewog = bt.gewog_median(annex["gewogs"]["Barshong"])
        self.assertIn("five-year group", gewog["median_age_note"])

    def test_a_gewog_that_is_not_table_21s_is_refused(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        read = table21(totals)
        read.gewogs["Barshong"] += 1
        with self.assertRaises(SystemExit):
            bt.check_annex("Tsirang", annex, read)

    def test_a_missing_year_is_refused(self):
        pages, totals = report()
        pages[0] = [r for r in pages[0] if r[0][2] != "40"]
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        with self.assertRaises(SystemExit):
            bt.check_annex("Tsirang", annex, table21(totals))

    def test_a_gewog_with_no_age_block_is_refused(self):
        pages, totals = report()
        annex = bt.annex_ages(pages, ["Barshong"])
        read = table21(totals)
        with self.assertRaises(SystemExit):
            bt.check_annex("Tsirang", annex, read)

    def test_a_gewog_running_onto_the_next_page(self):
        # Bumthang's Ura: the heading and a chiwog on one page, then the
        # table's title printed again and the All Chiwogs rows under it.
        pages, totals = report()
        a27 = pages[1]
        at = next(i for i, r in enumerate(a27) if r[0][2] == "KILKHORTHANG") + 2
        title = row("Table", "A2.7", "Population", "by", "Age,", "Sex,", "Chiwog",
                    "and", "Gewog/Town,", "Tsirang", "Dzongkhag", "2017")
        pages[1:2] = [a27[:at], [row("ANNEX", "2:", "Statistical", "Tables"), title,
                                 row("Gewog/Town/"), *a27[at:]]]
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        self.assertEqual(set(annex["gewogs"]), {"Barshong", "Kilkhorthang"})
        bt.check_annex("Tsirang", annex, table21(totals))

    def test_the_median_of_the_single_years(self):
        pages, _totals = report()
        annex = bt.annex_ages(pages, ["Barshong", "Kilkhorthang"])
        got = bt.dzongkhag_median(annex)["median_age"]["value"]
        # Both areas hold 2 + 2(90 - a) people at age a: the middle of 8,372
        # people falls in the year a little past 26.
        self.assertTrue(26 <= got < 27, got)


if __name__ == "__main__":
    unittest.main()
