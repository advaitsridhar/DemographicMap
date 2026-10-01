#!/usr/bin/env python3
"""Redraw second-order polygons the boundary file draws as the wrong number of units.

Two ways a boundary file can miscount a place, both found in Bolivia:

* **One feature for several units.** geoBoundaries draws the Cercado provinces
  of Beni, Cochabamba, Oruro and Tarija -- four provinces in four departments,
  the cities of Trinidad, Cochabamba, Oruro and Tarija -- as one multipolygon
  named "Cercado" and files it under Beni. No province's figures can go on it:
  every one of them would be a quarter of the truth drawn over four places.
  It is split here into its parts, each filed under the department its whole
  area lies in, and named as the province it is.
* **Several features for one unit.** Gualberto Villarroel (La Paz) is drawn as
  a polygon named for it and a second, two-part feature named "Gualberto
  Villarroe" that overlaps nothing else: the rest of the same province. The
  province's figures sit on the first and the second reads as an empty
  province of its own. They are merged here, under the first one's id, so the
  province is one unit with its whole ground.

Each redraw is measured before it is written: a split's every part must lie
at least 99% inside one first-order polygon, and no two parts in the same
one; a merge's features must not overlap any other second-order polygon of
the country. The output, data/processed/admin2_redrawn.geojson, is drawn by
the tiler into the second-order layer in place of the features it replaces
(``replaces`` on each feature), and read by the build the same way.

Usage:
    python3 scripts/make_redrawn.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_entities import BOUNDARIES, PROCESSED, whole  # noqa: E402

OUT = PROCESSED / "admin2_redrawn.geojson"
SIMPLIFY = 0.0005
INSIDE = 0.99

# iso3 -> redraws. A split names the feature and, per first-order polygon its
# parts fall in, the name the part is given; a merge names the features and
# the one whose id and name the whole keeps.
REDRAWS: dict[str, list[dict]] = {
    "BOL": [
        {"split": "80513517B48061932483413",
         "names": {"Beni": "Cercado", "Cochabamba": "Cercado", "Oruro": "Cercado",
                   "Tarija": "Cercado"}},
        {"merge": ["80513517B50126659359990", "80513517B19707809734230"],
         "keep": "80513517B50126659359990"},
    ],
    "ROU": [
        # UATs drawn as a main polygon and exclaves of the same name in the
        # same county; INS counts each once (romania_census.py puts the
        # figures on the largest). Checked: no part overlaps another UAT.
        {"merge": ["2599482B53905982235691", "2599482B31785088370324"],
         "keep": "2599482B53905982235691"},  # ARAD ARAD
        {"merge": ["2599482B25282375738521", "2599482B8806038231558"],
         "keep": "2599482B25282375738521"},  # ARAD LIPOVA
        {"merge": ["2599482B5177022501599", "2599482B19247594544458"],
         "keep": "2599482B5177022501599"},  # ARAD PAULIS
        {"merge": ["2599482B32759719925344", "2599482B71150188153613"],
         "keep": "2599482B32759719925344"},  # ARAD ZARAND
        {"merge": ["2599482B7783599693239", "2599482B2994749554598"],
         "keep": "2599482B7783599693239"},  # BOTOSANI UNGURENI
        {"merge": ["2599482B21199067234878", "2599482B16674200014647", "2599482B2860524053107", "2599482B289507895873"],
         "keep": "2599482B21199067234878"},  # BRASOV RUPEA
        {"merge": ["2599482B81185008860025", "2599482B910434267190"],
         "keep": "2599482B81185008860025"},  # BUZAU ULMENI
        {"merge": ["2599482B73805615564390", "2599482B18753621764646"],
         "keep": "2599482B73805615564390"},  # CALARASI CURCANI
        {"merge": ["2599482B91976879692627", "2599482B74221959783433"],
         "keep": "2599482B91976879692627"},  # DOLJ ROJISTE
        {"merge": ["2599482B30524546463793", "2599482B67036234724680"],
         "keep": "2599482B30524546463793"},  # HARGHITA MIERCUREA CIUC
        {"merge": ["2599482B24277216401355", "2599482B64409374014432"],
         "keep": "2599482B24277216401355"},  # HARGHITA BAILE TUSNAD
        {"merge": ["2599482B50254025578700", "2599482B79706795726804", "2599482B7850722509394", "2599482B60669636608871", "2599482B68924224489535", "2599482B45078767996614"],
         "keep": "2599482B50254025578700"},  # HARGHITA VLAHITA
        {"merge": ["2599482B17231771008992", "2599482B45908659223453"],
         "keep": "2599482B17231771008992"},  # HARGHITA BRADESTI
        {"merge": ["2599482B15077063893597", "2599482B50193316932914"],
         "keep": "2599482B15077063893597"},  # IASI ION NECULCE
        {"merge": ["2599482B74723640056211", "2599482B48526584820869", "2599482B98677359077398", "2599482B37635492647761"],
         "keep": "2599482B74723640056211"},  # ILFOV CERNICA
        {"merge": ["2599482B53836836172440", "2599482B33990588848115"],
         "keep": "2599482B53836836172440"},  # MEHEDINTI GRUIA
        {"merge": ["2599482B90638587736477", "2599482B13448214050806"],
         "keep": "2599482B90638587736477"},  # MURES BRANCOVENESTI
        {"merge": ["2599482B40977514976433", "2599482B65561652185041"],
         "keep": "2599482B40977514976433"},  # MURES SANTANA DE MURES
        {"merge": ["2599482B53428634835124", "2599482B28547583336437"],
         "keep": "2599482B53428634835124"},  # OLT VADASTRITA
        {"merge": ["2599482B8839717617259", "2599482B77905945866588"],
         "keep": "2599482B8839717617259"},  # SATU MARE RACSA
        {"merge": ["2599482B43386440731502", "2599482B60287900413907"],
         "keep": "2599482B43386440731502"},  # SATU MARE SANISLAU
        {"merge": ["2599482B24946279921532", "2599482B4700394891348"],
         "keep": "2599482B24946279921532"},  # SIBIU SIBIU
        {"merge": ["2599482B68453018923397", "2599482B49493178649584"],
         "keep": "2599482B68453018923397"},  # SIBIU SALISTE
        {"merge": ["2599482B89024892263144", "2599482B75206169001308"],
         "keep": "2599482B89024892263144"},  # SIBIU TALMACIU
        {"merge": ["2599482B40816245945082", "2599482B42247101066007", "2599482B61474640296478"],
         "keep": "2599482B40816245945082"},  # SIBIU CRISTIAN
        {"merge": ["2599482B75853154347523", "2599482B54964729595352", "2599482B20961139122315"],
         "keep": "2599482B75853154347523"},  # SIBIU POPLACA
        {"merge": ["2599482B75916194776070", "2599482B81731395938028", "2599482B67392717014509"],
         "keep": "2599482B75916194776070"},  # SIBIU TILISCA
        {"merge": ["2599482B40288902158054", "2599482B29791980403734"],
         "keep": "2599482B40288902158054"},  # TELEORMAN VIDELE
        {"merge": ["2599482B28400494535503", "2599482B35029885284970", "2599482B260875686248"],
         "keep": "2599482B28400494535503"},  # TELEORMAN BRAGADIRU
        {"merge": ["2599482B24334179401508", "2599482B95855728618173"],
         "keep": "2599482B24334179401508"},  # TELEORMAN BUJORU
        {"merge": ["2599482B84154453637694", "2599482B70697570158857"],
         "keep": "2599482B84154453637694"},  # TELEORMAN CIUPERCENI
        {"merge": ["2599482B67240297186090", "2599482B23402185147760"],
         "keep": "2599482B67240297186090"},  # TELEORMAN DRAGANESTI-VLASCA
        {"merge": ["2599482B76423000679583", "2599482B71059292210776"],
         "keep": "2599482B76423000679583"},  # TELEORMAN ISLAZ
        {"merge": ["2599482B88621270188908", "2599482B1586311708085"],
         "keep": "2599482B88621270188908"},  # TELEORMAN LUNCA
        {"merge": ["2599482B15929975886396", "2599482B91737143557292"],
         "keep": "2599482B15929975886396"},  # TIMIS TIMISOARA
        {"merge": ["2599482B95910170912575", "2599482B95683361390026"],
         "keep": "2599482B95910170912575"},  # TIMIS MARGINA
    ],
    "BGR": [
        # Zlatitsa, drawn as two features of one name; NSI counts it once.
        {"merge": ["11073933B76991292071364", "11073933B60320132010156"],
         "keep": "11073933B76991292071364"},  # Zlatitsa
    ],
    "HRV": [
        # Pirovac, Tisno, Tribunj and Murter-Kornati, which the file draws as
        # three polygons that cut Tisno in two: 'Opicina Pirovac' (107.9 km2)
        # holds Pirovac, Tribunj and mainland Tisno; 'Opicina Muter-Kornati'
        # (17.3 km2) is the island of Murter, with Murter and Tisno's villages
        # Betina and Jezera; 'Otok Kornat' (31.8 km2) is the rest of
        # Murter-Kornati. Measured with GeoNames' settlements (no other
        # municipality's falls in the three). croatia.py writes the four's sum
        # on the kept id once they are one.
        {"merge": ["41942358B56064565121242", "41942358B86068104638384",
                   "41942358B73644152682265"],
         "keep": "41942358B56064565121242"},  # Pirovac + Muter-Kornati + Otok Kornat
    ],
    "CYP": [
        # Dromolaxia and Meneou, which CYSTAT's 2021 census counts as the one
        # community Dromolaxia - Meneou (4014). (Not the two "Katydata" or the
        # two "Trimithousa": each second polygon is another village --
        # Agios Georgios (Lefkas), and the Trimithousa of the Chrysochou area,
        # Wikidata Q7842235 -- and cyprus_census pins the community to the
        # polygon that holds it.)
        {"merge": ["46923920B21347225976460", "46923920B15655385768829"],
         "keep": "46923920B21347225976460"},  # Dromolaxia + Meneou
    ],
    # Monaco: "The districts are those defined by Sovereign Order No. 4,481 of
    # 13 September 2013. Ravin Sainte-Devote has been incorporated into the
    # district of Les Moneghetti" (Monaco Statistics, 2025 Population census,
    # note to Figure 3). The boundary file still draws the Ravin as a ninth
    # district. Measured: the two touch and neither overlaps another district.
    "MCO": [
        {"merge": ["19026983B74744845285354", "19026983B23086528752726"],
         "keep": "19026983B74744845285354"},
    ],
    # Portugal: Montijo really is in two pieces -- a 316 km2 part inland to
    # the east (Canha and Pegoes, bordering Coruche, Montemor-o-Novo and
    # Vendas Novas) and a 20 km2 part on the Tagus that holds the town
    # (bordering Alcochete, Moita and Palmela) -- and Ilhavo is drawn as a
    # 19 km2 and a 4 km2 feature; INE counts each municipality once. Neither
    # part overlaps any other municipality; the census figures sit on the
    # larger part.
    "PRT": [
        {"merge": ["2272694B10601306194261", "2272694B43421578736002"],
         "keep": "2272694B10601306194261"},
        {"merge": ["2272694B86153814936026", "2272694B64447610403706"],
         "keep": "2272694B86153814936026"},
    ],
}


def features(level: str, iso3: str) -> dict[str, tuple[dict, object]]:
    import fiona
    from shapely.geometry import shape

    out = {}
    with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg") as src:
        for feat in src:
            props = dict(feat["properties"])
            if props.get("shapeGroup") == iso3 and feat["geometry"]:
                out[props["shapeID"]] = (props, whole(shape(feat["geometry"])))
    return out


def parts_of(geom) -> list:
    return list(getattr(geom, "geoms", [geom]))


def main() -> int:
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    out = []
    for iso3, redraws in REDRAWS.items():
        first = features("ADM1", iso3)
        second = features("ADM2", iso3)
        for redraw in redraws:
            if "split" in redraw:
                sid = redraw["split"]
                props, geom = second[sid]
                seen: dict[str, object] = {}
                for part in parts_of(geom):
                    inside = {fid: g.intersection(part).area / part.area
                              for fid, (_, g) in first.items() if g.intersects(part)}
                    fid, share = max(inside.items(), key=lambda kv: kv[1])
                    if share < INSIDE:
                        raise SystemExit(f"make_redrawn: a part of {props['shapeName']} "
                                         f"({sid}) is only {share:.1%} inside one first-order "
                                         "polygon; it cannot be filed under one")
                    if fid in seen:
                        raise SystemExit(f"make_redrawn: two parts of {sid} lie in "
                                         f"{first[fid][0]['shapeName']}")
                    seen[fid] = part
                for fid, part in seen.items():
                    parent = first[fid][0]["shapeName"]
                    name = redraw["names"].get(parent)
                    if name is None:
                        raise SystemExit(f"make_redrawn: {sid} has a part in {parent}, "
                                         "which the declaration does not name")
                    out.append({"type": "Feature", "properties": {
                        "shapeID": f"{sid}-{fid}", "shapeName": name, "shapeGroup": iso3,
                        "shapeType": "ADM2", "parentID": fid, "replaces": [sid],
                        "redrawn": (
                            f"geoBoundaries draws the {props['shapeName']} provinces of "
                            + ", ".join(sorted(first[f][0]["shapeName"] for f in seen))
                            + f" as one feature; this is the part in {parent}, drawn as a "
                            "unit of its own so its figures stand on its own ground.")},
                        "geometry": mapping(part.simplify(SIMPLIFY, preserve_topology=True))})
                print(f"  {iso3} {props['shapeName']}: split into {len(seen)} parts, in "
                      + ", ".join(first[f][0]["shapeName"] for f in seen))
            else:
                ids, keep = redraw["merge"], redraw["keep"]
                geoms = [second[i][1] for i in ids]
                for i in ids:
                    for other, (oprops, og) in second.items():
                        if other in ids or not og.intersects(second[i][1]):
                            continue
                        share = og.intersection(second[i][1]).area / second[i][1].area
                        if share > 0.01:
                            raise SystemExit(f"make_redrawn: {i} overlaps "
                                             f"{oprops['shapeName']} by {share:.1%}; it is "
                                             "not simply the rest of one unit")
                merged = whole(unary_union(geoms))
                inside = {fid: g.intersection(merged).area / merged.area
                          for fid, (_, g) in first.items() if g.intersects(merged)}
                fid = max(inside, key=inside.get)
                name = second[keep][0]["shapeName"]
                out.append({"type": "Feature", "properties": {
                    "shapeID": keep, "shapeName": name, "shapeGroup": iso3,
                    "shapeType": "ADM2", "parentID": fid, "replaces": ids,
                    "redrawn": (
                        f"geoBoundaries draws {name} as {len(ids)} features, one of them "
                        "labelled " + " and ".join(repr(second[i][0]["shapeName"]) for i in ids
                                                   if i != keep)
                        + "; they are drawn here as the one unit they are.")},
                    "geometry": mapping(merged.simplify(SIMPLIFY, preserve_topology=True))})
                print(f"  {iso3} {name}: {len(ids)} features merged under {keep}")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out},
                              ensure_ascii=False, separators=(",", ":")))
    print(f"make_redrawn: wrote {OUT.relative_to(ROOT)} ({len(out)} features)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
