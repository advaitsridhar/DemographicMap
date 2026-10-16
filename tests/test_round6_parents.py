"""Round 6, parents: which first-level unit a second-level polygon is filed under.

Polygons filed where their census counts them (DECLARED_PARENTS) in Bhutan,
Saudi Arabia, Uzbekistan, Iraq, Argentina, Malawi, Madagascar, Namibia, the
Dominican Republic, Suriname, the Bahamas and Portugal; Seychelles' second
level, which is not inside its first, and Belgium's Brussels polygon, which
has no first-level parent, left under their country; counts that take in
units the map does not draw (UNDRAWN_PARTS), with the build stopping where
the count and its divisions are of different years; Vanuatu's second level
declared partial; and the readers that say where the map files a district
reading the next build's parents (declared_parents.as_filed), with the notes
Nepal, Saudi Arabia, the Federated States of Micronesia, Tuvalu and
Argentina's Buenos Aires polygon now carry. No network.
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
from scripts.fetch_census import argentina_census as ac  # noqa: E402
from scripts.fetch_census import declared_parents as dp  # noqa: E402
from scripts.fetch_census import micronesia_census as fm  # noqa: E402
from scripts.fetch_census import nepal  # noqa: E402
from scripts.fetch_census import saudi_census as sc  # noqa: E402
from scripts.fetch_census import tuvalu_census as tv  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SITE = ROOT / "site" / "data"

# Words a visitor's note has no use for: the pipeline's own names for things.
INTERNAL = ("DECLARED", "UNDRAWN", "PARTIAL", "build", ".py", "adapter", "pipeline",
            "agent", "owner", "shape_id", "processed")


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def site_units(level, iso3):
    path = SITE / level / f"{iso3}.units.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def rows_of(name):
    data = json.loads((PROCESSED / name).read_text(encoding="utf-8"))
    return data["rows"] if isinstance(data, dict) and "rows" in data else data


class Plain(unittest.TestCase):
    def assertPlain(self, text):
        for word in INTERNAL:
            self.assertNotIn(word, text)


# ---------------------------------------------------------------------------
# DECLARED_PARENTS
# ---------------------------------------------------------------------------

class DeclaredWhereCounted(unittest.TestCase):
    def test_every_misfiled_polygon_of_the_items_is_declared(self):
        wanted = {
            "BTN": 17, "SAU": 1, "UZB": 3, "IRQ": 4, "ARG": 14, "MWI": 1, "MDG": 1,
            "NAM": 1, "DOM": 5, "SUR": 3, "BHS": 2, "PRT": 5}
        got = {}
        for iso3, _label in be.DECLARED_PARENTS.values():
            got[iso3] = got.get(iso3, 0) + 1
        for iso3, n in wanted.items():
            self.assertEqual(got.get(iso3), n, iso3)

    def test_a_census_that_names_its_districts_parents_agrees_with_each_declaration(self):
        # INDEC, the ONE and INE each name the province or district they
        # count a unit in; a declared polygon must be filed under that one.
        checked = 0
        for name in ("argentina_census.json", "dominican_census.json",
                     "portugal_census.json"):
            if not (PROCESSED / name).exists():
                continue
            for row in rows_of(name):
                declared = be.DECLARED_PARENTS.get(row.get("shape_id"))
                if declared and row.get("level") == "admin2":
                    self.assertEqual(declared, (row["country"], row["parent_name"]),
                                     row["name"])
                    checked += 1
        if not checked:
            self.skipTest("no census rows for these countries in this checkout")
        self.assertGreaterEqual(checked, 24)

    def test_suriname_s_rows_are_the_census_district_they_are_declared_under(self):
        # suriname_census names each ressort's row by the district the 2012
        # census counts it in: SUR-ABS-<district>-<ressort>.
        if not (PROCESSED / "suriname_census.json").exists():
            self.skipTest("no Suriname census rows in this checkout")
        found = {}
        for row in rows_of("suriname_census.json"):
            declared = be.DECLARED_PARENTS.get(row.get("shape_id"))
            if declared:
                found[row["id"].split("-")[2]] = declared[1].lower()
        self.assertEqual(sorted(found.items()), [("paramaribo", "paramaribo"),
                                                 ("wanica", "wanica")])

    def test_link_leaves_an_unnested_country_and_an_unparented_polygon_under_the_country(self):
        from shapely.geometry import box
        adm1 = [{"group": g, "shape_id": f"{g}-1", "name": "One", "_geom": box(0, 0, 10, 10)}
                for g in ("SYC", "BEL", "XXX")]
        adm2 = [{"group": "SYC", "shape_id": "S", "point": [5, 5], "bbox": [4, 4, 6, 6]},
                {"group": "BEL", "shape_id": "21686613B18913386279163", "point": [5, 5],
                 "bbox": [4, 4, 6, 6]},
                {"group": "XXX", "shape_id": "X", "point": [5, 5], "bbox": [4, 4, 6, 6]}]
        quiet(be.link_adm2_parents, adm1, adm2)
        self.assertEqual([r["parent_shape"] for r in adm2], [None, None, "XXX-1"])

    def test_declaring_a_parent_for_a_unit_that_has_none_stops_the_build(self):
        adm1 = [{"group": "SYC", "name": "Takamaka", "shape_id": "T"}]
        adm2 = [{"group": "SYC", "name": "East Mahe", "shape_id": "E", "parent_shape": None}]
        with self.assertRaises(SystemExit):
            quiet(be.declare_parents, adm1, adm2, {"E": ("SYC", "Takamaka")})
        adm1 = [{"group": "BEL", "name": "Brussels Hoofdstedelijk", "shape_id": "B"}]
        adm2 = [{"group": "BEL", "name": "Brussels", "shape_id": "21686613B18913386279163",
                 "parent_shape": None}]
        with self.assertRaises(SystemExit):
            quiet(be.declare_parents, adm1, adm2,
                  {"21686613B18913386279163": ("BEL", "Brussels Hoofdstedelijk")})

    def test_seychelles_and_brussels_are_not_declared_anywhere(self):
        self.assertIn("SYC", be.NOT_NESTED)
        self.assertNotIn("SYC", {iso3 for iso3, _ in be.DECLARED_PARENTS.values()})
        self.assertNotIn("21686613B18913386279163", be.DECLARED_PARENTS)


# ---------------------------------------------------------------------------
# declared_parents.as_filed, and the readers that use it
# ---------------------------------------------------------------------------

class AsFiled(unittest.TestCase):
    def test_a_declared_polygon_takes_its_declared_parent_and_the_rest_keep_theirs(self):
        a1 = [{"id": "T", "name": "Tashkent"}, {"id": "R", "name": "Tashkent Region"}]
        a2 = [{"id": "79887680B40109116454398", "name": "Bektemir", "parent": "R"},
              {"id": "Z", "name": "Zangiata", "parent": "R"}]
        filed = dp.as_filed("UZB", a1, a2)
        self.assertEqual([u["parent"] for u in filed], ["T", "R"])
        self.assertEqual(a2[0]["parent"], "R")          # copies, not the caller's units

    def test_an_unnested_or_unparented_polygon_is_filed_under_its_country(self):
        self.assertEqual(dp.as_filed("SYC", [{"id": "D", "name": "Takamaka"}],
                                     [{"id": "E", "parent": "D"}])[0]["parent"], "SYC")
        self.assertEqual(dp.as_filed("BEL", [{"id": "F", "name": "Vlaams Gewest"}],
                                     [{"id": "21686613B18913386279163", "parent": "F"}]
                                     )[0]["parent"], "BEL")

    def test_a_declared_label_drawn_twice_stops_the_run(self):
        a1 = [{"id": "T1", "name": "Tashkent"}, {"id": "T2", "name": "Tashkent"}]
        with self.assertRaises(SystemExit):
            dp.as_filed("UZB", a1, [{"id": "79887680B40109116454398", "parent": "T1"}])

    def test_iraq_reads_the_parents_the_next_build_gives(self):
        if not site_units("admin2", "IRQ"):
            self.skipTest("no Iraqi units in this checkout")
        from scripts.fetch_census import iraq_census
        drawn = iraq_census.drawn_parents()
        self.assertEqual(drawn["Al-Hindiya"], "Karbala")
        for name in ("Al-Mahmoudiya", "Al-Kadhmiyah", "Al-Mada'in"):
            self.assertEqual(drawn[name], "Baghdad", name)

    def test_tashkent_s_districts_are_looked_for_in_the_city(self):
        if not site_units("admin2", "UZB"):
            self.skipTest("no Uzbek units in this checkout")
        from scripts.fetch_census import uzbekistan_siat
        shapes = uzbekistan_siat.shapes()
        city = {u["name"] for u in shapes["Tashkent"]}
        self.assertTrue({"Bektemir", "Sergeli", "Uchtepa"} <= city)
        self.assertFalse({"Bektemir", "Sergeli", "Uchtepa"}
                         & {u["name"] for u in shapes["Tashkent Region"]})

    def test_portugal_s_municipalities_are_all_filed_under_ine_s_districts(self):
        a1, a2 = site_units("admin1", "PRT"), site_units("admin2", "PRT")
        if not a2:
            self.skipTest("no Portuguese units in this checkout")
        from scripts.fetch_census import portugal_census as pc
        labels = {u["id"]: u["name"] for u in a1}
        filed = {u["id"]: labels[u["parent"]] for u in dp.as_filed("PRT", a1, a2)}
        for sid, district in (("2272694B58845957130361", "AVEIRO"),
                              ("2272694B97180634547799", "COIMBRA"),
                              ("2272694B62092960833864", "SANTARÉM"),
                              ("2272694B2878786593857", "VILA REAL"),
                              ("2272694B21944289016738", "VISEU")):
            self.assertEqual(filed[sid], district)
        self.assertEqual(pc.district_note([], []), "")


# ---------------------------------------------------------------------------
# UNDRAWN_PARTS
# ---------------------------------------------------------------------------

def unit(uid, name, value, year, **extra):
    return {"id": uid, "name": name, "population": {"value": value, "year": year}, **extra}


def kids(parent, values, year):
    return [{"id": f"{parent}{i}", "parent": parent,
             "population": {"value": v, "year": year}} for i, v in enumerate(values)]


class UndrawnParts(Plain):
    def test_several_undrawn_units_are_named_and_what_is_left_is_theirs(self):
        yap = unit("Y", "Yap", 10_739, 2023)
        pohnpei = unit("P", "Pohnpei", 26_102, 2023)
        values = (592, 1_000, 900, 800, 700, 1_000, 1_000, 700, 669, 700)
        self.assertEqual(sum(values), 8_061)
        said = quiet(be.note_undrawn_parts, {"FSM": [yap, pohnpei]},
                     {"FSM": kids("Y", values, 2023)})
        self.assertEqual(len(said), 1)
        self.assertEqual(
            yap["population_note"],
            "This count takes in 10 municipalities the map does not draw as units of their "
            "own: Rumung, Ulithi, Fais, Ngulu, Eauripik, Ifalik, Faraulep, Elato, Lamotrek "
            "and Satawal. The 10 divisions drawn here add up to 8,061, which leaves 2,678 "
            "for those 10.")
        self.assertPlain(yap["population_note"])

    def test_a_count_of_another_year_than_its_divisions_stops_the_build(self):
        # Chuuk's 2023 count less its municipalities' 2010 counts is no number
        # of people, and the build says so rather than print it.
        yap = unit("Y", "Yap", 10_739, 2023)
        pohnpei = unit("P", "Pohnpei", 26_102, 2023)
        with self.assertRaises(SystemExit):
            quiet(be.note_undrawn_parts, {"FSM": [yap, pohnpei]},
                  {"FSM": kids("Y", (4_000, 4_061), 2010)})
        mixed = kids("Y", (4_000,), 2023) + kids("Z", (4_061,), 2010)
        for k in mixed:
            k["parent"] = "Y"
        with self.assertRaises(SystemExit):
            quiet(be.note_undrawn_parts, {"FSM": [yap, pohnpei]}, {"FSM": mixed})

    def test_one_undrawn_unit_keeps_its_wording(self):
        self.assertEqual(
            be.undrawn_sentence("Temotu Pele", 2, 16_924, 22_319),
            "This count takes in Temotu Pele, which the map does not draw as a unit of its "
            "own: the 2 divisions drawn here add up to 16,924, which leaves 5,395 for "
            "Temotu Pele.")

    def test_a_unit_is_found_by_its_boundary_label_too(self):
        shefa = unit("S", "Shefa", 103_987, 2020, shape_name="Shefa Province")
        torba = unit("T", "Torba", 11_330, 2020)
        quiet(be.note_undrawn_parts, {"VUT": [shefa, torba]},
              {"VUT": kids("S", (90_000, 7_689), 2020) + kids("T", (8_896,), 2020)})
        self.assertIn("North Tongoa, Tongariki, Makimae, Nguna and Emau. The 2 divisions "
                      "drawn here add up to 97,689, which leaves 6,298 for those 5.",
                      shefa["population_note"])
        self.assertIn("Torres, Mota and Merelava", torba["population_note"])
        self.assertIn("leaves 2,434 for those 3.", torba["population_note"])

    def test_paramaribo_s_four_ressorts(self):
        para = unit("P", "Paramaribo", 240_924, 2012)
        quiet(be.note_undrawn_parts, {"SUR": [para]},
              {"SUR": kids("P", (100_000, 59_090), 2012)})
        self.assertIn("Beekhuizen, Latour, Tammenga and Welgelegen", para["population_note"])
        self.assertIn("leaves 81,834 for those 4.", para["population_note"])

    def test_dakar_is_not_said_to_take_in_keur_massar_s_ground(self):
        # Keur Massar's ground is drawn, inside Pikine's and Rufisque's old
        # outlines, and the RGPH-5 counts 770,314 there, not 668,496.
        self.assertNotIn(("SEN", "Dakar"), be.UNDRAWN_PARTS)
        self.assertNotIn(("FSM", "Chuuk"), be.UNDRAWN_PARTS)


# ---------------------------------------------------------------------------
# Vanuatu's second level
# ---------------------------------------------------------------------------

class Vanuatu(Plain):
    def test_its_second_level_is_declared_partial_and_says_what_it_leaves_out(self):
        entry = be.PARTIAL_LEVELS[("VUT", "admin2")]
        self.assertEqual(entry["units"], 58)
        self.assertIn("Torres Islands", entry["note"])
        self.assertIn("66", entry["note"])
        self.assertPlain(entry["note"])

    def test_the_map_draws_the_councils_declared(self):
        drawn = site_units("admin2", "VUT")
        if not drawn:
            self.skipTest("no Vanuatu units in this checkout")
        self.assertEqual(len(drawn), be.PARTIAL_LEVELS[("VUT", "admin2")]["units"])


# ---------------------------------------------------------------------------
# Notes the readers write
# ---------------------------------------------------------------------------

def nepal_map(rukum_under="Karnali"):
    """Every census district drawn once, the two undivided districts as the map files them."""
    where = {d: p for p, names in nepal.DISTRICTS.items() for d in names}
    bound = {d for parts in nepal.SHAPE_BOUND.values() for d in parts}
    admin1 = [{"id": p, "name": p} for p in nepal.PROVINCES]
    admin2 = [{"id": f"S-{d}", "name": d, "parent": where[d]}
              for d in where if d not in bound]
    for sid, parts in nepal.SHAPE_BOUND.items():
        parent = where[parts[0]]
        if parts == ("Rukum East", "Rukum West"):
            parent = rukum_under
        admin2.append({"id": sid, "name": "label", "parent": parent})
    return admin1, admin2


def nepal_parsed():
    people = {d: 100_000 for names in nepal.DISTRICTS.values() for d in names}
    people.update({"Nawalpur": 378_079, "Parasi": 386_868, "Rukum East": 56_786,
                   "Rukum West": 154_000})
    return {"ethnicity": {d: {"_total": n} for d, n in people.items()},
            "language": {}, "religion": {}}, people


class NepalProvinces(Plain):
    def test_a_province_says_what_its_drawn_districts_add_up_to_and_why(self):
        admin1, admin2 = nepal_map()
        parsed, people = nepal_parsed()
        notes = nepal.province_notes(parsed, nepal.holdings(admin1, admin2))
        self.assertEqual(sorted(notes), ["Gandaki", "Karnali", "Lumbini"])
        gandaki = sum(people[d] for d in nepal.DISTRICTS["Gandaki"]) + 386_868
        self.assertEqual(
            notes["Gandaki"],
            f"Its districts as drawn add up to {gandaki:,}, not this count: the boundary "
            f"file draws Nawalpur and Parasi as one district, as it was before 2017, and it "
            f"is shown here, but Parasi's 386,868 people are counted in Lumbini.")
        self.assertIn("Parasi (386,868 people) as one district with Nawalpur",
                      notes["Lumbini"])
        self.assertIn("Rukum East (56,786 people) as one district with Rukum West",
                      notes["Lumbini"])
        lumbini = sum(people[d] for d in nepal.DISTRICTS["Lumbini"]) - 386_868 - 56_786
        self.assertIn(f"add up to {lumbini:,}", notes["Lumbini"])
        self.assertIn("Rukum East's 56,786 people are counted in Lumbini", notes["Karnali"])
        for note in notes.values():
            self.assertPlain(note)

    def test_the_notes_follow_the_province_the_map_shows_a_polygon_under(self):
        # Filed under Lumbini instead, the Rukum polygon would hold Karnali's
        # Rukum West, and the two notes would say that the other way round.
        admin1, admin2 = nepal_map(rukum_under="Lumbini")
        parsed, _ = nepal_parsed()
        notes = nepal.province_notes(parsed, nepal.holdings(admin1, admin2))
        self.assertIn("Rukum West's 154,000 people are counted in Karnali", notes["Lumbini"])
        self.assertIn("Rukum West (154,000 people) as one district with Rukum East, as it "
                      "was before 2017, and it is shown under Lumbini", notes["Karnali"])

    def test_a_district_drawn_twice_or_not_at_all_stops_the_run(self):
        admin1, admin2 = nepal_map()
        with self.assertRaises(SystemExit):
            nepal.holdings(admin1, admin2 + [dict(admin2[0], id="again")])
        with self.assertRaises(SystemExit):
            nepal.holdings(admin1, admin2[1:])

    def test_the_province_record_carries_the_note(self):
        # build() writes it where it is given the map's polygons.
        admin1, admin2 = nepal_map()
        parsed, _ = nepal_parsed()
        held = nepal.holdings(admin1, admin2)
        notes = nepal.province_notes(parsed, held)
        self.assertTrue(notes["Gandaki"].startswith("Its districts as drawn add up to"))


class SaudiRegions(Plain):
    def test_a_region_says_whose_figures_its_governorates_carry(self):
        self.assertTrue(sc.REGION_NOTE.startswith("The 2022 census count (10 May 2022)."))
        self.assertIn("the governorates drawn here that show a population carry Wikidata's "
                      "figures, most of them for 2010", sc.REGION_NOTE)
        # Balqarn ('Asir) shows Wikidata's figure for 2022, so no region may
        # say that none of its governorates carries one.
        self.assertNotIn("no governorate drawn here carries a 2022 figure", sc.REGION_NOTE)
        self.assertPlain(sc.REGION_NOTE)

    def test_every_region_written_carries_it(self):
        def row(name, pcode, scale):
            out = {"year": "2022", "ADM1_EN": name, "ADM1_PCODE": pcode,
                   "F_TL": str(10 * scale * 20), "M_TL": str(10 * scale * 20),
                   "T_TL": str(20 * scale * 20)}
            for low in range(0, 100, 5):
                for sex in "FM":
                    out[f"{sex}_{low:02d}_{low + 4:02d}"] = str(10 * scale)
                out[f"T_{low:02d}_{low + 4:02d}"] = str(20 * scale)
            return out
        rows = [row("Riyadh", "SA01", 3), row("Najran", "SA10", 1)]
        admin1 = [{"id": "r1", "name": "Riyadh Region"}, {"id": "r2", "name": "Najran Region"}]
        saved = sc.NATIONAL
        sc.NATIONAL = sum(int(r["T_TL"]) for r in rows)
        try:
            out = quiet(sc.build, rows, admin1)
        finally:
            sc.NATIONAL = saved
        self.assertEqual([r["population"]["note"] for r in out], [sc.REGION_NOTE] * 2)


class Chuuk(Plain):
    def fields(self):
        names = fm.MUNICIPALITIES["Chuuk"]
        drawn = {"Weno", "Fefen", "Tol", "Polle", "Paata", "Wonei", "Ta", "Polowat", "Makur",
                 "Piherarh"}
        values = {}
        for n in names:
            values[n] = 2_655 if n in drawn else 736
        values["Weno"] += 3       # 26,553 drawn
        values["Tonoas"] += 21    # 22,101 not drawn
        return {n: {"population": {"value": v}} for n, v in values.items()}, drawn

    def test_the_state_says_how_many_of_its_people_live_where_no_municipality_is_drawn(self):
        fields, drawn = self.fields()
        note = fm.chuuk_note(fields, drawn)
        self.assertTrue(note.startswith(
            "The 2023 census publishes Chuuk only as a state; its latest count by "
            "municipality is the 2010 census's, when Chuuk had 48,654 people. The map draws "
            "10 of its 40 municipalities, which held 26,553 of them; the other 30, which "
            "held 22,101, are not drawn as units of their own: Piis-Penau, Fono, Tonoas,"),
            note)
        self.assertTrue(note.endswith("Fananu, Ruo and Murillo."), note)
        self.assertNotIn("Weno", note.split("their own:")[1])
        self.assertPlain(note)


class TuvaluIslands(Plain):
    VILLAGES = {("Nui", "Manutalake"): (204, 106, 98), ("Nui", "Alamoni"): (290, 140, 150),
                ("Vaitupu", "Asau"): (612, 300, 312), ("Vaitupu", "Temotu"): (11, 9, 2),
                ("Vaitupu", "Saniuta"): (205, 110, 95), ("Vaitupu", "Matagi"): (36, 19, 17),
                ("Vaitupu", "Motufoua"): (326, 127, 199),
                ("Nukufetau", "Aulotu"): (329, 166, 163),
                ("Nukufetau", "Maneapa"): (202, 98, 104)}

    def test_an_island_says_what_its_villages_held_in_2017(self):
        self.assertEqual(
            tv.island_note("Nui", self.VILLAGES),
            "The 2022 census count (Table 3). The 2022 census gives no village counts; in "
            "2017 Nui counted 494 people: 290 in Alamoni, the one village the map draws, and "
            "204 in Manutalake, which it does not draw.")
        self.assertIn("531 people: 329 in Aulotu", tv.island_note("Nukufetau", self.VILLAGES))
        vaitupu = tv.island_note("Vaitupu", self.VILLAGES)
        self.assertIn("1,190 people: 578 in the four villages the map draws (Temotu 11, "
                      "Saniuta 205, Matagi 36, Motufoua 326), and 612 in Asau", vaitupu)
        self.assertPlain(vaitupu)

    def test_island_fields_carry_the_note_only_with_the_villages(self):
        report = {"Nui": {"population": 514, "sex_ratio": 95, "median": 30}}
        faith = {"Nui": {"Church of Tuvalu": 500}}
        ethnic = {"Nui": {"Tuvaluan": 500}}
        self.assertIsNone(tv.island_fields("Nui", report, faith, ethnic)["population_note"])
        with_note = tv.island_fields("Nui", report, faith, ethnic, self.VILLAGES)
        self.assertIn("290 in Alamoni", with_note["population_note"])


def age_sheet(counts, open_from, open_counts):
    """A sex-by-single-year sheet as INDEC lays it out (as tests/test_argentina_census)."""
    women = sum(w for w, _ in counts.values()) + open_counts[0]
    men = sum(m for _, m in counts.values()) + open_counts[1]
    rows = [["Censo Nacional"], ["Cuadro 4.2.0. Provincia."],
            ["Edad", "Total de población", "Sexo registrado al nacer"],
            [None, None, "Mujer / Femenino", "Varón / Masculino"],
            ["Total", women + men, women, men, 107]]
    for low in range(0, open_from, 5):
        years = range(low, min(low + 5, open_from))
        w = sum(counts[a][0] for a in years)
        m = sum(counts[a][1] for a in years)
        rows.append([f"{low}-{low + 4}", w + m, w, m, 100])
        rows += [[float(a), sum(counts[a]), counts[a][0], counts[a][1], 100] for a in years]
    rows.append([f"{open_from} y más", sum(open_counts), *open_counts, 100])
    return rows


class BuenosAiresWithEntreRios(Plain):
    def kept(self):
        links = {key: f"https://example.invalid/{key[0]}{key[1]}" for key in ac.TABLES}
        ba = {"code": "06", "people": 100, "ages": age_sheet({a: (5, 5) for a in range(10)},
                                                             10, (0, 0)),
              "peoples": {"Mapuche": 3, "Qom (Toba)": 1}, "afro": 2, "private": 98,
              "speak": [4, 1, 3, 0], "links": links}
        er = {"code": "30", "people": 40, "ages": age_sheet({a: (3, 1) for a in range(10)},
                                                            10, (0, 0)),
              "peoples": {"Charrúa": 2, "Qom (Toba)": 1}, "afro": 1, "private": 40,
              "speak": [3, 1, 2, 0], "links": links}
        return {"Buenos Aires": ba, "Entre Ríos": er}

    def test_the_polygon_takes_both_provinces_added_before_anything_is_derived(self):
        out = quiet(ac.drawn_together, "Buenos Aires", ("Entre Ríos",), self.kept())
        self.assertEqual(out["population"]["value"], 140)
        self.assertEqual(out["sex_ratio"]["value"], round(1000 * 60 / 80))
        counts = {g["group"]: g["count"] for g in out["ethnicity"]}
        self.assertEqual(counts["Qom (Toba)"], 2)
        self.assertEqual(counts[ac.AFRO], 3)
        self.assertEqual(counts[ac.REST], 138 - 7 - 3)
        self.assertEqual(
            out["population_note"],
            "The boundary file draws Entre Ríos inside this polygon and no first-level "
            "polygon of its own, so the figures here are Buenos Aires and Entre Ríos "
            "together. The 2022 census counts Buenos Aires 100 and Entre Ríos 40; this is "
            "their sum, 140.")
        self.assertNotIn("INDEC's own median", out["median_age_note"])
        self.assertEqual(len(out["sources"]), 6)
        self.assertPlain(out["population_note"])

    def test_two_provinces_whose_ages_close_differently_stop_the_run(self):
        kept = self.kept()
        kept["Entre Ríos"]["ages"] = age_sheet({a: (3, 1) for a in range(5)}, 5, (15, 5))
        with self.assertRaises(SystemExit):
            quiet(ac.drawn_together, "Buenos Aires", ("Entre Ríos",), kept)

    def test_the_provinces_are_read_under_the_boundary_file_s_labels(self):
        # The build names a polygon after the row bound to it, so the map shows
        # La Roja as La Rioja; read by those names, two provinces lost their
        # polygon and 31 departments their label.
        if not site_units("admin1", "ARG"):
            self.skipTest("no Argentine units in this checkout")
        admin1, admin2 = ac.drawn_units()
        labels = {u["name"] for u in admin1}
        self.assertEqual([p[5] for p in ac.PROVINCES if p[5] and p[5] not in labels], [])
        self.assertTrue(all(u["name"] == (u.get("shape_name") or u["name"]) for u in admin2))

    def test_only_entre_rios_is_drawn_inside_another_province(self):
        self.assertEqual(ac.DRAWN_INSIDE, {"Buenos Aires": ("Entre Ríos",)})
        undrawn = [p[4] for p in ac.PROVINCES if p[5] is None]
        self.assertEqual(undrawn, ["Entre Ríos"])


if __name__ == "__main__":
    unittest.main()
