"""The Dutch gemeenten's religion: CBS's 2010-2015 table carried to the gemeenten of 2022.

The descriptions below are CBS's own text from StatLine 70739ned, as the
probe (scripts/fetch_census/netherlands_probe.py) printed it; the table rows
copy the layout of the two workbooks (2010-2015 by the gemeenten of 2016, and
2010-2014 by those of 2014) as the probes dumped them. No network.
"""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import netherlands_religion_gemeente as m  # noqa: E402

LITTENSERADIEL = (
    "Opgeheven per 01-01-2018, overgegaan naar: - Leeuwarden (GM0080), ... 4330 hectare met 1416 "
    "woningen en 3394 inwoners - Súdwest-Fryslân (GM1900), ... 6738 hectare met 2325 woningen en "
    "5411 inwoners - Waadhoeke (GM1949), ... 1999 hectare met 806 woningen en 1878 inwoners "
    "Naamswijziging per 26-01-1985, oude naam: Littenseradeel (GM0103) Begindatum 26-01-1985")
KRIMPENERWAARD = (
    "Ontstaan per 01-01-2015, ontvangen van: - Bergambacht (GM0491) ... 3510 hectare met 4231 "
    "woningen en 10186 inwoners - Nederlek (GM0643) ... 2777 hectare met 6388 woningen en 14143 "
    "inwoners - Ouderkerk (GM0644) ... 2707 hectare met 3343 woningen en 8241 inwoners - "
    "Schoonhoven (GM0608) ... 628 hectare met 5302 woningen en 11898 inwoners - Vlist (GM0623) ... "
    "5373 hectare met 4001 woningen en 9740 inwoners Begindatum 01-01-2015")
MAASDONK = (
    "Opgeheven per 01-01-2015, overgegaan naar: - 's-Hertogenbosch (GM0796), ... 2619 hectare met "
    "2818 woningen en 6719 inwoners - Oss (GM0828), ... 1106 hectare met 1845 woningen en 4629 "
    "inwoners Grenswijziging per 01-01-2000, ontvangen van: - Oss (GM0828), ... 20 hectare met 0 "
    "woningen en 0 inwoners")
LEERDAM = (
    "Opgeheven per 01-01-2019, overgegaan naar: - Vijfheerenlanden (GM1961), ... 3376 hectare met "
    "8988 woningen en 21248 inwoners Provinciale wijziging per 01-01-2019: - overgegaan van "
    "provincie Zuid-Holland naar provincie Utrecht Wijziging per 01-01-1986, ontvangen van: - "
    "Heukelum (GM0533), ... 15 hectare met 1 woning en 1 inwoner - Kedichem (GM0538), ... 867 "
    "hectare met 466 woningen en 1084 inwoners Begindatum voor 1830")
FRIESE_MEREN = (
    "Naamswijziging per 01-07-2015, nieuwe naam: De Fryske Marren (GM1940) Ontstaan per "
    "01-01-2014, ontvangen van: - Boarnsterhim (GM0055), ... 531 hectare met 277 woningen en 783 "
    "inwoners - Lemsterland (GM0082), ... 7577 hectare met 6146 woningen en 13524 inwoners "
    "Begindatum 01-01-2014")
BINNENMAAS = (
    "Gemeentelijke herindeling per 01-01-2007, ontvangen van: - Binnenmaas (GM0585), ... 5026 "
    "hectare 8104 woningen en 19614 inwoners - 's-Gravendeel (GM0517), ... 1885 hectare 3709 "
    "woningen en 9035 inwoners")


class CBSsRecordOfChanges(unittest.TestCase):

    def test_a_divided_gemeente_names_each_successor_and_its_people(self):
        events = m.parse_events(LITTENSERADIEL)
        self.assertEqual([(e.kind, e.date, e.direction) for e in events],
                         [("Opgeheven", "20180101", "out"),
                          ("Naamswijziging", "19850126", "renamed_from")])
        self.assertEqual(events[0].entries, [("Leeuwarden", "GM0080", 3394),
                                             ("Súdwest-Fryslân", "GM1900", 5411),
                                             ("Waadhoeke", "GM1949", 1878)])

    def test_entries_without_the_comma_before_the_dots_still_read(self):
        (event,) = m.parse_events(KRIMPENERWAARD)
        self.assertEqual(event.direction, "in")
        self.assertEqual([(c, p) for _, c, p in event.entries],
                         [("GM0491", 10186), ("GM0643", 14143), ("GM0644", 8241),
                          ("GM0608", 11898), ("GM0623", 9740)])

    def test_a_name_with_an_apostrophe_and_a_later_event(self):
        events = m.parse_events(MAASDONK)
        self.assertEqual(events[0].entries[0], ("'s-Hertogenbosch", "GM0796", 6719))
        self.assertEqual((events[1].kind, events[1].direction, events[1].entries),
                         ("Grenswijziging", "in", [("Oss", "GM0828", 0)]))

    def test_a_province_change_takes_nothing_from_the_events_around_it(self):
        events = m.parse_events(LEERDAM)
        self.assertEqual([e.kind for e in events],
                         ["Opgeheven", "Provinciale wijziging", "Wijziging"])
        self.assertEqual(events[0].entries, [("Vijfheerenlanden", "GM1961", 21248)])
        self.assertEqual(events[1].entries, [])
        self.assertEqual(events[2].entries, [("Heukelum", "GM0533", 1), ("Kedichem", "GM0538", 1084)])

    def test_a_change_of_name_points_to_the_new_code(self):
        events = m.parse_events(FRIESE_MEREN)
        self.assertEqual((events[0].direction, events[0].entries),
                         ("renamed_to", [("De Fryske Marren", "GM1940", None)]))

    def test_an_entry_missing_its_met_still_counts_its_people(self):
        (event,) = m.parse_events(BINNENMAAS)
        self.assertEqual([p for *_, p in event.entries], [19614, 9035])

    def test_a_kind_not_listed_does_not_run_into_the_event_before(self):
        events = m.parse_events(
            "Opgeheven per 01-01-2019, overgegaan naar: - A (GM0001), ... 10 inwoners "
            "Splitsing per 01-01-2010, overgegaan naar: - B (GM0002), ... 5 inwoners")
        self.assertEqual(events[0].entries, [("A", "GM0001", 10)])
        self.assertEqual(events[1].kind, "Splitsing")


def gemeente(title: str, begin: str, end: str, description: str) -> dict:
    return {"title": title, "begin": begin, "end": end, "events": m.parse_events(description)}


def mini_history(e_records: int = 40) -> dict:
    """A, B merge into N (2015); C is shared out between D and E (2018); N gives
    E 40 people (2019); E is renamed F (2020)."""
    return {
        "GM0001": gemeente("A", "18300101", "20150101",
                           "Opgeheven per 01-01-2015, overgegaan naar: - N (GM0100), ... 1000 inwoners"),
        "GM0002": gemeente("B", "18300101", "20150101",
                           "Opgeheven per 01-01-2015, overgegaan naar: - N (GM0100), ... 3000 inwoners"),
        "GM0100": gemeente("N", "20150101", "",
                           "Grenswijziging per 01-01-2019, overgegaan naar: - E (GM0005), ... 4 hectare "
                           "met 10 woningen en 40 inwoners Ontstaan per 01-01-2015, ontvangen van: - "
                           "A (GM0001), ... 1000 inwoners - B (GM0002), ... 3000 inwoners"),
        "GM0003": gemeente("C", "18300101", "20180101",
                           "Opgeheven per 01-01-2018, overgegaan naar: - D (GM0004), ... 600 inwoners "
                           "- E (GM0005), ... 400 inwoners"),
        "GM0004": gemeente("D", "18300101", "",
                           "Gemeentelijke herindeling per 01-01-2018, ontvangen van: - D (GM0004), ... "
                           "9000 inwoners - C (GM0003), ... 600 inwoners"),
        "GM0005": gemeente("E", "18300101", "20200101",
                           "Naamswijziging per 01-01-2020, nieuwe naam: F (GM0200) Grenswijziging per "
                           f"01-01-2019, ontvangen van: - N (GM0100), ... {e_records} inwoners "
                           "Gemeentelijke herindeling per 01-01-2018, ontvangen van: - C (GM0003), ... "
                           "400 inwoners"),
        "GM0200": gemeente("F", "20200101", "",
                           "Naamswijziging per 01-01-2020, oude naam: E (GM0005) Begindatum 01-01-2020"),
        "GM0998": gemeente("Buitenland", "18300101", "", ""),
    }


POPULATION = {"GM0001": 1000.0, "GM0002": 3000.0, "GM0003": 1000.0, "GM0004": 10000.0,
              "GM0005": 2000.0}


class FollowingTheChanges(unittest.TestCase):

    def setUp(self):
        self.walk = m.follow(mini_history(), POPULATION, "20140101", "20221231")

    def test_the_gemeenten_on_the_last_day(self):
        self.assertEqual(set(self.walk.content), {"GM0100", "GM0004", "GM0200"})

    def test_a_merger_holds_its_parts_less_what_it_gave_away(self):
        self.assertAlmostEqual(self.walk.content["GM0100"]["GM0001"], 0.99)
        self.assertAlmostEqual(self.walk.content["GM0100"]["GM0002"], 0.99)

    def test_a_divided_gemeente_is_shared_by_its_people(self):
        self.assertAlmostEqual(self.walk.content["GM0004"]["GM0003"], 0.6)
        self.assertAlmostEqual(self.walk.content["GM0200"]["GM0003"], 0.4)

    def test_a_new_name_carries_everything(self):
        self.assertAlmostEqual(self.walk.content["GM0200"]["GM0005"], 1.0)
        self.assertAlmostEqual(self.walk.identity["GM0200"]["GM0005"], 1.0)

    def test_every_start_gemeente_is_placed_once(self):
        for code in POPULATION:
            self.assertAlmostEqual(sum(c.get(code, 0) for c in self.walk.content.values()), 1.0)

    def test_a_recipient_that_disagrees_with_its_donor_stops_the_run(self):
        with self.assertRaises(SystemExit):
            m.follow(mini_history(e_records=41), POPULATION, "20140101", "20221231")

    def test_a_transfer_the_recipient_does_not_record_stops_the_run(self):
        history = mini_history()
        history["GM0004"]["events"] = []
        with self.assertRaises(SystemExit):
            m.follow(history, POPULATION, "20140101", "20221231")


def parts(shares: dict | None = None) -> dict:
    """Every label at 0 but those given."""
    return {k: (shares or {}).get(k, 0.0) for k in m.LABELS}


def table(**suppressed) -> dict:
    rows = {}
    for code, name in (("GM0001", "A"), ("GM0002", "B"), ("GM0003", "C"), ("GM0004", "D"),
                       ("GM0005", "E")):
        shares = parts({"Roman Catholic": 20.0, "Protestant Church in the Netherlands": 10.0,
                        "Islam": 5.0, m.OTHER: 5.0})
        rows[code] = {"name": name, "province": "P", "total": 40.0, "parts": shares}
    for code in suppressed:
        rows[code] = {**rows[code], "total": None, "parts": {}}
    return rows


TITLES = {"GM0001": "A", "GM0002": "B", "GM0003": "C", "GM0004": "D", "GM0005": "E",
          "GM0100": "N", "GM0200": "F"}


class WhichGemeentenTakeAFigure(unittest.TestCase):

    def setUp(self):
        self.walk = m.follow(mini_history(), POPULATION, "20140101", "20221231")

    def test_a_union_that_gave_away_one_percent_is_still_its_parts(self):
        unit = m.classify("GM0100", self.walk, POPULATION, table(), TITLES)
        self.assertIsNone(unit.reason)
        self.assertEqual(set(unit.whole), {"GM0001", "GM0002"})
        self.assertAlmostEqual(unit.moved, 0.01)
        self.assertEqual(unit.events, ["it gave 40 inhabitants to E on 1 January 2019"])

    def test_part_of_a_divided_gemeente_takes_nothing(self):
        unit = m.classify("GM0004", self.walk, POPULATION, table(), TITLES)
        self.assertEqual(unit.kind, "changed")
        self.assertIn("it received 600 of the inhabitants of C when C was dissolved on 1 January "
                      "2018", unit.reason)
        self.assertIn("C gave 400 inhabitants to E on 1 January 2018", unit.reason)
        self.assertIn("never split", unit.reason)

    def test_a_suppressed_part_leaves_the_union_without_a_figure(self):
        unit = m.classify("GM0100", self.walk, POPULATION, table(GM0002=True), TITLES)
        self.assertEqual(unit.kind, "suppressed")
        self.assertIn("CBS printed no figure for B", unit.reason)

    def test_a_wider_tolerance_is_a_choice_the_caller_makes(self):
        # E took 400 of C and 40 of N on top of its own 2,000: 18% of its people.
        strict = m.classify("GM0200", self.walk, POPULATION, table(), TITLES)
        loose = m.classify("GM0200", self.walk, POPULATION, table(), TITLES, tolerance=0.2)
        self.assertIsNotNone(strict.reason)
        self.assertIsNone(loose.reason)

    def test_without_unions_a_union_takes_a_gap_that_names_its_parts(self):
        unit = m.classify("GM0100", self.walk, POPULATION, table(), TITLES, unions=False)
        self.assertEqual(unit.kind, "union")
        self.assertIn(f"covers what in {m.VINTAGE} were the gemeenten A and B", unit.reason)
        self.assertIn("none for their union", unit.reason)

    def test_without_unions_one_gemeente_renamed_still_takes_its_figure(self):
        unit = m.classify("GM0200", self.walk, POPULATION, table(), TITLES, tolerance=0.2,
                          unions=False)
        self.assertIsNone(unit.reason)
        self.assertEqual(set(unit.whole), {"GM0005"})

    def test_a_suppressed_part_is_said_before_the_union_is(self):
        unit = m.classify("GM0100", self.walk, POPULATION, table(GM0001=True), TITLES, unions=False)
        self.assertEqual(unit.kind, "suppressed")


def slochteren_history() -> dict:
    """S gives G 100 people (2017) and then goes wholly into M with H (2018), as
    Slochteren gave Groningen 1,033 before it went into Midden-Groningen; G
    also gives K 3 people (2016), as Leeuwarden gave Heerenveen 2."""
    return {
        "GM0040": gemeente("S", "18300101", "20180101",
                           "Opgeheven per 01-01-2018, overgegaan naar: - M (GM1952), ... 900 inwoners "
                           "Grenswijziging per 01-01-2017, overgegaan naar: - G (GM0014), ... 100 inwoners"),
        "GM0018": gemeente("H", "18300101", "20180101",
                           "Opgeheven per 01-01-2018, overgegaan naar: - M (GM1952), ... 3000 inwoners"),
        "GM1952": gemeente("M", "20180101", "",
                           "Ontstaan per 01-01-2018, ontvangen van: - H (GM0018), ... 3000 inwoners - "
                           "S (GM0040), ... 900 inwoners"),
        "GM0014": gemeente("G", "18300101", "",
                           "Grenswijziging per 01-01-2017, ontvangen van: - S (GM0040), ... 100 inwoners "
                           "Grenswijziging per 01-01-2016, overgegaan naar: - K (GM0074), ... 3 inwoners"),
        "GM0074": gemeente("K", "18300101", "",
                           "Grenswijziging per 01-01-2016, ontvangen van: - G (GM0014), ... 3 inwoners"),
    }


class WhatTheNotesName(unittest.TestCase):

    POP = {"GM0040": 1000.0, "GM0018": 3000.0, "GM0014": 20000.0, "GM0074": 50000.0}
    TITLES = {"GM0040": "S", "GM0018": "H", "GM1952": "M", "GM0014": "G", "GM0074": "K"}

    def setUp(self):
        self.walk = m.follow(slochteren_history(), self.POP, "20140101", "20221231")
        self.rows = {c: {"name": t, "total": 40.0, "parts": parts()} for c, t in self.TITLES.items()}

    def test_a_dissolved_gemeente_that_had_already_given_part_away_is_named_so(self):
        unit = m.classify("GM1952", self.walk, self.POP, self.rows, self.TITLES)
        self.assertEqual(unit.kind, "changed")
        self.assertIn("it received 900 of the inhabitants of S when S was dissolved", unit.reason)
        self.assertIn("S gave 100 inhabitants to G on 1 January 2017", unit.reason)

    def test_a_small_part_received_is_a_correction_and_nothing_more_is_said(self):
        unit = m.classify("GM0014", self.walk, self.POP, self.rows, self.TITLES)
        self.assertIsNone(unit.reason)
        self.assertEqual(unit.events, ["it gave 3 inhabitants to K on 1 January 2016",
                                       "it received 100 inhabitants from S on 1 January 2017"])

    def test_a_boundary_donor_s_other_transfers_are_not_listed(self):
        unit = m.classify("GM0074", self.walk, self.POP, self.rows, self.TITLES)
        self.assertEqual(unit.events, ["it received 3 inhabitants from G on 1 January 2016"])
        self.assertIn("less than 0.1%", m.unit_note(unit, "K", self.rows, 1000.0))


def sheet(*data: list) -> list[list]:
    """Rows laid out as CBS's 2016 workbook lays them out (probes of 4 October 2026):
    headings on three rows, the national row, then a row per gemeente."""
    return [
        ["Kerkelijke gezindte en kerkbezoek naar gemeenten 2010/2015"] + [None] * 17,
        [None] * 18,
        [None, None, None, "Kerkbezoek, minimaal 1x per maand (percentage van gehele 18+ populatie)",
         None, "Geen kerkelijke gezindte", "Wel kerkelijke gezindte", "waarvan"] + [None] * 10,
        [None] * 7 + ["Rooms-katholiek", "Protestants", "waarvan", None, None, "Islam", "Joods",
                      "Hindoe", "Boeddhist", "anders", None],
        [None] * 9 + ["Nederlands hervormd", "Gereformeerde kerken",
                      "Protestantse Kerk Nederland(PKN)"] + [None] * 6,
        NATIONAL,
        *data,
    ]


NATIONAL = [None, "Nederland totaal", None, 16.85, None, 47.93, 52.07, 25.49, 16.27, 7.04, 3.46,
            5.77, 4.77, 0.12, 0.62, 0.37, 4.44, None]
APPINGEDAM = ["GM0003", "Appingedam", "0003", 11.91, None, 55.17, 44.83, 3.71, 28.880000000000003,
              10.24, 8.29, 10.35, 3.85, 0, 0, 0.28, 8.1, None]
# Suppressed: "." everywhere but the Protestant subtotal, a formula that reads 0.
AMELAND = ["GM0060", "Ameland", "0060", ".", None, ".", ".", ".", 0, ".", ".", ".", ".", ".", ".",
           ".", ".", None]


class TheWorkbook(unittest.TestCase):

    def test_a_printed_and_a_suppressed_gemeente_and_the_country(self):
        rows, national = m.parse_table(sheet(APPINGEDAM, AMELAND))
        self.assertEqual(set(rows), {"GM0003", "GM0060"})
        self.assertEqual(rows["GM0003"]["total"], 44.83)
        self.assertEqual(rows["GM0003"]["none"], 55.17)
        self.assertEqual(rows["GM0003"]["parts"]["Roman Catholic"], 3.71)
        self.assertEqual(rows["GM0003"]["parts"]["Protestant Church in the Netherlands"], 10.35)
        self.assertEqual(rows["GM0003"]["parts"][m.OTHER], 8.1)
        self.assertIsNone(rows["GM0060"]["total"])
        self.assertEqual(national["total"], 52.07)
        m.check_table({**rows, "NL01": national})

    def test_the_subtotal_is_not_taken_for_the_church_whose_name_it_begins(self):
        rows, _ = m.parse_table(sheet(APPINGEDAM))
        self.assertEqual(rows["GM0003"]["protestant"], 28.880000000000003)
        self.assertEqual(rows["GM0003"]["parts"]["Protestant Church in the Netherlands"], 10.35)

    def test_categories_that_do_not_make_the_total_stop_the_run(self):
        wrong = list(APPINGEDAM)
        wrong[7] = 5.71                                         # Roman Catholic two points too many
        with self.assertRaises(SystemExit):
            m.check_table(m.parse_table(sheet(wrong))[0])

    def test_churches_that_do_not_make_the_protestant_subtotal_stop_the_run(self):
        wrong = list(APPINGEDAM)
        wrong[8] = 30.88
        with self.assertRaises(SystemExit):
            m.check_table(m.parse_table(sheet(wrong))[0])

    def test_a_total_with_a_share_missing_stops_the_run(self):
        wrong = list(APPINGEDAM)
        wrong[12] = "."
        with self.assertRaises(SystemExit):
            m.parse_table(sheet(wrong))

    def test_two_codes_that_disagree_stop_the_run(self):
        wrong = list(APPINGEDAM)
        wrong[2] = "0004"
        with self.assertRaises(SystemExit):
            m.parse_table(sheet(wrong))

    def test_a_heading_found_twice_stops_the_run(self):
        rows = sheet(APPINGEDAM)
        rows[3] = list(rows[3])
        rows[3][17] = "anders"
        with self.assertRaises(SystemExit):
            m.parse_table(rows)


def sheet_2014(*data: list) -> list[list]:
    """Rows laid out as CBS's 2010-2014 workbook lays them out (probe of 4 October 2026)."""
    blank = [""] * 15
    return [
        ["Kerkelijke gezindte en kerkbezoek naar gemeente, 2010-2014 1)"] + [""] * 14,
        ["-"] + [""] * 14,
        ["", "", "", "Maandelijks bezoek religieuze dienst",
         "Kerkelijke gezindte of levensbeschouwelijke groepering", "", "w.v."] + [""] * 8,
        ["", "", "", "", "", ""] + ["---"] * 9,
        ["", "", "", "", "", "", "Katholiek", "Hervormd", "Gereformeerd", "PKN", "Islam", "Joods",
         "Hindoe", "Boeddhist", "Anders"],
        ["", "", "", "%"] + [""] * 11,
        ["Provincie", "Gemeente", "Gemcode"] + [""] * 12,
        *data,
        ["-"] + [""] * 14,
        ["1) Gemeentelijke indeling 2014, minimaal 150 waarnemingen per gemeente"] + [""] * 14,
        ["Bron: CBS"] + [""] * 14,
        blank,
    ]


APPINGEDAM_2014 = ["Groningen", "Appingedam", 3.0, 10.3, 44.7, "", 3.2, 11.4, 8.2, 10.9, 3.4, 0.0,
                   0.0, 0.3, 7.4]
AMELAND_2014 = ["Friesland", "Ameland", 60.0, ".", ".", "", ".", ".", ".", ".", ".", ".", ".", ".",
                "."]


class TheWorkbookOf2014(unittest.TestCase):
    """The 2010-2014 table, read only to measure the union method."""

    def test_a_printed_and_a_suppressed_gemeente(self):
        rows = m.parse_table_2014(sheet_2014(APPINGEDAM_2014, AMELAND_2014))
        self.assertEqual(set(rows), {"GM0003", "GM0060"})
        self.assertEqual(rows["GM0003"]["total"], 44.7)
        self.assertEqual(rows["GM0003"]["parts"]["Roman Catholic"], 3.2)
        self.assertEqual(rows["GM0003"]["province"], "Groningen")
        self.assertIsNone(rows["GM0060"]["total"])
        m.check_table(rows, m.OLD_SUM_TOLERANCE)

    def test_the_total_is_the_column_under_its_heading_not_the_title(self):
        rows = m.parse_table_2014(sheet_2014(APPINGEDAM_2014))
        self.assertEqual(rows["GM0003"]["total"], 44.7)        # not the attendance, 10.3

    def test_categories_that_do_not_make_the_total_stop_the_run(self):
        wrong = list(APPINGEDAM_2014)
        wrong[6] = 5.2                                          # Katholiek two points too many
        with self.assertRaises(SystemExit):
            m.check_table(m.parse_table_2014(sheet_2014(wrong)), m.OLD_SUM_TOLERANCE)

    def test_a_total_with_a_share_missing_stops_the_run(self):
        wrong = list(APPINGEDAM_2014)
        wrong[10] = "."
        with self.assertRaises(SystemExit):
            m.parse_table_2014(sheet_2014(wrong))


class TheComposition(unittest.TestCase):

    def test_no_religion_is_the_rest_and_zeros_are_left_out(self):
        rows = m.parse_table(sheet(APPINGEDAM))[0]["GM0003"]
        out = m.composition(rows["parts"], rows["total"])
        shares = {r["group"]: r["pct"] for r in out}
        self.assertEqual(shares["No religion"], 55.2)
        self.assertEqual(shares["Dutch Reformed"], 10.2)
        self.assertNotIn("Judaism", shares)
        self.assertLessEqual(abs(sum(shares.values()) - 100.0), 0.2)
        self.assertEqual(out[0]["group"], "No religion")

    def test_a_union_is_weighted_by_its_adults(self):
        rows = {"GM0001": {"total": 40.0, "parts": parts({"Roman Catholic": 40.0})},
                "GM0002": {"total": 80.0, "parts": parts({"Roman Catholic": 80.0})}}
        total, shares = m.blend(rows, {"GM0001": 3000.0, "GM0002": 1000.0})
        self.assertAlmostEqual(total, 50.0)
        self.assertAlmostEqual(shares["Roman Catholic"], 50.0)

    def test_every_label_has_a_place_in_the_group_tree(self):
        import group_tree
        for label in m.LABELS:
            self.assertIsNotNone(group_tree.parent_of("religion", label), label)
        self.assertEqual(group_tree.parent_of("religion", "Roman Catholic"), "Catholicism")
        for label in m.PROTESTANT:
            self.assertEqual(group_tree.parent_of("religion", label), "Protestantism", label)

    def test_the_residual_is_labelled_as_the_province_file_labels_it(self):
        from fetch_census import netherlands_religion
        self.assertEqual(m.OTHER, netherlands_religion.OTHER)

    def test_the_basis_says_survey_estimate(self):
        self.assertTrue(m.BASIS.startswith("survey estimate"))
        self.assertTrue(m.OUT.name.endswith("_survey.json"))


class ChecksAgainstCBSsOwnFigures(unittest.TestCase):

    @staticmethod
    def two() -> dict:
        return {"GM0001": {"name": "A", "total": 40.0, "parts": parts({"Roman Catholic": 40.0})},
                "GM0002": {"name": "B", "total": 60.0, "parts": parts({"Roman Catholic": 60.0})},
                "GM0003": {"name": "C", "total": None, "parts": {}}}

    ADULTS = {"GM0001": 1000.0, "GM0002": 3000.0, "GM0003": 1000.0}

    def test_the_gemeenten_weighted_by_adults_make_the_national_row(self):
        national = {"total": 55.0, "parts": parts({"Roman Catholic": 55.0})}
        self.assertAlmostEqual(m.check_national(self.two(), self.ADULTS, national), 0.0)

    def test_a_national_row_they_miss_stops_the_run(self):
        national = {"total": 56.0, "parts": parts({"Roman Catholic": 56.0})}
        with self.assertRaises(SystemExit):
            m.check_national(self.two(), self.ADULTS, national)

    def test_low_precision_runs_as_high_as_the_rate_overestimates_a_suppressed_gemeente(self):
        # C was suppressed (fewer than 150) but this rate puts it at 180: 20% high.
        self.assertAlmostEqual(m.low_precision_cut(self.two(), self.ADULTS, 0.18), 360.0)
        # At a rate putting it at 90 there is nothing to correct.
        self.assertAlmostEqual(m.low_precision_cut(self.two(), self.ADULTS, 0.09), 300.0)


class TheUnionMethodMeasured(unittest.TestCase):
    """The 2014 table's gemeenten carried to a later division by the union
    method, against CBS's own figures for that division."""

    def test_a_union_and_a_gemeente_that_stayed_are_compared_and_the_rest_left(self):
        history = mini_history()
        history["GM0006"] = gemeente("G", "18300101", "", "")
        population = dict(POPULATION, GM0006=500.0)
        walk = m.follow(history, population, "20140101", "20221231")
        old = table()
        old["GM0001"] = {**old["GM0001"], "parts": parts({"Roman Catholic": 40.0})}
        old["GM0002"] = {**old["GM0002"], "total": 60.0, "parts": parts({"Roman Catholic": 60.0})}
        old["GM0006"] = {"name": "G", "total": 30.0, "parts": parts({"Islam": 30.0})}
        adults = {c: 0.8 * p for c, p in population.items()}
        new = {"GM0100": {"name": "N", "total": 56.0, "parts": parts({"Roman Catholic": 56.0})},
               "GM0006": {"name": "G", "total": 31.0, "parts": parts({"Islam": 31.0})},
               "GM0004": {"name": "D", "total": 40.0, "parts": parts()},
               "GM0200": {"name": "F", "total": 40.0, "parts": parts()}}
        titles = dict(TITLES, GM0006="G")
        unions, same = m.compare_unions(old, walk, population, adults, new, titles)
        # N is A (800 adults) and B (2,400): (40 x 800 + 60 x 2,400) / 3,200 = 55; CBS says 56.
        # D and F hold parts of the divided C, so neither is compared.
        self.assertEqual([(round(g, 2), name, n) for g, name, n in unions], [(1.0, "N", 2)])
        self.assertEqual([(round(g, 2), name, n) for g, name, n in same], [(1.0, "G", 1)])


class Binding(unittest.TestCase):

    SHAPES = [{"id": "s1", "name": "Hengelo (O)", "codes": {"cbs_gemeente": "GM0164"}},
              {"id": "s2", "name": "Groningen", "codes": {"cbs_gemeente": "GM0014"}},
              {"id": "s3", "name": "Bergen (L)", "codes": {}},
              {"id": "s4", "name": "Bergen (NH)", "codes": {}}]

    def test_by_code_and_checked_by_label(self):
        bound, problems = m.bind(["GM0164", "GM0014"],
                                 {"GM0164": "Hengelo (O.)", "GM0014": "Groningen"}, self.SHAPES)
        self.assertEqual(problems, [])
        self.assertEqual({c: s["id"] for c, s in bound.items()}, {"GM0164": "s1", "GM0014": "s2"})

    def test_a_code_on_a_polygon_of_another_name_is_refused(self):
        _, problems = m.bind(["GM0014"], {"GM0014": "Haren"}, self.SHAPES)
        self.assertEqual(len(problems), 1)

    def test_two_polygons_for_one_name_are_refused_not_guessed(self):
        _, problems = m.bind(["GM0893"], {"GM0893": "Bergen"}, self.SHAPES)
        self.assertIn("2 polygons", problems[0])

    def test_statlines_suffix_and_a_province_qualifier_are_not_the_name(self):
        self.assertTrue(m.same_place("Groningen (gemeente)", "Groningen"))
        self.assertTrue(m.same_place("Beek (L.)", "Beek"))
        self.assertTrue(m.same_place("Hengelo (O.)", "Hengelo (O)"))
        self.assertFalse(m.same_place("Haren", "Groningen"))

    def test_every_drawn_gemeente_carries_its_cbs_code(self):
        import json
        path = Path(__file__).resolve().parent.parent / "site" / "data" / "admin2" / "NLD.units.json"
        if not path.exists():
            self.skipTest("no built NLD file")
        codes = Counter((u.get("codes") or {}).get("cbs_gemeente") for u in json.loads(path.read_text()))
        self.assertEqual(len(codes), m.DRAWN)
        self.assertNotIn(None, codes)


class AgesOnAnOlderDate(unittest.TestCase):
    """03759ned by gemeente gives single years to 94 and then "95 jaar of
    ouder" on 1 January 2014, where 2022 runs to 104 and "105 jaar of ouder"
    (probe of 4 October 2026: Almere's single years fell 82 short of its
    total, the 82 aged 95 or over). Shrunk here to four single years."""

    META = {
        "DataProperties": [{"Type": "Topic", "Key": "Pop_1"}],
        "Geslacht": [{"Key": "T", "Title": "Totaal mannen en vrouwen"},
                     {"Key": "M", "Title": "Mannen"}, {"Key": "V", "Title": "Vrouwen"}],
        "Leeftijd": [{"Key": "TOT", "Title": "Totaal"},
                     *({"Key": f"A{n}", "Title": f"{n} jaar"} for n in range(4)),
                     {"Key": "T2", "Title": "2 jaar of ouder"},
                     {"Key": "T4", "Title": "4 jaar of ouder"}],
        "BurgerlijkeStaat": [{"Key": "BT", "Title": "Totaal burgerlijke staat"}],
    }

    def read(self, rows):
        from unittest import mock
        from fetch_census import netherlands_gemeente as nld

        def fake(table, path, params=None):
            return rows if path == "TypedDataSet" else self.META[path]
        with mock.patch.object(nld, "odata", fake):
            return nld.read_ages(["GM0001"], period="2014JJ00")

    @staticmethod
    def rows(values):
        return [{"RegioS": "GM0001", "Geslacht": sex, "Leeftijd": age, "Pop_1": value}
                for (sex, age), value in values.items()]

    def test_the_open_class_after_the_last_single_year_given_is_counted(self):
        out = self.read(self.rows({("T", "TOT"): 100, ("M", "A0"): 10, ("M", "A1"): 20,
                                   ("M", "A2"): None, ("M", "T4"): None, ("M", "T2"): 15,
                                   ("V", "A0"): 12, ("V", "A1"): 18, ("V", "T2"): 25}))
        self.assertEqual(dict(out["GM0001"]["m"]), {0: 10, 1: 20, 2: 15})
        self.assertEqual(dict(out["GM0001"]["f"]), {0: 12, 1: 18, 2: 25})

    def test_where_the_single_years_go_on_it_is_a_subtotal_and_not_counted(self):
        out = self.read(self.rows({("T", "TOT"): 20, ("M", "A0"): 1, ("M", "A1"): 2, ("M", "A2"): 3,
                                   ("M", "A3"): 2, ("M", "T4"): 1, ("M", "T2"): 6,
                                   ("V", "A0"): 2, ("V", "A1"): 2, ("V", "A2"): 3, ("V", "A3"): 3,
                                   ("V", "T4"): 1, ("V", "T2"): 7}))
        self.assertEqual(sum(out["GM0001"]["m"].values()) + sum(out["GM0001"]["f"].values()), 20)
        self.assertEqual(out["GM0001"]["m"][4], 1)

    def test_ages_that_still_do_not_make_the_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            self.read(self.rows({("T", "TOT"): 100, ("M", "A0"): 10, ("V", "A0"): 12}))


class TheNote(unittest.TestCase):

    ROWS = {"GM0001": {"name": "A"}, "GM0002": {"name": "B"}, "GM0005": {"name": "E"}}

    def test_a_union_names_its_parts_and_a_small_one_says_low_precision(self):
        unit = m.Unit("GM0100", {"GM0001": 1.0, "GM0002": 1.0}, {}, 0.0, [], None)
        note = m.unit_note(unit, "N", self.ROWS, 250.0)
        self.assertIn(f"N covers what in {m.VINTAGE} were the gemeenten A and B", note)
        self.assertIn(f"on 1 January {m.VINTAGE}", note)
        self.assertIn("Low precision", note)
        self.assertIn("would give about 250.", note)
        larger = m.unit_note(unit, "N", self.ROWS, 1234.0)
        self.assertNotIn("Low precision", larger)
        self.assertIn("would give about 1,234.", larger)

    def test_just_above_300_it_is_low_precision_while_the_estimate_can_run_high(self):
        unit = m.Unit("GM0001", {"GM0001": 1.0}, {}, 0.0, [], None)
        note = m.unit_note(unit, "A", self.ROWS, 320.0, cut=345.0)
        self.assertIn("Low precision", note)
        self.assertIn("would give about 320, and that estimate runs high", note)
        self.assertIn("fewer than 300 is possible", note)
        self.assertNotIn("Low precision", m.unit_note(unit, "A", self.ROWS, 320.0))

    def test_a_gemeente_renamed_since_names_what_it_was(self):
        unit = m.Unit("GM0200", {"GM0005": 1.0}, {}, 0.0, [], None)
        note = m.unit_note(unit, "F", self.ROWS, 1000.0)
        self.assertIn(f"F is the gemeente of {m.VINTAGE} E (renamed since).", note)

    def test_the_note_says_what_the_survey_was(self):
        self.assertIn("Enquête Beroepsbevolking", m.NOTE)
        self.assertIn("2010-2015", m.NOTE)
        self.assertIn("18 and over", m.NOTE)
        self.assertIn("150 respondents", m.NOTE)
        self.assertIn("no questionnaire census since 1971", m.NOTE)
        self.assertIn("latest table by gemeente", m.NOTE)

    def test_the_respondents_are_the_adults_among_the_samples(self):
        # 460,000 adults among 2010-2014's 508,224, carried to 2010-2015's 606,189.
        self.assertEqual(m.RESPONDENTS, 549_000)


if __name__ == "__main__":
    unittest.main()
