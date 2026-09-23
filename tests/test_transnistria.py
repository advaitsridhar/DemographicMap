"""Bender and Transnistria: 2015 ethnicity read, religion and mother tongue modelled.

The 2015 rows and the religion cross-table below are the sources' own, as the
runner's probes printed them on 23 September 2026. The mother-tongue table is
cut to a few columns and made to add up, because the probe printed only the
first twenty-two of its thirty.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import transnistria as t  # noqa: E402

# Written the way pop-stat writes its tables: no cell or row is ever closed.
POPSTAT = """<html><body><table>
<tr><td rowspan=3 colspan=2>Район<td>Все<td>Русские<td>Молдаване<td>Украинцы<td>Болгары<td>Гагаузы<td>Белорусы<td>Немцы<td>Приднестровцы<td>Поляки<td>Прочие<td>Не указано<td>Отказались
<tr><td>Total<td>Ruși<td>Moldoveni<td>Ucraineni<td>Bulgari<td>Găgăuzi<td>Belaruși<td>Germani<td>"Transnistrenii"<td>Polonezi<td>Alte<td>Nedeclarată<td>Au refuzat să răspundă
<tr><td>Total<td>Russians<td>Moldovans<td>Ukrainians<td>Bulgarians<td>Gagauzians<td>Belorussians<td>Germans<td>"Transnistrians"<td>Poles<td>Other<td>Undeclared<td>Refused to answer
<tr><td>Приднестровская Молдавская Республика<td>Republica Moldovenească Nistreană<td>475007<td>138072<td>135492<td>108923<td>11210<td>4999<td>2376<td>1276<td>1013<td>1005<td>4209<td>66432<td>1974
<tr><td>Бендерский горсовет<td>mun. Bender<td>91197<td>34644<td>19986<td>12526<td>2663<td>1291<td>530<td>169<td>13<td>113<td>1027<td>18235<td>376
<tr><td>Тираспольский горсовет<td>mun. Tiraspol<td>129367<td>47348<td>17805<td>33561<td>2032<td>2622<td>971<td>398<td>40<td>138<td>1470<td>22982<td>1229
<tr><td>г. Днестровск<td>or. Dnestrovsc<td>9744<td>3642<td>1706<td>2057<td>66<td>56<td>91<td>43<td>-<td>9<td>75<td>1999<td>236
<tr><td>Григориопольский<td>Grigoriopol<td>39795<td>6218<td>23512<td>5658<td>161<td>100<td>89<td>190<td>37<td>12<td>194<td>3624<td>170
<tr><td>Дубоссарский<td>Dubăsari<td>31159<td>6532<td>12607<td>5768<td>95<td>68<td>99<td>32<td>225<td>20<td>270<td>5443<td>695
<tr><td>Каменский<td>Camenca<td>20542<td>1950<td>9130<td>7499<td>40<td>54<td>34<td>10<td>83<td>304<td>69<td>1369<td>166
<tr><td>Рыбницкий<td>Rîbnița<td>69405<td>12231<td>19619<td>26491<td>263<td>146<td>266<td>104<td>170<td>364<td>446<td>9305<td>1197
<tr><td>Слободзейский<td>Slobozia<td>83798<td>25507<td>31127<td>15363<td>5890<td>662<td>296<td>330<td>445<td>45<td>658<td>3475<td>534
</table></body></html>"""

N = None
RELIGION = [
    (N, "5.35 Populația după etnie și afilierea religioasă la recensământul din 2024"),
    (N,) * 16 + ("persoane",),
    (N, "Etnia declarată", "Total", "Religia declarată", N, N, N, N, N, N, N, N, N, N, N, N, N,
     "Nu au declarat religia"),
    (N, N, N, "Ortodoxă", "Baptistă", "Martorii lui Iehova", "Penticostală", "Adventistă",
     "Creștină după Evanghelie", "Staroveri (Ortodoxă de rit vechi)", "Islam",
     "Romano-catolică", "Altă religie", "Liber cugetători", "Agnostic", "Ateu", "Fără religie", N),
    (N, "A", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
    (N, "Total", 2409207, 2271105, 26226, 16505, 12606, 6982, 6364, 4053, 3138, 2586, 4720,
     440, 2117, 14211, 20051, 18103),
    (N, "Moldovean", 1848670, 1762990, 17663, 13445, 9322, 4627, 4061, 466, 747, 773, 1868,
     259, 1064, 7311, 12619, 11455),
    (N, "Român", 193197, 183009, 1967, 794, 589, 510, 451, 7, 75, 197, 304, 78, 452, 1840,
     1540, 1384),
    (N, "Ucrainean", 123586, 110310, 3276, 1009, 1469, 821, 737, 159, 93, 433, 294, 31, 186,
     1486, 1793, 1489),
    (N, "Rus", 81630, 69304, 716, 562, 325, 158, 280, 3389, 97, 194, 255, 33, 243, 2466,
     2316, 1292),
    (N, "Găgăuz", 97205, 92120, 1752, 208, 451, 719, 409, 7, 62, 4, 80, 8, 26, 205, 452, 702),
    (N, "Bulgar", 38236, 36299, 523, 150, 77, 65, 188, 5, 13, 14, 50, 4, 28, 251, 386, 183),
    (N, "Evreu", 1640, 87, 9, 6, 5, 9, 6, "-", 1, 1, 947, 10, 29, 210, 227, 93),
    (N, "German / Neamț", 763, 528, 15, 19, 8, 14, 19, 1, 3, 40, 9, "-", 6, 41, 33, 27),
    (N, "Polonez", 1184, 603, 18, 6, 6, "-", 4, "-", 1, 452, 5, 2, 2, 28, 33, 24),
    (N, "Belorus", 2143, 1885, 11, 18, 9, 7, 7, 2, 2, 31, 12, "-", 6, 59, 54, 40),
    (N, "Alte etnii", 3671, 1388, 69, 16, 36, 10, 54, 1, 631, 235, 767, 4, 32, 82, 162, 184),
    (N, "Nu au declarat", 3448, 1935, 48, 24, 20, 12, 37, 13, 8, 15, 19, 8, 28, 106, 221, 954),
    (N, "în % față de total"),
    (N, "Total", 100, 94.27),
]

# Synthetic: the probe's language columns, cut to seven, with the rest of
# each row put in the last one so every row adds up to its total.
def lang_row(name, moldovan, romanian, ukrainian, russian, yiddish):
    rest = 100 - (moldovan + romanian + ukrainian + russian + yiddish)
    return (N, name, 100, moldovan + romanian, moldovan, romanian, ukrainian, russian,
            yiddish, rest)


LANGUAGE = [
    (N, "Etnia declarată", "Total", "Limba maternă declarată", N, N, N, N, N, N),
    (N, N, N, "Moldovenească sau română (total)", N, N, "Ucraineană", "Rusă", "Idiș",
     "Tătară"),
    (N, N, N, "Total", "Moldovenească", "Română"),
    (N, "A", 1, 2, 3, 4, 5, 6, 7, 8),
    lang_row("Moldovean", 60, 30, 1, 9, 0),
    lang_row("Român", 3, 96, 0, 1, 0),
    lang_row("Ucrainean", 4, 2, 50, 44, 0),
    lang_row("Rus", 2, 1, 1, 96, 0),
    lang_row("Găgăuz", 1, 1, 0, 10, 0),
    lang_row("Bulgar", 4, 2, 0, 21, 0),
    lang_row("German / Neamț", 8, 6, 1, 68, 0),
    lang_row("Polonez", 5, 3, 8, 75, 0),
    lang_row("Belorus", 3, 1, 1, 79, 0),
    lang_row("Evreu", 4, 4, 2, 82, 8),
    (N, "în % față de total"),
]


class TheTwentyFifteenTable(unittest.TestCase):
    def setUp(self):
        self.rows = t.ethnic_2015(POPSTAT)

    def test_rows_are_read_though_no_cell_is_ever_closed(self):
        self.assertEqual(self.rows[t.BENDER]["Russian"], 34644)
        self.assertEqual(sum(self.rows[t.BENDER].values()), 91197)

    def test_refused_is_inside_undeclared_and_not_counted_twice(self):
        self.assertEqual(self.rows[t.BENDER]["Not declared"], 18235)
        self.assertNotIn("Refused", self.rows[t.BENDER])

    def test_the_left_bank_and_bender_make_the_republic(self):
        left = sum(sum(self.rows[n].values()) for n in t.LEFT_BANK)
        self.assertEqual(left, 475007 - 91197)

    def test_a_row_that_does_not_add_up_stops_the_run(self):
        with self.assertRaises(SystemExit):
            t.ethnic_2015(POPSTAT.replace("<td>91197<td>34644", "<td>91197<td>34645"))


class TheCrossTables(unittest.TestCase):
    def test_religion_by_ethnicity(self):
        table = t.by_ethnicity("religion", RELIGION)
        self.assertEqual(table["rus"]["Old Believer"], 3389)
        self.assertEqual(table["rus"]["Orthodox"], 69304)
        self.assertEqual(table["polonez"]["Catholic"], 452)
        self.assertNotIn("in fata de total", table)

    def test_the_subtotal_is_not_a_language(self):
        table = t.by_ethnicity("language", LANGUAGE)
        self.assertEqual(table["moldovean"]["Moldovan"], 60)
        self.assertNotIn("Total", table["moldovean"])
        # A language the model does not name is one bar.
        self.assertEqual(table["evreu"]["Other"], 8)

    def test_the_pool_leaves_out_romanians_and_the_undeclared(self):
        pooled = t.rates(t.by_ethnicity("religion", RELIGION))["Other"]
        # Evreu and Alte etnii only: 1,640 + 3,671 people.
        self.assertAlmostEqual(pooled["Orthodox"], (87 + 1388) / (1640 + 3671))


class TheModel(unittest.TestCase):
    def setUp(self):
        self.rate = {"religion": t.rates(t.by_ethnicity("religion", RELIGION)),
                     "language": t.rates(t.by_ethnicity("language", LANGUAGE))}
        self.ethnic = t.ethnic_2015(POPSTAT)

    def test_bender_religion(self):
        rows = t.modelled("religion", self.ethnic[t.BENDER], self.rate["religion"])
        shares = {r["group"]: r["pct"] for r in rows}
        self.assertAlmostEqual(sum(shares.values()), 100, delta=0.3)
        # Bender's declared mix is 47% Russian, and Russians are the least
        # Orthodox of the three large groups (84.9%).
        self.assertTrue(85 < shares["Orthodox"] < 92, shares["Orthodox"])
        self.assertIn("Old Believer", shares)

    def test_moldovan_and_romanian_are_one_bar(self):
        rows = t.modelled("language", self.ethnic[t.BENDER], self.rate["language"])
        groups = {r["group"] for r in rows}
        self.assertIn("Moldovan or Romanian", groups)
        self.assertFalse({"Moldovan", "Romanian"} & groups)

    def test_the_undeclared_are_given_the_declared_mix(self):
        # Doubling the undeclared changes nothing.
        more = dict(self.ethnic[t.BENDER], **{"Not declared": 36470})
        self.assertEqual(t.modelled("religion", more, self.rate["religion"]),
                         t.modelled("religion", self.ethnic[t.BENDER], self.rate["religion"]))

    def test_records(self):
        drawn = {level: {"bender": "B", "transnistria": "T"} for level in ("admin1", "admin2")}
        got = {(r["name"], r["level"]): r for r in t.records(self.ethnic, self.rate, drawn)}
        self.assertEqual(len(got), 4)
        bender, pmr = got[("Bender", "admin1")], got[("Transnistria", "admin1")]
        # Bender's is a reading, dated; Transnistria's a sum over a slightly
        # larger area, marked as derived.
        self.assertIsInstance(bender["ethnicity"], list)
        self.assertEqual(bender["ethnicity_year"], 2015)
        self.assertEqual(pmr["ethnicity"]["status"], "derived")
        self.assertIn("Căușeni", pmr["ethnicity"]["note"])
        for r in (bender, pmr):
            self.assertEqual(r["religion"]["status"], "modelled")
            self.assertEqual(r["language"]["status"], "modelled")
            self.assertIn("understates Russian", r["language"]["note"])
            self.assertEqual(r["match_by"], "shape_id")
        self.assertEqual(got[("Transnistria", "admin2")]["shape_id"], "T")


if __name__ == "__main__":
    unittest.main()
