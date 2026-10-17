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


def report_pages():
    pages = sex_pages()
    pages += composition_pages("Quadro 6.1 - População de 2 ou mais anos, segundo grupos "
                               "étnicos ou tribos, 2024", ["Quicongo", "Quimbundo"],
                               ["Não sabe", "Outra Etnia"], ethnic)
    pages += language_pages()
    pages.append(religion_page())
    pages += age_pages()
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
        self.assertTrue(16 < dembos["median_age"]["value"] < 30)
        dande = by[("admin2", "Dande")]
        self.assertEqual(dande["population"]["value"], 418_274)
        self.assertIn("Lei n.º 18/16", dande["language_note"])

    def test_not_described_polygons_say_why(self):
        admin2 = ADMIN2 + [{"id": "91424787B4488869677577", "name": "Pango-Aluquem",
                            "parent": "N"}]
        records, _ = am.build([], ADMIN1, admin2)
        pango = next(r for r in records if r["name"] == "Pango-Aluquem")
        self.assertIn("39%", pango["ethnicity"]["note"])
        self.assertNotIn("value", pango["population"])


class National(unittest.TestCase):
    def test_disagreement_is_found(self):
        pages, texts = report_pages()
        rep = am.read_report("Bengo", pages, texts)
        total = rep.tables["ethnicity"][0][1]
        national = [{"name": "Bengo", "ethnicity": [
            {"group": "Bakongo", "pct": 1.0, "count": total["Bakongo"]},
            {"group": "Ambundu", "pct": 1.0, "count": total["Ambundu"] + 5_000}]}]
        problems = am.compare_national([rep], national)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][:2], ("Bengo", "ethnicity"))
        self.assertIn("Ambundu", problems[0][2])
        # The field is then left out of the province's polygons, and the rest kept.
        records, _ = am.build([rep], ADMIN1, ADMIN2, {("Bengo", "ethnicity")})
        dande = next(r for r in records if r["name"] == "Dande")
        self.assertNotIsInstance(dande["ethnicity"], list)
        self.assertIsInstance(dande["religion"], list)

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


if __name__ == "__main__":
    unittest.main()
