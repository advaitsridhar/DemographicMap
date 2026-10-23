"""Tests for the Uganda 2002 census religion adapter, no network.

The fixtures are Table B7 (religion by district) and Table 3A (population by
county) of the 2002 census's tabulations as their text comes out of the PDFs.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import uganda_2002 as u  # noqa: E402

B7 = """Table B7: Religion by District for the Population
Region
District Catholic Anglican SDA Pentecostal Moslem O ther None Total
Central
Kalangala
19,018 8,286 581 1,156 4,986 505 167 34,699
Kampala
405,070 366,919 16,446 106,729 268,787 20,675 3,169 1,187,795
Kayunga
74,032 123,526 4,670 12,407 76,127 3,033 773 294,568
Kiboga
78,986 90,690 9,326 15,736 27,839 5,930 790 229,297
Luwero
151,961 190,511 15,098 23,554 89,232 7,384 752 478,492
Masaka
447,447 119,307 6,484 23,216 164,950 7,579 1,396 770,379
Mpigi
209,600 87,998 5,411 12,301 87,314 4,501 614 407,739
Mubende
318,041 217,660 22,116 38,552 74,781 16,012 2,143 689,305
Mukono
295,409 265,171 14,297 44,909 165,817 8,303 1,208 795,114
Nakasongola
23,138 77,189 4,486 10,899 9,428 1,274 634 127,048
Rakai
255,849 135,575 3,757 16,400 51,348 5,854 1,361 470,144
Sembabule
81,156 55,024 2,377 11,032 27,408 2,483 548 180,028
Wakiso
346,865 297,029 19,045 68,382 164,256 10,947 1,212 907,736
Regional Total
2,706,572 2,034,885 124,094 385,273 1,212,273 94,480 14,767 6,572,344
Eastern
Bugiri
103,192 131,727 3,140 40,255 101,571 31,486 994 412,365
Busia
71,820 89,586 1,267 25,240 22,322 14,173 479 224,887
Iganga
96,523 339,469 5,394 16,618 239,582 10,112 932 708,630
Jinja
90,237 161,479 6,326 20,552 100,257 7,727 671 387,249
Kaberamaido
63,399 47,060 1,545 15,540 956 2,606 521 131,627
Kamuli
172,138 362,055 16,065 30,353 112,177 10,068 4,386 707,242
Kapchorwa
50,245 75,640 1,150 34,311 16,324 8,508 4,104 190,282
Katakwi
176,878 91,539 994 13,741 3,131 6,181 6,436 298,900
Kumi
137,051 197,409 518 29,754 11,632 5,954 7,281 389,599
Mayuge
75,184 106,745 3,868 12,883 117,526 7,961 501 324,668
Mbale
182,908 323,989 8,485 33,725 132,247 33,472 2,708 717,534
Pallisa
149,382 229,165 3,048 31,972 94,231 9,349 3,385 520,532
Sironko
97,699 129,918 5,642 12,893 28,961 7,336 607 283,056
Soroti
131,355 171,834 412 42,255 8,541 8,459 6,765 369,621
Tororo
237,603 207,432 1,613 20,037 63,381 5,950 716 536,732
Region
1,835,614 2,665,047 59,467 380,129 1,052,839 169,342 40,486 6,202,924
2002 Uganda Population and Housing Census Annex 2
37
Table B7: Religion by District for the Population – Cont’d
Region
District Catholic Anglican SDA Pentecostal Moslem O ther None Total
Northern
Adjumani
166,880 16,153 2,290 3,665 11,273 1,723 239 202,223
Apac
352,903 274,518 5,501 38,719 3,999 3,869 4,478 683,987
Arua
476,498 224,572 1,574 4,955 123,229 2,229 481 833,538
Gulu
371,276 82,462 1,126 9,318 4,597 3,309 2,983 475,071
Kitgum
182,165 92,039 643 3,006 1,617 1,276 1,524 282,270
Kotido
321,196 29,010 376 1,627 2,313 167,065 70,283 591,870
Lira
359,565 282,756 7,004 69,078 9,566 9,915 3,009 740,893
Moroto
118,452 9,583 50 596 1,707 37,319 22,200 189,907
Moyo
123,051 29,497 760 4,823 35,569 883 151 194,734
Nakapiripirit
83,544 11,858 127 520 1,390 38,556 18,499 154,494
Nebbi
322,366 76,013 2,154 9,205 17,829 7,021 664 435,252
Pader
231,450 86,870 448 3,087 1,463 2,278 724 326,320
Yumbe
35,526 22,052 284 1,657 191,913 304 22 251,758
Region
3,144,872 1,237,383 22,337 150,256 406,465 275,747 125,257 5,362,317
Western
Bundibugyo
41,033 107,371 28,352 6,788 18,601 6,251 1,424 209,820
Bushenyi
285,342 368,971 7,945 24,747 31,293 9,740 3,179 731,217
Hoima
150,027 140,208 5,425 10,755 17,438 18,254 1,373 343,480
Kabale
201,174 245,217 1,394 3,290 3,753 1,349 1,930 458,107
Kabarole
169,472 121,710 23,815 12,946 17,696 9,472 1,593 356,704
Kamwenge
109,526 114,065 6,439 13,756 10,865 8,256 688 263,595
Kanungu
73,608 115,970 2,089 3,396 5,564 3,460 553 204,640
Kasese
182,765 235,002 43,760 17,997 33,790 8,754 658 522,726
Kibaale
209,822 100,905 10,911 13,772 13,044 54,985 2,322 405,761
Kisoro
93,732 102,231 3,907 11,001 1,693 2,822 4,816 220,202
Kyenjojo
165,780 118,983 5,757 23,044 11,754 48,796 2,995 377,109
Masindi
226,692 166,357 5,350 14,379 31,753 12,866 1,847 459,244
Mbarara
427,355 534,926 10,431 37,754 61,273 10,489 5,784 1,088,012
Ntungamo
106,406 230,066 4,707 11,837 20,688 4,210 1,915 379,829
Rukungiri
112,802 143,524 1,792 8,527 5,339 2,316 801 275,101
Regional
Total
2,555,536 2,845,506 162,074 213,989 284,544 202,020 31,878 6,295,547
UGANDA
10,242,594 8,782,821 367,972 1,129,647 2,956,121 741,589 212,388 24,433,132
* This table excludes population enumerated in hotels; “Other ” includes Orthodox, Bahai, Other Christian, Non-Christian, and Traditional"""

T3A = """2002 UGANDA POPULATION AND HOUSING CENSUS
Table 3A: Total Population by County, Sex, Number o f Households, and Average Household Size
District Population
County Average
Households Male Female Total Household Size
UGANDA 5126762 11929803 12512281 24442084 4.7
Kalangala 12750 20849 13917 34766 2.6
Bujumba 5650 10198 7137 17335 3.0
Kyamuswa 7100 10651 6780 17431 2.3
Kampala 306178 569075 620067 1189142 3.8
Kampala City Council 306178 569075 620067 1189142 3 .8
Kiboga 51305 117080 112392 229472 4.4
Kiboga 51305 117080 112392 229472 4.4
Luwero 106604 236748 241847 478595 4.4
Bamunanika 30556 68131 69068 137199 4.5
Katikamu 45458 99848 104270 204118 4.4
Nakaseke 30590 68769 68509 137278 4.5
Masaka 176882 375787 394875 770662 4.3
Bukomansimbi 30567 68330 71226 139556 4.6
Bukoto 92969 196834 205820 402654 4.3
Kalungu 35560 78505 82179 160684 4.4
Masaka Municipality 17786 32118 35650 67768 3.6
Mpigi 88654 203511 204279 407790 4.6
Butambala 17537 42598 44157 86755 4.9
Gomba 28622 66852 66412 133264 4.6
Mawokota 42495 94061 93710 187771 4.4
Mubende 156161 344636 344894 689530 4.4
Busujju 17137 38409 38436 76845 4.5
Buwekula 49583 111567 110803 222370 4.5
Kassanda 45172 100015 101037 201052 4.4
Mityana 44269 94645 94618 189263 4.2
Mukono 187967 396250 399143 795393 4.2
Buikwe 74080 162931 166927 329858 4.4
Buvuma Islands 12668 23858 18625 42483 3.2
Mukono 63807 128227 129630 257857 4.0
Nakifuma 37412 81234 83961 165195 4.4
Nakasongola 25542 63799 63265 127064 4.9
Buruli 25542 63799 63265 127064 4.9
Rakai 106685 230043 240322 470365 4.4
Kabula 14525 32687 33352 66039 4.5
Kakuuto 19908 42420 43182 85602 4.3
Kooki 39564 86625 91519 178144 4.5
Kyotera 32688 68311 72269 140580 4.3
Ssembabule 39334 89226 90819 180045 4.6
Lwemiyaga 6567 15807 15251 31058 4.7
Mawogola 32767 73419 75568 148987 4.5
Kayunga 62039 143099 151514 294613 4.7
Bbaale 22716 53008 54849 107857 4.7
Ntenjeru 39323 90091 96665 186756 4.7
Wakiso 218142 440534 467454 907988 4.1
Busiro 88562 180420 184886 365306 4.1
Entebbe Municipality 14216 27135 27951 55086 3.8
Kyadondo 115364 232979 254617 487596 4.2
Bugiri 82749 199650 212745 412395 5.0
Bukooli 82749 199650 212745 412395 5.0
Busia 47886 107799 117209 225008 4.7
Samia-bugwe 47886 107799 117209 225008 4.7
Iganga 140225 339131 369559 708690 5.0
Bugweri 23798 56966 62641 119607 5.0
Busiki 33714 81512 86179 167691 5.0
Kigulu 47067 111928 123938 235866 5.0
Luuka 35646 88725 96801 185526 5.2
Jinja 84025 190329 197244 387573 4.5
Butembe 30918 66620 67688 134308 4.3
Jinja Municipality 16534 36325 34888 71213 3.9
Kagoma 36573 87384 94668 182052 5.0
Kamuli 136845 343192 364140 707332 5.1
Budiope 37394 93694 97572 191266 5.1
Bugabula 45240 110383 118483 228866 5.0
Bulamogi 29172 76090 78577 154667 5.3
Buzaaya 25039 63025 69508 132533 5.3
Kapchorwa 39072 93991 96400 190391 4.8
Kongasis 9722 24382 24570 48952 5.0
Kween 13818 33223 33948 67171 4.9
Tingey 15532 36386 37882 74268 4.7
Katakwi 64678 144378 154572 298950 4.6
Amuria 24297 57464 61460 118924 4.9
Kapelebyong 14570 29513 31585 61098 4.2
Usuk 25811 57401 61527 118928 4.6
Kumi 78439 186871 202794 389665 4.9
Bukedea 25767 58598 63835 122433 4.7
Kumi 32673 79518 85847 165365 5.0
Ngora 19999 48755 53112 101867 5.1
Mbale 162518 352554 365686 718240 4.4
Bubulo 58251 127849 134717 262566 4.5
Bungokho 58808 127953 133488 261441 4.4
Manjiya 27909 62189 60914 123103 4.4
Mbale Municipality 17550 34563 36567 71130 3.9
Pallisa 100144 251346 269232 520578 5.2
Butebo 18089 44906 48424 93330 5.1
Kibuku 25070 61675 66544 128219 5.1
Pallisa 30330 78951 83589 162540 5.3
Budaka 26655 65814 70675 136489 5.1
Soroti 70455 180147 189642 369789 5.2
Kasilo 13529 35244 36837 72081 5.3
Serere 19396 50681 53717 104398 5.4
Soroti 27762 73498 78101 151599 5.4
Soroti Municipality 9768 20724 20987 41711 4.1
Tororo 112283 261373 275515 536888 4.8
Bunyole 31949 76584 80905 157489 4.9
Tororo 29435 66200 70073 136273 4.6
Tororo Municipality 8004 17064 17746 34810 4.2
West Budama(kisoko) 42895 101525 106791 208316 4.8
Kaberamaido 25994 64307 67343 131650 5.0
Kaberamaido 12476 31057 32032 63089 5.0
Kalaki 13518 33250 35311 68561 5.1
Mayuge 64005 157564 167110 324674 5.1
Bunya 64005 157564 167110 324674 5.1
Sironko 67349 140219 142873 283092 4.2
Budadiri 43249 91977 93842 185819 4.3
Bulambuli 24100 48242 49031 97273 4.0
Adjumani 31857 100081 102209 202290 5.1
East Moyo 31857 100081 102209 202290 5.1
Apac 143037 334771 349222 683993 4.8
Kole 35093 80456 85466 165922 4.7
Kwania 26313 62825 65649 128474 4.9
Maruzi 25886 59832 61350 121182 4.7
Oyam 55745 131658 136757 268415 4.8
Arua 151851 401596 432332 833928 5.5
Arua Municipality 7443 21588 22341 43929 5.7
Ayivu 31312 81730 90825 172555 5.5
Koboko 20255 63771 65377 129148 6.3
Madi-okollo 17663 45535 48791 94326 5.3
Maracha 28137 69079 76626 145705 5.2
Terego 29432 76299 80105 156404 5.3
Vurra 17609 43594 48267 91861 5.2
Gulu 97173 233908 241352 475260 4.8
Aswa 15706 36112 37795 73907 4.6
Gulu Municipality 21622 59023 60407 119430 5.4
Kilak 29185 66919 68804 135723 4.6
Nwoya 9697 20239 20771 41010 4.2
Omoro 20963 51615 53575 105190 5.0
Kitgum 55973 139557 142818 282375 5.0
Chua 30608 81580 85450 167030 5.4
Lamwo 25365 57977 57368 115345 4.5
Kotido 83506 290889 301000 591889 6.8
Dodoth 49217 188331 195880 384211 7.6
Jie 22927 77053 77551 154604 6.3
Labwor 11362 25505 27569 53074 4.6
Lira 154129 363246 377994 741240 4.8
Dokolo 25801 62988 66397 129385 5.0
Erute 43610 101989 107733 209722 4.8
Kioga 19637 47828 48361 96189 4.9
Lira Municipality 16833 40391 40488 80879 4.6
Moroto 34529 79536 83511 163047 4.7
Otuke 13719 30514 31504 62018 4.5
Moroto 36582 91706 98234 189940 5.1
Bokora 21402 53708 58989 112697 5.2
Matheniko 13650 34418 35445 69863 5.1
Moroto Municipality 1530 3580 3800 7380 4.6
Moyo 38922 99265 95513 194778 5.0
Obongi 17566 45596 41744 87340 4.9
West Moyo 21356 53669 53769 107438 5.0
Nebbi 90040 208056 227304 435360 4.8
Jonam 19453 47192 52286 99478 5.1
Okoro 36582 81224 87824 169048 4.6
Padyere 34005 79640 87194 166834 4.9
Nakapiripirit 27356 76947 77547 154494 5.5
Chekwii 9660 25270 26929 52199 5.4
Pian 7422 17581 21142 38723 5.2
Pokot 10274 34096 29476 63572 5.8
Pader 65852 161119 165219 326338 4.9
Aruu 29374 70610 71710 142320 4.8
Agago 36478 90509 93509 184018 5.0
Yumbe 42576 126226 125558 251784 5.9
Aringa 42576 126226 125558 251784 5.9
Bundibugyo 45130 101326 108652 209978 4.6
Bwamba 35670 76112 82797 158909 4.4
Ntoroko 9460 25214 25855 51069 5.4
Bushenyi 142970 351266 380126 731392 5.1
Buhweju 15353 40578 42303 82881 5.4
Bunyaruguru 22897 49037 52767 101804 4.4
Igara 38772 99547 106124 205671 5.2
Ruhinda 31372 75543 85259 160802 5.1
Sheema 34576 86561 93673 180234 5.2
Hoima 70286 172046 171572 343618 4.6
Bugahya 42214 98265 100568 198833 4.7
Buhaguzi 28072 73781 71004 144785 4.6
Kabale 95071 214552 243766 458318 4.8
Kabale Municipality 9431 20584 20760 41344 4.0
Ndorwa 31479 71662 81933 153595 4.9
Rubanda 35494 79175 93605 172780 4.9
Rukiga 18667 43131 47468 90599 4.8
Kabarole 76853 178354 178560 356914 4.6
Bunyangabu 25938 62020 65042 127062 4.9
Burahya 40640 95892 92967 188859 4.6
Fort Portal Municipality 10275 20442 20551 40993 3. 8
Kasese 98839 252792 270241 523033 5.3
Bukonjo 43138 117234 128958 246192 5.7
Busongora 55701 135558 141283 276841 4.9
Kibaale 85038 200131 205751 405882 4.8
Bugangaizi 22968 53844 54513 108357 4.7
Buyaga 47578 112179 116150 228329 4.8
Buyanja 14492 34108 35088 69196 4.8
Kisoro 48537 99443 120869 220312 4.5
Bufumbira 48537 99443 120869 220312 4.5
Masindi 91799 229572 229918 459490 5.0
Bujenje 16343 39502 37234 76736 4.6
Buliisa 12578 31022 32341 63363 5
Buruuli 28193 66431 65253 131684 4.6
Kibanda 34685 92617 95090 187707 5.4
Mbarara 224820 534562 553794 1088356 4.8
Bukanga 24315 55844 57454 113298 4.6
Ibanda 40891 96965 101670 198635 4.8
Isingiro 43107 97418 105309 202727 4.7
Kashari 32276 78329 81823 160152 4.9
Kazo 21273 55853 55736 111589 5.2
Mbarara Municipality 17749 34214 35149 69363 3.7
Nyabushozi 19128 51523 49107 100630 5.2
Rwampara 26081 64416 67546 131962 5.0
Ntungamo 76428 181835 198152 379987 4.9
Kajara 19204 45197 51133 96330 5.0
Ruhaama 39666 91891 99074 190965 4.8
Rushenyi 17558 44747 47945 92692 5.3
Rukungiri 56222 131052 144110 275162 4.9
Rubabo 23972 56563 63681 120244 5.0
Rujumbura 32250 74489 80429 154918 4.8
Kamwenge 57138 126819 136911 263730 4.6
Kibale 33830 74860 81075 155935 4.6
Kitagwenda 23308 51959 55836 107795 4.6
Kanungu 43466 98627 106105 204732 4.7
Kinkiizi 43466 98627 106105 204732 4.7
Kyenjojo 80401 186571 190600 377171 4.7
Kyaka 22873 55150 55775 110925 4.8
Mwenge 57528 131421 134825 266246 4.6
Source: 2002 Uganda Population and Housing Census
Average household size is the population in households divided by the number of households excluding the
population in institutions, hotels, and homeless
Districts and counties are as of September 12, 2002."""


class TableB7Test(unittest.TestCase):
    def test_districts_regions_and_the_country_add_up(self):
        districts, regions, national = u.read_b7(B7)
        self.assertEqual(len(districts), 56)
        self.assertEqual(sum(national.values()), 24433132)
        self.assertEqual(sum(regions["Northern"].values()), 5362317)
        self.assertEqual(districts["Kampala"]["counts"]["None"], 3169)
        self.assertEqual(districts["Yumbe"]["region"], "Northern")
        self.assertEqual(districts["Yumbe"]["counts"]["Moslem"], 191913)

    def test_a_row_that_does_not_add_up_stops_the_run(self):
        bad = B7.replace("19,018 8,286 581", "19,018 8,286 582")
        with self.assertRaises(SystemExit):
            u.read_b7(bad)

    def test_a_district_misread_breaks_its_regions_total(self):
        # Moving people between two districts' rows keeps each row whole but
        # not the region's columns once one column is shifted.
        bad = B7.replace("74,032 123,526 4,670 12,407 76,127 3,033 773 294,568",
                         "74,033 123,525 4,670 12,407 76,127 3,033 773 294,568")
        with self.assertRaises(SystemExit):
            u.read_b7(bad)


class Table3ATest(unittest.TestCase):
    def test_districts_and_their_counties(self):
        table = u.read_3a(T3A)
        self.assertEqual(len(table), 56)
        single = [(d["name"], c[0]["name"]) for d, c in table if len(c) == 1]
        self.assertEqual(len(single), 10)
        self.assertIn(("Nakasongola", "Buruli"), single)
        self.assertIn(("Kampala", "Kampala City Council"), single)
        luwero = next(c for d, c in table if d["name"] == "Luwero")
        self.assertEqual([x["name"] for x in luwero], ["Bamunanika", "Katikamu", "Nakaseke"])

    def test_a_county_misread_stops_the_run(self):
        bad = T3A.replace("Bamunanika 30556 68131 69068 137199", "Bamunanika 30556 68131 69068 "
                          "137200")
        with self.assertRaises(SystemExit):
            u.read_3a(bad)


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.districts, self.regions, _ = u.read_b7(B7)
        self.table = u.read_3a(T3A)
        self.admin1 = [{"id": f"R{i}", "name": n} for i, n in enumerate(u.REGIONS.values())]
        parent = {n: f"R{i}" for i, n in enumerate(u.REGIONS)}
        names = [("K", "Kampala", "Central"), ("B", "Buruli", "Central"),
                 ("S", "Samia-Bugwe", "Eastern"), ("A", "Aringa", "Northern"),
                 ("M", "Bunya", "Eastern"), ("Q", "Kiboga", "Central"),
                 ("BK", "Bukooli", "Eastern"), ("EM", "East Moyo", "Northern"),
                 ("BF", "Bufumbira", "Western"), ("KK", "Kinkiizi", "Western")]
        self.admin2 = [{"id": i, "name": n, "parent": parent[r]} for i, n, r in names]
        self.counties = [
            {"code": "1021", "district_code": "102", "name": "KAMPALA CENTRAL DIVISION",
             "total": 81658},
            {"code": "1022", "district_code": "102", "name": "KAWEMPE DIVISION", "total": 1},
            {"code": "1061", "district_code": "106", "name": "NAKASONGOLA COUNTY", "total": 1},
            {"code": "2081", "district_code": "208", "name": "BUNYA COUNTY", "total": 1},
            {"code": "2091", "district_code": "209", "name": "JINJA SOUTH DIVISION", "total": 1},
            {"code": "2092", "district_code": "209", "name": "JINJA NORTH DIVISION", "total": 1},
        ]

    def test_regions_and_the_counties_that_were_districts(self):
        placed = {"K": ["1021", "1022"], "B": ["1061"], "M": ["2081", "2091"]}
        straddling = {"A": ["ARINGA EAST COUNTY"]}
        records, report = u.build(self.districts, self.regions, self.table, self.admin1,
                                  self.admin2, placed, straddling, self.counties)
        by = {(r["level"], r["name"]): r for r in records}
        northern = by[("admin1", "Northern Region")]
        self.assertEqual(northern["religion"][0], {"group": "Catholic", "pct": 58.6,
                                                   "count": 3144872})
        self.assertEqual(northern["religion_year"], 2002)
        self.assertIn("2014 and 2024 censuses", northern["religion_note"])
        kampala = by[("admin2", "Kampala")]
        self.assertEqual(sum(g["count"] for g in kampala["religion"]), 1187795)
        self.assertIn("Kampala District", kampala["religion_note"])
        self.assertEqual(kampala["match_by"], "shape_id")
        self.assertIn("Nakasongola District", by[("admin2", "Buruli")]["religion_note"])
        # Aringa is crossed by 2024 counties; Bunya's polygon takes in a
        # division of another district: neither is the 2002 district's ground.
        for name in ("Aringa", "Bunya"):
            self.assertIn("not shown to be the district's ground",
                          by[("admin2", name)]["religion"]["note"])
        # A polygon with no placement at all is not written either.
        self.assertIn("not shown", by[("admin2", "Samia-Bugwe")]["religion"]["note"])
        # Table B7 gives these no religion: it is cited for the note, not a figure.
        for name in ("Aringa", "Bunya", "Samia-Bugwe"):
            self.assertEqual([x["field"] for x in by[("admin2", name)]["sources"]],
                             ["religion note"])
        self.assertEqual([x["field"] for x in kampala["sources"]], ["religion"])
        self.assertEqual(len([r for r in records if r["level"] == "admin2"]), 10)

    def test_no_label_is_left_unmapped(self):
        self.assertEqual(set(u.LABELS), set(u.COLUMNS))


if __name__ == "__main__":
    unittest.main()
