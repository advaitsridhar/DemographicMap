"""Offline tests for the reader of the census taken in the north of Cyprus in 2011."""

import copy
import unittest
from collections import Counter
from unittest import mock

from scripts.fetch_census import cyprus_north_census as north
from scripts.fetch_census.balkans_common import shapes

PUBLISHED = {"total": 30.0, "men": 16.0, "women": 14.0}

# Tablo 3's layout: names indented across four columns, then total, men, women.
TABLO_3 = [
    ["İlçe, Bucak, Belediye, Mahalle ve Cinsiyete göre sürekli ikamet eden nüfus", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["İlçe, Bucak, Belediye ve Mahalle", "", "", "", "Toplam", "Cinsiyet", ""],
    ["", "", "", "", "", "Erkek", "Kadın"],
    ["Genel Toplam", "", "", "", 30.0, 16.0, 14.0],
    ["Girne", "İlçe Toplam", "", "", 20.0, 11.0, 9.0],
    ["", "GİRNE MERKEZ", "Bucak Toplamı", "", 20.0, 11.0, 9.0],
    ["", "", "GİRNE", "", 20.0, 11.0, 9.0],
    ["", "", "", "AŞAĞI GİRNE", 12.0, 7.0, 5.0],
    ["", "", "", "YUKARI GİRNE", 8.0, 4.0, 4.0],
    ["İskele", "İlçe Toplam", "", "", 10.0, 5.0, 5.0],
    ["", "MEHMETÇİK", "Bucak Toplamı", "", 10.0, 5.0, 5.0],
    ["", "", "KANTARA", "", 10.0, 5.0, 5.0],
    ["", "", "", "KANTARA", 10.0, 5.0, 5.0],
    ["", "", "", "", "", "", ""],
    ["Pile, Karaman (Yukarı Karmi) ve Kantara mahalleleri herhangi bir belediyeye bağlı "
     "olmadıklarından dolayı nüfusları ayrı olarak verilmiştir.", "", "", "", "", "", ""],
]
# Tablo 1: district, total, men, women.
TABLO_1 = [
    ["İlçe ve Cinsiyete göre sürekli ikamet eden nüfus, 2011", "", "", ""],
    ["", "", "", ""],
    ["İlçe", "Toplam", "Cinsiyet", ""],
    ["", "", "Erkek", "Kadın"],
    ["Genel Toplam", 30.0, 16.0, 14.0],
    ["Girne", 20.0, 11.0, 9.0],
    ["İskele", 10.0, 5.0, 5.0],
]
# Tablo 4: the whole north's column, then each district's total and each
# sub-district's three; single years (the first is the number 0.0), five-year
# sums, and the open top.
TABLO_4 = [
    ["Yaş, Yaş Grubu, İlçe ve Cinsiyete göre sürekli ikamet eden nüfus", "", "", "", "", "", "", "", "", ""],
    ["Yaş\nYaş Grubu", "TOPLAM", "İlçe", "", "", "", "", "", "", ""],
    ["", "", "GİRNE", "", "", "", "İSKELE", "", "", ""],
    ["", "", "Toplam", "Bucak", "", "", "Toplam", "Bucak", "", ""],
    ["", "", "", "GİRNE MERKEZ BUCAĞI", "", "", "", "MEHMETÇİK BUCAĞI", "", ""],
    ["", "", "", "Toplam", "Cinsiyet", "", "", "Toplam", "Cinsiyet", ""],
    ["", "", "", "", "Erkek", "Kadın", "", "", "Erkek", "Kadın"],
    ["Toplam", 30.0, 20.0, 20.0, 11.0, 9.0, 10.0, 10.0, 5.0, 5.0],
    [0.0, 5.0, 3.0, 3.0, 2.0, 1.0, 2.0, 2.0, 1.0, 1.0],
    [1.0, 9.0, 6.0, 6.0, 3.0, 3.0, 3.0, 3.0, 2.0, 1.0],
    ["0 - 4", 16.0, 10.0, 10.0, 5.0, 5.0, 6.0, 6.0, 3.0, 3.0],
    [2.0, 2.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0],
    ["85 VE ÜZERİ", 14.0, 10.0, 10.0, 6.0, 4.0, 4.0, 4.0, 2.0, 2.0],
]
# Tablo 5: citizenship by district, each district's both sexes first.
TABLO_5 = [
    ["", "", "", "", "", "", "", "", "", "", ""],
    ["İlçe, Cinsiyet ve Tabiiyete göre sürekli ikamet eden nüfus, 2011", "", "", "", "", "", "", "", "",
     "", ""],
    ["Tabiiyet", "", "", "", "", "İlçe - Cinsiyet", "", "", "", "", ""],
    ["", "", "", "", "", "GİRNE", "", "", "İSKELE", "", ""],
    ["", "", "TOPLAM", "Erkek", "Kadın", "Toplam", "Erkek", "Kadın", "Toplam", "Erkek", "Kadın"],
    ["GENEL TOPLAM", "", 30.0, 16.0, 14.0, 20.0, 11.0, 9.0, 10.0, 5.0, 5.0],
    ["KKTC TOPLAM", "", 15.0, 8.0, 7.0, 10.0, 5.0, 5.0, 5.0, 3.0, 2.0],
    ["", "YALNIZ KKTC", 9.0, 5.0, 4.0, 6.0, 3.0, 3.0, 3.0, 2.0, 1.0],
    ["", "KKTC - Türkiye", 4.0, 2.0, 2.0, 3.0, 1.0, 2.0, 1.0, 1.0, 0.0],
    ["", "KKTC - Diğer", 2.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0],
    ["TÜRKİYE", "", 10.0, 6.0, 4.0, 7.0, 5.0, 2.0, 3.0, 1.0, 2.0],
    ["Birleşik Krallık", "", 3.0, 1.0, 2.0, 2.0, 1.0, 1.0, 1.0, 0.0, 1.0],
    ["Azerbeycan", "", 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0],
    ["Diğer", "", 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0],
]


class ReadingTest(unittest.TestCase):
    def test_quarters_nest_and_add_up(self):
        t3 = north.quarters(TABLO_3, PUBLISHED)
        self.assertEqual(set(t3["quarters"]), {"girne/asagigirne", "girne/yukarigirne", "kantara/kantara"})
        q = t3["quarters"]["girne/asagigirne"]
        self.assertEqual((q["ilce"], q["bucak"], q["belediye"], q["mahalle"]),
                         ("girne", "girnemerkez", "GİRNE", "AŞAĞI GİRNE"))
        self.assertEqual((q["total"], q["men"], q["women"]), (12.0, 7.0, 5.0))
        self.assertEqual(set(t3["ilces"]), {"girne", "iskele"})
        self.assertEqual(set(t3["bucaks"]), {"girnemerkez", "mehmetcik"})
        self.assertEqual(t3["total"]["total"], 30.0)

    def test_a_quarter_whose_sexes_do_not_add_stops_the_run(self):
        rows = copy.deepcopy(TABLO_3)
        rows[8][5] = 6.0
        with self.assertRaises(SystemExit):
            north.quarters(rows, PUBLISHED)

    def test_quarters_that_do_not_add_to_their_municipality_stop_the_run(self):
        rows = copy.deepcopy(TABLO_3)
        rows[9][4:7] = [9.0, 5.0, 4.0]
        with self.assertRaises(SystemExit):
            north.quarters(rows, PUBLISHED)

    def test_a_total_other_than_the_published_one_stops_the_run(self):
        with self.assertRaises(SystemExit):
            north.quarters(TABLO_3, {"total": 31.0, "men": 16.0, "women": 14.0})
        # And the real table is held to the bulletin's figures.
        self.assertEqual(north.PUBLISHED, {"total": 286257, "men": 150483, "women": 135774})

    def test_districts(self):
        t1 = north.districts(TABLO_1)
        self.assertEqual(t1["total"], {"total": 30.0, "men": 16.0, "women": 14.0})
        self.assertEqual(t1["girne"]["men"], 11.0)

    def test_single_years_read_age_zero_and_the_open_top(self):
        ages = north.single_years(TABLO_4, {"girne", "iskele"})
        self.assertEqual(ages[("total", None)]["ages"], Counter({0: 5, 1: 9, 2: 2, 85: 14}))
        self.assertEqual(ages[("girne", None)]["ages"], Counter({0: 3, 1: 6, 2: 1, 85: 10}))
        self.assertEqual(ages[("girne", None)]["total"], 20.0)
        bucak = ages[("girne", "girnemerkez")]
        self.assertEqual((bucak["total"], bucak["men"], bucak["women"]), (20.0, 11.0, 9.0))
        self.assertEqual(bucak["men_ages"], Counter({0: 2, 1: 3, 2: 0, 85: 6}))
        self.assertIn(("iskele", "mehmetcik"), ages)
        # The tenth of the twenty is the one two-year-old: 2 + (10 - 9) / 1.
        self.assertEqual(north.median_age(ages[("girne", None)]["ages"]), 3.0)

    def test_single_years_that_do_not_add_stop_the_run(self):
        rows = copy.deepcopy(TABLO_4)
        rows[8][2] = 4.0
        with self.assertRaises(SystemExit):
            north.single_years(rows, {"girne", "iskele"})

    def test_citizenship(self):
        cit = north.citizenship(TABLO_5, {"girne", "iskele"})
        self.assertEqual(cit["girne"], {None: 20.0, "TRNC citizen": 6.0, "TRNC and Turkish citizen": 3.0,
                                        "TRNC and other citizen": 1.0, "Turkish citizen": 7.0,
                                        "British citizen": 2.0, "Azerbaijani citizen": 0.0, "Other": 1.0})
        self.assertEqual(cit["total"][None], 30.0)

    def test_an_unknown_citizenship_row_stops_the_run(self):
        rows = copy.deepcopy(TABLO_5)
        rows[12][0] = "Yunanistan"
        with self.assertRaises(SystemExit):
            north.citizenship(rows, {"girne", "iskele"})

    def test_trnc_rows_must_add_to_their_total(self):
        rows = copy.deepcopy(TABLO_5)
        rows[6][5] = 11.0
        with self.assertRaises(SystemExit):
            north.citizenship(rows, {"girne", "iskele"})

    def test_the_four_tables_agree(self):
        t3 = north.quarters(TABLO_3, PUBLISHED)
        ilces = set(t3["ilces"])
        ages = north.single_years(TABLO_4, ilces)
        cit = north.citizenship(TABLO_5, ilces)
        north.check_tables(t3, north.districts(TABLO_1), ages, cit)
        t1 = north.districts(TABLO_1)
        t1["girne"]["men"] = 12.0
        with self.assertRaises(SystemExit):
            north.check_tables(t3, t1, ages, cit)

    def test_text_keeps_a_zero(self):
        self.assertEqual(north.text(0.0), "0.0")
        self.assertEqual(north.text(None), "")
        self.assertEqual(north.text("  Yaş\nYaş  Grubu "), "Yaş Yaş Grubu")


class NamingTest(unittest.TestCase):
    def test_turkish_title_case(self):
        self.assertEqual(north.tr_title("AŞAĞI GİRNE"), "Aşağı Girne")
        self.assertEqual(north.tr_title("İSKELE"), "İskele")
        self.assertEqual(north.tr_title("ILGAZ"), "Ilgaz")
        self.assertEqual(north.tr_title("KARAMAN (YUKARI KARMİ)"), "Karaman (Yukarı Karmi)")
        self.assertEqual(north.tr_title("MALATYA - İNCESU"), "Malatya - İncesu")

    def test_keys_fold_turkish_letters(self):
        self.assertEqual(north.spec_key("GİRNE/AŞAĞI GİRNE"), "girne/asagigirne")
        self.assertEqual(north.spec_key("KARAMAN (YUKARI KARMİ)/KARAMAN (YUKARI KARMİ)"),
                         "karamanyukarikarmi/karamanyukarikarmi")
        self.assertEqual(north.spec_key("ALSANCAK/MALATYA - İNCESU"), "alsancak/malatyaincesu")

    def test_quarter_phrase(self):
        q = {"belediye": "LAPTA (ÇAMLIBEL)", "mahalle": "KORUÇAM"}
        self.assertEqual(north.quarter_phrase(q), "Koruçam, a quarter (mahalle) of Lapta municipality")
        q = {"belediye": "KANTARA", "mahalle": "KANTARA"}
        self.assertIn("of no municipality", north.quarter_phrase(q))

    def test_the_labels_say_citizenship(self):
        labels = set(north.CITIZENSHIP.values())
        self.assertIn("TRNC citizen", labels)
        self.assertIn("TRNC and Turkish citizen", labels)
        self.assertIn("Turkish citizen", labels)
        self.assertIn("Other", labels)
        self.assertTrue(all(label == "Other" or label.endswith("citizen") for label in labels))

    def test_the_named_countries_have_a_place_in_the_tree(self):
        import group_tree
        for label in ("Turkish citizen", "British citizen", "Nigerian citizen", "Pakistani citizen",
                      "Bulgarian citizen", "Azerbaijani citizen", "Turkmen citizen", "Other"):
            self.assertIsNotNone(group_tree.parent_of("ethnicity", label), label)


class TablesTest(unittest.TestCase):
    """The binding tables are a partition: every quarter once, every polygon once."""

    def test_every_quarter_once(self):
        specs = [s for entries in (north.BIND, north.ZERO_IN_REPUBLIC) for _, *ss in entries.values()
                 for s in ss] + list(north.UNPLACED)
        keys = [north.spec_key(s) for s in specs]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 250)          # Tablo 3's quarters

    def test_every_polygon_once(self):
        ids = [sid for t in (north.BIND, north.ZERO_IN_REPUBLIC, north.LEFT_OFF, north.BOTH) for sid in t]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual(set(north.NOTES), set(north.BIND))

    def test_labels_are_the_maps(self):
        drawn = {s["id"]: s["name"] for s in shapes("CYP", "admin2")}
        for table in (north.BIND, north.ZERO_IN_REPUBLIC, north.LEFT_OFF, north.BOTH):
            for sid, entry in table.items():
                self.assertEqual(drawn.get(sid), entry[0], sid)

    def test_no_republic_controlled_district_is_given_a_northern_village(self):
        district = {s["id"]: s["name"] for s in shapes("CYP", "admin1")}
        by_id = {s["id"]: s for s in shapes("CYP", "admin2")}
        for sid in north.BIND:
            self.assertNotIn(district[by_id[sid]["parent"]], {"Paphos", "Limassol"}, north.BIND[sid][0])


def synthetic(admin1, admin2):
    """A Tablo 3 holding every quarter the tables name, each in the district
    its placement says (Girne's quarters exactly those in Kyrenia), and the
    Republic's records as cyprus_census.json writes them today."""
    by_id = {s["id"]: s for s in admin2}
    district = {s["id"]: s["name"] for s in admin1}
    placed = [(s, district[by_id[sid]["parent"]]) for t in (north.BIND, north.ZERO_IN_REPUBLIC)
              for sid, (_, *ss) in t.items() for s in ss]
    placed += [(s, d) for s, (d, _) in north.UNPLACED.items()]
    quarters = {}
    for n, (spec, dname) in enumerate(placed):
        bel, _, mah = spec.partition("/")
        ilce = "girne" if dname == "Kyrenia" else "lefkosa"
        men, women = (16.0, 12.0) if spec == "YENİ BOĞAZİÇİ/SANDALLAR" else (40.0 + n % 7, 40.0)
        quarters[north.spec_key(spec)] = {"ilce": ilce, "bucak": ilce + "merkez", "belediye": bel,
                                          "mahalle": mah, "men": men, "women": women,
                                          "total": men + women}
    ilces = {}
    for name in ("girne", "lefkosa"):
        part = [q for q in quarters.values() if q["ilce"] == name]
        ilces[name] = {k: sum(q[k] for q in part) for k in ("total", "men", "women")}
        ilces[name]["name"] = name.title()
    total = {k: sum(i[k] for i in ilces.values()) for k in ("total", "men", "women")}
    t3 = {"quarters": quarters, "ilces": ilces, "total": total, "bucaks": {}, "municipalities": {}}
    g = ilces["girne"]["total"]
    ages = {("girne", None): {"ages": Counter({30: g / 2, 40: g / 2}), "total": g, "men": 0.0,
                              "women": 0.0}}
    cit = {"girne": {None: g, "TRNC citizen": g - 10, "Other": 10.0}}
    republic = {}
    for sid in list(north.BIND) + list(north.LEFT_OFF):
        republic[sid] = {"population": {"status": "not_available", "note": "not counted"}}
    for sid, (_, count) in north.BOTH.items():
        republic[sid] = {"population": {"value": count, "year": 2021}}
    for sid in north.ZERO_IN_REPUBLIC:
        republic[sid] = {"population": {"value": 0, "year": 2021}}
    return t3, ages, cit, republic


class BuildTest(unittest.TestCase):
    URLS = {k: f"https://example.invalid/{k}" for k in ("mahalle", "ilce", "ages", "citizenship")}

    @classmethod
    def setUpClass(cls):
        cls.admin1 = shapes("CYP", "admin1")
        cls.admin2 = shapes("CYP", "admin2")

    def build(self, t3, ages, cit, republic):
        return north.build(t3, ages, cit, self.admin1, self.admin2, republic, self.URLS)

    def test_records(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        records = self.build(t3, ages, cit, republic)
        admin2 = {r["shape_id"]: r for r in records if r["level"] == "admin2"}
        self.assertEqual(len(admin2), len(north.BIND) + len(north.LEFT_OFF))
        drawn = {s["id"]: s["name"] for s in self.admin2}
        for sid, rec in admin2.items():
            self.assertEqual(rec["name"], drawn[sid])
            self.assertEqual(rec["match_by"], "shape_id")
        # A polygon of several quarters carries their sum and says so.
        ilias = admin2["46923920B56788308456175"]
        want = sum(t3["quarters"][north.spec_key(s)]["total"] for s in north.BIND[ilias["shape_id"]][1:])
        self.assertEqual(ilias["population"]["value"], want)
        self.assertEqual(ilias["population"]["year"], 2011)
        self.assertIn("Boğaztepe", ilias["population_note"])
        self.assertIn("not recognised internationally", ilias["population_note"])
        # One quarter: the note names it, in Turkish title case.
        kepir = admin2["46923920B83418385302054"]
        self.assertIn("Dilekkaya, a quarter (mahalle) of Değirmenlik municipality", kepir["population_note"])
        self.assertEqual(kepir["median_age"]["status"], "not_available")
        self.assertIn("sub-district (bucak)", kepir["median_age"]["note"])
        self.assertIn("citizenship", kepir["ethnicity"]["note"])
        # Below 50 residents no ratio, and the counts said in words.
        santalaris = admin2["46923920B66935539070734"]
        self.assertEqual(santalaris["sex_ratio"]["status"], "not_available")
        self.assertIn("16 men and 12 women", santalaris["sex_ratio"]["note"])
        # A polygon left off says why, and displaces an encyclopaedia's
        # figure from before the census taken in 2011.
        avlona = admin2["46923920B38965206429869"]
        self.assertEqual(avlona["population"]["displaces_before"], 2011)
        self.assertIn("Fyllia", avlona["population"]["note"])
        self.assertIn("effective control", avlona["population"]["note"])
        # A polygon left off for its overlap gives the share measured.
        belapais = admin2["46923920B81569607832165"]
        self.assertNotIn("value", belapais["population"])
        self.assertIn("about 12% of the count", belapais["population"]["note"])
        self.assertIn("at most a tenth", belapais["population"]["note"])
        # A bound polygon with an overlap says how much, within the tenth.
        kioneli = admin2["46923920B14813142167534"]
        self.assertIn("about 5% of this count", kioneli["population_note"])
        # Nothing on the polygons both censuses count a part of, nor (yet) on
        # those the Republic lists empty.
        for sid in list(north.BOTH) + list(north.ZERO_IN_REPUBLIC):
            self.assertNotIn(sid, admin2)
        # Kyrenia: its villages do not cover it, so every field says why it
        # is empty, with the coverage measured, and no district figure of the
        # census is put on it.
        kyrenia = next(r for r in records if r["level"] == "admin1")
        self.assertEqual(kyrenia["name"], "Kyrenia")
        for field in ("population", "sex_ratio", "median_age", "ethnicity", "religion", "language"):
            self.assertEqual(kyrenia[field]["status"], "not_available", field)
            self.assertIn("effective control", kyrenia[field]["note"], field)
        self.assertEqual(kyrenia["population"]["displaces_before"], 2011)
        kyrenia_ids = {s["id"] for s in self.admin2 if s["parent"] == kyrenia["shape_id"]}
        bound = [sid for sid in north.BIND if sid in kyrenia_ids]
        held = sum(t3["quarters"][north.spec_key(s)]["total"] for sid in bound for s in north.BIND[sid][1:])
        note = kyrenia["population"]["note"]
        self.assertIn(f"bound to {len(bound)} of this district's {len(kyrenia_ids)} community polygons", note)
        self.assertIn(f"hold {held:,.0f} of the {t3['ilces']['girne']['total']:,.0f} residents", note)
        self.assertIn("Templos", note)
        self.assertIn("citizenship", kyrenia["ethnicity"]["note"])
        self.assertNotIn("ethnicity_basis", kyrenia)
        self.assertFalse(kyrenia.get("sources"))

    def test_the_empty_communities_are_written_once_the_republic_gives_a_gap(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        for sid in north.ZERO_IN_REPUBLIC:
            republic[sid] = {"population": {"status": "not_available", "note": "outside"}}
        records = self.build(t3, ages, cit, republic)
        written = {r["shape_id"]: r for r in records if r["shape_id"] in north.ZERO_IN_REPUBLIC}
        self.assertEqual(set(written), set(north.ZERO_IN_REPUBLIC))
        self.assertIn("no residents", written["46923920B91087779274595"]["population_note"])

    def test_a_polygon_the_republic_counts_stops_the_run(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        republic["46923920B83418385302054"] = {"population": {"value": 5, "year": 2021}}
        with self.assertRaises(SystemExit):
            self.build(t3, ages, cit, republic)

    def test_a_both_count_that_moved_stops_the_run(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        republic["46923920B48961032543563"] = {"population": {"value": 1, "year": 2021}}
        with self.assertRaises(SystemExit):
            self.build(t3, ages, cit, republic)

    def test_another_districts_quarter_in_kyrenia_stops_the_run(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        t3["quarters"][north.spec_key("ÇATALKÖY/ÇATALKÖY")]["ilce"] = "lefkosa"
        with self.assertRaises(SystemExit):
            self.build(t3, ages, cit, republic)

    def test_a_quarter_placed_nowhere_stops_the_run(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        t3["quarters"]["lefkosa/yeni"] = dict(t3["quarters"][north.spec_key("LEFKOŞA/AKKAVUK")])
        with self.assertRaises(SystemExit):
            self.build(t3, ages, cit, republic)

    def test_the_overlap_rule_is_held_to(self):
        t3, ages, cit, republic = synthetic(self.admin1, self.admin2)
        # A bound polygon measured over the tenth stops the run...
        with mock.patch.dict(north.OVERLAP, {"46923920B83418385302054": ("Agia Kepir", 0.12)}):
            with self.assertRaises(SystemExit):
                self.build(t3, ages, cit, republic)
        # ...and so does one left off for an overlap within it...
        with mock.patch.dict(north.OVERLAP, {"46923920B79471002373027": ("Templos", 0.08)}):
            with self.assertRaises(SystemExit):
                self.build(t3, ages, cit, republic)
        # ...or an entry whose label is not the polygon's.
        with mock.patch.dict(north.OVERLAP, {"46923920B79471002373027": ("Templo", 0.2)}):
            with self.assertRaises(SystemExit):
                self.build(t3, ages, cit, republic)
        # The table as it stands keeps the rule.
        for sid, (label, share) in north.OVERLAP.items():
            self.assertEqual(share <= north.MAX_OVERLAP, sid in north.BIND, label)


class KyreniaTest(unittest.TestCase):
    """The district is filled only from villages that cover it completely."""

    ADMIN1 = [{"id": "K", "name": "Kyrenia"}, {"id": "N", "name": "Nicosia"}]
    ADMIN2 = [{"id": "p1", "name": "Keryneia", "parent": "K"}, {"id": "p2", "name": "Templos", "parent": "K"},
              {"id": "p3", "name": "Kanli", "parent": "N"}]
    URLS = {k: f"https://example.invalid/{k}" for k in ("mahalle", "ilce", "ages", "citizenship")}

    def kyrenia(self, bind, admin2=None):
        t3 = north.quarters(TABLO_3, PUBLISHED)
        ilces = set(t3["ilces"])
        ages = north.single_years(TABLO_4, ilces)
        cit = north.citizenship(TABLO_5, ilces)
        src = {k: north.SOURCE.format(title=v) for k, v in north.TITLES.items()}
        return north.kyrenia(t3, ages, cit, self.ADMIN1, admin2 or self.ADMIN2, 20.0, src, self.URLS,
                             bind=bind)

    def test_complete_coverage_fills_the_district(self):
        rec = self.kyrenia({"p1": ("Keryneia", "GİRNE/AŞAĞI GİRNE"), "p2": ("Templos", "GİRNE/YUKARI GİRNE")})
        self.assertEqual(rec["population"]["value"], 20)
        self.assertEqual(rec["sex_ratio"]["value"], 122.2)       # 11 men, 9 women
        self.assertEqual(rec["median_age"]["value"], 3.0)
        self.assertEqual(rec["ethnicity_basis"], "citizenship")
        groups = {r["group"] for r in rec["ethnicity"]}
        self.assertIn("TRNC citizen", groups)
        self.assertLessEqual(groups, set(north.CITIZENSHIP.values()))
        self.assertAlmostEqual(sum(r["pct"] for r in rec["ethnicity"]), 100.0, places=6)
        self.assertEqual(rec["religion"]["status"], "not_available")

    def test_a_polygon_left_unbound_leaves_the_district_with_its_reason(self):
        rec = self.kyrenia({"p1": ("Keryneia", "GİRNE/AŞAĞI GİRNE")})
        for field in ("population", "sex_ratio", "median_age", "ethnicity"):
            self.assertEqual(rec[field]["status"], "not_available", field)
        self.assertIn("bound to 1 of this district's 2 community polygons, which hold 12 of the 20 "
                      "residents", rec["population"]["note"])
        self.assertIn("The other 1 (Templos)", rec["population"]["note"])

    def test_villages_short_of_the_district_leave_it(self):
        # Every polygon of the district bound, but one of its quarters on none.
        admin2 = [s for s in self.ADMIN2 if s["id"] != "p2"]
        rec = self.kyrenia({"p1": ("Keryneia", "GİRNE/AŞAĞI GİRNE")}, admin2)
        self.assertEqual(rec["population"]["status"], "not_available")
        self.assertIn("which hold 12 of the 20 residents", rec["population"]["note"])


if __name__ == "__main__":
    unittest.main()
