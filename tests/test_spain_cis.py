"""Spain's religion from the CIS's pre-electoral surveys: reading, checks, binding, records.

No network: the workbook, the HTML marginals and the ficha técnica are built
here in the shapes the CIS publishes them in.
"""

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import spain_cis as s  # noqa: E402

ANSWERS_ES = ["Católico/a practicante", "Católico/a no practicante", "Creyente de otra religión",
              "Agnóstico/a (no niegan la existencia de Dios pero tampoco la descartan)",
              "Indiferente, no creyente", "Ateo/a (niegan la existencia de Dios)", "N.C."]

FICHA_ROWS = [
    [None, "3545/0 PREELECTORAL ELECCIONES AUTONÓMICAS 2026. COMUNIDAD AUTÓNOMA DE CASTILLA Y LEÓN"],
    [None, "FICHA TÉCNICA DEL ESTUDIO"],
    ["FICHA TÉCNICA"],
    ["Ámbito", "Castilla y León   (aut.)."],
    ["Universo", "Población española con derecho a voto en elecciones autonómicas y residente "
                 "en la comunidad autónoma de ambos sexos de 18 y más años."],
    ["Tamaño de la muestra:"],
    ["Diseñada", "8.000 entrevistas."],
    ["Realizada", "{total} entrevistas."],
    ["Afijación", "No proporcional"],
    [None, "Partiendo de una distribución proporcional por provincias, ..._x000D_"],
    ["Ponderación", "Para tratar la muestra en su conjunto es necesario aplicar coeficientes "
                    "de ponderación (PESO)._x000D_ Para la estimación a nivel de cada provincia, "
                    "en el fichero de microdatos se incluye la ponderación para cada una de ellas "
                    "(variable PESOPROV)."],
    ["Procedimiento de muestreo", "Los cuestionarios se han aplicado mediante entrevista "
                                  "telefónica asistida por ordenador (CATI)."],
    ["Fecha de realización", "Del 6 al 13 de febrero de 2026."],
]

# Castilla y León's nine provinces: code, name, realised sample, mean weight.
CYL = [("05", "Ávila", 587, 0.9766), ("09", "Burgos", 1044, 1.0058), ("24", "León", 1377, 1.1183),
       ("34", "Palencia", 616, 0.9092), ("37", "Salamanca", 1012, 1.1053),
       ("40", "Segovia", 612, 0.8421), ("42", "Soria", 542, 0.5217),
       ("47", "Valladolid", 1637, 1.0439), ("49", "Zamora", 612, 1.1279)]


def province_shares(i):
    """Seven shares summing to 100, different for each province."""
    base = [26.0 + i, 36.0 - i, 2.0, 9.5, 10.5, 13.0, 3.0]
    return base


def region_of(provinces):
    mass = [n * w for _, _, n, w in provinces]
    whole = sum(mass)
    shares = [province_shares(i) for i in range(len(provinces))]
    return [sum(m * sh[k] for m, sh in zip(mass, shares)) / whole for k in range(7)]


def marginal_rows(title, shares, n):
    rows = [[None, "3545/0 PREELECTORAL"], [None, title], [None, "INFORME DE MARGINALES"],
            ["Pregunta A1"], ["Sexo:"], ["Hombre", 48.9], ["Mujer", 51.1], ["(N)", n], [None],
            ["Pregunta C6"], [s.QUESTION_ES]]
    rows += [[label, share] for label, share in zip(ANSWERS_ES, shares)]
    rows += [["(N)", n], [None], ["Pregunta C6a"],
             ["SÓLO A QUIENES SE DEFINEN EN MATERIA RELIGIOSA COMO CATÓLICOS/AS"],
             ["Casi nunca", 40.0], ["(N)", n - 10]]
    return rows


def workbook(provinces=CYL, region_shares=None, header="3545/0 PREELECTORAL ELECCIONES",
             total=None, drop=None):
    import openpyxl
    book = openpyxl.Workbook()
    first = book.active
    first.title = "Contenidos"
    first.append([None, header])
    total = total if total is not None else sum(n for _, _, n, _ in provinces)
    ficha = book.create_sheet("Ficha técnica")
    for row in FICHA_ROWS:
        ficha.append([c.format(total=f"{total:,}".replace(",", ".")) if isinstance(c, str) else c
                      for c in row])
    table = book.create_sheet("Tabla ponderaciones")
    table.append([None, "Muestra diseñada, realizada, coeficientes de ponderación y error (%)"])
    table.append([None, None, "Muestra"])
    table.append(["cpr", "Provincia", "Diseñada", "Realizada", "Ponderación", "Error (%)"])
    for code, name, n, w in provinces:
        table.append([code, name, 600, n, w, 4.0])
    table.append([None, "Total", 8000, total, None, 1.1])
    region = region_shares or region_of(provinces)
    book.create_sheet("Resultados_Castilla y León")
    for row in marginal_rows("Total", region, sum(n for _, _, n, _ in provinces)):
        book["Resultados_Castilla y León"].append(row)
    for i, (code, name, n, _) in enumerate(provinces):
        if name == drop:
            continue
        sheet = book.create_sheet(f"Resultados_{name}")
        for row in marginal_rows(f"Provincia de {name}", province_shares(i), n):
            sheet.append(row)
    book.create_sheet("Sexo")
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


STUDY = s.Study(3545, "Preelectoral elecciones autonómicas 2026. Comunidad autónoma de Castilla y León",
                "the 2026 election to the Cortes of Castile and León", "07",
                "https://www.cis.es/documents/20117/13765729/3545-multi.xlsx", "https://www.cis.es/x")


class TestAnswers(unittest.TestCase):
    def test_every_answer_the_cis_offers(self):
        self.assertEqual([s.answer_label(a) for a in ANSWERS_ES],
                         ["Practising Catholic", "Non-practising Catholic",
                          "Believer in another religion", "Agnostic",
                          "Indifferent / non-believer", "Atheist", "Not stated"])
        # The HTML marginals put a zero-width space after "Católico/".
        self.assertEqual(s.answer_label("Católico/&#8203;a no practicante"),
                         "Non-practising Catholic")
        self.assertEqual(s.answer_label("N.S."), "Not stated")

    def test_an_answer_it_does_not_offer_stops(self):
        with self.assertRaises(SystemExit):
            s.answer_label("Musulmán/a")

    def test_numbers(self):
        self.assertEqual(s.number("15,2"), 15.2)
        self.assertEqual(s.number("(4.998)"), 4998)
        self.assertEqual(s.number("(998)"), 998)
        self.assertEqual(s.number(26.4), 26.4)


class TestReading(unittest.TestCase):
    def test_religion_block(self):
        shares, n = s.religion_block(marginal_rows("Provincia de Ávila", province_shares(0), 587),
                                     "test")
        self.assertEqual(n, 587)
        self.assertEqual(shares["Practising Catholic"], 26.0)
        self.assertEqual(shares["Not stated"], 3.0)
        self.assertEqual(len(shares), 7)

    def test_a_missing_answer_or_a_bad_sum_stops(self):
        rows = marginal_rows("x", province_shares(0), 587)
        bad = [r for r in rows if not (r and r[0] == "Ateo/a (niegan la existencia de Dios)")]
        with self.assertRaises(SystemExit):
            s.religion_block(bad, "test")
        skew = [[r[0], 30.0] if r and r[0] == "N.C." else r for r in rows]
        with self.assertRaises(SystemExit):
            s.religion_block(skew, "test")

    def test_no_question_stops(self):
        with self.assertRaises(SystemExit):
            s.religion_block([["Pregunta A1"], ["Sexo:"], ["(N)", 5]], "test")

    def test_weights_table(self):
        rows = [[None, "x"], ["cpr", "Provincia", "Diseñada", "Realizada", "Ponderación", "Error (%)"],
                ["05", "Ávila", 600, 587, 0.9766, 4.1], [9, "Burgos", 1039, 1044, 1.0058, 3.1],
                [None, "Total", 1639, 1631, None, 1.1]]
        table, total = s.weights_table(rows, "test")
        self.assertEqual(total, 1631)
        self.assertEqual(table["09"]["realised"], 1044)
        self.assertEqual(table["05"]["weight"], 0.9766)
        rows[-1][3] = 1700
        with self.assertRaises(SystemExit):
            s.weights_table(rows, "test")

    def test_ficha(self):
        text = " ".join(f"{c}:" if j == 0 and isinstance(c, str) else str(c)
                        for row in FICHA_ROWS for j, c in enumerate(row) if c).format(total="8.039")
        got = s.ficha(text, "test")
        self.assertEqual(got["realised"], 8039)
        self.assertEqual(got["year"], 2026)
        self.assertEqual(got["fieldwork"], "Del 6 al 13 de febrero de 2026")
        self.assertTrue(got["voters"] and got["telephone"] and got["weighted"])
        self.assertTrue(got["province_weight"])
        # A barometer's universe names no election, and it has no provincial weight.
        barometer = ("Ámbito: Nacional. Universo: Población española de ambos sexos de 18 años "
                     "y más. Tamaño de la muestra: Diseñada: 4.000 entrevistas. Realizada: 4.042 "
                     "entrevistas. Fecha de realización: Del 1 al 4 de septiembre de 2026.")
        plain = s.ficha(barometer, "test")
        self.assertFalse(plain["voters"] or plain["province_weight"] or plain["weighted"])
        with self.assertRaises(SystemExit):
            s.ficha(barometer.replace("española", "residente"), "test")

    def test_dates_and_sheet_names(self):
        self.assertEqual(s.english_dates("Del 6 al 13 de febrero de 2026."), "6-13 February 2026")
        self.assertEqual(s.english_dates("Del 28 de abril al 5 de mayo de 2026"),
                         "28 April - 5 May 2026")
        self.assertEqual(s.sheet_unit("Resultados_Ávila"), "avila")
        self.assertEqual(s.sheet_unit("Resultados Extremadura "), "extremadura")
        self.assertEqual(s.sheet_unit("Resultados_provincia de Soria"), "soria")
        self.assertEqual(s.sheet_unit("Almería"), "almeria")
        self.assertTrue(s.names_study("Estudio nº3437. PREELECTORAL", 3437))
        self.assertFalse(s.names_study("34370", 3437))


class TestWorkbook(unittest.TestCase):
    def test_reads_every_province_and_the_comunidad(self):
        got = s.read_workbook(workbook(), STUDY)
        self.assertEqual(sorted(got["provinces"]), [c for c, *_ in CYL])
        self.assertEqual(got["provinces"]["42"]["n"], 542)
        self.assertEqual(got["region"]["n"], sum(n for _, _, n, _ in CYL))
        self.assertEqual(got["design"]["year"], 2026)

    def test_another_studys_workbook_stops(self):
        with self.assertRaises(SystemExit):
            s.read_workbook(workbook(header="3453/0 PREELECTORAL DE CATALUÑA"), STUDY)

    def test_a_comunidad_its_provinces_do_not_make_stops(self):
        # Separate weights put the comunidad a few tenths away: that passes.
        region = region_of(CYL)
        region[0] += 0.6
        region[1] -= 0.6
        s.read_workbook(workbook(region_shares=region), STUDY)
        # A point and a half is not weighting.
        region[0] += 0.9
        region[1] -= 0.9
        with self.assertRaises(SystemExit):
            s.read_workbook(workbook(region_shares=region), STUDY)

    def test_a_missing_province_or_a_wrong_total_stops(self):
        with self.assertRaises(SystemExit):
            s.read_workbook(workbook(drop="Soria"), STUDY)
        with self.assertRaises(SystemExit):
            s.read_workbook(workbook(total=8040), STUDY)


HTML = """<html><head><title>3448 Preelectoral del País Vasco</title></head><body>
<p><b>Pregunta C5 </b></p><table><tr><td>Primaria</td><td>9,3</td></tr>
<tr><td>(N)</td><td>(4.998)</td></tr></table>
<p style='x'><b>Pregunta C6 </b><br><p>&iquest;Cómo se define Ud. en materia religiosa:
católico/a practicante, católico/a no practicante, creyente de otra religión, agnóstico/a,
indiferente o no creyente, o ateo/a?</p> <p></p><br></p><table border=0>
<col width=432.0><tr><td style='a'>Católico/&#8203;a practicante</td><td>15,2</td></tr>
<tr><td>Católico/&#8203;a no practicante</td><td>31,8</td></tr>
<tr><td>Creyente de otra religión</td><td>2,6</td></tr>
<tr><td>Agnóstico/&#8203;a (no niegan la existencia de Dios pero tampoco la descartan)</td><td>12,0</td></tr>
<tr><td>Indiferente, no creyente</td><td>16,3</td></tr>
<tr><td>Ateo/&#8203;a (niegan la existencia de Dios)</td><td>20,9</td></tr>
<tr><td>N.C.</td><td>1,2</td></tr>
<tr><td style='b'>(N)</td><td>(4.998)</td></tr></table></body></html>"""


class TestHtmlTotal(unittest.TestCase):
    def test_reads_the_comunidads_marginals(self):
        study = s.Study(3448, "t", "e", "16", "u", "p", "f")
        shares, n = s.read_html_total(HTML, study)
        self.assertEqual(n, 4998)
        self.assertEqual(shares["Atheist"], 20.9)
        self.assertAlmostEqual(sum(shares.values()), 100.0)

    def test_marginals_of_another_study_stop(self):
        with self.assertRaises(SystemExit):
            s.read_html_total(HTML.replace("3448", "3437"), s.Study(3448, "t", "e", "16", "u", "p"))


class TestBinding(unittest.TestCase):
    def test_the_map_binds_by_code(self):
        provinces, comunidades = s.bind(*s.load_units())
        self.assertEqual(len(provinces), 52)
        self.assertEqual(len(comunidades), 19)
        self.assertEqual(provinces["35"]["name"], "Palmas, Las")
        self.assertEqual(provinces["42"]["name"], "Soria")
        self.assertEqual(comunidades["07"]["name"], "Castilla y León")
        self.assertEqual(provinces["42"]["parent"], comunidades["07"]["id"])

    def test_a_code_on_the_wrong_label_stops(self):
        admin1, admin2 = s.load_units()
        moved = [dict(u, name="Segovia") if u["name"] == "Soria" else u for u in admin2]
        with self.assertRaises(SystemExit):
            s.bind(admin1, moved)


class TestRecords(unittest.TestCase):
    def test_records(self):
        provinces, comunidades = s.bind(*s.load_units())
        got = s.read_workbook(workbook(), STUDY)
        got["provinces"]["42"]["n"] = 250                    # low precision
        got["provinces"]["40"]["n"] = 90                     # under the minimum
        records, skipped = s.build([(STUDY, got)], provinces, comunidades)
        self.assertEqual(len(records), 9)                   # the comunidad and 8 provinces
        self.assertEqual(skipped, ["Segovia: 90 respondents (study 3545)"])
        by = {r["name"]: r for r in records}
        soria = by["Soria"]
        self.assertEqual(soria["level"], "admin2")
        self.assertEqual(soria["shape_id"], provinces["42"]["id"])
        self.assertTrue(soria["religion_basis"].startswith("survey estimate"))
        self.assertIn("Low precision", soria["religion_note"])
        self.assertIn("250 respondents in the province of Soria", soria["religion_note"])
        self.assertTrue(all("count" not in row for row in soria["religion"]))
        pcts = [row["pct"] for row in soria["religion"]]
        self.assertEqual(pcts, sorted(pcts, reverse=True))
        self.assertEqual(soria["religion_year"], 2026)
        self.assertIn("PESOPROV", soria["religion_note"])
        region = by["Castilla y León"]
        self.assertEqual(region["level"], "admin1")
        self.assertEqual(region["shape_id"], comunidades["07"]["id"])
        self.assertNotIn("Low precision", region["religion_note"])
        self.assertIn("(PESO)", region["religion_note"])
        self.assertEqual(region["sources"][0]["field"], "religion")


if __name__ == "__main__":
    unittest.main()
