"""The final sweep's north fixes: North Africa's readers write each unit under
the name its own notes give it, cite every publication a note quotes, give a
ratio's men and women, say what Tripoli's outline is, and bind on the boundary
file's labels after a rebuild has renamed the polygons. No network."""

import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import egypt_census as ec  # noqa: E402
from scripts.fetch_census import libya_census as lc  # noqa: E402
from scripts.fetch_census import morocco_rgph2024 as mr  # noqa: E402
from scripts.fetch_census import morocco_rgph2024_ages as ma  # noqa: E402
from scripts.fetch_census import morocco_rgph2024_sexes as ms  # noqa: E402
from scripts.fetch_census import sudan_census as sc  # noqa: E402
from scripts.fetch_census import tunisia_census as tc  # noqa: E402
from scripts.fetch_census import uscb  # noqa: E402


def cited(record):
    """Each field a record's sources are cited for -> the names cited for it."""
    out = {}
    for src in record.get("sources") or []:
        for part in src["field"].split("/"):
            out.setdefault(part, set()).add(src["name"])
    return out


@contextlib.contextmanager
def site(module, iso3, levels):
    """The site's units as a rebuild writes them, ``levels`` {level: units},
    under ``module.SITE``."""
    with tempfile.TemporaryDirectory() as tmp:
        for level, units in levels.items():
            Path(tmp, level).mkdir()
            Path(tmp, level, f"{iso3}.units.json").write_text(json.dumps(units))
        with mock.patch.object(module, "SITE", Path(tmp)):
            yield


# ------------------------------------------------------------------ Tunisia

TUN_HEADER = ["Code_Gouvernorat", "Gouvernorat", "الولاية", "Code_Delegation", "Délégations",
              "المعتمدية", "Code_secteur_D", "Secteurs", "ID_Sexe", "Tranche d'âge", "Population"]
TUN_AGES = ["00-04", "05-09", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44",
            "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
# Mahdia's label as the boundary file writes it, between a right-to-left
# embedding and its closing mark.
MARKED = "\u202bالمهدية\u202c"


def tunisia_sheet(delegations):
    """INS's sheet, one sector a delegation: [(governorate code, French and
    Arabic names, delegation code, French and Arabic names, men and women in
    each age group)]."""
    rows = [TUN_HEADER]
    for g, gfr, gar, d, dfr, dar, men, women in delegations:
        for sex, n in (("M", men), ("F", women)):
            rows += [[g, gfr, gar, d, dfr, dar, d + "01", dfr, sex, age, n] for age in TUN_AGES]
    return rows


def tunisia_table():
    sheet = tunisia_sheet([
        ("33", "Mahdia", "المهدية", "3353", "Ouled chamekh", "أولاد الشامخ", 7, 10),
        ("33", "Mahdia", "المهدية", "3351", "Mahdia", "المهدية", 10, 10),
        ("33", "Mahdia", "المهدية", "3354", "Chebba", "الشابة", 5, 5)])
    with mock.patch.object(tc, "NATIONAL", 17 * (7 + 10 + 10 + 10 + 5 + 5)):
        return tc.read(sheet)


def tunisia_build(admin1, admin2):
    # Ouled Chamekh's label has lost its first letter, and is declared.
    with mock.patch.dict(tc.DELEGATIONS, {("33", "3353"): "والد شامخ"}, clear=True):
        records, _ = tc.build(tunisia_table(), admin1, admin2, {})
    return {r["shape_id"]: r for r in records}


class TunisiaNamesAndRatios(unittest.TestCase):
    """Delegations under INS's French names, the Arabic labels kept as aliases
    as they read (NWA-06); every ratio beside the men and women it is taken
    from (NWA-16)."""

    def build(self):
        return tunisia_build([{"id": "G", "name": "Mahdia"}],
                             [{"id": "C", "name": "والد شامخ", "parent": "G"},
                              {"id": "M", "name": MARKED, "parent": "G"},
                              {"id": "B", "name": "Chebba", "parent": "G"}])

    def test_a_delegation_takes_ins_s_french_name_and_keeps_its_label(self):
        by = self.build()
        self.assertEqual(by["C"]["name"], "Ouled Chamekh")
        self.assertEqual(by["C"]["aliases"], ["والد شامخ"])
        # The name is the one the notes give.
        self.assertTrue(by["C"]["population_note"].startswith(
            "The 2024 census count of the delegation of Ouled Chamekh:"))

    def test_the_label_kept_drops_its_direction_marks(self):
        by = self.build()
        self.assertEqual(by["M"]["name"], "Mahdia")
        self.assertEqual(by["M"]["aliases"], ["المهدية"])
        self.assertEqual(tc.clean("طبرقة\u200e"), "طبرقة")
        # A label that is the French name already is no alias of it.
        self.assertEqual(by["B"]["name"], "Chebba")
        self.assertNotIn("aliases", by["B"])

    def test_a_governorate_keeps_its_french_label(self):
        by = self.build()
        self.assertEqual(by["G"]["name"], "Mahdia")
        self.assertNotIn("aliases", by["G"])

    def test_a_ratio_gives_the_men_and_women_it_is_taken_from(self):
        by = self.build()
        self.assertEqual(by["C"]["sex_ratio"]["value"], 700)
        self.assertEqual(by["C"]["sex_ratio_note"],
                         "Men per 1,000 women at the 2024 census in the delegation of Ouled "
                         "Chamekh: 119 men and 170 women.")
        self.assertEqual(by["G"]["sex_ratio_note"],
                         "Men per 1,000 women at the 2024 census in the governorate of Mahdia: "
                         "374 men and 425 women.")


# ------------------------------------------------------------------ Morocco

def hcp_workbook(rows):
    """HCP's legal-population workbook: (name, Moroccans, foreigners, code)."""
    import io
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Population légale du Royaume du Maroc"])
    sheet.append(["", "Marocains", "Étrangers", "Population", "Ménages", "", "Code"])
    for name, moroccans, foreigners, code in rows:
        sheet.append([name, moroccans, foreigners, moroccans + foreigners, 1, "", code])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


SEMARA = [("Ensemble du territoire national", 68, 2, None),
          ("Région de Laâyoune-Sakia El Hamra", 68, 2, 11),
          ("Province d'Es-Semara", 50, 0, 11221),
          ("Préfecture de Laâyoune", 18, 2, 11321)]
SEMARA_LABEL = "Province d'Es-Semara إقليم السمارة"


def semara_table():
    with mock.patch.object(mr, "NATIONAL", 70):
        return mr.read(hcp_workbook(SEMARA))


class MoroccoNames(unittest.TestCase):
    """Provinces under their labels' Latin part, the whole label kept as an
    alias, in all three readers that bind them (NWA-07)."""

    def test_the_latin_part_is_the_name(self):
        for label, name in (("Province de Figuig إقليم الناظور", "Province de Figuig"),
                            ("Province d'Ifrane ⵜⴰⵙⴳⴰ ⵏ ⵉⴼⵔⴰⵏ إقليم إفران", "Province d'Ifrane"),
                            ("Préfecture d'Oujda-Angad عمالة وجدة - أنجاد",
                             "Préfecture d'Oujda-Angad"),
                            ("Province de Taza اقليم تازة", "Province de Taza"),
                            ("Tata Province", "Tata Province")):
            self.assertEqual(mr.written(label), name, label)
        self.assertEqual(mr.label_alias("Province de Figuig إقليم الناظور"),
                         ["Province de Figuig إقليم الناظور"])
        self.assertIsNone(mr.label_alias("Tata Province"))

    def test_figuig_is_written_as_figuig_with_its_own_count(self):
        rows = [("Ensemble du territoire national", 690, 10, None),
                ("Région de l'Oriental", 690, 10, 2),
                ("Province de Figuig", 290, 10, 2251),
                ("Province de Nador", 400, 0, 2381)]
        with mock.patch.object(mr, "NATIONAL", 700):
            table = mr.read(hcp_workbook(rows))
        admin1 = [{"id": "R", "name": "Oriental"}]
        admin2 = [{"id": "F", "name": "Province de Figuig إقليم الناظور", "parent": "R"},
                  {"id": "N", "name": "Province de Nador إقليم الناظور", "parent": "R"}]
        records, _ = mr.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["F"]["name"], "Province de Figuig")
        self.assertEqual(by["F"]["aliases"], ["Province de Figuig إقليم الناظور"])
        self.assertEqual(by["F"]["population"]["value"], 300)
        self.assertEqual(by["N"]["name"], "Province de Nador")
        self.assertEqual(by["N"]["population"]["value"], 400)
        self.assertEqual(by["R"]["name"], "Oriental")
        self.assertNotIn("aliases", by["R"])

    def test_the_sexes_and_the_ages_carry_the_same_name_and_alias(self):
        bound = [{"level": "admin2", "name": "Province de Figuig", "shape_id": "F",
                  "aliases": ["Province de Figuig إقليم الناظور"],
                  "codes": {"hcp": "2251"}, "population": {"value": 42}}]
        table = {"regions": {}, "provinces": {2251: {"name": "Province de Figuig",
                                                     "code": 2251}}}
        chart = ms.read_sexes([
            {"libelle_fr": "Oriental", "libelle_prov": "Figuig", "Sexe": s, "v": v}
            for s, v in (("Masculin", 20.0), ("Féminin", 22.0))])
        with mock.patch.object(ms.legal, "build", return_value=(bound, [])):
            sexes, _ = ms.build(chart, table, [], [])
        with mock.patch.object(ma.legal, "build", return_value=(bound, [])):
            ages, _ = ma.build(table, [], [], {})
        for got in (sexes[0], ages[0]):
            self.assertEqual(got["name"], "Province de Figuig")
            self.assertEqual(got["aliases"], ["Province de Figuig إقليم الناظور"])


class MoroccoCitations(unittest.TestCase):
    """A reason that quotes a count cites the publication of the count (NWA-17)."""

    def test_the_pieces_across_the_line_cite_hcp_s_workbook(self):
        admin1 = [{"id": "R", "name": "Laâyoune-Sakia El Hamra"}]
        admin2 = [{"id": "S", "name": SEMARA_LABEL, "parent": "R"}]
        records, _ = mr.build(semara_table(), admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["S"]["name"], "Province d'Es-Semara")
        for sid in ("R", "S"):
            self.assertEqual(len(by[sid]["sources"]), 1)
            source = by[sid]["sources"][0]
            self.assertEqual((source["name"], source["url"]), (mr.SOURCE, mr.LANDING))
            self.assertEqual(source["field"].split("/"),
                             [f"{field} note" for field in mr.FIELDS])
        self.assertIn("(50 people)", by["S"]["population"]["note"])

    def test_guelmim_s_median_cites_the_note_on_the_southern_provinces(self):
        bound = [{"level": "admin1", "name": "Guelmim-Oued Noun", "shape_id": "R",
                  "codes": {"hcp": "10"}, "population": {"value": 200}}]
        table = {"regions": {10: {"name": "Région de Guelmim-Oued Noun"}}, "provinces": {}}
        with mock.patch.object(ma.legal, "build", return_value=(bound, [])):
            records, _ = ma.build(table, [], [], {})
        median = records[0]["median_age"]
        self.assertNotIn("value", median)
        self.assertIn("31.3 years in 2024", median["note"])
        self.assertIn(ma.SOUTH_TITLE, median["note"])
        self.assertEqual(records[0]["sources"],
                         [{"field": "median_age note", "name": f"{ma.HCP}, {ma.SOUTH_TITLE}",
                           "url": ma.SOUTH_URL, "license": ma.LICENCE, "year": 2024}])


# -------------------------------------------------------------------- Egypt

def ocha(gov, en, ar, t, code, m=None, f=None):
    """A row of OCHA's 2006 table."""
    m = m if m is not None else (t // 2 if t else None)
    f = f if f is not None else (t - t // 2 if t else None)
    return {"gov": gov, "en": en, "ar": ar, "code": code, "m": m, "f": f, "t": t}


def capmas(code, ar, name, status, p2006, p2017, p2023):
    """A unit of City Population's table of CAPMAS's units."""
    return {"code": code, "gov": code[:2], "name": name, "status": status, "ar": ar,
            "p1996": None, "p2006": p2006, "p2017": p2017, "p2023": p2023,
            "href": f"/en/egypt/admin/x/{code}__x/"}


def governorate(code, p2017, p2023):
    return {"code": code, "name": ec.GOV_EN[code], "p2006": None, "p2017": p2017,
            "p2023": p2023, "href": f"/en/egypt/admin/{code}__x/"}


def egypt():
    """Every governorate drawn, as the boundary file labels them (two
    misspelt, two without a code), and outlines of four of them."""
    admin1 = []
    for gov, iso in ec.GOV_ISO.items():
        shape = {"id": f"G{gov}", "name": ec.UNCODED.get(iso) or f"{ec.GOV_EN[gov]} Governorate"}
        if iso not in ec.UNCODED:
            shape["iso_3166_2"] = iso
        admin1.append(shape)
    for shape in admin1:
        shape["name"] = {"G29": "Luxor Governate", "G24": "Minya Governate"}.get(
            shape["id"], shape["name"])
    admin2 = [{"id": "TK", "name": "Kesm Tahta", "parent": "G26"},
              {"id": "TM", "name": "Tahta", "parent": "G26"},
              {"id": "AC", "name": "Akhmim City", "parent": "G26"},
              {"id": "Z", "name": "Zemam Out", "parent": "G26"},
              {"id": "D", "name": "DuqqI", "parent": "G21"},
              {"id": "A", "name": "Alamn", "parent": "G33"},
              {"id": "P", "name": "Port Suez Police Department", "parent": "G04"}]
    districts = [ocha("26", "Kesm Tahta", "قسم طهطا", 100000, 2601),
                 ocha("26", "Tahta", "مركز طهطا", 300000, 2602),
                 ocha("26", "Akhmim City", "مدينة أخميم الجديدة", None, 2690),
                 ocha("21", "DuqqI", "قسم الدقى", 90000, 2101),
                 ocha("33", "Alamn", "قسم مارينا العلمين السياحية", 42, 3301, 41, 1),
                 ocha("04", "Port Suez Police Department", "إدارة شرطة ميناء السويس", None, 499)]
    units = [capmas("2610", "قسم طهطا", "Ṭahṭā", "Kism", 100000, 120000, 130000),
             capmas("2611", "مركز طهطا", "Ṭahṭā", "Markaz", 300000, 350000, 380000),
             capmas("2690", "مدينة أخميم الجديدة", "Madīnat Akhmīm al-Jadīdah", "New City",
                    None, 0, None),
             capmas("2105", "قسم الدقي", "Ad-Duqqī", "Kism", 90000, 70926, 75000),
             capmas("3306", "قسم العلمين", "Al-'Alamayn", "Kism (fully rural)", 52, 9932, 12580)]
    cp = {"units": {u["code"]: u for u in units},
          "govs": {"26": governorate("26", 470000, 510000),
                   "29": governorate("29", 1250209, 1400640)}}
    return cp, districts, admin1, admin2


class EgyptNames(unittest.TestCase):
    """Outlines under the CAPMAS names their notes use, governorates under the
    English names theirs do, every label kept as an alias (NWA-18)."""

    def build(self):
        cp, districts, admin1, admin2 = egypt()
        records, _ = ec.build(cp, districts, {}, admin1, admin2, {}, "https://hdx", "lic", [])
        return {r["shape_id"]: r for r in records}

    def test_a_garbled_label_gives_way_to_capmas_s_name(self):
        by = self.build()
        self.assertEqual(by["D"]["name"], "Ad-Duqqī")
        self.assertEqual(by["D"]["aliases"], ["DuqqI"])
        self.assertIn("the kism of Ad-Duqqī", by["D"]["population_note"])

    def test_a_kism_and_a_markaz_of_one_name_say_which_they_are(self):
        by = self.build()
        self.assertEqual((by["TK"]["name"], by["TM"]["name"]), ("Ṭahṭā (kism)", "Ṭahṭā (markaz)"))
        self.assertEqual((by["TK"]["aliases"], by["TM"]["aliases"]), (["Kesm Tahta"], ["Tahta"]))

    def test_a_unit_renamed_since_goes_by_today_s_name(self):
        by = self.build()
        self.assertEqual(by["A"]["name"], "Al-'Alamayn")
        self.assertEqual(by["A"]["aliases"], ["Alamn"])

    def test_outlines_no_table_names_keep_their_labels(self):
        by = self.build()
        for sid, label in (("Z", "Zemam Out"), ("P", "Port Suez Police Department")):
            self.assertEqual(by[sid]["name"], label)
            self.assertNotIn("aliases", by[sid])
        self.assertEqual(by["AC"]["name"], "Madīnat Akhmīm al-Jadīdah")

    def test_governorates_take_the_names_their_notes_use(self):
        by = self.build()
        self.assertEqual(by["G29"]["name"], "Luxor Governorate")
        self.assertEqual(by["G29"]["aliases"], ["Luxor Governate"])
        self.assertEqual(by["G26"]["name"], "Sohag Governorate")
        self.assertNotIn("aliases", by["G26"])


class EgyptCitations(unittest.TestCase):
    """Every publication a note quotes is cited for that note, and no record
    goes without a source (NWA-17)."""

    def build(self):
        cp, districts, admin1, admin2 = egypt()
        records, _ = ec.build(cp, districts, {}, admin1, admin2, {}, "https://hdx", "lic", [])
        return records, {r["shape_id"]: r for r in records}

    def test_no_record_goes_without_a_source(self):
        records, _ = self.build()
        self.assertEqual([r["name"] for r in records if not r["sources"]], [])

    def test_reasons_cite_the_tables_they_speak_of(self):
        _, by = self.build()
        notes = ["population note", "median_age note", "sex_ratio note"]
        zemam = cited(by["Z"])
        for note in notes:
            self.assertEqual(zemam[note], {ec.SOURCE_2017_COUNT, ec.SOURCE_2006})
            self.assertEqual(cited(by["P"])[note], {ec.SOURCE_2006})
            self.assertEqual(cited(by["AC"])[note], {ec.SOURCE_2017_COUNT})
        self.assertEqual(by["Z"]["sources"][0]["url"], ec.URL)
        self.assertEqual(by["P"]["sources"][0]["url"], "https://hdx")

    def test_the_2017_count_a_note_gives_is_cited(self):
        _, by = self.build()
        self.assertIn("the 2017 census counted 70,926", by["D"]["population_note"])
        self.assertEqual(cited(by["D"])["population note"], {ec.SOURCE_2017_COUNT})
        self.assertIn("the 2017 census counted 470,000", by["G26"]["population_note"])
        self.assertEqual(cited(by["G26"])["population note"], {ec.SOURCE_2017_COUNT})

    def test_a_renamed_unit_cites_both_tables_of_2006(self):
        _, by = self.build()
        self.assertIn("41 men and 1 woman", by["A"]["population_note"])
        self.assertEqual(cited(by["A"])["population note"],
                         {ec.SOURCE_2017_COUNT, ec.SOURCE_2006, ec.SOURCE_2006_CP})

    def test_a_refused_governorate_cites_what_its_reasons_quote(self):
        cp = {"govs": {"29": governorate("29", 1250209, 1400640),
                       "27": governorate("27", 3164281, 3640916)}, "units": {}}
        qus = capmas("2711", "مركز قوص", "Qūṣ", "Markaz", 1, 464288, 534523)
        plans = {"37247803B95427647060127": {"parts": [qus]}}
        shapes = {g: {"id": g, "name": g} for g in cp["govs"]}

        def flat(total):
            """Ten-year groups making ``total``, half of each group men."""
            per = [total // 10] * 9 + [total - 9 * (total // 10)]
            return [(lo, None if lo == 90 else lo + 9, n // 2, n - n // 2)
                    for lo, n in zip(range(0, 100, 10), per)]
        pages = {g: flat(r["p2017"]) for g, r in cp["govs"].items()}
        out = {r["codes"]["capmas"]: r for r in ec.governorates(cp, shapes, pages, plans, [])}
        luxor = cited(out["29"])
        self.assertEqual(out["29"]["population"]["status"], "not_available")
        self.assertEqual(luxor["population note"], {ec.SOURCE_2023, ec.SOURCE_2017_COUNT})
        for note in ("median_age note", "sex_ratio note"):
            self.assertEqual(luxor[note], {ec.SOURCE_2023, ec.SOURCE_2017})
        self.assertNotIn("population", luxor)

    def test_where_the_two_tables_of_2006_are_compared_both_are_cited(self):
        rows = [ocha("01", "Hurghada 1", "قسم أول الغردقة", 31148, 101, 17864, 13284)]
        units = ec.units_2006(rows)
        part = capmas("0101", "قسم أول الغردقة", "Al-Ghurdaqah 1", "Kism", 69616, 80000, 90000)
        for u in units:
            u["display"] = ec.display(u, {"0101": part})
        cp = {"units": {"0101": part}, "govs": {"01": {"p2006": 7902085}}}
        plan = ec.compose({"S": units}, cp, {"01": {"t": 7956536}}, [], units)["S"]
        fields = ec.outline_record({"id": "S", "name": "Hurghada 1"}, units, plan, {},
                                   "https://hdx", "lic")
        got = cited(fields)
        self.assertEqual(got["population"], {ec.SOURCE_2006})
        self.assertEqual(got["population note"], {ec.SOURCE_2006_CP})
        self.assertEqual(got["median_age note"], {ec.SOURCE_2006, ec.SOURCE_2006_CP})
        self.assertEqual(got["sex_ratio"], {ec.SOURCE_2006})

    def test_a_ratio_given_as_a_reason_cites_the_table_for_its_note(self):
        got = ec.ratio_fields(41, 1, 2006, ec.SOURCE_2006)
        self.assertEqual(ec.cited(got, "sex_ratio"), "sex_ratio note")
        got = ec.ratio_fields(10319, 4739, 2006, ec.SOURCE_2006)
        self.assertEqual(ec.cited(got, "sex_ratio"), "sex_ratio")


# -------------------------------------------------------------------- Libya

def libya_table():
    """Every shabiyah of SHAPES with one baladiyah of its own name, 20 men and
    20 women each."""
    shabiyat = {key: {"name": key.upper(), "total": 40, "men": 20, "women": 20,
                      "groups": [(0, 4, 20), (5, None, 20)], "shabiyah": key.upper()}
                for key in lc.SHAPES}
    return {"national": None, "shabiyat": shabiyat, "below": {},
            "baladiyat": [dict(unit) for unit in shabiyat.values()]}


LIBYA_LABELS = {"tarabulus": "Tajura' wa an Nawahi al Arba", "darnah": "Al Qubbah"}


def libya_build(drawn, estimates=None):
    with mock.patch.object(lc, "NATIONAL", 40 * len(lc.SHAPES)), \
            mock.patch.object(lc, "MOVED", {}):
        return lc.build(libya_table(), drawn, estimates,
                        "Bureau of Statistics and Census Libya, estimates for 2020")


class LibyaTripoli(unittest.TestCase):
    """The outline named Tripoli is its outskirts (NWA-04), and the two areas
    left without figures cite the census their reasons quote (NWA-17)."""

    def build(self, estimates=None):
        shapes = [{"id": sid, "name": LIBYA_LABELS.get(key, key.title())}
                  for key, sid in lc.SHAPES.items()]
        return libya_build({"admin1": shapes, "admin2": shapes}, estimates)

    def test_the_tripoli_outline_says_it_is_the_outskirts(self):
        tripoli = [r for r in self.build() if r["shape_id"] == lc.SHAPES["tarabulus"]]
        self.assertEqual(len(tripoli), 2)
        for r in tripoli:
            self.assertEqual(r["name"], "Tripoli")
            for field in ("population", "median_age", "sex_ratio", "ethnicity"):
                note = r[field]["note"]
                self.assertTrue(note.endswith(
                    " Tajura' wa an Nawahi al Arba, a name this area is also given, was a "
                    "district of the 2001 division; the area shown is the outskirts south and "
                    "east of Tripoli: the city itself and Tajura stand on a strip of coast, "
                    "about 155 km², that the map draws in no district."), note)
                self.assertNotIn("which holds Tripoli", note)

    def test_the_areas_without_figures_cite_the_census(self):
        records = self.build()
        for key in ("tarabulus", "aljafarah"):
            for r in (r for r in records if r["shape_id"] == lc.SHAPES[key]):
                self.assertEqual(r["sources"], [{
                    "field": "population note/median_age note/sex_ratio note/ethnicity note",
                    "name": lc.SOURCE, "url": lc.uscb.dataset_url(lc.DATASET), "year": 2006,
                    "license": lc.LICENCE}])
                self.assertIn("about 66,000 people", r["median_age"]["note"])

    def test_the_census_count_an_estimate_s_note_gives_stays_cited(self):
        estimates = {key: 1000 for key in lc.SHAPES}
        sabha = [r for r in self.build(estimates) if r["shape_id"] == lc.SHAPES["sabha"]][0]
        self.assertEqual(sabha["population"]["year"], 2020)
        self.assertIn("the 2006 census counted 40", sabha["population_note"])
        self.assertEqual(cited(sabha)["population note"], {lc.SOURCE})

    def test_another_relabelled_area_still_says_what_it_holds(self):
        darnah = [r for r in self.build() if r["shape_id"] == lc.SHAPES["darnah"]][0]
        self.assertIn("the area shown is the shabiyah of Darnah as drawn in 2007, which holds "
                      "Derna and Al Qubbah.", darnah["population_note"])


# -------------------------------------------------------------------- Sudan

SD_NAMES = ["AREA_NAME", "ADM1_NAME", "ADM_LEVEL", "GEO_MATCH", "M", "F", "T"]
SD_ALIASES = ["Area", "State", "Level", "Code",
              "Male Population, institutional and non-institutional population",
              "Female Population, institutional and non-institutional population",
              "Total Population, institutional and non-institutional population"]


def sudan_ages(total):
    """Table P01 for Sennar: three age groups making ``total``, half of each men."""
    names = ["AREA_NAME", "ADM_LEVEL", "BTOTL", "MTOTL", "FTOTL"]
    for sex in "BMF":
        names += [f"{sex}0004", f"{sex}0509", f"{sex}10PL"]
    groups = [total * 5 // 12, total * 5 // 12, total - 2 * (total * 5 // 12)]
    row = ["SINNAR", 1, total, total // 2, total - total // 2]
    for share in (1.0, 0.5, 0.5):
        row += [int(g * share) for g in groups]
    return sc.read_ages([names, names, row])


class SudanCitations(unittest.TestCase):
    """A state's median note sets Table P01's people against the
    retabulation's count, and cites both (NWA-17)."""

    def build(self, p01_total):
        retab = sc.read_retab([SD_NAMES, SD_ALIASES,
                               ["SUDAN", "", 0, "SD", 600, 600, 1200],
                               ["SINNAR", "SINNAR", 1, "SD02", 600, 600, 1200],
                               ["SINJA", "SINNAR", 2, "SD02001", 600, 600, 1200]])
        records, _ = sc.build(retab, sudan_ages(p01_total), [{"id": "S", "name": "Sinnar"}], [])
        return records[0]

    def test_the_median_note_cites_the_count_it_quotes(self):
        state = self.build(1200)
        self.assertIn("(1,200 people of the 1,200 it counted", state["median_age_note"])
        got = cited(state)
        self.assertEqual(got["median_age note"], {sc.RETAB_SOURCE})
        self.assertEqual(got["median_age"], {sc.AGE_SOURCE})
        self.assertEqual(got["sex_ratio"], {sc.RETAB_SOURCE})

    def test_a_state_without_a_median_cites_the_ratio_alone(self):
        state = self.build(1300)
        self.assertNotIn("median_age_note", state)
        self.assertEqual(cited(state), {"sex_ratio": {sc.RETAB_SOURCE}})


# ---------------------------------------------------------- labels as drawn

class RerunAfterARebuild(unittest.TestCase):
    """A rebuild names each polygon as these readers write it and keeps the
    boundary file's label as ``shape_name``; the readers bind on the labels,
    so a re-run after it binds as before."""

    def test_each_reader_reads_the_boundary_file_s_labels(self):
        units = [{"id": "A", "name": "As written", "shape_name": "As labelled"},
                 {"id": "B", "name": "Never renamed"}]
        for module, iso3 in ((tc, "TUN"), (mr, "MAR"), (ec, "EGY"), (lc, "LBY")):
            with site(module, iso3, {"admin1": units, "admin2": units}):
                for level in ("admin1", "admin2"):
                    self.assertEqual([u["name"] for u in module.drawn_units(level)],
                                     ["As labelled", "Never renamed"], module.__name__)

    def test_tunisia_s_declared_label_is_still_found(self):
        # Ouled Chamekh's polygon now shows its French name; DELEGATIONS names
        # its label.
        admin2 = [{"id": "C", "name": "Ouled Chamekh", "shape_name": "والد شامخ", "parent": "G"},
                  {"id": "M", "name": "Mahdia", "shape_name": MARKED, "parent": "G"},
                  {"id": "B", "name": "Chebba", "parent": "G"}]
        with site(tc, "TUN", {"admin1": [{"id": "G", "name": "Mahdia"}], "admin2": admin2}):
            by = tunisia_build(tc.drawn_units("admin1"), tc.drawn_units("admin2"))
        self.assertEqual(by["C"]["name"], "Ouled Chamekh")
        self.assertEqual(by["C"]["aliases"], ["والد شامخ"])
        self.assertEqual(by["M"]["aliases"], ["المهدية"])

    def test_es_semara_s_piece_still_says_why(self):
        # Without the label the piece across the line would not be found, and
        # would be left without its reason.
        levels = {"admin1": [{"id": "R", "name": "Laâyoune-Sakia El Hamra"}],
                  "admin2": [{"id": "S", "name": "Province d'Es-Semara",
                              "shape_name": SEMARA_LABEL, "parent": "R"}]}
        with site(mr, "MAR", levels):
            records, _ = mr.build(semara_table(), mr.drawn_units("admin1"),
                                  mr.drawn_units("admin2"))
        piece = {r["shape_id"]: r for r in records}["S"]
        self.assertEqual(piece["name"], "Province d'Es-Semara")
        self.assertEqual(piece["aliases"], [SEMARA_LABEL])
        self.assertIn("(50 people)", piece["population"]["note"])

    def test_libya_s_areas_keep_their_labels_as_other_names(self):
        named = {"tarabulus": "Tripoli", "darnah": "Darnah"}
        units = [{"id": sid, "name": named.get(key, key.title()),
                  **({"shape_name": LIBYA_LABELS[key]} if key in LIBYA_LABELS else {})}
                 for key, sid in lc.SHAPES.items()]
        with site(lc, "LBY", {"admin1": units, "admin2": units}):
            drawn = {level: lc.drawn_units(level) for level in ("admin1", "admin2")}
        records = libya_build(drawn)
        darnah = [r for r in records if r["shape_id"] == lc.SHAPES["darnah"]][0]
        self.assertEqual(darnah["aliases"], ["Al Qubbah"])
        self.assertIn("Al Qubbah, a name this area is also given", darnah["population_note"])
        tripoli = [r for r in records if r["shape_id"] == lc.SHAPES["tarabulus"]][0]
        self.assertEqual(tripoli["aliases"], ["Tajura' wa an Nawahi al Arba"])


class RunnerCommands(unittest.TestCase):
    """Each reader takes the label its runner command gives it and goes on to
    its source: the commands listed for the re-fetch parse."""

    class Reached(Exception):
        """The reader asked for its source."""

    def test_each_reader_takes_a_run_label(self):
        for module in (tc, mr, ms, ma, ec, lc, sc):
            with mock.patch.object(sys, "argv", [module.__name__, "--run", "final1"]), \
                    mock.patch.object(uscb, "package", side_effect=self.Reached), \
                    mock.patch.object(module, "http_get", side_effect=self.Reached):
                with self.assertRaises(self.Reached, msg=module.__name__):
                    module.main()


if __name__ == "__main__":
    unittest.main()
