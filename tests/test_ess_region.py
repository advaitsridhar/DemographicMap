"""ESS by region: codes, pooling, thresholds and binding, without the network."""

import unittest

from scripts.fetch_census import ess_region as ess


def tabs(rounds):
    """A stored-tables payload: {prefix: {field: {region: {code: n}}}} with weights = n * w."""
    out = {"rounds": {}}
    for prefix, fields in rounds.items():
        entry = {"labels": {}}
        for field, regions in fields.items():
            entry[field] = {
                "n": {r: dict(cells) for r, cells in regions.items()},
                "weighted": {r: {k: v * 1.5 if r.endswith("1") else v for k, v in cells.items()}
                             for r, cells in regions.items()},
            }
        out["rounds"][prefix] = entry
    return out


CROSSWALK = {
    "FRK": {"nuts_level": 1, "level": "admin1", "shape_id": "S-ARA", "name": "Auvergne-Rhône-Alpes",
            "iou": 0.9},
    "FRF": {"nuts_level": 1, "level": "admin1", "shape_id": "S-GE", "name": "Grand Est", "iou": 0.9},
    "FR1": {"superseded_by": "FR10"},
    "FR10": {"nuts_level": 2, "level": "admin1", "shape_id": "S-IDF", "name": "Île-de-France",
             "iou": 0.9},
    "ITC": {"nuts_level": 1, "level": "admin1", "shape_id": "S-NO", "name": "Nord-Ovest", "iou": 0.9},
    "ITC4": {"nuts_level": 2, "level": "admin2", "shape_id": "S-LOM", "name": "Lombardia",
             "iou": 0.9},
    "AT13": {"superseded_by": "AT130"},
    "AT130": {"nuts_level": 3, "level": "admin2", "shape_id": "S-WIEN2", "name": "Wien(Stadt)",
              "iou": 0.86, "also": [{"level": "admin1", "shape_id": "S-WIEN1", "name": "Wien"}]},
    "HU1": {"refused": "Budapest and Pest together"},
}


class Codes(unittest.TestCase):
    def test_religion_groups(self):
        self.assertEqual(ess.religion_group("2/66"), "No religion")
        self.assertEqual(ess.religion_group("1/1"), "Roman Catholic")
        self.assertEqual(ess.religion_group("1/3"), "Orthodox")
        self.assertEqual(ess.religion_group("1/6"), "Islam")
        for missing in ("7/66", "8/66", "9/66", "1/77", "1/88", "1/99", "1/66"):
            self.assertIsNone(ess.religion_group(missing), missing)

    def test_self_completion_keys(self):
        self.assertEqual(ess.one_question_key("66"), "2/66")
        self.assertEqual(ess.one_question_key("3"), "1/3")
        self.assertEqual(ess.one_question_key("99"), "9/99")
        self.assertEqual(ess.religion_group(ess.one_question_key("66")), "No religion")
        self.assertIsNone(ess.religion_group(ess.one_question_key("77")))

    def test_language_groups(self):
        self.assertEqual(ess.language_group("FRE"), "French")
        self.assertEqual(ess.language_group("FRM"), "French")  # a coder's slip, not Middle French
        self.assertEqual(ess.language_group("GLG"), "Galician")
        self.assertEqual(ess.language_group("APA"), "Other languages")  # never Apache in Spain
        for missing in ("777", "888", "999", "UND", "MIS", "ZXX"):
            self.assertIsNone(ess.language_group(missing))

    def test_labels_are_placed(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import group_tree
        for label in set(ess.DENOMINATIONS.values()) | {"No religion"}:
            if label != "No religion":
                self.assertIsNotNone(group_tree.parent_of("religion", label), label)
        # Other non-Christian would file under Protestantism by its words.
        self.assertNotIn("Other non-Christian religions", ess.DENOMINATIONS.values())

    def test_nuts_versions(self):
        self.assertEqual(ess.nuts2024("FR21"), "FRF")   # Champagne-Ardenne is in Grand Est
        self.assertEqual(ess.nuts2024("FR10"), "FR10")
        self.assertEqual(ess.nuts2024("GR30"), "EL30")
        self.assertEqual(ess.nuts2024("GR14"), "EL61")  # Thessalia recoded in 2016
        self.assertEqual(ess.nuts2024("ITD5"), "ITH5")
        self.assertIsNone(ess.nuts2024("99999"))
        self.assertIsNone(ess.nuts2024(""))
        self.assertEqual(ess.ancestors("ITC4"), ["ITC", "ITC4"])
        self.assertEqual(ess.ancestors("FRK"), ["FRK"])


class Build(unittest.TestCase):
    def test_threshold_binding_and_parents(self):
        data = tabs({
            "ESS9": {"religion": {
                "FRK": {"1/1": 60, "2/66": 40, "7/66": 3},
                "FR10": {"1/1": 30, "2/66": 50},
                "ITC4": {"1/1": 80, "2/66": 30},
                "ITC1": {"1/1": 20, "2/66": 10},
                "AT13": {"1/1": 60, "2/66": 50},
                "HU11": {"1/1": 200},
            }, "language": {}},
            "ESS11": {"religion": {
                "FR10": {"1/1": 10, "2/66": 30, "1/6": 5},
                "FR21": {"1/1": 70, "2/66": 40},     # NUTS 2013 Champagne-Ardenne
            }, "language": {}},
            "ESS5": {"religion": {"FRF": {"1/1": 500}}, "language": {}},  # before the pool
        })
        records, report = ess.build(data, CROSSWALK, first_round=7)
        by = {r["shape_id"]: r for r in records}
        # Auvergne-Rhône-Alpes: 100 answers (3 refusals left out), n = 100.
        self.assertIn("S-ARA", by)
        self.assertEqual(by["S-ARA"]["codes"]["ess_n"]["religion"], 100)
        self.assertEqual({g["group"]: g["pct"] for g in by["S-ARA"]["religion"]},
                         {"Roman Catholic": 60.0, "No religion": 40.0})
        self.assertTrue(by["S-ARA"]["religion_basis"].startswith("survey estimate"))
        self.assertIn("3 refused", by["S-ARA"]["religion_note"])
        self.assertIn("Low precision", by["S-ARA"]["religion_note"])
        # Île-de-France pooled over two rounds through FR1 -> FR10.
        self.assertEqual(by["S-IDF"]["codes"]["ess_n"]["religion"], 125)
        self.assertEqual(by["S-IDF"]["religion_year"], 2023)
        # Grand Est from the old code, and ESS5 is outside the pool.
        self.assertEqual(by["S-GE"]["codes"]["ess_n"]["religion"], 110)
        # Lombardia at admin2 and Nord-Ovest (its NUTS 1 parent) at admin1.
        self.assertEqual(by["S-LOM"]["codes"]["ess_n"]["religion"], 110)
        self.assertEqual(by["S-NO"]["codes"]["ess_n"]["religion"], 140)
        # Weighted: ITC1 respondents weigh 1.5, ITC4 1.0.
        no = {g["group"]: g["pct"] for g in by["S-NO"]["religion"]}
        self.assertAlmostEqual(no["Roman Catholic"], 100 * (80 + 30) / (80 + 30 + 30 + 15), places=1)
        # Wien through superseded_by to the admin2 polygon and its admin1 twin.
        self.assertIn("S-WIEN2", by)
        self.assertIn("S-WIEN1", by)
        self.assertEqual(by["S-WIEN1"]["level"], "admin1")
        # Every record binds by shape id; no refused region is written.
        self.assertTrue(all(r["match_by"] == "shape_id" for r in records))
        self.assertEqual(len(records), 7)

    def test_under_threshold_left_out(self):
        data = tabs({"ESS9": {"religion": {"FRK": {"1/1": 50, "2/66": 49}}, "language": {}}})
        records, report = ess.build(data, CROSSWALK, first_round=7)
        self.assertEqual(records, [])
        self.assertTrue(any("n=99 < 100" in line for line in report))

    def test_extension_to_older_rounds(self):
        data = tabs({
            "ESS9": {"religion": {"FRK": {"1/1": 40, "2/66": 30}}, "language": {}},
            "ESS6": {"religion": {"FR71": {"1/1": 20, "2/66": 20}}, "language": {}},  # Rhône-Alpes
        })
        (rec,) = ess.build(data, CROSSWALK, first_round=7)[0]
        self.assertEqual(rec["codes"]["ess_n"]["religion"], 110)
        self.assertIn("hold only 70 respondents", rec["religion_note"])
        self.assertIn("FR71", rec["religion_note"])   # the recoded old region is named

    def test_code_whose_outline_moved(self):
        cw = {"NO02": {"superseded_by": "NO020"},
              "NO020": {"nuts_level": 3, "level": "admin1", "shape_id": "S-INN",
                        "name": "Innlandet", "iou": 0.98}}
        data = tabs({
            "ESS9": {"religion": {"NO02": {"1/2": 500}}, "language": {}},   # Hedmark og Oppland
            "ESS10": {"religion": {"NO02": {"1/2": 60, "2/66": 50}}, "language": {}},
        })
        (rec,) = ess.build(data, cw, first_round=7)[0]
        self.assertEqual(rec["codes"]["ess_n"]["religion"], 110)
        self.assertEqual(rec["religion_year"], 2020)

    def test_alemannic_by_country(self):
        self.assertEqual(ess.language_group("GSW", "CH"), "Swiss German")
        self.assertEqual(ess.language_group("GSW", "FR"), "Alsatian")
        self.assertEqual(ess.language_group("GSW", "AT"), "German")
        self.assertEqual(ess.language_group("ROH", "CH"), "Romansh")
        self.assertEqual(ess.language_group("ROH", "SK"), "Other languages")

    def test_small_languages_fold_into_other(self):
        data = tabs({"ESS9": {"religion": {}, "language": {
            "FRK": {"FRE": 180, "ARA": 12, "POR": 4, "BRE": 2, "999": 5, "APA": 2},
        }}})
        records, _ = ess.build(data, CROSSWALK, first_round=7)
        (rec,) = records
        groups = {g["group"]: g["pct"] for g in rec["language"]}
        self.assertEqual(set(groups), {"French", "Arabic", "Other languages"})
        self.assertAlmostEqual(sum(groups.values()), 100.0, delta=0.2)
        self.assertEqual(rec["codes"]["ess_n"]["language"], 200)
        self.assertNotIn("religion_note", rec)


if __name__ == "__main__":
    unittest.main()
