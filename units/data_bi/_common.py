"""
Shared helpers for data_bi units: table (list of dicts) <-> pandas DataFrame.
All Pandas/Sklearn units use these so tables flow consistently through the graph.
"""
from __future__ import annotations

from typing import Any

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    pd = None  # type: ignore[assignment]
    _HAS_PANDAS = False


def table_to_df(table: Any) -> "pd.DataFrame":
    """Convert table (list of dicts or DataFrame) to DataFrame. Returns empty DataFrame if no pandas."""
    if not _HAS_PANDAS:
        return _empty_df()
    if table is None:
        return _empty_df()
    if hasattr(table, "to_dict"):  # already DataFrame
        return table
    if isinstance(table, list):
        if not table:
            return _empty_df()
        return pd.DataFrame(table)
    return _empty_df()


def _empty_df() -> Any:
    if _HAS_PANDAS:
        return pd.DataFrame()
    return None


def _make_columns_unique(df: "pd.DataFrame") -> "pd.DataFrame":
    """Return a copy of df with duplicate column names made unique (col, col -> col, col_1). Avoids to_dict(orient='records') omitting columns and warning."""
    cols = list(df.columns)
    if len(cols) == len(set(cols)):
        return df
    seen: dict[Any, int] = {}
    new_cols: list[str] = []
    for c in cols:
        n = seen.get(c, 0)
        seen[c] = n + 1
        name = str(c) if c is not None else ""
        new_cols.append(f"{name}_{n}" if n > 0 else (name or "col"))
    out = df.copy()
    out.columns = new_cols
    return out


def df_to_table(df: Any) -> list[dict]:
    """Convert DataFrame to list of dicts for output. Handles None / no pandas. Duplicate column names are made unique so no data is omitted."""
    if df is None or (not _HAS_PANDAS):
        return []
    if hasattr(df, "to_dict"):
        df = _make_columns_unique(df)
        return df.to_dict(orient="records")
    if isinstance(df, list):
        return df
    return []


def table_row_count(table: Any) -> float:
    """Return row count as float (for first output port)."""
    if table is None:
        return 0.0
    if hasattr(table, "__len__") and not hasattr(table, "to_dict"):
        return float(len(table))
    if _HAS_PANDAS and hasattr(table, "shape"):
        return float(len(table))
    return 0.0


def out_table(table: Any, state: dict, extra: dict | None = None) -> tuple[dict, dict]:
    """Standard unit output: row_count (float), table (list of dicts). Optional extra keys (e.g. accuracy, predictions)."""
    if _HAS_PANDAS and hasattr(table, "shape"):
        n = float(len(table))
        tbl = df_to_table(table)
    else:
        tbl = table if isinstance(table, list) else []
        n = float(len(tbl))
    out: dict[str, Any] = {"row_count": n, "table": tbl}
    if extra:
        out.update(extra)
    return out, state
