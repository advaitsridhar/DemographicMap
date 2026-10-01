import unittest

from scripts.fetch_census import russia_religion as r


class Respondents(unittest.TestCase):
    def test_whole_counts_of_800(self):
        shares = [100 * k / 800 for k in (404, 178, 84, 3, 65, 2, 12, 0, 0, 2, 3, 0, 6, 1, 1,
                                          1, 1, 38)]
        shares += [100 * k / 800 for k in (365, 435, 221, 203, 215, 161)]
        self.assertEqual(r.respondents(shares), 800)

    def test_whole_counts_of_500(self):
        shares = [27.0, 44.0, 17.6, 0.2, 1.8, 0.2, 0.2, 0.2, 0.6, 8.0]
        self.assertEqual(r.respondents(shares), 500)

    def test_a_weighted_share_has_no_n(self):
        self.assertIsNone(r.respondents([42.798403480631, 27.4531161645328]))


class Blocks(unittest.TestCase):
    def test_headings_and_answers(self):
        rows = [["Доли групп", 100.0, 1.1],
                ["Выберите, пожалуйста, из предлагаемого списка одно утверждение", "", ""],
                ["не верю в Бога", 13.0, 10.5],
                ["другое", 0.6, ""],
                ["Пол", "", ""],
                ["мужской", 45.0, 44.5]]
        got = r.blocks(rows)
        self.assertEqual(list(got), [rows[1][0], "Пол"])
        self.assertEqual([a for a, _ in got[rows[1][0]]], ["не верю в Бога", "другое"])


class Configuration(unittest.TestCase):
    def test_seventy_nine_subjects_and_four_left_out(self):
        self.assertEqual(len(r.SUBJECTS), 79)
        self.assertEqual(len(set(r.SUBJECTS.values())), 79)
        self.assertFalse(set(r.SUBJECTS.values()) & set(r.NOT_SURVEYED))

    def test_every_answer_has_its_own_label(self):
        self.assertEqual(len(set(r.ANSWERS.values())), len(r.ANSWERS))


class CountryRow(unittest.TestCase):
    def test_weighted_shares_become_counts_of_the_whole_sample(self):
        row = r.country_row({"Russian Orthodox Church": 41.12, "Atheist": 13.0,
                             "Believe in God, no specific religion": 45.88, "Judaism": 0.0},
                            56900)
        self.assertEqual([g["group"] for g in row["groups"]],
                         ["Believe in God, no specific religion", "Russian Orthodox Church",
                          "Atheist"])
        self.assertEqual(row["groups"][1], {"group": "Russian Orthodox Church", "pct": 41.1,
                                            "count": 23397})
        self.assertAlmostEqual(sum(g["count"] for g in row["groups"]), 56900, delta=1)

    def test_shares_that_do_not_make_a_whole_stop_the_run(self):
        with self.assertRaises(SystemExit):
            r.country_row({"Atheist": 13.0, "Judaism": 0.1}, 56900)


if __name__ == "__main__":
    unittest.main()
