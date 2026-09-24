"""Namibia's constituencies as OCHA draws them, to put the right names on CGAZ's.

geoBoundaries CGAZ draws Namibia's constituencies in the right places and
labels them wrongly. The polygon at Windhoek, in Khomas, is called "Eenhana",
a town on the Angolan border; the one called "Katutura Central" lies in
Hardap, 90 km south of the city; seven polygons are called "Luderitz". Every
name join then puts a constituency's figures on another constituency's
ground, which looks exactly like a right answer.

This reads OCHA's common operational boundaries for Namibia (cod-ab-nam on
HDX), which carry each constituency's name and P-code, and writes each one's
outline, simplified, to data/processed/nam_adm2_reference.json. The build
measures every CGAZ polygon against these outlines and takes its name from
the one it is. Nothing here is joined to anything: it is the evidence the
relabelling is measured against.

    python -m scripts.fetch_census.namibia_shapes
"""
from __future__ import annotations

import argparse
import re
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, write_json
from .cod_ps import HEADERS, TIMEOUT, get, is_usable, licence

PACKAGE = "cod-ab-nam"
OUT = PROCESSED / "nam_adm2_reference.json"
# About 50 m at Namibia's latitude: far below the width of any constituency,
# and it keeps the file to a few hundred kilobytes.
SIMPLIFY = 0.0005


def pick(resources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The resource holding the second-level outlines: a shapefile archive."""
    def score(res: dict[str, Any]) -> int:
        text = f"{res.get('name')} {res.get('url')} {res.get('format')}".lower()
        if "shp" not in text and "shapefile" not in text:
            return 0
        return 2 if "adm2" in text else 1
    ranked = sorted(resources, key=score, reverse=True)
    return ranked[0] if ranked and score(ranked[0]) else None


def adm2_member(archive: Path) -> str | None:
    """The second-level layer inside the archive, by its file name."""
    with zipfile.ZipFile(archive) as zf:
        shps = [n for n in zf.namelist() if n.lower().endswith(".shp")]
    log(f"  layers: {shps}")
    for name in shps:
        if re.search(r"adm(in)?_?2(?!\d)", Path(name).name.lower()):
            return name
    return None


def field(props: dict[str, Any], *names: str) -> str:
    for name in names:
        for key, value in props.items():
            if key.lower() == name.lower() and value not in (None, ""):
                return str(value).strip()
    return ""


def read(archive: Path, member: str) -> list[dict[str, Any]]:
    import fiona
    from shapely.geometry import mapping, shape

    out = []
    with fiona.open(f"zip://{archive}!{member}") as src:
        log(f"  {member}: {len(src)} features, fields {list(src.schema['properties'])}")
        for feat in src:
            props = dict(feat["properties"])
            geom = shape(feat["geometry"])
            point = geom.representative_point()
            out.append({
                "pcode": field(props, "ADM2_PCODE", "admin2Pcode"),
                "name": field(props, "ADM2_EN", "admin2Name_en", "ADM2_NAME"),
                "adm1": field(props, "ADM1_EN", "admin1Name_en", "ADM1_NAME"),
                "adm1_pcode": field(props, "ADM1_PCODE", "admin1Pcode"),
                "point": [round(point.x, 5), round(point.y, 5)],
                "area": geom.area,
                "geometry": mapping(geom.simplify(SIMPLIFY, preserve_topology=True)),
            })
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    package = get("package_show", id=PACKAGE)
    log(f"{PACKAGE}: {package.get('title')}")
    log(f"  licence: {licence(package)}")
    for res in package.get("resources") or ():
        log(f"  resource: {res.get('name')} [{res.get('format')}] {res.get('url')}")
    if not is_usable(package):
        raise SystemExit(f"{PACKAGE}: licence not one this map may read")
    resource = pick(package.get("resources") or [])
    if resource is None:
        raise SystemExit(f"{PACKAGE}: no shapefile archive among the resources")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "cod-ab-nam.zip"
        with urllib.request.urlopen(urllib.request.Request(
                str(resource["url"]), headers=HEADERS), timeout=TIMEOUT) as fh:
            archive.write_bytes(fh.read())
        log(f"  read {resource.get('name')}: {archive.stat().st_size:,} bytes")
        member = adm2_member(archive)
        if member is None:
            raise SystemExit(f"{PACKAGE}: no second-level layer in the archive")
        units = read(archive, member)
    missing = [u for u in units if not (u["pcode"] and u["name"])]
    if missing or not units:
        raise SystemExit(f"{PACKAGE}: {len(missing)} of {len(units)} outlines "
                         f"carry no name or P-code; nothing written")
    write_json(OUT, {
        "source": f"OCHA, Common Operational Dataset -- administrative boundaries "
                  f"({PACKAGE}), {resource.get('name')}",
        "url": f"https://data.humdata.org/dataset/{PACKAGE}",
        "licence": licence(package),
        "units": sorted(units, key=lambda u: u["pcode"]),
    })
    log(f"  {len(units)} constituencies in "
        f"{len({u['adm1'] for u in units})} regions written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
