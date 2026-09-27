import unittest

from scripts.fetch_census import armenia_2011 as a


def column(text, x, bottom=300.0, step=9.0):
    """A heading set sideways: its first letter lowest, one per line up."""
    return [{"text": ch, "x0": x, "x1": x + 9, "top": bottom - i * step, "upright": False}
            for i, ch in enumerate(text)]


def turned(text, top, right=500.0, step=6.0):
    """A heading turned right over: its first letter rightmost."""
    return [{"text": ch, "x0": right - i * step, "x1": right - i * step + 5, "top": top,
             "upright": False} for i, ch in enumerate(text)]


class Headings(unittest.TestCase):
    def test_a_column_read_from_the_bottom_up(self):
        chars = column("Հայ", 243) + column("առաքելական", 255)
        text = a.squeeze("".join(a.lines_of(chars)))
        self.assertEqual(text, "հայառաքելական")

    def test_a_heading_turned_over_is_matched_reversed(self):
        chars = turned("Եզդիերեն", 200)
        text = a.squeeze("".join(a.lines_of(chars)))
        got = a.classify(["ընդամենը", text], a.LANGUAGE, "language")
        self.assertEqual(got, [True, "Ezidian"])

    def test_religion_headings(self):
        headings = ["բնակչություն", "կրոնականդավանանքով", "հայառաքելական", "շարֆադինական",
                    "ուղղափառ", "եհովայիվկաներ", "այլ", "չունենկրոնականդավանանք",
                    "հրաժարվելենպատասխանել", "կրոնականդավանանքընշվածչէ"]
        got = a.classify(headings, a.RELIGION, "religion")
        self.assertEqual(got, [True, None, "Armenian Apostolic", "Yazidi", "Orthodox",
                               "Jehovah's Witnesses", "Other religion", "No religion",
                               "Not stated", "Not stated"])

    def test_an_unknown_heading_stops_the_run(self):
        with self.assertRaises(SystemExit):
            a.classify(["ընդամենը", "զզզզ"], a.LANGUAGE, "language")


class Rows(unittest.TestCase):
    def word(self, text, x0, top):
        return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top}

    def test_a_label_set_over_its_figures_is_joined_to_them(self):
        words = [self.word("Ընդամենը", 50, 158), self.word("1,060,138", 130, 161),
                 self.word("1,027,295", 170, 161), self.word("Հայ", 50, 177),
                 self.word("1,048,940", 130, 177)]
        rows = a.page_rows(words)
        self.assertEqual(len(rows), 2)
        label, numbers = a.split(rows[0][1])
        self.assertEqual((label, len(numbers)), ("Ընդամենը", 2))


class Figures(unittest.TestCase):
    def test_a_thousands_group_set_a_space_apart_is_one_figure(self):
        words = [{"text": "Հայ", "x0": 50, "x1": 65, "top": 1},
                 {"text": "259", "x0": 130, "x1": 145, "top": 1},
                 {"text": "845", "x0": 147, "x1": 160, "top": 1},
                 {"text": "12", "x0": 180, "x1": 190, "top": 1}]
        label, numbers = a.split(words)
        self.assertEqual(label, "Հայ")
        self.assertEqual([n["text"] for n in numbers], ["259,845", "12"])


class Composition(unittest.TestCase):
    def test_columns_must_make_the_total(self):
        labels = [True, None, "Armenian Apostolic", "No religion", "Not stated", "Not stated"]
        got = a.composition([100, 90, 90, 6, 3, 1], labels, "religion", "X")
        self.assertEqual(got, {"Armenian Apostolic": 90, "No religion": 6, "Not stated": 4})
        with self.assertRaises(SystemExit):
            a.composition([100, 90, 89, 6, 3, 1], labels, "religion", "X")


if __name__ == "__main__":
    unittest.main()
