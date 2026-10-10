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
    ["REGION DAKAR", 60, 40, 100, 61],
    ["DEPARTEMENT DE DAKAR", 30, 20, 50, 31],
    ["DEPARTEMENT DE PIKINE", 20, 10, 30, 20],
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
        sn.NATIONAL = 200

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
        self.assertEqual(by["D"]["population"]["value"], 100)
        self.assertEqual(by["m"]["population"]["value"], 50)
        self.assertEqual(by["m"]["sex_ratio"]["value"], round(1000 * 20 / 30))
        self.assertNotIn("p", by)


if __name__ == "__main__":
    unittest.main()
