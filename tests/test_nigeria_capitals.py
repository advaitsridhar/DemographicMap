"""The seat reader: what English Wikipedia's articles on Nigeria's local
government areas, The Gambia's units and Liberia's districts say, as the
runner's dump of them printed it (October 2026)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import nigeria_capitals as nc  # noqa: E402

# (polygon, article, wikitext, the seat read or None)
CASES = [
    ("Aba South", "Aba South", "'''Aba South''' is a LGA. The administrative headquarters of "
     "Aba South is situated in [[Aba, Nigeria|Aba]].", "Aba"),
    ("Abeokuta North", "Abeokuta North", "'''Abeokuta North''' is a LGA. Its headquarters are "
     "in the town of Akomoje, near [[Abeokuta]].", "Akomoje"),
    ("Calabar South", "Calabar South", "'''Calabar South''' is a LGA. Its headquarters are In "
     "the town of Anantigha. The local Government Headquarters are in Anantigha.", "Anantigha"),
    ("Chanchaga", "Chanchaga", "Its headquarters is in the state capital of [[Minna]] which "
     "occupies much of the [[Local Government Area]].", "Minna"),
    ("Enugu South", "Enugu South", "'''Enugu South''' is a LGA. Its headquarters are Nnobi "
     "Street, Uwani, Enugu and covers the communities of Akwuke.", "Uwani"),
    ("Esan North-East", "Esan North-East", "Its headquarters are in [[Uromi]]/Uzea.",
     "Uromi/Uzea"),
    ("Fagge", "Fagge", "Its headquarters are in the suburb of Waje.", "Waje"),
    ("Idanre", "Idanre", "'''Idanre''' (), known formerly as '''Ufe Oke''' is a historic town "
     "in [[Ondo State]], and the headquarters of the Idanre [[Local Government Areas of "
     "Nigeria|Local Government Area]] which carries its name.", "Idanre"),
    ("Ifedayo", "Ifedayo", "Its headquarters are in the town of [[Oke-Ila|Oke-Ila Orangun]]. "
     "Ifedayo has its administrative headquarters in Oke-Ila Orangun.", "Oke-Ila Orangun"),
    ("Obowo", "Obowo", "It was carved out of Etiti Local Government Area with its "
     "headquarters at Isi Nweke.", "Isi Nweke"),
    ("Ogbomosho South", "Ogbomosho South", "Its headquarters are located in '''Arowomole''' "
     "area of [[Ogbomoso]].", "Arowomole"),
    ("Oturkpo", "Otukpo", "Otukpo is the [[headquarters]] of the Otukpo Local Government Area. "
     "It is the headquarters of the Idoma Nation.", "Otukpo"),
    ("Sardauna", "Sardauna, Taraba State", "The capital of the [[local government areas of "
     "Nigeria|LGA]] is [[Gembu, Nigeria|Gembu]], an ancient Mambilla settlement.", "Gembu"),
    ("Tarauni", "Tarauni", "Its Secretariat is in the locality of Unguwa Uku within the city "
     "of [[Kano (city)|Kano]].", "Unguwa Uku"),
    ("Udu", "Udu, Nigeria", "{{Infobox settlement|seat_type = Headquarters|seat = "
     "[[Otor-Udu]]}}\n'''Udu''' is a LGA with its local government headquarters at "
     "[[Otor-Udu]].", "Otor-Udu"),
    ("Ughelli South", "Ughelli South", "{{Infobox settlement|seat_type = Headquarters|seat = "
     "[[Otu-Jeremi]]}}\n[[Otu Jeremi]] is the headquarters of Ughelli South LGA.", "Otu-Jeremi"),
    # Nothing that names the area's seat.
    ("Ojo", "Ojo, Lagos", "'''Ojo''' is a LGA. It also houses the divisional headquarters of "
     "the 81st Division of the [[Nigerian Army]] and Navy Town.", None),
    ("Lagos Island", "Lagos Island", "It is the principal area in [[Lagos]] and was the "
     "capital of [[Lagos State]] until 1957.", None),
    ("Kuntaur", "Kuntaur", "'''Kuntaur''' is a small town. The town is the seat of the Kuntaur "
     "[[Local Government Areas of the Gambia|Local Government Area]] in the [[Niani District|"
     "district of Niani]].", "Kuntaur"),
    ("Nianija", "Nianija", "There are approximately 33 villages in Nianija, the capital of "
     "which is Chamen, located at the district's western edge.", "Chamen"),
    ("Careysburg", "Careysburg District", "[[Bensonville]] is the capital, and the total "
     "district population is 28,463.", "Bensonville"),
    # A county's capital in the district is not the district's seat.
    ("Commonwealth", "Commonwealth District, Grand Cape Mount County", "[[Robertsport]], the "
     "capital city of Grand Cape Mount County, is located in the district.", None),
    ("Kakata", "Kakata District", "{{Infobox settlement|seat_type = Capital city|seat = "
     "Kakata}}\n[[Kakata]], the [[capital city]] of Margibi County, is located in the "
     "district.", "Kakata"),
    ("Konobo", "Konobo District", "The administrative seat of the District is [[Ziah Town]].",
     "Ziah Town"),
]


class SeatTest(unittest.TestCase):
    def test_what_each_article_names(self):
        for name, title, text, want in CASES:
            with self.subTest(name=name):
                self.assertEqual(nc.choose(nc.seats(text, title, [name])), want)

    def test_two_different_seats_give_none(self):
        text = ("{{Infobox settlement|seat_type = Headquarters|seat = [[Alpha]]}}\n"
                "'''X''' is a LGA. Its headquarters are in the town of Beta.")
        found = nc.seats(text, "X", ["X"])
        self.assertEqual(found, {"infobox": "Alpha", "opening": "Beta"})
        self.assertIsNone(nc.choose(found))

    def test_a_body_sentence_counts_only_where_it_names_the_unit(self):
        body = ("'''X''' is a LGA.\n== History ==\nIts headquarters are in Gamma. "
                "The headquarters of the market union is at Delta.")
        self.assertEqual(nc.seats(body, "X", ["X"]), {})

    def test_the_revision_cited(self):
        src = nc.cite({"title": "Ife Central", "revid": 1377793025,
                       "timestamp": "2026-10-01T03:48:58Z"})
        self.assertEqual(src["name"], "English Wikipedia, Ife Central")
        self.assertEqual(src["url"], "https://en.wikipedia.org/w/index.php?"
                                     "title=Ife_Central&oldid=1377793025")
        self.assertEqual(src["year"], 2026)

    def test_bind_writes_the_seat_or_the_reason(self):
        polys = [{"id": "p1", "name": "Boripe", "wikidata": "Q1", "level": "admin2",
                  "parent": "Osun"},
                 {"id": "p2", "name": "Igabi", "wikidata": "Q2", "level": "admin2",
                  "parent": "Kaduna"},
                 {"id": "p3", "name": "Zaria", "wikidata": None, "level": "admin2",
                  "parent": "Kaduna"}]
        items = {"Q1": {"sitelinks": {"enwiki": "Boripe"}, "P36": []},
                 "Q2": {"sitelinks": {"enwiki": "Igabi"}, "P36": []}}
        got = {"p1": {"title": "Boripe", "revid": 1, "timestamp": "2026-09-16T02:41:55Z",
                      "text": "Its headquarters are in the town of [[Iragbiji]]."},
               "p2": {"title": "Igabi", "revid": 2, "timestamp": "2026-10-14T08:33:59Z",
                      "text": "'''Igabi''' is a Local Government Area in Kaduna State."}}
        records, _ = nc.bind("NGA", polys, items, got, nc.nigeria_why)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["p1"]["capital"], "Iragbiji")
        self.assertEqual(by["p1"]["sources"][0]["url"],
                         "https://en.wikipedia.org/w/index.php?title=Boripe&oldid=1")
        self.assertIn("article on Igabi names no headquarters", by["p2"]["capital"]["note"])
        self.assertIn("Wikidata names none", by["p2"]["capital"]["note"])
        self.assertIn("no article on this local government area", by["p3"]["capital"]["note"])
        self.assertTrue(all(r["match_by"] == "shape_id" for r in records))


if __name__ == "__main__":
    unittest.main()
