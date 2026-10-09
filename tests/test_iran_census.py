import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import iran_census as ir  # noqa: E402

HEAD = [["", "جدول 1- جمعيت برحسب سن", "", "", "", ""],
        ["", "سن", "جمع", "", "", "نقاط شهري"],
        ["", "", "مردوزن", "مرد", "زن", "مردوزن"]]


def age_sheet(men, women, groups=True):
    """A Table 1 sheet: all ages, then 0-4 and its single years, then the rest."""
    rows = [r[:] for r in HEAD]
    rows.append(["", "تمامي سنين", float(sum(men) + sum(women)), float(sum(men)),
                 float(sum(women)), 0.0])
    labels = ["كمتر از يك ساله"] + [f"{a} ساله" for a in range(1, len(men) - 1)] + \
             [f"{len(men) - 1} ساله و بيشتر"]
    if groups:
        rows.append(["", "0-4 ساله", float(sum(men[:5]) + sum(women[:5])),
                     float(sum(men[:5])), float(sum(women[:5])), 0.0])
    for label, m, w in zip(labels, men, women):
        rows.append(["", label, float(m + w), float(m), float(w), 0.0])
    return rows


CIT_HEAD = ["جنس واستان", "جمع", "ايران", "افغانستان", "عراق", "پاكستان", "تركيه",
            "ساير كشورها", "", "اظهار نشده"]


def cit_sheet(name, counts):
    total = sum(counts)
    row = [float(c) if c else "" for c in counts]
    return [["جدول 3 - جمعيت برحسب ج"], CIT_HEAD,
            ["مردوزن", float(total), *row[:6], "", row[6]],
            [name, float(total), *row[:6], "", row[6]],
            ["مرد", 1.0, 1.0, "", "", "", "", "", "", ""]]


MEN = [10, 10, 10, 10, 10, 9, 8, 7]       # ages 0..6 and 7+
WOMEN = [9, 9, 10, 10, 11, 10, 9, 8]


class Ages(unittest.TestCase):
    def test_single_years_and_checks(self):
        table = ir.parse_ages(age_sheet(MEN, WOMEN), "test")
        self.assertEqual(table["total"], (sum(MEN) + sum(WOMEN), sum(MEN), sum(WOMEN)))
        self.assertEqual(table["men"][0], 10)
        self.assertEqual(table["open"], 7)
        self.assertEqual(table["groups"][(0, 4)], (99, 50, 49))

    def test_a_subtotal_that_disagrees_stops(self):
        rows = age_sheet(MEN, WOMEN)
        rows[4][3] = 49.0       # the 0-4 men's subtotal
        rows[4][2] = 98.0
        with self.assertRaises(SystemExit):
            ir.parse_ages(rows, "test")

    def test_men_and_women_must_make_both(self):
        rows = age_sheet(MEN, WOMEN)
        rows[6][2] = 25.0
        with self.assertRaises(SystemExit):
            ir.parse_ages(rows, "test")

    def test_persian_digits_and_letter_forms_fold(self):
        self.assertEqual(ir.age_of("۱۲ ساله"), ("single", 12))
        self.assertEqual(ir.fa("شهرستان آران وبیدگل"), ir.fa("آران و بيدگل"))
        self.assertEqual(ir.split_sheet_name("اراک0001"), ("اراک", "0001"))
        # The census sheet spells Sari with a hamza seat; OCHA with a plain yeh.
        self.assertEqual(ir.fa("سارئ"), ir.fa("ساری"))


class Citizenship(unittest.TestCase):
    def test_both_sexes_block(self):
        block = ir.parse_citizenship_block(cit_sheet("اراک", [900, 80, 10, 0, 0, 5, 5]), "t")
        total, counts = block["*"]
        self.assertEqual(total, 1000)
        self.assertEqual(counts["Afghan"], 80)
        self.assertEqual(counts["Not stated"], 5)

    def test_categories_must_make_the_total(self):
        rows = cit_sheet("اراک", [900, 80, 10, 0, 0, 5, 5])
        rows[2][1] = 1001.0
        with self.assertRaises(SystemExit):
            ir.parse_citizenship_block(rows, "t")


def county(nn, code, name, men=MEN, women=WOMEN, cit=None):
    table = ir.parse_ages(age_sheet(men, women), name)
    total = table["total"][0]
    return {"province": nn, "code": code, "name": name, "ages": table,
            "citizenship": (total, {"Iranian": total - 2, "Afghan": 2, "Iraqi": 0,
                                    "Pakistani": 0, "Turkish": 0,
                                    "Other nationalities": 0, "Not stated": 0})}


A1 = [{"id": "G", "name": "Golestan"}, {"id": "M1", "name": "Mazandaran"},
      {"id": "M2", "name": "Mazandaran"}]
A2 = [{"id": "g1", "name": "Gorgan", "parent": "G"},
      {"id": "g2", "name": "Turkman", "parent": "G"},
      {"id": "m1", "name": "Sari", "parent": "M1"}, {"id": "m2", "name": "Babol", "parent": "M1"},
      {"id": "z", "name": "Bandar-e-Gaz", "parent": "M2"}]
CODAB = {"Golestan": [{"en": "Gorgan", "fa": "شهرستان گرگان", "pcode": "1"},
                      {"en": "Bandar-e-Torkaman", "fa": "شهرستان ترکمن", "pcode": "2"},
                      {"en": "Bandar-e-Gaz", "fa": "شهرستان بندر گز", "pcode": "3"}],
         "Mazandaran": [{"en": "Sari", "fa": "شهرستان ساری", "pcode": "4"},
                        {"en": "Babol", "fa": "شهرستان بابل", "pcode": "5"}]}


class Binding(unittest.TestCase):
    def counties(self):
        return [county(27, "2701", "گرگان"), county(27, "2702", "تركمن"),
                county(27, "2703", "بندر گز"), county(2, "0201", "ساري"),
                county(2, "0202", "بابل")]

    def test_persian_to_ocha_to_drawn(self):
        bound, notes = ir.bind_counties(self.counties(), CODAB, A1, A2)
        self.assertEqual(bound["2702"]["id"], "g2")       # Bandar-e-Torkaman -> Turkman
        self.assertEqual(bound["2703"]["id"], "z")        # drawn under Mazandaran
        self.assertEqual(bound["0201"]["id"], "m1")

    def test_golestan_less_bandar_e_gaz_and_the_small_polygon(self):
        counties = self.counties()
        provinces = {nn: ir.add_ages([c["ages"] for c in counties if c["province"] == nn])
                     for nn in (2, 27)}
        golestan_total = provinces[27]["total"][0]
        cit = {ir.fa("گلستان"): (golestan_total, {"Iranian": golestan_total - 6, "Afghan": 6,
                                                   "Iraqi": 0, "Pakistani": 0, "Turkish": 0,
                                                   "Other nationalities": 0, "Not stated": 0}),
               ir.fa("مازندران"): (provinces[2]["total"][0],
                                   {"Iranian": provinces[2]["total"][0] - 4, "Afghan": 4,
                                    "Iraqi": 0, "Pakistani": 0, "Turkish": 0,
                                    "Other nationalities": 0, "Not stated": 0})}
        old = ir.PROVINCES
        ir.PROVINCES = {2: old[2], 27: old[27]}
        old_national = ir.NATIONAL
        ir.NATIONAL = sum(t["total"][0] for t in provinces.values())
        try:
            rows, _ = ir.build(provinces, cit, counties, CODAB, A1, A2)
        finally:
            ir.PROVINCES = old
            ir.NATIONAL = old_national
        by_shape = {r["shape_id"]: r for r in rows}
        one = sum(MEN) + sum(WOMEN)
        self.assertEqual(by_shape["G"]["population"]["value"], 2 * one)
        self.assertEqual(by_shape["M2"]["population"]["value"], one)
        self.assertEqual(by_shape["M1"]["population"]["value"], 2 * one)
        afghan = next(s for s in by_shape["G"]["ethnicity"] if s["group"] == "Afghan national")
        self.assertEqual(afghan["count"], 4)
        self.assertEqual(by_shape["g2"]["ethnicity_basis"], "citizenship")
        # Citizenship is written as a nationality, never as a people's name.
        groups = {s["group"] for r in rows for s in r["ethnicity"]}
        self.assertEqual(groups, {"Iranian national", "Afghan national"})

    def test_an_unmatched_shahrestan_stops(self):
        counties = self.counties() + [county(27, "2709", "ناشناخته")]
        with self.assertRaises(SystemExit):
            ir.bind_counties(counties, CODAB, A1, A2)

    def test_a_split_shahrestan_takes_nothing(self):
        codab = {"Tehran": [{"en": "Tehran", "fa": "شهرستان تهران", "pcode": "9"}]}
        a1 = [{"id": "T", "name": "Tehran"}]
        a2 = [{"id": "t1", "name": "Tehran", "parent": "T"},
              {"id": "t2", "name": "City of Tehran", "parent": "T"}]
        bound, notes = ir.bind_counties([county(23, "2301", "تهران")], codab, a1, a2)
        self.assertEqual(bound, {})
        self.assertIn("neither", notes[0])

    def test_haftgel_is_ochas_haftkel(self):
        codab = {"Khuzestan": [{"en": "Haftgol", "fa": "شهرستان هفتکل", "pcode": "IR015013"},
                               {"en": "Shush", "fa": "شهرستان شوش", "pcode": "IR015026"}]}
        a1 = [{"id": "K", "name": "Khuzestan"}]
        a2 = [{"id": "h", "name": "Haftgol", "parent": "K"},
              {"id": "s", "name": "Shush", "parent": "K"}]
        bound, _ = ir.bind_counties([county(6, "0622", "هفتگل"), county(6, "0626", "شوش")],
                                    codab, a1, a2)
        self.assertEqual(bound["0622"]["id"], "h")
        self.assertEqual(bound["0626"]["id"], "s")


# --------------------------------------------------------------------------
# The shahrestans the map draws as two polygons.

TRIPLE = ["مردوزن", "مرد", "زن"]
U_MEN, U_WOMEN = [20, 20, 18, 16, 14, 12, 10, 30], [19, 19, 18, 16, 15, 13, 11, 35]
R_MEN, R_WOMEN = [3, 3, 2, 2, 2, 1, 1, 4], [2, 2, 2, 2, 1, 1, 1, 5]
S_MEN, S_WOMEN = [0, 0, 0, 1, 1, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 0]


def four_block_sheet(blocks):
    """A Table 1 sheet with its four blocks: all, urban, rural, unsettled."""
    total = ([sum(b[0][i] for b in blocks) for i in range(len(blocks[0][0]))],
             [sum(b[1][i] for b in blocks) for i in range(len(blocks[0][1]))])
    blocks = [total] + list(blocks)
    rows = [["", "جدول 1- جمعيت برحسب سن"] + [""] * 12,
            ["", "سن", "جمع", "", "", "نقاط شهري", "", "", "نقاط روستايي", "", "",
             "غير ساکن", "", ""],
            ["", ""] + TRIPLE * 4]

    def line(label, pick):
        out = ["", label]
        for men, women in blocks:
            m, w = pick(men), pick(women)
            out += [float(m + w), float(m), float(w)]
        return out
    rows.append(line("تمامي سنين", sum))
    labels = ["كمتر از يك ساله"] + [f"{a} ساله" for a in range(1, 7)] + ["7 ساله و بيشتر"]
    for i, label in enumerate(labels):
        rows.append(line(label, lambda xs, i=i: xs[i]))
    return rows


SETTLEMENT_HEAD = ["كد", "نام", "كد", "نام", "كد", "نام", "كد", "نام", "شماره حوزه", "كد",
                   "نام", "كد ركورد", "ShahrTop", "SwDiv", "خانوار", "جمعيت", "مرد", "زن"]


def settlement_row(county, district, code, kind, p, m, w, top=None):
    return ["23", "تهران", county, "x", district, "y", code, "z", None, None, None,
            str(kind), top, None, 1, p, m, w]


def tehran_settlements(city=None):
    u = (sum(U_MEN) + sum(U_WOMEN), sum(U_MEN), sum(U_WOMEN))
    city = city or u
    r = (sum(R_MEN) + sum(R_WOMEN) + sum(S_MEN) + sum(S_WOMEN),
         sum(R_MEN) + sum(S_MEN), sum(R_WOMEN) + sum(S_WOMEN))
    county = (u[0] + r[0], u[1] + r[1], u[2] + r[2])
    rows = [["استان"], SETTLEMENT_HEAD,
            settlement_row("01", None, None, 2, *county),
            settlement_row("01", "02", None, 3, *u),
            settlement_row("01", "02", "1576", 5, *city),
            settlement_row("01", "02", "1601", 5, 100, 50, 50, top="1576"),
            settlement_row("01", "02", "1602", 5, city[0] - 100, city[1] - 50, city[2] - 50,
                           top="1576"),
            settlement_row("02", None, None, 2, 9, 4, 5)]
    return rows


class Split(unittest.TestCase):
    def test_a_block_of_table_1_is_read_under_its_heading(self):
        sheet = four_block_sheet([(U_MEN, U_WOMEN), (R_MEN, R_WOMEN), (S_MEN, S_WOMEN)])
        urban = ir.parse_ages(sheet, "t", block=1)
        self.assertEqual(urban["total"], (sum(U_MEN) + sum(U_WOMEN), sum(U_MEN), sum(U_WOMEN)))
        self.assertEqual(urban["men"][7], 30)
        unsettled = ir.parse_ages(sheet, "t", block=3)
        self.assertEqual(unsettled["total"], (3, 2, 1))
        # A block whose heading is not the one expected stops the run.
        sheet[1][5] = "جمع"
        with self.assertRaises(SystemExit):
            ir.parse_ages(sheet, "t", block=1)

    def test_settlement_rows_of_one_county(self):
        got = ir.read_settlements(tehran_settlements(), "01", "t")
        self.assertEqual(got["county"][0], sum(U_MEN + U_WOMEN + R_MEN + R_WOMEN + S_MEN + S_WOMEN))
        self.assertEqual(set(got["cities"]), {"1576"})
        self.assertEqual(got["regions"]["1576"], got["cities"]["1576"])
        self.assertEqual(set(got["districts"]), {"02"})

    def test_regions_that_do_not_make_their_city_stop(self):
        rows = tehran_settlements()
        rows[5][15] = 101
        rows[5][16] = 51
        with self.assertRaises(SystemExit):
            ir.read_settlements(rows, "01", "t")

    def test_tehran_the_city_is_the_urban_block(self):
        sheet = four_block_sheet([(U_MEN, U_WOMEN), (R_MEN, R_WOMEN), (S_MEN, S_WOMEN)])
        settlements = ir.read_settlements(tehran_settlements(), "01", "t")
        whole = ir.parse_ages(sheet, "t")
        made = ir.split_figures("Tehran", settlements, whole, sheet)
        self.assertEqual(made["part"], [sum(U_MEN) + sum(U_WOMEN), sum(U_MEN), sum(U_WOMEN)])
        self.assertEqual(made["rest"][0], sum(R_MEN + R_WOMEN + S_MEN + S_WOMEN))
        self.assertEqual(made["unsettled"], [3, 2, 1])
        rest = ir.table_from(made["ages"]["rest"])
        self.assertEqual(rest["men"][3], R_MEN[3] + S_MEN[3])
        # A city the urban block does not match to the person stops the run.
        u = (sum(U_MEN) + sum(U_WOMEN), sum(U_MEN), sum(U_WOMEN))
        wrong = ir.read_settlements(tehran_settlements(city=(u[0] + 1, u[1] + 1, u[2])), "01",
                                    "t")
        wrong["county"] = whole["total"]
        with self.assertRaises(SystemExit):
            ir.split_figures("Tehran", wrong, whole, sheet)
        # And so does a settlement table that counts the county otherwise.
        settlements["county"] = (1, 1, 0)
        with self.assertRaises(SystemExit):
            ir.split_figures("Tehran", settlements, whole, sheet)

    def figures(self):
        sheet = four_block_sheet([(U_MEN, U_WOMEN), (R_MEN, R_WOMEN), (S_MEN, S_WOMEN)])
        tehran = ir.split_figures("Tehran", ir.read_settlements(tehran_settlements(), "01", "t"),
                                  ir.parse_ages(sheet, "t"), sheet)
        isfahan = {"county": [1000, 510, 490], "part": [870, 440, 430], "rest": [130, 70, 60],
                   "other_cities": 13, "ages": None}
        mehdishahr = {"county": [47475, 23844, 23631], "part": [16694, 8377, 8317],
                      "rest": [30781, 15467, 15314], "other_cities": 2, "ages": None}
        return {"Tehran": tehran, "Isfahan": isfahan, "Mehdishahr": mehdishahr}

    def test_each_half_takes_its_own_count(self):
        a1 = [{"id": "T", "name": "Tehran"}, {"id": "I", "name": "Isfahan"},
              {"id": "S", "name": "Semnan"}]
        a2 = [{"id": "t1", "name": "Tehran", "parent": "T"},
              {"id": "t2", "name": "City of Tehran", "parent": "T"},
              {"id": "i1", "name": "Isfahan", "parent": "I"},
              {"id": "i2", "name": "Isfahan County", "parent": "I"},
              {"id": "s1", "name": "Mehdishahr", "parent": "S"},
              {"id": "s2", "name": "Shahmirzad", "parent": "S"}]
        rows = {r["shape_id"]: r for r in ir.split_records(a1, a2, self.figures())}
        self.assertEqual(sorted(rows), ["i1", "i2", "s1", "s2", "t1", "t2"])
        self.assertEqual(rows["t2"]["population"]["value"], sum(U_MEN) + sum(U_WOMEN))
        self.assertIn("median_age", rows["t2"])
        self.assertIsInstance(rows["t1"]["median_age"]["value"], float)
        self.assertEqual(rows["i1"]["population"]["value"], 870)
        self.assertEqual(rows["i2"]["sex_ratio"]["value"], round(100 * 70 / 60, 1))
        self.assertEqual(rows["i2"]["median_age"]["status"], "not_available")
        self.assertIn("13 other cities", rows["i2"]["median_age"]["note"])
        self.assertIn("13 other cities", rows["i2"]["population_note"])
        self.assertEqual(rows["s2"]["population"]["value"], 16694)
        self.assertEqual(rows["s1"]["population"]["value"], 30781)
        for r in rows.values():
            self.assertEqual(r["ethnicity"]["status"], "not_available")
            self.assertIn("by shahrestan only", r["ethnicity"]["note"])
            self.assertEqual(r["match_by"], "shape_id")
        # A half the map does not draw where it should stops the run.
        with self.assertRaises(SystemExit):
            ir.split_records(a1, a2[1:], self.figures())


def yearbook_pages(swapped=True, yazd_total=1138533):
    """Tables 3.17 and 3.18 as pypdf reads the English yearbook, two ostans only."""
    christian, zoroastrian = ("19823 10127 9696 25271 13880 11391 23109 12542 10567",
                              "109415 54751 54664 117704 63927 53777 130158 69075 61083")
    if not swapped:
        christian, zoroastrian = zoroastrian, christian
    p31 = "\n".join([
        "3.17. POPULATION BY SEX AND RELIGION", "Description",
        "     Total  .........  70495782 35866362 34629420 75149669 37905669 37244000 79926270 "
        "40498442 39427828",
        f"Christian ............  {christian}",
        f"Zoroastrian ..........  {zoroastrian}",
        "Source: Statistical Centre of Iran."])
    p32 = "\n".join([
        "3.18. POPULATION BY RELIGION AND OSTAN, 1395 CENSUS",
        "Ostan Total Muslim Christian Zoroastrian Jew Other Not stated",
        "    Total country ......  14406170 14311161 12179 45209 5098 10368 22155",
        "Tehran  ................  13267637 13179434 8579 43987 5067 9568 21002",
        f"Yazd  ..................  {yazd_total} 1131727 3600 1222 31 800 1153",
        "Source: Statistical Centre of Iran."])
    return [p31, p32]


class Religion(unittest.TestCase):
    def setUp(self):
        self.old = ir.PROVINCES
        ir.PROVINCES = {21: ("یزد", "Yazd"), 23: ("تهران", "Tehran")}

    def tearDown(self):
        ir.PROVINCES = self.old

    def test_the_swapped_headings_are_restored(self):
        table = ir.parse_religion(yearbook_pages())
        self.assertEqual(table["Yazd"]["Zoroastrianism"], 3600)
        self.assertEqual(table["Tehran"]["Christianity"], 43987)
        self.assertEqual(sum(table["Tehran"].values()), 13267637)

    def test_headings_no_longer_swapped_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ir.parse_religion(yearbook_pages(swapped=False))

    def test_a_row_that_does_not_add_up_stops(self):
        with self.assertRaises(SystemExit):
            ir.parse_religion(yearbook_pages(yazd_total=1138534))

    def test_golestan_without_bandar_e_gaz_takes_no_share(self):
        rows = [ir.record("IRN-CENSUS-P27", "Golestan", level="admin1", parent="IRN", country="IRN",
                          sources=[]),
                ir.record("IRN-CENSUS-P02-GAZ", "Mazandaran", level="admin1", parent="IRN", country="IRN",
                          sources=[]),
                ir.record("IRN-CENSUS-P21", "Yazd", level="admin1", parent="IRN", country="IRN",
                          sources=[])]
        religion = {"Yazd": {"Islam": 9, "Zoroastrianism": 1}}
        ages = {21: {"total": (10, 5, 5)}}
        county = ir.record("IRN-CENSUS-2101", "Yazd", level="admin2", parent="IRN",
                           country="IRN", sources=[])
        ir.add_religion(rows + [county], religion, ages)
        self.assertIn("province only", county["religion"]["note"])
        self.assertEqual(rows[0]["religion"]["status"], "not_available")
        self.assertEqual(rows[1]["religion"]["status"], "not_available")
        self.assertEqual(rows[2]["religion"][0], {"group": "Islam", "pct": 90.0, "count": 9})
        # A province whose religions are not the census's count stops the run.
        ages[21] = {"total": (11, 5, 6)}
        rows[2] = ir.record("IRN-CENSUS-P21", "Yazd", level="admin1", parent="IRN", country="IRN",
                            sources=[])
        with self.assertRaises(SystemExit):
            ir.add_religion(rows, religion, ages)


class Kept(unittest.TestCase):
    def test_a_kept_table_reads_back_the_same(self):
        table = ir.parse_ages(age_sheet(MEN, WOMEN), "t")
        back = ir.table_from(ir.table_json(table))
        for key in ("men", "women", "groups", "unstated", "total", "open"):
            self.assertEqual(back[key], table[key], key)
        ir.check_ages(back, "t")


class Median(unittest.TestCase):
    def test_median_is_interpolated_in_the_single_year(self):
        table = ir.parse_ages(age_sheet(MEN, WOMEN), "t")
        fields = ir.fields(table, None)
        ages = Counter({a: table["men"][a] + table["women"][a] for a in table["men"]})
        from scripts.fetch_census.redatam import median_age
        self.assertEqual(fields["median_age"]["value"], median_age(ages))
        self.assertEqual(fields["sex_ratio"]["value"], round(100 * sum(MEN) / sum(WOMEN), 1))


if __name__ == "__main__":
    unittest.main()
