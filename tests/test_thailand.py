"""Thailand: religion by province from the provincial data article, with the
one row where the article is not what the report prints put right.

No network: the article's table is written here in the shape thailand.py reads.
"""

import unittest

from scripts.fetch_census import thailand as t

HEADER = ("! province name !! Thai nationals in 1970 !! Thai nationals in 2000 !! "
          "Buddhist in 1990 !! Buddhist in 2000 !! Muslim in 1990 !! Muslim in 2000 !! "
          "Christian in 1990 !! Christian in 2000 !! Linguistic minorities in 1990 !! "
          "Linguistic minorities in 2000")


def row(link, report, buddhist_2000, thai_2000="99.6%"):
    ref = f"<ref>{{{{cite web|url=http://web.nso.go.th/pop2000/finalrep/{report} |title=x}}}}</ref>"
    return (f"| [[{link}]]{ref} || 99.5% || {thai_2000} || 99.7% || {buddhist_2000} || "
            f"0.1% || 0.1% || N/A || N/A || N/A || N/A")


def wikitext(rows):
    return ('{| class="wikitable sortable"\n|+ Data\n' + HEADER + "\n|-\n"
            + "\n|-\n".join(rows) + "\n|}\n")


def religion(records, name):
    rec = next(r for r in records if r["name"] == f"{name} Province")
    return {g["group"]: g["pct"] for g in rec["religion"]}, rec["religion_note"]


class CorrectionTest(unittest.TestCase):
    def test_sukhothai_takes_the_reports_buddhist_share(self):
        records = t.build(wikitext([
            row("Sukhothai province|Sukhothai", "sukhofn.pdf", "99.8%"),
            row("Phrae province|Phrae", "phraefn.pdf", "99.8%")]))
        shares, note = religion(records, "Sukhothai")
        self.assertEqual(shares["Buddhism"], 99.6)
        self.assertEqual(shares["Other or not stated"], 0.3)
        self.assertIn("wrong way round", note)
        # Another province with the same figure is left as the article has it.
        shares, note = religion(records, "Phrae")
        self.assertEqual(shares["Buddhism"], 99.8)
        self.assertNotIn("wrong way round", note)

    def test_an_article_put_right_needs_nothing(self):
        records = t.build(wikitext([row("Sukhothai province|Sukhothai", "sukhofn.pdf",
                                        "99.6%", thai_2000="99.8%")]))
        shares, note = religion(records, "Sukhothai")
        self.assertEqual(shares["Buddhism"], 99.6)
        self.assertNotIn("wrong way round", note)

    def test_an_article_changed_otherwise_refuses(self):
        with self.assertRaises(SystemExit):
            t.build(wikitext([row("Sukhothai province|Sukhothai", "sukhofn.pdf", "98.0%")]))


if __name__ == "__main__":
    unittest.main()
