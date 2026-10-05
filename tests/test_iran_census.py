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
        afghan = next(s for s in by_shape["G"]["ethnicity"] if s["group"] == "Afghan")
        self.assertEqual(afghan["count"], 4)
        self.assertEqual(by_shape["g2"]["ethnicity_basis"], "citizenship")

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
