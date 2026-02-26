"""Filter unit: filter rows by column + op + value. Delegates to pandas when available (same as FilterRows)."""

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, table_to_df
from units.registry import UnitSpec, register_unit


def _filter_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Filter: table + column, op, value. Uses pandas boolean indexing when available."""
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"row_count": 0.0, "table": []}, state
    column = inputs.get("column") or params.get("column")
    op = (params.get("op") or inputs.get("op") or "le").strip().lower()
    raw_value = inputs.get("value") if "value" in inputs else params.get("value")
    if column is None or raw_value is None:
        tbl = df_to_table(df)
        return {"row_count": float(len(tbl)), "table": tbl}, state
    if _HAS_PANDAS:
        import pandas as pd
        try:
            col = pd.to_numeric(df[column], errors="coerce")
            val = pd.to_numeric(raw_value, errors="ignore")
            if op == "lt":
                df = df[col < val]
            elif op == "le":
                df = df[col <= val]
            elif op == "gt":
                df = df[col > val]
            elif op == "ge":
                df = df[col >= val]
            elif op == "eq":
                df = df[df[column] == raw_value]
            elif op == "neq":
                df = df[df[column] != raw_value]
            else:
                df = df[col <= val]
        except Exception:
            pass
        tbl = df_to_table(df)
        return {"row_count": float(len(tbl)), "table": tbl}, state
    # Fallback: list-of-dicts
    try:
        val_float = float(raw_value)
    except (TypeError, ValueError):
        val_float = raw_value
    out = []
    for row in (df if isinstance(df, list) else df_to_table(df)):
        if not isinstance(row, dict) or column not in row:
            continue
        cell = row[column]
        try:
            c = float(cell)
        except (TypeError, ValueError):
            c = cell
        if op == "lt" and c < val_float:
            out.append(row)
        elif op == "le" and c <= val_float:
            out.append(row)
        elif op == "gt" and c > val_float:
            out.append(row)
        elif op == "ge" and c >= val_float:
            out.append(row)
        elif op == "eq" and cell == raw_value:
            out.append(row)
        elif op == "neq" and cell != raw_value:
            out.append(row)
    return {"row_count": float(len(out)), "table": out}, state


def register_filter() -> None:
    register_unit(UnitSpec(
        type_name="Filter",
        input_ports=[
            ("value", "float"),  # first port = action when wired from agent
            ("table", "table"),
            ("column", "str"),
            ("op", "str"),
        ],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_filter_step,
        controllable=True,
    ))
