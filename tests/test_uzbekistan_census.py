import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import uzbekistan_census as uz  # noqa: E402


def sp(n):
    return f"{n:,}".replace(",", " ")


# The compendium's labels, some wrapped over two lines the way the PDF sets them.
LABELS = {
    uz.REPUBLIC: "Республика\nУзбекистан",
    "республикакаракалпакстан": "Республика\nКаракалпакстан",
    "андижанскаяобласть": "Андижанская\nобласть", "бухарскаяобласть": "Бухарская область",
    "джизакскаяобласть": "Джизакская область",
    "кашкадарьинскаяобласть": "Кашкадарьинска\nя область",
    "навоийскаяобласть": "Навоийская\nобласть\n", "наманганскаяобласть": "Наманганская область",
    "самаркандскаяобласть": "Самаркандская область",
    "сурхандарьинскаяобласть": "Сурхандарьинская\nобласть",
    "сырдарьинскаяобласть": "Сырдарьинская область",
    "ташкентскаяобласть": "Ташкентская область", "ферганскаяобласть": "Ферганская область ",
    "хорезмскаяобласть": "Хорезмская область", "городташкент": "город Ташкент",
}
REGION_KEYS = list(uz.REGIONS)


def region_bands(k):
    """Region k's (men, women) in each of the 18 age groups."""
    return [(1000 + 37 * k + 11 * g, 990 + 29 * k + 7 * g) for g in range(18)]


def region_nations(k, men, women):
    """Region k's eight nationalities as (men, women), adding up to its sexes."""
    small = [(5 + k, 4 + k), (3, 2 + k), (7 * k, 6), (k, k + 1), (9, 9), (2, 3), (k + 4, 1)]
    first = (men - sum(m for m, _ in small), women - sum(w for _, w in small))
    return [first, *small]


def region_tongues(k, both):
    small = [10 + k, 3, 2 * k + 1, 4, 5 + k, 1, 6]
    return [both - sum(small), *small]


def data():
    out = {}
    for k, key in enumerate(REGION_KEYS):
        bands = region_bands(k)
        men, women = sum(m for m, _ in bands), sum(w for _, w in bands)
        out[key] = {"bands": bands, "sexes": (men + women, men, women),
                    "nations": region_nations(k, men, women),
                    "tongues": region_tongues(k, men + women)}
    rep = {"bands": [tuple(sum(out[r]["bands"][g][i] for r in REGION_KEYS) for i in range(2))
                     for g in range(18)],
           "sexes": tuple(sum(out[r]["sexes"][i] for r in REGION_KEYS) for i in range(3)),
           "nations": [tuple(sum(out[r]["nations"][n][i] for r in REGION_KEYS)
                             for i in range(2)) for n in range(8)],
           "tongues": [sum(out[r]["tongues"][n] for r in REGION_KEYS) for n in range(8)]}
    out[uz.REPUBLIC] = rep
    return out


def compendium(d, doubled=False):
    """The contents page and the five tables, page by page, as pypdf reads them."""
    areas = [uz.REPUBLIC, *REGION_KEYS]
    toc = ("Содержание\nРаспределение населения по регионам и полу .... 4\n"
           "Распределение населения по регионам, возрастным группам и полу 24\n"
           "Распределение населения по национальной принадлежности ... 43\n"
           "Распределение населения по регионам, национальной\nпринадлежности и полу ... 44\n"
           "Распределение населения по регионам и родному языку ... 52")
    sexes = ["4\nРаспределение населения по регионам и полу\nЧисленность\nнаселения\nвсего,\n"
             "человек\nиз них:\nмужчины женщины мужчины женщины"]
    for a in areas:
        both, men, women = d[a]["sexes"]
        if a == "республикакаракалпакстан":
            sexes.append("по областям:")
        sexes.append(f"{LABELS[a]} {sp(both)} {sp(men)} {sp(women)} 50,6 49,4")
    pages = [toc, "\n".join(sexes) + "\nРаспределение населения по регионам, городской и "
             "сельской\nместности\nРеспублика Узбекистан 1 2 3"]
    for i, a in enumerate(areas):
        both, men, women = d[a]["sexes"]
        lines = [str(24 + i)]
        if i == 0:
            lines.append("ВОЗРАСТНОЙ СОСТАВ\nРаспределение населения по регионам, возрастным\n"
                         "группам и полу")
        lines += ["Численность\nнаселения –\nвсего,\nчеловек",
                  f"{LABELS[a]} {sp(both)} {sp(men)} {sp(women)} 50,6 49,4",
                  "в том числе в\nвозрасте, лет"]
        for g, (m, w) in enumerate(d[a]["bands"]):
            label = f"{5 * g}-{5 * g + 4}" if g < 17 else "85 лет и старше"
            tail = " 51,2 48,8" if g < 17 else "\n\n\n48,6 51,4"
            lines.append(f"{label} {sp(m + w)} {sp(m)} {sp(w)}{tail}")
        pages.append("\n".join(lines))
    pages.append("39\nРаспределение населения по регионам и основным\n возрастным группам\n"
                 "Республика\nУзбекистан 9 4 3 2")
    nations = ["43\nНАЦИОНАЛЬНЫЙ СОСТАВ НАСЕЛЕНИЯ\nРаспределение населения по национальной "
               "принадлежности\nЧисленность\nнаселения –\nвсего, человек\nиз них по "
               "национальной принадлежности:\nузбеки каракалпаки казахи таджики киргизы "
               "русские туркмены другие"]
    for a in areas:
        nat = [m + w for m, w in d[a]["nations"]]
        label = " ".join(LABELS[a].split())
        nations.append(f"{label} {sp(d[a]['sexes'][0])} " + " ".join(sp(v) for v in nat))
    pages.append("\n".join(nations))
    names = list(uz.NATIONALITIES)
    for i, a in enumerate(areas):
        both, men, women = d[a]["sexes"]
        lines = [str(44 + i)]
        if i == 0:
            lines.append("Распределение населения по регионам, национальной\n"
                         "принадлежности и полу")
        lines += [f"{LABELS[a]} {sp(both)} {sp(men)} {sp(women)} 50,4 49,6",
                  "из них по\nнациональной\nпринадлежности:\n"]
        for name, (m, w) in zip(names, d[a]["nations"]):
            lines.append(f"{name} {sp(m + w)} {sp(m)} {sp(w)} 50,1 49,9")
        if doubled and i == 2:
            lines = [x for line in lines for x in (line, line)]
        pages.append("\n".join(lines))
    tongues = ["52\nНАСЕЛЕНИЕ ПО ЛИНГВИСТИЧЕСКИМ ХАРАКТЕРИСТИКАМ\nРаспределение населения по "
               "регионам и родному языку\nЧисленность\nнаселения –\nвсего, человек\nиз них "
               "считают родным языком:\nузбекский каракалпакский  казахский таджикский "
               "киргизский русский туркменский другой\n"]
    for a in areas:
        tongues.append(f"{LABELS[a]} {sp(d[a]['sexes'][0])} "
                       + " ".join(sp(v) for v in d[a]["tongues"]))
    pages.append("\n".join(tongues) + "\nЖИЛИЩНЫЕ УСЛОВИЯ\nРеспублика Узбекистан 1 2 3")
    return pages


def read(pages, d):
    with mock.patch.object(uz, "NATIONAL", d[uz.REPUBLIC]["sexes"][0]):
        return uz.read_tables(pages)


class Rows(unittest.TestCase):
    def test_counts_stop_at_the_shares(self):
        self.assertEqual(uz.split_row("0-4 207 304 107 144 100 160 51,7 48,3"),
                         ("0-4", ["207", "304", "107", "144", "100", "160"]))

    def test_a_figure_inside_a_label_stays_in_it(self):
        self.assertEqual(uz.split_row("85 лет и старше 168 973 82 168 86 805"),
                         ("85 лет и старше", ["168", "973", "82", "168", "86", "805"]))

    def test_a_wrapped_label_joins_its_figures(self):
        found = uz.rows("Кашкадарьинска\nя область 3 692 323 1 888 415 1 803 908 51,1 48,9")
        self.assertEqual(uz.area_of(found[0][0]), "кашкадарьинскаяобласть")
        self.assertEqual(uz.triple(found[0][1], "x"), (3692323, 1888415, 1803908))

    def test_a_heading_before_a_region_does_not_hide_it(self):
        self.assertEqual(uz.area_of("по областям: Андижанская область"), "андижанскаяобласть")
        self.assertIsNone(uz.area_of("область"))

    def test_page_numbers_and_breaks_are_not_rows(self):
        found = uz.rows(f"Навоийская\n{uz.PAGE_BREAK}\n45\nобласть 1 2 3")
        self.assertEqual(found, [("область", ["1", "2", "3"])])

    def test_a_row_of_nine_is_read_by_its_sum(self):
        tokens = "2 149 932 1 042 173 844 002 167 203 381 664 11 209 82 655 1 645".split()
        found = uz.figures(tokens, 9, lambda v: v[0] == sum(v[1:]))
        self.assertEqual(found, [[2149932, 1042173, 844002, 167203, 381, 664, 11209, 82655,
                                  1645]])


class Tables(unittest.TestCase):
    def test_every_table_read_and_checked(self):
        d = data()
        areas = read(compendium(d), d)
        self.assertEqual(len(areas), 15)
        k = REGION_KEYS.index("ферганскаяобласть")
        self.assertEqual(areas["ферганскаяобласть"]["sexes"], d["ферганскаяобласть"]["sexes"])
        self.assertEqual(areas["ферганскаяобласть"]["nationality"]["Tajik"],
                         sum(region_nations(k, 0, 0)[3]))
        self.assertEqual(areas["ферганскаяобласть"]["language"]["Other languages"], 6)

    def test_a_page_printed_twice_is_read_once(self):
        d = data()
        areas = read(compendium(d, doubled=True), d)
        self.assertEqual(areas["андижанскаяобласть"]["sexes"], d["андижанскаяобласть"]["sexes"])

    def test_a_nationality_that_disagrees_between_tables_stops_the_run(self):
        d = data()
        pages = compendium(d)
        k = REGION_KEYS.index("бухарскаяобласть")
        m, w = d["бухарскаяобласть"]["nations"][5]
        pages = [p.replace(f"русские {sp(m + w)} {sp(m)} {sp(w)}",
                           f"русские {sp(m + w + 1)} {sp(m + 1)} {sp(w)}")
                 if "Бухарская область" in p and "русские" in p else p for p in pages]
        with self.assertRaises(SystemExit):
            read(pages, d)
        self.assertGreater(k, 0)

    def test_age_groups_that_do_not_make_the_region_stop_the_run(self):
        d = data()
        pages = compendium(d)
        m, w = d["навоийскаяобласть"]["bands"][3]
        i = next(i for i, p in enumerate(pages) if "Навоийская\nобласть\n" in p and "15-19" in p)
        pages[i] = pages[i].replace(f"15-19 {sp(m + w)} {sp(m)} {sp(w)}",
                                    f"15-19 {sp(m + w + 2)} {sp(m + 1)} {sp(w + 1)}")
        with self.assertRaises(SystemExit):
            read(pages, d)


A1 = [{"id": f"S{i}", "name": f"Unit {code}", "iso_3166_2": code}
      for i, code in enumerate(uz.REGIONS.values())]


class Records(unittest.TestCase):
    def test_every_region_bound_by_its_code(self):
        d = data()
        areas = read(compendium(d), d)
        out = {r["shape_id"]: r for r in uz.build(areas, A1)}
        self.assertEqual(len(out), 14)
        tashkent = out[A1[list(uz.REGIONS.values()).index("UZ-TK")]["id"]]
        both, men, women = d["городташкент"]["sexes"]
        self.assertEqual(tashkent["population"]["value"], both)
        self.assertEqual(tashkent["population"]["year"], 2026)
        self.assertEqual(tashkent["sex_ratio"]["value"], round(100 * men / women, 1))
        self.assertEqual(round(sum(g["pct"] for g in tashkent["ethnicity"])), 100)
        self.assertEqual(tashkent["religion"]["status"], "not_available")
        self.assertIn("preliminary", tashkent["ethnicity_note"])
        self.assertTrue(all(r["match_by"] == "shape_id" for r in out.values()))

    def test_a_region_the_map_does_not_draw_stops_the_run(self):
        d = data()
        areas = read(compendium(d), d)
        with self.assertRaises(SystemExit):
            uz.build(areas, A1[1:])

    def test_the_median_comes_from_the_five_year_groups(self):
        bands = [(10, 10)] * 18
        areas = {a: {"sexes": (360, 180, 180), "bands": [(20, 10, 10)] * 18,
                     "nationality": {"Uzbek": 360}, "language": {"Uzbek": 360}}
                 for a in uz.REGIONS}
        out = uz.build(areas, A1)
        self.assertEqual(out[0]["median_age"]["value"], 45.0)
        self.assertEqual(len(bands), len(uz.GROUPS))


# The map's own labels, which the agency's region names are tied to.
LABELS_EN = {"UZ-QR": "Republic of Karakalpakstan", "UZ-AN": "Andijan Region",
             "UZ-BU": "Bukhara Region", "UZ-JI": "Jizzakh Region", "UZ-QA": "Qashqadaryo Region",
             "UZ-NW": "Navoiy Region", "UZ-NG": "Namangan Region", "UZ-SA": "Samarqand Region",
             "UZ-SU": "Surxondaryo Region", "UZ-SI": "Sirdaryo Region",
             "UZ-TO": "Tashkent Region", "UZ-FA": "Fergana Region", "UZ-XO": "Xorazm Region",
             "UZ-TK": "Tashkent"}
NAMED = [dict(u, name=LABELS_EN[u["iso_3166_2"]]) for u in A1]
REGION_ID = next(u["id"] for u in A1 if u["iso_3166_2"] == "UZ-TO")
A2 = [{"id": f"D{i}", "name": name, "parent": REGION_ID}
      for i, name in enumerate(("Bektemir", "Sergeli", "Uchtepa", "Zangiata"))]


def agency(off=None):
    """The agency's table: each region at its census count (scaled by ``off``
    where given), and the city's four districts drawn in the region."""
    d = data()
    by_label = {LABELS_EN[code]: d[area]["sexes"][0] for area, code in uz.REGIONS.items()}
    rows = [{"Code": f"17{i:02d}", "Klassifikator_en": en,
             "2025": 1.0, "2026": by_label[label] * (off or {}).get(label, 1.0) / 1000}
            for i, (en, label) in enumerate(uz.SIAT_REGION.items())]
    rows += [{"Code": code, "Klassifikator_en": f"District {code}", "2025": 1.0, "2026": n}
             for code, n in (("1726262", 304.4), ("1726264", 71.3), ("1726283", 178.7),
                             ("1726292", 200.5))]
    return rows


class AgencyNotes(unittest.TestCase):
    def test_tashkent_and_its_region_say_where_the_city_districts_are(self):
        d = data()
        areas = read(compendium(d), d)
        out = {r["aliases"][0]: r for r in uz.build(areas, NAMED, A2, agency())}
        self.assertIn("Bektemir, Sergeli and Uchtepa (754,900 people",
                      out["UZ-TK"]["population_note"])
        self.assertIn("their people are in this figure", out["UZ-TK"]["population_note"])
        self.assertIn("in the city's figure, not this one", out["UZ-TO"]["population_note"])
        # Every region within AGENCY_GAP of the agency: no comparison is written.
        self.assertFalse(any("estimate" in r["population_note"] for r in out.values()))
        self.assertTrue(out["UZ-AN"]["population_note"].endswith(uz.PRELIMINARY))

    def test_a_region_far_from_the_agency_says_how_far(self):
        d = data()
        areas = read(compendium(d), d)
        table = agency({"Tashkent Region": 1 / 1.25, "Andijan Region": 1.05})
        out = {r["aliases"][0]: r for r in uz.build(areas, NAMED, A2, table)}
        note = out["UZ-TO"]["population_note"]
        self.assertIn("The census counts 25.0% more people here than the statistics agency's "
                      "estimate for 1 January 2026", note)
        self.assertRegex(note, r"between -4[.]8% and [-+]0[.]0% from the agency.s figure")
        self.assertNotIn("estimate", out["UZ-AN"]["population_note"])

    def test_a_city_district_no_longer_drawn_in_the_region_stops_the_run(self):
        d = data()
        areas = read(compendium(d), d)
        with self.assertRaises(SystemExit):
            uz.build(areas, NAMED, [u for u in A2 if u["name"] != "Uchtepa"], agency())

    def test_a_district_the_agency_files_elsewhere_stops_the_run(self):
        d = data()
        areas = read(compendium(d), d)
        table = [r for r in agency() if r["Code"] != "1726292"]
        with self.assertRaises(SystemExit):
            uz.build(areas, NAMED, A2, table)


class Main(unittest.TestCase):
    def test_main_writes_the_regions(self):
        d = data()
        written = {}
        with mock.patch.object(uz, "http_get", return_value=b"pdf"), \
                mock.patch.object(uz, "pdf_pages", return_value=compendium(d)), \
                mock.patch.object(uz, "drawn_admin1", return_value=NAMED), \
                mock.patch.object(uz, "drawn_admin2", return_value=A2), \
                mock.patch.object(uz, "agency_table", return_value=agency()), \
                mock.patch.object(uz, "NATIONAL", d[uz.REPUBLIC]["sexes"][0]), \
                mock.patch.object(uz, "write_json",
                                  side_effect=lambda p, rows: written.update(rows=rows)), \
                mock.patch.object(sys, "argv", ["uzbekistan_census"]):
            self.assertEqual(uz.main(), 0)
        self.assertEqual(len(written["rows"]), 14)
        self.assertTrue(any("Bektemir" in r["population_note"] for r in written["rows"]))


if __name__ == "__main__":
    unittest.main()
