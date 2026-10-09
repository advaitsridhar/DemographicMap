"""Kuwait's 2021 register-based census, read from workbook rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import kuwait_census as kc  # noqa: E402

GOVS = list(kc.GOVERNORATES)
# Per governorate: Kuwaiti men/women, other men/women.
PEOPLE = {g: (100 + i, 110 + i, 300 + 10 * i, 100 + 5 * i) for i, g in enumerate(GOVS)}


def gov_label(g):
    return f"{g} Governorate"


def t1():
    rows = [[None, "x", "Kuwaiti", None, None, "Non-Kuwaiti"]]
    tot = [0] * 9
    for g in GOVS:
        km, kf, nm, nf = PEOPLE[g]
        cells = [km, kf, km + kf, nm, nf, nm + nf, km + nm, kf + nf, km + kf + nm + nf]
        tot = [a + b for a, b in zip(tot, cells)]
        rows.append([None, "عربي"] + cells + [gov_label(g)])
    rows.append([None, "الجملة"] + tot + ["Total"])
    return rows, tot[8]


BANDS = [f"{a}-{a + 4}" for a in range(0, 85, 5)] + ["> 84"]


def split(total, parts):
    base = [total // parts] * parts
    base[-1] += total - sum(base)
    return base


def t2():
    rows = [[None, "x", "x", "The Capital Governorate"]]
    per = {g: (split(sum(PEOPLE[g][0::2]), len(BANDS)), split(sum(PEOPLE[g][1::2]), len(BANDS)))
           for g in GOVS}
    for i, band in enumerate(BANDS):
        men = [per[g][0][i] for g in GOVS]
        women = [per[g][1][i] for g in GOVS]
        rows.append([None, band, "ذكر"] + men + [0, sum(men), "Male", band])
        rows.append([None, None, "انثى"] + women + [0, sum(women), "Female"])
        both = [m + w for m, w in zip(men, women)]
        rows.append([None, None, "الجملة"] + both + [0, sum(both), "Total"])
    return rows


def t6():
    rows = [[None, "x", "x", "Gulf", "Arabic", "Asian", "African", "European",
             "North America", "South America", "Australian", "Total"]]
    for g in GOVS:
        km, kf, nm, nf = PEOPLE[g]
        total = km + kf + nm + nf
        groups = [km + kf + 5, nm + nf - 5 - 3, 1, 1, 1, 0, 0, 0]
        rows.append([None, "عربي", "ذكر"] + [0] * 9 + ["Male", gov_label(g)])
        rows.append([None, None, "الجملة"] + groups + [total, "Total"])
    rows.append([None, "غير مبين", "ذكر"] + [0] * 9 + ["Male", "Not Stated"])
    rows.append([None, None, "الجملة"] + [0] * 9 + ["Total"])
    return rows


AREAS = {"The Capital": ["DASMAN", "AL-SHARQ"], "Hawalli": ["HAWALLI"],
         "Al-Ahmadi": ["AL-FAHAHEEL"], "Al-Jahra": ["AL-JAHRA", "AL-NAHDA"],
         "Al-Farwaniya": ["KHAITAN"], "Mubarak Al-Kabeer": ["AL-ADAN"]}


def t52(break_sum=False):
    rows = [[None, "Kuwaiti", None, None, "Non-Kuwaiti"]]
    for g in GOVS:
        km, kf, nm, nf = PEOPLE[g]
        names = AREAS[g]
        for j, name in enumerate(names):
            share = 1 if len(names) == 1 else (2 if j == 0 else None)
            if share == 1:
                parts = (km, kf, nm, nf)
            elif share == 2:
                parts = (km // 2, kf // 2, nm // 2, nf // 2)
            else:
                parts = (km - km // 2, kf - kf // 2, nm - nm // 2, nf - nf // 2)
            a, b, c, d = parts
            if break_sum and name == "DASMAN":
                a += 1
                cells = [a, b, a + b, c, d, c + d, a + c, b + d, a + b + c + d]
            else:
                cells = [a, b, a + b, c, d, c + d, a + c, b + d, a + b + c + d]
            rows.append(["عربي"] + cells + [name])
    rows.append(["غير مبين", 0, 0, 0, 0, 0, 0, 0, 0, 0, "NOT STATED"])
    return rows


ADMIN1 = [{"id": f"g{i}", "name": lab, "parent": "KWT"}
          for i, lab in enumerate(kc.GOVERNORATES.values())]
PARENTS = {u["id"]: u["name"] for u in ADMIN1}
ADMIN2 = [{"id": "a1", "name": "Dasman", "parent": "g0"},
          {"id": "a2", "name": "Sharq", "parent": "g0"},
          {"id": "a3", "name": "Hawalli", "parent": "g1"},
          {"id": "a4", "name": "Elnahda_Shark_Elsolybekhat", "parent": "g0"},
          {"id": "a5", "name": "Mina_Doha", "parent": "g0"},
          {"id": "a6", "name": "Mina_Doha", "parent": "g0"}]


PLACED = {
    "DASMAN": {"osm": ["r1"], "shares": {"a1": 0.95, "a2": 0.05}},
    "AL-SHARQ": {"osm": ["r2"], "shares": {"a2": 0.97, "a1": 0.03}},
    "HAWALLI": {"osm": ["r3"], "shares": {"a3": 1.0}},
    # Outlined, but off the drawn land: nobody to count anywhere drawn.
    "AL-FAHAHEEL": {"osm": ["r4"], "shares": {}},
    "AL-JAHRA": {"osm": ["r5"], "shares": {}},
    "AL-NAHDA": {"osm": ["r6"], "shares": {"a4": 0.10, "a5": 0.90}},
    "KHAITAN": {"osm": ["r7"], "shares": {}},
    "AL-ADAN": {"osm": ["r8"], "shares": {}},
}


class TheReader(unittest.TestCase):
    def setUp(self):
        self.saved = kc.NATIONAL
        kc.NATIONAL = t1()[1]

    def tearDown(self):
        kc.NATIONAL = self.saved

    def run_it(self, placed=None, **kw):
        return kc.build(t1()[0], t2(), t6(), t52(**kw), ADMIN1, ADMIN2, PARENTS,
                        PLACED if placed is None else placed)

    def test_governorates_carry_population_sex_age_and_nationality(self):
        out = {r["shape_id"]: r for r in self.run_it()}
        cap = out["g0"]
        km, kf, nm, nf = PEOPLE["The Capital"]
        self.assertEqual(cap["population"]["value"], km + kf + nm + nf)
        self.assertEqual(cap["sex_ratio"]["value"], round(100 * (km + nm) / (kf + nf), 1))
        self.assertIsNotNone(cap["median_age"])
        groups = {s["group"]: s["count"] for s in cap["ethnicity"]}
        self.assertEqual(groups["Kuwaiti"], km + kf)
        self.assertEqual(groups["GCC nationals"], 5)
        self.assertNotIn("Australian", kc.GROUPS.values())
        self.assertIn("Oceanian nationalities", kc.GROUPS.values())

    def test_areas_are_bound_by_their_ground(self):
        out = {r["shape_id"]: r for r in self.run_it()}
        self.assertEqual(out["a1"]["ethnicity_basis"], "nationality")
        self.assertIn("95%", out["a1"]["population"]["note"])
        # Al-Nahda's ground is a5's, not the sliver a4 drawn under its name;
        # a5 is drawn in the Capital, the census counts Al-Nahda in Al-Jahra.
        self.assertEqual(out["a4"]["population"]["status"], "not_available")
        self.assertIn("Jahra", out["a5"]["population"]["note"])
        self.assertIn("No census area", out["a4"]["population"]["note"])

    def test_a_polygon_holding_too_many_others_is_refused(self):
        placed = dict(PLACED, **{"AL-SHARQ": {"shares": {"a2": 0.8, "a1": 0.2}}})
        out = {r["shape_id"]: r for r in self.run_it(placed)}
        # Dasman's polygon would also hold a fifth of Al-Sharq's people.
        self.assertEqual(out["a1"]["population"]["status"], "not_available")
        self.assertIn("Al-Sharq", out["a1"]["population"]["note"])
        self.assertEqual(out["a2"]["population"]["status"] if "status" in out["a2"]["population"]
                         else "value", "value")

    def test_an_area_marked_only_by_a_point_counts_whole_where_the_point_is(self):
        placed = dict(PLACED, **{"AL-SHARQ": {"osm": [], "shares": {}, "points": {"n9": "a1"}}})
        out = {r["shape_id"]: r for r in self.run_it(placed)}
        self.assertEqual(out["a1"]["population"]["status"], "not_available")
        self.assertIn("OpenStreetMap places it here by a point", out["a1"]["population"]["note"])
        # Hawalli's polygon is not near the point.
        self.assertIn("value", out["a3"]["population"])

    def test_an_area_neither_outlined_nor_marked_may_be_anywhere_in_its_governorate(self):
        placed = dict(PLACED, **{"AL-SHARQ": {"osm": [], "shares": {}, "points": {}}})
        out = {r["shape_id"]: r for r in self.run_it(placed)}
        # Every polygon of the Capital may hold Al-Sharq's people ...
        self.assertEqual(out["a1"]["population"]["status"], "not_available")
        self.assertIn("may be in any polygon", out["a1"]["population"]["note"])
        self.assertEqual(out["a5"]["population"]["status"], "not_available")
        # ... and none of Hawalli's does.
        self.assertIn("value", out["a3"]["population"])

    def test_areas_sharing_a_home_are_summed(self):
        placed = dict(PLACED, **{"DASMAN": {"shares": {"a2": 0.9, "a1": 0.1}}})
        out = {r["shape_id"]: r for r in self.run_it(placed)}
        cap = PEOPLE["The Capital"]
        self.assertEqual(out["a2"]["population"]["value"], sum(cap))
        self.assertIn("sum of the census's areas", out["a2"]["population"]["note"])

    def test_small_counts_carry_no_ratio_or_share(self):
        b = {"names": ["X"], "shares": {"X": 1.0}, "stray": 0}
        areas = {"X": {"total": 3, "men": 1, "women": 2, "kuwaiti": 1, "other": 2,
                       "other_men": 1, "other_women": 1}}
        fields = kc.area_fields(["X"], areas, b, 2000, 1000)
        self.assertEqual(fields["population"]["value"], 3)
        self.assertIn("1 man and 2 women", fields["population"]["note"])
        self.assertEqual(fields["sex_ratio"]["status"], "not_available")
        self.assertEqual(fields["ethnicity"]["status"], "not_available")

    def test_a_skewed_ratio_says_it_is_the_count(self):
        b = {"names": ["X"], "shares": {"X": 1.0}, "stray": 0}
        areas = {"X": {"total": 2600, "men": 2450, "women": 150, "kuwaiti": 0, "other": 2600,
                       "other_men": 2450, "other_women": 150}}
        fields = kc.area_fields(["X"], areas, b, 1_941_628, 955_373)
        self.assertGreater(fields["sex_ratio"]["value"], 1000)
        self.assertIn("not an error", fields["sex_ratio_note"])

    def test_an_area_with_no_placement_entry_stops_the_run(self):
        placed = {k: v for k, v in PLACED.items() if k != "HAWALLI"}
        with self.assertRaises(SystemExit):
            self.run_it(placed)

    def test_an_area_whose_cells_do_not_add_up_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.run_it(break_sum=True)

    def test_a_national_total_that_does_not_match_stops_the_run(self):
        kc.NATIONAL += 1
        with self.assertRaises(SystemExit):
            self.run_it()


def square(x0, y0, x1, y1):
    return [{"lon": x0, "lat": y0}, {"lon": x1, "lat": y0}, {"lon": x1, "lat": y1},
            {"lon": x0, "lat": y1}, {"lon": x0, "lat": y0}]


class TheGround(unittest.TestCase):
    def setUp(self):
        from shapely.geometry import box
        drawn = {"p1": box(0, 0, 1, 1), "p2": box(1, 0, 2, 1)}
        labels = {"p1": "One", "p2": "Two"}
        # An area three quarters in p1, a quarter in p2, and as much again at
        # sea (beyond every drawn polygon), which does not count.
        elements = [
            {"type": "way", "id": 1, "tags": {"name": "المسايل", "boundary": "administrative",
                                              "admin_level": "6"},
             "geometry": square(0.25, -1, 1.25, 1)},
            {"type": "way", "id": 2, "tags": {"name": "الصليبخات", "place": "suburb"},
             "geometry": square(0, 0, 0.5, 1)},
            # Ahmadi City is only a point in OSM, under the city's name.
            {"type": "node", "id": 3, "lon": 1.5, "lat": 0.5,
             "tags": {"name": "الأحمدي", "place": "city"}},
        ]
        areas = {"AL-MASAYEL": {"ar": "المسايل", "governorate": "Hawalli"},
                 "AL-SULAIBIKHAT": {"ar": "الصليبيخات", "governorate": "Hawalli"},
                 "AL-AHMADI CITY": {"ar": "مدينة الأحمدي", "governorate": "Hawalli"},
                 "NOWHERE": {"ar": "لا مكان", "governorate": "Hawalli"},
                 "DESERT": {"ar": "بر محافظة حولي", "governorate": "Hawalli"},
                 # Neither outlined nor marked in OSM: placed by GeoNames.
                 "AL-MISILA": {"ar": "المسيلة", "governorate": "Hawalli"}}
        self.placed = kc.ground(areas, elements, drawn, labels, {"g": box(0, 0, 2, 1)},
                                {"g": "Hawalli"})

    def test_shares_are_measured_on_drawn_land(self):
        placed = self.placed
        self.assertAlmostEqual(placed["AL-MASAYEL"]["shares"]["p1"], 0.75, places=3)
        self.assertAlmostEqual(placed["AL-MASAYEL"]["shares"]["p2"], 0.25, places=3)
        self.assertEqual(placed["AL-MASAYEL"]["osm"], ["w1"])
        self.assertAlmostEqual(placed["AL-MASAYEL"]["admin1"]["g"], 1.0, places=3)
        # Spelt otherwise in OSM, found through the declared name.
        self.assertAlmostEqual(placed["AL-SULAIBIKHAT"]["shares"]["p1"], 1.0, places=3)
        self.assertEqual(placed["NOWHERE"]["osm"], [])
        self.assertEqual(placed["NOWHERE"]["points"], {})
        self.assertEqual(kc.osm_url("r18005317"),
                         "https://www.openstreetmap.org/relation/18005317")

    def test_an_area_with_no_outline_is_placed_by_its_point(self):
        self.assertEqual(self.placed["AL-AHMADI CITY"]["shares"], {})
        self.assertEqual(self.placed["AL-AHMADI CITY"]["points"], {"n3": "p2"})

    def test_an_area_osm_does_not_know_falls_back_to_geonames(self):
        points = self.placed["AL-MISILA"]["points"]
        self.assertEqual(len(points), 2)
        self.assertTrue(all(p.startswith("geonames:") for p in points))
        # Kuwait's coordinates lie in neither test polygon.
        self.assertEqual(set(points.values()), {None})

    def test_a_desert_is_the_governorate_less_every_outline(self):
        desert = self.placed["DESERT"]
        self.assertTrue(desert["desert"])
        # Outlines cover x 0-1.25; the rest, x 1.25-2, is all in p2.
        self.assertAlmostEqual(desert["shares"]["p2"], 1.0, places=3)
        self.assertNotIn("p1", desert["shares"])


class TheArabicNames(unittest.TestCase):
    def test_spellings_fold_together(self):
        self.assertEqual(kc.fold_ar("ضاحية عبدالله السالم"), kc.fold_ar("ضاحية عبد الله السالم"))
        self.assertEqual(kc.fold_ar("أبو حليفة"), kc.fold_ar("ابو حليفة"))
        self.assertEqual(kc.fold_ar("القرية"), kc.fold_ar("القريه"))


if __name__ == "__main__":
    unittest.main()
