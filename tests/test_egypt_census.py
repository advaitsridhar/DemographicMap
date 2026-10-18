"""Egypt's reader: CAPMAS's units by name, 2006's outlines, the ground test."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import egypt_census as ec  # noqa: E402


def row_html(code, name, status, native, pops, href):
    cells = "".join(f'<td class="rpop">{p}</td>' for p in pops)
    return (f'<tr itemscope="" onclick="javascript:sym(\'{code}\')"><td class="rname" id="i{code}">'
            f'<a><span itemprop="name">{name}</span></a></td><td class="rstatus">{status}</td>'
            f'<td class="rnative rev"><span itemprop="name">{native}</span></td>{cells}'
            f'<td class="sc"><a itemprop="url" href="{href}">&#8594;</a></td></tr>')


def pyramid_html(rows):
    data = [["Age Distribution", "Males", "Females"]] + [[l, -m, f] for l, m, f in rows]
    charts = [{"name": "Gender", "type": "pie", "data": []},
              {"name": "Age Distribution", "type": "pyramid", "format": "f0", "data": data}]
    return ("<th>Age Distribution (C 2017)</th><script>var addChartData = "
            f"{json.dumps(charts)};</script>")


def unit(gov, en, ar, t, m=None, f=None, code=1):
    m = m if m is not None else (t // 2 if t else None)
    f = f if f is not None else (t - t // 2 if t else None)
    return {"gov": gov, "en": en, "ar": ar, "code": code, "m": m, "f": f, "t": t}


def cp_unit(code, ar, p2006, p2017, p2023, name=None):
    return {"code": code, "gov": code[:2], "name": name or ar, "status": "Kism", "ar": ar,
            "p1996": None, "p2006": p2006, "p2017": p2017, "p2023": p2023,
            "href": f"/en/egypt/admin/x/{code}__x/"}


class Names(unittest.TestCase):
    def test_kind_number_and_name(self):
        self.assertEqual(ec.arkey("قسم ثان المنتزة"), ("kism", 2, "المنتزه"))
        self.assertEqual(ec.arkey("قسم  المنتزة"), ("kism", None, "المنتزه"))
        self.assertEqual(ec.arkey("مركز أبوتيج"), ec.arkey("مركز ابو تيج"))
        self.assertEqual(ec.arkey("مركز باريس"), ec.arkey("مركز شرطة باريس"))
        self.assertEqual(ec.arkey("قسم بدر"), ec.arkey("قسم مدينة بدر"))
        self.assertEqual(ec.arkey("الساحل الشمالى_جزء"), ec.arkey("الساحل الشمالىجزء"))

    def test_a_unit_named_twice_has_both_keys(self):
        both = ec.keys("قسم أول 6 أكتوبر / قسم ثالث 6 أكتوبر")
        self.assertEqual(both, {("kism", 1, "6اكتوبر"), ("kism", 3, "6اكتوبر")})


class Pages(unittest.TestCase):
    def test_the_table_of_every_unit(self):
        html = ("<table>" + row_html("19", "Al-Ismā'īliyah", "Governorate", "الإسماعيلية",
                                     ["714,828", "953,006", "1,303,993", "1,452,743"],
                                     "/en/egypt/admin/19__al_ismāīliyah/")
                + row_html("1908", "Abū Ṣuwīr", "Markaz", "مركز ابو صوير",
                           ["...", "152,316", "206,116", "223,134"],
                           "/en/egypt/admin/al_ismāīliyah/1908__abū_ṣuwīr/") + "</table>")
        cp = ec.parse_admin(html)
        self.assertEqual(list(cp["govs"]), ["19"])
        u = cp["units"]["1908"]
        self.assertEqual((u["gov"], u["p1996"], u["p2006"], u["p2023"]), ("19", None, 152316, 223134))
        self.assertEqual(u["ar"], "مركز ابو صوير")

    def test_the_2017_pyramid(self):
        html = pyramid_html([("90+ years", 42, 52), ("10-19 years", 21170, 18793),
                             ("0-9 years", 27047, 24995)] +
                            [(f"{lo}-{lo + 9} years", 10, 10) for lo in range(20, 90, 10)])
        pyr = ec.parse_pyramid(html)
        self.assertEqual(pyr[0], (0, 9, 27047, 24995))
        self.assertEqual(pyr[-1], (90, None, 42, 52))
        self.assertIsNone(ec.parse_pyramid("<p>no ages</p>"))

    def test_a_group_no_one_is_in_is_a_group_of_nobody(self):
        pyr = ec.parse_pyramid(pyramid_html([("80-89 years", 1, 2), ("0-9 years", 3, 4)]))
        self.assertEqual(len(pyr), 10)
        self.assertEqual(pyr[0], (0, 9, 3, 4))
        self.assertEqual(pyr[5], (50, 59, 0, 0))
        self.assertEqual(pyr[-1], (90, None, 0, 0))

    def test_groups_of_another_width_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ec.parse_pyramid(pyramid_html([("0-4 years", 1, 1), ("5+ years", 1, 1)]))


class Binding(unittest.TestCase):
    def shapes(self):
        return [{"id": "A", "name": "Aswan", "parent": "G", "bbox": [0, 0, 1, 1]},
                {"id": "B", "name": "Aswan", "parent": "G", "bbox": [0, 0, 0.1, 0.1]},
                {"id": "C", "name": "Siwa", "parent": "G", "bbox": [0, 0, 1, 1]},
                {"id": "D", "name": "Daba", "parent": "G", "bbox": [0, 0, 1, 1]},
                {"id": "E", "name": "Mit Salsil", "parent": "G", "bbox": [0, 0, 1, 1]},
                {"id": "Z", "name": "Zemam Out", "parent": "G", "bbox": [0, 0, 1, 1]}]

    def test_kism_by_size_sole_label_and_misfiled(self):
        rows = [unit("28", "Aswan", "قسم أسوان", 100), unit("28", "Aswan", "مركز أسوان", 50),
                unit("28", "Siwa", "قسم سيوة", 30), unit("28", "Daba", "قسم الضبعة", 40),
                unit("28", "Siwa", "قسم الضبعة", 5), unit("12", "MIt Salsil", "مركز ميت سلسيل", 9)]
        units = ec.units_2006(rows)
        gov_of = {s["id"]: "28" for s in self.shapes()}
        report = []
        bound = ec.bind_outlines(self.shapes(), gov_of, units, report)
        self.assertEqual(bound["B"][0]["key"][0], "kism")      # the smaller Aswan
        self.assertEqual(bound["A"][0]["key"][0], "markaz")
        self.assertEqual(bound["C"][0]["t"], 30)                # Siwa's own, not Daba's rows
        self.assertEqual(bound["D"][0]["t"], 45)                # Daba with its row labelled Siwa
        self.assertEqual(bound["E"][0]["gov"], "12")            # filed under the wrong one
        self.assertNotIn("Z", bound)

    def test_two_outlines_of_one_label_for_one_unit_bind_neither(self):
        rows = [unit("28", "Aswan", "قسم أسوان", 100)]
        shapes = [{"id": "A", "name": "Aswan", "parent": "G", "bbox": [0, 0, 1, 1]},
                  {"id": "X", "name": "Aswan", "parent": "H", "bbox": [0, 0, 1, 1]}]
        gov_of = {"A": "28", "X": "28"}
        report = []
        bound = ec.bind_outlines(shapes, gov_of, ec.units_2006(rows), report)
        self.assertEqual(bound, {})                             # two outlines, one unit: none


class Ground(unittest.TestCase):
    def test_numbered_parts_not_taken_by_another_2006_unit(self):
        rows = [unit("13", "10 Ramadan 1", "قسم مدينه عشره رمضان", 57463),
                unit("13", "10 Ramadan 2", "قسم ثان مدينه عشره رمضان", 66774)]
        units = ec.units_2006(rows)
        cp = {"1318": cp_unit("1318", "قسم أول مدينة عشرة رمضان", 58986, 73638, 88996),
              "1319": cp_unit("1319", "قسم ثان مدينة عشرة رمضان", 66934, 144246, 174325)}
        first = [u for u in units if u["key"][1] is None][0]
        numbered = {2}
        self.assertEqual([c["code"] for c in ec.named(first, cp, numbered)], ["1318"])

    def test_carved_units_make_up_the_2006_count(self):
        rows = [unit("19", "Ismailiyya", "مركز الاسماعيلية", 249858)]
        units = ec.units_2006(rows)
        bound = {"S": units}
        cp = {"units": {"1904": cp_unit("1904", "مركز الاسماعيلية", 97542, 159923, 170774),
                        "1908": cp_unit("1908", "مركز ابو صوير", 152316, 206116, 223134),
                        "1909": cp_unit("1909", "مركز التل الكبير", 66442, 101179, 112415)},
              "govs": {"19": {"p2006": 953006}}}
        provinces = {"19": {"t": 934849}}
        report = []
        plans = ec.compose(bound, cp, provinces, report, units)
        self.assertTrue(plans["S"]["same"])
        self.assertEqual(sorted(c["code"] for c in plans["S"]["parts"]), ["1904", "1908"])

    def test_a_redrawn_unit_keeps_its_2006_figures(self):
        rows = [unit("01", "Hilwan", "قسم حلوان", 640738, 330000, 310738)]
        units = ec.units_2006(rows)
        for u in units:
            u["display"] = "Hilwan"
        cp = {"units": {"0130": cp_unit("0130", "قسم حلوان", 396791, 521239, 560000)},
              "govs": {"01": {"p2006": 7902085}}}
        report = []
        plans = ec.compose({"S": units}, cp, {"01": {"t": 7956536}}, report, units)
        self.assertFalse(plans["S"]["same"])
        fields = ec.outline_record({"id": "S", "name": "Hilwan"}, units, plans["S"], {},
                                   "https://hdx", "CC BY")
        self.assertEqual(fields["population"]["value"], 640738)
        self.assertEqual(fields["population"]["year"], 2006)
        self.assertEqual(fields["sex_ratio"]["value"], 1062)
        self.assertEqual(fields["median_age"]["status"], "not_available")


class Median(unittest.TestCase):
    def test_ten_year_groups(self):
        self.assertEqual(ec.grouped_median([(0, 9, 50), (10, 19, 50), (20, None, 0)]), 10.0)


def flat_pyramid(total, men_share=0.5):
    """Ten-year groups making ``total``, men and women split by ``men_share``."""
    per = [total // 10] * 9 + [total - 9 * (total // 10)]
    return [(lo, None if lo == 90 else lo + 9, round(n * men_share), n - round(n * men_share))
            for lo, n in zip(range(0, 100, 10), per)]


def plan_for(rows, cp_units, gov_p2006, province_t):
    units = ec.units_2006(rows)
    for u in units:
        u["display"] = ec.display(u, cp_units)
    cp = {"units": cp_units, "govs": {rows[0]["gov"]: {"p2006": gov_p2006}}}
    plans = ec.compose({"S": units}, cp, {rows[0]["gov"]: {"t": province_t}}, [], units)
    return units, plans["S"]


class TableFaults(unittest.TestCase):
    def test_a_mistyped_row_is_declared_the_same_ground(self):
        # Beni Suef's markaz: a village keyed with 40,000 women too many.
        rows = [unit("22", "Bani Swayf", "مركز بنى سويف", 337254, 152303, 184951)]
        cp_units = {"2202": cp_unit("2202", "مركز بنى سويف", 298047, 429379, 473978)}
        units, plan = plan_for(rows, cp_units, 2291618, 2309439)
        self.assertTrue(plan["same"])
        self.assertTrue(plan["declared"])
        pages = {"2202": flat_pyramid(429379, 0.51)}
        fields = ec.outline_record({"id": "S", "name": "Bani Swayf"}, units, plan, pages,
                                   "https://hdx", "lic")
        self.assertEqual(fields["population"]["value"], 473978)
        self.assertEqual(fields["sex_ratio"]["year"], 2017)
        self.assertNotIn("redrawn", fields["population_note"])

    def test_a_low_2006_ratio_in_a_large_unit_is_not_written(self):
        rows = [unit("11", "Somewhere", "مركز مكان ما", 230235, 100724, 129511)]
        cp_units = {"1199": cp_unit("1199", "مركز مكان ما", 150000, 200000, 210000)}
        units, plan = plan_for(rows, cp_units, 1097339, 1123917)
        self.assertFalse(plan["same"])
        fields = ec.outline_record({"id": "S", "name": "Somewhere"}, units, plan, {},
                                   "https://hdx", "lic")
        self.assertEqual(fields["population"]["year"], 2006)
        self.assertEqual(fields["sex_ratio"]["status"], "not_available")
        self.assertIn("keying error", fields["sex_ratio"]["note"])

    def test_keyed_sub_district_rows(self):
        header = ["gov en", "gov ar", "gov", "dist en", "dist ar", "dist", "sub ar", "sub",
                  "m", "f", "t"]
        rows = [header,
                ["Beni Suef", "", 22, "Bani Swayf", "مركز بنى سويف", 2202, "الحكامنة", 220202,
                 4696, 43731, 48427],
                ["Beni Suef", "", 22, "Bani Swayf", "مركز بنى سويف", 2202, "رياض", 220223,
                 2746, 2549, 5295],
                ["Cairo", "", 1, "Tura", "قسم طره", 120, "سجن", 12001, 600, 200, 800]]
        keyed = ec.keyed_rows(rows)
        self.assertEqual([k["code"] for k in keyed], [220202])


class Wording(unittest.TestCase):
    def test_parts_named_by_kind(self):
        kism = {**cp_unit("2501", "قسم أبوتيج", 70969, 90000, 100000, "Abū Tīj"),
                "status": "Kism (fully urban)"}
        markaz = {**cp_unit("2502", "مركز أبوتيج", 193118, 230000, 270000, "Abū Tīj"),
                  "status": "Markaz"}
        self.assertEqual(ec.describe_parts([markaz, kism]), "the markaz and the kism of Abū Tīj")
        a = {**cp_unit("1301", "مركز الحسينية", 1, 1, 1, "Al-Ḥusayniyah"), "status": "Markaz"}
        b = {**cp_unit("1302", "مركز صان الحجر", 1, 1, 1, "Ṣān al-Ḥajar"), "status": "Markaz"}
        self.assertEqual(ec.describe_parts([a, b]),
                         "the markazes of Al-Ḥusayniyah and Ṣān al-Ḥajar")

    def test_a_2006_unit_named_after_its_numbered_parts(self):
        rows = [unit("24", "Kesm Al-minya", "قسم المنيا", 221547)]
        cp_units = {"2401": cp_unit("2401", "قسم أول المنيا", None, 1, 1, "Al-Minyā 1"),
                    "2402": cp_unit("2402", "قسم ثان المنيا", None, 1, 1, "Al-Minyā 2")}
        units = ec.units_2006(rows)
        self.assertEqual(ec.display(units[0], cp_units), "Al-Minyā")

    def test_tiny_counts_give_no_ratio_and_say_one_woman(self):
        got = ec.ratio_fields(41, 1, 2006, ec.SOURCE_2006)
        self.assertEqual(got["sex_ratio"]["status"], "not_available")
        self.assertIn("41 men and 1 woman", got["sex_ratio"]["note"])
        self.assertIn("42 people", got["sex_ratio"]["note"])

    def test_a_high_ratio_says_where_it_comes_from(self):
        got = ec.ratio_fields(10319, 4739, 2006, ec.SOURCE_2006)
        self.assertEqual(got["sex_ratio"]["value"], 2177)
        self.assertIn("barracks", got["sex_ratio_note"])

    def test_the_two_tables_disagreeing_is_said_as_such(self):
        rows = [unit("01", "Hurghada 1", "قسم أول الغردقة", 31148, 17864, 13284)]
        cp_units = {"0101": cp_unit("0101", "قسم أول الغردقة", 69616, 80000, 90000,
                                    "Al-Ghurdaqah 1")}
        units, plan = plan_for(rows, cp_units, 7902085, 7956536)
        fields = ec.outline_record({"id": "S", "name": "Hurghada 1"}, units, plan, {},
                                   "https://hdx", "lic")
        self.assertIn("put 69,616 people", fields["population_note"])
        self.assertIn("against 31,148", fields["population_note"])
        self.assertNotIn("redrawn", fields["population_note"] + fields["median_age"]["note"])

    def test_publications_have_their_own_names(self):
        rows = [unit("22", "Bani Swayf", "مركز بنى سويف", 337254, 152303, 184951)]
        cp_units = {"2202": cp_unit("2202", "مركز بنى سويف", 298047, 429379, 473978)}
        units, plan = plan_for(rows, cp_units, 2291618, 2309439)
        fields = ec.outline_record({"id": "S", "name": "Bani Swayf"}, units, plan,
                                   {"2202": flat_pyramid(429379)}, "https://hdx", "lic")
        names = {s["field"]: s["name"] for s in fields["sources"]}
        self.assertNotEqual(names["population"], names["median_age/sex_ratio"])
        self.assertTrue(all(n.startswith(ec.CAPMAS + ",") for n in names.values()))


class Renamed(unittest.TestCase):
    def test_marina_is_today_s_kism_of_al_alamayn(self):
        rows = [unit("33", "Alamn", "قسم مارينا العلمين السياحية", 42, 41, 1)]
        cp_units = {"3306": {**cp_unit("3306", "قسم العلمين", 52, 9932, 12580, "Al-'Alamayn"),
                             "status": "Kism (fully rural)"}}
        units, plan = plan_for(rows, cp_units, 323381, 306713)
        self.assertTrue(plan["same"])                   # 42 and 52: within the slack
        fields = ec.outline_record({"id": "S", "name": "Alamn"}, units, plan,
                                   {"3306": flat_pyramid(9932)}, "https://hdx", "lic")
        self.assertEqual(fields["population"]["value"], 12580)
        self.assertIn("Marina al-Alamein", fields["population_note"])
        self.assertIn("41 men and 1 woman", fields["population_note"])


class Governorates(unittest.TestCase):
    def test_an_outline_holding_other_ground_refuses_or_notes(self):
        def gov(code, p2017, p2023):
            return {"code": code, "name": code, "p2006": 1, "p2017": p2017, "p2023": p2023,
                    "href": f"/en/egypt/admin/{code}__x/"}
        cp = {"govs": {"29": gov("29", 1250209, 1400640), "27": gov("27", 3164281, 3640916),
                       "01": gov("01", 9539673, 10248385), "21": gov("21", 8632021, 9514540)},
              "units": {}}
        qus = {**cp_unit("2711", "مركز قوص", 1, 464288, 534523, "Qūṣ"), "status": "Markaz"}
        zamalek = {**cp_unit("0118", "قسم الزمالك", 17365, 14946, 16064, "Az-Zamālik"),
                   "status": "Kism (fully urban)"}
        plans = {"37247803B95427647060127": {"parts": [qus]},
                 "37247803B72756565577460": {"parts": [zamalek]}}
        shapes = {g: {"id": g, "name": g} for g in cp["govs"]}
        pages = {g: flat_pyramid(r["p2017"]) for g, r in cp["govs"].items()}
        out = {r["codes"]["capmas"]: r for r in ec.governorates(cp, shapes, pages, plans, [])}
        luxor, qena, cairo, giza = out["29"], out["27"], out["01"], out["21"]
        # Qūṣ is 38% of Luxor's people and 15% of Qena's: both refused, and say why.
        for refused in (luxor, qena):
            self.assertEqual(refused["population"]["status"], "not_available")
            self.assertIn("Qūṣ", refused["population"]["note"])
            self.assertEqual(refused["population"]["displaces_before"], ec.DISPLACES_BEFORE)
            self.assertEqual(refused["median_age"]["status"], "not_available")
            self.assertEqual(refused["sex_ratio"]["status"], "not_available")
        self.assertIn("1,400,640", luxor["population"]["note"])
        self.assertIn("holds the markaz of Qūṣ", luxor["population"]["note"])
        self.assertIn("leaves out the markaz of Qūṣ", qena["population"]["note"])
        # Zamalek is a sliver of either: the figures stand, with a note.
        self.assertEqual(cairo["population"]["value"], 10248385)
        self.assertIn("leaves out the kism of Az-Zamālik", cairo["population_note"])
        self.assertIn("holds the kism of Az-Zamālik", giza["sex_ratio_note"])


if __name__ == "__main__":
    unittest.main()
