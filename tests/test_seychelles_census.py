"""Seychelles' 2022 census by district, from the National Bureau of
Statistics' report, Tables 2.4, A2.1, A2.2, B3.1a and B4.1 (scripts/fetch_census/seychelles_census)."""

import unittest
from unittest import mock

from scripts.fetch_census import seychelles_census as sc

# The three tables as the report's text layer gives them (pp. 39, 116, 118).
TEXT = """Table 2.4: Sex ratio at national, regional and district levels, Census 2022 and 2010
Population 2022 Sex ratio
National / Region / District Both sexes Male Female 2022 2010
SEYCHELLES 102,612 56,226 46,386 121 107
Region and district
CENTRAL 30,145 15,386 14,759 104 101
Ile Perseverance 5,410 2,482 2,928 85 ..
English River 3,508 1,751 1,757 100 93
Mont Buxton 2,778 1,393 1,385 101 101
Saint Louis 3,267 1,723 1,544 112 98
Bel Air 2,619 1,348 1,271 106 97
Mont Fleuri 3,506 1,912 1,594 120 99
Plaisance 3,685 1,926 1,759 109 92
Roche Caiman 3,157 1,693 1,464 116 138
Les Mamelles 2,215 1,158 1,057 110 101
EAST and SOUTH 27,072 15,706 11,366 138 104
Cascade 6,659 4,751 1,908 249 105
Pointe Larue 3,267 1,747 1,520 115 101
Anse Aux Pins 3,898 2,005 1,893 106 95
Au Cap 5,168 2,781 2,387 117 118
Anse Royale 4,552 2,371 2,181 109 102
Takamaka 3,528 2,051 1,477 139 101
WEST 15,058 8,316 6,742 123 108
Baie Lazare 4,265 2,417 1,848 131 120
Anse Boileau 4,595 2,613 1,982 132 103
Grand Anse Mahé 3,425 1,760 1,665 106 96
Port Glaud 2,773 1,526 1,247 122 118
NORTH 17,843 9,345 8,498 110 99
Belombre 3,823 1,969 1,854 106 99
Beau Vallon 4,740 2,470 2,270 109 101
Glacis 3,803 1,988 1,815 110 104
Anse Etoile 5,477 2,918 2,559 114 97
PRASLIN 7,882 4,378 3,504 125 124
Grand Anse Praslin 3,610 1,987 1,623 122 112
Baie Sainte Anne 4,272 2,391 1,881 127 135
LA DIGUE and INNER 3,537 2,095 1,442 145 121
ISLANDS
OUTER ISLANDS 1,075 1,000 75 1,333 380
15
Table B3.1a: Population aged 3 years and over by main first language spoken at home by region/district, 2022
First Language
Other Do Not
Region/District Creole English French Gujarati Hindi Tamil (Specify) Know Refusal Missing
98,952 74,542 6,986 401 1,635 1,618 771 1,454 115 13 11,417
Central 28,982 22,533 1,945 84 109 149 318 434 17 7 3,386
English River 3,362 2,845 202 13 15 20 36 61 2 - 168
Mont Buxton 2,687 2,372 119 9 - 13 20 14 1 - 139
Saint Louis 3,140 2,331 219 6 16 18 98 65 7 6 374
Bel Air 2,530 1,870 261 11 28 8 59 37 - - 256
Mont Fleuri 3,398 2,340 284 9 29 23 26 92 3 - 592
Plaisance 3,555 2,918 234 11 - 7 26 42 3 - 314
Roche Caiman 3,036 1,923 264 13 21 60 43 95 - 1 616
Les Mamelles 2,131 1,774 127 4 - - 10 15 - - 201
Ile Perseverance 5,143 4,160 235 8 - - - 13 1 - 726
East-South 26,140 19,212 1,900 115 693 938 161 346 8 6 2,761
Cascade 6,481 3,188 504 19 557 577 27 63 3 - 1,543
Pointe Larue 3,132 2,740 188 3 - 1 6 17 3 - 174
Anse Aux Pins 3,748 3,207 150 8 12 13 37 45 - 5 271
Anse Royale 4,386 3,682 336 27 51 9 33 75 1 - 172
Takamaka 3,408 2,488 168 16 - 303 6 50 - 1 376
Au Cap 4,985 3,907 554 42 73 35 52 96 1 - 225
West 14,537 11,436 773 54 13 114 60 160 2 - 1,925
Baie Lazare 4,108 3,086 345 32 - 11 16 73 - - 545
Anse Boileau 4,435 3,441 205 8 11 11 17 30 2 - 710
Grand Anse Mahé 3,308 2,759 136 8 2 92 24 48 - - 239
Port Glaud 2,686 2,150 87 6 - - 3 9 - - 431
North 17,243 13,034 1,650 100 47 353 148 317 66 - 1,528
Belombre 3,689 2,783 390 7 - 11 38 81 1 - 378
Beau Vallon 4,581 3,126 530 34 12 20 52 81 57 - 669
Glacis 3,686 2,958 322 40 1 5 32 90 5 - 233
Anse Etoile 5,287 4,167 408 19 34 317 26 65 3 - 248
Praslin 7,566 5,956 475 30 13 18 58 76 5 - 935
Baie Ste Anne 4,091 3,250 167 18 13 9 44 50 5 - 535
Grand Anse Praslin 3,475 2,706 308 12 - 9 14 26 - - 400
La Digue & Inner Islands 3,499 2,371 190 18 53 46 26 121 17 - 657
Bird 1 - - - - - - - - - 1
Denis 86 - - - - - - - - - 86
Fregate 13 - - - - - - - - - 13
La Digue 3,013 2,310 174 16 43 43 25 102 17 - 283
North 88 38 14 1 - 3 1 17 - - 14
Silhouette 298 23 2 1 10 - - 2 - - 260
Outer Islands 985 - 53 - 707 - - - - - 225
Aldabra 3 - - - - - - - - - 3
Alphonse 111 - - - 13 - - - - - 98
Assumption 7 - - - 7 - - - - - -
Coetivy 22 - - - 22 - - - - - -
Darros 110 - - - 110 - - - - - -
Desroches 336 - 53 - 162 - - - - - 121
Farquhar 17 - - - 14 - - - - - 3
Marie-Louise 8 - - - 8 - - - - - -
Platte 353 - - - 353 - - - - - -
Poivre 9 - - - 9 - - - - - -
Providence 5 - - - 5 - - - - - -
Remire 4 - - - 4 - - - - - -
92
Table B4.1: Population in all households by religion and region/district, 2022
All households Religion
Christian Unable to Other
Region/District Total Catholic Anglican Islam Hindu (Other) classify (Specify) Missing
102,612 62,952 5,180 2,498 5,508 8,810 649 5,243 11,772
Central 30,145 18,769 1,701 925 1,083 2,646 142 1,448 3,431
English River 3,508 2,355 214 74 124 372 13 188 168
Mont Buxton 2,778 1,964 144 116 47 244 12 113 138
Saint Louis 3,267 1,873 282 145 205 194 15 176 377
Bel Air 2,619 1,528 236 68 136 209 29 156 257
Mont Fleuri 3,506 2,033 149 113 150 224 22 180 635
Plaisance 3,685 2,512 161 90 125 301 3 180 313
Roche Caiman 3,157 1,554 160 113 242 296 12 160 620
Les Mamelles 2,215 1,492 123 73 41 194 9 82 201
Ile Perseverance 5,410 3,458 232 133 13 612 27 213 722
East-South 27,072 16,695 908 583 2,229 2,375 183 1,066 3,033
Cascade 6,659 2,951 94 193 1,337 272 80 157 1,575
Pointe Larue 3,267 2,373 115 71 104 296 8 123 177
Anse Aux Pins 3,898 2,792 121 68 91 372 20 168 266
Anse Royale 4,552 3,067 237 107 146 536 35 253 171
Takamaka 3,528 2,306 49 57 330 265 13 133 375
Au Cap 5,168 3,206 292 87 221 634 27 232 469
West 15,058 9,923 396 368 303 1,229 91 827 1,921
Baie Lazare 4,265 2,838 68 155 75 305 41 239 544
Anse Boileau 4,595 2,961 121 52 77 440 26 211 707
Grand Anse Mahé 3,425 2,336 144 98 131 267 12 199 238
Port Glaud 2,773 1,788 63 63 20 217 12 178 432
North 17,843 11,386 1,021 467 797 1,381 141 1,086 1,564
Belombre 3,823 2,370 304 108 126 305 20 226 364
Beau Vallon 4,740 2,854 202 70 158 383 35 313 725
Glacis 3,803 2,673 166 126 71 268 53 213 233
Anse Etoile 5,477 3,489 349 163 442 425 33 334 242
Praslin 7,882 4,086 1,091 92 207 845 59 568 934
Baie Ste Anne 4,272 2,383 319 39 122 451 44 380 534
Grand Anse Praslin 3,610 1,703 772 53 85 394 15 188 400
La Digue & Inner Islands 3,624 2,050 62 63 182 329 33 244 661
Bird 1 - - - - - - - 1
Denis 86 - - - - - - - 86
Fregate 13 - - - - - - - 13
La Digue 3,133 1,989 62 58 159 318 31 232 284
North 88 38 - 4 10 9 1 11 15
Silhouette 303 23 - 1 13 2 1 1 262
Outer Islands 988 43 1 - 707 5 - 4 228
Aldabra 3 - - - - - - - 3
Alphonse 112 - - - 13 - - - 99
Assumption 7 - - - 7 - - - -
Coetivy 22 - - - 22 - - - -
Darros 110 - - - 110 - - - -
Desroches 338 43 1 - 162 5 - 4 123
Farquhar 17 - - - 14 - - - 3
Marie-Louise 8 - - - 8 - - - -
Platte 353 - - - 353 - - - -
Poivre 9 - - - 9 - - - -
Providence 5 - - - 5 - - - -
Remire 4 - - - 4 - - - -
94"""


# Tables A2.1 and A2.2 (pp. 89-90, printed rotated) as the text layer gives them: a line's name a word
# or two a line, then its 22 figures one a line, bottom up; four of their lines and the title.
AGES_BOTH = """Outer
Islands
988
2
1
-
-
29
228
162
175
145
109
76
39
16
6
-
-
-
-
-
-
-
La
Digue
3,133
36
174
195
195
156
164
259
290
315
272
256
234
199
143
82
52
42
37
25
5
2
La
Digue &
Inner
Islands
3,624
39
176
199
196
160
192
322
383
397
348
318
269
225
152
83
52
42
39
25
5
2
Cascade
6,659
66
234
292
291
288
469
764
865
891
748
529
414
288
190
132
79
56
37
17
5
4
(Both
Sexes)
102,612
1,213
5,185
6,655
6,521
5,981
6,517
8,746
9,606
9,474
8,777
7,476
6,713
6,050
4,883
3,330
2,150
1,409
1,010
587
254
75
Region/District
Total
Less
than
1
Year
01-04
05-09
10-14
15-19
20-24
25-29
30-34
35-39
40-44
45-49
50-54
55-59
60-64
65-69
70-74
75-79
80-84
85-89
90-94
95+
Table
A2.1:
Population
of
Seychelles
by
age
group,
region/district
(Both
sexes),
2022"""
AGES_MEN = """Outer
Islands
923
1
1
-
-
27
219
153
152
134
105
75
36
15
5
-
-
-
-
-
-
-
La
Digue
1,766
17
84
98
102
80
98
159
194
196
176
146
127
103
77
40
22
24
15
8
-
-
La
Digue &
Inner
Islands
2,172
19
85
100
102
83
117
210
276
266
242
197
158
124
84
40
22
24
15
8
-
-
Cascade
4,751
34
115
132
137
166
357
623
725
754
611
389
293
170
105
55
42
28
13
1
1
-
(Male)
56,226
621
2,643
3,420
3,208
3,088
3,786
5,272
6,009
6,023
5,221
4,198
3,519
2,977
2,417
1,635
1,026
607
329
155
60
12
Region/District
Total
Less
than
1
Year
01-04
05-09
10-14
15-19
20-24
25-29
30-34
35-39
40-44
45-49
50-54
55-59
60-64
65-69
70-74
75-79
80-84
85-89
90-94
95+
Table
A2.2:
Population
of
Seychelles
by
age
group,
region/district,
(Male),
2022"""
# Table 2.4's men and women for the same three districts.
TABLE24 = {"cascade": (6_659, 4_751), "ladigueandinnerislands": (3_537, 2_095),
           "outerislands": (1_075, 1_000)}

class SeychellesCensusTest(unittest.TestCase):
    def test_the_tables_add_up(self):
        table = sc.parse(TEXT)
        self.assertEqual(len(table), 27)
        self.assertEqual(table["cascade"]["men"], 4_751)
        self.assertEqual(table["baiesainteanne"]["religion"]["Catholic"], 2_383)

    def test_truncated_names_and_the_undrawn_district(self):
        admin1 = [{"id": "a", "name": "Anse Boile"}, {"id": "r", "name": "La Rivière"},
                  {"id": "d", "name": "La Digue a"}]
        table = {k: v for k, v in sc.parse(TEXT).items()
                 if k in ("anseboileau", "englishriver", "ladigueandinnerislands",
                          "ileperseverance")}
        recs = {r["shape_id"]: r for r in sc.build(table, admin1)}
        self.assertEqual(recs["r"]["population"]["value"], 3_508)
        self.assertEqual(recs["a"]["sex_ratio"]["value"], round(1000 * 2_613 / 1_982))
        self.assertEqual(recs["d"]["language"][0]["group"], "Seychellois Creole")
        self.assertIn("aged 3 and over", recs["d"]["language_note"])

    def test_a_district_on_no_polygon_is_refused_unless_it_is_known(self):
        table = {k: v for k, v in sc.parse(TEXT).items() if k in ("anseboileau", "cascade")}
        with self.assertRaises(SystemExit):
            sc.build(table, [{"id": "a", "name": "Anse Boile"}])


    def small(self):
        """The full tables cut to three districts, with the country patched to match."""
        table = {k: v for k, v in sc.parse(TEXT).items() if k in TABLE24}
        for k, (total, men) in TABLE24.items():
            self.assertEqual((table[k]["total"], table[k]["men"]), (total, men))
        return table

    def test_the_rotated_age_tables(self):
        rows = sc.age_rows(AGES_BOTH)
        self.assertEqual(rows["ladigue"][0][0], 3_133)
        self.assertEqual(rows["ladigueandinnerislands"][0][0], 3_624)
        self.assertEqual(len(rows["cascade"][0]), 22)
        table = self.small()
        with mock.patch.object(sc, "DISTRICTS", ("Cascade", "La Digue and Inner Islands",
                                                 "Outer Islands")), \
                mock.patch.object(sc, "NATIONAL", 6_659 + 3_624 + 988), \
                mock.patch.object(sc, "NATIONAL_MEN", 4_751 + 2_172 + 923):
            age = sc.ages(AGES_BOTH, AGES_MEN, table)
        # Table A2.1 places 87 islanders (77 men) in La Digue and Inner Islands
        # that Table 2.4 counts in the Outer Islands.
        self.assertEqual(age["ladigueandinnerislands"]["moved"], 87)
        self.assertEqual(age["outerislands"]["moved"], -87)
        self.assertEqual(age["cascade"]["moved"], 0)
        self.assertEqual(sc.median(age["cascade"]["groups"]), 35.3)
        self.assertEqual(age["ladigue"]["men"], 1_766)

    def test_a_district_off_its_count_is_refused(self):
        table = self.small()
        table["cascade"] = {**table["cascade"], "total": 6_600}
        with mock.patch.object(sc, "DISTRICTS", ("Cascade", "La Digue and Inner Islands",
                                                 "Outer Islands")), \
                mock.patch.object(sc, "NATIONAL", 6_659 + 3_624 + 988), \
                mock.patch.object(sc, "NATIONAL_MEN", 4_751 + 2_172 + 923), \
                self.assertRaises(SystemExit):
            sc.ages(AGES_BOTH, AGES_MEN, table)

    def test_the_second_level_polygons(self):
        table = self.small()
        with mock.patch.object(sc, "DISTRICTS", ("Cascade", "La Digue and Inner Islands",
                                                 "Outer Islands")), \
                mock.patch.object(sc, "NATIONAL", 6_659 + 3_624 + 988), \
                mock.patch.object(sc, "NATIONAL_MEN", 4_751 + 2_172 + 923), \
                mock.patch.object(sc, "GROUPS2", {"eastmahe": ("Cascade",)}):
            age = sc.ages(AGES_BOTH, AGES_MEN, table)
            recs = {r["shape_id"]: r for r in sc.build2(
                table, age, sc.island_composition(TEXT),
                [{"id": "e", "name": "East Mahe"}, {"id": "l", "name": "La Digue"},
                 {"id": "o", "name": "Other Islands"}])}
        self.assertEqual(recs["e"]["population"]["value"], 6_659)
        self.assertEqual(recs["e"]["median_age"]["value"], 35.3)
        self.assertEqual(recs["l"]["population"]["value"], 3_133)
        self.assertEqual(recs["l"]["sex_ratio"]["value"], round(1000 * 1_766 / 1_367))
        self.assertEqual(recs["l"]["religion"][0]["group"], "Catholic")
        self.assertEqual(recs["o"]["population"]["value"], 3_624 + 988 - 3_133)
        # The Outer Islands' fourth columns (Gujarati, Hindu) agree island by
        # island: their language and religion are withheld, with the reason.
        self.assertIn("coding error", recs["o"]["language"]["note"])
        self.assertEqual(recs["o"]["religion"]["status"], "not_available")

    def test_the_outer_islands_are_shown_once_the_columns_differ(self):
        table = self.small()
        self.assertIsNotNone(sc.garbled(table, "neither is"))
        table["outerislands"] = {**table["outerislands"],
                                 "religion": {**table["outerislands"]["religion"], "Hindu": 5}}
        self.assertIsNone(sc.garbled(table, "neither is"))


if __name__ == "__main__":
    unittest.main()
