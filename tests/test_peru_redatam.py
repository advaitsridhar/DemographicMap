"""Peru's 2017 census on REDATAM: output tables read, and every total checked."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import peru_redatam as pr  # noqa: E402


def row(*cells: str) -> str:
    return "<tr>" + "".join(f'<td class="c1">{c}</td>' for c in cells) + "</tr>"


def page(areas: list[tuple[str, str, list[tuple[str, str]], str, str | None]], title: str) -> str:
    """An output page as the processor writes one: an area row, a header, categories."""
    body = [row("Área Geográfica"), row("Toda la Base de Datos"), row("Frecuencia")]
    for code, name, cats, total, na in areas:
        body += [row("&nbsp;", f"AREA # {code}", name, "&nbsp;"), row("&nbsp;"),
                 row("&nbsp;", title, "Casos", "%", "Acumulado %")]
        body += [row("&nbsp;", label, f"   {n}", "1,00%", "1,00%") for label, n in cats]
        body.append(row("&nbsp;", "Total", f"   {total}", "100,00%", "100,00%"))
        if na is not None:
            body.append(row("&nbsp;", f"No Aplica : {na}"))
    return "<html><table>" + "".join(body) + "</table></html>"


class Tables(unittest.TestCase):
    def test_counts_with_spaced_thousands_and_numeric_labels_are_read_by_cell(self):
        html = page([("0101", "Amazonas, provincia: Chachapoyas",
                      [("Edad 0", "890"), ("Edad 7 años", "1 001")], "1 891", None)],
                    "P: Edad en años")
        (table,) = pr.tables(html)
        self.assertEqual(table["area"], "0101")
        self.assertEqual(table["rows"], [("Edad 0", 890), ("Edad 7 años", 1001)])
        self.assertEqual(table["total"], 1891)

    def test_not_applicable_is_read_in_one_cell_or_two(self):
        html = page([("0101", "Amazonas, provincia: Chachapoyas",
                      [("Católica", "179 874")], "179 874", "97 779")], "P12a+: Religión")
        self.assertEqual(pr.tables(html)[0]["na"], 97779)
        two = html.replace("No Aplica : 97 779", "No Aplica :</td><td>97 779")
        self.assertEqual(pr.tables(two)[0]["na"], 97779)

    def test_one_page_holds_one_table_per_province(self):
        html = page([("0101", "Amazonas, provincia: Chachapoyas", [("Hombre", "5")], "5", None),
                     ("0102", "Amazonas, provincia: Bagua", [("Mujer", "7")], "7", None)],
                    "P: Sexo")
        self.assertEqual([t["area"] for t in pr.tables(html)], ["0101", "0102"])


class Labels(unittest.TestCase):
    def test_a_label_this_file_does_not_know_stops_the_run(self):
        with self.assertRaises(SystemExit):
            pr.translate([("Católica", 5), ("Budista", 1)], pr.RELIGION, "religion")

    def test_the_unanswered_are_kept_apart_not_translated(self):
        counts, left = pr.translate([("Mestizo", 8), (pr.UNANSWERED, 2)], pr.ETHNICITY,
                                    "ethnicity", (pr.UNANSWERED,))
        self.assertEqual(counts, {"Mestizo": 8})
        self.assertEqual(left, {pr.UNANSWERED: 2})


class Checks(unittest.TestCase):
    def unit(self, code: str, people: int, under12: int, under3: int) -> dict[str, list[dict]]:
        name = "Amazonas, provincia: Chachapoyas"
        def t(rows, na=None):
            return [{"area": code, "name": name, "title": "x", "rows": rows,
                     "total": sum(n for _, n in rows), "na": na}]
        return {"sex": t([("Hombre", people // 2), ("Mujer", people - people // 2)]),
                "age": t([("Edad 0", people)]),
                "ethnicity": t([("Mestizo", people - under12)], under12),
                "religion": t([("Católica", people - under12)], under12),
                "language": t([("Castellano", people - under3)], under3)}

    def test_answers_and_not_applicable_must_make_the_province(self):
        tables = self.unit("0101", 100, 30, 10)
        tables["religion"][0]["na"] = 29
        with self.assertRaises(SystemExit):
            pr.collect(tables)

    def test_a_province_short_of_a_question_is_refused(self):
        tables = self.unit("0101", 100, 30, 10)
        del tables["language"]
        tables["language"] = []
        with self.assertRaises(SystemExit):
            pr.collect(tables)


    def test_the_countrys_table_after_the_provinces_is_a_check_not_a_unit(self):
        tables = self.unit("0101", 100, 30, 10)
        for q, found in tables.items():
            country = dict(found[0], area=None, name="")
            found.append(country)
        with self.assertRaises(SystemExit):          # one province is not INEI's 196
            pr.collect(tables)
        tables["sex"][-1]["total"] += 1
        with self.assertRaises(SystemExit) as caught:
            pr.collect(tables)
        self.assertIn("not the provinces' sum", str(caught.exception))


class Places(unittest.TestCase):
    def test_both_ways_inei_labels_a_province_are_read(self):
        self.assertEqual(pr.PLACE.match("Amazonas, provincia: Chachapoyas").groups(),
                         ("Amazonas", "Chachapoyas"))
        self.assertEqual(pr.PLACE.match("Madre de Dios prov. de Tambopata").groups(),
                         ("Madre de Dios", "Tambopata"))
        self.assertIsNone(pr.PLACE.match("Provincia Constitucional del Callao"))


class Median(unittest.TestCase):
    def test_the_median_is_interpolated_within_the_middle_year(self):
        from collections import Counter
        self.assertEqual(pr.median_age(Counter({a: 10 for a in range(10)})), 5.0)


if __name__ == "__main__":
    unittest.main()
