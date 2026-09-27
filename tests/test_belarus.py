import unittest

from scripts.fetch_census import belarus as b


def cells(spec):
    """'text@x0-x1 ...' -> [(x0, x1, text)]."""
    out = []
    for item in spec.split():
        text, box = item.rsplit("@", 1)
        x0, x1 = box.split("-")
        out.append((float(x0), float(x1), text))
    return out


class SplitRow(unittest.TestCase):
    def test_digit_groups_close_together_are_one_figure(self):
        row = cells("Брестская@62-121 область@124-170 1@202-208 485@211-229 095@233-251 "
                    "1@277-283 401@287-305 177@308-326 1@353-359 348@362-380 115@384-402 "
                    "Брэсцкая@428-473 вобласць@473-518")
        label, values, after = b.split_row(row)
        self.assertEqual(label, "Брестская область")
        self.assertEqual(values, [1485095.0, 1401177.0, 1348115.0])
        self.assertEqual(after, "Брэсцкая вобласць")

    def test_a_short_figure_and_a_dash(self):
        row = cells("мужчины@76-123 78@216-229 733@232-250 –@292-304 79@368-380 591@383-402")
        label, values, _ = b.split_row(row)
        self.assertEqual(label, "мужчины")
        self.assertEqual(values, [78733.0, None, 79591.0])


class Mend(unittest.TestCase):
    def test_a_row_split_by_a_footnote_is_rejoined(self):
        rows = [cells("мужчины@71-118 718@211-229 028@232-250 667@286-304 929@308-326 "
                      "641@362-380 133@383-401 мужчыны@440-487"),
                cells("женщины@71-120 жанчыны@440-487"),
                cells("827@211-229 055@232-250 772@286-304 789@308-326 747@362-380 "
                      "379@383-401"),
                cells("1)@300-306 1)@390-396")]
        got = b.mend(rows)
        self.assertEqual(len(got), 2)
        label, values, after = b.split_row(got[1])
        self.assertEqual((label, after), ("женщины", "жанчыны"))
        self.assertEqual(values, [827055.0, 772789.0, 747379.0])

    def test_a_mark_on_a_figure_is_taken_off(self):
        row = cells("Витебская@57-109 область@112-152 454@211-229 078@232-250 333@286-304 "
                    "7881)@308-330 259@362-380 034@383-401")
        _, values, _ = b.split_row(b.mend([row])[0])
        self.assertEqual(values, [454078.0, 333788.0, 259034.0])

    def test_the_year_header_stays_apart(self):
        rows = [cells("Працяг@57-90"), cells("1999@220-240 2009@290-310 2019@370-390")]
        self.assertEqual(len(b.mend(rows)), 2)


class Names(unittest.TestCase):
    def test_every_city_names_a_raion_we_know(self):
        for city, raion in b.CITY.items():
            self.assertIn(raion, b.RAION, city)

    def test_non_seat_cities_are_placed_by_their_centre_alone(self):
        for city in b.NOT_SEAT:
            self.assertNotIn(city, b.CITY)


if __name__ == "__main__":
    unittest.main()
