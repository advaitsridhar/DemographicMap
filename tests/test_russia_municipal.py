"""Tests for binding Russia's census formations to the map's polygons, no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import russia_municipal as rm  # noqa: E402


def cunit(name, total=1000, rural=500, towns=(), urban_only=False):
    unit = {"name": name, "total": total, "men": total // 2, "women": total - total // 2,
            "rural": rural, "towns": list(towns), "urban_only": urban_only, "places": []}
    unit["stems"] = rm.census_stems(unit)
    return unit


def shape(sid, name, label=None):
    s = {"id": sid, "name": name}
    s["stems"] = rm.shape_stems(s, {"ru": label} if label else None)
    return s


class NamesTest(unittest.TestCase):
    def test_a_district_and_its_town_keep_apart(self):
        self.assertNotEqual(rm.ru_stem(rm.ru_core("Алейский муниципальный район")),
                            rm.ru_stem(rm.ru_core("Алейск")))

    def test_romanisations_meet(self):
        census = rm.latin_stem(rm.translit(rm.ru_stem(rm.ru_core("Белорецкий муниципальный район"))))
        self.assertEqual(census, rm.latin_stem("Beloretsky District"))
        census = rm.latin_stem(rm.translit(rm.ru_stem(rm.ru_core("Абанский муниципальный район"))))
        self.assertEqual(census, rm.latin_stem("Abansky Rayon"))

    def test_a_cut_off_name_is_compared_as_a_start(self):
        self.assertEqual(rm.own_russian("городской округ Верхний Та"),
                         rm.ru_stem(rm.ru_core("Верхний Та")) + "*")
        self.assertEqual(rm.own_russian("Арамильский городской окру"),
                         rm.ru_stem("арамильский"))

    def test_a_town_is_not_its_districts_label(self):
        self.assertFalse(rm.label_agrees("Volgodonsk", "Волгодонской район"))
        self.assertTrue(rm.label_agrees("Anninsky District", "Аннинский район"))

    def test_a_city_okrug_answers_to_its_town(self):
        unit = cunit("Кемеровский городской округ", total=1000, rural=10, towns=["Кемерово"])
        self.assertEqual(unit["stems"][2], "city")
        self.assertIn(rm.ru_stem("кемерово"), unit["stems"][0])


class BindTest(unittest.TestCase):
    def test_town_and_district_each_find_their_own(self):
        units = [cunit("Кемеровский городской округ", rural=10, towns=["Кемерово"]),
                 cunit("Кемеровский муниципальный округ")]
        shapes = [shape("a", "Kemerovo"), shape("b", "Kemerovsky District")]
        bound, _ = rm.bind_subject(units, shapes, {})
        self.assertEqual(bound, {0: "a", 1: "b"})

    def test_two_equal_claims_bind_neither(self):
        units = [cunit("Каширский муниципальный район")]
        shapes = [shape("a", "Kashirsky District"), shape("b", "Каширский район")]
        bound, notes = rm.bind_subject(units, shapes, {})
        self.assertEqual(bound, {})
        self.assertTrue(notes)

    def test_a_declared_exonym_binds(self):
        units = [cunit("Прионежский муниципальный район")]
        shapes = [shape("a", "Äänisenranta District")]
        bound, _ = rm.bind_subject(units, shapes, {})
        self.assertEqual(bound, {0: "a"})


class MergedOkrugTest(unittest.TestCase):
    """An okrug of today is never laid on one of the polygons it was made from."""

    def town(self, name):
        return rm.latin_stem(rm.translit(rm.ru_stem(rm.ru_core(name)))).replace("~", "")

    def test_a_district_adjective_with_a_fleeting_vowel_is_its_towns(self):
        # Kolomna and Kolomensky differ in their sixth letter.
        self.assertTrue(rm.adjective_of(self.town("Коломна"),
                                        rm.latin_stem("Kolomensky District")))
        self.assertTrue(rm.adjective_of(self.town("Серпухов"),
                                        rm.latin_stem("Serpukhovsky District")))
        self.assertTrue(rm.adjective_of(self.town("Переславль-Залесский"),
                                        rm.latin_stem("Pereslavsky District")))
        self.assertFalse(rm.adjective_of(self.town("Коломна"),
                                         rm.latin_stem("Lukhovitsky District")))
        self.assertFalse(rm.adjective_of(self.town("Красноармейск"),
                                         rm.latin_stem("Krasnogorsky District")))

    def test_a_town_drawn_apart_refuses_its_okrug(self):
        odintsovo = cunit("Одинцовский городской округ", total=471529, rural=60000,
                          towns=["Одинцово", "Звенигород", "Кубинка"])
        free = [shape("z", "Zvenigorod", "Городской округ Звенигород"),
                shape("d", "Istrinsky District")]
        town, where = rm.town_drawn_apart([odintsovo], free)
        self.assertEqual((town, where["id"]), ("Звенигород", "z"))
        kolomna = cunit("Городской округ Коломна", total=217703, rural=58494,
                        towns=["Коломна", "Озёры"])
        town, where = rm.town_drawn_apart([kolomna], [shape("o", "городской округ Озёры")])
        self.assertEqual(where["id"], "o")

    def test_a_district_polygon_is_not_taken_for_a_town(self):
        pushkino = cunit("Городской округ Пушкинский", total=299385, rural=25158,
                         towns=["Пушкино"])
        self.assertIsNone(rm.town_drawn_apart([pushkino], [shape("p", "Pushkinsky District")]))

    def test_the_lotoshino_okrug_is_declared(self):
        bound, _ = rm.bind_subject([cunit("Городской округ Лотошино", rural=15940)],
                                   [shape("a", "Lotoshinsky District")], {})
        self.assertEqual(bound, {0: "a"})


class KindTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(rm.shape_kind("Abansky Rayon"), "district")
        self.assertEqual(rm.shape_kind("Kolomna urban okrug"), "city")
        self.assertEqual(rm.shape_kind("Voronezh"), "city")


if __name__ == "__main__":
    unittest.main()
