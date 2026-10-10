"""Israel's CBS Table 2.17, read from rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import israel_cbs as ic  # noqa: E402


def row(label, foreign, arabs, jews):
    israelis = round(arabs + jews, 1)
    return [label, foreign, arabs, jews, israelis, round(israelis + foreign, 1)]


SUBS = {
    "JERUSALEM DISTRICT": [],
    "NORTHERN DISTRICT": [("Zefat", 1.9, 14.4, 118.6), ("Kinneret", 1.9, 36.1, 86.9),
                          ("Yizre'el", 4.6, 299.2, 261.3), ("Akko", 3.1, 444.0, 240.9),
                          ("Golan(6)", 0.7, 27.4, 28.8)],
    "HAIFA DISTRICT": [("Haifa", 10.2, 76.8, 546.4), ("Hadera", 4.8, 205.8, 304.7)],
    "CENTRAL DISTRICT": [("Sharon", 10.2, 107.2, 395.6), ("Petah Tiqwa", 1.0, 10.0, 700.0),
                         ("Ramla", 1.0, 80.0, 300.0), ("Rehovot", 2.0, 2.0, 600.0)],
    "TEL AVIV DISTRICT": [],
    "SOUTHERN DISTRICT": [("Ashqelon", 2.0, 1.0, 600.0), ("Be'er Sheva", 5.0, 300.0, 500.0)],
}


def sheet():
    rows = [["TOTAL POPULATION", 0, 0, 0, 0, 0]]
    totals = [0.0, 0.0, 0.0]
    for district, subs in SUBS.items():
        if subs:
            f = round(sum(s[1] for s in subs), 1)
            a = round(sum(s[2] for s in subs), 1)
            j = round(sum(s[3] for s in subs), 1)
        elif district == "JERUSALEM DISTRICT":
            f, a, j = 52.4, 405.4, 840.4
        else:
            f, a, j = 30.0, 26.7, 1400.0
        totals = [totals[0] + f, totals[1] + a, totals[2] + j]
        rows.append(row(district, f, a, j))
        if district == "JERUSALEM DISTRICT":
            rows.append(row("   Judean Mountains", 49.2, 405.0, 652.7))
        for name, sf, sa, sj in subs:
            rows.append(row(f"   {name} S.D.", sf, sa, sj))
    rows[0] = row("TOTAL POPULATION(5)", *[round(t, 1) for t in totals])
    return {"ST02-17a": rows}


ADMIN1 = [{"id": f"d{i}", "name": n, "parent": "ISR"}
          for i, n in enumerate(["Jerusalem District", "Northern District", "Haifa",
                                 "Central District", "Tel Aviv", "Southern District"])]
PARENTS = {u["id"]: u["name"] for u in ADMIN1}
ADMIN2 = ([{"id": "s-jer", "name": "Jerusalem", "parent": "d0"}]
          + [{"id": f"s-{n}", "name": n, "parent": "d1"}
             for n in ("Zefat", "Kinneret", "Yizre'el", "Akko", "Golan")]
          + [{"id": f"s-{n}", "name": n, "parent": "d2"} for n in ("Haifa", "Hadera")]
          + [{"id": f"s-{n}", "name": n, "parent": "d3"}
             for n in ("HaSharon", "Petah Tiqwa", "Ramla", "Rehovot")]
          + [{"id": "s-ta", "name": "Tel Aviv", "parent": "d4"}]
          + [{"id": f"s-{n}", "name": n, "parent": "d5"} for n in ("Ashqelon", "Be'er Sheva")])


class TheReader(unittest.TestCase):
    def setUp(self):
        self.out = {r["shape_id"]: r for r in
                    ic.build(ic.read(sheet()), ADMIN1, ADMIN2, PARENTS)}

    def test_northern_district_leaves_the_golan_out(self):
        north = self.out["d1"]
        made = sum(1000 * (f + a + j) for n, f, a, j in SUBS["NORTHERN DISTRICT"]
                   if not n.startswith("Golan"))
        self.assertAlmostEqual(north["population"]["value"], made, delta=1)
        self.assertIn("other than the Golan", north["population"]["note"])

    def test_golan_and_jerusalem_say_why_they_are_empty(self):
        for sid in ("s-Golan", "s-jer", "d0"):
            self.assertEqual(self.out[sid]["population"]["status"], "not_available", sid)
        self.assertIn("Quneitra", self.out["s-Golan"]["population"]["note"])
        self.assertIn("East", self.out["d0"]["population"]["note"])

    def test_jerusalem_names_the_city_without_a_population(self):
        # Every published figure for the city counts East Jerusalem, which the
        # map draws in the West Bank: the shapes name the city, say why no
        # population is given for it, and carry none.
        for sid in ("s-jer", "d0"):
            rec = self.out[sid]
            self.assertEqual(rec["largest_settlement"], "Jerusalem", sid)
            self.assertNotIn("largest_settlement_population", rec)
            self.assertIn("East Jerusalem", rec["largest_settlement_note"])
            self.assertIn("largest settlement",
                          {s["field"] for s in rec["sources"]})
        # The Golan names no settlement and the other shapes are left to the
        # build's own placement.
        for sid in ("s-Golan", "s-Haifa", "d1"):
            self.assertEqual(self.out[sid]["largest_settlement"]["status"], "not_available")
            self.assertNotIn("largest_settlement_note", self.out[sid])

    def test_jerusalem_settlement_keeps_the_build_from_attaching_a_figure(self):
        # The build fills a settlement only where none is named, and attaches
        # GeoNames' population when it does. Run its two steps on the record.
        from scripts import build_entities as be
        for sid in ("s-jer", "d0"):
            row = dict(self.out[sid], _source=ic.OUT, _match="shape_id")
            entity = {"id": sid, "name": row["name"], "sources": []}
            be.merge_adapter(entity, row)
            towns = {sid: {"name": "Jerusalem", "population": 971800,
                           "source": "GeoNames (CC BY 4.0)"}}
            real = be.read_json
            be.read_json = lambda path, default=None: towns
            try:
                filled = be.fill_settlements_from_geonames({"ISR": [entity]}, {})
            finally:
                be.read_json = real
            self.assertEqual(filled, 0, sid)
            self.assertEqual(entity["largest_settlement"], "Jerusalem")
            self.assertNotIn("largest_settlement_population", entity)
            self.assertIn("East Jerusalem", entity["largest_settlement_note"])

    def test_sub_districts_carry_population_groups(self):
        haifa = self.out["s-Haifa"]
        self.assertEqual(haifa["population"]["value"], round(1000 * (10.2 + 76.8 + 546.4)))
        groups = {s["group"] for s in haifa["ethnicity"]}
        self.assertEqual(groups, {"Foreign nationals", "Arabs", "Jews and others"})
        self.assertEqual(haifa["ethnicity_basis"], "population group")

    def test_tel_aviv_takes_the_district_row(self):
        self.assertEqual(self.out["s-ta"]["population"]["value"], round(1000 * 1456.7))

    def test_a_row_that_does_not_add_up_stops_the_run(self):
        broken = sheet()
        broken["ST02-17a"][3][5] += 1.0
        with self.assertRaises(SystemExit):
            ic.read(broken)


DISTRICT_NAMES = ["Jerusalem District", "Northern District", "Haifa District",
                  "Central District", "Tel Aviv District", "Southern District"]
SUB_NAMES = ["Zefat", "Kinneret", "Yizre'el", "Akko", "Golan", "Haifa", "Hadera", "Sharon",
             "Petah Tiqwa", "Ramla", "Rehovot", "Ashqelon", "Be'er Sheva"]


def age_row(label, scale, median):
    # Eleven age groups, oldest first: 75+ ... 0-4, in thousands.
    groups = [round(scale * w, 1) for w in (1, 2, 3, 4, 5, 3, 3, 3, 3, 6, 3)]
    total = round(sum(groups), 1)
    females = [round(g / 2, 1) for g in groups]
    return ([label, median - 1] + females + [round(sum(females), 1)]
            + [median] + groups + [total])


def ages_sheet():
    rows = [["POPULATION OF ISRAELIS"], [None, " THEREOF: FEMALES - TOTAL"],
            age_row("GRAND TOTAL", 50, 30.3)]
    for name in DISTRICT_NAMES:
        rows.append(age_row(name, 10, 31.0))
    for name in SUB_NAMES:
        rows.append(age_row(f"   {name} S.D.", 2, 32.0))
    rows.append([None, " POPULATION GROUP"])
    rows.append(age_row("Haifa District", 99, 99.0))       # a later section: not read
    return {"ST02-19x": rows}


def religion_row(label, value, hebrew=""):
    return [label] + [1.0] * 8 + [value] + [None] * 7 + [hebrew]


def religion_sheets():
    x = [[None, "TOTAL POPULATION(5)"]]
    for name in DISTRICT_NAMES:
        x.append(religion_row(name, 100.0))
    x += [[None, "RELIGION"], [None, "JEWS"]]
    for name in DISTRICT_NAMES:
        x.append(religion_row(name, 69.5 if name in ("Northern District", "Haifa District")
                              else 78.5))
    y = [[None, "MOSLEMS"]] + [religion_row(n, 15.0) for n in DISTRICT_NAMES]
    y += [[None, "CHRISTIANS(6)"]] + [religion_row(n, 5.0) for n in DISTRICT_NAMES]
    y += [[None, "DRUZE"], religion_row("Thereof: Northern District", 9.0),
          religion_row("", 5.0, "מזה: נפת עכו"),
          religion_row("", 9.0, "מחוז חיפה")]
    y += [[None, "NOT CLASSIFIED BY RELIGION"]] + [religion_row(n, 1.0) for n in DISTRICT_NAMES]
    return {"ST02-15x": x, "ST02-15y": y}


class TheAgesAndReligions(unittest.TestCase):
    def test_ages_are_read_from_the_whole_population_section_only(self):
        ages = ic.read_ages(ages_sheet())
        self.assertEqual(ages[("district", "HAIFA DISTRICT")]["median"], 31.0)
        self.assertEqual(ages[("subdistrict", "Zefat")]["total"], round(2 * 36, 1) * 1000)
        self.assertNotIn(99.0, [a["median"] for a in ages.values()])

    def test_religions_by_district_including_hebrew_labelled_rows(self):
        rel = ic.read_religion(religion_sheets())
        self.assertEqual(rel["HAIFA DISTRICT"]["Druze"], 9000.0)
        self.assertEqual(rel["NORTHERN DISTRICT"]["Druze"], 9000.0)
        self.assertNotIn("Druze", rel["TEL AVIV DISTRICT"])
        fields = ic.religion_fields(rel["TEL AVIV DISTRICT"], "the Tel Aviv District")
        self.assertIn("remaining 500", fields["religion_note"])

    def test_a_religion_row_too_far_short_stops_the_run(self):
        rel = ic.read_religion(religion_sheets())
        rel["TEL AVIV DISTRICT"]["Judaism"] -= 5000
        with self.assertRaises(SystemExit):
            ic.religion_fields(rel["TEL AVIV DISTRICT"], "the Tel Aviv District")

    def test_jews_and_others_is_written_as_the_jews_and_the_rest(self):
        # Table 2.15's Jews: every district, and every sub-district under its
        # English label; one thousand fewer than Table 2.17's Jews and others.
        rows = [[None, "TOTAL POPULATION(5)"], [None, "RELIGION"], [None, "JEWS"]]
        for district, subs in SUBS.items():
            rows.append(religion_row(district.title(), 1.0))
            for name, _f, _a, j in subs:
                rows.append(religion_row(f"   {name} S.D.", round(j - 1.0, 1)))
        jews = ic.read_jews({"ST02-15x": rows})
        self.assertEqual(jews[("subdistrict", "Haifa")], round(546.4 - 1.0, 1) * 1000)
        out = {r["shape_id"]: r for r in ic.build(ic.read(sheet()), ADMIN1, ADMIN2, PARENTS,
                                                    jews=jews)}
        haifa = {s["group"]: s["count"] for s in out["s-Haifa"]["ethnicity"]}
        self.assertEqual(set(haifa), {"Foreign nationals", "Arabs", "Jewish",
                                      "Others (not Jews or Arabs)"})
        self.assertEqual(haifa["Jewish"], round((546.4 - 1.0) * 1000))
        self.assertEqual(haifa["Others (not Jews or Arabs)"], 1000)
        self.assertIn("Druze", out["s-Haifa"]["ethnicity_note"])
        # The Northern District, drawn without the Golan, sums four sub-districts.
        north = {s["group"]: s["count"] for s in out["d1"]["ethnicity"]}
        self.assertEqual(north["Others (not Jews or Arabs)"], 4000)
        # Jerusalem displaces an encyclopaedia's figure older than the check.
        self.assertEqual(out["d0"]["population"]["displaces_before"], ic.DISPLACES_BEFORE)
        self.assertEqual(out["s-jer"]["population"]["displaces_before"], ic.DISPLACES_BEFORE)
        self.assertNotIn("displaces_before", out["s-Golan"]["population"])
        # Every unit says why it has no language, and what was looked at.
        for r in out.values():
            self.assertEqual(r["language"]["status"], "not_available")
            self.assertIn("Statistical Abstract", r["language"]["note"])

    def test_more_jews_than_jews_and_others_stops_the_run(self):
        rows = [[None, "TOTAL POPULATION(5)"], [None, "RELIGION"], [None, "JEWS"]]
        for district, subs in SUBS.items():
            rows.append(religion_row(district.title(), 1.0))
            for name, _f, _a, j in subs:
                rows.append(religion_row(f"   {name} S.D.", round(j + 1.0, 1)))
        with self.assertRaises(SystemExit):
            ic.build(ic.read(sheet()), ADMIN1, ADMIN2, PARENTS,
                     jews=ic.read_jews({"ST02-15x": rows}))

    def test_build_writes_median_sex_and_religion(self):
        out = {r["shape_id"]: r for r in ic.build(
            ic.read(sheet()), ADMIN1, ADMIN2, PARENTS, ic.read_ages(ages_sheet()),
            ic.read_religion(religion_sheets()))}
        self.assertEqual(out["d2"]["median_age"]["value"], 31.0)
        self.assertEqual(out["d2"]["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(out["d2"]["religion_basis"],
                         "religion as recorded in the population register")
        north = out["d1"]
        self.assertIn("interpolated", north["median_age_note"])
        self.assertEqual(north["religion"]["status"], "not_available")
        self.assertEqual(out["s-ta"]["religion_year"], 2023)
        self.assertNotIn("religion_year", out["s-Haifa"])
        self.assertEqual(out["s-Haifa"]["religion"]["status"], "not_available")
        self.assertIn("Haifa sub-district", out["s-Haifa"]["religion"]["note"])


if __name__ == "__main__":
    unittest.main()
