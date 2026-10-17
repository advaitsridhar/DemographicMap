"""Lesotho's 2016 census by community council, from the Bureau of Statistics'
village list (scripts/fetch_census/lesotho_census)."""

import io
import unittest
import zipfile
from unittest import mock

import openpyxl

from scripts.fetch_census import lesotho_census as ls

VILLAGES = [  # district, constituency, council, EA, village, men, women
    ("Botha-Bothe", "Mechechane", "Ngoajane", "01010113019", "HA LEKULA", 99, 80),
    ("", "", "", "", "HA SEAPI", 88, 87),
    ("", "", "", "1010113020", "BENTEKE", 68, 84),
    ("", "", "Botha-Bothe Urban Council", "1010113021", "BENONI", 156, 172),
    ("Leribe", "Hlotse", "Manka", "02010113001", "HA MOLAPO", 50, 55),
]


def workbook(villages=VILLAGES, break_total=False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, "2016 POPULATION AND HOUSING CENSUS VILLAGE LIST"])
    ws.append([None, "District", "Constituency", "Council", "Enumeration Area Code",
               "Ecological Zone", "Settlement", "Village Name", "Households", "Population"])
    ws.append([None] * 9 + ["Male", "Female", "Total"])
    ea_rows: list = []

    def close():
        if ea_rows:
            m = sum(r[0] for r in ea_rows)
            f = sum(r[1] for r in ea_rows)
            ws.append([None] * 7 + ["Total", 1, m, f, m + f + (1 if break_total else 0)])
            ea_rows.clear()

    for d, c, council, ea, village, m, f in villages:
        if ea:
            close()
        ws.append([None, d, c, council, ea, "Lowlands", "Rural", village, 10, m, f, m + f])
        ea_rows.append((m, f))
    close()
    book = io.BytesIO()
    wb.save(book)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("2016 POPULATION CENSUS VILLAGE LIST.xlsx", book.getvalue())
    return out.getvalue()


TOTAL = sum(m + f for *_, m, f in VILLAGES)
ADMIN1 = [{"id": "B", "name": "Butha-Buthe District"}, {"id": "L", "name": "Leribe District"}]
ADMIN2 = [{"id": "n", "name": "Ngoajane", "parent": "B"},
          {"id": "u", "name": "Butha-Buthe (Butha-Buthe District)", "parent": "B"},
          {"id": "m", "name": "Manka", "parent": "L"},
          {"id": "x", "name": "Butha-Buthe (Leribe District)", "parent": "L"}]


class LesothoCensusTest(unittest.TestCase):
    def table(self, **kw):
        with mock.patch.object(ls, "NATIONAL", TOTAL):
            return ls.parse(ls.rows_of(workbook(**kw)))

    def test_villages_are_added_up_by_council(self):
        t = self.table()
        self.assertEqual(t["councils"][("Botha-Bothe", "Ngoajane")]["total"], 99 + 80 + 88 + 87
                         + 68 + 84)
        self.assertEqual(t["councils"][("Botha-Bothe", "Ngoajane")]["villages"], 3)
        self.assertEqual(sum(t["districts"].values()), TOTAL)

    def test_an_enumeration_areas_total_line_must_match_its_villages(self):
        with self.assertRaises(SystemExit):
            self.table(break_total=True)

    def test_councils_bind_by_name_within_their_district_only(self):
        recs = {r["shape_id"]: r for r in ls.build(self.table(), ADMIN1, ADMIN2)}
        self.assertEqual(recs["u"]["population"]["value"], 156 + 172)
        self.assertEqual(recs["m"]["sex_ratio"]["value"], round(1000 * 50 / 55))
        self.assertNotIn("x", recs)             # a Butha-Buthe drawn in Leribe: no guess
        self.assertIn("villages added up", recs["n"]["population_note"])
        self.assertEqual(recs["n"]["median_age"]["status"], "not_available")


if __name__ == "__main__":
    unittest.main()
