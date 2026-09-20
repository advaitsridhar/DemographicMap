"""The DPRK 2008 census report's Table 2, and the guards on reading it.

The fixture is the report's own geography -- the 208 rows it prints, in the
order it prints them, with the footnotes and the wrapped labels that make the
page hard to read -- carrying figures of this test's own. The figures are
invented; the names and the shape of the page are not, and it is the names
that the adapter has to turn into the 11 and 179 units the boundary file
draws.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402,F401
from fetch_census import northkorea as nk  # noqa: E402

# Table 2 as the report prints it: every city, district and county under the
# first-level area it stood in on 1 October 2008. The asterisked rows are the
# ones the report itself marks as parts of Chongjin and of Hamhung.
REPORT = {
    "Ryanggang": [
        "Hyesan City", "Samsu", "Kim Jong Suk", "Kim Hyong Jik",
        "Kim Hyong Gwon", "Pochon", "Samjiyon", "Taehongdan", "Unhung",
        "Paekam", "Kabsan", "Phungso"],
    "North Hamgyong": [
        "Rason City", "Kim Chaek City", "Hoeryong City", "Sinam Dist.*",
        "Chongam Dist.*", "Phohang Dist.*", "Sunam Dist.*",
        "Songphyong Dist.*", "Ranam Dist.*", "Puyun Dist.*", "Kilju",
        "Hwadae", "Myongchon", "Myonggan", "Orang", "Kyongsong", "Yonsa",
        "Musan", "Puryong", "Onsong", "Kyongwon", "Kyonghung"],
    "South Hamgyong": [
        "Sinpho City", "Tanchon City", "Songchongang Dist.*",
        "Tonghungsan Dist.*", "Hoesang Dist.*", "Sapho Dist.*",
        "Hungdok Dist.*", "Haean Dist.*", "Hungnam", "Hamju", "Yonggwang",
        "Sinhung", "Pujon", "Jangjin", "Jongphyong", "Kumya", "Yodok",
        "kowon", "Rakwon", "Hongwon", "Pukchong", "Toksong", "Riwon",
        "Hochon", "Sudong", "Kumho"],
    "Kangwon": [
        "Wonsan City", "Munchon City", "Anbyon", "Kosan", "Thongchon",
        "Kosong", "Kumgang", "Changdo", "Kimhwa", "Hoeyang", "Sepho",
        "Phyonggang", "Cholwon", "Ichon", "Phangyo", "Popdong", "Chonnae"],
    "Jagang": [
        "Kanggye City", "Manpho City", "Huichon City", "Rangrim", "Jonchon",
        "Songgan", "Janggang", "Hwaphyong", "Junggang", "Jasong", "Sijung",
        "Wiwon", "Chosan", "Usi", "Kophung", "Songwon", "Tongsin",
        "Ryongrim"],
    "North Phyongan": [
        "Sinuiju City", "Jongju City", "Kusong City", "Pyokdong", "Phihyon",
        "Ryongchon", "Yomju", "Cholwon", "Tongrim", "Sonchon", "Kwaksan",
        "Unjon", "Pakchon", "Nyongbyon", "Kujang", "Hyangsan", "Unsan",
        "Thaechon", "Chonma", "Uiju", "Sakju", "Taegwan", "Changsong",
        "Tongchang", "Sindo"],
    "South Phyongan": [
        "Phyongsong City", "Nampho City", "Anju City", "Kaechon City",
        "Sunchon City", "Tokchon City", "Taedong", "Jungsan", "Onchon",
        "Ryonggang", "Taean", "Kangso", "Chollima", "Phyongwon", "Sukchon",
        "Mundok", "Songchon", "Sinyang", "Yangdok", "Unsan", "Pukchang",
        "Maengsan", "Hoechang", "Nyongwon", "Taehung", "Chongnam",
        "Tukjang"],
    "North Hwanghae": [
        "Sariwon City", "Songrim City", "Kaesong City", "Jangphung",
        "Hwangju", "Yonthan", "Pongsan", "Unpha", "Rinsan", "Sohung", "Suan",
        "Yonsan", "Sinphyong", "Koksan", "Sinkye", "Phyongsan", "Kumchon",
        "Thosan"],
    "South Hwanghae": [
        "Haeju City", "Kangryong", "Ongjin", "Thaethan", "Jangyon",
        "Samchon", "Songhwa", "Unryul", "Unchon", "Anak", "Sinchon",
        "Jaeryong", "Sinwon", "Pongchon", "Paechon", "Yonan", "Chongdan",
        "Ryongchon", "Kwail", "Phyoksong"],
    "Pyongyang": [
        "Central Dist.", "Mangyongdae Dist.", "Sonkyo Dist.",
        "Phyongchon Dist.", "Tongdaewon Dist.", "Ryongsong Dist.",
        "Unjong Dist.", "Taesong Dist.", "Moranbong Dist.", "Sosong Dist.",
        "Pothonggang Dist.", "Taedonggang Dist.", "Sadong Dist.",
        "Hyongjesan Dist.", "Sunan Dist.", "Samsok Dist.", "Sungho Dist.",
        "Ryokpho Dist.", "Rakrang Dist.", "Kangnam", "Junghwa", "Sangwon",
        "Kangdong"],
}

FOOTNOTE = {"North Hamgyong": "*Part of Chongjin city",
            "South Hamgyong": " *part of Hamhung city"}

PAGE_HEAD = [
    "2008 Census of Population of DPR Korea",
    "18",
    "Table 2.  Population by Sex and by Urban-Rural,  by City/District/County "
    "and Province",
    "Province and",
    "City/District/",
    "County",
    "All Areas Urban Rural",
    "Both Sexes Male Female Both Sexes Male Female Both Sexes Male Female",
]


def quarters() -> dict[tuple[str, str], tuple[int, int, int, int]]:
    """Urban males, urban females, rural males, rural females per county.

    Every county gets a different set, so a row read onto the wrong shape
    changes a total; the last one carries whatever is left over, because the
    adapter refuses a table whose DPR Korea row is not the published
    23,349,859 and this fixture has to be that table.
    """
    keys = [(p, c) for p, names in REPORT.items() for c in names]
    out = {key: (1_000 + i, 1_100 + i, 500 + i, 600 + i)
           for i, key in enumerate(keys)}
    short = nk.CIVILIAN_TOTAL - sum(sum(v) for v in out.values())
    um, uf, rm, rf = out[keys[-1]]
    out[keys[-1]] = (um, uf, rm + short // 2, rf + short - short // 2)
    return out


QUARTERS = quarters()


def nine(um: int, uf: int, rm: int, rf: int) -> list[int]:
    return [um + uf + rm + rf, um + rm, uf + rf,
            um + uf, um, uf, rm + rf, rm, rf]


def spaced(value: int) -> str:
    """The report's thousands separator is a space, which is the whole
    difficulty: "192 680   91 420" is two numbers and nothing says so."""
    return f"{value:,}".replace(",", " ")


def printed(label: str, figures: list[int]) -> str:
    return f"  {label}   " + "   ".join(spaced(v) for v in figures)


def table(counts: dict[tuple[str, str], tuple[int, int, int, int]] | None = None,
          drop: tuple[str, str] | None = None,
          rename: tuple[str, str, str] | None = None) -> list[str]:
    """The five pages of Table 2 as one page's worth of lines."""
    counts = QUARTERS if counts is None else counts
    lines = list(PAGE_HEAD)
    national = [0] * 9
    body: list[str] = []
    for province, names in REPORT.items():
        rows = []
        for name in names:
            label = rename[2] if rename and rename[:2] == (province, name) else name
            rows.append((label, nine(*counts[(province, name)])))
        # The printed Total is the publisher's, so a row this reader loses
        # shows up against it rather than quietly shrinking the province.
        total = [sum(r[1][i] for r in rows) for i in range(9)]
        rows = [r for r in rows if drop != (province, r[0])]
        national = [national[i] + total[i] for i in range(9)]
        body.append(province)                     # the name, on its own line
        body.append(printed("Total", total))
        for label, figures in rows:
            if label.startswith("Songchongang"):  # the report wraps this one
                body.append("Songchongang")
                body.append(printed("Dist.*", figures))
            else:
                body.append(printed(label, figures))
        if province in FOOTNOTE:
            body.append(FOOTNOTE[province])
    lines.append(printed("DPR Korea", national))
    lines += body
    lines.append("Note:  Includes all individuals living in private "
                 "households and  institutional living quarters")
    return lines


def pages(lines: list[str]) -> list[str]:
    return ["", "\n".join(lines)]


def read(lines: list[str] | None = None) -> dict[str, dict[str, list[int]]]:
    text = pages(table() if lines is None else lines)
    return nk.counties(nk.rows(text, nk.table_pages(text)))


class ReadingARow(unittest.TestCase):
    def test_the_rows_own_arithmetic_picks_the_one_reading(self):
        # 23 349 859 is one number, not 23 / 349 / 859, and only the six
        # equations say so.
        figures = nine(1_000, 1_100, 500, 600)
        tokens = printed("Kabsan", figures).split()[1:]
        self.assertEqual(nk.split_row(tokens, "Kabsan"), figures)

    def test_a_dash_is_a_zero(self):
        # Every wholly urban district prints its rural columns as dashes.
        figures = nine(66_371, 64_962, 0, 0)
        row = "  Central Dist.   " + "   ".join(
            spaced(v) if v else "-" for v in figures)
        self.assertEqual(nk.split_row(row.split()[2:], "Central Dist."),
                         figures)

    def test_a_row_that_does_not_add_up_is_refused(self):
        figures = nine(1_000, 1_100, 500, 600)
        figures[1] += 7                       # males, and nothing else, moved
        tokens = printed("Kabsan", figures).split()[1:]
        with self.assertRaises(SystemExit) as caught:
            nk.split_row(tokens, "Kabsan")
        self.assertIn("arithmetic", str(caught.exception))


class ReadingTheTable(unittest.TestCase):
    def test_every_row_of_the_report_is_read(self):
        table_ = read()
        self.assertEqual(sorted(table_), sorted(REPORT))
        for province, names in REPORT.items():
            self.assertEqual(sorted(table_[province]), sorted(names))

    def test_a_footnote_is_not_read_as_the_next_provinces_name(self):
        # "*Part of Chongjin city" sits between Kyonghung and South Hamgyong;
        # left in the pending label it would swallow the province's name.
        self.assertIn("South Hamgyong", read())

    def test_a_wrapped_label_is_put_back_together(self):
        self.assertIn("Songchongang Dist.*", read()["South Hamgyong"])

    def test_a_county_missing_from_the_table_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            read(table(drop=("Kangwon", "Sepho")))
        self.assertIn("Kangwon", str(caught.exception))

    def test_a_dpr_korea_row_that_is_not_the_published_total_is_refused(self):
        counts = dict(QUARTERS)
        counts[("Jagang", "Usi")] = (1, 1, 1, 1)
        with self.assertRaises(SystemExit) as caught:
            read(table(counts=counts))
        self.assertIn("23,349,859", str(caught.exception))

    def test_a_first_level_area_this_reader_does_not_know_is_refused(self):
        lines = [line.replace("Kangwon", "Kangwon Province")
                 for line in table()]
        with self.assertRaises(SystemExit) as caught:
            read(lines)
        self.assertIn("Kangwon Province", str(caught.exception))

    def test_the_list_of_tables_is_not_mistaken_for_the_table(self):
        # The contents page prints Table 2's caption too, and the column
        # header over the figures is what tells the two apart.
        contents = ("Table 2.    Population by Sex and by Urban-Rural,  by "
                    "City/District/County and Province ......... 18\n"
                    "Table 3.    Number of  Localities and Population ... 23")
        self.assertEqual(nk.table_pages([contents, "\n".join(table())]), [2])

    def test_a_file_that_is_not_the_report_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            nk.table_pages(["some other census", "and its second page"])
        self.assertIn("not the National Report", str(caught.exception))


class TheWholePopulation(unittest.TestCase):
    """Table 1, which is where the military camps show up as a number."""

    PAGE = ("2008 Census of Population of DPR Korea\n14\n"
            "Table 1.  Total and Percent Distribution of Population by Sex "
            "and Sex-Ratio, by Single Year of Age\n"
            "Age\nPopulation Percent Sex\nRatio Both Sexes Male Female Both\n"
            "Sexes Male Female\n"
            "All Ages  24 052 231  11 721 838  12 330 393 100.0 100.0 100.0 "
            "95.1\n"
            "0-4    1 710 039  872 173  837 866 7.1 7.4 6.8 104.1")

    def test_the_all_ages_row_is_read_past_its_percentages(self):
        people, males = nk.whole_population(["", self.PAGE])
        self.assertEqual((people, males), (24_052_231, 11_721_838))
        self.assertEqual(people - nk.CIVILIAN_TOTAL, nk.IN_CAMPS)

    def test_a_row_whose_sexes_do_not_add_up_is_refused(self):
        page = self.PAGE.replace("11 721 838", "11 721 000")
        with self.assertRaises(SystemExit) as caught:
            nk.whole_population(["", page])
        self.assertIn("does not add up", str(caught.exception))

    def test_a_report_without_table_1_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            nk.whole_population(["", "\n".join(table())])
        self.assertIn("All Ages", str(caught.exception))


class Regrouping(unittest.TestCase):
    def setUp(self):
        self.shaped = nk.regroup(read())
        self.figures = {shape: {name: county.figures[0]
                                for name, county in rows.items()}
                        for shape, rows in self.shaped.items()}

    def test_eleven_shapes_and_a_hundred_and_seventy_nine_counties(self):
        self.assertEqual(len(self.shaped), 11)
        self.assertEqual(sum(len(v) for v in self.shaped.values()), 179)

    def test_nampo_is_its_six_counties_taken_out_of_south_phyongan(self):
        six = ["Nampho City", "Onchon", "Ryonggang", "Taean", "Kangso",
               "Chollima"]
        wanted = sum(sum(QUARTERS[("South Phyongan", c)]) for c in six)
        self.assertEqual(sum(self.figures["Nampo"].values()), wanted)
        self.assertNotIn("Nampo City", self.figures["South Pyongan"])
        self.assertEqual(len(self.figures["South Pyongan"]), 21)

    def test_the_three_counties_pyongyang_lost_are_in_north_hwanghae(self):
        for name in ("Kangnam", "Junghwa", "Sangwon"):
            self.assertIn(name, self.figures["North Hwanghae"])
            self.assertNotIn(name, self.figures["Pyongyang"])
            self.assertIn("boundary file draws it in North Hwanghae",
                          self.shaped["North Hwanghae"][name].note)

    def test_chongjin_is_the_seven_districts_the_report_marks_as_its_own(self):
        parts = nk.MERGED[("North Hamgyong", "Chongjin City")]
        wanted = sum(sum(QUARTERS[("North Hamgyong", p)]) for p in parts)
        self.assertEqual(self.figures["North Hamgyong"]["Chongjin City"],
                         wanted)

    def test_hamhung_is_its_six_districts_and_hungnam(self):
        parts = nk.MERGED[("South Hamgyong", "Hamhung City")]
        self.assertIn("Hungnam", parts)
        wanted = sum(sum(QUARTERS[("South Hamgyong", p)]) for p in parts)
        self.assertEqual(self.figures["South Hamgyong"]["Hamhung City"],
                         wanted)

    def test_pyongyang_the_shape_is_the_city_without_unjong_or_kangdong(self):
        city = self.figures["Pyongyang"]
        self.assertEqual(sorted(city),
                         ["Kangdong", "Pyongyang", "Unjong Dist."])
        self.assertEqual(city["Unjong Dist."],
                         sum(QUARTERS[("Pyongyang", "Unjong Dist.")]))

    def test_a_county_the_boundary_file_does_not_draw_is_refused(self):
        # The report renaming a county is the case this cannot paper over:
        # the row is read, and then it has nowhere to go.
        renamed = table(rename=("Kangwon", "Sepho", "Sepho County"))
        with self.assertRaises(SystemExit) as caught:
            nk.regroup(read(renamed))
        self.assertIn("Sepho County", str(caught.exception))


class TheRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = nk.build(nk.regroup(read()))
        cls.by_name = {r["name"]: r for r in cls.rows
                       if r["level"] == "admin1"}

    def test_the_counts_and_the_sums_close(self):
        nk.check(self.rows)                       # refuses if they do not

    def test_every_unit_reaches_a_shape_by_name_or_declared_alias(self):
        # Scoped by province, the way the join is: two provinces both draw an
        # Unsan, so the second level's names are unique only under a parent.
        root = Path(__file__).resolve().parent.parent / "site/data"
        if not (root / "admin2" / "PRK.json").exists():
            self.skipTest("site/data/admin2/PRK.json is not in this checkout")
        first = json.loads((root / "admin1" / "PRK.json").read_text())
        second = json.loads((root / "admin2" / "PRK.json").read_text())
        province = {row["id"]: row["name"] for row in first}
        drawn = {("admin1", None, row["name"]) for row in first}
        drawn |= {("admin2", province[row["parent"]], row["name"])
                  for row in second}
        self.assertEqual(len(first), 11)
        self.assertEqual(len(second), 179)
        self.assertEqual(len(drawn), 190)
        reached = set()
        for row in self.rows:
            keys = {(row["level"], row.get("parent_name"), name)
                    for name in (row["name"], *row.get("aliases", []))} & drawn
            self.assertEqual(len(keys), 1, row["name"])
            reached |= keys
        self.assertEqual(reached, drawn)

    def test_the_report_spelling_is_carried_as_an_alias(self):
        for shape, label in (("Cholsan", "Cholwon"),
                             ("Ryongyon", "Ryongchon"),
                             ("Pyongsong City", "Phyongsong City"),
                             ("Nampo City", "Nampho City")):
            row = next(r for r in self.rows if r["name"] == shape)
            self.assertEqual(row["aliases"], [label])
            self.assertIn(label, row["population_note"])

    def test_the_three_fields_yield_to_the_countrys_own_declaration(self):
        # Written as a noted not_available, which is the one form
        # apply_collection_policy replaces: a not_collected of this adapter's
        # own would stand, and go stale the next time the declaration is
        # sharpened.
        for field in ("religion", "ethnicity", "language"):
            self.assertEqual(common.collection_gap("PRK", field)["status"],
                             common.NOT_COLLECTED)
            for row in self.rows:
                self.assertEqual(row[field]["status"], common.NOT_AVAILABLE)
                self.assertIn("asks none of the three", row[field]["note"])
                replaced = dict(row)
                common.apply_collection_policy(replaced, "PRK")
                self.assertEqual(replaced[field],
                                 common.collection_gap("PRK", field))

    def test_a_country_with_no_declaration_is_refused(self):
        # This adapter writes no composition, so without the declaration its
        # 190 units would say only that nobody had fetched one.
        saved = common.NOT_COLLECTED_POLICY.pop("PRK")
        try:
            with self.assertRaises(SystemExit) as caught:
                nk.build(nk.regroup(read()))
            self.assertIn("missing declaration", str(caught.exception))
        finally:
            common.NOT_COLLECTED_POLICY["PRK"] = saved

    def test_every_row_says_what_its_figure_is_and_what_it_leaves_out(self):
        for row in self.rows:
            self.assertEqual(row["population"]["year"], 2008)
            self.assertIn("Table 2", row["population_note"])
            self.assertIn("military camps", row["population_note"])
            self.assertEqual(row["sex_ratio"]["unit"],
                             "females_per_1000_males")

    def test_a_province_says_how_its_boundary_differs_from_the_reports(self):
        self.assertIn("Nampo was not a first-level area in 2008",
                      self.by_name["Nampo"]["population_note"])
        self.assertIn("which are Nampo",
                      self.by_name["South Pyongan"]["population_note"])
        self.assertIn("plus Kangnam, Junghwa and Sangwon",
                      self.by_name["North Hwanghae"]["population_note"])

    def test_a_shape_that_does_not_equal_its_counties_is_refused(self):
        broken = [dict(r) for r in self.rows]
        row = next(r for r in broken if r["name"] == "Kabsan")
        row["population"] = dict(row["population"])
        row["population"]["value"] += 10
        with self.assertRaises(SystemExit) as caught:
            nk.check(broken)
        self.assertIn("Ryanggang", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
