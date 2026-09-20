"""Laos: how a village finds its province and district, how the percentages
are turned back into people, and what refuses."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import laos as L  # noqa: E402


def village(province, district, population, ethnicity=None, religion=None,
            sex_ratio=100.0, code="1"):
    """One row of the workbook, with every percentage defaulting to zero."""
    ethnic = {label: 0.0 for label in L.ETHNICITY.values()}
    ethnic.update(ethnicity or {})
    faith = {label: 0.0 for label in L.RELIGION.values()}
    faith.update(religion or {})
    return {"village": code, "village_name": f"B. {code}",
            "district_code": "0", "district_label": district,
            "province_code": "0", "province_label": province,
            "population": float(population), "sex_ratio": sex_ratio,
            "ethnicity": ethnic, "religion": faith}


class Provinces(unittest.TestCase):
    def test_the_eighteen_are_the_boundary_file_s_own_names(self):
        self.assertEqual(len(L.PROVINCES), 18)
        self.assertEqual(len({L.fold(name) for name in L.PROVINCES}), 18)
        self.assertEqual(set(L.DISTRICTS), set(L.PROVINCES))
        self.assertEqual(sum(len(d) for d in L.DISTRICTS.values()), 148)

    def test_the_two_vientianes_are_never_confused(self):
        self.assertEqual(L.province_of("Vientiane"), "Vientiane")
        self.assertEqual(L.province_of("Vientiane Province"), "Vientiane")
        self.assertEqual(L.province_of("Vientiane Capital"), "Vientiane Capital")
        self.assertEqual(L.province_of("VIENTIANE CAPITAL"), "Vientiane Capital")
        self.assertEqual(L.province_of("Vientiane Prefecture"), "Vientiane Capital")
        # A label that begins with the word and is neither of the two is
        # refused outright rather than handed to whichever is nearer.
        self.assertIsNone(L.province_of("Vientiane Something Else"))

    def test_romanisations_reach_the_boundary_file_s_spelling(self):
        for label, want in (("Xaignabouly", "Xaignabouli"), ("Xayabury", "Xaignabouli"),
                            ("Sayaboury", "Xaignabouli"), ("Saravane", "Salavan"),
                            ("Sekong", "Xekong"), ("Huaphanh", "Houaphan"),
                            ("Hua Phan", "Houaphan"), ("Borikhamxay", "Bolikhamsai"),
                            ("Luangnamtha", "Luang Namtha"),
                            ("Luangprabang", "Luang Prabang"),
                            ("Champasack", "Champasak"), ("Khammuane", "Khammouane"),
                            ("Xiengkhuang", "Xiangkhouang"),
                            ("Xaysomboun", "Xaisomboun")):
            self.assertEqual(L.province_of(label), want, label)

    def test_a_province_no_fold_reaches_is_none(self):
        self.assertIsNone(L.province_of("Chiang Mai"))
        self.assertIsNone(L.province_of(""))


class Districts(unittest.TestCase):
    def test_the_generic_word_is_not_part_of_the_name(self):
        self.assertEqual(L.district_of("Vientiane Capital", "Sikhottabong District"),
                         "Sikhottabong")
        self.assertEqual(L.district_of("Luang Prabang", "Xieng Ngeun  District"),
                         "Xieng Ngeun")

    def test_the_seven_that_romanise_differently(self):
        for province, label, want in (
                ("Houaphan", "Huim District", "Hiem"),
                ("Houaphan", "Kuane District", "Kuan"),
                ("Houaphan", "Sone District", "Xon"),
                ("Khammouane", "Nakai District", "Nakay"),
                ("Phongsaly", "Boontai District", "Boontay"),
                ("Xiangkhouang", "Morkmay District", "Mork"),
                ("Xiangkhouang", "Phoukoud District", "Phookood")):
            self.assertEqual(L.district_of(province, label), want, label)

    def test_a_name_is_only_looked_for_inside_its_own_province(self):
        # Xaysetha is a district of Attapeu and of Vientiane Capital, and
        # Phonthong of Champasak and of Luang Prabang. Each is found in its
        # own province and nowhere else.
        self.assertEqual(L.district_of("Attapeu", "Xaysetha"), "Xaysetha")
        self.assertEqual(L.district_of("Vientiane Capital", "Xaysetha"), "Xaysetha")
        self.assertIsNone(L.district_of("Bokeo", "Xaysetha"))
        self.assertIsNone(L.district_of("Salavan", "Phonthong"))
        self.assertIsNone(L.district_of("Vientiane Capital", "Nowhere"))


class Adding(unittest.TestCase):
    def test_a_percentage_becomes_people_and_the_people_are_summed(self):
        rows = [village("Bokeo", "Meung District", 100, {"Lao": 50.0, "Hmong": 50.0}),
                village("Bokeo", "Meung District", 900, {"Lao": 10.0, "Hmong": 20.0})]
        provinces, districts, unplaced = L.gather(rows)
        self.assertEqual(unplaced, [])
        unit = provinces["Bokeo"]
        self.assertEqual(unit["population"], 1000)
        self.assertAlmostEqual(unit["ethnicity"]["Lao"], 50 + 90)
        self.assertAlmostEqual(unit["ethnicity"]["Hmong"], 50 + 180)
        self.assertEqual(districts[("Bokeo", "Meung")]["population"], 1000)

    def test_the_sexes_are_summed_and_not_the_ratios(self):
        # 100 people at 150 men per 100 women is 40 women; 100 at 50 is 67.
        rows = [village("Bokeo", "Meung", 100, sex_ratio=150.0),
                village("Bokeo", "Meung", 100, sex_ratio=50.0)]
        unit = L.gather(rows)[0]["Bokeo"]
        self.assertAlmostEqual(unit["female"], 100 * 100 / 250 + 100 * 100 / 150, 6)
        self.assertAlmostEqual(unit["female"] + unit["male"], 200.0, 6)

    def test_an_unplaceable_district_keeps_its_people_in_the_province(self):
        rows = [village("Bokeo", "Somewhere District", 400, {"Lao": 100.0})]
        provinces, districts, unplaced = L.gather(rows)
        self.assertEqual(provinces["Bokeo"]["population"], 400)
        self.assertEqual(districts, {})
        self.assertEqual(unplaced, ["Bokeo / Somewhere District (400 people)"])

    def test_an_unknown_province_refuses_and_names_every_one_of_them(self):
        rows = [village("Bokeo", "Meung", 10), village("Atlantis", "X", 10),
                village("Narnia", "Y", 10), village("Atlantis", "Z", 10)]
        with self.assertRaises(SystemExit) as caught:
            L.gather(rows)
        message = str(caught.exception)
        self.assertIn("'Atlantis' (2 villages)", message)
        self.assertIn("'Narnia' (1 villages)", message)


class Composition(unittest.TestCase):
    def test_the_residual_is_what_the_named_categories_leave(self):
        rows = L.composition({"Lao": 600.0, "Hmong": 300.0}, 1000.0,
                             L.ETHNIC_RESIDUAL)
        self.assertEqual([(r["group"], r["pct"], r["count"]) for r in rows],
                         [("Lao", 60.0, 600), ("Hmong", 30.0, 300),
                          (L.ETHNIC_RESIDUAL, 10.0, 100)])

    def test_the_shares_add_to_exactly_a_hundred(self):
        for counts in ({"Lao": 1.0, "Hmong": 1.0, "Mien": 1.0},
                       {"Lao": 333.0, "Hmong": 333.0, "Mien": 334.0},
                       {"Lao": 999.0, "Hmong": 1.0}):
            total = sum(counts.values())
            rows = L.composition(counts, total, L.ETHNIC_RESIDUAL)
            self.assertEqual(round(sum(r["pct"] for r in rows), 6), 100.0, counts)

    def test_a_category_under_a_twentieth_of_a_percent_joins_the_residual(self):
        rows = L.composition({"Lao": 99_990.0, "Mien": 10.0}, 100_000.0,
                             L.ETHNIC_RESIDUAL)
        self.assertEqual([r["group"] for r in rows], ["Lao"])
        self.assertEqual(rows[0]["pct"], 100.0)

    def test_an_empty_unit_has_no_composition(self):
        self.assertEqual(L.composition({"Lao": 0.0}, 0.0, L.ETHNIC_RESIDUAL), [])


class Checks(unittest.TestCase):
    def country(self, lao=43.7, tai=18.3, khmu=23.6, hmong=9.7, tibeto=2.9,
                buddhist=64.7, christian=1.7, sex_ratio=100.53):
        """One village per province, together reproducing the national figures."""
        people = L.NATIONAL_POPULATION / len(L.PROVINCES)
        rows = []
        for n, (province, districts) in enumerate(L.DISTRICTS.items()):
            rows.append(village(province, districts[0], people,
                                {"Lao": lao, "Tai-Thay": tai, "Khmuic": khmu,
                                 "Hmong": hmong, "Tibeto-Burman": tibeto},
                                {"Buddhism": buddhist, "Christianity": christian},
                                sex_ratio=sex_ratio, code=str(n)))
        return rows

    def test_a_country_that_reproduces_the_volume_passes(self):
        provinces, districts, _ = L.gather(self.country())
        L.check(provinces, districts)               # does not raise

    def test_a_family_that_misses_the_volume_refuses(self):
        provinces, districts, _ = L.gather(self.country(hmong=4.0))
        with self.assertRaises(SystemExit) as caught:
            L.check(provinces, districts)
        self.assertIn("Hmong-Mien", str(caught.exception))

    def test_a_religion_that_misses_the_volume_refuses(self):
        provinces, districts, _ = L.gather(self.country(buddhist=40.0))
        with self.assertRaises(SystemExit) as caught:
            L.check(provinces, districts)
        self.assertIn("Buddhism", str(caught.exception))

    def test_a_sex_ratio_read_the_wrong_way_up_refuses(self):
        # 99.47 men per 100 women is the same figure inverted, and it must not
        # pass for the published 994.7 females per 1,000 males.
        provinces, districts, _ = L.gather(self.country(sex_ratio=99.47))
        with self.assertRaises(SystemExit) as caught:
            L.check(provinces, districts)
        self.assertIn("females per 1,000 males", str(caught.exception))

    def test_a_missing_province_refuses(self):
        rows = [r for r in self.country() if r["province_label"] != "Xekong"]
        provinces, districts, _ = L.gather(rows)
        with self.assertRaises(SystemExit) as caught:
            L.check(provinces, districts)
        self.assertIn("Xekong", str(caught.exception))

    def test_a_population_far_from_the_published_one_refuses(self):
        rows = self.country()
        for row in rows:
            row["population"] *= 0.5
        provinces, districts, _ = L.gather(rows)
        with self.assertRaises(SystemExit) as caught:
            L.check(provinces, districts)
        self.assertIn("against the census's published", str(caught.exception))


class Records(unittest.TestCase):
    def rows(self, level):
        provinces, districts, _ = L.gather([
            village("Vientiane Capital", "Sikhottabong District", 1000,
                    {"Lao": 90.0}, {"Buddhism": 80.0}),
            village("Vientiane", "Phonhong District", 500,
                    {"Tai-Thay": 60.0}, {"Buddhism": 70.0}),
        ])
        return L.build(provinces if level == "province" else districts, level)

    def test_a_province_names_itself_as_the_boundary_file_does(self):
        rows = self.rows("province")
        self.assertEqual([r["name"] for r in rows], ["Vientiane", "Vientiane Capital"])
        self.assertEqual([r["id"] for r in rows],
                         ["LAO-vientiane", "LAO-vientiane-capital"])
        self.assertEqual({r["level"] for r in rows}, {"admin1"})
        self.assertEqual({r["parent"] for r in rows}, {"LAO"})

    def test_a_district_says_which_province_it_is_in(self):
        rows = self.rows("district")
        self.assertEqual([(r["name"], r["parent"], r["parent_name"]) for r in rows],
                         [("Phonhong", "LAO-vientiane", "Vientiane"),
                          ("Sikhottabong", "LAO-vientiane-capital", "Vientiane Capital")])
        self.assertEqual({r["level"] for r in rows}, {"admin2"})

    def test_every_composition_carries_its_year_and_a_note(self):
        row = self.rows("province")[1]
        self.assertEqual(row["ethnicity_year"], L.YEAR)
        self.assertEqual(row["religion_year"], L.YEAR)
        self.assertIn("village indicator table", row["ethnicity_note"])
        self.assertIn("Tai-Thay", row["ethnicity_note"])
        self.assertIn("written doctrines", row["religion_note"])
        self.assertEqual(row["population"]["value"], 1000)
        self.assertEqual(sorted(s["field"] for s in row["sources"]),
                         ["ethnicity", "population", "religion"])

    def test_language_is_not_written_here_at_all(self):
        from common import NOT_COLLECTED, collection_status
        for row in self.rows("province") + self.rows("district"):
            self.assertEqual(row["language"], {"status": "not_available"})
        # ...because the country declares it, and the declaration reaches
        # every unit through apply_collection_policy.
        self.assertEqual(collection_status("LAO", "language"), NOT_COLLECTED)
        self.assertIsNone(collection_status("LAO", "religion"))
        self.assertIsNone(collection_status("LAO", "ethnicity"))


class Placed(unittest.TestCase):
    def test_both_residuals_are_known_to_be_residuals(self):
        # "No religion or not stated" is the largest row in nine provinces and
        # in half the districts, and it is partly the absence of an answer, so
        # the map must not colour those units for it.
        import canonical_groups as cg
        for field, label in (("ethnicity", L.ETHNIC_RESIDUAL),
                             ("religion", L.RELIGION_RESIDUAL)):
            rows = [{"group": label, "pct": 60.0},
                    {"group": "Lao" if field == "ethnicity" else "Buddhism",
                     "pct": 40.0}]
            counts = cg.canonicalise(rows, field)
            self.assertTrue(cg.is_residual(label), f"{field}: {label}")
            real = {k: v for k, v in counts.items() if not cg.is_residual(k)}
            self.assertEqual(max(real, key=real.get),
                             "Lao" if field == "ethnicity" else "Buddhism")

    def test_every_label_written_reaches_a_top_grouping(self):
        import group_tree
        for field, labels in (("ethnicity", [*L.ETHNICITY.values(), L.ETHNIC_RESIDUAL]),
                              ("religion", [*L.RELIGION.values(), L.RELIGION_RESIDUAL])):
            tops = group_tree.tier1_names(field)
            for label in labels:
                self.assertIn(group_tree.ancestry(field, label)[-1], tops,
                              f"{field}: {label}")


WRITTEN = ROOT / "data" / "processed" / "laos_province.json"


@unittest.skipUnless(WRITTEN.exists(), "laos_province.json has not been fetched")
class Written(unittest.TestCase):
    """What the runner actually produced, pinned."""

    def setUp(self):
        self.provinces = json.loads(WRITTEN.read_text(encoding="utf-8"))
        self.districts = json.loads(
            (WRITTEN.parent / "laos_district.json").read_text(encoding="utf-8"))

    def test_all_eighteen_and_all_hundred_and_forty_eight(self):
        self.assertEqual(len(self.provinces), 18)
        self.assertEqual(len(self.districts), 148)
        self.assertEqual({r["name"] for r in self.provinces}, set(L.PROVINCES))
        self.assertEqual(
            {(r["parent_name"], r["name"]) for r in self.districts},
            {(p, d) for p, names in L.DISTRICTS.items() for d in names})

    def test_every_unit_carries_both_compositions_adding_to_a_hundred(self):
        for row in self.provinces + self.districts:
            for field in ("ethnicity", "religion"):
                shares = row[field]
                self.assertIsInstance(shares, list, f"{row['name']} {field}")
                self.assertEqual(round(sum(s["pct"] for s in shares), 6), 100.0,
                                 f"{row['name']} {field}")
                self.assertEqual(row[f"{field}_year"], L.YEAR)

    def test_the_districts_weigh_to_their_provinces(self):
        by_province: dict[str, int] = {}
        for row in self.districts:
            by_province[row["parent_name"]] = (by_province.get(row["parent_name"], 0)
                                               + row["population"]["value"])
        for row in self.provinces:
            self.assertLessEqual(abs(by_province[row["name"]]
                                     - row["population"]["value"]), 1, row["name"])

    def test_vientiane_capital_is_not_vientiane_province(self):
        rows = {r["name"]: r for r in self.provinces}
        self.assertNotEqual(rows["Vientiane"]["population"]["value"],
                            rows["Vientiane Capital"]["population"]["value"])
        leader = rows["Vientiane Capital"]["ethnicity"][0]
        self.assertEqual(leader["group"], "Lao")
        self.assertGreater(leader["pct"], 80.0)


if __name__ == "__main__":
    unittest.main()
