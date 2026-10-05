"""Bangladesh 2022: Table P03's age groups and Table P11's sex ratios.

The fixtures are the National Report's rows as its text comes out: an area's
name alone on a line, a Total row, five-year rows, then the rural and urban
blocks. No PDF and no network.
"""

import unittest

from scripts.fetch_census import bangladesh as bd

LABELS = [f"{a}-{a + 4}" for a in range(0, 100, 5)] + ["100 & above"]


def block(name: str, scale: int) -> list[str]:
    """An area's all-localities block, then a rural one that must be ignored."""
    males = [scale * (21 - i) for i in range(21)]
    females = [scale * (21 - i) + scale for i in range(21)]
    rows = [name]
    tm, tf = sum(males), sum(females)
    rows.append(f"Total {tm + tf} 100.00 {tm} 50.00 {tf} 50.00 {100 * tm / tf:.2f}")
    for label, m, f in zip(LABELS, males, females):
        rows.append(f"{label} {m + f} 100.00 {m} 50.00 {f} 50.00 {100 * m / f:.2f}")
    rows += ["Rural", f"Total 7 100.00 3 42.86 4 57.14 75.00",
             "0-4 7 100.00 3 42.86 4 57.14 75.00"]
    return rows


def p03(divisions: dict[str, int]) -> list[str]:
    lines = ["Table P03 Population by Age, Sex, Division and Location, 2022 ...... 153",
             "Table P04 something ...... 160",
             "Table P03 Population by Age, Sex, Division and Location, 2022",
             "Age, Division & Total Male Female", "1 2 3 4 5 6 7 8"]
    total = sum(divisions.values())
    lines += block("National", total)
    for name, scale in divisions.items():
        lines += block(f"{name} Division", scale)
    lines.append("Table P04 Population by something else")
    return lines


EIGHT = {"Barishal": 1, "Chattogram": 2, "Dhaka": 3, "Khulna": 1, "Mymensingh": 1,
         "Rajshahi": 2, "Rangpur": 1, "Sylhet": 1}


class TableP03(unittest.TestCase):
    def test_the_all_localities_blocks_are_read(self):
        ages = bd.read_ages(p03(EIGHT))
        self.assertEqual(set(ages), {"National", *EIGHT})
        self.assertEqual(len(ages["Dhaka"]["groups"]), 21)
        self.assertEqual(ages["Dhaka"]["groups"][-1][:2], (100, None))
        bd.check_ages(ages)

    def test_a_division_that_does_not_add_up_to_the_nation_is_refused(self):
        # One more person in Dhaka's 5-9 row and its Total row, and one fewer
        # in Khulna's: every block adds up, the nation does not.
        lines = p03(EIGHT)

        def bump(at: int) -> None:
            """One more male in a row, its persons and its printed ratio."""
            tokens = lines[at].split()
            at100 = tokens.index("100.00")
            persons, males, females = at100 - 1, at100 + 1, at100 + 3
            tokens[persons] = str(int(tokens[persons]) + 1)
            tokens[males] = str(int(tokens[males]) + 1)
            tokens[-1] = f"{100 * int(tokens[males]) / int(tokens[females]):.2f}"
            lines[at] = " ".join(tokens)

        dhaka = lines.index("Dhaka Division")
        bump(dhaka + 3)                                 # Dhaka's 5-9 row
        bump(dhaka + 1)                                 # and its Total row
        ages = bd.read_ages(lines)
        with self.assertRaises(SystemExit) as caught:
            bd.check_ages(ages)
        self.assertIn("the divisions add up to", str(caught.exception))

    def test_a_printed_ratio_the_counts_do_not_give_is_refused(self):
        lines = p03(EIGHT)
        at = lines.index("Sylhet Division") + 1
        lines[at] = lines[at].rsplit(" ", 1)[0] + " 99.99"
        with self.assertRaises(SystemExit):
            bd.check_ages(bd.read_ages(lines))

    def test_division_fields(self):
        ages = bd.read_ages(p03(EIGHT))
        fields = bd.division_age_fields(ages["Khulna"])
        self.assertEqual(fields["sex_ratio"]["unit"], "males_per_100_females")
        self.assertGreater(fields["median_age"]["value"], 0)
        self.assertIn("five-year age group", fields["median_age_note"])


class TableP11(unittest.TestCase):
    LINES = [
        "Table P11 Average Annual Population Growth Rate, Sex Ratio ...... 259",
        "Table P12 next ...... 261",
        "Table P11 Average Annual Population Growth Rate, Sex Ratio, Dependency",
        "1 2 3 4 5 6 7 8 9 10 11 12 13",
        "National 1.22 98.07 52.63 332.38 0.21 95.30 56.08 350.49 3.90 104.35 45.63 294.52",
        "Barishal Division",
        "Total 0.79 95.27 57.71 349.03 -0.19 94.05 59.18 356.50 4.61 98.97 53.51 327.35",
        "Barguna 1.10 95.93 53.44 312.12 -0.11 95.73 54.23 317.13 7.17 96.61 50.83 295.91",
        "Cox's Bazar 1.86 103.32 63.79 460.91 -1.05 101.06 66.39 473.52 8.03 106.31 60.56 444.62",
        "Chapainawabganj 0.5 101.00 1.0 2.0 0.1 1.0 1.0 1.0 1.0 1.0 1.0 1.0",
        "Table P12 Something",
    ]

    def test_district_ratios_are_the_second_figure(self):
        got = bd.read_p11(self.LINES)
        self.assertEqual(got, {"Barguna": 95.93, "Cox's Bazar": 103.32,
                               "Chapainawabganj": 101.0})

    def test_the_workbook_must_give_the_printed_ratio(self):
        rows = [{"name": "Barguna", "males": 9593, "females": 10000, "hijra": 3,
                 "population": 19596},
                {"name": "Cox's Bazar", "males": 10332, "females": 10000, "hijra": 0,
                 "population": 20332},
                {"name": "Chapainababganj", "males": 101, "females": 100, "hijra": 0,
                 "population": 201}]
        bd.check_sexes(rows, bd.read_p11(self.LINES))
        rows[0]["males"] = 9600
        rows[0]["population"] = 19603
        with self.assertRaises(SystemExit):
            bd.check_sexes(rows, bd.read_p11(self.LINES))

    def test_the_hijra_are_in_neither_sex(self):
        fields = bd.zila_sex_ratio({"males": 9593, "females": 10000, "hijra": 3})
        self.assertEqual(fields["sex_ratio"]["value"], 95.9)
        self.assertIn("3 hijra", fields["sex_ratio_note"])


if __name__ == "__main__":
    unittest.main()
