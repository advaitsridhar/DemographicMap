"""Taiwan's townships from the household register: the sums, binding, records, offline.

The village records are synthetic but carry the keys the register's open-data
API answers with (ODRP014 ages by sex, ODRP013 indigenous status, ODRP018
peoples), two villages in each of two townships.
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import taiwan_townships as tt  # noqa: E402
from scripts.fetch_census._shared import NOT_COLLECTED  # noqa: E402
from scripts.fetch_census.taiwan import COUNTIES  # noqa: E402

WUQIU = "52511910B62500214534323"


def ages_record(code, site, village, men_by_age, women_by_age):
    r = {"statistic_yyymm": "11508", "district_code": code, "site_id": site, "village": village,
         "people_total": str(sum(men_by_age) + sum(women_by_age)),
         "people_total_m": str(sum(men_by_age)), "people_total_f": str(sum(women_by_age))}
    for sex, ages in (("m", men_by_age), ("f", women_by_age)):
        for age in range(100):
            r[f"people_age_{age:03d}_{sex}"] = str(ages[age])
        r[f"people_age_100up_{sex}"] = str(ages[100])
    return r


def status_record(code, site, village, men, women, plain=(0, 0), mountain=(0, 0)):
    return {"district_code": code, "site_id": site, "village": village,
            "nindigenous_total_m": str(men - plain[0] - mountain[0]),
            "nindigenous_total_f": str(women - plain[1] - mountain[1]),
            "indigenous_plain_total_m": str(plain[0]), "indigenous_plain_total_f": str(plain[1]),
            "indigenous_mountain_total_m": str(mountain[0]),
            "indigenous_mountain_total_f": str(mountain[1]),
            "indigenous_pingpu_total_m": "0", "indigenous_pingpu_total_f": "0"}


def peoples_record(code, site, village, **people):
    r = {"district_code": code, "site_id": site, "village": village}
    for key in tt.PEOPLES:
        m, f = people.get(key, (0, 0))
        r[f"indigenous_{key}_m"], r[f"indigenous_{key}_f"] = str(m), str(f)
    r["indigenous_total"] = str(sum(m + f for m, f in people.values()))
    return r


def flat(n, until=80):
    """n people at every age below ``until``, none older."""
    return [n if a < until else 0 for a in range(101)]


def villages():
    ages = [ages_record("65000010001", "新北市板橋區", "留侯里", flat(2), flat(3)),
            ages_record("65000010002", "新北市板橋區", "流芳里", flat(1, 40), flat(1, 40)),
            ages_record("10014010001", "臺東縣臺東市", "中山里", flat(1), flat(1))]
    status = [status_record("65000010001", "新北市板橋區", "留侯里", 160, 240, plain=(3, 9),
                            mountain=(2, 0)),
              status_record("65000010002", "新北市板橋區", "流芳里", 40, 40),
              status_record("10014010001", "臺東縣臺東市", "中山里", 80, 80, mountain=(40, 40))]
    peoples = [peoples_record("65000010001", "新北市板橋區", "留侯里", amis=(2, 8),
                              paiwan=(1, 1), bunun=(2, 0)),
               peoples_record("65000010002", "新北市板橋區", "流芳里"),
               peoples_record("10014010001", "臺東縣臺東市", "中山里", pinuyumayan=(30, 30),
                              siraya=(4, 4), undeclared=(6, 6))]
    return ages, status, peoples


class Aggregate(unittest.TestCase):
    def test_villages_add_up_to_townships(self):
        towns = tt.aggregate(*villages())
        self.assertEqual(sorted(towns), ["10014010", "65000010"])
        banqiao = towns["65000010"]
        self.assertEqual(banqiao["name"], "新北市板橋區")
        self.assertEqual((banqiao["men"], banqiao["women"]), (200, 280))
        self.assertEqual(banqiao["ages"]["m"][0], 3)
        self.assertEqual(banqiao["ages"]["f"][50], 3)
        self.assertEqual(banqiao["peoples"]["Amis"], 10)
        self.assertEqual(banqiao["peoples"]["Bunun"], 2)
        taitung = towns["10014010"]
        self.assertEqual(taitung["peoples"]["Puyuma"], 60)
        self.assertEqual(taitung["peoples"][tt.PINGPU], 8)
        self.assertEqual(taitung["peoples"]["Indigenous Taiwanese (people not declared)"], 12)

    def test_single_years_that_miss_the_total_are_refused(self):
        ages, status, peoples = villages()
        ages[0]["people_age_030_m"] = "9"
        with self.assertRaises(SystemExit):
            tt.aggregate(ages, status, peoples)

    def test_men_and_women_that_miss_the_total_are_refused(self):
        ages, status, peoples = villages()
        ages[1]["people_total"] = "81"
        with self.assertRaises(SystemExit):
            tt.aggregate(ages, status, peoples)

    def test_status_that_counts_other_people_is_refused(self):
        ages, status, peoples = villages()
        status[2]["nindigenous_total_f"] = "41"
        with self.assertRaises(SystemExit):
            tt.aggregate(ages, status, peoples)

    def test_peoples_that_miss_the_indigenous_count_are_refused(self):
        ages, status, peoples = villages()
        peoples[0]["indigenous_amis_f"] = "7"
        peoples[0]["indigenous_total"] = "13"
        with self.assertRaises(SystemExit):
            tt.aggregate(ages, status, peoples)

    def test_a_village_missing_from_a_dataset_is_refused(self):
        ages, status, peoples = villages()
        with self.assertRaises(SystemExit):
            tt.aggregate(ages, status, peoples[:2])

    def test_a_township_with_two_names_is_refused(self):
        ages, status, peoples = villages()
        ages[1]["site_id"] = "新北市三重區"
        with self.assertRaises(SystemExit):
            tt.aggregate(ages, status, peoples)


def register():
    """A township for every polygon the tables name, each with a small population."""
    towns = {}
    names = [(code, name) for code, name in tt.TOWNSHIPS.values()]
    names += [(f"9900{i:04d}", name) for i, name in enumerate(tt.BY_NAME.values())]
    for i, (code, name) in enumerate(names):
        men = Counter({a: 1 + (i % 3) for a in range(70)})
        women = Counter({a: 1 + (i % 2) for a in range(75)})
        towns[code] = {"name": name.replace("臺", "台") if i % 5 == 0 else name,
                       "men": sum(men.values()), "women": sum(women.values()),
                       "ages": {"m": men, "f": women},
                       "peoples": Counter({"Amis": i % 4, tt.PINGPU: i % 2})}
    return towns


def maps():
    admin1 = [{"id": f"C-{drawn}", "name": drawn} for drawn, _ in COUNTIES.values()]
    county_id = {zh: f"C-{drawn}" for zh, (drawn, _) in COUNTIES.items()}
    admin2 = []
    shapes = [(shape, name) for shape, (_, name) in tt.TOWNSHIPS.items()]
    shapes += list(tt.BY_NAME.items())
    for shape, name in shapes:
        county = next(zh for zh in COUNTIES if name.startswith(zh))
        parent = "TWN" if shape == WUQIU else county_id[county]
        admin2.append({"id": shape, "name": f"drawn {shape[-4:]}", "parent": parent})
    return admin1, admin2


class Tables(unittest.TestCase):
    def test_every_polygon_once(self):
        self.assertEqual(len(tt.TOWNSHIPS), 364)
        self.assertEqual(len(tt.BY_NAME), 4)
        self.assertFalse(set(tt.TOWNSHIPS) & set(tt.BY_NAME))
        codes = [code for code, _ in tt.TOWNSHIPS.values()]
        self.assertEqual(len(set(codes)), 364)
        self.assertTrue(all(len(c) == 8 and c.isdigit() for c in codes))
        names = [name for _, name in tt.TOWNSHIPS.values()] + list(tt.BY_NAME.values())
        self.assertEqual(len(set(names)), 368)

    def test_every_township_in_a_county(self):
        for _, name in list(tt.TOWNSHIPS.values()) + [(None, n) for n in tt.BY_NAME.values()]:
            self.assertTrue(any(name.startswith(zh) for zh in COUNTIES), name)

    def test_the_peoples(self):
        recognised = {v for v in tt.PEOPLES.values()
                      if v != tt.PINGPU and not v.startswith("Indigenous Taiwanese")}
        self.assertEqual(len(recognised), 16)
        self.assertEqual(sum(v == tt.PINGPU for v in tt.PEOPLES.values()), 10)


class Bind(unittest.TestCase):
    def test_one_to_one(self):
        _, admin2 = maps()
        bound = tt.bind(register(), admin2)
        self.assertEqual(len(bound), 368)
        self.assertEqual(len(set(bound.values())), 368)
        self.assertEqual(bound["52511910B38062779232785"], "09007020")

    def test_a_renamed_township_is_refused(self):
        _, admin2 = maps()
        towns = register()
        towns["09007020"]["name"] = "連江縣南竿鄉"
        with self.assertRaises(SystemExit):
            tt.bind(towns, admin2)

    def test_a_missing_township_is_refused(self):
        _, admin2 = maps()
        towns = register()
        del towns["09007030"]
        with self.assertRaises(SystemExit):
            tt.bind(towns, admin2)

    def test_an_undrawn_township_is_refused(self):
        _, admin2 = maps()
        towns = register()
        towns["99990000"] = dict(towns["09007020"], name="新北市不存在區")
        with self.assertRaises(SystemExit):
            tt.bind(towns, admin2)

    def test_a_polygon_with_no_township_is_refused(self):
        _, admin2 = maps()
        admin2.append({"id": "extra", "name": "Extra", "parent": "TWN"})
        with self.assertRaises(SystemExit):
            tt.bind(register(), admin2)


def table6(county, rows, sign=False):
    """Table 6 of a county report as openpyxl reads it: the title, the heads in
    two languages, the 按鄉鎮市區別分 block (county row first) and a note."""
    heads = ["國語", "閩南語", "客語", "原住民族語"] + (["臺灣手語"] if sign else []) + ["其他"]
    width = 2 + len(heads)
    blank = [None] * (width + 8)
    out = [list(blank) for _ in range(16)]
    out[0][1], out[0][2] = "單位：人", "民國109年"
    out[1][1] = f"表６ {county}６歲以上本國籍常住人口使用語言情形"
    out[6][2] = "６歲以上 本國籍常住 人口（人）"
    out[6][3] = "每百位常住人口目前主要使用語言"
    for j, h in enumerate(heads):
        out[9][3 + j] = h
    for j, h in enumerate(["國語", "閩南語", "客語", "原住民族語", "其他語言", "不知或無"]):
        out[9][width + 2 + j] = h
    out[15][1] = "按鄉鎮市區別分"
    for name, base, shares in rows:
        row = list(blank)
        row[1], row[2] = name, base
        for j, v in enumerate(shares):
            row[3 + j] = v
        out.append(row)
    note = list(blank)
    note[1] = "註：其他包括其他語言、不知或無；"
    out.append(note)
    return out


BANQIAO = ("板橋區", 300, [76.3, 23.3, 0.3, 0, 0.1])
WULAI = ("烏來區", 100, [83.1, 11.9, 0.1, 4.9, 0])
COUNTY = ("新北市", 400, [78.0, 20.5, 0.3, 1.2, 0.1])


class Language(unittest.TestCase):
    def test_townships_read_and_the_county_row_left_out(self):
        table = tt.read_language_table(table6("新北市", [COUNTY, BANQIAO, WULAI]), "新北市")
        self.assertEqual(sorted(table), ["新北市板橋區", "新北市烏來區"])
        self.assertEqual(table["新北市烏來區"]["base"], 100)
        self.assertEqual(table["新北市烏來區"]["main"]["Taiwanese indigenous languages"], 4.9)
        self.assertEqual(table["新北市板橋區"]["main"]["Mandarin"], 76.3)

    def test_a_sign_language_column_goes_to_other(self):
        rows = [("新北市", 400, [78.0, 20.5, 0.3, 1.2, 0.05, 0.05]),
                ("板橋區", 300, [76.3, 23.3, 0.3, 0, 0.0, 0.1]),
                ("烏來區", 100, [83.1, 11.9, 0.1, 4.9, 0.0, 0])]
        table = tt.read_language_table(table6("新北市", rows, sign=True), "新北市")
        self.assertAlmostEqual(table["新北市板橋區"]["main"]["Other languages"], 0.1)

    def test_a_row_far_from_a_hundred_is_refused(self):
        rows = [COUNTY, ("板橋區", 300, [76.3, 20.3, 0.3, 0, 0.1]), WULAI]
        with self.assertRaises(SystemExit):
            tt.read_language_table(table6("新北市", rows), "新北市")

    def test_townships_that_miss_the_county_are_refused(self):
        rows = [("新北市", 401, COUNTY[2]), BANQIAO, WULAI]
        with self.assertRaises(SystemExit):
            tt.read_language_table(table6("新北市", rows), "新北市")

    def test_a_county_row_its_townships_do_not_make_is_refused(self):
        rows = [("新北市", 400, [70.0, 28.5, 0.3, 1.1, 0.1]), BANQIAO, WULAI]
        with self.assertRaises(SystemExit):
            tt.read_language_table(table6("新北市", rows), "新北市")

    def test_another_county_s_table_is_refused(self):
        with self.assertRaises(SystemExit):
            tt.read_language_table(table6("臺北市", [COUNTY, BANQIAO, WULAI]), "新北市")

    def test_the_block_ends_at_the_next_block(self):
        # Keelung's sheet runs straight on into 按性別分 with no note between.
        rows = table6("新北市", [COUNTY, BANQIAO, WULAI])
        note = rows.pop()
        width = len(note)
        head = [None] * width
        head[1] = "按性別分"
        total = [None] * width
        total[1], total[2] = "總計", 400
        for j, v in enumerate(COUNTY[2]):
            total[3 + j] = v
        table = tt.read_language_table(rows + [head, total, note], "新北市")
        self.assertEqual(sorted(table), ["新北市板橋區", "新北市烏來區"])

    def test_the_rows(self):
        rows = tt.language_rows({"Mandarin": 83.1, "Taiwanese Hokkien": 11.9, "Hakka": 0.1,
                                 "Taiwanese indigenous languages": 4.9, "Other languages": 0})
        self.assertEqual([r["group"] for r in rows],
                         ["Mandarin", "Taiwanese Hokkien", "Taiwanese indigenous languages",
                          "Hakka"])


def spoken(towns):
    """A Table 6 row for every township the register has."""
    return {t["name"].replace("台", "臺"): {"base": 100, "main": {
        "Mandarin": 60.0, "Taiwanese Hokkien": 39.0, "Hakka": 0.5,
        "Taiwanese indigenous languages": 0.5, "Other languages": 0.0}}
        for t in towns.values()}


class LanguageBound(unittest.TestCase):
    def test_every_township_gets_its_row(self):
        admin1, admin2 = maps()
        towns = register()
        records = tt.build(towns, admin1, admin2, spoken(towns), hakka={})
        r = next(r for r in records if r.get("shape_id") == "52511910B38062779232785")
        self.assertEqual(r["language"][0], {"group": "Mandarin", "pct": 60.0})
        self.assertEqual(r["language_year"], 2020)
        self.assertIn("連江縣's report", r["language_note"])
        self.assertTrue(any(src["field"] == "language" and src["url"].endswith("230907/t006.xlsx")
                            for src in r["sources"]))
        counties = [r for r in records if r["level"] == "admin1"]
        self.assertTrue(all(c["language"] == {"status": "not_available"} for c in counties))

    def test_a_township_with_no_row_is_refused(self):
        admin1, admin2 = maps()
        towns = register()
        language = spoken(towns)
        language.pop("連江縣北竿鄉")
        with self.assertRaises(SystemExit):
            tt.build(towns, admin1, admin2, language, hakka={})

    def test_a_row_with_no_township_is_refused(self):
        admin1, admin2 = maps()
        towns = register()
        language = spoken(towns)
        language["新北市不存在區"] = language["連江縣北竿鄉"]
        with self.assertRaises(SystemExit):
            tt.build(towns, admin1, admin2, language, hakka={})


class Records(unittest.TestCase):
    def setUp(self):
        admin1, admin2 = maps()
        self.towns = register()
        self.records = tt.build(self.towns, admin1, admin2, hakka={})
        self.by_shape = {r["shape_id"]: r for r in self.records}

    def test_counts(self):
        levels = Counter(r["level"] for r in self.records)
        self.assertEqual(levels, {"admin2": 368, "admin1": 22})

    def test_township(self):
        r = self.by_shape["52511910B38062779232785"]
        self.assertEqual(r["match_by"], "shape_id")
        self.assertEqual(r["codes"], {"ris": "09007020"})
        town = self.towns["09007020"]
        self.assertEqual(r["population"]["value"], town["men"] + town["women"])
        self.assertEqual(r["sex_ratio"]["value"], round(100 * town["men"] / town["women"], 1))
        self.assertEqual(r["sex_ratio"]["unit"], "males_per_100_females")
        self.assertIsNotNone(r["median_age"]["value"])
        groups = {row["group"]: row["pct"] for row in r["ethnicity"]}
        self.assertIn(tt.NON_INDIGENOUS, groups)
        self.assertAlmostEqual(sum(groups.values()), 100.0, places=6)
        self.assertEqual(r["ethnicity_basis"], tt.ETHNICITY_BASIS)
        self.assertEqual(r["religion"]["status"], NOT_COLLECTED)
        self.assertEqual(r["language"]["status"], "not_available")
        self.assertIn("by county", r["language"]["note"])

    def test_a_polygon_labelled_with_another_township_s_name_carries_its_own(self):
        drawn = {u["id"]: u["name"] for u in maps()[1]}
        xinying = self.by_shape["52511910B15727969780764"]
        self.assertEqual(xinying["codes"], {"ris": "67000010"})
        self.assertEqual(xinying["name"], "Xinying")
        self.assertEqual(xinying["aliases"], [drawn["52511910B15727969780764"],
                                              self.towns["67000010"]["name"]])
        self.assertIn("labels this polygon 'Xiaying'", xinying["population_note"])
        # 下營 keeps its own drawn label, and no other polygon is renamed.
        xiaying = self.by_shape["52511910B67622492960002"]
        self.assertEqual(xiaying["codes"], {"ris": "67000080"})
        self.assertNotIn("labels this polygon", xiaying["population_note"])
        renamed = [r for r in self.records if r["level"] == "admin2"
                   and r.get("shape_id") not in tt.RELABELLED
                   and r["aliases"][0] != self.towns[r["codes"]["ris"]]["name"]]
        self.assertEqual(renamed, [])

    def test_wuqiu_hangs_from_the_country(self):
        self.assertEqual(self.by_shape[WUQIU]["parent"], "TWN")
        other = self.by_shape["52511910B21260910933226"]
        self.assertEqual(other["parent"], "TWN-kinmen")

    def test_counties_add_up_their_townships(self):
        counties = [r for r in self.records if r["level"] == "admin1"]
        towns = [r for r in self.records if r["level"] == "admin2"]
        self.assertEqual(sum(r["population"]["value"] for r in counties),
                         sum(r["population"]["value"] for r in towns))
        matsu = next(r for r in counties if r["name"] == "Matsu Islands")
        self.assertEqual(matsu["id"], "TWN-matsu-islands")
        # A bare marker: the build lets it displace neither the county's
        # census language nor its modelled religion.
        self.assertEqual(matsu["language"], {"status": "not_available"})
        self.assertEqual(matsu["religion"], {"status": "not_available"})
        self.assertIsNotNone(matsu["median_age"]["value"])

    def test_a_county_counts_its_townships_indigenous_status(self):
        counties = {r["name"]: r for r in self.records if r["level"] == "admin1"}
        matsu = counties["Matsu Islands"]
        towns = [t for t in self.towns.values() if t["name"].replace("台", "臺").startswith("連江縣")]
        people = sum(t["men"] + t["women"] for t in towns)
        amis = sum(t["peoples"]["Amis"] for t in towns)
        self.assertEqual(matsu["ethnicity_basis"], tt.ETHNICITY_BASIS)
        self.assertEqual(matsu["ethnicity_year"], 2026)
        self.assertEqual(sum(row["count"] for row in matsu["ethnicity"]), people)
        self.assertEqual(sum(row["pct"] for row in matsu["ethnicity"]), 100.0)
        self.assertIn(f"of the {people:,} registered people of this county", matsu["ethnicity_note"])
        self.assertEqual(next(row["count"] for row in matsu["ethnicity"] if row["group"] == "Amis"),
                         amis)
        self.assertIn("No count divides the non-indigenous majority", matsu["ethnicity_note"])
        self.assertEqual({src["field"] for src in matsu["sources"]},
                         {"population/median_age/sex_ratio", "ethnicity"})

    def test_kinmen_counts_wuqiu(self):
        counties = {r["name"]: r for r in self.records if r["level"] == "admin1"}
        kinmen = [t for t in self.towns.values() if t["name"].replace("台", "臺").startswith("金門縣")]
        self.assertTrue(any("烏坵" in t["name"] for t in kinmen))
        self.assertEqual(counties["Kinmen"]["population"]["value"],
                         sum(t["men"] + t["women"] for t in kinmen))
        self.assertEqual(sum(row["count"] for row in counties["Kinmen"]["ethnicity"]),
                         counties["Kinmen"]["population"]["value"])

    def test_the_county_note_quotes_the_hakka_survey(self):
        admin1, admin2 = maps()
        records = tt.build(self.towns, admin1, admin2, hakka={"Hsinchu": 30.3})
        hsinchu = next(r for r in records if r["level"] == "admin1" and r["name"] == "Hsinchu")
        self.assertIn("estimated that 30.3% of the county's registered residents meet the Hakka "
                      "Basic Act's definition", hsinchu["ethnicity_note"])
        self.assertIn("stands in place of a modelled split", hsinchu["ethnicity_note"])
        self.assertTrue(any(src["name"] == tt.HAKKA_SOURCE and src["field"].startswith("ethnicity (")
                            for src in hsinchu["sources"]))
        taipei = next(r for r in records if r["level"] == "admin1" and r["name"] == "Taipei")
        self.assertNotIn("Hakka Affairs Council", taipei["ethnicity_note"])
        self.assertFalse(any(src["name"] == tt.HAKKA_SOURCE for src in taipei["sources"]))

    def test_hakka_shares_read_from_the_model_s_note(self):
        model = [{"name": "Hsinchu", "ethnicity": {"status": "modelled", "note": (
                     "Modelled from three official figures: ..., the Hakka Affairs Council's 2021 "
                     "survey estimate that 30.3% of the county meets the Hakka Basic Act "
                     "definition, and ...")}},
                 {"name": "Taipei", "ethnicity": {"status": "not_available"}},
                 {"name": "Kinmen", "ethnicity": [{"group": "Hoklo Taiwanese", "pct": 90.0}]}]
        self.assertEqual(tt.hakka_shares(model), {"Hsinchu": 30.3})

    def test_median_from_single_years(self):
        town = {"name": "x", "men": 0, "women": 0, "peoples": Counter(),
                "ages": {"m": Counter({20: 10, 21: 10}), "f": Counter({30: 20})}}
        town["men"], town["women"] = 20, 20
        r = tt.township_record("s", "00000000", town, "X", "TWN")
        self.assertEqual(r["median_age"]["value"], 22.0)
        self.assertEqual(r["sex_ratio"]["value"], 100.0)
        self.assertEqual(r["ethnicity"], [{"group": tt.NON_INDIGENOUS, "pct": 100.0, "count": 40}])
        self.assertEqual(r["sex_ratio_note"], "20 men and 20 women.")


class Notes(unittest.TestCase):
    def town(self, peoples, total):
        return {"name": "x", "men": total // 2, "women": total - total // 2,
                "peoples": Counter(peoples),
                "ages": {"m": Counter({30: total // 2}), "f": Counter({30: total - total // 2})}}

    def test_a_pool_that_shows_is_described(self):
        # Five peoples of 2 or 3 each in 20,000 people: none shows alone, 12
        # together do (0.06% rounds to 0.1).
        peoples = {"Amis": 3000, "Bunun": 3, "Seediq": 2, "Truku": 3, "Tsou": 2, "Thao": 2}
        r = tt.township_record("s", "00000000", self.town(peoples, 20_000), "X", "TWN")
        groups = {row["group"] for row in r["ethnicity"]}
        self.assertIn(tt.OTHER_PEOPLES, groups)
        self.assertIn(f"'{tt.OTHER_PEOPLES}' is the 12 people of 5 groups too few here to show at "
                      "one decimal (Bunun, Seediq, Thao, Truku, Tsou).", r["ethnicity_note"])
        self.assertNotIn("not drawn", r["ethnicity_note"])

    def test_a_pool_too_small_to_show_is_not_described_as_a_group(self):
        # Budai: 12 people of 5 peoples in 23,199 is 0.05%, which rounds to 0.0.
        peoples = {"Amis": 95, "Atayal": 12, "Paiwan": 19, "Bunun": 3, "Seediq": 2,
                   "Truku": 3, "Tsou": 2, "Yami (Tao)": 2}
        r = tt.township_record("s", "00000000", self.town(peoples, 23_199), "X", "TWN")
        self.assertNotIn(tt.OTHER_PEOPLES, {row["group"] for row in r["ethnicity"]})
        self.assertNotIn(f"'{tt.OTHER_PEOPLES}' is", r["ethnicity_note"])
        self.assertIn(" 12 people of 5 groups too few to show at one decimal (Bunun, Seediq, "
                      "Truku, Tsou, Yami (Tao)) are counted in the total but not drawn.",
                      r["ethnicity_note"])

    def test_one_person_is_one_person(self):
        r = tt.township_record("s", "00000000", self.town({"Thao": 1}, 23_199), "X", "TWN")
        self.assertIn(" 1 person of one group too few to show at one decimal (Thao) is counted in "
                      "the total but not drawn.", r["ethnicity_note"])

    def test_a_usual_sex_ratio_gives_the_counts_only(self):
        ages = {"m": Counter({30: 100, 70: 10}), "f": Counter({30: 100, 70: 15})}
        self.assertEqual(tt.sex_note(110, 115, ages), "110 men and 115 women.")

    def test_a_far_out_sex_ratio_gives_the_working_ages_apart(self):
        # Juguang-like: a surplus of men of working age.
        ages = {"m": Counter({10: 50, 30: 900, 64: 100, 65: 50}),
                "f": Counter({10: 50, 30: 400, 64: 100, 70: 50})}
        note = tt.sex_note(1100, 600, ages)
        self.assertEqual(note, "1,100 men and 600 women. Among those aged 20 to 64, 200.0 men per "
                               "100 women (1,000 men, 500 women); at other ages, 100.0.")


if __name__ == "__main__":
    unittest.main()
