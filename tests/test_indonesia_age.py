"""Indonesia: population, median age and sex ratio from the 2020 census Long Form.

No network: the Age-Sex sheet is built here in the Bureau's two-row-header layout.
"""

import unittest
import unittest.mock

from scripts.fetch_census import indonesia_age as a

BANDS = [(lo, lo + 4) for lo in range(0, 75, 5)] + [(75, None)]


def col(sex, lo, hi):
    return f"{sex}{lo:02d}{hi:02d}" if hi is not None else f"{sex}{lo:02d}PL"


def sheet(rows, break_band=None):
    """rows: (level, adm1, adm2, men per band, women per band)."""
    names = (["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL", "NSO_CODE", "NSO_NAME",
              "BTOTL", "MTOTL", "FTOTL"]
             + [col(s, lo, hi) for s in "BMF" for lo, hi in BANDS])
    out = [names, ["alias"] * len(names)]
    for level, adm1, adm2, m, f in rows:
        n = len(BANDS)
        both = [m + f] * n
        if break_band is not None and adm2 == break_band:
            both[0] += 1
        out.append([adm2 or adm1 or "INDONESIA", adm1, adm2, level, "", adm2,
                    n * (m + f), n * m, n * f] + both + [m] * n + [f] * n)
    return out


JAK = "Jakarta Special Capital Region"
OTHERS = [p for p in a.indonesia.PROVINCES if p not in (JAK, "Bengkulu", "North Sumatra")]


def rows(seribu=True, extra=0):
    out = [(2, "JAKARTA", "KOTA ADMINISTRASI JAKARTA UTARA", 10, 10),
           (2, "BENGKULU", "KABUPATEN MUKO MUKO", 5, 4),
           (2, "BENGKULU", "KOTA BENGKULU", 6, 6),
           (2, "SUMATERA UTARA", "KABUPATEN TOBA", 3, 3)]
    if seribu:
        out.append((2, "JAKARTA", "KABUPATEN ADMINISTRASI KEPULAUAN SERIBU", 1, 1))
    jak = 10 + (1 if seribu else 0)
    out += [(1, "JAKARTA", "", jak, jak), (1, "BENGKULU", "", 11 + extra, 10),
            (1, "SUMATERA UTARA", "", 3, 3)]
    # Every other province: one regency of one man and one woman per band.
    for p in OTHERS:
        out += [(2, p.upper(), f"KABUPATEN {p.upper()} ONE", 1, 1), (1, p.upper(), "", 1, 1)]
    men = jak + 11 + extra + 3 + len(OTHERS)
    women = jak + 10 + 3 + len(OTHERS)
    return out + [(0, "", "", men, women)]


ADMIN1 = [{"id": e, "name": e} for e in a.indonesia.PROVINCES]
ADMIN2 = ([{"id": "J", "name": "Kota Jakarta Utara", "parent": JAK},
           {"id": "M", "name": "Mukomuko", "parent": "Bengkulu"},
           {"id": "K", "name": "Kota Bengkulu", "parent": "Bengkulu"},
           {"id": "T", "name": "Toba Samosir", "parent": "North Sumatra"},
           {"id": "L", "name": "Danau Toba", "parent": "North Sumatra"}]
          + [{"id": f"X{i}", "name": f"{p} One", "parent": p} for i, p in enumerate(OTHERS)])


class BuildTest(unittest.TestCase):
    def build(self, rs, admin2=ADMIN2, break_band=None):
        parsed = a.read_rows(sheet(rs, break_band))
        national = sum(sum(r["groups"]["B"].values()) for r in parsed if r["level"] == 0)
        with unittest.mock.patch.object(a, "NATIONAL", national):
            return {r["shape_id"]: r for r in a.build(parsed, ADMIN1, admin2)}

    def test_regencies_and_provinces(self):
        recs = self.build(rows())
        self.assertTrue({"J", "M", "K", "T", JAK, "Bengkulu"} <= set(recs))
        self.assertNotIn("L", recs)                                  # the lake
        self.assertEqual(recs["M"]["sex_ratio"]["value"], 125.0)
        # 16 equal groups to an open 75+: the middle person ends the 35-39 group.
        self.assertEqual(recs["K"]["median_age"]["value"], 40.0)
        self.assertEqual(recs["M"]["population"]["value"], 16 * 9)
        self.assertIsInstance(recs["M"]["population"]["value"], int)
        self.assertEqual(recs["M"]["median_age"]["year"], 2022)
        self.assertEqual(recs["Bengkulu"]["sex_ratio"]["value"], 110.0)
        # Jakarta is its own row: the Thousand Islands are in it, undrawn.
        self.assertEqual(recs[JAK]["population"]["value"], 16 * 22)
        self.assertIn("Kepulauan Seribu", recs[JAK]["median_age_note"])
        # A renamed regency binds the polygon of its earlier name.
        self.assertEqual(recs["T"]["name"], "Toba Samosir")

    def test_a_province_its_regencies_do_not_make_refuses(self):
        with self.assertRaises(SystemExit):
            self.build(rows(extra=1))

    def test_a_polygon_with_no_row_refuses(self):
        admin2 = ADMIN2 + [{"id": "B", "name": "Lebong", "parent": "Bengkulu"}]
        with self.assertRaises(SystemExit):
            self.build(rows(), admin2)

    def test_men_and_women_must_make_both(self):
        with self.assertRaises(SystemExit):
            self.build(rows(), break_band="KOTA BENGKULU")

    def test_a_blank_row_must_be_water(self):
        lake = sheet(rows())
        blank = ["DANAU TOBA", "SUMATERA UTARA", "DANAU TOBA", 2, "", "DANAU TOBA"] + [None] * (
            len(lake[0]) - 6)
        parsed = a.read_rows(lake[:2] + [blank] + lake[2:])
        national = sum(sum(r["groups"]["B"].values()) for r in parsed if r["level"] == 0)
        with unittest.mock.patch.object(a, "NATIONAL", national):
            recs = a.build(parsed, ADMIN1, ADMIN2)
        self.assertNotIn("L", {r["shape_id"] for r in recs})
        town = ["KOTA NOWHERE", "SUMATERA UTARA", "KOTA NOWHERE", 2, "", ""] + [None] * (
            len(lake[0]) - 6)
        parsed = a.read_rows(lake[:2] + [town] + lake[2:])
        with unittest.mock.patch.object(a, "NATIONAL", national):
            with self.assertRaises(SystemExit):
                a.build(parsed, ADMIN1, ADMIN2)

    def test_names(self):
        self.assertEqual(a.key("KABUPATEN SIMEULUE"), "simeulue")
        self.assertEqual(a.key("KOTA ADMINISTRASI JAKARTA BARAT"), "kotajakartabarat")
        self.assertEqual(a.key("KOTA SAWAHLUNTO"), "kotasawahlunto")
        self.assertEqual(a.key("KABUPATEN ADMINISTRASI KEPULAUAN SERIBU"), "kepulauanseribu")


if __name__ == "__main__":
    unittest.main()
