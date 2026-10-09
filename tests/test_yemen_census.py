"""Yemen's 2004 census and 2017 projection reader, on a small country built in memory.

Three governorates: Ibb (11) drawn whole, and the capital (13) and Sana'a
(23) between which the boundary file cuts two "Sana'a City Outskirts" units
the census never counted apart.
"""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import yemen_census as yc  # noqa: E402

GEO = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL", "NSO_CODE"]
AGES = [f"{a:02d}{a + 4:02d}" for a in range(0, 80, 5)]

# code: (name, men, women, five-year groups of the 2017 projection)
DISTRICTS = {
    "1101": ("AL QAFR", 600, 400, [60.0 - 3 * i for i in range(17)]),
    "1102": ("YARIM", 300, 300, [30.0 + i for i in range(17)]),
    "1301": ("ŞAN‘Ā’ AL QADĪMAH", 500, 450, [50.0 - i for i in range(17)]),
    "2301": ("HAMDĀN", 200, 210, [20.0 + (i % 3) for i in range(17)]),
    "2305": ("SANḨAN", 150, 140, [15.0 + (i % 2) for i in range(17)]),
}
GOVERNORATES = {"11": "IBB", "13": "AMĀNAT AL ‘ĀŞIMAH", "23": "ŞAN‘Ā’"}


def census_sheet(drop=None, bump=None):
    names = GEO + ["POP_TPOP", "POP_MPOP", "POP_FPOP", "NAT_YEM_B", "NAT_NYEM_B"]
    rows = [names, names]
    total = {"men": 0, "women": 0}
    by_gov = {g: {"men": 0, "women": 0} for g in GOVERNORATES}
    for code, (name, men, women, _ages) in DISTRICTS.items():
        by_gov[code[:2]]["men"] += men
        by_gov[code[:2]]["women"] += women
    for g, sexes in by_gov.items():
        total["men"] += sexes["men"]
        total["women"] += sexes["women"]

    def row(name, level, code, men, women):
        people = men + women + (bump if bump and code == "1101" else 0)
        foreign = 10 if level == 1 else None
        return [name, None, None, level, code, people, men, women,
                people - foreign if foreign else None, foreign]
    rows.append(row("YEMEN", 0, None, total["men"], total["women"]))
    for g, name in GOVERNORATES.items():
        rows.append(row(name, 1, g, by_gov[g]["men"], by_gov[g]["women"]))
    for code, (name, men, women, _ages) in DISTRICTS.items():
        if code != drop:
            rows.append(row(name, 2, code, men, women))
    return rows


def projection_sheet():
    names = GEO + [f"{s}TOTL_7" for s in "BMF"] + [f"B{g}_7" for g in AGES] + ["B80PL_7"]
    rows = [names, names]

    def row(name, level, code, groups):
        total = sum(groups)
        return [name, None, None, level, code, total, total / 2, total / 2] + list(groups)
    gov_groups = {g: [0.0] * 17 for g in GOVERNORATES}
    for code, (_n, _m, _w, groups) in DISTRICTS.items():
        gov_groups[code[:2]] = [a + b for a, b in zip(gov_groups[code[:2]], groups)]
    national = [sum(gs[i] for gs in gov_groups.values()) for i in range(17)]
    rows.append(row("YEMEN", 0, None, national))
    for g, name in GOVERNORATES.items():
        rows.append(row(name, 1, g, gov_groups[g]))
    for code, (name, _m, _w, groups) in DISTRICTS.items():
        rows.append(row(name, 2, code, groups))
    return rows


def book(**kw):
    return {"Metadata": [["Yemen census 2004; projections 2016-2017"]],
            "Census Population": census_sheet(**kw), "Age-Sex Estimates": projection_sheet()}


OUTSKIRTS_H = "Sana'a City Outskirts - Hamdan"
OUTSKIRTS_S = "Sana'a City Outskirts -Sanhan wa Bani Bahlul"
GAZ = {
    "yem_adm1": [["adm1_name", "adm1_pcode"], ["Ibb", "YE11"], ["Amanat Al Asimah", "YE13"],
                 ["Sana'a", "YE23"]],
    "yem_adm2": [["adm1_name", "adm2_name", "adm2_pcode"],
                 ["Ibb", "Al Qafr", "YE1101"], ["Ibb", "Yarim", "YE1102"],
                 ["Amanat Al Asimah", "Old City", "YE1301"],
                 ["Amanat Al Asimah", OUTSKIRTS_H, "YE1319"],
                 ["Amanat Al Asimah", OUTSKIRTS_S, "YE1324"],
                 ["Sana'a", "Hamdan", "YE2301"], ["Sana'a", "Sanhan wa Bani Bahlul", "YE2305"]],
}
ADMIN1 = [{"id": "g11", "name": "Ibb Governorate", "parent": "YEM"},
          {"id": "g13", "name": "Sanʿaʾ", "parent": "YEM"},
          {"id": "g23", "name": "Sanʿaʾ Governorate", "parent": "YEM"}]
ADMIN2 = [{"id": "d1101", "name": "Al Qafr", "parent": "g11"},
          {"id": "d1102", "name": "Yarim", "parent": "g11"},
          {"id": "d1301", "name": "Old City", "parent": "g13"},
          {"id": "d1319", "name": OUTSKIRTS_H, "parent": "g13"},
          {"id": "d1324", "name": OUTSKIRTS_S, "parent": "g13"},
          {"id": "d2301", "name": "Hamdan", "parent": "g23"},
          {"id": "d2305", "name": "Sanhan wa Bani Bahlul", "parent": "g23"}]
PARENTS = {u["id"]: u["name"] for u in ADMIN1}


def run(the_book=None, gaz=None, admin2=None):
    return yc.build(the_book or book(), gaz or GAZ, ADMIN1, admin2 or ADMIN2, PARENTS)


class TheCensus(unittest.TestCase):
    def setUp(self):
        self.rows, self.ages = run()
        self.by = {r["shape_id"]: r for r in self.rows}
        self.age = {r["shape_id"]: r for r in self.ages}

    def test_a_district_carries_its_census_count_and_sex_ratio(self):
        r = self.by["d1101"]
        self.assertEqual(r["codes"], {"cso": "1101"})
        self.assertEqual(r["population"]["value"], 1000)
        self.assertEqual(r["population"]["year"], 2004)
        self.assertEqual(r["sex_ratio"]["value"], 150.0)
        self.assertEqual(r["sex_ratio"]["unit"], "males_per_100_females")

    def test_a_governorate_is_its_districts_and_carries_nationality(self):
        g = self.by["g11"]
        self.assertEqual(g["population"]["value"], 1600)
        self.assertEqual(g["ethnicity_basis"], "nationality")
        shares = {s["group"]: s["count"] for s in g["ethnicity"]}
        self.assertEqual(shares, {"Yemeni citizens": 1590, "Foreign nationals": 10})
        self.assertIn("Nationality, not ethnicity", g["ethnicity_note"])
        self.assertIn("Mehri", g["ethnicity_note"])

    def test_every_unit_says_why_it_has_no_religion_or_language(self):
        for r in self.by.values():
            for field in ("religion", "language"):
                self.assertEqual(r[field]["status"], "not_available", (r["name"], field))
                self.assertIn("Table 25", r[field]["note"])

    def test_every_unit_without_nationality_says_why(self):
        for r in self.by.values():
            if isinstance(r["ethnicity"], list):
                continue
            self.assertEqual(r["ethnicity"]["status"], "not_available", r["name"])
            self.assertTrue(r["ethnicity"].get("note"), r["name"])
        self.assertIn("published by governorate only", self.by["d1101"]["ethnicity"]["note"])
        self.assertEqual(self.by["d2301"]["ethnicity"]["note"],
                         self.by["d2301"]["population"]["note"])
        cited = [s["field"] for s in self.by["d1101"]["sources"]]
        self.assertNotIn("ethnicity", cited)
        self.assertIn("ethnicity", [s["field"] for s in self.by["g11"]["sources"]])

    def test_the_split_districts_and_their_outskirts_say_why_they_are_empty(self):
        for sid in ("d2301", "d2305", "d1319", "d1324", "g13", "g23"):
            r = self.by[sid]
            self.assertEqual(r["population"]["status"], "not_available", sid)
            self.assertNotIn("value", r["population"], sid)
        self.assertIn("Part of Hamdan district", self.by["d1319"]["population"]["note"])
        self.assertIn("Part of Sanhan wa Bani Bahlul district",
                      self.by["d1324"]["population"]["note"])
        self.assertIn("counts Hamdan district whole (410 people)",
                      self.by["d2301"]["population"]["note"])
        for sid in ("d2301", "d2305", "d1319", "d1324", "g13", "g23"):
            self.assertEqual(self.by[sid]["population"]["displaces_before"],
                             yc.DISPLACES_BEFORE, sid)

    def test_the_outskirts_reason_displaces_an_older_encyclopaedia_figure(self):
        # Wikidata's 111,141 (2004) for the Hamdan outskirts stood on the map
        # beside the reason; the build's merge now drops it for the reason.
        from scripts import build_entities as be
        entity = {"id": "d1319"}
        be.merge_adapter(entity, {"_source": "wikidata_admin2.json",
                                  "population": {"value": 111141, "year": 2004,
                                                 "source": "Wikidata (CC0)"},
                                  "sources": [{"field": "population", "name": "Wikidata"}]})
        row = {k: v for k, v in self.by["d1319"].items() if k != "shape_id"}
        be.merge_adapter(entity, dict(row, _source="yemen_census.json"))
        self.assertEqual(entity["population"]["status"], "not_available")
        self.assertIn("Part of Hamdan district", entity["population"]["note"])
        self.assertNotIn("Wikidata", [s.get("name") for s in entity.get("sources", [])])

    def test_a_count_says_it_is_the_latest_census(self):
        self.assertIn("no census since", self.by["d1101"]["population"]["note"])
        self.assertNotIn("owner", self.by["g11"]["ethnicity_note"])

    def test_medians_come_from_the_projection_and_only_where_shapes_differ(self):
        self.assertEqual(self.age["d1101"]["median_age"]["year"], 2017)
        self.assertIn("projection", self.age["d1101"]["median_age_note"])
        self.assertNotIn("d2301", self.age)
        self.assertNotIn("g13", self.age)

    def test_a_governorate_whose_districts_copy_its_ages_gives_them_no_median(self):
        districts = copy.deepcopy(DISTRICTS)
        districts["1102"] = ("YARIM", 300, 300, [2 * a for a in DISTRICTS["1101"][3]])
        saved = dict(DISTRICTS)
        try:
            DISTRICTS.update(districts)
            _rows, ages = run()
        finally:
            DISTRICTS.clear()
            DISTRICTS.update(saved)
        by = {r["shape_id"] for r in ages}
        self.assertIn("g11", by)
        self.assertNotIn("d1101", by)
        self.assertNotIn("d1102", by)


class TheChecks(unittest.TestCase):
    def test_districts_that_miss_their_governorate_stop_the_run(self):
        with self.assertRaises(SystemExit):
            run(book(bump=7))

    def test_a_code_the_census_lacks_that_is_no_outskirts_unit_stops_the_run(self):
        gaz = copy.deepcopy(GAZ)
        gaz["yem_adm2"].append(["Ibb", "Newtown", "YE1199"])
        admin2 = ADMIN2 + [{"id": "d1199", "name": "Newtown", "parent": "g11"}]
        with self.assertRaises(SystemExit):
            run(gaz=gaz, admin2=admin2)

    def test_an_outskirts_label_naming_no_split_district_stops_the_run(self):
        gaz = copy.deepcopy(GAZ)
        gaz["yem_adm2"][4][1] = "Sana'a City Outskirts - East"
        admin2 = [dict(u, name="Sana'a City Outskirts - East") if u["id"] == "d1319" else u
                  for u in ADMIN2]
        with self.assertRaises(SystemExit):
            run(gaz=gaz, admin2=admin2)


if __name__ == "__main__":
    unittest.main()
