"""Venezuela's 2011 census on REDATAM: municipio tables read, partitioned and checked."""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import redatam  # noqa: E402
from scripts.fetch_census import venezuela_redatam as vr  # noqa: E402


def row(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def table(code: str, name: str, rows: list[tuple[str, int]], rest: dict[str, int]) -> dict:
    answers = [(k, n) for k, n in rows]
    return {"area": code, "name": name, "title": "x",
            "rows": answers + [(f"{k} :", v) for k, v in rest.items()],
            "total": sum(n for _, n in answers), "na": None}


def municipio(code: str, name: str, people: int, peoples: dict[str, int],
              identity: dict[str, int]) -> dict[str, dict]:
    indigenous = sum(peoples.values())
    return {
        "sex": table(code, name, [("Hombre", people // 2), ("Mujer", people - people // 2)], {}),
        "age": table(code, name, [("0", people // 2), ("30", people - people // 2)], {}),
        "peoples": table(code, name, list(peoples.items()), {"NSA": people - indigenous}),
        "identity": table(code, name, list(identity.items()),
                          {"NSA": people - sum(identity.values())}),
    }


def base(*municipios: dict[str, dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for m in municipios:
        for question, t in m.items():
            out.setdefault(question, []).append(t)
    for question, found in out.items():
        found.append({"area": None, "name": "", "title": "x", "rows": [],
                      "total": sum(t["total"] for t in found), "na": None})
    return out


class Output(unittest.TestCase):
    def test_not_asked_and_ignored_rows_come_after_the_total(self):
        page = ("<table>" + row("AREA # 0101", "Distrito Capital, Libertador")
                + row("Usted como se reconoce", "Casos", "%", "Acumulado %")
                + row("Blanca / Blanco", "1.000", "50", "50")
                + row("Morena / Moreno", "900", "45", "95")
                + row("Total", "1.900", "100", "100")
                + row("NSA :", "80") + row("Ignorado :", "20") + "</table>")
        (t,) = redatam.tables(page)
        answers, rest = vr.split_rows(t, "identity")
        self.assertEqual(answers, [("Blanca / Blanco", 1000), ("Morena / Moreno", 900)])
        self.assertEqual(rest, 100)


class Municipios(unittest.TestCase):
    def setUp(self):
        self.a = municipio("2315", "Zulia, Indígena Bolivariano Guajira", 100,
                           {"Wayuu": 60, "Guajiro": 20}, {"Morena / Moreno": 15, "Otra": 3})
        self.b = municipio("2401", "Vargas, Vargas", 50, {}, {"Blanca / Blanco": 50})

    def test_the_two_questions_partition_the_people_and_the_rest_is_not_stated(self):
        with mock.patch.object(vr, "NATIONAL", 150):
            units = vr.municipio_counts(base(self.a, self.b))
        unit = units["2315"]
        self.assertEqual(unit["state"], "Zulia")
        self.assertEqual(unit["peoples_"], {"Wayuu": 80})
        self.assertEqual(unit["not_stated"], 2)
        got = {r["group"]: r["count"] for r in vr.fields(unit, "admin2")["ethnicity"]}
        self.assertEqual(got, {"Wayuu": 80, "Moreno": 15, "Other": 3,
                               vr.NOT_STATED: 2})
        self.assertEqual(units["2401"]["state"], "La Guaira")

    def test_an_unknown_people_stops_the_run(self):
        self.a["peoples"]["rows"][0] = ("Wayú", 60)
        with mock.patch.object(vr, "NATIONAL", 150), self.assertRaises(SystemExit):
            vr.municipio_counts(base(self.a, self.b))

    def test_more_indigenous_people_than_the_identity_question_skipped_stops_the_run(self):
        self.a["identity"] = table("2315", "Zulia, Indígena Bolivariano Guajira",
                                   [("Morena / Moreno", 90)], {"NSA": 10})
        with mock.patch.object(vr, "NATIONAL", 150), self.assertRaises(SystemExit):
            vr.municipio_counts(base(self.a, self.b))

    def test_municipios_that_miss_the_national_count_stop_the_run(self):
        with mock.patch.object(vr, "NATIONAL", 149), self.assertRaises(SystemExit):
            vr.municipio_counts(base(self.a, self.b))

    def test_state_sums_must_be_ine_s_table_by_state(self):
        with mock.patch.object(vr, "NATIONAL", 150):
            units = vr.municipio_counts(base(self.a, self.b))
        vr.check_states(units, {"zulia": ("Zulia", 80, Counter({"Wayuu": 80}))})
        with self.assertRaises(SystemExit):
            vr.check_states(units, {"zulia": ("Zulia", 81, Counter({"Wayuu": 81}))})


class Labels(unittest.TestCase):
    def test_every_spelling_folds_into_the_name_ine_s_state_table_uses(self):
        self.assertEqual(vr.PEOPLES["Guajiro"], vr.PEOPLES["Wayuu"])
        self.assertEqual(vr.PEOPLES["Taurepán"], "Pemón")
        self.assertEqual(vr.IDENTITY["Morena / Moreno"], "Moreno")


if __name__ == "__main__":
    unittest.main()
