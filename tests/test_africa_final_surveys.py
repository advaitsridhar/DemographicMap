"""The Africa round's final sweep: what the Afrobarometer readers write.

Botswana's survey strata are added into the districts they make up, the
answer that names only a nationality is written as that, and the survey's
misspelt, French and twice-spelt labels are written as the groups are
called. The readers' rules are tested on hand-made tallies; the checks on
the written files skip where a file is not in this checkout. No network.
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import afrobarometer as ab  # noqa: E402
from scripts.fetch_census import afrobarometer_r56 as r56  # noqa: E402
from scripts.fetch_census import afrobarometer_r8 as r8  # noqa: E402

PROCESSED = ROOT / "data" / "processed"


def rows(filename):
    path = PROCESSED / filename
    if not path.exists():
        raise unittest.SkipTest(f"{filename} is not in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


def groups(row, field):
    value = row.get(field)
    return {g["group"]: g["pct"] for g in value} if isinstance(value, list) else {}


def respondents(row):
    """The respondents a row's notes count, published or too few."""
    for field in ("religion", "ethnicity", "language"):
        value = row.get(field)
        text = row.get(f"{field}_note") or (value.get("note") if isinstance(value, dict) else "")
        found = re.search(r"This region: (\d+) respondents|interviewed only (\d+) people", text or "")
        if found:
            return int(found.group(1) or found.group(2))
    return None


def cell(**fields):
    return {"religion": {}, "ethnicity": {}, "language": {}, **fields}


class BotswanaStrataMakeItsDistricts(unittest.TestCase):
    """North-East District showed North East's 40 respondents without
    Francistown's 56, which its polygon holds, and five districts showed
    nothing though the survey sampled them."""

    LABELS = {"REGION": {"147": "Francistown", "161": "North East", "153": "Kgatleng"}}

    def test_the_strata_are_added_into_the_district_that_holds_them(self):
        tally = {("4", "147"): cell(religion={"1": 40.0}, ethnicity={"2": 50.0}),
                 ("4", "161"): cell(religion={"1": 30.0, "2": 5.0}, ethnicity={"2": 35.0}),
                 ("4", "153"): cell(religion={"1": 60.0})}
        sample = {("4", "147"): 56, ("4", "161"): 40, ("4", "153"): 64}
        units = {u["name"]: u for u in ab.units(tally, sample, self.LABELS)}
        self.assertEqual(set(units), {"North-East District", "Kgatleng District"})
        north_east = units["North-East District"]
        self.assertEqual(north_east["key"], "North-East District")
        self.assertEqual(north_east["n"], 96)
        self.assertEqual(sorted(north_east["strata"]), ["Francistown", "North East"])
        # Weighted answers added, not shares averaged.
        self.assertEqual(north_east["cell"]["religion"], {"1": 70.0, "2": 5.0})
        self.assertEqual(units["Kgatleng District"]["strata"], ["Kgatleng"])

    def test_a_stratum_no_district_holds_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ab.units({("4", "999"): cell()}, {("4", "999"): 30},
                     {"REGION": {"999": "Okavango Delta"}})

    def test_other_countries_keep_the_survey_s_regions(self):
        (unit,) = ab.units({("10", "1620"): cell()}, {("10", "1620"): 300},
                           {"REGION": {"1620": "Hhohho"}})
        self.assertEqual((unit["key"], unit["name"], unit["n"]), ("1620", "Hhohho", 300))

    def test_every_round_9_stratum_of_botswana_has_its_district(self):
        if not ab.COUNTS.exists():
            self.skipTest("the Round 9 counts are not in this checkout")
        labels = ab.load_labels()
        _, sample, _ = ab.tabulate()
        strata = {labels["REGION"][region] for country, region in sample if country == "4"}
        self.assertEqual(len(strata), 24)
        self.assertFalse({s for s in strata if ("BWA", s) not in r8.REGIONS})

    def test_the_file_holds_the_ten_districts(self):
        data = {r["name"]: r for r in rows("afrobarometer_region.json") if r["country"] == "BWA"}
        self.assertEqual(len(data), 10)
        self.assertTrue(all(r["id"] == f"BWA-AB9-{name}" for name, r in data.items()))
        self.assertEqual(sum(respondents(r) for r in data.values()), 1200)
        self.assertNotIn("Francistown", data)
        self.assertNotIn("Gaborone", data)
        north_east = data["North-East District"]
        self.assertEqual(respondents(north_east), 96)
        self.assertIn("The survey stratifies the district as Francistown and North East, "
                      "and these shares are of their respondents together.",
                      north_east["language_note"])
        # Three of Southern's four strata are under 25 alone; together, 120.
        self.assertEqual(respondents(data["Southern District"]), 120)
        self.assertIsInstance(data["Southern District"]["religion"], list)
        # One stratum under its district's name says nothing about strata.
        self.assertNotIn("stratifies", data["Kgatleng District"]["religion_note"])
        # Chobe alone is still too thin, and says so.
        self.assertIn("only 16 people", data["Chobe District"]["religion"]["note"])


class NationalIdentityOnly(unittest.TestCase):
    """Eswatini's four regions read "No ethnic group" at 97 to 99.9%: code
    9990, "(National identity) only, or doesn't think of self in those terms"."""

    def test_round_9_writes_the_code_as_what_was_said(self):
        if not ab.LABELS.exists():
            self.skipTest("the Round 9 labels are not in this checkout")
        table = ab.load_labels()["Q84A"]
        self.assertIn("National identity", table[ab.NATIONAL_ONLY])
        self.assertEqual(ab.named("ethnicity", ab.NATIONAL_ONLY, table),
                         "National identity only")

    def test_rounds_5_and_6_write_it_alike(self):
        self.assertEqual(r56.answer("National identity only, or 'doesnt think of self "
                                    "in those terms'"), ab.NATIONAL_ONLY_LABEL)

    def test_it_is_filed_beside_no_ethnic_group(self):
        import canonical_groups as cg
        import group_tree
        for label in ("National identity only", "No ethnic group"):
            self.assertEqual(group_tree.parent_of("ethnicity", label),
                             "Unclassified ethnicity answers", label)
            self.assertTrue(cg.is_residual(label), label)

    def test_no_survey_file_says_no_ethnic_group(self):
        for filename in ("afrobarometer_region.json", "afrobarometer_r56.json"):
            for row in rows(filename):
                self.assertNotIn("No ethnic group", groups(row, "ethnicity"), row["id"])
        eswatini = [r for r in rows("afrobarometer_region.json") if r["country"] == "SWZ"]
        self.assertEqual(len(eswatini), 4)
        for row in eswatini:
            self.assertGreater(groups(row, "ethnicity")["National identity only"], 97)


class LabelsWrittenAsTheGroupsAreCalled(unittest.TestCase):
    """Zambia's "IIa", Madagascar's and Mauritius's French, Namibia's "Afrikaaner"."""

    FRENCH = (("language", "Malagasy officiel", "Official Malagasy"),
              ("language", "Malagasy avec spécificité régionale", "Malagasy (regional variety)"),
              ("ethnicity", "Hindou", "Hindu community"),
              ("ethnicity", "Musulman", "Muslim community"),
              ("ethnicity", "Tamoul", "Tamil"),
              ("ethnicity", "Telegou", "Telugu"),
              ("ethnicity", "Chinois", "Chinese"),
              ("ethnicity", "Afro-Mauricien (Creole)", "Afro-Mauritian (Creole)"),
              ("ethnicity", "Euro-Mauricien (Blanc)", "Euro-Mauritian (White)"),
              ("ethnicity", "Afrikaaner", "Afrikaner"))

    def test_ila_is_spelt_with_an_l(self):
        import group_tree
        self.assertEqual(ab.clean("IIa"), "Ila")
        self.assertEqual(group_tree.parent_of("language", "Ila"), "Bantu languages")

    def test_each_label_is_written_in_english_for_its_own_field(self):
        for field, said, written in self.FRENCH:
            self.assertEqual(ab.named(field, "1", {"1": said}), written, said)
        # A religion is not renamed by the ethnic list.
        self.assertEqual(ab.named("religion", "1", {"1": "Musulman"}), "Musulman")

    def test_each_keeps_its_place_in_the_tree(self):
        import group_tree
        for field, name, parent in (
                ("ethnicity", "Hindu community", "Unclassified ethnicity answers"),
                ("ethnicity", "Muslim community", "Unclassified ethnicity answers"),
                ("ethnicity", "Afro-Mauritian (Creole)", "Black or African (census category)"),
                ("ethnicity", "Euro-Mauritian (White)", "White or European (census category)"),
                ("ethnicity", "Afrikaner", "Germanic peoples"),
                ("ethnicity", "Tamil", "Dravidian peoples"),
                ("ethnicity", "Telugu", "Dravidian peoples"),
                ("ethnicity", "Chinese", "Han and Sinitic peoples"),
                ("language", "Official Malagasy", "Malagasy"),
                ("language", "Malagasy (regional variety)", "Malagasy")):
            self.assertEqual(group_tree.parent_of(field, name), parent, name)

    def test_the_file_carries_none_of_the_old_labels(self):
        old = {said for _, said, _ in self.FRENCH} | {"IIa", "Kiiraq", "Adergigna orHarari"}
        data = rows("afrobarometer_region.json")
        for row in data:
            for field in ("language", "ethnicity"):
                self.assertFalse(old & set(groups(row, field)), row["id"])
        zambia = {r["name"]: r for r in data if r["country"] == "ZMB"}
        self.assertIn("Ila", groups(zambia["Southern"], "language"))

    def test_a_label_two_codes_share_is_counted_once(self):
        # Mozambique's list has "Lomue" twice (550 and 559); in Zambézia the
        # second alone made it 5.2%.
        zambezia = {r["id"]: r for r in rows("afrobarometer_region.json")}["MOZ-AB9-547"]
        languages = groups(zambezia, "language")
        self.assertEqual(sum(1 for g in zambezia["language"] if g["group"] == "Lomue"), 1)
        self.assertEqual(max(languages, key=languages.get), "Lomue")


class TheTwoRoundsSpellALanguageAlike(unittest.TestCase):
    """Uganda's languages, summed from regions read from both rounds, listed
    Runyankole 9.4% beside Runyankore 0.9%, and Other beside Other language."""

    def test_round_8_takes_round_9_s_spelling(self):
        round_9 = {g for r in rows("afrobarometer_region.json") for g in groups(r, "language")}
        for written in r8.SPELLING.values():
            self.assertIn(written, round_9, written)
        round_8 = rows("afrobarometer_r8_language.json")
        for row in round_8:
            named = set(groups(row, "language"))
            self.assertFalse(named & (set(r8.SPELLING) | {"Other language"}), row["id"])
        uganda = {g for r in round_8 if r["country"] == "UGA" for g in groups(r, "language")}
        self.assertIn("Runyankore", uganda)

    def test_the_tree_files_both_spellings_together(self):
        import group_tree
        for one, other, parent in (("Runyankore", "Runyankole", "Bantu languages"),
                                   ("Ngakarimojong", "Karamojong", "Nilotic languages"),
                                   ("Kiiraqw", "Iraqw", "Cushitic languages")):
            self.assertEqual(group_tree.parent_of("language", one), parent, one)
            self.assertEqual(group_tree.parent_of("language", other), parent, other)
        self.assertEqual(group_tree.parent_of("language", "Diakanké"), "Mande languages")


class NotesSayWhatTheSurveyGives(unittest.TestCase):
    """Egypt's language note said no composition "is built" from the round."""

    def test_no_note_says_how_a_figure_was_made(self):
        for text in (r8.NO_LANGUAGE, r56.ONE_VALUE):
            self.assertNotRegex(text, r"\bbuil[dt]\b")
        self.assertIn("so it gives no language shares for its regions", r8.NO_LANGUAGE)
        botswana = [r for r in rows("afrobarometer_region.json") if r["country"] == "BWA"]
        for row in botswana:
            for field in ("religion", "ethnicity", "language"):
                note = row.get(f"{field}_note") or ""
                for word in ("summed", "shape", "map"):
                    self.assertNotIn(word, note, (row["id"], field))


class TheBuildReadsThePooledDistricts(unittest.TestCase):
    """What the build does with the districts and the national-identity answer."""

    @classmethod
    def setUpClass(cls):
        from scripts import build_entities as be
        cls.be = be

    def test_north_east_district_takes_its_pooled_row(self):
        # Francistown's stratum is in the district's row now, so the
        # refusal on the district's sole child no longer holds.
        self.assertNotIn(("BWA", "North-East District"), self.be.SOLE_CHILD_NOT_ITS_GROUND)

    def test_botswana_keeps_its_own_figures(self):
        for field in ("religion", "language", "ethnicity"):
            reason = self.be.COUNTRY_NOT_SUMMED[("BWA", field)]
            self.assertIn("survey estimates, from Afrobarometer's ninth round", reason)
        self.assertIn("Mongwato", self.be.COUNTRY_NOT_SUMMED[("BWA", "ethnicity")])

    def test_eswatini_says_why_it_shows_no_ethnic_groups(self):
        self.assertIn("ethnicity", self.be.WITHDRAWN_FIELDS["afrobarometer_region.json"]["SWZ"])
        reason = self.be.field_gap("SWZ", "ethnicity", "admin1")
        self.assertIn("1,186 of the 1,200 people", reason)
        self.assertIsNone(self.be.field_gap("SWZ", "religion", "admin1"))

    def test_the_count_is_the_survey_s(self):
        if not ab.COUNTS.exists():
            raise unittest.SkipTest("the Round 9 counts are not in this checkout")
        eswatini = [r for r in ab.read_counts(ab.COUNTS)
                    if r["country"] == "10" and r["question"] == "ethnicity"]
        self.assertEqual(sum(int(r["respondents"]) for r in eswatini), 1200)
        self.assertEqual(sum(int(r["respondents"]) for r in eswatini
                             if r["answer"] == ab.NATIONAL_ONLY), 1186)


if __name__ == "__main__":
    unittest.main()
