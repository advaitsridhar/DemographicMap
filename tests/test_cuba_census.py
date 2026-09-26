"""Tests for the Cuba reader: rows read back from ONEI's printed tables, no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import cuba_census as cc  # noqa: E402

# Rows as pypdf gives them from Estudios y Datos 2024, Table 5 (page 321 as
# printed): Cuba and Pinar del Río's totals, then two municipios' blocks.
TABLE_5 = """Unidad
EDADES Total Hombres Mujeres Total Hombres Mujeres Total Hombres Mujeres
CUBA 9 748 007 4 808 909 4 939 098 7 322 072 3 515 416 3 806 656 2 425 935 1 293 493 1 132 442
PINAR DEL RÍO 515 208 258 717 256 491 332 245 161 833 170 412 182 963 96 884 86 079
SANDINO
Total 31 612 16 456 15 156 19 340 9 774 9 566 12 272 6 682 5 590
0-4 1 317 688 629 919 473 446 398 215 183
5-9 1 488 761 727 1 102 562 540 386 199 187
10-14 1 720 910 810 1 152 615 537 568 295 273
15-19 1 629 856 773 965 493 472 664 363 301
20-24 1 873 1 022 851 1 122 613 509 751 409 342
25-29 1 789 928 861 1 052 557 495 737 371 366
30-34 2 174 1 150 1 024 1 286 656 630 888 494 394
35-39 1 883 948 935 1 151 542 609 732 406 326
40-44 1 588 851 737 947 502 445 641 349 292
45-49 1 966 1 010 956 1 158 593 565 808 417 391
50-54 2 791 1 418 1 373 1 657 799 858 1 134 619 515
55-59 3 026 1 575 1 451 1 815 903 912 1 211 672 539
60-64 2 766 1 421 1 345 1 725 875 850 1 041 546 495
65-69 1 809 963 846 1 132 553 579 677 410 267
70-74 1 384 715 669 874 441 433 510 274 236
75-79 1 119 566 553 649 316 333 470 250 220
80-84 740 375 365 403 196 207 337 179 158
85y+ 550 299 251 231 85 146 319 214 105
Estudios y Datos de la Población Cubana
Ambas zonas Urbana Rural
5 . Población de Cuba por municipios (incluye total provincial) y grupos de edades, según sexo
y zona de residencia, al 31/12/2024
321
"""

# The 2012 colour table's Pinar del Río rows, shares and all.
COLOUR = """1. Población por color de la piel, según provincias y municipios de residencia
Provincias / Municipios Total Blanca Negra Mulata Total Blanca Negra Mulata
CUBA 624 319 522 227 48 685 53 407 100,0 83,6 7,8 8,6
PINAR DEL RÍO 624 319 522 227 48 685 53 407 100,0 83,6 7,8 8,6
Sandino 37 293 32 343 1 988 2 962 100,0 86,7 5,3 7,9
Mantua 24 780 20 340 2 453 1 987 100,0 82,1 9,9 8,0
ISLA DE LA JUVENTUD 84 751 66 707 16 649 1 395 100,0 78,7 19,6 1,6
El color de la piel según el Censo de Población y Viviendas de 2012
Estructura en %Población
66
"""


class RegroupTest(unittest.TestCase):
    def test_spaced_thousands_read_by_their_sums(self):
        tokens = "1 317 688 629 919 473 446 398 215 183".split()
        self.assertEqual(cc.regroup(tokens, 9, cc.zones_error, "t"),
                         [1317, 688, 629, 919, 473, 446, 398, 215, 183])

    def test_unspaced_numbers_and_dashes(self):
        tokens = "4516 2342 2174 4516 2342 2174 - - -".split()
        self.assertEqual(cc.regroup(tokens, 9, cc.zones_error, "t"),
                         [4516, 2342, 2174, 4516, 2342, 2174, 0, 0, 0])

    def test_a_one_person_rounding_is_read_and_logged(self):
        # Rodas, as Estudios y Datos 2024 prints it: its urban men and women
        # make 18 926 against an urban total of 18 925.
        tokens = "28 713 14 518 14 196 18 925 9 285 9 641 9 788 5 233 4 555".split()
        self.assertEqual(cc.regroup(tokens, 9, cc.zones_error, "Rodas"),
                         [28713, 14518, 14196, 18925, 9285, 9641, 9788, 5233, 4555])
        self.assertIn("Rodas (by 2)", cc.DISCREPANCIES)

    def test_a_row_no_reading_satisfies_stops_the_run(self):
        with self.assertRaises(SystemExit):
            cc.regroup("1 2 3 4".split(), 4, cc.colours_error, "t")

    def test_split_row_keeps_a_hyphenated_name(self):
        self.assertEqual(cc.split_row("Songo - La Maya 86 354 43 395"),
                         ("Songo - La Maya", ["86", "354", "43", "395"]))


class TableTest(unittest.TestCase):
    def test_age_table_reads_a_block_and_checks_it_against_table_1(self):
        municipios = {"Pinar del Río": {
            "Sandino": [31612, 16456, 15156, 19340, 9774, 9566, 12272, 6682, 5590]}}
        ages = cc.age_table([TABLE_5], municipios)
        groups = ages[("Pinar del Río", "Sandino")]
        self.assertEqual(len(groups), 18)
        self.assertEqual(groups[0], (0, 4, 688, 629))
        self.assertEqual(groups[-1], (85, None, 299, 251))

    def test_age_groups_that_miss_table_1_stop_the_run(self):
        municipios = {"Pinar del Río": {
            "Sandino": [31614, 16458, 15156, 19342, 9776, 9566, 12272, 6682, 5590]}}
        with self.assertRaises(SystemExit):
            cc.age_table([TABLE_5], municipios)

    def test_age_groups_a_person_off_table_1_are_read_and_logged(self):
        # Corralillo's age groups make one woman fewer than Table 1 prints.
        municipios = {"Pinar del Río": {
            "Sandino": [31613, 16456, 15157, 19341, 9774, 9567, 12272, 6682, 5590]}}
        cc.age_table([TABLE_5], municipios)
        self.assertIn("Sandino's age groups against Table 1 (by 1)", cc.DISCREPANCIES)

    def test_table_5_headings_spelled_as_the_map_does(self):
        text = TABLE_5.replace("SANDINO", "ANTILLA")
        municipios = {"Pinar del Río": {
            "Antillas": [31612, 16456, 15156, 19340, 9774, 9566, 12272, 6682, 5590]}}
        self.assertIn(("Pinar del Río", "Antillas"), cc.age_table([text], municipios))

    def test_colour_rows_and_the_isle_of_youth(self):
        municipios, provinces, national, rows = cc.by_province(
            [COLOUR], 4, cc.colours_error, trailing_shares=4)
        self.assertEqual(municipios["Pinar del Río"]["Sandino"], [37293, 32343, 1988, 2962])
        # A province with no municipio beneath it is its own one unit.
        self.assertEqual(municipios["Isla de la Juventud"],
                         {"Isla de la Juventud": [84751, 66707, 16649, 1395]})
        self.assertEqual(len(rows), 5)

    def test_median_and_ratio(self):
        groups = [(0, 4, 50), (5, 9, 50), (10, None, 0)]
        out = cc.figures([100, 60, 40], groups)
        self.assertEqual(out["sex_ratio"]["value"], 1500)
        self.assertEqual(out["median_age"]["value"], 5.0)
        self.assertEqual(out["population"]["value"], 100)

    def test_colour_fields_are_shares_of_the_three_colours(self):
        out = cc.colour_fields([100, 60, 10, 30])
        self.assertEqual({g["group"]: g["pct"] for g in out["ethnicity"]},
                         {"White": 60.0, "Black": 10.0, "Mulatto or Mestizo": 30.0})


if __name__ == "__main__":
    unittest.main()
