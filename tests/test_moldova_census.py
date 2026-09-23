"""Moldova's 2024 census annex, tables 5.29 (religion) and 5.13 (mother tongue).

The rows below are the workbook's own, as the runner's probe printed them on
23 September 2026, cut to the header, the national total, one region and the
units each test is about.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import moldova_census as m  # noqa: E402

N = None

RELIGION = [
    ("Cuprins",),
    (N,),
    ("Recensământul Populației și Locuințelor 2024",),
    ("5.29 Populația după afilierea religioasă declarată, pe raioane",),
    (N,) * 17 + ("persoane",),
    ("Cod statistic CUATM", "Regiuni de dezvoltare, municipii, raioane", "Total",
     "Religia declarată", N, N, N, N, N, N, N, N, N, N, N, N, N, "Nu au declarat religia"),
    (N, N, N, "Ortodoxă", "Baptistă", "Martorii lui Iehova", "Penticostală", "Adventistă",
     "Creștină după Evanghelie", "Staroveri (Ortodoxă de rit vechi)", "Islam", "Catolică",
     "Alte religii", "Liber cugetător", "Agnostic", "Ateu", "Fără religie", N),
    ("A", "B", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
    (N, "Total", 2409207, 2271105, 26226, 16505, 12606, 6982, 6364, 4053, 3138, 2586,
     4720, 440, 2117, 14211, 20051, 18103),
    (N, "Nord", 608651, 565258, 6988, 9442, 7578, 2068, 2057, 3519, 232, 783, 793, 84,
     145, 1272, 4177, 4255),
    ("0300000", "Mun. Bălţi", 94546, 86534, 1747, 1062, 500, 166, 284, 141, 68, 375,
     275, 16, 90, 795, 1055, 1438),
    ("1400000", "Briceni", 46894, 37731, 549, 3603, 1979, 303, 175, 3, 14, 32, 63, 4,
     "-", 50, 1495, 893),
    (N,),
    ("”-” = magnitudine zero",),
]

LANGUAGE = [
    ("5.13 Populația după limba maternă declarată, pe raioane",),
    (N,) * 13 + ("persoane",),
    ("Cod statistic", "Regiuni de dezvoltare, municipii, raioane", "Total",
     "Limba maternă declarată", N, N, N, N, N, N, N, N, N),
    (N, N, N, "Moldovenească sau română (total)³", N, N, "Ucraineană", "Rusă",
     "Găgăuză", "Bulgară", "Romani (Țigănească)", "Altă limbă", "Nu au declarat limba maternă"),
    (N, N, N, "Total", "Moldovenească", "Română"),
    ("A", "B", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11),
    (N, "Total", 2409207, 1925695, 1159857, 765838, 71878, 280050, 87407, 28839, 7640,
     6116, 1582),
    ("0300000", "Mun. Bălţi", 94546, 54647, 34584, 20063, 4285, 35132, 66, 41, 113,
     171, 91),
    ("1400000", "Briceni", 46894, 35163, 29926, 5237, 7339, 4091, 25, 8, 201, 45, 22),
]


class Religion(unittest.TestCase):
    def setUp(self):
        self.units = {u["name"]: u for u in m.units("religion", RELIGION)}

    def test_only_units_with_a_code_are_read(self):
        # Not the national total, not the Nord region.
        self.assertEqual(set(self.units), {"Mun. Bălţi", "Briceni"})

    def test_briceni(self):
        briceni = self.units["Briceni"]
        self.assertEqual(briceni["total"], 46894)
        self.assertEqual(briceni["groups"]["Orthodox"], 37731)
        self.assertEqual(briceni["groups"]["Jehovah's Witnesses"], 3603)
        # The bureau's dash is a zero.
        self.assertEqual(briceni["groups"]["Agnosticism"], 0)
        shown = {g["group"]: g["pct"] for g in m.shares(briceni["groups"],
                                                        total=briceni["total"])}
        # The release's own sentence: Orthodox "80,5% în raionul Briceni".
        self.assertEqual(shown["Orthodox"], 80.5)

    def test_the_column_under_the_spanning_header_is_named_from_above(self):
        # "Nu au declarat religia" has no cell in the categories' row.
        self.assertEqual(self.units["Mun. Bălţi"]["groups"]["Not declared"], 1438)

    def test_a_row_that_does_not_add_up_stops_the_run(self):
        broken = list(RELIGION)
        broken[11] = ("1400000", "Briceni", 46895) + RELIGION[11][3:]
        with self.assertRaises(SystemExit):
            m.units("religion", broken)

    def test_an_unknown_category_stops_the_run(self):
        renamed = list(RELIGION)
        renamed[6] = RELIGION[6][:3] + ("Budistă",) + RELIGION[6][4:]
        with self.assertRaises(SystemExit) as caught:
            m.units("religion", renamed)
        self.assertIn("Budistă", str(caught.exception))

    def test_the_workbook_s_empty_first_column(self):
        # The annex leaves column A empty, and the code sits in column B.
        shifted = [(N,) + row for row in RELIGION]
        units = {u["name"]: u for u in m.units("religion", shifted)}
        self.assertEqual(units["Briceni"]["groups"]["Orthodox"], 37731)

    def test_every_name_is_already_on_the_map(self):
        import canonical_groups
        # "Not declared" stands alone on purpose: non-response is nobody's kind.
        for name in set(m.LABELS["religion"].values()) - {"Not declared"}:
            self.assertGreater(len(canonical_groups.ancestry("religion", name)), 1, name)


class MotherTongue(unittest.TestCase):
    def setUp(self):
        self.units = {u["name"]: u for u in m.units("language", LANGUAGE)}

    def test_the_moldovan_or_romanian_subtotal_is_not_a_group(self):
        balti = self.units["Mun. Bălţi"]["groups"]
        self.assertEqual(balti["Moldovan"], 34584)
        self.assertEqual(balti["Romanian"], 20063)
        self.assertNotIn("Total", balti)
        self.assertEqual(sum(balti.values()), 94546)

    def test_balti_matches_the_article_s_chart(self):
        # The English article's pie chart gives Russian 37.2%: it was this.
        balti = self.units["Mun. Bălţi"]
        shown = {g["group"]: g["pct"] for g in m.shares(balti["groups"], total=balti["total"])}
        self.assertEqual(shown["Russian"], 37.2)


class Records(unittest.TestCase):
    class Book:
        def __init__(self, sheets):
            self.sheets = sheets

        def __getitem__(self, name):
            rows = self.sheets[name]

            class Sheet:
                def iter_rows(self, values_only=True):
                    return iter(rows)
            return Sheet()

    def records(self):
        saved = m.UNITS
        m.UNITS = 2
        try:
            book = self.Book({"5.29": RELIGION, "5.13": LANGUAGE})
            drawn = {level: {"balti": "B1", "briceni": "B2"} for level in ("admin1", "admin2")}
            return m.build(book, drawn)
        finally:
            m.UNITS = saved

    def test_each_unit_is_bound_to_its_shape_at_both_levels(self):
        got = self.records()
        self.assertEqual(len(got), 4)
        self.assertEqual({(r["level"], r["shape_id"]) for r in got},
                         {("admin1", "B1"), ("admin2", "B1"), ("admin1", "B2"), ("admin2", "B2")})
        self.assertTrue(all(r["match_by"] == "shape_id" for r in got))

    def test_both_fields_are_dated_2024(self):
        for r in self.records():
            self.assertEqual(r["religion_year"], 2024)
            self.assertEqual(r["language_year"], 2024)

    def test_no_population_is_written(self):
        # The annex's totals check the groups; the map's population comes
        # from elsewhere and a gap here never replaces it.
        for r in self.records():
            self.assertEqual(r["population"]["status"], "not_available")

    def test_a_unit_the_map_does_not_draw_stops_the_run(self):
        saved = m.UNITS
        m.UNITS = 2
        try:
            with self.assertRaises(SystemExit):
                m.build(self.Book({"5.29": RELIGION, "5.13": LANGUAGE}),
                        {"admin1": {"balti": "B1"}, "admin2": {"balti": "B1"}})
        finally:
            m.UNITS = saved

    def test_the_map_is_given_the_name_not_the_workbook_s_label(self):
        # A bound row names its shape; "Mun. Chişinău" was on the map.
        self.assertEqual(m.display("Mun. Chişinău"), "Chișinău")
        self.assertEqual(m.display("Mun. Bălţi"), "Bălți")
        self.assertEqual(m.display("UTA Găgăuzia"), "Gagauzia")
        self.assertEqual(m.display("Ştefan Vodă"), "Ștefan Vodă")
        self.assertEqual(m.display("Briceni"), "Briceni")
        names = {r["name"] for r in self.records()}
        self.assertEqual(names, {"Bălți", "Briceni"})

    def test_the_workbook_s_names_fold_to_the_boundary_file_s(self):
        self.assertEqual(m.key("Mun. Bălţi"), m.key("Balti"))
        self.assertEqual(m.key("UTA Găgăuzia"), m.key("Gagauzia"))
        self.assertEqual(m.key("Ştefan Vodă"), m.key("Stefan Voda"))
        self.assertEqual(m.key("Rîşcani"), m.key("RIscani"))


if __name__ == "__main__":
    unittest.main()
