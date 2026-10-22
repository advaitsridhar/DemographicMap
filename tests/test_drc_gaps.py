"""The DRC's stated reasons, from rows laid out as OCHA's 2020 tables are (no network)."""

import unittest

from scripts.fetch_census import drc_gaps as dg

H1 = ("admin1Name_fr,admin1Pcode,F_00_04,M_00_04,F_05_19,M_05_19,F_adulte,M_adulte,F_agee,M_agee,"
      "T_00_04,T_05_19,T_adulte,T_agee,F_TL,M_TL")
ADM1 = "\n".join([
    H1,
    "Kinshasa,CD10,1035155,1041110,1927889,1949724,1929874,1916476,68481,54586,2076265,3877613,"
    "3846350,123067,5220436,4704348",
    "Kongo-Central,CD20,418794,413571,830960,819302,713199,769667,48430,69735,832365,1650262,"
    "1482866,118165,2011383,2072275",
    "Bas-Uele,CD52,96557,101359,219021,229953,287394,277979,29131,23381,197916,448974,565373,"
    "52512,609165,690000"])
H2 = ("admin2Name_fr,admin2Pcode,admin1Name_fr,admin1Pcode,REMARK,F_00_04,M_00_04,F_05_19,M_05_19,"
      "F_adulte,M_adulte,F_agee,M_agee,T_00_04,T_05_19,T_adulte,T_agee,F_TL,M_TL")
ADM2 = "\n".join([
    H2,
    "Kinshasa,CD1000,Kinshasa,CD10,,1035155,1041110,1927889,1949724,1929874,1916476,68481,54586,"
    "2076265,3877613,3846350,123067,5220436,4704348",
    "Matadi,CD2001,Kongo-Central,CD20,,35432,34990,70303,69317,60340,65118,4097,5900,70422,139620,"
    "125458,9997,176141,163899",
    "Songololo,CD2011,Kongo-Central,CD20,,35985,35536,71399,70398,61281,66133,4161,5992,71521,"
    "141797,127414,10153,178887,166455",
    "Bangu,CD2012,Kongo-Central,CD20,Population is reflected in CD2011,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
    "Mbanza-Ngungu,CD2013,Kongo-Central,CD20,,75712,74768,150226,148118,128936,139145,8756,12607,"
    "150480,298344,268081,21363,376381,350224"])
WIKI = """{| class="wikitable"
! Pcode !! Territoire !! Chef-lieu !! Province
|-
| 2011 || [[Songololo]] || [[Songololo]] || Kongo central
|-
| 2014 || [[Mbanza-Ngungu (territoire)|Mbanza-Ngungu]] || [[Mbanza-Ngungu]] || Kongo central
|-
| 2013 || Matadi || Wrong || Kasaï
|}"""


def units():
    admin1 = [{"id": "K", "name": "Kinshasa"}, {"id": "C", "name": "Kongo-Central"},
              {"id": "U", "name": "Lower Uele"}]
    admin2 = [{"id": n, "name": n, "parent": p, "point": [14.0 + i * 0.1, -5.0]}
              for i, (n, p) in enumerate([("Kinshasa", "K"), ("Matadi", "C"), ("Songololo", "C"),
                                          ("Bangu", "C"), ("Mbanza-Ngungu", "C")])]
    return admin1, admin2


class Reasons(unittest.TestCase):
    def test_provinces(self):
        adm1 = dg.rows_of(ADM1)
        kin = dg.province_fields("Kinshasa", adm1[0])
        self.assertIn("5,220,436 women", kin["sex_ratio"]["note"])
        self.assertIn("four broad groups", kin["median_age"]["note"])
        # Kongo-Central's two splits agree: the reason is the estimate itself.
        kc = dg.province_fields("Kongo-Central", adm1[1])
        self.assertIn("no census since", kc["sex_ratio"]["note"])

    def test_copied_structures(self):
        adm2 = dg.rows_of(ADM2)
        kc = [r for r in adm2 if r["admin1Pcode"] == "CD20" and not r["REMARK"]]
        self.assertTrue(dg.copied(kc))
        self.assertFalse(dg.copied(kc[:1]))

    def test_seats_by_name_not_code(self):
        seat_of = dg.seats(WIKI)
        self.assertEqual(seat_of[("songololo", "kongocentral")], "Songololo")
        self.assertNotIn(("matadi", "kongocentral"), seat_of)

    def test_build(self):
        admin1, admin2 = units()
        records, report = dg.build(dg.rows_of(ADM1), dg.rows_of(ADM2), dg.seats(WIKI), admin1, admin2)
        by = {(r["level"], r["name"]): r for r in records}
        self.assertIn("Lower Uele", by[("admin1", "Lower Uele")]["sex_ratio"]["note"])
        self.assertEqual(by[("admin2", "Songololo")]["capital"], "Songololo")
        self.assertEqual(by[("admin2", "Mbanza-Ngungu")]["capital"], "Mbanza-Ngungu")
        self.assertEqual(by[("admin2", "Matadi")]["capital"], "Matadi")         # a city's own
        self.assertIn("same proportion of men", by[("admin2", "Matadi")]["sex_ratio"]["note"])
        bangu = by[("admin2", "Bangu")]
        self.assertIn("edge of Songololo and Mbanza-Ngungu", bangu["population"]["note"])
        self.assertIn("within Songololo territory's figure", bangu["population"]["note"])
        # Kinshasa is its province's one unit, and takes the province's reasons.
        self.assertIn("5,220,436", by[("admin2", "Kinshasa")]["sex_ratio"]["note"])
        self.assertEqual(by[("admin2", "Kinshasa")]["capital"], "Kinshasa")
        self.assertIn("city-province", by[("admin2", "Kinshasa")]["capital_note"])

    def test_reasons_cite_notes_only(self):
        admin1, admin2 = units()
        records, _ = dg.build(dg.rows_of(ADM1), dg.rows_of(ADM2), dg.seats(WIKI), admin1, admin2)
        for r in records:
            for src in r["sources"]:
                if src["name"] == dg.OCHA:
                    self.assertTrue(all(p.endswith(" note") for p in src["field"].split("/")),
                                    (r["name"], src["field"]))

    def test_seats_only_for_listed_territories_and_known_cities(self):
        admin1 = [{"id": "E", "name": "Equateur"}, {"id": "N", "name": "North Kivu"}]
        admin2 = [{"id": n, "name": n, "parent": p, "point": [18.0 + i * 0.1, 0.0]}
                  for i, (n, p) in enumerate([("Makanza", "E"), ("Bikoro", "E"), ("Nowhere", "E"),
                                              ("Oïcha", "N"), ("Beni", "N"), ("Lubero", "N")])]
        rows = [H2] + [f"{n},{c},{p},{pc},,1,1,1,1,1,1,1,1,1,1,1,1,4,4"
                       for n, c, p, pc in (("Makanza", "CD4105", "Equateur", "CD41"),
                                           ("Bikoro", "CD4102", "Equateur", "CD41"),
                                           ("Nowhere", "CD4199", "Equateur", "CD41"),
                                           ("Oïcha", "CD6107", "Nord-Kivu", "CD61"),
                                           ("Beni", "CD6109", "Nord-Kivu", "CD61"),
                                           ("Lubero", "CD6105", "Nord-Kivu", "CD61"))]
        wiki = """{| class="wikitable"
! Pcode !! Territoire !! Chef-lieu !! Province
|-
| 4105 || Mankanza || Makanza || Équateur
|-
| 4102 || Bikoro || Bikoro || Équateur
|-
| 6109 || Beni || Beni || Nord-Kivu
|-
| 6105 || Lubero || Lubero || Nord-Kivu
|}"""
        records, report = dg.build([], dg.rows_of("\n".join(rows)), dg.seats(wiki), admin1, admin2)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Makanza"]["capital"], "Makanza")
        self.assertNotIn("capital_note", by["Makanza"])
        self.assertEqual(by["Beni"]["capital"], "Beni")
        self.assertIn("city administered apart", by["Beni"]["capital_note"])
        self.assertEqual(by["Oïcha"]["capital"]["status"], "not_available")
        self.assertIn("territory of Beni", by["Oïcha"]["capital"]["note"])
        self.assertNotIn("capital", {k for k, v in by["Nowhere"].items()
                                     if isinstance(v, str)})
        self.assertTrue(any("Nowhere" in line and "no seat written" in line for line in report))

    def test_the_2024_projection_by_territory(self):
        admin1, admin2 = units()
        sheet = [["Province", "Code Province", "Territoire", "Code Terrtoire", "Zone de sante",
                  "Pcode ZS", "Population 2024"],
                 ["Kongo-Central", "CD20", "Matadi", "CD2001", "Matadi", "CD2001ZS01", 351301],
                 ["Kongo-Central", "CD20", "Matadi", "CD2001", "Nzanza", "CD2001ZS02", 311532],
                 ["Kongo-Central", "CD20", "Songololo", "CD2011", "Kimpese", "CD2011ZS01", 400000]]
        sums = dg.hpc_sums(sheet)
        self.assertEqual(sums["CD2001"]["total"], 662_833)
        self.assertEqual(sums["CD2001"]["zones"], 2)
        held, _ = dg.hpc_build(sums, dg.rows_of(ADM2), admin1, admin2)
        by = {r["name"]: r for r in held}
        self.assertEqual(by["Matadi"]["population"]["value"], 662_833)
        self.assertEqual(by["Matadi"]["population"]["year"], 2024)
        self.assertIn("2 health zones", by["Matadi"]["population_note"])
        self.assertEqual(by["Matadi"]["match_by"], "shape_id")

    def test_the_2024_projection_matched_by_name_and_its_factor(self):
        admin1, admin2 = units()
        factor = 662_833 / 340_040
        # The workbook codes Mbanza-Ngungu CD2014; the 2020 table, CD2013.
        sheet = [["Province", "Code Province", "Territoire", "Code Terrtoire", "Zone de sante",
                  "Pcode ZS", "Population 2024"],
                 ["Kongo-Central", "CD20", "Matadi", "CD2001", "Matadi", "CD2001ZS01", 662_833],
                 ["Kongo-Central", "CD20", "Songololo", "CD2011", "Kimpese", "CD2011ZS01",
                  round(345_342 * factor)],
                 ["Kongo-Central", "CD20", "Mbanza-Ngungu", "CD2014", "Kwilu-Ngongo",
                  "CD2014ZS01", round(726_605 * factor)]]
        held, report = dg.hpc_build(dg.hpc_sums(sheet), dg.rows_of(ADM2), admin1, admin2)
        by = {r["name"]: r for r in held}
        self.assertEqual(by["Mbanza-Ngungu"]["population"]["value"], round(726_605 * factor))
        self.assertTrue(any("CD2014 Mbanza-Ngungu (Kongo-Central) is the 2020 table's CD2013"
                            in line for line in report))
        self.assertEqual(by["Matadi"]["population_note"],
                         "OCHA's projected population of Matadi for 2024, made for humanitarian "
                         "planning: its health zone's figure. The projection is OCHA's 2020 "
                         "estimate for every territory and city of Kongo-Central multiplied by "
                         "1.95.")
        self.assertEqual([s["field"] for s in by["Matadi"]["sources"]],
                         ["population", "population note"])
        # A code whose 2020 unit has another name is not taken on that code.
        sheet[3][2], sheet[3][3] = "Nowhere", "CD2013"
        held, report = dg.hpc_build(dg.hpc_sums(sheet), dg.rows_of(ADM2), admin1, admin2)
        self.assertNotIn("Mbanza-Ngungu", {r["name"] for r in held})
        self.assertTrue(any("CD2013 Nowhere (Kongo-Central): no 2020 unit" in line
                            for line in report))

    def test_town_premise_checked(self):
        admin1, admin2 = units()
        moved = ADM2.replace("Population is reflected in CD2011", "Population is reflected in CD2001")
        records, report = dg.build(dg.rows_of(ADM1), dg.rows_of(moved), {}, admin1, admin2)
        self.assertFalse(any(r["name"] == "Bangu" for r in records))
        self.assertTrue(any("town Bangu" in line and "left out" in line for line in report))


if __name__ == "__main__":
    unittest.main()
