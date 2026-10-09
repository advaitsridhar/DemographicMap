"""Afghanistan: the statistics office's 1396 estimates by province and district.

A synthetic sheet in the office's layout -- a summary of three provinces, then
a block per province opened by its Total row -- and drawn units for it. No
network.
"""

import json
import unittest
from pathlib import Path
from unittest import mock

from scripts.fetch_census import afghanistan_estimates as ae

ISO = {"01": "AF-KAB", "02": "AF-KAP", "03": "AF-PAR"}
NAMES = {"01": "Kabul", "02": "Kapisa", "03": "Parwan"}

# Province code -> its rows: (number, English name, rural F, rural M,
# urban F, urban M); a starred number is a temporary district.
ROWS = {
    "01": [("01", "Kabul city", 1000, 1100, 5000, 5200),
           ("02", "Paghman", 700, 760, 0, 0),
           ("03*", "new place", 200, 230, 0, 0)],
    "02": [("01", "Mahmud Raqi", 900, 950, 40, 45),
           ("02", "Koh Band", 300, 310, 0, 0),
           ("03", "Tagab", 600, 640, 0, 0)],
    "03": [("01", "Charikar", 1200, 1260, 300, 320),
           ("02", "Shutul", 150, 160, 0, 0),
           ("03", "Salang", 250, 260, 0, 0)],
}

# The drawn districts: province label -> district label -> row code. Shutul
# and Mahmud Raqi are drawn in the other province.
CROSSWALK = {
    "Kabul": {"Kabul": "0101", "Paghman": "0102"},
    "Kapisa": {"Koh Band": "0202", "Tagab": "0203", "Shutul": "0302"},
    "Parwan": {"Mahmudi Raqi": "0201", "Charikar": "0301", "Salang": "0303"},
}


def nine(rf: int, rm: int, uf: int, um: int) -> list[int]:
    return [rf, rm, rf + rm, uf, um, uf + um, rf + uf, rm + um, rf + rm + uf + um]


def blank(n: int) -> int | str:
    return n if n else "__"


def sheet(rows: dict | None = None) -> tuple[list[list], int]:
    """The sheet's rows and its settled total."""
    rows = rows or ROWS
    totals = {code: [sum(nine(*r[2:])[i] for r in block) for i in range(9)]
              for code, block in rows.items()}
    out: list[list] = [["Estimated Population by Civil Division"], ["No", "Province"]]
    grand = [sum(t[i] for t in totals.values()) for i in range(9)]
    out.append([None, "Total Including Nomadic", *grand, "مجموع", None])
    for code, t in totals.items():
        out.append([code, NAMES[code], *t, "ولایت", code])
    for code, block in rows.items():
        out.append([None, f"Settled Population of {NAMES[code]}"])
        out.append([None, "Total", *totals[code], "ټول", None])
        for no, name, *figs in block:
            out.append([no, name, *[blank(v) for v in nine(*figs)], "ولسوالی", no])
        if any("*" in r[0] for r in block):
            out.append(["* new place is temporary.", None, None, None, None, None,
                        None, None, None, None, None, "موقت", "*"])
    return out, grand[8]


def units() -> tuple[list[dict], list[dict]]:
    units1 = [{"id": f"P{code}", "name": NAMES[code], "iso_3166_2": ISO[code]}
              for code in ISO]
    pid = {NAMES[code]: f"P{code}" for code in ISO}
    units2 = [{"id": f"D{key}", "name": label, "parent": pid[province]}
              for province, districts in CROSSWALK.items()
              for label, key in districts.items()]
    return units1, units2


def patched(settled: int, **over):
    values = {"PROVINCE_ISO": ISO, "CROSSWALK": CROSSWALK, "SETTLED": settled,
              "TEMPORARY_PARENT": {"0103": "0102"}, "POINT_ELSEWHERE": {},
              "MISPRINTED": {}, "SHIFTED": {"0303"}}
    values.update(over)
    return mock.patch.multiple(ae, **values)


def named(rows: list[list], name: str) -> list:
    """The sheet's row for one district."""
    return next(r for r in rows if len(r) > 1 and r[1] == name)


def by_id(records: list[dict]) -> dict[str, dict]:
    return {r["id"]: r for r in records}


class Estimates(unittest.TestCase):
    def build(self, rows: list[list], settled: int, **over) -> dict[str, dict]:
        units1, units2 = units()
        with patched(settled, **over):
            return by_id(ae.build(rows, units1, units2))

    def test_districts_bound_by_shape_id_with_their_temporary_districts(self):
        rows, settled = sheet()
        records = self.build(rows, settled)
        self.assertEqual(len(records), 3 + 8)
        paghman = records["AFG-EST-0102"]
        self.assertEqual(paghman["match_by"], "shape_id")
        self.assertEqual(paghman["shape_id"], "D0102")
        self.assertEqual(paghman["population"]["value"], 700 + 760 + 200 + 230)
        self.assertEqual(paghman["population"]["year"], 2017)
        self.assertIn("Summed with New Place, a temporary district",
                      paghman["population_note"])
        self.assertEqual(paghman["sex_ratio"]["value"], round(100 * 990 / 900, 1))
        self.assertNotIn("AFG-EST-0103", records)
        self.assertEqual(records["AFG-EST-0101"]["population"]["value"], 12300)
        self.assertIn("1979", records["AFG-EST-0101"]["median_age"]["note"])

    def test_median_age_is_left_to_the_survey_file_where_its_report_is_read(self):
        # Kapisa (02) and Parwan (03) have their survey reports read, so this
        # file leaves the field bare there, Mahmudi Raqi (Kapisa's, drawn in
        # Parwan) included; Kabul's report is archived cut off, and says so.
        rows, settled = sheet()
        records = self.build(rows, settled)
        for key in ("AFG-EST-02", "AFG-EST-03", "AFG-EST-0201", "AFG-EST-0302"):
            self.assertEqual(records[key]["median_age"], {"status": "not_available"}, key)
        for key in ("AFG-EST-01", "AFG-EST-0101", "AFG-EST-0102"):
            note = records[key]["median_age"]["note"]
            self.assertIn("Socio-Demographic and Economic Survey of Kabul (2013)", note)
            self.assertIn("1 MiB", note)

    def test_a_province_the_survey_never_reached_says_so(self):
        from scripts.fetch_census.afghanistan_sdes import age_gap
        note = age_gap("3005")
        self.assertIn("twelve provinces between 2011 and 2016", note)
        self.assertIn("the province the office counts it in was not one of them", note)
        self.assertIn("this province was not one of them", age_gap("30"))
        with self.assertRaises(ValueError):
            age_gap("1001")

    def test_a_province_drawn_as_the_office_counts_it_takes_its_total(self):
        rows, settled = sheet()
        kabul = self.build(rows, settled)["AFG-EST-01"]
        self.assertEqual(kabul["shape_id"], "P01")
        self.assertEqual(kabul["population"]["value"], 12300 + 1460 + 430)
        self.assertIn("Kuchi", kabul["population_note"])
        self.assertEqual(kabul["sex_ratio"]["unit"], "males_per_100_females")

    def test_provinces_drawn_otherwise_take_their_drawn_districts_sum(self):
        # Kapisa is drawn with Koh Band, Tagab and Shutul (counted in Parwan)
        # and without Mahmudi Raqi: the polygon is those three districts.
        rows, settled = sheet()
        records = self.build(rows, settled)
        kapisa = records["AFG-EST-02"]
        females, males = 300 + 600 + 150, 310 + 640 + 160
        self.assertEqual(kapisa["population"]["value"], females + males)
        self.assertEqual(kapisa["sex_ratio"]["value"], round(100 * males / females, 1))
        self.assertIn("summed over the 3 districts", kapisa["population_note"])
        self.assertIn("Mahmudi Raqi, which the office counts here, is drawn in Parwan",
                      kapisa["population_note"])

    def test_a_province_drawn_with_a_refused_district_is_refused_and_says_why(self):
        # Parwan is drawn with Salang, whose own count is refused (SHIFTED).
        rows, settled = sheet()
        parwan = self.build(rows, settled)["AFG-EST-03"]
        self.assertNotIn("value", parwan["population"])
        self.assertNotIn("value", parwan["sex_ratio"])
        self.assertIn("Shutul, which the office counts here, is drawn in Kapisa",
                      parwan["population"]["note"])

    def test_provinces_drawn_otherwise_are_refused_and_say_why(self):
        rows, settled = sheet()
        records = self.build(rows, settled, POINT_ELSEWHERE={"0202": ("Kapisa", "Parwan")})
        kapisa, parwan = records["AFG-EST-02"], records["AFG-EST-03"]
        for province in (kapisa, parwan):
            self.assertNotIn("value", province["population"])
            self.assertNotIn("value", province["sex_ratio"])
        self.assertIn("Mahmudi Raqi, which the office counts here, is drawn in Parwan",
                      kapisa["population"]["note"])
        self.assertIn("Shutul, drawn here, is counted by the office in Parwan",
                      kapisa["population"]["note"])
        self.assertIn("Shutul, which the office counts here, is drawn in Kapisa",
                      parwan["population"]["note"])
        # The district itself is the office's row, wherever it is drawn.
        raqi = records["AFG-EST-0201"]
        self.assertEqual(raqi["population"]["value"], 1935)
        self.assertIn("The office counts it in Kapisa; the boundary file draws it in "
                      "Parwan.", raqi["population_note"])

    def test_a_point_in_another_polygon_refuses_both_provinces(self):
        rows, settled = sheet()
        records = self.build(rows, settled,
                             POINT_ELSEWHERE={"0102": ("Kabul", "Kapisa")})
        kabul = records["AFG-EST-01"]
        self.assertNotIn("value", kabul["population"])
        self.assertIn("the point of Paghman, drawn here, falls inside Kapisa's polygon",
                      kabul["population"]["note"])
        self.assertIn("the point of Paghman, drawn in Kabul, falls inside this one",
                      records["AFG-EST-02"]["sex_ratio"]["note"])

    def test_a_stale_point_entry_stops_the_run(self):
        rows, settled = sheet()
        with self.assertRaises(SystemExit):
            self.build(rows, settled, POINT_ELSEWHERE={"0102": ("Kapisa", "Parwan")})

    def test_a_misprinted_row_keeps_its_sex_ratio_only(self):
        # Koh Band prints 3,610 both-sexes people against 300 + 310 females
        # and males, rurally and in all: the province's Total row has 610.
        rows, settled = sheet()
        koh = named(rows, "Koh Band")
        koh[4] = koh[10] = 3610
        records = self.build(rows, settled,
                             MISPRINTED={"0202": "Koh Band prints 3,610 against 610."})
        koh = records["AFG-EST-0202"]
        self.assertNotIn("value", koh["population"])
        self.assertIn("3,610", koh["population"]["note"])
        self.assertEqual(koh["sex_ratio"]["value"], round(100 * 310 / 300, 1))

    def test_the_same_misprint_unnamed_stops_the_run(self):
        rows, settled = sheet()
        koh = named(rows, "Koh Band")
        koh[4] = koh[10] = 3610
        with self.assertRaises(SystemExit):
            self.build(rows, settled)

    def test_a_shifted_district_is_refused(self):
        rows, settled = sheet()
        salang = self.build(rows, settled)["AFG-EST-0303"]
        self.assertNotIn("value", salang["population"])
        self.assertNotIn("value", salang["sex_ratio"])
        self.assertEqual(salang["population"]["note"], ae.SHIFTED_NOTE)

    def test_districts_short_of_their_province_stop_the_run(self):
        rows, settled = sheet()
        named(rows, "Salang")[2:11] = nine(240, 260, 0, 0)    # ten females short
        with self.assertRaises(SystemExit):
            self.build(rows, settled)

    def test_the_national_total_is_checked(self):
        rows, settled = sheet()
        with self.assertRaises(SystemExit):
            self.build(rows, settled + 1)

    def test_a_temporary_district_without_a_parent_stops_the_run(self):
        rows, settled = sheet()
        with self.assertRaises(SystemExit):
            self.build(rows, settled, TEMPORARY_PARENT={})

    def test_a_drawn_district_with_no_row_stops_the_run(self):
        rows, settled = sheet()
        units1, units2 = units()
        units2.append({"id": "Dx", "name": "Unknown", "parent": "P01"})
        with patched(settled), self.assertRaises(SystemExit):
            ae.build(rows, units1, units2)

    def test_a_row_no_polygon_takes_stops_the_run(self):
        rows, settled = sheet()
        units1, units2 = units()
        units2 = [u for u in units2 if u["name"] != "Tagab"]
        with patched(settled), self.assertRaises(SystemExit):
            ae.build(rows, units1, units2)


class RealTables(unittest.TestCase):
    """The module's own constants, and the drawn units when the site is built."""

    def test_the_crosswalk_is_one_to_one_and_leaves_the_temporary_rows_out(self):
        codes = [key for districts in ae.CROSSWALK.values() for key in districts.values()]
        self.assertEqual(len(codes), 398)
        self.assertEqual(len(set(codes)), 398)
        self.assertFalse(set(codes) & set(ae.TEMPORARY_PARENT))
        for temp, parent in ae.TEMPORARY_PARENT.items():
            self.assertIn(parent, codes)
            self.assertEqual(temp[:2], parent[:2])
        self.assertLessEqual(set(ae.MISPRINTED) | ae.SHIFTED | set(ae.POINT_ELSEWHERE),
                             set(codes))
        self.assertEqual(len(ae.TEMPORARY_PARENT), 19)

    def test_the_drawn_units_and_the_provinces_drawn_otherwise(self):
        here = Path(__file__).resolve().parents[1]
        site = here / "site" / "data"
        if not (site / "admin2" / "AFG.units.json").exists():
            raise unittest.SkipTest("site/data has not been built")
        units1 = ae.load_units("AFG", "admin1", site)
        units2 = ae.load_units("AFG", "admin2", site)
        self.assertEqual(len(ae.drawn_districts(units1, units2)), len(units2))
        apart, counted_in = ae.drawn_apart(units1, units2)
        self.assertEqual(sorted(apart), ["02", "03", "08", "11", "12", "13", "14",
                                         "20", "21", "22", "26", "27"])
        self.assertEqual(len(counted_in), 9)
        drawn = json.loads((site / "admin2" / "AFG.units.json").read_text(encoding="utf-8"))
        self.assertEqual(len(drawn), 398)


if __name__ == "__main__":
    unittest.main()
