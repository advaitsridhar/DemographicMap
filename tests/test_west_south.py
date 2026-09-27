"""Offline tests for the west and south of Europe's readers (no network)."""

from __future__ import annotations

import unittest
from collections import Counter

# ISTAT 2015, Tavola 1 (family block), as the workbook prints it: region, then
# only/mainly Italian, only/mainly dialect, both, other language, other.
PCT = [
    ("Piemonte", "61.4", "7.8", "24.4", "5.9", "0.3"),
    ("Valle d'Aosta/Vallée d'Aoste", "64.1", "3.2", "16.6", "14.3", "1.2"),
    ("Liguria", "70.1", "8.2", "15.2", "5.8", "0.2"),
    ("Lombardia", "59.8", "5.6", "26.1", "7.5", "0.4"),
    ("Trentino-Alto Adige", "28.2", "38.4", "16.4", "16.1", "0.4"),
    ("Bolzano/Bozen", "23.3", "47.2", "7.7", "21.5", "-"),
    ("Trento", "33", "30.1", "24.8", "10.8", "0.8"),
    ("Veneto", "28.5", "30.6", "31.4", "9", "0.3"),
    ("Friuli-Venezia Giulia", "40.9", "9.9", "24.7", "23.9", "0.1"),
    ("Emilia-Romagna", "55.6", "6.5", "27.5", "9.4", "0.6"),
    ("Toscana", "74.9", "2.3", "15.1", "6.8", "0.4"),
    ("Umbria", "45.2", "14.9", "30.4", "8.1", "0.7"),
    ("Marche", "35.5", "16.3", "40", "7.5", "0.1"),
    ("Lazio", "59.2", "7.3", "25.5", "7.1", "0.1"),
    ("Abruzzo", "34.7", "13.8", "44.5", "6.1", "0.3"),
    ("Molise", "38.1", "18.8", "37.9", "4.3", "0.2"),
    ("Campania", "20.7", "26.3", "48.9", "3.2", "0.3"),
    ("Puglia", "34.5", "15.8", "46.6", "2", "0.3"),
    ("Basilicata", "27.5", "18.5", "50.9", "2", "0.2"),
    ("Calabria", "25.3", "24.1", "44.5", "4.5", "0.5"),
    ("Sicilia", "26.6", "25.5", "43.3", "3.6", "0.1"),
    ("Sardegna", "52.1", "0.6", "31.5", "15", "0.2"),
    ("Italia", "45.9", "14.1", "32.2", "6.9", "0.3"),
]
KILO = [
    ("Piemonte", "4161", "2556", "323", "1014", "247", "11"),
    ("Valle d'Aosta/Vallée d'Aoste", "120", "77", "4", "20", "17", "1"),
    ("Liguria", "1498", "1051", "123", "228", "87", "3"),
    ("Lombardia", "9395", "5619", "523", "2453", "702", "33"),
    ("Trentino-Alto Adige", "982", "277", "377", "161", "158", "4"),
    ("Bolzano/Bozen", "481", "112", "227", "37", "103", "-"),
    ("Trento", "500", "165", "150", "124", "54", "4"),
    ("Veneto", "4619", "1318", "1411", "1449", "416", "13"),
    ("Friuli-Venezia Giulia", "1155", "472", "114", "285", "276", "1"),
    ("Emilia-Romagna", "4186", "2325", "271", "1151", "395", "27"),
    ("Toscana", "3546", "2657", "81", "534", "242", "14"),
    ("Umbria", "844", "382", "126", "256", "68", "6"),
    ("Marche", "1461", "518", "238", "584", "110", "1"),
    ("Lazio", "5543", "3282", "406", "1416", "391", "6"),
    ("Abruzzo", "1259", "437", "174", "560", "77", "4"),
    ("Molise", "298", "114", "56", "113", "13", "0"),
    ("Campania", "5514", "1140", "1448", "2697", "176", "18"),
    ("Puglia", "3865", "1334", "613", "1800", "78", "10"),
    ("Basilicata", "548", "151", "102", "279", "11", "1"),
    ("Calabria", "1866", "473", "449", "830", "85", "10"),
    ("Sicilia", "4791", "1275", "1222", "2073", "171", "5"),
    ("Sardegna", "1580", "823", "9", "498", "236", "3"),
    ("Italia", "57230", "26282", "8069", "18402", "3955", "171"),
]
HEAD = ["Solo o prevalentemente italiano", "Solo o prevalentemente dialetto",
        "Sia italiano che dialetto", "Altra lingua", "Altro"]


def tav1() -> list[list[str]]:
    return ([["Tavola 1. Persone di 6 anni e più"], ["(per 100 persone)"],
             ["REGIONI", "In famiglia", "", "", "", "", "", "Con amici"],
             [""] + HEAD + ["", "Solo o prevalentemente italiano"]]
            + [list(r) + ["", "1"] for r in PCT] + [['Fonte: Indagine "I cittadini"']])


def tav1_segue() -> list[list[str]]:
    return ([["Tavola 1 (segue)"], ["(dati in migliaia)"],
             ["REGIONI", "", "In famiglia"],
             ["", "Persone di 6 anni e più"] + HEAD + ["", "Solo o prevalentemente italiano"]]
            + [list(r) + ["", "1"] for r in KILO] + [['Fonte: Indagine "I cittadini"']])


class ItalyLanguageSurvey(unittest.TestCase):
    def setUp(self):
        from scripts.fetch_census import italy_language_survey as m
        self.m = m
        self.pct = m.read_sheet(tav1(), with_total=False)
        self.kilo = m.read_sheet(tav1_segue(), with_total=True)

    def test_reads_every_region_under_the_map_names(self):
        self.assertEqual(len(self.kilo), 23)
        self.assertIn("Valle d'Aosta", self.kilo)
        self.assertIn("Friuli Venezia Giulia", self.kilo)
        self.assertEqual(self.kilo["Bolzano/Bozen"]["Altro"], 0.0)

    def test_the_published_tables_pass_the_checks(self):
        self.m.check(self.pct, self.kilo)

    def test_a_region_that_does_not_add_up_stops_the_run(self):
        self.kilo["Lazio"]["Altra lingua"] += 300
        with self.assertRaises(SystemExit):
            self.m.check(self.pct, self.kilo)

    def test_composition_carries_the_unanswered_and_the_german_dialect(self):
        rows = self.m.composition(982000, self.pct["Trentino-Alto Adige"], "Trentino-Alto Adige")
        groups = {r["group"]: r["pct"] for r in rows}
        self.assertEqual(groups["Local dialect (Italian or German)"], 38.4)
        self.assertNotIn("Italian dialects", groups)
        self.assertAlmostEqual(groups["Not stated"], 0.5, places=1)
        self.assertAlmostEqual(sum(groups.values()), 100.0, places=1)
        sicily = {r["group"] for r in self.m.composition(4791000, self.pct["Sicilia"], "Sicilia")}
        self.assertIn("Italian dialects", sicily)

    def test_every_label_is_placed_in_the_group_tree(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import group_tree
        labels = [english for _, english in self.m.CATEGORIES] + [self.m.MIXED_DIALECT,
                                                                   self.m.NOT_STATED]
        for label in labels:
            self.assertIsNotNone(group_tree.parent_of("language", label), label)


class UkShares(unittest.TestCase):
    def test_largest_remainder_makes_a_hundred_without_moving_a_share_a_tenth(self):
        from scripts.fetch_census.uk_nomis import to_tenths
        from scripts.fetch_census._shared import shares
        counts = {"English": 87544, "Polish": 433, "Arabic": 264}
        counts.update({f"Language {i}": 12 + i % 5 for i in range(70)})
        total = sum(counts.values())
        rounded = shares(counts, total=total)
        self.assertLess(sum(r["pct"] for r in rounded), 99.6)
        fixed = to_tenths(rounded, total)
        self.assertAlmostEqual(sum(r["pct"] for r in fixed), 100.0, places=6)
        for row in fixed:
            self.assertLess(abs(row["pct"] - 100 * row["count"] / total), 0.1)

    def test_a_real_shortfall_is_kept(self):
        from scripts.fetch_census.uk_nomis import to_tenths
        rows = [{"group": "A", "pct": 60.0, "count": 600}, {"group": "B", "pct": 30.0, "count": 300}]
        self.assertAlmostEqual(sum(r["pct"] for r in to_tenths(rows, 1000)), 90.0)


class SpainAges(unittest.TestCase):
    @staticmethod
    def series(sex, age_var, age_label, code, province, value, date="2026-01-01T00:00:00"):
        return {"MetaData": [
            {"T3_Variable": "Sexo", "Nombre": sex},
            {"T3_Variable": age_var, "Nombre": age_label, "Codigo": code},
            {"T3_Variable": "Provincias", "Nombre": "x", "Codigo": province}],
            "Data": [{"Fecha": date, "Valor": value}]}

    def test_open_top_class_is_read_whatever_its_wording(self):
        from unittest import mock
        from scripts.fetch_census import spain_italy_age as m
        payload = []
        provinces = [f"{i:02d}" for i in range(1, 53)]
        for p in provinces + ["00"]:
            weight = 52 if p == "00" else 1
            for sex, n in (("Hombres", 10), ("Mujeres", 12)):
                payload.append(self.series(sex, "Valores simples de edad", "0 años", "Y0", p,
                                           n * weight))
                payload.append(self.series(sex, "Totales de edad", "100 años y más", "", p,
                                           1 * weight))
                payload.append(self.series(sex, "Totales de edad", "Todas las edades", "", p,
                                           (n + 1) * weight))
            payload.append(self.series("Total", "Totales de edad", "Todas las edades", "", p,
                                       24 * weight))
        with mock.patch.object(m, "ine_series", return_value=payload):
            out, year = m.spain()
        self.assertEqual(year, 2026)
        self.assertEqual(out["35"]["ages"][100], 2)
        self.assertEqual(out["35"]["men"] + out["35"]["women"], 24)


class UkMidYear(unittest.TestCase):
    def test_successors_add_age_by_age(self):
        from scripts.fetch_census.uk_mye import combine
        a = {"name": "Cumberland", "year": 2025, "men": 2, "women": 3,
             "male": Counter({30: 2}), "female": Counter({40: 3})}
        b = {"name": "Westmorland and Furness", "year": 2025, "men": 1, "women": 1,
             "male": Counter({30: 1}), "female": Counter({50: 1})}
        whole = combine([a, b], "Cumbria")
        self.assertEqual(whole["male"][30], 3)
        self.assertEqual(whole["men"] + whole["women"], 7)
        b["year"] = 2024
        with self.assertRaises(SystemExit):
            combine([a, b], "Cumbria")


class BasqueLanguage(unittest.TestCase):
    def table(self):
        rows = {"01": (300, 60, 200, 30, 10), "48": (1000, 150, 700, 100, 50),
                "20": (700, 250, 300, 120, 30)}
        cells = []
        for code, (total, *langs) in rows.items():
            cells.append(({"territorio histórico": (code, code), "lengua": ("10", "Total")}, total))
            for lang, value in zip(("20", "30", "40", "50"), langs):
                cells.append(({"territorio histórico": (code, code), "lengua": (lang, lang)}, value))
        whole = [sum(r[i] for r in rows.values()) for i in range(5)]
        for lang, value in zip(("10", "20", "30", "40", "50"), whole):
            cells.append(({"territorio histórico": ("00", "CAPV"), "lengua": (lang, lang)}, value))
        from scripts.fetch_census import basque_language as m
        return m, m.tabulate(cells)

    def test_territories_make_the_community(self):
        m, table = self.table()
        m.check(table)
        rows = m.fields(table["20"])["language"]
        self.assertEqual({r["group"] for r in rows},
                         {"Basque", "Spanish", "Basque and Spanish", "Other language"})
        table["01"]["20"] += 5
        with self.assertRaises(SystemExit):
            m.check(table)


EULP_2023 = {
    "id": ["YEAR", "CAT", "LAN_ISO", "CONCEPT"], "size": [1, 1, 12, 1],
    "dimension": {
        "YEAR": {"category": {"index": ["2023"]}},
        "CAT": {"category": {"index": ["TOTAL"]}},
        "LAN_ISO": {"category": {"index": [
            "CA", "ES", "CA_ES", "OC_ARANESE", "CA_OTHER_LANG", "ES_OTHER_LANG",
            "CA_ES_OTHER_LANG", "AR", "OTHER_LANG", "OTHER_COMB_LANG", "_U", "TOTAL"]}},
        "CONCEPT": {"category": {"index": ["POP_YGE15T"]}}},
    "value": [2211.1, 3154.7, 636.5, 1.4, 50.9, 275.1, 23.2, 74.2, 233.7, 24.9, 99.4, 6785.1],
}


class CataloniaLanguage(unittest.TestCase):
    def test_habitual_language_as_published(self):
        from scripts.fetch_census.spain_language_survey import catalonia
        rows = {r["group"]: r["pct"] for r in catalonia(EULP_2023)["language"]}
        self.assertEqual(rows["Spanish"], 46.5)
        self.assertEqual(rows["Catalan"], 32.6)
        self.assertIn("Not stated", rows)
        self.assertAlmostEqual(sum(rows.values()), 100.0, delta=0.3)

    def test_a_short_table_stops_the_run(self):
        import copy
        from scripts.fetch_census.spain_language_survey import catalonia
        bad = copy.deepcopy(EULP_2023)
        bad["value"][0] -= 50
        with self.assertRaises(SystemExit):
            catalonia(bad)


MONACO_TEXT = """
Number of
residents Share
Monte-Carlo 8,318 21.4%
La Rousse 7,992 20.6%
La Condamine 5,446 14.0%
Jardin Exotique 4,997 12.9%
Les Moneghetti 4,498 11.6%
Fontvieille 4,297 11.1%
Larvotto 2,287 5.9%
Monaco-Ville 1,022 2.6%
Total 38,857 100%
Men Women Tot al % Men % Women % Total
16 y/o and under 2,966 2,920 5,885 15.5% 14.8% 15.1%
17 to 24 y/o 1,386 1,372 2,758 7.2% 7.0% 7.1%
25 to 34 y/o 1,922 1,936 3,858 10.0% 9.8% 9.9%
35 to 44 y/o 2,067 2,304 4,371 10.8% 11.7% 11.2%
45 to 54 y/o 2,482 2,614 5,096 13.0% 13.2% 13.1%
55 to 64 y/o 3,318 2,980 6,298 17.3% 15.1% 16.2%
65 to 74 y/o 2,408 2,393 4,801 12.6% 12.1% 12.4%
75 y/o and over 2,578 3,212 5,790 13.5% 16.3% 14.9%
Total 19,127 19,730 38,857 100% 100% 100%
"""


class Microstates(unittest.TestCase):
    def test_monaco_tables(self):
        from scripts.fetch_census.microstates import monaco
        out = monaco(MONACO_TEXT)
        self.assertEqual(out["districts"]["Les Moneghetti"], 4498)
        self.assertEqual((out["men"], out["women"]), (19127, 19730))
        self.assertAlmostEqual(out["median"], 50.0, delta=0.1)
        with self.assertRaises(SystemExit):
            monaco(MONACO_TEXT.replace("Larvotto 2,287", "Larvotto 2,288"))

    def test_san_marino_castelli(self):
        from scripts.fetch_census.microstates import san_marino
        rows = [["Popolazione Residente"], ["", "", "2023", "2024", "2025"]]
        castelli = {"San Marino": (2036, 2122), "Acquaviva": (1083, 1064),
                    "Borgo Maggiore": (3518, 3488), "Chiesanuova": (601, 591),
                    "Domagnano": (1748, 1865), "Faetano": (606, 610), "Fiorentino": (1273, 1315),
                    "Montegiardino": (492, 495), "Serravalle": (5630, 5635)}
        for name, (m, f) in castelli.items():
            rows += [[name, "M", "0", "0", str(m)], ["", "F", "0", "0", str(f)],
                     ["", "Total", "0", "0", str(m + f)]]
        men = sum(m for m, _ in castelli.values())
        women = sum(f for _, f in castelli.values())
        rows += [["Totale Generale", "M", "0", "0", str(men)], ["", "F", "0", "0", str(women)],
                 ["", "Totale", "0", "0", str(men + women)]]
        year, out = san_marino(rows)
        self.assertEqual(year, 2025)
        self.assertEqual(out["San Marino"]["total"], 4158)
        rows[-1][4] = str(men + women + 1)
        with self.assertRaises(SystemExit):
            san_marino(rows)

    def test_andorra_parishes_from_settlements(self):
        from scripts.fetch_census.microstates import andorra
        feats = [{"attributes": {"parroquia": p, "pob_2024": 10, "pob_2025": n}}
                 for p, n in (("Encamp", 5), ("Encamp", 7), ("Canillo", 3),
                              ("Escaldes-Engordany", 4), ("Andorra la Vella", 9),
                              ("La Massana", 2), ("Ordino", 1), ("Sant Julà de Lòria", 6))]
        year, parishes, n = andorra(feats)
        self.assertEqual((year, parishes["Encamp"], parishes["Sant Julià de Lòria"]), (2025, 12, 6))
        feats.append({"attributes": {"parroquia": "Elsewhere", "pob_2025": 1}})
        with self.assertRaises(SystemExit):
            andorra(feats)


class MaltaLanguage(unittest.TestCase):
    def test_runs_of_dashes_are_that_many_empty_cells(self):
        from scripts.fetch_census.malta_census import language_row
        self.assertEqual(language_row("Ħal Luqa 5,794 140 11 \u2010\u2010 9 9 5,963"),
                         ("Ħal Luqa", [5794.0, 140.0, 11.0, 0.0, 0.0, 9.0, 9.0, 5963.0]))
        name, values = language_row("L\u2010Imdina 120 38 \u2010\u2010\u2010\u2010\u2010 158")
        self.assertEqual((name, sum(values[:-1]), values[-1]), ("L-Imdina", 158.0, 158.0))
        self.assertIsNone(language_row("District and locality Maltese English Italian"))


class IrelandLanguage(unittest.TestCase):
    def test_the_complement_makes_the_population_aged_3(self):
        from scripts.fetch_census.ireland import home_language, ENGLISH_OR_IRISH
        rows = home_language({"Polish": 10, "Spanish": 5, "French": 3,
                              "Other (incl. not stated)": 12, "Total": 30}, 1000, "x")
        self.assertEqual(rows[ENGLISH_OR_IRISH], 970)
        self.assertEqual(sum(rows.values()), 1000)
        with self.assertRaises(SystemExit):
            home_language({"Polish": 10, "Total": 30}, 1000, "x")
        with self.assertRaises(SystemExit):
            home_language({"Polish": 30, "Total": 30}, 20, "x")

    def test_labels_are_placed(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import group_tree
        from scripts.fetch_census.ireland import LANGUAGE_LABELS, ENGLISH_OR_IRISH
        for label in list(LANGUAGE_LABELS.values()) + [ENGLISH_OR_IRISH]:
            self.assertIsNotNone(group_tree.parent_of("language", label), label)


class IrelandAges(unittest.TestCase):
    def test_bands(self):
        from scripts.fetch_census.ireland_age import band
        self.assertEqual(band("Age 20-24"), (20, 24))
        self.assertEqual(band("Age 85 and over"), (85, None))


if __name__ == "__main__":
    unittest.main()
