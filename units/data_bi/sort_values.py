"""SortValues: sort table by column(s) and direction (pandas)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _sort_values_step(
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
    by = params.get("by") or inputs.get("by")
    if isinstance(by, str):
        by = [by]
    if not by:
        return out_table(df, state)
    asc = params.get("ascending")
    if asc is None:
        asc = inputs.get("ascending", True)
    if isinstance(asc, str):
        asc = asc.lower() not in ("false", "0", "no")
    try:
        df = df.sort_values(by=[b for b in by if b in df.columns], ascending=asc)
    except Exception:
        pass
    return out_table(df, state)


def register_sort_values() -> None:
    register_unit(UnitSpec(
        type_name="SortValues",
        input_ports=[("table", "table"), ("by", "str"), ("ascending", "bool")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_sort_values_step,
    ))
