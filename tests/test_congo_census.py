"""The Republic of the Congo's 2023 departments and its second level's reasons (no network)."""

import unittest

from scripts.fetch_census import congo_census as cc

INDEX = ('<a href="/en/congo/admin/07__cuvette/">x</a>'
         '<a href="/en/congo/admin/cuvette/0711__bokoma/">y</a>'
         '<a href="https://www.citypopulation.de/en/congo/admin/03__lékoumou/">z</a>'
         '<a href="/en/congo/admin/l%C3%A9koumou/0302x__sibiti/">w</a>')
CUVETTE = ("<table><tr><th>Name</th><th>Status</th><th>Population Census 2023-05-17</th></tr>"
           "<tr><td><a href='x'>Cuvette</a></td><td>Department</td><td>316,599</td><td></td></tr>"
           "<tr><td><a href='/en/congo/admin/cuvette/0711__bokoma/'>Bokoma</a></td>"
           "<td>District</td><td>4,588</td></tr></table>"
           "<table><tr><td>Males</td><td>153,648</td></tr>"
           "<tr><td>Females</td><td>162,951</td></tr></table>")


def page(name, total, men, women, districts=()):
    rows = "".join(f"<tr><td><a href='/en/congo/admin/x/{i:04d}__{n.lower()}/'>{n}</a></td>"
                   f"<td>District</td><td>{t:,}</td></tr>" for i, (n, t) in enumerate(districts))
    return (f"<table><tr><td>{name}</td><td>Department</td><td>{total:,}</td></tr>{rows}</table>"
            f"<table><tr><td>Males</td><td>{men:,}</td></tr>"
            f"<tr><td>Females</td><td>{women:,}</td></tr></table>")


KOUILOU = page("Kouilou", 97_362, 52_111, 45_251, [("Hinda", 19_264)])
POINTE_NOIRE = page("Pointe-Noire", 1_420_612, 708_953, 711_659,
                    [("Pointe-Noire", 1_400_000), ("Tchiamba-Nzassi", 20_612)])
ADMIN1 = [{"id": "K", "name": "Kouilou"}, {"id": "P", "name": "Pointe-Noire"}]
URLS = {"Kouilou": "https://k", "Pointe-Noire": "https://p"}


class Pages(unittest.TestCase):
    def test_links_and_department(self):
        deps, districts = cc.links(INDEX)
        self.assertEqual(len(deps), 2)
        self.assertTrue(any(d.endswith("03__l%C3%A9koumou/") for d in deps))
        self.assertEqual(districts, 2)
        dep = cc.department(CUVETTE)
        self.assertEqual({k: dep[k] for k in ("name", "total", "men", "women")},
                         {"name": "Cuvette", "total": 316_599, "men": 153_648, "women": 162_951})
        self.assertEqual([(d["name"], d["total"]) for d in dep["districts"]], [("Bokoma", 4_588)])
        self.assertTrue(dep["districts"][0]["url"].endswith("/0711__bokoma/"))

    def test_build(self):
        found = [cc.department(CUVETTE)]
        admin1 = [{"id": "C", "name": "Cuvette"}]
        sid = "1427508B80151114352270"
        admin2 = [{"id": sid, "name": "Zanaga", "parent": "B"}]
        records, report = cc.build(found, 92, admin1, admin2, {"Cuvette": "https://x"})
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Cuvette"]["sex_ratio"]["value"], round(1000 * 153_648 / 162_951))
        note = by["Zanaga"]["population"]["note"]
        self.assertIn("Brazzaville (Brazzaville)", note)
        self.assertIn("92 districts and communes", note)
        # Polygons no longer drawn as measured are left out and said.
        self.assertTrue(any("no longer drawn" in line for line in report))

    def test_notes(self):
        self.assertIn("holds the town of that name",
                      cc.town_note("Mossendjo", (("Mossendjo", "Niari"),), 90))
        self.assertIn("no town", cc.town_note("Boundji", (), 90))


class SecondLevel(unittest.TestCase):
    """Komono stood with Wikidata's 8,941 beside notes saying no figure is shown."""

    def records(self):
        admin2 = [{"id": sid, "name": label, "parent": "X"}
                  for sid, (label, _) in cc.FACTS.items()]
        found = [cc.department(CUVETTE)]
        records, _ = cc.build(found, 92, [{"id": "C", "name": "Cuvette"}], admin2,
                              {"Cuvette": "https://x"})
        return {r["name"]: r for r in records if r["level"] == "admin2"}

    def test_the_reason_displaces_a_figure_bound_by_name(self):
        komono = self.records()["Komono"]
        for field in ("population", "median_age", "sex_ratio"):
            self.assertEqual(komono[field]["status"], "not_available")
            self.assertGreater(komono[field]["displaces_before"], cc.YEAR)
            self.assertTrue(komono[field]["displaces_undated"])

    def test_the_seat_note_says_what_the_polygon_holds(self):
        by = self.records()
        mossendjo = by["Mossendjo"]["capital"]["note"]
        self.assertIn("holds the town of Mossendjo", mossendjo)
        self.assertNotIn("out of place here", mossendjo)
        self.assertIn("Zanaga (Lékoumou), not Komono", by["Komono"]["capital"]["note"])
        self.assertTrue(by["Kakamoeka"]["capital"]["note"].startswith("No town inside"))

    def test_sources_are_cited_for_notes_only(self):
        for rec in self.records().values():
            for src in rec["sources"]:
                self.assertTrue(all(part.endswith(" note") for part in src["field"].split("/")),
                                src["field"])


class Moved(unittest.TestCase):
    """Tchiamba-Nzassi is counted under Pointe-Noire and drawn inside Kouilou."""

    def found(self):
        return [cc.department(KOUILOU), cc.department(POINTE_NOIRE)]

    def test_the_district_moves_with_its_sexes(self):
        sexed = "<table><tr><td>Males</td><td>10,500</td></tr><tr><td>Females</td><td>10,112</td></tr></table>"
        moved = cc.moves(self.found(), lambda url: sexed)
        self.assertEqual(len(moved), 1)
        self.assertEqual((moved[0]["total"], moved[0]["men"]), (20_612, 10_500))
        records, _ = cc.build(self.found(), 92, ADMIN1, [], URLS, moved)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Kouilou"]["population"]["value"], 97_362 + 20_612)
        self.assertEqual(by["Pointe-Noire"]["population"]["value"], 1_420_612 - 20_612)
        self.assertEqual(by["Kouilou"]["sex_ratio"]["value"],
                         round(1000 * (52_111 + 10_500) / (45_251 + 10_112)))
        self.assertIn("Tchiamba-Nzassi", by["Kouilou"]["population_note"])
        self.assertIn("lies inside the polygon drawn as Kouilou",
                      by["Pointe-Noire"]["population_note"])

    def test_without_its_sexes_the_ratios_say_so(self):
        moved = cc.moves(self.found(), lambda url: "<table></table>")
        records, _ = cc.build(self.found(), 92, ADMIN1, [], URLS, moved)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Kouilou"]["sex_ratio"]["value"], round(1000 * 52_111 / 45_251))
        self.assertIn("without the district of Tchiamba-Nzassi", by["Kouilou"]["sex_ratio_note"])
        self.assertIn("Tchiamba-Nzassi included", by["Pointe-Noire"]["sex_ratio_note"])

    def test_a_district_already_counted_where_drawn_does_not_move(self):
        kouilou = page("Kouilou", 117_974, 62_611, 55_363, [("Tchiamba-Nzassi", 20_612)])
        found = [cc.department(kouilou), cc.department(page("Pointe-Noire", 1_400_000, 1, 1))]
        self.assertEqual(cc.moves(found, lambda url: ""), [])


if __name__ == "__main__":
    unittest.main()
