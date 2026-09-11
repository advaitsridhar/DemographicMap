"""Peru's profile book prints figures with spaces for thousands, and two of
its religion tables in a font pdfplumber reads one letter at a time, so rows
are read from word positions. The row fixtures are the runner's actual boxes
for one row of each table page; the build test lays out whole synthetic
tables in the same format.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import peru  # noqa: E402

ROWS = {
    "204 total": "Total[87-102] 26[193-200] 887[202-212] 584[214-225] 22[242-249] 209[251-262] 686[263-274] 82,6[307-319] 3[340-344] 735[346-356] 682[358-369] 13,9[402-414] 444[440-451] 389[453-463] 1,7[500-508]",
    "204 rlima": "Región[87-107] Lima[109-122] 2/[124-130] 833[202-212] 189[214-225] 747[251-262] 966[263-274] 89,8[307-319] 76[349-356] 402[358-369] 9,2[405-414] 659[453-463] 0,1[500-508]",
    "206 amaz": "Amazonas[87-112] 100[184-193] 40[217-223] 976[225-234] 41[260-266] 12[307-313] 2[333-336] 481[337-346] 116[376-385] 740[421-430] 241[461-470] 5[495-498] 372[500-509]",
    "239 amaz": "Amazonas[94-125] 262[187-199] 668[200-211] 178[229-240] 107[242-253] 67,8[265-278] 281[296-307] 605[309-320] 179[338-349] 874[351-362] 63,9[373-386] 1[423-427] 767[429-440] 1,0[455-464] 0,1[484-493]",
    "245 amaz": "A[94-98] m[98-103] a[103-107] z[107-110] o[110-114] n[114-117] a[117-121] s[121-124] 2[184-187] 6[187-191] 2[191-195] 6[196-200] 6[200-204] 8[204-207] 1[227-230] 9[230-234] 8[236-239] 0[239-243] 6[243-246] 7[258-262] ,5[262-267] 2[293-296] 8[296-300] 1[300-303] 6[305-309] 0[309-312] 5[312-316] 1[334-338] 4[337-341] 3[343-347] 7[347-350] 6[350-354] 5[363-366] ,1[366-372] -[396-398] 5[400-404] 4[405-409] 3[409-413] 0[413-416] -2[439-445] 7[445-448] ,4[448-454] -3[479-485] ,2[485-490]",
}


def boxed(label: str, numbers: list[float], decimals: set[int] = frozenset()) -> str:
    """A row in probe_pdf's boxes format: thousands groups 2 pt apart, cells 20 pt apart."""
    x = 90
    words = []
    for part in label.split():
        words.append(f"{part}[{x}-{x + 5 * len(part)}]")
        x += 5 * len(part) + 2
    x += 40
    for i, n in enumerate(numbers):
        text = f"{n:.1f}".replace(".", ",") if i in decimals else f"{int(n):,}".replace(",", " ")
        for group in text.split(" "):
            words.append(f"{group}[{x}-{x + 4 * len(group)}]")
            x += 4 * len(group) + 2
        x += 20
    return " ".join(words)


class RowsAreReadFromPositions(unittest.TestCase):
    def test_rows(self):
        self.assertEqual(peru.parse_row(ROWS["204 total"]),
                         (None, [26887584, 22209686, 82.6, 3735682, 13.9, 444389, 1.7]))
        self.assertEqual(peru.parse_row(ROWS["204 rlima"]),
                         ("Lima", [833189, 747966, 89.8, 76402, 9.2, 659, 0.1]))
        self.assertEqual(peru.parse_row(ROWS["206 amaz"])[1],
                         [100, 40976, 41, 12, 2481, 116, 740, 241, 5372])
        self.assertEqual(peru.parse_row(ROWS["239 amaz"])[1][3:6], [281605, 179874, 63.9])
        name, values = peru.parse_row(ROWS["245 amaz"])
        self.assertEqual(name, "Amazonas")
        self.assertEqual(values, [262668, 19806, 7.5, 281605, 14376, 5.1, -5430, -27.4, -3.2])


class FourReligionTablesAndTwoLanguageHalvesAreOneCensus(unittest.TestCase):
    def tables(self, break_total=False):
        names = list(peru.DEPARTMENTS) + ["Lima"]
        pop = {n: 100000 * (i + 1) for i, n in enumerate(names)}
        pop["Lima"] = pop["Provincia de Lima"] + pop["Región Lima"]
        rel = {n: [0.7 * pop[n], 0.2 * pop[n], 0.06 * pop[n], 0.04 * pop[n]] for n in names}
        lang = {n: [0.8 * pop[n], 0.15 * pop[n], 0.02 * pop[n]] for n in names}
        rest = {n: [0.01 * pop[n]] * 3 for n in names}
        pages = []
        # Cuadro 2.64: first half, a graphic page between, second half.
        a = ["CUADRO[262-301] Nº[304-313] 2.64[316-334]"]
        for n in names:
            t = pop[n]
            a.append(boxed(n, [t, lang[n][0], 100 * lang[n][0] / t, lang[n][1],
                              100 * lang[n][1] / t, lang[n][2], 100 * lang[n][2] / t],
                           decimals={2, 4, 6}))
        pages.append("\n".join(a))
        pages.append("GRÁFICO[100-140] Nº[142-150] II.47[152-170]")
        b = ["CUADRO[262-301] Nº[304-313] 2.64[316-334]"]
        for n in names:
            t = pop[n]
            b.append(boxed(n, [0, 0, 0, 0, 0, 0, 0, 0, t - sum(lang[n])]))
        pages.append("\n".join(b))
        for i, number in enumerate(("2.78", "2.79", "2.80", "2.81")):
            page = [f"CUADRO[262-301] Nº[304-313] {number}[316-334]"]
            for n in names:
                t = pop[n]
                c = rel[n][i]
                if break_total and n == "Puno" and number == "2.80":
                    t = t + 1000
                page.append(boxed(n, [t, c, 100 * c / t, t, c, 100 * c / t, 0, 0, 0],
                                  decimals={2, 5, 7, 8}))
            pages.append("\n".join(page))
        return peru.PAGE_BREAK.join(pages)

    def test_build(self):
        records = peru.build(self.tables())
        self.assertEqual(len(records), 26)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Ancash"]["aliases"], ["Áncash"])
        self.assertEqual(by["Cusco"]["religion"][0], {"group": "Catholic", "pct": 70.0, "count": 560000})
        self.assertEqual(by["Cusco"]["language"][0]["group"], "Spanish")
        self.assertEqual([b["group"] for b in by["Cusco"]["language"]],
                         ["Spanish", "Quechua", "Not stated", "Aymara"])
        self.assertNotIn("Lima whole", by)
        self.assertEqual(by["Municipalidad Metropolitana de Lima"]["religion_year"], 2017)

    def test_disagreeing_totals_refuse(self):
        with self.assertRaises(SystemExit):
            peru.build(self.tables(break_total=True))


if __name__ == "__main__":
    unittest.main()
