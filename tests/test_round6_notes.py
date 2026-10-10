"""Round 6, notes partition: okrug splits, sub-district reads and stated reasons. No network."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import russia_municipal as rm  # noqa: E402


def okrug(name, total, men, women, parts):
    unit = {"name": name, "total": total, "men": men, "women": women, "towns": [],
            "rural": 0.0, "places": [], "parts": parts}
    unit["stems"] = rm.census_stems(unit)
    return unit


def part(urban, total, men, women, places=(), sub=()):
    return {"urban": urban, "label": "", "total": total, "men": men, "women": women,
            "places": [list(p) for p in places], "sub": [list(s) for s in sub]}


NOVOZYBKOV = okrug("Новозыбковский городской округ", 49379, 22232, 27147, [
    part(True, 38680, 17208, 21472, places=[("г.", "Новозыбков", 38680, 17208, 21472)]),
    part(False, 10699, 5024, 5675)])

VYSHNY = okrug("Вышневолоцкий городской округ", 67163, 29445, 37718, [
    part(True, 50223, 21634, 28589, sub=[("г.", "Вышний Волочек", 45830, 19693, 26137),
                                         ("пгт", "Красномайский", 4393, 1941, 2452)]),
    part(False, 16940, 7811, 9129)])

NAMES = {"t": "Novozybkov", "d": "Novozybkovsky District"}
KINDS = {"t": "city", "d": "district"}


class RussiaOkrugSplitTest(unittest.TestCase):
    def test_the_town_row_goes_to_the_town_and_the_rest_to_the_district(self):
        got = rm.split_okrug(NOVOZYBKOV, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                             NAMES, KINDS)
        self.assertIsInstance(got, tuple)
        town, rest = got
        self.assertEqual((town["total"], town["men"], town["women"]), (38680, 17208, 21472))
        self.assertEqual((rest["total"], rest["men"], rest["women"]), (10699, 5024, 5675))
        self.assertIn("Novozybkovsky District", town["own_note"])
        self.assertIn("Novozybkov,", rest["own_note"])

    def test_an_urban_type_settlement_stays_with_the_district(self):
        town, rest = rm.split_okrug(VYSHNY, "t", "d",
                                    [("t", 45830, "Вышний Волочек", "г.")], NAMES, KINDS)
        self.assertEqual(town["total"], 45830)
        self.assertEqual(rest["total"], 21333)   # 4,393 + 16,940
        self.assertIn("Красномайский (4,393)", rest["own_note"])

    def test_the_town_must_lie_in_the_town_polygon(self):
        got = rm.split_okrug(NOVOZYBKOV, "t", "d", [("d", 38680, "Новозыбков", "г.")],
                             NAMES, KINDS)
        self.assertIsInstance(got, str)
        self.assertIsInstance(rm.split_okrug(NOVOZYBKOV, "t", "d", [], NAMES, KINDS), str)

    def test_another_settlement_in_the_town_polygon_refuses(self):
        got = rm.split_okrug(NOVOZYBKOV, "t", "d",
                             [("t", 38680, "Новозыбков", "г."), ("t", 3100, "Замишево", "село")],
                             NAMES, KINDS)
        self.assertIsInstance(got, str)

    def test_two_towns_refuse(self):
        two = okrug("Орехово-Зуевский городской округ", 300, 140, 160, [
            part(True, 200, 90, 110, sub=[("г.", "А", 120, 50, 70), ("г.", "Б", 80, 40, 40)]),
            part(False, 100, 50, 50)])
        self.assertIsInstance(rm.split_okrug(two, "t", "d", [("t", 120, "А", "г.")],
                                             NAMES, KINDS), str)

    def test_rows_that_do_not_make_the_total_refuse(self):
        bad = okrug("X", 50000, 22232, 27147, NOVOZYBKOV["parts"])
        self.assertIsInstance(rm.split_okrug(bad, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                                             NAMES, KINDS), str)

    def test_a_part_far_from_the_polygons_own_figure_refuses(self):
        # Serpukhov: the rest is 1.33 times what Serpukhovsky District carries.
        got = rm.split_okrug(NOVOZYBKOV, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                             NAMES, KINDS, {"d": 7000})
        self.assertIsInstance(got, str)
        self.assertIn("times", got)
        ok = rm.split_okrug(NOVOZYBKOV, "t", "d", [("t", 38680, "Новозыбков", "г.")],
                            NAMES, KINDS, {"d": 10983, "t": None})
        self.assertIsInstance(ok, tuple)

    def test_the_polygons_must_be_a_towns_and_a_districts(self):
        self.assertIsInstance(rm.split_okrug(NOVOZYBKOV, "t", "d",
                                             [("t", 38680, "Новозыбков", "г.")], NAMES,
                                             {"t": "district", "d": "district"}), str)

    def test_a_spanning_reason_never_names_its_own_polygon(self):
        polygons = ["Ivanteyevka", "городской округ Красноарме", "Pushkinsky District"]
        held = {"городской округ Красноарме": 26492, "Pushkinsky District": 110868}
        text = rm.spanning_reason("Городской округ Пушкинский", 299385, polygons,
                                  "Pushkinsky District", held)
        self.assertIn("this one, Ivanteyevka and городской округ Красноарме.", text)
        self.assertIn("This one holds 110,868", text)
        self.assertNotIn("Pushkinsky District", text)

    @unittest.skipUnless((rm.RAW / "russia" / rm.TABLE).exists(), "workbook not checked in")
    def test_the_workbook_gives_each_okrugs_urban_and_rural_rows(self):
        table = rm.units((rm.RAW / "russia" / rm.TABLE).read_bytes())
        want = {
            "Брянская область": {"Новозыбковский городской округ": (38680, 10699),
                                 "Стародубский муниципальный округ": (17687, 17717)},
            "Ставропольский край": {"Георгиевский городской округ": (63221, 97017)},
            "Тверская область": {"Вышневолоцкий городской округ": (50223, 16940)},
            "Ярославская область": {
                "Городской округ город Переславль-Залесский": (37738, 18844)},
        }
        for subject, okrugs in want.items():
            units = {u["name"]: u for u in table[subject]["units"]}
            for name, (urban, rural) in okrugs.items():
                parts = units[name]["parts"]
                self.assertEqual([p["total"] for p in parts if p["urban"]], [urban], name)
                self.assertEqual([p["total"] for p in parts if not p["urban"]], [rural], name)
        vv = {u["name"]: u for u in table["Тверская область"]["units"]}
        sub = vv["Вышневолоцкий городской округ"]["parts"][0]["sub"]
        self.assertEqual([(s[0], s[1], s[2]) for s in sub],
                         [("г.", "Вышний Волочек", 45830), ("пгт", "Красномайский", 4393)])


class StatedReasonsTest(unittest.TestCase):
    def test_the_dambovita_piece_is_declared_against_prahova(self):
        from scripts.fetch_census import romania_census as rc
        why = rc.DETACHED[("dambovita", rc.fold(rc.bare("POIENARII BURCHII")))]
        self.assertEqual(why["county"], "Prahova")
        note = why["note"].format(people=4631, total=479404)
        self.assertIn("4,631", note)
        self.assertIn("479,404", note)
        self.assertNotIn("{", note)

    def test_the_maribor_sliver_is_kept_aside_with_its_municipality(self):
        from scripts.fetch_census import slovenia
        slivers = {}
        bound = slovenia.bind({"070": "Maribor"}, slivers)
        self.assertEqual(bound["070"]["id"], "79292919B61607630754818")
        self.assertIn("79292919B38849654156102", slivers)
        piece, main = slivers["79292919B38849654156102"]
        self.assertEqual(main["id"], "79292919B61607630754818")

    def test_a_unit_with_no_women_says_so(self):
        from scripts.fetch_census.us_island_areas import no_ratio
        self.assertIn("7 men and no women", no_ratio(7.0, 7.0, 0.0))
        self.assertIn("counts no one", no_ratio(0.0, 0.0, 0.0))

    def test_el_salvador_polygons_with_no_district_say_why(self):
        from scripts.fetch_census import el_salvador_census as es
        dept = {"id": "D1", "name": "La Paz"}
        other = {"id": "D2", "name": "Cuscatlán"}
        sons = {"id": "D3", "name": "Sonsonate"}
        admin2 = [
            {"id": "a", "name": "Olocuilta", "parent": "D1", "bbox": [0, 0, 0.1, 0.1]},
            {"id": "b", "name": "Null", "parent": "D1", "bbox": [0, 0, 0.1, 0.1]},
            {"id": "c", "name": "Jerusalén", "parent": "D2", "bbox": [0, 0, 0.1, 0.1]},
            {"id": "d", "name": "Olocuilta", "parent": "D1", "bbox": [0, 0, 0.0005, 0.0003]},
            {"id": "e", "name": "Sonsonate", "parent": "D3", "bbox": [0, 0, 0.1, 0.1]},
            {"id": "f", "name": "Null", "parent": "D3", "bbox": [0, 0, 0.1, 0.1]},
        ]
        parents = {"D1": "La Paz", "D2": "Cuscatlán", "D3": "Sonsonate"}
        places = {k: (k[:2], "x", k[2:]) for k in ("0801", "0803", "0315", "0316")}
        districts = {"0801": (places["0801"], "Olocuilta"), "0803": (places["0803"], "Jerusalén"),
                     "0315": (places["0315"], "Sonsonate"), "0316": (places["0316"], "Sonzacate")}
        pop = {places["0801"]: {"people": 30000}, places["0803"]: {"people": 2586},
               places["0315"]: {"people": 70000}, places["0316"]: {"people": 30459}}
        bound = {"0801": "a", "0803": "c"}
        departments = {"08": (("08", "", ""), "La Paz", dept), "03": (("03", "", ""), "Sonsonate", sons)}
        thin = es.slivers(admin2)
        self.assertEqual(thin, {"d"})
        out = {r["shape_id"]: r for r in es.stated_gaps(admin2, parents, thin, bound, districts,
                                                        departments, pop)}
        self.assertEqual(set(out), {"b", "d", "e", "f"})
        self.assertIn("Jerusalén's under Cuscatlán", out["b"]["population"]["note"])
        self.assertIn("Olocuilta's 30,000 people", out["d"]["ethnicity"]["note"])
        self.assertIn("100,459", out["e"]["population"]["note"])
        self.assertEqual(out["e"]["population"]["note"], out["f"]["population"]["note"])
        self.assertTrue(all(r["population"]["status"] == "not_available" for r in out.values()))
        del other


def c01_workbook(rows):
    """A C-01-shaped workbook: three title rows, then the given rows."""
    import io
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["C -1 POPULATION BY RELIGIOUS COMMUNITY - 2011"])
    sheet.append(["Table", "State", "Distt.", "Tehsil", "Town", "Area Name", "Total/"])
    sheet.append(["Name", "Code", "Code", "Code", "Code", "", "Rural/", "Total", "", "",
                  "Hindu", "", "", "Muslim", "", "", "Christian", "", "", "Sikh", "", "",
                  "Buddhist", "", "", "Jain", "", "", "Other religions and persuasions", "",
                  "", "Religion not stated"])
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def c01_row(district, tehsil, name, pop, hindu, muslim, men=None):
    men = pop // 2 + 1 if men is None else men
    women = pop - men
    groups = [(pop, men, women), (hindu, 0, 0), (muslim, 0, 0)] + [(0, 0, 0)] * 5
    groups.append((pop - hindu - muslim, 0, 0))
    cells = [v for g in groups for v in g]
    return ["C0101", "27", district, tehsil, "000000", name, "Total", *cells]


class IndiaTehsilTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import india_census as ic
        self.ic = ic
        self.split = dict(ic.TEHSIL_SPLITS[("maharashtra", "palghar")])

    def test_the_workbook_reader_keeps_district_and_tehsil_totals(self):
        blob = c01_workbook([
            c01_row("517", "00000", "District - Thane", 1000, 800, 150),
            c01_row("517", "04157", "Sub-District - Talasari", 300, 280, 10),
            c01_row("517", "04165", "Sub-District - Thane", 700, 520, 140),
            ["C0101", "27", "517", "04165", "000000", "Sub-District - Thane", "Rural",
             *([1] * 27)],
        ])
        table = self.ic.read_c01_state(blob)
        self.assertEqual(table["districts"]["517"]["Population"], 1000)
        self.assertEqual(table["tehsils"][("517", "Talasari")]["Hindus"], 280)
        self.assertEqual(set(table["tehsils"]), {("517", "Talasari"), ("517", "Thane")})

    def test_communities_that_do_not_make_the_total_stop_the_run(self):
        bad = c01_row("517", "04157", "Sub-District - Talasari", 300, 280, 10)
        bad[7 + 3 * 8] = 99   # "not stated" made wrong
        with self.assertRaises(SystemExit):
            self.ic.read_c01_state(c01_workbook([bad]))

    def test_palghar_and_thane_are_their_tehsils(self):
        import collections
        ic = self.ic
        tehsils = {"Talasari": 154818, "Dahanu": 402095, "Vikramgad": 137625,
                   "Jawhar": 140187, "Mokhada": 83453, "Vada": 178370, "Palghar": 550166,
                   "Vasai": 1343402, "Thane": 3787036, "Bhiwandi": 1141386,
                   "Shahapur": 314103, "Kalyan": 1565417, "Ulhasnagar": 506098,
                   "Ambarnath": 565340, "Murbad": 190652}
        men = sum(n // 2 + 1 for n in tehsils.values())
        rows = [c01_row("517", "00000", "District - Thane", 11060148, 11060148, 0, men)]
        rows += [c01_row("517", f"0{4157 + i}", f"Sub-District - {t}", n, n, 0)
                 for i, (t, n) in enumerate(tehsils.items())]
        table = ic.read_c01_state(c01_workbook(rows))
        whole = table["districts"]["517"]
        measured = {("maharashtra", "thane"): collections.Counter(whole)}
        thane = ic.build_record("Thane", collections.Counter(whole), level="admin2",
                                parent="IND", entity_id="IND-D517",
                                codes={"census2011_district": "517"})
        thane["parent_name"] = "Maharashtra"
        palghar = {"id": "IND-NEW-Maharashtra-Palghar", "name": "Palghar",
                   "parent_name": "Maharashtra", "language": {"status": "not_available"},
                   "ethnicity": {"status": "not_collected"},
                   "sex_ratio": {"value": 886}, "religion": [{"group": "Hindu", "pct": 100.0}]}
        out = [thane, palghar]
        original = ic.load_c01_state
        ic.load_c01_state = lambda split: c01_workbook(rows)
        try:
            ic.apply_tehsil_splits(out, measured, {})
        finally:
            ic.load_c01_state = original
        by = {r["id"]: r for r in out}
        self.assertEqual(by["IND-NEW-Maharashtra-Palghar"]["population"]["value"], 2990116)
        self.assertEqual(by["IND-D517"]["population"]["value"], 8070032)
        self.assertIn("eight tehsils", by["IND-NEW-Maharashtra-Palghar"]["religion_note"])
        self.assertNotIn("religion_estimated", by["IND-NEW-Maharashtra-Palghar"])
        self.assertEqual(by["IND-NEW-Maharashtra-Palghar"]["scheduled_groups"]["status"],
                         "not_available")

    def test_without_the_workbook_the_carried_figures_come_off(self):
        ic = self.ic
        new = {"id": "n", "sex_ratio": {"value": 886}, "sex_ratio_note": "x",
               "religion": [{"group": "Hindu", "pct": 78.8}], "religion_estimated": True,
               "scheduled_groups": [{"group": "Scheduled Tribe", "pct": 13.9}]}
        old = {"id": "o", "sex_ratio": {"value": 886}, "religion": [{"group": "Hindu"}]}
        ic.withdraw_carried(new, old, self.split)
        for r in (new, old):
            self.assertEqual(r["sex_ratio"]["status"], "not_available")
            self.assertEqual(r["religion"]["status"], "not_available")
        self.assertNotIn("religion_estimated", new)
        self.assertEqual(new["scheduled_groups"]["status"], "not_available")


if __name__ == "__main__":
    unittest.main()
