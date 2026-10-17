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

    def test_town_premise_checked(self):
        admin1, admin2 = units()
        moved = ADM2.replace("Population is reflected in CD2011", "Population is reflected in CD2001")
        records, report = dg.build(dg.rows_of(ADM1), dg.rows_of(moved), {}, admin1, admin2)
        self.assertFalse(any(r["name"] == "Bangu" for r in records))
        self.assertTrue(any("town Bangu" in line and "left out" in line for line in report))


if __name__ == "__main__":
    unittest.main()
