"""Religion and ethnicity summed onto Myanmar's composed polygons and Metro Manila's districts.

No network: the US Census Bureau's sheets are built here in their two-row-header layout.
"""

import unittest

from scripts.fetch_census import sea_composed as s
from scripts.fetch_census import uscb

GEO = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM3_NAME", "ADM_LEVEL"]


def burma_sheet(rows):
    """rows: (level, adm1, adm2, adm3, bamar, shan, buddhist, christian)."""
    names = GEO + ["ETH_TOTL", "ETH_BAMR", "ETH_SHAN", "RLG_TOTL", "RLG_BUDD", "RLG_CHRS"]
    aliases = ["Area", "State", "District", "Township", "Level",
               "Total population", "Bamar", "Shan", "Total population", "Buddhist",
               "Christian"]
    out = [names, aliases]
    for level, adm1, adm2, adm3, bamar, shan, budd, chri in rows:
        area = adm3 or adm2 or adm1 or "MYANMAR"
        eth = [None, None, None] if bamar is None else [bamar + shan, bamar, shan]
        out.append([area, adm1, adm2, adm3, level, *eth, budd + chri, budd, chri])
    return {"Ethnicity": out}


WA = ["HOPAN", "MONGMAO", "PANGWAUN", "MAKMAN", "NARPHAN", "PANGSANG"]
DISTRICTS = [  # (adm1, adm2, bamar, shan, buddhist, christian)
    ("CHIN STATE", "MINDAT", 10, 0, 4, 6), ("CHIN STATE", "MATUPI", 5, 0, 1, 4),
    ("SHAN STATE", "KENGTUNG", 10, 30, 35, 5),
    ("YANGON REGION", "YANGON", 90, 10, 95, 5),
    ("MANDALAY REGION", "MANDALAY", 50, 0, 49, 1),
    ("NAY PYI TAW", "OTTARA", 20, 0, 20, 0),
]


def burma_rows(wa_per_township=(2, 8, 9, 1)):
    rows = []
    states = {}
    for adm1, adm2, *v in DISTRICTS:
        rows.append((2, adm1, adm2, "", *v))
        states.setdefault(adm1, [0, 0, 0, 0])
        states[adm1] = [a + b for a, b in zip(states[adm1], v)]
    wa = [x * len(WA) for x in wa_per_township]
    rows.append((2, "SHAN STATE", "WA SELF-ADMINISTERED DIVISION", "", *wa))
    for t in WA:
        rows.append((3, "SHAN STATE", "WA SELF-ADMINISTERED DIVISION", t, *wa_per_township))
    states["SHAN STATE"] = [a + b for a, b in zip(states["SHAN STATE"], wa)]
    for adm1, v in states.items():
        rows.append((1, adm1, "", "", *v))
    union = [sum(v[i] for v in states.values()) for i in range(4)]
    rows.append((0, "", "", "", *union))
    return rows


ADMIN1 = [{"id": "S1", "name": "Chin"}, {"id": "S2", "name": "Shan"},
          {"id": "S3", "name": "Yangon"}, {"id": "S4", "name": "Mandalay"}]
ADMIN2 = [{"id": "D1", "name": "Mindat", "parent": "S1"},
          {"id": "D2", "name": "Kengtung", "parent": "S2"},
          {"id": "D3", "name": "Hopang", "parent": "S2"},
          {"id": "D4", "name": "Matman", "parent": "S2"},
          {"id": "D5", "name": "Yangon (West)", "parent": "S3"},
          {"id": "D6", "name": "Mandalay", "parent": "S4"},
          {"id": "D7", "name": "Ottara", "parent": "S4"}]


def pct(record, field):
    return {g["group"]: g["pct"] for g in record[field]}


class MyanmarTest(unittest.TestCase):
    def build(self, rows=None):
        units = s.read_units(burma_sheet(rows or burma_rows()), uscb.MYANMAR.topics)
        return {r["shape_id"]: r for r in s.myanmar(units, ADMIN1, ADMIN2)}

    def test_only_the_polygons_no_census_district_is(self):
        recs = self.build()
        self.assertEqual(set(recs), {"D1", "D3", "D4", "D5", "S4"})

    def test_mindat_takes_matupi(self):
        rec = self.build()["D1"]
        self.assertEqual(pct(rec, "religion"), {"Christian": 66.7, "Buddhist": 33.3})
        self.assertIn("Matupi district", rec["religion_note"])
        self.assertEqual(rec["ethnicity_year"], 2017)
        self.assertEqual(rec["religion_year"], 2014)

    def test_the_wa_division_splits_three_and_three(self):
        recs = self.build()
        for sid in ("D3", "D4"):
            self.assertEqual(recs[sid]["religion"][0]["count"], 3 * 9)
            self.assertEqual(pct(recs[sid], "ethnicity"), {"Shan": 80.0, "Bamar": 20.0})

    def test_mandalay_holds_nay_pyi_taw(self):
        rec = self.build()["S4"]
        self.assertEqual(rec["level"], "admin1")
        self.assertEqual(pct(rec, "ethnicity"), {"Bamar": 100.0})
        self.assertEqual(rec["religion"][0]["count"], 69)
        self.assertIn("Nay Pyi Taw", rec["religion_note"])

    def test_townships_without_ethnicity_leave_a_reason_not_a_part(self):
        # The Wa division's townships have religion and no ethnicity: its two
        # polygons say so, and the Union's ethnicity is everyone else's.
        rows = [(*r[:4], None, None, *r[6:]) if r[2] == "WA SELF-ADMINISTERED DIVISION" else r
                for r in burma_rows()]
        districts = [r for r in rows if r[0] == 2 and r[4] is not None]
        fixed = []
        for r in rows:
            if r[0] == 1 and r[1] == "SHAN STATE":
                r = (*r[:4], 10, 30, *r[6:])                    # Kengtung's alone
            if r[0] == 0:
                r = (*r[:4], sum(d[4] for d in districts), sum(d[5] for d in districts),
                     *r[6:])
            fixed.append(r)
        recs = self.build(fixed)
        for sid in ("D3", "D4"):
            self.assertNotIn("ethnicity_year", recs[sid])
            self.assertIn("carries no ethnicity figures for", recs[sid]["ethnicity"]["note"])
            self.assertIn("Hopan" if sid == "D3" else "Makman", recs[sid]["ethnicity"]["note"])
            self.assertEqual(recs[sid]["religion"][0]["count"], 27)
            self.assertEqual([s["field"] for s in recs[sid]["sources"]], ["religion"])

    def test_townships_that_do_not_make_their_division_refuse(self):
        rows = [r if not (r[0] == 3 and r[3] == "HOPAN") else (*r[:4], 3, 8, 9, 1)
                for r in burma_rows()]
        with self.assertRaises(SystemExit):
            self.build(rows)

    def test_a_union_row_the_polygons_do_not_make_refuses(self):
        rows = [r if r[0] != 0 else (*r[:4], r[4] + 5, *r[5:]) for r in burma_rows()]
        with self.assertRaises(SystemExit):
            self.build(rows)


NCR_PLACES = ["Manila", "Mandaluyong", "Marikina", "Pasig", "Quezon", "San Juan", "Caloocan",
              "Malabon", "Navotas", "Valenzuela", "Las Piñas", "Makati", "Muntinlupa",
              "Parañaque", "Pasay", "Pateros", "Taguig"]


def philippine_sheets(places=NCR_PLACES, region_extra=0):
    def sheet(cols, values):
        names = GEO + [c for c, _ in cols]
        aliases = ["Area", "Region", "Province", "", "Level"] + [a for _, a in cols]
        rows = [names, aliases]
        total = [0] * len(cols)
        for place in places:
            v = values(place)
            rows.append([place.upper(), "NATIONAL CAPITAL REGION", place.upper(), "", 2, *v])
            total = [a + b for a, b in zip(total, v)]
        total[0] += region_extra
        rows.append(["NATIONAL CAPITAL REGION", "NATIONAL CAPITAL REGION", "", "", 1, *total])
        return rows
    religion = sheet([("RLG_HPOP", "Household population"), ("RLG_RCAT", "Roman Catholic"),
                      ("RLG_INC", "Iglesia ni Cristo")], lambda p: [10000, 9000, 1000])
    ethnicity = sheet([("ETH_HPOP", "Household population"), ("ETH_TAG", "Tagalog"),
                       ("ETH_BIS", "Bisaya/Binisaya")],
                      lambda p: [10000, 10000, 0] if p != "Pateros" else [10000, 5000, 5000])
    return {"Religion": religion, "Ethnicity": ethnicity}


PHL2 = [{"id": "N1", "name": "NCR, City of Manila, First District"},
        {"id": "N2", "name": "NCR, Second District"},
        {"id": "N3", "name": "NCR, Third District"},
        {"id": "N4", "name": "NCR, Fourth District"}]


class PhilippinesTest(unittest.TestCase):
    def build(self, sheets=None):
        units = s.read_units(sheets or philippine_sheets(), uscb.PHILIPPINES.topics)
        return {r["shape_id"]: r for r in s.philippines(units, PHL2)}

    def test_three_districts_summed(self):
        recs = self.build()
        self.assertEqual(set(recs), {"N2", "N3", "N4"})
        self.assertEqual(recs["N2"]["religion"][0]["count"], 45000)
        self.assertEqual(pct(recs["N4"], "ethnicity"), {"Tagalog": 92.9, "Bisaya/Binisaya": 7.1})
        self.assertIn("Quezon City", recs["N2"]["religion_note"])

    def test_a_place_missing_from_the_districts_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(philippine_sheets(places=NCR_PLACES + ["Somewhere"]))

    def test_a_region_row_its_places_do_not_make_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(philippine_sheets(region_extra=3))

    def test_a_small_group_printed_differently_is_noted_not_refused(self):
        sheets = philippine_sheets()
        region = sheets["Ethnicity"][-1]
        region[-1], region[-2] = region[-1] + 1, region[-2] - 1   # the total stands
        self.assertEqual(set(self.build(sheets)), {"N2", "N3", "N4"})
        many = philippine_sheets()
        region = many["Ethnicity"][-1]
        region[-1], region[-2] = region[-1] + 100, region[-2] - 100
        with self.assertRaises(SystemExit):
            self.build(many)


class CotabatoCityTest(unittest.TestCase):
    def units(self, region_total):
        def unit(level, adm1, area, total):
            return {"level": level, "adm1": adm1, "adm2": area if level == 2 else "",
                    "adm3": "", "area": area, "where": area,
                    "fields": {f: {"counts": {"X": total}, "published": total}
                               for f in ("religion", "ethnicity")}}
        barmm = "BANGSAMORO AUTONOMOUS REGION IN MUSLIM MINDANAO"
        return [unit(1, barmm, barmm, region_total), unit(2, barmm, "MAGUINDANAO", 7),
                unit(2, barmm, "SULU", 3)]

    def test_no_row_says_why(self):
        shapes = {"cotabatocity": [{"id": "C1", "name": "Cotabato City"}]}
        recs = s.cotabato_city(self.units(10), ("religion", "ethnicity"), shapes)
        self.assertEqual(recs[0]["shape_id"], "C1")
        self.assertIn("Maguindanao, Sulu", recs[0]["religion"]["note"])
        self.assertNotIn("value", recs[0]["ethnicity"])

    def test_a_region_its_provinces_do_not_make_refuses(self):
        shapes = {"cotabatocity": [{"id": "C1", "name": "Cotabato City"}]}
        with self.assertRaises(SystemExit):
            s.cotabato_city(self.units(12), ("religion", "ethnicity"), shapes)


CLEAR_ROWS = [
    {"id": rid, "level": "admin2", "country": "PHL", "name": name,
     "language": [{"group": "Tagalog", "pct": 90.0}, {"group": "Cebuano", "pct": 10.0}],
     "language_year": 2010, "language_note": "Tabulated by CLEAR Global.",
     "sources": [{"field": "language", "name": "CLEAR Global"}]}
    for rid, (name, _) in s.CLEAR_PHL.items()]
CLEAR_SHAPES = PHL2 + [{"id": "IS", "name": "Isabela"}, {"id": "CI", "name": "City of Isabela"},
                       {"id": "C1", "name": "Cotabato City"}]


class ClearLanguageTest(unittest.TestCase):
    def test_rows_bound_by_their_codes_and_cities_without_one_say_so(self):
        got = s.clear_language(CLEAR_SHAPES, CLEAR_ROWS)
        self.assertEqual(set(got), {"N1", "N2", "N3", "N4", "IS", "CI", "C1"})
        self.assertEqual(got["IS"]["language"][0]["group"], "Tagalog")
        self.assertIn("PH02031", got["IS"]["language_note"])
        self.assertEqual(got["CI"]["language"]["status"], "not_available")
        self.assertIn("no row for City of Isabela", got["CI"]["language"]["note"])

    def test_merged_onto_a_record_or_written_alone(self):
        got = s.clear_language(CLEAR_SHAPES, CLEAR_ROWS)
        units = s.read_units(philippine_sheets(), uscb.PHILIPPINES.topics)
        recs = {r["shape_id"]: r for r in s.with_language(s.philippines(units, PHL2), got)}
        self.assertEqual(set(recs), {"N1", "N2", "N3", "N4", "IS", "CI", "C1"})
        # A summed district keeps its religion and gains the language and its source.
        self.assertEqual(recs["N2"]["religion"][0]["count"], 45000)
        self.assertEqual(recs["N2"]["language"][0]["group"], "Tagalog")
        self.assertIn("language", {c["field"] for c in recs["N2"]["sources"]})
        self.assertEqual(recs["N1"]["match_by"], "shape_id")

    def test_a_row_under_another_name_refuses(self):
        rows = [dict(r, name="Isabela City") if r["id"].endswith("PH02031") else r
                for r in CLEAR_ROWS]
        with self.assertRaises(SystemExit):
            s.clear_language(CLEAR_SHAPES, rows)


if __name__ == "__main__":
    unittest.main()
