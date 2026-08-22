#!/usr/bin/env python3
"""Administrative boundaries from geoBoundaries (gbOpen / CGAZ).

geoBoundaries is the only global ADM0/1/2 dataset with a genuinely
redistributable licence -- gbOpen is CC BY 4.0 (a few countries inherit ODbL or
CC-BY-SA from OpenStreetMap, which this script records per file so the
attribution page stays honest).  GADM is deliberately **not** used: its licence
forbids redistribution and commercial use, which a public repo cannot satisfy.

Two acquisition modes:

* ``--cgaz``      the global composite (ADM0/ADM1/ADM2), one file per level.
                  This is what the tiler consumes for the worldwide layers.
* ``--countries`` per-country gbOpen files at full or simplified precision,
                  used to add admin-2 country-by-country.

geoBoundaries stores release data in Git LFS, so ``raw.githubusercontent.com``
returns a 130-byte pointer rather than the file.  ``media.githubusercontent.com``
serves the real object, and the API host is tried first; all three are wired up
with fallbacks because at least one is usually reachable.

Usage:
    python scripts/fetch_boundaries.py --cgaz --levels ADM0 ADM1 ADM2
    python scripts/fetch_boundaries.py --countries USA GBR CAN BRA --level ADM2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import RAW, download, http_json, log, write_json  # noqa: E402

API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{level}/"
RAW_GH = ("https://raw.githubusercontent.com/wmgeolab/geoBoundaries/main/releaseData")
MEDIA_GH = ("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/main/releaseData")

DEST = RAW / "boundaries"
LEVELS = ("ADM0", "ADM1", "ADM2", "ADM3")

# The plan's priority list: countries whose admin-2 demographics are actually
# published through an API, so the extra geometry earns its bytes.
PRIORITY_ADM2 = [
    "USA", "GBR", "CAN", "BRA", "AUS", "IND", "IDN", "PHL", "MEX", "DEU",
    "FRA", "ESP", "ITA", "POL", "ROU", "NLD", "ZAF", "NGA", "KEN", "JPN",
    "CHN", "RUS", "ARG", "COL", "CHL", "PER", "VNM", "THA", "TUR", "EGY",
    "PAK", "BGD", "ETH", "TZA", "UKR", "SWE", "NOR", "FIN", "DNK", "IRL",
    "PRT", "GRC", "CZE", "HUN", "AUT", "CHE", "BEL", "NZL", "KOR", "MYS",
]


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(40).startswith(b"version https://git-lfs")
    except OSError:
        return False


def fetch_with_fallbacks(rel_path: str, dest: Path, *, force: bool = False) -> Path | None:
    """Try the media (LFS) host, then the plain raw host, for one release file."""
    for base in (MEDIA_GH, RAW_GH):
        try:
            download(f"{base}/{rel_path}", dest, force=force)
        except Exception as exc:
            log(f"  {base.split('//')[1].split('/')[0]} failed: {exc}")
            continue
        if is_lfs_pointer(dest):
            log("  got a Git LFS pointer, not the object -- trying the next host")
            dest.unlink(missing_ok=True)
            continue
        return dest
    return None


def fetch_cgaz(levels: list[str], fmt: str, force: bool) -> dict[str, Any]:
    """The global composite layers.

    geoBoundaries' own caveat applies and is surfaced in the app's About panel:
    CGAZ simplifies polygons, fills gaps along shared edges, and substitutes
    disputed areas with US Department of State definitions.  Good enough for a
    demographics choropleth; not authoritative for boundary disputes.
    """
    out: dict[str, Any] = {}
    for level in levels:
        name = f"geoBoundariesCGAZ_{level}.{fmt}"
        dest = DEST / name
        got = fetch_with_fallbacks(f"CGAZ/{name}", dest, force=force)
        if got is None:
            log(f"  ! CGAZ {level} unavailable")
            continue
        out[level] = {"path": str(got.relative_to(RAW.parent.parent)),
                      "bytes": got.stat().st_size,
                      "license": "CC BY 4.0 (geoBoundaries CGAZ)"}
    return out


def fetch_country(iso3: str, level: str, *, simplified: bool, force: bool) -> dict[str, Any] | None:
    """One gbOpen country file, with its per-file licence metadata."""
    meta: dict[str, Any] = {}
    try:
        meta = http_json(API.format(iso3=iso3, level=level), timeout=60)
        if isinstance(meta, list):
            meta = meta[0] if meta else {}
    except Exception as exc:
        log(f"  {iso3}/{level}: API unreachable ({exc}); falling back to the raw layout")

    suffix = "_simplified" if simplified else ""
    filename = f"geoBoundaries-{iso3}-{level}{suffix}.geojson"
    dest = DEST / "gbOpen" / iso3 / f"{level}{suffix}.geojson"

    url = meta.get("simplifiedGeometryGeoJSON") if simplified else meta.get("gjDownloadURL")
    got = None
    if url:
        try:
            download(url, dest, force=force)
            got = None if is_lfs_pointer(dest) else dest
        except Exception as exc:
            log(f"  {iso3}/{level}: API download failed ({exc})")
    if got is None:
        got = fetch_with_fallbacks(f"gbOpen/{iso3}/{level}/{filename}", dest, force=force)
    if got is None:
        return None

    return {
        "iso3": iso3,
        "level": level,
        "path": str(got),
        "bytes": got.stat().st_size,
        "license": meta.get("boundaryLicense") or "see geoBoundaries metadata",
        "license_url": meta.get("licenseDetail") or meta.get("boundaryLicenseURL"),
        "source": meta.get("boundarySource") or meta.get("boundarySource-1"),
        "release": meta.get("boundaryYearRepresented") or meta.get("boundaryUpdate"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cgaz", action="store_true", help="download the global composite layers")
    ap.add_argument("--levels", nargs="*", default=["ADM0", "ADM1", "ADM2"], choices=LEVELS)
    ap.add_argument("--format", default="gpkg", choices=["gpkg", "geojson", "topojson"],
                    help="CGAZ format; gpkg is ~2.5x smaller than geojson and streams")
    ap.add_argument("--countries", nargs="*", default=None,
                    help="ISO3 codes for per-country gbOpen files ('priority' for the built-in list)")
    ap.add_argument("--level", default="ADM2", choices=LEVELS, help="level for --countries")
    ap.add_argument("--full-precision", action="store_true",
                    help="fetch HPSCU instead of the simplified SSCU files")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.cgaz and args.countries is None:
        ap.error("pass --cgaz and/or --countries")

    manifest: dict[str, Any] = {"cgaz": {}, "countries": [], "unavailable": []}

    if args.cgaz:
        log(f"fetch_boundaries: CGAZ {' '.join(args.levels)} ({args.format})")
        manifest["cgaz"] = fetch_cgaz(args.levels, args.format, args.force)

    if args.countries is not None:
        codes = PRIORITY_ADM2 if args.countries in ([], ["priority"]) else [c.upper() for c in args.countries]
        log(f"fetch_boundaries: gbOpen {args.level} for {len(codes)} countries")
        for iso3 in codes:
            entry = fetch_country(iso3, args.level, simplified=not args.full_precision,
                                  force=args.force)
            if entry:
                manifest["countries"].append(entry)
            else:
                # A missing ADM2 usually means the country genuinely has no
                # second-level divisions -- data, not an error.
                log(f"  {iso3}/{args.level}: not published")
                manifest["unavailable"].append({"iso3": iso3, "level": args.level})

    existing = {}
    manifest_path = DEST / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
    merged = {
        "cgaz": {**existing.get("cgaz", {}), **manifest["cgaz"]},
        "countries": manifest["countries"] or existing.get("countries", []),
        "unavailable": manifest["unavailable"] or existing.get("unavailable", []),
    }
    write_json(manifest_path, merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
