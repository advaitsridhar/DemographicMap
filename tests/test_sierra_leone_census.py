"""Sierra Leone's 2015 census tables, as pypdf reads Statistics Sierra Leone's reports.

The page texts below are copied from the runner's log of the two reports.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import sierra_leone_census as s  # noqa: E402

A31 = """Table A3.1 Total population by region, district and sex, 1963-2015
Percentage distribution 2015 Census
Region/district 1963 1974 1985 2004 Total Male Female
Sierra Leone 2,180,355 2,735,159 3,515,812 4,976,871 7,092,113 3,490,978 3,601,135
Eastern 545,579 775,931 960,551 1,191,539 1,642,370 814,441 827,929
Kailahun 150,236 180,365 233,839 358,190 526,379 260,586 265,793
Kenema 227,428 266,636 337,055 497,948 609,891 301,104 308,787
Kono 167,915 328,930 389,657 335,401 506,100 252,751 253,349
Northern 897,566 1,046,158 1,259,641 1,745,553 2,508,201 1,224,828 1,283,373
Bombali 198,776 233,626 317,729 408,390 606,544 296,683 309,861
Kambia 137,806 155,341 186,231 270,462 345,474 165,541 179,933
Koinadugu 129,061 158,626 183,286 265,758 409,372 204,498 204,874
Port Loko 247,463 292,244 329,344 453,746 615,376 294,954 320,422
Tonkolili 184,460 206,321 243,051 347,197 531,435 263,152 268,283
Southern 542,187 596,758 741,377 1,092,657 1,441,308 702,151 739,157
Bo 209,754 217,711 268,671 463,668 575,478 280,569 294,909
Bonthe 80,139 87,561 105,107 139,687 200,781 99,014 101,767
Moyamba 167,425 188,745 250,514 260,910 318,588 153,699 164,889
Pujehun 84,869 102,741 117,185 228,392 346,461 168,869 177,592
Western 195,023 316,312 554,243 947,122 1,500,234 749,558 750,676
Western Area
Rural 67,106 40,065 84,467 174,249 444,270 221,351 222,919
Western Area
Urban 127,917 276,247 469,776 772,873 1,055,964 528,207 527,757
"""

T312 = """Table 3.12 Percentage distribution of the total population
by age, median age, dependency ratio, region and district
Region/district Age groups (years)
0-14 15-24 25-49 50-64 65+    Total Median age
Total country 40.8 21.7 24.9 9.2 3.5 100.0 18.7
Eastern 41.3 21.9 24.3 9.1 3.4 100.0 18.3
Kailahun 41.6 22.5 23.5 8.9 3.5 100.0 18.0
Kenema 40.3 22.1 24.8 9.4 3.5 100.0 18.8
Kono 42.1 21.1 24.6 9.0 3.3 100.0 18.1
Northern 43.8 20.3 23.2 9.1 3.7 100.0 17.6
Bombali 42.2 20.8 23.4 9.5 4.1 100.0 18.3
Kambia 44.7 19.4 22.6 9.2 4.1 100.0 17.3
Koinadugu 45.1 22.4 21.8 8.2 2.7 100.0 16.8
Port Loko 43.2 18.9 24.2 9.6 4.0 100.0 18.1
Tonkolili 44.8 20.1 23.3 8.6 3.2 100.0 17.2
Southern 42.2 20.7 23.6 9.4 4.0 100.0 18.2
Bo 40.9 21.5 24.1 9.5 4.0 100.0 18.7
Bonthe 42.7 20.6 23.5 9.1 4.0 100.0 18.0
Moyamba 43.0 17.7 23.5 10.8 5.0 100.0 18.4
Pujehun 43.2 22.3 23.1 8.2 3.2 100.0 17.5
Western 34.0 24.6 29.4 9.3 2.7 100.0 21.5
Western Area
Rural 37.3 23.5 27.7 8.9 2.6 100.0 20.2
Western Area
Urban 32.6 25.1 30.1 9.5 2.7 100.0 22.0
"""

T323 = """Table 3.23 Distribution of the household population
by region, district and most common main language
% Others Total
Total country Mende 29.2 Temne 26.2 Krio 17.9 26.8 100.0
Eastern Mende 53.0 Kono 17.6 Kissi 9.1 20.3 100.0
Kailahun Mende 69.8 Kissi 22.0 Krio 3.0 5.2 100.0
Kenema Mende 80.2 Krio 7.2 Temne 3.9 8.7 100.0
Kono Kono 56.0 Krio 11.1 Temne 7.4 25.6 100.0
Northern Temne 55.3 Limba 11.4 Koranko 9.5 23.8 100.0
Bombali Temne 42.8 Limba 20.0 Krio 11.8 25.4 100.0
Kambia Temne 53.7 Susu 20.6 Limba 15.7 10.0 100.0
Koinadugu Koranko 49.3 Limba 14.2 Fullah 11.2 25.2 100.0
Port Loko Temne 81.7 Krio 6.2 Susu 3.7 8.3 100.0
Tonkolili Temne 80.3 Limba 6.9 Koranko 6.4 6.3 100.0
Southern Mende 76.4 Temne 6.9 Krio 6.0 10.2 100.0
Bo Mende 76.5 Krio 10.7 Temne 5.0 7.8 100.0
Bonthe Mende 80.4 Sherbro 12.0 Krio 2.8 4.7 100.0
Moyamba Mende 54.8 Temne 20.7 Sherbro 12.5 12.0 100.0
Pujehun Mende 93.8 Krio 2.2 Time 0.6 3.4 100.0
Western Krio 59.9 Temne 20.3 Mende 5.3 14.5 100.0
Western Area Rural Krio 38.4 Temne 34.6 Mende 7.1 19.8 100.0
Western Area Urban Krio 69.0 Temne 14.2 Mende 4.6 12.2 100.0
"""

T52A = """Table 5.2: Ethnic composition of Sierra Leone, regions and district
Region Krio Mende Temne  Limba Kono Koranko Fullah Susu
Sierra Leone 1.3 31.9 31.4 8.4 5.1 4.4 3.8 2.9
Eastern 0.2 54.7 4.8 2.2 19.4 2.1 2.6 0.5
Northern 0.2 1.1 57.0 13.8 0.2 10.1 3.8 5.8
Southern 0.3 78.1 8.0 0.9 0.3 0.2 1.8 0.5
Western
Area 5.4 14.1 40.3 13.2 2.3 1.6 6.9 3.0
District
Kailahun 0.1 70.7 1.0 0.6 1.0 0.1 0.9 0.1
Kenema 0.3 83.4 4.8 1.8 0.6 0.4 3.1 0.7
Kono 0.3 3.3 8.6 4.5 61.2 6.0 3.8 0.5
Bombali 0.3 1.4 45.0 24.8 0.3 0.6 4.4 6.5
Kambia 0.1 0.7 54.8 17.9 0.1 0.1 1.7 20.8
Koinadugu 0.1 0.4 3.4 15.8 0.3 51.3 11.9 0.2
Port Loko 0.4 1.7 84.4 4.1 0.3 0.2 1.5 5.2
Tonkolili 0.2 0.9 81.5 8.1 0.2 7.3 0.9 0.1
Bo 0.5 81.9 6.7 1.7 0.4 0.2 2.8 0.6
Bonthe 0.4 72.4 1.6 0.3 0.2 0.1 1.0 0.4
Moyamba 0.3 55.4 22.3 0.7 0.4 0.1 1.5 1.0
Pujehun 0.1 95.8 0.7 0.3 0.1 0.3 0.7 0.1
Western
Area Rural 3.4 12.8 47.4 11.3 2.4 1.5 6.1 2.5
Western
Area Urban 6.2 14.6 37.3 14.1 2.3 1.6 7.3 3.1
"""

T52B = """Table 5.2: Ethnic composition of Sierra Leone, regions and district
(continued)
Region  Kissi Loko Madingo Sherbro Yalunka Krim Vai  Non- S/Leonean,
Sierra Leone 2.5 2.3 2.3 1.9 0.7 0.2 0.0 0.5
Eastern 9.9 0.3 2.1 0.3 0.1 0.0 0.0 0.6
Northern 0.1 3.2 2.1 0.5 1.8 0.0 0.0 0.2
Southern 0.2 0.5 1.4 6.2 0.0 1.0 0.0 0.4
Western
Area 0.6 4.9 3.6 2.0 0.3 0.0 0.0 1.2
District
Kailahun 23.5 0.1 0.9 0.1 0.0 0.0 0.0 0.3
Kenema 0.9 0.5 2.2 0.5 0.1 0.0 0.0 0.6
Kono 6.5 0.4 3.4 0.2 0.4 0.0 0.0 0.7
Bombali 0.1 12.2 3.7 0.1 0.1 0.0 0.0 0.3
Kambia 0.0 0.2 0.5 2.4 0.0 0.0 0.0 0.4
Koinadugu 0.1 0.1 5.4 0.0 10.6 0.0 0.0 0.3
Port Loko 0.1 0.7 0.8 0.3 0.0 0.0 0.0 0.2
Tonkolili 0.0 0.2 0.3 0.1 0.0 0.0 0.0 0.1
Bo 0.3 0.6 2.6 0.9 0.1 0.0 0.0 0.6
Bonthe 0.1 0.1 0.3 16.2 0.0 6.6 0.0 0.1
Moyamba 0.1 1.0 0.8 15.9 0.0 0.0 0.0 0.2
Pujehun 0.2 0.1 0.4 0.2 0.0 0.4 0.1 0.3
Western
Area Rural 0.6 4.5 2.7 3.2 0.3 0.0 0.0 0.9
Western
Area Urban 0.6 5.0 3.9 1.5 0.3 0.0 0.0 1.3
"""

T53A = """Table 5.3 Religious composition of household population
in Sierra Leone by regions and districts
Region Christianity Islam  Bahai Traditional Other No Religion
Sierra Leone 21.9 77.0 0.5 0.1 0.7 0.3
Eastern 29.0 69.4 0.1 0.1 1.2 0.2
Northern 13.7 85.1 0.0 0.0 0.6 0.5
Southern 19.2 79.9 0.0 0.0 0.6 0.3
Western
Area 30.1 69.1 0.1 0.0 0.6 0.1
District
Kailahun 34.0 64.0 0.1 0.2 1.4 0.3
Kenema 12.8 86.7 0.0 0.0 0.4 0.1
Kono 43.5 54.3 0.1 0.2 1.8 0.1
Bombali 26.9 71.4 0.0 0.0 1.2 0.4
Kambia 5.3 94.1 0.0 0.0 0.3 0.3
Koinadugu 12.7 86.6 0.0 0.0 0.4 0.2
Port Loko 5.9 92.8 0.0 0.0 0.5 0.8
"""

T53B = """Table 5.3- Religious composition of household population
in Sierra Leone by regions and districts (continued)
District
Tonkolili 14.0 84.9 0.0 0.1 0.5 0.4
Bo 26.9 72.1 0.0 0.0 0.7 0.2
Bonthe 13.1 85.4 0.0 0.0 1.4 0.1
Moyamba 24.9 74.2 0.0 0.0 0.4 0.4
Pujehun 4.8 94.6 0.0 0.0 0.1 0.5
Western
Area Rural 27.3 72.0 0.1 0.0 0.6 0.1
Western
Area Urban 31.3 67.9 0.1 0.0 0.6 0.1
Table 5.4: Youth population (15-35 years) Sierra Leone,
Sierra Leone 7,092,113 2,794,301 39.4 131758 47.2 1476720 52.8
Eastern 1,642,370 646472 39.4 302383 46.8 344089 53.2
"""


class SierraLeoneTest(unittest.TestCase):
    def test_population_and_sex(self):
        pop = s.read_population([A31])
        s.check_population(pop)
        self.assertEqual(pop["Western Area Urban"], (1055964, 528207, 527757))
        self.assertEqual(pop["Western"], (1500234, 749558, 750676))

    def test_median(self):
        med = s.read_median([T312])
        self.assertEqual(med["Koinadugu"], 16.8)
        self.assertEqual(med["Western Area Rural"], 20.2)
        self.assertEqual(med["Sierra Leone"], 18.7)

    def test_language_with_its_spelling(self):
        lang = s.read_language([T323])
        self.assertEqual(lang["Pujehun"], {"Mende": 93.8, "Krio": 2.2, "Temne": 0.6, "Other": 3.4})
        self.assertEqual(lang["Western Area Urban"]["Krio"], 69.0)

    def test_ethnicity_both_halves(self):
        eth = s.read_ethnicity([T52A, T52B])
        self.assertEqual(eth["Kailahun"]["Kissi"], 23.5)
        self.assertEqual(eth["Western"]["Krio"], 5.4)
        self.assertEqual(len(eth["Bo"]), 16)

    def test_religion_over_two_pages(self):
        rel = s.read_religion([T53A, T53B])
        self.assertEqual(rel["Pujehun"]["Islam"], 94.6)
        self.assertEqual(rel["Western"]["Christianity"], 30.1)

    def test_build_binds_each_polygon_by_name(self):
        tables = {"population": s.read_population([A31]), "median": s.read_median([T312]),
                  "language": s.read_language([T323]),
                  "ethnicity": s.read_ethnicity([T52A, T52B]),
                  "religion": s.read_religion([T53A, T53B])}
        admin1 = [{"id": f"r{i}", "name": n}
                  for i, n in enumerate(("Eastern", "Northern", "Southern", "Western Area"))]
        parent = {d: f"r{i}" for i, ds in enumerate(s.REGIONS.values()) for d in ds}
        admin2 = [{"id": f"d{d}", "name": d, "parent": parent[d]} for d in s.DISTRICTS]
        records = s.build(tables, admin1, admin2)
        self.assertEqual(len(records), 18)
        bombali = next(r for r in records if r["name"] == "Bombali")
        # The ratio from the counts (95.7), not the thematic report's 98.7.
        self.assertEqual(bombali["sex_ratio"]["value"], 95.7)
        west = next(r for r in records if r["name"] == "Western Area")
        self.assertEqual(west["population"]["value"], 1500234)
        self.assertEqual(west["median_age"]["value"], 21.5)


if __name__ == "__main__":
    unittest.main()
