"""FilterRows: filter rows by query or column + op + value (pandas)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _filter_rows_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    if not _HAS_PANDAS:
        return out_table(df_to_table(df), state)
    import pandas as pd
    query_expr = params.get("query") or inputs.get("query")
    column = params.get("column") or inputs.get("column")
    op = (params.get("op") or inputs.get("op") or "le").strip().lower()
    raw_val = inputs.get("value") if "value" in inputs else params.get("value")
    if query_expr:
        try:
            df = df.query(query_expr)
        except Exception:
            pass
    elif column is not None and raw_val is not None:
        try:
            col = pd.to_numeric(df[column], errors="coerce")
            val = pd.to_numeric(raw_val, errors="ignore")
            if op == "lt":
                df = df[col < val]
            elif op == "le":
                df = df[col <= val]
            elif op == "gt":
                df = df[col > val]
            elif op == "ge":
                df = df[col >= val]
            elif op == "eq":
                df = df[df[column] == raw_val]
            elif op == "neq":
                df = df[df[column] != raw_val]
            else:
                df = df[col <= val]
        except Exception:
            pass
    return out_table(df, state)


def register_filter_rows() -> None:
    register_unit(UnitSpec(
        type_name="FilterRows",
        input_ports=[
            ("value", "float"),
            ("table", "table"),
            ("query", "str"),
            ("column", "str"),
            ("op", "str"),
        ],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_filter_rows_step,
        controllable=True,
        description="Filters rows by column, operator, and value (query or column/op/value); agent can set value for RL.",
    ))
