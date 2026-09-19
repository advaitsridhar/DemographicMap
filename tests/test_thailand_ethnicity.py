"""Thailand's provinces under the owner's decision: an estimate built from the
census's home-language minorities and a regional assignment, labelled as one.

The fixture is the provincial data article's table in the shape thailand.py
reads it, with the linguistic-minorities cells as the runner printed them
for these provinces (data/processed/last-run.log of the probe that read the
whole table), and a cut of the 'Provinces of Thailand' population table.
"""

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import canonical_groups as cg  # noqa: E402
import common  # noqa: E402
from scripts import build_entities as be  # noqa: E402
from scripts.fetch_census import thailand  # noqa: E402
from scripts.fetch_census import thailand_ethnicity as m  # noqa: E402

HEADER = ("! province name !! Thai nationals in 1970 !! Thai nationals in 2000 !! "
          "Buddhist in 1990 !! Buddhist in 2000 !! Muslim in 1990 !! Muslim in 2000 !! "
          "Christian in 1990 !! Christian in 2000 !! Linguistic minorities in 1990 !! "
          "Linguistic minorities in 2000")


def row(link: str, report: str, cell_1990: str, cell_2000: str) -> str:
    ref = f"<ref>{{{{cite web|url=http://web.nso.go.th/pop2000/finalrep/{report} |title=x}}}}</ref>"
    return (f"| [[{link}]]{ref} || 99.0% || 99.5% || 90.0% || 90.0% || 5.0% || 5.0% || "
            f"N/A || N/A || {cell_1990} || {cell_2000}")


ROWS = [
    row("Surin province|Surin", "surin.pdf", "Khmer (63.4%)", "Khmer (47.2%)"),
    row("Yala province|Yala", "yala.pdf", "Malay (62.4%), Chinese (4.4%)",
        "Malay (66.1%), Chinese (3.0%)"),
    row("Mae Hong Son province|Mae Hong Son", "mhs.pdf", "Hill tribe languages (51.1%)",
        "Hill tribe languages (63.0%)"),
    row("Bangkok", "bkk.pdf", "English (0.1%)",
        "English (0.7%), Indian languages (0.1%), Japanese (0.1%)"),
    row("Phra Nakhon Si Ayutthaya province|Phra Nakhon Si Ayutthaya", "ayu.pdf", "N/A",
        "Malay-Yawi (<0.1%), Laotian and Vietnamese (<0.1%), Japanese (0.02%), Khmer (0.02%)"),
    row("Amnat Charoen province|Amnat Charoen", "amnat.pdf", "N/A", "N/A"),
    row("Ranong province|Ranong", "ranong.pdf", "Malay (1.1%)",
        "Malay (0.5%), Burmese and Peguan (7.0%)"),
]


def wikitext(rows=ROWS) -> str:
    return ('{| class="wikitable sortable"\n|+ Data\n' + HEADER + "\n|-\n"
            + "\n|-\n".join(rows) + "\n|}\n")


PROVINCES = """{| class="wikitable sortable"
! class=unsortable| Seal !! Name !! Name (in Thai) !! Population (December 2024) !! Area (km<sup>2</sup>)
|-
| 20px || Bangkok (special administrative area) || กรุงเทพมหานคร || 5,456,000 || 1,564
|-
| 20px || Amnat Charoen || อำนาจเจริญ || 372,000 || 3,290
|-
| 20px || Surin || สุรินทร์ || 1,380,000 || 8,124
|-
| 20px || Yala || ยะลา || 550,000 || 4,521
|-
| 20px || Mae Hong Son || แม่ฮ่องสอน || 290,000 || 12,681
|-
| 20px || Phra Nakhon Si Ayutthaya || พระนครศรีอยุธยา || 820,000 || 2,557
|-
| 20px || Ranong || ระนอง || 195,000 || 3,298
|}
"""


def provinces_fixture() -> str:
    """The seven provinces above and seventy filler rows, since the reader
    only trusts a table with the whole country in it."""
    filler = "".join(f"|-\n| 20px || Filler {chr(65 + i // 26)}{chr(65 + i % 26)} || x || 1,000 || 1\n"
                     for i in range(70))
    return PROVINCES.replace("|}\n", filler + "|}\n")


class Regions(unittest.TestCase):
    def test_the_four_regions_cover_the_77_provinces_once(self):
        sets = (m.NORTHERN, m.NORTHEASTERN, m.SOUTHERN, m.CENTRAL)
        self.assertEqual(sum(len(s) for s in sets), 77)
        self.assertEqual(len(set().union(*sets)), 77)

    def test_the_regions_spell_provinces_the_way_the_religion_adapter_does(self):
        # The two files write the same ids, which is how their fields merge
        # onto one province; a spelling that drifts leaves a second unit.
        rows = thailand.table(wikitext())
        for cells in rows[1:]:
            bare, _ = thailand.province(cells[0])
            self.assertIn(bare, m.REGION, bare)
        for bare in thailand.ALIASES:
            self.assertIn(bare, m.REGION, bare)


class Minorities(unittest.TestCase):
    def test_a_cell_is_read_under_the_maps_labels(self):
        shares, below = m.minorities("Malay (66.1%), Chinese (3.0%)")
        self.assertEqual(shares, {"Malay": 66.1, "Chinese": 3.0})
        self.assertEqual(below, [])

    def test_below_a_tenth_is_named_and_not_carried(self):
        shares, below = m.minorities(
            "Malay-Yawi (<0.1%), Laotian and Vietnamese (<0.1%), Japanese (0.02%), Khmer (0.02%)")
        self.assertEqual(shares, {})
        self.assertEqual(below, ["Malay", "Lao and Vietnamese", "Japanese", "Khmer"])

    def test_not_available_is_no_minority(self):
        self.assertEqual(m.minorities("N/A"), ({}, []))

    def test_a_wording_never_read_for_refuses(self):
        with self.assertRaises(SystemExit):
            m.minorities("Martian (2.0%)")

    def test_a_cell_that_is_not_minorities_refuses(self):
        with self.assertRaises(SystemExit):
            m.minorities("47.2%")


class Build(unittest.TestCase):
    def setUp(self):
        self.records = {r["id"]: r for r in m.build(wikitext())}

    def test_every_province_is_an_estimate_and_never_a_list(self):
        for rec in self.records.values():
            eth = rec["ethnicity"]
            self.assertTrue(common.is_estimate(eth), rec["id"])
            self.assertEqual(eth["status"], common.MODELLED)
            self.assertEqual(eth["method"], m.METHOD)
            self.assertEqual(len(eth["inputs"]), 2)
            self.assertTrue(eth["note"].startswith("Modelled from the 2000 census"), eth["note"])
            self.assertIn("a model, not a count", eth["note"])
            # Short: the method lives in the docs, not in every row.
            self.assertLess(len(eth["note"]), 1000, rec["id"])
            self.assertEqual(eth["census_year"], 2000)

    def test_every_province_sums_to_a_hundred(self):
        for rec in self.records.values():
            total = sum(r["pct"] for r in rec["ethnicity"]["estimate"])
            self.assertAlmostEqual(total, 100.0, delta=0.3, msg=rec["id"])

    def test_the_regional_group_takes_the_remainder(self):
        surin = self.records["THA-Surin"]["ethnicity"]
        self.assertEqual(surin["regional_group"], "Isan (Lao)")
        self.assertEqual(surin["estimate"],
                         [{"group": "Isan (Lao)", "pct": 52.8}, {"group": "Khmer", "pct": 47.2}])
        yala = {r["group"]: r["pct"] for r in self.records["THA-Yala"]["ethnicity"]["estimate"]}
        self.assertEqual(yala, {"Malay": 66.1, "Southern Thai": 30.9, "Chinese": 3.0})
        mhs = {r["group"]: r["pct"]
               for r in self.records["THA-Mae_Hong_Son"]["ethnicity"]["estimate"]}
        self.assertEqual(mhs, {"Hill tribe languages (census category)": 63.0,
                               "Northern Thai": 37.0})
        bangkok = {r["group"]: r["pct"] for r in self.records["THA-Bangkok"]["ethnicity"]["estimate"]}
        self.assertEqual(bangkok["Central Thai"], 99.1)

    def test_a_province_with_no_named_minority_is_all_its_region(self):
        self.assertEqual(self.records["THA-Amnat_Charoen"]["ethnicity"]["estimate"],
                         [{"group": "Isan (Lao)", "pct": 100.0}])

    def test_the_note_names_what_was_printed_below_a_tenth(self):
        note = self.records["THA-Phra_Nakhon_Si_Ayutthaya"]["ethnicity"]["note"]
        self.assertIn("Malay, Lao and Vietnamese, Japanese, Khmer printed below 0.1%", note)
        self.assertIn("no minority at or above 0.1%", note)

    def test_the_census_categories_keep_their_own_names(self):
        ranong = {r["group"]: r["pct"] for r in self.records["THA-Ranong"]["ethnicity"]["estimate"]}
        self.assertEqual(ranong, {"Southern Thai": 92.5, "Burmese and Mon": 7.0, "Malay": 0.5})

    def test_ids_names_and_aliases_match_the_religion_adapter(self):
        religion = {r["id"]: r for r in thailand.build(wikitext())}
        self.assertEqual(set(religion), set(self.records))
        for entity_id, rec in self.records.items():
            self.assertEqual(rec["name"], religion[entity_id]["name"])
            self.assertEqual(rec.get("aliases"), religion[entity_id].get("aliases"))
            self.assertEqual(rec["parent"], "THA")
            self.assertEqual(rec["level"], "admin1")
            self.assertEqual(rec["country"], "THA")

    def test_the_source_is_the_report_the_row_cites_and_the_maps(self):
        srcs = self.records["THA-Surin"]["sources"]
        self.assertEqual([s["field"] for s in srcs], ["ethnicity", "ethnicity"])
        self.assertEqual(srcs[0]["url"], "http://web.nso.go.th/pop2000/finalrep/surin.pdf")
        self.assertIn("Ethnolinguistic Maps of Thailand", srcs[1]["name"])

    def test_religion_is_left_to_the_other_adapter(self):
        for rec in self.records.values():
            self.assertTrue(common.is_gap(rec["religion"]))
            self.assertFalse(common.is_estimate(rec["religion"]))
            self.assertTrue(common.is_gap(rec["language"]))

    def test_a_renamed_province_refuses(self):
        text = wikitext([row("Elsewhere province|Elsewhere", "x.pdf", "N/A", "N/A")])
        with self.assertRaises(SystemExit):
            m.build(text)

    def test_minorities_past_a_hundred_refuse(self):
        text = wikitext([row("Surin province|Surin", "x.pdf", "N/A", "Khmer (60.0%), Malay (50.0%)")])
        with self.assertRaises(SystemExit):
            m.build(text)

    def test_a_changed_header_refuses(self):
        text = wikitext().replace("Linguistic minorities in 2000", "Languages in 2000")
        with self.assertRaises(SystemExit):
            m.build(text)


class NationalCheck(unittest.TestCase):
    def test_the_population_table_is_read_by_key(self):
        pops = m.populations(provinces_fixture())
        self.assertEqual(pops[m.key("Bangkok")], 5_456_000)
        self.assertEqual(pops[m.key("Phra Nakhon Si Ayutthaya")], 820_000)

    def test_keys_join_the_two_articles_spellings(self):
        self.assertEqual(m.key("Phang Nga"), m.key("Phangnga"))
        self.assertEqual(m.key("Si Sa Ket"), m.key("Sisaket"))
        self.assertEqual(m.key("Nong Bua Lamphu"), m.key("Nong Bua Lam Phu"))

    def test_the_national_aggregate_is_population_weighted(self):
        records = m.build(wikitext())
        weights = {m.key(n): p for n, p in (
            ("Bangkok", 5_456_000), ("Amnat Charoen", 372_000), ("Surin", 1_380_000),
            ("Yala", 550_000), ("Mae Hong Son", 290_000),
            ("Phra Nakhon Si Ayutthaya", 820_000), ("Ranong", 195_000))}
        shares = m.national(records, weights)
        total = sum(weights.values())
        self.assertAlmostEqual(shares["Khmer"], round(100 * 47.2 * 1_380_000 / 100 / total, 1), 1)
        self.assertAlmostEqual(sum(shares.values()), 100.0, delta=0.5)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            m.compare(records, weights)
        text = out.getvalue()
        self.assertIn("Ethnolinguistic Maps", text)
        self.assertIn("Khmer", text)
        self.assertIn("inside a regional remainder here", text)   # Nyaw, Phu Thai, Kuy, Karen

    def test_a_province_without_a_weight_refuses(self):
        with self.assertRaises(SystemExit):
            m.national(m.build(wikitext()), {})

    def test_a_missing_table_refuses(self):
        with self.assertRaises(SystemExit):
            m.populations("{|\n! Seal !! Nothing\n|-\n| a || b\n|}\n")


class TreeAndBuild(unittest.TestCase):
    def test_the_labels_the_model_writes_are_placed(self):
        for label in ("Central Thai", "Isan (Lao)", "Northern Thai", "Southern Thai",
                      "Khmer", "Malay", "Chinese", "Lao and Vietnamese",
                      "Hill tribe languages (census category)"):
            self.assertEqual(cg.family("ethnicity", label), "East and Southeast Asian ancestry",
                             label)
        self.assertEqual(cg.ancestry("ethnicity", "Burmese and Mon")[1],
                         "Himalayan and Tibeto-Burman peoples")
        self.assertEqual(cg.ancestry("ethnicity", "Thai Chinese")[1], "Han and Sinitic peoples")
        for label in m.CATEGORIES.values():
            self.assertGreater(len(cg.ancestry("ethnicity", label)), 1, label)

    def test_registered_with_the_surveys_and_after_the_religion_file_is_not_required(self):
        files = be.ADAPTER_FILES
        self.assertIn("thailand_ethnicity.json", files)
        # After Korea's survey (and the nationality file that sits with it),
        # before every census file.
        self.assertGreater(files.index("thailand_ethnicity.json"),
                           files.index("korea_survey_province.json"))
        self.assertLess(files.index("thailand_ethnicity.json"),
                        files.index("japan_prefecture.json"))

    def test_thailand_stays_a_documented_gap_that_names_the_model(self):
        self.assertIn("THA", be.ADAPTER_GAPS)
        self.assertIn("modelled", be.ADAPTER_GAPS["THA"])
        self.assertNotIn("THA", common.NOT_COLLECTED_POLICY)

    def test_the_build_script_runs_it(self):
        text = (ROOT / "scripts" / "build_all.sh").read_text()
        self.assertIn("scripts.fetch_census.thailand_ethnicity", text)


if __name__ == "__main__":
    unittest.main()
