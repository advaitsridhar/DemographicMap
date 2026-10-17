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


if __name__ == "__main__":
    unittest.main()
