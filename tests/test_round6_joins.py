"""Round 6, joins: decoding, declared aliases and unions, and figures refused as other ground.

Each test names the case it was written for. The declaration tables are
checked against the files and shapes they name, so a stale entry fails here
rather than silently matching nothing in a build.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_entities as be  # noqa: E402
import nuts_crosswalk  # noqa: E402
from common import shard_name  # noqa: E402
from fetch_census import cod_ps  # noqa: E402
from scripts.fetch_census import georgia, transnistria, uscb  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SITE = ROOT / "site" / "data"


def shapes(iso3: str) -> dict[str, dict]:
    """Every polygon the published build draws for a country, by id and level."""
    out = {}
    for level in ("admin1", "admin2"):
        path = SITE / level / shard_name(iso3)
        if path.exists():
            for unit in json.loads(path.read_text(encoding="utf-8")):
                out[(level, unit["id"])] = unit
    return out


def rows(filename: str) -> dict[str, dict]:
    path = PROCESSED / filename
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"]: r for r in data if isinstance(r, dict) and r.get("id")}


class CodPsDecoding(unittest.TestCase):
    """cod_ps decoded with 'replace', and 34 CAF names and one AGO name broke."""

    def test_a_utf8_table_is_read_as_utf8(self):
        text, fallen = cod_ps.decode_table("Pango-Aluquém,Baía Farta\n".encode())
        self.assertEqual(text, "Pango-Aluquém,Baía Farta\n")
        self.assertEqual(fallen, 0)

    def test_a_byte_order_mark_is_dropped(self):
        self.assertEqual(cod_ps.decode_table(b"\xef\xbb\xbfADM2_EN")[0], "ADM2_EN")

    def test_only_the_bytes_that_are_not_utf8_are_read_as_cp1252(self):
        # Angola's table: UTF-8 everywhere but "Chitato (L\xf3vua)".
        raw = ("Huíla,Lubango\n".encode() + b"Lunda Norte,Chitato (L\xf3vua)\n")
        text, fallen = cod_ps.decode_table(raw)
        self.assertEqual(text, "Huíla,Lubango\nLunda Norte,Chitato (Lóvua)\n")
        self.assertEqual(fallen, 1)

    def test_a_cp1252_table_reads_whole(self):
        # The Central African Republic's: "Ndélé", "Mambéré Kadéi".
        raw = "Mambéré Kadéi,CF21,Berbérati\nBamingui Bangoran,CF51,Ndélé\n".encode("cp1252")
        text, _ = cod_ps.decode_table(raw)
        self.assertIn("Berbérati", text)
        self.assertIn("Ndélé", text)
        self.assertNotIn(cod_ps.DAMAGED, text)

    def test_a_byte_cp1252_leaves_undefined_stays_damaged(self):
        text, fallen = cod_ps.decode_line(b"Nd\x81l")
        self.assertEqual(text, "Nd�l")
        self.assertEqual(fallen, 1)

    def test_a_damaged_name_stops_the_run(self):
        table = (["ADM2_EN", "ADM2_PCODE", "ADM1_EN", "T_TL", "year"],
                 [{"ADM2_EN": "Nd�l�", "ADM2_PCODE": "CF511",
                   "ADM1_EN": "Bamingui Bangoran", "T_TL": "45928", "year": "2015"}],
                 "caf_admpop_adm2_2015.csv")
        with mock.patch.object(cod_ps, "read_table", return_value=table):
            with self.assertRaises(SystemExit) as stop:
                cod_ps.read_units({}, {"name": "caf_admpop_adm2_2015.csv"}, "2")
        self.assertIn("Nd�l�", str(stop.exception))

    def test_a_damaged_parent_name_stops_the_run_too(self):
        rows_ = [{"a": "Bossembélé", "p": "Mamb�r� Kad�i"}]
        self.assertEqual(cod_ps.damaged_names(rows_, "a", "p"), ["Mamb�r� Kad�i"])

    def test_no_name_in_the_file_is_damaged(self):
        data = rows("cod_ps_admin2.json")
        if not data:
            self.skipTest("cod_ps_admin2.json is not in this checkout")
        damaged = [r["id"] for r in data.values()
                   if cod_ps.DAMAGED in (r.get("name") or "") + (r.get("parent_name") or "")]
        self.assertEqual(damaged, [])
        self.assertEqual(data["CAF-CODPS-CF511"]["name"], "Ndélé")
        self.assertEqual(data["AGO-CODPS-AO12104"]["name"], "Chitato (Lóvua)")


class CodPsOnly(unittest.TestCase):
    """--only CAF,AGO used to write a file of CAF and AGO alone."""

    OLD = [{"id": "AGO-1", "country": "AGO"}, {"id": "BDI-1", "country": "BDI"},
           {"id": "AGO-2", "country": "AGO"}, {"id": "CAF-1", "country": "CAF"}]

    def test_the_other_countries_are_kept_in_place(self):
        new = [{"id": "AGO-1", "country": "AGO", "fresh": True},
               {"id": "CAF-1", "country": "CAF", "fresh": True}]
        out = cod_ps.merged(self.OLD, new, {"AGO", "CAF"})
        self.assertEqual([r["id"] for r in out], ["AGO-1", "BDI-1", "CAF-1"])
        self.assertTrue(all(r.get("fresh") for r in out if r["country"] != "BDI"))

    def test_a_country_asked_for_and_not_read_stops_the_run(self):
        with self.assertRaises(SystemExit):
            cod_ps.merged(self.OLD, [{"id": "AGO-1", "country": "AGO"}], {"AGO", "CAF"})


class Declarations(unittest.TestCase):
    """Every declaration names a row that exists and a shape that is drawn."""

    def test_every_alias_is_a_label_drawn_in_the_rows_country(self):
        for filename, by_id in be.ROW_ALIASES.items():
            data = rows(filename)
            if not data:
                continue
            for row_id, aliases in by_id.items():
                self.assertIn(row_id, data, f"{filename}: {row_id} is not in the file")
                iso3 = row_id[:3]
                labels = {u["name"] for u in shapes(iso3).values()}
                if not labels:
                    continue
                for alias in aliases:
                    self.assertIn(alias, labels, f"{row_id}: {alias!r} is not drawn")

    def test_every_alias_label_is_drawn_once_at_its_rows_level(self):
        for filename, by_id in be.ROW_ALIASES.items():
            data = rows(filename)
            for row_id, aliases in by_id.items():
                level = (data.get(row_id) or {}).get("level", "admin2")
                units = [u for (lv, _), u in shapes(row_id[:3]).items() if lv == level]
                for alias in aliases:
                    count = sum(1 for u in units if u["name"] == alias)
                    self.assertLessEqual(count, 1, f"{alias!r} is drawn {count} times")

    def test_row_shapes_and_unions_name_drawn_polygons(self):
        for by_id in be.ROW_SHAPES.values():
            for row_id, (shape_id, label) in by_id.items():
                drawn = {sid: u for (_, sid), u in shapes(row_id[:3]).items()}
                if drawn:
                    self.assertEqual(drawn[shape_id]["name"], label)
        for (iso3, name), spec in be.ROW_UNIONS.items():
            drawn = shapes(iso3)
            data = rows(spec["file"])
            for rid in spec["rows"]:
                if data:
                    self.assertIn(rid, data, f"{iso3} {name}: {rid}")
            for level, shape_id in spec["shapes"]:
                if drawn:
                    self.assertEqual(drawn[(level, shape_id)]["name"], name)

    def test_not_this_ground_names_drawn_polygons(self):
        for (iso3, shape_id), fields in be.NOT_THIS_GROUND.items():
            drawn = {sid for (_, sid) in shapes(iso3)}
            if drawn:
                self.assertIn(shape_id, drawn, f"{iso3} {shape_id}")
            for field, (source, note) in fields.items():
                self.assertTrue(note.endswith("."), f"{iso3} {field}")
                for word in ("cod_ps", ".json", "adapter", "build", "pipeline"):
                    self.assertNotIn(word, note, f"{iso3} {field}")

    def test_the_argoba_row_is_scoped_to_amhara_and_drawn(self):
        # The polygon "Special Woreda" in Amhara is Argoba's; Bahir Dar's
        # special wereda stays a declared absence.
        self.assertEqual(uscb.ETHIOPIA.aliases["Argoba Special Wereda"], ("Special Woreda",))
        self.assertNotIn(("Āmara", "Argoba Special Wereda"), uscb.ETHIOPIA.no_shape)
        self.assertIn(("Āmara", "Bahir Dar Special Wereda"), uscb.ETHIOPIA.no_shape)

    def test_nordjylland_is_decided(self):
        for code in ("DK05", "DK050"):
            self.assertEqual(nuts_crosswalk.DECIDED[code][0], "84455774B84842167963849")


def admin2(name, sid, parent="P", **extra):
    return {"id": sid, "level": "admin2", "name": name, "parent": parent, "country": "TZA",
            **extra}


class Matching(unittest.TestCase):
    """The aliases reach the polygon by an exact name inside the row's region."""

    def index(self, units):
        by_name = {}
        for u in units:
            by_name.setdefault(be.norm(u["name"]), []).append(u)
        return by_name

    def test_a_municipal_council_reaches_the_urban_polygon_not_the_district(self):
        units = [admin2("Moshi", "d"), admin2("Moshi Urban", "u")]
        region = {"kilimanjaro": {"id": "P", "name": "Kilimanjaro"}}
        row = {"name": "MOSHI MUNICIPAL", "parent_name": "KILIMANJARO",
               "aliases": ["Moshi Urban"]}
        got, how = be.match_admin2(row, self.index(units), region)
        self.assertEqual(got["id"], "u")
        self.assertTrue(how.startswith("alias"))

    def test_a_province_named_by_the_row_tells_two_samraongs_apart(self):
        units = [admin2("Samraong", "takeo", parent="T"),
                 admin2("Samraong", "oddar", parent="O")]
        regions = {"takeo": {"id": "T", "name": "Takeo"},
                   "oddarmeanchey": {"id": "O", "name": "Oddar Meanchey"}}
        got, how = be.match_admin2({"name": "Samraong"}, self.index(units), regions)
        self.assertIsNone(got)
        self.assertEqual(how, "ambiguous")
        got, _ = be.match_admin2({"name": "Samraong", "parent_name": "Takeo"},
                                 self.index(units), regions)
        self.assertEqual(got["id"], "takeo")


class LoadAdapters(unittest.TestCase):
    """Aliases, parents, polygons and notes reach the rows; pooled parts survive superseding."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)
        cod = [
            {"id": "TZA-CODPS-TZ0306", "name": "MOSHI MUNICIPAL", "country": "TZA",
             "level": "admin2", "population": {"value": 221588, "year": 2020}},
            {"id": "TZA-CODPS-TZ0203", "name": "ARUSHA CITY", "country": "TZA",
             "level": "admin2", "population": {"value": 536007, "year": 2020}},
            {"id": "AGO-CODPS-AO09077", "name": "Lubango", "country": "AGO",
             "level": "admin2", "population": {"value": 1119881, "year": 2024}},
            {"id": "PRY-CODPS-PY1302", "name": "Bella Vista", "country": "PRY",
             "level": "admin2", "parent_name": "Amambay",
             "population": {"value": 19150, "year": 2023}},
            {"id": "PRY-CODPS-PY1301", "name": "Pedro Juan Caballero", "country": "PRY",
             "level": "admin2", "population": {"value": 126874, "year": 2023}},
        ]
        clear = [{"id": "KHM-CG-KH2107", "name": "Samraong", "country": "KHM",
                  "level": "admin2"}]
        census = [{"id": "PRY-INE-x", "name": "x", "country": "PRY", "level": "admin2"}]
        (path / "cod_ps_admin2.json").write_text(json.dumps(cod))
        (path / "clear_global_language.json").write_text(json.dumps(clear))
        (path / "paraguay_census.json").write_text(json.dumps(census))
        self.patches = [
            mock.patch.object(be, "PROCESSED", path),
            mock.patch.object(be, "ADAPTER_FILES", ["paraguay_census.json",
                                                    "clear_global_language.json",
                                                    "cod_ps_admin2.json"]),
            mock.patch.object(be, "SUPERSEDED_ROWS",
                              {"cod_ps_admin2.json": {"PRY": "paraguay_census.json"}}),
        ]
        for p in self.patches:
            p.start()
        with mock.patch.object(be, "log"):
            self.loaded = {r["id"]: r for rows_ in be.load_adapters().values() for r in rows_}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_alias(self):
        self.assertIn("Moshi Urban", self.loaded["TZA-CODPS-TZ0306"]["aliases"])

    def test_parent(self):
        self.assertEqual(self.loaded["KHM-CG-KH2107"]["parent_name"], "Takeo")

    def test_polygon(self):
        row = self.loaded["TZA-CODPS-TZ0203"]
        self.assertEqual((row["name"], row["match_by"], row["shape_id"]),
                         ("Arusha Urban", "shape_id", "72390352B90906351205470"))
        self.assertIn("ARUSHA CITY", row["aliases"])

    def test_note(self):
        self.assertIn("Cacula", self.loaded["AGO-CODPS-AO09077"]["population"]["note"])

    def test_a_pooled_part_survives_its_countrys_superseding(self):
        self.assertIn("PRY-CODPS-PY1302", self.loaded)
        self.assertNotIn("PRY-CODPS-PY1301", self.loaded)


def cod_row(rid, name, value, parent_name=None, year=2023):
    return {"id": rid, "name": name, "level": "admin2", "parent": "X", "country": rid[:3],
            "parent_name": parent_name, "_source": "cod_ps_admin2.json",
            "population": {"value": value, "year": year, "source": "OCHA"},
            "sources": [{"field": "population", "name": "OCHA", "url": "u"}]}


class Unions(unittest.TestCase):
    def pool(self, adapters):
        with mock.patch.object(be, "log"):
            return be.pool_row_unions(adapters)

    def test_zomba_is_its_district_and_its_city(self):
        adapters = {"MWI": [cod_row("MWI-CODPS-MW314", "Zomba District", 831015),
                            cod_row("MWI-CODPS-MW303", "Zomba City", 116797)]}
        done = self.pool(adapters)
        self.assertTrue(any(d.startswith("MWI Zomba") for d in done))
        (row,) = adapters["MWI"]
        self.assertEqual(row["population"]["value"], 947812)
        self.assertEqual((row["match_by"], row["shape_id"], row["level"], row["name"]),
                         ("shape_id", "42251766B13881881574545", "admin2", "Zomba"))
        self.assertIn("Zomba District and Zomba City", row["population"]["note"])
        self.assertIn("lies inside this one", row["population"]["note"])

    def test_a_union_missing_a_part_is_not_pooled(self):
        adapters = {"MWI": [cod_row("MWI-CODPS-MW314", "Zomba District", 831015)]}
        self.pool(adapters)
        self.assertEqual([r["id"] for r in adapters["MWI"]], ["MWI-CODPS-MW314"])

    def test_dire_dawa_is_written_at_both_levels(self):
        adapters = {"ETH": [cod_row("ETH-CODPS-ET1501", "Dire Dawa urban", 328357, year=2022),
                            cod_row("ETH-CODPS-ET1502", "Dire Dawa rural", 192643, year=2022)]}
        self.pool(adapters)
        got = {r["level"]: r for r in adapters["ETH"]}
        self.assertEqual(set(got), {"admin1", "admin2"})
        self.assertEqual({r["population"]["value"] for r in got.values()}, {521000})
        self.assertEqual(got["admin1"]["shape_id"], "75662566B22109266514860")

    def test_two_parts_of_one_name_are_told_apart_by_province(self):
        adapters = {"PRY": [cod_row("PRY-CODPS-PY1302", "Bella Vista", 19150, "Amambay"),
                            cod_row("PRY-CODPS-PY0702", "Bella Vista", 15863, "Itapúa")]}
        self.pool(adapters)
        (row,) = adapters["PRY"]
        self.assertEqual(row["population"]["value"], 35013)
        self.assertIn("Bella Vista (Amambay) and Bella Vista (Itapúa)",
                      row["population"]["note"])
        self.assertIn("Cerro Corá", row["population"]["note"])

    def test_survey_counts_are_summed_and_the_caveat_kept(self):
        caveat = "Regional shares are survey estimates, not census counts."

        def part(rid, name, n, portuguese):
            return {"id": rid, "name": name, "level": "admin1", "country": "MOZ",
                    "_source": "afrobarometer_region.json",
                    "language": [{"group": "Portuguese", "pct": 100 * portuguese / n,
                                  "count": portuguese},
                                 {"group": "Changana", "pct": 100 * (n - portuguese) / n,
                                  "count": n - portuguese}],
                    "language_note": f"{caveat} This region: {n} respondents."}
        adapters = {"MOZ": [part("MOZ-AB9-540", "Maputo Province", 100, 53),
                            part("MOZ-AB9-541", "Maputo City", 50, 41)]}
        self.pool(adapters)
        (row,) = adapters["MOZ"]
        shares = {g["group"]: g["pct"] for g in row["language"]}
        self.assertEqual(shares["Portuguese"], 62.7)
        self.assertTrue(row["language_note"].startswith(caveat))
        self.assertNotIn("This region", row["language_note"])

    def test_shares_with_nothing_to_weigh_them_by_say_so(self):
        # Moses Garoeb and Tobias Hainyeko: CLEAR's survey shares, no counts.
        def part(name, pct):
            return {"id": name, "name": name, "_source": "clear_global_language.json",
                    "language": [{"group": "Ndonga", "pct": pct},
                                 {"group": "Nama", "pct": 100 - pct}]}
        with mock.patch.object(be, "log"):
            pooled = be.pool_rows("Moses Garoeb and Tobias Hainyeko",
                                  [part("Moses Garoeb", 80), part("Tobias Hainyeko", 70)],
                                  "NAM", "clear_global_language.json")
        self.assertEqual(pooled["language"]["status"], be.NOT_AVAILABLE)
        self.assertIn("not combined", pooled["language"]["note"])


def unit(sid, level="admin2", **fields):
    entity = {"id": sid, "level": level, "name": sid, "sources": []}
    entity.update(fields)
    return entity


class NotThisGround(unittest.TestCase):
    """A figure that reached the right polygon by name and describes other ground."""

    def run_pass(self, entity, declared, fields=("population",), iso3="XXX"):
        table = {iso3: [entity]}
        with mock.patch.object(be, "NOT_THIS_GROUND", {(iso3, entity["id"]): declared}), \
                mock.patch.object(be, "log"):
            return be.refuse_not_this_ground(table if entity["level"] == "admin1" else {},
                                             table if entity["level"] == "admin2" else {},
                                             fields)

    def test_the_named_files_figure_is_refused_with_the_reason(self):
        e = unit("g", population={"value": 235884, "year": 2013},
                 _from={"population": "wikidata_admin2.json"},
                 sources=[{"field": "population", "name": "Wikidata"}])
        done = self.run_pass(e, {"population": ("wikidata_admin2.json", "Not the city.")})
        self.assertEqual(done, ["XXX g population"])
        self.assertEqual(e["population"]["note"], "Not the city.")
        self.assertTrue(e["population"]["not_this_ground"])
        self.assertEqual(e["sources"], [])

    def test_another_files_figure_stands(self):
        e = unit("g", population={"value": 100}, _from={"population": "ghana_census.json"})
        done = self.run_pass(e, {"population": ("cod_ps_admin2.json", "Old district.")})
        self.assertEqual(done, [])
        self.assertEqual(e["population"]["value"], 100)

    def test_any_files_figure_where_none_could_describe_the_polygon(self):
        e = unit("m", level="admin1", population={"value": 451028},
                 _from={"population": "hcp.json"})
        self.run_pass(e, {"population": (None, "North of the line.")})
        self.assertEqual(e["population"]["note"], "North of the line.")
        self.assertTrue(e["population"]["no_child_sum"])

    def test_a_bare_gap_is_given_the_reason(self):
        e = unit("x", religion={"status": be.NOT_COLLECTED, "note": "Country policy."})
        self.run_pass(e, {"religion": (None, "Half the region.")}, fields=("religion",))
        self.assertEqual(e["religion"]["note"], "Half the region.")

    def test_fields_outside_the_pass_are_left_for_the_other(self):
        e = unit("x", religion=[{"group": "A", "pct": 100.0}])
        self.run_pass(e, {"religion": (None, "Half the region.")}, fields=("population",))
        self.assertIsInstance(e["religion"], list)

    def test_a_polygon_not_drawn_stops_the_build(self):
        with mock.patch.object(be, "NOT_THIS_GROUND",
                               {("XXX", "gone"): {"population": (None, "x.")}}):
            with self.assertRaises(SystemExit):
                be.refuse_not_this_ground({}, {}, ("population",))

    def test_a_reason_that_says_left_out_shows_the_held_figure(self):
        held = {"value": {"value": 18565, "year": 2010, "source": "census"},
                "file": "wiki_table_population.json", "match": "shape_id", "sources": []}
        e = unit("t", level="admin1", population={"value": 30000},
                 _from={"population": "wikidata_admin1.json"},
                 _held={"population": [held]})
        self.run_pass(e, {"population": ("wikidata_admin1.json", "Undated, so it is left out.")})
        self.assertEqual(e["population"]["value"], 18565)
        self.assertIn("shown instead", e["population"]["note"])

    def test_tarrafal_shows_its_2021_census_row_in_place_of_wikidatas_30000(self):
        source, note = be.NOT_THIS_GROUND[("CPV", "35879248B2594883865860")]["population"]
        self.assertEqual(source, "wikidata_admin1.json")
        held = {"value": {"value": 16620, "year": 2021, "source": "2021 census of Cape Verde",
                          "note": "The municipality's row."},
                "file": "wiki_table_population.json", "match": "shape_id", "sources": []}
        e = unit("35879248B2594883865860", level="admin1",
                 population={"value": 30000, "source": "Wikidata (CC0)"},
                 _from={"population": "wikidata_admin1.json"}, _held={"population": [held]})
        self.run_pass(e, {"population": (source, note)}, iso3="CPV")
        self.assertEqual((e["population"]["value"], e["population"]["year"]), (16620, 2021))
        self.assertTrue(e["population"]["note"].endswith("so it is left out and this figure "
                                                         "is shown instead."))


class Georgia(unittest.TestCase):
    def test_a_stated_gap_displaces_an_older_encyclopaedia_figure(self):
        why = georgia.displacing({"status": "not_available", "note": "x"}, 2026)
        self.assertEqual(why["displaces_before"], 2027)
        self.assertTrue(why["displaces_undated"])
        entity = {"population": {"value": 2008, "year": 1996}, "_from": {"population": "wikidata_admin1.json"}}
        be.merge_adapter(entity, {"_source": "georgia.json", "population": why})
        self.assertEqual(entity["population"]["status"], "not_available")


class Transnistria(unittest.TestCase):
    """475,373 is the republic's, Bender included; the shape is the left bank."""

    def test_the_left_banks_population(self):
        from tests import test_transnistria as fixture
        ethnic = transnistria.ethnic_2015(fixture.POPSTAT)
        rate = {"religion": transnistria.rates(transnistria.by_ethnicity("religion", fixture.RELIGION)),
                "language": transnistria.rates(transnistria.by_ethnicity("language", fixture.LANGUAGE))}
        drawn = {level: {"bender": "B", "transnistria": "T"} for level in ("admin1", "admin2")}
        got = {(r["name"], r["level"]): r for r in transnistria.records(ethnic, rate, drawn)}
        pop = got[("Transnistria", "admin1")]["population"]
        self.assertEqual((pop["value"], pop["year"]), (383810, 2015))
        self.assertIn("475,007", pop["note"])
        self.assertIn("91,197", pop["note"])
        self.assertNotIn("population", got[("Bender", "admin1")])


if __name__ == "__main__":
    unittest.main()
