"""Religion from registered membership: Finland's population register, the Church of Sweden.

No network: the readers' helpers run on small made-up tables, and the Finnish
reader runs end to end on a made-up 11ra and 11rx bound to the map's own
units.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import group_tree  # noqa: E402
from scripts.fetch_census import finland as fi  # noqa: E402
from scripts.fetch_census import finland_religion as fr  # noqa: E402
from scripts.fetch_census import nordic_church as church  # noqa: E402
from scripts.fetch_census.nordic_origin import FIN_REGIONS  # noqa: E402

L, M, E = "vaesto_usk_evlut_p", "vaesto_usk_muu_p", "vaesto_usk_ei_p"
POP = "vaerak-vaesto"


def row(pop: float, lutheran: float, other: float, none: float) -> dict[str, float]:
    return {POP: pop, L: lutheran, M: other, E: none}


def stat2(dims: list[tuple[str, list[str]]], values: list[float]) -> dict:
    """A json-stat2 body over the given dimensions, row-major."""
    return {"id": [d for d, _ in dims], "size": [len(codes) for _, codes in dims],
            "dimension": {d: {"category": {"index": {c: i for i, c in enumerate(codes)},
                                           "label": {c: c for c in codes}}}
                          for d, codes in dims},
            "value": values}


class FinnishHelpers(unittest.TestCase):
    def test_the_division_is_read_from_the_area_variable(self):
        self.assertEqual(fr.division_year("alue_23_20260101"), 2026)
        with self.assertRaises(SystemExit):
            fr.division_year("alue")

    def test_a_maps_list_gives_the_codes_each_address_ends_in(self):
        base = ("https://api.stat.fi/classificationservice/open/api/classifications/v2/"
                "correspondenceTables/kunta_1_20200101%23seutukunta_1_20200101/maps/")
        self.assertEqual(fr.key_pairs([base + "305/178", base + "832/178", base + "434/016"]),
                         {"305": "178", "832": "178", "434": "016"})
        with self.assertRaises(SystemExit):                 # one municipality, two units
            fr.key_pairs([base + "305/178", base + "305/016"])
        with self.assertRaises(SystemExit):                 # not a map's address
            fr.key_pairs([base])
        self.assertEqual(fr.item_names([{"code": "063", "classificationItemNames": [
            {"lang": "fi", "name": "Etelä-Pirkanmaa"}]}]), {"063": "Etelä-Pirkanmaa"})

    def test_every_area_answers_and_its_shares_make_a_hundred(self):
        good = {"KU1": row(100, 60.0, 2.5, 37.5), "SSS": row(100, 60.0, 2.6, 37.5)}
        self.assertAlmostEqual(fr.check_rows(good), 0.1)
        with self.assertRaises(SystemExit):
            fr.check_rows({"KU1": row(100, 60.0, 2.5, 37.8)})        # makes 100.3
        with self.assertRaises(SystemExit):
            fr.check_rows({"KU1": {POP: 100, L: 60.0, M: 2.5}})       # a share missing
        with self.assertRaises(SystemExit):
            fr.check_rows({"KU1": row(0, 60.0, 2.5, 37.5)})           # nobody

    def test_the_national_count_must_agree_with_the_national_shares(self):
        rows = {"SSS": row(5652881, 61.2, 2.9, 35.9)}
        counted = fr.check_national(rows, {"SSS": 5652881, "F09": 3457125, "H00": 2030491})
        self.assertEqual(counted[fr.OTHER], 165265)
        with self.assertRaises(SystemExit):                 # another population
            fr.check_national(rows, {"SSS": 5652000, "F09": 3457125, "H00": 2030491})
        with self.assertRaises(SystemExit):                 # 62.0% Lutheran is not 61.2%
            fr.check_national(rows, {"SSS": 5652881, "F09": 3504786, "H00": 1982830})

    def test_today_s_municipalities_are_placed_by_code_and_a_merger_must_stay_inside(self):
        key = {"099": "S1", "214": "S1", "020": "S2"}
        self.assertEqual(fr.place(["214", "020"], key, {"099": "214"}, "t"),
                         {"214": "S1", "020": "S2"})
        with self.assertRaises(SystemExit):                 # gone, successor unknown
            fr.place(["214", "020"], key, {}, "t")
        with self.assertRaises(SystemExit):                 # successor in another unit
            fr.place(["214", "020"], {"099": "S2", "214": "S1", "020": "S2"},
                     {"099": "214"}, "t")
        with self.assertRaises(SystemExit):                 # a code the key lacks
            fr.place(["214", "020", "999"], key, {"099": "214"}, "t")

    def test_a_unit_takes_the_office_s_row_only_for_the_same_territory(self):
        rows = {"KU1": row(1000, 60.0, 2.5, 37.5), "KU2": row(3000, 70.0, 1.5, 28.5),
                "SKA": row(4000, 67.5, 1.8, 30.8), "SKB": row(3000, 70.0, 1.5, 28.5)}
        people, groups, parts = fr.sum_units(rows, {"1": "A", "2": "A"})
        self.assertEqual(people, {"A": 4000})
        self.assertEqual(parts, {"A": 2})
        self.assertAlmostEqual(groups["A"][fr.LUTHERAN], 2700)
        own = fr.own_row(rows, "SK", "A", people["A"])
        self.assertIs(own, rows["SKA"])
        self.assertIsNone(fr.own_row(rows, "SK", "B", 4000))   # same code, other people
        self.assertLessEqual(fr.check_agreement(own, groups["A"], 4000, "SKA"), 0.1)
        with self.assertRaises(SystemExit):
            fr.check_agreement(row(4000, 69.0, 1.8, 29.2), groups["A"], 4000, "SKA")
        drawn = "the sub-regions of 2020, which the map draws"
        fields, is_own = fr.composition(rows, "SK", "A", 4000, groups["A"], 2, 2025, drawn,
                                        "sub-region")
        self.assertTrue(is_own)
        self.assertEqual({g["group"]: g["pct"] for g in fields["religion"]},
                         {fr.LUTHERAN: 67.5, fr.OTHER: 1.8, fr.NONE: 30.8})
        self.assertEqual(fields["religion_basis"], "registered membership")
        self.assertIn("not of belief", fields["religion_note"])
        self.assertIn("own figure", fields["religion_note"])
        fields, is_own = fr.composition({**rows, "SKA": row(3900, 67.5, 1.8, 30.8)}, "SK",
                                        "A", 4000, groups["A"], 2, 2025, drawn, "sub-region")
        self.assertFalse(is_own)
        self.assertEqual({g["group"]: g["pct"] for g in fields["religion"]},
                         {fr.LUTHERAN: 67.5, fr.OTHER: 1.8, fr.NONE: 30.8})
        self.assertIn("Summed from its 2 municipalities in the sub-regions of 2020",
                      fields["religion_note"])

    def test_iitti_and_vaala_are_put_in_the_regions_the_map_draws_them_in(self):
        mk_of = {"142": "08", "785": "17", "020": "06"}
        munis = {"142": "Iitti", "785": "Vaala", "020": "Akaa"}
        self.assertEqual(fr.drawn_regions(mk_of, munis), {"142": "07", "785": "18", "020": "06"})
        with self.assertRaises(SystemExit):                 # the code is not Iitti's
            fr.drawn_regions(mk_of, {**munis, "142": "Isokyrö"})
        with self.assertRaises(SystemExit):                 # already where the map draws it
            fr.drawn_regions({**mk_of, "785": "18"}, munis)

    def test_the_labels_are_never_filed_under_a_named_religion_but_the_church(self):
        self.assertEqual(group_tree.ancestry("religion", fr.LUTHERAN)[1], "Protestantism")
        # The other two are the register's rows outside the Lutheran church and
        # outside every community: until shared.patch files them, the tree
        # cannot place them at all; once it does, the first only with the
        # other religions and the second with no religion.
        self.assertIn(group_tree.ancestry("religion", fr.OTHER)[-1],
                      {fr.OTHER, "Other and new religions"})
        self.assertIn(group_tree.ancestry("religion", fr.NONE)[-1], {fr.NONE, "No religion"})

    def test_the_country_is_itemised_from_every_community_of_the_register(self):
        national = {"SSS": 5652881, "A00": 65, "B00": 1845, "C00": 1072, "D00": 28512,
                    "E00": 1013, "F00": 3569853, "F01": 3067, "F02": 208, "F03": 2266,
                    "F04": 759, "F05": 14129, "F06": 16783, "F07": 1226, "F08": 58073,
                    "F09": 3457125, "F10": 14175, "F11": 2042, "G00": 20030, "G01": 620,
                    "G02": 15447, "G03": 3034, "G04": 260, "G05": 102, "G06": 567,
                    "H00": 2030491}             # 11rx, 31 December 2025 (church_probe c2)
        groups = {g["group"]: g for g in fr.national_groups(national)}
        self.assertEqual(sum(g["count"] for g in groups.values()), 5652881)
        self.assertEqual(groups[fr.LUTHERAN]["pct"], 61.2)
        self.assertEqual(groups[fr.NONE]["pct"], 35.9)
        self.assertEqual(groups["Orthodox churches"]["count"], 58073)
        self.assertEqual(groups["Other Christian"]["count"], 23743)
        self.assertEqual(groups["Other religions"]["count"], 1614)
        # Every label but the register's "none" is placed by the tree as it
        # stands, and none of them under another tradition than its own.
        expected = {fr.LUTHERAN: "Protestantism", "Orthodox churches": "Orthodoxy",
                    "Roman Catholic Church": "Catholicism", "Pentecostalism": "Protestantism",
                    "Islam": "Islam", "Buddhism": "Buddhism"}
        for label, tradition in expected.items():
            self.assertIn(tradition, group_tree.ancestry("religion", label))
        with self.assertRaises(SystemExit):     # a level that does not make its whole
            fr.national_groups({**national, "F05": 14128})
        with self.assertRaises(SystemExit):     # a community the reader does not know
            fr.national_groups({**national, "G07": 1})
        with self.assertRaises(SystemExit):     # a community missing
            fr.national_groups({k: v for k, v in national.items() if k != "A00"})
        row = fr.curated_row(fr.national_groups(national), 2025, national["SSS"])
        self.assertEqual((row["country"], row["field"], row["year"], row["basis"]),
                         ("FIN", "religion", 2025, "registered membership"))
        self.assertIn("not of belief", row["note"])

    def test_the_curated_row_is_compared_and_never_stopped_on(self):
        import json
        import tempfile
        groups = [{"group": fr.LUTHERAN, "pct": 60.0, "count": 60},
                  {"group": fr.NONE, "pct": 40.0, "count": 40}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admin0_detail.json"
            with mock.patch.object(fr, "CURATED", path):
                self.assertIn("cannot be read", fr.curated_agreement(groups, 2025))
                path.write_text(json.dumps({"rows": []}))
                self.assertIn("no row", fr.curated_agreement(groups, 2025))
                path.write_text(json.dumps({"rows": [{"country": "FIN", "field": "religion",
                                                      "year": 2025, "groups": groups}]}))
                self.assertIn("agrees", fr.curated_agreement(groups, 2025))
                self.assertIn("differs", fr.curated_agreement(groups, 2026))


class FinnishReader(unittest.TestCase):
    """finland() end to end on a made-up register, bound to the map's own units."""

    def setUp(self):
        drawn = sorted(fi.DRAWN)
        self.found = {d: f"s{i:02d}" for i, d in enumerate(drawn)}
        self.sk_names = {f"s{i:02d}": fi.DRAWN[d] for i, d in enumerate(drawn)}
        regions = sorted(FIN_REGIONS)
        self.sk_of, self.mk_of, rows = {}, {}, {}
        for i, d in enumerate(drawn):
            sk, mk = f"s{i:02d}", regions[i % len(regions)]
            for j, (pop, shares) in enumerate(((1000 + i, (60.0, 2.5, 37.5)),
                                               (3000, (70.0, 1.5, 28.5)))):
                code = f"{i:02d}{j}"
                self.sk_of[code], self.mk_of[code] = sk, mk
                rows[f"KU{code}"] = row(pop, *shares)

        def summed(codes):
            pop = sum(rows[f"KU{c}"][POP] for c in codes)
            return row(pop, *(round(sum(rows[f"KU{c}"][POP] * rows[f"KU{c}"][s]
                                        for c in codes) / pop, 1) for s in (L, M, E)))
        for sk in self.sk_names:
            rows[f"SK{sk}"] = summed([c for c, s in self.sk_of.items() if s == sk])
        for mk in regions:
            rows[f"MK{mk}"] = summed([c for c, m in self.mk_of.items() if m == mk])
        rows["SSS"] = summed(list(self.sk_of))
        # Today's s05 and region 06 are other territories than in 2020: their
        # rows count other people, so both must be summed and given a population.
        rows["SKs05"] = row(rows["SKs05"][POP] + 500, 50.0, 2.0, 48.0)
        rows["MK06"] = row(rows["MK06"][POP] - 700, 50.0, 2.0, 48.0)
        self.rows = rows
        everyone = rows["SSS"][POP]
        lutheran = round(sum(rows[f"KU{c}"][POP] * rows[f"KU{c}"][L] / 100 for c in self.sk_of))
        none = round(sum(rows[f"KU{c}"][POP] * rows[f"KU{c}"][E] / 100 for c in self.sk_of))
        # 11rx answers every community: the other members all Orthodox here.
        codes = fr.NATIONAL_TOP + tuple(c for parts in fr.NATIONAL_PARTS.values()
                                        for c in parts)
        self.national = dict.fromkeys(codes, 0)
        other = everyone - lutheran - none
        self.national.update({"SSS": everyone, "F09": lutheran, "F08": other,
                              "F00": lutheran + other, "H00": none})

    def fake_request(self, url, payload=None, **_):
        areas = sorted(self.rows)
        if url == fr.TABLE and payload is None:
            return {"variables": [{"code": "alue_23_20260101", "values": areas},
                                  {"code": "contentscode", "values": fr.CONTENTS + ["x"]},
                                  {"code": "timeperiod_y", "values": ["2024", "2025"]}]}
        if url == fr.TABLE:
            return stat2([("alue_23_20260101", areas), ("contentscode", fr.CONTENTS),
                          ("timeperiod_y", ["2025"])],
                         [self.rows[a][c] for a in areas for c in fr.CONTENTS])
        codes = sorted(self.national)
        if payload is None:
            return {"variables": [{"code": "uskontokunta_10_20190101", "values": codes}]}
        return stat2([("uskontokunta_10_20190101", codes), ("sukupuoli_9_20180101", ["SSS"]),
                      ("ikaryhma_10_20180101", ["SSS"]), ("timeperiod_y", ["2025"])],
                     [self.national[c] for c in codes])

    def keys(self, year):
        self.assertEqual(year, 2020)
        names = {mk: FIN_REGIONS[mk] for mk in FIN_REGIONS}
        munis = {code: f"Municipality {code}" for code in self.sk_of}
        return self.sk_of, self.sk_names, self.found, self.mk_of, names, munis

    def test_every_drawn_unit_is_written_once_with_its_population(self):
        # The made-up register has neither Iitti nor Vaala to move.
        with mock.patch.object(fr, "request_json", self.fake_request), \
                mock.patch.object(fr, "DRAWN_REGION", {}), \
                mock.patch.object(fr, "log") as said, \
                mock.patch("scripts.fetch_census.nordic_common.log"):
            records = fr.finland(keys=self.keys)
        admin2 = [r for r in records if r["level"] == "admin2"]
        admin1 = [r for r in records if r["level"] == "admin1"]
        self.assertEqual((len(admin2), len(admin1)), (70, 19))
        self.assertEqual(len({r["shape_id"] for r in records}), 89)
        # Every unit carries the same day's population: the office's own count
        # where today's unit of its code is the same territory, else its
        # municipalities' sum.
        self.assertTrue(all("value" in r["population"] for r in records))
        self.assertTrue(all(r["population"]["year"] == 2025 for r in records))
        # The country's itemised figure is printed for the curated file.
        printed = [c.args[0] for c in said.call_args_list if '"country": "FIN"' in c.args[0]]
        self.assertEqual(len(printed), 1)
        summed = sorted(r["id"] for r in records if "Summed" in r["population_note"])
        self.assertEqual(summed, ["FIN-REL-MK2020-06", "FIN-REL-SK2020-s05"])
        changed = next(r for r in records if r["id"] == "FIN-REL-SK2020-s05")
        self.assertEqual(changed["population"]["value"], 1005 + 3000)
        self.assertIn("Summed from its 2 municipalities", changed["religion_note"])
        self.assertIn("another territory", changed["population_note"])
        same = next(r for r in records if r["id"] == "FIN-REL-SK2020-s06")
        self.assertIn("own count", same["population_note"])
        self.assertEqual(same["population"]["value"], self.rows["SKs06"][POP])
        for r in records:
            self.assertEqual(r["religion_year"], 2025)
            self.assertEqual({g["group"] for g in r["religion"]},
                             {fr.LUTHERAN, fr.OTHER, fr.NONE})
            self.assertAlmostEqual(sum(g["pct"] for g in r["religion"]), 100, delta=0.2)

    def test_a_municipality_the_key_lacks_stops_the_run(self):
        self.rows["KU999"] = row(10, 60.0, 2.5, 37.5)
        self.rows["SSS"] = row(self.rows["SSS"][POP] + 10, *(self.rows["SSS"][c]
                                                             for c in (L, M, E)))
        self.national["SSS"] += 10
        self.national["H00"] += 10
        # The reason is checked: without DRAWN_REGION emptied the run stops
        # earlier, on the made-up register's want of Iitti.
        with mock.patch.object(fr, "request_json", self.fake_request), \
                mock.patch.object(fr, "DRAWN_REGION", {}), \
                mock.patch.object(fr, "log"), \
                self.assertRaisesRegex(SystemExit, r"\['999'\] are not in the key"):
            fr.finland(keys=self.keys)


class SwedishChurchCountry(unittest.TestCase):
    def test_shares_with_two_decimals_are_read(self):
        self.assertEqual(church.percent("56,39%"), 56.39)
        self.assertEqual(church.percent("71,8%"), 71.8)
        self.assertIsNone(church.percent("*"))

    def test_the_country_s_row_is_read_once_and_must_be_the_län_and_the_unplaced(self):
        lines = ["Blekinge län 158 854 103 376 65,1% 65,1% 0,11% 0,20% 0,98%",
                 "Riket 176 701 109 311 61,9% 61,9% 0,99% 0,50% 1,92%"]
        riket = church.riket_row(lines)
        self.assertEqual(riket, (176701, 109311, 61.9))
        with self.assertRaises(SystemExit):
            church.riket_row(lines + lines[-1:])
        # The 2021 edition calls the same row "Totalsumma"; 2020's prints none.
        self.assertEqual(church.riket_row(
            ["Totalsumma 10 452 326 5 633 867 53,9% 53,9% 0,22% 0,25% 1,27%"]),
            (10452326, 5633867, 53.9))
        self.assertIsNone(church.riket_row(lines[:1], optional=True))
        with self.assertRaises(SystemExit):
            church.riket_row(lines[:1])
        lan = {"Blekinge": (158854, 103376, 65.1)}
        church.check_country(lan, (17847, 5933, 33.2), riket)       # 2 members apart: allowed
        with self.assertRaises(SystemExit):
            church.check_country(lan, (17840, 5935, 33.2), riket)   # people must be exact
        with self.assertRaises(SystemExit):
            church.check_country(lan, (17847, 5900, 33.2), riket)

    def test_the_two_decimal_country_row_of_2019_splits_one_way(self):
        self.assertEqual(church.population_and_members(
            "10 327 579 5 823 515 56,39% 56,39% 0,16% 0,21% 1,07%"),
            (10327579, 5823515, 56.39))

    def test_län_names_find_all_twenty_one_codes_or_stop(self):
        sv = {"00": "Riket", "01": "Stockholms län", "08": "Kalmar län", "12": "Skåne län"}
        sv.update({f"{n:02d}": f"Län {n} län" for n in range(30, 48)})
        names = ["Stockholms", "Kalmars", "Skåne"] + [f"Län {n}" for n in range(30, 48)]
        codes = church.lan_codes(names, sv)
        self.assertEqual((codes["Stockholms"], codes["Kalmars"], codes["Skåne"]),
                         ("01", "08", "12"))
        with self.assertRaises(SystemExit):
            church.lan_codes(names[:-1], sv)

    def test_a_kommun_is_its_parishes_members_against_their_people(self):
        sv = {"1082": "Karlshamn", "10": "Blekinge län"}
        row = (32182, 20373, 63.3)
        edition = church.Edition(2021, "URL", {"1082": row}, {}, {"1082": 32246})
        rec = church.kommun_record("1082", edition, sv, "SHAPE")
        self.assertEqual((rec["level"], rec["shape_id"]), ("admin2", "SHAPE"))
        self.assertEqual({g["group"]: g["count"] for g in rec["religion"]},
                         {church.SWEDEN_CHURCH: 20373, church.SWEDEN_OUTSIDE: 11809})
        note = rec["religion_note"]
        self.assertIn("not belief", note)
        self.assertIn("the 20,373 members of the kommun's parishes, wherever they live, "
                      "against the 32,182 people registered in those parishes", note)
        self.assertIn("the latest edition by kommun and län", note)
        # How far the row's people are from SCB's count, and why.
        self.assertIn("-0.20% against Statistics Sweden's count of the kommun the same day "
                      "(32,246): it leaves out the people registered in the kommun without a "
                      "property", note)
        self.assertIn("63.3% are members of the Church in whatever parish", note)
        self.assertNotIn("preliminary", note)
        self.assertNotIn("Karlskrona", note)
        self.assertEqual(rec["religion_year"], 2021)
        self.assertEqual(rec["sources"][0]["url"], "URL")
        older = church.Edition(2019, "OLD", {"1082": row}, {}, {"1082": 31770}, True)
        rec = church.kommun_record("1082", older, sv, "SHAPE")
        self.assertEqual(rec["religion_year"], 2019)
        self.assertIn("in the 2021 edition they do not", rec["religion_note"])
        self.assertIn("+1.30% against Statistics Sweden's count", rec["religion_note"])
        self.assertIn("a parish crossing the kommun's boundary", rec["religion_note"])
        self.assertIn("marks its figures as preliminary", rec["religion_note"])

    def test_a_län_is_written_from_its_own_row(self):
        sv = {"10": "Blekinge län"}
        edition = church.Edition(2021, "URL", {"10": (158854, 103376, 65.1)}, {},
                                 {"10": 159001}, True)
        rec = church.lan_record("10", edition, sv, {"id": "L10", "name": "Blekinge län"})
        self.assertEqual((rec["level"], rec["parent"], rec["shape_id"], rec["name"]),
                         ("admin1", "SWE", "L10", "Blekinge län"))
        self.assertEqual({g["group"]: g["count"] for g in rec["religion"]},
                         {church.SWEDEN_CHURCH: 103376, church.SWEDEN_OUTSIDE: 55478})
        self.assertEqual(rec["religion_basis"], "registered membership")
        self.assertIn("the län's parishes", rec["religion_note"])
        self.assertIn("-0.09% against Statistics Sweden's count of the län",
                      rec["religion_note"])
        self.assertIn("preliminary", rec["religion_note"])

    def test_the_first_page_s_warning_is_found_above_the_figures_only(self):
        title = ("Medlemmar i Svenska kyrkan i förhållande till folkmängd den 31.12.2021 per "
                 "församling, kommun och län samt riket")
        warning = ("Obs! Informationen är preliminär och kan justeras i maj i samband med "
                   "publiceringen av Svenska kyrkans verksamhetsstatistik")
        row = "Karlshamns kommun 32 182 20 373 63,3% 63,3% 0,11% 0,20% 0,98%"
        self.assertEqual(church.preliminary([title, warning, row]), warning)
        self.assertIsNone(church.preliminary([title, row]))
        self.assertIsNone(church.preliminary([title, row, warning]))

    def test_a_joined_kommun_s_host_is_the_row_its_parish_is_printed_under(self):
        names = {"1762": "Munkfors", "1763": "Forshaga"}
        lines = ["Munkfors kommun 15 234 10 860 71,3% 71,3% 0,17% 0,41% 0,55%",
                 "Forshaga-Munkfors församling (176301) 15 234 10 860 71,3% 71,3% 0,17% "
                 "0,41% 0,55%"]
        # 2018-2020: the parish's code says Forshaga, the row it sits under Munkfors.
        self.assertEqual(church.joined_kommuner(["1763"], {"1762"}, names, lines,
                                                {"Munkfors": "1762"}),
                         {"1763": ("1762", "Forshaga-Munkfors")})
        with self.assertRaises(SystemExit):     # read by its code, it names itself
            church.joined_kommuner(["1763"], {"1762"}, names, lines)

    def test_each_unit_takes_the_newest_edition_whose_row_is_its_own(self):
        row = (1000, 600, 60.0)
        new = church.Edition(2021, "a", {"1442": row, "1447": row, "1082": row, "10": row},
                             {"1762": ("1763", "Forshaga-Munkfors")},
                             {"1442": 811, "1447": 1718, "1082": 1003, "10": 1006})
        old = church.Edition(2020, "b", {"1442": row, "1447": row, "1082": row, "10": row},
                             {"1763": ("1762", "Forshaga-Munkfors")},
                             {"1442": 999, "1447": 1053, "1082": 1004, "10": 1004})
        chosen, left = church.choose([new, old], ["1082", "1442", "1447", "1762", "1763"])
        self.assertEqual({c: e.year for c, e in chosen.items()}, {"1082": 2021, "1442": 2020})
        self.assertEqual(sorted(left), ["1447", "1762", "1763"])
        self.assertIn("2021: its row counts -41.8%", left["1447"][0])
        self.assertTrue(all("Forshaga-Munkfors" in why for why in left["1762"] + left["1763"]))
        # A län is held to half a per cent: 2021's row is 0.6% short, 2020's 0.4%.
        chosen, left = church.choose([new, old], ["10"], church.LAN_TOLERANCE)
        self.assertEqual({c: e.year for c, e in chosen.items()}, {"10": 2020})

    def test_the_swedish_labels_are_placed_where_denmark_s_are(self):
        self.assertEqual(group_tree.ancestry("religion", church.SWEDEN_CHURCH)[1],
                         "Protestantism")
        self.assertEqual(group_tree.ancestry("religion", church.SWEDEN_OUTSIDE)[-1],
                         "Not stated")


if __name__ == "__main__":
    unittest.main()
