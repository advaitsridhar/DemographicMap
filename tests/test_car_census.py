"""The Central African Republic's 2021 census mapping and 2016 ages, on small sheets (no network)."""

import unittest

from scripts.fetch_census import car_census as cc
from scripts.fetch_census.binding import fold


def uscb(rows):
    """A USCB sheet: field names, then aliases, then data."""
    head = list(rows[0].keys())
    return cc.table([head, head] + [[r.get(k) for k in head] for r in rows])


class Sheets(unittest.TestCase):
    def test_uscb_and_ocha_layouts(self):
        rows = uscb([{"ADM_LEVEL": 1, "AREA_NAME": "Lobaye", "POP_BTOTL": 10, "POP_MTOTL": 5,
                      "POP_FTOTL": 5}])
        self.assertEqual(rows[0]["AREA_NAME"], "Lobaye")
        ocha = cc.plain([["Pcode3", "T_TL"], ["CF111", 12.4], [None, None]])
        self.assertEqual(ocha, [{"Pcode3": "CF111", "T_TL": 12.4}])

    def test_prev_communes(self):
        rows = [{"Pcode1": "CF11", "PrevPréfecture": "Lobaye", "Pcode2": "CF111",
                 "PrevSous-préfecture": "Mbaïki", "Pcode3": "CF1111", "PrevCommune": "Mbaïki",
                 "T_TL": 100.4, "M_TL": 49.2, "F_TL": 51.2},
                {"Pcode3": "", "T_TL": 5}]
        out = cc.prev_communes(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["total"], 100)


class Crosswalk(unittest.TestCase):
    def c21(self):
        def unit(pref, sp, name, total):
            return {"name": name, "pref": pref, "sp": sp, "total": total,
                    "men": round(total * 0.49), "women": total - round(total * 0.49)}
        return {"country": None, "prefectures": {}, "sps": {},
                "communes": [unit("Lobaye", "Mbaïki", "Mbaïki", 100),
                             unit("Lobaye", "Mbaïki", "Nouvelle commune", 40),
                             unit("Bangui", "Bangui", "Bégoua", 60),
                             unit("Lim-Pendé", "Paoua", "Paoua", 70)]}

    def test_names_siblings_and_placed(self):
        g03 = [("lobaye", "mbaiki", "mbaiki"), ("ouhampende", "paoua", "paoua"),
               ("ombellampoko", "bimbo", "bimbo")]
        held, problems = cc.own_crosswalk(self.c21(), g03)
        self.assertEqual(problems, [])
        # The new commune goes with its sibling; Bégoua to Bimbo as placed; Paoua
        # under the prefecture it was in before 2020.
        self.assertEqual(sum(u["total"] for u in held[("lobaye", "mbaiki")]), 140)
        self.assertEqual(held[("ombellampoko", "bimbo")][0]["name"], "Bégoua")
        self.assertEqual(held[("ouhampende", "paoua")][0]["total"], 70)

    def test_fixed_split_is_counted(self):
        c21 = self.c21()
        self.assertEqual(cc.fixed_split(c21), 0)
        c21["communes"][0]["men"] = 60
        self.assertEqual(cc.fixed_split(c21), 1)

    def test_seat_reason_names_no_process(self):
        self.assertIn("seats", cc.SEAT_GAP)
        for word in ("read", "fetch", "adapter", "build"):
            self.assertNotIn(word, cc.SEAT_GAP.lower())

    def test_suspect_duplicate(self):
        self.assertIn(fold("Dédé-Mokouba"), cc.SUSPECT)
        self.assertIn("23,708", cc.SUSPECT[fold("Dédé-Mokouba")])
        self.assertEqual(cc.spelled("Dede-Makouba"), "Dédé-Mokouba")


class Twins(unittest.TestCase):
    """Counts the table gives two communes are said where they are counted."""

    def setUp(self):
        def unit(name, total):
            return {"name": name.upper(), "total": total}
        self.groups = {"M": [("bassekotto", "mobaye")], "D": [("mamberekadei", "dedemokouba")],
                       "G": [("ouaka", "grimari")]}
        self.placement = {("bassekotto", "mobaye"): [unit("Mobaye", 23_708), unit("Zangba", 57_790)],
                          ("mamberekadei", "dedemokouba"): [unit("Haute-Kadéi", 23_708)],
                          ("ouaka", "grimari"): [unit("Lissa", 8_825), unit("Pouyamba", 8_825),
                                                 unit("Grimari", 33_625)]}
        self.shapes = {"M": {"name": "Mobaye"}, "D": {"name": "Dédé-Mokouba"},
                       "G": {"name": "Grimari"}}
        self.prefectures = {"bassekotto": {"name": "Basse-Kotto"},
                            "mamberekadei": {"name": "Mambéré-Kadéï"}, "ouaka": {"name": "Ouaka"}}
        self.pref_of = {sid: keys[0][0] for sid, keys in self.groups.items()}
        self.twins = cc.twin_counts(self.groups, self.placement)

    def test_both_twins_are_found(self):
        self.assertEqual(set(self.twins), {23_708, 8_825})

    def test_the_sub_prefectures_say_so(self):
        mobaye = cc.twin_sentence("M", self.twins, self.shapes, self.prefectures, self.pref_of)
        self.assertIn("Haute-Kadéi, a commune of Dédé-Mokouba in Mambéré-Kadéï", mobaye)
        self.assertIn("cannot be told", mobaye)
        grimari = cc.twin_sentence("G", self.twins, self.shapes, self.prefectures, self.pref_of)
        self.assertIn("Lissa and Pouyamba, the same count (8,825 people each)", grimari)

    def test_the_prefectures_say_what_their_sums_include(self):
        mk = cc.twin_sentence_prefecture("mamberekadei", self.twins, self.shapes,
                                         self.prefectures, self.pref_of)
        self.assertIn("includes the 23,708 people the 2021 mapping's table gives Haute-Kadéi (Dédé-Mokouba)", mk)
        self.assertIn("shows no 2021 count for that reason", mk)
        self.assertIn("Mobaye (Mobaye, Basse-Kotto)", mk)
        bk = cc.twin_sentence_prefecture("bassekotto", self.twins, self.shapes,
                                         self.prefectures, self.pref_of)
        self.assertIn("Mobaye (Mobaye)", bk)
        self.assertNotIn("shows no 2021 count", bk)
        ouaka = cc.twin_sentence_prefecture("ouaka", self.twins, self.shapes, self.prefectures,
                                            self.pref_of)
        self.assertIn("Lissa (Grimari) and Pouyamba (Grimari)", ouaka)


class Ages(unittest.TestCase):
    def row(self, name, shares, men=490, women=510):
        row = {"ADM_LEVEL": 1, "AREA_NAME": name, "MTOTL": men, "FTOTL": women,
               "BTOTL": men + women}
        for i, low in enumerate(range(0, 80, 5)):
            row[f"B{low:02d}{low + 4:02d}"] = shares[i]
        row["B80PL"] = shares[16]
        return row

    def test_age_table_and_copies(self):
        young = [150, 140, 120, 100, 90, 80, 70, 60, 50, 40, 30, 25, 20, 10, 8, 5, 2]
        old = [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 25, 20, 5]
        ages = cc.age_table([self.row("Vakaga", young), self.row("Bangui", old),
                             self.row("Kémo", young)])
        self.assertEqual(ages["vakaga"]["groups"][-1], [80, None, 2])
        own, report = cc.own_structures(ages)
        # Vakaga and Kémo share one structure: neither is taken for its own.
        self.assertEqual(own, {"bangui"})
        self.assertTrue(any("share one structure" in line for line in report))


class Projection(unittest.TestCase):
    """ICASEES's 2025 projection by 2020 sub-prefecture, on the 2003 polygons."""

    def setUp(self):
        def commune(pref, sp, name, total):
            return {"pref": pref, "sp": sp, "name": name, "total": total}
        # 2003 (prefecture, sub-prefecture) -> its 2021 communes, each with its
        # 2020 prefecture and sub-prefecture.
        self.placement = {
            ("bassekotto", "alindao"): [commune("Basse-Kotto", "Alindao", "Alindao", 100_000),
                                        commune("Basse-Kotto", "Alindao", "Datoko", 25_040)],
            ("bassekotto", "mingala"): [commune("Basse-Kotto", "Mingala", "Mingala", 20_000)],
            # 2020's Amada-Gaza is in two 2003 polygons.
            ("mamberekadei", "amadagaza"): [commune("Mambéré", "Amada-Gaza", "Amada", 10_000)],
            ("mamberekadei", "gamboula"): [commune("Mambéré", "Amada-Gaza", "Gaza", 5_151),
                                          commune("Mambéré", "Gamboula", "Gamboula", 40_000)],
            ("bangui", "bangui"): [commune("Bangui", "Bangui", "1er Arrondissement", 900_000)],
            ("ombellampoko", "bimbo"): [commune("Bangui", "Bimbo", "Bimbo", 300_000)],
        }
        self.groups = {"p-alindao": [("bassekotto", "alindao")],
                       "p-mingala": [("bassekotto", "mingala")],
                       "p-amada": [("mamberekadei", "amadagaza")],
                       "p-gamboula": [("mamberekadei", "gamboula")],
                       "p-bangui": [("bangui", "bangui")],
                       "p-bimbo": [("ombellampoko", "bimbo")]}
        self.shapes = {sid: {"name": name} for sid, name in (
            ("p-alindao", "Alindao"), ("p-mingala", "Mingala"), ("p-amada", "Amada-Gaza"),
            ("p-gamboula", "Gamboula"), ("p-bangui", "Bangui"), ("p-bimbo", "Bimbo"))}
        self.c21 = {"sps": {(fold(c["pref"]), fold(c["sp"])): {}
                            for units in self.placement.values() for c in units}}
        self.admin1 = [{"id": "BK", "name": "Basse-Kotto"}, {"id": "MK", "name": "Mambéré-Kadéï"},
                       {"id": "BG", "name": "Bangui"}, {"id": "OM", "name": "Ombella-M'Poko"}]
        self.rows = [{"pref": "Basse-Kotto", "sp": "Alindao", "code": "CF612", "value": 131_218.5},
                     {"pref": "Basse-Kotto", "sp": "Mingala", "code": "CF613", "value": 21_000.2},
                     {"pref": "Mambéré", "sp": "Amada-Gaza", "code": "CF242", "value": 20_319.3},
                     {"pref": "Mambéré", "sp": "Gamboula", "code": "CF243", "value": 42_000.0},
                     {"pref": "Bangui", "sp": "Bangui Centre", "code": "CF711", "value": 700_000.0},
                     {"pref": "Bangui", "sp": "Bangui Kaga", "code": "CF712", "value": 786_900.0}]

    def run_it(self):
        totals = {sid: sum(u["total"] for k in keys for u in self.placement[k])
                  for sid, keys in self.groups.items()}
        return cc.projection(self.rows, self.c21, self.placement, self.groups, self.shapes,
                             self.admin1, totals, "https://data.humdata.org/dataset/cod-ps-caf")

    def test_whole_sub_prefectures_are_added_up(self):
        records, reasons, pref_reasons, _ = self.run_it()
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["p-alindao"]["population"]["value"], 131_218)
        self.assertEqual(by["p-alindao"]["population"]["year"], 2025)
        self.assertIn("The census mapping counted 125,040 people here on 1 March 2021",
                      by["p-alindao"]["population_note"])
        self.assertEqual(by["BK"]["population"]["value"], 152_219)
        self.assertNotIn("sex_ratio", {k for k, v in by["p-alindao"].items()
                                       if isinstance(v, dict) and "value" in v})

    def test_a_sub_prefecture_on_two_polygons_gives_neither_a_figure(self):
        records, reasons, pref_reasons, _ = self.run_it()
        shown = {r["shape_id"] for r in records}
        self.assertFalse({"p-amada", "p-gamboula", "MK"} & shown)
        self.assertIn("the communes of Amada-Gaza (Amada-Gaza, Gamboula) lie partly in this "
                      "sub-prefecture", reasons["p-amada"])
        self.assertIn("gives no figure for Amada-Gaza and Gamboula", pref_reasons["MK"])

    def test_a_withheld_count_gets_no_projection(self):
        totals = {sid: sum(u["total"] for k in keys for u in self.placement[k])
                  for sid, keys in self.groups.items()}
        records, reasons, pref_reasons, _ = cc.projection(
            self.rows, self.c21, self.placement, self.groups, self.shapes, self.admin1, totals,
            "https://data.humdata.org/dataset/cod-ps-caf", {"p-mingala"})
        self.assertNotIn("p-mingala", {r["shape_id"] for r in records})
        # Mingala's 2025 figure grows from its count as Alindao's does (5%).
        self.assertIn("gives it 21,000 people, the same 2021 count grown as its prefecture's "
                      "other sub-prefectures grow", reasons["p-mingala"])
        self.assertIn("gives no figure for Mingala", pref_reasons["BK"])

    def test_one_share_of_men_per_prefecture(self):
        rows = [{"pref": "Bangui", "men": 116_361.5, "women": 126_735.6},
                {"pref": "Bangui", "men": 263_419.2, "women": 286_904.1},
                {"pref": "Vakaga", "men": 5_625.9, "women": 5_142.2}]
        copied, report = cc.one_sex_split(rows)
        self.assertTrue(copied)
        rows.append({"pref": "Vakaga", "men": 5_000.0, "women": 5_000.0})
        self.assertFalse(cc.one_sex_split(rows)[0])

    def test_a_prefecture_divided_otherwise(self):
        records, reasons, _, report = self.run_it()
        self.assertFalse({"p-bangui", "p-bimbo"} & {r["shape_id"] for r in records})
        for sid in ("p-bangui", "p-bimbo"):
            self.assertIn("divides Bangui prefecture, as the 2020 division draws it, into 2 "
                          "units of its own (Bangui Centre, Bangui Kaga; 1,486,900 people)",
                          reasons[sid])


if __name__ == "__main__":
    unittest.main()
