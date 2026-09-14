"""The two territories' languages: where they come from and what they refuse.

Pakistan's four provinces and Islamabad answer the census's mother-tongue
question and are read from Table 11. Azad Jammu and Kashmir and Gilgit-
Baltistan are enumerated apart from the census proper and the Bureau publishes
no Table 11 for either, so each is read from its own government instead -- AJ&K
from Table 15.33 of its Statistical Year Book, Gilgit-Baltistan from Table
SR.3.1 of its MICS 2024-25 -- and each of those tables has one way of going
wrong that no total would catch.

**AJ&K's table has five numbered columns and eight languages in it.** Where a
district speaks something the headings do not name, the office writes the name
inside the cell: Bhimber's Dogri is printed under the column headed *Shina* and
its Punjabi under *Others*. A reader that took the heading would file Dogri
speakers as Shina, and every row would still add to 100.

**Gilgit-Baltistan's report spells Burushaski "Brushaski".** Which is why the
language was reported absent from 731 pages when it is on one of them, and why
the spelling is declared rather than matched.

Both readers are held to the control their own table supplies -- AJ&K's rows
to 100%, Gilgit-Baltistan's households to the total the same table prints --
and both refuse rather than guess when it fails.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import pakistan as pk  # noqa: E402


def cells(*spec):
    """(x0, x1, text) triples from ``(text, x0, x1)`` written left to right."""
    return [(x0, x1, text) for text, x0, x1 in spec]


# Page 213 of the AJ&K Statistical Year Book 2023, as probe_pdf --boxes
# reports it: Table 15.32's marriages above, Table 15.33's languages below,
# and the same ten district names down the left edge of both. The coordinates
# are the file's own.
AJK_HEADER = cells(("Kashmiri", 161, 194), ("Gojri", 247, 267),
                   ("Pahari", 324, 348), ("Shina", 404, 424),
                   ("Others", 481, 505))
AJK_ROWS = {
    "Muzaffarabad": cells(("Muzaffarabad", 80, 127), ("15", 177, 186),
                          ("35", 256, 265), ("50", 331, 340)),
    "Neelum": cells(("Neelum", 80, 106), ("20", 177, 186), ("10", 256, 265),
                    ("63", 331, 340), ("5", 412, 416), ("2", 468, 472),
                    ("Kundal", 474, 498), ("Shahi", 500, 519)),
    "Jhelum Valley": cells(("Jhelum", 80, 104), ("Valley", 106, 128),
                           ("15", 177, 186), ("35", 256, 265),
                           ("50", 331, 340)),
    "Bagh": cells(("Bagh", 80, 98), ("2", 182, 186), ("3", 261, 265),
                  ("95", 303, 311), ("Dhundi-Khairali", 314, 368)),
    "Haveli": cells(("Haveli", 80, 102), ("5", 182, 186), ("30", 256, 265),
                    ("65", 318, 327), ("Chibali", 329, 353)),
    "Poonch": cells(("Poonch", 80, 105), ("-", 183, 186), ("6", 261, 265),
                    ("94", 319, 327), ("Punchi", 329, 352)),
    "Sudhnoti": cells(("Sudhnoti", 80, 110), ("-", 183, 186), ("-", 262, 265),
                      ("95", 319, 327), ("Punchi", 329, 352), ("5", 491, 495)),
    "Kotli": cells(("Kotli", 80, 97), ("-", 183, 186), ("35", 256, 265),
                   ("63", 304, 312), ("Pahari", 314, 335),
                   ("Pothwari", 337, 367), ("-", 413, 416), ("2", 491, 495)),
    "Mirpur": cells(("Mirpur", 80, 104), ("-", 183, 186), ("10", 256, 265),
                    ("85", 318, 326), ("Mirpuri", 328, 354), ("-", 413, 416),
                    ("2", 491, 495)),
    "Bhimber": cells(("Bhimber", 80, 109), ("-", 183, 186), ("5", 261, 265),
                     ("30", 318, 326), ("Mirpuri", 328, 354),
                     ("30", 399, 408), ("Dogri", 410, 429), ("35", 475, 484),
                     ("Punjabi", 486, 511)),
}
AJK_CENTRES = [((x0 + x1) / 2.0, text) for x0, x1, text in AJK_HEADER]
AJK_LIMIT = min(b[0] - a[0] for a, b in zip(AJK_CENTRES, AJK_CENTRES[1:])) / 2.0


def ajk_page():
    """The whole page, marriages table included, in printed order."""
    page = [
        cells(("Table:", 80, 103), ("15.32", 105, 124),
              ("District-wise", 145, 189), ("Marriages", 289, 326)),
        # The trap: Table 15.32's own Muzaffarabad row, above 15.33 and with
        # the same name at the left of it.
        cells(("Muzaffarabad", 80, 127), ("5,850", 152, 171), ("15", 200, 208),
              ("5,920", 232, 251), ("14", 279, 287)),
        cells(("Table:15.33", 80, 122), ("Languages", 214, 252),
              ("Spoken", 254, 281), ("in", 283, 289), ("AJ&K", 291, 315)),
        cells(("%", 331, 340)),
        cells(("District", 95, 122)),
        AJK_HEADER,
        cells(("1", 106, 110), ("2", 175, 180), ("3", 255, 259),
              ("4", 334, 338), ("5", 412, 416), ("6", 491, 495)),
    ]
    page += [AJK_ROWS[name] for name in pk.AJK_DISTRICTS]
    page.append(cells(("Source:", 80, 103), ("Kashmir", 104, 129),
                      ("Liberation", 131, 161), ("Cell,", 163, 177),
                      ("Muzaffarabad", 179, 220)))
    return page


# The 2017 census populations Table 15.24 prints, which are what the ten rows
# are weighted by. Real figures, and they sum to the territory's own row.
AJK_PEOPLE = {
    "Muzaffarabad": 650370, "Neelum": 191251, "Jhelum Valley": 205431,
    "Bagh": 371919, "Haveli": 152124, "Poonch": 500571, "Sudhnoti": 297584,
    "Kotli": 774194, "Mirpur": 456200, "Bhimber": 432719,
}
AJK_WHOLE = {"TOTAL": sum(AJK_PEOPLE.values())}


class AReadPage:
    """Stands in for ``words_by_row``, which needs a PDF and a network."""

    def __init__(self, *pages):
        self.pages = pages

    def __call__(self, _blob, tolerance=2.0):
        return iter(self.pages)


class ReadingWithAPage:
    """Swap the module's page reader for a literal one, and put it back."""

    def pages(self, *pages):
        self.addCleanup(setattr, pk, "words_by_row", pk.words_by_row)
        pk.words_by_row = AReadPage(*pages)


class TheRoundingAddsUp(unittest.TestCase):
    def test_a_weighted_composition_comes_to_a_hundred_exactly(self):
        # Three roundings of a third each make 99.9, which on the page reads
        # as a source that does not cover its whole population.
        out = pk.to_hundred({"A": 100 / 3, "B": 100 / 3, "C": 100 / 3})
        self.assertEqual(round(sum(out.values()), 6), 100.0)

    def test_the_tenth_goes_to_the_largest_share(self):
        out = pk.to_hundred({"Big": 60.04, "Small": 39.94})
        self.assertEqual(out, {"Big": 60.1, "Small": 39.9})

    def test_a_composition_already_exact_is_left_alone(self):
        out = pk.to_hundred({"A": 50.0, "B": 50.0})
        self.assertEqual(out, {"A": 50.0, "B": 50.0})


class AjkLanguagesAreNamedByTheCellAndNotByTheColumn(unittest.TestCase):
    def row(self, district):
        row = AJK_ROWS[district]
        return pk.ajk_tongue_row(row[len(district.split()):], AJK_CENTRES,
                                 district, AJK_LIMIT)

    def test_a_heading_names_the_language_when_the_cell_does_not(self):
        self.assertEqual(self.row("Muzaffarabad"),
                         {"Kashmiri": 15.0, "Gojri": 35.0,
                          "Pahari-Pothwari": 50.0})

    def test_dogri_printed_under_shina_is_dogri(self):
        """The failure this reader exists to refuse.

        Bhimber has six languages and the table has five columns, so Dogri is
        printed under the heading *Shina* and Punjabi under *Others*. Filing
        either by its column would be a wrong row that adds up perfectly.
        """
        out = self.row("Bhimber")
        self.assertEqual(out, {"Gojri": 5.0, "Pahari-Pothwari": 30.0,
                               "Dogri": 30.0, "Punjabi": 35.0})
        self.assertNotIn("Shina", out)
        self.assertNotIn("Other languages", out)

    def test_the_local_names_of_pahari_fold_into_one_language(self):
        # Dhundi-Khairali, Chibali, Punchi, Pahari Pothwari and Mirpuri are
        # what five districts call their own variety, and the table files
        # every one of them in the Pahari column.
        for district in ("Bagh", "Haveli", "Poonch", "Kotli", "Mirpur"):
            with self.subTest(district=district):
                self.assertIn("Pahari-Pothwari", self.row(district))

    def test_pahari_is_not_published_under_the_bare_name(self):
        # "Pahari" is also a Tibeto-Burman language of Nepal, which this
        # project already carries. One label for two unrelated languages would
        # put four million people in the wrong family and the wrong colour.
        self.assertNotIn("Pahari", self.row("Bagh"))

    def test_an_unnamed_other_stays_a_residual(self):
        self.assertEqual(self.row("Sudhnoti"),
                         {"Pahari-Pothwari": 95.0, "Other languages": 5.0})

    def test_a_name_the_module_has_not_been_told_about_stops_the_run(self):
        row = cells(("Bagh", 80, 98), ("95", 303, 311), ("Balti", 314, 340))
        with self.assertRaises(SystemExit) as caught:
            pk.ajk_tongue_row(row[1:], AJK_CENTRES, "Bagh", AJK_LIMIT)
        self.assertIn("Balti", str(caught.exception))

    def test_a_figure_far_from_every_column_stops_the_run(self):
        row = cells(("Bagh", 80, 98), ("95", 600, 610))
        with self.assertRaises(SystemExit):
            pk.ajk_tongue_row(row[1:], AJK_CENTRES, "Bagh", AJK_LIMIT)

    def test_two_figures_in_one_column_stop_the_run(self):
        row = cells(("Bagh", 80, 98), ("50", 177, 186), ("45", 178, 187))
        with self.assertRaises(SystemExit):
            pk.ajk_tongue_row(row[1:], AJK_CENTRES, "Bagh", AJK_LIMIT)


class AjkTableIsFoundBelowItsOwnHeading(ReadingWithAPage, unittest.TestCase):
    def test_the_marriages_table_above_it_is_not_read(self):
        """Both tables are on page 213 with the same names down the side.

        A reader that took the first row beginning "Muzaffarabad" would come
        away with 5,850 marriages read as 5,850 per cent.
        """
        self.pages(ajk_page())
        found = pk.ajk_tongue_table(b"")
        self.assertEqual(set(found), set(pk.AJK_DISTRICTS))
        self.assertEqual(found["Muzaffarabad"],
                         {"Kashmiri": 15.0, "Gojri": 35.0,
                          "Pahari-Pothwari": 50.0})

    def test_a_caption_with_no_heading_under_it_is_the_contents(self):
        contents = [cells(("Table:15.33", 80, 122), ("Languages", 214, 252),
                          ("Spoken", 254, 281), ("in", 283, 289),
                          ("AJ&K", 291, 315), ("179", 520, 534))]
        self.pages(contents, ajk_page())
        self.assertEqual(set(pk.ajk_tongue_table(b"")), set(pk.AJK_DISTRICTS))

    def test_a_book_without_the_table_raises_lookup_rather_than_exiting(self):
        # The yearbook is reissued annually. A table that has gone should cost
        # the language field and leave the territory's religion standing.
        self.pages([cells(("Nothing", 80, 120), ("here", 130, 160))])
        with self.assertRaises(LookupError):
            pk.ajk_tongue_table(b"")

    def test_a_missing_district_stops_the_run(self):
        page = [row for row in ajk_page() if row is not AJK_ROWS["Bhimber"]]
        self.pages(page)
        with self.assertRaises(SystemExit):
            pk.ajk_tongue_table(b"")


class AjkWeighsItsDistrictsIntoOneRow(unittest.TestCase):
    """geoBoundaries draws Azad Kashmir as one second-level unit.

    So the ten printed rows have nowhere of their own to land and the only
    honest thing to do with them is add them up, weighted by the populations
    the religion table on the facing page already supplies.
    """

    def weighed(self, tongues=None):
        return pk.ajk_tongue_weighted(
            tongues or {name: pk.ajk_tongue_row(
                AJK_ROWS[name][len(name.split()):], AJK_CENTRES, name,
                AJK_LIMIT) for name in pk.AJK_DISTRICTS},
            {name: {"TOTAL": count} for name, count in AJK_PEOPLE.items()},
            AJK_WHOLE)

    def test_the_shares_come_to_a_hundred(self):
        out, _short = self.weighed()
        self.assertEqual(round(sum(out.values()), 6), 100.0)

    def test_pahari_pothwari_leads_and_dogri_survives_the_sum(self):
        out, _short = self.weighed()
        self.assertEqual(max(out, key=lambda k: out[k]), "Pahari-Pothwari")
        # Bhimber's 30% of 432,719 people, and the one language in the table
        # that exists only because a cell was read instead of a column.
        self.assertGreater(out["Dogri"], 2.0)

    def test_a_row_the_source_left_short_is_rescaled_and_said_so(self):
        """Mirpur's printed row sums to 97, and the other nine to 100.

        Three points of one district is 0.34% of the territory -- inside the
        half-point the page's own rounding repair would have absorbed without
        a word. So it is spread over Mirpur's own languages, where the people
        it describes live, and the note says which district and how much.
        """
        _out, short = self.weighed()
        self.assertIn("Mirpur", short)
        self.assertIn("97", short)

    def test_a_row_far_from_a_hundred_stops_the_run(self):
        tongues = {name: pk.ajk_tongue_row(
            AJK_ROWS[name][len(name.split()):], AJK_CENTRES, name, AJK_LIMIT)
            for name in pk.AJK_DISTRICTS}
        tongues["Bagh"] = {"Kashmiri": 40.0}
        with self.assertRaises(SystemExit):
            self.weighed(tongues)

    def test_districts_that_do_not_weigh_to_the_territory_stop_the_run(self):
        with self.assertRaises(SystemExit):
            pk.ajk_tongue_weighted(
                {name: {"Gojri": 100.0} for name in pk.AJK_DISTRICTS},
                {name: {"TOTAL": count} for name, count in AJK_PEOPLE.items()},
                {"TOTAL": AJK_WHOLE["TOTAL"] + 1})

    def test_the_records_carry_it_on_both_rows_and_no_year(self):
        out, short = self.weighed()
        rows = pk.ajk_records({}, dict(AJK_WHOLE, Muslim=AJK_WHOLE["TOTAL"]),
                              out, short)
        self.assertEqual({r["level"] for r in rows}, {"admin1", "admin2"})
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertIsInstance(row["language"], list)
                self.assertEqual(row["language_basis"], "languages spoken")
                # Table 15.33 prints no year and the yearbook's cover is not
                # one: dating the figures 2023 is the error the religion table
                # on the facing pages is careful to avoid.
                self.assertNotIn("language_year", row)
                self.assertIn("Kashmir Liberation Cell", row["language_note"])

    def test_without_the_table_both_rows_keep_a_stated_gap(self):
        rows = pk.ajk_records({}, dict(AJK_WHOLE, Muslim=AJK_WHOLE["TOTAL"]))
        for row in rows:
            self.assertEqual(row["language"]["status"], "not_available")
            self.assertIn("HC1B", row["language"]["note"])


# Table SR.3.1 of the Gilgit-Baltistan MICS 2024-25 Survey Findings Report, as
# it comes off page 57. Only the text matters to this reader, so the rows are
# written as the report prints them.
GB_PAGE_LINES = [
    "Table SR.3.1: Household composition",
    "Percent and frequency distribution of households, Gilgit-Baltistan, 2024-25",
    "Weighted percent",
    "Number of households",
    "Weighted Unweighted",
    "Total 100.0 6,929 6,929",
    "Sex of household head",
    "Male 86.1 5,964 5,905",
    "Female 13.9 965 1,024",
    "District",
    "Ghizer 13.7 947 692",
    "Gilgit 20.0 1,385 762",
    "Language of household head",
    "Shina 48.0 3,325 2,681",
    "Balti 29.2 2,025 2,450",
    "Brushaski 12.3 855 1,205",
    "Khowar 5.2 360 232",
    "Wakhi 1.0 71 132",
    "Other 4.2 293 229",
    "Sample coverage and characteristics of respondents | page 39",
]


def gb_page(lines=None):
    """One page as rows of word boxes; the x values are not read here."""
    page = []
    for line in (lines or GB_PAGE_LINES):
        at = 0.0
        row = []
        for word in line.split():
            row.append((at, at + 4.0 * len(word), word))
            at += 4.0 * len(word) + 4.0
        page.append(row)
    return page


class GilgitBaltistanReadsItsOwnSurvey(ReadingWithAPage, unittest.TestCase):
    def test_the_six_languages_and_the_survey_year(self):
        self.pages(gb_page())
        households, year = pk.gb_mics_language(b"")
        self.assertEqual(households, {"Shina": 3325, "Balti": 2025,
                                      "Burushaski": 855, "Khowar": 360,
                                      "Wakhi": 71, "Other languages": 293})
        # "2024-25" off the table's own caption, dated by where the fieldwork
        # ended rather than by the file's name.
        self.assertEqual(year, 2025)

    def test_the_report_spelling_is_translated_and_not_published(self):
        """731 pages reported no Burushaski because the report writes it
        Brushaski. The spelling is declared, so the map's name is one lookup
        rather than a guess at read time."""
        self.pages(gb_page())
        households, _year = pk.gb_mics_language(b"")
        self.assertNotIn("Brushaski", households)
        self.assertIn("Burushaski", households)

    def test_rows_that_do_not_sum_to_the_printed_total_stop_the_run(self):
        broken = [line.replace("Shina 48.0 3,325", "Shina 48.0 3,225")
                  for line in GB_PAGE_LINES]
        self.pages(gb_page(broken))
        with self.assertRaises(SystemExit) as caught:
            pk.gb_mics_language(b"")
        self.assertIn("households", str(caught.exception))

    def test_a_table_with_no_year_on_its_page_stops_the_run(self):
        undated = [line.replace(", 2024-25", "") for line in GB_PAGE_LINES]
        self.pages(gb_page(undated))
        with self.assertRaises(SystemExit):
            pk.gb_mics_language(b"")

    def test_a_report_without_the_table_raises_lookup(self):
        self.pages(gb_page(["Nothing here"]))
        with self.assertRaises(LookupError):
            pk.gb_mics_language(b"")

    def test_the_territory_publishes_the_survey_when_it_has_it(self):
        fields = pk.gb_language({"Shina": 3325, "Balti": 2025,
                                 "Burushaski": 855, "Khowar": 360,
                                 "Wakhi": 71, "Other languages": 293}, 2025)
        self.assertEqual(round(sum(g["pct"] for g in fields["language"]), 6),
                         100.0)
        self.assertEqual(fields["language"][0]["group"], "Shina")
        self.assertEqual(fields["language_year"], 2025)
        self.assertEqual(fields["language_basis"],
                         "language of the household head")
        # Households, so no count beside a group: a count there reads as
        # people everywhere else on this map.
        self.assertNotIn("count", fields["language"][0])

    def test_the_newspaper_account_is_the_fallback_and_not_the_figure(self):
        """The owner chose the Pamir Times article over a blank, twice.

        It stays as what the field falls back to when the survey report cannot
        be opened -- and the two disagree about which language leads, which is
        the clearest reason to prefer the office's own table when there is one.
        """
        fallback = pk.gb_language()
        self.assertEqual(fallback["language_year"], pk.GB_TONGUE_YEAR)
        self.assertEqual(fallback["language"][0]["group"], "Balti")
        survey = pk.gb_language({"Shina": 2, "Balti": 1}, 2025)
        self.assertEqual(survey["language"][0]["group"], "Shina")


class BangladeshSaysWhatWasAskedAndWhatWasPublished(unittest.TestCase):
    """The question *was* put -- and the answer still is not a composition.

    This class used to be called ``BangladeshSaysTheQuestionWasNeverPut`` and
    asserted exactly that, on the strength of the census questionnaire: 35
    questions, none of them language. The census's own project disproves the
    stronger half of it. The *Report on Socio-Economic and Demographic Survey
    2023* -- the long-questionnaire survey run after the census, published by
    the same Bureau as one of the five national reports of the Population and
    Housing Census 2021 Project -- collects mother tongue in Module 4 and
    publishes it in Table 3.6.

    So the invariant asserted here is the narrower, true one: the census does
    not ask; the survey does; what the survey publishes is a named group
    against a residual at the division and nothing below it; and therefore the
    field is a gap with a *reason*, marked ``not_available`` rather than
    ``not_collected``, because the map must not claim the Bureau never asked.
    """

    def setUp(self):
        from common import collection_policy, collection_status
        self.reason = collection_policy("BGD", "language")
        self.status = collection_status("BGD", "language")

    def test_the_reason_is_the_questionnaire_and_not_an_empty_file(self):
        self.assertTrue(self.reason)
        self.assertIn("35 questions", self.reason)

    def test_the_reason_names_the_survey_that_does_ask(self):
        # The half the old reason got wrong. Without this sentence the map
        # tells the reader Bangladesh never collects mother tongue, on the
        # very eight divisions for which the Bureau has published a table.
        self.assertIn("Socio-Economic and Demographic Survey 2023", self.reason)
        self.assertIn("Module 4", self.reason)
        self.assertIn("Table 3.6", self.reason)

    def test_the_reason_says_why_the_published_answer_cannot_be_drawn(self):
        # Two columns, one of them a residual, at a level two above the zila.
        self.assertIn("Bangla and Others", self.reason)
        self.assertIn("not a composition", self.reason)
        self.assertIn("nothing below the division", self.reason)

    def test_the_status_is_not_collected_no_longer(self):
        from common import NOT_AVAILABLE, NOT_COLLECTED
        self.assertEqual(self.status, NOT_AVAILABLE)
        self.assertNotEqual(self.status, NOT_COLLECTED)

    def test_religion_is_not_declared_with_it(self):
        # The same census asks religion and it is on the map from the same
        # workbook, so a declaration covering both would be false.
        from common import collection_policy
        self.assertIsNone(collection_policy("BGD", "religion"))

    def test_the_adapter_writes_the_declaration_rather_than_a_bare_gap(self):
        # The whole marker, status included: a zila saying "never asked" while
        # the country says "asked and not published this way" is the drift the
        # central table exists to prevent.
        from scripts.fetch_census import bangladesh
        self.assertEqual(bangladesh.LANGUAGE["note"], self.reason)
        self.assertEqual(bangladesh.LANGUAGE["status"], self.status)

    def test_no_zila_is_left_claiming_the_question_was_never_put(self):
        import json
        from common import NOT_COLLECTED, PROCESSED
        path = PROCESSED / "bangladesh_district.json"
        if not path.exists():  # pragma: no cover - built output may be absent
            self.skipTest("bangladesh_district.json has not been built")
        rows = json.loads(path.read_text())
        # Zilas only. The adapter also writes the eight divisions, which carry
        # the ethnic composition from Table P29 and take their language marker
        # from the central policy rather than restating it; counting the file
        # rather than the zilas made this test fail on 72 records the day that
        # arrived, which is a fact about the file and not about the claim.
        zilas = [row for row in rows if row["level"] == "admin2"]
        self.assertEqual(len(zilas), 64)
        self.assertEqual(len([r for r in rows if r["level"] == "admin1"]), 8)
        for row in zilas:
            language = row["language"]
            self.assertNotEqual(language.get("status"), NOT_COLLECTED, row["name"])
            self.assertIn("Socio-Economic and Demographic Survey 2023",
                          language.get("note", ""), row["name"])


if __name__ == "__main__":
    unittest.main()
