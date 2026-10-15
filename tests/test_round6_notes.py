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


def hcp_workbook(rows):
    """HCP's legal-population sheet: title rows, two header rows, then the rows
    (name, Moroccans, foreigners, total, households, Arabic name, code)."""
    import io
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Population légale du Royaume du Maroc"])
    sheet.append(["Collectivités territoriales", "المغاربة", "الأجانب", "السكان", "الأسر", "",
                  "الرمز الجغرافي"])
    sheet.append(["", "Marocains", "Étrangers", "Population", "Ménages", "",
                  "Code géographique"])
    for row in rows:
        sheet.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def hcp(name, moroccans, foreigners, code=None):
    return (name, moroccans, foreigners, moroccans + foreigners, 1, "", code)


HCP_ROWS = [
    hcp("Ensemble du territoire national", 1150, 50),
    hcp("Région de l'Oriental", 600, 30, 2),
    hcp("Région de Laâyoune-Sakia El Hamra", 550, 20, 11),
    hcp("Ensemble du territoire national (milieu urbain)", 700, 40),
    hcp("Région de l'Oriental (milieu urbain)", 400, 25, 2),
    hcp("Ensemble du territoire national", 1150, 50),
    hcp("Région de l'Oriental", 600, 30, 2),
    hcp("Préfecture d'Oujda-Angad", 400, 20, 2411),
    hcp("Province de Taourirt", 200, 10, 2533),
    hcp("Région de Laâyoune-Sakia El Hamra", 550, 20, 11),
    hcp("Préfecture de Laâyoune", 500, 18, 11321),
    hcp("Province d'Es-Semara", 50, 2, 11221),
    hcp("Commune d'Oujda", 300, 15, 24110123),
    hcp("Cercle d'Oujda-Banlieue Nord", 100, 5, 241103),
]


class MoroccoCensusTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import morocco_rgph2024 as mr
        self.mr = mr
        self.national = mr.NATIONAL
        mr.NATIONAL = 1200

    def tearDown(self):
        self.mr.NATIONAL = self.national

    def test_the_reader_takes_regions_and_provinces_and_skips_halves_and_communes(self):
        table = self.mr.read(hcp_workbook(HCP_ROWS))
        self.assertEqual(table["national"], 1200)
        self.assertEqual(sorted(table["regions"]), [2, 11])
        self.assertEqual(sorted(table["provinces"]), [2411, 2533, 11221, 11321])
        self.assertEqual(table["provinces"][2411]["total"], 420)
        self.assertEqual(table["regions"][2]["total"], 630)

    def test_a_unit_printed_twice_with_two_totals_stops_the_run(self):
        rows = list(HCP_ROWS)
        rows[6] = hcp("Région de l'Oriental", 601, 30, 2)
        with self.assertRaises(SystemExit):
            self.mr.read(hcp_workbook(rows))

    def test_provinces_that_do_not_make_their_region_stop_the_run(self):
        rows = [r for r in HCP_ROWS if r[0] != "Province de Taourirt"]
        with self.assertRaises(SystemExit):
            self.mr.read(hcp_workbook(rows))

    def test_binding_and_the_claim_line(self):
        table = self.mr.read(hcp_workbook(HCP_ROWS))
        admin1 = [{"id": "R2", "name": "Oriental"},
                  {"id": "R11", "name": "Laâyoune-Sakia El Hamra"}]
        admin2 = [{"id": "a", "name": "Préfecture d'Oujda-Angad عمالة وجدة - أنجاد",
                   "parent": "R2"},
                  {"id": "b", "name": "Taourirte Province", "parent": "R2"},
                  {"id": "c", "name": "Province d'Es-Semara إقليم السمارة", "parent": "R11"},
                  {"id": "d", "name": "Tarfaya Province", "parent": "R11"}]
        records, report = self.mr.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["R2"]["population"]["value"], 630)
        self.assertEqual(by["a"]["population"]["value"], 420)
        # A misspelt label is paired only as each other's closest spelling.
        self.assertEqual(by["b"]["population"]["value"], 210)
        self.assertTrue(any("by spelling" in line for line in report))
        for sid in ("R11", "c"):
            for field in self.mr.FIELDS:
                cell = by[sid][field]
                self.assertNotIn("value", cell)
                self.assertEqual(cell["displaces_before"], 2025)
                self.assertIn("Western Sahara line", cell["note"])
        self.assertIn("(52 people)", by["c"]["population"]["note"])
        self.assertIn("(570)", by["R11"]["population"]["note"])
        # A polygon of the region the line cuts that is not a declared piece is left alone.
        self.assertNotIn("d", by)

    def test_aliases_join_the_boundary_files_spellings(self):
        for label, hcp_name in (("Prefecture of Mohammédia", "Préfecture de Mohammadia"),
                                ("Province de Fquih Ben Saleh", "Province de Fquih Ben Salah"),
                                ("Province d'El Kelâat Es-Sraghna",
                                 "Province d'El Kelâa Des-Sraghna"),
                                ("Rhamna Province", "Province de Rehamna"),
                                ("Prefecture of Tangier - Assilah", "Préfecture de Tanger-Assilah"),
                                ("Fez-Meknes", "Région de Fès-Meknès")):
            self.assertEqual(self.mr.key(label), self.mr.key(hcp_name), label)


ZAMBIA_LINES = [
    "TABLE 5.2:",
    "Province/District/",
    "ZAMBIA TOTAL 300 140 160 180 85 95 120 55 65",
    "WESTERN PROVINCE 200 95 105 180 85 95 20 10 10",
    "SHANG'OMBO DISTRICT 120 55 65 100 45 55 20 10 10",
    "Shangombo Central 60 30 30 50 22 28 10 8 2",
    "DISTRICT SENANGA 80 40 40 80 40 40 - - -",
    "CENTRAL PROVINCE 100 45 55 - - - 100 45 55",
    "KABWE DISTRICT 100 45 55 - - - 100 45 55",
]


class ZambiaCensusTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import zambia_census as zc
        self.zc = zc
        self.national = zc.NATIONAL
        zc.NATIONAL = 300

    def tearDown(self):
        self.zc.NATIONAL = self.national

    def test_the_table_reads_district_and_province_lines_only(self):
        table = self.zc.parse(ZAMBIA_LINES)
        self.assertEqual(sorted(table["districts"]), ["kabwe", "senanga", "shangombo"])
        self.assertEqual(table["districts"]["shangombo"]["total"], 120)
        self.assertEqual(table["districts"]["senanga"]["province"], "western")
        self.assertEqual(table["provinces"]["western"]["total"], 200)

    def test_districts_that_do_not_make_their_province_stop_the_run(self):
        lines = [line for line in ZAMBIA_LINES if "SENANGA" not in line]
        with self.assertRaises(SystemExit):
            self.zc.parse(lines)

    def test_a_line_whose_parts_do_not_add_up_stops_the_run(self):
        lines = list(ZAMBIA_LINES)
        lines[4] = "SHANG'OMBO DISTRICT 120 55 64 100 45 55 20 10 10"
        with self.assertRaises(SystemExit):
            self.zc.parse(lines)

    def test_a_preliminary_national_total_stops_the_run(self):
        self.zc.NATIONAL = 299
        with self.assertRaises(SystemExit):
            self.zc.parse(ZAMBIA_LINES)

    def test_binding_and_provinces_drawn_differently(self):
        table = self.zc.parse(ZAMBIA_LINES)
        admin1 = [{"id": "W", "name": "Western"}, {"id": "C", "name": "Central"}]
        admin2 = [{"id": "a", "name": "Shangombo", "parent": "W"},
                  {"id": "b", "name": "Senanga", "parent": "C"},
                  {"id": "c", "name": "Kabwe", "parent": "C"}]
        records, _ = self.zc.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["a"]["population"]["value"], 120)
        self.assertEqual(by["a"]["sex_ratio"]["value"], round(1000 * 55 / 65))
        # Each polygon gets what is drawn in it, and says which districts those are.
        self.assertEqual(by["W"]["population"]["value"], 120)
        self.assertIn("other than Senanga, which this map draws under Central",
                      by["W"]["population_note"])
        self.assertEqual(by["C"]["population"]["value"], 180)
        self.assertIn("and Senanga, which the census counts under Western Province",
                      by["C"]["population_note"])

    def test_a_province_whose_districts_are_drawn_whole_gets_its_own_count(self):
        table = self.zc.parse(ZAMBIA_LINES)
        admin1 = [{"id": "W", "name": "Western"}, {"id": "C", "name": "Central"}]
        admin2 = [{"id": "a", "name": "Shangombo", "parent": "W"},
                  {"id": "b", "name": "Senanga", "parent": "W"},
                  {"id": "c", "name": "Kabwe", "parent": "C"}]
        records, _ = self.zc.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["W"]["population"]["value"], 200)
        self.assertEqual(by["W"]["population_note"],
                         "The 2022 census's final count for Western Province.")

    def test_the_boundary_files_spellings_join_the_censuss(self):
        for label, census in (("Chikankanta", "CHIKANKATA DISTRICT"),
                              ("Chiengi", "CHIENGE DISTRICT"), ("Milengi", "MILENGE DISTRICT"),
                              ("Mushindano", "MUSHINDAMO DISTRICT"),
                              ("Ikelenge", "IKELENG’I DISTRICT"),
                              ("Itezhi-Tezhi", "ITEZHI TEZHI DISTRICT"),
                              ("Shiwang'Andu", "SHIWANG'ANDU DISTRICT")):
            self.assertEqual(self.zc.key(label), self.zc.key(census), label)


class GuineaBissauCensusTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import guinea_bissau_census as gb
        self.gb = gb

    def test_a_line_is_the_one_split_its_digits_and_share_allow(self):
        split = self.gb.split_line
        self.assertEqual(split("Região de Tombali 91 089 44 099 46 990 51,6"),
                         ("Região de Tombali", 91089, 44099, 46990))
        self.assertEqual(split("Bedanda - Urbano 665 302 3 63 54,6"),
                         ("Bedanda - Urbano", 665, 302, 363))
        self.assertEqual(split("Região de Quinara 60 777 29 854 30 923 51"),
                         ("Região de Quinara", 60777, 29854, 30923))
        self.assertEqual(split("68956 33431 35525 51,5"), ("", 68956, 33431, 35525))
        # A locality whose name ends in a number cannot be told apart: not read.
        self.assertIsNone(split("Sintchã Boi 1 43 19 24 55,8"))

    def test_sectors_from_their_own_lines_or_their_urban_and_rural_parts(self):
        table = self.gb.parse([
            "Região de Bafatá 300 140 160 53,3",
            "68956 33431 35525 51,5",                      # Bafatá's own line, unnamed
            "Bafatá - Urbano 100 50 50 50,0",
            "Bafatá - Rural 100 40 60 60,0",
            "Sector de Cossé 100 50 50 50,0",
            "Cossé - Rural 100 50 50 50,0",
            "Galomaro 10 5 5 50,0",
        ], "Bafatá")
        self.assertEqual(table["region"], (300, 140, 160))
        self.assertEqual(table["sectors"]["bafata"]["total"], 200)
        self.assertEqual(table["sectors"]["cosse"]["women"], 50)
        self.assertIsNone(self.gb.check(table, "Bafatá", {"bafata", "cosse"}))
        self.assertIn("make 200", self.gb.check(table, "Bafatá", {"bafata"}))

    def test_a_sector_whose_parts_do_not_make_its_line_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.gb.parse(["Sector de Buba 100 50 50 50,0", "Buba - Rural 90 45 45 50,0"],
                          "Quinara")

    def test_catio_and_komo_pool_and_caio_says_why(self):
        tables = {
            "Tombali": self.gb.parse([
                "Região de Tombali 50 24 26 52,0", "Sector de Catió 20 10 10 50,0",
                "Sector de Komo 10 4 6 60,0", "Sector de Bedanda 10 5 5 50,0",
                "Sector de Cacine 5 2 3 60,0", "Sector de Quebo 5 3 2 40,0"], "Tombali"),
            "Cacheu": self.gb.parse([
                "REGIÃO DE CACHEU 60 30 30 50,0", "Bigene - Rural 10 5 5 50,0",
                "Bula - Rural 10 5 5 50,0", "Cacheu - Rural 10 5 5 50,0",
                "Caió - Rural 10 5 5 50,0", "Canchungo - Rural 10 5 5 50,0",
                "SDomingos - Urbano 4 2 2 50,0", "São Domingos - Rural 6 3 3 50,0"], "Cacheu"),
        }
        spec = self.gb.REGIONS
        admin1 = [{"id": spec["Tombali"]["polygon"], "name": "Tombali"},
                  {"id": spec["Cacheu"]["polygon"], "name": "Cacheu"}]
        admin2 = []
        for region in ("Tombali", "Cacheu"):
            for sid in set(spec[region]["sectors"].values()) - {None}:
                admin2.append({"id": sid, "name": sid, "parent": spec[region]["polygon"]})
        for sid in self.gb.CAIO:
            admin2.append({"id": sid, "name": sid, "parent": spec["Cacheu"]["polygon"]})
        records, report = self.gb.build(tables, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        catie = by["13655514B24413703823033"]
        self.assertEqual(catie["population"]["value"], 30)
        self.assertIn("Catió and Komo", catie["population_note"])
        for sid in self.gb.CAIO:
            self.assertNotIn("value", by[sid]["population"])
            self.assertIn("Caió sector whole", by[sid]["population"]["note"])
        self.assertEqual(by[spec["Tombali"]["polygon"]]["population"]["value"], 50)
        self.assertNotIn("Bafatá: left out", " ".join(report))


TANZANIA_LINES = [
    "Table 5.0: Population Distribution by Sex, Sex Ratio, Number of Households and Average",
    "Household Size by Council, Dar es Salaam Region; 2022 PHC",
    "Dar es Salaam Region 1,000 480 520 92 300 3.3",
    "1. Kinondoni Municipal 300 140 160 88 90 3.3",
    "2. Dar es Salaam City 250 120 130 92 80 3.1",
    "3. Temeke Municipal 200 100 100 100 60 3.3",
    "4. Kigamboni Municipal 50 20 30 67 15 3.3",
    "5. Ubungo Municipal 200 100 100 100 55 3.6",
    "Table 5.1: Population Distribution by Sex, Sex Ratio, Number of Households and Average",
    "Household Size by Ward, Kinondoni Municipal Council; 2022 PHC",
    "Kinondoni Municipal Council 300 140 160 88 90 3.3",
    "1. Kawe Town 30 14 16 88 9 3.3",
    "Household Size by Council, Singida Region; 2022 PHC",
    "Singida Region 500 250 250 100 100 5.0",
    "1. Iramba District 200 100 100 100 40 5.0",
    "2. Mkalama District 300 150 150 100 60 5.0",
]


class TanzaniaCensusTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import tanzania_census as tz
        self.tz = tz
        self.national = tz.NATIONAL
        tz.NATIONAL = 1500

    def tearDown(self):
        self.tz.NATIONAL = self.national

    def test_councils_from_the_regions_tables_and_not_the_wards(self):
        table = self.tz.parse(TANZANIA_LINES)
        self.assertEqual(sorted(table["regions"]), ["daressalaam", "singida"])
        self.assertIn("ubungo municipal", table["councils"])
        self.assertNotIn("kawe town", table["councils"])
        self.assertEqual(table["unread"], {})

    def test_the_councils_made_since_are_added_to_the_ones_drawn(self):
        table = self.tz.parse(TANZANIA_LINES)
        admin1 = [{"id": "D", "name": "Dar es Salaam"}, {"id": "S", "name": "Singida"}]
        admin2 = [{"id": "k", "name": "Kinondoni", "parent": "D"},
                  {"id": "t", "name": "Temeke", "parent": "D"},
                  {"id": "i", "name": "Ilala", "parent": "D"},
                  {"id": "r", "name": "Iramba", "parent": "S"},
                  {"id": "m", "name": "Mkalama", "parent": "S"}]
        cod = {"KINONDONI": 1000, "TEMEKE": 500, "ILALA": 500, "IRAMBA": 400, "MKALAMA": 100}
        records, report = self.tz.build(table, admin1, admin2, cod)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["D"]["population"]["value"], 1000)
        self.assertEqual(by["k"]["population"]["value"], 500)
        self.assertEqual(by["t"]["population"]["value"], 250)
        self.assertIn("Ubungo", by["k"]["population_note"])
        # Iramba and Mkalama moved apart against the 2012-based projection: both left out.
        self.assertNotIn("r", by)
        self.assertNotIn("m", by)


class StatedGapsTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import stated_gaps as sg
        self.sg = sg

    def test_each_declared_polygon_gets_its_reason_on_its_fields_only(self):
        declared = self.sg.DECLARED
        try:
            self.sg.DECLARED = [
                ("COD", "admin2", "t", "Tshimbulu", self.sg.ALL, "town reason", None),
                ("IRQ", "admin2", "a", "Aqra", ("language",), "aqra reason", None)]
            units = {("COD", "admin2"): {"t": {"id": "t", "name": "Tshimbulu"}},
                     ("IRQ", "admin2"): {"a": {"id": "a", "name": "Aqra"}}}
            records, report = self.sg.build(units)
        finally:
            self.sg.DECLARED = declared
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["t"]["population"]["note"], "town reason")
        self.assertEqual(by["a"]["language"]["note"], "aqra reason")
        self.assertNotIn("note", by["a"]["population"])
        self.assertEqual(report, [])

    def test_a_reason_whose_premise_or_polygon_is_gone_is_left_out(self):
        declared = self.sg.DECLARED
        try:
            self.sg.DECLARED = [
                ("COD", "admin2", "k", "Kungu", ("language",), "r", lambda: "CLEAR has a row"),
                ("COD", "admin2", "x", "Kaoze", ("population",), "r", None)]
            units = {("COD", "admin2"): {"k": {"id": "k", "name": "Kungu"},
                                         "x": {"id": "x", "name": "Kaoze II"}}}
            records, report = self.sg.build(units)
        finally:
            self.sg.DECLARED = declared
        self.assertEqual(records, [])
        self.assertEqual(len(report), 2)

    def test_the_declared_premises_hold_on_the_files_read(self):
        for iso3, level, sid, name, fields, reason, premise in self.sg.DECLARED:
            if premise is not None:
                self.assertIsNone(premise(), name)
            for word in ("map's", "adapter", "pipeline", ".py", "build"):
                self.assertNotIn(word, reason, name)


SENEGAL_ROWS = [
    ["PROJECTION DE LA POPULATION - 2023-2050", "RGPH-5 2023", None, None, "2024"],
    [None, "HOMME", "FEMME", "ENSEMBLE", "HOMME"],
    ["REGION DAKAR", 70, 50, 120, 71],
    ["DEPARTEMENT DE DAKAR", 30, 20, 50, 31],
    ["DEPARTEMENT DE PIKINE", 20, 10, 30, 20],
    ["DEPARTEMENT DE RUFISQUE", 10, 10, 20, 10],
    ["DEPARTEMENT DE KEUR MASSAR", 10, 10, 20, 10],
    ["REGION KOLDA", 40, 60, 100, 41],
    ["DEPARTEMENT  KOLDA", 20, 30, 50, 21],
    ["DEPARTEMENT MEDINA YORO FOULAH", 20, 30, 50, 20],
]


class SenegalCensusTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import senegal_rgph5 as sn
        self.sn = sn
        self.national = sn.NATIONAL
        sn.NATIONAL = 220

    def tearDown(self):
        self.sn.NATIONAL = self.national

    def test_the_2023_columns_by_region_and_department(self):
        table = self.sn.parse(SENEGAL_ROWS)
        self.assertEqual(sorted(table["regions"]), ["dakar", "kolda"])
        self.assertEqual(table["departments"]["medinayorofoulah"]["total"], 50)
        self.assertEqual(table["departments"]["kolda"]["region"], "kolda")

    def test_departments_that_do_not_make_their_region_stop_the_run(self):
        rows = [r for r in SENEGAL_ROWS if "KEUR MASSAR" not in str(r[0])]
        with self.assertRaises(SystemExit):
            self.sn.parse(rows)

    def test_a_sheet_not_headed_2023_stops_the_run(self):
        rows = [list(r) for r in SENEGAL_ROWS]
        rows[0][1] = "2024"
        with self.assertRaises(SystemExit):
            self.sn.parse(rows)

    def test_binding_leaves_the_departments_keur_massar_was_made_from(self):
        table = self.sn.parse(SENEGAL_ROWS)
        admin1 = [{"id": "D", "name": "Dakar"}, {"id": "K", "name": "Kolda"}]
        admin2 = [{"id": "d", "name": "Dakar", "parent": "D"},
                  {"id": "p", "name": "Pikine", "parent": "D"},
                  {"id": "m", "name": "Medina Yoroufoula", "parent": "K"},
                  {"id": "k", "name": "Kolda", "parent": "K"}]
        records, _ = self.sn.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["D"]["population"]["value"], 120)
        self.assertEqual(by["m"]["population"]["value"], 50)
        self.assertEqual(by["m"]["sex_ratio"]["value"], round(1000 * 20 / 30))
        # Pikine's polygon carries no figure, and says why in front of an
        # encyclopaedia's 2023 figure for the smaller department.
        for f in ("population", "sex_ratio"):
            stated = by["p"][f]
            self.assertEqual(stated["status"], "not_available")
            self.assertEqual(stated["displaces_before"], 2024)
            self.assertIn("Pikine 30, Rufisque 20 and Keur Massar 20", stated["note"])
        self.assertNotIn("value", by["p"]["population"])


class AlbaniaMunicipalitiesTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import albania_census as al
        self.al = al
        self.named = [m for ms in al.WHOLE_2023.values() for m in ms] + \
            [m for ms in al.CROSSED_2023.values() for m in ms]

    def test_every_district_has_one_rule_and_every_municipality_one_place(self):
        al = self.al
        groups = [d for g in al.CROSSED_2023 for d in g]
        names = {name for name, _, _ in al.DISTRICTS.values()}
        self.assertEqual(len(groups) + len(al.WHOLE_2023), 36)
        self.assertEqual(set(groups) | set(al.WHOLE_2023), names)
        self.assertFalse(set(groups) & set(al.WHOLE_2023))
        self.assertEqual(len(self.named), 61)
        self.assertEqual(len(set(self.named)), 61)
        # The twelve districts that were one municipality each are still so.
        self.assertEqual(len(al.SAME_2023), 15)

    def test_tab7_must_name_every_municipality_once(self):
        al = self.al
        rows = {m: (10.0, 6.0, 4.0) for m in self.named}
        got = al.municipalities_2023(rows)
        self.assertEqual(len(got), 61)
        with self.assertRaises(SystemExit):
            al.municipalities_2023({k: v for k, v in rows.items() if k != "Dimal"})
        with self.assertRaises(SystemExit):
            al.municipalities_2023({**rows, "Nowhere": (1.0, 1.0, 0.0)})

    def test_districts_take_their_municipalities_or_say_what_crosses_them(self):
        al = self.al
        sheets = {}
        for i, sheet in enumerate(al.SHEETS_2011):
            names = [p for n, s, listed in al.DISTRICTS.values() if s == i for p in listed.split("|")]
            k = float(len(names))
            sheets[sheet] = [["t"], ["Gjithsej Total", 2 * k, 2 * k, 0, 0, k, k, 0, 0, k, k, 0, 0]] + [
                [n, 2.0, 2.0, 0, 0, 1.0, 1.0, 0, 0, 1.0, 1.0, 0, 0] for n in names]
        others = [m for m in self.named if m != "Tiranë"]
        rest = al.NATIONAL - 100 * len(others)
        munis = [["Gjithsej Total", float(al.NATIONAL), float(al.NATIONAL), 0, 0, 1_190_448.0,
                  1_190_448.0, 0, 0, 1_211_665.0, 1_211_665.0, 0, 0]]
        munis += [[m, 100.0, 100.0, 0, 0, 60.0, 60.0, 0, 0, 40.0, 40.0, 0, 0] for m in others]
        men = 1_190_448.0 - 60 * len(others)
        women = 1_211_665.0 - 40 * len(others)
        munis.append(["Tiranë", float(rest), float(rest), 0, 0, men, men, 0, 0, women, women, 0, 0])
        saved = (al.http_get, al.sheets_of, al.NATIONAL_2011, al.log)
        al.http_get = lambda url, **k: url.encode()
        al.sheets_of = lambda blob: sheets if b"3140" in blob else {"T": munis}
        al.NATIONAL_2011 = 2 * 373
        al.log = lambda *a: None
        try:
            admin1 = {s["id"]: s["name"] for s in al.shapes("ALB", "admin1")}
            recs = al.districts(admin1)
        finally:
            al.http_get, al.sheets_of, al.NATIONAL_2011, al.log = saved
        by = {r["name"]: r for r in recs}
        elbasan = by["Elbasan"]
        self.assertEqual((elbasan["population"]["value"], elbasan["population"]["year"]), (300, 2023))
        self.assertIn("municipalities of Belsh, Cërrik and Elbasan", elbasan["population_note"])
        self.assertEqual(by["Tiranë"]["population"]["value"], round(rest + 200))
        vlore = by["Vlorë"]
        self.assertEqual(vlore["population"]["year"], 2011)
        self.assertIn("together with the districts of Delvinë and Sarandë", vlore["population_note"])
        self.assertIn("700 people in 2023", vlore["population_note"])
        kruje = by["Krujë"]
        self.assertIn("together with the district of Durrës,", kruje["population_note"])
        self.assertIn("Durrës, Krujë and Shijak, 300 people", kruje["population_note"])


GHANA_AREAS = ["Ghana", "Volta", "Hohoe Municipal", "Ho Municipal", "Oti", "Guan", "Jasikan",
               "Northern", "Tamale Metropolitan Area (TMA)", "TMA-Tamale South", "TMA-Tamale Central",
               "Sagnarigu Municipal"]


def ghana_table(g, overrides=None):
    sex, age, rel, eth = {}, {}, {}, {}

    def fill(name, n):
        sex[name] = {"Both sexes": n, "Male": 0.6 * n, "Female": 0.4 * n}
        age[name] = {str(i): n / 100 for i in range(100)}
        age[name]["100+"] = 0.0
        r = {"Protestant (Anglican, Lutheran, Presbyterian, Methodist, etc.)": 0.2 * n,
             "Catholic": 0.1 * n, "Pentecostal/Charismatic": 0.3 * n, "Other Christian": 0.1 * n,
             "Islam": 0.2 * n, "Traditionalist": 0.05 * n, "No Religion": 0.03 * n,
             "Other Religion": 0.02 * n}
        rel[name] = {**r, "Christian": 0.7 * n, "Total": n}
        e = {"Akan": 0.4 * n, "Ewe": 0.3 * n, "Mole-Dagbani": 0.2 * n, "Others": 0.05 * n}
        eth[name] = {**e, "Total": 0.95 * n}

    areas = g.areas(GHANA_AREAS)
    for a in areas:
        if a["kind"] in ("district", "submetro"):
            fill(a["name"], 50.0 if a["kind"] == "submetro" else 100.0)
    for r in ("Volta", "Oti", "Northern"):
        fill(r, 200.0)
    fill("Ghana", 600.0)
    for name, (field, value) in (overrides or {}).items():
        {"religion": rel, "ethnicity": eth, "sex": sex}[field][name].update(value)
    return {"areas": areas, "sex": sex, "age": age, "religion": rel, "ethnicity": eth}


class GhanaCensusTest(unittest.TestCase):
    ADMIN1 = [{"id": "V", "name": "Volta Region"}, {"id": "O", "name": "Oti Region"},
              {"id": "N", "name": "Northern Region"}]
    ADMIN2 = [{"id": "h", "name": "Hohoe Municipal", "parent": "V"},
              {"id": "ho", "name": "Ho Municipal", "parent": "V"},
              {"id": "j", "name": "Jasikan", "parent": "O"},
              {"id": "t", "name": "Tamale Metropolitan", "parent": "N"},
              {"id": "s", "name": "Sagnerigu", "parent": "N"}]

    def setUp(self):
        from scripts.fetch_census import ghana_census as g
        self.g = g
        self.saved = (g.REGIONS, g.NATIONAL, g.log)
        g.REGIONS, g.NATIONAL, g.log = ("Volta", "Oti", "Northern"), 600, (lambda *a: None)

    def tearDown(self):
        self.g.REGIONS, self.g.NATIONAL, self.g.log = self.saved

    def test_areas_are_told_apart(self):
        kinds = {a["name"]: a["kind"] for a in self.g.areas(GHANA_AREAS)}
        self.assertEqual(kinds["Volta"], "region")
        self.assertEqual(kinds["TMA-Tamale South"], "submetro")
        self.assertEqual(kinds["Sagnarigu Municipal"], "district")
        self.assertEqual(self.g.key("Tamale Metropolitan Area (TMA)"), "tamale")
        self.assertEqual(self.g.clean("Pentecostal/ Charismatic"), "Pentecostal/Charismatic")

    def test_counts_that_do_not_add_up_stop_the_run(self):
        g = self.g
        g.check(ghana_table(g))
        for bad in ({"Ho Municipal": ("religion", {"Christian": 69.0})},
                    {"Jasikan": ("ethnicity", {"Total": 120.0, "Akan": 70.0})},
                    {"Guan": ("sex", {"Male": 61.0})}):
            with self.assertRaises(SystemExit):
                g.check(ghana_table(g, bad))

    def test_guan_is_counted_with_hohoe_and_the_regions_say_so(self):
        g = self.g
        table = ghana_table(g)
        recs = g.build(table, g.check(table), self.ADMIN1, self.ADMIN2)
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(by["h"]["population"]["value"], 200)
        self.assertIn("Guan district was made in 2019", by["h"]["population_note"])
        self.assertIn("Hohoe Municipal 100 and Guan 100", by["h"]["population_note"])
        self.assertEqual(by["V"]["population"]["value"], 300)
        self.assertIn("Volta Region's 2 districts and Guan", by["V"]["population_note"])
        self.assertEqual(by["O"]["population"]["value"], 100)
        self.assertIn("other than Guan", by["O"]["population_note"])
        self.assertEqual(by["N"]["population_note"], "The 2021 census's count for Northern Region.")
        self.assertEqual(by["s"]["population_note"], "The 2021 census's count for Sagnarigu Municipal.")
        self.assertEqual(by["s"]["sex_ratio"]["value"], 150.0)
        self.assertEqual(by["s"]["median_age"]["value"], 50.0)
        religion = {r["group"]: r["pct"] for r in by["s"]["religion"]}
        self.assertEqual(religion["Pentecostal/Charismatic"], 30.0)
        self.assertNotIn("Christian", religion)
        ethnicity = {r["group"]: r["pct"] for r in by["s"]["ethnicity"]}
        self.assertEqual(ethnicity["Other"], round(100 * 5 / 95, 1))
        self.assertIn("95 people the census counts by ethnic group here, of 100",
                      by["s"]["ethnicity_note"])

    def test_a_polygon_or_district_left_over_stops_the_run(self):
        g = self.g
        table = ghana_table(g)
        got = g.check(table)
        with self.assertRaises(SystemExit):
            g.build(table, got, self.ADMIN1, self.ADMIN2[:-1])
        with self.assertRaises(SystemExit):
            g.build(table, got, self.ADMIN1,
                    self.ADMIN2 + [{"id": "x", "name": "Nowhere", "parent": "N"}])


class SouthAfricaDistrictsTest(unittest.TestCase):
    ADMIN1 = [{"id": "K", "name": "KwaZulu-Natal"}, {"id": "W", "name": "Western Cape"},
              {"id": "N", "name": "North West"}]
    ADMIN2 = [{"id": "u", "name": "Uthungulu", "parent": "K"},
              {"id": "e", "name": "eThekwini", "parent": "K"},
              {"id": "g", "name": "Eden", "parent": "W"},
              {"id": "b", "name": "Bojanala", "parent": "N"}]
    DISTRICTS = [{"code": "DC28", "name": "King Cetshwayo", "province": "KwaZulu-Natal",
                  "men": 48, "women": 52, "total": 100},
                 {"code": "ETH", "name": "eThekwini", "province": "KwaZulu-Natal",
                  "men": 100, "women": 100, "total": 200},
                 {"code": "DC4", "name": "Garden Route", "province": "Western Cape",
                  "men": 49, "women": 51, "total": 100},
                 {"code": "DC37", "name": "Bojanala Platinum", "province": "North West",
                  "men": 60, "women": 40, "total": 101}]

    def setUp(self):
        from scripts.fetch_census import south_africa_districts as za
        self.za = za

    def test_renamed_districts_join_and_say_the_boundary_files_name(self):
        recs = self.za.records_of({"districts": self.DISTRICTS}, self.ADMIN1, self.ADMIN2)
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(by["u"]["population"]["value"], 100)
        self.assertEqual(by["u"]["population"]["year"], 2022)
        self.assertEqual(by["u"]["sex_ratio"]["value"], round(100 * 48 / 52, 1))
        self.assertIn("King Cetshwayo (the boundary file's 'Uthungulu')", by["u"]["population_note"])
        self.assertEqual(by["e"]["population_note"], "Census 2022's count for eThekwini.")
        self.assertIn("Garden Route", by["g"]["population_note"])
        self.assertEqual(by["b"]["population"]["value"], 101)          # the service's own total

    def test_a_district_on_no_polygon_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.za.records_of({"districts": self.DISTRICTS}, self.ADMIN1, self.ADMIN2[:-1])
        moved = [dict(d) for d in self.DISTRICTS]
        moved[0]["province"] = "Western Cape"
        with self.assertRaises(SystemExit):
            self.za.records_of({"districts": moved}, self.ADMIN1, self.ADMIN2)

    def test_provinces_must_be_made_by_their_districts(self):
        za = self.za
        saved = za.NATIONAL
        za.NATIONAL = 500
        try:
            provinces = {"KwaZulu-Natal": {"id": 5, "total": 300}, "Western Cape": {"id": 1, "total": 100},
                         "North West": {"id": 6, "total": 100}}
            za.check(provinces, self.DISTRICTS)
            provinces["Western Cape"]["total"] = 110
            provinces["North West"]["total"] = 100
            with self.assertRaises(SystemExit):
                za.check(provinces, self.DISTRICTS)
        finally:
            za.NATIONAL = saved


CPV_SHEET = [
    ["POPULAÇÃO RESIDENTE E AGREGADOS"],
    ["", "Zona", "Lugar", "Sexo", "População residente", "Agregados"],
    ["", "", "", "", "", "", "Menos de 15 anos"],
    ["", "BRANDÃO", "", "Total", 198.0, 41.0],
    ["", "", "", "Masculino", 107.0, 30.0],
    ["", "", "", "Feminino", 91.0, 11.0],
    ["", "", "BRANDÃO/BRANDÃOZINHO", "Total", 31.0, 5.0],
    ["", "", "", "Masculino", 14.0, 3.0],
    ["", "", "", "Feminino", 17.0, 2.0],
    ["", "", "JOÃO DA NOLY", "Total", 167.0, 36.0],
    ["", "", "", "Masculino", 93.0, 27.0],
    ["", "", "", "Feminino", 74.0, 9.0],
    ["", "CIDADE", "", "Total", 2.0, 1.0],
    ["", "", "", "Masculino", 1.0, 1.0],
    ["", "", "", "Feminino", 1.0, 0.0],
]


class CaboVerdeParishesTest(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import cabo_verde_parishes as cv
        self.cv = cv

    def test_a_parish_is_its_zones_added_up(self):
        got = self.cv.parish(CPV_SHEET, "test")
        self.assertEqual((got["total"], got["men"], got["women"], got["zones"]), (200.0, 108.0, 92.0, 2.0))
        bad = [list(r) for r in CPV_SHEET]
        bad[9][4] = 160.0                                   # the localities no longer make the zone:
        logged = []                                         # reported, and the zone's own total kept
        saved, self.cv.log = self.cv.log, logged.append
        try:
            self.assertEqual(self.cv.parish(bad, "test")["total"], 200.0)
        finally:
            self.cv.log = saved
        self.assertIn("localities make 191, not 198", logged[0])
        bad = [list(r) for r in CPV_SHEET]
        bad[4][4] = 108.0                                   # men and women no longer make it
        with self.assertRaises(SystemExit):
            self.cv.parish(bad, "test")
        # Two zones of one name are two zones (Ribeira Grande's "Cidade").
        twice = CPV_SHEET + [["", "CIDADE", "", "Total", 3.0, 1.0],
                             ["", "", "", "Masculino", 2.0, 1.0],
                             ["", "", "", "Feminino", 1.0, 0.0]]
        got = self.cv.parish(twice, "test")
        self.assertEqual((got["total"], got["zones"]), (203.0, 3.0))
        # A locality whose name cell is blank still counts as the zone's locality.
        blank = CPV_SHEET + [["", "SALTO", "", "Total", 10.0, 2.0],
                             ["", "", "", "Masculino", 6.0, 1.0],
                             ["", "", "", "Feminino", 4.0, 1.0],
                             ["", "", "", "Total", 10.0, 2.0],
                             ["", "", "", "Masculino", 6.0, 1.0],
                             ["", "", "", "Feminino", 4.0, 1.0]]
        got = self.cv.parish(blank, "test")
        self.assertEqual((got["total"], got["men"], got["zones"]), (210.0, 114.0, 3.0))

    def test_a_zone_printed_among_localities_is_a_zone_of_its_own(self):
        # Santo André's "Jorge Luis" (347) is printed in the locality column
        # under "Chã de Norte" (241): the localities before it make Chã de
        # Norte, and those after it make Jorge Luis.
        def rows(name, total, men, women, zone=False):
            first = ["", name, "", "Total", total] if zone else ["", "", name, "Total", total]
            return [first, ["", "", "", "Masculino", men], ["", "", "", "Feminino", women]]
        sheet = (CPV_SHEET + rows("CHÃ DE NORTE", 241.0, 120.0, 121.0, zone=True)
                 + rows("BORDEIRA", 41.0, 20.0, 21.0) + rows("CHÃ / LOMBINHO", 200.0, 100.0, 100.0)
                 + rows("JORGE LUIS", 347.0, 170.0, 177.0) + rows("CAVOUCO", 41.0, 20.0, 21.0)
                 + rows("LOMBO VELHO", 306.0, 150.0, 156.0))
        logged = []
        saved, self.cv.log = self.cv.log, logged.append
        try:
            got = self.cv.parish(sheet, "test")
        finally:
            self.cv.log = saved
        self.assertEqual((got["total"], got["men"], got["women"], got["zones"]),
                         (788.0, 398.0, 390.0, 4.0))
        self.assertIn("JORGE LUIS (347), printed among CHÃ DE NORTE's localities", logged[0])
        # Only when both sums close exactly: here the localities after it
        # make 346, so nothing is promoted and the mismatch is reported.
        short = sheet[:-3] + rows("LOMBO VELHO", 305.0, 150.0, 155.0)
        logged.clear()
        self.cv.log = logged.append
        try:
            got = self.cv.parish(short, "test")
        finally:
            self.cv.log = saved
        self.assertEqual((got["total"], got["zones"]), (441.0, 3.0))
        self.assertIn("CHÃ DE NORTE's localities make 934, not 241", logged[0])
        self.assertIsNone(self.cv.embedded([{"name": "", "total": 10.0},
                                            {"name": "", "total": 40.0}], 10.0))

    def test_names_and_the_one_parish_rule(self):
        cv = self.cv
        self.assertEqual(cv.key("Freguesia N.S. Conceição"), cv.key("Nossa Senhora Da Conceicao"))
        self.assertEqual(cv.key("Nossa Senhora de Ajuda"), cv.key("Nossa Senhora Da Ajuda"))
        parishes = {82: [{"code": 821, "name": "São Lourenço", "total": 1},
                         {"code": 822, "name": "N.S. Conceição", "total": 2}],
                    83: [{"code": 831, "name": "Santa Catarina", "total": 3}]}
        admin1 = [{"id": "F", "name": "São Filipe"}, {"id": "C", "name": "Santa Catarina do Fogo"}]
        admin2 = [{"id": "a", "name": "Sao Lourenco", "parent": "F"},
                  {"id": "b", "name": "Nossa Senhora Da Conceicao", "parent": "F"},
                  {"id": "c", "name": "Santa Catarina Do Fogo", "parent": "C"}]
        saved = cv.MUNICIPALITIES
        cv.MUNICIPALITIES = {82: ("São Filipe", "S. Filipe"), 83: ("Santa Catarina do Fogo", "x")}
        try:
            bound = cv.bind(parishes, admin1, admin2)
            self.assertEqual({k: v["code"] for k, v in bound.items()}, {"a": 821, "b": 822, "c": 831})
            with self.assertRaises(SystemExit):
                cv.bind({82: parishes[82][:1], 83: parishes[83]}, admin1, admin2)
        finally:
            cv.MUNICIPALITIES = saved

    def test_the_municipalities_must_be_made_by_their_parishes(self):
        cv = self.cv
        saved = (cv.MUNICIPALITIES, cv.NATIONAL, cv.log)
        cv.MUNICIPALITIES, cv.NATIONAL = {82: ("São Filipe", "S. Filipe")}, 1010
        cv.log = lambda *_: None
        country = {"total": 1010.0, "households": 1000.0}
        try:
            parishes = {82: [{"total": 400.0}, {"total": 600.0}]}
            # The parishes make the people in private households; those in
            # collective dwellings (10 here) are not in any parish.
            cv.check(parishes, {"s. filipe": {"total": 1010.0, "households": 1000.0},
                                "cabo verde": country})
            # Within half a percent of it, the difference stated, not refused.
            cv.check({82: [{"total": 404.0}, {"total": 600.0}]},
                     {"s. filipe": {"total": 1010.0, "households": 1000.0}, "cabo verde": country})
            with self.assertRaises(SystemExit):              # past half a percent
                cv.check({82: [{"total": 406.0}, {"total": 600.0}]},
                         {"s. filipe": {"total": 1010.0, "households": 1000.0},
                          "cabo verde": country})
            with self.assertRaises(SystemExit):              # a table that is not the census's
                cv.check(parishes, {"s. filipe": {"total": 1010.0, "households": 1000.0},
                                    "cabo verde": {"total": 1011.0, "households": 1000.0}})
        finally:
            cv.MUNICIPALITIES, cv.NATIONAL, cv.log = saved

    def test_a_note_says_who_the_parish_leaves_out_and_by_how_much_it_misses(self):
        cv = self.cv
        parishes = {11: [{"code": 111, "name": "Nossa Senhora do Rosário", "total": 7361.0,
                          "zones": 9.0},
                         {"code": 112, "name": "Nossa Senhora do Livramen", "truncated": True,
                          "total": 11570.0, "zones": 14.0}]}
        table = {"ribeira grande": {"total": 18890.0, "households": 18886.0}}
        note = cv.note_for(parishes[11][0], "Nossa Senhora do Rosário", parishes, table)
        self.assertEqual(note, (
            "The 2010 census's count of the people living in private households in the parish "
            "of Nossa Senhora do Rosário, its 9 zones added up. The 4 people of Ribeira Grande "
            "municipality who lived in collective dwellings are counted only for the "
            "municipality as a whole. Added up this way, Ribeira Grande's 2 parishes make "
            "18,931, 45 more than the 18,886 people in private households that INE's table "
            "by municipality gives."))
        self.assertEqual(cv.display(parishes[11][1], {"name": "Nossa Senhora Do Livramento"}),
                         "Nossa Senhora do Livramento")
        self.assertEqual(cv.display({"name": "N.S. Conceição"}, {"name": "x"}),
                         "Nossa Senhora da Conceição")
        self.assertEqual(cv.display({"name": "N.S. do Monte"}, {"name": "x"}),
                         "Nossa Senhora do Monte")
        # A cut-short sheet name binds by its beginning.
        admin1 = [{"id": "R", "name": "Ribeira Grande"}]
        admin2 = [{"id": "a", "name": "Nossa Senhora Do Rosario", "parent": "R"},
                  {"id": "b", "name": "Nossa Senhora Do Livramento", "parent": "R"},
                  {"id": "c", "name": "Santo Crucifixo", "parent": "R"}]
        three = {11: parishes[11] + [{"code": 113, "name": "Santo Crucifixo", "total": 1.0}]}
        saved = cv.MUNICIPALITIES
        cv.MUNICIPALITIES = {11: ("Ribeira Grande", "Ribeira Grande")}
        try:
            bound = cv.bind(three, admin1, admin2)
        finally:
            cv.MUNICIPALITIES = saved
        self.assertEqual({k: v["code"] for k, v in bound.items()}, {"a": 111, "b": 112, "c": 113})

    def test_the_table_by_municipality_names_its_rows_in_its_second_column(self):
        # As INE's workbook lays it out: a blank first column, the names
        # beside it, and the resident population in the fourth figure column.
        rows = [["", "Distribuição da população residente", "", "", "", "", ""],
                ["", "", "População urbana", "População rural", "Total - população residente",
                 "Residente nos agregados familiares", "Residente nos alojamentos colectivos"],
                ["", "CABO VERDE", 303673.0, 188010.0, 491683.0, 488040.0, 3643.0],
                ["", "Concelho", "", "", "", "", ""],
                ["", "Ribeira Grande", 4625.0, 14265.0, 18890.0, 18886.0, 4.0],
                ["", "Ribeira Grande de Santiago", 1214.0, 7111.0, 8325.0, 8323.0, 2.0],
                ["", "S. Filipe", 8125.0, 14103.0, 22228.0, 22227.0, 1.0],
                ["", "Fonte: INE", "", "", "", "", ""]]
        self.assertEqual(self.cv.totals(rows), {
            "cabo verde": {"total": 491683.0, "households": 488040.0},
            "ribeira grande": {"total": 18890.0, "households": 18886.0},
            "ribeira grande de santiago": {"total": 8325.0, "households": 8323.0},
            "s. filipe": {"total": 22228.0, "households": 22227.0}})

    def test_every_municipality_that_misses_is_named_at_once(self):
        cv = self.cv
        saved = (cv.MUNICIPALITIES, cv.NATIONAL, cv.log)
        cv.MUNICIPALITIES, cv.NATIONAL = {82: ("São Filipe", "S. Filipe"), 91: ("Brava", "Brava")}, 600
        cv.log = lambda *_: None
        try:
            with self.assertRaises(SystemExit) as caught:
                cv.check({82: [{"total": 100.0}], 91: [{"total": 500.0}]},
                         {"s. filipe": {"total": 200.0, "households": 200.0},
                          "brava": {"total": 400.0, "households": 400.0},
                          "cabo verde": {"total": 600.0, "households": 600.0}})
        finally:
            cv.MUNICIPALITIES, cv.NATIONAL, cv.log = saved
        self.assertIn("S. Filipe's parishes make 100", str(caught.exception))
        self.assertIn("Brava's parishes make 500", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
