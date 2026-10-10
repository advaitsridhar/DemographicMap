"""The build's reach for South and Southeast Asia: displaced Wikidata-points
figures, the parents Viet Nam's and Timor-Leste's censuses name, and
nationality labels placed as nationalities."""

import json
import re
import sys
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
import group_tree  # noqa: E402


def fold(text):
    text = unicodedata.normalize("NFKD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]", "", text)


class DisplacedPointsFigure(unittest.TestCase):
    def test_a_reason_displaces_a_figure_the_points_file_bound(self):
        entity = {"sources": []}
        for row in ({"population": {"value": 105053, "year": 2019}, "sources": [],
                     "_source": "wikidata_admin2.json"},
                    {"population": {"value": 105053, "year": 2019}, "sources": [],
                     "_source": "wikidata_points_admin2.json"},
                    {"population": {"status": "not_available", "note": "undercount",
                                    "displaces_before": 2020},
                     "_source": "cambodia_census.json"}):
            be.merge_adapter(entity, dict(row))
        self.assertNotIn("value", entity["population"])

    def test_a_count_is_never_displaced(self):
        entity = {"sources": []}
        be.merge_adapter(entity, {"population": {"value": 9, "year": 2019}, "sources": [],
                                  "_source": "cambodia_census.json"})
        be.merge_adapter(entity, {"population": {"status": "not_available", "note": "x",
                                                 "displaces_before": 2020},
                                  "_source": "other.json"})
        self.assertEqual(entity["population"]["value"], 9)


class CensusParents(unittest.TestCase):
    def test_viet_nams_declared_parents_are_the_census_provinces(self):
        path = ROOT / "data/processed/vietnam_district.json"
        if not path.exists():
            self.skipTest("vietnam_district.json not in this checkout")
        province = {r["shape_id"]: r["id"].split("-")[2]
                    for r in json.loads(path.read_text())
                    if r.get("level") == "admin2" and r.get("shape_id")}
        declared = {sid: name for sid, (iso, name) in be.DECLARED_PARENTS.items()
                    if iso == "VNM"}
        self.assertGreaterEqual(len(declared), 27)
        for sid, name in declared.items():
            self.assertIn(sid, province, sid)
            census, label = province[sid], fold(name)
            self.assertTrue(census in label or label in census, (sid, name, census))

    def test_timor_lestes_two_districts(self):
        declared = {name for iso, name in be.DECLARED_PARENTS.values() if iso == "TLS"}
        self.assertEqual(declared, {"Dili", "Cova Lima"})


class NationalitiesAsNationalities(unittest.TestCase):
    def test_pakistans_table_10_answers_are_national_identities(self):
        for label in ("Afghan national", "Chinese national", "Bangali national", "Pakistani"):
            self.assertEqual(group_tree.parent_of("ethnicity", label),
                             "Other national identities", label)
        # The peoples keep their own places.
        self.assertNotEqual(group_tree.parent_of("ethnicity", "Chinese"),
                            "Other national identities")
        self.assertNotEqual(group_tree.parent_of("ethnicity", "Bangali"),
                            "Other national identities")


class ThaiRegisterRows(unittest.TestCase):
    """Thailand's districts take the register through Wikidata; three are spelt
    otherwise in the boundary file, and a 1970 province shadowed Thon Buri."""

    def setUp(self):
        self.saved = list(be.ADAPTER_FILES)
        be.ADAPTER_FILES[:] = ["wikidata_admin2.json"]

    def tearDown(self):
        be.ADAPTER_FILES[:] = self.saved

    def test_aliases_and_dropped_rows(self):
        if not (be.PROCESSED / "wikidata_admin2.json").exists():
            self.skipTest("wikidata_admin2.json not in this checkout")
        rows = {r["id"]: r for r in be.load_adapters()["THA"]}
        self.assertNotIn("THA-WD-Q6580711", rows)
        for rid, (name, alias) in {"THA-WD-Q1019417": ("Watthana", "Vadhana"),
                                   "THA-WD-Q475772": ("Khwao Sinarin", "Khwao Sin Rin"),
                                   "THA-WD-Q476889": ("Thap Khlo", "Tap Khlo")}.items():
            self.assertEqual(rows[rid]["name"], name)
            self.assertIn(alias, rows[rid]["aliases"])
        self.assertEqual(rows["THA-WD-Q2305621"]["name"], "Thon Buri")


if __name__ == "__main__":
    unittest.main()
