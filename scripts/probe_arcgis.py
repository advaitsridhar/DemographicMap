#!/usr/bin/env python3
"""Inspect an ArcGIS Online item and report what it actually contains.

Written because the build sandbox cannot reach arcgis.com, so the only way to
find out what an item holds is to have a CI runner look and print it. A lot of
census and administrative data is published as ArcGIS Hub items, and their
schemas cannot be guessed -- field names, layer ids and record counts all vary.

Given an item id or a portal URL, this reports:

* the item's title, type, licence and description;
* every layer or table in the service, with its record count;
* every field, with type and alias;
* a couple of sample rows, so the value formats are visible.

Nothing is written to disk: this is a read-only discovery step whose output is
the log. Use it to decide whether an item is worth an adapter, then write the
adapter against the schema it prints.

Usage:
    python scripts/probe_arcgis.py 16a1324c517048db890b86a87858a8ef
    python scripts/probe_arcgis.py "https://www.arcgis.com/home/item.html?id=..."
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import http_get, log  # noqa: E402

PORTAL = "https://www.arcgis.com/sharing/rest"


def item_id(value: str) -> str:
    """Accept a bare id or any portal URL carrying ``id=``."""
    if re.fullmatch(r"[0-9a-f]{32}", value.strip(), re.I):
        return value.strip()
    query = urllib.parse.urlparse(value).query
    found = urllib.parse.parse_qs(query).get("id")
    if found:
        return found[0]
    raise SystemExit(f"could not find an item id in {value!r}")


def get_json(url: str, **params: Any) -> Any:
    params.setdefault("f", "json")
    full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    text = http_get(full, cache=False, timeout=120)
    assert isinstance(text, str)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log(f"  ! non-JSON from {full}\n    starts: {text[:200]!r}")
        return None


def show_layer(service_url: str, layer: dict[str, Any], samples: int) -> None:
    lid = layer.get("id")
    url = f"{service_url}/{lid}"
    meta = get_json(url) or {}
    name = meta.get("name") or layer.get("name") or f"layer {lid}"
    kind = meta.get("type", "?")
    log(f"\n  --- [{lid}] {name}  ({kind})")

    count = get_json(f"{url}/query", where="1=1", returnCountOnly="true")
    if isinstance(count, dict) and "count" in count:
        log(f"      records: {count['count']:,}")

    fields = meta.get("fields") or []
    log(f"      {len(fields)} fields:")
    for field in fields:
        alias = field.get("alias") or ""
        alias = f"  ({alias})" if alias and alias != field.get("name") else ""
        log(f"        {field.get('name','?'):40s} {field.get('type','?'):22s}{alias}")

    if samples:
        rows = get_json(f"{url}/query", where="1=1", outFields="*",
                        resultRecordCount=samples, returnGeometry="false")
        features = (rows or {}).get("features") or []
        log(f"      {len(features)} sample row(s):")
        for feature in features:
            attrs = feature.get("attributes", {})
            preview = {k: v for k, v in list(attrs.items())[:14]}
            log(f"        {json.dumps(preview, default=str)[:400]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", help="ArcGIS item id, or a portal URL containing id=")
    ap.add_argument("--samples", type=int, default=2, help="sample rows per layer")
    ap.add_argument("--portal", default=PORTAL)
    args = ap.parse_args()

    iid = item_id(args.item)
    log(f"probe_arcgis: item {iid}")

    meta = get_json(f"{args.portal}/content/items/{iid}")
    if not meta or meta.get("error"):
        log(f"  cannot read the item: {(meta or {}).get('error')}")
        return 1

    for key in ("title", "type", "owner", "created", "modified", "licenseInfo",
                "accessInformation", "tags", "url", "size", "numViews"):
        value = meta.get(key)
        if value in (None, "", [], 0):
            continue
        if key in ("licenseInfo", "description"):
            value = re.sub(r"<[^>]+>", " ", str(value))
            value = re.sub(r"\s+", " ", value).strip()[:400]
        log(f"  {key:20s} {value}")
    snippet = meta.get("snippet")
    if snippet:
        log(f"  {'snippet':20s} {snippet}")

    service = meta.get("url")
    if not service:
        # No service: the payload may be an attached file (CSV, shapefile...).
        log("\n  no service URL -- this item is a file. Data endpoint:")
        log(f"    {args.portal}/content/items/{iid}/data")
        return 0

    root = get_json(service)
    if not root:
        return 1
    layers = (root.get("layers") or []) + (root.get("tables") or [])
    log(f"\n  service: {service}")
    log(f"  {len(layers)} layer(s)/table(s)")
    for layer in layers:
        show_layer(service, layer, args.samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
