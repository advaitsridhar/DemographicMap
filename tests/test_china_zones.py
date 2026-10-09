"""China's development zones placed by their townships, offline."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import china_zones as cz  # noqa: E402

ZONE_PAGE = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312"></head>
<table><tr class="towntr"><td><a href="72/220172001.html">220172001000</a></td>
<td><a href="72/220172001.html">永兴街道</a></td></tr>
<tr class="towntr"><td><a href="72/220172101.html">220172101000</a></td>
<td><a href="72/220172101.html">新湖镇</a></td></tr></table></html>"""

AREAS = [{"code": "220122", "name": "农安县", "cityCode": "2201", "provinceCode": "22"},
         {"code": "220172", "name": "长春净月高新技术产业开发区", "cityCode": "2201",
          "provinceCode": "22"},
         {"code": "320571", "name": "苏州工业园区", "cityCode": "3205", "provinceCode": "32"}]
STREETS = [{"code": "220122100", "name": "农安镇", "areaCode": "220122"},
           {"code": "220172001", "name": "永兴街道", "areaCode": "220172"},
           {"code": "220172101", "name": "新湖镇", "areaCode": "220172"},
           {"code": "320571001", "name": "娄葑街道", "areaCode": "320571"}]


class Reading(unittest.TestCase):
    def test_a_zone_page_s_townships(self):
        page = cz.decode(ZONE_PAGE.encode("gb18030"))
        self.assertEqual([(c, n) for c, n, _ in cz.rows_of(page, "town")],
                         [("220172001000", "永兴街道"), ("220172101000", "新湖镇")])

    def test_zone_codes(self):
        self.assertTrue(cz.is_zone("220172"))
        self.assertTrue(cz.is_zone("320571000000"))
        self.assertFalse(cz.is_zone("220122"))
        self.assertFalse(cz.is_zone("220181"))

    def test_only_the_zones_of_the_provinces_asked_for(self):
        zones = cz.zones_of(AREAS, STREETS, ["22"])
        self.assertEqual(list(zones), ["220172"])
        self.assertEqual(zones["220172"]["prefecture"], "220100")
        self.assertEqual(zones["220172"]["townships"],
                         [["220172001", "永兴街道"], ["220172101", "新湖镇"]])

    def test_the_bureau_s_own_page_must_agree(self):
        zones = cz.zones_of(AREAS, STREETS, ["22"])
        url = "http://www.stats.gov.cn/tjsj/tjbz/tjyqhdmhcxhfdm/2020/22/01/220172.html"
        page = cz.decode(ZONE_PAGE.encode("gb18030"))
        self.assertEqual(cz.check(zones, {url: page}),
                         ["220172: 2 townships, the same in both"])
        zones["220172"]["townships"].pop()
        with self.assertRaises(SystemExit):
            cz.check(zones, {url: page})


class Placing(unittest.TestCase):
    ITEMS = [{"qid": "Q1", "label": "Yongxing Subdistrict", "code": "220172001", "lon": 125.4,
              "lat": 43.8},
             {"qid": "Q2", "label": "Xinhu Town", "code": "220112104", "lon": 125.5, "lat": 43.7},
             {"qid": "Q3", "label": "Q9999", "code": "220172102", "lon": 125.6, "lat": 43.6},
             {"qid": "Q4", "label": "Heping Town", "code": "220122101", "lon": 125.1, "lat": 44.4},
             {"qid": "Q5", "label": "Heping Subdistrict", "code": "220102001", "lon": 125.3,
              "lat": 43.9}]

    def index(self):
        by_code = {p["code"]: p for p in self.ITEMS}
        by_pref: dict = {}
        for p in self.ITEMS:
            by_pref.setdefault(p["code"][:4], []).append(p)
        return by_code, by_pref

    def test_by_its_own_code_when_the_label_reads_as_its_name(self):
        item, how = cz.point_for("220172001", "永兴街道", *self.index())
        self.assertEqual((item["qid"], how), ("Q1", "its code"))

    def test_by_its_name_when_wikidata_keeps_its_older_code(self):
        item, how = cz.point_for("220172101", "新湖镇", *self.index())
        self.assertEqual(item["qid"], "Q2")
        self.assertIn("its name", how)

    def test_by_its_code_alone_when_the_label_is_no_name(self):
        item, _ = cz.point_for("220172102", "玉潭镇", *self.index())
        self.assertEqual(item["qid"], "Q3")

    def test_a_name_two_items_carry_places_nothing(self):
        item, how = cz.point_for("220172109", "和平镇", *self.index())
        self.assertIsNone(item)
        self.assertIn("2 items", how)


if __name__ == "__main__":
    unittest.main()
