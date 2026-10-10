import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import iraq_census as ic  # noqa: E402

DUMP = ROOT / "data" / "raw" / "iraq" / "aas2024_table11.txt"
GAZ = ROOT / "data" / "raw" / "iraq" / "ocha_admin3.txt"
PLACES = ROOT / "data" / "raw" / "iraq" / "ocha_places.txt"
GRID = ROOT / "data" / "raw" / "iraq" / "kontur_adm2.txt"


@unittest.skipUnless(DUMP.exists() and GAZ.exists(), "Iraq dumps not present")
class TheCensusTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ic.parse(DUMP.read_text(encoding="utf-8"))

    def test_every_governorate_adds_up_to_the_country(self):
        govs = self.table["governorates"]
        self.assertEqual(len(govs), 18)
        self.assertEqual(sum(govs.values()), ic.NATIONAL)
        self.assertEqual(self.table["grand"], ic.NATIONAL)

    def test_every_governorate_is_its_districts(self):
        for code, value in self.table["governorates"].items():
            self.assertEqual(self.table["sums"][code], value, code)

    def test_every_sub_district_is_read(self):
        # Rows whose code the layout lost are recovered from what their
        # district's total leaves over; only Wasit's Kut and Maysan's Ali
        # al-Gharbi, whose rows trade 867 people, do not add up.
        self.assertEqual(sorted(set(self.table["districts"]) - self.table["whole"]),
                         ["2601", "3402"])

    def test_a_total_printed_without_the_word_is_taken_only_when_it_is_the_sum(self):
        # Panjwin's total line carries no "Total".
        self.assertEqual(self.table["districts"]["1306"], 52_251)


@unittest.skipUnless(DUMP.exists() and GAZ.exists(), "Iraq dumps not present")
class TheCrosswalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        table = ic.parse(DUMP.read_text(encoding="utf-8"))
        cls.table = table
        places = ic.read_places(PLACES.read_text(encoding="utf-8")) if PLACES.exists() else []
        cls.result = ic.crosswalk(table, ic.read_gazetteer(GAZ.read_text(encoding="utf-8")),
                                  places)
        cls.placed = {n: key for n, _name, _d, _v, key, _how in cls.result["placed"]}
        grid = ic.read_grid(GRID.read_text(encoding="utf-8")) if GRID.exists() else {}
        cls.grid_log = ic.grid_check(cls.result, grid)
        cls.mapped = cls.result["districts"]
        cls.govs = cls.result["governorates"]

    def test_a_written_governorate_s_districts_add_up_to_it(self):
        districts = [e for e in self.mapped.values()
                     if e["governorate"] == "Al-Muthanna" and e["value"] is not None]
        self.assertEqual(len(districts), 4)
        self.assertEqual(sum(e["value"] for e in districts),
                         self.table["governorates"]["32"])

    def test_a_sub_district_moved_between_districts_follows_its_ground(self):
        # The census files Altun Kupri under Kirkuk district; the boundary
        # file draws it in Dibis. Its people go to Dibis.
        dibis = self.mapped["Kirkuk/Dibis"]
        self.assertIsNotNone(dibis["value"])
        self.assertTrue(any("Alton" in name for name, _v in dibis["parts"]))

    def test_a_namesake_across_a_governorate_line_is_not_taken_alone(self):
        # Ninewa's Faeda (186,456) is not OCHA's 34 km2 Fayde in Duhok.
        tilkaef = self.mapped["Ninewa/Tilkaef"]
        self.assertEqual(tilkaef["value"], self.table["districts"]["1204"])
        self.assertNotIn("Faeda", str(self.govs["Duhok"].get("note")))

    def test_ground_counted_under_another_governorate_moves_with_it(self):
        # Duhok counts Aqra, Shekhan and Bardarash; the map draws them in
        # Ninewa, and Makhmour, counted under Ninewa, in Erbil.
        census = {ic.GOVERNORATE[g]: v for g, v in self.table["governorates"].items()}
        for gov in ("Duhok", "Ninewa", "Erbil"):
            self.assertNotEqual(self.govs[gov]["value"], census[gov], gov)
        self.assertEqual(sum(e["value"] for e in self.govs.values()), ic.NATIONAL)

    def test_a_centre_is_not_carried_by_its_one_sibling(self):
        # Saed Sadiq's Serjook is OCHA's Saruchik in Sharbazher; Sayid Sadiq
        # town is in Halabja. The district is split between the two, each
        # taking its own sub-district's figure.
        self.assertEqual(self.placed["13041"], ("Al-Sulaymaniyah", "Halabcha"))
        self.assertEqual(self.placed["13042"], ("Al-Sulaymaniyah", "Sharbazher"))

    @unittest.skipUnless(PLACES.exists(), "OCHA's places not present")
    def test_a_village_does_not_place_a_district_named_like_it(self):
        # OCHA's only Haji Awa is a village by Sulaymaniyah city; Hajiawa
        # district goes where its article puts it, not there.
        self.assertNotEqual(self.placed.get("13181"),
                            ("Al-Sulaymaniyah", "Al-Sulaymaniyah"))

    @unittest.skipUnless(PLACES.exists(), "OCHA's places not present")
    def test_a_built_up_town_places_the_district_named_for_it(self):
        self.assertEqual(self.placed["25051"], ("Kerbala", "Kerbela"))
        kerbala = [e["value"] for e in self.mapped.values() if e["governorate"] == "Kerbala"]
        self.assertEqual(sum(kerbala), self.table["governorates"]["25"])

    @unittest.skipUnless(GRID.exists(), "Kontur's grid not present")
    def test_a_shape_that_is_not_the_census_s_ground_is_refused(self):
        # The boundary file draws Amarah city inside the shape it names
        # Al-Kahla; the census's Al-Umarra is 7.9 times the grid in the
        # shape named Al-Amara.
        amara = self.mapped["Maysan/Al-Amara"]
        self.assertIsNone(amara["value"])
        self.assertIn("grid", amara["why"])
        self.assertIsNotNone(self.mapped["Maysan/Ali Al-Gharbi"]["value"])

    @unittest.skipUnless(GRID.exists(), "Kontur's grid not present")
    def test_the_grid_is_not_used_where_it_is_wrong_for_the_governorate(self):
        self.assertTrue(any(line.startswith("Duhok:") for line in self.grid_log))
        self.assertIsNotNone(self.mapped["Duhok/Duhok"]["value"])

    def test_a_new_district_is_placed_where_its_article_puts_it(self):
        # Al-Obour is Al-Rummaneh district, raised from OCHA's Al-Rummaneh
        # sub-district of Al-Kaim; Kutha's centre was Al-Mashroo, OCHA's,
        # in Al-Mahaweel; Hajiawa was a sub-district of Ranya.
        self.assertEqual(self.placed["22121"], ("Al-Anbar", "Al-Kaim"))
        self.assertEqual(self.placed["24061"], ("Babil", "Al-Mahaweel"))
        self.assertEqual(self.placed["13181"], ("Al-Sulaymaniyah", "Rania"))
        anbar = [e["value"] for e in self.mapped.values() if e["governorate"] == "Al-Anbar"]
        self.assertNotIn(None, anbar)
        self.assertEqual(sum(anbar), self.table["governorates"]["22"])

    def test_every_seat_names_a_district_of_the_map_s(self):
        districts = {row["adm2_name"] for row in ic.read_gazetteer(GAZ.read_text(encoding="utf-8"))}
        for code, (district, why) in ic.SEATS.items():
            self.assertIn(district, districts, code)
            self.assertTrue(why.startswith("ar.wikipedia"), code)

    def test_a_district_that_cannot_be_placed_leaves_a_reason(self):
        for entry in self.mapped.values():
            if entry["value"] is None:
                self.assertTrue(entry["why"])


class Names(unittest.TestCase):
    def test_every_governorate_answers_to_the_map_s_spelling(self):
        # The map's first level: Dohuk, Ninawa, Al-Sulaimaniyah, An-Najaf,
        # Dhi Qar, Karbala, Wasit, Al-Qadisiyah.
        spelt = {a for names in ic.MAP_NAMES.values() for a in names}
        for name in ("Dohuk", "Ninawa", "Al-Sulaimaniyah", "An-Najaf", "Dhi Qar",
                     "Karbala", "Wasit", "Al-Qadisiyah"):
            self.assertIn(name, spelt)

    def test_reversed_arabic_is_read_back_in_order(self):
        self.assertEqual(ic.arabic("كوهد"), "دهوك")

    def test_a_second_name_in_brackets_is_a_name_too(self):
        self.assertEqual(ic.variants("Akd (Al-Daggara"), ["Akd", "Al-Daggara"])

    def test_kurdish_vowels_fold_to_the_arabic_spelling(self):
        self.assertEqual(ic.ar_loose("مهيدان"), ic.ar_loose("ميدان"))

    def test_short_romanisations_must_be_the_same(self):
        self.assertFalse(ic.alike(ic.en_key("Sowran"), ic.en_key("Shwan")))

    def test_the_lam_alef_ligature_is_folded(self):
        self.assertEqual(ic.ar_key("كربالء"), ic.ar_key("كربلاء"))


# Duhok's block of Table 10/2 as the PDF lays it out: the total, women and men
# whole, the rural and urban figures split mid-number, the governorate's label
# printed among the rows.
DUHOK = """164,384 80,355 84,029 37 ,010 18 ,145 18, 865 127 ,374 62,210 65,164 00-04
179,963 87,726 92,237 40 ,028 19 ,674 20, 354 139 ,935 68,052 71,883 05-09
190,072 93,543 96,529 42 ,149 20 ,829 21, 320 147 ,923 72,714 75,209 10-14
169,893 83,459 86,434 36 ,986 18 ,154 18, 832 132 ,907 65,305 67,602 15-19
163,269 80,983 82,286 35 ,567 17 ,378 18, 189 127 ,702 63,605 64,097 20-24
136,437 67,471 68,966 27 ,524 13 ,389 14, 135 108 ,913 54,082 54,831 25-29
121,465 60,360 61,105 24 ,138 11 ,971 12, 167 97 ,327 48,389 48,938 30-34
117,285 57,701 59,584 21 ,517 10 ,661 10, 856 95 ,768 47,040 48,728 35-39
98,876 49,361 49,515 16 ,925 8 ,592 8, 333 81, 951 40,769 41,182 40-44
Duhok-11 11-كوهد
73,132 36,814 36,318 12 ,368 6 ,440 5, 928 60, 764 30,374 30,390 45-49
62,410 30,572 31,838 10 ,951 5 ,354 5, 597 51, 459 25,218 26,241 50-54
39,973 18,731 21,242 6, 852 3 ,274 3, 578 33, 121 15,457 17,664 55-59
24,676 14,765 9,911 4, 023 2, 596 1, 427 20, 653 12,169 8,484 60-64
22,272 12,126 10,146 3, 581 1 ,969 1, 612 18, 691 10,157 8,534 65-69
19,531 10,438 9,093 3, 626 1, 909 1, 717 15, 905 8,529 7,376 70-74
7,987 4,458 3,529 1, 446 8 39 6 07 6,5 41 3,619 2,922 75-79
4,064 2,298 1,766 75 5 4 46 3 09 3,3 09 1,852 1,457 80-84
4,182 2,746 1,436 87 9 5 57 3 22 3,3 03 2,189 1,114 85+ رثكأف
Total 1,599,871 793,907 805,964 32 6,325 16 2,177 164 ,148 1,2 73,546 631,730 641,816 عومجملا
"""


class AgesAndSexes(unittest.TestCase):
    TABLE = {"governorates": {"11": 1_599_871}}

    def test_a_row_s_women_and_men_are_its_second_and_third_figures(self):
        self.assertEqual(ic.sexes_of("452,981 225,058 227,923 14 8 6 452,967 225,050 "
                                     "227,917 D.C of Duhok-11011-كوهد ق.م"), (225_058, 227_923))

    def test_a_row_whose_sexes_do_not_make_it_is_not_read_for_sex(self):
        self.assertIsNone(ic.sexes_of("84,319 416,665 42,654 17 ,435 30-34"))

    def test_a_governorate_s_age_groups_are_read_and_checked(self):
        ages = ic.governorate_ages(DUHOK, self.TABLE)
        self.assertEqual(list(ages), ["11"])
        groups = ages["11"]["groups"]
        self.assertEqual(groups[0], (0, 4, 164_384))
        self.assertEqual(groups[-1], (85, None, 4_182))
        self.assertEqual(sum(n for _a, _b, n in groups), 1_599_871)

    def test_a_block_that_does_not_make_its_total_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ic.governorate_ages(DUHOK.replace("164,384 80,355 84,029", "164,385 80,356 84,029"),
                                self.TABLE)

    def test_a_governorate_drawn_on_the_census_s_ground_gets_a_median(self):
        ages = ic.governorate_ages(DUHOK, self.TABLE)
        fields = ic.age_fields("Duhok", "11", {"value": 1_599_871}, ages)
        self.assertAlmostEqual(fields["median_age"]["value"], 22.9, delta=1.5)

    def test_one_whose_ground_moved_says_why_it_has_none(self):
        ages = ic.governorate_ages(DUHOK, self.TABLE)
        fields = ic.age_fields("Duhok", "11", {"value": 1_400_000, "note": "moved"}, ages)
        self.assertEqual(fields["median_age"]["status"], "not_available")

    def test_sex_ratio_is_written_only_beside_the_same_count(self):
        self.assertEqual(ic.sex_fields({"value": 10, "sexes": (5, 5)}, "district")
                         ["sex_ratio"]["value"], 100.0)
        self.assertEqual(ic.sex_fields({"value": 11, "sexes": (5, 5)}, "district"), {})


AGES = ROOT / "data" / "raw" / "iraq" / "aas2024_table10.txt"


@unittest.skipUnless(DUMP.exists() and GAZ.exists() and AGES.exists(), "Iraq dumps not present")
class EveryEmptyFieldSaysWhy(unittest.TestCase):
    """A district's empty median age or sex ratio carries the reason, not a bare gap."""

    @classmethod
    def setUpClass(cls):
        cls.rows = ic.build(DUMP.read_text(encoding="utf-8"), GAZ.read_text(encoding="utf-8"),
                            PLACES.read_text(encoding="utf-8") if PLACES.exists() else "",
                            AGES.read_text(encoding="utf-8"))

    def test_every_district_says_why_it_has_no_median_age(self):
        districts = [r for r in self.rows if r["level"] == "admin2"]
        self.assertTrue(districts)
        for row in districts:
            self.assertEqual(row["median_age"]["status"], "not_available", row["name"])
            self.assertIn("Table 10/2", row["median_age"]["note"], row["name"])

    def test_a_district_with_no_count_says_why_it_has_no_sex_ratio(self):
        empty = [r for r in self.rows if r["level"] == "admin2"
                 and "value" not in r["population"]]
        self.assertTrue(empty)
        for row in empty:
            self.assertEqual(row["sex_ratio"]["note"], row["population"]["note"], row["name"])

    def test_no_empty_field_is_left_without_a_note(self):
        for row in self.rows:
            for field in ("population", "median_age", "sex_ratio", "religion"):
                value = row[field]
                if isinstance(value, dict) and value.get("status"):
                    self.assertTrue(value.get("note"), f"{row['name']} {field}")


class Crossings(unittest.TestCase):
    """A district the map files under another governorate's polygon says so."""

    MAPPED = {
        "Kerbala/Al-Hindiya": {"governorate": "Kerbala", "district": "Al-Hindiya",
                               "value": 352503},
        "Kerbala/Kerbela": {"governorate": "Kerbala", "district": "Kerbela", "value": 1368059},
        "Baghdad/Al-Mahmoudiya": {"governorate": "Baghdad", "district": "Al-Mahmoudiya",
                                  "value": None},
    }
    DRAWN = {"Al-Hindiya": "Babil", "Kerbela": "Karbala", "Al-Mahmoudiya": "Babil"}

    def test_a_district_filed_elsewhere_and_both_governorates_say_so(self):
        district, governorate = ic.crossings(self.MAPPED, self.DRAWN)
        self.assertEqual(sorted(district), ["Baghdad/Al-Mahmoudiya", "Kerbala/Al-Hindiya"])
        self.assertIn("counts it in Kerbala governorate", district["Kerbala/Al-Hindiya"])
        self.assertIn("labelled Babil", district["Kerbala/Al-Hindiya"])
        self.assertIn("Al-Hindiya (352,503 people, counted in Kerbala)", governorate["Babil"])
        self.assertIn("Al-Mahmoudiya (counted in Baghdad)", governorate["Babil"])
        self.assertIn("not in this figure", governorate["Babil"])
        self.assertIn("Al-Hindiya (352,503 people, filed under Babil) in Kerbala",
                      governorate["Kerbala"])
        # The map's spelling of a governorate is the census's under another name.
        self.assertNotIn("Kerbala/Kerbela", district)

    def test_no_drawn_parent_no_note(self):
        district, governorate = ic.crossings(self.MAPPED, {})
        self.assertEqual((district, governorate), ({}, {}))


@unittest.skipUnless(DUMP.exists() and GAZ.exists(), "Iraq dumps not present")
class SexesInTheTable(unittest.TestCase):
    def test_every_unit_of_the_table_has_women_and_men_making_its_count(self):
        table = ic.parse(DUMP.read_text(encoding="utf-8"))
        sexes = table["sexes"]
        for code, (_en, _ar, value) in table["nahiyas"].items():
            self.assertEqual(sum(sexes[code]), value, code)
        for code, value in table["governorates"].items():
            self.assertEqual(sum(sexes[code]), value, code)
        women = sum(sexes[g][0] for g in table["governorates"])
        men = sum(sexes[g][1] for g in table["governorates"])
        # Table 2/2's national figures.
        self.assertEqual((women, men), (22_957_189, 23_161_604))


if __name__ == "__main__":
    unittest.main()
