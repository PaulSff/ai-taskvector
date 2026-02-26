"""ValueCounts: count values in a column (pandas value_counts)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _value_counts_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table([], state)
    col = params.get("column") or inputs.get("column")
    if not col or col not in df.columns:
        return out_table([], state)
    vc = df[col].value_counts().reset_index()
    vc.columns = [col, "count"]
    return out_table(vc, state)


def register_value_counts() -> None:
    register_unit(UnitSpec(
        type_name="ValueCounts",
        input_ports=[("table", "table"), ("column", "str")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_value_counts_step,
        controllable=True,
    ))
