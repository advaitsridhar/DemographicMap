"""Indonesia's Satu Data portals, read for the regencies the infobox left empty.

The fixtures are the tables as the runner printed them (probe_xlsx, and
data/processed/last-run.log of the --fetch runs), cut down to a few rows.
"""

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import group_tree  # noqa: E402
from scripts.fetch_census import indonesia_portals as p  # noqa: E402


def quiet(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        out = fn(*args, **kwargs)
    return out, buf.getvalue()


# East Kalimantan's sheet: a row number in the first column, a TOTAL row and a
# row of shares written as fractions, which as_count would read as a count of
# 874,455,186,306,684 people if the unit column were the row number.
KALTIM = [
    ["No.", "Kabupaten / Kota", "Islam", "Kristen", "Katolik", "Hindu", "Buddha",
     "Konghucu", "Jumlah"],
    [1, "Kab. Paser", 276235, 9857, 9461, 508, 517, 0, 296578],
    [7, "Kab. Mahakam Ulu", 8867, 5534, 22862, 49, 3, 0, 37315],
    [9, "Kota Samarinda", 775993, 43171, 21475, 828, 7904, 287, 849658],
    ["TOTAL", "", 3446652, 295113, 175114, 8644, 15607, 355, 3941485],
    ["%", "", 0.874455186306684, 0.074873556540238, 0.0444, 0.0021, 0.0039, 0.00009, 1],
]

# West Sumatra's: a title row above the header, a province row below it, the
# sexes in separate columns and a redundant total column beside them -- and
# the Christian pair headed in the reverse of the order the figures are in.
SUMBAR = [
    ["AGAMA - JENIS KELAMIN"],
    ["NO", "WILAYAH", "KODE", "ISLAM(LK)", "ISLAM(PR)", "ISLAM(JML)",
     "KATHOLIK(LK)", "KATHOLIK(PR)", "KATHOLIK(JML)",
     "KRISTEN(LK)", "KRISTEN(PR)", "KRISTEN(JML)"],
    ["", "SUMATERA BARAT", 13, 2813101, 2797660, 5610761, 45542, 42281, 87823,
     24384, 23720, 48104],
    [6, "AGAM", 1306, 263549, 262294, 525843, 2000, 1797, 3797, 257, 219, 476],
    [13, "KOTA PADANG", 1371, 452011, 453468, 905479, 7182, 7048, 14230,
     5802, 6323, 12125],
    [17, "KOTA BUKITTINGGI", 1375, 67592, 67345, 134937, 1207, 1085, 2292,
     566, 591, 1157],
]

# What the articles already say about those two, citing the same registry.
KNOWN_SUMBAR = {
    "Agam": {"Islam": 99.19, "Protestantism": 0.71, "Catholicism": 0.10},
    "Kota Padang": {"Islam": 96.87, "Protestantism": 1.52, "Catholicism": 1.29},
}


class Headers(unittest.TestCase):
    def test_a_faith_column_is_recognised_however_its_sex_is_marked(self):
        self.assertEqual(p.faith_of("ISLAM(JML)"), "Islam")
        self.assertEqual(p.faith_of("KHONGHUCU (L)"), "Confucianism")
        self.assertEqual(p.faith_of("Kepercayaan terhadap Tuhan"), "Kepercayaan "
                                                                  "(traditional belief)")
        self.assertEqual(p.faith_of("Agama Buddha"), "Buddhism")
        self.assertIsNone(p.faith_of("Jumlah"))
        self.assertIsNone(p.faith_of("KODE"))

    def test_the_total_column_is_dropped_where_the_halves_are_there(self):
        rows = p.rows_from_grid(SUMBAR, p.LABELS, "Sumatera Barat")
        agam = dict(rows)["AGAM"]
        # 263,549 + 262,294, once, not once more from ISLAM(JML).
        self.assertEqual(agam["Islam"], 525843)

    def test_the_unit_column_is_the_one_naming_places(self):
        rows = p.rows_from_grid(KALTIM, p.LABELS)
        self.assertEqual([unit for unit, _ in rows],
                         ["Kab. Paser", "Kab. Mahakam Ulu", "Kota Samarinda"])

    def test_the_province_row_and_the_footers_are_not_units(self):
        self.assertNotIn("SUMATERA BARAT",
                         dict(p.rows_from_grid(SUMBAR, p.LABELS, "Sumatera Barat")))
        units = dict(p.rows_from_grid(KALTIM, p.LABELS))
        self.assertNotIn("TOTAL", units)
        self.assertNotIn("%", units)


class Joining(unittest.TestCase):
    def test_a_prefix_and_a_spelling_are_matched_and_a_stranger_is_not(self):
        names = {"Paser": {}, "Kutai Kartanegara": {}, "Mahakam Hulu": {},
                 "Kota Samarinda": {}}
        self.assertEqual(p.match_unit("Kab. Paser", names), "Paser")
        self.assertEqual(p.match_unit("Kab. Mahakam Ulu", names), "Mahakam Hulu")
        self.assertEqual(p.match_unit("Samarinda", names), "Kota Samarinda")
        self.assertIsNone(p.match_unit("Kab. Nowhere", names))


class ChristianColumns(unittest.TestCase):
    def rows(self, n: int) -> list[tuple[str, dict[str, int]]]:
        """n copies of the two West Sumatra regencies the map already carries,
        because resolve_pair wants five units before it will decide."""
        base = [("AGAM", {"Islam": 525843, "Catholicism": 3797, "Protestantism": 476}),
                ("KOTA PADANG", {"Islam": 905479, "Catholicism": 14230,
                                 "Protestantism": 12125})]
        return [(f"{unit}{i or ''}", counts)
                for i in range(n) for unit, counts in base]

    def known(self, n: int) -> dict[str, dict[str, float]]:
        out = {}
        for i in range(n):
            for unit, shares in KNOWN_SUMBAR.items():
                out[f"{unit.upper()}{i or ''}".title()] = shares
        return out

    def test_a_workbook_headed_backwards_is_caught(self):
        # The column headed KATHOLIK holds 14,230 for Kota Padang, which is
        # 1.52% of the city -- the Protestant share Dukcapil publishes.
        rows, known = self.rows(3), self.known(3)
        swap, printed = quiet(p.resolve_pair, "sumbar", rows, known)
        self.assertTrue(swap, printed)
        self.assertIn("taking the swapped order", printed)

    def test_a_workbook_headed_the_usual_way_is_left_alone(self):
        rows = [(unit, p.swapped(counts)) for unit, counts in self.rows(3)]
        swap, printed = quiet(p.resolve_pair, "bengkulu", rows, self.known(3))
        self.assertFalse(swap, printed)
        self.assertIn("taking the printed order", printed)

    def test_too_few_units_to_score_is_read_as_printed_and_said_so(self):
        swap, printed = quiet(p.resolve_pair, "tangsel", self.rows(1), self.known(1))
        self.assertFalse(swap)
        self.assertIn("read as the table heads them", printed)

    def test_a_table_that_fits_neither_way_round_refuses(self):
        rows = [(unit, {"Islam": 1, "Protestantism": 40, "Catholicism": 59})
                for unit, _ in self.rows(3)]
        with self.assertRaises(SystemExit) as caught:
            quiet(p.resolve_pair, "nowhere", rows, self.known(3))
        self.assertIn("not published rather than guessed", str(caught.exception))


class Fields(unittest.TestCase):
    def test_the_note_names_the_portal_and_what_kind_of_count_it_is(self):
        source = next(s for s in p.SOURCES if s.key == "kaltim")
        fields = p.fields(source, {"Islam": 775993, "Protestantism": 43171,
                                   "Catholicism": 21475, "Buddhism": 7904,
                                   "Hinduism": 828, "Confucianism": 287}, False)
        self.assertEqual(fields["religion_year"], 2023)
        self.assertEqual(fields["religion"][0], {"group": "Islam", "pct": 91.33})
        self.assertAlmostEqual(sum(r["pct"] for r in fields["religion"]), 100.0, delta=0.02)
        note = fields["religion_note"]
        self.assertIn("data.kaltimprov.go.id", note)
        self.assertIn("Kementerian Agama", note)
        self.assertIn("not a census answer", note)
        self.assertLessEqual(note.count(". "), 3, note)
        self.assertEqual(fields["religion_source"]["field"], "religion")
        self.assertTrue(fields["religion_source"]["url"].startswith("https://"))

    def test_a_faith_too_small_to_round_to_a_hundredth_is_left_out(self):
        source = next(s for s in p.SOURCES if s.key == "sumbar")
        fields = p.fields(source, {"Islam": 101365, "Protestantism": 112,
                                   "Catholicism": 197, "Buddhism": 2}, True)
        self.assertNotIn("Buddhism", {r["group"] for r in fields["religion"]})
        self.assertIn("reverse of the order", fields["religion_note"])


class Committed(unittest.TestCase):
    """The four CSVs under data/raw are the deliverable; a refresh that
    silently reads a different table should fail here, not on the map."""

    def test_every_source_has_its_table_and_the_units_it_is_read_for(self):
        expected = {"sumbar": ("KOTA BUKITTINGGI", 19), "kaltim": ("Kota Samarinda", 10),
                    "bengkulu": ("Lebong", 10), "tangsel": ("Pamulang", 7)}
        for source in p.SOURCES:
            rows = p.committed(source)
            unit, count = expected[source.key]
            self.assertEqual(len(rows), count, source.key)
            self.assertIn(unit, dict(rows), source.key)
            for name, counts in rows:
                self.assertTrue(counts, f"{source.key}/{name} has no faiths")
                self.assertTrue(set(counts) <= set(p.FAITHS.values()),
                                f"{source.key}/{name}: {sorted(counts)}")

    def test_every_label_the_module_writes_has_a_family(self):
        for label in sorted(set(p.FAITHS.values())):
            self.assertTrue(group_tree.hue("religion", label), label)


if __name__ == "__main__":
    unittest.main()
