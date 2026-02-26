"""Head: first n rows (pandas head)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _head_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    k = inputs.get("n") or params.get("n") or params.get("k") or 10
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 10
    k = max(1, min(k, len(df)))
    if _HAS_PANDAS:
        df = df.head(k)
    else:
        df = df[:k]
    return out_table(df, state)


def register_head() -> None:
    register_unit(UnitSpec(
        type_name="Head",
        input_ports=[("table", "table"), ("n", "int")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_head_step,
        controllable=True,
    ))
