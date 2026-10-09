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


def aged_row(names, males, females):
    """A row with the given people per five-year group (13 closed, then 65+), by sex."""
    return names + [sum(females), sum(males), sum(males) + sum(females)] + females + males


# Butaritari's 3,250 people in five-year groups that keep Table A-10a's own broad
# groups -- 448 under five, 1,328 under 15, 1,421 aged 15-49, 358 aged 50-64 and
# 143 over -- split between the sexes as Table G-2 does (1,626 and 1,624).
BUTARITARI_M = [230, 225, 225, 100, 110, 115, 110, 100, 90, 86, 65, 60, 54, 56]
BUTARITARI_F = [218, 215, 215, 100, 110, 115, 110, 100, 90, 85, 65, 60, 54, 87]

# A country whose groups give everyone 22.7, males 21.8 and females 24.0.
NATION_M = [110, 110, 110, 110, 166, 80, 70, 60, 50, 40, 30, 25, 20, 19]
NATION_F = [100, 100, 100, 100, 125, 90, 80, 70, 60, 50, 40, 35, 25, 25]


def cod_book(butaritari=False):
    adm1 = [["ADM1_EN"] + HEADER_TAIL,
            cod_row(["Gilbert Islands"], 53260, 55401), cod_row(["Line Islands"], 5894, 5385),
            cod_row(["Phoenix Islands"], 0, 0)]
    rows = []
    for _, row in list(kc.ISLANDS.values()) + list(kc.UNDRAWN.values()):
        if row == "Butaritari" and butaritari:
            rows.append(aged_row([row], BUTARITARI_M, BUTARITARI_F))
        elif row:
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


class TheCountrysMedians(unittest.TestCase):
    """SPC's groups stand for the census's ages only if they give the Office's own
    country medians (Census Atlas, Table 2: 22.9, males 21.8, females 24.0)."""

    def nation(self, males=NATION_M, females=NATION_F):
        row = aged_row(["Kiribati"], males, females)
        book = Book({"t": [["ADM1_EN"] + HEADER_TAIL, row]})
        return {"Kiribati": kc.age_table(kc.rows_of(book, "t"), "ADM1_EN")["Kiribati"]}

    def test_the_atlas_medians_come_out_of_the_groups(self):
        got = kc.check_national(self.nation())
        self.assertEqual(got, {"everyone": 22.7, "males": 21.8, "females": 24.0})

    def test_groups_that_miss_the_atlas_stop_the_run(self):
        males = list(NATION_M)
        males[4], males[5] = males[4] - 60, males[5] + 60       # the males' median moves to 22.8
        with self.assertRaises(SystemExit):
            kc.check_national(self.nation(males=males))

    def test_table_a10a_is_not_the_atlas(self):
        self.assertGreater(abs(kc.A10A_NATIONAL - kc.ATLAS_MEDIANS["everyone"]),
                           kc.MEDIAN_SLACK)


class TheRecords(unittest.TestCase):
    def setUp(self):
        counts = kc.read_profile(profile_book())
        self.cod = kc.read_cod(cod_book(butaritari=True))
        self.report = kc.read_report(counts)
        self.census = kc.build(counts, self.cod, self.report, kc.read_religion(volume_pages()),
                               load_units("KIR", "admin1"), load_units("KIR", "admin2"))

    def named(self, name):
        return next(r for r in self.census if r["name"] == name)

    def test_every_drawn_unit_has_a_record(self):
        self.assertEqual(sum(r["level"] == "admin1" for r in self.census), 3)
        self.assertEqual(sum(r["level"] == "admin2" for r in self.census), 23)

    def test_the_gilbert_polygon_counts_its_own_islands_and_makin(self):
        # The boundary file draws Tarawa and Banaba inside its "Phoenix
        # Islands" polygon, so the Gilbert polygon's figure is the group
        # without them.
        gilbert = self.named("Gilbert Islands except Tarawa and Banaba")
        tarawa_banaba = 7018 + 44643 + 18429 + 333
        self.assertEqual(gilbert["population"]["value"],
                         kc.NATIONAL - 1893 - 1990 - 7369 - 41 - tarawa_banaba)
        self.assertIn("Makin", gilbert["population_note"])
        self.assertIn("Phoenix Islands, not in this one", gilbert["population_note"])
        self.assertIn("The Gilbert group as a whole counted 108,145.",
                      gilbert["population_note"])

    def test_the_phoenix_polygon_is_tarawa_banaba_and_kanton(self):
        drawn = self.named("Tarawa, Banaba and the Phoenix Islands")
        self.assertEqual(drawn["population"]["value"], 7018 + 44643 + 18429 + 333 + 41)
        self.assertIn("also draws North and South Tarawa", drawn["population_note"])
        self.assertNotIn("as a whole", drawn["population_note"])
        self.assertEqual(drawn["sex_ratio"]["unit"], "males_per_100_females")
        self.assertIn("Pacific Community", drawn["median_age"]["source"])
        self.assertIn("I-Kiribati", {g["group"] for g in drawn["ethnicity"]})
        # Its figures are its islands' added up, the same as theirs.
        islands = [r for r in self.census if r["level"] == "admin2"
                   and r["name"] in ("Tarawa Ieta", "Tarawa Teinainano", "Betio", "Banaba",
                                     "Kanton")]
        self.assertEqual(sum(r["population"]["value"] for r in islands),
                         drawn["population"]["value"])

    def test_each_polygon_is_its_drawn_islands_and_the_country_is_whole(self):
        groups = [r for r in self.census if r["level"] == "admin1"]
        self.assertEqual(sorted(r["name"] for r in groups),
                         sorted(["Gilbert Islands except Tarawa and Banaba", "Line Islands", "Tarawa, Banaba and the Phoenix Islands"]))
        self.assertEqual(sum(r["population"]["value"] for r in groups), kc.NATIONAL)

    def test_the_map_drawing_the_islands_otherwise_stops_the_run(self):
        admin1, admin2 = load_units("KIR", "admin1"), load_units("KIR", "admin2")
        gilbert = next(u["id"] for u in admin1 if u["name"] == "Gilbert Islands")
        moved = [dict(u, parent=gilbert) if u["name"] == "Betio" else u for u in admin2]
        counts = kc.read_profile(profile_book())
        with self.assertRaises(SystemExit):
            kc.build(counts, self.cod, self.report, kc.read_religion(volume_pages()),
                     admin1, moved)

    def test_kanton_says_why_it_has_no_median(self):
        record = self.named("Kanton")
        self.assertEqual(record["median_age"]["status"], "not_available")
        self.assertIn("41", record["median_age"]["note"])
        self.assertIn("17.9", record["median_age"]["note"])
        self.assertNotIn("median_age", {s["field"] for s in record["sources"]})

    def test_butaritari_takes_spcs_median_not_the_printed_one(self):
        butaritari = self.named("Butaritari")
        self.assertEqual(butaritari["median_age"]["value"], 22.2)
        self.assertIn("Pacific Community", butaritari["median_age"]["source"])
        self.assertIn("16.8", butaritari["median_age_note"])
        self.assertIn("Table A-10a", butaritari["median_age_note"])
        self.assertIn("22.9", butaritari["median_age_note"])
        self.assertIn("median_age", {s["field"] for s in butaritari["sources"]})
        compared = kc.compare_medians(self.report, self.cod)
        self.assertEqual(compared["pairs"]["Butaritari"], (16.8, 22.2))
        self.assertGreaterEqual(compared["most"], 5.4)

    def test_every_island_and_group_with_ages_has_one_source_of_median(self):
        for record in self.census:
            if record["name"] == "Kanton":
                continue
            self.assertIn("Pacific Community", record["median_age"]["source"], record["name"])

    def test_betio_is_spcs_village_and_the_offices_sex_and_ethnicity(self):
        betio = self.named("Betio")
        self.assertIn("BetioEast", betio["median_age_note"])
        self.assertIn("20.8", betio["median_age_note"])
        self.assertEqual(betio["sex_ratio"]["value"], 95.0)
        self.assertEqual(betio["ethnicity"][0]["group"], "I-Kiribati")
        self.assertEqual(betio["language"]["status"], "not_available")
        gilbert = self.named("Gilbert Islands except Tarawa and Banaba")
        self.assertIn("by island group", gilbert["median_age_note"])
        self.assertIn("Makin", gilbert["ethnicity_note"])

    def test_banabas_printed_median_is_on_the_wrong_side_of_15(self):
        banaba = self.named("Banaba")
        self.assertIn("13.8", banaba["median_age_note"])
        self.assertIn("150 of the island's 333", banaba["median_age_note"])


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
        self.census = kc.build(counts, kc.read_cod(cod_book()), kc.read_report(counts),
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
        gilbert = self.named("Gilbert Islands except Tarawa and Banaba")
        people = sum(r["count"] for r in gilbert["religion"])
        tarawa_banaba = 6_629 + 39_058 + 17_330 + 268
        self.assertEqual(people,
                         kc.NATIONAL_2015 - 1_712 - 2_315 - 6_456 - 20 - tarawa_banaba)
        self.assertIn("Makin", gilbert["religion_note"])
        drawn = self.named("Tarawa, Banaba and the Phoenix Islands")
        self.assertEqual(sum(r["count"] for r in drawn["religion"]), tarawa_banaba + 20)
        # Kanton's 41 people are too few to carry a share or a ratio on their own.
        kanton = self.named("Kanton")
        for field in ("religion", "ethnicity", "sex_ratio"):
            self.assertEqual(kanton[field]["status"], "not_available", field)
            self.assertIn("41 people", kanton[field]["note"])
        self.assertNotIn("religion_note", kanton)


class TheReport(unittest.TestCase):
    def test_the_tables_add_up_and_agree_with_the_profile(self):
        report = kc.read_report(kc.read_profile(profile_book()))
        self.assertEqual(report["g2"]["Kiritimati"]["Male"], 3_837)
        self.assertEqual(report["a3"]["Kiritimati"]["Kiribati/Mix"], 662)
        self.assertEqual(report["wrong_side"], {"Banaba"})
        self.assertEqual(report["a10"]["Makin"]["Median"], 15.4)

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
