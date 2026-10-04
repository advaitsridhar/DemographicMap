"""Pakistan Census 2023 Tables 4 and 10: the row reader and its checks.

The fixtures are built as pdfplumber's words would arrive: a row is a list
of (left x, right x, text), and a figure the Bureau's typesetting split --
"2 ,133,005" -- is two words with no gap between them, which is what
``pakistan.printed`` rejoins. No PDF and no network.
"""

import unittest
from collections import Counter

from scripts.fetch_census import pakistan, pakistan_census_tables as t


def row(*cells: str):
    """Cells separated by a column gap; '^' splits one cell into touching words."""
    out, x = [], 10.0
    for cell in cells:
        for i, word in enumerate(cell.split("^")):
            width = 4.0 * len(word)
            out.append((x, x + width, word))
            x += width            # touching: the next word starts where this ends
        x += 20.0                 # a column gap
    return out


def label_row(label: str, *cells: str):
    """A table row as the Bureau sets it: the label in its own column at the
    left margin, each figure in a column of its own at a fixed position."""
    out, x = [], 10.0
    for word in label.split():
        out.append((x, x + 4.0 * len(word), word))
        x += 4.0 * len(word) + 4.0
    for i, cell in enumerate(cells):
        x = 100.0 + 45.0 * i
        for word in cell.split("^"):
            width = 4.0 * len(word)
            out.append((x, x + width, word))
            x += width
    return out


def block(name: str, ages: dict[int, tuple[int, int]], *, tg: int = 0,
          blank_tg_at: int | None = None):
    """A Table 4 district block from {age: (males, females)}, 0..75."""
    rows = [row(*f"{name} DISTRICT".split())]
    males = sum(m for m, _ in ages.values())
    females = sum(f for _, f in ages.values())
    total = males + females + tg
    rows.append(label_row("ALL AGES", f"{total}", f"{males}", f"{females}",
                          f"{tg}" if tg else "-", *["-"] * 8))
    # The transgender persons, all at age 20, as a table would print them:
    # in the persons column and in neither sex.
    for low in range(0, 75, 5):
        m = sum(ages[a][0] for a in range(low, low + 5))
        f = sum(ages[a][1] for a in range(low, low + 5))
        g = tg if low == 20 else 0
        rows.append(label_row(f"{low:02d} -- {low + 4:02d}", f"{m + f + g}", f"{m}",
                              f"{f}", f"{g}" if g else "-", *["-"] * 8))
        for age in range(low, low + 5):
            m, f = ages[age]
            g = tg if age == 20 else 0
            label = "BELOW 1" if age == 0 else f"{age:02d}"
            tg_cell = [] if age == blank_tg_at else [f"{g}" if g else "-"]
            rows.append(label_row(label, f"{m + f + g}", f"{m}", f"{f}", *tg_cell,
                                  *["-"] * 8))
    m, f = ages[75]
    rows.append(label_row("75 & ABOVE", f"{m + f}", f"{m}", f"{f}", "-", *["-"] * 8))
    return rows


def ages_for(scale: int = 100):
    """A young population: fewer people at each older age."""
    return {a: (scale * (80 - a), scale * (80 - a) + a) for a in range(0, 76)}


class TestRows(unittest.TestCase):
    def test_split_figure_is_rejoined(self):
        match, figures = t.labelled(row("ALL", "AGES", "2^,133,005", "1^,071,693",
                                        "1^,061,231", "8^1"))
        self.assertEqual(match.group(0), "ALL AGES")
        self.assertEqual(figures[:4], [2133005, 1071693, 1061231, 81])

    def test_single_year_label_is_not_a_figure(self):
        match, figures = t.labelled(row("01", "4^5,268", "2^3,486", "21,782", "-"))
        self.assertEqual(match.group(4), "01")
        self.assertEqual(figures, [45268, 23486, 21782, 0])

    def test_column_numbers_are_skipped(self):
        match, figures = t.labelled(row(*[str(i) for i in range(1, 14)]))
        self.assertIsNone(match)
        self.assertEqual(figures, [])

    def test_sexes_refuse_a_shifted_row(self):
        with self.assertRaises(SystemExit):
            t.sexes([100, 60, 70, 0], "x")          # sexes exceed persons

    def test_sexes_take_a_blank_transgender_cell(self):
        self.assertEqual(t.sexes([50842, 27321, 23521, 27432, 14470, 12962, 0,
                                  23410, 12851, 10559, 0], "x"),
                         (50842, 27321, 23521))


class TestTable4(unittest.TestCase):
    def test_block_reads_and_checks(self):
        ages = ages_for()
        pages = [block("ATTOCK", ages, tg=7, blank_tg_at=12)
                 + [row("FATEH", "JANG", "TEHSIL"), label_row("ALL AGES", "5", "3", "2")]]
        out = t.ages_from_pages(pages, "punjab")
        self.assertEqual(set(out), {"ATTOCK"})
        t.check_ages("ATTOCK", out["ATTOCK"])
        got = out["ATTOCK"]["ages"]["T"]
        self.assertEqual(got[12], sum(ages[12]))
        self.assertEqual(got[20], sum(ages[20]) + 7)
        expected = Counter({a: m + f for a, (m, f) in ages.items()})
        expected[20] += 7
        self.assertEqual(
            t.median_single(dict(got), open_from=75),
            t.median_single(dict(expected), open_from=75))

    def test_page_break_inside_a_block(self):
        rows = block("ATTOCK", ages_for())
        cut = len(rows) // 2
        pages = [rows[:cut], [row(*[str(i) for i in range(1, 14)])] + rows[cut:]]
        out = t.ages_from_pages(pages, "punjab")
        t.check_ages("ATTOCK", out["ATTOCK"])

    def test_a_label_whose_figures_slipped_to_the_next_line(self):
        # Attock's age 57, as the first row of a continuation page: the label
        # beside the repeated heading's mangled glyphs, the figures a few
        # points lower on a line of their own.
        rows = block("ATTOCK", ages_for())
        at = next(i for i, cells in enumerate(rows)
                  if t.line_of(cells).startswith("57 "))
        figures = rows[at][1:]
        rows[at:at + 1] = [[rows[at][0], (300.0, 330.0, "0,781AT"),
                            (331.0, 340.0, "I,S6T1R7ICT")], figures]
        out = t.ages_from_pages([rows], "punjab")
        t.check_ages("ATTOCK", out["ATTOCK"])
        self.assertEqual(out["ATTOCK"]["ages"]["T"][57], sum(ages_for()[57]))

    def test_the_heading_repeated_on_a_new_page_is_not_a_new_block(self):
        rows = block("ATTOCK", ages_for())
        cut = len(rows) // 2
        pages = [rows[:cut], [row("ATTOCK", "DISTRICT")] + rows[cut:]]
        out = t.ages_from_pages(pages, "punjab")
        t.check_ages("ATTOCK", out["ATTOCK"])

    def test_interrupted_block_is_refused(self):
        rows = block("ATTOCK", ages_for())
        with self.assertRaises(SystemExit):
            t.ages_from_pages([rows[:20] + block("JHELUM", ages_for())], "punjab")

    def test_islamabad_heading(self):
        rows = block("X", ages_for())
        rows[0] = row("ISLAMABAD", "CAPITAL", "TERRITORY")
        out = t.ages_from_pages([rows], "ict")
        self.assertEqual(set(out), {"ISLAMABAD"})

    def test_a_wrong_group_row_is_caught(self):
        rows = block("ATTOCK", ages_for())
        for i, cells in enumerate(rows):
            if t.line_of(cells).startswith("05 -- 09"):
                rows[i] = label_row("05 -- 09", "1", "1", "0", "-", *["-"] * 8)
        out = t.ages_from_pages([rows], "punjab")
        with self.assertRaises(SystemExit):
            t.check_ages("ATTOCK", out["ATTOCK"])


class TestTable10(unittest.TestCase):
    def test_first_all_ages_row_is_the_district(self):
        pages = [[row("ATTOCK", "DISTRICT"), row("ALL", "SEXES"),
                  row("ALL", "AGES", "2,063,449", "68,573", "22", "18", "943",
                      "1,507,157", "38,687", "14", "14", "484", "556292",
                      "29,886", "8", "4", "459"),
                  row("MALE"), row("ALL", "AGES", "1", "2", "3", "4", "5")]]
        out = t.nationality_from_pages(pages, "punjab")
        self.assertEqual(out["ATTOCK"], {"PAKISTANI": 2063449, "AFGHANI": 68573,
                                         "BANGALI": 22, "CHINESE": 18, "OTHERS": 943})
        self.assertEqual(sum(out["ATTOCK"].values()), 2133005)

    def test_fields_are_nationality_not_ethnicity(self):
        fields = t.nationality_fields({"PAKISTANI": 90, "AFGHANI": 10, "BANGALI": 0,
                                       "CHINESE": 0, "OTHERS": 0}, 100, "u")
        self.assertEqual(fields["ethnicity_basis"], "nationality")
        self.assertEqual([g["group"] for g in fields["ethnicity"]],
                         ["Pakistani", "Afghan"])
        self.assertIn("not as ethnicity", fields["ethnicity_note"])


class TestMerges(unittest.TestCase):
    def test_drawn_parent_takes_its_carved_out_district(self):
        found = {"SHEIKHUPURA": {"A": 4049377}, "NANKANA SAHIB": {"A": 1634871},
                 "LAHORE": {"A": 1}}
        assembled = t.merge_parts(found, t.combine_counts)
        self.assertEqual(found["SHEIKHUPURA"], {"A": 5684248})
        self.assertNotIn("NANKANA SAHIB", found)
        self.assertEqual(assembled["SHEIKHUPURA"], ("SHEIKHUPURA", "NANKANA SAHIB"))

    def test_partial_merge_is_refused(self):
        with self.assertRaises(SystemExit):
            t.merge_parts({"KARACHI EAST": {"A": 1}}, t.combine_counts)

    def test_table9_merge_keeps_the_parents_name(self):
        found = {"KHARAN": {"TOTAL": 10, "Muslim": 10},
                 "WASHUK": {"TOTAL": 5, "Muslim": 5}}
        assembled = pakistan.merge("Balochistan", found, ["TOTAL", "Muslim"])
        self.assertEqual(found, {"KHARAN": {"TOTAL": 15, "Muslim": 15}})
        self.assertIn("Washuk", pakistan.merged_note("KHARAN", assembled["KHARAN"]))

    def test_every_merge_says_why(self):
        self.assertEqual(set(pakistan.MERGED), set(pakistan.MERGED_WHY))


if __name__ == "__main__":
    unittest.main()
