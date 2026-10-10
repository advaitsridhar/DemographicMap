"""Myanmar: median age and sex ratio by drawn district from the 2014 census.

No network: census rows are built here as read_rows() returns them.
"""

import unittest
from unittest import mock

from scripts.fetch_census import myanmar_age as m

BANDS = [(a, a + 4) for a in range(0, 75, 5)] + [(75, None)]


def unit(level, adm1, adm2="", adm3="", per_band=10, men=None):
    groups = [(a, b, per_band) for a, b in BANDS]
    total = per_band * len(BANDS)
    men = total // 2 if men is None else men
    return {"level": level, "adm1": adm1, "adm2": adm2, "adm3": adm3, "nso": "",
            "total": total, "men": men, "women": total - men, "groups": groups,
            "where": " / ".join(x for x in (adm1, adm2, adm3) if x)}


ROWS = [
    unit(2, "CHIN STATE", "MINDAT"), unit(2, "CHIN STATE", "MATUPI"),
    unit(2, "SHAN STATE", "KENGTUNG"),
    unit(2, "SHAN STATE", "WA SELF-ADMINISTERED DIVISION", per_band=60),
    *[unit(3, "SHAN STATE", "WA SELF-ADMINISTERED DIVISION", t)
      for t in ("HOPAN", "MONGMAO", "PANGWAUN", "MAKMAN", "NARPHAN", "PANGSANG")],
]
ADMIN2 = [{"id": "D1", "name": "Mindat", "parent": "S1"},
          {"id": "D2", "name": "Kengtung", "parent": "S2"},
          {"id": "D3", "name": "Hopang", "parent": "S2"},
          {"id": "D4", "name": "Matman", "parent": "S2"}]
ADMIN1 = [{"id": "S1", "name": "Chin"}, {"id": "S2", "name": "Shan"}]


class ZoneTest(unittest.TestCase):
    def test_zone_names(self):
        self.assertEqual(m.zone_of("PAO SELF-ADMINISTERED ZONE"), "PAO")
        self.assertEqual(m.zone_of("WA SELF-ADMINISTERED DIVISION"), "WA")
        self.assertIsNone(m.zone_of("HKAMTI"))


class ComposeTest(unittest.TestCase):
    def compose(self, rows=ROWS, admin2=ADMIN2):
        with mock.patch.object(m, "NATIONAL", sum(r["total"] for r in rows if r["level"] == 2)):
            return m.compose(rows, admin2)

    def test_old_districts_take_the_new_ones_and_the_zone_splits(self):
        figs = self.compose()
        self.assertEqual(figs["D1"]["total"], 2 * 160)          # Mindat + Matupi
        self.assertEqual(figs["D3"]["total"], 3 * 160)          # three Wa townships
        self.assertEqual(figs["D4"]["total"], 3 * 160)
        self.assertEqual(figs["D2"]["kind"], "district")

    def test_a_census_unit_left_over_refuses(self):
        rows = ROWS + [unit(2, "SHAN STATE", "MONG HPAYAK")]
        with self.assertRaises(SystemExit):
            self.compose(rows)

    def test_a_polygon_with_no_census_district_refuses(self):
        admin2 = ADMIN2 + [{"id": "D5", "name": "Nowhere", "parent": "S2"}]
        with self.assertRaises(SystemExit):
            self.compose(admin2=admin2)


class BuildTest(unittest.TestCase):
    def test_records_and_region_sums(self):
        with mock.patch.object(m, "NATIONAL", sum(r["total"] for r in ROWS if r["level"] == 2)):
            recs = m.build(ROWS, ADMIN1, ADMIN2)
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(set(by), {"D1", "D2", "D3", "D4", "S1", "S2"})
        # 16 equal groups to 75+: the middle person is at the end of 35-39.
        self.assertEqual(by["D2"]["median_age"]["value"], 40.0)
        self.assertEqual(by["D2"]["sex_ratio"]["value"], 100.0)
        self.assertEqual(by["D1"]["population"]["value"], 320)
        self.assertIn("Matupi district", by["D1"]["median_age_note"])
        self.assertIsNone(by["S2"]["population"].get("value"))


if __name__ == "__main__":
    unittest.main()
