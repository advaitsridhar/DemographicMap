"""The Afrobarometer rounds are committed as counts, not as respondents.

Each round keeps, for every stratum, question and answer, how many people gave
it and their summed weight, sorted by answer: a row counts the people who gave
one answer to one question, and the rows follow the answers, not the order of
the interviews. What each reader publishes is pinned to what the committed
counts give, so a change to either that moves a figure fails here. No network.
"""

import datetime
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import afrobarometer as ab  # noqa: E402
from scripts.fetch_census import afrobarometer_r56 as r56  # noqa: E402
from scripts.fetch_census import afrobarometer_r8 as r8  # noqa: E402

# Each round's counts, the columns its rows are keyed by, the questions it
# counts and the interviews its reader's docstring gives.
ROUNDS = ((ab.COUNTS, ["country", "region"], ab.FIELDS, 53_444),
          (r8.COUNTS, ["country", "region"], r8.QUESTIONS, 48_084),
          (r56.COUNTS, ["round", "year", "country", "region"], r56.FIELDS, 7_192))
TAIL = ["question", "answer", "respondents", "weight"]
# All the folder holds: the counts, and the labels and region list they are
# read with.
COMMITTED = {"r9_counts.csv.gz", "r9_labels.json", "r8_counts.csv.gz",
             "r8_region_codebook.json", "r56_counts.csv.gz"}


def keyed(path, strata):
    """The counts as {(stratum..., question, answer): (respondents, weight)}."""
    return {tuple(r[c] for c in [*strata, "question", "answer"]):
            (int(r["respondents"]), float(r["weight"])) for r in ab.read_counts(path)}


def run(module, out, *argv):
    """A reader's main(), writing to out, with its log lines kept quiet."""
    with mock.patch.object(sys, "argv", [module.__name__, *argv, "--out", str(out)]), \
            mock.patch.object(module, "log"), mock.patch("common.log"):
        module.main()
    return out


class Counting(unittest.TestCase):

    def test_weights_are_added_in_the_order_their_respondents_come(self):
        interviews = [(("7", "70"), {"religion": "5"}, 0.1),
                      (("7", "70"), {"religion": "9"}, 0.5),
                      (("7", "70"), {"religion": "5"}, 0.2),
                      (("7", "70"), {"religion": "5"}, 0.3)]
        got = ab.tally_answers(interviews)
        # 0.1, 0.2 and 0.3 make 0.6000000000000001 added in that order, and
        # 0.6 added the other way round or summed exactly.
        self.assertEqual(got[("7", "70", "religion", "5")], [3, 0.6000000000000001])
        self.assertEqual(got[("7", "70", "religion", "9")], [1, 0.5])

    def test_the_file_follows_the_answers_not_the_interviews(self):
        """In the order answers first appear, a stratum's first rows would be
        its first respondent's answer to every question."""
        counted = ab.tally_answers([(("7", "70"), {"religion": "9", "language": "4"}, 1.0),
                                    (("7", "70"), {"religion": "5", "language": "2"}, 1.0)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "counts.csv.gz"
            ab.write_counts(path, ["country", "region"], counted)
            back = [(r["question"], r["answer"]) for r in ab.read_counts(path)]
        self.assertEqual(back, [("language", "2"), ("language", "4"),
                                ("religion", "5"), ("religion", "9")])

    def test_a_sum_survives_the_file_to_the_last_digit(self):
        weights = {("7", "70", "religion", "5"): [3, 0.1 + 0.2 + 0.3],
                   ("7", "70", "religion", ""): [1, 1 / 3]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "counts.csv.gz"
            ab.write_counts(path, ["country", "region"], weights)
            back = ab.read_counts(path)
        self.assertEqual([r["answer"] for r in back], ["", "5"])
        self.assertEqual([float(r["weight"]) for r in back], [1 / 3, 0.1 + 0.2 + 0.3])

    def test_an_interview_without_a_stratum_is_not_counted(self):
        self.assertIsNone(ab.respondent({"country": "", "region": "1760", "religion": "1",
                                         "ethnicity": "1", "language": "1", "weight": "1"}))


class TheCommittedCounts(unittest.TestCase):

    def test_the_folder_holds_counts_and_labels_and_nothing_else(self):
        """Exact paths, so a file of respondents under any name or in any
        subfolder is caught once it is tracked."""
        listed = subprocess.run(["git", "ls-files", "-z", "--", "data/raw/afrobarometer"],
                                cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout.split("\0")
        self.assertEqual(sorted(p for p in listed if p),
                         sorted(f"data/raw/afrobarometer/{name}" for name in COMMITTED))

    def test_a_release_is_kept_out_of_a_commit_wherever_it_is_saved(self):
        """.gitignore lets the five in and nothing else from the folder, and
        no SPSS or Stata file from anywhere."""
        def ignored(path):
            return subprocess.run(["git", "check-ignore", "--no-index", "-q", path],
                                  cwd=ROOT).returncode == 0
        for path in ("data/raw/afrobarometer/R9.Merge_39ctry.xlsx",
                     "data/raw/afrobarometer/r9_extract.csv.gz",
                     "data/raw/afrobarometer/old/r9_counts.csv.gz",
                     "R5.sav", "tests/R6.dta"):
            self.assertTrue(ignored(path), path)
        for name in COMMITTED:
            self.assertFalse(ignored(f"data/raw/afrobarometer/{name}"), name)

    def test_a_row_is_one_answer_and_the_rows_are_sorted(self):
        for path, strata, _, _ in ROUNDS:
            rows = ab.read_counts(path)
            self.assertEqual(list(rows[0]), [*strata, *TAIL], path.name)
            keys = [tuple(r[c] for c in [*strata, "question", "answer"]) for r in rows]
            self.assertEqual(keys, sorted(set(keys)), path.name)
            self.assertTrue(all(int(r["respondents"]) >= 1 for r in rows), path.name)

    def test_every_interview_is_counted_once_under_every_question(self):
        for path, strata, questions, interviews in ROUNDS:
            by_question = {q: Counter() for q in questions}
            for r in ab.read_counts(path):
                by_question[r["question"]][tuple(r[c] for c in strata)] += int(r["respondents"])
            first, *rest = by_question.values()
            for other in rest:
                self.assertEqual(other, first, path.name)
            self.assertEqual(sum(first.values()), interviews, path.name)


class ThePublishedFiles(unittest.TestCase):

    def test_each_reader_writes_what_is_committed(self):
        for module in (ab, r8, r56):
            with self.subTest(module.__name__), tempfile.TemporaryDirectory() as tmp:
                written = run(module, Path(tmp) / module.OUT).read_bytes()
                self.assertEqual(written, (ROOT / "data" / "processed" / module.OUT).read_bytes())

    def test_a_question_the_counts_lack_is_given_no_reason(self):
        """The workbook route has no Q2. Its counts leave language at the
        record's bare default in every region: no shares, no note, and no
        "too few people" reason for a question that was never counted."""
        rows = [r for r in ab.read_counts(ab.COUNTS) if r["question"] != "language"]
        without = {(r["country"], r["region"], r["question"], r["answer"]):
                   [int(r["respondents"]), float(r["weight"])] for r in rows}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r9.csv.gz"
            ab.write_counts(path, ["country", "region"], without)
            with mock.patch.object(ab, "COUNTS", path):
                records = json.loads(run(ab, Path(tmp) / "out.json").read_text())
        bare = ab.gap(ab.NOT_AVAILABLE)
        self.assertFalse([r["id"] for r in records
                          if r["language"] != bare or "language_note" in r])
        self.assertTrue([r["id"] for r in records if isinstance(r.get("religion"), list)])
        self.assertTrue([r["id"] for r in records if "too few" in str(r.get("religion"))])


class ReadingTheReleases(unittest.TestCase):
    """``--extract`` on small SPSS releases written here: what reaches the
    counts, and that an interview without a country or region is not among it."""

    def setUp(self):
        try:
            import pandas  # noqa: F401
            import pyreadstat  # noqa: F401
        except ImportError:
            self.skipTest("pyreadstat is not installed")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def release(self, name, columns, labels):
        import pandas
        import pyreadstat
        path = self.tmp / name
        pyreadstat.write_sav(pandas.DataFrame(columns), str(path),
                             variable_value_labels=labels)
        return str(path)

    def test_round_9_counts_codes_and_its_labels_come_along(self):
        nan = float("nan")
        path = self.release("r9.sav", {
            "COUNTRY": [10, 10, 10, nan], "REGION": [1620] * 4,
            "Q84A": [9990, 9990, 1621, 1621], "Q95": [1, 2, 1, 1],
            "Q2": [3, 3, nan, 3], "withinwt_hh": [1.5, 0.5, 2.0, 9.0]},
            {"COUNTRY": {10: "Eswatini"}, "REGION": {1620: "Hhohho"},
             "Q95": {1: "Christian only", 2: "Muslim only"}, "Q84A": {1621: "Swazi"},
             "Q2": {3: "siSwati"}})
        with mock.patch.multiple(ab, HERE=self.tmp, COUNTS=self.tmp / "r9.csv.gz",
                                 LABELS=self.tmp / "r9.json", log=mock.Mock()):
            ab.extract_sav(path)
            got = keyed(ab.COUNTS, ["country", "region"])
            tally, sample, _ = ab.tabulate()
            labels = ab.load_labels()
        stratum = ("10", "1620")
        self.assertEqual(got, {
            (*stratum, "religion", "1"): (2, 3.5), (*stratum, "ethnicity", "9990"): (2, 2.0),
            (*stratum, "language", "3"): (2, 2.0), (*stratum, "religion", "2"): (1, 0.5),
            (*stratum, "ethnicity", "1621"): (1, 2.0), (*stratum, "language", ""): (1, 2.0)})
        self.assertEqual(sample, {stratum: 3})
        self.assertEqual(tally[stratum]["language"], {"3": 2.0})
        self.assertEqual(labels["REGION"], {"1620": "Hhohho"})

    def test_round_8_counts_labels_with_the_codebook_filling_the_regions(self):
        nan = float("nan")
        path = self.release("r8.sav", {
            "COUNTRY": [1, 1, 1, nan, 1], "REGION": [740, 740, 741, 740, nan],
            "Q2": [4, 5, 4, 4, 4], "Q98A": [1] * 5, "Q81": [7] * 5,
            "withinwt_hh": [1.0, 0.25, 0.75, 9.0, 9.0]},
            {"COUNTRY": {1: "Tanzania"}, "REGION": {741: "Arusha Region"},
             "Q2": {4: "Kiswahili", 5: "Other"}, "Q98A": {1: "Catholic"},
             "Q81": {7: "Chagga"}})
        with mock.patch.multiple(r8, HERE=self.tmp, COUNTS=self.tmp / "r8.csv.gz",
                                 log=mock.Mock()):
            r8.extract(path)
            got = keyed(r8.COUNTS, ["country", "region"])
            _, sample, _ = r8.tabulate()
        # 740 has no label in the release and takes the codebook's; 741's own wins.
        self.assertEqual(sample, {("Tanzania", "Dodoma"): 2, ("Tanzania", "Arusha Region"): 1})
        self.assertEqual(got[("Tanzania", "Dodoma", "language", "Other")], (1, 0.25))
        self.assertEqual(got[("Tanzania", "Dodoma", "religion", "Catholic")], (2, 1.25))
        self.assertEqual(got[("Tanzania", "Arusha Region", "ethnicity", "Chagga")], (1, 0.75))

    def test_rounds_5_and_6_count_three_countries_by_round_and_year(self):
        def interviews(ethnicity, year):
            return {"COUNTRY": [2, 2, 9, 2], "REGION": [1, 1, 1, float("nan")],
                    "Q2": [1, 2, 1, 1], ethnicity: [1] * 4, "Q98A": [1] * 4,
                    "withinwt": [1.0, 2.0, 5.0, 9.0],
                    "DATEINTR": [datetime.datetime(year, 11, 28)] * 4}
        labels = {"COUNTRY": {2: "Burundi", 9: "Kenya"}, "REGION": {1: "Gitega"},
                  "Q2": {1: "Kirundi", 2: "Swahili"}, "Q98A": {1: "Roman Catholic"}}
        r5 = self.release("r5.sav", interviews("Q84", 2012), {**labels, "Q84": {1: "Hutu"}})
        r6 = self.release("r6.sav", interviews("Q87", 2014), {**labels, "Q87": {1: "Hutu"}})
        with mock.patch.multiple(r56, HERE=self.tmp, COUNTS=self.tmp / "r56.csv.gz",
                                 log=mock.Mock()):
            r56.extract({"R5": r5, "R6": r6})
            got = keyed(r56.COUNTS, ["round", "year", "country", "region"])
        # Kenya is in Round 9 and is not counted here, nor is an interview
        # with no region.
        self.assertEqual({key[:4] for key in got},
                         {("R6", "2014", "Burundi", "Gitega"),
                          ("R5", "2012", "Burundi", "Gitega")})
        self.assertEqual(got[("R5", "2012", "Burundi", "Gitega", "language", "Swahili")],
                         (1, 2.0))
        self.assertEqual(got[("R6", "2014", "Burundi", "Gitega", "ethnicity", "Hutu")],
                         (2, 3.0))


if __name__ == "__main__":
    unittest.main()
