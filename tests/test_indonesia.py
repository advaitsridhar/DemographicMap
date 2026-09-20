"""Indonesia, read from the Indonesian Wikipedia: the 2010 ethnic tables in
their several shapes, the infobox religion figure with its citation, and the
national check that refuses a province table gone wrong.

The fixtures are the tables and infobox values as the runner printed them
(data/processed/last-run.log of the inspect and infobox probes), cut down.
"""

import io
import re
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


# Puncak Jaya gives its Hindus and Buddhists in one bucket, and its head count
# cites the registry by a name the page defines further down.
PUNCAK_JAYA = """{{Dati II
|nama = Kabupaten Puncak Jaya
|penduduk = 220393
|penduduktahun = 31 Desember [[2024]]
|pendudukref = <ref name="DUKCAPIL"/>
|agama = {{ublist |item_style=white-space; |{{Tree list}} * 98,82% [[Kekristenan]] ** 98,19% [[Protestan]] ** 0,63% [[Katolik]] {{Tree list/end}} |1,17% [[Islam]] |0,01% [[Hindu]]/[[Buddha]]<ref name="DUKCAPIL"/>}}
}}
Teks.<ref name="DUKCAPIL">{{cite web|url=https://gis.dukcapil.kemendagri.go.id/peta/|title=Visualisasi Data Kependudukan - Kementerian Dalam Negeri 2024}}</ref>
"""

DUKCAPIL_DEFINITION = (
    'Teks.<ref name="DUKCAPIL">{{cite web|url=https://gis.dukcapil.kemendagri.go.id/peta/'
    '|title=Visualisasi Data Kependudukan - Kementerian Dalam Negeri 2024}}</ref>\n')


# The four the faith list defeated, as the articles write them. Not one is a
# missing figure: a doubled percent sign, a third decimal place, and a link
# abutting the word before it.
BANGKA_BARAT = (
    "{{Dati II\n|nama = Kabupaten Bangka Barat\n"
    "|agama = {{ublist |item_style=white-space; |92,73% [[Islam]] "
    "|3,63% [[Agama Buddha|Buddha]] |{{Tree list}} * 1,93%% [[Kristen]] "
    "** 1,42% [[Protestan]] ** 0,51% [[Katolik]] {{Tree list/end}} "
    "|1,70% [[Konghucu]] |0,01% [[Hindu]]<ref name=\"DUKCAPIL\"/>}}\n}}\n"
    + DUKCAPIL_DEFINITION)

JAKARTA_TIMUR = (
    "{{Dati II\n|nama = Kota Administrasi Jakarta Timur\n"
    "|agama = {{ublist |item_style=white-space; |88,76% [[Islam]] |{{Tree list}} "
    "* 10,62% [[Kekristenan]] ** 8,06% [[Protestan]] ** 2,56% [[Katolik]] "
    "{{Tree list/end}} |0,454% [[Agama Buddha|Buddha]] |0,17% [[Hindu]]"
    "<ref name=\"AGAMA\"/>}}\n}}\n"
    'Teks.<ref name="AGAMA">{{cite web|url=https://statistik.jakarta.go.id/'
    'agama-penduduk-dki-jakarta-tahun-2020/|title=Agama Penduduk DKI Jakarta '
    '2020}}</ref>\n')

MINAHASA_TENGGARA = (
    "{{Dati II\n|nama = Kabupaten Minahasa Tenggara\n"
    "|agama = {{ublist |item_style=white-space; |{{Tree list}} * 81,97% [[Kristen]] "
    "** 80,93% [[Protestan]] ** 1,04% [[Katolik]] {{Tree list/end}} |18,02% [[Islam]] "
    "|0,01% [[Buddhisme|Budha]] dan[[Agama Hindu|Hindu]]<ref name=\"AGAMA\"/>}}\n}}\n"
    'Teks.<ref name="AGAMA">{{cite web|url=https://sp2010.bps.go.id/index.php/site/'
    'tabel?search-tabel=Penduduk+Menurut+Wilayah+dan+Agama+yang+Dianut&tid=321'
    '|title=Penduduk Menurut Wilayah dan Agama yang Dianut di Kabupaten Minahasa '
    'Tenggara}}</ref>\n')


# A head count with no reference at all, beside a cited composition.
UNCITED_COUNT = """{{Dati II
| nama = Kabupaten Contoh
| penduduk = 123.456
| penduduktahun = [[2024]]
| agama = {{ublist |100,00% [[Islam]]<ref name="X">{{cite web|url=https://gis.dukcapil.kemendagri.go.id/peta/|title=Visualisasi Data Kependudukan 2024}}</ref>}}
}}
"""


class EthnicTables(unittest.TestCase):
    def test_plain_table_is_read_and_shares_recomputed(self):
        counts, total, _ = m.read_ethnicity(GOVERNORS + SUMUT, "North Sumatra", "Sumatera Utara")
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
        counts, total, _ = m.read_ethnicity(JAMBI, "Jambi", "Jambi")
        self.assertEqual(total, 3_069_768)
        self.assertEqual(counts["Javanese"], 893_156)
        self.assertEqual(counts["Jambi peoples"], 1_337_521)
        self.assertEqual(counts["Malay"], 164_979)          # the bracketed qualifier dropped
        self.assertEqual(counts["South Sumatra peoples"], 57_663)

    def test_sub_rows_skipped_and_kalimantan_row_carried_as_residual(self):
        counts, total, _ = m.read_ethnicity(NTT, "East Nusa Tenggara", "Nusa Tenggara Timur")
        self.assertEqual(total, 4_672_648)
        self.assertEqual(counts["East Nusa Tenggara peoples"], 3_793_242)
        self.assertNotIn("Atoni", counts)
        self.assertEqual(counts["Other ethnic groups"], 678_090 + 97_239)

    def test_caption_row_before_the_header(self):
        counts, total, _ = m.read_ethnicity(KALTIM, "East Kalimantan", "Kalimantan Timur")
        self.assertEqual(total, 2_971_203)
        self.assertEqual(counts["Dayak"], 177_823)
        self.assertEqual(counts["Kutai"], 1_268_911)

    def test_percentages_before_the_count(self):
        counts, total, _ = m.read_ethnicity(JAKARTA, "Jakarta Special Capital Region",
                                         "Daerah Khusus Ibukota Jakarta")
        self.assertEqual(total, 9_547_541)
        self.assertEqual(counts["Betawi"], 2_700_722)

    def test_unknown_label_refuses_unless_small(self):
        bad = table("! No !! Suku !! Jumlah 2010 !! %", [
            "| 1 || Jawa || 900 || 90,00%", "| 2 || Martian || 100 || 10,00%",
            "| || Total || 1.000 || 100%"])
        with self.assertRaises(SystemExit) as cm:
            m.read_ethnicity(bad, "Bali", "Bali")
        self.assertIn("Martian", str(cm.exception))
        small = table("! No !! Suku !! Jumlah 2010 !! %", [
            "| 1 || Jawa || 9.950 || 99,50%", "| 2 || Martian || 50 || 0,50%",
            "| || Total || 10.000 || 100%"])
        (counts, total, remark), printed = quiet(m.read_ethnicity, small, "Bali", "Bali")
        self.assertEqual(counts["Other ethnic groups"], 50)
        self.assertIn("'Martian' (0.5%)", remark)

    def test_no_table_is_none(self):
        out, printed = quiet(m.read_ethnicity, GOVERNORS, "Bali", "Bali")
        self.assertIsNone(out)
        self.assertIn("no 2010 ethnic table", printed)

    def test_national_table_is_the_one_in_counts(self):
        national = m.national_figures(NATIONAL_MILLIONS + NATIONAL)
        self.assertEqual(national["Javanese"], 95_217_022)
        self.assertEqual(m.census_populations(POPULATIONS)["Jambi"], 3_092_265)

    def test_national_check_remarks_on_a_little_and_refuses_a_lot(self):
        national = {"Javanese": 95_217_022}
        with self.assertRaises(SystemExit):
            quiet(m.check_national, national, {}, {"Central Java": 31_560_859})
        remark, printed = quiet(m.check_national, national, {"Sundanese": 1},
                                {"Central Java": 94_900_000})
        self.assertIn("national check", printed)
        self.assertEqual(remark, "")
        remark, printed = quiet(m.check_national, national, {}, {"Central Java": 94_000_000})
        self.assertIn("98.7% of the census's national figure", remark)


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
        self.assertIn("not the census", fields["religion_note"])
        self.assertLessEqual(fields["religion_note"].count(". "), 2)

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
        self.assertIn("A census count.", note)

    def test_label_first_layout_and_a_broken_reference_tag(self):
        reading = m.read_religion(BANGGAI, "Kabupaten Banggai")
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows, {"Islam": 70.84, "Protestantism": 15.61, "Catholicism": 1.63,
                                "Hinduism": 11.08, "Buddhism": 0.83, "Other religion": 0.01})
        self.assertEqual((reading["kind"], reading["year"]), ("bps", 2020))

    def test_a_short_list_gets_a_remainder_and_an_overrun_is_refused(self):
        rows, why, remark = m.religion_shares([("Islam", 97.0), ("Hindu", 2.0)])
        self.assertIsNone(why)
        self.assertEqual(rows[-1], {"group": m.REMAINDER, "pct": 1.0})
        rows, why, remark = m.religion_shares([("Islam", 70.86), ("Kristen", 24.88),
                                       ("Protestan", 24.97), ("Katolik", 0.91), ("Hindu", 5.25)])
        self.assertIsNone(why)
        self.assertIn("add to 102.0%", remark)
        self.assertEqual(rows[0], {"group": "Islam", "pct": 70.86})
        rows, why, remark = m.religion_shares([("Islam", 90.0), ("Hindu", 20.0)])
        self.assertIn("shares add to 110", why)

    def test_uncited_figure_is_not_read(self):
        out, printed = quiet(m.read_religion, UNCITED, "Kabupaten Nowhere")
        self.assertIsNone(out)
        self.assertIn("no citation", printed)
        # A reference by a name the page never defines is no citation.
        garut = UNCITED.replace("[[Hindu]]}}", '[[Hindu]]<ref name="DUKCAPIL"/>}}')
        out, printed = quiet(m.read_religion, garut, "Kabupaten Garut")
        self.assertIsNone(out)
        self.assertIn("['dukcapil'] defined nowhere", printed)
        # A citation with no year in it dates nothing, and is not read.
        undated = UNCITED.replace("[[Hindu]]}}", '[[Hindu]]<ref>{{cite web|url=https://'
                                  'sumsel.bps.go.id/indicator/108/637/1/jumlah-penduduk-'
                                  'menurut-agama.html|title=Jumlah Penduduk Menurut Agama'
                                  '|accessdate=26 Januari 2021}}</ref>}}')
        out, printed = quiet(m.read_religion, undated, "Kabupaten Banyuasin")
        self.assertIsNone(out)
        self.assertIn("no year", printed)

    def test_a_table_whose_rows_miss_its_total_uses_the_rows(self):
        off = SUMUT.replace("12.930.319", "12.900.000")
        (counts, total, _), printed = quiet(m.read_ethnicity, off, "North Sumatra",
                                         "Sumatera Utara")
        self.assertEqual(total, 12_930_319)
        self.assertIn("the rows are the denominator", printed)
        far = SUMUT.replace("12.930.319", "11.000.000")
        with self.assertRaises(SystemExit):
            m.read_ethnicity(far, "North Sumatra", "Sumatera Utara")
        # Riau's case: the printed total is not the census population and
        # the rows are, so the rows stand.
        (counts, total, _), printed = quiet(m.read_ethnicity, far, "North Sumatra",
                                         "Sumatera Utara", 12_982_204)
        self.assertEqual(total, 12_930_319)
        self.assertIn("are the denominator", printed)

    def test_shares_that_do_not_add_up_are_refused(self):
        rows, why, remark = m.religion_shares([("Islam", 80.0), ("Hindu", 5.0)])
        self.assertEqual(rows, [])
        self.assertIn("add to", why)
        rows, why, remark = m.religion_shares([("Islam", 90.0), ("Jedi", 10.0)])
        self.assertIn("Jedi", why)



class InfoboxPopulation(unittest.TestCase):
    """The head count sitting one parameter above the faiths.

    It is read because the regency compositions are percentages and nothing
    else, so a province summed from them needs each regency's population as
    the weight -- and the eleven shapes in Papua and West Papua that Wikidata
    has no population for were exactly what refused those two sums.
    """

    def test_count_year_and_registry_named(self):
        (head, why), printed = quiet(m.read_population, CILACAP, "Kabupaten Cilacap")
        self.assertEqual(head, {"total": 2_037_899, "year": 2024, "kind": "dukcapil"})
        self.assertEqual(why, "")
        fields = m.population_fields(head, "Kabupaten Cilacap")
        self.assertEqual(fields["population"]["value"], 2_037_899)
        self.assertEqual(fields["population"]["year"], 2024)
        self.assertIn("Dukcapil", fields["population"]["source"])
        self.assertIn("identity card", fields["population_note"])
        self.assertEqual(fields["population_source"]["field"], "population")

    def test_year_falls_back_to_the_citation_when_the_infobox_gives_none(self):
        (head, _), printed = quiet(m.read_population, MANADO, "Kota Manado")
        self.assertEqual(head["total"], 459_409)
        self.assertEqual(head["year"], 2023)

    def test_separators_and_the_as_of_date_win_over_the_citation(self):
        (head, _), printed = quiet(m.read_population, PUNCAK_JAYA,
                                   "Kabupaten Puncak Jaya")
        self.assertEqual(head, {"total": 220_393, "year": 2024, "kind": "dukcapil"})

    def test_no_count_and_an_uncited_count_are_both_refused_with_a_reason(self):
        """A refusal has to say which of the two it is.

        Both end with no population on the record, and they are not the same
        fact about the place: one article prints no head count at all, the
        other prints one and cites nothing for it. A bare gap says neither.
        """
        (head, why), printed = quiet(m.read_population, SURABAYA, "Kota Surabaya")
        self.assertIsNone(head)
        self.assertIn("no head count at all", why)
        (head, why), printed = quiet(m.read_population, UNCITED_COUNT,
                                     "Kabupaten Contoh")
        self.assertIsNone(head)
        self.assertIn("cites nothing for it", why)
        self.assertIn("no citation", printed)

    def test_a_joint_hindu_buddhist_bucket_is_one_other_row(self):
        reading, printed = quiet(m.read_religion, PUNCAK_JAYA, "Kabupaten Puncak Jaya")
        self.assertIsNotNone(reading, printed)
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows["Other religion"], 0.01)
        self.assertEqual(rows["Protestantism"], 98.19)
        self.assertNotIn("Hinduism", rows)
        self.assertNotIn("Buddhism", rows)

    def test_a_doubled_percent_sign_is_not_part_of_the_faith(self):
        # "1,93%% [[Kristen]]" left "% Kristen" as the faith's name and
        # refused Bangka Barat and Bangka Tengah outright.
        reading, printed = quiet(m.read_religion, BANGKA_BARAT, "Kabupaten Bangka Barat")
        self.assertIsNotNone(reading, printed)
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows["Islam"], 92.73)
        self.assertEqual(rows["Protestantism"], 1.42)
        self.assertEqual(rows["Confucianism"], 1.70)
        self.assertNotIn("Christianity", rows)
        self.assertAlmostEqual(sum(rows.values()), 100.0, delta=m.RELIGION_TOLERANCE)
        self.assertEqual(reading["kind"], "dukcapil")

    def test_a_third_decimal_place_stays_on_the_number(self):
        # "0,454% [[Buddha]]" was cut at two decimals and the digit left over
        # became the faith, "4% Buddha".
        reading, printed = quiet(m.read_religion, JAKARTA_TIMUR,
                                 "Kota Administrasi Jakarta Timur")
        self.assertIsNotNone(reading, printed)
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows["Buddhism"], 0.45)
        self.assertEqual(rows["Islam"], 88.76)
        self.assertEqual((reading["kind"], reading["year"]), ("jakarta", 2020))

    def test_a_link_abutting_its_neighbour_keeps_the_space(self):
        # "[[Buddhisme|Budha]] dan[[Agama Hindu|Hindu]]" resolved to
        # "Budha danHindu"; it is the joint bucket Puncak Jaya has, spelled
        # the other way, and goes where that one goes.
        reading, printed = quiet(m.read_religion, MINAHASA_TENGGARA,
                                 "Kabupaten Minahasa Tenggara")
        self.assertIsNotNone(reading, printed)
        rows = {r["group"]: r["pct"] for r in reading["rows"]}
        self.assertEqual(rows["Other religion"], 0.01)
        self.assertEqual(rows["Protestantism"], 80.93)
        self.assertNotIn("Hinduism", rows)
        self.assertNotIn("Buddhism", rows)
        self.assertEqual((reading["kind"], reading["year"]), ("census2010", 2010))

    def test_reading_the_faiths_better_does_not_reach_the_citation_rules(self):
        # Garut's figure hangs off <ref name="dukcapil"/> and the page defines
        # no such reference -- the probe printed all five it does define -- so
        # it is still a citation to nothing, and still not read.
        garut = BANGKA_BARAT.replace(DUKCAPIL_DEFINITION, "Teks.\n")
        out, printed = quiet(m.read_religion, garut, "Kabupaten Garut")
        self.assertIsNone(out)
        self.assertIn("['dukcapil'] defined nowhere", printed)



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
        # Notes are short: what the figure is and where from, then caveats,
        # three sentences at most.
        for key in ("ethnicity_note", "religion_note"):
            self.assertLessEqual(len(re.findall(r"\. [A-Z]", sumut[key])) + 1, 3, sumut[key])
        self.assertEqual(sumut["aliases"], ["Sumatera Utara"])
        self.assertEqual({s["field"] for s in sumut["sources"]}, {"ethnicity", "religion"})
        self.assertEqual(by_name["Bali"]["ethnicity"]["status"], "not_available")
        self.assertEqual(by_name["Bangka-Belitung Islands"]["ethnicity"]["status"],
                         "not_available")
        self.assertIn("2022", by_name["Papua"]["religion"].get("note", ""))

        regencies, printed = quiet(m.regency_records, fake_fetch)
        by_regency = {r["name"]: r for r in regencies}
        # One article is stubbed, so one regency is read from an infobox; the
        # rest of what lands is the four portal tables, which cover every unit
        # of their provinces and write only the ones no article answered for.
        cilacap = by_regency["Kabupaten Cilacap"] if "Kabupaten Cilacap" in by_regency \
            else by_regency["Cilacap"]
        self.assertEqual(sum(1 for r in regencies
                             if r.get("religion_year") == 2019), 1)
        bukittinggi = by_regency["Kota Bukittinggi"]
        self.assertEqual(bukittinggi["religion_year"], 2023)
        self.assertEqual(bukittinggi["religion"][0]["group"], "Islam")
        self.assertIn("data.sumbarprov.go.id", bukittinggi["religion_note"])
        # The portal table prints counts, so its own total is a head count
        # for a regency whose article gave none.
        self.assertEqual({s["field"] for s in bukittinggi["sources"]},
                         {"religion", "population"})
        self.assertGreater(bukittinggi["population"]["value"], 0)
        self.assertEqual(bukittinggi["population"]["year"], 2023)
        self.assertIn("summed across the faiths", bukittinggi["population_note"])
        self.assertEqual(by_regency["Kota Samarinda"]["religion_year"], 2023)
        self.assertEqual(by_regency["Lebong"]["religion_year"], 2024)
        self.assertEqual(by_regency["Kota Tangerang Selatan"]["religion_year"], 2021)
        self.assertEqual(cilacap["id"], "IDN-central-java-cilacap")
        self.assertEqual(cilacap["parent"], "IDN-central-java")
        self.assertEqual(cilacap["parent_name"], "Central Java")
        self.assertEqual(cilacap["level"], "admin2")
        self.assertEqual(cilacap["religion_year"], 2019)
        # The weight the roll-up needs, from the same infobox.
        self.assertEqual(cilacap["population"]["value"], 2_037_899)
        self.assertEqual({s["field"] for s in cilacap["sources"]},
                         {"religion", "population"})
        self.assertIn("not read", printed)
        self.assertNotIn("Kabupaten Cilacap", printed)
        # Hutan is named as an uninhabited feature, never as a regency the
        # reader failed on: the two are different facts and the log says which.
        self.assertIn("uninhabited features", printed)
        for line in printed.splitlines():
            if "not read" in line or "does not answer" in line:
                self.assertNotIn("Hutan", line, line)

    def test_hapi_only_ever_fills_and_never_replaces(self):
        """The last-resort head count must not touch a regency that has one.

        HAPI's figures are a 2020 projection under a licence that is not
        open; the article route's are a registry count for 2023 to 2025. A
        rule that let the projection win anywhere would be replacing a better
        figure with a worse one, and would be doing it under a licence the
        project would rather not lean on at all.
        """
        pages = {("Kabupaten Cilacap", "id"): CILACAP}
        regencies, _ = quiet(m.regency_records,
                             lambda title, lang="id": (pages.get((title, lang), ""),
                                                       title))
        by_name = {r["name"]: r for r in regencies}
        cilacap = by_name.get("Kabupaten Cilacap") or by_name["Cilacap"]
        # Cilacap's article carries a cited, dated count, so that is what
        # lands -- not HAPI's, whatever HAPI holds for it.
        self.assertEqual(cilacap["population"]["value"], 2_037_899)
        self.assertEqual(cilacap["population"]["year"], 2024)
        self.assertIn("Dukcapil", cilacap["population"]["source"])
        self.assertNotIn("UNFPA", cilacap["population"]["source"])

    def test_a_hapi_record_carries_its_licence_and_its_vintage(self):
        from scripts.fetch_census import indonesia_hapi as hapi
        row = {"population": "95303", "year": "2020",
               "admin2_name": "Simeulue", "admin2_code": "ID1101",
               "resource_hdx_id": "8f6f09d2-95f7-42dc-b6f1-aead319607f3"}
        fields = m.hapi_fields(row, "Simeulue", "the article prints no head count")
        self.assertEqual(fields["population"]["value"], 95_303)
        self.assertEqual(fields["population"]["year"], 2020)
        self.assertEqual(fields["population_source"]["license"], hapi.LICENCE)
        self.assertIn("humanitarian use only", fields["population_source"]["license"])
        for phrase in ("projection, not a count", "owner's decision",
                       "humanitarian use only", "marks it as not open",
                       "the article prints no head count"):
            self.assertIn(phrase, fields["population_note"], phrase)

    def test_a_lake_says_it_is_a_lake(self):
        """Five shapes at this level are lakes, a forest and two reservoirs.

        Skipped in silence they fell through to the build's generic "nothing
        was read for this unit", which reads as a regency awaiting data. UN
        OCHA's catalogue entry for the matching boundary set names them as
        uninhabited and publishes no row for any of them.
        """
        regencies, _ = quiet(m.regency_records, lambda title, lang="id": ("", title))
        by_name = {r["name"]: r for r in regencies}
        for name in ("Hutan", "Danau", "Waduk Cirata"):
            self.assertIn(name, by_name, sorted(by_name)[:8])
            unit = by_name[name]
            for field in ("religion", "ethnicity", "language", "population"):
                self.assertEqual(unit[field]["status"], "not_collected", field)
                self.assertIn("nobody lives in it", unit[field]["note"])
        self.assertIn("a forest", by_name["Hutan"]["religion"]["note"])
        self.assertIn("reservoir", by_name["Waduk Cirata"]["religion"]["note"])

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
