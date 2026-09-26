"""Paraguay's 2022 census on REDATAM: tables read, districts regrouped, every total checked."""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import paraguay_census as pc  # noqa: E402

A2 = """Familia linguistica y pueblo,Total ,Asuncion ,Boqueron
Total pais ,1.210,20,1.190
Familia Guarani ,300,10,290
Ache ,100,-   ,100
Mbya Guarani ,200,10,190
Familia Mataco Mataguayo ,900,5,895
Nivacle ,900,5,895
No indigena ,10,5,5
,10,5,5
"""


def table(code: str, name: str, rows: list[tuple[str, int]], na: int | None = None) -> dict:
    return {"area": code, "name": name, "title": "x", "rows": rows,
            "total": sum(n for _, n in rows), "na": na}


def district(code: str, name: str, people: int, ind: int, habla: dict[int, int],
             spoken: dict[str, int]) -> dict[str, dict]:
    """One district's tables as the reader receives them, each making ``people``."""
    out = {
        "sex": table(code, name, [("Hombre", people // 2), ("Mujer", people - people // 2)]),
        "age": table(code, name, [("0", people // 2), ("40", people - people // 2)]),
        "indigenous": table(code, name, [("Indígena", ind), ("Resto", people - ind)]),
        "habla": table(code, name, [(str(k), v) for k, v in habla.items()]),
    }
    for item, category, _ in pc.LANGUAGES + [(pc.SPEAKS_NONE[0], pc.SPEAKS_NONE[1], "")]:
        n = spoken.get(item, 0)
        rows = ([(category, n)] if n else []) + [(pc.UNSPECIFIED, habla.get(9, 0))]
        answered = sum(v for _, v in rows)
        out[item] = table(code, name, rows, people - answered)
    return out


def by_question(*districts: dict[str, dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for d in districts:
        for question, t in d.items():
            out.setdefault(question, {})[t["area"]] = t
    return out


class Peoples(unittest.TestCase):
    def test_peoples_are_read_by_department_and_families_are_not_kept(self):
        found = pc.peoples_table(A2)
        self.assertEqual(found["BOQUERON"], {"Aché": 100, "Mbyá Guaraní": 190, "Nivaclé": 895})
        self.assertEqual(found["ASUNCION"], {"Mbyá Guaraní": 10, "Nivaclé": 5})

    def test_a_family_its_peoples_do_not_make_stops_the_run(self):
        with self.assertRaises(SystemExit):
            pc.peoples_table(A2.replace("Ache ,100,-   ,100", "Ache ,99,-   ,99"))

    def test_an_unknown_people_stops_the_run(self):
        with self.assertRaises(SystemExit):
            pc.peoples_table(A2.replace("Ache ,", "Guayaki ,"))


class Districts(unittest.TestCase):
    def setUp(self):
        self.one = district("0101", "CONCEPCIÓN", 100, 10, {0: 5, 1: 90, 2: 1, 9: 4},
                            {"P1601": 80, "P1602": 70, "P1698": 1})
        self.two = district("0110", "SAN ALFREDO", 50, 0, {0: 2, 1: 48},
                            {"P1601": 48, "P1604": 3})

    def test_counts_are_read_and_checked(self):
        with mock.patch.object(pc, "NATIONAL", 150):
            units = pc.district_counts(by_question(self.one, self.two))
        self.assertEqual(units["0101"]["spoken"]["Paraguayan Guaraní"], 80)
        self.assertEqual(units["0110"]["indigenous"], {"Indigenous": 0, "Not indigenous": 50})

    def test_a_language_item_whose_unrecorded_answers_differ_stops_the_run(self):
        rows = self.one["P1602"]["rows"]
        self.one["P1602"] = table("0101", "CONCEPCIÓN", [rows[0], (pc.UNSPECIFIED, 3)], 27)
        with mock.patch.object(pc, "NATIONAL", 150), self.assertRaises(SystemExit):
            pc.district_counts(by_question(self.one, self.two))

    def test_districts_that_do_not_make_the_national_count_stop_the_run(self):
        with mock.patch.object(pc, "NATIONAL", 151), self.assertRaises(SystemExit):
            pc.district_counts(by_question(self.one, self.two))

    def test_multi_response_shares_are_of_the_people_who_named_a_language(self):
        with mock.patch.object(pc, "NATIONAL", 150):
            units = pc.district_counts(by_question(self.one, self.two))
        both = pc.summed([units["0101"], units["0110"]])
        fields = pc.language_fields(both, "here")
        shares = {r["group"]: r["pct"] for r in fields["language"]}
        self.assertEqual(shares["Paraguayan Guaraní"], round(100 * 128 / 138, 1))
        self.assertGreater(sum(shares.values()), 100)
        self.assertIn("138", fields["language_note"])


class Splits(unittest.TestCase):
    def test_a_district_carved_from_one_drawn_district_is_added_back(self):
        units = {c: {} for c in ("0101", "0110", "0111", "0103", "0112")}
        self.assertEqual(pc.drawn_groups(units),
                         {"0101": ["0101", "0110", "0111"], "0103": ["0103", "0112"]})

    def test_districts_tangled_with_a_many_parent_split_are_left_out(self):
        units = {c: {} for c in ("0204", "0213", "0222", "0201")}
        self.assertEqual(pc.drawn_groups(units), {"0201": ["0201"]})

    def test_every_tangle_names_its_polygons(self):
        for olds, news, polys, why in pc.TANGLES:
            self.assertTrue(olds and news and polys and why)


class Ethnicity(unittest.TestCase):
    def test_peoples_beyond_the_table_are_one_line_and_the_rest_another(self):
        unit = {"indigenous": Counter({"Indigenous": 110, "Not indigenous": 890}), "people": 1000}
        fields = pc.department_ethnicity(unit, Counter({"Nivaclé": 100}), "BOQUERON")
        got = {r["group"]: r["count"] for r in fields["ethnicity"]}
        self.assertEqual(got, {"Nivaclé": 100, pc.UNPUBLISHED: 10, pc.NOT_INDIGENOUS: 890})

    def test_a_table_naming_more_indigenous_people_than_counted_stops_the_run(self):
        unit = {"indigenous": Counter({"Indigenous": 90, "Not indigenous": 910}), "people": 1000}
        with self.assertRaises(SystemExit):
            pc.department_ethnicity(unit, Counter({"Nivaclé": 100}), "BOQUERON")


class Religion(unittest.TestCase):
    def test_categories_are_translated_and_the_unanswered_left_out(self):
        fields = pc.religion_fields({"rows": [("Católica", 80), ("Mennonita", 10),
                                              ("Indígena + católica", 5),
                                              ("Religión indígena", 3), ("No especificado", 2)]})
        got = {r["group"]: r["count"] for r in fields["religion"]}
        self.assertEqual(got, {"Catholic": 80, "Mennonite": 10, "Indigenous religion": 8})
        self.assertIn("5 named an indigenous religion", fields["religion_note"])

    def test_an_unknown_religion_stops_the_run(self):
        with self.assertRaises(SystemExit):
            pc.religion_fields({"rows": [("Zoroastrismo", 1)]})


class Names(unittest.TestCase):
    def test_ine_capitals_are_written_as_names(self):
        self.assertEqual(pc.title("SAN JUAN DEL PARANÁ"), "San Juan del Paraná")
        self.assertEqual(pc.age_of("Menor de 1 año"), 0)
        self.assertEqual(pc.age_of("100 y más"), 100)


if __name__ == "__main__":
    unittest.main()
