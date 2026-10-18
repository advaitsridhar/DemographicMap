"""Sierra Leone's 2021 mid-term census, put together on the 2015 census's
districts from citypopulation.de's table of the 2017 districts and chiefdoms.

The figures are the table's own (runner log of October 2026), for the units
the 2017 changes touched; the other ten districts are left out by patching the
national totals down to what the units here make."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import sierra_leone_mtphc as m  # noqa: E402

KARENE = [("Buya", None, 13174, 14378), ("Dibia", 15077, 15519, 24059),
          ("Gbanti", None, 16639, 19789), ("Libeisaygahun/Gbombahun", None, 11770, 13510),
          ("Mafonda Makerembay", None, 4429, 6560), ("Romende", None, 21107, 27860),
          ("Safroko", None, 10980, 9158), ("Sanda Loko", 27667, 45075, 24862),
          ("Sanda Magbolontor", 15088, 23731, 27862), ("Sanda Tendaran", 18840, 26228, 29782),
          ("Sella Limba", 52579, 58401, 58066), ("Tambakha Simibungie", None, 14030, 9805),
          ("Tambakha Yobangie", None, 24463, 24622)]


def row(name, status, *values):
    cells = "".join(f"<td>{'...' if v is None else f'{v:,}'}</td>" for v in values)
    return f"<tr><td><a href='x'><span>{name}</span></a></td><td>{status}</td>{cells}<td>→</td></tr>"


def page(country):
    rows = [row("Bombali", "District", 270923, 422960, 387236),
            row("Makeni", "City", 82840, 125970, 85116),
            row("Mara", "Chiefdom", None, 17451, 11795),
            row("Rest of Bombali", "Chiefdom", None, 279539, 290325),
            row("Karene", "District", 210884, 285546, 290313),
            *[row(n, "Chiefdom", *v) for n, *v in KARENE],
            row("Port Loko", "District", 388236, 530865, 528038),
            row("Port Loko", "City", None, 530865, 528038),
            row("Tonkolili", "District", 339290, 513984, 557257),
            row("Tonkolili", "Chiefdom", None, 513984, 557257),
            row("Sierra Leone", "Republic", *country)]
    return "<table>" + "".join(rows) + "</table>"


SPEC = {k: m.FROM_2017[k] for k in ("Bombali", "Port Loko", "Tonkolili")}
COUNTS_2015 = {"Bombali": 606_544, "Port Loko": 615_376, "Tonkolili": 531_435}


class MidTermTest(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(m, "FROM_2017", SPEC),
                   mock.patch.object(m, "NATIONAL_2015", sum(COUNTS_2015.values())),
                   mock.patch.object(m, "NATIONAL_2021", 562_437 + 631_355 + 569_052)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.units = m.table(page((None, m.NATIONAL_2015, m.NATIONAL_2021)))

    def test_the_2015_districts_put_together(self):
        m.check(self.units, COUNTS_2015)
        self.assertEqual(m.compose(self.units, SPEC["Bombali"], 2), 562_437)
        self.assertEqual(m.compose(self.units, SPEC["Port Loko"], 2), 631_355)
        self.assertEqual(m.compose(self.units, SPEC["Tonkolili"], 2), 569_052)

    def test_a_move_the_2015_count_does_not_bear_out_stops_the_run(self):
        wrong = dict(SPEC, Bombali=dict(SPEC["Bombali"], minus=[]))
        with mock.patch.object(m, "FROM_2017", wrong), self.assertRaises(SystemExit):
            m.check(self.units, COUNTS_2015)

    def test_notes(self):
        self.assertIn("Koinadugu and Falaba districts added together",
                      m.note("Koinadugu", m.FROM_2017.get("Koinadugu")
                             or {"districts": ["Koinadugu", "Falaba"]}))
        bombali = m.note("Bombali", SPEC["Bombali"])
        self.assertIn("eight chiefdoms of Karene District", bombali)
        self.assertIn("609,174", bombali)
        self.assertTrue(m.note("Kailahun", {"districts": ["Kailahun"]})
                        .startswith("The 2021 Mid-Term Population and Housing Census's count "
                                    "for Kailahun District. The mid-term census's results were "
                                    "disputed"))


if __name__ == "__main__":
    unittest.main()
