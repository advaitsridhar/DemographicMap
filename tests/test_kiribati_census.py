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


# The 2015 census's religion by island (Volume 1, Table 6): each line's total
# and 14 religions as the volume prints them. Its males and females are split
# here, a half each, which keeps every sum the reader checks.
TABLE6 = """
Banaba | 268 176 65 15 - 11 - 1 - - - - - - -
Makin | 1,990 1,588 317 5 1 47 8 9 - - 1 - - - 14
Butaritari | 3,224 2,660 426 56 3 49 - 21 - - 2 - - - 7
Marakei | 2,799 2,151 436 45 8 119 - 25 2 2 2 - - - 9
Abaiang | 5,568 4,195 937 19 26 198 20 105 2 - 2 4 34 3 23
NTarawa | 6,629 4,729 1,311 66 2 327 33 149 10 2 - - - - -
STarawa | 39,058 20,984 11,944 840 186 2,999 244 878 233 81 65 42 90 21 451
Betio | 17,330 10,403 5,258 293 21 728 34 266 68 31 1 22 9 6 190
Maiana | 1,982 1,071 768 28 - 76 - 22 1 - - 7 7 - 2
Abemama | 3,262 2,142 644 244 2 100 7 79 - 2 1 - - 9 32
Kuria | 1,046 474 423 87 1 34 - 19 - - - - - - 8
Aranuka | 1,125 602 450 16 - 51 - - - - 1 5 - - -
Nonouti | 2,743 1,520 1,012 44 - 65 - 84 10 7 - - 1 - -
NTabiteuea | 3,955 2,596 985 36 - 239 - 80 2 - 1 4 - 4 8
STabiteuea | 1,306 726 381 2 - 39 - 157 - - 1 - - - -
Beru | 2,051 602 1,339 12 - 67 - 31 - - - - - - -
Nikunau | 1,789 899 821 5 - 30 1 28 - 5 - - - - -
Onotoa | 1,393 378 935 - - 35 8 33 1 - - - - 2 1
Tamana | 1,104 22 1,058 14 - 4 - 6 - - - - - - -
Arorae | 1,011 14 991 - - - - 6 - - - - - - -
Teeraina | 1,712 888 710 53 - 8 - 53 - - - - - - -
Tabuaeran | 2,315 1,153 920 46 4 92 - 81 5 - - - - 6 8
Kiritimati | 6,456 3,136 2,323 138 25 536 9 181 18 9 - 2 - - 79
Kanton | 20 7 10 - - 3 - - - - - - - - -
"""
# The heading as the volume's text layer breaks it over lines.
HEADING = ("Total  Total \n Roman \nCatholic  KPC \n Seventh \nDay \nAdventist \n Church "
           "\nOf God \n Latter \nDay \nSaints \n \nAssembly \nof God  Bahai \n Jehova's "
           "\nWitness \n(Te Koaua) \n \nIslam \n Four \nSquare \n Te \nRan \n All \nNation "
           "\n No \nreligion \n \nOther ")


def figure(n):
    return "-" if n == 0 else f"{n:,}"


def table6_lines(text=TABLE6):
    """{line: {sex: [figures]}}, the country's added up from its islands."""
    rows = {}
    for line in text.strip().splitlines():
        name, _, cells = (part.strip() for part in line.partition("|"))
        total = [0 if c == "-" else int(c.replace(",", "")) for c in cells.split()]
        male = [c // 2 for c in total[1:]]
        female = [c - m for c, m in zip(total[1:], male)]
        rows[name] = {"Total": total, "Male": [sum(male)] + male,
                      "Female": [sum(female)] + female}
    return {"Kiribati": {sex: [sum(r[sex][i] for r in rows.values()) for i in range(15)]
                         for sex in ("Total", "Male", "Female")}, **rows}


def volume_pages(rows=None, heading=HEADING):
    """The 2015 volume's pages as pypdf gives them: contents, Table 1a, then Table 6
    over four pages, the next table starting on the last."""
    rows = rows or table6_lines()
    names = list(rows)
    contents = ("Table 1a: Population and No of Households by Island: 2010, 2015 ......... 31 \n"
                "Table 6: Population by island, sex and religion: 2015 ............. 56 \n"
                "Table 7: Population by Home Country, Sex, and Broad Age Group:  2015 ..... 60 ")
    stated = {n: r["Total"][0] for n, r in rows.items() if n != "Kiribati"}
    stated["STarawa"] += stated.pop("Betio")
    table1a = ["Table 1a: Population and No of Households by Island: 2010, 2015 ", " ",
               "Population Private Hhold Population Private Hhold",
               f"Total 103,058        16,043               {rows['Kiribati']['Total'][0]:,}  17,772"]
    table1a += [f"{n} 100 10 {c:,} 10" for n, c in stated.items()]
    pages = [contents, "\n".join(table1a) + "\n2010 2015\n32 "]
    chunks = [names[0:7], names[7:14], names[14:21], names[21:]]
    titles = ["Table 6: Population by island, sex and religion: 2015 \n \n \n"
              "Table 6: Population by island, sex and religion - census 2015"] + [
              "Table 6 cont: Population by island, sex and religion: 2015 "] * 3
    for number, (title, chunk) in enumerate(zip(titles, chunks), start=56):
        lines = ["99 years 4 1 3", "Total Urban Rural", f"{number - 1} "] if number == 56 else []
        lines += [title, heading]
        for name in chunk:
            if name != "Kiribati":
                lines.append(f"    {name}")
            for sex in ("Total", "Male", "Female"):
                lines.append(f"{sex} " + "   ".join(figure(n) for n in rows[name][sex]) + " ")
        lines.append(f"{number} ")
        if number == 59:
            lines += ["Table 7: Population by Home Country, Sex, and Broad Age Group:  2015 ",
                      "Total 0-14 15-24 25-34 35-49 50+", "    Total",
                      "Total 110,136     38,438    21,995       17,684     17,382    14,637 "]
        pages.append("\n".join(lines))
    return pages


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
                                          kc.read_report(counts),
                                          kc.read_religion(volume_pages()),
                                          load_units("KIR", "admin1"), load_units("KIR", "admin2"))

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
        self.assertEqual(census["language"]["status"], "not_available")

    def test_an_island_carries_the_offices_own_age_sex_and_ethnicity(self):
        betio = self.named(self.census, "Betio")
        self.assertEqual(betio["median_age"]["value"], 20.8)
        self.assertEqual(betio["sex_ratio"]["value"], 95.0)
        self.assertEqual(betio["ethnicity"][0]["group"], "I-Kiribati")
        kanton = self.named(self.census, "Kanton")
        self.assertEqual(kanton["median_age"]["value"], 17.9)
        phoenix = self.named(self.census, "Phoenix Islands")
        self.assertEqual(phoenix["median_age"]["value"], 17.9)
        gilbert = self.named(self.census, "Gilbert Islands")
        self.assertNotIn("median_age_note", gilbert)
        self.assertIn("Makin", gilbert["ethnicity_note"])

    def test_a_median_its_own_age_groups_contradict_is_not_used(self):
        banaba = self.named(self.census, "Banaba")
        self.assertEqual(banaba["median_age"]["status"], "not_available")
        self.assertIn("13.8", banaba["median_age"]["note"])
        self.assertIn("150 of its 333", banaba["median_age"]["note"])


class TheReligionOf2015(unittest.TestCase):
    def test_the_table_adds_up_and_agrees_with_table_1a(self):
        table6 = kc.read_religion(volume_pages())
        self.assertEqual(table6["Kiribati"]["Total"][0], kc.NATIONAL_2015)
        self.assertEqual(table6["Betio"]["Total"][:3], [17_330, 10_403, 5_258])
        self.assertEqual(table6["Kanton"]["Total"][0], 20)

    def test_a_misread_figure_stops_the_run(self):
        rows = table6_lines()
        rows["Kuria"]["Total"][2] += 1          # its religions no longer make its total
        with self.assertRaises(SystemExit):
            kc.read_table6(volume_pages(rows))
        rows = table6_lines()
        rows["Kuria"]["Male"][3] += 1            # nor its sexes
        rows["Kuria"]["Male"][0] += 1
        with self.assertRaises(SystemExit):
            kc.read_table6(volume_pages(rows))

    def test_a_heading_out_of_order_stops_the_run(self):
        with self.assertRaises(SystemExit):
            kc.read_table6(volume_pages(heading=HEADING.replace("Islam", "Isl am")))
        swapped = HEADING.replace(" Four \nSquare \n Te \nRan", " Te \nRan \n Four \nSquare")
        self.assertNotEqual(swapped, HEADING)
        with self.assertRaises(SystemExit):
            kc.read_table6(volume_pages(heading=swapped))

    def test_an_island_table_1a_counts_otherwise_stops_the_run(self):
        pages = volume_pages()
        pages[1] = pages[1].replace("Kuria 100 10 1,046 10", "Kuria 100 10 1,047 10")
        with self.assertRaises(SystemExit):
            kc.read_religion(pages)

    def test_a_row_with_a_cell_too_many_stops_the_run(self):
        broken = [p.replace("Total 1,982", "Total 1,982   1", 1) for p in volume_pages()]
        with self.assertRaises(SystemExit):
            kc.read_table6(broken)

    def test_the_contents_line_is_not_the_table(self):
        pages = volume_pages()
        with self.assertRaises(SystemExit):
            kc.read_table6(pages[:1])


class TheReligionRecords(unittest.TestCase):
    def setUp(self):
        counts = kc.read_profile(profile_book())
        self.census, _ = kc.build(counts, kc.read_cod(cod_book()), kc.read_report(counts),
                                  kc.read_religion(volume_pages()), load_units("KIR", "admin1"),
                                  load_units("KIR", "admin2"))

    def named(self, name):
        return next(r for r in self.census if r["name"] == name)

    def test_an_island_carries_its_2015_religion(self):
        betio = self.named("Betio")
        self.assertEqual(betio["religion_year"], 2015)
        self.assertEqual(betio["religion"][0], {"group": "Roman Catholic", "pct": 60.0,
                                                "count": 10_403})
        self.assertIn("KPC", betio["religion_note"])
        self.assertIn("Table 6", betio["religion_note"])
        self.assertEqual(sum(r["count"] for r in betio["religion"]), 17_330)

    def test_te_ran_and_all_nation_are_counted_as_other_and_named(self):
        abaiang = self.named("Abaiang")
        other = next(r for r in abaiang["religion"] if r["group"] == "Other religion")
        self.assertEqual(other["count"], 4 + 34 + 23)
        self.assertIn("'Te Ran'", abaiang["religion_note"])
        self.assertIn("'All Nation'", abaiang["religion_note"])
        beru = self.named("Beru")
        self.assertNotIn("Te Ran", beru["religion_note"])

    def test_the_groups_add_their_islands_makin_included(self):
        gilbert = self.named("Gilbert Islands")
        people = sum(r["count"] for r in gilbert["religion"])
        self.assertEqual(people, kc.NATIONAL_2015 - 1_712 - 2_315 - 6_456 - 20)
        self.assertIn("Makin", gilbert["religion_note"])
        phoenix = self.named("Phoenix Islands")
        self.assertEqual(sum(r["count"] for r in phoenix["religion"]), 20)


class TheReport(unittest.TestCase):
    def test_the_tables_add_up_and_agree_with_the_profile(self):
        report = kc.read_report(kc.read_profile(profile_book()))
        self.assertEqual(report["g2"]["Kiritimati"]["Male"], 3_837)
        self.assertEqual(report["a3"]["Kiritimati"]["Kiribati/Mix"], 662)
        self.assertNotIn("Banaba", report["medians"])
        self.assertEqual(report["medians"]["Makin"], 15.4)

    def test_a_misread_figure_stops_the_run(self):
        counts = kc.read_profile(profile_book())
        original = kc.G2
        try:
            kc.G2 = original.replace("Kuria | 1,190 605 585", "Kuria | 1,190 606 584")
            with self.assertRaises(SystemExit):
                kc.read_report(counts)
            kc.G2 = original.replace("Kuria | 1,190 605 585", "Kuria | 1,190 605 586")
            with self.assertRaises(SystemExit):
                kc.read_report(counts)
        finally:
            kc.G2 = original


if __name__ == "__main__":
    unittest.main()
