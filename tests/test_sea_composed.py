"""Religion and ethnicity summed onto Myanmar's composed polygons and Metro Manila's districts.

No network: the US Census Bureau's sheets are built here in their two-row-header layout.
"""

import unittest
from dataclasses import replace
from unittest import mock

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

    def test_labels_are_the_ones_uscb_publishes(self):
        # uscb.py writes the profiles' "Burmese" as "Bamar" (its relabel); the
        # sums here must carry the same label, or one people would be two.
        import dataclasses
        from unittest import mock
        sheet = burma_sheet(burma_rows())
        sheet["Ethnicity"][1] = [("Burmese" if a == "Bamar" else a)
                                 for a in sheet["Ethnicity"][1]]
        relabelled = dataclasses.replace(uscb.MYANMAR, relabel={"Burmese": "Bamar"})
        with mock.patch.object(uscb, "MYANMAR", relabelled):
            units = s.read_units(sheet, uscb.MYANMAR.topics)
            recs = {r["shape_id"]: r for r in s.myanmar(units, ADMIN1, ADMIN2)}
        self.assertEqual(pct(recs["S4"], "ethnicity"), {"Bamar": 100.0})
        self.assertEqual(pct(recs["D3"], "ethnicity"), {"Shan": 80.0, "Bamar": 20.0})

    def test_myanmar_s_relabel_is_applied_and_the_tree_files_it_there(self):
        # The profiles' "Burmese", "Indian" and "Naga" are Myanmar's Bamar,
        # its citizens of South Asian descent and its Naga; the sums here
        # carry uscb.py's labels, and each lands with Myanmar's peoples.
        import group_tree as gt
        self.assertEqual(uscb.MYANMAR.relabel, {"Burmese": "Bamar", "Indian": "Indian (Myanmar)",
                                                "Naga": "Naga (Myanmar)"})
        made = {"counts": {"Burmese": 50.0, "Naga": 30.0, "Indian": 20.0}, "published": 100.0}
        self.assertEqual(pct({"e": s.composition(made, uscb.MYANMAR.relabel)}, "e"),
                         {"Bamar": 50.0, "Naga (Myanmar)": 30.0, "Indian (Myanmar)": 20.0})
        for label in ("Bamar", "Naga (Myanmar)"):
            self.assertEqual(gt.parent_of("ethnicity", label),
                             "Tibeto-Burman peoples of China and Southeast Asia", label)
        self.assertEqual(gt.parent_of("ethnicity", "Indian (Myanmar)"),
                         "Indian (census category)")

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

    def test_each_field_carries_its_own_question(self):
        # uscb's Philippine country note is no longer the religion note, so the
        # ethnicity field states the ethnicity question, here and in uscb's own
        # province records alike.
        recs = self.build()
        self.assertIn("ethnicity", recs["N2"]["ethnicity_note"])
        self.assertNotIn("church", recs["N2"]["ethnicity_note"])
        self.assertIn("church or denomination", recs["N2"]["religion_note"])
        notes = {t.field: s.topic_note(uscb.PHILIPPINES, t) for t in uscb.PHILIPPINES.topics}
        self.assertEqual(notes["ethnicity"], uscb.PHILIPPINES_ETHNICITY_NOTE)
        self.assertEqual(notes["religion"], uscb.PHILIPPINES_RELIGION_NOTE)
        self.assertNotIn("church", uscb.PHILIPPINES.note)

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
    for rid, (name, _) in [*s.CLEAR_PHL.items(), ("PHL-CG-PH02031", ("Isabela", ""))]]
CLEAR_SHAPES = PHL2 + [{"id": "IS", "name": "Isabela"}, {"id": "CI", "name": "City of Isabela"},
                       {"id": "C1", "name": "Cotabato City"}]


class ClearLanguageTest(unittest.TestCase):
    def test_rows_bound_by_their_codes_and_cities_without_one_say_so(self):
        got = s.clear_language(CLEAR_SHAPES, CLEAR_ROWS)
        self.assertEqual(set(got), {"N1", "N2", "N3", "N4", "IS", "CI", "C1"})
        # Isabela's row is there and is not used: the polygon says why.
        self.assertEqual(got["IS"]["language"]["status"], "not_available")
        self.assertIn("PSGC 02031", got["IS"]["language"]["note"])
        self.assertIn("16.1%", got["IS"]["language"]["note"])
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

    def test_a_refused_row_the_table_no_longer_has_refuses(self):
        rows = [r for r in CLEAR_ROWS if not r["id"].endswith("PH02031")]
        with self.assertRaises(SystemExit):
            s.clear_language(CLEAR_SHAPES, rows)

    def test_a_row_under_another_name_refuses(self):
        rows = [dict(r, name="Metro Manila") if r["id"].endswith("PH13074") else r
                for r in CLEAR_ROWS]
        with self.assertRaises(SystemExit):
            s.clear_language(CLEAR_SHAPES, rows)


# --------------------------------------------------------------------------
# Myanmar's population from COD-PS: composed districts and states
# --------------------------------------------------------------------------

def codps(code, name, people):
    return code, {"code": code, "name": name, "parent": code[:6], "people": float(people)}


MMR_ROWS2 = dict([
    codps("MMR004D002", "Mindat", 72331), codps("MMR004D004", "Matupi", 167630),
    codps("MMR004D003", "Hakha", 111861),
    codps("MMR015S002", "Kokang Self-Administered Zone", 178768),
    codps("MMR016D001", "Kengtung", 507502),
    codps("MMR010D001", "Mandalay", 1875615), codps("MMR018D001", "Oke Ta Ra", 618392),
])
MMR_ROWS1 = dict([
    codps("MMR004", "Chin", 72331 + 167630 + 111861),
    codps("MMR015", "Shan (North)", 178768), codps("MMR016", "Shan (East)", 507502),
    codps("MMR010", "Mandalay", 1875615), codps("MMR018", "Nay Pyi Taw", 618392),
])
MMR_A1 = [{"id": "S1", "name": "Chin"}, {"id": "S2", "name": "Shan"},
          {"id": "S4", "name": "Mandalay"}]
MMR_A2 = [{"id": "D1", "name": "Mindat", "parent": "S1"},
          {"id": "D2", "name": "Hakha", "parent": "S1"},
          {"id": "D3", "name": "Laukkaing", "parent": "S2"},
          {"id": "D4", "name": "Kengtung", "parent": "S2"},
          {"id": "D5", "name": "Mandalay", "parent": "S4"},
          {"id": "D6", "name": "Oke Ta Ra", "parent": "S4"}]
MMR_CENSUS = {"D1": 212497, "D3": 154912}
MMR_CITE = {"field": "population", "name": "OCHA COD-PS (cod-ps-mmr-archived), reference year "
            "2023", "year": 2023}


class MyanmarPopulationTest(unittest.TestCase):
    """Finding: Mindat showed Mindat district's 72,331 beside religion and ages for
    Mindat and Matupi; Kayah's encyclopaedia figure fell below its own Loikaw."""

    def build(self, rows2=MMR_ROWS2, rows1=MMR_ROWS1, census=MMR_CENSUS):
        return s.myanmar_population(rows2, rows1, MMR_A1, MMR_A2, census, 2023, MMR_CITE)

    def test_a_composed_polygon_takes_all_its_parts(self):
        got = self.build()
        self.assertEqual(got["D1"]["population"], {"value": 239961, "year": 2023,
                                                   "source": MMR_CITE["name"]})
        self.assertIn("Mindat district (72,331) and Matupi district (167,630)",
                      got["D1"]["population_note"])
        self.assertEqual(got["D1"]["sources"], [MMR_CITE])

    def test_a_zone_drawn_as_a_district_takes_the_zone(self):
        got = self.build()
        self.assertEqual(got["D3"]["population"]["value"], 178768)
        self.assertIn("Kokang Self-Administered Zone", got["D3"]["population_note"])

    def test_a_polygon_that_is_its_own_row_is_left_to_that_row(self):
        got = self.build()
        self.assertNotIn("D2", got)
        self.assertNotIn("D4", got)

    def test_states_take_the_first_level_rows_their_districts_make(self):
        got = self.build()
        self.assertEqual(got["S1"]["population"]["value"], 351822)
        self.assertEqual(got["S2"]["population"]["value"], 178768 + 507502)
        self.assertIn("Shan (North) and Shan (East)", got["S2"]["population_note"])
        self.assertEqual(got["S4"]["population"]["value"], 1875615 + 618392)
        self.assertIn("Nay Pyi Taw", got["S4"]["population_note"])
        self.assertEqual(got["S1"]["level"], "admin1")

    def test_a_row_on_no_polygon_refuses(self):
        rows2 = dict(MMR_ROWS2)
        rows2.update([codps("MMR004D009", "Somewhere", 10)])
        with self.assertRaises(SystemExit):
            self.build(rows2=rows2)

    def test_a_polygon_no_row_reaches_refuses(self):
        rows2 = {k: v for k, v in MMR_ROWS2.items() if k != "MMR015S002"}
        rows1 = dict(MMR_ROWS1)
        rows1.pop("MMR015")
        with self.assertRaises(SystemExit):
            self.build(rows2=rows2, rows1=rows1)

    def test_a_sum_far_from_the_census_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(census={"D1": 72331, "D3": 154912})
        with self.assertRaises(SystemExit):
            self.build(census={"D3": 154912})

    def test_a_first_level_row_its_districts_do_not_make_refuses(self):
        rows1 = dict(MMR_ROWS1)
        rows1.update([codps("MMR004", "Chin", 351822 + 500)])
        with self.assertRaises(SystemExit):
            self.build(rows1=rows1)

    def test_a_part_not_in_the_polygon_s_crosswalk_refuses(self):
        s.codps_part({"code": "MMR005S001", "name": "Naga Self-Administered Zone"}, "Hkamti")
        with self.assertRaises(SystemExit):
            s.codps_part({"code": "X", "name": "Naga Self-Administered Zone"}, "Kyaukme")
        with self.assertRaises(SystemExit):
            s.codps_part({"code": "X", "name": "Kawlin"}, "Mindat")
        with self.assertRaises(SystemExit):     # the Wa division is split in two
            s.codps_part({"code": "X", "name": "Wa Self-Administered Division"}, "Hopang")
        with self.assertRaises(SystemExit):     # Hakha is one census district
            s.codps_part({"code": "X", "name": "Matupi"}, "Hakha")

    def test_every_crosswalk_row_agrees_with_composed(self):
        for code, polygon in s.MMR_CODPS_INTO.items():
            name = {"MMR004D004": "Matupi", "MMR005D011": "Kawlin",
                    "MMR005S001": "Naga Self-Administered Zone",
                    "MMR014S001": "Danu Self-Administered Zone",
                    "MMR014S002": "Pa-O Self-Administered Zone",
                    "MMR015S001": "Pa Laung Self-Administered Zone",
                    "MMR015S002": "Kokang Self-Administered Zone"}[code]
            s.codps_part({"code": code, "name": name}, polygon)

    def test_population_joins_the_polygon_s_record_or_stands_alone(self):
        pops = self.build()
        records = [{"id": "MMR-COMP-mindat", "shape_id": "D1", "religion": [],
                    "sources": [{"field": "religion"}]}]
        out = {r["shape_id"]: r for r in s.with_population(records, pops)}
        self.assertEqual(out["D1"]["population"]["value"], 239961)
        self.assertEqual([c["field"] for c in out["D1"]["sources"]], ["religion", "population"])
        self.assertEqual(out["S2"]["id"], "MMR-POP-R-shan")
        self.assertEqual(out["D3"]["id"], "MMR-POP-laukkaing")
        self.assertEqual(len(out), 5)


# --------------------------------------------------------------------------
# The Philippines: provinces drawn with a highly urbanized city inside them
# --------------------------------------------------------------------------

def phl_unit(level, region, area, religion, ethnicity=None):
    def field(counts):
        return {"counts": counts, "published": sum(counts.values())}
    return {"level": level, "adm1": region.upper(), "adm2": area.upper() if level == 2 else "",
            "adm3": "", "area": area.upper(), "where": area,
            "fields": {"religion": field(religion), "ethnicity": field(ethnicity or religion)}}


def davao_units(region_extra=0):
    sur = {"Roman Catholic": 600000, "Islam": 79457}
    city = {"Roman Catholic": 1500000, "Islam": 270988}
    norte = {"Roman Catholic": 1000000, "Islam": 115167}
    region = {k: sur[k] + city[k] + norte[k] for k in sur}
    region["Islam"] += region_extra
    return [phl_unit(1, "Davao Region", "Davao Region", region),
            phl_unit(2, "Davao Region", "Davao Del Sur", sur),
            phl_unit(2, "Davao Region", "Davao", city),
            phl_unit(2, "Davao Region", "Davao Del Norte", norte)]


PHL_HUC_SHAPES = [{"id": "DS", "name": "Davao del Sur"}, {"id": "DN", "name": "Davao del Norte"}]
ONE_HUC = {"Davao del Sur": ("Davao Region", "Davao Del Sur", (("Davao", "Davao City"),))}


class HighlyUrbanizedCityTest(unittest.TestCase):
    """Finding: Davao del Sur's shares were the province's 679,457 people alone, while
    its population, median age and sex ratio counted Davao City's 1.77 million too."""

    def build(self, units=None, counted=None, declared=(("Davao Region", "Davao"),)):
        country = replace(uscb.PHILIPPINES, no_shape=frozenset(declared))
        with mock.patch.object(s, "HUC_PROVINCES", ONE_HUC), \
                mock.patch.object(s.uscb, "PHILIPPINES", country):
            return s.huc_provinces(units or davao_units(), PHL_HUC_SHAPES,
                                   counted if counted is not None else {"DS": 2457430})

    def test_the_city_is_added_to_the_province_around_it(self):
        recs = self.build()
        self.assertEqual([r["shape_id"] for r in recs], ["DS"])
        counts = {g["group"]: g["count"] for g in recs[0]["religion"]}
        self.assertEqual(counts, {"Roman Catholic": 2100000, "Islam": 350445})
        for field in ("religion", "ethnicity"):
            note = recs[0][f"{field}_note"]
            self.assertIn("draws Davao City inside this province's polygon", note)
            self.assertIn("the city's added together", note)

    def test_every_shapeless_city_must_be_added_somewhere(self):
        with self.assertRaises(SystemExit):
            self.build(declared=(("Davao Region", "Davao"), ("Davao Region", "Tagum")))

    def test_the_province_alone_making_the_polygon_refuses(self):
        # Nothing then shows the city is inside the polygon.
        with self.assertRaises(SystemExit):
            self.build(counted={"DS": 679457})

    def test_a_sum_well_short_of_the_polygon_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(counted={"DS": 3000000})
        with self.assertRaises(SystemExit):
            self.build(counted={})

    def test_a_region_its_provinces_and_cities_do_not_make_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(units=davao_units(region_extra=5000))

    def test_the_real_list_covers_every_city_uscb_declares(self):
        declared = {c for r, c in uscb.PHILIPPINES.no_shape
                    if r != s.NCR and c not in s.NOT_CITIES}
        named = {c for _, _, cities in s.HUC_PROVINCES.values() for c, _ in cities}
        self.assertEqual(declared, named)
        self.assertEqual(len(named), 17)
        self.assertEqual(len(s.HUC_PROVINCES), 15)


if __name__ == "__main__":
    unittest.main()
