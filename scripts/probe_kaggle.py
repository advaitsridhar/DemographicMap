#!/usr/bin/env python3
"""Report what a Kaggle dataset holds, without reading it into the map.

A dataset on Kaggle is a bundle of files with no promise about what is in
them. Before an adapter is written against one, it is worth knowing which
files there are, how big, which columns they carry, and -- for survey
microdata, where the columns are codes -- what the variable labels say
those codes mean. This prints that and writes nothing else: the log is the
output.

Reads Stata (.dta) and SPSS (.sav) with their variable and value labels,
and CSV, Parquet and Excel by header. A column is reported when its name or
its label matches one of the terms, and for a reported column with few
distinct values the values are counted on a sample.

Credentials: kagglehub reads KAGGLE_USERNAME and KAGGLE_KEY from the
environment. Neither is printed. Without them a public dataset may still
download; a private or gated one will not, and this says so.

Usage:
    python -m scripts.probe_kaggle owner/dataset --terms prov,relig,宗教
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

TABULAR = {".csv", ".dta", ".sav", ".parquet", ".xlsx", ".xls", ".tsv"}


def log(msg: str) -> None:
    print(msg, flush=True)


def download(handle: str) -> Path:
    import kagglehub
    creds = bool(os.environ.get("KAGGLE_USERNAME")) and bool(os.environ.get("KAGGLE_KEY"))
    log(f"probe_kaggle: {handle} ({'with' if creds else 'without'} credentials)")
    return Path(kagglehub.dataset_download(handle))


def listing(root: Path) -> list[Path]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    log(f"  {len(files)} files, {sum(p.stat().st_size for p in files):,} bytes")
    for p in files:
        log(f"    {p.stat().st_size:>14,}  {p.relative_to(root)}")
    return files


def labels_of(path: Path) -> tuple[dict[str, str], dict[str, dict[Any, str]]]:
    """Variable labels and value labels, for a Stata or SPSS file."""
    try:
        import pyreadstat
    except ImportError:
        return {}, {}
    reader = pyreadstat.read_dta if path.suffix == ".dta" else pyreadstat.read_sav
    _, meta = reader(str(path), metadataonly=True)
    var_labels = dict(meta.column_names_to_labels or {})
    value_labels: dict[str, dict[Any, str]] = {}
    for col, labelset in (meta.variable_to_label or {}).items():
        value_labels[col] = dict((meta.value_labels or {}).get(labelset, {}))
    return var_labels, value_labels


def columns_of(path: Path) -> list[str]:
    import pandas as pd
    if path.suffix == ".dta":
        with pd.read_stata(str(path), iterator=True, convert_categoricals=False) as it:
            return list(it.variable_labels().keys()) if hasattr(it, "variable_labels") \
                else list(it.read(1).columns)
    if path.suffix == ".sav":
        import pyreadstat
        _, meta = pyreadstat.read_sav(str(path), metadataonly=True)
        return list(meta.column_names)
    if path.suffix == ".parquet":
        return list(pd.read_parquet(str(path)).columns[:0].append(
            pd.read_parquet(str(path), columns=None).columns))
    if path.suffix in {".xlsx", ".xls"}:
        return list(pd.read_excel(str(path), nrows=0).columns)
    sep = "\t" if path.suffix == ".tsv" else ","
    return list(pd.read_csv(str(path), nrows=0, sep=sep).columns)


def sample(path: Path, cols: list[str], rows: int):
    import pandas as pd
    if path.suffix == ".dta":
        return pd.read_stata(str(path), columns=cols, convert_categoricals=False,
                             chunksize=rows).__next__()
    if path.suffix == ".sav":
        import pyreadstat
        df, _ = pyreadstat.read_sav(str(path), usecols=cols, row_limit=rows)
        return df
    if path.suffix == ".parquet":
        return pd.read_parquet(str(path), columns=cols).head(rows)
    if path.suffix in {".xlsx", ".xls"}:
        return pd.read_excel(str(path), usecols=cols, nrows=rows)
    sep = "\t" if path.suffix == ".tsv" else ","
    return pd.read_csv(str(path), usecols=cols, nrows=rows, sep=sep)


def probe(path: Path, terms: list[str], rows: int, max_values: int) -> None:
    try:
        cols = columns_of(path)
    except Exception as e:  # a file that is not what its suffix says
        log(f"    cannot read: {type(e).__name__}: {str(e)[:120]}")
        return
    var_labels, value_labels = labels_of(path) if path.suffix in {".dta", ".sav"} else ({}, {})
    log(f"    {len(cols)} columns")
    pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    hits = [c for c in cols if pattern.search(c) or pattern.search(var_labels.get(c, ""))]
    if not hits:
        log(f"    no column or label matches {terms}")
        return
    log(f"    {len(hits)} matching columns:")
    try:
        df = sample(path, hits[:60], rows)
    except Exception as e:
        log(f"    (sample failed: {type(e).__name__}: {str(e)[:120]})")
        df = None
    for c in hits[:60]:
        label = var_labels.get(c, "")
        line = f"      {c}" + (f"  -- {label}" if label else "")
        if df is not None and c in df.columns:
            vals = df[c].dropna()
            nun = vals.nunique()
            line += f"  [{nun} distinct in {len(vals)} sampled]"
            if 0 < nun <= max_values:
                counts = vals.value_counts().head(max_values)
                vl = value_labels.get(c, {})
                line += "  " + ", ".join(
                    f"{k}{'=' + vl[k] if k in vl else ''}:{v}" for k, v in counts.items())
        log(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="owner/dataset as Kaggle names it")
    ap.add_argument("--terms", default="prov,relig,宗教,信仰,weight",
                    help="comma-separated words to match in column names and labels")
    ap.add_argument("--rows", type=int, default=20000, help="rows to sample per file")
    ap.add_argument("--max-values", type=int, default=12,
                    help="count a column's values when it has at most this many")
    ap.add_argument("--only", default=None, help="regex on the file path; others are listed only")
    args = ap.parse_args()
    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    try:
        root = download(args.dataset)
    except Exception as e:
        log(f"probe_kaggle: download failed: {type(e).__name__}: {str(e)[:300]}")
        log("  a gated or private dataset needs KAGGLE_USERNAME and KAGGLE_KEY in the "
            "runner's secrets")
        return 1
    files = listing(root)
    only = re.compile(args.only) if args.only else None
    for p in files:
        if p.suffix.lower() not in TABULAR:
            continue
        if only and not only.search(str(p.relative_to(root))):
            continue
        log(f"  == {p.relative_to(root)}")
        probe(p, terms, args.rows, args.max_values)
    return 0


if __name__ == "__main__":
    sys.exit(main())
