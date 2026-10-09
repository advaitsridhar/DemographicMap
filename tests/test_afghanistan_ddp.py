"""Afghanistan: district ethnic shares read from the development plans' own PDFs.

Synthetic page texts in the layout of the NABDP summaries (cover, then the
district profile table) and synthetic drawn units bound through the office's
district codes. No network.
"""

import json
import unittest
from unittest import mock

from scripts.fetch_census import afghanistan_ddp as dd
from scripts.fetch_census import afghanistan_estimates as ae

COVER = """Islamic Republic of Afghanistan
Ministry of Rural Rehabilitation and Development
National Area Based Development Programme
SUMMARY OF DISTRICT DEVELOPMENT PLAN
{district} DISTRICT
{province} PROVINCE
Developed by the {district} District Development Assembly with the
DDA Re-Election Date
{month} {year}"""

PROFILE = """2. District Profile:
General Information
Population (According to field information) 15934 Persons
Area 1724 Sq. Km
{label} {ethnic}
Sectoral Information
Number of Primary Schools 9 Primary Schools"""

URL = "https://web.archive.org/web/2016id_/http://www.mrrd-nabdp.org/attachments/article/{a}/{f}"
ORIGINAL = "http://www.mrrd-nabdp.org/attachments/article/{a}/{f}"


def plan(district, province, ethnic, *, year=2009, label="Ethnic diversity", article="123",
         wrap=None):
    profile = PROFILE.format(label=label, ethnic=ethnic)
    if wrap:
        profile = profile.replace(ethnic, ethnic + "\n" + wrap)
    texts = [COVER.format(district=district.upper(), province=province.upper(),
                          month="October", year=year), profile]
    return dd.read_plan(texts, URL.format(a=article, f=f"{district}%20DDP%20English%20Summary.pdf"))


ISO = {"21": "AF-BAL", "02": "AF-KAP", "03": "AF-PAR"}
NAMES = {"21": "Balkh", "02": "Kapisa", "03": "Parwan"}
CROSSWALK = {
    "Balkh": {"Chimtal": "2108", "Balkh": "2106", "Dawlat Abad": "2109"},
    "Kapisa": {"Koh Band": "0203"},
    "Parwan": {"Mahmudi Raqi": "0201", "Charikar": "0301"},
}


def units():
    units1 = [{"id": f"P{c}", "name": NAMES[c], "iso_3166_2": ISO[c]} for c in ISO]
    pid = {NAMES[c]: f"P{c}" for c in ISO}
    units2 = [{"id": f"D{key}", "name": label, "parent": pid[province]}
              for province, districts in CROSSWALK.items() for label, key in districts.items()]
    return units1, units2


class Reading(unittest.TestCase):
    def test_the_cover_names_district_province_and_year(self):
        p = plan("Chemtal", "Balkh", "Pashtun 40%, Tajik 35%, Uzbek 25%")
        self.assertEqual((p["district"], p["province"], p["year"]), ("CHEMTAL", "BALKH", 2009))
        self.assertEqual(p["district_from"], "cover")
        self.assertEqual(p["ethnic"], "Pashtun 40%, Tajik 35%, Uzbek 25%")

    def test_a_wrapped_line_is_joined_and_the_next_field_ends_it(self):
        p = plan("Nad Ali", "Helmand", "90% Pashtun, 10% Turkmen and", wrap="Hazara")
        self.assertEqual(p["ethnic"], "90% Pashtun, 10% Turkmen and Hazara")
        self.assertEqual(dd.plan_shares(p["ethnic"]), [{"group": "Pashtun", "pct": 90.0}])

    def test_a_page_number_or_the_next_row_is_not_taken_in(self):
        for after in ("2", "Situation Analysis, Development Goals and Strategies",
                      "Kochi population in winter"):
            p = plan("Bost", "Helmand", "100% Pashtun", wrap=after)
            self.assertEqual(p["ethnic"], "100% Pashtun")

    def test_the_answer_on_the_line_below_its_label(self):
        texts = [COVER.format(district="NILI", province="DAIKUNDI", month="May", year=2007),
                 "District Profile\nEthnic diversity\n100 % Hazara\nSectoral Information"]
        self.assertEqual(dd.read_plan(texts, URL.format(a="134", f="Nili.pdf"))["ethnic"],
                         "100 % Hazara")

    def test_the_misspelt_label_of_some_plans_is_read(self):
        p = plan("Chemtal", "Balkh", "Pashtun, Arab, Tajik", label="Ethic Diversity")
        self.assertEqual(p["ethnic"], "Pashtun, Arab, Tajik")

    def test_a_cover_without_the_names_falls_back_to_the_file(self):
        p = dd.read_plan(["SUMMARY OF DISTRICT DEVELOPMENT PLAN", ""],
                         URL.format(a="122", f="Summary%20of%20the%20DDP%20in%20English-Bakwa.pdf"))
        self.assertEqual((p["district"], p["district_from"], p["province"]),
                         ("Bakwa", "file name", None))

    def test_file_names_with_and_without_ddp_give_the_district(self):
        for name, label in (("Chemtal%20DDP%20English%20Summary.pdf", "Chemtal"),
                            ("Khost_Tani_Summary_Finalized.pdf", "Khost Tani"),
                            ("Kabul_Guldara%20English%20summary%20finalized.pdf", "Kabul Guldara"),
                            ("Gizab%20District%20Summary.pdf", "Gizab"),
                            ("Chardara%20Summery.pdf", "Chardara"),
                            ("Dawlat%20Abad%20Full%20DDP.pdf", "Dawlat Abad"),
                            ("Samangan_Aibak_DDP%20Summary-translated-finalized.pdf", "Samangan Aibak")):
            self.assertEqual(dd.file_label(URL.format(a="139", f=name)), label)
            self.assertTrue(dd.PLAN_FILE.search(name), name)

    def test_a_full_plan_gives_way_to_its_summary(self):
        found = [("2016", URL.format(a="123", f="Dawlat%20Abad%20Full%20DDP.pdf")),
                 ("2016", URL.format(a="123", f="Dawlat%20Abad%20DDP%20English%20Summary.pdf")),
                 ("2016", URL.format(a="133", f="Khuram%20Sarbagh%20full%20DDP.pdf"))]
        kept = [url.rsplit("/", 1)[-1] for _, url in dd.prefer_summaries(found)]
        self.assertEqual(sorted(kept), ["Dawlat%20Abad%20DDP%20English%20Summary.pdf",
                                        "Khuram%20Sarbagh%20full%20DDP.pdf"])


class Fetching(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(dd, "PAUSE", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_plans_are_read_in_order_and_failures_named(self):
        pages = [COVER.format(district="CHEMTAL", province="BALKH", month="May", year=2010),
                 PROFILE.format(label="Ethnic diversity", ethnic="Tajik 60%, Pashtun 40%")]

        def get(url, **_):
            if "Gone" in url:
                raise RuntimeError("GET failed after 1 retries")
            return b"<html>" if "Bad" in url else b"%PDF-1.4"
        found = [("2016", ORIGINAL.format(a="123", f="Chemtal%20DDP%20English%20Summary.pdf")),
                 ("2016", ORIGINAL.format(a="123", f="Bad%20DDP%20English%20Summary.pdf")),
                 ("2016", ORIGINAL.format(a="123", f="Gone%20DDP%20English%20Summary.pdf"))]
        with mock.patch.object(dd, "http_get", get), \
                mock.patch.object(dd, "page_texts", lambda blob: pages):
            read, unread = dd.read_plans(found, workers=2)
        chemtal, bad, gone = (dd.capture_url(*item) for item in found)
        self.assertEqual(dd.plan_of(read[chemtal], chemtal)["district"], "CHEMTAL")
        # Not a PDF is remembered; an archive that did not answer is asked again.
        self.assertEqual(read[bad], {"failed": "not a PDF"})
        self.assertNotIn(gone, read)
        self.assertEqual(dd.still_to_read(found, read), [found[2]])
        self.assertEqual(unread, 0)

    def test_plans_past_the_runs_time_are_counted_not_read(self):
        found = [("2016", ORIGINAL.format(a="123", f="Chemtal%20DDP%20English%20Summary.pdf"))]
        with mock.patch.object(dd, "http_get", side_effect=AssertionError("fetched")):
            read, unread = dd.read_plans(found, minutes=-1)
        self.assertEqual((read, unread), ({}, 1))

    def test_what_is_kept_reads_back_the_same(self):
        texts = [COVER.format(district="NAD ALI", province="HELMAND", month="May", year=2008),
                 PROFILE.format(label="Ethnic diversity", ethnic="90% Pashtun, 10% Turkmen and")
                 .replace("Sectoral", "Hazara\nSectoral")]
        url = URL.format(a="131", f="Nad%20Ali%20DDP%20English%20Summary.pdf")
        kept = json.loads(json.dumps(dd.excerpt(texts)))
        self.assertEqual(dd.plan_of(kept, url), dd.read_plan(texts, url))
        self.assertEqual(dd.plan_of(kept, url)["ethnic"], "90% Pashtun, 10% Turkmen and Hazara")


class Shares(unittest.TestCase):
    def parts(self, text):
        return [(p["group"], p["pct"]) for p in dd.plan_shares(text)]

    def test_both_orders_and_the_and_between_two_shares(self):
        self.assertEqual(self.parts("Baloch 44%, Pashtun 34 % and Tajik 22%"),
                         [("Baloch", 44.0), ("Pashtun", 34.0), ("Tajik", 22.0)])
        self.assertEqual(self.parts("95% Pashtun and 5% Tajik"),
                         [("Pashtun", 95.0), ("Tajik", 5.0)])
        self.assertEqual(self.parts("Tajik 40%; Uzbak 40 % and Pashtun 20 %"),
                         [("Tajik", 40.0), ("Uzbek", 40.0), ("Pashtun", 20.0)])

    def test_the_plans_own_spellings(self):
        self.assertEqual(self.parts("55% Uzbak, 35%Tajik, 5% Pashton, 5% other ethnicities"),
                         [("Uzbek", 55.0), ("Tajik", 35.0), ("Pashtun", 5.0), ("Other", 5.0)])
        self.assertEqual(self.parts("100 % Pashtoon"), [("Pashtun", 100.0)])
        self.assertEqual(self.parts("Baloch 88 %, Pashtun 1 %, Brahawi 10 % and Tajik 1 %"),
                         [("Baloch", 88.0), ("Pashtun", 1.0), ("Brahui", 10.0), ("Tajik", 1.0)])

    def test_a_share_held_jointly_goes_to_none_of_them(self):
        self.assertEqual(self.parts("99% Pashtun, 1% Hazara, Tajik, Arab"), [("Pashtun", 99.0)])
        self.assertEqual(self.parts("Tajik 70%, Uzbak 20% and Mughol, Baloch 10%"),
                         [("Tajik", 70.0), ("Uzbek", 20.0)])
        self.assertEqual(self.parts("28% Pashtun, Tajik 70% and Arab and Baloch 2%"),
                         [("Tajik", 70.0), ("Pashtun", 28.0)])
        self.assertEqual(self.parts("90% Pashtun, 10% Turkmen and Hazara"), [("Pashtun", 90.0)])

    def test_a_name_unknown_here_is_left_out_not_guessed(self):
        self.assertEqual(self.parts("Pashtun 55%, Palo 20%, Brahawi 15%, Tajik 10%"),
                         [("Pashtun", 55.0), ("Brahui", 15.0), ("Tajik", 10.0)])
        self.assertEqual(self.parts("Pashtun 75% and the remaining 25% are Uzbak and Arab"),
                         [("Pashtun", 75.0)])

    def test_a_share_after_a_stray_comma_is_the_names_before_it(self):
        self.assertEqual(self.parts("Tajik 60%, Uzbak 35%, Pashtun, 5%"),
                         [("Tajik", 60.0), ("Uzbek", 35.0), ("Pashtun", 5.0)])

    def test_names_alone_are_no_shares(self):
        self.assertEqual(self.parts("Uzbek, Tajik, Gojor and Pashaai"), [])


class Building(unittest.TestCase):
    def build(self, plans, office=None):
        units1, units2 = units()
        with mock.patch.multiple(ae, PROVINCE_ISO=ISO, CROSSWALK=CROSSWALK,
                                 POINT_ELSEWHERE={}, TEMPORARY_PARENT={}), \
                mock.patch.object(dd, "SPELLINGS", {("21", "CHEMTAL"): "Chimtal"}):
            return {r["shape_id"]: r for r in dd.build(plans, units1, units2, office or {})}

    def test_shares_are_written_by_shape_id_with_the_plans_own_words(self):
        records = self.build([plan("Chemtal", "Balkh", "Pashtun 40%, Tajik 35%, Uzbek 25%")])
        chimtal = records["D2108"]
        self.assertEqual(chimtal["ethnicity"], [{"group": "Pashtun", "pct": 40.0},
                                                {"group": "Tajik", "pct": 35.0},
                                                {"group": "Uzbek", "pct": 25.0}])
        self.assertEqual(chimtal["ethnicity_year"], 2009)
        self.assertEqual(chimtal["ethnicity_basis"], "district development plan")
        self.assertIn("not a count", chimtal["ethnicity_note"])
        self.assertIn("Pashtun 40%, Tajik 35%, Uzbek 25%", chimtal["ethnicity_note"])
        self.assertTrue(chimtal["sources"][0]["url"].startswith("https://web.archive.org/"))

    def test_names_without_shares_are_not_written(self):
        self.assertEqual(self.build([plan("Balkh", "Balkh", "Pashtun, Arab, Tajik")]), {})

    def test_a_district_drawn_in_another_province_is_found_by_its_office_code(self):
        # Mahmudi Raqi is counted in Kapisa (02) and drawn in Parwan.
        records = self.build([plan("Mahmudi Raqi", "Kapisa", "Tajik 80%, Pashtun 20%")])
        self.assertEqual(records["D0201"]["ethnicity"][0], {"group": "Tajik", "pct": 80.0})

    def test_the_offices_spelling_reaches_the_drawn_district(self):
        records = self.build([plan("Dawlatabad", "Balkh", "Uzbek 60%, Pashtun 40%")],
                             office={"2109": "Dawlatabad"})
        self.assertIn("D2109", records)

    def test_an_unknown_name_binds_nothing(self):
        self.assertEqual(self.build([plan("Nowhere", "Balkh", "Uzbek 60%, Pashtun 40%")]), {})

    def test_a_file_name_that_leads_with_its_province_binds(self):
        texts = ["SUMMARY OF DISTRICT DEVELOPMENT PLAN",
                 PROFILE.format(label="Ethnic diversity", ethnic="Uzbek 60%, Pashtun 40%")]
        p = dd.read_plan(texts, URL.format(a="139", f="Balkh_Dawlat%20Abad_Summary_Finalized.pdf"))
        self.assertEqual((p["district"], p["province"]), ("Balkh Dawlat Abad", None))
        self.assertIn("D2109", self.build([p]))

    def test_the_provincial_centre_is_its_district(self):
        for name in ("Charikar Center", "Charikar Central"):
            records = self.build([plan(name, "Parwan", "Tajik 70%, Pashtun 30%")])
            self.assertIn("D0301", records)

    def test_a_declared_spelling_binds_whatever_its_case(self):
        texts = ["SUMMARY OF DISTRICT DEVELOPMENT PLAN",
                 PROFILE.format(label="Ethnic diversity", ethnic="Tajik 60%, Uzbek 40%")]
        p = dd.read_plan(texts, URL.format(a="123", f="Balkh_Chemtal_Summary_Finalized.pdf"))
        self.assertEqual(p["district"], "Balkh Chemtal")
        self.assertIn("D2108", self.build([p]))

    def test_the_later_of_two_plans_stands(self):
        early = plan("Balkh", "Balkh", "Tajik 70%, Pashtun 30%", year=2008)
        late = plan("Balkh", "Balkh", "Tajik 60%, Pashtun 40%", year=2010)
        for order in ([early, late], [late, early]):
            records = self.build(order)
            self.assertEqual(records["D2106"]["ethnicity"][0], {"group": "Tajik", "pct": 60.0})

    def test_a_line_that_cannot_be_its_districts_is_not_written(self):
        with mock.patch.object(dd, "NOT_ITS_OWN", {("21", "BALKH"): "not its own"}):
            self.assertEqual(self.build([plan("Balkh", "Balkh", "Tajik 60%, Pashtun 40%")]), {})

    def test_shares_that_overrun_are_refused(self):
        self.assertEqual(self.build([plan("Balkh", "Balkh", "Tajik 90%, Pashtun 40%")]), {})


if __name__ == "__main__":
    unittest.main()
