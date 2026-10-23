"""Angola's 2024 census on the 2016 municipalities, from pages laid out as the
provincial reports are (no network): words with their boxes, figures
right-aligned in columns, thousands spaced, zeros printed a little low."""

import unittest

from scripts.fetch_census import angola_municipios as am

LEFT = 90.0


def figure_words(value, right, top):
    """'145 798' right-aligned at ``right``: one word per digit group."""
    groups = f"{value:,}".split(",")
    words, x1 = [], right
    for g in reversed(groups):
        width = 4.0 * len(g)
        words.append((top, x1 - width, x1, g))
        x1 = x1 - width - 2.0
    return words


def line(top, label, values, rights, low_zeros=False):
    words, x = [], LEFT
    for part in label.split():
        words.append((top, x, x + 5.0 * len(part), part))
        x += 5.0 * len(part) + 3
    for v, r in zip(values, rights):
        words += figure_words(v, r, top + (4.0 if low_zeros and v == 0 else 0.0))
    return words


def header(top, texts_at):
    out = []
    for text, x0 in texts_at:
        for part in text.split():
            out.append((top, x0, x0 + 5.0 * len(part), part))
            x0 += 5.0 * len(part) + 3
    return out


class Page:
    def __init__(self):
        self.words, self.top = [], 40.0

    def title(self, text):
        self.words += header(self.top, [(text, LEFT)])
        self.top += 14

    def head(self, texts_at):
        self.words += header(self.top, texts_at)
        self.top += 12

    def row(self, label, values, rights, low_zeros=False):
        self.words += line(self.top, label, values, rights, low_zeros)
        self.top += 12

    def text(self):
        return am.squeeze(" ".join(w[3] for w in sorted(self.words)))


NEW = [("Dande", 145_798, 71_857, 73_941), ("Panguila", 158_068, 77_738, 80_330),
       ("Barra do Dande", 72_754, 35_801, 36_953), ("Úcua", 41_654, 20_958, 20_697),
       ("Quibaxe", 44_435, 22_311, 22_123), ("Piri", 26_265, 13_286, 12_979)]
OLD = [("Dande", 418_274, 206_354, 211_921), ("Dembos", 70_700, 35_598, 35_102)]
COMMUNES = {"Dande": ["Caxito", "Mabubas"], "Quibaxe": ["Quibaxe", "Coxe"]}


def split(values, share=0.7):
    a = [round(v * share) for v in values]
    return a, [v - x for v, x in zip(values, a)]


def composition_pages(title, labels1, labels2, make):
    """A two-group table by municipality and commune; ``make(name)`` gives the
    row's (total, groups1, groups2)."""
    pages = []
    for labels, pick in ((labels1, 1), (labels2, 2)):
        page = Page()
        page.title(title)
        rights = [240.0 + 70 * k for k in range(len(labels) + 1)]
        page.head([("Município e área de residência", LEFT), ("População com 2 ou mais anos", 180)]
                  + [(lab, rights[k + 1] - 40) for k, lab in enumerate(labels)])
        province = [0] * (len(labels) + 1)
        rows = []
        for name, *_ in NEW:
            total, g1, g2 = make(name)
            rows.append((name, [total] + (g1 if pick == 1 else g2)))
        for _, vals in rows:
            province = [p + v for p, v in zip(province, vals)]
        page.row("Bengo", province, rights)
        page.row("Urbana", [p // 2 for p in province], rights)
        page.row("Rural", [p - p // 2 for p in province], rights)
        page.head([("Municípios / Comunas", LEFT)])
        for name, vals in rows:
            page.row(name, vals, rights)
            if name in COMMUNES:
                a, b = split(vals)
                page.row(COMMUNES[name][0], a, rights, low_zeros=True)
                page.row(COMMUNES[name][1], b, rights, low_zeros=True)
            else:
                page.row(name, vals, rights)
        pages.append(page)
    return pages


def ethnic(name):
    total = {"Dande": 138_560, "Panguila": 150_602, "Barra do Dande": 68_885, "Úcua": 39_460,
             "Quibaxe": 42_451, "Piri": 24_995}[name]
    kongo = total // 5
    mbundu = total // 2
    unknown = total // 10
    other = 0
    rest = total - kongo - mbundu - unknown - other
    return total, [kongo, mbundu + rest], [unknown, other]


def religion_page():
    page = Page()
    page.title("Quadro 7.1 - População com 2 ou mais anos por área de residência e município, "
               "segundo a religião ou espiritualidade, 2024")
    rights = [240.0, 310.0, 380.0]
    page.head([("População com 2 ou mais anos", 180), ("Católica", 270), ("Protestante", 335)])
    rows = []
    for name, *_ in NEW:
        total = ethnic(name)[0]
        rows.append((name, [total, total * 3 // 5, total - total * 3 // 5]))
    page.row("Bengo", [sum(r[1][k] for r in rows) for k in range(3)], rights)
    page.head([("Municípios/Comunas", LEFT)])
    for name, vals in rows:
        page.row(name, vals, rights)
    return page


def language_pages():
    def make(name):
        total = ethnic(name)[0]
        pt = total // 2
        return total, [pt, total - pt - 10], [10]
    return composition_pages("Quadro 6.2 - População por província e área de residência, "
                             "segundo a língua Materna", ["Português", "Kimbundu"], ["Não sabe"],
                             make)


def age_pages():
    pages = []
    broad, other = Page(), Page()
    broad.title("Quadro 1.4 - População por município, segundo grandes grupos etários, 2024")
    other.title("Quadro 1.5 - População por província, segundo outros grupos etários, 2024")
    rb = [240.0, 300.0, 360.0, 420.0]
    ro = [240.0 + 60 * k for k in range(7)]
    broad.head([("Município e área de residência", LEFT), ("Total", 220), ("0 - 14 anos", 270),
                ("15-64 anos", 330), ("65 ou mais anos", 390)])
    other.head([("Município e área de 75 ou mais", LEFT)])
    other.head([("Total", 220), ("0-19 anos", 270), ("20-29 anos", 330), ("30-54 anos", 390),
                ("55-64 anos", 450), ("65-74 anos", 510), ("75 ou mais anos", 570)])

    def groups(total):
        g = [round(total * s) for s in (0.36, 0.11, 0.17, 0.25, 0.05, 0.03)]
        g.append(total - sum(g))
        return g  # 0-14, 15-19, 20-29, 30-54, 55-64, 65-74, 75+

    rows = []
    for name, total, *_ in NEW:
        g = groups(total)
        rows.append((name, [total, g[0], g[1] + g[2] + g[3] + g[4], g[5] + g[6]],
                     [total, g[0] + g[1], g[2], g[3], g[4], g[5], g[6]]))
    for page, k, rights in ((broad, 1, rb), (other, 2, ro)):
        page.row("Bengo", [sum(r[k][j] for r in rows) for j in range(len(rights))], rights)
        page.head([("Município / comuna", LEFT)])
        for r in rows:
            page.row(r[0], r[k], rights)
            names = COMMUNES.get(r[0], [r[0]])
            if len(names) == 2:
                a, b = split(r[k])
                page.row(names[0], a, rights)
                page.row(names[1], b, rights)
            else:
                page.row(names[0], r[k], rights)
        pages.append(page)
    return pages


def sex_pages():
    new, old, five = Page(), Page(), Page()
    new.title("Quadro 10 - População residente por município, segundo o sexo, Censo 2024")
    new.head([("Total Homens Mulheres", 250)])
    r3 = [260.0, 320.0, 380.0]
    new.row("Bengo", [sum(n[k] for n in NEW) for k in (1, 2, 3)], r3)
    for n in NEW:
        new.row(n[0], list(n[1:]), r3)
    old.title("Quadro 11 - População residente por município, segundo o sexo, Censos 2014 e 2024")
    old.head([("Censo 2014", 250), ("Censo 2024", 430)])
    r6 = [260.0, 320.0, 380.0, 440.0, 500.0, 560.0]
    old.row("Bengo", [252_586, 125_695, 126_890, 488_974, 241_952, 247_023], r6)
    old.row("Dande", [222_528, 111_188, 111_340, *OLD[0][1:]], r6)
    old.row("Dembos", [30_058, 14_507, 15_550, *OLD[1][1:]], r6)
    five.title("Quadro 1.3 - População por grupos etários quinquenais, 2024")
    five.row("Bengo", [488_974, 241_951, 247_023], r3)
    total = 488_974
    sizes = [70_000, 65_000, 62_000, 55_000, 48_000, 40_000, 33_000, 27_000, 21_000, 18_000,
             14_000, 11_000, 8_000, 6_000, 4_000, 3_000, 2_000, 1_000, 500]
    sizes.append(total - sum(sizes))
    for k, n in enumerate(sizes):
        label = f"{5 * k}-{5 * k + 4} anos" if k < 19 else "95 ou mais anos"
        five.row(label, [n, n // 2, n - n // 2], r3)
    return [new, old, five]


def decimal_words(top, label, left, values, rights):
    """A row of Quadro 1.7: its label, then 'média' and 'mediana' as '22,1'."""
    words, x = [], left
    for part in label.split():
        words.append((top, x, x + 5.0 * len(part), part))
        x += 5.0 * len(part) + 3
    for v, r in zip(values, rights):
        text = f"{v:.1f}".replace(".", ",")
        words.append((top, r - 4.0 * len(text), r, text))
    return words


# Quadro 1.7's rows for Bengo: (label, média, mediana); None for a heading.
MEDIANS = [("Bengo", 22.1, 20.0), ("Área de residência", None, None), ("Urbana", 21.0, 19.0),
           ("Rural", 23.0, 21.0), ("Sexo", None, None), ("Homens", 22.0, 19.0),
           ("Mulheres", 22.2, 20.0), ("Municípios / Comunas", None, None),
           ("Dande", 21.5, 18.0), ("Caxito", 21.0, 18.0), ("Mabubas", 23.0, 19.0),
           ("Panguila", 20.0, 17.0), ("Panguila", 20.0, 17.0),
           ("Barra do Dande", 23.4, 21.0), ("Barra do Dande", 23.4, 21.0),
           ("Úcua", 22.0, 19.0), ("Úcua", 22.0, 19.0),
           ("Quibaxe", 24.0, 21.0), ("Quibaxe", 24.2, 21.0), ("Coxe", 23.0, 20.0),
           ("Piri", 24.5, 22.0), ("Piri", 24.5, 22.0)]


def median_page(entries=MEDIANS):
    page = Page()
    page.title("Quadro 1.7 - Idade média e mediana da população por área de residência e "
               "sexo, 2024")
    page.head([("Média", 240), ("Mediana", 290)])
    for label, mean, median in entries:
        if mean is None:
            page.head([(label, LEFT)])
        else:
            page.words += decimal_words(page.top, label, LEFT, (mean, median), (260.0, 320.0))
            page.top += 12
    return page


def report_pages():
    pages = sex_pages()
    pages += composition_pages("Quadro 6.1 - População de 2 ou mais anos, segundo grupos "
                               "étnicos ou tribos, 2024", ["Quicongo", "Quimbundo"],
                               ["Não sabe", "Outra Etnia"], ethnic)
    pages += language_pages()
    pages.append(religion_page())
    pages += age_pages()
    pages.append(median_page())
    return [am.rows_of(p.words) for p in pages], [p.text() for p in pages]


ADMIN1 = [{"id": "B", "name": "Bengo"}, {"id": "N", "name": "Cuanza Norte"}]
ADMIN2 = [{"id": "p-dande", "name": "Dande", "parent": "B"},
          {"id": "p-dembos", "name": "Dembos-Quibaxe", "parent": "B"}]


class Reading(unittest.TestCase):
    def test_zeros_printed_low_join_their_row(self):
        page = Page()
        page.row("Quicabo", [10_432, 0, 0], [240.0, 300.0, 360.0], low_zeros=True)
        rows = am.rows_of(page.words)
        self.assertEqual(len(rows), 1)
        self.assertEqual([v for *_, v in rows[0].figures()], [10_432, 0, 0])

    def test_report(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        self.assertEqual(rep.problems, [])
        self.assertEqual(rep.total, (488_974, 241_951, 247_023))
        self.assertEqual(len(rep.new), 6)
        self.assertEqual(rep.old[1], ("Dembos", 70_700, 35_598, 35_102))
        self.assertEqual(len(rep.five_year), 20)
        # Quadro 1.7: the province's median and each 2024 municipality's, not
        # its first commune's (Dande's Caxito).
        self.assertEqual(rep.median, 20.0)
        self.assertEqual(rep.medians, {"dande": 18.0, "panguila": 17.0, "barradodande": 21.0,
                                       "ucua": 19.0, "quibaxe": 21.0, "piri": 22.0})
        self.assertEqual({k: rep.quadros[k] for k in ("new", "old", "five_year", "medians",
                                                      "ethnicity", "religion")},
                         {"new": "10", "old": "11", "five_year": "1.3", "medians": "1.7",
                          "ethnicity": "6.1", "religion": "7.1"})
        eth = am.municipalities(rep, "ethnicity", rep.tables["ethnicity"])
        self.assertEqual(eth["dande"]["TOTAL"], 138_560)
        self.assertEqual(set(eth["piri"]), {"TOTAL", "Bakongo", "Ambundu", "Not stated", "Other"})
        rel = am.municipalities(rep, "religion", rep.tables["religion"])
        self.assertEqual(len(rel), 6)
        self.assertEqual(rep.problems, [])

    def test_crosswalk(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        walk = am.crosswalk(rep)
        self.assertEqual(walk["panguila"], "dande")
        self.assertEqual(walk["piri"], "dembos")
        self.assertEqual(walk["quibaxe"], "dembos")

    def test_ambiguous_crosswalk_is_refused(self):
        rep = am.Report("X")
        rep.new = [("A", 40_000, 20_000, 20_000), ("B", 30_000, 15_000, 15_000),
                   ("C", 20_000, 10_000, 10_000), ("D", 10_000, 5_000, 5_000)]
        rep.old = [("A", 70_000, 35_000, 35_000), ("E", 30_000, 15_000, 15_000)]
        self.assertIsNone(am.crosswalk(rep))
        self.assertTrue(any("2 assignments" in p for p in rep.problems))


class Building(unittest.TestCase):
    def test_records(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        records, lines = am.build([rep], ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        bengo = by[("admin1", "Bengo")]
        self.assertEqual(bengo["population"]["value"], 488_974)
        self.assertEqual(bengo["sex_ratio"]["value"], round(1000 * 241_951 / 247_023))
        self.assertIsNotNone(bengo["median_age"]["value"])
        dembos = by[("admin2", "Dembos-Quibaxe")]
        self.assertEqual(dembos["population"]["value"], 70_700)
        self.assertIn("Quibaxe and Piri", dembos["ethnicity_note"])
        groups = {g["group"]: g for g in dembos["ethnicity"]}
        self.assertEqual(groups["Bakongo"]["count"], 42_451 // 5 + 24_995 // 5)
        self.assertEqual({g["group"] for g in dembos["religion"]}, {"Catholic", "Protestant"})
        # Its age groups put the middle person at 21.8 years: 21 in completed
        # years, between Quibaxe's 21 and Piri's 22.
        self.assertEqual(dembos["median_age"]["value"], 21.0)
        dande = by[("admin2", "Dande")]
        self.assertEqual(dande["population"]["value"], 418_274)
        self.assertIn("Lei n.º 18/16", dande["language_note"])

    def test_medians_published_and_worked_out(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        bengo = by[("admin1", "Bengo")]
        self.assertEqual(bengo["median_age"]["value"], 20.0)
        self.assertEqual(bengo["median_age_note"],
                         "The median age the 2024 census publishes for the province.")
        # Dembos is two municipalities of 2024: no median of its own is published.
        dembos = by[("admin2", "Dembos-Quibaxe")]
        self.assertIn("(Quibaxe 21 and Piri 22 years), not for Dembos", dembos["median_age_note"])
        self.assertIn("in completed years, as the census gives its medians",
                      dembos["median_age_note"])
        self.assertIn("taken from their counts by age group", dembos["median_age_note"])

    def test_one_municipality_shows_its_published_median(self):
        rep = am.Report("Zaire")
        rep.medians = {"tomboco": 16.0}
        fields, given, quadros, lines = {}, [], [], []
        am.median_fields(rep, [{"name": "Tomboco"}], ["Tomboco"], ["tomboco"], [{}],
                         ["Tomboco"], "it stood", "", "", set(), {}, {}, fields, given,
                         quadros, lines, "Tomboco")
        self.assertEqual(fields["median_age"]["value"], 16.0)
        self.assertEqual(fields["median_age_note"],
                         "The median age the 2024 census publishes for Tomboco.")
        self.assertEqual((given, quadros), (["median_age"], ["medians"]))

    def test_each_record_cites_what_it_gives(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        rep.url = "https://censo2024.ine.gov.ao/Relatorio_Provincial_Bengo_Censo2024.pdf"
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        (province,) = by[("admin1", "Bengo")]["sources"]
        self.assertEqual(province["field"], "population/sex_ratio/median_age")
        self.assertTrue(province["name"].endswith("Bengo province report: Quadros 10 and 1.7"))
        self.assertEqual(province["url"], rep.url)
        (dembos,) = by[("admin2", "Dembos-Quibaxe")]["sources"]
        self.assertEqual(dembos["field"],
                         "population/sex_ratio/median_age/ethnicity/language/religion")
        self.assertIn("Quadros 11, 6.1, 6.2, 7.1, 1.7, 1.4 and 1.5", dembos["name"])

    def test_not_described_polygons_say_why(self):
        admin2 = ADMIN2 + [{"id": "91424787B4488869677577", "name": "Pango-Aluquem",
                            "parent": "N"}]
        records, _ = am.build([], ADMIN1, admin2)
        pango = next(r for r in records if r["name"] == "Pango-Aluquem")
        self.assertIn("39%", pango["ethnicity"]["note"])
        self.assertNotIn("value", pango["population"])
        # Nor do projections for Pango Aluquém: its population, median age and sex
        # ratio say so, and put such figures aside.
        for field in ("population", "median_age", "sex_ratio"):
            self.assertIn("whether the 2024 census's or a projection", pango[field]["note"])
            self.assertEqual(pango[field]["displaces_before"], am.YEAR + 1)
            self.assertTrue(pango[field]["displaces_undated"])
        (cited,) = pango["sources"]
        self.assertEqual(cited["field"], "population note/sex_ratio note/median_age note/"
                                         "ethnicity note/language note/religion note")
        self.assertIn("cod-ab-ago", cited["url"])

    def test_luanda_polygons_on_other_ground(self):
        admin1 = ADMIN1 + [{"id": "L", "name": "Luanda"}]
        admin2 = ADMIN2 + [{"id": "91424787B66059706224288", "name": "Belas", "parent": "L"}]
        records, _ = am.build([], admin1, admin2)
        belas = next(r for r in records if r["name"] == "Belas")
        self.assertIn("about 30% in Viana", belas["population"]["note"])
        self.assertTrue(belas["median_age"]["displaces_undated"])
        self.assertNotIn("note", belas["religion"])      # Luanda's reports not read here
        self.assertEqual([s["field"] for s in belas["sources"]],
                         ["population note/sex_ratio note/median_age note"])

    def test_names_as_notes_show_them(self):
        self.assertEqual(am.shown_name("Cacongo(ex_Lândana)"), "Cacongo (ex-Lândana)")
        self.assertEqual(am.shown_name("Catabola (ex. Nova Sintra)"), "Catabola (ex-Nova Sintra)")
        self.assertEqual(am.shown_name("Cunhinga (Vouga)"), "Cunhinga (Vouga)")
        self.assertEqual(am.quadro_of("Quadro 1. 7- Idade média e mediana"), "1.7")
        self.assertEqual(am.quadro_of("Quadro 11 - População residente"), "11")


class National(unittest.TestCase):
    def test_disagreement_is_found(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        total = rep.tables["ethnicity"][0][1]
        # A few per cent apart, or one group apart, is the two publications.
        near = [{"name": "Bengo", "ethnicity": [
            {"group": "Bakongo", "pct": 1.0, "count": total["Bakongo"] * 2},
            {"group": "Ambundu", "pct": 1.0, "count": total["Ambundu"] + 5_000}]}]
        self.assertEqual(am.compare_national([rep], near), [])
        # Two columns under each other's headings move two groups at once.
        national = [{"name": "Bengo", "ethnicity": [
            {"group": "Bakongo", "pct": 1.0, "count": total["Ambundu"]},
            {"group": "Ambundu", "pct": 1.0, "count": total["Bakongo"]}]}]
        notes = {}
        problems = am.compare_national([rep], national, None, notes)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][:2], ("Bengo", "ethnicity"))
        self.assertIn("Ambundu", problems[0][2])
        self.assertRegex(notes[("Bengo", "ethnicity")],
                         r"^The 2024 census's provincial report for Bengo counts [\d,]+ people "
                         r"under \w+ where its national report counts [\d,]+ \(and [\d,]+ "
                         r"against [\d,]+ under \w+\), so the municipalities' ethnic group "
                         r"figures are not shown\.$")
        # The field is then left out of the province's polygons, saying why, and
        # the rest kept.
        records, _ = am.build([rep], ADMIN1, ADMIN2, {("Bengo", "ethnicity")}, None, notes)
        dande = next(r for r in records if r["name"] == "Dande")
        self.assertEqual(dande["ethnicity"]["note"], notes[("Bengo", "ethnicity")])
        self.assertIsInstance(dande["religion"], list)
        self.assertIn("ethnicity note", dande["sources"][0]["field"])
        self.assertNotIn("/ethnicity/", dande["sources"][0]["field"] + "/")
        # The note rests on the provincial table and on the national report: both cited.
        self.assertIn(rep.quadros["ethnicity"], dande["sources"][0]["name"])
        self.assertEqual(dande["sources"][1]["field"], "ethnicity note")
        self.assertEqual(dande["sources"][1]["url"], am.NATIONAL_URL)
        self.assertTrue(dande["sources"][1]["name"].endswith("Resultados Definitivos: Quadro 6.1"))

    def test_only_provinces_known_to_lack_the_2016_table_say_so(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        rep.old = []                                    # as if its 2016 table were not read
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        for r in records:
            for field in ("ethnicity", "language", "religion"):
                note = (r.get(field) or {}).get("note", "") if isinstance(r.get(field), dict) else ""
                self.assertNotIn("only by the municipalities", note)

    def test_a_province_half_read_gets_no_total(self):
        pages, texts = report_pages()
        rep = am.read_report("Cubango", pages, texts)       # Cuando's report not read
        records, lines = am.build([rep], ADMIN1 + [{"id": "CC", "name": "Cuando Cubango"}], ADMIN2)
        self.assertFalse(any(r["level"] == "admin1" and r["name"] == "Cuando Cubango"
                             for r in records))
        self.assertTrue(any("not all its reports read" in line for line in lines))


def report(new, old, short=0, stem="Bengo"):
    rep = am.Report(stem)
    rep.new = [(n, t, round(t * 0.48), t - round(t * 0.48)) for n, t in new]
    rep.old = old
    rep.total = tuple(sum(r[j] for r in rep.new) for j in (1, 2, 3))
    rep.short = short
    return rep


def sexed(name, t, m, f):
    return (name, t, m, f)


class Rounding(unittest.TestCase):
    def test_communes_a_person_off_their_municipality(self):
        rep = am.Report("Cabinda")
        rep.new = [("Necuto", 16_441, 8_000, 8_441), ("Miconje", 8_629, 4_300, 4_329)]
        rows = [("Cabinda", {"TOTAL": 25_070}), ("Necuto", {"TOTAL": 16_441}),
                ("Necuto", {"TOTAL": 14_099}), ("Inhuca", {"TOTAL": 2_343}),
                ("Miconje", {"TOTAL": 8_629}), ("Miconje", {"TOTAL": 8_629})]
        got = am.municipalities(rep, "religion", rows)
        self.assertEqual(set(got), {"necuto", "miconje"})
        self.assertEqual(rep.problems, [])

    def test_a_municipality_its_communes_do_not_make_is_left_out(self):
        rep = am.Report("Cabinda")
        rep.new = [("Necuto", 16_441, 8_000, 8_441), ("Miconje", 8_629, 4_300, 4_329)]
        rows = [("Cabinda", {"TOTAL": 25_070}), ("Necuto", {"TOTAL": 16_441}),
                ("Necuto", {"TOTAL": 14_099}), ("Inhuca", {"TOTAL": 2_443}),
                ("Miconje", {"TOTAL": 8_629}), ("Miconje", {"TOTAL": 8_629})]
        got = am.municipalities(rep, "religion", rows)
        self.assertEqual(set(got), {"miconje"})
        self.assertTrue(any("communes of necuto" in p for p in rep.problems))


class Cells(unittest.TestCase):
    def page(self, dande):
        page = Page()
        page.title("Quadro 7.1 - População com 2 ou mais anos por área de residência e "
                   "município, segundo a religião ou espiritualidade, 2024")
        page.head([("População com 2 ou mais anos", 180), ("Católica", 270),
                   ("Protestante", 335)])
        rights = [240.0, 310.0, 380.0]
        page.row("Bengo", [300, 200, 100], rights)
        page.row("Dande", dande, rights[:len(dande)])
        page.row("Dembos", [200, 100, 100], rights)
        return [am.rows_of(page.words)], [page.text()]

    def test_an_empty_cell_is_nobody_when_the_row_adds_up(self):
        pages, texts = self.page([100, 100])
        rep = am.Report("Bengo")
        rows = dict(am.read_table(rep, "religion", am.TABLES["religion"], pages, texts))
        self.assertEqual(rows["Dande"], {"TOTAL": 100, "Catholic": 100, "Protestant": 0})

    def test_an_empty_cell_that_loses_people_marks_the_row(self):
        # The row stays, so the walk through municipalities keeps its shape, and
        # that municipality's figures are left out, saying why; the rest stand.
        pages, texts = self.page([100, 60])
        rep = am.Report("Bengo")
        rows = am.read_table(rep, "religion", am.TABLES["religion"], pages, texts)
        self.assertEqual([label for label, _ in rows], ["Bengo", "Dande", "Dembos"])
        self.assertEqual(rep.bad_rows["religion"], {1: ("sums", 60, 100)})
        self.assertTrue(any("no figure" in p for p in rep.problems))
        rep.new = [("Dande", 105, 50, 55), ("Dembos", 210, 100, 110)]
        got = am.municipalities(rep, "religion", rows)
        self.assertEqual(set(got), {"dembos"})
        self.assertEqual(rep.refusals["religion"]["dande"], ("sums", 60, 100))
        self.assertIn("the groups of Dande's row add up to 60, not the 100 printed",
                      am.reason_note(rep, "religion", "Dande", ("sums", 60, 100), ["Dande"],
                                     "it stood"))

    def test_broad_age_groups_printed_by_sex(self):
        page = Page()
        page.title("Quadro 1.6 - População por área de residência, municípios e comunas, "
                   "segundo os grandes grupos etários e sexo, 2024")
        rights = [250.0 + 60 * k for k in range(9)]
        page.head([("0 - 14 anos", 270), ("15 - 64 anos", 450), ("65 ou mais", 630)])
        page.head([(w, r - 40) for w, r in zip(["Total", "Homens", "Mulheres"] * 3, rights)])
        page.row("Bengo", [600, 290, 310, 360, 170, 190, 40, 20, 20], rights)
        page.row("Dande", [600, 290, 310, 360, 170, 190, 40, 20, 20], rights)
        rep = am.Report("Bengo")
        rows = dict(am.read_table(rep, "age_broad", am.TABLES["age_broad"],
                                  [am.rows_of(page.words)], [page.text()]))
        self.assertEqual(rows["Dande"], {"0-14": 600, "15-64": 360, "65+": 40, "TOTAL": 1000})

    def test_names_with_brackets(self):
        self.assertIn("cacongo", am.census_keys("Cacongo(ex_Lândana)"))
        self.assertIn("catabola", am.census_keys("Catabola (ex. Nova Sintra)"))
        admin2 = [{"id": "c", "name": "Cunhinga", "parent": "Z"},
                  {"id": "k", "name": "Cuito", "parent": "Z"}]
        poly = am.polygon_for("Cunhinga (Vouga)", "Bié", admin2, {"Z": "bie"})
        self.assertEqual(poly["id"], "c")


class OldDivision(unittest.TestCase):
    def test_a_table_of_namesakes_is_not_the_old_division(self):
        pages, texts = report_pages()
        old = next(i for i, t in enumerate(texts) if "censos2014e2024" in t)
        page = Page()
        page.title("Quadro 11 - População residente por município, segundo o sexo, "
                   "Censos 2014 e 2024")
        page.head([("Censo 2014", 250), ("Censo 2024", 430)])
        r6 = [260.0, 320.0, 380.0, 440.0, 500.0, 560.0]
        page.row("Bengo", [252_586, 125_695, 126_890, 488_974, 241_952, 247_023], r6)
        page.row("Dande", [222_528, 111_188, 111_340, *NEW[0][1:]], r6)
        page.row("Quibaxe", [30_058, 14_507, 15_550, *NEW[4][1:]], r6)
        pages[old], texts[old] = am.rows_of(page.words), page.text()
        rep = am.read_report("Bengo", pages, texts)
        self.assertEqual(rep.old, [])
        self.assertEqual(rep.namesakes, 4)
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        dande = next(r for r in records if r["name"] == "Dande")
        self.assertIn("leaves out the 4 others", dande["religion"]["note"])
        self.assertNotIn("value", dande["population"])

    def test_straddling_municipalities_within_two_per_cent(self):
        rep = report([("A", 1_000), ("B", 500), ("C", 300), ("D", 200)],
                     [("A", 1_492, 716, 776), ("C", 508, 244, 264)])
        got = am.crosswalk_parts(rep)
        self.assertEqual(got["a"], (["A", "B"], False))
        self.assertEqual(got["c"], (["C", "D"], False))
        # A table that does not make its province is believed only where exact.
        rep = report([("A", 1_000), ("B", 500), ("C", 300), ("D", 200)],
                     [("A", 1_492, 716, 776), ("C", 508, 244, 264)], short=10)
        self.assertEqual(am.crosswalk_parts(rep), {})

    def test_each_old_municipality_on_its_own(self):
        rep = report([("Dande", 1_000), ("Panguila", 500), ("Quibaxe", 310), ("Piri", 200),
                      ("Coxe", 77)],
                     [("Dande", 1_500, 720, 780), ("Dembos", 450, 216, 234)], short=137)
        got = am.crosswalk_parts(rep)
        self.assertEqual(got, {"dande": (["Dande", "Panguila"], True)})
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        by = {r["name"]: r for r in records if r["level"] == "admin2"}
        self.assertEqual(by["Dande"]["population"]["value"], 1_500)
        self.assertNotIn("value", by["Dembos-Quibaxe"]["population"])
        self.assertEqual(by["Dembos-Quibaxe"]["ethnicity"]["note"],
                         "The 2024 census's table of Bengo province's municipalities as they "
                         "stood under Lei n.º 18/16 adds up to 1,950 residents, 137 short of the "
                         "province's 2,087, so only the rows that municipalities created in 2024 "
                         "make exactly are taken, and none makes Dembos's; its figures are not "
                         "shown.")

    def test_a_municipality_more_than_one_set_makes(self):
        rep = report([("A", 40_000), ("B", 30_000), ("C", 20_000), ("D", 10_000)],
                     [("A", 70_000, 33_600, 36_400), ("E", 30_000, 14_400, 15_600)])
        self.assertEqual(am.crosswalk_parts(rep), {})
        self.assertEqual(rep.candidates["a"], [(["A", "B"], 70_000), (["A", "C", "D"], 70_000)])
        admin2 = [{"id": "pa", "name": "A", "parent": "B"}, {"id": "pe", "name": "E", "parent": "B"}]
        records, _ = am.build([rep], ADMIN1, admin2)
        a = next(r for r in records if r["name"] == "A")
        self.assertEqual(a["population"]["value"], 70_000)
        self.assertEqual(a["religion"]["note"],
                         "The 2024 census publishes ethnic group, mother tongue and religion only "
                         "for the municipalities created in 2024, and more than one set of them "
                         "comes within 2% of A as it stood under Lei n.º 18/16 (70,000 residents) "
                         "in its residents, its men and its women: A and B make 70,000, and A, C "
                         "and D 70,000, so it cannot be matched to one set of them, and its own "
                         "figures for these are not shown.")


RELIGION_TITLE = ("Quadro 7.1 - População com 2 ou mais anos por área de residência e "
                  "município, segundo a religião ou espiritualidade, 2024")


class Continued(unittest.TestCase):
    def read(self, pages):
        rep = am.Report("Bengo")
        rows = am.read_table(rep, "religion", am.TABLES["religion"],
                             [am.rows_of(pg.words) for pg in pages], [pg.text() for pg in pages])
        return rep, dict(rows)

    def test_a_heading_that_runs_onto_a_second_line(self):
        # Cuanza Sul's: "... segundo a religião ou" / "espiritualidade, 2024".
        page = Page()
        page.title("Quadro 7.1 - População com 2 ou mais anos por município e área de "
                   "residência, segundo a religião ou")
        page.head([("espiritualidade, 2024", LEFT)])
        page.head([("População com 2 ou mais anos", 180), ("Católica", 270),
                   ("Protestante", 335)])
        page.row("Bengo", [300, 200, 100], [240.0, 310.0, 380.0])
        page.row("Dande", [100, 60, 40], [240.0, 310.0, 380.0])
        self.assertEqual(am.table_numbers(am.TABLES["religion"], [page.text()]), {"71"})
        _, rows = self.read([page])
        self.assertEqual(rows["Dande"], {"TOTAL": 100, "Catholic": 60, "Protestant": 40})

    def test_columns_carried_to_an_untitled_page(self):
        first, second = Page(), Page()
        first.title(RELIGION_TITLE)
        first.head([("População com 2 ou mais anos", 180), ("Católica", 270)])
        second.head([("População com 2 ou mais anos", 180), ("Protestante", 270)])
        for label, total, cat in (("Bengo", 300, 200), ("Dande", 100, 60), ("Dembos", 200, 140)):
            first.row(label, [total, cat], [240.0, 310.0])
            second.row(label, [total, total - cat], [240.0, 310.0])
        _, rows = self.read([first, second])
        self.assertEqual(rows["Dande"], {"TOTAL": 100, "Catholic": 60, "Protestant": 40})

    def test_rows_carried_on_under_the_province_printed_again(self):
        first, second = Page(), Page()
        for page in (first, second):
            page.title(RELIGION_TITLE)
            page.head([("População com 2 ou mais anos", 180), ("Católica", 270),
                       ("Protestante", 335)])
            page.row("Bengo", [300, 200, 100], [240.0, 310.0, 380.0])
        first.row("Dande", [100, 60, 40], [240.0, 310.0, 380.0])
        second.row("Dembos", [200, 140, 60], [240.0, 310.0, 380.0])
        _, rows = self.read([first, second])
        self.assertEqual(list(rows), ["Bengo", "Dande", "Dembos"])

    def test_the_same_age_groups_printed_twice(self):
        plain, sexed = Page(), Page()
        plain.title("Quadro 1.4 - População por área de residência, municípios e comunas, "
                    "segundo os grandes grupos etários, 2024")
        plain.head([("Total", 220), ("0 - 14 anos", 270), ("15-64 anos", 330),
                    ("65 ou mais anos", 390)])
        plain.row("Dande", [1000, 600, 360, 40], [240.0, 300.0, 360.0, 420.0])
        sexed.title("Quadro 1.6 - População por área de residência, municípios e comunas, "
                    "segundo os grandes grupos etários e sexo, 2024")
        rights = [250.0 + 60 * k for k in range(9)]
        sexed.head([("0 - 14 anos", 270), ("15 - 64 anos", 450), ("65 ou mais", 630)])
        sexed.head([(w, r - 40) for w, r in zip(["Total", "Homens", "Mulheres"] * 3, rights)])
        sexed.row("Homens", [290, 290, 0, 170, 170, 0, 20, 20, 0], rights)
        sexed.row("Dande", [600, 290, 310, 360, 170, 190, 40, 20, 20], rights)
        rep = am.Report("Bengo")
        rows = dict(am.read_table(rep, "age_broad", am.TABLES["age_broad"],
                                  [am.rows_of(plain.words), am.rows_of(sexed.words)],
                                  [plain.text(), sexed.text()]))
        self.assertEqual(rows["Dande"], {"TOTAL": 1000, "0-14": 600, "15-64": 360, "65+": 40})
        self.assertEqual(rep.problems, [])


class Settling(unittest.TestCase):
    def test_a_municipality_settles_once_its_neighbour_has(self):
        new = [("Moçâmedes", 345_987), ("Tômbwa", 123_620), ("Bibala", 119_295),
               ("Virei", 54_034), ("Camucuio", 42_073), ("Lucira", 28_354),
               ("Cacimbas", 32_077), ("Sacomar", 65_692), ("Iona", 4_576)]
        rep = report(new, [])
        by = {n: (t, m, f) for n, t, m, f in rep.new}

        def old(name, parts, moved=(0, 0, 0)):
            return (name, *(sum(by[q][j] for q in parts) + moved[j] for j in range(3)))
        rep.old = [old("Moçâmedes", ["Moçâmedes", "Sacomar", "Lucira"], (-340, -163, -177)),
                   old("Tômbwa", ["Tômbwa", "Iona"], (340, 163, 177)),
                   old("Bibala", ["Bibala"]), old("Virei", ["Virei"]),
                   old("Camucuio", ["Camucuio", "Cacimbas"])]
        got = am.crosswalk_parts(rep)
        self.assertEqual(set(got["mocamedes"][0]), {"Moçâmedes", "Sacomar", "Lucira"})
        self.assertFalse(got["mocamedes"][1])
        self.assertEqual(got["tombwa"], (["Tômbwa", "Iona"], False))
        self.assertEqual(got["camucuio"], (["Camucuio", "Cacimbas"], True))

    def test_rows_against_their_residents(self):
        self.assertTrue(am.plausible("religion", 95_000, 100_000))
        self.assertFalse(am.plausible("religion", 50_000, 100_000))
        self.assertTrue(am.plausible("age_other", 100_200, 100_000))
        self.assertFalse(am.plausible("age_broad", 90_000, 100_000))

    def test_one_group_apart_is_said(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        total = rep.tables["ethnicity"][0][1]
        near = [{"name": "Bengo", "ethnicity": [
            {"group": "Bakongo", "pct": 1.0, "count": total["Bakongo"] * 2},
            {"group": "Ambundu", "pct": 1.0, "count": total["Ambundu"] + 5_000}]}]
        apart = {}
        self.assertEqual(am.compare_national([rep], near, apart), [])
        self.assertIn("national report", apart[("Bengo", "ethnicity")])
        records, _ = am.build([rep], ADMIN1, ADMIN2, set(), apart)
        dande = next(r for r in records if r["name"] == "Dande")
        self.assertIn(f"{total['Bakongo'] * 2:,}", dande["ethnicity_note"])
        # The figure the note quotes is the national report's, which it cites.
        self.assertEqual([s["field"] for s in dande["sources"]][1:], ["ethnicity note"])


class Resuming(unittest.TestCase):
    def test_a_municipality_whose_own_row_is_missing_is_its_communes(self):
        # Cunene's ethnic groups list Cahama's two communes and no row for Cahama:
        # its namesake commune's 76,090 is too few for its 140,925 residents.
        rep = am.Report("Cunene")
        rep.new = [("Chitado", 35_425, 17_000, 18_425), ("Cahama", 140_925, 68_000, 72_925),
                   ("Cuvelai", 76_582, 37_000, 39_582)]
        rows = [("Cunene", {"TOTAL": 1_000_000}), ("Chitado", {"TOTAL": 32_985}),
                ("Chitado", {"TOTAL": 32_985}), ("Cahama", {"TOTAL": 76_090, "Herero": 76_090}),
                ("Otchinjau", {"TOTAL": 54_436, "Herero": 50_000, "Other": 4_436}),
                ("Cuvelai", {"TOTAL": 70_729}), ("Cuvelai", {"TOTAL": 70_729})]
        got = am.municipalities(rep, "ethnicity", rows)
        self.assertEqual(set(got), {"chitado", "cahama", "cuvelai"})
        self.assertEqual(got["cahama"], {"TOTAL": 130_526, "Herero": 126_090, "Other": 4_436})
        self.assertEqual(rep.patched["ethnicity"]["cahama"], ("namesake", 76_090, 130_526))

    def test_a_misprinted_row_gives_way_to_its_communes(self):
        # Cunene's mother tongues give Cafima 25,194 against 19,163 residents.
        rep = am.Report("Cunene")
        rep.new = [("Nehone", 181_969, 88_000, 93_969), ("Cafima", 19_163, 9_000, 10_163),
                   ("Chissuata", 7_996, 3_900, 4_096)]
        rows = [("Cunene", {"TOTAL": 1_688_677}), ("Nehone", {"TOTAL": 170_000}),
                ("Nehone", {"TOTAL": 120_000}), ("Evale", {"TOTAL": 50_000}),
                ("Cafima", {"TOTAL": 25_194, "Kwanyama": 25_194}),
                ("Cafima", {"TOTAL": 17_788, "Kwanyama": 17_000, "Portuguese": 788}),
                ("Chissuata", {"TOTAL": 7_500}), ("Chissuata", {"TOTAL": 7_500})]
        got = am.municipalities(rep, "language", rows)
        self.assertEqual(set(got), {"nehone", "cafima", "chissuata"})
        self.assertEqual(got["cafima"], {"TOTAL": 17_788, "Kwanyama": 17_000, "Portuguese": 788})
        self.assertEqual(rep.patched["language"]["cafima"], ("communes", 25_194, 17_788))
        note = am.patched_note(rep, ("language",), ["cafima"], {"cafima": "Cafima"},
                               {"cafima": 19_163})
        self.assertEqual(note, " Cafima's own row in that table counts 25,194 people, against "
                               "its 19,163 residents; its communes' rows, which add up to 17,788, "
                               "are taken in its place.")

    def test_a_municipality_counted_with_its_neighbour(self):
        # Cunene's ethnic groups count Naulila's people in Humbe's row too.
        rep = am.Report("Cunene")
        rep.new = [("Humbe", 198_400, 95_000, 103_400), ("Naulila", 83_504, 40_000, 43_504)]
        rows = [("Cunene", {"TOTAL": 2_000_000}), ("Humbe", {"TOTAL": 262_420}),
                ("Mucope", {"TOTAL": 90_000}), ("Humbe", {"TOTAL": 94_059}),
                ("Naulila", {"TOTAL": 78_361}), ("Naulila", {"TOTAL": 78_361})]
        got = am.municipalities(rep, "ethnicity", rows)
        self.assertEqual(got["humbe"]["TOTAL"], 184_059)
        self.assertEqual(got["naulila"]["TOTAL"], 78_361)

    def test_two_rows_that_trade_people_are_both_found_and_left_out(self):
        # Benguela's broad age groups give Baía Farta 12,634 people more than
        # its residents and Caimbambo as many fewer, rows and communes alike.
        rep = am.Report("Benguela")
        rep.new = [("Baia Farta", 95_994, 46_000, 49_994), ("Caimbambo", 79_511, 38_000, 41_511),
                   ("Cubal", 229_379, 110_000, 119_379)]
        rows = [("Benguela", {"TOTAL": 2_597_638}), ("Baia Farta", {"TOTAL": 108_628}),
                ("Baia Farta", {"TOTAL": 60_000}), ("Calahanga", {"TOTAL": 48_628}),
                ("Caimbambo", {"TOTAL": 66_877}), ("Caimbambo", {"TOTAL": 66_877}),
                ("Cubal", {"TOTAL": 229_379}), ("Cubal", {"TOTAL": 229_379})]
        got = am.municipalities(rep, "age_broad", rows)
        self.assertEqual(set(got), {"cubal"})
        self.assertEqual(rep.refusals["age_broad"]["baiafarta"], ("plausible", 108_628, 95_994))
        self.assertEqual(rep.refusals["age_broad"]["caimbambo"], ("plausible", 66_877, 79_511))
        self.assertFalse(any("not found" in p for p in rep.problems))

    def test_a_row_no_communes_make_up_for_is_left_out(self):
        rep = am.Report("Cunene")
        rep.new = [("Cahama", 140_925, 68_000, 72_925), ("Cuvelai", 76_582, 37_000, 39_582)]
        rows = [("Cunene", {"TOTAL": 1_000_000}), ("Cahama", {"TOTAL": 40_000}),
                ("Otchinjau", {"TOTAL": 30_000}), ("Cuvelai", {"TOTAL": 70_729})]
        got = am.municipalities(rep, "ethnicity", rows)
        self.assertEqual(set(got), {"cuvelai"})
        self.assertEqual(rep.refusals["ethnicity"]["cahama"], ("plausible", 40_000, 140_925))

    def test_rows_aligned_on_a_shortened_name_or_their_total(self):
        self.assertTrue(am.aligned("Jamba", "Jamba Mineira", None, None))
        self.assertTrue(am.aligned("Urbama", "Urbana", None, None))
        self.assertTrue(am.aligned("Xa-Muteba", "Cassanje", 40_000, 40_000))
        self.assertFalse(am.aligned("Luau", "Luanda", 10, 20))


class Medians(unittest.TestCase):
    def rep(self, names):
        rep = am.Report("Malanje")
        rep.new = [(n, 1_000, 500, 500) for n in names]
        return rep

    def test_two_column_groups_side_by_side(self):
        # Malanje's Quadro 1.7: the left group runs on into the right one, whose
        # rows share the left's baselines or fall between them.
        left = [("Total", 22.9, 18.0), ("Área de residência", None, None),
                ("Urbana", 21.8, 18.0), ("Rural", 24.3, 18.0), ("Municípios", None, None),
                ("Calandula", 25.6, 19.0), ("Calandula", 24.0, 17.0), ("Cota", 27.7, 22.0),
                ("Malanje", 22.6, 18.0), ("Malanje", 22.4, 17.0)]
        right = [("Quinguengue", 22.2, 17.0), ("Milando", 24.8, 21.0), ("Milando", 24.8, 21.0),
                 ("Xandel", 23.7, 18.0), ("Xandel", 23.5, 16.0), ("Moma", 24.2, 18.0)]
        page = Page()
        page.title("Quadro 1.7 - Idade média e mediana da população por área de residência e "
                   "sexo, 2024")
        page.head([("Média", 200), ("Mediana", 250), ("Média", 470), ("Mediana", 520)])
        for k, (label, mean, median) in enumerate(left):
            top = page.top + 12 * k
            page.words += (header(top, [(label, LEFT)]) if mean is None else
                           decimal_words(top, label, LEFT, (mean, median), (230.0, 285.0)))
        for k, (label, mean, median) in enumerate(right):
            top = page.top + 12 * k + (0 if k % 2 else 6)
            page.words += decimal_words(top, label, 320.0, (mean, median), (500.0, 555.0))
        rep = self.rep(["Calandula", "Malanje", "Milando", "Xandel"])
        am.medians_of(rep, [am.rows_of(page.words)], [page.text()])
        self.assertEqual(rep.median, 18.0)
        self.assertEqual(rep.medians, {"calandula": 19.0, "malanje": 18.0, "milando": 21.0,
                                       "xandel": 18.0})

    def test_three_column_groups(self):
        page = Page()
        page.title("Quadro 1.7 - Idade média e mediana da população por área de residência e "
                   "sexo, 2024")
        page.head([("Mediana", 150), ("Mediana", 330), ("Mediana", 510)])
        groups = [[("Uíge", 20.1, 16.0), ("Municípios", None, None), ("Bungo", 19.0, 15.0)],
                  [("Negage", 21.0, 17.0), ("Negage", 21.0, 17.0)],
                  [("Puri", 18.0, 14.0), ("Puri", 18.0, 14.0)]]
        for g, entries in enumerate(groups):
            left = LEFT + 180 * g
            for k, (label, mean, median) in enumerate(entries):
                top = page.top + 12 * k
                page.words += (header(top, [(label, left)]) if mean is None else
                               decimal_words(top, label, left, (mean, median),
                                             (left + 80, left + 100)))
        rep = self.rep(["Bungo", "Negage", "Puri"])
        am.medians_of(rep, [am.rows_of(page.words)], [""])
        self.assertEqual(rep.median, 16.0)
        self.assertEqual(rep.medians, {"bungo": 15.0, "negage": 17.0, "puri": 14.0})

    def test_a_municipality_printed_without_figures(self):
        # Benguela's table leaves the row of a municipality of several communes
        # blank: it has no median of its own, and its commune's is not taken.
        page = median_page([("Benguela", 22.6, 18.0), ("Municípios", None, None),
                            ("Bocoio", None, None), ("Bocoio", 22.9, 17.0),
                            ("Monte Belo", 23.2, 17.0), ("Cubal", 21.6, 16.0),
                            ("Cubal", 21.6, 16.0)])
        rep = self.rep(["Bocoio", "Cubal"])
        am.medians_of(rep, [am.rows_of(page.words)], [page.text()])
        self.assertEqual(rep.medians, {"bocoio": None, "cubal": 16.0})
        self.assertEqual(rep.problems, [])


class Columns(unittest.TestCase):
    def test_figures_of_two_columns_printed_close(self):
        page = Page()
        page.title("Quadro 6.1 - População com 2 ou mais anos por município, segundo grupos "
                   "étnicos ou tribos, 2024")
        rights = [240.0, 256.0, 330.0]
        page.head([("Quicongo", 200), ("Quimbundu", 226), ("Lunda-Quioco", 280)])
        page.row("Lunda Sul", [5, 34, 3_451], rights)
        page.row("Alto Chicapa", [1, 340, 3_451], rights)
        block = am.blocks_of(am.rows_of(page.words))[0]
        self.assertEqual([v for *_, v in block.data[1].figures()], [1_340, 3_451])
        self.assertEqual(am.assign_columns(block), [])
        self.assertEqual(am.values(block, block.data[1]), [1, 340, 3_451])

    def test_a_row_of_one_figure_in_a_column_group(self):
        # Lunda Sul's Alto Chicapa: all its people are under columns of the first
        # group, and the second prints only their number.
        pages = []
        for labels, rows in ((["Quicongo", "Quimbundo"],
                              [("Lunda Sul", [1_000, 2_000]), ("Dala", [400, 600]),
                               ("Alto Chicapa", [1, 340])]),
                             (["Não sabe", "Total"],
                              [("Lunda Sul", [1_050, 4_050]), ("Dala", [1_010, 2_010]),
                               ("Alto Chicapa", [341])])):
            page = Page()
            page.title("Quadro 6.1 - População com 2 ou mais anos por município, segundo "
                       "grupos étnicos ou tribos, 2024")
            page.head([(labels[0], 200), (labels[1], 270)])
            for label, values in rows:
                page.row(label, values, [240.0, 330.0][-len(values):])
            pages.append(page)
        rep = am.Report("Lunda_Sul")
        got = dict(am.read_table(rep, "ethnicity", am.TABLES["ethnicity"],
                                 [am.rows_of(p.words) for p in pages], [p.text() for p in pages]))
        self.assertEqual(got["Alto Chicapa"], {"Bakongo": 1, "Ambundu": 340, "Not stated": 0,
                                               "TOTAL": 341})
        self.assertEqual(rep.problems, [])

    def test_a_line_of_one_figure_off_the_total_is_no_row(self):
        page = Page()
        page.title("Quadro 7.1 - População com 2 ou mais anos por área de residência e "
                   "município, segundo a religião ou espiritualidade, 2024")
        page.head([("População com 2 ou mais anos", 180), ("Católica", 270),
                   ("Protestante", 335)])
        rights = [240.0, 310.0, 380.0]
        page.row("Bengo", [3_000, 2_000, 1_000], rights)
        page.row("Municípios / Comunas", [2], [380.0])      # a stray footnote mark
        page.row("Dande", [1_000, 600, 400], rights)
        page.row("Dembos", [2_000, 1_400, 600], rights)
        rep = am.Report("Bengo")
        got = am.read_table(rep, "religion", am.TABLES["religion"], [am.rows_of(page.words)],
                            [page.text()])
        self.assertEqual([label for label, _ in got], ["Bengo", "Dande", "Dembos"])
        self.assertEqual(rep.problems, [])


def laid_out(lines):
    """Rows as a run's page dump prints them, "top|word@x0 word@x0 ...": a
    figure such as "22,4" is 14.5 points wide, a word 5 points a letter."""
    rows = []
    for line in lines:
        top, _, words = line.partition("|")
        row = am.Row(float(top))
        for word in words.split():
            text, _, x0 = word.rpartition("@")
            width = 14.5 if am.DECIMAL.match(text) else 5.0 * len(text)
            row.words.append((float(x0), float(x0) + width, text))
        rows.append(row)
    return rows


# Uíge's Quadro 1.7 as its report lays it out (run 1de29a8, page 78): three
# column groups side by side, each municipality's row before its communes',
# and the first two rows of the third group ending 21 points left of the rest.
UIGE_P78 = """59|Quadro@269 1.7@303 -@318 Idade@323 média@349 e@377 mediana@384 da@422 população@435 por@481 área@497 de@518 residência@530 e@575 sexo@582
84|Média@211 Mediana@274 Média@456 Mediana@519 Média@701 Mediana@764
101|Uíge@91 22,4@214 17,0@281 Lêmboa@344 25,2@460 18,0@527 Luanga@589 23,6@705 17,0@772
112|Área@91 de@108 residência@118 Petecusso@344 25,1@460 20,0@527 Mucaba@581 22,0@705 15,0@772
124|Urbana@99 21,7@214 17,0@281 Sanza@336 Pombo@357 22,8@460 16,0@527 Mucaba@589 21,9@726 15,0@793
136|Rural@99 23,2@214 17,0@281 Sanza@344 Pombo@364 22,4@460 16,0@527 Uando@589 Mucaba@612 22,6@726 15,0@793
148|Sexo@91 Alfândega@344 21,7@460 15,0@527 Nova@581 Esperança@600 21,6@726 15,0@793
160|Homens@99 21,9@214 16,0@281 Cuílo@344 Pombo@362 25,0@460 19,0@527 Nova@589 Esperança@608 21,1@726 15,0@793
172|Mulheres@99 22,9@214 18,0@281 Uamba@344 24,4@460 17,0@527 Buenga-Sul@589 22,1@726 15,0@793
184|Bembe@336 26,6@460 19,0@527 Cuílo@589 Camboso@607 22,9@726 16,0@793
186|Municíppios@99
195|Bembe@344 26,5@460 19,0@527 Sacandica@581 23,2@726 20,0@793
198|Dange@91 Quitexe@114 22,7@214 17,0@281
207|Mabaia@344 26,7@460 20,0@527 Sacandica@589 23,8@726 21,0@793
210|Quitexe@99 22,9@214 17,0@281
219|Milunga@336 21,8@460 16,0@527 Béu@589 22,4@726 19,0@793
222|Aldeia@99 Viçosa@121 22,2@214 17,0@281
231|Milunga@344 22,3@460 16,0@527 Cuilo@589 Futa@607 28,5@726 24,0@793
234|Bungo@91 21,7@214 15,0@281
243|Macocola@344 21,6@460 15,0@527 Quipedro@581 23,6@726 17,0@793
245|Bungo@99 21,7@214 15,0@281
255|Songo@336 21,9@460 16,0@527 Quipedro@589 23,6@726 17,0@793
257|Ambuila@91 23,1@214 17,0@281
267|Songo@344 21,5@460 16,0@527 Alto@581 Zaza@597 23,4@726 19,0@793
269|Ambuila@99 23,1@214 17,0@281
278|Quivuenga@344 24,1@460 18,0@527 Alto@589 Zaza@604 23,6@726 19,0@793
281|Negage@91 21,4@214 16,0@281
290|Quimbele@336 24,0@460 18,0@527 Cuango@589 Calumbo@615 22,9@726 19,0@793
293|Negage@91 21,0@214 16,0@281
302|Quimbele@344 23,9@460 18,0@527 Massau@581 21,5@726 16,0@793
305|Dimuca@99 22,8@214 16,0@281
314|Icoca@344 24,3@460 19,0@527 Massau@589 21,2@726 15,0@793
316|Quisseque@99 22,3@214 16,0@281
326|Cangola@336 22,5@460 16,0@527 Macolo@589 22,0@726 16,0@793
328|Puri@91 22,4@214 15,0@281
338|Cangola@344 22,6@460 16,0@527 Nsosso@581 25,0@726 18,0@793
340|Puri@99 22,4@214 15,0@281
349|Bengo@344 22,8@460 16,0@527 Nsosso@589 25,0@726 18,0@793
352|Maquela@99 do@129 Zombo@139 23,6@214 19,0@281
361|Caiongo@344 22,2@460 15,0@527 Vista@581 Alegre@599 21,4@726 16,0@793
364|Maquela@99 do@129 Zombo@139 23,4@214 19,0@281
373|Uíge@336 21,9@460 17,0@527 Vista@581 Alegre@599 21,4@726 16,0@793
376|Quibocolo@91 24,7@214 21,0@281
385|Uíge@344 21,8@460 17,0@527 Cambamba@581 21,3@726 16,0@793
388|Damba@91 25,2@214 20,0@281
397|Cancungo@344 22,2@460 17,0@527 Lucunga@581 26,0@726 19,0@793
399|Damba@99 25,4@214 20,0@281
409|Casseche@344 22,0@460 16,0@527 Lucunga@589 26,0@726 19,0@793
411|Camatambo@99 23,2@214 17,0@281""".splitlines()
UIGE_2024 = ["Dange Quitexe", "Bungo", "Ambuila", "Negage", "Puri", "Maquela do Zombo", "Damba",
             "Sanza Pombo", "Bembe", "Milunga", "Songo", "Quimbele", "Cangola", "Uíge",
             "Mucaba", "Nova Esperança", "Sacandica", "Quipedro", "Alto Zaza", "Massau",
             "Nsosso", "Vista Alegre", "Lucunga"]
# Moxico's (run 1de29a8, page 73): the province's figures end 19 points left of
# the column the rows below it end in.
MOXICO_P73 = """59|Quadro@126 1.7@160 -@175 Idade@180 média@206 e@234 mediana@241 da@280 população@292 por@338 área@354 de@375 residência@388 e@432 sexo,@440 2024@463
74|Média@331 Mediana@399
89|Moxico@163 22,37@336 18,00@408
103|Área@163 de@181 Residência@191
117|Urbana@163 21,97@355 18,00@432
130|Rural@163 23,28@355 18,00@432
143|Sexo@163
156|Homens@163 22,28@355 18,00@432
170|Mulheres@163 22,46@355 18,00@432
183|Município/Comuna@163
196|Luena@163 22,2@356 18,0@433
209|Luena@171 22,2@356 18,0@433
222|Cassongo@171 20,0@356 15,0@433""".splitlines()


class ReviewRound(unittest.TestCase):
    def test_three_column_groups(self):
        rep = am.Report("Uige")
        rep.new = [(n, 1, 1, 0) for n in UIGE_2024]
        am.medians_of(rep, [laid_out(UIGE_P78)], [""])
        self.assertEqual(rep.median, 17.0)
        self.assertEqual(rep.quadros["province_median"], "1.7")
        self.assertEqual(rep.medians, {
            "dangequitexe": 17.0, "bungo": 15.0, "ambuila": 17.0, "negage": 16.0, "puri": 15.0,
            "maqueladozombo": 19.0, "damba": 20.0, "sanzapombo": 16.0, "bembe": 19.0,
            "milunga": 16.0, "songo": 16.0, "quimbele": 18.0, "cangola": 16.0, "uige": 17.0,
            "mucaba": 15.0, "novaesperanca": 15.0, "sacandica": 20.0, "quipedro": 17.0,
            "altozaza": 19.0, "massau": 16.0, "nsosso": 18.0, "vistaalegre": 16.0,
            "lucunga": 19.0})
        self.assertEqual(rep.problems, [])

    def test_a_row_ending_off_its_column(self):
        rep = am.Report("Moxico")
        rep.new = [("Luena", 1, 1, 0)]
        am.medians_of(rep, [laid_out(MOXICO_P73)], [""])
        self.assertEqual((rep.median, rep.medians), (18.0, {"luena": 18.0}))

    def test_key_indicators_give_the_province(self):
        quadro1 = laid_out(["103|Quadro@191 1@225 -@233 Síntese@239 dos@271 principais@288 "
                            "indicadores,@330 2014@383 e@406 2024@433",
                            "229|1.4@97 Idade@120 mediana@140 da@170 população@180 15,0@457 "
                            "16,0@513"])
        quadro2 = laid_out(["59|Quadro@205 2@241 -@249 Síntese@255 dos@287 principais@304 "
                            "indicadores,@346 2024@419",
                            "175|1.4@58 Idade@79 mediana@99 da@129 população@139 16,0@354 "
                            "17,0@398 16,0@444 16,0@491 17,0@538"])
        self.assertEqual(am.indicator_median([quadro1, quadro2]), (16.0, "1"))
        new = laid_out(["200|1.4@41 Idade@63 mediana@83 da@113 população@123 -@460 18,0@500"])
        self.assertEqual(am.indicator_median([new]), (18.0, ""))
        other = laid_out(["175|1.4@58 Idade@79 mediana@99 da@129 população@139 17,0@354 "
                          "17,0@398 16,0@444 16,0@491 17,0@538"])
        self.assertEqual(am.indicator_median([quadro1, other]), (None, ""))
        # Huambo prints no Quadro 1.7 (the page after Quadro 1.6 is blank).
        rep = am.Report("Huambo")
        rep.new = [("Huambo", 1, 1, 0)]
        am.medians_of(rep, [quadro1, quadro2], ["", ""])
        self.assertEqual((rep.median, rep.quadros["province_median"]), (16.0, "1"))
        self.assertEqual(rep.medians, {})

    def test_completed_years(self):
        # The middle person at 21.8 years is 21 in completed years.
        groups = [(0, 14, 360), (15, 19, 110), (20, 29, 170), (30, 54, 250), (55, 64, 50),
                  (65, 74, 30), (75, None, 30)]
        self.assertEqual(am.completed_median(groups), 21.0)
        self.assertIsNone(am.completed_median([(0, 14, 10), (15, None, 90)]))

    def five_year(self, scale=1):
        sizes = [70, 65, 62, 55, 48, 40, 33, 27, 21, 18, 14, 11, 8, 6, 4, 3, 2, 1]
        return {(5 * k, 5 * k + 4): n * scale for k, n in enumerate(sizes)}

    def province(self, medians, groups):
        reps = []
        for stem, median in medians:
            rep = am.Report(stem)
            rep.median = median
            rep.quadros["province_median"] = "1.7"
            reps.append(rep)
        fields, given, noted, quadros, lines = {}, [], [], [], []
        total = sum(groups.values())
        am.province_median("Cuando Cubango", reps, [s for s, _ in medians], total, groups,
                           fields, given, noted, quadros, lines)
        return fields, given, noted

    def test_two_provinces_with_one_median(self):
        fields, given, _ = self.province([("Cubango", 18.0), ("Cuando", 18.0)], self.five_year())
        self.assertEqual(fields["median_age"]["value"], 18.0)
        self.assertEqual(fields["median_age_note"],
                         "The census publishes a median age of 18 years for both Cubango and "
                         "Cuando provinces, which were made out of this one in 2024, so the two "
                         "together have that median too.")
        self.assertEqual(given, ["median_age"])

    def test_two_provinces_with_two_medians(self):
        # The groups put the middle person at 19.3 years: 19, between 18 and 21.
        fields, _, _ = self.province([("Luanda", 21.0), ("Icolo e Bengo", 18.0)],
                                     self.five_year())
        self.assertEqual(fields["median_age"]["value"], 19.0)
        self.assertIn("in completed years, as the census gives its medians; the census "
                      "publishes 21 years for Luanda and 18 years for Icolo e Bengo",
                      fields["median_age_note"])
        fields, given, noted = self.province([("Luanda", 23.0), ("Icolo e Bengo", 21.0)],
                                             self.five_year())
        self.assertNotIn("value", fields["median_age"])
        self.assertIn("does not fall between the two", fields["median_age"]["note"])
        self.assertEqual((given, noted), ([], ["median_age"]))

    def test_merged_polygon_medians(self):
        rows = [{"age_broad": {"TOTAL": 1000, "0-14": 360, "15-64": 580, "65+": 60},
                 "age_other": {"TOTAL": 1000, "0-19": 470, "20-29": 170, "30-54": 250,
                               "55-64": 50, "65-74": 30, "75+": 30}}] * 2
        usable = {"age_broad", "age_other"}

        def run(medians):
            rep = am.Report("Bengo")
            rep.medians = dict(zip(("quibaxe", "piri"), medians))
            fields, given, quadros, noted = {}, [], [], []
            am.median_fields(rep, [{"name": "Dembos"}], ["Quibaxe", "Piri"], ["quibaxe", "piri"],
                             rows, ["Dembos"], "it stood", "", "", usable, {}, {}, fields,
                             given, quadros, [], "Dembos-Quibaxe", noted)
            return fields, noted
        fields, _ = run((20.0, 20.0))
        self.assertEqual(fields["median_age"]["value"], 20.0)
        self.assertIn("a median age of 20 years for each of the municipalities created in 2024 "
                      "that make up Dembos", fields["median_age_note"])
        fields, _ = run((21.0, 22.0))
        self.assertEqual(fields["median_age"]["value"], 21.0)
        fields, noted = run((17.0, 16.0))
        self.assertNotIn("value", fields["median_age"])
        self.assertIn("(Quibaxe 17 and Piri 16 years)", fields["median_age"]["note"])
        self.assertEqual(noted, ["median_age"])

    def religion_page(self, rows, title="Quadro 7.1 - População com 2 ou mais anos por área "
                      "de residência e município, segundo a religião ou espiritualidade, 2024"):
        page = Page()
        page.title(title)
        page.head([("População com 2 ou mais anos", 180), ("Católica", 270),
                   ("Protestante", 335)])
        rights = [240.0, 310.0, 380.0]
        for label, values in rows:
            if values:
                page.row(label, values, rights)
            else:
                page.head([(label, LEFT)])
        return [am.rows_of(page.words)], [page.text()]

    def test_a_name_on_two_lines(self):
        pages, texts = self.religion_page([
            ("Uíge", [400, 250, 150]), ("Municípios", None), ("Puri", [100, 60, 40]),
            ("Maquela do", [200, 120, 80]), ("Zombo", None), ("Damba", [100, 70, 30])])
        rep = am.Report("Uige")
        rep.new = [("Puri", 105, 50, 55), ("Maquela do Zombo", 210, 100, 110),
                   ("Damba", 105, 50, 55)]
        rows = am.read_table(rep, "religion", am.TABLES["religion"], pages, texts)
        self.assertEqual([label for label, _ in rows],
                         ["Uíge", "Puri", "Maquela do Zombo", "Damba"])
        got = am.municipalities(rep, "religion", rows)
        self.assertEqual(set(got), {"puri", "maqueladozombo", "damba"})
        self.assertEqual(dict(rep.refusals["religion"]), {})

    def test_a_missing_row_withdraws_what_is_said_of_communes(self):
        rep = am.Report("Uige")
        rep.new = [("Puri", 105, 50, 55), ("Maquela do Zombo", 210, 100, 110),
                   ("Damba", 105, 50, 55)]
        rows = [("Uíge", {"TOTAL": 400}), ("Puri", {"TOTAL": 100}),
                ("Maquela do", {"TOTAL": 200}), ("Damba", {"TOTAL": 100})]
        got = am.municipalities(rep, "religion", rows)
        self.assertEqual(set(got), {"damba"})
        self.assertEqual(rep.refusals["religion"]["puri"], ("unsure",))
        note = am.reason_note(rep, "religion", "Puri", ("unsure",), ["Puri"], "it stood")
        self.assertEqual(note, "The 2024 census prints religions for the municipalities created "
                               "in 2024 (its report for Uíge province); these figures are not "
                               "shown for Puri as it stood under Lei n.º 18/16.")

    def test_a_table_printed_without_some_answers(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        # Only the Catholics of each row printed: three fifths of every total.
        rep.tables["religion"] = [(label, {"TOTAL": v["TOTAL"], "Catholic": v["Catholic"]})
                                  for label, v in rep.tables["religion"]]
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        dembos = next(r for r in records if r["name"] == "Dembos-Quibaxe")
        self.assertEqual(dembos["religion"]["note"],
                         "The 2024 census's report for Bengo province prints its table of "
                         "religions by municipality (Quadro 7.1) with 1 of the census's 21 "
                         "answers, which account for 60% of the province's people aged 2 and "
                         "over; the other 20 (Bom Deus Church, Islam, Animist, Judaism, "
                         "Protestant, Universal Church of the Kingdom of God, New Apostolic, the "
                         "Assemblies of God, Tocoist, Kimbanguist, Josafat Church, Methodist, "
                         "Evangelical, Adventist, Baptist, Jehovah's Witnesses, the Mensagem dos "
                         "Últimos Tempos Church, no religion, another religion and no answer) "
                         "are not printed by municipality, so the religion figures for Dembos as "
                         "it stood under Lei n.º 18/16 are not shown.")
        self.assertIsInstance(dembos["ethnicity"], list)
        # The note cites the table it speaks of.
        (cited,) = dembos["sources"]
        self.assertTrue(cited["field"].endswith("/religion note"))
        self.assertIn("7.1", cited["name"])

    def test_province_total_printed_elsewhere(self):
        pages, texts = report_pages()
        # Quadro 10 without the province's row, Quadro 8 with it.
        new = Page()
        new.title("Quadro 10 - População residente por município, segundo o sexo, Censo 2024")
        new.head([("Total Homens Mulheres", 250)])
        r3 = [260.0, 320.0, 380.0]
        for n in NEW:
            new.row(n[0], list(n[1:]), r3)
        area = Page()
        area.title("Quadro 8 - População residente por área de residência, segundo o sexo, 2024")
        area.head([("Total Homens Mulheres", 250)])
        area.row("Bengo", [488_978, 241_953, 247_025], r3)
        area.row("Urbana", [300_000, 150_000, 150_000], r3)
        pages[0], texts[0] = am.rows_of(new.words), new.text()
        pages.insert(0, am.rows_of(area.words))
        texts.insert(0, area.text())
        rep = am.read_report("Bengo", pages, texts)
        self.assertEqual((rep.province, rep.total), ("Bengo", (488_978, 241_953, 247_025)))
        self.assertEqual(rep.quadros["total"], "8")
        records, _ = am.build([rep], ADMIN1, ADMIN2)
        bengo = next(r for r in records if r["level"] == "admin1")
        self.assertEqual(bengo["population"]["value"], 488_978)
        self.assertIn("Quadros 8 and 1.7", bengo["sources"][0]["name"])

    def test_a_row_that_holds_the_next_municipality(self):
        # Uíge's Quadro 1.5 (run e36dafd, pages 73-74): Nsosso's row counts
        # Nsosso and Vista Alegre together, its commune Nsosso its residents,
        # and Vista Alegre's communes follow under no row of their own.
        rep = am.Report("Uige")
        rep.new = [("Damba", 59_745, 29_000, 30_745), ("Nsosso", 33_933, 16_000, 17_933),
                   ("Vista Alegre", 24_277, 12_000, 12_277), ("Lucunga", 14_832, 7_000, 7_832)]
        rows = [(label, {"TOTAL": total}) for label, total in (
            ("Uíge", 132_787), ("Damba", 59_745), ("Damba", 37_098), ("Camatambo", 4_801),
            ("Lêmboa", 4_332), ("Petecusso", 13_515), ("Nsosso", 58_210), ("Nsosso", 33_933),
            ("Vista Alegre", 17_106), ("Cambamba", 7_171), ("Lucunga", 14_832),
            ("Lucunga", 14_832))]
        got = am.municipalities(rep, "age_other", rows)
        self.assertEqual({k: v["TOTAL"] for k, v in got.items()},
                         {"damba": 59_745, "nsosso": 33_933, "vistaalegre": 24_277,
                          "lucunga": 14_832})
        self.assertEqual(rep.patched["age_other"], {"nsosso": ("communes", 58_210, 33_933),
                                                    "vistaalegre": ("namesake", 17_106, 24_277)})

    def test_census_labels_in_notes(self):
        self.assertEqual(am.shown_name("Boa Entrada(Cadá)"), "Boa Entrada (Cadá)")
        self.assertEqual(am.shown_name("Gangula(Kuvu)"), "Gangula (Kuvu)")
        self.assertEqual(am.shown_name("Milunga (Ex. Santa Cruz)"), "Milunga (ex-Santa Cruz)")
        self.assertEqual(am.shown_name("Cacongo(ex_Lândana)"), "Cacongo (ex-Lândana)")


if __name__ == "__main__":
    unittest.main()
