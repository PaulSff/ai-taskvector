"""SelectColumns: keep only listed columns (pandas)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _select_columns_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    cols = params.get("columns") or inputs.get("columns")
    if isinstance(cols, str):
        cols = [c.strip() for c in cols.split(",") if c.strip()]
    if not cols:
        return out_table(df, state)
    if _HAS_PANDAS:
        cols = [c for c in cols if c in df.columns]
        if cols:
            df = df[cols]
    else:
        tbl = df_to_table(df)
        cols_set = set(cols)
        tbl = [{k: v for k, v in row.items() if k in cols_set} for row in tbl]
        return out_table(tbl, state)
    return out_table(df, state)


def register_select_columns() -> None:
    register_unit(UnitSpec(
        type_name="SelectColumns",
        input_ports=[("table", "table"), ("columns", "list")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_select_columns_step,
        controllable=True,
    ))
