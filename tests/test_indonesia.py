"""Indonesia, read from the Indonesian Wikipedia: the 2010 ethnic tables in
their several shapes, the infobox religion figure with its citation, and the
national check that refuses a province table gone wrong.

The fixtures are the tables and infobox values as the runner printed them
(data/processed/last-run.log of the inspect and infobox probes), cut down.
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
import group_tree  # noqa: E402
from scripts import build_entities as be  # noqa: E402
from scripts.fetch_census import indonesia as m  # noqa: E402


def table(header: str, rows: list[str], caption: str = "") -> str:
    body = "\n|-\n".join(rows)
    return f'{{| class="wikitable"\n{caption}{header}\n|-\n{body}\n|}}\n'


SUMUT = table("! No !! Suku !! Jumlah 2010 !! %", [
    "| 1 || Batak || 5.785.716 || 44,75%",
    "| 2 || Jawa || 4.319.719 || 33,41%",
    "| 3 || Nias || 911.820 || 7,05%",
    "| 4 || Melayu || 771.668 || 5,97%",
    "| 5 || Tionghoa || 340.320 || 2,63%",
    "| 6 || Minangkabau || 333.241 || 2,58%",
    "| 7 || Aceh || 133.439 || 1,03%",
    "| 8 || Banjar || 125.707 || 0,97%",
    "| 9 || Banten || 46.640 || 0,36%",
    "| 10 || Sunda || 35.500 || 0,27%",
    "| 11 || Warga Negara Asing || 29.676 || 0,23%",
    "| 12 || Papua || 11.254 || 0,09%",
    "| 13 || Suku Lain || 85.619 || 0,66%",
    "| || '''Sumatera Utara''' || '''12.930.319''' || 100%",
])

# Two censuses side by side, a header continuation row, and a total row whose
# spanning first cell pushes the name out of its column.
JAMBI = table("! rowspan=2 | No !! rowspan=2 | Suku !! colspan=2 | Sensus 2000 !! colspan=2 | Sensus 2010", [
    "! Jumlah !! % !! Jumlah !! %",
    "| 1 || asal Jambi || 1.102.628 || 45,81% || 1.337.521 || 43,57%",
    "| 2 || [[Suku Jawa|Jawa]] || 664.931 || 27,62% || 893.156 || 29,10%",
    "| 3 || Melayu (selain Melayu Jambi) || 124.004 || 5,15% || 164.979 || 5,37%",
    "| 4 || asal Sumatera Selatan || - || - || 57.663 || 1,88%",
    "| 5 || Suku Lainnya || 76.647 || 3,18% || 616.449 || 20,08%",
    '| colspan="2" | Provinsi Jambi || 2.407.166 || 100% || 3.069.768 || 100%',
])

# Sub-rows under the native bundle, and the row carried as a residual.
NTT = table("! No !! Etnis !! Jumlah !! Persentasi", [
    "| 1 || Suku asli Nusa Tenggara Timur || 3.793.242 || 81,18%",
    "| || * Atoni || 927.753 || 19,85%",
    "| || * Manggarai || 727.404 || 15,57%",
    "| 2 || Asal Kalimantan || 678.090 || 14,51%",
    "| 3 || Jawa || 54.511 || 01,17%",
    "| 4 || Asal Sulawesi || 41.527 || 00,89%",
    "| 5 || Tionghoa || 8.039 || 00,17%",
    "| 6 || Lainnya || 97.239 || 02,08%",
    "| Total || Nusa Tenggara Timur || 4.672.648 || 100%",
])

# A citation in the caption arrives as a row of its own before the header.
KALTIM = table("! No !! Suku bangsa !! Jumlah (2010) !! %", [
    "| 1 || Jawa || 968.680 || 32,60%",
    "| 2 || Bugis || 555.789 || 18,71%",
    "| 3 || Dayak (termasuk Tidung dan Bulungan) || 177.823 || 5,98%",
    "| 4 || Kutai || 1.268.911 || 42,71%",
    "| || Total || 2.971.203 || 100,00%",
], caption="|+ Suku bangsa<ref>{{cite book |last = Gunawan |first = I Ketut}}</ref>\n|-\n")

# Percentages before the count.
JAKARTA = table("! No !! Suku Bangsa !! 1930 (%) !! 2010 (%) !! Jumlah (2010)", [
    "| 1 || Jawa || 11,01% || 36,17% || 3.453.453",
    "| 2 || Betawi || 36,19% || 28,29% || 2.700.722",
    "| 3 || Lainnya || 52,80% || 35,54% || 3.393.366",
    "| || Provinsi DKI Jakarta || 100% || 100% || 9.547.541",
])

GOVERNORS = table("! Potret !! Gubernur !! Mulai menjabat", ["| 135x135px || Someone || 2025"])

CILACAP = """{{Dati II
|nama = Kabupaten Cilacap
|penduduk = 2037899
|penduduktahun = [[2024]]
|pendudukref = <ref name="DUKCAPIL">{{cite web|url=https://gis.dukcapil.kemendagri.go.id/peta/|title=Visualisasi Data Kependudukan - Kementerian Dalam Negeri 2024|format=visual}}</ref>
|kepadatan = auto
|agama = {{ublist |item_style=white-space; |98,62% [[Islam]] |{{Tree list}}
* 1,21% [[Kekristenan]]
** 0,81% [[Protestan]]
** 0,40% [[Katolik]]
{{Tree list/end}} |0,10% [[Agama Buddha|Buddha]] |0,06% Kepercayaan |0,01% [[Hindu]]<ref>{{cite web|url=https://cilacapkab.bps.go.id/statictable/2020/08/11/34/penduduk-menurut-agama.html|title=Penduduk Kabupaten Cilacap Menurut Agama yang Dianut per Kecamatan 2019|website=www.cilacapkab.bps.go.id}}</ref>}}
|bahasa = [[Bahasa Jawa]]
}}
'''Kabupaten Cilacap''' adalah sebuah kabupaten.
"""

MANADO = """{{Kegunaan lain|Manado}}
{{Dati II
| nama = Kota Manado
| penduduk = 459409
| pendudukref = <ref name="DUKCAPIL"/>
| agama = {{ublist |item_style=white-space; |{{Tree list}} * 68,21% [[Kekristenan]] ** 62,89% [[Protestan]] ** 5,32% [[Katolik]] {{Tree list/end}} |30,93% [[Islam]] |0,62% [[Agama Buddha|Buddha]] |0,17% [[Hindu]] |0,06% [[Konghucu]]<ref name="DUKCAPIL"/><ref name=":0">{{cite web|url=https://sulut.bps.go.id/id/statistics-table/2/NzMyIzI=/persentase.html|title=Persentase Penduduk Menurut Kabupaten/Kota dan Agama yang Dianut, 2022-2023|date=12 September 2024|website=sulut.bps.go.id}}</ref>}}
}}
Text.<ref name="DUKCAPIL">{{cite web|url=https://gis.dukcapil.kemendagri.go.id/peta/|title=Visualisasi Data Kependudukan - Kementerian Dalam Negeri 2023}}</ref>
"""

SURABAYA = """{{Dati II
| nama = Kota Surabaya
| agama = {{ublist |item_style=white-space; |85,50% [[Islam]] |{{Tree list}} * 12,80% [[Kekristenan|Kristen]] ** 8,89% [[Protestan]] ** 3,91% [[Katolik]] {{Tree list/end}} |1,42 [[Agama Buddha|Buddha]] |0,25% [[Hindu]] |0,06% Kepercayaan |0,02% [[Konghucu]] |0,01% Lainnya<ref name="AGAMA">{{cite web|url=https://surabayakota.bps.go.id/dynamictable/2020/05/22/137/banyaknya-pemeluk-agama-2019.html|title=Banyaknya Pemeluk Agama Menurut Jenisnya 2019|publisher=[[Badan Pusat Statistik]] Kota Surabaya}}</ref>}}
}}
"""

TORAJA = """{{Dati II
| nama = Kabupaten Tana Toraja
| agama = {{ublist |item_style=white-space; |{{Tree list}} * 86,25% [[Kekristenan|Kristen]] ** 70,66% [[Protestan]] ** 15,59% [[Katolik]] {{Tree list/end}} |12,09% [[Islam]] |1,56% [[Hindu]] |0,09% [[Agama Buddha|Buddha]] |0,01% [[Aluk Todolo]]<ref name="AGAMA">{{cite web|url=https://sp2010.bps.go.id/index.php/site/tabel?search-tabel=Penduduk+Menurut+Wilayah+dan+Agama+yang+Dianut&tid=321&wid=7318000000|title=Penduduk Menurut Wilayah dan Agama yang Dianut di Kabupaten Tana Toraja|publisher=[[Badan Pusat Statistik]]}}</ref>}}
}}
"""

# The other layout: label first, <br>-separated, the Christian split dashed,
# and a citation whose <ref> tag lost its bracket.
BANGGAI = """{{Dati II
| nama = Kabupaten Banggai
| agama = [[Islam]] 70,84%<br> [[Kristen]] 17,24%<br>- [[Protestan]] 15,61%<br>- [[Katolik]] 1,63%<br> [[Hindu]] 11,08%<br> [[Agama Buddha|Buddha]] 0,83%<br> Lainnya 0,01%<ref name="BANGGAI2020">{{cite web|url=https://banggaikab.bps.go.id/publication/2020/02/28/x/kabupaten-banggai-dalam-angka-2020.html|title=Kabupaten Banggai Dalam Angka 2020}}</ref> ref name="AGAMA">{{cite web|url=https://sp2010.bps.go.id/x|title=Penduduk|accessdate=16 Februari 2020}}</ref>
}}
"""

UNCITED = """{{Dati II
| nama = Kabupaten Nowhere
| agama = {{ublist |90,00% [[Islam]] |10,00% [[Hindu]]}}
}}
"""

NATIONAL = table("! rowspan=2|Ethnic group !! colspan=2|Population", [
    "! Numbers !! Percentage",
    "| [[Javanese people|Javanese]] || 95,217,022 || 40.22",
    "| [[Sundanese people|Sundanese]] || 36,701,670 || 15.5",
    "| [[Batak]] || 8,466,969 || 3.58",
])
NATIONAL_MILLIONS = table("! rowspan=2|Ethnic group !! colspan=2|Population !! rowspan=2|Main regions", [
    "! Millions !! Percentage",
    "| Javanese || 94.843 || 40.06 || East Java",
])

POPULATIONS = table("! Nama provinsi !! Luas (km²) !! Populasi (2010) !! Populasi (2020)", [
    "| [[Sumatera Utara]] || 72.427,81 || 12.982.204 || 14.799.361",
    "| [[Jambi]] || 50.058,16 || 3.092.265 || 3.548.228",
])


def quiet(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        out = fn(*args, **kwargs)
    return out, buf.getvalue()


class EthnicTables(unittest.TestCase):
    def test_plain_table_is_read_and_shares_recomputed(self):
        counts, total = m.read_ethnicity(GOVERNORS + SUMUT, "North Sumatra", "Sumatera Utara")
        self.assertEqual(total, 12_930_319)
        self.assertEqual(counts["Batak"], 5_785_716)
        self.assertEqual(counts["Chinese Indonesian"], 340_320)
        self.assertEqual(counts["Foreign nationals"], 29_676)
        self.assertEqual(counts["Other ethnic groups"], 85_619)
        rows = m.ethnic_rows(counts, total)
        self.assertEqual(rows[0]["group"], "Batak")
        self.assertAlmostEqual(rows[0]["pct"], 44.75, places=2)
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0, delta=m.SUM_TOLERANCE)

    def test_two_census_table_reads_the_2010_column_and_spanned_total(self):
        counts, total = m.read_ethnicity(JAMBI, "Jambi", "Jambi")
        self.assertEqual(total, 3_069_768)
        self.assertEqual(counts["Javanese"], 893_156)
        self.assertEqual(counts["Jambi peoples"], 1_337_521)
        self.assertEqual(counts["Malay"], 164_979)          # the bracketed qualifier dropped
        self.assertEqual(counts["South Sumatra peoples"], 57_663)

    def test_sub_rows_skipped_and_kalimantan_row_carried_as_residual(self):
        counts, total = m.read_ethnicity(NTT, "East Nusa Tenggara", "Nusa Tenggara Timur")
        self.assertEqual(total, 4_672_648)
        self.assertEqual(counts["East Nusa Tenggara peoples"], 3_793_242)
        self.assertNotIn("Atoni", counts)
        self.assertEqual(counts["Other ethnic groups"], 678_090 + 97_239)

    def test_caption_row_before_the_header(self):
        counts, total = m.read_ethnicity(KALTIM, "East Kalimantan", "Kalimantan Timur")
        self.assertEqual(total, 2_971_203)
        self.assertEqual(counts["Dayak"], 177_823)
        self.assertEqual(counts["Kutai"], 1_268_911)

    def test_percentages_before_the_count(self):
        counts, total = m.read_ethnicity(JAKARTA, "Jakarta Special Capital Region",
                                         "Daerah Khusus Ibukota Jakarta")
        self.assertEqual(total, 9_547_541)
        self.assertEqual(counts["Betawi"], 2_700_722)

    def test_unknown_label_refuses(self):
        bad = table("! No !! Suku !! Jumlah 2010 !! %", [
            "| 1 || Jawa || 900 || 90,00%", "| 2 || Martian || 100 || 10,00%",
            "| || Total || 1.000 || 100%"])
        with self.assertRaises(SystemExit) as cm:
            m.read_ethnicity(bad, "Bali", "Bali")
        self.assertIn("Martian", str(cm.exception))

    def test_no_table_is_none(self):
        out, printed = quiet(m.read_ethnicity, GOVERNORS, "Bali", "Bali")
        self.assertIsNone(out)
        self.assertIn("no 2010 ethnic table", printed)

    def test_national_table_is_the_one_in_counts(self):
        national = m.national_figures(NATIONAL_MILLIONS + NATIONAL)
        self.assertEqual(national["Javanese"], 95_217_022)
        self.assertEqual(m.census_populations(POPULATIONS)["Jambi"], 3_092_265)

    def test_national_check_refuses_a_short_javanese_sum(self):
        national = {"Javanese": 95_217_022}
        with self.assertRaises(SystemExit):
            quiet(m.check_national, national, {}, {"Central Java": 31_560_859})
        _, printed = quiet(m.check_national, national, {"Sundanese": 1},
                           {"Central Java": 94_900_000})
        self.assertIn("national check", printed)


class InfoboxReligion(unittest.TestCase):
    def test_christian_parent_dropped_and_bps_citation_named(self):
        reading = m.read_religion(CILACAP, "Kabupaten Cilacap")
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows["Islam"], 98.62)
        self.assertEqual(rows["Protestantism"], 0.81)
        self.assertEqual(rows["Catholicism"], 0.40)
        self.assertNotIn("Christianity", rows)
        self.assertEqual(rows["Kepercayaan (traditional belief)"], 0.06)
        self.assertEqual(reading["kind"], "bps")
        self.assertEqual(reading["year"], 2019)
        fields = m.religion_fields(reading, "Kabupaten Cilacap")
        self.assertIn("BPS", fields["religion_source"]["name"])
        self.assertIn("not a census count", fields["religion_note"])

    def test_named_reference_defined_elsewhere_and_the_better_citation_wins(self):
        reading = m.read_religion(MANADO, "Kota Manado")
        self.assertEqual(reading["kind"], "bps")
        self.assertEqual(reading["year"], 2023)
        self.assertEqual(reading["rows"][0], {"group": "Protestantism", "pct": 62.89})
        self.assertEqual(len(reading["all"]), 2)

    def test_missing_percent_sign_and_other(self):
        reading = m.read_religion(SURABAYA, "Kota Surabaya")
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows["Buddhism"], 1.42)
        self.assertEqual(rows["Other religion"], 0.01)
        self.assertAlmostEqual(sum(rows.values()), 100.0, delta=m.RELIGION_TOLERANCE)

    def test_census_citation_is_dated_2010_and_named_a_count(self):
        reading = m.read_religion(TORAJA, "Kabupaten Tana Toraja")
        self.assertEqual(reading["kind"], "census2010")
        self.assertEqual(reading["year"], 2010)
        self.assertIn("Aluk Todolo", {r["group"] for r in reading["rows"]})
        note = m.religion_fields(reading, "Kabupaten Tana Toraja")["religion_note"]
        self.assertNotIn("not a census count", note)

    def test_label_first_layout_and_a_broken_reference_tag(self):
        reading = m.read_religion(BANGGAI, "Kabupaten Banggai")
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows, {"Islam": 70.84, "Protestantism": 15.61, "Catholicism": 1.63,
                                "Hinduism": 11.08, "Buddhism": 0.83, "Other religion": 0.01})
        self.assertEqual((reading["kind"], reading["year"]), ("bps", 2020))

    def test_a_short_list_gets_a_remainder_and_an_overrun_is_refused(self):
        rows, why = m.religion_shares([("Islam", 97.0), ("Hindu", 2.0)])
        self.assertIsNone(why)
        self.assertEqual(rows[-1], {"group": m.REMAINDER, "pct": 1.0})
        rows, why = m.religion_shares([("Islam", 70.86), ("Kristen", 24.88),
                                       ("Protestan", 24.97), ("Katolik", 0.91), ("Hindu", 5.25)])
        self.assertIn("102.00", why)

    def test_uncited_figure_is_not_read(self):
        out, printed = quiet(m.read_religion, UNCITED, "Kabupaten Nowhere")
        self.assertIsNone(out)
        self.assertIn("no citation", printed)

    def test_shares_that_do_not_add_up_are_refused(self):
        rows, why = m.religion_shares([("Islam", 80.0), ("Hindu", 10.0)])
        self.assertEqual(rows, [])
        self.assertIn("add to", why)
        rows, why = m.religion_shares([("Islam", 90.0), ("Jedi", 10.0)])
        self.assertIn("Jedi", why)


class Records(unittest.TestCase):
    def test_province_and_regency_records_end_to_end(self):
        pages = {
            ("Ethnic groups in Indonesia", "en"): NATIONAL,
            ("Demografi Indonesia", "id"): POPULATIONS,
            ("Sumatera Utara", "id"): MANADO.replace("Kota Manado", "Sumatera Utara") + SUMUT,
            ("Jambi", "id"): JAMBI,
            ("Kabupaten Cilacap", "id"): CILACAP,
        }

        def fake_fetch(title, lang="id"):
            return pages.get((title, lang), ""), title

        # The national check needs the provinces to add up, so the two read
        # here are given the whole census's Javanese between them.
        national = NATIONAL.replace("95,217,022", f"{4_319_719 + 893_156:,}")
        pages[("Ethnic groups in Indonesia", "en")] = national
        (records, javanese), printed = quiet(m.province_records, fake_fetch)
        self.assertEqual(len(records), 34)
        self.assertEqual(javanese, {"North Sumatra": 4_319_719, "Jambi": 893_156})
        by_name = {r["name"]: r for r in records}
        sumut = by_name["North Sumatra"]
        self.assertEqual(sumut["id"], "IDN-north-sumatra")
        self.assertEqual(sumut["level"], "admin1")
        self.assertEqual(sumut["ethnicity_year"], 2010)
        self.assertEqual(sumut["ethnicity"][0]["group"], "Batak")
        self.assertEqual(sumut["religion"][0]["group"], "Protestantism")
        self.assertEqual(sumut["aliases"], ["Sumatera Utara"])
        self.assertEqual({s["field"] for s in sumut["sources"]}, {"ethnicity", "religion"})
        self.assertEqual(by_name["Bali"]["ethnicity"]["status"], "not_available")
        self.assertEqual(by_name["Bangka-Belitung Islands"]["ethnicity"]["status"],
                         "not_available")
        self.assertIn("2022", by_name["Papua"]["religion"].get("note", ""))

        regencies, printed = quiet(m.regency_records, fake_fetch)
        self.assertEqual(len(regencies), 1)
        cilacap = regencies[0]
        self.assertEqual(cilacap["id"], "IDN-central-java-cilacap")
        self.assertEqual(cilacap["parent"], "IDN-central-java")
        self.assertEqual(cilacap["parent_name"], "Central Java")
        self.assertEqual(cilacap["level"], "admin2")
        self.assertEqual(cilacap["religion_year"], 2019)
        self.assertIn("not read", printed)
        self.assertNotIn("Hutan", printed)
        self.assertNotIn("Kabupaten Cilacap", printed)

    def test_regency_titles(self):
        self.assertEqual(m.regency_title("Kota Medan"), "Kota Medan")
        self.assertEqual(m.regency_title("Deli Serdang"), "Kabupaten Deli Serdang")
        self.assertEqual(m.regency_title("Toba Samosir"), "Kabupaten Toba")

    def test_every_map_name_is_a_province_and_the_file_is_registered(self):
        shapes = {s["name"] for s in m.shapes("admin1")}
        self.assertEqual(shapes, set(m.PROVINCES))
        self.assertIn("indonesia.json", be.ADAPTER_FILES)
        self.assertNotIn("IDN", be.ADAPTER_GAPS)
        self.assertIn("IDN", be.ADAPTER_HINTS)


class Classification(unittest.TestCase):
    def test_every_label_the_adapter_writes_has_a_family(self):
        for label in set(m.ETHNIC_LABELS.values()) | set(m.RESIDUAL_BY_PROVINCE.values()):
            if label == "Moluccan":
                continue    # Maluku's peoples are Austronesian and Papuan both; left unplaced
            self.assertTrue(group_tree.hue("ethnicity", label), label)
        for label in set(m.RELIGION_LABELS.values()):
            self.assertTrue(group_tree.hue("religion", label), label)
        self.assertEqual(cg.ancestry("ethnicity", "Chinese Indonesian")[1],
                         "Han and Sinitic peoples")
        self.assertEqual(cg.ancestry("ethnicity", "Papuan")[1], "Melanesian peoples")


if __name__ == "__main__":
    unittest.main()
