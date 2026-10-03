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


def ige_csv(values):
    head = ('"Idade","Lingua na que fala habitualmente","Medidas","CodTempo","Tempo",'
            '"CodEspazo","Espazo","DatoN","DatoT"')
    lines = [head]
    for (code, place), row in values.items():
        for language, value in row.items():
            for year in (2018, 2023):
                lines.append(f'"Total   ","{language}","Porcentaxe",{year},"{year}","{code}",'
                             f'"{code} {place}",{value},"x"')
                lines.append(f'"De 5 a 14 anos  ","{language}","Porcentaxe",{year},"{year}",'
                             f'"{code}","{code} {place}",1,"x"')
    return "\n".join(lines)


class GaliciaLanguage(unittest.TestCase):
    ROW = {"En galego sempre": 24.37, "Máis galego ca castelán": 21.86,
           "Máis castelán ca galego": 24.11, "En castelán sempre": 29.66, "Total": 100}

    def test_latest_wave_for_galicia_and_its_provinces(self):
        from scripts.fetch_census.spain_language_survey import galicia, galicia_fields
        places = {("12", "Galicia"): self.ROW, ("15", "A Coruña"): self.ROW,
                  ("27", "Lugo"): self.ROW, ("32", "Ourense"): self.ROW,
                  ("36", "Pontevedra"): self.ROW}
        year, out = galicia(ige_csv(places))
        self.assertEqual(year, 2023)
        rows = galicia_fields(out["27"], year, "Lugo")["language"]
        self.assertEqual({r["group"] for r in rows},
                         {"Galician only", "Mostly Galician", "Mostly Spanish", "Spanish only"})
        self.assertNotIn("count", rows[0])

    def test_an_undeclared_category_stops_the_run(self):
        from scripts.fetch_census.spain_language_survey import galicia
        odd = dict(self.ROW, **{"Outro caso raro": 0.0})
        places = {(c, n): odd for c, n in (("12", "Galicia"), ("15", "A Coruña"), ("27", "Lugo"),
                                             ("32", "Ourense"), ("36", "Pontevedra"))}
        with self.assertRaises(SystemExit):
            galicia(ige_csv(places))

    def test_labels_are_placed(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import group_tree
        from scripts.fetch_census.spain_language_survey import IGE_LABELS, EULP_LABELS
        for label in list(IGE_LABELS.values()) + list(EULP_LABELS.values()):
            if label in ("Other language combinations",):
                continue        # placed by shared.patch
            self.assertIsNotNone(group_tree.parent_of("language", label), label)


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

    def test_area_median_is_interpolated_within_the_five_year_group(self):
        from scripts.fetch_census.ireland_age import area_median
        # 100 people: 30 aged 0-4, 40 aged 5-9, 30 aged 10+ (open); the 50th is
        # 20 into the 40 of 5-9, so 5 + 20/40 * 5 = 7.5.
        entry = {"M": {"groups": [(0, 4, 15), (5, 9, 20), (10, None, 15)]},
                 "F": {"groups": [(0, 4, 15), (5, 9, 20), (10, None, 15)]}}
        self.assertEqual(area_median(entry), 7.5)

    def test_province_median_from_the_councils_single_years(self):
        from scripts.fetch_census.ireland_age import province_years
        from scripts.fetch_census.redatam import median_age
        a = {"M": {"years": Counter({30: 10})}, "F": {"years": Counter({30: 10})}}
        b = {"M": {"years": Counter({40: 10})}, "F": {"years": Counter({50: 10})}}
        years = province_years([a, b])
        self.assertEqual(sum(years.values()), 40)
        self.assertEqual(years[30], 20)
        self.assertLessEqual(median_age(years), 40.0)
        self.assertGreaterEqual(median_age(years), 30.0)


IRL_UNITS1 = [{"id": "C", "name": "Connacht"}, {"id": "L", "name": "Leinster"},
              {"id": "M", "name": "Munster"}, {"id": "U", "name": "Ulster"}]


class IrelandProvinces(unittest.TestCase):
    def data(self):
        areas = {"1": "Newport, Tipperary", "2": "Ballina, Mayo", "3": "Arklow, Wicklow",
                 "4": "Macroom, Cork County", "5": "Letterkenny, Donegal"}
        rel = {"1": {"Catholic": 80, "No religion": 20}, "2": {"Catholic": 90, "No religion": 10},
               "3": {"Catholic": 70, "No religion": 30}, "4": {"Catholic": 60, "No religion": 40},
               "5": {"Catholic": 50, "No religion": 50}}
        fields = {"religion": rel, "ethnicity": {c: {"White Irish": 100} for c in areas}}
        totals = {"religion": {c: 100 for c in areas}, "ethnicity": {c: 100 for c in areas}}
        language = {c: {"English or Irish only": 90, "Polish": 10} for c in areas}
        units2 = [{"id": "s1", "parent": "C", "aliases": ["Newport, Tipperary"]},
                  {"id": "s2", "parent": "C", "aliases": ["Ballina, Mayo"]},
                  {"id": "s3", "parent": "L", "aliases": ["Arklow, Wicklow"]}]
        return areas, fields, totals, language, units2

    def test_an_area_drawn_in_another_provinces_outline_is_found(self):
        from scripts.fetch_census.ireland import drawn_elsewhere
        areas, _, _, _, units2 = self.data()
        found = drawn_elsewhere(areas, units2, IRL_UNITS1)
        self.assertEqual([(e["label"], e["own"], e["drawn"]) for e in found],
                         [("Newport, Tipperary", "Munster", "Connacht")])

    def test_provinces_are_summed_by_county_not_by_outline(self):
        from scripts.fetch_census.ireland import drawn_elsewhere, province_records
        areas, fields, totals, language, units2 = self.data()
        elsewhere = drawn_elsewhere(areas, units2, IRL_UNITS1)
        out = {r["name"]: r for r in province_records(areas, fields, totals, language,
                                                      elsewhere, IRL_UNITS1)}
        munster = {g["group"]: g["count"] for g in out["Munster"]["religion"]}
        self.assertEqual(munster, {"Catholic": 140, "No religion": 60})   # Newport and Macroom
        self.assertEqual(out["Connacht"]["religion"][0]["count"], 90)     # Ballina alone
        self.assertIn("inside this province's outline; these figures leave it out",
                      out["Connacht"]["language_note"])
        self.assertIn("the census counts it in Munster", out["Munster"]["religion_note"])
        self.assertEqual(out["Munster"]["shape_id"], "M")

    def test_a_county_with_no_province_stops_the_run(self):
        from scripts.fetch_census.ireland import province_of
        self.assertEqual(province_of("Macroom, Cork County"), "Munster")
        with self.assertRaises(SystemExit):
            province_of("Somewhere, Atlantis")

    def test_the_language_note_says_non_response_is_inside(self):
        from scripts.fetch_census.ireland import LANGUAGE_NOTE
        self.assertIn("did not answer the question", LANGUAGE_NOTE)
        self.assertIn("upper bound", LANGUAGE_NOTE)


def ine_rows(sexes):
    rows = []
    for sex, ages in sexes.items():
        rows.append({"dim_3_t": sex, "dim_4_t": "Total", "valor": str(sum(ages.values()))})
        for age, n in ages.items():
            label = "Menos de 1 ano" if age == 0 else f"{age} anos"
            rows.append({"dim_3_t": sex, "dim_4_t": label, "valor": str(n)})
    return rows


class PortugalCensus(unittest.TestCase):
    AGES = {"H": {0: 1, 20: 4, 99: 1}, "M": {0: 2, 20: 3, 100: 1}}

    def ages_rows(self):
        both = Counter(self.AGES["H"]) + Counter(self.AGES["M"])
        return ine_rows({"HM": dict(both), **self.AGES})

    def test_single_years_make_the_totals(self):
        from unittest import mock
        from scripts.fetch_census import portugal_census as m
        with mock.patch.object(m, "get", return_value=self.ages_rows()):
            out = m.read_ages("0101")
        self.assertEqual((out["men"], out["women"]), (6.0, 6.0))
        self.assertEqual(out["ages"][20], 7)
        bad = self.ages_rows()
        bad[1]["valor"] = "5"
        with mock.patch.object(m, "get", return_value=bad):
            with self.assertRaises(SystemExit):
                m.read_ages("0101")

    def test_the_unanswered_are_not_stated(self):
        from unittest import mock
        from scripts.fetch_census import portugal_census as m
        rows = [{"dim_3_t": "Total", "valor": "8"}, {"dim_3_t": "Católica", "valor": "6"},
                {"dim_3_t": "Sem religião", "valor": "2"}]
        with mock.patch.object(m, "get", return_value=rows):
            religion = m.read_religion("0101")
        with mock.patch.object(m, "get", return_value=self.ages_rows()):
            ages = m.read_ages("0101")
        out = m.fields(ages, religion, "")
        groups = {g["group"]: g["count"] for g in out["religion"]}
        # 9 residents aged 15 and over, 8 of whom answered.
        self.assertEqual(groups, {"Roman Catholic": 6, "No religion": 2, "Not stated": 1})
        ages["ages"][30] += 4
        ages["women"] += 4
        groups = {g["group"]: g["count"] for g in m.fields(ages, religion, "")["religion"]}
        self.assertEqual(groups["Not stated"], 5)
        rows.append({"dim_3_t": "Seita nova", "valor": "1"})
        with mock.patch.object(m, "get", return_value=rows):
            with self.assertRaises(SystemExit):
                m.read_religion("0101")

    def test_districts_add_their_municipalities(self):
        from scripts.fetch_census import portugal_census as m
        a = {"men": 2, "women": 1, "ages": Counter({10: 2, 70: 1})}
        b = {"men": 1, "women": 3, "ages": Counter({10: 1, 40: 3})}
        ra = {"counts": {"Roman Catholic": 2}, "total": 2}
        rb = {"counts": {"Roman Catholic": 1, "No religion": 1}, "total": 2}
        ages, religion = m.district_sums([a, b], [ra, rb])
        self.assertEqual((ages["men"], ages["women"], ages["ages"][10]), (3, 4, 3))
        self.assertEqual(religion, {"counts": {"Roman Catholic": 3, "No religion": 1}, "total": 4})
        a["men"] += 1
        with self.assertRaises(SystemExit):
            m.district_sums([a, b], [ra, rb])

    def test_mean_age_reads_each_age_at_its_midpoint(self):
        from scripts.fetch_census.portugal_census import mean_age
        self.assertEqual(mean_age(Counter({0: 1, 1: 1})), 1.0)

    def site(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        return (json.loads((root / "site/data/admin1/PRT.units.json").read_text()),
                json.loads((root / "site/data/admin2/PRT.units.json").read_text()),
                root / "data/processed/portugal_census.json")

    def test_declared_polygons_are_the_ones_named(self):
        from scripts.fetch_census import portugal_census as m
        admin1, admin2, _ = self.site()
        name = {s["id"]: s["name"] for s in admin2}
        parent = {s["id"]: s.get("parent") for s in admin2}
        first = {u["id"]: u["name"] for u in admin1}
        self.assertEqual(name[m.PINNED["1507"]], "Montijo")
        self.assertEqual(name[m.PINNED["0110"]], "Ilhavo")
        self.assertEqual(name[m.PINNED["1810"]], "Oliveira de Frades")
        for sid, code in m.SECOND_PARTS.items():
            if sid in name:                    # gone once make_redrawn merges it
                self.assertEqual(name[sid], name[m.PINNED[code]])
        for sid in m.UNIDENTIFIED:
            self.assertEqual(name[sid], "Oliveira de Frades")
            self.assertEqual(first[parent[sid]], "VISEU")
        rec = m.unidentified_record("x", "Oliveira de Frades", "why")
        self.assertEqual(rec["population"]["note"], "why")
        self.assertNotIn("value", rec["population"])

    def test_binding_and_the_municipalities_drawn_under_another_district(self):
        import json
        from scripts.fetch_census import portugal_census as m
        admin1, admin2, processed = self.site()
        if not processed.exists():
            self.skipTest("portugal_census.json needs a network run to exist")
        rows = json.loads(processed.read_text())
        names = {r["codes"]["dico"]: (r["aliases"][0] if r["aliases"] else r["name"])
                 for r in rows if r["level"] == "admin2" and "dico" in (r.get("codes") or {})}
        bound, district = m.bind_municipalities(names, admin1, admin2)
        self.assertEqual(len(bound), 308)
        elsewhere = m.drawn_elsewhere(bound, names, admin1, admin2, district)
        moved = sorted(line.split(":")[0] for line in elsewhere["lines"])
        self.assertEqual(moved, ["Espinho", "Mesão Frio", "Oliveira de Frades", "Sardoal",
                                 "Tábua"])
        aveiro = next(u["id"] for u in admin1 if u["name"] == "AVEIRO")
        note = m.district_note(elsewhere["out"][aveiro], elsewhere["in"][aveiro])
        self.assertIn("Espinho under Porto", note)
        self.assertIn("Oliveira de Frades (INE's Viseu) inside this district's outline", note)
        self.assertEqual(m.district_note([], []), "")


class PortugalDistrictsAreNotNuts3(unittest.TestCase):
    """Beja, Braganca and Coimbra are not NUTS-3 regions, and Eurostat's
    figures for the regions that share their outlines must not land on them."""

    def test_no_wrong_region_on_a_district(self):
        import json
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(root / "scripts"))
        import nuts_crosswalk
        codes = ("PT11E", "PT192", "PT1C2")
        if not all(c in nuts_crosswalk.DECIDED for c in codes):
            self.skipTest("the DECIDED entries arrive with the west_south shared.patch")
        crosswalk = json.loads((root / "data/processed/nuts_crosswalk.json").read_text())
        for code in codes:
            self.assertIn("refused", crosswalk.get(code, {}), code)
        path = root / "data/processed/eurostat_nuts3.json"
        if path.exists():
            placed = {r["codes"]["nuts"] for r in json.loads(path.read_text())
                      if r.get("country") == "PRT" and r.get("match_by") == "shape_id"}
            self.assertFalse(placed & set(codes),
                             "re-run scripts.fetch_census.eurostat --level nuts3")


MALTA_T53 = [
    ["TABLE 5.3"],
    ["District and locality", "Roman Catholicism", "Islam", "Orthodoxy", "Hinduism",
     "Church of England", "Protestantism", "Buddhism", "Judaism", "Other religious groups",
     "No religious affiliation", "Total"],
    ["Valletta", 4000, 50, 20, 10, 5, 5, 0, 0, 10, 400, 4500],
    ["L-Imdina", 200, None, None, None, None, None, None, None, None, 20, 220],
    ["MALTA", 4200, 50, 20, 10, 5, 5, 0, 0, 10, 420, 4720],
]


class MaltaTables(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        from scripts.fetch_census import malta_census as m
        self.m = m
        self.patch = mock.patch.object(m, "LOCALITIES", {"Valletta": "Valletta",
                                                         "L-Imdina": "Mdina"})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_religion_rows_make_their_totals_and_malta(self):
        out = self.m.religion_table([list(r) for r in MALTA_T53])
        self.assertEqual(out["L-Imdina"]["counts"]["No religion"], 20)
        self.assertEqual(out["Valletta"]["total"], 4500)
        bad = [list(r) for r in MALTA_T53]
        bad[2][1] = 4001
        with self.assertRaises(SystemExit):
            self.m.religion_table(bad)

    def test_racial_origin_rows(self):
        from unittest import mock
        page = ("TABLE 4.3. Total population by racial origin and locality\n"
                "Valletta 5,000 300 100 200 50 350 6,000\n"
                "L-Imdina 200 5 2 1 0 2 210\n"
                "MALTA 5,200 305 102 201 50 352 6,210\n")
        with mock.patch.object(self.m, "NATIONAL", 6210):
            out = self.m.racial_origin_table([page])
        self.assertEqual(out["Valletta"]["counts"]["More than one racial origin"], 350)
        with mock.patch.object(self.m, "NATIONAL", 6210), self.assertRaises(SystemExit):
            self.m.racial_origin_table([page.replace("6,000", "6,001")])

    def test_single_years_and_the_nso_mean(self):
        sheet = [["Age", "Males", "Females", "Total", None, "Age", "Males", "Females", "Total"],
                 ["Less than 1", 1, 1, 2, None, "50", 1, "-", 1],
                 ["0-9", 1, 1, 2, None, "Over 89", 0, 1, 1],
                 ["Total", 2, 2, 4, None, None, None, None, None]]
        out = self.m.single_years(sheet, "x")
        self.assertEqual(out["ages"], Counter({0: 2, 50: 1, 90: 1}))
        self.assertEqual(self.m.mean_age(out["ages"]), 35.0)       # completed years as they stand
        sheet[3][1] = 3
        with self.assertRaises(SystemExit):
            self.m.single_years(sheet, "x")

    def test_racial_origin_labels_are_placed(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import group_tree
        for label in self.m.RACIAL_ORIGINS:
            if label == "More than one racial origin" and \
                    group_tree.parent_of("ethnicity", label) is None:
                continue        # placed by shared.patch
            self.assertIsNotNone(group_tree.parent_of("ethnicity", label), label)


class UkMidYearSeries(unittest.TestCase):
    def test_a_figure_far_from_mid_2021_carries_its_series(self):
        from scripts.fetch_census.uk_mye import series_note
        city = {2021: 8689, 2022: 12020, 2023: 14514, 2024: 15497, 2025: 15631}
        note = series_note("City of London", "Office for National Statistics", city, 2025)
        self.assertIn("8,689 (2021)", note)
        self.assertIn("15,631 (2025)", note)
        self.assertIn("1.80 times", note)
        self.assertEqual(series_note("Westminster", "x", {2021: 205759, 2025: 212367}, 2025), "")


def nomis_obs(area, code, label, value):
    return {"geography": {"geogcode": area, "description": area},
            "c2021_mlang_94": {"value": code, "description": label},
            "obs_value": {"value": value}}


class UkNomisTruncated(unittest.TestCase):
    def test_a_truncated_table_is_read_again_in_parts_by_category(self):
        from unittest import mock
        from scripts.fetch_census import uk_nomis as m
        cats = [(0, "Total", 10), (1, "English", 8), (2, "Polish", 2)]
        full = [nomis_obs(a, c, label, v) for a in ("E1", "E2") for c, label, v in cats]
        calls = []

        def answer(url, timeout=0):
            calls.append(url)
            if "c2021_mlang_94=" not in url:
                return {"header": {"truncated": "true"}, "obs": full[:4]}
            wanted = {int(c) for c in url.rsplit("=", 1)[1].split(",")}
            return {"header": {"truncated": "false"},
                    "obs": [o for o in full if o["c2021_mlang_94"]["value"] in wanted]}
        with mock.patch.object(m, "http_json", side_effect=answer), \
                mock.patch.object(m, "CATEGORY_PARTS", 2):
            out = m.fetch_table("NM_2043_1", None, "TYPE154")
        self.assertEqual(out["E2"]["total"], 10)
        self.assertEqual(out["E2"]["counts"], {"English": 8, "Polish": 2})
        self.assertEqual(len(calls), 3)

    def test_a_part_still_truncated_stops_the_run(self):
        from unittest import mock
        from scripts.fetch_census import uk_nomis as m
        page = {"header": {"truncated": "true"},
                "obs": [nomis_obs("E1", 0, "Total", 1), nomis_obs("E1", 1, "English", 1)]}
        with mock.patch.object(m, "http_json", return_value=page):
            with self.assertRaises(SystemExit):
                m.fetch_table("NM_2043_1", None, "TYPE154")


class UkNomisComplete(unittest.TestCase):
    def test_a_table_read_short_stops_the_run(self):
        from scripts.fetch_census.uk_nomis import check_complete
        full = {"E1": {"counts": {"a": 1}}, "E2": {"counts": {"a": 1}}}
        check_complete({"ethnicity": full, "religion": full, "language": full})
        with self.assertRaises(SystemExit):
            check_complete({"ethnicity": full, "religion": full,
                            "language": {"E1": {"counts": {"a": 1}}}})


class MonacoDistrictOrder(unittest.TestCase):
    def test_the_report_must_still_say_what_the_note_rests_on(self):
        from scripts.fetch_census.microstates import check_district_order
        text = ("Note: The districts are those defined by Sovereign Order No. 4,481 of 13\n"
                "September 2013. Ravin Sainte-Dévote has been incorporated into the district "
                "of Les\nMoneghetti. 35,352 38,857")
        check_district_order(text)
        with self.assertRaises(SystemExit):
            check_district_order(text.replace("4,481", "4,482"))


PROSPETTO = """PROSPETTO B. FAMIGLIE
STIME Piemonte Valle
20.000 99,9 99,9 99,9 99,9 99,9 99,9 99,9 99,9 99,9 99,9 99,9 99,9
PROSPETTO C. VALORI INTERPOLATI DEGLI ERRORI CAMPIONARI RELATIVI PERCENTUALI
STIME Italia Nord Nord-
ovest Nord-est Centro Mezzogiorno Sud Isole A1 A2 B1 B2 B3 B4
20.000 44,9 42,8 43,9 34,5 39,8 33,4 31,8 31,5 42,8 37,6 22,7 33,6 35,7 34,2
STIME Piemonte Valle
d'Aosta Liguria Lombardia Trentino-
20.000 31,4 6,0 21,0 46,4 13,2 12,4 11,9 32,8 18,4 33,4 30,8 16,3
60.000 16,2 3,1 11,0 24,2 6,8 6,3 6,0 17,1 9,6 17,1 15,8 8,7
300.000 6,1 - 4,3 9,3 2,6 2,4 2,2 6,6 3,7 6,5 5,9 3,4
STIME Marche Lazio Abruzzo Molise Campania Puglia Basilicata Calabria Sicilia Sardegna
20.000 19,2 41,5 18,5 9,3 33,2 31,4 13,4 21,8 33,5 20,9
"""


class ItalySamplingError(unittest.TestCase):
    def test_prospetto_c_is_read_after_its_title(self):
        from scripts.fetch_census.italy_language_survey import prospetto_c
        errors = prospetto_c(PROSPETTO)
        self.assertEqual(errors["Valle d'Aosta"], {20000: 6.0, 60000: 3.1})
        self.assertEqual(errors["Nord-Ovest"][20000], 43.9)
        self.assertEqual(errors["Sardegna"][20000], 20.9)
        with self.assertRaises(SystemExit):
            prospetto_c(PROSPETTO.replace("20.000 19,2 41,5", "20.000 41,5"))

    def test_effective_sample_of_the_smallest_region(self):
        from scripts.fetch_census.italy_language_survey import (
            effective_sample, precision_note)
        level, cv, n = effective_sample(120000, {20000: 6.0, 60000: 3.1})
        self.assertEqual((level, cv, n), (60000, 3.1, 1040))
        self.assertIn("about 1,040 persons", precision_note(120000, {20000: 6.0, 60000: 3.1}))
        with self.assertRaises(SystemExit):
            precision_note(120000, {60000: 12.0})               # n about 70


class SpainSurveySamples(unittest.TestCase):
    def test_the_ige_design_adds_up(self):
        from scripts.fetch_census.spain_language_survey import ige_sample
        text = ("Tamaño da mostra\nA mostra consta de 512 seccións coa seguinte repartición por "
                "provincias: A Coruña 180; Lugo\n90; Ourense 91; Pontevedra 151. En cada sección "
                "entrev ístanse 18 vivendas, co que resulta un\ntotal de 9.216 vivendas.")
        self.assertEqual(ige_sample(text), {"12": 9216, "15": 3240, "27": 1620, "32": 1638,
                                            "36": 2718})
        with self.assertRaises(SystemExit):
            ige_sample(text.replace("Lugo\n90", "Lugo\n91"))

    def test_the_eulp_effective_sample(self):
        from scripts.fetch_census.spain_language_survey import catalonia, eulp_sample
        page = "<p>La mostra efectiva ha estat de 8.682 individus.</p>"
        self.assertEqual(eulp_sample(page), 8682)
        self.assertIn("effective sample of 8,682", catalonia(EULP_2023, 8682)["language_note"])
        with self.assertRaises(SystemExit):
            eulp_sample("<p>nothing</p>")


if __name__ == "__main__":
    unittest.main()
