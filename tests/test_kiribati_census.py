"""Kiribati, 2020 census: the Office's island counts and SPC's age and sex table.

The fixtures follow the two workbooks' layouts -- an island sheet with its
"Population (Census)" row under 2015 and 2020, the summary sheet's island
block from column J, and SPC's sheets with one column per sex and five-year
group -- filled with the census's own island counts. No network.
"""

import unittest

from scripts.fetch_census import kiribati_census as kc
from scripts.fetch_census.oceania_common import load_units


class Sheet:
    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, values_only=True):
        return iter(self.rows)


class Book(dict):
    @property
    def sheetnames(self):
        return list(self.keys())

    def __getitem__(self, name):
        return Sheet(dict.__getitem__(self, name))


# The 2020 census by island, as the Island Profile workbook gives it.
COUNTS = {"Banaba": 333, "Makin": 1914, "Butaritari": 3250, "Marakei": 2738, "Abaiang": 5815,
          "North Tarawa": 7018, "South Tarawa": 44643, "Betio": 18429, "Maiana": 2345,
          "Abemama": 3255, "Kuria": 1190, "Aranuka": 1221, "Nonouti": 2749,
          "NTabiteuea": 4181, "STabiteuea": 1356, "Beru": 2214, "Nikunau": 2055,
          "Onotoa": 1417, "Tamana": 1028, "Arorae": 994, "Teraina": 1893, "Tabuaeran": 1990,
          "Kiritimati": 7369, "Kanton": 41}


def island_sheet(count):
    return [[None, "Banaba", None, None, None],
            [None, None, None, 2015, 2020],
            ["Population (Census)", None, None, 268, count],
            ["Percent of national population", None, None, 0.0024, 0.0028]]


def summary_sheet(counts):
    rows = [[None] * 9 + ["(Village)", "0-5", "6-14", "15-17", "18-49", "50+", "Total"]]
    for sheet, count in counts.items():
        name = kc.SUMMARY_NAMES.get(sheet, sheet)
        young = count // 5
        rows.append([None] * 9 + [name, young, young, young, young, count - 4 * young, count])
    total = sum(counts.values())
    rows.append([None] * 9 + ["Total", total // 5, total // 5, total // 5, total // 5,
                              total - 4 * (total // 5), total])
    return rows


def profile_book(counts=COUNTS):
    sheets = {name + (" " if name in ("Beru", "Tabuaeran") else ""): island_sheet(count)
              for name, count in counts.items()}
    sheets["Check"] = summary_sheet(counts)
    return Book(sheets)


BANDS = [(lo, lo + 4) for lo in range(0, 65, 5)]
HEADER_TAIL = (["F_TL", "M_TL", "T_TL"]
               + [f"F_{lo:02d}_{hi:02d}" for lo, hi in BANDS] + ["F_65Plus"]
               + [f"M_{lo:02d}_{hi:02d}" for lo, hi in BANDS] + ["M_65Plus"])


def cod_row(names, males, females):
    """A row whose people sit in the first three age groups, a third in each."""
    def spread(n):
        third = n // 3
        return [third, third, n - 2 * third] + [0] * (len(BANDS) - 2)
    return names + [females, males, males + females] + spread(females) + spread(males)


def cod_book():
    adm1 = [["ADM1_EN"] + HEADER_TAIL,
            cod_row(["Gilbert Islands"], 53260, 55401), cod_row(["Line Islands"], 5894, 5385),
            cod_row(["Phoenix Islands"], 0, 0)]
    rows = []
    for _, row in kc.ISLANDS.values():
        if row:
            rows.append(cod_row([row], 1000, 900))
    rows += [cod_row(["South Tarawa"], 30458, 32981), cod_row(["Betio"], 0, 0),
             cod_row(["Kanton"], 0, 0)]
    adm2 = [["ADM2_EN"] + HEADER_TAIL] + rows
    adm3 = [["ADM3_EN"] + HEADER_TAIL, cod_row(["BetioEast"], 9049, 9516),
            cod_row(["Bairiki"], 1679, 1821)]
    return Book({"kir_admpop_adm1_2020": adm1, "kir_admpop_adm2_2020": adm2,
                 "kir_admpop_adm3_2020": adm3})


class TheOfficesCounts(unittest.TestCase):
    def test_the_islands_make_the_census(self):
        self.assertEqual(sum(COUNTS.values()), kc.NATIONAL)
        counts = kc.read_profile(profile_book())
        self.assertEqual(counts["Betio"], 18_429)
        self.assertEqual(counts["Tarawa Teinainano"], 44_643)
        self.assertEqual(counts["Makin"], 1_914)

    def test_a_sheet_the_summary_contradicts_stops_the_run(self):
        book = profile_book()
        dict.__setitem__(book, "Kuria", island_sheet(1191))
        with self.assertRaises(SystemExit):
            kc.read_profile(book)


class SPCsTable(unittest.TestCase):
    def test_betio_is_its_village_and_teinainano_the_rest(self):
        cod = kc.read_cod(cod_book())
        self.assertEqual((cod["Betio"]["male"], cod["Betio"]["female"]), (9049, 9516))
        self.assertEqual(cod["Tarawa Teinainano"]["male"], 30458 - 9049)
        self.assertEqual(cod["Line Islands"]["female"], 5385)

    def test_a_row_whose_groups_miss_its_total_stops_the_run(self):
        book = cod_book()
        rows = dict.__getitem__(book, "kir_admpop_adm3_2020")
        rows[1][2] += 1
        with self.assertRaises(SystemExit):
            kc.read_cod(book)


class TheRecords(unittest.TestCase):
    def setUp(self):
        counts = kc.read_profile(profile_book())
        self.census, self.ages = kc.build(counts, kc.read_cod(cod_book()),
                                          load_units("KIR", "admin1"),
                                          load_units("KIR", "admin2"))

    def named(self, records, name):
        return next(r for r in records if r["name"] == name)

    def test_every_drawn_unit_has_both_records(self):
        for records in (self.census, self.ages):
            self.assertEqual(sum(r["level"] == "admin1" for r in records), 3)
            self.assertEqual(sum(r["level"] == "admin2" for r in records), 23)

    def test_the_gilbert_islands_count_makin_too(self):
        gilbert = self.named(self.census, "Gilbert Islands")
        self.assertEqual(gilbert["population"]["value"],
                         kc.NATIONAL - 1893 - 1990 - 7369 - 41)
        self.assertIn("Makin", gilbert["population_note"])

    def test_kanton_says_why_it_has_no_age(self):
        kanton = self.named(self.ages, "Kanton")
        self.assertEqual(kanton["median_age"]["status"], "not_available")
        self.assertIn("41", kanton["median_age"]["note"])

    def test_an_island_carries_spcs_figures_and_says_whose(self):
        betio = self.named(self.ages, "Betio")
        self.assertEqual(betio["sex_ratio"]["value"], 95.1)
        self.assertIn("BetioEast", betio["sex_ratio_note"])
        census = self.named(self.census, "Betio")
        self.assertEqual(census["religion"]["status"], "not_available")


if __name__ == "__main__":
    unittest.main()
