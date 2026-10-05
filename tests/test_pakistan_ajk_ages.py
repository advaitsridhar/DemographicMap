"""Azad Jammu and Kashmir: the yearbook's Table 15.8, single years by sex.

Rows are built as pdfplumber's words would arrive -- (left x, right x, text)
-- with twelve figures after each label: rural, urban and the territory's own
male, female, transgender and total. No PDF and no network.
"""

import unittest

from scripts.fetch_census import pakistan as pk


def row(*words: str):
    out, x = [], 10.0
    for word in words:
        out.append((x, x + 4.0 * len(word), word))
        x += 4.0 * len(word) + 20.0
    return out


def figures(m: int, f: int, t: int = 0) -> list[str]:
    """Twelve cells: rural and urban halves, then the territory."""
    def cells(a, b, c):
        return [f"{a:,}", f"{b:,}", f"{c:,}" if c else "-", f"{a + b + c:,}"]
    return (cells(m - m // 2, f - f // 2, 0) + cells(m // 2, f // 2, t)
            + cells(m, f, t))


def table(misprint_62: bool = True):
    """Table 15.8 over two pages: everyone aged a has 100 - a males, 110 - a females."""
    caption = row("Table:15.8", "Age", "Group", "and", "Gender-wise", "Rural", "&",
                  "Urban", "Population", "of", "AJ&K", "(Census", "2017)")
    pages, rows = [], [caption, row(*[str(i) for i in range(1, 14)])]
    total_m = total_f = 0
    for low in range(0, 75, 5):
        m = sum(100 - a for a in range(low, low + 5))
        f = sum(110 - a for a in range(low, low + 5))
        rows.append(row(f"{low}-{low + 4}", *figures(m, f)))
        for a in range(low, low + 5):
            label = ["Below", "1"] if a == 0 else [str(a)]
            if misprint_62 and a == 62:
                label = ["61"]
            rows.append(row(*label, *figures(100 - a, 110 - a)))
        total_m, total_f = total_m + m, total_f + f
        if low == 35:
            pages.append(rows)
            rows = [caption]
    rows.append(row("75", "+", *figures(30, 40, 2)))
    rows.append(row("Total", *figures(total_m + 30, total_f + 40, 2)))
    pages.append(rows)
    return pages, total_m + total_f + 72


class Table158(unittest.TestCase):
    def test_reads_both_pages_and_the_misprinted_label(self):
        pages, people = table()
        got = pk.ajk_ages_from_pages(pages)
        self.assertEqual(set(got["ages"]), set(range(0, 76)))
        self.assertEqual(got["ages"][62][:2], (38, 48))
        self.assertEqual(got["ages"][75], (30, 40, 2, 72))
        pk.ajk_ages_check(got, people)

    def test_a_population_other_than_table_15_24s_is_refused(self):
        pages, people = table()
        got = pk.ajk_ages_from_pages(pages)
        with self.assertRaises(SystemExit):
            pk.ajk_ages_check(got, people + 1)

    def test_a_lost_row_is_caught_by_its_group(self):
        pages, people = table(misprint_62=False)
        pages[1] = [r for r in pages[1] if r[0][2] != "47"]
        got = pk.ajk_ages_from_pages(pages)
        with self.assertRaises(SystemExit):
            pk.ajk_ages_check(got, people)

    def test_fields(self):
        pages, people = table()
        got = pk.ajk_ages_from_pages(pages)
        fields = pk.ajk_age_fields(got, " shape")
        self.assertEqual(fields["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(fields["median_age"]["year"], 2017)
        self.assertTrue(fields["sex_ratio_note"].endswith(" shape"))
        self.assertIn("2 transgender", fields["sex_ratio_note"])

    def test_no_caption_is_a_lookup_error_not_a_refusal(self):
        with self.assertRaises(LookupError):
            pk.ajk_ages_from_pages([[row("Wheat", "1,000", "2,000")]])


if __name__ == "__main__":
    unittest.main()
