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
                # A polygon a bound row renames keeps the boundary file's label
                # as shape_name, and rows read before the rename reach it by
                # that label: Morocco's provinces, labelled in French and
                # Arabic, are named in their Latin part by the 2024 census.
                labels = {label for u in shapes(iso3).values()
                          for label in (u["name"], u.get("shape_name")) if label}
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
            for filename, wanted in be.union_groups(spec):
                data = rows(filename)
                for rid in wanted:
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

    def test_a_composition_refusal_names_no_file(self):
        # The file a composition came from is no longer known when the
        # compositions are refused, so a refusal scoped to one never applies:
        # San Salvador's ethnicity stood through a whole build that way.
        for (iso3, shape_id), fields in be.NOT_THIS_GROUND.items():
            for field, (source, _note) in fields.items():
                if field in be.ROLLUP_FIELDS:
                    self.assertIsNone(source, f"{iso3} {shape_id} {field}")

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
        georgia = [{"id": "GEO-GEOSTAT-92138335B56355921545740", "name": "Zugdidi",
                    "country": "GEO", "level": "admin2",
                    "population": {"value": 98300, "year": 2026},
                    "population_note": "Geostat's estimate for 1 January 2026.",
                    "median_age": {"value": 40.9, "year": 2014},
                    "sex_ratio": {"value": 91.1, "year": 2014},
                    "ethnicity": [{"group": "Georgian", "pct": 99.0}]}]
        (path / "cod_ps_admin2.json").write_text(json.dumps(cod))
        (path / "clear_global_language.json").write_text(json.dumps(clear))
        (path / "paraguay_census.json").write_text(json.dumps(census))
        (path / "georgia.json").write_text(json.dumps(georgia))
        self.patches = [
            mock.patch.object(be, "PROCESSED", path),
            mock.patch.object(be, "ADAPTER_FILES", ["paraguay_census.json",
                                                    "clear_global_language.json",
                                                    "cod_ps_admin2.json",
                                                    "georgia.json"]),
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
        # Beside the figure: the sentence is about the polygon, and the figure
        # may be copied to other records.
        row = self.loaded["AGO-CODPS-AO09077"]
        self.assertIn("Cacula", row["population_note"])
        self.assertNotIn("note", row["population"])

    def test_notes_after_the_rows_own_and_on_lists_too(self):
        row = self.loaded["GEO-GEOSTAT-92138335B56355921545740"]
        self.assertTrue(row["population_note"].startswith(
            "Geostat's estimate for 1 January 2026. The outline drawn here also takes in "
            "the villages along the Enguri"), row["population_note"])
        self.assertTrue(row["population_note"].endswith("who are not in this figure."))
        for field in ("median_age", "sex_ratio"):
            self.assertTrue(row[f"{field}_note"].endswith(
                "whom the 2014 census did not count."), field)
        self.assertTrue(row["ethnicity_note"].endswith("whom the 2002 census did not count."))

    def test_a_sentence_for_a_field_the_row_lacks_stops_the_run(self):
        notes = {"cod_ps_admin2.json": {"AGO-CODPS-AO09077": {"median_age": "x."}}}
        with mock.patch.object(be, "ROW_NOTES", notes), mock.patch.object(be, "log"), \
                self.assertRaises(SystemExit):
            be.load_adapters()

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
        # The sentence goes where the panel shows a figure's note.
        self.assertNotIn("note", row["population"])
        self.assertIn("Zomba District and Zomba City", row["population_note"])
        self.assertIn("lies inside this one", row["population_note"])

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
                      row["population_note"])
        self.assertIn("Cerro Corá", row["population_note"])

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

    def test_a_refused_count_is_kept_to_weigh_the_country(self):
        e = unit("m", level="admin1", population={"value": 451028},
                 _from={"population": "hcp.json"})
        self.run_pass(e, {"population": (None, "North of the line.")})
        self.assertEqual(e["population"]["refused_value"], 451028)

    def test_a_count_a_reader_hands_on_with_its_own_reason_is_kept_too(self):
        # morocco_rgph2024 writes Laayoune-Sakia El Hamra's reason itself,
        # displacing the figure this pass would have kept, and hands the
        # region's count on with it; without it Morocco's language was not
        # summed for want of the 1.2% the region is.
        e = unit("m", level="admin1",
                 population={"status": be.NOT_AVAILABLE, "note": "Across the line.",
                             "refused_value": 451028})
        self.run_pass(e, {"population": (None, "North of the line.")})
        self.assertEqual(e["population"]["note"], "North of the line.")
        self.assertEqual(e["population"]["refused_value"], 451028)
        others = [{"population": {"value": 9_000_000},
                   "language": [{"group": "A", "pct": 100.0}]}]
        self.assertAlmostEqual(be.covered_share([e] + others, "language"),
                               9_000_000 / 9_451_028)

    def test_a_refused_count_is_never_written(self):
        e = {"population": {"status": be.NOT_AVAILABLE, "note": "x.", "refused_value": 5,
                            "not_this_ground": True}}
        be.drop_build_flags(e)
        self.assertEqual(e["population"], {"status": be.NOT_AVAILABLE, "note": "x."})

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

    def test_brussels_half_polygon_carries_none_of_the_regions_figures(self):
        # The first-level polygon is about half the region; the region's
        # figures stand whole on the second-level "Brussels".
        declared = be.NOT_THIS_GROUND[("BEL", "27649430B17719898407236")]
        self.assertEqual(set(declared), {"population", "median_age", "sex_ratio",
                                         "religion", "language", "ethnicity"})
        self.assertTrue(all(source is None for source, _ in declared.values()))
        e = unit("27649430B17719898407236", level="admin1",
                 population={"value": 1271709, "year": 2025},
                 median_age={"value": 36.1, "year": 2025},
                 sex_ratio={"value": 97.1, "year": 2025},
                 ethnicity=[{"group": "Belgian", "pct": 64.2, "count": 787590}],
                 religion={"status": be.NOT_COLLECTED, "note": "Country policy."},
                 _from={"population": "eurostat_nuts2.json"})
        self.run_pass(e, declared, fields=("population", "median_age", "sex_ratio"),
                      iso3="BEL")
        self.run_pass(e, declared, fields=be.ROLLUP_FIELDS, iso3="BEL")
        for field in declared:
            self.assertEqual(e[field]["status"], be.NOT_AVAILABLE, field)
            self.assertIn("about half of the Brussels-Capital Region", e[field]["note"])
        self.assertTrue(e["population"]["no_child_sum"])
        shapes_ = shapes("BEL")
        if shapes_:
            region = shapes_[("admin2", "21686613B18913386279163")]
            self.assertEqual(region["name"], "Brussels")

    def test_north_abacos_supervisory_district_count_is_refused(self):
        source, note = be.NOT_THIS_GROUND[("BHS", "57655419B79428110843392")]["population"]
        self.assertEqual(source, "wiki_population_admin1.json")
        e = unit("57655419B79428110843392", level="admin1",
                 population={"value": 9578, "year": 2010},
                 _from={"population": "wiki_population_admin1.json"})
        self.run_pass(e, {"population": (source, note)}, iso3="BHS")
        self.assertEqual(e["population"]["status"], be.NOT_AVAILABLE)
        self.assertIn("17,224", e["population"]["note"])


class Georgia(unittest.TestCase):
    def test_a_stated_gap_displaces_an_older_encyclopaedia_figure(self):
        why = georgia.displacing({"status": "not_available", "note": "x"}, 2026)
        self.assertEqual(why["displaces_before"], 2027)
        self.assertTrue(why["displaces_undated"])
        entity = {"population": {"value": 2008, "year": 1996}, "_from": {"population": "wikidata_admin1.json"}}
        be.merge_adapter(entity, {"_source": "georgia.json", "population": why})
        self.assertEqual(entity["population"]["status"], "not_available")


def drawn_index(iso3: str):
    """The published build's polygons of a country, indexed the way the join indexes them.

    The boundary file's own label is the key (``shape_name`` where a binding
    renamed the polygon), as it is when the build matches a row.
    """
    units = shapes(iso3)
    admin1 = [dict(u, name=u.get("shape_name") or u["name"])
              for (level, _), u in units.items() if level == "admin1"]
    admin2 = [dict(u, name=u.get("shape_name") or u["name"])
              for (level, _), u in units.items() if level == "admin2"]
    a1_by_key = {}
    for e in admin1:
        a1_by_key.setdefault(be.norm(e["name"]), []).append(e)
    a1 = {k: v[0] for k, v in a1_by_key.items() if len(v) == 1}
    a1_exact = {" ".join(e["name"].split()).casefold(): e for e in admin1}
    a2 = {}
    for e in admin2:
        if not e.get("remainder"):
            a2.setdefault(be.norm(e["name"]), []).append(e)
    be.add_known_as(a2, admin2)
    return a2, a1, a1_exact, {e["id"]: e["name"] for e in admin1}


def join(row: dict, iso3: str):
    """What the build's matcher for the row's level does with one adapter row.

    A first-level row goes to the first-level shapes, as in the build: Huế's
    Wikidata row (wikidata_admin1.json) is the province Thừa Thiên Huế, and
    the second-level matcher would hand it Huế city's district instead.
    """
    a2, a1, a1_exact, names = drawn_index(iso3)
    key = {"name": row.get("name") or "", "aliases": row.get("aliases") or [],
           "parent_name": row.get("parent_name"),
           "parent_aliases": row.get("parent_aliases") or [],
           "point": be.row_point(row)}
    if row.get("level") == "admin1":
        admin1 = [dict(u, name=u.get("shape_name") or u["name"])
                  for (level, _), u in shapes(iso3).items() if level == "admin1"]
        by_key: dict = {}
        for e in admin1:
            by_key.setdefault(be.norm(e["name"]), []).append(e)
        be.add_known_as(by_key, admin1)
        entity, how = be.match_name(key, be.settle(by_key, [key["name"], *key["aliases"]]))
        return entity, how, names
    entity, how = be.match_admin2(key, a2, a1, a1_exact)
    return entity, how, names


class RealRowsReachTheirPolygons(unittest.TestCase):
    """Each declared row, as the file holds it, reaches the one polygon declared for it.

    Run through the build's own matcher against the published polygons, so an
    alias that a province name or a rival row would defeat fails here, and so
    does a file re-read under other names.
    """

    def test_every_aliased_row_reaches_its_alias(self):
        checked = 0
        for filename, by_id in be.ROW_ALIASES.items():
            if filename == "wikidata_admin2.json":
                continue
            data = rows(filename)
            if not data:
                continue
            for row_id, aliases in by_id.items():
                row = copy.deepcopy(data[row_id])
                iso3 = row_id[:3]
                if not shapes(iso3):
                    continue
                row["aliases"] = [*(row.get("aliases") or []), *aliases]
                entity, how, _ = join(row, iso3)
                self.assertIsNotNone(entity, f"{row_id} {row.get('name')!r}: {how}")
                self.assertIn(entity["name"], aliases, f"{row_id} reached {entity['name']!r}")
                checked += 1
        if not checked:
            self.skipTest("the published build or the files are not in this checkout")

    def test_the_rows_without_their_aliases_reach_nothing_or_elsewhere(self):
        # The aliases add joins; without them none of these rows found its
        # polygon, which is why they were declared.
        for filename in ("cod_ps_admin2.json", "clear_global_language.json"):
            data = rows(filename)
            for row_id, aliases in be.ROW_ALIASES.get(filename, {}).items():
                if row_id not in data or not shapes(row_id[:3]):
                    continue
                entity, _, _ = join(copy.deepcopy(data[row_id]), row_id[:3])
                self.assertFalse(entity is not None and entity["name"] in aliases,
                                 f"{row_id} needs no alias")

    def test_samraong_is_takeos_by_its_code(self):
        data = rows("clear_global_language.json")
        if "KHM-CG-KH2107" not in data or not shapes("KHM"):
            self.skipTest("CLEAR's Cambodian rows or the published build are not here")
        row = copy.deepcopy(data["KHM-CG-KH2107"])
        # Without its province the name is two polygons', and the matcher's
        # word pass reaches a third, Kampong Cham's Samraong Tong, which has a
        # row of its own: never Takeo's district.
        entity, how, names = join(row, "KHM")
        self.assertFalse(entity is not None and entity["name"] == "Samraong"
                         and names[entity["parent"]] == "Takeo", how)
        row["parent_name"] = be.ROW_PARENTS["clear_global_language.json"]["KHM-CG-KH2107"]
        entity, _, names = join(row, "KHM")
        self.assertEqual((entity["name"], names[entity["parent"]]), ("Samraong", "Takeo"))

    def test_argoba_reaches_amharas_special_woreda(self):
        data = rows("ethiopia_region.json")
        row = data.get("ETH-āmara-argoba-special-wereda")
        if not row or not shapes("ETH"):
            self.skipTest("Ethiopia's census rows or the published build are not here")
        self.assertFalse(row.get("no_shape"))
        entity, _, names = join(copy.deepcopy(row), "ETH")
        # The boundary file's "Special Woreda", read under the woreda's own name.
        self.assertEqual((entity["name"], names[entity["parent"]]),
                         ("Argoba Special Woreda", "Amhara"))
        self.assertTrue(data["ETH-āmara-bahir-dar-special-wereda"].get("no_shape"))


class RowUnionsFromTheFiles(unittest.TestCase):
    """The unions' parts, as the files hold them, make the figures the audit measured."""

    SUMS = {("MWI", "Zomba"): 947812, ("MWI", "Lilongwe"): 2993163,
            ("MWI", "Mzimba"): 1290719, ("MWI", "Blantyre"): 1381065,
            ("ETH", "Dire Dawa"): 521000, ("PRY", "Bella Vista"): 35013}

    def test_population_unions_sum_to_the_measured_figures(self):
        data = rows("cod_ps_admin2.json")
        if not data:
            self.skipTest("cod_ps_admin2.json is not in this checkout")
        for key, total in self.SUMS.items():
            spec = be.ROW_UNIONS[key]
            parts = [data[rid] for rid in spec["rows"]]
            self.assertEqual(sum(p["population"]["value"] for p in parts), total, key)
            self.assertEqual(len({p["population"]["year"] for p in parts}), 1, key)

    def test_survey_unions_are_pooled_by_their_respondents(self):
        data = rows("afrobarometer_region.json")
        if not data:
            self.skipTest("afrobarometer_region.json is not in this checkout")
        for key in (("MOZ", "Maputo"), ("STP", "São Tomé Province")):
            parts = [data[rid] for rid in be.ROW_UNIONS[key]["rows"]]
            for field in ("religion", "language"):
                for part in parts:
                    self.assertTrue(all(isinstance(e.get("count"), (int, float))
                                        for e in part[field]), (key, field, part["id"]))
            with mock.patch.object(be, "log"):
                pooled = be.pool_rows(key[1], [dict(p, _source="afrobarometer_region.json")
                                               for p in parts], key[0],
                                      "afrobarometer_region.json")
            self.assertIn("weighted by their published counts", pooled["language_note"])
        # Sao Tome's three strata hold 1,127 answers on religion.
        stp = [data[rid] for rid in be.ROW_UNIONS[("STP", "São Tomé Province")]["rows"]]
        self.assertEqual(sum(e["count"] for p in stp for e in p["religion"]), 1127)


class RefusedFiguresAreTheFilesFigures(unittest.TestCase):
    """A refusal scoped to one file quotes that file's figure for the country.

    If the file is re-read and the figure changes, the sentence would quote a
    number nobody shows, so it fails here.
    """

    def test_each_quoted_figure_is_in_its_file(self):
        import re
        checked = 0
        for (iso3, _), fields in be.NOT_THIS_GROUND.items():
            for field, (source, note) in fields.items():
                if source is None or field != "population":
                    continue
                data = rows(source)
                if not data:
                    continue
                # The first figure written with a thousands separator: a year
                # ("The 2021 figure of 180,507") is written without one.
                quoted = int(re.search(r"\d{1,3}(?:,\d{3})+", note).group().replace(",", ""))
                values = {(r.get("population") or {}).get("value")
                          for r in data.values()
                          if (r.get("country") or r["id"][:3]) == iso3
                          and isinstance(r.get("population"), dict)}
                self.assertIn(quoted, values, f"{iso3} {source}: {quoted}")
                checked += 1
        if not checked:
            self.skipTest("the refused files are not in this checkout")


class RegeneratedFiles(unittest.TestCase):
    """What the runner's re-reads wrote, checked record by record against the items."""

    def test_georgias_stated_gaps_give_way_to_nothing_older(self):
        data = rows("georgia.json")
        if not data:
            self.skipTest("georgia.json is not in this checkout")
        names = {"Abkhazia", "Gagra", "Gali", "Gudauta", "Gulripshi", "Ochamchire",
                 "Sokhumi", "Khobi", "Lanchkhuti", "Terjola", "Tkibuli", "Tsqaltubo"}
        found = {r["name"]: r for r in data.values() if r.get("name") in names}
        self.assertEqual(set(found), names)
        for name, record in found.items():
            pop = record["population"]
            self.assertEqual(pop["status"], "not_available", name)
            self.assertGreaterEqual(pop["displaces_before"], 2027, name)
            self.assertTrue(pop["displaces_undated"], name)

    def test_transnistria_is_the_left_bank(self):
        data = rows("transnistria_2015.json")
        if not data:
            self.skipTest("transnistria_2015.json is not in this checkout")
        for rid in ("MDA-pmr-admin1-transnistria", "MDA-pmr-admin2-transnistria"):
            self.assertEqual((data[rid]["population"]["value"], data[rid]["population"]["year"]),
                             (383810, 2015))
        self.assertEqual(475007 - 91197, 383810)

    def test_yamoussoukro_and_tarrafal(self):
        data = rows("wiki_table_population.json")
        if not data:
            self.skipTest("wiki_table_population.json is not in this checkout")
        civ = data["CIV-WT-district-autonome-de-yamoussoukro"]["population"]
        self.assertEqual((civ["value"], civ["year"]), (422072, 2021))
        self.assertEqual(372559 + 49513, 422072)       # its two departments, 2021
        cpv = data["CPV-WT-tarrafal"]["population"]
        self.assertEqual((cpv["value"], cpv["year"]), (16620, 2021))


class Nordjylland(unittest.TestCase):
    """DK05 dropped out of the crosswalk unremarked; decided, the reader places it."""

    def test_the_reader_follows_dk05_to_nordjylland(self):
        from scripts.fetch_census import ess_region
        crosswalk = {"DK05": {"superseded_by": "DK050"},
                     "DK050": {"nuts_level": 3, "level": "admin1", "name": "Nordjylland",
                               "shape_id": nuts_crosswalk.DECIDED["DK050"][0]}}
        self.assertEqual(ess_region.placement("DK05", crosswalk),
                         [{"level": "admin1", "shape_id": "84455774B84842167963849",
                           "name": "Nordjylland"}])
        drawn = {sid for (level, sid) in shapes("DNK") if level == "admin1"}
        if drawn:
            self.assertIn("84455774B84842167963849", drawn)


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


class SurveyCountsCutToWholeNumbers(unittest.TestCase):
    """Côte d'Ivoire's Gôh-Djiboua: Gôh's 40 respondents and Lôh-Djiboua's 32."""

    def part(self, name, religion):
        return {"id": name, "level": "admin1", "name": name, "country": "CIV",
                "_source": "afrobarometer_region.json",
                "sources": [{"name": "Afro", "field": "religion", "url": "u"}],
                "religion": religion, "population": {"status": "not_available"}}

    def goh_and_loh(self):
        goh = self.part("Gôh", [{"group": "Evangelical", "pct": 39.5, "count": 15},
                                {"group": "Muslim", "pct": 2.3, "count": 0},
                                {"group": "Christian", "pct": 58.2, "count": 23}])
        loh = self.part("Lôh-Djiboua", [{"group": "Evangelical", "pct": 44.9, "count": 14},
                                        {"group": "Christian", "pct": 55.1, "count": 17}])
        return goh, loh

    def test_a_union_weighed_by_respondents_keeps_a_small_groups_share(self):
        with mock.patch.object(be, "log"):
            pooled = be.pool_rows("Gôh-Djiboua", list(self.goh_and_loh()), "CIV",
                                  "afrobarometer_region.json", weigh="respondents")
        shares = {r["group"]: r["pct"] for r in pooled["religion"]}
        # 2.3% of Gôh's 38 counted, over 69: 1.3%, not the nought the counts give.
        self.assertAlmostEqual(shares["Muslim"], round(2.3 * 38 / 69, 1), places=1)
        self.assertAlmostEqual(shares["Evangelical"], round((39.5 * 38 + 44.9 * 31) / 69, 1),
                               delta=0.1)
        self.assertIn("weighted by their respondents", pooled["religion_note"])

    def test_only_the_unions_that_ask_are_weighed_by_respondents(self):
        # Without the union's word the counts are added, as for Maputo and São
        # Tomé, whose published shares stay as they were.
        with mock.patch.object(be, "log"):
            pooled = be.pool_rows("Gôh-Djiboua", list(self.goh_and_loh()), "CIV",
                                  "afrobarometer_region.json")
        self.assertIn("weighted by their published counts", pooled["religion_note"])
        self.assertNotIn("Muslim", {r["group"] for r in pooled["religion"]
                                    if r["pct"] > 0})
        asked = {key for key, spec in be.ROW_UNIONS.items() if spec.get("weigh")}
        self.assertEqual(asked, {("CIV", "Goh-Djiboua"), ("CIV", "Sassandra-Marahoue"),
                                 ("NER", "Tahoua/Agadez"), ("NER", "Zinder/Diffa"),
                                 ("TGO", "Maritime Region"), ("MDG", "Vatovavy-Fitovinany")})
        self.assertTrue(all(spec["weigh"] == "respondents" for key, spec in be.ROW_UNIONS.items()
                            if key in asked))


class WithdrawnFields(unittest.TestCase):
    """Niger: Round 9's languages and religion are not used; its ethnic groups are."""

    def test_a_withdrawn_field_leaves_the_row_and_its_citation(self):
        row = {"id": "NER-AB9-1102", "country": "NER", "name": "DOSSO",
               "religion": [{"group": "Muslim", "pct": 92.1}], "religion_note": "n",
               "language": [{"group": "Haoussa", "pct": 51.0}], "language_note": "n",
               "ethnicity": [{"group": "Haoussa", "pct": 51.6}],
               "sources": [{"field": "religion/ethnicity/language", "name": "Afro"}]}
        be.withdraw_fields(row, be.WITHDRAWN_FIELDS["afrobarometer_region.json"]["NER"])
        for key in ("language", "language_note", "religion", "religion_note"):
            self.assertNotIn(key, row)
        self.assertIn("ethnicity", row)
        self.assertEqual(row["sources"], [{"field": "ethnicity", "name": "Afro"}])

    def test_the_niger_unions_pool_ethnicity_alone(self):
        data = rows("afrobarometer_region.json")
        if not data:
            self.skipTest("afrobarometer_region.json is not in this checkout")
        fields = be.WITHDRAWN_FIELDS["afrobarometer_region.json"]["NER"]
        parts = [dict(data[rid], _source="afrobarometer_region.json")
                 for rid in be.ROW_UNIONS[("NER", "Zinder/Diffa")]["rows"]]
        for part in parts:
            be.withdraw_fields(part, fields)
        with mock.patch.object(be, "log"):
            pooled = be.pool_rows("Zinder/Diffa", parts, "NER", "afrobarometer_region.json")
        self.assertIsInstance(pooled.get("ethnicity"), list)
        self.assertNotIn("religion", pooled)
        self.assertNotIn("language", pooled)

    def test_a_row_can_lose_one_field(self):
        # Wikidata's seat for Togo's Savanes is not its seat: the capital leaves
        # that row alone, and its citation, so GeoNames' Dapaong can stand.
        withdrawn = be.WITHDRAWN_FIELDS["wikidata_admin1.json"]
        self.assertEqual(set(withdrawn), {"TGO-WD-Q279945", "SEN-WD-Q738061", "BEN-WD-Q29147",
                                          "LBY-WD-Q32845", "LBY-WD-Q26023", "DZA-WD-Q233645",
                                          "ETH-WD-Q193494", "TZA-WD-Q498067", "RWA-WD-Q845807",
                                          "GAB-WD-Q281109", "AGO-WD-Q191299", "ZMB-WD-Q738382",
                                          "NAM-WD-Q876512", "MUS-WD-Q934126", "MAR-WD-Q19951088"})
        row = {"id": "TGO-WD-Q279945", "country": "TGO", "name": "Savanes Region",
               "capital": "Durum Town", "population": {"value": 1, "year": 2022},
               "sources": [{"field": "population/capital/coordinates", "name": "Wikidata"}]}
        be.withdraw_fields(row, withdrawn[row["id"]])
        self.assertNotIn("capital", row)
        self.assertEqual(row["sources"], [{"field": "population/coordinates",
                                           "name": "Wikidata"}])

    def test_round_8s_french_is_noted_where_round_9_differs(self):
        notes = be.ROW_NOTES["afrobarometer_r8_language.json"]
        self.assertIn("12.5%", notes["NER-AB8-TILLABERI"]["language"])
        self.assertIn("6.8%", notes["NER-AB8-MARADI"]["language"])
        cited = be.ROW_NOTE_SOURCES["afrobarometer_r8_language.json"]["NER-AB8-MARADI"]
        self.assertEqual([(s["field"], s["name"]) for s in cited],
                         [("language note", "Afrobarometer Round 9 (2021-2023)")])
        data = rows("afrobarometer_r8_language.json")
        if data:
            french = {e["group"]: e["pct"] for e in data["NER-AB8-TILLABERI"]["language"]}
            self.assertEqual(french["French"], 12.5)


if __name__ == "__main__":
    unittest.main()
