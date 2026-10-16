"""Abkhazia's de facto statistics committee's yearbook, read from the text the
runner's PDF reader gave for it (pages 6, 16, 17, 19, 20, 23, 24 and 28 of
«Абхазский статистический ежегодник – 2025»). No network."""

import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import abkhazia_census as a  # noqa: E402

# The contents page (6) names every table first, so it is in the fixture: the
# tables are read where they are printed, not where they are listed.
YEARBOOK = """СОДЕРЖАНИЕ Стр.
Административно-территориальное деление Республики Абхазия 5
СВОДНЫЕ ПОКАЗАТЕЛИ 12
Основные показатели экономического и социального развития 12
Основные социально-экономические показатели развития по административно-
территориальным образованиям Республики Абхазия за 2025 год 15
1. НАСЕЛЕНИЕ 16
1.1 Численность наличного населения 16
1.2 Распределение наличного населения по возрастным группам
(по данным Переписи населения 2011 года) 17
1.3 Распределение наличного населения по возрастным группам на 1 января 2023 года 17
1.4 Распределение наличного населения по возрастным группам на 1 января 2024 года 18
1.5 Распределение наличного населения по возрастным группам на 1 января 2025 года 18
1.6 Распределение наличного населения по возрастным группам на 1 января 2026 года 19
1.7 Численность наличного населения по административно-территориальным
образованиям (по данным Переписи населения 2011 года) 19
1.8 Численность наличного населения по административно-территориальным
образованиям на 1 января 2023 года 20
1.9 Численность наличного населения по административно-территориальным
образованиям на 1 января 2024 года 21
1.10 Численность наличного населения по административно-территориальным
образованиям на 1 января 2025 года 22
1.11 Численность наличного населения по административно-территориальным
образованиям на 1 января 2026 года 23
1.12 Национальный состав наличного населения (по данным Переписи населения 2011 года) 24
1.13 Национальный состав наличного населения на 1 января 2023 года 25
1.14 Национальный состав наличного населения на 1 января 2024 года 26
1.15 Национальный состав наличного населения на 1 января 2025 года 27
1.16 Национальный состав наличного населения на 1 января 2026 года 28
1.17 Рождаемость, смертность, естественный прирост (убыль) населения, брачность и
разводимость 29
1.18 Смертность населения по основным классам и причинам 30
1.19 Младенческая смертность 30
1.20 Младенческая смертность по основным классам и причинам 30
1.21 Миграционное движение 31
1.22 Сведения о миграционной ситуации 32
1. 23 Основные показатели репатриации 32
2. РЫНОК ТРУДА 33
2.1 Численность занятого населения в отраслях экономики 33
2.2 Среднемесячная заработная плата занятых в отраслях экономики 34
Среднегодовая численность занятых по административно-территориальным
2.3
образованиям 34
Среднемесячная денежная заработная плата по административно - территориальным
2.4
образованиям 35
2.5 Структура занятых в отраслях экономики 35
6
[324 words in 48 rows]
1.НАСЕЛЕНИЕ
В разделе приведены данные о численности, национальном и половозрастном составе
населения, естественном движении, а также о миграционных процессах.
Первоисточником получения сведений о населении является Перепись населения. Текущая
оценка численности населения на 1 января рассчитывается на основании итогов Переписи
населения, к которым ежегодно прибавляются числа родившихся и прибывших на данную
территорию и из которых вычитаются числа умерших и выбывших с данной территории.
К наличному населению относятся лица, находившиеся на момент Переписи населения на
данной территории, включая временно проживающих.
К постоянному населению относятся лица, постоянно проживающие на данной
территории, включая временно отсутствовавших на момент Переписи населения.
Сведения о рождении, смерти, браках и разводах получают на основании ежегодной
статистической разработки данных, содержащихся в актовых записях соответственно о рождении
и смерти, заключении и расторжении брака, составляемых органами записи актов гражданского
состояния. В число родившихся включены только родившиеся живыми.
Общие коэффициенты рождаемости и смертности – отношение соответственно числа
родившихся (живыми) и числа умерших в течение календарного года к среднегодовой
численности наличного населения. Исчисляется в промилле.
Коэффициент естественного прироста – разность общих коэффициентов рождаемости и
смертности. Исчисляется в промилле.
Данные о миграции населения получены в результате разработки документов
статистического учета прибытий и убытий, которые заполняются органами внутренних дел при
прописке и выписке населения по месту жительства.
1.1 Численность наличного населения
(на начало года)
Все В общей численности
в том числе
Годы население, населения в %
(чел.) городское сельское городское сельское
2011 240 705 121 255 119 450 50,4 49,6
2012 241 414 121 633 119 781 50,4 49,6
2013 242 028 121 884 120 144 50,4 49,6
2014 242 756 122 309 120 447 50,4 49,6
2015 243 206 122 434 120 772 50,3 49,7
2016 243 564 122 547 121 017 50,3 49,7
2017 243 936 122 722 121 214 50,3 49,7
2018 244 832 123 301 121 531 50,4 49,6
2019 245 246 123 485 121 761 50,4 49,6
2020 245 424 123 462 121 962 50,3 49,7
2021 244 926 123 015 121 911 50,2 49,8
2022 244236 122 523 121 713 50,2 49,8
2023 243 958 122 267 121 691 50,1 49,8
2024 243 711 122 041 121 670 50,1 49,9
2025 243 897 122 125 121 772 50,1 49,9
2026 243 977 122 161 121 816 50,1 49,9
16
[369 words in 46 rows]
1.2 Распределение наличного населения по возрастным группам
по данным Переписи населения 2011 года
На 1000 мужчин
Все население, В процентах
данного возраста
(чел.) к итогу
приходится женщин
Все население 240 705 100 1 151
в том числе в возрасте, лет:
0 – 4 12 592 5,2 935
5 – 9 11 648 4,8 948
10 – 14 14 122 5,9 957
15 – 19 15 199 6,3 973
20 – 24 19 828 8,2 1 024
25 – 29 19 211 8,0 1 014
30 – 34 18 251 7,5 1 018
35 – 39 15 877 6,6 1 052
40 – 44 15 831 6,6 1 079
45 – 49 17 258 7,2 1 148
50 – 54 17 726 7,4 1 223
55 – 59 15 409 6,4 1 332
60 – 64 12 414 5,2 1 402
65 – 69 8 210 3,4 1 489
70 лет и старше 27 129 11,3 1 807
из общей численности населения в возрасте:
моложе трудоспособного 41 602 17,28 947
трудоспособном 142 549 59,23 969
старше трудоспособного 56 554 23,49 2 119
1.3 Распределение наличного населения по возрастным группам
на 1 января 2023 года
На 1000 мужчин
Все население, В процентах
данного возраста
(чел.) к итогу
приходится женщин
Все население 243 958 100 1 122
в том числе в возрасте, лет:
0 – 4 12 686 5,2 939
5 – 9 11 710 4,8 949
10 – 14 14 394 5,9 979
15 – 19 15 369 6,3 984
20 – 24 20 005 8,2 1 040
25 – 29 19 517 8,0 1 034
30 – 34 18 297 7,5 1 025
35 – 39 16 101 6,6 1 063
40 – 44 16 101 6,6 1 095
45 – 49 17 565 7,2 1 177
50 – 54 18 053 7,4 1 246
55 – 59 15 613 6,4 1 343
60 – 64 12 686 5,2 1 434
65 – 69 8 294 3,4 1 501
70 лет и старше 27 567 11,3 1 847
из общей численности населения в возрасте:
моложе трудоспособного 42 156 17,28 969
трудоспособном 144 496 59,23 1 011
старше трудоспособного 57 306 23,49 2 120
17
[363 words in 57 rows]
1.6 Распределение наличного населения по возрастным группам
на 1 января 2026 года
На 1000 мужчин
Все население, В процентах
данного возраста
(чел.) к итогу
приходится женщин
Все население 243 977 100 1 117
в том числе в возрасте, лет:
0 – 4 12 687 5,2 939
5 – 9 11 711 4,8 949
10 – 14 14 395 5,9 979
15 – 19 15 371 6,3 983
20 – 24 20 006 8,2 1 040
25 – 29 19 518 8,0 1 034
30 – 34 18 298 7,5 1 025
35 – 39 16 102 6,6 1 063
40 – 44 16 102 6,6 1 095
45 – 49 17 566 7,2 1 177
50 – 54 18 054 7,4 1 246
55 – 59 15 615 6,4 1 343
60 – 64 12 687 5,2 1 434
65 – 69 8 296 3,4 1 502
70 лет и старше 27 569 11,3 1 847
из общей численности населения в возрасте:
моложе трудоспособного 42 159 17,28 970
трудоспособном 144 508 59,23 1 012
старше трудоспособного 57 310 23,49 2 120
1.7 Численность наличного населения по административно-
территориальным образованиям
по данным Переписи населения 2011 года
Оба пола мужчины женщины
Все население 240 705 111 885 128 820
Городское население 121 255 53 717 67 538
Сельское население 119 450 58 168 61 282
г. Сухум 62 914 27 778 35 136
Гагрский район 40 217 18 140 22 077
Городское население 26 451 11 695 14 756
г. Гагра 12 364 5 392 6 972
г. Пицунда 4 198 1 770 2 428
пгт Бзыпта 4 719 2 174 2 545
пгт Цандрыпш 5 170 2 359 2 811
Сельское население 13 766 6 445 7 321
Гудаутский район 36 775 17 553 19 222
Городское население 10 082 4 438 5 644
г. Гудаута 8 514 3 767 4 747
г. Новый-Афон 1 518 642 876
пгт Мысра 50 29 21
Сельское население 26 693 13 115 13 578
19
[331 words in 50 rows]
Сухумский район 11 531 5 610 5 921
Гулрыпшский район 18 032 8 626 9 406
Городское население 3 910 1 732 2 178
пгт Гулрыпш 3 910 1 732 2 178
Сельское население 14 122 6 894 7 228
Очамчырский район 24 868 11 955 12 913
Городское население 5 280 2 315 2 965
г. Очамчыра 5 280 2 315 2 965
Сельское население 19 588 9 640 9 948
Ткуарчалский район 16 012 7 666 8 346
Городское население 5 013 2 257 2 756
г. Ткуарчал 5 013 2 257 2 756
Сельское население 10 999 5 409 5 590
Галский район 30 356 14 557 15 799
Городское население 7 605 3 502 4 103
г. Гал 7 605 3 502 4 103
Сельское население 22 751 11 055 11 696
1.8 Численность наличного населения по административно-
территориальным образованиям
на 1 января 2023 года
Оба пола мужчины женщины
Все население 243 958 114 951 129 007
Городское население 122 267 55 623 66 644
Сельское население 121 691 59 328 62 363
г. Сухум 65 087 29 942 35 145
Гагрский район 38 656 17 538 21 118
Городское население 25 439 11 382 14 057
г. Гагра 11 765 5 229 6 536
г. Пицунда 3 970 1 705 2 265
пгт Бзыпта 4 825 2 232 2 593
пгт Цандрыпш 4 879 2 216 2 663
Сельское население 13 217 6 156 7 061
Гудаутский район 38 646 18 540 20 106
Городское население 10 296 4 529 5 767
г. Гудаута 8 715 3 868 4 847
г. Новый-Афон 1 520 626 894
пгт Мысра 61 35 26
Сельское население 28 350 14 011 14 339
Сухумский район 11 259 5 459 5 800
Гулрыпшский район 17 620 8 503 9 117
Городское население 3 753 1 711 2 042
пгт Гулрыпш 3 753 1 711 2 042
Сельское население 13 867 6 792 7 075
Очамчырский район 25 994 12 599 13 395
Городское население 5 221 2 345 2 876
г. Очамчыра 5 221 2 345 2 876
20
[349 words in 47 rows]
1.11 Численность наличного населения по административно-
территориальным образованиям
на 1 января 2026 года
Оба пола мужчины женщины
Все население 243 977 115 252 128 725
Городское население 122 161 55 815 66 346
Сельское население 121 816 59 437 62 379
г. Сухум 65 180 30 163 35 017
Гагрский район 38 384 17 457 20 927
Городское население 25 299 11 345 13 954
г. Гагра 11 729 5 224 6 505
г. Пицунда 3 949 1 702 2 247
пгт Бзыпта 4 814 2 222 2 592
пгт Цандрыпш 4 807 2 197 2 610
Сельское население 13 085 6 112 6 973
Гудаутский район 38 830 18 648 20 182
Городское население 10 307 4 533 5 774
г. Гудаута 8 744 3 888 4 856
г. Новый-Афон 1 504 611 893
пгт Мысра 59 34 25
Сельское население 28 523 14 115 14 408
Сухумский район 11 212 5 445 5 767
Гулрыпшский район 17 489 8 451 9 038
Городское население 3 704 1 699 2 005
пгт Гулрыпш 3 704 1 699 2 005
Сельское население 13 785 6 752 7 033
Очамчырский район 26 073 12 650 13 423
Городское население 5 154 2 332 2 822
г. Очамчыра 5 154 2 332 2 822
Сельское население 20 919 10 318 10 601
Ткуарчалский район 16 458 7 925 8 533
Городское население 5 024 2 309 2 715
г. Ткуарчал 5 024 2 309 2 715
Сельское население 11 434 5 616 5 818
Галский район 30 351 14 513 15 838
Городское население 7 493 3 434 4 059
г. Гал 7 493 3 434 4 059
Сельское население 22 858 11 079 11 779
23
[285 words in 39 rows]
1. 12 Национальный состав наличного населения
по данным Переписи населения 2011 года
в том числе
й й н н н
- - -
й и ш о р о л о
м и й
В с е г о п о и к й ы й а й
у н н к н п и н
Национальности к с а а ч а
х о о с о ы ч к о
А б х а з и и с т м р р р р
у й й й м с й
р у р а
С а а у а й й й л а
г а л а у
р р х р и и и а р
а д ч к
. у у Г
г Г у к О к к
С Г Т
Г с с с
Все население 240 705 62 914 40 217 36 775 11 531 18 032 24 868 16 012 30 356
в том числе:
Абхазы 122 175 42 342 15 482 30 125 3 505 6 057 19 328 5 128 208
Русские 22 064 9 288 6 334 1 838 864 2 048 967 537 188
Армяне 41 906 6 192 15 422 3 667 6 467 8 430 1 646 56 26
Грузины 43 248 1 692 999 487 233 796 1 980 9 285 27 776
Украинцы 1 743 697 529 135 58 162 74 67 21
Белорусы 285 80 95 22 14 36 19 14 5
Греки 1 381 645 259 117 146 125 58 20 11
Мегрелы 3 207 58 4 19 1 3 386 701 2 035
Осетины 605 215 199 56 16 36 22 49 12
Татары 338 112 101 34 40 30 10 7 4
Турки 731 217 60 35 91 69 193 66 -
Цыгане 261 248 4 1 - 5 2 1 -
Эстонцы 351 60 238 7 9 32 3 2 -
Другие национальности 2 410 1 068 491 232 87 203 180 79 70
[338 words in 38 rows]
1. 16 Национальный состав наличного населения
на 1 января 2026 года
в том числе
й й й
й и и и
й
й и к к к
м и й
В с е г о п о и к сн сн с
у н н к н н и н
Национальности к ш р л
х о с о с о о о о к о
А б х а з и и с т ы а
у й й м й п й й й с й
р у ч
С а а у а ы а ч а а л а
г а р
р р х р р м р р а р
а д р а
. у Г
г Г у л а у
С ч
Г у к
Г О Т
Все население 243 977 65 180 38 384 38 830 11 212 17 489 26 073 16 458 30 351
в том числе:
Абхазы 125 469 43 867 14 778 31 802 3 408 5 876 20 259 5 267 212
Русские 22 230 9 647 6 065 1 942 841 1 976 1 017 560 182
Ар мяне 41 203 6 388 14 739 3 805 6 290 8 184 1 721 49 27
Грузины 43 685 1 825 959 505 224 769 2 085 9 546 27 772
/
Украинцы 1 751 717 498 155 56 157 78 66 24
Белорусы 265 65 76 39 11 34 21 13 6
Греки 1 346 652 230 116 146 122 52 16 12
Мегрелы 3 267 65 3 19 2 3 417 724 2 034
Ос етины 591 195 191 78 11 34 18 49 15
Татары 343 130 76 39 34 34 8 16 6
Турки 743 195 76 39 89 69 209 66 -
Цыгане 289 261 3 12 3 5 3 2 -
Эстонцы 350 65 230 8 8 34 3 2 -
Другие национальности 2 445 1 108 460 271 89 192 182 82 61
[336 words in 41 rows]"""

ADMIN1 = [{"id": "A", "name": "Abkhazia"}, {"id": "S", "name": "Samegrelo-Zemo Svaneti"}]
ADMIN2 = [{"id": name[:3].upper(), "name": name, "parent": "A"}
          for name in ("Gagra", "Gali", "Gudauta", "Gulripshi", "Ochamchire", "Sokhumi")] + [
          {"id": "ZUG", "name": "Zugdidi", "parent": "S"}]


class Tables(unittest.TestCase):
    def setUp(self):
        self.figures = a.read(YEARBOOK)

    def test_the_count_for_1_january_2026(self):
        people = self.figures["people"]
        self.assertEqual(people[a.WHOLE], (243977, 115252, 128725))
        self.assertEqual(people["Гагрский район"], (38384, 17457, 20927))
        self.assertEqual(people["Гудаутский район"], (38830, 18648, 20182))
        self.assertEqual(people["г. Сухум"], (65180, 30163, 35017))
        self.assertEqual(sum(people[d][0] for d in a.DISTRICTS), 243977)

    def test_the_2011_census_by_nationality(self):
        nat = self.figures["nationality"]
        self.assertEqual(sum(nat[a.WHOLE].values()), 240705)
        self.assertEqual(nat[a.WHOLE]["Abkhaz"], 122175)
        self.assertEqual(nat[a.WHOLE]["Mingrelian"], 3207)
        # Columns are told apart by their totals, not their sideways headings.
        self.assertEqual(sum(nat["Гагрский район"].values()), 40217)
        self.assertEqual((nat["Гагрский район"]["Abkhaz"], nat["Гагрский район"]["Armenian"]),
                         (15482, 15422))
        self.assertEqual(nat["Галский район"]["Georgian"], 27776)
        self.assertEqual(nat["Галский район"]["Turkish"], 0)       # printed "-"

    def test_the_median_age_is_the_census_s(self):
        # 120,352.5 people are younger than the median; 110,851 are under 35,
        # and the 35-39 group holds 15,877: 35 + 5 * 9,501.5 / 15,877.
        self.assertEqual(self.figures["median"], 38.0)

    def test_a_table_for_2026_that_is_a_new_count_stops_the_run(self):
        moved = YEARBOOK.replace("Ар мяне 41 203 6 388 14 739 3 805",
                                 "Ар мяне 41 503 6 388 14 739 4 105")
        moved = moved.replace("Абхазы 125 469 43 867 14 778 31 802",
                              "Абхазы 125 169 43 867 14 778 31 502")
        with self.assertRaises(SystemExit) as stop:
            a.read(moved)
        self.assertIn("table 1.16 moves Gudauta district's", str(stop.exception))

    def test_ages_for_2026_that_are_not_the_census_s_shares_stop_the_run(self):
        aged = YEARBOOK.replace("0 – 4 12 687 5,2 939", "0 – 4 12 687 5,3 939")
        with self.assertRaises(SystemExit) as stop:
            a.read(aged)
        self.assertIn("table 1.6 prints 5,3", str(stop.exception))

    def test_a_later_edition_is_not_read_as_this_one(self):
        later = YEARBOOK.replace("образованиям\nна 1 января 2026 года",
                                 "образованиям\nна 1 января 2027 года")
        self.assertNotEqual(later, YEARBOOK)
        with self.assertRaises(SystemExit) as stop:
            a.read(later)
        self.assertIn("not dated", str(stop.exception))


class Numbers(unittest.TestCase):
    def test_spaces_between_thousands(self):
        self.assertEqual(a.numbers("62 914 27 778 35 136", 3, lambda r: r[0] == r[1] + r[2], "x"),
                         [62914, 27778, 35136])
        self.assertEqual(a.numbers("244236 122 523 121 713", 3, lambda r: r[0] == r[1] + r[2], "x"),
                         [244236, 122523, 121713])
        self.assertEqual(a.numbers("261 248 4 1 - 5 2 1 -", 9, lambda r: r[0] == sum(r[1:]), "x"),
                         [261, 248, 4, 1, 0, 5, 2, 1, 0])

    def test_a_row_that_adds_up_two_ways_stops_the_run(self):
        with self.assertRaises(SystemExit):
            a.numbers("1 1 1", 2, lambda r: True, "x")


class Records(unittest.TestCase):
    def setUp(self):
        self.rows = {r["name"]: r for r in a.records(a.read(YEARBOOK), ADMIN1, ADMIN2)}

    def test_the_republic(self):
        r = self.rows["Abkhazia"]
        self.assertEqual((r["level"], r["shape_id"], r["match_by"]), ("admin1", "A", "shape_id"))
        self.assertEqual((r["population"]["value"], r["population"]["year"]), (243977, 2026))
        self.assertEqual((r["sex_ratio"]["value"], r["sex_ratio"]["year"]), (89.5, 2026))
        self.assertEqual((r["median_age"]["value"], r["median_age"]["year"]), (38.0, 2011))
        self.assertEqual(r["ethnicity_year"], 2011)
        self.assertEqual(r["ethnicity"][0], {"group": "Abkhaz", "pct": 50.8, "count": 122175})
        self.assertEqual(sum(g["count"] for g in r["ethnicity"]), 240705)
        self.assertEqual(r["religion"]["status"], "not_available")
        self.assertIn("2011", r["median_age_note"])

    def test_the_two_districts_drawn_as_they_are(self):
        gagra, gudauta = self.rows["Gagra"], self.rows["Gudauta"]
        self.assertEqual((gagra["shape_id"], gagra["population"]["value"]), ("GAG", 38384))
        self.assertEqual((gudauta["shape_id"], gudauta["population"]["value"]), ("GUD", 38830))
        self.assertEqual(gagra["sex_ratio"]["value"], 83.4)
        self.assertEqual(gudauta["ethnicity"][0]["group"], "Abkhaz")
        self.assertEqual(gagra["median_age"]["status"], "not_available")
        self.assertNotIn(0, [g["count"] for g in gagra["ethnicity"]])

    def test_sokhumi_is_the_city_and_its_district_together(self):
        r = self.rows["Sokhumi"]
        self.assertEqual((r["shape_id"], r["population"]["value"]), ("SOK", 65180 + 11212))
        # 30,163 + 5,445 men and 35,017 + 5,767 women.
        self.assertEqual(r["sex_ratio"]["value"], round(100 * 35608 / 40784, 1))
        self.assertEqual(sum(g["count"] for g in r["ethnicity"]), 62914 + 11531)
        self.assertEqual(r["ethnicity"][0], {"group": "Abkhaz", "pct": 61.6, "count": 45847})
        self.assertIn("65,180", r["population_note"])
        self.assertIn("11,212", r["population_note"])
        self.assertIn("7%", r["population_note"])
        self.assertIn("added together", r["ethnicity_note"])
        self.assertEqual(r["median_age"]["status"], "not_available")

    def test_the_sex_ratio_says_what_the_census_counted(self):
        note = self.rows["Abkhazia"]["sex_ratio_note"]
        self.assertIn("115,252 men and 128,725 women", note)
        self.assertIn("111,885 men and 128,820 women, 86.9 men per 100 women", note)
        self.assertIn("33,388 men and 41,057 women", self.rows["Sokhumi"]["sex_ratio_note"])

    def test_the_three_outlines_that_are_no_district_say_why(self):
        for name in ("Gulripshi", "Ochamchire", "Gali"):
            r = self.rows[name]
            for field in ("population", "sex_ratio", "ethnicity"):
                self.assertEqual(r[field]["status"], "not_available", (name, field))
                self.assertTrue(r[field]["not_this_ground"], (name, field))
            self.assertEqual(r["sources"], [])
        self.assertIn("17,489", self.rows["Gulripshi"]["population"]["note"])
        self.assertIn("a quarter", self.rows["Gulripshi"]["population"]["note"])
        for name in ("Ochamchire", "Gali"):
            self.assertIn("72,882", self.rows[name]["population"]["note"])
        self.assertEqual(26073 + 16458 + 30351, 72882)
        self.assertIn("at least 12,066 of the district's 30,356",
                      self.rows["Gali"]["population"]["note"])
        self.assertEqual(sum(a.ENGURI.values()), 12066)
        # The outlines follow the old districts only roughly: the town of
        # Ochamchira lies in the one drawn as Gali.
        for name in ("Ochamchire", "Gali"):
            note = self.rows[name]["population"]["note"]
            self.assertNotIn("are the districts as they were before", note)
            self.assertIn("only roughly", note)
            self.assertIn("town of Ochamchira", note)
            self.assertIn("5,154 people on 1 January 2026", note)
        self.assertIn("its centre just inside the outline drawn as Gali",
                      self.rows["Ochamchire"]["population"]["note"])
        self.assertIn("the centre of the town of Ochamchira", self.rows["Gali"]["population"]["note"])

    def test_each_unit_names_its_largest_town(self):
        expect = {"Abkhazia": ("Sokhumi", 65180), "Sokhumi": ("Sokhumi", 65180),
                  "Gagra": ("Gagra", 11729), "Gudauta": ("Gudauta", 8744)}
        for name, (town, people) in expect.items():
            r = self.rows[name]
            self.assertEqual(r["largest_settlement"], town, name)
            self.assertEqual((r["largest_settlement_population"]["value"],
                              r["largest_settlement_population"]["year"]), (people, 2026), name)
            self.assertIn("table 1.11", r["largest_settlement_note"])
            self.assertIn("largest_settlement", [s["field"] for s in r["sources"]])
        # Not New Athos railway station's 26,636, which are Gagra's people.
        self.assertIn("town of Gudauta", self.rows["Gudauta"]["largest_settlement_note"])
        # The outlines that are no district name none; GeoNames is left to.
        for name in ("Gulripshi", "Ochamchire", "Gali"):
            self.assertEqual(self.rows[name]["largest_settlement"]["status"], "not_available")

    def test_a_village_that_may_outnumber_the_town_stops_the_run(self):
        figures = a.read(YEARBOOK)
        with mock.patch.dict(a.VILLAGES_2011, {"Гудаутский район": 8500}):
            with self.assertRaises(SystemExit) as stop:
                a.largest_town(("Гудаутский район",), figures)
        self.assertIn("may be larger than г. Гудаута", str(stop.exception))
        with mock.patch.dict(a.VILLAGES_2011, clear=True):
            with self.assertRaises(SystemExit):
                a.largest_town(("Гагрский район",), figures)
        # The city outnumbers every district whole, so the republic needs none.
        self.assertEqual(a.largest_town((a.WHOLE,), figures), ("г. Сухум", 65180))

    def test_a_district_s_towns_make_its_urban_row(self):
        broken = YEARBOOK.replace("г. Гудаута 8 744 3 888 4 856", "г. Гудаута 8 745 3 889 4 856")
        self.assertNotEqual(broken, YEARBOOK)
        with self.assertRaises(SystemExit) as stop:
            a.read(broken)
        self.assertIn("towns in Gudauta district", str(stop.exception))

    def test_the_town_of_ochamchira_is_read_from_its_own_row(self):
        figures = a.read(YEARBOOK)
        self.assertEqual(figures["towns"]["Очамчырский район"], {a.TOWN: 5154})
        self.assertNotIn(a.TOWN, figures["people"])

    def test_sokhumi_names_no_distance_that_holds_for_one_point_only(self):
        note = self.rows["Sokhumi"]["population_note"]
        self.assertIn("whose centre lies in this one.", note)
        self.assertNotIn("km", note)

    def test_zugdidi_says_what_its_outline_takes_in_beyond_the_enguri(self):
        import build_entities as be
        notes = be.ROW_NOTES["georgia.json"]["GEO-GEOSTAT-92138335B56355921545740"]
        self.assertEqual(set(notes), {"population", "median_age", "sex_ratio", "ethnicity"})
        for note in notes.values():
            self.assertIn("Enguri", note)
            self.assertIn(f"{round(sum(a.ENGURI.values()), -3):,.0f} or more people", note)

    def test_the_notes_speak_to_a_reader(self):
        for r in self.rows.values():
            for key, value in r.items():
                note = value.get("note") if isinstance(value, dict) else (
                    value if key.endswith("_note") else None)
                if note:
                    for word in ("owner", "agent", "adapter", "pipeline", ".json", "runner"):
                        self.assertNotIn(word, note.lower(), (r["name"], key))

    def test_a_map_drawn_differently_stops_the_run(self):
        with self.assertRaises(SystemExit):
            a.records(a.read(YEARBOOK), ADMIN1, ADMIN2[:-2])


if __name__ == "__main__":
    unittest.main()
