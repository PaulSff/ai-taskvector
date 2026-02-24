"""GroupByAgg: group by column(s) and aggregate (pandas groupby)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _groupby_agg_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table(df if df is not None else [], state)
    import pandas as pd
    by = params.get("by") or inputs.get("by")
    if isinstance(by, str):
        by = [by]
    if not by or not all(b in df.columns for b in by):
        return out_table(df, state)
    agg = params.get("agg") or inputs.get("agg") or "size"
    try:
        if agg == "size" or agg is None:
            df = df.groupby(by=by, dropna=False).size().reset_index(name="count")
        elif isinstance(agg, str):
            num_cols = [c for c in df.columns if c not in by and pd.api.types.is_numeric_dtype(df[c])]
            df = df.groupby(by=by, dropna=False).agg({c: agg for c in num_cols}).reset_index()
        else:
            df = df.groupby(by=by, dropna=False).agg(agg).reset_index()
    except Exception:
        pass
    return out_table(df, state)


def register_groupby_agg() -> None:
    register_unit(UnitSpec(
        type_name="GroupByAgg",
        input_ports=[("table", "table"), ("by", "str"), ("agg", "str")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_groupby_agg_step,
    ))
