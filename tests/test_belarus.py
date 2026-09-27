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


class Names(unittest.TestCase):
    def test_every_city_names_a_raion_we_know(self):
        for city, raion in b.CITY.items():
            self.assertIn(raion, b.RAION, city)

    def test_non_seat_cities_are_declared_cities(self):
        for city in b.NOT_SEAT:
            self.assertIn(city, b.CITY)


if __name__ == "__main__":
    unittest.main()
