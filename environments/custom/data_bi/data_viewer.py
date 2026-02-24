#!/usr/bin/env python3
"""
Minimal data viewer for data_bi: load a table (JSON/CSV) and show pandas + matplotlib.
Use before/during development to inspect data. Requires: pandas, matplotlib.

  python -m environments.custom.data_bi.data_viewer path/to/data.json
  python -m environments.custom.data_bi.data_viewer path/to/data.csv --format csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="View table data (JSON/CSV) with pandas and matplotlib")
    parser.add_argument("path", type=str, help="Path to JSON or CSV file")
    parser.add_argument("--format", choices=["json", "csv", "jsonl"], default="json", help="File format")
    parser.add_argument("--head", type=int, default=0, help="Show only first N rows (0 = all)")
    parser.add_argument("--hist", action="store_true", help="Plot histograms of numeric columns")
    parser.add_argument("--no-table", action="store_true", help="Skip printing table head")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"File not found: {path}")
        return

    try:
        import pandas as pd
    except ImportError:
        print("Install pandas: pip install pandas")
        return

    if args.format == "csv":
        df = pd.read_csv(path)
    elif args.format == "jsonl":
        df = pd.read_json(path, lines=True)
    else:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            for key in ("data", "offers", "rows", "records"):
                if key in data and isinstance(data[key], list):
                    df = pd.DataFrame(data[key])
                    break
            else:
                df = pd.DataFrame([data])
        else:
            df = pd.DataFrame()

    if df.empty:
        print("Empty table.")
        return

    if args.head:
        df = df.head(args.head)

    print(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
    print("Columns:", list(df.columns))
    if not args.no_table:
        print(df.head(10).to_string())

    if args.hist:
        try:
            import matplotlib.pyplot as plt
            num = df.select_dtypes(include="number")
            if num.columns.empty:
                print("No numeric columns to plot.")
                return
            ncols = min(4, len(num.columns))
            nrows = (len(num.columns) + ncols - 1) // ncols
            fig, axes = plt.subplots(nrows, ncols, figsize=(3 * ncols, 2.5 * nrows))
            if nrows == 1 and ncols == 1:
                axes = [[axes]]
            elif nrows == 1:
                axes = [axes]
            for idx, col in enumerate(num.columns):
                ax = axes[idx // ncols][idx % ncols]
                ax.hist(num[col].dropna(), bins=min(30, max(5, len(num) // 5)), edgecolor="black", alpha=0.7)
                ax.set_title(col)
            for idx in range(len(num.columns), nrows * ncols):
                axes[idx // ncols][idx % ncols].set_visible(False)
            plt.tight_layout()
            plt.show()
        except ImportError:
            print("Install matplotlib for --hist: pip install matplotlib")


if __name__ == "__main__":
    main()
