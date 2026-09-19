#!/usr/bin/env python3
"""Malaysia: religion by state and administrative district (probe stage).

Usage:
    python -m scripts.fetch_census.malaysia_religion --probe
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import http_get, log

BARMETER = "https://storage.dosm.gov.my/dashboards/kawasanku_admin_barmeter.parquet"
CALLOUT = "https://storage.dosm.gov.my/dashboards/kawasanku_admin_barmeter_callout.parquet"


def read_parquet(url: str) -> Any:
    import pyarrow.parquet as pq  # noqa: PLC0415
    blob = http_get(url, binary=True, timeout=300)
    return pq.read_table(io.BytesIO(blob)).to_pandas()


def probe() -> int:
    for url in (BARMETER, CALLOUT):
        log(f"== {url}")
        try:
            df = read_parquet(url)
        except Exception as exc:  # noqa: BLE001
            log(f"   failed: {exc!r}")
            continue
        log(f"   shape {df.shape}; columns {list(df.columns)}")
        log(f"   dtypes {dict(df.dtypes.astype(str))}")
        for col in df.columns:
            if df[col].dtype == object or str(df[col].dtype).startswith("str"):
                vals = df[col].dropna().unique()
                if len(vals) <= 40:
                    log(f"   {col}: {sorted(map(str, vals))}")
                else:
                    log(f"   {col}: {len(vals)} distinct, e.g. {sorted(map(str, vals))[:12]}")
        if "chart" in df.columns:
            rel = df[df["chart"].astype(str).str.contains("relig", case=False)]
            log(f"   religion rows: {len(rel)}")
            if "area_type" in rel.columns:
                for at in sorted(rel["area_type"].astype(str).unique()):
                    sub = rel[rel["area_type"].astype(str) == at]
                    log(f"   area_type={at}: {sub['area'].nunique()} areas")
                st = rel[rel["area_type"].astype(str) == "state"]
                for _, r in st.head(120).iterrows():
                    log("   " + " | ".join(f"{k}={r[k]}" for k in rel.columns))
                di = rel[rel["area_type"].astype(str) == "district"]
                for _, r in di.head(24).iterrows():
                    log("   " + " | ".join(f"{k}={r[k]}" for k in rel.columns))
            else:
                for _, r in rel.head(60).iterrows():
                    log("   " + " | ".join(f"{k}={r[k]}" for k in rel.columns))
        else:
            for _, r in df.head(30).iterrows():
                log("   " + " | ".join(f"{k}={r[k]}" for k in df.columns))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    if args.probe:
        return probe()
    raise SystemExit("malaysia_religion: only --probe is implemented yet")


if __name__ == "__main__":
    raise SystemExit(main())
