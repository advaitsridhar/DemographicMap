"""Zimbabwe's 2022 census by district and province, from ZIMSTAT's ward tables
(scripts/fetch_census/zimbabwe_districts)."""

import unittest
from unittest import mock

from scripts.fetch_census import zimbabwe_districts as zw

# One district a province, and Harare's three pages as the final tables print
# them: Harare Urban District's page opens with the ward that is Harare Rural.
DISTRICTS = {p: [(f"{p} District", [(1_000, 1_100)])] for p in zw.PROVINCES}
DISTRICTS["Bulawayo"] = [("Bulawayo Urban District", [(307_871, 358_081)])]
DISTRICTS["Harare"] = [("Harare Urban District", [(174_550, 183_313), (13_670, 16_559)]),
                       ("Chitungwiza District", [(2_000, 2_200)]),
                       ("Epworth District", [(3_000, 3_300)])]


def fmt(n):
    return f"{n:,}"


def pages():
    out, totals = [], {}
    for p in zw.PROVINCES:
        out.append(f"{p} Province\n2")
        pm = pf = ph = 0
        for name, wards in DISTRICTS[p]:
            lines = [name, "Population Distribution by Ward, Sex and Number of Households",
                     "Ward Male Female Total Households"]
            dm = df = dh = 0
            for i, (m, f) in enumerate(wards, 1):
                h = (m + f) // 4
                lines.append(f"Ward {i:02d} {fmt(m)} {fmt(f)} {fmt(m + f)} {fmt(h)}")
                dm, df, dh = dm + m, df + f, dh + h
            lines.append(f"Total {fmt(dm)} {fmt(df)} {fmt(dm + df)} {fmt(dh)}")
            out.append("\n".join(lines))
            pm, pf, ph = pm + dm, pf + df, ph + dh
        totals[p] = (pm, pf, ph)
    head = ["Population Distribution by Province, Sex and Number of Households",
            "Province Male Female Total Households"]
    tm = tf = th = 0
    for p, (m, f, h) in totals.items():
        head.append(f"{p} {fmt(m)} {fmt(f)} {fmt(m + f)} {fmt(h)}")
        tm, tf, th = tm + m, tf + f, th + h
    head.append(f"Total {fmt(tm)} {fmt(tf)} {fmt(tm + tf)} {fmt(th)}")
    return ["Table of Contents ....... ii\nPopulation Distribution by Province ..... 1",
            "\n".join(head)] + out, tm + tf


ADMIN1 = [{"id": f"P{i}", "name": p} for i, p in enumerate(zw.PROVINCES)]
PARENT = {p: f"P{i}" for i, p in enumerate(zw.PROVINCES)}
ADMIN2 = ([{"id": f"D-{p}", "name": p, "parent": PARENT[p]} for p in zw.PROVINCES
           if p not in ("Bulawayo", "Harare")]
          + [{"id": "D-Byo", "name": "Bulawayo", "parent": PARENT["Bulawayo"]},
             {"id": "D-Hre", "name": "Harare", "parent": PARENT["Harare"]},
             {"id": "D-HreR", "name": "Harare Rural", "parent": PARENT["Harare"]},
             {"id": "D-Chi", "name": "Chitungwiza", "parent": PARENT["Harare"]},
             {"id": "D-Epw", "name": "Epworth", "parent": PARENT["Harare"]}])


class ZimbabweDistrictsTest(unittest.TestCase):
    def table(self):
        texts, national = pages()
        with mock.patch.object(zw, "NATIONAL", national):
            return zw.parse(texts)

    def test_wards_districts_and_provinces_are_checked(self):
        table = self.table()
        self.assertEqual(len(table["districts"]), len(zw.PROVINCES) + 2)
        self.assertEqual(table["provinces"]["Bulawayo"]["total"], 665_952)
        texts, national = pages()
        broken = [t.replace("Total 307,871 358,081 665,952", "Total 307,871 358,081 665,953")
                  for t in texts]
        with mock.patch.object(zw, "NATIONAL", national), self.assertRaises(SystemExit):
            zw.parse(broken)

    def test_harare_rural_is_ward_one_of_harare_urbans_page(self):
        recs = {r["shape_id"]: r for r in zw.build(self.table(), ADMIN1, ADMIN2)}
        rural, urban = recs["D-HreR"], recs["D-Hre"]
        self.assertEqual(rural["population"]["value"], 357_863)
        self.assertEqual(urban["population"]["value"], 30_229)
        self.assertEqual(rural["sex_ratio"]["value"], round(1000 * 174_550 / 183_313))
        self.assertEqual(rural["sex_ratio"]["unit"], "males_per_1000_females")
        self.assertIn("Ward 01 of Harare Urban District", rural["population_note"])
        self.assertIn("less its Ward 01", urban["population_note"])
        self.assertTrue(any("Preliminary Report" in s["name"] for s in rural["sources"]))

    def test_a_ward_one_unlike_the_preliminary_reports_is_refused(self):
        table = self.table()
        harare = [d for d in table["districts"] if d["name"] == "Harare Urban District"][0]
        harare["wards"][0]["total"] += 5_000
        with self.assertRaises(SystemExit):
            zw.build(table, ADMIN1, ADMIN2)

    def test_every_polygon_gets_a_district_and_reasons_for_the_rest(self):
        recs = zw.build(self.table(), ADMIN1, ADMIN2)
        admin2 = [r for r in recs if r["level"] == "admin2"]
        self.assertEqual(sorted(r["shape_id"] for r in admin2), sorted(s["id"] for s in ADMIN2))
        for r in admin2:
            self.assertEqual(r["religion"]["status"], "not_available")
            self.assertIn("Table 2.14", r["religion"]["note"])
            self.assertIn("by district", r["median_age"]["note"])
        byo = [r for r in admin2 if r["shape_id"] == "D-Byo"][0]
        self.assertEqual(byo["population_note"],
                         "The 2022 census's count for Bulawayo Urban District, drawn here as "
                         "Bulawayo.")
        provinces = [r for r in recs if r["level"] == "admin1"]
        self.assertEqual(len(provinces), 10)

    def test_a_polygon_without_a_census_district_is_refused(self):
        extra = ADMIN2 + [{"id": "D-X", "name": "Nowhere", "parent": PARENT["Midlands"]}]
        with self.assertRaises(SystemExit):
            zw.build(self.table(), ADMIN1, extra)

    def test_figures_split_from_their_label_are_joined_again(self):
        lines = ["Chipinge Rural District", "Ward 22 5,448 6,376 11,824 2,517",
                 "5,243 6,057 11,300 2,302", "Ward 23", "14,013 17,147 31,160 7,321", "Ward 24",
                 "174,277 200,982 375,259 84,046", "Total", "7"]
        self.assertEqual(zw.joined_lines(lines),
                         ["Chipinge Rural District", "Ward 22 5,448 6,376 11,824 2,517",
                          "Ward 23 5,243 6,057 11,300 2,302", "Ward 24 14,013 17,147 31,160 7,321",
                          "Total 174,277 200,982 375,259 84,046", "7"])

    def test_visitor_notes_say_nothing_about_how_the_map_is_made(self):
        for r in zw.build(self.table(), ADMIN1, ADMIN2):
            text = " ".join(str(r.get(k)) for k in r if k.endswith("note")) + " ".join(
                str((r.get(f) or {}).get("note", "")) for f in
                ("religion", "language", "ethnicity", "median_age"))
            for word in ("adapter", "fetched", "pipeline", "build", "scraped", "boundary file"):
                self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
