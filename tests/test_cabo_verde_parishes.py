"""Cabo Verde's parishes: what the median-age reason quotes, it cites."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import cabo_verde_parishes as cv  # noqa: E402


def parish(code: int, name: str, total: float, men: float) -> dict:
    return {"code": code, "name": name, "total": total, "men": men, "women": total - men,
            "zones": 2.0, "url": "u", "island": "Fogo.xls", "island_name": "Fogo"}


class ParishReasonsCiteWhatTheyQuote(unittest.TestCase):
    def test_a_parish_of_a_municipality_with_several(self):
        # São Filipe (INE code 82) has two parishes: neither takes a 2021 count,
        # and each says why it has no median age, quoting the 2010 parish table,
        # the 2021 census and OCHA's projections, all three cited for the note.
        parishes = {82: [parish(821, "N.S. Conceição", 13_328.0, 6_667.0),
                         parish(822, "S. Lourenço", 8_000.0, 4_000.0)]}
        table = {cv.fold("S. Filipe"): {"total": 21_329.0, "households": 21_328.0}}
        admin1 = [{"id": "m82", "name": "São Filipe"}]
        admin2 = [{"id": "p1", "name": "Nossa Senhora Da Conceicao", "parent": "m82"},
                  {"id": "p2", "name": "Sao Lourenco", "parent": "m82"}]
        records = cv.records_of(parishes, table, admin1, admin2)
        rec = next(r for r in records if r["shape_id"] == "p1")
        self.assertIn("the 2021 census and OCHA's population projections",
                      rec["median_age"]["note"])
        cited = [(s["field"], s["name"]) for s in rec["sources"]]
        self.assertEqual(cited[0][0], "population/sex_ratio/median_age note")
        self.assertEqual([f for f, _ in cited[1:]], ["median_age note", "median_age note"])
        self.assertIn("Censo 2021", cited[1][1])
        self.assertIn("cod-ps-cpv", cited[2][1])


if __name__ == "__main__":
    unittest.main()
