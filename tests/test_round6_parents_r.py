"""Round 6, parents (repair): notes that hold before a rebuild and after it.

Saudi regions no longer say that none of their governorates carries a 2022
figure ('Asir's Balqarn shows Wikidata's figure for 2022), and what they do
say is checked against the governorates as the build files them. Portugal's
second Oliveira de Frades polygon tells the two apart by size, since both are
filed under Viseu once the declaration is built. Argentina's capital says what
its first-level outline holds: about four times the city, most of it Greater
Buenos Aires partidos the map files under Buenos Aires. No network.
"""

import json
import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
from scripts.fetch_census import argentina_census as ac  # noqa: E402
from scripts.fetch_census import declared_parents as dp  # noqa: E402
from scripts.fetch_census import portugal_census as pc  # noqa: E402
from scripts.fetch_census import saudi_census as sc  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SITE = ROOT / "site" / "data"

# Words a visitor's note has no use for: the pipeline's own names for things.
INTERNAL = ("DECLARED", "UNDRAWN", "PARTIAL", "OUTLINE", "build", ".py", "adapter",
            "pipeline", "agent", "owner", "shape_id", "processed")

CABA = "Ciudad Autónoma de Buenos Aires"
OLIVEIRA_SMALL = "2272694B61775283939308"
OLIVEIRA = "2272694B21944289016738"


def site_units(level, iso3):
    path = SITE / level / f"{iso3}.units.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def rows_of(name):
    path = PROCESSED / name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["rows"] if isinstance(data, dict) and "rows" in data else data


class Plain(unittest.TestCase):
    def assertPlain(self, text):
        for word in INTERNAL:
            self.assertNotIn(word, text)


class SaudiRegionNote(Plain):
    def test_no_region_says_none_of_its_governorates_carries_a_2022_figure(self):
        self.assertNotIn("no governorate drawn here carries a 2022 figure", sc.REGION_NOTE)
        self.assertTrue(sc.REGION_NOTE.startswith(
            "The 2022 census count (10 May 2022). No table of the 2022 census by "
            "governorate could be read; the governorates drawn here that show a population "
            "carry Wikidata's figures, most of them for 2010"))
        self.assertPlain(sc.REGION_NOTE)

    def test_wikidata_dates_balqarn_s_figure_2022(self):
        # Why the clause went: the fill-only figure the map shows on Balqarn
        # ('Asir) is Wikidata's, dated 2022.
        rows = [r for r in rows_of("wikidata_admin2_classes.json") if r.get("country") == "SAU"]
        if not rows:
            self.skipTest("no Saudi Wikidata rows in this checkout")
        years = {r["name"]: (r.get("population") or {}).get("year") for r in rows}
        self.assertEqual(years.get("Balqarn governorate"), 2022)

    def test_what_the_note_says_holds_in_every_region_as_filed(self):
        # Every governorate that shows a population shows Wikidata's; in every
        # region most of them are 2010's; and in none do they make the region's
        # census count. Read from the published units, filed as the next build
        # files them (Sharurah under Najran).
        admin1, admin2 = site_units("admin1", "SAU"), site_units("admin2", "SAU")
        if not admin2:
            self.skipTest("no Saudi units in this checkout")
        kids = defaultdict(list)
        for unit in dp.as_filed("SAU", admin1, admin2):
            kids[unit.get("parent")].append(unit)
        regions = 0
        for region in admin1:
            own = (region.get("population") or {}).get("value")
            shown = [u["population"] for u in kids.get(region["id"], [])
                     if (u.get("population") or {}).get("value") is not None]
            self.assertTrue(shown, region["name"])
            for figure in shown:
                self.assertTrue(str(figure.get("source", "")).startswith("Wikidata"),
                                region["name"])
            of_2010 = sum(1 for f in shown if f.get("year") == 2010)
            self.assertGreater(2 * of_2010, len(shown), region["name"])
            self.assertNotEqual(round(sum(f["value"] for f in shown)), round(own or 0),
                                region["name"])
            regions += 1
        self.assertEqual(regions, 13)


class OliveiraDeFrades(Plain):
    def test_the_note_tells_the_two_polygons_apart_by_size(self):
        note = pc.UNIDENTIFIED[OLIVEIRA_SMALL]
        self.assertIn("The municipality (145 km²) is the 144 km² one", note)
        for district in ("Aveiro", "Viseu"):
            self.assertNotIn(f"under {district}", note)
        self.assertPlain(note)

    def test_as_the_build_files_them_both_polygons_are_under_viseu(self):
        admin1, admin2 = site_units("admin1", "PRT"), site_units("admin2", "PRT")
        if not admin2:
            self.skipTest("no Portuguese units in this checkout")
        labels = {u["id"]: u["name"] for u in admin1}
        filed = {u["id"]: labels.get(u.get("parent")) for u in dp.as_filed("PRT", admin1, admin2)}
        self.assertEqual(filed[OLIVEIRA], "VISEU")
        self.assertEqual(filed[OLIVEIRA_SMALL], "VISEU")


class CapitalOutline(Plain):
    MOSTLY = ("General San Martín", "Hurlingham", "Morón", "San Isidro", "Tres de Febrero",
              "Vicente López", "Ituzaingó", "Lanús", "San Miguel")
    IN_PART = ("La Matanza", "Lomas de Zamora", "Avellaneda")
    # The partidos the note names in part, by polygon: other provinces have
    # departments of the same names.
    IN_PART_IDS = {"61730980B21366789082443": "La Matanza",
                   "61730980B58255414710643": "Lomas de Zamora",
                   "61730980B497821979952": "Avellaneda"}

    def note(self):
        return ac.OUTLINE_NOTES[CABA]

    def test_the_capital_says_what_its_outline_holds(self):
        note = self.note()
        self.assertTrue(note.startswith("The outline drawn here is not the city's own: it is "
                                        "about four times the city's area."))
        for name in self.MOSTLY + self.IN_PART:
            self.assertIn(name, note)
        self.assertIn("Comuna 1, nearly all of Comuna 2 and parts of Comunas 3, 4, 13 and 14",
                      note)
        self.assertTrue(note.endswith("the partidos' people are counted in Buenos Aires."))
        self.assertPlain(note)
        self.assertEqual(set(ac.OUTLINE_NOTES), {CABA})

    def test_the_partidos_mostly_inside_it_are_the_ones_declared_under_buenos_aires(self):
        admin2 = site_units("admin2", "ARG")
        if not admin2:
            self.skipTest("no Argentine units in this checkout")
        declared = {sid for sid, (iso3, label) in be.DECLARED_PARENTS.items()
                    if (iso3, label) == ("ARG", "Buenos Aires")}
        names = {u["id"]: u.get("shape_name") or u["name"] for u in admin2}
        self.assertEqual(sorted(names[sid] for sid in declared),
                         sorted(self.MOSTLY + ("Avellaneda",)))

    def test_as_filed_the_capital_holds_its_15_comunas_and_the_partidos_are_under_buenos_aires(self):
        if not site_units("admin1", "ARG"):
            self.skipTest("no Argentine units in this checkout")
        admin1, admin2 = ac.drawn_units()
        labels = {u["id"]: u["name"] for u in admin1}
        filed = dp.as_filed("ARG", admin1, admin2)
        self.assertEqual(sorted(u["name"] for u in filed if labels.get(u.get("parent")) == CABA),
                         sorted(f"Comuna {i}" for i in range(1, 16)))
        named = {sid: label for sid, (iso3, label) in be.DECLARED_PARENTS.items()
                 if iso3 == "ARG" and label == "Buenos Aires"}
        named.update(self.IN_PART_IDS)
        under = {u["id"]: (u["name"], labels.get(u.get("parent"))) for u in filed}
        self.assertEqual(sorted(under[sid][0] for sid in named),
                         sorted(self.MOSTLY + self.IN_PART))
        for sid in named:
            self.assertEqual(under[sid][1], "Buenos Aires", under[sid][0])


class VanuatuPartialLevel(unittest.TestCase):
    def test_the_declaration_stands_and_its_side_effects_are_written_down(self):
        self.assertIn(("VUT", "admin2"), be.PARTIAL_LEVELS)
        source = (ROOT / "scripts" / "build_entities.py").read_text(encoding="utf-8")
        block = source[source.index("Declaring the level puts land under"):
                       source.index('("VUT", "admin2"): {')]
        for name in ("fill_parent_populations", "restate_encyclopaedia_parents",
                     "population_disagreements", "check_rollups", "mark_disputed_or_hint"):
            self.assertIn(name, block)


if __name__ == "__main__":
    unittest.main()
