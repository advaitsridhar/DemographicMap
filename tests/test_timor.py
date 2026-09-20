"""Timor-Leste's two 2015 priority tables, its 2022 basic table, and the guards.

The grids here are the three sheets' real shape -- the stacked headers, the
column-numbering row of "-1.0", "-2.0", the male and female rows under every
municipality, the three label columns of the 2022 table, the footnote marker on
the exclave's name -- with a handful of groups rather than the census's full
lists. They are built rather than typed out so that all thirteen columns are
present, which is what the reader insists on: a table missing a municipality is
a table this project will not read.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
import group_tree  # noqa: E402
from fetch_census import timor  # noqa: E402

# The thirteen columns as the language sheet heads them: its own spellings,
# not this project's, "Lautem" and "Liquiça" and the footnoted exclave among
# them.
LANGUAGE_COLUMNS = ["Aileu", "Ainaro", "Baucau", "Bobonaro", "Covalima", "Dili",
                    "Ermera", "Lautem", "Liquiça", "Manatuto", "Manufahi",
                    "SAR1 of Oecusse", "Viqueque"]
# The religion sheet's, which are the same names shouted and differently
# accented.
RELIGION_ROWS = ["AILEU", "AINARO", "BAUCAU", "BOBONARO", "COVALIMA", "DILI",
                 "ERMERA", "LAUTÉM", "LIQUIÇA", "MANATUTO", "MANUFAHI",
                 "SAR1 OF OECUSSE", "VIQUEQUE"]
# Each municipality holds a hundred people, divided the same way, so the
# arithmetic a reader has to get right is visible: 13 x 100 = 1,300.
EACH = 100.0
TONGUES = {"Tetun Prasa": 60.0, "Fataluku": 30.0, "Mambai": 9.0,
           "Makuva": 1.0, "Other": 0.0}
FAITHS = {"Catholicism": 95.0, "Protestantism/ Evangelicalism": 3.0, "Islam": 1.0,
          "Buddhism": 0.0, "Hinduism": 0.0, "Traditional": 1.0, "Other": 0.0}
UNITS = len(LANGUAGE_COLUMNS)


def language_grid() -> list[list]:
    wide = len(LANGUAGE_COLUMNS) + 4
    grid = [
        ["Table 12 Population by Mother Tongue, Municipality and Urban/Rural Location"],
        ["Mother Tongue", "Timor-Leste", "", "", "Municipality"],
        ["", "Total", "Urban", "Rural", *LANGUAGE_COLUMNS],
        [f"-{i + 1}.0" for i in range(wide)],
        ["TIMOR-LESTE", EACH * UNITS, EACH * UNITS / 2, EACH * UNITS / 2,
         *[EACH] * UNITS],
    ]
    for tongue, count in TONGUES.items():
        grid.append([tongue, count * UNITS, count * UNITS / 2, count * UNITS / 2,
                     *[count] * UNITS])
    grid.append(["1 Special Adminstrative Region of Oe-Cusse Ambeno"])
    return grid


def religion_grid() -> list[list]:
    def row(label, scale=1.0):
        return [label, EACH * scale, *[v * scale for v in FAITHS.values()]]

    grid = [
        ["Table 11 Population by Municipality, Urban/Rural Location, Sex and Religion"],
        ["Municipality, urban/rural location, sex", "Total", "Religion",
         "", "", "", "", "", ""],
        ["", "", *FAITHS],
        [f"-{i + 1}.0" for i in range(len(FAITHS) + 2)],
        row("TIMOR LESTE", UNITS),
        row("Male", UNITS / 2), row("Female", UNITS / 2),
        row("Urban", UNITS / 2), row("Rural", UNITS / 2),
    ]
    for name in RELIGION_ROWS:
        grid += [row(name), row("Male", 0.5), row("Female", 0.5)]
    grid.append(["1 Special Adminstrative Region of Oe-Cusse Ambeno"])
    return grid


# The 2022 sheet's fourteen municipalities -- Atauro among them -- each with
# its administrative posts, and Aileu Vila with two sucos beneath it.
POSTS_2022 = {
    "Aileu": [("Aileu Vila", 70), ("Laulara", 50)],
    "Ainaro": [("Ainaro", 120)],
    "Atauro": [("Atauro", 80)],
    "Baucau": [("Baucau", 120)],
    "Bobonaro": [("Maliana", 120)],
    "Covalima": [("Suai", 120)],
    "Dili": [("Vera Cruz", 60), ("Cristo Rei", 60)],
    "Ermera": [("Gleno", 120)],
    "Lautém": [("Lospalos", 120)],
    "Liquiçá": [("Liquiçá", 120)],
    "Manatuto": [("Manatuto", 120)],
    "Manufahi": [("Same", 120)],
    "Oecusse": [("Pante Macassar", 120)],
    "Viqueque": [("Viqueque", 120)],
}


def population_grid() -> list[list]:
    grid = [
        ["Table 4.01: Population, by municipality, administrative post, suco, and by "
         "urban/rural location, sex"],
        [""],
        ["Municipality, administrative post, suco", "", "", "Urban/rural location, sex"],
        ["", "", "", "Total", "", "", "Urban", ""],
        ["", "", "", "Total", "Male", "Female", "Total", "Male"],
        ["1", "2", "3", "4", "5", "6", "7", "8"],
    ]
    national = sum(v for posts in POSTS_2022.values() for _p, v in posts)
    grid.append(["Timor-Leste", "", "", national, national // 2, national // 2, 0, 0])
    for municipality, posts in POSTS_2022.items():
        total = sum(v for _p, v in posts)
        grid.append([municipality, "", "", total, total // 2, total // 2, 0, 0])
        for post, value in posts:
            grid.append(["", post, "", value, value // 2, value // 2, 0, 0])
            if post == "Aileu Vila":
                grid.append(["", "", "Aissirimou", 40, 20, 20, 0, 0])
                grid.append(["", "", "Seloi Craic", 30, 15, 15, 0, 0])
    grid.append(["Source: Population and Housing Census 2022"])
    return grid


def read_all():
    language, language_totals, _ = timor.read_language(language_grid())
    religion, religion_totals, country, _ = timor.read_religion(religion_grid())
    population, posts, national, _ = timor.read_population(population_grid())
    return (language, language_totals, religion, religion_totals, country,
            population, posts, national)


class ReadingTheSheets(unittest.TestCase):
    def test_the_language_header_is_found_and_its_columns_named(self):
        counts, totals, title = timor.read_language(language_grid())
        self.assertIn("Mother Tongue", title)
        self.assertEqual(set(counts), set(timor.MUNICIPALITIES))
        self.assertEqual(totals["Oecusse"], EACH)
        self.assertEqual(counts["Oecusse"]["Fataluku"], 30.0)

    def test_the_column_numbering_row_is_not_a_mother_tongue(self):
        # "-1.0", "-2.0", ... is a row of numbers under a label of numbers,
        # and nothing but the absence of a letter tells it from a real row.
        counts, _totals, _title = timor.read_language(language_grid())
        for label in counts["Aileu"]:
            self.assertTrue(any(c.isalpha() for c in label), label)
        self.assertEqual(len(counts["Aileu"]), len(TONGUES))

    def test_the_country_row_is_the_check_and_not_a_tongue(self):
        counts, totals, _ = timor.read_language(language_grid())
        self.assertNotIn("TIMOR-LESTE", counts["Dili"])
        self.assertEqual(totals["Dili"], EACH)

    def test_the_censuss_other_becomes_a_named_language_row(self):
        counts, _totals, _ = timor.read_language(language_grid())
        self.assertIn("Other language", counts["Aileu"])
        self.assertNotIn("Other", counts["Aileu"])

    def test_a_municipality_spelling_the_reader_does_not_know_refuses(self):
        grid = [list(row) for row in language_grid()]
        grid[2][4 + LANGUAGE_COLUMNS.index("SAR1 of Oecusse")] = "Ambeno Enclave District"
        with self.assertRaises(SystemExit) as caught:
            timor.read_language(grid)
        self.assertIn("Oecusse", str(caught.exception))

    def test_the_religion_total_column_is_a_row_above_the_religions(self):
        counts, totals, country, title = timor.read_religion(religion_grid())
        self.assertIn("Religion", title)
        self.assertEqual(totals["Aileu"], EACH)
        self.assertEqual(country["Total"], EACH * UNITS)
        self.assertEqual(counts["Aileu"]["Catholic"], 95.0)

    def test_male_female_urban_and_rural_are_not_units(self):
        counts, _totals, _country, _ = timor.read_religion(religion_grid())
        self.assertEqual(set(counts), set(timor.MUNICIPALITIES))

    def test_the_religion_columns_are_matched_by_their_opening_word(self):
        # The sheet breaks the second heading across a line; a reader keyed on
        # the whole string would lose the column if the space closed.
        grid = [list(row) for row in religion_grid()]
        grid[2][3] = "Protestantism/Evangelicalism"
        counts, _totals, _country, _ = timor.read_religion(grid)
        self.assertEqual(counts["Dili"]["Protestant/Evangelical"], 3.0)

    def test_a_religion_column_gone_missing_refuses(self):
        grid = [list(row) for row in religion_grid()]
        grid[2][7] = "Animist"
        with self.assertRaises(SystemExit) as caught:
            timor.read_religion(grid)
        self.assertIn("religion columns", str(caught.exception))

    def test_the_population_sheets_three_label_columns_give_the_level(self):
        municipalities, posts, national, title = timor.read_population(population_grid())
        self.assertIn("4.01", title)
        self.assertEqual(national, sum(municipalities.values()))
        self.assertEqual(municipalities["Aileu"], 120)
        self.assertEqual(len(posts), sum(len(p) for p in POSTS_2022.values()))

    def test_a_suco_is_not_an_administrative_post(self):
        _municipalities, posts, _national, _ = timor.read_population(population_grid())
        self.assertNotIn("Aissirimou", [p for p, _parent, _v in posts])
        self.assertIn("Aileu Vila", [p for p, _parent, _v in posts])

    def test_atauro_is_read_as_its_own_2022_municipality(self):
        municipalities, posts, _national, _ = timor.read_population(population_grid())
        self.assertEqual(municipalities[timor.ATAURO], 80)
        self.assertIn((timor.ATAURO, timor.ATAURO, 80), posts)

    def test_a_municipality_the_2022_sheet_names_and_the_reader_does_not_refuses(self):
        grid = [list(row) for row in population_grid()]
        grid[7][0] = "Aileu District"
        with self.assertRaises(SystemExit) as caught:
            timor.read_population(grid)
        self.assertIn("does not know", str(caught.exception))


class TheChecks(unittest.TestCase):
    def test_the_real_shaped_grids_pass_every_check(self):
        (language, language_totals, religion, religion_totals, country,
         population, posts, national) = read_all()
        timor.check_language(language, language_totals)
        timor.check_religion(religion, religion_totals, country)
        timor.check_population(population, posts, national)

    def test_a_tongue_dropped_from_a_column_refuses(self):
        grid = [list(row) for row in language_grid()]
        column = 4 + LANGUAGE_COLUMNS.index("Dili")
        grid[6][column] = 0.0          # Dili loses its thirty Fataluku speakers
        counts, totals, _ = timor.read_language(grid)
        with self.assertRaises(SystemExit) as caught:
            timor.check_language(counts, totals)
        self.assertIn("Dili", str(caught.exception))

    def test_a_municipality_that_does_not_add_to_its_own_total_refuses(self):
        grid = [list(row) for row in religion_grid()]
        row = 9 + 3 * RELIGION_ROWS.index("DILI")
        grid[row][2] = 94.0            # Dili's Catholics, one short
        counts, totals, country, _ = timor.read_religion(grid)
        with self.assertRaises(SystemExit) as caught:
            timor.check_religion(counts, totals, country)
        self.assertIn("Dili", str(caught.exception))

    def test_municipalities_that_do_not_add_to_the_country_row_refuse(self):
        grid = [list(row) for row in religion_grid()]
        grid[4][1] += 1.0              # the country row alone moves
        grid[4][2] += 1.0
        counts, totals, country, _ = timor.read_religion(grid)
        with self.assertRaises(SystemExit) as caught:
            timor.check_religion(counts, totals, country)
        self.assertIn("country row", str(caught.exception))

    def test_two_tables_of_different_universes_refuse(self):
        base = timor.NATIONAL_BASE / len(timor.MUNICIPALITIES)
        language_totals = {name: base for name in timor.MUNICIPALITIES}
        religion_totals = dict(language_totals)
        religion_totals["Dili"] = base + 1
        with self.assertRaises(SystemExit) as caught:
            timor.check_bases(language_totals, religion_totals)
        self.assertIn("Dili", str(caught.exception))

    def test_a_base_that_is_not_the_published_one_refuses(self):
        totals = {name: 1.0 for name in timor.MUNICIPALITIES}
        with self.assertRaises(SystemExit) as caught:
            timor.check_bases(totals, dict(totals))
        self.assertIn("release has changed", str(caught.exception))

    def test_posts_that_do_not_add_to_their_municipality_refuse(self):
        municipalities, posts, national, _ = timor.read_population(population_grid())
        posts = [(p, parent, v - 1 if p == "Lospalos" else v) for p, parent, v in posts]
        with self.assertRaises(SystemExit) as caught:
            timor.check_population(municipalities, posts, national)
        self.assertIn("Lautém", str(caught.exception))

    def test_a_2022_country_row_that_does_not_match_the_municipalities_refuses(self):
        municipalities, posts, national, _ = timor.read_population(population_grid())
        with self.assertRaises(SystemExit) as caught:
            timor.check_population(municipalities, posts, national + 1)
        self.assertIn("country row", str(caught.exception))


class TheNationalCheck(unittest.TestCase):
    """The published figures the run is checked against, exercised on the real
    counts rather than on the toy grids."""

    COUNTRY = {"Total": float(timor.NATIONAL_BASE), "Catholic": 1_150_990.0}
    # The national column of table 12, for the tongues the map's country row
    # names. One municipality's worth is enough: check_published sums over
    # whatever municipalities it is given.
    LANGUAGE = {"Dili": {
        "Tetun Prasa": 361_027.0, "Mambai": 195_778.0, "Makasai": 123_840.0,
        "Tetun Terik": 71_418.0, "Baikenu": 69_190.0, "Kemak": 68_995.0,
        "Bunak": 64_686.0, "Tokodede": 46_784.0, "Fataluku": 41_500.0,
        "Waima'a": 21_227.0, "Galoli": 16_266.0, "Naueti": 16_507.0,
        "Idate": 14_178.0, "Midiki": 14_616.0,
    }}

    def test_the_published_national_figures_pass(self):
        timor.check_published(self.LANGUAGE, self.COUNTRY,
                              float(timor.NATIONAL_POPULATION_2022))

    def test_a_2022_country_row_that_is_not_the_published_one_refuses(self):
        with self.assertRaises(SystemExit) as caught:
            timor.check_published(self.LANGUAGE, self.COUNTRY, 1_300_000.0)
        self.assertIn("census published", str(caught.exception))

    def test_a_catholic_share_off_the_published_one_refuses(self):
        country = {**self.COUNTRY, "Catholic": 1_100_000.0}
        with self.assertRaises(SystemExit) as caught:
            timor.check_published(self.LANGUAGE, country,
                                  float(timor.NATIONAL_POPULATION_2022))
        self.assertIn("Catholicism", str(caught.exception))

    def test_a_mother_tongue_off_the_country_rows_share_refuses(self):
        language = {"Dili": {**self.LANGUAGE["Dili"], "Fataluku": 4_150.0}}
        with self.assertRaises(SystemExit) as caught:
            timor.check_published(language, self.COUNTRY,
                                  float(timor.NATIONAL_POPULATION_2022))
        self.assertIn("Fataluku", str(caught.exception))


class TheRecords(unittest.TestCase):
    def setUp(self):
        (language, language_totals, religion, religion_totals, _country,
         population, posts, _national) = read_all()
        self.rows = timor.build(language, language_totals, religion,
                                religion_totals, population, posts)
        self.by_name = {row["name"]: row for row in self.rows
                        if row["level"] == "admin1"}
        self.posts = {row["name"]: row for row in self.rows
                      if row["level"] == "admin2"}

    def test_thirteen_municipalities_and_every_post(self):
        self.assertEqual(sorted(self.by_name), sorted(timor.MUNICIPALITIES))
        self.assertEqual(len(self.posts), sum(len(p) for p in POSTS_2022.values()))

    def test_atauro_is_summed_into_dili_rather_than_left_to_miss_a_shape(self):
        self.assertEqual(self.by_name["Dili"]["population"]["value"], 200)  # 120 + 80
        self.assertNotIn(timor.ATAURO, self.by_name)
        self.assertIn("Atauro", self.by_name["Dili"]["population"]["note"])

    def test_atauros_post_is_scoped_to_the_shape_that_contains_it(self):
        post = self.posts["Atauro"]
        self.assertEqual(post["parent_name"], "Dili")
        self.assertEqual(post["codes"]["census_municipality_2022"], "Atauro")
        self.assertEqual(post["codes"]["municipality"], "Dili")

    def test_every_post_says_which_municipality_it_is_in(self):
        for name, row in self.posts.items():
            self.assertIn(row["parent_name"], timor.MUNICIPALITIES, name)

    def test_every_composition_carries_its_year_and_a_note(self):
        for name, row in self.by_name.items():
            for field in ("language", "religion"):
                self.assertIsInstance(row[field], list, name)
                self.assertEqual(row[f"{field}_year"], timor.COMPOSITION_YEAR)
                self.assertTrue(row[f"{field}_note"])
                self.assertAlmostEqual(sum(g["pct"] for g in row[field]), 100.0,
                                       delta=0.6)

    def test_a_note_opens_with_what_the_figure_is_and_where_it_is_from(self):
        note = self.by_name["Aileu"]["language_note"]
        self.assertTrue(note.startswith("Mother tongue as the 2015 census counted it"))
        self.assertIn("Volume 2 priority tables", note)

    def test_a_post_carries_a_stated_gap_and_not_a_bare_one(self):
        post = self.posts["Lospalos"]
        for field in ("language", "religion"):
            self.assertEqual(post[field]["status"], common.NOT_AVAILABLE)
            self.assertIn("below the municipality", post[field]["note"])
        self.assertEqual(post["population"]["value"], 120)

    def test_ethnicity_is_the_declaration_and_not_a_gap(self):
        for row in self.rows:
            self.assertEqual(row["ethnicity"]["status"], common.NOT_COLLECTED)
            self.assertIn("E58", row["ethnicity"]["note"])

    def test_every_row_names_the_source_of_every_figure_it_carries(self):
        for row in self.rows:
            fields = {source["field"] for source in row["sources"]}
            self.assertIn("population", fields, row["name"])
            if row["level"] == "admin1":
                self.assertEqual(fields, {"population", "language", "religion"})

    def test_a_tongue_under_a_twentieth_of_a_percent_is_left_out_of_the_rows(self):
        counts = {"Tetun Prasa": 999.0, "Makuva": 1.0}
        rows = timor.composition(counts, 10_000.0)
        self.assertEqual([r["group"] for r in rows], ["Tetun Prasa"])
        self.assertEqual(timor.dropped(counts, 10_000.0), 1)

    def test_a_group_with_nobody_in_it_is_not_a_row(self):
        # The census prints a zero for every tongue in every municipality,
        # and "Other 0.0%" is not a fact worth a row.
        for row in self.by_name.values():
            for field in ("language", "religion"):
                for entry in row[field]:
                    self.assertGreater(entry["count"], 0, entry["group"])


class TheLabels(unittest.TestCase):
    def test_every_religion_label_is_placed_in_the_tree(self):
        for label in timor.RELIGION_LABELS:
            self.assertTrue(group_tree.parent_of("religion", label), label)

    def test_the_censuss_mother_tongues_are_placed(self):
        # Every one of the 38 the 2015 table names, except Sa'ani, which the
        # literature does not settle between the Austronesian and the Papuan
        # side and which is therefore left unplaced on purpose.
        tongues = [
            "Tetun Prasa", "Tetun Terik", "Adabe", "Atauran", "Baikenu", "Bekais",
            "Bunak", "Dadu'a", "Fataluku", "Galoli", "Habun", "Idalaka", "Idate",
            "Isni", "Kairui", "Kawaimina", "Kemak", "Lakalei", "Lolein", "Makalero",
            "Makasai", "Makuva", "Mambai", "Midiki", "Nanaek", "Naueti", "Rahesuk",
            "Raklungu", "Resuk", "Tokodede", "Waima'a", "Portuguese", "Indonesian",
            "English", "Malay", "Chinese", "Other language",
        ]
        for tongue in tongues:
            self.assertTrue(group_tree.parent_of("language", tongue), tongue)
        self.assertEqual(group_tree.parent_of("language", "Fataluku"),
                         "Papuan languages")
        self.assertEqual(group_tree.parent_of("language", "Adabe"),
                         "Papuan languages")
        self.assertEqual(group_tree.parent_of("language", "Atauran"),
                         "Malayo-Polynesian languages")

    def test_the_curly_apostrophe_the_census_prints_is_flattened(self):
        self.assertEqual(timor.tidy("Waima’a"), "Waima'a")
        self.assertEqual(timor.tidy("  Dadu’a \n"), "Dadu'a")

    def test_a_footnote_marker_is_not_part_of_the_exclaves_name(self):
        for spelling in ("SAR1 of Oecusse", "SAR1 OF OECUSSE", "Oé-Cusse Ambeno",
                         "RAEOA", "Oecussi"):
            self.assertEqual(timor.MUNICIPALITY_KEYS[timor.fold(spelling)], "Oecusse")

    def test_the_two_workbooks_spellings_meet(self):
        for spelling in ("Lautem", "LAUTÉM"):
            self.assertEqual(timor.MUNICIPALITY_KEYS[timor.fold(spelling)], "Lautém")
        for spelling in ("Liquiça", "LIQUIÇA", "Likisá"):
            self.assertEqual(timor.MUNICIPALITY_KEYS[timor.fold(spelling)], "Liquiçá")
        self.assertEqual(timor.MUNICIPALITY_KEYS[timor.fold("Covalima")], "Cova Lima")

    def test_no_capital_is_an_alias_of_its_municipality(self):
        # Maliana, Suai, Same and Lospalos are administrative posts as well as
        # towns; as first-level aliases they would pull a municipality's row
        # onto a second-level shape.
        aliases = {timor.fold(a) for names in timor.MUNICIPALITIES.values()
                   for a in names}
        for capital in ("Maliana", "Suai", "Same", "Lospalos", "Los Palos",
                        "Pante Macassar", "Gleno"):
            self.assertNotIn(timor.fold(capital), aliases, capital)


class ThePolicy(unittest.TestCase):
    def test_timor_leste_declares_ethnicity_uncollected_with_its_evidence(self):
        marker = common.collection_gap("TLS", "ethnicity")
        self.assertEqual(marker["status"], common.NOT_COLLECTED)
        self.assertIn("E58", marker["note"])
        self.assertIn("questionnaire", marker["note"])

    def test_religion_and_language_are_not_declared_uncollected(self):
        # Both are asked, both are published, and a declaration here would
        # contradict the compositions this adapter writes.
        for field in ("religion", "language"):
            self.assertIsNone(common.collection_gap("TLS", field), field)

    def test_the_declaration_reaches_a_unit_that_says_nothing(self):
        row = {"religion": common.gap(common.NOT_AVAILABLE),
               "ethnicity": common.gap(common.NOT_AVAILABLE)}
        applied = common.apply_collection_policy(row, "TLS")
        self.assertEqual(applied, ["ethnicity"])
        self.assertEqual(row["ethnicity"]["status"], common.NOT_COLLECTED)
        self.assertEqual(row["religion"]["status"], common.NOT_AVAILABLE)


if __name__ == "__main__":
    unittest.main()
