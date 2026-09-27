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


class IrelandAges(unittest.TestCase):
    def test_bands(self):
        from scripts.fetch_census.ireland_age import band
        self.assertEqual(band("Age 20-24"), (20, 24))
        self.assertEqual(band("Age 85 and over"), (85, None))


if __name__ == "__main__":
    unittest.main()
