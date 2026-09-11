"""The year travels with the composition it describes, and nowhere else.

Thailand's national religion was the 2000 census dated 2021: the provinces
stamped no year, so the country's sum kept the 2021 the Factbook estimate it
replaced had been wearing. ``roll_up_field`` now drops a stamp its children
cannot agree on, which is right, and which left 42 country fields undated
because their divisions said nothing about when they were counted.

These are the two halves of the repair. The adapters stamp the census year
they read, so a summed parent has something honest to inherit; and the stamp
never travels without the figure -- neither out of an adapter, where a year
beside a gap would fall through ``merge_adapter`` onto somebody else's
numbers, nor out of the build.

**Why two exemption lists and not one.** An adapter change and the file it
writes are separate acts in this repository: ``run-adapter.yml`` exists because
the build sandbox cannot reach a statistical host, so a pull request that
changes an adapter cannot also produce its output. AWAITING_AN_ADAPTER_RUN is
that gap, named file by file, and it shrinks to nothing as the runs land.
UNDATED_BY_DESIGN is a different claim: a source that genuinely cannot be
dated, which no run will ever fix.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from common import dated, gap  # noqa: E402
from scripts.fetch_census._shared import record  # noqa: E402

FIELDS = ("religion", "ethnicity", "language")
PROCESSED = ROOT / "data" / "processed"

# A source that cannot be dated, for a reason about the source and not about
# the adapter. No adapter run will change these; they are not a backlog.
UNDATED_BY_DESIGN = {
    # Round 9 was fielded across 2021-2023 and the committed five-column
    # extract carries no interview date, so there is no per-country year to
    # read. One stamp cannot describe the round, and taking one from the
    # round's title would date Ghana's interviews by Zimbabwe's -- which is
    # the fault this whole file exists to prevent, not a smaller version of
    # it. Dating these means adding the interview-date column to the extract,
    # which needs the 24 MB published workbook and an --extract run.
    "afrobarometer_region.json": {"religion", "ethnicity"},
}

# The adapter now stamps the year; the committed file predates that and says
# nothing about it. Each entry comes off this list when its adapter is re-run
# through the "Run one adapter" workflow and the output is committed. A file
# that is NOT listed here must be dated -- that is what keeps a new adapter
# from shipping undated and quietly joining the backlog.
AWAITING_AN_ADAPTER_RUN = {
    "admin0.json",                                  # fetch_factbook
    "australia_state.json",                         # abs --level state
}


def processed_files():
    return sorted(PROCESSED.glob("*.json"))


def rows(path):
    body = json.loads(path.read_text(encoding="utf-8"))
    return body if isinstance(body, list) else []


class TheHelperStampsOnlyAFigure(unittest.TestCase):
    def test_a_composition_gets_the_year(self):
        self.assertEqual(dated([{"group": "Alpha", "pct": 100.0}], 2021), 2021)

    def test_a_gap_gets_none(self):
        self.assertIsNone(dated(gap("not_available"), 2021))
        self.assertIsNone(dated(gap("not_collected", "never asked"), 2021))

    def test_an_empty_composition_gets_none(self):
        """``shares()`` returns [] when the total is zero, before the ``or gap``."""
        self.assertIsNone(dated([], 2021))

    def test_no_year_stays_no_year(self):
        """A source that prints no year is not dated by having been read."""
        self.assertIsNone(dated([{"group": "Alpha", "pct": 100.0}], None))

    def test_record_drops_the_none_rather_than_writing_a_null(self):
        """Which is what lets the rule be one expression at the call site."""
        built = record("XXX-1", "Somewhere", level="admin1", parent="XXX",
                       religion=gap("not_available"),
                       religion_year=dated(gap("not_available"), 2021))
        self.assertNotIn("religion_year", built)
        self.assertEqual(built["religion"]["status"], "not_available")


class NoStampWithoutAFigure(unittest.TestCase):
    """A year beside a gap claims a measurement nobody took.

    It is also how a stamp outlives its value: ``merge_adapter`` lets a gap
    fall through to whatever the record already held, so a year travelling
    beside that gap would land on another source's figures and date them
    wrongly -- Thailand's fault again, one level down.
    """

    def test_every_stamp_has_a_composition_under_it(self):
        offenders = []
        for path in processed_files():
            # fetch_factbook guards these now; the committed file predates the
            # guard and carries 16 of them. It is the one file here that cannot
            # be refreshed as part of the change that fixed it -- today's
            # mirror has moved on, and re-running it would drop 36 countries'
            # compositions to free text for reasons this change is not about.
            if path.name in AWAITING_AN_ADAPTER_RUN:
                continue
            for row in rows(path):
                if not isinstance(row, dict):
                    continue
                for field in FIELDS:
                    if row.get(f"{field}_year") is None:
                        continue
                    if not isinstance(row.get(field), list):
                        offenders.append(
                            f"{path.name}: {row.get('id')} stamps {field}_year "
                            f"with no {field} composition")
        self.assertEqual([], offenders)


class EveryDatableSourceSaysItsYear(unittest.TestCase):
    """The gap this repair exists to close, held shut.

    An adapter reads one census or one survey round, so it knows the year; a
    composition arriving undated has dropped it on the way, and the country
    summed from those divisions loses its date for no reason anybody could
    state.
    """

    def undated(self):
        found = {}
        for path in processed_files():
            for row in rows(path):
                if not isinstance(row, dict):
                    continue
                for field in FIELDS:
                    if isinstance(row.get(field), list) and not row.get(f"{field}_year"):
                        found.setdefault(path.name, set()).add(field)
        return found

    def test_nothing_is_undated_but_the_two_lists_say_so(self):
        unexplained = {name: sorted(fields)
                       for name, fields in self.undated().items()
                       if name not in AWAITING_AN_ADAPTER_RUN
                       and not (UNDATED_BY_DESIGN.get(name, set()) >= fields)}
        self.assertEqual(
            {}, unexplained,
            "these files publish a composition and no year. Either the adapter "
            "should stamp the census year it read, or -- if the source "
            "genuinely mixes vintages -- it belongs in UNDATED_BY_DESIGN with "
            "the reason written out. Do not add it to AWAITING_AN_ADAPTER_RUN "
            "unless an adapter that stamps the year is already merged.")

    def test_the_backlog_only_shrinks(self):
        """A file that is dated must come off the list, not sit on it.

        A stale entry is worse than none: it reads as a promise that somebody
        still owes a run, and it exempts the file from the check above.
        """
        undated = self.undated()
        settled = sorted(name for name in AWAITING_AN_ADAPTER_RUN
                         if not undated.get(name))
        self.assertEqual(
            [], settled,
            "these files are dated now, so remove them from "
            "AWAITING_AN_ADAPTER_RUN")

    def test_an_exemption_names_a_file_that_exists(self):
        """An exemption for a file nobody writes any more is just stale text."""
        for name in set(UNDATED_BY_DESIGN) | AWAITING_AN_ADAPTER_RUN:
            self.assertTrue((PROCESSED / name).exists(), name)


class TheCuratedSeedDatesItsCompositions(unittest.TestCase):
    """The build's own copy of the rule.

    The provenance block states a year per country -- India's 2011, China's
    2020 -- and it was reaching the population and the sex ratio while the
    compositions beside them went out undated.
    """

    def test_a_curated_composition_takes_the_provenance_year(self):
        import build_entities as be

        entity = {"id": "IND-XX", "name": "Somewhere", "sources": []}
        be.apply_curated(
            entity,
            {"name": "Somewhere", "religion": [{"group": "Hindu", "pct": 80.0}]},
            {"source": "Census of India 2011", "year": 2011})
        self.assertEqual(entity["religion_year"], 2011)

    def test_provenance_without_a_year_stamps_nothing(self):
        import build_entities as be

        entity = {"id": "IND-XX", "name": "Somewhere", "sources": []}
        be.apply_curated(
            entity,
            {"name": "Somewhere", "religion": [{"group": "Hindu", "pct": 80.0}]},
            {"source": "Census of India 2011"})
        self.assertNotIn("religion_year", entity)

    def test_a_field_the_row_does_not_carry_is_not_dated(self):
        """The year belongs to the figure, so no figure means no year."""
        import build_entities as be

        entity = {"id": "IND-XX", "name": "Somewhere", "sources": []}
        be.apply_curated(
            entity,
            {"name": "Somewhere", "religion": [{"group": "Hindu", "pct": 80.0}]},
            {"source": "Census of India 2011", "year": 2011})
        self.assertNotIn("language_year", entity)
        self.assertNotIn("ethnicity_year", entity)


class AReplacedFigureTakesItsYearWithIt(unittest.TestCase):
    """California is the case, and it is Thailand's fault in miniature.

    The curated seed carried an ACS placeholder stamped 2022. The live ACS row
    replaced the figure, said nothing about a year, and the 2022 stayed --
    describing numbers it had never seen, on three states out of fifty-two,
    which was enough for the country's sum to inherit it and read as dated. It
    happened to be the right year. That is what made it worth removing: nothing
    on the record distinguished it from a wrong one.
    """

    def entity(self):
        return {"id": "USA-06", "name": "California",
                "ethnicity": [{"group": "Placeholder", "pct": 100.0}],
                "ethnicity_year": 2022,
                "ethnicity_basis": "seeded",
                "ethnicity_note": "Approximate, pending a live API pull.",
                "sources": []}

    def test_a_row_that_says_nothing_leaves_nothing_behind(self):
        import build_entities as be

        entity = self.entity()
        be.merge_adapter(entity, {
            "ethnicity": [{"group": "White alone", "pct": 40.0}], "sources": []})
        self.assertEqual(entity["ethnicity"][0]["group"], "White alone")
        for suffix in ("_year", "_basis", "_note"):
            self.assertNotIn(f"ethnicity{suffix}", entity)

    def test_a_row_that_does_say_so_is_what_is_kept(self):
        import build_entities as be

        entity = self.entity()
        be.merge_adapter(entity, {
            "ethnicity": [{"group": "White alone", "pct": 40.0}],
            "ethnicity_year": 2023, "ethnicity_note": "ACS table B03002.",
            "sources": []})
        self.assertEqual(entity["ethnicity_year"], 2023)
        self.assertEqual(entity["ethnicity_note"], "ACS table B03002.")
        self.assertNotIn("ethnicity_basis", entity)

    def test_a_field_the_row_does_not_touch_keeps_everything(self):
        """merge_adapter works field by field, and so does this."""
        import build_entities as be

        entity = self.entity()
        entity["religion"] = [{"group": "Catholic", "pct": 30.0}]
        entity["religion_year"] = 2020
        be.merge_adapter(entity, {
            "ethnicity": [{"group": "White alone", "pct": 40.0}], "sources": []})
        self.assertEqual(entity["religion_year"], 2020)

    def test_a_gap_row_replaces_nothing_and_clears_nothing(self):
        """A gap never overwrites a real value, so it never orphans one either."""
        import build_entities as be
        from common import gap as make_gap

        entity = self.entity()
        be.merge_adapter(entity, {"ethnicity": make_gap("not_available"),
                                  "sources": []})
        self.assertEqual(entity["ethnicity"][0]["group"], "Placeholder")
        self.assertEqual(entity["ethnicity_year"], 2022)


class TheDivisionsNowDateTheirCountry(unittest.TestCase):
    """End to end: what the adapter stamps is what the country's panel says.

    Russia is the case that can be run here -- its Rosstat workbooks are
    checked in, so the adapter produces this output in the sandbox rather than
    on a runner -- and it is one of the 42 country fields the roll-up's rule
    had left undated.
    """

    def test_russias_subjects_carry_the_2020_census_year(self):
        path = PROCESSED / "russia_subject.json"
        subjects = rows(path)
        self.assertTrue(subjects)
        for field in ("ethnicity", "language"):
            dated_rows = [s for s in subjects if s.get(f"{field}_year")]
            self.assertEqual(len(dated_rows), len(subjects), field)
            # Rosstat publishes the 2020 round with a 2021 reference date, and
            # that is the year the record carries -- see russia.YEAR.
            self.assertEqual({s[f"{field}_year"] for s in dated_rows}, {2021})

    def test_a_country_summed_from_them_would_agree_on_one_year(self):
        """Which is the condition ``roll_up_field`` needs to keep the stamp."""
        import build_entities as be

        subjects = rows(PROCESSED / "russia_subject.json")
        for field in ("ethnicity", "language"):
            years = {s.get(f"{field}_year") for s in subjects
                     if isinstance(s.get(field), list)} - {None}
            self.assertEqual(len(years), 1, field)
        self.assertTrue(hasattr(be, "roll_up_field"))


if __name__ == "__main__":
    unittest.main()
